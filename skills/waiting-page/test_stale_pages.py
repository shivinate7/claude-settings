"""Fixture suite for stale_pages.py. Run: python3 skills/waiting-page/test_stale_pages.py

STALE_PAGES_UNDER_TEST names the command to run (default: stale_pages.py beside this file), so the
same cases run red against a checkout that lacks it.
"""
import contextlib
import importlib.util
import io
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
ALTERED = PAGE.replace("<style>", "<style>/* altered */", 1)  # differs outside designData, the roadmap block and <title> text (shiv ruling, Oct 30 14:33 CDT)
BS = chr(92)  # one backslash: a live page's mockups hold backslash-u-003c escapes
STALE_BODY = '{"a": "' + BS + 'u003cp>mock' + BS + 'u003c/p>", "b": "<i>raw</i>"}'
MOCK_BODY = '{"a": "' + BS + 'u003cp>mockup' + BS + 'u003c/p>", "b": "<i>raw</i>"}'
WRAPPER = os.path.join(HERE, "tests", "host-wrapper.txt")  # the real host wrapper, from an Artifact read
with open(WRAPPER, encoding="utf-8", newline="") as f:
    WRAPPER_TEXT = f.read()
VERDICT = re.compile(r"\b(current|behind|unknown)\b")


def with_title(text, title):
    """`text` with its document title's text replaced. A function replacement keeps the title's backslashes."""
    return re.sub(r"<title>[^<]*</title>", lambda m: "<title>%s</title>" % title, text, count=1)


# The setTitle line of main before the page was named Cockpit. Its escape is JS text, kept as written.
OLD_TITLE_LINE = r'  document.title = (name ? name + " " : "") + "Queue" + (state.tab === "s" ? " \u00b7 Status" : "");'


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

    def fetch(self, page_id, text=None, unreadable=False, notfound=False):
        ext = ".notfound" if notfound else ".unreadable" if unreadable else ".html"
        with open(os.path.join(self.fetched, page_id + ext), "w", encoding="utf-8") as f:
            f.write(text or "")

    def run_script(self, *args, script=None, home=None, extra_env=None):
        """Every script run goes through here, so the timeout bounds each one. `extra_env` adds variables to the run."""
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        if home is not None:
            env["HOME"] = home
        env.update(extra_env or {})
        return subprocess.run([sys.executable, script or CMD, *args], capture_output=True, text=True,
                              timeout=30, env=env)

    def run_cmd(self, *roots, script=None):
        r = self.run_script(self.fetched, *roots, script=script)
        return r.returncode, r.stdout + r.stderr

    def line_starting(self, out, prefix):
        """The one output line that starts with `prefix`."""
        lines = [line for line in out.splitlines() if line.startswith(prefix)]
        self.assertEqual(len(lines), 1, "want one line starting %r:\n%s" % (prefix, out))
        return lines[0]

    def not_found_line(self, out, owner):
        """The one output line that starts `not-found: <owner>`."""
        return self.line_starting(out, "not-found: %s" % owner)

    def total_line(self, out):
        """The one output line that starts `waiting pages:`."""
        lines = [line for line in out.splitlines() if line.startswith("waiting pages: ")]
        self.assertEqual(len(lines), 1, "want one total line:\n" + out)
        return lines[0]

    def hub_checkout(self, url=None, extras_text=None):
        """A claude-settings checkout for batch mode: a copy of the script with page.html and lint/ beside it, and an
        extras file naming `url` as its waiting page (None: no waiting page), or `extras_text` as the file's text.
        Returns the copy's path; the checkout is self.tmp.name/hub."""
        hub = os.path.join(self.tmp.name, "hub")
        skill = os.path.join(hub, "skills", "waiting-page")
        write_text(os.path.join(skill, "page.html"), PAGE)
        shutil.copy2(CMD, os.path.join(skill, "stale_pages.py"))
        shutil.copy2(SPLICE, os.path.join(skill, "splice.py"))  # the script imports it from beside itself
        os.symlink(LINT, os.path.join(hub, "lint"))
        extras = {"kinds": {}}
        if url:
            extras["waiting-page"] = url
        text = extras_text if extras_text is not None else json.dumps(extras)
        write_text(os.path.join(hub, ".claude", "layout-extras.json"), text)
        return os.path.join(skill, "stale_pages.py")

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
        self.assertIn("1 current, 1 behind, 1 unknown, 0 not-found", out)

    def test_page_with_own_mockups_is_current(self):
        mock = PAGE.replace('id="designData">', 'id="designData">{"a": "\\u003cp>mockup\\u003c/p>"}', 1)
        self.assertNotEqual(mock, PAGE)
        root = self.repo("mocked", "DDD")
        self.fetch("DDD", mock)
        code, out = self.run_cmd(root)
        self.assertEqual(code, 0, out)
        self.assertIn("current: mocked", out)

    def test_a_page_that_differs_only_in_its_title_is_current_in_both_modes(self):
        # The verdict ignores the <title> text, so a title alone never makes a page behind. The title holds a lone
        # quote and comment openers; every other byte is page.html's.
        titled = re.sub(r"<title>[^<]*</title>", "<title>Bob's /* // Compass Cockpit</title>", PAGE, count=1)
        self.assertNotEqual(titled, PAGE)
        with self.subTest("batch"):
            root = self.repo("titled", "KKK")
            self.fetch("KKK", titled)
            code, out = self.run_cmd(root)
            self.assertEqual(code, 0, out)
            self.assertIn("current: titled", out)
        with self.subTest("single page"):
            page = write_text(os.path.join(self.fetched, "titled-single.html"), titled)
            r = self.page_run(page, "--main", TEMPLATE)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(self.verdict(r)[0], "current")

    def test_an_edited_svg_title_reads_behind_and_an_edited_page_title_does_not(self):
        # Only the document <title> is the live page's own. A <title> inside an svg is page code.
        svg = "<svg><title>Icon label</title></svg>"
        main = write_text(os.path.join(self.fetched, "main-with-svg.html"), PAGE.replace('<header class="hdr">', svg + '<header class="hdr">', 1))
        self.assertIn(svg, open(main, encoding="utf-8").read())
        edited_svg = write_text(os.path.join(self.fetched, "svg-edited.html"), open(main, encoding="utf-8").read().replace("Icon label", "Edited label"))
        main_text = open(main, encoding="utf-8").read()
        retitled = with_title(main_text, "Compass Cockpit")
        self.assertNotEqual(retitled, main_text, "the edit changed no title")
        edited_title = write_text(os.path.join(self.fetched, "title-edited.html"), retitled)
        r = self.page_run(edited_svg, "--main", main)
        self.assertEqual(self.verdict(r)[0], "behind", r.stdout + r.stderr)
        r = self.page_run(edited_title, "--main", main)
        self.assertEqual(self.verdict(r)[0], "current", r.stdout + r.stderr)

    def test_an_old_main_page_titled_with_the_old_name_reads_behind_the_new_template(self):
        # A live page from before the rename still runs
        # the old setTitle line, so it reads behind. The title text alone never makes a page behind; this line does.
        self.assertIsNotNone(re.search(r"^  document\.title = [^\n]*", PAGE, re.M), "page.html has no setTitle document.title line")
        old = re.sub(r"^  document\.title = [^\n]*", lambda m: OLD_TITLE_LINE, PAGE, count=1, flags=re.M)
        old = with_title(old, "Compass Queue")
        root = self.repo("old-main", "OLD")
        self.fetch("OLD", old)
        code, out = self.run_cmd(root)
        self.assertEqual(code, 1, out)
        self.assertIn("behind: old-main", out)
        page = write_text(os.path.join(self.fetched, "old-main-single.html"), old)
        r = self.page_run(page, "--main", TEMPLATE)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(self.verdict(r)[0], "behind", r.stdout + r.stderr)

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

    def test_a_notfound_marker_reads_not_found_not_unknown(self):
        # Not found from this account proves nothing: the page may belong to another account.
        root = self.repo("gone", "NNN")
        self.fetch("NNN", notfound=True)
        code, out = self.run_cmd(root)
        line = self.not_found_line(out, "gone")
        self.assertRegex(line, r"not found from this account", "the not-found line does not say it was not found from this account")
        self.assertRegex(line, r"another account", "the not-found line does not say the page may be another account's")
        self.assertEqual(code, 1, out)

    def test_a_notfound_line_names_the_claude_settings_waiting_page(self):
        # The target is the waiting page of the checkout that holds the script, read from its extras file. This hub's
        # URL is not the claude-settings page, so a URL copied into the script fails this case.
        hub_url = URL % "HUBLIVE0123"
        script = self.hub_checkout(hub_url)
        root = self.repo("gone", "NNN")
        self.fetch("NNN", notfound=True)
        code, out = self.run_cmd(root, script=script)
        line = self.not_found_line(out, "gone")
        self.assertIn("the claude-settings waiting page %s" % hub_url, line,
                      "the not-found line does not name the claude-settings waiting page")

    def test_a_hub_with_no_waiting_page_says_the_claude_settings_waiting_page_is_unknown(self):
        script = self.hub_checkout(None)
        root = self.repo("gone", "NNN")
        self.fetch("NNN", notfound=True)
        code, out = self.run_cmd(root, script=script)
        line = self.not_found_line(out, "gone")
        self.assertIn("the claude-settings waiting page is unknown", line,
                      "the not-found line does not say the claude-settings waiting page is unknown")

    def test_the_total_line_counts_not_found_apart_from_unknown_and_exit_1(self):
        # A page not found from this account is never counted current, and has its own count apart from unknown.
        roots = [self.repo("fresh", "AAA"), self.repo("gone", "NNN"), self.repo("gone-too", "MMM")]
        self.fetch("AAA", PAGE)
        self.fetch("NNN", notfound=True)
        self.fetch("MMM", notfound=True)
        code, out = self.run_cmd(*roots)
        self.assertEqual(self.total_line(out), "waiting pages: 1 current, 0 behind, 0 unknown, 2 not-found",
                         "the total line does not count the not-found pages apart")
        self.assertEqual(code, 1, out)

    def test_a_batch_with_no_waiting_page_totals_zero_not_found(self):
        # The empty state: a repo with no waiting page is left out, and the total line still carries a not-found count.
        bare = os.path.join(self.tmp.name, "bare")
        write_text(os.path.join(bare, ".claude", "layout-extras.json"), json.dumps({"kinds": {}}))
        code, out = self.run_cmd(bare)
        self.assertEqual(self.total_line(out), "waiting pages: 0 current, 0 behind, 0 unknown, 0 not-found",
                         "the total line has no not-found count")
        self.assertEqual(code, 0, out)

    def test_an_unreadable_line_says_the_read_failed_and_not_or_not_found(self):
        # An unreadable page is another account's or a failed read. The line claims no more than that: .notfound owns "not found".
        root = self.repo("other-account", "CCC")
        self.fetch("CCC", unreadable=True)
        code, out = self.run_cmd(root)
        line = self.line_starting(out, "unknown: other-account")
        self.assertIn("the read failed", line, "the unreadable line does not say the read failed")
        self.assertNotIn("or not found", line, "the unreadable line still says 'or not found'")

    def test_a_sibling_not_found_line_says_to_re_file_its_items_on_the_hub_page(self):
        # The hub page holds the hub's own items, not this repo's. The line tells the owner to re-file this repo's items there.
        hub_url = URL % "HUBLIVE0123"
        script = self.hub_checkout(hub_url)
        root = self.repo("sibling", "NNN")
        self.fetch("NNN", notfound=True)
        code, out = self.run_cmd(root, script=script)
        line = self.not_found_line(out, "sibling")
        self.assertIn("re-file", line, "the not-found line does not say to re-file the items")
        self.assertIn("the claude-settings waiting page %s" % hub_url, line,
                      "the not-found line does not name the claude-settings waiting page to re-file on")
        self.assertNotIn("holds", line, "the not-found line says the hub page already holds the items")

    def test_a_hub_whose_own_page_is_not_found_names_no_page_to_re_file_on(self):
        # The hub's target is its own recorded page. When that page is not found too, no page is named as where to re-file.
        hub_url = URL % "HUBLIVE0123"
        script = self.hub_checkout(hub_url)
        hub = os.path.join(self.tmp.name, "hub")
        self.fetch("HUBLIVE0123", notfound=True)
        code, out = self.run_cmd(hub, script=script)
        line = self.not_found_line(out, "hub")
        self.assertNotIn("the claude-settings waiting page %s" % hub_url, line,
                         "the hub's not-found line names its own page as the waiting page to re-file on")
        self.assertIn("the claude-settings waiting page is unknown", line,
                      "the hub's not-found line does not read the waiting page as unknown")

    def test_a_hub_url_with_a_query_string_is_still_its_own_page_for_the_target(self):
        # The hub's URL carries a query string. It is the same artifact, so the hub's own target is unknown.
        hub_url = (URL % "HUBLIVE0123") + "?x=1"
        script = self.hub_checkout(hub_url)
        hub = os.path.join(self.tmp.name, "hub")
        self.fetch("HUBLIVE0123", notfound=True)
        code, out = self.run_cmd(hub, script=script)
        line = self.not_found_line(out, "hub")
        self.assertNotIn("the claude-settings waiting page %s" % hub_url, line,
                         "the hub's own line names its own query-string URL as the waiting page to re-file on")
        self.assertIn("the claude-settings waiting page is unknown", line,
                      "the hub's own target is not unknown when its URL carries a query string")

    def test_a_sibling_under_a_not_found_hub_gives_its_re_file_target_as_unknown(self):
        # The hub's page is not found too, so the sibling has no live page to re-file on and must not name the hub's URL.
        hub_url = URL % "HUBLIVE0123"
        script = self.hub_checkout(hub_url)
        hub = os.path.join(self.tmp.name, "hub")
        root = self.repo("sibling", "NNN")
        self.fetch("HUBLIVE0123", notfound=True)
        self.fetch("NNN", notfound=True)
        code, out = self.run_cmd(hub, root, script=script)
        line = self.not_found_line(out, "sibling")
        self.assertIn("the claude-settings waiting page is unknown", line,
                      "the sibling's re-file target is not unknown while the hub page is not found")
        self.assertNotIn(hub_url, line, "the sibling's line names the hub page as its re-file target")

    def test_a_sibling_under_an_unreadable_hub_gives_its_re_file_target_as_unknown(self):
        # The hub's page cannot be read, so the sibling has no live page to re-file on and must not name the hub's URL.
        hub_url = URL % "HUBLIVE0123"
        script = self.hub_checkout(hub_url)
        hub = os.path.join(self.tmp.name, "hub")
        root = self.repo("sibling", "NNN")
        self.fetch("HUBLIVE0123", unreadable=True)
        self.fetch("NNN", notfound=True)
        code, out = self.run_cmd(hub, root, script=script)
        line = self.not_found_line(out, "sibling")
        self.assertIn("the claude-settings waiting page is unknown", line,
                      "the sibling's re-file target is not unknown while the hub page is unreadable")
        self.assertNotIn(hub_url, line, "the sibling's line names the hub page as its re-file target")

    def test_malformed_hub_extras_give_no_traceback_and_an_unknown_target(self):
        # The hub's extras file is not JSON. A sibling's not-found line still prints, with the target unknown, and no traceback.
        script = self.hub_checkout(extras_text="{not json")
        root = self.repo("sibling", "NNN")
        self.fetch("NNN", notfound=True)
        r = self.run_script(self.fetched, root, script=script)
        out = r.stdout + r.stderr
        self.assertNotIn("Traceback", out, "malformed hub extras end the batch with a traceback")
        line = self.not_found_line(out, "sibling")
        self.assertIn("the claude-settings waiting page is unknown", line,
                      "the not-found line does not read the waiting page as unknown")
        self.assertEqual(r.returncode, 1, out)

    # Single-page mode: stale_pages.py --page <fetched.html> [--write <out.html>] [--main <page.html>]

    def page_run(self, page, *extra, home=None, script=None, env=None):
        return self.run_script("--page", page, *extra, home=home, script=script, extra_env=env)

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

    # Single-page mode with --items <file or folder>: one wait line per open item with a `waits` field, after the verdict line.

    def gh_env(self, answers):
        """The environment of one run: WAITING_PAGE_GH names a gh stand-in that answers `answers` ({full argv: [exit, stdout]}),
        and PATH starts with a gh that only logs, so no run reaches GitHub. Returns (env, the folder whose calls.txt logs both)."""
        folder = tempfile.mkdtemp(dir=self.tmp.name, prefix="gh-")
        write_text(os.path.join(folder, "answers.json"), json.dumps(answers))
        stub = self.executable(os.path.join(folder, "gh"), GH_STUB)
        path_dir = tempfile.mkdtemp(dir=self.tmp.name, prefix="path-")
        self.executable(os.path.join(path_dir, "gh"), GH_LOG.replace("@LOG@", repr(os.path.join(folder, "calls.txt"))))
        return {"WAITING_PAGE_GH": stub, "PATH": path_dir + os.pathsep + os.environ.get("PATH", "")}, folder

    def executable(self, path, text):
        write_text(path, text.replace("@PYTHON@", sys.executable))
        os.chmod(path, 0o755)
        return path

    def gh_calls(self, folder):
        """Each argv that reached the gh stand-in or the logging gh, in order. Empty when none did."""
        path = os.path.join(folder, "calls.txt")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            return f.read().splitlines()

    def items_file(self, items):
        """The items as a JSON list: the first shape --items takes."""
        return self.list_file(items, "items")

    def list_file(self, docs, name):
        """`docs` as a JSON list in <name>.json, in a folder of its own: the list shape --items and --answers take."""
        path = os.path.join(tempfile.mkdtemp(dir=self.tmp.name, prefix=name + "-"), name + ".json")
        return write_text(path, json.dumps(docs))

    def items_folder(self, items, keys=None):
        """The items as the folder `ArtifactData list` saves: one <key>.json per item, and the .complete marker it leaves.
        The key is the item's id, unless `keys` names one per item, for an item with no id field."""
        return self.docs_folder({(keys[i] if keys else item["id"]): item for i, item in enumerate(items)}, "items")

    def docs_folder(self, docs, name):
        """The folder `ArtifactData list` saves: one <doc id>.json per entry of `docs` ({doc id: data}), and the .complete marker it leaves."""
        folder = tempfile.mkdtemp(dir=self.tmp.name, prefix=name + "-")
        for doc_id, data in docs.items():
            write_text(os.path.join(folder, doc_id + ".json"), json.dumps(data))
        write_text(os.path.join(folder, ".complete"), "")
        return folder

    def current_and_behind(self):
        """The two fetched pages the --items cases run on: page.html as it is, and the stale page the behind cases use."""
        return (write_text(os.path.join(self.fetched, "current.html"), PAGE),
                write_text(os.path.join(self.fetched, "behind.html"), set_body(ALTERED, STALE_BODY)))

    def items_run(self, page, items, env, answers=None):
        extra = [] if answers is None else ["--answers", answers]
        return self.page_run(page, "--main", TEMPLATE, "--items", items, *extra, env=env)

    def page_line(self, r):
        """The page's verdict line: the first stdout line."""
        return (r.stdout.splitlines() or [""])[0]

    def assert_page_word(self, r, word, code):
        """Exit `code`, and the verdict line first on stdout reads `word`."""
        self.assertTrue(self.page_line(r).startswith(word + ":"), "the first stdout line is not the page verdict %r:\n%s" % (word, r.stdout + r.stderr))
        self.assertEqual(r.returncode, code, "the exit code is not the page verdict's:\n" + r.stdout + r.stderr)

    def wait_lines(self, r, n):
        """The stdout lines after the verdict line that name item `n` as a whole number."""
        return [line for line in r.stdout.splitlines()[1:] if re.search(r"(?<!\d)%d(?!\d)" % n, line)]

    def assert_wait_line(self, r, n, target, word):
        """Exactly one line after the verdict line names item `n` and `target`, and it reads `word` and no other wait word."""
        lines = self.wait_lines(r, n)
        self.assertEqual(len(lines), 1, "item %d: want one wait line after the verdict line, got %d:\n%s" % (n, len(lines), r.stdout + r.stderr))
        line = lines[0]
        self.assertRegex(line, r"(?<!\d)%s(?!\d)" % re.escape(str(target)), "item %d: its wait line does not name %s" % (n, target))
        self.assertRegex(line, r"\b%s\b" % word, "item %d: its wait line does not read %s" % (n, word))
        for other in WAIT_WORDS - {word}:
            self.assertNotRegex(line, r"\b%s\b" % other, "item %d: its wait line reads %s as well as %s" % (n, other, word))

    def assert_wait(self, waits, argv, answer, target, word, n=154, as_folder=False):
        """Item `n` waiting on `waits`, gh answering `answer` to `argv`: the page stays current at exit 0, its wait line
        names `target` and reads `word`, and gh was called once, with argv."""
        current, _ = self.current_and_behind()
        env, folder = self.gh_env({argv: answer})
        item = [wait_item(n, waits)]
        items = self.items_folder(item) if as_folder else self.items_file(item)
        r = self.items_run(current, items, env)
        self.assert_page_word(r, "current", 0)
        self.assert_wait_line(r, n, target, word)
        self.assertEqual(self.gh_calls(folder), [argv], "gh calls for item %d" % n)

    def test_a_run_that_completed_with_a_failure_names_its_item_ended(self):
        for as_folder in (False, True):
            with self.subTest("folder of <id>.json files" if as_folder else "list file"):
                self.assert_wait({"repo": REPO, "run": RUN}, RUN_ARGV, RUN_DONE, RUN, "ended", as_folder=as_folder)

    def test_an_open_pr_or_a_run_in_progress_names_its_item_waiting(self):
        with self.subTest("open pr"):
            self.assert_wait({"repo": REPO, "pr": PR}, PR_ARGV, PR_OPEN, PR, "waiting")
        with self.subTest("run in progress"):
            self.assert_wait({"repo": REPO, "run": RUN}, RUN_ARGV, RUN_IN_PROGRESS, RUN, "waiting")

    def test_a_pr_closed_without_a_merge_names_its_item_ended(self):
        self.assert_wait({"repo": REPO, "pr": PR}, PR_ARGV, PR_CLOSED, PR, "ended")

    def test_a_merged_pr_names_its_item_ended(self):
        self.assert_wait({"repo": REPO, "pr": PR}, PR_ARGV, PR_MERGED, PR, "ended")

    def test_a_gh_that_fails_is_missing_or_answers_non_json_names_its_item_unknown(self):
        current, behind = self.current_and_behind()
        base, _ = self.gh_env({RUN_ARGV: [1, ""]})
        envs = {
            "exits non-zero": base,
            "missing": dict(base, WAITING_PAGE_GH=os.path.join(self.tmp.name, "no-such-gh")),
            "answers non-json": self.gh_env({RUN_ARGV: [0, "not json"]})[0],
        }
        for label, env in envs.items():
            for word, page, code in (("current", current, 0), ("behind", behind, 1)):
                with self.subTest(gh=label, page=word):
                    items = self.items_file([wait_item(154, {"repo": REPO, "run": RUN})])
                    r = self.items_run(page, items, env)
                    self.assert_page_word(r, word, code)
                    self.assert_wait_line(r, 154, RUN, "unknown")

    def test_without_items_gh_is_never_called(self):
        current, _ = self.current_and_behind()
        env, folder = self.gh_env({RUN_ARGV: RUN_DONE})
        r = self.page_run(current, "--main", TEMPLATE, env=env)
        self.assert_page_word(r, "current", 0)
        self.assertEqual(len(r.stdout.splitlines()), 1, "a run without --items printed lines past the verdict:\n" + r.stdout)
        self.assertEqual(self.gh_calls(folder), [], "a run without --items called gh")

    def test_one_open_waits_item_makes_exactly_one_gh_call(self):
        current, _ = self.current_and_behind()
        env, folder = self.gh_env({RUN_ARGV: RUN_DONE})
        r = self.items_run(current, self.items_file([wait_item(154, {"repo": REPO, "run": RUN})]), env)
        self.assert_page_word(r, "current", 0)
        self.assertEqual(self.gh_calls(folder), [RUN_ARGV], "gh calls for one open waits item")

    def test_a_closed_waits_item_makes_no_gh_call_and_prints_no_line(self):
        current, _ = self.current_and_behind()
        env, folder = self.gh_env({RUN_ARGV: RUN_DONE, PR_ARGV: PR_MERGED})
        items = [wait_item(155, {"repo": REPO, "pr": PR}, status="closed"), wait_item(154, {"repo": REPO, "run": RUN})]
        r = self.items_run(current, self.items_file(items), env)
        self.assert_page_word(r, "current", 0)
        self.assertEqual(self.wait_lines(r, 155), [], "the closed item printed a wait line")
        self.assertEqual(self.gh_calls(folder), [RUN_ARGV], "gh calls: the closed item must not be asked, the open one must")

    def test_an_empty_list_or_an_open_item_with_no_waits_makes_no_gh_call(self):
        current, _ = self.current_and_behind()
        cases = {
            "empty list": self.items_file([]),
            "folder with only the marker": self.items_folder([]),
            "open item with no waits": self.items_file([wait_item(3, None)]),
        }
        for label, items in cases.items():
            with self.subTest(label):
                env, folder = self.gh_env({RUN_ARGV: RUN_DONE})
                r = self.items_run(current, items, env)
                self.assert_page_word(r, "current", 0)
                self.assertEqual(len(r.stdout.splitlines()), 1, "printed lines past the verdict:\n" + r.stdout)
                self.assertEqual(self.gh_calls(folder), [], "gh calls")

    def test_full_size_items_make_one_call_per_open_waits_item_and_no_more(self):
        current, _ = self.current_and_behind()
        items, answers, want = [], {}, []
        for i in range(40):  # open, waits on a PR: asked
            pr = 3001 + i
            items.append(wait_item(501 + i, {"repo": REPO, "pr": pr}))
            answers[pr_argv(pr)] = PR_OPEN
            want.append(pr_argv(pr))
        for i in range(40):  # closed, waits on a run: not asked
            items.append(wait_item(601 + i, {"repo": REPO, "run": "8%08d" % i}, status="closed"))
        for i in range(40):  # open, no waits: not asked
            items.append(wait_item(701 + i, None))
        self.assertEqual(len(items), 120)
        env, folder = self.gh_env(answers)
        r = self.items_run(current, self.items_file(items), env)
        self.assert_page_word(r, "current", 0)
        self.assertEqual(sorted(self.gh_calls(folder)), sorted(want), "gh calls for 120 items")
        self.assertEqual(len(r.stdout.splitlines()) - 1, 40, "want one wait line per open waits item:\n" + r.stdout)
        for i in range(40):
            self.assert_wait_line(r, 501 + i, 3001 + i, "waiting")

    def test_the_exit_code_stays_the_verdicts_with_an_ended_wait(self):
        current, behind = self.current_and_behind()
        env, _ = self.gh_env({RUN_ARGV: RUN_DONE})
        items = self.items_file([wait_item(154, {"repo": REPO, "run": RUN})])
        for word, page, code in (("current", current, 0), ("behind", behind, 1)):
            with self.subTest(page=word):
                r = self.items_run(page, items, env)
                self.assert_page_word(r, word, code)
                self.assert_wait_line(r, 154, RUN, "ended")

    def test_a_run_completed_with_failure_names_the_conclusion_in_its_line(self):
        current, _ = self.current_and_behind()
        env, _ = self.gh_env({RUN_ARGV: RUN_DONE})
        r = self.items_run(current, self.items_file([wait_item(154, {"repo": REPO, "run": RUN})]), env)
        self.assert_page_word(r, "current", 0)
        lines = self.wait_lines(r, 154)
        self.assertEqual(len(lines), 1, "want one wait line for item 154:\n" + r.stdout + r.stderr)
        self.assertIn("failure", lines[0], "the wait line does not name the run's conclusion:\n" + lines[0])

    def test_a_run_or_pr_number_is_valid_only_as_a_whole_number_or_digits_without_a_leading_zero(self):
        current, _ = self.current_and_behind()
        valid = [("run", int(RUN), RUN, RUN_ARGV, RUN_DONE, "ended"), ("run", RUN, RUN, RUN_ARGV, RUN_DONE, "ended"),
                 ("pr", PR, PR, PR_ARGV, PR_OPEN, "waiting"), ("pr", str(PR), PR, PR_ARGV, PR_OPEN, "waiting")]
        for kind, value, target, argv, answer, word in valid:
            with self.subTest(valid=(kind, value)):
                env, folder = self.gh_env({argv: answer})
                r = self.items_run(current, self.items_file([wait_item(154, {"repo": REPO, kind: value})]), env)
                self.assert_page_word(r, "current", 0)
                self.assert_wait_line(r, 154, target, word)
                self.assertEqual(self.gh_calls(folder), [argv], "gh calls for a valid %s of %r" % (kind, value))
        for kind in ("run", "pr"):
            for value in ("0", "012", 0, -5, "abc"):
                with self.subTest(malformed=(kind, value)):
                    env, folder = self.gh_env({RUN_ARGV: RUN_DONE, PR_ARGV: PR_OPEN})
                    r = self.items_run(current, self.items_file([wait_item(154, {"repo": REPO, kind: value})]), env)
                    self.assert_page_word(r, "current", 0)
                    lines = self.wait_lines(r, 154)
                    self.assertEqual(len(lines), 1, "want one wait line for item 154:\n" + r.stdout + r.stderr)
                    self.assertRegex(lines[0], r"\bunknown\b", "a malformed %s reads as something other than unknown: %s" % (kind, lines[0]))
                    self.assertEqual(self.gh_calls(folder), [], "gh was called for a malformed %s of %r" % (kind, value))

    def test_an_items_folder_with_no_complete_marker_reads_every_wait_unknown_and_calls_no_gh(self):
        current, behind = self.current_and_behind()
        folder = self.items_folder([wait_item(154, {"repo": REPO, "run": RUN}), wait_item(155, {"repo": REPO, "pr": PR})])
        os.remove(os.path.join(folder, ".complete"))
        for word, page, code in (("current", current, 0), ("behind", behind, 1)):
            with self.subTest(page=word):
                env, calls_folder = self.gh_env({RUN_ARGV: RUN_DONE, PR_ARGV: PR_MERGED})
                r = self.items_run(page, folder, env)
                self.assert_page_word(r, word, code)
                self.assert_wait_line(r, 154, RUN, "unknown")
                self.assert_wait_line(r, 155, PR, "unknown")
                self.assertEqual(self.gh_calls(calls_folder), [], "gh was called for an items folder with no .complete marker")

    def test_fifty_one_open_waits_items_make_exactly_the_cap_of_gh_calls_and_the_last_line_is_unknown(self):
        cap = load_stale_pages().WAIT_CAP
        current, _ = self.current_and_behind()
        items, answers, want = [], {}, []
        for i in range(cap + 1):  # every item waits on an open PR, and gh would answer each one
            pr = 3001 + i
            items.append(wait_item(501 + i, {"repo": REPO, "pr": pr}))
            answers[pr_argv(pr)] = PR_OPEN
            if i < cap:
                want.append(pr_argv(pr))
        env, folder = self.gh_env(answers)
        r = self.items_run(current, self.items_file(items), env)
        self.assert_page_word(r, "current", 0)
        self.assertEqual(self.gh_calls(folder), want, "gh calls for %d open waits items" % (cap + 1))
        self.assert_wait_line(r, 501 + cap - 1, 3001 + cap - 1, "waiting")
        self.assert_wait_line(r, 501 + cap, 3001 + cap, "unknown")

    # An item on a lane (`lane` set): an open one with `lastAnswer` and no `waits` prints one lane line, built from the item
    # alone, so the writer sees a wait that never ends. An item with `waits` keeps its one gh line. A closed item, and one
    # with `lane` but no `lastAnswer` (a question still open on a busy lane), prints nothing.

    def lane_item(self, n, status="open", last_answer=True, waits=None):
        """An item on lane LANE: `lane` set, and `lastAnswer` set unless `last_answer` is False."""
        item = wait_item(n, waits, status=status)
        item["lane"] = LANE
        if last_answer:
            item["lastAnswer"] = {"choice": "a", "note": "", "at": ANSWERED}
        return item

    def lane_item_with(self, n, answer):
        """An open item on lane LANE whose `lastAnswer` is `answer`, as given."""
        item = self.lane_item(n, last_answer=False)
        item["lastAnswer"] = answer
        return item

    def test_an_open_lane_item_with_a_last_answer_and_no_waits_prints_one_lane_line(self):
        current, _ = self.current_and_behind()
        for as_folder in (False, True):
            with self.subTest("folder of <id>.json files" if as_folder else "list file"):
                env, _ = self.gh_env({})
                items = self.items_folder([self.lane_item(154)]) if as_folder else self.items_file([self.lane_item(154)])
                r = self.items_run(current, items, env)
                self.assert_page_word(r, "current", 0)
                self.assertEqual(r.stdout.splitlines()[1:], [lane_line(154)],
                                 "the lane line for item 154 is missing or differs:\n" + r.stdout + r.stderr)

    def test_the_lane_line_starts_no_gh_process(self):
        current, _ = self.current_and_behind()
        env, folder = self.gh_env({RUN_ARGV: RUN_DONE})
        r = self.items_run(current, self.items_file([self.lane_item(154)]), env)
        self.assert_page_word(r, "current", 0)
        self.assertEqual(r.stdout.splitlines()[1:], [lane_line(154)],
                         "the lane line for item 154 is missing or differs:\n" + r.stdout + r.stderr)
        self.assertEqual(self.gh_calls(folder), [], "gh was called for an item with lane and lastAnswer and no waits")

    def test_an_item_with_lane_and_waits_keeps_its_one_gh_line_and_adds_no_lane_line(self):
        current, _ = self.current_and_behind()
        env, folder = self.gh_env({RUN_ARGV: RUN_DONE})
        r = self.items_run(current, self.items_file([self.lane_item(154, waits={"repo": REPO, "run": RUN})]), env)
        self.assert_page_word(r, "current", 0)
        self.assertEqual(len(r.stdout.splitlines()) - 1, 1,
                         "want one wait line after the verdict line, not a lane line as well:\n" + r.stdout + r.stderr)
        self.assert_wait_line(r, 154, RUN, "ended")
        self.assertEqual(self.gh_calls(folder), [RUN_ARGV], "gh calls for an item with lane and waits")

    def test_a_closed_lane_item_prints_no_line_and_calls_no_gh(self):
        current, _ = self.current_and_behind()
        env, folder = self.gh_env({RUN_ARGV: RUN_DONE})
        r = self.items_run(current, self.items_file([self.lane_item(154, status="closed")]), env)
        self.assert_page_word(r, "current", 0)
        self.assertEqual(len(r.stdout.splitlines()), 1, "a closed lane item printed a line past the verdict:\n" + r.stdout)
        self.assertEqual(self.gh_calls(folder), [], "gh was called for a closed lane item")

    def test_a_lane_item_with_no_last_answer_prints_no_line_and_calls_no_gh(self):
        current, _ = self.current_and_behind()
        env, folder = self.gh_env({RUN_ARGV: RUN_DONE})
        r = self.items_run(current, self.items_file([self.lane_item(154, last_answer=False)]), env)
        self.assert_page_word(r, "current", 0)
        self.assertEqual(len(r.stdout.splitlines()), 1, "a lane item with no lastAnswer printed a line past the verdict:\n" + r.stdout)
        self.assertEqual(self.gh_calls(folder), [], "gh was called for a lane item with no lastAnswer")

    def test_full_size_lane_items_print_a_line_only_for_the_open_ones_with_a_last_answer(self):
        current, _ = self.current_and_behind()
        items = [self.lane_item(801 + i) for i in range(40)]  # open, lastAnswer: one line each
        items += [self.lane_item(901 + i, status="closed") for i in range(40)]  # closed: none
        items += [self.lane_item(951 + i, last_answer=False) for i in range(40)]  # open, no lastAnswer: none
        self.assertEqual(len(items), 120)
        env, folder = self.gh_env({})
        r = self.items_run(current, self.items_file(items), env)
        self.assert_page_word(r, "current", 0)
        self.assertEqual(r.stdout.splitlines()[1:], [lane_line(801 + i) for i in range(40)],
                         "the lane lines for 120 items differ from the 40 open items with a lastAnswer:\n" + r.stdout)
        self.assertEqual(self.gh_calls(folder), [], "gh was called for lane items with no waits")

    def test_a_lane_line_whose_answer_has_no_usable_at_reads_answered_at_unknown_and_never_none_or_a_number(self):
        current, _ = self.current_and_behind()
        cases = (("no at key", {"choice": "a", "note": ""}),
                 ("at null", {"choice": "a", "note": "", "at": None}),
                 ("at a whole number", {"choice": "a", "note": "", "at": 1762264589}),
                 ("at a float", {"choice": "a", "note": "", "at": 1762264589.5}))
        for label, answer in cases:
            with self.subTest(case=label):
                env, folder = self.gh_env({})
                r = self.items_run(current, self.items_file([self.lane_item_with(154, answer)]), env)
                self.assert_page_word(r, "current", 0)
                self.assertEqual(r.stdout.splitlines()[1:], [lane_line_unknown(154)],
                                 "the lane line for item 154 with %s is not the unknown line:\n%s" % (label, r.stdout + r.stderr))
                self.assertEqual(self.gh_calls(folder), [], "gh was called for a lane item with %s" % label)

    def entry_key_forms(self):
        """Two forms of an item with no `n` and no `id`: a waits item (gh) and a lane item (no gh call). Each is a builder of the item."""
        return (("waits item", lambda: wait_item(154, {"repo": REPO, "run": RUN})),
                ("lane item", lambda: self.lane_item(154, waits=None)))

    # The doc key is the item id (roadmap step page-item-id-check).
    def test_a_wait_line_for_an_item_with_no_n_and_no_id_names_its_entry_key(self):
        """The entry key is the item's id, so a wait line names it when the item has no `n` and no `id` field. Red on the old
        code, which names the item ? from the missing fields. Both forms: a `waits` item (gh) and a lane item (no gh call)."""
        current, _ = self.current_and_behind()
        for label, make in self.entry_key_forms():
            with self.subTest(label):
                env, _ = self.gh_env({RUN_ARGV: RUN_DONE})
                item = make()
                del item["n"], item["id"]
                r = self.items_run(current, self.items_folder([item], keys=["entry-key-154"]), env)
                self.assert_page_word(r, "current", 0)
                lines = r.stdout.splitlines()[1:]
                self.assertEqual(len(lines), 1, "want one wait line for the item, got %d:\n%s" % (len(lines), r.stdout + r.stderr))
                self.assertIn("item entry-key-154", lines[0], "the wait line is not labelled by its entry key:\n" + lines[0])

    def test_a_wait_line_for_a_list_row_with_no_n_and_no_id_names_its_entry_key(self):
        """A --items list file holds the rows ArtifactData list returns, {"id", "data"}. The entry key is the item's id, so a wait
        line names the item in `data` by its key when that item has no `n` and no `id` field. Red on the old code, which reads
        the row itself as the item: it finds no waits and no lane, so it prints nothing."""
        current, _ = self.current_and_behind()
        for label, make in self.entry_key_forms():
            with self.subTest(label):
                env, _ = self.gh_env({RUN_ARGV: RUN_DONE})
                item = make()
                del item["n"], item["id"]
                r = self.items_run(current, self.items_file([{"id": "entry-key-154", "data": item}]), env)
                self.assert_page_word(r, "current", 0)
                lines = r.stdout.splitlines()[1:]
                self.assertEqual(len(lines), 1, "want one wait line for the row, got %d:\n%s" % (len(lines), r.stdout + r.stderr))
                self.assertIn("item entry-key-154", lines[0], "the wait line is not labelled by its entry key:\n" + lines[0])
                self.assertNotIn("item ?", r.stdout, "a wait line names the item ?:\n" + r.stdout)

    def test_a_wait_line_names_the_entry_key_when_the_id_field_differs(self):
        """The entry key is the item's id, so a wait line names the item by its key when the item's own `id` field names another
        item. Both shapes: a folder doc, and a list row {"id", "data"}. Both forms: a `waits` item (gh) and a lane item (no gh call).
        Red on the merged code, which names the item by that field: `item other-id`, not `item entry-key-154`."""
        current, _ = self.current_and_behind()
        shapes = (("folder doc", lambda item: self.items_folder([item], keys=["entry-key-154"])),
                  ("list row", lambda item: self.items_file([{"id": "entry-key-154", "data": item}])))
        for shape, arg in shapes:
            for label, make in self.entry_key_forms():
                with self.subTest(shape=shape, form=label):
                    env, _ = self.gh_env({RUN_ARGV: RUN_DONE})
                    item = make()
                    del item["n"]
                    item["id"] = "other-id"
                    r = self.items_run(current, arg(item), env)
                    self.assert_page_word(r, "current", 0)
                    lines = r.stdout.splitlines()[1:]
                    self.assertEqual(len(lines), 1, "want one wait line for the item, got %d:\n%s" % (len(lines), r.stdout + r.stderr))
                    self.assertIn("item entry-key-154", lines[0], "the wait line is not labelled by its entry key:\n" + lines[0])

    # Single-page mode with --answers <file or folder>, with --items: one kept-answer line per answer kept on a closed item.
    # Each do-not-flag case also holds the incident item (item 356), so the run's own incident line shows the answers were
    # read before the negative is checked. An open item, an arbiter ruling and a park answer are legitimate states: never named.

    def shaped(self, items, answers, as_folder):
        """(--items arg, --answers arg) in one shape: a list file each, or a folder each. `answers` is (doc id, data) pairs. The list
        file holds each doc's data alone, as a list gives it; the folder names each doc by its id."""
        if as_folder:
            return self.items_folder(items), self.docs_folder(dict(answers), "answers")
        return self.items_file(items), self.list_file([data for _, data in answers], "answers")

    def paired_run(self, extra_items, extra_answers, as_folder):
        """A run with the incident item and its kept answer, plus `extra_items` and `extra_answers` ((doc id, data) pairs)."""
        current, _ = self.current_and_behind()
        items, answers = self.shaped([INCIDENT, *extra_items], [(INCIDENT_ID, INCIDENT_ANSWER), *extra_answers], as_folder)
        return self.items_run(current, items, {}, answers=answers)

    def assert_kept_line(self, r, n, item_id, want=None):
        """Exactly one kept-answer line names item `n` (id `item_id`), and it starts with `want`, the line the flag prints by default.
        Returns that line."""
        want = kept_line(n, item_id) if want is None else want
        named = [line for line in kept_lines(r.stdout) if line.startswith("kept-answer: item %d (%s)" % (n, item_id))]
        self.assertEqual(len(named), 1, "want one kept-answer line for item %d (%s), got %d:\n%s"
                         % (n, item_id, len(named), r.stdout + r.stderr))
        self.assertTrue(named[0].startswith(want), "the kept-answer line for item %d differs:\n%s" % (n, named[0]))
        return named[0]

    def assert_not_named(self, r, item_id, case):
        """The run read the incident's answer first (the scope), and no kept-answer line names `item_id`, which is `case`."""
        self.assert_kept_line(r, INCIDENT_N, INCIDENT_ID)
        named = [line for line in kept_lines(r.stdout) if item_id in line]
        self.assertEqual(named, [], "%s is named as a kept answer:\n%s" % (case, r.stdout + r.stderr))

    def test_a_kept_answer_on_a_closed_item_is_named_in_both_shapes(self):
        current, _ = self.current_and_behind()
        for as_folder in (False, True):
            with self.subTest("folder of <id>.json files" if as_folder else "list file"):
                items, answers = self.shaped([INCIDENT], [(INCIDENT_ID, INCIDENT_ANSWER)], as_folder)
                r = self.items_run(current, items, {}, answers=answers)
                self.assert_kept_line(r, INCIDENT_N, INCIDENT_ID)
                self.assert_page_word(r, "current", 0)

    def test_a_closed_item_with_a_last_answer_and_a_kept_answer_is_named(self):
        # Route and close, step 2, deletes the answer when it closes the item. A kept answer on a closed item is a missed delete,
        # whether or not the close also wrote lastAnswer.
        current, _ = self.current_and_behind()
        item = decision_item(INCIDENT_N, INCIDENT_ID, lastAnswer={"choice": "a", "note": "x", "at": ANSWER_AT})
        for as_folder in (False, True):
            with self.subTest("folder of <id>.json files" if as_folder else "list file"):
                items, answers = self.shaped([item], [(INCIDENT_ID, INCIDENT_ANSWER)], as_folder)
                r = self.items_run(current, items, {}, answers=answers)
                self.assert_kept_line(r, INCIDENT_N, INCIDENT_ID)
                self.assert_page_word(r, "current", 0)

    def assert_not_named_in_both_shapes(self, extra_items, extra_answers, item_id, case):
        for as_folder in (False, True):
            with self.subTest("folder of <id>.json files" if as_folder else "list file", case=case):
                r = self.paired_run(extra_items, extra_answers, as_folder)
                self.assert_not_named(r, item_id, case)

    def test_an_open_item_with_a_kept_answer_is_not_named(self):
        self.assert_not_named_in_both_shapes([decision_item(357, "open-answer", status="open")],
                                             [("open-answer", answer_for("open-answer", 357))],
                                             "open-answer", "an open item (status open) with a kept answer")

    def test_an_item_with_no_status_key_and_a_kept_answer_is_not_named(self):
        self.assert_not_named_in_both_shapes([decision_item(358, "no-status-answer", status=None)],
                                             [("no-status-answer", answer_for("no-status-answer", 358))],
                                             "no-status-answer", "an item with no status key and a kept answer")

    def test_an_open_busy_lane_item_with_a_last_answer_and_a_kept_answer_is_not_named(self):
        item = decision_item(359, "lane-answer", status="open", lane=LANE, lastAnswer={"choice": "a", "note": "x", "at": ANSWER_AT})
        self.assert_not_named_in_both_shapes([item], [("lane-answer", answer_for("lane-answer", 359))],
                                             "lane-answer", "an open busy-lane item with a last answer and a kept answer")

    def test_a_closed_arbiter_ruling_with_an_overturn_answer_is_not_named(self):
        self.assert_not_named_in_both_shapes([decision_item(360, "ruling-answer", arbiter=True, pick="a")],
                                             [("ruling-answer", answer_for("ruling-answer", 360, choice="overturn", note="reopen"))],
                                             "ruling-answer", "a closed arbiter ruling with an overturn answer")

    def test_a_park_line_answer_under_park_dot_id_on_a_closed_item_is_not_named(self):
        # The list shape holds no key, so the park line's `id` equals the closed item's id: only its `parked` field keeps it unnamed.
        park = {"parked": True, "id": "parked-entry", "act": "unpark", "ref": "Round 2: the parked line", "note": "back to work", "at": ANSWER_AT}
        self.assert_not_named_in_both_shapes([decision_item(361, "parked-entry")], [("park.parked-entry", park)],
                                             "parked-entry", "a park.<id> answer on a closed item")

    def test_an_item_park_answer_on_a_closed_item_is_not_named(self):
        item = decision_item(362, "parked-item", lastAnswer={"act": "park", "note": "later", "at": ANSWER_AT})
        park = {"item": "parked-item", "n": 362, "act": "park", "note": "later", "at": ANSWER_AT}
        self.assert_not_named_in_both_shapes([item], [("parked-item", park)], "parked-item", "an item park answer on a closed item")

    def test_an_answer_with_no_matching_item_is_not_named(self):
        self.assert_not_named_in_both_shapes([], [("orphan-answer", answer_for("orphan-answer", 363))],
                                             "orphan-answer", "an answer with no matching item")

    def test_the_kept_answer_line_comes_after_the_wait_and_lane_lines(self):
        current, _ = self.current_and_behind()
        env, _ = self.gh_env({RUN_ARGV: RUN_DONE})
        items, answers = self.shaped([INCIDENT, wait_item(154, {"repo": REPO, "run": RUN}), self.lane_item(155)],
                                     [(INCIDENT_ID, INCIDENT_ANSWER)], as_folder=False)
        r = self.items_run(current, items, env, answers=answers)
        self.assert_kept_line(r, INCIDENT_N, INCIDENT_ID)
        lines = r.stdout.splitlines()
        self.assertEqual(len(lines), 4, "want the verdict, the wait line, the lane line and the kept-answer line:\n" + r.stdout + r.stderr)
        self.assertTrue(lines[1].startswith("wait: item 154 ") and lines[2].startswith("wait: item 155 "),
                        "the wait and lane lines are not right after the verdict line:\n" + r.stdout)
        self.assert_page_word(r, "current", 0)

    def test_a_behind_page_keeps_exit_1_and_still_prints_the_kept_answer_line(self):
        _, behind = self.current_and_behind()
        items, answers = self.shaped([INCIDENT], [(INCIDENT_ID, INCIDENT_ANSWER)], as_folder=False)
        r = self.items_run(behind, items, {}, answers=answers)
        self.assert_kept_line(r, INCIDENT_N, INCIDENT_ID)
        self.assert_page_word(r, "behind", 1)

    def test_without_answers_the_output_is_the_verdict_line_alone(self):
        # Control: the answer is kept on disk, but the run is not given --answers, so it must print no kept-answer line.
        current, _ = self.current_and_behind()
        self.list_file([INCIDENT_ANSWER], "answers")
        r = self.items_run(current, self.items_file([INCIDENT]), {})
        self.assert_page_word(r, "current", 0)
        self.assertEqual(r.stdout.splitlines(), [self.page_line(r)], "a run without --answers printed lines past the verdict:\n" + r.stdout)

    def test_full_size_kept_answers_name_only_the_closed_items_in_order(self):
        current, _ = self.current_and_behind()
        items, answers, want = [], [], []
        for i in range(40):  # closed, answer kept: named, in item order
            item_id = "incident-%03d" % i
            items.append(decision_item(1000 + i, item_id))
            answers.append((item_id, answer_for(item_id, 1000 + i)))
            want.append(kept_line(1000 + i, item_id))
        for i in range(40):  # open, answer kept: not named
            item_id = "open-%03d" % i
            items.append(decision_item(1100 + i, item_id, status="open"))
            answers.append((item_id, answer_for(item_id, 1100 + i)))
        for i in range(40):  # arbiter ruling, overturn kept: not named
            item_id = "ruling-%03d" % i
            items.append(decision_item(1200 + i, item_id, arbiter=True))
            answers.append((item_id, answer_for(item_id, 1200 + i, choice="overturn")))
        for i in range(40):  # closed, no answer: not named
            items.append(decision_item(1300 + i, "quiet-%03d" % i))
        self.assertEqual(len(items), 160)
        for as_folder in (False, True):
            with self.subTest("folder of <id>.json files" if as_folder else "list file"):
                items_arg, answers_arg = self.shaped(items, answers, as_folder)
                r = self.items_run(current, items_arg, {}, answers=answers_arg)
                got = kept_lines(r.stdout)
                self.assertEqual(len(got), 40, "want 40 kept-answer lines, one per closed item with a kept answer, got %d:\n%s"
                                 % (len(got), r.stdout + r.stderr))
                for line, prefix in zip(got, want):
                    self.assertTrue(line.startswith(prefix), "a kept-answer line is not the one for its item, in item order:\n" + line)
                self.assert_page_word(r, "current", 0)

    def test_an_empty_answers_list_or_folder_prints_no_kept_answer_line(self):
        current, _ = self.current_and_behind()
        items = self.items_file([INCIDENT])  # closed, no answer on file
        cases = (("empty list file", self.list_file([], "answers")), ("folder with only the marker", self.docs_folder({}, "answers")))
        for label, answers in cases:
            with self.subTest(label):
                r = self.items_run(current, items, {}, answers=answers)
                self.assert_page_word(r, "current", 0)
                self.assertEqual(kept_lines(r.stdout), [], "an empty --answers printed a kept-answer line:\n" + r.stdout)

    def test_an_unreadable_answers_file_prints_one_unknown_line_and_keeps_the_exit_code(self):
        current, _ = self.current_and_behind()
        items = self.items_file([INCIDENT])
        cases = (("malformed JSON", "[{"), ("a JSON object, not a list", "{}"))
        for label, text in cases:
            with self.subTest(label):
                path = write_text(os.path.join(tempfile.mkdtemp(dir=self.tmp.name, prefix="answers-"), "answers.json"), text)
                r = self.items_run(current, items, {}, answers=path)
                unknown = [line for line in r.stdout.splitlines()[1:] if "unknown" in line]
                self.assertEqual(len(unknown), 1, "an unreadable --answers file prints no single unknown line:\n" + r.stdout + r.stderr)
                self.assertNotIn("Traceback", r.stdout + r.stderr)
                self.assert_page_word(r, "current", 0)

    def test_an_items_folder_with_no_complete_marker_prints_one_unknown_kept_answer_line_and_no_item_line(self):
        # The items list may be cut short, so a closed status in it is not proof: one unknown line, and no item line.
        current, _ = self.current_and_behind()
        items = self.docs_folder({INCIDENT_ID: INCIDENT}, "items")
        os.remove(os.path.join(items, ".complete"))
        answer_shapes = (("list file", self.list_file([INCIDENT_ANSWER], "answers")),
                         ("folder of <id>.json files", self.docs_folder({INCIDENT_ID: INCIDENT_ANSWER}, "answers")))
        for label, answers in answer_shapes:
            with self.subTest(label):
                r = self.items_run(current, items, {}, answers=answers)
                unknown = [line for line in kept_lines(r.stdout) if line.startswith("kept-answer: unknown")]
                self.assertEqual(len(unknown), 1, "want one kept-answer: unknown line for an items folder with no marker, got %d:\n%s"
                                 % (len(unknown), r.stdout + r.stderr))
                self.assertIn("the items folder", unknown[0], "the unknown line does not name the items folder:\n" + unknown[0])
                named = [line for line in kept_lines(r.stdout) if not line.startswith("kept-answer: unknown")]
                self.assertEqual(named, [], "an items folder with no marker still names an item:\n" + r.stdout)
                self.assert_page_word(r, "current", 0)

    def test_pin_an_answers_folder_with_no_complete_marker_prints_one_unknown_kept_answer_line(self):
        # Pin: an answers folder with no marker may be cut short, so it reads as one unknown kept-answer line and names no item.
        current, _ = self.current_and_behind()
        items = self.items_file([INCIDENT])
        answers = self.docs_folder({INCIDENT_ID: INCIDENT_ANSWER}, "answers")
        os.remove(os.path.join(answers, ".complete"))
        r = self.items_run(current, items, {}, answers=answers)
        kept = kept_lines(r.stdout)
        self.assertEqual(len(kept), 1, "want exactly one kept-answer line for an answers folder with no marker, got %d:\n%s"
                         % (len(kept), r.stdout + r.stderr))
        self.assertTrue(kept[0].startswith("kept-answer: unknown"), "the one kept-answer line is not the unknown line:\n" + kept[0])
        self.assertIn("the answers folder", kept[0], "the unknown line does not name the answers folder:\n" + kept[0])
        self.assert_page_word(r, "current", 0)

    def test_the_unknown_kept_answer_line_names_the_folder_with_no_marker(self):
        # The unknown line says which folder may be cut short: "items" for an items folder, "answers" for an answers folder.
        current, _ = self.current_and_behind()
        items = self.docs_folder({INCIDENT_ID: INCIDENT}, "items")
        os.remove(os.path.join(items, ".complete"))
        answers = self.docs_folder({INCIDENT_ID: INCIDENT_ANSWER}, "answers")
        os.remove(os.path.join(answers, ".complete"))
        cases = (("items folder with no marker", items, self.list_file([INCIDENT_ANSWER], "answers"), "items"),
                 ("answers folder with no marker", self.items_file([INCIDENT]), answers, "answers"))
        for label, items_arg, answers_arg, folder in cases:
            with self.subTest(label):
                r = self.items_run(current, items_arg, {}, answers=answers_arg)
                self.assert_page_word(r, "current", 0)
                unknown = kept_lines(r.stdout)
                self.assertEqual(len(unknown), 1, "want one kept-answer line:\n" + r.stdout + r.stderr)
                self.assertIn("the %s folder" % folder, unknown[0],
                              "the unknown line does not name the %s folder:\n%s" % (folder, unknown[0]))

    def test_an_items_folder_doc_with_no_id_field_is_matched_by_its_file_name_and_still_flagged(self):
        # export_page.docs_in keys each folder doc by its file name without .json, so the file name is the doc id.
        current, _ = self.current_and_behind()
        no_id = {key: value for key, value in INCIDENT.items() if key != "id"}
        items = self.docs_folder({INCIDENT_ID: no_id}, "items")
        answers = self.docs_folder({INCIDENT_ID: INCIDENT_ANSWER}, "answers")
        r = self.items_run(current, items, {}, answers=answers)
        self.assert_kept_line(r, INCIDENT_N, INCIDENT_ID)
        self.assert_page_word(r, "current", 0)

    # A closed item with `waits` and a kept answer: a page answer is kept during a wait, a chat answer then closes the item, and no
    # wait line ever ends it (wait lines cover open items only, SKILL.md "Route and close"). It gets one line, which says to delete
    # answers/<id> only when its wait has ended.

    def assert_waits_kept_line(self, r, n, item_id):
        """Exactly one kept-answer line names closed item `n` (id `item_id`) with waits, and it starts with the waits line. A line
        that says to delete answers/<id> also says when its wait has ended."""
        line = self.assert_kept_line(r, n, item_id, want=waits_kept_line(n, item_id))
        if "delete" in line:
            self.assertIn("when its wait", line, "the line says to delete answers/%s before its wait has ended:\n%s" % (item_id, line))

    def test_a_closed_item_with_waits_and_a_kept_answer_gets_one_waits_line_in_both_shapes(self):
        current, _ = self.current_and_behind()
        for label, waits in (("a run", {"repo": REPO, "run": RUN}), ("a PR", {"repo": REPO, "pr": PR}), ("a malformed value", "soon")):
            for as_folder in (False, True):
                with self.subTest(label, folder=as_folder):
                    waited = decision_item(364, "waits-kept", waits=waits)
                    answer = ("waits-kept", answer_for("waits-kept", 364))
                    items, answers = self.shaped([INCIDENT, waited], [(INCIDENT_ID, INCIDENT_ANSWER), answer], as_folder)
                    r = self.items_run(current, items, {}, answers=answers)
                    self.assert_kept_line(r, INCIDENT_N, INCIDENT_ID)  # the scope: the run read the answers before the subject is checked
                    self.assert_waits_kept_line(r, 364, "waits-kept")
                    self.assert_page_word(r, "current", 0)

    def test_full_size_closed_waits_items_get_one_line_each_only_when_their_answer_is_kept(self):
        current, _ = self.current_and_behind()
        items, answers, want = [], [], []
        for i in range(40):  # closed with waits, answer kept: one line each, in item order
            item_id, n = "waits-kept-%03d" % i, 1400 + i
            items.append(decision_item(n, item_id, waits={"repo": REPO, "run": RUN} if i % 2 else {"repo": REPO, "pr": PR}))
            answers.append((item_id, answer_for(item_id, n)))
            want.append(waits_kept_line(n, item_id))
        for i in range(40):  # closed with waits, no answer: no line
            items.append(decision_item(1500 + i, "waits-quiet-%03d" % i, waits={"repo": REPO, "run": RUN}))
        self.assertEqual(len(items), 80)
        for as_folder in (False, True):
            with self.subTest("folder of <id>.json files" if as_folder else "list file"):
                env, folder = self.gh_env({})
                items_arg, answers_arg = self.shaped(items, answers, as_folder)
                r = self.items_run(current, items_arg, env, answers=answers_arg)
                got = kept_lines(r.stdout)
                self.assertEqual(len(got), 40, "want 40 kept-answer lines, one per closed item with waits and a kept answer, got %d:\n%s"
                                 % (len(got), r.stdout + r.stderr))
                for line, prefix in zip(got, want):
                    self.assertTrue(line.startswith(prefix), "a kept-answer line is not the waits line for its item, in item order:\n" + line)
                self.assert_page_word(r, "current", 0)
                self.assertEqual(self.gh_calls(folder), [], "gh was called for a closed item")

    def test_a_list_of_id_and_data_entries_names_the_incident_in_both_lists(self):
        # The shape parked_mode reads and the store's list returns: one {"id", "data"} entry per doc. The list of bare data objects
        # is the control beside it: a pin that it keeps working.
        current, _ = self.current_and_behind()
        shapes = (("entries", [{"id": INCIDENT_ID, "data": INCIDENT}], [{"id": INCIDENT_ID, "data": INCIDENT_ANSWER}]),
                  ("bare data", [INCIDENT], [INCIDENT_ANSWER]))
        for label, items_docs, answer_docs in shapes:
            with self.subTest(label):
                items = self.list_file(items_docs, "items")
                answers = self.list_file(answer_docs, "answers")
                r = self.items_run(current, items, {}, answers=answers)
                self.assert_kept_line(r, INCIDENT_N, INCIDENT_ID)
                self.assert_page_word(r, "current", 0)

    def test_items_with_answers_starts_no_more_gh_processes_than_items_alone(self):
        # Cost: --answers reads files only. The run that prints the closed-with-waits line starts no gh process beyond the ones
        # --items alone starts for the same items.
        current, _ = self.current_and_behind()
        items = [wait_item(154, {"repo": REPO, "run": RUN}), wait_item(155, {"repo": REPO, "pr": PR}),
                 decision_item(INCIDENT_N, INCIDENT_ID), decision_item(365, "waits-kept", waits={"repo": REPO, "run": RUN})]
        answers = [(INCIDENT_ID, INCIDENT_ANSWER), ("waits-kept", answer_for("waits-kept", 365))]
        gh_answers = {RUN_ARGV: RUN_DONE, PR_ARGV: PR_OPEN}
        env, alone_folder = self.gh_env(gh_answers)
        r_alone = self.items_run(current, self.items_file(items), env)
        self.assert_page_word(r_alone, "current", 0)
        env, both_folder = self.gh_env(gh_answers)
        items_arg, answers_arg = self.shaped(items, answers, as_folder=False)
        r_both = self.items_run(current, items_arg, env, answers=answers_arg)
        self.assert_waits_kept_line(r_both, 365, "waits-kept")  # the scope: the path whose gh calls are counted prints its line
        self.assert_page_word(r_both, "current", 0)
        alone, both = self.gh_calls(alone_folder), self.gh_calls(both_folder)
        self.assertGreaterEqual(len(alone), 2, "the items-alone run did not start the gh processes its open waits need: %s" % alone)
        self.assertLessEqual(len(both), len(alone), "--answers started more gh processes than --items alone:\n%s" % both)


# Fixtures for the --items cases: a repo, a run that ended completed/failure, and the PR that run checked.
REPO, RUN, PR = "shivinate7/q_max", "41861801325", 1011
RUN_ARGV = "run view %s --repo %s --json status,conclusion" % (RUN, REPO)


def pr_argv(pr):
    return "pr view %d --repo %s --json state,mergedAt" % (pr, REPO)


PR_ARGV = pr_argv(PR)
RUN_DONE = [0, '{"status":"completed","conclusion":"failure"}']
RUN_IN_PROGRESS = [0, '{"status":"in_progress","conclusion":""}']
PR_OPEN = [0, '{"state":"OPEN","mergedAt":null}']
PR_CLOSED = [0, '{"state":"CLOSED","mergedAt":null}']
PR_MERGED = [0, '{"state":"MERGED","mergedAt":"2026-11-04T21:10:00Z"}']
WAIT_WORDS = {"ended", "waiting", "unknown"}
# The gh stand-in: answers by its full argv, logs each argv to calls.txt beside itself, and fails on any argv it does not know.
GH_STUB = '''#!@PYTHON@
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
argv = " ".join(sys.argv[1:])
with open(os.path.join(HERE, "calls.txt"), "a", encoding="utf-8") as f:
    f.write(argv + "\\n")
with open(os.path.join(HERE, "answers.json"), encoding="utf-8") as f:
    answers = json.load(f)
if argv not in answers:
    sys.stderr.write("UNEXPECTED gh call: %s\\n" % argv)
    sys.exit(3)
code, out = answers[argv]
sys.stdout.write(out)
sys.exit(code)
'''
# The gh on PATH: logs its call with a PATH prefix, so a run that ignores WAITING_PAGE_GH shows in the calls.
GH_LOG = '''#!@PYTHON@
import sys
open(@LOG@, "a", encoding="utf-8").write("PATH " + " ".join(sys.argv[1:]) + "\\n")
sys.exit(3)
'''


def wait_item(n, waits, status="open"):
    """An item record as the page holds it. `waits` is its waits field, or None for an item with none."""
    item = {"id": "item-%d" % n, "n": n, "kind": "task", "status": status, "title": "CI fix"}
    if waits is not None:
        item["waits"] = waits
    return item


LANE, ANSWERED = "owner-word-relay", "2026-11-04T13:56:29.078Z"  # a lane's slug, and the lastAnswer.at of an item on it


def lane_line(n):
    """The line an open item on a lane with a lastAnswer prints: `wait: item <n> (lane <slug>): waiting (answered <at>)`."""
    return "wait: item %d (lane %s): waiting (answered %s)" % (n, LANE, ANSWERED)


def lane_line_unknown(n):
    """The line an open item on a lane prints when its lastAnswer has no usable `at`: the same line, `answered at unknown`."""
    return "wait: item %d (lane %s): waiting (answered at unknown)" % (n, LANE)


# Fixtures for the --answers cases. An answer doc names its item in `item` (the list shape has no doc id), and a park line
# names its entry in `id`. A line is the one the flag prints for a kept answer on a closed item.
ANSWER_AT, ITEM_ADDED = "2026-11-07T19:41:50.035Z", "2026-11-07T19:33:00Z"


def decision_item(n, item_id, status="closed", **extra):
    """A decision item as the page holds it: `status` (None: no status key), and the `extra` fields added."""
    item = {"id": item_id, "n": n, "kind": "decision", "added": ITEM_ADDED, "options": [{"key": "a"}, {"key": "b"}]}
    if status is not None:
        item["status"] = status
    item.update(extra)
    return item


def answer_for(item_id, n, **extra):
    """The answer doc the page writes at answers/<item id>: a choice and a note, with the `extra` fields replacing any."""
    doc = {"item": item_id, "n": n, "choice": "a", "at": ANSWER_AT, "note": "x"}
    doc.update(extra)
    return doc


def kept_line(n, item_id):
    """The line the flag prints for a kept answer on closed item `n` (id `item_id`). A remedy may follow it."""
    return "kept-answer: item %d (%s) is closed and answers/%s is kept" % (n, item_id, item_id)


def waits_kept_line(n, item_id):
    """The line the flag prints for a kept answer on closed item `n` (id `item_id`) that still has `waits`. A remedy may follow it."""
    return "kept-answer: item %d (%s) is closed with waits and answers/%s is kept" % (n, item_id, item_id)


def kept_lines(out):
    """The lines of `out` that start as a kept-answer line does."""
    return [line for line in out.splitlines() if line.startswith("kept-answer:")]


INCIDENT_N, INCIDENT_ID = 356, "round3-fail-holds"  # the incident: a closed decision whose answer was kept
INCIDENT = decision_item(INCIDENT_N, INCIDENT_ID)
INCIDENT_ANSWER = answer_for(INCIDENT_ID, INCIDENT_N)


def load_stale_pages():
    """stale_pages.py as a module, loaded from CMD, so the unit checks run the function the script runs."""
    if HERE not in sys.path:
        sys.path.insert(0, HERE)  # the script imports splice from its own folder
    spec = importlib.util.spec_from_file_location("stale_pages_under_test", CMD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CarriesData(unittest.TestCase):
    """carries_data is False for a live page whose parts all match the template's. The title is one of those parts."""

    def test_an_untouched_page_titled_with_the_old_name_carries_no_data(self):
        stale = load_stale_pages()
        untouched = with_title(PAGE, "Queue")
        self.assertNotEqual(untouched, PAGE, "the fixture kept the template's title")
        self.assertFalse(stale.carries_data(PAGE, untouched), "an untouched page titled Queue counts as carrying data")

    def test_an_identical_page_carries_no_data(self):
        self.assertFalse(load_stale_pages().carries_data(PAGE, PAGE), "the template counts as carrying data")

    def test_a_changed_mockup_carries_data(self):
        self.assertTrue(load_stale_pages().carries_data(PAGE, set_body(PAGE, MOCK_BODY)), "a live mockup is not counted as data")


# --parked: the on-demand pass over the parked block (waiting-page SKILL.md, the parked branch). It reads three saved
# files in one folder and writes none. Each list file holds [{"id", "data"}] entries, the shape an ArtifactData list
# returns for a collection (one entry per doc). meta.json holds the data of meta/page alone, not an entry:
#   meta.json     {"writer": ..., "parked": [{"id", "ref", "note"}, ...]}
#   items.json    [{"id": "<item id>", "data": {"status": "open" | "closed", ...}}, ...]
#   answers.json  [{"id": "park.<item id>", "data": {"parked", "id", "act", "ref", "note", "at"}}, ...]   a parked line's answer
#                 [{"id": "<item id>", "data": {"item", "n", "at", "act": "park", "note"}}, ...]          a Park press on a card
# One line per stale thing, then exit 1: `parked-open <id>` for a parked entry whose item is open, and
# `park-answer-old <key>` for a park answer (either key form) whose `at` is more than 10 minutes before --now. With none,
# `parked: clean` and exit 0. An answer whose act is not park is never read. A file of the wrong shape (items or answers
# not a list, meta not a dict), or a park answer with no readable `at`, prints `unknown: <what>` and exits 2: the mode
# never calls such a thing clean or stale. Times are ISO strings with a Z, as the store writes them.
NOW = "2026-11-05T13:10:00Z"
PARKED_W = {"id": "windows-live-checks", "ref": "Step windows-live-checks, the Windows live checks", "note": "Triage removes this line."}
PARKED_GONE = {"id": "no-such-item", "ref": "Step no-such-item, a line whose item is gone", "note": "Gone."}


def item_entry(item_id, status, **extra):
    """An item doc. `extra` sets or overrides its data fields."""
    data = {"id": item_id, "kind": "decision", "status": status, "n": 10, "title": "Windows live checks"}
    data.update(extra)
    return {"id": item_id, "data": data}


def park_answer_entry(item_id, at):
    return {"id": "park." + item_id, "data": {"parked": True, "id": item_id, "act": "unpark", "ref": "Step " + item_id, "note": "Wait.", "at": at}}


def item_answer_entry(item_id, at):
    """An item's answer under its own key, as a Park press on its card writes it: {item, n, at, act: "park", note}."""
    return {"id": item_id, "data": {"item": item_id, "n": 27, "at": at, "act": "park", "note": "Later."}}


def pick_answer_entry(item_id, at):
    """An item's answer to a pick under its own key: {item, n, at, choice, note}, with no act."""
    return {"id": item_id, "data": {"item": item_id, "n": 27, "at": at, "choice": "a", "note": ""}}


def without_field(entry, key):
    """The same entry with no `key` field."""
    del entry["data"][key]
    return entry


def without_at(entry):
    """The same entry with no `at` field."""
    return without_field(entry, "at")


def output_lines(out):
    return [line for line in out.splitlines() if line.strip()]


class FolderCase(unittest.TestCase):
    """A folder of saved store files, one folder per case. The store modes share this base: the run-folder temp, the file writer, the unknown check and the tree."""
    FOLDER = "folder"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=RUN_FOLDER)  # test-temp-standard: never the system temp dir
        self.addCleanup(self.tmp.cleanup)
        self.folder = os.path.join(self.tmp.name, self.FOLDER)
        os.mkdir(self.folder)

    def write_store(self, files):
        """Writes each file (name -> value) as JSON exactly as given: a name left out is a file that is not there."""
        for name, value in files.items():
            write_text(os.path.join(self.folder, name + ".json"), json.dumps(value))

    def clear_store(self):
        """Empties the folder, so a case with several subtests starts each one from no files."""
        shutil.rmtree(self.folder)
        os.mkdir(self.folder)

    def assert_unknown(self, rc, out, *names):
        """The run exits 2 and prints an unknown line naming each of `names`: never a clean or a stale line for the same cause."""
        lines = output_lines(out)
        self.assertEqual(rc, 2, "exit %d, want 2 for an unknown read: %s" % (rc, out))
        unknown = [line for line in lines if line.startswith("unknown:")]
        self.assertTrue(unknown, "no unknown: line was printed: %r" % out)
        for name in names:
            self.assertTrue(any(name in line for line in unknown), "the unknown line does not name %s: %r" % (name, unknown))

    def tree(self):
        """Every file under the test folder, as {relative path: bytes}."""
        out = {}
        for root, _, files in os.walk(self.tmp.name):
            for name in files:
                path = os.path.join(root, name)
                with open(path, "rb") as f:
                    out[os.path.relpath(path, self.tmp.name)] = f.read()
        return out


class ParkedStale(FolderCase):
    """The --parked mode. Each case writes its own three files, then runs the script on them."""
    FOLDER = "parked"

    def store(self, meta=None, items=(), answers=()):
        """Writes the three files the mode reads, each from its entries."""
        self.store_raw(meta, list(items), list(answers))

    def store_raw(self, meta=None, items=None, answers=None):
        """Writes the three files exactly as given (a file left out is empty), so a case can hand the mode a value of the wrong shape."""
        meta = {"writer": "triage", "parked": []} if meta is None else meta
        items = [] if items is None else items
        answers = [] if answers is None else answers
        self.write_store({"meta": meta, "items": items, "answers": answers})

    def run_parked(self, now=NOW, codes=(0, 1)):
        """Runs the mode on the folder. Stale.run_script is the one runner of CMD in this file; it reads no state of its case.
        Without the mode, the script runs its batch mode on the folder, so that output is named as the cause."""
        r = Stale.run_script(self, "--parked", self.folder, "--now", now)
        self.assertNotIn("waiting pages:", r.stdout + r.stderr, "the --parked mode did not run: stale_pages.py ran its batch mode")
        self.assertIn(r.returncode, codes, "the --parked mode exited %d, want one of %s: %s" % (r.returncode, codes, r.stdout + r.stderr))
        return r.returncode, r.stdout

    def assert_unknown_key(self, entry, key):
        """A park answer with no readable `at` is unknown and names its key. It is not named old."""
        self.store(answers=[entry])
        rc, out = self.run_parked(codes=(0, 1, 2))
        self.assert_unknown(rc, out, key)
        self.assertEqual([line for line in output_lines(out) if line.startswith("park-answer-old")], [],
                         "a park answer with no readable at was named old, not unknown: " + out)

    def test_an_open_item_under_a_parked_entry_is_named_and_the_mode_exits_1(self):
        self.store(meta={"writer": "triage", "parked": [PARKED_W]}, items=[item_entry("windows-live-checks", "open")])
        rc, out = self.run_parked()
        self.assertEqual(rc, 1, "a parked entry whose item is open did not exit 1:\n" + out)
        self.assertEqual(output_lines(out), ["parked-open windows-live-checks"], "the parked entry whose item is open was not the one line named")

    def test_a_park_answer_more_than_ten_minutes_old_is_named_by_its_key(self):
        self.store(answers=[park_answer_entry("ci-cap-raise", "2026-11-05T12:59:59Z")])
        rc, out = self.run_parked()
        self.assertEqual(rc, 1, "a park answer 10 minutes and 1 second old did not exit 1:\n" + out)
        self.assertEqual(output_lines(out), ["park-answer-old park.ci-cap-raise"], "the old park answer was not the one line named")

    def test_a_park_answer_exactly_ten_minutes_old_is_not_named(self):
        self.store(answers=[park_answer_entry("ci-cap-raise", "2026-11-05T13:00:00Z")])
        rc, out = self.run_parked()
        self.assertEqual((rc, output_lines(out)), (0, ["parked: clean"]), "a park answer exactly 10 minutes old was named: " + out)

    def test_a_parked_entry_whose_item_is_closed_or_missing_is_not_named(self):
        self.store(meta={"writer": "triage", "parked": [PARKED_W, PARKED_GONE]}, items=[item_entry("windows-live-checks", "closed")])
        rc, out = self.run_parked()
        self.assertEqual((rc, output_lines(out)), (0, ["parked: clean"]), "a parked entry with no open item was named: " + out)

    def test_a_fresh_park_answer_and_a_closed_item_leave_nothing_stale(self):
        self.store(meta={"writer": "triage", "parked": [PARKED_W]}, items=[item_entry("windows-live-checks", "closed")],
                   answers=[park_answer_entry("windows-live-checks", "2026-11-05T13:05:00Z")])
        rc, out = self.run_parked()
        self.assertEqual((rc, output_lines(out)), (0, ["parked: clean"]), "a fresh park answer under a closed item was named: " + out)

    def test_each_stale_thing_gets_one_line_and_the_mode_exits_1(self):
        self.store(meta={"writer": "triage", "parked": [PARKED_W]}, items=[item_entry("windows-live-checks", "open")],
                   answers=[park_answer_entry("ci-cap-raise", "2026-11-05T12:00:00Z")])
        rc, out = self.run_parked()
        self.assertEqual(rc, 1, "two stale things did not exit 1:\n" + out)
        self.assertEqual(sorted(output_lines(out)), ["park-answer-old park.ci-cap-raise", "parked-open windows-live-checks"],
                         "the two stale things were not named one line each")

    def test_an_item_park_answer_more_than_ten_minutes_old_is_named_by_its_item_id(self):
        self.store(answers=[item_answer_entry("pick-a-colour", "2026-11-05T12:59:59Z")])
        rc, out = self.run_parked()
        self.assertEqual(rc, 1, "an item's park answer 10 minutes and 1 second old did not exit 1: " + out)
        self.assertEqual(output_lines(out), ["park-answer-old pick-a-colour"], "the old item park answer was not the one line named: " + out)

    # Control: passes on the code as it stands. A fresh item park answer is not named, so the old-answer check cannot name every answer.
    def test_a_fresh_item_park_answer_is_not_named(self):
        self.store(answers=[item_answer_entry("pick-a-colour", "2026-11-05T13:05:00Z")])
        rc, out = self.run_parked()
        self.assertEqual((rc, output_lines(out)), (0, ["parked: clean"]), "a fresh item park answer was named: " + out)

    # Control: passes on the code as it stands. An item answer with no act park is never read, however old or however it is stamped.
    def test_an_item_answer_without_act_park_is_never_named(self):
        self.store(answers=[pick_answer_entry("pick-a-colour", "2026-11-05T12:00:00Z"), without_at(pick_answer_entry("ci-cap-raise", "2026-11-05T12:00:00Z"))])
        rc, out = self.run_parked()
        self.assertEqual((rc, output_lines(out)), (0, ["parked: clean"]), "an item answer with no act park was named: " + out)

    def test_items_not_a_list_is_unknown_and_exits_2(self):
        self.store_raw(items={})
        rc, out = self.run_parked(codes=(0, 1, 2))
        self.assert_unknown(rc, out, "items.json")

    def test_answers_not_a_list_is_unknown_and_exits_2(self):
        self.store_raw(answers={})
        rc, out = self.run_parked(codes=(0, 1, 2))
        self.assert_unknown(rc, out, "answers.json")

    def test_meta_not_a_dict_is_unknown_and_exits_2(self):
        self.store_raw(meta=[PARKED_W], items=[item_entry("windows-live-checks", "open")])
        rc, out = self.run_parked(codes=(0, 1, 2))
        self.assert_unknown(rc, out, "meta.json")

    def test_a_parked_line_answer_with_no_at_is_unknown_and_names_its_key(self):
        self.assert_unknown_key(without_at(park_answer_entry("ci-cap-raise", "2026-11-05T12:00:00Z")), "park.ci-cap-raise")

    def test_an_item_park_answer_with_no_at_is_unknown_and_names_its_key(self):
        self.assert_unknown_key(without_at(item_answer_entry("pick-a-colour", "2026-11-05T12:00:00Z")), "pick-a-colour")

    def test_a_parked_line_answer_with_an_unparseable_at_is_unknown_and_names_its_key(self):
        self.assert_unknown_key(park_answer_entry("ci-cap-raise", "not-a-time"), "park.ci-cap-raise")

    def test_an_item_park_answer_with_an_unparseable_at_is_unknown_and_names_its_key(self):
        self.assert_unknown_key(item_answer_entry("pick-a-colour", "not-a-time"), "pick-a-colour")

    def test_the_mode_reads_its_three_files_writes_none_and_starts_no_git(self):
        self.store(meta={"writer": "triage", "parked": [PARKED_W]}, items=[item_entry("windows-live-checks", "open")])
        write_text(os.path.join(self.folder, "other.json"), "{ not json")  # a file the mode never reads
        before = self.tree()
        # No PATH: a git start would fail, so a clean run shows the mode starts no git process.
        r = subprocess.run([sys.executable, CMD, "--parked", self.folder, "--now", NOW], capture_output=True, text=True,
                           timeout=30, env={"PATH": "", "PYTHONDONTWRITEBYTECODE": "1", "HOME": self.tmp.name})
        self.assertNotIn("waiting pages:", r.stdout, "the --parked mode did not run: stale_pages.py ran its batch mode")
        self.assertIn(r.returncode, (0, 1), "the --parked mode did not run with no PATH (exit %d): %s" % (r.returncode, r.stderr))
        self.assertEqual(r.stderr, "", "the --parked mode wrote to stderr, so it needs a process it does not own: " + r.stderr)
        self.assertEqual(output_lines(r.stdout), ["parked-open windows-live-checks"], "the mode did not read its three files")
        self.assertEqual(self.tree(), before, "the --parked mode wrote or removed a file")


# --unread: the on-demand pass over the answers the writer has not read back (waiting-page SKILL.md). It reads four saved
# files in one folder and writes none. Each list file holds [{"id", "data"}] entries, the shape an ArtifactData list returns.
#   meta.json      {"writer": ..., "woke": "<ISO time>"}   the meta/page data, an object; `woke` is the writer's previous wake
#   items.json     [{"id": "<item id>", "data": {"status": "open" | "closed", "n": <number>, "owner": ..., ...}}, ...]
#   answers.json   [{"id": "<item id>", "data": {"item", "n", "at", ...}}, ...]   an item's answer, under its item's id
#   receipts.json  [{"id": "<answer id>", "data": {"read": "<ISO time>", "filed": "<ISO time>"}}, ...]
# An answer is listed when it is an item answer (not park.<id>, not parked, not act park), its item exists (open, or closed
# with the answer kept), its `at` is before `woke`, and no receipt for it has a `read` at or after `at`. With no `woke`
# (absent or null), every answer with no such receipt is listed. One line per listed answer, in answers.json order, then
# exit 1: `answer-unread <id> (item <n>, owner <owner>, answered <at>, before wake <woke>)`, with `before wake: none recorded`
# as the last field when there is no woke, and `?` for a missing n or owner. With none, `unread: clean` and exit 0. A file
# missing or of the wrong shape, an unreadable `woke`, an unreadable `at`, or an unreadable `read` of a receipt that is
# compared prints `unknown: <what>` and exits 2: the mode never calls such a thing clean or listed. Receipt times are ISO
# UTC with a trailing Z by the skill's rule (SKILL.md, the receipts entry); the fixtures use that form.
# The mode reads no clock: what it lists depends on the saved files alone.
WOKE = "2026-11-05T13:10:00Z"
EARLY = "2026-11-05T02:40:00Z"  # long before WOKE: the incident shape, an answer that stayed unread that long
LATER_REPLY = "2026-11-05T03:40:00Z"  # an item reply an hour after EARLY, still before WOKE
UNREAD_LINE = re.compile(r"answer-unread \S+ \(|answer-needs-reply \S+ \(|lane-missing \S+ \(|unread: clean$|unknown: ")  # the mode's own line shapes


def good_files(meta=None):
    """The four files of a store with nothing to list and the wake WOKE. A shape case changes one of them."""
    return {"meta": {"writer": "triage", "woke": WOKE} if meta is None else meta, "items": [], "answers": [], "receipts": []}


def unread_line(item_id, n, owner, at, woke=WOKE):
    """The line the mode prints for a listed answer. A `woke` of None is the no-wake form."""
    before = "before wake %s" % woke if woke else "before wake: none recorded"
    return "answer-unread %s (item %s, owner %s, answered %s, %s)" % (item_id, n, owner, at, before)


def receipt_entry(item_id, **fields):
    """A receipt, under the id of the answer it reads back."""
    return {"id": item_id, "data": fields}


def parked_data_answer(item_id, at):
    """An item's answer under its own key that carries parked: true and no act: the third form a park answer takes."""
    return {"id": item_id, "data": {"parked": True, "item": item_id, "n": 27, "at": at, "note": "Later."}}


HOLDS = "Stops the batch run until the answer."  # the item's `holds` field: what a lane, a merge or a PR waits on (SKILL.md, "Add an item")
WAITS = {"repo": REPO, "pr": PR}  # the item's `waits` field: the PR it waits on (SKILL.md, "Add an item"); a CI or PR wait, not a lane


def lane_unread_line(item_id, n, owner, at, lane, woke=WOKE):
    """The line for a listed answer on an item with `lane`: the plain line, with `lane <slug>` as its last field."""
    before = "before wake %s" % woke if woke else "before wake: none recorded"
    return "answer-unread %s (item %s, owner %s, answered %s, %s, lane %s)" % (item_id, n, owner, at, before, lane)


def lane_missing_line(item_id, n, owner):
    """The line for an open item that holds a lane (`holds` set) with no `lane`."""
    return "lane-missing %s (item %s, owner %s)" % (item_id, n, owner)


def needs_reply_line(item_id, n, owner, at):
    """The line for a `none` answer that asks a question with no item reply newer than the answer."""
    return "answer-needs-reply %s (item %s, owner %s, answered %s)" % (item_id, n, owner, at)


def none_answer_entry(item_id, at, note):
    """An answer of `none` (none of these) with a note, under the item's own key."""
    return {"id": item_id, "data": {"item": item_id, "n": 27, "at": at, "choice": "none", "note": note}}


class UnreadStale(FolderCase):
    """The --unread mode. Each case writes its own four files, then runs the script on them."""
    FOLDER = "unread"

    def store(self, meta=None, items=(), answers=(), receipts=()):
        """Writes the four files the mode reads. The meta carries the wake WOKE unless `meta` is given."""
        files = good_files(meta)
        files.update(items=list(items), answers=list(answers), receipts=list(receipts))
        self.write_store(files)

    def assert_mode_lines(self, out, detail=""):
        """The output is the mode's own lines. Without the mode, the script runs its batch mode, whose output is not these lines."""
        lines = output_lines(out)
        self.assertTrue(lines and all(UNREAD_LINE.match(line) for line in lines),
                        "the --unread mode did not run: its output is not its lines: %r; %s" % (out, detail))

    def assert_no_listed_line(self, out, why):
        self.assertEqual([line for line in output_lines(out) if line.startswith("answer-unread")], [], "%s: %s" % (why, out))

    def run_unread(self, codes=(0, 1)):
        """Runs the mode on the folder through Stale.run_script, the one runner of CMD in this file."""
        r = Stale.run_script(self, "--unread", self.folder)
        self.assert_mode_lines(r.stdout, r.stderr)
        self.assertIn(r.returncode, codes, "the --unread mode exited %d, want one of %s: %s" % (r.returncode, codes, r.stdout + r.stderr))
        return r.returncode, r.stdout

    def run_main(self, *argv):
        """main(argv) in this process, with stdout captured. Each process start is refused and recorded, at the start itself, so
        `starts` lists every one the run asked for. Returns (exit code, stdout, starts, error); error is the exception text when
        the run raised instead of answering, else ""."""
        stale = load_stale_pages()
        starts = []

        def refuse(*args, **kwargs):
            starts.append(args[0] if args else kwargs.get("args"))
            raise OSError("process start refused")

        out, code, error = io.StringIO(), None, ""
        with mock.patch.object(subprocess, "Popen", side_effect=refuse), mock.patch.object(os, "system", side_effect=refuse), \
                contextlib.redirect_stdout(out):
            try:
                code = stale.main(list(argv))
            except SystemExit as err:
                code = err.code
            except Exception as err:  # a run that raised answered nothing; the caller names it
                error = repr(err)
        return code, out.getvalue(), starts, error

    def test_an_answer_long_before_the_wake_with_no_receipt_is_listed_with_its_exact_line_and_exits_1(self):
        self.store(items=[item_entry("colour-pick", "open", n=143, owner="ops")], answers=[pick_answer_entry("colour-pick", EARLY)])
        rc, out = self.run_unread()
        self.assertEqual((rc, output_lines(out)), (1, [unread_line("colour-pick", 143, "ops", EARLY)]), "the old answer with no receipt was not listed: " + out)

    def test_an_answer_one_second_before_the_wake_is_listed(self):
        at = "2026-11-05T13:09:59Z"
        self.store(items=[item_entry("colour-pick", "open", n=143, owner="ops")], answers=[pick_answer_entry("colour-pick", at)])
        rc, out = self.run_unread()
        self.assertEqual((rc, output_lines(out)), (1, [unread_line("colour-pick", 143, "ops", at)]), "an answer one second before the wake was not listed: " + out)

    def test_an_answer_at_the_wake_or_after_it_is_not_listed(self):
        self.store(items=[item_entry("at-wake", "open"), item_entry("after-wake", "open")],
                   answers=[pick_answer_entry("at-wake", WOKE), pick_answer_entry("after-wake", "2026-11-05T13:10:01Z")])
        rc, out = self.run_unread(codes=(0,))
        self.assertEqual((rc, output_lines(out)), (0, ["unread: clean"]), "an answer at or after the wake was listed: " + out)

    def test_a_receipt_read_at_or_after_the_answer_clears_it(self):
        self.store(items=[item_entry("same-time", "open"), item_entry("read-later", "open")],
                   answers=[pick_answer_entry("same-time", EARLY), pick_answer_entry("read-later", EARLY)],
                   receipts=[receipt_entry("same-time", read=EARLY), receipt_entry("read-later", read="2026-11-05T13:00:00Z")])
        rc, out = self.run_unread(codes=(0,))
        self.assertEqual((rc, output_lines(out)), (0, ["unread: clean"]), "a receipt read at or after the answer did not clear it: " + out)

    def test_a_receipt_read_before_the_answer_does_not_clear_it(self):
        self.store(items=[item_entry("colour-pick", "open", n=143, owner="ops")], answers=[pick_answer_entry("colour-pick", EARLY)],
                   receipts=[receipt_entry("colour-pick", read="2026-11-05T02:00:00Z")])
        rc, out = self.run_unread()
        self.assertEqual((rc, output_lines(out)), (1, [unread_line("colour-pick", 143, "ops", EARLY)]), "a receipt read before the answer cleared it: " + out)

    def test_a_receipt_with_only_filed_does_not_clear_it(self):
        self.store(items=[item_entry("colour-pick", "open", n=143, owner="ops")], answers=[pick_answer_entry("colour-pick", EARLY)],
                   receipts=[receipt_entry("colour-pick", filed="2026-11-05T02:50:00Z")])
        rc, out = self.run_unread()
        self.assertEqual((rc, output_lines(out)), (1, [unread_line("colour-pick", 143, "ops", EARLY)]), "a receipt with only filed cleared the answer: " + out)

    # The store keeps one receipt per id (receipts/<id>), so two receipts for one answer never occur there: these two cases
    # pin the code only. The code reads every receipt of an answer and clears it on any read at or after the answer. Both
    # orders are pinned, since a check that reads only the last receipt in the list passes one order and fails the other.
    def test_a_receipt_read_before_the_answer_beside_one_read_after_it_clears_it(self):
        self.store(items=[item_entry("colour-pick", "open")], answers=[pick_answer_entry("colour-pick", EARLY)],
                   receipts=[receipt_entry("colour-pick", read="2026-11-05T02:00:00Z"), receipt_entry("colour-pick", read="2026-11-05T13:00:00Z")])
        rc, out = self.run_unread(codes=(0,))
        self.assertEqual((rc, output_lines(out)), (0, ["unread: clean"]),
                         "a receipt read before the answer, beside one read after it, kept the answer unread: " + out)

    def test_a_receipt_read_after_the_answer_beside_one_read_before_it_clears_it(self):
        self.store(items=[item_entry("colour-pick", "open")], answers=[pick_answer_entry("colour-pick", EARLY)],
                   receipts=[receipt_entry("colour-pick", read="2026-11-05T13:00:00Z"), receipt_entry("colour-pick", read="2026-11-05T02:00:00Z")])
        rc, out = self.run_unread(codes=(0,))
        self.assertEqual((rc, output_lines(out)), (0, ["unread: clean"]),
                         "a receipt read after the answer, beside one read before it, kept the answer unread: " + out)

    def test_with_no_wake_every_answer_with_no_receipt_read_back_is_listed(self):
        items = [item_entry("recent", "open", n=1, owner="ops"), item_entry("old", "open", n=2, owner="ops"), item_entry("read", "open", n=3, owner="ops")]
        answers = [pick_answer_entry("recent", "2026-11-05T13:09:00Z"), pick_answer_entry("old", EARLY), pick_answer_entry("read", EARLY)]
        receipts = [receipt_entry("read", read=EARLY)]
        expected = [unread_line("recent", 1, "ops", "2026-11-05T13:09:00Z", woke=None), unread_line("old", 2, "ops", EARLY, woke=None)]
        for meta in ({"writer": "triage"}, {"writer": "triage", "woke": None}):
            with self.subTest(meta=meta):
                self.store(meta=meta, items=items, answers=answers, receipts=receipts)
                rc, out = self.run_unread()
                self.assertEqual((rc, output_lines(out)), (1, expected), "with no wake, the answers with no receipt were not all listed: " + out)

    def test_a_park_answer_is_never_listed_under_any_of_its_three_forms(self):
        self.store(items=[item_entry("colour-pick", "open"), item_entry("parked-entry", "open"), item_entry("ci-cap-raise", "open")],
                   answers=[park_answer_entry("colour-pick", EARLY), parked_data_answer("parked-entry", EARLY), item_answer_entry("ci-cap-raise", EARLY)])
        rc, out = self.run_unread(codes=(0,))
        self.assertEqual((rc, output_lines(out)), (0, ["unread: clean"]), "a park answer was listed as unread: " + out)

    def test_an_answer_for_a_missing_item_is_skipped(self):
        self.store(answers=[pick_answer_entry("ghost-item", EARLY)])
        rc, out = self.run_unread(codes=(0,))
        self.assertEqual((rc, output_lines(out)), (0, ["unread: clean"]), "an answer with no item was listed: " + out)

    def test_a_closed_item_with_its_answer_kept_is_listed(self):
        self.store(items=[item_entry("colour-pick", "closed", n=143, owner="ops")], answers=[pick_answer_entry("colour-pick", EARLY)])
        rc, out = self.run_unread()
        self.assertEqual((rc, output_lines(out)), (1, [unread_line("colour-pick", 143, "ops", EARLY)]), "a closed item's kept answer was not listed: " + out)

    def test_a_missing_n_or_owner_prints_a_question_mark(self):
        item = without_field(without_field(item_entry("colour-pick", "open", n=143, owner="ops"), "n"), "owner")
        self.store(items=[item], answers=[pick_answer_entry("colour-pick", EARLY)])
        rc, out = self.run_unread()
        self.assertEqual((rc, output_lines(out)), (1, [unread_line("colour-pick", "?", "?", EARLY)]), "a missing n or owner did not print ?: " + out)

    def test_listed_answers_print_in_answers_order(self):
        self.store(items=[item_entry("bee", "open", n=2, owner="ops"), item_entry("ay", "open", n=1, owner="ops")],
                   answers=[pick_answer_entry("bee", EARLY), pick_answer_entry("ay", EARLY)])
        rc, out = self.run_unread()
        self.assertEqual((rc, output_lines(out)), (1, [unread_line("bee", 2, "ops", EARLY), unread_line("ay", 1, "ops", EARLY)]),
                         "the listed answers were not in answers.json order: " + out)

    def test_a_full_store_lists_each_unread_answer_and_no_other(self):
        count = 120  # a full page of answers, every third one read back
        items = [item_entry("item-%03d" % i, "open", n=i, owner="ops") for i in range(count)]
        answers = [pick_answer_entry("item-%03d" % i, EARLY) for i in range(count)]
        receipts = [receipt_entry("item-%03d" % i, read=EARLY) for i in range(0, count, 3)]
        self.store(items=items, answers=answers, receipts=receipts)
        rc, out = self.run_unread()
        expected = [unread_line("item-%03d" % i, i, "ops", EARLY) for i in range(count) if i % 3]
        self.assertEqual((rc, output_lines(out)), (1, expected), "a full store did not list each unread answer, in order: " + out[:300])

    def test_an_empty_store_is_clean(self):
        self.store()
        rc, out = self.run_unread(codes=(0,))
        self.assertEqual((rc, output_lines(out)), (0, ["unread: clean"]), "an empty store was not clean: " + out)

    def test_a_receipt_with_an_unreadable_read_is_unknown_when_its_answer_is_compared(self):
        self.store(items=[item_entry("colour-pick", "open")], answers=[pick_answer_entry("colour-pick", EARLY)],
                   receipts=[receipt_entry("colour-pick", read="not-a-time")])
        rc, out = self.run_unread(codes=(0, 1, 2))
        self.assert_unknown(rc, out, "colour-pick")
        self.assert_no_listed_line(out, "an answer whose receipt has no readable read was listed beside its unknown")

    def test_a_receipt_with_an_unreadable_read_is_not_read_for_a_skipped_answer(self):
        self.store(items=[item_entry("colour-pick", "open")],
                   answers=[pick_answer_entry("ghost-item", EARLY), park_answer_entry("colour-pick", EARLY)],
                   receipts=[receipt_entry("ghost-item", read="not-a-time"), receipt_entry("park.colour-pick", read="not-a-time")])
        rc, out = self.run_unread(codes=(0,))
        self.assertEqual((rc, output_lines(out)), (0, ["unread: clean"]), "a receipt of a skipped answer was read as unknown: " + out)

    def test_an_answer_with_an_unreadable_at_is_unknown_and_names_its_id(self):
        self.store(items=[item_entry("colour-pick", "open")], answers=[pick_answer_entry("colour-pick", "not-a-time")])
        rc, out = self.run_unread(codes=(0, 1, 2))
        self.assert_unknown(rc, out, "colour-pick")
        self.assert_no_listed_line(out, "an answer with an unreadable at was listed")

    def test_a_listed_answer_beside_an_answer_with_an_unreadable_at_prints_both_lines_and_exits_2(self):
        self.store(items=[item_entry("colour-pick", "open", n=143, owner="ops"), item_entry("bad-time", "open")],
                   answers=[pick_answer_entry("colour-pick", EARLY), pick_answer_entry("bad-time", "not-a-time")])
        rc, out = self.run_unread(codes=(2,))
        self.assert_unknown(rc, out, "bad-time")
        self.assertEqual([line for line in output_lines(out) if line.startswith("answer-unread")], [unread_line("colour-pick", 143, "ops", EARLY)],
                         "the listed answer was not printed beside the unknown line: " + out)

    def test_an_answer_with_no_at_is_unknown_and_names_its_id(self):
        self.store(items=[item_entry("colour-pick", "open")], answers=[without_at(pick_answer_entry("colour-pick", EARLY))])
        rc, out = self.run_unread(codes=(0, 1, 2))
        self.assert_unknown(rc, out, "colour-pick")
        self.assert_no_listed_line(out, "an answer with no at was listed")

    def test_an_unreadable_woke_is_unknown_and_exits_2(self):
        self.store(meta={"writer": "triage", "woke": "not-a-time"}, items=[item_entry("colour-pick", "open")],
                   answers=[pick_answer_entry("colour-pick", EARLY)])
        rc, out = self.run_unread(codes=(0, 1, 2))
        self.assert_unknown(rc, out, "woke")
        self.assert_no_listed_line(out, "an answer was listed against an unreadable woke")

    def test_a_missing_file_is_unknown_and_exits_2(self):
        for name in ("meta", "items", "answers", "receipts"):
            with self.subTest(missing=name):
                self.clear_store()
                files = good_files()
                del files[name]
                self.write_store(files)
                rc, out = self.run_unread(codes=(0, 1, 2))
                self.assert_unknown(rc, out, name + ".json")

    def test_a_file_that_is_not_json_is_unknown_and_exits_2(self):
        for name in ("meta", "items", "answers", "receipts"):
            with self.subTest(unreadable=name):
                self.clear_store()
                self.write_store(good_files())
                write_text(os.path.join(self.folder, name + ".json"), "{ not json")
                rc, out = self.run_unread(codes=(0, 1, 2))
                self.assert_unknown(rc, out, name + ".json")

    def test_a_file_of_the_wrong_shape_is_unknown_and_exits_2(self):
        wrong = {"meta": ["woke", WOKE], "items": {}, "answers": {}, "receipts": {}}
        for name, value in wrong.items():
            with self.subTest(shape=name):
                self.clear_store()
                files = good_files()
                files[name] = value
                self.write_store(files)
                rc, out = self.run_unread(codes=(0, 1, 2))
                self.assert_unknown(rc, out, name + ".json")

    def test_the_mode_writes_no_file(self):
        self.store(items=[item_entry("colour-pick", "open", n=143, owner="ops")], answers=[pick_answer_entry("colour-pick", EARLY)])
        before = self.tree()
        self.run_unread(codes=(1,))
        self.assertEqual(self.tree(), before, "the --unread mode wrote or removed a file")

    def test_the_mode_starts_no_process_in_process(self):
        self.store(items=[item_entry("colour-pick", "open", n=143, owner="ops")], answers=[pick_answer_entry("colour-pick", EARLY)])
        _, out, starts, error = self.run_main("--unread", self.folder)
        self.assert_mode_lines(out, error)
        self.assertEqual(starts, [], "the --unread mode asked for a process: %r" % starts)

    def test_the_mode_runs_with_no_path_so_it_starts_no_git(self):
        self.store(items=[item_entry("colour-pick", "open", n=143, owner="ops")], answers=[pick_answer_entry("colour-pick", EARLY)])
        # No PATH: a git or gh start would fail, so a clean run shows the mode starts none.
        r = subprocess.run([sys.executable, CMD, "--unread", self.folder], capture_output=True, text=True, timeout=30,
                           env={"PATH": "", "PYTHONDONTWRITEBYTECODE": "1", "HOME": self.tmp.name})
        self.assert_mode_lines(r.stdout, r.stderr)
        self.assertEqual((r.returncode, r.stderr), (1, ""), "the --unread mode failed with no PATH, or wrote to stderr: " + r.stderr)
        self.assertEqual(output_lines(r.stdout), [unread_line("colour-pick", 143, "ops", EARLY)], "the mode did not read its files with no PATH: " + r.stdout)

    def test_main_sends_unread_to_its_mode(self):
        self.store(items=[item_entry("colour-pick", "open", n=143, owner="ops")], answers=[pick_answer_entry("colour-pick", EARLY)])
        code, out, _, error = self.run_main("--unread", self.folder)
        self.assert_mode_lines(out, error)
        self.assertEqual((code, output_lines(out)), (1, [unread_line("colour-pick", 143, "ops", EARLY)]), "main() did not send --unread to its mode: " + out)

    # The lane fields. An item that holds a lane carries it in `lane`, and a listed answer names that lane, so the wake can message
    # it. An open item that holds (`holds` set) with no `lane` is named lane-missing. A holding item with a lane, or an item that
    # holds nothing, is not named.

    def test_an_answer_on_an_item_with_a_lane_names_that_lane(self):
        self.store(items=[item_entry("colour-pick", "open", n=143, owner="triage", lane="batch-runner")], answers=[pick_answer_entry("colour-pick", EARLY)])
        rc, out = self.run_unread()
        self.assertEqual((rc, output_lines(out)), (1, [lane_unread_line("colour-pick", 143, "triage", EARLY, "batch-runner")]),
                         "the answer on a lane item does not name its lane: " + out)

    def test_an_answer_on_an_item_with_no_lane_keeps_the_plain_line(self):
        self.store(items=[item_entry("colour-pick", "open", n=143, owner="triage")], answers=[pick_answer_entry("colour-pick", EARLY)])
        rc, out = self.run_unread()
        self.assertEqual((rc, output_lines(out)), (1, [unread_line("colour-pick", 143, "triage", EARLY)]), "an answer on an item with no lane changed its line: " + out)

    def test_a_holding_item_with_no_lane_is_reported_as_lane_missing(self):
        cases = {"no lane key": item_entry("colour-pick", "open", n=143, owner="ops", holds=HOLDS),
                 "empty lane": item_entry("colour-pick", "open", n=143, owner="ops", holds=HOLDS, lane="")}
        for case, item in cases.items():
            with self.subTest(case=case):
                self.store(items=[item])
                rc, out = self.run_unread(codes=(0, 1))
                self.assertEqual((rc, output_lines(out)), (1, [lane_missing_line("colour-pick", 143, "ops")]),
                                 "a holding item with %s was not reported as lane-missing: %s" % (case, out))

    def test_a_holding_item_with_a_lane_is_not_reported_as_lane_missing(self):
        self.store(items=[item_entry("colour-pick", "open", n=143, owner="ops", holds=HOLDS, lane="batch-runner")])
        rc, out = self.run_unread(codes=(0,))
        self.assertEqual((rc, output_lines(out)), (0, ["unread: clean"]), "a holding item with a lane was reported: " + out)

    def test_an_item_that_holds_nothing_is_not_reported_for_its_empty_lane(self):
        self.store(items=[item_entry("colour-pick", "open", n=143, owner="ops", lane="")])
        rc, out = self.run_unread(codes=(0,))
        self.assertEqual((rc, output_lines(out)), (0, ["unread: clean"]), "an item that holds nothing was reported as lane-missing: " + out)

    def test_a_holding_item_with_waits_and_no_lane_is_reported_as_lane_missing(self):
        cases = {"no lane key": item_entry("colour-pick", "open", n=143, owner="ops", holds=HOLDS, waits=WAITS),
                 "empty lane": item_entry("colour-pick", "open", n=143, owner="ops", holds=HOLDS, waits=WAITS, lane="")}
        for case, item in cases.items():
            with self.subTest(case=case):
                self.store(items=[item])
                rc, out = self.run_unread()
                self.assertEqual((rc, output_lines(out)), (1, [lane_missing_line("colour-pick", 143, "ops")]),
                                 "a holding item with waits and %s was not reported as lane-missing: %s" % (case, out))
        with self.subTest(case="full store"):  # a full page of holding items that wait and have no lane: each one is named, in order
            count = 120
            self.store(items=[item_entry("item-%03d" % i, "open", n=i + 1, owner="ops", holds=HOLDS, waits=WAITS) for i in range(count)])
            rc, out = self.run_unread()
            expected = [lane_missing_line("item-%03d" % i, i + 1, "ops") for i in range(count)]
            self.assertEqual((rc, output_lines(out)), (1, expected), "a full store of holding items with waits did not name each one as lane-missing: " + out[:300])

    # A `none` answer that asks a question (its note ends in `?`, or its note is not empty) needs a reply on the item: a `reply` with
    # text, and `replied` later than the answer's `at`. Each case reads the answer's receipt back, so only the reply check can list it.

    def test_a_none_answer_that_asks_a_question_with_no_reply_is_listed_as_needing_reply(self):
        self.store(items=[item_entry("colour-pick", "open", n=143, owner="ops")], answers=[none_answer_entry("colour-pick", EARLY, "Which shade?")],
                   receipts=[receipt_entry("colour-pick", read=EARLY)])
        rc, out = self.run_unread()
        self.assertEqual((rc, output_lines(out)), (1, [needs_reply_line("colour-pick", 143, "ops", EARLY)]),
                         "a none answer that asks a question with no reply was not listed as needing a reply: " + out)

    def test_a_none_answer_with_a_note_and_no_question_mark_is_listed_as_needing_reply(self):
        self.store(items=[item_entry("colour-pick", "open", n=143, owner="ops")], answers=[none_answer_entry("colour-pick", EARLY, "Cheaper, please")],
                   receipts=[receipt_entry("colour-pick", read=EARLY)])
        rc, out = self.run_unread()
        self.assertEqual((rc, output_lines(out)), (1, [needs_reply_line("colour-pick", 143, "ops", EARLY)]),
                         "a none answer with a non-empty note and no question mark was not listed as needing a reply: " + out)

    def test_a_none_answer_with_an_empty_note_asks_nothing(self):
        self.store(items=[item_entry("colour-pick", "open", n=143, owner="ops")], answers=[none_answer_entry("colour-pick", EARLY, "")],
                   receipts=[receipt_entry("colour-pick", read=EARLY)])
        rc, out = self.run_unread(codes=(0,))
        self.assertEqual((rc, output_lines(out)), (0, ["unread: clean"]), "a none answer with an empty note was listed as needing a reply: " + out)

    def test_a_none_answer_with_a_reply_newer_than_it_needs_no_reply(self):
        self.store(items=[item_entry("colour-pick", "open", n=143, owner="ops", reply="Red, not grey.", replied=LATER_REPLY)],
                   answers=[none_answer_entry("colour-pick", EARLY, "Which shade?")], receipts=[receipt_entry("colour-pick", read=EARLY)])
        rc, out = self.run_unread(codes=(0,))
        self.assertEqual((rc, output_lines(out)), (0, ["unread: clean"]), "a none answer with a reply newer than it was listed: " + out)

    def test_a_none_answer_with_a_reply_older_than_it_is_listed_as_needing_reply(self):
        self.store(items=[item_entry("colour-pick", "open", n=143, owner="ops", reply="Red, not grey.", replied="2026-11-05T02:00:00Z")],
                   answers=[none_answer_entry("colour-pick", EARLY, "Which shade?")], receipts=[receipt_entry("colour-pick", read=EARLY)])
        rc, out = self.run_unread()
        self.assertEqual((rc, output_lines(out)), (1, [needs_reply_line("colour-pick", 143, "ops", EARLY)]),
                         "a none answer whose reply is older than it was not listed as needing a reply: " + out)

    def test_a_none_answer_with_an_empty_reply_is_listed_even_when_replied_is_newer(self):
        self.store(items=[item_entry("colour-pick", "open", n=143, owner="ops", reply="", replied=LATER_REPLY)],
                   answers=[none_answer_entry("colour-pick", EARLY, "Which shade?")], receipts=[receipt_entry("colour-pick", read=EARLY)])
        rc, out = self.run_unread()
        self.assertEqual((rc, output_lines(out)), (1, [needs_reply_line("colour-pick", 143, "ops", EARLY)]),
                         "a none answer with an empty reply was not listed as needing a reply: " + out)

    def test_a_pick_answer_with_a_question_note_needs_no_reply(self):
        answer = {"id": "colour-pick", "data": {"item": "colour-pick", "n": 27, "at": EARLY, "choice": "a", "note": "Why red?"}}
        self.store(items=[item_entry("colour-pick", "open", n=143, owner="ops")], answers=[answer], receipts=[receipt_entry("colour-pick", read=EARLY)])
        rc, out = self.run_unread(codes=(0,))
        self.assertEqual((rc, output_lines(out)), (0, ["unread: clean"]), "a pick answer with a question note was listed as needing a reply: " + out)

    def test_a_full_store_lists_each_none_question_with_no_reply_and_no_other(self):
        count = 120  # a full page of answers: every third asks a question and has no reply, the others are picks
        items = [item_entry("item-%03d" % i, "open", n=i + 1, owner="ops") for i in range(count)]
        answers = [none_answer_entry("item-%03d" % i, EARLY, "Which shade?") if i % 3 == 0 else pick_answer_entry("item-%03d" % i, EARLY)
                   for i in range(count)]
        receipts = [receipt_entry("item-%03d" % i, read=EARLY) for i in range(count)]
        self.store(items=items, answers=answers, receipts=receipts)
        rc, out = self.run_unread()
        expected = [needs_reply_line("item-%03d" % i, i + 1, "ops", EARLY) for i in range(count) if i % 3 == 0]
        self.assertEqual((rc, output_lines(out)), (1, expected), "a full store did not list each none question with no reply, in order: " + out[:300])

    def test_a_none_question_on_an_item_that_waits_is_listed_as_needing_reply_even_when_its_reply_is_newer(self):
        with self.subTest(case="one item"):
            self.store(items=[item_entry("colour-pick", "open", n=143, owner="ops", waits=WAITS, reply="Red, not grey.", replied=LATER_REPLY)],
                       answers=[none_answer_entry("colour-pick", EARLY, "Which shade?")], receipts=[receipt_entry("colour-pick", read=EARLY)])
            rc, out = self.run_unread()
            self.assertEqual((rc, output_lines(out)), (1, [needs_reply_line("colour-pick", 143, "ops", EARLY)]),
                             "a none question on an item that waits was cleared by a reply newer than the answer: " + out)
        with self.subTest(case="full store"):  # a full page of waiting items, each with a newer reply and a none question: each one is listed
            count = 120
            items = [item_entry("item-%03d" % i, "open", n=i + 1, owner="ops", waits=WAITS, reply="Red, not grey.", replied=LATER_REPLY) for i in range(count)]
            answers = [none_answer_entry("item-%03d" % i, EARLY, "Which shade?") for i in range(count)]
            self.store(items=items, answers=answers, receipts=[receipt_entry("item-%03d" % i, read=EARLY) for i in range(count)])
            rc, out = self.run_unread()
            expected = [needs_reply_line("item-%03d" % i, i + 1, "ops", EARLY) for i in range(count)]
            self.assertEqual((rc, output_lines(out)), (1, expected), "a full store of waiting items with a newer reply did not list each none question, in order: " + out[:300])


# The close batch (SKILL.md, "Route and close", steps 1 and 2 as one write). The mode reads no clock: its time is `--now`.
CLOSE_ID = "colour-pick"
CLOSE_NOW = "2026-11-13T13:40:00Z"
CLOSE_AT = "2026-11-13T13:20:00Z"  # the answer's time, before CLOSE_NOW


def item_data(**extra):
    """An open decision item's data, as a fetched items/<id> document holds it."""
    return dict({"id": CLOSE_ID, "kind": "decision", "status": "open", "n": 143, "owner": "triage", "title": "Colour"}, **extra)


def answer_data(**extra):
    """A pick answer's data, as a fetched answers/<id> document holds it."""
    return dict({"item": CLOSE_ID, "n": 143, "at": CLOSE_AT, "choice": "a", "note": "Red please"}, **extra)


def dropped(data, key):
    """The same data with `key` left out."""
    return {k: v for k, v in data.items() if k != key}


class CloseBatch(FolderCase):
    """The --close-batch mode. It prints one ArtifactData batch payload, {"writes": [...]}: the receipt set, the item close and the
    answer delete together, with the item and the answer each pinned to the version read. A refused read prints one unknown line,
    exits 2 and prints no payload. Each fetched file is {"id", "data", "version"}, the shape an ArtifactData get returns."""
    FOLDER = "close"

    def write_doc(self, name, data, version):
        write_text(os.path.join(self.folder, name), json.dumps({"id": CLOSE_ID, "data": data, "version": version}))

    def store(self, item="default", answer="default"):
        """Writes the item at version 4 and the answer at version 2. None leaves that file out; "default" writes the default data."""
        if item is not None:
            self.write_doc("item.json", item_data() if item == "default" else item, 4)
        if answer is not None:
            self.write_doc("answer.json", answer_data() if answer == "default" else answer, 2)

    def close(self, *extra, now=CLOSE_NOW):
        """Runs the mode on the item and answer files. `extra` adds flags, such as --reply."""
        return Stale.run_script(self, "--close-batch", "--item", os.path.join(self.folder, "item.json"),
                                "--answer", os.path.join(self.folder, "answer.json"), "--now", now, *extra)

    def good_payload(self, *extra):
        """The writes of a close that must succeed: exit 0 and one {"writes": [...]} payload."""
        r = self.close(*extra)
        self.assertEqual(r.returncode, 0, "the close exited %d, want 0: %s" % (r.returncode, r.stdout + r.stderr))
        try:
            doc = json.loads(r.stdout)
        except ValueError:
            doc = None
        writes = doc.get("writes") if isinstance(doc, dict) else None
        self.assertIsInstance(writes, list, 'the close printed no {"writes": [...]} payload: ' + r.stdout + r.stderr)
        return writes

    def write_for(self, writes, collection):
        """The one write of `collection` in the payload, or None when there is not exactly one."""
        found = [w for w in writes if isinstance(w, dict) and w.get("collection") == collection]
        return found[0] if len(found) == 1 else None

    def assert_refused(self, r, *names):
        """The close exits 2 with an unknown line naming each of `names`, and prints no payload."""
        self.assert_unknown(r.returncode, r.stdout, *names)
        self.assertNotIn('"writes"', r.stdout, "a refused close printed a payload: " + r.stdout)

    def test_a_close_batch_holds_the_receipt_the_item_close_and_the_answer_delete_together(self):
        self.store()
        writes = self.good_payload()
        collections = sorted(str(w.get("collection")) for w in writes if isinstance(w, dict))
        self.assertEqual(collections, ["answers", "items", "receipts"],
                         "the close batch does not hold one receipts, one items and one answers write: %r" % writes)

    def test_the_close_batch_sets_the_receipt_read_and_filed_to_the_given_time(self):
        self.store()
        receipt = self.write_for(self.good_payload(), "receipts")
        self.assertIsNotNone(receipt, "the close batch has no single receipts write")
        self.assertEqual((receipt.get("op"), receipt.get("doc_id"), receipt.get("data")), ("set", CLOSE_ID, {"read": CLOSE_NOW, "filed": CLOSE_NOW}),
                         "the receipt write is not a set of read and filed to the given time: %r" % receipt)

    def test_the_close_batch_closes_the_item_and_copies_the_answer_into_last_answer(self):
        self.store()
        item = self.write_for(self.good_payload(), "items")
        self.assertIsNotNone(item, "the close batch has no single items write")
        self.assertEqual((item.get("op"), item.get("doc_id")), ("update", CLOSE_ID), "the items write is not an update of the item: %r" % item)
        self.assertEqual(item.get("data"), {"status": "closed", "closed": CLOSE_NOW, "lastAnswer": {"choice": "a", "note": "Red please", "at": CLOSE_AT}},
                         "the item update does not close it with the answer copied into lastAnswer: %r" % item)

    def test_the_close_batch_pins_the_item_update_to_the_version_read(self):
        self.store()
        item = self.write_for(self.good_payload(), "items")
        self.assertIsNotNone(item, "the close batch has no single items write")
        self.assertEqual(item.get("if_version"), 4, "the item update is not pinned to the version read: %r" % item)

    def test_the_close_batch_deletes_the_answer_pinned_to_the_version_read(self):
        self.store()
        answer = self.write_for(self.good_payload(), "answers")
        self.assertIsNotNone(answer, "the close batch has no single answers write")
        self.assertEqual((answer.get("op"), answer.get("doc_id"), answer.get("if_version")), ("delete", CLOSE_ID, 2),
                         "the answer write is not a delete of answers/<id> pinned to its version: %r" % answer)

    def test_a_close_batch_refuses_when_the_answer_is_missing(self):
        self.store(answer=None)
        self.assert_refused(self.close(), CLOSE_ID)

    def test_a_close_batch_refuses_an_answer_with_no_at(self):
        self.store(answer=dropped(answer_data(), "at"))
        self.assert_refused(self.close(), CLOSE_ID)

    def test_a_close_batch_refuses_an_answer_with_an_unreadable_at(self):
        self.store(answer=answer_data(at="not-a-time"))
        self.assert_refused(self.close(), CLOSE_ID)

    def test_a_close_batch_refuses_when_the_item_is_missing(self):
        self.store(item=None)
        self.assert_refused(self.close(), CLOSE_ID)

    def test_a_close_of_a_question_none_answer_is_refused_without_a_reply(self):
        self.store(answer=answer_data(choice="none", note="Which shade?"))
        r = self.close()
        self.assert_refused(r, CLOSE_ID)
        self.assertTrue(any("reply" in line for line in output_lines(r.stdout) if line.startswith("unknown:")),
                        "the refusal does not name the missing reply: " + r.stdout)

    def test_a_close_of_a_question_none_answer_with_an_empty_reply_is_refused(self):
        self.store(answer=answer_data(choice="none", note="Which shade?"))
        r = self.close("--reply", "")
        self.assert_refused(r, CLOSE_ID)
        self.assertTrue(any("reply" in line for line in output_lines(r.stdout) if line.startswith("unknown:")),
                        "the refusal does not name the empty reply: " + r.stdout)

    def test_a_close_of_a_question_none_answer_with_a_reply_writes_the_reply_and_its_time(self):
        self.store(answer=answer_data(choice="none", note="Which shade?"))
        writes = self.good_payload("--reply", "Red, not grey.")
        item = self.write_for(writes, "items")
        self.assertIsNotNone(item, "the close batch has no single items write")
        self.assertEqual(item.get("data"), {"status": "closed", "closed": CLOSE_NOW, "lastAnswer": {"choice": "none", "note": "Which shade?", "at": CLOSE_AT},
                                            "reply": "Red, not grey.", "replied": CLOSE_NOW},
                         "the item update does not carry the reply and its time in the same write: %r" % item)
        self.assertEqual(len(writes), 3, "the reply close does not hold the receipt, the item close and the answer delete together: %r" % writes)

    def test_a_close_batch_refuses_an_item_on_a_lane_or_with_waits_until_the_act_is_told_done(self):
        for case, extra in (("lane", {"lane": "batch-runner"}), ("waits", {"waits": WAITS})):
            with self.subTest(case=case):
                self.store(item=item_data(**extra))
                r = self.close()
                self.assertEqual(r.returncode, 2, "the close of a %s item exited %d, want 2 for a done report: %s" % (case, r.returncode, r.stdout + r.stderr))
                self.assertTrue(any(line.startswith("unknown: item waits for a done report") for line in output_lines(r.stdout)),
                                "the refusal of a %s item does not say it waits for a done report: %r" % (case, r.stdout))
                self.assertNotIn('"writes"', r.stdout, "the refused close of a %s item printed a payload: %s" % (case, r.stdout))

    def test_a_close_batch_with_done_closes_an_item_on_a_lane_or_with_waits(self):
        for case, extra in (("lane", {"lane": "batch-runner"}), ("waits", {"waits": WAITS})):
            with self.subTest(case=case):
                self.store(item=item_data(**extra))
                item = self.write_for(self.good_payload("--done"), "items")
                self.assertIsNotNone(item, "the --done close of a %s item has no single items write" % case)
                self.assertEqual(item.get("data", {}).get("status"), "closed", "the --done close of a %s item does not close it: %r" % (case, item))

    def test_a_close_with_no_version_known_says_unpinned_on_stderr_and_pinned_false_in_the_payload(self):
        self.write_doc("item.json", item_data(), None)
        self.write_doc("answer.json", answer_data(), None)
        r = self.close()
        self.assertEqual(r.returncode, 0, "the unpinned close exited %d, want 0: %s" % (r.returncode, r.stdout + r.stderr))
        self.assertTrue(r.stderr.startswith("unpinned:"), "the close with no version known does not start its stderr with unpinned: %r" % r.stderr)
        self.assertTrue("item" in r.stderr and "answer" in r.stderr, "the unpinned line does not name the item and the answer: %r" % r.stderr)
        doc = json.loads(r.stdout)
        self.assertIs(doc.get("pinned"), False, "the close with no version known does not print pinned false: %r" % r.stdout)
        pinned = [w for w in doc.get("writes", []) if isinstance(w, dict) and "if_version" in w]
        self.assertEqual(pinned, [], "a write with no version known carries an if_version: %r" % pinned)

    def test_the_version_flags_pin_each_write_to_the_version_given(self):
        self.write_doc("item.json", item_data(), None)
        self.write_doc("answer.json", answer_data(), None)
        self.write_doc("receipt.json", {"read": CLOSE_AT}, None)
        r = self.close("--receipt", os.path.join(self.folder, "receipt.json"),
                       "--item-version", "9", "--answer-version", "8", "--receipt-version", "6")
        self.assertEqual(r.returncode, 0, "the close with version flags exited %d, want 0: %s" % (r.returncode, r.stdout + r.stderr))
        doc = json.loads(r.stdout)
        pins = {w.get("collection"): w.get("if_version") for w in doc.get("writes", []) if isinstance(w, dict)}
        self.assertEqual(pins, {"receipts": 6, "items": 9, "answers": 8}, "the version flags do not pin their writes: %r" % doc)
        self.assertIs(doc.get("pinned"), True, "a close with every version given does not print pinned true: %r" % r.stdout)

    def test_a_version_flag_beats_the_wrapper_version_and_the_wrapper_still_pins_where_no_flag_is_given(self):
        self.store()  # the wrapper holds item version 4 and answer version 2
        r = self.close("--item-version", "9")
        self.assertEqual(r.returncode, 0, "the close with --item-version exited %d, want 0: %s" % (r.returncode, r.stdout + r.stderr))
        doc = json.loads(r.stdout)
        pins = {w.get("collection"): w.get("if_version") for w in doc.get("writes", []) if isinstance(w, dict)}
        self.assertEqual(pins.get("items"), 9, "--item-version does not beat the wrapper's version 4: %r" % doc)
        self.assertEqual(pins.get("answers"), 2, "the answer with no flag does not keep its wrapper version 2: %r" % doc)

    def test_the_close_batch_writes_no_file(self):
        self.store()
        before = self.tree()
        self.close()
        self.assertEqual(self.tree(), before, "the close batch wrote or removed a file")


if __name__ == "__main__":
    unittest.main()
