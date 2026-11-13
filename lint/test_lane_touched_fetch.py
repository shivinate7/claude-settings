#!/usr/bin/env python3
"""Pins for the lane-touched-tests fetch (R62, step ci-linux-windows-once).

touched-tests.py reads one diff: BASE_SHA...HEAD. A lane checkout therefore fetches a small depth, not the full history.
Every checkout in the lane workflow must fetch a depth from 1 to MAX_DEPTH. A depth of 0 is the full history, and it is
refused here so the lane checkout stays shallow.

The reach-the-merge-base step builds the credential as a base64 header. GitHub masks the token itself, not its base64
form, so the step must mask that form with ::add-mask:: before the fetch argv uses it. LANE_YML names another copy of the
workflow for a green control; it defaults to the workflow in this repo.

    python3 lint/test_lane_touched_fetch.py
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANE = os.environ.get("LANE_YML") or os.path.join(ROOT, ".github", "workflows", "lane-touched-tests.yml")
MAX_DEPTH = 50  # the largest fetch-depth that still counts as shallow; a checkout fetching more than this fails the depth case
MASK = "::add-mask::"
MASKED_VARIABLE = re.compile(r"::add-mask::\$\{?\w")
USE_IN_ARGV = re.compile(r"extraheader=\$\{?auth")  # the fetch argv carries the credential as the git header


def live_lines(text):
    """The workflow's lines without comment-only lines, so a comment that names the mask does not count as the mask."""
    return [line for line in text.splitlines() if not line.lstrip().startswith("#")]


def mask_problem(text):
    """None when the credential is masked before the fetch argv uses it, else the one cause."""
    lines = live_lines(text)
    use = next((i for i, line in enumerate(lines) if USE_IN_ARGV.search(line)), None)
    if use is None:
        return "the lane workflow has no fetch argv that carries the credential header"
    mask = next((i for i, line in enumerate(lines) if MASK in line), None)
    if mask is None:
        return "the base64 credential is not masked: no ::add-mask:: line, so a log can print it"
    if mask > use:
        return "the base64 credential is masked after the fetch argv already uses it"
    if not MASKED_VARIABLE.search(lines[mask]):
        return "the ::add-mask:: line does not mask a shell variable that holds the credential"
    return None


GOOD = ('      - name: Reach the merge base\n'
        '        run: |\n'
        '          auth="AUTHORIZATION: basic $(printf \'x-access-token:%s\' "$GH_TOKEN" | base64 -w0)"\n'
        '          echo "::add-mask::$auth"\n'
        '          fetch() { git -c "http.https://github.com/.extraheader=$auth" fetch "$@"; }\n')


class LaneCheckoutDepth(unittest.TestCase):
    def test_every_checkout_in_the_lane_workflow_fetches_a_small_depth(self):
        with open(LANE, encoding="utf-8") as f:
            text = f.read()
        depths = re.findall(r"^\s*fetch-depth:\s*(\S+)\s*$", text, re.M)
        self.assertTrue(depths, "the lane workflow has no fetch-depth, so each checkout fetches the full history")
        for depth in depths:
            self.assertTrue(depth.isdigit() and 1 <= int(depth) <= MAX_DEPTH,
                            f"a lane checkout fetches depth {depth}, want 1 to {MAX_DEPTH}")


class LaneTokenMask(unittest.TestCase):
    def test_the_base64_credential_is_masked_before_the_fetch_argv_uses_it(self):
        self.assertTrue(os.path.isfile(LANE), f"the lane workflow is missing at {LANE}")
        with open(LANE, encoding="utf-8") as f:
            problem = mask_problem(f.read())
        self.assertIsNone(problem, problem)

    def test_a_mask_that_only_a_comment_names_does_not_count(self):
        text = GOOD.replace('          echo "::add-mask::$auth"\n', '          # ::add-mask::$auth is the plan\n')
        self.assertEqual(mask_problem(text), "the base64 credential is not masked: no ::add-mask:: line, so a log can print it")

    def test_a_mask_after_the_argv_use_is_a_problem(self):
        lines = GOOD.splitlines(keepends=True)
        mask = '          echo "::add-mask::$auth"\n'
        late = [line for line in lines if line != mask] + [mask]
        self.assertEqual(mask_problem("".join(late)),
                         "the base64 credential is masked after the fetch argv already uses it")

    def test_a_mask_before_the_argv_use_passes(self):
        self.assertIsNone(mask_problem(GOOD))


if __name__ == "__main__":
    unittest.main()
