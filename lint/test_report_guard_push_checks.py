#!/usr/bin/env python3
"""Cases for the Stop-side CI check after a push (lint/report_guard.py; debt push-report-before-checks;
decision push-report-names-ci, section "The ruling").

A turn that pushes a head holds its report until that head's CI is known. The report holds one line
that names the head, in the form the guard reads:
- `CI running on <sha7>` under Next, while a run is pending, or while a ready PR has no run yet.
- `CI red on <sha7>`, when a run ended red.
- `CI unknown on <sha7>`, when a read failed.
A green run, a draft PR, a branch with no PR, a repo with no workflows, a tag push, a delete and a dry run need no line. A Done
item may not claim a pending head.

A check that did not run reads UNKNOWN in the systemMessage, never a block, as the hand-off check's note does
(`Push-CI guard: UNKNOWN, the check did not run`). That holds when the CI read raises, and when the guard module does
not load on a push turn.

Each case runs the real Stop hook as a subprocess. The gh stand-in leads its PATH (setUpModule of
lint/test_report_guard.py, which takes the stand-in's program from hooks/test_ci_wake.py) and answers
the fixture the case writes. No real gh runs, no network is reached and no clock is read. The budget
cases run in process with a fake clock. The path-filter reader cases call ci_wake's filter functions in process, on real
temp repos (or on a string, for the scanner cases).

Cost, proved by the stand-in's call log: a turn with no push, and a Stop with stop_hook_active, make no
gh call. A push reads at most 3 gh calls for its head: the PR read, the run list, and the workflow list when the run
list is empty. A bare-name push with no ref line starts at most 1 git process when its remote-tracking ref names the
head, else 3 per name (the tag, the local branch and the remote-tracking ref). A HEAD refspec or a push with no refspec
starts 1 more for the checked-out branch. A git stand-in's call log counts them.

Each case asserts the guard's verdict on the turn it builds.

Run it from the repository root:

    python3 lint/test_report_guard_push_checks.py -v
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_report_guard as trg  # noqa: E402  the Stop-hook harness and the gh stand-in seam (one home)
import ci_wake  # noqa: E402  the read budget, ci_wake.Budget (hooks/ci_wake.py; on sys.path from the harness import)
import report_guard  # noqa: E402  push_ci_states and push_ci_problem, read in process
import local_time  # noqa: E402  the missing-report marker path (hooks/local_time.py)

HEAD = "9f3c2a1b7d4e5f60718293a4b5c6d7e8f9012345"  # the head a case pushes
HEAD7 = HEAD[:7]
MID = "5e6f7a8b9c0d1e2f30415263748596a7b8c9d0e1"  # the head between two pushes of one turn
MID7 = MID[:7]
OLD = "1a2b3c4d5e6f708192a3b4c5d6e7f80910111213"  # the head before the first push
OLD7 = OLD[:7]
OTHER = "7a8b9c0d1e2f30415263748596a7b8c9d0e1f2a3"  # the head of a second branch pushed in the same turn
OTHER7 = OTHER[:7]
BRANCH = "push-report-checks"
OTHER_BRANCH = "other-branch"
REJECTED_BRANCH = "fix/rejected-items"
REPORT = trg.GOOD_REPORT  # a report of the right shape that holds no CI line
NO_REPORT = "Pushed it."
RUNNING = "> **Done** BUILT abc123\n> **Next** CI running on %s" % HEAD7
RED = "> **Done** BUILT abc123\n> **Next** CI red on %s" % HEAD7
UNKNOWN = "> **Done** BUILT abc123\n> **Next** CI unknown on %s" % HEAD7
UNKNOWN_HEAD = "> **Done** BUILT abc123\n> **Next** CI unknown on HEAD"  # a push whose branch read failed
UNKNOWN_BRANCH = "> **Done** BUILT abc123\n> **Next** CI unknown on %s" % BRANCH  # a push that named no head
DONE_CLAIMS_HEAD = "> **Done** BUILT %s\n> **Next** CI running on %s" % (HEAD7, HEAD7)
PUSH_UNKNOWN_NOTE = "Push-CI guard: UNKNOWN, the check did not run"  # the note of a push check that did not run
REMOTE_URL = "https://github.com/shivinate7/claude-settings.git"  # a push to a URL updates no remote-tracking ref
REMOTE_LINE = "To %s\n" % REMOTE_URL  # the header git prints for a push; it names no ref
TAG = "v1.0"  # a short-name tag: a push names it without `refs/tags/`
FEAT = "feat"  # a bare name a push gives with no ref line: a branch, a tag or both, by the case
UNNAMED_HEAD_TEXT = "no remote-tracking ref names the pushed head"  # the reason a head no read named gives
def checks_workflow(push_block):
    """A `checks` workflow whose `push:` event holds `push_block`, the lines under `push:` as written (indented 4)."""
    return ("name: checks\non:\n  push:\n" + push_block + "jobs:\n  unit:\n"
            "    runs-on: ubuntu-latest\n    steps:\n      - run: echo ok\n")


# A workflow that runs for a push that touches docs/ only. A push that touches other files starts no run of it.
DOCS_ONLY_WORKFLOW = checks_workflow("    paths:\n      - 'docs/**'\n")
SRC_ONLY_WORKFLOW = checks_workflow("    paths:\n      - 'src/**'\n")
FLOW_PATHS = ("api/**", "docs/**", "hooks/**", "lint/**", "migrations/**", "scripts/**", "src/**", "web/**")
SOURCE = "value = 1\n" * 20  # long enough that a moved copy is still the same file to rename detection


def flow_paths_workflow(spread):
    """A `checks` workflow whose push `paths` is FLOW_PATHS, as one flow line or as a flow list spread over lines."""
    if not spread:
        return checks_workflow("    paths: [%s]\n" % ", ".join('"%s"' % p for p in FLOW_PATHS))
    lines = "".join('      "%s",\n' % p for p in FLOW_PATHS[:-1]) + '      "%s"\n' % FLOW_PATHS[-1]
    return checks_workflow("    paths: [\n" + lines + "    ]\n")


def pr_entry(draft=False, branch=BRANCH, sha=HEAD, number=1430):
    return {"number": number, "isDraft": draft, "headRefName": branch, "headRefOid": sha,
            "state": "OPEN", "url": "https://github.com/shivinate7/claude-settings/pull/%d" % number}


def run_entry(conclusion, sha=HEAD, run_id=501, status="completed"):
    """One run as the stand-in lists it. Status in_progress with conclusion None is a pending run."""
    return {"databaseId": run_id, "name": "checks", "workflowName": "checks", "headSha": sha,
            "event": "pull_request", "status": status, "conclusion": conclusion,
            "jobs": [{"name": "unit", "conclusion": conclusion, "status": status}]}


PENDING = run_entry(None, status="in_progress")
PENDING_MID = run_entry(None, sha=MID, run_id=502, status="in_progress")
PENDING_OTHER = run_entry(None, sha=OTHER, run_id=503, status="in_progress")
GREEN = run_entry("success")
RED_RUN = run_entry("failure")
SKIPPED = run_entry("skipped")


def answers(prs=(), runs=(), mode="ok", workflows=None):
    """The stand-in's fixture. mode "error" fails every call; "garbage" prints non-JSON. workflows, when
    given, is the `gh workflow list` answer: [] is a repo with no active workflow."""
    out = {"mode": mode, "prs": list(prs), "runs": list(runs)}
    if workflows is not None:
        out["workflows"] = list(workflows)
    return out


def call(name, tool_input, use_id):
    block = {"type": "tool_use", "id": use_id, "name": name, "input": tool_input}
    return [{"type": "assistant", "isSidechain": False, "message": {"role": "assistant", "content": [block]}}]


def result(text, use_id):
    block = {"type": "tool_result", "tool_use_id": use_id, "content": text}
    return [{"type": "user", "isSidechain": False, "message": {"role": "user", "content": [block]}}]


def bash(command, output, use_id="tu_1"):
    return call("Bash", {"command": command}, use_id) + result(output, use_id)


def push_out(new, old=OLD7, dst=BRANCH):
    """The lines git push prints for one update: `old..new src -> dst`."""
    return "To https://github.com/shivinate7/claude-settings.git\n   %s..%s  HEAD -> %s\n" % (old, new, dst)


def push(output, command="git push origin HEAD:%s" % BRANCH, use_id="tu_1"):
    return bash(command, output, use_id)


def mcp_push(use_id="tu_1"):
    """A GitHub MCP push_files call, and a result that names the commit it made."""
    tool_input = {"owner": "shivinate7", "repo": "claude-settings", "branch": BRANCH, "message": "x", "files": []}
    return call("mcp__github__push_files", tool_input, use_id) + result(json.dumps({"sha": HEAD}), use_id)


def turn(reply, *steps):
    """One human message, then each step's records in order, then the reply."""
    records = [trg.human("do the task")]
    for step in steps:
        records.extend(step)
    records.append(trg.assistant_text(reply))
    return records


def block_of(done):
    """-> (decision, reason). Silence reads as (None, ""). Text that is not JSON reads as ("unparsed", text)."""
    text = done.stdout.strip()
    if not text:
        return None, ""
    try:
        out = json.loads(text)
    except ValueError:
        return "unparsed", text[:300]
    return out.get("decision"), out.get("reason") or ""


GIT_IDENTITY = {"GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
                "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@example.invalid"}


def git_commit(folder, remote_branch=BRANCH, on_branch=None, detach=False, tag=None, files=None, remove=None):
    """Make `folder` a git repo, and commit on it. -> the full hash. Local git only.
    on_branch: the local branch the commit lands on, made from the current HEAD when it is new (None keeps the
    default branch). remote_branch: the branch whose remote-tracking ref is set to the commit (None sets none).
    detach: HEAD is left detached at the commit, so no branch is checked out. tag: a local tag of that name at the
    commit (None makes none). files: {relative path: text}, written and committed (None commits no file). remove:
    relative paths deleted in the commit (a rename is one removal and one new file, with the same text)."""
    env = dict(os.environ, **GIT_IDENTITY)

    def run_git(*args):
        return subprocess.run(["git", *args], cwd=folder, env=env, capture_output=True, text=True,
                              check=True, timeout=30).stdout.strip()

    run_git("init", "-q")
    if on_branch:
        run_git("checkout", "-q", "-B", on_branch)
    for rel, text in (files or {}).items():
        os.makedirs(os.path.dirname(os.path.join(folder, rel)), exist_ok=True)
        with open(os.path.join(folder, rel), "w", encoding="utf-8") as f:
            f.write(text)
    for rel in remove or ():
        run_git("rm", "-q", "--", rel)
    if files:
        run_git("add", "--", *files)
    run_git("commit", "-q", "--allow-empty", "-m", "x")
    head = run_git("rev-parse", "HEAD")
    if tag:
        run_git("tag", tag)
    if remote_branch:
        run_git("update-ref", "refs/remotes/origin/" + remote_branch, head)
    if detach:
        run_git("checkout", "-q", "--detach")
    return head


def git_stand_in(folder):
    """A `git` stand-in that leads PATH for one case. Each call appends its argv to a log, then runs the real git, so
    the log holds one line per git process a guard starts. A POSIX launcher, as the gh stand-in's is.
    -> (bin_dir, log)."""
    real = shutil.which("git")
    bin_dir = os.path.join(folder, "git-bin")
    os.makedirs(bin_dir)
    log = os.path.join(folder, "git.log")
    launcher = os.path.join(bin_dir, "git")
    with open(launcher, "w", encoding="utf-8", newline="\n") as f:
        f.write('#!/bin/sh\necho "$*" >> "%s"\nexec "%s" "$@"\n' % (log, real))
    os.chmod(launcher, 0o755)
    return bin_dir, log


def git_calls(log):
    """The argv of each git process the stand-in logged, one string per call. [] when none ran."""
    if not os.path.exists(log):
        return []
    with open(log, encoding="utf-8") as f:
        return f.read().splitlines()


class StepClock:
    """A clock that answers each call with the next of `values`, then keeps answering the last one, so a test
    sets when each budget read lands and no read runs past the script."""

    def __init__(self, values):
        self.values = list(values)

    def __call__(self):
        if len(self.values) > 1:
            return self.values.pop(0)
        return self.values[0]


def setUpModule():
    trg.setUpModule()


def tearDownModule():
    trg.tearDownModule()


class PushCheckTests(unittest.TestCase):
    def case_folder(self):
        return tempfile.mkdtemp(prefix="push-", dir=trg.RUN_FOLDER)

    def run_stop(self, records, answers_=None, stop_active=False, no_gh=False, folder=None, session_id=None,
                 block=()):
        """Run the Stop hook over `records`, with the stand-in answering `answers_`. no_gh: the guard's PATH
        holds no gh at all. folder: the case's folder (its call log and fixture), new when None. session_id:
        the hook's session, which names the missing-report marker. block: module names whose import raises
        inside the hook (trg.run_guard's seam). -> (the finished process, gh calls)."""
        folder = folder or self.case_folder()
        transcript = trg.write_transcript(records, folder)
        fixture_path = os.path.join(folder, "fixture.json")
        with open(fixture_path, "w", encoding="utf-8") as f:
            json.dump(answers() if answers_ is None else answers_, f)
        log = os.path.join(folder, "gh.log")
        path = None
        if no_gh:
            path = os.path.join(folder, "no-gh")
            os.makedirs(path)
        hook = {"hook_event_name": "Stop", "transcript_path": transcript, "cwd": folder,
                "stop_hook_active": stop_active}
        if session_id is not None:
            hook["session_id"] = session_id
        try:
            done = trg.run_guard(trg.REPORT_GUARD, hook, env=trg.gh_env(fixture_path, log, path), block=block)
        except subprocess.TimeoutExpired:
            self.fail("the Stop hook ran past its timeout: a push turn reads CI once and returns")
        self.assertEqual(done.returncode, 0, "the Stop hook exited %d: %s" % (done.returncode, done.stderr[-300:]))
        return done, trg.GH_STUB.read_log(log)

    def stop(self, records, answers_=None, stop_active=False, no_gh=False, folder=None, session_id=None):
        """The Stop hook over `records` (run_stop). -> (decision, reason, gh calls)."""
        done, calls = self.run_stop(records, answers_, stop_active, no_gh, folder, session_id)
        decision, reason = block_of(done)
        return decision, reason, calls

    def stop_note(self, records, answers_=None, block=()):
        """The Stop hook over `records` with the modules in `block` unloadable. -> (decision, systemMessage). Silence
        reads as (None, ""). Text that is not JSON fails the case."""
        done, _ = self.run_stop(records, answers_, block=block)
        text = done.stdout.strip()
        if not text:
            return None, ""
        try:
            out = json.loads(text)
        except ValueError:
            self.fail("the Stop hook printed text that is not JSON: %r" % text[:300])
        return out.get("decision"), out.get("systemMessage") or ""

    # The CI line a push turn owes: which pushes owe one, the run state it names, and what holds it.

    def test_no_workflows_repo_needs_no_ci_line_for_a_ready_pr_push(self):
        steps = push(push_out(HEAD7))
        fixture_ = answers(prs=[pr_entry()], runs=[], workflows=[])
        decision, _, _ = self.stop(turn(NO_REPORT, steps), fixture_)
        self.assertEqual(decision, "block", "a report-less push turn was not blocked (scope check)")
        decision, reason, _ = self.stop(turn(REPORT, steps), fixture_)
        self.assertIsNone(decision, "a push to a ready PR in a repo with no workflows was blocked for CI: " + reason)

    def test_no_workflows_repo_needs_no_ci_line_for_a_push_to_main(self):
        steps = push(push_out(HEAD7, dst="main"), command="git push origin HEAD:main")
        fixture_ = answers(runs=[], workflows=[])
        decision, _, _ = self.stop(turn(NO_REPORT, steps), fixture_)
        self.assertEqual(decision, "block", "a report-less push to main was not blocked (scope check)")
        decision, reason, _ = self.stop(turn(REPORT, steps), fixture_)
        self.assertIsNone(decision, "a push to main in a repo with no workflows was blocked for CI: " + reason)

    def test_pr_read_that_lags_the_push_still_owes_a_ci_line(self):
        # The PR's REST read can lag the push: it still names the head the push moved from, which is not the pushed
        # commit. That read clears nothing, so the report must name the pushed head's CI state.
        steps = push(push_out(HEAD7))
        fixture_ = answers(prs=[pr_entry(sha=OLD)], runs=[PENDING])
        decision, _, _ = self.stop(turn(NO_REPORT, steps), fixture_)
        self.assertEqual(decision, "block", "a report-less push turn was not blocked (scope check)")
        decision, reason, _ = self.stop(turn(REPORT, steps), fixture_)
        self.assertEqual(decision, "block", "a push whose PR still named the head before it passed with no CI line: "
                         "the lagging read was taken as no CI")
        self.assertIn(HEAD7, reason, "the lagging PR read left the pushed head unnamed: %s" % reason)

    def test_push_that_no_workflow_path_filter_matches_owes_no_ci_line(self):
        # The one workflow runs only for a push that touches docs/. This push touches lint/ alone, so no run is due
        # and the report needs no CI line.
        folder = self.case_folder()
        base = git_commit(folder, remote_branch=None, files={".github/workflows/checks.yml": DOCS_ONLY_WORKFLOW})
        head = git_commit(folder, remote_branch=None, files={"lint/x.py": "x = 1\n"})
        steps = push(push_out(head[:7], old=base[:7]))
        fixture_ = answers(prs=[pr_entry(sha=head)], runs=[])
        decision, _, _ = self.stop(turn(NO_REPORT, steps), fixture_, folder=folder)
        self.assertEqual(decision, "block", "a report-less push turn was not blocked (scope check)")
        decision, reason, _ = self.stop(turn(REPORT, steps), fixture_, folder=folder)
        self.assertIsNone(decision, "a push that no workflow's path filter matches was held for a run that never "
                          "starts: " + reason)

    def test_push_that_a_workflow_path_filter_matches_still_owes_a_running_ci_line(self):
        # The same workflow, and a push that touches docs/: the run is due, so with no run listed yet the report must
        # name the head as running.
        folder = self.case_folder()
        base = git_commit(folder, remote_branch=None, files={".github/workflows/checks.yml": DOCS_ONLY_WORKFLOW})
        head = git_commit(folder, remote_branch=None, files={"docs/guide.md": "guide\n"})
        steps = push(push_out(head[:7], old=base[:7]))
        fixture_ = answers(prs=[pr_entry(sha=head)], runs=[])
        decision, _, _ = self.stop(turn(NO_REPORT, steps), fixture_, folder=folder)
        self.assertEqual(decision, "block", "a report-less push turn was not blocked (scope check)")
        decision, reason, _ = self.stop(turn(REPORT, steps), fixture_, folder=folder)
        self.assertEqual(decision, "block", "a push that a workflow path filter matches, with no run listed, "
                         "passed with no CI line")
        self.assertIn("CI running on " + head[:7], reason, "the due run is not named running: %s" % reason)

    def due_read(self, folder, new, old, cwd=None):
        """push_may_start_run for the push old..new, read from `cwd` (the repo when None). The budget's clock never
        moves, so no read runs out and the verdict is the filter's own."""
        budget = ci_wake.Budget(total=20, per_read=8, clock=StepClock([0.0]))
        return ci_wake.push_may_start_run(new, old, cwd or folder, budget)

    def git_names(self, folder, *args):
        """The names one git read lists, run in the repo: the scope a case checks before it asserts the reader."""
        return subprocess.run(["git", *args], cwd=folder, capture_output=True, text=True, check=True,
                              timeout=30).stdout.split()

    def subfolder_push(self):
        """A repo with a src/** workflow, a lint/ folder and a docs-only push. -> (folder, base, head)."""
        folder = self.case_folder()
        base = git_commit(folder, remote_branch=None, files={".github/workflows/checks.yml": SRC_ONLY_WORKFLOW,
                                                             "lint/x.py": "x = 1\n", "docs/guide.md": "guide\n"})
        head = git_commit(folder, remote_branch=None, files={"docs/guide.md": "guide v2\n"})
        return folder, base, head

    # The path-filter reader (ci_wake.workflow_runs_for, push_may_start_run). Each finding has one red case, which
    # names the defect, and green controls beside it. Each red case checks its scope first.

    def test_multi_line_flow_paths_list_keeps_a_run_due_for_a_matching_file(self):
        # Eight patterns as one flow line, then spread over lines. src/a.py matches the last one. A list the reader
        # cannot read must keep the run due, not read as no pattern at all.
        self.assertTrue(ci_wake.workflow_runs_for(flow_paths_workflow(spread=False), ["src/a.py"]),
                        "scope: the one-line form does not keep a run due for src/a.py")
        self.assertTrue(ci_wake.workflow_runs_for(flow_paths_workflow(spread=True), ["src/a.py"]),
                        "a flow paths list spread over lines was read as no pattern, so no run is due for src/a.py")

    def test_one_line_flow_paths_list_owes_no_run_for_an_unmatched_file(self):
        self.assertFalse(ci_wake.workflow_runs_for(flow_paths_workflow(spread=False), ["other/x.py"]),
                         "a one-line flow paths list kept a run due for a file none of its patterns matches")

    def test_empty_workflow_file_keeps_a_run_due(self):
        # The empty state of the reader: no `on:` block reads as a form it does not parse, so a run stays due.
        self.assertTrue(ci_wake.workflow_runs_for("", ["docs/x.md"]), "an empty workflow file was read as owing no run")

    def test_rename_out_of_a_watched_path_keeps_a_run_due(self):
        folder = self.case_folder()
        base = git_commit(folder, remote_branch=None, files={".github/workflows/checks.yml": SRC_ONLY_WORKFLOW,
                                                             "src/a.py": SOURCE})
        head = git_commit(folder, remote_branch=None, files={"docs/a.py": SOURCE}, remove=["src/a.py"])
        # Scope: the push takes src/a.py out of src/. Rename detection hides that old path from a plain name list.
        self.assertEqual(self.git_names(folder, "diff", "--name-only", "--no-renames", base, head),
                         ["docs/a.py", "src/a.py"], "scope: the push does not remove src/a.py")
        self.assertTrue(self.due_read(folder, head, base),
                        "a rename out of src/ dropped the old path from the push's names, so no run is due for src/**")

    def test_plain_edit_of_a_watched_file_keeps_a_run_due(self):
        folder = self.case_folder()
        base = git_commit(folder, remote_branch=None, files={".github/workflows/checks.yml": SRC_ONLY_WORKFLOW,
                                                             "src/a.py": SOURCE})
        head = git_commit(folder, remote_branch=None, files={"src/a.py": SOURCE + "x = 2\n"})
        self.assertTrue(self.due_read(folder, head, base), "an edit of src/a.py owes no run of the src/** workflow")

    def test_move_between_unwatched_paths_owes_no_run(self):
        folder = self.case_folder()
        base = git_commit(folder, remote_branch=None, files={".github/workflows/checks.yml": SRC_ONLY_WORKFLOW,
                                                             "docs/x.md": SOURCE})
        head = git_commit(folder, remote_branch=None, files={"docs/y.md": SOURCE}, remove=["docs/x.md"])
        self.assertFalse(self.due_read(folder, head, base), "a move between docs/ paths kept a run due for src/**")

    def test_push_read_from_a_subfolder_finds_the_workflows_at_the_root(self):
        folder, base, head = self.subfolder_push()
        # Scope: the head holds the workflow at the root, where a read from lint/ must find it.
        self.assertEqual(self.git_names(folder, "ls-tree", "-r", "--name-only", head, ".github/workflows"),
                         [".github/workflows/checks.yml"], "scope: the head holds no workflow at the root")
        self.assertFalse(self.due_read(folder, head, base, cwd=os.path.join(folder, "lint")),
                         "a push read from lint/ found no workflow and kept a run due for a docs-only push")

    def test_docs_only_push_from_the_repo_root_owes_no_run(self):
        folder, base, head = self.subfolder_push()
        self.assertFalse(self.due_read(folder, head, base), "a docs-only push kept a run due for src/** from the root")

    def test_src_push_read_from_a_subfolder_keeps_a_run_due(self):
        folder, base, head = self.subfolder_push()
        src = git_commit(folder, remote_branch=None, files={"src/a.py": "x = 2\n"})
        self.assertTrue(self.due_read(folder, src, head, cwd=os.path.join(folder, "lint")),
                        "a src/ push read from lint/ owes no run of the src/** workflow")

    def test_quoted_path_holding_space_hash_matches_its_file(self):
        text = checks_workflow('    paths:\n      - "docs/a #b.md"\n')
        self.assertTrue(ci_wake._path_passes("docs/a #b.md", ["docs/a #b.md"]),
                        "scope: the matcher does not take the path itself")
        self.assertTrue(ci_wake.workflow_runs_for(text, ["docs/a #b.md"]),
                        "a quoted path holding ' #' was cut as a comment, so its own file kept no run due")

    def test_trailing_comment_after_a_quoted_path_is_still_read(self):
        text = checks_workflow('    paths:\n      - "docs/a.md"  # the docs\n')
        self.assertTrue(ci_wake.workflow_runs_for(text, ["docs/a.md"]),
                        "a real trailing comment after a quoted path hid the path")
        self.assertFalse(ci_wake.workflow_runs_for(text, ["docs/b.md"]), "a path after the comment matched the filter")

    def test_quoted_path_holding_space_hash_does_not_match_another_file(self):
        text = checks_workflow('    paths:\n      - "docs/a #b.md"\n')
        self.assertFalse(ci_wake.workflow_runs_for(text, ["docs/a.md"]),
                         "a quoted path holding ' #' matched a different file")

    def test_lone_quote_in_a_name_and_a_comment_does_not_hide_the_filter(self):
        # A lone apostrophe is text, not the start of a string: the path and the comment after it still read.
        text = ("name: Don't build\non:\n  push:\n    paths:\n      - docs/don't.md  # don't widen this\n"
                "jobs:\n  unit:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ok\n")
        self.assertTrue(ci_wake.workflow_runs_for(text, ["docs/don't.md"]),
                        "a lone apostrophe hid the path docs/don't.md")
        self.assertFalse(ci_wake.workflow_runs_for(text, ["src/a.py"]),
                         "a lone apostrophe widened the filter to src/a.py")

    def test_block_scalar_text_does_not_change_the_push_filter(self):
        # A run script after the on: block holds filter-looking text and a `#` line. Only the on: block is the filter.
        text = ("on:\n  push:\n    paths: [src/**]\njobs:\n  unit:\n    steps:\n      - run: |\n"
                "          # a shell comment, not a workflow one\n          paths: [docs/**]\n          on: push\n")
        self.assertTrue(ci_wake.workflow_runs_for(text, ["src/a.py"]), "the on: block's own filter was lost")
        self.assertFalse(ci_wake.workflow_runs_for(text, ["docs/guide.md"]),
                         "text in a run script widened the push filter to docs/")

    def test_rewrite_that_still_lacks_the_ci_line_is_blocked(self):
        # The first reply holds a report but no CI line, so the Stop blocks for the CI line alone. Its rewrite, the
        # stop_hook_active Stop of the same turn, must still hold the line, so a rewrite without it is blocked.
        session = uuid.uuid4().hex
        steps = push(push_out(HEAD7))
        fixture_ = answers(prs=[pr_entry()], runs=[PENDING])
        decision, _, _ = self.stop(turn(REPORT, steps), fixture_, session_id=session)
        self.assertEqual(decision, "block", "a report with no CI line was not blocked for the pending push")
        decision, reason, _ = self.stop(turn(REPORT, steps), fixture_, stop_active=True, session_id=session)
        self.assertEqual(decision, "block",
                         "the rewrite of a CI-only block still lacks the CI line and passed unchecked")
        self.assertIn("CI running on " + HEAD7, reason,
                      "the rewrite's block does not name the pending head: %s" % reason)

    def test_rewrite_that_names_the_ci_line_passes(self):
        # The rewrite of a CI-only block that adds the running line passes.
        session = uuid.uuid4().hex
        steps = push(push_out(HEAD7))
        fixture_ = answers(prs=[pr_entry()], runs=[PENDING])
        decision, _, _ = self.stop(turn(REPORT, steps), fixture_, session_id=session)
        self.assertEqual(decision, "block", "a report with no CI line was not blocked for the pending push")
        decision, reason, _ = self.stop(turn(RUNNING, steps), fixture_, stop_active=True, session_id=session)
        self.assertIsNone(decision, "a rewrite that names the running CI line was blocked: " + reason)

    def test_pending_run_on_ready_pr_blocks_until_next_names_running(self):
        decision, reason, _ = self.stop(turn(REPORT, push(push_out(HEAD7))),
                                        answers(prs=[pr_entry()], runs=[PENDING]))
        self.assertEqual(decision, "block", "a push to a ready PR with a pending run passed with no CI line")
        self.assertIn("CI running on " + HEAD7, reason, "the block does not name the pending head")

    def test_red_run_on_ready_pr_blocks_until_next_names_red(self):
        decision, reason, _ = self.stop(turn(REPORT, push(push_out(HEAD7))),
                                        answers(prs=[pr_entry()], runs=[RED_RUN]))
        self.assertEqual(decision, "block", "a push whose run ended red passed with no CI line")
        self.assertIn("CI red on " + HEAD7, reason, "the block does not name the red head")

    def test_no_run_yet_on_ready_pr_blocks_as_running(self):
        decision, reason, _ = self.stop(turn(REPORT, push(push_out(HEAD7))),
                                        answers(prs=[pr_entry()], runs=[]))
        self.assertEqual(decision, "block", "a ready PR with no run yet passed with no CI line")
        self.assertIn("CI running on " + HEAD7, reason, "a ready PR with no run yet is not named running")

    def test_only_skipped_runs_on_ready_pr_block_as_running_not_red(self):
        decision, reason, _ = self.stop(turn(REPORT, push(push_out(HEAD7))),
                                        answers(prs=[pr_entry()], runs=[SKIPPED]))
        self.assertEqual(decision, "block", "a ready PR whose runs all skipped passed with no CI line")
        self.assertIn("CI running on " + HEAD7, reason,
                      "a ready PR whose runs all skipped is not named running (skipped is no run)")

    def test_push_to_main_with_pending_run_blocks_as_running(self):
        steps = push(push_out(HEAD7, dst="main"), command="git push origin HEAD:main")
        decision, reason, _ = self.stop(turn(REPORT, steps), answers(runs=[PENDING]))
        self.assertEqual(decision, "block", "a push to main with a pending run passed with no CI line")
        self.assertIn("CI running on " + HEAD7, reason, "a push to main is not named running")

    def test_gh_error_blocks_as_unknown(self):
        decision, reason, _ = self.stop(turn(REPORT, push(push_out(HEAD7))),
                                        answers(prs=[pr_entry()], mode="error"))
        self.assertEqual(decision, "block", "a push whose gh read exited 1 passed with no CI line")
        self.assertIn("CI unknown on " + HEAD7, reason, "a failed read is not named unknown")

    def test_gh_non_json_blocks_as_unknown(self):
        decision, reason, _ = self.stop(turn(REPORT, push(push_out(HEAD7))),
                                        answers(prs=[pr_entry()], mode="garbage"))
        self.assertEqual(decision, "block", "a push whose gh read printed non-JSON passed with no CI line")
        self.assertIn("CI unknown on " + HEAD7, reason, "a non-JSON read is not named unknown")

    def test_gh_missing_blocks_as_unknown(self):
        decision, reason, _ = self.stop(turn(REPORT, push(push_out(HEAD7))),
                                        answers(prs=[pr_entry()], runs=[PENDING]), no_gh=True)
        self.assertEqual(decision, "block", "a push with no gh on PATH passed with no CI line")
        self.assertIn("CI unknown on " + HEAD7, reason, "a missing gh is not named unknown")

    def test_push_files_blocks_until_next_names_running(self):
        decision, reason, _ = self.stop(turn(REPORT, mcp_push()), answers(prs=[pr_entry()], runs=[PENDING]))
        self.assertEqual(decision, "block", "a push_files commit with a pending run passed with no CI line")
        self.assertIn("CI running on " + HEAD7, reason, "a push_files head is not named running")

    def test_done_item_may_not_claim_a_pending_head(self):
        decision, _, _ = self.stop(turn(DONE_CLAIMS_HEAD, push(push_out(HEAD7))),
                                   answers(prs=[pr_entry()], runs=[PENDING]))
        self.assertEqual(decision, "block", "a Done item named a pending head as built and the guard passed it")

    def test_two_pushes_block_on_the_newest_head(self):
        steps = [push(push_out(MID7, old=OLD7), use_id="tu_1"), push(push_out(HEAD7, old=MID7), use_id="tu_2")]
        decision, reason, _ = self.stop(turn(REPORT, *steps),
                                        answers(prs=[pr_entry()], runs=[PENDING, PENDING_MID]))
        self.assertEqual(decision, "block", "two pushes with a pending newest head passed with no CI line")
        self.assertIn("CI running on " + HEAD7, reason, "the block does not name the newest head")
        self.assertNotIn(MID7, reason, "the block names the older head of the turn")

    def test_built_done_item_naming_a_red_head_blocks(self):
        reply = "> **Done** BUILT %s\n> **Next** CI red on %s" % (HEAD7, HEAD7)
        decision, reason, _ = self.stop(turn(reply, push(push_out(HEAD7))), answers(prs=[pr_entry()], runs=[RED_RUN]))
        self.assertEqual(decision, "block", "a Done item named a red head as built and the guard passed it")
        self.assertIn(HEAD7, reason, "the block does not name the red head")

    def test_branch_named_with_rejected_is_checked(self):
        steps = push(push_out(HEAD7, dst=REJECTED_BRANCH), command="git push origin HEAD:%s" % REJECTED_BRANCH)
        fixture_ = answers(prs=[pr_entry(branch=REJECTED_BRANCH)], runs=[PENDING])
        decision, _, _ = self.stop(turn(NO_REPORT, steps), fixture_)
        self.assertEqual(decision, "block", "a push to %s was not treated as a landing (scope check)" % REJECTED_BRANCH)
        decision, reason, _ = self.stop(turn(REPORT, steps), fixture_)
        self.assertEqual(decision, "block", "a push to %s was skipped: the word rejected in the branch name "
                         "read as a rejected push" % REJECTED_BRANCH)
        self.assertIn("CI running on " + HEAD7, reason, "the push to %s was not named running" % REJECTED_BRANCH)

    def test_multi_ref_push_checks_the_accepted_head_past_a_rejected_ref(self):
        output = " ! [rejected]        HEAD -> main (fetch first)\n   %s..%s  HEAD -> %s\n" % (OLD7, HEAD7, BRANCH)
        steps = push(output, command="git push origin HEAD:main HEAD:%s" % BRANCH)
        fixture_ = answers(prs=[pr_entry()], runs=[PENDING])
        decision, _, _ = self.stop(turn(NO_REPORT, steps), fixture_)
        self.assertEqual(decision, "block", "a multi-ref push was not treated as a landing (scope check)")
        decision, reason, _ = self.stop(turn(REPORT, steps), fixture_)
        self.assertEqual(decision, "block", "a multi-ref push with one rejected ref skipped the accepted head")
        self.assertIn("CI running on " + HEAD7, reason, "the accepted head was not named running")

    def test_cd_then_push_reads_the_head_in_that_checkout(self):
        folder = self.case_folder()
        other = os.path.join(folder, "other")
        os.makedirs(other)
        head = git_commit(other)
        steps = bash("cd '%s' && git push origin HEAD:%s" % (other.replace("\\", "/"), BRANCH), "")
        fixture_ = answers(prs=[pr_entry(sha=head)], runs=[run_entry(None, sha=head, status="in_progress")])
        decision, _, _ = self.stop(turn(NO_REPORT, steps), fixture_, folder=folder)
        self.assertEqual(decision, "block", "a report-less cd-and-push turn was not blocked (scope check)")
        decision, reason, _ = self.stop(turn(REPORT, steps), fixture_, folder=folder)
        self.assertEqual(decision, "block", "a push after cd into another checkout was not checked: the head was "
                         "read in the hook's repo, not that checkout")
        self.assertIn("CI running on " + head[:7], reason, "the head in the other checkout was not named running")

    def test_rewrite_after_a_missing_report_block_reads_no_gh_and_marker_carries_each_head(self):
        sid = "push-marker-" + uuid.uuid4().hex
        folder = self.case_folder()
        steps = [push(push_out(HEAD7), command="git push origin HEAD:%s" % BRANCH, use_id="tu_1"),
                 push(push_out(OTHER7, dst=OTHER_BRANCH), command="git push origin HEAD:%s" % OTHER_BRANCH,
                      use_id="tu_2")]
        fixture_ = answers(prs=[pr_entry(), pr_entry(branch=OTHER_BRANCH, sha=OTHER, number=1431)],
                           runs=[PENDING, PENDING_OTHER])
        decision, _, _ = self.stop(turn(NO_REPORT, *steps), fixture_, folder=folder, session_id=sid)
        self.assertEqual(decision, "block", "a report-less two-push turn was not blocked (scope check)")
        marker = local_time.report_marker_path(sid)
        self.assertIsNotNone(marker, "no missing-report marker path for this session")
        self.assertTrue(os.path.exists(marker), "the missing-report block left no marker")
        with open(marker, encoding="utf-8") as f:
            marker_lines = f.read().split("\n")
        for sha7 in (HEAD7, OTHER7):
            self.assertTrue(any(line.startswith("%s pending" % sha7) for line in marker_lines),
                            "the marker does not carry %s's pending state: %r" % (sha7, marker_lines))
        before = len(trg.GH_STUB.read_log(os.path.join(folder, "gh.log")))
        self.assertGreaterEqual(before, 1, "the first Stop read no CI, so the marker has no state to carry")
        reply = "> **Done** BUILT abc123\n> **Next** CI running on %s; CI running on %s" % (HEAD7, OTHER7)
        decision, reason, _ = self.stop(turn(reply, *steps), fixture_, stop_active=True, folder=folder,
                                        session_id=sid)
        after = len(trg.GH_STUB.read_log(os.path.join(folder, "gh.log")))
        self.assertEqual(after, before, "the rewrite after a missing-report block read gh again")
        self.assertIsNone(decision, "the rewrite that holds each head's running line was blocked: " + reason)
        # The negative: a rewrite that drops OTHER7's line must block, and still read no gh.
        decision, _, _ = self.stop(turn(NO_REPORT, *steps), fixture_, folder=folder, session_id=sid)
        self.assertEqual(decision, "block", "a second report-less two-push turn was not blocked (scope check)")
        before_drop = len(trg.GH_STUB.read_log(os.path.join(folder, "gh.log")))
        only_head = "> **Done** BUILT abc123\n> **Next** CI running on %s" % HEAD7
        decision, reason, _ = self.stop(turn(only_head, *steps), fixture_, stop_active=True, folder=folder,
                                        session_id=sid)
        after_drop = len(trg.GH_STUB.read_log(os.path.join(folder, "gh.log")))
        self.assertEqual(after_drop, before_drop, "the rewrite that drops a head read gh again")
        self.assertEqual(decision, "block", "a rewrite that drops the other branch's running line passed")
        self.assertIn("CI running on " + OTHER7, reason, "the block does not name the dropped head")

    def test_push_ci_check_that_raises_reads_unknown_in_the_note(self):
        # The raise is the import of ci_wake inside push_ci_states, the check's first read. The turn passes with no
        # word that the check did not run.
        steps = push(push_out(HEAD7))
        fixture_ = answers(prs=[pr_entry()], runs=[PENDING])
        decision, reason, _ = self.stop(turn(REPORT, steps), fixture_)
        self.assertEqual(decision, "block", "a push turn with a pending run and no CI line was not blocked (scope)")
        self.assertIn("CI running on " + HEAD7, reason, "the scope check's block does not name the pending head")
        decision, note = self.stop_note(turn(REPORT, steps), fixture_, block=("ci_wake",))
        self.assertNotEqual(decision, "block", "a push turn whose CI check raised was blocked, not noted")
        self.assertIn(PUSH_UNKNOWN_NOTE, note, "a push turn whose CI check raised passed with no UNKNOWN note")

    def test_push_turn_with_an_unloadable_guard_reads_unknown_in_the_note(self):
        # The guard module's import fails, so turn_landed reads the push as no landing and push_ci_states never runs.
        steps = push(push_out(HEAD7))
        fixture_ = answers(prs=[pr_entry()], runs=[PENDING])
        decision, reason, _ = self.stop(turn(REPORT, steps), fixture_)
        self.assertEqual(decision, "block", "a push turn with a pending run and no CI line was not blocked (scope)")
        self.assertIn("CI running on " + HEAD7, reason, "the scope check's block does not name the pending head")
        decision, note = self.stop_note(turn(REPORT, steps), fixture_, block=("guard",))
        self.assertNotEqual(decision, "block", "a push turn whose guard module did not load was blocked, not noted")
        self.assertIn(PUSH_UNKNOWN_NOTE, note,
                      "a push turn whose guard module did not load passed with no UNKNOWN note")

    def test_failed_branch_read_names_the_branch_read_not_the_budget(self):
        # A detached HEAD makes the branch read raise. The block reason must carry that read's own message, not a
        # read budget that was never spent.
        folder = self.case_folder()
        git_commit(folder, detach=True)
        steps = push("", command="git push")
        fixture_ = answers(prs=[pr_entry()], runs=[PENDING])
        decision, reason, _ = self.stop(turn(REPORT, steps), fixture_, folder=folder)
        self.assertEqual(decision, "block", "a bare push whose branch read failed passed with no CI line")
        self.assertNotIn("read budget", reason,
                         "a failed branch read is reported as a read budget run-out: " + reason)
        with self.assertRaises(ci_wake.Unknown) as raised:
            ci_wake.current_branch(folder)
        self.assertIn(str(raised.exception), reason,
                      "the block does not name the branch read's failure (%s): %s" % (raised.exception, reason))

    def test_push_with_no_remote_tracking_ref_reads_unknown_not_silent(self):
        # The pushed branch has no remote-tracking ref, so the head cannot be named (commit_of gives ""). The turn
        # must read as unknown on the branch, never pass with the head dropped.
        folder = self.case_folder()
        git_commit(folder, remote_branch=None)
        steps = push("", command="git push origin HEAD:%s" % BRANCH)
        fixture_ = answers(prs=[pr_entry()], runs=[PENDING])
        decision, _, _ = self.stop(turn(NO_REPORT, steps), fixture_, folder=folder)
        self.assertEqual(decision, "block", "a report-less push with no remote-tracking ref was not blocked "
                         "(scope check)")
        decision, reason, _ = self.stop(turn(REPORT, steps), fixture_, folder=folder)
        self.assertEqual(decision, "block", "a push with no remote-tracking ref for %s passed with no CI line: the "
                         "head was dropped" % BRANCH)
        self.assertIn("CI unknown on " + BRANCH, reason, "the block does not name the push as unknown: " + reason)
        self.assertNotIn("read budget", reason,
                         "a push with no remote-tracking ref is reported as a read budget run-out: " + reason)
        decision, _, _ = self.stop(turn(UNKNOWN_BRANCH, steps), fixture_, folder=folder)
        self.assertIsNone(decision, "a report that holds the unknown line was blocked")

    def test_short_name_tag_push_with_a_new_tag_line_needs_no_ci_line(self):
        # `v1.0` is a tag, not a branch: the push names no head, so no CI line is due and no branch is read.
        steps = push(REMOTE_LINE + " * [new tag]         %s -> %s\n" % (TAG, TAG), command="git push origin %s" % TAG)
        fixture_ = answers(prs=[pr_entry()], runs=[PENDING])
        decision, _, _ = self.stop(turn(NO_REPORT, steps), fixture_)
        self.assertEqual(decision, "block", "a report-less turn with a tag push was not blocked (scope check)")
        decision, reason, _ = self.stop(turn(REPORT, steps), fixture_)
        self.assertIsNone(decision, "a push of tag %s with a [new tag] line was blocked for CI, though it names no "
                          "head: %s" % (TAG, reason))

    def test_short_name_tag_push_with_no_ref_line_needs_no_ci_line(self):
        steps = push(REMOTE_LINE, command="git push origin %s" % TAG)
        fixture_ = answers(prs=[pr_entry()], runs=[PENDING])
        decision, _, _ = self.stop(turn(NO_REPORT, steps), fixture_)
        self.assertEqual(decision, "block", "a report-less turn with a tag push was not blocked (scope check)")
        decision, reason, _ = self.stop(turn(REPORT, steps), fixture_)
        self.assertIsNone(decision, "a push of tag %s with no ref line was blocked for CI, though it names no head: "
                          "%s" % (TAG, reason))

    def test_branch_head_is_kept_when_a_tag_of_its_name_is_pushed_too(self):
        # `git push origin feat --tags` prints the branch's ref line and a [new tag] line of one name. The ref line
        # makes the name a branch, so the branch is checked at the ref line's new sha, and the tag does not drop it.
        output = push_out(HEAD7, old=OLD7, dst=FEAT) + " * [new tag]         %s -> %s\n" % (FEAT, FEAT)
        steps = push(output, command="git push origin %s --tags" % FEAT)
        fixture_ = answers(prs=[pr_entry(branch=FEAT)], runs=[PENDING])
        decision, _, _ = self.stop(turn(NO_REPORT, steps), fixture_)
        self.assertEqual(decision, "block", "a report-less turn with a branch and a tag of one name was not blocked "
                         "(scope check)")
        decision, reason, _ = self.stop(turn(REPORT, steps), fixture_)
        self.assertEqual(decision, "block", "a push of branch %s with --tags passed with no CI line: the branch head "
                         "was dropped for the tag of its name" % FEAT)
        self.assertIn("CI running on " + HEAD7, reason, "the branch head of the push is not named running: " + reason)

    def test_new_branch_is_kept_when_a_tag_of_its_name_is_pushed_too(self):
        # `git push origin feat --tags` prints a [new branch] line, which gives no sha, and a [new tag] line of one name.
        # The head of a new branch is read from the remote-tracking ref the push sets, so the branch is checked at that
        # commit. The tag sits on an older commit, which the head read must not take.
        folder = self.case_folder()
        git_commit(folder, remote_branch=None, tag=FEAT)  # the tag, on an older commit
        head = git_commit(folder, remote_branch=FEAT, on_branch=FEAT)  # the new branch's head
        output = (REMOTE_LINE + " * [new branch]      %s -> %s\n" % (FEAT, FEAT)
                  + " * [new tag]         %s -> %s\n" % (FEAT, FEAT))
        steps = push(output, command="git push origin %s --tags" % FEAT)
        fixture_ = answers(prs=[pr_entry(branch=FEAT, sha=head)],
                           runs=[run_entry(None, sha=head, status="in_progress")])
        decision, _, _ = self.stop(turn(NO_REPORT, steps), fixture_, folder=folder)
        self.assertEqual(decision, "block", "a report-less turn with a new branch and a tag of one name was not blocked "
                         "(scope check)")
        decision, reason, _ = self.stop(turn(REPORT, steps), fixture_, folder=folder)
        self.assertEqual(decision, "block", "a push of new branch %s with --tags passed with no CI line: the branch was "
                         "dropped for the tag of its name" % FEAT)
        self.assertIn("CI running on " + head[:7], reason, "the new branch's head is not named running: " + reason)

    def test_colon_form_tag_only_push_needs_no_ci_line(self):
        # `git push origin v1.0:v1.0` names a tag in the colon form, with a [new tag] line and no ref line. The local
        # tag exists, as git needs for a push of it, so the name reads as a tag and no CI line is due.
        folder = self.case_folder()
        git_commit(folder, remote_branch=None, tag=TAG)
        steps = push(REMOTE_LINE + " * [new tag]         %s -> %s\n" % (TAG, TAG),
                     command="git push origin %s:%s" % (TAG, TAG))
        fixture_ = answers(prs=[pr_entry()], runs=[PENDING])
        decision, _, _ = self.stop(turn(NO_REPORT, steps), fixture_, folder=folder)
        self.assertEqual(decision, "block", "a report-less colon-form tag push was not blocked (scope check)")
        decision, reason, _ = self.stop(turn(REPORT, steps), fixture_, folder=folder)
        self.assertIsNone(decision, "a colon-form push of tag %s was blocked for CI, though the name is a tag: %s"
                          % (TAG, reason))

    # A push with no ref line names the head of the checked-out branch (report_guard._heads_of_git_push). These cases
    # check that the named head is that branch's own, and that a failed branch read names HEAD as unknown.

    def test_bare_push_names_the_checked_out_branch_head(self):
        for command in ("git push", "git push origin HEAD"):
            for branch in (BRANCH, OTHER_BRANCH):
                with self.subTest(command=command, branch=branch):
                    other = OTHER_BRANCH if branch == BRANCH else BRANCH
                    folder = self.case_folder()
                    git_commit(folder, remote_branch=other)  # origin/<other> at a commit of its own
                    head = git_commit(folder, remote_branch=branch, on_branch=branch)  # HEAD on <branch>
                    fixture_ = answers(prs=[pr_entry(branch=branch, sha=head)],
                                       runs=[run_entry(None, sha=head, status="in_progress")])
                    steps = push("", command=command)
                    decision, _, _ = self.stop(turn(NO_REPORT, steps), fixture_, folder=folder)
                    self.assertEqual(decision, "block", "a report-less %r turn on %s was not blocked (scope check)"
                                     % (command, branch))
                    decision, reason, _ = self.stop(turn(REPORT, steps), fixture_, folder=folder)
                    self.assertEqual(decision, "block", "%r with no ref line, on %s, read no head: the check passed "
                                     "it with no CI line" % (command, branch))
                    self.assertIn("CI running on " + head[:7], reason,
                                  "%r on %s did not name the checked-out branch's head: %s"
                                  % (command, branch, reason))

    def test_failed_branch_read_on_a_bare_push_reads_unknown_on_head(self):
        for command in ("git push", "git push origin HEAD"):
            with self.subTest(command=command):
                folder = self.case_folder()
                git_commit(folder, detach=True)
                steps = push("", command=command)
                fixture_ = answers(prs=[pr_entry()], runs=[PENDING])
                decision, _, _ = self.stop(turn(NO_REPORT, steps), fixture_, folder=folder)
                self.assertEqual(decision, "block", "a report-less %r turn was not blocked (scope check)" % command)
                decision, reason, _ = self.stop(turn(REPORT, steps), fixture_, folder=folder)
                self.assertEqual(decision, "block", "%r whose branch read failed passed with no CI line: the push "
                                 "was dropped, not read unknown" % command)
                self.assertIn("CI unknown on HEAD", reason, "%r whose branch read failed is not named unknown on "
                              "HEAD: %s" % (command, reason))
                decision, _, _ = self.stop(turn(UNKNOWN_HEAD, steps), fixture_, folder=folder)
                self.assertIsNone(decision, "a report that holds the unknown line on HEAD was blocked")

    def test_push_to_a_url_remote_reads_unknown_on_the_branch_and_blocks_once(self):
        # A URL remote updates no remote-tracking ref, so the head is not named. The branch reads unknown, the turn
        # blocks once, and the rewrite that holds the unknown line passes. Covers the URL branch of
        # report_guard._heads_of_git_push.
        outputs = (("no ref line", REMOTE_LINE), ("a [new branch] line",
                                                   REMOTE_LINE + " * [new branch]      %s -> %s\n" % (BRANCH, BRANCH)))
        for label, output in outputs:
            with self.subTest(output=label):
                steps = push(output, command="git push %s HEAD:%s" % (REMOTE_URL, BRANCH))
                fixture_ = answers(prs=[pr_entry()], runs=[PENDING])
                decision, _, _ = self.stop(turn(NO_REPORT, steps), fixture_)
                self.assertEqual(decision, "block", "a report-less URL push with %s was not blocked (scope check)"
                                 % label)
                decision, reason, _ = self.stop(turn(REPORT, steps), fixture_)
                self.assertEqual(decision, "block", "a URL push with %s passed with no CI line: its head is not named, "
                                 "so it reads unknown" % label)
                self.assertIn("CI unknown on " + BRANCH, reason, "a URL push with %s is not named unknown on %s: %s"
                              % (label, BRANCH, reason))
                decision, _, _ = self.stop(turn(UNKNOWN_BRANCH, steps), fixture_)
                self.assertIsNone(decision, "a URL push with %s: the report that holds the unknown line was blocked"
                                  % label)

    # A bare name with no ref line (`git push origin feat`) is a branch, a tag or both, by what the clone holds. Each
    # case builds its refs in a real repo and runs the Stop hook, as the cases above do.

    def test_bare_name_with_a_local_branch_and_its_remote_ref_names_the_head(self):
        # The remote-tracking ref names the head, so the name is a branch and no tag read runs.
        folder = self.case_folder()
        head = git_commit(folder, remote_branch=FEAT, on_branch=FEAT)
        steps = push("", command="git push origin %s" % FEAT)
        fixture_ = answers(prs=[pr_entry(branch=FEAT, sha=head)],
                           runs=[run_entry(None, sha=head, status="in_progress")])
        decision, _, _ = self.stop(turn(NO_REPORT, steps), fixture_, folder=folder)
        self.assertEqual(decision, "block", "a report-less bare-name push was not blocked (scope check)")
        decision, reason, _ = self.stop(turn(REPORT, steps), fixture_, folder=folder)
        self.assertEqual(decision, "block", "a bare-name push of a branch with a remote-tracking ref passed with no CI "
                         "line: the name was read as a tag")
        self.assertIn("CI running on " + head[:7], reason, "the bare-name push's branch head is not named running")

    def test_bare_name_with_only_a_remote_tracking_ref_reads_as_a_branch(self):
        # The local branch is gone: only origin/feat names a commit, so the name is a branch and its head is read from
        # that ref.
        folder = self.case_folder()
        head = git_commit(folder, remote_branch=FEAT)
        steps = push("", command="git push origin %s" % FEAT)
        fixture_ = answers(prs=[pr_entry(branch=FEAT, sha=head)],
                           runs=[run_entry(None, sha=head, status="in_progress")])
        decision, _, _ = self.stop(turn(NO_REPORT, steps), fixture_, folder=folder)
        self.assertEqual(decision, "block", "a report-less bare-name push was not blocked (scope check)")
        decision, reason, _ = self.stop(turn(REPORT, steps), fixture_, folder=folder)
        self.assertEqual(decision, "block", "a bare-name push with only a remote-tracking ref passed with no CI line: "
                         "the name was read as a tag")
        self.assertIn("CI running on " + head[:7], reason, "the bare-name push's head is not named running")

    def test_first_push_of_a_branch_on_a_single_branch_clone_reads_the_local_head(self):
        # A single-branch clone has no remote-tracking ref for a branch it has not pushed before. The head is read from
        # the local branch the push sends, so the report must name that commit, not an unknown read.
        folder = self.case_folder()
        head = git_commit(folder, remote_branch=None, on_branch=FEAT)
        steps = push(REMOTE_LINE + " * [new branch]      %s -> %s\n" % (FEAT, FEAT),
                     command="git push origin %s" % FEAT)
        fixture_ = answers(prs=[pr_entry(branch=FEAT, sha=head)],
                           runs=[run_entry(None, sha=head, status="in_progress")])
        decision, _, _ = self.stop(turn(NO_REPORT, steps), fixture_, folder=folder)
        self.assertEqual(decision, "block", "a report-less first push on a single-branch clone was not blocked (scope "
                         "check)")
        running = "> **Done** BUILT abc123\n> **Next** CI running on %s" % head[:7]
        decision, reason, _ = self.stop(turn(running, steps), fixture_, folder=folder)
        self.assertIsNone(decision, "the first push of %s on a single-branch clone read its head unknown, not from the "
                          "local commit %s: %s" % (FEAT, head[:7], reason))

    def test_bare_name_with_a_tag_and_a_local_branch_reads_the_local_branch_head(self):
        # The tag and the local branch share a name, and the branch has no remote-tracking ref. The push sends the
        # branch, so its local head is read: not the tag's commit, and not unknown.
        folder = self.case_folder()
        git_commit(folder, remote_branch=None, tag=FEAT)
        head = git_commit(folder, remote_branch=None, on_branch=FEAT)
        steps = push("", command="git push origin %s" % FEAT)
        fixture_ = answers(prs=[pr_entry(branch=FEAT, sha=head)],
                           runs=[run_entry(None, sha=head, status="in_progress")])
        decision, _, _ = self.stop(turn(NO_REPORT, steps), fixture_, folder=folder)
        self.assertEqual(decision, "block", "a report-less bare-name push was not blocked (scope check)")
        decision, reason, _ = self.stop(turn(REPORT, steps), fixture_, folder=folder)
        self.assertEqual(decision, "block", "a bare-name push of a tag and a local branch of one name passed with no "
                         "CI line: the branch's local head was not read")
        self.assertIn("CI running on " + head[:7], reason,
                      "the bare-name push's local branch head is not named running on %s: %s" % (head[:7], reason))
        decision, _, _ = self.stop(turn("> **Done** BUILT abc123\n> **Next** CI running on %s" % head[:7], steps),
                                   fixture_, folder=folder)
        self.assertIsNone(decision, "a report that holds the running line on %s was blocked" % head[:7])

    def test_bare_name_with_a_tag_and_a_branch_with_its_remote_ref_names_the_branch_head(self):
        # The tag sits on an older commit than the branch's head, so the head named must be the branch's own. The
        # remote-tracking ref is read first, so the tag is never read as the name.
        folder = self.case_folder()
        git_commit(folder, remote_branch=None, tag=FEAT)
        head = git_commit(folder, remote_branch=FEAT, on_branch=FEAT)
        steps = push("", command="git push origin %s" % FEAT)
        fixture_ = answers(prs=[pr_entry(branch=FEAT, sha=head)],
                           runs=[run_entry(None, sha=head, status="in_progress")])
        decision, _, _ = self.stop(turn(NO_REPORT, steps), fixture_, folder=folder)
        self.assertEqual(decision, "block", "a report-less bare-name push was not blocked (scope check)")
        decision, reason, _ = self.stop(turn(REPORT, steps), fixture_, folder=folder)
        self.assertEqual(decision, "block", "a bare-name push of a tag and a branch with its remote ref passed with no "
                         "CI line: the name was read as a tag")
        self.assertIn("CI running on " + head[:7], reason, "the bare-name push's branch head is not named running")

    def test_bare_name_with_only_a_local_tag_reads_as_a_tag(self):
        # With no branch of the name, a local tag makes the bare name a tag: it names no head, so no CI line is due.
        folder = self.case_folder()
        git_commit(folder, remote_branch=None, tag=FEAT)
        steps = push(REMOTE_LINE, command="git push origin %s" % FEAT)
        fixture_ = answers(prs=[pr_entry(branch=FEAT)], runs=[PENDING])
        decision, _, _ = self.stop(turn(NO_REPORT, steps), fixture_, folder=folder)
        self.assertEqual(decision, "block", "a report-less bare-name push of a tag was not blocked (scope check)")
        decision, reason, _ = self.stop(turn(REPORT, steps), fixture_, folder=folder)
        self.assertIsNone(decision, "a bare-name push of a local tag was blocked for CI, though the name is a tag: "
                          + reason)

    def test_ref_line_to_a_refs_tags_name_reads_no_branch_head(self):
        # git writes the full ref, refs/tags/<name>, as the destination when a branch of that name exists too. That line
        # names a tag, so the check reads no PR or run for it and asks for no CI line.
        folder = self.case_folder()
        git_commit(folder, remote_branch=FEAT, on_branch=FEAT)
        steps = push(push_out(HEAD7, dst="refs/tags/%s" % FEAT), command="git push origin HEAD:refs/tags/%s" % FEAT)
        fixture_ = answers(prs=[pr_entry(branch=FEAT)], runs=[PENDING])
        decision, _, _ = self.stop(turn(NO_REPORT, steps), fixture_, folder=folder)
        self.assertEqual(decision, "block", "a report-less tag push was not blocked (scope check)")
        decision, reason, calls = self.stop(turn(REPORT, steps), fixture_, folder=folder)
        self.assertIsNone(decision, "a push whose ref line names the tag refs/tags/%s was blocked for CI: %s"
                          % (FEAT, reason))
        self.assertFalse([arg for call in calls for arg in call if "refs/tags" in arg],
                         "the tag %s was read as a branch head: gh was asked %s" % (FEAT, calls))

    def test_tags_push_with_no_ref_line_names_no_head_and_reports_no_unknown_check(self):
        # A `git push origin --tags` that prints no ref line names no head. The check reads nothing: it asks for no CI
        # line and does not report that the check failed to run.
        folder = self.case_folder()
        git_commit(folder, remote_branch=None, on_branch=FEAT, tag=TAG)
        steps = push(REMOTE_LINE + " * [new tag]         %s -> %s\n" % (TAG, TAG), command="git push origin --tags")
        fixture_ = answers(prs=[pr_entry(branch=FEAT)], runs=[PENDING])
        decision, _, _ = self.stop(turn(NO_REPORT, steps), fixture_, folder=folder)
        self.assertEqual(decision, "block", "a report-less --tags push was not blocked (scope check)")
        done, _ = self.run_stop(turn(REPORT, steps), fixture_, folder=folder)
        decision, reason = block_of(done)
        self.assertIsNone(decision, "a --tags push with no ref line was blocked for CI, though it names no head: "
                          + reason)
        self.assertNotIn(PUSH_UNKNOWN_NOTE, done.stdout, "a --tags push with no ref line reported that the push check "
                         "did not run")

    def test_green_run_on_ready_pr_passes(self):
        decision, reason, _ = self.stop(turn(REPORT, push(push_out(HEAD7))),
                                        answers(prs=[pr_entry()], runs=[GREEN]))
        self.assertIsNone(decision, "a push to a ready PR whose run is green was blocked: " + reason)

    def test_draft_pr_with_skipped_runs_passes(self):
        decision, reason, _ = self.stop(turn(REPORT, push(push_out(HEAD7))),
                                        answers(prs=[pr_entry(draft=True)], runs=[SKIPPED]))
        self.assertIsNone(decision, "a push to a draft PR was blocked: " + reason)

    def test_branch_with_no_pr_passes(self):
        decision, reason, _ = self.stop(turn(REPORT, push(push_out(HEAD7))), answers())
        self.assertIsNone(decision, "a push to a branch with no PR was blocked: " + reason)

    def test_report_that_names_the_state_passes(self):
        cases = [
            ("running", RUNNING, answers(prs=[pr_entry()], runs=[PENDING])),
            ("red", RED, answers(prs=[pr_entry()], runs=[RED_RUN])),
            ("unknown", UNKNOWN, answers(prs=[pr_entry()], mode="error")),
        ]
        for state, reply, fixture_ in cases:
            with self.subTest(state=state):
                decision, reason, _ = self.stop(turn(reply, push(push_out(HEAD7))), fixture_)
                self.assertIsNone(decision, "a report that holds the %s line was blocked: %s" % (state, reason))

    def test_tag_delete_and_dry_run_pushes_read_no_ci(self):
        dry_run = "To https://github.com/shivinate7/claude-settings.git\n   %s..%s  HEAD -> %s (dry run)\n" % (
            OLD7, HEAD7, BRANCH)
        pushes = [
            ("git push origin --tags", ""),
            ("git push --delete origin stale-branch",
             "To https://github.com/shivinate7/claude-settings.git\n - [deleted]         stale-branch\n"),
            ("git push --dry-run origin %s" % BRANCH, dry_run),
        ]
        fixture_ = answers(prs=[pr_entry()], runs=[PENDING])
        for command, output in pushes:
            with self.subTest(command=command):
                # Scope first: the guard reads the turn as a landing, so a report-less reply is blocked.
                decision, _, _ = self.stop(turn(NO_REPORT, bash(command, output)), fixture_)
                self.assertEqual(decision, "block", "a report-less turn with %r was not blocked" % command)
                decision, reason, calls = self.stop(turn(REPORT, bash(command, output)), fixture_)
                self.assertIsNone(decision, "%r was blocked for CI: %s" % (command, reason))
                self.assertEqual(calls, [], "%r read gh: %s" % (command, calls))

    def test_commit_turn_makes_no_gh_call(self):
        step = bash("git commit -m x", "[push-report-checks 1a2b3c4] x")
        fixture_ = answers(prs=[pr_entry()], runs=[PENDING])
        decision, _, _ = self.stop(turn(NO_REPORT, step), fixture_)
        self.assertEqual(decision, "block", "a report-less commit turn was not blocked (scope check)")
        decision, reason, calls = self.stop(turn(REPORT, step), fixture_)
        self.assertIsNone(decision, "a commit turn was blocked: %s" % reason)
        self.assertEqual(calls, [], "a commit turn read gh: %s" % calls)

    def test_turn_without_a_landing_makes_no_gh_call(self):
        step = bash("ls -la", "total 0")
        decision, reason, calls = self.stop(turn(REPORT, step), answers(prs=[pr_entry()], runs=[PENDING]))
        self.assertIsNone(decision, "a turn with no landing was blocked: %s" % reason)
        self.assertEqual(calls, [], "a turn with no landing read gh: %s" % calls)

    def test_stop_hook_active_makes_no_gh_call(self):
        steps = push(push_out(HEAD7))
        decision, _, _ = self.stop(turn(NO_REPORT, steps), answers(prs=[pr_entry()], runs=[PENDING]))
        self.assertEqual(decision, "block", "a report-less push turn was not blocked (scope check)")
        decision, reason, calls = self.stop(turn(REPORT, steps), answers(prs=[pr_entry()], runs=[PENDING]),
                                            stop_active=True)
        self.assertIsNone(decision, "a stop_hook_active Stop was blocked: %s" % reason)
        self.assertEqual(calls, [], "a stop_hook_active Stop read gh: %s" % calls)

    def test_two_pushes_never_read_the_older_head(self):
        steps = [push(push_out(MID7, old=OLD7), use_id="tu_1"), push(push_out(HEAD7, old=MID7), use_id="tu_2")]
        decision, _, _ = self.stop(turn(NO_REPORT, *steps), answers(prs=[pr_entry()], runs=[PENDING, PENDING_MID]))
        self.assertEqual(decision, "block", "a report-less two-push turn was not blocked (scope check)")
        decision, reason, calls = self.stop(turn(RUNNING, *steps),
                                            answers(prs=[pr_entry()], runs=[PENDING, PENDING_MID]))
        self.assertIsNone(decision, "a two-push turn whose report names the newest head as running was blocked: "
                          + reason)
        older = [c for c in calls if any(MID in a or MID7 in a for a in c)]
        self.assertEqual(older, [], "the guard read the older head of the turn: %s" % older)

    def test_turn_with_no_push_gives_no_push_ci_note_with_a_module_unloadable(self):
        # The note must not fire on every turn while a module is unloadable, only on a push turn.
        step = bash("ls -la", "total 0")
        fixture_ = answers(prs=[pr_entry()], runs=[PENDING])
        for module in ("ci_wake", "guard"):
            with self.subTest(module=module):
                decision, note = self.stop_note(turn(REPORT, step), fixture_, block=(module,))
                self.assertIsNone(decision, "a turn with no push was blocked with %s unloadable: %s" % (module, note))
                self.assertNotIn(PUSH_UNKNOWN_NOTE, note,
                                 "a turn with no push read a push-CI UNKNOWN note with %s unloadable" % module)

    # Cost: the call log counts the gh processes a push turn starts.

    def test_push_turn_reads_at_most_two_gh_calls_per_head(self):
        decision, reason, calls = self.stop(turn(REPORT, push(push_out(HEAD7))),
                                            answers(prs=[pr_entry()], runs=[PENDING]))
        self.assertGreaterEqual(len(calls), 1, "a push with a pending run read no CI: %s" % calls)
        self.assertLessEqual(len(calls), 2, "a push read more than two gh calls for its head: %s" % calls)

    def test_push_turn_with_no_run_listed_reads_three_gh_calls_for_its_head(self):
        # The record's Cost line: the PR read, the run list (empty here), then the workflow list that decides between
        # none and running. Three gh processes is the most a head reads.
        decision, reason, calls = self.stop(turn(REPORT, push(push_out(HEAD7))),
                                            answers(prs=[pr_entry()], runs=[]))
        self.assertEqual(decision, "block", "a ready PR with no run listed passed with no CI line (scope check)")
        self.assertIn("CI running on " + HEAD7, reason, "a ready PR with no run listed is not named running: " + reason)
        self.assertEqual(len(calls), 3, "a push with no run listed started %d gh processes for its head, not the "
                         "record's 3: %s" % (len(calls), calls))
        self.assertEqual([call[:2] for call in calls[1:]], [["run", "list"], ["workflow", "list"]],
                         "the reads after the PR read are not the run list, then the workflow list: %s" % calls)

    def bare_push_git_reads(self, folder, fixture_, command="git push origin %s" % FEAT):
        """-> (states, git calls) of a push with no ref line, `command` (default `git push origin feat`), read in
        process by report_guard.push_ci_states. The git stand-in leads PATH, so each git process the read starts is
        one log line."""
        bin_dir, log = git_stand_in(folder)
        fixture_path = os.path.join(folder, "fixture.json")
        with open(fixture_path, "w", encoding="utf-8") as f:
            json.dump(fixture_, f)
        env = {"PATH": os.pathsep.join((bin_dir, os.environ["PATH"])), "GH_STUB_FIXTURE": fixture_path,
               "GH_STUB_LOG": os.path.join(folder, "gh.log")}
        records = turn(REPORT, push("", command=command))[1:]
        budget = ci_wake.Budget(total=20, per_read=8, clock=StepClock([0.0]))  # a fixed clock: no read runs out
        with mock.patch.dict(os.environ, env):
            states = report_guard.push_ci_states(records, {"cwd": folder}, budget=budget)
        return states, git_calls(log)

    @unittest.skipIf(os.name == "nt", "the git stand-in is a POSIX launcher; no Windows run is made here")
    def test_bare_name_push_reads_git_within_the_cost_bound(self):
        # The cost line (decision push-report-names-ci): one git process when the remote-tracking ref names the head,
        # and at most 3 per name otherwise (the tag, the local branch, the remote-tracking ref). The first row pins the
        # one-process path. The other two rows pin the three-process bound.
        cases = (
            ("the remote-tracking ref names the head", 1, lambda folder: git_commit(folder, remote_branch=FEAT),
             lambda head: [head[:7]]),
            ("a local branch with no remote-tracking ref", 3,
             lambda folder: git_commit(folder, remote_branch=None, on_branch=FEAT), lambda head: [head[:7]]),
            ("no ref of the name", 3, lambda folder: git_commit(folder, remote_branch=None), lambda head: []),
        )
        for label, bound, setup, names_of in cases:
            with self.subTest(case=label):
                folder = self.case_folder()
                head = setup(folder)
                fixture_ = answers(prs=[pr_entry(branch=FEAT, sha=head)],
                                   runs=[run_entry(None, sha=head, status="in_progress")])
                states, calls = self.bare_push_git_reads(folder, fixture_)
                self.assertEqual([name for name, _, _ in states], names_of(head),
                                 "scope: the push did not name what %s names: %s" % (label, states))
                self.assertGreaterEqual(len(calls), 1, "scope: the git stand-in counted no process for %s" % label)
                self.assertLessEqual(len(calls), bound, "a bare-name push, %s, started %d git processes, past the cost "
                                     "bound of %d: %s" % (label, len(calls), bound, calls))

    @unittest.skipIf(os.name == "nt", "the git stand-in is a POSIX launcher; no Windows run is made here")
    def test_head_refspec_and_bare_push_start_one_git_process_for_the_branch_and_one_for_the_ref(self):
        # The record's Cost line: a `HEAD` refspec or a push with no refspec reads the checked-out branch, one git
        # process more, then its remote-tracking ref names the head, one more: 2 in all. A `HEAD:name` push names its
        # branch, so it starts only the ref read: 1.
        cases = (("git push origin HEAD", 2), ("git push", 2), ("git push origin HEAD:%s" % BRANCH, 1))
        for command, count in cases:
            with self.subTest(command=command):
                folder = self.case_folder()
                head = git_commit(folder, remote_branch=BRANCH, on_branch=BRANCH)
                fixture_ = answers(prs=[pr_entry(branch=BRANCH, sha=head)],
                                   runs=[run_entry(None, sha=head, status="in_progress")])
                states, calls = self.bare_push_git_reads(folder, fixture_, command=command)
                self.assertEqual([name for name, _, _ in states], [head[:7]],
                                 "scope: %r did not name the checked-out branch's head: %s" % (command, states))
                self.assertEqual(len(calls), count, "%r started %d git processes, not the record's %d: %s"
                                 % (command, len(calls), count, calls))


class BudgetTests(unittest.TestCase):
    """The read budget of one Stop (ci_wake.Budget): the per-read cap and the spent total, on a fake clock.
    No real time passes. The gh reads run through the stand-in on PATH, with this case's fixture. It also holds the
    git read of a head (ci_wake.commit_of) that fails outright: git missing, or a timeout."""

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="budget-", dir=trg.RUN_FOLDER)
        self.log = os.path.join(self.folder, "gh.log")
        fixture_path = os.path.join(self.folder, "fixture.json")
        with open(fixture_path, "w", encoding="utf-8") as f:
            json.dump(answers(prs=[pr_entry()], runs=[PENDING]), f)
        patch = mock.patch.dict(os.environ, {"GH_STUB_FIXTURE": fixture_path, "GH_STUB_LOG": self.log})
        patch.start()
        self.addCleanup(patch.stop)

    def test_spent_total_reads_ci_unknown_with_no_gh_call(self):
        clock = StepClock([0.0, 25.0])  # the 20 s total is spent before any read
        budget = ci_wake.Budget(total=20, per_read=8, clock=clock)
        records = turn(REPORT, push(push_out(HEAD7)))[1:]
        states = report_guard.push_ci_states(records, {"cwd": self.folder}, budget=budget)
        self.assertEqual([(sha7, state) for sha7, state, _ in states], [(HEAD7, "unknown")],
                         "a spent budget did not read the pushed head as unknown: %s" % states)
        reason = report_guard.push_ci_problem(REPORT, states)
        self.assertIn("CI unknown on " + HEAD7, reason, "a spent budget is not named CI unknown")
        self.assertEqual(trg.GH_STUB.read_log(self.log), [], "a spent budget still read gh")

    def test_spent_budget_during_the_branch_read_is_unknown_not_a_silent_pass(self):
        hook = {"cwd": self.folder}
        with self.subTest(read="the branch's PR read, head named by the push output"):
            clock = StepClock([0.0, 25.0])  # the total is spent when the PR read asks for its timeout
            budget = ci_wake.Budget(total=20, per_read=8, clock=clock)
            records = turn(REPORT, push(push_out(HEAD7)))[1:]
            states = report_guard.push_ci_states(records, hook, budget=budget)
            reason = report_guard.push_ci_problem(REPORT, states)
            self.assertIn("CI unknown on " + HEAD7, reason,
                          "a budget spent during the branch's PR read was not named CI unknown: %s" % states)
        with self.subTest(read="the branch's remote-ref read, head not yet named"):
            clock = StepClock([0.0, 25.0])  # the total is spent when the remote-ref read asks for its timeout
            budget = ci_wake.Budget(total=20, per_read=8, clock=clock)
            records = turn(REPORT, push(""))[1:]  # no ref line in the output: the head is read from the ref
            try:
                states = report_guard.push_ci_states(records, hook, budget=budget)
            except Exception as exc:  # the Stop hook catches this and passes the turn
                self.fail("a budget spent during the branch's remote-ref read escaped the push check, which then "
                          "fails open and passes the turn: %s: %s" % (type(exc).__name__, exc))
            reason = report_guard.push_ci_problem(REPORT, states)
            self.assertIn("CI unknown", reason, "a budget spent during the remote-ref read passed with no CI line")
            self.assertIn("budget", reason,
                          "a budget spent during the remote-ref read is not reported as the budget: " + reason)
        with self.subTest(read="the branch read of a bare push, head not yet named"):
            clock = StepClock([0.0, 25.0])  # the total is spent when the branch read asks for its timeout
            budget = ci_wake.Budget(total=20, per_read=8, clock=clock)
            records = turn(REPORT, push("", command="git push"))[1:]
            states = report_guard.push_ci_states(records, hook, budget=budget)
            reason = report_guard.push_ci_problem(REPORT, states)
            self.assertIn("CI unknown on HEAD", reason,
                          "a budget spent during a bare push's branch read is not named CI unknown on HEAD: %s"
                          % states)
            self.assertIn("budget", reason,
                          "a budget spent during a bare push's branch read is not reported as the budget: " + reason)

    def test_every_gh_read_is_capped_at_the_per_read_timeout(self):
        clock = StepClock([0.0])
        budget = ci_wake.Budget(total=20, per_read=8, clock=clock)
        real_gh = ci_wake.gh
        timeouts = []

        def spy(args, cwd, timeout=ci_wake.READ_TIMEOUT):
            timeouts.append(timeout)
            return real_gh(args, cwd, timeout)

        with mock.patch.object(ci_wake, "gh", spy):
            state, _ = ci_wake.head_state(HEAD7, BRANCH, self.folder, budget)
        self.assertTrue(timeouts, "the head read made no gh call, so no timeout was checked")
        self.assertLessEqual(max(timeouts), 8,
                             "a gh read was given %s s, past the 8 s per-read cap" % max(timeouts))
        self.assertEqual(state, "pending", "the fixture's pending run did not read as pending")

    def failed_head_read_reason(self, failure):
        """The block reason of a push whose head the git read (commit_of) cannot name: `failure` is the patch that
        makes the read fail. The push has no ref line, so the head is read from its remote-tracking ref."""
        records = turn(REPORT, push("", command="git push origin HEAD:%s" % BRANCH))[1:]
        budget = ci_wake.Budget(total=20, per_read=8, clock=StepClock([0.0]))
        with failure:
            states = report_guard.push_ci_states(records, {"cwd": self.folder}, budget=budget)
        # Scope first: the push is read as one branch, unknown, with no head.
        self.assertEqual([(branch, state) for branch, state, _ in states], [(BRANCH, "unknown")],
                         "the push was not read as one unknown branch: %s" % states)
        return report_guard.push_ci_problem(REPORT, states)

    def failed_read_text(self, failure, ref):
        """The message the head read of `ref` raises under `failure`: the read's own text, which a reason must carry."""
        with failure:
            with self.assertRaises(ci_wake.Unknown) as raised:
                ci_wake.commit_read(ref, self.folder)
        return str(raised.exception)

    def assert_names_failed_read(self, reason, text):
        self.assertNotIn(UNNAMED_HEAD_TEXT, reason, "the failed head read is reported as the ref names no head, which "
                         "hides that the read failed: " + reason)
        self.assertIn("CI unknown on " + BRANCH, reason, "the push is not named unknown on %s: %s" % (BRANCH, reason))
        self.assertNotIn("budget", reason, "a failed head read is reported as the read budget, which was never spent: "
                         + reason)
        self.assertIn(text, reason, "the reason does not carry the head read's own message (%s): %s" % (text, reason))

    def test_missing_git_on_the_head_read_names_the_failed_read(self):
        ref = "refs/remotes/origin/%s" % BRANCH

        def failure():
            return mock.patch.object(ci_wake.shutil, "which", return_value=None)

        text = self.failed_read_text(failure(), ref)
        reason = self.failed_head_read_reason(failure())
        self.assert_names_failed_read(reason, text)

    def test_timed_out_head_read_names_the_failed_read(self):
        ref = "refs/remotes/origin/%s" % BRANCH

        def failure():
            return mock.patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired(["git", "rev-parse"], 8))

        text = self.failed_read_text(failure(), ref)
        reason = self.failed_head_read_reason(failure())
        self.assert_names_failed_read(reason, text)


if __name__ == "__main__":
    unittest.main()
