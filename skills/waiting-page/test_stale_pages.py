"""Fixture suite for stale_pages.py. Run: python3 skills/waiting-page/test_stale_pages.py

STALE_PAGES_UNDER_TEST names the command to run (default: stale_pages.py beside this file), so the
same cases run red against a checkout that lacks it.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)

CMD = os.environ.get("STALE_PAGES_UNDER_TEST") or os.path.join(HERE, "stale_pages.py")
SPLICE = os.environ.get("SPLICE_UNDER_TEST") or os.path.join(HERE, "splice.py")  # the same seam as test_splice.py
DESIGN_BLOCK = re.compile(r'<script type="application/json" id="designData">.*?</script>', re.S)
with open(os.path.join(HERE, "page.html"), encoding="utf-8") as f:
    PAGE = f.read()
URL = "https://claude.ai/artifact/%s"
RUN_FOLDER = None  # made in setUpModule

OPEN, CLOSE = "<!-- roadmap:data -->", "<!-- /roadmap:data -->"
DESIGN_BODY = '{"a": "\\u003cp>mockup\\u003c/p>"}'
# A roadmap block as build.py --block writes it: markup escaped, a lone quote, the escaped form of the closing marker.
ROADMAP_BODY = ('\n<script>window.ROADMAP_DATA = {"steps": {"c1": {"note": "a \\u003c!-- b <\\/script> Don\'t '
                '\\u003c!-- /roadmap:data -->"}}}; window.ROADMAP_BUILD = {"repo": "r"};</script>\n')
BLOCK = re.compile(re.escape(OPEN) + r".*?" + re.escape(CLOSE), re.S)


def with_both_blocks(page):
    """`page` with its designData and its roadmap block filled, as a live page holds them."""
    page = page.replace('id="designData">', 'id="designData">' + DESIGN_BODY, 1)
    return BLOCK.sub(lambda m: OPEN + ROADMAP_BODY + CLOSE, page, count=1)


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


class Stale(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=RUN_FOLDER)
        self.addCleanup(self.tmp.cleanup)
        self.fetched = os.path.join(self.tmp.name, "fetched")
        os.mkdir(self.fetched)

    def repo(self, name, page_id):
        root = os.path.join(self.tmp.name, name)
        os.makedirs(os.path.join(root, ".claude"))
        with open(os.path.join(root, ".claude", "layout-extras.json"), "w") as f:
            json.dump({"kinds": {}, "waiting-page": URL % page_id}, f)
        return root

    def fetch(self, page_id, text=None, unreadable=False):
        ext = ".unreadable" if unreadable else ".html"
        with open(os.path.join(self.fetched, page_id + ext), "w", encoding="utf-8") as f:
            f.write(text or "")

    def run_cmd(self, *roots):
        r = subprocess.run([sys.executable, CMD, self.fetched, *roots], capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def test_old_and_unreadable_are_named_and_current_passes(self):
        roots = [self.repo("fresh", "AAA"), self.repo("old", "BBB"), self.repo("other-account", "CCC")]
        self.fetch("AAA", PAGE)
        self.fetch("BBB", PAGE[: len(PAGE) // 2] + "<p>old template</p>")
        self.fetch("CCC", unreadable=True)
        code, out = self.run_cmd(*roots)
        self.assertEqual(code, 1, out)
        self.assertIn("current: fresh", out)
        self.assertIn("behind: old", out)
        self.assertIn("unknown: other-account", out)
        self.assertIn("1 current, 1 behind, 1 unknown", out)

    def test_page_with_own_mockups_is_current(self):
        mock = PAGE.replace('id="designData">', 'id="designData">{"a": "\\u003cp>mockup\\u003c/p>"}', 1)
        self.assertNotEqual(mock, PAGE)
        root = self.repo("mocked", "DDD")
        self.fetch("DDD", mock)
        code, out = self.run_cmd(root)
        self.assertEqual(code, 0, out)
        self.assertIn("current: mocked", out)

    def live_with_both_blocks(self):
        live = with_both_blocks(PAGE)
        self.assertTrue(re.search(re.escape(OPEN) + r"\s*" + re.escape(CLOSE), PAGE), "page.html has no empty roadmap block")
        self.assertIn(ROADMAP_BODY, live, "the roadmap block was not filled")
        return live

    def test_page_differing_only_inside_the_two_blocks_is_current(self):
        root = self.repo("blocks", "GGG")
        self.fetch("GGG", self.live_with_both_blocks())
        code, out = self.run_cmd(root)
        self.assertEqual(code, 0, out)
        self.assertIn("current: blocks", out)

    def test_change_outside_the_blocks_is_behind_even_with_both_blocks_filled(self):
        live = self.live_with_both_blocks()
        changes = {
            "far from them": live.replace("<style>", "<style>/* old */", 1),
            "right after the roadmap block": live.replace(CLOSE, CLOSE + "<p>old template</p>", 1),
        }
        root = self.repo("changed", "HHH")
        for name, text in changes.items():
            self.assertNotEqual(text, live, name)
            with self.subTest(name):
                self.fetch("HHH", text)
                code, out = self.run_cmd(root)
                self.assertEqual(code, 1, out)
                self.assertIn("behind: changed", out)

    def carry_into_template(self, live):
        """page.html with the live page's blocks carried in (splice.py --carry), as the writer republishes it."""
        live_path = os.path.join(self.tmp.name, "live.html")
        carried_path = os.path.join(self.tmp.name, "carried.html")
        with open(live_path, "w", encoding="utf-8", newline="") as f:
            f.write(live)
        r = subprocess.run([sys.executable, SPLICE, "--page", os.path.join(HERE, "page.html"), "--carry", live_path,
                            "--out", carried_path], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(carried_path, encoding="utf-8", newline="") as f:
            return f.read()

    def test_a_carry_of_a_page_from_before_the_roadmap_block_keeps_its_designs_and_reads_current(self):
        # The first batch: every live page predates the roadmap block, and its designs must survive the republish.
        self.live_with_both_blocks()  # the template has the block to keep
        old = BLOCK.sub("", PAGE.replace('id="designData">', 'id="designData">' + DESIGN_BODY, 1), count=1)
        self.assertNotEqual(DESIGN_BLOCK.findall(old), DESIGN_BLOCK.findall(PAGE))
        carried = self.carry_into_template(old)
        self.assertEqual(DESIGN_BLOCK.findall(carried), DESIGN_BLOCK.findall(old), "the carry lost the live designData")
        self.assertTrue(re.search(re.escape(OPEN) + r"\s*" + re.escape(CLOSE), carried), "the template's empty roadmap block is gone")
        self.fetch("JJJ", carried)
        code, out = self.run_cmd(self.repo("before", "JJJ"))
        self.assertEqual(code, 0, out)
        self.assertIn("current: before", out)

    def test_a_carry_reads_current_and_keeps_the_live_designs(self):
        # stale_pages empties designData on both sides, so "current" cannot show a loss of the live mockups.
        # A republish of plain page.html reads current with designData empty; only the carry keeps them.
        live = self.live_with_both_blocks()
        self.assertNotEqual(DESIGN_BLOCK.findall(live), DESIGN_BLOCK.findall(PAGE), "the template holds the live designs")
        carried = self.carry_into_template(live)
        self.assertEqual(DESIGN_BLOCK.findall(carried), DESIGN_BLOCK.findall(live), "the carry lost the live designData")
        self.assertIn(ROADMAP_BODY, carried, "the carry lost the live roadmap block")
        self.fetch("III", carried)
        code, out = self.run_cmd(self.repo("carried", "III"))
        self.assertEqual(code, 0, out)
        self.assertIn("current: carried", out)

    def test_page_with_no_fetched_file_is_unknown_never_current(self):
        code, out = self.run_cmd(self.repo("unfetched", "EEE"))
        self.assertEqual(code, 1, out)
        self.assertIn("unknown: unfetched", out)
        self.assertNotIn("current: unfetched", out)

    def test_empty_file_is_unknown(self):
        root = self.repo("blank", "FFF")
        self.fetch("FFF", "")
        code, out = self.run_cmd(root)
        self.assertEqual(code, 1, out)
        self.assertIn("unknown: blank", out)


if __name__ == "__main__":
    unittest.main()
