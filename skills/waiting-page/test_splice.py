"""Fixture suite for splice.py, the page writer's one splice. Run: python3 skills/waiting-page/test_splice.py

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

    python3 splice.py --page LIVE.html --add-design SLUG=FILE [--add-design ...] --out OUT.html

The add-design form adds `"SLUG": "<html>"` to the page's one designData object for each FILE, every `<`
written as a \\u003c escape, and no other byte changed. It runs alone with --page, or with --block or --carry.
It refuses, and writes no page, when the designData block is missing, doubled or not a JSON object, when a FILE
is missing, empty or unreadable, when a SLUG is not [a-z0-9-]+, or when a SLUG exists with other html.

SPLICE_UNDER_TEST names the command to run (default: splice.py beside this file), so the same
cases run red against a checkout that lacks it. Temp files: the run folder of lint/_test_temp.py,
whose sweep lint/test_find_copies.py proves (decision test-temp-standard).
"""
import importlib.util
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
ROADMAP_PAGE = os.path.join(HERE, "..", "roadmap", "page", "index.html")
RUN_FOLDER = None  # made in setUpModule


def load_splice():
    """splice.py as a module, loaded from CMD, so a name a test reads is the one the splice defines."""
    spec = importlib.util.spec_from_file_location("splice_under_test", CMD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SPLICE = load_splice()


def page_name(test):
    """splice.PAGE_NAME. A test asserts the old name is gone before it asks for the new one."""
    name = getattr(SPLICE, "PAGE_NAME", None)
    test.assertIsNotNone(name, "splice.py has no PAGE_NAME")
    return name


def set_title_statement(text):
    """The document.title expression of setTitle() in `text`, up to the line's `;`, or None."""
    body = re.search(r"function setTitle\(\) \{(.*?)\n\}", text, re.S)
    stmt = re.search(r"document\.title\s*=\s*(.*?);[ \t]*(?:\n|\Z)", body.group(1)) if body else None
    return stmt.group(1) if stmt else None


def js_literals(code):
    """The double-quoted string literals of a JS expression, escapes kept as written."""
    return re.findall(r'"((?:[^"\\]|\\.)*)"', code or "")


def design_script(designs):
    """A designData element holding the JSON object `designs`, written as the page writer writes it: every `<` as a \\u003c escape."""
    return '<script type="application/json" id="designData">' + json.dumps(designs).replace("<", "\\u003c") + "</script>"


OPEN, CLOSE = "<!-- roadmap:data -->", "<!-- /roadmap:data -->"
# designData: "<" is written as <, as the writer does. It holds comment openers in strings, a
# multi-line template literal, a lone quote, a `$1` and backslashes, and the escaped form of a marker.
DESIGN = design_script({
    "mock": "<p>Don't stop /* here // # `line one\nline two` $1 \\1 \\g<0> <!-- roadmap:data -->é</p>",
})
# Text that looks like a block but is not one: a JS string, and a template literal of several lines.
DECOY_STRING = '<script>\nconst OPEN = "<!-- roadmap:data -->"; // a string, not a marker\nconst Q = \'/* not a comment\';\n</script>'
DECOY_TEMPLATE = "<script>\nconst T = `\n<!-- roadmap:data -->\nnot the block\n<!-- /roadmap:data -->\n`;\n</script>"
OLD_BLOCK = OPEN + '\n<script>window.ROADMAP_DATA = {"old": true}; window.ROADMAP_BUILD = {"old": true};</script>\n' + CLOSE
# A block as build.py --block writes it: data with markup escaped, `\\1` and `\\g<0>` as plain text, a lone quote.
NEW_BLOCK = (OPEN + '\n<script>window.ROADMAP_DATA = {"steps": {"c1": {"note": "a \\u003c!-- b <\\/script> Don\'t \\\\1 \\\\g<0> '
             '`x`\\n// # /* $1"}}}; window.ROADMAP_BUILD = {"repo": "r"};</script>\n' + CLOSE + "\n")
OTHER_BLOCK = OPEN + '\n<script>window.ROADMAP_DATA = null; window.ROADMAP_BUILD = {"repo": "other"};</script>\n' + CLOSE + "\n"


def live_page(block=OLD_BLOCK, decoys=True, design=DESIGN, extra="", title="x: Questions"):
    """A page: the roadmap block (or none) between a lone-quote text and the designData block (or none).
    `extra` is one more line of markup, for a template that changed. `title` is the page's own <title> text."""
    return ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\"><title>" + title + "</title></head><body>\n"
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


# A live title of an old form becomes PAGE_NAME under its prefix. Each other live title is kept byte for byte.
# The rewrite holds each regex special as text, so these cases pin `$1`, `\1` and `\g<0>` as literal text.
OLD_TITLES = [
    ("Queue", ""), ("Queue · Status", ""), ("Roadmap", ""),
    ("Compass Queue", "Compass "), ("Compass Queue · Status", "Compass "), ("Compass Roadmap", "Compass "),
    ("Roadmap Queue", "Roadmap "), ("Queue Lab Roadmap", "Queue Lab "),
    (r"Don't /* // # $1 \1 Compass Queue", r"Don't /* // # $1 \1 Compass "),
    (r"\g<0> $& \\ Compass Roadmap", r"\g<0> $& \\ Compass "),
]
OTHER_TITLES = ["Compass Cockpit", "Compass Queues", "Requeue", "Compass Queue · Other", "Queue Status", ""]


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

    def title_of(self, page):
        span = SPLICE.title_span(page)
        self.assertIsNotNone(span, "the page has no title")
        return page[span[0]:span[1]]

    def test_the_live_title_is_renamed_and_a_title_in_a_script_does_not_move(self):
        # The old title becomes PAGE_NAME under its prefix. The title holds a
        # lone quote, comment openers, `$1` and `\1`, and the rewrite keeps them. The decoys are <title> strings in a
        # script and a template literal: only the head's title moves.
        live_title = r"Don't /* // # $1 \1 Compass Queue"
        decoys = ("<script>\nconst S = '<title>Queue</title>';\n</script>\n"
                  "<script>\nconst T = `\n<title>Queue</title>\n`;\n</script>")
        template = live_page(block=EMPTY_BLOCK, design=EMPTY_DESIGN, title="Template Title", extra=decoys)
        live = live_page(block=NEW_BLOCK.strip(), design=DESIGN, title=live_title, extra=decoys.replace("Queue", "Live decoy"))
        out = self.carried(template, live)
        self.assertNotEqual(self.title_of(out), live_title, "the carry kept the old title")
        name = page_name(self)
        self.assertEqual(out, live_page(block=NEW_BLOCK.strip(), design=DESIGN, title=r"Don't /* // # $1 \1 Compass " + name, extra=decoys),
                         "the renamed title and blocks, the template's own script text, and nothing else")
        self.assertEqual(self.read("live.html"), live, "the live page changed")

    def test_each_old_title_becomes_the_page_name_under_its_prefix(self):
        for old, prefix in OLD_TITLES:
            with self.subTest(old=old):
                out = self.carried(live_page(block=EMPTY_BLOCK, design=EMPTY_DESIGN),
                                   live_page(block=NEW_BLOCK.strip(), design=DESIGN, title=old))
                self.assertNotEqual(self.title_of(out), old, "the carry kept the old title")
                self.assertEqual(self.title_of(out), prefix + page_name(self), "the old title did not become the page name")

    def test_any_other_live_title_is_kept_byte_for_byte(self):
        for old in OTHER_TITLES:
            with self.subTest(old=old):
                out = self.carried(live_page(block=EMPTY_BLOCK, design=EMPTY_DESIGN),
                                   live_page(block=NEW_BLOCK.strip(), design=DESIGN, title=old))
                self.assertEqual(self.title_of(out), old, "the carry changed a title it must keep")

    def test_a_live_page_with_no_title_keeps_the_templates_title(self):
        template = live_page(block=EMPTY_BLOCK, design=EMPTY_DESIGN, title="Template Title")
        live = live_page(block=NEW_BLOCK.strip(), design=DESIGN).replace("<title>x: Questions</title>", "", 1)
        self.assertIsNone(SPLICE.title_span(live), "the live page still has a title")
        self.assertEqual(self.title_of(self.carried(template, live)), "Template Title")

    def test_a_host_title_ahead_of_the_page_title_is_not_carried(self):
        # The host's skeleton holds its own <title> before the page's. The page's own title is the one that moves.
        host = '<!doctype html>\n<html><head><meta charset="utf-8"><title>Host Title</title></head><body>\n'
        template = live_page(block=EMPTY_BLOCK, design=EMPTY_DESIGN, title="Queue")
        live = host + live_page(block=NEW_BLOCK.strip(), design=DESIGN, title="Compass Board") + "</body></html>\n"
        out = self.carried(template, live)
        self.assertEqual(out, live_page(block=NEW_BLOCK.strip(), design=DESIGN, title="Compass Board"),
                         "the page's title, not the host's, and no host text")
        self.assertEqual(self.read("live.html"), live, "the live page changed")

    def test_a_title_in_an_svg_is_not_the_page_title(self):
        svg = "<svg><title>Icon label</title></svg>"
        template = live_page(block=EMPTY_BLOCK, design=EMPTY_DESIGN, title="Queue", extra=svg)
        live = live_page(block=NEW_BLOCK.strip(), design=DESIGN, title="Compass Board", extra=svg.replace("Icon label", "Live icon"))
        out = self.carried(template, live)
        self.assertEqual(out, live_page(block=NEW_BLOCK.strip(), design=DESIGN, title="Compass Board", extra=svg))

    def test_a_script_string_with_comment_openers_and_a_title_does_not_move_the_title(self):
        # building-scanner-respects-strings: `/*`, `//` and `#` in a string, with a head tag, a body tag and an svg title in it.
        decoy = ("<script>\nconst D = '/* // # <title>Decoy</title> <body class=\"x\"> <svg><title>S</title></svg> */ //';\n"
                 "const E = `\n# <title>Decoy</title> // /*\n`;\n</script>")
        template = live_page(block=EMPTY_BLOCK, design=EMPTY_DESIGN, title="Queue", extra=decoy)
        live = live_page(block=NEW_BLOCK.strip(), design=DESIGN, title="Compass Board", extra=decoy.replace("Decoy", "Live decoy"))
        out = self.carried(template, live)
        self.assertEqual(out, live_page(block=NEW_BLOCK.strip(), design=DESIGN, title="Compass Board", extra=decoy))

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


class PageName(unittest.TestCase):
    """The page's name is splice.PAGE_NAME. page.html's static title and setTitle's literal must say it too."""

    def test_the_static_title_is_the_page_name_and_the_page_name_is_cockpit(self):
        span = SPLICE.title_span(TEMPLATE)
        self.assertIsNotNone(span, "page.html has no document title")
        static = TEMPLATE[span[0]:span[1]]
        self.assertNotEqual(static, "Queue", "page.html's static title is still the old name Queue")
        name = page_name(self)
        self.assertEqual(static, name, "page.html's static title is not PAGE_NAME")
        self.assertEqual(name, "Cockpit", "PAGE_NAME is not the ruled name Cockpit")

    def test_set_title_writes_the_page_name_and_no_status_suffix(self):
        stmt = set_title_statement(TEMPLATE)
        self.assertIsNotNone(stmt, "page.html has no setTitle() document.title statement")
        literals = js_literals(stmt)
        self.assertNotIn("Queue", literals, "setTitle still writes the old name Queue")
        name = page_name(self)
        self.assertIn(name, literals, "setTitle writes no PAGE_NAME literal")
        self.assertEqual([s for s in literals if "Status" in s], [], "setTitle still adds a Status suffix")

    def test_the_roadmap_page_keeps_its_main_title(self):
        # The roadmap page is never published, so its title stays main's. Carry renames a live title, not this file's.
        with open(ROADMAP_PAGE, encoding="utf-8") as f:
            text = f.read()
        span = SPLICE.title_span(text)
        self.assertIsNotNone(span, "the roadmap page has no document title")
        self.assertEqual(text[span[0]:span[1]], "claude-settings Roadmap", "the roadmap page title is not main's")

    def test_the_setTitle_reader_skips_comment_openers_in_strings_and_a_template_literal(self):
        # building-scanner-respects-strings: the reader finds the statement and its literals past `/*`, `//`, `#`,
        # a lone quote in a string, and a multi-line template literal.
        code = ('function setTitle() {\n'
                '  const T = `\n  // not a comment /* # \'\n  `;\n'
                '  document.title = (name ? name + " " : "") + "A /* // # Don\'t $1 Cockpit";\n'
                '}\n')
        self.assertEqual(set_title_statement(code), '(name ? name + " " : "") + "A /* // # Don\'t $1 Cockpit"')
        self.assertIn("A /* // # Don't $1 Cockpit", js_literals(set_title_statement(code)))


MANY_DESIGNS = {"m1": "<p>one</p>", "m2": "<p>two</p>", "m3": "<p>three</p>"}
# A mockup with comment openers, a template literal over two lines, `$1`, `\1`, a lone quote, a letter outside
# ASCII, and the closing tag and the marker that a naive splice would trip on.
MOCK_HTML = "<p>Don't stop /* here // # `line one\nline two` $1 \\1 \\g<0> <!-- roadmap:data -->é</p>\n</script>\n"


class AddDesign(Folder):
    """--add-design SLUG=FILE: the page's one designData object gains "SLUG": "<html>" for each FILE, every `<` as a
    \\u003c escape, and no other byte changes. A refusal names its cause and writes no page. The option is new, so on a
    checkout without it each case fails at its first assert, on the option being unknown."""

    def command(self, *argv, out="out.html", cwd=None):
        r = subprocess.run([sys.executable, CMD, *argv, "--out", self.path(out)], capture_output=True, text=True, cwd=cwd)
        return r.returncode, r.stdout + r.stderr

    @staticmethod
    def adds(*pairs):
        """The --add-design arguments for (slug, file) pairs, in order."""
        return [arg for slug, path in pairs for arg in ("--add-design", "%s=%s" % (slug, path))]

    def added(self, page, *pairs, out="out.html", cwd=None):
        code, said = self.command("--page", self.write("live.html", page), *self.adds(*pairs), out=out, cwd=cwd)
        self.assertEqual(code, 0, "--add-design exited %d, so no page was written: %s" % (code, said))
        return self.read(out)

    def design_span(self, text):
        try:
            return SPLICE.design_span(text, "the page")
        except SystemExit as e:
            self.fail("the page does not hold one designData block: %s" % e)

    def body(self, text):
        start, end = self.design_span(text)
        el = text[start:end]
        return el[el.index(">") + 1:el.rindex("</script>")]

    def designs(self, text):
        try:
            return json.loads(self.body(text))
        except ValueError as e:
            self.fail("the designData body is not valid JSON: %s" % e)

    def outside(self, text):
        """The page's text before and after its designData block."""
        start, end = self.design_span(text)
        return text[:start], text[end:]

    def assert_only_designs_added(self, page, out):
        """Every byte outside designData is the page's own. The body is the page's own text with its closing brace
        moved past the new members, and it holds no raw `<`."""
        self.assertEqual(self.outside(out), self.outside(page), "a byte outside designData changed")
        base = self.body(page).rstrip()
        self.assertTrue(self.body(out).startswith(base[:base.rindex("}")]), "a member of the page's designData changed")
        self.assertNotIn("<", self.body(out), "a raw < is in designData")

    def test_adds_one_design_after_the_existing_one(self):
        page = live_page(extra=DECOY_SLOT)  # the add must reach the real block, not the slot in the JS string
        out = self.added(page, ("new", self.write("new.html", MOCK_HTML)))
        self.assertEqual(list(self.designs(out)), ["mock", "new"], "the new design does not follow the existing one")
        self.assertEqual(self.designs(out)["new"], MOCK_HTML, "the new design is not the file's text")
        self.assert_only_designs_added(page, out)
        self.assertIn(OLD_BLOCK, out, "the roadmap block changed")
        self.assertIn("<title>x: Questions</title>", out, "the title changed")

    def test_adds_two_designs_in_argument_order_after_three_existing_ones(self):
        page = live_page(design=design_script(MANY_DESIGNS))
        out = self.added(page, ("b", self.write("b.html", MOCK_HTML)), ("a", self.write("a.html", "<p>a</p>\n")))
        self.assertEqual(list(self.designs(out)), ["m1", "m2", "m3", "b", "a"],
                         "the keys are not the existing ones, then the new ones in argument order")
        self.assertEqual(self.designs(out)["b"], MOCK_HTML, "the first new design is not the file's text")
        self.assertEqual(self.designs(out)["a"], "<p>a</p>\n", "the second new design is not the file's text")
        self.assert_only_designs_added(page, out)

    def test_adds_to_an_empty_designdata_without_a_leading_comma(self):
        page = live_page(design=EMPTY_DESIGN)
        out = self.added(page, ("new", self.write("new.html", MOCK_HTML)))
        self.assertEqual(list(self.designs(out)), ["new"])
        self.assert_only_designs_added(page, out)

    def test_a_full_size_mockup_arrives_whole_and_its_markers_stay_in_the_script(self):
        page = live_page()
        out = self.added(page, ("full", self.write("full.html", TEMPLATE)))
        self.assertEqual(self.designs(out)["full"], TEMPLATE, "the full-size mockup is not the file's text")
        self.assert_only_designs_added(page, out)
        self.assertEqual(len(SPLICE.markers(out)), len(SPLICE.markers(page)), "a marker of the mockup became a block marker")

    def test_every_angle_bracket_is_a_u003c_escape_and_the_value_round_trips(self):
        page = live_page(design=EMPTY_DESIGN)
        out = self.added(page, ("tricky", self.write("tricky.html", MOCK_HTML)))
        self.assertEqual(self.body(out).count("\\u003c"), MOCK_HTML.count("<"), "a < is not written as \\u003c")
        self.assertEqual(self.designs(out)["tricky"], MOCK_HTML, "the value does not round-trip to the file's text")
        self.assertEqual(len(SPLICE.markers(out)), len(SPLICE.markers(page)), "a marker of the mockup became a block marker")

    def test_add_design_combines_with_carry_and_changes_only_the_designs(self):
        template = live_page(block=EMPTY_BLOCK, design=EMPTY_DESIGN, extra=CHANGED_LINE)
        live = live_page(block=NEW_BLOCK.strip(), design=DESIGN, extra=DECOY_SLOT)
        template_path, live_path = self.write("template.html", template), self.write("live.html", live)
        code, said = self.command("--page", template_path, "--carry", live_path, out="carried.html")
        self.assertEqual(code, 0, "the carry does not run on a good pair: " + said)
        carried = self.read("carried.html")
        code, said = self.command("--page", template_path, "--carry", live_path, *self.adds(("new", self.write("new.html", MOCK_HTML))))
        self.assertEqual(code, 0, "--add-design with --carry exited %d, so no page was written: %s" % (code, said))
        out = self.read("out.html")
        self.assertEqual(self.outside(out), self.outside(carried), "the add changed a byte outside designData")
        self.assertEqual(list(self.designs(out)), ["mock", "new"], "the carried designs and the new one are not in order")
        self.assertEqual(self.designs(out)["new"], MOCK_HTML, "the new design is not the file's text")
        self.assertIn(CHANGED_LINE, out, "the template's change is gone")
        self.assertIn(NEW_BLOCK.strip(), out, "the live roadmap block is not carried")

    def test_a_relative_file_is_read_from_the_working_directory_as_its_whole_path_is(self):
        page = live_page(design=EMPTY_DESIGN)
        self.write("mock.html", MOCK_HTML)
        whole = self.added(page, ("new", self.path("mock.html")), out="whole.html")
        code, said = self.command("--page", self.path("live.html"), *self.adds(("new", "mock.html")), out="relative.html", cwd=self.tmp.name)
        self.assertEqual(code, 0, "the relative FILE is not read from the working directory: " + said)
        self.assertEqual(self.read("relative.html"), whole, "a relative FILE gives other bytes than its whole path")

    def test_a_relative_file_beside_the_page_is_not_read_from_another_working_directory(self):
        os.makedirs(self.path("pages"))
        page_path = self.write("pages/live.html", live_page(design=EMPTY_DESIGN))
        self.write("pages/mock.html", MOCK_HTML)
        code, said = self.command("--page", page_path, *self.adds(("new", "mock.html")), cwd=self.tmp.name)
        self.assertNotEqual(code, 0, "a relative FILE beside the page was read")
        self.assertRegex(said, "(?i)missing|not found|no such|cannot read", "the refusal does not name the missing file")
        self.assertFalse(os.path.exists(self.path("out.html")), "an output file was left")
        self.assertEqual(self.read("pages/live.html"), live_page(design=EMPTY_DESIGN), "the live page changed")

    def test_the_same_slug_with_the_same_html_is_a_no_op(self):
        page = live_page()
        out = self.added(page, ("mock", self.write("same.html", self.designs(page)["mock"])))
        self.assertEqual(out, page, "the no-op changed the page")

    def refused(self, page, pairs, word, why):
        """The same command adds a good design to a good page, so a refusal here is the add's own."""
        code, said = self.command("--page", self.write("live.html", live_page()), *self.adds(("ok", self.write("ok.html", MOCK_HTML))))
        self.assertEqual(code, 0, "the add does not run on a good page: " + said)
        os.remove(self.path("out.html"))
        code, said = self.command("--page", self.write("live.html", page), *self.adds(*pairs))
        self.assertNotEqual(code, 0, why + ": the add wrote a page")
        self.assertNotIn("Traceback", said, why + ": the refusal is a crash, not a refusal")
        self.assertNotIn("unrecognized arguments", said, why + ": the option was not read")
        self.assertNotIn("the following arguments are required", said, why + ": an argument is refused, not the design")
        self.assertNotIn("one of the arguments", said, why + ": an argument group is refused, not the design")
        self.assertRegex(said, "(?i)" + word, why + ": the refusal does not name its cause")
        self.assertFalse(os.path.exists(self.path("out.html")), why + ": an output file was left")
        self.assertEqual(self.read("live.html"), page, why + ": the live page changed")

    def test_a_page_with_no_designdata_block_is_refused(self):
        self.refused(live_page(design=""), [("new", self.write("new.html", MOCK_HTML))], "designData", "no designData block")

    def test_a_page_with_two_designdata_blocks_is_refused(self):
        self.refused(live_page(design=DESIGN + "\n" + DESIGN), [("new", self.write("new.html", MOCK_HTML))], "designData", "two designData blocks")

    def test_a_designdata_body_that_is_not_a_json_object_is_refused(self):
        for body in ["[]", "null", '"text"', "1", "{"]:
            with self.subTest(body=body):
                page = live_page(design='<script type="application/json" id="designData">%s</script>' % body)
                self.refused(page, [("new", self.write("new.html", MOCK_HTML))], "designData", "a designData body of %r" % body)

    def test_a_file_that_is_missing_empty_or_unreadable_is_refused(self):
        os.mkdir(self.path("dir.html"))
        with open(self.path("bad.html"), "wb") as f:
            f.write(b"\xff\xfe<p>\n")
        cases = [
            ("missing file", self.path("missing.html"), "missing|not found|no such|cannot read"),
            ("empty file", self.write("empty.html", ""), "empty"),
            ("a directory", self.path("dir.html"), "unreadable|cannot read|not readable|directory"),
            ("bytes that are not utf-8", self.path("bad.html"), "unreadable|cannot read|not readable|utf-?8|decode"),
        ]
        for why, path, word in cases:
            with self.subTest(why):
                self.refused(live_page(), [("new", path)], word, why)

    def test_a_slug_outside_a_to_z_0_to_9_and_hyphen_is_refused(self):
        good = self.write("good.html", MOCK_HTML)
        for slug in ["Bad", "under_score", "has space", "dot.name", "", "ünï", "a/b", "UPPER"]:
            with self.subTest(slug=slug):
                self.refused(live_page(), [(slug, good)], "slug", "the slug %r" % slug)

    def test_a_slug_with_a_hyphen_is_accepted_and_lands_in_designdata(self):
        page = live_page()
        self.assertNotIn("price-a", self.designs(page), "the page already holds the slug, so the add proves nothing")
        out = self.added(page, ("price-a", self.write("price-a.html", MOCK_HTML)))
        self.assertEqual(list(self.designs(out)), ["mock", "price-a"], "the hyphen slug is not added after the existing design")
        self.assertEqual(self.designs(out)["price-a"], MOCK_HTML, "the hyphen slug's design is not the file's text")
        self.assert_only_designs_added(page, out)

    def test_a_slug_with_a_digit_is_accepted_and_lands_in_designdata(self):
        for slug in ["opt2", "2a"]:
            with self.subTest(slug=slug):
                page = live_page()
                self.assertNotIn(slug, self.designs(page), "the page already holds the slug, so the add proves nothing")
                out = self.added(page, (slug, self.write(slug + ".html", MOCK_HTML)))
                self.assertEqual(list(self.designs(out)), ["mock", slug], "the digit slug %s is not added after the existing design" % slug)
                self.assertEqual(self.designs(out)[slug], MOCK_HTML, "the digit slug %s's design is not the file's text" % slug)
                self.assert_only_designs_added(page, out)

    def test_a_slug_that_exists_with_other_html_is_refused(self):
        other = self.write("other.html", "<p>different</p>\n")
        self.refused(live_page(), [("mock", other)], "already|exists|differ", "a slug that exists with other html")

    def test_one_bad_design_among_good_ones_writes_no_page(self):
        good = self.write("good.html", MOCK_HTML)
        self.refused(live_page(), [("good", good), ("Bad", good)], "slug", "a bad second design")


if __name__ == "__main__":
    unittest.main()
