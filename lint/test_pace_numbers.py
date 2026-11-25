#!/usr/bin/env python3
"""Fixture tests for lint/pace_numbers.py, the reader of pace numbers two and three.

Form under test: `python3 lint/pace_numbers.py --transcript FILE --between START END`, aware ISO times.
- A span starts at an Agent (or Task) tool_use record's timestamp. A refused spawn (a tool_result with
  is_error and no toolUseResult.agentId) starts no span.
- The agent's task-id is the agentId in its launch result (toolUseResult.agentId).
- A span ends at the first task-notification with that task-id and status completed. A notice counts as
  text in a user record's content or a queue-operation's content. Text in a tool_result, a blob copy
  (no timestamp) or an attachment never counts.
- A notice whose task-id matches no spawn (a background shell command) is ignored.
- A SendMessage to the agent's id, sent after its span closed, reopens the span at the send's time.
  A send while the span is open changes nothing.
- A span is clipped to the window. An agent with no end notice in the file runs to END.
- Output: `agents run: N, most at once: M`, with ` (P still running)` appended when P > 0, then
  `minutes with no agent running: K`. N counts distinct agents. K is the floor of idle seconds / 60.
- An unreadable file, an empty file, or a window with no record in it prints one `unknown: <reason>`
  line and exits 0.

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
    """A window bound in -06:00 for the UTC instant `hm` on DAY."""
    hours, minutes = (int(x) for x in hm.split(":")[:2])
    return "%sT%02d:%02d:00-06:00" % (DAY, hours - CENTRAL_OFFSET_HOURS, minutes)


def agent_id(n):
    """A 17-character agent id, the shape a launch result gives."""
    return "a%016x" % n


def shell_id(n):
    """A 9-character task id, the shape a background shell command gets."""
    return "b%08x" % n


def expected_lines(agents, most, idle, still=0):
    """The reader's two lines. The wording lives here only, so a wording change is one edit."""
    first = "agents run: %d, most at once: %d" % (agents, most)
    if still:
        first += " (%d still running)" % still
    return [first, "minutes with no agent running: %d" % idle]


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


def launched(ts, use_id, aid):
    return {"type": "user", "timestamp": ts, "isSidechain": False,
            "message": {"role": "user", "content": [{
                "type": "tool_result", "tool_use_id": use_id,
                "content": [{"type": "text", "text": "Async agent launched successfully.\nagentId: %s" % aid}]}]},
            "toolUseResult": {"isAsync": True, "status": "async_launched", "agentId": aid}}


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


def notice(task_id, tool_use_id, status="completed"):
    status_tag = "<status>%s</status>\n" % status if status else ""
    return ("<task-notification>\n<task-id>%s</task-id>\n<tool-use-id>%s</tool-use-id>\n%s"
            "<summary>synthetic summary</summary>\n</task-notification>" % (task_id, tool_use_id, status_tag))


def queued(ts, text):
    return {"type": "queue-operation", "operation": "enqueue", "timestamp": ts, "content": text}


def user_text(ts, text):
    """A user record whose content is a plain string, the shape a notice takes in a user record."""
    return {"type": "user", "timestamp": ts, "isSidechain": False,
            "message": {"role": "user", "content": text}}


def end(queue_hm, copy_hm, aid, tool_use_id):
    """One stop's notice as the transcript logs it: a queue-operation, then a user copy a minute later."""
    text = notice(aid, tool_use_id)
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


def plain(ts, text="synthetic text"):
    return user_text(ts, text)


def write_transcript(folder, records):
    path = os.path.join(folder, "transcript.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    return path


def run_reader(transcript, start_hm, end_hm):
    # The answer must not depend on the machine's zone, so the run sets one that is not UTC.
    env = dict(os.environ, TZ="America/Chicago")
    return subprocess.run(
        [sys.executable, SCRIPT, "--transcript", transcript,
         "--between", window_arg(start_hm), window_arg(end_hm)],
        capture_output=True, text=True, timeout=HANG_CAP, env=env)


class PaceNumbersTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(dir=RUN_FOLDER)

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def expect(self, path, start, end, want):
        proc = run_reader(path, start, end)
        self.assertEqual(proc.returncode, 0, "exit code is not 0: " + proc.stderr.strip())
        self.assertEqual(proc.stdout.splitlines(), want, "reader lines differ from the form")

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
        ))
        self.expect(path, "10:00", "10:30", expected_lines(agents=2, most=2, idle=10))

    def test_back_to_back_agents_with_a_gap_count_the_gap_as_idle(self):
        path = write_transcript(self.folder, flat(
            spawn(at("10:00"), "t1"), launched(at("10:00"), "t1", agent_id(1)),
            end("10:10", "10:11", agent_id(1), "t1"),
            spawn(at("10:15"), "t2"), launched(at("10:15"), "t2", agent_id(2)),
            end("10:25", "10:26", agent_id(2), "t2"),
        ))
        self.expect(path, "10:00", "10:30", expected_lines(agents=2, most=1, idle=10))

    def test_task_named_spawn_starts_a_span_like_agent(self):
        path = write_transcript(self.folder, flat(
            spawn(at("10:00"), "t1", name="Task"), launched(at("10:00"), "t1", agent_id(1)),
            end("10:10", "10:11", agent_id(1), "t1"),
        ))
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
        ))
        self.expect(path, "10:00", "10:30", expected_lines(agents=1, most=1, idle=0, still=1))

    def test_shell_command_notice_is_ignored(self):
        path = write_transcript(self.folder, flat(
            spawn(at("10:00"), "t1"), launched(at("10:00"), "t1", agent_id(1)),
            queued(at("10:03"), notice(shell_id(1), "x1")),
            user_text(at("10:04"), notice(shell_id(1), "x1")),
            queued(at("10:05"), notice(shell_id(2), "x2", status=None)),
            end("10:10", "10:11", agent_id(1), "t1"),
        ))
        self.expect(path, "10:00", "10:30", expected_lines(agents=1, most=1, idle=20))

    def test_resumed_agent_reopens_only_after_a_send_that_follows_its_end(self):
        path = write_transcript(self.folder, flat(
            spawn(at("10:00"), "t1"), launched(at("10:00"), "t1", agent_id(1)),
            send(at("10:02"), agent_id(1), "s0"),
            end("10:05", "10:06", agent_id(1), "t1"),
            send(at("10:20"), agent_id(1), "s1"),
            end("10:30", "10:31", agent_id(1), "s1"),
        ))
        self.expect(path, "10:00", "10:40", expected_lines(agents=1, most=1, idle=25))

    def test_refused_spawn_starts_no_span(self):
        path = write_transcript(self.folder, flat(
            spawn(at("10:00"), "t0"), refused(at("10:00"), "t0"),
            spawn(at("10:10"), "t1"), launched(at("10:10"), "t1", agent_id(1)),
            end("10:20", "10:21", agent_id(1), "t1"),
        ))
        self.expect(path, "10:00", "10:30", expected_lines(agents=1, most=1, idle=20))

    def test_quoted_notice_and_comment_openers_in_text_do_not_end_or_break_parsing(self):
        path = write_transcript(self.folder, flat(
            spawn(at("10:00"), "t1"), launched(at("10:00"), "t1", agent_id(1)),
            plain(at("10:02"), OPENERS),
            quoted_in_result(at("10:03"), "t9", notice(agent_id(1), "t1") + "\n" + OPENERS),
            blob(notice(agent_id(1), "t1")),
            snapshot(at("10:04")),
            end("10:10", "10:11", agent_id(1), "t1"),
        ))
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
        path = write_transcript(self.folder, [plain(at("10:00")), plain(at("10:50"))])
        self.expect(path, "10:00", "11:00", expected_lines(agents=0, most=0, idle=60))


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
