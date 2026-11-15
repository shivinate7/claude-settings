# The stale-install check reads origin on every cloud prompt

## Ruling

Ruling a (owner, 2026-11-15 11:33 CST, waiting-page item 870): accepted. The hook makes one `git ls-remote` per cloud prompt, bounded at 10 s.

Measure behind it: the read took 367 ms median and 610 ms p95 over 20 reads, taken from a cloud container through the proxy (lane stable-refresh-local). A Mac's own network is not measured.

The hook is `hooks/stale_install.py`, a UserPromptSubmit hook. It reinstalls the hooks when origin's tip moves past the installed sha. It starts a new process on every prompt. Rule `outcomes-mechanize-rules` (root CLAUDE.md) allows tracking reads on demand inside a process already running, never on every tool call. The three timer exceptions under owner ruling `stall-watch-exceptions-180a` are the stall watch, the CI wake and the daily job. This hook is none of the three, so no ruling covers it.

Cost, as the hook's module docstring states it:

- Python process starts: one per prompt, in every session, cloud or local. The `settings.json` command starts python before the hook checks for a cloud session. The note `stale-hook-python-every-prompt` (python starts in local sessions) names this gap.
- Network reads: at most one `git ls-remote` per prompt, a child git process. It reads the recorded ref only. Bounded by `CLAUDE_SETTINGS_FETCH_TIMEOUT`, default 10 s. None outside a cloud session. The origin URL comes from the source clone's `.git/config`, with no git call.
- Local git reads: none when the tip matches the record. A reinstall adds one installer run and a few local git reads in `restart_line`.
- Files written by the hook: none of its own. The installer writes the install record. Python may write its bytecode cache (`hooks/__pycache__`) on the first import of `_nowindow`; the hook's command does not turn that off.
- Timer: none. Long-lived process: none.
- Frequency: every prompt.

A cloud prompt with a current record costs one python start and one `git ls-remote`. The ruling accepts that cost. What the reinstalls it saves are worth is unmeasured.

Proof, in `hooks/test_reinstall_stale.py`:

- Read counts: `hooks/test_reinstall_stale.py::StaleInstall::test_current_makes_one_ls_remote_and_no_install` (one read, no fetch or clone). `hooks/test_reinstall_stale.py::StaleInstall::test_second_turn_after_reinstall_is_silent` (the next prompt makes one read and no install). `hooks/test_reinstall_stale.py::StaleInstall::test_behind_origin_reinstalls_once_and_names_both_shas` (one read, one installer run). `hooks/test_reinstall_stale.py::StaleInstall::test_ls_remote_timeout_reports_unknown_and_installs_nothing` and `hooks/test_reinstall_stale.py::StaleInstall::test_ls_remote_failure_reports_unknown_and_installs_nothing` (one read, one unknown line, no install).
- No git outside a cloud session: `hooks/test_reinstall_stale.py::StaleInstall::test_not_cloud_is_silent_with_no_git_call`.
- Cost text: `hooks/test_reinstall_stale.py::HookFile::test_docstring_states_the_cost` checks that the docstring names process starts, network reads, the per-turn frequency, no timer and no long-lived process. It checks the words, not the numbers.
- Not pinned (unmeasured): the python start count, since no case counts starts. The `git show` reads of a reinstall. The `git diff` read is pinned at one by `hooks/test_reinstall_stale.py::StaleInstall::test_failed_local_diff_prints_restart_unknown_line`.

Retry backoff (owner, 2026-11-15 11:33 CST, waiting-page item 871 b; closes debt `reinstall-no-backoff`):

- Where it is remembered: `<config dir>/.claude-settings-install-attempt.json`, `{tip, epoch}`. The installer writes it at the start of a hook-driven cloud run, before it takes the install lock, so a run that fails on the lock leaves it too (`write_attempt_stamp` in `install.sh`, told the tip by the hook through `CS_STALE_TIP`). It removes it only when the record it writes is at that tip. The hook writes nothing.
- A fresh stamp for the current tip means an install failed, timed out, fell short of the tip, or is still running. The hook then runs no installer and prints "reinstall skipped (install started at <tip7> not finished, retry in <N> s)". A new tip, an older stamp, an unreadable stamp or a stamp dated in the future (the clock stepped back) runs the installer as before, so no stamp holds a skip past the backoff. A later success clears the stamp.
- Length: 900 s, `CLAUDE_SETTINGS_REINSTALL_BACKOFF` replaces it. The worst failed run is about 75 s, so one retry per 15 min caps the retry at under 10% of the time, against every prompt before. The number is a choice. How long real failures last and how often prompts come are unmeasured. The length is fixed, not doubling.
- Cost: no timer, no long-lived process, no file written by the hook. A skipped prompt still makes the one `git ls-remote`. The installer writes one small file per hook-driven run.
- Failed first install: no record is written, so no retry and no read; the hook prints `install freshness unknown (no install record)` on each prompt until a record exists.
- Pinned: `hooks/test_reinstall_stale.py::StaleInstallBackoff` (skip within the backoff, run after it, a new tip, a garbled stamp, the env override, the stamp kept after a failure, a timeout and a short record, cleared on success, `CS_STALE_TIP` passed to the installer, no file written on a skipped prompt). The installer side runs for real in `hooks/test_install_src.sh` cases `stale_stamp1` to `stale_stamp7`. A lock wait is pinned by `stale_stamp8` and a future stamp by `test_future_stamp_an_hour_ahead_reinstalls`. Not pinned: a retry exactly at the backoff, and a lock held by a live install that later finishes.

Kind: process
Home: hooks/stale_install.py
