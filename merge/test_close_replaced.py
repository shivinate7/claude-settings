#!/usr/bin/env python3
"""Cases for the close lines and the reopen line of `merge --reviewed --root DIR`, and for the batch line that drops a PR they close.

Run: python3 merge/test_close_replaced.py
The lines, per root, after the batch line:
  close as replaced: OWNER/NAME #N by #R    an open PR R whose body holds `Replaces #N`, N another open PR
  close as carried: OWNER/NAME #A by #B     an open draft PR A with a done record whose head open PR B holds
  close as carried unknown (REASON)         the compare, or the frozen block of an open batch head, that decides a carried close failed; exit 1
  reopen: OWNER/NAME #N (replacer #R dropped)                 a closed N whose replacer R is closed, unmerged
  reopen: OWNER/NAME #N (replacer #R no longer names it)      a closed N whose replacer R is open and no longer names N
Every fixture is test_merge.py's, the one home of the fake host and the record helpers. The one piece this file adds is ClosedHost,
which answers `pulls/<n>` for a closed pull request; test_merge.py's PullsHost answers open ones only. ReviewedRoots is used unbound,
so its own cases run in merge/test_merge.py and not again here.
"""
import collections, json, re, unittest

import test_merge as tm  # the one home of the fixtures (merge/test_merge.py)
from test_merge import PullsHost, batch_pull, batch_lines_of, green, running, record_of, review_comment, freeze_body, freeze_inner, lint_of, BATCH_BEGIN

REPLACED, CARRIED, REOPENED = "close as replaced: ", "close as carried: ", "reopen: "
CARRIED_UNKNOWN = "close as carried unknown "
BATCH_HEAD = "batch-nightly"  # the head ref of an open batch: only a head `batch-*` holds a frozen block that counts (frozen_lanes)
BATCH_LINE_KINDS = ("open batch now: ", "build next batch on the running head: ", "batch line unknown ")  # the three starts of the batch line


def head_of(n):
    """A full 40-hex head for pull request n, distinct per n up to 15."""
    return format(n, "x") * 40


def named_pull(number, sha, body="", draft=False, base="main", head_ref=None):
    """An open pull request row with its body, as the open list gives it. head_ref names its head branch (default feat<number>)."""
    return {**batch_pull(number, sha, base=base, draft=draft, head_ref=head_ref), "body": body}


def closed_pull(number, sha, body="", merged=False, head_ref=None):
    """A pull request the open list does not hold: `pulls/<n>` answers it closed, and merged when `merged`."""
    return {**named_pull(number, sha, body, head_ref=head_ref), "state": "closed", "merged": merged}


class ClosedHost(PullsHost):
    """PullsHost that also answers `pulls/<n>` for each closed pull request in `closed`, and that holds `since` on the comment list as GitHub
    does: a comment whose updated_at is before `since` is not in the list (open-list runs only; count_gh runs take PullsHost's list). Every
    other number and every other read is PullsHost's."""

    def __init__(self, pulls, check_rows, closed=(), unreadable=(), **kw):
        super().__init__(pulls, check_rows, **kw)
        self.closed, self.unreadable = list(closed), set(unreadable)

    def pages(self, rel, key=None, fields=None):
        if rel == "issues/comments" and fields and "since" in fields and not self.count_gh:
            self.reads.append(rel)
            self.list_calls.append((rel, dict(fields)))
            return [c for c in self.comments if (c.get("updated_at") or c["created_at"]) >= fields["since"]]
        return super().pages(rel, key, fields)

    def pull_reply(self, n):
        if n in self.unreadable:
            return 1, "gh: HTTP 500 (test: the pull request cannot be read)"
        found = [d for d in self.closed if d["number"] == n]
        if not found:
            return super().pull_reply(n)
        return 0, json.dumps({**found[0], "mergeable": True, "mergeable_state": "clean", "changed_files": 0})

    def answer(self, rel, argv):
        """PullsHost has no compare route in count mode, so a compare read is answered here from the same `compares` table its gh() uses."""
        m = re.fullmatch(r"compare/([^/]+)\.\.\.([^/]+)", rel)
        if m:
            return json.dumps({"status": self.compares.get(m.groups(), "diverged")})
        return super().answer(rel, argv)


def closed_host(repo, pulls=(), comments=(), closed=(), check_rows=None, **kw):
    """The fake host of one --root repo: its open pulls, its comments, its check runs, and the closed pulls `pulls/<n>` answers.
    Each open pull also gets a lane-lint PASS at its head, since a done record counts only with one (lint_state)."""
    pulls = list(pulls)
    lints = [tm.lint_of(d["number"], d["head"]["sha"]) for d in pulls]
    return ClosedHost(pulls, check_rows or {}, closed=closed, comments=list(comments) + lints, repo=repo, **kw)


def block_of(test, out, name):
    """-> the lines under the `repo <name>:` header, up to the next header. A load_config notice is not one of them."""
    test.assertIn(f"repo {name}:", out.splitlines(), f"no block for {name}:\n" + out)
    lines, inside = [], False
    for line in out.splitlines():
        if re.fullmatch(r"repo \S+:", line):
            inside = line == f"repo {name}:"
        elif inside and "leaves out" not in line:
            lines.append(line)
    return lines


def kind_lines(block, kind):
    return [l for l in block if l.startswith(kind)]


class CloseEnv(tm.Env):
    """A checkout for `--root`, and a run of `merge --reviewed` over it with a ClosedHost. ReviewedRoots.checkout is called unbound."""

    def setUp(self):
        super().setUp()
        self.alpha = tm.ReviewedRoots.checkout(self, "alpha")

    def reviewed(self, host, want_rc=0):
        """-> the output of `merge --reviewed --root` over alpha, whose host is `host`. The exit code is checked first."""
        rc, out, err = self.run_args("--reviewed", "--root", self.alpha, hosts={self.alpha: host})
        self.assertEqual(rc, want_rc, out + err)
        return out

    def block_for_alpha(self, pulls=(), comments=(), closed=(), check_rows=None):
        return block_of(self, self.reviewed(closed_host("o/alpha", pulls, comments, closed, check_rows)), "o/alpha")


class CloseAsReplaced(CloseEnv):
    """`close as replaced: OWNER/NAME #N by #R`: one line per open N that an open R names, ascending, the lowest-numbered R per N."""

    def test_an_open_replacer_closes_the_pr_it_names(self):
        block = self.block_for_alpha(pulls=[named_pull(4, head_of(4)), named_pull(7, head_of(7), body="Replaces #4")])
        lines = kind_lines(block, REPLACED)
        self.assertRegex(lines[0] if lines else "", r"^close as replaced: o/alpha #\d+ by #\d+$", "the line has no OWNER/NAME before its number:\n" + "\n".join(block))
        self.assertEqual(lines, ["close as replaced: o/alpha #4 by #7"], "\n".join(block))

    def test_each_replaced_pr_is_one_line_in_ascending_order(self):
        pulls = [named_pull(3, head_of(3)), named_pull(4, head_of(4)), named_pull(7, head_of(7), body="Replaces #4"),
                 named_pull(9, head_of(9), body="Replaces #3")]
        block = self.block_for_alpha(pulls=pulls)
        self.assertEqual(kind_lines(block, REPLACED), ["close as replaced: o/alpha #3 by #9", "close as replaced: o/alpha #4 by #7"],
                         "\n".join(block))

    def test_two_replacers_of_one_pr_name_the_lowest_numbered(self):
        pulls = [named_pull(4, head_of(4)), named_pull(9, head_of(9), body="Replaces #4"), named_pull(7, head_of(7), body="Replaces #4")]
        block = self.block_for_alpha(pulls=pulls)
        self.assertEqual(kind_lines(block, REPLACED), ["close as replaced: o/alpha #4 by #7"], "\n".join(block))

    def test_a_pr_never_replaces_itself(self):
        # Anchor: #8 replaces #6 and must print. #4 names itself and must not.
        pulls = [named_pull(4, head_of(4), body="Replaces #4"), named_pull(6, head_of(6)), named_pull(8, head_of(8), body="Replaces #6")]
        lines = kind_lines(self.block_for_alpha(pulls=pulls), REPLACED)
        self.assertIn("close as replaced: o/alpha #6 by #8", lines, "control: #8 replaces open #6 and prints no line:\n" + "\n".join(lines))
        self.assertNotIn("close as replaced: o/alpha #4 by #4", lines, "a PR replaced itself")

    def test_a_replacement_of_a_closed_or_unknown_pr_makes_no_line(self):
        # Anchor: #8 replaces open #6. #9 names #2, which is closed, and #10 names #99, which is unknown. Neither prints.
        pulls = [named_pull(6, head_of(6)), named_pull(8, head_of(8), body="Replaces #6"), named_pull(9, head_of(9), body="Replaces #2"),
                 named_pull(10, head_of(10), body="Replaces #99")]
        lines = kind_lines(self.block_for_alpha(pulls=pulls, closed=[closed_pull(2, head_of(2))]), REPLACED)
        self.assertIn("close as replaced: o/alpha #6 by #8", lines, "control: #8 replaces open #6 and prints no line:\n" + "\n".join(lines))
        self.assertEqual(lines, ["close as replaced: o/alpha #6 by #8"], "a replacement of a closed or unknown PR printed a line")

    def test_closing_keywords_and_unreplaces_are_not_replaces(self):
        # Anchor: #8 replaces #6. #9 says Closes #4, #10 says Fixes #4, #11 says Unreplaces #4: none of them replaces #4.
        pulls = [named_pull(4, head_of(4)), named_pull(6, head_of(6)), named_pull(8, head_of(8), body="Replaces #6"),
                 named_pull(9, head_of(9), body="Closes #4"), named_pull(10, head_of(10), body="Fixes #4"),
                 named_pull(11, head_of(11), body="Unreplaces #4")]
        lines = kind_lines(self.block_for_alpha(pulls=pulls), REPLACED)
        self.assertIn("close as replaced: o/alpha #6 by #8", lines, "control: #8 replaces open #6 and prints no line:\n" + "\n".join(lines))
        self.assertEqual(lines, ["close as replaced: o/alpha #6 by #8"], "a Closes, Fixes or Unreplaces body printed a replaced line for #4")

    def test_a_replaced_replacer_still_replaces_its_target(self):
        # Pin: a replaced PR that is itself replaced still replaces its target. #7 replaces #4 and is itself replaced by #9: both lines print.
        # Only the carried check drops replaced PRs.
        pulls = [named_pull(4, head_of(4)), named_pull(7, head_of(7), body="Replaces #4"), named_pull(9, head_of(9), body="Replaces #7")]
        block = self.block_for_alpha(pulls=pulls)
        self.assertEqual(kind_lines(block, REPLACED), ["close as replaced: o/alpha #4 by #7", "close as replaced: o/alpha #7 by #9"], "\n".join(block))

    def test_a_full_repo_of_twelve_chained_prs_closes_eleven(self):
        # Pin: a chain of replacers prints one line per replaced PR, all in one pass, so twelve PRs
        # give eleven lines.
        pulls = [named_pull(n, head_of(n), body=f"Replaces #{n - 1}" if n > 1 else "") for n in range(1, 13)]
        block = self.block_for_alpha(pulls=pulls)
        self.assertEqual(kind_lines(block, REPLACED), [f"close as replaced: o/alpha #{n} by #{n + 1}" for n in range(1, 12)], "\n".join(block))

    def test_a_mutual_replaces_closes_neither(self):
        # A mutual pair closes neither: #1 says Replaces #2 and #2 says Replaces #1. Control: #8 replaces open #6 and prints.
        pulls = [named_pull(1, head_of(1), body="Replaces #2"), named_pull(2, head_of(2), body="Replaces #1"),
                 named_pull(6, head_of(6)), named_pull(8, head_of(8), body="Replaces #6")]
        lines = kind_lines(self.block_for_alpha(pulls=pulls), REPLACED)
        self.assertIn("close as replaced: o/alpha #6 by #8", lines, "control: #8 replaces open #6 and prints no line:\n" + "\n".join(lines))
        self.assertEqual(lines, ["close as replaced: o/alpha #6 by #8"], "a mutual Replaces closed one of its pair")

    def test_a_replacer_on_another_base_closes_nothing(self):
        # A replacer on another base closes nothing: #7 is on base release and names `Replaces #4`; #4 is on main, so no line. Control: #8 on main replaces #6.
        pulls = [named_pull(4, head_of(4)), named_pull(6, head_of(6)), named_pull(7, head_of(7), body="Replaces #4", base="release"),
                 named_pull(8, head_of(8), body="Replaces #6")]
        lines = kind_lines(self.block_for_alpha(pulls=pulls), REPLACED)
        self.assertIn("close as replaced: o/alpha #6 by #8", lines, "control: #8 replaces open #6 and prints no line:\n" + "\n".join(lines))
        self.assertEqual(lines, ["close as replaced: o/alpha #6 by #8"], "a PR on base release closed #4 on base main")

    def test_a_quoted_replaces_closes_nothing(self):
        # Replaces counts only at a line start, after optional whitespace, and not in a `>` quote. Control: #8's
        # body is indented, and that is allowed.
        pulls = [named_pull(4, head_of(4)), named_pull(6, head_of(6)), named_pull(7, head_of(7), body="> Replaces #4"),
                 named_pull(8, head_of(8), body="  Replaces #6")]
        lines = kind_lines(self.block_for_alpha(pulls=pulls), REPLACED)
        self.assertIn("close as replaced: o/alpha #6 by #8", lines, "control: an indented Replaces prints no line:\n" + "\n".join(lines))
        self.assertEqual(lines, ["close as replaced: o/alpha #6 by #8"], "a quoted Replaces closed #4")

    def test_a_fenced_replaces_closes_nothing(self):
        # A Replaces line inside a fenced code block names nothing. Control: #8 replaces open #6.
        pulls = [named_pull(4, head_of(4)), named_pull(6, head_of(6)), named_pull(7, head_of(7), body="```\nReplaces #4\n```"),
                 named_pull(8, head_of(8), body="Replaces #6")]
        lines = kind_lines(self.block_for_alpha(pulls=pulls), REPLACED)
        self.assertIn("close as replaced: o/alpha #6 by #8", lines, "control: #8 replaces open #6 and prints no line:\n" + "\n".join(lines))
        self.assertEqual(lines, ["close as replaced: o/alpha #6 by #8"], "a Replaces in a fenced block closed #4")

    def test_a_replaces_inside_a_sentence_closes_nothing(self):
        # Replaces must start its line. Control: #8 replaces open #6.
        pulls = [named_pull(4, head_of(4)), named_pull(6, head_of(6)), named_pull(7, head_of(7), body="This lane Replaces #4 later."),
                 named_pull(8, head_of(8), body="Replaces #6")]
        lines = kind_lines(self.block_for_alpha(pulls=pulls), REPLACED)
        self.assertIn("close as replaced: o/alpha #6 by #8", lines, "control: #8 replaces open #6 and prints no line:\n" + "\n".join(lines))
        self.assertEqual(lines, ["close as replaced: o/alpha #6 by #8"], "a Replaces in the middle of a sentence closed #4")

    def test_close_lines_print_after_the_batch_line(self):
        pulls = [named_pull(4, head_of(4)), named_pull(5, head_of(5)), named_pull(7, head_of(7), body="Replaces #4")]
        block = self.block_for_alpha(pulls=pulls, comments=[record_of(5, head_of(5))], check_rows={head_of(5): green()})
        self.assertEqual(batch_lines_of(block), ["open batch now: o/alpha #5"], "\n".join(block))
        replaced = kind_lines(block, REPLACED)
        self.assertEqual(replaced, ["close as replaced: o/alpha #4 by #7"], "\n".join(block))
        self.assertLess(block.index(batch_lines_of(block)[0]), block.index(replaced[0]), "the close line prints before the batch line:\n" + "\n".join(block))

    def test_each_root_closes_only_its_own_pull_requests(self):
        # alpha's #4 is replaced by alpha's #7. bravo has its own #4 and no replacer: bravo's block names no close line.
        self.bravo = tm.ReviewedRoots.checkout(self, "bravo")
        hosts = {self.alpha: closed_host("o/alpha", pulls=[named_pull(4, head_of(4)), named_pull(7, head_of(7), body="Replaces #4")]),
                 self.bravo: closed_host("o/bravo", pulls=[named_pull(4, head_of(4))])}
        rc, out, err = self.run_args("--reviewed", "--root", self.alpha, "--root", self.bravo, hosts=hosts)
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(kind_lines(block_of(self, out, "o/alpha"), REPLACED), ["close as replaced: o/alpha #4 by #7"], out)
        self.assertEqual(kind_lines(block_of(self, out, "o/bravo"), REPLACED), [], "bravo's #4 was closed by alpha's replacer:\n" + out)

    def test_a_root_with_no_open_pulls_prints_no_close_line_beside_a_root_that_closes(self):
        # The empty state: bravo has no open pull request, so its block is its empty line and the line saying the reopen is not checked.
        # alpha's replaced #4 is the control.
        self.bravo = tm.ReviewedRoots.checkout(self, "bravo")
        hosts = {self.alpha: closed_host("o/alpha", pulls=[named_pull(4, head_of(4)), named_pull(7, head_of(7), body="Replaces #4")]),
                 self.bravo: closed_host("o/bravo")}
        rc, out, err = self.run_args("--reviewed", "--root", self.alpha, "--root", self.bravo, hosts=hosts)
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(kind_lines(block_of(self, out, "o/alpha"), REPLACED), ["close as replaced: o/alpha #4 by #7"], out)
        self.assertEqual(block_of(self, out, "o/bravo"), ["no open pull requests.", "reopen not checked (no open pull request)"],
                         "an empty repo printed other than its empty line and the reopen-not-checked line:\n" + out)


class CloseAsCarried(CloseEnv):
    """`close as carried: OWNER/NAME #A by #B`: a done draft A whose head an open B on the base holds. Draft or ready B both count; a ready A never does."""

    def test_a_done_lane_under_a_ready_carrier_closes(self):
        # #9 is the ready carrier and holds #5. #6 is done and held by nothing, so it does not close.
        host = tm.ReviewedRoots.held_hosts(self, {(head_of(5), head_of(9)): "ahead"}, draft9=False)[self.alpha]
        block = block_of(self, self.reviewed(host), "o/alpha")
        self.assertEqual(kind_lines(block, CARRIED), ["close as carried: o/alpha #5 by #9"], "\n".join(block))

    def test_a_done_lane_under_a_draft_integration_carrier_closes(self):
        host = tm.ReviewedRoots.held_hosts(self, {(head_of(5), head_of(9)): "ahead"}, draft9=True)[self.alpha]
        block = block_of(self, self.reviewed(host), "o/alpha")
        self.assertEqual(kind_lines(block, CARRIED), ["close as carried: o/alpha #5 by #9"], "\n".join(block))

    def test_a_replaced_pr_holds_no_carry(self):
        # A replaced PR carries nothing. #4's head holds #3, and #5 names #4 as replaced without holding #3, so #3 must not be carried by #4:
        # #3 gets no carried line, and the replaced line for #4 prints.
        pulls = [named_pull(3, head_of(3)), named_pull(4, head_of(4)), named_pull(5, head_of(5), body="Replaces #4")]
        host = closed_host("o/alpha", pulls=pulls, comments=[record_of(3, head_of(3))], check_rows={head_of(3): green()},
                           compares={(head_of(3), head_of(4)): "ahead"})
        block = block_of(self, self.reviewed(host), "o/alpha")
        self.assertEqual(kind_lines(block, REPLACED), ["close as replaced: o/alpha #4 by #5"], "\n".join(block))
        self.assertEqual(kind_lines(block, CARRIED), [], "#3 is carried by #4, which is named replaced:\n" + "\n".join(block))

    def test_a_done_pr_held_only_by_a_replaced_pr_stays_on_the_batch_line(self):
        # Pin: #4 is the only PR whose head holds #3, and #5 names #4 as replaced. #4 carries
        # nothing for the carried check, so #3 gets no carried line and stays on the batch line.
        pulls = [named_pull(3, head_of(3)), named_pull(4, head_of(4)), named_pull(5, head_of(5), body="Replaces #4")]
        host = closed_host("o/alpha", pulls=pulls, comments=[record_of(3, head_of(3))], check_rows={head_of(3): green()},
                           compares={(head_of(3), head_of(4)): "ahead"})
        block = block_of(self, self.reviewed(host), "o/alpha")
        self.assertEqual(kind_lines(block, CARRIED), [], "#3 is carried by #4, which is named replaced:\n" + "\n".join(block))
        self.assertEqual(batch_lines_of(block), ["open batch now: o/alpha #3"], "#3 left the batch line although only a replaced PR holds it:\n" + "\n".join(block))

    def test_an_identical_head_under_a_replaced_lower_is_not_carried(self):
        # #10 is named replaced by #12, so #10 carries nothing. #11 has #10's head, and would be carried by #10 if #10 counted.
        same = head_of(10)
        pulls = [named_pull(10, same), named_pull(11, same), named_pull(12, head_of(12), body="Replaces #10")]
        host = closed_host("o/alpha", pulls=pulls, comments=[record_of(11, same)], check_rows={same: green()})
        block = block_of(self, self.reviewed(host), "o/alpha")
        self.assertEqual(kind_lines(block, REPLACED), ["close as replaced: o/alpha #10 by #12"], "\n".join(block))
        self.assertEqual(kind_lines(block, CARRIED), [], "#11 is carried by #10, which is named replaced:\n" + "\n".join(block))

    def test_identical_heads_close_only_the_higher_numbered_pr(self):
        # #4 and #6 have one head, and each holds the other. Only #6 closes, by #4. #4 stays open. Both are drafts: only a draft is carried.
        same = head_of(4)
        block = self.block_for_alpha(pulls=[named_pull(4, same, draft=True), named_pull(6, same, draft=True)],
                                     comments=[record_of(4, same), record_of(6, same)],
                                     check_rows={same: green()})
        self.assertEqual(kind_lines(block, CARRIED), ["close as carried: o/alpha #6 by #4"], "\n".join(block))

    def test_identical_heads_batch_the_lower_and_keep_the_higher_off_the_batch(self):
        # Pin of the batch half, on the direction of test_identical_heads_close_only_the_higher_numbered_pr: #4 holds, so it is batched, and
        # #6 closes by #4, so it is not. Both are drafts: only a draft is carried. The coordinator ruled the direction at 08:02 CST: the lower
        # batches, the higher closes. If that changes, this case and that one change together.
        same = head_of(4)
        block = self.block_for_alpha(pulls=[named_pull(4, same, draft=True), named_pull(6, same, draft=True)],
                                     comments=[record_of(4, same), record_of(6, same)],
                                     check_rows={same: green()})
        self.assertEqual(batch_lines_of(block), ["open batch now: o/alpha #4"], "the batch line does not hold the lower of two identical heads:\n" + "\n".join(block))
        self.assertNotIn("#6", "\n".join(batch_lines_of(block)), "the higher of two identical heads is on the batch line, though its close line names it")

    def test_a_chain_closes_each_lane_under_the_holder_outside_it(self):
        # #3 is inside #5, and #5 is inside #4. #3's lowest-numbered holder is #4, and #5's holder is #4. #4 closes nothing.
        heads = {3: head_of(3), 4: head_of(4), 5: head_of(5)}
        pulls = [named_pull(n, heads[n], draft=n != 4) for n in (3, 4, 5)]  # #3 and #5 are drafts: only a draft is carried
        comments = [record_of(n, heads[n]) for n in (3, 4, 5)]
        compares = {(heads[3], heads[5]): "ahead", (heads[3], heads[4]): "ahead", (heads[5], heads[4]): "ahead"}
        host = closed_host("o/alpha", pulls=pulls, comments=comments, check_rows={h: green() for h in heads.values()}, compares=compares)
        block = block_of(self, self.reviewed(host), "o/alpha")
        self.assertEqual(kind_lines(block, CARRIED), ["close as carried: o/alpha #3 by #4", "close as carried: o/alpha #5 by #4"], "\n".join(block))

    def test_an_undone_lane_under_a_carrier_stays_open(self):
        # Anchor: #5 is done and held by #9, and closes. #6 is held by #9 too, but it has no record, so it stays open.
        pulls = [named_pull(5, head_of(5), draft=True), named_pull(6, head_of(6), draft=True), named_pull(9, head_of(9))]
        compares = {(head_of(5), head_of(9)): "ahead", (head_of(6), head_of(9)): "ahead"}
        host = closed_host("o/alpha", pulls=pulls, comments=[record_of(5, head_of(5))], check_rows={head_of(5): green()}, compares=compares)
        lines = kind_lines(block_of(self, self.reviewed(host), "o/alpha"), CARRIED)
        self.assertIn("close as carried: o/alpha #5 by #9", lines, "control: the done #5 under #9 prints no line:\n" + "\n".join(lines))
        self.assertNotIn("close as carried: o/alpha #6 by #9", lines, "an undone lane under a carrier was closed")

    def test_a_done_pr_whose_head_main_holds_is_not_carried_by_another_open_pr(self):
        # Probe: #5's head a is on main (compare a...main reads ahead), and open #9 holds a too. #5 is done, so only the carried check could
        # close it. Control: #6 is done on a head only #9 holds, and closes by #9.
        a, c, b9 = head_of(5), head_of(6), head_of(9)
        pulls = [named_pull(5, a, draft=True), named_pull(6, c, draft=True), named_pull(9, b9)]  # both done PRs are drafts: only a draft is carried
        comments = [record_of(5, a), record_of(6, c)]
        compares = {(a, b9): "ahead", (a, "main"): "ahead", (c, b9): "ahead"}
        host = closed_host("o/alpha", pulls, comments, check_rows={a: green(), c: green()}, compares=compares)
        lines = kind_lines(block_of(self, self.reviewed(host), "o/alpha"), CARRIED)
        self.assertIn("close as carried: o/alpha #6 by #9", lines, "control: the done #6 under #9 prints no close line:\n" + "\n".join(lines))
        self.assertNotIn("close as carried: o/alpha #5 by #9", lines, "#5's head is on main already, yet #5 closes as carried by #9:\n" + "\n".join(lines))

    def test_an_unknown_compare_prints_unknown_and_exits_one(self):
        # The compare of #5 with #9 fails. The line says unknown, with a reason, in place of a close line. A close line is never printed.
        host = closed_host("o/alpha", pulls=[named_pull(5, head_of(5), draft=True), named_pull(9, head_of(9))], comments=[record_of(5, head_of(5))],
                           check_rows={head_of(5): green()}, compares={(head_of(5), head_of(9)): "ahead"}, compare_error=(1, "gh: HTTP 502 (test)"))
        rc, out, err = self.run_args("--reviewed", "--root", self.alpha, hosts={self.alpha: host})
        lines = kind_lines(block_of(self, out, "o/alpha"), "close as carried")
        unknown = [l for l in lines if l.startswith("close as carried unknown (")]
        self.assertTrue(unknown, "no `close as carried unknown (...)` line for the failed compare:\n" + out + err)
        self.assertRegex(unknown[0], r"^close as carried unknown \(.+\)$", "the unknown line gives no reason:\n" + unknown[0])
        self.assertEqual(rc, 1, "a carried close with an unknown compare exits 0:\n" + out + err)
        self.assertEqual([l for l in lines if l.startswith(CARRIED)], [], "a close line printed although its compare is unknown:\n" + out)


class CarryOnlyDrafts(CloseEnv):
    """Only a draft done PR is carried. A ready one that an open PR holds closes nothing, and stays off the batch line as on main: the hold keeps
    it off, and no close line is printed for it."""

    def held_block(self, a_draft, checks, b=9, b_draft=True):
        """-> the alpha block when done #5 (a draft when `a_draft`, with `checks` on its head) is held by open #b (a draft when `b_draft`, no record)."""
        pulls = [named_pull(5, head_of(5), draft=a_draft), named_pull(b, head_of(b), draft=b_draft)]
        host = closed_host("o/alpha", pulls=pulls, comments=[record_of(5, head_of(5))], check_rows={head_of(5): checks},
                           compares={(head_of(5), head_of(b)): "ahead"})
        return block_of(self, self.reviewed(host), "o/alpha")

    def test_a_ready_done_pr_under_a_draft_holder_closes_nothing_while_ci_runs(self):
        self.assertEqual(kind_lines(self.held_block(True, running()), CARRIED), ["close as carried: o/alpha #5 by #9"],
                         "control: the draft done #5 under draft #9 prints no close line")
        self.assertEqual(kind_lines(self.held_block(False, running()), CARRIED), [],
                         "a ready done #5 closed as carried by draft #9 while its CI runs")

    def test_a_ready_done_pr_under_a_draft_holder_closes_nothing_when_green(self):
        self.assertEqual(kind_lines(self.held_block(True, green()), CARRIED), ["close as carried: o/alpha #5 by #9"],
                         "control: the draft done #5 under draft #9 prints no close line")
        self.assertEqual(kind_lines(self.held_block(False, green()), CARRIED), [],
                         "a ready done #5 closed as carried by draft #9 once its CI is green")

    def test_a_ready_done_pr_held_by_a_draft_stays_off_the_batch_line(self):
        # Pin, as on main: main's batch line drops a done PR that another open PR on the base holds. The carry change must keep that.
        # Passes today.
        self.assertEqual(batch_lines_of(self.held_block(False, green())), [], "a ready done #5 that draft #9 holds is on the batch line")

    def test_a_ready_done_pr_with_an_identical_lower_head_closes_nothing(self):
        # Equal heads: #5 and #9 hold each other. Control: a draft #9 is carried by #5. A ready #9 is not.
        same = head_of(5)

        def closes(draft9):
            pulls = [named_pull(5, same), named_pull(9, same, draft=draft9)]
            host = closed_host("o/alpha", pulls=pulls, comments=[record_of(5, same), record_of(9, same)], check_rows={same: green()})
            return kind_lines(block_of(self, self.reviewed(host), "o/alpha"), CARRIED)

        self.assertEqual(closes(True), ["close as carried: o/alpha #9 by #5"], "control: the draft #9 with the head of #5 prints no close line")
        self.assertEqual(closes(False), [], "a ready #9 with the head of the lower #5 closed as carried")


class CarrySkipsFrozen(CloseEnv):
    """A done draft that an open batch's frozen block lists (`Lane: #N <head>`, as merge --batch-build writes it) is held by that batch, so it
    closes nothing, at the head the block lists. Only an open pull request whose head is a batch (`batch-*`) holds a block that counts: a body
    that quotes one, or a lone marker, on any other head is read as nothing. A done draft that no open batch lists still closes under its holder.
    Batch #9 is a draft on head BATCH_HEAD in every case here, unless a case says otherwise.
    A lane that open batches list at two heads is held at each of them, whatever the open list order. An unreadable block in an open batch
    makes only the carried line unknown: the batch line still prints."""

    def wake_run(self, pulls, done, compares, closed=()):
        """-> (rc, output, err) of a wake over `pulls`. The numbers in `done` are done drafts: a record and a lane lint at their head, CI green."""
        comments = [c for n in done for c in (record_of(n, head_of(n)), lint_of(n, head_of(n)))]
        checks = {head_of(n): green() for n in done}
        host = closed_host("o/alpha", pulls=pulls, comments=comments, closed=closed, check_rows=checks, compares=compares)
        return self.run_args("--reviewed", "--root", self.alpha, hosts={self.alpha: host})

    def wake(self, pulls, done, compares, closed=()):
        """-> the alpha block of a wake over `pulls`, which must exit 0."""
        rc, out, err = self.wake_run(pulls, done, compares, closed)
        self.assertEqual(rc, 0, out + err)
        return block_of(self, out, "o/alpha")

    def lane_held_by_ten(self):
        """Control: lane #5 at NEW is in no open batch, and open ready #10 holds NEW. -> the carried lines, which name #10 when it closes #5."""
        new = head_of(5)
        return kind_lines(self.wake([named_pull(5, new, draft=True), named_pull(10, head_of(10))], [5], {(new, head_of(10)): "ahead"}), CARRIED)

    def two_batch_lines(self, order, frozen=True):
        """-> the carried lines of a wake over lane #5 (a done draft at NEW) and two open batch drafts, listed in `order` (e.g. (9, 8)).
        Batch #9 (head BATCH_HEAD) freezes #5 at NEW, and #9 holds NEW. Batch #8 (head batch-older) freezes #5 at OLD, which is head_of(14).
        With `frozen` False both bodies are empty, so no batch freezes #5 and #9 holds it on its own."""
        new = head_of(5)
        body9 = freeze_body(freeze_inner("nightly", [(5, new)])) if frozen else ""
        body8 = freeze_body(freeze_inner("older", [(5, head_of(14))])) if frozen else ""
        rows = {9: named_pull(9, head_of(9), body=body9, draft=True, head_ref=BATCH_HEAD),
                8: named_pull(8, head_of(8), body=body8, draft=True, head_ref="batch-older")}
        pulls = [named_pull(5, new, draft=True), *(rows[n] for n in order)]
        return kind_lines(self.wake(pulls, [5], {(new, head_of(9)): "ahead"}), CARRIED)

    def test_a_done_draft_frozen_in_an_open_batch_closes_nothing(self):
        frozen = freeze_body(freeze_inner("nightly", [(5, head_of(5)), (6, head_of(6))]))
        drafts = [named_pull(5, head_of(5), draft=True), named_pull(6, head_of(6), draft=True)]
        compares = {(head_of(5), head_of(9)): "ahead", (head_of(6), head_of(9)): "ahead"}
        # Control: the same batch with no frozen block closes #5 and #6 under #9, so the empty result below comes from the freeze.
        control = kind_lines(self.wake([*drafts, named_pull(9, head_of(9), draft=True, head_ref=BATCH_HEAD)], [5, 6], compares), CARRIED)
        self.assertEqual(control, ["close as carried: o/alpha #5 by #9", "close as carried: o/alpha #6 by #9"], "control: no close line for #5 and #6 under #9:\n" + "\n".join(control))
        block = self.wake([*drafts, named_pull(9, head_of(9), body=frozen, draft=True, head_ref=BATCH_HEAD)], [5, 6], compares)
        self.assertEqual(kind_lines(block, CARRIED), [], "a lane that open batch #9 freezes closed as carried:\n" + "\n".join(block))

    def test_a_done_draft_no_open_batch_freezes_still_closes_under_its_holder(self):
        # Pin: #5 and #6 are frozen in #9 and close nothing. #7 is a done draft that no batch lists, and open ready #8 holds it: #7 still closes.
        frozen = freeze_body(freeze_inner("nightly", [(5, head_of(5)), (6, head_of(6))]))
        pulls = [named_pull(5, head_of(5), draft=True), named_pull(6, head_of(6), draft=True), named_pull(7, head_of(7), draft=True),
                 named_pull(8, head_of(8)), named_pull(9, head_of(9), body=frozen, draft=True, head_ref=BATCH_HEAD)]
        compares = {(head_of(5), head_of(9)): "ahead", (head_of(6), head_of(9)): "ahead", (head_of(7), head_of(8)): "ahead"}
        lines = kind_lines(self.wake(pulls, [5, 6, 7], compares), CARRIED)
        self.assertIn("close as carried: o/alpha #7 by #8", lines, "a done draft that no batch freezes does not close under its holder:\n" + "\n".join(lines))

    def test_once_the_batch_closes_unmerged_its_lanes_are_no_longer_skipped(self):
        # Pin: #9 is closed unmerged, so no open batch lists #5 or #6. Open ready #10 holds both, so each closes under #10.
        frozen = freeze_body(freeze_inner("nightly", [(5, head_of(5)), (6, head_of(6))]))
        pulls = [named_pull(5, head_of(5), draft=True), named_pull(6, head_of(6), draft=True), named_pull(10, head_of(10))]
        compares = {(head_of(5), head_of(10)): "ahead", (head_of(6), head_of(10)): "ahead"}
        lines = kind_lines(self.wake(pulls, [5, 6], compares, closed=[closed_pull(9, head_of(9), body=frozen, head_ref=BATCH_HEAD)]), CARRIED)
        self.assertEqual(lines, ["close as carried: o/alpha #5 by #10", "close as carried: o/alpha #6 by #10"],
                         "the lanes of a closed batch are still skipped, or the holder #10 does not carry them:\n" + "\n".join(lines))

    def test_once_the_batch_merges_its_lanes_close_nothing(self):
        # Pin: #9 merged, so main holds #5 and #6. Open ready #10 holds both heads too, so only the base check keeps them uncarried.
        # Control: where main holds neither head, the same #10 carries both, so the empty result comes from main's hold.
        frozen = freeze_body(freeze_inner("nightly", [(5, head_of(5)), (6, head_of(6))]))
        pulls = [named_pull(5, head_of(5), draft=True), named_pull(6, head_of(6), draft=True), named_pull(10, head_of(10))]
        holds = {(head_of(5), head_of(10)): "ahead", (head_of(6), head_of(10)): "ahead"}
        closed = [closed_pull(9, head_of(9), body=frozen, merged=True, head_ref=BATCH_HEAD)]
        control = kind_lines(self.wake(pulls, [5, 6], holds, closed=closed), CARRIED)
        self.assertEqual(control, ["close as carried: o/alpha #5 by #10", "close as carried: o/alpha #6 by #10"], "control: #10 does not carry #5 and #6:\n" + "\n".join(control))
        lines = kind_lines(self.wake(pulls, [5, 6], {**holds, (head_of(5), "main"): "ahead", (head_of(6), "main"): "ahead"}, closed=closed), CARRIED)
        self.assertEqual(lines, [], "a done draft that main holds closed as carried by open #10 after its batch merged:\n" + "\n".join(lines))

    def test_a_lone_marker_in_an_open_pull_request_that_is_not_a_batch_is_not_read(self):
        # Probe: open #7 (head feat7, not a batch) has one lone begin marker, which parse_freeze calls a Stop. Only a batch head holds a block that
        # counts, so #7 is read as nothing: no batch line or carried line goes unknown, and done draft #5 closes under ready #8.
        pulls = [named_pull(5, head_of(5), draft=True), named_pull(7, head_of(7), body=BATCH_BEGIN + "\n"), named_pull(8, head_of(8))]
        rc, out, err = self.wake_run(pulls, [5], {(head_of(5), head_of(8)): "ahead"})
        block = block_of(self, out, "o/alpha")
        unknown = [l for l in block if l.startswith(("batch line unknown ", CARRIED_UNKNOWN))]
        self.assertEqual(unknown, [], "a lone marker in open non-batch #7 made a line unknown:\n" + out + err)
        self.assertEqual(rc, 0, "a lone marker in open non-batch #7 exits 1:\n" + out + err)
        self.assertEqual(kind_lines(block, CARRIED), ["close as carried: o/alpha #5 by #8"],
                         "a lone marker in open non-batch #7 stops #5 closing under #8:\n" + "\n".join(block))

    def test_a_lane_frozen_at_an_older_head_closes_under_a_holder_of_its_current_head(self):
        # Probe: lane #5 is frozen in open batch #9 at OLD (head_of(14)), and has moved to NEW (head_of(5)), which open #10 holds. The block holds
        # the lane only at the head it lists, so #5 closes under #10. Control: the batch froze NEW, the lane's current head, so #5 closes nothing.
        new = head_of(5)

        def lines(frozen_head):
            frozen = freeze_body(freeze_inner("nightly", [(5, frozen_head)]))
            pulls = [named_pull(5, new, draft=True), named_pull(9, head_of(9), body=frozen, draft=True, head_ref=BATCH_HEAD), named_pull(10, head_of(10))]
            return kind_lines(self.wake(pulls, [5], {(new, head_of(10)): "ahead"}), CARRIED)

        self.assertEqual(lines(new), [], "control: a lane frozen at its current head closed as carried")
        self.assertEqual(lines(head_of(14)), ["close as carried: o/alpha #5 by #10"], "a lane frozen at an older head is still held by the batch")

    def test_a_lane_frozen_at_its_head_by_batch_nine_closes_nothing_with_open_list_nine_then_eight(self):
        # Probe: lane #5 at NEW is frozen at NEW in open batch #9, and an older open batch #8 froze #5 at an old head. The open list is [#9, #8].
        # frozen_lanes keeps one head per lane, so #8's head wins and #5 reads as moved: it closes under #9. The controls: a lane in no batch
        # closes under ready #10, and with both bodies empty #9 holds #5 and closes it, so the freeze is what holds #5.
        self.assertEqual(self.lane_held_by_ten(), ["close as carried: o/alpha #5 by #10"], "control: a lane in no open batch is not closed by ready #10")
        self.assertEqual(self.two_batch_lines((9, 8), frozen=False), ["close as carried: o/alpha #5 by #9"], "control: with no freeze, #9 does not hold lane #5")
        self.assertEqual(self.two_batch_lines((9, 8)), [],
                         "a lane that open batch #9 freezes at its head closed as carried, with the open list [#9, #8] and an older batch #8 that froze it at an old head")

    def test_a_lane_frozen_at_its_head_by_batch_nine_closes_nothing_with_open_list_eight_then_nine(self):
        # The reverse open-list order of the case above. A fix that keeps the first head of a lane passes that case and fails this one.
        self.assertEqual(self.lane_held_by_ten(), ["close as carried: o/alpha #5 by #10"], "control: a lane in no open batch is not closed by ready #10")
        self.assertEqual(self.two_batch_lines((8, 9), frozen=False), ["close as carried: o/alpha #5 by #9"], "control: with no freeze, #9 does not hold lane #5")
        self.assertEqual(self.two_batch_lines((8, 9)), [],
                         "a lane that open batch #9 freezes at its head closed as carried, with the open list [#8, #9] and an older batch #8 that froze it at an old head")

    def test_a_non_batch_pull_request_that_quotes_a_block_freezes_nothing(self):
        # Probe: open #7 on head feat7 (not a batch) quotes a whole block that lists lane #5 at its head. #5 closes under ready #8.
        # Control: the same body on a batch head holds #5, so it closes nothing.
        quote = freeze_body(freeze_inner("nightly", [(5, head_of(5))]))
        compares = {(head_of(5), head_of(8)): "ahead"}

        def lines(head_ref):
            pulls = [named_pull(5, head_of(5), draft=True), named_pull(7, head_of(7), body=quote, head_ref=head_ref), named_pull(8, head_of(8))]
            return kind_lines(self.wake(pulls, [5], compares), CARRIED)

        self.assertEqual(lines(BATCH_HEAD), [], "control: a batch head that lists lane #5 closed it as carried")
        self.assertEqual(lines(None), ["close as carried: o/alpha #5 by #8"], "a quoted block on a non-batch pull request holds lane #5")

    def test_a_malformed_block_in_an_open_batch_head_prints_carried_unknown_and_exits_one(self):
        # Pins the body source of `close as carried unknown`: a frozen block in an open batch head that this tool cannot read makes the carried
        # close unknown, with a reason that names the block, and the run exits 1. Control: the batch head with a readable block exits 0.
        # The batch line stays as the readable control's: the unreadable block does not make it unknown.
        others = [named_pull(5, head_of(5), draft=True), named_pull(8, head_of(8))]
        compares = {(head_of(5), head_of(8)): "ahead"}
        readable = freeze_body(freeze_inner("nightly", [(5, head_of(5))]))
        rc, out, err = self.wake_run([*others, named_pull(9, head_of(9), body=readable, draft=True, head_ref=BATCH_HEAD)], [5], compares)
        self.assertEqual(rc, 0, "control: a readable block in open batch #9 exits 1:\n" + out + err)
        control_batch = [l for l in block_of(self, out, "o/alpha") if l.startswith(BATCH_LINE_KINDS)]
        rc, out, err = self.wake_run([*others, named_pull(9, head_of(9), body=BATCH_BEGIN + "\n", draft=True, head_ref=BATCH_HEAD)], [5], compares)
        block = block_of(self, out, "o/alpha")
        unknown = kind_lines(block, CARRIED_UNKNOWN)
        self.assertEqual(len(unknown), 1, "no `close as carried unknown (...)` line for the malformed block in open batch #9:\n" + "\n".join(block))
        self.assertRegex(unknown[0], r"^close as carried unknown \(.*(marker|frozen block).*\)$", "the unknown line does not name the frozen block:\n" + unknown[0])
        batch = [l for l in block if l.startswith(BATCH_LINE_KINDS)]
        self.assertEqual(batch, control_batch, "a malformed block in open batch #9 changed the batch line from its readable control:\n" + "\n".join(block))
        self.assertEqual(rc, 1, "a malformed block in open batch #9 does not exit 1:\n" + out + err)
        self.assertEqual(kind_lines(block, CARRIED), [], "a close line printed while the block of open batch #9 is unknown:\n" + "\n".join(block))

    def test_a_malformed_block_in_an_open_batch_keeps_the_batch_line_for_a_lane_with_no_holder(self):
        # Cry-wolf cost: one unreadable block in an open batch must not make the whole batch line unknown. Done draft #5 has no holder, so the batch
        # line still names it. Only the carried line is unknown, and the run exits 1. Control: an empty body in open batch #9 prints the batch line, exit 0.

        def wake_with(body):
            pulls = [named_pull(5, head_of(5), draft=True), named_pull(9, head_of(9), body=body, draft=True, head_ref=BATCH_HEAD)]
            rc, out, err = self.wake_run(pulls, [5], {})
            return rc, block_of(self, out, "o/alpha"), out + err

        rc, block, text = wake_with("")
        self.assertEqual(rc, 0, "control: an empty body in open batch #9 exits 1:\n" + text)
        self.assertEqual(kind_lines(block, "open batch now: "), ["open batch now: o/alpha #5"], "control: the batch line does not name done draft #5:\n" + text)

        rc, block, text = wake_with(BATCH_BEGIN + "\n")
        unknown = kind_lines(block, CARRIED_UNKNOWN)
        self.assertEqual(len(unknown), 1, "no `close as carried unknown (...)` line for the malformed block in open batch #9:\n" + text)
        self.assertRegex(unknown[0], r"^close as carried unknown \(.*(marker|frozen block).*\)$", "the unknown line does not name the frozen block:\n" + unknown[0])
        self.assertEqual(kind_lines(block, "batch line unknown "), [], "a malformed block in open batch #9 made the whole batch line unknown:\n" + text)
        self.assertEqual(kind_lines(block, "open batch now: "), ["open batch now: o/alpha #5"], "a malformed block in open batch #9 changed the batch line for done draft #5:\n" + text)
        self.assertEqual(rc, 1, "a malformed block in open batch #9 does not exit 1:\n" + text)
        self.assertEqual(kind_lines(block, CARRIED), [], "a close line printed while the block of open batch #9 is unknown:\n" + text)


class CloseThenBuild(CloseEnv, tm.CloudSession):
    """The batch leg of the frozen-lane skip. A wake over alpha prints its close lines. The batch runner closes each pull request a line names,
    as the host would. Then `merge --batch-build nightly` runs on this case's own origin. The lanes, the batch and its frozen block come from
    test_merge.py's BatchFreeze helpers, called unbound (the one home of those fixtures), and the wake reads the same heads."""

    def setUp(self):
        super().setUp()
        self.heads = {}  # lane PR number -> its head on origin, as BatchFreeze.lane leaves it

    def build(self, numbers, blamed=()):
        """Lanes `numbers`, and their draft batch `nightly`. -> the batch pull request's number."""
        for n in numbers:
            tm.BatchFreeze.lane(self, n)
        return tm.BatchFreeze.frozen_batch(self, "nightly", list(numbers), draft=True, blamed=blamed)

    def wake_and_close(self, pr):
        """A wake over alpha reads the batch `pr` and its lanes. The batch runner closes each pull request a close line names. -> the close lines."""
        bh = self.head("batch-nightly")
        lanes = sorted(self.heads)
        pulls = [named_pull(n, self.heads[n], draft=True) for n in lanes]
        pulls.append({**batch_pull(pr, bh, draft=True, head_ref="batch-nightly"), "body": self.host.batch_pulls[pr]["body"]})
        compares = {(self.heads[n], bh): "ahead" for n in lanes}
        comments = [c for n in lanes for c in (record_of(n, self.heads[n]), lint_of(n, self.heads[n]))]
        checks = {self.heads[n]: green() for n in lanes}
        host = closed_host("o/alpha", pulls=pulls, comments=comments, check_rows=checks, compares=compares)
        lines = kind_lines(block_of(self, self.reviewed(host), "o/alpha"), CARRIED)
        for line in lines:
            self.host.batch_pulls[int(re.search(r"#(\d+) by", line).group(1))]["state"] = "CLOSED"
        return lines

    def ready(self):
        """-> (rc, output) of `merge --batch-build nightly --ready`, with the lint and the ready checks scripted to pass."""
        with tm.BatchFreeze.no_lint_or_ready_check(self, ready_state="pass"):
            return tm.BatchFreeze.run_batch(self, "--batch-build", "nightly", "--ready")

    def test_the_ready_build_after_a_wake_does_not_stop_on_a_closed_lane(self):
        pr = self.build([5, 6])
        self.wake_and_close(pr)
        rc, out = self.ready()
        self.assertNotIn("CLOSED, not open", out, "the ready build stopped on a lane that a wake closed:\n" + out)
        self.assertEqual(rc, 0, "the ready build after a wake exited %s:\n%s" % (rc, out))
        self.assertEqual(self.host.readies, [pr], "the ready build after a wake did not mark #%d ready:\n%s" % (pr, out))

    def test_the_ready_build_after_a_drop_does_not_stop_on_a_closed_lane(self):
        pr = self.build([5, 6], blamed=[6])  # #6 is blamed, so a drop may take it off
        self.wake_and_close(pr)
        with tm.BatchFreeze.no_lint_or_ready_check(self):
            rc, out = tm.BatchFreeze.run_batch(self, "--batch-drop", "nightly", "6")
        self.assertEqual(rc, 0, "control: the drop of #6 exited %s:\n%s" % (rc, out))
        self.assertIn("merge: #6 dropped from batch nightly.", out, "control: the drop of #6 did not run:\n" + out)
        rc, out = self.ready()
        self.assertNotIn("CLOSED, not open", out, "the ready build after a drop stopped on a lane that a wake closed:\n" + out)
        self.assertEqual(rc, 0, "the ready build after a drop exited %s:\n%s" % (rc, out))

    def test_the_same_set_again_after_a_wake_does_not_stop_on_a_closed_lane(self):
        pr = self.build([5, 6])
        self.wake_and_close(pr)
        with tm.BatchFreeze.no_lint_or_ready_check(self):
            rc, out = tm.BatchFreeze.run_batch(self, "--batch-build", "nightly", "6", "5")
        self.assertNotIn("CLOSED, not open", out, "the same set again stopped on a lane that a wake closed:\n" + out)
        self.assertEqual(rc, 0, "the same set again exited %s:\n%s" % (rc, out))
        rc, out = self.ready()
        self.assertNotIn("CLOSED, not open", out, "the ready build after the same set again stopped on a closed lane:\n" + out)
        self.assertEqual(rc, 0, "the ready build after the same set again exited %s:\n%s" % (rc, out))


class BatchSkipsClosed(CloseEnv):
    """A PR on a close line cannot join a batch: the batch line drops it."""

    def test_a_replaced_pr_is_dropped_from_the_batch_line(self):
        pulls = [named_pull(4, head_of(4)), named_pull(5, head_of(5)), named_pull(7, head_of(7), body="Replaces #4")]
        block = self.block_for_alpha(pulls=pulls, comments=[record_of(4, head_of(4)), record_of(5, head_of(5))],
                                     check_rows={head_of(4): green(), head_of(5): green()})
        self.assertEqual(batch_lines_of(block), ["open batch now: o/alpha #5"], "a PR named replaced is still on the batch line:\n" + "\n".join(block))


class ReopenClosed(CloseEnv):
    """`reopen: OWNER/NAME #N (...)`: a closed N whose comment names a replacer or carrier R. R closed and unmerged, or open and no longer naming N."""

    def reopened(self, closed, extra_pulls=(), extra_comments=()):
        """-> the reopen lines of alpha, with open #5 done and green beside the candidates."""
        pulls = [named_pull(5, head_of(5)), *extra_pulls]
        comments = [record_of(5, head_of(5)), *extra_comments]
        return kind_lines(self.block_for_alpha(pulls, comments, closed, {head_of(5): green()}), REOPENED)

    def test_a_closed_replaced_pr_reopens_when_its_replacer_is_closed_unmerged(self):
        lines = self.reopened(closed=[closed_pull(4, head_of(4)), closed_pull(7, head_of(7))],
                              extra_comments=[review_comment(90, 4, "Replaced by #7")])
        self.assertEqual(lines, ["reopen: o/alpha #4 (replacer #7 dropped)"], "\n".join(lines))

    def test_a_closed_carried_pr_reopens_when_its_carrier_is_closed_unmerged(self):
        lines = self.reopened(closed=[closed_pull(4, head_of(4)), closed_pull(9, head_of(9))],
                              extra_comments=[review_comment(90, 4, "Carried by #9")])
        self.assertEqual(lines, ["reopen: o/alpha #4 (replacer #9 dropped)"], "\n".join(lines))

    @unittest.expectedFailure  # Known gap, debt docs/debts/carrier-lost-head-stays-closed.md: reopen_lines reopens a carried PR only when its carrier
    # closes unmerged. Owner ruling 2026-11-09 21:29 CST says it "reopens if the carrier is dropped". This flips to passing when the code reopens it.
    def test_a_carried_link_whose_open_carrier_lost_its_head_reopens_the_pr(self):
        # #4 is closed with the note `Carried by #9`. Open #9 has moved off #4's head: its head is head_of(9), and its compare with #4's head is
        # diverged. The ruling says #4 reopens. The closed-carrier control is the one in test_a_closed_carried_pr_reopens_when_its_carrier_is_closed_unmerged.
        host = closed_host("o/alpha", pulls=[named_pull(5, head_of(5)), named_pull(9, head_of(9))],
                           comments=[record_of(5, head_of(5)), review_comment(90, 4, "Carried by #9")], closed=[closed_pull(4, head_of(4))],
                           check_rows={head_of(5): green()}, compares={(head_of(4), head_of(9)): "diverged"})
        rc, out, err = self.run_args("--reviewed", "--root", self.alpha, hosts={self.alpha: host})
        self.assertEqual(rc, 0, out + err)
        lines = kind_lines(block_of(self, out, "o/alpha"), REOPENED)
        self.assertTrue(any(l.startswith("reopen: o/alpha #4 ") for l in lines),
                        "#4 did not reopen while its open carrier #9 has moved off #4's head:\n" + "\n".join(lines))

    def test_a_replacer_that_no_longer_names_it_reopens(self):
        lines = self.reopened(closed=[closed_pull(4, head_of(4))], extra_pulls=[named_pull(7, head_of(7))],
                              extra_comments=[review_comment(90, 4, "Replaced by #7")])
        self.assertEqual(lines, ["reopen: o/alpha #4 (replacer #7 no longer names it)"], "\n".join(lines))

    def test_an_open_replacer_that_still_names_it_keeps_the_pr_closed(self):
        # Anchor: #6 is closed, replaced by open #8, which no longer names #6, so #6 reopens. #4 is replaced by open #7, which still names #4.
        lines = self.reopened(closed=[closed_pull(4, head_of(4)), closed_pull(6, head_of(6))],
                              extra_pulls=[named_pull(7, head_of(7), body="Replaces #4"), named_pull(8, head_of(8))],
                              extra_comments=[review_comment(90, 4, "Replaced by #7"), review_comment(91, 6, "Replaced by #8")])
        self.assertIn("reopen: o/alpha #6 (replacer #8 no longer names it)", lines, "control: #6 has no reopen line:\n" + "\n".join(lines))
        self.assertFalse([l for l in lines if l.startswith("reopen: o/alpha #4 ")], "#4 reopened while its replacer still names it")

    def test_an_indented_closing_note_reopens(self):
        # A closing note counts at a line start after optional whitespace. #4's note is indented, and #7 is closed.
        lines = self.reopened(closed=[closed_pull(4, head_of(4)), closed_pull(7, head_of(7))],
                              extra_comments=[review_comment(90, 4, "  Replaced by #7")])
        self.assertEqual(lines, ["reopen: o/alpha #4 (replacer #7 dropped)"], "\n".join(lines))

    def test_a_fenced_closing_note_reopens_nothing(self):
        # A closing note inside a fenced code block names nothing. Control: #6's plain note reopens.
        lines = self.reopened(closed=[closed_pull(4, head_of(4)), closed_pull(7, head_of(7)), closed_pull(6, head_of(6)), closed_pull(8, head_of(8))],
                              extra_comments=[review_comment(90, 4, "```\nReplaced by #7\n```"), review_comment(91, 6, "Replaced by #8")])
        self.assertIn("reopen: o/alpha #6 (replacer #8 dropped)", lines, "control: #6 has no reopen line:\n" + "\n".join(lines))
        self.assertEqual(lines, ["reopen: o/alpha #6 (replacer #8 dropped)"], "a closing note in a fenced block reopened #4")

    def test_an_unreadable_candidate_names_its_repo_and_number(self):
        # The reopen unknown text names OWNER/NAME #N, never a bare #N. The read of pulls/4 fails.
        host = closed_host("o/alpha", pulls=[named_pull(5, head_of(5))], comments=[record_of(5, head_of(5)), review_comment(90, 4, "Replaced by #7")],
                           closed=[closed_pull(4, head_of(4)), closed_pull(7, head_of(7))], unreadable=(4,), check_rows={head_of(5): green()})
        rc, out, err = self.run_args("--reviewed", "--root", self.alpha, hosts={self.alpha: host})
        unknown = [l for l in block_of(self, out, "o/alpha") if l.startswith("reopen unknown (")]
        self.assertTrue(unknown, "no `reopen unknown (...)` line for the unreadable #4:\n" + out + err)
        self.assertIn("o/alpha #4", unknown[0], "the reopen unknown line names #4 with no repo name:\n" + unknown[0])

    def test_zero_open_pulls_says_the_reopen_is_not_checked(self):
        # With no open pull request the reopen lines are not read. The block keeps its empty line and says so.
        host = closed_host("o/alpha", pulls=[], comments=[review_comment(90, 4, "Replaced by #7")],
                           closed=[closed_pull(4, head_of(4)), closed_pull(7, head_of(7))])
        block = block_of(self, self.reviewed(host), "o/alpha")
        self.assertIn("no open pull requests.", block, "\n".join(block))
        self.assertIn("reopen not checked (no open pull request)", block, "a zero-open block does not say the reopen was not checked:\n" + "\n".join(block))
        self.assertEqual(kind_lines(block, REOPENED), [], "\n".join(block))

    def test_a_merged_replacer_does_not_reopen(self):
        # Anchor: #6 reopens (replacer #8 closed, unmerged). #4's replacer #7 is merged, so #4 stays closed.
        lines = self.reopened(closed=[closed_pull(4, head_of(4)), closed_pull(7, head_of(7), merged=True), closed_pull(6, head_of(6)),
                                      closed_pull(8, head_of(8))],
                              extra_comments=[review_comment(90, 4, "Replaced by #7"), review_comment(91, 6, "Replaced by #8")])
        self.assertIn("reopen: o/alpha #6 (replacer #8 dropped)", lines, "control: #6 has no reopen line:\n" + "\n".join(lines))
        self.assertFalse([l for l in lines if l.startswith("reopen: o/alpha #4 ")], "#4 reopened although its replacer #7 merged")

    def test_an_open_pr_is_never_reopened(self):
        # Anchor: #6 reopens (replacer #8 closed, unmerged). #4 is open and carries a Replaced by comment: it is not closed, so no line.
        lines = self.reopened(closed=[closed_pull(6, head_of(6)), closed_pull(8, head_of(8))],
                              extra_pulls=[named_pull(4, head_of(4))],
                              extra_comments=[review_comment(90, 4, "Replaced by #8"), review_comment(91, 6, "Replaced by #8")])
        self.assertIn("reopen: o/alpha #6 (replacer #8 dropped)", lines, "control: #6 has no reopen line:\n" + "\n".join(lines))
        self.assertFalse([l for l in lines if l.startswith("reopen: o/alpha #4 ")], "an open PR was reopened")

    def test_a_chain_whose_tail_is_open_reopens_no_link(self):
        # Chain #4 -> #7 -> #9. Open #9 names #7, so the chain is alive and #4 stays closed. A reopen here would churn at every wake.
        lines = self.reopened(closed=[closed_pull(4, head_of(4)), closed_pull(7, head_of(7))],
                              extra_pulls=[named_pull(9, head_of(9), body="Replaces #7")],
                              extra_comments=[review_comment(90, 4, "Replaced by #7"), review_comment(91, 7, "Replaced by #9")])
        self.assertEqual(lines, [], "a closed link reopened while its chain still ends at open #9:\n" + "\n".join(lines))

    def test_a_twelve_chain_with_eleven_closed_links_reopens_no_link(self):
        # Open #12 names #11, and each of #1 to #11 is closed with its note. Every link is alive through the chain: no reopen line.
        closed = [closed_pull(n, head_of(n)) for n in range(1, 12)]
        notes = [review_comment(100 + n, n, f"Replaced by #{n + 1}") for n in range(1, 12)]
        block = self.block_for_alpha(pulls=[named_pull(12, head_of(12), body="Replaces #11")], comments=notes, closed=closed)
        self.assertEqual(kind_lines(block, REOPENED), [], "a closed link of a live chain reopened:\n" + "\n".join(block))

    def test_a_closed_chain_tail_reopens_one_link_on_one_wake(self):
        # Chain #4 -> #7 -> #9, with #9 closed and unmerged. The nearest link #7 reopens (its replacer #9 is dropped). #4 reopens alone or
        # waits for a later wake: either choice passes, and a wake that reopens both is wrong.
        lines = self.reopened(closed=[closed_pull(4, head_of(4)), closed_pull(7, head_of(7)), closed_pull(9, head_of(9))],
                              extra_comments=[review_comment(90, 4, "Replaced by #7"), review_comment(91, 7, "Replaced by #9")])
        self.assertEqual(len(lines), 1, "a closed chain tail reopened more than one link on one wake:\n" + "\n".join(lines))
        self.assertIn(lines[0], ["reopen: o/alpha #7 (replacer #9 dropped)", "reopen: o/alpha #4 (replacer #7 dropped)"], "\n".join(lines))

    def test_a_reopen_waits_while_another_open_pr_still_names_the_closed_one(self):
        # Probe: #5 is closed with the note `Replaced by #9`, and #9 is closed unmerged, so the reopen read would reopen #5. Open #12 says
        # `Replaces #5`, so a reopened #5 closes again by #12 on the next wake. Control: without #12, the same run reopens #5.
        closed = [closed_pull(5, head_of(5)), closed_pull(9, head_of(9))]
        notes = [review_comment(90, 5, "Replaced by #9")]
        control = kind_lines(self.block_for_alpha(pulls=[named_pull(4, head_of(4))], comments=notes, closed=closed), REOPENED)
        self.assertEqual(control, ["reopen: o/alpha #5 (replacer #9 dropped)"], "control: the reopen line for #5 is missing without #12:\n" + "\n".join(control))
        pulls = [named_pull(4, head_of(4)), named_pull(12, head_of(12), body="Replaces #5")]
        lines = kind_lines(self.block_for_alpha(pulls=pulls, comments=notes, closed=closed), REOPENED)
        self.assertEqual(lines, [], "#5 reopened while open #12 still names it, so the next wake closes it again:\n" + "\n".join(lines))

    def test_a_note_older_than_every_open_pr_is_not_read(self):
        # Pin of the stated limit: the comment list starts at the oldest open pull request, so #4's note of 2026-09-01 is never read and #4 does
        # not reopen, though its replacer #7 is closed unmerged. Why it stays so: an older note needs an earlier comment read on every wake,
        # and each quiet run would pay for it. Control: #6's note is inside the window, and it reopens.
        closed = [closed_pull(4, head_of(4)), closed_pull(6, head_of(6)), closed_pull(7, head_of(7)), closed_pull(8, head_of(8))]
        notes = [review_comment(90, 4, "Replaced by #7", created="2026-09-01T00:00:00Z"), review_comment(91, 6, "Replaced by #8")]
        lines = kind_lines(self.block_for_alpha(pulls=[named_pull(5, head_of(5))], comments=notes, closed=closed), REOPENED)
        self.assertIn("reopen: o/alpha #6 (replacer #8 dropped)", lines, "control: the note inside the window does not reopen #6:\n" + "\n".join(lines))
        self.assertFalse([l for l in lines if l.startswith("reopen: o/alpha #4 ")], "#4 reopened from a note older than the oldest open pull request")

    def test_a_reopen_line_repeats_on_every_wake_after_a_hand_close(self):
        # Pin of a named limit, not the desired end. The desired end: #4 stays closed after the owner closes it by hand. Today its closing note still
        # names #7, which is closed unmerged, so each wake prints the reopen line again. The limit is `reopened-then-closed-by-hand-reopens-again`
        # in docs/debts/notes.md, and it becomes a debt after a real incident. Passes today.
        closed = [closed_pull(4, head_of(4)), closed_pull(7, head_of(7))]
        notes = [review_comment(90, 4, "Replaced by #7")]
        want = ["reopen: o/alpha #4 (replacer #7 dropped)"]

        def wake():
            return kind_lines(self.block_for_alpha(pulls=[named_pull(5, head_of(5))], comments=[record_of(5, head_of(5)), *notes], closed=closed,
                                                   check_rows={head_of(5): green()}), REOPENED)

        self.assertEqual(wake(), want, "the first wake prints no reopen line for #4")
        self.assertEqual(wake(), want, "the next wake, after a hand close, did not repeat the reopen line for #4 (the named limit is gone)")


class CarryCost(CloseEnv):
    """The gh reads of the carry check. Only a draft carries, so a busy ready done PR reads no compare with the open PRs on its base, and no compare
    with main for the PR that holds it. Main reads no compare for a busy ready PR."""

    def compare_reads(self, pulls, comments, check_rows, compares=None):
        """-> the compare routes of one run of `merge --reviewed` over alpha, each read once per call (count_gh)."""
        host = closed_host("o/alpha", pulls=pulls, comments=comments, check_rows=check_rows, compares=compares or {}, count_gh=True)
        rc, out, err = self.run_args("--reviewed", "--root", self.alpha, hosts={self.alpha: host})
        self.assertEqual(rc, 0, out + err)
        return [route for route in host.gh_calls if route.startswith("compare/")]

    def test_a_busy_ready_done_pr_with_no_holder_reads_no_compare(self):
        # Control: the same done PR as a draft reads its compares with the two open drafts, so the count sees the reads.
        def reads(draft):
            pulls = [named_pull(5, head_of(5), draft=draft), named_pull(6, head_of(6), draft=True), named_pull(7, head_of(7), draft=True)]
            return self.compare_reads(pulls, [record_of(5, head_of(5))], {head_of(5): running()})

        self.assertTrue(reads(True), "control: the draft done #5 read no compare, so the count below proves nothing")
        self.assertEqual(reads(False), [], "a busy ready done #5 with no holder read a compare; main reads none")

    def test_a_busy_ready_done_pr_with_a_holder_pays_no_base_compare(self):
        # Control: the same done PR as a draft pays the compare with main, because its holder makes it a carry candidate.
        head5 = head_of(5)

        def reads(draft):
            pulls = [named_pull(5, head5, draft=draft), named_pull(6, head_of(6), draft=True)]
            return self.compare_reads(pulls, [record_of(5, head5)], {head5: running()}, compares={(head5, head_of(6)): "ahead"})

        self.assertIn(f"compare/{head5}...main", reads(True), "control: the draft done #5 with a holder paid no compare with main")
        self.assertNotIn(f"compare/{head5}...main", reads(False), "a busy ready done #5 paid a compare with main for its holder")


class ReplacesCycles(CloseEnv):
    """A cycle of Replaces claims closes none of its members. The two-member cycle is test_a_mutual_replaces_closes_neither in CloseAsReplaced."""

    def test_a_three_cycle_closes_none(self):
        pulls = [named_pull(1, head_of(1), body="Replaces #3"), named_pull(2, head_of(2), body="Replaces #1"),
                 named_pull(3, head_of(3), body="Replaces #2")]
        block = self.block_for_alpha(pulls=pulls)
        self.assertEqual(kind_lines(block, REPLACED), [], "a three-cycle closed one of its members:\n" + "\n".join(block))

    def test_a_four_cycle_closes_none(self):
        pulls = [named_pull(1, head_of(1), body="Replaces #4"), named_pull(2, head_of(2), body="Replaces #1"),
                 named_pull(3, head_of(3), body="Replaces #2"), named_pull(4, head_of(4), body="Replaces #3")]
        block = self.block_for_alpha(pulls=pulls)
        self.assertEqual(kind_lines(block, REPLACED), [], "a four-cycle closed one of its members:\n" + "\n".join(block))

    def test_a_claim_that_leads_into_a_cycle_closes_none(self):
        # #4 names #1, and #1, #2 and #3 form a three-cycle. Following #1's replacers returns to #1, so #4's claim on #1 is dropped too. This is
        # a state choice the test names, not the mechanism. #1 closes nothing, and neither does any other cycle member.
        pulls = [named_pull(1, head_of(1), body="Replaces #3"), named_pull(2, head_of(2), body="Replaces #1"),
                 named_pull(3, head_of(3), body="Replaces #2"), named_pull(4, head_of(4), body="Replaces #1")]
        block = self.block_for_alpha(pulls=pulls)
        self.assertEqual(kind_lines(block, REPLACED), [], "a PR that leads into a cycle closed a member of it:\n" + "\n".join(block))


class ReplacesFences(CloseEnv):
    """A Replaces line inside a fenced code block names nothing, and a line that only looks like a fence opens none. Each case sits beside a
    control: open #10 replaces open #11, a plain claim that prints."""

    def fenced_lines(self, body):
        """-> the REPLACED lines when open #6 has `body` and names open #5, with the control pair #10 and #11 beside them."""
        pulls = [named_pull(5, head_of(5)), named_pull(6, head_of(6), body=body), named_pull(10, head_of(10), body="Replaces #11"),
                 named_pull(11, head_of(11))]
        return kind_lines(self.block_for_alpha(pulls=pulls), REPLACED)

    def test_a_four_tick_fence_holding_a_three_tick_line_names_nothing(self):
        # The ``` line inside the four-tick fence does not close it, so `Replaces #5` is still fenced.
        lines = self.fenced_lines("````\n```\nReplaces #5\n```\n````")
        self.assertIn("close as replaced: o/alpha #11 by #10", lines, "control: a plain claim prints no line:\n" + "\n".join(lines))
        self.assertNotIn("close as replaced: o/alpha #5 by #6", lines, "a Replaces inside a four-tick fence closed #5")

    def test_a_three_tick_fence_holding_a_tilde_line_names_nothing(self):
        # A ~~~ line inside a ``` fence is content, not a closing fence, so `Replaces #5` is still fenced.
        lines = self.fenced_lines("```\n~~~\nReplaces #5\n~~~\n```")
        self.assertIn("close as replaced: o/alpha #11 by #10", lines, "control: a plain claim prints no line:\n" + "\n".join(lines))
        self.assertNotIn("close as replaced: o/alpha #5 by #6", lines, "a Replaces inside a three-tick fence holding a ~~~ line closed #5")

    def test_a_line_of_inline_code_is_not_a_fence(self):
        # ```x``` opens and closes on one line. It is inline code, not a fence, so the real `Replaces #5` after it counts.
        lines = self.fenced_lines("```x```\nReplaces #5")
        self.assertEqual(lines, ["close as replaced: o/alpha #5 by #6", "close as replaced: o/alpha #11 by #10"],
                         "the line of inline code opened a fence and hid the real Replaces #5")


# The gh routes of a run with no reopen candidate. The run must make exactly these reads: each extra one is paid by every quiet run.
QUIET_MAIN_READS = collections.Counter({
    "branches/main/protection/required_status_checks": 2,
    f"commits/{head_of(5)}/check-runs": 2, f"commits/{head_of(5)}/status": 2,
    f"commits/{head_of(6)}/check-runs": 1, f"commits/{head_of(6)}/status": 1,
    f"compare/{head_of(5)}...{head_of(6)}": 1, f"compare/{head_of(5)}...main": 1,
    "issues/comments": 1, "pulls": 1,
})


class ReadCost(CloseEnv):
    """The gh reads a run makes, counted at the seam (PullsHost.gh_calls). A reopen candidate adds at most two reads: pulls/N, and pulls/R
    when R is closed. An open R's body is in the open list, so it adds none."""

    def quiet(self, closed=(), extra_comments=(), body6=""):
        """-> the gh routes of a run over open #5 (done) and #6 (no record, body `body6`), with no candidate unless `closed` and `extra_comments` give one."""
        host = closed_host("o/alpha", pulls=[named_pull(5, head_of(5)), named_pull(6, head_of(6), body=body6)],
                           comments=[record_of(5, head_of(5)), *extra_comments], closed=closed, check_rows={head_of(5): green()}, count_gh=True)
        rc, out, err = self.run_args("--reviewed", "--root", self.alpha, hosts={self.alpha: host})
        self.assertEqual(rc, 0, out + err)
        return collections.Counter(host.gh_calls)

    def test_a_quiet_repo_reads_what_main_reads_and_a_closed_candidate_adds_two(self):
        base = self.quiet()
        self.assertEqual(base, QUIET_MAIN_READS, "a run with no reopen candidate makes other reads than main makes")
        cand = self.quiet(closed=[closed_pull(4, head_of(4)), closed_pull(7, head_of(7))], extra_comments=[review_comment(90, 4, "Replaced by #7")])
        self.assertEqual(cand - base, collections.Counter({"pulls/4": 1, "pulls/7": 1}),
                         "a closed candidate whose replacer is closed: want exactly two reads, pulls/4 and pulls/7")
        # A replacement line judges N from the open list: a body naming a closed PR, or an unknown one, reads nothing more.
        for body in ("Replaces #2", "Replaces #99"):
            with self.subTest(body=body):
                named = self.quiet(closed=[closed_pull(2, head_of(2))], body6=body)
                self.assertEqual(named - base, collections.Counter(), f"a body `{body}` read a pull request by number")

    def test_an_open_replacer_candidate_adds_one_read(self):
        base = self.quiet()
        cand = self.quiet(closed=[closed_pull(4, head_of(4))], extra_comments=[review_comment(90, 4, "Replaced by #6")])
        self.assertEqual(cand - base, collections.Counter({"pulls/4": 1}),
                         "a candidate whose replacer #6 is open: want exactly one read, pulls/4; the body of #6 is already in the open list")

    def chain_reads(self):
        """-> the gh routes of one run: open #14 with no record, and twelve closed PRs #1 to #12, each with a `Replaced by #13` note. #13 is merged."""
        closed = [closed_pull(n, head_of(n)) for n in range(1, 13)] + [closed_pull(13, head_of(13), merged=True)]
        notes = [review_comment(100 + n, n, "Replaced by #13") for n in range(1, 13)]
        host = closed_host("o/alpha", pulls=[named_pull(14, head_of(14))], comments=notes, closed=closed, count_gh=True)
        rc, out, err = self.run_args("--reviewed", "--root", self.alpha, hosts={self.alpha: host})
        self.assertEqual(rc, 0, out + err)
        return collections.Counter(host.gh_calls)

    def test_a_merged_replacer_shared_by_twelve_candidates_is_read_once_per_wake(self):
        self.assertEqual(self.chain_reads()["pulls/13"], 1, "the merged replacer #13 was read once per candidate, not once per wake")

    def test_each_closed_candidate_is_read_once_per_wake(self):
        # Pin: pulls/N is read once for each of the twelve candidates, so twelve reads in all.
        counts = self.chain_reads()
        self.assertEqual([counts[f"pulls/{n}"] for n in range(1, 13)], [1] * 12, "a closed candidate was not read exactly once per wake")


if __name__ == "__main__":
    unittest.main()
