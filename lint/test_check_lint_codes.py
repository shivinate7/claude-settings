#!/usr/bin/env python3
"""Cases for lint/check_lint_codes.py: one code, one home, judged against the base and the ref.

    python3 lint/test_check_lint_codes.py

A code has one home. An STE code is the first argument of `_rule(` in lint/ste_lint.py. A STALE code
is a row of the module docstring table in lint/stale_cites.py, a line matching `  STALE\\d{3}  `. A MAP
code is a `MAP<n>: () => {` key of the body in skills/plain-english-map/scripts/map-check.mjs.

Each case builds a temp git repo under this run's folder (lint/_test_temp.py). `main` is the ref,
`feature` is the branch, and the real script runs as `--base main --root <repo>`. Every fixture holds
all three home files, so no case pins what a missing home file means.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
MODULE = os.environ.get("LINT_CODES_UNDER_TEST") or os.path.join(HERE, "check_lint_codes.py")
STALE = "lint/stale_cites.py"
STE = "lint/ste_lint.py"
MAP = "skills/plain-english-map/scripts/map-check.mjs"
RUN_FOLDER = None  # made in setUpModule, so an import leaks no folder


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


def real(rel):
    """The text of a home file as it stands in this checkout: today's main."""
    with open(os.path.join(ROOT, *rel.split("/")), encoding="utf-8") as f:
        return f.read()


def stale_module(codes, note=(), tail=(), text="the line names a path the range deleted."):
    """A stand-in for lint/stale_cites.py: one table row per code, and two reader classes that both set
    code STALE002, as the real file does. `note` lines sit in the docstring above the rows; `tail`
    lines follow the classes; `text` is the row text."""
    lines = ['#!/usr/bin/env python3',
             '"""The stale-prose merge check. Standard library only.', '',
             '    python3 lint/stale_cites.py --range <base>...<head>', '',
             'Refuses a range that leaves a tracked Markdown line naming a name the range removed.']
    lines += list(note)
    lines += ["  %s  %s" % (code, text) for code in codes]
    lines += ['"""', 'import re', '', '',
              'class StaleName:', '    """STALE002: a line that cites `file.py name`."""', '    code = "STALE002"', '', '',
              'class UnknownName:', '    """STALE002 unknown: a JavaScript name the range touched."""', '    code = "STALE002"', '']
    lines += list(tail)
    return "\n".join(lines) + "\n"


def ste_module(codes, top=()):
    """A stand-in for lint/ste_lint.py: one `_rule(` call per code, its code the first argument. `top`
    lines sit above the calls."""
    lines = ['#!/usr/bin/env python3', '"""The prose lint. Standard library only."""', '', 'RULES = {}', '', '',
             'def _rule(code, name, severity, tags, summary, detail):',
             '    RULES[code] = (code, name, severity, tags, summary, detail)', '', '']
    lines += list(top)
    for code in codes:
        lines += ['_rule(', '    "%s", "rule-%s", "error", "[5.1]",' % (code, code.lower()),
                  '    "The sentence is too long.",', '    "Shorten the sentence.",', ')', '']
    return "\n".join(lines) + "\n"


def map_module(keys, top=()):
    """A stand-in for skills/plain-english-map/scripts/map-check.mjs: one `MAP<n>: () => {` key per
    entry of the body object. `top` lines sit above the object."""
    lines = ['// The plain-English map checks. A stand-in for the body object.',
             'const cfg = { title: "stand-in" };', ''] + list(top)
    lines += ['export function bodies(files) {', '  return {']
    for key in keys:
        lines += ['    %s: () => {' % key, '      return true;', '    },', '']
    lines += ['  };', '}', '']
    return "\n".join(lines)


def tree(stale=("STALE001", "STALE002"), ste=("STE001",), maps=("MAP1", "MAP2"),
         stale_note=(), stale_tail=(), stale_text=None, ste_top=(), map_top=()):
    """The three home files of one commit. Every fixture holds all three."""
    text = {} if stale_text is None else {"text": stale_text}
    return {STALE: stale_module(stale, stale_note, stale_tail, **text),
            STE: ste_module(ste, ste_top),
            MAP: map_module(maps, map_top)}


def rows(text, code):
    """How many table rows of `code` a stale_cites.py text holds, counted by the row form."""
    return text.count("\n  %s  " % code)


class CheckLintCodesTests(unittest.TestCase):

    def setUp(self):
        self.tree = tempfile.mkdtemp(prefix="lcu_", dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.tree, True)

    # The git helper has the shape of lint/test_check_record_slugs.py. No shared git-fixture home exists
    # in lint/ or testing/, so the helper is per suite.
    def git(self, *args):
        return subprocess.run(["git", "-C", self.tree, "-c", "user.name=test", "-c", "user.email=test@example.com", *args],
                              check=True, capture_output=True, text=True).stdout

    def commit(self, files, message):
        for rel, text in files.items():
            path = os.path.join(self.tree, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def build(self, base, ref=None, head=None, merge_ref=False):
        """`main` holds `base`, then `ref` when given. `feature` branches from base and commits `head`.
        With `merge_ref`, feature then merges main in. The check runs on feature."""
        self.git("init", "-q")
        self.git("symbolic-ref", "HEAD", "refs/heads/main")
        self.commit(base, "base")
        self.git("checkout", "-q", "-b", "feature")
        if head is not None:
            self.commit(head, "head")
        self.git("checkout", "-q", "main")
        if ref is not None:
            self.commit(ref, "ref")
        self.git("checkout", "-q", "feature")
        if merge_ref:
            self.git("merge", "-q", "--no-edit", "main")

    def check(self, *args, root=None):
        """Run the real script on the fixture. Returns (exit code, output). A missing module fails here."""
        self.assertTrue(os.path.isfile(MODULE), "module absent: lint/check_lint_codes.py")
        cmd = [sys.executable, MODULE, *args, "--root", root or self.tree]
        r = subprocess.run(cmd, cwd=self.tree, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=120)
        return r.returncode, r.stdout + r.stderr

    def assert_passes(self, cause):
        rc, out = self.check("--base", "main")
        self.assertEqual(rc, 0, "%s: exit %d, want 0\n%s" % (cause, rc, out))

    def assert_flags(self, code, cause):
        rc, out = self.check("--base", "main")
        self.assertEqual(rc, 1, "%s: exit %d, want 1\n%s" % (cause, rc, out))
        self.assertIn(code, out, "%s: the failure does not name %s\n%s" % (cause, code, out))

    # Controls first: a red case means nothing if the clean cases fail.

    def test_today_main_passes_on_the_real_home_files(self):
        # The false-alarm case. STALE001, STALE002 and STALE005 each have one table row and one or two
        # `code =` lines in the real file, so a reader that counts `code =` lines as definitions fails here.
        self.build({STALE: real(STALE), STE: real(STE), MAP: real(MAP)})
        text = self.git("show", "HEAD:" + STALE)
        self.assertEqual(text.count('code = "STALE002"'), 2, "fixture: two readers set STALE002")
        self.assertEqual(rows(text, "STALE002"), 1, "fixture: one table row for STALE002")
        self.assert_passes("today's main is red: a code is counted twice in the real files")

    def test_stale002_read_by_two_classes_with_one_row_passes(self):
        self.build(tree())
        text = self.git("show", "HEAD:" + STALE)
        self.assertEqual(text.count('code = "STALE002"'), 2, "fixture: two readers set STALE002")
        self.assertEqual(rows(text, "STALE002"), 1, "fixture: one table row for STALE002")
        self.assert_passes("STALE002 set in two classes is counted as a second definition")

    def test_branch_adds_codes_the_ref_lacks_in_all_three_homes_passes(self):
        self.build(tree(),
                   ref=tree(stale=("STALE001", "STALE002", "STALE003")),
                   head=tree(stale=("STALE001", "STALE002", "STALE006"), ste=("STE001", "STE002"),
                             maps=("MAP1", "MAP2", "MAP3")))
        self.assertEqual(rows(self.git("show", "main:" + STALE), "STALE003"), 1, "fixture: main lacks its STALE003 row")
        self.assert_passes("a code the ref lacks is flagged as a collision")

    def test_branch_that_merged_ref_in_passes(self):
        ref = tree(stale=("STALE001", "STALE002", "STALE003"), ste=("STE001", "STE002"),
                   maps=("MAP1", "MAP2", "MAP3"))
        self.build(tree(), ref=ref, head={"notes/lane.md": "# Lane\n\nNotes only.\n"}, merge_ref=True)
        self.assertEqual(rows(self.git("show", "HEAD:" + STALE), "STALE003"), 1, "fixture: the merge did not bring STALE003 in")
        self.assertEqual(len(self.git("rev-list", "--parents", "-n", "1", "HEAD").split()), 3, "fixture: HEAD is not a merge commit")
        self.assert_passes("a code the merge brought in from the ref is flagged as the branch's own")

    def test_empty_homes_then_first_codes_pass(self):
        self.build(tree(stale=(), ste=(), maps=()),
                   head=tree(stale=("STALE001",), ste=("STE001",), maps=("MAP1",)))
        self.assertNotIn("MAP1: () =>", self.git("show", "main:" + MAP), "fixture: main already has a MAP key")
        self.assert_passes("the first code in an empty home is flagged as a collision")

    def test_map_line_inside_a_template_literal_is_not_a_key_passes(self):
        self.build(tree(map_top=["const SAMPLE = `", "    MAP2: () => {", "`;"]))
        self.assertEqual(self.git("show", "HEAD:" + MAP).count("    MAP2: () => {"), 2,
                         "fixture: the template line and the real key are not both in the file")
        self.assert_passes("a MAP line inside a template literal is counted as a second key")

    def test_rule_call_text_in_a_comment_or_string_is_not_a_call_passes(self):
        top = ['# _rule("STE001", "old name", "error", "[5.1]", "Old.", "Old.")',
               "# Don't add a second call for one code.",
               'EXAMPLE = "_rule(\\"STE001\\")"']
        self.build(tree(ste_top=top))
        text = self.git("show", "HEAD:" + STE)
        self.assertIn('# _rule("STE001"', text, "fixture: the comment is not in the file")
        self.assertIn('EXAMPLE = "_rule(', text, "fixture: the string is not in the file")
        self.assert_passes("_rule( text in a comment or a string is counted as a call")

    def test_row_text_in_a_string_or_a_function_docstring_is_not_a_row_passes(self):
        tail = ['SAMPLE = """', "  STALE003  a sample line inside a string, not a table row.", '"""', '',
                'def sample():', '    """Doc.', '', "  STALE003  a row-shaped line in a function docstring.",
                '    """', '    return SAMPLE', '']
        self.build(tree(stale=("STALE001", "STALE002", "STALE003"), stale_tail=tail))
        self.assertEqual(rows(self.git("show", "HEAD:" + STALE), "STALE003"), 3,
                         "fixture: the string and function lines are not both in the file")
        self.assert_passes("row-shaped text outside the module docstring is counted as a row")

    def test_prose_naming_codes_in_the_docstring_is_not_a_row_passes(self):
        note = ["Left out: a line marked `<!-- ste-disable-line STALE001 -->` (or STALE002, STALE003, STALE004)."]
        self.build(tree(stale_note=note), head=tree(stale=("STALE001", "STALE002", "STALE006"), stale_note=note))
        self.assertIn("(or STALE002, STALE003, STALE004)", self.git("show", "HEAD:" + STALE),
                      "fixture: the prose line is not in the docstring")
        self.assert_passes("codes named in docstring prose are counted as table rows")

    # The collisions: a code the branch adds that the ref already defines.

    def test_branch_adds_a_stale_code_the_ref_defines_fails(self):
        # The lane that added STALE003 for stale flags, after main had taken it for the dead-path check.
        self.build(tree(), ref=tree(stale=("STALE001", "STALE002", "STALE003")),
                   head=tree(stale=("STALE001", "STALE002", "STALE003")))
        self.assertEqual(rows(self.git("show", "HEAD~1:" + STALE), "STALE003"), 0, "fixture: the base already has STALE003")
        self.assertEqual(rows(self.git("show", "main:" + STALE), "STALE003"), 1, "fixture: main lacks STALE003")
        self.assertEqual(rows(self.git("show", "HEAD:" + STALE), "STALE003"), 1, "fixture: the branch lacks STALE003")
        self.assert_flags("STALE003", "STALE003 that main defines is added again by the branch")

    def test_ste_code_the_ref_defines_and_the_branch_adds_fails(self):
        self.build(tree(), ref=tree(ste=("STE001", "STE002")), head=tree(ste=("STE001", "STE002")))
        self.assertEqual(self.git("show", "HEAD~1:" + STE).count('"STE002"'), 0, "fixture: the base already has STE002")
        self.assertEqual(self.git("show", "main:" + STE).count('"STE002"'), 1, "fixture: main lacks STE002")
        self.assert_flags("STE002", "STE002 that main defines is added again by the branch")

    def test_map_code_the_ref_defines_and_the_branch_adds_fails(self):
        self.build(tree(), ref=tree(maps=("MAP1", "MAP2", "MAP3")), head=tree(maps=("MAP1", "MAP2", "MAP3")))
        self.assertEqual(self.git("show", "HEAD~1:" + MAP).count("    MAP3: () => {"), 0, "fixture: the base already has MAP3")
        self.assertEqual(self.git("show", "main:" + MAP).count("    MAP3: () => {"), 1, "fixture: main lacks MAP3")
        self.assert_flags("MAP3", "MAP3 that main defines is added again by the branch")

    # One tree that defines a code twice.

    def test_stale_row_twice_in_one_tree_fails(self):
        self.build(tree(), head=tree(stale=("STALE001", "STALE002", "STALE004", "STALE004")))
        self.assertEqual(rows(self.git("show", "HEAD:" + STALE), "STALE004"), 2, "fixture: STALE004 is not twice in the table")
        self.assert_flags("STALE004", "two table rows for STALE004 in one tree are not flagged")

    def test_rule_called_twice_in_one_tree_fails(self):
        self.build(tree(), head=tree(ste=("STE001", "STE002", "STE002")))
        self.assertEqual(self.git("show", "HEAD:" + STE).count('"STE002"'), 2, "fixture: STE002 is not in two calls")
        self.assert_flags("STE002", "two _rule calls for STE002 in one tree are not flagged")

    def test_map_key_defined_twice_in_one_tree_fails(self):
        self.build(tree(), head=tree(maps=("MAP1", "MAP2", "MAP3", "MAP3")))
        self.assertEqual(self.git("show", "HEAD:" + MAP).count("    MAP3: () => {"), 2, "fixture: MAP3 is not twice in the body")
        self.assert_flags("MAP3", "two MAP3 keys in one body are not flagged")

    def test_full_size_table_with_a_duplicate_at_the_end_fails(self):
        full = ["STE%03d" % n for n in range(1, 61)]
        self.build(tree(ste=full), head=tree(ste=full + ["STE060"]))
        self.assertEqual(self.git("show", "HEAD:" + STE).count('"rule-ste060"'), 2, "fixture: STE060 is not in two calls")
        self.assert_flags("STE060", "a second _rule call for STE060 at the end of a full table is not flagged")

    # The scanner traps: a text reader of a home must not stop at a quote, an opener or a template.

    def test_lone_quote_in_the_docstring_does_not_hide_a_stale_row_fails(self):
        note = ["  Don't count a second row for one code as a new code."]
        self.build(tree(), head=tree(stale=("STALE001", "STALE002", "STALE003", "STALE003"), stale_note=note))
        text = self.git("show", "HEAD:" + STALE)
        self.assertLess(text.index("Don't"), text.index("\n  STALE003  "), "fixture: the quote is not above the rows")
        self.assert_flags("STALE003", "a lone quote in the docstring hides a second STALE003 row")

    def test_comment_openers_in_a_string_do_not_hide_a_map_key_fails(self):
        opener = 'const NOTE = "/* not a comment, // nor this, # or this";'
        self.build(tree(), head=tree(maps=("MAP1", "MAP2", "MAP1"), map_top=[opener]))
        self.assertIn(opener, self.git("show", "HEAD:" + MAP), "fixture: the openers are not in the file")
        self.assertEqual(self.git("show", "HEAD:" + MAP).count("    MAP1: () => {"), 2, "fixture: MAP1 is not twice in the body")
        self.assert_flags("MAP1", "comment openers inside a string hide a second MAP1 key")

    def test_comment_openers_in_a_docstring_row_do_not_hide_a_second_row_fails(self):
        text = 'the line names "#", "//" and "/*" in a path.'
        self.build(tree(), head=tree(stale=("STALE001", "STALE002", "STALE003", "STALE003"), stale_text=text))
        self.assertIn('"/*"', self.git("show", "HEAD:" + STALE), "fixture: the openers are not in the rows")
        self.assertEqual(rows(self.git("show", "HEAD:" + STALE), "STALE003"), 2, "fixture: STALE003 is not twice in the table")
        self.assert_flags("STALE003", "comment openers inside a docstring row hide a second STALE003 row")

    def test_lone_quote_in_a_comment_does_not_hide_a_map_key_added_to_ref_fails(self):
        top = ["// the check's body reads each key once."]
        self.build(tree(), ref=tree(maps=("MAP1", "MAP2", "MAP3"), map_top=top),
                   head=tree(maps=("MAP1", "MAP2", "MAP3"), map_top=top))
        ref_text = self.git("show", "main:" + MAP)
        self.assertLess(ref_text.index("check's"), ref_text.index("    MAP3: () => {"), "fixture: the quote is not above MAP3")
        self.assert_flags("MAP3", "a lone quote in a comment hides MAP3 on the ref")

    # The exit-2 cases: a git read that fails is UNKNOWN, never 0.

    def test_unknown_base_ref_exits_2_with_unknown(self):
        self.build(tree())
        rc, out = self.check("--base", "no-such-ref")
        self.assertEqual(rc, 2, "unknown base ref: exit %d, want 2\n%s" % (rc, out))
        self.assertIn("UNKNOWN", out, "unknown base ref is not named UNKNOWN\n%s" % out)

    def test_root_that_is_not_a_git_repo_exits_2_with_unknown(self):
        plain = tempfile.mkdtemp(prefix="lcu_plain_", dir=RUN_FOLDER)
        self.assertNotEqual(subprocess.run(["git", "-C", plain, "rev-parse", "--git-dir"], capture_output=True).returncode, 0,
                            "fixture: the plain folder is inside a git repo")
        self.build(tree())
        rc, out = self.check("--base", "main", root=plain)
        self.assertEqual(rc, 2, "a root that is not a repo: exit %d, want 2\n%s" % (rc, out))
        self.assertIn("UNKNOWN", out, "a root that is not a repo is not named UNKNOWN\n%s" % out)

    def test_unreadable_base_blob_exits_2_with_unknown(self):
        self.build(tree(), head=tree(ste=("STE001", "STE002")))
        blob = self.git("rev-parse", "main:" + STE).strip()
        loose = os.path.join(self.tree, ".git", "objects", blob[:2], blob[2:])
        self.assertTrue(os.path.isfile(loose), "fixture: the base blob is not a loose object, so it cannot be removed")
        os.remove(loose)
        self.assertNotEqual(subprocess.run(["git", "-C", self.tree, "cat-file", "-e", blob], capture_output=True).returncode, 0,
                            "fixture: the base blob still reads")
        rc, out = self.check("--base", "main")
        self.assertEqual(rc, 2, "an unreadable base blob: exit %d, want 2\n%s" % (rc, out))
        self.assertIn("UNKNOWN", out, "an unreadable base blob is not named UNKNOWN\n%s" % out)


if __name__ == "__main__":
    unittest.main()
