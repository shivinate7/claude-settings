#!/usr/bin/env python3
"""revert_rule, called directly: does a live revert on a branch lift a red run (the module docstring of revert_rule.py).

Run: python3 actions/ci-alarm/test_revert_rule.py. Stdlib unittest. gh_json is replaced by a fake in every case, so no case
reaches `gh api`, and no case reads or writes a file.
"""
import contextlib
import io
import os
import re
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import revert_rule  # noqa: E402  the one home of the revert rule, beside this file

REPO = "owner/repo"
BRANCH = "main"
H, C1, C2, C3 = "a" * 40, "b" * 40, "c" * 40, "d" * 40  # the red run's head, then three later commits
SEARCHED = re.compile(r"This reverts commit ([0-9a-f]{40})")
COMPARED = re.compile(r"/compare/([0-9a-f]{40})\.\.\.")


def revert_msg(target):
    return f'Revert "work"\n\nThis reverts commit {target}.\n'


def hit(commit_sha, message, date=None):
    commit = {"message": message}
    if date is not None:  # the committer date each search/commits hit carries: the order git log reads (merge.py), which the reverter case needs
        commit["committer"] = {"date": date}
    return {"sha": commit_sha, "commit": commit}


def search_reply(*hits, total=None, incomplete=False):
    return {"total_count": len(hits) if total is None else total, "incomplete_results": incomplete, "items": list(hits)}


def compare_reply(status):
    return {"status": status}


def compare_path(sha):
    return f"repos/{REPO}/compare/{sha}...{BRANCH}?per_page=1"


class FakeGh:
    """Stands in for revert_rule.gh_json. `search` maps a head to its search reply. `compare` maps a sha to its compare reply, or to
    an exception to raise. An unmapped head has no hits, and an unmapped sha is behind the branch. Every call is kept in `calls`."""

    def __init__(self):
        self.search, self.compare, self.calls = {}, {}, []

    def __call__(self, *args):
        self.calls.append(args)
        if args[:3] == ("-X", "GET", "search/commits"):
            return self.search.get(SEARCHED.search(args[4]).group(1), search_reply())
        if COMPARED.search(args[0]) is None:
            raise AssertionError(f"unexpected gh api call: {args}")
        reply = self.compare.get(COMPARED.search(args[0]).group(1), compare_reply("behind"))
        if isinstance(reply, Exception):
            raise reply
        return reply

    def searched(self):
        """The heads searched for, in call order."""
        return [SEARCHED.search(a[4]).group(1) for a in self.calls if a[:3] == ("-X", "GET", "search/commits")]

    def compare_paths(self):
        """The compare paths asked, in call order."""
        return [a[0] for a in self.calls if COMPARED.search(a[0])]

    def compared(self):
        """The shas compared with the branch, in call order."""
        return [COMPARED.search(p).group(1) for p in self.compare_paths()]


class CountingMap(dict):
    """A dict that fails the test after 100 membership reads, so a walk that never ends fails instead of hanging."""
    reads = 0

    def __contains__(self, key):
        self.reads += 1
        if self.reads > 100:
            raise AssertionError("net_reverted did not stop on a cycle: more than 100 reads")
        return super().__contains__(key)


class RevertMap(unittest.TestCase):
    def test_a_full_sha_revert_line_maps_the_reverted_commit_to_its_revert(self):
        # Named failure: the 40-hex line is not read, so H reads as not reverted.
        self.assertEqual(revert_rule.revert_map([("R", [H], revert_msg(H))]), {H: "R"},
                         "the 40-hex revert line did not map H to its revert R")

    def test_a_short_sha_or_a_body_with_no_revert_line_maps_nothing(self):
        # Named failure: a short sha, or a body with no revert line, is read as a revert of H.
        bodies = {"short sha": f'Revert "work"\n\nThis reverts commit {H[:7]}.\n',
                  "no revert line": f"Fix the flake seen on {H}\n"}
        for name, body in bodies.items():
            with self.subTest(body=name):
                self.assertEqual(revert_rule.revert_map([("R", [H], body)]), {},
                                 "a body that is not a 40-hex revert line mapped a commit")


class NetReverted(unittest.TestCase):
    def test_an_odd_chain_is_a_net_revert(self):
        # One revert, then three. Named failure: the parity is inverted, so one revert reads as not undone.
        for name, undone in {"one revert": {H: C1}, "three reverts": {H: C1, C1: C2, C2: C3}}.items():
            with self.subTest(chain=name):
                self.assertTrue(revert_rule.net_reverted(undone, H), "an odd chain of reverts of H is not a net revert")

    def test_an_even_chain_is_not_a_net_revert(self):
        # A revert of H, and a revert of that revert: H stands. Named failure: the parity is inverted, so two reverts read as undone.
        self.assertFalse(revert_rule.net_reverted({H: C1, C1: C2}, H), "an even chain of reverts of H reads as a net revert")

    def test_a_commit_with_no_revert_is_not_a_net_revert(self):
        self.assertFalse(revert_rule.net_reverted({}, H), "a commit with no revert reads as a net revert")

    def test_a_cycle_ends_the_walk_and_reads_even(self):
        # H is reverted by C1, and C1 by H: two steps, then the walk meets H again and stops.
        # Named failure: the walk does not stop at the repeat, so it never returns.
        self.assertFalse(revert_rule.net_reverted(CountingMap({H: C1, C1: H}), H),
                         "a two-step cycle reads as a net revert, where the count is even")


class RuleCase(unittest.TestCase):
    """Each case gets a fresh fake in place of gh_json. The case sets the replies it needs, then reads what the fake recorded."""

    def setUp(self):
        self.gh = FakeGh()
        patcher = mock.patch.object(revert_rule, "gh_json", self.gh)
        patcher.start()
        self.addCleanup(patcher.stop)

    def live(self, head=H):
        return revert_rule.live_revert(REPO, BRANCH, head)

    def main(self, head=H):
        with contextlib.redirect_stderr(io.StringIO()):
            return revert_rule.main(["--repo", REPO, "--branch", BRANCH, "--head", head])

    def exit_code(self, head=H):
        """main's exit code. An exception that escapes main exits the process 1, which alarm.sh reads as no revert: a named failure here."""
        try:
            return self.main(head)
        except Exception as e:
            self.fail(f"main raised {type(e).__name__} ({e}) instead of an exit code: the process exits 1, which alarm.sh reads as no revert")

    def main_err(self, head=H):
        """main's exit code and its stderr, so a case can name which read gave the exit. An escaped exception is a named failure, as in exit_code."""
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err):
                got = revert_rule.main(["--repo", REPO, "--branch", BRANCH, "--head", head])
        except Exception as e:
            self.fail(f"main raised {type(e).__name__} ({e}) instead of an exit code: the process exits 1, which alarm.sh reads as no revert")
        return got, err.getvalue()


class LiveRevert(RuleCase):
    def test_a_reachable_revert_lifts_the_run(self):
        # Ahead and identical both mean the revert is on the branch.
        # Named failure: a revert that is on the branch does not lift the run.
        for status in ("ahead", "identical"):
            with self.subTest(status=status):
                self.gh.calls.clear()
                self.gh.search[H] = search_reply(hit(C1, revert_msg(H)))
                self.gh.compare[C1] = compare_reply(status)
                got = self.live()
                self.assertEqual(self.gh.compare_paths(), [compare_path(C1)], "the hit was not compared with the branch")
                self.assertEqual(got, C1, f"a revert whose compare is {status} did not lift the run")

    def test_a_revert_the_branch_does_not_reach_does_not_lift(self):
        # Behind and diverged both mean the revert is not on the branch.
        # Named failure: a revert off the branch lifts the run.
        for status in ("behind", "diverged"):
            with self.subTest(status=status):
                self.gh.calls.clear()
                self.gh.search[H] = search_reply(hit(C1, revert_msg(H)))
                self.gh.compare[C1] = compare_reply(status)
                got = self.live()
                self.assertEqual(self.gh.compare_paths(), [compare_path(C1)], "the hit was not compared with the branch")
                self.assertIsNone(got, f"a revert whose compare is {status} lifted the run")

    def test_decoy_hits_lift_nothing_and_cost_no_compare(self):
        # Each decoy is reachable (ahead), so only the revert-line filter stops it. The own-commit decoy is also caught by
        # live_revert's seen set, so it shows behaviour only.
        # Named failure: a decoy passes the filter, so it costs a compare, and a reachable decoy lifts the run.
        decoys = {
            "one digit off": hit(C1, revert_msg("a" * 39 + "b")),
            "short sha": hit(C1, f'Revert "work"\n\nThis reverts commit {H[:7]}.\n'),
            "the run's own commit": hit(H, revert_msg(H)),
            "no revert line": hit(C1, f"Retry the flake seen on {H}\n"),
        }
        self.gh.compare[C1] = compare_reply("ahead")
        for name, decoy in decoys.items():
            with self.subTest(decoy=name):
                self.gh.calls.clear()
                self.gh.search[H] = search_reply(decoy)
                got = self.live()
                self.assertEqual(self.gh.searched(), [H], "the run's head was not searched once")
                self.assertEqual(self.gh.compared(), [], "a decoy cost a compare read")
                self.assertIsNone(got, "a decoy lifted the run")
        with self.subTest(decoy="all four in one page"):
            self.gh.calls.clear()
            self.gh.search[H] = search_reply(*decoys.values())
            got = self.live()
            self.assertEqual(len(self.gh.calls), 1, "a page of decoys cost more than one search")
            self.assertEqual(self.gh.compared(), [], "a page of decoys cost a compare read")
            self.assertIsNone(got, "a page of decoys lifted the run")

    def test_no_hit_costs_one_search_and_no_compare(self):
        # Named failure: a run with no revert costs more than its one search, or lifts.
        got = self.live()
        self.assertEqual(self.gh.searched(), [H], "the run's head was not searched once")
        self.assertEqual(len(self.gh.calls), 1, "a run with no revert cost more than one read")
        self.assertIsNone(got, "a run with no revert was lifted")

    def test_an_even_chain_of_two_reverts_does_not_lift(self):
        # H is reverted by C1, and C1 by C2. All three are on the branch, so the chain is even and H stands.
        # Named failure: C1 is taken as the lift although C2 undoes it, so a reverted revert takes the run as lifted.
        self.gh.search = {H: search_reply(hit(C1, revert_msg(H))), C1: search_reply(hit(C2, revert_msg(C1)))}
        self.gh.compare = {C1: compare_reply("ahead"), C2: compare_reply("ahead")}
        got = self.live()
        self.assertCountEqual(self.gh.compared(), [C1, C2], "the chain of two reverts was not walked to its end")
        self.assertIsNone(got, "a chain of two reverts lifted the run")

    def test_an_odd_chain_of_three_reverts_lifts(self):
        # H is reverted by C1, C1 by C2, and C2 by C3. All on the branch, so the chain is odd and H is undone.
        # Named failure: the odd chain does not lift, so the run stays red.
        self.gh.search = {H: search_reply(hit(C1, revert_msg(H))),
                          C1: search_reply(hit(C2, revert_msg(C1))),
                          C2: search_reply(hit(C3, revert_msg(C2)))}
        self.gh.compare = {C1: compare_reply("ahead"), C2: compare_reply("ahead"), C3: compare_reply("ahead")}
        got = self.live()
        self.assertCountEqual(self.gh.compared(), [C1, C2, C3], "the chain of three reverts was not walked to its end")
        self.assertEqual(got, C1, "a chain of three reverts did not lift the run")

    def test_a_revert_of_a_revert_off_the_branch_leaves_the_lift(self):
        # H is reverted by C1, on the branch. C1 is reverted by C2, which is not on the branch, so C1 stands as the lift.
        # Named failure: the off-branch revert counts, so C1 reads as undone and the run stays red.
        self.gh.search = {H: search_reply(hit(C1, revert_msg(H))), C1: search_reply(hit(C2, revert_msg(C1)))}
        self.gh.compare = {C1: compare_reply("ahead"), C2: compare_reply("behind")}
        got = self.live()
        self.assertCountEqual(self.gh.compared(), [C1, C2], "the off-branch revert of the revert was not compared")
        self.assertEqual(got, C1, "a revert of a revert off the branch took away the lift")

    def test_a_failed_compare_raises_unread(self):
        # Named failure: a compare that fails is read as not reachable, so the run is judged, not unknown.
        for name, reply in {"reply with no status": {}, "failed read": revert_rule.Unread("gh api failed")}.items():
            with self.subTest(reply=name):
                self.gh.calls.clear()
                self.gh.search[H] = search_reply(hit(C1, revert_msg(H)))
                self.gh.compare[C1] = reply
                with self.assertRaises(revert_rule.Unread):
                    self.live()

    def test_a_cut_off_search_page_raises_unread(self):
        # Named failure: a page that cuts hits off is read as the whole list, so a revert past the cut is missed or a hit is judged.
        full_page = [hit(f"{i:040x}", revert_msg(H)) for i in range(100)]
        cases = {"total above items, full page": search_reply(*full_page, total=150),
                 "incomplete results": search_reply(hit(C1, revert_msg(H)), incomplete=True)}
        for name, reply in cases.items():
            with self.subTest(page=name):
                self.gh.calls.clear()
                self.gh.search[H] = reply
                with self.assertRaises(revert_rule.Unread):
                    self.live()
                self.assertEqual(self.gh.compared(), [], "a cut-off page was compared before it was refused")

    def test_a_full_page_of_hits_lifts_on_its_one_reachable_revert(self):
        # One hundred hits: 99 decoys, then the real revert. Named failure: the page is cut at 99, or the decoys cost compares.
        decoys = [hit(f"{i:040x}", f"Retry of {H}") for i in range(99)]
        self.gh.search[H] = search_reply(*decoys, hit(C1, revert_msg(H)))
        self.gh.compare[C1] = compare_reply("ahead")
        got = self.live()
        self.assertEqual(self.gh.compared(), [C1], "a full page cost a compare for a decoy, or dropped the real revert")
        self.assertEqual(got, C1, "the reachable revert at the end of a full page did not lift the run")

    def test_a_twice_reverted_commit_gives_one_exit_in_both_search_orders(self):
        # H is reverted by R1, and R1 is reverted twice, by OLDER and by NEWER, both on the branch. R3 reverts one of those two.
        # The expected exit is merge.py's rule (merge/merge.py read_lanes and Host.base_state, both through revert_rule.revert_map):
        # the recs come in git log order, newest first, and revert_map keeps the last line it reads for each commit, so the OLDEST
        # reverter of R1 wins. H is lifted when R1 is not net-reverted by that chain (exit 0), and stands otherwise (exit 1).
        # Two cases, so a fix that sorts by sha, takes the newest reverter, or takes the first search answer fails one of them.
        # Named failure: the exit depends on which reverter search answers first.
        R1, R3, LOW, HIGH = C1, "e" * 40, C2, C3  # LOW has the lower sha and HIGH the higher, so sha order and date order disagree
        OLD, NEW, LATEST = "2026-01-03T00:00:00Z", "2026-01-04T00:00:00Z", "2026-01-05T00:00:00Z"
        cases = {  # name: (the older reverter, the newer one, the reverter R3 reverts, the exit merge.py gives)
            "R3 reverts the newer reverter": (LOW, HIGH, HIGH, 1),
            "R3 reverts the older reverter": (HIGH, LOW, HIGH, 0),
        }
        for name, (older, newer, reverted, want) in cases.items():
            dates = {older: OLD, newer: NEW}
            # recs as git log lists them, newest first: R3, the newer reverter, the older reverter, R1, H
            recs = [(R3, [reverted], revert_msg(reverted)), (newer, [R1], revert_msg(R1)), (older, [R1], revert_msg(R1)),
                    (R1, [H], revert_msg(H)), (H, [], "work\n")]
            undone = revert_rule.revert_map(recs)
            lifted = not revert_rule.net_reverted(undone, R1)  # H is lifted by R1 when R1 is not net-reverted
            # Scope first: merge.py's rule, on this history, gives the exit the case names.
            self.assertEqual(undone[R1], older, f"{name}: revert_map does not keep the older reverter of R1")
            self.assertEqual(lifted, want == 0, f"{name}: merge.py's rule gives exit {0 if lifted else 1}, the case says {want}")
            for order, answers in {"newer first": (newer, older), "older first": (older, newer)}.items():
                with self.subTest(case=name, search=order):
                    self.gh.search = {
                        H: search_reply(hit(R1, revert_msg(H), "2026-01-02T00:00:00Z")),
                        R1: search_reply(*(hit(c, revert_msg(R1), dates[c]) for c in answers)),
                        reverted: search_reply(hit(R3, revert_msg(reverted), LATEST)),
                    }
                    self.gh.compare = {c: compare_reply("ahead") for c in (R1, LOW, HIGH, R3)}
                    got = self.exit_code()
                    self.assertEqual(got, want, f"search answering {order} gave exit {got}, merge.py's rule gives {want}")

    def test_two_reachable_reverters_of_a_revert_on_one_date_exit_2(self):
        # H is reverted by C1, and C1 by S1 and S2, both on the branch with one commit date. Which is the oldest cannot be told,
        # so the run is unknown: exit 2, from the tie, in both search orders.
        # Named failure: the tie is read as a pick, so the exit is 1 (the first reverter undoes C1), not 2 (unknown).
        S1, S2, same = C2, C3, "2026-01-03T00:00:00Z"
        for name, answers in {"S1 first": (S1, S2), "S2 first": (S2, S1)}.items():
            with self.subTest(search=name):
                self.gh.calls.clear()
                self.gh.search = {H: search_reply(hit(C1, revert_msg(H), "2026-01-02T00:00:00Z")),
                                  C1: search_reply(*(hit(s, revert_msg(C1), same) for s in answers))}
                self.gh.compare = {C1: compare_reply("ahead"), S1: compare_reply("ahead"), S2: compare_reply("ahead")}
                got, err = self.main_err()
                self.assertEqual(got, 2, f"two reachable reverters of C1 on one date exited {got}, not 2 (unknown)")
                self.assertEqual(self.gh.searched(), [H, C1], "the chain was not walked to the reverters of C1")
                self.assertIn("share one commit date", err, "exit 2 came from another read, not from the tie on one date")

    def test_two_reverters_one_with_no_usable_date_exit_2(self):
        # H is reverted by C1, and C1 by X, with a commit date, and Y, whose date is missing, unparseable or naive. Both are on the branch.
        # Y cannot be ordered against X, so the run is unknown: exit 2, from the date guard, in both search orders.
        # Named failure: the pair is sorted anyway, so the unknown comes from the sort's TypeError, not from the guard.
        X, Y = C2, C3
        kinds = {"missing": None, "unparseable": "not-a-date", "naive": "2026-01-03T00:00:00"}
        for kind, bad in kinds.items():
            dates = {X: "2026-01-03T00:00:00Z", Y: bad}
            for name, answers in {"X first": (X, Y), "Y first": (Y, X)}.items():
                with self.subTest(date=kind, search=name):
                    self.gh.calls.clear()
                    self.gh.search = {H: search_reply(hit(C1, revert_msg(H), "2026-01-02T00:00:00Z")),
                                      C1: search_reply(*(hit(c, revert_msg(C1), dates[c]) for c in answers))}
                    self.gh.compare = {C1: compare_reply("ahead"), X: compare_reply("ahead"), Y: compare_reply("ahead")}
                    got, err = self.main_err()
                    self.assertEqual(self.gh.searched(), [H, C1], "the chain was not walked to the reverters of C1")
                    self.assertEqual(got, 2, f"a reverter of C1 with a {kind} date exited {got}, not 2 (unknown)")
                    self.assertIn("no usable commit date", err, "exit 2 came from the sort, not from the date guard")

    def test_a_tie_with_one_reverter_off_the_branch_exits_1(self):
        # H is reverted by C1, and C1 by S1 and S2, one commit date. S1 is on the branch and S2 is not, in both search orders.
        # Only S1 is reachable, so there is no tie on the branch: S1 undoes C1, H stands, and the exit is 1, not unknown.
        # Green control. Named failure: the off-branch reverter counts in the tie, so the exit is 2.
        S1, S2, same = C2, C3, "2026-01-03T00:00:00Z"
        for name, answers in {"S1 first": (S1, S2), "S2 first": (S2, S1)}.items():
            with self.subTest(search=name):
                self.gh.calls.clear()
                self.gh.search = {H: search_reply(hit(C1, revert_msg(H), "2026-01-02T00:00:00Z")),
                                  C1: search_reply(*(hit(s, revert_msg(C1), same) for s in answers))}
                self.gh.compare = {C1: compare_reply("ahead"), S1: compare_reply("ahead"), S2: compare_reply("behind")}
                got = self.exit_code()
                self.assertEqual(self.gh.searched(), [H, C1, S1], "the chain was not walked through the on-branch reverter of C1")
                self.assertEqual(got, 1, f"a tie with one reverter off the branch exited {got}, not 1 (H stands)")

    def test_a_single_reverter_with_no_date_is_read_not_unknown(self):
        # One reverter needs no commit date, since nothing is ordered. Case 1: a reverter of H with no date, on the branch, lifts
        # the run (exit 0). Case 2: a reverter of C1 with no date, on the branch, undoes C1, so H stands (exit 1). Neither is unknown.
        # Green control. Named failure: a single hit with no date reads unknown (exit 2).
        self.gh.calls.clear()
        self.gh.search = {H: search_reply(hit(C1, revert_msg(H)))}
        self.gh.compare = {C1: compare_reply("ahead")}
        got = self.exit_code()
        self.assertEqual(self.gh.searched(), [H, C1], "the chain was not walked to the reverters of the one reverter of H")
        self.assertEqual(got, 0, f"a single reverter of H with no date exited {got}, not 0 (lifted)")
        self.gh.calls.clear()
        self.gh.search = {H: search_reply(hit(C1, revert_msg(H), "2026-01-02T00:00:00Z")), C1: search_reply(hit(C2, revert_msg(C1)))}
        self.gh.compare = {C1: compare_reply("ahead"), C2: compare_reply("ahead")}
        got = self.exit_code()
        self.assertEqual(self.gh.searched(), [H, C1, C2], "the chain was not walked through the one reverter of C1")
        self.assertEqual(got, 1, f"a single reverter of C1 with no date exited {got}, not 1 (H stands)")


class MainExitCodes(RuleCase):
    def test_exit_0_when_a_live_revert_lifts_the_run(self):
        # Named failure: a lifting revert returns some code other than 0.
        self.gh.search[H] = search_reply(hit(C1, revert_msg(H)))
        self.gh.compare[C1] = compare_reply("ahead")
        self.assertEqual(self.main(), 0, "a live revert did not exit 0")

    def test_exit_1_when_no_live_revert_lifts_the_run(self):
        # No revert at all, and a revert off the branch. Named failure: the run is lifted, or the exit is not 1.
        self.assertEqual(self.main(), 1, "a run with no revert did not exit 1")
        self.gh.calls.clear()
        self.gh.search[H] = search_reply(hit(C1, revert_msg(H)))
        self.gh.compare[C1] = compare_reply("behind")
        self.assertEqual(self.main(), 1, "a revert off the branch did not exit 1")

    def test_exit_2_when_the_read_is_unknown(self):
        # Named failure: a cut-off page exits 0 or 1, so a failed read reads as clear or as not lifted.
        self.gh.search[H] = search_reply(hit(C1, revert_msg(H)), total=150)
        self.assertEqual(self.main(), 2, "a failed read did not exit 2")

    def test_a_head_that_is_not_40_hex_exits_1_with_no_read(self):
        # Named failure: a head that is not a whole sha is read, so the API is asked about it.
        for head in ("a" * 7, "a" * 41, "z" * 40):
            with self.subTest(head=head):
                self.gh.calls.clear()
                self.assertEqual(self.main(head), 1, "a head that is not 40 hex did not exit 1")
                self.assertEqual(self.gh.calls, [], "a head that is not 40 hex was read")


class FailedReadIsUnknown(RuleCase):
    """A read the rule cannot judge exits 2, unknown. An exception that escapes main exits 1, which alarm.sh reads as no revert."""

    def test_a_hit_whose_commit_is_a_string_exits_2(self):
        # A full page of 100 with the malformed hit last, so the whole list is read before the verdict.
        # Named failure: the hit's commit is a string, so AttributeError escapes main and the process exits 1, read as no revert.
        page = [hit(f"{i:040x}", f"Retry of {H}") for i in range(99)]
        page.append({"sha": C1, "commit": "Revert of the head"})
        self.gh.search[H] = search_reply(*page)
        got = self.exit_code()
        self.assertEqual(self.gh.searched(), [H], "the run's head was not searched once")
        self.assertEqual(got, 2, f"a hit whose commit is a string exited {got}, not 2 (unknown)")


class KnownUnknownShapes(RuleCase):
    """Green controls: these replies already exit 2 on the old code, through the Unread checks in revert_hits. They must stay 2."""

    def test_a_reply_with_no_commit_or_no_list_or_no_string_sha_exits_2(self):
        shapes = {
            "a hit with no commit": search_reply({"sha": C1}),
            "items that are not a list": {"total_count": 1, "incomplete_results": False, "items": "none"},
            "a hit whose sha is not a string": search_reply({"sha": 7, "commit": {"message": revert_msg(H)}}),
        }
        for name, reply in shapes.items():
            with self.subTest(shape=name):
                self.gh.calls.clear()
                self.gh.search[H] = reply
                got = self.exit_code()
                self.assertEqual(self.gh.searched(), [H], "the run's head was not searched once")
                self.assertEqual(got, 2, f"{name} exited {got}, not 2 (unknown)")


class NotUtf8IsUnknown(unittest.TestCase):
    """gh's reply is read as text, so bytes that are not UTF-8 make subprocess.run raise UnicodeDecodeError inside gh_json. That read is unknown."""

    def test_a_reply_that_is_not_utf8_exits_2(self):
        # The subprocess call is replaced by one that raises as text=True decoding does, so no case runs gh or writes a file.
        # Named failure: the decode error escapes main, so the process exits 1, read as no revert.
        run = mock.Mock(side_effect=UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte"))
        with mock.patch.object(revert_rule.subprocess, "run", run), contextlib.redirect_stderr(io.StringIO()):
            try:
                got = revert_rule.main(["--repo", REPO, "--branch", BRANCH, "--head", H])
            except Exception as e:
                self.fail(f"main raised {type(e).__name__} ({e}) instead of an exit code: the process exits 1, which alarm.sh reads as no revert")
        self.assertEqual(run.call_count, 1, "the search was not read")
        self.assertEqual(got, 2, f"a reply that is not UTF-8 exited {got}, not 2 (unknown)")


if __name__ == "__main__":
    unittest.main()
