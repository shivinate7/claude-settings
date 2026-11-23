#!/usr/bin/env python3
"""After the shell ready command `gh pr ready <N>` (Bash or PowerShell), or an `mcp__github__update_pull_request` call with `draft` false, waits for CI on that PR head. Then wakes the session with one line: green, red, cancelled or unknown, with the names of failing jobs.

PostToolUse hook for the Bash and PowerShell tools and for the GitHub MCP `update_pull_request` tool,
registered with `asyncRewake: true`. Two calls start a watch: `gh pr ready <N>`, and an MCP `update_pull_request`
with `draft` false (the cloud's ready route, since `gh pr ready` gets 403 in cloud; route pr-ready-gh-cli-cloud;
decision ci-wait-reads-run-status, The CI wake-up). The MCP call names its PR by `owner`, `repo` and `pullNumber` in tool_input.
A call with `draft` absent or true starts none. Each `gh pr ready` in a command gets its own watch, in this one
process. A push starts none. Per PR it reads the head once. It lists that head's runs until a run settles the
wait (`settled`: a red run, a run still going, or a completed run whose rollup job `all-jobs-passed` passed; a skipped
draft run, a draft-era checks run whose rollup job is skipped or absent, and a green run of another workflow settle
nothing, so green never comes from them), waits on it, lists once more at once for a late run, and prints one line:

    CI <green|red|cancelled> on <sha7>: <failing job names>
    CI unknown on <sha7 or PR>: <reason>        (also "still running" at the deadline)

A job of the run that has failed ends the wait at the poll that shows it, while the run goes on: the line is then red,
and names the failed jobs known so far. A red line is followed by up to MAX_DETAIL lines: the failing lines of the
first failed job's log (merge.py `failing_log_lines`, each cut to DETAIL_WIDTH characters, timestamp and colour codes
removed), or one `log unread: <reason>` line when that log could not be read or holds no failing line.
Then it exits 2 once, which wakes the session. A repo with no active workflow, whose PR adds no
.github/workflows file, has no CI to wait for, so it wakes with `CI none on <sha7>: no active workflow`. The
Stop check closes its CI wait on that line and reads only the transcript (stall_watch `open_ci_wait`). A workflow
list with stderr output reads unknown, and the watch runs. It prints nothing and exits 0 when no watch starts, for a
draft or when another watcher already holds every PR it would watch. Any error exits 2 with an unknown
line, never 1. It lists runs, and reads a run's status and jobs (one `gh` child per poll; API requests per poll unmeasured), 30 s apart for the first 4 minutes, then at
gaps that grow to 120 s (`pauses`). One extra list comes at once after the first judged run, to catch a
run that shows late (debt ci-wake-lists-runs-once). It never loops on a red run. Cost: no more status reads than that
schedule, plus one job-log read per watch, made only for a red wake (the first failed job's log).

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

HERE = os.path.dirname(os.path.realpath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# The sibling modules (guard_core, guard_env, guard_merge, _nowindow) load inside main() and gh(), so a
# failed import ends in an unknown line, never a traceback and exit 1.

MCP_READY_TOOL = "mcp__github__update_pull_request"   # the cloud's ready route: draft false marks a PR ready
DEFAULT_DEADLINE = 3300   # seconds; the hook timeout in settings.json is 3600
STATUS_PAUSE = 30         # seconds between two reads in the first BACKOFF_FLAT seconds, and before a retry
BACKOFF_FLAT = 240        # seconds the gap stays STATUS_PAUSE
BACKOFF_CAP = 120         # seconds, the longest gap
READ_TIMEOUT = 60         # seconds for each gh read
POLL_FIELDS = "status,jobs"   # one poll: the status, and the jobs that show a failure while the run goes on
MAX_DETAIL = 12           # failing lines after a red line
DETAIL_WIDTH = 200        # characters of one failing line
ANSI = re.compile(r"\x1b\[[0-9;]*m")
RUN_FIELDS = "databaseId,name,status,conclusion,workflowName,headSha,event"
GOOD = ("success", "skipped", "neutral")
REPO_FLAGS = ("-R", "--repo")
PR_URL = re.compile(r"^https?://([^/]+)/([^/]+/[^/]+)/pull/(\d+)")
# A word-internal apostrophe (don't) opens no quote. Masked here, so split_segments does not read it as one.
APOSTROPHE = re.compile(r"(?<=[A-Za-z])'(?=[A-Za-z])")
HELD = []   # open lock files, kept until the process ends: the OS drops the locks then, kill included


NO_CI_LINE = "CI none on %s: no active workflow"   # CI_VERDICT in stall_watch closes the Stop wait on it


class Unknown(Exception):
    """A read that could not run. The message is the reason."""


class NoPR(Exception):
    """The number names no pull request: no watch, not an unknown."""


def emit(lines):
    if not lines:
        return 0
    try:
        # A line may hold line breaks (a red wake and its failing lines): each part is one output line.
        sys.stderr.buffer.write("".join(" ".join(part.split())[:300] + "\n" for x in lines for part in x.split("\n")).encode("utf-8", "replace"))
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
    """-> the JSON gh prints. gone: text in a failed read's output that means the PR does not exist (NoPR).
    timeout: seconds for the one gh read; precompact_handoff's goal-order reminder passes a short one."""
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
    """Read `gh run view <id> --json status,jobs` until the status is `completed`, a job has failed, or the deadline
    passes. -> True when a job failed while the run still goes (the wake need not wait for the run's end), else None.
    Reads follow `pauses`, and the last pause ends at the deadline. No `gh run watch` (decision ci-wait-reads-run-status). A failed or non-JSON read
    gets one retry after the pause (never past the deadline); a second failure raises Unknown."""
    def read():
        args = ["run", "view", str(run_id), *(["-R", repo] if repo else []), "--json", POLL_FIELDS]
        try:
            return gh_json(args, cwd)
        except Unknown:
            time.sleep(max(0, min(STATUS_PAUSE, deadline - time.monotonic())))
            if deadline - time.monotonic() <= 0:
                raise
            return gh_json(args, cwd)
    gaps = pauses()
    while deadline - time.monotonic() > 0:  # at or past the deadline: no read, no pause
        got = read()
        if got.get("status") == "completed":
            return
        if any(j.get("conclusion") == "failure" for j in got.get("jobs") or []):
            return True
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
    return merge is not None and bool(judge(merge, runs)[0])


def early_red(run):
    """True for a run that goes on (not completed) with a job that has failed: red already."""
    return run.get("status") != "completed" and any(j.get("conclusion") == "failure" for j in run.get("jobs") or [])


def judge(merge, runs):
    """-> (red, pending) as judge_runs gives them, with a run that goes on and has a failed job judged red, not pending."""
    red, pending = merge.Host.judge_runs([dict(r, status="completed", conclusion="failure") if early_red(r) else r for r in runs])
    for r in runs:
        # judge_runs keeps one run per name, the newest. A failed run that a newer run of its name hides (one still going)
        # must stay red: a green line would claim the failed job passed.
        newest = next(x for x in runs if x["name"] == r["name"])
        if early_red(r) and newest.get("status") != "completed" \
                and not any(t.startswith("workflow %s: " % r["name"]) for t in red):
            red.append("workflow %s: failure" % r["name"])
    return red, pending


def settled(runs):
    """True when `runs` may end the wait: a run is red (a failed job included), a run is still going (an unknown line, never
    green), or a completed run has its rollup job (merge.py ROLLUP_JOB, the one home of the name) passed. A head whose runs
    are all draft-era (a checks run whose rollup job is skipped or absent, a green run of another workflow) is none of these:
    the real run is still to come, so the wait keeps listing. An unloadable merge tool settles at once: verdict raises Unknown."""
    from guard_merge import merge_module
    merge = merge_module()
    if merge is None:
        return True
    red, pending = judge(merge, runs)
    rollup = getattr(merge, "ROLLUP_JOB", None)
    return bool(red or pending) or any(
        r.get("status") == "completed" and any(j.get("name") == rollup and j.get("conclusion") == "success" for j in r.get("jobs") or [])
        for r in runs)


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
    list does, since the unread list could hold a red or a running run (rule verification-report-unknown-reads). A run that first shows after the re-list is not judged (debt ci-wake-lists-runs-once).
    Runs that `settled` does not accept (draft-era runs only) end no wait and start no at-once re-list: the lists follow `pauses`,
    each run is viewed once, and the deadline ends in Unknown. The rollup job's name is merge.py ROLLUP_JOB, read from the runs' own jobs: no extra read."""
    extra = ["-R", repo] if repo else []
    list_args = ["run", "list", "--commit", sha, "--limit", "100", *extra, "--json", RUN_FIELDS]
    gaps = pauses()
    seen, viewed, relisted, failed_early = set(), [], False, False
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
            if failed_early:
                break   # a job failed in a run that goes on: no other run is waited on, each is only read once below
            failed_early = bool(watch_run(r["databaseId"], cwd, deadline, repo))
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
        if ran and not relisted and settled(viewed):
            relisted = True
            continue   # the first settled run: list once more at once for a later one, even at the deadline
        if viewed and settled(viewed):
            return viewed
        left = deadline - time.monotonic()
        if left <= 0:
            raise Unknown("no run with a passed rollup job yet" if viewed else "no run yet")
        time.sleep(min(next(gaps), left))


def verdict(sha, runs):
    from guard_merge import merge_module
    merge = merge_module()
    if merge is None:
        raise Unknown("the merge tool (judge_runs) could not be loaded")
    early = any(early_red(r) for r in runs)
    red, pending = judge(merge, runs)
    if pending and not early:   # a red run stays red, whatever else still runs
        raise Unknown("still running: " + ", ".join(pending))
    if not red:
        return "CI green on %s: no failing jobs" % sha[:7]
    names, cancelled = [], True
    for text in red:
        run = next((r for r in sorted(runs, key=lambda x: not early_red(x)) if text.startswith("workflow %s: " % r["name"])), None)   # a failed run before the newer run of its name that hides it
        if run is None:
            names.append(text)
            cancelled = False
            continue
        cancelled = cancelled and run["conclusion"] == "cancelled"
        failed_now = early_red(run)   # its other jobs still run: only the failed ones are red so far
        jobs = [j["name"] for j in run.get("jobs") or []
                if (j.get("conclusion") == "failure" if failed_now else j.get("conclusion") not in GOOD)]
        names.extend(jobs or ["workflow " + run["name"]])
    return "CI %s on %s: %s" % ("cancelled" if cancelled else "red", sha[:7], ", ".join(dict.fromkeys(names)))


def first_failed_job(runs, rollup=None):
    """-> (name, job id) of the first failed job of the runs, newest run first, else None. The rollup job (merge.py
    ROLLUP_JOB, passed as `rollup`) is skipped: it logs only its own verdict."""
    for run in runs:
        for j in run.get("jobs") or []:
            if j.get("conclusion") == "failure" and j.get("name") != rollup:
                return j.get("name") or "?", j.get("databaseId") or j.get("id")
    return None


def unlogged_cause(runs, rollup=None):
    """-> the `log unread` line for a red run with no failed job: the first job that ended badly (timed_out and the like) with
    its conclusion, else the first red run's own conclusion (startup_failure), else a plain no-failed-job line."""
    for run in runs:
        for j in run.get("jobs") or []:
            if j.get("conclusion") not in GOOD + (None, "failure", "cancelled") and j.get("name") != rollup:
                return "log unread: job %s concluded %s" % (j.get("name") or "?", j["conclusion"])
    for run in runs:
        if run.get("status") == "completed" and run.get("conclusion") not in GOOD:
            return "log unread: workflow %s concluded %s, with no failed job" % (run.get("name") or "?", run.get("conclusion"))
    return "log unread: no failed job in the run"


def detail_lines(runs, cwd, repo):
    """-> the lines after a red line: the failing lines of the first failed job's log, else one `log unread: <reason>`
    line. This is the watch's one log read. A refused or empty read is unknown, never clear. The lines come from
    merge.py `failing_log_lines`, the one home of the log reader, with timestamp and colour codes removed."""
    from guard_merge import merge_module
    merge = merge_module()
    rollup = getattr(merge, "ROLLUP_JOB", None) if merge is not None else None
    job = first_failed_job(runs, rollup)
    if job is None:
        return [unlogged_cause(runs, rollup)]
    name, job_id = job
    slug, tail = repo_route(repo)
    try:
        rc, out, err = gh(["api", "-X", "GET", "repos/%s/actions/jobs/%s/logs" % (slug, job_id), *tail], cwd)
        if rc != 0:
            return ["log unread: reading the log of job %s failed: %s" % (name, (err or out).strip() or "gh exited %d" % rc)]
        if merge is None:
            return ["log unread: the merge tool (failing_log_lines) could not be loaded"]
        lines = []
        for raw, _parsed in merge.failing_log_lines(out, detail=True):
            text = ANSI.sub("", merge.LOG_PREFIX.sub("", raw, count=1)).strip()
            if text:
                lines.append(text[:DETAIL_WIDTH])
    except Unknown as e:
        return ["log unread: %s" % e]
    return lines[:MAX_DETAIL] or ["log unread: the log of job %s has no failing line" % name]


def no_workflows(cwd, repo):
    """True only when `gh workflow list` reads cleanly and shows no active workflow: no CI, so no
    watch. gh 2.89.0 prints 0 bytes and exits 0 for a repo with no workflow, never "[]", so empty output
    with exit 0 and nothing on stderr counts as none. A failed, non-JSON or noisy read is unknown, not
    "no workflows" (the watch runs)."""
    try:
        rc, out, err = gh(["workflow", "list", *(["-R", repo] if repo else []), "--json", "id"], cwd)
        return rc == 0 and (not out.strip() and not err.strip() or bool(out.strip()) and json.loads(out) == [])
    except (Unknown, ValueError):
        return False


def repo_route(repo):
    """-> (slug, gh api tail) for a repo of the form [HOST/]OWNER/REPO, else gh fills {owner}/{repo} from the folder."""
    parts = repo.split("/") if repo else []
    host, slug = (parts[0], "/".join(parts[1:])) if len(parts) == 3 else ("", repo or "{owner}/{repo}")
    return slug, (["--hostname", host] if host else [])


def adds_workflow(pr, repo, cwd):
    """True when the PR's own files touch .github/workflows, or the file list cannot be read in full: the PR's head
    has CI that the default branch's workflow list does not show. One page of 100 files; a full page may hide it."""
    slug, tail = repo_route(repo)
    try:
        files = gh_json(["api", "--method", "GET", "repos/%s/pulls/%s/files" % (slug, pr["number"]), "-F", "per_page=100", *tail], cwd)
    except (Unknown, NoPR):
        return True
    return not isinstance(files, list) or len(files) >= 100 or any(
        str(f.get("filename", "")).startswith(".github/workflows/") for f in files if isinstance(f, dict))


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
    slug, tail = repo_route(repo)
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
        if not lock_pr(pr, lock_dir):
            return None
        if no_workflows(cwd, repo) and not adds_workflow(pr, repo, cwd):
            return NO_CI_LINE % ident   # no CI to wait for; the line closes the Stop's CI wait
        runs = wait_for(pr["headRefOid"], cwd, deadline, repo)
        line = verdict(pr["headRefOid"], runs)
        if line.startswith("CI red "):
            line = "\n".join([line, *detail_lines(runs, cwd, repo)])
        return line
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
