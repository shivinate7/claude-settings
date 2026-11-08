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
- The refusal names itself "Hand-off guard", opens with its owner line, and cites the record that holds its remedy.
  It ends with the output rule id, not the waiting-page rule.
- A capability reason ("can't", "cannot", "refuse", "refuses", "refused", "unable to", "denied", "forbidden", "no
  access", "isn't" or "not allowed", "isn't" or "not permitted", "unavailable", "403", "blocked", "not available")
  passes with a route cite whose row is refused or asks, a refusal of this session, or "(measured <date>, <check and
  result>)". A measured premise with no date is refused, and the refusal names the missing date.
- "blocked" or "not available" followed by "until" is a dependency, not a capability. With no other verb it passes.
- A choice, login or safety-kept reason ("your choice", "your call", "needs your login", "sign in as you", "a safety
  rule ... stays yours", "the safety rules keep") needs no cite, even with a capability verb on the line.
- A Why yours line behind "- ", "1. " or a bold label, or under Next, is judged.
- An unreadable refusals file (a directory, or not JSON) reads UNKNOWN in the systemMessage. It never passes silently.
- A reply with no Why yours line does not import route_match.
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
import subprocess
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
UNLABELLED = "The builder can't push from here (route r-missing)."
# A prose line with a capability verb and no Why yours label. The hand-off guard leaves it alone. Its subject is the
# trailer check, a third party, so the cannot-claim check does not read it as the session's own claim.
NOT_HAND_OFF = "The trailer check can't run here, so it is open."
TOOL_CITE = "Why yours: I can't push from here, since `%s` was refused this session." % TOOL
# Pick Q1 (b): a capability reason needs a cite (a route row that is refused or asks, a refusal of this session, or a
# measured premise with a date). A reason with no capability verb needs none.
CAPABILITY_REASONS = ("I can't push from here", "I cannot push from here", "the remote refuses the push",
                      "the push is blocked here", "a push is not available here")
CAPABILITY_LINE = "Why yours: %s, since check_red_run showed the trailer needs the owner."
CHOICE_LINES = ("Why yours: this needs your login.", "Why yours: this is your choice.",
                "Why yours: the safety rules keep this for you.")
# Each choice probe holds a base capability verb, so it reads red on a base that lacks the matching exemption.
# One probe per choice phrase.
CHOICE_PROBES = (
    "Why yours: it is your choice, and I can't make it for you.",
    "Why yours: it is your call, since the push is blocked here.",
    "Why yours: this needs your login, and I cannot push from here.",
    "Why yours: I cannot sign in as you, so the push is yours.",
    "Why yours: the remote refuses the push, and a safety rule for it stays yours.",
    "Why yours: I can't push from here, and the safety rules keep this for you.",
)
WIDENED_LINES = (
    "Why yours: the act was refused by the classifier, since the trailer needs the owner.",
    "Why yours: I am unable to push from here, since the trailer needs the owner.",
    "Why yours: this session has no access to the remote, since the trailer needs the owner.",
    "Why yours: pushing isn't allowed from this session, since the trailer needs the owner.",
    "Why yours: pushing is not allowed from this session, since the trailer needs the owner.",
    "Why yours: pushing isn't permitted from this session, since the trailer needs the owner.",
    "Why yours: pushing is not permitted from this session, since the trailer needs the owner.",
    "Why yours: the push was denied, since the trailer needs the owner.",
    "Why yours: the push is forbidden here, since the trailer needs the owner.",
    "Why yours: the push tool is unavailable, since the trailer needs the owner.",
    "Why yours: the remote returned 403, since the trailer needs the owner.",
    "Why yours: I refuse to push from here, since the trailer needs the owner.",
)
UNTIL_LINES = (
    "Why yours: the push is blocked until the CI run ends, since the trailer needs the owner.",
    "Why yours: the release is not available until the owner signs off.",
)
UNTIL_WITH_VERB = "Why yours: the push is blocked until CI ends, and I can't push from here."
OTHER_TOOL = "mcp__claude-code-remote__other_tool"  # a tool this session did not refuse
NO_CITE_OPENING = ("Hand-off guard: a Why yours line gives a capability reason with no cite "
                   "(decision guard-remedy-not-to-owner).")
NO_DATE_REFUSAL = ("Hand-off guard: a Why yours line carries a measured premise with no date, or with no check and "
                   "result (decision guard-remedy-not-to-owner).")
UNREAD_REFUSALS = "Hand-off guard: UNKNOWN, this session's refusals file did not read"
CATCH_NOTE = r"Hand-off guard: UNKNOWN, the check did not run \((ImportError|ModuleNotFoundError)\)\."  # a regex
MEASURED_OK = "Why yours: I can't push from here (measured 2026-11-06, check_red_run exited 1)."
MEASURED_NO_DATE = "Why yours: I can't push from here (measured, check_red_run exited 1)."
# The forms the waiting page already refuses, which the hand-off check must judge too.
LIST_AND_BOLD_FORMS = {
    "bullet": "- " + CHECK_ONLY,
    "numbered": "1. " + CHECK_ONLY,
    "bold label": "**Why yours:** I can't push from here, since check_red_run showed the trailer needs the owner.",
}
TAIL_RULE = "(rule output-never-hand-off-doable-step)"
# Run report_guard in a fresh process and print whether the named module is in sys.modules when it returns.
PROBE_CODE = (
    "import json, runpy, sys\n"
    "module = sys.argv[2]\n"
    "try:\n"
    "    runpy.run_path(sys.argv[1], run_name='__main__')\n"
    "except SystemExit:\n"
    "    pass\n"
    "print('PROBE ' + json.dumps(module in sys.modules))\n"
)


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

    def hook_and_env(self, reply, landed=False, sid=None):
        """The Stop input and environment for one reply: the transcript holds the reply (a landed turn holds a git
        commit first), and the rows and refusals files sit in this case's folder on the local surface."""
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
        return hook, hook_base.surface_env(env, "local")  # the surface a row's outcome is read on

    def imported_after(self, reply, module):
        """True when report_guard's process has `module` in sys.modules after the Stop runs on `reply`."""
        hook, env = self.hook_and_env(reply)
        run = subprocess.run([sys.executable, "-c", PROBE_CODE, trg.REPORT_GUARD, module],
                             input=json.dumps(hook), capture_output=True, text=True, timeout=15, env=env)
        self.assertEqual(run.returncode, 0, "the probe exited non-zero: " + run.stderr[-300:])
        out, mark, tail = run.stdout.rpartition("PROBE ")
        self.assertTrue(mark, "the probe did not finish: " + run.stderr[-300:])
        return json.loads(tail)

    def stop(self, reply, landed=False, sid=None):
        hook, env = self.hook_and_env(reply, landed, sid)
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

    # ---- red: each fails on a base where no hand-off check exists

    def test_hd_red_why_yours_with_a_check_name_only_is_refused(self):
        # Catches: a "can't" reason that names a check, which is no cite, passing the Stop. A trailer hand-off
        # whose reason names check_red_run is the form this stops.
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
                    self.assertIn("decision guard-remedy-not-to-owner", out["reason"],
                                  "the refusal does not cite the record that holds its remedy")

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

    # ---- green: each passes on the guard as shipped and must stay green

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
        prose = (NOT_HAND_OFF,
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

    # ---- the forms the waiting page refuses, the refusal's rule, the unread refusals file, the fast path

    def test_hd_red_a_why_yours_in_a_list_or_bold_is_judged(self):
        # Catches: a Why yours line behind a bullet, a number or a bold label passing the Stop, though the waiting
        # page refuses the same forms.
        self.write_rows(ROWS)
        for form, line in LIST_AND_BOLD_FORMS.items():
            for landed in (False, True):
                with self.subTest(form=form, landed=landed):
                    out = self.stop(report(prose=(line,), item=(ACT_ITEM,)), landed=landed)
                    self.assert_refused(out, "a Why yours line in the %s form with no cite (landed %s)"
                                        % (form, landed))

    def test_hd_red_a_why_yours_under_next_is_judged(self):
        # Catches: a Why yours line under the Next label passing, since the check reads only prose and Input Needed.
        self.write_rows(ROWS)
        text = "\n".join(["", DONE, "> **Deviations** none", "> **Input Needed** " + ACT_ITEM, "> **Next** wait",
                          "> " + CHECK_ONLY])
        for landed in (False, True):
            with self.subTest(landed=landed):
                out = self.stop(text, landed=landed)
                self.assert_refused(out, "a Why yours line under Next with no cite (landed %s)" % landed)

    def test_hd_red_the_refusal_ends_with_the_output_rule(self):
        # Catches: a hand-off refusal tagged with the waiting-page rule, task-names-check, rather than the output rule
        # it is a breach of. The refusal's own text is the span before the report's trailing rule label.
        self.write_rows(ROWS)
        for landed in (False, True):
            with self.subTest(landed=landed):
                out = self.stop(in_block(CHECK_ONLY), landed=landed)
                self.assert_refused(out, "a check-only Why yours line (landed %s)" % landed)
                segment = out["reason"].split(" (rule reports-order-of-labels)")[0]
                self.assertTrue(segment.endswith(TAIL_RULE),
                                "the hand-off refusal does not end with %s: %r" % (TAIL_RULE, segment[-120:]))
                self.assertNotIn("task-names-check", out["reason"], "the refusal still carries the waiting-page rule")

    def test_hd_red_an_unreadable_refusals_file_reads_unknown(self):
        # Catches: a refusals file that did not read passing the Stop with no word, or refusing a cite it could not check.
        for label in ("a directory at the refusals path", "a refusals file that is not JSON"):
            with self.subTest(file=label):
                path = self.refusals_file(self.SID)
                if os.path.isdir(path):
                    shutil.rmtree(path)
                elif os.path.exists(path):
                    os.remove(path)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                if label.startswith("a directory"):
                    os.makedirs(path)
                else:
                    with open(path, "w", encoding="utf-8") as handle:
                        handle.write("not json\n")
                self.assertTrue(os.path.exists(path), "scope: the unreadable refusals file is not in place")
                out = self.stop(in_block(TOOL_CITE), sid=self.SID)
                self.assertIsNotNone(out, "%s passed the Stop with no systemMessage" % label)
                self.assertIn("UNKNOWN", out.get("systemMessage", ""), "%s was not reported as UNKNOWN" % label)
                self.assertNotEqual(out.get("decision"), "block", "%s was refused on the file that did not read" % label)

    def test_hd_cost_a_reply_with_no_why_yours_does_not_import_route_match(self):
        # Catches: the fast path importing route_match, the rows reader, on every Stop. A Why yours line may import it.
        reply = report(prose=(NOT_HAND_OFF,))
        self.assertFalse(self.imported_after(reply, "route_match"),
                         "a reply with no Why yours line imported route_match")

    # ---- pick Q1 (b): capability reasons need a cite, choice reasons need none, a measured premise needs a date

    def test_hd_green_a_capability_reason_with_no_cite_is_refused(self):
        # Catches: a capability reason, under any of its verbs, passing the Stop with none of the three cites.
        self.write_rows(ROWS)
        for phrase in CAPABILITY_REASONS:
            for shape, make in SHAPES.items():
                for landed in (False, True):
                    with self.subTest(phrase=phrase, shape=shape, landed=landed):
                        out = self.stop(make(CAPABILITY_LINE % phrase), landed=landed)
                        self.assert_refused(out, "a capability reason with no cite (%r, %s, landed %s)"
                                            % (phrase, shape, landed))

    def test_hd_red_a_choice_reason_with_no_cite_passes(self):
        # Catches: a choice, a login or a safety-kept reason, with no capability verb, refused for lacking a cite.
        for line in CHOICE_LINES:
            for shape, make in SHAPES.items():
                for landed in (False, True):
                    with self.subTest(line=line, shape=shape, landed=landed):
                        out = self.stop(make(line), landed=landed)
                        self.assert_passes(out, "a choice reason with no cite (%r, %s, landed %s)"
                                           % (line, shape, landed))

    def test_hd_red_a_measured_premise_with_a_date_passes(self):
        # Catches: a capability reason backed by a dated measured premise refused for lacking a route row.
        self.write_rows(ROWS)
        for shape, make in SHAPES.items():
            for landed in (False, True):
                with self.subTest(shape=shape, landed=landed):
                    out = self.stop(make(MEASURED_OK), landed=landed)
                    self.assert_passes(out, "a measured premise with a date (%s, landed %s)" % (shape, landed))

    def test_hd_red_a_measured_premise_with_no_date_is_refused(self):
        # Catches: a measured premise with no date passing, and a refusal that does not say the date is what is missing.
        self.write_rows(ROWS)
        for shape, make in SHAPES.items():
            for landed in (False, True):
                with self.subTest(shape=shape, landed=landed):
                    out = self.stop(make(MEASURED_NO_DATE), landed=landed)
                    self.assert_refused(out, "a measured premise with no date (%s, landed %s)" % (shape, landed))
                    self.assertIn(NO_DATE_REFUSAL, out["reason"],
                                  "the refusal for a missing date is not the pinned text")

    # ---- choice phrases, widened capability verbs, "until", the refusals file's unread states, and the note for
    # a check that did not run

    def write_binary_refusals(self, sid):
        path = self.refusals_file(sid)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(b"\xff\xfe\x00 not utf-8\n")

    def stop_blocking(self, reply, module, landed=False):
        """The Stop run with `module` set to None in sys.modules, so its import raises inside the hook."""
        hook, env = self.hook_and_env(reply, landed)
        run = trg.run_guard(trg.REPORT_GUARD, hook, env=env, block=(module,))
        self.assertEqual(run.returncode, 0, "the Stop hook exited non-zero: " + run.stderr[-300:])
        self.assertNotIn("Traceback", run.stderr, "the Stop hook crashed: " + run.stderr[-300:])
        return json.loads(run.stdout) if run.stdout.strip() else None

    def test_hd_red_a_choice_phrase_passes_even_with_a_capability_verb(self):
        # Catches: a choice, login or safety-kept line refused for the capability verb it holds, with no cite to give.
        self.write_rows(ROWS)
        for line in CHOICE_PROBES:
            for shape, make in SHAPES.items():
                for landed in (False, True):
                    with self.subTest(line=line, shape=shape, landed=landed):
                        out = self.stop(make(line), landed=landed)
                        self.assert_passes(out, "a choice line with a capability verb (%r, %s, landed %s)"
                                           % (line, shape, landed))

    def test_hd_red_a_widened_capability_verb_with_no_cite_is_refused(self):
        # Catches: a capability verb the check does not know (refused, unable to, denied, 403 and the rest) passing the
        # Stop with no cite, as a reason that needs one.
        self.write_rows(ROWS)
        for line in WIDENED_LINES:
            for shape, make in SHAPES.items():
                for landed in (False, True):
                    with self.subTest(line=line, shape=shape, landed=landed):
                        out = self.stop(make(line), landed=landed)
                        self.assert_refused(out, "a capability verb with no cite (%r, %s, landed %s)"
                                            % (line, shape, landed))

    def test_hd_red_a_blocked_or_unavailable_until_is_a_dependency(self):
        # Catches: "blocked until" or "not available until", a wait on another act, refused as a capability.
        self.write_rows(ROWS)
        for line in UNTIL_LINES:
            for shape, make in SHAPES.items():
                for landed in (False, True):
                    with self.subTest(line=line, shape=shape, landed=landed):
                        out = self.stop(make(line), landed=landed)
                        self.assert_passes(out, "a dependency with until (%r, %s, landed %s)" % (line, shape, landed))

    def test_hd_green_an_until_line_with_another_capability_verb_is_refused(self):
        # Catches: the until rule passing a line whose other capability verb still needs a cite.
        self.write_rows(ROWS)
        for shape, make in SHAPES.items():
            for landed in (False, True):
                with self.subTest(shape=shape, landed=landed):
                    out = self.stop(make(UNTIL_WITH_VERB), landed=landed)
                    self.assert_refused(out, "an until line with can't and no cite (%s, landed %s)" % (shape, landed))

    def test_hd_red_a_binary_refusals_file_keeps_the_other_verdicts(self):
        # Catches: a refusals file that does not decode taking the other verdicts down with it, so a route cite to a
        # works row passes.
        self.write_rows([WORKS])
        self.write_binary_refusals(self.SID)
        for shape, make in SHAPES.items():
            for landed in (False, True):
                with self.subTest(shape=shape, landed=landed):
                    out = self.stop(make(WHY % " (route r-works)"), landed=landed, sid=self.SID)
                    self.assert_refused(out, "a route cite to a works row with a binary refusals file (%s, landed %s)"
                                        % (shape, landed))
                    self.assertIn("gh-api", out["reason"], "the remedy does not name the works row's route")

    def test_hd_red_a_binary_refusals_file_reads_unknown_for_that_read(self):
        # Catches: a refusals file that does not decode passing with no word that the read failed, or refusing the
        # cite on that read alone.
        self.write_binary_refusals(self.SID)
        for shape, make in SHAPES.items():
            for landed in (False, True):
                with self.subTest(shape=shape, landed=landed):
                    out = self.stop(make(CAPABILITY_LINE % "I can't push from here"), landed=landed, sid=self.SID)
                    self.assertNotEqual((out or {}).get("decision"), "block",
                                        "a binary refusals file blocked the reply on that read alone")
                    self.assertIn(UNREAD_REFUSALS, (out or {}).get("systemMessage", ""),
                                  "the binary refusals file was not reported as unread")

    def test_hd_green_a_readable_refusals_file_naming_no_cited_tool_is_refused(self):
        # Catches: a readable refusals file, with a row for another tool, reading UNKNOWN in place of refusing the cite.
        self.write_rows(ROWS)
        self.write_refusals([TOOL], sid=self.SID)
        line = "Why yours: I can't push from here, since `%s` was refused this session." % OTHER_TOOL
        for shape, make in SHAPES.items():
            for landed in (False, True):
                with self.subTest(shape=shape, landed=landed):
                    out = self.stop(make(line), landed=landed, sid=self.SID)
                    self.assert_refused(out, "a cite naming a tool the readable file lacks (%s, landed %s)"
                                        % (shape, landed))
                    self.assertIn(NO_CITE_OPENING, out["reason"], "the refusal is not the no-cite refusal")
                    self.assertNotIn("UNKNOWN", (out or {}).get("systemMessage", ""),
                                     "a readable refusals file was reported as unread")

    def test_hd_green_a_route_cite_with_an_unreadable_refusals_file_is_refused(self):
        # Catches: an unreadable refusals file turning a works or dead route cite into an UNKNOWN that passes the reply.
        self.write_rows(ROWS + [WORKS])
        os.makedirs(self.refusals_file(self.SID))  # a directory at the refusals path: it cannot be read
        for why, remedy in ((WHY % " (route r-works)", "gh-api"),
                            (DEAD_ROUTE, "cites a route id the route rows file does not hold")):
            for shape, make in SHAPES.items():
                for landed in (False, True):
                    with self.subTest(why=why, shape=shape, landed=landed):
                        out = self.stop(make(why), landed=landed, sid=self.SID)
                        self.assert_refused(out, "a route cite with an unreadable refusals file (%r, %s, landed %s)"
                                            % (why, shape, landed))
                        self.assertIn(remedy, out["reason"], "the refusal's remedy does not match the route verdict")

    def test_hd_green_an_exception_in_the_hand_off_check_reads_unknown(self):
        # Catches: an exception in the hand-off check passing the Stop with no word, or refusing the reply on it.
        self.write_rows(ROWS)
        for landed in (False, True):
            with self.subTest(landed=landed):
                out = self.stop_blocking(in_block(WITH_ROUTE), "route_match", landed=landed)
                self.assertNotEqual((out or {}).get("decision"), "block",
                                    "the hand-off check's exception blocked the reply (landed %s)" % landed)
                self.assertRegex((out or {}).get("systemMessage", ""), CATCH_NOTE,
                                 "the hand-off check's exception was not reported as UNKNOWN (landed %s)" % landed)

    # ---- cost: no file read beyond today's, unless a hand-off line is present

    def test_hd_cost_a_reply_with_no_hand_off_opens_only_the_transcript(self):
        # Catches: the hand-off check reading the rows file or the refusals file on every Stop.
        reply = report(prose=(NOT_HAND_OFF,))
        with mock.patch.dict(os.environ, {ROUTE_ROWS_ENV: self.rows}):
            out, opened, transcript = self.guard_opens(reply)
        self.assertEqual(out, "", "a reply with no hand-off was judged: %s" % out)
        self.assertEqual(set(opened), {transcript},
                         "a reply with no hand-off opened: %s" % sorted(set(opened) - {transcript}))


if __name__ == "__main__":
    unittest.main()
