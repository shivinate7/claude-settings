#!/usr/bin/env python3
"""Cancels the CI runs of a pull request that was closed, for .github/workflows/cancel-on-close.yml.

Usage: cancel_closed_pr_runs.py PR_NUMBER OWNER/REPO      (env: GH_TOKEN, read by the gh CLI)

It re-reads the PR from the API instead of trusting the event, lists the repo's runs that have not finished, and cancels
each one select_runs picks. It fails safe: a PR that is not closed, another open PR on the same head branch, a read it
cannot parse or a gh call that fails cancels nothing, and an unreadable input exits non-zero so the run shows red. Stdlib only.
"""
import json
import os
import subprocess
import sys

# The run statuses GitHub lists as not finished. A completed run has nothing left to cancel.
ACTIVE_STATUSES = ("queued", "in_progress", "waiting", "pending", "requested")


def pr_is_closed(state):
    return state == "closed"


def _head_of(pr):
    """(head ref, head repo full name) of a PR dict, or None when the PR names either as anything but a non-empty string.
    A deleted fork has a null head repo."""
    head = pr.get("head") if isinstance(pr, dict) else None
    repo = head.get("repo") if isinstance(head, dict) else None
    ref = head.get("ref") if isinstance(head, dict) else None
    name = repo.get("full_name") if isinstance(repo, dict) else None
    if not (isinstance(ref, str) and ref and isinstance(name, str) and name):
        return None
    return ref, name


def head_in_repo(pr, repo):
    """True when the PR's head branch lives in this repo. A fork's runs belong to the fork's author."""
    head = _head_of(pr)
    return head is not None and head[1] == repo


def other_open_pr_shares_head(open_prs, pr):
    """True when an open PR other than this one has the same head branch in the same head repo. Closing one of two PRs
    on a branch must leave the runs the other still needs."""
    head = _head_of(pr)
    if head is None or not isinstance(open_prs, list):
        return False
    return any(isinstance(other, dict) and other.get("number") != pr.get("number") and _head_of(other) == head
               for other in open_prs)


def _is_candidate(run, pr, repo, default_branch):
    """An unfinished pull_request run on this PR's head branch, from this repo, before its PR list is read."""
    if not isinstance(run, dict):
        return False
    run_id = run.get("id")
    if not isinstance(run_id, int) or isinstance(run_id, bool):
        return False
    if run.get("event") != "pull_request" or run.get("status") not in ACTIVE_STATUSES:
        return False
    branch = run.get("head_branch")
    # A run on the default branch is a merged commit's verdict, never a PR's.
    if not isinstance(branch, str) or not branch or branch == default_branch or branch != _head_of(pr)[0]:
        return False
    head_repo = run.get("head_repository")
    return isinstance(head_repo, dict) and head_repo.get("full_name") == repo


def _lists_this_pr(run, pr_number):
    # GitHub lists no PR for a run of a closed PR, so an empty list is the usual shape. Another PR's run names only that PR.
    prs = run.get("pull_requests")
    if not isinstance(prs, list):
        return False
    return not prs or any(isinstance(item, dict) and item.get("number") == pr_number for item in prs)


def select_runs(runs, pr, repo, default_branch, own_run_id=None):
    """The ids of the runs to cancel: an unfinished pull_request run of this PR's head branch, at any head SHA, from this
    repo, off the default branch, whose pull_requests list is empty or names this PR. pr is the dict GET pulls/N returns.

    The cancel job is itself an unfinished run of the closed PR, so own_run_id is never selected: it would cancel itself
    before the older runs."""
    if not isinstance(runs, list) or not head_in_repo(pr, repo):
        return []
    return [run["id"] for run in runs
            if _is_candidate(run, pr, repo, default_branch) and _lists_this_pr(run, pr.get("number"))
            and run["id"] != own_run_id]


def count_other_pr_runs(runs, pr, repo, default_branch):
    """How many runs on the PR's head branch select_runs leaves because their list names only other PRs."""
    if not isinstance(runs, list) or not head_in_repo(pr, repo):
        return 0
    return sum(1 for run in runs if _is_candidate(run, pr, repo, default_branch)
               and isinstance(run.get("pull_requests"), list) and run["pull_requests"]
               and not _lists_this_pr(run, pr.get("number")))


class ReadError(Exception):
    pass


def gh_api(args):
    try:
        return subprocess.run(["gh", "api", *args], capture_output=True, text=True, check=False)
    except OSError as e:
        raise ReadError(f"gh did not start: {e}")


def read_text(args):
    done = gh_api(args)
    if done.returncode != 0:
        raise ReadError(f"gh api {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout


def _json_lines(args):
    """One JSON value per line of a --jq filter that ends in [], across every page. --paginate alone joins page objects
    into invalid JSON."""
    items = []
    for line in read_text(args).splitlines():
        if line.strip():
            try:
                items.append(json.loads(line))
            except ValueError as e:
                raise ReadError(f"a list line is not JSON: {e}")
    return items


def read_pr(repo, pr_number):
    out = read_text(["-X", "GET", f"repos/{repo}/pulls/{pr_number}"])
    try:
        pr = json.loads(out)
    except ValueError as e:
        raise ReadError(f"the PR is not JSON: {e}")
    if not isinstance(pr, dict):
        raise ReadError("the PR read is not an object")
    return pr


def list_active_runs(repo):
    runs = []
    for status in ACTIVE_STATUSES:
        runs += _json_lines(["-X", "GET", "--paginate", f"repos/{repo}/actions/runs", "-f", f"status={status}",
                             "-f", "per_page=100", "--jq", ".workflow_runs[]"])
    return runs


def list_open_prs_on_head(repo, pr):
    owner = pr["head"]["repo"]["full_name"].split("/")[0]
    return _json_lines(["-X", "GET", "--paginate", f"repos/{repo}/pulls", "-f", "state=open",
                        "-f", f"head={owner}:{pr['head']['ref']}", "-f", "per_page=100", "--jq", ".[]"])


def main(argv):
    if len(argv) != 3 or not argv[1].isdigit() or "/" not in argv[2]:
        print("usage: cancel_closed_pr_runs.py PR_NUMBER OWNER/REPO", file=sys.stderr)
        return 2
    pr_number, repo = int(argv[1]), argv[2]
    # Read before any gh call: an unreadable id cannot be left out of the cancel, so nothing may be cancelled.
    raw_run_id = os.environ.get("GITHUB_RUN_ID", "")
    if raw_run_id and not (raw_run_id.isascii() and raw_run_id.isdigit()):
        print(f"nothing cancelled: GITHUB_RUN_ID is not a number: {raw_run_id!r}", file=sys.stderr)
        return 1
    own_run_id = int(raw_run_id) if raw_run_id else None
    try:
        pr = read_pr(repo, pr_number)
        state = pr.get("state")
        if not isinstance(state, str) or not state:
            raise ReadError("the PR state came back empty")
        if not pr_is_closed(state):
            print(f"PR {pr_number} is {state}, not closed: nothing cancelled")
            return 0
        if _head_of(pr) is None:
            raise ReadError("the PR names no head branch or head repo")
        if not head_in_repo(pr, repo):
            print(f"PR {pr_number} has its head in a fork: nothing cancelled")
            return 0
        if other_open_pr_shares_head(list_open_prs_on_head(repo, pr), pr):
            print(f"another open PR shares the head branch {pr['head']['ref']}: nothing cancelled", file=sys.stderr)
            return 0
        default_branch = read_text([f"repos/{repo}", "--jq", ".default_branch"]).strip()
        if not default_branch:
            raise ReadError("the default branch came back empty")
        runs = list_active_runs(repo)
        ids = select_runs(runs, pr, repo, default_branch, own_run_id)
        skipped = count_other_pr_runs(runs, pr, repo, default_branch)
        if skipped:
            print(f"{skipped} run(s) skipped: they name only another PR", file=sys.stderr)
        # A reopen during the list must stop the cancel, so the state is read again right before the loop.
        state = read_pr(repo, pr_number).get("state")
        if not isinstance(state, str) or not pr_is_closed(state):
            print(f"PR {pr_number} is {state or 'unreadable'}, not closed: nothing cancelled")
            return 0
    except ReadError as e:
        print(f"nothing cancelled: {e}", file=sys.stderr)
        return 1
    failed = 0
    for run_id in ids:
        done = gh_api(["-X", "POST", f"repos/{repo}/actions/runs/{run_id}/cancel"])
        # A run that finished since the list answers 409; there was nothing left to cancel.
        if done.returncode == 0 or "HTTP 409" in done.stderr:
            print(f"cancelled run {run_id}")
        else:
            failed += 1
            print(f"could not cancel run {run_id}: {done.stderr.strip()}", file=sys.stderr)
    print(f"{len(ids)} run(s) selected for PR {pr_number}, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
