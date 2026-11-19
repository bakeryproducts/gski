import { existsSync, readdirSync, readFileSync, statSync } from "node:fs"
import { dirname, join } from "node:path"
import { flat, fmtModelRef, round4, sumTokens } from "./format"
import { REGISTRY, type Ocm, type Run, type Stream, type Task } from "./types"

export function fold(text: string) {
  const tasks = new Map<string, Task>()
  for (const line of text.split("\n")) {
    if (!line.trim()) continue
    let ev: any
    try {
      ev = JSON.parse(line)
    } catch {
      continue
    }
    if (!ev || ev.id == null) continue
    let t = tasks.get(ev.id)
    if (!t) {
      t = { id: ev.id, attempts: 0, cost: 0, status: "pending" }
      tasks.set(ev.id, t)
    }
    const { t: ts, denied, cost, tokens, ...rest } = ev
    t.updated = ts
    if (Array.isArray(denied) && !denied.length) delete t.denied
    else if (denied) (t.denied ??= []).push(denied)
    t.cost = round4(t.cost + (cost || 0))
    if (tokens) t.tokens = sumTokens([t.tokens, tokens])
    Object.assign(t, rest)
  }
  return tasks
}

export function findUp(dir: string, name: string) {
  let d = dir
  while (true) {
    try {
      if (statSync(join(d, name)).isDirectory()) return d
    } catch {}
    const p = dirname(d)
    if (p === d) return undefined
    d = p
  }
}

const stamp = (p: string) => {
  try {
    const s = statSync(p)
    return `${s.mtimeMs}:${s.size}`
  } catch {
    return ""
  }
}

const ocmCache = new Map<string, { key: string; ocm: Ocm }>()

export function loadOcm(root: string): Ocm | undefined {
  const lp = join(root, ".ocm", "ledger.jsonl")
  const cp = join(root, ".ocm", "ocm.json")
  const key = [stamp(lp), stamp(cp)].join("|")
  if (key === "|") return undefined
  const hit = ocmCache.get(root)
  if (hit && hit.key === key) return hit.ocm
  let cfg: Record<string, any> = {}
  try {
    cfg = JSON.parse(readFileSync(cp, "utf8"))
  } catch {}
  const byId = new Map<string, Stream>()
  if (existsSync(lp)) {
    for (const line of readFileSync(lp, "utf8").split("\n")) {
      if (!line.trim()) continue
      try {
        const ev = JSON.parse(line)
        if (!ev || ev.id == null) continue
        const { t: ts, denied, ...rest } = ev
        const s = byId.get(ev.id) ?? { id: ev.id }
        s.updated = ts
        if (Array.isArray(denied) && !denied.length) delete s.denied
        else if (denied) (s.denied ??= []).push(denied)
        Object.assign(s, rest)
        byId.set(ev.id, s)
      } catch {}
    }
  }
  const streams = [...byId.values()].sort((a, b) => (b.updated || 0) - (a.updated || 0))
  const ocm: Ocm = { root, manager: cfg.manager, streams }
  ocmCache.set(root, { key, ocm })
  return ocm
}

export function scanOcm(dir: string, runsList: Run[], extraSid?: string): Ocm | undefined {
  const up = findUp(dir, ".ocm")
  if (up) {
    const direct = loadOcm(up)
    if (direct) return direct
  }
  let projects: string[] = []
  try {
    projects = readFileSync(REGISTRY, "utf8").split("\n").filter(Boolean)
  } catch {
    return undefined
  }
  const orchIds = new Set(runsList.map((r) => r.cfg?.orchestrator).filter(Boolean))
  if (extraSid) orchIds.add(extraSid)
  for (const p of projects) {
    const ocm = loadOcm(p)
    if (!ocm) continue
    if (
      ocm.streams.some(
        (s) => (s.session && orchIds.has(s.session)) || (s.dir && (dir === s.dir || dir.startsWith(s.dir + "/"))),
      )
    ) {
      return ocm
    }
  }
  return undefined
}

const runCache = new Map<string, { key: string; run: Run }>()

export function loadRun(dir: string, name: string, rootDir: string): Run | undefined {
  const lp = join(dir, "ledger.jsonl")
  const rp = join(dir, "run.json")
  const bp = join(dir, "brief.md")
  const key = [stamp(lp), stamp(rp), stamp(bp)].join("|")
  const hit = runCache.get(dir)
  if (hit && hit.key === key) return hit.run
  let cfg: Record<string, any> = {}
  try {
    cfg = JSON.parse(readFileSync(rp, "utf8"))
  } catch {}
  const tasks = existsSync(lp) ? [...fold(readFileSync(lp, "utf8")).values()] : []
  const counts: Record<string, number> = {}
  for (const t of tasks) counts[t.status] = (counts[t.status] || 0) + 1
  let last = 0
  try {
    last = Math.floor(statSync(existsSync(lp) ? lp : rp).mtimeMs / 1000)
  } catch {}
  const run: Run = {
    key: `run:${dir}`,
    kind: "run",
    name,
    dir,
    projectDir: cfg.dir || rootDir,
    cfg,
    tasks,
    counts,
    total: tasks.length,
    cost: round4(tasks.reduce((a, t) => a + (t.cost || 0), 0)),
    last,
    brief: existsSync(bp) ? readFileSync(bp, "utf8").slice(0, 20000) : "",
  }
  runCache.set(dir, { key, run })
  return run
}

export function scan(root: string): Run[] {
  const base = join(root, ".ocq", "runs")
  let names: string[] = []
  try {
    names = readdirSync(base)
  } catch {
    return []
  }
  return names
    .filter((n) => existsSync(join(base, n, "run.json")))
    .map((n) => loadRun(join(base, n), n, root))
    .filter((r): r is Run => !!r)
    .sort((a, b) => b.last - a.last)
}

export function isLiveRun(r: Run, activeIds: Set<string>) {
  return !!(
    r.counts.running ||
    r.counts.pending ||
    r.counts.reported ||
    r.stream?.status === "running" ||
    r.stream?.status === "reported" ||
    (r.kind === "orch" && activeIds.has(r.cfg?.orchestrator))
  )
}

export function buildRuns(opts: {
  diskRuns: Run[]
  ocm?: Ocm
  watchDir?: string
  activeIds: Set<string>
  curSid?: string
  trackedOrch?: string
  localSessions: any[]
  remoteSessions: any[]
}): Run[] {
  const { diskRuns, ocm, watchDir, activeIds, curSid, trackedOrch, localSessions, remoteSessions } = opts
  const streamBySid = new Map<string, Stream>()
  if (ocm) {
    for (const s of ocm.streams) {
      if (s.session) streamBySid.set(s.session, s)
    }
  }

  const out: Run[] = []
  const coveredSids = new Set<string>()
  for (const r of diskRuns) {
    const sid = r.cfg?.orchestrator
    if (sid) coveredSids.add(sid)
    const st = sid ? streamBySid.get(sid) : undefined
    out.push(st ? { ...r, stream: st, last: Math.max(r.last, st.updated || 0) } : r)
  }

  if (ocm) {
    for (const s of ocm.streams) {
      if (s.session && coveredSids.has(s.session)) continue
      if (s.session) coveredSids.add(s.session)
      const pdir = s.dir || ocm.root
      out.push({
        key: `ocm:${ocm.root}:${s.id}`,
        kind: "ocm",
        name: s.id,
        dir: pdir,
        projectDir: pdir,
        cfg: { orchestrator: s.session, dir: pdir, agent: "orchestrator", model: s.model },
        tasks: [],
        counts: {},
        total: 0,
        cost: round4(s.cost || 0),
        last: s.updated || s.finished || s.started || 0,
        brief: "",
        stream: s,
      })
    }
  }

  const newestExisting = out.reduce((mx, r) => Math.max(mx, r.last), 0)
  const candidates = new Map<string, any>()
  for (const s of localSessions) if (s?.id) candidates.set(s.id, s)
  for (const s of remoteSessions) if (s?.id && !candidates.has(s.id)) candidates.set(s.id, s)

  const standalone = [...candidates.values()]
    .filter((s: any) => {
      if (!s?.id || s.time?.archived || coveredSids.has(s.id)) return false
      if (s.agent !== "orchestrator") return false
      if (s.title?.startsWith("ocm/") || s.title?.startsWith("ocq/")) return false
      const sdir = s.location?.directory
      return !watchDir || !sdir || sdir === watchDir
    })
    .sort((a: any, b: any) => (b.time?.updated || b.time?.created || 0) - (a.time?.updated || a.time?.created || 0))

  let addedFallback = false
  for (const s of standalone) {
    const updatedSec = Math.floor((s.time?.updated || s.time?.created || 0) / 1000)
    const keep =
      activeIds.has(s.id) ||
      s.id === curSid ||
      s.id === trackedOrch ||
      (newestExisting > 0 && updatedSec > newestExisting) ||
      (out.length === 0 && !addedFallback)
    if (!keep) continue
    addedFallback = true
    const pdir = s.location?.directory || watchDir || ""
    out.push({
      key: `orch:${s.id}`,
      kind: "orch",
      name: flat(s.title) || s.id.slice(0, 12),
      dir: pdir,
      projectDir: pdir,
      cfg: { orchestrator: s.id, dir: pdir, agent: "orchestrator", model: fmtModelRef(s.model) },
      tasks: [],
      counts: {},
      total: 0,
      cost: round4(s.cost || 0),
      last: updatedSec,
      brief: "",
    })
  }

  return out.sort((a, b) => b.last - a.last)
}
