#!/usr/bin/env python3
"""Cases for the cite cover in hooks/route_match.py, judged through the guard surface: a page task's route cite must
name a row whose pattern covers the task's act. Each case is one waiting-page task write judged by guard.data_tool_hit
(test_question_form.guard_hit), on the local surface that its rows file pins. The rule is the coordinator pick of
decision claims-carry-backing, 2026-11-07 15:12 CST.

Run it from the repository root:

    python3 hooks/test_route_match_cover.py

Standard library only, and no test runner. The fixtures are the sibling's: test_question_form.py (rows_at, local_rows,
task_item, entry_of, guard_hit, WHY_RULE) and test_refusal_note.py (route_row, reached through it). No case writes a
file of its own; each rows file is written into the run folder that test_question_form.py makes.

Two of the cases also state the exact output of a helper in hooks/route_match.py, which no guard verdict shows: the
piece list of act_texts, and the row order of rows_covering. Those lines run after the guard part of their case, and a
helper that is missing fails them by name, as hooks/test_guard.py cloud_name_check does.
"""
import os
import re
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import route_match  # noqa: E402  the route matcher, the one home of act text and cover (hooks/route_match.py)
import guard_core  # noqa: E402  the one home of the cloud check, patched by the one case that reads a cloud row
import test_question_form as qf  # noqa: E402  the sibling's guard fixtures, the one home of each (rows, local, guard)

WHY_RULE = qf.WHY_RULE
PASS = ("", "")  # guard_hit's answer for a write the guard lets through
STEPS = ["Open Terminal"]
LINE = "Why yours: the cloud refuses branch deletes"
DELETE_PAT = "^git push origin --delete\\b"
DELETE_LINE = "git push origin --delete old-branch"


REPRO_LINES = "cd ~/repo\ngh auth switch -u shivinate7\ngit push origin --delete old-branch"
CHAIN_LINES = "cd x && git fetch;  git push origin --delete y ;"


def shells(mac_text):
    """A command with both shells, as the guard's command-in-item rule wants. The act is the mac text: the
    powershell text is one plain line, since that rule refuses a bash operator or a bare gh in it."""
    return {"powershell": "Write-Output ready", "mac": mac_text}


REPRO = shells(REPRO_LINES)
PR_READY = "^gh pr ready\\b"
MCP_PR = "^mcp__github__update_pull_request$"
FULL_SIZE_ROWS = 400  # the size of a full rows file: the same bound as test_refusal_note_route's n10 case


def cite(row_id):
    return " (route %s)" % row_id


def row(row_id, pattern, outcome, surface="local"):
    return qf.hook_base.route_row(row_id, pattern, outcome, surface=surface)


def task(context, command=None):
    over = {} if command is None else {"command": command}
    return qf.task_item(STEPS, context=context, **over)


class RouteCover(unittest.TestCase):
    def helper(self, name):
        """The named helper of hooks/route_match.py. A missing one fails the case with its name and its cause."""
        fn = getattr(route_match, name, None)
        if not callable(fn):
            self.fail("route_match has no %s: a helper the cover reads is missing" % name)
        return fn

    def judge(self, rows, context, command=None):
        """The guard's verdict on one waiting-page task write, with `rows` as its rows file, on the local surface."""
        path = qf.rows_at(self._testMethodName + ".json", rows)
        with qf.local_rows(path):
            self.assertEqual(route_match.surface(), "local",
                             "scope: the surface is not local, so the cite is judged on the wrong rows")
            return qf.guard_hit("set", qf.entry_of(task(context, command)))

    def assertPasses(self, rows, context, command, message):
        hit = self.judge(rows, context, command)
        self.assertEqual(hit, PASS, "%s: the guard gave %r" % (message, hit))

    def assertRefused(self, rows, context, command, message):
        hit = self.judge(rows, context, command)
        self.assertEqual(hit[0], WHY_RULE, "%s: the guard gave %r" % (message, hit))

    def rows_on_local(self, rows):
        """Opens the local rows seam for `rows`, so a helper that reads the rows file sees the same rows."""
        return qf.local_rows(qf.rows_at(self._testMethodName + "-helper.json", rows))

    def test_act_texts_splits_each_line_at_and_and_semicolon(self):
        rows = [row("push-delete", DELETE_PAT, "asks"), row("chain-row", "^cd x && git fetch", "asks")]
        chain = shells(CHAIN_LINES)
        self.assertPasses(rows, LINE + cite("push-delete") + ".", chain,
                          "the delete piece of a chain is not covered by its row")
        self.assertRefused(rows, LINE + cite("chain-row") + ".", chain,
                           "a row that matches the unsplit chain covers it, so the chain is not split at && and ;")
        act_texts = self.helper("act_texts")
        self.assertEqual(act_texts({"command": CHAIN_LINES}), ["cd x", "git fetch", "git push origin --delete y"],
                         "act_texts does not give one piece per && or ; piece, or keeps an empty piece")
        self.assertEqual(act_texts({"command": REPRO_LINES}),
                         ["cd ~/repo", "gh auth switch -u shivinate7", DELETE_LINE],
                         "act_texts does not give one piece per line of the command")

    def test_act_texts_reads_every_value_of_a_command_dict(self):
        rows = [row("push-delete", DELETE_PAT, "asks"), row("ready-asks", PR_READY, "asks"),
                row("zzz", "^zzz", "asks")]
        variants = {"powershell": DELETE_LINE, "mac": "gh auth switch -u shivinate7\ngh pr ready 12"}
        self.assertPasses(rows, LINE + cite("push-delete") + ".", variants,
                          "the powershell value of the command dict is not read as an act")
        self.assertPasses(rows, LINE + cite("ready-asks") + ".", variants,
                          "the mac value of the command dict is not read as an act")
        self.assertRefused(rows, LINE + cite("zzz") + ".", variants,
                           "a cite that matches no value of the command dict is not refused")

    def test_act_texts_reads_each_backtick_span_of_the_context(self):
        rows = [row("mcp-asks", MCP_PR, "asks"), row("ready-asks", PR_READY, "asks")]
        self.assertPasses(rows, LINE + cite("mcp-asks") + ", so I ran `mcp__github__update_pull_request`.", None,
                          "a backtick span of the context is not read as an act")
        self.assertRefused(rows, LINE + cite("ready-asks") + ", so I ran `mcp__github__update_pull_request`.", None,
                           "a cite that covers no backtick span of the context is not refused")

    def test_rows_covering_returns_the_matching_rows_in_row_order_whatever_their_outcome(self):
        rows = [row("ready-asks", PR_READY, "asks"), row("push-refused", DELETE_PAT, "refused"),
                row("status-works", "^git status\\b", "works"), row("push-asks", DELETE_PAT, "asks")]
        self.assertPasses(rows, LINE + cite("push-refused") + ".", REPRO,
                          "a refused row that matches the delete is not counted as covering it")
        self.assertPasses(rows, LINE + cite("push-asks") + ".", REPRO,
                          "a row that matches the delete does not cover it")
        self.assertRefused(rows, LINE + cite("ready-asks") + ".", REPRO,
                           "a row whose pattern matches no piece of the delete covers it")
        texts = self.helper("act_texts")({"command": REPRO_LINES})
        rows_covering = self.helper("rows_covering")
        with self.rows_on_local(rows):
            found = rows_covering(rows, texts)
        self.assertEqual([r["id"] for r in found], ["push-refused", "push-asks"],
                         "rows_covering does not return the matching rows in row order")

    def test_rows_covering_skips_a_row_on_the_other_surface(self):
        self.assertIsNotNone(re.search(DELETE_PAT, DELETE_LINE), "scope: the delete pattern does not match the delete line")
        rows = [row("push-local", DELETE_PAT, "asks", surface="local"),
                row("push-cloud", DELETE_PAT, "asks", surface="cloud"),
                row("ready-asks", PR_READY, "asks", surface="local")]
        self.assertPasses(rows, LINE + cite("push-local") + ".", REPRO,
                          "a row on this surface that matches the delete is not counted as covering it")
        self.assertRefused(rows, LINE + cite("push-cloud") + cite("ready-asks") + ".", REPRO,
                           "a row on the other surface is counted as covering the delete")
        texts = self.helper("act_texts")({"command": REPRO_LINES})
        with self.rows_on_local(rows):
            found = self.helper("rows_covering")(rows, texts)
        self.assertEqual([r["id"] for r in found], ["push-local"],
                         "rows_covering returns a row of the other surface, or drops the row of this one")

    def test_rows_covering_skips_a_pattern_over_the_pattern_bound(self):
        # A comment group pads the pattern past the bound without changing what it matches.
        padded = DELETE_PAT + "(?#" + "x" * route_match.MAX_PATTERN_CHARS + ")"
        self.assertGreater(len(padded), route_match.MAX_PATTERN_CHARS,
                           "scope: the padded pattern is not over the bound")
        self.assertIsNotNone(re.search(padded, DELETE_LINE), "scope: the padded pattern does not match the delete line")
        rows = [row("plain", DELETE_PAT, "asks"), row("padded", padded, "asks"), row("ready-asks", PR_READY, "asks")]
        self.assertPasses(rows, LINE + cite("plain") + ".", REPRO,
                          "control: the unpadded pattern does not cover the delete line")
        self.assertRefused(rows, LINE + cite("padded") + cite("ready-asks") + ".", REPRO,
                           "a pattern over MAX_PATTERN_CHARS covers the delete line")
        with self.rows_on_local(rows):
            found = self.helper("rows_covering")([row("padded", padded, "asks")], [DELETE_LINE])
        self.assertEqual(found, [], "rows_covering matches a pattern over MAX_PATTERN_CHARS")

    def test_a_cite_of_a_pr_ready_row_on_the_delete_task_is_no(self):
        rows = [row("pr-ready-asks", PR_READY, "asks")]
        self.assertRefused(rows, LINE + cite("pr-ready-asks") + ".", REPRO,
                           "a row for gh pr ready covers a task that deletes a branch")

    def test_a_cite_of_the_delete_row_covers_once_the_cd_and_auth_lines_are_split_off(self):
        rows = [row("push-delete", DELETE_PAT, "asks")]
        self.assertPasses(rows, LINE + cite("push-delete") + ".", REPRO,
                          "the delete row does not cover the delete line after the cd and auth lines are split off")

    def test_a_one_line_and_chain_covers_on_its_second_piece(self):
        rows = [row("push-delete", DELETE_PAT, "asks"), row("chain-row", "^cd x && git push", "asks")]
        cmd = shells("cd x && git push origin --delete y")
        self.assertPasses(rows, LINE + cite("push-delete") + ".", cmd,
                          "the delete row does not cover the second piece of a one-line && chain")
        self.assertRefused(rows, LINE + cite("chain-row") + ".", cmd,
                           "a row that matches the unsplit one-line chain covers it")

    def test_two_rows_sharing_a_pattern_cover_either_id(self):
        rows = [row("push-delete-a", DELETE_PAT, "asks"), row("push-delete-b", DELETE_PAT, "asks"),
                row("ready-asks", PR_READY, "asks")]
        self.assertPasses(rows, LINE + cite("push-delete-a") + ".", REPRO,
                          "the first of two rows sharing a pattern does not cover")
        self.assertPasses(rows, LINE + cite("push-delete-b") + ".", REPRO,
                          "the second of two rows sharing a pattern does not cover")
        self.assertRefused(rows, LINE + cite("ready-asks") + ".", REPRO,
                           "a row sharing no pattern with the delete covers it")

    def test_a_backtick_tool_name_in_the_context_covers_a_tool_name_row(self):
        rows = [row("pr-ready-mcp", MCP_PR, "asks"), row("ready-asks", PR_READY, "asks")]
        self.assertPasses(rows, LINE + cite("pr-ready-mcp") + ", so I ran `mcp__github__update_pull_request`.", None,
                          "a tool-name row does not cover its backtick span in the context")
        self.assertRefused(rows, LINE + cite("pr-ready-mcp") + ", so I ran `gh pr ready 12`.", None,
                           "a row whose pattern matches no span covers the context's gh pr ready span")

    def test_no_command_and_no_backtick_span_is_unknown(self):
        rows = [row("push-delete", DELETE_PAT, "asks")]
        self.assertPasses(rows, LINE + cite("push-delete") + ".", None,
                          "a task with no act text is refused on its cite, though its cover is unknown")

    def test_a_row_with_no_pattern_is_unknown(self):
        nopattern = row("push-nopattern", DELETE_PAT, "asks")
        del nopattern["pattern"]
        self.assertPasses([nopattern], LINE + cite("push-nopattern") + ".", REPRO,
                          "a cited row with no pattern is refused, though its cover is unknown")

    def test_a_cited_row_whose_pattern_does_not_compile_is_unknown(self):
        with self.assertRaises(re.error, msg="scope: the pattern '(' compiles, so it is not an uncompilable pattern"):
            re.compile("(")
        self.assertPasses([row("push-broken", "(", "asks")], LINE + cite("push-broken") + ".", REPRO,
                          "a cited row whose pattern does not compile is refused, though its cover is unknown")
        self.assertRefused([row("push-other", "^zzz", "asks")], LINE + cite("push-other") + ".", REPRO,
                           "control: a compiling pattern that matches no act piece is not refused")

    def test_a_row_only_on_the_other_surface_is_unknown(self):
        self.assertIsNotNone(re.search(DELETE_PAT, DELETE_LINE), "scope: the delete pattern does not match the delete line")
        self.assertPasses([row("push-cloud", DELETE_PAT, "asks", surface="cloud")],
                          LINE + cite("push-cloud") + ".", REPRO,
                          "a cited row on the other surface is refused, though its cover is unknown")
        self.assertPasses([row("push-local", DELETE_PAT, "asks")], LINE + cite("push-local") + ".", REPRO,
                          "control: the same row on this surface does not cover the delete line")
        self.assertRefused([row("push-cloud", DELETE_PAT, "asks", surface="cloud"),
                            row("ready-asks", PR_READY, "asks")],
                           LINE + cite("push-cloud") + cite("ready-asks") + ".", REPRO,
                           "a cloud-only row covers a delete on the local surface")

    def test_an_id_no_row_holds_or_an_empty_rows_list_is_unknown(self):
        # Helper contract only: the guard refuses a cite no row holds (hooks/test_question_form.py, the empty rows
        # file case), so the cover's unknown is not a guard verdict. Listed in the commit as a conflict to rule on.
        texts = self.helper("act_texts")({"command": REPRO_LINES})
        cite_covers = self.helper("cite_covers")
        rows = [row("push-delete", DELETE_PAT, "asks")]
        with self.rows_on_local(rows):
            self.assertEqual(cite_covers("no-such-row", rows, texts), "unknown",
                             "a cite of an id that no row holds is judged, not unknown")
            self.assertEqual(cite_covers("push-delete", [], texts), "unknown",
                             "a cite against an empty rows list is judged, not unknown")

    def test_an_alternate_of_a_row_does_not_cover(self):
        alt = row("ready-alt", PR_READY, "asks")
        # The alternates shape is assumed: no row in hooks/route_rows.json holds one yet.
        alt["alternates"] = [{"act": "delete a remote branch", "pattern": DELETE_PAT}]
        self.assertIsNotNone(re.search(DELETE_PAT, DELETE_LINE),
                             "scope: the alternate's pattern does not match the delete line")
        self.assertRefused([alt], LINE + cite("ready-alt") + ".", REPRO,
                           "an alternate of a row covers a task that it does not name")

    def test_a_full_size_rows_file_covers_a_cite_of_its_last_row(self):
        rows = [row("r-%03d" % i, "never-matches-%03d" % i, "works") for i in range(FULL_SIZE_ROWS - 1)]
        rows.append(row("r-last", DELETE_PAT, "asks"))
        self.assertEqual(len(rows), FULL_SIZE_ROWS, "scope: the fixture is not the full size")
        self.assertPasses(rows, LINE + cite("r-last") + ".", REPRO,
                          "a cite of the last row of a full-size rows file is refused")

    def test_matching_rows_still_matches_the_whole_command_target(self):
        """Green control: the cover reads act pieces, and matching_rows keeps its whole-target match. It passes now."""
        rows = [qf.hook_base.route_row("gh-api-works", "^gh api", "works"),
                qf.hook_base.route_row("gh-api-refused", "^gh api", "refused")]

        def bash(command):
            return [("Bash", {"command": command})]

        def ids(found):
            return [row_found["id"] for row_found in found]

        gh_api = "gh api repos/acme/widgets"
        with mock.patch.object(guard_core, "is_cloud", return_value=True):  # every row here is a cloud row
            self.assertEqual(ids(route_match.matching_rows(rows, "works", bash(gh_api))), ["gh-api-works"],
                             "matching_rows no longer matches a Bash command by its start")
            self.assertEqual(ids(route_match.matching_rows(rows, "refused", bash(gh_api))), ["gh-api-refused"],
                             "matching_rows picks the wrong outcome")
            self.assertEqual(route_match.matching_rows(rows, "works", bash("cd x\n" + gh_api)), [],
                             "matching_rows matches a line after the first: its whole-target match changed")

    def test_an_env_prefixed_act_is_covered_by_the_row_of_its_act(self):
        cmd = shells("gh auth switch -u shivinate7\nenv GH_TOKEN=x gh pr ready 12")
        self.assertPasses([row("pr-ready", PR_READY, "asks")], LINE + cite("pr-ready") + ".", cmd,
                          "a leading env is kept in the act piece, so the row for gh pr ready does not cover it")
        self.assertRefused([row("env-row", "^env ", "asks")], LINE + cite("env-row") + ".", cmd,
                           "a leading env is kept in the act piece, so a row for the env prefix covers it")

    def test_an_assignment_prefixed_act_is_covered_by_the_row_of_its_act(self):
        cmd = shells("gh auth switch -u shivinate7\nGH_TOKEN=x gh pr ready 12")
        self.assertPasses([row("pr-ready", PR_READY, "asks")], LINE + cite("pr-ready") + ".", cmd,
                          "a NAME=value assignment is kept in the act piece, so the row for gh pr ready does not cover it")
        self.assertRefused([row("assign-row", "^GH_TOKEN=", "asks")], LINE + cite("assign-row") + ".", cmd,
                           "a NAME=value assignment is kept in the act piece, so a row for the assignment covers it")

    def test_an_or_chained_act_is_covered_by_the_row_of_its_act(self):
        cmd = shells("gh auth switch -u shivinate7\nfalse || gh pr ready 12")
        self.assertPasses([row("pr-ready", PR_READY, "asks")], LINE + cite("pr-ready") + ".", cmd,
                          "act_texts does not split a line at ||, so the row for gh pr ready does not cover its act")
        self.assertRefused([row("unsplit-row", "^false \\|\\|", "asks")], LINE + cite("unsplit-row") + ".", cmd,
                           "act_texts does not split a line at ||, so a row for the unsplit line covers it")


if __name__ == "__main__":
    unittest.main()
