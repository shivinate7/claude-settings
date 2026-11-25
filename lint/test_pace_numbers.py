#!/usr/bin/env python3
"""Fixture tests for lint/pace_numbers.py, the reader of pace numbers two and three.

Form under test: `python3 lint/pace_numbers.py --transcript FILE --between START END`, aware ISO times.
- A span starts at an Agent (or Task) tool_use record's timestamp. A refused spawn (a tool_result with
  is_error and no toolUseResult.agentId) starts no span.
- The agent's task-id is the agentId in its launch result (toolUseResult.agentId).
- A foreground launch (a result with agentId and no isAsync) ends its span at the result's time.
- A span ends at the first task-notification with that task-id and status completed, failed or killed. A
  notice counts as text in a user record's content, a queue-operation's content or a queued_command attachment's
  prompt. Text in a tool_result, a blob copy (no timestamp) or a compaction summary (a user record with
  isCompactSummary) never counts. One notice logged in several carriers is one notice, and its edge is its first copy.
- A notice whose task-id matches no spawn (a background shell command) is ignored.
- A SendMessage to the agent's id, sent after its span closed, reopens the span at the send's time.
  A send while the span is open changes nothing. A send whose result failed (is_error, or toolUseResult
  success false) reopens nothing. A distinct end notice with no send since the span closed extends the span to
  that notice's first copy.
- A span is clipped to the window. An agent with no end notice in the file runs to END. An end notice
  after END clips the span to END and does not make the agent still running.
- A window time with no UTC offset exits 2 with an argument error that names the window time, and prints
  no number.
- Output: `agents run: N, most at once: M`, with ` (P still running)` appended when P > 0, then
  `minutes with no agent running: K`, with a coverage note appended to the second line when the window reaches
  past the covered span (below). N counts distinct agents. K is the floor of idle seconds / 60.
- The covered span runs from the earliest to the latest timestamped record. A window minute outside it is not
  idle. The second line then ends with ` (transcript covers from <ISO> on; <N> min before it not counted)` when
  the window starts before the span, or ` (transcript covers until <ISO>; <N> min after it not counted)` when it
  ends after it. <ISO> is the span's edge in the window's offset, such as 2026-11-25T04:00:00-06:00. A coverage
  note prints only for an overhang of one minute or more; its minute count is the floor of the overhang.
- A window with no minute in common with the covered span, touching it at one instant included, prints one
  `unknown: <reason>` line and exits 0. So does an unreadable file, an empty one, or one whose bytes are not
  UTF-8; such a read prints no traceback.

Each case runs the reader as a subprocess and compares its stdout. No case imports the reader, so a
missing reader fails on an assert, not on an import.

Run with:

    python3 lint/test_pace_numbers.py -v
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
import _transcript  # noqa: E402  the shared transcript readers, used by the control case only

SCRIPT = os.path.join(HERE, "pace_numbers.py")
RUN_FOLDER = _test_temp.run_folder()
HANG_CAP = 60  # seconds; the reader reads a few KB, so the cap sits far above a run
DAY = "2026-11-25"
PREVIOUS_DAY = "2026-11-24"
CENTRAL_OFFSET_HOURS = 6  # window bounds are written in -06:00; fixture records are UTC (Z)
OPENERS = ('Check the /* opener, a // line, a # hash, an it\'s lone quote, a "quoted" word,\n'
           'and a second line with a \\ backslash.')


def at(hm, day=DAY):
    """A transcript timestamp in UTC with milliseconds, as the real records write it."""
    parts = (hm.split(":") + ["00"])[:3]
    return "%sT%s:%s:%s.000Z" % (day, parts[0], parts[1], parts[2])


def window_arg(hm):
    """A window bound in -06:00 for the UTC instant `hm` on DAY, written HH:MM or HH:MM:SS."""
    hours, minutes, seconds = (int(x) for x in (hm.split(":") + ["0"])[:3])
    return "%sT%02d:%02d:%02d-06:00" % (DAY, hours - CENTRAL_OFFSET_HOURS, minutes, seconds)


def agent_id(n):
    """A 17-character agent id, the shape a launch result gives."""
    return "a%016x" % n


def shell_id(n):
    """A 9-character task id, the shape a background shell command gets."""
    return "b%08x" % n


def expected_lines(agents, most, idle, still=0, note=None):
    """The reader's two lines. The wording lives here only, so a wording change is one edit. note is the coverage
    note the idle line ends with when the window reaches past the covered span."""
    first = "agents run: %d, most at once: %d" % (agents, most)
    if still:
        first += " (%d still running)" % still
    second = "minutes with no agent running: %d" % idle
    if note:
        second += " (%s)" % note
    return [first, second]


def before_note(hm, minutes):
    """The coverage note for a window that starts `minutes` before the covered span, which starts at `hm` UTC."""
    return "transcript covers from %s on; %d min before it not counted" % (window_arg(hm), minutes)


def after_note(hm, minutes):
    """The coverage note for a window that ends `minutes` after the covered span, which ends at `hm` UTC."""
    return "transcript covers until %s; %d min after it not counted" % (window_arg(hm), minutes)


def flat(*items):
    out = []
    for item in items:
        out.extend(item if isinstance(item, list) else [item])
    return out


def spawn(ts, use_id, name="Agent"):
    return {"type": "assistant", "timestamp": ts, "isSidechain": False,
            "message": {"role": "assistant", "content": [{
                "type": "tool_use", "id": use_id, "name": name,
                "input": {"description": "synthetic task", "subagent_type": "builder",
                          "prompt": "synthetic prompt", "run_in_background": True}}]}}


def launched(ts, use_id, aid, foreground=False):
    """A spawn's launch result. A background launch carries isAsync and the async status. A foreground one carries
    only the agent id, with no isAsync key, as the reviewer's probe gives it (the real transcript holds none)."""
    if foreground:
        text, result = "synthetic foreground result", {"agentId": aid}
    else:
        text = "Async agent launched successfully.\nagentId: %s" % aid
        result = {"isAsync": True, "status": "async_launched", "agentId": aid}
    return {"type": "user", "timestamp": ts, "isSidechain": False,
            "message": {"role": "user", "content": [{
                "type": "tool_result", "tool_use_id": use_id,
                "content": [{"type": "text", "text": text}]}]},
            "toolUseResult": result}


def refused(ts, use_id):
    return {"type": "user", "timestamp": ts, "isSidechain": False,
            "message": {"role": "user", "content": [{
                "type": "tool_result", "tool_use_id": use_id, "is_error": True,
                "content": [{"type": "text", "text": "PreToolUse:Agent hook error: synthetic refusal"}]}]}}


def send(ts, to, use_id):
    return {"type": "assistant", "timestamp": ts, "isSidechain": False,
            "message": {"role": "assistant", "content": [{
                "type": "tool_use", "id": use_id, "name": "SendMessage",
                "input": {"to": to, "recipient_kind": "agent", "summary": "synthetic follow-up",
                          "message": "synthetic follow-up text"}}]}}


def notice(task_id, tool_use_id, status="completed", summary="synthetic summary"):
    status_tag = "<status>%s</status>\n" % status if status else ""
    return ("<task-notification>\n<task-id>%s</task-id>\n<tool-use-id>%s</tool-use-id>\n%s"
            "<summary>%s</summary>\n</task-notification>" % (task_id, tool_use_id, status_tag, summary))


def send_failed(ts, use_id):
    """The cloud shape of a failed send: a tool_result with is_error, for the send's own tool_use id."""
    return {"type": "user", "timestamp": ts, "isSidechain": False,
            "message": {"role": "user", "content": [{
                "type": "tool_result", "tool_use_id": use_id, "is_error": True,
                "content": [{"type": "text", "text": "synthetic send failure: target not reachable"}]}]}}


def send_failed_local(ts, use_id):
    """The local shape of a failed SendMessage: no is_error, only toolUseResult.success false."""
    return {"type": "user", "timestamp": ts, "isSidechain": False,
            "message": {"role": "user", "content": [{
                "type": "tool_result", "tool_use_id": use_id,
                "content": [{"type": "text", "text": "synthetic send failure"}]}]},
            "toolUseResult": {"success": False}}


def queued(ts, text):
    return {"type": "queue-operation", "operation": "enqueue", "timestamp": ts, "content": text}


def user_text(ts, text):
    """A user record whose content is a plain string, the shape a notice takes in a user record."""
    return {"type": "user", "timestamp": ts, "isSidechain": False,
            "message": {"role": "user", "content": text}}


def end(queue_hm, copy_hm, aid, tool_use_id, status="completed", summary="synthetic summary"):
    """One stop's notice as the transcript logs it: a queue-operation, then a user copy (copy_hm, a little later)."""
    text = notice(aid, tool_use_id, status, summary)
    return [queued(at(queue_hm), text), user_text(at(copy_hm), text)]


def quoted_in_result(ts, use_id, text):
    return {"type": "user", "timestamp": ts, "isSidechain": False,
            "message": {"role": "user", "content": [{
                "type": "tool_result", "tool_use_id": use_id,
                "content": [{"type": "text", "text": text}]}]}}


def blob(text):
    """A resumed session's copy of an earlier request. It has no timestamp."""
    return {"type": "api-request-blob", "hash": "synthetic", "message": [{"type": "text", "text": text}]}


def snapshot(ts):
    return {"type": "attachment", "timestamp": ts, "isSidechain": False,
            "attachment": {"type": "prompt_snapshot",
                           "systemPrompt": ["synthetic system prompt that names <task-notification> tags"]}}


def attachment_notice(ts, text):
    """A notice queued as a queued_command attachment, the shape the real transcript gives it: its text is in prompt."""
    return {"type": "attachment", "timestamp": ts, "isSidechain": False,
            "attachment": {"type": "queued_command", "commandMode": "task-notification",
                           "origin": {"kind": "task-notification"}, "prompt": text}}


def compaction_summary(ts, text):
    """A resumed session's summary of earlier turns: a user record flagged isCompactSummary."""
    return {"type": "user", "timestamp": ts, "isSidechain": False, "isCompactSummary": True,
            "message": {"role": "user", "content": text}}


def plain(ts, text="synthetic text"):
    return user_text(ts, text)


def write_transcript(folder, records, runs_to=None, tail_bytes=None):
    """The fixture file. runs_to, an HH:MM UTC time, adds one plain record stamped there, so the file's covered
    span reaches it and a window ending there lies inside the span. tail_bytes, raw bytes, is appended after the
    records, for a file whose last bytes are not UTF-8."""
    if runs_to:
        records = list(records) + [plain(at(runs_to))]
    path = os.path.join(folder, "transcript.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    if tail_bytes is not None:
        with open(path, "ab") as f:
            f.write(tail_bytes)
    return path


def covered_span(path):
    """The earliest and latest timestamped record of a fixture, read back from disk. A case checks its scope with
    this before it asks the reader about a window."""
    moments = [rec["timestamp"] for rec in _transcript.read_transcript(path)
               if isinstance(rec.get("timestamp"), str)]
    return min(moments), max(moments)


def run_reader(transcript, start_hm, end_hm):
    return run_reader_bounds(transcript, window_arg(start_hm), window_arg(end_hm))


def run_reader_bounds(transcript, start_text, end_text):
    """The reader with its two window bounds exactly as given, so a case can pass a bound with no offset."""
    # The answer must not depend on the machine's zone, so the run sets one that is not UTC.
    env = dict(os.environ, TZ="America/Chicago")
    return subprocess.run(
        [sys.executable, SCRIPT, "--transcript", transcript, "--between", start_text, end_text],
        capture_output=True, text=True, timeout=HANG_CAP, env=env)


class PaceNumbersTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(dir=RUN_FOLDER)

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def expect(self, path, start, end, want, cause="reader lines differ from the form"):
        proc = run_reader(path, start, end)
        self.assertEqual(proc.returncode, 0, "exit code is not 0: " + proc.stderr.strip())
        self.assertEqual(proc.stdout.splitlines(), want, cause)

    def expect_unknown(self, path, start, end):
        proc = run_reader(path, start, end)
        self.assertEqual(proc.returncode, 0, "an unknown read exits with a code other than 0")
        lines = proc.stdout.splitlines()
        self.assertEqual(len(lines), 1, "an unknown read prints more than one line")
        self.assertTrue(lines[0].startswith("unknown: "), "the line does not start with 'unknown: '")

    def test_overlapping_agents_give_most_at_once_two_and_trailing_idle(self):
        path = write_transcript(self.folder, flat(
            spawn(at("10:00"), "t1"), launched(at("10:00"), "t1", agent_id(1)),
            spawn(at("10:05"), "t2"), launched(at("10:05"), "t2", agent_id(2)),
            end("10:10", "10:11", agent_id(1), "t1"),
            end("10:20", "10:21", agent_id(2), "t2"),
        ), runs_to="10:30")
        self.expect(path, "10:00", "10:30", expected_lines(agents=2, most=2, idle=10))

    def test_back_to_back_agents_with_a_gap_count_the_gap_as_idle(self):
        path = write_transcript(self.folder, flat(
            spawn(at("10:00"), "t1"), launched(at("10:00"), "t1", agent_id(1)),
            end("10:10", "10:11", agent_id(1), "t1"),
            spawn(at("10:15"), "t2"), launched(at("10:15"), "t2", agent_id(2)),
            end("10:25", "10:26", agent_id(2), "t2"),
        ), runs_to="10:30")
        self.expect(path, "10:00", "10:30", expected_lines(agents=2, most=1, idle=10))

    def test_task_named_spawn_starts_a_span_like_agent(self):
        path = write_transcript(self.folder, flat(
            spawn(at("10:00"), "t1", name="Task"), launched(at("10:00"), "t1", agent_id(1)),
            end("10:10", "10:11", agent_id(1), "t1"),
        ), runs_to="10:30")
        self.expect(path, "10:00", "10:30", expected_lines(agents=1, most=1, idle=20))

    def test_spans_are_clipped_at_start_and_end_and_outside_spans_are_not_counted(self):
        path = write_transcript(self.folder, flat(
            spawn(at("09:50"), "t1"), launched(at("09:50"), "t1", agent_id(1)),
            end("10:10", "10:11", agent_id(1), "t1"),
            spawn(at("10:50"), "t2"), launched(at("10:50"), "t2", agent_id(2)),
            end("11:20", "11:21", agent_id(2), "t2"),
            spawn(at("09:00"), "t3"), launched(at("09:00"), "t3", agent_id(3)),
            end("09:30", "09:31", agent_id(3), "t3"),
        ))
        self.expect(path, "10:00", "11:00", expected_lines(agents=2, most=1, idle=40))

    def test_agent_with_no_end_notice_runs_to_end_and_is_marked_still_running(self):
        path = write_transcript(self.folder, flat(
            spawn(at("10:00"), "t1"), launched(at("10:00"), "t1", agent_id(1)),
        ), runs_to="10:30")
        self.expect(path, "10:00", "10:30", expected_lines(agents=1, most=1, idle=0, still=1))

    def test_shell_command_notice_is_ignored(self):
        path = write_transcript(self.folder, flat(
            spawn(at("10:00"), "t1"), launched(at("10:00"), "t1", agent_id(1)),
            queued(at("10:03"), notice(shell_id(1), "x1")),
            user_text(at("10:04"), notice(shell_id(1), "x1")),
            queued(at("10:05"), notice(shell_id(2), "x2", status=None)),
            end("10:10", "10:11", agent_id(1), "t1"),
        ), runs_to="10:30")
        self.expect(path, "10:00", "10:30", expected_lines(agents=1, most=1, idle=20))

    def test_resumed_agent_reopens_only_after_a_send_that_follows_its_end(self):
        path = write_transcript(self.folder, flat(
            spawn(at("10:00"), "t1"), launched(at("10:00"), "t1", agent_id(1)),
            send(at("10:02"), agent_id(1), "s0"),
            end("10:05", "10:06", agent_id(1), "t1"),
            send(at("10:20"), agent_id(1), "s1"),
            end("10:30", "10:31", agent_id(1), "s1"),
        ), runs_to="10:40")
        self.expect(path, "10:00", "10:40", expected_lines(agents=1, most=1, idle=25))

    def test_refused_spawn_starts_no_span(self):
        path = write_transcript(self.folder, flat(
            spawn(at("10:00"), "t0"), refused(at("10:00"), "t0"),
            spawn(at("10:10"), "t1"), launched(at("10:10"), "t1", agent_id(1)),
            end("10:20", "10:21", agent_id(1), "t1"),
        ), runs_to="10:30")
        self.expect(path, "10:00", "10:30", expected_lines(agents=1, most=1, idle=20))

    def test_quoted_notice_and_comment_openers_in_text_do_not_end_or_break_parsing(self):
        path = write_transcript(self.folder, flat(
            spawn(at("10:00"), "t1"), launched(at("10:00"), "t1", agent_id(1)),
            plain(at("10:02"), OPENERS),
            quoted_in_result(at("10:03"), "t9", notice(agent_id(1), "t1") + "\n" + OPENERS),
            blob(notice(agent_id(1), "t1")),
            snapshot(at("10:04")),
            end("10:10", "10:11", agent_id(1), "t1"),
        ), runs_to="10:20")
        # Scope first: the quoted notice must really sit in a tool_result before the reader is asked about it.
        with open(path, encoding="utf-8") as f:
            on_disk = [json.loads(line) for line in f if line.strip()]
        quoted = [rec for rec in on_disk if rec.get("type") == "user" and isinstance(rec["message"]["content"], list)
                  and any("<task-notification>" in b.get("content", [{}])[0].get("text", "")
                          for b in rec["message"]["content"] if b.get("type") == "tool_result")]
        self.assertEqual(len(quoted), 1, "the fixture holds one notice quoted inside a tool_result")
        self.expect(path, "10:00", "10:20", expected_lines(agents=1, most=1, idle=10))

    def test_unreadable_file_prints_one_unknown_line(self):
        self.expect_unknown(os.path.join(self.folder, "missing.jsonl"), "10:00", "11:00")

    def test_empty_file_prints_one_unknown_line(self):
        path = write_transcript(self.folder, [])
        self.expect_unknown(path, "10:00", "11:00")

    def test_window_with_no_record_in_it_prints_one_unknown_line(self):
        path = write_transcript(self.folder, [plain(at("10:00", day=PREVIOUS_DAY))])
        self.expect_unknown(path, "10:00", "11:00")

    def test_window_with_records_but_no_agent_prints_zero_agents_and_the_whole_window_idle(self):
        path = write_transcript(self.folder, [plain(at("10:00")), plain(at("10:50"))], runs_to="11:00")
        self.expect(path, "10:00", "11:00", expected_lines(agents=0, most=0, idle=60))

    def test_window_starting_before_the_first_record_counts_only_from_the_first_record(self):
        # The blob has no timestamp and comes first, so the first timestamped record is the spawn at 10:00.
        path = write_transcript(self.folder, flat(
            blob("synthetic resumed copy with no timestamp, written before the first record"),
            spawn(at("10:00"), "t1"), launched(at("10:00"), "t1", agent_id(1)),
            end("10:10", "10:11", agent_id(1), "t1"),
        ), runs_to="10:30")
        self.assertEqual(covered_span(path), (at("10:00"), at("10:30")), "the fixture's covered span")
        self.expect(path, "09:30", "10:30",
                    expected_lines(agents=1, most=1, idle=20, note=before_note("10:00", 30)),
                    cause="a window part before the first timestamped record is counted as idle")

    def test_window_ending_after_the_last_record_counts_only_up_to_it(self):
        path = write_transcript(self.folder, flat(
            spawn(at("10:00"), "t1"), launched(at("10:00"), "t1", agent_id(1)),
            end("10:10", "10:11", agent_id(1), "t1"),
            plain(at("10:20")),
        ))
        self.assertEqual(covered_span(path), (at("10:00"), at("10:20")), "the fixture's covered span")
        self.expect(path, "10:00", "11:00",
                    expected_lines(agents=1, most=1, idle=10, note=after_note("10:20", 40)),
                    cause="a window part after the last timestamped record is counted as idle")

    def test_window_inside_the_covered_span_prints_the_plain_line(self):
        path = write_transcript(self.folder, flat(
            spawn(at("10:00"), "t1"), launched(at("10:00"), "t1", agent_id(1)),
            end("10:10", "10:11", agent_id(1), "t1"),
        ), runs_to="10:30")
        self.assertEqual(covered_span(path), (at("10:00"), at("10:30")), "the fixture's covered span")
        self.expect(path, "10:05", "10:25", expected_lines(agents=1, most=1, idle=15))

    def test_window_touching_the_covered_span_prints_one_unknown_line(self):
        # A window that meets the span at one instant has no minute in the span, so it lies wholly outside it.
        path = write_transcript(self.folder, flat(
            spawn(at("10:00"), "t1"), launched(at("10:00"), "t1", agent_id(1)),
            end("10:10", "10:11", agent_id(1), "t1"),
        ), runs_to="10:30")
        self.assertEqual(covered_span(path), (at("10:00"), at("10:30")), "the fixture's covered span")
        problems = []
        for side, begin_hm, finish_hm in (("before", "09:00", "10:00"), ("after", "10:30", "11:00")):
            proc = run_reader(path, begin_hm, finish_hm)
            lines = proc.stdout.splitlines()
            if proc.returncode != 0 or len(lines) != 1 or not lines[0].startswith("unknown: "):
                problems.append("%s window: exit %d, lines %r" % (side, proc.returncode, lines))
        self.assertEqual(problems, [],
                         "a window that meets the covered span at one instant prints numbers, not one "
                         "'unknown: <reason>' line")

    def test_window_clear_of_the_covered_span_prints_one_unknown_line(self):
        path = write_transcript(self.folder, flat(
            spawn(at("10:00"), "t1"), launched(at("10:00"), "t1", agent_id(1)),
            end("10:10", "10:11", agent_id(1), "t1"),
        ), runs_to="10:30")
        self.expect_unknown(path, "09:00", "09:30")
        self.expect_unknown(path, "10:45", "11:00")

    def test_failed_notice_ends_a_span(self):
        path = write_transcript(self.folder, flat(
            spawn(at("10:00"), "t1"), launched(at("10:00"), "t1", agent_id(1)),
            end("10:10", "10:11", agent_id(1), "t1", status="failed"),
        ), runs_to="10:30")
        self.expect(path, "10:00", "10:30", expected_lines(agents=1, most=1, idle=20))

    def test_killed_notice_ends_a_span(self):
        path = write_transcript(self.folder, flat(
            spawn(at("10:00"), "t1"), launched(at("10:00"), "t1", agent_id(1)),
            end("10:10", "10:11", agent_id(1), "t1", status="killed"),
        ), runs_to="10:30")
        self.expect(path, "10:00", "10:30", expected_lines(agents=1, most=1, idle=20))

    def test_send_that_failed_with_is_error_does_not_reopen_a_span(self):
        path = write_transcript(self.folder, flat(
            spawn(at("10:00"), "t1"), launched(at("10:00"), "t1", agent_id(1)),
            end("10:05", "10:06", agent_id(1), "t1"),
            send(at("10:20"), agent_id(1), "s1"), send_failed(at("10:20"), "s1"),
        ), runs_to="10:30")
        self.expect(path, "10:00", "10:30", expected_lines(agents=1, most=1, idle=25))

    def test_send_that_failed_with_success_false_does_not_reopen_a_span(self):
        path = write_transcript(self.folder, flat(
            spawn(at("10:00"), "t1"), launched(at("10:00"), "t1", agent_id(1)),
            end("10:05", "10:06", agent_id(1), "t1"),
            send(at("10:20"), agent_id(1), "s1"), send_failed_local(at("10:20"), "s1"),
        ), runs_to="10:30")
        self.expect(path, "10:00", "10:30", expected_lines(agents=1, most=1, idle=25))

    def test_end_notice_after_end_clips_the_span_and_is_not_still_running(self):
        path = write_transcript(self.folder, flat(
            spawn(at("10:00"), "t1"), launched(at("10:00"), "t1", agent_id(1)),
            end("10:40", "10:41", agent_id(1), "t1"),
        ))
        self.expect(path, "10:00", "10:30", expected_lines(agents=1, most=1, idle=0))

    def test_idle_minutes_are_floored_not_rounded_up(self):
        path = write_transcript(self.folder, flat(
            spawn(at("10:00"), "t1"), launched(at("10:00"), "t1", agent_id(1)),
            end("10:10:30", "10:11:30", agent_id(1), "t1"),
        ), runs_to="10:30")
        # Window 1800 s, busy 630 s, idle 1170 s = 19.5 min: K is the floor, 19.
        self.expect(path, "10:00", "10:30", expected_lines(agents=1, most=1, idle=19))

    def test_window_time_without_a_utc_offset_exits_with_an_argument_error(self):
        path = write_transcript(self.folder, [plain(at("10:00"))])
        proc = run_reader_bounds(path, "%sT10:00:00" % DAY, window_arg("11:00"))
        self.assertEqual(proc.returncode, 2, "a window time with no UTC offset exits 2, the argument-error code")
        self.assertEqual(proc.stdout, "", "a window time with no UTC offset prints no number")
        errors = [line for line in proc.stderr.splitlines() if ": error: " in line]
        self.assertEqual(len(errors), 1, "one argument error line is printed")
        self.assertIn("window time needs a UTC offset", errors[0], "the error names the window time")

    def test_foreground_agent_span_ends_at_its_result(self):
        path = write_transcript(self.folder, flat(
            spawn(at("10:00"), "t1"), launched(at("10:05"), "t1", agent_id(1), foreground=True),
        ), runs_to="10:10")
        # Scope first: the one launch result carries the agent id and no isAsync key.
        results = [rec for rec in _transcript.read_transcript(path) if isinstance(rec.get("toolUseResult"), dict)]
        self.assertEqual(len(results), 1, "the fixture holds one launch result")
        self.assertEqual(sorted(results[0]["toolUseResult"]), ["agentId"], "a foreground launch has no isAsync key")
        self.assertEqual(covered_span(path), (at("10:00"), at("10:10")), "the fixture's covered span")
        self.expect(path, "10:00", "10:10", expected_lines(agents=1, most=1, idle=5),
                    cause="a foreground agent's span runs past its result to the window end")

    def test_second_end_notice_without_a_send_extends_the_span(self):
        path = write_transcript(self.folder, flat(
            spawn(at("10:00"), "t1"), launched(at("10:00"), "t1", agent_id(1)),
            end("10:02", "10:03", agent_id(1), "n1", summary="synthetic first stop"),
            end("10:06", "10:07", agent_id(1), "n2", summary="synthetic second stop"),
        ), runs_to="10:10")
        # Scope first: two distinct stops, each logged twice, and no send between them.
        records = _transcript.read_transcript(path)
        self.assertEqual(sum(1 for rec in records if rec.get("type") == "queue-operation"), 2,
                         "the fixture holds two queued stops")
        names = [use.get("name") for rec in records for use in _transcript.tool_uses(rec)]
        self.assertEqual(names, ["Agent"], "no send sits between the two stops")
        self.assertEqual(covered_span(path), (at("10:00"), at("10:10")), "the fixture's covered span")
        self.expect(path, "10:00", "10:10", expected_lines(agents=1, most=1, idle=4),
                    cause="a second stop with no send since the first is ignored, so the span ends at the first")

    def test_attachment_only_notice_ends_a_span(self):
        text = notice(agent_id(1), "n1")
        path = write_transcript(self.folder, flat(
            spawn(at("10:00"), "t1"), launched(at("10:00"), "t1", agent_id(1)),
            attachment_notice(at("10:05"), text),
        ), runs_to="10:10")
        # Scope first: the attachment is the stop's only carrier.
        carriers = [rec.get("type") for rec in _transcript.read_transcript(path)
                    if "<task-notification>" in json.dumps(rec)]
        self.assertEqual(carriers, ["attachment"], "the only carrier of the stop is the attachment")
        self.assertEqual(covered_span(path), (at("10:00"), at("10:10")), "the fixture's covered span")
        self.expect(path, "10:00", "10:10", expected_lines(agents=1, most=1, idle=5),
                    cause="a stop carried only by an attachment does not end its span")

    def test_notice_in_queue_user_and_attachment_counts_once(self):
        # A green guard: one stop in all three carriers ends the span once, at its first copy.
        text = notice(agent_id(1), "n1")
        path = write_transcript(self.folder, flat(
            spawn(at("10:00"), "t1"), launched(at("10:00"), "t1", agent_id(1)),
            queued(at("10:05"), text), user_text(at("10:06"), text), attachment_notice(at("10:07"), text),
        ), runs_to="10:10")
        carriers = sorted(rec.get("type") for rec in _transcript.read_transcript(path)
                          if "<task-notification>" in json.dumps(rec))
        self.assertEqual(carriers, ["attachment", "queue-operation", "user"], "the scope: one stop in three carriers")
        self.assertEqual(covered_span(path), (at("10:00"), at("10:10")), "the fixture's covered span")
        self.expect(path, "10:00", "10:10", expected_lines(agents=1, most=1, idle=5),
                    cause="one stop in three carriers does not end its span once, at its first copy")

    def test_compaction_summary_quote_does_not_end_a_resumed_span(self):
        # The send at 10:03 resumes the span, and no real stop follows it, so the span is still running at 10:10.
        # The summary quotes a stop of the same agent whose text no real carrier has. A reader that counts the
        # quote closes the span at 10:04: no span still running, and 7 min idle instead of 1.
        quoted = notice(agent_id(1), "q1", summary="synthetic quoted stop")
        path = write_transcript(self.folder, flat(
            spawn(at("10:00"), "t1"), launched(at("10:00"), "t1", agent_id(1)),
            end("10:02", "10:02:30", agent_id(1), "n1", summary="synthetic first stop"),
            send(at("10:03"), agent_id(1), "s1"),
            compaction_summary(at("10:04"), "synthetic summary of earlier turns:\n" + quoted),
        ), runs_to="10:10")
        # Scope first: the summary is the only compaction record, it quotes a stop, and no other record carries that stop.
        summaries = [rec for rec in _transcript.read_transcript(path) if rec.get("isCompactSummary") is True]
        self.assertEqual(len(summaries), 1, "the fixture holds one compaction summary record")
        self.assertIn("<task-notification>", summaries[0]["message"]["content"], "the summary quotes a stop")
        carriers = [rec for rec in _transcript.read_transcript(path)
                    if "<tool-use-id>q1</tool-use-id>" in json.dumps(rec)]
        self.assertEqual(len(carriers), 1, "only the summary carries the quoted stop")
        self.assertEqual(covered_span(path), (at("10:00"), at("10:10")), "the fixture's covered span")
        self.expect(path, "10:00", "10:10", expected_lines(agents=1, most=1, idle=1, still=1),
                    cause="a compaction summary that quotes a stop ends the resumed span")

    def test_invalid_utf8_at_the_end_prints_one_unknown_line(self):
        path = write_transcript(self.folder, flat(
            spawn(at("10:00"), "t1"), launched(at("10:00"), "t1", agent_id(1)),
            end("10:05", "10:06", agent_id(1), "n1"),
        ), runs_to="10:10", tail_bytes=b"\xff\xfe partial record\n")
        # Scope first: the file's bytes do not decode as UTF-8.
        with open(path, "rb") as f:
            raw = f.read()
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            pass
        else:
            self.fail("scope: the fixture must end in bytes that are not UTF-8")
        proc = run_reader(path, "10:00", "10:10")
        self.assertNotIn("Traceback", proc.stderr,
                         "invalid UTF-8 at the transcript's end ends in a traceback, not an unknown line")
        self.assertEqual(proc.returncode, 0, "an unknown read exits with a code other than 0")
        lines = proc.stdout.splitlines()
        self.assertEqual(len(lines), 1, "an unknown read prints more than one line")
        self.assertTrue(lines[0].startswith("unknown: "), "the line does not start with 'unknown: '")

    def test_overhang_under_one_minute_prints_no_note(self):
        path = write_transcript(self.folder, flat(
            spawn(at("10:00"), "t1"), launched(at("10:00"), "t1", agent_id(1)),
            end("10:05:20", "10:06:20", agent_id(1), "n1"),
        ), runs_to="10:09:30")
        self.assertEqual(covered_span(path), (at("10:00"), at("10:09:30")), "the fixture's covered span")
        # The 30 s overhang floors to 0 min, and idle is 250 s or 280 s either way: both print 4.
        self.expect(path, "10:00", "10:10", expected_lines(agents=1, most=1, idle=4),
                    cause="an overhang under one minute prints a 'not counted' note")

    def test_overhang_of_61_seconds_prints_one_minute_note(self):
        # A green guard at the boundary: a 61 s overhang floors to 1 min and keeps its note.
        path = write_transcript(self.folder, flat(
            spawn(at("10:00"), "t1"), launched(at("10:00"), "t1", agent_id(1)),
            end("10:02", "10:02:30", agent_id(1), "n1"),
        ), runs_to="10:08:59")
        self.assertEqual(covered_span(path), (at("10:00"), at("10:08:59")), "the fixture's covered span")
        self.expect(path, "10:00", "10:10",
                    expected_lines(agents=1, most=1, idle=6, note=after_note("10:08:59", 1)),
                    cause="a 61 s overhang does not print its one-minute note")


class PaceNumbersFixtureControlTests(unittest.TestCase):
    """Green on the old head. The fixtures parse through the shared readers, so the reds above fail on the
    missing reader, never on a bad fixture."""

    def setUp(self):
        self.folder = tempfile.mkdtemp(dir=RUN_FOLDER)

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_fixture_carriers_parse_through_the_shared_readers(self):
        records = flat(
            spawn(at("10:00"), "t0"), refused(at("10:00"), "t0"),
            spawn(at("10:01"), "t1"), launched(at("10:01"), "t1", agent_id(1)),
            send(at("10:02"), agent_id(1), "s0"),
            end("10:05", "10:06", agent_id(1), "t1"),
            quoted_in_result(at("10:07"), "t9", notice(agent_id(1), "t1")),
            blob(notice(agent_id(1), "t1")),
            snapshot(at("10:08")),
        )
        path = write_transcript(self.folder, records)
        self.assertTrue(path.startswith(RUN_FOLDER), "the fixture sits in this run's folder")
        read = _transcript.read_transcript(path)
        self.assertEqual(len(read), len(records), "every fixture line parses as a JSON record")
        names = sorted(use.get("name") for rec in read for use in _transcript.tool_uses(rec))
        self.assertEqual(names, ["Agent", "Agent", "SendMessage"], "the spawn and send tool_use names")
        queue_carriers = [rec for rec in read if rec.get("type") == "queue-operation"
                          and "<task-notification>" in rec.get("content", "")]
        self.assertEqual(len(queue_carriers), 1, "one queue-operation carrier of the notice")
        user_carriers = [rec for rec in read if rec.get("type") == "user"
                         and isinstance(rec["message"]["content"], str)
                         and "<task-notification>" in rec["message"]["content"]]
        self.assertEqual(len(user_carriers), 1, "one user-record carrier of the notice")


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
