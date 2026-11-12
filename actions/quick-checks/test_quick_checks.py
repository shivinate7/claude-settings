#!/usr/bin/env python3
"""Cases for actions/quick-checks/quick_checks.py: the three quick checks of the starter CI for a repo with no CI.

    python3 actions/quick-checks/test_quick_checks.py

The script takes one mode and runs in the checkout root. `links`: each relative link in a markdown file resolves.
`scripts`: each Python and shell script parses. `json`: each JSON file parses. It exits 0 when every file of its kind
passes (no such file is a pass), 1 when a file fails, and names each failing file in its output. It fetches no URL.

One clean repo is built once. Each defect case copies it and adds one defect, committed, so each case reads one cause and
the other two modes pass the same tree. The traps (a link in a code fence, a `#` in a Python string, a `//` in a JSON
string, a lone quote in text, an external link) each sit in a small repo of their own and must pass. The empty and the
full-size repos are the P8 states. Conventional JSONC names (tsconfig*.json, jsconfig.json, .eslintrc.json,
devcontainer.json) may hold comments; every other .json may not, and the controls keep that gate.
Temp files: this run's folder (lint/_test_temp.py, decision test-temp-standard).
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "lint"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)

SCRIPT = os.path.join(HERE, "quick_checks.py")
MODES = ("links", "scripts", "json")
ENV = _test_git.apply(dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
                           GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t"))
RUN_FOLDER = None
PARENT = None  # the clean repo every defect case copies, made in setUpModule

CLEAN = {
    "README.md": "# Project\n\nSee [the guide](docs/guide.md) and [the notes](docs/notes/today.md).\n",
    "docs/guide.md": "# Guide\n\nBack to the [readme](../README.md).\n",
    "docs/notes/today.md": "# Today\n\nNothing yet.\n",
    "tools/tidy.py": "import sys\n\n\ndef main():\n    print(sys.argv)\n",
    "bin/run.sh": "#!/usr/bin/env bash\nset -eu\necho ok\n",
    "config/settings.json": '{"name": "widgets", "tags": ["a", "b"]}\n',
}


def setUpModule():
    global RUN_FOLDER, PARENT
    RUN_FOLDER = _test_temp.run_folder()
    PARENT = make_repo(CLEAN)


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, env=ENV, check=True, capture_output=True)


def write_files(root, files):
    for rel, text in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)


def commit_all(root):
    git(root, "add", "-A")
    git(root, "commit", "-q", "--allow-empty", "-m", "fixture")


def make_repo(files):
    """A committed git repo in this run's folder holding `files` (path -> text). -> its path."""
    root = tempfile.mkdtemp(dir=RUN_FOLDER)
    git(root, "init", "-q")
    write_files(root, files)
    commit_all(root)
    return root


def defect_repo(overrides):
    """A copy of the clean repo with `overrides` written over it and committed: one defect, one cause."""
    root = os.path.join(tempfile.mkdtemp(dir=RUN_FOLDER), "repo")
    shutil.copytree(PARENT, root)
    write_files(root, overrides)
    commit_all(root)
    return root


def check(root, mode):
    """-> (exit code, output) of one quick check, run in `root` as the action runs it."""
    r = subprocess.run([sys.executable, SCRIPT, mode], cwd=root, env=ENV, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


class QuickChecks(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(SCRIPT), "actions/quick-checks/quick_checks.py is missing: no quick check to run")

    def assert_passes(self, root, modes=MODES):
        for mode in modes:
            with self.subTest(mode=mode):
                rc, out = check(root, mode)
                self.assertEqual(rc, 0, "%s failed a repo that should pass (exit %d): %s" % (mode, rc, out))

    def assert_one_cause(self, root, mode, names):
        """`mode` exits 1 and its output names each of `names`; the other two modes pass the same tree."""
        rc, out = check(root, mode)
        self.assertEqual(rc, 1, "%s exited %d on a repo with one defect, want 1: %s" % (mode, rc, out))
        for name in names:
            self.assertIn(name, out, "%s does not name %r in its output: %s" % (mode, name, out))
        self.assert_passes(root, [m for m in MODES if m != mode])


class CleanRepos(QuickChecks):
    def test_the_clean_repo_passes_each_check(self):
        self.assert_passes(PARENT)

    def test_an_empty_repo_passes_each_check(self):
        self.assert_passes(make_repo({"README.md": "# Empty\n"}))

    def test_a_repo_of_many_nested_files_passes_each_check(self):
        # The full-size state: 60 pages in six folders, each linking to the next, the last back to the first.
        files = {}
        for i in range(60):
            nxt = (i + 1) % 60
            files["docs/part%d/page%d.md" % (i % 6, i)] = "# Page %d\n\n[next](../part%d/page%d.md)\n" % (i, nxt % 6, nxt)
        self.assert_passes(make_repo(files))


class Defects(QuickChecks):
    def test_a_broken_relative_link_fails_links_and_names_its_file(self):
        root = defect_repo({"docs/guide.md": "# Guide\n\nSee [gone](missing.md).\n"})
        self.assert_one_cause(root, "links", ["docs/guide.md", "missing.md"])

    def test_an_unparseable_python_script_fails_scripts_and_names_it(self):
        root = defect_repo({"tools/tidy.py": "def main(:\n    pass\n"})
        self.assert_one_cause(root, "scripts", ["tools/tidy.py"])

    def test_an_unparseable_shell_script_fails_scripts_and_names_it(self):
        # A missing `fi` is a parse error for bash -n and sh -n alike. A runtime-only error, such as `[ -n x ;`, passes both.
        root = defect_repo({"bin/run.sh": "#!/usr/bin/env bash\nif true; then\n  echo no\n"})
        self.assert_one_cause(root, "scripts", ["bin/run.sh"])

    def test_the_same_shell_script_with_its_fi_passes_each_check(self):
        # The control: the defect case's script with `fi` restored. Only the missing `fi` makes the defect case fail.
        self.assert_passes(defect_repo({"bin/run.sh": "#!/usr/bin/env bash\nif true; then\n  echo no\nfi\n"}))

    def test_bad_json_fails_json_and_names_its_file(self):
        root = defect_repo({"config/settings.json": '{"name": "widgets", "tags": ["a", "b",]}\n'})
        self.assert_one_cause(root, "json", ["config/settings.json"])


class Traps(QuickChecks):
    def test_a_link_inside_a_code_fence_is_not_a_link(self):
        self.assert_passes(make_repo({"README.md": "# A\n\n```\n[gone](missing.md)\n```\n"}), ["links"])

    def test_an_external_link_is_not_fetched(self):
        # example.invalid never resolves: a fetch would fail the check, so a pass proves no URL was read.
        self.assert_passes(make_repo({"README.md": "# A\n\nSee [the site](https://example.invalid/page).\n"}), ["links"])

    def test_a_hash_inside_a_python_string_is_not_a_comment(self):
        self.assert_passes(make_repo({"tools/quote.py": 'print("# not a comment")\n'}), ["scripts"])

    def test_a_double_slash_inside_a_json_string_is_text(self):
        self.assert_passes(make_repo({"config/url.json": '{"home": "https://example.invalid/x"}\n'}), ["json"])

    def test_a_lone_quote_in_markdown_is_text(self):
        self.assert_passes(make_repo({"docs/apostrophe.md": "Don't break a link here.\n"}))


JSONC = '// compiler options\n{\n  /* the strict set */\n  "strict": true\n}\n'


class FalseAlarms(QuickChecks):
    """Each case is a clean repo of one valid layout the checks must pass (a false alarm, when it fails)."""

    def test_a_tsconfig_with_line_and_block_comments_passes_each_check(self):
        self.assert_passes(make_repo({"tsconfig.json": JSONC}))

    def test_each_conventional_jsonc_name_with_comments_passes_json(self):
        for name in ("tsconfig.base.json", "jsconfig.json", ".eslintrc.json", "devcontainer.json"):
            with self.subTest(file=name):
                self.assert_passes(make_repo({name: JSONC}), ["json"])

    def test_a_comment_opener_inside_a_string_and_a_lone_quote_in_a_comment_are_text(self):
        text = '// don\'t edit by hand\n{"home": "https://example.invalid/x", "note": "/* not a comment */"}\n'
        self.assert_passes(make_repo({"tsconfig.json": text}), ["json"])

    def test_a_json_file_with_a_byte_order_mark_passes_json(self):
        self.assert_passes(make_repo({"config/bom.json": "﻿" + '{"name": "widgets"}\n'}), ["json"])

    def test_a_footnote_definition_is_not_a_link(self):
        self.assert_passes(make_repo({"README.md": "# A\n\nA claim.[^1]\n\n[^1]: See the RFC\n"}), ["links"])

    def test_a_link_target_with_balanced_parens_resolves(self):
        self.assert_passes(make_repo({"README.md": "# A\n\nSee [the note](foo_(bar).md).\n", "foo_(bar).md": "# Note\n"}), ["links"])

    def test_a_link_in_a_fence_indented_in_a_list_item_is_not_a_link(self):
        self.assert_passes(make_repo({"README.md": "# A\n\n- Run it:\n\n    ```\n    [gone](missing.md)\n    ```\n"}), ["links"])


class FalseAlarmControls(QuickChecks):
    """The gates the false-alarm fixes must keep: a non-conventional .json with comments, broken JSON in a JSONC name, and
    a broken reference definition still fail, each named."""

    def test_a_plain_json_file_with_comments_still_fails_json(self):
        root = defect_repo({"config/notes.json": '// a note\n{"name": "widgets"}\n'})
        self.assert_one_cause(root, "json", ["config/notes.json"])

    def test_broken_json_in_a_conventional_jsonc_file_still_fails_json(self):
        root = defect_repo({"tsconfig.json": '// options\n{"strict": }\n'})
        self.assert_one_cause(root, "json", ["tsconfig.json"])

    def test_a_broken_reference_definition_still_fails_links(self):
        root = defect_repo({"docs/guide.md": "# Guide\n\nSee [the rfc][rfc].\n\n[rfc]: missing.md\n"})
        self.assert_one_cause(root, "links", ["docs/guide.md", "missing.md"])


if __name__ == "__main__":
    unittest.main()
