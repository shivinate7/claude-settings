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


def hook_tier_line():
    """The tier line's text as the hook file holds it, so a wording change in the hook edits no test."""
    with open(HOOK, encoding="utf-8") as handle:
        found = TIER_PRINTF.findall(handle.read())
    if len(found) != 1:
        sys.exit("fixture setup failed: expected one session tier line in %s, found %d" % (HOOK, len(found)))
    return found[0]


def normal_tier_line():
    """The tier line with its whitespace folded and its letters lower-cased, so a test reads a phrase's words, not their casing."""
    return " ".join(hook_tier_line().split()).lower()


def merge_role_sentence(line, anchor="merge --role"):
    """The sentence of the tier line that holds `anchor`: from the ". " before it to the ". " after it, or to the line's ends."""
    at = line.index(anchor)
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

    def run_hook(self, remote=None, fetch_timeout="30", session_cwd=None, source=None, compact=False):
        """The hook's stdout lines. Its stderr lands in self.last_stderr.

        remote: the CLAUDE_CODE_REMOTE value, or None to unset it as a non-cloud runner does.
        session_cwd: the session's cwd, in the payload and as the process cwd; None means the primary checkout.
        source: the payload's "source" (startup, resume, ...), or None to send none.
        compact: send the payload with no spaces after its separators, the way the hook's sed must also read it.
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
        if remote is not None:
            env["CLAUDE_CODE_REMOTE"] = remote
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

    def test_private_visibility_prints_the_private_solo_level(self):
        self.point_at()
        os.makedirs(os.path.join(self.primary, ".claude"))
        with open(os.path.join(self.primary, ".claude", "layout-extras.json"), "w", encoding="utf-8") as handle:
            json.dump({"kinds": {}, "visibility": "private"}, handle)
        lines = self.run_hook()
        self.assertIn("repo caution: private-solo", lines)
        self.assertTrue(any(line.startswith("repo fact: ") for line in lines))
        self.assertEqual(len([l for l in lines if l.startswith("repo caution: ")]), 1)

    def test_a_read_that_cannot_run_prints_unknown_never_a_level(self):
        self.point_at(layout_json="{broken")
        lines = self.run_hook()
        self.assertIn("repo caution: unknown, the level could not be read", lines)
        self.assertFalse(any(line.startswith("repo caution: public") for line in lines))


class SessionStartTierLineTests(SessionStartAgentWorktreeNoticeTests):
    """The cloud session-tier line prints once, after the checkout line, only when CLAUDE_CODE_REMOTE is "true"."""

    # The 51-worktree case builds 51 worktrees; this class does not repeat it.
    test_no_notice_at_fifty_and_one_notice_at_fifty_one = None

    def tier_lines(self, lines):
        return [line for line in lines if line.startswith("session tier:")]

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
        outside = os.path.join(self.root, "outside")
        os.makedirs(outside)
        probe = subprocess.run([VCS, "-C", outside, "rev-parse", "--show-toplevel"], capture_output=True,
                               text=True, timeout=60)
        self.assertNotEqual(probe.returncode, 0, "the folder is inside a git tree, so the case tests nothing: %r"
                            % outside)
        expected = hook_tier_line()
        lines = self.run_hook(remote="true", session_cwd=outside)
        self.assertEqual(self.last_stderr, "", "the hook wrote to stderr: %r" % self.last_stderr)
        self.assertEqual(self.tier_lines(lines), [expected], "the tier line is not printed once: %r" % lines)


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
    """The tier line tells a cloud session how to record its merge role: `merge --role <tier>`, for the two tiers that may run
    `merge <pr> --confirm` (merge/merge.py MERGE_ROLES). It reads the hook's own text, so no repo fixture is built. The existing
    SessionStartTierLineTests prove the line prints once and only in the cloud."""

    def test_the_tier_line_names_the_role_writer(self):
        self.assertIn("merge --role", hook_tier_line())

    def test_the_merge_role_sentence_names_the_command_by_its_home_path(self):
        # Bare `merge` is not on a cloud session's PATH, so the sentence gives the shim's full path.
        self.assertIn("~/.claude/bin/merge --role", merge_role_sentence(hook_tier_line()))

    def test_the_tier_line_names_both_merge_tiers(self):
        line = hook_tier_line()
        for tier in ("coordinator", "batch-runner"):
            with self.subTest(tier=tier):
                self.assertIn(tier, line)

    def test_the_tier_line_says_the_role_is_recorded_again_after_a_resume(self):
        # A resumed session keeps its id, but the role file may be gone (a fresh container): the line must not say the call is a one-time act.
        sentence = merge_role_sentence(hook_tier_line())
        self.assertIn("resume", sentence.lower(), sentence)

    def test_the_tier_line_does_not_say_once(self):
        self.assertNotRegex(hook_tier_line(), r"(?i)\bonce\b")

    def test_the_tier_line_says_only_the_batch_runner_merges(self):
        # Owner ruling (waiting-page item 111 a, 2026-11-01 11:53 CST): in a coordinator build only the batch runner merges.
        line = normal_tier_line()
        anchor = "only the batch runner merges"
        self.assertIn(anchor, line, "the tier line does not say that only the batch runner merges")
        self.assertIn("coordinator build", merge_role_sentence(line, anchor),
                      "the sentence that says only the batch runner merges is not scoped to a coordinator build")

    def test_the_handoff_sentence_is_scoped_to_a_coordinator_build(self):
        # The hand-off to the batch runner binds a session in a coordinator build only: every other session in that build,
        # the coordinator too. A solo or one-lane session keeps merging its own work, so the line must not bind it.
        line = normal_tier_line()
        anchor = "hands the branch, head and pr to the batch runner"
        self.assertIn(anchor, line, "the tier line does not say who hands the branch, head and PR to the batch runner")
        sentence = merge_role_sentence(line, anchor)
        self.assertIn("coordinator build", sentence, "the hand-off is not scoped to a coordinator build: %r" % sentence)
        self.assertIn("the coordinator too", sentence, "the hand-off does not bind the coordinator: %r" % sentence)

    def test_the_merge_role_sentence_is_found_by_its_edges(self):
        # The helper cuts at ". ": from the one before `merge --role` to the one after it, or to the line's ends.
        self.assertEqual(merge_role_sentence("A one. B runs `merge --role x` now. C two."), "B runs `merge --role x` now.")
        self.assertEqual(merge_role_sentence("merge --role x. C two."), "merge --role x.")
        self.assertEqual(merge_role_sentence("A one. B runs merge --role x"), "B runs merge --role x")


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
