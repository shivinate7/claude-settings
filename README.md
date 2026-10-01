# claude-settings

One source of truth for my user-level Claude Code config. Local sessions and cloud sessions
(desktop app, claude.ai/code) both read it.

## What is here

| Path            | Holds                                                    | Becomes                       |
| --------------- | --------------------------------------------------------- | ------------------------------ |
| `CLAUDE.md`     | Global working rules                                       | `~/.claude/CLAUDE.md`, through a one-line `@` import |
| `settings.json` | Output style, env vars, hooks                               | `~/.claude/settings.json` |
| `agents/`       | The `builder` and `reviewer` roles                          | `~/.claude/agents/*.md` |
| `hooks/`        | `guard.py` (refuses destructive git in a shared tree), config and decision watches, `session_start.sh` | `~/.claude/hooks/*` |
| `lint/`         | The Simplified Technical English prose linter and its hook gate | `~/.claude/lint/*` |
| `janitor/`      | A machine-wide sweep for orphaned worktrees, branches, and listeners. See `janitor/GUIDE.md` | not installed to `~/.claude`, runs from the clone |
| `decisions/`    | One file per ruling, cited by slug                          | stays in the repo |
| `deferred/`, `plans/` | Open questions and plans, not yet a ruling             | stay in the repo |
| `actions/`      | Composite GitHub Actions this repo publishes (`stamp`, `ste-lint`) | callers pin them by commit SHA |
| `merge/`, `bin/` | The `merge` command, and its launchers `bin/merge` and `bin/merge.cmd` | `bin/` lands in `~/.claude/bin`. `merge/` runs from the clone |
| `.github/`      | `gates.yml`, the CI that checks this repo                   | runs here only, never installed |

`agents/`, `hooks/`, and `lint/` are the folders `landed-dirs.txt` names. Both installers read
that file, so a new folder added there lands on every platform with no other change.

## Quick start

### Windows

```powershell
git clone https://github.com/shivinate7/claude-settings C:\src\claude-settings
cd C:\src\claude-settings
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Needs Windows Developer Mode (Settings > System > For developers), or an admin shell, for real
symlinks. Without it, the script copies the files and installs a git `post-merge` hook that
re-copies them after every pull on `main`.

### macOS, Linux

```bash
mkdir -p ~/Developer
git clone https://github.com/shivinate7/claude-settings ~/Developer/claude-settings
cd ~/Developer/claude-settings
bash install.sh
```

Everything is a real symlink. A `git pull` in the clone is the whole update.

### Cloud sessions (desktop app, claude.ai/code, `claude --cloud`)

A cloud VM never sees your machine's `~/.claude`. In claude.ai/code, set the environment's
setup script to:

```bash
curl -fsSL https://raw.githubusercontent.com/shivinate7/claude-settings/main/install.sh | bash -s -- --cloud
```

Leave network access at Trusted, or add `raw.githubusercontent.com`, `github.com`, and
`codeload.github.com` to a Custom list. The script also writes a `SessionStart` hook that
re-runs itself, so each new or resumed session re-fetches the files even from a stale
snapshot. To pin cloud sessions to one commit instead of `main`, replace `/main/` in the URL
with `/<sha>/`, or set `CLAUDE_SETTINGS_REF=<sha>` as an environment variable.

## Verify the install

* `/context`, in any session, lists `~/.claude/CLAUDE.md` and the imported file under
  **Memory files**.
* `/status` shows the `shiv-stylisms` output style.
* In a cloud session, ask Claude to run `echo $CLAUDE_CODE_SUBAGENT_MODEL`. Expect `sonnet`.
* On Windows in copy mode, check `~\.claude\claude-settings-install.log` for a dated line from
  the last run.

## How a change reaches you

Edit a file here, commit, push, open a pull request against `main`. `.github/workflows/gates.yml`
runs the guard fixture suite, its mutation harness, the STE lint, and the rest of the checks
named in that file. Merge only when you say so, or under a repo grant, per CLAUDE.md.

Once merged:

* Local (symlink mode): `settings.json` carries a `SessionStart` hook that pulls the clone at
  every session start. The new file is live in that same session, because Claude Code reads
  `CLAUDE.md` after `SessionStart` hooks finish.
* Local (copy mode, Windows without Developer Mode): the `post-merge` git hook copies the
  changed files after your next `git pull` on `main`, and re-runs `install.ps1` itself if
  `install.ps1` changed.
* Cloud: the next new or resumed session re-runs the setup script and picks up the change.

## The `merge` command

One command merges a pull request in any repo that has opted in. It claims record numbers
before the merge, waits for CI on the claim commit, reverts the claim if a step fails, and
then merges. Plan: `plans/shared-merge-tool.md`. The repo's own opt-in is the `merge` block of
its stamp config, see "The merge tool contract" in `actions/stamp/README.md`.

Run it from inside the repo, with `gh`, `git`, `node` and Python 3 on PATH:

```
merge <pr>              preview: what it would claim and merge. Presses nothing.
merge <pr> --confirm    lock, claim, push, wait, merge, move the local main, clean up.
merge --unlock          remove this repo's merge lock. Reads no other state.
merge --dev ...         run the checkout's own tree, not origin main
```

* **Launcher.** On macOS and Linux, `bin/merge` lands in `~/.claude/bin`. On Windows,
  `bin\merge.cmd` lands there too, and starts `bin\merge`. Both find this clone through
  `CLAUDE_SETTINGS_DIR`, then the `@` line in `CLAUDE.md` under `CLAUDE_CONFIG_DIR` (default
  `~/.claude`). With neither, they clone
  the public repo into a temporary folder. The checkout must have `origin` set to
  `shivinate7/claude-settings`. Any other result stops before a pull request read.
* **Fresh code.** Each run fetches `origin main` and runs from a temporary worktree at that
  SHA. It prints the SHA it ran. If it cannot prove fresh code, such as when offline, it
  prints a warning block and runs the code it has. `--dev` skips all of this and runs the
  checkout's own tree. Use it only to work on the tool.
* **Preview.** `merge <pr>` runs the claim in a temporary worktree and drops it. It prints
  the lock state, the state of the head's checks (green, or every pending or red check by name), the claim line, and the steps a run would take. Nothing reaches origin.
* **`--confirm`.** It takes the lock, then reads the required checks. If the list is empty or
  unreadable, it stops before the claim push. Then it checks first: it waits for the head's
  own checks, and a red one stops the run with nothing claimed or pushed. Only on green does it
  claim and push the claim, and wait for the checks on the claim SHA. It checks that each claimed number is still free on the base tip,
  and merges with `--match-head-commit`. Then it moves the local main, runs `afterMerge`, and
  deletes the head branch if `merge.deleteBranch` is set. A rerun on a branch that already
  holds its own claim resumes at the wait.
* **The wait.** It ends green only when every check run and status on the head SHA has finished
  and none failed, required or not. Skipped and neutral pass. A pending check is waited on. A
  failed, cancelled, timed out, action required or startup failure check stops the run, and so does
  any status the tool does not know. The required list must still be non-empty, and each name must
  be present, so a check that never started cannot pass by its absence. Both waits (the head
  before the claim, and the claim SHA) work this way. `merge.ignoreChecks` is an optional list of
  `{"name": "...", "reason": "..."}` in the `merge` block. A check named there is left out of the
  wait, and the output names it. An entry with no name or an empty reason refuses the config.
* **A stop in the wait.** The wait stops on any failed or cancelled check, required or not,
  and on a DIRTY branch or a moved head. It reverts the claim, but only while the origin head
  is still the claim commit. A head that still reads as the pre-claim SHA is GitHub lagging
  the push, so the wait goes on until the deadline.
* **`--unlock`.** The lock is the ref `refs/merge-lock/<defaultBranch>` on origin. It expires
  after twice `merge.deadlineMinutes` plus ten minutes (a run can wait twice), and a later run breaks an expired lock.
  `--unlock` removes it at once, for a run that died. It reads no lock state. It still reads the git root and the config.

Exit codes:

| Code | Meaning |
| --- | --- |
| 0 | A preview ran, the lock was removed, or the merge landed and every after-step passed. |
| 1 | A refusal or a failed step. The message on stderr names it. A launcher stop also exits 1. |
| 1 | The merge landed, but the local main did not move or an `afterMerge` command failed. The merge stays. The printed line says so. |
| 2 | The arguments are wrong, such as both a pull request number and `--unlock`. |

Exit 1 has two causes. Read the output to tell them apart. A line that starts
`merge: #<pr> merged as` means that the merge landed.

## Editing

* A rule in `CLAUDE.md`: edit the file. Wrap the sentence in a `<!-- rule:<slug> --> ` anchor if
  you want `lint/rule_audit.py` to hold you to naming its enforcement (a guard rule, a gate, a
  CI step, or `unmechanized` plus a reason) in `lint/rule_mechanisms.json`.
  All the guard rules, gates, and their design rationale live as comments and numbered
  decisions inside `hooks/guard.py` and `lint/`. Read there, not here, for the full list.
* A new role: add `agents/<name>.md`. A project can override it with a project-level
  `.claude/agents/<name>.md` carrying the same `name`.
  See `agents/builder.md` and `agents/reviewer.md` for the two shipped roles, and CLAUDE.md's
  Roles section for what each is for.
* A linter change: edit `lint/`. A guard change: edit `hooks/`. Re-run the installer once
  locally so a new symlink exists.
* A ruling worth keeping: one new file under `decisions/`, named by slug. Claim its number only
  at merge, per CLAUDE.md ("never allocate a numbered record on a branch").
* An open question, not yet ruled on: a file under `deferred/`.

## Troubleshooting

* **The STE lint or guard hooks do nothing.** They need Python 3.9+ as `python3` or `python` on
  PATH. Hook commands run under `sh` on Windows, so put Python on Git Bash's own PATH there.
  Python 3 ships with the Command Line Tools on macOS. When it is missing, run
  `xcode-select --install`. When Python is missing, the hook command exits silently, so a
  machine without it just runs without the gates.
* **A symlink did not take on Windows.** Enable Developer Mode. Re-run `install.ps1` once, to
  replace the copies with real symlinks.
* **An existing `~/.claude/CLAUDE.md` or `settings.json` had content you wanted to keep.** Both
  installers back up the old file as `*.bak.<timestamp>` before writing. Fold anything you want
  into the repo's own `CLAUDE.md` or `settings.json`, then commit.
* **A cloud session looks stale.** Anthropic snapshots the VM for about 7 days and reuses it.
  The `SessionStart` hook the setup script installs re-fetches on every session, so this should
  self-heal. When it does not, check the environment's network access is not blocking the three
  hosts above.
* **The subagent model cap needs a temporary raise.** See CLAUDE.md's Roles section and
  `decisions/subagent-model-cap.md` for the guarded override and its required expiry field.
* **Other repositories cannot use `actions/` after this repository becomes private.** Open
  Settings, then Actions, then General, then Access. Set "Accessible from repositories owned by
  the user".

## Details worth knowing but not part of setup

* **Why local sessions never run stale.** `settings.json` carries a `SessionStart` hook that
  runs a quiet `git pull --ff-only` in the clone, found through the `@` pointer in
  `~/.claude/CLAUDE.md`. It exits at once in cloud sessions. It never blocks a session. A
  failed pull falls through silently.
* **Why subagents cannot nest.** `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1` removes the `Agent`
  tool from every subagent, so only the main conversation fans out. A nested child's completion
  notice can misroute. This stalls the subagent that launched it
  ([anthropics/claude-code#75043](https://github.com/anthropics/claude-code/issues/75043)). A
  repo that needs nesting raises the depth in its own `.claude/settings.json` and records the
  risk in its CLAUDE.md.
* **Why `actions/ste-lint` exists as a composite action.** A caller repo can then lint only the
  lines a pull request changed, against the pull request base. It never pays down a whole
  document's old backlog on the first branch that touches it. See the diff-scope rationale in
  `actions/ste-lint` and `decisions/ste-lint-gloss-collapse.md`.
* **The janitor is one machine-wide sweep, not a per-repo tool.** It reaps branches and
  worktrees no session still needs, across every repository on the machine. It can stop one
  kind of process: an orphaned TCP listener it owns. Full contract in `janitor/GUIDE.md`
  (`decisions/the-janitor-is-one-machine-wide-sweep.md`).

## License

No `LICENSE` file is in this repository yet. Until one is added, the default is "all rights
reserved". Treat the content as personal configuration, not as licensed for reuse.
