#!/usr/bin/env python3
"""The shared merge tool, git half. The flow is `confirm` in merge/merge.py.

  merge <pr>              preview: what it would claim and merge, and the silent-undo check on the head. Presses
                          nothing. A draft is previewed too; a dropped line prints one `BLOCKED:` line and exits 1.
                          A `Drops-lines:` line in the PR body excuses its path, as a commit trailer does.
  merge <pr> --confirm [--session NAME]   lock, claim, rebuild the records page, push, wait, merge, sync the local base, clean up.
  merge --unlock [branch] remove the merge lock on the branch (default: the default branch). Reads no lock state first.
  merge --role TIER       cloud only: record this session's merge role (coordinator or batch-runner). In a cloud session `--confirm`
                          runs only when that role is recorded for the session (read_merge_role).

Git half: the merge lock, the temporary worktree, the claim, the push, the revert, resume, the
local base branch, afterMerge and the branch delete. GitHub half (`Host`): required checks, the wait,
the minute read and the merge with its head guard. Every read is a `gh api` REST call: a Claude Code cloud session answers GraphQL with HTTP 403.
`gh` 2.48 or newer is needed (`--paginate --slurp`); an older gh fails closed.
A cloud session runs the whole flow (c53): its proxy passes `gh api` reads, PUT pulls/N/merge and a push to refs/heads, so the lock is a
git push there (default_lock). Its proxy refuses a ref delete: the lock is released by an expired commit, and the branch deletes print "not deleted".
"""
import argparse, ast, contextlib, datetime, json, math, os, pathlib, re, shutil, posixpath, signal, socket, subprocess, sys, tempfile, threading, time, uuid
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
try:
    import _nowindow  # the one home of a no-window child start (hooks/_nowindow.py)
except ImportError:  # a hook loads this file; a missing helper never stops that hook
    _nowindow = subprocess

STAMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "actions", "stamp", "stamp.mjs")
RECORDS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lint", "hook_catalog.py")  # the records-page generator; the tool brings it, a repo adds nothing
sys.path.insert(0, os.path.dirname(RECORDS))
try:
    from hook_catalog import RECORDS_PAGE  # noqa: E402  the page the generator writes; one home, so a conflict on the page is told from any other
except Exception as e:  # a missing or broken module: one line, no traceback when run; an ImportError when imported
    _why = "merge: cannot load the records generator, module hook_catalog (lint/hook_catalog.py): " + " ".join(f"{type(e).__name__}: {e}".split())
    if __name__ == "__main__":
        sys.exit(_why)
    raise ImportError(_why) from e  # an importer, such as the merge guard, must see a failed load, not a process exit

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))  # guard_core, which cut_lanes loads

class Stop(Exception):
    """A refusal. The message is the whole report."""

class NetStop(Stop):
    """A `gh` call kept failing with a network error. Not a refusal: the caller must not revert a claim for it."""

class Dropped(Stop):
    """The silent-undo check found a dropped line."""

class Held(Stop):
    pass

SH_TIMEOUT = None  # seconds; the guard sets it, so a hung `gh` cannot outlast its hook

def resolve_program(name, env=None):
    """Find the real program by full path. One home for sh(), block() and after_merge().

    On Windows CreateProcess never reads PATHEXT, so a bare `gh` misses `gh.cmd`: shutil.which
    covers that. For `bash` specifically, Windows also lists C:\\Windows\\System32 ahead of
    Git's own bin on PATH, and that folder holds the WSL launcher stub, not Git Bash (decision
    bare-bash-on-windows-can-resolve-to-the-wsl-stub). So bash never resolves to anything under
    System32: check %ProgramFiles%\\Git\\bin\\bash.exe (and the x86/W6432 copies) first, then a
    PATH scan that skips System32. On POSIX this is plain shutil.which."""
    env = env or os.environ
    path = env.get("PATH")
    if name == "bash" and os.name == "nt":
        for var in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
            base = env.get(var)
            if base:
                candidate = os.path.join(base, "Git", "bin", "bash.exe")
                if os.path.isfile(candidate):
                    return candidate
        system_root = os.path.normcase(os.path.join(env.get("SystemRoot", r"C:\Windows"), "System32"))
        for folder in (path or "").split(os.pathsep):
            if os.path.normcase(folder).startswith(system_root):
                continue
            candidate = os.path.join(folder, "bash.exe")
            if os.path.isfile(candidate):
                return candidate
    return shutil.which(name, path=path) or name

# Set only inside `shared_deadline`, below. A fixed per-call SH_TIMEOUT would let a hung `gh`
# hold the read for each call in turn; one shared deadline bounds the whole read. `Host.head_read` makes four calls (five with a branch name,
# more for the batch read of a settled head) for one read, so it shares a single deadline across them instead: each call gets whatever of
# that one budget the earlier calls left.
_READ_DEADLINE = None

@contextlib.contextmanager
def shared_deadline(seconds):
    """Give every `sh()` call made in this block one shared time budget (seconds) instead of the
    fixed SH_TIMEOUT each would otherwise get. `seconds=None` is a no-op: sh() keeps using
    SH_TIMEOUT alone, as it does everywhere outside this context."""
    global _READ_DEADLINE
    prior = _READ_DEADLINE
    _READ_DEADLINE = (time.monotonic() + seconds) if seconds is not None else None
    try:
        yield
    finally:
        _READ_DEADLINE = prior

def sh(args, cwd=None, input=None, env=None, timeout=None):
    args = [resolve_program(args[0], env), *args[1:]]
    limits = [t for t in (SH_TIMEOUT, timeout) if t is not None]
    timeout = max(0.05, _READ_DEADLINE - time.monotonic()) if _READ_DEADLINE is not None else min(limits) if limits else None
    r =_nowindow.run(args, cwd=cwd, input=input, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    return r.returncode, (r.stdout + r.stderr).strip()

def git(cwd, *a, input=None):
    return sh(["git", "-C", cwd, *a], input=input)

RULE_FILES = ("claude.md", ".claude/claude.md")  # lower case: the match ignores case. Plus each file under RULE_PREFIX (decision claude-md-change-is-flagged)
RULE_PREFIX = "output-styles/"
SETTLE_SECONDS = 30
NET_RETRIES, NET_PAUSE = 3, 5  # retry a network error 3 times, a short pause between (standing-merge-grant)
RATE_LADDER = (60, 300, 900)  # seconds, one wait per retry (standing-merge-grant). GitHub's own reset time, when `gh api -i` gives one, is the wait instead. The last rung is the cap on any wait.
# A rate-limit text (gh prints these on a 403 or 429): the wrapped HTTPError line, the GraphQL line, and `gh api`'s last line. Same anchors as the 5xx forms.
_RATE_WRAPPED = r"(?:^|: )HTTP 403: (?:API rate limit|You have exceeded a secondary rate limit)[^\n]*\(https?://\S+\)\s*$"
_RATE_GRAPHQL = r"^GraphQL: (?:API rate limit (?:already )?exceeded|You have exceeded a secondary rate limit)"
_RATE_API_TAIL = r"gh: (?:API rate limit|You have exceeded a secondary rate limit)[^\n]*\(HTTP 403\)\s*\Z"
_RATE_429 = (r"^(?:gh: )?(?:Server Error \()?HTTP 429\b|(?:^|: )HTTP 429(?:: [^\n]*)? \(https?://\S+\)\s*$"
             r"|gh: (?:[^\n]*\()?HTTP 429\)?\s*\Z")  # a 429 is a rate limit too (owner via the coordinator)
RATE_LIMIT = re.compile(f"{_RATE_WRAPPED}|{_RATE_GRAPHQL}|{_RATE_API_TAIL}|{_RATE_429}", re.I | re.M)
# A network error, anchored on the error line, never on refusal text (a PR title "#502 Bad Gateway fix" is no match):
# gh's Go transport error `Post "https://...": <cause>`, gh's offline line, gh's own server-error lines at the start of a line
# (`HTTP 502 (url)`, `HTTP 500: ...`, `gh: HTTP 503`, `gh: Server Error (HTTP 502)`, `GraphQL: Something went wrong ...`),
# gh's HTTPError after a command's prefix (`failed to get runs: HTTP 502: 502 Bad Gateway (https://...)`; a title has no
# trailing url), a rate-limit 403 in the same wrapped form (`HTTP 403: API rate limit exceeded ... (https://...)`, a permission 403 is
# no match), gh's GraphQL rate-limit line, `--jq` on an HTML gateway page, a truncated reply, git's transport lines (SSL only after curl's
# `unable to access '<url>': `, so a branch `ssl-fix` is no match). Never free text: a PR title "Fix (HTTP 502 retry)"
# or a check "build: HTTP 500 guard" is no match. The one home: Host.gh, the fetch and both lock reads ask is_net.
NET_ERROR = re.compile(r"(?:^|: )(?:(?:Post|Get|Put|Patch|Delete|Head) \x22https?://[^\x22\s]*\x22: |error connecting to )"
                       r"|^(?:gh: )?(?:Server Error \()?HTTP (?:5\d\d|429)\b|^GraphQL: Something went wrong"
                       r"|(?:^|: )HTTP (?:5\d\d|429)(?:: [^\n]*)? \(https?://\S+\)\s*$"
                       f"|{_RATE_WRAPPED}|{_RATE_GRAPHQL}"
                       r"|^invalid character '<' looking for beginning of value"
                       r"|^(?:fatal|error): .*(?:Could not resolve (?:host|proxy)|Failed to connect|Connection was reset|connection reset|connection refused|connectex|wsarecv|"
                       r"schannel|unable to access '[^']*': .*\bSSL\b|GnuTLS|timed out|context deadline exceeded|Recv failure|the remote end hung up|early EOF|RPC failed|returned error: 5\d\d|"
                       r"HTTP/2 stream|Empty reply from server|Failed sending data)"
                       r"|^ssh: (?:connect to host|Could not resolve hostname)|^kex_exchange_identification\b|^unexpected end of JSON input", re.I | re.M)
# `gh api` on a 5xx prints the body to stdout with no newline, then its own line to stderr. Measured with gh 2.98.0:
# `{"message": "Server Error"}gh: Server Error (HTTP 502)` and `<html>...</html>gh: HTTP 502`. That line ends the output.
GH_API_TAIL = re.compile(r"gh: (?:[^\n]*\()?HTTP (?:5\d\d|429)\)?\s*\Z|" + _RATE_API_TAIL, re.I)

def is_net(c, out):
    """A failed call whose output is a network error line. JSON is gh's answer (a check named EOF), not its error line,
    unless gh's own 5xx line ends it."""
    return bool(c and (GH_API_TAIL.search(out) or (NET_ERROR.search(out) and not out.lstrip().startswith(("[", "{")))))

_HEAD_BLOCK = re.compile(r"HTTP/\d(?:\.\d)? \d{3}\b[^\n]*(?:\n(.*?\r?\n)?\r?\n|\n?.*\Z)", re.S)  # what `gh api -i` prints first: the status line, the headers, a blank line. An empty body leaves no blank line: the block then runs to the end

def split_headers(out):
    """-> (headers, body). A reply that starts with a status line has a header block: its names are lower case in `headers`, and `body` has no block.
    A header-like line anywhere else is text, and the body is the whole reply."""
    m = _HEAD_BLOCK.match(out)
    if not m:
        return {}, out
    pairs = (line.partition(":") for line in m.group(0).splitlines()[1:])
    return {k.strip().lower(): v.strip() for k, sep, v in pairs if sep}, out[m.end():]

def _seconds(value):
    """A header value as whole seconds, or None when it is not a number."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

def rate_wait(headers, n, now):
    """Whole seconds to wait before retry n of a rate limit. `Retry-After` always counts. `X-Ratelimit-Reset` (an epoch) counts only while
    `X-Ratelimit-Remaining` is 0, as GitHub documents. A header that is missing, unreadable or not in the future gives the ladder rung. Capped at the last rung."""
    after = _seconds(headers.get("retry-after"))
    reset = _seconds(headers.get("x-ratelimit-reset"))
    if after is None or after <= 0:
        after = reset - now if reset is not None and headers.get("x-ratelimit-remaining") == "0" else 0
    return min(math.ceil(after) if after > 0 else RATE_LADDER[min(n, len(RATE_LADDER)) - 1], RATE_LADDER[-1])  # whole seconds, rounded up

def retry_net(call, pause, retries=NET_RETRIES, what="the call", now=time.time, before_wait=None):
    """-> (code, output, retries used). The output has no `gh api -i` header block. Runs `call` again after `pause(wait)` while it fails with a network
    error, up to `retries` times. The wait is NET_PAUSE, or on a rate limit rate_wait(). Before a rate wait it prints one line that names `what`.
    `before_wait(wait)` runs before each rate wait. It extends the merge lock past the wait, or raises NetStop: then the call stops in place of the wait."""
    n = 0
    while True:
        c, out = call()
        headers, out = split_headers(out)
        if n >= retries or not is_net(c, out):
            return c, out, n
        n += 1
        if not RATE_LIMIT.search(out):
            pause(NET_PAUSE)
            continue
        wait = rate_wait(headers, n, now())
        if before_wait:
            try:
                before_wait(wait)
            except NetStop as e:
                raise NetStop(f"{what} hit a GitHub rate limit, and the wait of {wait} s needs the merge lock extended first. {e}\n{out}") from None
        say(f"merge: {what} hit a GitHub rate limit; waiting {wait} s, then retry {n} of {retries}.")
        pause(wait)

UNDO_MEMO = {}

def undo_check(wt, base_ref, unknown_ok="", pr_body=""):
    """The shared silent-undo lint (lint/check_silent_undo.py), run on the branch before anything is pushed.
    A finding refuses. An unreadable history refuses too, unless the owner passed
    --undo-check-unknown-ok "<reason>": that is the way out when the check cannot run (octopus merge,
    git older than 2.38, shallow clone). It is logged and does not excuse a finding."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lint"))
    import check_silent_undo as undo
    # The scan is slow on a merge-heavy branch and merge runs it twice. Its answer depends only on the head, the base tip, the PR body,
    # and the default refs it reads, so the second call reuses the first when all of them are unchanged.
    try:
        key = (wt, *(git(wt, "rev-parse", "--verify", "-q", r + "^{commit}")[1].strip() for r in ("HEAD", base_ref, "origin/HEAD", "origin/main", "main")), pr_body)
        if not (key[1] and key[2]) or key not in UNDO_MEMO:  # a head or base that does not resolve is never reused; a hit skips the scan and its beat
            c, n = git(wt, "rev-list", "--count", f"{base_ref}..HEAD")
            say(f"merge: scanning for silent undos ({n.strip() if not c else '?'} commits) ...")  # the scan can run for minutes
            t0, done, at = time.time(), threading.Event(), [0, 0]  # at: the scan's file counter, set by its progress hook
            undo.progress = lambda i, total: at.__setitem__(slice(None), [i, total])

            def beat():  # a line every 60 s, with the count, so a reader sees the scan move
                while not done.wait(60):
                    where = f"file {at[0]}/{at[1]}" if at[1] else "reading the history"
                    say(f"merge: silent-undo scan: {where}, {(time.time() - t0) / 60:.0f} min")

            beater = threading.Thread(target=beat, daemon=True)
            beater.start()
            try:
                UNDO_MEMO[key] = undo.check(wt, base_ref, "HEAD", tool=RECORDS, pr_body=pr_body)  # a base with no generator: the page is judged by the generator that rebuilds it
            finally:  # the beat stops, and is joined, before any line below: no beat prints after "scan done"
                done.set()
                beater.join()
                undo.progress = None  # the hook is the scan's alone
            say(f"merge: silent-undo scan done ({time.time() - t0:.0f} s)")
        res = UNDO_MEMO[key]
    except subprocess.TimeoutExpired as e:  # a read that timed out is unknown, and is not remembered
        res = undo.Unknown(f"a git read timed out after {e.timeout:.0f}s")
    except undo.Unknown as e:
        res = UNDO_MEMO[key] = e
    if isinstance(res, Exception):  # an Unknown; the scanner is never asked for its class here
        e = res
        if unknown_ok.strip():
            say(f"merge: silent-undo check UNKNOWN ({e}). Owner override, reason: {unknown_ok.strip()}")
            return
        raise Stop(f"silent-undo check could not read the history: {e}\nIf the owner accepts that, run again with --undo-check-unknown-ok \"<reason>\".")
    problems, notes = res
    for n in notes:
        say("merge: " + n)
    if problems:
        raise Dropped("the branch silently undoes earlier work:\n  " + "\n  ".join(problems) + f"\nPut it back, or add the trailer `{undo.TRAILER}: <path> -- <reason>` to a commit message.")

def say(*lines):
    text = "\n".join(lines)  # one line each: the preview is a list of indented lines, never one long line
    try:
        print(text, flush=True)
    except UnicodeEncodeError:  # a piped Windows stdout is cp1252, strict: escape what it cannot hold, so no name can stop the steps after a merge. stderr already escapes
        enc = sys.stdout.encoding or "ascii"
        print(text.encode(enc, "backslashreplace").decode(enc), flush=True)

# ------------------------------------------------------------------ the merge lock
# A lock is a commit that a ref points at. The commit message holds the expiry. The ref is
# refs/heads/merge-lock/<defaultBranch>: a branch, because the cloud proxy refuses a push to any ref outside refs/heads.
# Two backends, one interface: acquire, release, unlock. A Claude Code cloud session uses GitLock (default_lock).

SESSION_MAX = 80  # characters of --session kept; the spec names no cap
LOCK_MARGIN = 300  # seconds: before a rate wait of W s the lock's expiry moves to now + W + this
LOCK_MAX_HOLD = 6 * 3600  # seconds: the hard bound on one run's hold, counted from the take. No rate wait extends the lock past it (a rate wait is the exception to the 600 s cap; standing-merge-grant)

def lock_ref(b):
    """The one name of the lock ref. Mac and cloud runs must share it, or each would hold a lock the other cannot see."""
    return f"refs/heads/merge-lock/{b}"

def old_lock_ref(b):
    """The lock name before c53. A Mac run of older merge.py still takes it, so a GitLock (cloud) take refuses while it is live.
    One way only: an old run never reads the new name, so it can take the old name while a cloud run holds the new one. Only the Mac's
    reinstall from main at each merge closes that. GhLock skips this read for the same reason. Delete this and its read once no install
    runs a merge.py older than c53."""
    return f"refs/merge-lock/{b}"

def refuse_old_lock(b, old, now):
    if old and old[1] > now:
        raise Held(holder_text(b, old, now) + " It holds the lock under the old name: that run is on merge.py from before c53.")

def boot_stamp():
    """One text per boot of this machine, or "" when it cannot be read. Cloud VMs share a hostname and each has its own pid numbers, so a pid
    absent here proves a holder dead only on the machine that booted when the lock was taken. Linux: the boot id. macOS: kern.boottime
    seconds. Windows: boot time from the tick count (seconds; same_boot allows the drift)."""
    try:
        if sys.platform.startswith("linux"):
            with open("/proc/sys/kernel/random/boot_id", encoding="ascii") as f:
                return f.read().strip() + ":" + os.readlink("/proc/self/ns/pid")  # a container's pid numbers are its own, on the same boot
        if sys.platform == "darwin":
            m = re.search(r"sec = (\d+)", sh(["sysctl", "-n", "kern.boottime"], timeout=10)[1])
            return m.group(1) if m else ""
        if os.name == "nt":
            import ctypes
            tick = ctypes.WinDLL("kernel32").GetTickCount64
            tick.restype = ctypes.c_ulonglong  # the default c_int wraps after 24.9 days
            return str(int(time.time() - tick() / 1000))
    except (OSError, ValueError, subprocess.SubprocessError, AttributeError):
        pass
    return ""

def same_boot(a, b):
    """Both stamps read, and equal. Number stamps (macOS, Windows) may differ by two minutes of clock drift."""
    if not a or not b:
        return False
    if a.isdigit() and b.isdigit():
        return abs(int(a) - int(b)) <= 120
    return a == b

def lock_message(ttl, now, holder=None):
    """`holder` holds pr, branch, session. The session is untrusted text: one line, capped, so it cannot add an `expires:` or `owner:` line."""
    lines = [f"merge lock\nexpires: {int(now + ttl)}\nowner: {uuid.uuid4().hex}"]
    if holder:
        lines += [f"pr: {holder['pr']}", "branch: " + " ".join(str(holder["branch"]).split()), f"host: {socket.gethostname()}", f"platform: {sys.platform}",
                  f"pid: {os.getpid()}", f"started: {int(now)}"]
        if boot_stamp():
            lines.append("boot: " + boot_stamp())
        session = " ".join(holder.get("session", "").split())[:SESSION_MAX]  # fold first, then test: a blank one writes no line
        if session:
            lines.append("session: " + session)
    return "\n".join(lines)

def expiry_of(message):
    m = re.search(r"^expires: (\d+)$", message, re.M)
    return int(m.group(1)) if m else float("inf")  # not ours: never expires, only --unlock removes it

def pid_alive(pid):
    """Windows never gets os.kill(pid, 0): signal 0 is CTRL_C_EVENT there."""
    if os.name == "nt":
        import ctypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ctypes.get_last_error() == 5  # access denied: it exists
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return not ok or code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return True  # ponytail: a reused pid reads alive. That is the safe side. A start-time check would close it.

def holder_text(b, held, now):
    """The one description of a lock's holder. `held` is read()'s (sha, expiry, message)."""
    f = dict(re.findall(r"^(\w+): (.*)$", held[2], re.M))
    who = f"PR #{f['pr']}" if "pr" in f else "an unknown holder"
    extra = [f"branch {f['branch']}"] if "branch" in f else []
    if "session" in f:
        extra.append(f'session "{f["session"]}"')
    text = f"the merge lock on {b} is held by {who}" + (f" ({', '.join(extra)})" if extra else "")
    if "pid" in f and "host" in f:
        text += f", pid {f['pid']} on {f['host']}"
    started_ok = re.fullmatch(r"[0-9]{1,10}", f.get("started", ""))  # a garbled field means a forged lock: trust none of it
    if started_ok:
        text += ", started " + time.strftime("%H:%M:%SZ", time.gmtime(int(f["started"])))
    text += f", expires in {held[1] - now:.0f}s." if held[1] != float("inf") else ", never expires."
    state = holder_state(held)
    if state == "alive":
        return text + " The holder is alive. Wait for it, or ask its session."
    if state == "dead":
        return text + " The holder is dead. The next merge run takes the lock over."
    return text + " Cannot tell if the holder is alive. Ask its owner before: merge --unlock"

def holder_state(held):
    """-> "alive", "dead" or "unknown" for the holder of a lock `held` (read()'s (sha, expiry, message)). Dead only for a pid on this host, platform and boot:
    a lock with no boot line, or one from another boot, reads unknown."""
    f = dict(re.findall(r"^(\w+): (.*)$", held[2], re.M))
    started_ok = re.fullmatch(r"[0-9]{1,10}", f.get("started", ""))  # a garbled field means a forged lock: trust none of it
    pid = int(f["pid"]) if re.fullmatch(r"[0-9]{1,10}", f.get("pid", "")) else 0
    if f.get("host") == socket.gethostname() and f.get("platform") == sys.platform and started_ok and 0 < pid < 2 ** 31:  # a pid from another OS reads nothing
        if pid_alive(pid):
            return "alive"
        return "dead" if same_boot(f.get("boot", ""), boot_stamp()) else "unknown"
    return "unknown"

def refuse_or_take_over(b, held, now):
    """A live lock stops the run (Held), unless its holder's pid is dead on this host: then one line says so and the take goes on, as for an expired lock."""
    if holder_state(held) != "dead":
        raise Held(holder_text(b, held, now))
    f = dict(re.findall(r"^(\w+): (.*)$", held[2], re.M))
    say(f"merge: took over the merge lock on {b}: its holder, PR #{f.get('pr', '?')} (branch {f.get('branch', '?')}), pid {f['pid']} on {f['host']}, is dead.")

@contextlib.contextmanager
def release_on_signals():
    """SIGTERM and SIGINT end the run through its `finally`, which releases the merge lock. A second signal while it releases is ignored.
    Where signal handlers cannot be set (another thread), nothing changes."""
    names = [signal.SIGTERM, signal.SIGINT]
    def stop(sig, frame):
        for n in names:
            signal.signal(n, signal.SIG_IGN)
        raise SystemExit(128 + sig)
    try:
        before = {n: signal.signal(n, stop) for n in names}
    except ValueError:
        yield
        return
    try:
        yield
    finally:
        for n, h in before.items():
            signal.signal(n, h)

class Lock:
    """What both backends share: a release that reports and never raises (it runs in a `finally`)."""
    until = holder = began = tree = message = None  # holder: set by confirm before acquire; a dict of pr, branch, session. until: the published expiry, set once the lock is held
    mine = frozenset()  # the lock commits this run made: the take, then one per extension, added before its push or PATCH

    def _take(self, b, sha, tree, message, now):
        """The one place a take is recorded. The expiry is read back from the published text, so `until` and the text cannot differ."""
        self.base, self.sha, self.tree, self.message, self.began = b, sha, tree, message, now
        self.mine, self.until = frozenset({sha}), expiry_of(message)

    def extend_for(self, wait):
        """Before a rate wait of `wait` s: publish an expiry that covers now + wait + LOCK_MARGIN, then return. NetStop when the lock cannot be
        extended (rate limit, the ref moved) or the hard bound LOCK_MAX_HOLD would pass: the run never waits on a lock that could expire.
        No-op while no lock is held."""
        if self.until is None:
            return
        now = self.now()
        if self.until <= now:  # expired: acquire frees a lock at expiry <= now, so a rival may hold it already. Never extend it
            raise NetStop(f"the merge lock on {self.base} expired before the rate wait, so another run may hold it now. Run again.")
        need = int(now + wait + LOCK_MARGIN)
        if need <= self.until:
            return
        if need > self.began + LOCK_MAX_HOLD:
            raise NetStop(f"the merge lock on {self.base} cannot be held past {LOCK_MAX_HOLD} s from the take. Run again.")
        msg = re.sub(r"^expires: \d+$", f"expires: {need}", self.message, flags=re.M)
        try:
            sha = self.swap(self.base, msg)
        except Stop as e:
            raise NetStop(f"cannot extend the merge lock on {self.base} for a wait of {wait} s, so the run stops in place of waiting on a lock that could expire. Run again. {e}") from e
        self.sha, self.message, self.until = sha, msg, expiry_of(msg)

    def release(self, b, token):
        left = f" It expires in {max(0, self.until - self.now()):.0f}s." if self.until else ""
        try:
            cur = self.read(b)
            if not cur or (cur[0] != token and not {token, cur[0]} <= self.mine):  # owned: the ref holds the token, or a later commit of this run (an extension) and the token is this run's too
                say(f"merge: the lock on {b} was not this run's any more. Someone removed it during the run. Left as is.")
                return
            c, why = self.delete(b, cur[0])
            if not c:
                return
        except Exception as e:
            why = str(e)
        finally:
            self.until = None  # no lock is held after this: a later rate wait extends nothing
        say(f"merge: the lock release failed: {why}.{left} Run merge --unlock only if no run holds it.")

class GitLock(Lock):
    """Any git remote. Tests use a local bare origin. The create-only push is the one arbiter."""
    def __init__(self, root, now=time.time, pause=time.sleep):
        self.root, self.now, self.pause = root, now, pause

    def read(self, b, ref=None):
        ref = ref or lock_ref(b)
        c, out, _ = retry_net(lambda: git(self.root, "ls-remote", "origin", ref), self.pause, what=f"the lock read {ref}")
        if c:
            raise (NetStop if is_net(c, out) else Stop)("cannot read the merge lock: " + out)
        if not out:
            return None
        if git(self.root, "fetch", "-q", "origin", ref)[0]:
            return out.split()[0], float("inf"), ""
        msg = git(self.root, "log", "-1", "--format=%B", "FETCH_HEAD")[1]
        return out.split()[0], expiry_of(msg), msg

    def acquire(self, b, ttl):
        ref = lock_ref(b)
        cur = self.read(b)
        if cur and cur[1] > self.now():
            refuse_or_take_over(b, cur, self.now())
        refuse_old_lock(b, self.read(b, old_lock_ref(b)), self.now())
        tree = git(self.root, "mktree", input="")[1]
        now = self.now()  # read once: the text and `until` come from this one value
        msg = lock_message(ttl, now, self.holder)
        c, sha = git(self.root, "-c", "user.name=merge", "-c", "user.email=merge@localhost", "commit-tree", tree, "-m", msg)
        if c:
            raise Stop("cannot make the lock commit: " + sha)
        # --force-with-lease with an empty expect creates only. With a sha it swaps only that
        # expired lock. So two runs that break one expired lock cannot both win.
        lease = f"--force-with-lease={ref}:{cur[0] if cur else ''}"
        c, out = git(self.root, "push", "-q", lease, "origin", f"{sha}:{ref}")
        if c:
            raise Held("another run took the merge lock first")
        self._take(b, sha, tree, msg, now)
        return sha

    def swap(self, b, msg):
        """A new lock commit with the text `msg`, swapped in only while the ref still holds this run's last commit. -> its sha, or Stop."""
        ref = lock_ref(b)
        c, sha = git(self.root, "-c", "user.name=merge", "-c", "user.email=merge@localhost", "commit-tree", self.tree, "-m", msg)
        if c:
            raise Stop("cannot make the lock commit: " + sha)
        self.mine |= {sha}  # this run's before the push: a push that lands with a lost reply still leaves a lock release can delete
        c, out = git(self.root, "push", "-q", f"--force-with-lease={ref}:{self.sha}", "origin", f"{sha}:{ref}")
        if c:
            raise Stop("the lock ref moved, or the push failed: " + out)
        return sha

    def released(self, b, lease):
        """Push a lock commit that expired at 0, so any run may take it. The cloud proxy refuses every ref delete (HTTP 403, c53),
        so there a release or an unlock leaves this commit in place of no ref. `lease` is the push's lease flag. -> (code, output)."""
        ref = lock_ref(b)
        c, sha = git(self.root, "-c", "user.name=merge", "-c", "user.email=merge@localhost", "commit-tree", git(self.root, "mktree", input="")[1],
                     "-m", f"merge lock\nexpires: 0\nreleased: {int(self.now())}")
        return (c, sha) if c else git(self.root, "push", "-q", lease, "origin", f"{sha}:{ref}")

    def delete(self, b, token):
        ref = lock_ref(b)
        c, out = git(self.root, "push", "-q", f"--force-with-lease={ref}:{token}", "origin", f":{ref}")
        if not c:
            return c, out
        c2, out2 = self.released(b, f"--force-with-lease={ref}:{token}")  # the same lease: a lock another run took is never touched
        return (0, out2) if not c2 else (c, out + "\n" + out2)

    def unlock(self, b):
        """-> True when it removed or expired a lock, False when no lock was there."""
        ref = lock_ref(b)
        cur = self.read(b)
        if not cur or cur[1] <= 0:  # no ref, or a lock already released to expires 0
            return False
        c, out = git(self.root, "push", "-q", "origin", f":{ref}")
        if c and "does not exist" in out:  # gone since the read
            return False
        if c:
            c2, out2 = self.released(b, f"--force-with-lease={ref}:{cur[0]}")
            if c2:
                raise Stop("unlock failed: " + out + "\n" + out2)
        return True

class GhLock(Lock):
    """Real use: the GitHub API. The API refuses a ref that exists, so one run wins."""
    def __init__(self, now=time.time, pause=time.sleep):
        self.now, self.pause = now, pause

    def api(self, *a, once=False):
        """The one home of every lock `gh api` call. A network error or rate limit is retried NET_RETRIES times with `self.pause`
        (the ladder or GitHub's reset time on a rate limit), then the last (code, output) returns: the caller raises NetStop when is_net says so.
        Every call asks for the headers (-i), and retry_net drops the block. Once this run holds the lock, extend_for pushes the expiry past each rate wait.
        `once`: no retry and no wait at all. The extension calls and the delete of an expired lock use it: a retry could land after another run's take.
        ponytail: no retry inside `shared_deadline`, as in Host.gh. Before the lock is held, a rate wait follows the ladder: 60 + 300 + 900 s = 21 minutes per call at most, and the lock is not yet ours to extend."""
        path = next((x for x in a if x.startswith("repos/")), " ".join(a))
        retries = NET_RETRIES if _READ_DEADLINE is None and not once else 0
        c, out, _ = retry_net(lambda: sh(["gh", "api", "-i", *a]), self.pause, retries, f"the lock call {path}", self.now, self.extend_for)
        return c, out

    def read(self, b):
        c, sha = self.api(f"repos/{{owner}}/{{repo}}/git/ref/{lock_ref(b)[5:]}", "--jq", ".object.sha")
        if c:
            if is_net(c, sha):  # first: a 5xx reply whose url holds "404" is no proof the lock is gone
                raise NetStop("cannot read the merge lock: " + sha)
            if "404" in sha or "Not Found" in sha:
                return None
            raise Stop("cannot read the merge lock: " + sha)
        c, out = self.api(f"repos/{{owner}}/{{repo}}/git/commits/{sha}", "--jq", ".message")
        if is_net(c, out):  # an unread expiry is no lock that never expires
            raise NetStop("cannot read the merge lock commit: " + out)
        return (sha, expiry_of(out), out) if not c else (sha, float("inf"), "")

    def acquire(self, b, ttl):
        cur = self.read(b)
        if cur and cur[1] > self.now():
            refuse_or_take_over(b, cur, self.now())
        if cur:  # ponytail: the API cannot delete "only if the ref is still X". Window: from this run's read of the expired lock (or of a live lock whose holder is dead) to its delete. If another run breaks the lock and creates a live one inside that window, this delete removes the live lock, and the create below then succeeds, so both runs hold it. The window is a few API calls. Close it with a lock backend that has compare-and-swap.
            c, out = self.api("-X", "DELETE", f"repos/{{owner}}/{{repo}}/git/{lock_ref(b)}", once=True)  # never retried or waited: a late delete could remove another run's fresh lock
            if c and not self.gone(out):
                raise (NetStop if is_net(c, out) else Stop)("cannot remove the expired merge lock: " + out)
        c, head = self.api(f"repos/{{owner}}/{{repo}}/git/ref/heads/{b}", "--jq", ".object.sha")
        c2, tree = self.api(f"repos/{{owner}}/{{repo}}/git/commits/{head}", "--jq", ".tree.sha") if not c else (c, head)
        if c2:
            raise (NetStop if is_net(c2, tree) else Stop)("cannot read the base branch: " + tree)
        now = self.now()  # read once: the text and `until` come from this one value
        msg = lock_message(ttl, now, self.holder)
        c, sha = self.api("-X", "POST", "repos/{owner}/{repo}/git/commits", "-f", f"message={msg}", "-f", f"tree={tree}", "--jq", ".sha")
        if c:
            raise (NetStop if is_net(c, sha) else Stop)("cannot make the lock commit: " + sha)
        c, out = self.api("-X", "POST", "repos/{owner}/{repo}/git/refs", "-f", f"ref={lock_ref(b)}", "-f", f"sha={sha}")
        if c:
            if is_net(c, out):
                raise NetStop("cannot take the merge lock: " + out)
            if "already exists" not in out:  # 422 "Reference already exists" is the race; any other text is the refusal itself
                raise Stop("cannot take the merge lock: " + out)
            raise Held("another run took the merge lock first")
        self._take(b, sha, tree, msg, now)
        return sha

    def swap(self, b, msg):
        """A new lock commit with the text `msg`, then the ref moved to it. -> its sha, or Stop. No retry, no wait (api once).
        ponytail: the ref update is not compare-and-swap. Window: the read of the ref to the PATCH. The API has no lease; a backend with compare-and-swap closes it."""
        ref = f"repos/{{owner}}/{{repo}}/git/{lock_ref(b)}"
        c, cur = self.api(f"repos/{{owner}}/{{repo}}/git/ref/{lock_ref(b)[5:]}", "--jq", ".object.sha", once=True)
        if c or cur.strip() != self.sha:
            raise Stop("the lock is not this run's any more" if not c else "cannot read the lock: " + cur)
        c, sha = self.api("-X", "POST", "repos/{owner}/{repo}/git/commits", "-f", f"message={msg}", "-f", f"tree={self.tree}", "--jq", ".sha", once=True)
        if c:
            raise Stop("cannot make the lock commit: " + sha)
        self.mine |= {sha.strip()}  # this run's before the PATCH: a PATCH that lands with a lost reply still leaves a lock release can delete
        c, out = self.api("-X", "PATCH", ref, "-f", f"sha={sha.strip()}", "-F", "force=true", once=True)
        if c:
            raise Stop("cannot move the lock: " + out)
        return sha.strip()

    @staticmethod
    def gone(out):
        """The ref is not there: a delete that finds this has nothing left to do (a retry after a lost reply lands here).
        A network error or rate limit is never "gone", though its text may hold "404" (a user id, a request id)."""
        return not is_net(1, out) and ("404" in out or "Not Found" in out or "does not exist" in out)

    def delete(self, b, token):
        c, out = self.api("-X", "DELETE", f"repos/{{owner}}/{{repo}}/git/{lock_ref(b)}")
        return (0, out) if c and self.gone(out) else (c, out)

    def unlock(self, b):
        """-> True when it removed the lock, False when no lock was there."""
        c, out = self.api("-X", "DELETE", f"repos/{{owner}}/{{repo}}/git/{lock_ref(b)}")
        if c and is_net(c, out):
            raise NetStop("unlock failed, still failing after the retries. Run again: " + out)
        if c and not self.gone(out):
            raise Stop("unlock failed: " + out)
        return not c

# ------------------------------------------------------------------ the GitHub half (the seam)

class Host:
    """The GitHub half: `gh` for the pull request, the required checks, the wait and the merge.
    Tests pass a fake with the same pr, wait_checks and merge, or a `gh` shim on PATH."""

    def __init__(self, required="protection", base="main", minute=60, now=time.time, pause=time.sleep, ignore=None, repo=None, cwd=None):
        self.required, self.base, self.minute, self.now, self.pause = required, base, minute, now, pause
        self.repo = repo  # OWNER/NAME, or None for the repo of the working directory
        self.cwd = cwd    # where `gh` runs, so it names the repo of that directory
        self.ignore = ignore or {}  # check name -> reason, from ignore_checks()
        self.warned = set()  # (check name, link) already warned about, so a poll loop prints each line once

    before_wait = None  # lock.extend_for, set by confirm once the lock is held: runs before each rate wait. No gh call has one before

    def gh(self, args, cwd=None):
        """-> (code, output). The one home of every Host `gh` call. A network error is retried NET_RETRIES times with
        `self.pause`; after that NetStop. Any other failure returns at once. `self.net_retries` counts the retries
        of the last call. ponytail: no retry inside `shared_deadline` (the guard's hard hook budget has no room for a pause)."""
        c, out, self.net_retries = retry_net(lambda: sh(["gh", *args], cwd=cwd), self.pause, NET_RETRIES if _READ_DEADLINE is None else 0, f"`gh {' '.join(args[:2])}`", self.now, self.before_wait)
        if is_net(c, out):
            raise NetStop(f"network error from `gh {' '.join(args[:2])}`, still failing after {self.net_retries} retries. Nothing was reverted. Run again.\n{out}")
        return c, out

    def _repo_args(self):
        return ["-R", self.repo] if self.repo else []

    def api(self, rel, *extra, method="GET", fields=None):
        """-> (code, output) of one REST call, through Host.gh so its retries hold. The repo is Host.repo, else the repo of the working directory.
        `fields` go out as -f fields: a GET must say -X GET, or gh sends them as a POST body. A query value never goes in the route, because the
        Windows .cmd shim of gh lets cmd.exe split an argument at '&'."""
        route = f"repos/{self.repo}" if self.repo else "repos/{owner}/{repo}"
        args = ["api", f"{route}/{rel}" if rel else route, "-X", method]
        for key, value in (fields or {}).items():
            args += ["-f", f"{key}={value}"]
        return self.gh([*args, *extra], self.cwd)

    def pages(self, rel, key=None, fields=None):
        """-> every item of a list read, all pages. `key` names the field that holds the page in an object reply (check_runs, statuses); None is an array reply.
        A failed read is a Stop: never an empty list, which would read as no checks or no pull requests."""
        c, out = self.api(rel, "--paginate", "--slurp", fields={**(fields or {}), "per_page": 100})
        try:
            if c:
                raise ValueError(out)
            return [x for page in json.loads(out) for x in (page[key] if key else page)]
        except (ValueError, KeyError, TypeError) as e:
            raise Stop(f"reading {rel} from GitHub failed: {e}")

    # The old GraphQL values the rest of the tool reads, from the REST fields.
    MERGEABLE = {True: "MERGEABLE", False: "CONFLICTING", None: "UNKNOWN"}  # mergeable is null while GitHub works it out

    def pr_number(self, selector):
        """The pull request number of a selector: a number, a .../pull/<n> URL, a branch name, or none (the current branch).
        A branch resolves through the open pull request list on head.ref; no open pull request, or two, is a Stop. A URL also names its repo."""
        s = "" if selector is None else str(selector).strip()
        if s.isdigit():
            return int(s)
        m = re.search(r"github\.com/([^/\s]+/[^/\s]+)/pull/(\d+)", s)
        if m:
            self.repo = m.group(1)
            return int(m.group(2))
        m = re.search(r"/pull/(\d+)", s)
        if m:
            return int(m.group(1))
        branch = s
        if not branch:
            c, out = sh(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=self.cwd)
            if c or not out.strip() or out.strip() == "HEAD":
                raise Stop("no pull request is named, and the branch of the working directory cannot be read: " + out)
            branch = out.strip()
        hits = [d["number"] for d in self.pages("pulls", fields={"state": "open"}) if d["head"]["ref"] == branch]
        if len(hits) != 1:
            raise Stop(f"{len(hits)} open pull requests have the head {branch}: name the pull request by its number")
        return hits[0]

    def pr(self, n):
        """-> {head, branch, base, state, mergeable, merge_state, draft, body}"""
        c, out = self.api(f"pulls/{self.pr_number(n)}")
        if c:
            raise Stop("reading the pull request failed: " + out)
        d = json.loads(out)
        self.base = d["base"]["ref"]  # the PR's own base drives required_names
        return {"head": d["head"]["sha"], "branch": d["head"]["ref"], "base": d["base"]["ref"],
                "state": "MERGED" if d.get("merged") else d["state"].upper(),
                "mergeable": self.MERGEABLE[d.get("mergeable")], "merge_state": (d.get("mergeable_state") or "unknown").upper(),
                "draft": bool(d.get("draft")), "body": d.get("body") or ""}

    def open_heads(self):
        """-> {head branch name: (head sha, PR base)} of the open pull requests, every page. A failed read raises Stop: never an empty set,
        which would say no PR is open. A head with two open PRs (a backport, or a fork's branch of the same name) gets base None under
        its name, and every one of its rows is kept under name:index, a key no branch can have, so every base still counts, in any row order."""
        rows = self.pages("pulls", fields={"state": "open"})
        seen = [d["head"]["ref"] for d in rows]
        heads = {}
        for i, d in enumerate(rows):
            name, row = d["head"]["ref"], (d["head"]["sha"], d["base"]["ref"])
            if seen.count(name) > 1:
                heads.setdefault(name, (row[0], None))
                name = f"{name}:{i}"
            heads[name] = row
        return heads

    def batch_running(self, n, base, unprotected_counts_all=False, ignore=None):
        """-> one line per other open, ready pull request on `base` whose head has a workflow run not completed, or a required check
        reported and not completed (rule git-no-merge-during-batch-ci). The run counts because a required job can wait on another job
        (checks.yml's `checks` needs `scope`), so it has no row yet. A required name with no entry and no running workflow on that head
        does not count: a ready PR whose CI never reports would block every merge. merge.ignoreChecks runs and checks never count. The PR `n` itself, drafts and other bases never count. A failed read raises Stop: unknown is red.
        The required names are a pinned list, else the branch protection. `unprotected_counts_all` (the guard's mode): a base with no
        branch protection counts every reported pending check, and an empty protection list counts none. Without it, required_names rules.
        `ignore` (the guard's, whose Host keeps no ignore list so its own head counts every check) replaces self.ignore for this read."""
        ignore = self.ignore if ignore is None else ignore
        others = [d for d in self.pages("pulls", fields={"state": "open"})
                  if d["base"]["ref"] == base and not d.get("draft") and d["number"] != n]
        if not others:
            return []  # no protection read when no other pull request could block
        if unprotected_counts_all and not isinstance(self.required, list):
            names = self.protection_names()  # None: no branch protection
        else:
            names = self.required_names()
        blockers = []
        for d in others:
            got = self.checks(d["number"], warn=False, sha=d["head"]["sha"])
            _, pending, _ = self.classify(got, names or [], ignore)
            hits = [f"`{k}` is pending: " + next((l for b, l in got[k] if b == "pending"), "")
                    for k in pending if (names is None or k in names) and got.get(k)]
            running = self.judge_runs([r for r in self.runs(d["head"]["sha"]) if r["name"] not in ignore])[1]
            parts = (["required check " + "; ".join(hits)] if hits else []) + [w + " is not completed" for w in running]
            if parts:
                blockers.append(f"#{d['number']} ({d['head']['ref']}) " + "; ".join(parts))
        return blockers

    def protection_names(self):
        """-> the required check names of the base's branch protection, or None when the base has none (an HTTP 404 that is not a
        network error). Through api, so the guard's -R repo and its cwd name the repo. Any other failed read raises Stop."""
        c, out = self.api(f"branches/{self.base}/protection/required_status_checks", "--jq", ".contexts")
        if c and not is_net(c, out) and re.search(r"\bHTTP 404\b", out):
            return None
        try:
            names = json.loads(out) if not c else None
            if not isinstance(names, list):
                raise ValueError
        except ValueError:
            raise Stop(f"cannot read the required checks of {self.base}. Set merge.requiredChecks to a list of check names.\n{out}")
        return names

    def required_names(self):
        """The required check names. Never empty: an empty list would pass the wait without a read."""
        if isinstance(self.required, list):
            names = self.required
        else:
            names = self.protection_names()
            if names is None:
                raise Stop(f"{self.base} has no branch protection, so it names no required checks. "
                           "Set merge.requiredChecks to a list of check names.")
        clash = [k for k in names if k in self.ignore]
        if clash:
            raise Stop("merge.ignoreChecks names a required check: " + ", ".join(clash) + ". A required check is never ignored.")
        if not names:
            raise Stop(f"no required checks are named for {self.base} (merge.requiredChecks or the branch protection is empty). "
                       "The tool never merges with nothing to wait for. Name the checks.")
        return names

    def refuse_pinned_mismatch(self):
        """A pinned merge.requiredChecks list must equal a non-empty branch protection list: a copy that drifted waits on checks no run reports (#746).
        An empty or unreadable protection leaves the pinned list in force; an unreadable one says so."""
        if not isinstance(self.required, list):
            return
        try:
            held = self.protection_names()
        except NetStop:
            raise
        except Stop:
            held = None
        if held is None:
            say(f"merge: cannot read the branch protection of {self.base}, so the pinned merge.requiredChecks list is not compared with it.")
        elif held and set(held) != set(self.required):
            raise Stop(f"merge.requiredChecks pins {', '.join(self.required)}, but the branch protection of {self.base} requires {', '.join(held)}. "
                       'Set merge.requiredChecks to "protection" so the protection list is the one source.')

    # A check run's conclusion, and a commit status's state, to the bucket the tool judges. A run that is not completed is pending. Any other value is a fail.
    CONCLUSION_BUCKET = {"success": "pass", "neutral": "skipping", "skipped": "skipping", "cancelled": "cancel"}
    STATE_BUCKET = {"success": "pass", "pending": "pending"}

    def checks(self, n, warn=True, sha=None):
        """-> {check name: [(bucket, link), ...]}, every entry kept: the check runs of the head AND its commit statuses, all pages of each. A check that
        exists only as a status counts. The combined status is never read: its state says "pending" for a commit with no statuses.
        `sha` is the head the caller already read; with none, the head of the pull request `n` is read. The same read judges time against each job's cap (`job_caps`, from the workflow files of this checkout). With `warn`, a job over 70% of its cap prints one line.
        A read that must print nothing passes warn=False: the guard's `head_read` shares stdout with the guard's JSON, and the preview builds its lines first.
        A cancelled check that ran its full cap gets the bucket "timed out ... re-cap or split", so it reads red and apart from a test failure. A pending job has no end time and is skipped."""
        sha = sha or self.pr(n)["head"]
        rows = []
        for r in self.pages(f"commits/{sha}/check-runs", "check_runs"):
            rows.append(self.run_row(r, r.get("details_url")))
        for s in self.pages(f"commits/{sha}/status", "statuses"):
            rows.append({"name": s["context"], "bucket": self.STATE_BUCKET.get(s["state"], "fail"), "link": s.get("target_url")})
        return self.buckets(rows, warn)

    def run_row(self, r, link):
        """A check run, or an Actions job (the same fields), as the row `buckets` judges."""
        bucket = "pending" if r["status"] != "completed" else self.CONCLUSION_BUCKET.get(r.get("conclusion"), "fail")
        return {"name": r["name"], "bucket": bucket, "link": link, "startedAt": r.get("started_at"), "completedAt": r.get("completed_at")}

    def buckets(self, rows, warn=True):
        """-> {name: [(bucket, link), ...]} of check rows, a cancel that ran its full cap turned into the timeout bucket. See checks."""
        try:
            flow = workflow_dir(self.cwd)
            caps = job_caps(p.read_text(encoding="utf-8") for p in sorted(flow.glob("*.y*ml"))) if flow else {}
        except (OSError, ValueError):  # the warning is advice: with no readable workflow there is no cap to judge against
            caps = {}
        got = {}
        for d in rows:
            bucket, link, cap, used = d["bucket"], d.get("link") or "", caps.get(d["name"]), job_minutes(d)
            if cap and used is not None:
                if bucket == "cancel" and used >= cap:
                    bucket = f"timed out at its {cap}-minute cap; re-cap or split"
                elif warn and used > 0.7 * cap and (d["name"], link) not in self.warned:
                    self.warned.add((d["name"], link))
                    say(f"job {d['name']}: {round(used)} of {cap} min; raise the cap from measured runs, or split its slowest suite")
            got.setdefault(d["name"], []).append((bucket, link))
        return got

    def wait_checks(self, n, sha, deadline_minutes, prior=None):
        """Wait until every check on `sha` has finished and none failed. -> (ok, why). `prior` is the head before this run's push.
        Each pass reads the pull request first: a third head, DIRTY or CONFLICTING ends the wait. A head
        that still reads as `prior` is GitHub lagging the push: keep waiting. Any red check, required or
        not, ends the wait, and any pending check, required or not, is waited on. A pending check pauses with no gh call (30 s with an Actions run link, else a minute), then the loop reads again."""
        listed = self.required if isinstance(self.required, list) else None  # protection mode needs a gh read to know the names
        say("merge: checking " + (", ".join(listed) if listed else "the required checks") + " ...")  # before the first gh read, which can block
        names = self.required_names()
        base = self.base  # the base read under the lock: the last pr() before the wait
        end = self.now() + deadline_minutes * 60
        settled, absent_seen = False, None
        if not listed:
            say("merge: required: " + ", ".join(names))
        said, said_at = None, self.now()  # the text last printed, and when (the wait's start before any line)

        def progress(what):
            nonlocal said, said_at
            if what and (what != said or self.now() - said_at >= 120):
                say("merge: waiting on " + what)
                said, said_at = what, self.now()

        while True:
            info = self.pr(n)
            if info["head"] == prior and prior != sha:
                progress("GitHub to show the pushed head")
                if self.now() >= end:
                    return False, f"the deadline of {deadline_minutes} minutes passed. GitHub still shows the head before the push."
                self.pause(self.minute)
                continue
            if info["base"] != base:
                return False, f"the base of the pull request changed from {base} to {info['base']} during the wait."
            if info["head"] != sha:
                return False, f"the branch head moved to {info['head'][:9]} during the wait ({sha[:9]} was waited on). Run again."
            if info["mergeable"] == "CONFLICTING" or info["merge_state"] == "DIRTY":
                return False, "the pull request went DIRTY during the wait. Merge the base into the branch and run again."
            got = self.checks(n, sha=info["head"])
            red, pending, ignored = self.classify(got, names, self.ignore, info["branch"])
            red, pending = self.settle(red, pending, *self.run_state(sha))
            if red:
                return False, "a check is red: " + "; ".join(red)
            absent = sorted(k for k in names if not got.get(k))
            if absent and got and pending == absent:  # every reported check and run has ended; only a required name nobody reports is left
                if absent_seen != absent:  # ponytail: a job that waits on another, or a status from outside Actions, can appear after the last check ends. One minute covers that; one later still stops the run, which is rerun.
                    absent_seen = absent
                    self.pause(self.minute)  # a status from outside Actions can post a minute after the last job ends
                    continue
                return False, ("no run reports the required check " + ", ".join(absent) + f" on this head, and every check that did report has ended. "
                               f"Waiting would end at the deadline of {deadline_minutes} minutes. Compare merge.requiredChecks and the branch protection of {base} with the workflow job names.")
            absent_seen = None
            if not pending and not settled:
                # ponytail: a workflow GitHub has not created yet still reads as green. The runs read and this settle read close most of the window. Ceiling: a workflow that appears after SETTLE_SECONDS.
                if self.now() - said_at + SETTLE_SECONDS > 120:  # the settle pause would break the 120 s rhythm
                    say("merge: waiting on a last read of the checks")
                    said_at = self.now()
                self.pause(SETTLE_SECONDS)
                settled = True
                continue
            if not pending:
                if ignored:
                    say("merge: ignored by merge.ignoreChecks: " + "; ".join(ignored))
                return True, ""
            if self.now() >= end:
                return False, f"the deadline of {deadline_minutes} minutes passed. Still pending: " + ", ".join(pending)
            settled = False
            progress(", ".join(pending))
            self.block(pending, got)

    def runs(self, sha):
        """The workflow runs of `sha`, less the ignored ones."""
        c, out = self.gh(["run", "list", *self._repo_args(), "--commit", sha, "--limit", "100", "--json", "status,conclusion,name"], self.cwd)
        try:
            runs = json.loads(out)
        except ValueError:
            raise Stop("gh run list failed: " + out)
        return [r for r in runs if r["name"] not in self.ignore]

    def run_state(self, sha):
        """-> (red, pending) from the workflow runs of `sha`. A run that is not completed holds the wait even
        when its jobs are not listed as checks yet. Success, skipped and neutral pass, but see judge_runs."""
        return self.judge_runs(self.runs(sha))

    @staticmethod
    def judge_runs(runs):
        """-> (red, pending) from a list of workflow runs, newest first. Pending: any run not completed, even an
        older one. Red: judged on the newest run per workflow name, after a skipped run is dropped when another run
        of that name is not skipped (a skip never outranks a run that ran), and after a cancelled run is dropped when another run
        of that name ran, completed or in progress (concurrency cancels one of two same-second runs; a cancelled run alone stays red). Success, skipped and neutral pass, but when
        every run is completed/skipped and none is pending, no job ran on this head: red (GitHub counts a
        skipped job as passing, so required checks miss it)."""
        pending = [f"workflow {r['name']}" for r in runs if r["status"] != "completed"]
        ran = {r["name"] for r in runs if r["conclusion"] != "skipped"}
        runs = [r for r in runs if not (r["conclusion"] == "skipped" and r["name"] in ran)]
        live = {r["name"] for r in runs if r["conclusion"] not in ("skipped", "cancelled")}
        runs = [r for r in runs if not (r["conclusion"] == "cancelled" and r["name"] in live)]
        runs = list({r["name"]: r for r in reversed(runs)}.values())[::-1]
        red = [f"workflow {r['name']}: {r['conclusion']}" for r in runs if r["status"] == "completed" and r["conclusion"] not in ("success", "skipped", "neutral")]
        if runs and not pending and all(r["conclusion"] == "skipped" for r in runs):
            red = [f"workflow {r['name']}: skipped, no job ran" for r in runs]
        return red, pending

    BASE_EVENTS = ("push", "schedule", "workflow_dispatch")  # the runs of the base's own commits; a dispatch is the tool's own remedy

    def base_state(self, base, flows):
        """-> (verdict, detail) for the red-main check (decision no-merge-onto-red-main): green, red, or unknown.
        Judged: per workflow file in `flows` (the paths on the base), its newest completed run on `base` of BASE_EVENTS. A newer run still going
        waits its turn. A file gone from the base is not judged: its last run is never replaced. Per file, not per name: a rename keeps the file.
        Red: a job whose bucket is a fail, or one gh adds later (classify). A cancelled or skipped job is not red, nor one timed out at its cap.
        A run that did not succeed with no red job: a timed-out job explains it; else a cancelled run is unknown, never swapped for an older
        run (the twin rule of judge_runs would reach across commits here), and any other is red (a broken workflow file runs no job).
        One page of runs, never every page: the base's history is long. A run that did not succeed costs one jobs read. A failed read is unknown."""
        try:
            c, out = self.api("actions/runs", fields={"branch": base, "per_page": 50})
            if c:
                raise Stop(out)
            done = [r for r in json.loads(out)["workflow_runs"] if r["status"] == "completed" and r["event"] in self.BASE_EVENTS
                    and r["name"] not in self.ignore and r["path"].split("@")[0] in flows]
            red, unknown = [], []
            for r in {r["path"]: r for r in reversed(done)}.values():
                if r["conclusion"] in ("success", "skipped", "neutral"):
                    continue
                got = self.buckets([self.run_row(j, j.get("html_url")) for j in self.pages(f"actions/runs/{r['id']}/jobs", "jobs")], warn=False)
                steps = {k: v for k, rows in got.items() if (v := [x for x in rows if x[0] != "cancel" and not x[0].startswith("timed out")])}
                jobs = [j for j in self.classify(steps, [], self.ignore)[0] if "no check ran" not in j]
                where = f"run {r['id']} of {r['name']} at {str(r.get('head_sha'))[:9]} ({r.get('html_url')})"
                if jobs:
                    red.append(f"{where}: " + "; ".join(jobs))
                elif any(b.startswith("timed out") for rows in got.values() for b, _ in rows):
                    continue
                elif r["conclusion"] == "cancelled":
                    unknown.append(f"{where} was cancelled with no red job")
                else:
                    red.append(f"{where} ended {r['conclusion']} with no red job")
        except (Stop, ValueError, KeyError, TypeError, AttributeError) as e:
            return "unknown", " ".join(str(e).split())
        return ("red", " | ".join(red)) if red else ("unknown", " | ".join(unknown)) if unknown else ("green", "")

    @staticmethod
    def settle(red, pending, r_red, r_pending):
        """Join the checks' and the runs' (red, pending). Anything still pending holds the wait, so a
        "no check ran" or "no job ran" red is dropped: the run the remedy just started is not refused."""
        red, pending = red + r_red, pending + r_pending
        return ([x for x in red if "no check ran" not in x and "no job ran" not in x] if pending else red), pending

    @staticmethod
    def classify(got, names, ignore=None, branch="<branch>"):
        """-> (red, pending, ignored). Every check on the head counts, required or not. Red: any bucket
        that is not pass, skipping or pending (fail, cancel, and any bucket gh adds later: closed).
        A cancel entry is dropped when another entry of that name is pass or pending (another run ran; concurrency cancels one of two
        same-head runs; a cancel beside only a skip or alone stays red; a fail or timeout is never dropped).
        Also red: a head with entries where none is pass or pending (all skipping): no check ran on it,
        unless something is pending. `branch` fills the remedy's `--ref`. A dispatch run skips DRAFT_SKIP_CHECK, so when it is
        required the remedy names `gh pr ready` or a new push, not a dispatch.
        Pending: a pending entry, or a required name with no entry, or, when nothing is red, a required DRAFT_SKIP_CHECK whose
        entries are all skipping (a draft run on the same head skipped it; the ready run has not passed it yet). Any other required
        name that only skipped reads green. `ignore` maps a name to its reason:
        those checks are left out of red and pending, and named in `ignored`."""
        ignore = ignore or {}
        live = {k: rows for k, rows in got.items() if k not in ignore or k in names}
        live = {k: ([r for r in rows if r[0] != "cancel"] if any(r[0] in ("pass", "pending") for r in rows) else rows) for k, rows in live.items()}
        red = [f"{k}: {b} {l}".strip() for k, rows in live.items() for b, l in rows if b not in ("pass", "skipping", "pending")]
        pending = sorted({k for k, rows in live.items() if any(b == "pending" for b, _ in rows)} | {k for k in names if not got.get(k)})
        if live and not red and not pending and not any(b == "pass" for rows in live.values() for b, _ in rows):
            fix = ("Run `gh pr ready`, or push anew if the PR is ready" if DRAFT_SKIP_CHECK in names
                   else f"Run `gh workflow run checks.yml --ref {branch}`, or push anew after `gh pr ready`")
            red = [f"no check ran on this head (every check skipped). {fix}"]
        if not red and DRAFT_SKIP_CHECK in names and live.get(DRAFT_SKIP_CHECK) and all(b == "skipping" for b, _ in live[DRAFT_SKIP_CHECK]):
            pending = sorted(set(pending) | {DRAFT_SKIP_CHECK})
        ignored = [f"{k} ({ignore[k]}): " + "/".join(sorted({b for b, _ in rows})) for k, rows in got.items() if k in ignore]
        return red, pending, ignored

    def head_state(self, n):
        """One read of the head's own checks, for the preview: green, pending, or red: <name>. Reads only, never waits."""
        try:
            got = self.checks(n, warn=False)
            red, pending, ignored = self.classify(got, self.required_names(), self.ignore)
        except Stop as e:
            return f"unknown ({e})"
        s = "red: " + "; ".join(red) if red else "pending: " + ", ".join(pending) if pending else "green"
        return s + (" (ignored: " + "; ".join(ignored) + ")" if ignored else "")

    def head_read(self, n, nothing_is_green=False, batch_ignore=None):
        """One read, no wait, of every check and workflow run on the head, required or not.
        -> (verdict, detail): green, pending, red, batch, or unknown when any read could not run. The guard's
        home for "has this head settled", so it shares classify and runs with the wait.
        No check and no run reads as pending, not green: right after a push GitHub has not created
        them yet (wait_checks settles for the same reason). `nothing_is_green` is for a repo with no workflows.
        batch: the head is settled, but another ready PR on its base has a workflow run or a required check pending (batch_running,
        which takes `batch_ignore` as its ignore list).
        Its `gh` calls (the pull request, the check runs, the commit statuses, the workflow runs; a branch name adds the open pull request list;
        a settled head adds the batch read) share one deadline (SH_TIMEOUT, the guard's one budget for this whole
        read) instead of each getting it afresh, so a hung gh holds the whole read for one deadline,
        not one per call."""
        try:
            with shared_deadline(SH_TIMEOUT):
                num = self.pr_number(n)  # the number, so batch_running can leave this PR out; pr() of a number reads nothing more
                info = self.pr(num)
                got = self.checks(num, warn=False, sha=info["head"])
                red, pending, _ = self.classify(got, [], self.ignore, info["branch"])
                runs = self.runs(info["head"])
                red, pending = self.settle(red, pending, *self.judge_runs(runs))
                unseen = not got and not runs and not nothing_is_green
                blockers = [] if red or pending or unseen else self.batch_running(num, info["base"], unprotected_counts_all=True, ignore=batch_ignore)
        except subprocess.TimeoutExpired:  # its text names the resolved program path
            return "unknown", "a gh call timed out"
        except Exception as e:  # Stop, a missing gh, malformed JSON: all unread
            return "unknown", str(e)
        if red:
            return "red","; ".join(red)
        if pending:
            return "pending", ", ".join(pending)
        if unseen:
            return "pending", "no check and no workflow run is reported on the head yet"
        if blockers:
            return "batch", "; ".join(blockers)
        return "green", ""

    def block(self, pending, got):
        """Pause for something to change. A check with an Actions run pauses 30 s, else a minute. Neither makes a gh call."""
        ids = [m.group(1) for k in pending for _, l in got.get(k, []) for m in [re.search(r"/actions/runs/(\d+)", l)] if m]
        if not ids:  # ponytail: a check outside Actions has no run link, so this is a plain pause. Fine while the loop exits at the deadline.
            self.pause(self.minute)
            return
        self.pause(30)  # no gh call: the next pass reads the checks (decision ci-wait-reads-run-status)

    def merge(self, n, method, sha):
        """`PUT pulls/<n>/merge` with `sha`, so GitHub refuses (409) a head that moved. Never --admin, never --delete-branch (cut_branch does that).
        -> (merge commit oid or None, message). The reply is never trusted: after any reply the PR state is read.
        MERGED at head `sha` is this run's merge. merge_commit_sha proves nothing alone: GitHub sets it on an open pull request too. MERGED at another head is not: Stop, no revert. An unreadable state,
        or OPEN after a reply lost to the network, is a NetStop (no revert). Only a proven refusal returns None (revert)."""
        say(f"merge: merging #{n} ...")  # the merge call can block
        # The old `gh pr merge` (no --admin) refused a BLOCKED or BEHIND pull request itself. The REST PUT does not: a token that may bypass branch
        # protection merges it. So read the pull request right before the PUT; blocked or behind is a proven refusal, and no PUT is sent. Clean, unstable and the rest go on.
        state_now = self.pr(n)["merge_state"]
        if state_now in ("BLOCKED", "BEHIND"):
            return None, f"#{n} reads {state_now}: its base rules are not met or its branch is behind the base. gh's merge refuses it the same way, so no merge call was sent."
        lost = False
        try:
            c, out = self.api(f"pulls/{n}/merge", method="PUT", fields={"merge_method": method, "sha": sha})
        except NetStop as e:
            lost, c, out = True, 1, str(e)
        try:
            c2, view = self.api(f"pulls/{n}")
            d = json.loads(view) if not c2 else None
            state, head, oid = "MERGED" if d["merged"] else d["state"].upper(), d["head"]["sha"], d["merged"] and d["merge_commit_sha"]
            if state == "MERGED" and not oid:
                raise ValueError("MERGED with no merge commit")
        except (NetStop, ValueError, KeyError, TypeError) as e:
            raise NetStop(f"the merge of #{n} may have landed, and its state cannot be read. Nothing was reverted. Check the pull request #{n} on GitHub. "
                          f"If it is merged, do the after-merge steps by hand (move the local {self.base}, run merge.afterMerge, cut the branch). If it is open, run again.\n{out}\n{e if isinstance(e, NetStop) else view}")
        if state == "MERGED":
            if head == sha:
                return oid, ""
            raise Stop(f"#{n} is merged at {str(head)[:9]}, not at the proven head {sha[:9]}: not this run's merge. Nothing was reverted.\n{out}")
        if lost:
            raise NetStop(f"network error on the merge call of #{n}, and the pull request is not merged. Nothing was reverted. Run again.\n{out}")
        if not c:  # exit 0 and still OPEN: not a refusal (a queued merge, or a lagging read). The claim stays.
            raise NetStop(f"the merge call of #{n} exited 0, but the pull request still reads OPEN. Nothing was reverted. Check the pull request #{n} on GitHub: "
                          f"if it merged, do the after-merge steps by hand; if it is open, run again.\n{view}")
        # A refusal reply with the PR still OPEN is proven, even when the first try lost its reply and a retry got the refusal
        # (gh retried it): gh answered and the merge did not happen. The caller reverts the claim. Only a proven refusal reverts (standing-merge-grant).
        return None, out

# ------------------------------------------------------------------ git steps

def node_stamp(wt, cfgrel, mode, base):  # cfgrel: relative to wt, or absolute
    # GITHUB_REF and GITHUB_BASE_REF name the runner's checkout, not this worktree. stamp would read them as the worktree's branch.
    env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_REF", "GITHUB_BASE_REF")}
    return sh(["node", STAMP, f"--{mode}", "--base", base, "--config", os.path.join(wt, cfgrel), "--root", wt], env=env)

def stamp_stop(what, out):
    """One line for a stamp.mjs failure: the reason, and the file that keeps the full output. Never a stack trace."""
    fd, log = tempfile.mkstemp(prefix="merge-stamp-", suffix=".log")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(out)
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    errs = [l for l in lines if re.match(r"(\w*Error|UNKNOWN|stamp)\b", l)]
    reason = errs[-1] if errs else lines[0] if lines else "no output"
    return Stop(f"{what}: {reason} (full output: {log})")

def base_stamp_config(wt, tmp, cfgrel, base_ref):
    """The stamp config as the base branch holds it, never the pull request's tree (ios-adblock #28).
    -> a file path outside the worktree, or None when the base has no config or no stamp kinds."""
    c, listed = git(wt, "ls-tree", "--name-only", base_ref, "--", cfgrel)
    if c:  # an unreadable base is not an absent file
        raise Stop(f"cannot read {base_ref} to look for {cfgrel}: {listed}")
    if not listed:
        return None
    try:
        c, text = git(wt, "show", f"{base_ref}:{cfgrel}")
        if c:
            raise Stop(f"cannot read {cfgrel} on {base_ref}: {text}")
        kinds = json.loads(text).get("kinds")
    except (ValueError, AttributeError) as e:
        raise Stop(f"cannot read the config {cfgrel} on {base_ref}: {e}")
    if not kinds:
        return None
    path = os.path.join(tmp, "base-stamp.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path

def head_claim(wt):
    """The Record-claim ids on HEAD's last commit, or ''."""
    return git(wt, "log", "-1", "--format=%(trailers:key=Record-claim,valueonly)", "HEAD")[1].strip()

def own_claim(wt, cfgrel, base):
    """The trailer ids when HEAD is this tool's claim and each number is still free, else None."""
    ids = head_claim(wt)
    if not ids or not cfgrel:
        return None
    c, out = node_stamp(wt, cfgrel, "check", base)
    return None if c or "UNKNOWN:" in out else ids  # UNKNOWN is a failure: it exits 0 outside Actions

def do_claim(wt, cfgrel, base):
    """Run the claim in the worktree. -> the Record-claim line, or None when nothing was claimed.

    sh() joins stdout+stderr (see sh() above), so a regenerate step's npm warn/notice lines on
    stderr can land after the trailer. Scan every line for the one starting "Record-claim: "
    instead of assuming it is the last line. Two such lines is a signal we don't understand: refuse
    rather than guess which one is real."""
    c, out = node_stamp(wt, cfgrel, "claim", base)
    if c:
        raise stamp_stop("the claim was refused. Nothing is on origin", out)
    claims = [l for l in out.splitlines() if l.startswith("Record-claim: ")]
    if len(claims) > 1:
        raise Stop("the claim printed more than one Record-claim line. Refusing to guess which is real.\n" + out)
    return claims[0] if claims else None

def identity(wt):
    return [] if git(wt, "config", "user.email")[1] and git(wt, "config", "user.name")[1] else ["-c", "user.name=merge", "-c", "user.email=merge@localhost"]  # a runner has no identity

def commit_claim(wt, trailer):
    """One commit for the claim and the rebuilt records page. No trailer: the page alone."""
    git(wt, "add", "-A")
    msg = ["-m", "Claim record numbers", "-m", trailer] if trailer else ["-m", "Rebuild the records page",
           "-m", f"Drops-lines: {RECORDS_PAGE} -- a generated page, rebuilt by the generator"]  # the silent-undo check reads the rebuilt page as generated
    c, out = git(wt, *identity(wt), "commit", "-q", *msg)
    if c:
        raise Stop("cannot commit the claim: " + out)
    return git(wt, "rev-parse", "HEAD")[1]

def rebuild_records(wt):
    """Run the records generator on the worktree: `python3 <RECORDS> --root <wt> --records-only`, nothing else. -> True when it changed a file.
    The tree hash before and after is the proof: `git add -A` first, so the claim's own edits are not the generator's."""
    def tree():
        git(wt, "add", "-A")
        return git(wt, "write-tree")[1]
    before = tree()
    c, out = sh([sys.executable, RECORDS, "--root", wt, "--records-only"])
    if c:
        why = "; ".join(l.strip() for l in out.splitlines() if l.strip()) or "no output"
        raise Stop(f"the records page cannot be rebuilt, so nothing was pushed: {why}")
    return tree() != before

def records_proof(wt, base_ref):
    """Merge base_ref into the worktree without a commit, run the generator, and say what the page needs.
    -> "fresh": the page on the head holds in the merge result. "stale": it would change. "healed": only the page
    conflicted, so the merge is committed with the page rebuilt on the merged tree, and HEAD is that commit.
    A conflict on any other file stops. Fresh and stale put the worktree back as it was."""
    c, out = git(wt, *identity(wt), "merge", "--no-commit", "--no-ff", "-q", base_ref)
    healed = False
    try:
        if c:
            if git(wt, "diff", "--name-only", "--diff-filter=U")[1].split() != [RECORDS_PAGE]:
                raise Stop(f"the head does not merge cleanly with {base_ref}, so the records page cannot be proved fresh: {out}")
            page = os.path.join(wt, *RECORDS_PAGE.split("/"))
            if os.path.exists(page):
                os.remove(page)  # the generator is the only thing that clears a conflict on the page: a page it does not write stays a conflict
            rebuild_records(wt)  # the page is derived: rebuilt on the merged tree, it replaces both sides
            if not os.path.exists(page):  # a repo with no record folders gets no generated page, so a hand-written one cannot be rebuilt
                raise Stop(f"the records page {RECORDS_PAGE} conflicts with {base_ref} and the generator writes no page for this repo, so nothing was merged. Resolve the page by hand on the branch.")
            # the rebuilt page drops lines a side added; the silent-undo check after the next wait must read that as generated
            c, out = git(wt, *identity(wt), "commit", "-q", "-m", f"Merge {base_ref} and rebuild the records page",
                         "-m", f"Drops-lines: {RECORDS_PAGE} -- a generated page, rebuilt on the merged tree")
            if c:
                raise Stop("cannot commit the merge of the base: " + out)
            healed = True
            return "healed"
        return "stale" if rebuild_records(wt) else "fresh"
    finally:
        if not healed:
            git(wt, "reset", "--hard", "-q", "HEAD")  # also ends a merge in progress
            git(wt, "clean", "-fdq")

CI_JOB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin", "ci-job")  # the lint steps of a job, read from the workflow; the tool brings it
CI_SCOPE = ".github/scripts/ci-scope.sh"  # the repo's one home of which jobs read which paths; a repo without it never takes a small move
DRAFT_SKIP_CHECK = "all-jobs-passed"  # the one required check a draft run skips (actions/all-jobs-passed): its skip means the ready run is still to come, not green
LINT_SECONDS = 1200  # the bound on the lint run of the merge result, and again on the suites it hits; the lock is extended to cover each
SUITE_LINE = re.compile(r"(python3|node|bash) ([\w./-]+\.(?:py|mjs|sh))(?: [^|&;`<>$(){}]*)?")  # a suite line run as written: no shell syntax

def needles(path):
    """The names a suite that reads `path` would hold: the path, its file name, its stem (4 or more characters), and each
    parent folder below the top, as a path and as its own name. A top folder alone (`docs`) names too much to tell."""
    parts = path.split("/")
    out = {path, parts[-1]}
    stem = parts[-1].rsplit(".", 1)[0]
    if len(stem) >= 4:
        out.add(stem)
    for i in range(2, len(parts)):
        out.update(("/".join(parts[:i]), parts[i - 1]))
    return out

READERS = {"open", "listdir", "scandir", "glob", "iglob", "rglob", "iterdir", "Path", "PurePath", "walk", "exists", "isfile", "isdir"}
SAME_DIR = {"abspath", "realpath", "normpath", "resolve", "Path", "PurePath", "absolute", "str", "fspath", "expanduser"}  # a call that names the folder it is given
# a call that builds a path or a string and reads nothing
BUILDERS = SAME_DIR | {"dirname", "join", "joinpath", "normcase", "relpath", "basename", "splitext", "as_posix", "commonpath",
                       "replace", "lower", "strip", "rstrip", "lstrip", "encode", "decode", "split", "rsplit", "startswith", "endswith", "format"}

def _words(needle_set):
    return [re.compile(r"(?<![\w.-])" + re.escape(n) + r"(?![\w-])") for n in needle_set]

def _func_name(call):
    f = call.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None

def _constant_path(e):
    """True when e is a string, or a call (such as os.path.join) on strings only: a path fixed in the source."""
    if isinstance(e, ast.Constant):
        return isinstance(e.value, str)
    return isinstance(e, ast.Call) and bool(e.args) and all(_constant_path(a) for a in e.args)

def _own_nodes(scope):
    """The nodes of one scope: the module or one function, without the functions nested in it."""
    todo, out = list(ast.iter_child_nodes(scope)), []
    while todo:
        n = todo.pop()
        out.append(n)
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            todo.extend(ast.iter_child_nodes(n))
    return out

def _top_exprs(stmt):
    """The largest expressions of one statement: an expression held by a `with` item or an argument list counts too."""
    for child in ast.iter_child_nodes(stmt):
        if isinstance(child, ast.expr):
            yield child
        elif not isinstance(child, ast.stmt):
            yield from _top_exprs(child)

def _up(d, n=1):
    """The folder n levels above repo folder d ("." is the top), or None above the top."""
    for _ in range(n):
        if d is None or d == ".":
            return None
        d = posixpath.dirname(d) or "."
    return d

def _under(d, *parts):
    d = posixpath.normpath(posixpath.join(d, *(x.strip("/") for x in parts)))
    return None if d == ".." or d.startswith("../") else d

def python_suite_hits(source, rel, paths, read=None, depth=1):
    """True when a Python suite at repo path `rel` may read one of `paths` from the checkout. Read with `ast`, so a
    name inside a string or comment is told from code. A root is a name bound, in its own scope or the module's, from
    an expression that holds `__file__` or a root. A hit is:
    - the exact path or file name anywhere in the source;
    - a folder below the top or a stem (needles) in any string of an expression that holds a root, in any form
      (join, `/`, `+`, f-string, format, `%`), or given bare to a file reader (CI runs at the repo top);
    - a path under the folder a root names, when a call that builds no path takes that root whole (a walk). A root at
      the top takes every path.
    `read(path)` -> the text of a repo file or None: each local module the suite imports, from its own folder or a
    folder it puts on sys.path, is read the same way, `depth` levels deep. A module that resolves to no file is no hit.
    A folder named only under a temp dir is no hit. SyntaxError when the source does not parse."""
    tree = ast.parse(source)
    for p in paths:
        if any(w.search(source) for w in _words({p, p.split("/")[-1]})):
            return True
    words = _words({w for p in paths for w in needles(p)})
    path_dirs = set()
    # a function of this file that calls only builders builds a path too, such as a helper that turns `\\` into `/`
    builders = BUILDERS | {f.name for f in tree.body if isinstance(f, ast.FunctionDef)
                           and all(_func_name(c) in BUILDERS for c in ast.walk(f) if isinstance(c, ast.Call))}

    def analyze(scope, outer):
        """-> (roots of this scope: name -> folder or None, hit). `outer` is the module's roots, for names not bound here."""
        nodes = _own_nodes(scope)
        bound = {n.id for n in nodes if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
        if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            bound |= {a.arg for a in ast.walk(scope.args) if isinstance(a, ast.arg)}
        roots = {}
        def is_root(name):
            return name == "__file__" or (name in roots if name in bound else name in outer)
        def has_root(e):
            return any(isinstance(n, ast.Name) and is_root(n.id) for n in ast.walk(e))
        def folder(e):  # the repo folder a root expression names, or None when it cannot be told
            if isinstance(e, ast.Name):
                return rel if e.id == "__file__" else roots.get(e.id) if e.id in bound else outer.get(e.id)
            if isinstance(e, ast.Attribute) and e.attr == "parent":
                return _up(folder(e.value))
            if isinstance(e, ast.Subscript) and isinstance(e.value, ast.Attribute) and e.value.attr == "parents":
                k = e.slice
                return _up(folder(e.value.value), k.value + 1) if isinstance(k, ast.Constant) and isinstance(k.value, int) else None
            if isinstance(e, ast.BinOp) and isinstance(e.right, ast.Constant) and isinstance(e.right.value, str):
                d = folder(e.left)
                if d is not None and (isinstance(e.op, ast.Div) or isinstance(e.op, ast.Add) and e.right.value.startswith("/")):
                    return _under(d, e.right.value)
                return None
            if isinstance(e, ast.JoinedStr) and e.values and isinstance(e.values[0], ast.FormattedValue):
                d = folder(e.values[0].value)
                rest = e.values[1:]
                if d is not None and all(isinstance(x, ast.Constant) for x in rest):
                    return _under(d, "".join(x.value for x in rest))
                return None
            if isinstance(e, ast.Call):
                name = _func_name(e)
                head = e.args[0] if e.args else e.func.value if isinstance(e.func, ast.Attribute) else None
                if head is None or name not in BUILDERS:
                    return None
                rest = e.args[1:] if e.args and head is e.args[0] else e.args
                d = folder(head)
                if name in SAME_DIR:
                    return d
                if name == "dirname":
                    return _up(d)
                if d is not None and all(isinstance(x, ast.Constant) and isinstance(x.value, str) for x in rest):
                    return _under(d, *(x.value for x in rest))
            return None
        binds = sorted((n for n in nodes if isinstance(n, (ast.Assign, ast.AnnAssign)) and n.value is not None), key=lambda n: (n.lineno, n.col_offset))
        for _ in range(3):  # a root bound from a root bound from __file__: a few passes reach the fixpoint
            for n in binds:
                if has_root(n.value):
                    for t in (n.targets if isinstance(n, ast.Assign) else [n.target]):
                        if isinstance(t, ast.Name):
                            roots[t.id] = folder(n.value)
        consts = []
        for n in nodes:
            if isinstance(n, ast.stmt):
                for e in _top_exprs(n):  # any expression that holds a root: each string in it may be a path part
                    if has_root(e):
                        consts += [y.value for y in ast.walk(e) if isinstance(y, ast.Constant) and isinstance(y.value, str)]
            if isinstance(n, ast.Call):
                name = _func_name(n)
                if name in READERS:  # a bare relative path: CI runs at the repo top
                    for x in n.args:
                        if _constant_path(x):
                            consts += [y.value for y in ast.walk(x) if isinstance(y, ast.Constant) and isinstance(y.value, str) and not y.value.startswith("/")]
                heads = list(n.args) + ([n.func.value] if isinstance(n.func, ast.Attribute) else [])
                for x in heads:
                    d = folder(x) if has_root(x) else None
                    if d is None:
                        continue
                    if name in ("insert", "append") and isinstance(n.func, ast.Attribute):
                        path_dirs.add(d)  # sys.path.insert(0, <root>): a folder its imports come from
                    if name not in builders and (d == "." or any(p.startswith(d + "/") for p in paths)):
                        return roots, True  # a root taken whole, as by a walk: every path under it
        return roots, any(w.search(c) for c in consts for w in words)

    module, hit = analyze(tree, {})
    if hit or any(analyze(f, module)[1] for f in ast.walk(tree) if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))):
        return True
    if read is None or depth < 1:
        return False
    mods = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module and not n.level}
    for mod in sorted(mods):
        for d in [posixpath.dirname(rel) or ".", *sorted(path_dirs)]:
            for cand in (_under(d, mod.replace(".", "/") + ".py"), _under(d, mod.replace(".", "/"), "__init__.py")):
                text = cand and read(cand)
                if text is not None and text is not False and cand != rel:
                    try:
                        if python_suite_hits(text, cand, paths, read, depth - 1):
                            return True
                    except SyntaxError:
                        return True  # a module it cannot read is read as a hit
                    break
    return False

def lint_steps(root, base_ref, env=None):
    """-> the names of the `checks` steps `ci-job --lint` runs, from its own plan: ci-job is the one home of that choice."""
    c, out = sh([sys.executable, CI_JOB, "checks", "--lint", "--plan", "--base", base_ref], cwd=root, env=env, timeout=120)
    if c:
        raise Stop(f"the lint steps cannot be listed (exit {c})")
    return {l[len("would run"):].strip() for l in out.splitlines() if l.startswith("would run ")}

def hit_suites(root, paths, skip):
    """-> [(file, line)]: each suite line of the `checks` job in root's workflow whose source names one of `paths`
    (needles), except a mutation script and the steps named in `skip`. The workflow is the one home of which suites
    run, so no list is kept here. A step's `if:` is not read: the batch may have turned it on. Stop when the
    workflow, its job or a suite source cannot be read, or a hit line is not a plain suite line."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lint"))
    from workflow_steps import job_block, run_body, step_blocks, step_key  # the one home of the step parser
    try:
        with open(os.path.join(root, ".github", "workflows", "checks.yml"), encoding="utf-8") as f:
            block = job_block(f.read(), "checks")
    except (OSError, UnicodeError) as e:
        raise Stop(f"the workflow cannot be read ({type(e).__name__})")
    if block is None:
        raise Stop("the workflow has no `checks` job")
    words = _words({n for p in paths for n in needles(p)})
    names = _words({x for p in paths for x in (p, p.split("/")[-1], *(p.rsplit("/", i)[0] for i in range(1, p.count("/") + 1)))})
    def read(path):
        try:
            with open(os.path.join(root, *path.split("/")), encoding="utf-8") as f:
                return f.read()
        except (OSError, UnicodeError):
            return None
    hits = []
    for step in step_blocks(block):
        if step_key(step, "name") in skip:
            continue
        for line in (run_body(step) or "").splitlines():
            line = line.strip()
            m = re.match(r"(?:python3|node|bash) +(\S+\.(?:py|mjs|sh))\b", line)
            if not m:  # a line of no suite form is never read, so one that names main's paths or their folders refuses
                if line and any(w.search(line) for w in names):
                    raise Stop(f"the checks line `{line}` names main's paths and is no suite this tool can read")
                continue
            if "mutate" in m.group(1):
                continue
            try:
                with open(os.path.join(root, *m.group(1).split("/")), encoding="utf-8") as f:
                    text = f.read()
            except (OSError, UnicodeError) as e:
                raise Stop(f"the suite {m.group(1)} cannot be read ({type(e).__name__})")
            if m.group(1).endswith(".py"):
                try:
                    hit = python_suite_hits(text, m.group(1), paths, read)
                except (SyntaxError, ValueError, RecursionError) as e:
                    raise Stop(f"the suite {m.group(1)} cannot be parsed ({type(e).__name__})")
            else:  # node and bash suites: any needle in the source is a hit, which fails safe
                hit = any(w.search(text) for w in words)
            if hit:
                if not SUITE_LINE.fullmatch(line):
                    raise Stop(f"the suite line `{line}` reads main's paths and cannot be run as written")
                hits.append((m.group(1), line))
    return hits

_SMALL_MOVES = {}  # (worktree, head, base tip) -> the verdict, so the read after the wait does not repeat a proof it already holds

def small_base_move(wt, base_ref, sha, before_run=None):
    """-> (True, why the green run on sha stands) or (False, why not), for a sha that lacks the base tip T.
    It stands only when main's paths since the merge base M share no path with the batch's (the records page aside: the
    generator proves it on the merge), the merge of sha and T is clean, the repo's ci-scope.sh turns on no job and no suite
    for main's paths, and on that merge the `checks` lint steps pass and so does each other `checks` suite that names one of
    main's paths (hit_suites). Anything unread refuses. The worktree goes back to its HEAD.
    Cost per call: about 10 git starts, one ci-scope.sh run, two ci-job runs (a plan, and the lints at two starts per
    step) and one start per hit suite; one temp output file, and one ci-job log, kept only on a failure."""
    c, tip = git(wt, "rev-parse", base_ref)
    if c:
        return False, f"cannot read {base_ref}"
    key = (wt, sha, tip)
    if key in _SMALL_MOVES:
        return _SMALL_MOVES[key]
    c, m = git(wt, "merge-base", sha, tip)
    if c or not m:
        return False, "the merge base cannot be read"
    reads = [git(wt, "diff", "--name-only", "--no-renames", "-z", m, x) for x in (tip, sha)]  # --no-renames: a moved file names both paths
    count = git(wt, "rev-list", "--count", f"{sha}..{tip}")
    if any(c for c, _ in reads) or count[0]:
        return False, "the paths of main or of the batch cannot be read"
    theirs, ours = ({p for p in out.split("\0") if p} for _, out in reads)
    shared = sorted((theirs & ours) - {RECORDS_PAGE})
    if not theirs or shared:
        return False, "main and the batch both change " + ", ".join(shared) if shared else "main's commits change no path"
    c, head = git(wt, "rev-parse", "HEAD")
    if c:
        return False, "the worktree's HEAD cannot be read"
    fd, out_file = tempfile.mkstemp(prefix="merge-scope-")
    os.close(fd)
    fd, log = tempfile.mkstemp(prefix="merge-lint-", suffix=".log")
    os.close(fd)
    keep = False
    try:
        c, out = git(wt, *identity(wt), "merge", "--no-ff", "-q", "-m", f"Merge {base_ref} to read the lints", tip)
        if c:
            return False, f"the head does not merge cleanly with {base_ref}"
        if not os.path.isfile(os.path.join(wt, *CI_SCOPE.split("/"))):
            return False, f"the repo has no {CI_SCOPE} to say which jobs read main's paths"
        # On the merge, sha...HEAD is main's paths: the same set as M..T, because the two sides share none
        env = {**{k: v for k, v in os.environ.items() if not k.startswith("GITHUB_")}, "EVENT": "pull_request", "BASE_SHA": sha, "GITHUB_OUTPUT": out_file}
        c, out = sh(["bash", CI_SCOPE], cwd=wt, env=env, timeout=120)
        with open(out_file, encoding="utf-8") as f:
            flags = dict(l.strip().split("=", 1) for l in f if "=" in l)
        on = sorted(k for k, v in flags.items() if v != "false")
        if on or not flags:
            return False, f"{CI_SCOPE} turns on " + (", ".join(on) if flags else "every job (it gave no answer)") + " for main's paths"
        if c:
            return False, f"{CI_SCOPE} failed (exit {c}) on main's paths"
        if before_run:
            before_run(LINT_SECONDS)  # extends the merge lock past the run, or stops with a NetStop
        # --base is the base tip, as a pull request run reads its base: it checks the merge against main as it is now
        c, out = sh([sys.executable, CI_JOB, "checks", "--lint", "--base", base_ref], cwd=wt, env={**env, "VERDICT_LOG": log}, timeout=LINT_SECONDS)
        if c:
            keep = True
            bad = [l.strip() for l in out.splitlines() if l.startswith(("FAIL", "unknown"))]
            return False, f"the lints of the merge are not all PASS ({'; '.join(bad[:3]) or 'exit ' + str(c)}; full output: {log})"
        try:
            # the records page is left out: it is derived from the records, which are matched, and the generator proves it on the merge
            suites = hit_suites(wt, sorted(theirs - {RECORDS_PAGE}), lint_steps(wt, base_ref, env))
        except Stop as e:
            return False, str(e)
        if suites and before_run:
            before_run(LINT_SECONDS)
        end = time.monotonic() + LINT_SECONDS
        for suite, line in suites:  # each suite that reads one of main's paths, run on the merge as the workflow writes it
            c, out = sh(["bash", "-c", line], cwd=wt, env=env, timeout=max(1, end - time.monotonic()))
            if c:
                return False, f"{suite} fails on the merge (exit {c})"
        n = int(count[1])
        verdict = True, f"{base_ref.split('/', 1)[-1]} moved by {n} commit{'s' * (n != 1)} touching only paths no job of this batch reads; the lints pass on the merge"
        _SMALL_MOVES[key] = verdict
        return verdict
    except (subprocess.TimeoutExpired, OSError, ValueError) as e:
        return False, f"the proof could not run ({type(e).__name__})"
    finally:
        git(wt, "merge", "--abort")
        git(wt, "reset", "--hard", "-q", head)
        git(wt, "clean", "-fdq")
        for f in (out_file, *(() if keep else (log,))):
            with contextlib.suppress(OSError):
                os.remove(f)

def holds_base(wt, base_ref, sha, before_run=None):
    """-> (None, None) when sha holds the tip of base_ref; (None, why) when it does not but its green run still stands
    (small_base_move); else (why not, None). The checks ran on sha, so a sha without that tip was never tested against
    the base as it is now. Branch protection has strict false, so GitHub does not refuse it (merge-needs-current-base)."""
    c, out = git(wt, "merge-base", "--is-ancestor", base_ref, sha)
    if c == 0:
        return None, None
    if c == 1:
        ok, why = small_base_move(wt, base_ref, sha, before_run)
        if ok:
            return None, why
        tip = git(wt, "rev-parse", "--short=9", base_ref)[1]
        base = base_ref.split("/", 1)[-1]
        return (f"{sha[:9]} does not hold {base_ref} at {tip}, so no run on it tested the current {base}. "
                f"Merge {base} into the branch, push, and run again. The green run cannot stand: {why}."), None
    return f"cannot read whether {sha[:9]} holds {base_ref}, so the run cannot be proved current: {out}", None

def push_branch(wt, branch):
    """A plain push. Never force: a moved branch refuses it, and nothing reaches origin."""
    c, out = git(wt, "push", "-q", "origin", f"HEAD:refs/heads/{branch}")
    if c:
        raise Stop(f"the push of {branch} was refused. Nothing is on origin from this run. Run again.\n{out}")

def origin_head(root, branch):
    return git(root, "ls-remote", "origin", f"refs/heads/{branch}")[1].split("\t")[0]

def revert_claim(root, wt, branch, claim_sha):
    """Revert only while the origin head is the claim commit. Else the claim commit can be gone."""
    if origin_head(root, branch) != claim_sha:
        say(f"merge: origin {branch} is not the claim commit {claim_sha[:9]}. Nothing reverted. Run again.")
        return False
    cmd = f"git fetch origin {branch} && git checkout {branch} && git revert --no-edit {claim_sha} && git push origin {branch}"
    c, out = git(wt, "revert", "--no-edit", claim_sha)
    if not c:
        c, out = git(wt, "push", "-q", "origin", f"HEAD:refs/heads/{branch}")
    if c:
        say(f"merge: the revert was refused. The claim stays on {branch}. Run:\n  {cmd}\n{out}")
        return False
    say(f"merge: claim {claim_sha[:9]} reverted on {branch}.")
    return True

def holder(root, branch):
    path = None
    for line in git(root, "worktree", "list", "--porcelain")[1].splitlines():
        if line.startswith("worktree "):
            path = line[9:].strip()
        elif line.strip() == f"branch refs/heads/{branch}":
            return path
    return None

def ff_main(root, base, commit):
    """Move the local base branch onto `commit`, a commit that origin holds."""
    c, out = git(root, "fetch", "-q", "origin")
    if c:
        raise Stop("git fetch origin failed, so the local main cannot be moved: " + out)
    if git(root, "merge-base", "--is-ancestor", commit, f"refs/remotes/origin/{base}")[0]:
        raise Stop(f"{commit[:9]} is not on origin/{base}. Nothing was moved.")
    tree = holder(root, base)
    if tree:
        if git(tree, "rev-parse", "--abbrev-ref", "HEAD")[1] != base:
            raise Stop(f"{tree} is not on {base}. Nothing was moved.")
        c, out = git(tree, "merge", "-q", "--ff-only", commit)
    else:
        c, out = git(root, "fetch", "-q", "origin", f"{base}:{base}")
    if c:
        # Drop git's advice lines (commit, stash, move, remove): they name the forbidden way out.
        kept = "\n".join(l for l in out.splitlines() if not l.startswith(("Please ", "Aborting")))
        where = os.path.realpath(tree or root)
        raise Stop(f"the local main did not move in {where}. {kept}\nFast-forward {base} there by hand.")
    say(f"merge: local {base} is at {commit[:9]}.")

def _keep_words(reason):
    """The sweep's keep reason in plain words for the `kept here` line."""
    if reason.startswith("dirty"):
        return "dirty: it has uncommitted changes."
    if reason.startswith(("unmerged", "unpushed")):
        return "its HEAD is not in the merged head, so it holds local-only commits."
    if reason.startswith("locked"):
        return "the worktree has a lock (" + reason + ")."
    if reason.startswith("live-session"):
        return "a live Claude session works in it."
    if reason.startswith("process-inside"):
        return "a process runs inside it (" + reason + ")."
    if reason.startswith("unreadable"):
        return "a read on it failed, so it is not judged removable."
    return reason + "."

def remove_held_tree(root, branch, held, merged):
    """Remove the one worktree `held` that holds `branch`, by the janitor sweep's fast path
    (janitor/sweep.py `decide_worktree`, `remove_worktree`): one home for what may go, no --force.
    -> True when the tree is gone and the caller may delete the branch; False when it stays, after one
    `kept here` line. The caller's cwd inside the tree, a primary checkout and any failed read keep it."""
    def keep(why):
        say(f"merge: {branch} kept here: {why}")
        return False
    try:
        here, tree = os.path.realpath(os.getcwd()), os.path.realpath(held)
        if here == tree or here.startswith(tree + os.sep):
            return keep(f"the current directory (cwd) is inside {held}.")
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "janitor"))
        import sweep  # janitor/sweep.py: the one home of the worktree keep rule and the removal
        entry = next((e for e in sweep.parse_worktree_list(root) or [] if os.path.realpath(e["path"]) == tree), None)
        if entry is None:
            return keep(f"checked out in {held}, whose entry could not be read.")
        if sweep._is_primary_checkout(held) is not False:
            return keep(f"checked out in {held}, the primary checkout or a tree not proven linked.")
        batch = sweep.merged_batch(root, merged)
        if batch is None:
            return keep(f"checked out in {held}; which commits are merged could not be read.")
        decision = sweep.decide_worktree(root, entry, attended=True, fast=True, batch=batch)
        if decision["action"] != "reap":
            return keep(_keep_words(decision["reason"]))
        sweep.remove_worktree(root, held, decision)
        if decision.get("error") or os.path.exists(held):
            return keep("it could not be removed: " + str(decision.get("error", "the folder is still there")))
    except Exception as e:  # any failed import or read keeps the tree; the merge is done
        return keep(f"checked out in {held}; the janitor read failed ({type(e).__name__}: {e}).")
    say(f"merge: worktree {held} removed.")
    return True

def cut_branch(root, branch, merged):
    """Delete the head branch on origin, and here unless it has local-only commits (its tip must be an
    ancestor of `merged`, the head that merged). A worktree that holds the branch goes first when the
    janitor sweep's fast path judges it removable (`remove_held_tree`); otherwise it stays, with one
    line why. Never fails the merge."""
    c, out = git(root, "push", "-q", "origin", "--delete", branch)
    # A gone remote ref is a deleted branch: the repo may set delete_branch_on_merge.
    gone = c and "remote ref does not exist" in out
    say(f"merge: origin/{branch}: " + ("deleted." if not c else "already deleted." if gone else "not deleted: " + (out.splitlines() or ["?"])[-1]))
    cut_local(root, branch, merged)

def cut_local(root, branch, merged):
    """The local half of a branch's cleanup, for the PR's branch and each lane branch: a worktree that holds it goes
    first when the janitor sweep's fast path judges it removable (`remove_held_tree`), else the branch stays (that
    function prints why). The branch is deleted only when its tip is an ancestor of `merged`; a tip outside it holds
    local-only commits. No --force. A branch that is not here is a no-op."""
    if git(root, "rev-parse", "-q", "--verify", f"refs/heads/{branch}")[0]:
        return
    held = holder(root, branch)
    if held and not remove_held_tree(root, branch, held, merged):
        return
    if git(root, "merge-base", "--is-ancestor", f"refs/heads/{branch}", merged)[0]:
        say(f"merge: {branch} kept here: its tip is not in the merged head {merged[:9]}, so it holds local-only commits.")
    else:
        c, out = git(root, "branch", "-D", branch)
        say(f"merge: {branch} here: " + ("deleted." if not c else "not deleted: " + out))

def read_lanes(wt, base_ref, sha):
    """-> (tips, dropped). tips: parents 2+ of each merge commit in base_ref..sha, less any already on base_ref
    (a merge of the base into the branch has a base commit as its second parent). dropped: the tips whose every such
    merge is net-reverted on the batch: a "This reverts commit <sha>." message names it, and a revert of that revert
    undoes it, so an odd chain is a revert. A read that fails raises."""
    c, out = git(wt, "log", "--format=%H%x01%P%x01%B%x00", f"{base_ref}..{sha}")
    if c:
        raise ValueError("git log failed: " + (out.splitlines() or ["?"])[-1])
    undone, took = {}, {}  # commit -> the commit that reverts it; tip -> the merges that took it in
    for rec in out.split("\0"):
        parts = rec.strip().split("\x01", 2)
        if len(parts) != 3:
            continue
        h, parents, body = parts
        for r in re.findall(r"This reverts commit ([0-9a-f]{40})", body):
            undone[r] = h
        for t in parents.split()[1:]:
            took.setdefault(t, []).append(h)
    def reverted(h):
        n, seen = 0, set()
        while h in undone and h not in seen:
            seen.add(h)
            h, n = undone[h], n + 1
        return n % 2 == 1
    tips = []
    for t in took:
        c, out = git(wt, "merge-base", "--is-ancestor", t, base_ref)
        if c not in (0, 1):  # 1 is "not an ancestor"; any other code is a failed read
            raise ValueError(f"git merge-base failed on {t[:9]}: " + (out.splitlines() or ["?"])[-1])
        if c:
            tips.append(t)
    return tips, {t for t in tips if all(reverted(h) for h in took[t])}

def lane_tips(wt, base_ref, sha):
    """read_lanes, read before the merge. A read that fails prints one line and returns no lanes: the merge goes on and nothing is deleted."""
    try:
        return read_lanes(wt, base_ref, sha)
    except Exception as e:
        say(f"merge: no lane branch is deleted: the batch's merge commits could not be read ({type(e).__name__}: {e}).")
        return [], set()

def refuse_dropped_lane(wt, base_ref, sha, unknown_ok=""):
    """A lane dropped by a revert of its merge puts a removal commit on the base. When that lane later merges the base,
    the revert silently deletes its files (batch #663: the platform-ask lane lost 11 of 13 files). Refuse it before anything
    is claimed. A read that fails refuses too, unless the owner passed --undo-check-unknown-ok "<reason>"."""
    try:
        _, dropped = read_lanes(wt, base_ref, sha)
    except Exception as e:
        if unknown_ok.strip():
            say(f"merge: dropped-lane check UNKNOWN ({type(e).__name__}: {e}). Owner override, reason: {unknown_ok.strip()}")
            return
        raise Stop(f"the dropped-lane check could not read the batch's merge commits ({type(e).__name__}: {e}).\n"
                   "If the owner accepts that, run again with --undo-check-unknown-ok \"<reason>\".")
    if dropped:
        raise Dropped("the batch drops a lane by a revert of its merge (lane tip " + ", ".join(sorted(t[:9] for t in dropped))
                      + "). Main would hold the revert, and the lane would lose its files when it merges main.\n"
                      "Instead, rebuild the batch branch from main without the lane, then run again.")

def cut_lanes(root, lanes, commit, host=None, base=None, skip=(), keep=(), dropped=()):
    """Delete the lane branches on origin that the batch took in: the heads, read after the merge, that sit at a lane tip.
    One line per lane, never a silent drop. A lane tip that no head sits at has moved or is gone. Kept, with a line why:
    a name in `keep`; a head at a tip in `dropped`, whose merge into the batch was reverted on the batch; one whose open PR is at another sha than its tip, or at its tip with a base that is neither `base`,
    the batch's base, nor a lane of this batch (a backport); none when the open-PR read fails; one whose tip is in
    `commit` neither by id nor by patch, or whose proof could not run; the base of an open PR whose head is no lane of
    this batch at its tip (a partial stack), and the base of a lane that is itself kept, to a fixpoint. A PR is done when
    its head sits at a lane tip of this batch; a base is a lane of this batch whether kept or not. A name in `skip` is
    no lane. Dependents are deleted before their base, each delete leased to the tip. A base whose dependent was not
    deleted is kept, with a line. Each lane has its own try. Never fails the merge.
    Then, whatever the origin read or the remote pass found (GitHub may have deleted the heads already), the local
    side: every local branch, of any name, whose tip equals a lane tip not in `dropped`, except a name in `skip`,
    gets `cut_local`'s cleanup. A branch at no lane tip is never touched. The local pass follows the remote pass: a
    name in `keep` stays, and so does every local branch at the tip of a head the remote pass kept or failed to
    delete, for any reason. It does not run when the heads or the open PRs could not be read."""
    def local_pass(held):  # held: the tips whose remote head stays
        try:
            c, out = git(root, "for-each-ref", "--format=%(objectname) %(refname:short)", "refs/heads/")
            if c:
                return
            live = {t for t in lanes if t not in dropped and t not in held}
            for line in out.splitlines():
                sha, _, name = line.partition(" ")
                if sha in live and name not in skip and name not in keep:
                    try:  # one lane's failure never stops the next lane
                        cut_local(root, name, commit)
                    except Exception as e:
                        say(f"merge: {name} here: not deleted: {type(e).__name__}: {e}")
        except Exception as e:
            say(f"merge: the local lane cleanup stopped: {type(e).__name__}: {e}")
    try:
        import guard_core  # hooks/guard_core.py: the one home of the cherry test
        c, out = git(root, "ls-remote", "--heads", "origin")
        if c:
            say("merge: no lane branch is deleted: the heads on origin could not be read: " + (out.splitlines() or ["?"])[-1])
            return
        rows = [l.split("\t", 1) for l in out.splitlines()]
        heads = {r[1].removeprefix("refs/heads/"): r[0] for r in rows if len(r) == 2 and r[0] in lanes}
        for tip in lanes:
            if tip not in heads.values():
                say(f"merge: lane {tip[:9]}: no head on origin sits at this tip: it moved or is gone.")
        heads = {b: t for b, t in heads.items() if b not in skip}
        kept = {b: "kept: its merge into the batch was reverted on the batch." for b, t in heads.items() if t in dropped}  # b -> the line's words
        kept.update({b: "kept: it is in merge.keepBranches." for b in heads if b in keep})
        shown = set(kept)
        for b in kept:
            say(f"merge: lane origin/{b}: {kept[b]}")
        if len(kept) == len(heads):
            local_pass({heads[b] for b in kept})
            return
        try:
            # {head name: (head sha, PR base)}; a head with two PRs has a None base, and one name:index row per PR
            prs = [(k.split(":")[0], sha, pb) for k, (sha, pb) in host.open_heads().items() if pb is not None]
            opened = True
        except Exception:  # unreadable or malformed: delete nothing
            opened = None
        proofs = {}
        def proof(b):  # why the tip is not in the merge commit, or None; one run per lane
            if b not in proofs:
                a = git(root, "merge-base", "--is-ancestor", heads[b], commit)[0]
                why = None
                if a == 1:
                    proven = guard_core.branch_cherry_empty(root, commit, heads[b])
                    why = None if proven else "its tip is not in the merge commit." if proven is not None else "the proof could not run."
                elif a:
                    why = "the proof could not run."
                proofs[b] = why
            return proofs[b]
        def reason(b):
            tip = heads[b]
            if opened is None:
                return "the open PRs could not be read."
            # an open PR is done when its head sits at a lane tip of this batch; a kept head still needs its base
            if needs := sorted({n for n, sha, pb in prs if pb == b and (heads.get(n) != sha or n in kept)}):
                return "it is the base of an open PR: " + ", ".join(needs) + "."
            if any(n == b and sha != tip for n, sha, _ in prs):
                return "it has an open PR."
            if other := sorted({pb for n, _, pb in prs if n == b and pb != base and pb not in heads}):
                return "its open PR at the tip has another base: " + ", ".join(other) + "."  # the base or a batch lane: its own PR, done
            return proof(b)
        changed = True
        while changed:  # a kept lane keeps its base, which may keep its own: until no lane changes
            changed = False
            for b in heads:
                if b in kept:
                    continue
                try:
                    why = reason(b)
                    line = why and "kept: " + why
                except Exception as e:  # one lane's failure never stops the next lane
                    line = f"not deleted: {type(e).__name__}: {e}"
                if line:
                    kept[b] = line
                    changed = True
        for b in heads:
            if b in kept and b not in shown:
                say(f"merge: lane origin/{b}: {kept[b]}")
        rest = [b for b in heads if b not in kept]
        order = []
        while rest:  # dependents first: a lane waits while a lane left in `rest` has an open PR based on it
            ready = [b for b in rest if not any(pb == b and n in rest for n, _, pb in prs)] or rest
            order += ready
            rest = [b for b in rest if b not in ready]
        blocked = {}  # base -> the lane whose delete did not happen
        stays = {heads[b] for b in kept}  # tips whose remote head stays
        for b in order:
            tip = heads[b]
            if b in blocked:
                say(f"merge: lane origin/{b}: kept: {blocked[b]} was not deleted, and its open PR is based on this lane.")
                undone = True
            else:
                try:
                    c, out = git(root, "push", "-q", "origin", f"--force-with-lease=refs/heads/{b}:{tip}", f":refs/heads/{b}")
                    say(f"merge: lane origin/{b}: " + (f"deleted at {tip[:9]}." if not c else "not deleted: " + (out.splitlines() or ["?"])[-1]))
                    undone = bool(c)
                except Exception as e:  # one lane's failure never stops the next lane
                    say(f"merge: lane origin/{b}: not deleted: {type(e).__name__}: {e}")
                    undone = True
            if undone:
                stays.add(tip)
                for n, _, pb in prs:
                    if n == b:
                        blocked.setdefault(pb, b)
        if opened is not None:  # an unread PR list means nothing is known to be done
            local_pass(stays)
    except Exception as e:  # a lane cleanup never fails a merge that landed
        say(f"merge: the lane cleanup stopped: {type(e).__name__}: {e}")

def after_merge(root, cmds):
    """Run each command. True when every one passed. A failure never undoes the merge."""
    ok = True
    for cmd in cmds:
        # nowindow: the afterMerge command prints on the caller's terminal; with no window that output goes to a hidden console
        c = subprocess.run([resolve_program("bash"), "-c", cmd], cwd=root).returncode
        say(f"merge: afterMerge `{cmd}`: " + ("done." if not c else f"FAILED (exit {c}). The merge landed and stays."))
        ok = ok and not c
    return ok

# ------------------------------------------------------------------ the flow

MERGE_DEFAULTS = {"method": "merge", "deadlineMinutes": 45, "requiredChecks": "protection", "afterMerge": []}
MERGE_FIELDS = set(MERGE_DEFAULTS) | {"deleteBranch", "ignoreChecks", "keepBranches", "standingGrant"}

def host_default_branch(root):
    # time.sleep is looked up at call time, so a test's patch of it holds. No retry inside `shared_deadline`, as in Host.gh.
    c, out, n = retry_net(lambda: sh(["gh", "api", "repos/{owner}/{repo}", "-X", "GET"], cwd=root), lambda s: time.sleep(s), NET_RETRIES if _READ_DEADLINE is None else 0, "`gh api repos`")
    if is_net(c, out):
        raise NetStop(f"network error from `gh api repos`, still failing after {n} retries. Run again.\n{out}")
    try:
        if c:
            raise ValueError(out)
        name = json.loads(out)["default_branch"]
        if not isinstance(name, str) or not name:
            raise ValueError("no default_branch in the answer")
        return name
    except (ValueError, KeyError, TypeError) as e:
        raise Stop(f"the default branch cannot be read from gh: {e}")

def job_minutes(row):
    """Minutes a check row ran, from startedAt to completedAt. None when either is missing or the job has not finished (gh gives a pending one the zero time)."""
    try:
        a, b = (datetime.datetime.fromisoformat(row[k].replace("Z", "+00:00")) for k in ("startedAt", "completedAt"))
    except (KeyError, AttributeError, ValueError):
        return None
    return (b - a).total_seconds() / 60 if b > a else None

def workflow_dir(start):
    """The `.github/workflows` of the checkout that holds `start` (the working directory when None): the nearest one up the tree, so a run from a subfolder reads the repo root's.
    The search stops at the checkout's root (the first folder holding .git), so a nested checkout never reads its parent's caps."""
    d = pathlib.Path(start or ".").resolve()
    for p in (d, *d.parents):
        if (q := p / ".github" / "workflows").is_dir():
            return q
        if (p / ".git").exists():
            return None
    return None

def job_caps(texts):
    """-> {job id or job name: timeout-minutes} from workflow file texts. A line scan, since the repo has no YAML reader:
    only a job's own keys count, at four spaces under a two-space job id under `jobs:`. A step's cap, a comment, a block scalar
    and a quoted string are deeper or start with another character. A quoted number counts. An expression (`${{ ... }}`) is unknown: the job has no cap."""
    caps = {}
    for text in texts:
        in_jobs, job, jobs = False, None, []
        for line in text.splitlines():
            if re.match(r"[^\s#]", line):
                in_jobs, job = line.startswith("jobs:"), None
            elif in_jobs and (m := re.match(r"^ {2}([\w-]+):\s*(?:#.*)?$", line)):
                job = {"ids": [m.group(1)], "cap": None}
                jobs.append(job)
            elif job and (m := re.match(r"^ {4}name:\s*(.+?)\s*$", line)):
                job["ids"].append(m.group(1).strip("'\""))
            elif job and (m := re.match(r"^ {4}timeout-minutes:\s*['\"]?(\d+)['\"]?\s*(?:#.*)?$", line)):
                job["cap"] = int(m.group(1))
        for i, cap in ((i, j["cap"]) for j in jobs if j["cap"] for i in j["ids"]):
            caps[i] = max(cap, caps.get(i, 0))  # one id in two files: the larger cap, so neither the floor nor the warning runs short
    return caps

def base_workflows(root, ref):
    """The workflow files on `ref`, read with git (the base branch, never the local tree)."""
    c, listed = git(root, "ls-tree", "-r", "--name-only", ref, "--", ".github/workflows")
    if c:
        raise Stop(f"cannot read {ref} to look for .github/workflows: {listed}")
    return [f for f in listed.splitlines() if f.endswith((".yml", ".yaml"))]

def base_job_caps(root, ref):
    """job_caps of the workflow files on `ref`, read with git (the base branch, never the local tree)."""
    texts = []
    for f in base_workflows(root, ref):
        c, text = git(root, "show", f"{ref}:{f}")
        if c:
            raise Stop(f"cannot read {f} on {ref}: {text}")
        texts.append(text)
    return job_caps(texts)

def load_config(root, base, path):
    """The repo's config, read from the base branch on origin: never the local checkout, never the PR tree.
    No file: all defaults. A file with fields left out: defaults for those fields. A broken file stops."""
    ref = f"origin/{base}"
    c, out = git(root, "fetch", "-q", "origin", f"+refs/heads/{base}:refs/remotes/origin/{base}")
    if c:
        raise Stop(f"git fetch origin {base} failed: {out}")
    c, listed = git(root, "ls-tree", "--name-only", ref, "--", path)
    if c:  # an unreadable base is not an absent file
        raise Stop(f"cannot read {ref} to look for {path}: {listed}")
    if not listed:
        branch = host_default_branch(root)
        say(f"merge: {path} not found on {ref}. Using the defaults: merge method merge, 45 minute deadline, required checks from branch protection, default branch {branch}.")
        return {"defaultBranch": branch, "merge": dict(MERGE_DEFAULTS)}
    try:
        c, text = git(root, "show", f"{ref}:{path}")
        if c:
            raise ValueError(text)
        cfg = json.loads(text)
        if not isinstance(cfg, dict) or not isinstance(cfg.get("merge", {}), dict):
            raise ValueError("not an object")
    except ValueError as e:
        raise Stop(f"cannot read the config {path} on {ref}: {e}")
    m = cfg.setdefault("merge", {})
    unknown = sorted(set(m) - MERGE_FIELDS)
    if unknown:
        raise Stop(f"{path} on {ref} has an unknown field in the merge block: {', '.join(unknown)}")
    if not isinstance(m.get("ignoreChecks", []), list):
        raise Stop(f"{path} on {ref}: merge.ignoreChecks must be a list, not {m['ignoreChecks']!r}.")
    dm = m.get("deadlineMinutes", MERGE_DEFAULTS["deadlineMinutes"])
    if not isinstance(dm, int) or isinstance(dm, bool) or not 1 <= dm <= 360:  # 360: GitHub's longest job run
        raise Stop(f"{path} on {ref}: merge.deadlineMinutes must be a whole number from 1 to 360, not {dm!r}.")
    caps = base_job_caps(root, ref)
    floor = min(max(caps.values(), default=0) + 5, 360)  # clamped: 360 is the most a deadline may be
    if caps and dm < floor:  # the wait must outlast the slowest job's cap, or a job still within its cap reads as a deadline miss
        # Wait the floor, never stop: a stop here would block the very PR that raises the deadline.
        m["deadlineMinutes"] = floor
        say(f"merge: the largest job timeout-minutes in .github/workflows is {max(caps.values())}, so the wait is {floor} minutes, not {dm}. "
            f"raise merge.deadlineMinutes in {path} to at least {floor}")
    ne = lambda v: isinstance(v, str) and v.strip()
    # A branch name as `git ls-remote` lists it: no ref path, no glob, and one that `git check-ref-format --branch` takes as is
    # (it turns @{-1} into another name). The regex holds what a git build may take, such as the backslash.
    plain_name = lambda v: (ne(v) and not re.search(r"[\s*?\[:~^\\]|\.\.|^-", v) and not v.startswith(("refs/", "origin/"))
                            and git(root, "check-ref-format", "--branch", v) == (0, v))
    rc, am = m.get("requiredChecks", "protection"), m.get("afterMerge", [])
    for ok, k in ((m.get("method", "merge") in ("merge", "squash", "rebase"), "method"),
                  (isinstance(m.get("deleteBranch", True), bool), "deleteBranch"),
                  (isinstance(m.get("standingGrant", True), bool), "standingGrant"),
                  (isinstance(am, list) and all(map(ne, am)), "afterMerge"),
                  (isinstance(m.get("keepBranches", []), list) and all(map(plain_name, m.get("keepBranches", []))), "keepBranches"),
                  (rc == "protection" or isinstance(rc, list) and rc and all(map(ne, rc)), "requiredChecks")):
        if not ok:
            raise Stop(f"{path} on {ref}: merge.{k} is not valid: {m[k]!r}.")
    if "defaultBranch" in cfg and not ne(cfg["defaultBranch"]):
        raise Stop(f"{path} on {ref}: defaultBranch must be a non-empty string, not {cfg['defaultBranch']!r}.")
    ignore_checks(cfg)  # refuse a bad entry before the defaults notice, so the refusal is the only line
    filled = [k for k in MERGE_DEFAULTS if k not in m]
    for k in filled:
        m[k] = MERGE_DEFAULTS[k]
    if not cfg.get("defaultBranch"):
        cfg["defaultBranch"] = host_default_branch(root)
        filled.insert(0, "defaultBranch")
    if filled:
        say(f"merge: {path} on {ref} leaves out {', '.join(filled)}. Using the defaults for those.")
    return cfg

def refuse_bad_pr(info, draft_ok=False):
    if info["state"] != "OPEN":
        raise Stop(f"the pull request is {info['state']}")
    if info["draft"] and not draft_ok:
        raise Stop("the pull request is a draft. Mark it ready after review and run again. Nothing was claimed.")
    if info["mergeable"] == "CONFLICTING" or info["merge_state"] == "DIRTY":
        raise Stop("the pull request is CONFLICTING. Merge the base into the branch and run again. Nothing was claimed.")

def open_worktree(root, info, base):
    """Fetch, check that the head is the one gh named, and make a detached worktree there."""
    for ref in (base, info["branch"]):
        c, out = git(root, "fetch", "-q", "origin", f"+refs/heads/{ref}:refs/remotes/origin/{ref}")
        if c:
            raise Stop(f"git fetch origin {ref} failed: {out}")
    got = git(root, "rev-parse", f"refs/remotes/origin/{info['branch']}")[1]
    if got != info["head"]:
        raise Stop(f"{info['branch']} moved: gh says {info['head'][:9]}, origin holds {got[:9]}. Run again. Nothing was claimed.")
    tmp = os.path.realpath(tempfile.mkdtemp(prefix="merge-wt-"))  # /var is a symlink on macOS
    wt = os.path.join(tmp, "tree")
    c, out = git(root, "worktree", "add", "-q", "--detach", "--lock", "--reason", f"merge tool, pid {os.getpid()}", wt, info["head"])  # a locked tree survives the janitor sweep
    if c:
        shutil.rmtree(tmp, ignore_errors=True)
        raise Stop("cannot make the worktree: " + out)
    return tmp, wt

def drop_worktree(root, tmp, wt):
    git(root, "worktree", "unlock", wt)
    git(root, "worktree", "remove", "--force", wt)
    git(root, "worktree", "prune")
    shutil.rmtree(tmp, ignore_errors=True)

def ignore_checks(cfg):
    """merge.ignoreChecks -> {name: reason}. An entry without a name or a non-empty reason refuses the config."""
    out = {}
    for e in cfg.get("merge", {}).get("ignoreChecks", []):
        if not isinstance(e, dict) or not all(isinstance(e.get(k), str) and e[k].strip() for k in ("name", "reason")):
            raise Stop(f"merge.ignoreChecks entry {e!r} needs a name and a non-empty reason. Config refused.")
        out[e["name"]] = e["reason"]
    return out

def base_verdict(root, host, base):
    """host.base_state over the workflow files on origin/<base>. A failed read of them is unknown."""
    try:
        flows = base_workflows(root, f"origin/{base}")
    except (Stop, subprocess.TimeoutExpired, OSError) as e:
        return "unknown", " ".join(str(e).split())
    return host.base_state(base, flows)

def red_base(root, host, base, red_ok=""):
    """The red-main check (decision no-merge-onto-red-main): refuse while the base's latest completed run has a red job, or cannot be read.
    --base-red-ok "<reason>" is a reason flag, as --undo-check-unknown-ok is: the way out for the batch that carries the fix, or for an unknown read. It is logged."""
    verdict, detail = base_verdict(root, host, base)
    if verdict == "green":
        return
    what = f"{base}'s latest completed run is red: {detail}" if verdict == "red" else f"{base}'s runs are UNKNOWN, the read failed: {detail}"
    if red_ok.strip():
        say(f"merge: {what}. --base-red-ok, reason: {red_ok.strip()}")
        return
    raise Stop(f"{what}\nNo batch merges onto a red {base}. If this batch carries the fix, or the owner accepts the unknown, run again with the reason flag --base-red-ok \"<reason>\".")

def batch_refusal(host, n, base):
    """The batch brake (rule git-no-merge-during-batch-ci): -> the refusal while another ready PR on `base` has a workflow run or a required check pending,
    else None. A failed read raises Stop. No reason flag lifts it: a merge under a running batch moves the base that run tests."""
    blockers = host.batch_running(n, base)
    if not blockers:
        return None
    return (f"#{n} does not merge to {base} while another ready PR's CI runs: " + "; ".join(blockers) + ".\n"
            "Wait for that run to end. Its run's end, or its CI-done comment on a red run, wakes the session that watches that PR. Then run again.")

def preview(root, cfg, cfgrel, n, host, lock, info=None, unknown_ok=""):
    info = info or host.pr(n)
    refuse_bad_pr(info, draft_ok=True)  # a draft is previewed, so its silent undos show before it is marked ready
    if info["draft"]:
        say(f"merge: #{n} is a draft. This is a preview only; --confirm needs it ready.")
    base = info["base"]
    resumed = trailer = records = None
    tmp, wt = open_worktree(root, info, base)  # the same tree confirm checks
    try:
        try:
            undo_check(wt, f"origin/{base}", unknown_ok, info.get("body", ""))
            refuse_dropped_lane(wt, f"origin/{base}", info["head"], unknown_ok)
            current, stands = holds_base(wt, f"origin/{base}", info["head"])
            current = current and ("BEHIND: " if "does not hold" in current else "UNKNOWN: ") + current + " --confirm refuses it."
            current = current or stands and stands + ". The green run stands."
        except Dropped as e:  # one greppable line for a reader that scans the output for a verdict; the detail follows
            say("BLOCKED: " + " ".join(str(e).splitlines()[:-1]).replace("  ", " ").strip())
            raise
        if base == cfg["defaultBranch"]:  # ids are claimed only on the default branch
            sc = base_stamp_config(wt, tmp, cfgrel, f"origin/{base}")
            if sc:
                resumed = own_claim(wt, sc, f"origin/{base}")
                trailer = None if resumed else do_claim(wt, sc, f"origin/{base}")
            records = "rebuild docs/records.md" if rebuild_records(wt) else "current"  # after the claim, as confirm does
    finally:
        drop_worktree(root, tmp, wt)
    m = cfg.get("merge", {})
    held = lock.read(base)
    verdict, detail = base_verdict(root, host, base)  # the red-main check's read
    try:
        blockers = host.batch_running(n, base)
        batch = "; ".join(blockers) + ". --confirm refuses it." if blockers else "clear"
    except Stop as e:
        batch = "unknown (" + " ".join(str(e).split()) + "). --confirm refuses it."
    say(f"merge: PREVIEW for #{n} ({info['branch']} at {info['head'][:9]}). Nothing was pressed.",
        "  lock:   " + (holder_text(base, held, lock.now()) if held and held[1] > lock.now() else "free"),
        f"  head checks: {host.head_state(n)}",
        "  batch:  " + batch,
        f"  {base} run: {verdict}" + (f": {detail}. --confirm refuses it." if verdict != "green" else ""),
        "  base:   " + (current or f"holds {base}'s tip"),
        "  claim:  " + (f"already claimed ({resumed}); a run resumes at the wait" if resumed else trailer or "nothing to claim"),
        *([f"  records: {records}"] if records else []),
        *([] if base == cfg["defaultBranch"] else [f"  ids:    stay pending: {base} is not the default branch ({cfg['defaultBranch']}); they are claimed when it merges there."]),
        f"  then:   push HEAD:{info['branch']}, wait for the checks, PUT pulls/<n>/merge with merge_method={m.get('method', '?')} and the head sha as the guard,",
        f"          move local {base}, run {len(m.get('afterMerge', []))} afterMerge command(s)" + (", delete the branch and the batch's lane branches." if m.get("deleteBranch") else "."))

WAITS = 3  # the host.wait_checks calls in confirm, none in a loop: the head, the claim, the merge commit that heals the page

def confirm(root, cfg, cfgrel, n, host, lock, unknown_ok="", session="", info=None, red_ok=""):
    m = cfg.get("merge", {})
    info = info or host.pr(n)  # main read it once already, and the config came from that base. A read: acquire never waits, so the head cannot move before the lock is ours
    base = info["base"]  # the PR's own base; read again under the lock
    base_ref = f"origin/{base}"
    lock.holder = {"pr": n, "branch": info["branch"], "session": session}
    token = lock.acquire(base, (WAITS * m["deadlineMinutes"] + 10) * 60)  # each wait at most once, ten minutes spare
    host.before_wait = getattr(lock, "extend_for", None)  # a rate wait extends the lock first (standing-merge-grant); the TTL spare is for the checks waits
    tmp = wt = claim_sha = None
    try:
        info = host.pr(n)
        refuse_bad_pr(info)
        if info["base"] != base:
            raise Stop(f"the base of #{n} changed from {base} to {info['base']} while the lock was taken. Nothing was claimed or pushed.")
        host.required_names()  # an empty or unreadable list stops here, before anything is pushed
        red_base(root, host, base, red_ok)
        busy = batch_refusal(host, n, base)
        if busy:
            raise Stop(busy + " Nothing was claimed or pushed.")
        branch = info["branch"]
        tmp, wt = open_worktree(root, info, base)
        undo_check(wt, base_ref, unknown_ok, info.get("body", ""))
        refuse_dropped_lane(wt, base_ref, info["head"], unknown_ok)
        stale, stands = holds_base(wt, base_ref, info["head"], host.before_wait)
        if stale:
            raise Stop(stale + " This run claimed nothing.")
        if stands:
            say(f"merge: {stands}. The green run stands.")
        stamp_cfg = base_stamp_config(wt, tmp, cfgrel, base_ref)  # None: no config or no kinds, so no claim and no stamp
        resumed = own_claim(wt, stamp_cfg, base_ref) if base == cfg["defaultBranch"] else None
        claimed, trailer = bool(resumed), None  # claimed: the pushed commit holds a Record-claim
        if base != cfg["defaultBranch"]:
            if head_claim(wt):  # an old claim would put real ids into a branch that is not the default
                raise Stop(f"{info['head'][:7]} on {branch} holds a Record-claim, and {base} is not the default branch. Revert that commit and run again.")
            say(f"merge: {base} is not the default branch. Ids stay pending; nothing to claim.")
        else:
            if resumed:
                claim_sha = info["head"]
                say(f"merge: resumed. {branch} already holds the claim {resumed}.")
            else:
                trailer = do_claim(wt, stamp_cfg, base_ref) if stamp_cfg else None
                claimed = bool(trailer)
            rebuilt = rebuild_records(wt)  # after the claim, whatever the stamp config holds: a stale page heals at the next merge, on a resumed head too
            if trailer or rebuilt:
                # check first, then claim: a claim push cancels the head's own run and would hide a red already there
                try:
                    ok, why = host.wait_checks(n, info["head"], m["deadlineMinutes"])
                except NetStop:
                    raise
                except Stop as e:
                    ok, why = False, str(e)
                if not ok:
                    raise Stop("the head's own checks are not green, so nothing was claimed or pushed: " + why)
                claim_sha = commit_claim(wt, trailer)
                push_branch(wt, branch)
                say(f"merge: {trailer or 'the records page'} pushed to {branch} at {claim_sha[:9]}.")
            elif not resumed:
                say("merge: nothing to claim.")
        sha = claim_sha or info["head"]

        def fail(why):
            if claim_sha:
                if not os.path.exists(os.path.join(wt, ".git")):  # the tree is gone (swept or cleaned): the revert needs one
                    shutil.rmtree(tmp, ignore_errors=True)
                    git(root, "worktree", "unlock", wt)
                    git(root, "worktree", "prune")
                    os.makedirs(tmp)
                    c, out = git(root, "worktree", "add", "-q", "--detach", "--lock", "--reason", f"merge tool, pid {os.getpid()}", wt, claim_sha)
                    if c:
                        raise Stop(f"{why}\nmerge: the worktree is gone and cannot be rebuilt ({out}). The claim {claim_sha[:9]} stays on {branch}. Run again to resume, or revert it by hand.")
                revert_claim(root, wt, branch, claim_sha)
            raise Stop(why)

        try:  # after the push only a Stop may leave: any other error reverts the claim first
            try:
                ok, why = host.wait_checks(n, sha, m["deadlineMinutes"], info["head"] if claim_sha else None)
            except NetStop:  # a network error is not a refusal: the claim stays
                raise
            except Stop as e:  # a read that fails in the wait still reverts the claim
                ok, why = False, str(e)
            if not ok:
                fail(why)
            def prove(stop):
                """Read the branch against the base tip fetched now. -> the records proof, or None off the default base.
                stop(why) refuses. It waits on no check, so WAITS stays the bound."""
                c, out, _ = retry_net(lambda: git(root, "fetch", "-q", "origin", f"+refs/heads/{base}:refs/remotes/origin/{base}"), getattr(host, "pause", time.sleep), what=f"the fetch of {base}")
                if is_net(c, out):  # a network error is not a refusal: the claim stays
                    raise NetStop(f"network error on the fetch of origin {base}, still failing after {NET_RETRIES} retries. The claim stays on {branch}. Run again to resume.\n{out}")
                if c:  # never check against a stale base tip
                    stop(f"cannot fetch origin {base}, so the claim cannot be proved fresh:\n" + out)
                try:  # main may have moved during the wait: read the branch against the tip fetched just now
                    undo_check(wt, base_ref, unknown_ok, info.get("body", ""))
                except Stop as e:
                    stop(str(e))
                if not os.path.exists(os.path.join(wt, ".git")):
                    stop("the worktree is gone, so the claim cannot be proved fresh.")
                try:  # the config is the base tip's, read just after the fetch
                    stamp_cfg = base_stamp_config(wt, tmp, cfgrel, base_ref)
                except Stop as e:
                    stop(str(e))
                if claimed and not stamp_cfg:
                    stop(f"base lost its config: {cfgrel} on {base_ref} no longer holds stamp kinds, so the claim cannot be proved fresh.")
                c, out = node_stamp(wt, stamp_cfg, "check", base_ref) if stamp_cfg else (0, "")  # each claimed number must still be free on the base tip
                if c or "UNKNOWN:" in out:
                    stop(str(stamp_stop("the base moved and the claim is stale, or the check could not read the base", out)))
                if base != cfg["defaultBranch"]:
                    proof = None
                else:
                    try:  # the base moved with a record and no rebuild: the merge result would hold a stale page
                        proof = records_proof(wt, base_ref)
                    except Stop as e:
                        stop(str(e))
                if proof == "healed":  # the merge commit holds the base tip, and its own checks wait next
                    return proof
                if proof == "stale":
                    stop(f"the records page is stale for the merge result: {base_ref} gained a record after the rebuild (a push that did not use the tool). Nothing was merged. Run again.")
                stale, stands = holds_base(wt, base_ref, sha, host.before_wait)  # the base moved during the wait: the green run did not test it
                if stale:
                    stop(stale)
                if stands:
                    say(f"merge: {stands}. The green run stands.")
                return proof

            if prove(fail) == "healed":  # the page conflicted with the base: the merge commit carries a rebuilt page, so it is pushed and its checks wait
                merged = git(wt, "rev-parse", "HEAD")[1]
                try:
                    push_branch(wt, branch)
                except Stop as e:
                    fail(str(e))
                say(f"merge: {base_ref} merged into {branch} with the records page rebuilt, pushed at {merged[:9]}.")
                try:
                    ok, why = host.wait_checks(n, merged, m["deadlineMinutes"], sha)
                except NetStop:
                    raise
                except Stop as e:
                    ok, why = False, str(e)

                def keep(why):  # a revert of a merge commit would undo the base's own work in the branch, so the commit stays
                    raise Stop(f"{why}\nmerge: the merge commit {merged[:9]} stays on {branch}. Fix the cause and run again.")
                if not ok:
                    keep(f"the checks on the merge commit {merged[:9]} are not green.\n{why}")
                sha = merged
                if prove(keep) == "healed":  # the base moved during that wait and the page conflicts again: a fourth wait would outrun the lock
                    keep(f"{base_ref} moved during the wait on the merge commit, and the records page conflicts again. Nothing was merged.")
            try:  # the PR's own paths. --no-renames: a moved file names both paths. -z: git does not quote a non-ASCII name. Any failure of this read leaves the list unknown and never holds the merge
                c, names = git(wt, "diff", "--name-only", "--no-renames", "-z", f"{base_ref}...{sha}")
            except (subprocess.TimeoutExpired, OSError):
                c, names = 1, ""
            rule_files = [x for x in names.split("\0") if x.lower() in RULE_FILES or x.lower().startswith(RULE_PREFIX)] if c == 0 else None
            lanes, dropped = lane_tips(wt, base_ref, sha) if m.get("deleteBranch") else ([], set())  # read before the merge: after it the lane tips are on the base
            try:  # again right before the PUT: a batch that went ready during the waits is refused, and its claim reverted as for a refused PUT
                busy = batch_refusal(host, n, base)
            except NetStop:  # a network error is not a refusal: the claim stays
                raise
            except Stop as e:
                busy = str(e)
            if busy:
                fail(busy)
            commit, msg = host.merge(n, m["method"], sha)
            if not commit:
                fail("the merge was refused:\n" + msg)
        except Stop:
            raise
        except Exception as e:
            fail(f"unexpected {type(e).__name__} after the claim was pushed: {e}")
        say(f"merge: #{n} merged as {commit[:9]}.")
        if rule_files is None:
            say(f"merge: #{n} the rule-file check could not run: git diff failed. Read the PR's files yourself.")
        for x in rule_files or []:
            say(f"merge: #{n} changes {x}, a rule file every session loads.")
        ok = True
        try:
            ff_main(root, base, commit)
        except Stop as e:  # the merge landed: report, go on, exit non-zero at the end
            say(f"merge: the merge landed. The local {base} did not move: {e}")
            ok = False
        ok = after_merge(root, m.get("afterMerge", [])) and ok
        if m.get("deleteBranch"):
            cut_branch(root, branch, sha)
            if lanes:
                cut_lanes(root, lanes, commit, host, base, {cfg["defaultBranch"], base, branch}, m.get("keepBranches", []), dropped)
        return 0 if ok else 1  # the merge landed either way; a failed ff or afterMerge exits non-zero
    finally:
        if wt:
            drop_worktree(root, tmp, wt)
        lock.release(base, token)

def default_lock(root):
    """A Claude Code cloud session (CLAUDE_CODE_REMOTE=true) gets GitLock: its proxy refuses the REST writes GhLock makes (HTTP 403 on
    POST git/commits and git/refs, PATCH and DELETE git/refs; measured c53) and passes a push to refs/heads. Elsewhere GhLock, as before."""
    return GitLock(root) if os.environ.get("CLAUDE_CODE_REMOTE") == "true" else GhLock()

MERGE_ROLES = {"coordinator", "batch-runner"}  # the tiers that may run `merge <pr> --confirm` in a cloud session

def role_path():
    return pathlib.Path(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")) / "state" / "merge-role.json"

def read_merge_role():
    """This session's recorded merge role, or None: no session id, no file, unreadable or malformed, another session's, or a tier outside MERGE_ROLES.
    Every failure is None, so the gate fails closed. An absent id never equals an absent record."""
    sid = os.environ.get("CLAUDE_CODE_REMOTE_SESSION_ID")
    if not sid:
        return None
    try:
        data = json.loads(role_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):  # UnicodeDecodeError and JSONDecodeError are ValueErrors
        return None
    if not isinstance(data, dict) or data.get("session") != sid:
        return None
    role = data.get("role")
    return role if isinstance(role, str) and role in MERGE_ROLES else None  # a list is unhashable: test the type first

def write_merge_role(tier):
    """Record `tier` as this cloud session's merge role. Refuses outside the cloud, with no session id, or for a tier outside MERGE_ROLES; nothing is written then."""
    sid = os.environ.get("CLAUDE_CODE_REMOTE_SESSION_ID")
    if os.environ.get("CLAUDE_CODE_REMOTE") != "true":
        raise Stop("--role records a merge role in a cloud session only.")
    if not sid:
        raise Stop("--role needs CLAUDE_CODE_REMOTE_SESSION_ID, and it is not set.")
    if tier not in MERGE_ROLES:
        raise Stop("this session's tier may not record a merge role. Hand the pull request number and its head to the batch runner.")  # names no valid tier: a lane must not learn which to claim
    path = role_path()
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")  # replace, so a reader never sees half a file
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps({"session": sid, "role": tier}), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as e:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise Stop(f"cannot write the merge role to {path}: {e}.")

def main(argv, host=None, lock=None):
    p = argparse.ArgumentParser(prog="merge", description=__doc__.split("\n\n")[0])
    p.add_argument("pr", nargs="?", type=int)
    p.add_argument("--confirm", action="store_true")
    p.add_argument("--role", metavar="TIER", help="cloud only: record this session's merge role (coordinator or batch-runner)")
    p.add_argument("--unlock", nargs="?", const=True, metavar="BRANCH")
    p.add_argument("--undo-check-unknown-ok", default="", metavar="REASON", help="go on when the silent-undo check cannot read the history; logged")
    p.add_argument("--base-red-ok", default="", metavar="REASON", help="go on when the base's latest run is red or unreadable (the batch carries the fix); logged")
    p.add_argument("--session", default="", metavar="NAME", help="your session name; the lock shows it to waiting runs")
    p.add_argument("--config", default=".github/stamp.json")
    a = p.parse_args(argv)
    UNDO_MEMO.clear()  # one merge run owns the memo: equal shas in another run (or test) must not reuse its verdict
    if a.role is not None:
        if a.pr is not None or a.confirm or a.unlock is not None:
            p.error("--role stands alone")
    elif (a.unlock is None) == (a.pr is None) or (a.unlock is not None and a.confirm):
        p.error("give a pull request number, --unlock, or --role TIER")
    try:
        if a.role is not None:
            write_merge_role(a.role)
            say(f"merge: merge role {a.role} recorded for this session.")
            return 0
        if a.confirm and os.environ.get("CLAUDE_CODE_REMOTE") == "true" and not read_merge_role():  # before any host read or lock
            raise Stop("this session may not merge. Hand the pull request number and its head to the batch runner.")
        c, root = sh(["git", "rev-parse", "--show-toplevel"])
        if c:
            raise Stop("not in a git checkout")
        lock = lock or default_lock(root)
        if a.unlock is not None:
            b = a.unlock
            if b is True:
                c, head = git(root, "rev-parse", "--abbrev-ref", "origin/HEAD")
                b = head.split("/", 1)[1] if not c and "/" in head else host_default_branch(root)
            say(f"merge: lock on {b} removed." if lock.unlock(b) else f"merge: no lock on {b}; nothing to remove.")
            return 0
        h = host or Host()
        info = h.pr(a.pr)  # the PR's base decides which config; confirm and preview reuse this read
        refuse_bad_pr(info, draft_ok=not a.confirm)  # a closed PR, or a draft under --confirm, stops before the config notice
        cfg = load_config(root, info["base"], a.config)
        if a.confirm and os.environ.get("CLAUDE_CODE_REMOTE") == "true" and cfg["merge"].get("standingGrant", True) is False:
            raise Stop("The owner's standing merge grant is off for this repo, so ask the owner to merge this PR.")
        ignore = ignore_checks(cfg)
        if not host:
            h.required, h.ignore = cfg["merge"]["requiredChecks"], ignore
            h.refuse_pinned_mismatch()
        if a.confirm:
            with release_on_signals():
                return confirm(root, cfg, a.config, a.pr, h, lock, a.undo_check_unknown_ok, a.session, info, a.base_red_ok) or 0
        return (preview(root, cfg, a.config, a.pr, h, lock, info, a.undo_check_unknown_ok)) or 0
    except Stop as e:
        print(f"merge: {e} No override lifts this refusal, because this tool runs after the guard.", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
