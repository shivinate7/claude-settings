#!/usr/bin/env python3
"""Selects the test files a draft lane PR touches, for .github/workflows/lane-touched-tests.yml.

Input (env): BASE_SHA, the PR's base commit. The checkout is at HEAD.
Output: the lines `files=<JSON list>` and `any=<true|false>`, written to $GITHUB_OUTPUT (stdout when unset).
Stdout also names every touched path and what became of it, so the run log shows each decision.

A touched path selects:
  a test file (patterns TEST_PATTERNS)                                       -> itself
  dir/x.py                                                                   -> dir/test_x.py
  dir/x.mjs, dir/x.js                                                        -> dir/x.test.{mjs,js}, dir/tests/x.test.{mjs,js}
  any non-.md path under skills/plain-english-map/                           -> every test in its tests folder
  any non-.md, non-test path under a folder named tests                      -> every test under that folder
Each selected test then lands in one of three places, each printed with its reason, none dropped silently:
  HEAVY        the batch shards it in its own jobs; running it per lane push is a cost blow-up
  NEEDS_SETUP  needs a browser or a tool this workflow does not install, or runs on one OS only
  run          listed in files=
An unreadable diff (no BASE_SHA, git fails) exits 1 and writes no output (decision ci-unknown-is-red).
"""
import fnmatch
import json
import os
import subprocess
import sys

# Test-file name patterns, matched on the file's own name.
TEST_PATTERNS = ("*.test.mjs", "*.test.js", "test_*.mjs", "test_*.py", "test_*.sh", "*.test.sh")

# The suites checks.yml runs in shard jobs or under a step cap of its own (glob -> reason).
HEAVY = {
    "hooks/test_guard.py": "heavy: runs in the batch's shard jobs (GUARD_SHARD)",
    "merge/test_merge.py": "heavy: runs in the batch's shard jobs (MERGE_SHARD)",
    "janitor/test_sweep.py": "heavy: runs in the batch's checks-windows-sweep job",
    "hooks/test_install_src.sh": "heavy: runs in the batch's shell-macos job under its own step cap",
}

# Suites that need a browser or a tool this workflow does not install (glob -> reason).
NEEDS_SETUP = {
    "*/tests/page.test.mjs": "needs Playwright and Chromium; runs in checks-shoot or checks-guard on Linux only",
    "skills/waiting-page/tests/test_check_designs.mjs": "needs Playwright and Chromium; runs in checks-guard on Linux only",
    "lint/test_shoot.mjs": "needs Playwright and Chromium; runs in checks-shoot on Linux only",
    "lint/test_ios_ship.sh": "needs macOS tooling (bin/ios-ship); runs in shell-macos only",
    "lint/test_sim_test.sh": "needs macOS tooling (bin/sim-test); runs in shell-macos only",
}

MAP_DIR = "skills/plain-english-map/"
MAP_TESTS = MAP_DIR + "tests/"


def fail(message):
    print(f"touched-tests: {message}", file=sys.stderr)
    sys.exit(1)


def git(*args):
    r = subprocess.run(["git", *args], capture_output=True)
    if r.returncode:
        fail(f"git {args[0]} failed: {r.stderr.decode(errors='replace').strip()}")
    return r.stdout.decode(errors="replace")


def is_test(path):
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in TEST_PATTERNS)


def reason(path, table):
    for glob, why in table.items():
        if fnmatch.fnmatchcase(path, glob):
            return why
    return None


def candidates(path, tracked):
    """The test files `path` selects, from the tracked paths at HEAD."""
    if is_test(path):
        return {path}
    found = set()
    directory, _, name = path.rpartition("/")
    prefix = directory + "/" if directory else ""
    stem, dot, ext = name.rpartition(".")
    if dot and ext == "py":
        found.add(f"{prefix}test_{stem}.py")
    elif dot and ext in ("mjs", "js"):
        for test_ext in ("mjs", "js"):
            found.add(f"{prefix}{stem}.test.{test_ext}")
            found.add(f"{prefix}tests/{stem}.test.{test_ext}")
    if not path.endswith(".md"):
        if path.startswith(MAP_DIR):
            found |= {t for t in tracked if t.startswith(MAP_TESTS) and is_test(t)}
        parts = path.split("/")
        if "tests" in parts[:-1]:
            folder = "/".join(parts[: parts.index("tests") + 1]) + "/"
            found |= {t for t in tracked if t.startswith(folder) and is_test(t)}
    return {c for c in found if c in tracked}


def write_outputs(files):
    lines = f"files={json.dumps(files)}\nany={'true' if files else 'false'}\n"
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with open(target, "a", encoding="utf-8", newline="\n") as f:
            f.write(lines)
    else:
        sys.stdout.write(lines)


def main():
    base = os.environ.get("BASE_SHA", "").strip()
    if not base:
        fail("BASE_SHA is not set: the diff is unknown, so no test list can be trusted")
    touched = git("diff", "--name-only", "--no-renames", "-z", f"{base}...HEAD").split("\0")
    tracked = set(git("ls-tree", "-r", "--name-only", "-z", "HEAD").split("\0")) - {""}
    touched = sorted(p for p in touched if p and p in tracked)
    selected = set()
    for path in touched:
        found = sorted(candidates(path, tracked))
        print(f"touched {path} -> {', '.join(found) if found else 'no test file maps to it'}")
        selected |= set(found)
    files = []
    for test in sorted(selected):
        why = reason(test, HEAVY) or reason(test, NEEDS_SETUP)
        if why:
            print(f"skip {test}: {why}")
        else:
            print(f"run {test}")
            files.append(test)
    write_outputs(files)


if __name__ == "__main__":
    main()
