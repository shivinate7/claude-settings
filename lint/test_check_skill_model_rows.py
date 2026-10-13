#!/usr/bin/env python3
"""Cases for lint/check_skill_model_rows.py. Run: python3 lint/test_check_skill_model_rows.py

Owner ruling (2026-10-13): decisions/subagent-model-cap.md gets one row per skill under skills/.
Each row says "no model pin; runs on the caller's model". These cases pin the check that enforces it.

Interface the check must meet (the builder builds to it):
- A standalone script. It finds the repo from its own path, as lint/check_landed_dirs.py does.
  It reads decisions/subagent-model-cap.md and the folders directly under skills/.
- A skill is a folder directly under skills/ that holds SKILL.md (the sibling check's definition).
  A folder without SKILL.md, and a stray file, need no row.
- A row is a markdown table line whose first cell is: skill `NAME`. NAME must equal the folder
  name exactly: no case folding, no prefix stripping. A plugin prefix is not stripped.
- A row line must contain "no model pin" and "runs on the caller's model" (ASCII apostrophe).
- Each skill needs exactly one row. A row for a missing skill is stale. Both fail.
- Rows inside a fenced block or a multi-line HTML comment do not count. Text after a row's first
  cell is row text: "<!--", "/*", "//", "#", a lone backtick or an apostrophe must not hide later rows.
- Exit 0 when clean. Exit 1 when a row disagrees: one line per problem, naming the skill.
  Exit non-zero, with a message naming the path, when the record or skills/ cannot be read.

Every case fails until lint/check_skill_model_rows.py exists, and names that as the cause.
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CHECK = os.path.join(HERE, "check_skill_model_rows.py")
RECORD = "decisions/subagent-model-cap.md"
REAL_SKILLS = os.path.join(ROOT, "skills")
GATES = os.path.join(ROOT, ".github", "workflows", "gates.yml")
CHECK_STEP = "Skill model rows check"
FIXTURE_STEP = "Skill model rows fixture suite"

sys.path.insert(0, HERE)
from test_windows_split import all_jobs  # noqa: E402  one home for the gates.yml step parser

PHRASE = "no model pin; runs on the caller's model"
HEAD = "| Point | Model | Effort |\n|---|---|---|\n"
AGGREGATE = "| skills | no `model:` pin | none |"  # the existing category row, not a skill row
ROLE = "| reviewer | haiku | xhigh |"


def row(name, text=PHRASE):
    return "| skill `%s` | %s | none |" % (name, text)


def record(rows=(), prose="", extra=""):
    """A record: the category and role rows, then `rows`. `prose` goes before, `extra` after."""
    return prose + HEAD + "\n".join([AGGREGATE, ROLE] + list(rows)) + "\n" + extra


def skills(*names):
    """Files for one skill folder per name. Each folder holds SKILL.md."""
    files = {}
    for name in names:
        files["skills/%s/SKILL.md" % name] = "---\nname: %s\n---\n\nbody\n" % name
    return files


def need_check():
    if not os.path.exists(CHECK):
        raise AssertionError("lint/check_skill_model_rows.py does not exist: no check reads the skill rows")


def run(files, real_skills=False):
    """Build a temp repo from {relpath: text}, run the check in it. Returns (exit code, output)."""
    need_check()
    tree = tempfile.mkdtemp(prefix="skill_rows_")
    try:
        os.makedirs(os.path.join(tree, "lint"))
        script = os.path.join(tree, "lint", "check_skill_model_rows.py")
        shutil.copy(CHECK, script)
        if real_skills:
            shutil.copytree(REAL_SKILLS, os.path.join(tree, "skills"))
        for rel, text in files.items():
            path = os.path.join(tree, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
        proc = subprocess.run([sys.executable, script], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=120)
        return proc.returncode, proc.stdout + proc.stderr
    finally:
        shutil.rmtree(tree, ignore_errors=True)


def run_real():
    """Run the check in the real repo, the way CI does."""
    need_check()
    proc = subprocess.run([sys.executable, CHECK], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120)
    return proc.returncode, proc.stdout + proc.stderr


def real_skill_names():
    return sorted(os.path.basename(os.path.dirname(p))
                  for p in glob.glob(os.path.join(REAL_SKILLS, "*", "SKILL.md")))


class Coverage(unittest.TestCase):
    def test_a_row_for_every_skill_passes(self):
        files = skills("alpha", "beta")
        files[RECORD] = record([row("alpha"), row("beta")], prose="Don't edit this table by hand.\n\n")
        code, out = run(files)
        self.assertEqual(code, 0, out)

    def test_crlf_record_reads_the_same(self):
        files = skills("alpha")
        files[RECORD] = record([row("alpha")]).replace("\n", "\r\n")
        code, out = run(files)
        self.assertEqual(code, 0, out)

    def test_folder_without_skill_md_and_stray_file_need_no_row(self):
        files = skills("alpha")
        files[RECORD] = record([row("alpha")])
        files["skills/notes/README.txt"] = "not a skill\n"
        files["skills/stray.md"] = "not a skill\n"
        code, out = run(files)
        self.assertEqual(code, 0, out)

    def test_skill_with_no_row_fails_and_is_named(self):
        files = skills("alpha", "beta")
        files[RECORD] = record([row("alpha")])
        code, out = run(files)
        self.assertEqual(code, 1, out)
        self.assertIn("beta", out)
        for line in out.splitlines():
            self.assertNotIn("alpha", line)

    def test_stale_row_fails_and_is_named(self):
        files = skills("alpha")
        files[RECORD] = record([row("alpha"), row("gone")])
        code, out = run(files)
        self.assertEqual(code, 1, out)
        self.assertIn("gone", out)

    def test_duplicate_row_fails_and_is_named(self):
        files = skills("alpha")
        files[RECORD] = record([row("alpha"), row("alpha")])
        code, out = run(files)
        self.assertEqual(code, 1, out)
        self.assertIn("alpha", out)

    def test_category_and_role_rows_are_not_skill_rows(self):
        for folder in ("reviewer", "skills"):
            with self.subTest(folder=folder):
                files = skills(folder)
                files[RECORD] = record([])
                code, out = run(files)
                self.assertEqual(code, 1, out)
                self.assertIn(folder, out)

    def test_row_text_must_carry_both_phrases(self):
        cases = {
            "sonnet only": "runs on Sonnet",
            "caller phrase only": "runs on the caller's model",
            "no model pin only": "no model pin",
        }
        for label, text in cases.items():
            with self.subTest(case=label):
                files = skills("alpha")
                files[RECORD] = record([row("alpha", text)])
                code, out = run(files)
                self.assertEqual(code, 1, out)
                self.assertIn("alpha", out)

    def test_phrases_in_prose_do_not_satisfy_a_row(self):
        files = skills("alpha")
        files[RECORD] = record([row("alpha", "runs on Sonnet")], prose=PHRASE + "\n\n")
        code, out = run(files)
        self.assertEqual(code, 1, out)
        self.assertIn("alpha", out)

    def test_name_matches_its_folder_exactly(self):
        files = skills("my skill")
        files[RECORD] = record([row("my skill")])
        code, out = run(files)
        self.assertEqual(code, 0, out)
        for label, folder, name in (
            ("case differs", "alpha", "Alpha"),
            ("plugin prefix", "skill", "plugin:skill"),
        ):
            with self.subTest(case=label):
                files = skills(folder)
                files[RECORD] = record([row(name)])
                code, out = run(files)
                self.assertEqual(code, 1, out)
                self.assertIn(name, out)

    def test_rows_in_a_fence_do_not_count(self):
        files = skills("alpha", "beta")
        files[RECORD] = record([row("beta")], extra="```text\n%s\n```\n" % row("alpha"))
        code, out = run(files)
        self.assertEqual(code, 1, out)
        self.assertIn("alpha", out)

    def test_rows_in_a_multi_line_html_comment_do_not_count(self):
        files = skills("alpha", "beta")
        files[RECORD] = record([row("beta")], extra="<!--\n%s\n-->\n" % row("alpha"))
        code, out = run(files)
        self.assertEqual(code, 1, out)
        self.assertIn("alpha", out)

    def test_scanner_markers_in_row_text_do_not_hide_later_rows(self):
        files = skills("alpha", "beta", "gamma")
        files[RECORD] = record(
            [row("alpha", PHRASE + " <!-- open a comment"),
             row("beta", PHRASE + " /* open a block"),
             row("gamma", PHRASE + " // and # and a lone ` backtick")],
            extra="\nA closing remark --> and */ and don't stop here.\n",
        )
        code, out = run(files)
        self.assertEqual(code, 0, out)

    def test_unreadable_input_fails_with_a_message(self):
        # The record and skills/ cases use no skill rows, so an input read as empty cannot pass.
        cases = {
            "record missing": (skills("alpha"), "subagent-model-cap.md"),
            "skills folder missing": ({RECORD: record([])}, "skills"),
            "skills is a file": ({RECORD: record([]), "skills": "not a folder\n"}, "skills"),
        }
        for label, (files, named) in cases.items():
            with self.subTest(case=label):
                code, out = run(files)
                self.assertNotEqual(code, 0, out)
                self.assertIn(named, out)


class RealRepo(unittest.TestCase):
    def test_real_record_and_skills_pass(self):
        code, out = run_real()
        self.assertEqual(code, 0, out)

    def test_real_skills_fail_against_an_empty_record(self):
        names = real_skill_names()
        self.assertTrue(names, "no skills/*/SKILL.md found: this case would prove nothing")
        code, out = run({RECORD: record([])}, real_skills=True)
        self.assertEqual(code, 1, out)
        for name in names:
            with self.subTest(skill=name):
                self.assertIn(name, out)


class CiWiring(unittest.TestCase):
    def step(self, name):
        with open(GATES, encoding="utf-8") as handle:
            jobs = all_jobs(handle.read())
        self.assertIn("gates", jobs, "gates.yml has no gates job")
        found = [s for s in jobs["gates"]["steps"] if s.get("name") == name]
        self.assertEqual(len(found), 1, "gates job needs exactly one step named %r" % name)
        return found[0]

    def test_gates_job_runs_the_check(self):
        step = self.step(CHECK_STEP)
        self.assertEqual(step.get("run"), "python3 lint/check_skill_model_rows.py")
        self.assertNotIn("if", step, "an if: gate lets a skipped check read as passing")

    def test_gates_job_runs_the_fixture_suite(self):
        step = self.step(FIXTURE_STEP)
        self.assertEqual(step.get("run"), "python3 lint/test_check_skill_model_rows.py")
        self.assertNotIn("if", step, "an if: gate lets a skipped suite read as passing")


if __name__ == "__main__":
    unittest.main()
