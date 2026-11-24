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
  request head whose newest checks.yml run is a green pull request run: all-jobs-passed and every suite job succeeded. A run that
  concluded cancelled counts too, when all-jobs-passed and every suite job succeeded: a cancel after those jobs passed is no gap.
  A suite step that scope skipped does not stop the skip: after a passing PR run, narrowed or full, main runs none of its suites for that merge.
  A macOS job runs on a schedule and a dispatch only (owner, 01:33 CST Nov 16), so it is no suite job of a batch head or a pull request:
  its skip is no gap, and no scope-skips input names it. Any other suite job skipped on the run is still a gap.
  A records-only run (every suite job skipped, scope and all-jobs-passed succeeded) is a passing run: its skips are proven. The
  REST jobs read carries no job outputs, so all-jobs-passed's success stands for its records_only_skip flag.
- base=<sha> on every push, written even when empty: the head of the newest completed, successful checks.yml run of main whose
  suites ran (a run with every suite job skipped is no base). A newer run still queued or in progress is unread, so it gives
  empty (consultant's pick, 07:10 CST Nov 24 2026, under decision push-skip-on-proven-tree). A completed red or
  cancelled run newer than the base gives empty, and so does this run's own record (GITHUB_RUN_ID). The output is a full 40-hex
  sha or empty. A read error, a malformed reply or a full page with no usable run gives empty and says "unknown" (class ProvenBase).
- Any read error, unknown state or unreadable record writes skip=false and says "unknown".
- Every other skip=false path prints its reason on one line that names what refused it: the pull request number or the head branch,
  and the trees (short) for a tree mismatch. A push that no pull request covers names the push tree (short).

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
from test_windows_split import ALL_JOBS_PASSED_JOB, CHECKS, MACOS_JOBS, NIGHTLY_SKIP_JOB, PUSH_SKIP_JOB, all_jobs, eval_if, eval_value, job_outputs_of  # noqa: E402  the one home of the checks.yml reader
from all_jobs_passed_rules import FAN_IN, needs_of, split_jobs  # noqa: E402  the one home of the needs reader
from workflow_steps import job_block, step_blocks, step_env, step_key, step_with  # noqa: E402  the one home of the job parser
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
SCOPE_JOB = "scope"  # the job that reads the scope flags; a scope skip needs its run to have succeeded
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
    `workflow_runs` are the runs of the repo (filtered by head_sha, event and branch when the read names them, as the API does, and
    never by status: a case's in-progress run reaches the script) and `jobs` maps a run id to its jobs. check_name filters the check
    runs; per_page (default 30) and page cut every list. `fail` is raised by every check-runs read, `runs_fail` by the runs read and
    `jobs_fail` by the jobs read. `runs_reply` is returned in place of the list by a runs read that names no head_sha (the base
    search), so a case can give a malformed reply. `ignore_query` names the runs-read filters (event, branch) this fake does not
    apply, so a case whose run the API would have filtered out reaches the script, and the script's own filter is what drops it.
    A URL no case expects goes to `unexpected`, which the case asserts empty; `reads` keeps every path asked, in order."""

    def __init__(self, runs=(), fail=None, pulls=None, trees=None, workflow_runs=None, jobs=None, runs_fail=None, jobs_fail=None,
                 runs_reply=None, ignore_query=()):
        self.runs = list(runs or [])
        self.fail = fail
        self.pulls = [{"head": {"ref": BATCH, "sha": HEAD}}] if pulls is None else pulls
        self.trees = {HEAD: TREE} if trees is None else trees
        self.workflow_runs = [] if workflow_runs is None else workflow_runs
        self.jobs = {} if jobs is None else jobs
        self.runs_fail, self.jobs_fail = runs_fail, jobs_fail
        self.runs_reply = runs_reply
        self.ignore_query = tuple(ignore_query)
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
            if self.runs_reply is not None and "head_sha" not in query:
                return self.runs_reply
            runs = [r for r in self.workflow_runs
                    if ("head_sha" not in query or r["head_sha"] == query["head_sha"][0])
                    and ("event" not in query or "event" in self.ignore_query or r["event"] == query["event"][0])
                    and ("branch" not in query or "branch" in self.ignore_query or r.get("head_branch") == query["branch"][0])]
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

    def test_a_head_whose_suite_jobs_were_all_skipped_does_not_skip_the_push_when_all_jobs_passed_failed(self):
        changes = {name: {"conclusion": "skipped"} for name in SUITE_JOBS}
        changes[ALL_JOBS_PASSED_JOB] = {"conclusion": "failure"}
        value, _ = self.skip_on(ready_head_runs(changes))
        self.assertEqual(value, "false", "every suite job skipped and all-jobs-passed failed, so the rollup refused the skips: skip=false")

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
                self.assertEqual(value, "false", "%s is a suite job, but skipping it still gives skip=true" % name)

    def test_the_macos_jobs_are_no_suite_job_of_checks_yml(self):
        # Named failure: a macOS job is a suite job, so a skipped macOS job on a ready run is a gap the push must not skip over.
        self.assertTrue(set(MACOS_JOBS) <= set(ALL_RUN_JOBS), "a macOS job is not a job of checks.yml, so this case would prove nothing")
        self.assertEqual(sorted(set(MACOS_JOBS) & set(SUITE_JOBS)), [], "a macOS job is a suite job of checks.yml")

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


def job_row(name, conclusion="success", steps=None, status="completed"):
    """One job of a run, in the shape the jobs read returns. Its steps default to one that ran, as a job that passed has. `status` is
    completed unless the job is still running."""
    return {"name": name, "status": status, "conclusion": conclusion, "steps": [step("Run")] if steps is None else steps}


def full_run_jobs(changes=None):
    """The jobs of a full, ready pull request run of checks.yml: every job passed with its steps, and the jobs that never run on a pull
    request are skipped with no steps. `changes` maps a job name to the job_row keyword arguments it gets instead, or to None to leave
    that job out."""
    jobs = {name: job_row(name, "skipped", steps=[]) if name in OFF_ON_PR else job_row(name) for name in ALL_RUN_JOBS}
    for name, change in (changes or {}).items():
        if change is None:
            jobs.pop(name, None)
        else:
            jobs[name] = job_row(name, **change)
    return list(jobs.values())


def skipped_suite_steps(jobs):
    """(job, step) for each step of a suite job that was skipped: a scope flag that is off skips steps this way."""
    return [(job["name"], s["name"]) for job in jobs if job["name"] in SUITE_JOBS for s in job["steps"] if s["conclusion"] == "skipped"]


def pull_request_run(id_, conclusion="success", status="completed", head=LANE_HEAD, created_at=EARLY, path=RUN_PATH, event="pull_request"):
    """One checks.yml run of a pull request head, in the shape the runs read returns."""
    return {"id": id_, "name": "checks", "path": path, "event": event, "head_sha": head, "status": status,
            "conclusion": conclusion, "created_at": created_at, "run_attempt": 1}


LANE_NUMBER = 3819  # a merged lone lane's pull request number, as the pull request read carries it


def lane_pull(head=LANE_HEAD, merged_at=EARLY, branch="lane-x", number=LANE_NUMBER):
    """The pull request of the push commit, in the shape the pull request read returns: merged unless merged_at is None."""
    return {"number": number, "head": {"ref": branch, "sha": head}, "merged_at": merged_at}


def lone_lane_fake(runs, jobs, pulls=None, tree=TREE, **options):
    """The reads of a push whose tree is a merged lone lane's: its pull request, its head's tree, and its checks.yml runs and jobs."""
    return FakeGitHub(pulls=[lane_pull()] if pulls is None else pulls, trees={LANE_HEAD: tree}, workflow_runs=runs, jobs=jobs, **options)


def reason_lines(text, token):
    """The printed lines that name `token`. A skip=false prints the reason for it, and the reason names what refused the push."""
    return [line for line in text.splitlines() if token in line]


class MergedPullRequest(LiveHead):
    """A push whose tree is the tree of one merged pull request that is not a batch head. The push skips only when the newest checks.yml
    run on that head is a full green pull request run. The reads are answered by FakeGitHub: the runs read asks for 100 per page, as
    the other reads do, so a full page is unknown."""

    def lane_fake(self, runs, jobs, pulls=None, tree=TREE, **options):
        return lone_lane_fake(runs, jobs, pulls=pulls, tree=tree, **options)

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
        # A real draft skips its scope job, so all-jobs-passed fails on the skipped scope.
        changes = {name: {"conclusion": "skipped", "steps": []} for name in SUITE_JOBS}
        changes[SCOPE_JOB] = {"conclusion": "skipped", "steps": []}
        changes[ROLLUP_NAME] = {"conclusion": "failure"}
        jobs = full_run_jobs(changes)
        got = {job["name"]: job["conclusion"] for job in jobs}
        self.assertEqual((got.get(SCOPE_JOB), got.get(ROLLUP_NAME)), ("skipped", "failure"), "the fixture must be a draft: scope skipped, all-jobs-passed failed")
        self.assertTrue(all(got.get(name) == "skipped" for name in SUITE_JOBS), "the fixture must skip every suite job")
        value, _ = self.skip_on(fake=self.lane_fake([pull_request_run(1)], {1: jobs}))
        self.assertEqual(value, "false", "the draft run skipped its scope job, so no suite ran and a skipped job proves nothing: skip=false")

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


class MacosJobsOffBatchHead(LiveHead):
    """A ready batch head whose macOS jobs never ran. They start on a schedule and a dispatch only, so the ready run skips them and they
    are no suite job of the head. The rest of the suite, and the rollup and scope runs, still decide the skip."""

    def test_a_batch_head_whose_macos_jobs_never_ran_skips_the_push(self):
        runs = ready_head_runs()
        got = {r["name"]: r["conclusion"] for r in runs}
        self.assertEqual({name: got.get(name) for name in MACOS_JOBS}, {name: "skipped" for name in MACOS_JOBS},
                         "the ready run must skip each macOS job, as a pull_request does now")
        self.assertEqual((got.get(SCOPE_JOB), got.get(ROLLUP_NAME)), ("success", "success"),
                         "the fixture's scope and all-jobs-passed runs must succeed")
        value, text = self.skip_on(runs)
        self.assertEqual(value, "true", "the macOS jobs never ran on the head, and every suite job passed: skip=true (%s)"
                         % text.strip()[-200:])

    def test_each_macos_job_skipped_alone_skips_the_push(self):
        for name in MACOS_JOBS:
            with self.subTest(job=name):
                value, _ = self.skip_on(ready_head_runs({name: {"conclusion": "skipped"}}))
                self.assertEqual(value, "true", "%s is skipped on the ready run and is no suite job of the head: skip=true" % name)

    def test_a_skipped_suite_job_beside_the_skipped_macos_jobs_is_refused(self):
        name = "checks-windows-rest"
        self.assertIn(name, SUITE_JOBS, "%s is not a suite job of checks.yml, so this case probes the wrong job" % name)
        value, _ = self.skip_on(ready_head_runs({name: {"conclusion": "skipped"}}))
        self.assertEqual(value, "false", "%s was skipped on the ready run and is a suite job: skip=false" % name)

    def test_a_failed_rollup_is_refused(self):
        value, _ = self.skip_on(ready_head_runs({ROLLUP_NAME: {"conclusion": "failure"}}))
        self.assertEqual(value, "false", "all-jobs-passed failed on the ready run, so it judged no skip: skip=false")

    def test_no_rollup_run_is_refused(self):
        value, _ = self.skip_on(ready_head_runs({ROLLUP_NAME: None}))
        self.assertEqual(value, "false", "the ready run has no all-jobs-passed run, so no rollup judged the skip: skip=false")



class MacosJobsCallerWorkspace(LiveHead):
    """The calling workflow's checks.yml is read from GITHUB_WORKSPACE. No macOS job has a scope skip now, so the file names no
    scope-skips map, and a caller with that file still proves the skip from its suite jobs alone."""

    def caller(self):
        """A calling workspace whose checks.yml is this repo's."""
        caller = os.path.join(RUN_FOLDER, "caller-%s" % uuid.uuid4().hex)
        os.makedirs(os.path.join(caller, ".github", "workflows"))
        with open(os.path.join(caller, ".github", "workflows", "checks.yml"), "w", encoding="utf-8") as handle:
            handle.write(CHECKS_TEXT)
        return caller

    def test_a_caller_with_no_scope_skips_input_skips_the_push_when_the_macos_jobs_never_ran(self):
        runs = ready_head_runs()
        got = {r["name"]: r["conclusion"] for r in runs}
        self.assertEqual({name: got.get(name) for name in MACOS_JOBS}, {name: "skipped" for name in MACOS_JOBS},
                         "the ready run must skip each macOS job, as a pull_request does now")
        value, text = self.skip_on(runs, extra_env={"GITHUB_WORKSPACE": self.caller()})
        self.assertEqual(value, "true", "the caller names no scope-skips map, and no macOS job is a suite job: skip=true (%s)"
                         % text.strip()[-200:])


class MacosJobsOffMergedPullRequest(LiveHead):
    """A merged lone-lane head whose newest checks.yml run is full: its macOS jobs never ran on the pull request, so each is skipped with no
    steps and is no suite job of the head. The newest run's scope and all-jobs-passed jobs still decide the skip."""

    def fake_for(self, changes, extra=()):
        """`extra` adds jobs of the same names beside the full run's, such as a second run of one job."""
        jobs = full_run_jobs(changes) + list(extra)
        fake = FakeGitHub(pulls=[lane_pull()], trees={LANE_HEAD: TREE}, workflow_runs=[pull_request_run(1)], jobs={1: jobs})
        return jobs, fake

    def test_a_merged_pull_request_whose_macos_jobs_never_ran_skips_the_push(self):
        jobs, fake = self.fake_for({})
        got = {job["name"]: job["conclusion"] for job in jobs}
        self.assertEqual({name: got.get(name) for name in MACOS_JOBS}, {name: "skipped" for name in MACOS_JOBS},
                         "the newest run must skip each macOS job, as a pull_request does now")
        self.assertEqual((got.get(SCOPE_JOB), got.get(ROLLUP_NAME)), ("success", "success"),
                         "the fixture's scope and all-jobs-passed jobs must succeed")
        value, text = self.skip_on(fake=fake)
        self.assertEqual(value, "true", "the macOS jobs never ran on the pull request, and every suite job passed: skip=true (%s)"
                         % text.strip()[-200:])

    def test_each_macos_job_skipped_alone_on_a_merged_pull_request_skips(self):
        for name in MACOS_JOBS:
            with self.subTest(job=name):
                _, fake = self.fake_for({name: {"conclusion": "skipped", "steps": []}})
                value, _ = self.skip_on(fake=fake)
                self.assertEqual(value, "true", "%s is skipped on the newest run and is no suite job of the head: skip=true" % name)

    def test_a_skipped_suite_job_beside_the_skipped_macos_jobs_runs(self):
        name = "checks-windows-rest"
        self.assertIn(name, SUITE_JOBS, "%s is not a suite job of checks.yml, so this case probes the wrong job" % name)
        _, fake = self.fake_for({name: {"conclusion": "skipped", "steps": []}})
        value, _ = self.skip_on(fake=fake)
        self.assertEqual(value, "false", "%s was skipped and is a suite job, so the push runs: skip=false" % name)

    def test_a_failed_rollup_job_runs(self):
        _, fake = self.fake_for({ROLLUP_NAME: {"conclusion": "failure"}})
        value, _ = self.skip_on(fake=fake)
        self.assertEqual(value, "false", "all-jobs-passed failed on the newest run, so it judged no skip: skip=false")

    def test_no_rollup_job_runs(self):
        _, fake = self.fake_for({ROLLUP_NAME: None})
        value, _ = self.skip_on(fake=fake)
        self.assertEqual(value, "false", "the newest run has no all-jobs-passed job, so no rollup judged the skip: skip=false")


def records_only_changes(scope="success", rollup="success"):
    """full_run_jobs changes for a records-only pull request run: every suite job skipped with no steps. `scope` and `rollup` are the
    conclusions of the scope and all-jobs-passed jobs. None leaves that job out."""
    changes = {name: {"conclusion": "skipped", "steps": []} for name in SUITE_JOBS}
    changes[SCOPE_JOB] = None if scope is None else {"conclusion": scope}
    changes[ROLLUP_NAME] = None if rollup is None else {"conclusion": rollup}
    return changes


def records_only_check_runs(scope="success", rollup="success"):
    """The same records-only run as the check runs of a batch head. None leaves that run out."""
    changes = {name: {"conclusion": "skipped"} for name in SUITE_JOBS}
    changes[SCOPE_JOB] = None if scope is None else {"conclusion": scope}
    changes[ROLLUP_NAME] = None if rollup is None else {"conclusion": rollup}
    return ready_head_runs(changes)


def records_only_lone_fake(jobs):
    """A merged lone-lane head whose newest checks.yml pull request run has these jobs."""
    return lone_lane_fake([pull_request_run(1)], {1: jobs})


class RecordsOnlyRun(LiveHead):
    """A records-only run: a pull request run whose change is records only. Its scope job succeeded, every suite job was skipped with no
    steps, and all-jobs-passed succeeded. The rollup passes those skips only when its records_only_skip output is "true"
    (actions/all-jobs-passed/check.sh). push-skip cannot read that output, since the REST jobs read carries no job outputs. So the
    rollup's success is the visible form of the flag, and the unset control is the same skips with all-jobs-passed failed.
    The two red cases are the two paths push-skip reads a pull request run on. Each control is a gap on the old code too."""

    def shape(self, rows, scope, rollup):
        """The fixture's scope and all-jobs-passed conclusions, and every suite job skipped. Asserted before the verdict."""
        got = {row["name"]: row["conclusion"] for row in rows}
        self.assertEqual((got.get(SCOPE_JOB), got.get(ROLLUP_NAME)), (scope, rollup),
                         "the fixture's scope and all-jobs-passed must be %s and %s" % (scope, rollup))
        self.assertEqual({name: got.get(name) for name in SUITE_JOBS}, {name: "skipped" for name in SUITE_JOBS},
                         "the fixture must skip every suite job")

    def assert_gap(self, scope, rollup, cause):
        """On both paths the same records-only shape, with this scope and rollup conclusion, stays a gap: skip=false."""
        jobs = full_run_jobs(records_only_changes(scope, rollup))
        runs = records_only_check_runs(scope, rollup)
        for path, rows, source in (("merged pull request", jobs, {"fake": records_only_lone_fake(jobs)}), ("batch head", runs, {"runs": runs})):
            with self.subTest(path=path):
                self.shape(rows, scope, rollup)
                value, text = self.skip_on(**source)
                self.assertEqual(value, "false", "%s: %s, so its skipped suite jobs are gaps: skip=false (%s)" % (path, cause, text.strip()[-200:]))

    def test_a_records_only_merged_pull_request_run_skips_the_push(self):
        jobs = full_run_jobs(records_only_changes())
        self.shape(jobs, "success", "success")
        value, text = self.skip_on(fake=records_only_lone_fake(jobs))
        self.assertEqual(value, "true", "a records-only merged pull request run passed, so its skipped suite jobs are proven and the push skips: skip=true (%s)"
                         % text.strip()[-200:])

    def test_a_records_only_batch_head_run_skips_the_push(self):
        runs = records_only_check_runs()
        self.shape(runs, "success", "success")
        value, text = self.skip_on(runs)
        self.assertEqual(value, "true", "a records-only batch head run passed, so its skipped suite jobs are proven and the push skips: skip=true (%s)"
                         % text.strip()[-200:])

    def test_the_records_only_shape_with_a_failed_rollup_stays_a_gap(self):
        self.assert_gap("success", "failure", "all-jobs-passed failed, which is what an unset records_only_skip gives")

    def test_the_records_only_shape_with_a_failed_scope_run_stays_a_gap(self):
        self.assert_gap("failure", "success", "the scope run failed, so the flags the skips rest on are not known")

    def test_the_records_only_shape_with_no_scope_run_stays_a_gap(self):
        self.assert_gap(None, "success", "there is no scope run, so the flags the skips rest on are not known")


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


class MismatchReason(LiveHead):
    """A merged lone lane whose head tree is not the push's covers nothing, and the output says so in one line: the pull request's number,
    the push's tree and the head's tree (both short), and that no run proved the push tree. Skip stays false. The control is the same
    pull request on the push's tree: it skips, and its output never says that no run proved the push tree."""

    def test_a_merged_pull_request_with_another_tree_names_the_reason_in_one_line(self):
        fake = lone_lane_fake([pull_request_run(1)], {1: full_run_jobs()}, tree=OTHER_TREE)
        self.assertNotEqual(fake.trees[LANE_HEAD], TREE, "the fixture's tree must differ from the push's, or it proves nothing")
        value, text = self.skip_on(fake=fake)
        self.assertEqual(value, "false", "a merged pull request whose tree is not the push's covers nothing: skip=false (%s)" % text.strip()[-200:])
        lines = reason_lines(text, str(LANE_NUMBER))
        self.assertEqual(len(lines), 1, "the tree mismatch must name pull request %d in one line, got %s" % (LANE_NUMBER, text.strip()[-200:]))
        self.assertIn(TREE[:7], lines[0], "the reason must name the push's tree, short: %s" % lines[0])
        self.assertIn(OTHER_TREE[:7], lines[0], "the reason must name the pull request head's tree, short: %s" % lines[0])
        self.assertIn("no run proved the push tree", lines[0], "the reason must say that no run proved the push tree: %s" % lines[0])

    def test_a_merged_pull_request_on_the_push_tree_skips_and_never_says_no_run_proved_it(self):
        value, text = self.skip_on(fake=lone_lane_fake([pull_request_run(1)], {1: full_run_jobs()}))
        self.assertEqual(value, "true", "the control: a merged pull request on the push's tree with a green run skips (%s)" % text.strip()[-200:])
        self.assertNotIn("no run proved the push tree", text, "a skip proved the push tree, so the output must not say no run did: %s" % text.strip()[-200:])


class CancelledRunProof(LiveHead):
    """A lone lane's newest checks.yml pull request run that concluded cancelled. A cancel of the fan-in job (ci-done) that lands after the
    jobs passed leaves all-jobs-passed and every suite job succeeded, and that run proves the head, so the push skips. The controls are
    the refusals the proof keeps: all-jobs-passed missing or not success, a suite job not success, a run still in progress, and a failed
    run whose jobs read green. The green twin is a run that concluded success."""

    def run_on_lane(self, conclusion, status="completed", changes=None):
        """The lone lane's one checks.yml run, with this conclusion and status and the jobs `changes` makes. Returns (value, text)."""
        return self.skip_on(fake=lone_lane_fake([pull_request_run(1, conclusion=conclusion, status=status)], {1: full_run_jobs(changes)}))

    def test_a_cancelled_run_whose_all_jobs_passed_and_suite_jobs_succeeded_proves_the_head(self):
        changes = {FAN_IN: {"conclusion": "cancelled", "steps": []}}
        got = {job["name"]: job["conclusion"] for job in full_run_jobs(changes)}
        self.assertEqual(got[FAN_IN], "cancelled", "the fixture's ci-done must be cancelled, or it proves nothing")
        self.assertEqual(got[ROLLUP_NAME], "success", "the fixture's all-jobs-passed must succeed, or it proves nothing")
        self.assertEqual({name: got[name] for name in SUITE_JOBS}, {name: "success" for name in SUITE_JOBS},
                         "the fixture's every suite job must succeed, or it proves nothing")
        value, text = self.run_on_lane("cancelled", changes=changes)
        self.assertEqual(value, "true", "a cancelled pull request run whose all-jobs-passed and every suite job succeeded proves the head, "
                         "so the push skips (%s)" % text.strip()[-200:])

    def test_the_green_twin_a_run_that_concluded_success_still_skips(self):
        value, text = self.run_on_lane("success", changes={FAN_IN: {"conclusion": "success", "steps": []}})
        self.assertEqual(value, "true", "the control: a completed green run with the same jobs skips (%s)" % text.strip()[-200:])

    def test_a_cancelled_run_whose_all_jobs_passed_is_missing_or_not_success_still_refuses(self):
        for label, rollup in (("missing", None), ("failure", {"conclusion": "failure", "steps": []}),
                              ("cancelled", {"conclusion": "cancelled", "steps": []})):
            with self.subTest(all_jobs_passed=label):
                value, text = self.run_on_lane("cancelled", changes={FAN_IN: {"conclusion": "cancelled", "steps": []}, ROLLUP_NAME: rollup})
                self.assertEqual(value, "false", "a cancelled run whose all-jobs-passed is %s has no proof of the head: skip=false (%s)"
                                 % (label, text.strip()[-200:]))

    def test_a_cancelled_run_with_a_suite_job_not_success_still_refuses(self):
        self.assertIn("checks-windows-rest", SUITE_JOBS, "the fixture's suite job must be a suite job of checks.yml, or it proves nothing")
        for conclusion in ("failure", "cancelled"):
            with self.subTest(suite_job=conclusion):
                changes = {FAN_IN: {"conclusion": "cancelled", "steps": []}, "checks-windows-rest": {"conclusion": conclusion, "steps": []}}
                value, text = self.run_on_lane("cancelled", changes=changes)
                self.assertEqual(value, "false", "a suite job that concluded %s is a gap, so the cancelled run proves nothing: skip=false (%s)"
                                 % (conclusion, text.strip()[-200:]))

    def test_a_run_still_in_progress_refuses_though_its_jobs_read_green(self):
        value, text = self.run_on_lane(None, status="in_progress")
        self.assertEqual(value, "false", "a run still in progress has no result yet, so its green jobs prove nothing: skip=false (%s)"
                         % text.strip()[-200:])

    def test_a_failed_run_refuses_though_its_jobs_read_green(self):
        value, text = self.run_on_lane("failure")
        self.assertEqual(value, "false", "a failed run is no green run, whatever its jobs read: skip=false (%s)" % text.strip()[-200:])


class SilentRefusals(LiveHead):
    """A skip=false that printed nothing about why. Each case is a read the script refused with no reason, and its reason names what
    refused it: a push no pull request covers (the push tree, short); a batch head on another tree (its branch and tree, short); a batch
    head whose all-jobs-passed is not success (its branch and the result); a merged lone lane that was not merged (its number). Each
    control is the same read green, and it skips."""

    def test_a_push_no_pull_request_covers_names_the_push_tree_in_its_reason(self):
        value, text = self.skip_on(fake=FakeGitHub(pulls=[]))
        self.assertEqual(value, "false", "no pull request covers the push: skip=false (%s)" % text.strip()[-200:])
        self.assertTrue(reason_lines(text, TREE[:7]), "a push no pull request covers must print why, naming the push tree (short): got %s"
                        % text.strip()[-200:])

    def test_a_batch_head_on_another_tree_names_its_branch_and_tree_in_its_reason(self):
        fake = FakeGitHub(ready_head_runs(), trees={HEAD: OTHER_TREE})
        self.assertNotEqual(fake.trees[HEAD], TREE, "the fixture's batch head tree must differ from the push's, or it proves nothing")
        value, text = self.skip_on(fake=fake)
        self.assertEqual(value, "false", "a batch head on another tree covers nothing: skip=false (%s)" % text.strip()[-200:])
        lines = reason_lines(text, BATCH)
        self.assertTrue(lines, "a batch head whose tree is not the push's must print why, naming its branch %s: got %s" % (BATCH, text.strip()[-200:]))
        self.assertIn(OTHER_TREE[:7], lines[0], "the reason must name the batch head's tree, short: %s" % lines[0])

    def test_a_batch_head_whose_all_jobs_passed_failed_names_its_branch_and_result_in_its_reason(self):
        value, text = self.skip_on(fake=FakeGitHub(ready_head_runs({ROLLUP_NAME: {"conclusion": "failure"}})))
        self.assertEqual(value, "false", "a batch head whose all-jobs-passed failed is no proof: skip=false (%s)" % text.strip()[-200:])
        lines = reason_lines(text, BATCH)
        self.assertTrue(lines, "a batch head whose all-jobs-passed failed must print why, naming its branch %s: got %s" % (BATCH, text.strip()[-200:]))
        self.assertTrue(any(word in lines[0] for word in ("failure", "failed")), "the reason must name the all-jobs-passed result it refused: %s" % lines[0])

    def test_a_batch_head_whose_all_jobs_passed_is_still_running_names_its_state_in_its_reason(self):
        value, text = self.skip_on(fake=FakeGitHub(ready_head_runs({ROLLUP_NAME: {"status": "in_progress", "conclusion": None}})))
        self.assertEqual(value, "false", "a batch head whose all-jobs-passed is still running is no proof: skip=false (%s)" % text.strip()[-200:])
        lines = reason_lines(text, BATCH)
        self.assertTrue(lines, "a batch head whose all-jobs-passed is still running must print why, naming its branch %s: got %s" % (BATCH, text.strip()[-200:]))
        self.assertTrue(any(word in lines[0] for word in ("in_progress", "in progress")), "the reason must name the running all-jobs-passed: %s" % lines[0])

    def test_an_unmerged_lone_lane_pull_request_names_its_number_and_that_it_is_not_merged(self):
        fake = lone_lane_fake([pull_request_run(1)], {1: full_run_jobs()}, pulls=[lane_pull(merged_at=None)])
        self.assertIsNone(fake.pulls[0]["merged_at"], "the fixture's pull request must be unmerged, or it proves nothing")
        value, text = self.skip_on(fake=fake)
        self.assertEqual(value, "false", "a pull request that was not merged is no proof for main: skip=false (%s)" % text.strip()[-200:])
        lines = reason_lines(text, str(LANE_NUMBER))
        self.assertTrue(lines, "an unmerged pull request must print why, naming its number %d: got %s" % (LANE_NUMBER, text.strip()[-200:]))
        self.assertIn("merged", lines[0], "the reason must say the pull request was not merged: %s" % lines[0])

    def test_the_green_twin_a_matching_green_batch_head_still_skips(self):
        value, text = self.skip_on(fake=FakeGitHub(ready_head_runs()))
        self.assertEqual(value, "true", "the control: a green batch head on the push's tree skips (%s)" % text.strip()[-200:])

    def test_the_green_twin_a_merged_lone_lane_on_the_push_tree_still_skips(self):
        value, text = self.skip_on(fake=lone_lane_fake([pull_request_run(1)], {1: full_run_jobs()}))
        self.assertEqual(value, "true", "the control: a merged lone lane on the push's tree with a green run skips (%s)" % text.strip()[-200:])


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

    def test_scope_needs_push_skip_so_a_skipped_push_skips_every_job_through_needs(self):
        needs = needs_of(job_block(self.text, "scope")) or []
        self.assertIn(JOB, needs, f"scope does not need {JOB}, so a matching push would not skip the other jobs")


OLDER = "1" * 40  # the head of an older green push run: the base that a newer run which is red, skipped or still going must not hide
NEWER = "2" * 40  # the head of a newer push run


def push_run(id_, head, conclusion="success", status="completed", created_at=EARLY, path=RUN_PATH, event="push", branch="main"):
    """One checks.yml run of a push to main, in the shape the runs read returns."""
    return {"id": id_, "name": "checks", "path": path, "event": event, "head_branch": branch, "head_sha": head, "status": status,
            "conclusion": conclusion, "created_at": created_at, "run_attempt": 1}


def skipped_whole_jobs():
    """The jobs of a push run that push-skip skipped whole: push-skip succeeded, and scope, all-jobs-passed and every suite job skipped."""
    changes = {name: {"conclusion": "skipped", "steps": []} for name in SUITE_JOBS}
    changes[SCOPE_JOB] = {"conclusion": "skipped", "steps": []}
    changes[ROLLUP_NAME] = {"conclusion": "skipped", "steps": []}
    return full_run_jobs(changes)


def half_ran_jobs():
    """The jobs of a push run whose suites partly ran: the first half of the suite jobs passed and the rest were skipped by scope."""
    return full_run_jobs({name: {"conclusion": "skipped", "steps": []} for name in SUITE_JOBS[len(SUITE_JOBS) // 2:]})


class ProvenBase(LiveHead):
    """main() on a push with no pull request, so the one runs read is the base search. The base output is the head of the newest
    completed, successful checks.yml run of main whose suites ran. A run with every suite job skipped is no base (push-skip skipped
    it whole), and a newer run still queued or in progress is unread, so it gives no base. A completed red or cancelled run newer than the base gives no base, because main
    is then not known green. This run's own record never counts. Each case reads the base output through main(), the entry point the
    job runs, and each failure names the claim that did not hold. The output must be written on every path: empty is a value."""

    def base_on(self, runs=None, jobs=None, fake=None, extra_env=None):
        """main() on the push, with FakeGitHub answering. -> (the base output's value, or None when no base line was
        written; the text printed)."""
        self.assertTrue(os.path.isfile(PUSH_SKIP), SCRIPT_MISSING)
        module = load_script()
        fake = fake if fake is not None else FakeGitHub(pulls=[], workflow_runs=runs, jobs=jobs)
        out = os.path.join(RUN_FOLDER, "output-%s" % uuid.uuid4().hex)
        env = {"EVENT": "push", "GH_TOKEN": "t", "REPO": REPO, "HEAD_SHA": SHA, "PUSH_TREE": TREE, "GITHUB_OUTPUT": out, **(extra_env or {})}
        printed = io.StringIO()
        with mock.patch.object(module._nightly_skip(), "api_get", side_effect=fake), contextlib.redirect_stdout(printed):
            code = module.main(env)
        self.assertEqual(fake.unexpected, [], "the script read a path no case expects, so the case cannot judge it")
        self.assertEqual(code, 0, "main exits %d, so the push job fails on the decision" % code)
        bases = []
        if os.path.isfile(out):
            with open(out, encoding="utf-8") as f:
                bases = [line.strip()[len("base="):] for line in f if line.startswith("base=")]
        return (bases[0] if len(bases) == 1 else None), printed.getvalue()

    def assert_base(self, base, want, claim):
        if base is None:
            self.fail("%s: the push wrote no base output line, so the scoped run has no base for it" % claim)
        self.assertEqual(base, want, "%s: the base output must be %r, got %r" % (claim, want, base))

    def test_the_newest_green_push_run_is_the_base(self):
        runs = [push_run(2, NEWER, created_at=LATE), push_run(1, OLDER, created_at=EARLY)]
        base, _ = self.base_on(runs, jobs={1: full_run_jobs(), 2: full_run_jobs()})
        self.assert_base(base, NEWER, "the newest completed, successful push run of checks.yml on main is the base")

    def test_a_green_push_run_whose_suites_partly_ran_is_a_base(self):
        base, _ = self.base_on([push_run(1, OLDER, created_at=EARLY)], jobs={1: half_ran_jobs()})
        self.assert_base(base, OLDER, "a green push run with some suite jobs skipped still ran its suites, so it is the base")

    def test_a_push_run_skipped_whole_by_push_skip_is_never_the_base(self):
        runs = [push_run(2, NEWER, created_at=LATE), push_run(1, OLDER, created_at=EARLY)]
        jobs = {1: full_run_jobs(), 2: skipped_whole_jobs()}
        got = {job["name"]: job["conclusion"] for job in jobs[2]}
        self.assertEqual({name: got[name] for name in SUITE_JOBS}, {name: "skipped" for name in SUITE_JOBS},
                         "the fixture must skip every suite job of the newer run, or it proves nothing")
        self.assertEqual(got.get("push-skip"), "success", "the fixture's push-skip must succeed, as a skipped push run's does")
        base, _ = self.base_on(runs, jobs=jobs)
        self.assert_base(base, OLDER, "the newer run is green but every suite job was skipped whole, so the search goes on to the older run")

    def test_a_newer_red_or_cancelled_push_run_gives_no_base(self):
        for conclusion in ("failure", "cancelled"):
            with self.subTest(conclusion=conclusion):
                runs = [push_run(2, NEWER, conclusion=conclusion, created_at=LATE), push_run(1, OLDER, created_at=EARLY)]
                base, _ = self.base_on(runs, jobs={1: full_run_jobs(), 2: full_run_jobs()})
                self.assert_base(base, "", "a completed push run that ended %s is newer than the base, so main is not known green" % conclusion)
                twin, _ = self.base_on([push_run(1, OLDER, created_at=EARLY)], jobs={1: full_run_jobs()})
                self.assert_base(twin, OLDER, "the control: without the %s run, the older green run is the base" % conclusion)

    def test_a_newer_queued_or_in_progress_push_run_gives_no_base(self):
        # Consultant's pick, 07:10 CST Nov 24 2026: a newer push run of main still queued or in progress is unread, so it gives no
        # base and every flag stays on. The older green run is not used, and the reason line names the run it could not read.
        for status in ("in_progress", "queued"):
            with self.subTest(status=status):
                runs = [push_run(2, NEWER, conclusion=None, status=status, created_at=LATE), push_run(1, OLDER, created_at=EARLY)]
                base, text = self.base_on(runs, jobs={1: full_run_jobs()})
                self.assert_base(base, "", "a %s push run newer than the candidate is unread (consultant's pick, 07:10 CST Nov 24 2026), so the push has no base" % status)
                self.assertIn("push run 2", text, "the reason line must name the newer run it could not read: %s" % text.strip()[-200:])
                self.assertIn(status, text, "the reason line must say the newer run is %s: %s" % (status, text.strip()[-200:]))
                twin, _ = self.base_on([push_run(1, OLDER, created_at=EARLY)], jobs={1: full_run_jobs()})
                self.assert_base(twin, OLDER, "the control: with no newer unfinished run, the older green run is the base")

    def test_this_runs_own_record_never_counts(self):
        runs = [push_run(2, NEWER, created_at=LATE), push_run(1, OLDER, created_at=EARLY)]
        jobs = {1: full_run_jobs(), 2: full_run_jobs()}
        base, _ = self.base_on(runs, jobs=jobs, extra_env={"GITHUB_RUN_ID": "2"})
        self.assert_base(base, OLDER, "run 2 is this run: its record reads green, and it is no base for itself")
        twin, _ = self.base_on(runs, jobs=jobs)
        self.assert_base(twin, NEWER, "the control: with no GITHUB_RUN_ID, the same green run 2 is the base")

    def test_this_runs_own_unfinished_record_is_passed_over(self):
        # push-skip reads the runs while this run is still going, so its own record is queued or in progress. It is passed over, and the
        # older green run is the base. The control is the same unfinished run without GITHUB_RUN_ID: it is another run, so it is unread.
        own_id = 2
        for status in ("in_progress", "queued"):
            with self.subTest(status=status):
                runs = [push_run(own_id, NEWER, conclusion=None, status=status, created_at=LATE), push_run(1, OLDER, created_at=EARLY)]
                jobs = {1: full_run_jobs()}
                base, text = self.base_on(runs, jobs=jobs, extra_env={"GITHUB_RUN_ID": str(own_id)})
                self.assert_base(base, OLDER, "this run's own record is %s, so it is passed over and the older green push run is the base: %s"
                                 % (status, text.strip()[-200:]))
                twin, _ = self.base_on(runs, jobs=jobs)
                self.assert_base(twin, "", "the control: the same %s run, not named by GITHUB_RUN_ID, is unread, so the push has no base" % status)

    def test_an_unfinished_run_of_another_workflow_is_passed_over(self):
        jobs = {1: full_run_jobs()}
        other = [push_run(2, NEWER, conclusion=None, status="in_progress", created_at=LATE, path=OTHER_PATH), push_run(1, OLDER, created_at=EARLY)]
        base, _ = self.base_on(other, jobs=jobs)
        self.assert_base(base, OLDER, "an in-progress run of another workflow is no base and is passed over, so the older green run of checks.yml is the base")
        twin = [push_run(2, NEWER, conclusion=None, status="in_progress", created_at=LATE), push_run(1, OLDER, created_at=EARLY)]
        got, _ = self.base_on(twin, jobs=jobs)
        self.assert_base(got, "", "the control: the same unfinished run of checks.yml is unread, so the push has no base")

    def test_an_unfinished_schedule_pull_request_or_dispatch_run_is_passed_over(self):
        # The fake returns the run whatever its event, so the script's own event filter is what passes it over.
        jobs = {1: full_run_jobs()}
        for label, event in (("a schedule run", "schedule"), ("a pull_request run", "pull_request"), ("a dispatch run", "workflow_dispatch")):
            with self.subTest(run=label):
                runs = [push_run(2, NEWER, conclusion=None, status="in_progress", created_at=LATE, event=event), push_run(1, OLDER, created_at=EARLY)]
                fake = FakeGitHub(pulls=[], workflow_runs=runs, jobs=jobs, ignore_query=("event", "branch"))
                base, _ = self.base_on(fake=fake)
                self.assert_base(base, OLDER, "%s in progress is no push run, so it is passed over and the older green push run is the base" % label)
                twin = [push_run(2, NEWER, conclusion=None, status="in_progress", created_at=LATE), push_run(1, OLDER, created_at=EARLY)]
                got, _ = self.base_on(twin, jobs=jobs)
                self.assert_base(got, "", "the control: the same unfinished run as a push run is unread, so the push has no base")

    def test_an_unfinished_push_run_on_another_branch_is_passed_over(self):
        runs = [push_run(2, NEWER, conclusion=None, status="in_progress", created_at=LATE, branch="lane-x"), push_run(1, OLDER, created_at=EARLY)]
        fake = FakeGitHub(pulls=[], workflow_runs=runs, jobs={1: full_run_jobs()}, ignore_query=("event", "branch"))
        base, _ = self.base_on(fake=fake)
        self.assert_base(base, OLDER, "an in-progress push run on another branch is no base for main and is passed over, so the older green run is the base")

    def test_a_schedule_pull_request_or_dispatch_run_another_workflow_or_another_branch_is_no_base(self):
        others = (("a schedule run", {"event": "schedule"}), ("a pull_request run", {"event": "pull_request"}),
                  ("a dispatch run", {"event": "workflow_dispatch"}), ("a run of another workflow", {"path": OTHER_PATH}),
                  ("a push run on another branch", {"branch": "lane-x"}))
        jobs = {1: full_run_jobs(), 2: full_run_jobs()}
        for label, kind in others:
            with self.subTest(run=label):
                runs = [push_run(2, NEWER, created_at=LATE, **kind), push_run(1, OLDER, created_at=EARLY)]
                fake = FakeGitHub(pulls=[], workflow_runs=runs, jobs=jobs, ignore_query=("event", "branch"))
                base, _ = self.base_on(fake=fake)
                self.assert_base(base, OLDER, "%s is no base, so the older green push run on main is the base" % label)

    def test_a_read_error_a_malformed_reply_or_a_full_page_with_no_usable_run_gives_no_base_and_says_unknown(self):
        full = [push_run(i, NEWER, conclusion=None, status="in_progress", created_at=LATE) for i in range(1, 101)]
        replies = (
            ("a read error", FakeGitHub(pulls=[], runs_fail=http.client.IncompleteRead(b"partial"))),
            ("a reply with no run list", FakeGitHub(pulls=[], runs_reply={"total_count": 1})),
            ("a reply that is a list", FakeGitHub(pulls=[], runs_reply=["not a body"])),
            ("a run entry that is not an object", FakeGitHub(pulls=[], runs_reply={"workflow_runs": ["not a run"]})),
            ("a full page with no usable run", FakeGitHub(pulls=[], workflow_runs=full)),
        )
        for label, fake in replies:
            with self.subTest(reply=label):
                base, text = self.base_on(fake=fake)
                self.assert_base(base, "", "%s gives no base" % label)
                self.assertIn("unknown", text.lower(), "%s must print a line that says unknown, got %s" % (label, text.strip()[-200:]))

    def test_a_full_page_holding_a_newer_unfinished_run_gives_no_base(self):
        # The page holds 99 newer runs still going. Each is unread (consultant's pick, 07:10 CST Nov 24 2026), so the usable green run
        # below them is no base. The control is the same page with those runs finished: the newest green run is the base.
        page = [push_run(i, NEWER, conclusion=None, status="in_progress", created_at=LATE) for i in range(1, 100)]
        page.append(push_run(100, OLDER, created_at=EARLY))
        base, _ = self.base_on(fake=FakeGitHub(pulls=[], workflow_runs=page, jobs={100: full_run_jobs()}))
        self.assert_base(base, "", "a newer run still in progress on a full page is unread (consultant's pick, 07:10 CST Nov 24 2026), so the push has no base")
        done = [push_run(i, NEWER, created_at=EARLY) for i in range(1, 100)] + [push_run(100, OLDER, created_at=LATE)]
        twin, _ = self.base_on(fake=FakeGitHub(pulls=[], workflow_runs=done, jobs={100: full_run_jobs()}))
        self.assert_base(twin, OLDER, "the control: a full page of finished runs gives its newest green run as the base")

    def test_a_full_page_of_green_runs_all_skipped_whole_reads_unknown_and_gives_no_base(self):
        # Every run on the page is completed and green, and push-skip skipped each one whole, so no run on it is usable. An older run may
        # sit past the page, so the read is unknown. The control puts one usable run at the page's end, and that run is the base.
        page = [push_run(i, OLDER, created_at=LATE) for i in range(1, 101)]
        jobs = {i: skipped_whole_jobs() for i in range(1, 101)}
        fake = FakeGitHub(pulls=[], workflow_runs=page, jobs=jobs)
        base, text = self.base_on(fake=fake)
        self.assertEqual(len([path for path in fake.reads if path.endswith("/jobs")]), 100,
                         "the fixture must walk all 100 runs of the page, or it does not reach the full-page arm")
        self.assert_base(base, "", "a full page with no usable run may hide an older run, so the push has no base")
        self.assertIn("unknown", text.lower(), "a full page with no usable run must print a line that says unknown, got %s" % text.strip()[-200:])
        with_end = [push_run(i, OLDER, created_at=LATE) for i in range(1, 100)] + [push_run(100, NEWER, created_at=EARLY)]
        end_jobs = {i: skipped_whole_jobs() for i in range(1, 100)}
        end_jobs[100] = full_run_jobs()
        twin, _ = self.base_on(with_end, jobs=end_jobs)
        self.assert_base(twin, NEWER, "the control: the same full page with one usable run last gives that run as the base")

    def test_a_full_page_of_jobs_for_a_candidate_run_is_unknown_and_gives_no_base(self):
        # One job the read did not return may be a suite job that failed, so a full page of jobs is unknown and the candidate gives no base.
        jobs = [job_row("job-%d" % i) for i in range(99)] + [job_row(SUITE_JOBS[0])]
        base, text = self.base_on([push_run(1, OLDER, created_at=EARLY)], jobs={1: jobs})
        self.assert_base(base, "", "a full page of jobs may hide a failed suite job, so the candidate gives no base")
        self.assertIn("unknown", text.lower(), "the full page must print a line that says unknown, got %s" % text.strip()[-200:])
        twin, _ = self.base_on([push_run(1, OLDER, created_at=EARLY)], jobs={1: [job_row(SUITE_JOBS[0])]})
        self.assert_base(twin, OLDER, "the control: the same suite job on a short page gives the candidate as the base")

    def test_the_base_is_a_full_hex_sha_or_empty_never_a_short_or_symbolic_ref(self):
        for head in ("1234567", "main", "refs/heads/main", "G" * 40):
            with self.subTest(head=head):
                base, _ = self.base_on([push_run(1, head, created_at=EARLY)], jobs={1: full_run_jobs()})
                self.assert_base(base, "", "a head_sha of %r is no full sha, so the output must be empty" % head)
        base, _ = self.base_on([push_run(1, OLDER, created_at=EARLY)], jobs={1: full_run_jobs()})
        self.assert_base(base, OLDER, "the control: a full 40-hex head_sha is written as the base")


class ProvenBaseWiring(unittest.TestCase):
    """checks.yml hands push-skip's proven base to scope (decision push-skip-on-proven-tree). Each case reads checks.yml with the repo's
    reader, and the scope job's BASE_SHA is resolved with the repo's `if:`/value evaluator, for each event. Each case was shown red by a
    mutant of the workflow text, made in the copy red-run makes, so a cut in that wiring fails its own case."""
    PR_BASE = "3" * 40  # the pull request's base sha, as github.event.pull_request.base.sha carries it
    PUSH_BASE = "4" * 40  # the base push-skip's decide step writes on a push

    def setUp(self):
        with open(CHECKS, encoding="utf-8") as f:
            self.text = f.read()

    def scope_steps(self):
        return step_blocks(job_block(self.text, "scope") or "")

    def resolve(self, event, pr_base, push_base):
        """BASE_SHA of the scope job's detect step, as GitHub resolves it for `event`: pr_base is the pull request's base sha (None off a
        pull request) and push_base is the value of needs.push-skip.outputs.base."""
        steps = [s for s in self.scope_steps() if step_key(s, "id") == "scope"]
        self.assertEqual(len(steps), 1, "the scope job must have one step with id scope")
        expr = step_env(steps[0]).get("BASE_SHA")
        self.assertIsNotNone(expr, "the scope step sets no BASE_SHA, so the scope job reads no base")
        expr = expr.replace("github.event.pull_request.base.sha", repr(pr_base))
        got = eval_value(expr, event, "", outputs={PUSH_SKIP_JOB: {"base": push_base}})
        return "" if got is None else got  # GitHub renders a null or unset value in an env as the empty string

    def test_push_skip_exposes_its_decision_base_as_a_job_output(self):
        outputs = job_outputs_of(self.text, PUSH_SKIP_JOB)
        self.assertEqual(outputs.get("base"), "${{ steps.decide.outputs.base }}",
                         f"{PUSH_SKIP_JOB} does not expose the base its decide step writes, so scope gets no proven base: {outputs}")

    def test_scope_base_is_the_pull_request_base_on_a_pull_request(self):
        got = self.resolve("pull_request", self.PR_BASE, self.PUSH_BASE)
        self.assertEqual(got, self.PR_BASE, "on a pull request BASE_SHA must be the pull request's base, got %r" % (got,))

    def test_scope_base_is_the_push_skip_base_output_on_a_push(self):
        got = self.resolve("push", None, self.PUSH_BASE)
        self.assertEqual(got, self.PUSH_BASE, "on a push BASE_SHA must be the push-skip base output, got %r" % (got,))

    def test_scope_base_is_empty_on_a_schedule(self):
        got = self.resolve("schedule", None, self.PUSH_BASE)
        self.assertEqual(got, "", "a schedule run never scopes, so BASE_SHA must be empty even with a push base, got %r" % (got,))

    def test_scope_base_is_empty_on_a_workflow_dispatch(self):
        got = self.resolve("workflow_dispatch", None, self.PUSH_BASE)
        self.assertEqual(got, "", "a dispatch run never scopes, so BASE_SHA must be empty even with a push base, got %r" % (got,))

    def test_scope_checks_out_with_full_history_so_the_base_is_in_the_clone(self):
        checkouts = [s for s in self.scope_steps() if "actions/checkout@" in s]
        self.assertEqual(len(checkouts), 1, f"the scope job has {len(checkouts)} checkout steps, want 1")
        self.assertEqual(step_with(checkouts[0]).get("fetch-depth"), "0",
                         "the scope checkout is not fetch-depth 0, so the proven base is not in the clone and the range does not read")


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    unittest.main()
