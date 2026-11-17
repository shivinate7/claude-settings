# The stale-install check reads no origin on a cloud prompt

## Ruling

A cloud prompt makes no network call (owner, 2026-11-17 09:34 CST).

The owner's words: "none of those are scenarios to guard against on what gets past the merge tool so that cheaper approach will work best" (09:34 CST; the event triggers, 09:30 CST). The install refreshes on two events: a session start or resume, and a move of the local `origin/<record ref>` ref that a prompt sees. Decision of the owner's consultant, 2026-11-17 09:57 CST: the merge-notice trigger (an inbox message "main moved to <sha>; refresh") is dropped, because nothing sends it and the merged mid-session reinstall (pull request 3487, the hook this one rewrites) already reinstalls when main's hooks move. No lookup of origin runs on any prompt, and no fallback timer asks origin on a clock.

The hook is `hooks/stale_install.py`, a UserPromptSubmit hook. It compares the install record's sha with the record's source clone's own local ref. A trigger starts the recorded installer once, which fetches. The pin (a detached checkout that holds `merge/install_from_main.sh`) runs that script once per new head and prints how many commits it is behind the ref it read. That ref is `origin/<record ref>`, or local main when origin has no such ref, which is where the script pins then. A reinstall also runs once per head. A later prompt on a head the record still does not cover prints `install still stale` and runs nothing. The clone the config dir's `CLAUDE.md` points at gets one line when it is behind, once per head. A missing local ref, record or source prints `install freshness unknown`, never "current". A linked worktree pin reads like a clone: git follows its common dir, so its verdict is real.

Rule `outcomes-mechanize-rules` (root CLAUDE.md) allows tracking reads on demand inside a process already running, never on every tool call. The hook still starts one process per prompt, but its reads are local files and git objects. The three timer exceptions under owner ruling `stall-watch-exceptions-180a` do not cover it, and it needs none: it has no timer.

Cost, as the hook's module docstring states it:

- Python process starts: one per prompt, in every session, cloud or local. The `settings.json` command starts python before the hook checks for a cloud session. The note `stale-hook-python-every-prompt` (python starts in local sessions) names this gap.
- Network calls per prompt: 0. The installer a trigger starts fetches origin; the hook does not.
- Local reads per cloud prompt: the install record, the config dir's `CLAUDE.md`, and git reads in a clone. At most 4 with no trigger (the ref, merge-base, and the shared clone's ref and count). At most 8 on a trigger prompt: those four, symbolic-ref, then two counts for a pin, or one diff and two `settings.json` reads for a reinstall. A pin with no origin ref adds one read of local main. None outside a cloud session. A trigger adds one installer run. Counted from the code; no case pins the counts.
- Files written by the hook: the seen file, `.claude-settings-refresh-seen` in the config dir, only when a reinstall, a pin refresh or a clone flag acts on a new head. It keeps the last 20 heads. The installer writes the install record.
- Timer: none. Long-lived process: none.
- Frequency: every prompt.

Whether the reinstalls it saves are worth one python start per prompt is unmeasured.

Session start and resume run the installer's own refresh, so that trigger needs nothing in this hook.

Proof, in `hooks/test_reinstall_stale.py`:

- No lookup on a prompt: `StaleInstall::test_prompt_with_no_trigger_reads_no_origin`, `test_hanging_origin_is_not_read_on_a_prompt`, `test_failing_origin_is_not_read_on_a_prompt`, `test_current_prompt_makes_no_network_read_and_no_install`, `test_second_turn_after_reinstall_is_silent` and `test_shared_check_reads_no_origin_on_a_prompt`.
- The trigger: `test_local_ref_move_triggers_the_refresh_with_no_lookup`.
- Once per head, pin and shared clone: `test_behind_pin_refreshes_once_per_head`, `test_behind_pin_stale_line_names_its_commit_count`, `test_behind_shared_clone_is_flagged_with_its_commit_count`.
- Linked pin: `test_linked_pin_current_is_silent_with_no_read` and `test_linked_pin_behind_gets_a_verdict_not_unknown`. A missing local ref is unknown: `test_unknown_ref_reports_unknown_without_a_read`.
- No git outside a cloud session: `test_not_cloud_is_silent_with_no_git_call`.
- Cost text: `HookFile::test_docstring_states_the_cost` checks that the docstring names process starts, network calls per prompt, the per-prompt frequency, no timer and no long-lived process. It checks the words, not the numbers.
- Not pinned (unmeasured): the python start count, since no case counts starts. The claim that the hook writes no file but the seen file. The git read counts of a prompt with a trigger. The `git diff` read is pinned at one by `test_failed_local_diff_prints_restart_unknown_line`.

Retry cost, debt `reinstall-no-backoff` (the hook reruns the installer on each prompt, with no backoff). A reinstall and a pin refresh now run once per head, so a failed run is not retried on later prompts for that head:

- A failed install, an installer that exits 0 short of the target, or a blocked pin move. The head is marked tried before the run. Each later prompt on that head prints `install still stale` and runs nothing. A new head runs once again.
- Failed first install. No record is written, so there is no retry. The hook prints `install freshness unknown (no install record)` on each prompt until a record exists.
- Pinned: `test_failed_reinstall_runs_once_per_head_and_later_prompts_stay_stale`, `test_pin_move_blocked_by_tracked_changes_stays_stale_on_later_prompts` and `test_installer_failure_after_the_pin_moved_stays_stale_on_later_prompts`.

Kind: process
Home: hooks/stale_install.py
