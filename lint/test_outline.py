#!/usr/bin/env python3
"""Cases for bin/outline: a file's outline, one line per unit, so a reader takes only the section it needs.

    python3 lint/test_outline.py -v

`bin/outline <file> [symbol]` prints one line per unit, `<first>-<last> <kind> <qualified name>`, in file order.
With a symbol it prints that unit's line only. Python is read by ast, Markdown by heading, a YAML workflow by job
and step, shell by function. Exit 0: the outline, or the symbol's line. Exit 1: a missing or an ambiguous symbol
(an ambiguous name prints each candidate's line). Exit 2: a file type that is not read. A call starts no child
process and writes no file.

The kind words, the names of headings and steps, and the way a range ends are choices this file pins. Each is
named where its fixture is.
"""
import ast
import contextlib
import io
import os
import re
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "testing"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
import cost_probe  # noqa: E402  the one home of the cost counters (testing/cost_probe.py)

TOOL = os.environ.get("OUTLINE_UNDER_TEST") or os.path.join(REPO, "bin", "outline")
MERGE = os.path.join(REPO, "merge", "merge.py")
TEST_MERGE = os.path.join(REPO, "merge", "test_merge.py")
RUN = _test_temp.run_folder()  # every fixture is written under this folder; tearDownModule removes it
HANG_CAP = 60  # seconds: a run takes well under one second, so this only stops a hung tool
UNIT = re.compile(r"^(\d+)-(\d+) (\S+) (.+)$")


def tearDownModule():
    shutil.rmtree(RUN, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


def require_tool():
    if not os.path.isfile(TOOL):
        raise AssertionError("bin/outline not found: %s" % TOOL)


def fixture(name, text):
    """Writes `text` to `name` in a new folder of this run and returns the path. Each call gets its own folder."""
    folder = tempfile.mkdtemp(dir=RUN)
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def run_tool(args):
    """bin/outline with `args`, as its own process, in the run folder. -> (exit code, stdout, stderr)."""
    require_tool()
    done = subprocess.run([sys.executable, TOOL] + list(args), cwd=RUN, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=HANG_CAP)
    return done.returncode, done.stdout, done.stderr


def run_in_process(args, cwd, tmp):
    """bin/outline run in this process as one call, from `cwd`, with `tmp` as the temp dir. -> (exit code, stdout, stderr).
    sys.dont_write_bytecode is set, so an import of the tool's own modules writes no .pyc. The argv, cwd, temp dir and
    bytecode switch are put back afterwards."""
    saved = (sys.argv, sys.dont_write_bytecode, os.getcwd(), tempfile.tempdir)
    out, err, code = io.StringIO(), io.StringIO(), 0
    sys.argv, sys.dont_write_bytecode, tempfile.tempdir = [TOOL] + list(args), True, tmp
    os.chdir(cwd)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            runpy.run_path(TOOL, run_name="__main__")
    except SystemExit as done:
        code = done.code or 0
    finally:
        os.chdir(saved[2])
        sys.argv, sys.dont_write_bytecode, tempfile.tempdir = saved[0], saved[1], saved[3]
    return code, out.getvalue(), err.getvalue()


def unit_lines(out):
    """The non-blank lines of `out`, each checked to be `<first>-<last> <kind> <name>` before any content is compared."""
    lines = [line for line in out.splitlines() if line.strip()]
    for line in lines:
        if not UNIT.match(line):
            raise AssertionError("not an outline line, `<first>-<last> <kind> <name>`: %r" % line)
    return lines


def nonblank(text):
    return [line for line in text.splitlines() if line.strip()]


def bounds(line):
    match = UNIT.match(line)
    return int(match.group(1)), int(match.group(2))


def span(node):
    """A unit's first and last lines: its first decorator or its def line, to its last line (ast end_lineno)."""
    decorators = [item.lineno for item in getattr(node, "decorator_list", [])]
    return min([node.lineno] + decorators), node.end_lineno


def node_named(body, kind, name):
    for node in body:
        if isinstance(node, kind) and getattr(node, "name", None) == name:
            return node
    raise AssertionError("no %s named %s in the body" % (kind.__name__, name))


def ast_method_span(path, class_name, method):
    tree = ast.parse(read(path))
    return span(node_named(node_named(tree.body, ast.ClassDef, class_name).body, ast.FunctionDef, method))


def ast_class_lines(path):
    """Each top-level class of the file as `<first>-<last> class <name>`, in file order, by ast."""
    tree = ast.parse(read(path))
    lines = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            first, last = span(node)
            lines.append("%d-%d class %s" % (first, last, node.name))
    return lines


# The Python fixture. Units, in file order: LONG (a constant of seven lines), Outer (a class), Outer.value (a method
# under a decorator), Outer.run (a method), Outer.run.inner (a def nested in a method, listed under its parent's name),
# top (a function under a decorator). SHORT is three lines, so it is not a unit.
PY_OUTLINE = '''"""Module docstring."""

import os

SHORT = {
    "a": 1,
}

LONG = {
    "a": 1,
    "b": 2,
    "c": 3,
    "d": 4,
    "e": 5,
}


class Outer:
    """Outer doc."""

    @property
    def value(self):
        return 1

    def run(self):
        def inner():
            return 2
        return inner()


@decorator
def top(x):
    return x
'''
PY_UNITS = [
    "9-15 constant LONG",
    "18-28 class Outer",
    "21-23 method Outer.value",
    "25-28 method Outer.run",
    "26-27 function Outer.run.inner",
    "31-33 function top",
]

# A constant spanning exactly five lines is not a unit (more than 5 lines is the rule); six is. A lowercase
# name is not a unit, whatever its length.
CONSTANTS = '''A_FIVE = [
    1,
    2,
    3,
]
B_SIX = [
    1,
    2,
    3,
    4,
]
lower_case = [
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
]
'''

# Comment openers inside strings: none of them opens a comment or a block, so the defs after them are read whole.
OPENERS = '''BANNER = "# not a comment"
SLASH = "// not a comment"
BLOCK = "/* not a block comment"


def after_strings():
    return "/* still a string"


class Later:
    TEXT = "class Fake:  # not a class"
    pass
'''

# A multi-line string holds lines that look like a def and a comment. Neither is a unit; holder runs to the line
# that closes the string.
MULTI = '''def holder():
    text = """
def fake():
    pass
# heading inside a string
class AlsoFake:
"""
    return text


def real():
    return 1
'''

# A lone apostrophe in a comment and in a docstring does not end a unit.
QUOTE = '''# Don't read this apostrophe as the start of a string.


def first():
    """It's fine."""
    return 1


class Second:
    # it's a lone quote
    pass
'''

# Markdown: each heading ends on the line before the next heading of the same or a higher level. A blank line
# before that heading belongs to the earlier heading.
MARKDOWN = '''# Guide

## Install

### Linux

Text.

## Usage

Use it.
'''
MARKDOWN_UNITS = [
    "1-11 heading Guide",
    "3-8 heading Install",
    "5-8 heading Linux",
    "9-11 heading Usage",
]

# A heading inside a fenced block is not a heading.
FENCE = '''# Title

Don't stop reading here.

```bash
# not a heading
## also not a heading
```

## Next

Body.
'''
FENCE_UNITS = [
    "1-12 heading Title",
    "10-12 heading Next",
]

# A YAML workflow: a job is `jobs.<id>`; a step is `jobs.<id>.<name>`, and an unnamed step takes its `uses:` value,
# or the text after its `run:`. The `- name: fake` line is inside a `run: |` block, so it is not a step.
WORKFLOW = '''name: checks
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Real step
        run: |
          echo start
          - name: fake
          echo end
      - name: Next
        run: echo next
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Lint
        run: python3 lint/x.py
      - run: echo hi
'''
WORKFLOW_UNITS = [
    "4-13 job jobs.build",
    "7-11 step jobs.build.Real step",
    "12-13 step jobs.build.Next",
    "14-20 job jobs.lint",
    "17-17 step jobs.lint.actions/checkout@v4",
    "18-19 step jobs.lint.Lint",
    "20-20 step jobs.lint.echo hi",
]

# Shell: functions only. A function inside a here-doc is text, and so is a function line inside a string.
SHELL = '''#!/bin/sh
# don't use this apostrophe as a quote start
build() {
  echo "# not a comment"
  echo "/* open"
}
cat <<'EOF'
helper() {
  echo inside heredoc
}
EOF
cat <<-EOT
\tinner() {
\t}
EOT
deploy() {
  echo deploying
}
'''
SHELL_UNITS = [
    "3-6 function build",
    "16-18 function deploy",
]

# Two methods with one bare name: a symbol that matches both is ambiguous.
AMBIGUOUS = '''class A:
    def run(self):
        return 1


class B:
    def run(self):
        return 2
'''


# A bare name shared by a top-level function and a method is ambiguous: both are candidates.
SHARED = '''def run():
    return 1


class A:
    def run(self):
        return 2
'''

# A nested class is a unit under its dotted name. A class under a module-level `if` or `try` is a unit too.
NESTED = '''class Outer:
    """Outer doc."""

    class Inner:
        value = 1

    def run(self):
        return 2
'''
NESTED_UNITS = ["1-8 class Outer", "4-5 class Outer.Inner", "7-8 method Outer.run"]
GATED = '''import sys

if sys.platform:
    class Gated:
        value = 1
'''
TRY_CLASS = '''try:
    class Loaded:
        value = 1
except ImportError:
    pass
'''

# A YAML file indented with a tab is refused: the reader takes spaces only.
TABBED = '''name: checks
on: push
jobs:
\tbuild:
\t\truns-on: ubuntu-latest
'''

# A form feed or a U+2028 inside a line is not a line break. Line numbers count newlines only, as sed does.
MD_FORM_FEED = '# One\n\nfirst\fpart\n\n## Two\n\nbody\n'
MD_LINE_SEP = MD_FORM_FEED.replace("\f", " ")
MD_SPLIT_UNITS = ["1-7 heading One", "5-7 heading Two"]
YAML_FORM_FEED = '''name: checks
on: push
jobs:
  build:
    # a note\fcarries on
    steps:
      - name: Real
        run: echo hi
'''
YAML_LINE_SEP = YAML_FORM_FEED.replace("\f", " ")
YAML_UNITS = ["4-8 job jobs.build", "7-8 step jobs.build.Real"]
SHELL_FORM_FEED = '#!/bin/sh\n# a\fb\nbuild() {\n  echo hi\n}\n'
SHELL_LINE_SEP = SHELL_FORM_FEED.replace("\f", " ")
SHELL_SPLIT_UNITS = ["3-5 function build"]

# A subshell body with a case pattern: the pattern's `)` is not the end of the body.
SUBSHELL = '''#!/bin/sh
f() (
  case "$1" in
    a) echo one ;;
    *) echo other ;;
  esac
)
'''
SUBSHELL_UNITS = ["2-7 function f"]

# A quoted YAML value is text: a hash, a double slash or a slash star in it starts no comment, and a lone apostrophe
# in a plain value is text too.
QUOTED_HASH = '''jobs:
  lint:
    steps:
      - name: "build # 1"
        run: echo one
'''
QUOTED_SLASH = '''jobs:
  lint:
    steps:
      - name: "a // b /* c"
        run: echo one
'''
APOSTROPHE = '''jobs:
  lint:
    steps:
      - name: Don't stop
        run: echo it's
'''

# Shell: a double-quoted string is text, so a hash, a brace or a slash opener in it is not code. A lone apostrophe in a
# here-doc or after a comment's hash is text. A string spanning two lines holds a def line and a hash line as text.
SHELL_HASH_IN_QUOTES = '''f() {
  echo "# }"
}
g() {
  echo two
}
'''
SHELL_SLASH_IN_QUOTES = '''k() {
  echo "/* {"
  echo "// {"
}
m() {
  echo x
}
'''
SHELL_APOSTROPHE_IN_HEREDOC = '''#!/bin/sh
cat <<EOF
it's a lone quote
g() {
EOF
h() {
  echo ok
}
'''
SHELL_MULTI_LINE_STRING = '''f() {
  echo "first
# not a comment
g() {
second"
}
h() {
  echo ok
}
'''
SHELL_APOSTROPHE_AFTER_HASH = '''build() { # it's the build
  echo ok
}
deploy() {
  echo go
}
'''


def assert_outline(case, path, want):
    code, out, err = run_tool([path])
    case.assertEqual(code, 0, "exit %d on a file the tool reads: %s%s" % (code, out, err))
    case.assertEqual(unit_lines(out), want, "the outline of %s is not the expected units" % os.path.basename(path))


class PythonOutline(unittest.TestCase):
    def test_each_unit_is_listed_in_file_order_with_its_qualified_name(self):
        assert_outline(self, fixture("outer.py", PY_OUTLINE), PY_UNITS)

    def test_upper_case_constant_of_six_lines_is_listed_and_five_is_not(self):
        assert_outline(self, fixture("constants.py", CONSTANTS), ["6-11 constant B_SIX"])

    def test_comment_openers_inside_strings_start_nothing(self):
        assert_outline(self, fixture("openers.py", OPENERS), ["6-7 function after_strings", "10-12 class Later"])

    def test_lines_inside_a_multi_line_string_are_not_units(self):
        assert_outline(self, fixture("multi.py", MULTI), ["1-8 function holder", "11-12 function real"])

    def test_a_lone_quote_in_a_comment_or_docstring_does_not_end_a_unit(self):
        assert_outline(self, fixture("quote.py", QUOTE), ["4-6 function first", "9-11 class Second"])

    def test_an_empty_python_file_prints_no_unit_and_exits_0(self):
        code, out, err = run_tool([fixture("empty.py", "")])
        self.assertEqual(code, 0, "exit %d on an empty Python file: %s%s" % (code, out, err))
        self.assertEqual(unit_lines(out), [], "an empty Python file printed a unit")

    def test_a_class_under_a_module_level_if_is_a_unit(self):
        assert_outline(self, fixture("gated.py", GATED), ["4-5 class Gated"])

    def test_a_class_under_a_module_level_try_is_a_unit(self):
        assert_outline(self, fixture("try_class.py", TRY_CLASS), ["2-3 class Loaded"])

    def test_a_nested_class_is_listed_under_its_dotted_name_with_its_range(self):
        assert_outline(self, fixture("nested.py", NESTED), NESTED_UNITS)


class MarkdownOutline(unittest.TestCase):
    def test_each_heading_ends_before_the_next_of_same_or_higher_level(self):
        assert_outline(self, fixture("guide.md", MARKDOWN), MARKDOWN_UNITS)

    def test_a_heading_inside_a_fenced_block_is_not_a_heading(self):
        assert_outline(self, fixture("fence.md", FENCE), FENCE_UNITS)

    def test_a_form_feed_inside_a_line_is_not_a_line_break(self):
        assert_outline(self, fixture("form.md", MD_FORM_FEED), MD_SPLIT_UNITS)

    def test_a_line_separator_inside_a_line_is_not_a_line_break(self):
        assert_outline(self, fixture("separator.md", MD_LINE_SEP), MD_SPLIT_UNITS)


class YamlOutline(unittest.TestCase):
    def test_a_run_block_line_that_looks_like_a_step_is_not_a_step(self):
        assert_outline(self, fixture("checks.yml", WORKFLOW), WORKFLOW_UNITS)

    def test_a_form_feed_inside_a_line_is_not_a_line_break(self):
        assert_outline(self, fixture("form.yml", YAML_FORM_FEED), YAML_UNITS)

    def test_a_line_separator_inside_a_line_is_not_a_line_break(self):
        assert_outline(self, fixture("separator.yml", YAML_LINE_SEP), YAML_UNITS)

    def test_a_hash_inside_quotes_in_a_yaml_value_is_text(self):
        assert_outline(self, fixture("hash.yml", QUOTED_HASH), ["2-5 job jobs.lint", "4-5 step jobs.lint.build # 1"])

    def test_a_double_slash_and_a_slash_star_inside_quotes_in_a_yaml_value_are_text(self):
        assert_outline(self, fixture("slash.yml", QUOTED_SLASH), ["2-5 job jobs.lint", "4-5 step jobs.lint.a // b /* c"])

    def test_a_lone_apostrophe_in_a_plain_yaml_value_is_text(self):
        assert_outline(self, fixture("apostrophe.yml", APOSTROPHE), ["2-5 job jobs.lint", "4-5 step jobs.lint.Don't stop"])


class ShellOutline(unittest.TestCase):
    def test_a_function_inside_a_here_doc_is_not_a_function(self):
        assert_outline(self, fixture("run.sh", SHELL), SHELL_UNITS)

    def test_a_form_feed_inside_a_line_is_not_a_line_break(self):
        assert_outline(self, fixture("form.sh", SHELL_FORM_FEED), SHELL_SPLIT_UNITS)

    def test_a_line_separator_inside_a_line_is_not_a_line_break(self):
        assert_outline(self, fixture("separator.sh", SHELL_LINE_SEP), SHELL_SPLIT_UNITS)

    def test_a_subshell_body_with_a_case_pattern_ends_at_its_closing_paren(self):
        assert_outline(self, fixture("subshell.sh", SUBSHELL), SUBSHELL_UNITS)

    def test_a_hash_inside_double_quotes_is_text(self):
        assert_outline(self, fixture("hash.sh", SHELL_HASH_IN_QUOTES), ["1-3 function f", "4-6 function g"])

    def test_a_slash_star_and_a_double_slash_inside_double_quotes_are_text(self):
        assert_outline(self, fixture("slash.sh", SHELL_SLASH_IN_QUOTES), ["1-4 function k", "5-7 function m"])

    def test_a_lone_apostrophe_in_a_here_doc_is_text(self):
        assert_outline(self, fixture("heredoc.sh", SHELL_APOSTROPHE_IN_HEREDOC), ["6-8 function h"])

    def test_a_string_spanning_two_lines_holds_a_def_line_and_a_hash_line_as_text(self):
        assert_outline(self, fixture("multi.sh", SHELL_MULTI_LINE_STRING), ["1-6 function f", "7-9 function h"])

    def test_a_lone_apostrophe_in_a_comment_after_a_function_header_is_text(self):
        assert_outline(self, fixture("comment.sh", SHELL_APOSTROPHE_AFTER_HASH), ["1-3 function build", "4-6 function deploy"])


class SymbolMode(unittest.TestCase):
    def test_an_exact_qualified_name_prints_only_its_line(self):
        code, out, err = run_tool([fixture("outer.py", PY_OUTLINE), "Outer.value"])
        self.assertEqual(code, 0, "exit %d on an exact qualified name: %s%s" % (code, out, err))
        self.assertEqual(unit_lines(out), ["21-23 method Outer.value"], "the exact name did not print its one line")

    def test_a_unique_bare_method_name_matches_its_method(self):
        code, out, err = run_tool([fixture("outer.py", PY_OUTLINE), "value"])
        self.assertEqual(code, 0, "exit %d on a unique bare name: %s%s" % (code, out, err))
        self.assertEqual(unit_lines(out), ["21-23 method Outer.value"], "the bare name did not print the method's line")

    def test_an_ambiguous_name_exits_1_and_prints_every_candidate(self):
        code, out, err = run_tool([fixture("amb.py", AMBIGUOUS), "run"])
        self.assertEqual(code, 1, "an ambiguous name exited %d, not 1: %s%s" % (code, out, err))
        for line in ["2-3 method A.run", "7-8 method B.run"]:
            self.assertIn(line, out, "the ambiguous name does not print the candidate %r: %s" % (line, out))

    def test_a_missing_name_exits_1_with_one_line(self):
        code, out, err = run_tool([fixture("outer.py", PY_OUTLINE), "Outer.nope"])
        self.assertEqual(code, 1, "a missing name exited %d, not 1: %s%s" % (code, out, err))
        self.assertEqual(len(nonblank(out + err)), 1, "a missing name did not print exactly one line: %r" % (out + err))


    def test_a_bare_name_shared_by_a_function_and_a_method_prints_both_and_exits_1(self):
        code, out, err = run_tool([fixture("shared.py", SHARED), "run"])
        self.assertEqual(code, 1, "a bare name shared by a function and a method exited %d, not 1: %s%s" % (code, out, err))
        for line in ["1-2 function run", "6-7 method A.run"]:
            self.assertIn(line, out, "a bare name shared by a function and a method does not print %r: %s" % (line, out))

    def test_a_nested_class_prints_its_range_for_its_dotted_name(self):
        code, out, err = run_tool([fixture("nested.py", NESTED), "Outer.Inner"])
        self.assertEqual(code, 0, "exit %d on the dotted name of a nested class: %s%s" % (code, out, err))
        self.assertEqual(unit_lines(out), ["4-5 class Outer.Inner"], "the dotted name of a nested class did not print its range")

    def test_a_nested_class_prints_its_range_for_its_bare_name_when_unique(self):
        code, out, err = run_tool([fixture("nested.py", NESTED), "Inner"])
        self.assertEqual(code, 0, "exit %d on the unique bare name of a nested class: %s%s" % (code, out, err))
        self.assertEqual(unit_lines(out), ["4-5 class Outer.Inner"], "the bare name of a nested class did not print its range")

    def test_a_class_under_a_module_level_if_prints_its_range_for_its_bare_name(self):
        code, out, err = run_tool([fixture("gated.py", GATED), "Gated"])
        self.assertEqual(code, 0, "exit %d on the bare name of a class under an if: %s%s" % (code, out, err))
        self.assertEqual(unit_lines(out), ["4-5 class Gated"], "the bare name of a class under an if did not print its range")

    def test_a_class_under_a_module_level_try_prints_its_range_for_its_bare_name(self):
        code, out, err = run_tool([fixture("try_class.py", TRY_CLASS), "Loaded"])
        self.assertEqual(code, 0, "exit %d on the bare name of a class under a try: %s%s" % (code, out, err))
        self.assertEqual(unit_lines(out), ["2-3 class Loaded"], "the bare name of a class under a try did not print its range")


class Refusals(unittest.TestCase):
    def test_a_file_type_that_is_not_read_exits_2_with_one_line(self):
        code, out, err = run_tool([fixture("notes.txt", "plain text\n")])
        self.assertEqual(code, 2, "a .txt file exited %d, not 2: %s%s" % (code, out, err))
        self.assertEqual(len(nonblank(out + err)), 1, "a .txt file did not print exactly one line: %r" % (out + err))

    # Pins: the head already exits 2 with one line in each case below. The commit's Red-run trailers name a mutant of
    # the refusal each one reaches, so each goes red if that refusal stops exiting 2.
    def test_a_missing_file_exits_2_with_one_line(self):
        code, out, err = run_tool([os.path.join(tempfile.mkdtemp(dir=RUN), "gone.py")])
        self.assertEqual(code, 2, "a missing file exited %d, not 2: %s%s" % (code, out, err))
        self.assertEqual(len(nonblank(out + err)), 1, "a missing file did not print exactly one line: %r" % (out + err))

    def test_a_python_file_with_a_syntax_error_exits_2_with_one_line(self):
        code, out, err = run_tool([fixture("broken.py", "def broken(:\n")])
        self.assertEqual(code, 2, "a Python file with a syntax error exited %d, not 2: %s%s" % (code, out, err))
        self.assertEqual(len(nonblank(out + err)), 1, "a Python syntax error did not print exactly one line: %r" % (out + err))


    def test_a_tab_indented_yaml_file_exits_2_with_one_line(self):
        code, out, err = run_tool([fixture("tabbed.yml", TABBED)])
        self.assertEqual(code, 2, "a tab-indented YAML file exited %d, not 2: %s%s" % (code, out, err))
        self.assertEqual(len(nonblank(out + err)), 1, "a tab-indented YAML file did not print exactly one line: %r" % (out + err))


class HelpFlag(unittest.TestCase):
    def test_the_long_help_flag_prints_usage_and_exits_0(self):
        code, out, err = run_tool(["--help"])
        self.assertEqual(code, 0, "--help exited %d, not 0: %s%s" % (code, out, err))
        self.assertIn("usage:", out.lower(), "--help printed no usage line: %r" % (out + err))

    def test_the_short_help_flag_prints_usage_and_exits_0(self):
        code, out, err = run_tool(["-h"])
        self.assertEqual(code, 0, "-h exited %d, not 0: %s%s" % (code, out, err))
        self.assertIn("usage:", out.lower(), "-h printed no usage line: %r" % (out + err))

    def test_help_names_each_kind_of_unit(self):
        code, out, err = run_tool(["--help"])
        for kind in ("python", "markdown", "yaml", "shell"):
            self.assertIn(kind, out.lower(), "--help does not name the %s kind: %r" % (kind, out + err))

    def test_help_names_the_file_and_symbol_call_forms(self):
        code, out, err = run_tool(["--help"])
        self.assertIn("FILE", out, "--help does not show the FILE argument: %r" % (out + err))
        self.assertIn("SYMBOL", out, "--help does not show the SYMBOL argument: %r" % (out + err))

    def test_help_names_the_exit_codes(self):
        code, out, err = run_tool(["--help"])
        self.assertIn("exit", out.lower(), "--help does not name the exit codes: %r" % (out + err))


class RealFiles(unittest.TestCase):
    def test_host_merge_is_one_def_whose_range_matches_ast_in_the_same_file(self):
        code, out, err = run_tool([MERGE, "Host.merge"])
        self.assertEqual(code, 0, "exit %d on merge/merge.py Host.merge: %s%s" % (code, out, err))
        lines = unit_lines(out)
        self.assertEqual(len(lines), 1, "Host.merge did not resolve to one line: %r" % lines)
        first, last = bounds(lines[0])
        with open(MERGE, encoding="utf-8") as handle:
            text = handle.read().splitlines()
        self.assertIn("def merge(", text[first - 1], "the first line of Host.merge is not its def: %r" % text[first - 1])
        self.assertEqual((first, last), ast_method_span(MERGE, "Host", "merge"), "Host.merge's range differs from ast's")

    def test_every_top_level_class_of_test_merge_has_its_ast_range(self):
        code, out, err = run_tool([TEST_MERGE])
        self.assertEqual(code, 0, "exit %d on merge/test_merge.py: %s%s" % (code, out, err))
        # A class nested in a class has a dotted name and is pinned by its own cases, so this compares dotless class units only.
        got = [line for line in unit_lines(out)
               if line.split(" ", 2)[1] == "class" and "." not in line.split(" ", 2)[2]]
        want = ast_class_lines(TEST_MERGE)
        self.assertGreater(len(want), 0, "ast finds no top-level class in merge/test_merge.py: the oracle is empty")
        self.assertEqual(got, want, "the class lines of merge/test_merge.py differ from ast's top-level classes")


class OneCall(unittest.TestCase):
    """A call is one call of the tool, starts no child process and writes no file. The tool runs in this process, so
    cost_probe.children() counts every child it starts through subprocess.Popen. Its folders are the fixture folder,
    an empty working folder and an empty temp dir, which must stay as they were."""

    def test_a_call_starts_no_child_process_and_writes_no_file(self):
        require_tool()
        path = fixture("cost.py", PY_OUTLINE)
        folder = os.path.dirname(path)
        cwd, tmp = tempfile.mkdtemp(dir=RUN), tempfile.mkdtemp(dir=RUN)
        before = cost_probe.snapshot(folder)
        with cost_probe.children() as log:
            code, out, err = run_in_process([path], cwd, tmp)
        self.assertEqual(unit_lines(out), PY_UNITS, "the call printed no outline, so its child count means nothing: %s%s" % (out, err))
        self.assertEqual(code, 0, "the call exited %d: %s" % (code, err))
        self.assertEqual(log.argvs, [], "the call started child processes: %r" % log.argvs)
        self.assertEqual(cost_probe.written(before, cost_probe.snapshot(folder)), [], "the call wrote into the fixture folder")
        self.assertEqual(cost_probe.leftovers(cwd), [], "the call left files in its working folder")
        self.assertEqual(cost_probe.leftovers(tmp), [], "the call left files in the temp dir")


class FixtureControl(unittest.TestCase):
    """Green on the old code, since no tool runs here. The expected ranges of the Python fixture are the ranges ast
    reads, so a red case means the tool is wrong, not the expected numbers."""

    def test_python_fixture_expected_ranges_are_the_ast_ranges(self):
        tree = ast.parse(PY_OUTLINE)
        long_ = [node for node in tree.body if isinstance(node, ast.Assign) and node.targets[0].id == "LONG"][0]
        outer = node_named(tree.body, ast.ClassDef, "Outer")
        value = node_named(outer.body, ast.FunctionDef, "value")
        run = node_named(outer.body, ast.FunctionDef, "run")
        inner = node_named(run.body, ast.FunctionDef, "inner")
        top = node_named(tree.body, ast.FunctionDef, "top")
        got = [span(node) for node in (long_, outer, value, run, inner, top)]
        self.assertEqual(got, [bounds(line) for line in PY_UNITS], "the expected ranges of the Python fixture are not ast's")


if __name__ == "__main__":
    unittest.main()
