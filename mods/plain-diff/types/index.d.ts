export type Entry = {
  path: string
  label: string
  key: string
  add: number
  del: number
  lines: number
  diff: string
  isCut: boolean
  note: string
  // turn: Claude's own words. model: one model call. pending: a call is running.
  // none: no note, with a reason. large: change too large. secret: file skipped, no diff kept.
  source: 'turn' | 'model' | 'pending' | 'none' | 'large' | 'secret'
}
export type Report = {
  entries: Entry[]
  files: number
  add: number
  del: number
  hiddenFiles: number
  truncated: boolean
  error: string
}

declare module 'claude-code' {
  interface PluginState {
    'plain-diff': { report: Report; open: string[] }
  }
}
