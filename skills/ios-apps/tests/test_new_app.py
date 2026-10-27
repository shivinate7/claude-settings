#!/usr/bin/env python3
"""Cases for skills/ios-apps/scripts/new_app.py, the new iOS app starter. Standard library only.

    python3 skills/ios-apps/tests/test_new_app.py

Each case runs the starter into an empty temp folder. The cases prove the file list, the standard
the tree holds (Swift 6, iOS 26, XcodeGen, the make targets, the pinned CI runner, the ios-ship
entry with no account IDs), that the generated tokens file matches its source, and that the
starter refuses a bad name and an existing file. No case needs a Mac: the Mac half is `make
native-check` in the new repo.
"""
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(SKILL))
sys.path.insert(0, os.path.join(SKILL, "scripts"))
sys.path.insert(0, os.path.join(REPO, "lint"))
import new_app  # noqa: E402
import compliance_probes  # noqa: E402  the probe's runner constant is the one the starter writes

ARGS = ["--name", "Tally", "--bundle-id", "dev.example.tally", "--repo-url", "https://github.com/example/tally.git"]
EXPECTED = [
    ".github/workflows/ios.yml",
    ".gitignore",
    "Makefile",
    "native/Tally/Assets.xcassets/AppIcon.appiconset/Contents.json",
    "native/Tally/Assets.xcassets/Contents.json",
    "native/Tally/ContentView.swift",
    "native/Tally/TallyApp.swift",
    "native/TallyKit/Package.swift",
    "native/TallyKit/Sources/TallyKit/Greeting.swift",
    "native/TallyKit/Sources/TallyKit/Tokens.swift",
    "native/TallyKit/Tests/TallyKitTests/GreetingTests.swift",
    "native/TallyUITests/LaunchTests.swift",
    "native/project.yml",
    "tokens/tokens.json",
    "tools/gen-tokens.py",
    "tools/ios-ship.json",
]
PLACEHOLDER = r"__[A-Z][A-Z_]*__"
# The account values bin/ios-ship reads from the account file. None may sit in a repo.
ACCOUNT_KEYS = {"team_id", "device_udid", "asc_key_path", "asc_key_id", "asc_issuer_id"}


def run(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = new_app.main(list(args))
    return code, out.getvalue(), err.getvalue()


def tree(root):
    found = {}
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            path = os.path.join(base, name)
            with open(path, encoding="utf-8") as f:
                found[os.path.relpath(path, root).replace(os.sep, "/")] = f.read()
    return found


def targets(makefile):
    return {m.group(1): m.group(2) for m in re.finditer(r"^([\w-]+):[^\n=]*\n((?:\t[^\n]*\n)*)", makefile, re.M)}


class Starter(unittest.TestCase):
    def setUp(self):
        self.dest = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dest)

    def made(self):
        code, out, err = run(self.dest, *ARGS)
        self.assertEqual(code, 0, err)
        return tree(self.dest)

    def test_writes_the_tree(self):
        files = self.made()
        self.assertEqual(sorted(files), EXPECTED)
        for rel, text in files.items():
            self.assertNotRegex(text, PLACEHOLDER, rel)
            self.assertNotRegex(rel, PLACEHOLDER)

    def test_project_is_xcodegen_swift_6_ios_26(self):
        spec = self.made()["native/project.yml"]
        self.assertIn('SWIFT_VERSION: "6.0"', spec)
        self.assertIn('iOS: "26.0"', spec)
        self.assertNotRegex(spec, r"SWIFT_VERSION: \"?5")
        self.assertIn("TallyKit:\n    path: TallyKit", spec)
        self.assertIn("PRODUCT_BUNDLE_IDENTIFIER: dev.example.tally", spec)
        self.assertIn("bundleIdPrefix: dev.example", spec)
        self.assertNotIn("DEVELOPMENT_TEAM", spec)

    def test_kit_package_is_swift_6(self):
        files = self.made()
        package = files["native/TallyKit/Package.swift"]
        self.assertRegex(package, r"^// swift-tools-version: 6\.\d")
        self.assertNotIn(".v5", package)
        self.assertIn("import Testing", files["native/TallyKit/Tests/TallyKitTests/GreetingTests.swift"])
        self.assertIn("import XCTest", files["native/TallyUITests/LaunchTests.swift"])

    def test_make_targets(self):
        make = targets(self.made()["Makefile"])
        for name in ("phone", "testflight", "native-check", "kit-test", "app-build", "ui-test", "tokens", "tokens-check"):
            self.assertIn(name, make)
        self.assertIn("ios-ship install", make["phone"])
        self.assertIn("ios-ship testflight", make["testflight"])
        self.assertIn("sim-test", make["ui-test"])
        self.assertIn("swift test", make["kit-test"])
        self.assertIn("build-for-testing", make["app-build"])

    def test_ci_runs_the_fast_targets_on_the_pinned_runner(self):
        ci = self.made()[".github/workflows/ios.yml"]
        runners = re.findall(r"runs-on: (\S+)", ci)
        self.assertIn(compliance_probes.IOS_RUNNER, runners)
        self.assertNotIn("macos-latest", runners)
        for step in ("make tokens-check", "make kit-test", "make app-build"):
            self.assertIn(step, ci)
        self.assertNotIn("ui-test", ci)
        self.assertIn("github.event.pull_request.draft", ci)
        for use in re.findall(r"uses: (\S+)", ci):
            self.assertRegex(use, r"@[0-9a-f]{40}$")
        self.assertIn("persist-credentials: false", ci)

    def test_ship_entry_has_no_account_ids(self):
        cfg = json.loads(self.made()["tools/ios-ship.json"])
        self.assertEqual(cfg["repo_url"], "https://github.com/example/tally.git")
        self.assertFalse(ACCOUNT_KEYS & set(cfg))
        self.assertEqual(cfg["apps"], [{"name": "Tally", "scheme": "Tally", "bundle_id": "dev.example.tally",
                                        "project_dir": "native", "project_yml": "project.yml"}])

    def test_tokens_are_generated_from_their_source(self):
        files = self.made()
        swift = files["native/TallyKit/Sources/TallyKit/Tokens.swift"]
        self.assertIn("Generated by tools/gen-tokens.py", swift)
        gen = os.path.join(self.dest, "tools", "gen-tokens.py")
        check = [sys.executable, gen, "--check"]
        self.assertEqual(subprocess.run(check, cwd=self.dest, capture_output=True).returncode, 0)
        source = os.path.join(self.dest, "tokens", "tokens.json")
        data = json.loads(files["tokens/tokens.json"])
        data["color"]["accent"]["dark"] = "#123456"
        with open(source, "w", encoding="utf-8") as f:
            json.dump(data, f)
        self.assertEqual(subprocess.run(check, cwd=self.dest, capture_output=True).returncode, 1)
        self.assertEqual(subprocess.run([sys.executable, gen], cwd=self.dest, capture_output=True).returncode, 0)
        self.assertEqual(subprocess.run(check, cwd=self.dest, capture_output=True).returncode, 0)
        with open(os.path.join(self.dest, "native/TallyKit/Sources/TallyKit/Tokens.swift"), encoding="utf-8") as f:
            self.assertIn("0x12", f.read().lower())

    def test_refuses_an_existing_file_and_writes_nothing(self):
        os.makedirs(os.path.join(self.dest, "tools"))
        with open(os.path.join(self.dest, "tools", "ios-ship.json"), "w", encoding="utf-8") as f:
            f.write("{}")
        code, _, err = run(self.dest, *ARGS)
        self.assertEqual(code, 1)
        self.assertIn("tools/ios-ship.json", err)
        self.assertEqual(sorted(tree(self.dest)), ["tools/ios-ship.json"])

    def test_refuses_bad_arguments(self):
        for bad in (["--name", "tally"], ["--name", "Tal ly"], ["--name", "SwiftUI"], ["--bundle-id", "tally"],
                    ["--repo-url", "nope"], ["--repo-url", 'https://github.com/e/t".git'], ["--repo-url", "https://github.com/e\\t"]):
            args = list(ARGS)
            i = args.index(bad[0])
            args[i + 1] = bad[1]
            code, _, _ = run(self.dest, *args)
            self.assertEqual(code, 2, bad)
        self.assertEqual(tree(self.dest), {})

    def test_a_failed_write_removes_what_it_made(self):
        real, calls = open, []

        def failing(path, mode="r", *args, **kwargs):
            if "x" in mode:
                calls.append(path)
                if len(calls) == 5:
                    raise OSError("disk full")
            return real(path, mode, *args, **kwargs)

        new_app.open = failing
        self.addCleanup(delattr, new_app, "open")
        code, _, err = run(os.path.join(self.dest, "app"), *ARGS)
        self.assertEqual(code, 1)
        self.assertIn("disk full", err)
        self.assertEqual(os.listdir(self.dest), [])


if __name__ == "__main__":
    unittest.main()
