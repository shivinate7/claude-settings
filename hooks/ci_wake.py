#!/usr/bin/env python3
"""After the shell ready command `gh pr ready <N>` (Bash or PowerShell), or an `mcp__github__update_pull_request` call with `draft` false, waits for CI on that PR head. Then wakes the session with one line: green, red, cancelled or unknown, with the names of failing jobs.

PostToolUse hook for the Bash and PowerShell tools and for the GitHub MCP `update_pull_request` tool,
registered with `asyncRewake: true`. Two calls start a watch: `gh pr ready <N>`, and an MCP `update_pull_request`
with `draft` false (the cloud's ready route, since `gh pr ready` gets 403 in cloud; route pr-ready-gh-cli-cloud;
decision ci-wait-reads-run-status, The CI wake-up). The MCP call names its PR by `owner`, `repo` and `pullNumber` in tool_input.
A call with `draft` absent or true starts none. Each `gh pr ready` in a command gets its own watch, in this one
process. A push starts none. Per PR it reads the head once. It lists that head's runs until a run that
ran shows (a skipped draft run is no run), waits on it, lists once more at once for a late run, and prints one line:

    CI <green|red|cancelled> on <sha7>: <failing job names>
    CI unknown on <sha7 or PR>: <reason>        (also "still running" at the deadline)

Then it exits 2 once, which wakes the session. It prints nothing and exits 0 when no watch starts,
when the repo has no active workflow, or when another watcher already holds every PR it would watch. Any error exits 2 with an unknown
line, never 1. It lists runs, and reads a run's status, 30 s apart for the first 4 minutes, then at
gaps that grow to 120 s (`pauses`). One extra list comes at once after the first judged run, to catch a
run that shows late (debt ci-wake-lists-runs-once). It never loops on a red run.

Seams: CI_WAKE_DEADLINE, the watch budget in seconds (default DEFAULT_DEADLINE, under the hook
timeout in settings.json). CI_WAKE_LOCK_DIR, the folder of the per-PR lock files.
The cancelled-twin rule is merge.py's `Host.judge_runs`, loaded through guard_merge.merge_module.
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

# The sibling modules (guard_core, guard_env, guard_merge, git_reads, _nowindow) load inside the functions that use
# them, so a failed import ends in an unknown line, never a traceback and exit 1.

MCP_READY_TOOL = "mcp__github__update_pull_request"   # the cloud's ready route: draft false marks a PR ready
DEFAULT_DEADLINE = 3300   # seconds; the hook timeout in settings.json is 3600
STATUS_PAUSE = 30         # seconds between two reads in the first BACKOFF_FLAT seconds, and before a retry
BACKOFF_FLAT = 240        # seconds the gap stays STATUS_PAUSE
BACKOFF_CAP = 120         # seconds, the longest gap
READ_TIMEOUT = 60         # seconds for each gh read
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
    """-> (rc, stdout, stderr) from git_reads.gh_run, the one gh runner (shared with the guard); a GhUnread from it,
    such as a missing gh or a timeout, is raised here as Unknown."""
    try:
        import git_reads  # the one gh runner (git_reads.gh_run)
    except ImportError as e:  # a hook never dies for a missing helper (it lands a moment after the hook in an install)
        raise Unknown("gh runner unavailable: %s" % type(e).__name__)
    try:
        return git_reads.gh_run(args, cwd, timeout)
    except git_reads.GhUnread as e:
        raise Unknown(str(e))


def gh_json(args, cwd, gone=""):
    """-> the JSON gh prints. gone: text in a failed read's output that means the PR does not exist (NoPR)."""
    rc, out, err = gh(args, cwd)
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


def exported_repo(tokens):
    """The GH_REPO a segment sets for the shell, "" when it clears it, None when it leaves it alone:
    `export GH_REPO=o/r` (an empty value clears), `unset GH_REPO` (bash), `$env:GH_REPO = o/r` or
    `${env:GH_REPO} = o/r` (PowerShell, any case), `Remove-Item Env:GH_REPO` or `ri` (clears). The
    hook reads text only, so a value it cannot expand (`$var`, `$null`, `$(...)`, a backtick) names
    no repo: "" too, and the folder's repo is used."""
    def value(v):
        return "" if "$" in v or "`" in v else v
    if tokens[:1] == ["export"]:
        vals = [t[8:] for t in tokens[1:] if t.startswith("GH_REPO=")]
        return value(vals[-1]) if vals else None
    if tokens[:1] == ["unset"]:
        return "" if "GH_REPO" in tokens[1:] else None
    if tokens[:1] and tokens[0].lower() in ("remove-item", "ri"):
        return "" if any(re.match(r"env:\\?gh_repo$", t, re.I) for t in tokens[1:]) else None
    m = tokens and re.match(r"\$(?:env:gh_repo|\{env:gh_repo\})(=.*)?$", tokens[0], re.I)
    if m:
        if m.group(1):
            return value(m.group(1)[1:])
        if tokens[1:2] == ["="]:
            return value(tokens[2]) if len(tokens) > 2 else ""
    return None


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
    exported = ""   # GH_REPO set earlier in the command text, for every later gh call
    for segment in (p for s in guard_core.split_segments(text) for p in _ampersand_split(s)):
        rest = gh_call_of(segment)
        tokens = segment_tokens(segment) or []
        call = None
        if rest is not None:
            env = [t[8:] for t in tokens[:resolve_command(tokens) or 0] if t.startswith("GH_REPO=")]
            call = ready_call(rest, env[-1] if env else exported)
        else:
            new = exported_repo(tokens)
            exported = exported if new is None else new
        if call:
            found.append(call)
    return found


def mcp_ready_calls(tool_input):
    """-> [(selector, repo)] for a GitHub MCP update_pull_request call that marks a PR ready, else [].
    Only `draft` false is a ready call: an absent or true `draft` starts none. The PR is the owner, repo
    and pullNumber of tool_input, in the same form `gh pr ready <N> --repo <owner>/<repo>` gives
    (guard.py reads the same keys). A call that names no PR starts none."""
    if not isinstance(tool_input, dict) or tool_input.get("draft") is not False:
        return []
    owner, repo, number = tool_input.get("owner"), tool_input.get("repo"), tool_input.get("pullNumber")
    if not (isinstance(owner, str) and owner and isinstance(repo, str) and repo):
        return []
    if isinstance(number, bool) or not (isinstance(number, int) or (isinstance(number, str) and number.isdigit())):
        return []
    return [(str(number), "%s/%s" % (owner, repo))]


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


def judged_red(runs):
    """True when judge_runs finds a red run among `runs`. An unloadable merge tool judges nothing red."""
    from guard_merge import merge_module
    merge = merge_module()
    return merge is not None and bool(merge.Host.judge_runs(runs)[0])


def wait_for(sha, cwd, deadline, repo=""):
    """List the head's runs, watch each one (not a cancelled twin), then read each with its jobs.
    A run that ends skipped is no run: the draft PR's run skips, and the run of `gh pr ready`
    comes after it. While no run that ran is judged, list again, `pauses` apart; the last
    pause ends at the deadline, with one list there. After the first run that ran is judged,
    list once more at once, even when the deadline has passed, and judge any run not yet read there, then
    return. The re-list past the deadline may add one list call plus one view per new run. A run still going at the re-list reads as pending, so Unknown. The runs come back
    newest first, as judge_runs reads them: the re-list's runs go ahead of the runs read before,
    so a newer run of a name outranks the older one. A refused re-list list or view returns the runs already
    judged only when they judge red: a red run stays red. Otherwise it raises Unknown, as a refused first
    list does, since the unread list could hold a red or a running run (rule verification-report-unknown-reads). A run that first shows after the re-list is not judged (debt ci-wake-lists-runs-once)."""
    extra = ["-R", repo] if repo else []
    list_args = ["run", "list", "--commit", sha, "--limit", "100", *extra, "--json", RUN_FIELDS]
    gaps = pauses()
    seen, viewed, relisted = set(), [], False
    while True:
        try:
            listed = gh_json(list_args, cwd)
        except Unknown:
            if viewed and judged_red(viewed):
                return viewed   # the at-once re-list failed: a red run stays red, whatever the list hid
            raise   # no run judged yet, or the judged runs are not red: a green line would claim the unread list passed
        runs = [r for r in listed if r["conclusion"] != "skipped"]
        live = {r["name"] for r in runs if r["conclusion"] != "cancelled"}
        fresh = [r for r in runs if r["databaseId"] not in seen
                 and not (r["conclusion"] == "cancelled" and r["name"] in live)]   # a cancelled twin: judge_runs reads the run that ran
        for r in fresh:
            watch_run(r["databaseId"], cwd, deadline, repo)
        try:
            got = [gh_json(["run", "view", str(r["databaseId"]), *extra, "--json", "databaseId,name,status,conclusion,jobs"], cwd)
                   for r in fresh]
        except Unknown:
            if viewed and judged_red(viewed):
                return viewed   # a refused view in a later list: a red run stays red, as for a refused list
            raise   # a first-list view, or judged runs that are not red: unread runs could be red or running
        seen.update(r["databaseId"] for r in fresh)
        ran = [r for r in got if r.get("conclusion") != "skipped"]   # it ended skipped: no run
        viewed = ran + viewed   # newest first: gh lists newest first, and a later list shows newer runs
        if ran and not relisted:
            relisted = True
            continue   # the first judged run: list once more at once for a later one, even at the deadline
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


def no_workflows(cwd, repo):
    """True only when `gh workflow list` reads cleanly and shows no active workflow: no CI, so no
    watch. A failed or non-JSON read is unknown, not "no workflows" (the watch runs)."""
    try:
        return gh_json(["workflow", "list", *(["-R", repo] if repo else []), "--json", "id"], cwd) == []
    except (Unknown, NoPR):
        return False


def pr_fields(p):
    """A REST pull request as the dict the watch reads: number, isDraft, headRefName, headRefOid, state
    (OPEN, CLOSED, MERGED) and url. The list endpoint has `merged_at` only, so either marks a merge."""
    return {"number": p["number"], "isDraft": bool(p.get("draft")), "headRefName": p["head"]["ref"],
            "headRefOid": p["head"]["sha"], "url": p["html_url"],
            "state": "MERGED" if p.get("merged") or p.get("merged_at") else p["state"].upper()}


def current_branch(cwd):
    """The folder's branch, for `gh pr ready` with no selector. A detached HEAD names none."""
    try:
        import _nowindow
    except ImportError:
        _nowindow = subprocess
    exe = shutil.which("git")  # a bare "git" misses a .cmd launcher on Windows, as for gh
    if exe is None:
        raise Unknown("git branch read failed: git is not on PATH")
    try:
        p = _nowindow.run([exe, "symbolic-ref", "--short", "-q", "HEAD"], cwd=cwd, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=READ_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Unknown("git branch read failed: %s" % type(e).__name__)
    if p.returncode != 0 or not p.stdout.strip():
        raise Unknown("no branch is checked out")
    return p.stdout.strip()


def read_pr(selector, repo, cwd):
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
    if selector[:1] == "#" and selector[1:].isdigit():
        selector = selector[1:]   # `gh pr ready "#12"` names PR 12, as gh reads it
    if selector.isdigit():
        return pr_fields(gh_json(["api", base + "/" + selector, *tail], cwd, gone="http 404"))
    head = selector or current_branch(cwd)
    if ":" not in head:
        head = slug.split("/")[0] + ":" + head
    # Fields, not a query string: a `&` in an argument is a command separator to cmd.exe behind a .cmd
    # launcher. -F fills a {owner} placeholder inside its value; -f does not.
    found = gh_json(["api", "-X", "GET", base, "-F", "head=" + head, "-f", "state=open", *tail], cwd)
    if not found:
        raise NoPR()
    return pr_fields(found[0])


def repo_of_url(url):
    """The `[HOST/]OWNER/REPO` of a pull request url, for -R; "" when the url names none."""
    m = PR_URL.match(url or "")
    return "" if m is None else m.group(2) if m.group(1) == "github.com" else m.group(1) + "/" + m.group(2)


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
    if not isinstance(data, dict) or data.get("tool_name") not in ("Bash", "PowerShell", MCP_READY_TOOL):
        return 0
    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) and os.path.isdir(data["cwd"]) else None
    if data["tool_name"] == MCP_READY_TOOL:
        calls = mcp_ready_calls(data.get("tool_input"))
    else:
        command = data["tool_input"]["command"]
        if "ready" not in command.lower():
            return 0   # no `gh pr ready` can hide here: no import, so a broken install wakes no `ls`
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
