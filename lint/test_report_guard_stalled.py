#!/usr/bin/env python3
"""The triage Stop hold: a triage wake does not end while the newest roadmap build output prints a stalled entry.

The coordinator's ruling sets the rule: triage's Stop refuses to end a wake while `stalled step:` lines print,
so a triage session cannot end a wake that leaves a stall unread. The rules the cases pin:

- Only a session whose own newest get_session record carries cs-build:triage is held. A set_session_tags call
  after that record ends the proof, as in hooks/guard_merge.py _own_tier_proved.
- The newest build output decides. A build output is the result of a Bash call that runs build.py. A clean
  build prints no stalled line, so a newer clean build releases an older entry.
- An entry line is `stalled step: <id> (...)` or `stalled step: item <n> (...)`. An unknown line is not an entry.
- The refusal names the ids of the newest output's entries, and cites the record that holds the steps to dispose
  each.
- A second Stop (stop_hook_active) is refused again, unless the report's Input Needed section names every
  entry id and item n. One missing id keeps the refusal. The escape is an escalation to the coordinator.
- An owner `override` typed for the session lifts the hold, as guard_core's refuse() honours override.grant.
  The Stop that the override lifts spends it: the next Stop is held again.
- A build run through the verdict wrapper is read from the log path its result names, where its lines are kept.
- A held Stop on a well-formed report carries no correction tail: the report is not to be sent again.
- A non-triage Stop opens its transcript no more often than the base commit does (BASE_OPENS on this transcript).

The stalled lines come from build.stalled_lines, the one emitter, so a change to the format reaches these cases.
A held case is red where no hold exists: its Stop is not refused. A control case pins what must stay released,
and it passes on that code too. The fixture, the transcript helpers and the run folder come from
lint/test_report_guard.py, and the Stop helper is its QuestionReachesPageTests.stop. Run with:

    python3 lint/test_report_guard_stalled.py -v
"""
import itertools
import json
import os
import subprocess
import sys
import unittest
from datetime import datetime
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "roadmap"))
import test_report_guard as trg  # noqa: E402  the fixture, helpers and run folder (one home)
import build  # noqa: E402  the emitter of the stalled lines (one home)
import override  # noqa: E402  the owner override and its file (one home)

human = trg.human
assistant_text = trg.assistant_text
REPORT_GUARD = trg.REPORT_GUARD

TRIAGE_ID = "session_triage1"
TRIAGE_ENV = "cse_triage1"  # the remote id override.remote_session_id() reads as TRIAGE_ID
LANE_ID = "session_lane1"
LANE_ENV = "cse_lane1"
COORD_ID = "session_coord1"
OWNER_SESSION = "session_stop1"  # the hook's own session id: the owner's override file is named by it
NOW = "2026-11-06T12:40:00-06:00"  # LOCAL_TIME_NOW for the hook and the grant, so the override clock is fixed
SUMMARY = "roadmap.md: 14 steps, 3 topics, 2 meta"  # the line every build run prints first
BUILD = "python3 skills/roadmap/build.py --repo ."
WELL_FORMED = "\n".join(["> **Done** BUILT abc123", "> **Deviations** none", "> **Input Needed** none", "> **Next** wait"])
# Runs the guard with every open of the watched transcript logged to COUNT_OPENS_LOG. The main loop, the hold's read
# and the own-record read all open it through builtins.open, so the count is every transcript read of the Stop.
COUNT_OPENS_CODE = (
    "import builtins, os, runpy, sys\n"
    "watched = os.environ['COUNT_OPENS_PATH']\n"
    "log = os.environ['COUNT_OPENS_LOG']\n"
    "real_open = builtins.open\n"
    "def counting_open(file, *args, **kwargs):\n"
    "    if isinstance(file, (str, bytes, os.PathLike)) and os.path.abspath(os.fsdecode(file)) == watched:\n"
    "        with real_open(log, 'a', encoding='utf-8') as f:\n"
    "            f.write('open\\n')\n"
    "    return real_open(file, *args, **kwargs)\n"
    "builtins.open = counting_open\n"
    "sys.argv = sys.argv[1:2]\n"
    "runpy.run_path(sys.argv[0], run_name='__main__')\n"
)
BASE_OPENS = 3  # a plain Stop opens the transcript three times: the main record load, and one in each of the two last_reply calls, since the hook carries no reply text
_IDS = itertools.count(1)


def setUpModule():
    trg.setUpModule()  # the run folder, CLAUDE_CONFIG_DIR and the model stub, set as test_report_guard sets them


def tearDownModule():
    trg.tearDownModule()


def stalled_lines(steps=(), landed=(), items=(), why=None, items_why=None):
    """The lines build.py prints for these stalled entries: steps as todo ids, landed as (id, landed marks),
    items as (n, lane). `why` or `items_why` makes that read unknown, as build.stalled does."""
    block = {"why": why,
             "steps": None if why else [{"id": k, "fix": "todo"} for k in steps]
                                       + [{"id": k, "fix": marks} for k, marks in landed],
             "paused": [], "badPause": [],
             "items": None if items_why else [{"n": n, "lane": lane} for n, lane in items],
             "itemsWhy": items_why}
    return build.stalled_lines(block)


def tool_pair(name, input_, result, is_error=False):
    """A tool call and its result, as a transcript holds them."""
    use_id = "toolu_st%d" % next(_IDS)
    return [{"type": "assistant", "isSidechain": False, "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": use_id, "name": name, "input": input_}]}},
            {"type": "user", "isSidechain": False, "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": use_id, "content": result, "is_error": is_error}]}}]


def build_run(lines, exit_code=0):
    """A Bash call of build.py and its result. A run that prints an entry line exits 1, so its result is an error."""
    body = "\n".join([SUMMARY] + list(lines))
    if exit_code:
        body = "Exit code %d\n%s" % (exit_code, body)
    return tool_pair("Bash", {"command": BUILD}, body, is_error=bool(exit_code))


def verdict_build_run(log_path):
    """A build run through the verdict wrapper: its result shows the FAIL line and the log path only. The build's own
    lines are in that log file, as the wrapper keeps them. The run exits 1, so its result is an error."""
    body = "FAIL python3 skills/roadmap/build.py --repo . rc=1 (0.4s) log=%s" % log_path
    return tool_pair("Bash", {"command": "~/.claude/bin/verdict python3 skills/roadmap/build.py --repo ."}, body,
                     is_error=True)


def own_record(session_id, tags, parent=None):
    """This session's own get_session result, read with no argument: the record the own-record reader takes."""
    ccr = {"id": session_id, "tags": list(tags)}
    if parent:
        ccr["parent_session_id"] = parent
    return tool_pair("mcp__claude-code-remote__get_session", {}, json.dumps({"ccr": ccr}))


def set_tags(session_ids):
    return tool_pair("mcp__claude-code-remote__set_session_tags",
                     {"session_ids": list(session_ids), "add": ["cs-build:lane"]}, "ok")


def report(*names):
    """A report whose Input Needed item names each of `names`. It holds no question, pick or option."""
    return "\n".join(["> **Done** OTHER read the build",
                      "> **Input Needed** Stalled for this wake: " + "; ".join(names) + ".",
                      "> **Next** wait"])


class StalledFixture(trg.SameTurnWriter):
    """test_report_guard's QuestionReachesPageTests fixture, borrowed name by name. A case here reuses it and does
    not copy it, so a change to the shared fixture reaches both files."""

    PAGE = trg.QuestionReachesPageTests.PAGE  # named here, not aliased at module level: an alias loads its cases too
    setUp = trg.QuestionReachesPageTests.setUp
    make_repo = trg.QuestionReachesPageTests.make_repo
    stop = trg.QuestionReachesPageTests.stop

    def run_stop(self, records, env_id=TRIAGE_ENV, stop_active=False):
        """Stop on `records` as the session env_id names, with the hook's own session id set."""
        return self.stop(records, env_id=env_id, stop_active=stop_active, session_id=OWNER_SESSION)

    def held(self, out, *named):
        """The Stop was refused as a block, and the refusal names each of `named`, the triage check and its record."""
        self.assertIsNotNone(out, "the Stop was not refused: a triage wake ended while a stalled step line printed")
        self.assertEqual(out.get("decision"), "block", "the Stop was not refused as a block: %r" % (out,))
        for word in named:
            self.assertIn(word, out["reason"], "the refusal does not name %r" % word)
        self.assertIn("Triage hold", out["reason"], "the refusal is not the triage hold")
        self.assertIn("decision guard-remedy-not-to-owner", out["reason"],
                      "the refusal does not cite the record of its steps")

    def released(self, out):
        """The Stop was not refused."""
        self.assertFalse(out and out.get("decision") == "block",
                         "the Stop was refused with no held entry on the newest build output: %r" % (out,))

    def stalled_wake(self, steps=("build-stalled-check",), items=()):
        """A triage wake whose newest build run prints an entry for each id and item. No reply yet."""
        return [human("wake"), *own_record(TRIAGE_ID, ["cs-build:triage"]),
                *build_run(stalled_lines(steps=list(steps), items=list(items)), exit_code=1)]

    def transcript_opens(self, records, env_id=TRIAGE_ENV):
        """How many times one Stop opens its transcript. The hook runs under COUNT_OPENS_CODE, which logs each open."""
        path = trg.write_transcript(records, self.run_dir)
        hook = {"hook_event_name": "Stop", "session_id": OWNER_SESSION, "transcript_path": path,
                "stop_hook_active": False, "cwd": self.repo}
        log = os.path.join(self.run_dir, "opens.log")
        env = dict(os.environ, CLAUDE_CONFIG_DIR=self.cfg, HOME=self.home,
                   COUNT_OPENS_PATH=os.path.abspath(path), COUNT_OPENS_LOG=log)
        env.pop("CLAUDE_CODE_REMOTE_SESSION_ID", None)
        if env_id:
            env["CLAUDE_CODE_REMOTE_SESSION_ID"] = env_id
        run = subprocess.run([sys.executable, "-c", COUNT_OPENS_CODE, REPORT_GUARD], input=json.dumps(hook),
                             capture_output=True, text=True, timeout=15, env=env)
        self.assertEqual(run.returncode, 0, run.stderr)
        if not os.path.exists(log):
            return 0
        with open(log, encoding="utf-8") as handle:
            return sum(1 for _ in handle)

    def grant_once(self):
        """The owner's typed `override`: the once-override file the prompt hook writes for the session."""
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": self.cfg}):
            granted = override.grant(OWNER_SESSION, "override", datetime.fromisoformat(NOW))
        self.assertIsNotNone(granted, "the typed override wrote no override file")


class TriageHoldTests(StalledFixture, unittest.TestCase):

    # Held: the newest build output has an entry line. Each is red where no hold exists.

    def test_st_red_entry_line_holds_the_triage_stop(self):
        # Catches: a triage wake ends while `stalled step: <id> (...)` prints, so the stalled step stays unread.
        out = self.run_stop([human("wake"), *own_record(TRIAGE_ID, ["cs-build:triage"]),
                             *build_run(stalled_lines(steps=["build-stalled-check"]), exit_code=1),
                             assistant_text("Build read.")])
        self.held(out, "build-stalled-check")

    def test_st_red_item_line_holds_the_triage_stop(self):
        # Catches: a stalled waiting-page item (an answer routed to a gone lane) does not hold the wake.
        out = self.run_stop([human("wake"), *own_record(TRIAGE_ID, ["cs-build:triage"]),
                             *build_run(stalled_lines(items=[(7, "idle-lane")]), exit_code=1),
                             assistant_text("Build read.")])
        self.held(out, "item 7")

    def test_st_red_landed_line_holds_the_triage_stop(self):
        # Catches: a step that landed but still reads stalled is treated as settled, so the wake ends on it.
        out = self.run_stop([human("wake"), *own_record(TRIAGE_ID, ["cs-build:triage"]),
                             *build_run(stalled_lines(landed=[("landed-step", ["#1290"])]), exit_code=1),
                             assistant_text("Build read.")])
        self.held(out, "landed-step")

    def test_st_red_every_entry_of_the_newest_run_is_named(self):
        # Catches: the refusal names one entry and drops the rest of a full run. Several steps, landed and items.
        lines = stalled_lines(steps=["build-stalled-check", "pause-wait-owner", "resume-probe"],
                              landed=[("landed-step", ["#1290"])], items=[(7, "idle-lane"), (9, "old-lane")])
        out = self.run_stop([human("wake"), *own_record(TRIAGE_ID, ["cs-build:triage"]),
                             *build_run(lines, exit_code=1), assistant_text("Build read.")])
        self.held(out, "build-stalled-check", "pause-wait-owner", "resume-probe", "landed-step", "item 7", "item 9")

    def test_st_red_refusal_names_the_newest_run_only(self):
        # Catches: an older run's stalled step, already disposed on a later build, is named again.
        out = self.run_stop([human("wake"), *own_record(TRIAGE_ID, ["cs-build:triage"]),
                             *build_run(stalled_lines(steps=["old-step-probe"]), exit_code=1),
                             *build_run(stalled_lines(steps=["build-stalled-check"]), exit_code=1),
                             assistant_text("Build read.")])
        self.held(out, "build-stalled-check")
        self.assertNotIn("old-step-probe", out["reason"], "the refusal names a step the newest build does not print")

    def test_st_red_older_clean_run_does_not_hide_a_newer_entry(self):
        # Catches: a clean build before the entry run is read as the newest output, so the entry never holds.
        out = self.run_stop([human("wake"), *own_record(TRIAGE_ID, ["cs-build:triage"]),
                             *build_run([]),
                             *build_run(stalled_lines(steps=["build-stalled-check"]), exit_code=1),
                             assistant_text("Build read.")])
        self.held(out, "build-stalled-check")

    def test_st_red_entry_beside_an_unknown_line_holds(self):
        # Catches: an unknown line in the newest run hides the entry printed beside it.
        lines = stalled_lines(why="unknown (the live read failed)") + stalled_lines(steps=["build-stalled-check"])
        out = self.run_stop([human("wake"), *own_record(TRIAGE_ID, ["cs-build:triage"]),
                             *build_run(lines, exit_code=1), assistant_text("Build read.")])
        self.held(out, "build-stalled-check")

    def test_st_red_second_stop_on_a_held_entry_is_refused_again(self):
        # Catches: a Stop after a refusal (stop_hook_active) ends a wake whose newest build still prints an entry.
        out = self.run_stop([human("wake"), *own_record(TRIAGE_ID, ["cs-build:triage"]),
                             *build_run(stalled_lines(steps=["build-stalled-check"]), exit_code=1),
                             assistant_text("Build read.")], stop_active=True)
        self.held(out, "build-stalled-check")

    def test_st_red_second_stop_with_every_id_under_input_needed_is_released(self):
        # Catches: no escalation path, so a wake whose every stall the report names as Input Needed loops forever.
        steps = ["build-stalled-check", "pause-wait-owner"]
        records = self.stalled_wake(steps, items=[(7, "idle-lane")])
        self.held(self.run_stop(records + [assistant_text("Build read.")], stop_active=True),
                  *steps, "item 7")  # precondition: with no names the second Stop is refused again
        out = self.run_stop(records + [assistant_text(report(*steps, "item 7"))], stop_active=True)
        self.released(out)

    def test_st_red_second_stop_with_one_id_missing_under_input_needed_stays_refused(self):
        # Catches: an Input Needed that names most entries releases the wake, so one stall escapes escalation.
        records = self.stalled_wake(["build-stalled-check", "pause-wait-owner"], items=[(7, "idle-lane")])
        out = self.run_stop(records + [assistant_text(report("build-stalled-check", "item 7"))], stop_active=True)
        self.held(out, "pause-wait-owner")

    def test_st_red_owner_override_lifts_the_hold(self):
        # Catches: the owner's typed override does not reach the hold, so the wake cannot end for the owner's act.
        records = self.stalled_wake() + [assistant_text("Build read.")]
        with mock.patch.dict(os.environ, {"LOCAL_TIME_NOW": NOW}):
            self.held(self.run_stop(records), "build-stalled-check")  # the hold stands before the override
            self.grant_once()
            self.released(self.run_stop(records))

    def test_st_red_a_stop_the_override_lifts_spends_it(self):
        # Catches: one typed override lifts every later Stop, so a stalled triage is released for good on one act.
        records = self.stalled_wake() + [assistant_text("Build read.")]
        with mock.patch.dict(os.environ, {"LOCAL_TIME_NOW": NOW}):
            self.held(self.run_stop(records), "build-stalled-check")  # the hold stands before the override
            self.grant_once()
            self.released(self.run_stop(records))  # the one lifted Stop
            self.held(self.run_stop(records), "build-stalled-check")  # the next Stop is held again: it was spent

    # Controls: each must stay released. They pass where no hold exists, and they pin the release rules.

    def test_st_control_unknown_lines_alone_do_not_hold(self):
        # Catches: an unknown read reads as a stall, so every wake that cannot read the live work is held.
        lines = stalled_lines(why="unknown (the live read failed)", items_why="unknown (the page read failed)")
        out = self.run_stop([human("wake"), *own_record(TRIAGE_ID, ["cs-build:triage"]),
                             *build_run(lines), assistant_text("Build read.")])
        self.released(out)

    def test_st_control_newer_clean_run_releases_an_older_entry(self):
        # Catches: a clean rebuild after a disposition still holds on the old entry, so the wake never ends.
        out = self.run_stop([human("wake"), *own_record(TRIAGE_ID, ["cs-build:triage"]),
                             *build_run(stalled_lines(steps=["build-stalled-check"]), exit_code=1),
                             *build_run([]), assistant_text("Build read.")])
        self.released(out)

    def test_st_control_newer_unknown_only_run_releases_an_older_entry(self):
        # Catches: a newest run with unknown lines only still holds on the older entry.
        out = self.run_stop([human("wake"), *own_record(TRIAGE_ID, ["cs-build:triage"]),
                             *build_run(stalled_lines(steps=["build-stalled-check"]), exit_code=1),
                             *build_run(stalled_lines(why="unknown (the live read failed)")),
                             assistant_text("Build read.")])
        self.released(out)

    def test_st_control_quoted_stalled_text_is_not_a_build_run(self):
        # Catches: a read of the skill text or a grep of the docs quotes an entry line and holds the wake (a false alarm).
        out = self.run_stop([human("wake"), *own_record(TRIAGE_ID, ["cs-build:triage"]),
                             *tool_pair("Bash", {"command": "cat skills/roadmap/SKILL.md"},
                                        "stalled step: build-stalled-check (resume, pause or done)"),
                             *tool_pair("Read", {"file_path": "skills/roadmap/build.py"},
                                        "stalled step: item 7 (lane idle-lane: re-route, close or resume)"),
                             assistant_text("Read the docs.")])
        self.released(out)

    def test_st_control_triage_wake_with_no_build_run_is_released(self):
        # Catches: the empty state (no build run at all) holds the wake.
        out = self.run_stop([human("wake"), *own_record(TRIAGE_ID, ["cs-build:triage"]),
                             assistant_text("Nothing to build.")])
        self.released(out)

    def test_st_control_lane_session_holds_nothing(self):
        # Catches: a lane's Stop is held on a build output it has no part in.
        out = self.run_stop([human("wake"), *own_record(LANE_ID, ["cs-build:lane"], parent="session_parent1"),
                             *build_run(stalled_lines(steps=["build-stalled-check"]), exit_code=1),
                             assistant_text("Build read.")], env_id=LANE_ENV)
        self.released(out)

    def test_st_control_coordinator_session_holds_nothing(self):
        # Catches: the coordinator's Stop is held, so the coordinator cannot end a wake that reads a build.
        out = self.run_stop([human("wake"), *own_record(COORD_ID, ["cs-build:coordinator"]),
                             *build_run(stalled_lines(steps=["build-stalled-check"]), exit_code=1),
                             assistant_text("Build read.")], env_id="cse_coord1")
        self.released(out)

    def test_st_control_session_with_no_record_holds_nothing(self):
        # Catches: a session with no get_session record is taken for triage, so any build read holds it.
        out = self.run_stop([human("wake"), *build_run(stalled_lines(steps=["build-stalled-check"]), exit_code=1),
                             assistant_text("Build read.")])
        self.released(out)

    def test_st_control_tags_set_after_the_triage_record_release_it(self):
        # Catches: a session whose triage tag was removed after its record still holds the wake.
        out = self.run_stop([human("wake"), *own_record(TRIAGE_ID, ["cs-build:triage"]),
                             *set_tags([TRIAGE_ID]),
                             *build_run(stalled_lines(steps=["build-stalled-check"]), exit_code=1),
                             assistant_text("Build read.")])
        self.released(out)

    def test_st_control_another_sessions_triage_record_holds_nothing(self):
        # Catches: a triage record for another session id is read as this session's own record.
        out = self.run_stop([human("wake"), *own_record(COORD_ID, ["cs-build:triage"]),
                             *build_run(stalled_lines(steps=["build-stalled-check"]), exit_code=1),
                             assistant_text("Build read.")])
        self.released(out)

    def test_st_control_no_remote_id_holds_nothing(self):
        # Catches: a session with no remote id is held on the record it cannot prove it owns.
        out = self.run_stop([human("wake"), *own_record(TRIAGE_ID, ["cs-build:triage"]),
                             *build_run(stalled_lines(steps=["build-stalled-check"]), exit_code=1),
                             assistant_text("Build read.")], env_id=None)
        self.released(out)

    # Held on the report's shape and on the run's log. Red on the current head: the refusal and the log read are missing.

    def test_st_red_held_first_stop_on_a_well_formed_report_has_no_correction_tail(self):
        # Catches: the hold's refusal carries the report's correction tail, so a well-formed report is told to send itself again.
        out = self.run_stop(self.stalled_wake() + [assistant_text(WELL_FORMED)])
        self.held(out, "build-stalled-check")
        tails = ("Post only the corrected lines", "Never send the report again")
        self.assertFalse(any(tail in out["reason"] for tail in tails),
                         "the hold's refusal carries the report's correction tail: %r" % (out["reason"],))

    def test_st_red_build_run_through_verdict_is_read_from_its_log(self):
        # Catches: a build run through the verdict wrapper shows only its FAIL line and log path, so the stalled lines in that log go unread.
        log = os.path.join(self.run_dir, "verdict-build.log")
        with open(log, "w", encoding="utf-8") as handle:
            handle.write("\n".join([SUMMARY] + stalled_lines(steps=["build-stalled-check"])) + "\n")
        records = [human("wake"), *own_record(TRIAGE_ID, ["cs-build:triage"]),
                   *verdict_build_run(log), assistant_text("Build read.")]
        self.held(self.run_stop(records), "build-stalled-check")

    def test_st_red_a_non_triage_stop_opens_the_transcript_no_more_than_the_base(self):
        # Catches: the hold adds a transcript open to every Stop, even in a session with no triage record and no build
        # run. A plain Stop opens the transcript BASE_OPENS times, so the hold may add none.
        records = [human("wake"), assistant_text("Build read.")]
        opens = self.transcript_opens(records, env_id=None)
        self.assertLessEqual(opens, BASE_OPENS, "the Stop opened its transcript %d times; a plain Stop opens it "
                                                "%d times, and a non-triage Stop may add none" % (opens, BASE_OPENS))


if __name__ == "__main__":
    unittest.main()
