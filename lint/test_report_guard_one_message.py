#!/usr/bin/env python3
"""The first Stop of a turn prints one merged block, also when the transcript has no human message.

A lane's turn can begin from a peer or system message, so the transcript holds no human record. The plain Stop
then skipped the relay checks (question-keys and past-ruling) and the answered check, while the retry Stop that
follows the block runs them. One reply got one refusal on the first Stop and another on the retry. These cases
pin what the first Stop prints:

- a reply that fails the pick check and the past-ruling check prints one block that names both;
- a reply whose only failure is the past-ruling check prints the text the retry prints for it;
- a reply whose only failure is the pick check keeps its text;
- a reply with no failing check prints nothing, a long reply with the question at its end included;
- process starts stay at the documented cost: none for a reply that asks nothing, at most the one git read the
  past-ruling check documents for a reply that asks; settings.json still lists the same Stop scripts.

The fixture, the transcript helpers, the model stub and the run folder come from lint/test_report_guard.py, the
one home, borrowed by name here. The past-ruling model call is the stub's answer, never a real model call. Run with:

    python3 lint/test_report_guard_one_message.py -v
"""
import collections
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_report_guard as trg  # noqa: E402  the fixture, helpers and run folder (one home)
import test_call_judge as tcj  # noqa: E402  the model stub's answers, the decided repo's ruling (one home)
import _transcript  # noqa: E402  is_last_human, the reader the Stop check itself uses
import report_guard as RG  # noqa: E402  the reason texts the check prints (one home)

REPORT_GUARD = trg.REPORT_GUARD
SETTINGS = os.path.join(HERE, "..", "settings.json")
ALLOW = tcj.ALLOW
REFUSE = trg.REFUSE_APPS
REFUSE_REASON = json.loads(REFUSE)["reason"]
DONE_ONLY = trg.DONE_ONLY
RELAY = trg.RELAY
ORDER_SUFFIX = " (rule reports-order-of-labels)"
# The Stop scripts settings.json lists today, by path: the same list is the cost the Stop hook is measured against.
STOP_SCRIPTS = sorted([
    "hooks/config_watch.py", "hooks/feedback_guard.py", "hooks/precompact_handoff.py", "hooks/reply_judge.py",
    "hooks/reread_check.py", "hooks/ruling_home.py", "hooks/stall_watch.py", "lint/report_guard.py",
])
# The guard run as the hook runs it, with every process start logged to a file. The log is written before each start,
# and the start itself goes on unchanged, so the guard behaves as it does without the wrapper.
COUNT_CODE = (
    "import os, runpy, subprocess, sys\n"
    "log = sys.argv[2]\n"
    "def note(what):\n"
    "    with open(log, 'a', encoding='utf-8') as f:\n"
    "        f.write(what + '\\n')\n"
    "real_popen = subprocess.Popen\n"
    "class CountedPopen(real_popen):\n"
    "    def __init__(self, args, *rest, **kwargs):\n"
    "        argv = args if isinstance(args, (list, tuple)) else [args]\n"
    "        note(os.path.basename(str(argv[0])))\n"
    "        real_popen.__init__(self, args, *rest, **kwargs)\n"
    "subprocess.Popen = CountedPopen\n"
    "real_system = os.system\n"
    "def counted_system(command):\n"
    "    note('system')\n"
    "    return real_system(command)\n"
    "os.system = counted_system\n"
    "sys.argv = sys.argv[1:2]\n"
    "runpy.run_path(sys.argv[0], run_name='__main__')\n"
)
Stop = collections.namedtuple("Stop", "out lines calls starts")


def setUpModule():
    trg.setUpModule()  # the run folder, CLAUDE_CONFIG_DIR and the model stub, set as test_report_guard sets them


def tearDownModule():
    trg.tearDownModule()


def _remove(path):
    if os.path.exists(path):
        os.remove(path)


def _lines(path):
    """The lines of a file the run wrote, or [] when the run wrote none."""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return f.read().splitlines()


class OneMessageStopTests(trg.SameTurnWriter, unittest.TestCase):
    PAGE = tcj.PAGE_URL  # the waiting page the decided repo names; the writer read cites it

    def setUp(self):
        self.run_dir = tempfile.mkdtemp(dir=trg._ISOLATION["dir"])
        self.addCleanup(shutil.rmtree, self.run_dir, ignore_errors=True)
        self.decided = tcj.make_repo("one-message-decided", decisions={tcj.APPS_SLUG: tcj.APPS_RULING})
        # A same-turn send to the page writer: the pick check passes, so only the relay checks can refuse.
        self.sent = [*self.writer_read(self.WRITER), *self.send(session_id=self.WRITER)]

    def stop(self, records, answer=ALLOW, active=False):
        """One Stop of `records`, run as the hook runs it. Returns the decoded block (or {}), the stdout lines, the
        model calls the stub recorded, and the process starts the wrapper logged."""
        path = trg.write_transcript(records, self.run_dir)
        for name in ("calls.jsonl", "git.log"):
            _remove(os.path.join(trg._ISOLATION["stub"], name))
        log = os.path.join(self.run_dir, "starts.log")
        _remove(log)
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": active, "cwd": self.decided}
        with mock.patch.dict(os.environ, {"CJ_ANSWER": answer}):
            run = subprocess.run([sys.executable, "-c", COUNT_CODE, REPORT_GUARD, log], input=json.dumps(hook),
                                 capture_output=True, text=True, timeout=15)
        self.assertEqual(run.returncode, 0, run.stderr)
        out = json.loads(run.stdout) if run.stdout.strip() else {}
        calls = _lines(os.path.join(trg._ISOLATION["stub"], "calls.jsonl"))
        return Stop(out, run.stdout.strip().splitlines(), len(calls), _lines(log))

    def assert_no_human(self, records):
        """The scope these cases need: no human record in the transcript, only peer or system messages."""
        self.assertFalse(any(_transcript.is_last_human(rec) for rec in records),
                         "the transcript holds a human record, so the no-human path is not what this case runs")

    def test_no_human_turn_with_a_pick_and_a_relay_failure_prints_one_block_naming_both(self):
        records = [trg.peer_msg("status: the lane ended"), trg.assistant_text(RELAY)]
        self.assert_no_human(records)
        stop = self.stop(records, answer=REFUSE)
        self.assertEqual(stop.out.get("decision"), "block", "the first Stop printed no block for a reply that fails")
        self.assertEqual(len(stop.lines), 1, "the first Stop printed %d lines, not one block" % len(stop.lines))
        reason = stop.out.get("reason", "")
        self.assertIn("Pick guard", reason, "the pick refusal is missing from the first Stop's block: %r" % reason)
        self.assertIn("Past-ruling guard", reason,
                      "the first Stop's one block leaves out the past-ruling refusal, which the retry names: %r"
                      % reason)

    def test_no_human_turn_with_only_a_past_ruling_failure_prints_the_retry_text(self):
        records = [trg.peer_msg("status: the lane ended"), *self.sent, trg.assistant_text(RELAY)]
        self.assert_no_human(records)
        expected = RG.RELAY_RULE_REASON % REFUSE_REASON + ORDER_SUFFIX
        retry = self.stop(records, answer=REFUSE, active=True)  # the retry's text for this check: the one to match
        self.assertEqual(retry.out.get("reason"), expected, "the retry's text for the past-ruling failure moved")
        first = self.stop(records, answer=REFUSE)
        self.assertEqual(first.out.get("reason"), expected,
                         "the first Stop printed %r for the single past-ruling failure, not the retry's text"
                         % first.out.get("reason"))

    def test_no_human_turn_with_only_a_pick_failure_keeps_the_pick_text(self):
        records = [trg.peer_msg("status: the lane ended"), trg.assistant_text(RELAY)]
        self.assert_no_human(records)
        expected = RG.OWNER_REFUSAL % ("the page writer is not known to this session; the waiting page is "
                                       + tcj.PAGE_URL) + ORDER_SUFFIX
        stop = self.stop(records, answer=ALLOW)
        self.assertEqual(stop.out.get("reason"), expected, "the pick-only text changed on the first Stop")

    def test_no_failing_check_prints_nothing(self):
        cases = {
            "a question every check passes": [trg.peer_msg("status: the lane ended"), *self.sent,
                                              trg.assistant_text(RELAY)],
            "a reply that asks nothing": [trg.peer_msg("status: the lane ended"), trg.assistant_text(DONE_ONLY)],
        }
        for label, records in cases.items():
            with self.subTest(case=label):
                self.assert_no_human(records)
                stop = self.stop(records, answer=ALLOW)
                self.assertEqual(stop.lines, [], "the first Stop printed for %s: %r" % (label, stop.lines))

    def test_long_reply_with_the_question_at_its_end_names_the_past_ruling_check(self):
        # Full size: the reply is past the question check's text cap, so only its end carries the question.
        filler = "Status line: nothing new since the last check.\n" * 200
        records = [trg.peer_msg("status: the lane ended"), *self.sent, trg.assistant_text(filler + RELAY)]
        self.assert_no_human(records)
        stop = self.stop(records, answer=REFUSE)
        self.assertIn("Past-ruling guard", stop.out.get("reason", ""),
                      "the first Stop leaves out the past-ruling refusal for a long reply: %r" % stop.out)

    def test_a_plain_stop_starts_no_process_when_it_asks_nothing(self):
        records = [trg.peer_msg("status: the lane ended"), trg.assistant_text(DONE_ONLY)]
        self.assert_no_human(records)
        stop = self.stop(records)
        self.assertEqual(stop.starts, [], "the first Stop started a process for a reply that asks nothing: %r"
                         % stop.starts)
        self.assertEqual(stop.calls, 0, "the first Stop called the model for a reply that asks nothing")

    def test_a_plain_stop_that_asks_starts_at_most_the_one_git_read_the_relay_documents(self):
        # Control: the probe must see the documented cost, so a silent probe cannot pass the ceiling below. The
        # retry runs the past-ruling check on this reply: one git read and one model call.
        control = self.stop([trg.peer_msg("status: the lane ended"), trg.assistant_text(RELAY)], answer=REFUSE,
                            active=True)
        self.assertEqual(control.starts, ["git"], "the probe did not see the one git read of the retry's check")
        self.assertEqual(control.calls, 1, "the probe did not see the one model call of the retry's check")
        cases = [
            ("pick and past-ruling failures, no send to the writer", [trg.peer_msg("status: the lane ended"),
                                                                     trg.assistant_text(RELAY)], REFUSE),
            ("past-ruling failure after a send to the writer", [trg.peer_msg("status: the lane ended"),
                                                                *self.sent, trg.assistant_text(RELAY)], REFUSE),
            ("question every check passes", [trg.peer_msg("status: the lane ended"), *self.sent,
                                             trg.assistant_text(RELAY)], ALLOW),
        ]
        for label, records, answer in cases:
            with self.subTest(case=label):
                self.assert_no_human(records)
                stop = self.stop(records, answer=answer)
                self.assertLessEqual(len(stop.starts), 1,
                                     "the first Stop started %d processes for %s: %r" % (len(stop.starts), label,
                                                                                         stop.starts))
                self.assertTrue(set(stop.starts) <= {"git"},
                                "the first Stop started a process other than the git read: %r" % stop.starts)
                self.assertLessEqual(stop.calls, 1, "the first Stop made %d model calls for %s" % (stop.calls, label))

    def test_settings_stop_still_lists_the_same_hook_scripts(self):
        with open(SETTINGS, encoding="utf-8") as f:
            entries = json.load(f)["hooks"]["Stop"]
        commands = [hook["command"] for entry in entries for hook in entry.get("hooks", [])]
        scripts = sorted(s for command in commands for s in re.findall(r'/((?:hooks|lint)/[\w.]+\.py)"', command))
        self.assertEqual(len(commands), len(STOP_SCRIPTS), "settings.json Stop lists %d hook commands, not %d"
                         % (len(commands), len(STOP_SCRIPTS)))
        self.assertEqual(scripts, STOP_SCRIPTS, "settings.json Stop lists a different set of hook scripts")


if __name__ == "__main__":
    unittest.main()
