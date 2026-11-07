#!/usr/bin/env python3
"""Cases for lint/check_lint_codes.py: one code, one home, judged against the base and the ref.

    python3 lint/test_check_lint_codes.py

A code has one home. An STE code is the first argument of `_rule(` in lint/ste_lint.py. A STALE code
is a row of the module docstring table in lint/stale_cites.py, a line matching `  STALE\\d{3}  `. A MAP
code is a `MAP<n>: () => {` key of the body in skills/plain-english-map/scripts/map-check.mjs.

Each case builds a temp git repo under this run's folder (lint/_test_temp.py). `main` is the ref,
`feature` is the branch, and the real script runs as `--base main --root <repo>`. Most fixtures hold
all three home files. The cases that name a missing home say so.
"""
import collections
import os
import re
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
from test_stale_cites import git_commands  # noqa: E402  the one home of the GIT_TRACE reader (lint/test_stale_cites.py)
from test_windows_split import CHECKS, run_commands  # noqa: E402  the one home of the checks.yml run reader
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


def map_module(keys, top=(), body=()):
    """A stand-in for skills/plain-english-map/scripts/map-check.mjs: one `MAP<n>: () => {` key per
    entry of the body object. `top` lines sit above the object; `body` lines sit inside it, after the keys."""
    lines = ['// The plain-English map checks. A stand-in for the body object.',
             'const cfg = { title: "stand-in" };', ''] + list(top)
    lines += ['export function bodies(files) {', '  return {']
    for key in keys:
        lines += ['    %s: () => {' % key, '      return true;', '    },', '']
    lines += list(body)
    lines += ['  };', '}', '']
    return "\n".join(lines)


def tree(stale=("STALE001", "STALE002"), ste=("STE001",), maps=("MAP1", "MAP2"),
         stale_note=(), stale_tail=(), stale_text=None, ste_top=(), map_top=(), map_body=()):
    """The three home files of one commit. Every fixture holds all three."""
    text = {} if stale_text is None else {"text": stale_text}
    return {STALE: stale_module(stale, stale_note, stale_tail, **text),
            STE: ste_module(ste, ste_top),
            MAP: map_module(maps, map_top, map_body)}


def rows(text, code):
    """How many table rows of `code` a stale_cites.py text holds, counted by the row form."""
    return text.count("\n  %s  " % code)


def step_block(text, name):
    """The text of the checks.yml step named `name`, from its `- name:` line up to the next step's. "" when none has it."""
    mark = "      - name: %s\n" % name
    start = text.find(mark)
    if start == -1:
        return ""
    end = text.find("\n      - name:", start + len(mark))
    return text[start:] if end == -1 else text[start:end]


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
            if text is None:  # a deletion: `git add -A` stages the path gone
                os.remove(path)
                continue
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

    def tool_dir(self, node=None):
        """A folder to be the whole PATH: a link to git, and a `node` file holding `node` when given."""
        bindir = tempfile.mkdtemp(prefix="lcu_bin_", dir=RUN_FOLDER)
        os.symlink(shutil.which("git"), os.path.join(bindir, "git"))
        if node is not None:
            shim = os.path.join(bindir, "node")
            with open(shim, "w", encoding="utf-8", newline="\n") as f:
                f.write(node)
            os.chmod(shim, 0o755)
        return bindir

    def check(self, *args, root=None, env=None):
        """Run the real script on the fixture. Returns (exit code, output). A missing module fails here."""
        self.assertTrue(os.path.isfile(MODULE), "module absent: lint/check_lint_codes.py")
        cmd = [sys.executable, MODULE, *args, "--root", root or self.tree]
        r = subprocess.run(cmd, cwd=self.tree, env=env, capture_output=True, text=True, encoding="utf-8",
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

    # A home the base tip holds is judged at HEAD: absent there is UNKNOWN, never no codes.

    def test_a_home_the_base_tip_holds_and_the_head_moved_away_is_unknown_and_names_it(self):
        ref = tree(stale=("STALE001", "STALE002", "STALE003"))  # main defines STALE003 after the branch point
        moved = stale_module(("STALE001", "STALE002", "STALE003"))  # the branch moves the home and adds the colliding row
        self.build(tree(), ref=ref, head={STALE: None, "elsewhere/stale_cites.py": moved})
        self.assertNotIn(STALE, self.git("ls-tree", "-r", "--name-only", "HEAD"), "fixture: the head still holds the home")
        self.assertIn(STALE, self.git("ls-tree", "-r", "--name-only", "main"), "fixture: main lacks the home")
        rc, out = self.check("--base", "main")
        self.assertEqual(rc, 2, "a home the base tip holds and HEAD lacks: exit %d, want 2\n%s" % (rc, out))
        self.assertIn("UNKNOWN", out, "the moved home is not named UNKNOWN\n%s" % out)
        self.assertIn(STALE, out, "the UNKNOWN line does not name the moved home\n%s" % out)

    def test_a_home_that_the_base_tip_and_the_head_both_lack_passes(self):
        self.build({STE: ste_module(("STE001",)), MAP: map_module(("MAP1",))},
                   head={"notes/lane.md": "# Lane\n\nNotes only.\n"})
        self.assertNotIn(STALE, self.git("ls-tree", "-r", "--name-only", "HEAD"), "fixture: a revision holds the stale home")
        self.assert_passes("a home that neither the base tip nor the head holds is not read as no codes")

    # The row form: a row has whitespace around its code, so any spacing is still a row.

    def test_a_stale_row_with_one_space_after_its_code_counts_as_a_row(self):
        self.build(tree(), head=tree(stale=("STALE001", "STALE002", "STALE003"), stale_note=["  STALE003 x"]))
        text = self.git("show", "HEAD:" + STALE)
        self.assertIn("\n  STALE003 x\n", text, "fixture: the one-space row is not in the docstring")
        self.assertEqual(rows(text, "STALE003"), 1, "fixture: one standard STALE003 row")
        self.assert_flags("STALE003", "a one-space STALE003 row beside a standard one is not counted as a second row")

    def test_a_stale_row_with_three_spaces_before_its_code_counts_as_a_row(self):
        self.build(tree(), head=tree(stale=("STALE001", "STALE002", "STALE003"), stale_note=["   STALE003  x"]))
        text = self.git("show", "HEAD:" + STALE)
        self.assertIn("\n   STALE003  x\n", text, "fixture: the three-space row is not in the docstring")
        self.assertEqual(rows(text, "STALE003"), 1, "fixture: one standard STALE003 row")
        self.assert_flags("STALE003", "a three-space STALE003 row beside a standard one is not counted as a second row")

    def test_a_stale_row_with_a_tab_before_its_code_counts_as_a_row(self):
        self.build(tree(), head=tree(stale=("STALE001", "STALE002", "STALE003"), stale_note=["\tSTALE003  x"]))
        text = self.git("show", "HEAD:" + STALE)
        self.assertIn("\n\tSTALE003  x\n", text, "fixture: the tab row is not in the docstring")
        self.assertEqual(rows(text, "STALE003"), 1, "fixture: one standard STALE003 row")
        self.assert_flags("STALE003", "a tab-led STALE003 row beside a standard one is not counted as a second row")

    # The collisions: a code the branch adds that the ref already defines.

    def test_branch_adds_a_stale_code_the_ref_defines_fails(self):
        # main defines STALE003 after the branch point; the branch adds its own STALE003 row.
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

    def test_a_duplicate_the_base_tip_already_holds_does_not_fail_a_branch_that_contains_it(self):
        # CI's merge ref: the branch holds main, and main already defines STALE004 twice.
        ref = tree(stale=("STALE001", "STALE002", "STALE004", "STALE004"))
        self.build(tree(), ref=ref, head={"notes/lane.md": "# Lane\n\nNotes only.\n"}, merge_ref=True)
        self.assertEqual(rows(self.git("show", "main:" + STALE), "STALE004"), 2, "fixture: main does not hold the duplicate")
        self.assertEqual(rows(self.git("show", "HEAD:" + STALE), "STALE004"), 2, "fixture: the branch does not hold the duplicate")
        self.assert_passes("a duplicate the base tip already holds fails a branch that holds it")

    def test_a_new_duplicate_fails_even_when_the_base_tip_holds_another(self):
        ref = tree(stale=("STALE001", "STALE002", "STALE004", "STALE004"))
        self.build(tree(), ref=ref, head=tree(stale=("STALE001", "STALE002", "STALE005", "STALE005")))
        self.assertEqual(rows(self.git("show", "main:" + STALE), "STALE005"), 0, "fixture: main already defines STALE005")
        self.assertEqual(rows(self.git("show", "HEAD:" + STALE), "STALE005"), 2, "fixture: the branch does not define STALE005 twice")
        self.assert_flags("STALE005", "a new duplicate in the branch is not flagged")

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

    # The MAP key forms: a key with no space after its colon, and the two method forms.

    def test_a_no_space_map_key_counts_as_a_definition(self):
        head = tree(maps=("MAP1", "MAP2"), map_body=["    MAP2:() => {", "      return true;", "    },"])
        self.build(tree(), head=head)
        self.assertEqual(self.git("show", "HEAD:" + MAP).count("MAP2:() => {"), 1, "fixture: the no-space key is not in the body")
        self.assert_flags("MAP2", "a no-space MAP2 key beside a standard one is not counted as a second definition")

    def test_an_async_map_method_counts_as_a_definition(self):
        self.build(tree(), ref=tree(maps=("MAP1", "MAP2", "MAP3")),
                   head=tree(maps=("MAP1", "MAP2"), map_body=["    async MAP3() {", "      return true;", "    },"]))
        self.assertEqual(self.git("show", "main:" + MAP).count("    MAP3: () => {"), 1, "fixture: main lacks MAP3")
        self.assertEqual(self.git("show", "HEAD:" + MAP).count("async MAP3() {"), 1, "fixture: the branch lacks the async method")
        self.assert_flags("MAP3", "an async MAP3 method the branch adds is not counted as the key main already defines")

    def test_a_plain_map_method_counts_as_a_definition(self):
        self.build(tree(), ref=tree(maps=("MAP1", "MAP2", "MAP4")),
                   head=tree(maps=("MAP1", "MAP2"), map_body=["    MAP4() {", "      return true;", "    },"]))
        self.assertEqual(self.git("show", "main:" + MAP).count("    MAP4: () => {"), 1, "fixture: main lacks MAP4")
        self.assertEqual(self.git("show", "HEAD:" + MAP).count("    MAP4() {"), 1, "fixture: the branch lacks the method")
        self.assert_flags("MAP4", "a MAP4 method the branch adds is not counted as the key main already defines")

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

    def test_a_missing_node_prints_unknown_and_exits_2_never_a_traceback(self):
        self.build(tree())
        bindir = self.tool_dir()  # PATH holds git only: the MAP scan has no node to start
        self.assertIsNone(shutil.which("node", path=bindir), "fixture: node is on the PATH")
        rc, out = self.check("--base", "main", env=dict(os.environ, PATH=bindir))
        self.assertEqual(rc, 2, "a missing node: exit %d, want 2\n%s" % (rc, out))
        self.assertIn("UNKNOWN", out, "a missing node is not named UNKNOWN\n%s" % out)
        self.assertNotIn("Traceback", out, "a missing node printed a traceback\n%s" % out)

    def test_a_failing_node_prints_unknown_and_exits_2(self):
        self.build(tree())
        bindir = self.tool_dir(node="#!/bin/sh\necho scan failed >&2\nexit 3\n")
        rc, out = self.check("--base", "main", env=dict(os.environ, PATH=bindir))
        self.assertEqual(rc, 2, "a failing node: exit %d, want 2\n%s" % (rc, out))
        self.assertIn("UNKNOWN", out, "a failing node is not named UNKNOWN\n%s" % out)
        self.assertNotIn("Traceback", out, "a failing node printed a traceback\n%s" % out)

    # The cost: one run starts the git processes it reads with and one node scan, and no other process.

    def test_one_run_starts_exactly_the_pinned_processes_on_a_fixture_with_three_homes(self):
        self.build(tree())
        folder = tempfile.mkdtemp(prefix="lcu_cost_", dir=RUN_FOLDER)
        trace = os.path.join(folder, "git-trace.txt")
        starts = os.path.join(folder, "node-starts.txt")
        real_node = shutil.which("node")
        self.assertTrue(real_node, "fixture: node is not on the PATH")
        bindir = self.tool_dir(node='#!/bin/sh\necho node >> "%s"\nexec "%s" "$@"\n' % (starts, real_node))
        env = dict(os.environ, GIT_TRACE=trace, PATH=bindir + os.pathsep + os.environ.get("PATH", ""))
        rc, out = self.check("--base", "main", env=env)
        self.assertEqual(rc, 0, out)
        subs = []
        for command in git_commands(trace):
            found = re.search(r"\b(rev-parse|merge-base|ls-tree|cat-file)\b", command)
            subs.append(found.group(1) if found else command)
        # Pinned: two rev-parse and one merge-base, then an ls-tree and a cat-file for each of the three homes at each of
        # the three revisions. The node scan runs once, for the MAP texts.
        self.assertEqual(collections.Counter(subs), collections.Counter({"rev-parse": 2, "merge-base": 1, "ls-tree": 9, "cat-file": 9}), subs)
        with open(starts, encoding="utf-8") as f:
            self.assertEqual(f.read().split(), ["node"], "the node scan did not start exactly once")


class CiStep(unittest.TestCase):
    def test_the_lint_code_step_passes_the_pr_head_sha_as_the_silent_undo_step_does(self):
        with open(CHECKS, encoding="utf-8") as handle:
            block = step_block(handle.read(), "Lint code check")
        self.assertTrue(block, "no step named Lint code check in checks.yml")
        commands = run_commands(block)
        self.assertTrue(any('--head "$HEAD_SHA"' in command for command in commands),
                        "the Lint code check step does not pass --head \"$HEAD_SHA\": %r" % commands)
        self.assertIn("HEAD_SHA: ${{ github.event.pull_request.head.sha }}", block,
                      "the Lint code check step does not set HEAD_SHA from the PR head")


if __name__ == "__main__":
    unittest.main()
