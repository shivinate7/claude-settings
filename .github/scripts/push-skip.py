#!/usr/bin/env python3
"""The push skip decision: it decides whether a push to main can skip the checks its tree already passed (R62, step ci-linux-windows-once).

Writes one line to $GITHUB_OUTPUT (stdout when unset): skip=true or skip=false. It exits 0 on every path, so the push-skip job
is a visible success and scope reads its output.

skip=true only when the push commit's tree equals the tree of an integration PR head (a batch-* branch) whose all-jobs-passed check
run concluded success and whose every check concluded success. An integration PR is ready, and its ready run runs the Windows
guard, merge and rest jobs in full, and ci-scope.sh sets every scope flag on for a ready pull request from a batch-* branch, so that
run is the all-flags run: no job or suite skipped on the PR head's diff. Any error from the read, of any type, writes skip=false and
says "unknown": an unknown state runs everything, never skips.

The result is read from the head's check runs, not from the checks.yml run's own conclusion: a draft run skips every job and
concludes success, and it must not stand for the ready run. A skipped check run (the draft run's) is not a result. all-jobs-passed
fails on a skipped needed job, but a job can succeed while a flag skipped the test steps inside it. The job conclusion hides that, and
the only guard is the all-flags arm in ci-scope.sh. So all-jobs-passed is not enough alone: a reused run counts for a suite only if that
suite's job ran and concluded success on that tree. The checks are the jobs all-jobs-passed needs, minus the bookkeeping jobs. They are
derived from checks.yml by lint/all_jobs_passed_rules.py (split_jobs, the one reader), never copied here. The head record's conclusion
is success only when both hold. Else it names the checks that did not succeed, or holds the raw conclusion when all-jobs-passed itself failed or is missing.

Input (env): PUSH_TREE (the push commit's tree sha), REPO (owner/name), GH_TOKEN, HEAD_SHA (the push commit). PRS_JSON is a stand-in
for the read: a JSON list of integration PR heads, each {"head_branch", "tree", "status", "conclusion"}
(lint/test_push_skip.py). Cost: one pull request list read, then per integration PR head its commit and one page of its check runs
(every job, up to 100), plus one read of checks.yml; no file written, no process kept.
"""
import functools
import importlib.util
import json
import os
import sys
import urllib.parse

BATCH_PREFIX = "batch-"
ROLLUP = "all-jobs-passed"
PAGE = 100
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CHECKS = os.path.join(ROOT, ".github", "workflows", "checks.yml")
LINT = os.path.join(ROOT, "lint")


class Unknown(Exception):
    """The read could not be judged: the script says skip=false."""


@functools.lru_cache(maxsize=None)
def _nightly_skip():
    """nightly-skip.py is the one home of the API reader. Its name has a hyphen, so it loads by path."""
    spec = importlib.util.spec_from_file_location("nightly_skip", os.path.join(HERE, "nightly-skip.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@functools.lru_cache(maxsize=None)
def suite_jobs():
    """The jobs a ready integration PR run must have run its tests in: every job all-jobs-passed needs, except the bookkeeping jobs that
    decide, skip or fan in. lint/all_jobs_passed_rules.py is the one reader of checks.yml, loaded by path since lint/ is no package.
    Unknown when checks.yml cannot be read or yields no check, since an empty list would let any run stand."""
    sys.path.insert(0, LINT)
    try:
        spec = importlib.util.spec_from_file_location("all_jobs_passed_rules", os.path.join(LINT, "all_jobs_passed_rules.py"))
        rules = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rules)
        with open(CHECKS, encoding="utf-8") as handle:
            needed, _off, _problems = rules.split_jobs(handle.read())
    except Exception as ex:  # a missing file, a reader import error or a parse error all leave the suite list unknown
        raise Unknown("the suite jobs could not be read from checks.yml (%s: %s)" % (type(ex).__name__, ex))
    bookkeeping = {"scope", rules.ALL_JOBS_PASSED_JOB, rules.FAN_IN, rules.PUSH_SKIP_JOB, rules.NIGHTLY_SKIP_JOB}
    suites = tuple(name for name in needed if name not in bookkeeping)
    if not suites:
        raise Unknown("checks.yml yields no suite job")
    return suites


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
    newest = max(ran, key=lambda r: str(r.get("started_at") or "\uffff"))
    return newest.get("status"), newest.get("conclusion")


def rollup_result(env, sha, runs=None):
    """(status, conclusion) of the newest all-jobs-passed check run on `sha`. `runs` is the head's check runs when the caller read them."""
    return newest_result(check_runs(env, sha) if runs is None else runs, ROLLUP)


def suites_not_success(runs):
    """The checks whose newest check run that ran is missing or did not complete with success, sorted."""
    return sorted(name for name in suite_jobs() if newest_result(runs, name) != ("completed", "success"))


def read_heads(env):
    """The batch pull request heads: the stand-in when PRS_JSON is set, else the pull requests the push commit belongs to, each
    with its head's tree and its result: the all-jobs-passed result, not success when a check did not succeed. Raises Unknown on anything that is not a list of records."""
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
        raise Unknown("the pull request read is a full page, so a batch head may be missing")
    heads = []
    for pr in prs:
        head = pr.get("head") if isinstance(pr, dict) else None
        if not isinstance(head, dict) or not head.get("sha"):
            raise Unknown("a pull request has no head sha")
        branch = head.get("ref") or ""
        if not branch.startswith(BATCH_PREFIX):
            continue  # only a batch head is read: the other reads would not change the answer
        commit = get("git/commits/%s" % head["sha"], None, env)
        tree = (commit.get("tree") or {}).get("sha") if isinstance(commit, dict) else None
        if not tree:
            raise Unknown("the commit read of a batch head has no tree")
        runs = check_runs(env, head["sha"])
        status, conclusion = rollup_result(env, head["sha"], runs)
        if (status, conclusion) == ("completed", "success"):
            # A job can succeed with its test steps skipped by a flag, which all-jobs-passed cannot see, so a green rollup counts only when every check also succeeded.
            missing = suites_not_success(runs)
            if missing:
                conclusion = "suite jobs not success: " + ", ".join(missing)
                print("push-skip: batch head %s is not covered, %s" % (branch, conclusion))
        heads.append({"head_branch": branch, "tree": tree, "status": status, "conclusion": conclusion})
    return heads


def decide(heads, push_tree):
    """True when the push can skip. `heads` is a list of batch pull request head records."""
    if not all(isinstance(h, dict) for h in heads):
        raise Unknown("a pull request head record is not an object")
    if not push_tree:
        raise Unknown("no PUSH_TREE, so the push commit's tree cannot be compared")
    return any(str(h.get("head_branch") or "").startswith(BATCH_PREFIX) and h.get("tree") == push_tree
               and h.get("status") == "completed" and h.get("conclusion") == "success" for h in heads)


def main(env=None):
    env = os.environ if env is None else env
    try:
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
