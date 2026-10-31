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

The STALL line lists the job's shell (the pid `&` gave) and every process under it, parent first.
Stopping all of them, in that order, ends every shape with nothing left, and the report needs no
scan of the command text. The shape cases stall a command in sh, bash and zsh and stop the listed
pids. A shape that a shell cannot parse, such as `time while` in dash, runs in the other shells.

Every case runs the real hook and the real rewritten command, the way the harness runs them. No
case imports the module. Two environment variables steer the run:
- STALL_WATCH_MODULE: the module under test (default hooks/stall_watch.py beside this file).
  Mutation runs point it at a copy with a defect in it.
- STALL_WATCH_QUIET: the quiet seconds the hook writes into the rewritten command. The tests set 2.

Report format the tests read: `pid=<a>,<b>,...` on the STALL line lists the pids to stop, parent first.
Its absolute path, ending in .log, names the log. Pids are found by regex, so spacing around `=` is
tolerant.

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

from case_runner_test import Skip, run_cases

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.environ.get("STALL_WATCH_MODULE") or os.path.join(HERE, "stall_watch.py")
PY = sys.executable
SCRATCH = tempfile.mkdtemp(prefix="test-stall-watch-")
PIDS = set()
MARKS = []  # tokens in job shells' argv that no other process carries, so reap() finds a stray job
CASES = []

PID_RE = re.compile(r"\bpid\b\W{0,3}(\d+)")
LOG_RE = re.compile(r"(/\S+\.log)\b")

ORIG_QUOTING = r'''printf '%s\n' "it's" 'x$HOME' "$((1+2))" && echo chained # trailing comment'''
QUOTING_WANT = "it's\nx$HOME\n3\nchained\n"
ORIG_HEREDOC = "cat <<'EOF'\nline \"one\" $HOME\nEOF\necho after"
HEREDOC_WANT = 'line "one" $HOME\nafter\n'


class Fail(Exception):
    pass


def case(fn):
    CASES.append(fn)
    return fn


def posix_case(fn):
    """A case that needs the posix hook. Off posix the hook is silent by design, so the case
    reports SKIP there, never PASS (decision: stall_watch is posix-only)."""
    def posix_only():
        if os.name != "posix":
            raise Skip("posix only: the hook is silent on os.name %r" % os.name)
        return fn()
    posix_only.__doc__ = fn.__doc__
    posix_only.__name__ = fn.__name__
    CASES.append(posix_only)
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


def kill_all(pids):
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def reap():
    """Kill the background jobs that reports named, with their descendants. Also kill each loop
    that carries a mark: a watcher that crashed names no pid, and its loop would spin on. Then
    forget them."""
    for root in list(PIDS):
        kill_all(pid for pid, _args in tree(root))
    for pid, _ppid, args in process_table():
        if any(mark in args for mark in MARKS):
            kill_all(p for p, _a in tree(pid))
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


def run_rewritten(command, shell="/bin/sh", timeout=40, mark=None):
    """Run the rewritten command in the given shell. Return (rc or None, text, seconds, cmd).
    The mark is the shell's $0, so ps shows it on the job and reap() finds a job that no report
    names. Text added to the command would change it, for one ending in a backslash."""
    cmd, _hso = rewrite(command)
    mark = mark or new_mark()
    d = new_dir()
    out_path = os.path.join(d, "harness.out")
    start = time.monotonic()
    with open(out_path, "wb") as out:
        proc = subprocess.Popen([shell, "-c", cmd, mark], cwd=d, stdin=subprocess.DEVNULL,
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


def trailing_backslash_keeps_brace_apart():
    """8. an original ending in a backslash: sh and bash match bare output; zsh matches exit code"""
    return parity_problems("echo ends-with-backslash \\")


def comment_ending_in_backslash_keeps_exit_code():
    """10. false # note \\ keeps the bare exit code in sh, bash and zsh"""
    return parity_problems("false # note \\", full_output_shells=(),
                           rc_only_shells=("/bin/sh", "/bin/bash", "/bin/zsh"))


def lone_backslash_line_keeps_exit_code():
    """11. false, then a lone backslash line: exit code matches bare in sh and bash"""
    # Known limit, not checked here: bare zsh treats a lone backslash line as an empty command and
    # exits 126, while the wrapper exits 1. The decision record names this limit, so zsh is out.
    return parity_problems("false\n\\", full_output_shells=(),
                           rc_only_shells=("/bin/sh", "/bin/bash"))


@posix_case
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


@posix_case
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


@posix_case
def quiet_sleep_stalls_and_exits_3():
    """3a. quiet sleep 30: STALL with a pid within about 4 s, exit 3, sleep still alive"""
    problems = []
    for shell in shells():
        rc, text, secs, _cmd = run_rewritten("sleep 30", shell=shell)
        problems += [f"{shell}: {p}" for p in stall_problems(rc, text, secs, sleep_args="sleep 30")]
        reap()
    return problems


@posix_case
def healthy_printer_no_stall():
    """3b. a printer that prints every second: no STALL, exit 0"""
    orig = "i=0; while [ $i -lt 4 ]; do echo tick$i; sleep 1; i=$((i+1)); done"
    rc, text, secs, _cmd = run_rewritten(orig)
    problems = expect(rc == 0, f"exit {rc}, want 0")
    problems += expect("STALL:" not in text, "a STALL report came for a healthy printer")
    problems += expect(text == "tick0\ntick1\ntick2\ntick3\n", f"output {text!r}")
    reap()
    return problems


def exit_code_passes_through():
    """3c. exit 7 gives 7, with the output printed before it"""
    rc, text, _secs, _cmd = run_rewritten("echo before; exit 7")
    problems = expect(rc == 7, f"exit {rc}, want 7")
    problems += expect(text == "before\n", f"output {text!r}")
    reap()
    return problems


@posix_case
def quoting_and_chains_survive():
    """3d. quotes, $, && and a trailing # comment all work, in both shells"""
    problems = []
    for shell in shells():
        rc, text, _secs, _cmd = run_rewritten(ORIG_QUOTING, shell=shell)
        problems += expect(rc == 0, f"{shell}: exit {rc}, want 0")
        problems += expect(text == QUOTING_WANT, f"{shell}: output {text!r}, want {QUOTING_WANT!r}")
        reap()
    return problems


@posix_case
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


@posix_case
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


@posix_case
def report_names_the_wait_helper():
    """6b. the report names bin/wait-pid, the one allowed way to wait on the stranded job (roadmap step wait-for-pid-form)"""
    rc, text, secs, _cmd = run_rewritten("sleep 30")
    problems = expect(rc == 3, f"exit {rc}, want 3")
    problems += expect("wait-pid" in text, "report does not name wait-pid, the way to wait on the job")
    reap()
    return problems


@posix_case
def report_lists_the_job_pid_parent_first():
    """12. a single command: the STALL line lists the job's own pid, parent first, so stopping the line ends the job"""
    problems = []
    for shell in shells():
        d = new_dir()
        orig, pidfile = pidfile_job(d, "job")
        rc, text, _secs, _cmd = run_rewritten(orig, shell=shell)
        problems += [f"{shell}: {p}" for p in expect(rc == 3, f"exit {rc}, want 3")]
        listed, job = stall_pids(text), read_pid(pidfile)
        if not listed or job is None:
            problems.append(f"{shell}: report pid or job pid file missing")
        else:
            problems += [f"{shell}: {p}" for p in expect(
                job in listed, f"the line lists pids {listed}, but the job is pid {job}")]
            problems += [f"{shell}: {p}" for p in order_problems(listed, ppids())]
        reap()
    return problems


def pidfile_job(d, tag):
    """Return (shell word, pidfile) for a 30 s python job that writes its own pid to the pidfile."""
    pidfile = os.path.join(d, tag + ".pid")
    code = "import os, time\nopen(%r, 'w').write(str(os.getpid()))\ntime.sleep(30)" % pidfile
    return " ".join(shlex.quote(a) for a in [PY, "-c", code]), pidfile


def read_pid(pidfile):
    return int(open(pidfile).read().strip()) if os.path.exists(pidfile) else None


def stall_pids(text):
    """The pids on the report's STALL: line. This is what the report says to stop."""
    m = re.search(r"^STALL:.*?\bpids?\b\W{0,3}(\d+(?:,\s?\d+)*)", text, re.M)
    return [int(p) for p in re.split(r"\D+", m.group(1))] if m else []


def listed_pids(text):
    """Every pid the report lists: the STALL: line and the rows of the process table."""
    pids = set(stall_pids(text))
    in_table = False
    for line in text.splitlines():
        if line.startswith("Processes"):
            in_table = True
        elif in_table:
            m = re.match(r"  (\d+) ", line)
            if m:
                pids.add(int(m.group(1)))
            elif not line.startswith(" "):
                break
    return pids


def crash_line(text):
    """The error line that ends a Python traceback in text, or ''."""
    m = re.search(r"^Traceback[^\n]*\n(?:[ \t]+[^\n]*\n)+(\S[^\n]*)", text, re.M)
    return m.group(1) if m else ""


def new_mark():
    """A token for a job's command line. The job's shell copies in ps carry it, and no other process does."""
    MARKS.append("7772%d%d" % (os.getpid(), len(MARKS)))
    return MARKS[-1]


def ppids():
    """Map each pid in the process table to its parent pid."""
    return {pid: ppid for pid, ppid, _args in process_table()}


def alive(pids):
    """The pids in pids that still run. A zombie is an ended process, so it does not count."""
    out = subprocess.run(["ps", "-axo", "pid=,stat="], capture_output=True, text=True).stdout
    state = {}
    for line in out.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2:
            state[parts[0]] = parts[1]
    return [p for p in pids if not state.get(str(p), "Z").startswith("Z")]


def parses(shell, orig):
    """True when shell reads orig as shell code. dash has no `time` keyword, for one."""
    return subprocess.run([shell, "-n", "-c", orig], capture_output=True).returncode == 0


def order_problems(listed, ppid_of=None):
    """Problems with the order of the pids on the STALL line: after the first, each pid has its
    parent earlier in the line. The first is the root, and every other pid is under it."""
    ppid_of = ppid_of or ppids()
    problems = []
    for i, pid in enumerate(listed[1:], 1):
        parent = ppid_of.get(pid)
        if parent in listed[:i]:
            continue
        if parent in listed[i:]:
            problems.append(f"the line lists pid {pid} before its parent, pid {parent}")
        else:
            problems.append(f"the line lists pid {pid}, which is not under pid {listed[0]} "
                            f"(its parent is pid {parent})")
    return problems


def job_problems(shell, template, pidfiles=()):
    """Stall template in shell and check its statement: the STALL line lists the job's shell and every
    process under it, parent first, and stopping them all in that order ends the job with nothing
    left. template may hold @MARK@ (a token that only this job carries in its ps lines) and @NEVER@
    (a file path that only a command after the stall point creates, so it must stay absent).
    pidfiles name files where job processes wrote their pids, and each pid must be listed.
    Return a list of problems."""
    mark = new_mark()
    never = os.path.join(new_dir(), mark + ".b")
    orig = template.replace("@MARK@", mark).replace("@NEVER@", never)
    rc, text, secs, _cmd = run_rewritten(orig, shell=shell, timeout=10, mark=mark)
    problems = stall_problems(rc, text, secs)
    problems += expect("Traceback" not in text, "the watcher crashed: " + (crash_line(text) or "traceback"))
    listed = stall_pids(text)
    args_of = {pid: args for pid, _ppid, args in process_table()}
    ppid_of = ppids()
    carriers = {pid for pid, args in args_of.items() if mark in args}
    tops = [pid for pid in carriers if ppid_of[pid] not in carriers]  # the job's shell, found without the line
    if len(tops) != 1:
        kill_all(carriers)
        return problems + [f"found {len(tops)} job shells (pids {sorted(tops)}), want 1"]
    job = tops[0]
    below = [pid for pid, _args in tree(job)]
    if not listed:
        problems.append("the STALL line lists no pid")
    else:
        if listed[0] != job:
            problems.append(f"the line starts with pid {listed[0]} ({args_of.get(listed[0], 'gone')[:40]!r}), "
                            f"not the job's shell, pid {job}")
        problems += order_problems(listed, ppid_of)
    for pid in alive(below):
        if pid not in listed:
            problems.append(f"pid {pid} ({args_of.get(pid, '')[:40]!r}) is under the job's shell, "
                            f"and the line does not list it")
    for pidfile in pidfiles:
        member = read_pid(pidfile)
        if member is None:
            problems.append("a job process wrote no pid file")
        elif member not in listed:
            problems.append(f"the line does not list job process pid {member}")
    before = alive(below)
    for pid in listed:  # one at a time, in line order: the parent dies first and starts nothing more
        kill_all([pid])
    time.sleep(0.5)
    deadline = time.monotonic() + 2.5
    while True:
        left = {pid: args for pid, _ppid, args in process_table() if mark in args}
        for pid in alive(before):
            left.setdefault(pid, args_of.get(pid, ""))
        if not left or time.monotonic() > deadline:
            break
        time.sleep(0.1)
    if left:
        pid, args = next(iter(left.items()))
        problems.append(f"stopping pids {','.join(map(str, listed))} leaves the job running: "
                        f"pid {pid} ({args[:40]!r})")
    if "@NEVER@" in template and os.path.exists(never):
        problems.append("a command after the stall point ran after the stop")
    kill_all(left)
    return problems


def shape_problems(shapes):
    """Run each (label, template) shape through job_problems, in each shell that parses it."""
    problems, ran = [], 0
    for shell in shells():
        for label, template in shapes:
            if not parses(shell, template):
                continue
            ran += 1
            problems += [f"{shell} {label}: {p}" for p in job_problems(shell, template)]
            reap()
    if not ran:
        raise Skip("no installed shell parses these shapes")
    return problems


@posix_case
def pipeline_line_lists_the_shell_then_every_member():
    """13. a stalled pipeline: the line lists the job's shell, then every member, parent first; stopping them ends the job"""
    problems = []
    for shell in shells():
        d = new_dir()
        first, first_file = pidfile_job(d, "first")
        second, second_file = pidfile_job(d, "second")
        problems += [f"{shell}: {p}" for p in job_problems(
            shell, first + " | " + second, [first_file, second_file])]
        reap()
    return problems


@posix_case
def sequence_subshell_exec_line_lists_the_running_command():
    """14. a sequence, a subshell and an exec each stall on one command: the line lists its pid, parent first"""
    shapes = (("sequence", "true; %s; true"), ("subshell", "( %s )"), ("exec", "exec %s"))
    problems = []
    for shell in shells():
        for label, template in shapes:
            d = new_dir()
            word, pidfile = pidfile_job(d, "job")
            rc, text, _secs, _cmd = run_rewritten(template % word, shell=shell)
            problems += [f"{shell} {label}: {p}" for p in expect(rc == 3, f"exit {rc}, want 3")]
            listed, job = stall_pids(text), read_pid(pidfile)
            if not listed or job is None:
                problems.append(f"{shell} {label}: report pid or job pid file missing")
            else:
                problems += [f"{shell} {label}: {p}" for p in expect(
                    job in listed, f"the line lists pids {listed}, but the running command is pid {job}")]
                problems += [f"{shell} {label}: {p}" for p in order_problems(listed, ppids())]
                if label == "exec":  # the shell is the command: nothing else to list
                    problems += [f"{shell} {label}: {p}" for p in expect(
                        listed == [job], f"the line lists pids {listed}, want only the exec'd command, pid {job}")]
            reap()
    return problems


@posix_case
def builtin_only_loop_stalls_with_a_report():
    """15. a loop of builtins only has no child: STALL report, exit 3, no traceback, and stopping the line ends the loop"""
    return shape_problems([("builtin loop", "while [ x != @MARK@ ]; do :; done")])


@posix_case
def polling_loop_line_lists_the_loop_shell_then_its_sleep():
    """16. while true; do sleep N; done: the line lists the loop's shell, then its sleep, so stopping the line ends the loop"""
    return shape_problems([("polling loop", "while true; do sleep 30.@MARK@; done")])


@posix_case
def nested_pipeline_line_lists_every_member_and_inner_shell():
    """17. (a|b)|c and { a|b; }|c: the line lists the job's shell, every inner shell copy, and a, b and c, parent first"""
    shapes = (("subshell", "(%s | %s) | %s"), ("group", "{ %s | %s; } | %s"))
    problems = []
    for shell in shells():
        for label, template in shapes:
            d = new_dir()
            words = [pidfile_job(d, tag) for tag in ("a", "b", "c")]
            problems += [f"{shell} {label}: {p}" for p in job_problems(
                shell, template % tuple(w for w, _f in words), [f for _w, f in words])]
            reap()
    return problems


@posix_case
def sequence_never_starts_its_next_command_after_the_stop():
    """18. a; b: after the line is stopped, b never starts"""
    return shape_problems([("a; b", "sleep 30.@MARK@; touch @NEVER@")])


@posix_case
def loop_with_a_subshell_or_substitution_body_ends_with_the_stop():
    """19. a loop whose body is a subshell or $(...): stopping the line leaves no process, and no restart"""
    return shape_problems([
        ("loop body ( )", "while true; do ( sleep 30.@MARK@; : ); done"),
        ("loop body $( )", "while true; do x=$(sleep 30.@MARK@; :); done"),
    ])


@posix_case
def loop_after_a_keyword_or_a_shift_ends_with_the_stop():
    """20. a loop after `time`, in a case arm, or after << as a shift or a heredoc: stopping the line ends it"""
    return shape_problems([
        ("time while", "time while true; do sleep 30.@MARK@; done"),
        ("case arm", "case x in x) while true; do sleep 30.@MARK@; done;; esac"),
        ("<< as a shift", "x=$((1<<2))\nwhile true; do sleep 30.@MARK@; done"),
        ("<< as a heredoc", "cat <<EOF >/dev/null\nbody\nEOF\nwhile true; do sleep 30.@MARK@; done"),
    ])


@posix_case
def command_after_a_loop_ends_with_the_stop():
    """21. a command after a loop: stopping the line ends the job, and a command past the stall never starts"""
    return shape_problems([
        ("loop, then sleep", "for i in 1; do :; done; sleep 30.@MARK@"),
        ("loop, then b", "for i in 1 2; do sleep 30.@MARK@; done; touch @NEVER@"),
    ])


@posix_case
def reap_ends_a_job_that_no_report_names():
    """22. reap() ends an endless loop that no report names: it finds the job by its mark"""
    rc, text, _secs, _cmd = run_rewritten("while true; do sleep 1; done")
    problems = expect(rc == 3, f"exit {rc}, want 3")
    m = PID_RE.search(text)
    job = [pid for pid, _args in tree(int(m.group(1)))] if m else []
    try:
        problems += expect(m is not None, "report names no pid=")
        PIDS.clear()  # as when a report names the wrong pid: only the mark is left to find the job
        reap()
        deadline = time.monotonic() + 2.5
        while alive(job) and time.monotonic() < deadline:
            time.sleep(0.1)
        problems += expect(not alive(job), f"reap() left the job running: pids {alive(job)}")
    finally:
        kill_all(alive(job))  # the job must not outlive a failing case
        reap()
    return problems


@posix_case
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


def growing_log_job(log, steps=5):
    """A merge.py-like job: nothing on stdout, one line a second into a log its command names."""
    return "i=0; while [ $i -lt %d ]; do echo t$i; sleep 1; i=$((i+1)); done >> %s 2>&1" % (steps, log)


@posix_case
def named_log_that_grows_is_no_stall():
    """23a. a quiet stdout and a log the command names by redirection that grows each second: no
    STALL, exit 0, in each shell"""
    problems = []
    for shell in shells():
        log = os.path.join(new_dir(), "merge.log")
        rc, text, _secs, _cmd = run_rewritten(growing_log_job(shlex.quote(log)), shell=shell)
        problems += expect(rc == 0, f"{shell}: exit {rc}, want 0")
        problems += expect("STALL:" not in text, f"{shell}: a STALL report came for a job whose log grows")
        reap()
    return problems


@posix_case
def named_log_relative_tee_and_flag_forms_are_read():
    """23b. a relative `> F`, a `| tee -a F` and a `--log F` name a log the watcher reads: no STALL"""
    problems = []
    py = shlex.quote(PY)
    grow = "import sys, time\nfor i in range(5): open(sys.argv[2], 'a').write('t\\n'); time.sleep(1)"
    forms = {
        "relative": growing_log_job("rel.log"),
        "tee": "i=0; while [ $i -lt 5 ]; do echo t$i; sleep 1; i=$((i+1)); done 2>&1 | tee -a tee.log >%s"
               % os.devnull,
        "flag": "%s -c %s --log flag.log" % (py, shlex.quote(grow)),
    }
    for name, orig in forms.items():
        rc, text, _secs, _cmd = run_rewritten(orig)
        problems += expect(rc == 0, f"{name}: exit {rc}, want 0")
        problems += expect("STALL:" not in text, f"{name}: a STALL report came for a job whose log grows")
        reap()
    return problems


def simulated_watch(phase, ps_secs, tick_extra, quiet=2.0, period=1.7, writes=6):
    """Run stall_watch.watch on a fake clock. The job writes a named log every `period` seconds from
    `phase`, then ends 1 s after its last write. Each ps takes `ps_secs`, each sleep overshoots by
    `tick_extra`, as on a loaded runner. Return watch's exit code."""
    import builtins
    import importlib.util
    spec = importlib.util.spec_from_file_location("stall_watch_sim", MODULE)
    sw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sw)
    clock = [0.0]
    stamps = [phase + period * i for i in range(writes)]
    end = stamps[-1] + 1.0

    def job_state(_pid):
        clock[0] += ps_secs
        return "Z" if clock[0] >= end else "S"

    class Empty:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def read(self):
            return b""

    sw.time = type("Clock", (), {
        "monotonic": staticmethod(lambda: clock[0]),
        "sleep": staticmethod(lambda secs: clock.__setitem__(0, clock[0] + secs + tick_extra))})
    sw.os = type("Os", (), {"path": type("Path", (), {"exists": staticmethod(lambda _p: True)})})
    sw.job_state = job_state
    sw.log_marks = lambda paths, base=None: {p: (sum(1 for w in stamps if w <= clock[0]), 0) for p in paths}
    sw.report = lambda *_a: None
    real_open = builtins.open
    builtins.open = lambda *_a, **_k: Empty()
    try:
        return sw.watch(1, "log", quiet, ["named.log"])
    finally:
        builtins.open = real_open


@posix_case
def named_log_written_slower_than_the_check_is_no_stall():
    """23b2. a named log written every 1.7 s under a 2 s quiet, with a slow ps and a late sleep, is no
    stall at any phase: the quiet test acts on a fresh sample, not the one from up to a second ago"""
    grid = [(ph, ps) for ps in range(0, 400, 3) for ph in range(0, 190, 4)]
    stalls = [(ph, ps) for ph, ps in grid if simulated_watch(ph / 100, ps / 1000, 0.005) == 3]
    return expect(not stalls, f"{len(stalls)} of {len(grid)} runs reported a STALL, first (phase, ps ms): {stalls[:3]}")


@posix_case
def named_log_that_stops_growing_stalls():
    """23c. the same job whose log stops growing: STALL within about 4 s, exit 3, the job alive"""
    log = shlex.quote(os.path.join(new_dir(), "merge.log"))
    rc, text, secs, _cmd = run_rewritten("echo once >> %s; sleep 30 >> %s 2>&1" % (log, log))
    problems = stall_problems(rc, text, secs, sleep_args="sleep 30")
    reap()
    return problems


@posix_case
def log_named_only_in_a_string_or_comment_still_stalls():
    """23d. a log path the command names only inside quotes or a comment is not a redirection: a
    quiet job stalls though another process grows that file"""
    log = os.path.join(new_dir(), "elsewhere.log")
    q = shlex.quote(log)
    writer = subprocess.Popen([PY, "-c", "import sys, time\nwhile True:\n    open(sys.argv[1], 'a').write('x\\n'); time.sleep(0.3)", log])
    try:
        orig = "echo '> %s' \"--log %s\" >%s; sleep 30 # >> %s" % (log, log, os.devnull, q)
        rc, text, secs, _cmd = run_rewritten(orig)
    finally:
        writer.kill()
        writer.wait()
    problems = stall_problems(rc, text, secs, sleep_args="sleep 30")
    reap()
    return problems


@posix_case
def quiet_job_with_no_named_log_stalls():
    """23e. a quiet job whose only redirection is to the null device, with no other log: STALL"""
    rc, text, secs, _cmd = run_rewritten("sleep 30 >%s 2>&1" % os.devnull)
    problems = stall_problems(rc, text, secs, sleep_args="sleep 30")
    reap()
    return problems


# Parity table. A row is one case body from above, and keeps its label. A failing row
# prints that label before its problem. A row that raises names itself too.
@posix_case
def table_parity_and_exit_codes():
    """Table, parity: a rewritten original keeps the bare exit code, and the bare output where
    the row says so, in each shell that is installed."""
    problems = []
    for body in (trailing_backslash_keeps_brace_apart,
                 comment_ending_in_backslash_keeps_exit_code,
                 lone_backslash_line_keeps_exit_code,
                 exit_code_passes_through):
        label = body.__doc__.split(".")[0].strip()
        try:
            found = body()
        except Skip:
            raise
        except Exception as e:
            found = [str(e)]
        problems += ["%s: %s" % (label, p) for p in found]
    return problems


if __name__ == "__main__":
    sys.exit(run_cases(CASES))
