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
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lint"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
CMD = os.environ.get("STALE_PAGES_UNDER_TEST") or os.path.join(HERE, "stale_pages.py")
SPLICE = os.environ.get("SPLICE_UNDER_TEST") or os.path.join(HERE, "splice.py")  # the same seam as test_splice.py
DESIGN_BLOCK = re.compile(r'<script type="application/json" id="designData">.*?</script>', re.S)
LINT = os.path.realpath(os.path.join(HERE, "..", "..", "lint"))
HOOKS = os.path.realpath(os.path.join(HERE, "..", "..", "hooks"))
sys.path.insert(0, LINT)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)

TEMPLATE = os.path.join(HERE, "page.html")
with open(TEMPLATE, encoding="utf-8") as f:
    PAGE = f.read()
URL = "https://claude.ai/artifact/%s"
RUN_FOLDER = None  # made in setUpModule

OPEN, CLOSE = "<!-- roadmap:data -->", "<!-- /roadmap:data -->"
DESIGN_BODY = '{"a": "\\u003cp>mockup\\u003c/p>"}'
# A roadmap block as build.py --block writes it: markup escaped, a lone quote, the escaped form of the closing marker.
ROADMAP_BODY = ('\n<script>window.ROADMAP_DATA = {"steps": {"c1": {"note": "a \\u003c!-- b <\\/script> Don\'t '
                '\\u003c!-- /roadmap:data -->"}}}; window.ROADMAP_BUILD = {"repo": "r"};</script>\n')
ROADMAP_RE = re.compile(re.escape(OPEN) + r".*?" + re.escape(CLOSE), re.S)


def with_both_blocks(page):
    """`page` with its designData and its roadmap block filled, as a live page holds them."""
    page = page.replace('id="designData">', 'id="designData">' + DESIGN_BODY, 1)
    return ROADMAP_RE.sub(lambda m: OPEN + ROADMAP_BODY + CLOSE, page, count=1)


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder

# Fixtures, all derived from page.html at run time. A live page holds backslash-u escapes in its mockups.
BLOCK = re.compile(r'(<script type="application/json" id="designData">)(.*?)(</script>)', re.S)
ALTERED = PAGE.replace("<title>", "<title>Altered ", 1)  # differs outside designData only
BS = chr(92)  # one backslash: a live page's mockups hold backslash-u-003c escapes
STALE_BODY = '{"a": "' + BS + 'u003cp>mock' + BS + 'u003c/p>", "b": "<i>raw</i>"}'
MOCK_BODY = '{"a": "' + BS + 'u003cp>mockup' + BS + 'u003c/p>", "b": "<i>raw</i>"}'
WRAPPER = os.path.join(HERE, "tests", "host-wrapper.txt")  # the real host wrapper, from an Artifact read
with open(WRAPPER, encoding="utf-8", newline="") as f:
    WRAPPER_TEXT = f.read()
VERDICT = re.compile(r"\b(current|behind|unknown)\b")


def set_body(text, body):
    """The text with its designData body replaced. A function replacement keeps the body's backslashes."""
    return BLOCK.sub(lambda m: m.group(1) + body + m.group(3), text, count=1)


def host_wrapped(page, after_body=""):
    """The host wrapper around `page`, with `after_body` placed right after its <body> tag."""
    assert WRAPPER_TEXT.count("@@PAGE@@") == 1 and WRAPPER_TEXT.count("<body>") == 1, "the wrapper fixture changed shape"
    return WRAPPER_TEXT.replace("<body>", "<body>" + after_body, 1).replace("@@PAGE@@", page, 1)


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return path


def link_repo_dirs(claude, hooks=True):
    """A fake ~/.claude gets this repo's lint folder, and its hooks folder unless `hooks` is False."""
    os.symlink(LINT, os.path.join(claude, "lint"))
    if hooks:
        os.symlink(HOOKS, os.path.join(claude, "hooks"))


def git(cwd, *args):
    """One git step of a fixture clone. The timeout bounds it, as it bounds every script run."""
    return subprocess.run(["git", "-C", cwd, "-c", "user.name=test", "-c", "user.email=test@example.invalid",
                           "-c", "core.hooksPath=/dev/null", *args],
                          capture_output=True, text=True, timeout=30, check=True)


class Stale(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=RUN_FOLDER)  # test-temp-standard: never the system temp dir
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

    def run_script(self, *args, script=None, home=None):
        """Every script run goes through here, so the timeout bounds each one."""
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        if home is not None:
            env["HOME"] = home
        return subprocess.run([sys.executable, script or CMD, *args], capture_output=True, text=True,
                              timeout=30, env=env)

    def run_cmd(self, *roots):
        r = self.run_script(self.fetched, *roots)
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
        old = ROADMAP_RE.sub("", PAGE.replace('id="designData">', 'id="designData">' + DESIGN_BODY, 1), count=1)
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

    # Single-page mode: stale_pages.py --page <fetched.html> [--write <out.html>] [--main <page.html>]

    def page_run(self, page, *extra, home=None, script=None):
        return self.run_script("--page", page, *extra, home=home, script=script)

    def verdict(self, r):
        """(word, line) for the one stdout line that names a verdict."""
        lines = [line for line in r.stdout.splitlines() if VERDICT.search(line)]
        self.assertEqual(len(lines), 1, "want one verdict line:\n" + r.stdout + r.stderr)
        return VERDICT.search(lines[0]).group(1), lines[0]

    def assert_names_template(self, line):
        self.assertTrue(any(p in line for p in (TEMPLATE, os.path.realpath(TEMPLATE))), line)

    def snapshot(self):
        """Every file under this test's temp folder, with size and mtime, so a write shows as a change."""
        found = {}
        for folder, _, names in os.walk(self.tmp.name):
            for name in names:
                path = os.path.join(folder, name)
                st = os.stat(path)
                found[os.path.relpath(path, self.tmp.name)] = (st.st_size, st.st_mtime_ns)
        return found

    def assert_only_new(self, before, new):
        """No file from `before` changed, and exactly the names in `new` appeared."""
        after = self.snapshot()
        self.assertEqual({k: after[k] for k in before if k in after}, before, "an existing file changed")
        self.assertEqual(set(after) - set(before), set(new))

    def assert_origin_run(self, page, home, script, code, word):
        """One run under a fake HOME: the exit code and the verdict, with origin/main the one source named."""
        r = self.page_run(page, home=home, script=script)
        self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        got, line = self.verdict(r)
        self.assertEqual(got, word, line)
        self.assertIn("origin/main", line)
        self.assertNotIn("installed copy", line)

    def assert_unknown_run(self, page, home, script):
        """Main unreadable: exit 2 and unknown, naming the installed copy or main. No file, even with --write, and no traceback."""
        out = os.path.join(self.tmp.name, "unknown-out.html")
        before = self.snapshot()
        r = self.page_run(page, "--write", out, home=home, script=script)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        word, line = self.verdict(r)
        self.assertEqual(word, "unknown", line)
        self.assertRegex(line, r"installed copy|main unreadable")
        self.assertNotIn("Traceback", r.stdout + r.stderr)
        self.assertFalse(os.path.exists(out))
        self.assert_only_new(before, set())

    def make_clone(self, name, files):
        """A git clone of `files` whose origin/main is its HEAD, as a fetched remote leaves it."""
        clone = os.path.join(self.tmp.name, name)
        for rel, text in files.items():
            write_text(os.path.join(clone, rel), text)
        git(clone, "init", "-q")
        git(clone, "add", "-A")
        git(clone, "commit", "-q", "-m", "fixture")
        git(clone, "update-ref", "refs/remotes/origin/main", "HEAD")
        return clone

    def test_stale_page_is_behind_and_write_puts_the_template_with_the_live_mockups(self):
        self.assertNotEqual(ALTERED, PAGE)
        stale = write_text(os.path.join(self.fetched, "stale.html"), set_body(ALTERED, STALE_BODY))
        r = self.page_run(stale, "--main", TEMPLATE)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        word, line = self.verdict(r)
        self.assertEqual(word, "behind")
        self.assert_names_template(line)
        out = os.path.join(self.tmp.name, "republish.html")
        before = self.snapshot()
        r = self.page_run(stale, "--main", TEMPLATE, "--write", out)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assert_only_new(before, {"republish.html"})
        with open(out, encoding="utf-8", newline="") as f:
            self.assertEqual(f.read(), set_body(PAGE, STALE_BODY))

    def write_out(self, live_text):
        """Run --page <live> --write OUT against page.html; (OUT text, the run). OUT is read without newline changes."""
        live = write_text(os.path.join(self.fetched, "live.html"), live_text)
        out = os.path.join(self.tmp.name, "republish.html")
        r = self.page_run(live, "--main", TEMPLATE, "--write", out)
        self.assertTrue(os.path.isfile(out), r.stdout + r.stderr)
        with open(out, encoding="utf-8", newline="") as f:
            return f.read(), r

    def test_write_carries_the_live_designdata_and_roadmap_blocks_byte_for_byte(self):
        # The writer republishes OUT: a roadmap block left empty here gives a blank Status tab, and stale_pages
        # still reads the page current because its compare empties that block.
        def crlf(text):  # CRLF inside the block: a carry that re-serializes it would change these bytes
            return text.replace(ROADMAP_BODY, ROADMAP_BODY.replace("\n", "\r\n"), 1)
        live_text = crlf(with_both_blocks(ALTERED))  # behind: differs from page.html outside the blocks
        self.assertIn(ROADMAP_BODY.replace("\n", "\r\n"), live_text)
        out, r = self.write_out(live_text)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(ROADMAP_RE.findall(out), ROADMAP_RE.findall(live_text), "OUT lost the live roadmap block")
        self.assertEqual(DESIGN_BLOCK.findall(out), DESIGN_BLOCK.findall(live_text), "OUT lost the live designData block")
        self.assertEqual(out, crlf(with_both_blocks(PAGE)), "OUT is not page.html with the two live blocks")

    def test_write_of_a_page_with_no_roadmap_block_keeps_the_live_designs_and_the_templates_empty_block(self):
        live_text = ROADMAP_RE.sub("", set_body(ALTERED, DESIGN_BODY), count=1)  # a page from before the roadmap block
        self.assertNotIn(OPEN, live_text)
        out, r = self.write_out(live_text)
        self.assertNotEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(DESIGN_BLOCK.findall(out), DESIGN_BLOCK.findall(live_text), "OUT lost the live designData block")
        self.assertEqual(ROADMAP_RE.findall(out), ROADMAP_RE.findall(PAGE), "OUT lost the template's empty roadmap block")
        self.assertEqual(out, set_body(PAGE, DESIGN_BODY), "OUT is not page.html with the live designData")

    def test_current_page_with_mockups_is_current_and_check_mode_writes_nothing(self):
        mocked = write_text(os.path.join(self.fetched, "mocked.html"), set_body(PAGE, MOCK_BODY))
        before = self.snapshot()
        r = self.page_run(mocked, "--main", TEMPLATE)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        word, line = self.verdict(r)
        self.assertEqual(word, "current")
        self.assert_names_template(line)
        self.assert_only_new(before, set())

    def test_unknown_page_exits_2_and_writes_nothing_even_with_write(self):
        cases = {
            "missing file": None,
            "empty file": "",
            "no designData block": BLOCK.sub("", PAGE, count=1),
            "two designData blocks": PAGE + "\n" + BLOCK.search(PAGE).group(0),
        }
        out = os.path.join(self.tmp.name, "republish.html")
        for label, text in cases.items():
            with self.subTest(label):
                page = os.path.join(self.fetched, label.replace(" ", "-") + ".html")
                if text is not None:
                    write_text(page, text)
                before = self.snapshot()
                r = self.page_run(page, "--main", TEMPLATE, "--write", out)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertEqual(self.verdict(r)[0], "unknown")
                self.assertFalse(os.path.exists(out))
                self.assert_only_new(before, set())

    def test_only_origin_main_proves_current_or_behind(self):
        clone = self.make_clone("clone", {"skills/waiting-page/page.html": PAGE, "CLAUDE.md": "# claude-settings\n"})
        home = os.path.join(self.tmp.name, "home")
        claude = os.path.join(home, ".claude")
        installed = os.path.join(claude, "skills", "waiting-page")
        os.makedirs(installed)
        probe = subprocess.run(["git", "-C", installed, "rev-parse", "--is-inside-work-tree"],
                               capture_output=True, text=True, timeout=30)
        self.assertNotEqual(probe.returncode, 0, "the temp folder is inside a git checkout, so the script finds that")
        shutil.copy2(CMD, os.path.join(installed, "stale_pages.py"))
        shutil.copy2(SPLICE, os.path.join(os.path.dirname(os.path.join(installed, "stale_pages.py")), "splice.py"))
        write_text(os.path.join(installed, "page.html"), ALTERED)
        link_repo_dirs(claude)
        pointer = write_text(os.path.join(claude, "CLAUDE.md"), "@%s/CLAUDE.md\n" % clone)
        script = os.path.join(installed, "stale_pages.py")
        same = write_text(os.path.join(self.fetched, "same.html"), PAGE)  # equals origin/main
        old = write_text(os.path.join(self.fetched, "old.html"), ALTERED)  # equals the installed copy
        with self.subTest("pointer: origin/main page is current"):
            self.assert_origin_run(same, home, script, 0, "current")
        with self.subTest("pointer: older page is behind origin/main"):
            self.assert_origin_run(old, home, script, 1, "behind")
        write_text(pointer, "# no pointer here\n")
        with self.subTest("no pointer: main unreadable, so unknown"):
            self.assert_unknown_run(old, home, script)
        with self.subTest("no pointer: origin/main page is still unknown"):
            self.assert_unknown_run(same, home, script)
        plain = write_text(os.path.join(self.tmp.name, "plain", "CLAUDE.md"), "# not a checkout\n")
        write_text(pointer, "@%s\n" % plain)
        with self.subTest("pointer to a folder with no git read: unknown"):
            self.assert_unknown_run(old, home, script)

    def test_script_run_from_inside_a_checkout_reads_that_checkouts_origin_main(self):
        with open(CMD, encoding="utf-8") as f:
            script_text = f.read()
        with open(SPLICE, encoding="utf-8") as f:
            splice_text = f.read()
        clone = self.make_clone("own", {"skills/waiting-page/page.html": PAGE,
                                        "skills/waiting-page/stale_pages.py": script_text,
                                        "skills/waiting-page/splice.py": splice_text})
        home = os.path.join(self.tmp.name, "home")
        os.makedirs(os.path.join(home, ".claude", "skills", "waiting-page"))
        link_repo_dirs(os.path.join(home, ".claude"))
        script = os.path.join(home, ".claude", "skills", "waiting-page", "stale_pages.py")
        os.symlink(os.path.join(clone, "skills", "waiting-page", "stale_pages.py"), script)
        same = write_text(os.path.join(self.fetched, "same.html"), PAGE)
        old = write_text(os.path.join(self.fetched, "old.html"), ALTERED)
        with self.subTest("origin/main page is current"):
            self.assert_origin_run(same, home, script, 0, "current")
        with self.subTest("older page is behind origin/main"):
            self.assert_origin_run(old, home, script, 1, "behind")

    def test_extra_code_outside_the_template_is_behind(self):
        cases = {
            "appended script": PAGE + "<script>window.extra = 1;</script>",
            "style right after body": host_wrapped(PAGE, "<style>p { color: red; }</style>"),
            "script right after body": host_wrapped(PAGE, "<script>window.extra = 1;</script>"),
        }
        for label, text in cases.items():
            with self.subTest(label):
                page = write_text(os.path.join(self.fetched, label.replace(" ", "-") + ".html"), text)
                r = self.page_run(page, "--main", TEMPLATE)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertEqual(self.verdict(r)[0], "behind")

    def test_host_wrapper_around_the_template_is_current_in_both_modes(self):
        with self.subTest("single page"):
            page = write_text(os.path.join(self.fetched, "wrapped.html"), host_wrapped(PAGE))
            r = self.page_run(page, "--main", TEMPLATE)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(self.verdict(r)[0], "current")
        with self.subTest("batch"):
            root = self.repo("wrapped", "HHH")
            self.fetch("HHH", host_wrapped(PAGE))
            code, out = self.run_cmd(root)
            self.assertEqual(code, 0, out)
            self.assertIn("current: wrapped", out)

    def test_batch_mode_appended_code_is_behind(self):
        root = self.repo("appended", "GGG")
        self.fetch("GGG", PAGE + "<script>window.extra = 1;</script>")
        code, out = self.run_cmd(root)
        self.assertEqual(code, 1, out)
        self.assertIn("behind: appended", out)
        self.assertNotIn("current: appended", out)

    def test_write_to_an_unwritable_path_is_unknown_without_traceback(self):
        stale = write_text(os.path.join(self.fetched, "unwritable.html"), set_body(ALTERED, STALE_BODY))
        blocker = write_text(os.path.join(self.tmp.name, "blocker"), "a regular file\n")
        targets = {
            "under a regular file": os.path.join(blocker, "out.html"),
            "parent folder missing": os.path.join(self.tmp.name, "no-such-folder", "out.html"),
        }
        for label, out in targets.items():
            with self.subTest(label):
                before = self.snapshot()
                r = self.page_run(stale, "--main", TEMPLATE, "--write", out)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertEqual(self.verdict(r)[0], "unknown")
                self.assertNotIn("Traceback", r.stdout + r.stderr)
                self.assertFalse(os.path.exists(out))
                self.assert_only_new(before, set())

    def test_no_hooks_reachable_is_unknown_without_traceback(self):
        home = os.path.join(self.tmp.name, "home")
        claude = os.path.join(home, ".claude")
        installed = os.path.join(claude, "skills", "waiting-page")
        os.makedirs(installed)
        script = os.path.join(installed, "stale_pages.py")
        shutil.copy2(CMD, script)
        shutil.copy2(SPLICE, os.path.join(os.path.dirname(script), "splice.py"))
        write_text(os.path.join(installed, "page.html"), ALTERED)
        link_repo_dirs(claude, hooks=False)
        same = write_text(os.path.join(self.fetched, "same.html"), PAGE)
        self.assert_unknown_run(same, home, script)

    def test_non_utf8_pointer_file_gives_no_traceback(self):
        clone = self.make_clone("clone", {"skills/waiting-page/page.html": PAGE, "CLAUDE.md": "# claude-settings\n"})
        home = os.path.join(self.tmp.name, "home")
        claude = os.path.join(home, ".claude")
        installed = os.path.join(claude, "skills", "waiting-page")
        os.makedirs(installed)
        script = os.path.join(installed, "stale_pages.py")
        shutil.copy2(CMD, script)
        shutil.copy2(SPLICE, os.path.join(os.path.dirname(script), "splice.py"))
        write_text(os.path.join(installed, "page.html"), ALTERED)
        link_repo_dirs(claude)
        # Bytes that are not UTF-8, then a valid pointer line to the clone.
        pointer = bytes([255, 254, 32]) + b"caf" + bytes([233, 10]) + b"@" + os.fsencode(clone) + b"/CLAUDE.md" + bytes([10])
        with open(os.path.join(claude, "CLAUDE.md"), "wb") as f:
            f.write(pointer)
        same = write_text(os.path.join(self.fetched, "same.html"), PAGE)
        r = self.page_run(same, home=home, script=script)
        self.assertIn(r.returncode, (0, 1, 2), r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stdout + r.stderr)
        word, line = self.verdict(r)
        self.assertEqual(r.returncode, {"current": 0, "behind": 1, "unknown": 2}[word], line)

    def test_check_mode_writes_no_file_and_write_mode_writes_exactly_one(self):
        stale = write_text(os.path.join(self.fetched, "cost.html"), set_body(ALTERED, STALE_BODY))
        mocked = write_text(os.path.join(self.fetched, "cost-current.html"), set_body(PAGE, MOCK_BODY))
        before = self.snapshot()
        with mock.patch.object(subprocess, "run", wraps=subprocess.run) as spy:
            self.assertEqual(self.page_run(stale, "--main", TEMPLATE).returncode, 1)
            self.assert_only_new(before, set())
            behind_out = os.path.join(self.tmp.name, "behind.html")
            self.assertEqual(self.page_run(stale, "--main", TEMPLATE, "--write", behind_out).returncode, 1)
            self.assert_only_new(before, {"behind.html"})
            current_out = os.path.join(self.tmp.name, "current.html")
            self.assertEqual(self.page_run(mocked, "--main", TEMPLATE, "--write", current_out).returncode, 0)
            self.assert_only_new(before, {"behind.html", "current.html"})
        self.assertEqual(spy.call_count, 3)
        self.assertEqual({c.kwargs.get("timeout") for c in spy.call_args_list}, {30})


if __name__ == "__main__":
    unittest.main()
