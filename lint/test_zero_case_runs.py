#!/usr/bin/env python3
"""A run of zero cases must exit non-zero, for the hand runners and for the mods test collector.

A hand runner prints its own `PASS: N of N` line and exits 0 when its case list is empty, so a suite
that lost every case still passes when run directly. CI runs most steps without bin/verdict, the one
place that fails a run of zero tests. So each hand runner here runs with its case lists emptied, and
must exit non-zero without a traceback. Each mods test collector (token-weather, session-board,
decision-watch, plain-diff) runs with every `await test(` disabled, and must exit non-zero too.

The runner's case lists are emptied by a driver in the run folder: it loads the runner file as a module
(not as __main__), sets each case list it finds to an empty one of the same type, then calls main().
A runner that loads its cases in another name must be added to CASE_LISTS.
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.realpath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  the one home of the run folder and its sweep (lint/_test_temp.py)

TIMEOUT = 300  # seconds for one runner; a hang guard well above a runner's run
CASE_LISTS = ("CASES", "RED_CASES", "GENERAL_CASES", "BAD_CASES")
# A runner that builds its list inside main() (hooks/test_wrappers.py) is emptied by a builder that returns [].
CASE_BUILDERS = ("build_cases",)
# Not listed: hooks/test_guard.py, whose cases come from section files on disk and not from a case list,
# and lint/check_guardset_lists.py, which with no case names runs hooks/test_install_src.sh whole.
RUNNERS = [
    "hooks/test_config_watch_fast_exit.py",
    "hooks/test_shared_names.py",
    "hooks/test_rm_prompt_answer.py",
    "hooks/test_page_link_check.py",
    "hooks/test_config_watch.py",
    "hooks/test_agent_brief.py",
    "hooks/test_guard_load_os.py",
    "hooks/test_feedback_inbox.py",
    "hooks/test_waiting_export.py",
    "hooks/test_wrappers.py",
    "hooks/test_reply_judge.py",
]
MODS_TEST = os.path.join("mods", "token-weather", "token-weather.test.mjs")
SESSION_BOARD = os.path.join("mods", "session-board", "session-board.test.mjs")
DECISION_WATCH = os.path.join("mods", "decision-watch", "decision-watch.test.mjs")
PLAIN_DIFF = os.path.join("mods", "plain-diff", "plain-diff.test.mjs")
DISABLE_FROM = "await test("  # every case in a mods collector starts with this call
SUMMARY = re.compile(r"fail of 0\b")  # every collector ends with "<name>: N pass, M fail of T"
# An import with a relative specifier: `from './x'`, `import '../y'`, or a dynamic `import('./z')`.
STATIC_IMPORT = re.compile(r"""(\bfrom\s+|\bimport\s+|\bimport\(\s*)(['"])(\.\.?/[^'"]+)\2""")

DRIVER = '''import importlib.util, os, sys
path = os.path.abspath(sys.argv[1])
sys.argv = [path]
sys.path.insert(0, os.path.dirname(path))
spec = importlib.util.spec_from_file_location("runner_under_test", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
for name in %r:
    if hasattr(mod, name):
        value = getattr(mod, name)
        setattr(mod, name, type(value)())
for name in %r:
    if hasattr(mod, name):
        setattr(mod, name, lambda: [])
sys.exit(mod.main())
''' % (CASE_LISTS, CASE_BUILDERS)


def setUpModule():
    global RUN
    RUN = _test_temp.run_folder()
    with open(os.path.join(RUN, "drive_runner.py"), "w", encoding="utf-8") as f:
        f.write(DRIVER)


def tearDownModule():
    shutil.rmtree(RUN, ignore_errors=True)


class HandRunnersWithNoCases(unittest.TestCase):
    def test_each_runner_exits_nonzero_when_its_cases_are_emptied(self):
        driver = os.path.join(RUN, "drive_runner.py")
        for path in RUNNERS:
            with self.subTest(runner=path):
                proc = subprocess.run([sys.executable, driver, path], cwd=REPO, capture_output=True,
                                      text=True, timeout=TIMEOUT)
                last = (proc.stdout + proc.stderr).strip().splitlines()[-1:] or ["<no output>"]
                self.assertNotEqual(proc.returncode, 0,
                                    "%s exits 0 with zero cases run: its last line is %r" % (path, last[0]))
                self.assertNotIn("Traceback", proc.stderr, "%s crashed with zero cases, not failed" % path)


def absolute_import(match, base):
    """The import with its relative specifier made an absolute file URL under base."""
    target = os.path.normpath(os.path.join(base, match.group(3)))
    return match.group(1) + match.group(2) + pathlib.Path(target).as_uri() + match.group(2)


def make_variant(original, out):
    """Write to out the copy of one mods test file with every `await test(` call disabled. Returns how
    many calls it disabled. The copy's relative imports and import.meta.url name the original file."""
    with open(original, encoding="utf-8") as f:
        source = f.read()
    base = os.path.dirname(original)
    copied = STATIC_IMPORT.sub(lambda m: absolute_import(m, base), source)
    copied = copied.replace("import.meta.url", '"%s"' % pathlib.Path(original).as_uri())
    with open(out, "w", encoding="utf-8") as f:
        f.write(copied.replace(DISABLE_FROM, "if (false) " + DISABLE_FROM))
    return source.count(DISABLE_FROM)


def zero_test_exit(case, path):
    """Run one mods test file with every `await test(` call disabled, and check that the run fails.

    The copy goes in the run folder. Its static relative imports become absolute file URLs, and every
    import.meta.url names the original file, so top-level reads of repo files still find them. The
    summary line must print first: a crash before it fails the case under its own name, not as a
    zero-test run that passed."""
    node = shutil.which("node")
    if node is None:
        case.skipTest("node is not on PATH: the %s zero-test case skips here" % os.path.basename(path))
    variant = os.path.join(RUN, "zero_" + os.path.basename(path))
    disabled = make_variant(os.path.join(REPO, path), variant)
    case.assertGreater(disabled, 0,
                       "%s has no `await test(` call to disable, so no zero-test run can be made" % path)
    proc = subprocess.run([node, variant], cwd=RUN, capture_output=True, text=True, timeout=TIMEOUT)
    last = (proc.stdout + proc.stderr).strip().splitlines()[-1:] or ["<no output>"]
    case.assertRegex(proc.stdout, SUMMARY,
                     "%s did not reach its summary line with zero tests run: its last line is %r" % (path, last[0]))
    case.assertNotEqual(proc.returncode, 0,
                        "%s exits 0 with zero tests run: its last line is %r" % (path, last[0]))


class TokenWeatherCollectorWithNoTests(unittest.TestCase):
    def test_collector_exits_nonzero_when_every_test_is_disabled(self):
        zero_test_exit(self, MODS_TEST)


class ModsCollectorsWithNoTests(unittest.TestCase):
    def test_session_board_exits_nonzero_when_every_test_is_disabled(self):
        zero_test_exit(self, SESSION_BOARD)

    def test_decision_watch_exits_nonzero_when_every_test_is_disabled(self):
        zero_test_exit(self, DECISION_WATCH)

    def test_plain_diff_exits_nonzero_when_every_test_is_disabled(self):
        zero_test_exit(self, PLAIN_DIFF)


def file_uri(folder, rel):
    """The file URL of rel under folder, as make_variant writes it."""
    return pathlib.Path(os.path.normpath(os.path.join(folder, rel))).as_uri()


class VariantRewriteCases(unittest.TestCase):
    """make_variant changes code only: an import specifier, a dynamic import, import.meta.url or an
    `await test(` call. Text in a string, a comment or a template literal stays as it is."""

    def variant_of(self, name, text):
        folder = os.path.join(RUN, name)
        os.makedirs(folder)
        original = os.path.join(folder, "fixture.mjs")
        with open(original, "w", encoding="utf-8") as f:
            f.write(text)
        out = os.path.join(folder, "variant.mjs")
        disabled = make_variant(original, out)
        with open(out, encoding="utf-8") as f:
            return f.read().splitlines(), disabled, folder

    def assertAbsolute(self, lines, head, uri, msg):
        """A line holds head, then uri as a quoted file URL. Either quote style passes."""
        self.assertRegex("\n".join(lines), re.escape(head) + r"['\"]" + re.escape(uri) + r"['\"]", msg)

    def test_comment_openers_inside_strings_are_kept(self):
        lines, _, folder = self.variant_of("comment_openers", (
            "const slash = \"// from './keep-slash.mjs'\";\n"
            "const block = \"/* from './keep-block.mjs'\";\n"
            "const hash = \"# from './keep-hash.mjs'\";\n"
            "import lib from './hooks/lib.mjs';\n"))
        for kept in ("const slash = \"// from './keep-slash.mjs'\";",
                     "const block = \"/* from './keep-block.mjs'\";",
                     "const hash = \"# from './keep-hash.mjs'\";"):
            self.assertIn(kept, lines, "text inside a string was rewritten: %r" % kept)
        self.assertAbsolute(lines, "import lib from ", file_uri(folder, "hooks/lib.mjs"),
                      "the import after the strings was not made absolute")

    def test_template_literal_holding_an_import_line_is_kept(self):
        lines, _, folder = self.variant_of("template_literal", (
            "const fixture = `\n"
            "import fake from './keep-template.mjs'\n"
            "`;\n"
            "import lib from './hooks/lib.mjs';\n"))
        self.assertIn("import fake from './keep-template.mjs'", lines,
                      "a line inside a template literal was rewritten")
        self.assertAbsolute(lines, "import lib from ", file_uri(folder, "hooks/lib.mjs"),
                      "the import after the template literal was not made absolute")

    def test_comment_with_a_lone_quote_is_kept(self):
        lines, _, folder = self.variant_of("lone_quote", (
            "// don't rewrite: from './keep-comment.mjs'\n"
            "const note = \"it's fine\";\n"
            "import lib from './hooks/lib.mjs';\n"))
        self.assertIn("// don't rewrite: from './keep-comment.mjs'", lines,
                      "a comment with a lone quote was rewritten")
        self.assertAbsolute(lines, "import lib from ", file_uri(folder, "hooks/lib.mjs"),
                      "the import after the comment was not made absolute")

    def test_import_meta_url_inside_a_string_is_kept(self):
        lines, _, folder = self.variant_of("meta_in_string", (
            "const doc = \"import.meta.url\";\n"
            "const here = new URL('./hooks/lib.mjs', import.meta.url);\n"))
        self.assertIn("const doc = \"import.meta.url\";", lines,
                      "import.meta.url inside a string was replaced")
        self.assertAbsolute(lines, "const here = new URL('./hooks/lib.mjs', ",
                            pathlib.Path(os.path.join(folder, "fixture.mjs")).as_uri(),
                            "import.meta.url in code was not replaced by the original file's URL")

    def test_await_test_inside_a_string_is_not_disabled(self):
        lines, disabled, _ = self.variant_of("await_in_string", (
            "const sample = \"await test('x', () => {})\";\n"
            "await test('real', () => {});\n"))
        self.assertIn("const sample = \"await test('x', () => {})\";", lines,
                      "an await test( call inside a string was disabled")
        self.assertIn("if (false) await test('real', () => {});", lines,
                      "the real await test( call was not disabled")
        self.assertEqual(disabled, 1, "make_variant counted %d calls to disable, want 1: the string holds none"
                         % disabled)

    def test_relative_import_in_code_is_made_absolute(self):
        lines, _, folder = self.variant_of("plain_import", "import lib from './hooks/lib.mjs';\n")
        self.assertAbsolute(lines, "import lib from ", file_uri(folder, "hooks/lib.mjs"),
                      "a relative import in code was not made absolute")

    def test_dynamic_import_in_code_is_made_absolute(self):
        lines, _, folder = self.variant_of("dynamic_import", "const late = await import('./hooks/lib.mjs');\n")
        self.assertAbsolute(lines, "const late = await import(", file_uri(folder, "hooks/lib.mjs"),
                            "a dynamic import of a relative path in code was not made absolute")


if __name__ == "__main__":
    unittest.main()
