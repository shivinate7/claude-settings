#!/usr/bin/env python3
"""Cases for the Stop half of the route-row falsifier in lint/report_guard.py: a successful tool result whose call
matches a route row that says the act is refused, for the current surface, adds a note to the Stop's
systemMessage. The note is raised once per row per session and never refuses the turn. The PermissionDenied
half, a refusal that a row says works, is hooks/test_refusal_note_route.py.

Run it from the repository root:

    python3 lint/test_report_guard_falsifier.py -v

Standard library only. The Stop runner, the transcript helpers, the run folder and SameTurnWriter.call come from
lint/test_report_guard.py, and the route-row fixture (route_row, write_route_rows, surface_env, ROUTE_ROWS_ENV)
from hooks/test_refusal_note.py. Each is borrowed by name here, not copied.

Contract the builder codes against, pinned by these cases (the same contract as the hook half):
- The rows file's path is the env named by ROUTE_ROWS_ENV (GUARD_ROUTE_ROWS). It is {"rows": [...]}.
- Surface: "cloud" when CLAUDE_CODE_REMOTE is "true" (hooks/guard_core.is_cloud), else "local".
- A row matches a call when its surface is the current one, its outcome is "refused", and its pattern matches the
  call. The target is the Bash command text for a Bash call, and the tool name for any other call.
- A call whose tool result is an error (is_error) never notes a row.
- A matching call adds a systemMessage that names the row id and says "contradicted", with no decision key.
- Each row is noted once per session, however many matching calls the session makes.
- Cost: the hook starts no process, and it never writes the rows file.
- Missing or unreadable rows file: no output, no traceback, exit 0.
- Scanner rule (building-scanner-respects-strings): not applicable, the pattern is a regex over a call's target.

A case that judges a match pairs its negative with a positive twin in the same run: the twin shows the row would
match before the negative is judged, so a clean pass cannot come from a hook that never notes anything. s14 and
s15 are controls for a missing, unreadable or empty rows file: no output and no crash.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
import test_report_guard as trg  # noqa: E402  the Stop runner, transcript helpers and run folder (one home)
import test_refusal_note as base  # noqa: E402  the route-row fixture (one home)

CREATE = "mcp__claude-code-remote__create_session"  # neither a landing tool nor a send
MERGE_CMD = "gh api repos/acme/widgets/merge"
PROSE = trg.PendingRefusalTests.PROSE
SID = "rf-sid-1"


def setUpModule():
    trg.setUpModule()  # the isolation the Stop runner needs: config dir, model stub, and the rows seam


def tearDownModule():
    trg.tearDownModule()


def read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


class RouteNoteStopTests(trg.SameTurnWriter, unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.mkdtemp(dir=trg.RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.scratch, True)
        self.cfg = os.path.join(self.scratch, "cfg")
        os.makedirs(self.cfg)
        self.rows = os.path.join(self.scratch, "route_rows.json")

    def ok(self, name, input_):
        return self.call(name, input_, result="ok")

    def failed(self, name, input_):
        records = self.call(name, input_, result="denied")
        records[1]["message"]["content"][0]["is_error"] = True
        return records

    @staticmethod
    def turn(*records):
        """One turn: the owner's message, the calls, and a prose reply that is no report and asks nothing."""
        return [trg.human("do the task"), *records, trg.assistant_text(PROSE)]

    def stop(self, records, rows=None, surface="cloud", sid=SID, rows_path=None, refuse=False):
        if rows is not None:
            base.write_route_rows(self.rows, rows)
        path = trg.write_transcript(records, self.scratch)
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": False,
                "session_id": sid, "cwd": self.scratch}
        env = base.surface_env(dict(os.environ), surface)
        env["CLAUDE_CONFIG_DIR"] = self.cfg
        env[base.ROUTE_ROWS_ENV] = rows_path or self.rows
        run = trg.run_guard(trg.REPORT_GUARD, hook, env=env, refuse_process=refuse)
        self.assertEqual(run.returncode, 0, run.stderr[-300:])
        return run

    @staticmethod
    def output(run):
        return json.loads(run.stdout) if run.stdout.strip() else None

    def note(self, run):
        """The systemMessage the Stop printed, or "" when it printed none. Never a decision."""
        out = self.output(run)
        if out is None:
            return ""
        self.assertNotIn("decision", out, "the note refused the turn: %r" % out)
        return out.get("systemMessage", "")

    def test_s1_a_successful_call_matching_a_refused_row_adds_a_contradicted_note(self):
        rows = [base.route_row("r-create", CREATE, "refused")]
        out = self.output(self.stop(self.turn(*self.ok(CREATE, {"name": "x"})), rows=rows))
        self.assertIsNotNone(out, "no note: a successful call matched a refused row")
        self.assertNotIn("decision", out, "the note refused the turn: %r" % out)
        msg = out.get("systemMessage", "")
        self.assertIn("r-create", msg, "the note does not name its row: %r" % msg)
        self.assertIn("contradict", msg.lower(), "the note does not say the row is contradicted: %r" % msg)

    def test_s2_a_failed_call_adds_no_note(self):
        rows = [base.route_row("r-create", CREATE, "refused")]
        twin = self.stop(self.turn(*self.ok(CREATE, {"name": "x"})), rows=rows, sid="rf-twin")
        self.assertIn("r-create", self.note(twin), "scope: a successful twin call did not note the row")
        failed = self.stop(self.turn(*self.failed(CREATE, {"name": "x"})), sid="rf-failed")
        self.assertEqual(self.note(failed), "", "an errored call noted a row: %r" % self.note(failed))

    def test_s3_a_works_row_adds_no_note(self):
        rows = [base.route_row("r-create", CREATE, "refused"), base.route_row("r-works", CREATE, "works")]
        msg = self.note(self.stop(self.turn(*self.ok(CREATE, {"name": "x"})), rows=rows))
        self.assertIn("r-create", msg, "scope: the refused row was not noted in the same run")
        self.assertNotIn("r-works", msg, "a row that says works was noted as contradicted")

    def test_s4_a_refused_row_for_the_other_surface_adds_no_note(self):
        rows = [base.route_row("r-cloud", CREATE, "refused", surface="cloud"),
                base.route_row("r-local", CREATE, "refused", surface="local")]
        msg = self.note(self.stop(self.turn(*self.ok(CREATE, {"name": "x"})), rows=rows, surface="cloud"))
        self.assertIn("r-cloud", msg, "scope: the cloud row was not noted in a cloud session")
        self.assertNotIn("r-local", msg, "a local row was noted in a cloud session")

    def test_s5_a_local_refused_row_notes_a_local_session_only(self):
        rows = [base.route_row("r-local", CREATE, "refused", surface="local"),
                base.route_row("r-cloud", CREATE, "refused", surface="cloud")]
        msg = self.note(self.stop(self.turn(*self.ok(CREATE, {"name": "x"})), rows=rows, surface="local"))
        self.assertIn("r-local", msg, "scope: the local row was not noted in a local session")
        self.assertNotIn("r-cloud", msg, "a cloud row was noted in a local session")

    def test_s6_a_bash_row_matches_the_command_text_not_the_tool_name(self):
        rows = [base.route_row("r-cmd", MERGE_CMD, "refused", route="gh-api"),
                base.route_row("r-name", "^Bash$", "refused", route="gh-api")]
        msg = self.note(self.stop(self.turn(*self.ok("Bash", {"command": MERGE_CMD})), rows=rows))
        self.assertIn("r-cmd", msg, "scope: the command-text row was not noted")
        self.assertNotIn("r-name", msg, "a row was matched by the tool name of a Bash call")

    def test_s7_a_row_whose_pattern_matches_no_call_adds_no_note(self):
        rows = [base.route_row("r-hit", CREATE, "refused"), base.route_row("r-miss", "gh pr merge 12", "refused")]
        msg = self.note(self.stop(self.turn(*self.ok(CREATE, {"name": "x"})), rows=rows))
        self.assertIn("r-hit", msg, "scope: the matching row was not noted")
        self.assertNotIn("r-miss", msg, "a row whose pattern matches no call was noted")

    def test_s8_a_row_is_noted_once_per_session(self):
        rows = [base.route_row("r-create", CREATE, "refused")]
        first = self.turn(*self.ok(CREATE, {"name": "x"}))
        self.assertIn("r-create", self.note(self.stop(first, rows=rows)), "scope: the first matching call did not note")
        second = first + self.turn(*self.ok(CREATE, {"name": "y"}))
        self.assertNotIn("r-create", self.note(self.stop(second, rows=rows)),
                         "the row was noted again in the same session")

    def test_s9_a_row_matched_twice_in_one_turn_is_noted_once(self):
        rows = [base.route_row("r-create", CREATE, "refused")]
        msg = self.note(self.stop(self.turn(*self.ok(CREATE, {"name": "x"}), *self.ok(CREATE, {"name": "y"})), rows=rows))
        self.assertIn("r-create", msg, "scope: the matching calls did not note the row")
        self.assertEqual(msg.count("r-create"), 1, "the row was noted %d times in one turn" % msg.count("r-create"))

    def test_s10_a_new_session_gets_its_own_note(self):
        rows = [base.route_row("r-create", CREATE, "refused")]
        first = self.note(self.stop(self.turn(*self.ok(CREATE, {"name": "x"})), rows=rows, sid="rf-a"))
        self.assertIn("r-create", first, "scope: session A did not get its note")
        second = self.note(self.stop(self.turn(*self.ok(CREATE, {"name": "x"})), sid="rf-b"))
        self.assertIn("r-create", second, "the row was not noted again in a new session")

    def test_s11_each_matching_row_gets_its_own_note(self):
        rows = [base.route_row("r-one", CREATE, "refused"),
                base.route_row("r-two", "^mcp__claude-code-remote__create_session$", "refused")]
        msg = self.note(self.stop(self.turn(*self.ok(CREATE, {"name": "x"})), rows=rows))
        self.assertIn("r-one", msg, "scope: the first matching row was not noted")
        self.assertIn("r-two", msg, "the second matching row was not noted")

    def test_s12_a_full_size_rows_file_notes_its_last_matching_row(self):
        rows = [base.route_row("r-%03d" % i, "never-matches-%03d" % i, "refused") for i in range(399)]
        rows.append(base.route_row("r-last", CREATE, "refused"))
        msg = self.note(self.stop(self.turn(*self.ok(CREATE, {"name": "x"})), rows=rows))
        self.assertIn("r-last", msg, "the note does not name the matching row at the end of 400")

    def test_s13_cost_a_note_starts_no_process_and_leaves_the_rows_file_unchanged(self):
        rows = [base.route_row("r-create", CREATE, "refused")]
        base.write_route_rows(self.rows, rows)
        before = read_bytes(self.rows)
        run = self.stop(self.turn(*self.ok(CREATE, {"name": "x"})), refuse=True)
        self.assertIn("r-create", self.note(run), "scope: the matching call did not note the row")
        self.assertNotIn("tried to start a process", run.stderr, "the Stop started a process: %r" % run.stderr[-300:])
        self.assertEqual(read_bytes(self.rows), before, "the Stop wrote the rows file")

    def test_s14_a_missing_or_unreadable_rows_file_passes_quietly(self):
        os.makedirs(os.path.join(self.scratch, "dir-as-rows"))
        cases = (("missing", os.path.join(self.scratch, "absent.json")),
                 ("not json", self.write_text("{not json")),
                 ("rows is not a list", self.write_text('{"rows": 5}')),
                 ("a directory", os.path.join(self.scratch, "dir-as-rows")))
        for label, path in cases:
            with self.subTest(label):
                run = self.stop(self.turn(*self.ok(CREATE, {"name": "x"})), rows_path=path)
                self.assertIsNone(self.output(run), "output with an unreadable rows file: %r" % run.stdout)
                self.assertNotIn("Traceback", run.stderr)

    def test_s15_an_empty_rows_list_passes_quietly(self):
        run = self.stop(self.turn(*self.ok(CREATE, {"name": "x"})), rows=[])
        self.assertIsNone(self.output(run), "output with an empty rows list: %r" % run.stdout)

    def write_text(self, text):
        path = os.path.join(self.scratch, "bad-rows.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path


if __name__ == "__main__":
    unittest.main()
