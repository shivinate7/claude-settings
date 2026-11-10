#!/usr/bin/env python3
"""Cases for the close lines and the reopen line of `merge --reviewed --root DIR`, and for the batch line that drops a PR they close.

Run: python3 merge/test_close_replaced.py
The lines, per root, after the batch line:
  close as replaced: OWNER/NAME #N by #R    an open PR R whose body holds `Replaces #N`, N another open PR
  close as carried: OWNER/NAME #A by #B     an open PR A with a done record whose head open PR B holds
  close as carried unknown (REASON)         the compare that decides a carried close failed; exit 1
  reopen: OWNER/NAME #N (replacer #R dropped)                 a closed N whose replacer R is closed, unmerged
  reopen: OWNER/NAME #N (replacer #R no longer names it)      a closed N whose replacer R is open and no longer names N
Every fixture is test_merge.py's, the one home of the fake host and the record helpers. The one piece this file adds is ClosedHost,
which answers `pulls/<n>` for a closed pull request; test_merge.py's PullsHost answers open ones only. ReviewedRoots is used unbound,
so its own cases run in merge/test_merge.py and not again here.
"""
import collections, json, re, unittest

import test_merge as tm  # the one home of the fixtures (merge/test_merge.py)
from test_merge import PullsHost, batch_pull, batch_lines_of, green, record_of, review_comment

REPLACED, CARRIED, REOPENED = "close as replaced: ", "close as carried: ", "reopen: "


def head_of(n):
    """A full 40-hex head for pull request n, distinct per n up to 15."""
    return format(n, "x") * 40


def named_pull(number, sha, body="", draft=False, base="main"):
    """An open pull request row with its body, as the open list gives it."""
    return {**batch_pull(number, sha, base=base, draft=draft), "body": body}


def closed_pull(number, sha, body="", merged=False):
    """A pull request the open list does not hold: `pulls/<n>` answers it closed, and merged when `merged`."""
    return {**named_pull(number, sha, body), "state": "closed", "merged": merged}


class ClosedHost(PullsHost):
    """PullsHost that also answers `pulls/<n>` for each closed pull request in `closed`. Every other number and every other read is PullsHost's."""

    def __init__(self, pulls, check_rows, closed=(), unreadable=(), **kw):
        super().__init__(pulls, check_rows, **kw)
        self.closed, self.unreadable = list(closed), set(unreadable)

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
    """The fake host of one --root repo: its open pulls, its comments, its check runs, and the closed pulls `pulls/<n>` answers."""
    return ClosedHost(list(pulls), check_rows or {}, closed=closed, comments=list(comments), repo=repo, **kw)


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
        # Pin, ruling 2 correction (lane, 22:22 CST): every REPLACED claim stands. #7 replaces #4 and is itself replaced by #9: both lines print.
        # Only the carried check drops replaced PRs. The 22:14 CST wording that voided #7's claim is withdrawn.
        pulls = [named_pull(4, head_of(4)), named_pull(7, head_of(7), body="Replaces #4"), named_pull(9, head_of(9), body="Replaces #7")]
        block = self.block_for_alpha(pulls=pulls)
        self.assertEqual(kind_lines(block, REPLACED), ["close as replaced: o/alpha #4 by #7", "close as replaced: o/alpha #7 by #9"], "\n".join(block))

    def test_a_full_repo_of_twelve_chained_prs_closes_eleven(self):
        # Pin, ruling 2 correction (lane, 22:22 CST): a chain of replacers prints one line per replaced PR, all in one pass, so twelve PRs
        # give eleven lines.
        pulls = [named_pull(n, head_of(n), body=f"Replaces #{n - 1}" if n > 1 else "") for n in range(1, 13)]
        block = self.block_for_alpha(pulls=pulls)
        self.assertEqual(kind_lines(block, REPLACED), [f"close as replaced: o/alpha #{n} by #{n + 1}" for n in range(1, 12)], "\n".join(block))

    def test_a_mutual_replaces_closes_neither(self):
        # Ruling 1 (lane, 22:14 CST): #1 says Replaces #2 and #2 says Replaces #1. Neither closes. Control: #8 replaces open #6 and prints.
        pulls = [named_pull(1, head_of(1), body="Replaces #2"), named_pull(2, head_of(2), body="Replaces #1"),
                 named_pull(6, head_of(6)), named_pull(8, head_of(8), body="Replaces #6")]
        lines = kind_lines(self.block_for_alpha(pulls=pulls), REPLACED)
        self.assertIn("close as replaced: o/alpha #6 by #8", lines, "control: #8 replaces open #6 and prints no line:\n" + "\n".join(lines))
        self.assertEqual(lines, ["close as replaced: o/alpha #6 by #8"], "a mutual Replaces closed one of its pair")

    def test_a_replacer_on_another_base_closes_nothing(self):
        # Ruling 4 (lane, 22:14 CST): #7 is on base release and names `Replaces #4`; #4 is on main, so no line. Control: #8 on main replaces #6.
        pulls = [named_pull(4, head_of(4)), named_pull(6, head_of(6)), named_pull(7, head_of(7), body="Replaces #4", base="release"),
                 named_pull(8, head_of(8), body="Replaces #6")]
        lines = kind_lines(self.block_for_alpha(pulls=pulls), REPLACED)
        self.assertIn("close as replaced: o/alpha #6 by #8", lines, "control: #8 replaces open #6 and prints no line:\n" + "\n".join(lines))
        self.assertEqual(lines, ["close as replaced: o/alpha #6 by #8"], "a PR on base release closed #4 on base main")

    def test_a_quoted_replaces_closes_nothing(self):
        # Ruling 5 (lane, 22:14 CST): Replaces counts only at a line start, after optional whitespace, and not in a `>` quote. Control: #8's
        # body is indented, and that is allowed.
        pulls = [named_pull(4, head_of(4)), named_pull(6, head_of(6)), named_pull(7, head_of(7), body="> Replaces #4"),
                 named_pull(8, head_of(8), body="  Replaces #6")]
        lines = kind_lines(self.block_for_alpha(pulls=pulls), REPLACED)
        self.assertIn("close as replaced: o/alpha #6 by #8", lines, "control: an indented Replaces prints no line:\n" + "\n".join(lines))
        self.assertEqual(lines, ["close as replaced: o/alpha #6 by #8"], "a quoted Replaces closed #4")

    def test_a_fenced_replaces_closes_nothing(self):
        # Ruling 5 (lane, 22:14 CST): a Replaces line inside a fenced code block names nothing. Control: #8 replaces open #6.
        pulls = [named_pull(4, head_of(4)), named_pull(6, head_of(6)), named_pull(7, head_of(7), body="```\nReplaces #4\n```"),
                 named_pull(8, head_of(8), body="Replaces #6")]
        lines = kind_lines(self.block_for_alpha(pulls=pulls), REPLACED)
        self.assertIn("close as replaced: o/alpha #6 by #8", lines, "control: #8 replaces open #6 and prints no line:\n" + "\n".join(lines))
        self.assertEqual(lines, ["close as replaced: o/alpha #6 by #8"], "a Replaces in a fenced block closed #4")

    def test_a_replaces_inside_a_sentence_closes_nothing(self):
        # Ruling 5 (lane, 22:14 CST): Replaces must start its line. Control: #8 replaces open #6.
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
        # The empty state: bravo has no open pull request, so its block is its empty line and, under ruling 3 (lane, 22:14 CST), the line that
        # says the reopen was not checked. alpha's replaced #4 is the control.
        self.bravo = tm.ReviewedRoots.checkout(self, "bravo")
        hosts = {self.alpha: closed_host("o/alpha", pulls=[named_pull(4, head_of(4)), named_pull(7, head_of(7), body="Replaces #4")]),
                 self.bravo: closed_host("o/bravo")}
        rc, out, err = self.run_args("--reviewed", "--root", self.alpha, "--root", self.bravo, hosts=hosts)
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(kind_lines(block_of(self, out, "o/alpha"), REPLACED), ["close as replaced: o/alpha #4 by #7"], out)
        self.assertEqual(block_of(self, out, "o/bravo"), ["no open pull requests.", "reopen not checked (no open pull request)"],
                         "an empty repo printed other than its empty line and the reopen-not-checked line:\n" + out)


class CloseAsCarried(CloseEnv):
    """`close as carried: OWNER/NAME #A by #B`: a done A whose head an open B on the base holds. Draft or ready B both count."""

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
        # Ruling 2 (lane, 22:14 CST): #4 holds #3, and #5 names #4 as replaced without holding #3. #4 is named on a line, so it holds nothing:
        # #3 gets no carried line, and the replaced line for #4 prints.
        pulls = [named_pull(3, head_of(3)), named_pull(4, head_of(4)), named_pull(5, head_of(5), body="Replaces #4")]
        host = closed_host("o/alpha", pulls=pulls, comments=[record_of(3, head_of(3))], check_rows={head_of(3): green()},
                           compares={(head_of(3), head_of(4)): "ahead"})
        block = block_of(self, self.reviewed(host), "o/alpha")
        self.assertEqual(kind_lines(block, REPLACED), ["close as replaced: o/alpha #4 by #5"], "\n".join(block))
        self.assertEqual(kind_lines(block, CARRIED), [], "#3 is carried by #4, which is named replaced:\n" + "\n".join(block))

    def test_a_done_pr_held_only_by_a_replaced_pr_stays_on_the_batch_line(self):
        # Pin, ruling 2 (lane, 22:14 CST), the case the builder flagged: #4 is the only PR whose head holds #3, and #5 names #4 as replaced. #4 holds
        # nothing for the carried check, so #3 gets no carried line and stays on the batch line.
        pulls = [named_pull(3, head_of(3)), named_pull(4, head_of(4)), named_pull(5, head_of(5), body="Replaces #4")]
        host = closed_host("o/alpha", pulls=pulls, comments=[record_of(3, head_of(3))], check_rows={head_of(3): green()},
                           compares={(head_of(3), head_of(4)): "ahead"})
        block = block_of(self, self.reviewed(host), "o/alpha")
        self.assertEqual(kind_lines(block, CARRIED), [], "#3 is carried by #4, which is named replaced:\n" + "\n".join(block))
        self.assertEqual(batch_lines_of(block), ["open batch now: o/alpha #3"], "#3 left the batch line although only a replaced PR holds it:\n" + "\n".join(block))

    def test_an_identical_head_under_a_replaced_lower_is_not_carried(self):
        # Ruling 2 (lane, 22:14 CST): #10 is named replaced by #12. #11 has #10's head, so #10 would carry it, but #10 holds nothing.
        same = head_of(10)
        pulls = [named_pull(10, same), named_pull(11, same), named_pull(12, head_of(12), body="Replaces #10")]
        host = closed_host("o/alpha", pulls=pulls, comments=[record_of(11, same)], check_rows={same: green()})
        block = block_of(self, self.reviewed(host), "o/alpha")
        self.assertEqual(kind_lines(block, REPLACED), ["close as replaced: o/alpha #10 by #12"], "\n".join(block))
        self.assertEqual(kind_lines(block, CARRIED), [], "#11 is carried by #10, which is named replaced:\n" + "\n".join(block))

    def test_identical_heads_close_only_the_higher_numbered_pr(self):
        # #4 and #6 have one head, and each holds the other. Only #6 closes, by #4. #4 stays open.
        same = head_of(4)
        block = self.block_for_alpha(pulls=[named_pull(4, same), named_pull(6, same)], comments=[record_of(4, same), record_of(6, same)],
                                     check_rows={same: green()})
        self.assertEqual(kind_lines(block, CARRIED), ["close as carried: o/alpha #6 by #4"], "\n".join(block))

    def test_a_chain_closes_each_lane_under_the_holder_outside_it(self):
        # #3 is inside #5, and #5 is inside #4. #3's lowest-numbered holder is #4, and #5's holder is #4. #4 closes nothing.
        heads = {3: head_of(3), 4: head_of(4), 5: head_of(5)}
        pulls = [named_pull(n, heads[n]) for n in (3, 4, 5)]
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
        # Ruling 5 (lane, 22:14 CST): a closing note counts at a line start after optional whitespace. #4's note is indented, and #7 is closed.
        lines = self.reopened(closed=[closed_pull(4, head_of(4)), closed_pull(7, head_of(7))],
                              extra_comments=[review_comment(90, 4, "  Replaced by #7")])
        self.assertEqual(lines, ["reopen: o/alpha #4 (replacer #7 dropped)"], "\n".join(lines))

    def test_a_fenced_closing_note_reopens_nothing(self):
        # Ruling 5 (lane, 22:14 CST): a closing note inside a fenced code block names nothing. Control: #6's plain note reopens.
        lines = self.reopened(closed=[closed_pull(4, head_of(4)), closed_pull(7, head_of(7)), closed_pull(6, head_of(6)), closed_pull(8, head_of(8))],
                              extra_comments=[review_comment(90, 4, "```\nReplaced by #7\n```"), review_comment(91, 6, "Replaced by #8")])
        self.assertIn("reopen: o/alpha #6 (replacer #8 dropped)", lines, "control: #6 has no reopen line:\n" + "\n".join(lines))
        self.assertEqual(lines, ["reopen: o/alpha #6 (replacer #8 dropped)"], "a closing note in a fenced block reopened #4")

    def test_an_unreadable_candidate_names_its_repo_and_number(self):
        # Ruling 6 (lane, 22:14 CST): the reopen unknown text names OWNER/NAME #N, never a bare #N. The read of pulls/4 fails.
        host = closed_host("o/alpha", pulls=[named_pull(5, head_of(5))], comments=[record_of(5, head_of(5)), review_comment(90, 4, "Replaced by #7")],
                           closed=[closed_pull(4, head_of(4)), closed_pull(7, head_of(7))], unreadable=(4,), check_rows={head_of(5): green()})
        rc, out, err = self.run_args("--reviewed", "--root", self.alpha, hosts={self.alpha: host})
        unknown = [l for l in block_of(self, out, "o/alpha") if l.startswith("reopen unknown (")]
        self.assertTrue(unknown, "no `reopen unknown (...)` line for the unreadable #4:\n" + out + err)
        self.assertIn("o/alpha #4", unknown[0], "the reopen unknown line names #4 with no repo name:\n" + unknown[0])

    def test_zero_open_pulls_says_the_reopen_is_not_checked(self):
        # Ruling 3 (lane, 22:14 CST): with no open pull request the reopen lines are not read. The block keeps its empty line and says so.
        host = closed_host("o/alpha", pulls=[], comments=[review_comment(90, 4, "Replaced by #7")],
                           closed=[closed_pull(4, head_of(4)), closed_pull(7, head_of(7))])
        block = block_of(self, self.reviewed(host), "o/alpha")
        self.assertIn("no open pull requests.", block, "\n".join(block))
        self.assertIn("reopen not checked (no open pull request)", block, "a zero-open block does not say the reopen was not checked:\n" + "\n".join(block))
        self.assertEqual(kind_lines(block, REOPENED), [], "\n".join(block))

    def test_a_merged_replacer_does_not_reopen(self):
        # Anchor: #6 reopens (replacer #8 closed, unmerged). #4's replacer #7 was merged, so #4 stays closed.
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


# The gh routes of ReadCost.quiet on main (ddaa393c0), as measured. A run with no reopen candidate must make exactly these.
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


if __name__ == "__main__":
    unittest.main()
