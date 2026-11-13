#!/usr/bin/env python3
"""Cancels the CI runs of a pull request that was closed, for .github/workflows/cancel-on-close.yml.

Usage: cancel_closed_pr_runs.py PR_NUMBER OWNER/REPO      (env: GH_TOKEN, read by the gh CLI)

It re-reads the PR from the API instead of trusting the event, lists the repo's runs that have not finished, and cancels
each one select_runs picks. It fails safe: a PR that is not closed, a read it cannot parse or a gh call that fails cancels
nothing, and an unreadable input exits non-zero so the run shows red. Stdlib only.
"""
import json
import subprocess
import sys

# The run statuses GitHub lists as not finished. A completed run has nothing left to cancel.
ACTIVE_STATUSES = ("queued", "in_progress", "waiting", "pending")


def pr_is_closed(state):
    return state == "closed"


def _lists_pr(run, pr_number):
    prs = run.get("pull_requests")
    if not isinstance(prs, list):
        return False
    return any(isinstance(pr, dict) and pr.get("number") == pr_number for pr in prs)


def _is_cancellable(run, pr_number, repo, default_branch):
    if not isinstance(run, dict):
        return False
    run_id = run.get("id")
    if not isinstance(run_id, int) or isinstance(run_id, bool):
        return False
    if run.get("event") != "pull_request" or run.get("status") not in ACTIVE_STATUSES:
        return False
    branch = run.get("head_branch")
    # A run on the default branch is a merged commit's verdict, never a PR's.
    if not isinstance(branch, str) or not branch or branch == default_branch:
        return False
    # A fork's run belongs to the fork's author, and a run's pull_requests list names only PRs whose head is in this repo.
    head_repo = run.get("head_repository")
    if not isinstance(head_repo, dict) or head_repo.get("full_name") != repo:
        return False
    return _lists_pr(run, pr_number)


def select_runs(runs, pr_number, repo, default_branch):
    """The ids of the runs to cancel: an unfinished pull_request run of this PR, from this repo, off the default branch."""
    if not isinstance(runs, list):
        return []
    return [run["id"] for run in runs if _is_cancellable(run, pr_number, repo, default_branch)]


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


def list_active_runs(repo):
    runs = []
    for status in ACTIVE_STATUSES:
        # --jq prints one run per line across every page, where --paginate alone joins page objects into invalid JSON.
        out = read_text(["--paginate", f"repos/{repo}/actions/runs", "-f", f"status={status}", "-f", "per_page=100",
                         "--jq", ".workflow_runs[]"])
        for line in out.splitlines():
            if line.strip():
                try:
                    runs.append(json.loads(line))
                except ValueError as e:
                    raise ReadError(f"a run list line is not JSON: {e}")
    return runs


def main(argv):
    if len(argv) != 3 or not argv[1].isdigit() or "/" not in argv[2]:
        print("usage: cancel_closed_pr_runs.py PR_NUMBER OWNER/REPO", file=sys.stderr)
        return 2
    pr_number, repo = int(argv[1]), argv[2]
    try:
        state = read_text([f"repos/{repo}/pulls/{pr_number}", "--jq", ".state"]).strip()
        if not state:
            raise ReadError("the PR state came back empty")
        if not pr_is_closed(state):
            print(f"PR {pr_number} is {state}, not closed: nothing cancelled")
            return 0
        default_branch = read_text([f"repos/{repo}", "--jq", ".default_branch"]).strip()
        if not default_branch:
            raise ReadError("the default branch came back empty")
        ids = select_runs(list_active_runs(repo), pr_number, repo, default_branch)
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
