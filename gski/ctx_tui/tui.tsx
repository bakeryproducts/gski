import { spawn } from "node:child_process"
import { existsSync, mkdirSync, readFileSync, unlinkSync, writeFileSync } from "node:fs"
import { homedir } from "node:os"
import { basename, join } from "node:path"
import { Database } from "bun:sqlite"
import { Plugin } from "@opencode/plugin/tui"
import { TextAttributes, type RGBA, type ScrollBoxRenderable } from "@opentui/core"
import { useTerminalDimensions } from "@opentui/solid"
import { createEffect, createMemo, createSignal, For, on, onCleanup, Show } from "solid-js"

const ROUTE = "ctx"
const HEAD = 10
const ROW = 3
const DB_PATH = join(homedir(), ".local", "share", "opencode", "opencode.db")
const TMP_DIR = "/tmp/opencode"

type SessionRow = {
  id: string
  title: string
  directory: string
  agent: string
  model: string
  time_updated: number
  msg_count: number
}

type ItemKind = "user" | "text" | "reasoning" | "tool" | "synthetic" | "compaction" | "system" | "other"

type Item = {
  key: string
  msgId: string
  seq: number
  msgType: string
  partIdx: number | null
  kind: ItemKind
  label: string
  chars: number
  preview: string
  detail: string
  editText: string
  editable: boolean
  active: boolean
  spam: boolean
  created: number
}

const flat = (s: any) => String(s ?? "").replace(/\s+/g, " ").trim()

function kn(n?: number) {
  n = n || 0
  if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e7 ? 0 : 1) + "M"
  if (n >= 1e3) return (n / 1e3).toFixed(n >= 1e4 ? 0 : 1) + "k"
  return String(n)
}

function tokStr(chars?: number) {
  const t = Math.round((chars || 0) / 4)
  if (t < 1000) return "<1k"
  return kn(t)
}

function ago(ms?: number) {
  if (!ms) return ""
  const s = Math.max(0, Math.floor((Date.now() - ms) / 1000))
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h`
  return `${Math.floor(h / 24)}d`
}

const SPAM_RE = /(\[\]\s*\([^)\n]{0,40}\)\]?){3,}/g

function hasSpam(s: string) {
  SPAM_RE.lastIndex = 0
  return SPAM_RE.test(s)
}

function cleanSpamText(s: string) {
  return s.replace(/(\s*\[\]\s*\([^)\n]{0,40}\)\]?){2,}/g, "").trimEnd()
}

function truncateLines(s: string, keep = 20) {
  const lines = s.split("\n")
  if (lines.length <= keep * 2 + 2) {
    if (s.length <= 2000) return s
    return `${s.slice(0, 800)}\n\n... [truncated ${s.length - 1600} chars] ...\n\n${s.slice(-800)}`
  }
  const omitted = lines.length - keep * 2
  return [...lines.slice(0, keep), `\n... [truncated ${omitted} lines] ...\n`, ...lines.slice(-keep)].join("\n")
}

function toolOutputText(st: any): string {
  if (!st) return ""
  if (Array.isArray(st.content)) {
    return st.content
      .map((c: any) => (c?.type === "text" ? String(c.text ?? "") : `[${c?.type ?? "part"}]`))
      .join("\n")
  }
  if (st.error) return typeof st.error === "string" ? st.error : JSON.stringify(st.error, null, 2)
  return ""
}

function toolSummaryInput(inp: any): string {
  if (!inp || typeof inp !== "object") return ""
  return String(
    inp.command || inp.path || inp.filePath || inp.pattern || inp.url || inp.query || inp.description || JSON.stringify(inp),
  )
}

function openDb(readonly = true) {
  if (!existsSync(DB_PATH)) return undefined
  return new Database(DB_PATH, { readonly })
}

function listSessions(limit = 120): SessionRow[] {
  const db = openDb(true)
  if (!db) return []
  try {
    return db
      .query(
        `SELECT s.id, COALESCE(s.title, '') as title, s.directory, COALESCE(s.agent, '') as agent,
                COALESCE(s.model, '') as model, s.time_updated,
                (SELECT count(*) FROM session_message m WHERE m.session_id = s.id) as msg_count
         FROM session_v2 s
         ORDER BY s.time_updated DESC
         LIMIT ?`,
      )
      .all(limit) as SessionRow[]
  } catch {
    return []
  } finally {
    db.close()
  }
}

function loadSessionItems(sessionID: string): { info?: SessionRow; items: Item[]; compactionSeq: number } {
  const db = openDb(true)
  if (!db) return { items: [], compactionSeq: 0 }
  try {
    const info = db
      .query(
        `SELECT s.id, COALESCE(s.title, '') as title, s.directory, COALESCE(s.agent, '') as agent,
                COALESCE(s.model, '') as model, s.time_updated,
                (SELECT count(*) FROM session_message m WHERE m.session_id = s.id) as msg_count
         FROM session_v2 s WHERE s.id = ?`,
      )
      .get(sessionID) as SessionRow | undefined

    const rows = db
      .query(`SELECT id, type, seq, time_created, data FROM session_message WHERE session_id = ? ORDER BY seq ASC`)
      .all(sessionID) as { id: string; type: string; seq: number; time_created: number; data: string }[]

    let compactionSeq = 0
    let keepID: string | undefined
    for (const r of rows) {
      if (r.type === "compaction") {
        try {
          const d = JSON.parse(r.data)
          if (d.status === "completed" || d.summary) {
            compactionSeq = r.seq
            keepID = d.metadata?.keepID
          }
        } catch {}
      }
    }
    let activeFromSeq = compactionSeq
    if (keepID) {
      const k = rows.find((r) => r.id === keepID)
      if (k && k.seq < activeFromSeq) activeFromSeq = k.seq
    }

    const items: Item[] = []
    for (const r of rows) {
      if (r.type === "idle" || r.type === "agent-switched" || r.type === "model-switched") continue
      let d: any
      try {
        d = JSON.parse(r.data)
      } catch {
        continue
      }
      const active = r.seq >= activeFromSeq
      const created = d?.time?.created || r.time_created

      if (r.type === "user" || r.type === "synthetic" || r.type === "system") {
        const txt = String(d.text ?? "")
        const files = Array.isArray(d.files) && d.files.length ? ` [+${d.files.length} files]` : ""
        const kind: ItemKind = r.type === "user" ? "user" : r.type === "synthetic" ? "synthetic" : "system"
        const src = r.type === "synthetic" && d.metadata?.source ? `:${d.metadata.source}` : ""
        items.push({
          key: `${r.id}:msg`,
          msgId: r.id,
          seq: r.seq,
          msgType: r.type,
          partIdx: null,
          kind,
          label: `${r.type}${src}${files}`,
          chars: txt.length,
          preview: flat(txt) || "(empty)",
          detail: txt,
          editText: txt,
          editable: true,
          active,
          spam: hasSpam(txt),
          created,
        })
      } else if (r.type === "compaction") {
        const txt = String(d.summary ?? "")
        items.push({
          key: `${r.id}:msg`,
          msgId: r.id,
          seq: r.seq,
          msgType: r.type,
          partIdx: null,
          kind: "compaction",
          label: `compaction (${d.status || "done"})`,
          chars: txt.length,
          preview: flat(txt) || "(empty summary)",
          detail: txt,
          editText: txt,
          editable: true,
          active: r.seq >= compactionSeq,
          spam: hasSpam(txt),
          created,
        })
      } else if (r.type === "assistant") {
        const content = Array.isArray(d.content) ? d.content : []
        if (!content.length) {
          const err = d.error ? JSON.stringify(d.error) : "(empty assistant turn)"
          items.push({
            key: `${r.id}:msg`,
            msgId: r.id,
            seq: r.seq,
            msgType: r.type,
            partIdx: null,
            kind: "other",
            label: "asst:empty",
            chars: err.length,
            preview: flat(err),
            detail: err,
            editText: "",
            editable: false,
            active,
            spam: false,
            created,
          })
          continue
        }
        content.forEach((p: any, idx: number) => {
          if (p?.type === "text" || p?.type === "reasoning") {
            const txt = String(p.text ?? "")
            const kind: ItemKind = p.type === "reasoning" ? "reasoning" : "text"
            items.push({
              key: `${r.id}:${idx}`,
              msgId: r.id,
              seq: r.seq,
              msgType: r.type,
              partIdx: idx,
              kind,
              label: p.type === "reasoning" ? "asst:think" : "asst:text",
              chars: txt.length,
              preview: flat(txt) || "(empty)",
              detail: txt,
              editText: txt,
              editable: true,
              active,
              spam: hasSpam(txt),
              created,
            })
          } else if (p?.type === "tool") {
            const st = p.state || {}
            const inpStr = JSON.stringify(st.input ?? {}, null, 2)
            const outStr = toolOutputText(st)
            const cmdPreview = toolSummaryInput(st.input)
            const totalChars = inpStr.length + outStr.length
            const statusTag = st.status && st.status !== "completed" ? ` (${st.status})` : ""
            items.push({
              key: `${r.id}:${idx}`,
              msgId: r.id,
              seq: r.seq,
              msgType: r.type,
              partIdx: idx,
              kind: "tool",
              label: `tool:${p.name || "?"}${statusTag}`,
              chars: totalChars,
              preview: `${flat(cmdPreview)} -> ${flat(outStr.slice(0, 200)) || "(no output)"}`,
              detail: `--- INPUT (${tokStr(inpStr.length)} tok) ---\n${inpStr}\n\n--- OUTPUT (${tokStr(outStr.length)} tok) ---\n${outStr}`,
              editText: outStr,
              editable: true,
              active,
              spam: hasSpam(outStr),
              created,
            })
          }
        })
      }
    }
    return { info, items, compactionSeq }
  } catch {
    return { items: [], compactionSeq: 0 }
  } finally {
    db.close()
  }
}

function recalcLastAssistantTokens(db: Database, sessionID: string) {
  const rows = db
    .query(`SELECT id, type, seq, data FROM session_message WHERE session_id = ? ORDER BY seq ASC`)
    .all(sessionID) as { id: string; type: string; seq: number; data: string }[]
  if (!rows.length) return
  let compSeq = 0
  let keepID: string | undefined
  for (const r of rows) {
    if (r.type === "compaction") {
      try {
        const d = JSON.parse(r.data)
        if (d.status === "completed" || d.summary) {
          compSeq = r.seq
          keepID = d.metadata?.keepID
        }
      } catch {}
    }
  }
  let fromSeq = compSeq
  if (keepID) {
    const k = rows.find((r) => r.id === keepID)
    if (k && k.seq < fromSeq) fromSeq = k.seq
  }
  let activeChars = 0
  let lastAsst: { id: string; data: any } | undefined
  for (const r of rows) {
    let d: any
    try {
      d = JSON.parse(r.data)
    } catch {
      continue
    }
    if (r.seq >= fromSeq) activeChars += r.data.length
    if (r.type === "assistant" && d.tokens) lastAsst = { id: r.id, data: d }
  }
  if (lastAsst) {
    const estInput = Math.max(256, Math.round(activeChars / 4))
    lastAsst.data.tokens = {
      input: estInput,
      output: lastAsst.data.tokens.output || 0,
      reasoning: lastAsst.data.tokens.reasoning || 0,
      cache: { read: 0, write: 0 },
    }
    db.query(`UPDATE session_message SET data = ? WHERE id = ?`).run(JSON.stringify(lastAsst.data), lastAsst.id)
  }
}

function mutateItem(item: Item, action: "edit" | "strip" | "truncate" | "clean" | "delete" | "delete_after", newText?: string): string {
  const db = openDb(false)
  if (!db) return "DB not found"
  try {
    const nowMs = Date.now()
    const info = db.query(`SELECT session_id FROM session_message WHERE id = ?`).get(item.msgId) as { session_id: string } | undefined
    if (!info) return "Message not found"
    const sid = info.session_id

    if (action === "delete_after") {
      const res = db.query(`DELETE FROM session_message WHERE session_id = ? AND seq > ?`).run(sid, item.seq)
      recalcLastAssistantTokens(db, sid)
      return `Deleted ${res.changes} messages after #${item.seq}`
    }
    if (action === "delete") {
      if (item.partIdx !== null) {
        const row = db.query(`SELECT data FROM session_message WHERE id = ?`).get(item.msgId) as { data: string } | undefined
        if (!row) return "Message not found"
        const d = JSON.parse(row.data)
        if (Array.isArray(d.content) && d.content.length > 1) {
          d.content.splice(item.partIdx, 1)
          db.query(`UPDATE session_message SET data = ?, time_updated = ? WHERE id = ?`).run(JSON.stringify(d), nowMs, item.msgId)
          recalcLastAssistantTokens(db, sid)
          return `Removed part [${item.partIdx}] from #${item.seq}`
        }
      }
      db.query(`DELETE FROM session_message WHERE id = ?`).run(item.msgId)
      recalcLastAssistantTokens(db, sid)
      return `Deleted message #${item.seq}`
    }

    const row = db.query(`SELECT data FROM session_message WHERE id = ?`).get(item.msgId) as { data: string } | undefined
    if (!row) return "Message not found"
    const d = JSON.parse(row.data)

    const computeText = (orig: string, fallbackStub: string) => {
      if (action === "edit") return newText ?? orig
      if (action === "strip") return fallbackStub
      if (action === "truncate") return truncateLines(orig, 20)
      if (action === "clean") return cleanSpamText(orig)
      return orig
    }

    if (item.partIdx === null) {
      if (item.msgType === "compaction") {
        d.summary = computeText(String(d.summary ?? ""), "[compaction summary cleared]")
      } else {
        d.text = computeText(String(d.text ?? ""), "[cleared]")
      }
    } else {
      const part = d.content?.[item.partIdx]
      if (!part) return "Part not found"
      if (part.type === "text" || part.type === "reasoning") {
        part.text = computeText(String(part.text ?? ""), "[cleared]")
      } else if (part.type === "tool") {
        const st = (part.state ??= {})
        const orig = toolOutputText(st)
        const updated = computeText(orig, "[tool output cleared by user]")
        if (st.status === "error" && st.error) {
          st.error = { type: "tool.execution", message: updated }
        } else {
          st.content = [{ type: "text", text: updated }]
        }
      }
    }

    db.query(`UPDATE session_message SET data = ?, time_updated = ? WHERE id = ?`).run(JSON.stringify(d), nowMs, item.msgId)
    recalcLastAssistantTokens(db, sid)
    return `${action} applied to #${item.seq}`
  } catch (e: any) {
    return `Error: ${e?.message || String(e)}`
  } finally {
    db.close()
  }
}

function spawnVim(initialText: string, tag: string): Promise<string | null> {
  return new Promise((resolve) => {
    try {
      mkdirSync(TMP_DIR, { recursive: true })
    } catch {}
    const safeTag = tag.replace(/[^a-zA-Z0-9_-]/g, "_")
    const file = join(TMP_DIR, `ctx-edit-${safeTag}-${Date.now()}.md`)
    writeFileSync(file, initialText, "utf8")
    const child = spawn("alacritty", ["--class", "oc-edit", "-t", `OC Edit | ${tag}`, "-e", "vim", file], {
      stdio: "ignore",
    })
    child.on("error", () => {
      try {
        unlinkSync(file)
      } catch {}
      resolve(null)
    })
    child.on("exit", () => {
      try {
        const updated = readFileSync(file, "utf8")
        unlinkSync(file)
        resolve(updated !== initialText ? updated : null)
      } catch {
        resolve(null)
      }
    })
  })
}

export default Plugin.define({
  id: "gski.ctx",
  setup(context) {
    const [sessionID, setSessionID] = createSignal<string>()
    const [sessionInfo, setSessionInfo] = createSignal<SessionRow>()
    const [items, setItems] = createSignal<Item[]>([])
    const [selKey, setSelKey] = createSignal<string>()
    const [sortBy, setSortBy] = createSignal<"seq" | "size">("seq")
    const [scope, setScope] = createSignal<"active" | "all">("active")
    const [pane, setPane] = createSignal(true)
    const [zoom, setZoom] = createSignal(false)

    const kindColor = (it: Item): RGBA => {
      const t = context.theme
      if (it.spam || it.chars >= 20000) return t.text.feedback.error.base
      if (it.chars >= 5000) return t.text.feedback.warning.base
      if (it.kind === "user") return t.text.feedback.success.base
      if (it.kind === "tool") return t.text.feedback.info.base
      if (it.kind === "compaction") return t.text.feedback.warning.base
      return t.text.base
    }

    const roleColor = (kind: ItemKind): RGBA => {
      const t = context.theme
      if (kind === "user") return t.text.feedback.success.base
      if (kind === "tool") return t.text.feedback.info.base
      if (kind === "compaction") return t.text.feedback.warning.base
      if (kind === "synthetic" || kind === "system" || kind === "reasoning") return t.text.muted
      return t.text.base
    }

    const syncHostSession = async (sid: string) => {
      try {
        context.data.session.message.invalidate(sid)
        await context.data.session.message.sync(sid)
        context.data.session.invalidate(sid)
        await context.data.session.sync(sid)
      } catch {}
    }

    const reload = (sid = sessionID()) => {
      if (!sid) {
        const list = listSessions(1)
        if (list[0]) {
          sid = list[0].id
          setSessionID(sid)
        }
      }
      if (!sid) return
      const res = loadSessionItems(sid)
      setSessionInfo(res.info)
      setItems(res.items)
    }

    const shown = createMemo(() => {
      const list = items().filter((it) => (scope() === "active" ? it.active : true))
      if (sortBy() === "size") {
        return [...list].sort((a, b) => b.chars - a.chars || b.seq - a.seq)
      }
      return list
    })

    const selIndex = createMemo(() => Math.max(0, shown().findIndex((it) => it.key === selKey())))
    const selected = createMemo(() => shown()[selIndex()])

    const activeStats = createMemo(() => {
      const all = items()
      const act = all.filter((i) => i.active)
      const actChars = act.reduce((acc, i) => acc + i.chars, 0)
      const allChars = all.reduce((acc, i) => acc + i.chars, 0)
      const spamCount = act.filter((i) => i.spam).length
      return {
        actCount: act.length,
        allCount: all.length,
        actChars,
        actTokens: Math.round(actChars / 4),
        allChars,
        spamCount,
      }
    })

    const route = () => context.ui.router.current()
    const close = () => {
      const r = route()
      if (r.type !== "plugin" || r.name !== ROUTE) return
      context.ui.router.navigate((r.data?.returnRoute as any) ?? { type: "home" })
    }

    const toggle = () => {
      const r = route()
      if (r.type === "plugin" && r.name === ROUTE) return close()
      const activeSid = r.type === "session" ? r.sessionID : (r as any).data?.sessionID
      if (activeSid) setSessionID(activeSid)
      reload(activeSid || sessionID())
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
        data: { returnRoute, sessionID: activeSid },
      })
    }

    const pickSession = async () => {
      const sessions = listSessions(150)
      if (!sessions.length) {
        context.ui.toast.show({ message: "No sessions found in DB", variant: "warning" })
        return
      }
      const chosen = await context.ui.dialog.select({
        title: "Select Session to Inspect / Edit",
        current: sessionID(),
        options: sessions.map((s) => ({
          title: `${s.title || "(untitled)"}  [${s.msg_count} msgs · ${ago(s.time_updated)}]`,
          value: s.id,
          description: `${basename(s.directory || "")} · ${s.agent || "default"} · ${s.id}`,
        })),
      })
      if (chosen) {
        setSessionID(chosen)
        setSelKey(undefined)
        reload(chosen)
      }
    }

    function ItemRow(props: { it: Item; sel: boolean }) {
      const it = () => props.it
      return (
        <box
          height={ROW}
          flexShrink={0}
          flexDirection="row"
          backgroundColor={props.sel ? context.theme.background.raised.high : undefined}
          onMouseUp={() => setSelKey(it().key)}
        >
          <box width={1} flexShrink={0} backgroundColor={props.sel ? kindColor(it()) : undefined} />
          <box flexDirection="column" flexGrow={1} minWidth={0} paddingLeft={2} paddingRight={2}>
            <box flexDirection="row" height={1}>
              <text wrapMode="none" flexGrow={1} minWidth={0} truncate>
                <span style={{ fg: context.theme.text.muted }}>{`#${it().seq}${it().partIdx !== null ? `.${it().partIdx}` : ""} `}</span>
                <span style={{ fg: roleColor(it().kind), attributes: TextAttributes.BOLD }}>{it().label}</span>
                <Show when={!it().active}>
                  <span style={{ fg: context.theme.text.muted }}>{" [archived]"}</span>
                </Show>
                <Show when={it().spam}>
                  <span style={{ fg: context.theme.text.feedback.error.base, attributes: TextAttributes.BOLD }}>
                    {" [SPAM LOOP]"}
                  </span>
                </Show>
              </text>
              <text wrapMode="none" fg={kindColor(it())} flexShrink={0}>
                {tokStr(it().chars)}
              </text>
            </box>
            <text wrapMode="none" truncate fg={it().chars < 30 ? context.theme.text.muted : context.theme.text.base}>
              {it().preview}
            </text>
          </box>
        </box>
      )
    }

    function Detail(props: { it: Item; ref: (s: ScrollBoxRenderable) => void }) {
      const it = () => props.it
      return (
        <scrollbox ref={props.ref} flexGrow={1} scrollbarOptions={{ visible: false }}>
          <box flexDirection="column" paddingLeft={2} paddingRight={1} paddingTop={1} gap={1}>
            <text>
              <span style={{ fg: context.theme.text.base, attributes: TextAttributes.BOLD }}>
                {`#${it().seq}${it().partIdx !== null ? `.${it().partIdx}` : ""} ${it().label}`}
              </span>
              <span style={{ fg: context.theme.text.muted }}>
                {`  ${tokStr(it().chars)} tok  ${ago(it().created)} ago  ${it().msgId}`}
              </span>
            </text>
            <text fg={context.theme.text.base} wrapMode="word">
              {it().detail}
            </text>
          </box>
        </scrollbox>
      )
    }

    function Page() {
      const dims = useTerminalDimensions()
      const [offset, setOffset] = createSignal(0)
      let detail: ScrollBoxRenderable | undefined

      reload()

      const wide = () => dims().width >= 110
      const split = () => wide() && pane() && !zoom()
      const listWidth = () => (split() ? Math.floor(dims().width * 0.52) : dims().width)
      const perPage = () => Math.max(1, Math.floor((dims().height - HEAD) / ROW))
      const win = createMemo(() => {
        const n = perPage()
        const i = selIndex()
        let off = Math.min(offset(), Math.max(0, shown().length - n))
        if (i < off) off = i
        if (i >= off + n) off = i - n + 1
        return off
      })
      createEffect(() => setOffset(win()))
      createEffect(on(selected, () => detail?.scrollTo(0)))

      const pageRows = createMemo(() => shown().slice(win(), win() + perPage()))
      const select = (i: number) => {
        const list = shown()
        if (!list.length) return
        setSelKey(list[Math.max(0, Math.min(list.length - 1, i))].key)
      }
      const move = (d: number) => select(selIndex() + d)
      const half = () => Math.max(1, Math.floor(perPage() / 2))

      const applyAction = async (action: "strip" | "truncate" | "clean" | "delete" | "delete_after") => {
        const it = selected()
        const sid = sessionID()
        if (!it || !sid) return
        if (action === "delete" || action === "delete_after") {
          const ok = await context.ui.dialog.confirm({
            title: action === "delete_after" ? "Truncate Session History?" : "Delete Message / Part?",
            message:
              action === "delete_after"
                ? `Delete all messages after #${it.seq} (${it.label})?`
                : `Permanently delete #${it.seq} (${it.label}, ${kn(it.chars)} chars)?`,
            label: { confirm: "Delete", cancel: "Cancel" },
          })
          if (!ok) return
        }
        const prevIdx = selIndex()
        const msg = mutateItem(it, action)
        reload(sid)
        select(prevIdx)
        await syncHostSession(sid)
        context.ui.toast.show({ message: msg, variant: "success", duration: 2500 })
      }

      const editInVim = async () => {
        const it = selected()
        const sid = sessionID()
        if (!it || !sid) return
        if (!it.editable) {
          context.ui.toast.show({ message: "This item has no editable text", variant: "warning" })
          return
        }
        const updated = await spawnVim(it.editText, `${it.seq}_${it.label}`)
        if (updated === null) return
        const msg = mutateItem(it, "edit", updated)
        reload(sid)
        await syncHostSession(sid)
        context.ui.toast.show({ message: msg, variant: "success", duration: 2500 })
      }

      const cleanAllSpam = async () => {
        const sid = sessionID()
        if (!sid) return
        const spamItems = items().filter((i) => i.spam)
        if (!spamItems.length) {
          context.ui.toast.show({ message: "No repetition spam detected in this session", variant: "info" })
          return
        }
        for (const it of spamItems) mutateItem(it, "clean")
        reload(sid)
        await syncHostSession(sid)
        context.ui.toast.show({
          message: `Cleaned repetition spam in ${spamItems.length} message(s)`,
          variant: "success",
        })
      }

      const openTargetSession = () => {
        const sid = sessionID()
        if (!sid) return
        context.ui.router.navigate({ type: "session", sessionID: sid })
      }

      context.keymap.layer(() => ({
        priority: 10,
        commands: [
          { bind: "j,down", title: "Next item", group: "ctx", run: () => move(1) },
          { bind: "k,up", title: "Previous item", group: "ctx", run: () => move(-1) },
          { bind: "gg,home", title: "First item", group: "ctx", run: () => select(0) },
          { bind: "shift+g,end", title: "Last item", group: "ctx", run: () => select(shown().length - 1) },
          { bind: "ctrl+d,pagedown", title: "Half page down", group: "ctx", run: () => move(half()) },
          { bind: "ctrl+u,pageup", title: "Half page up", group: "ctx", run: () => move(-half()) },
          { bind: "shift+j", title: "Scroll detail down", group: "ctx", run: () => detail?.scrollBy(5) },
          { bind: "shift+k", title: "Scroll detail up", group: "ctx", run: () => detail?.scrollBy(-5) },
          {
            bind: "o",
            title: "Toggle sort (seq / size)",
            group: "ctx",
            run: () => setSortBy((s) => (s === "seq" ? "size" : "seq")),
          },
          {
            bind: "f",
            title: "Toggle scope (active / all)",
            group: "ctx",
            run: () => setScope((s) => (s === "active" ? "all" : "active")),
          },
          { bind: "s", title: "Select session", group: "ctx", run: () => void pickSession() },
          { bind: "e,return", title: "Edit in Vim", group: "ctx", run: () => void editInVim() },
          { bind: "x", title: "Strip / stub content", group: "ctx", run: () => void applyAction("strip") },
          { bind: "t", title: "Truncate long output", group: "ctx", run: () => void applyAction("truncate") },
          { bind: "c", title: "Clean repetition spam on item", group: "ctx", run: () => void applyAction("clean") },
          { bind: "shift+c", title: "Clean all repetition spam in session", group: "ctx", run: () => void cleanAllSpam() },
          { bind: "d", title: "Delete message/part", group: "ctx", run: () => void applyAction("delete") },
          { bind: "shift+x", title: "Delete all messages after this", group: "ctx", run: () => void applyAction("delete_after") },
          { bind: "g", title: "Go to this session in chat", group: "ctx", run: openTargetSession },
          { bind: "space", title: "Zoom detail", group: "ctx", run: () => setZoom((z) => !z) },
          { bind: "p", title: "Toggle detail pane", group: "ctx", run: () => setPane((v) => !v) },
          { bind: "r", title: "Refresh", group: "ctx", run: () => reload() },
          { bind: "q,escape", title: "Close ctx", group: "ctx", run: close },
          { id: "app.exit", title: "Close ctx", group: "ctx", run: close },
        ],
      }))

      const muted = () => context.theme.text.muted
      const base = () => context.theme.text.base
      const st = activeStats

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
              <span style={{ fg: base(), attributes: TextAttributes.BOLD }}>ctx</span>
              <span style={{ fg: muted() }}>{"   " + (sessionInfo()?.title || "(untitled session)")}</span>
              <span style={{ fg: muted() }}>{"  ·  " + (sessionID() || "")}</span>
            </text>
            <text wrapMode="none" flexShrink={0}>
              <span style={{ fg: muted() }}>sort: </span>
              <span style={{ fg: context.theme.text.feedback.info.base, attributes: TextAttributes.BOLD }}>
                {sortBy() === "size" ? "SIZE ↓" : "SEQ ↑"}
              </span>
              <span style={{ fg: muted() }}>{"   scope: "}</span>
              <span style={{ fg: context.theme.text.feedback.warning.base, attributes: TextAttributes.BOLD }}>
                {scope() === "active" ? "ACTIVE" : "ALL"}
              </span>
            </text>
          </box>
          <box height={1} flexShrink={0} />
          <text wrapMode="none" truncate height={1} flexShrink={0}>
            <span style={{ fg: base(), attributes: TextAttributes.BOLD }}>{`${tokStr(st().actChars)} tok`}</span>
            <span style={{ fg: muted() }}>{` active     `}</span>
            <span style={{ fg: base(), attributes: TextAttributes.BOLD }}>{`${st().actCount}`}</span>
            <span style={{ fg: muted() }}>{`/${st().allCount} items     `}</span>
            <Show when={st().spamCount > 0}>
              <span style={{ fg: context.theme.text.feedback.error.base, attributes: TextAttributes.BOLD }}>
                {`${st().spamCount} SPAM LOOP(S) [press C to clean]     `}
              </span>
            </Show>
            <span style={{ fg: muted() }}>{sessionInfo()?.directory ? context.ui.format.path(sessionInfo()!.directory) : ""}</span>
          </text>
          <box height={1} flexShrink={0} />
          <Show
            when={!zoom()}
            fallback={
              <Show when={selected()} fallback={<text fg={muted()}> No items.</text>}>
                {(it) => <Detail it={it()} ref={(s) => (detail = s)} />}
              </Show>
            }
          >
            <box flexDirection="row" flexGrow={1} minHeight={0}>
              <box flexDirection="column" width={listWidth()} flexShrink={0}>
                <Show when={shown().length} fallback={<text fg={muted()}> No messages in scope.</text>}>
                  <For each={pageRows()}>{(it) => <ItemRow it={it} sel={it.key === selected()?.key} />}</For>
                </Show>
              </box>
              <Show when={split()}>
                <box
                  flexGrow={1}
                  minWidth={0}
                  border={["left"]}
                  borderColor={context.theme.border.base}
                  flexDirection="column"
                >
                  <Show when={selected()}>{(it) => <Detail it={it()} ref={(s) => (detail = s)} />}</Show>
                </box>
              </Show>
            </box>
          </Show>
          <box flexGrow={1} />
          <box height={1} flexShrink={0} />
          <text wrapMode="none" truncate height={1} flexShrink={0} fg={muted()}>
            {
              "j/k nav   s session   o sort(size/seq)   f scope   e/⏎ vim   x strip   t trunc   c/C clean-spam   d del   X del-after   space zoom   q close"
            }
          </text>
        </box>
      )
    }

    context.ui.router.register({ name: ROUTE, render: () => <Page /> })
    context.ui.slot({
      append: "app",
      render() {
        context.keymap.layer(() => ({
          mode: "global",
          commands: [
            {
              id: "ctx.toggle",
              title: "Toggle session context editor",
              group: "ctx",
              bind: "<leader>x",
              palette: true,
              slash: { name: "ctx", aliases: ["context-edit"] },
              run: toggle,
            },
          ],
        }))
        return null
      },
    })
  },
})
