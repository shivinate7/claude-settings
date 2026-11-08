#!/usr/bin/env python3
"""Cases for hooks/probe.py, the guard probe a reviewer agent runs. Standard library only.

Run it from the repository root:

    python3 hooks/test_probe.py

Design under test: `python3 hooks/probe.py --tool Bash --command '<text>' [--cwd <dir>]`, also
`--command-file <path>`, or a JSON payload `{"tool_name", "tool_input", "cwd"}` on stdin when no flags
are given. The probe runs hooks/guard.py's own main in a subprocess, with payload on stdin and
CLAUDE_CONFIG_DIR set to a fresh temp dir that the probe deletes after. It never runs the probed command.
It prints one line: `allow` when the guard prints nothing, else `<decision> <rule>: <reason>` from the
guard's permissionDecision output. It exits 0 on a verdict, and nonzero with a message on bad input.

Scope first. Every case that compares, or looks for an absence, first checks that the probe exited 0
and printed one verdict line. Without that check, a missing helper would pass those cases: no output
equals no output, no marker is no run, an untouched config dir is no write.

The expected refusal line comes from running hooks/guard.py directly on the same payload, in a fresh
config dir, with the same scrubbed environment. That direct run is also the green control. The refusal
case pins the decision and the rule literally as well.

The probe runs use the environment that hooks/test_guard.py's decide uses: the four session variables
are dropped. The probe's cwd is NOGIT, a folder outside any repository, so a probe that ran the probed
command would run it where it can do no harm. Every fixture folder sits under the run folder.

Scratch files live under one run folder (lint/_test_temp.py), which is removed at exit. The sweep of
sibling run folders is proved in hooks/test_checks_never_raise.py (sweep_proof), not here.
"""

import atexit
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

from case_runner_test import run_cases

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)

PROBE = os.environ.get("PROBE_MODULE") or os.path.join(HERE, "probe.py")
GUARD = os.path.join(HERE, "guard.py")
PY = sys.executable
SCRATCH = _test_temp.run_folder()
CASES = []

# The refused command is the one hooks/test_guard.py's "reset: throws the tree away" case refuses,
# with the same rule. Its cwd is NOGIT there too.
REFUSED = "git reset --hard origin/main"
REFUSED_RULE = "shared-tree"
HARMLESS = "ls -la"
# 200000 bytes, refused at the tail, so a command cut short would allow.
FULL_SIZE = "echo " + "x" * 199990 + " && " + REFUSED
SESSION_VARS = ("CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_REMOTE", "CLAUDE_CODE_REMOTE_SESSION_ID", "CLAUDE_PROJECT_DIR")
VERDICT = re.compile(r"allow|(deny|ask) [a-z][a-z0-9-]*: .+")
INTERPRETER_MISSING = "can't open file '%s'" % PROBE   # what Python prints when the probe file is absent

NOGIT = os.path.join(SCRATCH, "nogit")
os.makedirs(NOGIT)


def _cleanup():
    shutil.rmtree(SCRATCH, ignore_errors=True)


atexit.register(_cleanup)


def case(fn):
    CASES.append(fn)
    return fn


def expect(ok, msg):
    return [] if ok else [msg]


def new_dir():
    return tempfile.mkdtemp(dir=SCRATCH)


def write(path, data):
    with open(path, "wb") as handle:
        handle.write(data)


def tree(root):
    """Every file and folder under root, with its bytes. An absent root is an empty tree."""
    found = {}
    for folder, dirs, files in os.walk(root):
        for name in dirs:
            found[os.path.relpath(os.path.join(folder, name), root) + os.sep] = b""
        for name in files:
            full = os.path.join(folder, name)
            with open(full, "rb") as handle:
                found[os.path.relpath(full, root)] = handle.read()
    return found


def changed_names(before, after):
    names = set(before) ^ set(after)
    names |= {name for name in before if name in after and before[name] != after[name]}
    return sorted(names)


def scrubbed_env(config_dir):
    env = {k: v for k, v in os.environ.items() if k not in SESSION_VARS}
    env["CLAUDE_CONFIG_DIR"] = config_dir
    return env


def probe(args, stdin="", config_dir=None, tmp=None, script=None):
    """Run hooks/probe.py (or `script`) the way a reviewer runs it, from NOGIT. Returns (rc, stdout, stderr)."""
    env = scrubbed_env(config_dir or new_dir())
    if tmp is not None:
        env["TMPDIR"] = tmp
    result = subprocess.run([PY, script or PROBE] + list(args), input=stdin, capture_output=True, text=True,
                            env=env, cwd=NOGIT, timeout=120)
    return result.returncode, result.stdout, result.stderr


def guard(stdin, config_dir=None):
    """Run hooks/guard.py directly, the way the harness runs it. Returns (rc, stdout)."""
    result = subprocess.run([PY, GUARD], input=stdin, capture_output=True, text=True,
                            env=scrubbed_env(config_dir or new_dir()), cwd=NOGIT, timeout=120)
    return result.returncode, result.stdout


def guard_line(stdout):
    """The verdict line the probe must print for the guard's stdout."""
    if not stdout.strip():
        return "allow"
    hso = json.loads(stdout)["hookSpecificOutput"]
    return "%s %s" % (hso["permissionDecision"], hso["permissionDecisionReason"])


def payload(command):
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": NOGIT})


def flags(command):
    return ["--tool", "Bash", "--command", command, "--cwd", NOGIT]


def scope(rc, out, err):
    """The scope every verdict case checks first: exit 0 and one verdict line. Empty when it holds."""
    if rc != 0:
        last = err.strip().splitlines()[-1:] or [""]
        return ["probe exited %d, want 0: %s" % (rc, last[0][:200])]
    if out.count("\n") != 1 or not out.endswith("\n") or not VERDICT.fullmatch(out[:-1]):
        return ["stdout is not one verdict line: %r" % out[:160]]
    return []


def bad_input_problems(rc, out, err):
    if INTERPRETER_MISSING in err:
        return ["stderr is the interpreter's missing-file error, so the helper did not run"]
    problems = expect(rc != 0, "exit 0, want nonzero")
    problems += expect(bool(err.strip()), "stderr is empty, want a message")
    problems += expect(out == "", "printed %r, want no verdict" % out[:60])
    return problems


# ------------------------------------------------------------------ controls: green on the old commit

@case
def control_guard_refuses_reset():
    """Control: hooks/guard.py run directly refuses the reset with decision deny and rule shared-tree."""
    rc, out = guard(payload(REFUSED))
    if rc != 0:
        return ["guard exited %d, want 0" % rc]
    if not out.strip():
        return ["guard printed nothing, want a deny for %r" % REFUSED]
    hso = json.loads(out)["hookSpecificOutput"]
    problems = expect(hso["permissionDecision"] == "deny", "decision %r, want deny" % hso["permissionDecision"])
    problems += expect(hso["permissionDecisionReason"].startswith(REFUSED_RULE + ": "),
                       "reason %r does not name rule %s" % (hso["permissionDecisionReason"][:40], REFUSED_RULE))
    return problems


@case
def control_guard_writes_its_config_dir():
    """Control: a direct guard run changes guard.log in its config dir, so the byte check can see a leak."""
    cfg = new_dir()
    write(os.path.join(cfg, "guard.log"), b"seed\n")
    before = tree(cfg)
    guard(payload(REFUSED), config_dir=cfg)
    return expect(tree(cfg) != before, "guard.log did not change, so the untouched-config check would pass a leak")


# ------------------------------------------------------------------ the verdict

@case
def refusal_line_matches_guard():
    """Probe: a refused command prints the guard's own line: decision deny, rule shared-tree."""
    rc, out, err = probe(flags(REFUSED))
    problems = scope(rc, out, err)
    if problems:
        return problems
    line = out[:-1]
    if not line.startswith("deny %s: " % REFUSED_RULE):
        return ["line %r does not start with 'deny %s: '" % (line[:60], REFUSED_RULE)]
    rc, guard_out = guard(payload(REFUSED))
    return expect(line == guard_line(guard_out),
                  "line differs from the guard's own refusal line (probe %r)" % line[:80])


@case
def harmless_command_prints_allow():
    """Probe: a harmless command prints exactly `allow`."""
    rc, out, err = probe(flags(HARMLESS))
    problems = scope(rc, out, err)
    if problems:
        return problems
    return expect(out == "allow\n", "line %r, want 'allow'" % out[:60])


@case
def stdin_payload_matches_flags():
    """Probe: a JSON payload on stdin gets the same verdict as the flags, for a refused and a harmless command."""
    problems = []
    for command in (REFUSED, HARMLESS):
        rc, flag_out, err = probe(flags(command))
        bad = scope(rc, flag_out, err)
        if bad:
            return problems + ["flags %r: %s" % (command, bad[0])]
        rc, stdin_out, err = probe([], stdin=payload(command))
        bad = scope(rc, stdin_out, err)
        if bad:
            return problems + ["stdin %r: %s" % (command, bad[0])]
        problems += expect(stdin_out == flag_out,
                           "stdin %r gives %r, flags give %r" % (command, stdin_out[:80], flag_out[:80]))
    return problems


@case
def command_file_matches_flags():
    """Probe: --command-file gets the same verdict as --command, for a refused and a harmless command."""
    problems = []
    for command in (REFUSED, HARMLESS):
        path = os.path.join(new_dir(), "command.txt")
        write(path, command.encode("utf-8"))
        rc, flag_out, err = probe(flags(command))
        bad = scope(rc, flag_out, err)
        if bad:
            return problems + ["flags %r: %s" % (command, bad[0])]
        rc, file_out, err = probe(["--tool", "Bash", "--command-file", path, "--cwd", NOGIT])
        bad = scope(rc, file_out, err)
        if bad:
            return problems + ["command file %r: %s" % (command, bad[0])]
        problems += expect(file_out == flag_out,
                           "command file %r gives %r, flags give %r" % (command, file_out[:80], flag_out[:80]))
    return problems


@case
def full_size_command_is_judged_whole():
    """Probe: a 200 KB command, refused at its tail, is refused through --command-file and through stdin."""
    path = os.path.join(new_dir(), "command.txt")
    write(path, FULL_SIZE.encode("utf-8"))
    rc, out, err = probe(["--tool", "Bash", "--command-file", path, "--cwd", NOGIT])
    bad = scope(rc, out, err)
    if bad:
        return ["command file: " + bad[0]]
    problems = expect(out.startswith("deny %s: " % REFUSED_RULE),
                      "command file gives %r, want the refusal (a cut-off command would allow)" % out[:60])
    rc, out, err = probe([], stdin=payload(FULL_SIZE))
    bad = scope(rc, out, err)
    if bad:
        return problems + ["stdin: " + bad[0]]
    return problems + expect(out.startswith("deny %s: " % REFUSED_RULE),
                             "stdin gives %r, want the refusal (a cut-off command would allow)" % out[:60])


@case
def probed_command_never_runs():
    """Probe: an allowed touch and a refused compound with a touch both leave their marker absent."""
    shapes = (
        ("allowed touch", "touch %s", "allow\n"),
        ("refused compound", REFUSED + "; touch %s", "deny %s: " % REFUSED_RULE),
    )
    problems = []
    for label, shape, want in shapes:
        marker = os.path.join(new_dir(), "marker")
        rc, out, err = probe(flags(shape % marker))
        bad = scope(rc, out, err)
        if bad:
            return problems + ["%s: %s" % (label, bad[0])]
        if not out.startswith(want):
            problems.append("%s: verdict %r, want %r" % (label, out[:60], want))
        if os.path.exists(marker):
            problems.append("%s: the probe ran the command, the marker exists" % label)
    return problems


LOG_FIXTURES = (
    ("no guard.log", None),
    ("a short guard.log", b"seed one\nseed two\n"),
    ("a full-size guard.log", b"".join(b"seed line %06d\n" % n for n in range(20000))),
)


@case
def outer_config_dir_is_untouched():
    """Probe: the outer CLAUDE_CONFIG_DIR keeps every byte, for no guard.log, a short one and a full-size one."""
    problems = []
    for label, seed in LOG_FIXTURES:
        cfg = new_dir()
        if seed is not None:
            write(os.path.join(cfg, "guard.log"), seed)
        before = tree(cfg)
        rc, out, err = probe(flags(REFUSED), config_dir=cfg)
        bad = scope(rc, out, err)
        if bad:
            return problems + ["%s: %s" % (label, bad[0])]
        after = tree(cfg)
        if after != before:
            problems.append("%s: the outer config dir changed: %s" % (label, changed_names(before, after)))
    return problems


@case
def probe_leaves_no_temp_dir():
    """Probe: the temp dir the probe makes is gone after a refusal and after a command file."""
    problems = []
    path = os.path.join(new_dir(), "command.txt")
    write(path, HARMLESS.encode("utf-8"))
    for label, args in (("refusal", flags(REFUSED)),
                        ("command file", ["--tool", "Bash", "--command-file", path, "--cwd", NOGIT])):
        tmp = new_dir()
        rc, out, err = probe(args, tmp=tmp)
        bad = scope(rc, out, err)
        if bad:
            return problems + ["%s: %s" % (label, bad[0])]
        left = sorted(os.listdir(tmp))
        if left:
            problems.append("%s: the probe left %s in TMPDIR" % (label, left))
    return problems


BAD_INPUT = (
    ("no flags and empty stdin", [], ""),
    ("stdin that is not JSON", [], "not json"),
    ("stdin that is a JSON list", [], json.dumps(["Bash"])),
    ("an unknown flag", flags(HARMLESS) + ["--bogus", "x"], ""),
    ("a missing --command-file", ["--tool", "Bash", "--command-file", os.path.join(SCRATCH, "missing.txt"),
                                  "--cwd", NOGIT], ""),
)


@case
def bad_input_exits_nonzero_with_a_message():
    """Probe: bad input exits nonzero with its own message and prints no verdict, after a valid run."""
    rc, out, err = probe(flags(HARMLESS))
    bad = scope(rc, out, err)
    if bad:
        return ["valid run first: " + bad[0]]
    problems = []
    for label, args, stdin in BAD_INPUT:
        rc, out, err = probe(args, stdin=stdin)
        problems += ["%s: %s" % (label, p) for p in bad_input_problems(rc, out, err)]
    return problems


GUARD_FAILURES = (
    ("a guard that exits 3 with no output", "import sys\nsys.stdin.read()\nsys.exit(3)\n"),
    ("a guard that crashes", "import sys\nsys.stdin.read()\nraise RuntimeError('guard crashed')\n"),
)
SILENT_GUARD = "import sys\nsys.stdin.read()\n"


@case
def guard_failure_is_never_allow():
    """Probe: a guard that exits nonzero or crashes gives no verdict and a nonzero exit, never `allow`."""
    folder = new_dir()
    # probe.py finds guard.py beside itself, so the stub guard needs a copy of the probe beside it.
    probe_copy = os.path.join(folder, "probe.py")
    shutil.copyfile(PROBE, probe_copy)
    guard_copy = os.path.join(folder, "guard.py")
    # Scope first: a silent guard that exits 0 prints exactly `allow`, so the copy and the stub really ran.
    write(guard_copy, SILENT_GUARD.encode("utf-8"))
    rc, out, err = probe(flags(HARMLESS), script=probe_copy)
    bad = scope(rc, out, err)
    if bad or out != "allow\n":
        return ["control, a silent guard: " + (bad[0] if bad else "printed %r, want 'allow'" % out[:60])]
    problems = []
    for label, source in GUARD_FAILURES:
        write(guard_copy, source.encode("utf-8"))
        rc, out, err = probe(flags(HARMLESS), script=probe_copy)
        problems += ["%s: %s" % (label, p) for p in bad_input_problems(rc, out, err)]
        problems += ["%s: %s" % (label, p) for p in expect("guard" in err, "stderr does not name the guard")]
    return problems


if __name__ == "__main__":
    sys.exit(run_cases(CASES))
