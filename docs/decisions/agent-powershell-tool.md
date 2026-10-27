# An agent runs PowerShell with the PowerShell tool

## The question

How does an agent run PowerShell (an Excel harness, COM, a .ps1)?

## The ruling

With Claude Code's PowerShell tool. Never `powershell.exe`, `pwsh` or `cmd` from the Bash tool. No wrapper that hides the command from a check.

Outcome protected: builders prove their own Excel and PowerShell steps (`roles-each-layer-proves-once`, each layer proves a change once), without loosening Claude Code's isolation check or our guard.

## Evidence

Measured 2026-10-20 12:11 CDT, in a worktree-isolated builder in claude-settings:

- The PowerShell tool ran a command in the worktree. It also ran a hidden Excel COM create, save, reopen and quit on a scratch copy.
- Our guard still judged PowerShell-tool calls. Rule `git-env-set` refused `$env:GIT_DIR = 'x'`.
- `powershell.exe -NoProfile -Command "Get-Location"` from Bash was refused by Claude Code itself: "this command runs powershell in a plain command; what it reads or is handed as shell text cannot be shown not to run git". The text is inside claude.exe, not in claude-settings.
- The excel-ui-kit session hit the same refusal for its harness. A reviewer with no worktree also had inline PowerShell refused. The Bash route is closed to agents in general.

Docs: code.claude.com/docs/en/worktrees ("How Claude Code enforces isolation") and docs/en/tools-reference ("PowerShell tool").

Kind: process
Home: agents/builder.md
