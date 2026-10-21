export type Limit = { kind: string; percent: number; resetsAt: string | null }

export type Agent = { type: string; description: string }

export type Snapshot = {
  at: number
  startedAt: number
  prompts: number
  dir: string
  branch: string | null
  isWorktree: boolean
  ahead: number
  behind: number
  changed: number
  costUsd: number | null
  limits: Limit[]
  agents: Agent[]
}

export type GitRead = Pick<Snapshot, 'branch' | 'isWorktree' | 'ahead' | 'behind' | 'changed'> & { at: number }

export type TurnStat = {
  at: number
  durationMs: number
  model: string | null
  cacheHit: number | null
}

export type Compactions = { since: number; count: number; before: number | null; after: number | null }

declare module 'claude-code' {
  interface PluginState {
    'desktop-statusline': {
      snap: Snapshot | null
      git: GitRead | null
      gitFailed: boolean
      warned: string[]
      lastTurn: TurnStat | null
      compactions: Compactions | null
    }
  }
}
