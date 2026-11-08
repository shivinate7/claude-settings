#!/usr/bin/env python3
"""Selects the test files a draft lane PR touches, for .github/workflows/lane-touched-tests.yml.

Input (env): BASE_SHA, the PR's base commit. The checkout is at HEAD.
Output: lines written to $GITHUB_OUTPUT (stdout when unset):
  files, any                    every test either OS runs (the union), and whether it is non-empty
  files_windows, any_windows    the tests the Windows job runs
  files_macos, any_macos        the tests the macOS job runs
  matrix                        {"include": [{"os", "files"}]}, one entry per OS that has tests; files is a JSON list as text
Stdout also names every touched path and what became of it, so the run log shows each decision.

A touched path selects:
  a test file (patterns TEST_PATTERNS)                                       -> itself
  dir/x.py                                                                   -> dir/test_x.py
  dir/x.sh                                                                   -> dir/test_x.sh
  dir/x.mjs, dir/x.js                                                        -> dir/x.test.{mjs,js}, dir/tests/x.test.{mjs,js}; x.mjs also dir/test_x.mjs
  any non-.md path under skills/plain-english-map/                           -> every test in its tests folder
  any non-.md, non-test path under a folder named tests                      -> every test under that folder
Each selected test then lands in one of these places, each printed with its reason, none dropped silently:
  HEAVY           the batch shards it in its own jobs; running it per lane push is a cost blow-up
  NEEDS_SETUP     needs a browser or a tool this workflow does not install, or runs on one OS only
  per OS          listed for an OS when a job of checks.yml at HEAD runs on that OS and names it (see os_runs);
                  skipped on each other OS, and on both with "no CI job runs it" when no Windows or macOS job names it
An unreadable diff (no BASE_SHA, git fails) or a checks.yml it cannot read exits 1 and writes no output
(decision ci-unknown-is-red).
"""
import fnmatch
import json
import os
import re
import subprocess
import sys

# Test-file name patterns, matched on the file's own name.
TEST_PATTERNS = ("*.test.mjs", "*.test.js", "test_*.mjs", "test_*.py", "test_*.sh", "*.test.sh", "*.test.ps1")

# The workflow whose jobs decide each OS's list. It is read from the HEAD commit, so a lane that moves a test between
# jobs is judged by its own checks.yml.
CI_PATH = ".github/workflows/checks.yml"
# runs-on prefix -> the OS word the lists and log lines use. A Linux runner runs nothing here. Any other runner is
# unknown, and exits 1.
OS_RUNNERS = {"windows-": "windows", "macos-": "macos"}
LINUX_RUNNERS = ("ubuntu-",)
# The runner scripts a run text may name in place of a test path, with the tests each phase runs (script ->
# {argument: globs}; "" is no argument). Read from .github/scripts/mod-tests.sh: phase_mods runs every *.test.mjs
# and *.test.js under mods/, and phase_skill runs `node --test` in the map skill's tests folder. A change to that
# script's file lists changes this table too.
RUNNER_SCRIPTS = {
    ".github/scripts/mod-tests.sh": {
        "mods": ("mods/*.test.mjs", "mods/*.test.js"),
        "skill": ("skills/plain-english-map/tests/*.test.mjs", "skills/plain-english-map/tests/*.test.js"),
        "": ("mods/*.test.mjs", "mods/*.test.js",
             "skills/plain-english-map/tests/*.test.mjs", "skills/plain-english-map/tests/*.test.js"),
    },
}

# The suites checks.yml runs in shard jobs or under a step cap of its own (glob -> reason).
HEAVY = {
    "hooks/test_guard.py": "heavy: runs in the batch's shard jobs (GUARD_SHARD)",
    "merge/test_merge.py": "heavy: runs in the batch's shard jobs (MERGE_SHARD)",
    "janitor/test_sweep.py": "heavy: runs in the batch's checks-windows-sweep job",
    "hooks/test_install_src.sh": "heavy: runs in the batch's shell-macos job under its own step cap",
}

# Suites that need a browser or a tool this workflow does not install (glob -> reason).
NEEDS_SETUP = {
    "*/tests/page.test.mjs": "needs Playwright and Chromium; runs in checks-shoot on Linux only",
    "skills/waiting-page/tests/test_check_designs.mjs": "needs Playwright and Chromium; runs in checks-shoot on Linux only",
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
    elif dot and ext == "sh":
        found.add(f"{prefix}test_{stem}.sh")
    elif dot and ext in ("mjs", "js"):
        for test_ext in ("mjs", "js"):
            found.add(f"{prefix}{stem}.test.{test_ext}")
            found.add(f"{prefix}tests/{stem}.test.{test_ext}")
        if ext == "mjs":
            found.add(f"{prefix}test_{stem}.mjs")
    if not path.endswith(".md"):
        if path.startswith(MAP_DIR):
            found |= {t for t in tracked if t.startswith(MAP_TESTS) and is_test(t)}
        parts = path.split("/")
        if "tests" in parts[:-1]:
            folder = "/".join(parts[: parts.index("tests") + 1]) + "/"
            found |= {t for t in tracked if t.startswith(folder) and is_test(t)}
    return {c for c in found if c in tracked}


# A YAML mapping key line: indent, an optional "- " list dash, the key, and the rest of the line.
KEY_LINE = re.compile(r"^(?P<indent> *)(?P<dash>- +)?(?P<key>[A-Za-z0-9_.-]+):(?:[ \t]+(?P<value>.*?))?[ \t]*$")


def one_line_scalar(value):
    """A one-line YAML scalar's text, with its comment cut and its quotes removed; None when it is not one."""
    value = (value or "").strip()
    if value[:1] in ("'", '"'):
        end = value.find(value[0], 1)
        return value[1:end] if end > 0 and not value[end + 1:].strip().lstrip("#") else None
    value = re.split(r"[ \t]#", value, maxsplit=1)[0].strip()
    return value if value and value[0] not in "[{|>&*!" and "${{" not in value else None


def ci_jobs(text):
    """{job: (runs-on, [run text])} for each job under the top-level `jobs:` of a workflow. A hand parser: the runner
    image has no YAML module. A run text is the line's value plus every deeper line after it, so a block scalar
    (`run: |`), a folded one and a plain continuation are each read whole. A job this cannot read exits 1: a job
    read as no job would drop its tests in silence."""
    jobs, job, job_indent, prop_indent, in_jobs = {}, None, None, None, False
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if line[indent] == "\t":
            fail(f"{CI_PATH} line {i} is indented with a tab")
        m = KEY_LINE.match(line)
        if indent == 0:
            in_jobs = bool(m) and m["key"] == "jobs" and not m["dash"] and one_line_scalar(m["value"]) is None
            job = None
            continue
        if not in_jobs:
            continue
        if job_indent is None:
            job_indent = indent
        if indent < job_indent:
            fail(f"{CI_PATH} line {i} sits between the top level and the jobs: {line.strip()!r}")
        if indent == job_indent:
            if not m or m["dash"] or m["value"]:
                fail(f"{CI_PATH} line {i} is not a job name: {line.strip()!r}")
            job, prop_indent = m["key"], None
            if job in jobs:
                fail(f"{CI_PATH} names job {job} twice")
            jobs[job] = [None, []]
            continue
        if prop_indent is None:
            prop_indent = indent
        if not m:
            continue
        key_col = indent + len(m["dash"] or "")
        if m["key"] == "runs-on" and indent == prop_indent and not m["dash"]:
            runner = one_line_scalar(m["value"])
            if runner is None or jobs[job][0] is not None:
                fail(f"{CI_PATH} job {job}: cannot read runs-on {m['value']!r}; the OS lists would be unknown")
            jobs[job][0] = runner
        elif m["key"] == "run":
            body = [m["value"] or ""]
            while i < len(lines) and (not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip(" ")) > key_col):
                body.append(lines[i])
                i += 1
            jobs[job][1].append("\n".join(body))
    if not jobs:
        fail(f"{CI_PATH} has no jobs this can read")
    for name, (runner, _) in jobs.items():
        if runner is None:
            fail(f"{CI_PATH} job {name} has no runs-on this can read; the OS lists would be unknown")
    return {name: (runner, runs) for name, (runner, runs) in jobs.items()}


def os_of(job, runner):
    for prefix, word in OS_RUNNERS.items():
        if runner.startswith(prefix):
            return word
    if runner.startswith(LINUX_RUNNERS):
        return None
    fail(f"{CI_PATH} job {job} runs on {runner!r}, a runner this cannot place on an OS")


def names(text, path):
    """True when `text` names `path` as a whole path, not as part of a longer one."""
    return re.search(rf"(?<![\w./\\-])(?:\./)?{re.escape(path)}(?![\w./\\-])", text) is not None


def script_globs(text):
    """The test globs of each runner script (RUNNER_SCRIPTS) that `text` names, by the phase argument it passes."""
    globs = []
    for script, phases in RUNNER_SCRIPTS.items():
        for m in re.finditer(rf"(?<![\w./\\-])(?:\./)?{re.escape(script)}(?![\w./\\-])(?:[ \t]+(\w+))?", text):
            arg = m[1] or ""
            if arg not in phases:
                fail(f"{CI_PATH} runs {script} with argument {arg!r}, which names no phase this knows")
            globs.extend(phases[arg])
    return globs


def os_runs():
    """{OS word: [run text]} for the Windows and macOS jobs of checks.yml at HEAD."""
    texts = {word: [] for word in OS_RUNNERS.values()}
    for job, (runner, runs) in ci_jobs(git("show", f"HEAD:{CI_PATH}")).items():
        word = os_of(job, runner)
        if word:
            texts[word].extend(runs)
    return texts


def runs_on(test, texts):
    """The OS words whose jobs name `test`, by its path or by a runner script whose globs cover it."""
    return [word for word, runs in texts.items()
            if any(names(t, test) or any(fnmatch.fnmatchcase(test, g) for g in script_globs(t)) for t in runs)]


def flag(listed):
    return "true" if listed else "false"


def write_outputs(windows, macos):
    files = sorted(set(windows) | set(macos))
    matrix = [{"os": name, "files": json.dumps(listed)}
              for name, listed in (("windows-latest", windows), ("macos-latest", macos)) if listed]
    lines = (f"files={json.dumps(files)}\nany={flag(files)}\n"
             f"files_windows={json.dumps(windows)}\nany_windows={flag(windows)}\n"
             f"files_macos={json.dumps(macos)}\nany_macos={flag(macos)}\n"
             f"matrix={json.dumps({'include': matrix})}\n")
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
    texts = os_runs()
    lists = {word: [] for word in texts}
    labels = {"windows": "Windows", "macos": "macOS"}
    for test in sorted(selected):
        why = reason(test, HEAVY) or reason(test, NEEDS_SETUP)
        if why:
            print(f"skip {test}: {why}")
            continue
        on = runs_on(test, texts)
        if not on:
            print(f"skip {test} on {' and '.join(texts)}: no CI job runs it on Windows or macOS ({CI_PATH})")
            continue
        for word in texts:
            if word in on:
                lists[word].append(test)
            else:
                print(f"skip {test} on {word}: {CI_PATH} runs it on no {labels[word]} job")
        print(f"run {test} on {' and '.join(on)}")
    write_outputs(lists["windows"], lists["macos"])


if __name__ == "__main__":
    main()
