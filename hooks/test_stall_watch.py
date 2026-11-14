#!/usr/bin/env python3
"""Cases for hooks/stall_watch.py. Standard library only, and no test runner.

Run it from the repository root:

    python3 hooks/test_stall_watch.py

Design under test: the PreToolUse hook rewrites a background Bash command into shell code that
runs in the harness shell. The original stays unquoted, as top-level code inside `{ ... }`, so a
settings deny rule still sees it:

    { export STALL_WATCH_BEAT=BEAT
    { <original>
    }
    } > LOG 2>&1 & pid=$!; python3 stall_watch.py --watch-pid $pid --log LOG --quiet N --beat BEAT;
    rc=$?; [ $rc -eq 3 ] && exit 3; wait $pid; rc=$?; rm -f LOG BEAT; exit $rc

The watcher streams LOG, and any new byte of BEAT, to stdout (the harness output file). A tool that
is quiet by design (bin/verdict) appends its heartbeat to BEAT, so a redirect in the command cannot
hide it. After N silent seconds it prints one report that starts with a
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
- STALL_WATCH_QUIET: the quiet seconds the hook writes into the rewritten command. The tests set 2,
  and the verdict cases (24a-24c) set 3.

Report format the tests read: `pid=<a>,<b>,...` on the STALL line lists the pids to stop, parent first.
Its absolute path, ending in .log, names the log. Pids are found by regex, so spacing around `=` is
tolerant.

Scratch files, and each log the hook names (it reads TMPDIR), live in one temp directory, removed
at exit. Every process a report names is killed at exit, with its descendants. The tests start
those processes themselves.
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
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)
MODULE = os.environ.get("STALL_WATCH_MODULE") or os.path.join(HERE, "stall_watch.py")
PY = sys.executable
VERDICT = os.path.join(os.path.dirname(HERE), "bin", "verdict")
SCRATCH = _test_temp.run_folder()
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


def hook(command, os_name=None, quiet="2", agent_id=None, background=True):
    """Run the hook on one Bash call, with STALL_WATCH_QUIET set to quiet. Return (rc, stdout, stderr).
    agent_id, when not None, is sent as the payload's top-level agent_id, whatever its type, so a
    malformed value can be sent too."""
    module_or_fail()
    payload = {
        "session_id": "test-stall-watch",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command, "description": "test", "run_in_background": background},
    }
    if agent_id is not None:
        payload["agent_id"] = agent_id
    # TMPDIR makes the hook name its log under SCRATCH (case 7b): a stalled job's log is never
    # removed by the wrapper, so the run's cleanup must remove it. Every caller goes through here.
    env = dict(os.environ, STALL_WATCH_QUIET=quiet, TMPDIR=SCRATCH)
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


def rewrite(command, quiet="2", agent_id=None, background=True):
    """Return (rewritten command, hookSpecificOutput) for a call, or raise Fail."""
    rc, out, err = hook(command, quiet=quiet, agent_id=agent_id, background=background)
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


def job_env(**extra):
    """The environment a rewritten job runs in: ours, minus STALL_WATCH_BEAT (the rewrite exports
    it for the job), plus `extra`."""
    env = {k: v for k, v in os.environ.items() if k != "STALL_WATCH_BEAT"}
    env.update(extra)
    return env


def run_rewritten(command, shell="/bin/sh", timeout=40, mark=None, env=None, quiet="2"):
    """Run the rewritten command in the given shell, with `env` as its environment (default: job_env()).
    Return (rc or None, text, seconds, cmd).
    The mark is the shell's $0, so ps shows it on the job and reap() finds a job that no report
    names. Text added to the command would change it, for one ending in a backslash."""
    cmd, _hso = rewrite(command, quiet=quiet)
    mark = mark or new_mark()
    d = new_dir()
    out_path = os.path.join(d, "harness.out")
    start = time.monotonic()
    with open(out_path, "wb") as out:
        proc = subprocess.Popen([shell, "-c", cmd, mark], cwd=d, stdin=subprocess.DEVNULL,
                                stdout=out, stderr=subprocess.STDOUT,
                                env=job_env() if env is None else env)
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


def job_files(cmd):
    """The LOG and BEAT paths a rewrite names, read off its --log and --beat flags. The one home of
    that parse. The wrapper writes `;` straight after the beat path, so a lexer that splits punctuation
    off reads the path as one token. A missing flag gives None."""
    def flag_value(flag):
        tail = cmd.split(" %s " % flag, 1)
        if len(tail) != 2:
            return None
        return shlex.shlex(tail[1], posix=True, punctuation_chars=True).get_token()
    return flag_value("--log"), flag_value("--beat")


def stall_problems(rc, text, sleep_args=None):
    """Checks shared by the stall cases. Return a list of problems."""
    problems = expect(rc == 3, f"exit {rc}, want 3")
    lines = text.splitlines()
    stall_at = next((i for i, line in enumerate(lines) if line.startswith("STALL:")), None)
    problems += expect(stall_at is not None, "no line starts with STALL:")
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
    """3a. quiet sleep 30: STALL with a pid, exit 3, sleep still alive"""
    problems = []
    for shell in shells():
        rc, text, secs, _cmd = run_rewritten("sleep 30", shell=shell)
        problems += [f"{shell}: {p}" for p in stall_problems(rc, text, sleep_args="sleep 30")]
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
def dead_pid_missing_log_returns():
    """9. --watch-pid on a dead pid with no log file returns, with no stall report: a real run inside the
    10 s hang guard, and the same return on a fake clock by fake time 0.5 s"""
    module_or_fail()
    gone = subprocess.Popen([PY, "-c", "pass"])
    gone.wait()
    log = os.path.join(new_dir(), "never-created.log")
    try:
        proc = subprocess.run([PY, MODULE, "--watch-pid", str(gone.pid), "--log", log, "--quiet", "2"],
                              stdin=subprocess.DEVNULL, capture_output=True, timeout=10)
    except subprocess.TimeoutExpired:
        return ["watcher hung past 10 s on a dead pid with no log file"]
    text = proc.stdout.decode("utf-8", "replace")
    problems = expect("STALL:" not in text, "a dead pid reported a stall")
    # The no-log branch on the fake clock: the real run above is bounded only by the 10 s hang guard.
    absent, stalled, ended = [], [], []
    rc = simulated_watch(0, 0, 0, writes=1, job_secs=0.0, stall_at=stalled, ended_at=ended,
                         log_exists=False, absent_at=absent)
    if not absent:  # scope first: the log check must have seen the log missing, or no-log branch did not run
        return problems + ["fake no-log: the log check never found the log missing, so the no-log branch did not run"]
    problems += expect(rc == 0, f"fake no-log: exit {rc}, want 0")
    problems += expect(not stalled, f"fake no-log: a stall report at fake times {stalled}, want none")
    problems += expect(len(ended) == 1 and ended[0] <= 0.5,
                       f"fake no-log: returned at fake times {ended}, want one return by 0.5 s")
    return problems


@case
def stall_cases_pass_on_slow_runner():
    """9b. stall_cases_pass_on_slow_runner: the quiet-stall and dead-pid cases pass when each clock read jumps 100 s"""
    if os.name != "posix":
        raise Skip("posix only: the hook is silent on os.name %r" % os.name)
    global time
    real_time = time
    clock = [0.0]

    class SlowClock:
        """Stands in for the time module here: each monotonic() read jumps 100 s, and other names are the real module's."""

        def monotonic(self):
            clock[0] += 100.0
            return clock[0]

        def __getattr__(self, name):
            return getattr(real_time, name)

    time = SlowClock()
    try:
        # Scope before subject: the stub must be live before the bodies read it.
        first = time.monotonic()
        gap = time.monotonic() - first
        if gap != 100.0:
            return [f"clock stub is not live: two reads differ by {gap}, want 100.0"]
        problems = [f"quiet_sleep_stalls_and_exits_3: {p}" for p in quiet_sleep_stalls_and_exits_3()]
        problems += [f"dead_pid_missing_log_returns: {p}" for p in dead_pid_missing_log_returns()]
    finally:
        time = real_time
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
def report_runs_the_wait_helper_by_its_bin_path():
    """6c. the report's run line names the helper as ~/.claude/bin/wait-pid: a bare wait-pid is not on PATH in a cloud session"""
    rc, text, secs, _cmd = run_rewritten("sleep 30")
    problems = expect(rc == 3, f"exit {rc}, want 3")
    problems += expect("run `~/.claude/bin/wait-pid" in text,
                       "the run line does not name the helper as ~/.claude/bin/wait-pid")
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
    problems = stall_problems(rc, text)
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
    # The tail sleep keeps the job alive after its last write, so the poll below sees LOG before a
    # job that removes its own log at exit does so.
    rc, text, _secs, _cmd = run_rewritten("echo first; sleep 4; echo second; sleep 2")
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


@posix_case
def rewrite_log_lies_under_scratch():
    """7b. the log the rewrite names lies under SCRATCH, so the run's cleanup removes it"""
    # A stalled job skips the wrapper's own `rm -f` (case 7), so only the folder's removal clears its
    # log. The check reads the path off the rewrite, never a count of files in the system temp dir.
    cmd, _hso = rewrite("echo hi")
    log, _beat = job_files(cmd)
    if log is None:
        return ["the rewrite has no --log"]
    scratch = os.path.realpath(SCRATCH)
    return expect(os.path.isabs(log) and os.path.realpath(log).startswith(scratch + os.sep),
                  f"--log {log} lies outside {scratch}: the hook took the system temp dir, "
                  "so each stalled job leaves a log behind")


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


def simulated_watch(phase, ps_secs, tick_extra, quiet=2.0, period=1.7, writes=6, job_secs=None,
                    stall_at=None, ended_at=None, log_exists=True, absent_at=None):
    """Run stall_watch.watch on a fake clock. The job writes a named log every `period` seconds from
    `phase`, then ends 1 s after its last write. Each ps takes `ps_secs`, each sleep overshoots by
    `tick_extra`, as on a loaded runner. `job_secs` sets when the job ends on the fake clock, in place of
    1 s after its last write. A `stall_at` list gets the fake time of each stall report, and an `ended_at`
    list the fake time watch returns. With `log_exists` False the watched log is absent until fake time
    30 s, and an `absent_at` list gets the fake time of each existence check that finds it absent.
    Return watch's exit code."""
    import builtins
    import importlib.util
    spec = importlib.util.spec_from_file_location("stall_watch_sim", MODULE)
    sw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sw)
    clock = [0.0]
    stamps = [phase + period * i for i in range(writes)]
    end = stamps[-1] + 1.0 if job_secs is None else job_secs

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

    def exists(_p):
        if log_exists or clock[0] >= 30.0:
            return True
        if absent_at is not None:
            absent_at.append(clock[0])
        return False

    sw.os = type("Os", (), {"path": type("Path", (), {"exists": staticmethod(exists)})})
    sw.job_state = job_state
    sw.log_marks = lambda paths, base=None: {p: (sum(1 for w in stamps if w <= clock[0]), 0) for p in paths}
    sw.report = lambda *_a: stall_at.append(clock[0]) if stall_at is not None else None
    real_open = builtins.open
    builtins.open = lambda *_a, **_k: Empty()
    try:
        rc = sw.watch(1, "log", quiet, ["named.log"])
    finally:
        builtins.open = real_open
    if ended_at is not None:
        ended_at.append(clock[0])
    return rc


@posix_case
def stall_and_exit_latency_on_a_fake_clock():
    """23b1. on a fake clock, a quiet live job gives exit 3 and one stall report by fake time 4.0 s, and a
    job that already ended gives exit 0, no report, and a return by fake time 1.2 s. The fake clock keeps
    a slow runner from moving either bound."""
    stalled = []
    rc = simulated_watch(0, 0, 0, writes=1, job_secs=30.0, stall_at=stalled)
    problems = expect(rc == 3, f"quiet live job: exit {rc}, want 3")
    problems += expect(len(stalled) == 1 and stalled[0] <= 2.0 + 2.0,
                       f"stall reported at fake times {stalled}, want one report by 4.0 s")
    ended, back = [], []
    rc = simulated_watch(0, 0, 0, writes=1, job_secs=0.0, stall_at=ended, ended_at=back)
    problems += expect(rc == 0 and not ended, f"ended job: exit {rc}, reports {ended}, want exit 0, none")
    problems += expect(len(back) == 1 and back[0] <= 0.2 + 1.0,
                       f"ended job returned at fake times {back}, want one return by 1.2 s")
    return problems


@posix_case
def named_log_written_slower_than_the_check_is_no_stall():
    """23b2. a named log written every 1.7 s under a 2 s quiet, with a slow ps and a late sleep, is no
    stall at any phase: the quiet test acts on a fresh sample, not the one from up to a second ago"""
    grid = [(ph, ps) for ps in range(0, 400, 3) for ph in range(0, 190, 4)]
    stalls = [(ph, ps) for ph, ps in grid if simulated_watch(ph / 100, ps / 1000, 0.005) == 3]
    return expect(not stalls, f"{len(stalls)} of {len(grid)} runs reported a STALL, first (phase, ps ms): {stalls[:3]}")


@posix_case
def named_log_that_stops_growing_stalls():
    """23c. the same job whose log stops growing: STALL, exit 3, the job alive"""
    log = shlex.quote(os.path.join(new_dir(), "merge.log"))
    rc, text, secs, _cmd = run_rewritten("echo once >> %s; sleep 30 >> %s 2>&1" % (log, log))
    problems = stall_problems(rc, text, sleep_args="sleep 30")
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
    problems = stall_problems(rc, text, sleep_args="sleep 30")
    reap()
    return problems


@posix_case
def quiet_job_with_no_named_log_stalls():
    """23e. a quiet job whose only redirection is to the null device, with no other log: STALL"""
    rc, text, secs, _cmd = run_rewritten("sleep 30 >%s 2>&1" % os.devnull)
    problems = stall_problems(rc, text, sleep_args="sleep 30")
    reap()
    return problems


VERDICT_QUIET = "3"  # the quiet time of the watch in the verdict cases
VERDICT_SLEEP = 6  # the verdict child runs this many seconds, above the quiet time


def verdict_job_env():
    """A one-second heartbeat, and this run's folder for the logs verdict makes. Never STALL_WATCH_BEAT:
    the rewrite must export it, as it does for a real job."""
    env = job_env(VERDICT_HEARTBEAT="1", TMPDIR=SCRATCH)
    env.pop("VERDICT_LOG", None)
    return env


def verdict_stall_problems(orig, want_rc=None):
    """Run orig as a background job under a quiet watch. No STALL may come. Return a list of problems."""
    rc, text, _secs, _cmd = run_rewritten(orig, timeout=30, env=verdict_job_env(), quiet=VERDICT_QUIET)
    reap()
    problems = expect(rc is not None, "the job did not end within 30 s")
    problems += expect("STALL" not in text, "a STALL report came: the heartbeat never reached the watch")
    problems += expect(rc != 3, "exit 3: the watch stalled and ended the job")
    if want_rc is not None:
        problems += expect(rc == want_rc, f"exit {rc}, want {want_rc}")
    return problems


@posix_case
def verdict_heartbeat_through_grep_is_no_stall():
    """24a. verdict sleep N 2>&1 | grep nomatch: the heartbeat reaches the watch, so no STALL"""
    return verdict_stall_problems(f"{shlex.quote(VERDICT)} sleep {VERDICT_SLEEP} 2>&1 | grep nomatch")


@posix_case
def verdict_heartbeat_to_devnull_is_no_stall():
    """24b. verdict sleep N 2>/dev/null: the child's stderr is dropped, yet the heartbeat reaches the watch"""
    return verdict_stall_problems(f"{shlex.quote(VERDICT)} sleep {VERDICT_SLEEP} 2>/dev/null", want_rc=0)


@posix_case
def verdict_heartbeat_reaches_the_harness_output():
    """24e. verdict sleep N 2>/dev/null: the watcher relays the heartbeat to the harness output, where the Stop check reads"""
    orig = f"{shlex.quote(VERDICT)} sleep {VERDICT_SLEEP} 2>/dev/null"
    rc, text, _secs, _cmd = run_rewritten(orig, timeout=30, env=verdict_job_env(), quiet=VERDICT_QUIET)
    reap()
    problems = expect(rc == 0, f"exit {rc}, want 0")
    problems += expect("verdict: still running" in text,
                       "the heartbeat is not in the harness output: " + text[:200])
    return problems


@posix_case
def bare_verdict_is_no_stall():
    """24c. bare verdict sleep N: the heartbeat lands in the job's log, so no STALL (no regression)"""
    return verdict_stall_problems(f"{shlex.quote(VERDICT)} sleep {VERDICT_SLEEP}", want_rc=0)


@posix_case
def beat_file_is_removed_when_the_job_ends():
    """24d. a job that writes its beat file exits 5: the rewrite exports STALL_WATCH_BEAT, the wrapper keeps
    the exit code, relays each output line once, and removes the beat file and LOG when the job ends"""
    orig = ('echo "beat=$STALL_WATCH_BEAT"; echo x >> "$STALL_WATCH_BEAT"; [ -s "$STALL_WATCH_BEAT" ] && echo held; '
            'exit 5')
    rc, text, _secs, cmd = run_rewritten(orig)
    reap()
    problems = expect(rc == 5, f"exit {rc}, want 5")
    m = re.search(r"^beat=(\S+)$", text, re.M)
    if not m:
        return problems + ["the job saw no STALL_WATCH_BEAT: " + text[:200]]
    beat = m.group(1)
    problems += expect("held" in text.splitlines(), "the job could not write to the beat file")
    problems += expect(beat.endswith(".beat"), f"beat path {beat} does not end in .beat")
    log, _beat = job_files(cmd)
    if log is None:
        return problems + ["the rewrite has no --log"]
    problems += expect(os.path.realpath(os.path.dirname(beat)) == os.path.realpath(os.path.dirname(log)),
                       f"beat {beat} is not in the folder of LOG {log}")
    # The job's lines, plus the beat line the watcher relays, each once: no byte lost or doubled.
    problems += expect(sorted(text.splitlines()) == sorted(["beat=" + beat, "held", "x"]),
                       f"relayed lines {text.splitlines()!r}, want the job's three lines once each")
    problems += expect(not os.path.exists(beat), f"beat file {beat} is still there after the job ended")
    problems += expect(not os.path.exists(log), f"LOG {log} is still there after the job ended")
    return problems


def wait_until(cond, secs):
    """Poll cond until it holds or secs pass. Return whether it held. This bound is the only wait."""
    deadline = time.monotonic() + secs
    while True:
        if cond():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.2)


def stall_then_end_problems(shell):
    """A1 for one shell. The job prints a line, stalls, then ends after the wrapper has returned."""
    done = os.path.join(new_dir(), "done")  # the job's last act, so the wait below has a file to see
    orig = 'echo pre-stall-line; echo x >> "$STALL_WATCH_BEAT"; sleep 4; touch %s' % shlex.quote(done)
    try:
        rc, text, _secs, cmd = run_rewritten(orig, shell=shell)
        log, beat = job_files(cmd)
        if log is None or beat is None:
            return ["the rewrite names no --log or no --beat"]
        lines = text.splitlines()
        problems = expect(rc == 3, f"exit {rc}, want 3")
        problems += expect(any(line.startswith("STALL:") for line in lines), "no STALL: line on the wrapper's stdout")
        # Scope: both files exist when the wrapper returns, so their removal below proves something.
        problems += expect(os.path.exists(log), f"LOG {log} is gone when the wrapper returns")
        problems += expect(os.path.exists(beat), f"BEAT {beat} is gone when the wrapper returns")
        header = next((i for i, line in enumerate(lines) if re.match(r"Last \d+ output lines:$", line)), None)
        problems += expect(header is not None, "the STALL report has no 'Last N output lines:' header")
        if header is not None:
            problems += expect(any("pre-stall-line" in line for line in lines[header + 1:]),
                               "the pre-stall line is not in the report's tail")
        problems += expect(wait_until(lambda: os.path.exists(done), 30), "the job did not end within 30 s")
        wait_until(lambda: not (os.path.exists(log) or os.path.exists(beat)), 5)
        problems += expect(not os.path.exists(log), f"LOG {log} is left after the job ended")
        problems += expect(not os.path.exists(beat), f"BEAT {beat} is left after the job ended")
        return problems
    finally:
        reap()


@posix_case
def stalled_job_leaves_no_files_when_it_ends():
    """A1. a job that stalls, then ends: the STALL report reaches stdout with the pre-stall line in its
    tail, and once the job ends neither LOG nor BEAT is left"""
    problems = []
    for shell in shells():
        problems += ["%s: %s" % (shell, p) for p in stall_then_end_problems(shell)]
    return problems


@posix_case
def exit_code_job_leaves_no_files():
    """A2. a job that exits 7 with no stall: the wrapper returns 7, and neither LOG nor BEAT is left"""
    problems = []
    for shell in shells():
        rc, text, _secs, cmd = run_rewritten('echo out; echo x >> "$STALL_WATCH_BEAT"; exit 7', shell=shell)
        reap()
        log, beat = job_files(cmd)
        if log is None or beat is None:
            return problems + ["the rewrite names no --log or no --beat"]
        found = expect(rc == 7, f"exit {rc}, want 7")
        found += expect("out" in text.splitlines(), f"the job's line is not relayed: {text!r}")
        found += expect(not os.path.exists(log), f"LOG {log} is left after the wrapper returned")
        found += expect(not os.path.exists(beat), f"BEAT {beat} is left after the wrapper returned")
        problems += ["%s: %s" % (shell, p) for p in found]
    return problems


@posix_case
def fast_job_output_is_relayed_on_every_run():
    """A4. a job that ends at once, run 20 times in each shell: all its output is relayed every time, and a
    job with no output relays none. A fix that deletes LOG at the job's exit must not win this race"""
    fast = (
        ("echo hi", "hi\n"),
        ("printf '%s\\n' " + " ".join("l%d" % i for i in range(200)),
         "".join("l%d\n" % i for i in range(200))),
        ("true", ""),
    )
    problems = []
    for shell in shells():
        for orig, want in fast:
            for n in range(20):
                rc, text, _secs, _cmd = run_rewritten(orig, shell=shell)
                reap()
                found = expect(rc == 0, f"exit {rc}, want 0")
                found += expect(text == want, f"output {text[:80]!r}, want {want[:80]!r}")
                if found:  # the first bad run says enough; a long list hides it
                    return problems + ["%s, %r, run %d: %s" % (shell, orig[:20], n + 1, p) for p in found]
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


# The agent marker. A valid agent_id is 17 lowercase hex. A background agent call's command gets
# `export CLAUDE_AGENT_ID=<id>` ahead of its wrapper, so every process the job starts holds the tag in
# its exec-time environment. A foreground call is not rewritten.
AGENT_TAG = "CLAUDE_AGENT_ID"
AGENT_ID = "3f9c1e7a0b2d4e6f8"
WRAP_BASE = re.compile(r"stall-watch-[0-9a-f]{32}")
MALFORMED_AGENT_IDS = (
    "3F9C1E7A0B2D4E6F8",    # uppercase
    "3f9c1e7a0b2d4e6f",     # 16 characters
    "3f9c1e7a0b2d4e6f80",   # 18 characters
    "3f9c1e7a0b2d4e6fz",    # not hex
    "",                     # empty
    1234567890123456,       # a number
    "3f9c1e7a0b2d4e6f;",    # a shell separator
    "3f9c1e7a0b2d4e6 f",    # a space
    "3f9c1e7a0b2d4e6f\n",   # a trailing newline, which a `$` anchor would pass
    "3f9c1e7a$(id)",        # a command substitution
    ["3f9c1e7a0b2d4e6f8"],  # a list
)


def export_line(agent_id):
    return "export %s=%s\n" % (AGENT_TAG, agent_id)


def updated_command(out):
    """The updatedInput command in a hook's stdout, or None when the hook gave no updatedInput."""
    if not out.strip():
        return None
    try:
        cmd = json.loads(out)["hookSpecificOutput"]["updatedInput"]["command"]
    except (ValueError, KeyError, TypeError):
        return None
    return cmd if isinstance(cmd, str) else None


def same_wrapper(a, b):
    """True when two rewrites differ only in their scratch base name, which holds a fresh uuid per call."""
    return WRAP_BASE.sub("stall-watch-UUID", a) == WRAP_BASE.sub("stall-watch-UUID", b)


@posix_case
def agent_foreground_call_gets_no_output():
    """12a. a foreground call with agent_id gets no output, as one without agent_id does: the original runs as typed"""
    orig = "echo agent-fg"
    rc, out, err = hook(orig, agent_id=AGENT_ID, background=False)
    problems = expect(rc == 0, f"hook exit {rc}, want 0: {err.strip()[:200]}")
    problems += expect(out == "", f"foreground agent call: output {out[:120]!r}, want none")
    rc_plain, out_plain, _err = hook(orig, background=False)
    return problems + expect(rc_plain == 0 and out_plain == "",
                             f"foreground call without agent_id: output {out_plain[:120]!r}, want none")


@posix_case
def agent_background_call_gets_export_prefix():
    """12b. a background call with agent_id: its command is the export line, then today's wrapper"""
    orig = "echo agent-bg"
    plain = updated_command(hook(orig)[1])
    if plain is None or "--watch-pid" not in plain:  # scope: the call without agent_id gets the watch wrapper
        return ["scope: the call without agent_id is not rewritten into the watch wrapper"]
    cmd = updated_command(hook(orig, agent_id=AGENT_ID)[1])
    if cmd is None:
        return ["background agent call: no hookSpecificOutput.updatedInput.command"]
    prefix = export_line(AGENT_ID)
    if not cmd.startswith(prefix):
        return ["background agent call: command does not begin with the export line"]
    return expect(same_wrapper(cmd[len(prefix):], plain),
                  "background agent call: the rest is not today's wrapper")


@posix_case
def no_agent_id_call_is_unchanged():
    """12c. a call without agent_id: a foreground call gets no output, and a background command names no tag"""
    orig = "echo agent-none"
    rc, out, _err = hook(orig, background=False)
    problems = expect(rc == 0 and out == "",
                      f"foreground call without agent_id: exit {rc}, output {out[:120]!r}, want none")
    cmd = updated_command(hook(orig)[1])
    if cmd is None:
        return problems + ["background call without agent_id: no updatedInput"]
    return problems + expect(AGENT_TAG not in cmd, "background call without agent_id: the command names the tag")


@posix_case
def malformed_agent_id_is_ignored():
    """12d. a malformed agent_id changes nothing: a foreground call gets no output, and a background call
    gets the wrapper of a call without agent_id"""
    orig = "echo agent-bad"
    plain = updated_command(hook(orig)[1])
    if plain is None:
        return ["scope: the call without agent_id is not rewritten into the watch wrapper"]
    problems = []
    for bad in MALFORMED_AGENT_IDS:
        rc, out, _err = hook(orig, agent_id=bad, background=False)
        found = expect(rc == 0 and out == "", f"agent_id {bad!r}, foreground: output {out[:120]!r}, want none")
        cmd = updated_command(hook(orig, agent_id=bad)[1])
        if cmd is None:
            found += [f"agent_id {bad!r}, background: no updatedInput"]
        else:
            found += expect(same_wrapper(cmd, plain),
                            f"agent_id {bad!r}, background: the command differs from the wrapper without agent_id")
        problems += found
    return problems


@posix_case
def agent_foreground_child_holds_no_tag_on_linux():
    """12e. live: a foreground agent call gets no rewrite, so the harness runs the original as it is, and the
    child it starts holds no CLAUDE_AGENT_ID"""
    if not sys.platform.startswith("linux"):
        raise Skip("Linux only: the child's environment is read from /proc")
    d = new_dir()
    pidfile = os.path.join(d, "child.pid")
    orig = "sleep 30 & echo $! > " + shlex.quote(pidfile)
    out = hook(orig, agent_id=AGENT_ID, background=False)[1]
    if out.strip():
        return ["foreground agent call: the hook rewrote the command (%r), want no output" % out[:120]]
    env = {k: v for k, v in job_env().items() if k != AGENT_TAG}  # nothing in the environment names the tag
    with open(os.path.join(d, "bash.out"), "wb") as out_f:
        run = subprocess.run(["bash", "-c", orig], stdin=subprocess.DEVNULL, stdout=out_f,
                             stderr=subprocess.STDOUT, env=env, timeout=20)
    if run.returncode != 0:
        return [f"original command exit {run.returncode}, want 0"]
    try:
        with open(pidfile) as f:
            pid = int(f.read().strip())
    except (OSError, ValueError):
        return ["the original command wrote no child pid"]
    PIDS.add(pid)
    problems = expect(pid_alive(pid), f"child pid {pid} is not alive")
    if problems:
        return problems
    with open("/proc/%d/environ" % pid, "rb") as f:
        entries = f.read().split(b"\0")
    kill_all([pid])
    return expect(not any(entry.startswith((AGENT_TAG + "=").encode()) for entry in entries),
                  "foreground agent call: its child holds CLAUDE_AGENT_ID")


# The Bash hook commands in settings.json when the agent marker landed: the guard, the stall watch and the
# simulator boot record. The count is the cost: a call starts no process the stall watch entry does not.
PRE_TOOL_USE_BASH_HOOKS = 3


def matches_bash(matcher):
    """True when a PreToolUse matcher covers the Bash tool: empty or `*` covers every tool, else a regex."""
    return not matcher or matcher == "*" or re.fullmatch(matcher, "Bash") is not None


@case
def settings_add_no_bash_hook_process():
    """13. settings.json PreToolUse keeps the same Bash hook commands, one of them stall_watch --hook, and no
    command names a marker: the marker rides the stall watch entry, so a call starts no process of its own"""
    with open(os.path.join(os.path.dirname(HERE), "settings.json"), encoding="utf-8") as f:
        groups = json.load(f)["hooks"]["PreToolUse"]
    bash = [h.get("command", "") for g in groups if matches_bash(g.get("matcher", "")) for h in g.get("hooks", [])]
    every = [h.get("command", "") for g in groups for h in g.get("hooks", [])]
    problems = expect(len(bash) == PRE_TOOL_USE_BASH_HOOKS,
                      f"{len(bash)} Bash hook commands, want {PRE_TOOL_USE_BASH_HOOKS}")
    stall = [c for c in bash if "stall_watch.py" in c and "--hook" in c]
    problems += expect(len(stall) == 1, f"{len(stall)} Bash hook commands run stall_watch.py --hook, want 1")
    named = [c[:80] for c in every if re.search("mark", c, re.I)]
    problems += expect(not named, f"a PreToolUse command names a marker: {named}")
    return problems


if __name__ == "__main__":
    sys.exit(run_cases(CASES))
