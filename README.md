# claude-settings

One source of truth for my user-level Claude Code config, read by local sessions and by cloud
sessions started from the desktop app / claude.ai/code.

| File            | Becomes                                              |
| --------------- | ---------------------------------------------------- |
| `CLAUDE.md`     | `~/.claude/CLAUDE.md` (through a one-line `@` import) |
| `settings.json` | `~/.claude/settings.json` (symlink locally, generated copy in the cloud) |
| `agents/*.md`   | `~/.claude/agents/*.md` (symlink per file locally, copies in the cloud) |
| `lint/*`        | `~/.claude/lint/*` STE linter and hook gate (same treatment)          |
| `hooks/*`       | `~/.claude/hooks/*` guard and session-start line (same treatment)     |
| `install.sh`    | Wiring for Linux/macOS and for the cloud setup script |
| `install.ps1`   | Wiring for Windows                                   |
| `.github/`      | The `gates.yml` workflow. Runs in this repository only, never installed |
| `actions/`      | Composite actions this repository publishes. Callers pin them at `@main` |

`settings.json` sets `outputStyle: "Concise"` (built-in style, needs Claude Code v2.1.237+),
`CLAUDE_CODE_SUBAGENT_MODEL=sonnet`, `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1`, and
`worktree.baseRef: "head"`.

## Local machine (Windows)

```powershell
git clone https://github.com/ssemwal-cdc/claude-settings C:\src\claude-settings
cd C:\src\claude-settings
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Result:

* `~\.claude\CLAUDE.md` contains one line, `@C:/src/claude-settings/CLAUDE.md`. Claude Code
  resolves `@` imports at session start, so after `git pull` the next session reads the new file.
  Nothing to re-run.
* `~\.claude\settings.json` is a symlink to the clone's `settings.json`, and each
  `~\.claude\agents\<role>.md` is a symlink to the clone's `agents\<role>.md`. Symlinks need
  Windows Developer Mode (Settings > System > For developers) or an admin shell. Without it the
  script copies the files instead, and installs a git `post-merge` hook in the clone. The loop
  is then: a merge lands on main, the next local session start pulls the clone, and the hook
  copies `settings.json`, `agents\*`, and `lint\*`. The hook also re-runs `install.ps1` when the
  pull changed it. A new landed folder or a changed hook body then needs no manual run. Both the
  hook and `install.ps1` log one dated line per run to `~\.claude\claude-settings-install.log`.
  The hook is a bandaid. When Developer Mode is on, re-run `install.ps1` once to get the real
  symlinks.
* Any existing `~\.claude\CLAUDE.md` or `settings.json` is backed up as `*.bak.<timestamp>`
  first. Merge keys you want to keep (for example a `permissions.allow` list Claude Code built up
  from "always allow") into the repo's `settings.json`, then commit.

Verify in a session: `/context` lists `~/.claude/CLAUDE.md` and the imported file under
**Memory files**. `/status` shows the Concise output style.

Linux/macOS: `bash install.sh` from the clone does the same with a real symlink.

## Cloud sessions (desktop app, claude.ai/code, `claude --cloud`)

Cloud VMs never see your machine's `~/.claude`, so the environment's **setup script** has to
recreate it. In claude.ai/code > environment settings, set the setup script to:

```bash
curl -fsSL https://raw.githubusercontent.com/ssemwal-cdc/claude-settings/main/install.sh | bash -s -- --cloud
```

Leave network access at **Trusted** (or add `raw.githubusercontent.com` to a Custom list).
This runs as root before Claude starts and writes:

* `/root/.claude/CLAUDE.md` = `@~/claude-settings/CLAUDE.md`
* `/root/.claude/agents/builder.md` and `reviewer.md` = copies of the repo files
* `/root/.claude/settings.json` = repo `settings.json` plus a `SessionStart` hook that re-runs
  the same one-liner, so each new or resumed session re-fetches both files.

Why the hook: Anthropic snapshots the VM after the setup script and reuses it for about 7 days.
The setup script alone would pin whatever was on `main` at snapshot time. The hook keeps it
fresh. Claude Code reads CLAUDE.md after SessionStart hooks finish, so the fetched files are live
in that same session. Editing the setup script text (any character) forces a fresh snapshot.

To make cloud sessions change only when you say so, pin a commit instead of `main`. Replace
`/main/` in the URL with `/<sha>/`. Set `CLAUDE_SETTINGS_REF=<sha>` as an environment variable on
the environment.

Verify in a cloud session: `/context` for the memory file, and ask Claude to run
`echo $CLAUDE_CODE_SUBAGENT_MODEL` (expect `sonnet`).

## Local auto-pull

`settings.json` carries a `SessionStart` hook that runs at every local session start. It reads
the `@` pointer in `~/.claude/CLAUDE.md` to find the clone, then runs a quiet `git pull --ff-only`
there. It exits at once in cloud sessions (`CLAUDE_CODE_REMOTE` is set). It prints nothing and
never blocks a session. No network, no clone, or a diverged branch all fall through silently. Claude
Code reads CLAUDE.md after SessionStart hooks finish (measured: a hook that rewrote CLAUDE.md
changed the same session's first answer), so a pulled change is live in that very session. The
cloud installer replaces this hook with its own refresh hook, so it never runs in the cloud.

## Subagent model gate

`CLAUDE_CODE_SUBAGENT_MODEL=sonnet` is only a default: a model Claude passes when it spawns a
subagent, or a `model` field in an agent definition, outranks it. A `PreToolUse` hook on the
`Agent` tool closes the first gap. When the spawn names a model other than Sonnet or Haiku, the
hook returns `ask`. A permission prompt appears, in auto mode too, and you decide. CLAUDE.md
tells the orchestrator to make its case in one line before such a spawn. The hook does not catch
a `model` field in an agent file. Set `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` to pin those to Sonnet
as well, at the cost of removing the ask path.

## Roles

CLAUDE.md names three worker roles. Two are shipped here as user-level agent definitions. The
third is Claude Code's built-in `Explore`.

| Role       | File                 | Tools                                   | Tree                       |
| ---------- | -------------------- | --------------------------------------- | -------------------------- |
| `builder`  | `agents/builder.md`  | all                                     | own worktree, from `head`  |
| `reviewer` | `agents/reviewer.md` | all except `Edit`, `Write`, `NotebookEdit` | caller's checkout       |
| `Explore`  | built in             | read-only                               | caller's checkout          |

`worktree.baseRef: "head"` makes a builder's worktree branch from the orchestrator's current
branch instead of `main`, so a second-round builder sees the first round's commits. A worktree
holds tracked files only: a repo with heavy dependencies adds a `.worktreeinclude` for its env
files and an install step to the brief.

**Workers never spawn.** `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1` removes the `Agent` tool
from every subagent, so only the main conversation fans out. Reason, as of September 2026: a
nested child's completion notice goes to the main conversation or is dropped. The subagent that
launched it never hears back and waits forever
([anthropics/claude-code#75043](https://github.com/anthropics/claude-code/issues/75043),
[#86782](https://github.com/anthropics/claude-code/issues/86782),
[#88545](https://github.com/anthropics/claude-code/issues/88545)). Claude Code's cloud
environment already runs at depth 1. This setting makes local sessions match. A repo that needs
nesting sets a higher depth in its own `.claude/settings.json` and records the stall risk in its
CLAUDE.md. Re-check those issues before raising it here.

A project-level `.claude/agents/builder.md` with the same `name` shadows the user-level file, so
a repo can specialize a role and note the change in its CLAUDE.md.

## STE lint gate

CLAUDE.md asks for Simplified Technical English and a fixed report shape. Hooks in
`settings.json` enforce the parts a machine can check, at error severity only:

| Hook | Trigger | Effect |
| --- | --- | --- |
| `PreToolUse` on `Write`, `Edit`, `MultiEdit` | the target path ends in `.md` | the write is denied and the findings come back, so Claude fixes the text and writes again |
| `Stop` | end of a turn | a warning is shown as a system message. The turn is not blocked |
| `Stop` | the turn ran `git commit`, `git push`, `git merge`, or a GitHub MCP write tool | the turn is blocked once unless the reply is one blockquote with the bold labels Done, Deviations, Input Needed, Next in order, written tight in Simplified Technical English |
| `PreToolUse` on `Bash`, `PowerShell`, `Read`, `Grep`, `Edit`, `Write`, `MultiEdit`, `NotebookEdit`, and the GitHub merge tool | a call matches a guard rule | the guard answers deny, ask, or nothing. See Guard below |
| `SessionStart` on `startup`, `resume` | every local session start or resume | the session-start line prints. See Guard below |

Errors are: a sentence over the STE budget (STE001), a semicolon (STE006), a Latin
abbreviation such as `i.e.` (STE007), a contraction (STE008). Warnings such as passive voice
and paragraph length are not gated. Fenced code and inline code are exempt. Table cells are not.

The linter is `lint/ste_lint.py`, vendored from
[DotDebian/asd-ste100-skill](https://github.com/DotDebian/asd-ste100-skill) at commit
`e71a969`, MIT, license in `lint/LICENSE-ste_lint`. It is Python 3.9+ with no dependencies.
The STE gate is `lint/ste_gate.py`. The report gate is `lint/report_gate.py`. It checks the
shape only, not the wording, and it fires only after a landed commit, push, or merge. Both
gates share one fixture suite, `lint/test_gates.py`. Its cases are the check that proves each
gate goes red on the defect it guards. The hook command exits silently when the files or
Python are missing, so a machine without Python runs without the gates. The cloud image has
Python 3.11. On Windows, install Python and make sure `python3` or `python` is on the PATH of
Git Bash.

Run it by hand:

```bash
python3 ~/.claude/lint/ste_lint.py CLAUDE.md            # all severities
python3 ~/.claude/lint/ste_lint.py --fail-on error docs/  # what the gate checks
python3 ~/.claude/lint/ste_lint.py --explain STE006
```

The linter is an approximation of ASD-STE100, whose dictionary is not open. Verified before
merge: the old Roles paragraph with its semicolon goes red, the current CLAUDE.md is clean at
error level.

## Guard

`hooks/guard.py` is a `PreToolUse` hook on `Bash`, `PowerShell`, `Read`, `Grep`,
`Edit`, `Write`, `MultiEdit`, `NotebookEdit`, and the GitHub merge tool. It answers
deny, ask, or nothing. It fails open on bad input.

| Rule | Tools | Decision | Remedy |
| --- | --- | --- | --- |
| Shared trees: `git stash`, `git reset`, `git restore`, `git clean -f`, `git checkout <path>` | `Bash`, `PowerShell` | deny in a shared checkout, ask in a git worktree | mutation-test with a `.bak` copy, or work in a worktree of your own |
| Machine-wide kills: `pkill`, `killall`, `lsof -t`, `taskkill /IM`, `Stop-Process -Name` | `Bash`, `PowerShell` | deny | name one PID this session started |
| Force push: `--force`, `-f`, `--force-with-lease` | `Bash`, `PowerShell` | ask | the click in the prompt is the grant |
| Recursive delete at `/`, `~`, `.`, `*`, or a drive root | `Bash`, `PowerShell` | deny | name the folder |
| Environment files: any `.env*` except `.env.example` | `Read`, `Grep`, `Edit`, `Write`, `MultiEdit`, `NotebookEdit`, and shell text | deny | ask the user for the value. Loader flags such as `--env-file` and existence checks with `ls` or `test` pass |
| Merge into main: `gh pr merge` with base `main`, and every `mcp__github__merge_pull_request` call | `Bash`, `PowerShell`, MCP | ask | the click is the grant. A merge into another base passes |
| Frozen paths: a project's `.claude/settings.json`, `.claude/settings.local.json`, `.claude/hooks/*`, and `settings.json`, `CLAUDE.md`, `hooks/*`, `lint/*`, `agents/*` under `~/.claude` | `Edit`, `Write`, `MultiEdit`, `NotebookEdit`, and shell writes | deny | edit the clone of claude-settings and open a PR |
| Live streams: `tail -f`, `tail -F`, `--follow`, `Get-Content -Wait` | `Bash`, `PowerShell` | deny | run it in the foreground with a timeout, or in the background and wait for the completion notice |

The harness watcher tool `Monitor` is removed through `permissions.deny` in `settings.json`. It
errors often, and a background command with a completion notice does the same job.

### Decisions

1. Discards and force push: **ask or deny, no tokens.** Deny `git stash`, `git reset`, `git restore`, `git clean -f`, and a `git checkout` that names a path when the cwd is a shared checkout. Answer `ask` for the same commands when the cwd is a git worktree, and `ask` for `git push --force` or `-f` anywhere. The user's click in the permission prompt is the grant. Reason: q_max's `GIT_DISCARD_OK=1` and `DESTRUCTIVE_OK=1` tokens pass silently and are typed by the agent, so nothing proves the user was asked.
2. Merge into main: **ask always.** `gh pr merge` whose PR base is `main` (read with `gh pr view <n> --json baseRefName`, and `ask` when unreadable), and every call of the `mcp__github__merge_pull_request` tool. A merge into any other base passes. No `OWNER_MERGE=1` token.
3. Composite action pin for callers: **`@main`.**
4. STE in CI: **changed files only** against the PR base by default. A `scope: all` input runs the whole tree in report mode and never fails the build, for manual audits from the Actions tab.
5. Stamping of decision records: **stays local** in each repo. Formats differ (`D100_<slug>.md` per kind by date in job-cost-reporting, `<slug>.md` with `id: pending` in first-parent order in q_max). Do not touch it.
6. Extras: add the SessionStart checkout line. No scheduled audit, dispatch only. No stamp work.

Every deny or ask appends one line to `~/.claude/guard.log`: timestamp, tool,
decision, rule, and the matched text cut at 120 characters. Allows are never
logged. This is how a false positive gets measured later.

Both job-cost-reporting and q_max keep their own guards until a week of clean
`guard.log` on both machines. After that, each repo trims to what only it
owns. That is a later task.

`hooks/session_start.sh` prints `checkout <toplevel> on <branch>, <n> dirty
files` at local session start and resume. It stays silent outside a git tree.
The cloud install replaces the `SessionStart` list, so this line is local
only.

Run the fixture suite with `python3 ~/.claude/hooks/test_guard.py`. Each case
is the check that proves a rule goes red on the defect it guards.

## CI

`.github/workflows/gates.yml` runs on push to `main`, on every pull request, and on manual
dispatch. Each run sets up Python 3.11. It then runs the guard suite, the report-gate suite,
a shell check of `install.sh`, a PowerShell parse of `install.ps1`, and the STE lint action.

Manual dispatch takes one input, `full_ste_audit`. Enable it from the Actions tab to lint
the whole tree in report mode. That run never fails the build. It only writes a summary.

`actions/ste-lint` is the composite action behind the STE step. Scope `changed` diffs
markdown against the pull request base, or the default branch on a push. Scope `all` lints
every file the `paths` glob names. Input `fail` sets whether an error blocks the step. The
action always writes a step summary: the file count, the error and warning counts, and a
table of the first fifty findings.

A caller pins the action to `@main`:

```yaml
- uses: actions/checkout@v4
  with: { fetch-depth: 0 }
- uses: ssemwal-cdc/claude-settings/actions/ste-lint@main
  with:
    scope: changed
    fail: "true"
```

The caller needs `actions/checkout` at `fetch-depth: 0`. Scope `changed` diffs against a
branch, and a shallow clone carries no history for the diff.

One manual step remains, in this repository only. Open Settings, then Actions, then
General, then Access. Set "Accessible from repositories owned by the user". That setting
applies to a private repository only. This repository is public, so any repository can
call the action today. No file sets this switch. Flip it after this pull request merges,
before the first external caller runs.

## Editing

Edit `CLAUDE.md` or `settings.json` here, commit, push. Local picks it up on `git pull`. Cloud
picks it up on the next session start.

A new role is a new `agents/<name>.md`. A linter change is a change to `lint/`. A guard change is
a change to `hooks/`. Locally, re-run the installer once so the symlink exists. In copy mode, the
post-merge hook copies `settings.json`, `agents\*`, `lint\*`, and `hooks\*` on the next pull. It
also re-runs `install.ps1` itself when the pull changed it. So a new landed folder or a changed
hook body needs no manual run. Check `~\.claude\claude-settings-install.log` for a dated line
from each run. Cloud picks it up on the next session start.

Hooks in `settings.json` run everywhere the file lands. Command hooks use `sh` syntax, which Git
Bash runs on Windows. Guard anything local-only with `CLAUDE_CODE_REMOTE`. The cloud install
replaces the `SessionStart` list with its own refresh hook and leaves every other event alone.
