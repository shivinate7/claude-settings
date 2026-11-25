# Pace numbers two and three come from the session transcript

## The ruling

Numbers two and three of the pace-numbers rule (`reports-batch-pace-numbers`, root CLAUDE.md) come from the session transcript. `lint/pace_numbers.py` reads the transcript on demand, at report time. It prints two lines:

```
agents run: N, most at once: M[ (P still running)]
minutes with no agent running: K
```

## Why

Owner, 00:50 CST Nov 25 2026, on the pace line "minutes with no lane running: unknown" (owner task fb-0050-2, the pace-gap task in `docs/todo.md`), word for word: "how is stuff like this unknown? seems like a gap?"

The gap: git, GitHub and guard.log hold no agent start or end. So number three was always "unknown", and number two had no source for the most running at once. The session transcript holds each Agent or Task spawn and each task notice, with its time.

## What counts as a span

- A span opens at the time of an Agent or Task tool_use. The launch result gives the agent id (`toolUseResult.agentId`). A spawn whose result is an error, or has no agent id, opens no span.
- A span closes at the first task notice for that agent id with a status in the reader's status list (`ENDING_STATUSES`): completed, failed or killed.
- A notice counts only in a queue-operation's content or a user record's text. A notice in a tool_result, a blob copy or an attachment does not count.
- A notice whose task id matches no agent start is ignored. A background shell command is one case.
- A SendMessage to the agent after its span closed opens a new span at the send's time. A send while the span is open changes nothing. A failed send changes nothing. A second end notice while the span is closed changes nothing.
- Spans are clipped to the window. A span with no end notice runs to the window end and counts as still running.

## What the lines mean

- N counts distinct agents with a span in the window. A resumed agent counts once.
- M is the most spans open at one moment, clipped to the window.
- P counts the agents with no end notice in the file. It is appended to the first line only when P is above 0.
- K is the window length less the time that any span covers, floored to whole minutes.
- A window with records and no agent prints `agents run: 0, most at once: 0`, and K is the whole window.
- `unknown: <reason>` prints, and the exit code is 0, for an unreadable file, an empty file, or a window with no record in it.
- A window time with no UTC offset is a usage error (argparse exit 2). It prints no `unknown:` line.

## Picks

These are the consultant session's picks. No owner ruling covers them.

- N counts agents, not spans, so a resumed agent is one.
- K is floored, not rounded.
- The lines use the glossary's term "agent". The rule's old "lane" label named a unit the transcript cannot count, since an agent is never a lane (GLOSSARY.md).

## Cost

Cost: one python start per merge report, on demand (unmeasured: no test counts starts). No file is written (unmeasured). Measured once on a builder run, Nov 25 2026: 0.18 s wall on a session transcript of about 14,000 records (not pinned: no test holds the figure). The named reader is the session's merge report. No test proves this cost yet (not pinned).

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
- PaceNumbersFixtureControlTests.test_fixture_carriers_parse_through_the_shared_readers (the fixture control)

## Limits

- The reader counts agents of one session's transcript. A lane run as another session is not seen.
- The reader gives the idle minutes only. The reason for them is still written by the session.
- The cloud path is not built. A cloud session's transcript is not read.
- No CI step (`.github/workflows/checks.yml`) runs `lint/test_pace_numbers.py` yet.

Kind: process
Home: lint/pace_numbers.py
