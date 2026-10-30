"""Fixture suite for splice.py, the waiting-page writer's one splice. Run: python3 skills/waiting-page/test_splice.py

    python3 splice.py --page LIVE.html --block FILE --out OUT.html

It replaces the roadmap block of the live page (the block between `<!-- roadmap:data -->` and
`<!-- /roadmap:data -->`, markers included) with the block file, and keeps every other byte, the
designData block among them. A page with no roadmap block is refused. A marker that sits inside a
<script>, as text of a JS string or template literal, is not a block marker.

    python3 splice.py --page TEMPLATE.html --carry LIVE.html --out OUT.html

The carry mode puts the live page's designData block and roadmap block, byte for byte, into the
template, for a republish of a changed template. A live page with no roadmap marker at all (it
predates the block) gives only its designData block; the template keeps its empty roadmap block. It
refuses, and writes nothing, when the template lacks either block, when either file has an unclosed
or doubled block or a doubled designData slot, or when the live page has no designData slot.

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


def live_page(block=OLD_BLOCK, decoys=True, design=DESIGN, extra=""):
    """A page: the roadmap block (or none) between a lone-quote text and the designData block (or none).
    `extra` is one more line of markup, for a template that changed."""
    return ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\"><title>x: Questions</title></head><body>\n"
            "<p>Don't split here</p>\n" + (extra + "\n" if extra else "") + (DECOY_STRING + "\n" if decoys else "") +
            (block + "\n" if block else "") + (design + "\n" if design else "") +
            (DECOY_TEMPLATE + "\n" if decoys else "") + "</body></html>\n")


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


class Folder(unittest.TestCase):
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


class Splice(Folder):
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


EMPTY_BLOCK = OPEN + "\n" + CLOSE
EMPTY_DESIGN = '<script type="application/json" id="designData">{}</script>'
CHANGED_LINE = "<p>The template changed this line.</p>"
# A JS string that holds a designData slot, ahead of the real one: not a block.
DECOY_SLOT = "<script>\nconst SLOT = '<script type=\"application/json\" id=\"designData\">{\"decoy\": 1}<\\/script>';\n</script>"


class Carry(Folder):
    """--carry LIVE: a republish of a changed template keeps the live page's two data blocks, the
    designData block and the roadmap block, byte for byte (build constraint 6: replace only the
    block you change, keep the other). A live page with no roadmap marker yet keeps the template's
    empty roadmap block."""

    def carry(self, template, live, out="out.html"):
        r = subprocess.run([sys.executable, CMD, "--page", self.write("template.html", template), "--carry",
                            self.write("live.html", live), "--out", self.path(out)], capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def carried(self, template, live):
        code, said = self.carry(template, live)
        self.assertEqual(code, 0, said)
        return self.read("out.html")

    def test_both_live_blocks_land_in_a_changed_template_byte_for_byte(self):
        block = NEW_BLOCK.strip()
        template = live_page(block=EMPTY_BLOCK, design=EMPTY_DESIGN, extra=DECOY_SLOT + "\n" + CHANGED_LINE)
        live = live_page(block=block, design=DESIGN, extra=DECOY_SLOT)
        out = self.carried(template, live)
        self.assertIn(CHANGED_LINE, out, "the template's change is gone")
        self.assertEqual(out.count(DESIGN), 1, "the live designData block is not kept byte for byte")
        self.assertEqual(out.count(block), 1, "the live roadmap block is not kept byte for byte")
        self.assertNotIn(EMPTY_DESIGN, out)
        self.assertNotIn(EMPTY_BLOCK, out)
        # Nothing else of the template changed: the template with the two live blocks swapped in, and no more.
        self.assertEqual(out, live_page(block=block, design=DESIGN, extra=DECOY_SLOT + "\n" + CHANGED_LINE))
        self.assertEqual(self.read("live.html"), live, "the live page changed")

    def test_a_second_carry_gives_the_same_page(self):
        template = live_page(block=EMPTY_BLOCK, design=EMPTY_DESIGN, extra=CHANGED_LINE)
        first = self.carried(template, live_page())
        self.assertEqual(self.carried(template, first), first)

    def refused(self, template, live, word, why):
        """The same command carries a good pair, so a refusal here is the carry's own."""
        code, said = self.carry(live_page(block=EMPTY_BLOCK, design=EMPTY_DESIGN), live_page())
        self.assertEqual(code, 0, "the carry does not run on a good pair: " + said)
        os.remove(self.path("out.html"))
        code, said = self.carry(template, live)
        self.assertNotEqual(code, 0, why + ": the carry wrote a page")
        self.assertRegex(said, "(?i)" + word, why + ": the message does not name the missing block")
        self.assertFalse(os.path.exists(self.path("out.html")), why + ": an output file was left")
        self.assertEqual((self.read("template.html"), self.read("live.html")), (template, live), why + ": an input changed")

    def test_a_live_page_from_before_the_roadmap_block_carries_its_designs_and_keeps_the_templates_empty_block(self):
        # Every live page predates the roadmap block on the first batch (build constraint 6: keep what exists).
        template = live_page(block=EMPTY_BLOCK, design=EMPTY_DESIGN, extra=CHANGED_LINE)
        cases = {"no marker at all": live_page(block=None, decoys=False),
                 "markers only in script text": live_page(block=None, decoys=True)}
        for why, live in cases.items():
            with self.subTest(why):
                out = self.carried(template, live)
                self.assertEqual(out, live_page(block=EMPTY_BLOCK, design=DESIGN, extra=CHANGED_LINE),
                                 "the live designData block, the template's empty roadmap block and nothing else")
                self.assertEqual(self.read("live.html"), live, "the live page changed")

    def test_a_template_missing_a_block_or_a_live_page_with_a_broken_block_is_refused(self):
        good_template = live_page(block=EMPTY_BLOCK, design=EMPTY_DESIGN)
        twice = lambda text: text + "\n" + text
        cases = [
            ("template with no designData slot", live_page(block=EMPTY_BLOCK, design=""), live_page(), "designData"),
            ("template with no roadmap markers", live_page(block=None, design=EMPTY_DESIGN, decoys=False), live_page(), "roadmap"),
            ("template with markers only in script text", live_page(block=None, design=EMPTY_DESIGN), live_page(), "roadmap"),
            ("template with an unclosed roadmap block", live_page(block=OPEN, design=EMPTY_DESIGN, decoys=False), live_page(), "roadmap"),
            ("template with two designData slots", live_page(block=EMPTY_BLOCK, design=twice(EMPTY_DESIGN)), live_page(), "designData"),
            ("template with two roadmap blocks", live_page(block=twice(EMPTY_BLOCK), design=EMPTY_DESIGN), live_page(), "roadmap"),
            ("live page with no designData slot", good_template, live_page(design=""), "designData"),
            ("live page with two designData slots", good_template, live_page(design=twice(DESIGN)), "designData"),
            ("live page with an unclosed roadmap block", good_template, live_page(block=OPEN, decoys=False), "roadmap"),
            ("live page with a closing marker and no opening one", good_template, live_page(block=CLOSE, decoys=False), "roadmap"),
            ("live page with two roadmap blocks", good_template, live_page(block=twice(OLD_BLOCK)), "roadmap"),
        ]
        for why, template, live, word in cases:
            with self.subTest(why):
                self.refused(template, live, word, why)


if __name__ == "__main__":
    unittest.main()
