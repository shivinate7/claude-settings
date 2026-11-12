#!/usr/bin/env python3
"""Cases for lint/check_health_map.py. Standard library only.

    python3 lint/test_check_health_map.py

docs/health-map.json holds rows. Each row says what a part of the repo sees, its grade, and the globs that
cover it. The check reads every hook, check and skill, and fails on a part that no row's covers glob matches.
A map it cannot read is unknown: the run exits 2 and never prints the covers-all line.

Each case writes a fixture root under this run's folder (test-temp-standard, lint/_test_temp.py), then runs
the real script with --root on it. CHECK_HEALTH_MAP_UNDER_TEST overrides the module path.

Exit 2 is also what Python prints for a script it cannot open, and what argparse prints for a bad flag. So an
unknown case asserts a reason word that neither prints. It also asserts no traceback, no can't-open line
and no usage line.

No string scanner here: the check matches path globs and reads no source text.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)

MODULE = os.environ.get("CHECK_HEALTH_MAP_UNDER_TEST") or os.path.join(HERE, "check_health_map.py")
MAP = os.path.join("docs", "health-map.json")
GRADES = ("green", "amber", "red", "grey")
CLEAR = "health map covers all"
ALL_LINE = CLEAR + " %d parts"
RUN_FOLDER = None  # made in setUpModule, so an import leaks no folder

# One hook of each extension, one check, and one skill directory with a file in it.
BASE_PARTS = ["hooks/guard.py", "hooks/notify.mjs", "hooks/stop.sh", "lint/check_alpha.py", "skills/alpha/SKILL.md"]
BASE_UNCOVERED = [
    "uncovered hook: hooks/guard.py",
    "uncovered hook: hooks/notify.mjs",
    "uncovered hook: hooks/stop.sh",
    "uncovered check: lint/check_alpha.py",
    "uncovered skill: skills/alpha/",
]
# Narrow globs. Each covers one base part, so a part added later matches none of them.
NARROW_COVERS = [["hooks/guard*.py"], ["hooks/notify*.mjs"], ["hooks/stop*.sh"], ["lint/check_alpha*.py"], ["skills/alpha*"]]
# Broad globs. "skills/*" matches the directory part whether or not the part path keeps its trailing slash.
BROAD_COVERS = [["hooks/*.py"], ["hooks/*.mjs"], ["hooks/*.sh"], ["lint/check_*.py"], ["skills/*"]]


def row(n, covers, grade="green"):
    return {"n": n, "sees": "fixture part %d" % n, "grade": grade, "why": "fixture row %d" % n, "covers": covers}


def rows_for(covers_list):
    """One row per covers list, numbered from 1 and graded in turn, so all four grades appear."""
    return [row(i + 1, c, GRADES[i % len(GRADES)]) for i, c in enumerate(covers_list)]


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


class HealthMapTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="health_", dir=RUN_FOLDER)

    def write(self, rel, text="# fixture\n", root=None):
        path = os.path.join(root or self.root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        return path

    def write_map(self, rows):
        self.write(MAP, json.dumps({"rows": rows}, indent=2) + "\n")

    def write_parts(self, rels=BASE_PARTS):
        for rel in rels:
            self.write(rel)

    def fixture(self, extra=()):
        """The base parts, each covered by a narrow glob, plus any extra part files."""
        self.write_parts()
        for rel in extra:
            self.write(rel)
        self.write_map(rows_for(NARROW_COVERS))

    def check(self, *extra):
        cmd = [sys.executable, MODULE, "--root", self.root] + list(extra)
        r = subprocess.run(cmd, cwd=RUN_FOLDER, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        return r.returncode, r.stdout + r.stderr

    def uncovered(self, out):
        return [ln for ln in out.splitlines() if ln.startswith("uncovered ")]

    def assert_clear(self, rc, out, n):
        self.assertEqual(rc, 0, "every part is covered, so the run must exit 0\n" + out)
        self.assertIn(ALL_LINE % n, out.splitlines(),
                      "the clear line for %d parts is missing\n%s" % (n, out))
        self.assertEqual(self.uncovered(out), [], "a clear run named an uncovered part\n" + out)

    def assert_uncovered(self, rc, out, expected):
        self.assertEqual(rc, 1, "an uncovered part must exit 1\n" + out)
        self.assertCountEqual(self.uncovered(out), expected,
                              "the uncovered lines are not the parts with no covering row\n" + out)
        self.assertNotIn(CLEAR, out, "a run with an uncovered part printed the clear line\n" + out)

    def assert_unknown(self, rc, out, token):
        self.assertEqual(rc, 2, "an unreadable or invalid map must exit 2\n" + out)
        self.assertIn(token, out.lower(), "the reason does not name %r\n%s" % (token, out))
        self.assertNotIn(CLEAR, out, "an unreadable map printed the clear line\n" + out)
        for bad in ("Traceback", "can't open file", "usage:"):
            self.assertNotIn(bad.lower(), out.lower(),
                             "the exit 2 came from the interpreter or argparse, not the check (%s)\n%s" % (bad, out))

    def test_0_control_fixture_is_written_under_the_run_folder(self):
        # Green on the old code: it shows the harness writes its fixtures under this run's folder.
        path = self.write("hooks/x.py", "A = 1\n")
        self.assertTrue(path.startswith(RUN_FOLDER + os.sep), "fixture left the run folder: " + path)
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "A = 1\n", "fixture text did not read back")

    def test_1_every_part_covered_exits_0_and_counts_each_part(self):
        self.write_parts()
        self.write("skills/README.md", "not a skill directory\n")  # a stray file in skills/ is not a part
        self.write_map(rows_for(BROAD_COVERS))
        rc, out = self.check()
        self.assert_clear(rc, out, 5)

    def test_2_uncovered_hook_is_named(self):
        self.fixture(["hooks/extra.py"])
        rc, out = self.check()
        self.assert_uncovered(rc, out, ["uncovered hook: hooks/extra.py"])

    def test_3_uncovered_check_is_named(self):
        self.fixture(["lint/check_beta.py"])
        rc, out = self.check()
        self.assert_uncovered(rc, out, ["uncovered check: lint/check_beta.py"])

    def test_4_uncovered_skill_directory_is_named(self):
        self.fixture(["skills/beta/SKILL.md"])
        rc, out = self.check()
        self.assert_uncovered(rc, out, ["uncovered skill: skills/beta/"])

    def test_5_uncovered_mjs_and_sh_hooks_are_named(self):
        self.fixture(["hooks/extra.mjs", "hooks/extra.sh"])
        rc, out = self.check()
        self.assert_uncovered(rc, out, ["uncovered hook: hooks/extra.mjs", "uncovered hook: hooks/extra.sh"])

    def test_6_test_files_are_not_parts(self):
        # The one real uncovered hook proves the scan reached hooks/. The test files must not join it.
        self.fixture(["hooks/extra.py", "hooks/test_extra.py", "hooks/extra_test.py", "hooks/_test_extra.py",
                      "hooks/test_extra.mjs", "hooks/test_extra.sh", "lint/test_check_beta.py"])
        rc, out = self.check()
        self.assert_uncovered(rc, out, ["uncovered hook: hooks/extra.py"])

    def test_7_glob_matching_a_directory_skill_covers_it(self):
        self.write("skills/gamma/SKILL.md")
        self.write("skills/gamma/notes.md")  # a file inside a skill directory is not a part
        self.write("skills/README.md")
        self.write_map(rows_for([["skills/ga*"]]))
        rc, out = self.check()
        self.assert_clear(rc, out, 1)

    def test_8_bad_grade_exits_2(self):
        self.write_parts()
        rows = rows_for(NARROW_COVERS)
        rows[2]["grade"] = "purple"
        self.write_map(rows)
        rc, out = self.check()
        self.assert_unknown(rc, out, "grade")
        self.assertIn("purple", out.lower(), "the reason does not name the bad grade value\n" + out)

    def test_9_missing_map_exits_2(self):
        self.write_parts()  # no docs/health-map.json at all
        rc, out = self.check()
        self.assert_unknown(rc, out, "health-map.json")

    def test_10_invalid_json_map_exits_2(self):
        self.write_parts()
        self.write(MAP, "{not json")
        rc, out = self.check()
        self.assert_unknown(rc, out, "json")

    def test_11_duplicate_n_exits_2(self):
        self.write_parts()
        rows = rows_for(NARROW_COVERS[:2])
        rows[1]["n"] = rows[0]["n"]
        self.write_map(rows)
        rc, out = self.check()
        self.assert_unknown(rc, out, "duplicate")

    def test_12_empty_covers_exits_2(self):
        self.write_parts()
        rows = rows_for(NARROW_COVERS[:2])
        rows[0]["covers"] = []
        self.write_map(rows)
        rc, out = self.check()
        self.assert_unknown(rc, out, "covers")

    def test_13_map_without_a_rows_list_exits_2(self):
        self.write_parts()
        self.write(MAP, json.dumps({"rowz": rows_for(NARROW_COVERS)}) + "\n")
        rc, out = self.check()
        self.assert_unknown(rc, out, "rows")

    def test_14_new_hook_added_to_a_green_fixture_is_flagged(self):
        self.fixture()
        rc, out = self.check()  # the green run first, so the new file is the only change
        self.assert_clear(rc, out, 5)
        self.write("hooks/new.py")
        rc, out = self.check()
        self.assert_uncovered(rc, out, ["uncovered hook: hooks/new.py"])

    def test_15_empty_rows_leave_every_part_uncovered(self):
        # Empty map state. The default docs/health-map.json is the one read when --map is not given.
        self.write_parts()
        self.write_map([])
        rc, out = self.check()
        self.assert_uncovered(rc, out, BASE_UNCOVERED)

    def test_16_map_flag_is_read_instead_of_the_default(self):
        self.write_parts()
        self.write_map([])  # the default map covers nothing
        rc, out = self.check()  # the default run first: it must read the empty default and exit 1
        self.assert_uncovered(rc, out, BASE_UNCOVERED)
        alt = self.write(os.path.join("maps", "alt.json"),
                         json.dumps({"rows": rows_for(BROAD_COVERS)}) + "\n")
        rc, out = self.check("--map", alt)
        self.assert_clear(rc, out, 5)

    def test_17_full_size_tree_names_only_the_late_uncovered_part(self):
        # 300 hooks covered by one glob, then a hook the glob misses that sorts last. A check that stops
        # reading early never reaches it.
        for i in range(300):
            self.write("hooks/hook_%03d.py" % i)
        self.write("hooks/zz_late.py")
        self.write_map(rows_for([["hooks/hook_*.py"]]))
        rc, out = self.check()
        self.assert_uncovered(rc, out, ["uncovered hook: hooks/zz_late.py"])


if __name__ == "__main__":
    unittest.main()
