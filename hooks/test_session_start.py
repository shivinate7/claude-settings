#!/usr/bin/env python3
"""Session-start notice for agent worktrees. hooks/session_start.sh prints
one notice when more than 50 `.claude/worktrees/agent-*` worktrees exist. At exactly 50 it prints
none. Real git repo and real `git worktree add`. The hook runs as the harness runs it: `sh
session_start.sh` with the session payload on stdin. Stdlib only. Exit 0 on PASS, 1 on FAIL.

    python hooks/test_session_start.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "session_start.sh")
sys.path.insert(0, os.path.join(HERE, "..", "lint"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
RUN_FOLDER = _test_temp.run_folder()
SESSION = "session-start-cases"  # the session id every run_hook payload names
VCS = "g" + "it"  # assembled so this file cannot itself look like the command it tests
IDENT = ["-c", "user.email=session-start-cases@example.invalid", "-c", "user.name=session-start-cases"]
LIMIT = 50  # the notice starts above this many agent worktrees
NOTICE = re.compile(r"agent[ -]worktree", re.IGNORECASE)
# The one printed line whose text starts "session tier: ", quoted in the hook's printf call.
TIER_PRINTF = re.compile(r"'(session tier: .*)'[ \t]*$", re.MULTILINE)
UNKNOWN_LINE = "repo caution: unknown, the level could not be read"  # the hook's line when the caution level is unread


def hook_tier_line():
    """The tier line's text as the hook file holds it, so a wording change in the hook edits no test."""
    with open(HOOK, encoding="utf-8") as handle:
        found = TIER_PRINTF.findall(handle.read())
    if len(found) != 1:
        sys.exit("fixture setup failed: expected one session tier line in %s, found %d" % (HOOK, len(found)))
    return found[0]


def sentences(line):
    """The line's sentences, cut at each ". " as merge_role_sentence cuts."""
    return re.split(r"(?<=\.) ", line)


def merge_role_sentence(line):
    """The sentence of the tier line that holds `merge --role`: from the ". " before it to the ". " after it, or to the line's ends."""
    at = line.index("merge --role")
    start = line.rfind(". ", 0, at)
    end = line.find(". ", at)
    return line[0 if start < 0 else start + 2:len(line) if end < 0 else end + 1]


def sh_exe():
    """Git's own sh.exe on Windows, by full path. A bare `sh` can resolve to the WSL stub."""
    if os.name != "nt":
        return shutil.which("sh") or "sh"
    for var in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
        candidate = os.path.join(os.environ.get(var) or "", "Git", "bin", "sh.exe")
        if os.path.isfile(candidate):
            return candidate
    sys.exit("fixture setup failed: Git sh.exe not found")


def vcs(where, *args):
    answer = subprocess.run([VCS, "-C", where, *IDENT, *args], capture_output=True, text=True,
                            timeout=60)
    if answer.returncode != 0:
        sys.exit("fixture setup failed: %s %s: %s" % (VCS, " ".join(args), answer.stderr.strip()))
    return answer


def make_stub(folder, name, body="exit 0\n"):
    """An executable sh stub named `name` in `folder`, running `body`. Returns its path."""
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("#!/bin/sh\n" + body)
    os.chmod(path, 0o755)
    return path


class SessionStartAgentWorktreeNoticeTests(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="session_start_cases_", dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.root, True)
        self.config = os.path.join(self.root, "cfg")
        os.makedirs(self.config)
        # Names the SessionEnd hook, so the disarmed notice stays silent in every run.
        with open(os.path.join(self.config, "settings.json"), "w", encoding="utf-8") as handle:
            handle.write('{"hooks": {"SessionEnd": []}}\n')
        self.primary = os.path.join(self.root, "repo")
        os.makedirs(self.primary)
        vcs(self.primary, "init", "-q", "-b", "main", ".")
        # Ignores the worktree folder, so the dirty count in the hook's first line never moves.
        with open(os.path.join(self.primary, ".gitignore"), "w", encoding="utf-8") as handle:
            handle.write(".claude/\n")
        with open(os.path.join(self.primary, "f.txt"), "w", encoding="utf-8") as handle:
            handle.write("base\n")
        vcs(self.primary, "add", "-A")
        vcs(self.primary, "commit", "-q", "-m", "first")
        self.made = 0

    def add_agent_worktrees(self, count):
        for _ in range(count):
            self.made += 1
            path = os.path.join(self.primary, ".claude", "worktrees", "agent-s%03d" % self.made)
            vcs(self.primary, "worktree", "add", "-q", "--detach", "--no-checkout", path, "HEAD")

    def run_hook(self, remote=None, fetch_timeout="30", session_cwd=None, source=None, compact=False,
                 remote_session_id=None, extra_env=None):
        """The hook's stdout lines. Its stderr lands in self.last_stderr.

        remote: the CLAUDE_CODE_REMOTE value, or None to unset it as a non-cloud runner does.
        remote_session_id: the CLAUDE_CODE_REMOTE_SESSION_ID value, "" for an empty one, or None to unset it.
        session_cwd: the session's cwd, in the payload and as the process cwd; None means the primary checkout.
        source: the payload's "source" (startup, resume, ...), or None to send none.
        compact: send the payload with no spaces after its separators, the way the hook's sed must also read it.
        extra_env: variables set on the hook's environment last, for the cases that name HOME or CLAUDE_ENV_FILE.
        """
        where = self.primary if session_cwd is None else session_cwd
        # Forward slashes: the hook reads "cwd" with sed, and a doubled backslash is not a path.
        body = {"cwd": where.replace("\\", "/"), "session_id": SESSION}
        if source is not None:
            body["source"] = source
        payload = json.dumps(body, separators=(",", ":") if compact else None)
        env = dict(os.environ, CLAUDE_CONFIG_DIR=self.config, CLAUDE_SETTINGS_FETCH_TIMEOUT=fetch_timeout)
        # The test runner may itself be a cloud session, so each run sets the variable it means.
        env.pop("CLAUDE_CODE_REMOTE", None)
        env.pop("CLAUDE_CODE_REMOTE_SESSION_ID", None)
        if remote is not None:
            env["CLAUDE_CODE_REMOTE"] = remote
        if remote_session_id is not None:
            env["CLAUDE_CODE_REMOTE_SESSION_ID"] = remote_session_id
        # The session's env file is named only by the cases that mean it: a runner inside a Claude session has one.
        env.pop("CLAUDE_ENV_FILE", None)
        env.update(extra_env or {})
        answer = subprocess.run([sh_exe(), HOOK], input=payload, capture_output=True, text=True,
                                env=env, cwd=where, timeout=120)
        self.last_stderr = answer.stderr
        self.assertEqual(answer.returncode, 0, "the hook exited %d" % answer.returncode)
        return answer.stdout.splitlines()

    def test_no_notice_at_fifty_and_one_notice_at_fifty_one(self):
        baseline = self.run_hook()
        # Control: the hook really ran. Without its first line, "no notice" would pass vacuously.
        self.assertTrue(any(line.startswith("checkout ") for line in baseline),
                        "the hook printed no checkout line: %r" % baseline)
        self.add_agent_worktrees(LIMIT)
        at_limit = self.run_hook()
        with self.subTest(agent_worktrees=LIMIT):
            extra = [line for line in at_limit if line not in baseline]
            self.assertEqual(extra, [], "a notice printed at %d agent worktrees" % LIMIT)
        self.add_agent_worktrees(1)
        above = self.run_hook()
        extra = [line for line in above if line not in baseline]
        with self.subTest(agent_worktrees=LIMIT + 1):
            self.assertEqual(len(extra), 1, "expected one notice at %d agent worktrees, got %r"
                             % (LIMIT + 1, extra))
            self.assertIn(str(LIMIT + 1), extra[0], "the notice does not state the count: %r" % extra[0])
            self.assertRegex(extra[0], NOTICE, "the notice does not name agent worktrees: %r" % extra[0])

class SessionStartCautionTests(SessionStartAgentWorktreeNoticeTests):
    """The repo's caution level prints once at session start (decision repo-kind-and-caution)."""

    def point_at(self, layout_json=None):
        """A pointer dir with lint/layout.py and layout.json, named by the config's CLAUDE.md."""
        pointer = os.path.join(self.root, "pointer")
        os.makedirs(os.path.join(pointer, "lint"))
        for name in ("layout.py", "layout.json"):
            shutil.copy(os.path.join(HERE, "..", "lint", name), os.path.join(pointer, "lint", name))
        if layout_json is not None:
            with open(os.path.join(pointer, "lint", "layout.json"), "w", encoding="utf-8") as handle:
                handle.write(layout_json)
        with open(os.path.join(self.config, "CLAUDE.md"), "w", encoding="utf-8") as handle:
            handle.write("@%s/CLAUDE.md\n" % pointer.replace("\\", "/"))

    def write_extras(self, keys):
        """The repo's extras file holds `keys` as JSON, beside the kinds key every extras file has."""
        os.makedirs(os.path.join(self.primary, ".claude"), exist_ok=True)
        with open(os.path.join(self.primary, ".claude", "layout-extras.json"), "w", encoding="utf-8") as handle:
            json.dump(dict({"kinds": {}}, **keys), handle)

    def assert_unknown_caution(self, lines):
        """The unknown line prints once, never a public line. Layout.py's facts and acts come with it, which
        shows the line came from the layout's own read and not from the hook's fallback."""
        self.assertIn(UNKNOWN_LINE, lines)
        self.assertEqual(len([l for l in lines if l.startswith("repo caution: ")]), 1, lines)
        self.assertFalse(any(line.startswith("repo caution: public") for line in lines), lines)
        self.assertTrue(any(line.startswith("repo fact: ") for line in lines), lines)
        self.assertTrue(any(line.startswith("repo act: ") for line in lines), lines)

    def test_private_visibility_prints_the_private_solo_level(self):
        self.point_at()
        self.write_extras({"visibility": "private"})
        lines = self.run_hook()
        self.assertIn("repo caution: private-solo", lines)
        self.assertTrue(any(line.startswith("repo fact: ") for line in lines))
        self.assertEqual(len([l for l in lines if l.startswith("repo caution: ")]), 1)

    def test_public_visibility_prints_the_public_level(self):
        self.point_at()
        self.write_extras({"visibility": "public"})
        lines = self.run_hook()
        self.assertIn("repo caution: public", lines)
        self.assertEqual(len([l for l in lines if l.startswith("repo caution: ")]), 1)

    def test_no_extras_file_prints_unknown_never_public(self):
        self.point_at()
        self.assert_unknown_caution(self.run_hook())

    def test_an_extras_file_with_no_readable_visibility_prints_unknown_never_public(self):
        self.point_at()
        for keys in ({}, {"visibility": None}, {"visibility": 3}, {"visibility": "default"},
                     {"visibility": "secret-ish"}):
            with self.subTest(keys=keys):
                self.write_extras(keys)
                self.assert_unknown_caution(self.run_hook())

    def test_a_read_that_cannot_run_prints_unknown_never_a_level(self):
        self.point_at(layout_json="{broken")
        lines = self.run_hook()
        self.assertIn(UNKNOWN_LINE, lines)
        self.assertFalse(any(line.startswith("repo caution: public") for line in lines))


class SessionStartTierLineTests(SessionStartAgentWorktreeNoticeTests):
    """The session-tier line prints once, after the checkout line, when CLAUDE_CODE_REMOTE is exactly "true" or
    CLAUDE_CODE_REMOTE_SESSION_ID is non-empty. A local lane session sets only the id, so it still reads its record."""

    # The 51-worktree case builds 51 worktrees; this class does not repeat it.
    test_no_notice_at_fifty_and_one_notice_at_fifty_one = None

    def tier_lines(self, lines):
        return [line for line in lines if line.startswith("session tier:")]

    def outside_a_git_tree(self):
        """A folder under the run root that is no git tree. The probe proves it, or the case tests nothing."""
        outside = os.path.join(self.root, "outside")
        os.makedirs(outside)
        probe = subprocess.run([VCS, "-C", outside, "rev-parse", "--show-toplevel"], capture_output=True,
                               text=True, timeout=60)
        self.assertNotEqual(probe.returncode, 0, "the folder is inside a git tree, so the case tests nothing: %r"
                            % outside)
        return outside

    def test_cloud_prints_the_tier_line_once_right_after_the_checkout_line(self):
        expected = hook_tier_line()
        lines = self.run_hook(remote="true")
        self.assertTrue(lines and lines[0].startswith("checkout "), "no checkout line first: %r" % lines)
        self.assertEqual(self.tier_lines(lines), [expected])
        self.assertEqual(lines.index(expected), 1, "the tier line is not after the checkout line: %r" % lines)

    def test_no_tier_line_unless_the_variable_is_exactly_true(self):
        expected = hook_tier_line()
        # None is a runner that never sets it; the rest are values the hook must not treat as cloud.
        for remote in (None, "", "false", "1", "TRUE"):
            with self.subTest(remote=remote):
                lines = self.run_hook(remote=remote)
                self.assertTrue(lines and lines[0].startswith("checkout "), "no checkout line: %r" % lines)
                self.assertEqual(self.tier_lines(lines), [])
                self.assertNotIn(expected, lines)

    def test_the_tier_line_prints_with_no_remote_and_a_tiny_fetch_timeout(self):
        # The line needs no network, so a fetch bound too short for the bounded git calls still leaves it.
        lines = self.run_hook(remote="true", fetch_timeout="0.01")
        self.assertEqual(self.tier_lines(lines), [hook_tier_line()])

    def test_cloud_prints_the_tier_line_once_outside_any_git_tree(self):
        # The line needs no git, so a cloud session whose cwd is no checkout still gets it, with no stderr.
        outside = self.outside_a_git_tree()
        expected = hook_tier_line()
        lines = self.run_hook(remote="true", session_cwd=outside)
        self.assertEqual(self.last_stderr, "", "the hook wrote to stderr: %r" % self.last_stderr)
        self.assertEqual(self.tier_lines(lines), [expected], "the tier line is not printed once: %r" % lines)

    # A local lane session sets CLAUDE_CODE_REMOTE_SESSION_ID and not CLAUDE_CODE_REMOTE, so the id alone must print the line.
    def test_a_session_id_alone_prints_the_tier_line_in_a_git_tree(self):
        lines = self.run_hook(remote_session_id="cse_abc")
        self.assertTrue(lines and lines[0].startswith("checkout "), "no checkout line first: %r" % lines)
        self.assertEqual(self.tier_lines(lines), [hook_tier_line()],
                         "no tier line in a git tree with CLAUDE_CODE_REMOTE unset and a session id set: %r" % lines)

    def test_a_session_id_alone_prints_the_tier_line_outside_a_git_tree(self):
        outside = self.outside_a_git_tree()
        lines = self.run_hook(session_cwd=outside, remote_session_id="cse_abc")
        self.assertEqual(self.last_stderr, "", "the hook wrote to stderr: %r" % self.last_stderr)
        self.assertEqual(self.tier_lines(lines), [hook_tier_line()],
                         "no tier line outside a git tree with CLAUDE_CODE_REMOTE unset and a session id set: %r"
                         % lines)

    # Green controls: with neither variable set, or the id empty, the hook must print no tier line.
    def test_no_tier_line_with_both_variables_unset_in_a_git_tree(self):
        lines = self.run_hook()
        self.assertTrue(lines and lines[0].startswith("checkout "), "no checkout line first: %r" % lines)
        self.assertEqual(self.tier_lines(lines), [], "a tier line printed with both variables unset: %r" % lines)

    def test_no_tier_line_with_both_variables_unset_outside_a_git_tree(self):
        outside = self.outside_a_git_tree()
        lines = self.run_hook(session_cwd=outside)
        self.assertEqual(self.last_stderr, "", "the hook wrote to stderr: %r" % self.last_stderr)
        self.assertEqual(self.tier_lines(lines), [], "a tier line printed with both variables unset: %r" % lines)

    def test_no_tier_line_with_an_empty_session_id_in_a_git_tree(self):
        lines = self.run_hook(remote_session_id="")
        self.assertTrue(lines and lines[0].startswith("checkout "), "no checkout line first: %r" % lines)
        self.assertEqual(self.tier_lines(lines), [], "a tier line printed with an empty session id: %r" % lines)


class SessionStartSessionHomeTests(SessionStartAgentWorktreeNoticeTests):
    """Rule session-home: a resumed session whose recorded worktree is gone gets one line that says
    so and names EnterWorktree, before any write. The record is `<primary>/.git/session-homes/<session_id>`.
    The record is written by hand here: this hook only reads it, and the guard's own write has its cases."""

    # The 51-worktree case builds 51 worktrees; this class does not repeat it.
    test_no_notice_at_fifty_and_one_notice_at_fifty_one = None

    def record_lane(self, name):
        """A worktree at `.claude/worktrees/<name>`, and a record that names it. Returns its path."""
        lane = os.path.join(self.primary, ".claude", "worktrees", name)
        vcs(self.primary, "worktree", "add", "-q", "--detach", "--no-checkout", lane, "HEAD")
        record = os.path.join(self.primary, ".git", "session-homes", SESSION)
        os.makedirs(os.path.dirname(record), exist_ok=True)
        with open(record, "w", encoding="utf-8") as handle:
            handle.write(lane)
        return lane

    def lose_lane(self, lane):
        """The harness removes the worktree's folder."""
        vcs(self.primary, "worktree", "remove", "--force", lane)

    @staticmethod
    def enter_lines(lines):
        return [line for line in lines if "EnterWorktree" in line]

    def test_resume_with_a_gone_worktree_prints_one_enter_worktree_line(self):
        baseline = self.run_hook(source="resume")
        lane = self.record_lane("lane-gone")
        self.lose_lane(lane)
        lines = self.run_hook(source="resume")
        extra = [line for line in lines if line not in baseline]
        self.assertEqual(len(extra), 1, "want one new line for a gone worktree, got %r" % extra)
        self.assertRegex(extra[0], r"gone|missing|removed", "the line does not say the worktree is gone: %r" % extra[0])
        self.assertNotIn(lane, extra[0], "the line names the lost worktree's path: %r" % extra[0])

    def test_the_compact_source_spelling_prints_the_same_line(self):
        lane = self.record_lane("lane-compact")
        self.lose_lane(lane)
        spaced = self.enter_lines(self.run_hook(source="resume"))
        compact = self.enter_lines(self.run_hook(source="resume", compact=True))
        self.assertEqual(len(compact), 1, "the compact payload prints %d lines naming EnterWorktree" % len(compact))
        self.assertEqual(compact, spaced)

    def test_startup_with_a_gone_worktree_prints_nothing_new(self):
        lane = self.record_lane("lane-startup")
        self.lose_lane(lane)
        lines = self.run_hook(source="startup")
        self.assertEqual(self.enter_lines(lines), [], "a startup printed the resume line: %r" % lines)

    def test_resume_with_no_record_prints_nothing_new(self):
        lines = self.run_hook(source="resume")
        self.assertEqual(self.enter_lines(lines), [], "a resume with no record printed the line: %r" % lines)

    def test_resume_with_the_recorded_folder_present_prints_nothing_new(self):
        self.record_lane("lane-present")
        lines = self.run_hook(source="resume")
        self.assertEqual(self.enter_lines(lines), [], "a present folder printed the line: %r" % lines)

    def test_resume_outside_git_prints_nothing_new(self):
        outside = os.path.join(self.root, "outside")
        os.makedirs(outside)
        probe = subprocess.run([VCS, "-C", outside, "rev-parse", "--show-toplevel"], capture_output=True,
                               text=True, timeout=60)
        self.assertNotEqual(probe.returncode, 0, "the folder is inside a git tree, so the case tests nothing: %r"
                            % outside)
        lines = self.run_hook(source="resume", session_cwd=outside)
        self.assertEqual(self.last_stderr, "", "the hook wrote to stderr: %r" % self.last_stderr)
        self.assertEqual(self.enter_lines(lines), [], "a resume outside git printed the line: %r" % lines)


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder

class SessionStartMergeRoleTests(unittest.TestCase):
    """The tier line tells a cloud session how to record its merge role: `merge --role <tier>`, for the one tier that may run
    `merge <pr> --confirm` (merge/merge.py MERGE_ROLES; decision session-tiers: the coordinator never merges).
    It reads the hook's own text, so no repo fixture is built. The existing SessionStartTierLineTests prove the line prints
    once and only in the cloud."""

    @staticmethod
    def merge_is_negated(sentence):
        """True when the sentence negates a merge: `never merges`, `not merge`, `no merges`."""
        return re.search(r"\b(?:never|not|no)\s+merges?\b", sentence, re.IGNORECASE) is not None

    @staticmethod
    def says_coordinator_merges(sentence):
        """True when the sentence names a coordinator and a merge the sentence does not negate."""
        return ("coordinator" in sentence.lower() and re.search(r"\bmerges?\b", sentence, re.IGNORECASE) is not None
                and not SessionStartMergeRoleTests.merge_is_negated(sentence))

    @staticmethod
    def says_coordinator_never_merges(sentence):
        """True when the sentence names a coordinator and says `never merges`."""
        return "coordinator" in sentence.lower() and re.search(r"\bnever merges\b", sentence, re.IGNORECASE) is not None

    @staticmethod
    def is_no_parent_merge(sentence):
        """True when a session with no parent, or one the owner started, merges its own PR under the merge grant, not negated."""
        return (re.search(r"no parent|owner started", sentence, re.IGNORECASE) is not None and "own PR" in sentence
                and "merge grant" in sentence and not SessionStartMergeRoleTests.merge_is_negated(sentence))

    @staticmethod
    def names_a_lane(sentence):
        """True when the sentence names the lane session: its cs-build:lane tag, or the words `lane session`."""
        return "cs-build:lane" in sentence or "lane session" in sentence

    def test_the_tier_line_names_the_role_writer(self):
        self.assertIn("merge --role", hook_tier_line())

    def test_the_merge_role_sentence_names_the_command_by_its_home_path(self):
        # Bare `merge` is not on a cloud session's PATH, so the sentence gives the shim's full path.
        self.assertIn("~/.claude/bin/merge --role", merge_role_sentence(hook_tier_line()))

    # decision session-tiers: re-pointed from both tiers to the batch runner alone
    def test_the_merge_role_sentence_names_only_the_batch_runner_tag(self):
        role = [s for s in sentences(hook_tier_line()) if "merge role" in s.lower()]
        self.assertEqual(len(role), 1, role)
        self.assertIn("cs-build:batch-runner", role[0])
        self.assertNotIn("coordinator", role[0].lower(), role[0])

    # decision session-tiers: no sentence of the tier line says a coordinator merges; "never merges" is not a merge
    def test_no_sentence_of_the_tier_line_says_a_coordinator_merges(self):
        told = [s for s in sentences(hook_tier_line()) if self.says_coordinator_merges(s)]
        self.assertEqual(told, [], "the tier line says a coordinator merges: %r" % told)

    # decision session-tiers: the coordinator never merges, so one sentence of the tier line says so
    def test_some_sentence_of_the_tier_line_says_the_coordinator_never_merges(self):
        told = [s for s in sentences(hook_tier_line()) if self.says_coordinator_never_merges(s)]
        self.assertTrue(told, "no sentence of the tier line says the coordinator never merges")

    # decision session-tiers: a session the owner started (no parent) merges its own PR under the merge grant, affirmatively
    def test_a_session_with_no_parent_merges_its_own_pr_under_the_merge_grant(self):
        told = [s for s in sentences(hook_tier_line()) if self.is_no_parent_merge(s)]
        self.assertTrue(told, "no affirmative sentence says a session with no parent merges its own PR under the merge grant")

    # decision session-tiers: only a solo or one-lane session the owner started merges its own PR, so its sentence names that shape
    def test_the_no_parent_merge_sentence_names_solo_or_one_lane(self):
        told = [s for s in sentences(hook_tier_line()) if self.is_no_parent_merge(s)]
        self.assertTrue(told, "no affirmative sentence says a session with no parent merges its own PR under the merge grant")
        for sentence in told:
            self.assertIn("solo or one-lane", sentence, "the no-parent merge sentence does not name solo or one-lane: %r" % sentence)

    def hand_off_sentence(self):
        """The tier line's one sentence that hands a branch to the batch runner. Asserts that scope before any content."""
        found = [s for s in sentences(hook_tier_line()) if "hands" in s and "batch runner" in s]
        self.assertEqual(len(found), 1, "expected one hand-off sentence, found %d: %r" % (len(found), found))
        return found[0]

    # decision session-tiers: only a lane (a session with a parent_session_id) hands its branch to the batch runner
    def test_the_hand_off_sentence_names_a_parent_session_id(self):
        self.assertIn("parent_session_id", self.hand_off_sentence(), "the hand-off sentence names no parent_session_id")

    # decision session-tiers: only a lane session hands its branch to the batch runner; a parent_session_id alone is not one
    def test_the_hand_off_sentence_names_the_lane_session(self):
        sentence = self.hand_off_sentence()
        self.assertTrue(self.names_a_lane(sentence), "the hand-off sentence names no cs-build:lane tag and no lane session: %r" % sentence)

    # decision session-tiers: only a lane session hands its branch to the batch runner
    def test_the_hand_off_sentence_does_not_say_any_other_session(self):
        self.assertNotIn("any other session", self.hand_off_sentence().lower(), "the hand-off sentence says any other session hands off")

    def test_the_tier_line_says_the_role_is_recorded_again_after_a_resume(self):
        # A resumed session keeps its id, but the role file may be gone (a fresh container): the line must not say the call is a one-time act.
        sentence = merge_role_sentence(hook_tier_line())
        self.assertIn("resume", sentence.lower(), sentence)

    def test_the_tier_line_does_not_say_once(self):
        self.assertNotRegex(hook_tier_line(), r"(?i)\bonce\b")

    def test_the_merge_role_sentence_is_found_by_its_edges(self):
        # The helper cuts at ". ": from the one before `merge --role` to the one after it, or to the line's ends.
        self.assertEqual(merge_role_sentence("A one. B runs `merge --role x` now. C two."), "B runs `merge --role x` now.")
        self.assertEqual(merge_role_sentence("merge --role x. C two."), "merge --role x.")
        self.assertEqual(merge_role_sentence("A one. B runs merge --role x"), "B runs merge --role x")

    # decision session-tiers: the coordinator predicate flags a merging coordinator and passes a negated one (green control)
    def test_the_coordinator_merge_predicate_flags_a_merge_and_passes_a_negated_one(self):
        self.assertTrue(self.says_coordinator_merges("The coordinator merges its own PR."))
        self.assertFalse(self.says_coordinator_merges("The coordinator never merges."))

    # decision session-tiers: the never-merges predicate takes only "never merges" with a coordinator (green control)
    def test_the_coordinator_never_merges_predicate_takes_only_the_negated_coordinator(self):
        self.assertTrue(self.says_coordinator_never_merges("The coordinator never merges."))
        self.assertFalse(self.says_coordinator_never_merges("The coordinator merges its own PR."))
        self.assertFalse(self.says_coordinator_never_merges("A lane session never merges its own PR."))

    # decision session-tiers: the no-parent predicate takes only an affirmative merge, so a negated one never satisfies it (green control)
    def test_the_no_parent_merge_predicate_rejects_a_negated_merge(self):
        self.assertTrue(self.is_no_parent_merge("A solo or one-lane session with no parent_session_id merges its own PR under the repo merge grant."))
        self.assertFalse(self.is_no_parent_merge("A session with no parent_session_id never merges its own PR under the merge grant."))
        self.assertFalse(self.is_no_parent_merge("A session with a parent_session_id merges its own PR under the merge grant."))

    # decision session-tiers: a hand-off that names no lane session does not scope to the lane (green control)
    def test_the_lane_predicate_rejects_a_hand_off_that_names_no_lane(self):
        self.assertFalse(self.names_a_lane("A session with a parent_session_id hands its reviewed branch, head and PR to the batch "
                                           "runner (list_sessions, tag cs-build:batch-runner, same repo) and never merges."))
        self.assertTrue(self.names_a_lane("A lane session (tag cs-build:lane) hands its reviewed branch, head and PR to the batch "
                                          "runner and never merges."))


class SessionStartLivePinNoticeTests(SessionStartAgentWorktreeNoticeTests):
    """A cwd inside a claude-settings live pin prints one line that names the pin, the words "live pin", and the
    clone to cd to. The pin is the linked worktree <clone>-live-<12 hex>, or the <clone>-live link to it. A pin
    counts only when the clone beside it holds merge/install_from_main.sh, the install script that makes the pin
    (the scope guard_frozen.py uses). Folders that only look like one print no such line."""

    # The 51-worktree case builds 51 worktrees; this class does not repeat it.
    test_no_notice_at_fifty_and_one_notice_at_fifty_one = None

    def setUp(self):
        super().setUp()
        # The clone holds the install script before the pin is made, so the pin carries it too.
        os.makedirs(os.path.join(self.primary, "merge"))
        with open(os.path.join(self.primary, "merge", "install_from_main.sh"), "w", encoding="utf-8") as handle:
            handle.write("# stub: the install script that makes the live pin\n")
        vcs(self.primary, "add", "-A")
        vcs(self.primary, "commit", "-q", "-m", "install script")
        # The pin's name is <clone>-live-<12 hex>, the short sha install_from_main.sh makes it with.
        short = vcs(self.primary, "rev-parse", "--short=12", "HEAD").stdout.strip()
        self.pin = self.primary + "-live-" + short
        self.link = self.primary + "-live"
        vcs(self.primary, "worktree", "add", "-q", "--detach", self.pin, "HEAD")

    @staticmethod
    def phys(path):
        return os.path.realpath(path).replace("\\", "/")

    @staticmethod
    def names(line, path):
        """True when the line holds PATH as a whole path, not as the front of a longer one such as <clone>-live."""
        return re.search(re.escape(path) + r"(?![\w-]|\.\w)", line) is not None

    def link_to(self, target, link):
        try:
            os.symlink(target, link)
        except (OSError, NotImplementedError) as error:
            self.skipTest("this account cannot create a symlink: %s" % error)
        return link

    def make_link(self):
        return self.link_to(self.pin, self.link)

    @staticmethod
    def live_pin_lines(lines):
        return [line for line in lines if "live pin" in line]

    def assert_one_live_pin_line(self, lines, pin_paths):
        found = self.live_pin_lines(lines)
        self.assertEqual(len(found), 1, "want one live pin line, got %r" % lines)
        line = found[0].replace("\\", "/")
        self.assertTrue(any(self.names(line, path) for path in pin_paths),
                        "the line does not name the pin: %r" % found[0])
        self.assertTrue(self.names(line, self.phys(self.primary)),
                        "the line does not name the clone to cd to: %r" % found[0])

    def assert_no_live_pin_line(self, session_cwd=None):
        lines = self.run_hook(session_cwd=session_cwd)
        # Control: the hook really ran. Without its checkout line, "no line" would pass vacuously.
        self.assertTrue(any(line.startswith("checkout ") for line in lines),
                        "the hook printed no checkout line: %r" % lines)
        self.assertEqual(self.live_pin_lines(lines), [],
                         "a live pin line printed for a folder that is not a live pin: %r" % lines)

    def test_a_cwd_in_the_pin_by_its_hex_path_prints_one_live_pin_line(self):
        lines = self.run_hook(session_cwd=self.pin)
        self.assert_one_live_pin_line(lines, [self.phys(self.pin)])

    def test_a_cwd_in_the_pin_through_the_live_link_prints_one_live_pin_line(self):
        link = self.make_link()
        lines = self.run_hook(session_cwd=link)
        # The hook reads the resolved path (git's toplevel), so the pin's own path is the expected one;
        # the link's text is accepted too, since it names the same pin.
        link_text = self.phys(os.path.dirname(link)) + "/" + os.path.basename(link)
        self.assert_one_live_pin_line(lines, [self.phys(self.pin), link_text])

    def test_a_subfolder_of_the_pin_prints_the_same_line(self):
        sub = os.path.join(self.pin, "nested")
        os.makedirs(sub)
        lines = self.run_hook(session_cwd=sub)
        self.assert_one_live_pin_line(lines, [self.phys(self.pin)])

    def test_the_clone_prints_no_live_pin_line(self):
        self.assert_no_live_pin_line()

    def test_an_agent_worktree_of_the_clone_prints_no_live_pin_line(self):
        agent = os.path.join(self.primary, ".claude", "worktrees", "agent-x")
        vcs(self.primary, "worktree", "add", "-q", "--detach", agent, "HEAD")
        self.assert_no_live_pin_line(session_cwd=agent)

    def test_a_standalone_repo_named_like_a_pin_prints_no_live_pin_line(self):
        # Not a worktree of the clone: a name-only check would fire on it.
        plain = os.path.join(self.root, "plain-live")
        os.makedirs(plain)
        vcs(plain, "init", "-q", "-b", "main", ".")
        with open(os.path.join(plain, "f.txt"), "w", encoding="utf-8") as handle:
            handle.write("plain\n")
        vcs(plain, "add", "-A")
        vcs(plain, "commit", "-q", "-m", "plain")
        self.assert_no_live_pin_line(session_cwd=plain)

    def test_a_linked_worktree_named_livex_prints_no_live_pin_line(self):
        livex = self.primary + "-livex"
        vcs(self.primary, "worktree", "add", "-q", "--detach", livex, "HEAD")
        self.assert_no_live_pin_line(session_cwd=livex)

    def pin_beside_a_clone_without_the_script(self):
        """A clone that holds no merge/install_from_main.sh, and a pin made beside it the way install.sh makes one."""
        unscripted = os.path.join(self.root, "unscripted")
        os.makedirs(unscripted)
        vcs(unscripted, "init", "-q", "-b", "main", ".")
        with open(os.path.join(unscripted, "f.txt"), "w", encoding="utf-8") as handle:
            handle.write("unscripted\n")
        vcs(unscripted, "add", "-A")
        vcs(unscripted, "commit", "-q", "-m", "unscripted")
        short = vcs(unscripted, "rev-parse", "--short=12", "HEAD").stdout.strip()
        pin = unscripted + "-live-" + short
        vcs(unscripted, "worktree", "add", "-q", "--detach", pin, "HEAD")
        self.assertFalse(os.path.exists(os.path.join(unscripted, "merge", "install_from_main.sh")),
                         "the fixture clone holds the install script, so the control tests nothing")
        return unscripted, pin

    def test_a_pin_beside_a_clone_without_the_install_script_prints_no_live_pin_line(self):
        unscripted, pin = self.pin_beside_a_clone_without_the_script()
        self.assert_no_live_pin_line(session_cwd=pin)

    def test_a_link_to_a_pin_beside_a_clone_without_the_install_script_prints_no_live_pin_line(self):
        unscripted, pin = self.pin_beside_a_clone_without_the_script()
        link = self.link_to(pin, unscripted + "-live")
        self.assert_no_live_pin_line(session_cwd=link)


# The waiting page behind main (rule page-stale). A repo whose extras name a waiting page prints one line
# when the stamp an allowed publish wrote, <git common dir>/waiting-page-built, holds a blob sha other than
# main's page.html. Main is origin/main of the claude-settings clone that the config's CLAUDE.md names, the
# checkout the guard's stale_pages reads, not the session's own repo. The page text here is a stand-in: the
# hook compares blob shas and never reads the text.
WAITING_URL = "https://claude.ai/artifact/sspage"
WAITING_PAGE_REL = "skills/waiting-page/page.html"
WAITING_STAMP = "waiting-page-built"
MAIN_PAGE = "<!doctype html>\n<title>Queue</title>\n"
OLDER_PAGE = "<!doctype html>\n<title>Queue, older</title>\n"


class SessionStartWaitingPageTests(SessionStartAgentWorktreeNoticeTests):
    """The session-start line for a waiting page built from a page other than main's (rule page-stale)."""

    # The 51-worktree case builds 51 worktrees; this class does not repeat it.
    test_no_notice_at_fifty_and_one_notice_at_fifty_one = None

    def setUp(self):
        super().setUp()
        # The claude-settings clone stands in: a checkout whose origin/main holds the skill's page.
        self.pointer = os.path.join(self.root, "claude-settings")
        self.put(os.path.join(self.pointer, WAITING_PAGE_REL), MAIN_PAGE)
        vcs(self.pointer, "init", "-q", "-b", "main", ".")
        vcs(self.pointer, "add", "-A")
        vcs(self.pointer, "commit", "-q", "-m", "main")
        vcs(self.pointer, "update-ref", "refs/remotes/origin/main", "HEAD")
        self.main_sha = vcs(self.pointer, "rev-parse", "origin/main:" + WAITING_PAGE_REL).stdout.strip()
        older = os.path.join(self.root, "older.html")
        self.put(older, OLDER_PAGE)
        self.older_sha = vcs(self.pointer, "hash-object", older).stdout.strip()
        self.put(os.path.join(self.config, "CLAUDE.md"), "@%s/CLAUDE.md\n" % self.pointer.replace("\\", "/"))
        self.waiting_extras(self.primary)

    def put(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def waiting_extras(self, checkout):
        """The checkout's extras file names the waiting page, as lint/layout.py reads it."""
        self.put(os.path.join(checkout, ".claude", "layout-extras.json"),
                 json.dumps({"kinds": {}, "waiting-page": WAITING_URL}))

    def stamp(self, sha):
        """Write the stamp into the common git dir of the primary checkout, where an allowed publish puts it."""
        self.put(os.path.join(self.primary, ".git", WAITING_STAMP), sha + "\n")

    def waiting_lines(self, lines):
        return [line for line in lines if re.search("waiting page", line, re.IGNORECASE)]

    def run_checked(self, session_cwd=None):
        """The hook's lines. A control first: the hook ran and printed its checkout line, so an empty
        waiting-page answer is not an empty run."""
        lines = self.run_hook(session_cwd=session_cwd)
        self.assertTrue(any(line.startswith("checkout ") for line in lines),
                        "the hook printed no checkout line: %r" % lines)
        return lines

    def test_a_stamp_that_is_not_main_blob_prints_one_behind_line(self):
        self.stamp(self.older_sha)
        hits = self.waiting_lines(self.run_checked())
        self.assertEqual(len(hits), 1, "expected one waiting page line, got %r" % hits)
        self.assertIn("behind", hits[0], "the waiting page line does not say behind: %r" % hits[0])

    def test_a_stamp_equal_to_main_blob_prints_no_line(self):
        self.stamp(self.main_sha)
        self.assertEqual(self.waiting_lines(self.run_checked()), [])

    def test_no_stamp_prints_no_line(self):
        self.assertEqual(self.waiting_lines(self.run_checked()), [])

    def test_main_unreadable_prints_no_line_even_with_a_stale_stamp(self):
        self.stamp(self.older_sha)
        vcs(self.pointer, "update-ref", "-d", "refs/remotes/origin/main")
        self.assertEqual(self.waiting_lines(self.run_checked()), [])

    def test_a_repo_whose_extras_name_no_waiting_page_prints_no_line(self):
        self.stamp(self.older_sha)
        os.remove(os.path.join(self.primary, ".claude", "layout-extras.json"))
        self.assertEqual(self.waiting_lines(self.run_checked()), [])

    def test_a_linked_worktree_reads_the_stamp_of_the_common_dir(self):
        linked = os.path.join(self.root, "linked")
        vcs(self.primary, "worktree", "add", "-q", "--detach", linked, "HEAD")
        self.waiting_extras(linked)
        self.stamp(self.older_sha)
        hits = self.waiting_lines(self.run_checked(session_cwd=linked))
        self.assertEqual(len(hits), 1, "expected one waiting page line from the linked worktree, got %r" % hits)
        self.assertIn("behind", hits[0], "the waiting page line does not say behind: %r" % hits[0])


class SessionStartEnvFileTests(SessionStartAgentWorktreeNoticeTests):
    """The PATH line the hook writes to CLAUDE_ENV_FILE (roadmap step wait-tools-on-path). The guard's remedies
    name wait-until and wait-pid by their bare names, which resolve in a session only through that line."""

    # The 51-worktree case builds 51 worktrees; this class does not repeat it.
    test_no_notice_at_fifty_and_one_notice_at_fifty_one = None
    SEED = "export KEEP_ME=1\n"  # a line the env file held before any run; no run may drop it
    BIN_MARK = ".claude/bin"  # the text the hook's line names the bin folder by

    def setUp(self):
        super().setUp()
        # HOME is a fixture. Its .claude/bin holds one executable wait-until stub, so no real folder can answer.
        self.home = os.path.join(self.root, "home")
        self.bin_dir = os.path.join(self.home, ".claude", "bin")
        os.makedirs(self.bin_dir)
        self.stub = make_stub(self.bin_dir, "wait-until")
        self.env_file = os.path.join(self.root, "claude_env")
        self.seed("")  # empty, as a fresh session starts it

    def seed(self, text):
        with open(self.env_file, "w", encoding="utf-8") as handle:
            handle.write(text)

    def hook_env(self, **extra):
        """The environment of one hook run: the fixture HOME and env file, plus the variables the case sets."""
        return dict({"HOME": self.home, "CLAUDE_ENV_FILE": self.env_file}, **extra)

    def env_lines(self):
        with open(self.env_file, encoding="utf-8") as handle:
            return handle.read().splitlines()

    def bin_lines(self):
        return [line for line in self.env_lines() if self.BIN_MARK in line]

    def tree_names(self):
        """Every file under the fixture root, relative, so a file the hook makes anywhere shows up."""
        found = []
        for folder, _dirs, files in os.walk(self.root):
            found += [os.path.relpath(os.path.join(folder, name), self.root) for name in files]
        return sorted(found)

    def probe(self, body, source=True, path=None):
        """Stdout of a fresh sh running `body`, after it sources CLAUDE_ENV_FILE when `source` is set. HOME is the fixture.
        `path`, when given, is the PATH the shell starts with."""
        script = '. "$1" || exit 3; ' + body if source else body
        env = dict(os.environ, HOME=self.home)
        if path is not None:
            env["PATH"] = path
        answer = subprocess.run([sh_exe(), "-c", script, "sh", self.env_file], capture_output=True, text=True,
                                env=env, timeout=60)
        self.assertEqual(answer.returncode, 0, "the sh probe failed, exit %d: %s"
                         % (answer.returncode, answer.stderr.strip()))
        return answer.stdout.strip()

    def resolve(self, source, name="wait-until", path=None):
        """Where a fresh sh finds `name`, after it sources the env file when `source` is set. HOME is the fixture."""
        return self.probe("command -v %s || true" % name, source=source, path=path)

    def assert_stub_resolves(self, where, name="wait-until", stub=None, path=None):
        stub = self.stub if stub is None else stub
        found = self.resolve(source=True, name=name, path=path)
        self.assertTrue(found and os.path.realpath(found) == os.path.realpath(stub),
                        "%s does not resolve to the fixture stub after %s: got %r" % (name, where, found))

    def test_a_the_env_file_puts_the_stub_on_path(self):
        lines = self.run_hook(extra_env=self.hook_env())
        # Scope first: the hook ran, and the stub is not on the base PATH, so a later resolution comes from the hook.
        self.assertTrue(any(line.startswith("checkout ") for line in lines),
                        "the hook printed no checkout line: %r" % lines)
        self.assertEqual(self.last_stderr, "", "the hook wrote to stderr: %r" % self.last_stderr)
        self.assertNotEqual(self.resolve(source=False), self.stub,
                            "fixture setup failed: the stub already resolves on the base PATH")
        self.assert_stub_resolves("the hook ran in a git checkout")

    def test_a2_a_session_outside_any_git_tree_gets_the_line_too(self):
        # self.root holds git repos below it, but is not inside one, so the hook takes its no-checkout exit.
        self.run_hook(session_cwd=self.root, extra_env=self.hook_env())
        self.assertEqual(self.last_stderr, "", "the hook wrote to stderr outside any git tree: %r" % self.last_stderr)
        self.assert_stub_resolves("the hook ran outside any git tree")

    def test_b_two_runs_add_one_line_and_keep_the_seed(self):
        self.seed(self.SEED)
        self.run_hook(extra_env=self.hook_env())
        self.assertEqual(self.last_stderr, "", "the first run wrote to stderr: %r" % self.last_stderr)
        self.assertIn(self.SEED.strip(), self.env_lines(), "the first run dropped the env file's own line")
        self.assertEqual(len(self.bin_lines()), 1,
                         "the first run wrote %d bin-folder lines, want 1: %r" % (len(self.bin_lines()), self.env_lines()))
        # The test's PATH never holds the bin folder, so the second run finds its line only by reading the file.
        self.run_hook(extra_env=self.hook_env())
        self.assertEqual(self.last_stderr, "", "the second run wrote to stderr: %r" % self.last_stderr)
        self.assertIn(self.SEED.strip(), self.env_lines(), "the second run dropped the env file's own line")
        self.assertEqual(len(self.bin_lines()), 1,
                         "the second run left %d bin-folder lines, want 1: %r" % (len(self.bin_lines()), self.env_lines()))

    def test_c_a_path_that_holds_the_bin_folder_writes_nothing(self):
        self.seed(self.SEED)
        path = os.pathsep.join([self.bin_dir, os.environ.get("PATH", "")])
        lines = self.run_hook(extra_env=self.hook_env(PATH=path))
        self.assertTrue(any(line.startswith("checkout ") for line in lines),
                        "the hook printed no checkout line: %r" % lines)
        self.assertEqual(self.env_lines(), self.SEED.splitlines(),
                         "a run whose PATH already holds ~/.claude/bin changed CLAUDE_ENV_FILE")

    def test_d_without_an_env_file_the_hook_exits_quietly_and_writes_nothing(self):
        before = self.tree_names()
        lines = self.run_hook(extra_env={"HOME": self.home})
        self.assertTrue(any(line.startswith("checkout ") for line in lines),
                        "the hook printed no checkout line: %r" % lines)
        self.assertEqual(self.last_stderr, "", "the hook wrote to stderr: %r" % self.last_stderr)
        self.assertEqual(self.tree_names(), before, "the hook created or removed files with CLAUDE_ENV_FILE unset")

    def assert_missing_env_file_gets_the_line(self, session_cwd, where):
        # The name has a space, as a real session's path may. Its folder exists; the file does not yet.
        folder = os.path.join(self.root, "fresh area")
        os.makedirs(folder)
        self.env_file = os.path.join(folder, "env file.sh")
        self.assertFalse(os.path.exists(self.env_file), "fixture setup failed: the env file exists before the run")
        self.run_hook(session_cwd=session_cwd, extra_env=self.hook_env())
        self.assertEqual(self.last_stderr, "", "the hook wrote to stderr for a missing env file, %s: %r"
                         % (where, self.last_stderr))
        self.assertTrue(os.path.isfile(self.env_file), "the hook did not create the env file, %s" % where)
        self.assertEqual(len(self.bin_lines()), 1, "the env file holds %d bin-folder lines after the run, %s, want 1: %r"
                         % (len(self.bin_lines()), where, self.env_lines()))

    def test_e_a_missing_env_file_in_an_existing_folder_gets_the_line_in_a_git_tree(self):
        self.assert_missing_env_file_gets_the_line(session_cwd=None, where="a session inside a git tree")

    def test_e2_a_missing_env_file_in_an_existing_folder_gets_the_line_outside_a_git_tree(self):
        self.assert_missing_env_file_gets_the_line(session_cwd=self.root, where="a session outside any git tree")

    def test_f_an_env_file_that_names_a_directory_is_left_alone(self):
        self.env_file = os.path.join(self.root, "env dir")
        os.makedirs(self.env_file)
        self.assertTrue(os.path.isdir(self.env_file), "fixture setup failed: the env path is not a directory")
        before = self.tree_names()
        lines = self.run_hook(extra_env=self.hook_env())
        self.assertTrue(any(line.startswith("checkout ") for line in lines),
                        "the hook printed no checkout line: %r" % lines)
        self.assertEqual(self.last_stderr, "", "the hook wrote to stderr when CLAUDE_ENV_FILE names a directory: %r"
                         % self.last_stderr)
        self.assertEqual(self.tree_names(), before, "the hook wrote a file when CLAUDE_ENV_FILE names a directory")

    def test_g_a_seed_with_no_trailing_newline_keeps_its_own_line(self):
        # No newline after the seed: the hook's line must start on a line of its own.
        self.seed(self.SEED.rstrip("\n"))
        lines = self.run_hook(extra_env=self.hook_env())
        self.assertTrue(any(line.startswith("checkout ") for line in lines),
                        "the hook printed no checkout line: %r" % lines)
        self.assertIn(self.SEED.strip(), self.env_lines(),
                      "the seed line is not a line of its own, so the hook's line was glued to it: %r" % self.env_lines())
        self.assertEqual(self.probe('printf %s "$KEEP_ME"'), "1", "sourcing the env file did not set KEEP_ME to 1")
        self.assert_stub_resolves("the first run after a seed with no trailing newline")
        self.run_hook(extra_env=self.hook_env())
        self.assertEqual(len(self.bin_lines()), 1, "after the second run the env file holds %d bin-folder lines, want 1: %r"
                         % (len(self.bin_lines()), self.env_lines()))

    def test_h_the_bin_folder_comes_before_a_system_rm(self):
        real_rm = shutil.which("rm")
        usr_dir = os.path.join(self.root, "usr-like", "bin")
        os.makedirs(usr_dir)
        usr_rm = make_stub(usr_dir, "rm", 'exec "%s" "$@"\n' % real_rm)
        # Each stub execs the real rm, so the hook's own rm -f still runs when the stub leads PATH.
        bin_rm = make_stub(self.bin_dir, "rm", 'exec "%s" "$@"\n' % real_rm)
        path = os.pathsep.join([usr_dir, self.bin_dir, os.environ.get("PATH", "")])
        # Scope first: the fixture PATH gives the system rm the lead before any run.
        self.assertEqual(os.path.realpath(self.resolve(source=False, name="rm", path=path)), os.path.realpath(usr_rm),
                         "fixture setup failed: rm does not resolve to the system stub on the fixture PATH")
        lines = self.run_hook(extra_env=self.hook_env(PATH=path))
        self.assertTrue(any(line.startswith("checkout ") for line in lines),
                        "the hook printed no checkout line: %r" % lines)
        self.assert_stub_resolves("a run whose PATH holds the bin folder behind a system rm",
                                  name="rm", stub=bin_rm, path=path)

    def test_i_an_env_file_in_a_missing_folder_is_left_alone_and_silent(self):
        # The append cannot open a file whose folder is missing. The hook's group keeps that failure off stderr.
        folder = os.path.join(self.root, "no such dir")
        self.env_file = os.path.join(folder, "env.sh")
        self.assertFalse(os.path.exists(folder), "fixture setup failed: the env file's folder exists before the run")
        lines = self.run_hook(extra_env=self.hook_env())
        self.assertTrue(any(line.startswith("checkout ") for line in lines),
                        "the hook printed no checkout line: %r" % lines)
        self.assertEqual(self.last_stderr, "", "the hook wrote to stderr when CLAUDE_ENV_FILE sits in a missing folder: %r"
                         % self.last_stderr)
        self.assertFalse(os.path.exists(folder), "the hook created the missing folder of CLAUDE_ENV_FILE")
        self.assertFalse(os.path.exists(self.env_file), "the hook created CLAUDE_ENV_FILE in a missing folder")


if __name__ == "__main__":
    unittest.main(verbosity=2)
