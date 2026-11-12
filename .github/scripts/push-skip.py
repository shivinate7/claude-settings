#!/usr/bin/env python3
"""The push skip decision: it decides whether a push to main can skip the checks its tree already passed (R62, step ci-linux-windows-once).

Writes one line to $GITHUB_OUTPUT (stdout when unset): skip=true or skip=false. It exits 0 on every path, so the push-skip job
is a visible success and scope reads its output.

skip=true only when the push commit's tree equals the tree of a batch-* pull request head whose all-jobs-passed check run
concluded success. A batch pull request is ready, and its ready run carries every job, the Windows full shards included, so
that run proved this tree. Any read failure writes skip=false and says "unknown": an unknown state runs everything, never skips.

The result is read from the head's all-jobs-passed check run, not from the checks.yml run's own conclusion: a draft run skips every
job and concludes success, and it must not stand for the ready run. A skipped check run (the draft run's) is not a result.

Input (env): PUSH_TREE (the push commit's tree sha), REPO (owner/name), GH_TOKEN, HEAD_SHA (the push commit). PRS_JSON is a stand-in
for the read: a JSON list of batch pull request heads, each {"head_branch", "tree", "status", "conclusion"}
(lint/test_push_skip.py). Cost: one pull request list read, then per batch head its commit and its check runs; no file, no process kept.
"""
import functools
import importlib.util
import json
import os
import sys
import urllib.error
import urllib.parse

BATCH_PREFIX = "batch-"
ROLLUP = "all-jobs-passed"
PAGE = 100
HERE = os.path.dirname(os.path.abspath(__file__))


class Unknown(Exception):
    """The read could not be judged: the script says skip=false."""


@functools.lru_cache(maxsize=None)
def _nightly_skip():
    """nightly-skip.py is the one home of the API reader. Its name has a hyphen, so it loads by path."""
    spec = importlib.util.spec_from_file_location("nightly_skip", os.path.join(HERE, "nightly-skip.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def get(path, query, env):
    api = _nightly_skip()
    url = "%s/repos/%s/%s" % (api.API, env["REPO"], path)
    if query:
        url += "?" + urllib.parse.urlencode(query)
    try:
        return api.api_get(url, env["GH_TOKEN"])
    except (urllib.error.URLError, OSError, ValueError) as ex:
        raise Unknown("the read of %s failed (%s)" % (path, ex))


def rollup_result(env, sha):
    """(status, conclusion) of the newest all-jobs-passed check run on `sha` that ran. A skipped one is the draft run's, so it is
    not a result. (\"none\", None) when no check run ran."""
    body = get("commits/%s/check-runs" % sha, {"check_name": ROLLUP, "per_page": str(PAGE)}, env)
    runs = body.get("check_runs") if isinstance(body, dict) else None
    if not isinstance(runs, list):
        raise Unknown("the check runs read has no check_runs list")
    if len(runs) >= PAGE:
        raise Unknown("the check runs read is a full page, so a newer run may be missing")
    ran = [r for r in runs if isinstance(r, dict) and r.get("conclusion") != "skipped"]
    if not ran:
        return "none", None
    newest = max(ran, key=lambda r: str(r.get("started_at") or ""))
    return newest.get("status"), newest.get("conclusion")


def read_heads(env):
    """The batch pull request heads: the stand-in when PRS_JSON is set, else the pull requests the push commit belongs to, each
    with its head's tree and its all-jobs-passed result. Raises Unknown on anything that is not a list of records."""
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
        status, conclusion = rollup_result(env, head["sha"])
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
    except Unknown as ex:
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
