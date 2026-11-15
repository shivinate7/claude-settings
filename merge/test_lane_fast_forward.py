#!/usr/bin/env python3
"""Suite for the batch lane cleanup when the pull request's head fast-forwards onto main and brings a lane in (merge/merge.py).

Run: python3 merge/test_lane_fast_forward.py

A lane that fast-forwards onto the base leaves no merge commit, so a reader of the batch's merge commits never sees its tip.
Decision merge-deletes-batch-lanes (a merge deletes only its own pull request's branch) keeps that lane's branch on origin too.
The clones, the host and the lane helper come from merge/test_merge.py: Env, LaneHost and lane_batch are extended here, not copied.
Importing test_merge runs none of its cases.
"""
import os, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_merge as tm  # noqa: E402  the clones, the host and the lane helper; importing it runs none of its cases

def ff_lane(env, name):
    """Lane `name` through lane_batch, then feat set to that tip by a fast-forward only, so the PR head holds no merge commit.
    The merge lane_batch pushed to feat is replaced on origin by a force push, since a fast-forward from main does not keep it. -> the lane's tip."""
    tip = tm.lane_batch(env, name)[name]
    o = env.other
    tm.sh(o, "git", "checkout", "-q", "-B", "feat", "origin/main")
    tm.sh(o, "git", "merge", "-q", "--ff-only", tip)
    env.assertEqual(tm.sh(o, "git", "rev-list", "--merges", "origin/main..feat"), "", "subject: feat must hold no merge commit")
    env.assertEqual(tm.sh(o, "git", "rev-parse", "feat"), tip, "subject: feat must sit at the lane's tip")
    tm.sh(o, "git", "push", "-q", "-f", "origin", "feat")
    return tip

class FastForwardLane(tm.Env):
    """A pull request head that fast-forwards onto main and brings a lane in keeps that lane's branch on origin, and cuts only
    the pull request's own branch. The fast-forwarded lane has no merge commit, so a reader of merge commits never sees its tip. The
    cases fail only on a cut that reads the lane from the merged head's history."""
    def setUp(self):
        super().setUp()
        self.host = tm.LaneHost(self.co, self.other)

    def go(self):
        return self.run_merge("7", "--confirm")

    def test_a_head_that_fast_forwards_a_lane_in_keeps_the_lane_and_cuts_its_own_branch(self):
        tip = ff_lane(self, "lane1")
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.head("feat"), "", f"feat, the pull request's own branch, is still on origin: {out!r}")  # scope first
        self.assertNotEqual(self.head("lane1"), "", f"lane1, the lane the fast-forward brought in, was deleted from origin: {out!r}")
        self.assertEqual(self.head("lane1"), tip, f"lane1, the lane the fast-forward brought in, moved on origin: {out!r}")

    def test_a_fast_forwarded_lane_and_a_no_ff_lane_both_stay_and_the_pr_branch_is_cut(self):
        tip1 = ff_lane(self, "lane1")
        tip2 = tm.lane_batch(self, "lane2")["lane2"]  # lane2 merges into feat with --no-ff, on top of the fast-forwarded lane1
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.head("feat"), "", f"feat, the pull request's own branch, is still on origin: {out!r}")  # scope first
        self.assertNotEqual(self.head("lane1"), "", f"lane1, the fast-forwarded lane, was deleted from origin: {out!r}")
        self.assertEqual(self.head("lane1"), tip1, f"lane1, the fast-forwarded lane, moved on origin: {out!r}")
        self.assertNotEqual(self.head("lane2"), "", f"lane2, the --no-ff lane, was deleted from origin: {out!r}")
        self.assertEqual(self.head("lane2"), tip2, f"lane2, the --no-ff lane, moved on origin: {out!r}")

if __name__ == "__main__":
    unittest.main()
