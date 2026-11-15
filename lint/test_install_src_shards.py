#!/usr/bin/env python3
"""Shard pins for hooks/test_install_src.sh, and the shell-macos matrix in .github/workflows/checks.yml.

The suite contract the builder implements:
  INSTALL_SRC_SHARD=i/k (1-based i, k >= 1) runs only the cases whose position in the file's `run` list
  satisfies (pos - 1) % k == i - 1: round-robin in run order. Unset runs every case.
  `--list` prints the selected case names, one per line, runs nothing, and exits 0.
  A bad value (0/2, 3/2, x, or an empty value) exits non-zero, writes a message to stderr that names INSTALL_SRC_SHARD,
  and selects no case.

Every suite call here passes --list, so no case runs. On the old code `--list` is a name filter that
matches no case, which is why the shard cases are red there. A bad value run without --list would run
all 174 cases on the old code.

The shell-macos pins read the job with lint/workflow_steps.py. The shape they accept: a `strategy.matrix`
of the shards i/k for 1 <= i <= k; the install step takes its shard from its own step `env`; and every
other run step of the job keeps its name and run string, and its `if` is its original condition with the
matrix-leg test appended: `(S) && C && matrix.<key> == 'i/k'` for `(S) && C`, and `(S) && matrix.<key> == 'i/k'`
for a bare scope condition S. So every step's scope prefix stays `(S)`, the one condition test_windows_split reads.

Run with:  python3 lint/test_install_src_shards.py -v
"""
import os
import re
import shutil
import subprocess
import sys
import unittest
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from workflow_steps import job_block, step_blocks, step_key  # noqa: E402  the one home of the step parser
from test_windows_split import paren_prefix, unwrap  # noqa: E402  the one home of the scope prefix reader (G)
import _test_temp  # noqa: E402  the one home of the test temp folder (test-temp-standard)

REPO = os.path.abspath(os.path.join(HERE, ".."))
SUITE = os.path.join(REPO, "hooks", "test_install_src.sh")
CHECKS = os.path.join(REPO, ".github", "workflows", "checks.yml")
SHARD_ENV = "INSTALL_SRC_SHARD"
# Env the suite reads from its caller. Stripped from every call, so the caller's shell cannot change what a call selects.
STRIPPED_ENV = (SHARD_ENV, "INSTALL_SH_UNDER_TEST", "SESSION_START_SH_UNDER_TEST")
# A run line may repeat only as a named exception: name -> reason. Empty on ae13fcab, where no run line repeats.
KNOWN_DUPLICATE_RUNS = {}
NAME = re.compile(r"[A-Za-z_]\w*")
# The leg test a run step's `if` ends with: `${{ <scope prefix and original condition> && matrix.<key> == '<i/k>' }}`.
GATE = re.compile(r"\$\{\{ (.*) && matrix\.(\w+) == '([^']*)' \}\}")


def leg_gate(orig, key, leg):
    """The `if` of a run step on matrix leg `key` == `leg`, for its original condition `orig`. A bare scope condition
    takes its parentheses first, so its scope prefix is `(S)`; `(S) && C` keeps its prefix and gets the leg test appended."""
    base = f"({orig})" if orig == SCOPE_ORIG else orig
    return f"${{{{ {base} && matrix.{key} == '{leg}' }}}}"

SCOPE_ORIG = "needs.scope.outputs.shell_macos == 'true' || github.event_name != 'pull_request'"
SCOPE_CODE_ORIG = f"({SCOPE_ORIG}) && needs.scope.outputs.code == 'true'"
INSTALL_RUN = "sh hooks/test_install_src.sh"
INSTALL_NAME = "install.sh checkout-detection suite"
INSTALL_IF = f"${{{{ {SCOPE_CODE_ORIG} }}}}"
# Every run step of shell-macos but the install step, as ae13fcab has it: (name, run string or None for a block
# scalar, original condition). Each keeps its name and run string, and gets one matrix-leg gate.
OTHER_STEPS = [
    ("Report the shell this job actually runs", None, SCOPE_ORIG),
    ("Shell syntax check, install.sh", "bash -n install.sh", SCOPE_ORIG),
    ("install_from_main suite", "sh merge/test_install_from_main.sh", SCOPE_CODE_ORIG),
    ("ios-ship fixture suite (/bin/bash 3.2)", "/bin/bash lint/test_ios_ship.sh", SCOPE_CODE_ORIG),
    ("ios-ship fixture suite (bash on PATH)", "bash lint/test_ios_ship.sh", SCOPE_CODE_ORIG),
    ("sim-test fixture suite (/bin/bash 3.2)", "/bin/bash lint/test_sim_test.sh", SCOPE_CODE_ORIG),
    ("sim-test fixture suite (bash on PATH)", "bash lint/test_sim_test.sh", SCOPE_CODE_ORIG),
    ("duo-fold fixture suite (/bin/bash 3.2)", "/bin/bash lint/test_duo_fold.sh", SCOPE_CODE_ORIG),
    ("duo-fold fixture suite (bash on PATH)", "bash lint/test_duo_fold.sh", SCOPE_CODE_ORIG),
]


def run_names():
    """The `run X` lines of the suite, in file order. A repeated name stays repeated."""
    with open(SUITE, encoding="utf-8") as f:
        return re.findall(r"^run (\S+)$", f.read(), re.M)


def defined_functions():
    with open(SUITE, encoding="utf-8") as f:
        return set(re.findall(r"^(?:function\s+)?([A-Za-z_]\w*)\s*\(\s*\)", f.read(), re.M))


def list_cases(shard=None, suite=SUITE):
    """The suite run with --list, under INSTALL_SRC_SHARD=shard when given. -> (exit code, case names, stdout, stderr).

    Names are the identifier lines of stdout. The summary line the old code prints is not one. `suite` is the script run.
    """
    env = {k: v for k, v in os.environ.items() if k not in STRIPPED_ENV}
    if shard is not None:
        env[SHARD_ENV] = shard
    p = subprocess.run(["sh", suite, "--list"], cwd=REPO, env=env, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True)
    names = [ln.strip() for ln in p.stdout.splitlines() if NAME.fullmatch(ln.strip())]
    return p.returncode, names, p.stdout, p.stderr


def under(text, key, indent=4):
    """The lines under the `key:` line at `indent` spaces, up to the next key at that indent or less. '' when absent."""
    lines = text.splitlines()
    for n, line in enumerate(lines):
        if line.rstrip() == " " * indent + key + ":":
            body = []
            for nxt in lines[n + 1:]:
                if nxt.strip() and not nxt.lstrip().startswith("#") and len(nxt) - len(nxt.lstrip(" ")) <= indent:
                    break
                body.append(nxt)
            return "\n".join(body)
    return ""


def shard_values(matrix):
    """The i/k values under a matrix, as (i, k) pairs in file order."""
    return [(int(i), int(k)) for i, k in re.findall(r"(\d+)/(\d+)", matrix)]


def matrix_keys(matrix):
    """The key names a matrix holds, at any depth under `matrix:`."""
    return set(re.findall(r"^\s*(?:-\s+)?(\w+):", matrix, re.M))


class ShardListsEveryCaseOnce(unittest.TestCase):
    def test_every_run_line_names_one_defined_function(self):
        # Control, green on the old code: the run list and the functions it names agree.
        runs = run_names()
        self.assertTrue(runs, "the suite has no `run X` line")
        self.assertEqual(sorted(set(runs) - defined_functions()), [], "a run line names no defined function")

    def test_a_run_line_repeats_only_as_a_named_exception(self):
        # Control, green on the old code: no run line repeats, and KNOWN_DUPLICATE_RUNS is empty.
        counts = Counter(run_names())
        self.assertEqual(sorted(n for n, c in counts.items() if c > 1), sorted(KNOWN_DUPLICATE_RUNS),
                         "a run line repeats without a named exception in KNOWN_DUPLICATE_RUNS")

    def test_unset_list_names_every_case_in_run_order(self):
        runs = run_names()
        code, names, _, err = list_cases()
        self.assertEqual(code, 0, f"--list with no shard set exited {code}: {err.strip()[-200:]}")
        self.assertEqual(names, runs,
                         f"--list with no shard set named {len(names)} cases, want the {len(runs)} run lines in file order")

    def test_shards_list_each_case_exactly_once(self):
        runs = run_names()
        for k in (1, 2, 3):
            with self.subTest(k=k):
                listed = []
                for i in range(1, k + 1):
                    code, names, _, err = list_cases(f"{i}/{k}")
                    self.assertEqual(code, 0, f"shard {i}/{k}: --list exited {code}")
                    # Round-robin in run order: shard i holds the 0-based run lines i-1, i-1+k, ...
                    self.assertEqual(names, runs[i - 1::k],
                                     f"shard {i}/{k} named {len(names)} cases, want its round-robin cases")
                    listed += names
                self.assertEqual(sorted(n for n, c in Counter(listed).items() if c > 1), [],
                                 f"k={k}: a case is in two shards")
                self.assertEqual(sorted(listed), sorted(runs), f"k={k}: the shards do not cover the run list")

    def test_a_shard_past_the_case_count_is_empty_and_exits_zero(self):
        runs = run_names()
        k = len(runs) + 1
        code, names, _, err = list_cases(f"1/{k}")
        self.assertEqual(code, 0, f"shard 1/{k}: --list exited {code}")
        self.assertEqual(names, runs[:1], f"shard 1/{k} named {len(names)} cases, want the first case alone")
        code, names, _, err = list_cases(f"{k}/{k}")
        self.assertEqual(code, 0, f"shard {k}/{k}: --list exited {code}")
        self.assertEqual(names, [], f"spare shard {k}/{k} named {len(names)} cases, want none")


class ShardsAreBalancedByCount(unittest.TestCase):
    def test_shards_are_balanced_by_count(self):
        runs = run_names()
        for k in (2, 3, 4):
            with self.subTest(k=k):
                counts = []
                for i in range(1, k + 1):
                    code, names, _, err = list_cases(f"{i}/{k}")
                    self.assertEqual(code, 0, f"shard {i}/{k}: --list exited {code}")
                    counts.append(len(names))
                # Scope first: the shards must split the whole list. Empty shards have a spread of 0 and say nothing.
                self.assertEqual(sum(counts), len(runs),
                                 f"k={k}: the shards hold {sum(counts)} of {len(runs)} cases: nothing is split")
                self.assertLessEqual(max(counts) - min(counts), 1, f"k={k}: shard counts {counts} differ by more than 1")


class BadShardValueRunsNothing(unittest.TestCase):
    BAD_VALUES = ("0/2", "3/2", "x", "")

    def test_each_bad_value_exits_non_zero_names_the_variable_and_selects_no_case(self):
        for value in self.BAD_VALUES:
            with self.subTest(value=value):
                code, names, _, err = list_cases(value)
                self.assertNotEqual(code, 0, f"{SHARD_ENV}={value} exited 0")
                self.assertIn(SHARD_ENV, err, f"{SHARD_ENV}={value}: the stderr message does not name the variable")
                self.assertEqual(names, [], f"{SHARD_ENV}={value} still selected {len(names)} cases")


class ShellMacosRunsTheShardsByMatrix(unittest.TestCase):
    def setUp(self):
        with open(CHECKS, encoding="utf-8") as f:
            self.block = job_block(f.read(), "shell-macos") or ""
        self.assertTrue(self.block, "checks.yml has no shell-macos job")
        self.steps = step_blocks(self.block)
        self.install = [s for s in self.steps if step_key(s, "run") == INSTALL_RUN]
        self.matrix = under(under(self.block, "strategy"), "matrix", 6)

    def test_the_steps_keep_their_names_run_strings_and_install_condition(self):
        # Control, green on the old code: the shape adds a gate and a step env, and renames and rewrites nothing else.
        self.assertEqual(len(self.install), 1, "shell-macos does not run the install suite in exactly one step")
        self.assertEqual(step_key(self.install[0], "name"), INSTALL_NAME, "the install step was renamed")
        self.assertEqual(step_key(self.install[0], "if"), INSTALL_IF, "the install step's condition changed")
        by_name = {step_key(s, "name"): s for s in self.steps}
        for name, run, _orig in OTHER_STEPS:
            with self.subTest(step=name):
                self.assertIn(name, by_name, "the step is gone or renamed")
                if run is not None:
                    self.assertEqual(step_key(by_name[name], "run"), run, "the run string changed")

    def test_the_job_sets_no_job_level_env(self):
        # Control, green on the old code: the shard comes from one step's env, since a job-level env reaches every step.
        self.assertNotRegex(self.block, r"(?m)^    env:", "shell-macos sets a job-level env: every step takes it")

    def test_shell_macos_runs_the_suite_once_per_shard_by_matrix(self):
        strategy = under(self.block, "strategy")
        self.assertTrue(strategy.strip(), "shell-macos has no strategy: the suite runs once, not once per shard")
        self.assertTrue(self.matrix.strip(), "shell-macos strategy has no matrix")
        pairs = shard_values(self.matrix)
        self.assertTrue(pairs, "the matrix holds no i/k shard value")
        totals = {k for _, k in pairs}
        self.assertEqual(len(totals), 1, f"the matrix shards name more than one total: {sorted(totals)}")
        k = totals.pop()
        self.assertGreaterEqual(k, 2, "the matrix holds one shard, so nothing is split")
        self.assertEqual(sorted(i for i, _ in pairs), list(range(1, k + 1)),
                         f"the matrix does not hold shards 1..{k} of {k}, once each")

    def test_the_install_step_takes_its_shard_from_step_env(self):
        self.assertEqual(len(self.install), 1, "shell-macos does not run the install suite in exactly one step")
        env = under(self.install[0], "env", 8)
        m = re.search(r"^\s+INSTALL_SRC_SHARD:\s*\$\{\{\s*matrix\.(\w+)\s*\}\}\s*$", env, re.M)
        self.assertIsNotNone(m, "the install step does not set INSTALL_SRC_SHARD from a matrix value in its own step env")
        self.assertIn(m.group(1), matrix_keys(self.matrix),
                      f"INSTALL_SRC_SHARD reads matrix.{m.group(1)}, which the matrix does not hold")

    def test_the_other_run_steps_run_on_exactly_one_leg(self):
        legs = {f"{i}/{k}" for i, k in shard_values(self.matrix)}
        keys = matrix_keys(self.matrix)
        others = [s for s in self.steps if step_key(s, "run") not in (None, INSTALL_RUN)]
        # Scope first: the pin lists every run step of the job, so a step added later must be listed and gated too.
        self.assertEqual(sorted(step_key(s, "name") for s in others), sorted(n for n, _, _ in OTHER_STEPS),
                         "the run steps of shell-macos other than the install step changed: list and gate each one")
        by_name = {step_key(s, "name"): s for s in others}
        for name, _run, orig in OTHER_STEPS:
            with self.subTest(step=name):
                cond = step_key(by_name[name], "if") or ""
                m = GATE.fullmatch(cond)
                self.assertIsNotNone(m, f"{name!r} has no matrix-leg test, so it runs on every leg")
                key, leg = m.group(2), m.group(3)
                self.assertIn(key, keys, f"{name!r}: the gate reads matrix.{key}, which the matrix does not hold")
                self.assertIn(leg, legs, f"{name!r}: the gate names {leg!r}, which is no matrix value")
                self.assertEqual(cond, leg_gate(orig, key, leg),
                                 f"{name!r}: the gate is not the one shape (the leg test appended to the original condition)")

    def test_every_shell_macos_step_has_one_scope_prefix(self):
        # Control shape read by test_windows_split (read_scope_condition): the scope prefix of every step's `if` is one
        # condition. A gate that wraps the original condition gives the scoped steps the prefix `(S) && C`, so they disagree.
        self.assertTrue(self.steps, "shell-macos has no steps")
        conds = {(step_key(s, "name") or step_key(s, "uses")): step_key(s, "if") for s in self.steps}
        self.assertEqual(sorted(n for n, c in conds.items() if c is None), [],
                         "a shell-macos step has no `if`, so it carries no scope condition")
        prefixes = {paren_prefix(unwrap(c)) or unwrap(c) for c in conds.values()}
        self.assertEqual(sorted(prefixes), [SCOPE_ORIG],
                         "the shell-macos steps' scope prefixes are not the one scope condition")


class ListCountsOnlyExecutedCalls(unittest.TestCase):
    # Two `run` words that are no call: one in a heredoc, one in a `: '...'` block (a quoted no-op).
    GHOSTS = "\n: <<'GHOST_HEREDOC'\nrun ghost_heredoc\nGHOST_HEREDOC\n: '\nrun ghost_quoted\n'\n"

    def test_a_run_word_in_a_heredoc_or_quoted_block_is_not_listed(self):
        # Red on 7c0ddeb8: --list read every `run X` text line, so both ghosts were listed (176 names, not 174).
        # The oracle is the real suite's --list, which names the calls it makes and no others.
        with open(SUITE, encoding="utf-8") as f:
            text = f.read()
        self.assertEqual(text.count("\nset -u\n"), 1, "the fixture: the suite has one `set -u` line to insert after")
        folder = _test_temp.run_folder()
        self.addCleanup(shutil.rmtree, folder, True)
        copy = os.path.join(folder, "test_install_src_ghosts.sh")
        with open(copy, "w", encoding="utf-8") as f:
            f.write(text.replace("\nset -u\n", "\nset -u\n" + self.GHOSTS, 1))
        code, real, _, err = list_cases()
        self.assertEqual(code, 0, f"the real suite's --list exited {code}: {err.strip()[-200:]}")
        code, copied, _, err = list_cases(suite=copy)
        self.assertEqual(code, 0, f"the copy's --list exited {code}: {err.strip()[-200:]}")
        self.assertEqual([n for n in copied if "ghost" in n], [],
                         "--list names a `run` word that is no call the suite makes")
        self.assertEqual(copied, real, "the copy's --list differs from the real suite's, with no ghost name in it")


if __name__ == "__main__":
    unittest.main()
