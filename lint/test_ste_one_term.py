#!/usr/bin/env python3
"""Tests for STE022, the warn-only one-term lint (rule speak-one-name-per-thing, step one-term-warn-lint).

STE022 reads the "Not" names from GLOSSARY.md on each run and warns when prose uses one. It is advisory:
it never fails a run (decision plain-prose-lint).

    python lint/test_ste_one_term.py -v
"""
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ste_lint  # noqa: E402
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)

RUN_FOLDER = _test_temp.run_folder()


def lint(text, path="t.md"):
    return [f for f in ste_lint.Linter(dict(ste_lint.DEFAULT_CONFIG)).check_text(path, text) if f.code == "STE022"]


def _mirror_lint(root):
    """A lint folder under `root` with ste_lint.py, the modules it imports when it loads, and no check_glossary.py.

    ste_lint reads GLOSSARY.md from the parent of its real folder, so that path is `root/GLOSSARY.md`, which is never written.
    layout.json is read on each run, so the copy carries it too."""
    lint_dir = os.path.join(root, "lint")
    os.makedirs(lint_dir)
    for name in ("ste_lint.py", "ui_suffixes.py", "layout.py", "layout.json"):
        shutil.copy(os.path.join(HERE, name), os.path.join(lint_dir, name))
    return lint_dir


class OneTermTests(unittest.TestCase):
    def test_not_name_in_prose_warns(self):
        got = lint("The gate refuses the push.\n")
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].severity, "warning")
        self.assertIn("guard", got[0].message)

    def test_glossary_term_passes(self):
        self.assertEqual(lint("The guard refuses the push.\n"), [])

    def test_plural_and_case_warn(self):
        self.assertEqual(len(lint("Gates stop the push.\n")), 1)

    def test_code_span_passes(self):
        self.assertEqual(lint("The word `gate` names a hook in another repo.\n"), [])

    def test_this_sense_name_is_left_to_the_reviewer(self):
        self.assertEqual(lint("Add an entry to the list.\n"), [])

    def test_glossary_file_itself_is_skipped(self):
        self.assertEqual(lint("The gate refuses the push.\n", path="GLOSSARY.md"), [])

    def test_source_comment_warns_and_string_passes(self):
        linter = ste_lint.Linter(dict(ste_lint.DEFAULT_CONFIG))
        code = '# The gate refuses the push.\nx = "the gate refuses"\n'
        got = [f for f in linter.check_source("t.py", code) if f.code == "STE022"]
        self.assertEqual([f.line for f in got], [1])

    def test_names_come_from_glossary_not_a_copy(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "GLOSSARY.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write("## Terms\n\n| Term | Meaning | Home | Not |\n|---|---|---|---|\n"
                        "| zork | A thing. | `GLOSSARY.md` | `blorp` |\n")
            old = ste_lint.GLOSSARY_PATH
            ste_lint.GLOSSARY_PATH = path
            try:
                self.assertEqual(len(lint("The blorp runs.\n")), 1)
                self.assertEqual(lint("The gate runs.\n"), [])
            finally:
                ste_lint.GLOSSARY_PATH = old

    def test_missing_glossary_gives_no_finding(self):
        old = ste_lint.GLOSSARY_PATH
        ste_lint.GLOSSARY_PATH = os.path.join(HERE, "no-such-glossary.md")
        ste_lint.reset_one_term_cache()
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err):
                self.assertEqual(lint("The gate runs.\n"), [])
                with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as root:
                    md = os.path.join(root, "a.md")
                    with open(md, "w", encoding="utf-8") as f:
                        f.write("The gate runs.\n")
                    with contextlib.redirect_stdout(io.StringIO()):
                        rc = ste_lint.main([md])
            self.assertEqual(rc, 0, "run exits %d with GLOSSARY.md missing" % rc)
        finally:
            ste_lint.GLOSSARY_PATH = old
            ste_lint.set_gloss_pattern(None)  # main sets it from the repo's decisions folder; restore the default
        unknown = [line for line in err.getvalue().splitlines() if "unknown" in line]
        self.assertEqual(len(unknown), 1, "stderr holds %d 'unknown' lines, want one: %s" % (len(unknown), err.getvalue()))

    def test_never_fails_a_run(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write("The gate refuses the push.\n")
            r = subprocess.run([sys.executable, os.path.join(HERE, "ste_lint.py"), p],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("STE022", r.stdout)

    def test_every_use_in_one_paragraph_warns_at_its_own_line(self):
        got = lint("The gate refuses.\nIt stops.\nThe gate refuses again.\n")
        self.assertEqual(sorted(f.line for f in got), [1, 3])

    def test_camel_case_name_reports_its_own_column(self):
        got = lint("The batchBranch runs.\n")
        self.assertEqual([(f.line, f.col) for f in got], [(1, 5)])

    def test_glossary_file_skip_does_not_leak_to_the_next_file(self):
        linter = ste_lint.Linter(dict(ste_lint.DEFAULT_CONFIG))
        linter.check_text("GLOSSARY.md", "The gate refuses.\n")
        got = [f for f in linter.check_ui("a.tsx", "export const A = () => <p>The gate refuses the push.</p>;\n")
               if f.code == "STE022"]
        self.assertEqual(len(got), 1)

    def test_platform_names_pass(self):
        self.assertEqual(lint("The SubagentStop hook runs.\n"), [])
        self.assertEqual(lint("A permission deny rule runs.\n"), [])

    def test_vendored_folder_is_skipped(self):
        self.assertEqual(lint("The gate refuses.\n", path="skills/impeccable/x.md"), [])

    def test_glossary_is_read_once_per_run(self):
        import check_glossary
        ste_lint.reset_one_term_cache()
        calls = []
        real = check_glossary.rows
        check_glossary.rows = lambda t: calls.append(1) or real(t)
        try:
            lint("The gate one.\n\nThe gate two.\n\nThe gate three.\n")
        finally:
            check_glossary.rows = real
        self.assertEqual(len(calls), 1)

    def test_symlinked_linter_finds_the_glossary(self):
        with tempfile.TemporaryDirectory() as d:
            link = os.path.join(d, "ste_lint.py")
            os.symlink(os.path.join(HERE, "ste_lint.py"), link)
            a = os.path.join(d, "a.md")
            with open(a, "w", encoding="utf-8") as f:
                f.write("The gate refuses the push.\n")
            r = subprocess.run([sys.executable, link, a], capture_output=True, text=True)
            self.assertIn("STE022", r.stdout)

    def test_platform_name_behind_punctuation_passes(self):
        self.assertEqual(len(lint("A subagent runs.\n")), 1)  # control: the retired name still warns
        for text in ("Hooks (SubagentStop, SubagentStart) run.\n",
                     "(CLAUDE_CODE_SUBAGENT_MODEL) is set.\n",
                     "**SubagentStop** runs.\n"):
            with self.subTest(text=text):
                self.assertEqual(lint(text), [])

    def test_missing_check_glossary_does_not_crash_the_run(self):
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as root:
            lint_dir = _mirror_lint(root)
            env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
            # Scope before subject: the copy loads, GLOSSARY.md is not beside it, and check_glossary does not load.
            self.assertFalse(os.path.exists(os.path.join(root, "GLOSSARY.md")), "GLOSSARY.md is beside the copy")
            scope = subprocess.run([sys.executable, "-c", "import ste_lint"], cwd=lint_dir, env=env,
                                   capture_output=True, text=True)
            self.assertEqual(scope.returncode, 0, "the copy does not load: " + scope.stderr)
            gone = subprocess.run([sys.executable, "-c", "import check_glossary"], cwd=lint_dir, env=env,
                                  capture_output=True, text=True)
            self.assertNotEqual(gone.returncode, 0, "check_glossary loads from the copy's folder")
            md = os.path.join(root, "a.md")
            with open(md, "w", encoding="utf-8") as f:
                f.write("They'd finished.\n")
            r = subprocess.run([sys.executable, os.path.join(lint_dir, "ste_lint.py"), md],
                               cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, "exit %d when check_glossary is missing; stderr: %s"
                             % (r.returncode, r.stderr))
            self.assertIn("STE008", r.stdout)
            self.assertNotIn("Traceback", r.stderr)

    def test_finding_is_not_placed_when_the_spelling_is_not_found(self):
        self.assertEqual([f.col for f in lint("The gate runs.\n")], [5])  # control: a spelled name is placed on its word
        with self.subTest(case="theGate, camelCase inside a word"):
            got = lint("First line.\nThe theGate runs.\n")
            self.assertTrue({f.line for f in got} <= {2},
                            "STE022 for theGate placed on lines %s; line 1 is 'First line.'" % sorted({f.line for f in got}))
        with self.subTest(case="GATEWAY, a longer word that starts with gate"):
            text = "The GATEWAY runs and a gate too.\n"
            want = text.index(" gate ") + 2
            cols = [f.col for f in lint(text)]
            self.assertTrue(all(c == want for c in cols),
                            "STE022 placed at cols %s; only the standalone gate, at col %d, may be" % (cols, want))


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    unittest.main()
