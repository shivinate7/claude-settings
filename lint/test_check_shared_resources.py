#!/usr/bin/env python3
"""Cases for lint/check_shared_resources.py and layout.shared_resources(). Standard library only.

    python3 lint/test_check_shared_resources.py

Each case builds a temp repo with an extras file (and a git origin where the owner case needs one),
runs the real script with --root, and reads its exit code and FAIL lines.
SHARED_RESOURCES_UNDER_TEST overrides the script path.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.environ.get("SHARED_RESOURCES_UNDER_TEST") or os.path.join(HERE, "check_shared_resources.py")
EXTRAS = ".claude/layout-extras.json"
GOOD = {"name": "ha-green", "owner": "me/home", "preflight": "scripts/preflight.sh", "holds": "holds"}


class SharedResourcesTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(SCRIPT), "script absent: lint/check_shared_resources.py")
        self.root = tempfile.mkdtemp(prefix="shres_")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

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

    def test_owner_repo_missing_preflight_file_is_red(self):
        self.repo(self.entry(), origin="Me/Home")
        self.assertRed("ha-green", "scripts/preflight.sh")

    def test_owner_repo_with_preflight_file_is_green(self):
        self.repo(self.entry(), origin="Me/Home", files=("scripts/preflight.sh",))
        self.assertEqual(self.run_check(), (0, ""))

    def test_user_repo_needs_no_local_preflight_file(self):
        self.repo(self.entry(), origin="me/degen")
        self.assertEqual(self.run_check(), (0, ""))

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
