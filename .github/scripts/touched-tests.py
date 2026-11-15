#!/usr/bin/env python3
"""Selects the test files a draft lane PR touches, for .github/workflows/lane-touched-tests.yml.

Input (env): BASE_SHA, the PR's base commit. The checkout is at HEAD.
Output: lines written to $GITHUB_OUTPUT (stdout when unset):
  files, any                    every test either OS runs (the union), and whether it is non-empty
  files_windows, any_windows    the tests the Windows job runs
  files_macos, any_macos        the tests the macOS job runs, less the shared hooks suites (MACOS_SHARED, read for MACOS_WORDS), which are skipped with a reason
  matrix                        {"include": [{"os", "files"}]}, one entry per OS that has tests; files is a JSON list as text
  commands_windows, commands_macos   {path: cmd} over that OS's files. cmd is the interpreter its checks.yml run line starts
                                with: sh, bash, node, node --test, python, python3, powershell or pwsh (mod-tests.sh files:
                                `node` for a mods test, `node --test` for a map skill test). Each OS names its own, so a
                                test run as `python` on Windows and `python3` on macOS has both.
Stdout also names every touched path and what became of it, so the run log shows each decision.

A touched path selects:
  a test file (patterns TEST_PATTERNS)                                       -> itself
  dir/x.py                                                                   -> dir/test_x.py
  dir/x.sh                                                                   -> dir/test_x.sh, dir/x.test.sh
  dir/x.ps1                                                                  -> dir/x.test.ps1, dir/x-*.test.ps1
  any non-.md, non-test path under mods/<mod>/                               -> every *.test.mjs, *.test.js and check.mjs under
                                                                               mods/<mod>/, not node_modules (that mod's only:
                                                                               mod-tests.sh runs every mod's, each with `node`)
  dir/x.mjs, dir/x.js                                                        -> dir/x.test.{mjs,js}, dir/tests/x.test.{mjs,js}; x.mjs also dir/test_x.mjs
  any non-.md path under skills/plain-english-map/                           -> every test in its tests folder
  any non-.md, non-test path under a folder named tests                      -> every test under that folder
Each selected test then lands in one of these places, each printed with its reason, none dropped silently:
  HEAVY           the batch shards it in its own jobs; running it per lane push is a cost blow-up
  NEEDS_SETUP     needs a browser or a tool this workflow does not install, or runs on one OS only
  per OS          listed for an OS when a job of checks.yml at HEAD runs on that OS and names it (see os_runs);
                  skipped on each other OS, and on both with "no CI job runs it" when no Windows or macOS job names it
An unreadable diff (no BASE_SHA, git fails) or a checks.yml it cannot read exits 1 and writes no output
(decision ci-unknown-is-red). A checks.yml it cannot read is a runs-on it cannot place, no jobs, a tab indent, a
flow-style step (`- {`), a one-line `steps: [...]`, a `defaults:` block, or a run line that names a test after anything but
an interpreter (`FOO=x node t`, `cd a && node t`) or after a chain (`&&`, `;`, `|` outside quotes: `node a.mjs && node t`).
The exit names the line. A trailing backslash joins a line to the next. A step with `shell: powershell` or `pwsh` is read
with each backslash as a slash, and a trailing backtick joins its line to the next.
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
# The runner scripts a run text may name in place of a test path, with the tests each phase runs and the command that
# script runs each with (script -> {argument: ((glob, cmd), ...)}; "" is no argument). Read from
# .github/scripts/mod-tests.sh: phase_mods runs `node <f>` on every *.test.mjs, *.test.js and check.mjs under mods/, and
# phase_skill runs `node --test` in the map skill's tests folder. A change to that script's file lists changes this table
# and MOD_CHECK too.
MOD_CHECK = "check.mjs"
MODS_TESTS = (("mods/*.test.mjs", "node"), ("mods/*.test.js", "node"), (f"mods/*/{MOD_CHECK}", "node"))
SKILL_TESTS = (("skills/plain-english-map/tests/*.test.mjs", "node --test"),
               ("skills/plain-english-map/tests/*.test.js", "node --test"))
RUNNER_SCRIPTS = {
    ".github/scripts/mod-tests.sh": {"mods": MODS_TESTS, "skill": SKILL_TESTS, "": MODS_TESTS + SKILL_TESTS},
}

# The suites checks.yml runs in shard jobs or under a step cap of its own (glob -> reason).
HEAVY = {
    "hooks/test_guard.py": "heavy: runs in the batch's shard jobs (GUARD_SHARD)",
    "tests/guard/*": "heavy: section files of hooks/test_guard.py, which runs in the batch's shard jobs (GUARD_SHARD)",
    "merge/test_merge.py": "heavy: runs in the batch's shard jobs (MERGE_SHARD)",
    "janitor/test_sweep.py": "heavy: runs in the batch's checks-windows-sweep job",
    "hooks/test_install_src.sh": "heavy: runs in the batch's shell-macos job under its own step cap",
}

# Suites that need a browser or a tool this workflow does not install (glob -> reason).
NEEDS_SETUP = {
    "*/tests/page.test.mjs": "needs Playwright and Chromium; runs in checks-shoot (roadmap) or checks-waiting-page (waiting page) on Linux only",
    "skills/waiting-page/tests/test_check_designs.mjs": "needs Playwright and Chromium; runs in checks-waiting-page on Linux only",
    "lint/test_shoot.mjs": "needs Playwright and Chromium; runs in checks-shoot on Linux only",
    "lint/test_ios_ship.sh": "needs macOS tooling (bin/ios-ship); runs in shell-macos only",
    "lint/test_sim_test.sh": "needs macOS tooling (bin/sim-test); runs in shell-macos only",
}

# R61 part 4: the macOS leg of a lane runs a test only when its subject is macOS. A shared suite (one that runs the same on every
# OS) proves nothing more on a lane push, and the batch's macOS run covers it. A hooks test is shared by default (MACOS_SHARED,
# glob -> reason), unless its own text names a macOS thing (MACOS_WORDS: the file is read) or MACOS_SUBJECT names it. An
# unreadable file and a test no list covers stay on the macOS leg: unknown is not skip. ci-scope.sh's checks_macos flag is too
# wide to define this (any hooks/ edit sets it), so these lists are the one home. A product file selects its test through
# candidates(), so a change to janitor/install_launchd.py reaches janitor/test_install_launchd.py.
MACOS_SHARED = {
    "hooks/test_*.py": "a hook suite with no macOS word in its text runs the same on every OS",
}
# The words that make a test a macOS subject: darwin (also a faked Darwin uname), macos, launchd and xcrun.
MACOS_WORDS = re.compile(r"darwin|macos|launchd|xcrun", re.IGNORECASE)
# A test that runs code with a darwin arm or macOS-only tooling. It stays on the macOS leg even inside a shared glob.
MACOS_SUBJECT = {
    "janitor/test_install_launchd.py": "tests the launchd installer",
    "janitor/test_session_end_sweep.py": "tests the session-end sweep, whose process-start read has a darwin arm",
    "hooks/test_guard_load_os.py": "checks the guard's load reader against the macOS tools (its darwin arm)",
    "lint/test_rm_shim.py": "tests the rm shim over the real macOS rm (its darwin arm)",
    "hooks/test_sim_boot_record.py": "tests the iOS simulator boot record, which reads macOS launchd state",
}


def shared_on_macos(test):
    """The reason `test` is a shared suite that the macOS leg skips, or None when it stays. It stays when MACOS_SUBJECT names
    it, when its own text has a MACOS_WORDS word, and when the file cannot be read (unknown is not skip)."""
    why = reason(test, MACOS_SHARED)
    if not why or reason(test, MACOS_SUBJECT):
        return None
    try:
        with open(test, encoding="utf-8", errors="replace") as f:
            return None if MACOS_WORDS.search(f.read()) else why
    except OSError:
        return None

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
    # A file that a HEAVY glob names is selected even when its name is no test name (a section file), so the log skips it with its reason.
    if is_test(path) or reason(path, HEAVY):
        return {path}
    found = set()
    directory, _, name = path.rpartition("/")
    prefix = directory + "/" if directory else ""
    stem, dot, ext = name.rpartition(".")
    if dot and ext == "py":
        found.add(f"{prefix}test_{stem}.py")
    elif dot and ext == "sh":
        found.add(f"{prefix}test_{stem}.sh")
        found.add(f"{prefix}{stem}.test.sh")
    elif dot and ext == "ps1":
        found.add(f"{prefix}{stem}.test.ps1")
        found |= {t for t in tracked if t.rpartition("/")[0] == directory
                  and fnmatch.fnmatchcase(t.rpartition("/")[2], f"{stem}-*.test.ps1")}
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
        if parts[0] == "mods" and len(parts) > 2 and "node_modules" not in parts:
            mod = "/".join(parts[:2]) + "/"
            found |= {t for t in tracked if t.startswith(mod) and "node_modules" not in t.split("/")
                      and (t.endswith((".test.mjs", ".test.js")) or t.rpartition("/")[2] == MOD_CHECK)}
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
        if end < 0:
            return None
        tail = value[end + 1:]
        # Only whitespace, or a comment that follows whitespace, may come after the closing quote.
        return value[1:end] if not tail.strip() or (tail[0] in " \t" and tail.strip().startswith("#")) else None
    value = re.split(r"[ \t]#", value, maxsplit=1)[0].strip()
    return value if value and value[0] not in "#[{|>&*!" and "${{" not in value else None


def ci_jobs(text):
    """{job: (runs-on, [(line, run text, line join)])} for each job under the top-level `jobs:` of a workflow. A hand
    parser: the runner image has no YAML module. `line join` is the step shell's line continuation. A run text is the line's
    value plus every deeper line after it, so a block scalar (`run: |`), a folded one and a plain continuation are each
    read whole. `line` is the number of the `run:` key's line, so the nth line of its text is line + n - 1. A job this cannot read exits 1: a job read as no job would drop its
    tests in silence."""
    jobs, job, job_indent, prop_indent, in_jobs = {}, None, None, None, False
    in_steps, step_indent, step_col, step_no = False, None, None, 0
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
            if m and m["key"] == "defaults":
                fail(f"{CI_PATH} line {i} sets workflow-level defaults, which this cannot read: a default shell would change how a step reads")
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
            jobs[job] = [None, [], {}]
            in_steps, step_indent, step_col, step_no = False, None, None, 0
            continue
        if prop_indent is None:
            prop_indent = indent
        if indent == prop_indent and m and not m["dash"]:
            in_steps = m["key"] == "steps"
            step_indent, step_col, step_no = None, None, 0
            if m["key"] == "defaults":
                fail(f"{CI_PATH} line {i} sets job {job}'s defaults, which this cannot read: a default shell would change how a step reads")
            if in_steps and m["value"] and not m["value"].startswith("#"):
                fail(f"{CI_PATH} line {i} writes job {job}'s steps on one line, which this cannot read: {line.strip()!r}")
        if in_steps and re.match(r"-[ \t]+\{", line.lstrip(" ")) and step_indent in (None, indent):
            fail(f"{CI_PATH} line {i} is a flow-style step, which this cannot read; the job {job} would be misread: "
                 f"{line.strip()!r}")
        if not m:
            continue
        key_col = indent + len(m["dash"] or "")
        if in_steps and m["dash"] and step_indent in (None, indent):
            step_indent, step_col, step_no = indent, key_col, step_no + 1
        if m["key"] == "runs-on" and indent == prop_indent and not m["dash"]:
            runner = one_line_scalar(m["value"])
            if runner is None or jobs[job][0] is not None:
                fail(f"{CI_PATH} job {job}: cannot read runs-on {m['value']!r}; the OS lists would be unknown")
            jobs[job][0] = runner
        elif m["key"] == "shell" and in_steps and key_col == step_col:
            jobs[job][2][step_no] = one_line_scalar(m["value"])
        elif m["key"] == "run":
            start, body = i, [m["value"] or ""]
            while i < len(lines) and (not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip(" ")) > key_col):
                body.append(lines[i])
                i += 1
            jobs[job][1].append((step_no if in_steps else 0, start, "\n".join(body)))
    if not jobs:
        fail(f"{CI_PATH} has no jobs this can read")
    for name, (runner, _, _) in jobs.items():
        if runner is None:
            fail(f"{CI_PATH} job {name} has no runs-on this can read; the OS lists would be unknown")
    # A powershell step names a path with a backslash (lint\\test_x.py). Read it as the slash form the lists use. Its
    # line continuation is a trailing backtick; a bash step's is a trailing backslash.
    out = {}
    for name, (runner, runs, shells) in jobs.items():
        out[name] = (runner, [])
        for step, start, text in runs:
            if shells.get(step) in POWERSHELLS:
                out[name][1].append((start, text.replace("\\", "/"), "`"))
            else:
                out[name][1].append((start, text, "\\"))
    return out


POWERSHELLS = ("powershell", "pwsh")


def os_of(job, runner):
    for prefix, word in OS_RUNNERS.items():
        if runner.startswith(prefix):
            return word
    if runner.startswith(LINUX_RUNNERS):
        return None
    fail(f"{CI_PATH} job {job} runs on {runner!r}, a runner this cannot place on an OS")


def name_match(text, path):
    """The match of `path` named as a whole path in `text`, not as part of a longer one; None when it is not named."""
    return re.search(rf"(?<![\w./\\-])(?:\./)?{re.escape(path)}(?![\w./\\-])", text)


# The interpreters a run line may start with. The command a test runs with is this word (`node --test` for node's runner).
INTERPRETERS = ("sh", "bash", "node", "python", "python3", "powershell", "pwsh")


def chain_before(prefix):
    """The first chain operator (`&&`, `;`, `|`) in `prefix` outside quotes, or None. `||` reads as `|`."""
    quote = None
    for k, ch in enumerate(prefix):
        if quote:
            quote = None if ch == quote else quote
        elif ch in "'\"":
            quote = ch
        elif ch in ";|" or prefix.startswith("&&", k):
            return prefix[k:k + 2] if ch == "&" else ch
    return None


def line_command(start, text, match, join):
    """The command the run line that names the path `match` found starts with: a word of INTERPRETERS, or `node --test`
    for node's test runner. `start` is the line number of text's first line. The line is the logical line, so a
    trailing `join` (a backslash, or a backtick in a powershell step) joins the next line. Anything else before the
    interpreter (an env prefix, `cd a &&`, `if`, the path itself), or a chain between the interpreter and the path,
    exits 1 naming the line: the run could not be reproduced from its command word alone."""
    rows = text.split("\n")
    index = text.count("\n", 0, match.start())
    first = index
    while first > 0 and rows[first - 1].rstrip().endswith(join):
        first -= 1
    column = match.start() - (text.rfind("\n", 0, match.start()) + 1)
    joined = [row.rstrip().removesuffix(join) for row in rows[first:index]]
    words = " ".join(joined + [rows[index]]).split()
    chain = chain_before(" ".join(joined + [rows[index][:column]]))
    if chain:
        fail(f"{CI_PATH} line {start + first} names a test after a chain ({chain!r}), so its command cannot be read from "
             f"the line's first word: {' '.join(words)!r}")
    if not words or words[0] not in INTERPRETERS:
        fail(f"{CI_PATH} line {start + first} names a test after {words[0] if words else 'nothing'!r}, not an interpreter "
             f"({', '.join(INTERPRETERS)}), so its command cannot be read: {' '.join(words)!r}")
    return "node --test" if words[0] == "node" and words[1:2] == ["--test"] else words[0]


def script_globs(text):
    """The (test glob, command) pairs of each runner script (RUNNER_SCRIPTS) that `text` names, by the phase argument
    it passes."""
    globs = []
    for script, phases in RUNNER_SCRIPTS.items():
        for m in re.finditer(rf"(?<![\w./\\-])(?:\./)?{re.escape(script)}(?![\w./\\-])(?:[ \t]+(\w+))?", text):
            arg = m[1] or ""
            if arg not in phases:
                fail(f"{CI_PATH} runs {script} with argument {arg!r}, which names no phase this knows")
            globs.extend(phases[arg])
    return globs


def os_runs():
    """{OS word: [(line, run text, line join)]} for the Windows and macOS jobs of checks.yml at HEAD."""
    texts = {word: [] for word in OS_RUNNERS.values()}
    for job, (runner, runs) in ci_jobs(git("show", f"HEAD:{CI_PATH}")).items():
        word = os_of(job, runner)
        if word:
            texts[word].extend(runs)
    return texts


def command_for(test, runs):
    """The command a run text of `runs` runs `test` with: the interpreter its run line starts with, or the command of
    the runner script whose globs cover it. None when no run text names it. `runs` is [(line, run text, line join)]."""
    for start, text, join in runs:
        found = name_match(text, test)
        if found:
            return line_command(start, text, found, join)
        for glob, cmd in script_globs(text):
            if fnmatch.fnmatchcase(test, glob):
                return cmd
    return None


def flag(listed):
    return "true" if listed else "false"


def write_outputs(windows, macos, cmds):
    """`cmds` is {OS word: {test: command}}."""
    files = sorted(set(windows) | set(macos))
    matrix = [{"os": name, "files": json.dumps(sorted(listed))}
              for name, listed in (("windows-latest", windows), ("macos-latest", macos)) if listed]
    lines = (f"files={json.dumps(files)}\nany={flag(files)}\n"
             f"files_windows={json.dumps(windows)}\nany_windows={flag(windows)}\n"
             f"files_macos={json.dumps(macos)}\nany_macos={flag(macos)}\n"
             f"matrix={json.dumps({'include': matrix})}\n"
             f"commands_windows={json.dumps(cmds['windows'])}\ncommands_macos={json.dumps(cmds['macos'])}\n")
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
    cmds = {word: {} for word in texts}
    labels = {"windows": "Windows", "macos": "macOS"}
    for test in sorted(selected):
        why = reason(test, HEAVY) or reason(test, NEEDS_SETUP)
        if why:
            print(f"skip {test}: {why}")
            continue
        for word in texts:
            cmd = command_for(test, texts[word])
            if cmd is not None:
                cmds[word][test] = cmd
        on = [word for word in texts if word in cmds and test in cmds[word]]
        if not on:
            print(f"skip {test} on {' and '.join(texts)}: no CI job runs it on Windows or macOS ({CI_PATH})")
            continue
        shared = shared_on_macos(test)
        listed = [word for word in on if word != "macos" or not shared]
        for word in texts:
            if word in listed:
                lists[word].append(test)
            elif word in on:
                del cmds[word][test]
                print(f"skip {test} on {word}: not a macOS subject ({shared}), so a lane's macOS leg leaves it to the batch's macOS run")
            else:
                print(f"skip {test} on {word}: {CI_PATH} runs it on no {labels[word]} job")
        if listed:
            print(f"run {test} on {' and '.join(listed)}")
    write_outputs(lists["windows"], lists["macos"], cmds)


if __name__ == "__main__":
    main()
