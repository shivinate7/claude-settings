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
    # The probe must set PYTHONDONTWRITEBYTECODE itself, so an outer setting must not hide a bytecode write.
    env = {k: v for k, v in os.environ.items() if k not in SESSION_VARS + ("PYTHONDONTWRITEBYTECODE",)}
    env["CLAUDE_CONFIG_DIR"] = config_dir
    return env


def probe(args, stdin="", config_dir=None, tmp=None, script=None, run_in=None):
    """Run hooks/probe.py (or `script`) as a reviewer does, from NOGIT or `run_in`. Returns (rc, stdout, stderr)."""
    env = scrubbed_env(config_dir or new_dir())
    if tmp is not None:
        env["TMPDIR"] = tmp
    result = subprocess.run([PY, script or PROBE] + list(args), input=stdin, capture_output=True, text=True,
                            env=env, cwd=run_in or NOGIT, timeout=120)
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


JUDGE_RAISES = "def _raise(payload):\n    raise RuntimeError('judge raised')\nguard.judge = _raise"


def guard_stub(judge_body):
    """A stub guard.py that runs the real guard's main, with its judge replaced by judge_body."""
    return (
        "import importlib.util\n"
        "spec = importlib.util.spec_from_file_location('guard_under_test', %r)\n"
        "guard = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(guard)\n"
        "%s\n"
        "guard.main()\n" % (GUARD, judge_body)
    )


@case
def judge_crash_is_never_allow():
    """Probe: a guard whose judge raises gives `probe: guard crashed (...), verdict unknown`, nonzero, never allow."""
    folder = new_dir()
    # probe.py finds guard.py beside itself, so the stub guard needs a copy of the probe beside it.
    probe_copy = os.path.join(folder, "probe.py")
    shutil.copyfile(PROBE, probe_copy)
    guard_copy = os.path.join(folder, "guard.py")
    # Scope first: the same stub with the real judge prints exactly `allow` for a harmless command.
    write(guard_copy, guard_stub("pass").encode("utf-8"))
    rc, out, err = probe(flags(HARMLESS), script=probe_copy)
    bad = scope(rc, out, err)
    if bad or out != "allow\n":
        return ["control, the real judge: " + (bad[0] if bad else "printed %r, want 'allow'" % out[:60])]
    write(guard_copy, guard_stub(JUDGE_RAISES).encode("utf-8"))
    rc, out, err = probe(flags(HARMLESS), script=probe_copy)
    problems = bad_input_problems(rc, out, err)
    problems += expect("probe: guard crashed (" in err, "stderr does not say the guard crashed")
    problems += expect("verdict unknown" in err, "stderr does not say the verdict is unknown")
    return problems


@case
def session_fields_stay_out_of_the_guard():
    """Probe: a stdin payload's session_id and agent_id never reach the guard."""
    folder = new_dir()
    probe_copy = os.path.join(folder, "probe.py")
    shutil.copyfile(PROBE, probe_copy)
    received = os.path.join(folder, "received.json")
    write(os.path.join(folder, "guard.py"), (
        "import json, sys\n"
        "with open(%r, 'w', encoding='utf-8') as handle:\n"
        "    json.dump(json.load(sys.stdin), handle)\n" % received).encode("utf-8"))
    stdin = json.dumps({"tool_name": "Bash", "tool_input": {"command": HARMLESS}, "cwd": NOGIT,
                        "session_id": "probe-session-1", "agent_id": "probe-agent-1"})
    rc, out, err = probe([], stdin=stdin, script=probe_copy)
    bad = scope(rc, out, err)
    if bad:
        return bad
    if not os.path.exists(received):
        return ["the stub guard received no payload"]
    with open(received, encoding="utf-8") as handle:
        got = json.load(handle)
    # Scope first: the stub got the call itself, so an absent field means the probe dropped it.
    if got.get("tool_name") != "Bash" or got.get("tool_input", {}).get("command") != HARMLESS:
        return ["the stub guard did not get the call: %r" % got]
    problems = expect("session_id" not in got, "the guard received session_id")
    problems += expect("agent_id" not in got, "the guard received agent_id")
    return problems


@case
def probe_writes_no_bytecode():
    """Probe: a probe run in a copy of hooks/ leaves no __pycache__ folder behind."""
    copy = os.path.join(new_dir(), "hooks")
    shutil.copytree(HERE, copy, ignore=shutil.ignore_patterns("__pycache__"))
    rc, out, err = probe(flags(HARMLESS), script=os.path.join(copy, "probe.py"))
    bad = scope(rc, out, err)
    if bad:
        return bad
    found = []
    for folder, dirs, _files in os.walk(copy):
        if "__pycache__" in dirs:
            found.append(os.path.relpath(os.path.join(folder, "__pycache__"), copy))
    return expect(not found, "the probe wrote bytecode folders: %s" % sorted(found)[:3])


def runner_source(keep_temp_dir):
    """A runner that loads the probe under test and calls its main. With keep_temp_dir, rmtree does nothing,
    so the probe's temp dir cannot be removed and stays behind."""
    return (
        "import importlib.util, shutil, sys\n"
        "spec = importlib.util.spec_from_file_location('probe_under_test', %r)\n"
        "probe = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(probe)\n"
        "if %r:\n"
        "    shutil.rmtree = lambda path, ignore_errors=False: None\n"
        "sys.exit(probe.main())\n" % (PROBE, keep_temp_dir)
    )


@case
def temp_dir_removal_failure_is_reported():
    """Probe: a temp dir the probe cannot remove gets a stderr note; the verdict and exit code do not change."""
    control = os.path.join(new_dir(), "runner.py")
    write(control, runner_source(False).encode("utf-8"))
    stub = os.path.join(new_dir(), "runner.py")
    write(stub, runner_source(True).encode("utf-8"))
    # Scope first: with removal working, the run prints one verdict line, exits 0, and writes no note.
    rc, out, err = probe(flags(HARMLESS), script=control)
    bad = scope(rc, out, err)
    if bad:
        return ["control, removal works: " + bad[0]]
    if "could not remove" in err:
        return ["control, removal works: stderr has a note"]
    tmp = new_dir()
    rc2, out2, err2 = probe(flags(HARMLESS), script=stub, tmp=tmp)
    bad = scope(rc2, out2, err2)
    if bad:
        return ["removal fails: " + bad[0]]
    problems = expect(out2 == out, "verdict %r, want the control's %r" % (out2[:60], out[:60]))
    problems += expect(rc2 == rc, "exit %d, want the control's %d" % (rc2, rc))
    match = re.search(r"could not remove its temp dir (\S+)", err2)
    if match is None:
        return problems + ["stderr has no 'could not remove its temp dir' line"]
    return problems + expect(os.path.isdir(match.group(1)), "the path the note names is not left behind")


SCRATCH_SESSION_ID = "probe-session-scratch-1"
DELETE_ROOT = "rm -rf /"


def probe_env(args, session_id):
    """Run the probe with the outer session env as given, and only CLAUDE_CODE_SESSION_ID set when session_id is."""
    env = {k: v for k, v in os.environ.items() if k not in SESSION_VARS}
    if session_id:
        env["CLAUDE_CODE_SESSION_ID"] = session_id
    env["CLAUDE_CONFIG_DIR"] = new_dir()
    result = subprocess.run([PY, PROBE] + list(args), capture_output=True, text=True, env=env,
                            cwd=NOGIT, timeout=120)
    return result.returncode, result.stdout, result.stderr


@case
def session_env_does_not_change_the_verdict():
    """Probe: a session id in the outer env does not change the verdict for a call from a session's scratchpad."""
    cwd = os.path.join(new_dir(), SCRATCH_SESSION_ID, "scratchpad")
    os.makedirs(cwd)
    args = ["--tool", "Bash", "--command", REFUSED, "--cwd", cwd]
    # Control first: with no session id, the refusal stands.
    rc, out, err = probe_env(args, None)
    bad = scope(rc, out, err)
    if bad:
        return ["control, no session id: " + bad[0]]
    if not out.startswith("deny %s: " % REFUSED_RULE):
        return ["control, no session id: printed %r, want the refusal" % out[:60]]
    rc2, out2, err2 = probe_env(args, SCRATCH_SESSION_ID)
    bad = scope(rc2, out2, err2)
    if bad:
        return ["with a session id: " + bad[0]]
    return expect(out2 == out, "with CLAUDE_CODE_SESSION_ID set the verdict is %r, want the unset run's %r"
                  % (out2[:60], out[:60]))


@case
def tool_outside_shell_tools_is_refused():
    """Probe: a --tool outside the guard's shell tools, with --command, exits nonzero with no verdict."""
    # Scope first: the shell tools still get the guard's verdict for the same command.
    for tool in ("Bash", "PowerShell"):
        rc, out, err = probe(["--tool", tool, "--command", DELETE_ROOT, "--cwd", NOGIT])
        bad = scope(rc, out, err)
        if bad:
            return ["control %s: %s" % (tool, bad[0])]
        if not out.startswith("deny destructive-delete: "):
            return ["control %s: printed %r, want the destructive-delete refusal" % (tool, out[:60])]
    problems = []
    for tool in ("bash", "Shell", "Write"):
        rc, out, err = probe(["--tool", tool, "--command", DELETE_ROOT, "--cwd", NOGIT])
        problems += ["%s: %s" % (tool, p) for p in bad_input_problems(rc, out, err)]
    return problems


@case
def dropped_session_fields_are_noted():
    """Probe: a stdin payload's session_id, agent_id and agent_type are dropped with a stderr note that names each."""
    base = {"tool_name": "Bash", "tool_input": {"command": HARMLESS}, "cwd": NOGIT}
    with_fields = dict(base, session_id="probe-session-2", agent_id="probe-agent-2", agent_type="Explore")
    # Scope first: without those fields the run prints one verdict line, exits 0, and writes no note.
    rc, out, err = probe([], stdin=json.dumps(base))
    bad = scope(rc, out, err)
    if bad:
        return ["control, no session fields: " + bad[0]]
    if err.strip():
        return ["control, no session fields: stderr %r, want none" % err[:60]]
    rc2, out2, err2 = probe([], stdin=json.dumps(with_fields))
    bad = scope(rc2, out2, err2)
    if bad:
        return bad
    problems = expect(out2 == out, "verdict %r, want the control's %r" % (out2[:60], out[:60]))
    for field in ("session_id", "agent_id", "agent_type"):
        problems += expect(field in err2, "stderr does not name the dropped %s" % field)
    return problems


@case
def relative_cwd_is_judged_as_the_absolute_folder():
    """Probe: a relative --cwd gives the guard the same folder as the absolute path, so the verdict is the same."""
    # realpath: the probe reports the folder the OS resolves, so a symlinked TMPDIR must not split the two runs.
    folder = os.path.realpath(new_dir())
    sub = os.path.join(folder, "sub")
    os.makedirs(sub)
    probe_copy = os.path.join(folder, "probe.py")
    shutil.copyfile(PROBE, probe_copy)
    # The stub refuses with the cwd it was handed as its reason, so the verdict shows which folder the guard judged.
    write(os.path.join(folder, "guard.py"), (
        "import json, sys\n"
        "payload = json.load(sys.stdin)\n"
        "reason = 'cwd-seen: ' + str(payload.get('cwd'))\n"
        "out = {'permissionDecision': 'deny', 'permissionDecisionReason': reason}\n"
        "print(json.dumps({'hookSpecificOutput': out}))\n"
    ).encode("utf-8"))
    # Scope first: the absolute folder gives the verdict naming that folder.
    rc, out, err = probe(["--tool", "Bash", "--command", HARMLESS, "--cwd", sub], script=probe_copy, run_in=folder)
    bad = scope(rc, out, err)
    if bad:
        return ["control, absolute cwd: " + bad[0]]
    if out != "deny cwd-seen: %s\n" % sub:
        return ["control, absolute cwd: printed %r, want the folder named" % out[:80]]
    rc2, out2, err2 = probe(["--tool", "Bash", "--command", HARMLESS, "--cwd", "sub"], script=probe_copy,
                            run_in=folder)
    bad = scope(rc2, out2, err2)
    if bad:
        return ["relative cwd: " + bad[0]]
    return expect(out2 == out, "relative cwd gives %r, want the absolute run's %r" % (out2[:80], out[:80]))


@case
def config_overlap_is_noted():
    """Probe: a cwd inside the real config dir gets a `probe: note:` line; the verdict does not change."""
    config = os.path.realpath(new_dir())
    inside = os.path.join(config, "work")
    os.makedirs(inside)
    outside = os.path.join(os.path.realpath(new_dir()), "elsewhere")
    os.makedirs(outside)
    refused = ["--tool", "Bash", "--command", REFUSED]
    # Control: a cwd outside the outer config dir gives no note.
    rc, out, err = probe(refused + ["--cwd", outside], config_dir=config)
    bad = scope(rc, out, err)
    if bad:
        return ["control, cwd outside the config dir: " + bad[0]]
    if "probe: note:" in err:
        return ["control, cwd outside the config dir: stderr has a note"]
    # Baseline: a cwd inside a config dir that is not the outer one gives no note.
    rc2, out2, err2 = probe(refused + ["--cwd", inside], config_dir=new_dir())
    bad = scope(rc2, out2, err2)
    if bad:
        return ["baseline, cwd inside another config dir: " + bad[0]]
    if "probe: note:" in err2:
        return ["baseline, cwd inside another config dir: stderr has a note"]
    rc3, out3, err3 = probe(refused + ["--cwd", inside], config_dir=config)
    bad = scope(rc3, out3, err3)
    if bad:
        return ["cwd inside the config dir: " + bad[0]]
    notes = [line for line in err3.splitlines() if line.startswith("probe: note:")]
    problems = expect(bool(notes), "stderr has no 'probe: note:' line for a cwd inside the config dir")
    if notes:
        problems += expect("frozen-path" in notes[0] and "override" in notes[0],
                           "the note does not name frozen-path and override")
    return problems + expect(out3 == out2, "verdict %r, want the baseline's %r" % (out3[:60], out2[:60]))


if __name__ == "__main__":
    sys.exit(run_cases(CASES))
