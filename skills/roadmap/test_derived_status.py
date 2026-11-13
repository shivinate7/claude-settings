"""Fixture suite for the derived step status in the roadmap build. Run: python3 skills/roadmap/test_derived_status.py

A step's derived status, read at build time: done when a merged proof names it (a Step trailer on main, or a
landedPulls row), else doing when an open pull's branch is in lane_head_refs(step), else the hand status. Session
tags are no source. Where the hand status differs from the derived one, the build prints
`status drift: <id> (hand <x>, derived <y>)` and lists the step in a `status drift` upkeep row. Drift never
changes the exit code.

The fixtures come from test_build.py (its UpkeepFixture), so this file adds no fixture of its own.
"""
import pathlib
import re
import sys
import unittest

sys.dont_write_bytecode = True
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import test_build  # noqa: E402  the one home of the upkeep fixture (make_repo, UpkeepFixture)

DRIFT_ROW = "status drift"
DRIFT_PRINTED = re.compile(r"^status drift: (\S+) \(hand (\w+), derived (\w+)\)$", re.M)
DRIFT_ENTRY = re.compile(r"([^,()\s]+) \(hand (\w+), derived (\w+)\)")


def setUpModule():
    # Fixture.setUp takes its folder from test_build.RUN_FOLDER, which only test_build's own module hooks set.
    test_build.setUpModule()


def tearDownModule():
    test_build.tearDownModule()


class DriftFixture(test_build.UpkeepFixture):
    """Readers of the drift output: the printed lines and the status drift row, as sorted (id, hand, derived)."""

    def open_pull(self, number, branch, title=None):
        """An open pull row, not a draft, on `branch`. The title defaults to the branch name."""
        return {"number": number, "title": title or "lane " + branch, "branch": branch, "draft": False}

    def trailer_steps_on_main(self):
        """The step ids named by a Step: trailer on main, one per trailer."""
        return test_build.git(self.repo, "log", "main", "--format=%(trailers:key=Step,valueonly)").split()

    def printed(self, out):
        return sorted(DRIFT_PRINTED.findall(out))

    def row_entries(self, out):
        """The status drift row's entries. Fails when the row is absent; the row's count must match its entries."""
        count, detail = self.row(out, DRIFT_ROW)
        entries = sorted(DRIFT_ENTRY.findall(detail))
        self.assertEqual(count, len(entries), "the status drift count must equal its entries: %r" % detail)
        return entries

    def assert_drift(self, out, expected, why):
        """The printed lines and the status drift row each list exactly `expected`, (id, hand, derived) tuples."""
        expected = sorted(expected)
        self.assertEqual(self.printed(out), expected, "printed status drift lines: " + why)
        self.assertEqual(self.row_entries(out), expected, "status drift row entries: " + why)


class DerivedStatus(DriftFixture):

    def test_landed_row_with_no_trailer_derives_done(self):
        # This step landed with no Step trailer, so only the landedPulls row proves it.
        self.commit_step("mcp-merge-unguarded", status="ready", order=2)
        self.no_trailer_on_main()
        self.publish(sessions=[], items=[], landed=[self.pull_row(41, "lane/mcp-merge-unguarded", merged=True)])
        out = self.out_with_live(expect=(0,))  # exits 0 today
        self.assert_drift(out, [("mcp-merge-unguarded", "ready", "done")],
                          "a merged landedPulls row derives done with no Step trailer")

    def test_landed_row_whose_head_is_on_main_derives_done(self):
        self.commit_step("c2", status="doing", order=2)
        behind = self.behind_main()  # leaves HEAD on main
        self.assertTrue(self.is_ancestor(behind, "main"), "scope: the row's head must be an ancestor of main")
        self.no_trailer_on_main()
        self.publish(sessions=[], items=[], landed=[self.pull_row(42, "lane/c2", head=behind)])
        out = self.out_with_live(expect=(1,))
        self.assert_drift(out, [("c2", "doing", "done")],
                          "a landedPulls row whose head is on main derives done, as pull_landed_marks reads it")

    def test_trailer_on_main_derives_done_for_an_open_step(self):
        self.land("c2", 7, status="doing", order=2)
        self.assertIn("c2", self.trailer_steps_on_main(), "scope: main must carry the Step trailer for c2")
        self.publish(sessions=[], items=[])
        out = self.out_with_live(expect=(1,))
        self.assert_drift(out, [("c2", "doing", "done")], "a Step trailer on main derives done for a doing step")

    def test_open_lane_pull_derives_doing_and_drift_keeps_the_exit_code(self):
        self.commit_step("roadmap-push-refusal-says-fetch", status="done", order=2)
        self.no_trailer_on_main()
        self.publish(sessions=[], items=[],
                     pulls=[self.open_pull(44, "lane/roadmap-push-refusal-says-fetch")])
        out = self.out_with_live(expect=(0,))  # exit 0 is the pin: a drift line must not change the exit code
        self.assert_drift(out, [("roadmap-push-refusal-says-fetch", "done", "doing")],
                          "an open pull on lane/<id> derives doing for a done step")

    def test_open_pull_on_the_bare_step_id_derives_doing(self):
        self.commit_step("c3", status="todo", order=3)
        self.no_trailer_on_main()
        self.publish(sessions=[], items=[], pulls=[self.open_pull(45, "c3")])
        out = self.out_with_live(expect=(1,))  # the todo step's open pull prints its pair line, which exits 1 today
        self.assert_drift(out, [("c3", "todo", "doing")], "an open pull on the bare step id derives doing")

    def test_merged_beats_open(self):
        self.land("c5", 31, status="doing", order=5)  # hand doing, merged; lane/c5 is open too
        self.land("c6", 32, status="done", order=6)  # hand done, merged; lane/c6 is open too
        self.assertEqual(sorted(self.trailer_steps_on_main()), ["c5", "c6"],
                         "scope: both steps carry a Step trailer on main")
        self.publish(sessions=[], items=[], pulls=[self.open_pull(51, "lane/c5"), self.open_pull(52, "lane/c6")])
        out = self.out_with_live(expect=(0,))  # exits 0 today
        self.assert_drift(out, [("c5", "doing", "done")],
                          "a merged proof beats an open pull: c5 derives done, and done c6 agrees")

    def test_agreeing_steps_are_not_flagged(self):
        # Set up the roadmap-branch steps before any land(), which leaves HEAD on main.
        self.commit_step("a2", status="doing", order=3)  # hand doing, open lane pull: agrees
        self.commit_step("a5", status="done", order=4)  # hand done, a pull whose title names it on another branch
        self.land("a1", 21, status="done", order=2)  # hand done, merged: agrees
        self.land("p1", 23, status="doing", order=5)  # control: hand doing, merged: flagged
        self.publish(sessions=[], items=[],
                     pulls=[self.open_pull(53, "lane/a2"), self.open_pull(54, "feature/a5", title="a5 follow-up")])
        out = self.out_with_live(expect=(1,))
        self.assert_drift(out, [("p1", "doing", "done")],
                          "c1 (todo, nothing), a1 (done, merged), a2 (doing, open pull) and a5 (done, title only) agree")

    def test_session_tags_are_not_a_source(self):
        self.commit_step("c7", status="todo", order=7)  # its cs-step session must not derive doing
        self.land("p2", 61, status="doing", order=8)  # control: hand doing, merged: flagged
        session = test_build.session_row("session_derive01", "SESSION_STATUS_RUNNING", self.REPO,
                                         "cs-step:c7", "cs-build:lane", status_bucket=test_build.BUCKET_WORKING)
        self.publish(sessions=[session], items=[])
        out = self.out_with_live(expect=(1,))
        self.assert_drift(out, [("p2", "doing", "done")], "a live cs-step session on c7 derives nothing for c7")

    def test_no_live_file_or_no_pulls_list_flags_no_pull_drift(self):
        self.commit_step("c8", status="doing", order=8)  # hand doing, nothing proves it: must not flag
        self.commit_step("c9", status="ready", order=9)  # hand ready, nothing proves it: must not flag
        self.land("p3", 71, status="doing", order=10)  # control: a Step trailer still derives done with no pulls
        # With the live read unknown, the landed step's stall reads unknown too, so the build exits 0 today.
        with self.subTest(live="no --live file"):
            _, out = self.build_from_main(expect=(0,))
            self.assert_drift(out, [("p3", "doing", "done")], "with no --live file, unknown pulls flag nothing")
        with self.subTest(live="live file with no pulls list"):
            self.write_live({"readAt": test_build.iso_ago(5), "sessions": [], "items": []})
            out = self.out_with_live(expect=(0,))
            self.assert_drift(out, [("p3", "doing", "done")], "a live file with no pulls list flags no pull drift")

    def test_no_live_file_and_no_proof_leaves_the_drift_row_empty(self):
        self.commit_step("c8", status="doing", order=8)  # hand doing, nothing proves it
        self.commit_step("c9", status="ready", order=9)  # hand ready, nothing proves it
        _, out = self.build_from_main(expect=(0,))
        self.assertEqual(self.row(out, DRIFT_ROW), (0, ""),
                         "with no --live file and no proof, the status drift row reads no entries")

    def test_no_live_file_and_no_proof_prints_no_drift_line(self):
        # Green on the old code: no drift is derived from pulls, so none is printed. It must stay green.
        self.commit_step("c8", status="doing", order=8)  # hand doing, nothing proves it
        self.commit_step("c9", status="ready", order=9)  # hand ready, nothing proves it
        _, out = self.build_from_main(expect=(0,))
        self.assertEqual(self.printed(out), [], "no drift line is printed with no --live file and no proof")


if __name__ == "__main__":
    unittest.main()
