#!/usr/bin/env python3
"""Cases for lint/check_shared_resources.py and layout.shared_resources(). Standard library only.

    python3 lint/test_check_shared_resources.py

Each case builds a temp repo with an extras file (and a git origin where the owner case needs one),
runs the real script with --root, and reads its exit code and FAIL lines.
SHARED_RESOURCES_UNDER_TEST overrides the script path.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per test run (lint/_test_temp.py)
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  rm_tree also removes the read-only git objects of a fixture (testing/tracked_tree.py)
SCRIPT = os.environ.get("SHARED_RESOURCES_UNDER_TEST") or os.path.join(HERE, "check_shared_resources.py")
EXTRAS = ".claude/layout-extras.json"
GOOD = {"name": "ha-green", "owner": "me/home", "preflight": "scripts/preflight.sh", "holds": "holds"}
RUN_FOLDER = None  # made in setUpModule, so an import leaks no folder


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    tracked_tree.rm_tree(RUN_FOLDER)  # test-temp-standard: teardown removes the run folder


class SharedResourcesTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(SCRIPT), "script absent: lint/check_shared_resources.py")
        self.root = tempfile.mkdtemp(prefix="shres_", dir=RUN_FOLDER)
        self.addCleanup(tracked_tree.rm_tree, self.root)

    def repo(self, extras, origin=None, files=()):
        os.makedirs(os.path.join(self.root, ".claude"))
        if extras is not None:
            with open(os.path.join(self.root, EXTRAS), "w", encoding="utf-8") as handle:
                handle.write(extras if isinstance(extras, str) else json.dumps(extras))
        if origin:
            os.makedirs(os.path.join(self.root, ".git"))
            with open(os.path.join(self.root, ".git", "config"), "w", encoding="utf-8") as handle:
                handle.write('[remote "origin"]\n\turl = https://github.com/%s.git\n' % origin)
        for rel in files:
            os.makedirs(os.path.dirname(os.path.join(self.root, rel)), exist_ok=True)
            open(os.path.join(self.root, rel), "w").close()

    def git(self, *args, env=None, stdin=None):
        """One git step of the fixture repo. Commit signing is off for the run (lint/_test_git.py)."""
        done = subprocess.run(["git", "-C", self.root, "-c", "user.name=test", "-c", "user.email=test@example.invalid", *args],
                              capture_output=True, text=True, input=stdin, env=env, timeout=30, check=True)
        return done.stdout

    def real_repo(self, checkout, origin_main):
        """A real git checkout: its working extras file holds `checkout`, and refs/remotes/origin/main holds the
        extras file `origin_main` (text), with no origin/HEAD. A read of origin's blob is live, not a config stub."""
        self.repo(checkout)
        self.git("init", "-q")
        env = dict(os.environ, GIT_INDEX_FILE=os.path.join(self.root, ".git", "main-index"))
        self.git("read-tree", "--empty", env=env)
        blob = self.git("hash-object", "-w", "--stdin", stdin=origin_main, env=env).strip()
        self.git("update-index", "--add", "--cacheinfo", "100644,%s,%s" % (blob, EXTRAS), env=env)
        tree = self.git("write-tree", env=env).strip()
        commit = self.git("commit-tree", tree, "-m", "main", env=env).strip()
        self.git("update-ref", "refs/remotes/origin/main", commit)
        done = subprocess.run(["git", "-C", self.root, "cat-file", "-e", "refs/remotes/origin/main:" + EXTRAS], capture_output=True)
        self.assertEqual(done.returncode, 0, "scope: origin/main holds no extras file")

    def run_check(self):
        done = subprocess.run([sys.executable, SCRIPT, "--root", self.root], capture_output=True, text=True)
        return done.returncode, done.stdout

    def entry(self, **changes):
        item = dict(GOOD, **changes)
        return {"kinds": {}, "shared-resources": [{k: v for k, v in item.items() if v is not None}]}

    def assertRed(self, *words):
        code, out = self.run_check()
        self.assertEqual(code, 1, out)
        self.assertIn("check_shared_resources: FAIL:", out)
        for word in words:
            self.assertIn(word, out)

    def test_no_key_is_green(self):
        self.repo({"kinds": {}})
        self.assertEqual(self.run_check(), (0, ""))

    def test_no_extras_file_is_green(self):
        self.repo(None)
        self.assertEqual(self.run_check(), (0, ""))

    def test_valid_entry_is_green(self):
        self.repo(self.entry())
        self.assertEqual(self.run_check(), (0, ""))

    def test_no_owner_is_red(self):
        self.repo(self.entry(owner=None))
        self.assertRed("layout-extras.json", "ha-green", "owner")

    def test_no_preflight_is_red(self):
        self.repo(self.entry(preflight=None))
        self.assertRed("ha-green", "preflight")

    def test_dotdot_path_is_red(self):
        self.repo(self.entry(preflight="../x/preflight.sh"))
        self.assertRed("ha-green", "not inside the repo")

    def test_absolute_holds_is_red(self):
        self.repo(self.entry(holds="/etc/holds"))
        self.assertRed("ha-green")

    def test_entry_not_an_object_is_red(self):
        self.repo({"kinds": {}, "shared-resources": ["ha-green"]})
        self.assertRed("layout-extras.json")

    def test_list_not_a_list_is_red(self):
        self.repo({"kinds": {}, "shared-resources": {"name": "x"}})
        self.assertRed("layout-extras.json")

    def test_owner_not_owner_slash_repo_is_red(self):
        self.repo(self.entry(owner="home"))
        self.assertRed("ha-green", "owner")

    def test_checkouts_own_bad_owner_is_red_when_origin_main_lacks_the_key(self):
        self.real_repo(self.entry(owner="not an owner"), json.dumps({"kinds": {}}))
        code, out = self.run_check()
        self.assertEqual(code, 1, "the checkout's own bad owner passed: the check read origin/main's file, not the checkout's. Output: %s" % out)
        self.assertIn("owner", out)

    def test_owner_repo_missing_preflight_file_is_red(self):
        self.repo(self.entry(), origin="Me/Home")
        self.assertRed("ha-green", "scripts/preflight.sh")

    def test_owner_repo_with_preflight_file_is_green(self):
        self.repo(self.entry(), origin="Me/Home", files=("scripts/preflight.sh",))
        self.assertEqual(self.run_check(), (0, ""))

    def test_user_repo_needs_no_local_preflight_file(self):
        self.repo(self.entry(), origin="me/degen")
        self.assertEqual(self.run_check(), (0, ""))

    def test_owner_with_dot_git_is_red(self):
        self.repo(self.entry(owner="me/home.git"), origin="Me/Home")
        self.assertRed("ha-green", "owner")

    def test_no_name_is_red(self):
        self.repo(self.entry(name=None))
        self.assertRed("layout-extras.json", "entry 1", "name")

    def test_empty_name_is_red(self):
        self.repo(self.entry(name=" "))
        self.assertRed("name")

    def test_duplicate_name_is_red(self):
        extras = self.entry()
        extras["shared-resources"].append(dict(GOOD, holds="other"))
        self.repo(extras)
        self.assertRed("ha-green", "twice")

    def test_preflight_with_whitespace_is_red(self):
        self.repo(self.entry(preflight="scripts/preflight.sh "))
        self.assertRed("ha-green", "whitespace")

    def test_holds_with_leading_whitespace_is_red(self):
        self.repo(self.entry(holds=" holds"))
        self.assertRed("ha-green", "whitespace")

    def test_unreadable_extras_is_red(self):
        self.repo("{not json")
        self.assertRed("cannot read")

    def test_cli_verb_prints_the_list(self):
        self.repo(self.entry())
        done = subprocess.run([sys.executable, os.path.join(HERE, "layout.py"), "shared-resources", self.root],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout), [GOOD])


if __name__ == "__main__":
    unittest.main()
