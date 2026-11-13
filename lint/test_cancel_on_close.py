#!/usr/bin/env python3
"""Guard for the PR-close cancel: .github/workflows/cancel-on-close.yml and .github/scripts/cancel_closed_pr_runs.py.

WorkflowShape reads the workflow by line, as lint/test_windows_split.py does, with the step parser of lint/workflow_steps.py.
ScriptSelects proves select_runs cancels only an unfinished pull_request run of this PR's head branch and head SHA, from
this repo, whose pull_requests list is empty or names this PR. ScriptSharedHead proves other_open_pr_shares_head finds
another open PR in this repo on the same head branch. ScriptPrClosed proves pr_is_closed reads only "closed".
ScriptGhCalls and ScriptMain prove every list call is a GET, main cancels nothing when another open PR shares the head,
main counts the runs it skips for naming only another PR, main reads the PR before it cancels, main excludes the run
named by GITHUB_RUN_ID, and main cancels nothing when GITHUB_RUN_ID is not numeric. ParserControl and ScannerTraps test
the readers in this file on text that exists on main, so a red WorkflowShape case points at the workflow, not at the
reader.

Run with:  python3 lint/test_cancel_on_close.py -v
"""
import contextlib
import importlib.util
import inspect
import io
import json
import os
import re
import subprocess
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "..")
sys.path.insert(0, HERE)
from workflow_steps import drop_comment, job_block, step_blocks, step_key, step_with  # noqa: E402  the one home of the step parser

WORKFLOW = os.path.join(REPO, ".github", "workflows", "cancel-on-close.yml")
SCRIPT = os.path.join(REPO, ".github", "scripts", "cancel_closed_pr_runs.py")
CONTROL_WORKFLOW = os.path.join(REPO, ".github", "workflows", "lane-touched-tests.yml")
SCRIPT_CALL = ".github/scripts/cancel_closed_pr_runs.py"
PR = 7
OTHER_PR = 8
REPO_FULL = "owner/repo"
OWNER = "owner"
DEFAULT = "main"
HEAD_REF = "feature"
HEAD_SHA = "3f1c0a9d2b7e4c6f8a0b1d2e3f4a5b6c7d8e9f01"
OLD_SHA = "9b8a7f6e5d4c3b2a1f0e9d8c7b6a5f4e3d2c1b0a"
ACTIVE = ("queued", "in_progress", "waiting", "pending", "requested")


def read_text(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def indent_of(line):
    return len(line) - len(line.lstrip(" "))


def is_blank_or_comment(line):
    return not line.strip() or line.lstrip().startswith("#")


def scalar(raw):
    """A scalar without its surrounding space and quotes."""
    s = raw.strip()
    return s[1:-1] if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"" else s


def key_entry(lines, key, indent):
    """(inline value, child lines) of `key:` at exactly `indent` spaces, or None when absent. The value loses its comment.
    The child lines are those under it that sit deeper than `indent`; blank and comment lines do not end them."""
    for i, line in enumerate(lines):
        if re.match(rf"^ {{{indent}}}{re.escape(key)}:", line):
            value = drop_comment(line[indent + len(key) + 1:].strip())
            kids = []
            for nxt in lines[i + 1:]:
                if not is_blank_or_comment(nxt) and indent_of(nxt) <= indent:
                    break
                kids.append(nxt)
            return value, kids
    return None


def map_at(lines, indent):
    """{key: inline value} for the `key:` lines at exactly `indent` spaces. A key with no inline value maps to ""."""
    out = {}
    for line in lines:
        m = re.match(r"^ {%d}([\w-]+):(.*)$" % indent, line)
        if m and not is_blank_or_comment(line):
            out[m.group(1)] = drop_comment(m.group(2).strip())
    return out


def flow_list(raw):
    """The items of a flow list `[a, b]`. A bare scalar is a list of one."""
    s = raw.strip()
    if s.startswith("[") and s.endswith("]"):
        return [scalar(item) for item in s[1:-1].split(",") if item.strip()]
    return [scalar(s)]


def flow_map(raw):
    """{name: value} from a flow map `{a: b, c: d}`."""
    body = raw.strip()[1:-1]
    return {scalar(part.split(":", 1)[0]): scalar(part.split(":", 1)[1]) for part in body.split(",") if ":" in part}


def mapping_at(lines, key, indent):
    """{name: value} of the mapping under `key:` at `indent`, in flow form or block form. None when the key is absent."""
    entry = key_entry(lines, key, indent)
    if entry is None:
        return None
    value, kids = entry
    if value.startswith("{"):
        return flow_map(value)
    if value:
        return {}
    return map_at(kids, indent + 2)


def types_of(trigger_lines):
    """The `types:` of one trigger, as a flow list or a block list. None when it names none."""
    entry = key_entry(trigger_lines, "types", 4)
    if entry is None:
        return None
    value, items = entry
    if value:
        return flow_list(value)
    return [scalar(drop_comment(ln.strip()[2:])) for ln in items if ln.strip().startswith("- ")]


def triggers(text):
    """{event: types or None} for each trigger under the top-level `on:`. None when `on:` is absent."""
    entry = key_entry(text.split("\n"), "on", 0)
    if entry is None:
        return None
    value, kids = entry
    if value:
        return {name: None for name in flow_list(value)}
    return {name: types_of(key_entry(kids, name, 2)[1]) for name in map_at(kids, 2)}


def job_names(text):
    entry = key_entry(text.split("\n"), "jobs", 0)
    return [] if entry is None else list(map_at(entry[1], 2))


def job_value(job, key):
    entry = key_entry(job.split("\n"), key, 4)
    return None if entry is None else entry[0]


def checkout_steps(job):
    return [st for st in step_blocks(job) if drop_comment(step_key(st, "uses") or "").startswith("actions/checkout@")]


def shell_code(line):
    """A shell line without its comment. A `#` that starts a word opens a comment, unless a quote opened before it. A quote
    opens only at the start of a word, so the lone quote in `don't` is text and hides no comment."""
    quote, word_start = "", True
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote, word_start = "", False
            continue
        if ch == "#" and word_start:
            return line[:i]
        if ch in "\"'" and word_start:
            quote, word_start = ch, False
            continue
        word_start = ch in " \t;&|()"
    return line


def run_shell_lines(step):
    """The shell lines a step runs, comments dropped. A one-line `run:` loses its YAML comment first; a block body keeps
    its lines until a line indented less than the body's 10 spaces."""
    lines = step.split("\n")
    for i, line in enumerate(lines):
        m = re.match(r"^(?:      - |        )run:[ \t]*(.*?)[ \t]*$", line)
        if not m:
            continue
        head = drop_comment(m.group(1))
        if head[:1] not in ("|", ">"):
            return [shell_code(head)]
        body = []
        for nxt in lines[i + 1:]:
            if nxt.strip() and indent_of(nxt) < 10:
                break
            body.append(nxt.strip())
        return [shell_code(ln) for ln in body if ln]
    return []


def calls_script(step):
    return any(SCRIPT_CALL in ln for ln in run_shell_lines(step))


def concurrency_of(text, job):
    """The `concurrency:` mapping: the top-level one, else the job's. None when neither has one."""
    top = mapping_at(text.split("\n"), "concurrency", 0)
    return top if top is not None else mapping_at(job.split("\n"), "concurrency", 4)


class WorkflowShape(unittest.TestCase):
    """The contract of .github/workflows/cancel-on-close.yml."""

    def text(self):
        self.assertTrue(os.path.isfile(WORKFLOW), "the workflow .github/workflows/cancel-on-close.yml is absent")
        return read_text(WORKFLOW)

    def job(self):
        # Scope first: the job-level cases read the one job, so the count is asserted before its fields.
        text = self.text()
        names = job_names(text)
        self.assertEqual(len(names), 1, f"the workflow has {len(names)} jobs, want exactly one: {names}")
        return job_block(text, names[0])

    def test_workflow_file_exists(self):
        self.assertTrue(os.path.isfile(WORKFLOW), "the workflow .github/workflows/cancel-on-close.yml is absent")

    def test_trigger_names_no_event_but_pull_request(self):
        self.assertEqual(sorted(triggers(self.text()) or {}), ["pull_request"],
                         "the workflow's events are not only pull_request")

    def test_trigger_has_no_pull_request_target(self):
        self.assertNotIn("pull_request_target", triggers(self.text()) or {},
                         "the workflow triggers on pull_request_target")

    def test_pull_request_is_triggered_on_closed_only(self):
        self.assertEqual((triggers(self.text()) or {}).get("pull_request"), ["closed"],
                         "the pull_request types are not [closed] only")

    def test_top_level_permissions_are_contents_read(self):
        perms = mapping_at(self.text().split("\n"), "permissions", 0)
        self.assertIsNotNone(perms, "the workflow has no top-level permissions block")
        self.assertEqual(perms, {"contents": "read"}, "the top-level permissions are not contents: read")

    def test_exactly_one_job(self):
        names = job_names(self.text())
        self.assertEqual(len(names), 1, f"the workflow has {len(names)} jobs, want exactly one: {names}")

    def test_job_runs_on_ubuntu_latest(self):
        self.assertEqual(job_value(self.job(), "runs-on"), "ubuntu-latest", "the job does not run on ubuntu-latest")

    def test_job_sets_a_timeout(self):
        value = job_value(self.job(), "timeout-minutes")
        self.assertIsNotNone(value, "the job has no timeout-minutes")
        self.assertRegex(value, r"^\d+$", "the job's timeout-minutes is not a number of minutes")

    def test_job_permissions_are_actions_write_contents_read_and_pull_requests_read(self):
        perms = mapping_at(self.job().split("\n"), "permissions", 4)
        self.assertIsNotNone(perms, "the job has no permissions block")
        self.assertEqual(perms, {"actions": "write", "contents": "read", "pull-requests": "read"},
                         "the job's permissions are not actions: write, contents: read, pull-requests: read")

    def test_checkout_never_takes_the_pr_head(self):
        # A checkout with no ref takes the PR merge commit, so each one must name a base ref.
        for st in checkout_steps(self.job()):
            ref = step_with(st).get("ref")
            self.assertIsNotNone(ref, "a checkout names no ref, so it takes the PR merge commit")
            bad = [word for word in ("head", "merge", "refs/pull") if word in ref]
            self.assertEqual(bad, [], f"a checkout takes PR code: ref {ref}")

    def test_checkout_keeps_no_credentials(self):
        for st in checkout_steps(self.job()):
            self.assertEqual(step_with(st).get("persist-credentials"), "false",
                             "a checkout keeps its token: persist-credentials is not false")

    def test_job_checks_out_the_base_for_the_script(self):
        job = self.job()
        self.assertTrue(any(calls_script(st) for st in step_blocks(job)), "no run step calls the script")
        self.assertTrue(checkout_steps(job), "the job calls the script but checks out nothing, so the file is not on the runner")

    def test_concurrency_group_is_keyed_on_the_pr_number(self):
        conc = concurrency_of(self.text(), self.job())
        self.assertIsNotNone(conc, "the workflow has no concurrency block")
        self.assertIn("github.event.pull_request.number", conc.get("group", ""),
                      "the concurrency group is not keyed on the PR number")

    def test_concurrency_never_cancels_in_progress(self):
        conc = concurrency_of(self.text(), self.job())
        self.assertIsNotNone(conc, "the workflow has no concurrency block")
        self.assertEqual(conc.get("cancel-in-progress"), "false", "the concurrency group cancels in-progress runs")

    def test_a_run_step_calls_the_cancel_script(self):
        self.assertTrue(any(calls_script(st) for st in step_blocks(self.job())),
                        "no run step calls .github/scripts/cancel_closed_pr_runs.py")

    def test_the_script_step_passes_the_pr_number_and_repo(self):
        steps = [st for st in step_blocks(self.job()) if calls_script(st)]
        self.assertTrue(steps, "no run step calls the script")
        self.assertIn("github.event.pull_request.number", steps[0], "the script step does not pass the PR number")
        self.assertIn("github.repository", steps[0], "the script step does not pass the repo")


class ScriptCase(unittest.TestCase):
    def module(self):
        self.assertTrue(os.path.isfile(SCRIPT), "the script .github/scripts/cancel_closed_pr_runs.py is absent")
        spec = importlib.util.spec_from_file_location("cancel_closed_pr_runs", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception as e:  # a script that does not import is a named red, not a crash
            self.fail(f"the script does not import: {type(e).__name__}: {e}")
        return mod


def pr_dict(number=PR, state="closed", ref=HEAD_REF, sha=HEAD_SHA, head_repo=REPO_FULL):
    """The PR as GET repos/R/pulls/N returns it, cut to the keys the script reads."""
    return {"number": number, "state": state,
            "head": {"ref": ref, "sha": sha, "repo": {"full_name": head_repo}},
            "base": {"ref": DEFAULT, "repo": {"full_name": REPO_FULL, "default_branch": DEFAULT}}}


def open_pr(number=OTHER_PR, ref=HEAD_REF, head_repo=REPO_FULL):
    """An entry of GET repos/R/pulls?state=open&head=OWNER:BRANCH. A null head_repo is a deleted fork, as the API gives it."""
    repo = None if head_repo is None else {"full_name": head_repo}
    return {"number": number, "state": "open", "head": {"ref": ref, "sha": HEAD_SHA, "repo": repo}}


def run_of(**changes):
    """An unfinished run of this PR's head. GitHub lists no PR for a run of a closed PR, so pull_requests is empty by default."""
    run = {"id": 101, "event": "pull_request", "status": "queued", "head_branch": HEAD_REF, "head_sha": HEAD_SHA,
           "head_repository": {"full_name": REPO_FULL}, "pull_requests": [], "name": "checks"}
    run.update(changes)
    return run


def without(run, key):
    return {k: v for k, v in run.items() if k != key}


PULLS_ROUTE = f"repos/{REPO_FULL}/pulls/{PR}"
PULLS_LIST_ROUTE = f"repos/{REPO_FULL}/pulls"
REPO_ROUTE = f"repos/{REPO_FULL}"
RUNS_ROUTE = f"repos/{REPO_FULL}/actions/runs"
CANCEL_RE = re.compile(rf"repos/{re.escape(REPO_FULL)}/actions/runs/(\d+)/cancel")
QUERY_KEYS = ("state", "head", "status", "per_page")


def done(argv, code, out, err=""):
    return subprocess.CompletedProcess(argv, code, stdout=out, stderr=err)


def split_argv(argv):
    """(endpoint path, query params, jq filter) of a gh api argv. The query may sit on the endpoint or come as -f pairs."""
    path, params, jq = None, {}, None
    for i, tok in enumerate(argv):
        if tok == "--jq" and i + 1 < len(argv):
            jq = argv[i + 1]
        elif tok.startswith("repos/"):
            base, _, query = tok.partition("?")
            path = base
            params.update(dict(part.split("=", 1) for part in query.split("&") if "=" in part))
        elif "=" in tok and tok.split("=", 1)[0] in QUERY_KEYS:
            key, value = tok.split("=", 1)
            params[key] = value
    return path, params, jq


def jq_apply(body, expr):
    """What gh prints for a jq filter of the form ., .a.b, .a[] or .[]. Any other filter is refused."""
    each = expr.endswith("[]")
    core = expr[:-2] if each else expr
    if not re.fullmatch(r"\.(?:[\w-]+(?:\.[\w-]+)*)?", core):
        raise ValueError(f"the fixture serves no filter {expr!r}")
    for key in [k for k in core.split(".") if k]:
        body = body[key]
    if each:
        return "".join(json.dumps(item) + "\n" for item in body)
    if isinstance(body, str):
        return body + "\n"
    return json.dumps(body) + "\n"


def served(argv, body, jq):
    """The stdout gh gives for a body, with the --jq filter applied when one is given."""
    if jq is None:
        return done(argv, 0, json.dumps(body) + "\n")
    try:
        return done(argv, 0, jq_apply(body, jq))
    except (KeyError, TypeError, ValueError) as e:
        return done(argv, 1, "", f"fake gh: the --jq filter does not fit the fixture: {e}")


class FakeGh:
    """Stands in for subprocess.run under the script's gh calls. It records each argv and answers by the endpoint path, the
    part before any query. It applies a --jq filter the way gh does, so a read may take the whole JSON or one field. An
    endpoint no case names returns rc 1, so a broken fixture reads as a failure. It does not enforce GET: a POST list
    would then cancel nothing, and a case would fail for a cause other than its own."""

    def __init__(self, runs=(), states=("closed",), pr=None, open_prs=(), pr_read_fails=False, open_read_fails=False):
        self.runs, self.states = list(runs), list(states)
        self.pr = pr_dict() if pr is None else pr
        self.open_prs = list(open_prs)
        self.pr_read_fails, self.open_read_fails = pr_read_fails, open_read_fails
        self.reads, self.calls = 0, []

    def __call__(self, argv, *args, **kwargs):
        self.calls.append(list(argv))
        path, params, jq = split_argv(argv)
        if path == PULLS_ROUTE:
            if self.pr_read_fails:
                return done(argv, 1, "", "fake gh: the PR read failed")
            state = self.states[min(self.reads, len(self.states) - 1)]
            self.reads += 1
            return served(argv, dict(self.pr, state=state), jq)
        if path == PULLS_LIST_ROUTE:
            if self.open_read_fails:
                return done(argv, 1, "", "fake gh: the open PR list failed")
            return served(argv, self.open_prs, jq)
        if path == REPO_ROUTE:
            return served(argv, {"default_branch": DEFAULT}, jq)
        if path == RUNS_ROUTE:
            status = params.get("status")
            return served(argv, {"workflow_runs": [run for run in self.runs if status is None or run.get("status") == status]}, jq)
        if path and CANCEL_RE.fullmatch(path):
            return done(argv, 0, "")
        return done(argv, 1, "", "fake gh: no case names this endpoint: " + " ".join(argv))


def path_of(argv):
    return split_argv(argv)[0]


def list_calls(calls):
    return [argv for argv in calls if path_of(argv) == RUNS_ROUTE]


def open_list_calls(calls):
    return [argv for argv in calls if path_of(argv) == PULLS_LIST_ROUTE]


def cancelled_ids(calls):
    return [int(CANCEL_RE.fullmatch(tok).group(1)) for argv in calls for tok in argv if CANCEL_RE.fullmatch(tok)]


def has_get(argv):
    return any(argv[i:i + 2] == ["-X", "GET"] for i in range(len(argv)))


class ScriptSelects(ScriptCase):
    """select_runs(runs, pr, repo, default_branch, own_run_id) -> the run ids to cancel. pr is the dict GET repos/R/pulls/N returns."""

    def select(self, runs, pr=None, repo=REPO_FULL, default=DEFAULT, own_run_id=None):
        fn = getattr(self.module(), "select_runs", None)
        self.assertTrue(callable(fn), "select_runs is not defined in .github/scripts/cancel_closed_pr_runs.py")
        pr = pr_dict() if pr is None else pr
        args = (runs, pr, repo, default) if own_run_id is None else (runs, pr, repo, default, own_run_id)
        try:
            return fn(*args)
        except Exception as e:
            self.fail(f"select_runs raised {type(e).__name__}: {e}")

    def test_takes_the_pr_dict_as_its_second_argument(self):
        fn = getattr(self.module(), "select_runs", None)
        self.assertTrue(callable(fn), "select_runs is not defined in .github/scripts/cancel_closed_pr_runs.py")
        self.assertEqual(list(inspect.signature(fn).parameters), ["runs", "pr", "repo", "default_branch", "own_run_id"],
                         "select_runs does not take (runs, pr, repo, default_branch, own_run_id) with pr as the PR dict")

    def test_cancels_a_queued_run_of_this_pr(self):
        self.assertEqual(self.select([run_of(status="queued")]), [101])

    def test_cancels_an_in_progress_run_of_this_pr(self):
        self.assertEqual(self.select([run_of(status="in_progress")]), [101])

    def test_cancels_a_waiting_run_of_this_pr(self):
        self.assertEqual(self.select([run_of(status="waiting")]), [101])

    def test_cancels_a_pending_run_of_this_pr(self):
        self.assertEqual(self.select([run_of(status="pending")]), [101])

    def test_cancels_a_requested_run_of_this_pr(self):
        self.assertEqual(self.select([run_of(status="requested")]), [101],
                         "a requested run of this PR was not selected")

    def test_cancels_each_active_status_of_a_run_listing_this_pr(self):
        for status in ACTIVE:
            with self.subTest(status=status):
                self.assertEqual(self.select([run_of(status=status, pull_requests=[{"number": PR}])]), [101],
                                 f"a {status} run listing this PR was not selected")

    def test_cancels_a_run_whose_pull_list_is_empty(self):
        # GitHub lists no PR for a run of a closed PR, so an empty list is the usual shape of the run to cancel.
        self.assertEqual(self.select([run_of(pull_requests=[])]), [101],
                         "a run with an empty PR list was not selected")

    def test_cancels_a_run_listing_this_pr_among_others(self):
        # main stops the cancel when another open PR shares the head, so select_runs takes any list that names this PR.
        for prs in ([{"number": 5}, {"number": PR}], [{"number": PR}, {"number": OTHER_PR}]):
            with self.subTest(pull_requests=prs):
                self.assertEqual(self.select([run_of(pull_requests=prs)]), [101],
                                 "a run listing this PR among others was not selected")

    def test_never_cancels_a_push_run_on_main(self):
        self.assertEqual(self.select([run_of(id=101), run_of(id=102, event="push", head_branch=DEFAULT)]), [101])

    def test_never_cancels_a_push_run_on_this_prs_branch(self):
        self.assertEqual(self.select([run_of(id=101), run_of(id=102, event="push")]), [101])

    def test_never_cancels_a_completed_run(self):
        self.assertEqual(self.select([run_of(id=101), run_of(id=102, status="completed")]), [101])

    def test_never_cancels_a_run_of_another_pr(self):
        for prs in ([{"number": OTHER_PR}], [{"number": 5}, {"number": OTHER_PR}]):
            with self.subTest(pull_requests=prs):
                self.assertEqual(self.select([run_of(id=101), run_of(id=102, pull_requests=prs)]), [101],
                                 "a run naming only other PRs was selected")

    def test_never_cancels_a_run_on_the_default_branch(self):
        pr = pr_dict(ref=DEFAULT)
        runs = [run_of(id=101, head_branch=DEFAULT)]
        self.assertEqual(self.select(runs, pr=pr, default="trunk"), [101],
                         "scope: a run on main is not the default branch when the default is trunk")
        self.assertEqual(self.select(runs, pr=pr, default=DEFAULT), [],
                         "a run on the default branch was selected")

    def test_default_branch_is_the_argument_not_a_constant(self):
        runs = [run_of(id=101, head_branch="main"), run_of(id=102, head_branch="trunk")]
        self.assertEqual(self.select(runs, pr=pr_dict(ref="main"), default="trunk"), [101])

    def test_never_cancels_a_fork_run(self):
        self.assertEqual(self.select([run_of(id=101), run_of(id=102, head_repository={"full_name": "someone/fork"})]), [101])

    def test_never_cancels_any_run_when_the_pr_head_is_a_fork(self):
        self.assertEqual(self.select([run_of(id=101)]), [101], "scope: this PR's run is not selected with a same-repo head")
        self.assertEqual(self.select([run_of(id=101)], pr=pr_dict(head_repo="someone/fork")), [],
                         "a run was selected for a PR whose head is a fork")

    def test_never_cancels_a_run_of_another_head_sha(self):
        self.assertEqual(self.select([run_of(id=101), run_of(id=102, head_sha=OLD_SHA)]), [101])

    def test_never_cancels_a_run_of_another_branch(self):
        self.assertEqual(self.select([run_of(id=101), run_of(id=102, head_branch="other")]), [101])

    def test_skips_a_run_missing_a_key(self):
        for key in ("id", "event", "status", "head_branch", "head_sha", "pull_requests", "head_repository"):
            with self.subTest(missing=key):
                self.assertEqual(self.select([without(run_of(), key), run_of(id=101)]), [101],
                                 f"a run missing {key} was selected")
        with self.subTest(missing="head_repository.full_name"):
            self.assertEqual(self.select([run_of(head_repository={}), run_of(id=101)]), [101],
                             "a run with no head_repository.full_name was selected")

    def test_skips_malformed_runs_and_keeps_the_valid_one(self):
        runs = [None, "run", 5, run_of(id=103, pull_requests=None), run_of(id=104, pull_requests=[None]),
                run_of(id=105, pull_requests=[{}]), run_of(id=106, head_repository=None), run_of(id=101)]
        self.assertEqual(self.select(runs), [101])

    def test_empty_run_list_selects_nothing(self):
        self.assertEqual(self.select([]), [])

    def test_full_size_list_selects_only_the_matching_runs(self):
        # 300 runs, past one page of the runs API. Every seventh run matches; each other run fails one rule.
        other_rules = [dict(status="completed"), dict(event="push", head_branch="main", pull_requests=[]),
                       dict(pull_requests=[{"number": OTHER_PR}]), dict(head_sha=OLD_SHA), dict(head_branch="other"),
                       dict(head_repository={"full_name": "someone/fork"}), dict(head_branch=DEFAULT)]
        runs, want = [], []
        for i in range(300):
            run = run_of(id=1000 + i)
            if i % 7 == 0:
                want.append(1000 + i)
            else:
                run.update(other_rules[i % len(other_rules)])
            runs.append(run)
        self.assertEqual(sorted(self.select(runs)), sorted(want), "the full-size list selected the wrong runs")

    def test_excludes_the_own_run_and_selects_the_others(self):
        # Scope first: select_runs must take own_run_id, or the call below fails as a TypeError and not as a finding.
        fn = getattr(self.module(), "select_runs", None)
        self.assertTrue(callable(fn), "select_runs is not defined in .github/scripts/cancel_closed_pr_runs.py")
        self.assertIn("own_run_id", inspect.signature(fn).parameters,
                      "select_runs takes no own_run_id, so the cancel job's own run cannot be left out")
        got = self.select([run_of(id=101), run_of(id=102)], own_run_id=101)
        self.assertIn(102, got, "the other run 102 was not selected")
        self.assertNotIn(101, got, "the own run 101 was selected, so the cancel job would cancel itself")


class ScriptPrClosed(ScriptCase):
    """pr_is_closed(state) is true only for the state "closed"."""

    def closed(self, state):
        fn = getattr(self.module(), "pr_is_closed", None)
        self.assertTrue(callable(fn), "pr_is_closed is not defined in .github/scripts/cancel_closed_pr_runs.py")
        return fn(state)

    def test_closed_state_is_closed(self):
        self.assertIs(self.closed("closed"), True)

    def test_open_state_is_not_closed(self):
        self.assertIs(self.closed("open"), False, "an open PR reads as closed, so the script would cancel for a PR still open")

    def test_empty_state_is_not_closed(self):
        self.assertIs(self.closed(""), False, "a failed read reads as closed")


class ScriptSharedHead(ScriptCase):
    """other_open_pr_shares_head(open_prs, pr) is True only for another open PR in this repo on the PR's head branch."""

    def shares(self, open_prs, pr=None):
        fn = getattr(self.module(), "other_open_pr_shares_head", None)
        self.assertTrue(callable(fn), "other_open_pr_shares_head is not defined in .github/scripts/cancel_closed_pr_runs.py")
        try:
            return fn(open_prs, pr_dict() if pr is None else pr)
        except Exception as e:
            self.fail(f"other_open_pr_shares_head raised {type(e).__name__}: {e}")

    def test_empty_list_shares_nothing(self):
        self.assertIs(self.shares([]), False)

    def test_this_pr_alone_shares_nothing(self):
        self.assertIs(self.shares([pr_dict(state="open")]), False, "this PR was counted as another PR on its head")

    def test_another_open_pr_on_the_same_branch_shares_the_head(self):
        self.assertIs(self.shares([open_pr(number=OTHER_PR)]), True,
                      "another open PR on the same head branch was not found")

    def test_an_open_pr_on_another_branch_shares_nothing(self):
        self.assertIs(self.shares([open_pr(number=OTHER_PR)]), True, "scope: the same-branch PR was not found")
        self.assertIs(self.shares([open_pr(ref="other")]), False, "a PR on another branch was counted as sharing the head")

    def test_a_fork_pr_with_the_same_branch_name_shares_nothing(self):
        self.assertIs(self.shares([open_pr(number=OTHER_PR)]), True, "scope: the same-branch PR was not found")
        self.assertIs(self.shares([open_pr(number=OTHER_PR, head_repo="someone/fork")]), False,
                      "a fork PR with the same branch name was counted as sharing the head")

    def test_a_full_size_list_finds_its_one_match_at_the_end(self):
        others = [open_pr(number=100 + i, ref=f"branch-{i}") for i in range(250)]
        self.assertIs(self.shares(others), False, "scope: a list with no same-branch PR shared the head")
        self.assertIs(self.shares(others + [open_pr(number=OTHER_PR)]), True,
                      "the same-branch PR at the end of the list was not found")

    def test_malformed_entries_do_not_hide_a_valid_match(self):
        self.assertIs(self.shares([{"number": 9}, open_pr()]), True, "a valid same-branch PR was hidden by a malformed entry")

    def test_a_null_head_repo_does_not_raise(self):
        # shares() fails the test on a raise, so this case only needs a bool back, not a value to pin.
        self.assertIsInstance(self.shares([open_pr(head_repo=None)]), bool, "a null head repo gave no bool")


class ScriptGhCalls(ScriptCase):
    """list_active_runs makes each run list call a GET."""

    def test_every_run_list_call_is_a_get(self):
        mod = self.module()
        fake = FakeGh()
        with mock.patch.object(mod.subprocess, "run", fake):
            mod.list_active_runs(REPO_FULL)
        lists = list_calls(fake.calls)
        self.assertTrue(lists, "list_active_runs made no run list call, so there is no argv to check")
        posts = [argv for argv in lists if not has_get(argv)]
        self.assertEqual(posts, [], "a run list call has no -X GET, so gh sends a POST and the list fails")


class ScriptMain(ScriptCase):
    """main(argv) reads the PR, cancels what select_runs picks, cancels nothing when another open PR shares the head, and
    reports the runs it skips for naming only another PR."""

    def run_main(self, runs, states=("closed",), github_run_id=None, open_prs=(), pr=None, pr_read_fails=False,
                 open_read_fails=False):
        # The env is set per case, so a GITHUB_RUN_ID from the CI runner never reaches a case that does not name one.
        mod = self.module()
        fake = FakeGh(runs, states, pr=pr, open_prs=open_prs, pr_read_fails=pr_read_fails, open_read_fails=open_read_fails)
        err = io.StringIO()
        with mock.patch.dict(os.environ), mock.patch.object(mod.subprocess, "run", fake), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            os.environ.pop("GITHUB_RUN_ID", None)
            if github_run_id is not None:
                os.environ["GITHUB_RUN_ID"] = github_run_id
            try:
                rc = mod.main(["cancel_closed_pr_runs.py", str(PR), REPO_FULL])
            except Exception as e:
                self.fail(f"main raised {type(e).__name__}: {e}")
        return err.getvalue(), fake, rc

    def test_prints_the_count_of_runs_skipped_for_naming_another_pr(self):
        skipped = [run_of(id=201, pull_requests=[{"number": OTHER_PR}]), run_of(id=202, pull_requests=[{"number": OTHER_PR}]),
                   run_of(id=203, pull_requests=[{"number": OTHER_PR}])]
        not_counted = [run_of(id=204, event="push", pull_requests=[{"number": OTHER_PR}]),
                       run_of(id=205, head_branch="other", pull_requests=[{"number": OTHER_PR}])]
        err, fake, _ = self.run_main(skipped + not_counted + [run_of(id=101), run_of(id=102)])
        self.assertEqual(sorted(cancelled_ids(fake.calls)), [101, 102], "scope: the runs with an empty PR list were not cancelled")
        m = re.search(r"(\d+) run\(s\) skipped", err)
        self.assertIsNotNone(m, "main printed no 'run(s) skipped' count")
        self.assertEqual(int(m.group(1)), 3, "the skipped count is not the 3 runs of this branch that name only another PR")

    def test_cancels_nothing_when_the_pr_is_open_at_the_reread(self):
        err, fake, _ = self.run_main([run_of(id=101, pull_requests=[{"number": PR}])], states=("closed", "open"))
        self.assertTrue(list_calls(fake.calls), "scope: main never listed the runs")
        self.assertEqual(cancelled_ids(fake.calls), [], "main cancelled run 101 after the PR read as open")

    def test_cancels_the_run_when_the_pr_stays_closed_at_the_reread(self):
        err, fake, _ = self.run_main([run_of(id=101)], states=("closed", "closed"))
        self.assertEqual(cancelled_ids(fake.calls), [101], "a closed PR's run with an empty PR list was not cancelled")

    def test_cancels_a_run_listing_this_pr_among_others_when_no_open_pr_shares_the_head(self):
        err, fake, _ = self.run_main([run_of(id=101, pull_requests=[{"number": 5}, {"number": PR}])])
        self.assertEqual(cancelled_ids(fake.calls), [101], "a run listing this PR among others was not cancelled")

    def test_cancels_nothing_when_an_open_pr_on_the_head_lists_the_run(self):
        err, fake, _ = self.run_main([run_of(id=101, pull_requests=[{"number": 5}, {"number": PR}])], open_prs=[open_pr(number=5)])
        self.assertTrue(open_list_calls(fake.calls), "scope: main never listed the open PRs for the head")
        self.assertEqual(cancelled_ids(fake.calls), [], "main cancelled a run while another open PR shares the head")

    def test_cancels_nothing_when_another_open_pr_shares_the_head(self):
        err, fake, _ = self.run_main([run_of(id=101, pull_requests=[{"number": PR}]), run_of(id=102)], open_prs=[open_pr()])
        self.assertTrue(open_list_calls(fake.calls), "scope: main never listed the open PRs for the head")
        self.assertEqual(cancelled_ids(fake.calls), [], "main cancelled runs while another open PR shares the head")

    def test_exits_zero_with_a_message_when_another_open_pr_shares_the_head(self):
        err, fake, rc = self.run_main([run_of(id=101)], open_prs=[open_pr()])
        self.assertTrue(open_list_calls(fake.calls), "scope: main never listed the open PRs for the head")
        self.assertEqual(rc, 0, f"main returned {rc} when another open PR shares the head, want 0")
        self.assertTrue(err.strip(), "main printed no message for the cancel it skipped")

    def test_an_open_pr_on_another_branch_does_not_block_the_cancel(self):
        err, fake, _ = self.run_main([run_of(id=101, pull_requests=[{"number": PR}])], open_prs=[open_pr(ref="other")])
        self.assertTrue(open_list_calls(fake.calls), "scope: main never listed the open PRs for the head")
        self.assertEqual(cancelled_ids(fake.calls), [101], "an open PR on another branch blocked the cancel")

    def test_an_open_pr_from_a_fork_with_the_same_branch_name_does_not_block_the_cancel(self):
        err, fake, _ = self.run_main([run_of(id=101, pull_requests=[{"number": PR}])],
                                     open_prs=[open_pr(head_repo="someone/fork")])
        self.assertTrue(open_list_calls(fake.calls), "scope: main never listed the open PRs for the head")
        self.assertEqual(cancelled_ids(fake.calls), [101], "a fork PR with the same branch name blocked the cancel")

    def test_cancels_nothing_when_the_open_pr_list_cannot_be_read(self):
        err, fake, _ = self.run_main([run_of(id=101, pull_requests=[{"number": PR}]), run_of(id=102, pull_requests=[{"number": PR}])],
                                     open_read_fails=True)
        self.assertTrue(open_list_calls(fake.calls), "scope: main never asked for the open PRs")
        self.assertEqual(cancelled_ids(fake.calls), [], "main cancelled runs although the open PR list could not be read")

    def test_exits_one_when_the_open_pr_list_cannot_be_read(self):
        err, fake, rc = self.run_main([run_of(id=101)], open_read_fails=True)
        self.assertTrue(open_list_calls(fake.calls), "scope: main never asked for the open PRs")
        self.assertEqual(rc, 1, f"main returned {rc} when the open PR list could not be read, want 1")

    def test_fails_safe_when_the_pr_cannot_be_read(self):
        err, fake, rc = self.run_main([run_of(id=101, pull_requests=[{"number": PR}])], pr_read_fails=True)
        self.assertEqual(rc, 1, f"main returned {rc} when the PR could not be read, want 1")
        self.assertEqual(cancelled_ids(fake.calls), [], "main cancelled runs although the PR could not be read")

    def test_a_run_of_an_older_head_sha_is_not_cancelled(self):
        err, fake, _ = self.run_main([run_of(id=101, head_sha=OLD_SHA, pull_requests=[{"number": PR}]),
                                      run_of(id=102, pull_requests=[{"number": PR}])])
        self.assertIn(102, cancelled_ids(fake.calls), "scope: the run at the PR's head SHA was not cancelled")
        self.assertNotIn(101, cancelled_ids(fake.calls), "a run of an older head SHA was cancelled")

    def test_a_run_of_another_branch_is_not_cancelled(self):
        err, fake, _ = self.run_main([run_of(id=101, head_branch="other", pull_requests=[{"number": PR}]),
                                      run_of(id=102, pull_requests=[{"number": PR}])])
        self.assertIn(102, cancelled_ids(fake.calls), "scope: the run on the PR's branch was not cancelled")
        self.assertNotIn(101, cancelled_ids(fake.calls), "a run of another branch was cancelled")

    def test_no_active_runs_cancels_nothing_and_exits_zero(self):
        err, fake, rc = self.run_main([])
        self.assertTrue(list_calls(fake.calls), "scope: main never listed the runs")
        self.assertEqual(cancelled_ids(fake.calls), [], "main cancelled runs when there were none to cancel")
        self.assertEqual(rc, 0, f"main returned {rc} with no active runs, want 0")

    def test_the_run_named_by_github_run_id_is_not_cancelled(self):
        err, fake, _ = self.run_main([run_of(id=101), run_of(id=102)], github_run_id="101")
        self.assertIn(102, cancelled_ids(fake.calls), "the other run 102 (empty PR list) was not cancelled")
        self.assertNotIn(101, cancelled_ids(fake.calls), "the own run 101 named by GITHUB_RUN_ID was cancelled")

    def test_a_non_numeric_github_run_id_cancels_nothing(self):
        err, fake, _ = self.run_main([run_of(id=101), run_of(id=102)], github_run_id="abc")
        self.assertEqual(cancelled_ids(fake.calls), [], "main cancelled runs although GITHUB_RUN_ID is not numeric")

    def test_a_non_numeric_github_run_id_exits_one_before_any_gh_call(self):
        err, fake, rc = self.run_main([run_of(id=101)], github_run_id="abc")
        self.assertEqual(rc, 1, f"main returned {rc} for a GITHUB_RUN_ID that is not numeric, want 1")
        self.assertEqual(fake.calls, [], "main called gh before it refused the GITHUB_RUN_ID")

    def test_every_list_call_is_a_get_including_the_open_pr_list(self):
        err, fake, _ = self.run_main([run_of(id=101)], open_prs=[open_pr()])
        self.assertTrue(open_list_calls(fake.calls), "scope: main never listed the open PRs for the head")
        posts = [argv for argv in list_calls(fake.calls) + open_list_calls(fake.calls) if not has_get(argv)]
        self.assertEqual(posts, [], "a list call has no -X GET, so gh sends a POST and the list fails")

    def test_the_open_pr_list_asks_for_open_prs_on_the_owner_and_head_branch(self):
        err, fake, _ = self.run_main([run_of(id=101)])
        calls = open_list_calls(fake.calls)
        self.assertTrue(calls, "scope: main never listed the open PRs for the head")
        params = split_argv(calls[0])[1]
        self.assertEqual(params.get("state"), "open", "the open PR list does not ask for state=open")
        self.assertEqual(params.get("head"), f"{OWNER}:{HEAD_REF}", "the open PR list does not ask for head=OWNER:BRANCH")


class ParserControl(unittest.TestCase):
    """Checks the readers WorkflowShape uses, on lane-touched-tests.yml. So a red WorkflowShape case points at
    cancel-on-close.yml, never at a reader."""

    def test_reads_the_triggers_of_lane_touched_tests(self):
        self.assertEqual(triggers(read_text(CONTROL_WORKFLOW)),
                         {"pull_request": ["opened", "synchronize", "reopened", "converted_to_draft"]})

    def test_reads_the_top_permissions_of_lane_touched_tests(self):
        self.assertEqual(mapping_at(read_text(CONTROL_WORKFLOW).split("\n"), "permissions", 0), {"contents": "read"})

    def test_reads_the_job_names_of_lane_touched_tests(self):
        self.assertEqual(job_names(read_text(CONTROL_WORKFLOW)), ["touched", "run"])

    def test_reads_the_checkout_persist_flag_of_lane_touched_tests(self):
        job = job_block(read_text(CONTROL_WORKFLOW), "touched")
        self.assertTrue(checkout_steps(job), "no checkout step read in the touched job")
        for st in checkout_steps(job):
            self.assertEqual(step_with(st).get("persist-credentials"), "false")

    def test_a_block_list_of_types_is_read(self):
        self.assertEqual(triggers("on:\n  pull_request:\n    types:\n      - closed\n"), {"pull_request": ["closed"]})

    def test_a_flow_permissions_map_with_a_comment_is_read(self):
        text = "# permissions: write-all\npermissions: {contents: read}  # read only\n"
        self.assertEqual(mapping_at(text.split("\n"), "permissions", 0), {"contents": "read"})

    def test_a_trailing_comment_on_types_is_dropped(self):
        self.assertEqual(triggers("on:\n  pull_request:\n    types: [closed]  # pull_request_target\n"),
                         {"pull_request": ["closed"]})


class ScannerTraps(unittest.TestCase):
    """The shell and trigger readers must tell a comment from text. An opener inside quotes is text, a real comment is
    dropped, and a lone quote hides nothing. WorkflowShape relies on each of these."""

    def test_a_comment_opener_inside_double_quotes_is_text(self):
        self.assertIn(SCRIPT_CALL, shell_code('echo "# x" && python3 ' + SCRIPT_CALL))

    def test_a_lone_quote_in_a_word_does_not_hide_a_comment(self):
        self.assertNotIn(SCRIPT_CALL, shell_code("echo don't # python3 " + SCRIPT_CALL))

    def test_a_lone_quote_does_not_hide_a_call(self):
        self.assertIn(SCRIPT_CALL, shell_code("echo don't && python3 " + SCRIPT_CALL))

    def test_a_trailing_shell_comment_is_dropped(self):
        self.assertNotIn(SCRIPT_CALL, shell_code("echo ok  # python3 " + SCRIPT_CALL))

    def test_a_one_line_run_comment_with_a_space_before_it_hides_the_call(self):
        step = "      - name: Cancel\n        run: echo ok # python3 " + SCRIPT_CALL + "\n"
        self.assertFalse(calls_script(step))

    def test_a_one_line_run_opener_with_no_space_before_it_is_text(self):
        step = '      - name: Cancel\n        run: echo "#x" && python3 ' + SCRIPT_CALL + "\n"
        self.assertTrue(calls_script(step))

    def test_a_block_run_with_an_opener_in_quotes_is_a_call(self):
        step = '      - name: Cancel\n        run: |\n          echo "# x" && python3 ' + SCRIPT_CALL + "\n"
        self.assertTrue(calls_script(step))

    def test_a_comment_line_in_a_block_is_no_call(self):
        step = "      - name: Cancel\n        run: |\n          # python3 " + SCRIPT_CALL + "\n          echo ok\n"
        self.assertFalse(calls_script(step))

    def test_a_block_goes_on_past_a_comment_line(self):
        step = "      - name: Cancel\n        run: |\n          # note\n          python3 " + SCRIPT_CALL + "\n"
        self.assertTrue(calls_script(step))

    def test_a_block_ends_at_the_next_step_key(self):
        step = "      - name: Cancel\n        run: |\n          echo start\n        name: python3 " + SCRIPT_CALL + "\n"
        self.assertFalse(calls_script(step))

    def test_a_lone_quote_in_a_step_name_is_no_run(self):
        step = "      - name: Don't run python3 " + SCRIPT_CALL + "\n        shell: bash\n"
        self.assertFalse(calls_script(step))

    def test_a_comment_line_in_the_trigger_block_is_no_trigger(self):
        text = "on:\n  # pull_request_target: not a trigger\n  pull_request:\n    types: [closed]\n"
        self.assertEqual(triggers(text), {"pull_request": ["closed"]})

    def test_a_lone_quote_in_a_trigger_comment_is_no_trigger(self):
        text = "on:\n  # don't use pull_request_target\n  pull_request:\n    types: [closed]\n"
        self.assertEqual(triggers(text), {"pull_request": ["closed"]})


if __name__ == "__main__":
    unittest.main()
