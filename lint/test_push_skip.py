#!/usr/bin/env python3
"""Tests for .github/scripts/push-skip.py, the decision that lets a push to main skip the checks its tree already passed.

The script writes skip=true to $GITHUB_OUTPUT only when the push commit's tree equals the tree of a batch-* pull request
head whose checks run concluded success. Any read failure writes skip=false and says "unknown". Two stand-ins drive it,
never the network: PUSH_TREE, the push commit's tree sha, and PRS_JSON, a JSON list of the batch pull request heads, each
{"head_branch", "tree", "status", "conclusion"}. The live read uses GH_TOKEN and REPO.

The wiring cases read checks.yml: the push-skip job decides in a step with id decide, outputs skip, is push-only, and scope
needs it, so every other job skips through needs as nightly-skip does for scope.

The live cases answer the GitHub reads through FakeGitHub, by URL, as the API does. A ready batch head skips the push only when
every suite job of checks.yml succeeded on that head's ready run, not only when all-jobs-passed passed.

    python3 lint/test_push_skip.py
"""
import contextlib
import http.client
import importlib.util
import io
import json
import os
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
from workflow_steps import job_block  # noqa: E402  the one home of the job parser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUSH_SKIP = os.path.join(ROOT, ".github", "scripts", "push-skip.py")
RUN_FOLDER = _test_temp.run_folder()  # one run folder per test run; teardown removes it

JOB = "push-skip"
REPO = "owner/repo"
TREE = "a" * 40  # the push commit's tree
OTHER_TREE = "b" * 40
BATCH = "batch-lane-x"
SCRIPT_MISSING = "push-skip.py is missing at .github/scripts/push-skip.py, so no decision sets the push skip"

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
    """The GitHub reads push-skip makes, answered by URL the way the API answers them: the batch head's pull request list, its
    commit, and its check runs. check_name filters the runs, and per_page (default 30) and page cut them. `fail` is raised by every
    check-runs read. A URL no case expects goes to `unexpected`, which the case asserts empty."""

    def __init__(self, runs, fail=None):
        self.runs = runs
        self.fail = fail
        self.unexpected = []

    def __call__(self, url, token):
        parts = urllib.parse.urlsplit(url)
        prefix = "/repos/%s/" % REPO
        path = parts.path[len(prefix):] if parts.path.startswith(prefix) else parts.path
        query = urllib.parse.parse_qs(parts.query)
        if path == "commits/%s/pulls" % SHA:
            return [{"head": {"ref": BATCH, "sha": HEAD}}]
        if path == "git/commits/%s" % HEAD:
            return {"tree": {"sha": TREE}}
        if path == "commits/%s/check-runs" % HEAD:
            if self.fail is not None:
                raise self.fail
            runs = self.runs
            if "check_name" in query:
                runs = [run for run in runs if run["name"] == query["check_name"][0]]
            per_page = int(query.get("per_page", ["30"])[0])
            page = int(query.get("page", ["1"])[0])
            return {"check_runs": runs[(page - 1) * per_page:page * per_page]}
        self.unexpected.append(path)
        return {}


class LiveHead(unittest.TestCase):
    """main() on the live reads, each answered by FakeGitHub: no network, no stand-in. Returns the one skip value written and the text
    printed."""

    def skip_on(self, runs=None, fake=None):
        self.assertTrue(os.path.isfile(PUSH_SKIP), SCRIPT_MISSING)
        module = load_script()
        fake = fake if fake is not None else FakeGitHub(runs)
        out = os.path.join(RUN_FOLDER, "output-%s" % uuid.uuid4().hex)
        env = {"GH_TOKEN": "t", "REPO": REPO, "HEAD_SHA": SHA, "PUSH_TREE": TREE, "GITHUB_OUTPUT": out}
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


class PushSkipWiring(unittest.TestCase):
    def setUp(self):
        with open(CHECKS, encoding="utf-8") as f:
            self.text = f.read()
        self.jobs = all_jobs(self.text)

    def test_push_skip_is_a_job_that_runs_on_push_and_not_on_pull_request(self):
        expr = self.jobs.get(JOB, {}).get("if")
        self.assertIsNotNone(expr, f"checks.yml has no {JOB} job with a job-level if")
        self.assertTrue(eval_if(expr, "push", "", draft=False), f"{JOB} does not run on push: if {expr}")
        self.assertFalse(eval_if(expr, "pull_request", "", draft=False), f"{JOB} runs on pull_request: if {expr}")

    def test_push_skip_decides_in_a_step_with_id_decide_and_outputs_skip(self):
        block = job_block(self.text, JOB) or ""
        self.assertIn("id: decide", block, f"{JOB} has no step with id decide")
        self.assertIn("skip: ${{ steps.decide.outputs.skip }}", block, f"{JOB} does not output skip from steps.decide")

    def test_push_skip_has_a_timeout_cap_and_read_only_permissions(self):
        block = job_block(self.text, JOB) or ""
        self.assertIn("timeout-minutes:", block, f"{JOB} has no timeout-minutes cap")
        self.assertIn("contents: read", block, f"{JOB} does not restate contents: read")

    def test_scope_needs_push_skip_so_a_skipped_push_skips_every_job_through_needs(self):
        needs = needs_of(job_block(self.text, "scope")) or []
        self.assertIn(JOB, needs, f"scope does not need {JOB}, so a matching push would not skip the other jobs")


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    unittest.main()
