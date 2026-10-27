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
| `bin/` | The command launchers: `merge`, `verdict`, `ste-changed`, `claude-janitor`, and `ci-job`, which runs every step of one workflow job here and prints one verdict per step. Also `ios-ship`, the shared tool that ships iOS apps from the Mac (see "Shipping iOS apps"), `sim-test`, which runs `xcodebuild test` on one phone simulator (see "Simulator tests"), and `shoot`, which takes one screenshot per route, width and theme from a repo's `.claude/shoot.json` and prints one verdict line. |
| `janitor/` | The machine-wide sweep for orphaned worktrees, branches, and listeners. See `janitor/GUIDE.md`. |
| `merge/` | The code of the `merge` command. It runs from the clone, and nothing installs a copy. `bin/merge` starts it. |
| `actions/` | Composite GitHub Actions this repo publishes (`stamp`, `ste-lint`). Callers pin them by commit SHA. |
| `mods/`, `.claude-plugin/` | The vendored mods, and the marketplace file that lists them. |
| `githooks/` | Git hooks for a repo, such as `main-ref`. |
| `testing/` | A shared test helper, `skip-locally-fail-in-ci.mjs`. |
| `tools/` | `mem-monitor.ps1`, a manual Windows memory monitor. No installer lands it, and no hook runs it. |
| `docs/decisions/`, `docs/debts/`, `docs/plans/` | The records: one file per ruling, known gap or deferred item, and plan. See `docs/debts/README.md`. |
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

* Local (symlink mode): at each session start, a `SessionStart` hook in `settings.json`
  fast-forwards local `main` and the live pin to `origin/main` when it can. It works in a
  detached child, so the session that starts it can load before the move ends. A session that
  starts after the child ends sees the move.
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
* A ruling worth keeping: one new file under `docs/decisions/`, named by slug. Claim its number only
  at merge, per CLAUDE.md ("never allocate a numbered record on a branch").
* An open question, not yet ruled on, or a deferred item: a file under `docs/debts/`.

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
  `opus-grant-expires` for the guarded override and its required expiry field.
* **Other repositories cannot use `actions/` after this repository becomes private.** Open
  Settings, then Actions, then General, then Access. Set "Accessible from repositories owned by
  the user".

## Shipping iOS apps

`bin/ios-ship` builds, signs and ships the owner's iOS apps from the Mac. It runs on macOS only, under `/bin/bash` 3.2.
Each private app repo keeps only what differs, in `tools/ios-ship.json`. The account values live once, on the Mac.

**The App Store Connect API key**

* An App Store Connect API key exists for the owner's Apple team.
* The `.p8` file lives only on the Mac, at `~/.appstoreconnect/private_keys/AuthKey_<KEY_ID>.p8`. Never commit it.
  This repo is public, so it holds no team ID, key ID, issuer ID or phone ID.
* A command-line build needs the key. It cannot see the account that is signed in to the Xcode window, and it fails
  with "No Accounts".
* The account file, `~/.config/ios-ship/account.json`, holds the key path and the IDs: `team_id`, `device_udid`,
  `asc_key_path`, `asc_key_id`, `asc_issuer_id`. It lives only on the Mac. The tool checks that the key file exists.
  It never reads the key file.

**The repo config.** The top level holds `repo_url` (the install job clones it) and `apps`. It may also set an account
key, as a variant for that repo. Each app holds `name`, `scheme`, `bundle_id` and `project_dir`. These keys are
optional:

* `project_yml`: the XcodeGen spec. Without it, the project is hand-written and XcodeGen does not run.
* `product_name`: the `.app` name when it differs from the scheme.
* `prebuild`: commands that run in the repo root before XcodeGen.
* `trust_package_plugins`: `true` adds `-skipPackagePluginValidation` and `-skipMacroValidation` to the build.
* `configuration`: `Release` (default) or `Debug`. The install job only.
* `copy_in`: a list of `{from, to}` secret files. The tool copies each into the tree for the build only, and removes
  the copy on every exit path. `to` must be git-ignored. A relative `from` resolves against the repo root of the config.
* `after_archive`: commands that check the archive. They run in the repo root with `ARCHIVE` set. A command that fails
  fails the app. The testflight job only.

Each account value comes from the first of: an environment variable of the same name in capitals (`TEAM_ID`,
`DEVICE_UDID`, `ASC_KEY_PATH`, `ASC_KEY_ID`, `ASC_ISSUER_ID`), the repo config, the account file. A value that is unset
in all three is refused, and the refusal names both files and the variable. The tool has no built-in IDs.

**Run it** from inside the app repo: `ios-ship testflight`, `ios-ship install` or `ios-ship profile --app NAME`. With no `CONFIG`, the tool uses
`tools/ios-ship.json` at the git toplevel of the current folder. Outside a git repo, or with no such file, it exits 2.
The app repos need no wrapper script. `install` refuses `PHONE_APPS_JSON` (exit 2): use `--app` and
`tools/ios-ship.json`.

* `ios-ship testflight [CONFIG] [--app NAME]... [--export-only]` archives each app as Release and uploads it to TestFlight.
  It refuses unless the tree is clean and HEAD is `origin/main`, just fetched. All apps share one build number. It
  stops at the first app that fails, and prints one verdict line. `--export-only` skips the main check, exports the
  `.ipa` files to a folder it prints, and deletes the `.ipa` of each app that has `copy_in`.
* `ios-ship install [CONFIG] [--app NAME]... [--no-install] [--debug] [--force]` builds each app in its own clone under
  `~/Library/Application Support/ios-adblock-reinstall` and installs it on the phone. One app's failure does not stop
  the others. Exit 75 means that the phone was not reachable. `--no-install` stops after a build for generic iOS.
  An install that is more than 300 days old raises an overdue notice.
* `ios-ship profile [CONFIG] --app NAME [--template T] [--time-limit S] [--output P] [--retry-wait S]` records one app
  on the phone with Instruments (`xcrun xctrace record`), by the phone's UDID, and launches the app by its bundle id.
  Defaults: `Time Profiler`, 20 s, a new folder under `$TMPDIR` (the path is printed), and a 60 s retry wait. On a
  network-paired phone, `xctrace` can fail with "Waiting for device to boot" while the phone is fine, and no device
  state predicts it. So that one failure is retried once, after the retry wait. Any other failure is not retried. A
  failure exits with `xctrace`'s code (124 when the tool's timeout stops it) and prints the log path. A failed retry
  also says that the phone may need unlocking or a cable.
* `--app NAME` limits a run to the named apps. A name that is not in the config exits 2. `profile` needs exactly one.

## Simulator tests

`bin/sim-test` runs `xcodebuild test` on one phone simulator. It runs on macOS only, under `/bin/bash` 3.2.
Run it from the folder that holds the project: `sim-test <xcodebuild test args without -destination>`.
It reuses the first booted iPhone. With none booted, it boots the shared iPhone 18 Pro, runs the tests, and shuts that simulator down, also on failure, INT and TERM.
It never shuts down a simulator it did not boot. The exit code is xcodebuild's. The tool takes no lock and waits for no load.

## Standing roles and a roadmap record for a repo

The `project-ops` skill packages how the claude-settings project on claude.ai runs. It holds four
standing roles (triage, build advisor, local liaison, merge hand), one roster, counted hand-offs and
autopilot deferral. It also holds a record branch for the roadmap data, briefs and role hand-off notes. Its
`scripts/scaffold.py` writes the record-branch skeleton. Its `templates/` hold the operating model,
the roster, a brief and a role hand-off note. A repo adopts it only on the owner's word. See
`skills/project-ops/SKILL.md`.

## Details worth knowing but not part of setup

* **How local sessions catch up with main.** `settings.json` carries a `SessionStart` hook. It exits at once
  in cloud sessions, and otherwise hands its work to a detached child and exits 0, so it never blocks
  a session. The session that starts it can load before the child ends; a session that starts
  after the child ends sees the move. The child finds the clone from the `@` pointer in `~/.claude/CLAUDE.md` (the pointer names
  the live pin, a worktree of the clone). One child runs at a time: it holds a lock directory in
  `~/.claude`, and a start that finds the lock exits quietly. A lock a killed child left is cleared
  once it is stale. The child fetches `origin/main` and moves local `main` to it,
  fast-forward only. A tree that holds `main` is merged in place when it has no tracked change;
  otherwise the tree is left alone. The hook never stashes, resets or forces in your trees. When the
  pin is not at local `main`, the child runs `merge/install_from_main.sh`, which switches only the pin
  and never one with tracked changes. A failed fetch,
  move, skip or pin install writes one line to the install log, with its own reason.
  Cost, per session start or resume: one detached child and at most one network fetch. A local
  `git fetch .` runs only when `main` moves by ref because no tree holds it. The helper and the
  installer start only when the pin is not at local `main`. Files written: the lock directory, made
  and removed each time; install-log lines only on a failure, plus the start and end lines of the
  helper and of the installer when they run. The install log's reader is the owner; no hook reads it. Case 34 of
  `merge/test_install_from_main.sh` proves the no-move cost: no log line, no installer, one fetch.
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
  (`docs/decisions/the-janitor-is-one-machine-wide-sweep.md`).

## License

No `LICENSE` file is in this repository yet. Until one is added, the default is "all rights
reserved". Treat the content as personal configuration, not as licensed for reuse.
