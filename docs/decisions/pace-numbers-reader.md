# Pace numbers two and three come from the session transcript

## The ruling

Numbers two and three of the pace-numbers rule (`reports-batch-pace-numbers`, root CLAUDE.md) come from the session transcript. `lint/pace_numbers.py` reads the transcript on demand, at report time. It prints two lines:

```
agents run: N, most at once: M[ (P still running)]
minutes with no agent running: K[ (note)][ (note)]
```

The notes are defined under "The covered span".

## Why

Owner, 00:50 CST Nov 25 2026, on the pace line "minutes with no lane running: unknown" (owner task fb-0050-2, the pace-gap task in `docs/todo.md`), word for word: "how is stuff like this unknown? seems like a gap?"

Git, GitHub and guard.log hold no agent start or end, so numbers two and three had no source there. The session transcript holds each Agent or Task spawn and each task notice, with its time.

## What counts as a span

- A span opens at an Agent or Task tool_use (`SPAWN_TOOLS`). Its launch result gives the agent id (`toolUseResult.agentId`). A spawn whose result is an error, or has no agent id, opens no span.
- A background agent's launch result has `isAsync` true. Its span closes at the earliest copy of its first task notice with status completed, failed or killed (`ENDING_STATUSES`). Failed and killed close it the same as completed.
- A foreground agent's span closes at its launch result's time. That result has the agent id and no `isAsync` true.
- A notice counts only in a queue-operation's content, a user record's text, or a queued_command attachment's prompt. Copies of one notice are one stop, at the earliest copy. A notice in a tool_result, a blob copy, or a compaction summary (a user record with `isCompactSummary`) does not count.
- A notice whose task id matches no agent start is ignored, as is one with no ending status. A background shell command is one case.
- A SendMessage to the agent after its span closed opens a new span at the send's time. A send while the span is open changes nothing. A send that failed (`is_error` true, or `toolUseResult.success` false) changes nothing.
- An end notice after a span closed, with no send since, moves the close to that stop. The span then runs to the later stop.

## The covered span

The covered span runs from the transcript's first to its last timestamped record. The window is clipped to it before any count: N, M, P and K use only the part inside it.

- Window time before the first record or after the last is not counted as idle. The idle line says so: `transcript covers from <ISO> on; <minutes> min before it not counted`, or `transcript covers until <ISO>; <minutes> min after it not counted`. `<ISO>` is the span edge in the UTC offset of the window's start. A note prints only for an overhang of one minute or more. `<minutes>` is the floor of the overhang.
- A window with no minute in common with the covered span, touching at one instant included, prints `unknown:`.

## What the lines mean

- N counts distinct agents with a span in the window. A resumed agent counts once.
- M is the most spans open at one moment. Ends sort before starts at one instant, so back-to-back spans do not overlap.
- P counts agents whose last span has no end notice anywhere in the file and that overlaps the window. It does not count spans open at the window's end: an end notice after the window end clips the span and does not make the agent still running. P appears on the first line only when above 0.
- K is the covered part of the window, less the time any span covers, floored to whole minutes. A window with records and no agent prints `agents run: 0, most at once: 0`, and K is the whole covered part.
- Each note sits in its own parenthesis on the idle line, so both can print.
- `unknown: <reason>` prints, and the exit code is 0, for an unreadable file, a file that is not valid UTF-8, an empty file, a window with no record in it, or a window with no minute in the covered span.
- A window time with no UTC offset is an argument error (argparse exit 2). It prints no number and no `unknown:` line.

## Picks

These are the consultant session's picks. No owner ruling covers them.

- N counts agents, not spans, so a resumed agent is one.
- K is floored, not rounded.
- The lines use the glossary's term "agent". The transcript cannot count lanes: an agent is never a lane (GLOSSARY.md).

## Cost

Cost: one python start per merge report, on demand (unmeasured: no test counts starts). No file is written (unmeasured). Measured Nov 25 2026: 0.31 s wall, one run through `verdict`, on a session transcript of 16,061 records (`wc -l`) (not pinned: no test holds the figure). The named reader is the session's merge report. No test proves this cost yet (not pinned).

## Checks

`lint/test_pace_numbers.py` runs the reader as a subprocess and compares its two lines. Its cases:

- test_overlapping_agents_give_most_at_once_two_and_trailing_idle
- test_back_to_back_agents_with_a_gap_count_the_gap_as_idle
- test_task_named_spawn_starts_a_span_like_agent
- test_spans_are_clipped_at_start_and_end_and_outside_spans_are_not_counted
- test_agent_with_no_end_notice_runs_to_end_and_is_marked_still_running
- test_shell_command_notice_is_ignored
- test_resumed_agent_reopens_only_after_a_send_that_follows_its_end
- test_refused_spawn_starts_no_span
- test_quoted_notice_and_comment_openers_in_text_do_not_end_or_break_parsing
- test_unreadable_file_prints_one_unknown_line
- test_empty_file_prints_one_unknown_line
- test_window_with_no_record_in_it_prints_one_unknown_line
- test_window_with_records_but_no_agent_prints_zero_agents_and_the_whole_window_idle
- test_window_starting_before_the_first_record_counts_only_from_the_first_record
- test_window_ending_after_the_last_record_counts_only_up_to_it
- test_window_inside_the_covered_span_prints_the_plain_line
- test_window_touching_the_covered_span_prints_one_unknown_line
- test_window_clear_of_the_covered_span_prints_one_unknown_line
- test_failed_notice_ends_a_span
- test_killed_notice_ends_a_span
- test_send_that_failed_with_is_error_does_not_reopen_a_span
- test_send_that_failed_with_success_false_does_not_reopen_a_span
- test_end_notice_after_end_clips_the_span_and_is_not_still_running
- test_idle_minutes_are_floored_not_rounded_up
- test_window_time_without_a_utc_offset_exits_with_an_argument_error
- test_foreground_agent_span_ends_at_its_result
- test_second_end_notice_without_a_send_extends_the_span
- test_attachment_only_notice_ends_a_span
- test_notice_in_queue_user_and_attachment_counts_once
- test_compaction_summary_quote_does_not_end_a_resumed_span (fails when summaries count)
- test_invalid_utf8_at_the_end_prints_one_unknown_line (bytes at the end only)
- test_overhang_under_one_minute_prints_no_note
- test_overhang_of_61_seconds_prints_one_minute_note
- PaceNumbersFixtureControlTests.test_fixture_carriers_parse_through_the_shared_readers (the fixture control)

## Limits

- The reader counts agents of one session's transcript. A lane run as another session is not seen.
- Agents started by a Workflow call are not seen. The spawn tools are `Agent` and `Task` only (`SPAWN_TOOLS`). The glossary's `agent` term counts them.
- The foreground-agent shape is not in the one real transcript measured, where all launches were async. Its span rule rests on `test_foreground_agent_span_ends_at_its_result` alone.
- A line that is not valid JSON is skipped without a note.
- The reader gives the idle minutes only. The reason for them is still written by the session.
- The cloud path is not built. A cloud session's transcript is not read.
- No CI step (`.github/workflows/checks.yml`) runs `lint/test_pace_numbers.py` yet.
- No case proves that no file is written. That case is owed.

Kind: process
Home: lint/pace_numbers.py
