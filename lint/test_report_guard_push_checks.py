#!/usr/bin/env python3
"""Cases for the Stop-side CI check after a push (lint/report_guard.py; debt push-report-before-checks;
decision ci-wait-reads-run-status, section "A report after a push").

A turn that pushes a head holds its report until that head's CI is known. The report holds one line
that names the head, in the form the guard reads:
- `CI running on <sha7>` under Next, while a run is pending, or while a ready PR has no run yet.
- `CI red on <sha7>`, when a run ended red.
- `CI unknown on <sha7>`, when a read failed.
A green run, a draft PR, a branch with no PR, a repo with no workflows, a tag push, a delete and a dry run need no line. A Done
item may not claim a pending head.

Each case runs the real Stop hook as a subprocess. The gh stand-in leads its PATH (setUpModule of
lint/test_report_guard.py, which takes the stand-in's program from hooks/test_ci_wake.py) and answers
the fixture the case writes. No real gh runs, no network is reached and no clock is read. The budget
cases run in process with a fake clock.

Cost, proved by the stand-in's call log: a turn with no push, and a Stop with stop_hook_active, make no
gh call. A push reads at most 2 gh calls for its head: the PR read and the run list.

A red case fails on an assertion on the old code, where the guard blocks nothing. A control passes on
the old code and on the new.

Run it from the repository root:

    python3 lint/test_report_guard_push_checks.py -v
"""
import json
import os
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
DONE_CLAIMS_HEAD = "> **Done** BUILT %s\n> **Next** CI running on %s" % (HEAD7, HEAD7)


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


def git_commit(folder):
    """Make `folder` a git repo with one empty commit, and its remote-tracking ref for BRANCH at that commit.
    -> the full hash. Local git only."""
    env = dict(os.environ, **GIT_IDENTITY)

    def run_git(*args):
        return subprocess.run(["git", *args], cwd=folder, env=env, capture_output=True, text=True,
                              check=True, timeout=30).stdout.strip()

    run_git("init", "-q")
    run_git("commit", "-q", "--allow-empty", "-m", "x")
    head = run_git("rev-parse", "HEAD")
    run_git("update-ref", "refs/remotes/origin/" + BRANCH, head)
    return head


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

    def stop(self, records, answers_=None, stop_active=False, no_gh=False, folder=None, session_id=None):
        """Run the Stop hook over `records`, with the stand-in answering `answers_`. no_gh: the guard's PATH
        holds no gh at all. folder: the case's folder (its call log and fixture), new when None. session_id:
        the hook's session, which names the missing-report marker. -> (decision, reason, gh calls)."""
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
            done = trg.run_guard(trg.REPORT_GUARD, hook, env=trg.gh_env(fixture_path, log, path))
        except subprocess.TimeoutExpired:
            self.fail("the Stop hook ran past its timeout: a push turn reads CI once and returns")
        self.assertEqual(done.returncode, 0, "the Stop hook exited %d: %s" % (done.returncode, done.stderr[-300:]))
        decision, reason = block_of(done)
        return decision, reason, trg.GH_STUB.read_log(log)

    # Red: each case fails on an assertion on the old code.

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
        steps = bash("cd %s && git push origin HEAD:%s" % (other, BRANCH), "")
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

    # Green controls: each passes on the old code and on the new.

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

    # Cost: the call log counts the gh processes a push turn starts.

    def test_push_turn_reads_at_most_two_gh_calls_per_head(self):
        decision, reason, calls = self.stop(turn(REPORT, push(push_out(HEAD7))),
                                            answers(prs=[pr_entry()], runs=[PENDING]))
        self.assertGreaterEqual(len(calls), 1, "a push with a pending run read no CI: %s" % calls)
        self.assertLessEqual(len(calls), 2, "a push read more than two gh calls for its head: %s" % calls)


class BudgetTests(unittest.TestCase):
    """The read budget of one Stop (ci_wake.Budget): the per-read cap and the spent total, on a fake clock.
    No real time passes. The gh reads run through the stand-in on PATH, with this case's fixture."""

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


if __name__ == "__main__":
    unittest.main()
