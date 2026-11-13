#!/usr/bin/env python3
"""Guard for the PR-close cancel: .github/workflows/cancel-on-close.yml and .github/scripts/cancel_closed_pr_runs.py.

WorkflowShape reads the workflow by line, as lint/test_windows_split.py does, with the step parser of lint/workflow_steps.py.
ScriptSelects proves select_runs cancels only a queued, in-progress, waiting, pending or requested pull_request run of
this PR from this repo, only one whose PR list names this PR and no other, and never the run whose id is own_run_id.
ScriptPrClosed proves pr_is_closed reads only "closed". ScriptGhCalls and ScriptMain prove every run list is a GET,
main counts the runs it skips for having no PR list, main reads the PR again before it cancels, main excludes the run
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
REPO_FULL = "owner/repo"
DEFAULT = "main"


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

    def test_job_permissions_are_actions_write_and_pull_requests_read(self):
        perms = mapping_at(self.job().split("\n"), "permissions", 4)
        self.assertIsNotNone(perms, "the job has no permissions block")
        self.assertEqual(perms, {"actions": "write", "pull-requests": "read"},
                         "the job's permissions are not actions: write, pull-requests: read")

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


def run_of(**changes):
    """A run that this PR's close would cancel, with each field replaced by `changes`."""
    run = {"id": 101, "event": "pull_request", "status": "queued", "head_branch": "feature",
           "pull_requests": [{"number": PR}], "head_repository": {"full_name": REPO_FULL}, "name": "checks"}
    run.update(changes)
    return run


def without(run, key):
    return {k: v for k, v in run.items() if k != key}


PULLS_ROUTE = f"repos/{REPO_FULL}/pulls/{PR}"
REPO_ROUTE = f"repos/{REPO_FULL}"
RUNS_ROUTE = f"repos/{REPO_FULL}/actions/runs"
CANCEL_RE = re.compile(rf"repos/{re.escape(REPO_FULL)}/actions/runs/(\d+)/cancel")


def done(argv, code, out, err=""):
    return subprocess.CompletedProcess(argv, code, stdout=out, stderr=err)


class FakeGh:
    """Stands in for subprocess.run under the script's gh calls. It records each argv and answers by the exact endpoint
    token. An endpoint no case names returns rc 1, so a broken fixture reads as a failure. It does not enforce GET: a
    POST list would then cancel nothing, and a case would fail for a cause other than its own."""

    def __init__(self, runs=(), states=("closed",)):
        self.runs, self.states = list(runs), list(states)
        self.reads, self.calls = 0, []

    def __call__(self, argv, *args, **kwargs):
        self.calls.append(list(argv))
        if PULLS_ROUTE in argv:
            state = self.states[min(self.reads, len(self.states) - 1)]
            self.reads += 1
            return done(argv, 0, state + "\n")
        if REPO_ROUTE in argv:
            return done(argv, 0, DEFAULT + "\n")
        if RUNS_ROUTE in argv:
            status = [tok.split("=", 1)[1] for tok in argv if tok.startswith("status=")]
            lines = [json.dumps(run) + "\n" for run in self.runs if status and run.get("status") == status[0]]
            return done(argv, 0, "".join(lines))
        if any(CANCEL_RE.fullmatch(tok) for tok in argv):
            return done(argv, 0, "")
        return done(argv, 1, "", "fake gh: no case names this endpoint: " + " ".join(argv))


def list_calls(calls):
    return [argv for argv in calls if RUNS_ROUTE in argv]


def cancelled_ids(calls):
    return [int(CANCEL_RE.fullmatch(tok).group(1)) for argv in calls for tok in argv if CANCEL_RE.fullmatch(tok)]


def has_get(argv):
    return any(argv[i:i + 2] == ["-X", "GET"] for i in range(len(argv)))


class ScriptSelects(ScriptCase):
    """select_runs(runs, pr_number, repo, default_branch) -> the run ids to cancel."""

    def select(self, runs, pr=PR, repo=REPO_FULL, default=DEFAULT, own_run_id=None):
        fn = getattr(self.module(), "select_runs", None)
        self.assertTrue(callable(fn), "select_runs is not defined in .github/scripts/cancel_closed_pr_runs.py")
        args = (runs, pr, repo, default) if own_run_id is None else (runs, pr, repo, default, own_run_id)
        try:
            return fn(*args)
        except Exception as e:
            self.fail(f"select_runs raised {type(e).__name__}: {e}")

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

    def test_never_cancels_a_run_listing_several_prs(self):
        for prs in ([{"number": 5}, {"number": PR}], [{"number": PR}, {"number": 8}]):
            with self.subTest(pull_requests=prs):
                self.assertEqual(self.select([run_of(pull_requests=prs)]), [],
                                 f"a run listing several PRs was selected: closing PR {PR} would cancel "
                                 "another open PR's run")

    def test_never_cancels_a_push_run_on_main(self):
        self.assertEqual(self.select([run_of(event="push", head_branch="main", pull_requests=[])]), [])

    def test_never_cancels_a_push_run_on_this_prs_branch(self):
        self.assertEqual(self.select([run_of(event="push", head_branch="feature")]), [])

    def test_never_cancels_a_completed_run(self):
        self.assertEqual(self.select([run_of(status="completed")]), [])

    def test_never_cancels_a_run_of_another_pr(self):
        self.assertEqual(self.select([run_of(pull_requests=[{"number": 8}])]), [])

    def test_never_cancels_a_run_with_no_pull_request(self):
        self.assertEqual(self.select([run_of(pull_requests=[])]), [])

    def test_never_cancels_a_run_on_the_default_branch(self):
        self.assertEqual(self.select([run_of(head_branch=DEFAULT)]), [])

    def test_default_branch_is_the_argument_not_a_constant(self):
        runs = [run_of(id=101, head_branch="main"), run_of(id=102, head_branch="trunk")]
        self.assertEqual(self.select(runs, default="trunk"), [101])

    def test_never_cancels_a_fork_run(self):
        self.assertEqual(self.select([run_of(head_repository={"full_name": "someone/fork"})]), [])

    def test_skips_a_run_missing_a_key(self):
        for key in ("id", "event", "status", "head_branch", "pull_requests", "head_repository"):
            with self.subTest(missing=key):
                self.assertEqual(self.select([without(run_of(), key)]), [], f"a run missing {key} was selected")
        with self.subTest(missing="head_repository.full_name"):
            self.assertEqual(self.select([run_of(head_repository={})]), [],
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
                       dict(pull_requests=[{"number": 8}]), dict(pull_requests=[]), dict(head_branch=DEFAULT),
                       dict(head_repository={"full_name": "someone/fork"})]
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
    """main(argv) reads the PR, cancels what select_runs picks, and reports the runs it skips for having no PR list."""

    def run_main(self, runs, states=("closed",), github_run_id=None):
        # The env is set per case, so a GITHUB_RUN_ID from the CI runner never reaches a case that does not name one.
        mod = self.module()
        fake = FakeGh(runs, states)
        err = io.StringIO()
        with mock.patch.dict(os.environ), mock.patch.object(mod.subprocess, "run", fake), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            os.environ.pop("GITHUB_RUN_ID", None)
            if github_run_id is not None:
                os.environ["GITHUB_RUN_ID"] = github_run_id
            rc = mod.main(["cancel_closed_pr_runs.py", str(PR), REPO_FULL])
        return err.getvalue(), fake, rc

    def test_prints_the_count_of_runs_with_no_pr_list(self):
        no_list = [run_of(id=201, pull_requests=[]), run_of(id=202, pull_requests=[])]
        not_counted = [run_of(id=203, event="push", pull_requests=[]),
                       run_of(id=204, head_repository={"full_name": "someone/fork"}, pull_requests=[]),
                       run_of(id=205, head_branch=DEFAULT, pull_requests=[]),
                       run_of(id=206, pull_requests=[{"number": 8}])]
        err, fake, _ = self.run_main(no_list + not_counted + [run_of(id=101)])
        self.assertEqual(cancelled_ids(fake.calls), [101], "scope: the PR's own run was not the one cancelled")
        self.assertIn("2 run(s) skipped: no PR list", err, "main printed no count of the runs with no PR list")

    def test_cancels_nothing_when_the_pr_is_open_at_the_reread(self):
        err, fake, _ = self.run_main([run_of(id=101)], states=("closed", "open"))
        self.assertTrue(list_calls(fake.calls), "scope: main never listed the runs")
        self.assertEqual(cancelled_ids(fake.calls), [], "main cancelled run 101 after the PR read as open")

    def test_cancels_the_run_when_the_pr_stays_closed_at_the_reread(self):
        err, fake, _ = self.run_main([run_of(id=101)], states=("closed", "closed"))
        self.assertEqual(cancelled_ids(fake.calls), [101])

    def test_the_run_named_by_github_run_id_is_not_cancelled(self):
        err, fake, _ = self.run_main([run_of(id=101), run_of(id=102)], github_run_id="101")
        self.assertIn(102, cancelled_ids(fake.calls), "scope: the other run 102 was not cancelled")
        self.assertNotIn(101, cancelled_ids(fake.calls), "the own run 101 named by GITHUB_RUN_ID was cancelled")

    def test_a_non_numeric_github_run_id_cancels_nothing(self):
        err, fake, _ = self.run_main([run_of(id=101), run_of(id=102)], github_run_id="abc")
        self.assertEqual(cancelled_ids(fake.calls), [], "main cancelled runs although GITHUB_RUN_ID is not numeric")

    def test_a_non_numeric_github_run_id_exits_one(self):
        err, fake, rc = self.run_main([run_of(id=101)], github_run_id="abc")
        self.assertEqual(rc, 1, f"main returned {rc} for a GITHUB_RUN_ID that is not numeric, want 1")


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
