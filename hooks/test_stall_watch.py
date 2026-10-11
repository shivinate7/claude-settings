#!/usr/bin/env python3
"""Cases for hooks/stall_watch.py. Standard library only, and no test runner.

Run it from the repository root:

    python3 hooks/test_stall_watch.py

Design under test: the PreToolUse hook rewrites a background Bash command into shell code that
runs in the harness shell. The original stays unquoted, as top-level code inside `{ ... }`, so a
settings deny rule still sees it:

    { <original>
    } > LOG 2>&1 & pid=$!; python3 stall_watch.py --watch-pid $pid --log LOG --quiet N; rc=$?;
    [ $rc -eq 3 ] && exit 3; wait $pid

The watcher streams LOG to stdout. After N silent seconds it prints one report that starts with a
line `STALL:`, and exits 3. The command keeps running. If the pid ends first, the watcher exits 0,
and `wait` returns the command's code.

Every case runs the real hook and the real rewritten command, the way the harness runs them. No
case imports the module. Two environment variables steer the run:
- STALL_WATCH_MODULE: the module under test (default hooks/stall_watch.py beside this file).
  Mutation runs point it at a copy with a defect in it.
- STALL_WATCH_QUIET: the quiet seconds the hook writes into the rewritten command. The tests set 2.

Report format the tests read: `pid=<n>` names the background job. its absolute path, ending in .log, names the log.
Pids are found by regex, so spacing around `=` is tolerant.

Scratch files live in one temp directory, removed at exit. Every process a report names is killed
at exit, with its descendants. The tests start those processes themselves.
"""

import atexit
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.environ.get("STALL_WATCH_MODULE") or os.path.join(HERE, "stall_watch.py")
PY = sys.executable
SCRATCH = tempfile.mkdtemp(prefix="test-stall-watch-")
PIDS = set()
CASES = []

PID_RE = re.compile(r"\bpid\b\W{0,3}(\d+)")
LOG_RE = re.compile(r"(/\S+\.log)\b")

ORIG_QUOTING = r'''printf '%s\n' "it's" 'x$HOME' "$((1+2))" && echo chained # trailing comment'''
QUOTING_WANT = "it's\nx$HOME\n3\nchained\n"
ORIG_HEREDOC = "cat <<'EOF'\nline \"one\" $HOME\nEOF\necho after"
HEREDOC_WANT = 'line "one" $HOME\nafter\n'


class Skip(Exception):
    pass


class Fail(Exception):
    pass


def case(fn):
    CASES.append(fn)
    return fn


def expect(ok, msg):
    return [] if ok else [msg]


def new_dir():
    return tempfile.mkdtemp(dir=SCRATCH)


def shells():
    found = ["/bin/sh"]
    for extra in ("/bin/bash", "/bin/zsh"):
        if os.path.exists(extra):
            found.append(extra)
    return found


def process_table():
    out = subprocess.run(["ps", "-axo", "pid=,ppid=,args="], capture_output=True, text=True).stdout
    rows = []
    for line in out.splitlines():
        parts = line.split(None, 2)
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            rows.append((int(parts[0]), int(parts[1]), parts[2] if len(parts) > 2 else ""))
    return rows


def tree(root):
    """Return [(pid, args)] for root and every descendant alive now."""
    rows = process_table()
    kids = {}
    args_of = {}
    for pid, ppid, args in rows:
        kids.setdefault(ppid, []).append(pid)
        args_of[pid] = args
    found, stack, seen = [], [root], set()
    while stack:
        p = stack.pop()
        if p in seen:
            continue
        seen.add(p)
        found.append((p, args_of.get(p, "")))
        stack.extend(kids.get(p, []))
    return found


def pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def reap():
    """Kill the background jobs that reports named, with their descendants. Then forget them."""
    for root in list(PIDS):
        for pid, _args in tree(root):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
    PIDS.clear()


def _cleanup():
    reap()
    shutil.rmtree(SCRATCH, ignore_errors=True)


atexit.register(_cleanup)


def remember(text):
    for m in PID_RE.finditer(text):
        PIDS.add(int(m.group(1)))


def module_or_fail():
    if not os.path.isfile(MODULE):
        raise Fail(f"{MODULE} is missing")


def hook(command, os_name=None):
    """Run the hook on one background Bash call. Return (rc, stdout, stderr)."""
    module_or_fail()
    payload = {
        "session_id": "test-stall-watch",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command, "description": "test", "run_in_background": True},
    }
    env = dict(os.environ, STALL_WATCH_QUIET="2")
    if os_name is None:
        argv = [PY, MODULE, "--hook"]
    else:
        # Import the stdlib first, so only the module's own os.name checks see the patch.
        driver = "import json, os, runpy, shlex, shutil, signal, subprocess, sys, tempfile, time\n" \
                 "os.name = %r\nsys.argv = [sys.argv[1], '--hook']\n" \
                 "runpy.run_path(sys.argv[0], run_name='__main__')\n" % os_name
        argv = [PY, "-c", driver, MODULE]
    proc = subprocess.run(argv, input=json.dumps(payload).encode("utf-8"),
                          capture_output=True, env=env, timeout=20)
    return proc.returncode, proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace")


def rewrite(command):
    """Return (rewritten command, hookSpecificOutput) for a background call, or raise Fail."""
    rc, out, err = hook(command)
    if rc != 0:
        raise Fail(f"hook exit {rc}: {err.strip()[:200]}")
    try:
        hso = json.loads(out)["hookSpecificOutput"]
    except (ValueError, KeyError):
        raise Fail("hook stdout is not the expected JSON object")
    ui = hso.get("updatedInput")
    if not isinstance(ui, dict) or not isinstance(ui.get("command"), str):
        raise Fail("no hookSpecificOutput.updatedInput.command")
    return ui["command"], hso


def run_rewritten(command, shell="/bin/sh", timeout=40):
    """Run the rewritten command in the given shell. Return (rc or None, text, seconds, cmd)."""
    cmd, _hso = rewrite(command)
    d = new_dir()
    out_path = os.path.join(d, "harness.out")
    start = time.monotonic()
    with open(out_path, "wb") as out:
        proc = subprocess.Popen([shell, "-c", cmd], cwd=d, stdin=subprocess.DEVNULL,
                                stdout=out, stderr=subprocess.STDOUT)
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            rc = None
    secs = time.monotonic() - start
    with open(out_path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    remember(text)
    return rc, text, secs, cmd


def stall_problems(rc, text, secs, sleep_args=None):
    """Checks shared by the stall cases. Return a list of problems."""
    problems = expect(rc == 3, f"exit {rc}, want 3")
    lines = text.splitlines()
    stall_at = next((i for i, line in enumerate(lines) if line.startswith("STALL:")), None)
    problems += expect(stall_at is not None, "no line starts with STALL:")
    problems += expect(secs <= 5.0, f"rewritten command ran {secs:.1f}s, want about 4s")
    m = PID_RE.search(text)
    if not m:
        return problems + ["report names no pid="]
    pid = int(m.group(1))
    problems += expect(pid_alive(pid), f"pid {pid} is not alive after the watcher exited")
    if sleep_args:
        args = [a for _p, a in tree(pid)]
        problems += expect(any(sleep_args in a for a in args),
                           f"no process with args {sleep_args!r} under pid {pid}")
    return problems


def bare_run(shell, orig):
    bare = subprocess.run([shell, "-c", orig], stdin=subprocess.DEVNULL,
                          capture_output=True, timeout=20)
    return bare.returncode, bare.stdout.decode("utf-8", "replace")


def parity_problems(orig, full_output_shells=("/bin/sh", "/bin/bash"), rc_only_shells=("/bin/zsh",)):
    """Run orig bare and rewritten in each shell. Compare exit codes everywhere, output where stated."""
    problems = []
    for shell in full_output_shells + rc_only_shells:
        if not os.path.exists(shell):
            continue
        bare_rc, bare_text = bare_run(shell, orig)
        rc, text, _secs, _cmd = run_rewritten(orig, shell=shell)
        problems += expect(rc == bare_rc, f"{shell}: exit {rc}, bare exit {bare_rc}")
        if shell in full_output_shells:
            problems += expect(text == bare_text, f"{shell}: output {text!r}, bare output {bare_text!r}")
        else:
            problems += expect("syntax error" not in text, f"{shell}: syntax error: {text!r}")
        reap()
    return problems


@case
def trailing_backslash_keeps_brace_apart():
    """8. an original ending in a backslash: sh and bash match bare output; zsh matches exit code"""
    return parity_problems("echo ends-with-backslash \\")


@case
def comment_ending_in_backslash_keeps_exit_code():
    """10. false # note \\ keeps the bare exit code in sh, bash and zsh"""
    return parity_problems("false # note \\", full_output_shells=(),
                           rc_only_shells=("/bin/sh", "/bin/bash", "/bin/zsh"))


@case
def lone_backslash_line_keeps_exit_code():
    """11. false, then a lone backslash line: exit code matches bare in sh, bash and zsh"""
    return parity_problems("false\n\\", full_output_shells=(),
                           rc_only_shells=("/bin/sh", "/bin/bash", "/bin/zsh"))


@case
def hook_has_no_permission_decision():
    """1. the hook output has updatedInput and no permissionDecision key"""
    rc, out, err = hook("echo hi")
    problems = expect(rc == 0, f"hook exit {rc}, want 0: {err.strip()[:200]}")
    try:
        hso = json.loads(out)["hookSpecificOutput"]
    except (ValueError, KeyError):
        return problems + ["hook stdout is not the expected JSON object"]
    problems += expect("permissionDecision" not in hso, "hook output carries a permissionDecision key")
    problems += expect(isinstance(hso.get("updatedInput"), dict), "no updatedInput")
    return problems


@case
def original_is_unquoted_top_level():
    """2a. the original command appears verbatim as top-level code inside { ... }"""
    orig = "echo zzq*.nomatch"
    cmd, _hso = rewrite(orig)
    problems = expect(orig in cmd, "the original command is not present verbatim in the rewrite")
    problems += expect(re.search(r"\{\s*" + re.escape(orig) + r"\s*\n\s*\}", cmd) is not None,
                       "the original is not the body of a { ... } group")
    return problems


@case
def zsh_glob_fails_as_zsh_does():
    """2b. under zsh, echo zzq*.nomatch gives zsh's no-match error, not a literal echo"""
    if "/bin/zsh" not in shells():
        raise Skip("zsh is not installed")
    rc, text, _secs, _cmd = run_rewritten("echo zzq*.nomatch", shell="/bin/zsh")
    problems = expect("no matches found" in text, f"zsh did not report no matches found: {text!r}")
    problems += expect("zzq*.nomatch" not in text.splitlines(), "zsh echoed the literal pattern")
    # Control: sh does echo the literal, so the zsh result above is not a test artefact.
    _rc, sh_text, _s, _c = run_rewritten("echo zzq*.nomatch", shell="/bin/sh")
    problems += expect("zzq*.nomatch" in sh_text.splitlines(), "sh control did not echo the literal")
    return problems


@case
def quiet_sleep_stalls_and_exits_3():
    """3a. quiet sleep 30: STALL with a pid within about 4 s, exit 3, sleep still alive"""
    problems = []
    for shell in shells():
        rc, text, secs, _cmd = run_rewritten("sleep 30", shell=shell)
        problems += [f"{shell}: {p}" for p in stall_problems(rc, text, secs, sleep_args="sleep 30")]
        reap()
    return problems


@case
def healthy_printer_no_stall():
    """3b. a printer that prints every second: no STALL, exit 0"""
    orig = "i=0; while [ $i -lt 4 ]; do echo tick$i; sleep 1; i=$((i+1)); done"
    rc, text, secs, _cmd = run_rewritten(orig)
    problems = expect(rc == 0, f"exit {rc}, want 0")
    problems += expect("STALL:" not in text, "a STALL report came for a healthy printer")
    problems += expect(text == "tick0\ntick1\ntick2\ntick3\n", f"output {text!r}")
    reap()
    return problems


@case
def exit_code_passes_through():
    """3c. exit 7 gives 7, with the output printed before it"""
    rc, text, _secs, _cmd = run_rewritten("echo before; exit 7")
    problems = expect(rc == 7, f"exit {rc}, want 7")
    problems += expect(text == "before\n", f"output {text!r}")
    reap()
    return problems


@case
def quoting_and_chains_survive():
    """3d. quotes, $, && and a trailing # comment all work, in both shells"""
    problems = []
    for shell in shells():
        rc, text, _secs, _cmd = run_rewritten(ORIG_QUOTING, shell=shell)
        problems += expect(rc == 0, f"{shell}: exit {rc}, want 0")
        problems += expect(text == QUOTING_WANT, f"{shell}: output {text!r}, want {QUOTING_WANT!r}")
        reap()
    return problems


@case
def heredoc_survives():
    """3e. a heredoc in the original works, in both shells"""
    problems = []
    for shell in shells():
        rc, text, _secs, _cmd = run_rewritten(ORIG_HEREDOC, shell=shell)
        problems += expect(rc == 0, f"{shell}: exit {rc}, want 0")
        problems += expect(text == HEREDOC_WANT, f"{shell}: output {text!r}, want {HEREDOC_WANT!r}")
        reap()
    return problems


@case
def dead_pid_missing_log_returns_fast():
    """9. --watch-pid on a dead pid with no log file returns within about 2 s"""
    module_or_fail()
    gone = subprocess.Popen([PY, "-c", "pass"])
    gone.wait()
    log = os.path.join(new_dir(), "never-created.log")
    start = time.monotonic()
    try:
        proc = subprocess.run([PY, MODULE, "--watch-pid", str(gone.pid), "--log", log, "--quiet", "2"],
                              stdin=subprocess.DEVNULL, capture_output=True, timeout=10)
    except subprocess.TimeoutExpired:
        return ["watcher hung past 10 s on a dead pid with no log file"]
    secs = time.monotonic() - start
    text = proc.stdout.decode("utf-8", "replace")
    problems = expect(secs <= 3.0, f"returned after {secs:.1f}s, want about 2s")
    problems += expect("STALL:" not in text, "a dead pid reported a stall")
    return problems


@case
def stall_report_lists_lock_path():
    """4. a child holding a file under a *lock* path: the report lists it after the STALL: line"""
    if shutil.which("lsof") is None:
        raise Skip("lsof is not installed")
    d = new_dir()
    lock = os.path.join(d, "playwright-install.lock")
    code = "import sys, time\nf = open(sys.argv[1], 'w')\nprint('held', flush=True)\ntime.sleep(30)"
    orig = " ".join(shlex.quote(a) for a in [PY, "-c", code, lock])
    rc, text, secs, _cmd = run_rewritten(orig)
    problems = expect(rc == 3, f"exit {rc}, want 3")
    lines = text.splitlines()
    stall_at = next((i for i, line in enumerate(lines) if line.startswith("STALL:")), None)
    if stall_at is None:
        problems.append("no line starts with STALL:")
    else:
        report = "\n".join(lines[stall_at:])
        problems += expect(os.path.realpath(lock) in report,
                           "report, after its STALL: line, does not list the lock path held open")
    reap()
    return problems


@case
def non_posix_hook_prints_nothing():
    """5. on a non-posix os.name the hook prints nothing; posix control prints the rewrite"""
    rc, out, err = hook("echo hi", os_name="nt")
    problems = expect(rc == 0, f"hook exit {rc} on nt, want 0: {err.strip()[:200]}")
    problems += expect(out.strip() == "", f"hook printed on nt: {out.strip()[:120]!r}")
    rc, out, err = hook("echo hi", os_name="posix")
    problems += expect(rc == 0 and "updatedInput" in out, "control: posix hook did not rewrite")
    return problems


@case
def report_names_pid_and_asks_owner_to_stop():
    """6. the report names the pid and tells the session to ask the owner to stop it, not kill it"""
    rc, text, secs, _cmd = run_rewritten("sleep 30")
    problems = expect(rc == 3, f"exit {rc}, want 3")
    m = PID_RE.search(text)
    problems += expect(m is not None, "report names no pid=")
    problems += expect(re.search(r"ask\b[^\n]*\bowner\b[^\n]*\bstop\b", text, re.I) is not None,
                       "report does not tell the session to ask the owner to stop the job")
    problems += expect(re.search(r"\bkill", text, re.I) is None,
                       "report tells the session to kill; the guard denies that for a reparented job")
    reap()
    return problems


@case
def log_keeps_growing_after_watcher_exits():
    """7. after the watcher exits 3, the command's later output still reaches the log"""
    rc, text, _secs, _cmd = run_rewritten("echo first; sleep 4; echo second")
    problems = expect(rc == 3, f"exit {rc}, want 3 (the 4 s gap is a stall)")
    m = LOG_RE.search(text)
    if not m:
        reap()
        return problems + ["report names no log="]
    log = m.group(1)
    deadline = time.monotonic() + 15
    body = ""
    while time.monotonic() < deadline:
        if os.path.exists(log):
            with open(log, encoding="utf-8", errors="replace") as f:
                body = f.read()
            if "second" in body:
                break
        time.sleep(0.2)
    problems += expect("first" in body, "log lacks the output printed before the stall")
    problems += expect("second" in body, "log lacks output printed after the watcher exited")
    reap()
    return problems


def main():
    failed = skipped = 0
    for fn in CASES:
        name = (fn.__doc__ or fn.__name__).strip()
        try:
            problems = fn()
        except Skip as s:
            skipped += 1
            print(f"SKIP {name}: {s}")
            continue
        except Exception as e:  # a missing module or a crash is a failed case, not a stop
            problems = [str(e)]
        if problems:
            failed += 1
            print(f"FAIL {name}")
            for p in problems:
                print(f"  - {p}")
        else:
            print(f"PASS {name}")
    print(f"{len(CASES)} cases, {failed} failed, {skipped} skipped")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
