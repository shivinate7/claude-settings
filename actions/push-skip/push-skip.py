#!/usr/bin/env python3
"""The push skip decision: it decides whether a push to main can skip the checks its tree already passed (decision push-skip-on-proven-tree).

This is the shared action's script (actions/push-skip/action.yml). Child repos pin the action, and this repo's checks.yml calls it.
Writes one line to $GITHUB_OUTPUT (stdout when unset): skip=true or skip=false. It exits 0 on every path, so the push-skip job
is a visible success and scope reads its output.

skip=true only when the push commit's tree equals the head tree of a pull request the push commit belongs to, and that pull request's
run passed, narrowed or full, in one of two forms. Main then runs none of its suites for that merge:
  1. a batch-* head (an integration pull request): its all-jobs-passed check run concluded success and so did every suite job.
  2. any other merged pull request head (a lone lane): its newest checks run is a completed, successful pull request run in which
     all-jobs-passed and every suite job succeeded. A suite step that scope skipped (a narrowed run) does not stop the skip: the
     suites the diff left out are not re-run on main until a later change touches them.
A suite job that the run skipped (conclusion skipped) is proven, never a gap, only when all three hold: its name is a key of the
calling workflow's all-jobs-passed scope-skips input, the same run's scope job succeeded, and the same run's all-jobs-passed
succeeded. The map is read from the caller's workflow file with the rules reader (scope_skips_map), never from testing/, since a
pinned copy of this action has no testing/. Any other skipped job is not proven.
Anything else runs everything: a direct push, an admin merge with no green run, a tree mismatch, a red, draft, cancelled or
in-progress run, a run of another head or workflow. A schedule or workflow_dispatch run (EVENT) never skips. Any error from the read,
of any type, writes skip=false and says "unknown": an unknown state runs everything, never skips.

The suite jobs are the jobs all-jobs-passed needs in the CALLING repo's workflow ($GITHUB_WORKSPACE/$WORKFLOW), minus the bookkeeping
jobs. lint/all_jobs_passed_rules.py reads them (split_jobs, the one reader), loaded from this action's own checkout, so a child repo
that pins this action by SHA gets the reader its pin carries. Nothing is copied here.

A skipped push run clears no red nightly: a push run with push-skip success and scope skipped is evidence for the push group only,
and a skipped job is never a pass (actions/ci-alarm/clear_rule.py, merge/test_merge.py).

Input (env): PUSH_TREE (the push commit's tree sha), REPO (owner/name), GH_TOKEN, HEAD_SHA (the push commit), EVENT (the event name),
GITHUB_WORKSPACE (the calling checkout; unset reads this repo), WORKFLOW (the calling workflow's path, default
.github/workflows/checks.yml). PRS_JSON is a stand-in for the read: a JSON list of integration PR heads, each {"head_branch",
"tree", "status", "conclusion"} (lint/test_push_skip.py). Cost per push: one pull request list read; per batch head its commit and
one page of its check runs; per merged lone-lane head its commit, and, only when its tree is the push's tree, one runs read and one
jobs read; plus one read of the workflow file (the suite jobs and the scope-skips map come from the same text). No file written, no process kept.
"""
import functools
import importlib.util
import json
import os
import sys
import urllib.parse

BATCH_PREFIX = "batch-"
ROLLUP = "all-jobs-passed"
DEFAULT_WORKFLOW = ".github/workflows/checks.yml"
PAGE = 100
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))  # the checkout this action came from: a pinned child repo gets claude-settings' copy
LINT = os.path.join(ROOT, "lint")
NIGHTLY_SKIP = os.path.join(ROOT, ".github", "scripts", "nightly-skip.py")


class Unknown(Exception):
    """The read could not be judged: the script says skip=false."""


@functools.lru_cache(maxsize=None)
def _nightly_skip():
    """nightly-skip.py is the one home of the API reader. Its name has a hyphen, so it loads by path."""
    spec = importlib.util.spec_from_file_location("nightly_skip", NIGHTLY_SKIP)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@functools.lru_cache(maxsize=None)
def _rules():
    """lint/all_jobs_passed_rules.py is the one reader of a workflow's jobs, loaded by path since lint/ is no package."""
    sys.path.insert(0, LINT)
    spec = importlib.util.spec_from_file_location("all_jobs_passed_rules", os.path.join(LINT, "all_jobs_passed_rules.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def workflow_path(env):
    """The calling workflow's repo-relative path, as a run's `path` names it."""
    return env.get("WORKFLOW") or DEFAULT_WORKFLOW


@functools.lru_cache(maxsize=None)
def _suite_jobs(file):
    """The jobs a passing pull request run must have succeeded in: every job all-jobs-passed needs, except the bookkeeping jobs that
    decide, skip or fan in. Unknown when the workflow cannot be read or yields no check, since an empty list would let any run stand."""
    try:
        rules = _rules()
        with open(file, encoding="utf-8") as handle:
            needed, _off, _problems = rules.split_jobs(handle.read())
        bookkeeping = {"scope", rules.ALL_JOBS_PASSED_JOB, rules.FAN_IN, rules.PUSH_SKIP_JOB, rules.NIGHTLY_SKIP_JOB}
    except Exception as ex:  # a missing file, a reader import error or a parse error all leave the suite list unknown
        raise Unknown("the suite jobs could not be read from %s (%s: %s)" % (file, type(ex).__name__, ex))
    suites = tuple(name for name in needed if name not in bookkeeping)
    if not suites:
        raise Unknown("%s yields no suite job" % file)
    return suites


def suite_jobs(env):
    """The suite jobs of the calling repo's workflow: under GITHUB_WORKSPACE, or this repo's own when that is unset."""
    return _suite_jobs(os.path.join(env.get("GITHUB_WORKSPACE") or ROOT, workflow_path(env)))


@functools.lru_cache(maxsize=None)
def _scope_skips(file):
    """The jobs the calling workflow's all-jobs-passed scope-skips input names. Unknown when the file or the reader cannot be read."""
    try:
        with open(file, encoding="utf-8") as handle:
            return frozenset(_rules().scope_skips_map(handle.read()))
    except Exception as ex:
        raise Unknown("the scope-skips map could not be read from %s (%s: %s)" % (file, type(ex).__name__, ex))


def scope_skips(env):
    """The names in the calling workflow's scope-skips input: a skipped job of one of them may be proven by its scope run."""
    return _scope_skips(os.path.join(env.get("GITHUB_WORKSPACE") or ROOT, workflow_path(env)))


def get(path, query, env):
    api = _nightly_skip()
    url = "%s/repos/%s/%s" % (api.API, env["REPO"], path)
    if query:
        url += "?" + urllib.parse.urlencode(query)
    try:
        return api.api_get(url, env["GH_TOKEN"])
    except Exception as ex:  # any read error (URLError, a cut-off http.client.IncompleteRead, bad JSON) is an unknown state
        raise Unknown("the read of %s failed (%s: %s)" % (path, type(ex).__name__, ex))


def check_runs(env, sha):
    """The check runs of `sha`: one page of every job. Unknown on a full page, since a newer run may be missing."""
    body = get("commits/%s/check-runs" % sha, {"per_page": str(PAGE)}, env)
    runs = body.get("check_runs") if isinstance(body, dict) else None
    if not isinstance(runs, list):
        raise Unknown("the check runs read has no check_runs list")
    if len(runs) >= PAGE:
        raise Unknown("the check runs read is a full page, so a newer run may be missing")
    return runs


def newest_result(runs, name):
    """(status, conclusion) of the newest check run called `name` that ran, a queued one included. A skipped one is the draft run's,
    or a job the run left out, so it is not a result. ("none", None) when no check run ran."""
    ran = [r for r in runs if isinstance(r, dict) and r.get("name") == name and r.get("conclusion") != "skipped"]
    if not ran:
        return "none", None
    # A run with no started_at is queued and not started yet, so it is the newest: an older green run must not stand for it.
    newest = max(ran, key=lambda r: str(r.get("started_at") or "￿"))
    return newest.get("status"), newest.get("conclusion")


def rollup_result(env, sha, runs=None):
    """(status, conclusion) of the newest all-jobs-passed check run on `sha`. `runs` is the head's check runs when the caller read them."""
    return newest_result(check_runs(env, sha) if runs is None else runs, ROLLUP)


def suites_not_success(runs, env):
    """The checks whose newest check run that ran is missing or did not complete with success, sorted. A check the run skipped is no
    gap when the caller's scope-skips map names it and the same head's scope check run succeeded. The caller has read the head's
    all-jobs-passed as success, which is the third condition."""
    skippable = scope_skips(env) if newest_result(runs, "scope") == ("completed", "success") else frozenset()
    return sorted(name for name in suite_jobs(env) if newest_result(runs, name) != ("completed", "success")
                  and not (name in skippable and skipped_only(runs, name)))


def skipped_only(runs, name):
    """True when `name` has a check run, and every one concluded skipped: it never ran, as opposed to missing from the run."""
    rows = [r for r in runs if isinstance(r, dict) and r.get("name") == name]
    return bool(rows) and all(r.get("conclusion") == "skipped" for r in rows)


def pull_request_run_gap(env, sha):
    """None when the newest checks run of the pull request head `sha` is a green pull request run. Else the reason it proves
    nothing. Raises Unknown on a read that cannot be judged. Green: the run, all-jobs-passed and every suite job succeeded. A step
    that scope skipped inside a succeeded job is no gap (a narrowed run)."""
    body = get("actions/runs", {"head_sha": sha, "event": "pull_request", "per_page": str(PAGE)}, env)
    page = body.get("workflow_runs") if isinstance(body, dict) else None
    if not isinstance(page, list):
        raise Unknown("the runs read has no workflow_runs list")
    if len(page) >= PAGE:
        raise Unknown("the runs read is a full page, so a newer run may be missing")
    workflow = workflow_path(env)
    mine = [r for r in page if isinstance(r, dict) and r.get("head_sha") == sha and str(r.get("path") or "").split("@")[0] == workflow]
    if not mine:
        return "no %s pull request run on the head" % workflow
    newest = max(mine, key=lambda r: (str(r.get("run_started_at") or r.get("created_at") or ""), r.get("id") or 0))
    if (newest.get("status"), newest.get("conclusion")) != ("completed", "success"):
        return "its newest run is %s/%s" % (newest.get("status"), newest.get("conclusion"))
    jobs_body = get("actions/runs/%s/jobs" % newest.get("id"), {"per_page": str(PAGE)}, env)
    jobs = jobs_body.get("jobs") if isinstance(jobs_body, dict) else None
    if not isinstance(jobs, list) or not all(isinstance(j, dict) for j in jobs):
        raise Unknown("the jobs read has no jobs list")
    if len(jobs) >= PAGE:
        raise Unknown("the jobs read is a full page, so a job may be missing")
    def conclusions(name):
        return [(j.get("status"), j.get("conclusion")) for j in jobs if j.get("name") == name]

    def succeeded(name):
        return bool(conclusions(name)) and all(c == ("completed", "success") for c in conclusions(name))

    skippable = scope_skips(env) if succeeded("scope") else frozenset()
    gaps = []
    for name in (ROLLUP,) + suite_jobs(env):
        # A suite job the run skipped is proven by the map and this run's scope job. The rollup is never skippable: it must succeed.
        proven_skip = (name in skippable and name != ROLLUP and bool(conclusions(name))
                       and all(c == ("completed", "skipped") for c in conclusions(name)))
        if not succeeded(name) and not proven_skip:
            gaps.append("%s did not succeed" % name)
    return "; ".join(gaps) if gaps else None


def read_heads(env):
    """The pull request heads that may cover the push: the stand-in when PRS_JSON is set, else the pull requests the push commit
    belongs to. Each record has its head's tree and its result: for a batch head, the all-jobs-passed result (not success when a
    check did not succeed); for a merged lone-lane head whose tree is the push's tree, a success record with full_run set (the run passed), kept only
    when its run is a green pull request run. Raises Unknown on anything that is not a list of records."""
    raw = env.get("PRS_JSON")
    if raw is not None:
        try:
            heads = json.loads(raw)
        except ValueError as ex:
            raise Unknown("PRS_JSON is not JSON (%s)" % ex)
        if not isinstance(heads, list):
            raise Unknown("PRS_JSON is not a list of pull request heads")
        return heads
    if not env.get("GH_TOKEN") or not env.get("REPO") or not env.get("HEAD_SHA"):
        raise Unknown("no PRS_JSON and no GH_TOKEN, REPO or HEAD_SHA to read pull requests with")
    prs = get("commits/%s/pulls" % env["HEAD_SHA"], {"per_page": str(PAGE)}, env)
    if not isinstance(prs, list):
        raise Unknown("the pull request read is not a list")
    if len(prs) >= PAGE:
        raise Unknown("the pull request read is a full page, so a head may be missing")
    heads = []
    for pr in prs:
        head = pr.get("head") if isinstance(pr, dict) else None
        if not isinstance(head, dict) or not head.get("sha"):
            raise Unknown("a pull request has no head sha")
        branch = head.get("ref") or ""
        batch = branch.startswith(BATCH_PREFIX)
        if not batch and not pr.get("merged_at"):
            continue  # a lone lane's pull request that was not merged is no proof for main, and its head is not read
        commit = get("git/commits/%s" % head["sha"], None, env)
        tree = (commit.get("tree") or {}).get("sha") if isinstance(commit, dict) else None
        if not tree:
            raise Unknown("the commit read of a pull request head has no tree")
        if not batch:
            if tree != env.get("PUSH_TREE"):
                continue  # another tree covers nothing, so its run is not read
            gap = pull_request_run_gap(env, head["sha"])
            if gap:
                print("push-skip: merged pull request head %s is not covered, %s" % (branch, gap))
            else:
                heads.append({"head_branch": branch, "tree": tree, "status": "completed", "conclusion": "success", "full_run": True})
            continue
        runs = check_runs(env, head["sha"])
        status, conclusion = rollup_result(env, head["sha"], runs)
        if (status, conclusion) == ("completed", "success"):
            # A job can succeed with its test steps skipped by a flag, which all-jobs-passed cannot see, so a green rollup counts only when every check also succeeded.
            missing = suites_not_success(runs, env)
            if missing:
                conclusion = "suite jobs not success: " + ", ".join(missing)
                print("push-skip: batch head %s is not covered, %s" % (branch, conclusion))
        heads.append({"head_branch": branch, "tree": tree, "status": status, "conclusion": conclusion})
    return heads


def decide(heads, push_tree):
    """True when the push can skip. `heads` is a list of pull request head records: a batch head, or a lone lane's head with full_run."""
    if not all(isinstance(h, dict) for h in heads):
        raise Unknown("a pull request head record is not an object")
    if not push_tree:
        raise Unknown("no PUSH_TREE, so the push commit's tree cannot be compared")
    return any((str(h.get("head_branch") or "").startswith(BATCH_PREFIX) or h.get("full_run") is True) and h.get("tree") == push_tree
               and h.get("status") == "completed" and h.get("conclusion") == "success" for h in heads)


def main(env=None):
    env = os.environ if env is None else env
    try:
        event = env.get("EVENT") or "push"
        if event != "push":
            skip = False  # only a push skips: a schedule or manual run is the check on what a pull request run scoped out
            print("push-skip: a %s run never skips" % event)
        else:
            skip = decide(read_heads(env), env.get("PUSH_TREE"))
            print("push-skip: skip=%s" % str(skip).lower())
    except Exception as ex:  # Unknown, or a record shape the reads did not expect: either way the push runs everything and the job stays green
        skip = False
        print("push-skip: unknown (%s), so the push runs everything" % ex)
    line = "skip=%s\n" % str(skip).lower()
    out = env.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(line)
    else:
        sys.stdout.write(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
