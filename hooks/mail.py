"""The git mailbox: one home for the git plumbing, the addresses and the turn-start read (decision session-messages, page item 153).

Messages are files `mail/<addr>/<id>.md` on refs/heads/mail of MAILBOX_REPO. bin/mail sends, reads and takes; local_time.py
calls turn_start_lines on each UserPromptSubmit. The cache is a bare clone (MAILBOX_CACHE, else ~/.claude/mail.git) and only
plumbing touches it, never a working tree. No log is written.

Cost of a turn start: one git process (ls-remote) when the ref has not moved, and no file written. When it moved: at most four
(ls-remote, fetch, grep, log), and files written only in the cache. The four bounds sum to 10 s, so a hung remote costs the
prompt at most 10 s. A failure prints "mail unknown: <reason>", never "no mail".

Cost of `mail wait`: one process, one lock file, and one ls-remote per interval (30 s) while the ref has not moved. A moved
ref adds one fetch and one grep. A wake adds one show (the subject) and the grep's age lookup, one log. Nothing else is
written during a poll.
"""
import hashlib
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _nowindow  # noqa: E402  the one home of a no-window child start

REF = "refs/heads/mail"
# The git bounds of one moved turn start, in seconds. They sum to 10: each step may run its full bound.
REMOTE_BOUND, FETCH_BOUND, GREP_BOUND, LOG_BOUND = 3, 4, 2, 1
TRANSFER_BOUND = 30  # bin/mail's own git calls, which no prompt waits on
LOG_LIMIT = "200"  # commits the age lookup may walk
HEADER = re.compile(r"^Msg (\S+) from (\S+) to (\S+) kind (\S+) re (\S+) try (\d+)")
SAFE = re.compile(r"^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$")
# Platforms that get nothing from the settings.json default: no turn-start line, and `mail` refuses. MAILBOX_HOLD_OFF=1
# lifts it for one command. Empty: no platform is held.
HELD_PLATFORMS = ()
HOLD_OFF = "MAILBOX_HOLD_OFF"
NOT_FF = "[rejected]"  # local fast-forward refusal; a hook or ACL refusal says "[remote rejected]" and is not retried
WINDOWS = sys.platform == "win32"  # read at call time, so a case can drive the Windows branch on any runner
WAIT_INTERVAL, WAIT_MAX_SECONDS = 30, 6600  # `mail wait`: poll gap, and a run that ends before the 2 h background cap
BODY_LIMIT = 160  # characters of a message's first body line that the wake line shows
WAKE_MAX_NAMED = 5  # new messages one poll names in full; the rest count in one "more new" line
BASELINE_RETRY_SECONDS = 300  # how long a failed start read is retried before `mail wait` gives up with exit 2


class MailError(Exception):
    pass


def safe(value):
    """True for a path-safe address or id: no empty part, no `.` or `..` part."""
    return bool(SAFE.match(value)) and not any(part in (".", "..") for part in value.split("/"))


def utf8(text):
    """The one encode of message text: a lone surrogate (a non-UTF-8 byte read in text mode) becomes "?", as text mode did,
    so the pushed blob and the sha the read-back computes hold the same bytes."""
    return text.encode("utf-8", errors="replace")


def git(args, env, cache=None, timeout=TRANSFER_BOUND, input_text=None):
    """One git process. Returns (returncode, stdout, stderr). Raises MailError on a timeout or a missing git.
    No prompt can open: a hook has no terminal to answer it. A ssh command or GIT_SSH program the caller set is kept;
    otherwise ssh runs in batch mode with a 3 s connect bound, which overrides core.sshCommand. The step's timeout kills
    git but not its ssh child, so the connect bound stops a connecting ssh from outliving the step."""
    run_env = dict(env, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    if not env.get("GIT_SSH_COMMAND") and not env.get("GIT_SSH"):
        run_env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes -o ConnectTimeout=3"
    prefix = ["git", "-c", "commit.gpgsign=false"] + (["--git-dir", cache] if cache else [])
    # Bytes in and out: text mode on Windows may rewrite "\n" to "\r\n" on the child's stdin, which would change
    # blob bytes and put a CR in an index path.
    data = None if input_text is None else utf8(input_text)
    try:
        done = _nowindow.run(prefix + args, env=run_env, input=data, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise MailError("timeout")
    except OSError as error:
        raise MailError("git: %s" % error)
    return done.returncode, _text(done.stdout), _text(done.stderr)


def git_bounded(args, env, cache=None, timeout=TRANSFER_BOUND, input_text=None):
    """git() for `mail wait`, whose polls run for hours. Off Windows it is git(). On Windows (read at call time) a timeout
    kills the child's tree and waits with a bound, since subprocess.run would call communicate() again after the kill.
    Own copy of git()'s env and command build: the send path and turn-start read keep git() byte for byte, so the
    Windows child start is scoped to the wait."""
    if not WINDOWS:
        return git(args, env, cache, timeout, input_text)
    run_env = dict(env, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    if not env.get("GIT_SSH_COMMAND") and not env.get("GIT_SSH"):
        run_env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes -o ConnectTimeout=3"
    prefix = ["git", "-c", "commit.gpgsign=false"] + (["--git-dir", cache] if cache else [])
    data = None if input_text is None else utf8(input_text)
    try:
        done = _run_windows(prefix + args, run_env, data, timeout)
    except subprocess.TimeoutExpired:
        raise MailError("timeout")
    except OSError as error:
        raise MailError("git: %s" % error)
    return done.returncode, _text(done.stdout), _text(done.stderr)


def _run_windows(command, env, data, timeout):
    """subprocess.run on Windows calls communicate() again after it kills a timed-out child, and that call can block while
    a grandchild (ssh) holds the pipes open. Here a timeout kills the child's tree (taskkill /T, best effort, since
    Popen.kill ends only the child) and then waits with a bound of 1 s, never calling communicate() again. Unmeasured on
    Windows: whether the tree kill frees the pipes is not known; the cases drive this branch with a fake child."""
    child = _nowindow.Popen(command, env=env, stdin=subprocess.PIPE if data is not None else None,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        out, err = child.communicate(data, timeout=timeout)
    except BaseException:
        try:
            _nowindow.run(["taskkill", "/F", "/T", "/PID", str(child.pid)], capture_output=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            pass  # best effort: the kill below still ends the child itself
        child.kill()
        try:
            child.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
        raise
    return subprocess.CompletedProcess(command, child.returncode, out, err)


def _text(value):
    """Child output as text. A str passes through: test_mail.py's SshBatchDefault patches _nowindow.run with str output."""
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value


def reason(stderr):
    text = stderr or ""
    if re.search(r"Authentication failed|could not read (Username|Password)|Permission denied", text):
        return "auth"
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return "git failed"
    # git ends a refused push with a generic "failed to push some refs" line; the cause sits in an earlier line.
    cause = next((line for line in lines if re.match(r"(! \[(remote )?rejected\]|error:|remote:)", line)), lines[-1])
    return re.sub(r"^(fatal|error): ", "", cause)[:160]


def must(args, env, cache=None, timeout=TRANSFER_BOUND, input_text=None, run=None):
    """git that raises MailError on a failure. `run` replaces git for one caller (mail wait's injected runner)."""
    code, out, err = (run or git)(args, env, cache, timeout, input_text)
    if code:
        raise MailError(reason(err))
    # git exits 0 when core.protectNTFS skips an index path and prints only "Ignoring path" on stderr.
    if "Ignoring path" in (err or ""):
        raise MailError("git ignored a path")
    return out


def cache_path(env):
    return env.get("MAILBOX_CACHE") or os.path.join(os.path.expanduser("~"), ".claude", "mail.git")


def ensure_cache(cache):
    """A bare repo written as files: `git init` would cost a process start the moved-turn bound has no room for."""
    if os.path.exists(os.path.join(cache, "HEAD")):
        return
    for sub in ("objects", "refs"):
        os.makedirs(os.path.join(cache, sub), exist_ok=True)
    with open(os.path.join(cache, "config"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write("[core]\n\trepositoryformatversion = 0\n\tbare = true\n")
    with open(os.path.join(cache, "HEAD"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write("ref: %s\n" % REF)


def remote_tip(env, run=None):
    """The remote mail ref's sha, or None when the store has no mail ref yet."""
    out = must(["ls-remote", env["MAILBOX_REPO"], REF], env, timeout=REMOTE_BOUND, run=run)
    return out.split()[0] if out.strip() else None


def fetch(env, timeout=TRANSFER_BOUND, run=None):
    ensure_cache(cache_path(env))
    must(["fetch", "--quiet", "--no-tags", env["MAILBOX_REPO"], "+%s:%s" % (REF, REF)], env, cache_path(env), timeout, run=run)


def sync(env):
    """Bring the cache to the remote tip. Returns the tip, or None for an empty store."""
    tip = remote_tip(env)
    if tip:
        fetch(env)
    return tip


def commit_tree(env, tip, adds, removes, message):
    """One commit on `tip` (None for the first) that adds {path: bytes-as-text} and removes paths. A temp index inside the cache."""
    cache = cache_path(env)
    ensure_cache(cache)
    index = os.path.join(cache, "mail.index.%d" % os.getpid())
    step = dict(env, GIT_INDEX_FILE=index)
    try:
        must(["read-tree"] + ([tip] if tip else ["--empty"]), step, cache)
        entries = []
        for path, text in adds.items():
            sha = must(["hash-object", "-w", "--stdin"], env, cache, input_text=text).strip()
            entries.append("100644 %s\t%s\n" % (sha, path))
        entries += ["0 %s\t%s\n" % ("0" * 40, path) for path in removes]
        must(["update-index", "--index-info"], step, cache, input_text="".join(entries))
        tree = must(["write-tree"], step, cache).strip()
        verify_tree(env, cache, tree, adds, removes)
        return must(["commit-tree", tree, "-m", message] + (["-p", tip] if tip else []), env, cache).strip()
    finally:
        if os.path.exists(index):
            os.remove(index)


def blob_sha(text):
    data = utf8(text)
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def verify_tree(env, cache, tree, adds, removes):
    """Read the new tree back: each added path holds the blob of its text, each removed path is gone. A silent
    update-index failure leaves the parent's tree, and a CR in an index line leaves a path ending in CR."""
    listing = must(["ls-tree", "-r", "-z", "--full-tree", tree], env, cache)
    held = {}
    for row in listing.split("\0"):
        meta, _, path = row.partition("\t")
        if path:
            held[path] = meta.split()[2]
    if any(held.get(path) != blob_sha(text) for path, text in adds.items()) or any(path in held for path in removes):
        raise MailError("message file missing from the commit")


def push(env, commit):
    """True when the push landed, False on a non-fast-forward (the caller syncs and rebuilds). Any other refusal raises."""
    code, _, err = git(["push", "--quiet", env["MAILBOX_REPO"], "%s:%s" % (commit, REF)], env, cache_path(env))
    if not code:
        return True
    if NOT_FF in err and "[remote rejected]" not in err:
        return False
    raise MailError(reason(err))


def host_slug():
    return re.sub(r"[^a-z0-9-]+", "-", socket.gethostname().lower()).strip("-") or "host"


def git_config(start):
    """The .git/config of the repo that holds `start`, found by walking up. A worktree's .git file leads to the common dir."""
    here = os.path.abspath(start)
    while True:
        dot = os.path.join(here, ".git")
        if os.path.isdir(dot):
            return os.path.join(dot, "config")
        if os.path.isfile(dot):
            with open(dot, encoding="utf-8", errors="replace") as handle:
                gitdir = handle.read().strip().partition("gitdir:")[2].strip()
            gitdir = os.path.join(here, gitdir)
            common = os.path.join(gitdir, "commondir")
            if os.path.exists(common):
                with open(common, encoding="utf-8") as handle:
                    gitdir = os.path.join(gitdir, handle.read().strip())
            return os.path.join(gitdir, "config")
        parent = os.path.dirname(here)
        if parent == here:
            return None
        here = parent


def repo_slug(start):
    """<owner>-<repo> from the origin url in .git/config, or None."""
    config = git_config(start) if start else None
    if not config or not os.path.exists(config):
        return None
    inside = False
    with open(config, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if line.startswith("["):
                inside = line.replace(" ", "") == '[remote"origin"]'
            elif inside and line.startswith("url"):
                parts = [p for p in re.split(r"[/:]", re.sub(r"\.git$", "", line.partition("=")[2].strip())) if p]
                if len(parts) >= 2 and all(re.match(r"^[A-Za-z0-9._-]+$", p) for p in parts[-2:]):
                    return "%s-%s" % (parts[-2], parts[-1])
    return None


def own_addrs(session_id, cwd, env):
    """This session's addresses, most specific first. Cloud: cloud/<id>, where the id `cse_X` is `session_X`. Local:
    pc/<host>/<owner>-<repo>[/<session id>]."""
    cloud = env.get("CLAUDE_CODE_REMOTE_SESSION_ID")
    if cloud:
        cloud = re.sub(r"^cse_", "session_", cloud)
        return ["cloud/%s" % cloud] if safe(cloud) else []
    slug = repo_slug(cwd)
    if not slug:
        return []
    base = "pc/%s/%s" % (host_slug(), slug)
    return ([base + "/" + session_id] if session_id and safe(session_id) else []) + [base]


def open_messages(env, tip, addrs, run=None):
    """[{id, addr, from, kind, re, sent}] for each file directly under mail/<addr>/ at `tip`. Two git processes. A repo
    address is a path prefix of its session addresses, so grep's hits are filtered to the folders named."""
    cache = cache_path(env)
    paths = ["mail/%s/" % addr for addr in addrs]
    code, out, err = (run or git)(["grep", "-I", "--no-color", "-e", "^Msg ", tip, "--"] + paths, env, cache, GREP_BOUND)
    if code not in (0, 1):  # 1 is no match
        raise MailError(reason(err))
    found = {}
    for row in out.splitlines():
        _, path, content = row.split(":", 2)
        match = HEADER.match(content)
        if match and path not in found and path[len("mail/"):path.rindex("/")] in addrs:
            found[path] = match
    times, stamp = {}, None
    if found:
        # The age is a courtesy: a slow or failed lookup leaves "age unknown" and never hides the mail.
        try:
            rows = must(["log", "-n", LOG_LIMIT, "--format=@%ct", "--name-only", "--diff-filter=A", "--no-renames", tip,
                         "--"] + paths, env, cache, LOG_BOUND, run=run).splitlines()
        except MailError:
            rows = []
        for row in rows:
            if row.startswith("@"):
                stamp = int(row[1:])
            elif row:
                times.setdefault(row, stamp)
    return [{"id": m.group(1), "addr": path[len("mail/"):path.rindex("/")],
             "from": m.group(2), "kind": m.group(4), "re": m.group(5), "sent": times.get(path)}
            for path, m in sorted(found.items())]


def age(sent, now):
    if sent is None:
        return "age unknown"
    seconds = max(0, int(now - sent))
    return "%dd" % (seconds // 86400) if seconds >= 86400 else "%dh" % (seconds // 3600) if seconds >= 3600 else "%dm" % (seconds // 60)


def render(messages, now):
    if not messages:
        return []
    lines = ["mail: %d open. Run the line's take command before acting on its message." % len(messages)]
    for m in messages:
        lines.append("mail: %s from %s kind %s%s, %s old; read: `mail read --addr %s %s`; take: `mail take --addr %s %s`" % (
            m["id"], m["from"], m["kind"], "" if m["re"] == "-" else " re " + m["re"], age(m["sent"], now),
            m["addr"], m["id"], m["addr"], m["id"]))
    return lines


def listing_path(env, addrs):
    return os.path.join(cache_path(env), "listing-%s.json" % hashlib.sha1("\n".join(sorted(addrs)).encode()).hexdigest()[:12])


def read_listing(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def held(env):
    """True on a held platform unless the caller sets MAILBOX_HOLD_OFF=1."""
    return sys.platform in HELD_PLATFORMS and env.get(HOLD_OFF) != "1"


def turn_start_lines(payload, env):
    """The lines a UserPromptSubmit hook prints: one per open message, or one "mail unknown: <reason>". Nothing when
    MAILBOX_REPO is unset, the session has no address, or the platform is held (`held`)."""
    if not env.get("MAILBOX_REPO") or held(env):
        return []
    try:
        addrs = own_addrs((payload or {}).get("session_id"), (payload or {}).get("cwd"), env)
        if not addrs:
            return []
        tip = remote_tip(env)
        if not tip:
            return []
        path = listing_path(env, addrs)
        saved = read_listing(path)
        if saved.get("tip") != tip:
            fetch(env, FETCH_BOUND)
            saved = {"tip": tip, "messages": open_messages(env, tip, addrs)}
            tmp = "%s.%d" % (path, os.getpid())
            with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(saved, handle)
            os.replace(tmp, path)
        return render(saved["messages"], time.time())
    except Exception as error:  # a MailError, or a bug: advisory, so it never blocks the prompt
        return ["mail unknown: %s" % error]


def _pid_alive(pid):
    if WINDOWS:  # os.kill would end the process there, so ask for its exit code
        try:
            import ctypes
            kernel = ctypes.windll.kernel32
            handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                return False
            code = ctypes.c_ulong()
            ok = kernel.GetExitCodeProcess(handle, ctypes.byref(code))
            kernel.CloseHandle(handle)
            return bool(ok) and code.value == 259  # STILL_ACTIVE
        except Exception:
            return True  # unknown reads as alive: the lock deadline still ends a stale waiter
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True  # EPERM: the process exists
    return True


def _start_time(pid):
    """The process start time in clock ticks since boot, or None where /proc has none. It tells a reused pid from the
    process that wrote a lock."""
    try:
        with open("/proc/%d/stat" % pid, encoding="utf-8") as handle:
            return float(handle.read().rpartition(")")[2].split()[19])
    except (OSError, ValueError, IndexError):
        return None


def _read_lock(path):
    try:
        with open(path, encoding="utf-8") as handle:
            record = json.load(handle)
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def _lock_is_stale(record, now, pid_alive, start_time):
    """Stale: unreadable, its pid is dead, its deadline has passed, or its pid now started at another time (a reused pid)."""
    if record is None or not isinstance(record.get("pid"), int) or not pid_alive(record["pid"]):
        return True
    if not isinstance(record.get("deadline"), (int, float)) or record["deadline"] <= now:
        return True
    began = start_time(record["pid"])
    return began is not None and record.get("started") is not None and record["started"] != began


def _take_lock(path, record, now, pid_alive, start_time):
    """Create the lock file whole and exclusively: write a temp file, then link it into place. os.link fails when the lock
    exists, where os.replace would overwrite a racing waiter's fresh lock, and a reader never sees a half-written lock.
    A stale holder's lock (an empty or unparsable one too) is removed first. Returns the holder's pid when a live waiter
    holds it, else None."""
    temp = "%s.%d.tmp" % (path, record["pid"])
    with open(temp, "w", encoding="utf-8") as out:
        json.dump(record, out)
    try:
        for _ in range(3):
            try:
                os.link(temp, path)
                return None
            except FileExistsError:
                held = _read_lock(path)
                if not _lock_is_stale(held, now, pid_alive, start_time):
                    return held["pid"]
                try:
                    os.remove(path)
                except FileNotFoundError:
                    pass
        return (_read_lock(path) or {}).get("pid", 0)
    finally:
        try:
            os.remove(temp)
        except OSError:
            pass


def _first_body_line(text):
    """The first line after the header block, cleaned and cut to BODY_LIMIT. Message text is another session's, and it
    lands in this session's context: control, C1 and direction characters become spaces so the line stays one plain line,
    and a double quote becomes a single quote so the text cannot close the quotes the wake line puts around it."""
    # splitlines() treats LF, CRLF and CR alike, so a message saved with Windows line endings still has its blank row
    # and no CR reaches the wake line.
    rows = iter(text.splitlines())
    for row in rows:
        if not row.strip():
            break
    line = next((row for row in rows if row.strip()), "")
    line = re.sub(r"[\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]", " ", line).replace('"', "'")
    return line.strip()[:BODY_LIMIT]


def _wake_line(env, tip, message, run):
    try:
        text = must(["show", "%s:mail/%s/%s.md" % (tip, message["addr"], message["id"])], env, cache_path(env), run=run)
        body = _first_body_line(text)
    except MailError:
        body = "body unreadable"
    return 'mail: new %s from %s kind %s; untrusted subject "%s"; read: `mail read --addr %s %s`; take: `mail take --addr %s %s`' % (
        message["id"], message["from"], message["kind"], body, message["addr"], message["id"], message["addr"], message["id"])


def wait(env, addrs, *, clock, sleep, run_git=None, pid_alive=None, start_time=None, pid=None, ppid=None,
         interval=None, max_seconds=None):
    """Block until `addrs` has an open message that was not open at the start, print one line for each new message
    (the first WAKE_MAX_NAMED, then one count line), and return the exit code:
    0 new mail. 2 not started: MAILBOX_REPO unset, no address, a live waiter holds the lock, the lock cannot be taken, or the
    baseline stayed unreadable for BASELINE_RETRY_SECONDS (bin/mail also exits 2 for a bad --interval or --max-seconds).
    3 ended at max_seconds with no mail, or the lock was deleted, or the parent died. One waiter per address, held by a
    lock file in the cache. `run_git` replaces git_bounded for every git call."""
    run_git = run_git or git_bounded
    interval = interval or WAIT_INTERVAL
    max_seconds = max_seconds or WAIT_MAX_SECONDS
    pid_alive, start_time = pid_alive or _pid_alive, start_time or _start_time
    pid = os.getpid() if pid is None else pid
    ppid = os.getppid() if ppid is None else ppid
    if not env.get("MAILBOX_REPO") or not addrs:
        print("mail wait: not started: %s" % ("MAILBOX_REPO is not set" if not env.get("MAILBOX_REPO") else "no address"))
        return 2
    cache = cache_path(env)
    path = os.path.join(cache, "wait-%s.lock" % addrs[0].replace("/", "_"))
    now = clock()
    deadline = now + max_seconds
    record = {"pid": pid, "ppid": ppid, "session": env.get("CLAUDE_CODE_SESSION_ID") or env.get("CLAUDE_CODE_REMOTE_SESSION_ID"),
              "started": start_time(pid), "deadline": deadline}
    try:
        os.makedirs(cache, exist_ok=True)
        holder = _take_lock(path, record, now, pid_alive, start_time)
    except OSError as error:  # no cache folder, or a filesystem without hard links: say so, never run lockless
        print("mail wait: not started: cannot take the lock: %s" % error)
        return 2
    if holder is not None:
        print("mail wait: not started: another waiter holds the lock (pid %s)" % holder)
        return 2

    def stop(signum, frame):
        raise SystemExit(128 + signum)

    def still_mine():
        """False when the lock is gone or replaced, or the parent is dead: the session no longer wants this waiter."""
        held = _read_lock(path)
        return bool(held) and held.get("pid") == pid and pid_alive(ppid)

    try:
        previous = signal.signal(signal.SIGTERM, stop)
    except ValueError:  # not the main thread: no handler, and the lock still goes in the finally
        previous = None
    try:
        # The baseline: what is open now never wakes the waiter. An empty store has no ref, so nothing is open.
        # A failed read is retried for BASELINE_RETRY_SECONDS: a waiter with no baseline would call every open message new.
        give_up = clock() + BASELINE_RETRY_SECONDS
        while True:
            try:
                tip = remote_tip(env, run_git)
                seen = set()
                if tip:
                    fetch(env, run=run_git)
                    seen = {m["id"] for m in open_messages(env, tip, addrs, run_git)}
                break
            except MailError as error:
                if clock() >= give_up:
                    print("mail wait: not started: %s" % error)
                    return 2
            sleep(interval)
            if not still_mine():
                print("mail wait: ended, no mail")
                return 3
        while clock() < deadline:
            sleep(interval)
            if not still_mine():
                break
            try:
                now_tip = remote_tip(env, run_git)
                if not now_tip or now_tip == tip:
                    continue
                fetch(env, run=run_git)
                fresh = [m for m in open_messages(env, now_tip, addrs, run_git) if m["id"] not in seen]
                tip = now_tip
                if fresh:
                    for message in fresh[:WAKE_MAX_NAMED]:
                        print(_wake_line(env, now_tip, message, run_git))
                    if len(fresh) > WAKE_MAX_NAMED:
                        print("mail: %d more new; read: `mail read --addr %s`" % (len(fresh) - WAKE_MAX_NAMED, fresh[0]["addr"]))
                    return 0
            except MailError:
                continue  # a transient failure: the tip stays as it was, so the next poll tries the same move again
        print("mail wait: ended, no mail")
        return 3
    finally:
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)
        held = _read_lock(path)
        if held and held.get("pid") == pid:
            try:
                os.remove(path)
            except OSError:
                pass
