#!/usr/bin/env python3
"""Shared plumbing for hooks/mutate_guard.py and janitor/mutate_sweep.py.

Both files run the same shape of mutation test: apply one literal-string replacement to a
source file, run a fixture suite against the mutated copy, and read the suite's own FAIL lines
back to tell KILLED from SURVIVED from WRONG CAUSE (a mutant that dies on some case OTHER than
the one its label names, which proves nothing about the rule that label claims to break -- see
either caller's module docstring for the full argument). This module holds the five pieces that
were byte-for-byte identical, or near enough, between the two files:

- `safe_name`: label -> filesystem-safe stem.
- `job_count`: MUTATE_JOBS, else the CPU count, at least one.
- `run_suite`: spawn one suite subprocess and scan its combined stdout+stderr for FAIL lines.
- `check_stale`: the anchor-text precheck, run before any suite starts, so a mutation whose
  anchor moved on fails loudly in the first second rather than being silently skipped.
- `run_mutants`: the ThreadPoolExecutor verdict loop (SURVIVED / WRONG CAUSE / KILLED) and the
  tally line at the end.

What stays with each caller, because it differs: `MUTATIONS` itself, `mutation_parts` (the two
files disagree on field order and on how strictly they validate `target`), and how a mutated
copy is laid out on disk (`hooks/mutate_guard.py` writes one file per mutant into a shared work
directory; `janitor/mutate_sweep.py` builds a whole two-package scaffold per mutant). Each caller
therefore supplies its own `run_one(entry, work) -> (label, code, red, required)` callback and
passes it to `run_mutants`.
"""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor


def safe_name(label: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in label)[:60]


def job_count() -> int:
    """How many suites to run at once: MUTATE_JOBS, else the CPU count, at least one."""
    try:
        wanted = int(os.environ.get("MUTATE_JOBS", "") or 0)
    except ValueError:
        wanted = 0
    return max(1, wanted or os.cpu_count() or 1)


def run_suite(argv, env, timeout=1200):
    """Run one suite subprocess. Return (exit code, FAIL lines from stdout+stderr).

    Scanned together and by substring, not `stdout` alone with `startswith`: hooks/test_guard.py
    prints its own hand-rolled "FAIL ..." lines to stdout only, and janitor/test_sweep.py's plain
    `unittest.main` prints its progress and failure headings to stderr instead. Neither suite's
    passing output puts the substring "FAIL" anywhere but at the start of an actual failure line,
    so scanning both streams for the substring catches either shape without missing anything.
    """
    result = subprocess.run(
        argv, capture_output=True, text=True, env=env, timeout=timeout,
    )
    red = [
        line for line in (result.stdout + "\n" + result.stderr).splitlines()
        if "FAIL" in line
    ]
    return result.returncode, red


def check_stale(entries_info, sources) -> bool:
    """The stale-anchor precheck, run before any suite starts.

    `entries_info` is a list of (label, target, old, required) tuples, already pulled out of each
    caller's own MUTATIONS by its own `mutation_parts`. Prints one ERROR line per problem and
    returns False if any target is unknown, any anchor text is not found verbatim in that
    target's current source (a STALE mutation: the source moved on and it no longer proves
    anything), or any entry carries no required case name.
    """
    ok = True
    for label, target, old, required in entries_info:
        if target not in sources:
            print("ERROR unknown mutation target %r: %s" % (target, label))
            ok = False
            continue
        if old not in sources[target]:
            print("ERROR stale mutation, anchor text not found: %s" % label)
            ok = False
            continue
        if not required:
            print("ERROR mutation carries no required case name: %s" % label)
            ok = False
    return ok


def run_mutants(entries, run_one, work):
    """Run every entry's mutant in parallel and print the SURVIVED / WRONG CAUSE / KILLED verdict
    line for each, plus the tally at the end.

    `run_one(entry, work) -> (label, code, red, required)` is supplied by the caller: it applies
    one mutation, runs its suite however that caller lays a mutant out on disk, and returns the
    suite's exit code and FAIL lines alongside the label and the required case name. Order of the
    printed verdicts matches the order of `entries`. Returns (survivors, wrong_cause).
    """
    jobs = job_count()
    print("%d mutations, %d at a time" % (len(entries), jobs))
    survivors = 0
    wrong_cause = 0
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(run_one, entry, work) for entry in entries]
        for future in futures:
            label, code, red, required = future.result()
            if code == 0 or not red:
                survivors += 1
                print("SURVIVED    %-62s %2d red" % (label, len(red)), flush=True)
            elif not any(required in line for line in red):
                wrong_cause += 1
                print("WRONG CAUSE %-62s %2d red, missing %r" % (
                    label, len(red), required), flush=True)
            else:
                print("KILLED      %-62s %2d red" % (label, len(red)), flush=True)
    print()
    killed = len(entries) - survivors - wrong_cause
    print("%d of %d mutations killed (%d survived, %d wrong cause)" % (
        killed, len(entries), survivors, wrong_cause))
    return survivors, wrong_cause


if __name__ == "__main__":
    sys.exit("hooks/mutate_lib.py is a library, imported by hooks/mutate_guard.py and "
              "janitor/mutate_sweep.py -- it is not run directly.")
