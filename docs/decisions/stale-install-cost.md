# The stale-install check reads origin on every prompt

## Ruling

Open: is one `git ls-remote` of origin per prompt, cloud or local, acceptable? Not ruled. Filed on waiting-page item 870, no owner answer yet.

The hook is `hooks/stale_install.py`, a UserPromptSubmit hook. It reinstalls the hooks when origin's tip moves past the installed sha. It starts a new process on every prompt. Rule `outcomes-mechanize-rules` (root CLAUDE.md) allows tracking reads on demand inside a process already running, never on every tool call. The three timer exceptions under owner ruling `stall-watch-exceptions-180a` are the stall watch, the CI wake and the daily job. This hook is none of the three, so no ruling covers it.

Cost, as the hook's module docstring states it:

- Python process starts: one per prompt, in every session, cloud or local. The `settings.json` command starts python before the hook reads the install record. The note `stale-hook-python-every-prompt` (python starts in local sessions) names this gap.
- Network reads: at most one `git ls-remote` per prompt, a child git process. It reads the recorded ref only. Bounded by `CLAUDE_SETTINGS_FETCH_TIMEOUT`, default 10 s. A local session with no install record makes none. The origin URL comes from the source clone's `.git/config`, with no git call.
- Local git reads: none when the tip matches the record. A reinstall adds one installer run and a few local git reads in `restart_line`.
- Files written by the hook: none. The installer writes the install record.
- Timer: none. Long-lived process: none.
- Frequency: every prompt.

A prompt with a current record costs one python start and one `git ls-remote`. Whether the reinstalls it saves are worth that is unmeasured.

Measured, 20 sequential `git ls-remote` reads of this repo's `refs/heads/stable` (2026-11-15 12:00 CST, one cloud container through the agent proxy, 0 failures): median 367 ms, p95 610 ms. A Mac's own network was not measured. A local reinstall (the clone's `merge/install_from_main.sh`, narrow mode) took 17 s in a temp home with no `package-lock.json`, so the `npm ci` step is not in that figure.

Proof, in `hooks/test_reinstall_stale.py`:

- Read counts: `hooks/test_reinstall_stale.py::StaleInstall::test_current_makes_one_ls_remote_and_no_install` (one read, no fetch or clone). `hooks/test_reinstall_stale.py::StaleInstall::test_second_turn_after_reinstall_is_silent` (the next prompt makes one read and no install). `hooks/test_reinstall_stale.py::StaleInstall::test_behind_origin_reinstalls_once_and_names_both_shas` (one read, one installer run). `hooks/test_reinstall_stale.py::StaleInstall::test_ls_remote_timeout_reports_unknown_and_installs_nothing` and `hooks/test_reinstall_stale.py::StaleInstall::test_ls_remote_failure_reports_unknown_and_installs_nothing` (one read, one unknown line, no install).
- No git read for a local session with no install record: `hooks/test_reinstall_stale.py::StaleInstall::test_local_without_record_is_silent_with_no_git_call`. One read for a local session with a current record: `hooks/test_reinstall_stale.py::LocalRefresh::test_local_current_makes_one_ls_remote_read`.
- Cost text: `hooks/test_reinstall_stale.py::HookFile::test_docstring_states_the_cost` checks that the docstring names process starts, network reads, the per-turn frequency, no timer and no long-lived process. It checks the words, not the numbers.
- No file written by the hook: `hooks/test_reinstall_stale.py::NoWrites` snapshots the config dir before and after a current local check, a failing cloud check and a failing local check, and finds no change.
- Not pinned (unmeasured): the python start count, since no case counts starts. The `git show` reads of a reinstall. The `git diff` read is pinned at one by `hooks/test_reinstall_stale.py::StaleInstall::test_failed_local_diff_prints_restart_unknown_line`.

Retry cost, debt `reinstall-no-backoff` (the hook reruns the installer on each prompt, with no backoff):

- Record behind the tip after a failed install. The installer writes the record only after a clean install, so the older record stays. Each prompt then runs one `git ls-remote` and one installer run. The debt holds the time.
- Installer exits 0, but its files stay short of the tip. The record is rewritten at the short sha, and the hook prints "reinstall did not reach". The next prompt runs the same retry.
- Failed first install. No record is written, so there is no retry and no read. A cloud session prints `install freshness unknown (no install record)` on each prompt until a record exists. A local session with no record prints nothing.
- Pinned: one installer run inside one prompt, `hooks/test_reinstall_stale.py::StaleInstall::test_installer_exit_3_prints_one_failure_line_and_runs_once`. Not pinned: the retry across prompts (unmeasured).

Kind: process
Home: hooks/stale_install.py
