#!/usr/bin/env python3
"""Cases for lint/check_standin_signatures.py. Standard library only.

    python3 lint/test_standin_signatures.py

A test stand-in replaces a product function on the product module. The product calls that function with
keyword and positional arguments. A stand-in that lacks a keyword the product passes raises TypeError when
the test runs, and so does one that takes fewer positional arguments than the product passes. The check
reads both files with the ast module: it never imports them and never runs a test.

The interface these cases pin:
- check_standins(product_path, test_paths) returns (findings, not_judged). Each finding is a dict with the keys
  file (the test path as given), line (the first line of the patch call), name (the product function, such as
  sh), standin (the stand-in's name, or None for a lambda or a call made inline), keyword (the missing keyword,
  or None) and kind ("keyword" or "positional"). not_judged counts the stand-ins the check cannot resolve.
- python3 lint/check_standin_signatures.py [--root DIR] scans DIR, which defaults to the checkout. It pairs each
  test_X.py with X.py in the same folder, prints one line per finding that names the test file and its line,
  prints one "N stand-ins not judged" line when N is more than 0, and exits 1 on any finding, else 0.

Each case writes its fixtures under this run's folder (test-temp-standard, lint/_test_temp.py). The sweep of
old run folders is proved in lint/test_find_copies.py. Until the check exists, every case except ControlTests
fails at an assert that names the behaviour it wants. ControlTests passes on the old commit: it shows that the
fixtures copy the real merge tool's shapes, so a failure comes from the check and not from a fixture.
"""
import ast
import importlib.util
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

CHECK_REL = "lint/check_standin_signatures.py"
CHECK = os.path.join(ROOT, "lint", "check_standin_signatures.py")
REAL_PRODUCT = os.path.join(ROOT, "merge", "merge.py")
REAL_TESTS = os.path.join(ROOT, "merge", "test_merge.py")
SITES = 60
BAD_SITE = 37
RUN_FOLDER = None  # made in setUpModule, so an import leaks no folder


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


# The product: sh() with the parameters of sh() in merge/merge.py, and a keyword that one call passes.
PRODUCT_STDOUT = '''"""The merge tool's shell runner, with the parameters of sh() in merge/merge.py."""
import subprocess


def sh(args, cwd=None, input=None, env=None, timeout=None, live_stderr=False, raw=False, stdout_only=False):
    out = subprocess.run(args, cwd=cwd, input=input, env=env, capture_output=True, text=True)
    return out.returncode, (out.stdout if stdout_only else out.stdout + out.stderr)


def head(root):
    return sh(["git", "rev-parse", "HEAD"], cwd=root, stdout_only=True)
'''

# The product: one keyword, passed by one call.
PRODUCT_KW = '''"""A product whose only keyword call passes stdout_only."""
def sh(args, cwd=None, stdout_only=False):
    return 0, ""


def status(root):
    return sh(["git", "status"], stdout_only=True)
'''

PRODUCT_EMPTY = '''"""A product that calls sh() nowhere."""
def sh(args, cwd=None):
    return 0, ""
'''

# A stand-in for sh() that lacks stdout_only, which PRODUCT_STDOUT passes.
BROKEN_DEF = "def fake_sh(args, cwd=None, input=None, env=None):"
KWARGS_DEF = "def fake_sh(args, cwd=None, input=None, env=None, **kwargs):"
KEYWORD_DEF = "def fake_sh(args, cwd=None, input=None, env=None, stdout_only=False):"

SINGLE_PATCH = '''import unittest
import unittest.mock

import merge


__STANDIN__
    return 0, ""


class SingleTests(unittest.TestCase):
    def test_call(self):
        with unittest.mock.patch.object(merge, "sh", fake_sh):
            pass
'''


def single_patch(def_line):
    return SINGLE_PATCH.replace("__STANDIN__", def_line)


def require_check(case, want):
    if not os.path.isfile(CHECK):
        case.fail("want: %s. %s does not exist yet (not built), so there is no check to return findings"
                  % (want, CHECK_REL))


def load_check(case, want):
    require_check(case, want)
    spec = importlib.util.spec_from_file_location("check_standin_signatures", CHECK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def case_folder(case, variant):
    return os.path.join(RUN_FOLDER, case.id().rsplit(".", 1)[-1], variant)


def write(folder, rel, text):
    path = os.path.join(folder, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return path


def judge(case, want, variant, product_text, tests):
    """Write the product (merge.py) and the test files under this case's variant folder, then call check_standins."""
    module = load_check(case, want)
    folder = case_folder(case, variant)
    product = write(folder, "merge.py", product_text)
    paths = [write(folder, name, text) for name, text in sorted(tests.items())]
    return module.check_standins(product, paths)


def run_cli(case, want, variant, files):
    require_check(case, want)
    folder = case_folder(case, variant)
    for name, text in files.items():
        write(folder, name, text)
    return subprocess.run([sys.executable, CHECK, "--root", folder], cwd=folder,
                          capture_output=True, text=True, timeout=120)


def line_of(text, marker):
    hits = [n for n, line in enumerate(text.split("\n"), 1) if marker in line]
    assert len(hits) == 1, "fixture marker %r must sit on exactly one line, found lines %s" % (marker, hits)
    return hits[0]


def patch_line_after(text, marker):
    """The line of the first patch.object( call at or below the line that holds marker (a case's own def)."""
    lines = text.split("\n")
    for n in range(line_of(text, marker) - 1, len(lines)):
        if "patch.object(" in lines[n]:
            return n + 1
    raise AssertionError("fixture has no patch.object( call after the line holding %r" % marker)


def where(findings):
    return sorted((os.path.basename(f["file"]), f["line"]) for f in findings)


def defs_named(tree, name):
    return [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == name]


def params(fn):
    return [a.arg for a in fn.args.args + fn.args.kwonlyargs]


def keyword_names(text):
    return {kw.arg for node in ast.walk(ast.parse(text)) if isinstance(node, ast.Call) for kw in node.keywords}


class ControlTests(unittest.TestCase):
    def test_fixtures_copy_the_real_merge_tool_shapes(self):
        with open(REAL_PRODUCT, encoding="utf-8") as f:
            real_sh = defs_named(ast.parse(f.read()), "sh")
        self.assertTrue(real_sh, "merge/merge.py has no def sh, so the fixture product shape has no source")
        fixture_sh = defs_named(ast.parse(PRODUCT_STDOUT), "sh")[0]
        self.assertEqual(params(fixture_sh)[:4], params(real_sh[0])[:4],
                         "the fixture sh must take merge/merge.py's first four parameters, in order")
        with open(REAL_TESTS, encoding="utf-8") as f:
            real_stubs = [params(fn)[:4] for fn in defs_named(ast.parse(f.read()), "fake_sh")]
        stand_in = defs_named(ast.parse(single_patch(BROKEN_DEF)), "fake_sh")[0]
        self.assertIn(params(stand_in)[:4], real_stubs,
                      "the fixture stand-in should take the same four parameters as a fake_sh in merge/test_merge.py")
        self.assertIn("stdout_only", keyword_names(PRODUCT_STDOUT),
                      "the fixture product must pass stdout_only= at a call site, as head() does")
        self.assertNotIn("stdout_only", params(stand_in),
                         "the fixture stand-in must lack stdout_only, the keyword the product passes")


class KeywordTests(unittest.TestCase):
    def test_a_stand_in_without_a_passed_keyword_is_one_finding(self):
        text = single_patch(BROKEN_DEF)
        findings, not_judged = judge(
            self, "one finding at the patch line of fake_sh, which lacks stdout_only, a keyword the sh() call in head() passes",
            "broken", PRODUCT_STDOUT, {"test_merge.py": text})
        line = patch_line_after(text, "def test_call")
        self.assertEqual(where(findings), [("test_merge.py", line)],
                         "want one finding at the patch line of fake_sh, which lacks stdout_only that head() passes")
        self.assertEqual(not_judged, 0, "want a plain def stand-in judged, not counted as not judged")
        finding = findings[0]
        self.assertEqual((finding["name"], finding["standin"], finding["keyword"], finding["kind"]),
                         ("sh", "fake_sh", "stdout_only", "keyword"),
                         "want the finding to name sh, fake_sh, the missing keyword stdout_only, and kind keyword")

    def test_kwargs_twin_is_clean_once_the_broken_one_is_flagged(self):
        want = "a stand-in with **kwargs takes any keyword, so no finding"
        text = single_patch(BROKEN_DEF)
        broken, _ = judge(self, want, "broken", PRODUCT_STDOUT, {"test_merge.py": text})
        self.assertEqual(where(broken), [("test_merge.py", patch_line_after(text, "def test_call"))],
                         "want the broken twin flagged first, so a check that reports nothing cannot pass the clean twin")
        fixed, _ = judge(self, want, "kwargs", PRODUCT_STDOUT, {"test_merge.py": single_patch(KWARGS_DEF)})
        self.assertEqual(where(fixed), [], "want no finding for a fake_sh with **kwargs, which takes stdout_only")

    def test_keyword_added_twin_is_clean_once_the_broken_one_is_flagged(self):
        want = "a stand-in that adds stdout_only as a parameter is clean"
        text = single_patch(BROKEN_DEF)
        broken, _ = judge(self, want, "broken", PRODUCT_STDOUT, {"test_merge.py": text})
        self.assertEqual(where(broken), [("test_merge.py", patch_line_after(text, "def test_call"))],
                         "want the broken twin flagged first, so a check that reports nothing cannot pass the clean twin")
        fixed, _ = judge(self, want, "keyword", PRODUCT_STDOUT, {"test_merge.py": single_patch(KEYWORD_DEF)})
        self.assertEqual(where(fixed), [], "want no finding once fake_sh takes stdout_only=False")

    def test_keyword_passed_only_from_a_nested_scope_is_collected(self):
        want = "the keyword in a call inside a nested function and a method is collected"
        product = '''"""A product that passes stdout_only only from a nested function inside a method."""
def sh(args, cwd=None, stdout_only=False):
    return 0, ""


class Runner:
    def run(self, root):
        def inner():
            return sh(["git", "status"], stdout_only=True)

        return inner()
'''
        text = single_patch("def fake_sh(args, cwd=None):")
        broken, _ = judge(self, want, "broken", product, {"test_merge.py": text})
        self.assertEqual(where(broken), [("test_merge.py", patch_line_after(text, "def test_call"))],
                         "want one finding: the keyword passed inside a nested scope is a keyword the product passes")
        fixed, _ = judge(self, want, "fixed", product,
                         {"test_merge.py": single_patch("def fake_sh(args, cwd=None, stdout_only=False):")})
        self.assertEqual(where(fixed), [], "want no finding once the stand-in takes stdout_only")

    def test_keyword_text_in_a_product_string_or_comment_is_not_a_call(self):
        want = "stdout_only in a string or a comment is not a keyword the product passes"
        prose = '''"""Notes: a caller writes sh(["git"], stdout_only=True) in prose."""
def sh(args, cwd=None, stdout_only=False):
    return 0, ""


def status(root):
    # sh(["git", "status"], stdout_only=True)
    note = "sh(['git', 'status'], stdout_only=True)"
    return sh(["git", "status"], root), note
'''
        real = '''"""A product that passes stdout_only in a real call."""
def sh(args, cwd=None, stdout_only=False):
    return 0, ""


def status(root):
    return sh(["git", "status"], stdout_only=True)
'''
        text = single_patch("def fake_sh(args, cwd=None):")
        flagged, _ = judge(self, want, "real", real, {"test_merge.py": text})
        self.assertEqual(where(flagged), [("test_merge.py", patch_line_after(text, "def test_call"))],
                         "want one finding from the real call, so the text variant below can be read against it")
        clean, _ = judge(self, want, "text", prose, {"test_merge.py": text})
        self.assertEqual(where(clean), [], "want no finding: a keyword named only in a string or comment is not passed")

    def test_a_keyword_no_product_call_passes_is_not_a_finding(self):
        want = "a keyword that no product call passes is not flagged; a keyword a call passes is flagged"
        product = '''"""A product whose stdout_only is never passed, and whose cwd is passed."""
def sh(args, cwd=None, stdout_only=False):
    return 0, ""


def status(root):
    return sh(["git", "status"], cwd=root)
'''
        tests = '''import unittest
import unittest.mock

import merge


def fake_plain(args):
    return 0, ""


def fake_sh(args, cwd=None):
    return 0, ""


class NoCallTests(unittest.TestCase):
    def test_lacks_cwd(self):
        with unittest.mock.patch.object(merge, "sh", fake_plain):
            pass

    def test_lacks_stdout_only_no_call_passes(self):
        with unittest.mock.patch.object(merge, "sh", fake_sh):
            pass
'''
        findings, _ = judge(self, want, "mixed", product, {"test_merge.py": tests})
        self.assertEqual(where(findings), [("test_merge.py", patch_line_after(tests, "def test_lacks_cwd"))],
                         "want one finding, for fake_plain lacking cwd; fake_sh lacks stdout_only, which no call passes")
        self.assertEqual([(f["standin"], f["keyword"]) for f in findings], [("fake_plain", "cwd")],
                         "want the finding to name fake_plain and the keyword cwd, and no finding for stdout_only")


class PositionalTests(unittest.TestCase):
    def test_too_few_positional_parameters_is_flagged_by_the_largest_call(self):
        want = "a stand-in with fewer positional parameters than the largest product call passes is flagged"
        product = '''"""Calls with one, two and three positional arguments."""
def sh(args, cwd=None, input=None, stdout_only=False):
    return 0, ""


def first(root):
    return sh(["git"])


def second(root):
    return sh(["git", "log"], root, "input text")
'''
        tests = '''import unittest
import unittest.mock

import merge


def fake_one(args):
    return 0, ""


def fake_two(args, cwd=None):
    return 0, ""


def fake_three(args, cwd=None, input=None):
    return 0, ""


def fake_star(*args):
    return 0, ""


class PositionalTests(unittest.TestCase):
    def test_one(self):
        with unittest.mock.patch.object(merge, "sh", fake_one):
            pass

    def test_two(self):
        with unittest.mock.patch.object(merge, "sh", fake_two):
            pass

    def test_three(self):
        with unittest.mock.patch.object(merge, "sh", fake_three):
            pass

    def test_star(self):
        with unittest.mock.patch.object(merge, "sh", fake_star):
            pass
'''
        findings, _ = judge(self, want, "pos", product, {"test_merge.py": tests})
        self.assertEqual(where(findings), [("test_merge.py", patch_line_after(tests, "def test_one")),
                                           ("test_merge.py", patch_line_after(tests, "def test_two"))],
                         "want fake_one and fake_two flagged: each takes fewer positionals than the 3 the largest call passes")
        self.assertEqual(sorted((f["standin"], f["kind"]) for f in findings),
                         [("fake_one", "positional"), ("fake_two", "positional")],
                         "want kind positional for both, and no keyword finding: no call passes a keyword")


class JudgingTests(unittest.TestCase):
    def test_keyword_only_and_defaulted_parameters_that_match_are_clean(self):
        want = "a keyword-only or defaulted parameter that matches the passed keyword is clean"
        tests = '''import unittest
import unittest.mock

import merge


def fake_kwonly(args, cwd=None, *, stdout_only=False):
    return 0, ""


def fake_default(args, cwd=None, input=None, env=None, stdout_only=False):
    return 0, ""


def fake_bad(args, cwd=None, input=None, env=None):
    return 0, ""


class MatchTests(unittest.TestCase):
    def test_keyword_only(self):
        with unittest.mock.patch.object(merge, "sh", fake_kwonly):
            pass

    def test_defaulted(self):
        with unittest.mock.patch.object(merge, "sh", fake_default):
            pass

    def test_bad(self):
        with unittest.mock.patch.object(merge, "sh", fake_bad):
            pass
'''
        findings, _ = judge(self, want, "match", PRODUCT_STDOUT, {"test_merge.py": tests})
        self.assertEqual(where(findings), [("test_merge.py", patch_line_after(tests, "def test_bad"))],
                         "want only fake_bad flagged; fake_kwonly and fake_default accept stdout_only")

    def test_self_is_not_a_positional_slot_of_a_method_stand_in(self):
        want = "self is not counted: a method stand-in with one argument fewer than the product passes is flagged"
        product = '''"""A product whose sh() takes two positional arguments."""
def sh(args, cwd=None):
    return 0, ""


def head(root):
    return sh(["git", "rev-parse", "HEAD"], root)
'''
        tests = '''import unittest
import unittest.mock

import merge


class SelfTests(unittest.TestCase):
    def fake_short(self, args):
        return 0, ""

    def fake_full(self, args, cwd=None):
        return 0, ""

    def test_short(self):
        with unittest.mock.patch.object(merge, "sh", self.fake_short):
            pass

    def test_full(self):
        with unittest.mock.patch.object(merge, "sh", self.fake_full):
            pass
'''
        findings, _ = judge(self, want, "self", product, {"test_merge.py": tests})
        self.assertEqual(where(findings), [("test_merge.py", patch_line_after(tests, "def test_short"))],
                         "want fake_short flagged: bound, it takes args only, one fewer than the two the product passes")
        self.assertEqual([f["standin"] for f in findings], ["fake_short"],
                         "want the standin named fake_short; fake_full takes two positionals and is clean")

    def test_obj_dot_method_with_a_unique_def_is_judged(self):
        want = "a method reached through an instance, whose def is in the file, is judged"
        tests = '''import unittest
import unittest.mock

import merge


class Fake:
    def run_bad(self, args, cwd=None):
        return 0, ""


class Good:
    def run_ok(self, args, cwd=None, stdout_only=False):
        return 0, ""


class ObjTests(unittest.TestCase):
    def test_bad(self):
        fake = Fake()
        with unittest.mock.patch.object(merge, "sh", fake.run_bad):
            pass

    def test_ok(self):
        good = Good()
        with unittest.mock.patch.object(merge, "sh", good.run_ok):
            pass
'''
        findings, _ = judge(self, want, "obj", PRODUCT_STDOUT, {"test_merge.py": tests})
        self.assertEqual(where(findings), [("test_merge.py", patch_line_after(tests, "def test_bad"))],
                         "want run_bad flagged for stdout_only and run_ok clean")
        self.assertEqual([(f["standin"], f["keyword"]) for f in findings], [("run_bad", "stdout_only")],
                         "want the standin named run_bad and the keyword stdout_only")

    def test_callable_instance_stand_in_is_judged(self):
        want = "an inline instance of a class with __call__ is judged by __call__"
        tests = '''import unittest
import unittest.mock

import merge


class FakeSh:
    def __call__(self, args, cwd=None):
        return 0, ""


class GoodSh:
    def __call__(self, args, cwd=None, stdout_only=False):
        return 0, ""


class CallTests(unittest.TestCase):
    def test_bad(self):
        with unittest.mock.patch.object(merge, "sh", FakeSh()):
            pass

    def test_ok(self):
        with unittest.mock.patch.object(merge, "sh", GoodSh()):
            pass
'''
        findings, _ = judge(self, want, "call", PRODUCT_KW, {"test_merge.py": tests})
        self.assertEqual(where(findings), [("test_merge.py", patch_line_after(tests, "def test_bad"))],
                         "want FakeSh() flagged for the keyword stdout_only; GoodSh() takes it and is clean")
        self.assertEqual((findings[0]["name"], findings[0]["keyword"]), ("sh", "stdout_only"),
                         "want the finding to name sh and the keyword stdout_only")

    def test_lambda_stand_in_is_judged_and_kwargs_lambda_is_clean(self):
        want = "a lambda without the keyword is flagged; a lambda with **kw is clean"
        tests = '''import unittest
import unittest.mock

import merge


class LambdaTests(unittest.TestCase):
    def test_bad(self):
        with unittest.mock.patch.object(merge, "sh", lambda args, cwd=None: (0, "")):
            pass

    def test_ok(self):
        with unittest.mock.patch.object(merge, "sh", lambda args, cwd=None, **kw: (0, "")):
            pass
'''
        findings, _ = judge(self, want, "lam", PRODUCT_KW, {"test_merge.py": tests})
        self.assertEqual(where(findings), [("test_merge.py", patch_line_after(tests, "def test_bad"))],
                         "want the lambda without stdout_only flagged, and the lambda with **kw clean")
        self.assertEqual(findings[0]["keyword"], "stdout_only", "want the keyword stdout_only named")

    def test_every_patch_spelling_is_judged(self):
        want = "each patch spelling (dotted, new=, side_effect=, decorator, started later) is judged"
        stand_ins = "".join('def fake_%s(args, cwd=None):\n    return 0, ""\n\n\n' % n for n in "abcde")
        tests = '''import unittest
import unittest.mock
from unittest import mock

import merge


''' + stand_ins + '''def fake_ok(args, cwd=None, stdout_only=False):
    return 0, ""


class SpellingTests(unittest.TestCase):
    def test_dotted_positional(self):
        with unittest.mock.patch.object(merge, "sh", fake_a):
            pass

    def test_new_keyword(self):
        with mock.patch.object(merge, "sh", new=fake_b):
            pass

    def test_side_effect_keyword(self):
        with unittest.mock.patch.object(merge, "sh", side_effect=fake_c):
            pass

    @unittest.mock.patch.object(merge, "sh", fake_d)
    def test_decorator(self):
        pass

    def test_started_later(self):
        p = unittest.mock.patch.object(merge, "sh", fake_e)
        p.start()
        p.stop()

    def test_clean(self):
        with mock.patch.object(merge, "sh", fake_ok):
            pass
'''
        findings, _ = judge(self, want, "spell", PRODUCT_KW, {"test_merge.py": tests})
        self.assertEqual(where(findings), [
            ("test_merge.py", patch_line_after(tests, "def test_dotted_positional")),
            ("test_merge.py", patch_line_after(tests, "def test_new_keyword")),
            ("test_merge.py", patch_line_after(tests, "def test_side_effect_keyword")),
            ("test_merge.py", line_of(tests, "@unittest.mock.patch.object(")),
            ("test_merge.py", patch_line_after(tests, "def test_started_later")),
        ], "want five findings, one per patch spelling, each at its patch call; fake_ok is clean")
        self.assertEqual(sorted(f["standin"] for f in findings), ["fake_a", "fake_b", "fake_c", "fake_d", "fake_e"],
                         "want each spelling's stand-in named")

    def test_nearest_def_wins_in_both_directions(self):
        want = "a nested def shadows a module-level def of the same name; the nearest def is judged"
        tests = '''import unittest
import unittest.mock

import merge


def fake_sh(args):
    return 0, ""


def fake_out(args, cwd=None, stdout_only=False):
    return 0, ""


class ShadowTests(unittest.TestCase):
    def test_nested_narrow(self):
        def fake_out(args):
            return 0, ""

        with unittest.mock.patch.object(merge, "sh", fake_out):
            pass

    def test_nested_wide(self):
        def fake_sh(args, cwd=None, stdout_only=False):
            return 0, ""

        with unittest.mock.patch.object(merge, "sh", fake_sh):
            pass

    def test_module_narrow(self):
        with unittest.mock.patch.object(merge, "sh", fake_sh):
            pass
'''
        findings, _ = judge(self, want, "shadow", PRODUCT_KW, {"test_merge.py": tests})
        self.assertEqual(where(findings), [
            ("test_merge.py", patch_line_after(tests, "def test_nested_narrow")),
            ("test_merge.py", patch_line_after(tests, "def test_module_narrow")),
        ], "want the narrow nested fake_out flagged, the wide nested fake_sh clean, and the module-level narrow fake_sh flagged")
        self.assertEqual(sorted(f["standin"] for f in findings), ["fake_out", "fake_sh"],
                         "want the standins named fake_out and fake_sh")


class ScannerTests(unittest.TestCase):
    def test_patch_text_in_strings_and_comments_is_not_a_stand_in(self):
        want = "a patch call written in a docstring, a comment or a string is not a stand-in"
        tests = '''"""A docstring that quotes the call unittest.mock.patch.object(merge, "sh", fake_sh)."""
# unittest.mock.patch.object(merge, "sh", fake_sh)  don't count this comment
import unittest
import unittest.mock

import merge

QUOTED = 'unittest.mock.patch.object(merge, "sh", fake_sh)  # the text of a call'
BLOCK = """
# unittest.mock.patch.object(merge, "sh", fake_sh)
/* a C-style opener */ // a slash opener
"""


def fake_sh(args):
    return 0, ""


class TextTests(unittest.TestCase):
    def test_real(self):
        with unittest.mock.patch.object(merge, "sh", fake_sh):
            pass
'''
        findings, not_judged = judge(self, want, "text", PRODUCT_KW, {"test_merge.py": tests})
        self.assertEqual(where(findings), [("test_merge.py", line_of(tests, "with unittest.mock.patch.object("))],
                         "want one finding, at the real with-line: the text above it must not shift lines or count")
        self.assertEqual(not_judged, 0, "want the quoted text not counted as an unresolved stand-in")

    def test_a_multi_line_patch_call_is_judged_at_its_first_line(self):
        want = "a patch call spread over several lines is judged, at the line where patch.object( starts"
        tests = '''import unittest
import unittest.mock

import merge


def fake_sh(args):
    return 0, ""


def fake_ok(args, cwd=None, stdout_only=False):
    return 0, ""


class MultiLineTests(unittest.TestCase):
    def test_multi(self):
        with unittest.mock.patch.object(
            merge,
            "sh",
            fake_sh,
        ):
            pass

    def test_clean(self):
        with unittest.mock.patch.object(
            merge,
            "sh",
            fake_ok,
        ):
            pass
'''
        findings, _ = judge(self, want, "multi", PRODUCT_KW, {"test_merge.py": tests})
        self.assertEqual(where(findings), [("test_merge.py", patch_line_after(tests, "def test_multi"))],
                         "want one finding at the line where the multi-line patch.object( call starts")
        self.assertEqual(findings[0]["standin"], "fake_sh", "want the standin named fake_sh")


class ResolutionTests(unittest.TestCase):
    def test_a_stand_in_the_check_cannot_resolve_is_counted_not_flagged(self):
        want = "a MagicMock, Mock, imported name or call result is counted as not judged, and is not a finding"
        tests = '''import unittest
import unittest.mock
from unittest import mock

import merge
from elsewhere import imported_fake


def fake_sh(args):
    return 0, ""


class NotJudgedTests(unittest.TestCase):
    def test_magicmock(self):
        with unittest.mock.patch.object(merge, "sh", unittest.mock.MagicMock()):
            pass

    def test_mock(self):
        with mock.patch.object(merge, "sh", mock.Mock()):
            pass

    def test_imported(self):
        with unittest.mock.patch.object(merge, "sh", imported_fake):
            pass

    def test_factory(self):
        with unittest.mock.patch.object(merge, "sh", make_stub()):
            pass

    def test_flagged(self):
        with unittest.mock.patch.object(merge, "sh", fake_sh):
            pass
'''
        findings, not_judged = judge(self, want, "nj", PRODUCT_KW, {"test_merge.py": tests})
        self.assertEqual(where(findings), [("test_merge.py", patch_line_after(tests, "def test_flagged"))],
                         "want only the resolvable fake_sh flagged; the four unresolved stand-ins are not findings")
        self.assertEqual(not_judged, 4, "want 4 not judged: MagicMock(), Mock(), an imported name, and a call result")

    def test_a_name_the_product_does_not_define_is_out_of_scope(self):
        want = "a patch of a name the product does not define is out of scope: no finding, not counted"
        tests = '''import unittest
import unittest.mock

import merge


def fake_sh(args):
    return 0, ""


def fake_other(args):
    return 0, ""


class ScopeTests(unittest.TestCase):
    def test_sh(self):
        with unittest.mock.patch.object(merge, "sh", fake_sh):
            pass

    def test_not_in_product(self):
        with unittest.mock.patch.object(merge, "not_in_product", fake_other):
            pass
        with unittest.mock.patch.object(merge, "not_in_product", unittest.mock.MagicMock()):
            pass
'''
        findings, not_judged = judge(self, want, "scope", PRODUCT_KW, {"test_merge.py": tests})
        self.assertEqual(where(findings), [("test_merge.py", patch_line_after(tests, "def test_sh"))],
                         "want only the sh stand-in flagged; a name the product lacks is not a product stand-in")
        self.assertEqual(not_judged, 0, "want the out-of-scope MagicMock not counted as not judged")

    def test_empty_product_and_tests_are_clean_once_a_broken_one_is_flagged(self):
        want = "an empty product and test pair has no findings; a pair with a broken stand-in has one"
        text = single_patch("def fake_sh(args):")
        broken, _ = judge(self, want, "broken", PRODUCT_KW, {"test_merge.py": text})
        self.assertEqual(where(broken), [("test_merge.py", patch_line_after(text, "def test_call"))],
                         "want the broken pair flagged first, so a check that reports nothing cannot pass the empty pair")
        empty_tests = '''import unittest


class EmptyTests(unittest.TestCase):
    def test_nothing(self):
        self.assertTrue(True)
'''
        findings, not_judged = judge(self, want, "empty", PRODUCT_EMPTY, {"test_merge.py": empty_tests})
        self.assertEqual(findings, [], "want no finding for a product with no sh() call and a test with no patch")
        self.assertEqual(not_judged, 0, "want nothing counted as not judged in an empty pair")

    def test_a_full_size_test_file_flags_exactly_the_bad_site(self):
        want = "one finding among %d stand-ins: the one that lacks stdout_only" % SITES
        lines = ["import unittest", "import unittest.mock", "", "import merge", ""]
        for i in range(SITES):
            if i == BAD_SITE:
                lines += ["def fake_%02d(args):" % i, "    return 0, ''", "", ""]
            else:
                lines += ["def fake_%02d(args, stdout_only=False):" % i, "    return 0, ''", "", ""]
        lines += ["", "class FullSizeTests(unittest.TestCase):"]
        for i in range(SITES):
            lines += ["    def test_%02d(self):" % i,
                      "        with unittest.mock.patch.object(merge, 'sh', fake_%02d):" % i,
                      "            pass", ""]
        tests = "\n".join(lines) + "\n"
        findings, not_judged = judge(self, want, "full", PRODUCT_KW, {"test_merge.py": tests})
        self.assertEqual(where(findings), [("test_merge.py", patch_line_after(tests, "def test_%02d(self):" % BAD_SITE))],
                         "want exactly one finding, at the patch line of the one stand-in without stdout_only")
        self.assertEqual(not_judged, 0, "want every generated stand-in judged, none counted as not judged")


# The fixture for the forms in UnjudgedFormTests: one test method whose body is the lines a case gives.
FORM_HEAD = '''import json
import unittest
import unittest.mock

import merge


def fake_sh(args):
    return 0, ""


class FormTests(unittest.TestCase):
    def test_form(self):
'''

PRODUCT_LIMIT = PRODUCT_KW + "\nLIMIT = 1\n"


def form_file(body):
    return FORM_HEAD + "".join("        " + line + "\n" for line in body)


class UnjudgedFormTests(unittest.TestCase):
    """A form the check cannot resolve is counted in not_judged, never silent: a MagicMock, a string target, a
    patch.multiple, a new_callable, an assignment to a product function, a setattr, or a ** dict. Each case here is
    such a form, or a control that must add nothing. The cases pin the count and never a judgement of a stand-in."""

    def assert_not_judged_adds(self, want, variant, body, expected, product=PRODUCT_KW):
        """Judge the test file with body against the same file with body set to pass, so the count compares only the
        form's own growth. The form adds no finding."""
        _, base = judge(self, want, variant + "-base", product, {"test_merge.py": form_file(["pass"])})
        findings, got = judge(self, want, variant, product, {"test_merge.py": form_file(body)})
        self.assertEqual(where(findings), [], "want no finding for %s: a form the check cannot judge is counted, not flagged" % want)
        self.assertEqual(got - base, expected, "want not_judged to grow by %d for %s; it grew by %d" % (expected, want, got - base))

    def test_starred_target_tuple_is_counted_not_silent(self):
        want = "patch.object(*target), with target a tuple built in a loop, is counted as not judged, not silent"
        tests = '''import unittest
import unittest.mock

import merge


class StarredTests(unittest.TestCase):
    def test_loop(self):
        for target in ((merge, "sh", unittest.mock.MagicMock()),):
            with unittest.mock.patch.object(*target):
                pass
'''
        findings, not_judged = judge(self, want, "starred", PRODUCT_KW, {"test_merge.py": tests})
        self.assertEqual(where(findings), [], "want no finding for patch.object(*target): its stand-in is a MagicMock")
        self.assertEqual(not_judged, 1, "want patch.object(*target) counted as 1 not judged; got %d, so the form is silent"
                         % not_judged)

    def test_string_target_naming_the_product_module_is_counted_not_silent(self):
        want = 'patch("merge.sh", stand_in), a string target naming the product module, is counted, not silent'
        tests = '''import unittest
import unittest.mock

import merge


class StringTargetTests(unittest.TestCase):
    def test_string(self):
        with unittest.mock.patch("merge.sh", unittest.mock.MagicMock()):
            pass
'''
        findings, not_judged = judge(self, want, "string", PRODUCT_KW, {"test_merge.py": tests})
        self.assertEqual(where(findings), [], 'want no finding for patch("merge.sh", ...): its stand-in is a MagicMock')
        self.assertEqual(not_judged, 1, 'want patch("merge.sh", ...) counted as 1 not judged; got %d, so the form is silent'
                         % not_judged)

    def test_patch_multiple_on_the_product_module_is_counted_not_silent(self):
        want = "patch.multiple(merge, sh=stand_in) is counted as not judged, not silent"
        tests = '''import unittest
import unittest.mock

import merge


class MultipleTests(unittest.TestCase):
    def test_multiple(self):
        with unittest.mock.patch.multiple(merge, sh=unittest.mock.MagicMock()):
            pass
'''
        findings, not_judged = judge(self, want, "multiple", PRODUCT_KW, {"test_merge.py": tests})
        self.assertEqual(where(findings), [], "want no finding for patch.multiple(merge, sh=...): its stand-in is a MagicMock")
        self.assertEqual(not_judged, 1, "want patch.multiple(merge, sh=...) counted as 1 not judged; got %d, so the form is silent"
                         % not_judged)

    def test_new_callable_on_the_product_module_is_counted_not_silent(self):
        want = 'patch.object(merge, "sh", new_callable=...) is counted as not judged, not silent'
        tests = '''import unittest
import unittest.mock

import merge


class NewCallableTests(unittest.TestCase):
    def test_new_callable(self):
        with unittest.mock.patch.object(merge, "sh", new_callable=unittest.mock.MagicMock):
            pass
'''
        findings, not_judged = judge(self, want, "newcallable", PRODUCT_KW, {"test_merge.py": tests})
        self.assertEqual(where(findings), [], 'want no finding for patch.object(merge, "sh", new_callable=...)')
        self.assertEqual(not_judged, 1, 'want patch.object(merge, "sh", new_callable=...) counted as 1 not judged; '
                         "got %d, so the form is silent" % not_judged)

    def test_a_patch_on_an_unrelated_module_adds_nothing(self):
        want = "a patch.object on json, not the product module merge, adds no finding and no not-judged count"
        tests = '''import json
import unittest
import unittest.mock

import merge


def fake_sh(args):
    return 0, ""


class UnrelatedTests(unittest.TestCase):
    def test_broken_def(self):
        with unittest.mock.patch.object(json, "sh", fake_sh):
            pass

    def test_mock(self):
        with unittest.mock.patch.object(json, "sh", unittest.mock.MagicMock()):
            pass
'''
        findings, not_judged = judge(self, want, "control", PRODUCT_KW, {"test_merge.py": tests})
        self.assertEqual(where(findings), [], "want no finding for a patch on json: json is not the product module merge")
        self.assertEqual(not_judged, 0, "want no not-judged count for a patch on json: json is not the product module merge")

    def test_plain_assignment_of_a_product_function_is_counted_not_silent(self):
        want = "merge.sh = lambda *a: None, a plain assignment that replaces a product function"
        self.assert_not_judged_adds(want, "assign", ["merge.sh = lambda *a: None"], expected=1)

    def test_setattr_with_a_literal_name_is_counted_not_silent(self):
        want = 'setattr(merge, "sh", fake_sh), a setattr that replaces a product function'
        self.assert_not_judged_adds(want, "setattr_literal", ['setattr(merge, "sh", fake_sh)'], expected=1)

    def test_setattr_with_a_non_literal_name_is_counted_not_silent(self):
        want = "setattr(merge, name, fake_sh) in a loop over a name that is not a literal"
        self.assert_not_judged_adds(want, "setattr_name", ['for name in ("sh",):', "    setattr(merge, name, fake_sh)"],
                                    expected=1)

    def test_patch_object_with_a_double_star_dict_is_counted_not_silent(self):
        want = 'patch.object(merge, "sh", **kwargs), where the ** dict holds the stand-in'
        self.assert_not_judged_adds(want, "double_star", ['kwargs = {"new": fake_sh}',
                                                          'with unittest.mock.patch.object(merge, "sh", **kwargs):',
                                                          "    pass"], expected=1)

    def test_assignment_to_an_unrelated_module_adds_nothing(self):
        want = "json.loads = fake_sh, an assignment to an attribute of json, not of the product module merge"
        self.assert_not_judged_adds(want, "json_assign", ["json.loads = fake_sh"], expected=0)

    def test_assignment_to_a_product_constant_adds_nothing(self):
        want = "merge.LIMIT = 3, an assignment to a name the product defines only as a constant, not a function"
        self.assert_not_judged_adds(want, "constant_assign", ["merge.LIMIT = 3"], expected=0, product=PRODUCT_LIMIT)

    def test_string_target_on_another_module_adds_nothing(self):
        want = 'patch("json.sh", fake_sh), a string target that names json, not the product module merge'
        self.assert_not_judged_adds(want, "string_json", ['with unittest.mock.patch("json.sh", fake_sh):', "    pass"],
                                    expected=0)

    def test_string_target_on_an_undefined_product_name_adds_nothing(self):
        want = 'patch("merge.undefined_name", fake_sh), a string target naming a name the product does not define'
        self.assert_not_judged_adds(want, "string_undefined",
                                    ['with unittest.mock.patch("merge.undefined_name", fake_sh):', "    pass"], expected=0)

    def test_patch_multiple_on_another_module_adds_nothing(self):
        want = "patch.multiple(json, sh=fake_sh), a patch.multiple on json, not the product module merge"
        self.assert_not_judged_adds(want, "multiple_json", ["with unittest.mock.patch.multiple(json, sh=fake_sh):", "    pass"],
                                    expected=0)

    def test_patch_multiple_with_an_undefined_product_name_adds_nothing(self):
        want = "patch.multiple(merge, undefined_name=fake_sh), a keyword naming a name the product does not define"
        self.assert_not_judged_adds(want, "multiple_undefined",
                                    ["with unittest.mock.patch.multiple(merge, undefined_name=fake_sh):", "    pass"],
                                    expected=0)


class FixtureTests(unittest.TestCase):
    def test_the_check_reads_with_ast_and_never_imports_the_files(self):
        want = "the check reads both files with ast: a module-level statement in either file never runs"
        folder_marks = {}
        product_mark = os.path.join(case_folder(self, "ast"), "product-ran.marker")
        test_mark = os.path.join(case_folder(self, "ast"), "test-ran.marker")
        product = PRODUCT_KW + "open(%r, 'w').close()\n" % product_mark
        tests = {"test_merge.py": single_patch(BROKEN_DEF) + "open(%r, 'w').close()\n" % test_mark}
        findings, _ = judge(self, want, "ast", product, tests)
        self.assertEqual(where(findings), [("test_merge.py", patch_line_after(tests["test_merge.py"], "def test_call"))],
                         "want the broken stand-in still flagged, so the run did read the files")
        folder_marks["product"] = os.path.exists(product_mark)
        folder_marks["test"] = os.path.exists(test_mark)
        self.assertEqual(folder_marks, {"product": False, "test": False},
                         "want neither file imported: a module-level statement in it must not run")


class CliTests(unittest.TestCase):
    def test_command_line_exits_1_on_a_finding_and_0_on_none(self):
        want = "the command line exits 1 with one line per finding, and 0 when the stand-in takes stdout_only"
        broken = run_cli(self, want, "broken", {"merge.py": PRODUCT_STDOUT,
                                                 "test_merge.py": single_patch(BROKEN_DEF)})
        self.assertEqual(broken.returncode, 1, "want exit 1 on a stand-in that lacks stdout_only; got %s" % broken.returncode)
        flagged = [line for line in broken.stdout.splitlines() if "test_merge.py" in line]
        self.assertEqual(len(flagged), 1, "want one output line per finding, naming test_merge.py")
        line = patch_line_after(single_patch(BROKEN_DEF), "def test_call")
        self.assertIsNotNone(re.search(r"test_merge\.py:%d\b" % line, flagged[0]),
                             "want the finding line to name test_merge.py and line %d" % line)
        self.assertIn("stdout_only", flagged[0], "want the finding line to name the keyword stdout_only")
        fixed_tests = single_patch(KWARGS_DEF) + (
            "\n    def test_mock(self):\n"
            "        with unittest.mock.patch.object(merge, 'sh', unittest.mock.MagicMock()):\n"
            "            pass\n")
        fixed = run_cli(self, want, "fixed", {"merge.py": PRODUCT_STDOUT, "test_merge.py": fixed_tests})
        self.assertEqual(fixed.returncode, 0, "want exit 0 when no stand-in is flagged; got %s" % fixed.returncode)

    def test_command_line_prints_one_count_line_for_the_not_judged_stand_ins(self):
        want = "the command line prints one 'N stand-ins not judged' line, and that count does not change the exit"
        fixed_tests = single_patch(KWARGS_DEF) + (
            "\n    def test_mock(self):\n"
            "        with unittest.mock.patch.object(merge, 'sh', unittest.mock.MagicMock()):\n"
            "            pass\n")
        run = run_cli(self, want, "counted", {"merge.py": PRODUCT_STDOUT, "test_merge.py": fixed_tests})
        counts = re.findall(r"\b(\d+) stand-ins not judged\b", run.stdout)
        self.assertEqual(counts, ["1"], "want exactly one 'N stand-ins not judged' line, with N 1 for the MagicMock()")
        self.assertEqual(run.returncode, 0, "want a not-judged stand-in to leave the exit at 0")


if __name__ == "__main__":
    unittest.main()
