#!/usr/bin/env python3
"""Tests for the push skip decision, which lets a push to main skip the checks its tree already passed.

The decision's one home is the shared action actions/push-skip (push-skip.py beside its action.yml). Child repos pin that action,
and this repo's checks.yml calls it. Until the lift moves the script, the copy at .github/scripts/push-skip.py answers.

The contract these cases pin. A change to any of it changes these cases first.
- Env in: PUSH_TREE (the push commit's tree), HEAD_SHA (the push commit), REPO, GH_TOKEN, GITHUB_OUTPUT. EVENT is the event name,
  as ci-scope.sh reads it: a schedule or workflow_dispatch run never skips. GITHUB_WORKSPACE is the calling checkout; the suite
  list is read from its .github/workflows/checks.yml, and unset means this repo, as before.
- Reads: commits/<sha>/pulls (the pull requests the push commit belongs to); git/commits/<head> (the head's tree);
  commits/<head>/check-runs (a batch-* head only: its all-jobs-passed run and its suite runs); actions/runs?head_sha&event
  (the checks.yml runs of a merged pull request head that is not a batch head); actions/runs/<id>/jobs (its jobs, with steps).
- skip=true when the push tree equals the tree of a batch-* head whose ready run passed every suite job, or of a merged pull
  request head whose newest checks.yml run is a green pull request run: all-jobs-passed and every suite job succeeded. A suite step
  that scope skipped does not stop the skip: after a passing PR run, narrowed or full, main runs none of its suites for that merge.
- Any read error, unknown state or unreadable record writes skip=false and says "unknown".

The stand-in PRS_JSON, a JSON list of batch heads, is read by the older cases. The live cases answer the reads through FakeGitHub,
by URL, as the API does. A ready batch head skips only when every suite job of checks.yml succeeded on its ready run, not only
when all-jobs-passed passed.

    python3 lint/test_push_skip.py
"""
import contextlib
import http.client
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import unittest
import urllib.parse
import uuid
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _test_temp  # noqa: E402  test-temp-standard: every temp path comes from this run's folder
from test_windows_split import ALL_JOBS_PASSED_JOB, CHECKS, NIGHTLY_SKIP_JOB, PUSH_SKIP_JOB, all_jobs, eval_if  # noqa: E402  the one home of the checks.yml reader
from all_jobs_passed_rules import FAN_IN, needs_of, split_jobs  # noqa: E402  the one home of the needs reader
from workflow_steps import job_block, step_blocks, step_key  # noqa: E402  the one home of the job parser
import test_all_jobs_passed as all_jobs_home  # noqa: E402  the one home of the child workflow fixtures (CHILD_GOOD)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ACTION_SCRIPT = os.path.join(ROOT, "actions", "push-skip", "push-skip.py")
LEGACY_SCRIPT = os.path.join(ROOT, ".github", "scripts", "push-skip.py")
PUSH_SKIP = ACTION_SCRIPT if os.path.isfile(ACTION_SCRIPT) else LEGACY_SCRIPT  # the one home; a tree that has not moved it yet answers from the legacy copy
RUN_FOLDER = _test_temp.run_folder()  # one run folder per test run; teardown removes it

JOB = "push-skip"
REPO = "owner/repo"
TREE = "a" * 40  # the push commit's tree
OTHER_TREE = "b" * 40
BATCH = "batch-lane-x"
RUN_PATH = ".github/workflows/checks.yml"
OTHER_PATH = ".github/workflows/other.yml"
SCRIPT_MISSING = "push-skip.py is missing at actions/push-skip/push-skip.py and at .github/scripts/push-skip.py, so no decision sets the push skip"

# The suite jobs: the jobs a ready pull request run is meant to run, read from checks.yml by the one reader (split_jobs, whose
# needed list is all-jobs-passed's needs). Bookkeeping is not a suite: scope decides, push-skip and nightly-skip never run on a
# pull request, and all-jobs-passed and ci-done are the fan-in. A new suite job in checks.yml is in SUITE_JOBS with no edit here.
with open(CHECKS, encoding="utf-8") as _handle:
    CHECKS_TEXT = _handle.read()
NEEDED_JOBS, OFF_ON_PR, _SPLIT_PROBLEMS = split_jobs(CHECKS_TEXT)
BOOKKEEPING = {"scope", ALL_JOBS_PASSED_JOB, FAN_IN, PUSH_SKIP_JOB, NIGHTLY_SKIP_JOB}
SUITE_JOBS = sorted(name for name in NEEDED_JOBS if name not in BOOKKEEPING)
ALL_RUN_JOBS = sorted(all_jobs(CHECKS_TEXT))  # every job of checks.yml is one check run on a pull request run


def pr(tree=TREE, branch=BATCH, conclusion="success", status="completed"):
    """One batch pull request head in the shape the stand-in read carries."""
    return {"head_branch": branch, "tree": tree, "status": status, "conclusion": conclusion}


def decide(prs=None, raw=None, tree=TREE, token=None):
    """Run the script once on the stand-ins. Returns (exit code, the one skip value or None, printed text)."""
    out = os.path.join(RUN_FOLDER, "output-%s" % uuid.uuid4().hex)
    env = {k: v for k, v in os.environ.items() if k not in ("PUSH_TREE", "PRS_JSON", "GH_TOKEN", "REPO", "GITHUB_OUTPUT")}
    env["GITHUB_OUTPUT"] = out
    env["REPO"] = "owner/repo"
    if tree is not None:
        env["PUSH_TREE"] = tree
    if raw is not None:
        env["PRS_JSON"] = raw
    elif prs is not None:
        env["PRS_JSON"] = json.dumps(prs)
    if token is not None:
        env["GH_TOKEN"] = token
    done = subprocess.run([sys.executable, PUSH_SKIP], env=env, capture_output=True, text=True, timeout=60)
    skips = []
    if os.path.isfile(out):
        with open(out, encoding="utf-8") as f:
            skips = [line.strip()[len("skip="):] for line in f if line.startswith("skip=")]
    value = skips[0] if len(skips) == 1 else None
    return done.returncode, value, done.stdout + done.stderr


class PushSkipDecision(unittest.TestCase):
    def skip_value(self, **kwargs):
        self.assertTrue(os.path.isfile(PUSH_SKIP), SCRIPT_MISSING)
        rc, value, text = decide(**kwargs)
        self.assertEqual(rc, 0, "the script exits %d, so the push job fails on the decision: %s" % (rc, text[-300:]))
        return value, text

    def test_skip_true_when_the_push_tree_equals_a_green_batch_pull_request_head(self):
        value, _ = self.skip_value(prs=[pr()])
        self.assertEqual(value, "true", "a batch head with the push's tree and a green run must give skip=true")

    def test_skip_false_when_the_tree_differs(self):
        value, _ = self.skip_value(prs=[pr(tree=OTHER_TREE)])
        self.assertEqual(value, "false", "a batch head with another tree does not cover the push, so skip=false")

    def test_skip_false_when_the_matching_batch_run_failed(self):
        value, _ = self.skip_value(prs=[pr(conclusion="failure")])
        self.assertEqual(value, "false", "a red batch run with the push's tree must give skip=false")

    def test_skip_false_when_the_matching_batch_run_is_in_progress(self):
        value, _ = self.skip_value(prs=[pr(status="in_progress", conclusion=None)])
        self.assertEqual(value, "false", "an in-progress batch run is not a green run yet, so skip=false")

    def test_skip_false_when_the_matching_head_is_not_an_integration_branch(self):
        value, _ = self.skip_value(prs=[pr(branch="lane-x")])
        self.assertEqual(value, "false", "a lone lane's head is not a batch head, so skip=false")

    def test_skip_false_on_an_empty_pull_request_list(self):
        value, _ = self.skip_value(prs=[])
        self.assertEqual(value, "false", "an empty list has no batch head with the push's tree, so skip=false")

    def test_skip_true_in_a_full_size_list_that_holds_the_matching_green_head(self):
        full = [pr(tree=OTHER_TREE) for _ in range(99)] + [pr()]
        value, _ = self.skip_value(prs=full)
        self.assertEqual(value, "true", "a hundred-head list that holds the matching green head must give skip=true")

    def test_skip_false_in_a_full_size_list_with_no_matching_head(self):
        full = [pr(tree=OTHER_TREE) for _ in range(100)]
        value, _ = self.skip_value(prs=full)
        self.assertEqual(value, "false", "a hundred-head list with no matching tree must give skip=false")

    def test_a_read_that_is_not_json_gives_skip_false_and_says_unknown(self):
        value, text = self.skip_value(raw="not json")
        self.assertEqual(value, "false", "a read that fails must give skip=false")
        self.assertIn("unknown", text.lower(), "a read that fails must say unknown")

    def test_no_push_tree_gives_skip_false_and_says_unknown(self):
        value, text = self.skip_value(prs=[pr()], tree=None)
        self.assertEqual(value, "false", "without the push's tree the script cannot compare, so skip=false")
        self.assertIn("unknown", text.lower(), "without the push's tree the script must say unknown")

    def test_no_stand_in_and_no_token_gives_skip_false_and_says_unknown(self):
        value, text = self.skip_value(token=None)
        self.assertEqual(value, "false", "with no pull request read and no token the script must give skip=false")
        self.assertIn("unknown", text.lower(), "with no pull request read and no token the script must say unknown")


SHA = "c" * 40  # the push commit
HEAD = "d" * 40  # a batch head
LANE_HEAD = "e" * 40  # a lone lane's head, which the read must never touch
ROLLUP_NAME = "all-jobs-passed"
EARLY = "2026-11-12T10:00:00Z"
LATE = "2026-11-12T11:00:00Z"


def load_script():
    """The script as a module. Importing it makes no read: the read is a function the case replaces."""
    spec = importlib.util.spec_from_file_location("push_skip_under_test", PUSH_SKIP)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_run(conclusion="success", status="completed", started_at=EARLY, name=ROLLUP_NAME):
    """One check run in the shape the GitHub read returns: all-jobs-passed by default, or the job `name` of a suite."""
    return {"name": name, "status": status, "conclusion": conclusion, "started_at": started_at}


def ready_head_runs(changes=None, extra=()):
    """The check runs of a ready batch head, one per job of checks.yml, as GitHub lists them: every job succeeded, and the jobs that
    never run on a pull request are skipped. `changes` maps a job name to the check_run keyword arguments it gets instead, or to None
    to leave that job's run out. `extra` adds runs of the same names, such as a re-run."""
    runs = {name: check_run(name=name, conclusion="skipped" if name in OFF_ON_PR else "success") for name in ALL_RUN_JOBS}
    for name, change in (changes or {}).items():
        if change is None:
            runs.pop(name, None)
        else:
            runs[name] = check_run(name=name, **change)
    return list(runs.values()) + list(extra)


class FakeGitHub:
    """The GitHub reads push-skip makes, answered by URL the way the API answers them. The batch head's pull request list, commit and
    check runs are the defaults. `pulls` is the list the push commit's pull request read returns, `trees` maps a head sha to its tree,
    `workflow_runs` are the runs of the repo (filtered by head_sha and event when the read names them) and `jobs` maps a run id to its
    jobs. check_name filters the check runs; per_page (default 30) and page cut every list. `fail` is raised by every check-runs read,
    `runs_fail` by the runs read and `jobs_fail` by the jobs read. `ignore_run_filters` returns every run whatever head_sha and event
    the runs read names, as a read that answers wider than it was asked does, so the decision's own check of the head and the event
    must hold alone. A URL no case expects goes to `unexpected`, which the case asserts empty; `reads` keeps every path asked, in order."""

    def __init__(self, runs=(), fail=None, pulls=None, trees=None, workflow_runs=None, jobs=None, runs_fail=None, jobs_fail=None,
                 ignore_run_filters=False):
        self.runs = list(runs or [])
        self.fail = fail
        self.pulls = [{"head": {"ref": BATCH, "sha": HEAD}}] if pulls is None else pulls
        self.trees = {HEAD: TREE} if trees is None else trees
        self.workflow_runs = [] if workflow_runs is None else workflow_runs
        self.jobs = {} if jobs is None else jobs
        self.runs_fail, self.jobs_fail = runs_fail, jobs_fail
        self.ignore_run_filters = ignore_run_filters
        self.unexpected, self.reads = [], []

    @staticmethod
    def page(items, query):
        per_page = int(query.get("per_page", ["30"])[0])
        page = int(query.get("page", ["1"])[0])
        return items[(page - 1) * per_page:page * per_page]

    def __call__(self, url, token):
        parts = urllib.parse.urlsplit(url)
        prefix = "/repos/%s/" % REPO
        path = parts.path[len(prefix):] if parts.path.startswith(prefix) else parts.path
        query = urllib.parse.parse_qs(parts.query)
        self.reads.append(path)
        if path == "commits/%s/pulls" % SHA:
            return self.pulls
        if path.startswith("git/commits/") and path[len("git/commits/"):] in self.trees:
            return {"tree": {"sha": self.trees[path[len("git/commits/"):]]}}
        if path == "commits/%s/check-runs" % HEAD:
            if self.fail is not None:
                raise self.fail
            runs = self.runs
            if "check_name" in query:
                runs = [run for run in runs if run["name"] == query["check_name"][0]]
            return {"check_runs": self.page(runs, query)}
        if path == "actions/runs":
            if self.runs_fail is not None:
                raise self.runs_fail
            runs = [r for r in self.workflow_runs
                    if self.ignore_run_filters
                    or (("head_sha" not in query or r["head_sha"] == query["head_sha"][0])
                        and ("event" not in query or r["event"] == query["event"][0]))]
            return {"total_count": len(runs), "workflow_runs": self.page(runs, query)}
        if path.startswith("actions/runs/") and path.endswith("/jobs"):
            if self.jobs_fail is not None:
                raise self.jobs_fail
            run_id = int(path[len("actions/runs/"):-len("/jobs")])
            jobs = self.jobs.get(run_id, [])
            return {"total_count": len(jobs), "jobs": self.page(jobs, query)}
        self.unexpected.append(path)
        return {}


class LiveHead(unittest.TestCase):
    """main() on the live reads, each answered by FakeGitHub: no network, no stand-in. Returns the one skip value written and the text
    printed."""

    def skip_on(self, runs=None, fake=None, extra_env=None):
        self.assertTrue(os.path.isfile(PUSH_SKIP), SCRIPT_MISSING)
        module = load_script()
        fake = fake if fake is not None else FakeGitHub(runs)
        out = os.path.join(RUN_FOLDER, "output-%s" % uuid.uuid4().hex)
        env = {"GH_TOKEN": "t", "REPO": REPO, "HEAD_SHA": SHA, "PUSH_TREE": TREE, "GITHUB_OUTPUT": out, **(extra_env or {})}
        printed = io.StringIO()
        with mock.patch.object(module._nightly_skip(), "api_get", side_effect=fake), contextlib.redirect_stdout(printed):
            code = module.main(env)
        self.assertEqual(fake.unexpected, [], "the script read a path no case expects, so the case cannot judge it")
        self.assertEqual(code, 0, "main exits %d, so the push job fails on the decision" % code)
        skips = []
        if os.path.isfile(out):
            with open(out, encoding="utf-8") as f:
                skips = [line.strip()[len("skip="):] for line in f if line.startswith("skip=")]
        self.assertEqual(len(skips), 1, "one skip line must be written, got %s" % skips)
        return skips[0], printed.getvalue()


class ReadStub:
    """Stands in for the script's GitHub read. It answers by path and records each path it is asked."""

    def __init__(self, answers):
        self.answers = answers
        self.asked = []

    def __call__(self, path, query, env):
        self.asked.append(path)
        if path not in self.answers:
            raise AssertionError("the script read a path no case expects: %s" % path)
        return self.answers[path]


class RollupResult(unittest.TestCase):
    def rollup(self, runs):
        self.assertTrue(os.path.isfile(PUSH_SKIP), SCRIPT_MISSING)
        module = load_script()
        path = "commits/%s/check-runs" % SHA
        module.get = ReadStub({path: {"check_runs": runs}})
        result = module.rollup_result({"REPO": "owner/repo", "GH_TOKEN": "t"}, SHA)
        self.assertEqual(module.get.asked, [path], "rollup_result read a path other than the head's check runs")
        return result

    def test_a_skipped_draft_run_is_not_a_result(self):
        result = self.rollup([check_run(conclusion="skipped", started_at=LATE), check_run(started_at=EARLY)])
        self.assertEqual(result, ("completed", "success"), "a skipped check run is the draft run's, so the older green ready run must stand")

    def test_the_newest_started_run_is_the_result_in_either_list_order(self):
        runs = [check_run(conclusion="failure", started_at=LATE), check_run(started_at=EARLY)]
        self.assertEqual(self.rollup(runs), ("completed", "failure"), "the newer failed run must be the result when it is first in the list")
        self.assertEqual(self.rollup(list(reversed(runs))), ("completed", "failure"),
                         "the newer failed run must be the result when it is last in the list")

    def test_a_newest_cancelled_run_is_the_result_and_is_not_green(self):
        result = self.rollup([check_run(conclusion="cancelled", started_at=LATE), check_run(started_at=EARLY)])
        self.assertEqual(result, ("completed", "cancelled"), "a newer cancelled run must be the result, so an older green run cannot stand for it")

    def test_a_queued_run_with_no_started_at_does_not_lose_to_an_older_green_run(self):
        result = self.rollup([check_run(conclusion=None, status="queued", started_at=None), check_run(started_at=EARLY)])
        self.assertNotEqual(result, ("completed", "success"),
                            "a queued run with no started_at lost to an older green run, so a push could skip on a run still in progress")

    def test_no_check_run_gives_none(self):
        self.assertEqual(self.rollup([]), ("none", None), "a head with no all-jobs-passed run must read as none")

    def test_a_full_page_of_check_runs_is_unknown(self):
        module = load_script()
        module.get = ReadStub({"commits/%s/check-runs" % SHA: {"check_runs": [check_run() for _ in range(100)]}})
        with self.assertRaises(module.Unknown):
            module.rollup_result({"REPO": "owner/repo", "GH_TOKEN": "t"}, SHA)


class ReadHeads(unittest.TestCase):
    def github_answers(self, runs):
        # The head's suite runs are green here, so the all-jobs-passed runs given decide the read alone (the suite read is in SuiteRunsOfTheHead).
        suites = [check_run(name=name) for name in SUITE_JOBS]
        return {
            "commits/%s/pulls" % SHA: [{"head": {"ref": BATCH, "sha": HEAD}}, {"head": {"ref": "lane-y", "sha": LANE_HEAD}}],
            "git/commits/%s" % HEAD: {"tree": {"sha": TREE}},
            "commits/%s/check-runs" % HEAD: {"check_runs": list(runs) + suites},
        }

    def read(self, answers):
        module = load_script()
        stub = ReadStub(answers)
        module.get = stub
        heads = module.read_heads({"GH_TOKEN": "t", "REPO": "owner/repo", "HEAD_SHA": SHA})
        return heads, stub.asked

    def test_the_github_read_keeps_only_batch_heads_and_their_newest_result(self):
        heads, asked = self.read(self.github_answers([check_run(conclusion="skipped", started_at=LATE), check_run(started_at=EARLY)]))
        self.assertNotIn("git/commits/%s" % LANE_HEAD, asked, "a lone lane's head was read, so the read is wider than the batch heads")
        self.assertEqual(heads, [{"head_branch": BATCH, "tree": TREE, "status": "completed", "conclusion": "success"}],
                         "the batch head must carry its tree and its newest all-jobs-passed result")

    def test_a_queued_batch_head_is_not_read_as_green(self):
        heads, _ = self.read(self.github_answers([check_run(conclusion=None, status="queued", started_at=None), check_run(started_at=EARLY)]))
        self.assertEqual(len(heads), 1, "the one batch head must be in the read")
        self.assertNotEqual((heads[0]["status"], heads[0]["conclusion"]), ("completed", "success"),
                            "a queued run with no started_at lost to an older green run, so the batch head reads green")

    def test_a_full_page_of_pull_requests_is_unknown(self):
        module = load_script()
        module.get = ReadStub({"commits/%s/pulls" % SHA: [{"head": {"ref": "lane-y", "sha": LANE_HEAD}} for _ in range(100)]})
        with self.assertRaises(module.Unknown):
            module.read_heads({"GH_TOKEN": "t", "REPO": "owner/repo", "HEAD_SHA": SHA})

    def test_prs_json_that_is_not_a_list_is_unknown(self):
        module = load_script()
        with self.assertRaises(module.Unknown):
            module.read_heads({"PRS_JSON": '{"head_branch": "%s"}' % BATCH})

    def test_prs_json_that_is_not_json_is_unknown(self):
        module = load_script()
        with self.assertRaises(module.Unknown):
            module.read_heads({"PRS_JSON": "not json"})


class LiveReadErrors(unittest.TestCase):
    """An error from the live GitHub read, other than the script's own Unknown, writes skip=false and exits 0, so the push runs
    everything. Each case replaces the network call (api_get in nightly-skip.py); none reaches GitHub."""

    def live_decision(self, answer):
        """main() on the live read, with `answer` standing for the network call. -> (exit code, skip lines written, printed text)."""
        module = load_script()
        out = os.path.join(RUN_FOLDER, "output-%s" % uuid.uuid4().hex)
        env = {"GH_TOKEN": "t", "REPO": "owner/repo", "HEAD_SHA": SHA, "GITHUB_OUTPUT": out}
        printed = io.StringIO()
        crash = None
        with mock.patch.object(module._nightly_skip(), "api_get", side_effect=answer), contextlib.redirect_stdout(printed):
            try:
                code = module.main(env)
            except Exception as ex:  # a crash out of main is the named failure, not a decision
                crash = ex
        if crash is not None:
            self.fail("the live read let %s out of push-skip, so no skip=false was written: %s" % (type(crash).__name__, crash))
        skips = []
        if os.path.isfile(out):
            with open(out, encoding="utf-8") as f:
                skips = [line.strip() for line in f if line.startswith("skip=")]
        return code, skips, printed.getvalue()

    # Named failure: an incomplete read escapes the read's except list, so push-skip writes no decision and the push job fails.
    def test_an_incomplete_read_on_the_first_call_writes_skip_false_and_exits_zero(self):
        code, skips, text = self.live_decision(http.client.IncompleteRead(b"partial"))
        self.assertEqual(skips, ["skip=false"], "an incomplete read on the pull request list must write skip=false")
        self.assertEqual(code, 0, "an incomplete read on the pull request list must exit 0")
        self.assertIn("unknown", text.lower(), "an incomplete read on the pull request list must say unknown")

    # Named failure: any other exception from the network call escapes the read's except list the same way.
    def test_an_error_other_than_a_read_error_on_the_first_call_writes_skip_false_and_exits_zero(self):
        code, skips, text = self.live_decision(RuntimeError("the read broke"))
        self.assertEqual(skips, ["skip=false"], "an error other than Unknown from the read must write skip=false")
        self.assertEqual(code, 0, "an error other than Unknown from the read must exit 0")
        self.assertIn("unknown", text.lower(), "an error other than Unknown from the read must say unknown")

    # Named failure: an incomplete read of the batch head's commit, after the pull request list was read, escapes the same way.
    def test_an_incomplete_read_after_the_pull_request_list_writes_skip_false_and_exits_zero(self):
        def answer(url, token):
            if "/pulls?" in url:
                return [{"head": {"ref": BATCH, "sha": HEAD}}]
            raise http.client.IncompleteRead(b"partial")
        code, skips, text = self.live_decision(answer)
        self.assertEqual(skips, ["skip=false"], "an incomplete read of a batch head's commit must write skip=false")
        self.assertEqual(code, 0, "an incomplete read of a batch head's commit must exit 0")
        self.assertIn("unknown", text.lower(), "an incomplete read of a batch head's commit must say unknown")


class SuiteRunsOfTheHead(LiveHead):
    """The live read of a ready batch head's check runs. The push skips only when every suite job of checks.yml succeeded on that
    head's ready run, and all-jobs-passed alone does not decide it. Each case gives the head's runs to FakeGitHub."""

    def test_a_head_whose_every_suite_job_succeeded_skips_the_push(self):
        runs = ready_head_runs()
        self.assertGreater(len(runs), 30, "the head must hold more check runs than GitHub's default page of 30, so the read must reach past it")
        value, text = self.skip_on(runs)
        self.assertEqual(value, "true", "every suite job succeeded on the ready run and the jobs off a pull request are skipped: skip=true (%s)"
                         % text.strip()[-200:])

    def test_a_head_whose_suite_jobs_were_all_skipped_does_not_skip_the_push_though_all_jobs_passed_is_green(self):
        value, _ = self.skip_on(ready_head_runs({name: {"conclusion": "skipped"} for name in SUITE_JOBS}))
        self.assertEqual(value, "false", "every suite job skipped on the ready run, so no suite ran on this tree: skip=false")

    def test_one_suite_job_skipped_among_successes_does_not_skip_the_push(self):
        name = "checks-windows-rest"
        self.assertIn(name, SUITE_JOBS, "%s is not a suite job of checks.yml, so this case probes the wrong job" % name)
        value, _ = self.skip_on(ready_head_runs({name: {"conclusion": "skipped"}}))
        self.assertEqual(value, "false", "%s skipped on the ready run while the other suites succeeded: skip=false" % name)

    def test_one_suite_job_still_queued_does_not_skip_the_push(self):
        name = "checks-windows-rest"
        self.assertIn(name, SUITE_JOBS, "%s is not a suite job of checks.yml, so this case probes the wrong job" % name)
        value, _ = self.skip_on(ready_head_runs({name: {"conclusion": None, "status": "queued", "started_at": None}}))
        self.assertEqual(value, "false", "%s is still queued on the ready run, so its suite has not passed: skip=false" % name)

    def test_one_suite_job_missing_from_the_ready_run_does_not_skip_the_push(self):
        name = "checks-windows-rest"
        self.assertIn(name, SUITE_JOBS, "%s is not a suite job of checks.yml, so this case probes the wrong job" % name)
        value, _ = self.skip_on(ready_head_runs({name: None}))
        self.assertEqual(value, "false", "%s has no run on the ready run, so its suite never ran: skip=false" % name)

    def test_a_suite_job_that_failed_or_was_cancelled_does_not_skip_the_push(self):
        name = "checks-windows-rest"
        self.assertIn(name, SUITE_JOBS, "%s is not a suite job of checks.yml, so this case probes the wrong job" % name)
        for conclusion in ("failure", "cancelled"):
            with self.subTest(conclusion=conclusion):
                value, _ = self.skip_on(ready_head_runs({name: {"conclusion": conclusion}}))
                self.assertEqual(value, "false", "%s ended %s on the ready run: skip=false" % (name, conclusion))

    def test_a_suite_job_re_run_to_failure_does_not_skip_the_push_on_its_older_success(self):
        name = "checks-windows-rest"
        self.assertIn(name, SUITE_JOBS, "%s is not a suite job of checks.yml, so this case probes the wrong job" % name)
        runs = ready_head_runs({name: {"conclusion": "failure", "started_at": LATE}}, extra=[check_run(name=name, started_at=EARLY)])
        value, _ = self.skip_on(runs)
        self.assertEqual(value, "false", "%s was re-run and the newer run failed, so the older success stands for nothing: skip=false" % name)

    def test_every_suite_job_of_checks_yml_is_required_for_the_skip(self):
        self.assertTrue(SUITE_JOBS, "the reader derived no suite job from checks.yml, so this case would prove nothing")
        for name in SUITE_JOBS:
            with self.subTest(job=name):
                value, _ = self.skip_on(ready_head_runs({name: {"conclusion": "skipped"}}))
                self.assertEqual(value, "false", "%s is a suite job of checks.yml but skipping it still gives skip=true" % name)

    def test_a_head_with_no_check_runs_does_not_skip_the_push(self):
        value, _ = self.skip_on([])
        self.assertEqual(value, "false", "a head with no check runs has no run that passed: skip=false")

    def test_a_draft_batch_head_whose_runs_were_all_skipped_does_not_skip_the_push(self):
        draft = ready_head_runs({name: {"conclusion": "skipped"} for name in ALL_RUN_JOBS})
        value, _ = self.skip_on(draft)
        self.assertEqual(value, "false", "the draft run skipped every job, and a skipped run is no result: skip=false")

    def test_a_cancelled_all_jobs_passed_does_not_skip_the_push_though_every_suite_job_succeeded(self):
        value, _ = self.skip_on(ready_head_runs({ALL_JOBS_PASSED_JOB: {"conclusion": "cancelled"}}))
        self.assertEqual(value, "false", "all-jobs-passed was cancelled on the ready run, so the run did not pass: skip=false")

    def test_a_check_run_read_that_fails_does_not_skip_the_push(self):
        value, text = self.skip_on(fake=FakeGitHub(ready_head_runs(), fail=http.client.IncompleteRead(b"partial")))
        self.assertEqual(value, "false", "the check-runs read failed, so the suite evidence is unknown: skip=false")
        self.assertIn("unknown", text.lower(), "the check-runs read failed, so the script must say unknown")


OTHER_HEAD = "9" * 40  # a head that is not the pull request head under test


def step(name, conclusion="success"):
    """One step of a job, in the shape the jobs read returns."""
    return {"name": name, "status": "completed", "conclusion": conclusion}


def job_row(name, conclusion="success", steps=None):
    """One job of a run, in the shape the jobs read returns. Its steps default to one that ran, as a job that passed has."""
    return {"name": name, "status": "completed", "conclusion": conclusion, "steps": [step("Run")] if steps is None else steps}


def full_run_jobs(changes=None, extra=()):
    """The jobs of a full, ready pull request run of checks.yml: every job passed with its steps, and the jobs that never run on a pull
    request are skipped with no steps. `changes` maps a job name to the job_row keyword arguments it gets instead, or to None to leave
    that job out. `extra` adds rows after them, such as a second row of one name from a re-run."""
    jobs = {name: job_row(name, "skipped", steps=[]) if name in OFF_ON_PR else job_row(name) for name in ALL_RUN_JOBS}
    for name, change in (changes or {}).items():
        if change is None:
            jobs.pop(name, None)
        else:
            jobs[name] = job_row(name, **change)
    return list(jobs.values()) + list(extra)


def skipped_suite_steps(jobs):
    """(job, step) for each step of a suite job that was skipped: a scope flag that is off skips steps this way."""
    return [(job["name"], s["name"]) for job in jobs if job["name"] in SUITE_JOBS for s in job["steps"] if s["conclusion"] == "skipped"]


def pull_request_run(id_, conclusion="success", status="completed", head=LANE_HEAD, created_at=EARLY, path=RUN_PATH, event="pull_request"):
    """One checks.yml run of a pull request head, in the shape the runs read returns."""
    return {"id": id_, "name": "checks", "path": path, "event": event, "head_sha": head, "status": status,
            "conclusion": conclusion, "created_at": created_at, "run_attempt": 1}


def lane_pull(head=LANE_HEAD, merged_at=EARLY, branch="lane-x"):
    """The pull request of the push commit, in the shape the pull request read returns: merged unless merged_at is None."""
    return {"head": {"ref": branch, "sha": head}, "merged_at": merged_at}


class MergedPullRequest(LiveHead):
    """A push whose tree is the tree of one merged pull request that is not a batch head. The push skips only when the newest checks.yml
    run on that head is a full green pull request run. The reads are answered by FakeGitHub: the runs read asks for 100 per page, as
    the other reads do, so a full page is unknown."""

    def lane_fake(self, runs, jobs, pulls=None, tree=TREE, **options):
        return FakeGitHub(pulls=[lane_pull()] if pulls is None else pulls, trees={LANE_HEAD: tree}, workflow_runs=runs, jobs=jobs, **options)

    def test_a_merged_pull_request_with_the_push_tree_and_a_full_green_run_skips(self):
        fake = self.lane_fake([pull_request_run(1)], {1: full_run_jobs()})
        value, text = self.skip_on(fake=fake)
        self.assertIn("actions/runs", fake.reads, "push-skip never read the merged pull request's runs, so it cannot prove that run full")
        self.assertEqual(value, "true", "a merged pull request with the push's tree and a full green run must give skip=true (%s)"
                         % text.strip()[-200:])

    def test_a_full_run_whose_only_skipped_steps_are_mutation_report_steps_skips(self):
        # The mutation report is set by head ref (batch-* only), and on a push its action reports nothing, so its skipped steps are no narrowing.
        jobs = full_run_jobs({"mutation-report": {"steps": [step("Checkout", "skipped"), step("Mutation report and known defects", "skipped")]}})
        self.assertEqual(skipped_suite_steps(jobs), [("mutation-report", "Checkout"), ("mutation-report", "Mutation report and known defects")],
                         "the fixture must skip only the mutation-report steps, or it proves nothing about the exemption")
        fake = self.lane_fake([pull_request_run(1)], {1: jobs})
        value, text = self.skip_on(fake=fake)
        self.assertIn("actions/runs", fake.reads, "push-skip never read the merged pull request's runs, so it cannot judge the exemption")
        self.assertEqual(value, "true", "a full run whose skipped steps are all mutation-report steps must give skip=true (%s)" % text.strip()[-200:])

    def test_a_narrowed_run_whose_suite_step_was_skipped_by_scope_skips(self):
        jobs = full_run_jobs({"checks-windows-rest": {"steps": [step("Run"), step("Rest tests", "skipped")]}})
        self.assertEqual(skipped_suite_steps(jobs), [("checks-windows-rest", "Rest tests")], "the fixture must skip one suite step, or it proves nothing")
        value, text = self.skip_on(fake=self.lane_fake([pull_request_run(1)], {1: jobs}))
        self.assertEqual(value, "true", "a green run with a suite step skipped by scope is a passing PR run, so main skips (%s)" % text.strip()[-200:])

    def test_a_draft_run_whose_suite_jobs_were_all_skipped_runs(self):
        jobs = full_run_jobs({name: {"conclusion": "skipped", "steps": []} for name in SUITE_JOBS})
        self.assertTrue(all(job["conclusion"] == "skipped" for job in jobs if job["name"] in SUITE_JOBS), "the fixture must skip every suite job")
        value, _ = self.skip_on(fake=self.lane_fake([pull_request_run(1)], {1: jobs}))
        self.assertEqual(value, "false", "the draft run skipped every suite job, and a skipped job proves nothing: skip=false")

    def test_a_red_pull_request_run_runs(self):
        jobs = full_run_jobs({"checks-windows-rest": {"conclusion": "failure"}})
        value, _ = self.skip_on(fake=self.lane_fake([pull_request_run(1, conclusion="failure")], {1: jobs}))
        self.assertEqual(value, "false", "a red pull request run must give skip=false")

    def test_a_newer_red_run_beats_an_older_full_green_run(self):
        runs = [pull_request_run(1, created_at=EARLY), pull_request_run(2, conclusion="failure", created_at=LATE)]
        jobs = {1: full_run_jobs(), 2: full_run_jobs({"checks-windows-rest": {"conclusion": "failure"}})}
        self.assertEqual(max(runs, key=lambda r: r["created_at"])["conclusion"], "failure", "the fixture's newest run must be the red one")
        value, _ = self.skip_on(fake=self.lane_fake(runs, jobs))
        self.assertEqual(value, "false", "the newest run on the head is red, so an older green run stands for nothing: skip=false")

    def test_a_cancelled_newer_run_beats_an_older_full_green_run(self):
        runs = [pull_request_run(1, created_at=EARLY), pull_request_run(2, conclusion="cancelled", created_at=LATE)]
        jobs = {1: full_run_jobs(), 2: full_run_jobs({name: {"conclusion": "cancelled", "steps": []} for name in SUITE_JOBS})}
        value, _ = self.skip_on(fake=self.lane_fake(runs, jobs))
        self.assertEqual(value, "false", "the newest run on the head was cancelled, so it is no green run: skip=false")

    def test_an_in_progress_newer_run_beats_an_older_full_green_run(self):
        runs = [pull_request_run(1, created_at=EARLY), pull_request_run(2, conclusion=None, status="in_progress", created_at=LATE)]
        value, _ = self.skip_on(fake=self.lane_fake(runs, {1: full_run_jobs()}))
        self.assertEqual(value, "false", "the newest run on the head is still going, so its result is not in: skip=false")

    def test_a_full_green_run_on_another_head_runs(self):
        fake = self.lane_fake([pull_request_run(1, head=OTHER_HEAD)], {1: full_run_jobs()})
        self.assertNotEqual(fake.workflow_runs[0]["head_sha"], LANE_HEAD, "the fixture's run must be on another head, or it proves nothing")
        value, _ = self.skip_on(fake=fake)
        self.assertEqual(value, "false", "a green run on another head does not prove this pull request head: skip=false")

    def test_a_full_green_run_of_another_workflow_runs(self):
        fake = self.lane_fake([pull_request_run(1, path=OTHER_PATH)], {1: full_run_jobs()})
        self.assertNotEqual(fake.workflow_runs[0]["path"].split("@")[0], RUN_PATH, "the fixture's run must be another workflow, or it proves nothing")
        value, _ = self.skip_on(fake=fake)
        self.assertEqual(value, "false", "a green run of another workflow is not the checks run: skip=false")

    def test_a_pull_request_that_was_not_merged_runs(self):
        fake = self.lane_fake([pull_request_run(1)], {1: full_run_jobs()}, pulls=[lane_pull(merged_at=None)])
        self.assertIsNone(fake.pulls[0]["merged_at"], "the fixture's pull request must be unmerged, or it proves nothing")
        value, _ = self.skip_on(fake=fake)
        self.assertEqual(value, "false", "a pull request that was not merged is no proof for main: skip=false")

    def test_a_merged_pull_request_with_another_tree_runs(self):
        fake = self.lane_fake([pull_request_run(1)], {1: full_run_jobs()}, tree=OTHER_TREE)
        self.assertNotEqual(fake.trees[LANE_HEAD], TREE, "the fixture's tree must differ from the push's, or it proves nothing")
        value, _ = self.skip_on(fake=fake)
        self.assertEqual(value, "false", "a pull request whose tree is not the push's tree does not cover the push: skip=false")

    def test_a_direct_push_with_no_pull_request_runs(self):
        fake = self.lane_fake([pull_request_run(1)], {1: full_run_jobs()}, pulls=[])
        self.assertEqual(fake.pulls, [], "the fixture must give the push no pull request, or it proves nothing")
        value, _ = self.skip_on(fake=fake)
        self.assertEqual(value, "false", "a direct push has no pull request run to stand for it: skip=false")

    def test_a_failed_runs_read_runs(self):
        fake = self.lane_fake([pull_request_run(1)], {1: full_run_jobs()}, runs_fail=http.client.IncompleteRead(b"partial"))
        value, _ = self.skip_on(fake=fake)
        self.assertEqual(value, "false", "a failed runs read is unknown, so it runs everything: skip=false")

    def test_a_failed_jobs_read_runs(self):
        fake = self.lane_fake([pull_request_run(1)], {1: full_run_jobs()}, jobs_fail=http.client.IncompleteRead(b"partial"))
        value, _ = self.skip_on(fake=fake)
        self.assertEqual(value, "false", "a failed jobs read is unknown, so it runs everything: skip=false")

    def test_a_full_page_of_runs_on_the_head_runs(self):
        runs = [pull_request_run(i) for i in range(1, 101)]
        jobs = {i: full_run_jobs() for i in range(1, 101)}  # every run is full and green: only the full page keeps the read from skipping
        self.assertEqual(len(runs), 100, "the fixture must fill a page of 100, or it proves nothing")
        value, _ = self.skip_on(fake=self.lane_fake(runs, jobs))
        self.assertEqual(value, "false", "a full page of runs may hide a newer run, so the read is unknown: skip=false")

    def test_a_batch_head_that_passed_still_skips_beside_a_narrowed_merged_pull_request(self):
        jobs = full_run_jobs({"checks-windows-rest": {"steps": [step("Rest tests", "skipped")]}})
        self.assertTrue(skipped_suite_steps(jobs), "the merged pull request's run must be partial, so the merged pull request is narrowed beside the batch head")
        fake = FakeGitHub(ready_head_runs(), pulls=[{"head": {"ref": BATCH, "sha": HEAD}}, lane_pull()],
                          trees={HEAD: TREE, LANE_HEAD: TREE}, workflow_runs=[pull_request_run(1)], jobs={1: jobs})
        value, _ = self.skip_on(fake=fake)
        self.assertEqual(value, "true", "a green batch head with the push's tree still skips, whatever a narrowed merged pull request says")

    def test_a_merged_pull_request_whose_all_jobs_passed_row_is_missing_runs(self):
        # all-jobs-passed fans in the suite jobs, so a run without its row has not been shown to pass.
        jobs = full_run_jobs({ROLLUP_NAME: None})
        self.assertEqual([j for j in jobs if j["name"] == ROLLUP_NAME], [],
                         "the fixture must leave all-jobs-passed out, or it proves nothing")
        value, _ = self.skip_on(fake=self.lane_fake([pull_request_run(1)], {1: jobs}))
        self.assertEqual(value, "false", "a green run with no all-jobs-passed row does not prove the merged pull request: skip=false")

    def test_a_merged_pull_request_whose_all_jobs_passed_was_cancelled_runs(self):
        jobs = full_run_jobs({ROLLUP_NAME: {"conclusion": "cancelled"}})
        self.assertEqual([j["conclusion"] for j in jobs if j["name"] == ROLLUP_NAME], ["cancelled"],
                         "the fixture must cancel all-jobs-passed, or it proves nothing")
        value, _ = self.skip_on(fake=self.lane_fake([pull_request_run(1)], {1: jobs}))
        self.assertEqual(value, "false", "all-jobs-passed was cancelled in the merged pull request's run: skip=false")

    def test_a_push_run_on_the_head_does_not_prove_the_merged_pull_request(self):
        # The runs read asks for event=pull_request, and the decision checks no event of its own, so the query keeps a push run out.
        fake = self.lane_fake([pull_request_run(1, event="push")], {1: full_run_jobs()})
        self.assertEqual(fake.workflow_runs[0]["event"], "push", "the fixture's run must be a push run, or it proves nothing")
        value, _ = self.skip_on(fake=fake)
        self.assertIn("actions/runs", fake.reads, "push-skip never read the head's runs, so the push run was not in play")
        self.assertEqual(value, "false", "a green push run on the head is no pull request run, so it proves nothing: skip=false")

    def test_a_green_run_on_another_head_that_the_read_returns_does_not_prove_this_head(self):
        # The API filters by head_sha, but the decision must hold its own head check when a read returns a run on another head.
        fake = self.lane_fake([pull_request_run(1, head=OTHER_HEAD)], {1: full_run_jobs()}, ignore_run_filters=True)
        self.assertEqual(fake.workflow_runs[0]["head_sha"], OTHER_HEAD, "the fixture's run must be on another head, or it proves nothing")
        value, _ = self.skip_on(fake=fake)
        self.assertIn("actions/runs", fake.reads, "push-skip never read the runs, so the other head's run was not in play")
        self.assertEqual(value, "false", "a green run on another head does not prove this pull request head: skip=false")

    def test_a_newest_run_that_failed_was_cancelled_or_is_running_runs_though_its_jobs_passed(self):
        # The run's own verdict is the result. Its jobs are all green here, so only the run's status and conclusion can stop the skip.
        for status, conclusion in (("completed", "failure"), ("completed", "cancelled"), ("in_progress", None)):
            with self.subTest(run="%s/%s" % (status, conclusion)):
                runs = [pull_request_run(1, created_at=EARLY),
                        pull_request_run(2, conclusion=conclusion, status=status, created_at=LATE)]
                jobs = {1: full_run_jobs(), 2: full_run_jobs()}
                self.assertTrue(all(j["conclusion"] in ("success", "skipped") for j in jobs[2]),
                                "the fixture's newest run must have every job green, or it proves nothing")
                value, _ = self.skip_on(fake=self.lane_fake(runs, jobs))
                self.assertEqual(value, "false", "the newest run on the head is %s/%s, so an older green run stands for nothing: skip=false"
                                 % (status, conclusion))

    def test_a_full_page_of_jobs_on_the_run_runs_though_every_required_job_passed(self):
        # A page of 100 may hide a row past it, so the read is unknown and the decision runs everything.
        jobs = full_run_jobs()
        jobs += [job_row("padding-%03d" % i) for i in range(100 - len(jobs))]
        self.assertEqual(len(jobs), 100, "the fixture must fill a page of 100 jobs, or it proves nothing")
        self.assertTrue({ROLLUP_NAME, *SUITE_JOBS} <= {j["name"] for j in jobs},
                        "a required job is missing from the fixture, so the case proves nothing")
        value, _ = self.skip_on(fake=self.lane_fake([pull_request_run(1)], {1: jobs}))
        self.assertEqual(value, "false", "a full page of jobs may hide a row past it, so the read is unknown: skip=false")

    def test_a_jobs_page_one_short_of_full_still_skips(self):
        jobs = full_run_jobs()
        jobs += [job_row("padding-%03d" % i) for i in range(99 - len(jobs))]
        self.assertEqual(len(jobs), 99, "the fixture must leave one row short of a full page, or it proves nothing")
        value, text = self.skip_on(fake=self.lane_fake([pull_request_run(1)], {1: jobs}))
        self.assertEqual(value, "true",
                         "a page of 99 jobs is not full, and every required job passed: skip=true (%s)" % text.strip()[-200:])

    def test_a_failed_row_of_a_job_blocks_the_skip_beside_its_passed_row_in_either_order(self):
        # The rule kept here: any non-success row of a job name blocks the skip. A newer passed row does not clear an older failed one.
        name = "checks-windows-rest"
        self.assertIn(name, SUITE_JOBS, "%s is not a suite job of checks.yml, so this case probes the wrong job" % name)
        failed = job_row(name, "failure")
        orders = {"failed row first": [failed] + full_run_jobs(), "passed row first": full_run_jobs(extra=[failed])}
        for order, jobs in orders.items():
            with self.subTest(order=order):
                self.assertEqual(sum(1 for j in jobs if j["name"] == name), 2,
                                 "the fixture must hold two rows of %s, or it proves nothing" % name)
                value, _ = self.skip_on(fake=self.lane_fake([pull_request_run(1)], {1: jobs}))
                self.assertEqual(value, "false", "a failed row of %s blocks the skip beside its passed row: skip=false" % name)

    def test_two_passed_rows_of_one_job_still_skip(self):
        name = "checks-windows-rest"
        jobs = full_run_jobs(extra=[job_row(name)])
        self.assertEqual(sum(1 for j in jobs if j["name"] == name), 2, "the fixture must hold two rows of %s, or it proves nothing" % name)
        value, text = self.skip_on(fake=self.lane_fake([pull_request_run(1)], {1: jobs}))
        self.assertEqual(value, "true", "two passed rows of %s are no failure, so every job passed and the push skips (%s)"
                         % (name, text.strip()[-200:]))


class EventRefusal(LiveHead):
    """A scheduled or manual run never skips, even when a green batch head with the push's tree is there. The push job runs on push
    only, but the decision refuses by event too, so a wiring that drops the push-only if: cannot skip a nightly."""

    def test_a_schedule_run_never_skips_even_when_a_green_batch_head_matches(self):
        fake = FakeGitHub(ready_head_runs())
        self.assertEqual(fake.trees[HEAD], TREE, "the fixture's batch head must match the push's tree, or it proves nothing")
        value, _ = self.skip_on(fake=fake, extra_env={"EVENT": "schedule"})
        self.assertEqual(value, "false", "a scheduled run must never skip: skip=false")

    def test_a_workflow_dispatch_run_never_skips_even_when_a_green_batch_head_matches(self):
        fake = FakeGitHub(ready_head_runs())
        self.assertEqual(fake.trees[HEAD], TREE, "the fixture's batch head must match the push's tree, or it proves nothing")
        value, _ = self.skip_on(fake=fake, extra_env={"EVENT": "workflow_dispatch"})
        self.assertEqual(value, "false", "a manual run must never skip: skip=false")


class CallerWorkflow(LiveHead):
    """The suite list comes from the calling checkout, GITHUB_WORKSPACE, as all-jobs-passed reads its own workflow. A child repo that pins
    the shared action has its own checks.yml, and the action's copy of this repo's is not that repo's."""

    def test_the_suite_list_is_read_from_the_calling_workflow_in_the_workspace(self):
        caller = os.path.join(RUN_FOLDER, "caller-%s" % uuid.uuid4().hex)
        os.makedirs(os.path.join(caller, ".github", "workflows"))
        with open(os.path.join(caller, ".github", "workflows", "checks.yml"), "w", encoding="utf-8") as handle:
            handle.write(all_jobs_home.CHILD_GOOD)
        child_suites = sorted(name for name in split_jobs(all_jobs_home.CHILD_GOOD)[0] if name not in BOOKKEEPING)
        self.assertNotEqual(child_suites, SUITE_JOBS, "the caller's suite list must differ from this repo's, or the case proves nothing")
        fake = FakeGitHub([check_run(name="lint"), check_run(name="test-mac"), check_run(name=ROLLUP_NAME)])
        value, text = self.skip_on(fake=fake, extra_env={"GITHUB_WORKSPACE": caller})
        self.assertEqual(value, "true", "every suite job of the caller's checks.yml passed, so the push skips: the suite list must come from the caller (%s)"
                         % text.strip()[-200:])


class SharedAction(unittest.TestCase):
    """This repo's checks.yml calls the shared action for the decision, so the decision has one home. The uses line is matched the way
    this repo writes its local actions: its prefix is read from the all-jobs-passed line, never assumed."""

    def setUp(self):
        with open(CHECKS, encoding="utf-8") as f:
            self.text = f.read()

    def test_the_push_skip_job_calls_the_shared_action(self):
        prefix = re.search(r"uses: (\S*?)actions/all-jobs-passed", self.text)
        self.assertIsNotNone(prefix, "checks.yml has no all-jobs-passed uses line to read the local action prefix from")
        block = job_block(self.text, JOB) or ""
        self.assertIn("uses: %sactions/push-skip" % prefix.group(1), block,
                      "the push-skip job does not call the shared action, so the decision keeps its own copy in a run step")

    def test_the_push_skip_job_passes_the_event_name_to_the_decision(self):
        block = job_block(self.text, JOB) or ""
        self.assertIn("EVENT: ${{ github.event_name }}", block, "the push-skip job does not pass the event name, so the decision cannot refuse a schedule or dispatch run")

    def test_no_second_copy_of_the_decision_is_left_under_github_scripts(self):
        self.assertFalse(os.path.isfile(LEGACY_SCRIPT), "push-skip.py still has a second copy at .github/scripts/push-skip.py, so the decision has two homes")


class PushSkipWiring(unittest.TestCase):
    def setUp(self):
        with open(CHECKS, encoding="utf-8") as f:
            self.text = f.read()
        self.jobs = all_jobs(self.text)

    def test_push_skip_starts_on_every_event_and_its_steps_run_on_a_push_only(self):
        # A job-level if would leave the job skipped on a pull request, and all-jobs-passed reads a skipped needed job as red.
        # Named failure: a job-level if returns, or a step runs off a push.
        self.assertIsNone(self.jobs.get(JOB, {}).get("if"), f"{JOB} keeps a job-level if: it would read skipped on a pull request")
        block = job_block(self.text, JOB) or ""
        steps = step_blocks(block)
        self.assertTrue(steps, f"{JOB} has no steps")
        for step in steps:
            expr = step_key(step, "if")
            self.assertIsNotNone(expr, f"a {JOB} step has no if: it would run off a push")
            self.assertTrue(eval_if(expr, "push", "", draft=False), f"a {JOB} step does not run on push: if {expr}")
            for event in ("pull_request", "schedule", "workflow_dispatch"):
                self.assertFalse(eval_if(expr, event, "", draft=False), f"a {JOB} step runs on {event}: if {expr}")

    def test_push_skip_decides_in_a_step_with_id_decide_and_outputs_skip(self):
        block = job_block(self.text, JOB) or ""
        self.assertIn("id: decide", block, f"{JOB} has no step with id decide")
        self.assertIn("skip: ${{ steps.decide.outputs.skip }}", block, f"{JOB} does not output skip from steps.decide")

    def test_push_skip_has_a_timeout_cap_and_read_only_permissions(self):
        block = job_block(self.text, JOB) or ""
        self.assertIn("timeout-minutes:", block, f"{JOB} has no timeout-minutes cap")
        self.assertIn("contents: read", block, f"{JOB} does not restate contents: read")

    def test_push_skip_pins_actions_read_so_the_runs_read_is_not_refused(self):
        # The lone-lane path reads actions/runs. Without actions: read GitHub refuses that read, and the decision then writes skip=false
        # with no red, so the pin is the only thing that keeps the skip working.
        block = job_block(self.text, JOB) or ""
        self.assertIn("permissions:", block, f"{JOB} has no permissions block to pin actions: read in")
        self.assertRegex(block, r"(?m)^      actions: read$",
                         f"{JOB} does not pin actions: read, so the runs read is refused and the skip never fires")

    def test_scope_needs_push_skip_so_a_skipped_push_skips_every_job_through_needs(self):
        needs = needs_of(job_block(self.text, "scope")) or []
        self.assertIn(JOB, needs, f"scope does not need {JOB}, so a matching push would not skip the other jobs")


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    unittest.main()
