#!/usr/bin/env python3
"""Stop report guard: which calls land a turn, beyond git commit, push and merge.

A turn that lands a commit must end with the report (report_guard.turn_landed). These cases
pin the calls that land and must be blocked: the GitHub MCP tools that write a commit, the git
calls that make one (revert, cherry-pick, and their resume forms), and the gh calls that merge
or open a PR. The controls pin the calls that land nothing, so a fix cannot widen the match by
name alone. The transcript helpers and the run isolation come from lint/test_report_guard.py.

    python3 lint/test_report_guard_landing.py -v
"""
import ast
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_report_guard as trg  # noqa: E402  the transcript helpers, the guard path and the run isolation (one home)

sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
import guard_merge  # noqa: E402  MERGE_TOOLS and CREATE_PR_TOOL, the guard's own names (one home)
import report_guard  # noqa: E402  LANDING_TOOLS, the report's read of the landing names
import shared_names  # noqa: E402  the one home of the landing tool names (hooks/shared_names.py)

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


class LandingToolHomeTests(unittest.TestCase):
    # The landing tool names have one home, hooks/shared_names.py (CLAUDE.md building-one-home-per-capability).
    # These cases read the constants, never a copied list (building-allow-list-is-the-constant).

    def test_lh_red_landing_tools_are_the_shared_names_constant(self):
        # Catches: report_guard keeps its own literal LANDING_TOOLS, so a landing tool named in shared_names is missed here.
        self.assertTrue(hasattr(shared_names, "LANDING_TOOLS"),
                        "LANDING_TOOLS has no home in hooks/shared_names.py, so report_guard keeps its own set")
        self.assertIs(report_guard.LANDING_TOOLS, shared_names.LANDING_TOOLS,
                      "report_guard.LANDING_TOOLS is a copy, not the shared_names constant")

    def test_lh_red_report_guard_keeps_no_mcp_name_literal(self):
        # Catches: report_guard.py keeps its own literal MCP tool names, so a name added to shared_names is missed here.
        # Scope first: the file must still name LANDING_TOOLS, by assignment or by import, or an emptied file would pass.
        with open(os.path.join(HERE, "report_guard.py"), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        named = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                named.add(node.id)
            elif isinstance(node, ast.alias):
                named.add(node.asname or node.name)
        self.assertIn("LANDING_TOOLS", named, "scope: report_guard.py no longer names LANDING_TOOLS")
        hits = sorted({node.value for node in ast.walk(tree)
                       if isinstance(node, ast.Constant) and isinstance(node.value, str)
                       and node.value.startswith("mcp__")})
        self.assertEqual(hits, [], "report_guard.py keeps its own MCP tool names, not the shared_names constant: %s"
                         % ", ".join(hits))

    def stop_in_copy(self, shared_names_src):
        """Run the Stop hook of a copy of lint/report_guard.py on a stub turn that lands nothing. The copy of lint/
        sits in this run's folder. A None source leaves no hooks/ folder beside it; otherwise hooks/shared_names.py
        holds the source."""
        root = tempfile.mkdtemp(dir=RUN_FOLDER)
        shutil.copytree(HERE, os.path.join(root, "lint"), ignore=shutil.ignore_patterns("__pycache__"))
        if shared_names_src is not None:
            os.makedirs(os.path.join(root, "hooks"))
            with open(os.path.join(root, "hooks", "shared_names.py"), "w", encoding="utf-8") as f:
                f.write(shared_names_src)
        records = [trg.human("land it"), trg.assistant_text("Nothing landed.")]
        path = trg.write_transcript(records, tempfile.mkdtemp(dir=RUN_FOLDER))
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": False}
        return trg.run_guard(os.path.join(root, "lint", "report_guard.py"), hook)

    def test_lh_red_no_hooks_beside_the_copy_fails_open(self):
        # Catches: a lint/ with no hooks/ beside it crashes the Stop hook at its import. The hook must fail open,
        # because an install lands lint/ before hooks/.
        run = self.stop_in_copy(None)
        self.assertEqual(run.returncode, 0,
                         "no hooks/ beside lint/: the Stop hook exited %d, not 0: %s"
                         % (run.returncode, run.stderr[-300:]))

    def test_lh_red_shared_names_without_landing_tools_fails_open(self):
        # Catches: an older hooks/shared_names.py with no LANDING_TOOLS crashes the Stop hook at its import.
        # The hook must fail open, as it does when hooks/ is missing.
        run = self.stop_in_copy("STATE_DIR_NAME = 'state'\n")
        self.assertEqual(run.returncode, 0,
                         "shared_names without LANDING_TOOLS: the Stop hook exited %d, not 0: %s"
                         % (run.returncode, run.stderr[-300:]))

    def test_lh_green_guard_merge_and_create_names_are_landing_tools(self):
        # Allow control: every name the guard merges through, or opens a pull request through, is a landing tool.
        for name in tuple(guard_merge.MERGE_TOOLS) + (guard_merge.CREATE_PR_TOOL,):
            with self.subTest(tool=name):
                self.assertIn(name, report_guard.LANDING_TOOLS)


if __name__ == "__main__":
    unittest.main()
