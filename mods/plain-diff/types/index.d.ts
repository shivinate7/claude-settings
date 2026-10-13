export type Entry = {
  path: string
  add: number
  del: number
  lines: number
  diff: string
  isCut: boolean
  note: string
  // turn: Claude's own words. model: one model call. pending: a call is running. none: no note.
  source: 'turn' | 'model' | 'pending' | 'none'
}
export type Report = {
  entries: Entry[]
  files: number
  add: number
  del: number
  hiddenFiles: number
  error: string
}

declare module 'claude-code' {
  interface PluginState {
    'plain-diff': { report: Report; open: string[] }
  }
}
