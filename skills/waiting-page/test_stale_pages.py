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
CMD = os.environ.get("STALE_PAGES_UNDER_TEST") or os.path.join(HERE, "stale_pages.py")
LINT = os.path.realpath(os.path.join(HERE, "..", "..", "lint"))
HOOKS = os.path.realpath(os.path.join(HERE, "..", "..", "hooks"))
sys.path.insert(0, LINT)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)

RUN_FOLDER = _test_temp.run_folder()  # test-temp-standard (one run folder per test run)
TEMPLATE = os.path.join(HERE, "page.html")
with open(TEMPLATE, encoding="utf-8") as f:
    PAGE = f.read()
URL = "https://claude.ai/artifact/%s"

# Fixtures, all derived from page.html at run time. A live page holds < escapes in its mockups.
BLOCK = re.compile(r'(<script type="application/json" id="designData">)(.*?)(</script>)', re.S)
ALTERED = PAGE.replace("<title>", "<title>Altered ", 1)  # differs outside designData only
STALE_BODY = r'{"a": "<p>mock</p>", "b": "<i>raw</i>"}'
MOCK_BODY = r'{"a": "<p>mockup</p>", "b": "<i>raw</i>"}'
VERDICT = re.compile(r"\b(current|behind|unknown)\b")


def set_body(text, body):
    """The text with its designData body replaced. A function replacement keeps the body's backslashes."""
    return BLOCK.sub(lambda m: m.group(1) + body + m.group(3), text, count=1)


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return path


def link_repo_dirs(claude):
    """A fake ~/.claude gets this repo's lint and hooks folders, as a real install has both."""
    os.symlink(LINT, os.path.join(claude, "lint"))
    os.symlink(HOOKS, os.path.join(claude, "hooks"))


def git(cwd, *args):
    """One git step of a fixture clone. The timeout bounds it, as it bounds every script run."""
    return subprocess.run(["git", "-C", cwd, "-c", "user.name=test", "-c", "user.email=test@example.invalid",
                           "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
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

    def assert_source_run(self, page, home, script, code, word, source):
        """One run under a fake HOME: the exit code, the verdict, and the one template source it names."""
        r = self.page_run(page, home=home, script=script)
        self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        got, line = self.verdict(r)
        self.assertEqual(got, word, line)
        self.assertIn(source, line)
        self.assertNotIn("installed copy" if source == "origin/main" else "origin/main", line)

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

    def test_template_source_is_named_and_the_pointer_chooses_it(self):
        clone = self.make_clone("clone", {"skills/waiting-page/page.html": PAGE, "CLAUDE.md": "# claude-settings\n"})
        home = os.path.join(self.tmp.name, "home")
        claude = os.path.join(home, ".claude")
        installed = os.path.join(claude, "skills", "waiting-page")
        os.makedirs(installed)
        probe = subprocess.run(["git", "-C", installed, "rev-parse", "--is-inside-work-tree"],
                               capture_output=True, text=True, timeout=30)
        self.assertNotEqual(probe.returncode, 0, "the temp folder is inside a git checkout, so the script finds that")
        shutil.copy2(CMD, os.path.join(installed, "stale_pages.py"))
        write_text(os.path.join(installed, "page.html"), ALTERED)
        link_repo_dirs(claude)
        pointer =write_text(os.path.join(claude, "CLAUDE.md"), "@%s/CLAUDE.md\n" % clone)
        script = os.path.join(installed, "stale_pages.py")
        same = write_text(os.path.join(self.fetched, "same.html"), PAGE)  # equals origin/main
        old = write_text(os.path.join(self.fetched, "old.html"), ALTERED)  # equals the installed copy
        with self.subTest("pointer: origin/main page is current"):
            self.assert_source_run(same, home, script, 0, "current", "origin/main")
        with self.subTest("pointer: installed page is behind origin/main"):
            self.assert_source_run(old, home, script, 1, "behind", "origin/main")
        write_text(pointer, "# no pointer here\n")
        with self.subTest("no pointer: installed page is current"):
            self.assert_source_run(old, home, script, 0, "current", "installed copy")
        with self.subTest("no pointer: origin/main page is behind the installed copy"):
            self.assert_source_run(same, home, script, 1, "behind", "installed copy")
        plain = write_text(os.path.join(self.tmp.name, "plain", "CLAUDE.md"), "# not a checkout\n")
        write_text(pointer, "@%s\n" % plain)
        with self.subTest("pointer to a folder with no git read: installed copy"):
            self.assert_source_run(old, home, script, 0, "current", "installed copy")

    def test_script_run_from_inside_a_checkout_reads_that_checkouts_origin_main(self):
        with open(CMD, encoding="utf-8") as f:
            script_text = f.read()
        clone = self.make_clone("own", {"skills/waiting-page/page.html": PAGE,
                                        "skills/waiting-page/stale_pages.py": script_text})
        home = os.path.join(self.tmp.name, "home")
        os.makedirs(os.path.join(home, ".claude", "skills", "waiting-page"))
        link_repo_dirs(os.path.join(home, ".claude"))
        script =os.path.join(home, ".claude", "skills", "waiting-page", "stale_pages.py")
        os.symlink(os.path.join(clone, "skills", "waiting-page", "stale_pages.py"), script)
        same = write_text(os.path.join(self.fetched, "same.html"), PAGE)
        old = write_text(os.path.join(self.fetched, "old.html"), ALTERED)
        with self.subTest("origin/main page is current"):
            self.assert_source_run(same, home, script, 0, "current", "origin/main")
        with self.subTest("older page is behind origin/main"):
            self.assert_source_run(old, home, script, 1, "behind", "origin/main")

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
    try:
        unittest.main()
    finally:
        shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder
