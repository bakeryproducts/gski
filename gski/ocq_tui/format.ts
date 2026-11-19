import { basename } from "node:path"
import type { Act, Run, Tokens } from "./types"

export const now = () => Math.floor(Date.now() / 1000)
export const round4 = (n: number) => Math.round(n * 1e4) / 1e4
export const money = (c: number) => "$" + (c || 0).toFixed(2)
export const flat = (s: any) => String(s ?? "").replace(/\s+/g, " ").trim()
export const listOf = (res: any) => (Array.isArray(res) ? res : res?.data || [])

export function fmtDateTime(sec?: number) {
  if (!sec) return ""
  const d = new Date(sec * 1000)
  const p = (n: number) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

export function fmtModelRef(m: any): string {
  if (!m) return ""
  if (typeof m === "string") return m
  const base = [m.providerID, m.id || m.modelID].filter(Boolean).join("/")
  return base + (m.variant ? `#${m.variant}` : "")
}

export function clip(s: string, n: number) {
  return s.length <= n ? s : s.slice(0, n - 1) + "…"
}

export function dur(s?: number) {
  if (s == null || s < 0) return ""
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const x = s % 60
  return h ? `${h}h ${m}m` : m ? `${m}m ${x}s` : `${x}s`
}

export function kn(n?: number) {
  n = n || 0
  if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e7 ? 0 : 1) + "M"
  if (n >= 1e3) return (n / 1e3).toFixed(n >= 1e4 ? 0 : 1) + "k"
  return String(n)
}

export function sumTokens(items: any[]): Tokens {
  const out = { input: 0, output: 0, reasoning: 0, cache_read: 0, cache_write: 0 }
  for (const tk of items) {
    if (!tk) continue
    const cache = tk.cache || {}
    out.input += tk.input || 0
    out.output += tk.output || 0
    out.reasoning += tk.reasoning || 0
    out.cache_read += tk.cache_read ?? cache.read ?? 0
    out.cache_write += tk.cache_write ?? cache.write ?? 0
  }
  return out
}

export function streamStatusMark(s?: string) {
  if (s === "running") return "▸"
  if (s === "reported") return "?"
  if (s === "failed") return "✗"
  if (s === "done") return "✓"
  return "○"
}

export function runLabel(r: Run, activeIds?: Set<string>) {
  const proj = r.projectDir ? basename(r.projectDir) : ""
  const dt = fmtDateTime(r.last)
  const suffix = dt ? ` · ${dt}` : ""
  if (r.kind === "ocm") {
    const label = proj ? `${proj}/ocm:${r.name}` : `ocm:${r.name}`
    return ` ${label} ${streamStatusMark(r.stream?.status)}${suffix} `
  }
  if (r.kind === "orch") {
    const busy = activeIds?.has(r.cfg?.orchestrator)
    const label = proj ? `${proj}/orch:${clip(r.name, 22)}` : `orch:${clip(r.name, 22)}`
    return ` ${label} ${busy ? "▸" : "○"}${suffix} `
  }
  const label = proj ? `${proj}/${r.name}` : r.name
  const ocmRunning = !r.counts.running && r.stream?.status === "running"
  return ` ${label} ${r.counts.done || 0}/${r.total}${r.counts.running ? ` ${r.counts.running}▸` : ocmRunning ? " ▸" : ""}${r.counts.reported ? ` ${r.counts.reported}?` : ""}${suffix} `
}

export function assistants(msgs: any[]) {
  return msgs.filter((m) => m?.type === "assistant")
}

export function activity(msgs: any[], limit = 10): Act[] {
  const out: Act[] = []
  for (const m of assistants(msgs)) {
    for (const c of [...(m.content || [])].reverse()) {
      if (c.type === "tool") {
        const st = c.state || {}
        const inp = st.input || {}
        const what = inp.command || inp.path || inp.filePath || inp.pattern || inp.url || inp.query || ""
        out.push({ text: `${c.name}: ${what}`.slice(0, 2000), status: st.status || "completed" })
        if (out.length >= limit) return out
      } else if (!out.length && c.type === "text" && String(c.text || "").trim()) {
        out.push({ text: c.text.trim().slice(0, 2000), status: "completed" })
      }
    }
  }
  return out
}

export function lastText(msgs: any[]) {
  for (const m of assistants(msgs)) {
    const txt = (m.content || [])
      .filter((c: any) => c.type === "text")
      .map((c: any) => c.text || "")
      .join("\n")
      .trim()
    if (txt) return txt
  }
  return ""
}

export function shortTier(t: any) {
  const m = String(t.model || "")
    .split("/")
    .pop()!
    .split("#")[0]
    .replace("gemini-4-", "")
  const a = t.agent && t.agent !== "worker" ? t.agent : ""
  return [a, m].filter(Boolean).join("/")
}

export function taskSummary(t: any) {
  if (t.status === "running") {
    if (t.msg) return "msg: " + t.msg
    if (t.live?.state === "idle") return "settling…"
    const a = t.live?.activity?.[0]
    return a ? (a.status === "error" ? "✗ " : a.status === "running" ? "▸ " : "✓ ") + a.text : t.task
  }
  if (t.status === "reported" && t.worker) return `${t.worker}: ${t.note || ""}`
  return (t.status !== "pending" && t.note) || t.task
}

export function taskTime(t: any, nowSec: number) {
  if (t.status === "running" && t.started) return dur(nowSec - t.started)
  if (t.started && t.finished && t.finished >= t.started) return dur(t.finished - t.started)
  return ""
}
