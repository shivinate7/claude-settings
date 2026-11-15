#!/usr/bin/env python3
"""Shard pins for hooks/test_install_src.sh, and the job checks step that runs this file.

The suite contract the builder implements:
  INSTALL_SRC_SHARD=i/k (1-based i, k >= 1) runs only the cases whose position in the file's `run` list
  satisfies (pos - 1) % k == i - 1: round-robin in run order. Unset runs every case.
  `--list` prints the selected case names, one per line, runs nothing, and exits 0.
  A bad value (0/2, 3/2, x, or an empty value) exits non-zero, writes a message to stderr that names INSTALL_SRC_SHARD,
  and selects no case.

Every suite call here passes --list, so no case runs. On the old code `--list` is a name filter that
matches no case, which is why the shard cases are red there. A bad value run without --list would run
all 174 cases on the old code.

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
import _test_temp  # noqa: E402  the one home of the test temp folder (test-temp-standard)

REPO = os.path.abspath(os.path.join(HERE, ".."))
SUITE = os.path.join(REPO, "hooks", "test_install_src.sh")
CHECKS = os.path.join(REPO, ".github", "workflows", "checks.yml")
RUN_CMD = "python3 lint/test_install_src_shards.py"  # the run line of the job checks step that runs this file
SHARD_ENV = "INSTALL_SRC_SHARD"
# Env the suite reads from its caller. Stripped from every call, so the caller's shell cannot change what a call selects.
STRIPPED_ENV = (SHARD_ENV, "INSTALL_SH_UNDER_TEST", "SESSION_START_SH_UNDER_TEST")
# A run line may repeat only as a named exception: name -> reason. Empty on ae13fcab, where no run line repeats.
KNOWN_DUPLICATE_RUNS = {}
NAME = re.compile(r"[A-Za-z_]\w*")


def run_names():
    """The case names in run_cases, the suite's one run list, in file order. A repeated name stays repeated. A `run` word
    elsewhere (a heredoc, a quoted block) is text: the suite never calls it, so it names no case."""
    with open(SUITE, encoding="utf-8") as f:
        m = re.search(r"^run_cases\(\) \{\n(.*?)^\}\n", f.read(), re.M | re.S)
    return re.findall(r"^run (\S+)$", m.group(1), re.M) if m else []


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


class ShardListsEveryCaseOnce(unittest.TestCase):
    def test_every_run_line_names_one_defined_function(self):
        # Control, green on the old code: the run list and the functions it names agree.
        runs = run_names()
        self.assertTrue(runs, "the suite's run_cases lists no case")
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


class ShardPinsRunInChecksJob(unittest.TestCase):
    def test_checks_job_runs_this_file_in_one_step(self):
        # Scope first: the job exists, so a missing step is not read as a missing job.
        with open(CHECKS, encoding="utf-8") as f:
            block = job_block(f.read(), "checks")
        self.assertIsNotNone(block, "checks.yml has no checks job")
        runs = [s for s in step_blocks(block) if step_key(s, "run") == RUN_CMD]
        self.assertEqual(len(runs), 1, f"job checks runs {RUN_CMD!r} in {len(runs)} steps, want one")


if __name__ == "__main__":
    unittest.main()
