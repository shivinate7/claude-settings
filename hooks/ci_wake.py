#!/usr/bin/env python3
"""CI wake-up hook. Standard library only. See decisions/handoff-hooks-wave-2.md, part 3.

PostToolUse hook for Bash, registered with `asyncRewake: true`. After `gh pr ready <N>`, or a
`git push` to a branch with an open ready PR, it waits once on every workflow run of that PR head
and exits 2 with one line, which wakes the session:

    CI <green|red|cancelled> on <sha7>: <failing job names>
    CI unknown on <sha7 or branch>: <reason>

Any other command exits 0 with no output and makes no gh call. A branch with no PR starts no
watch. It never polls and never loops on a red run: one PR read, one run list, one blocking
`gh run watch` per unfinished run, one read of each run. The settings.json `timeout` caps the wait.
The cancelled-twin rule is merge.py's `Host.judge_runs`, loaded through guard_merge.merge_module.
"""
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from guard_core import basename, resolve_command, segment_tokens, split_segments  # noqa: E402
from guard_merge import gh_call_of, merge_module  # noqa: E402

NO_RUN_PAUSE = 20   # seconds; the one pause when the head has no run yet
READ_TIMEOUT = 60   # seconds for each gh read; `gh run watch` has none (the hook timeout caps it)
PR_FIELDS = "number,isDraft,headRefName,headRefOid,state"
RUN_FIELDS = "databaseId,name,status,conclusion,workflowName,headSha,event"
GOOD = ("success", "skipped", "neutral")
REPO_FLAGS = ("-R", "--repo")


class Unknown(Exception):
    """A read that could not run. The message is the reason."""


class NoPR(Exception):
    """The branch or number names no pull request: no watch, not an unknown."""


def say(line):
    sys.stderr.write(" ".join(line.split())[:300] + "\n")
    sys.exit(2)


def gh(args, cwd, timeout=READ_TIMEOUT):
    """-> (rc, stdout, stderr). gh is found with shutil.which: a list-form call of a bare "gh"
    misses a .cmd launcher on Windows."""
    exe = shutil.which("gh")
    if exe is None:
        raise Unknown("gh is not on PATH")
    try:
        p = subprocess.run([exe, *args], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=cwd, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Unknown("gh %s failed: %s" % (" ".join(args[:2]), type(e).__name__))
    return p.returncode, p.stdout or "", p.stderr or ""


def gh_json(args, cwd):
    rc, out, err = gh(args, cwd)
    if rc != 0:
        if "no pull requests found" in (out + err).lower():
            raise NoPR()
        raise Unknown("gh %s exited %d: %s" % (" ".join(args[:2]), rc, (err or out).strip()))
    try:
        return json.loads(out)
    except ValueError:
        raise Unknown("gh %s printed non-JSON" % " ".join(args[:2]))


def command_words(segment):
    """-> (program, args) of a segment's command word, or None."""
    tokens = segment_tokens(segment)
    if not tokens:
        return None
    i = resolve_command(tokens)
    return None if i is None else (basename(tokens[i]), tokens[i + 1:])


def ready_call(rest):
    """-> (selector, repo) for `gh pr ready` args, else None."""
    if rest[:2] != ["pr", "ready"] or any(a in ("--undo", "-h", "--help") for a in rest):
        return None
    pos, repo, i = [], "", 2
    while i < len(rest):
        a = rest[i]
        if a in REPO_FLAGS and i + 1 < len(rest):
            repo, i = rest[i + 1], i + 1
        elif a.startswith("--repo="):
            repo = a[7:]
        elif not a.startswith("-"):
            pos.append(a)
        i += 1
    return (pos[0] if pos else ""), repo


def triggers(command):
    """-> the watches this command starts, in order: ("ready", selector, repo) or ("push", args, "").
    Reads the text only. Quoted text is no command, and a word that is not a segment's command is no call."""
    found = []
    for segment in split_segments(command):
        rest = gh_call_of(segment)
        if rest is not None:
            call = ready_call(rest)
            if call:
                found.append(("ready", *call))
            continue
        words = command_words(segment)
        if words and words[0] in ("git", "git.exe"):
            args, i = words[1], 0
            while i < len(args) and args[i].startswith("-"):   # git global options
                i += 2 if args[i] in ("-C", "-c") else 1
            if args[i:i + 1] == ["push"]:
                found.append(("push", args[i + 1:], ""))
    return found


def push_branch(args, cwd):
    """The branch a `git push` targets, or "" when it pushes no branch (delete, tags)."""
    if any(a in ("-d", "--delete", "--tags", "--mirror") for a in args):
        return ""
    pos = [a for a in args if not a.startswith("-")][1:]   # drop the remote
    ref = (pos[0] if pos else "HEAD").split(":")[-1].lstrip("+")
    if ref.startswith("refs/heads/"):
        ref = ref[len("refs/heads/"):]
    if ref in ("", "HEAD"):   # the current branch
        try:
            ref = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True,
                                 cwd=cwd, timeout=READ_TIMEOUT).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            ref = ""
        if not ref:
            raise Unknown("git push target branch not readable")
    return ref


def ready_pr(kind, key, repo, cwd):
    """-> the open, non-draft PR to watch, or None for a draft, a closed PR or no PR."""
    extra = ["-R", repo] if repo else []
    try:
        if kind == "ready":
            prs = [gh_json(["pr", "view", *([key] if key else []), *extra, "--json", PR_FIELDS], cwd)]
        else:
            prs = gh_json(["pr", "list", "--head", key, "--json", PR_FIELDS], cwd)
        prs = [p for p in prs if p.get("state", "OPEN") == "OPEN" and not p.get("isDraft")]
    except NoPR:
        return None
    return prs[0] if prs else None


def wait_for(sha, cwd):
    """One run list (two when the head has no run yet, after one pause), one blocking watch per
    run (not a cancelled twin), then one read of each run with its jobs."""
    list_args = ["run", "list", "--commit", sha, "--limit", "100", "--json", RUN_FIELDS]
    runs = gh_json(list_args, cwd)
    if not runs:
        time.sleep(NO_RUN_PAUSE)
        runs = gh_json(list_args, cwd)
    if not runs:
        raise Unknown("no run yet")
    live = {r["name"] for r in runs if r["conclusion"] != "cancelled"}
    for r in runs:
        if r["conclusion"] == "cancelled" and r["name"] in live:
            continue   # a cancelled twin: judge_runs reads the run that ran
        gh(["run", "watch", str(r["databaseId"])], cwd, timeout=None)   # blocks; at once for a finished run. The view below gives the verdict
    return [gh_json(["run", "view", str(r["databaseId"]), "--json", "databaseId,name,status,conclusion,jobs"], cwd)
            for r in runs]


def verdict(sha, runs):
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


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(data, dict) or data.get("tool_name") != "Bash":
        return 0
    command = (data.get("tool_input") or {}).get("command")
    if not isinstance(command, str):
        return 0
    cwd = data.get("cwd") if os.path.isdir(data.get("cwd") or "") else None
    ident = "?"
    try:
        for kind, key, repo in triggers(command):
            if kind == "push":
                key = push_branch(key, cwd)
                if not key:
                    continue
            ident = key or "PR"
            pr = ready_pr(kind, key, repo, cwd)
            if pr:
                sha = pr["headRefOid"]
                ident = sha[:7]
                say(verdict(sha, wait_for(sha, cwd)))
    except Unknown as e:
        say("CI unknown on %s: %s" % (ident, e))
    except (KeyError, TypeError, AttributeError):
        say("CI unknown on %s: gh printed unexpected JSON" % ident)
    return 0


if __name__ == "__main__":
    sys.exit(main())
