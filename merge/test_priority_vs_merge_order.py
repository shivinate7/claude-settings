#!/usr/bin/env python3
"""Fixture suite for the priority check on `merge N --confirm --priority-rows FILE` (merge/merge.py): a lower pull request does not go
while a priority row's own pull request is ready, and the line says why when a lower one goes anyway.

Run: python3 merge/test_priority_vs_merge_order.py

WHAT IT PROVES. With FILE, the confirm reads each priority row with priority_row and priority_verdict. It refuses to merge PR N when N is
not a row's own PR and some row's PR is ok (ready, clean, newest runs green), and it names that row's slug and PR. An open pull request
whose base is not main is never ok: its row reads flag and names the base, and it does not block a pull request that lands on main. Otherwise it merges
and prints one line that says why: a row is flag, waiting or unknown. With no FILE it prints that nothing was checked. An empty or
missing FILE is not clear, and its line says so. A row the reader cannot parse refuses too, and the refusal says it cannot be read. A
refusal lands nothing: no merge, no claim on main, no lock held, no ref moved. A priority pull request costs at most two reads per run,
and its runs only when its verdict needs them.

Each case runs the real --confirm flow in-process on the fixture of merge/test_merge.py (Env, FakeHost), imported and not copied.
PriorityHost scripts the reads of the priority pull requests. The verdict is merge.Host.judge_runs itself.
"""
import contextlib
import io
import pathlib
import re
import sys
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import merge  # noqa: E402
import test_merge as tm  # noqa: E402  the --confirm fixture (Env, FakeHost); its TestCases are not collected here

REPO = "shivinate7/claude-settings"
SLUG = "ci-speed-stack-4"  # the row of the #3302 sequence
OTHER_SLUG = "ci-speed-stack-5"
ROW_3302 = "priority: %s | pr: %s#3302\n" % (SLUG, REPO)
ROW_3303 = "priority: %s | pr: %s#3303\n" % (OTHER_SLUG, REPO)
BRANCH_ROW = "priority: %s | branch: feat-3302\n" % SLUG  # the same pull request, named by its head branch
MALFORMED_SLUG = "ci-speed"  # its pr has no owner/repo, so no row reads it
MALFORMED_ROW = "priority: %s | pr: #3302\n" % MALFORMED_SLUG
LOWER = 3314  # the combined PR the runner merges first
HEAD_3302, HEAD_3303 = "a" * 40, "c" * 40
NO_ROWS_LINE = "priority: no rows given, not checked"
NOT_CLEAR = re.compile(r"(?<!not )\bclear\b")
USAGE = "usage:"  # argparse's first line; it prints that line when it refuses the flags, and then no check runs
VERDICT_START = re.compile(r"\s*(ok|flag|waiting|done|unknown)\b")  # a row's verdict line starts with its verdict


def run_row(sha, name, status, conclusion, run_id):
    """One workflow run on `sha`, in the fields judge_runs reads."""
    return {"name": name, "status": status, "conclusion": conclusion, "databaseId": run_id,
            "workflowDatabaseId": 100 + run_id, "headSha": sha}


def green(sha):
    return [run_row(sha, "checks", "completed", "success", 2)]


def pr_fields(head, branch="feat-3302", **fields):
    """The pr() fields of a priority pull request: open, ready and clean, unless `fields` say otherwise."""
    info = {"head": head, "branch": branch, "base": "main", "state": "OPEN", "mergeable": "MERGEABLE",
            "merge_state": "CLEAN", "draft": False, "body": "", "created": None, "changed_files": None}
    info.update(fields)
    return info


def words(line):
    return set(re.findall(r"[a-z]+", line.lower()))


class PriorityHost(tm.FakeHost):
    """The fake host with each priority pull request's reads scripted. `prio` maps a number to its pr() fields, `prio_runs` a head sha to
    its run rows, `prio_fail` holds the numbers whose pull request read fails, and `prio_error` maps a number to the exception its read
    raises. `prio_open`, when set, is the open pull list a branch row reads; unset, the fake's own list is read. Each read is logged in
    `reads`: `pr N`, `runs <sha>`, `open_prs`."""
    repo = REPO
    judge_runs = staticmethod(merge.Host.judge_runs)  # the real judge, bound and not copied

    def __init__(self, root, other):
        super().__init__(root, other)
        self.reads, self.prio, self.prio_runs, self.prio_fail = [], {}, {}, set()
        self.prio_error, self.prio_open = {}, None

    def pr(self, n):
        self.reads.append(f"pr {n}")
        if n in self.prio_fail:
            raise merge.Stop(f"reading the pull request failed: HTTP 404: Not Found (#{n})")
        if n in self.prio_error:
            raise self.prio_error[n]
        if n in self.prio:
            return dict(self.prio[n])
        return super().pr(n)

    def runs(self, sha):
        self.reads.append(f"runs {sha}")
        return list(self.prio_runs.get(sha, []))

    def open_prs(self):
        self.reads.append("open_prs")
        return super().open_prs() if self.prio_open is None else list(self.prio_open)


class PriorityBeforeMerge(tm.Env):
    """`merge N --confirm --priority-rows FILE` in the --confirm fixture, with the priority pull requests scripted on PriorityHost."""

    def setUp(self):
        super().setUp()
        self.host = PriorityHost(self.co, self.other)
        self.host.own_number = LOWER
        self.rows = pathlib.Path(self.t) / "rows.txt"

    def confirm(self, pr, text):
        """`merge pr --confirm --priority-rows FILE`, FILE holding `text`. -> (rc, out, err); a usage refusal is read as a result."""
        self.rows.write_text(text, encoding="utf-8")
        return self.run_args(str(pr), "--confirm", "--priority-rows", str(self.rows))

    def assert_reached_check(self, out, err):
        """Scope first: the flags reached the check. A usage line means argparse refused them, so no priority check ran."""
        last = (err.strip().splitlines() or [""])[-1]  # the parser's error line, not its usage block
        self.assertFalse(USAGE in err, "the parser refuses --priority-rows with a PR number, so no priority check ran: " + last)

    def priority_lines(self, out, err):
        return [line for line in (out + err).splitlines() if "priority" in line.lower()]

    def line_with(self, out, err, *needles):
        lines = [line for line in (out + err).splitlines() if all(n in line for n in needles)]
        self.assertTrue(lines, "no printed line holds %s:\n%s%s" % (needles, out, err))
        return lines[0]

    def refusal_names(self, out, err, slug, pr):
        """A line that names the row as a refusal does: not the row's own verdict line, which starts with its verdict word."""
        lines = [line for line in (out + err).splitlines()
                 if slug in line and pr in line and not VERDICT_START.match(line)]
        self.assertTrue(lines, "no refusal line names %s %s:\n%s%s" % (slug, pr, out, err))

    def assert_merged(self, rc, out, err):
        self.assertEqual(rc, 0, "the merge should proceed and exit 0: " + out + err)
        self.assertTrue(getattr(self.host, "merged", False), "the merge did not land: " + out + err)

    def assert_refused_lands_nothing(self, rc, refs0, claims0):
        self.assertNotEqual(rc, 0, "a refused merge exits nonzero")
        self.assertFalse(getattr(self.host, "merged", False), "the refused PR merged")
        self.assertEqual(self.claims(), claims0, "the refusal pushed a claim on main")
        self.assertFalse(self.lock_ref(), "the refusal left the merge lock held")
        self.assertEqual(self.refs(), refs0, "the refusal moved a ref on origin")

    def assert_not_clear_line(self, out, err):
        lines = self.priority_lines(out, err)
        self.assertTrue(any(re.search(r"not (clear|checked)", line) for line in lines),
                        "an empty or missing FILE must say it is not clear: " + out + err)
        for line in lines:
            self.assertIsNone(NOT_CLEAR.search(line), "the line reads as clear: " + line)

    def assert_cannot_be_read(self, out, err):
        """A row the reader cannot parse: the refusal says the row cannot be read, and that nothing is clear."""
        self.assertIn("cannot be read", out + err, "a row the reader cannot parse must say it cannot be read: " + out + err)
        self.assertIn("not clear", out + err, "a row the reader cannot parse must say it is not clear: " + out + err)

    def lower_goes_with(self, info, runs, status, why):
        """A priority row whose PR reads as `info`, with `runs` on its head, does not block a lower pull request. The lower one merges, and the row's line says `status` and `why`."""
        self.host.prio[3302] = info
        self.host.prio_runs[HEAD_3302] = runs
        rc, out, err = self.confirm(LOWER, ROW_3302)
        self.assert_reached_check(out, err)
        line = self.line_with(out, err, SLUG, "#3302")
        self.assertIn(status, words(line), "want %s on the row's line: %s" % (status, line))
        self.assertIn(why, line, "want the reason %r on the row's line: %s" % (why, line))
        self.assertIsNone(NOT_CLEAR.search(line), "the row's line reads as clear: " + line)
        self.assert_merged(rc, out, err)

    def both_rows_ok_merge(self, own):
        """Rows 3302 and 3303 are both ok, and `own` is merged. Its own row reads through the fixture's own pull request (head: feat);
        the other row is scripted."""
        self.host.own_number = own
        other, other_head = (3303, HEAD_3303) if own == 3302 else (3302, HEAD_3302)
        self.host.prio[other] = pr_fields(other_head, branch="feat-%d" % other)
        self.host.prio_runs[other_head] = green(other_head)
        self.host.prio_runs[self.head()] = green(self.head())
        rc, out, err = self.confirm(own, ROW_3302 + ROW_3303)
        self.assert_reached_check(out, err)
        self.assert_merged(rc, out, err)

    # The #3302 sequence: a ready priority row refuses the lower combined PR.

    def test_the_3302_sequence_refuses_the_lower_combined_pr(self):
        self.host.prio[3302] = pr_fields(HEAD_3302)
        self.host.prio_runs[HEAD_3302] = green(HEAD_3302)
        refs0, claims0 = self.refs(), self.claims()
        rc, out, err = self.confirm(LOWER, ROW_3302)
        self.assert_reached_check(out, err)
        self.refusal_names(out, err, SLUG, "#3302")
        self.assert_refused_lands_nothing(rc, refs0, claims0)

    def test_merging_the_priority_pr_itself_passes_under_its_own_ready_row(self):
        head = self.head()
        self.host.own_number = 3302
        self.host.prio_runs[head] = green(head)
        rc, out, err = self.confirm(3302, ROW_3302)
        self.assert_reached_check(out, err)
        self.assert_merged(rc, out, err)

    def test_no_rows_given_says_nothing_was_checked_and_reads_no_priority_pr(self):
        self.host.prio[3302] = pr_fields(HEAD_3302)
        self.host.prio_runs[HEAD_3302] = green(HEAD_3302)
        rc, out, err = self.run_args(str(LOWER), "--confirm", host=self.host)
        self.assert_merged(rc, out, err)
        self.assertIn(NO_ROWS_LINE, out + err, "a merge given no rows says nothing was checked: " + out + err)
        self.assertEqual([r for r in self.host.reads if r in ("pr 3302", "runs " + HEAD_3302)], [],
                         "no rows given, so no priority pull request is read")

    def test_a_draft_priority_pr_lets_the_lower_pr_go_and_says_why(self):
        self.lower_goes_with(pr_fields(HEAD_3302, draft=True), [], "flag", "draft")

    def test_a_dirty_priority_pr_lets_the_lower_pr_go_and_says_why(self):
        self.lower_goes_with(pr_fields(HEAD_3302, mergeable="CONFLICTING", merge_state="DIRTY"), green(HEAD_3302), "flag", "dirty")

    def test_a_red_priority_pr_lets_the_lower_pr_go_and_says_why(self):
        red = [run_row(HEAD_3302, "checks", "completed", "failure", 3)]
        self.lower_goes_with(pr_fields(HEAD_3302), red, "flag", "workflow checks: failure")

    def test_a_pending_priority_pr_is_waiting_and_the_lower_pr_goes(self):
        pending = [run_row(HEAD_3302, "checks", "in_progress", None, 4)]
        self.lower_goes_with(pr_fields(HEAD_3302), pending, "waiting", "workflow checks")

    def test_an_unreadable_priority_pr_is_unknown_never_clear_and_the_lower_pr_goes(self):
        self.host.prio_fail.add(3302)
        rc, out, err = self.confirm(LOWER, ROW_3302)
        self.assert_reached_check(out, err)
        line = self.line_with(out, err, SLUG)  # an unread PR has no number on its line
        self.assertIn("unknown", words(line), "want unknown on the row's line: " + line)
        self.assertNotIn("ok", words(line), "unknown must never read as ok: " + line)
        self.assertIsNone(NOT_CLEAR.search(line), "the row's line reads as clear: " + line)
        self.assert_merged(rc, out, err)

    def test_a_closed_unmerged_priority_pr_does_not_block(self):
        self.lower_goes_with(pr_fields(HEAD_3302, state="CLOSED"), [], "flag", "closed, not on main")

    def test_a_merged_priority_pr_does_not_block(self):
        self.lower_goes_with(pr_fields(HEAD_3302, state="MERGED"), [], "done", "merged")

    def test_an_open_row_based_on_another_branch_is_flagged_and_does_not_block_a_main_pr(self):
        self.lower_goes_with(pr_fields(HEAD_3302, base="feat-3337"), green(HEAD_3302), "flag", "feat-3337")

    def test_two_ok_rows_refuse_a_third_pr_and_name_both(self):
        self.host.prio[3302] = pr_fields(HEAD_3302)
        self.host.prio_runs[HEAD_3302] = green(HEAD_3302)
        self.host.prio[3303] = pr_fields(HEAD_3303, branch="feat-3303")
        self.host.prio_runs[HEAD_3303] = green(HEAD_3303)
        refs0, claims0 = self.refs(), self.claims()
        rc, out, err = self.confirm(LOWER, ROW_3302 + ROW_3303)
        self.assert_reached_check(out, err)
        self.refusal_names(out, err, SLUG, "#3302")
        self.refusal_names(out, err, OTHER_SLUG, "#3303")
        self.assert_refused_lands_nothing(rc, refs0, claims0)

    def test_merging_row_pr_3302_passes_while_row_3303_is_ok(self):
        self.both_rows_ok_merge(3302)

    def test_rows_carry_no_rank_the_second_listed_row_passes_past_an_ok_row(self):
        """Rows carry no rank: a row's own pull request goes while another row reads ok, and no other row is read for it."""
        self.both_rows_ok_merge(3303)
        for n, reads in enumerate(self.run_reads, 1):
            for read in ("pr 3302", "runs " + HEAD_3302):
                self.assertNotIn(read, reads, "run %d read %r, but a row's own pull request reads no other row" % (n, read))

    def test_a_ready_priority_pr_costs_at_most_two_reads_per_run(self):
        self.host.prio[3302] = pr_fields(HEAD_3302)
        self.host.prio_runs[HEAD_3302] = green(HEAD_3302)
        rc, out, err = self.confirm(LOWER, ROW_3302)
        self.assert_reached_check(out, err)
        self.assertEqual(len(self.run_reads), 1, "a refused merge is one run")
        mine = [r for r in self.run_reads[0] if r in ("pr 3302", "runs " + HEAD_3302)]
        self.assertLessEqual(mine.count("pr 3302"), 1, "one read of the pull request: %s" % mine)
        self.assertLessEqual(mine.count("runs " + HEAD_3302), 1, "one read of the runs on its head: %s" % mine)
        self.assertLessEqual(len(mine), 2, "a ready priority pull request costs at most two reads: %s" % mine)

    def test_a_draft_priority_pr_is_judged_on_its_pr_read_alone(self):
        self.host.prio[3302] = pr_fields(HEAD_3302, draft=True)
        self.host.prio_runs[HEAD_3302] = green(HEAD_3302)
        rc, out, err = self.confirm(LOWER, ROW_3302)
        self.assert_reached_check(out, err)
        self.assert_merged(rc, out, err)
        for n, reads in enumerate(self.run_reads, 1):
            self.assertNotIn("runs " + HEAD_3302, reads, "run %d read the runs of a draft, whose verdict needs only its pull request" % n)

    # A draft's --confirm is the records step: the priority check never runs for it, so no row is read and nothing merges.

    def assert_draft_runs_no_check(self, rows_text, pulls):
        """A draft N, FILE holding `rows_text`, and each (number, head) of `pulls` ready and green. The draft's --confirm runs no priority
        check, reads no row, merges nothing, and marks N ready."""
        self.host.draft = True
        for n, head in pulls:
            self.host.prio[n] = pr_fields(head, branch="feat-%d" % n)
            self.host.prio_runs[head] = green(head)
        rc, out, err = self.confirm(LOWER, rows_text)
        self.assert_reached_check(out, err)
        self.assertEqual(self.priority_lines(out, err), [], "a draft's --confirm ran the priority check, and a draft reads no row: " + out + err)
        for n, reads in enumerate(self.run_reads, 1):
            for pr, head in pulls:
                for read in ("pr %d" % pr, "runs " + head):
                    self.assertNotIn(read, reads, "run %d read %r, and a draft reads no row" % (n, read))
        self.assertFalse(getattr(self.host, "merged", False), "a draft's --confirm merged: " + out + err)
        self.assertEqual(self.host.readies, [LOWER], "the draft's --confirm does not mark it ready: " + out + err)

    def test_a_draft_confirm_under_a_ready_row_runs_no_priority_check(self):
        self.assert_draft_runs_no_check(ROW_3302, [(3302, HEAD_3302)])

    def test_a_draft_confirm_under_full_rows_runs_no_priority_check(self):
        self.assert_draft_runs_no_check(ROW_3302 + ROW_3303, [(3302, HEAD_3302), (3303, HEAD_3303)])

    def test_a_draft_confirm_under_an_empty_rows_file_runs_no_priority_check(self):
        self.assert_draft_runs_no_check("", [(3302, HEAD_3302)])

    def test_an_empty_rows_file_says_it_is_not_clear(self):
        rc, out, err = self.confirm(LOWER, "")
        self.assert_reached_check(out, err)
        self.assert_not_clear_line(out, err)

    def test_a_missing_rows_file_says_it_is_not_clear(self):
        missing = pathlib.Path(self.t) / "missing.txt"
        rc, out, err = self.run_args(str(LOWER), "--confirm", "--priority-rows", str(missing))
        self.assert_reached_check(out, err)
        self.assert_not_clear_line(out, err)

    def test_a_mixed_rows_file_gives_each_row_its_line_and_refuses_on_the_ready_one(self):
        self.host.prio[3302] = pr_fields(HEAD_3302)
        self.host.prio_runs[HEAD_3302] = green(HEAD_3302)
        self.host.prio[3280] = pr_fields("e" * 40, branch="feat-3280", state="MERGED")
        self.host.prio[3290] = pr_fields("f" * 40, branch="feat-3290", draft=True)
        rows = ("# this wake's priorities\n\n" + ROW_3302 +
                "priority: step-done | pr: %s#3280\n" % REPO +
                "priority: step-draft | pr: %s#3290\n" % REPO)
        refs0, claims0 = self.refs(), self.claims()
        rc, out, err = self.confirm(LOWER, rows)
        self.assert_reached_check(out, err)
        self.assertIn("done", words(self.line_with(out, err, "step-done")), "a merged row reads done")
        self.assertIn("flag", words(self.line_with(out, err, "step-draft")), "a draft row reads flag")
        self.refusal_names(out, err, SLUG, "#3302")
        self.assert_refused_lands_nothing(rc, refs0, claims0)

    # A row the reader cannot parse refuses the merge: the check cannot tell which row is ready, so it says so and merges nothing.

    def test_a_malformed_row_refuses_the_merge_and_says_it_cannot_be_read(self):
        refs0, claims0 = self.refs(), self.claims()
        rc, out, err = self.confirm(LOWER, MALFORMED_ROW)
        self.assert_reached_check(out, err)
        self.assertNotEqual(rc, 0, "a row the reader cannot parse must refuse the merge: " + out + err)
        self.assert_refused_lands_nothing(rc, refs0, claims0)
        self.refusal_names(out, err, MALFORMED_SLUG, "#3302")
        self.assert_cannot_be_read(out, err)

    def test_a_rows_file_with_no_priority_row_refuses_as_not_clear(self):
        refs0, claims0 = self.refs(), self.claims()
        rc, out, err = self.confirm(LOWER, "notes for the wake, with no row in them\n")
        self.assert_reached_check(out, err)
        self.assertNotEqual(rc, 0, "a rows file with no priority row must refuse the merge: " + out + err)
        self.assert_refused_lands_nothing(rc, refs0, claims0)
        self.assert_not_clear_line(out, err)

    def test_a_mixed_rows_file_with_a_malformed_row_refuses_though_no_row_is_ready(self):
        self.host.prio[3280] = pr_fields("e" * 40, branch="feat-3280", state="MERGED")  # step-done reads done, not ok
        refs0, claims0 = self.refs(), self.claims()
        rc, out, err = self.confirm(LOWER, "priority: step-done | pr: %s#3280\n" % REPO + MALFORMED_ROW)
        self.assert_reached_check(out, err)
        self.assertNotEqual(rc, 0, "a malformed row must refuse the merge even with no ready row: " + out + err)
        self.assert_refused_lands_nothing(rc, refs0, claims0)
        self.refusal_names(out, err, MALFORMED_SLUG, "#3302")
        self.assert_cannot_be_read(out, err)

    def test_a_malformed_pr_row_refusal_starts_its_sentence_with_the_row(self):
        rc, out, err = self.confirm(LOWER, MALFORMED_ROW)
        self.assert_reached_check(out, err)
        self.assertIn("the priority row %s cannot be read: pr #3302 is not owner/repo#N." % MALFORMED_SLUG, out + err,
                      "the refusal must start its sentence with the row, then say it cannot be read: " + out + err)
        self.assert_cannot_be_read(out, err)

    # Controls: these pass on the old code too, and show that the fixture means what each case says.

    def test_control_the_standing_reader_reads_the_3302_row_ok(self):
        self.host.prio[3302] = pr_fields(HEAD_3302)
        self.host.prio_runs[HEAD_3302] = green(HEAD_3302)
        self.rows.write_text(ROW_3302, encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = merge.priority_rows(str(self.rows), self.co, self.host)
        self.assertEqual(rc, 0, out.getvalue())
        self.assertIn("ok " + SLUG + " #3302", out.getvalue())

    def test_control_a_plain_confirm_of_a_ready_pr_merges(self):
        rc, out, err = self.run_args(str(LOWER), "--confirm", host=self.host)
        self.assert_merged(rc, out, err)

    def test_control_a_network_error_on_a_priority_pr_read_is_unknown_and_the_lower_pr_goes(self):
        """Any error from the read is caught, not only a Stop: the row reads unknown, says why, and does not block the merge."""
        self.host.prio_error[3302] = ConnectionError("network unreachable")
        rc, out, err = self.confirm(LOWER, ROW_3302)
        self.assert_reached_check(out, err)
        line = self.line_with(out, err, SLUG)  # an unread PR has no number on its line
        self.assertIn("unknown", words(line), "want unknown on the row's line: " + line)
        self.assertIn("network unreachable", line, "the line says why the read failed: " + line)
        self.assertNotIn("ok", words(line), "unknown must never read as ok: " + line)
        self.assertIsNone(NOT_CLEAR.search(line), "the row's line reads as clear: " + line)
        self.assert_merged(rc, out, err)

    def test_control_an_open_row_based_on_main_still_refuses_a_lower_pr(self):
        """Green on the old code too: an open row whose base is main reads ok and refuses a lower pull request."""
        self.host.prio[3302] = pr_fields(HEAD_3302, base="main")
        self.host.prio_runs[HEAD_3302] = green(HEAD_3302)
        refs0, claims0 = self.refs(), self.claims()
        rc, out, err = self.confirm(LOWER, ROW_3302)
        self.assert_reached_check(out, err)
        self.assertIn("ok", words(self.line_with(out, err, SLUG, "#3302")), "want ok on the row's line: " + out + err)
        self.refusal_names(out, err, SLUG, "#3302")
        self.assert_refused_lands_nothing(rc, refs0, claims0)

    def script_ready_branch_row(self):
        """Branch feat-3302 is one open pull request, #3302, ready and green: the branch row names it."""
        info = pr_fields(HEAD_3302, branch="feat-3302")
        self.host.prio[3302] = info
        self.host.prio_open = [(3302, info)]
        self.host.prio_runs[HEAD_3302] = green(HEAD_3302)

    def test_control_a_ready_branch_row_refuses_a_lower_pr_and_names_the_row(self):
        self.script_ready_branch_row()
        refs0, claims0 = self.refs(), self.claims()
        rc, out, err = self.confirm(LOWER, BRANCH_ROW)
        self.assert_reached_check(out, err)
        self.refusal_names(out, err, SLUG, "#3302")
        self.assert_refused_lands_nothing(rc, refs0, claims0)

    def test_control_the_stdin_form_refuses_a_lower_pr_for_a_ready_branch_row(self):
        """One run only: a stdin that is read to the end cannot serve the second step of a passing confirm."""
        self.script_ready_branch_row()
        refs0, claims0 = self.refs(), self.claims()
        with mock.patch.object(sys, "stdin", io.StringIO(BRANCH_ROW)):
            rc, out, err = self.run_args(str(LOWER), "--confirm", "--priority-rows", "-")
        self.assert_reached_check(out, err)
        self.refusal_names(out, err, SLUG, "#3302")
        self.assert_refused_lands_nothing(rc, refs0, claims0)


if __name__ == "__main__":
    unittest.main()
