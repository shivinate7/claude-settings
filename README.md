# claude-settings

One source of truth for my user-level Claude Code config. Local sessions and cloud sessions
(desktop app, claude.ai/code) both read it.

## What is here

Each folder that `landed-dirs.txt` names lands in `~/.claude`. Both installers read that
file, so a folder added there lands on every platform with no other change. Every other path
stays in the clone. The mods install from the marketplace instead (decision
`mods-install-via-marketplace`, mods install with no installer step).

| Path | Holds |
| --- | --- |
| `CLAUDE.md` | Global working rules. A one-line `@` import in `~/.claude/CLAUDE.md` loads it. |
| `settings.json` | Output style, env vars, hooks. It becomes `~/.claude/settings.json`. |
| `landed-dirs.txt` | The folders that both installers land. |
| `agents/` | The subagent roles, one file each. |
| `hooks/` | The guard, the watches, and the other hook scripts. |
| `lint/` | The Simplified Technical English linter, and the gates and checks that CI runs. |
| `skills/` | The shipped skills, one folder each. |
| `output-styles/` | The `shiv-stylisms` output style. |
| `ux/` | The house UX rules. |
| `bin/` | The command launchers: `merge`, `verdict`, `ste-changed`, `claude-janitor`. |
| `janitor/` | The machine-wide sweep for orphaned worktrees, branches, and listeners. See `janitor/GUIDE.md`. |
| `merge/` | The code of the `merge` command. It runs from the clone, and nothing installs a copy. `bin/merge` starts it. |
| `actions/` | Composite GitHub Actions this repo publishes (`stamp`, `ste-lint`). Callers pin them by commit SHA. |
| `mods/`, `.claude-plugin/` | The vendored mods, and the marketplace file that lists them. |
| `githooks/` | Git hooks for a repo, such as `main-ref`. |
| `testing/` | A shared test helper, `skip-locally-fail-in-ci.mjs`. |
| `decisions/`, `debts/`, `deferred/`, `plans/` | The records: one file per ruling, known gap, open question, and plan. See `debts/README.md`. |
| `docs/` | The generated pages: `records.md` indexes the records, `catalog.md` lists hooks, mods and skills. |
| `.github/` | `gates.yml`, the CI that checks this repo, and this repo's stamp config. |
| `.claude/` | Instructions that load only in sessions on this repo. |
| `.gitattributes`, `.gitignore` | The line-ending rules, and the files that git leaves out. |
| `.ste-lint-exclude` | The pathspecs that the STE lint leaves out, such as pinned third-party prose. |
| `renovate.json` | The Renovate config that updates pinned versions. |
| `install.sh`, `install.ps1` | The installers. The `install*.test.ps1` files test them. |

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
  The line reads `settings.json=<mode> agents/lint=<mode>`. A mode is `symlink`, `copy`, or `kept`.
  `kept` means that a replace failed (a file lock, say) and nothing was copied, so the old files
  stay in place. `copy+failed` (agents/lint only) means that some files were copied and at least
  one replace failed; that file keeps its old copy. The run prints why. Run `install.ps1` again
  after you close the lock.

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
then merges. The repo's own opt-in is the `merge` block of its stamp config, see "The merge
tool contract" in `actions/stamp/README.md`.

Run it from inside the repo, with `gh`, `git`, `node` and Python 3 on PATH:

```
merge <pr>              preview: what it would claim and merge. Presses nothing.
merge <pr> --confirm [--session NAME]   lock, claim, rebuild the records page, push, wait, merge, move the local main, clean up.
                        NAME shows in the lock to a waiting run.
merge --unlock [BRANCH] remove the merge lock on BRANCH (default: the default branch). Reads no lock state.
merge --dev ...         run the checkout's own tree, not origin main
```

`merge --help` lists every flag except `--dev`.

* **Launcher.** On macOS and Linux, `bin/merge` lands in `~/.claude/bin`. On Windows,
  `bin\merge.cmd` lands there too, and starts `bin\merge`. The installers put `~/.claude/bin`
  on PATH. The launcher holds no merge logic. It finds this clone through `CLAUDE_SETTINGS_DIR`,
  then the `@` line in `CLAUDE.md` under `CLAUDE_CONFIG_DIR` (default `~/.claude`). With
  neither, it clones the public repo into a temporary folder. The checkout must have `origin`
  set to `shivinate7/claude-settings`. Any other result stops before a pull request read. A
  repo's own wrapper, such as a `make merge` target, may hold the same lookup instead.
* **Fresh code.** Each run fetches `origin main` and runs from a temporary worktree at that
  SHA. It prints the SHA it ran. If it cannot prove fresh code, such as when offline, it
  prints a warning block and runs the code it has. `--dev` skips all of this and runs the
  checkout's own tree. Use it only to work on the tool.
* **After a stop.** The message on stderr names the cause. A held lock names its holder and
  says if the holder is alive, dead, or unknown. `--unlock` is for a dead holder only.
  A rerun on a branch that already holds its own claim resumes at the wait.
* **Where the rest is written.** The flow is `confirm` in `merge/merge.py`. The rulings are
  in these decisions:
  * ci-wait-reads-run-status (the wait reads status, never `gh run watch`)
  * records-index-at-merge (the merge rebuilds the records page)

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
  CI step, or `unmechanized` or `judgment` plus a reason) in `lint/rule_mechanisms.json`.
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
  `actions/ste-lint`.
* **The janitor is one machine-wide sweep, not a per-repo tool.** It reaps branches and
  worktrees no session still needs, across every repository on the machine. It can stop one
  kind of process: an orphaned TCP listener it owns. Full contract in `janitor/GUIDE.md`
  (`decisions/the-janitor-is-one-machine-wide-sweep.md`).

## License

No `LICENSE` file is in this repository yet. Until one is added, the default is "all rights
reserved". Treat the content as personal configuration, not as licensed for reuse.
