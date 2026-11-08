#!/usr/bin/env python3
"""Cases for the route-row note in hooks/refusal_note.py: a refused call that a route row says works is
contradicted, so the hook adds a note to the refusal's own row. The falsifier compares real acts with route
rows (the Stop half, the same note for a successful call a row says is refused, is
lint/test_report_guard_falsifier.py).

Run it from the repository root:

    python3 hooks/test_refusal_note_route.py

Standard library only. The hook harness (HookCase, fire, refusal_rows, files_written) and the route-row
fixture (route_row, write_route_rows, surface_env, ROUTE_ROWS_ENV) come from hooks/test_refusal_note.py. The
cost case runs the hook through run_guard in its no-process mode, from lint/test_report_guard.py. Each is
borrowed by name here, not copied.

Contract the builder codes against, pinned by these cases:
- The rows file's path is the env named by ROUTE_ROWS_ENV (GUARD_ROUTE_ROWS). It is {"rows": [...]}.
- Surface: "cloud" when CLAUDE_CODE_REMOTE is "true" (hooks/guard_core.is_cloud), else "local".
- A row matches a call when its surface is the current one, its outcome is "works", and its pattern matches the
  call. The target is the Bash command text for a Bash call, and the tool name for any other call. Cases use
  patterns where a whole-target match and a search agree.
- A contradicted refusal adds one key, `note`, to its own row. The note names the row id and says "contradicted".
  The hook prints nothing: PermissionDenied reads only a retry decision.
- A refusal with no matching row, or whose matching row says refused, adds no key: the row keeps its base keys.
- A missing or unreadable rows file: the row is still written, the hook prints nothing and exits 0.
- Cost: the hook starts no process, and writes only the refusals file. It never writes the rows file.
- Scanner rule (building-scanner-respects-strings): not applicable, the pattern is a regex over a call's target, not a source scan.
"""
import os
import shutil
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_refusal_note as base  # noqa: E402  the hook harness and the route-row fixture (one home)
sys.path.insert(0, os.path.join(HERE, "..", "lint"))
import test_report_guard as trg  # noqa: E402  run_guard and NO_PROCESS_CODE (one home)
import route_match  # noqa: E402  the rows matcher and its size limits (hooks/route_match.py)

ARCHIVE = base.ARCHIVE
BASE_KEYS = {"ts", "tool_name", "reason", "tool_use_id"}
BASH_REASON = "Permission for Bash was denied by the auto-mode classifier."
CMD = "gh api repos/acme/widgets/merge"


def read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def tearDownModule():
    shutil.rmtree(base.RUN, ignore_errors=True)  # the harness's run folder, made at its import
    shutil.rmtree(trg.RUN_FOLDER, ignore_errors=True)  # the lint runner's run folder, made at its import


class RouteNoteTests(base.HookCase):
    def rows_path(self):
        return os.path.join(self.scratch, "route_rows.json")

    def run_refusal(self, data, rows_path=None, surface="cloud", refuse=False):
        env = base.surface_env(self.env(), surface)
        env[base.ROUTE_ROWS_ENV] = rows_path or self.rows_path()
        if refuse:
            return trg.run_guard(base.HOOK, data, env=env, refuse_process=True)
        return self.fire(data, env=env)

    def bash_refusal(self, use_id, session=base.SESSION):
        data = self.refusal(tool="Bash", reason=BASH_REASON, use_id=use_id, session=session)
        data["tool_input"] = {"command": CMD}
        return data

    def row_for(self, use_id, session=base.SESSION):
        """The refusal row the hook wrote for `use_id`. Scope: the row must exist before its note is judged."""
        rows = self.refusal_rows(session=session, skip_bad=True)
        found = [row for row in rows if row.get("tool_use_id") == use_id]
        self.assertEqual(len(found), 1, "scope: the refusal %s did not write one row: %r" % (use_id, rows))
        return found[0]

    def note_of(self, row):
        self.assertIn("route_flag", row, "the refusal row carries no note: %r" % row)
        return row["route_flag"]

    def assert_no_note(self, row):
        self.assertEqual(set(row), BASE_KEYS, "the refusal row carries a key it should not: %r" % row)

    def test_n1_a_works_row_for_the_cloud_surface_adds_a_contradicted_note(self):
        base.write_route_rows(self.rows_path(), [base.route_row("r-archive", ARCHIVE, "works", surface="cloud")])
        run = self.run_refusal(self.refusal(use_id="toolu_n1"), surface="cloud")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.strip(), "", "the hook printed on a noted refusal: %r" % run.stdout)
        note = self.note_of(self.row_for("toolu_n1"))
        self.assertIn("r-archive", note, "the note does not name its row: %r" % note)
        self.assertIn("contradict", note.lower(), "the note does not say the row is contradicted: %r" % note)

    def test_n2_a_bash_row_matches_the_command_text(self):
        base.write_route_rows(self.rows_path(), [base.route_row("r-bash", CMD, "works", route="gh-api")])
        run = self.run_refusal(self.bash_refusal("toolu_n2"), surface="cloud")
        self.assertEqual(run.returncode, 0, run.stderr)
        note = self.note_of(self.row_for("toolu_n2"))
        self.assertIn("r-bash", note, "the note does not name its row: %r" % note)
        self.assertIn("contradict", note.lower(), "the note does not say the row is contradicted: %r" % note)

    def test_n3_a_bash_row_is_not_matched_by_the_tool_name(self):
        base.write_route_rows(self.rows_path(), [base.route_row("r-named", "^Bash$", "works", route="gh-api")])
        self.run_refusal(self.bash_refusal("toolu_n3"), surface="cloud")
        self.assert_no_note(self.row_for("toolu_n3"))

    def test_n4_a_refused_row_adds_no_note(self):
        base.write_route_rows(self.rows_path(), [base.route_row("r-refused", ARCHIVE, "refused", surface="cloud")])
        self.run_refusal(self.refusal(use_id="toolu_n4"), surface="cloud")
        self.assert_no_note(self.row_for("toolu_n4"))

    def test_n5_a_row_that_matches_no_call_adds_no_note(self):
        base.write_route_rows(self.rows_path(), [base.route_row("r-other", "gh pr merge 12", "works", surface="cloud")])
        self.run_refusal(self.refusal(use_id="toolu_n5"), surface="cloud")
        self.assert_no_note(self.row_for("toolu_n5"))

    def test_n6_a_local_row_adds_a_note_in_a_local_session(self):
        base.write_route_rows(self.rows_path(), [base.route_row("r-local", ARCHIVE, "works", surface="local")])
        run = self.run_refusal(self.refusal(use_id="toolu_n6"), surface="local")
        self.assertEqual(run.returncode, 0, run.stderr)
        note = self.note_of(self.row_for("toolu_n6"))
        self.assertIn("r-local", note, "the note does not name its row: %r" % note)

    def test_n7_a_local_row_adds_no_note_in_a_cloud_session(self):
        base.write_route_rows(self.rows_path(), [base.route_row("r-local", ARCHIVE, "works", surface="local")])
        self.run_refusal(self.refusal(use_id="toolu_n7"), surface="cloud")
        self.assert_no_note(self.row_for("toolu_n7"))

    def test_n8_a_cloud_row_adds_no_note_in_a_local_session(self):
        base.write_route_rows(self.rows_path(), [base.route_row("r-cloud", ARCHIVE, "works", surface="cloud")])
        self.run_refusal(self.refusal(use_id="toolu_n8"), surface="local")
        self.assert_no_note(self.row_for("toolu_n8"))

    def test_n9_an_empty_rows_list_adds_no_note(self):
        base.write_route_rows(self.rows_path(), [])
        self.run_refusal(self.refusal(use_id="toolu_n9"), surface="cloud")
        self.assert_no_note(self.row_for("toolu_n9"))

    def test_n10_a_full_size_rows_file_notes_its_last_matching_row(self):
        rows = [base.route_row("r-%03d" % i, "never-matches-%03d" % i, "works") for i in range(399)]
        rows.append(base.route_row("r-last", ARCHIVE, "works"))
        base.write_route_rows(self.rows_path(), rows)
        run = self.run_refusal(self.refusal(use_id="toolu_n10"), surface="cloud")
        self.assertEqual(run.returncode, 0, run.stderr)
        note = self.note_of(self.row_for("toolu_n10"))
        self.assertIn("r-last", note, "the note does not name the matching row at the end of 400: %r" % note)

    def test_n11_a_missing_rows_file_writes_the_row_and_adds_no_note(self):
        run = self.run_refusal(self.refusal(use_id="toolu_n11"), rows_path=os.path.join(self.scratch, "absent.json"))
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.strip(), "", "the hook printed with no rows file: %r" % run.stdout)
        self.assertNotIn("Traceback", run.stderr)
        self.assert_no_note(self.row_for("toolu_n11"))

    def test_n12_an_unreadable_rows_file_writes_the_row_and_adds_no_note(self):
        bad = (("not json", "{not json"), ("rows is not a list", '{"rows": 5}'), ("a directory", None))
        for index, (label, text) in enumerate(bad):
            with self.subTest(label):
                session = "rn12-%d" % index
                path = os.path.join(self.scratch, "bad-%d.json" % index)
                if text is None:
                    os.makedirs(path)
                else:
                    with open(path, "w", encoding="utf-8") as handle:
                        handle.write(text)
                run = self.run_refusal(self.refusal(use_id="toolu_n12_%d" % index, session=session), rows_path=path)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(run.stdout.strip(), "", "the hook printed with an unreadable rows file: %r" % run.stdout)
                self.assertNotIn("Traceback", run.stderr)
                self.assert_no_note(self.row_for("toolu_n12_%d" % index, session=session))

    def test_n13_cost_a_note_starts_no_process_and_writes_only_the_refusals_file(self):
        base.write_route_rows(self.rows_path(), [base.route_row("r-archive", ARCHIVE, "works", surface="cloud")])
        before = read_bytes(self.rows_path())
        run = self.run_refusal(self.refusal(use_id="toolu_n13"), surface="cloud", refuse=True)
        self.assertNotIn("tried to start a process", run.stderr, "the hook started a process: %r" % run.stderr[-300:])
        self.assertEqual(run.returncode, 0, run.stderr[-300:])
        self.note_of(self.row_for("toolu_n13"))
        self.assertEqual(self.files_written(), [os.path.join("state", base.REFUSALS_DIR, base.SESSION + ".jsonl")],
                         "the hook wrote a file besides the refusals file")
        self.assertEqual(read_bytes(self.rows_path()), before, "the hook wrote the rows file")


class RouteMatchLimitTests(unittest.TestCase):
    """hooks/route_match.py's two size limits, MAX_PATTERN_CHARS (500) and MAX_TARGET_CHARS (4000). Each limit is
    driven at its value and one past it. The limits are pinned as literal lengths, so a change to either one moves the
    boundary these cases check. No case here is red on the base code: they pin behaviour the code already has."""

    def row(self, pattern):
        return {"id": "r1", "act": "a", "route": "b", "surface": "local", "outcome": "works", "pattern": pattern}

    def matches(self, pattern, command):
        with mock.patch.object(route_match, "surface", return_value="local"):
            rows = route_match.matching_rows([self.row(pattern)], "works", [("Bash", {"command": command})])
        return bool(rows)

    def test_pattern_of_500_chars_is_matched(self):
        self.assertTrue(self.matches("b" * 500, "b" * 500), "a pattern at MAX_PATTERN_CHARS (500) was skipped")

    def test_pattern_of_501_chars_is_skipped(self):
        self.assertFalse(self.matches("b" * 501, "b" * 501), "a pattern one past MAX_PATTERN_CHARS (500) was matched")

    def test_match_that_ends_at_4000_chars_is_found(self):
        self.assertTrue(self.matches("ACT", "x" * 3997 + "ACT"), "a match that ends at MAX_TARGET_CHARS (4000) was missed")

    def test_match_that_starts_at_4000_chars_is_not_searched(self):
        self.assertFalse(self.matches("ACT", "x" * 4000 + "ACT"),
                         "a match that starts past MAX_TARGET_CHARS (4000) was searched")

    def test_match_whose_last_char_is_one_past_4000_chars_is_not_found(self):
        self.assertFalse(self.matches("ACT", "x" * 3998 + "ACT"),
                         "a match whose last char is one past MAX_TARGET_CHARS (4000) was found")


if __name__ == "__main__":
    unittest.main()
