#!/usr/bin/env python3
"""Cases for lint/find_copies.py. Standard library only.

    python3 lint/test_find_copies.py

Each case builds a temp parent and a temp child, then runs the real script on them. The
fixtures copy the shape of the worked examples: q_max's drifted plain-english-map skill,
q_max's verbatim copy of a parent test with a header added, and the impeccable copies in
ios-adblock, joyous and degen, which differ from the parent and from each other.
FIND_COPIES_UNDER_TEST overrides the module path.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.environ.get("FIND_COPIES_UNDER_TEST") or os.path.join(HERE, "find_copies.py")
# test-temp-standard (one run folder per test run): the repo's one temp root and run folder
# name, as in hooks/test_guard.py. Its sweep removes a run folder that a crashed run left here.
TEMP_ROOT = os.path.join(tempfile.gettempdir(), "claude-settings-test-temp")
RUN_FOLDER = os.path.join(TEMP_ROOT, "%d-%s" % (os.getpid(), uuid.uuid4().hex))

SKILL_MD = "---\nname: {name}\ndescription: A shared skill for the fixture.\n---\n\n" + "".join(
    f"Step {i}: do the shared thing number {i} with care.\n" for i in range(12)
)
HELPER = "".join(f"export function helper{i}(value) {{ return value * {i} + 1; }}\n" for i in range(15))
TEST = "// Red proof: node --test testing/\nimport { helper } from './helper.mjs';\n" + "".join(
    f"test('case {i} keeps its promise', () => assert.equal(helper({i}), {i * 2}));\n" for i in range(15)
)
# Comment openers inside strings, a multi-line template literal and a lone quote in text.
TRAPS = (
    "const a = 'not /* a comment';\nconst b = \"not // a comment either\";\nconst c = `line one\n"
    "line two # not a comment`;\nconst d = <p>Don't stop here</p>;\n"
    + "".join(f"const keep{i} = 'value number {i} for the trap file';\n" for i in range(10))
)


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def make_parent(root):
    write(root, "skills/impeccable/SKILL.md", SKILL_MD.format(name="impeccable"))
    write(root, "skills/impeccable/scripts/run.mjs", HELPER)
    write(root, "skills/impeccable/reference/document.md", "".join(f"Rule {i} of the reference.\n" for i in range(12)))
    write(root, "skills/plain-english-map/SKILL.md", SKILL_MD.format(name="plain-english-map"))
    write(root, "skills/plain-english-map/scripts/map-check.mjs", HELPER)
    write(root, "skills/plain-english-map/scripts/map-upgrade.mjs", HELPER.replace("helper", "upgrade"))
    write(root, "testing/skip-locally-fail-in-ci.test.mjs", TEST)
    write(root, "lint/traps.mjs", TRAPS)
    write(root, "LICENSE", "MIT License\n" * 30)
    write(root, "actions/stamp/examples/frontmatter.stamp.json", HELPER)


def run(parent, child, *extra):
    proc = subprocess.run(
        [sys.executable, MODULE, child, "--parent", parent, *extra],
        capture_output=True, text=True, timeout=60,
    )
    return proc


class FindCopiesTest(unittest.TestCase):
    def setUp(self):
        os.makedirs(RUN_FOLDER, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=RUN_FOLDER)
        self.parent = os.path.join(self.tmp.name, "parent")
        self.child = os.path.join(self.tmp.name, "child")
        make_parent(self.parent)
        os.makedirs(self.child)

    def tearDown(self):
        self.tmp.cleanup()

    def findings(self, *extra):
        proc = run(self.parent, self.child, "--json", *extra)
        self.assertIn(proc.returncode, (0, 1), proc.stderr)
        return proc.returncode, json.loads(proc.stdout)

    def test_clean_child_is_quiet(self):
        write(self.child, "src/app.ts", "".join(f"export const own{i} = {i};\n" for i in range(20)))
        write(self.child, "LICENSE", "MIT License\n" * 30)
        proc = run(self.parent, self.child)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("no copies", proc.stdout)

    def test_drifted_skill_copy(self):
        # q_max shape: the copy lags the parent, with edits and a missing file.
        base = ".claude/skills/plain-english-map"
        write(self.child, f"{base}/SKILL.md", SKILL_MD.format(name="plain-english-map") + "A local edit.\n")
        write(self.child, f"{base}/scripts/map-check.mjs", HELPER)
        code, out = self.findings()
        self.assertEqual(code, 1)
        skills = [f for f in out["skills"] if f["skill"] == "plain-english-map"]
        self.assertEqual(len(skills), 1, out)
        s = skills[0]
        self.assertEqual(s["child_path"], base)
        self.assertEqual(s["state"], "drifted")
        self.assertEqual(s["differ"], ["SKILL.md"])
        self.assertEqual(s["only_in_parent"], ["scripts/map-upgrade.mjs"])
        # Files inside a reported skill copy are not reported again as file copies.
        self.assertEqual([f for f in out["files"] if f["child"].startswith(base)], [])

    def test_identical_skill_copy_is_still_a_copy(self):
        base = ".claude/skills/impeccable"
        write(self.child, f"{base}/SKILL.md", SKILL_MD.format(name="impeccable"))
        write(self.child, f"{base}/scripts/run.mjs", HELPER)
        write(self.child, f"{base}/reference/document.md", "".join(f"Rule {i} of the reference.\n" for i in range(12)))
        code, out = self.findings()
        self.assertEqual(code, 1)
        self.assertEqual([(s["skill"], s["state"]) for s in out["skills"]], [("impeccable", "same")])

    def test_three_impeccable_copies_that_differ(self):
        # ios-adblock, joyous and degen each hold a copy that differs from the parent and from
        # the others. Each child is its own run, so each run reports its own copy.
        edits = {
            "ios-adblock": ("SKILL.md", "Edited for ios-adblock.\n"),
            "joyous": ("scripts/run.mjs", "// joyous edit\n"),
            "degen": ("reference/document.md", "Degen's own rule.\n"),
        }
        for repo, (rel, extra) in edits.items():
            child = os.path.join(self.tmp.name, repo)
            base = os.path.join(child, ".claude/skills/impeccable")
            write(base, "SKILL.md", SKILL_MD.format(name="impeccable"))
            write(base, "scripts/run.mjs", HELPER)
            write(base, "reference/document.md", "".join(f"Rule {i} of the reference.\n" for i in range(12)))
            with open(os.path.join(base, rel), "a", encoding="utf-8") as f:
                f.write(extra)
            proc = run(self.parent, child, "--json")
            self.assertEqual(proc.returncode, 1, repo + proc.stderr)
            out = json.loads(proc.stdout)
            self.assertEqual(len(out["skills"]), 1, repo)
            self.assertEqual(out["skills"][0]["state"], "drifted", repo)
            self.assertEqual(out["skills"][0]["differ"], [rel], repo)

    def test_skill_found_by_frontmatter_name_under_another_folder(self):
        write(self.child, "tools/map-skill/SKILL.md", SKILL_MD.format(name="plain-english-map"))
        code, out = self.findings()
        self.assertEqual(code, 1)
        self.assertEqual([(s["skill"], s["child_path"]) for s in out["skills"]],
                         [("plain-english-map", "tools/map-skill")])

    def test_verbatim_test_copy_with_header(self):
        # q_max shape: the parent test, with a provenance header added on top.
        header = "// Copied verbatim from claude-settings, testing/skip-locally-fail-in-ci.test.mjs.\n// Import path adapted.\n"
        write(self.child, "harness/tests/skip-locally-fail-in-ci.test.mjs", header + TEST)
        code, out = self.findings()
        self.assertEqual(code, 1)
        self.assertEqual(len(out["files"]), 1, out)
        f = out["files"][0]
        self.assertEqual(f["parent"], "testing/skip-locally-fail-in-ci.test.mjs")
        self.assertEqual(f["child"], "harness/tests/skip-locally-fail-in-ci.test.mjs")
        self.assertEqual(f["kind"], "near-equal")
        self.assertGreaterEqual(f["score"], 0.8)

    def test_byte_equal_file_under_another_name(self):
        write(self.child, "vendor/whatever.mjs", TEST)
        code, out = self.findings()
        self.assertEqual(code, 1)
        self.assertEqual([(f["parent"], f["kind"]) for f in out["files"]],
                         [("testing/skip-locally-fail-in-ci.test.mjs", "byte-equal")])

    def test_scanner_traps_compare_as_plain_text(self):
        write(self.child, "src/traps.mjs", TRAPS)
        code, out = self.findings()
        self.assertEqual(code, 1)
        self.assertEqual([(f["parent"], f["kind"]) for f in out["files"]], [("lint/traps.mjs", "byte-equal")])

    def test_shared_boilerplate_is_not_a_copy(self):
        # A file that shares a few common lines with a parent file is not a copy.
        write(self.child, "src/other.mjs", HELPER[:200] + "".join(f"const mine{i} = {i};\n" for i in range(40)))
        code, out = self.findings()
        self.assertEqual(code, 0, out)

    def test_parent_example_is_meant_to_be_copied(self):
        write(self.child, ".github/stamp.json", HELPER.replace("helper1(", "local1("))
        code, out = self.findings()
        self.assertEqual([f["parent"] for f in out["files"]],
                         ["skills/impeccable/scripts/run.mjs"])

    def test_missing_child_is_unknown(self):
        proc = run(self.parent, os.path.join(self.tmp.name, "nowhere"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("unknown", proc.stdout + proc.stderr)

    def test_reads_only(self):
        write(self.child, "harness/tests/copy.test.mjs", TEST)
        before = sorted(os.walk(self.child))
        run(self.parent, self.child)
        self.assertEqual(before, sorted(os.walk(self.child)))


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        shutil.rmtree(RUN_FOLDER, ignore_errors=True)
