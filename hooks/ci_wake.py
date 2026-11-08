#!/usr/bin/env python3
"""After `gh pr ready <N>`, waits for CI on that PR head. Then wakes the session with one line: green, red, cancelled or unknown, with the names of failing jobs.

PostToolUse hook for the Bash and PowerShell tools, registered with `asyncRewake: true`. Only
`gh pr ready <N>` starts a watch, and each one in a command gets its own, in this one process.
A push starts none. Neither does MCP `update_pull_request`, the cloud's ready route: the hook's matcher
sees only Bash and PowerShell, and `gh pr ready` gets 403 in cloud (route pr-ready-gh-cli-cloud; debt ci-wake-misses-mcp-ready). Per PR it reads the head once. It lists that head's runs until a run that
ran has ended (a skipped draft run is no run), waits on it, and prints one line:

    CI <green|red|cancelled> on <sha7>: <failing job names>
    CI unknown on <sha7 or PR>: <reason>        (also "still running" at the deadline)

Then it exits 2 once, which wakes the session. It prints nothing and exits 0 when no watch starts,
when the repo has no active workflow, or when another watcher already holds every PR it would watch. Any error exits 2 with an unknown
line, never 1. It lists runs, and reads a run's status, 30 s apart for the first 4 minutes, then at
gaps that grow to 120 s (`pauses`). It never loops on a red run.

Seams: CI_WAKE_DEADLINE, the watch budget in seconds (default DEFAULT_DEADLINE, under the hook
timeout in settings.json). CI_WAKE_LOCK_DIR, the folder of the per-PR lock files.
The cancelled-twin rule is merge.py's `Host.judge_runs`, loaded through guard_merge.merge_module.

The Stop-side read (`head_state`, for lint/report_guard.py after a push): one read of a pushed head's CI state,
in a Stop hook that is already running. It starts no watch, timer or process of its own. Cost per head: at most 2
gh processes (the open PR of the branch, then the head's runs), plus 1 more when the run list is empty (the
workflow list), plus 1 local process to name a short head on main. The path-filter read, paid only when the run list
is empty, adds 2 git processes plus 1 per workflow file read, and stops at the first workflow that runs. A PR read that
lags the push adds 1 git process, to read the pushed head direct.
Budget: HEAD_READ seconds for each read, HEAD_TOTAL for all of a Stop's reads, under the Stop hook timeout in
settings.json. The seam is `Budget(total, per_read, clock)`: a test passes a clock it controls, so the budget is
proved without real time.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# The sibling modules (guard_core, guard_env, guard_merge, _nowindow) load inside main() and gh(), so a
# failed import ends in an unknown line, never a traceback and exit 1.

DEFAULT_DEADLINE = 3300   # seconds; the hook timeout in settings.json is 3600
STATUS_PAUSE = 30         # seconds between two reads in the first BACKOFF_FLAT seconds, and before a retry
BACKOFF_FLAT = 240        # seconds the gap stays STATUS_PAUSE
BACKOFF_CAP = 120         # seconds, the longest gap
READ_TIMEOUT = 60         # seconds for each gh read
HEAD_READ = 8             # seconds for each read of head_state
HEAD_TOTAL = 20           # seconds for every read of one Stop, under the Stop hook's 35 s timeout
MAIN_BRANCHES = ("main", "master")   # a push here has no PR to read: the head's runs are read direct
RUN_FIELDS = "databaseId,name,status,conclusion,workflowName,headSha,event"
GOOD = ("success", "skipped", "neutral")
REPO_FLAGS = ("-R", "--repo")
PR_URL = re.compile(r"^https?://([^/]+)/([^/]+/[^/]+)/pull/(\d+)")
# A word-internal apostrophe (don't) opens no quote. Masked here, so split_segments does not read it as one.
APOSTROPHE = re.compile(r"(?<=[A-Za-z])'(?=[A-Za-z])")
HELD = []   # open lock files, kept until the process ends: the OS drops the locks then, kill included


class Unknown(Exception):
    """A read that could not run. The message is the reason."""


class NoPR(Exception):
    """The number names no pull request: no watch, not an unknown."""


def emit(lines):
    if not lines:
        return 0
    try:
        sys.stderr.buffer.write("".join(" ".join(x.split())[:300] + "\n" for x in lines).encode("utf-8", "replace"))
        sys.stderr.buffer.flush()
    except Exception:
        pass
    return 2


def gh(args, cwd, timeout=READ_TIMEOUT):
    """-> (rc, stdout, stderr). gh is found with shutil.which: a list-form call of a bare "gh"
    misses a .cmd launcher on Windows. A timeout kills gh and never waits on its pipes."""
    try:
        import _nowindow  # the one home of a no-window child start
    except ImportError:  # a hook never dies for a missing helper (it lands a moment after the hook in an install)
        _nowindow = subprocess
    exe = shutil.which("gh")
    if exe is None:
        raise Unknown("gh is not on PATH")
    try:
        p = _nowindow.Popen([exe, *args], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, cwd=cwd)
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        raise Unknown("gh %s timed out" % " ".join(args[:2]))
    except OSError as e:
        raise Unknown("gh %s failed: %s" % (" ".join(args[:2]), type(e).__name__))
    return p.returncode, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


def gh_json(args, cwd, gone="", timeout=READ_TIMEOUT):
    """-> the JSON gh prints. gone: text in a failed read's output that means the PR does not exist (NoPR)."""
    rc, out, err = gh(args, cwd, timeout)
    if rc != 0:
        if gone and gone in (out + err).lower():
            raise NoPR()
        raise Unknown("gh %s exited %d: %s" % (" ".join(args[:2]), rc, (err or out).strip()))
    try:
        return json.loads(out)
    except ValueError:
        raise Unknown("gh %s printed non-JSON" % " ".join(args[:2]))


def pauses():
    """The one schedule of the watch's reads and lists: STATUS_PAUSE gaps through BACKOFF_FLAT seconds,
    then each gap grows by STATUS_PAUSE up to BACKOFF_CAP, and never shrinks."""
    for _ in range(BACKOFF_FLAT // STATUS_PAUSE):
        yield STATUS_PAUSE
    gap = STATUS_PAUSE
    while True:
        gap = min(BACKOFF_CAP, gap + STATUS_PAUSE)
        yield gap


def watch_run(run_id, cwd, deadline, repo=""):
    """Read `gh run view <id> --json status` until the status is `completed` or the deadline
    passes. Reads follow `pauses`, and the last pause ends at the deadline. No `gh run watch` (decision ci-wait-reads-run-status). A failed or non-JSON read
    gets one retry after the pause (never past the deadline); a second failure raises Unknown."""
    def read():
        args = ["run", "view", str(run_id), *(["-R", repo] if repo else []), "--json", "status"]
        try:
            return gh_json(args, cwd)
        except Unknown:
            time.sleep(max(0, min(STATUS_PAUSE, deadline - time.monotonic())))
            if deadline - time.monotonic() <= 0:
                raise
            return gh_json(args, cwd)
    gaps = pauses()
    while deadline - time.monotonic() > 0:  # at or past the deadline: no read, no pause
        if read().get("status") == "completed":
            return
        left = deadline - time.monotonic()
        gap = next(gaps)
        if left <= gap:  # the last pause is clamped to the deadline, and the wait ends there
            time.sleep(max(0, left))
            return
        time.sleep(gap)


def ready_call(rest, env_repo=""):
    """-> (selector, repo) for the args of a `gh pr ready` call, else None. The repo is the -R or
    --repo value (`-R o/r`, `-Ro/r`, `-R=o/r`, `--repo o/r`, `--repo=o/r`), else env_repo (GH_REPO)."""
    if rest[:2] != ["pr", "ready"] or any(a in ("--undo", "-h", "--help") for a in rest):
        return None
    pos, repo, i = [], env_repo, 2
    while i < len(rest):
        a = rest[i]
        if a in REPO_FLAGS and i + 1 < len(rest):
            repo, i = rest[i + 1], i + 1
        elif a.startswith("--repo="):
            repo = a[7:]
        elif a.startswith("-R") and not a.startswith("--"):
            repo = a[2:].lstrip("=")
        elif not a.startswith("-"):
            pos.append(a)
        i += 1
    return (pos[0] if pos else ""), repo


def triggers(command, powershell):
    """-> [(selector, repo)], one per `gh pr ready` in the command. Reads the text only. A heredoc
    body, quoted text and text after `#` is no command (split_segments drops comments and keeps
    quotes whole); a lone apostrophe in a word opens no quote. A lone `&` ends a command too
    (guard_env's quote-aware split); the `&` of `2>&1` leaves the call whole."""
    import guard_core
    from guard_core import resolve_command, segment_tokens
    from guard_env import _ampersand_split
    from guard_merge import gh_call_of
    guard_core.POWERSHELL_CALL[0] = powershell
    text = APOSTROPHE.sub("\x01", guard_core.strip_heredoc_bodies(command))
    found = []
    for segment in (p for s in guard_core.split_segments(text) for p in _ampersand_split(s)):
        rest = gh_call_of(segment)
        call = None
        if rest is not None:
            tokens = segment_tokens(segment) or []
            env = [t[8:] for t in tokens[:resolve_command(tokens) or 0] if t.startswith("GH_REPO=")]
            call = ready_call(rest, env[-1] if env else "")
        if call:
            found.append(call)
    return found


def lock_pr(pr, lock_dir):
    """Take the one lock of this PR for the life of the process. False when another watcher holds it."""
    key = re.sub(r"[^A-Za-z0-9._-]+", "_", str(pr.get("url") or pr["number"]))
    os.makedirs(lock_dir, exist_ok=True)
    fd = os.open(os.path.join(lock_dir, key + ".lock"), os.O_CREAT | os.O_RDWR)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return False
    HELD.append(fd)
    return True


def wait_for(sha, cwd, deadline, repo=""):
    """List the head's runs, watch each one (not a cancelled twin), then read each with its jobs.
    A run that ends skipped is no run: the draft PR's run skips, and the run of `gh pr ready`
    comes after it. While no run that ran is judged, list again, `pauses` apart; the last
    pause ends at the deadline, with one list there. Once a run that ran is judged, return it:
    later runs are not waited on (debt ci-wake-lists-runs-once)."""
    extra = ["-R", repo] if repo else []
    list_args = ["run", "list", "--commit", sha, "--limit", "100", *extra, "--json", RUN_FIELDS]
    gaps = pauses()
    while True:
        runs = [r for r in gh_json(list_args, cwd) if r["conclusion"] != "skipped"]
        live = {r["name"] for r in runs if r["conclusion"] != "cancelled"}
        for r in runs:
            if r["conclusion"] == "cancelled" and r["name"] in live:
                continue   # a cancelled twin: judge_runs reads the run that ran
            watch_run(r["databaseId"], cwd, deadline, repo)
        viewed = [gh_json(["run", "view", str(r["databaseId"]), *extra, "--json", "databaseId,name,status,conclusion,jobs"], cwd)
                  for r in runs]
        viewed = [r for r in viewed if r.get("conclusion") != "skipped"]   # it ended skipped: no run
        if viewed:
            return viewed
        left = deadline - time.monotonic()
        if left <= 0:
            raise Unknown("no run yet")
        time.sleep(min(next(gaps), left))


def verdict(sha, runs):
    from guard_merge import merge_module
    merge = merge_module()
    if merge is None:
        raise Unknown("the merge tool (judge_runs) could not be loaded")
    red, pending = merge.Host.judge_runs(runs)
    if pending:
        raise Unknown("still running: " + ", ".join(pending))
    if not red:
        return "CI green on %s: no failing jobs" % sha[:7]
    names, cancelled = [], True
    for text in red:
        run = next((r for r in runs if text.startswith("workflow %s: " % r["name"])), None)
        if run is None:
            names.append(text)
            cancelled = False
            continue
        cancelled = cancelled and run["conclusion"] == "cancelled"
        jobs = [j["name"] for j in run.get("jobs") or [] if j.get("conclusion") not in GOOD]
        names.extend(jobs or ["workflow " + run["name"]])
    return "CI %s on %s: %s" % ("cancelled" if cancelled else "red", sha[:7], ", ".join(dict.fromkeys(names)))


def no_workflows(cwd, repo, timeout=READ_TIMEOUT):
    """True only when `gh workflow list` reads cleanly and shows no active workflow: no CI, so no
    watch. A failed or non-JSON read is unknown, not "no workflows" (the watch runs)."""
    try:
        return gh_json(["workflow", "list", *(["-R", repo] if repo else []), "--json", "id"], cwd,
                       timeout=timeout) == []
    except (Unknown, NoPR):
        return False


def pr_fields(p):
    """A REST pull request as the dict the watch reads: number, isDraft, headRefName, headRefOid, state
    (OPEN, CLOSED, MERGED) and url. The list endpoint has `merged_at` only, so either marks a merge."""
    return {"number": p["number"], "isDraft": bool(p.get("draft")), "headRefName": p["head"]["ref"],
            "headRefOid": p["head"]["sha"], "url": p["html_url"],
            "state": "MERGED" if p.get("merged") or p.get("merged_at") else p["state"].upper()}


def current_branch(cwd, timeout=READ_TIMEOUT):
    """The folder's branch, for `gh pr ready` with no selector and for a push of `HEAD` (lint/report_guard.py, which
    passes a timeout from its Budget). A detached HEAD names none."""
    try:
        import _nowindow
    except ImportError:
        _nowindow = subprocess
    exe = shutil.which("git")  # a bare "git" misses a .cmd launcher on Windows, as for gh
    if exe is None:
        raise Unknown("git branch read failed: git is not on PATH")
    try:
        p = _nowindow.run([exe, "symbolic-ref", "--short", "-q", "HEAD"], cwd=cwd, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Unknown("git branch read failed: %s" % type(e).__name__)
    if p.returncode != 0 or not p.stdout.strip():
        raise Unknown("no branch is checked out")
    return p.stdout.strip()


def read_pr(selector, repo, cwd, timeout=READ_TIMEOUT):
    """The PR a `gh pr ready` selector names, by REST: `gh pr view` is GraphQL, which the cloud proxy (route
    graphql-gh-api-cloud) refuses. selector: a number, a PR url, a branch, or "" for the folder's branch. repo is
    [HOST/]OWNER/REPO, else gh fills {owner}/{repo} from the folder. NoPR when none is found."""
    m = PR_URL.match(selector)
    if m:
        repo, selector = repo_of_url(selector), m.group(3)
    parts = repo.split("/") if repo else []
    host, slug = (parts[0], "/".join(parts[1:])) if len(parts) == 3 else ("", repo or "{owner}/{repo}")
    tail = ["--hostname", host] if host else []
    base = "repos/%s/pulls" % slug
    if selector.isdigit():
        return pr_fields(gh_json(["api", base + "/" + selector, *tail], cwd, gone="http 404", timeout=timeout))
    head = selector or current_branch(cwd)
    if ":" not in head:
        head = slug.split("/")[0] + ":" + head
    # Fields, not a query string: a `&` in an argument is a command separator to cmd.exe behind a .cmd
    # launcher. -F fills a {owner} placeholder inside its value; -f does not.
    found = gh_json(["api", "-X", "GET", base, "-F", "head=" + head, "-f", "state=open", *tail], cwd, timeout=timeout)
    if not found:
        raise NoPR()
    return pr_fields(found[0])


def repo_of_url(url):
    """The `[HOST/]OWNER/REPO` of a pull request url, for -R; "" when the url names none."""
    m = PR_URL.match(url or "")
    return "" if m is None else m.group(2) if m.group(1) == "github.com" else m.group(1) + "/" + m.group(2)


class Budget:
    """The time one Stop may spend on gh reads: `per_read` seconds for each, `total` for all, counted on `clock`
    (default time.monotonic). A test passes a clock it moves by hand. `next_timeout` is the timeout of the next
    read; it raises Unknown once the total is spent, so a spent budget is an unknown read, never green."""

    def __init__(self, total=HEAD_TOTAL, per_read=HEAD_READ, clock=time.monotonic):
        self.total, self.per_read, self.clock = total, per_read, clock
        self.end = clock() + total

    def next_timeout(self):
        left = self.end - self.clock()
        if left <= 0:
            raise Unknown("the %g s read budget is spent" % self.total)
        return min(self.per_read, left)


def git_out(args, cwd, timeout, what):
    """-> (returncode, stdout) of one local git read in the folder, the one home of the Stop-side git reads. Not
    git_reads._git: that one has a fixed 10 s timeout and returns None on failure, and these reads need the Budget's
    timeout and a raised Unknown. A raised Unknown when the read itself failed (the tool is missing, timed out or could not start); `what` names the
    read in that message."""
    try:
        import _nowindow
    except ImportError:
        _nowindow = subprocess
    exe = shutil.which("git")
    if exe is None:
        raise Unknown("git read of %s failed: git is not on PATH" % what)
    try:
        p = _nowindow.run([exe, *args], cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                          timeout=timeout)
    except subprocess.TimeoutExpired:
        raise Unknown("git read of %s timed out" % what)
    except OSError as e:
        raise Unknown("git read of %s failed: %s" % (what, type(e).__name__))
    return p.returncode, p.stdout


def commit_read(ref, cwd, timeout=HEAD_READ):
    """The full commit hash `ref` names in the folder, "" when the read ran and no ref names a commit, and a raised
    Unknown when the read itself failed (the tool is missing, timed out or could not start)."""
    code, out = git_out(["rev-parse", "--verify", "-q", ref + "^{commit}"], cwd, timeout, ref)
    out = out.strip()
    return out if code == 0 and re.fullmatch(r"[0-9a-f]{40}", out) else ""


def commit_of(ref, cwd, timeout=HEAD_READ):
    """The full commit hash `ref` names in the folder, or "" when the tool is missing, fails, or names no commit."""
    try:
        return commit_read(ref, cwd, timeout)
    except Unknown:
        return ""


WORKFLOW_DIR = ".github/workflows"
NO_PUSH_EVENTS = ("workflow_dispatch", "schedule")   # events that start no run for a push


def _glob_regex(pattern):
    """A workflow path-filter pattern as a regex, per GitHub's filter pattern cheat sheet: `*` is zero or more
    characters but `/`, `**` is zero or more of any character (`**/` also matches no folder, but only at the pattern start or after a `/`),`?` and `+` are zero or
    one and one or more of the character before them, `[...]` is one listed letter, digit or range, and `\\` escapes
    the next character. Raises _Unparsed for a form whose meaning is unsure (a `?` or `+` after no plain character, an
    open or odd bracket, a trailing `\\`), so the run stays due rather than a guessed reading dropping it."""
    parts, quantifiable, i = [], False, 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i) and (i == 0 or pattern[i - 1] == "/"):
            parts.append("(?:.*/)?")
            quantifiable, i = False, i + 3
        elif pattern.startswith("**", i):
            parts.append(".*")
            quantifiable, i = False, i + 2
        elif c == "*":
            parts.append("[^/]*")
            quantifiable, i = False, i + 1
        elif c in "?+":
            if not quantifiable:
                raise _Unparsed(pattern)
            parts[-1] = "(?:%s)%s" % (parts[-1], c)
            quantifiable, i = False, i + 1
        elif c == "[":
            j = pattern.find("]", i)
            if j < 0 or not re.fullmatch(r"(?:[a-z]-[a-z]|[A-Z]-[A-Z]|[0-9]-[0-9]|[A-Za-z0-9])+", pattern[i + 1:j]):
                raise _Unparsed(pattern)
            parts.append(pattern[i:j + 1])
            quantifiable, i = False, j + 1
        elif c == "\\":
            if i + 1 == len(pattern):
                raise _Unparsed(pattern)
            parts.append(re.escape(pattern[i + 1]))
            quantifiable, i = True, i + 2
        else:
            parts.append(re.escape(c))
            quantifiable, i = True, i + 1
    try:
        return re.compile("".join(parts) + r"\Z")
    except re.error:
        raise _Unparsed(pattern) from None


def _path_passes(path, patterns):
    """True when a filter's pattern list lets `path` through: the last pattern that matches decides, and `!` negates."""
    passed = False
    for pattern in patterns:
        negated = pattern.startswith("!")
        if _glob_regex(pattern[1:] if negated else pattern).match(path):
            passed = not negated
    return passed


def _unquote(word):
    word = word.strip()
    return word[1:-1] if len(word) > 1 and word[0] == word[-1] and word[0] in "'\"" else word


def _outside_quotes(raw):
    """-> (index, char) of each character of a workflow line that no quoted string holds. A quote opens only where a
    value starts (after a space, `[`, `{`, `,` or the line start), so a lone apostrophe inside a word is text. Not
    actions/ci-alarm/clear_rule.py's `strip_comment`: that one reads a lone apostrophe as a quote, and hooks/ stays
    stdlib-only and loads in the Stop hook. The quote characters themselves are not yielded."""
    quote = None
    for i, ch in enumerate(raw):
        before = raw[i - 1] if i else " "
        if quote:
            if ch == quote and not (quote == '"' and before == "\\"):
                quote = None
        elif ch in "'\"" and before in " \t[{,":
            quote = ch
        else:
            yield i, ch


def _strip_comment(raw):
    """A workflow line without its comment: a `#` at a line start or after a space ends the line, unless a quoted
    string holds it (see `_outside_quotes`)."""
    for i, ch in _outside_quotes(raw):
        if ch == "#" and (i == 0 or raw[i - 1] in " \t"):
            return raw[:i].rstrip()
    return raw.rstrip()


def _split_flow(text):
    """The items of a flow list's inner text, split at each comma no quoted string holds."""
    items, start = [], 0
    for i, ch in _outside_quotes(text):
        if ch == ",":
            items.append(text[start:i])
            start = i + 1
    items.append(text[start:])
    return [w for w in items if w.strip()]


def _scalar(word):
    """One filter pattern as written, quoted or plain. Raises _Unparsed for a plain scalar this reader cannot read
    exactly: a block scalar (`|`, `>`), an anchor (`&a`) or an alias (`*a`), which YAML resolves elsewhere. A plain
    scalar cannot start with `*` in YAML, so any such start is read as an alias."""
    word = word.strip()
    if word[:1] in ("'", '"'):
        return _unquote(word)
    if word[:1] in ("|", ">", "&", "*"):
        raise _Unparsed(word)
    return word


def _workflow_lines(text):
    """-> [(indent, content)] of a workflow's non-blank lines, comments dropped (see `_strip_comment`)."""
    lines = []
    for raw in text.splitlines():
        content = _strip_comment(raw)
        if content.strip():
            lines.append((len(content) - len(content.lstrip()), content.strip()))
    return lines


class _Unparsed(Exception):
    """A filter form this reader does not parse: the run stays due."""


def _filter_list(block, key):
    """The patterns of `key:` in a push block's lines ([(indent, content)]), or None when the key is absent. Reads a
    flow list (`[a, b]`, on one line or spread over lines), a lone scalar and a block list (`- a`). Raises _Unparsed
    for a flow list that never closes, a block list item with its value on the next line, a line under the key that
    is no list item, a key that yields no item (its items all commented out, or the next key follows it), and a
    scalar `_scalar` does not read. A list item is `-` then a space or a tab."""
    for n, (indent, content) in enumerate(block):
        head, colon, rest = content.partition(":")
        if head.strip() != key or not colon:
            continue
        rest = rest.strip()
        if rest.startswith("["):
            text, later = rest, iter(block[n + 1:])
            while not text.endswith("]"):
                nxt = next(later, None)
                if nxt is None:
                    raise _Unparsed(key)
                text += " " + nxt[1]
            return [_scalar(w) for w in _split_flow(text[1:-1])]
        if rest:
            return [_scalar(rest)]
        items = []
        for deeper, line in block[n + 1:]:
            is_item = line[0] == "-" and line[1:2] in ("", " ", "\t")
            if deeper < indent or (deeper == indent and not is_item):
                break
            if line == "-" or deeper > indent and not is_item:
                raise _Unparsed(key)
            if is_item:
                items.append(_scalar(line[1:]))
        if not items:
            raise _Unparsed(key)
        return items
    return None


def workflow_runs_for(text, files):
    """False only when a workflow's `on:` block reads cleanly and no push of `files` starts a run of it: it has no
    event but workflow_dispatch and schedule, or its push event carries a `paths` or `paths-ignore` filter that every
    file fails. A form this reader does not parse (a flow map, a key it does not know, an unsure filter pattern) reads
    True, so a run stays due.
    Stdlib only: CI and the Stop hook have no YAML parser."""
    lines = _workflow_lines(text)
    start = next((n for n, (i, c) in enumerate(lines) if i == 0 and re.match(r"""["']?on["']?\s*:""", c)), None)
    if start is None:
        return True
    inline = lines[start][1].partition(":")[2].strip()
    if inline:
        words = set(re.findall(r"[\w-]+", inline))
        return inline.startswith("{") or bool(words - set(NO_PUSH_EVENTS))
    body = []
    for indent, content in lines[start + 1:]:
        if indent == 0:
            break
        body.append((indent, content))
    if not body:
        return True
    base = body[0][0]
    if body[0][1].startswith("- "):
        return _sequence_runs(body, base)
    events, push_block, in_push = [], [], False
    for indent, content in body:
        if indent == base and not content.startswith("- "):
            name, _, rest = content.partition(":")
            events.append(_unquote(name))
            in_push = _unquote(name) == "push"
            if in_push and rest.strip():
                return True
        elif in_push:
            push_block.append((indent, content))
    if any(e not in NO_PUSH_EVENTS and e != "push" for e in events):
        return True
    if "push" not in events:
        return False
    try:
        paths, ignore = _filter_list(push_block, "paths"), _filter_list(push_block, "paths-ignore")
        if (paths is None) == (ignore is None):
            return True
        if paths is not None:
            return any(_path_passes(f, paths) for f in files)
        return any(not _path_passes(f, ignore) for f in files)
    except _Unparsed:
        return True


def _sequence_runs(body, base):
    """An `on:` block written as a block sequence (`- push`): False only when every item is a plain event name and
    none starts a run for a push. An item it cannot read, a line that is no item, or a deeper line reads True."""
    events = []
    for indent, content in body:
        name = _unquote(content[2:]) if indent == base and content.startswith("- ") else ""
        if not re.fullmatch(r"[\w-]+", name):
            return True
        events.append(name)
    return any(e not in NO_PUSH_EVENTS for e in events)


def push_may_start_run(full, old, cwd, budget):
    """False only when the workflow files at the pushed head all read cleanly and none can start a run for the files
    the push changed (`old..full`): a push no path filter matches starts no run, so none is due. Any read that fails,
    no workflow file, or a push with no `old` head (a new branch) reads True, so a run stays due. Cost: 2 git
    processes plus 1 per workflow file read; the reads stop at the first workflow that runs."""
    if not old:
        return True
    try:
        code, out = git_out(["diff", "--name-only", "--no-renames", "-z", old, full], cwd, budget.next_timeout(), "the push's files")
        files = [f for f in out.split("\0") if f]
        if code != 0:
            return True
        code, out = git_out(["ls-tree", "--name-only", "--full-tree", "-z", full, WORKFLOW_DIR + "/"], cwd, budget.next_timeout(),
                            "the workflow files")
        names = [n for n in out.split("\0") if n.endswith((".yml", ".yaml"))]
        if code != 0 or not names:
            return True
        for name in names:
            code, text = git_out(["show", "%s:%s" % (full, name)], cwd, budget.next_timeout(), name)
            if code != 0 or workflow_runs_for(text, files):
                return True
        return False
    except Unknown:
        return True


def head_state(sha, branch, cwd, budget=None, old=None):
    """-> (state, detail) for a head pushed to `branch`; sha may be short. One read, no wait. old is the head the
    remote held before the push (the push's ref line), or None.
    state: "none" (no CI to wait for: no open PR, a draft PR, a head the PR has moved past, a repo with no
    workflows, read once when the run list is empty, or a push no workflow path filter matches), "green",
    "pending" (a run has not ended, or a ready PR has no run yet), "red" (a run ended not green), or "unknown"
    (a read failed or ran out of budget). A push to main reads the head's runs direct. A ready PR's runs drop
    skipped ones as `wait_for` does, then judge_runs judges the rest (the cancelled-twin rule is its own)."""
    budget = budget or Budget()
    try:
        full, main = sha, branch in MAIN_BRANCHES
        if main:
            full = commit_of(sha, cwd, budget.next_timeout()) or sha
        else:
            try:
                pr = read_pr(branch, "", cwd, budget.next_timeout())
            except NoPR:
                return "none", "no open PR"
            if pr.get("isDraft"):
                return "none", "draft PR"
            if pr["headRefOid"].startswith(sha):
                full = pr["headRefOid"]
            elif old and pr["headRefOid"].startswith(old):
                # The PR read lags the push: it still names the head before it, so the pushed head is read direct.
                full = commit_of(sha, cwd, budget.next_timeout()) or sha
            else:
                return "none", "the PR head has moved past %s" % sha[:7]
        args = ["run", "list", "--commit", full, "--limit", "100", "--json", RUN_FIELDS]
        runs = [r for r in gh_json(args, cwd, timeout=budget.next_timeout()) if r["conclusion"] != "skipped"]
        if not runs:
            # No run is listed: either the repo has no CI (nothing to wait for) or the run has not started.
            if no_workflows(cwd, "", budget.next_timeout()):
                return "none", "the repo has no workflows"
            if not push_may_start_run(full, old, cwd, budget):
                return "none", "no workflow path filter matches the push"
            return ("unknown", "no run is listed for a push to %s" % branch) if main else ("pending", "no run yet")
        from guard_merge import merge_module
        merge = merge_module()
        if merge is None:
            raise Unknown("the merge tool (judge_runs) could not be loaded")
        red, pending = merge.Host.judge_runs(runs)
        if red:
            return "red", ", ".join(red)
        if pending:
            return "pending", ", ".join(pending)
        return "green", ""
    except NoPR:
        return "none", "no open PR"
    except Unknown as e:
        return "unknown", str(e)
    except Exception as e:
        return "unknown", "%s: %s" % (type(e).__name__, e)


def watch_pr(selector, repo, cwd, deadline, lock_dir):
    """-> one output line, or None when no watch starts."""
    ident = "PR" + selector if selector else "PR"
    try:
        pr = read_pr(selector, repo, cwd)
        ident = pr["headRefOid"][:7]
        repo = repo_of_url(pr.get("url")) or repo   # the PR's own repo, whatever form named it
        if pr.get("isDraft"):
            return None   # gh pr ready did not take: a draft runs no CI
        if no_workflows(cwd, repo):
            return None   # a repo with no active workflow runs no CI: nothing to wait for
        if not lock_pr(pr, lock_dir):
            return None
        return verdict(pr["headRefOid"], wait_for(pr["headRefOid"], cwd, deadline, repo))
    except NoPR:
        return None
    except Unknown as e:
        return "CI unknown on %s: %s" % (ident, e)
    except Exception as e:
        return "CI unknown on %s: %s: %s" % (ident, type(e).__name__, e)


def main():
    data = json.load(sys.stdin)
    if not isinstance(data, dict) or data.get("tool_name") not in ("Bash", "PowerShell"):
        return 0
    command = data["tool_input"]["command"]
    if "ready" not in command.lower():
        return 0   # no `gh pr ready` can hide here: no import, so a broken install wakes no `ls`
    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) and os.path.isdir(data["cwd"]) else None
    calls = triggers(command, data["tool_name"] == "PowerShell")
    if not calls:
        return 0
    try:
        budget = float(os.environ.get("CI_WAKE_DEADLINE") or DEFAULT_DEADLINE)
    except ValueError:
        budget = DEFAULT_DEADLINE
    deadline = time.monotonic() + budget
    lock_dir = os.environ.get("CI_WAKE_LOCK_DIR") or os.path.join(tempfile.gettempdir(), "ci-wake-locks")
    from guard_merge import merge_module
    merge_module()   # load once here, before the threads
    lines = [None] * len(calls)

    def work(i, selector, repo):
        lines[i] = watch_pr(selector, repo, cwd, deadline, lock_dir)

    threads = [threading.Thread(target=work, args=(i, *call), daemon=True) for i, call in enumerate(calls)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return emit([x for x in lines if x])


if __name__ == "__main__":
    try:
        code = main()
        if code:
            sys.stderr.flush()   # only after a write: a broken stderr must not wake a silent run
    except BaseException as e:   # never exit 1: an unread CI is an unknown, not a silent failure
        code = emit(["CI unknown on ?: %s: %s" % (type(e).__name__, e)])
    os._exit(code)   # a daemon thread or a killed gh child must not hold the process open
