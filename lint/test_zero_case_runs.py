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
SUMMARY = re.compile(r"fail of 0\b")  # every collector ends with "<name>: N pass, M fail of T"
REWRITER_NAME = "rewrite_variant.cjs"
# Rewrites a copy of a mods test file. It asks TypeScript's scanner (the one lint/comment_scan.mjs uses) which
# text is code, so strings, comments and template literals are never changed.
REWRITER = r"""// node rewrite_variant.cjs <typescript.js> <original file> <out file>
// Writes the copy of one test file: a relative import specifier and a dynamic import() of one become absolute
// file URLs, import.meta.url becomes the original file's URL, and each `await test(` statement is disabled.
// Prints how many statements it disabled.
const fs = require('node:fs')
const path = require('node:path')
const { pathToFileURL } = require('node:url')
const ts = require(process.argv[2])
const [original, out] = process.argv.slice(3)
const source = fs.readFileSync(original, 'utf8')
const file = ts.createSourceFile(original, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.JS)
const dir = path.dirname(original)
const edits = []
let disabled = 0

const replaceNode = (node, text) => edits.push({ start: node.getStart(file), end: node.end, text })
const specifier = (literal) => {
  if (ts.isStringLiteral(literal) && /^\.\.?\//.test(literal.text)) {
    replaceNode(literal, JSON.stringify(pathToFileURL(path.resolve(dir, literal.text)).href))
  }
}
const isImportMeta = (node) => ts.isMetaProperty(node) && node.keywordToken === ts.SyntaxKind.ImportKeyword
const isTestCall = (node) => ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === 'test'

const visit = (node) => {
  if ((ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) && node.moduleSpecifier) {
    specifier(node.moduleSpecifier)
  } else if (ts.isCallExpression(node) && node.expression.kind === ts.SyntaxKind.ImportKeyword && node.arguments.length > 0) {
    specifier(node.arguments[0])
  } else if (ts.isPropertyAccessExpression(node) && isImportMeta(node.expression) && node.name.text === 'url') {
    replaceNode(node, JSON.stringify(pathToFileURL(original).href))
  } else if (ts.isExpressionStatement(node) && ts.isAwaitExpression(node.expression) && isTestCall(node.expression.expression)) {
    disabled += 1
    const start = node.getStart(file)
    edits.push({ start, end: start, text: 'if (false) ' })
  }
  ts.forEachChild(node, visit)
}
visit(file)

let text = source
for (const edit of edits.sort((a, b) => b.start - a.start || b.end - a.end)) {
  text = text.slice(0, edit.start) + edit.text + text.slice(edit.end)
}
fs.writeFileSync(out, text)
process.stdout.write(String(disabled))
"""

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
    with open(os.path.join(RUN, REWRITER_NAME), "w", encoding="utf-8") as f:
        f.write(REWRITER)


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


NEEDS_TS = unittest.skipUnless(
    (shutil.which("tsc") and shutil.which("node")) or os.environ.get("CI"),
    "tsc and node are not on PATH: npm ci --ignore-scripts --prefix actions/code-check/tools puts tsc on PATH (CI does)")


def make_variant(original, out):
    """Write to out the copy of one mods test file with every `await test(` statement disabled, and return how
    many it disabled. The copy's relative imports and import.meta.url name the original file. Strings, comments
    and template literals are copied as they are."""
    tsc = shutil.which("tsc")
    if tsc is None:
        raise AssertionError("tsc is not on PATH, so make_variant cannot tell the code of %s" % original)
    typescript = os.path.normpath(os.path.join(os.path.dirname(os.path.realpath(tsc)), "..", "lib", "typescript.js"))
    proc = subprocess.run(["node", os.path.join(RUN, REWRITER_NAME), typescript, original, out],
                          capture_output=True, text=True, timeout=TIMEOUT)
    if proc.returncode != 0:
        raise AssertionError("the rewrite of %s failed: %s" % (original, proc.stderr.strip()[-300:]))
    return int(proc.stdout)


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


@NEEDS_TS
class TokenWeatherCollectorWithNoTests(unittest.TestCase):
    def test_collector_exits_nonzero_when_every_test_is_disabled(self):
        zero_test_exit(self, MODS_TEST)


@NEEDS_TS
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


@NEEDS_TS
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


# A runner that reads a filter from the environment and runs only the cases it names. A filter that names no
# case must fail the run, as an emptied case list does (hooks/case_runner_test.py no_cases_exit).
FILTERED_RUNNERS = (("hooks/test_config_watch.py", "MUTATE_ONLY"),)
NO_CASE_NAMED = "no case name holds this value 7c1e9a"


class FilterMatchingNoCase(unittest.TestCase):
    def test_each_filtered_runner_exits_nonzero_when_its_filter_matches_no_case(self):
        for path, variable in FILTERED_RUNNERS:
            with self.subTest(runner=path):
                env = dict(os.environ)
                env[variable] = NO_CASE_NAMED
                proc = subprocess.run([sys.executable, path], cwd=REPO, env=env, capture_output=True,
                                      text=True, timeout=TIMEOUT)
                text = proc.stdout + proc.stderr
                last = text.strip().splitlines()[-1:] or ["<no output>"]
                self.assertNotIn("Traceback", proc.stderr, "%s crashed with %s matching no case" % (path, variable))
                self.assertNotEqual(proc.returncode, 0,
                                    "%s exits 0 with %s matching no case, so it runs zero cases: its last line is %r"
                                    % (path, variable, last[0]))
                self.assertIn("no cases ran", text, "%s does not say that no cases ran" % path)


if __name__ == "__main__":
    unittest.main()
