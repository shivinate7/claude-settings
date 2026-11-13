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
| `agents/` | The agent roles, one file each. |
| `hooks/` | The guard, the watches, and the other hook scripts. |
| `lint/` | The Simplified Technical English linter, and the guards and checks that CI runs. |
| `skills/` | The shipped skills, one folder each. |
| `output-styles/` | The `shiv-stylisms` output style. |
| `docs/design/` | The house UX rules. |
| `bin/` | The command launchers: `merge`, `verdict`, `ste-changed`, `claude-janitor`, and `ci-job`, which runs every step of one workflow job here and prints one verdict per step. Also `ios-ship`, the shared tool that ships iOS apps from the Mac (see "Shipping iOS apps"), `sim-test`, which runs `xcodebuild test` on one phone simulator, and `sim-lease`, the queue and lease it takes first (see "Simulator tests"), `duo-fold`, which folds the iPhone Duo and reads the angle back, and `shoot`, which takes one screenshot per route, width and theme from a repo's `.claude/shoot.json` and prints one verdict line. |
| `janitor/` | The machine-wide sweep for orphaned worktrees, branches, and listeners. See `janitor/GUIDE.md`. |
| `merge/` | The code of the `merge` command. It runs from the clone, and nothing installs a copy. `bin/merge` starts it. |
| `actions/` | Composite GitHub Actions this repo publishes (`stamp`, `ste-lint`, `playwright-setup`). Callers pin them by commit SHA. |
| `mods/`, `.claude-plugin/` | The vendored mods, and the marketplace file that lists them. |
| `githooks/` | Git hooks for a repo, such as `main-ref`. |
| `testing/` | A shared test helper, `skip-locally-fail-in-ci.mjs`. |
| `tools/` | `mem-monitor.ps1`, a manual Windows memory monitor. No installer lands it, and no hook runs it. |
| `docs/decisions/`, `docs/debts/`, `docs/plans/` | The records: one file per ruling, known gap or deferred item, and plan. See `docs/debts/README.md`. |
| `docs/` | The generated pages: `records.md` indexes the records, `catalog.md` lists hooks, mods and skills. |
| `.github/` | `checks.yml`, the CI that checks this repo, and this repo's stamp config. |
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

A cloud VM never sees your machine's `~/.claude`. Paste this once per environment, in the
cloud environment menu in the session title bar, then Edit, then Setup script. It installs
before Claude Code starts, so the first agent spawn reads `agents/*.md` (decision
`agent-model-cap`). It never fails setup: on any failure it prints one
`claude-settings setup:` line and the session starts without the install.

```bash
f=$(mktemp)
if ! curl -fsS --max-time 20 https://raw.githubusercontent.com/shivinate7/claude-settings/main/cloud-setup.sh -o "$f"; then
  : > "$f"
  for d in ${CLAUDE_SETTINGS_SEARCH_ROOTS:-/home/user /root}; do
    for c in "$d"/*/cloud-setup.sh; do
      case "$(git -C "${c%/*}" config --get remote.origin.url 2>/dev/null)" in
        *github.com[/:]shivinate7/claude-settings|*github.com[/:]shivinate7/claude-settings.git) cp "$c" "$f" && break 2 ;;
      esac
    done
  done
fi
if [ -s "$f" ]; then bash "$f" || true; else echo "claude-settings setup: no source: GitHub down, or the repo is private and not under the environment's Repositories"; fi
rm -f "$f"
exit 0
```

Also set these as environment variables in the same cloud environment menu. They are
the `env` keys of `settings.json` (read `settings.json` `env`; decision `agent-model-cap`),
but a session can start without them. Measured in another session: the SessionStart refresh
rewrites `settings.json` after Claude Code reads it.

* `CLAUDE_CODE_SUBAGENT_MODEL=sonnet`
* `CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL=sonnet`
* `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1`
* `PLAYWRIGHT_SKIP_BROWSER_GC=1` (decision `playwright-install-once`)
* `MAILBOX_REPO=https://github.com/shivinate7/session-mailbox.git` (decision `session-messages`)

The cloud image already has Playwright's Chromium in `/opt/pw-browsers`. Sessions set
`PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers` and `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1`. A setup
script's `playwright install` without that path downloads a second copy to the default cache,
which sessions never read. Install only when the browser that the pinned Playwright needs is
missing from `/opt/pw-browsers`. Agents never install a browser (decision
`playwright-install-once`).

Leave network access at Trusted, or add `raw.githubusercontent.com`, `github.com`, and
`codeload.github.com` to a Custom list. The setup script cannot read the environment's
variables or secrets. If this repo goes private, add it under the environment's Repositories.
install.sh also writes a `SessionStart` hook that re-runs it, so each new or resumed session
re-fetches the files. To pin cloud sessions to one commit instead of `main`, set
`CLAUDE_SETTINGS_REF=<sha>` as an environment variable. Only the `SessionStart` hook reads it.

A repo's own `.claude/settings.json` hooks, deny rules, and `SessionStart` hooks do not run in a
project's cloud thread. The docs say repo hooks run "outside a project thread" in
[Setup scripts vs. SessionStart hooks](https://code.claude.com/docs/en/cloud-environments#setup-scripts-vs-sessionstart-hooks).
So a repo that needs a `SessionStart` hook or its own deny rule for setup or safety must provision
in the environment setup script instead. A guard that must hold in project threads belongs in this
repo's guard, `hooks/guard.py`: it still loads there, while the repo's own settings did not
(measured 2026-11-03 in a project thread). Whether the `SessionStart` refresh above runs in project
threads is not measured.

## Verify the install

* `/context`, in any session, lists `~/.claude/CLAUDE.md` and the imported file under
  **Memory files**.
* `/status` shows the `shiv-stylisms` output style.
* In a cloud session, ask Claude to run `echo $CLAUDE_CODE_SUBAGENT_MODEL`. Expect `sonnet`. If
  it prints nothing, set the variable as an environment variable, as above.
* On Windows in copy mode, check `~\.claude\claude-settings-install.log` for a dated line from
  the last run.
  The line reads `settings.json=<mode> agents/lint=<mode>`. A mode is `symlink`, `copy`, or `kept`.
  `kept` means that a replace failed (a file lock, say) and nothing was copied, so the old files
  stay in place. `copy+failed` (agents/lint only) means that some files were copied and at least
  one replace failed; that file keeps its old copy. The run prints why. Run `install.ps1` again
  after you close the lock.

## How a change reaches you

Edit a file here, commit, push, open a pull request against `main`. `.github/workflows/checks.yml`
runs the guard fixture suite, its mutation test, the STE lint, and the rest of the checks
named in that file. Merge only when you say so, or under a repo grant, per CLAUDE.md.

Once merged:

* Local (symlink mode): at each session start, a `SessionStart` hook in `settings.json`
  fast-forwards local `main` and the live pin to `origin/main` when it can. It works in a
  detached child, so the session that starts it can load before the move ends. A session that
  starts after the child ends sees the move.
* Local (copy mode, Windows without Developer Mode): the `post-merge` git hook copies the
  changed files after your next `git pull` on `main`, and re-runs `install.ps1` itself if
  `install.ps1` changed.
* Cloud: the next new session runs the setup script, and each new or resumed session runs the `SessionStart` refresh hook; both pick up the change.

## The `merge` command

One command merges a pull request in any repo that has opted in. It claims record numbers
before the merge, waits for CI on the claim commit, reverts the claim if a step fails, and
then merges. The repo's own opt-in is the `merge` block of its stamp config, see "The merge
tool contract" in `actions/stamp/README.md`.

Run it from inside the repo, or name the repo's checkout with `-C PATH` (`--repo-dir PATH`), with `gh`, `git`, `node` and Python 3 on PATH:

```
merge <pr>              preview: what it would claim and merge. Presses nothing.
merge <pr> --confirm [--session NAME]   lock, claim, rebuild the records page, push, wait, merge, move the local main, clean up.
                        NAME shows in the lock to a waiting run.
merge --unlock [BRANCH] remove the merge lock on BRANCH (default: the default branch). Never checks the holder. A cloud run reads the lock first and skips one already released.
merge -C PATH <pr> ...  act in the checkout at PATH, not the one the process stands in. Works with every form above and with --lane-lint. The last -C wins.
merge <pr> --review-record --head SHA --kind K --guard yes|no [--round N:ROLE:MODEL:VERDICT ...] [--net-value V]
                        print the review record for the head SHA that was reviewed. Exit 1 when the PR's live head is another sha.
                        Posts nothing: the lane posts it as a PR comment.
merge --reviewed        one line per open PR that has a review record comment: its state (bad when the newest does not parse) and live CI.
                        Then the PRs with no record.
merge --reviewed --root DIR [--root DIR ...]
                        the same list for each repo checkout DIR, one block each, then one batch line per repo:
                        `open batch now: OWNER/NAME #a`, or `build next batch on the running head: ...`. A failed root prints unknown.
merge --touches [--run RUN_ID] [--case TEXT ...] [--file PATH ...]
                        one line per open PR that changes a named file or adds a named case in a `+` line of its patch. --run reads the
                        failing lines of that run's failed jobs for the cases (and the files of a pytest or unittest line; a run by path logs
                        `__main__.Class.name`, so its file is best-effort). No lock, no merge, no post. No match prints the clear line only
                        when every read succeeded and nothing is unknown. Unknown, exit 1, never clear. A failed read prints only `unknown`; the other causes list the matches too:
                        - a failed read;
                        - a --run whose failing lines give no case and no file at all;
                        - a --run with a failed job whose own log gives no case and no file, an empty log too (the all-jobs-passed rollup is skipped);
                        - a --run with a failed job that has a failing line naming no case or file (a unittest summary line apart);
                        - a --run with a job that is not success, skipped, neutral or failure, such as timed out, cancelled or still running;
                        - a PR with a patch-less changed file, only while a case is queried and that PR has no match.
                        --file alone is fine beside a patch-less file. An empty value is a usage error.
                        Limits. A case matches only when its text sits whole in one `+` line; a case a --run names also matches a context line. A name built from pieces or with escapes never matches.
                        A --case matches a context line only when a --run names the same case. --file finds a fix elsewhere, in guard or product code or far from the case line. --run finds it only when a failing line names its file, or the case name is on an added line or in the patch's context lines. --file is an exact path after normpath.
                        It finds no rename's previous name, no directory and no backslash path. A reason that spans lines may leave `  (note` in the case.
                        Cost: API reads only. The pull list, one call per page of 100. One files read (its pages) per open PR.
                        For --run, the jobs read, one call per page of 100, and one log read per failed job but the rollup.
merge --release-check N [N ...] [--lint N@SHA:PASS|UNKNOWN-AT-CAP|FAIL ...]
                        one line per PR before it goes to a batch: `#N PASS`, or `#N FAIL: reasons`. Checks: open, review record done at the
                        live head and unedited, lint verdict given for the live head (SHA a full lowercase 40-hex; a PASS on UNKNOWN-AT-CAP
                        reads `#N PASS (lint unknown at cap)`) and not FAIL, clean merge with the base, and a stacked base's PR in the call
                        and passing. A check that cannot run is a FAIL, so a missing line is never a pass. Exit 0 only when all PASS.
merge --dev ...         run the checkout's own tree, not origin main
```

`merge --help` lists every flag except `--dev`.

A flag prefix is an error, not the flag it starts (`merge 5 --conf` fails; write `--confirm`).

* **Launcher.** On macOS and Linux, `bin/merge` lands in `~/.claude/bin`. On Windows,
  `bin\merge.cmd` lands there too, and starts `bin\merge`. The installers put `~/.claude/bin`
  on PATH. The launcher holds no merge logic. It finds this clone through `CLAUDE_SETTINGS_DIR`,
  then the `@` line in `CLAUDE.md` under `CLAUDE_CONFIG_DIR` (default `~/.claude`). With
  neither, it clones the public repo into a temporary folder. The checkout must have `origin`
  set to `shivinate7/claude-settings`. Any other result stops before a pull request read. A
  repo's own wrapper, such as a `make merge` target, may hold the same lookup instead.
* **Another checkout.** A batch runner that merges in a second checkout runs
  `~/.claude/bin/merge -C <checkout> <pr> --confirm`, never `cd <checkout> && merge ...`. The flag
  is `-C` (or `--repo-dir`); the tool refuses a prefix such as `--repo`. It runs in the
  foreground (Bash timeout up to 600000), never with `run_in_background`. Measured 2026-11-03
  16:56 CST in a cloud auto-mode session: the foreground call matched the allow rule and ran. The
  same call in the background went to the auto-mode classifier, which refused it. In a cloud
  session the guard reads the checkout from the flag, else the `cd`, else the working directory
  (read `hooks/guard_merge.py` `_merge_target_repo`). It allows `--confirm` only when a `cs-repo`
  tag of the session's own newest `get_session` record names that checkout's repo, and no
  `set_session_tags` call follows that record (read `hooks/guard_merge.py` `repo_proof_hit`; its
  tag reader is `hooks/shared_names.py` `repo_tag_names`). Guard rule `merge-confirm-repo` (read
  `hooks/guard.py` `judge_shell`) refuses a merge that fails the check. Decision
  `merge-confirm-repo`: a cloud merge confirm acts only in a repo its own record names. A `-C`
  value that names no folder stops the merge tool before any read. A `-C` value that is no git
  checkout stops it before its lock and any pull request read (read `merge/merge.py` `main`: the
  stops say `-C names no folder` and `not in a git checkout`).
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
  you want `lint/rule_audit.py` to hold you to naming its enforcement (a guard rule, a check, a
  CI step, or `unmechanized` or `judgment` plus a reason) in `lint/rule_mechanisms.json`.
  All the guard rules, checks, and their design rationale live as comments and numbered
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
  machine without it just runs without the guards.
* **A symlink did not take on Windows.** Enable Developer Mode. Re-run `install.ps1` once, to
  replace the copies with real symlinks.
* **An existing `~/.claude/CLAUDE.md` or `settings.json` had content you wanted to keep.** Both
  installers back up the old file as `*.bak.<timestamp>` before writing. Fold anything you want
  into the repo's own `CLAUDE.md` or `settings.json`, then commit.
* **A cloud session looks stale.** Anthropic snapshots the VM for about 7 days and reuses it.
  The `SessionStart` hook the setup script installs re-fetches on every session, so this should
  self-heal. When it does not, check the environment's network access is not blocking the three
  hosts above.
* **The agent model cap needs a temporary raise.** See CLAUDE.md's Roles section and
  `opus-grant-expires` for the guarded override and its required expiry field.
* **Other repositories cannot use `actions/` after this repository becomes private.** Open
  Settings, then Actions, then General, then Access. Set "Accessible from repositories owned by
  the user".

## Shipping iOS apps

The iOS standard every app follows, and a starter for a new app, live in the `ios-apps` skill
(`skills/ios-apps/SKILL.md`). The `ios` probe of `lint/compliance_probes.py` flags a repo that drifts from it.

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

* `ios-ship testflight [CONFIG] [--app NAME]... [--export-only [--method debugging|release-testing]]` archives each app as Release and uploads it to TestFlight.
  It refuses unless the tree is clean and HEAD is `origin/main`, just fetched. All apps share one build number. It
  stops at the first app that fails, and prints one verdict line. `--export-only` skips the main check, exports the
  `.ipa` files to a folder it prints, and deletes the `.ipa` of each app that has `copy_in`.
  `--method` sets the export method: `debugging` for a development `.ipa`, `release-testing` for a release `.ipa` for registered devices. The default is
  `app-store-connect`. It is refused without `--export-only`.
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
It runs on the Duo by default, or on the iPhone 18 Pro with `--device pro`. It reuses the first booted device of that role. With none booted, it boots the role's device, runs the tests, and shuts that simulator down, also on failure, INT and TERM. With the other phone kind booted, it boots nothing and exits 1. `--hold [--for S] [-- CMD]` keeps the device for S seconds (default 300, max 900) under the same lock, with no xcodebuild.
Before that boot it applies the guard's cap itself: with 2 devices of any kind booted, it boots nothing, names them, and exits 1.
It never shuts down a simulator it did not boot. The exit code is xcodebuild's. It holds one Mac-wide lock for the whole run (`state/sim-test.lock` under the config folder). A second run waits for it, up to `SIM_TEST_LOCK_WAIT` seconds (default 300), then exits 1. It also stops a simulator whose SpringBoard crash-loops.
On its own boot it first takes the role's lease from `bin/sim-lease`, the Mac-wide simulator queue: `sim-lease take --device duo|pro [--udid]`, `give` and `status`. After the grant it checks the booted list again before it boots. A take waits for its turn and the load bars (5-minute load under 100, 1-minute load under 60; slot 2 under 60), up to `SIM_LEASE_WAIT` seconds (default 300), then exits 1. A holder that dies is reaped by pid. It does nothing off macOS or under `CI`.

## Session tiers and a roadmap record for a repo

The `project-ops` skill packages how the claude-settings project on claude.ai runs. It holds the
session roles (a coordinator that starts triage and the batch runner, then lanes), one roster,
rotation of a standing session that goes stale or breaks, and autopilot deferral. It also holds a record branch for the roadmap data, briefs and role handoff notes. Its
`scripts/scaffold.py` writes the record-branch skeleton. Its `templates/` hold the operating model,
the roster, a brief and a role handoff note. A repo adopts it only on the owner's grant. See
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
* **Why agents cannot nest.** `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1` removes the `Agent`
  tool from every agent, so only the main conversation fans out. A nested child's completion
  notice can misroute. This stalls the agent that launched it
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
