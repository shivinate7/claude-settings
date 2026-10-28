#!/usr/bin/env python3
"""Cases for lint/check_skill_model_rows.py. Run: python3 lint/test_check_skill_model_rows.py

decisions/agent-model-cap.md gets one row per skill under skills/.
Each row says "no model pin; runs on the caller's model". These cases pin the check that enforces it.

Interface the check must meet (the builder builds to it):
- A standalone script. It finds the repo from its own path, as lint/check_landed_dirs.py does.
  It reads decisions/agent-model-cap.md and the folders directly under skills/.
- A skill is a folder directly under skills/ that holds a file named exactly SKILL.md (case
  exact, so skill.md does not count). Dot folders and __pycache__ are never skills.
  A folder without SKILL.md, and a stray file, need no row.
- A row is a markdown table line whose first cell is: skill `NAME`. NAME must equal the folder
  name exactly: no case folding, no prefix stripping. A plugin prefix is not stripped.
- A row line must contain "no model pin" and "runs on the caller's model" (ASCII apostrophe).
- Each skill needs exactly one row. A row for a missing skill is stale. Both fail.
- Fenced blocks: a fence closes only on a fence of the same character and at least the same
  length. A ~~~ or a shorter line does not close a ``` fence.
- HTML comments: a "<!--" with no "-->" on the same line opens a multi-line comment, unless it
  sits inside a code span or a fence. Rows inside the comment do not count.
- Other text after a row's first cell is plain: "/*", "//", "#", a lone backtick, an apostrophe.
- A clean run prints nothing, not even a blank line.
- Exit 0 when clean. Exit 1 when a row disagrees: one line per problem, naming the skill.
  Exit 2, with a message naming the path, when the record or skills/ cannot be read, or a
  skill folder cannot be read (POSIX permissions; pinned on POSIX only, see CHECK_LOCKED).

Each case names the defect it pins in its docstring or comment. Red cases are marked "Red".
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CHECK = os.path.join(HERE, "check_skill_model_rows.py")
RECORD = "decisions/agent-model-cap.md"
CHECKS = os.path.join(ROOT, ".github", "workflows", "checks.yml")
CHECK_STEP = "Skill model rows check"
FIXTURE_STEP = "Skill model rows fixture suite"

sys.path.insert(0, HERE)
from test_windows_split import all_jobs  # noqa: E402  one home for the checks.yml step parser
from check_skill_model_rows import skill_names  # noqa: E402
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  copies what git lists, so no fixture lists files (testing/tracked_tree.py)

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


# chmod 000 stops reads only for a non-root POSIX user. CI runs the checks job on ubuntu.
POSIX_USER = hasattr(os, "geteuid") and os.geteuid() != 0
CHECK_LOCKED = "needs POSIX chmod and a non-root user; not pinned on Windows (no ACL change made)"


def run(files, locked=()):
    """Build a temp repo from {relpath: text}, run the check in it. Returns (exit code, output).

    `locked` names folders to chmod 000 after the files are written. They are restored before
    the temp tree is removed.
    """
    need_check()
    tree = tempfile.mkdtemp(prefix="skill_rows_")
    try:
        tracked_tree.copy_tracked(tree, "lint")  # the layout and the check's imports
        script = os.path.join(tree, "lint", "check_skill_model_rows.py")
        shutil.copy(CHECK, script)
        for rel, text in files.items():
            path = os.path.join(tree, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
        for rel in locked:
            os.chmod(os.path.join(tree, *rel.split("/")), 0o000)
        proc = subprocess.run([sys.executable, script], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=120)
        return proc.returncode, proc.stdout + proc.stderr
    finally:
        for rel in locked:
            try:
                os.chmod(os.path.join(tree, *rel.split("/")), 0o755)
            except OSError:
                pass
        shutil.rmtree(tree, ignore_errors=True)


class Coverage(unittest.TestCase):
    def test_a_row_for_every_skill_passes(self):
        files = skills("alpha", "beta")
        files[RECORD] = record([row("alpha"), row("beta")], prose="Don't edit this table by hand.\n\n")
        code, out = run(files)
        self.assertEqual(code, 0, out)

    def test_clean_run_prints_nothing(self):
        # A clean run prints nothing, not a blank line.
        files = skills("alpha")
        files[RECORD] = record([row("alpha")])
        code, out = run(files)
        self.assertEqual(code, 0, out)
        self.assertEqual(out, "")

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

    def test_phrases_outside_the_second_cell_do_not_satisfy_a_row(self):
        # Red: the check matches the phrases anywhere on the row line. They count in the second cell only.
        cases = {
            "both phrases in the third cell": "| skill `alpha` | runs on Sonnet | %s |" % PHRASE,
            "one phrase per cell": "| skill `alpha` | no model pin | runs on the caller's model |",
        }
        for label, line in cases.items():
            with self.subTest(case=label):
                files = skills("alpha")
                files[RECORD] = record([line])
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

    def test_unreadable_input_fails_with_a_message(self):
        # The record and skills/ cases use no skill rows, so an input read as empty cannot pass.
        cases = {
            "record missing": (skills("alpha"), "agent-model-cap.md"),
            "skills folder missing": ({RECORD: record([])}, "skills"),
            "skills is a file": ({RECORD: record([]), "skills": "not a folder\n"}, "skills"),
        }
        for label, (files, named) in cases.items():
            with self.subTest(case=label):
                code, out = run(files)
                self.assertNotEqual(code, 0, out)
                self.assertIn(named, out)


class Fences(unittest.TestCase):
    """Fence length, and mid-line comment openers."""

    def test_fence_closes_only_on_a_fence_at_least_as_long(self):
        # Red: a 4-backtick (or 4-tilde) fence must not close on a 3-character line inside it.
        cases = {
            "4-backtick fence, inner 3-backtick line": "````text\n```\n%s\n````\n" % row("alpha"),
            "4-tilde fence, inner 3-tilde line": "~~~~text\n~~~\n%s\n~~~~\n" % row("alpha"),
        }
        for label, extra in cases.items():
            with self.subTest(case=label):
                files = skills("alpha")
                files[RECORD] = record([], extra=extra)
                code, out = run(files)
                self.assertEqual(code, 1, out)
                self.assertIn("alpha", out)
        # A row inside a plain fence does not count.
        with self.subTest(case="rows in a fence"):
            files = skills("alpha", "beta")
            files[RECORD] = record([row("beta")], extra="```text\n%s\n```\n" % row("alpha"))
            code, out = run(files)
            self.assertEqual(code, 1, out)
            self.assertIn("alpha", out)
        # A longer closer closes the fence (green).
        for label, pattern in {
            "3-backtick fence, 4-backtick closer": "```text\n%s\n````\n%s\n",
            "3-tilde fence, 4-tilde closer": "~~~text\n%s\n~~~~\n%s\n",
        }.items():
            with self.subTest(case=label):
                files = skills("alpha")
                files[RECORD] = record([], extra=pattern % (row("alpha"), row("alpha")))
                code, out = run(files)
                self.assertEqual(code, 0, out)

    def test_mid_line_comment_opener_hides_the_rows_it_wraps(self):
        # Red: "intro <!--" opens a multi-line comment on a prose line. The row inside must not count.
        files = skills("alpha", "beta")
        files[RECORD] = record([row("beta")], extra="intro <!--\n%s\n-->\n" % row("alpha"))
        code, out = run(files)
        self.assertEqual(code, 1, out)
        self.assertIn("alpha", out)
        # "<!-- note -->" closes on its line.
        with self.subTest(case="comment closed on its line"):
            files = skills("alpha")
            files[RECORD] = record([], extra="intro <!-- note --> text\n%s\n" % row("alpha"))
            code, out = run(files)
            self.assertEqual(code, 0, out)
        # A lone opener in a code span
        # or a fence opens nothing.
        with self.subTest(case="opener in a code span or fence"):
            files = skills("alpha", "beta")
            extra = ("Write `<!--` to open a comment.\n"
                     "```text\n<!-- lone opener in a fence\n```\n"
                     "%s\n" % row("beta"))
            files[RECORD] = record([row("alpha", PHRASE + " `<!-- open`")], extra=extra)
            code, out = run(files)
            self.assertEqual(code, 0, out)
        # A row inside a multi-line comment.
        with self.subTest(case="rows in a multi-line html comment"):
            files = skills("alpha", "beta")
            files[RECORD] = record([row("beta")], extra="<!--\n%s\n-->\n" % row("alpha"))
            code, out = run(files)
            self.assertEqual(code, 1, out)
            self.assertIn("alpha", out)
        # Markers in row text hide nothing.
        with self.subTest(case="scanner markers in row text"):
            files = skills("alpha", "beta", "gamma")
            files[RECORD] = record(
                [row("alpha", PHRASE + " `<!-- open a comment`"),
                 row("beta", PHRASE + " /* open a block"),
                 row("gamma", PHRASE + " // and # and a lone ` backtick")],
                extra="\nA closing remark --> and */ and don't stop here.\n",
            )
            code, out = run(files)
            self.assertEqual(code, 0, out)

class OpenFences(unittest.TestCase):
    """An unclosed fence or comment hides every later line. The check fails visibly, and names the open one
    and the line it starts on, so a reader does not hunt for the cause (agent-model-cap)."""

    def said(self, opener, closer, hidden):
        """-> (exit code, output, start line, record). `hidden` is the skills whose rows sit after the opener."""
        files = skills("alpha", *hidden)
        rows = [row("alpha")]
        text = record(rows, extra="%s\n%s\n" % (opener, "\n".join(row(n) for n in hidden)) + closer)
        files[RECORD] = text
        start = text.splitlines().index(opener) + 1
        code, out = run(files)
        return code, out, start

    def assertNamed(self, out, word, start):
        self.assertTrue(any(word in line.lower() and re.search(r"\b%d\b" % start, line) for line in out.splitlines()),
                        "no line names the open %s and line %d:\n%s" % (word, start, out))

    def test_unclosed_fence_with_every_row_present_still_fails_and_is_named(self):
        # Red: all rows precede the fence, so nothing is hidden and the check exits 0 on a broken record.
        for opener in ("```text", "~~~text"):
            with self.subTest(opener=opener):
                code, out, start = self.said(opener, "", [])
                self.assertEqual(code, 1, out)
                self.assertNamed(out, "fence", start)

    def test_unclosed_fence_that_hides_a_row_names_the_fence(self):
        # Red: the output says "no row" for the hidden skill and never says why.
        code, out, start = self.said("```text", "", ["beta"])
        self.assertEqual(code, 1, out)
        self.assertIn("beta", out)
        self.assertNamed(out, "fence", start)

    def test_unclosed_comment_names_the_comment(self):
        # Red: "intro <!--" never closes. The line it opens on is the start line.
        files = skills("alpha")
        text = record([row("alpha")], extra="intro <!--\n%s\n" % row("beta"))
        files[RECORD] = text
        start = text.splitlines().index("intro <!--") + 1
        code, out = run(files)
        self.assertEqual(code, 1, out)
        self.assertNamed(out, "comment", start)

    def test_closed_fence_and_closed_comment_say_nothing(self):
        # Control, green today: a closed fence and a closed comment get no problem line.
        files = skills("alpha")
        files[RECORD] = record([row("alpha")], extra="```text\nx\n```\n<!--\ny\n-->\n")
        code, out = run(files)
        self.assertEqual(code, 0, out)
        self.assertEqual(out, "")


class Folders(unittest.TestCase):
    """Exact SKILL.md, dot folders, unreadable folders."""

    def test_skill_md_name_is_exact_case(self):
        # NTFS matches skill.md to SKILL.md, so the check must compare the name exactly.
        files = {"skills/lc/skill.md": "lowercase name, not a skill\n"}
        files[RECORD] = record([])
        code, out = run(files)
        self.assertEqual(code, 0, out)
        self.assertEqual(out, "")

    def test_a_directory_named_skill_md_is_not_a_skill_file(self):
        # Red: a directory named SKILL.md passes the name test, so its folder counts as a skill and needs a row.
        files = {"skills/alpha/SKILL.md/note.txt": "a folder, not the skill file\n"}
        files[RECORD] = record([])
        code, out = run(files)
        self.assertEqual(code, 0, out)
        self.assertEqual(out, "")

    def test_dot_folders_and_pycache_need_no_row(self):
        cases = {
            "dot folder with SKILL.md": {"skills/.foo/SKILL.md": "---\nname: foo\n---\n"},
            "__pycache__ with a .pyc": {"skills/__pycache__/check.cpython-311.pyc": "x"},
        }
        for label, folder_files in cases.items():
            with self.subTest(case=label):
                files = dict(folder_files)
                files[RECORD] = record([])
                code, out = run(files)
                self.assertEqual(code, 0, out)

    @unittest.skipUnless(POSIX_USER, CHECK_LOCKED)
    def test_unreadable_skill_folder_without_a_row_exits_2(self):
        # Red: a folder whose SKILL.md cannot be stat'ed is read as "not a skill", so the run passes.
        files = skills("locked")
        files[RECORD] = record([])
        code, out = run(files, locked=("skills/locked",))
        self.assertEqual(code, 2, out)
        self.assertIn("locked", out)


class SkillNames(unittest.TestCase):
    """skill_names is also called by lint/hook_catalog.py, on a settings root of its own."""

    def test_a_root_with_no_skills_folder_lists_no_skills(self):
        # Red: os.listdir raises FileNotFoundError, a traceback in the catalog render of a root with hooks/ only.
        # main() still exits 2 for a missing skills/ (test_unreadable_input_fails_with_a_message): that check stays in main.
        tree = tempfile.mkdtemp(prefix="skill_names_")
        self.addCleanup(shutil.rmtree, tree, True)
        os.makedirs(os.path.join(tree, "hooks"))
        self.assertEqual(skill_names(os.path.join(tree, "skills")), [])

    def test_a_skills_path_that_is_a_file_lists_no_skills(self):
        tree = tempfile.mkdtemp(prefix="skill_names_")
        self.addCleanup(shutil.rmtree, tree, True)
        with open(os.path.join(tree, "skills"), "w", encoding="utf-8") as handle:
            handle.write("not a folder\n")
        self.assertEqual(skill_names(os.path.join(tree, "skills")), [])

    def test_a_root_with_skills_still_lists_them(self):
        # Control, green today.
        tree = tempfile.mkdtemp(prefix="skill_names_")
        self.addCleanup(shutil.rmtree, tree, True)
        os.makedirs(os.path.join(tree, "skills", "alpha"))
        with open(os.path.join(tree, "skills", "alpha", "SKILL.md"), "w", encoding="utf-8") as handle:
            handle.write("---\nname: alpha\n---\n")
        self.assertEqual(skill_names(os.path.join(tree, "skills")), ["alpha"])


class CiWiring(unittest.TestCase):
    def step(self, name):
        with open(CHECKS, encoding="utf-8") as handle:
            jobs = all_jobs(handle.read())
        self.assertIn("checks", jobs, "checks.yml has no checks job")
        found = [s for s in jobs["checks"]["steps"] if s.get("name") == name]
        self.assertEqual(len(found), 1, "checks job needs exactly one step named %r" % name)
        return found[0]

    def test_checks_job_runs_the_check(self):
        step = self.step(CHECK_STEP)
        self.assertEqual(step.get("run"), "python3 lint/check_skill_model_rows.py")
        self.assertNotIn("if", step, "an if: condition lets a skipped check read as passing")

    def test_checks_job_runs_the_fixture_suite(self):
        step = self.step(FIXTURE_STEP)
        self.assertEqual(step.get("run"), "python3 lint/test_check_skill_model_rows.py")
        self.assertNotIn("if", step, "an if: condition lets a skipped suite read as passing")


if __name__ == "__main__":
    unittest.main()
