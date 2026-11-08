"""The git mailbox: one home for the git plumbing, the addresses and the turn-start read (decision session-messages, page item 153).

Messages are files `mail/<addr>/<id>.md` on refs/heads/mail of MAILBOX_REPO. bin/mail sends, reads and takes; local_time.py
calls turn_start_lines on each UserPromptSubmit. The cache is a bare clone (MAILBOX_CACHE, else ~/.claude/mail.git) and only
plumbing touches it, never a working tree. No log is written.

Cost of a turn start: one git process (ls-remote) when the ref has not moved, and no file written. When it moved: at most four
(ls-remote, fetch, grep, log), and files written only in the cache. The four bounds sum to 10 s, so a hung remote costs the
prompt at most 10 s. A failure prints "mail unknown: <reason>", never "no mail".
"""
import hashlib
import json
import os
import re
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
NOT_FF = "[rejected]"  # local fast-forward refusal; a hook or ACL refusal says "[remote rejected]" and is not retried


class MailError(Exception):
    pass


def safe(value):
    """True for a path-safe address or id: no empty part, no `.` or `..` part."""
    return bool(SAFE.match(value)) and not any(part in (".", "..") for part in value.split("/"))


def git(args, env, cache=None, timeout=TRANSFER_BOUND, input_text=None):
    """One git process. Returns (returncode, stdout, stderr). Raises MailError on a timeout or a missing git.
    No prompt can open: a hook has no terminal to answer it. A ssh command or GIT_SSH program the caller set is kept;
    otherwise ssh runs in batch mode with a 3 s connect bound, which overrides core.sshCommand. The step's timeout kills
    git but not its ssh child, so the connect bound stops a connecting ssh from outliving the step."""
    run_env = dict(env, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    if not env.get("GIT_SSH_COMMAND") and not env.get("GIT_SSH"):
        run_env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes -o ConnectTimeout=3"
    prefix = ["git", "-c", "commit.gpgsign=false"] + (["--git-dir", cache] if cache else [])
    try:
        done = _nowindow.run(prefix + args, env=run_env, input=input_text, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        raise MailError("timeout")
    except OSError as error:
        raise MailError("git: %s" % error)
    return done.returncode, done.stdout, done.stderr


def reason(stderr):
    text = stderr or ""
    if re.search(r"Authentication failed|could not read (Username|Password)|Permission denied", text):
        return "auth"
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return re.sub(r"^(fatal|error): ", "", lines[-1])[:120] if lines else "git failed"


def must(args, env, cache=None, timeout=TRANSFER_BOUND, input_text=None):
    code, out, err = git(args, env, cache, timeout, input_text)
    if code:
        raise MailError(reason(err))
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


def remote_tip(env):
    """The remote mail ref's sha, or None when the store has no mail ref yet."""
    out = must(["ls-remote", env["MAILBOX_REPO"], REF], env, timeout=REMOTE_BOUND)
    return out.split()[0] if out.strip() else None


def fetch(env, timeout=TRANSFER_BOUND):
    ensure_cache(cache_path(env))
    must(["fetch", "--quiet", "--no-tags", env["MAILBOX_REPO"], "+%s:%s" % (REF, REF)], env, cache_path(env), timeout)


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
    index =os.path.join(cache, "mail.index.%d" % os.getpid())
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
        return must(["commit-tree", tree, "-m", message] + (["-p", tip] if tip else []), env, cache).strip()
    finally:
        if os.path.exists(index):
            os.remove(index)


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


def open_messages(env, tip, addrs):
    """[{id, addr, from, kind, re, sent}] for each file directly under mail/<addr>/ at `tip`. Two git processes. A repo
    address is a path prefix of its session addresses, so grep's hits are filtered to the folders named."""
    cache = cache_path(env)
    paths = ["mail/%s/" % addr for addr in addrs]
    code, out, err = git(["grep", "-I", "--no-color", "-e", "^Msg ", tip, "--"] + paths, env, cache, GREP_BOUND)
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
                         "--"] + paths, env, cache, LOG_BOUND).splitlines()
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


def turn_start_lines(payload, env):
    """The lines a UserPromptSubmit hook prints: one per open message, or one "mail unknown: <reason>". Nothing when
    MAILBOX_REPO is unset or the session has no address."""
    if not env.get("MAILBOX_REPO"):
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
