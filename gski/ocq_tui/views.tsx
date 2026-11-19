import { TextAttributes, type RGBA, type ScrollBoxRenderable } from "@opentui/core"
import { createMemo, For, Show } from "solid-js"
import { dur, flat, fmtDateTime, kn, money, shortTier, sumTokens, taskSummary, taskTime } from "./format"
import { BAR, ROW, type Act, type Live, type Run, type Tokens } from "./types"

export function statusColor(theme: any, s: string): RGBA {
  if (s === "running") return theme.text.feedback.info.base
  if (s === "reported") return theme.text.feedback.warning.base
  if (s === "done") return theme.text.feedback.success.base
  if (s === "failed") return theme.text.feedback.error.base
  return theme.text.muted
}

export function Bar(props: { counts: Record<string, number>; total: number; width: number; theme: any }) {
  const segs = () => {
    const w = Math.max(1, props.width)
    if (!props.total) return [{ s: "pending", n: w, ch: "░" }]
    let acc = 0
    let used = 0
    return BAR.map((s) => {
      acc += props.counts[s] || 0
      const end = Math.round((acc / props.total) * w)
      const n = end - used
      used = end
      return { s, n, ch: s === "pending" ? "░" : "█" }
    }).filter((x) => x.n > 0)
  }
  return (
    <text wrapMode="none">
      <For each={segs()}>{(x) => <span style={{ fg: statusColor(props.theme, x.s) }}>{x.ch.repeat(x.n)}</span>}</For>
    </text>
  )
}

export function TaskRow(props: { t: any; sel: boolean; clock: number; theme: any; onSelect: (id: string) => void }) {
  const t = () => props.t
  const dot = () => {
    const s = t().live?.state
    if (!s) return ""
    return s === "idle" ? " ○" : s === "waiting" ? " ◐" : " ●"
  }
  const meta = () =>
    [
      shortTier(t()),
      t().attempts > 1 ? `a${t().attempts}` : "",
      t().denied?.length ? `denied ${t().denied.length}` : "",
      t().cost ? money(t().cost) : "",
      taskTime(t(), props.clock),
    ]
      .filter(Boolean)
      .join("  ")
  return (
    <box
      height={ROW}
      flexShrink={0}
      flexDirection="row"
      backgroundColor={props.sel ? props.theme.background.raised.high : undefined}
      onMouseUp={() => props.onSelect(t().id)}
    >
      <box width={1} flexShrink={0} backgroundColor={props.sel ? statusColor(props.theme, t().status) : undefined} />
      <box flexDirection="column" flexGrow={1} minWidth={0} paddingLeft={2} paddingRight={2} paddingTop={1}>
        <box flexDirection="row" height={1}>
          <text wrapMode="none" flexGrow={1} minWidth={0} truncate>
            <span style={{ fg: props.theme.text.base, attributes: TextAttributes.BOLD }}>{t().id}</span>{" "}
            <span style={{ fg: statusColor(props.theme, t().status) }}>
              {t().status}
              {dot()}
            </span>
          </text>
          <text wrapMode="none" fg={props.theme.text.muted} flexShrink={0}>
            {meta()}
          </text>
        </box>
        <text
          wrapMode="none"
          truncate
          fg={t().status === "done" ? props.theme.text.muted : props.theme.text.base}
        >
          {flat(taskSummary(t()))}
        </text>
      </box>
    </box>
  )
}

export function Detail(props: {
  t: any
  reply?: string
  clock: number
  theme: any
  ref: (s: ScrollBoxRenderable) => void
}) {
  const t = () => props.t
  const tk = () => t().tokens as Tokens | undefined
  const sections = () => {
    const x = t()
    return [
      ["Report", x.status === "reported" && x.worker ? `${x.worker}: ${x.note || ""}` : x.note],
      ["Artifact", x.artifact],
      ["Model", [x.agent, x.model].filter(Boolean).join(" · ")],
      ["Message", x.msg],
      [
        "Activity",
        x.live?.activity
          ?.map((a: Act) => (a.status === "error" ? "✗ " : a.status === "running" ? "▸ " : "✓ ") + flat(a.text))
          .join("\n"),
      ],
      ["Task", x.task],
      ["Feedback", x.feedback],
      ["Denied", (x.denied || []).join("\n")],
      [
        "Tokens",
        tk()
          ? `in ${kn(tk()!.input)} · out ${kn(tk()!.output)} · reasoning ${kn(tk()!.reasoning)} · cache r ${kn(tk()!.cache_read)} w ${kn(tk()!.cache_write)}`
          : "",
      ],
      ["Last reply", props.reply === undefined && x.session ? "loading…" : props.reply],
      ["Session", x.session],
    ].filter(([, v]) => v)
  }
  const tm = () => taskTime(t(), props.clock)
  return (
    <scrollbox ref={props.ref} flexGrow={1} scrollbarOptions={{ visible: false }}>
      <box flexDirection="column" paddingLeft={2} paddingRight={1} paddingTop={1} gap={1}>
        <text>
          <span style={{ fg: props.theme.text.base, attributes: TextAttributes.BOLD }}>{t().id}</span>{" "}
          <span style={{ fg: statusColor(props.theme, t().status) }}>{t().status}</span>
          <span style={{ fg: props.theme.text.muted }}>
            {"  "}attempt {t().attempts || 0}
            {t().cost ? "  " + money(t().cost) : ""}
            {tm() ? "  " + tm() : ""}
          </span>
        </text>
        <For each={sections()}>
          {([k, v]) => (
            <box flexDirection="column">
              <text fg={props.theme.text.muted}>{k}</text>
              <text fg={props.theme.text.base} wrapMode="word">
                {String(v)}
              </text>
            </box>
          )}
        </For>
      </box>
    </scrollbox>
  )
}

export function OrchDetail(props: {
  run: Run
  live?: Live
  reply?: string
  theme: any
  ref: (s: ScrollBoxRenderable) => void
}) {
  const r = () => props.run
  const st = () => r().stream
  const sid = () => r().cfg?.orchestrator as string | undefined
  const tk = () => (props.live?.tokens ?? st()?.tokens) as Tokens | undefined
  const sections = () => {
    const s = st()
    const id = sid()
    return [
      [
        "Activity",
        props.live?.activity
          ?.map((a: Act) => (a.status === "error" ? "✗ " : a.status === "running" ? "▸ " : "✓ ") + flat(a.text))
          .join("\n"),
      ],
      ["Report", s?.note],
      ["Message", s?.msg],
      ["Task", s?.task],
      ["Directory", r().projectDir],
      ["Model", r().cfg?.model],
      ["Allow", s?.allow?.length ? s.allow.join(", ") : ""],
      ["Denied", (s?.denied || []).join("\n")],
      [
        "Tokens",
        tk()
          ? `in ${kn(tk()!.input)} · out ${kn(tk()!.output)} · reasoning ${kn(tk()!.reasoning)} · cache r ${kn(tk()!.cache_read)} w ${kn(tk()!.cache_write)}`
          : "",
      ],
      ["Last reply", props.reply === undefined && id ? "loading…" : props.reply],
      ["Session", id],
    ].filter(([, v]) => v)
  }
  return (
    <scrollbox ref={props.ref} flexGrow={1} scrollbarOptions={{ visible: false }}>
      <box flexDirection="column" paddingLeft={1} paddingRight={1} gap={1}>
        <text fg={props.theme.text.muted}>
          No workers spawned yet — press Enter or O to open orchestrator session.
        </text>
        <For each={sections()}>
          {([k, v]) => (
            <box flexDirection="column">
              <text fg={props.theme.text.muted}>{k}</text>
              <text fg={props.theme.text.base} wrapMode="word">
                {String(v)}
              </text>
            </box>
          )}
        </For>
      </box>
    </scrollbox>
  )
}

function stat(theme: any, n: any, label: string, color?: RGBA) {
  return (
    <>
      <span style={{ fg: color ?? theme.text.base, attributes: TextAttributes.BOLD }}>{String(n)}</span>
      <span style={{ fg: theme.text.muted }}>{` ${label}     `}</span>
    </>
  )
}

export function RunView(props: {
  run: Run
  rows: any[]
  pageRows: any[]
  selected: any
  replies: Record<string, string>
  brief: boolean
  zoom: boolean
  split: boolean
  listWidth: number
  width: number
  clock: number
  theme: any
  formatPath: (p: string) => string
  onSelect: (id: string) => void
  detailRef: (s: ScrollBoxRenderable) => void
}) {
  const tk = createMemo(() => sumTokens(props.rows.map((t) => t.tokens)))
  const cost = createMemo(() => props.rows.reduce((a, t) => a + (t.cost || 0), 0))
  const c = () => props.run.counts
  return (
    <>
      <text wrapMode="none" truncate height={1} flexShrink={0}>
        <span style={{ fg: props.theme.text.base, attributes: TextAttributes.BOLD }}>{props.run.name}</span>
        <span style={{ fg: props.theme.text.muted }}>
          {props.run.projectDir ? "  " + props.formatPath(props.run.projectDir) : ""}
          {props.run.last ? " · " + fmtDateTime(props.run.last) : ""}
          {props.run.stream ? ` · ocm/${props.run.stream.id} (${props.run.stream.status || "?"})` : ""}
          {props.run.cfg.agent ? " · " + props.run.cfg.agent : ""}
          {props.run.cfg.model ? " · " + props.run.cfg.model : ""}
          {props.run.cfg.concurrency ? ` · concurrency ${props.run.cfg.concurrency}` : ""}
        </span>
      </text>
      <text wrapMode="none" truncate height={1} flexShrink={0}>
        {stat(props.theme, `${c().done || 0}/${props.run.total}`, "done")}
        {stat(props.theme, c().running || 0, "running", c().running ? statusColor(props.theme, "running") : undefined)}
        {c().reported ? stat(props.theme, c().reported, "review", statusColor(props.theme, "reported")) : null}
        {stat(props.theme, c().failed || 0, "failed", c().failed ? statusColor(props.theme, "failed") : undefined)}
        {c().pending ? stat(props.theme, c().pending, "pending") : null}
        {stat(props.theme, money(cost()), "")}
        {stat(props.theme, kn(tk().input + tk().cache_read), "in")}
        {stat(props.theme, kn(tk().output + tk().reasoning), "out")}
      </text>
      <box height={1} flexShrink={0} />
      <box height={1} flexShrink={0}>
        <Bar counts={c()} total={props.run.total} width={props.width - 4} theme={props.theme} />
      </box>
      <box height={1} flexShrink={0} />
      <Show
        when={!props.brief}
        fallback={
          <scrollbox ref={props.detailRef} flexGrow={1}>
            <box paddingLeft={1} paddingRight={1}>
              <text fg={props.theme.text.base} wrapMode="word">
                {props.run.brief || "No brief."}
              </text>
            </box>
          </scrollbox>
        }
      >
        <Show
          when={!props.zoom}
          fallback={
            <Show when={props.selected} fallback={<text fg={props.theme.text.muted}> No task.</text>}>
              {(t) => (
                <Detail
                  t={t()}
                  reply={t().session ? props.replies[t().session] : undefined}
                  clock={props.clock}
                  theme={props.theme}
                  ref={props.detailRef}
                />
              )}
            </Show>
          }
        >
          <box flexDirection="row" flexGrow={1} minHeight={0}>
            <box flexDirection="column" width={props.listWidth} flexShrink={0}>
              <Show when={props.rows.length} fallback={<text fg={props.theme.text.muted}> No tasks.</text>}>
                <For each={props.pageRows}>
                  {(t) => (
                    <TaskRow
                      t={t}
                      sel={t.id === props.selected?.id}
                      clock={props.clock}
                      theme={props.theme}
                      onSelect={props.onSelect}
                    />
                  )}
                </For>
              </Show>
            </box>
            <Show when={props.split}>
              <box
                flexGrow={1}
                minWidth={0}
                border={["left"]}
                borderColor={props.theme.border.base}
                flexDirection="column"
              >
                <Show when={props.selected}>
                  {(t) => (
                    <Detail
                      t={t()}
                      reply={t().session ? props.replies[t().session] : undefined}
                      clock={props.clock}
                      theme={props.theme}
                      ref={props.detailRef}
                    />
                  )}
                </Show>
              </box>
            </Show>
          </box>
        </Show>
      </Show>
    </>
  )
}

export function FooterView(props: {
  liveRuns: Run[]
  activeIds: Set<string>
  theme: any
  onToggle: () => void
}) {
  return (
    <Show when={props.liveRuns[0]}>
      {(r) => (
        <box flexShrink={0} onMouseUp={props.onToggle}>
          <text fg={props.theme.text.muted} wrapMode="none">
            <span style={{ fg: props.theme.text.base }}>
              {r().kind === "run" ? "ocq " : r().kind === "ocm" ? "ocm " : "orch "}
            </span>
            {r().name}{" "}
            <Show
              when={r().kind === "run"}
              fallback={
                <>
                  <Show
                    when={
                      r().stream?.status === "running" ||
                      (r().kind === "orch" && props.activeIds.has(r().cfg?.orchestrator))
                    }
                  >
                    <span style={{ fg: statusColor(props.theme, "running") }}>▸ </span>
                  </Show>
                  <Show when={r().stream?.status === "reported"}>
                    <span style={{ fg: statusColor(props.theme, "reported") }}>? </span>
                  </Show>
                  {r().cost ? money(r().cost) : ""}
                </>
              }
            >
              <Show when={r().counts.running || r().stream?.status === "running"}>
                <span style={{ fg: statusColor(props.theme, "running") }}>{r().counts.running || ""}▸ </span>
              </Show>
              <Show when={r().counts.reported}>
                <span style={{ fg: statusColor(props.theme, "reported") }}>{r().counts.reported}? </span>
              </Show>
              <Show when={r().counts.failed}>
                <span style={{ fg: statusColor(props.theme, "failed") }}>{r().counts.failed}✗ </span>
              </Show>
              {r().counts.done || 0}/{r().total} {money(r().cost)}
            </Show>
            {props.liveRuns.length > 1 ? ` +${props.liveRuns.length - 1}` : ""}
          </text>
        </box>
      )}
    </Show>
  )
}

export function OrchView(props: {
  run: Run
  live?: Live
  reply?: string
  activeIds: Set<string>
  width: number
  clock: number
  theme: any
  formatPath: (p: string) => string
  detailRef: (s: ScrollBoxRenderable) => void
}) {
  const sid = () => props.run.cfg?.orchestrator as string | undefined
  const st = () => props.run.stream
  const status = () =>
    st()?.status ||
    (props.live?.state && props.live.state !== "idle"
      ? "running"
      : props.activeIds.has(sid() || "")
        ? "running"
        : "idle")
  const dot = () => {
    const s = props.live?.state
    if (!s) return ""
    return s === "idle" ? " ○" : s === "waiting" ? " ◐" : " ●"
  }
  const cost = () => Math.max(props.run.cost, props.live?.cost || 0)
  const tk = () => (props.live?.tokens ?? st()?.tokens) as Tokens | undefined
  const elapsed = () => {
    const s = st()
    if (!s?.started) return ""
    if (s.status === "running") return dur(props.clock - s.started)
    if (s.finished && s.finished >= s.started) return dur(s.finished - s.started)
    return ""
  }
  return (
    <>
      <text wrapMode="none" truncate height={1} flexShrink={0}>
        <span style={{ fg: props.theme.text.base, attributes: TextAttributes.BOLD }}>
          {props.run.kind === "ocm" ? `ocm/${props.run.name}` : props.run.name}
        </span>{" "}
        <span style={{ fg: statusColor(props.theme, status()) }}>
          {status()}
          {dot()}
        </span>
        <span style={{ fg: props.theme.text.muted }}>
          {props.run.projectDir ? "  " + props.formatPath(props.run.projectDir) : ""}
          {props.run.last ? " · " + fmtDateTime(props.run.last) : ""}
          {props.run.cfg.model ? " · " + props.run.cfg.model : ""}
        </span>
      </text>
      <text wrapMode="none" truncate height={1} flexShrink={0}>
        {stat(props.theme, "0", "workers")}
        {stat(props.theme, money(cost()), "")}
        {tk() ? stat(props.theme, kn(tk()!.input + tk()!.cache_read), "in") : null}
        {tk() ? stat(props.theme, kn(tk()!.output + tk()!.reasoning), "out") : null}
        {elapsed() ? stat(props.theme, elapsed(), "") : null}
      </text>
      <box height={1} flexShrink={0} />
      <box height={1} flexShrink={0}>
        <Bar counts={{}} total={0} width={props.width - 4} theme={props.theme} />
      </box>
      <box height={1} flexShrink={0} />
      <OrchDetail run={props.run} live={props.live} reply={props.reply} theme={props.theme} ref={props.detailRef} />
    </>
  )
}
