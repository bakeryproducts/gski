import { homedir } from "node:os"
import { join } from "node:path"

export const ROUTE = "ocq"
export const REGISTRY = join(process.env.XDG_STATE_HOME || join(homedir(), ".local", "state"), "ocq", "projects")
export const ORDER = ["running", "reported", "failed", "pending", "done"]
export const BAR = ["done", "reported", "running", "failed", "pending"]
export const HEAD = 12
export const ROW = 4

export type Tokens = { input: number; output: number; reasoning: number; cache_read: number; cache_write: number }
export type Task = Record<string, any> & { id: string; status: string; attempts: number; cost: number }
export type Act = { text: string; status: string }
export type Live = { state: string; cost: number; tokens?: Tokens; activity: Act[] }
export type Stream = Record<string, any> & {
  id: string
  status?: string
  session?: string
  dir?: string
  manager?: string
  updated?: number
}
export type Ocm = { root: string; manager?: string; streams: Stream[] }
export type Run = {
  key: string
  kind: "run" | "ocm" | "orch"
  name: string
  dir: string
  projectDir: string
  cfg: Record<string, any>
  tasks: Task[]
  counts: Record<string, number>
  total: number
  cost: number
  last: number
  brief: string
  stream?: Stream
}
