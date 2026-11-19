import { Plugin } from "@opencode/plugin/tui"
import { TextAttributes, type ScrollBoxRenderable } from "@opentui/core"
import { useTerminalDimensions } from "@opentui/solid"
import { createEffect, createMemo, createSignal, For, on, onCleanup, Show } from "solid-js"
import { lastText, listOf, now, round4, runLabel, sumTokens } from "./format"
import { findManagerId, findOrchestratorId, pollOrchSession, pollRunTasks } from "./live"
import { buildRuns, findUp, isLiveRun, scan, scanOcm } from "./store"
import { HEAD, ORDER, ROUTE, ROW, type Live, type Ocm, type Run, type Task, type Tokens } from "./types"
import { FooterView, OrchView, RunView, statusColor } from "./views"

export default Plugin.define({
  id: "gski.ocq",
  setup(context) {
    const [root, setRoot] = createSignal<string>()
    const [diskRuns, setDiskRuns] = createSignal<Run[]>([])
    const [live, setLive] = createSignal<Record<string, Live>>({})
    const [orchLive, setOrchLive] = createSignal<Record<string, Live>>({})
    const [activeIds, setActiveIds] = createSignal<Set<string>>(new Set())
    const [remoteSessions, setRemoteSessions] = createSignal<any[]>([])
    const [replies, setReplies] = createSignal<Record<string, string>>({})
    const [doneTokens, setDoneTokens] = createSignal<Record<string, Tokens>>({})
    const [server, setServer] = createSignal(true)
    const [clock, setClock] = createSignal(now())
    const [opened, setOpened] = createSignal(false)

    const [selRun, setSelRun] = createSignal<string>()
    const [selId, setSelId] = createSignal<string>()
    const [brief, setBrief] = createSignal(false)
    const [pane, setPane] = createSignal(true)
    const [zoom, setZoom] = createSignal(false)
    const [ocm, setOcm] = createSignal<Ocm>()
    const [orchSession, setOrchSession] = createSignal<string>()
    const [mgrByDir, setMgrByDir] = createSignal<Record<string, string>>({})

    const activeSessionId = () => {
      const r = context.ui.router.current()
      return r.type === "session" ? r.sessionID : (r as any).data?.sessionID
    }

    const activeDir = () => {
      const sid = activeSessionId()
      const d = sid ? (context.data.session.get(sid) as any)?.location?.directory : undefined
      return d || context.location?.directory || context.data.location.default()?.directory || process.cwd()
    }

    const isLive = (r: Run) => isLiveRun(r, activeIds())

    const runs = createMemo<Run[]>(() => {
      let localSessions: any[] = []
      try {
        localSessions = context.data.session.list() as any[]
      } catch {}
      return buildRuns({
        diskRuns: diskRuns(),
        ocm: ocm(),
        watchDir: root() ?? ocm()?.root ?? activeDir(),
        activeIds: activeIds(),
        curSid: activeSessionId(),
        trackedOrch: orchSession(),
        localSessions,
        remoteSessions: remoteSessions(),
      })
    })

    const isWorkerSession = (sid?: string) => !!sid && diskRuns().some((run) => run.tasks.some((t) => t.session === sid))
    const isOcmOrch = (sid?: string) => !!sid && !!ocm()?.streams.some((s) => s.session === sid)
    const isOcmMgr = (sid?: string) =>
      !!sid && (ocm()?.manager === sid || !!ocm()?.streams.some((s) => s.manager === sid))

    const trackSession = (sid?: string) => {
      if (!sid) return
      const sInfo = context.data.session.get(sid) as any
      if (!sInfo) return
      const sDir = sInfo.location?.directory
      if (sInfo.agent === "manager" || isOcmMgr(sid)) {
        if (sDir) setMgrByDir((m) => (m[sDir] === sid ? m : { ...m, [sDir]: sid }))
        return
      }
      if (
        sInfo.agent === "orchestrator" ||
        isOcmOrch(sid) ||
        (sInfo.agent !== "worker" && !isWorkerSession(sid) && !sInfo.title?.startsWith("ocq/"))
      ) {
        setOrchSession(sid)
      }
    }

    const refreshFiles = () => {
      const dir = activeDir()
      const r = findUp(dir, ".ocq")
      if (r !== root()) setRoot(r)
      const localRuns = r ? scan(r) : []
      const m = scanOcm(dir, localRuns, activeSessionId())
      const byDir = new Map<string, Run>()
      for (const run of localRuns) byDir.set(run.dir, run)
      if (m) {
        for (const s of m.streams) {
          if (s.dir && s.dir !== r && s.session) {
            for (const run of scan(s.dir)) {
              if (run.cfg?.orchestrator === s.session && !byDir.has(run.dir)) byDir.set(run.dir, run)
            }
          }
        }
      }
      setDiskRuns([...byDir.values()])
      setOcm(m)
      trackSession(activeSessionId())
    }

    const current = createMemo(() => {
      const rs = runs()
      return rs.find((r) => r.key === selRun()) ?? rs.find(isLive) ?? rs[0]
    })

    let busy = false
    const refreshLive = async () => {
      if (busy) return
      busy = true
      try {
        const rawActive: any = await context.client.session.active()
        const active: Record<string, any> = rawActive?.data ?? rawActive ?? {}
        setServer(true)
        setActiveIds(new Set(Object.keys(active)))

        const watchDir = root() ?? ocm()?.root ?? activeDir()
        if (watchDir) {
          const slist = listOf(
            await context.client.session.list({ directory: watchDir, limit: 30 }).catch(() => undefined),
          )
          setRemoteSessions(slist)
        }

        const run = current()
        if (!run) return

        if (run.kind === "run") {
          const res = await pollRunTasks(context.client, run, active, doneTokens())
          setLive(res.live)
          if (Object.keys(res.newDone).length) setDoneTokens((d) => ({ ...d, ...res.newDone }))
        } else {
          const res = await pollOrchSession(context.client, run, active, diskRuns())
          if (res) {
            setOrchLive((prev) => ({ ...prev, [res.sid]: res.live }))
            if (res.reply !== undefined) setReplies((prev) => ({ ...prev, [res.sid]: res.reply! }))
          }
        }
      } catch {
        setServer(false)
      } finally {
        busy = false
      }
    }

    const fetchSessionReply = async (sid?: string, running = false) => {
      if (!sid || (replies()[sid] !== undefined && !running)) return
      const msgs = await context.client.message
        .list({ sessionID: sid, limit: 30, order: "desc" })
        .then(listOf)
        .catch(() => undefined)
      if (msgs) setReplies((r) => ({ ...r, [sid]: lastText(msgs).slice(0, 8000) }))
    }

    const fetchReply = (t?: Task) => fetchSessionReply(t?.session, t?.status === "running")

    const rows = createMemo(() => {
      const run = current()
      if (!run) return []
      const lv = live()
      const dt = doneTokens()
      return run.tasks
        .map((t) => {
          const l = t.status === "running" ? lv[t.id] : undefined
          return {
            ...t,
            live: l,
            cost: round4((t.cost || 0) + (l?.cost || 0)),
            tokens: l ? sumTokens([t.tokens, l.tokens]) : t.tokens || (t.session ? dt[t.session] : undefined),
          }
        })
        .sort((a, b) => ORDER.indexOf(a.status) - ORDER.indexOf(b.status))
    })

    const selIndex = createMemo(() => Math.max(0, rows().findIndex((t) => t.id === selId())))
    const selected = createMemo(() => rows()[selIndex()])

    const tick = setInterval(() => {
      refreshFiles()
      if (opened()) void refreshLive()
    }, 2000)
    const sec = setInterval(() => opened() && setClock(now()), 1000)
    refreshFiles()

    createEffect(on(selected, (t) => opened() && void fetchReply(t)))
    createEffect(
      on(current, (r) => {
        if (opened() && r && r.kind !== "run") {
          void fetchSessionReply(
            r.cfg?.orchestrator,
            r.stream?.status === "running" || activeIds().has(r.cfg?.orchestrator),
          )
        }
      }),
    )

    const route = () => context.ui.router.current()
    const close = () => {
      const r = route()
      if (r.type !== "plugin" || r.name !== ROUTE) return
      context.ui.router.navigate((r.data?.returnRoute as any) ?? { type: "home" })
    }
    const toggle = () => {
      const r = route()
      if (r.type === "plugin" && r.name === ROUTE) return close()
      refreshFiles()
      if (r.type === "session") trackSession(r.sessionID)
      context.ui.dialog.clear()
      const returnRoute =
        r.type === "session"
          ? { type: "session", sessionID: r.sessionID }
          : r.type === "plugin"
            ? { type: "plugin", id: r.id, name: r.name, ...(r.data ? { data: { ...r.data } } : {}) }
            : { type: "home" }
      context.ui.router.navigate({
        type: "plugin",
        name: ROUTE,
        data: { returnRoute, sessionID: r.type === "session" ? r.sessionID : undefined },
      })
    }

    const managerDir = () => ocm()?.root ?? root() ?? activeDir()

    const hasManager = createMemo(() => {
      if (ocm()) return true
      const d = managerDir()
      if (d && mgrByDir()[d]) return true
      try {
        return context.data.session
          .list()
          .some((s: any) => s?.location?.directory === d && s?.agent === "manager" && !s?.time?.archived)
      } catch {
        return false
      }
    })

    const resolveOrchestrator = () =>
      findOrchestratorId({
        context,
        cur: current(),
        ocm: ocm(),
        orchSession: orchSession(),
        runs: runs(),
        dir: root() ?? ocm()?.root ?? activeDir(),
        isOcmMgr,
        isWorkerSession,
        onFound: setOrchSession,
      })

    const resolveManager = () =>
      findManagerId({
        context,
        cur: current(),
        ocm: ocm(),
        dir: managerDir(),
        mgrByDir: mgrByDir(),
        onFound: (d, sid) => setMgrByDir((prev) => ({ ...prev, [d]: sid })),
      })

    function Page() {
      const dims = useTerminalDimensions()
      const [offset, setOffset] = createSignal(0)
      let detail: ScrollBoxRenderable | undefined

      setOpened(true)
      setClock(now())
      void refreshLive()
      void fetchReply(selected())
      const initCur = current()
      if (initCur && initCur.kind !== "run") {
        void fetchSessionReply(
          initCur.cfg?.orchestrator,
          initCur.stream?.status === "running" || activeIds().has(initCur.cfg?.orchestrator),
        )
      }
      onCleanup(() => setOpened(false))

      const wide = () => dims().width >= 110
      const split = () => wide() && pane() && !zoom()
      const listWidth = () => (split() ? Math.floor(dims().width * 0.55) : dims().width)
      const perPage = () => Math.max(1, Math.floor((dims().height - HEAD) / ROW))
      const win = createMemo(() => {
        const n = perPage()
        const i = selIndex()
        let off = Math.min(offset(), Math.max(0, rows().length - n))
        if (i < off) off = i
        if (i >= off + n) off = i - n + 1
        return off
      })
      createEffect(() => setOffset(win()))
      createEffect(on(selected, () => detail?.scrollTo(0)))
      createEffect(on(current, () => detail?.scrollTo(0)))

      const pageRows = createMemo(() => rows().slice(win(), win() + perPage()))
      const strip = createMemo(() => {
        const list = runs()
        if (!list.length) return { start: 0, items: [] as Run[], more: 0 }
        const act = activeIds()
        const sel = Math.max(0, list.findIndex((r) => r.key === current()?.key))
        const avail = Math.max(20, dims().width - 4)
        const w = (r: Run) => runLabel(r, act).length + 3
        const overhead = (start: number, end: number) =>
          (start > 0 ? `‹ ${start}   `.length : 0) + (end < list.length ? `${list.length - end} ›`.length : 0)
        let start = sel
        let end = sel + 1
        let used = w(list[sel])
        while (start > 0) {
          const nextUsed = used + w(list[start - 1])
          if (nextUsed + overhead(start - 1, end) > avail) break
          start--
          used = nextUsed
        }
        while (end < list.length) {
          const nextUsed = used + w(list[end])
          if (nextUsed + overhead(start, end + 1) > avail) break
          used = nextUsed
          end++
        }
        return { start, items: list.slice(start, end), more: list.length - end }
      })

      const select = (i: number) => {
        if (current()?.kind !== "run") {
          detail?.scrollTo(i === 0 ? 0 : 999999)
          return
        }
        const list = rows()
        if (!list.length) return
        setSelId(list[Math.max(0, Math.min(list.length - 1, i))].id)
      }
      const move = (d: number) => {
        if (current()?.kind !== "run") {
          detail?.scrollBy(d * 3)
          return
        }
        select(selIndex() + d)
      }
      const pickRun = (d: number) => {
        const list = runs()
        if (!list.length) return
        const i = list.findIndex((r) => r.key === current()?.key)
        const next = list[Math.max(0, Math.min(list.length - 1, i + d))]
        if (next.key === current()?.key) return
        setSelRun(next.key)
        setSelId(undefined)
        setLive({})
        void refreshLive()
      }
      const openOrchestratorSession = async () => {
        const sid = await resolveOrchestrator()
        if (!sid) return context.ui.toast.show({ message: "No orchestrator session found", variant: "warning" })
        context.ui.router.navigate({ type: "session", sessionID: sid })
      }
      const openManagerSession = async () => {
        const sid = await resolveManager()
        if (!sid) return context.ui.toast.show({ message: "No manager session found", variant: "warning" })
        context.ui.router.navigate({ type: "session", sessionID: sid })
      }
      const openSession = () => {
        if (current()?.kind !== "run") return void openOrchestratorSession()
        const t = selected()
        if (!t?.session) return context.ui.toast.show({ message: "No session for this task", variant: "warning" })
        context.ui.router.navigate({ type: "session", sessionID: t.session })
      }
      const half = () => Math.max(1, Math.floor(perPage() / 2))

      context.keymap.layer(() => ({
        priority: 10,
        commands: [
          { bind: "j,down", title: "Next task", group: "ocq", run: () => move(1) },
          { bind: "k,up", title: "Previous task", group: "ocq", run: () => move(-1) },
          { bind: "gg,home", title: "First task", group: "ocq", run: () => select(0) },
          { bind: "shift+g,end", title: "Last task", group: "ocq", run: () => select(rows().length - 1) },
          { bind: "ctrl+d,pagedown", title: "Half page down", group: "ocq", run: () => move(half()) },
          { bind: "ctrl+u,pageup", title: "Half page up", group: "ocq", run: () => move(-half()) },
          { bind: "l,right", title: "Next run", group: "ocq", run: () => pickRun(1) },
          { bind: "h,left", title: "Previous run", group: "ocq", run: () => pickRun(-1) },
          { bind: "shift+j", title: "Scroll detail down", group: "ocq", run: () => detail?.scrollBy(3) },
          { bind: "shift+k", title: "Scroll detail up", group: "ocq", run: () => detail?.scrollBy(-3) },
          { bind: "return,o", title: "Open worker/orchestrator session", group: "ocq", run: openSession },
          { bind: "shift+o,O", title: "Open orchestrator session", group: "ocq", run: openOrchestratorSession },
          { bind: "m,shift+m,M", title: "Open manager session", group: "ocq", run: openManagerSession },
          { bind: "space", title: "Zoom detail", group: "ocq", run: () => setZoom((z) => !z) },
          { bind: "p", title: "Toggle detail pane", group: "ocq", run: () => setPane((v) => !v) },
          { bind: "b", title: "Toggle brief", group: "ocq", run: () => setBrief((v) => !v) },
          {
            bind: "r",
            title: "Refresh",
            group: "ocq",
            run: () => {
              refreshFiles()
              void refreshLive()
              setReplies({})
              const cur = current()
              if (cur && cur.kind !== "run") void fetchSessionReply(cur.cfg?.orchestrator, true)
              else void fetchReply(selected())
            },
          },
          { bind: "q,escape", title: "Close ocq", group: "ocq", run: close },
          { id: "app.exit", title: "Close ocq", group: "ocq", run: close },
        ],
      }))

      const muted = () => context.theme.text.muted
      const base = () => context.theme.text.base
      const headerRoot = () => root() ?? ocm()?.root ?? current()?.projectDir

      return (
        <box
          width="100%"
          height="100%"
          flexDirection="column"
          backgroundColor={context.theme.background.base}
          paddingLeft={2}
          paddingRight={2}
          paddingTop={1}
        >
          <box flexDirection="row" height={1} flexShrink={0}>
            <text wrapMode="none" flexGrow={1} minWidth={0} truncate>
              <span style={{ fg: base(), attributes: TextAttributes.BOLD }}>ocq</span>
              <span style={{ fg: muted() }}>
                {"   " + (headerRoot() ? context.ui.format.path(headerRoot()!) : "no .ocq / .ocm here")}
              </span>
            </text>
            <text wrapMode="none" flexShrink={0}>
              <span style={{ fg: statusColor(context.theme, server() ? "done" : "failed") }}>●</span>
              <span style={{ fg: muted() }}>{server() ? " server" : " server offline"}</span>
            </text>
          </box>
          <box height={1} flexShrink={0} />
          <text wrapMode="none" truncate height={1} flexShrink={0}>
            <span style={{ fg: muted() }}>{strip().start ? `‹ ${strip().start}   ` : ""}</span>
            <For each={strip().items}>
              {(r) => {
                const sel = () => r.key === current()?.key
                return (
                  <>
                    <span
                      style={{
                        fg: sel() ? base() : muted(),
                        bg: sel() ? context.theme.background.raised.high : undefined,
                        attributes: sel() ? TextAttributes.BOLD : 0,
                      }}
                    >
                      {runLabel(r, activeIds())}
                    </span>
                    <span>{"   "}</span>
                  </>
                )
              }}
            </For>
            <span style={{ fg: muted() }}>{strip().more ? `${strip().more} ›` : ""}</span>
          </text>
          <box height={1} flexShrink={0} />
          <Show
            when={current()}
            fallback={
              <box paddingTop={1}>
                <text fg={muted()}>No ocq runs or active orchestrators in this project.</text>
              </box>
            }
          >
            {(run) => (
              <Show
                when={run().kind === "run"}
                fallback={
                  <OrchView
                    run={run()}
                    live={run().cfg?.orchestrator ? orchLive()[run().cfg.orchestrator] : undefined}
                    reply={run().cfg?.orchestrator ? replies()[run().cfg.orchestrator] : undefined}
                    activeIds={activeIds()}
                    width={dims().width}
                    clock={clock()}
                    theme={context.theme}
                    formatPath={(p) => context.ui.format.path(p)}
                    detailRef={(s) => (detail = s)}
                  />
                }
              >
                <RunView
                  run={run()}
                  rows={rows()}
                  pageRows={pageRows()}
                  selected={selected()}
                  replies={replies()}
                  brief={brief()}
                  zoom={zoom()}
                  split={split()}
                  listWidth={listWidth()}
                  width={dims().width}
                  clock={clock()}
                  theme={context.theme}
                  formatPath={(p) => context.ui.format.path(p)}
                  onSelect={setSelId}
                  detailRef={(s) => (detail = s)}
                />
              </Show>
            )}
          </Show>
          <box flexGrow={1} />
          <box height={1} flexShrink={0} />
          <text wrapMode="none" truncate height={1} flexShrink={0} fg={muted()}>
            {`j/k ${current()?.kind === "run" ? "task" : "scroll"}    gg/G ends    ^d/^u page    h/l run    ${current()?.kind === "run" ? "⏎ worker    O orch" : "⏎/O orch"}    ${hasManager() ? "M mgr    " : ""}space zoom    p pane    J/K scroll    b brief    r refresh    q close`}
          </text>
        </box>
      )
    }

    const liveRuns = createMemo(() => runs().filter(isLive))
    context.ui.router.register({ name: ROUTE, render: () => <Page /> })
    context.ui.slot({
      append: "prompt.footer.status",
      render: () => <FooterView liveRuns={liveRuns()} activeIds={activeIds()} theme={context.theme} onToggle={toggle} />,
    })
    context.ui.slot({
      append: "app",
      render() {
        context.keymap.layer(() => ({
          mode: "global",
          commands: [
            {
              id: "ocq.toggle",
              title: "Toggle ocq dashboard",
              group: "ocq",
              bind: "<leader>o",
              palette: true,
              slash: { name: "ocq" },
              run: toggle,
            },
          ],
        }))
        return null
      },
    })

    return () => {
      clearInterval(tick)
      clearInterval(sec)
    }
  },
})
