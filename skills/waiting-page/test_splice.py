"""Fixture suite for splice.py, the waiting-page writer's one splice. Run: python3 skills/waiting-page/test_splice.py

    python3 splice.py --page LIVE.html --block FILE --out OUT.html

It replaces the roadmap block of the live page (the block between `<!-- roadmap:data -->` and
`<!-- /roadmap:data -->`, markers included) with the block file, and keeps every other byte, the
designData block among them. A page with no roadmap block is refused. A marker that sits inside a
<script>, as text of a JS string or template literal, is not a block marker.

SPLICE_UNDER_TEST names the command to run (default: splice.py beside this file), so the same
cases run red against a checkout that lacks it. Temp files: the run folder of lint/_test_temp.py,
whose sweep lint/test_find_copies.py proves (decision test-temp-standard).
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
import _test_temp  # noqa: E402

CMD = os.environ.get("SPLICE_UNDER_TEST") or os.path.join(HERE, "splice.py")
with open(os.path.join(HERE, "page.html"), encoding="utf-8") as f:
    TEMPLATE = f.read()
RUN_FOLDER = None  # made in setUpModule

OPEN, CLOSE = "<!-- roadmap:data -->", "<!-- /roadmap:data -->"
# designData: "<" is written as <, as the writer does. It holds comment openers in strings, a
# multi-line template literal, a lone quote, a `$1` and backslashes, and the escaped form of a marker.
DESIGN = '<script type="application/json" id="designData">' + json.dumps({
    "mock": "<p>Don't stop /* here // # `line one\nline two` $1 \\1 \\g<0> <!-- roadmap:data -->é</p>",
}).replace("<", "\\u003c") + "</script>"
# Text that looks like a block but is not one: a JS string, and a template literal of several lines.
DECOY_STRING = '<script>\nconst OPEN = "<!-- roadmap:data -->"; // a string, not a marker\nconst Q = \'/* not a comment\';\n</script>'
DECOY_TEMPLATE = "<script>\nconst T = `\n<!-- roadmap:data -->\nnot the block\n<!-- /roadmap:data -->\n`;\n</script>"
OLD_BLOCK = OPEN + '\n<script>window.ROADMAP_DATA = {"old": true}; window.ROADMAP_BUILD = {"old": true};</script>\n' + CLOSE
# A block as build.py --block writes it: data with markup escaped, `\\1` and `\\g<0>` as plain text, a lone quote.
NEW_BLOCK = (OPEN + '\n<script>window.ROADMAP_DATA = {"steps": {"c1": {"note": "a \\u003c!-- b <\\/script> Don\'t \\\\1 \\\\g<0> '
             '`x`\\n// # /* $1"}}}; window.ROADMAP_BUILD = {"repo": "r"};</script>\n' + CLOSE + "\n")
OTHER_BLOCK = OPEN + '\n<script>window.ROADMAP_DATA = null; window.ROADMAP_BUILD = {"repo": "other"};</script>\n' + CLOSE + "\n"


def live_page(block=OLD_BLOCK, decoys=True):
    """A live page: the roadmap block (or none) between a lone-quote text and the designData block."""
    return ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\"><title>x: Questions</title></head><body>\n"
            "<p>Don't split here</p>\n" + (DECOY_STRING + "\n" if decoys else "") +
            (block + "\n" if block else "") + DESIGN + "\n" + (DECOY_TEMPLATE + "\n" if decoys else "") +
            "</body></html>\n")


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


class Splice(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=RUN_FOLDER)
        self.addCleanup(self.tmp.cleanup)

    def path(self, name):
        return os.path.join(self.tmp.name, name)

    def write(self, name, text):
        with open(self.path(name), "w", encoding="utf-8", newline="") as f:
            f.write(text)
        return self.path(name)

    def read(self, name):
        with open(self.path(name), encoding="utf-8", newline="") as f:
            return f.read()

    def splice(self, page, block, out="out.html"):
        r = subprocess.run([sys.executable, CMD, "--page", self.write("live.html", page), "--block",
                            self.write("block.html", block), "--out", self.path(out)], capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def spliced(self, page, block):
        code, said = self.splice(page, block)
        self.assertEqual(code, 0, said)
        return self.read("out.html")

    def test_template_carries_an_empty_roadmap_block_and_a_design_slot(self):
        self.assertTrue(re.search(re.escape(OPEN) + r"\s*" + re.escape(CLOSE), TEMPLATE), "page.html has no empty roadmap block")
        self.assertTrue('id="designData"' in TEMPLATE, "page.html has no designData block")

    def test_replaces_only_the_roadmap_block_and_keeps_every_other_byte(self):
        live = live_page()
        head, tail = live.split(OLD_BLOCK)
        out = self.spliced(live, NEW_BLOCK)
        # White space at the two joins may differ; every byte outside the old block and the new one may not.
        self.assertTrue(out.startswith(head.rstrip()), "the text before the block changed")
        self.assertTrue(out.endswith(tail.lstrip()), "the text after the block changed")
        middle = out[len(head.rstrip()):len(out) - len(tail.lstrip())]
        self.assertEqual(middle.strip(), NEW_BLOCK.strip(), "the block is not the block file's text, byte for byte")
        self.assertNotIn('"old": true', out)

    def test_design_data_stays_byte_for_byte(self):
        out = self.spliced(live_page(), NEW_BLOCK)
        self.assertEqual(out.count(DESIGN), 1)

    def test_markers_inside_a_script_are_not_the_block(self):
        live = live_page()
        out = self.spliced(live, NEW_BLOCK)
        self.assertIn(DECOY_STRING, out, "the splice changed the JS string")
        self.assertIn(DECOY_TEMPLATE, out, "the splice changed the template literal")
        self.assertEqual(out.count("not the block"), 1)

    def test_a_second_splice_replaces_and_never_appends(self):
        first = self.spliced(live_page(), NEW_BLOCK)
        second = self.spliced(first, OTHER_BLOCK)
        self.assertEqual(second, self.spliced(live_page(), OTHER_BLOCK))
        self.assertNotIn("a \\u003c!-- b", second)
        self.assertEqual(second.count('"repo": "other"'), 1)

    def test_a_block_with_a_backslash_or_dollar_arrives_unchanged(self):
        # A replacement string read as a template would turn `\1` or `\g<0>` into text and fail on `<`.
        out = self.spliced(live_page(decoys=False), NEW_BLOCK)
        self.assertIn(NEW_BLOCK.strip(), out)

    def refused(self, page, why):
        """The same command splices a page that has a block, so a refusal here is the splice's own."""
        code, said = self.splice(live_page(), NEW_BLOCK)
        self.assertEqual(code, 0, "the splice does not run on a good page: " + said)
        os.remove(self.path("out.html"))
        code, said = self.splice(page, NEW_BLOCK)
        self.assertNotEqual(code, 0, why + ": the splice wrote a page")
        self.assertRegex(said, r"roadmap", why + ": the message does not name the roadmap block")
        self.assertFalse(os.path.exists(self.path("out.html")), why + ": an output file was left")
        self.assertEqual(self.read("live.html"), page, why + ": the live page changed")

    def test_page_with_no_markers_is_refused(self):
        self.refused(live_page(block=None, decoys=False), "no markers")

    def test_page_with_only_the_opening_marker_is_refused(self):
        self.refused(live_page(block=OPEN + "\n<script>window.ROADMAP_DATA = null;</script>", decoys=False), "no closing marker")

    def test_page_whose_only_markers_sit_inside_scripts_is_refused(self):
        self.refused(live_page(block=None, decoys=True), "markers only in script text")


if __name__ == "__main__":
    unittest.main()
