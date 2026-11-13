#!/usr/bin/env python3
"""Stop report guard: which calls land a turn, beyond git commit, push and merge.

A turn that lands a commit must end with the report (report_guard.turn_landed). These cases
pin the calls that land and must be blocked: the GitHub MCP tools that write a commit, the git
calls that make one (revert, cherry-pick, and their resume forms), and the gh calls that merge
or open a PR. The controls pin the calls that land nothing, so a fix cannot widen the match by
name alone. The transcript helpers and the run isolation come from lint/test_report_guard.py.

    python3 lint/test_report_guard_landing.py -v
"""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_report_guard as trg  # noqa: E402  the transcript helpers, the guard path and the run isolation (one home)

RUN_FOLDER = trg.RUN_FOLDER  # this run's one folder (test-temp-standard); every case takes its folder from it
SHA = "1a2b3c4"
LANDING_REPLY = "Landed it."  # a reply with no report, on a turn that lands
QUIET_REPLY = "Nothing landed."  # a reply on a turn that lands nothing
# A call that lands on main, so the guard blocks it there. A control runs it first: if the witness does
# not block, the fixture never reached the guard and an empty output below proves nothing.
WITNESS_BASH = ("Bash", {"command": "git commit -m x"})
WITNESS_MCP = ("mcp__github__create_pull_request", {"title": "x"})


def setUpModule():
    trg.setUpModule()


def tearDownModule():
    trg.tearDownModule()


class LandingToolTests(unittest.TestCase):
    def run_turn(self, calls, reply):
        """Run the Stop guard on one turn. `calls` is a list of (tool name, input) pairs, each a tool
        call followed by its result, in order. Returns the finished process."""
        records = [trg.human("land it")]
        for n, (name, tool_input) in enumerate(calls):
            records.append(trg.tool_use_msg(name, tool_input))
            records.append(trg.tool_result_msg("tu_%d" % n))
        records.append(trg.assistant_text(reply))
        path = trg.write_transcript(records, tempfile.mkdtemp(dir=RUN_FOLDER))
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": False}
        return trg.run_guard(trg.REPORT_GUARD, hook)

    def decision_of(self, run, label):
        self.assertEqual(run.returncode, 0, "the guard crashed on %s: %s" % (label, run.stderr[-300:]))
        return json.loads(run.stdout).get("decision") if run.stdout.strip() else None

    def assert_scope(self, witness):
        """Assert the scope before the subject: the witness, a real landing, must block in this fixture."""
        run = self.run_turn([witness], LANDING_REPLY)
        self.assertEqual(self.decision_of(run, witness[0]), "block",
                         "scope: the witness %s did not block, so the fixture does not reach the guard" % witness[0])

    def assert_blocks(self, calls, label):
        run = self.run_turn(calls, LANDING_REPLY)
        self.assertEqual(self.decision_of(run, label), "block",
                         "%r landed with no report, and the guard did not block it" % label)

    def assert_quiet(self, calls, label):
        run = self.run_turn(calls, QUIET_REPLY)
        self.assertEqual(run.returncode, 0, "the guard crashed on %r: %s" % (label, run.stderr[-300:]))
        self.assertEqual(run.stdout.strip(), "", "%r landed nothing, yet the guard wrote output" % label)

    def test_lt_red_github_write_tools_that_commit_block(self):
        # Catches: a GitHub MCP write that adds a commit to a branch is not a landing, so its turn passes.
        for tool in ("mcp__github__delete_file", "mcp__github__update_pull_request_branch"):
            with self.subTest(tool=tool):
                self.assert_blocks([(tool, {})], tool)

    def test_lt_red_git_revert_and_cherry_pick_block(self):
        # Catches: git revert and git cherry-pick make a commit, so a turn that runs them lands and must report.
        for command in ("git revert %s" % SHA, "git cherry-pick %s" % SHA, "git -C /x revert %s" % SHA):
            with self.subTest(command=command):
                self.assert_blocks([("Bash", {"command": command})], command)

    def test_lt_red_resumed_revert_or_cherry_pick_block(self):
        # Catches: --continue commits the resolved pick. --skip resumes the sequence, and it commits the
        # rest of the sequence (measured for cherry-pick and for revert in a scratch repo), so both land.
        for command in ("git revert --continue", "git cherry-pick --continue",
                        "git revert --skip", "git cherry-pick --skip"):
            with self.subTest(command=command):
                self.assert_blocks([("Bash", {"command": command})], command)

    def test_lt_red_gh_pr_writes_block(self):
        # Catches: gh pr merge and gh pr create write to GitHub, and a gh call after `cd x &&` runs the same way.
        for command in ("gh pr merge 12 --squash", "gh pr create --title t --body b",
                        "cd x && gh pr merge 12 --squash"):
            with self.subTest(command=command):
                self.assert_blocks([("Bash", {"command": command})], command)

    def test_lt_red_landing_after_quoted_text_or_a_comment_still_blocks(self):
        # Catches: a comment opener inside quotes, or a lone quote in a comment, hides the landing after it.
        commands = [
            'echo "a # b" && gh pr merge 12 --squash',
            'echo "# note" && git revert %s' % SHA,
            'echo "don\'t" && gh pr merge 12 --squash',
            "# don't\ngh pr merge 12 --squash",
            "# don't\ngit cherry-pick %s" % SHA,
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assert_blocks([("Bash", {"command": command})], command)

    def test_lt_red_landing_after_many_reads_blocks(self):
        # Catches: a landing late in a long turn, after many read-only calls, passes with no report.
        calls = [("Bash", {"command": "ls %d" % n}) for n in range(60)]
        calls.append(("Bash", {"command": "git revert %s" % SHA}))
        self.assert_blocks(calls, "git revert after 60 reads")

    def test_lt_green_git_calls_that_land_nothing_pass(self):
        self.assert_scope(WITNESS_BASH)
        # Catches: --abort and --quit only clear a sequence, and -n or --no-commit stops before the commit.
        commands = [
            "git revert --abort",
            "git revert --quit",
            "git cherry-pick --abort",
            "git cherry-pick --quit",
            "git revert -n %s" % SHA,
            "git revert --no-commit %s" % SHA,
            "git cherry-pick -n %s" % SHA,
            "git cherry-pick --no-commit %s" % SHA,
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assert_quiet([("Bash", {"command": command})], command)

    def test_lt_green_gh_reads_and_help_pass(self):
        self.assert_scope(WITNESS_BASH)
        # Catches: a gh pr call that only reads, or only prints help, is read as a merge or a PR write.
        for command in ("gh pr view 12", "gh pr list", "gh pr merge --help"):
            with self.subTest(command=command):
                self.assert_quiet([("Bash", {"command": command})], command)

    def test_lt_green_quoted_comment_heredoc_and_empty_text_pass(self):
        self.assert_scope(WITNESS_BASH)
        commands = [
            # Catches: a quoted gh call is text, not a call.
            'echo "gh pr merge 12"',
            # Catches: a quoted gh call on its own line of a multi-line string is text, not a call.
            'echo "line one\ngh pr merge 12 --squash\nline three"',
            # Catches: a heredoc body that names a git revert is written, not run.
            "cat <<'EOF' > notes.txt\ngit revert x\nEOF",
            # Catches: a heredoc body that names a gh merge is written, not run.
            "cat <<'EOF' > notes.txt\ngh pr merge 12 --squash\nEOF",
            # Catches: a comment line that names a git revert is read as a call.
            "# git revert x would undo it\nls",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assert_quiet([("Bash", {"command": command})], command)
        # Catches: an empty command is read as a landing, or crashes the guard.
        with self.subTest(command="empty"):
            self.assert_quiet([("Bash", {"command": ""})], "an empty command")

    def test_lt_green_github_read_and_metadata_tools_pass(self):
        self.assert_scope(WITNESS_MCP)
        # Catches: a GitHub tool that edits PR metadata or reads a PR is matched by its name prefix.
        for tool in ("mcp__github__update_pull_request", "mcp__github__pull_request_read"):
            with self.subTest(tool=tool):
                self.assert_quiet([(tool, {})], tool)

    def test_lt_red_gh_root_flag_forms_block(self):
        # Catches: a root flag before the verb (-R, --repo=, --repo, or GH_REPO= ahead of gh) hides
        # pr merge or pr create from the gh guard, so the turn passes with no report.
        commands = [
            "gh -R o/r pr merge 12",
            "gh --repo=o/r pr merge 12",
            "gh --repo o/r pr create --fill",
            "GH_REPO=o/r gh -R o/r pr merge 12",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assert_blocks([("Bash", {"command": command})], command)

    def test_lt_red_gh_update_branch_and_dry_run_create_block(self):
        # Catches: gh pr update-branch merges the base into the PR branch, which is a commit. A dry-run
        # create may still push the branch, so it lands too.
        for command in ("gh pr update-branch 12", "gh pr create --dry-run --fill"):
            with self.subTest(command=command):
                self.assert_blocks([("Bash", {"command": command})], command)

    def test_lt_red_enable_auto_merge_tool_blocks(self):
        # Catches: enable_pr_auto_merge queues the merge, so a turn that calls it lands and must report.
        tool = "mcp__github__enable_pr_auto_merge"
        self.assert_blocks([(tool, {})], tool)

    def test_lt_green_gh_disable_web_and_help_flags_pass(self):
        self.assert_scope(WITNESS_BASH)
        # Catches: --disable-auto turns auto-merge off, and --web opens a browser; neither merges or creates.
        # Catches: -h on revert or cherry-pick prints help, as --help does, and makes no commit.
        commands = [
            "gh pr merge 12 --disable-auto",
            "gh pr create --web",
            "gh pr create -h",
            "gh pr create --help",
            "git revert -h",
            "git cherry-pick -h",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assert_quiet([("Bash", {"command": command})], command)

    def test_lt_red_gh_api_merge_calls_block(self):
        # Catches: a merge made through the REST API lands a commit, but the guard reads only gh pr verbs, so the
        # turn passes with no report. A PUT to a pull's merge route merges it. A POST to the merges route writes a
        # merge commit, and gh sends a POST whenever -f fields are given, as in the last command.
        self.assert_scope(WITNESS_BASH)
        commands = [
            "gh api -X PUT repos/o/r/pulls/12/merge",
            "gh api --method PUT repos/o/r/pulls/12/merge -f merge_method=squash",
            "gh api -X POST repos/o/r/merges -f base=main -f head=topic",
            "gh api repos/o/r/merges -f base=main -f head=topic",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assert_blocks([("Bash", {"command": command})], command)

    def test_lt_green_gh_api_reads_and_other_writes_pass(self):
        self.assert_scope(WITNESS_BASH)
        # Catches: a gh api read of a pull, or of its merge status, is taken for a merge, or a write to another
        # route is taken for one. Only a PUT to a pull's merge route and a POST to the merges route land.
        commands = [
            "gh api repos/o/r/pulls/12",
            "gh api -X GET repos/o/r/pulls/12/merge",
            "gh api -X PUT repos/o/r/issues/12/labels -f labels[]=x",
            "gh api -X POST repos/o/r/issues/12/comments -f body=x",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assert_quiet([("Bash", {"command": command})], command)

    def test_lt_red_gh_api_put_to_pull_merge_with_fields_still_blocks(self):
        # Catches: the control for the POST case below. GitHub merges a pull by PUT, and -f fields do not change
        # that method, so a PUT to a pull's merge route with fields is still a merge and still lands.
        self.assert_scope(WITNESS_BASH)
        self.assert_blocks([("Bash", {"command": "gh api -X PUT repos/o/r/pulls/12/merge -f merge_method=squash"})],
                           "gh api -X PUT pulls/12/merge with fields")

    def test_lt_green_gh_api_post_to_pull_merge_passes(self):
        # Catches: a POST to a pull's merge route is no merge, since GitHub merges a pull by PUT only. gh sends a
        # POST implicitly once -f fields are given, so the implicit form and the explicit form are both quiet.
        self.assert_scope(WITNESS_BASH)
        commands = [
            "gh api repos/o/r/pulls/12/merge -f merge_method=squash",
            "gh api -X POST repos/o/r/pulls/12/merge -f merge_method=squash",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assert_quiet([("Bash", {"command": command})], command)

    def test_lt_green_gh_api_help_with_a_merge_route_passes(self):
        # Catches: gh api with --help prints help and makes no request, so a merge route named beside --help is no
        # merge, and it lands nothing whatever the method.
        self.assert_scope(WITNESS_BASH)
        commands = [
            "gh api -X PUT repos/o/r/pulls/12/merge --help",
            "gh api -X POST repos/o/r/merges -f base=main -f head=topic --help",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assert_quiet([("Bash", {"command": command})], command)


    def test_lt_green_api_request_blob_copy_of_a_landing_call_passes(self):
        # Catches: a resumed session's transcript holds `api-request-blob` records, copies of earlier calls with no
        # timestamp. Read as this turn's calls, a copy of an old `git commit` lands a turn that ran nothing, so a quiet
        # turn is blocked for a report. Only a real assistant record is a call.
        self.assert_scope(WITNESS_BASH)
        blob = {"type": "api-request-blob", "hash": "h1", "sessionId": "s1",
                "message": {"role": "assistant", "content": [
                    {"type": "tool_use", "id": "old1", "name": "Bash", "input": {"command": "git commit -m x"}}]}}
        records = [trg.human("is there any reason not to archive"), blob, trg.assistant_text(QUIET_REPLY)]
        path = trg.write_transcript(records, tempfile.mkdtemp(dir=RUN_FOLDER))
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": False}
        run = trg.run_guard(trg.REPORT_GUARD, hook)
        self.assertEqual(run.returncode, 0, "the guard crashed: %s" % run.stderr[-300:])
        self.assertEqual(run.stdout.strip(), "", "a blob copy of an old commit landed a turn that ran nothing")


if __name__ == "__main__":
    unittest.main()
