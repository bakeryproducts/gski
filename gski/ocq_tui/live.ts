import { activity, lastText, listOf, sumTokens } from "./format"
import type { Live, Ocm, Run, Tokens } from "./types"

export async function pollRunTasks(
  client: any,
  run: Run,
  active: Record<string, any>,
  doneTokens: Record<string, Tokens>,
) {
  const running = run.tasks.filter((t) => t.status === "running" && t.session)
  const shells = running.length
    ? listOf(await client.shell.list({ location: { directory: run.projectDir } }).catch(() => undefined))
    : []
  const next: Record<string, Live> = {}
  await Promise.all(
    running.map(async (t) => {
      const sid = t.session as string
      const [rawInfo, msgs] = await Promise.all([
        client.session.get({ sessionID: sid }).catch(() => undefined),
        client.message
          .list({ sessionID: sid, limit: 15, order: "desc" })
          .then(listOf)
          .catch(() => []),
      ])
      const info = (rawInfo as any)?.data ?? rawInfo
      let state = active[sid] ? (active[sid].type === "retry" ? "retry" : "busy") : "idle"
      let acts = activity(msgs)
      if (state === "idle") {
        const bg = shells.filter((s: any) => s.status === "running" && (s.metadata || {}).sessionID === sid)
        if (bg.length) {
          state = "waiting"
          acts = [...bg.map((b: any) => ({ text: `bg shell: ${b.command}`, status: "running" })), ...acts]
        }
      }
      next[t.id] = { state, cost: info?.cost || 0, tokens: info?.tokens, activity: acts }
    }),
  )
  const newDone: Record<string, Tokens> = {}
  const missing = run.tasks.filter(
    (t) => t.session && t.status !== "running" && t.status !== "pending" && !t.tokens && !doneTokens[t.session],
  )
  for (const t of missing.slice(0, 20)) {
    const rawInfo: any = await client.session.get({ sessionID: t.session }).catch(() => undefined)
    const info = rawInfo?.data ?? rawInfo
    if (info) newDone[t.session] = sumTokens([info.tokens])
  }
  return { live: next, newDone }
}

export async function pollOrchSession(client: any, run: Run, active: Record<string, any>, diskRuns: Run[]) {
  const sid = run.cfg?.orchestrator as string | undefined
  if (!sid) return undefined
  const [rawInfo, msgs, shells] = await Promise.all([
    client.session.get({ sessionID: sid }).catch(() => undefined),
    client.message
      .list({ sessionID: sid, limit: 20, order: "desc" })
      .then(listOf)
      .catch(() => []),
    listOf(await client.shell.list({ location: { directory: run.projectDir } }).catch(() => undefined)),
  ])
  const info = (rawInfo as any)?.data ?? rawInfo
  let state = active[sid] ? (active[sid].type === "retry" ? "retry" : "busy") : "idle"
  let acts = activity(msgs)
  if (state === "idle") {
    const bg = shells.filter((s: any) => s.status === "running" && (s.metadata || {}).sessionID === sid)
    const childRuns = diskRuns.filter((r) => r.cfg?.orchestrator === sid && r.counts.running)
    if (bg.length || childRuns.length) {
      state = "waiting"
      acts = [
        ...childRuns.map((r) => ({ text: `ocq/${r.name}: ${r.counts.running} running`, status: "running" })),
        ...bg.map((b: any) => ({ text: `bg shell: ${b.command}`, status: "running" })),
        ...acts,
      ]
    }
  }
  return {
    sid,
    live: {
      state,
      cost: info?.cost || 0,
      tokens: info?.tokens ? sumTokens([info.tokens]) : undefined,
      activity: acts,
    } as Live,
    reply: msgs.length ? lastText(msgs).slice(0, 8000) : undefined,
  }
}

async function validSession(context: any, sid?: string): Promise<string | undefined> {
  if (!sid) return undefined
  const cached = context.data.session.get(sid) as any
  if (cached) return cached.time?.archived ? undefined : sid
  const info: any = await context.client.session.get({ sessionID: sid }).catch(() => undefined)
  const s = info?.data ?? info
  return s?.id && !s?.time?.archived ? sid : undefined
}

export async function findOrchestratorId(opts: {
  context: any
  cur?: Run
  ocm?: Ocm
  orchSession?: string
  runs: Run[]
  dir?: string
  isOcmMgr: (sid?: string) => boolean
  isWorkerSession: (sid?: string) => boolean
  onFound: (sid: string) => void
}): Promise<string | undefined> {
  const { context, cur, ocm, orchSession, runs, dir, isOcmMgr, isWorkerSession, onFound } = opts
  if (cur?.cfg?.orchestrator) return cur.cfg.orchestrator
  if (!cur && ocm) {
    const st = ocm.streams.find((s) => s.status === "running" && s.session) ?? ocm.streams.find((s) => s.session)
    const ok = await validSession(context, st?.session)
    if (ok) return ok
  }
  if (orchSession && !isOcmMgr(orchSession)) return orchSession
  for (const r of runs) if (r.cfg?.orchestrator) return r.cfg.orchestrator
  const canBeOrch = (s: any) =>
    s?.agent !== "manager" &&
    s?.agent !== "worker" &&
    !isOcmMgr(s?.id) &&
    !isWorkerSession(s?.id) &&
    !s?.title?.startsWith("ocq/") &&
    !s?.time?.archived
  if (dir) {
    try {
      const list = listOf(await context.client.session.list({ directory: dir, limit: 30 }).catch(() => undefined))
      const match = list.find((s: any) => s?.agent === "orchestrator" && !s?.time?.archived) ?? list.find(canBeOrch)
      if (match?.id) {
        onFound(match.id)
        return match.id
      }
    } catch {}
    try {
      const cached = context.data.session.list()
      const match =
        cached.find(
          (s: any) => s?.location?.directory === dir && s?.agent === "orchestrator" && !s?.time?.archived,
        ) ?? cached.find((s: any) => s?.location?.directory === dir && canBeOrch(s))
      if (match?.id) {
        onFound(match.id)
        return match.id
      }
    } catch {}
  }
  return undefined
}

export async function findManagerId(opts: {
  context: any
  cur?: Run
  ocm?: Ocm
  dir?: string
  mgrByDir: Record<string, string>
  onFound: (dir: string, sid: string) => void
}): Promise<string | undefined> {
  const { context, cur, ocm, dir, mgrByDir, onFound } = opts
  if (cur?.stream?.manager) {
    const ok = await validSession(context, cur.stream.manager)
    if (ok) return ok
  }
  const orchSid = cur?.cfg?.orchestrator
  if (ocm && orchSid) {
    const matched = ocm.streams.find((s) => s.session === orchSid && s.manager)
    const ok = await validSession(context, matched?.manager)
    if (ok) return ok
  }
  if (ocm?.manager) {
    const ok = await validSession(context, ocm.manager)
    if (ok) return ok
  }
  if (ocm) {
    for (const s of ocm.streams) {
      const ok = await validSession(context, s.manager)
      if (ok) return ok
    }
  }
  if (dir && mgrByDir[dir]) {
    const ok = await validSession(context, mgrByDir[dir])
    if (ok) return ok
  }
  if (dir) {
    try {
      const list = listOf(await context.client.session.list({ directory: dir, limit: 30 }).catch(() => undefined))
      const match = list.find((s: any) => s?.agent === "manager" && !s?.time?.archived)
      if (match?.id) {
        onFound(dir, match.id)
        return match.id
      }
    } catch {}
    try {
      const cached = [...context.data.session.list()].sort(
        (a: any, b: any) => (b?.time?.updated || 0) - (a?.time?.updated || 0),
      )
      const match = cached.find(
        (s: any) => s?.location?.directory === dir && s?.agent === "manager" && !s?.time?.archived,
      )
      if (match?.id) {
        onFound(dir, match.id)
        return match.id
      }
    } catch {}
  }
  return undefined
}
