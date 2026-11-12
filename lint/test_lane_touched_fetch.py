#!/usr/bin/env python3
"""Pins for the lane-touched-tests checkout depth (R62, step ci-linux-windows-once).

touched-tests.py reads one diff: BASE_SHA...HEAD. A lane checkout therefore fetches a small depth, not the full history.
Every checkout in the lane workflow must fetch a depth from 1 to MAX_DEPTH. A depth of 0 is the full history, and it is
refused here so the lane checkout stays shallow.

    python3 lint/test_lane_touched_fetch.py
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANE = os.path.join(ROOT, ".github", "workflows", "lane-touched-tests.yml")
MAX_DEPTH = 50  # the bound the brief asks for ("small"); the builder's depth must sit inside it


class LaneCheckoutDepth(unittest.TestCase):
    def test_every_checkout_in_the_lane_workflow_fetches_a_small_depth(self):
        with open(LANE, encoding="utf-8") as f:
            text = f.read()
        depths = re.findall(r"^\s*fetch-depth:\s*(\S+)\s*$", text, re.M)
        self.assertTrue(depths, "the lane workflow has no fetch-depth, so each checkout fetches the full history")
        for depth in depths:
            self.assertTrue(depth.isdigit() and 1 <= int(depth) <= MAX_DEPTH,
                            f"a lane checkout fetches depth {depth}, want 1 to {MAX_DEPTH}")


if __name__ == "__main__":
    unittest.main()
