# The stale-install check reads no origin on a prompt

## Ruling

A cloud prompt makes no network call (owner, 2026-11-17 09:34 CST; the event triggers, 09:30 CST). The install refreshes on two events: a session start or resume, and a move of the local `origin/<record ref>` ref that a prompt sees. The merge-notice trigger (an inbox message that says main moved) is dropped (consultant decision, 2026-11-17 09:57 CST): nothing sends it, and the mid-session reinstall (pull request 3487) already reinstalls when main's hooks move. No lookup of origin runs on any prompt, and no fallback timer asks origin on a clock.

Local sessions (owner, 2026-11-23 19:41-19:42 CST, consultant's chat): a local session refreshes its live pin as a cloud session refreshes its install, at a session start or resume and when the local `origin/stable` ref has moved. This holds on the Mac and on Windows. A prompt makes no network call in a local session either.

The hook is `hooks/stale_install.py`, a UserPromptSubmit hook. It compares the install record's sha with the record's source clone's own local ref. A trigger starts the recorded installer once, which fetches. For a pin (a detached checkout that holds `merge/install_from_main.sh`), a trigger runs that script once per new head instead, and the hook prints how many commits the pin is behind the ref it read. That ref is `origin/<record ref>`, or local main when origin has no such ref, which is where the script pins then. A reinstall also runs once per head. A later prompt on a head the record still does not cover prints `install still stale` and runs nothing. The clone the config dir's `CLAUDE.md` points at gets one line when it is behind, once per head. A missing local ref or source prints `install freshness unknown`, never "current". A linked worktree pin reads like a clone: git follows its common dir, so its verdict is real.

A local session has no record, because install.sh writes one only with `--cloud`. The hook reads the pin it lives in instead: the pin's HEAD is the record, with ref `stable`. The hook resolves its own file's real path first (`pin_record`), so a hook run through a symlink finds the same pin as a direct run. The pin is either `<clone>-live` or the `<clone>-live-<12 hex>` worktree that link points to. A hook in no pin prints nothing and makes no git read. A local session never runs `install.sh --cloud` and never reinstalls a source that is not a pin. A local session with a record reads it as a cloud session does.

Session start and resume. In a cloud session, the installer's own refresh runs at session start and resume, so that trigger needs nothing in this hook. In a local session, the `startup|resume` SessionStart entry in `settings.json` (it exits in a cloud session) fetches origin, fast-forwards local main to origin/main, and runs `merge/install_from_main.sh` when the pin is not at origin's `stable`. Its matcher names no other event, so compact, clear and fork get no refresh from it. This hook covers those: it runs on every prompt, so a local refresh also runs mid-session, after a compaction, clear or fork, when the local `origin/stable` ref has moved. This hook does not run at session start.

Windows. On Windows the refresh starts Git Bash found by `find_git_bash` (`hooks/git_bash.py`), never a bare `bash`. That is the Windows start path, and it is unproven (see Unproven on Windows).

A refresh changes hooks under running sessions. A reinstall prints a restart line for each changed path a new session must read again: `CLAUDE.md`, `output-styles/`, and the `settings.json` keys `model` and `effortLevel`. A pin refresh prints none.

Install lock (pin refresh only). While another install holds a fresh `<config dir>/.claude-settings-install.lock`, a pin refresh prints nothing, runs nothing and leaves its head unseen, so a later prompt checks again. A lock older than `LOCK_MAX_AGE` (600 s) is ignored. A refresh that times out behind another install's lock acts the same way.

Once per head. The file `<config dir>/.claude-settings-refresh-seen` holds the last 20 heads that a reinstall, a pin refresh or a clone flag acted on. A pin refresh marks its head seen when it ends, success or failure. A cloud reinstall marks its head before it runs. A hook cut short before a refresh ends leaves its head unseen, so the next prompt tries it again.

Code homes. The pin's names (`LIVE_PIN_SUFFIX`, `PIN_TREE`, `PIN_SCRIPT`) live in `hooks/shared_names.py`, the one home that `hooks/guard_frozen.py` and `hooks/stale_install.py` import. The Windows tree stop is `taskkill_tree` in `hooks/_nowindow.py`, the one home that `hooks/stale_install.py` and `hooks/mail.py` call.

Rule `outcomes-mechanize-rules` (root CLAUDE.md) allows tracking reads on demand inside a process already running, never on every tool call. The hook still starts one process per prompt, but its reads are local files and git objects. The three timer exceptions under owner ruling `stall-watch-exceptions-180a` do not cover it, and it needs none: it has no timer.

Cost, as the hook's module docstring states it:

- Python process starts: one per prompt, in every session, cloud or local. The `settings.json` command starts python before the hook checks for a cloud session. The note `stale-hook-python-every-prompt` (python starts in local sessions) names this gap.
- Network calls per prompt: 0. The installer or pin refresh a trigger starts fetches origin; the hook does not.
- Git reads per cloud prompt: the install record, the config dir's `CLAUDE.md`, and git reads in a clone. At most 4 with no trigger (the ref, merge-base, and the shared clone's ref and count). At most 8 on a trigger prompt: those four, symbolic-ref, then two counts for a pin, or one diff and two `settings.json` reads for a reinstall. A pin with no origin ref adds one read of local main. A trigger adds one installer run. Counted from the code. Cases pin the no-trigger bound. No case pins the trigger count.
- Git reads per local prompt with a record: the same counts as a cloud prompt.
- Git reads per local prompt with no record, in a pin: 2 when the pin is current (its HEAD and `origin/stable`). 4 when it is behind a head already seen, where no refresh runs (adds the ancestry check and the detached-HEAD check). Pinned by `LocalSession::test_local_symlinked_hook_current_pin_is_silent_and_makes_two_git_calls` and `LocalSession::test_local_symlinked_hook_seen_head_stays_stale_and_makes_four_git_calls`. Neither adds a shared-clone read. Counted from the code, not pinned: a second clone named in the config's `CLAUDE.md` adds up to 2 reads, and a trigger prompt makes at most 9, that clone's 2 included.
- Git reads per local prompt with no record, in no pin: 0. Pinned for a hook linked from a folder in no pin (`LocalSession::test_local_symlinked_hook_outside_every_pin_is_silent_and_makes_no_git_call`), not for a direct run.
- Files written by the hook: the seen file, `.claude-settings-refresh-seen` in the config dir, only when a reinstall, a pin refresh or a clone flag acts on a new head. It keeps the last 20 heads. The installer writes the install record.
- Timer: none. Long-lived process: none.
- Frequency: every prompt.

Whether the reinstalls it saves are worth one python start per prompt is unmeasured.

Proof, in `hooks/test_reinstall_stale.py`:

- No lookup on a prompt: `StaleInstall::test_prompt_with_no_trigger_reads_no_origin`, `test_hanging_origin_is_not_read_on_a_prompt`, `test_failing_origin_is_not_read_on_a_prompt`, `test_current_prompt_makes_no_network_read_and_no_install`, `test_second_turn_after_reinstall_is_silent` and `test_shared_check_reads_no_origin_on_a_prompt`. Local: `LocalSession::test_local_no_trigger_prompt_reads_no_origin_and_runs_nothing`.
- The trigger: `test_local_ref_move_triggers_the_refresh_with_no_lookup`. Local: `LocalSession::test_local_trigger_refreshes_the_pin_once_and_prints_the_cloud_line`.
- Once per head, pin and shared clone: `test_behind_pin_refreshes_once_per_head`, `test_behind_pin_stale_line_names_its_commit_count`, `test_behind_shared_clone_is_flagged_with_its_commit_count`. Local: `LocalSession::test_local_second_prompt_on_the_same_head_runs_nothing_and_a_new_head_refreshes_again`.
- Install lock, pin refresh only: `LocalSession::test_local_fresh_lock_held_by_another_install_stays_silent_and_unseen`, `LocalSession::test_local_lock_older_than_the_age_limit_is_ignored_and_the_refresh_runs`, `LocalSession::test_local_pin_refresh_timed_out_behind_another_install_prints_nothing_and_stays_unseen`.
- Seen mark, pin refresh: `LocalSession::test_local_seen_entry_is_written_only_after_the_refresh_ends`, `LocalSession::test_local_failed_refresh_marks_its_head_seen_only_after_it_ends_and_later_prompts_say_stale`, `LocalSession::test_local_failed_pin_refresh_prints_its_line_and_is_not_retried_on_the_same_head`.
- Windows tree stop of a timed-out pin refresh: `LocalSession::test_local_windows_stop_of_a_timed_out_pin_refresh_uses_the_shared_taskkill_argv`. It pins the argv through a shim, not a real taskkill.
- Linked pin: `test_linked_pin_current_is_silent_with_no_read` and `test_linked_pin_behind_gets_a_verdict_not_unknown`. Local: `LocalSession::test_local_current_linked_pin_is_silent_with_no_read` and `test_local_linked_pin_refresh_starts_through_the_symlink`.
- Outside a cloud session: `StaleInstall::test_not_cloud_pin_behind_refreshes_once_with_exit_zero_and_no_lookup`, and the `LocalSession` cases. Every other local case writes a record. The no-record cases are `LocalSession::test_local_pin_hook_run_directly_refreshes_the_pin_once_with_no_record` and the four `LocalSession::test_local_symlinked_hook_*` cases.
- A missing local ref is unknown: `test_unknown_ref_reports_unknown_without_a_read`. Local: `LocalSession::test_local_unknown_ref_reads_unknown_with_no_read_of_origin`.
- The stop path where os.killpg and signal.SIGKILL do not exist: `PosixOnlyStop::test_timeout_without_killpg_or_sigkill_prints_the_timeout_line`. It runs on POSIX with both removed.
- Cost text: `HookFile::test_docstring_states_the_cost` checks that the docstring names process starts, network calls per prompt, the per-prompt frequency, no timer and no long-lived process. It checks the words, not the numbers.
- Cost cases: `test_no_trigger_prompt_writes_no_seen_file`, `test_no_trigger_prompt_makes_at_most_four_git_calls_and_no_network_read` and `test_seen_file_keeps_the_last_twenty_heads`. A record past the target counts as reached: `test_record_past_the_target_reads_as_reinstalled`. A record ahead of the local ref is silent: `test_record_ahead_of_the_local_ref_is_silent_with_no_install`.
- Not pinned (unmeasured): the python start count, since no case counts starts. The git read count of a prompt with a trigger, cloud or local, and a local pin's shared-clone reads. The `git diff` read is pinned at one by `test_failed_local_diff_prints_restart_unknown_line`.

Unproven on Windows:

- Git Bash found and started: `find_git_bash` (`hooks/git_bash.py`) returns Git Bash on Windows, never the System32 WSL launcher; off Windows, `bash` on PATH. With none on Windows, `run_script` prints one line, `reinstall not run (Git Bash not found)` or `pin refresh not run (Git Bash not found)`, and starts nothing. No case pins that line.
- Forward-slash script path: `script_path` gives the pin script a forward-slash path on Windows.
- `taskkill /T /F` ends the installer tree. The install lock then stays until its age limit clears it.
- Hand-off to install.ps1: `merge/install_from_main.sh` runs install.ps1 under MINGW, MSYS and CYGWIN. A pin refresh on Windows ends there.
- Follow-on, named and not built: a Windows-capable CI shard for `hooks/test_reinstall_stale.py`.

Retry cost. A reinstall and a pin refresh run once per head, so a failed run is not retried on later prompts for that head:

- A failed install, an installer that exits 0 short of the target, a blocked pin move, or no Git Bash on Windows. A cloud reinstall marks its head before the run; a pin refresh marks its head when the refresh ends. Each later prompt on that head prints `install still stale` and runs nothing. A new head runs once again. A pin refresh that times out behind another install's lock is the exception: it prints nothing and leaves its head unseen (see Install lock).
- Failed first install. No record is written, so there is no retry. In a cloud session the hook prints `install freshness unknown (no install record)` on each prompt until a record exists. A local session with no record reads its pin instead, and prints nothing when it lives in no pin.
- Pinned: `test_failed_reinstall_runs_once_per_head_and_later_prompts_stay_stale`, `test_pin_move_blocked_by_tracked_changes_stays_stale_on_later_prompts` and `test_installer_failure_after_the_pin_moved_stays_stale_on_later_prompts`. Local: `LocalSession::test_local_failed_pin_refresh_prints_its_line_and_is_not_retried_on_the_same_head`.

Kind: process
Home: hooks/stale_install.py
