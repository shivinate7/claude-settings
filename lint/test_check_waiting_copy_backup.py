#!/usr/bin/env python3
"""Cases for lint/check_waiting_copy_backup.py: the waiting copy is a backup, never a live source.

    python3 lint/test_check_waiting_copy_backup.py

The copy folder (layout kind `waiting-data`) may be read as content by one tool only: the recovery,
merge and export functions of skills/waiting-page/export_page.py. The suite pins the contract through the
command line only:

    python3 lint/check_waiting_copy_backup.py [--root DIR]
    exit 0  clean
    exit 1  findings, one line each:
              <path>:<line>: reads the waiting copy folder as a live source    (a reader)
              <path>: does not call the waiting copy a backup                 (prose)
    exit 2  unknown: a prose file cannot be read

A reader is a source file under skills/, hooks/, lint/ or bin/ (an extensionless file with a python or
shell shebang counts too). A test path (hooks/guard.py is_test_rel) is not a tool. A reader names the copy
folder by name (the string "waiting-data", the segment "waiting" in a path, or a call to waiting_copy()) and
reads its content (open, read, read_text, load, grep, cat-file, show, readFileSync, cat, head, jq). The copy
may reach the read through variables, attributes, closures, helper calls and imports. Metadata reads do not
count (log, ls-tree, rev-parse, isdir, getmtime). A presence check of an item under the copy (isfile, exists,
listdir) is a read. Text in a string or a comment does not count, and "waiting-data-in-repo" names another file.

WAITING_COPY_CHECK_UNDER_TEST names the script to run instead, for the stub run (lint/waiting_copy_stub_test.py).
"""
import ast
import os
import re
import shutil
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)

CHECK = os.environ.get("WAITING_COPY_CHECK_UNDER_TEST") or os.path.join(HERE, "check_waiting_copy_backup.py")
RUN_FOLDER = None  # made in setUpModule, so an import leaks no folder
WAITING = "skills/waiting-page"
SKILL, COPIES, EXPORT = WAITING + "/SKILL.md", WAITING + "/reference/copies-and-accounts.md", WAITING + "/export_page.py"
PROSE_FILES = (SKILL, COPIES, EXPORT)
BACKUP = re.compile(r"\bbackups?\b", re.IGNORECASE)
GOOD_PROSE = {
    SKILL: "The copy in git is a backup for recovery and account moves.\n",
    COPIES: "The copy in git is a backup for recovery and account moves.\n",
    EXPORT: '"""Export. The copy in git is a backup for recovery and account moves."""\n',
}
LIVE = "reads the waiting copy folder as a live source"

DIRECT = '''import json, os

def read_items(layout, root):
    folder = layout.path(root, "waiting-data")
    out = []
    for name in os.listdir(os.path.join(folder, "items")):
        with open(os.path.join(folder, "items", name), encoding="utf-8") as handle:
            out.append(json.load(handle))
    return out
'''

RESOLVER = '''def filed_numbers(layout, root):
    folder = waiting_copy(layout, root)
    return _run_git(root, ["grep", "-I", "-e", ".", "origin/main", "--", folder + "/items/"])
'''

HELPER = '''def read_items(folder):
    return open(os.path.join(folder, "items", "1.json"), encoding="utf-8").read()

def run(layout, root):
    return read_items(layout.path(root, "waiting-data"))
'''

BIN = '''#!/usr/bin/env python3
import json, os

def main(layout, root):
    folder = layout.path(root, "waiting-data")
    return json.load(open(os.path.join(folder, "items", "1.json")))
'''

JS_READ = ('function readItem(layout, root) { return fs.readFileSync(path.join('
           'layout.path(root, "waiting-data"), "items", "1.json")); }\n')

JS_TEMPLATE = ("const banner = `\n/* a template line, not a comment\n`;\n"
               + JS_READ)

HASH_IN_STRING = '''def read(layout, root):
    base = "https://example.test/#frag"; data = open(os.path.join(layout.path(root, "waiting-data"), "items", "1.json")).read()
    return base, data
'''

QUOTE_IN_COMMENT = '''def read(layout, root):
    # don't skip this read: it is the copy's items
    folder = layout.path(root, "waiting-data")
    return open(os.path.join(folder, "items", "1.json")).read()
'''

MENTION = '''"""The waiting-data folder is a backup. Only export_page.py may open it as a source."""

# open the waiting-data folder items/ in export_page.py only

def describe():
    return "waiting-data folder: read by export_page.py only"
'''

OTHER_NAME = '''def decision_text():
    return open("docs/decisions/waiting-data-in-repo.md", encoding="utf-8").read()
'''

PROBES = '''def copy_age(layout, root):
    folder = waiting_copy(layout, root)
    return _run_git(root, ["log", "-1", "--format=%ct", "refs/remotes/origin/main", "--", folder + "/"])

def copy_present(root):
    return _run_git(root, ["ls-tree", "--name-only", "origin/main", "--", layout.path(root, "waiting-data")])
'''

TEST_PATH_READER = '''def read_copy(layout, root):
    return open(os.path.join(layout.path(root, "waiting-data"), "items", "1.json")).read()
'''

PEEK_PARAM = '''

def peek_items(folder):
    return open(os.path.join(folder, "items", "1.json")).read()
'''

SHELL_FORMS = (
    ("cat", "bin/peek_cat", "cat $ROOT/waiting-data/items/1.json"),
    ("head", "bin/peek_head", "head -n 5 $ROOT/waiting-data/items/1.json"),
    ("jq", "bin/peek_jq", "jq . $ROOT/waiting-data/items/1.json"),
    ("quoted", "bin/peek_quoted", 'cat "$ROOT/waiting-data/items/1.json"'),
)

JS_TWO_LINE = ('const folder = layout.path(root, "waiting-data");\n'
               'const text = fs.readFileSync(path.join(folder, "items", "1.json"), "utf8");\n')

GIT_LIST = '''import subprocess

def head_item(root):
    return subprocess.run(["git", "-C", root, "show", "origin/main:waiting/items/1.json"], capture_output=True)
'''

GIT_STRING = '''import subprocess

def head_item(root):
    return subprocess.run("git show origin/main:waiting-data/items/1.json", shell=True, cwd=root)
'''

TWO_STEPS = '''import json, os

def copy_folder(layout, root):
    return layout.path(root, "waiting-data")

def read_items(folder):
    with open(os.path.join(folder, "items", "1.json"), encoding="utf-8") as handle:
        return json.load(handle)

def compose(layout, root):
    return read_items(copy_folder(layout, root))
'''

PRESENCE_FORMS = (
    ("isfile", 'import os\n\ndef filed(layout, root):\n'
               '    return os.path.isfile(os.path.join(layout.path(root, "waiting-data"), "items", "1.json"))\n'),
    ("exists", 'import os\n\ndef filed(layout, root):\n'
               '    return os.path.exists(os.path.join(layout.path(root, "waiting-data"), "items", "1.json"))\n'),
    ("listdir", 'import os\n\ndef filed(layout, root):\n'
                '    return os.listdir(os.path.join(layout.path(root, "waiting-data"), "items"))\n'),
)

TWO_FILED = '''class Homes:
    def filed_numbers(self, layout, root):
        folder = waiting_copy(layout, root)
        return _run_git(root, ["grep", "-I", "-e", ".", "origin/main", "--", folder + "/items/"])


class Other:
    def filed_numbers(self, layout, root):
        folder = waiting_copy(layout, root)
        return _run_git(root, ["grep", "-I", "-e", ".", "origin/main", "--", folder + "/items/"])
'''

LAYOUT_READER = '''import json, os

def copy_path(root):
    with open(os.path.join(root, "lint", "layout.json"), encoding="utf-8") as handle:
        kinds = json.load(handle)["kinds"]
    return kinds["waiting-data"]["path"]
'''


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


def tree(name, files, prose=True):
    """A fixture tree under this run's folder: the good prose files (unless prose is False), then `files` over them."""
    root = os.path.join(RUN_FOLDER, name)
    merged = dict(GOOD_PROSE) if prose else {}
    merged.update(files)
    for rel, text in merged.items():
        path = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    return root


def check(root):
    """(exit code, stdout) of the check run with --root on `root`."""
    done = subprocess.run([sys.executable, CHECK, "--root", root], capture_output=True, text=True,
                          encoding="utf-8")
    return done.returncode, done.stdout


def reader_lines(out):
    return [line for line in out.splitlines() if LIVE in line]


def reader_named(out, rel):
    return any(line.startswith(rel + ":") for line in reader_lines(out))


class ReaderCases(unittest.TestCase):
    def test_direct_read_of_the_copy_fails(self):
        root = tree(self._testMethodName, {"hooks/reads_direct.py": DIRECT})
        rc, out = check(root)
        self.assertEqual(rc, 1, "a direct read of the copy folder passed: %r" % out)
        self.assertTrue(reader_named(out, "hooks/reads_direct.py"), "hooks/reads_direct.py was not flagged as a live reader")

    def test_resolver_then_git_grep_of_items_fails(self):
        root = tree(self._testMethodName, {"hooks/reads_resolver.py": RESOLVER})
        rc, out = check(root)
        self.assertEqual(rc, 1, "a git grep of the copy's items passed: %r" % out)
        self.assertTrue(reader_named(out, "hooks/reads_resolver.py"), "hooks/reads_resolver.py was not flagged as a live reader")

    def test_handle_passed_to_a_reading_helper_fails(self):
        root = tree(self._testMethodName, {"hooks/reads_helper.py": HELPER})
        rc, out = check(root)
        self.assertEqual(rc, 1, "a copy folder passed to a reading helper passed: %r" % out)
        self.assertTrue(reader_named(out, "hooks/reads_helper.py"), "hooks/reads_helper.py was not flagged as a live reader")

    def test_reader_in_an_extensionless_bin_script_fails(self):
        root = tree(self._testMethodName, {"bin/peek": BIN})
        rc, out = check(root)
        self.assertEqual(rc, 1, "a reader in bin/peek (python shebang) passed: %r" % out)
        self.assertTrue(reader_named(out, "bin/peek"), "bin/peek was not flagged as a live reader")

    def test_reader_in_javascript_fails(self):
        root = tree(self._testMethodName, {"skills/waiting-page/peek.mjs": JS_READ})
        rc, out = check(root)
        self.assertEqual(rc, 1, "a javascript reader passed: %r" % out)
        self.assertTrue(reader_named(out, "skills/waiting-page/peek.mjs"), "peek.mjs was not flagged as a live reader")

    def test_comment_opener_inside_a_string_does_not_hide_a_reader(self):
        root = tree(self._testMethodName, {"lint/hash_reader.py": HASH_IN_STRING})
        rc, out = check(root)
        self.assertEqual(rc, 1, "a reader after a '#' inside a string passed: %r" % out)
        self.assertTrue(reader_named(out, "lint/hash_reader.py"), "a reader after '#' in a string was not flagged")

    def test_lone_quote_in_a_comment_does_not_hide_a_reader(self):
        root = tree(self._testMethodName, {"hooks/quote_reader.py": QUOTE_IN_COMMENT})
        rc, out = check(root)
        self.assertEqual(rc, 1, "a reader after a comment with a lone quote passed: %r" % out)
        self.assertTrue(reader_named(out, "hooks/quote_reader.py"), "a reader after a lone quote was not flagged")

    def test_comment_opener_in_a_template_literal_does_not_hide_a_reader(self):
        root = tree(self._testMethodName, {"skills/waiting-page/template_reader.mjs": JS_TEMPLATE})
        rc, out = check(root)
        self.assertEqual(rc, 1, "a reader after a template literal with '/*' passed: %r" % out)
        self.assertTrue(reader_named(out, "skills/waiting-page/template_reader.mjs"),
                        "a reader after a template literal was not flagged")

    def test_one_reader_among_many_files_is_the_only_finding(self):
        files = {"hooks/clean_%02d.py" % i: "def value():\n    return %d\n" % i for i in range(60)}
        files["lint/reader.py"] = DIRECT
        root = tree(self._testMethodName, files)
        rc, out = check(root)
        self.assertEqual(rc, 1, "a reader among 61 files passed: %r" % out)
        self.assertEqual(len(reader_lines(out)), 1, "more or fewer than one reader was named: %r" % out)
        self.assertTrue(reader_named(out, "lint/reader.py"), "lint/reader.py was not the named reader")


class ControlCases(unittest.TestCase):
    def test_empty_source_tree_passes(self):
        root = tree(self._testMethodName, {})
        rc, out = check(root)
        self.assertEqual(rc, 0, "a tree with the prose and no source passed as dirty: %r" % out)

    def test_mention_in_a_docstring_comment_and_string_passes(self):
        root = tree(self._testMethodName, {"hooks/mentions.py": MENTION})
        rc, out = check(root)
        self.assertEqual(rc, 0, "a mention of the copy folder with no read was flagged: %r" % out)

    def test_other_file_named_with_the_copy_kind_prefix_passes(self):
        root = tree(self._testMethodName, {"lint/cites.py": OTHER_NAME})
        rc, out = check(root)
        self.assertEqual(rc, 0, "waiting-data-in-repo was read as the copy folder: %r" % out)

    def test_metadata_reads_of_the_copy_pass(self):
        root = tree(self._testMethodName, {"hooks/probe.py": PROBES})
        rc, out = check(root)
        self.assertEqual(rc, 0, "a commit-time or presence probe of the copy was flagged: %r" % out)

    def test_test_paths_are_not_tools(self):
        root = tree(self._testMethodName, {"hooks/test_reads_copy.py": TEST_PATH_READER})
        rc, out = check(root)
        self.assertEqual(rc, 0, "a test file that reads a fixture copy was flagged: %r" % out)

    def test_export_page_real_file_has_no_reader_finding(self):
        with open(os.path.join(ROOT, *EXPORT.split("/")), encoding="utf-8") as handle:
            real = handle.read()
        root = tree(self._testMethodName, {EXPORT: real})
        rc, out = check(root)
        self.assertFalse([line for line in reader_lines(out) if line.startswith(EXPORT + ":")],
                         "export_page.py's own recovery, merge and export modes were flagged: %r" % out)

    def test_export_page_parameter_reader_fails(self):
        with open(os.path.join(ROOT, *EXPORT.split("/")), encoding="utf-8") as handle:
            real = handle.read()
        text = real + PEEK_PARAM
        root = tree(self._testMethodName, {EXPORT: text})
        rc, out = check(root)
        def_line = next(i for i, line in enumerate(text.split("\n"), 1) if "def peek_items" in line)
        self.assertEqual(rc, 1, "a new export_page.py function that reads a folder passed in was not flagged: %r" % out)
        numbers = reader_line_numbers(out, EXPORT)
        self.assertTrue(any(def_line <= n <= def_line + 2 for n in numbers),
                        "peek_items in export_page.py (line %d) was not the flagged reader, found %r" % (def_line, numbers))


def reader_line_numbers(out, rel):
    return [int(line.split(":")[1]) for line in reader_lines(out) if line.startswith(rel + ":")]


class UnflaggedReaderCases(unittest.TestCase):
    """Unflagged readers a session could reach by mistake in normal work (decision guard-guards-mistakes-only)."""

    def test_shell_read_of_the_copy_items_fails(self):
        for form, rel, command in SHELL_FORMS:
            with self.subTest(form=form):
                root = tree("%s-%s" % (self._testMethodName, form), {rel: "#!/bin/sh\n" + command + "\n"})
                rc, out = check(root)
                self.assertEqual(rc, 1, "a shell %s of the copy's items passed: %r" % (form, out))
                self.assertTrue(reader_named(out, rel), "%s was not flagged as a live reader" % rel)

    def test_two_line_javascript_read_fails(self):
        root = tree(self._testMethodName, {"skills/waiting-page/two_line.mjs": JS_TWO_LINE})
        rc, out = check(root)
        self.assertEqual(rc, 1, "a javascript read split over two lines passed: %r" % out)
        self.assertTrue(reader_named(out, "skills/waiting-page/two_line.mjs"), "two_line.mjs was not flagged")

    def test_git_argument_list_with_a_literal_copy_path_fails(self):
        root = tree(self._testMethodName, {"hooks/reads_git_list.py": GIT_LIST})
        rc, out = check(root)
        self.assertEqual(rc, 1, "git show of a literal waiting/ path in an argument list passed: %r" % out)
        self.assertTrue(reader_named(out, "hooks/reads_git_list.py"), "reads_git_list.py was not flagged")

    def test_git_shell_string_with_the_copy_name_fails(self):
        root = tree(self._testMethodName, {"hooks/reads_git_string.py": GIT_STRING})
        rc, out = check(root)
        self.assertEqual(rc, 1, "a git show of waiting-data in a shell string passed: %r" % out)
        self.assertTrue(reader_named(out, "hooks/reads_git_string.py"), "reads_git_string.py was not flagged")

    def test_name_read_and_compose_in_three_helpers_fails(self):
        root = tree(self._testMethodName, {"hooks/reads_two_steps.py": TWO_STEPS})
        rc, out = check(root)
        self.assertEqual(rc, 1, "a copy folder read through two helper steps passed: %r" % out)
        self.assertTrue(reader_named(out, "hooks/reads_two_steps.py"), "reads_two_steps.py was not flagged")

    def test_presence_check_of_the_copy_items_fails(self):
        for form, text in PRESENCE_FORMS:
            with self.subTest(form=form):
                rel = "hooks/presence_%s.py" % form
                root = tree("%s-%s" % (self._testMethodName, form), {rel: text})
                rc, out = check(root)
                self.assertEqual(rc, 1, "an os.path/listdir %s of the copy's items passed: %r" % (form, out))
                self.assertTrue(reader_named(out, rel), "%s was not flagged as a live reader" % rel)

    def test_second_function_named_like_the_allowed_one_fails(self):
        root = tree(self._testMethodName, {"hooks/feedback_guard.py": TWO_FILED})
        rc, out = check(root)
        other = next(i for i, line in enumerate(TWO_FILED.split("\n"), 1) if line.startswith("class Other"))
        self.assertEqual(rc, 1, "a second filed_numbers that reads the copy passed: %r" % out)
        numbers = reader_line_numbers(out, "hooks/feedback_guard.py")
        self.assertTrue(numbers and all(n > other for n in numbers),
                        "the second filed_numbers (after line %d) was not the flagged one, found %r" % (other, numbers))

    def test_layout_config_key_read_is_not_a_copy_reader(self):
        root = tree(self._testMethodName, {"lint/reads_layout.py": LAYOUT_READER})
        rc, out = check(root)
        self.assertEqual(rc, 0, "a read of the waiting-data key in lint/layout.json was flagged as a copy read: %r" % out)


ROUTED_DOCS = '''from export_page import docs_in

def items(layout, root):
    return docs_in(layout.path(root, "waiting-data"), "items")
'''

ROUTED_LOAD = '''import os

from export_page import load_json

def item(layout, root):
    return load_json(os.path.join(layout.path(root, "waiting-data"), "items", "1.json"))
'''

UNLISTED_DOCS = '\n\ndef peek_docs(folder):\n    return docs_in(folder, "items")\n'

UNLISTED_READ = '\n\ndef peek_read(folder):\n    return read_copy(folder, ["items"])\n'

GIT_HELPER_PARAM = '''import subprocess

def git_items(root, folder):
    return subprocess.run(["git", "-C", root, "grep", "-I", "-e", ".", "origin/main", "--", folder + "/items/"])

def caller(layout, root):
    return git_items(root, layout.path(root, "waiting-data"))
'''

ON_DISK_JOIN = '''import os

def item(root):
    with open(os.path.join(root, "waiting", "items", "1.json"), encoding="utf-8") as handle:
        return handle.read()
'''

ON_DISK_PATHLIB = '''from pathlib import Path

def item(root):
    return (Path(root) / "waiting" / "items" / "1.json").read_text(encoding="utf-8")
'''

ON_DISK_CONCAT = '''def item(root):
    with open(root + "/waiting/items/1.json", encoding="utf-8") as handle:
        return handle.read()
'''

ON_DISK_SHELL = (
    ("cat", "bin/on_disk_cat", "cat $ROOT/waiting/items/1.json"),
    ("quoted", "bin/on_disk_quoted", 'cat "$ROOT/waiting/items/1.json"'),
)

LOCK_WAIT = '''import os, sys

def take_lock(path):
    if os.path.exists(path):
        sys.stderr.write("waiting for lock\\n")
    with open(path, encoding="utf-8") as handle:
        return handle.read()
'''

TAINT_MODULE = '''import os

COPY = "waiting-data"

def read_item(layout, root):
    with open(os.path.join(layout.path(root, COPY), "items", "1.json"), encoding="utf-8") as handle:
        return handle.read()
'''

TAINT_SELF = '''import os

class Items:
    def __init__(self, layout, root):
        self.folder = layout.path(root, "waiting-data")

    def read(self, name):
        with open(os.path.join(self.folder, "items", name), encoding="utf-8") as handle:
            return handle.read()
'''

TAINT_CLOSURE = '''import os

def make_reader(layout, root):
    folder = layout.path(root, "waiting-data")

    def read_item(name):
        with open(os.path.join(folder, "items", name), encoding="utf-8") as handle:
            return handle.read()

    return read_item
'''

SHELL_LS_THEN_CAT = '#!/bin/sh\nls waiting-data/items\ncat notes.txt\n'

GIT_SHOW_OTHER_PATH = '''import subprocess

def doc_at_main(root):
    return subprocess.run(["git", "-C", root, "show", "origin/main:docs/x.md"], capture_output=True)
'''

OPEN_OTHER_ATTRIBUTE = '''class Notes:
    def __init__(self, other):
        self.other = other

    def read(self):
        with open(self.other, encoding="utf-8") as handle:
            return handle.read()
'''

JS_SLASHES_IN_STRING = ('const docs = "https://example.test/docs";\n'
                        'const text = fs.readFileSync(path.join(layout.path(root, "waiting-data"), "items", "1.json"));\n')

JSX_LONE_QUOTE_READER = ("const view = <p>Don't</p>;\n"
                         'const text = fs.readFileSync(path.join(layout.path(root, "waiting-data"), "items", "1.json"));\n')

JSX_LONE_QUOTE_MENTION = "const view = <p>Don't</p>;\n// the waiting-data folder is a backup\n"

SHELL_HASH_IN_STRING = '#!/bin/sh\necho "step #2 of the copy"\ncat $ROOT/waiting-data/items/1.json\n'

SHELL_HASH_LABEL = '#!/bin/sh\necho "#waiting-data is a label"\n'

SHELL_COMMENT_QUOTE = "#!/bin/sh\n# don't read the copy here\ncat $ROOT/waiting-data/items/1.json\n"

SHELL_DOUBLE_QUOTE_APOSTROPHE = '#!/bin/sh\necho "it\'s the copy"\ncat $ROOT/waiting-data/items/1.json\n'

SUMMARY = re.compile(r"^checked (\d+) source files?\b.*: 0 findings?$")


class ReaderRouteCases(unittest.TestCase):
    """A copy read reached through an import from export_page.py, a new export_page.py function, or a parameter."""

    def test_docs_in_imported_from_export_page_fails(self):
        root = tree(self._testMethodName, {"hooks/routed_docs.py": ROUTED_DOCS})
        rc, out = check(root)
        self.assertEqual(rc, 1, "docs_in of the copy, imported from export_page.py, passed: %r" % out)
        self.assertTrue(reader_named(out, "hooks/routed_docs.py"), "hooks/routed_docs.py was not flagged as a live reader")

    def test_load_json_imported_from_export_page_fails(self):
        root = tree(self._testMethodName, {"hooks/routed_load.py": ROUTED_LOAD})
        rc, out = check(root)
        self.assertEqual(rc, 1, "load_json of the copy, imported from export_page.py, passed: %r" % out)
        self.assertTrue(reader_named(out, "hooks/routed_load.py"), "hooks/routed_load.py was not flagged as a live reader")

    def test_unlisted_export_function_calling_docs_in_fails(self):
        self.assert_export_reader(UNLISTED_DOCS, "def peek_docs", "docs_in")

    def test_unlisted_export_function_calling_read_copy_fails(self):
        self.assert_export_reader(UNLISTED_READ, "def peek_read", "read_copy")

    def assert_export_reader(self, appended, marker, callee):
        with open(os.path.join(ROOT, *EXPORT.split("/")), encoding="utf-8") as handle:
            text = handle.read() + appended
        root = tree(self._testMethodName, {EXPORT: text})
        rc, out = check(root)
        at = next(i for i, line in enumerate(text.split("\n"), 1) if marker in line)
        self.assertEqual(rc, 1, "an unlisted export_page.py function that calls %s on a folder passed in passed: %r" % (callee, out))
        numbers = reader_line_numbers(out, EXPORT)
        self.assertTrue(any(at <= n <= at + 2 for n in numbers),
                        "%s in export_page.py (line %d) was not the flagged reader, found %r" % (marker, at, numbers))

    def test_git_helper_taking_the_folder_fails(self):
        root = tree(self._testMethodName, {"hooks/git_helper.py": GIT_HELPER_PARAM})
        rc, out = check(root)
        self.assertEqual(rc, 1, "a git helper that reads a folder passed in passed: %r" % out)
        self.assertTrue(reader_named(out, "hooks/git_helper.py"), "hooks/git_helper.py was not flagged as a live reader")


class OnDiskNameCases(unittest.TestCase):
    """The copy's on-disk folder is `waiting` (layout COPY_PATH), as well as its kind name `waiting-data`."""

    def test_on_disk_join_of_the_waiting_folder_fails(self):
        root = tree(self._testMethodName, {"hooks/on_disk_join.py": ON_DISK_JOIN})
        rc, out = check(root)
        self.assertEqual(rc, 1, "os.path.join of the waiting folder's items passed: %r" % out)
        self.assertTrue(reader_named(out, "hooks/on_disk_join.py"), "hooks/on_disk_join.py was not flagged as a live reader")

    def test_on_disk_pathlib_of_the_waiting_folder_fails(self):
        root = tree(self._testMethodName, {"hooks/on_disk_pathlib.py": ON_DISK_PATHLIB})
        rc, out = check(root)
        self.assertEqual(rc, 1, "a Path join of the waiting folder's items passed: %r" % out)
        self.assertTrue(reader_named(out, "hooks/on_disk_pathlib.py"), "hooks/on_disk_pathlib.py was not flagged as a live reader")

    def test_on_disk_concatenated_path_fails(self):
        root = tree(self._testMethodName, {"hooks/on_disk_concat.py": ON_DISK_CONCAT})
        rc, out = check(root)
        self.assertEqual(rc, 1, "a concatenated /waiting/ path into the copy's items passed: %r" % out)
        self.assertTrue(reader_named(out, "hooks/on_disk_concat.py"), "hooks/on_disk_concat.py was not flagged as a live reader")

    def test_on_disk_shell_read_fails(self):
        for form, rel, command in ON_DISK_SHELL:
            with self.subTest(form=form):
                root = tree("%s-%s" % (self._testMethodName, form), {rel: "#!/bin/sh\n" + command + "\n"})
                rc, out = check(root)
                self.assertEqual(rc, 1, "a shell %s of the waiting folder's items passed: %r" % (form, out))
                self.assertTrue(reader_named(out, rel), "%s was not flagged as a live reader" % rel)

    def test_lock_wait_message_is_not_the_copy(self):
        root = tree(self._testMethodName, {"hooks/lock_wait.py": LOCK_WAIT})
        rc, out = check(root)
        self.assertEqual(rc, 0, "a 'waiting for lock' message and a lock-file read were flagged as the copy: %r" % out)


class TaintCases(unittest.TestCase):
    """The copy reached through a module constant, an attribute or a closure, read in another scope."""

    def test_module_constant_naming_the_copy_then_read_fails(self):
        root = tree(self._testMethodName, {"hooks/taint_module.py": TAINT_MODULE})
        rc, out = check(root)
        self.assertEqual(rc, 1, "a module constant naming the copy, read in a function, passed: %r" % out)
        self.assertTrue(reader_named(out, "hooks/taint_module.py"), "hooks/taint_module.py was not flagged as a live reader")

    def test_attribute_set_in_one_method_and_read_in_another_fails(self):
        root = tree(self._testMethodName, {"hooks/taint_self.py": TAINT_SELF})
        rc, out = check(root)
        self.assertEqual(rc, 1, "self.folder set to the copy in one method, read in another, passed: %r" % out)
        self.assertTrue(reader_named(out, "hooks/taint_self.py"), "hooks/taint_self.py was not flagged as a live reader")

    def test_closure_over_the_copy_folder_fails(self):
        root = tree(self._testMethodName, {"hooks/taint_closure.py": TAINT_CLOSURE})
        rc, out = check(root)
        self.assertEqual(rc, 1, "a closure that reads the copy folder passed: %r" % out)
        self.assertTrue(reader_named(out, "hooks/taint_closure.py"), "hooks/taint_closure.py was not flagged as a live reader")


class FalseAlarmCases(unittest.TestCase):
    """Reads that are not the copy must not be flagged."""

    def test_shell_listing_of_the_copy_with_an_unrelated_cat_passes(self):
        root = tree(self._testMethodName, {"bin/notes_list": SHELL_LS_THEN_CAT})
        rc, out = check(root)
        self.assertEqual(rc, 0, "an unrelated cat of notes.txt beside a listing of the copy was flagged: %r" % out)

    def test_git_show_of_another_path_passes(self):
        root = tree(self._testMethodName, {"hooks/doc_at_main.py": GIT_SHOW_OTHER_PATH})
        rc, out = check(root)
        self.assertEqual(rc, 0, "git show of docs/x.md was flagged as a copy read: %r" % out)

    def test_open_of_an_attribute_in_a_class_without_the_copy_passes(self):
        root = tree(self._testMethodName, {"hooks/notes_reader.py": OPEN_OTHER_ATTRIBUTE})
        rc, out = check(root)
        self.assertEqual(rc, 0, "open(self.other) in a class that never names the copy was flagged: %r" % out)


class ScannerStringCases(unittest.TestCase):
    """Strings and comments are not code: a comment opener, a lone quote or a '#' in text must not crash the
    scan, flag text that is not a read, or hide a read that follows."""

    def test_double_slash_in_a_javascript_string_hides_no_reader(self):
        root = tree(self._testMethodName, {"skills/waiting-page/url_reader.mjs": JS_SLASHES_IN_STRING})
        rc, out = check(root)
        self.assertEqual(rc, 1, "a reader after '//' inside a string was not flagged: %r" % out)
        self.assertTrue(reader_named(out, "skills/waiting-page/url_reader.mjs"), "url_reader.mjs was not flagged")

    def test_jsx_lone_quote_does_not_hide_a_later_reader(self):
        root = tree(self._testMethodName, {"skills/waiting-page/jsx_reader.mjs": JSX_LONE_QUOTE_READER})
        rc, out = check(root)
        self.assertEqual(rc, 1, "a reader after a JSX lone quote was not flagged: %r" % out)
        self.assertTrue(reader_named(out, "skills/waiting-page/jsx_reader.mjs"), "jsx_reader.mjs was not flagged")

    def test_jsx_lone_quote_with_only_a_mention_passes(self):
        root = tree(self._testMethodName, {"skills/waiting-page/jsx_mention.mjs": JSX_LONE_QUOTE_MENTION})
        rc, out = check(root)
        self.assertEqual(rc, 0, "a JSX lone quote with only a mention of the copy was flagged: %r" % out)

    def test_shell_hash_in_a_string_hides_no_reader(self):
        root = tree(self._testMethodName, {"bin/hash_echo": SHELL_HASH_IN_STRING})
        rc, out = check(root)
        self.assertEqual(rc, 1, "a reader after '#' inside a shell string was not flagged: %r" % out)
        self.assertTrue(reader_named(out, "bin/hash_echo"), "bin/hash_echo was not flagged")

    def test_shell_hash_in_a_label_string_passes(self):
        root = tree(self._testMethodName, {"bin/hash_label": SHELL_HASH_LABEL})
        rc, out = check(root)
        self.assertEqual(rc, 0, "a '#waiting-data' label in a shell string was flagged: %r" % out)

    def test_shell_comment_with_a_lone_quote_hides_no_reader(self):
        root = tree(self._testMethodName, {"bin/comment_quote": SHELL_COMMENT_QUOTE})
        rc, out = check(root)
        self.assertEqual(rc, 1, "a reader after a shell comment with a lone quote was not flagged: %r" % out)
        self.assertTrue(reader_named(out, "bin/comment_quote"), "bin/comment_quote was not flagged")

    def test_shell_double_quoted_apostrophe_hides_no_reader(self):
        root = tree(self._testMethodName, {"bin/apostrophe_echo": SHELL_DOUBLE_QUOTE_APOSTROPHE})
        rc, out = check(root)
        self.assertEqual(rc, 1, "a reader after a double-quoted apostrophe was not flagged: %r" % out)
        self.assertTrue(reader_named(out, "bin/apostrophe_echo"), "bin/apostrophe_echo was not flagged")


SHELL_CONTINUED = '#!/bin/sh\ncat \\\n  $ROOT/waiting-data/items/1.json\n'

JS_WRAPPED = ('const text = fs.readFileSync(\n'
              '  path.join(layout.path(root, "waiting-data"), "items", "1.json"));\n')

PARSE_LINE = "    args = ap.parse_args(argv)\n"

PEEK_IN_MAIN = ('    ap.add_argument("--peek", metavar="DIR", help="print the items of a waiting folder")\n'
                '    args = ap.parse_args(argv)\n'
                '    if args.peek:\n'
                '        print(docs_in(args.peek, "items"))\n')


class ContinuedReadCases(unittest.TestCase):
    """A read wrapped over two lines is one statement: a shell line that ends in a backslash, or a JavaScript
    call that goes on past a line break."""

    def test_shell_read_continued_with_a_backslash_fails(self):
        root = tree(self._testMethodName, {"bin/split_cat": SHELL_CONTINUED})
        rc, out = check(root)
        self.assertEqual(rc, 1, "a shell read continued with a backslash passed: %r" % out)
        self.assertTrue(reader_named(out, "bin/split_cat"), "bin/split_cat was not flagged as a live reader")

    def test_javascript_call_wrapped_over_two_lines_fails(self):
        root = tree(self._testMethodName, {"skills/waiting-page/wrapped.mjs": JS_WRAPPED})
        rc, out = check(root)
        self.assertEqual(rc, 1, "a JavaScript read wrapped over two lines passed: %r" % out)
        self.assertTrue(reader_named(out, "skills/waiting-page/wrapped.mjs"), "wrapped.mjs was not flagged as a live reader")


class ExportFrontCases(unittest.TestCase):
    """export_page.py's main may call only the five mode entry functions (EXPORT_FRONT)."""

    def test_export_main_peek_option_reading_a_folder_fails(self):
        with open(os.path.join(ROOT, *EXPORT.split("/")), encoding="utf-8") as handle:
            real = handle.read()
        self.assertEqual(real.count(PARSE_LINE), 1, "scope: main's argument parse line is not unique in export_page.py")
        text = real.replace(PARSE_LINE, PEEK_IN_MAIN)
        root = tree(self._testMethodName, {EXPORT: text})
        rc, out = check(root)
        at = next(i for i, line in enumerate(text.split("\n"), 1) if "print(docs_in(args.peek" in line)
        self.assertEqual(rc, 1, "a --peek option in main that reads a folder passed in passed: %r" % out)
        numbers = reader_line_numbers(out, EXPORT)
        self.assertTrue(any(at - 1 <= n <= at + 1 for n in numbers),
                        "the --peek read in main (line %d) was not the flagged reader, found %r" % (at, numbers))


class ProseCases(unittest.TestCase):
    def test_prose_without_backup_names_all_three_files(self):
        root = tree(self._testMethodName, {
            SKILL: "The copy in git is the record.\n",
            COPIES: "The copy in git is the record.\n",
            EXPORT: '"""Export. The copy in git is the record."""\n',
        })
        rc, out = check(root)
        self.assertEqual(rc, 1, "prose with no backup passed: %r" % out)
        for rel in PROSE_FILES:
            self.assertIn(rel + ":", out, "%s does not call the copy a backup, and was not named" % rel)

    def test_backup_in_a_code_comment_is_not_the_export_docstring(self):
        root = tree(self._testMethodName, {
            EXPORT: '"""Export of the waiting page."""\n# the copy is a backup\n',
        })
        rc, out = check(root)
        self.assertEqual(rc, 1, "a backup word in a code comment satisfied the docstring rule: %r" % out)
        self.assertIn(EXPORT + ":", out, "export_page.py's docstring does not call the copy a backup, and was not named")

    def test_missing_prose_file_is_unknown_not_a_pass(self):
        root = tree(self._testMethodName, {COPIES: GOOD_PROSE[COPIES], EXPORT: GOOD_PROSE[EXPORT]}, prose=False)
        rc, out = check(root)
        self.assertEqual(rc, 2, "a tree with no SKILL.md was not unknown: rc %d, %r" % (rc, out))


class RealRepoCases(unittest.TestCase):
    def test_real_prose_calls_the_copy_a_backup(self):
        for rel in PROSE_FILES:
            with self.subTest(file=rel):
                path = os.path.join(ROOT, *rel.split("/"))
                self.assertTrue(os.path.isfile(path), "%s is not in the repo" % rel)
                with open(path, encoding="utf-8") as handle:
                    text = handle.read()
                if rel == EXPORT:
                    text = ast.get_docstring(ast.parse(text)) or ""
                self.assertTrue(BACKUP.search(text), "%s does not call the waiting copy a backup" % rel)

    def test_real_repo_has_no_live_reader(self):
        rc, out = check(ROOT)
        self.assertEqual(rc, 0, "the checker exited %d on the real tree: %r" % (rc, out))
        summary = [line for line in out.splitlines() if SUMMARY.match(line)]
        self.assertTrue(summary, "the checker printed no summary line for the real tree, so its run is not shown: %r" % out)
        self.assertGreater(int(SUMMARY.match(summary[0]).group(1)), 0, "the summary counts no source files: %r" % summary[0])
        self.assertEqual(reader_lines(out), [], "the real tree has a live reader of the copy folder: %r" % out)


if __name__ == "__main__":
    unittest.main()
