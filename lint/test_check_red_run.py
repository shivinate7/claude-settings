#!/usr/bin/env python3
"""Cases for lint/check_red_run.py. Standard library only.

    python3 lint/test_check_red_run.py

A commit that adds lines to a test path carries a trailer line in its message:

    Red-run: <command> -> <N> failed on <sha>     N >= 1, sha 7 or more hex digits
    Red-run: none: <reason>                       reason non-empty
    Red-run: mutant: <mutation> -> <N> failed on <sha>   mutation non-empty; sha 7 or more hex digits

The check reads the non-merge commits in <base>..HEAD, from --base <sha>, else env BASE_SHA. A test
path is one that hooks/guard.py is_test_rel judges. When HEAD holds lint/check_red_run.py, a commit whose
parent tree lacks it predates the check, so it is not judged. A repo without the file at HEAD gets no such
exemption: every non-merge commit that is not a revert is judged.

Each case builds a fixture repo under this run's folder (lint/_test_temp.py): a base commit, then
change commits on top. The check runs as the copy at lint/check_red_run.py in that repo. The cwd and
--root cases run the module by its path, from another directory. CHECK_RED_RUN_UNDER_TEST overrides the
module path, which a stub run uses.
"""
import importlib.util
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
MODULE = os.path.abspath(os.environ.get("CHECK_RED_RUN_UNDER_TEST") or os.path.join(HERE, "check_red_run.py"))
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  copies what git lists, so no fixture lists files (testing/tracked_tree.py)

CHECK_REL = "lint/check_red_run.py"
PRODUCT_REL = "src/widgets.py"
PRODUCT_TEXT = "def widget():\n    return 1\n"
TEST_TEXT = "def test_widget():\n    assert widget() == 1\n"
GOOD = "Red-run: python3 lint/test_widgets.py -> 2 failed on abc1234"
# Lines carry the placeholder SHA, filled with a real fixture sha by each case (see filled).
VALID_LINE = "Red-run: python3 lint/test_widgets.py -> 1 failed on SHA"
# Keyword typos. Each must flag its commit, and none may pass as a failed-form command. The last six and the generic
# one name the words a builder's rule refuses: a first word that ends in a colon (other than `mutant:` and `none:`), or
# that starts `mutat` or `mutan`. `runner:` stands for every colon word.
KEYWORD_TYPOS = ("Red-run: mutants: x -> 1 failed on SHA",
                 "Red-run: mutation: x -> 1 failed on SHA",
                 "Red-run: mutant x -> 1 failed on SHA",
                 "Red-run: non: reason",
                 "Red-run: Mutant A (x) -> 1 failed on SHA",
                 "Red-run: mutations x -> 1 failed on SHA",
                 "Red-run: mutate x -> 1 failed on SHA",
                 "Red-run: none x -> 1 failed on SHA",
                 "Red-run: non x -> 1 failed on SHA",
                 "Red-run: mutated x -> 1 failed on SHA",
                 "Red-run: mutating x -> 1 failed on SHA",
                 "Red-run: mutates: x -> 1 failed on SHA",
                 "Red-run: mutan: x -> 1 failed on SHA",
                 "Red-run: mutnat: x -> 1 failed on SHA",
                 "Red-run: nonee: x -> 1 failed on SHA",
                 "Red-run: runner: x -> 1 failed on SHA")
# Wrapped and typo'd words. A wrapper is a bracket, a quote (straight or curly), an underscore, `*` or `#`. A word is a typo of
# `mutant` or `mutation` (one edit or one adjacent swap away), or starts `mutat` or `mutan` (`mutate=x`). The failed form would
# read each as a command, so each must flag its commit, alone and beside a valid line. `**none**` is a none word, not a mutant
# word, so it sits in WRAPPED_AND_TYPO only: the hint test reads MUTANT_TYPOS, and a none word takes no mutant hint.
WRAPPED_MUTANT_TYPOS = ("Red-run: (mutant A) -> 1 failed on SHA",
                        'Red-run: "mutant A" -> 1 failed on SHA',
                        "Red-run: [mutant] -> 1 failed on SHA",
                        "Red-run: - mutant: A -> 1 failed on SHA",
                        "Red-run: _mutant_ x -> 1 failed on SHA",
                        "Red-run: _mutnat_ x -> 1 failed on SHA",
                        "Red-run: “mutant A” -> 1 failed on SHA",
                        "Red-run: #mutant x -> 1 failed on SHA",
                        "Red-run: ‘mutant’ x -> 1 failed on SHA",
                        "Red-run: mutnat x -> 1 failed on SHA",
                        "Red-run: mtuant x -> 1 failed on SHA",
                        "Red-run: mutnt x -> 1 failed on SHA",
                        "Red-run: mutaiton x -> 1 failed on SHA",
                        "Red-run: mutate=x -> 1 failed on SHA",
                        "Red-run: mutan=x -> 1 failed on SHA")
WRAPPED_AND_TYPO = WRAPPED_MUTANT_TYPOS + ("Red-run: (none) -> 1 failed on SHA", "Red-run: **none** x -> 1 failed on SHA")
# The refused keywords that start `mutant` or `mutation`, and the wrapped and typo'd mutant words. Their FAIL line holds the
# hint that names the mutant form.
MUTANT_TYPOS = (tuple(line for line in KEYWORD_TYPOS if re.match(r"Red-run: mut(?:ant|ation)", line, re.IGNORECASE))
                + WRAPPED_MUTANT_TYPOS)
# A mutant keyword with text glued on. The failed form would read it as a command, so each must flag its commit.
PREFIX_BYPASSES = ("Red-run: mutant(A) (x) -> 1 failed on SHA",
                   "Red-run: mutant-A (x) -> 1 failed on SHA",
                   "Red-run: mutantA: x -> 1 failed on SHA",
                   "Red-run: mutant=x -> 1 failed on SHA")
# A key that is not `Red-run:` at line start. Beside a valid line, each is a malformed Red-run line.
CASE_VARIANT_KEYS = ("Red-Run: none (x)", "red-run: none", "Red-run : x")
VALID_NONE = "Red-run: none: ok"
# A key that reads like `Red-run:` but is not. Each body is a valid failed form, so the key is the only defect. Beside a
# valid line, each is a malformed Red-run line and flags the commit.
NEAR_MISS_KEYS = ("Red-runs: python3 x -> 1 failed on SHA",
                  "Red run: python3 x -> 1 failed on SHA",
                  "Red_run: python3 x -> 1 failed on SHA",
                  "Redrun: python3 x -> 1 failed on SHA",
                  "Red-run python3 x -> 1 failed on SHA")
# Lines that are not a Red-run key, so each passes beside a valid line: prose that mentions the key mid-line, and a
# word that only starts like the key.
NOT_KEY_LINES = ("Prose: the Red-run: none form is for re-points.",
                 "the red-run check reads it",
                 "see Red-run docs",
                 "Redress: x",
                 "Reduce: y")
# Real commands pass as the failed form. Each first word is an ordinary word, a path, or an environment assignment. An
# upper-case assignment (`NAME=value`, quoted or not) skips the second layer, so `MUTATE_ONLY=x` and `MUTATE_ONLY="a: b"`
# pass. The first layer still reads it: `MUTANT_X=1` is refused, as `mutant=x` is. Any assignment is exempt from the colon
# refusal, as `lint_mode=on:` is. `mutant=x` and `mutate=x` stay refused (PREFIX_BYPASSES, WRAPPED_AND_TYPO).
REAL_COMMANDS = ("Red-run: python3 lint/test_x.py -> 2 failed on SHA",
                 "Red-run: MUTATE_ONLY='x' python3 hooks/test_guard.py -> 1 failed on SHA",
                 "Red-run: MUTATE_ONLY=x python3 lint/test_x.py -> 1 failed on SHA",
                 'Red-run: MUTATE_ONLY="worktree-home: the cross-checkout read costs" python3 hooks/test_guard.py -> 1 failed on SHA',
                 "Red-run: NONE=1 python3 lint/test_x.py -> 1 failed on SHA",
                 "Red-run: env X=1 python3 lint/test_x.py -> 1 failed on SHA",
                 "Red-run: nonstop lint/test_x.py -> 1 failed on SHA",
                 "Red-run: make test -> 1 failed on SHA",
                 "Red-run: ./bin/verdict python3 lint/test_x.py -> 1 failed on SHA",
                 "Red-run: mutmut run -> 1 failed on SHA",
                 "Red-run: ./mutation_probe.sh -> 1 failed on SHA",
                 "Red-run: ./scripts/mutation_probe.sh -> 1 failed on SHA",
                 "Red-run: python3 -m pytest -k mutant_case -> 1 failed on SHA",
                 "Red-run: lint/mutation/run.py -> 1 failed on SHA",
                 "Red-run: env mutatest run -> 1 failed on SHA",
                 "Red-run: node lint/test_x.js -> 1 failed on SHA",
                 "Red-run: mutagen run -> 1 failed on SHA",
                 "Red-run: (cd lint && python3 test_x.py) -> 1 failed on SHA",
                 "Red-run: python3 lint/test_x.py (mutant: x) -> 1 failed on SHA",
                 "Red-run: lint_mode=on: python3 lint/test_x.py -> 1 failed on SHA",
                 "Red-run: _build/run_tests.sh -> 1 failed on SHA",
                 "Red-run: __main__.py -> 1 failed on SHA")
# The label word, one row per line form: (line, expected, source). `refused` is a line the check must refuse as a
# failed form, `valid` one it must pass. `SHA` is filled with LABEL_SHA. The source names the form family a row pins,
# and labels its failure message. A row runs three ways: valid_line alone, beside a valid line, and the mutant hint in the FAIL line.
LABEL_SHA = "abcdef1"
LABEL_FORMS = (
    # Forms the check must refuse: a mutant or none typo, or a key variant.
    ("Red-run: mutant A (...) -> 1 failed on SHA", "refused", "typo or key variant"),
    ("Red-run: mutant(A) -> 1 failed on SHA", "refused", "typo or key variant"),
    ("Red-run: mutant-A -> 1 failed on SHA", "refused", "typo or key variant"),
    ("Red-run: mutantA: x -> 1 failed on SHA", "refused", "typo or key variant"),
    ("Red-run: mutant= x -> 1 failed on SHA", "refused", "typo or key variant"),
    ("Red-run: mutated x -> 1 failed on SHA", "refused", "typo or key variant"),
    ("Red-run: mutating x -> 1 failed on SHA", "refused", "typo or key variant"),
    ("Red-run: mutates: x -> 1 failed on SHA", "refused", "typo or key variant"),
    ("Red-run: mutan: x -> 1 failed on SHA", "refused", "typo or key variant"),
    ("Red-run: mutnat: x -> 1 failed on SHA", "refused", "typo or key variant"),
    ("Red-run: nonee: x -> 1 failed on SHA", "refused", "typo or key variant"),
    ("Red-run: none x -> 1 failed on SHA", "refused", "typo or key variant"),
    ("Red-run: non: x -> 1 failed on SHA", "refused", "typo or key variant"),
    ("Red-run: runner: x -> 1 failed on SHA", "refused", "typo or key variant"),
    ("Red-Run: python3 lint/test_x.py -> 1 failed on SHA", "refused", "typo or key variant"),
    ("red-run: python3 lint/test_x.py -> 1 failed on SHA", "refused", "typo or key variant"),
    ("Red-run : python3 lint/test_x.py -> 1 failed on SHA", "refused", "typo or key variant"),
    # Wrapped and typo'd words. The check refuses each one.
    ("Red-run: (mutant A) -> 1 failed on SHA", "refused", "wrapped or typo'd word"),
    ('Red-run: "mutant A" -> 1 failed on SHA', "refused", "wrapped or typo'd word"),
    ("Red-run: [mutant] -> 1 failed on SHA", "refused", "wrapped or typo'd word"),
    ("Red-run: - mutant: A -> 1 failed on SHA", "refused", "wrapped or typo'd word"),
    ("Red-run: mutnat x -> 1 failed on SHA", "refused", "wrapped or typo'd word"),
    ("Red-run: mtuant x -> 1 failed on SHA", "refused", "wrapped or typo'd word"),
    ("Red-run: mutnt x -> 1 failed on SHA", "refused", "wrapped or typo'd word"),
    ("Red-run: mutaiton x -> 1 failed on SHA", "refused", "wrapped or typo'd word"),
    ("Red-run: mutate=x -> 1 failed on SHA", "refused", "wrapped or typo'd word"),
    ("Red-run: mutan=x -> 1 failed on SHA", "refused", "wrapped or typo'd word"),
    ("Red-run: (none) -> 1 failed on SHA", "refused", "wrapped or typo'd word"),
    ("Red-run: **none** x -> 1 failed on SHA", "refused", "wrapped or typo'd word"),
    ("Red-run: `none` x -> 1 failed on SHA", "refused", "wrapped or typo'd word"),
    ("Red-run: `mutant` x -> 1 failed on SHA", "refused", "wrapped or typo'd word"),
    ("Red-run: _mutant_ x -> 1 failed on SHA", "refused", "wrapped or typo'd word"),
    ("Red-run: _mutnat_ x -> 1 failed on SHA", "refused", "wrapped or typo'd word"),
    ("Red-run: “mutant A” -> 1 failed on SHA", "refused", "wrapped or typo'd word"),
    ("Red-run: ‘mutant’ x -> 1 failed on SHA", "refused", "wrapped or typo'd word"),
    ("Red-run: #mutant x -> 1 failed on SHA", "refused", "wrapped or typo'd word"),
    ("Red-run: **mutant** x -> 1 failed on SHA", "refused", "wrapped or typo'd word"),
    # A wrapper nested inside an underscore, or a list marker, tilde, brace or angle bracket, is refused as a failed form.
    ("Red-run: _**mutant**_ x -> 1 failed on SHA", "refused", "wrapper or marker"),
    ("Red-run: _`mutant`_ x -> 1 failed on SHA", "refused", "wrapper or marker"),
    ('Red-run: _"mutant"_ x -> 1 failed on SHA', "refused", "wrapper or marker"),
    ("Red-run: _'mutant'_ x -> 1 failed on SHA", "refused", "wrapper or marker"),
    ("Red-run: _(none)_ x -> 1 failed on SHA", "refused", "wrapper or marker"),
    ("Red-run: ~mutant~ x -> 1 failed on SHA", "refused", "wrapper or marker"),
    ("Red-run: > mutant x -> 1 failed on SHA", "refused", "wrapper or marker"),
    ("Red-run: 1) mutant x -> 1 failed on SHA", "refused", "wrapper or marker"),
    ("Red-run: {mutant} x -> 1 failed on SHA", "refused", "wrapper or marker"),
    ("Red-run: <mutant> x -> 1 failed on SHA", "refused", "wrapper or marker"),
    # A list marker inside a leading underscore: the strip reads through both to the word.
    ("Red-run: _-mutant A (x) -> 1 failed on SHA", "refused", "list marker under underscore"),
    ("Red-run: _+mutant A -> 1 failed on SHA", "refused", "list marker under underscore"),
    ("Red-run: _- mutant A -> 1 failed on SHA", "refused", "list marker under underscore"),
    ("Red-run: _+none -> 1 failed on SHA", "refused", "list marker under underscore"),
    # A fixed point, not a fixed count of passes: forty wrappers each side still read as the word.
    ("Red-run: " + "(" * 40 + "mutant" + ")" * 40 + " x -> 1 failed on SHA", "refused", "fixed point"),
    # Real commands pass as the failed form. These are the must-pass rows.
    ("Red-run: python3 -m pytest -k mutant_case -> 1 failed on SHA", "valid", "must-pass"),
    ("Red-run: lint/mutation/run.py -> 1 failed on SHA", "valid", "must-pass"),
    ("Red-run: ./mutation_probe.sh -> 1 failed on SHA", "valid", "must-pass"),
    ("Red-run: env mutatest run -> 1 failed on SHA", "valid", "must-pass"),
    ("Red-run: MUTATE_ONLY=x python3 lint/test_x.py -> 1 failed on SHA", "valid", "must-pass"),
    ('Red-run: MUTATE_ONLY="worktree-home: the cross-checkout read costs" python3 hooks/test_guard.py -> 1 failed on SHA',
     "valid", "must-pass"),
    ("Red-run: node lint/test_x.js -> 1 failed on SHA", "valid", "must-pass"),
    ("Red-run: mutagen run -> 1 failed on SHA", "valid", "must-pass"),
    ("Red-run: mutmut run -> 1 failed on SHA", "valid", "must-pass"),
    ("Red-run: (cd lint && python3 test_x.py) -> 1 failed on SHA", "valid", "must-pass"),
    ("Red-run: _build/run_tests.sh -> 1 failed on SHA", "valid", "must-pass"),
    ("Red-run: __main__.py -> 1 failed on SHA", "valid", "must-pass"),
    ("Red-run: _mutant.sh -> 1 failed on SHA", "valid", "must-pass"),
    ("Red-run: _mutation_probe.sh -> 1 failed on SHA", "valid", "must-pass"),
    ("Red-run: __none__.py -> 1 failed on SHA", "valid", "must-pass"),
    ("Red-run: ./mutant -> 1 failed on SHA", "valid", "must-pass"),
    ("Red-run: nonstop lint/test_x.py -> 1 failed on SHA", "valid", "must-pass"),
    ("Red-run: NONE=1 python3 lint/test_x.py -> 1 failed on SHA", "valid", "must-pass"),
    ("Red-run: lint_mode=on: python3 lint/test_x.py -> 1 failed on SHA", "valid", "must-pass"),
    ("Red-run: python3 lint/test_x.py (mutant: x) -> 1 failed on SHA", "valid", "must-pass"),
    # An upper-case assignment behind a list marker, a number or a wrapper is a real command's prefix, so it passes.
    ("Red-run: - MUTATE_ONLY=x python3 t.py -> 1 failed on SHA", "valid", "assignment behind a prefix"),
    ("Red-run: `MUTATE_ONLY=x python3 t.py -> 1 failed on SHA", "valid", "assignment behind a prefix"),
    ("Red-run: (MUTATE_ONLY=x python3 t.py -> 1 failed on SHA", "valid", "assignment behind a prefix"),
    ('Red-run: "MUTATE_ONLY=x python3 t.py -> 1 failed on SHA', "valid", "assignment behind a prefix"),
    ("Red-run: *MUTATE_ONLY=x python3 t.py -> 1 failed on SHA", "valid", "assignment behind a prefix"),
    ("Red-run: > MUTATE_ONLY=x python3 t.py -> 1 failed on SHA", "valid", "assignment behind a prefix"),
    ("Red-run: 1. MUTATE_ONLY=x python3 t.py -> 1 failed on SHA", "valid", "assignment behind a prefix"),
    ("Red-run: 1) MUTATE_ONLY=x python3 t.py -> 1 failed on SHA", "valid", "assignment behind a prefix"),
    # Controls: the two valid keyword forms, so a refusal above is not a broken line shape.
    ("Red-run: mutant: drop the guard -> 1 failed on SHA", "valid", "control"),
    ("Red-run: none: re-points fixtures", "valid", "control"),
)
# The normalised label word of a line: the first word after `Red-run:`, with its wrappers, list markers, emphasis and
# trailing closers and colons stripped, in lower case. A leading underscore that closes no underscore stays (a real name),
# unless the core is bare letters: `_-mutant` reads `mutant`. Each row is (line, word, upper_env). upper_env is True
# when the stripped token, before it is folded to lower case, is an upper-case `NAME=` assignment.
LABEL_WORDS = (
    ("Red-run:", "", False),  # the empty state: no word
    ("Red-run: (mutant A) -> 1 failed on SHA", "mutant", False),
    ('Red-run: "mutant A" -> 1 failed on SHA', "mutant", False),
    ("Red-run: [mutant] -> 1 failed on SHA", "mutant", False),
    ("Red-run: - mutant: A -> 1 failed on SHA", "mutant", False),
    ("Red-run: * mutant x -> 1 failed on SHA", "mutant", False),
    ("Red-run: > mutant x -> 1 failed on SHA", "mutant", False),
    ("Red-run: 1) mutant x -> 1 failed on SHA", "mutant", False),
    ("Red-run: 1. mutant x -> 1 failed on SHA", "mutant", False),
    ("Red-run: {mutant} x -> 1 failed on SHA", "mutant", False),
    ("Red-run: <mutant> x -> 1 failed on SHA", "mutant", False),
    ("Red-run: `mutant` x -> 1 failed on SHA", "mutant", False),
    ("Red-run: “mutant A” -> 1 failed on SHA", "mutant", False),
    ("Red-run: ‘mutant’ x -> 1 failed on SHA", "mutant", False),
    ("Red-run: #mutant x -> 1 failed on SHA", "mutant", False),
    ("Red-run: ~mutant~ x -> 1 failed on SHA", "mutant", False),
    ("Red-run: _mutant_ x -> 1 failed on SHA", "mutant", False),
    ("Red-run: _mutant A_ x -> 1 failed on SHA", "mutant", False),
    ("Red-run: _mutnat_ x -> 1 failed on SHA", "mutnat", False),
    # A list marker inside a leading underscore strips to the word.
    ("Red-run: _-mutant A (x) -> 1 failed on SHA", "mutant", False),
    ("Red-run: _+mutant A -> 1 failed on SHA", "mutant", False),
    ("Red-run: _- mutant A -> 1 failed on SHA", "mutant", False),
    ("Red-run: _+none -> 1 failed on SHA", "none", False),
    ("Red-run: **none** x -> 1 failed on SHA", "none", False),
    ("Red-run: (none) x -> 1 failed on SHA", "none", False),
    ("Red-run: _(none)_ x -> 1 failed on SHA", "none", False),
    ("Red-run: _**mutant**_ x -> 1 failed on SHA", "mutant", False),
    ("Red-run: **_mutant_** x -> 1 failed on SHA", "mutant", False),
    ("Red-run: _`mutant`_ x -> 1 failed on SHA", "mutant", False),
    ('Red-run: _"mutant"_ x -> 1 failed on SHA', "mutant", False),
    ("Red-run: _'mutant'_ x -> 1 failed on SHA", "mutant", False),
    ("Red-run: mutant: x -> 1 failed on SHA", "mutant", False),
    ("Red-run: mutant, x -> 1 failed on SHA", "mutant", False),
    ("Red-run: (mutant:) x -> 1 failed on SHA", "mutant", False),
    ("Red-run: MUTANT: x -> 1 failed on SHA", "mutant", False),
    ("Red-run: Mutant x -> 1 failed on SHA", "mutant", False),
    ("Red-run: mutnt x -> 1 failed on SHA", "mutnt", False),
    ("Red-run: mutant=x x -> 1 failed on SHA", "mutant=x", False),
    ("Red-run: _build/run_tests.sh -> 1 failed on SHA", "_build/run_tests.sh", False),
    ("Red-run: _Build/Run_Tests.sh x -> 1 failed on SHA", "_build/run_tests.sh", False),
    ("Red-run: __main__.py -> 1 failed on SHA", "__main__.py", False),
    ("Red-run: _mutant.sh x -> 1 failed on SHA", "_mutant.sh", False),
    ("Red-run: _mutation_probe.sh x -> 1 failed on SHA", "_mutation_probe.sh", False),
    ("Red-run: __none__.py x -> 1 failed on SHA", "__none__.py", False),
    ("Red-run: ./mutant x -> 1 failed on SHA", "./mutant", False),
    ("Red-run: python3 lint/test_x.py (mutant: x) -> 1 failed on SHA", "python3", False),
    ("Red-run: " + "(" * 40 + "mutant" + ")" * 40 + " x -> 1 failed on SHA", "mutant", False),
    # An upper-case assignment behind a list marker, a number or a wrapper reads as its word.
    ("Red-run: - MUTATE_ONLY=x python3 t.py -> 1 failed on SHA", "mutate_only=x", True),
    ("Red-run: `MUTATE_ONLY=x python3 t.py -> 1 failed on SHA", "mutate_only=x", True),
    ("Red-run: (MUTATE_ONLY=x python3 t.py -> 1 failed on SHA", "mutate_only=x", True),
    ('Red-run: "MUTATE_ONLY=x python3 t.py -> 1 failed on SHA', "mutate_only=x", True),
    ("Red-run: *MUTATE_ONLY=x python3 t.py -> 1 failed on SHA", "mutate_only=x", True),
    ("Red-run: > MUTATE_ONLY=x python3 t.py -> 1 failed on SHA", "mutate_only=x", True),
    ("Red-run: 1. MUTATE_ONLY=x python3 t.py -> 1 failed on SHA", "mutate_only=x", True),
    ("Red-run: 1) MUTATE_ONLY=x python3 t.py -> 1 failed on SHA", "mutate_only=x", True),
    # A lower-case assignment is not an environment exemption: its upper_env stays False.
    ("Red-run: mutate=x -> 1 failed on SHA", "mutate=x", False),
    ("Red-run: mutant=x -> 1 failed on SHA", "mutant=x", False),
)
BASE_REF = "origin/main"
# origin/main's name for the message verdict, read from its checker. The read accepts either name in BASE_VERDICTS.
BASE_VERDICTS = ("has_valid_trailer", "has_trailer")
VERDICT = "has_valid_trailer"  # this checker's name for the message verdict
FIELD = "\x1f"
# Every commit carries this block, as real commits do. A check that wants Red-run as the last
# trailer fails here, not on the first real commit.
ATTRIBUTION = ["Co-Authored-By: Claude <noreply@anthropic.com>",
               "Claude-Session: https://claude.ai/code/session_0000"]

GIT_ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
for _name in ("BASE_SHA", "CI", "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
    GIT_ENV.pop(_name, None)  # a case sets BASE_SHA itself; the outer shell's values never leak in

RUN_FOLDER = None


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    if RUN_FOLDER and os.path.isdir(RUN_FOLDER):
        tracked_tree.rm_tree(RUN_FOLDER)  # test-temp-standard: teardown removes the run folder


def read_module():
    with open(MODULE, encoding="utf-8", newline="") as f:
        return f.read()


def filled(lines, sha):
    """Each line with the placeholder SHA replaced by a real sha."""
    return [line.replace("SHA", sha) for line in lines]


def with_why(why, out):
    """An assert message: the one cause the case names, then the check's output."""
    return out if why is None else why + "\n" + out


class Unknown(Exception):
    """A git read of origin/main failed, so the history pin cannot say."""


def git_text(*args):
    done = subprocess.run(["git", *args], cwd=HERE, capture_output=True, encoding="utf-8", errors="replace", env=GIT_ENV)
    if done.returncode:
        raise Unknown("unknown: git %s failed: %s" % (args[0], done.stderr.strip()))
    return done.stdout


def shallow_clone():
    """True when this checkout is a shallow clone, whose history stops short of origin/main's."""
    return git_text("rev-parse", "--is-shallow-repository").strip() == "true"


# A shallow clone cuts origin/main's history short, so the pin would pass falsely there. CI fetches the full history.
SHALLOW_REASON = ("shallow clone: origin/main's history stops short here, so the pin would pass falsely. "
                  "CI fetches the full history (fetch-depth 0 in .github/workflows/checks.yml)")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verdict(module, name, message):
    return getattr(module, name)(message)


def main_messages():
    """(sha, subject, message) for each non-merge commit on origin/main."""
    out = git_text("log", "--no-merges", "-z", "--format=%H" + FIELD + "%s" + FIELD + "%B", BASE_REF)
    records = []
    for chunk in out.split("\0"):
        if chunk.strip():
            sha, subject, message = chunk.lstrip("\n").split(FIELD, 2)
            records.append((sha, subject, message))
    return records


def load_baseline(folder):
    """origin/main's checker, loaded from its git blob. Its hooks are this checkout's: the message verdict imports none."""
    base = tempfile.mkdtemp(dir=folder, prefix="base_")  # test-temp-standard: the run folder holds it
    os.makedirs(os.path.join(base, "lint"))
    done = subprocess.run(["git", "show", BASE_REF + ":" + CHECK_REL], cwd=HERE, capture_output=True, env=GIT_ENV)
    if done.returncode:
        raise Unknown("unknown: origin/main has no %s: %s" % (CHECK_REL, done.stderr.decode("utf-8", "replace").strip()))
    path = os.path.join(base, "lint", "check_red_run.py")
    with open(path, "wb") as f:
        f.write(done.stdout)
    tracked_tree.copy_tracked(base, "hooks")
    return load_module("check_red_run_on_main", path)


def base_verdict_name(module):
    """The name origin/main's checker gives the message verdict. Raises when it has neither, so the pin says why."""
    for name in BASE_VERDICTS:
        if hasattr(module, name):
            return name
    raise AssertionError("origin/main's checker has none of %s: re-point the pin" % ", ".join(BASE_VERDICTS))


def lost_trailers(baseline, current, records):
    """One line per message that origin/main's checker accepts and `current` refuses, named by short sha and subject."""
    base_name = base_verdict_name(baseline)
    lost = []
    for sha, subject, message in records:
        if verdict(baseline, base_name, message) and not verdict(current, VERDICT, message):
            lost.append("%s %s" % (sha[:7], subject))
    return lost


class Fixture(unittest.TestCase):
    """A fixture repo: a base commit, then the change commits that a case adds on top."""

    def setUp(self):
        self.tree = tempfile.mkdtemp(dir=RUN_FOLDER, prefix="crr_")
        self.addCleanup(tracked_tree.rm_tree, self.tree)
        tracked_tree.copy_tracked(self.tree, "lint", "hooks")  # the check's imports, such as hooks/guard.py
        self.serial = 0
        self.git("init", "-q")
        self.git("symbolic-ref", "HEAD", "refs/heads/main")

    def git(self, *args, input=None):
        done = subprocess.run(["git", "-C", self.tree, "-c", "user.name=test", "-c", "user.email=test@example.com",
                               "-c", "core.autocrlf=false", *args],
                              check=True, capture_output=True, text=True, env=GIT_ENV, input=input)
        return done.stdout.strip()

    def has_file(self, rev, rel):
        done = subprocess.run(["git", "-C", self.tree, "cat-file", "-e", rev + ":" + rel],
                              capture_output=True, env=GIT_ENV)
        return done.returncode == 0

    def names_commit(self, rev):
        """True when git resolves rev to a commit in the fixture repo."""
        done = subprocess.run(["git", "-C", self.tree, "cat-file", "-e", rev + "^{commit}"],
                              capture_output=True, env=GIT_ENV)
        return done.returncode == 0

    def reaches_head(self, rev):
        """True when HEAD's history holds rev."""
        done = subprocess.run(["git", "-C", self.tree, "merge-base", "--is-ancestor", rev, "HEAD"],
                              capture_output=True, env=GIT_ENV)
        return done.returncode == 0

    def new_test_path(self):
        """A new test file path per call, so no two commits of one case add the same lines."""
        self.serial += 1
        return "lint/test_widgets_%d.py" % self.serial

    def commit(self, subject, files, red=None):
        """Write files (a None value deletes one), commit them, return the full sha. `red` is a Red-run line, or a list."""
        for rel, text in files.items():
            path = os.path.join(self.tree, *rel.split("/"))
            if text is None:
                os.remove(path)
                continue
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(text)
        if files:
            self.git("add", "--", *files)  # only the named paths join the commit
        reds = [red] if isinstance(red, str) else list(red or [])
        body = reds + ATTRIBUTION
        self.git("commit", "-q", "--allow-empty", "--cleanup=verbatim", "-F", "-",
                 input=subject + "\n\n" + "\n".join(body) + "\n")
        return self.git("rev-parse", "HEAD")

    def base(self, files=None, check=True):
        """The base commit the check diffs from. check=False builds a parent tree from before the check landed."""
        files = dict(files or {})
        if check:
            files[CHECK_REL] = read_module()
        self.base_sha = self.commit("fixture base", files)
        self.assertEqual(self.has_file(self.base_sha, CHECK_REL), check)

    def merge(self, branch):
        self.git("merge", "-q", "--no-ff", "-m", "Merge " + branch, branch)
        return self.git("rev-parse", "HEAD")

    def lint(self, args=None, env=None, script=None, cwd=None):
        """Run the check in the fixture repo: the copy by default, or `script` by path from `cwd`.
        Returns (exit code, stdout and stderr)."""
        argv = ["--base", self.base_sha] if args is None else args
        script = script or os.path.join(self.tree, "lint", "check_red_run.py")
        done = subprocess.run([sys.executable, script, *argv],
                              cwd=cwd or self.tree, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              env=dict(GIT_ENV, **(env or {})))
        return done.returncode, done.stdout + done.stderr


class CheckCase(Fixture):
    """Cases that need the check. setUp fails when the check file is absent, so no case passes without it."""

    def setUp(self):
        self.assertTrue(os.path.isfile(MODULE), "module absent: lint/check_red_run.py")
        super().setUp()

    def assertClean(self, args=None, env=None, script=None, cwd=None, why=None):
        rc, out = self.lint(args, env, script, cwd)
        self.assertEqual(rc, 0, with_why(why, out))
        self.assertNotIn("Traceback", out, out)

    def assertGap(self, out, sha, subject, rel):
        """The output names the commit by short sha and subject, and names the path it added on the sha's line."""
        short = sha[:7]
        self.assertNotIn("Traceback", out, out)
        self.assertIn(short, out, out)
        self.assertIn(subject, out, out)
        self.assertTrue(any(short in line and rel in line for line in out.splitlines()),
                        "no line names %s with %s:\n%s" % (short, rel, out))

    def assertFlagged(self, sha, subject, rel, script=None, cwd=None, why=None):
        rc, out = self.lint(script=script, cwd=cwd)
        self.assertEqual(rc, 1, with_why(why, out))
        self.assertGap(out, sha, subject, rel)
        return out

    def scratch_repo_test_commit(self, red=None):
        """One test commit in a repo that lacks the check file at HEAD, the shape of any repo but claude-settings.
        The tree's disk copy of the script is untracked, so the case also rejects a check read from disk."""
        self.base(check=False)
        rel = self.new_test_path()
        sha = self.commit("add widget tests", {rel: TEST_TEXT}, red=red)
        self.assertFalse(self.has_file("HEAD", CHECK_REL))
        return rel, sha

    def flagged_untrailered(self):
        """Flag one test commit that carries no trailer. Returns the check's output."""
        self.base()
        rel = self.new_test_path()
        sha = self.commit("add widget tests", {rel: TEST_TEXT})
        return self.assertFlagged(sha, "add widget tests", rel)

    def test_untrailered_test_commit_is_flagged(self):
        out = self.flagged_untrailered()
        # The check's message states each trailer form, and how to add a trailer to a commit.
        self.assertIn("Red-run: <command> -> <N> failed on <sha>", out, out)
        self.assertIn("Red-run: mutant: <mutation> -> <N> failed on <sha>", out, out)
        self.assertIn("Red-run: none: <reason>", out, out)
        self.assertIn("reword", out, out)

    def test_remedy_names_no_force_or_interactive_route(self):
        out = self.flagged_untrailered()
        # The sessions cannot run a forced push or an interactive rebase.
        self.assertIsNone(re.search(r"--force|\s-f\b", out), "remedy names a forced push:\n" + out)
        self.assertIsNone(re.search(r"rebase\s+(-i\b|--interactive)", out),
                          "remedy names an interactive rebase:\n" + out)
        self.assertIsNone(re.search(r"(?:^|[\s`])\+[\w/:]", out), "remedy names a + refspec:\n" + out)

    def test_remedy_amend_carries_a_message(self):
        out = self.flagged_untrailered()
        self.assertIn("--amend", out, "remedy names no amend route for the last commit:\n" + out)
        # An amend with no -m opens an editor, which a session cannot drive.
        for amend in re.finditer(r"--amend", out):
            segment = re.split(r"[`\n]", out[amend.end():], maxsplit=1)[0]
            self.assertIsNotNone(re.search(r"(?<![\w-])-m\b|--message\b", segment),
                                 "remedy names an amend with no -m:\n" + out)

    def test_remedy_names_plain_push(self):
        out = self.flagged_untrailered()
        pushes = re.findall(r"git push[^`\n]*", out)
        self.assertTrue(any(not re.search(r"--force|\s-f\b", push) for push in pushes),
                        "remedy names no git push without a force flag:\n" + out)

    def test_remedy_names_cherry_pick_route(self):
        out = self.flagged_untrailered()
        # A pushed older commit goes onto a new branch by cherry-pick, since an interactive rebase cannot run.
        self.assertIn("cherry-pick", out, "remedy names no cherry-pick route for a pushed older commit:\n" + out)

    def test_valid_red_run_trailer_passes(self):
        for red in (GOOD, "Red-run: python3 lint/test_widgets.py -> 1 failed on abcdef1",
                    "Red-run: python3 lint/test_widgets.py -> 1 failed on " + "a" * 40):
            with self.subTest(red=red):
                self.base()
                self.commit("add widget tests", {self.new_test_path(): TEST_TEXT}, red=red)
                self.assertClean()

    def test_none_with_a_reason_passes(self):
        self.base()
        self.commit("re-point widget fixtures", {self.new_test_path(): TEST_TEXT},
                    red="Red-run: none: re-points fixtures")
        self.assertClean()

    def test_none_without_a_reason_is_flagged(self):
        for red in ("Red-run: none", "Red-run: none:", "Red-run: none:   "):
            with self.subTest(red=red):
                self.base()
                rel = self.new_test_path()
                sha = self.commit("add widget tests", {rel: TEST_TEXT}, red=red)
                self.assertFlagged(sha, "add widget tests", rel)

    def test_malformed_line_beside_a_valid_line_is_flagged(self):
        """One malformed Red-run line flags the commit, whichever line comes first. Each pair is a valid line and a bad one."""
        pairs = (("Red-run: none: re-points fixtures", "Red-run: mutant:  -> 1 failed on SHA"),
                 (VALID_LINE, "Red-run: none"))
        for valid, bad in pairs:
            for order in ((valid, bad), (bad, valid)):
                with self.subTest(order=order):
                    self.base()
                    rel = self.new_test_path()
                    sha = self.commit("add widget tests", {rel: TEST_TEXT}, red=filled(order, self.base_sha))
                    self.assertFlagged(sha, "add widget tests", rel, why="a malformed Red-run line must flag the commit: "
                                       + filled([bad], self.base_sha)[0])

    def test_two_valid_lines_pass(self):
        """Two valid Red-run lines in one message pass. The controls for the malformed-line case."""
        pairs = (("Red-run: none: re-points fixtures", VALID_LINE),
                 (VALID_LINE, "Red-run: mutant: drop the guard -> 1 failed on SHA"),
                 (VALID_LINE, "Red-run: python3 lint/test_gadgets.py -> 2 failed on SHA"))
        for pair in pairs:
            with self.subTest(pair=pair):
                self.base()
                self.commit("add widget tests", {self.new_test_path(): TEST_TEXT}, red=filled(pair, self.base_sha))
                self.assertClean(why="two valid Red-run lines must pass: " + " | ".join(filled(pair, self.base_sha)))

    def test_keyword_typo_line_is_flagged_alone(self):
        """A keyword typo, wrapped or not, is refused, not read as the failed form, even as the only Red-run line."""
        for typo in KEYWORD_TYPOS + WRAPPED_AND_TYPO:
            with self.subTest(typo=typo):
                self.base()
                rel = self.new_test_path()
                sha = self.commit("add widget tests", {rel: TEST_TEXT}, red=filled([typo], self.base_sha))
                self.assertFlagged(sha, "add widget tests", rel,
                                   why="a keyword typo must flag the commit, not pass as a failed form: " + filled([typo], self.base_sha)[0])

    def test_keyword_typo_beside_a_valid_line_is_flagged(self):
        """A keyword typo, wrapped or not, beside a valid line flags the commit. The valid line must not carry the typo through."""
        for typo in KEYWORD_TYPOS + WRAPPED_AND_TYPO:
            with self.subTest(typo=typo):
                self.base()
                rel = self.new_test_path()
                sha = self.commit("add widget tests", {rel: TEST_TEXT},
                                  red=filled([VALID_LINE, typo], self.base_sha))
                self.assertFlagged(sha, "add widget tests", rel,
                                   why="a keyword typo beside a valid line must flag the commit: " + filled([typo], self.base_sha)[0])

    def test_mutant_keyword_with_glued_text_is_flagged(self):
        """The failed form would read a glued keyword as a command. Each of these must flag its commit."""
        for line in PREFIX_BYPASSES:
            with self.subTest(line=line):
                self.base()
                rel = self.new_test_path()
                sha = self.commit("add widget tests", {rel: TEST_TEXT}, red=filled([line], self.base_sha))
                self.assertFlagged(sha, "add widget tests", rel,
                                   why="a mutant keyword with glued text must flag the commit, not pass as a failed form: "
                                       + filled([line], self.base_sha)[0])

    def test_mutant_typo_fail_line_names_the_mutant_form(self):
        """The FAIL line for a refused mutant-like line holds the hint. The remedy line names the form too, so this reads the FAIL line."""
        for typo in MUTANT_TYPOS:
            with self.subTest(typo=typo):
                self.base()
                rel = self.new_test_path()
                sha = self.commit("add widget tests", {rel: TEST_TEXT}, red=filled([typo], self.base_sha))
                out = self.assertFlagged(sha, "add widget tests", rel,
                                         why="a mutant typo must flag the commit: " + filled([typo], self.base_sha)[0])
                fail = [line for line in out.splitlines() if line.startswith("check_red_run: FAIL:") and sha[:7] in line]
                self.assertTrue(fail, "no FAIL line names the commit:\n" + out)
                self.assertIn("Red-run: mutant:", fail[0],
                              "the FAIL line for %s holds no hint naming the mutant form:\n%s" % (typo, out))

    def test_case_variant_key_beside_a_valid_line_is_flagged(self):
        """A Red-run key in another case, or with a space before its colon, is malformed. It flags the commit beside a valid line."""
        for variant in CASE_VARIANT_KEYS:
            with self.subTest(variant=variant):
                self.base()
                rel = self.new_test_path()
                sha = self.commit("add widget tests", {rel: TEST_TEXT}, red=[VALID_NONE, variant])
                self.assertFlagged(sha, "add widget tests", rel,
                                   why="a case-variant Red-run key beside a valid line must flag the commit: " + variant)

    def test_near_miss_key_beside_a_valid_line_is_flagged(self):
        """A key that reads like `Red-run:` but is not is malformed. It flags the commit beside a valid line."""
        for line in NEAR_MISS_KEYS:
            with self.subTest(line=line):
                self.base()
                rel = self.new_test_path()
                sha = self.commit("add widget tests", {rel: TEST_TEXT}, red=filled([VALID_NONE, line], self.base_sha))
                self.assertFlagged(sha, "add widget tests", rel,
                                   why="a near-miss Red-run key beside a valid line must flag the commit: "
                                       + filled([line], self.base_sha)[0])

    def test_lines_that_are_not_the_key_pass(self):
        """Prose that mentions the key mid-line, and a word that only starts like it, are not Red-run lines. The controls for the near-miss cases."""
        for line in NOT_KEY_LINES:
            with self.subTest(line=line):
                self.base()
                self.commit("add widget tests", {self.new_test_path(): TEST_TEXT}, red=[VALID_NONE, line])
                self.assertClean(why="a line that is not a Red-run key must not count as one: " + line)

    def test_real_commands_with_ordinary_first_words_pass(self):
        """Real commands pass as the failed form, including ones whose first word is an ordinary word. The controls for the typo cases."""
        for command in REAL_COMMANDS:
            with self.subTest(command=command):
                self.base()
                self.commit("add widget tests", {self.new_test_path(): TEST_TEXT}, red=filled([command], self.base_sha))
                self.assertClean(why="a real command must pass as the failed form: " + filled([command], self.base_sha)[0])

    def test_mutatest_command_stays_refused(self):
        """A `mutatest` command is a mutat-start word, so it stays refused. The pin for the word rule's second layer."""
        self.base()
        rel = self.new_test_path()
        line = "Red-run: mutatest run -> 1 failed on SHA"
        sha = self.commit("add widget tests", {rel: TEST_TEXT}, red=filled([line], self.base_sha))
        self.assertFlagged(sha, "add widget tests", rel, why="mutatest run must stay refused, not pass as a failed form: " + line)

    def test_zero_failures_is_flagged(self):
        for form in ("Red-run: python3 lint/test_widgets.py -> 0 failed on %s",
                     "Red-run: mutant: drop the guard -> 0 failed on %s"):
            with self.subTest(form=form):
                self.base()  # a real sha, so the zero count is the only cause
                rel = self.new_test_path()
                sha = self.commit("add widget tests", {rel: TEST_TEXT}, red=form % self.base_sha)
                self.assertFlagged(sha, "add widget tests", rel)

    def test_short_or_missing_sha_is_flagged(self):
        for red in ("Red-run: python3 lint/test_widgets.py -> 1 failed on abc123",
                    "Red-run: python3 lint/test_widgets.py -> 1 failed",
                    "Red-run: mutant: drop the guard -> 1 failed on abc123",
                    "Red-run: mutant: drop the guard -> 1 failed"):
            with self.subTest(red=red):
                self.base()
                rel = self.new_test_path()
                sha = self.commit("add widget tests", {rel: TEST_TEXT}, red=red)
                self.assertFlagged(sha, "add widget tests", rel)

    def test_mutant_with_an_empty_mutation_is_flagged(self):
        for form in ("Red-run: mutant:  -> 1 failed on %s", "Red-run: mutant: -> 1 failed on %s",
                     "Red-run: Mutant: -> 1 failed on %s", "Red-run: mutant : -> 1 failed on %s",
                     "Red-run: MUTANT: -> 1 failed on %s"):
            with self.subTest(form=form):
                self.base()
                rel = self.new_test_path()
                sha = self.commit("add widget tests", {rel: TEST_TEXT}, red=form % self.base_sha)
                self.assertFlagged(sha, "add widget tests", rel)

    def test_mutant_with_a_mutation_passes(self):
        """Each spelling of the mutant form passes with a mutation. These are the controls for the empty-mutation case."""
        for form in ("Red-run: mutant: drop the guard -> 1 failed on %s",
                     "Red-run: Mutant: drop the guard -> 1 failed on %s",
                     "Red-run: mutant : drop the guard -> 1 failed on %s",
                     "Red-run: MUTANT: drop the guard -> 1 failed on %s"):
            with self.subTest(form=form):
                self.base()
                self.commit("add widget tests", {self.new_test_path(): TEST_TEXT}, red=form % self.base_sha)
                self.assertClean()

    # Shape only: a mutant line's sha is read for its shape, not its reach. A rebase or cherry-pick rewrites the
    # commit a mutant line names, and a fresh CI clone lacks it, so reach cannot be read there. The two cases
    # here pin that shape-only read, so a later reach check must re-point them.
    def test_mutant_naming_no_commit_passes(self):
        self.base()
        self.assertFalse(self.names_commit("f" * 40))  # scope: the sha names no commit
        self.commit("add widget tests", {self.new_test_path(): TEST_TEXT},
                    red="Red-run: mutant: drop the guard -> 1 failed on " + "f" * 40)
        self.assertClean()

    def test_mutant_naming_an_unmerged_commit_passes(self):
        """The side commit exists in the repo, but no branch HEAD reaches merges it. Shape only, so it passes."""
        self.base()
        self.git("checkout", "-q", "-b", "side")
        side = self.commit("change widget product on side", {PRODUCT_REL: PRODUCT_TEXT})
        self.git("checkout", "-q", "main")
        self.assertTrue(self.names_commit(side))  # scope: the side commit exists
        self.assertFalse(self.reaches_head(side))  # scope: HEAD does not reach it
        self.commit("add widget tests", {self.new_test_path(): TEST_TEXT},
                    red="Red-run: mutant: drop the guard -> 1 failed on " + side)
        self.assertClean()

    def test_mutant_with_a_seven_digit_sha_passes(self):
        """Seven hex digits is the least the mutant form takes. The pair of the six-digit case, which is flagged."""
        self.base()
        self.commit("add widget tests", {self.new_test_path(): TEST_TEXT},
                    red="Red-run: mutant: drop the guard -> 1 failed on " + self.base_sha[:7])
        self.assertClean()

    def test_mutant_naming_an_in_range_commit_passes(self):
        self.base()
        prod = self.commit("change widget product", {PRODUCT_REL: PRODUCT_TEXT})
        self.commit("add widget tests", {self.new_test_path(): TEST_TEXT},
                    red="Red-run: mutant: drop the guard -> 1 failed on " + prod)
        self.assertClean()

    def test_commit_that_only_deletes_test_lines_passes(self):
        rel = "lint/test_trim.py"
        self.base({rel: "def test_a():\n    assert 1\n    assert 2\n"})
        self.commit("trim widget asserts", {rel: "def test_a():\n    assert 1\n"})
        self.assertClean()
        self.base({rel: "def test_b():\n    assert 3\n"})
        self.commit("delete widget test file", {rel: None})
        self.assertClean()

    def test_product_only_commit_passes(self):
        self.base()
        self.commit("change widget product", {PRODUCT_REL: PRODUCT_TEXT})
        self.assertClean()

    def test_test_and_product_in_one_commit_is_flagged(self):
        self.base()
        rel = self.new_test_path()
        sha = self.commit("change widgets and tests", {PRODUCT_REL: PRODUCT_TEXT, rel: TEST_TEXT})
        self.assertFlagged(sha, "change widgets and tests", rel)

    def test_bad_commit_is_named_before_a_good_head(self):
        self.base()
        rel = self.new_test_path()
        bad = self.commit("add widget tests", {rel: TEST_TEXT})
        self.commit("change widget product", {PRODUCT_REL: PRODUCT_TEXT})
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertGap(out, bad, "add widget tests", rel)
        self.assertNotIn("change widget product", out, out)  # only a gap prints a subject; the range is read

    def test_merge_of_a_tested_side_passes(self):
        self.base()
        rel = self.new_test_path()
        self.git("checkout", "-q", "-b", "side")
        self.commit("add widget tests", {rel: TEST_TEXT}, red=GOOD)
        self.git("checkout", "-q", "main")
        self.commit("change widget product", {PRODUCT_REL: PRODUCT_TEXT})
        self.merge("side")  # brings in the test lines, and is not judged itself
        self.assertClean()

    def test_merge_flags_its_untrailered_side_commit_not_the_merge(self):
        self.base()
        rel = self.new_test_path()
        self.git("checkout", "-q", "-b", "side")
        side = self.commit("add widget tests", {rel: TEST_TEXT})
        self.git("checkout", "-q", "main")
        self.commit("change widget product", {PRODUCT_REL: PRODUCT_TEXT})
        self.merge("side")
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertGap(out, side, "add widget tests", rel)
        self.assertNotIn("Merge side", out, out)  # only a gap prints a subject, so the merge stays unnamed

    def test_commit_before_the_check_landed_is_not_judged(self):
        self.base(check=False)
        landed = self.commit("land the red-run check", {CHECK_REL: read_module(), self.new_test_path(): TEST_TEXT})
        self.assertFalse(self.has_file(self.base_sha, CHECK_REL))  # the landing commit's parent lacks the check
        self.assertClean()
        rel = self.new_test_path()
        later = self.commit("add a second widget test", {rel: TEST_TEXT})
        self.assertTrue(self.has_file(landed, CHECK_REL))  # the next commit's parent has the check
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertGap(out, later, "add a second widget test", rel)
        self.assertNotIn(landed[:7], out, out)

    def test_untrailered_test_commit_in_repo_without_check_is_flagged(self):
        """No rollout exemption without the check file at HEAD. The script runs by its absolute path, from the scratch repo."""
        rel, sha = self.scratch_repo_test_commit()
        self.assertFlagged(sha, "add widget tests", rel, script=MODULE, cwd=self.tree)

    def test_trailered_test_commit_in_repo_without_check_passes(self):
        """The same scratch repo, with a valid trailer on its test commit, is green. The script runs by its absolute path."""
        self.scratch_repo_test_commit(red=GOOD)
        self.assertClean(script=MODULE, cwd=self.tree)

    def test_files_that_only_look_like_tests_are_not_judged(self):
        self.base()
        self.commit("add contest helpers", {"src/contest.py": "def contest():\n    return 1\n",
                                            "src/attest.py": "def attest():\n    return 1\n"})
        self.assertClean()

    def test_file_in_a_test_folder_is_a_test_path(self):
        self.base()
        sha = self.commit("add roadmap test helpers", {"tests/helpers.py": "def helper():\n    return 1\n"})
        self.assertFlagged(sha, "add roadmap test helpers", "tests/helpers.py")

    def test_unreadable_base_exits_two_as_unknown(self):
        self.base()
        self.commit("add widget tests", {self.new_test_path(): TEST_TEXT})  # a real finding, so 0 would be wrong
        for args, env in ((["--base", "0" * 40], None), ([], {"BASE_SHA": "1" * 40})):
            with self.subTest(args=args, env=env):
                rc, out = self.lint(args, env)
                self.assertEqual(rc, 2, out)
                self.assertIn("unknown", out.lower(), out)
                self.assertNotIn("Traceback", out, out)

    def test_base_comes_from_base_sha_without_a_flag(self):
        self.base()
        rel = self.new_test_path()
        sha = self.commit("add widget tests", {rel: TEST_TEXT})
        rc, out = self.lint([], {"BASE_SHA": self.base_sha})
        self.assertEqual(rc, 1, out)
        self.assertGap(out, sha, "add widget tests", rel)

    def test_check_reads_the_repo_it_is_run_in(self):
        """The repo comes from the current directory, not from the checkout that holds the script."""
        self.base()
        rel = self.new_test_path()
        sha = self.commit("add widget tests", {rel: TEST_TEXT})
        rc, out = self.lint(script=MODULE, cwd=self.tree)
        self.assertEqual(rc, 1, "the check must read the repo it runs in, not its own checkout:\n" + out)
        self.assertGap(out, sha, "add widget tests", rel)

    def test_root_flag_names_the_repo_to_read(self):
        """--root picks the repo whatever the current directory is. The cwd here is outside any repo."""
        self.base()
        rel = self.new_test_path()
        sha = self.commit("add widget tests", {rel: TEST_TEXT})
        cwd = tempfile.mkdtemp(dir=RUN_FOLDER, prefix="cwd_")
        self.addCleanup(tracked_tree.rm_tree, cwd)
        rc, out = self.lint(["--root", self.tree, "--base", self.base_sha], script=MODULE, cwd=cwd)
        self.assertEqual(rc, 1, out)
        self.assertNotIn("usage", out, out)
        self.assertGap(out, sha, "add widget tests", rel)

    def test_revert_of_a_test_deletion_is_not_judged(self):
        """A revert re-adds the lines it undoes. Its message carries the This reverts commit line, not a trailer."""
        rel = "lint/test_trim.py"
        self.base({rel: "def test_a():\n    assert 1\n    assert 2\n"})
        trim = self.commit("trim widget asserts", {rel: "def test_a():\n    assert 1\n"})
        self.git("revert", "--no-edit", trim)
        self.assertIn("This reverts commit ", self.git("log", "-1", "--format=%B"))  # the case is a revert
        self.assertClean()

    def test_reapply_of_a_revert_is_not_judged(self):
        """A revert of a revert re-adds the test file. It carries the This reverts commit line, not a trailer."""
        rel = self.new_test_path()
        self.base()
        added = self.commit("add widget tests", {rel: TEST_TEXT}, red=GOOD)
        self.git("revert", "--no-edit", added)
        self.git("revert", "--no-edit", "HEAD")  # the reapply: it re-adds the test file
        self.assertIn("This reverts commit ", self.git("log", "-1", "--format=%B"))  # the case is a reapply
        self.assertTrue(self.has_file("HEAD", rel))
        self.assertClean()

    def test_normal_untrailered_commit_after_a_revert_is_still_flagged(self):
        """The revert exemption covers the revert commit alone. A normal test commit after it is still a gap."""
        rel = "lint/test_trim.py"
        self.base({rel: "def test_a():\n    assert 1\n    assert 2\n"})
        trim = self.commit("trim widget asserts", {rel: "def test_a():\n    assert 1\n"})
        self.git("revert", "--no-edit", trim)
        normal = self.new_test_path()
        sha = self.commit("add widget tests", {normal: TEST_TEXT})
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertGap(out, sha, "add widget tests", normal)


def word_of(result):
    """The word of a label_word result: field 0 of its (word, ended_in_colon, upper_env) tuple. A bare string is the
    word itself, so a word row fails on its own word, and the triple test names the shape. Pure."""
    return result[0] if isinstance(result, tuple) else result


class LabelForms(unittest.TestCase):
    """Each LABEL_FORMS row alone and beside a valid line, and the LABEL_WORDS table and the triple of label_word."""

    @classmethod
    def setUpClass(cls):
        cls.check = load_module("check_red_run_label_forms", MODULE)

    def test_form_alone_is_refused_or_passed(self):
        for line, expected, source in LABEL_FORMS:
            line = filled([line], LABEL_SHA)[0]
            with self.subTest(line=line):
                self.assertEqual(self.check.valid_line(line), expected == "valid",
                                 "%s: this line must be %s as a failed form: %s" % (source, expected, line))

    def test_form_beside_a_valid_line_is_refused_or_passed(self):
        for line, expected, source in LABEL_FORMS:
            line = filled([line], LABEL_SHA)[0]
            message = "fixture subject\n\n" + "\n".join(filled([VALID_LINE, line], LABEL_SHA)) + "\n"
            with self.subTest(line=line):
                self.assertEqual(self.check.has_valid_trailer(message), expected == "valid",
                                 "%s: this line must be %s beside a valid line: %s" % (source, expected, line))

    def test_label_word_reads_the_normalised_word(self):
        fn = getattr(self.check, "label_word", None)
        self.assertIsNotNone(fn, "label_word absent: the red-run label has no one normaliser yet")
        for line, word, _upper_env in LABEL_WORDS:
            with self.subTest(line=line):
                self.assertEqual(word_of(fn(line)), word, "label_word(%r) must read the word %r" % (line, word))

    def test_label_word_reads_upper_env(self):
        fn = getattr(self.check, "label_word", None)
        self.assertIsNotNone(fn, "label_word absent: the red-run label has no one normaliser yet")
        for line, _word, upper_env in LABEL_WORDS:
            with self.subTest(line=line):
                self.assertEqual(tuple(fn(line)[2:]), (upper_env,),
                                 "label_word(%r) must carry upper_env %r as its third field" % (line, upper_env))

    def test_label_word_returns_word_colon_and_upper_env(self):
        """label_word returns one triple (word, ended_in_colon, upper_env). The upper-case NAME= exemption reads the
        same stripped token as the word, so one parse serves both."""
        fn = getattr(self.check, "label_word", None)
        self.assertIsNotNone(fn, "label_word absent: the red-run label has no one normaliser yet")
        for line, triple in (("Red-run:", ("", False, False)),
                             ("Red-run: mutant x -> 1 failed on SHA", ("mutant", False, False)),
                             ("Red-run: mutant: x -> 1 failed on SHA", ("mutant", True, False)),
                             ("Red-run: (mutant:) x -> 1 failed on SHA", ("mutant", True, False)),
                             ("Red-run: - MUTATE_ONLY=x python3 t.py -> 1 failed on SHA",
                              ("mutate_only=x", False, True))):
            with self.subTest(line=line):
                got = fn(line)
                self.assertIsInstance(got, tuple,
                                      "label_word must return a (word, ended_in_colon, upper_env) triple, not %r: %s"
                                      % (got, line))
                self.assertEqual(got, triple, "label_word(%r) must be %r" % (line, triple))

    def test_label_parts_is_not_a_second_home(self):
        self.assertFalse(hasattr(self.check, "_label_parts"),
                         "_label_parts is a second home for the label: label_word must hold the parse itself")


class LabelFormHints(Fixture):
    """The mutant hint: a refused form whose text holds `mut` names the mutant form in its FAIL line."""

    def test_refused_mut_form_names_the_mutant_hint(self):
        check = load_module("check_red_run_label_hints", MODULE)
        rows = [filled([line], LABEL_SHA)[0] for line, expected, _source in LABEL_FORMS
                if expected == "refused" and "mut" in line.lower()]
        self.base()  # one commit per row, so one check run reads every form
        shas = [self.commit("label form %d" % index, {self.new_test_path(): TEST_TEXT}, red=line)
                for index, line in enumerate(rows)]
        bad = check.gaps(self.tree, self.base_sha)
        for line, sha in zip(rows, shas):
            fail = [out for out in bad if sha[:7] in out]
            with self.subTest(line=line):
                self.assertTrue(fail, "this line must be flagged before its hint can be read: " + line)
                self.assertIn("Red-run: mutant:", fail[0], "the FAIL line holds no hint naming the mutant form: " + line)


class MainHistory(unittest.TestCase):
    """The history pin: a message origin/main's checker accepts must still pass this checker.

    It reads origin/main's whole history, which CI fetches (fetch-depth 0). A ref it cannot read is unknown, and fails.
    A shallow clone cannot read it all, so the class skips there (SHALLOW_REASON).
    """

    # Main commits that wrote the no-colon mutant line (`Red-run: mutant A ...`). Main's history cannot change, so each
    # stays exempt here. The checker judges a branch's own range only, so the pin is the one place main's commits are
    # re-judged. No other main commit is exempt.
    GRANDFATHERED = frozenset(("408340997f6b913294cc44691eab705caf80a6e0",
                               "1762ec79f2f44d35720e2f32b8ee7ccec1291db4",
                               "b2f0fb754befe1667228529d4dc266fb476e3315"))

    @classmethod
    def setUpClass(cls):
        if shallow_clone():
            raise unittest.SkipTest(SHALLOW_REASON)
        cls.records = main_messages()
        cls.baseline = load_baseline(RUN_FOLDER)
        cls.current = load_module("check_red_run_under_test", MODULE)
        cls.base_name = base_verdict_name(cls.baseline)
        if not hasattr(cls.current, VERDICT):
            raise AssertionError("this checker has no %s: re-point the pin" % VERDICT)

    def test_pin_reads_every_non_merge_message_on_main(self):
        counted = int(git_text("rev-list", "--no-merges", "--count", BASE_REF))
        self.assertEqual(len(self.records), counted, "the pin must read every non-merge message on origin/main")

    def test_no_valid_trailer_on_main_turns_invalid(self):
        judged = [record for record in self.records if record[0] not in self.GRANDFATHERED]
        accepted = [record for record in judged if verdict(self.baseline, self.base_name, record[2])]
        self.assertGreater(len(accepted), 0, "scope: origin/main holds no valid trailer, so the pin checks nothing")
        lost = lost_trailers(self.baseline, self.current, judged)
        self.assertEqual(lost, [], "a valid trailer on origin/main turns invalid under this checker:\n" + "\n".join(lost))

    def test_pin_flags_a_message_the_checker_refuses(self):
        """A checker that refuses every message trips the pin, so a green pin means the comparison ran."""
        class RefusesAll:
            def has_valid_trailer(self, message):
                return False

        lost = lost_trailers(self.baseline, RefusesAll(), self.records)
        self.assertGreater(len(lost), 0, "a checker that refuses every message must trip the pin")


class ShallowPin(Fixture):
    """In a shallow clone the history pin skips, so a cut-short history cannot pass it. A depth-1 clone runs it."""

    def test_shallow_clone_skips_the_pin(self):
        tracked_tree.copy_tracked(self.tree, "testing")  # the module imports tracked_tree from testing/
        shutil.copyfile(os.path.abspath(__file__), os.path.join(self.tree, "lint", "test_check_red_run.py"))
        self.git("add", "-A")  # the copied lint, hooks and testing folders, and this module
        self.commit("fixture base", {})
        self.commit("fixture tip", {"README.md": "tip\n"})  # a second commit, so depth 1 cuts the history
        clone_parent = tempfile.mkdtemp(dir=RUN_FOLDER, prefix="shallow_")
        self.addCleanup(tracked_tree.rm_tree, clone_parent)
        clone = os.path.join(clone_parent, "clone")
        done = subprocess.run(["git", "clone", "-q", "--depth", "1", pathlib.Path(self.tree).as_uri(), clone],
                              capture_output=True, text=True, env=GIT_ENV)
        self.assertEqual(done.returncode, 0, done.stderr)
        scope = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=clone,
                               capture_output=True, text=True, env=GIT_ENV).stdout.strip()
        self.assertEqual(scope, "true", "scope: the clone must be shallow")
        done = subprocess.run([sys.executable, os.path.join(clone, "lint", "test_check_red_run.py"), "-v", "MainHistory"],
                              cwd=clone, capture_output=True, text=True, encoding="utf-8", errors="replace", env=GIT_ENV)
        out = done.stdout + done.stderr
        self.assertEqual(done.returncode, 0, "the pin must skip in a shallow clone, not fail:\n" + out)
        self.assertRegex(out, r"skipped .*shallow clone", "the pin must skip, naming the shallow clone, not run:\n" + out)


if __name__ == "__main__":
    unittest.main()
