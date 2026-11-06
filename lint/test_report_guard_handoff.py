#!/usr/bin/env python3
"""Cases for the hand-off cite in lint/report_guard.py at Stop (part (v), layer (a); not built yet).

When a final reply hands an act to the owner, the "can't" reason must cite one of two things:
- `(route <id>)`, an id in the route rows file (hooks/route_rows.json, read through hooks/route_match.py; the env
  GUARD_ROUTE_ROWS overrides the path). An id the file does not hold is no cite.
- a refusal this session recorded (hooks/refusal_note.py), named by its tool in backticks.

A hand-off is a "Why yours:" line (hooks/question_form.py WHY_YOURS_LINE) at a line start, in prose above the
report or as a continuation line of the Input Needed item. The cite sits on that same line. A hand-off with no
cite is refused like the other report-shape faults, with a remedy line that never names the act handed over
(rule git-remedy-never-names-target).

Choices pinned here:
- A route cite passes only when its row's outcome on this surface is "refused" or "asks". A "works" row means the
  act is doable, so the cite is refused, and the remedy names the row's route. An "unknown" row reads UNKNOWN: a
  systemMessage with no decision.
- A rows file that does not read (missing) is UNKNOWN for a route cite: no decision, a systemMessage that
  contains the word UNKNOWN, exit 0, no traceback. It never refuses on that alone.
- An empty rows file reads, holds no id, so a route cite in it is dead and is refused.
- Scope: only a "Why yours" line is judged. An Input Needed item with no such label is not touched.
- The refusal names itself "Hand-off guard" and its remedy line starts "Remedy:".
- Every case runs on the local surface, so the rows' surface is "local" and the Stop env says so.

Cost: a reply with no hand-off reads only the transcript. A hand-off line may read the rows file.

Run from the repository root:

    python3 lint/test_report_guard_handoff.py -v

The Stop runner, the transcript records, the run folder and the route-row helpers are borrowed by name from
lint/test_report_guard.py and hooks/test_refusal_note.py, the one homes. This file adds only its cases.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_report_guard as trg  # noqa: E402  the Stop runner, the transcript records and the run folder (one home)
import test_refusal_note as hook_base  # noqa: E402  the route-row helpers and the rows-file env name (one home)

ROUTE_ROWS_ENV = hook_base.ROUTE_ROWS_ENV
ROUTE_ID = "r-archive"
# The rows the cases cite, all on the local surface the Stop env pins (see HandOffTests.stop).
ROWS = [hook_base.route_row(ROUTE_ID, "archive_session", "refused", surface="local"),
        hook_base.route_row("r-asks", "ask_first", "asks", surface="local", route="ask-first")]
WORKS = hook_base.route_row("r-works", "gh_api", "works", surface="local", route="gh-api")
UNKNOWN_ROW = hook_base.route_row("r-unknown", "unread_act", "unknown", surface="local", route="unread-route")
ACT = "archive/prose-truth-handoff"  # the act the reply hands over: a remedy never names it
TOOL = "mcp__claude-code-remote__archive_session"  # a refused tool, named in full in backticks
DONE = "> **Done** BUILT abc123"
ACT_ITEM = "Push `%s` from your computer." % ACT
WHY = "Why yours: I can't push from here, since check_red_run showed the trailer needs the owner%s."
CHECK_ONLY = WHY % ""
WITH_ROUTE = WHY % (" (route %s)" % ROUTE_ID)
DEAD_ROUTE = WHY % " (route r-missing)"
ASKS_CITE = WHY % " (route r-asks)"
# An Input Needed item with no Why yours label. Layer (a) does not judge it, even with a dead cite.
UNLABELLED = "I can't push from here (route r-missing)."
TOOL_CITE = "Why yours: I can't push from here, since `%s` was refused this session." % TOOL


def report(prose=(), item=("none",)):
    """A report with `prose` above it. The Input Needed item is `item`: its first line follows the label and the
    rest are continuation lines of that item."""
    lines = [*prose, "", DONE, "> **Deviations** none", "> **Input Needed** " + item[0]]
    lines += ["> " + line for line in item[1:]]
    return "\n".join(lines + ["> **Next** wait"])


def in_block(why):
    """The hand-off as a continuation line of the Input Needed item."""
    return report(item=(ACT_ITEM, why))


def in_prose(why):
    """The hand-off as a prose line above the report, with the Input Needed item naming the act."""
    return report(prose=(why,), item=(ACT_ITEM,))


SHAPES = {"block": in_block, "prose": in_prose}


def setUpModule():
    trg.setUpModule()  # the run folder, CLAUDE_CONFIG_DIR, the model stub and the missing route-rows seam


def tearDownModule():
    trg.tearDownModule()


class HandOffTests(unittest.TestCase):
    """Each case runs the Stop hook as a subprocess, as the other report_guard suites do, on an unlanded turn and on
    a landed one, and on both hand-off shapes. Each case works in its own folder under this run's folder."""

    SID = "ho-sid-1"
    OTHER_SID = "ho-sid-2"
    # Borrowed by name. guard_opens reads self.hook, the one-reply transcript builder.
    hook = trg.AnsweredNeedsSourceTests.hook
    guard_opens = trg.AnsweredNeedsSourceTests.guard_opens

    def setUp(self):
        self.run_dir = tempfile.mkdtemp(dir=trg.RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.run_dir, True)
        self.cfg = os.path.join(self.run_dir, "cfg")
        self.home = os.path.join(self.run_dir, "home")
        self.rows = os.path.join(self.run_dir, "route_rows.json")
        os.makedirs(self.cfg)
        os.makedirs(self.home)

    # ---- the rows file and the refusals file, both in this case's folder

    def write_rows(self, rows):
        hook_base.write_route_rows(self.rows, rows)

    def row_ids(self):
        with open(self.rows, encoding="utf-8") as handle:
            return [row["id"] for row in json.load(handle)["rows"]]

    def refusals_file(self, sid):
        return os.path.join(self.cfg, "state", "refusals", sid + ".jsonl")

    def write_refusals(self, tools, sid):
        os.makedirs(os.path.dirname(self.refusals_file(sid)), exist_ok=True)
        with open(self.refusals_file(sid), "w", encoding="utf-8") as handle:
            for tool in tools:
                handle.write(json.dumps({"ts": "2026-11-06T10:00:00-06:00", "tool_name": tool,
                                         "reason": "refused"}) + "\n")

    def pending_tools(self, sid):
        """The tool_name of each row in the session's refusals file, [] when the file is gone."""
        try:
            with open(self.refusals_file(sid), encoding="utf-8") as handle:
                return [json.loads(line)["tool_name"] for line in handle if line.strip()]
        except FileNotFoundError:
            return []

    # ---- the Stop run and its verdict

    def stop(self, reply, landed=False, sid=None):
        records = [trg.human("ask the owner")]
        if landed:
            records += [trg.tool_use_msg("Bash", {"command": "git commit -m x"}), trg.tool_result_msg()]
        records.append(trg.assistant_text(reply))
        hook = {"hook_event_name": "Stop", "transcript_path": trg.write_transcript(records, self.run_dir),
                "stop_hook_active": False, "cwd": self.run_dir}
        if sid:
            hook["session_id"] = sid
        env = dict(os.environ, CLAUDE_CONFIG_DIR=self.cfg, HOME=self.home)
        env[ROUTE_ROWS_ENV] = self.rows
        env = hook_base.surface_env(env, "local")  # the surface a row's outcome is read on
        run = trg.run_guard(trg.REPORT_GUARD, hook, env=env)
        self.assertEqual(run.returncode, 0, "the Stop hook exited non-zero: " + run.stderr[-300:])
        self.assertNotIn("Traceback", run.stderr, "the Stop hook crashed: " + run.stderr[-300:])
        return json.loads(run.stdout) if run.stdout.strip() else None

    def assert_refused(self, out, case):
        self.assertIsNotNone(out, "%s passed" % case)
        self.assertEqual(out.get("decision"), "block", "%s was not refused: %s" % (case, out))
        self.assertIn("Hand-off guard", out.get("reason", ""),
                      "%s: the refusal does not name the hand-off guard" % case)

    def assert_passes(self, out, case):
        self.assertIsNone(out, "%s was refused: %s" % (case, out and out.get("reason")))

    # ---- red: each fails on c31a8e77, where no hand-off check exists

    def test_hd_red_why_yours_with_a_check_name_only_is_refused(self):
        # Catches: a "can't" reason that names a check, which is no cite, passing the Stop. The 2026-11-06 incident
        # was a trailer hand-off whose reason named check_red_run.
        self.write_rows(ROWS)
        for shape, make in SHAPES.items():
            for landed in (False, True):
                with self.subTest(shape=shape, landed=landed):
                    out = self.stop(make(CHECK_ONLY), landed=landed)
                    self.assert_refused(out, "a Why yours line that cites only a check name (%s, landed %s)"
                                        % (shape, landed))

    def test_hd_red_route_id_the_rows_file_lacks_is_refused(self):
        # Catches: a cite to an id the rows file does not hold passing the Stop. The empty rows file is the empty state.
        for label, rows in (("empty rows file", []), ("rows file with other ids", ROWS)):
            self.write_rows(rows)
            for shape, make in SHAPES.items():
                for landed in (False, True):
                    with self.subTest(rows=label, shape=shape, landed=landed):
                        self.assertNotIn("r-missing", self.row_ids(), "scope: the cited id is in the rows file")
                        out = self.stop(make(DEAD_ROUTE), landed=landed)
                        self.assert_refused(out, "a route cite to an id the rows file lacks (%s, %s, landed %s)"
                                            % (label, shape, landed))

    def test_hd_red_route_cite_outside_the_why_yours_line_is_refused(self):
        # Catches: a valid cite in a prose line clearing a Why yours line that cites nothing.
        self.write_rows(ROWS)
        self.assertIn(ROUTE_ID, self.row_ids(), "scope: the cited id is not in the rows file")
        prose = ("The archive call is a known gap (route %s)." % ROUTE_ID,)
        for landed in (False, True):
            with self.subTest(landed=landed):
                out = self.stop(report(prose=prose, item=(ACT_ITEM, CHECK_ONLY)), landed=landed)
                self.assert_refused(out, "a valid cite on a line other than the Why yours line (landed %s)" % landed)

    def test_hd_red_refusal_row_of_another_session_is_refused(self):
        # Catches: a tool refused in another session counting as this session's refusal row.
        self.write_refusals([TOOL], sid=self.OTHER_SID)
        self.assertEqual(self.pending_tools(self.SID), [], "scope: this session already has a refusal row")
        self.assertEqual(self.pending_tools(self.OTHER_SID), [TOOL], "scope: the other session's row is missing")
        for shape, make in SHAPES.items():
            for landed in (False, True):
                with self.subTest(shape=shape, landed=landed):
                    out = self.stop(make(TOOL_CITE), landed=landed, sid=self.SID)
                    self.assert_refused(out, "a cite of another session's refusal row (%s, landed %s)"
                                        % (shape, landed))

    def test_hd_red_remedy_never_names_the_act_handed_over(self):
        # Catches: a refusal whose remedy quotes the act it refuses, which points the owner at that act.
        self.write_rows(ROWS)
        for shape, make in SHAPES.items():
            for landed in (False, True):
                with self.subTest(shape=shape, landed=landed):
                    out = self.stop(make(CHECK_ONLY), landed=landed)
                    self.assert_refused(out, "a refusal to check its remedy (%s, landed %s)" % (shape, landed))
                    self.assertNotIn(ACT, out["reason"], "the remedy names the act the reply handed over")
                    self.assertIn("Remedy:", out["reason"], "the refusal has no remedy line")

    def test_hd_red_route_cite_with_no_rows_file_reads_unknown(self):
        # Catches: a route cite the rows file cannot give, refused on the unread file alone, or passed with no word
        # that it went unread.
        self.assertFalse(os.path.exists(self.rows), "scope: the rows file exists, so the case reads no missing file")
        for shape, make in SHAPES.items():
            for landed in (False, True):
                with self.subTest(shape=shape, landed=landed):
                    out = self.stop(make(WITH_ROUTE), landed=landed)
                    self.assertNotEqual((out or {}).get("decision"), "block",
                                        "a route cite with no rows file was refused on that alone")
                    self.assertIn("UNKNOWN", (out or {}).get("systemMessage", ""),
                                  "a route cite with no rows file was not reported as UNKNOWN")

    def test_hd_red_hand_off_with_a_route_cite_reads_the_rows_file(self):
        # Catches: a hand-off whose route cite is never read, so the cite is taken on trust.
        self.write_rows(ROWS)
        with mock.patch.dict(os.environ, {ROUTE_ROWS_ENV: self.rows}):
            _out, opened, _transcript = self.guard_opens(report(prose=(WITH_ROUTE,)))
        self.assertIn(self.rows, opened, "a Why yours line with a route cite did not read the rows file")

    # ---- green: each passes on c31a8e77 and must stay green

    def test_hd_green_a_valid_route_cite_on_the_why_yours_line_passes(self):
        # Catches: the cite on the same line as the reason refused, so the check never reads a route cite at all.
        self.write_rows(ROWS)
        self.assertIn(ROUTE_ID, self.row_ids(), "scope: the cited id is not in the rows file")
        for shape, make in SHAPES.items():
            for landed in (False, True):
                with self.subTest(shape=shape, landed=landed):
                    out = self.stop(make(WITH_ROUTE), landed=landed)
                    self.assert_passes(out, "a valid route cite on the Why yours line (%s, landed %s)"
                                       % (shape, landed))

    def test_hd_green_this_sessions_refusal_row_is_a_cite(self):
        # Catches: the refusal rows read after pending_refusals clears the row that the reply names under Input
        # Needed, so the cite is lost.
        for landed in (False, True):
            with self.subTest(landed=landed):
                self.write_refusals([TOOL], sid=self.SID)
                self.assertEqual(self.pending_tools(self.SID), [TOOL],
                                 "scope: this session's refusal row is not in its file")
                out = self.stop(report(item=(ACT_ITEM, TOOL_CITE)), landed=landed, sid=self.SID)
                self.assert_passes(out, "a Why yours line citing this session's refusal row (landed %s)" % landed)

    def test_hd_green_a_reply_with_no_hand_off_is_not_touched(self):
        # Catches: a "can't" sentence, or "why yours" mid-line, read as a hand-off line.
        prose = ("I can't run check_red_run here, so the trailer check is open.",
                 "The note says why yours is open.")
        for landed in (False, True):
            with self.subTest(landed=landed):
                out = self.stop(report(prose=prose), landed=landed)
                self.assert_passes(out, "a reply with no Why yours line (landed %s)" % landed)

    # ---- scope and outcome: layer (a) judges only a Why yours line, and a cite passes only on a refused or asks row

    def test_hd_red_a_labelled_line_beside_an_unlabelled_item_is_judged(self):
        # Catches: a check that skips the whole Input Needed item once one line in it has no Why yours label, so a
        # Why yours line beside it passes.
        self.write_rows(ROWS)
        for landed in (False, True):
            with self.subTest(landed=landed):
                out = self.stop(report(item=(ACT_ITEM, UNLABELLED, CHECK_ONLY)), landed=landed)
                self.assert_refused(out, "a Why yours line beside an unlabelled item (landed %s)" % landed)

    def test_hd_green_an_unlabelled_input_needed_item_is_not_touched(self):
        # Catches: a check that refuses an Input Needed item with no Why yours label, even one with a dead cite.
        self.write_rows(ROWS)
        self.assertNotIn("r-missing", self.row_ids(), "scope: the cited id is in the rows file")
        for landed in (False, True):
            with self.subTest(landed=landed):
                out = self.stop(report(item=(ACT_ITEM, UNLABELLED)), landed=landed)
                self.assert_passes(out, "an unlabelled Input Needed item with a dead cite (landed %s)" % landed)

    def test_hd_red_a_cite_to_a_works_row_is_refused_with_its_route(self):
        # Catches: a route cite to a row that says the act works passing the Stop. The remedy names the row's route.
        self.write_rows([WORKS])
        self.assertIn("r-works", self.row_ids(), "scope: the cited id is not in the rows file")
        for shape, make in SHAPES.items():
            for landed in (False, True):
                with self.subTest(shape=shape, landed=landed):
                    out = self.stop(make(WHY % " (route r-works)"), landed=landed)
                    self.assert_refused(out, "a route cite to a works row (%s, landed %s)" % (shape, landed))
                    self.assertIn("gh-api", out["reason"], "the remedy does not name the works row's route")

    def test_hd_green_a_cite_to_a_refused_or_asks_row_passes(self):
        # Catches: a route cite to a refused or asks row refused. Those rows say the act is not doable, so the cite
        # is the reason the owner is asked.
        self.write_rows(ROWS)
        self.assertEqual(sorted(self.row_ids()), ["r-archive", "r-asks"], "scope: the rows file lacks a cited row")
        for shape, make in SHAPES.items():
            for label, why in (("refused", WITH_ROUTE), ("asks", ASKS_CITE)):
                for landed in (False, True):
                    with self.subTest(row=label, shape=shape, landed=landed):
                        out = self.stop(make(why), landed=landed)
                        self.assert_passes(out, "a route cite to a %s row (%s, landed %s)" % (label, shape, landed))

    def test_hd_red_a_cite_to_an_unknown_row_reads_unknown(self):
        # Catches: a cite to a row whose outcome is unknown refused, or passed with no note that it could not be read.
        self.write_rows([UNKNOWN_ROW])
        self.assertIn("r-unknown", self.row_ids(), "scope: the cited id is not in the rows file")
        for shape, make in SHAPES.items():
            for landed in (False, True):
                with self.subTest(shape=shape, landed=landed):
                    out = self.stop(make(WHY % " (route r-unknown)"), landed=landed)
                    self.assertNotEqual((out or {}).get("decision"), "block",
                                        "a route cite to an unknown row was refused")
                    self.assertIn("UNKNOWN", (out or {}).get("systemMessage", ""),
                                  "a route cite to an unknown row was not reported as UNKNOWN")

    # ---- cost: no file read beyond today's, unless a hand-off line is present

    def test_hd_cost_a_reply_with_no_hand_off_opens_only_the_transcript(self):
        # Catches: the hand-off check reading the rows file or the refusals file on every Stop.
        reply = report(prose=("I can't run check_red_run here, so the trailer check is open.",))
        with mock.patch.dict(os.environ, {ROUTE_ROWS_ENV: self.rows}):
            out, opened, transcript = self.guard_opens(reply)
        self.assertEqual(out, "", "a reply with no hand-off was judged: %s" % out)
        self.assertEqual(set(opened), {transcript},
                         "a reply with no hand-off opened: %s" % sorted(set(opened) - {transcript}))


if __name__ == "__main__":
    unittest.main()
