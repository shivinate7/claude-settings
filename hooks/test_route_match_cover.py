#!/usr/bin/env python3
"""Cases for the cite cover in hooks/route_match.py: a page task's route cite must name a row that covers the
task's act. The rule is the coordinator pick of decision claims-carry-backing, 2026-11-07 15:12 CST.

Run it from the repository root:

    python3 hooks/test_route_match_cover.py

Standard library only, and no test runner. The route-row fixture (route_row) comes from hooks/test_refusal_note.py,
the one home, and is borrowed by name here, not copied. No case writes a file, so this module owns no scratch. The
run folder that the borrowed harness makes at its import is shared with hooks/test_refusal_note_route.py, which
removes it, so this module never removes it.

Contract the builder codes against. Each helper is in hooks/route_match.py:
- act_texts(task) -> list of str. task is a waiting-page task dict. Its "command" is a string, or a dict of variant
  strings such as {"powershell": ..., "mac": ...}, and every value is read. Each line of each command is split at
  "&&" and ";", stripped, and empty pieces are dropped. Each backtick span in "context" is one more piece. A task
  with neither gives [].
- rows_covering(rows, texts) -> the row dicts on this surface (route_match.surface()) whose pattern matches any
  piece, in row order, through the matcher's _compile and MAX_* bounds. No outcome filter.
- cite_covers(rid, rows, texts) -> "covers", "no" or "unknown". A cite covers when its row is in rows_covering.
  It is "unknown" when texts is empty, when no row on this surface holds rid, or when that row has no pattern or
  its pattern does not compile.
  An alternate never covers: an alternate names another act.
- matching_rows(rows, outcome, calls) keeps its behaviour: it matches the whole call target, not each piece.

The surface is forced by patching guard_core.is_cloud, so no case reads the environment. A helper that is missing
fails its case by name, as hooks/test_guard.py cloud_name_check does, and never by a crash.
Scanner rule (building-scanner-respects-strings): not applicable, the patterns are matched against act text.
"""
import os
import re
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import route_match  # noqa: E402  the route matcher, the one home of act text and cover (hooks/route_match.py)
import guard_core  # noqa: E402  the one home of the cloud check, patched per case
import test_refusal_note as base  # noqa: E402  the route-row fixture (one home)

DELETE = "^git push origin --delete\\b"
DELETE_LINE = "git push origin --delete old-branch"
PR_READY = "^gh pr ready\\b"
MCP_PR = "^mcp__github__update_pull_request$"
REPRO_LINES = "cd ~/repo\ngh auth switch -u shivinate7\ngit push origin --delete old-branch"
REPRO_COMMAND = {"mac": REPRO_LINES}
FULL_SIZE_ROWS = 400  # the size of a full rows file: the same bound as test_refusal_note_route's n10 case
CAUSES = {
    "act_texts": "a cite cannot be judged against the act a task names",
    "rows_covering": "no row whose pattern covers an act piece is found",
    "cite_covers": "a route cite is not judged against the act it names",
}


class CoverTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(guard_core, "is_cloud", return_value=True)  # every case is a cloud session
        patcher.start()
        self.addCleanup(patcher.stop)

    def helper(self, name):
        """The named helper of hooks/route_match.py. A missing one fails the case with its name and its cause."""
        fn = getattr(route_match, name, None)
        if not callable(fn):
            self.fail("route_match has no %s: %s" % (name, CAUSES[name]))
        return fn

    def repro_texts(self):
        """The act text of the repro task, with its scope checked first: the delete line is one of its pieces."""
        texts = self.helper("act_texts")({"command": REPRO_COMMAND})
        self.assertIn(DELETE_LINE, texts, "scope: the act text of the delete task lacks its delete line: %r" % texts)
        return texts

    def test_act_texts_splits_each_line_at_and_and_semicolon(self):
        act_texts = self.helper("act_texts")
        self.assertEqual(act_texts({"command": REPRO_LINES}),
                         ["cd ~/repo", "gh auth switch -u shivinate7", DELETE_LINE],
                         "act_texts does not give one piece per line of the command")
        self.assertEqual(act_texts({"command": "cd x && git fetch;  git push origin --delete y ;"}),
                         ["cd x", "git fetch", "git push origin --delete y"],
                         "act_texts does not split at && and ;, or keeps an empty piece")

    def test_act_texts_reads_every_value_of_a_command_dict(self):
        texts = self.helper("act_texts")({"command": {"powershell": DELETE_LINE, "mac": "gh pr ready 12"}})
        self.assertIn(DELETE_LINE, texts, "act_texts does not read the powershell value of a command dict")
        self.assertIn("gh pr ready 12", texts, "act_texts does not read the mac value of a command dict")

    def test_act_texts_reads_each_backtick_span_of_the_context(self):
        texts = self.helper("act_texts")({"context": "Mark PR 1294 ready with `mcp__github__update_pull_request`."})
        self.assertIn("mcp__github__update_pull_request", texts,
                      "act_texts does not read a backtick span of the context")

    def test_rows_covering_returns_the_matching_rows_in_row_order_whatever_their_outcome(self):
        texts = self.repro_texts()
        rows = [base.route_row("ready-asks", PR_READY, "asks"),
                base.route_row("push-refused", DELETE, "refused"),
                base.route_row("status-works", "^git status\\b", "works"),
                base.route_row("push-asks", DELETE, "asks")]
        found = self.helper("rows_covering")(rows, texts)
        self.assertEqual([row["id"] for row in found], ["push-refused", "push-asks"],
                         "rows_covering does not return the rows whose pattern matches an act piece, in row order")

    def test_rows_covering_skips_a_row_on_the_other_surface(self):
        self.assertIsNotNone(re.search(DELETE, DELETE_LINE), "scope: the delete pattern does not match the delete line")
        rows = [base.route_row("push-local", DELETE, "asks", surface="local"),
                base.route_row("push-cloud", DELETE, "asks", surface="cloud")]
        found = self.helper("rows_covering")(rows, [DELETE_LINE])
        self.assertEqual([row["id"] for row in found], ["push-cloud"],
                         "rows_covering returns a row of the other surface, or drops the row of this one")

    def test_rows_covering_skips_a_pattern_over_the_pattern_bound(self):
        # A comment group pads the pattern past the bound without changing what it matches.
        padded = DELETE + "(?#" + "x" * route_match.MAX_PATTERN_CHARS + ")"
        self.assertGreater(len(padded), route_match.MAX_PATTERN_CHARS,
                           "scope: the padded pattern is not over the bound")
        self.assertIsNotNone(re.search(padded, DELETE_LINE), "scope: the padded pattern does not match the delete line")
        rows_covering = self.helper("rows_covering")
        plain = rows_covering([base.route_row("plain", DELETE, "asks")], [DELETE_LINE])
        self.assertEqual([row["id"] for row in plain], ["plain"],
                         "control: the unpadded pattern does not cover the delete line")
        self.assertEqual(rows_covering([base.route_row("padded", padded, "asks")], [DELETE_LINE]), [],
                         "rows_covering matches a pattern over MAX_PATTERN_CHARS")

    def test_a_cite_of_a_pr_ready_row_on_the_delete_task_is_no(self):
        texts = self.repro_texts()
        rows = [base.route_row("pr-ready-asks", PR_READY, "asks")]
        self.assertEqual(self.helper("cite_covers")("pr-ready-asks", rows, texts), "no",
                         "a row for gh pr ready covers a task that deletes a branch")

    def test_a_cite_of_the_delete_row_covers_once_the_cd_and_auth_lines_are_split_off(self):
        texts = self.repro_texts()
        rows = [base.route_row("push-delete", DELETE, "asks")]
        self.assertEqual(self.helper("cite_covers")("push-delete", rows, texts), "covers",
                         "the delete row does not cover the delete line after the cd and auth lines are split off")

    def test_a_one_line_and_chain_covers_on_its_second_piece(self):
        texts = self.helper("act_texts")({"command": "cd x && git push origin --delete y"})
        self.assertIn("git push origin --delete y", texts, "scope: the && chain is not split into its pieces")
        rows = [base.route_row("push-delete", DELETE, "asks")]
        self.assertEqual(self.helper("cite_covers")("push-delete", rows, texts), "covers",
                         "the delete row does not cover the second piece of a one-line && chain")

    def test_two_rows_sharing_a_pattern_cover_either_id(self):
        texts = self.helper("act_texts")({"command": DELETE_LINE})
        self.assertIn(DELETE_LINE, texts, "scope: the delete command is not an act piece")
        rows = [base.route_row("push-delete-a", DELETE, "asks"), base.route_row("push-delete-b", DELETE, "asks")]
        cite_covers = self.helper("cite_covers")
        self.assertEqual(cite_covers("push-delete-a", rows, texts), "covers",
                         "the first of two rows sharing a pattern does not cover")
        self.assertEqual(cite_covers("push-delete-b", rows, texts), "covers",
                         "the second of two rows sharing a pattern does not cover")

    def test_a_backtick_tool_name_in_the_context_covers_a_tool_name_row(self):
        texts = self.helper("act_texts")({"context": "Mark PR 1294 ready with `mcp__github__update_pull_request`."})
        self.assertIn("mcp__github__update_pull_request", texts, "scope: the backtick span is not an act piece")
        rows = [base.route_row("pr-ready-mcp", MCP_PR, "works")]
        self.assertEqual(self.helper("cite_covers")("pr-ready-mcp", rows, texts), "covers",
                         "a tool-name row does not cover its backtick span in the context")

    def test_no_command_and_no_backtick_span_is_unknown(self):
        texts = self.helper("act_texts")({"context": "Delete the stale branch."})
        self.assertEqual(texts, [], "scope: a task with no command and no backtick span has act text: %r" % texts)
        rows = [base.route_row("push-delete", DELETE, "asks")]
        self.assertEqual(self.helper("cite_covers")("push-delete", rows, texts), "unknown",
                         "a task with no act text is judged, not unknown")

    def test_a_row_with_no_pattern_is_unknown(self):
        texts = self.repro_texts()
        row = base.route_row("push-nopattern", DELETE, "asks")
        del row["pattern"]
        self.assertEqual(self.helper("cite_covers")("push-nopattern", [row], texts), "unknown",
                         "a cited row with no pattern is judged, not unknown")

    def test_a_cited_row_whose_pattern_does_not_compile_is_unknown(self):
        texts = self.repro_texts()
        self.assertIsNone(route_match._compile("("),
                          "scope: the pattern '(' compiles, so it is not an uncompilable pattern")
        cite_covers = self.helper("cite_covers")
        self.assertEqual(cite_covers("push-broken", [base.route_row("push-broken", "(", "asks")], texts), "unknown",
                         "a cited row whose pattern does not compile is judged, not unknown")
        self.assertEqual(cite_covers("push-other", [base.route_row("push-other", "^zzz", "asks")], texts), "no",
                         "control: a compiling pattern that matches no act piece is not read as unknown")

    def test_a_row_only_on_the_other_surface_is_unknown(self):
        texts = self.repro_texts()
        self.assertIsNotNone(re.search(DELETE, DELETE_LINE), "scope: the delete pattern does not match the delete line")
        cite_covers = self.helper("cite_covers")
        local_rows = [base.route_row("push-local", DELETE, "asks", surface="local")]
        self.assertEqual(cite_covers("push-local", local_rows, texts), "unknown",
                         "a cited row on the other surface is judged, not unknown")
        self.assertEqual(cite_covers("push-cloud", [base.route_row("push-cloud", DELETE, "asks")], texts), "covers",
                         "control: the same row on this surface does not cover the delete line")

    def test_an_id_no_row_holds_or_an_empty_rows_list_is_unknown(self):
        texts = self.repro_texts()
        rows = [base.route_row("push-delete", DELETE, "asks")]
        cite_covers = self.helper("cite_covers")
        self.assertEqual(cite_covers("no-such-row", rows, texts), "unknown",
                         "a cite of an id that no row holds is judged, not unknown")
        self.assertEqual(cite_covers("push-delete", [], texts), "unknown",
                         "a cite against an empty rows list is judged, not unknown")

    def test_an_alternate_of_a_row_does_not_cover(self):
        texts = self.repro_texts()
        row = base.route_row("ready-alt", PR_READY, "asks")
        # The alternates shape is assumed: no row in hooks/route_rows.json holds one yet.
        row["alternates"] = [{"act": "delete a remote branch", "pattern": DELETE}]
        self.assertIsNotNone(re.search(DELETE, DELETE_LINE),
                             "scope: the alternate's pattern does not match the delete line")
        self.assertEqual(self.helper("cite_covers")("ready-alt", [row], texts), "no",
                         "an alternate of a row covers a task that it does not name")

    def test_a_full_size_rows_file_covers_a_cite_of_its_last_row(self):
        texts = self.repro_texts()
        rows = [base.route_row("r-%03d" % i, "never-matches-%03d" % i, "works") for i in range(FULL_SIZE_ROWS - 1)]
        rows.append(base.route_row("r-last", DELETE, "asks"))
        self.assertEqual(len(rows), FULL_SIZE_ROWS, "scope: the fixture is not the full size")
        self.assertEqual(self.helper("cite_covers")("r-last", rows, texts), "covers",
                         "a cite of the last row of a full-size rows file is not judged")

    def test_matching_rows_still_matches_the_whole_command_target(self):
        """Green control: the cover reads act pieces, and matching_rows keeps its whole-target match. It passes now."""
        rows = [base.route_row("gh-api-works", "^gh api", "works"),
                base.route_row("gh-api-refused", "^gh api", "refused")]

        def bash(command):
            return [("Bash", {"command": command})]

        def ids(found):
            return [row["id"] for row in found]

        gh_api = "gh api repos/acme/widgets"
        self.assertEqual(ids(route_match.matching_rows(rows, "works", bash(gh_api))), ["gh-api-works"],
                         "matching_rows no longer matches a Bash command by its start")
        self.assertEqual(ids(route_match.matching_rows(rows, "refused", bash(gh_api))), ["gh-api-refused"],
                         "matching_rows picks the wrong outcome")
        self.assertEqual(route_match.matching_rows(rows, "works", bash("cd x\n" + gh_api)), [],
                         "matching_rows matches a line after the first: its whole-target match changed")

    def test_an_env_prefixed_act_is_covered_by_the_row_of_its_act(self):
        rows = [base.route_row("pr-ready", PR_READY, "asks")]
        texts = self.helper("act_texts")({"command": "env GH_TOKEN=x gh pr ready 12"})
        self.assertEqual(self.helper("cite_covers")("pr-ready", rows, texts), "covers",
                         "a leading env is kept in the act piece, so the row for gh pr ready does not cover it")

    def test_an_assignment_prefixed_act_is_covered_by_the_row_of_its_act(self):
        rows = [base.route_row("pr-ready", PR_READY, "asks")]
        texts = self.helper("act_texts")({"command": "GH_TOKEN=x gh pr ready 12"})
        self.assertEqual(self.helper("cite_covers")("pr-ready", rows, texts), "covers",
                         "a NAME=value assignment is kept in the act piece, so the row for gh pr ready does not cover it")

    def test_an_or_chained_act_is_covered_by_the_row_of_its_act(self):
        rows = [base.route_row("pr-ready", PR_READY, "asks")]
        texts = self.helper("act_texts")({"command": "false || gh pr ready 12"})
        self.assertEqual(self.helper("cite_covers")("pr-ready", rows, texts), "covers",
                         "act_texts does not split a line at ||, so the row for gh pr ready does not cover its act")


if __name__ == "__main__":
    unittest.main()
