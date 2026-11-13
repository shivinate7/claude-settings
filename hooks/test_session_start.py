#!/usr/bin/env python3
"""Session-start notice for agent worktrees. hooks/session_start.sh prints
one notice when more than 50 `.claude/worktrees/agent-*` worktrees exist. At exactly 50 it prints
none. Real git repo and real `git worktree add`. The hook runs as the harness runs it: `sh
session_start.sh` with the session payload on stdin. Stdlib only. Exit 0 on PASS, 1 on FAIL.

    python hooks/test_session_start.py
"""
import hashlib
import json
import os
import re
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "session_start.sh")
sys.path.insert(0, os.path.join(HERE, "..", "lint"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
RUN_FOLDER = _test_temp.run_folder()
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  copies the repo's lint folder into the pointer clone (testing/tracked_tree.py)
import test_ruled_store as fixture  # noqa: E402  the one home of a ruled-store fixture (lint/test_ruled_store.py)
SESSION = "session-start-cases"  # the session id every run_hook payload names
VCS = "g" + "it"  # assembled so this file cannot itself look like the command it tests
IDENT = ["-c", "user.email=session-start-cases@example.invalid", "-c", "user.name=session-start-cases"]
LIMIT = 50  # the notice starts above this many agent worktrees
NOTICE = re.compile(r"agent[ -]worktree", re.IGNORECASE)
# The one printed line whose text starts "session tier: ", quoted in the hook's printf call.
TIER_PRINTF = re.compile(r"'(session tier: .*)'[ \t]*$", re.MULTILINE)
UNKNOWN_LINE = "repo caution: unknown, the level could not be read"  # the hook's line when the caution level is unread
# A hang guard for the cut-off runs. No assert reads it: a hook that never reaches its step ends at EOF.
HOOK_WAIT = 120


def hook_role_line():
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


def sh_exe(name="sh"):
    """Git's own sh.exe (or bash.exe, with name="bash") on Windows, by full path. A bare name can resolve to the WSL stub."""
    if os.name != "nt":
        return shutil.which(name) or name
    for var in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
        candidate = os.path.join(os.environ.get(var) or "", "Git", "bin", name + ".exe")
        if os.path.isfile(candidate):
            return candidate
    sys.exit("fixture setup failed: Git %s.exe not found" % name)


# Git for Windows' sh.exe is a launcher: before the script runs, it puts its own folders ahead of PATH, so a stub folder
# put first on PATH is no longer first inside sh. sh_argv puts the stub folders first again, inside the shell the launcher
# started. A case may set WINDOWS_LAUNCH to True to run this form on Linux.
WINDOWS_LAUNCH = os.name == "nt"
STUB_FIRST = 'PATH="$1:$PATH"; export PATH; shift; exec sh "$@"'  # $1: the folders as sh reads them, then sh's arguments


def sh_path(native_folders):
    """Native folders joined by os.pathsep, as sh reads a PATH: a drive letter C: becomes /c and each separator a colon.
    Plain string handling, so no cygpath is needed. Git for Windows mounts drives under /c by default."""
    parts = []
    for folder in native_folders.split(os.pathsep):
        match = re.match(r"([A-Za-z]):(.*)$", folder)
        if match:
            folder = "/" + match.group(1).lower() + match.group(2)
        parts.append(folder.replace("\\", "/"))
    return ":".join(parts)


def sh_argv(path_dirs, *sh_args):
    """The argv that runs sh with `sh_args`. With `path_dirs` (native folders joined by os.pathsep), those folders lead PATH
    inside that sh. Off Windows, or with no folders, the argv is the plain one."""
    if path_dirs is None or not WINDOWS_LAUNCH:
        return [sh_exe(), *sh_args]
    return [sh_exe(), "-c", STUB_FIRST, "sh", sh_path(path_dirs), *sh_args]


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

    def put(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def add_agent_worktrees(self, count):
        for _ in range(count):
            self.made += 1
            path = os.path.join(self.primary, ".claude", "worktrees", "agent-s%03d" % self.made)
            vcs(self.primary, "worktree", "add", "-q", "--detach", "--no-checkout", path, "HEAD")

    def point_at(self, layout_json=None):
        """A pointer dir with lint/layout.py and layout.json, named by the config's CLAUDE.md. A second call rewrites
        the same files."""
        pointer = os.path.join(self.root, "pointer")
        os.makedirs(os.path.join(pointer, "lint"), exist_ok=True)
        for name in ("layout.py", "layout.json"):
            shutil.copy(os.path.join(HERE, "..", "lint", name), os.path.join(pointer, "lint", name))
        if layout_json is not None:
            with open(os.path.join(pointer, "lint", "layout.json"), "w", encoding="utf-8") as handle:
                handle.write(layout_json)
        with open(os.path.join(self.config, "CLAUDE.md"), "w", encoding="utf-8") as handle:
            handle.write("@%s/CLAUDE.md\n" % pointer.replace("\\", "/"))

    def hook_launch(self, remote=None, fetch_timeout="30", session_cwd=None, source=None, compact=False,
                    remote_session_id=None, path_dir=None, trace_file=None):
        """The hook's argv, environment, stdin payload and cwd, as the harness starts it. The arguments are run_hook's,
        and run_hook and the cut-off runs both start here, so the environment is built in one place."""
        where = self.primary if session_cwd is None else session_cwd
        # Forward slashes: the hook reads "cwd" with sed, and a doubled backslash is not a path.
        body = {"cwd": where.replace("\\", "/"), "session_id": SESSION}
        if source is not None:
            body["source"] = source
        payload = json.dumps(body, separators=(",", ":") if compact else None)
        env = dict(os.environ, CLAUDE_CONFIG_DIR=self.config, CLAUDE_SETTINGS_FETCH_TIMEOUT=fetch_timeout)
        if path_dir is not None:
            env["PATH"] = path_dir + os.pathsep + env.get("PATH", "")
        if trace_file is not None:
            env["GIT_TRACE"] = trace_file.replace("\\", "/")
        # The test runner may itself be a cloud session, so each run sets the variable it means.
        env.pop("CLAUDE_CODE_REMOTE", None)
        env.pop("CLAUDE_CODE_REMOTE_SESSION_ID", None)
        if remote is not None:
            env["CLAUDE_CODE_REMOTE"] = remote
        if remote_session_id is not None:
            env["CLAUDE_CODE_REMOTE_SESSION_ID"] = remote_session_id
        return sh_argv(path_dir, HOOK), env, payload, where

    def run_hook(self, remote=None, fetch_timeout="30", session_cwd=None, source=None, compact=False,
                 remote_session_id=None, path_dir=None, trace_file=None):
        """The hook's stdout lines. Its stderr lands in self.last_stderr.

        remote: the CLAUDE_CODE_REMOTE value, or None to unset it as a non-cloud runner does.
        remote_session_id: the CLAUDE_CODE_REMOTE_SESSION_ID value, "" for an empty one, or None to unset it.
        session_cwd: the session's cwd, in the payload and as the process cwd; None means the primary checkout.
        source: the payload's "source" (startup, resume, ...), or None to send none.
        compact: send the payload with no spaces after its separators, the way the hook's sed must also read it.
        path_dir: a folder put first on PATH, such as a git shim's folder, or None for the runner's own PATH.
        trace_file: a file git appends its own trace to (GIT_TRACE), or None for no trace.
        """
        argv, env, payload, where = self.hook_launch(remote=remote, fetch_timeout=fetch_timeout,
                                                     session_cwd=session_cwd, source=source, compact=compact,
                                                     remote_session_id=remote_session_id, path_dir=path_dir,
                                                     trace_file=trace_file)
        answer = subprocess.run(argv, input=payload, capture_output=True, text=True, env=env, cwd=where,
                                timeout=120)
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

    def role_lines(self, lines):
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
        expected = hook_role_line()
        lines = self.run_hook(remote="true")
        self.assertTrue(lines and lines[0].startswith("checkout "), "no checkout line first: %r" % lines)
        self.assertEqual(self.role_lines(lines), [expected])
        self.assertEqual(lines.index(expected), 1, "the tier line is not after the checkout line: %r" % lines)

    def test_no_tier_line_unless_the_variable_is_exactly_true(self):
        expected = hook_role_line()
        # None is a runner that never sets it; the rest are values the hook must not treat as cloud.
        for remote in (None, "", "false", "1", "TRUE"):
            with self.subTest(remote=remote):
                lines = self.run_hook(remote=remote)
                self.assertTrue(lines and lines[0].startswith("checkout "), "no checkout line: %r" % lines)
                self.assertEqual(self.role_lines(lines), [])
                self.assertNotIn(expected, lines)

    def test_the_tier_line_prints_with_no_remote_and_a_tiny_fetch_timeout(self):
        # The line needs no network, so a fetch bound too short for the bounded git calls still leaves it.
        lines = self.run_hook(remote="true", fetch_timeout="0.01")
        self.assertEqual(self.role_lines(lines), [hook_role_line()])

    def test_cloud_prints_the_tier_line_once_outside_any_git_tree(self):
        # The line needs no git, so a cloud session whose cwd is no checkout still gets it, with no stderr.
        outside = self.outside_a_git_tree()
        expected = hook_role_line()
        lines = self.run_hook(remote="true", session_cwd=outside)
        self.assertEqual(self.last_stderr, "", "the hook wrote to stderr: %r" % self.last_stderr)
        self.assertEqual(self.role_lines(lines), [expected], "the tier line is not printed once: %r" % lines)

    # A local lane session sets CLAUDE_CODE_REMOTE_SESSION_ID and not CLAUDE_CODE_REMOTE, so the id alone must print the line.
    def test_a_session_id_alone_prints_the_tier_line_in_a_git_tree(self):
        lines = self.run_hook(remote_session_id="cse_abc")
        self.assertTrue(lines and lines[0].startswith("checkout "), "no checkout line first: %r" % lines)
        self.assertEqual(self.role_lines(lines), [hook_role_line()],
                         "no tier line in a git tree with CLAUDE_CODE_REMOTE unset and a session id set: %r" % lines)

    def test_a_session_id_alone_prints_the_tier_line_outside_a_git_tree(self):
        outside = self.outside_a_git_tree()
        lines = self.run_hook(session_cwd=outside, remote_session_id="cse_abc")
        self.assertEqual(self.last_stderr, "", "the hook wrote to stderr: %r" % self.last_stderr)
        self.assertEqual(self.role_lines(lines), [hook_role_line()],
                         "no tier line outside a git tree with CLAUDE_CODE_REMOTE unset and a session id set: %r"
                         % lines)

    # Green controls: with neither variable set, or the id empty, the hook must print no tier line.
    def test_no_tier_line_with_both_variables_unset_in_a_git_tree(self):
        lines = self.run_hook()
        self.assertTrue(lines and lines[0].startswith("checkout "), "no checkout line first: %r" % lines)
        self.assertEqual(self.role_lines(lines), [], "a tier line printed with both variables unset: %r" % lines)

    def test_no_tier_line_with_both_variables_unset_outside_a_git_tree(self):
        outside = self.outside_a_git_tree()
        lines = self.run_hook(session_cwd=outside)
        self.assertEqual(self.last_stderr, "", "the hook wrote to stderr: %r" % self.last_stderr)
        self.assertEqual(self.role_lines(lines), [], "a tier line printed with both variables unset: %r" % lines)

    def test_no_tier_line_with_an_empty_session_id_in_a_git_tree(self):
        lines = self.run_hook(remote_session_id="")
        self.assertTrue(lines and lines[0].startswith("checkout "), "no checkout line first: %r" % lines)
        self.assertEqual(self.role_lines(lines), [], "a tier line printed with an empty session id: %r" % lines)


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

    # the heads a term binds to, the clause breaks and the other verbs that end a binding, and the session kinds (for the helpers below)
    SKIP_VERB = r"\bskip\w*"
    NAME_VERB = r"\b(?:names?|naming)\b"
    CLAUSE_BREAK = re.compile(r"[,;:.()]")
    OTHER_VERB = re.compile(r"\b(?:archiv\w*|runs?|names?|naming|reports?)\b", re.IGNORECASE)
    SESSION_KIND = re.compile(r"\b(?:sessions?|tiers?|coordinators?|solo|one-lanes?|lanes?)\b", re.IGNORECASE)

    @staticmethod
    def binds(sentence, head, term):
        """True when the head (a regex) comes before the term (a regex), with no clause break and no other verb between them."""
        found = re.search(term, sentence)
        if found is None:
            return False
        for hit in re.compile(head, re.IGNORECASE).finditer(sentence, 0, found.start()):
            between = sentence[hit.end():found.start()]
            if not SessionStartMergeRoleTests.CLAUSE_BREAK.search(between) and not SessionStartMergeRoleTests.OTHER_VERB.search(between):
                return True
        return False

    @staticmethod
    def archive_follows_get_session(sentence):
        """True when the archive comes after the get_session call: get_session first, or the archive set `after` its get_session."""
        get, archive = sentence.find("get_session"), sentence.find("archive")
        if get < 0 or archive < 0:
            return False
        if get < archive:
            return True
        return re.search(r"archiv\w*[^,;.()]*\bafter\b[^,;.()]*get_session", sentence) is not None

    @staticmethod
    def runner_subject_only(sentence):
        """True when the words before the verb `runs` name the batch runner tag and no other session kind."""
        verb = re.search(r"\bruns?\b", sentence)
        if verb is None:
            return False
        subject = sentence[:verb.start()]
        return "cs-build:batch-runner" in subject and len(SessionStartMergeRoleTests.SESSION_KIND.findall(subject)) == 1

    @staticmethod
    def idle_lanes_sentences(line):
        """The tier line's sentences that name the idle-lanes command, by its verb and flag."""
        return [s for s in sentences(line) if "merge --idle-lanes" in s]

    def idle_lanes_sentence(self):
        """The one sentence that names the idle-lanes command. Asserts that scope before any content."""
        found = self.idle_lanes_sentences(hook_role_line())
        self.assertEqual(len(found), 1, "expected one sentence naming merge --idle-lanes, found %d: %r" % (len(found), found))
        return found[0]

    def test_the_tier_line_names_the_role_writer(self):
        self.assertIn("merge --role", hook_role_line())

    def test_the_merge_role_sentence_names_the_command_by_its_home_path(self):
        # Bare `merge` is not on a cloud session's PATH, so the sentence gives the shim's full path.
        self.assertIn("~/.claude/bin/merge --role", merge_role_sentence(hook_role_line()))

    # decision session-tiers: re-pointed from both tiers to the batch runner alone
    def test_the_merge_role_sentence_names_only_the_batch_runner_tag(self):
        role = [s for s in sentences(hook_role_line()) if "merge role" in s.lower()]
        self.assertEqual(len(role), 1, role)
        self.assertIn("cs-build:batch-runner", role[0])
        self.assertNotIn("coordinator", role[0].lower(), role[0])

    # decision session-tiers: no sentence of the tier line says a coordinator merges; "never merges" is not a merge
    def test_no_sentence_of_the_tier_line_says_a_coordinator_merges(self):
        told = [s for s in sentences(hook_role_line()) if self.says_coordinator_merges(s)]
        self.assertEqual(told, [], "the tier line says a coordinator merges: %r" % told)

    # decision session-tiers: the coordinator never merges, so one sentence of the tier line says so
    def test_some_sentence_of_the_tier_line_says_the_coordinator_never_merges(self):
        told = [s for s in sentences(hook_role_line()) if self.says_coordinator_never_merges(s)]
        self.assertTrue(told, "no sentence of the tier line says the coordinator never merges")

    # decision session-tiers: a session the owner started (no parent) merges its own PR under the merge grant, affirmatively
    def test_a_session_with_no_parent_merges_its_own_pr_under_the_merge_grant(self):
        told = [s for s in sentences(hook_role_line()) if self.is_no_parent_merge(s)]
        self.assertTrue(told, "no affirmative sentence says a session with no parent merges its own PR under the merge grant")

    # decision session-tiers: only a solo or one-lane session the owner started merges its own PR, so its sentence names that shape
    def test_the_no_parent_merge_sentence_names_solo_or_one_lane(self):
        told = [s for s in sentences(hook_role_line()) if self.is_no_parent_merge(s)]
        self.assertTrue(told, "no affirmative sentence says a session with no parent merges its own PR under the merge grant")
        for sentence in told:
            self.assertIn("solo or one-lane", sentence, "the no-parent merge sentence does not name solo or one-lane: %r" % sentence)

    def hand_off_sentence(self):
        """The tier line's one sentence that hands a branch to the batch runner. Asserts that scope before any content."""
        found = [s for s in sentences(hook_role_line()) if "hands" in s and "batch runner" in s]
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
        sentence = merge_role_sentence(hook_role_line())
        self.assertIn("resume", sentence.lower(), sentence)

    def test_the_tier_line_does_not_say_once(self):
        self.assertNotRegex(hook_role_line(), r"(?i)\bonce\b")

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

    # batch-runner-start-names-idle-lanes: the scope comes first, so a missing sentence fails the scope, never passes empty
    def test_one_sentence_of_the_role_line_names_the_idle_lanes_command(self):
        found = self.idle_lanes_sentences(hook_role_line())
        self.assertEqual(len(found), 1, "expected one sentence naming merge --idle-lanes, found %d: %r" % (len(found), found))

    def test_the_idle_lanes_sentence_names_the_batch_runner_tag(self):
        sentence = self.idle_lanes_sentence()
        self.assertIn("cs-build:batch-runner", sentence, "the idle-lanes sentence names no cs-build:batch-runner tag: %r" % sentence)

    def test_the_idle_lanes_sentence_has_the_batch_runner_tag_as_its_only_subject(self):
        sentence = self.idle_lanes_sentence()
        self.assertTrue(self.runner_subject_only(sentence), "the words before `runs` do not name only the batch runner tag: %r" % sentence)

    def test_the_idle_lanes_sentence_does_not_name_the_coordinator(self):
        sentence = self.idle_lanes_sentence()
        self.assertNotIn("coordinator", sentence.lower(), "the idle-lanes sentence names the coordinator: %r" % sentence)

    def test_the_idle_lanes_sentence_does_not_name_a_lane(self):
        sentence = self.idle_lanes_sentence()
        self.assertFalse(self.names_a_lane(sentence),
                         "the idle-lanes sentence names a lane session or the cs-build:lane tag: %r" % sentence)

    def test_the_idle_lanes_command_is_named_by_its_home_path(self):
        # Bare `merge` is not on a cloud session's PATH, so the sentence gives the shim's full path, as the merge role sentence does.
        told = [s for s in sentences(hook_role_line()) if "~/.claude/bin/merge --idle-lanes --live FILE" in s]
        self.assertTrue(told, "no sentence names ~/.claude/bin/merge --idle-lanes --live FILE")

    def test_the_idle_lanes_sentence_says_to_run_it_after_each_merge(self):
        told = [s for s in self.idle_lanes_sentences(hook_role_line()) if re.search(r"after (?:each|every) merge", s, re.IGNORECASE)]
        self.assertTrue(told, "no sentence says to run merge --idle-lanes after each merge")

    def test_the_idle_lanes_sentence_says_to_run_get_session_on_each_listed_lane_alone(self):
        told = [s for s in self.idle_lanes_sentences(hook_role_line()) if self.binds(s, r"get_session", r"\balone\b")]
        self.assertTrue(told, "no sentence says to run get_session on each listed lane alone")

    def test_the_idle_lanes_sentence_says_to_archive_each_lane_after_its_get_session(self):
        told = [s for s in self.idle_lanes_sentences(hook_role_line()) if self.archive_follows_get_session(s)]
        self.assertTrue(told, "no sentence says to archive each lane after its get_session")

    def test_the_idle_lanes_sentence_says_to_skip_a_lane_with_a_hold_marker(self):
        told = [s for s in self.idle_lanes_sentences(hook_role_line()) if self.binds(s, self.SKIP_VERB, r"\bHOLD\b")]
        self.assertTrue(told, "no sentence says to skip a lane that carries a HOLD marker")

    def test_the_idle_lanes_sentence_says_to_skip_a_lane_that_needs_judgment(self):
        told = [s for s in self.idle_lanes_sentences(hook_role_line()) if self.binds(s, self.SKIP_VERB, r"\bjudgment\b")]
        self.assertTrue(told, "no sentence says to skip a lane that needs judgment")

    def test_the_idle_lanes_sentence_says_to_name_each_skipped_lane_in_its_report(self):
        told = [s for s in self.idle_lanes_sentences(hook_role_line())
                if self.binds(s, self.NAME_VERB, r"\bskipped\b") and self.binds(s, self.NAME_VERB, r"\breport\b")]
        self.assertTrue(told, "no sentence says to name each skipped lane in its report")

    def test_the_idle_lanes_sentence_names_the_livework_readme_that_builds_the_live_file(self):
        told = [s for s in self.idle_lanes_sentences(hook_role_line()) if "roadmap/livework/README.md" in s]
        self.assertTrue(told, "no idle-lanes sentence names roadmap/livework/README.md as the builder of the live file")

    def test_the_livework_readme_is_named_on_the_record_branch(self):
        told = [s for s in self.idle_lanes_sentences(hook_role_line())
                if "roadmap/livework/README.md" in s and "record branch" in s.lower()]
        self.assertTrue(told, "no idle-lanes sentence says roadmap/livework/README.md is on the record branch")

    # green controls (P2): the helpers pass on the current code, so a red above is the sentence, not a broken helper
    def test_the_binding_helper_binds_a_head_to_its_term_only_with_no_clause_break_or_verb_between(self):
        skip, name = self.SKIP_VERB, self.NAME_VERB
        self.assertTrue(self.binds("archives that lane, but skips any lane that shows a HOLD marker.", skip, r"\bHOLD\b"),
                        "a skip verb before HOLD in its clause is not read")
        self.assertFalse(self.binds("archives any lane that shows a HOLD marker, skipping nothing.", skip, r"\bHOLD\b"),
                         "a skip verb after a comma is read as governing HOLD")
        self.assertFalse(self.binds("archives any lane that shows a HOLD marker; skipped lanes are named in its report.", skip, r"\bHOLD\b"),
                         "a skip verb after HOLD is read as governing it")
        self.assertFalse(self.binds("skips any lane that shows a HOLD marker or archives any lane that needs judgment.", skip,
                                    r"\bjudgment\b"), "an archive verb between skip and judgment is not blocked")
        self.assertTrue(self.binds("names each skipped lane in its report.", name, r"\bskipped\b"),
                        "a name verb before skipped is not read")
        self.assertFalse(self.binds("archives each listed lane, but skips each one in its report.", name, r"\breport\b"),
                         "a report with no name verb is read as named")
        self.assertTrue(self.binds("runs get_session alone on each listed lane.", r"get_session", r"\balone\b"),
                        "alone right after get_session is not read")
        self.assertFalse(self.binds("runs get_session on each listed lane, and archives that lane; "
                                    "names each skipped lane alone in its report.", r"get_session", r"\balone\b"),
                         "an alone after a comma in the report is read as the get_session one")

    def test_the_archive_order_helper_takes_both_allowed_wordings_and_rejects_archive_first(self):
        self.assertTrue(self.archive_follows_get_session("runs get_session on each listed lane alone and archives that lane."),
                        "archive after get_session is not read")
        self.assertTrue(self.archive_follows_get_session("archives each lane after its get_session."),
                        "archive set after its get_session is not read")
        self.assertFalse(self.archive_follows_get_session("archives that lane, then runs get_session on it."),
                         "archive before get_session is read as in order")
        self.assertFalse(self.archive_follows_get_session("archives each lane and runs get_session on it."),
                         "archive before get_session with no after is read as in order")

    def test_the_runner_subject_helper_passes_one_runner_subject_and_rejects_a_second_one(self):
        self.assertTrue(self.runner_subject_only("A session tagged cs-build:batch-runner, and no other, runs `x`."),
                        "the one batch runner subject is rejected")
        self.assertFalse(self.runner_subject_only("A session tagged cs-build:batch-runner, and any session, runs `x`."),
                         "a second session subject is accepted")
        self.assertFalse(self.runner_subject_only("A session tagged cs-build:batch-runner, and a solo session does too, runs `x`."),
                         "a solo session subject is accepted")


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


# The standing-grant check (rule grants-read-from-main). The hook compares the committed blobs of CLAUDE.md and
# .claude/CLAUDE.md at HEAD with origin/main's, and prints the lines these tests pin. The texts are stand-ins: the
# hook compares blob shas and never reads the words.
GRANT_FILES = ("CLAUDE.md", ".claude/CLAUDE.md")
GRANT_STALE = "# stale grants: the acts an old checkout held\n"
GRANT_FRESH = "# fresh grants: the acts origin/main holds\n"
GRANT_STALE_DOT = "# stale copy under .claude\n"
GRANT_FRESH_DOT = "# fresh copy under .claude\n"
GRANT_TRUNK = "# trunk grants: the acts origin/trunk holds\n"
GRANT_WORD = re.compile(r"standing grant")
GRANT_UNKNOWN = re.compile(r"^checkout .+: standing grant check unknown, neither origin/main nor origin/HEAD "
                           r"could be read$")
GIT_STARTS_LOG = "git-starts.log"
GIT_TRACE_LOG = "git-trace.log"
STUB_LOG = "stub-calls.log"  # each git call a PATH stub received, written by the stub before it acts


def log_lines(path):
    """The non-blank lines of a log a stub or a shim wrote, or [] when no log exists because nothing ran."""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return [entry.strip() for entry in handle if entry.strip()]


def grant_text(tag, count):
    """A grant file of `count` lines: the full-size state."""
    return "".join("%s grant line %d\n" % (tag, number) for number in range(count))


def differ_line(rel, ref):
    """The one line a grant file prints when it differs from `ref`. Group 1 is the ref's short sha."""
    return re.compile(r"^checkout .+: %s differs from %s at ([0-9a-f]{7,40}); read the standing grants with git show "
                      r"%s:%s$" % (re.escape(rel), re.escape(ref), re.escape(ref), re.escape(rel)))


# The ruled store's reads (lint/ruled_store.py) start `git -C <repo> ls-tree ... roadmap/rulings` and `git -C <repo>
# cat-file --batch`. The grant check's starts never carry -C, so a -C ls-tree or cat-file is the store's, not the check's.
STORE_READ = re.compile(r"^-C .* (ls-tree|cat-file)\b")


def names_the_grant_check(argv):
    """True when a git start is one the grant check makes: it names a grant file, an origin ref, or a stdin read.
    The hook's own default-branch read (symbolic-ref, which names origin/HEAD) runs before the check, so it is not
    counted. Neither is a ruled-store read (STORE_READ)."""
    if argv.split()[0] == "symbolic-ref" or STORE_READ.match(argv):
        return False
    return any(part in argv for part in ("CLAUDE.md", "origin", "--batch", "--stdin"))


class GrantFilterTests(unittest.TestCase):
    """names_the_grant_check counts the grant check's git starts only. The ruled store's reads (lint/ruled_store.py, run
    as git -C <repo>) are not the grant check's, so they are not counted."""

    def test_a_ruled_store_read_is_not_a_grant_check_start(self):
        for start in ("-C /tmp/repo ls-tree -z --name-only origin/roadmap roadmap/rulings/",
                      "-C /tmp/repo cat-file --batch"):
            with self.subTest(start=start):
                self.assertFalse(names_the_grant_check(start),
                                 "a ruled-store read is counted as a grant-check start: %r" % start)

    def test_a_grant_read_is_still_a_grant_check_start(self):
        for start in ("show origin/main:CLAUDE.md",
                      "rev-list --left-right --count refs/heads/main...refs/remotes/origin/main"):
            with self.subTest(start=start):
                self.assertTrue(names_the_grant_check(start),
                                "a grant-check read is not counted: %r" % start)


class GitFixtureMixin:
    """Fixture helpers for a checkout with a local origin: refs, grant files, the hook run, the git starts the run
    makes (read from a PATH shim's log), and the checkout's file snapshot. The grant and fetch classes share them."""

    # Fixture helpers. Every ref and commit lives in self.primary, the checkout the hook reads.

    def head_sha(self):
        return vcs(self.primary, "rev-parse", "HEAD").stdout.strip()

    def resolve(self, rev):
        """The sha `rev` names, or None when it does not resolve."""
        answer = subprocess.run([VCS, "-C", self.primary, "rev-parse", "-q", "--verify", rev],
                                capture_output=True, text=True, timeout=60)
        return answer.stdout.strip() if answer.returncode == 0 else None

    def blob(self, rev, rel):
        """The blob sha of `rel` at `rev`, or None when the path is absent there."""
        return self.resolve("%s:%s" % (rev, rel))

    def set_grants(self, claude_md, dot_claude_md):
        """Writes each grant file in the primary checkout and stages it past .gitignore. None removes the file."""
        for rel, text in zip(GRANT_FILES, (claude_md, dot_claude_md)):
            path = os.path.join(self.primary, *rel.split("/"))
            if text is None:
                if os.path.exists(path):
                    os.remove(path)
                vcs(self.primary, "rm", "-q", "--cached", "--ignore-unmatch", "--", rel)
            else:
                self.put(path, text)
                vcs(self.primary, "add", "-f", "--", rel)

    def commit(self, message):
        vcs(self.primary, "commit", "-q", "--allow-empty", "-m", message)

    def tip_with(self, claude_md, dot_claude_md):
        """The sha of a commit on top of HEAD that holds these grant files and a changed f.txt. It is made on a side
        branch, so HEAD and the checkout end where they began."""
        side = "grants-side-tip"
        vcs(self.primary, "checkout", "-q", "-b", side)
        try:
            self.put(os.path.join(self.primary, "f.txt"), "tip\n")
            vcs(self.primary, "add", "--", "f.txt")
            self.set_grants(claude_md, dot_claude_md)
            self.commit("grants at the tip")
            return self.head_sha()
        finally:
            vcs(self.primary, "checkout", "-q", "main")
            vcs(self.primary, "branch", "-q", "-D", side)

    def point_origin_main(self, sha):
        vcs(self.primary, "update-ref", "refs/remotes/origin/main", sha)

    def point_origin_head_at(self, sha):
        """origin/HEAD names origin/trunk, which sits at `sha`. origin/main is left as it was."""
        vcs(self.primary, "update-ref", "refs/remotes/origin/trunk", sha)
        vcs(self.primary, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")

    def run_checked(self, session_cwd=None, path_dir=None, fetch_timeout="30", trace_file=None):
        """The hook's lines, after a control: the hook ran and printed its checkout line."""
        lines = self.run_hook(session_cwd=session_cwd, path_dir=path_dir, fetch_timeout=fetch_timeout,
                              trace_file=trace_file)
        self.assertTrue(any(line.startswith("checkout ") for line in lines),
                        "the hook printed no checkout line: %r" % lines)
        return lines

    @staticmethod
    def grant_lines_of(lines):
        return [line for line in lines if GRANT_WORD.search(line)]

    def assert_one_differ_line(self, lines, rel, ref, tip):
        """Exactly one grant line: the line for `rel` against `ref`, whose short sha is a prefix of `tip`."""
        grant = self.grant_lines_of(lines)
        self.assertEqual(len(grant), 1, "want one grant line for %s, got %r" % (rel, grant))
        found = differ_line(rel, ref).match(grant[0])
        self.assertIsNotNone(found, "the grant line is not the %s line against %s: %r" % (rel, ref, grant[0]))
        self.assertTrue(tip.startswith(found.group(1)),
                        "the line's sha %s is not a prefix of %s, the tip of %s: %r"
                        % (found.group(1), tip, ref, grant[0]))

    def make_git_shim(self):
        """A folder whose `git` appends its arguments to git-starts.log under the run root, then runs the real git."""
        real = shutil.which("git")
        folder = os.path.join(self.root, "shim")
        os.makedirs(folder)
        log = os.path.join(self.root, GIT_STARTS_LOG)
        script = os.path.join(folder, "git")
        with open(script, "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\nprintf '%%s\\n' \"$*\" >> \"%s\"\nexec \"%s\" \"$@\"\n" % (log, real))
        os.chmod(script, 0o755)
        return folder

    def run_logged(self, session_cwd=None):
        """The hook's lines, and each git start it made, read back from the log of the shim on its PATH."""
        if getattr(self, "shim_folder", None) is None:
            self.shim_folder = self.make_git_shim()
        log = os.path.join(self.root, GIT_STARTS_LOG)
        if os.path.exists(log):
            os.remove(log)
        lines = self.run_checked(session_cwd=session_cwd, path_dir=self.shim_folder)
        return lines, log_lines(log)

    def run_traced(self, session_cwd=None, fetch_timeout="30"):
        """The hook's lines, and each git start the run made, read from git's own trace (GIT_TRACE). A PATH shim does not
        run on every platform; git writes its trace itself, the same way everywhere. Each start is git's argv without
        the leading `git`, so the fetch checks read it as they read a shim's log."""
        trace = os.path.join(self.root, GIT_TRACE_LOG)
        if os.path.exists(trace):
            os.remove(trace)
        lines = self.run_checked(session_cwd=session_cwd, fetch_timeout=fetch_timeout, trace_file=trace)
        starts = []
        if os.path.exists(trace):
            with open(trace, encoding="utf-8") as handle:
                for entry in handle:
                    if "built-in: git " in entry:
                        starts.append(entry.split("built-in: git ", 1)[1].strip())
        return lines, starts

    def make_git_stub(self, name, body):
        """A folder, named `name` under the run root, whose `git` logs its arguments to STUB_LOG in that folder, runs the
        shell `body` and then the real git with the same arguments. A body that exits ends the call with its status.
        Every git stub on PATH is built here. The file is written LF, with forward-slash paths, so sh reads it on Windows."""
        real = shutil.which("git").replace("\\", "/")
        folder = os.path.join(self.root, name)
        os.makedirs(folder)
        log = os.path.join(folder, STUB_LOG).replace("\\", "/")
        script = os.path.join(folder, "git")
        with open(script, "w", encoding="utf-8", newline="\n") as handle:
            handle.write('#!/bin/sh\nprintf "%%s\\n" "$*" >> "%s"\n%s\nexec "%s" "$@"\n' % (log, body, real))
        os.chmod(script, 0o755)
        return folder

    def stub_starts(self, folder):
        """Each git call the stub in `folder` received, as its argv without the leading git. Empty when it never ran."""
        return log_lines(os.path.join(folder, STUB_LOG))

    def assert_stub_reached(self, folder, command, must_name=""):
        """Scope before subject: the stub in `folder` ran for git `command`, with `must_name` in its argv when given. The
        assertions after this one test the stub's effect, so a bypassed stub fails here, as this one cause, never as a
        wrong count. How sh resolves git is read only when the check fails."""
        starts = self.stub_starts(folder)
        if any(start.split()[0] == command and must_name in start for start in starts):
            return
        _argv, env, _payload, where = self.hook_launch(path_dir=folder)
        # The same launch as the hook's, so a stub that is still bypassed shows here.
        answer = subprocess.run(sh_argv(folder, "-c", 'command -v git; printf "%s\\n" "$PATH"'), capture_output=True,
                                text=True, env=env, cwd=where, timeout=60)
        wanted = " ".join(part for part in (command, must_name) if part)
        self.fail("the git stub was not reached: no logged call matches git %s (logged: %r); sh with this PATH "
                  "resolves git to: %r" % (wanted, starts, (answer.stdout + answer.stderr).strip()))

    def make_fetch_killed_shim(self):
        """A folder whose `git` exits 143 for `fetch`, the status of a git that SIGTERM ended, and runs the real git for
        every other call. The refresh fails as a killed refresh does, with no timer involved."""
        return self.make_git_stub("fetch-killed-shim", 'if [ "$1" = fetch ]; then exit 143; fi')

    def run_to_slow_step(self, path_dir=None):
        """The hook's stdout lines kept when its slow step is cut off, and whether the step was reached.

        The slow step is the caution call, the hook's first python3 start, which runs before the grant block on main.
        A shim stands in for python3: at that call it writes one line down a pipe the hook inherits, then sleeps. This
        reads the line, then ends the hook's own process group. The output printed before the step is kept and the
        rest is dropped, as a killed hook loses its later output. No clock decides the cut: it lands at the step. EOF
        before the line means the hook ended without reaching the step, so reached is False.
        """
        self.point_at()
        folder = os.path.join(self.root, "slow-step")
        os.makedirs(folder)
        marker_read, marker_write = os.pipe()
        shim = os.path.join(folder, "python3")
        with open(shim, "w", encoding="utf-8") as handle:
            handle.write("\n".join([
                "#!/bin/sh",
                'case "$*" in',
                "  */lint/layout.py\\ caution*)",
                "    printf 'reached\\n' >&%d" % marker_write,
                "    sleep 600",
                "    ;;",
                '  *) exec "%s" "$@" ;;' % sys.executable,
                "esac",
            ]) + "\n")
        os.chmod(shim, 0o755)
        search = folder if path_dir is None else os.pathsep.join([folder, path_dir])
        argv, env, payload, where = self.hook_launch(path_dir=search)
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env=env, cwd=where, start_new_session=True, pass_fds=(marker_write,), text=True)
        os.close(marker_write)
        marker = os.fdopen(marker_read, encoding="utf-8")
        reached = False
        try:
            proc.stdin.write(payload)
            proc.stdin.close()
            # Python 3.11 and 3.12 flush stdin inside communicate() without guarding a closed file, so the drain
            # below must not see it. None skips that flush; the drain reads only stdout and stderr.
            proc.stdin = None
            if select.select([marker], [], [], HOOK_WAIT)[0]:
                reached = marker.readline() == "reached\n"
        finally:
            marker.close()
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        out, err = proc.communicate(timeout=HOOK_WAIT)
        self.last_stderr = err
        return out.splitlines(), reached

    def assert_grant_check_is_cheap(self):
        """The grant check starts at most two git processes that name a grant or origin, and no git fetch runs.
        The notice is asserted first, so the count is taken on a run that made the check."""
        lines, starts = self.run_logged()
        self.assertTrue(self.grant_lines_of(lines), "no grant line, so the check did not run: %r" % lines)
        named = [start for start in starts if names_the_grant_check(start)]
        self.assertLessEqual(len(named), 2, "the grant check starts %d git processes, want at most 2; all git starts: %r"
                             % (len(named), starts))
        fetches = [start for start in starts if start.split()[0] == "fetch"]
        self.assertEqual(fetches, [], "the hook starts git fetch: %r" % fetches)

    def snapshot(self):
        """Each file under the primary checkout, .git included, as (size, mtime_ns, sha-256), keyed by its path.
        .git/index is left out: git status rewrites its stat cache on its own while an entry is racy (written in the
        same second as the file), which is git's bookkeeping, not a write the grant check makes."""
        found = {}
        for dirpath, _dirs, names in os.walk(self.primary):
            for name in names:
                path = os.path.join(dirpath, name)
                rel = os.path.relpath(path, self.primary)
                if rel == os.path.join(".git", "index"):
                    continue
                with open(path, "rb") as handle:
                    body = handle.read()
                info = os.stat(path)
                found[rel] = (info.st_size, info.st_mtime_ns, hashlib.sha256(body).hexdigest())
        return found


class SessionStartGrantsFromMainTests(GitFixtureMixin, SessionStartAgentWorktreeNoticeTests):
    """Rule grants-read-from-main. A session that cites a standing grant reads it from origin/main. The hook prints one
    line per grant file whose HEAD blob differs from origin/main's, or that sits on one side only. origin/HEAD's target
    stands in when origin/main is absent. One unknown line prints when neither ref can be read. Otherwise silent.
    Incident: a coordinator read the grants from a stale checkout."""

    # The 51-worktree case builds 51 worktrees; this class does not repeat it.
    test_no_notice_at_fifty_and_one_notice_at_fifty_one = None

    def setUp(self):
        super().setUp()
        # HEAD starts on the stale grants, as the incident's checkout did. No origin ref exists until a test makes one.
        self.set_grants(GRANT_STALE, GRANT_STALE_DOT)
        self.commit("stale grants")
        self.shim_folder = None

    # Blob comparison. A grant file that differs, or sits on one side only, prints its line.

    def test_equal_blobs_on_a_newer_commit_print_no_grant_line(self):
        # Control: origin/main is a newer commit whose grant blobs equal HEAD's, so only a blob compare stays silent.
        origin = self.tip_with(GRANT_STALE, GRANT_STALE_DOT)
        self.point_origin_main(origin)
        self.assertNotEqual(self.head_sha(), origin, "scope: origin/main is HEAD itself")
        for rel in GRANT_FILES:
            self.assertIsNotNone(self.blob("HEAD", rel), "scope: HEAD has no %s" % rel)
            self.assertEqual(self.blob("HEAD", rel), self.blob("origin/main", rel), "scope: %s differs" % rel)
        self.assertEqual(self.grant_lines_of(self.run_checked()), [], "a grant line printed for equal blobs")

    def test_a_stale_root_claude_md_prints_one_line_naming_it(self):
        self.point_origin_main(self.tip_with(GRANT_FRESH, GRANT_STALE_DOT))
        self.assertNotEqual(self.blob("HEAD", "CLAUDE.md"), self.blob("origin/main", "CLAUDE.md"),
                            "scope: the root CLAUDE.md does not differ")
        self.assertEqual(self.blob("HEAD", ".claude/CLAUDE.md"), self.blob("origin/main", ".claude/CLAUDE.md"),
                         "scope: the .claude copy differs")
        self.assert_one_differ_line(self.run_checked(), "CLAUDE.md", "origin/main", self.resolve("origin/main"))

    def test_a_stale_dot_claude_md_prints_one_line_naming_it(self):
        self.point_origin_main(self.tip_with(GRANT_STALE, GRANT_FRESH_DOT))
        self.assertNotEqual(self.blob("HEAD", ".claude/CLAUDE.md"), self.blob("origin/main", ".claude/CLAUDE.md"),
                            "scope: the .claude copy does not differ")
        self.assertEqual(self.blob("HEAD", "CLAUDE.md"), self.blob("origin/main", "CLAUDE.md"),
                         "scope: the root CLAUDE.md differs")
        self.assert_one_differ_line(self.run_checked(), ".claude/CLAUDE.md", "origin/main", self.resolve("origin/main"))

    def test_both_files_differing_at_full_size_print_one_line_each(self):
        big = grant_text("stale", 2000)
        self.set_grants(big, big)
        self.commit("full-size grants")
        fresh = grant_text("fresh", 2000)
        self.point_origin_main(self.tip_with(fresh, fresh))
        for rel in GRANT_FILES:
            self.assertNotEqual(self.blob("HEAD", rel), self.blob("origin/main", rel), "scope: %s does not differ" % rel)
        grant = self.grant_lines_of(self.run_checked())
        self.assertEqual(len(grant), 2, "want one grant line per file, got %r" % grant)
        for rel in GRANT_FILES:
            matched = [line for line in grant if differ_line(rel, "origin/main").match(line)]
            self.assertEqual(len(matched), 1, "want one line for %s, got %r" % (rel, grant))

    def test_a_root_claude_md_missing_on_origin_main_prints_its_line(self):
        self.point_origin_main(self.tip_with(None, GRANT_STALE_DOT))
        self.assertIsNotNone(self.blob("HEAD", "CLAUDE.md"), "scope: HEAD has no CLAUDE.md")
        self.assertIsNone(self.blob("origin/main", "CLAUDE.md"), "scope: origin/main still has CLAUDE.md")
        self.assert_one_differ_line(self.run_checked(), "CLAUDE.md", "origin/main", self.resolve("origin/main"))

    def test_a_root_claude_md_missing_at_head_prints_its_line(self):
        self.set_grants(None, GRANT_STALE_DOT)
        self.commit("no root grants")
        self.point_origin_main(self.tip_with(GRANT_FRESH, GRANT_STALE_DOT))
        self.assertIsNone(self.blob("HEAD", "CLAUDE.md"), "scope: HEAD still has CLAUDE.md")
        self.assertIsNotNone(self.blob("origin/main", "CLAUDE.md"), "scope: origin/main has no CLAUDE.md")
        self.assert_one_differ_line(self.run_checked(), "CLAUDE.md", "origin/main", self.resolve("origin/main"))

    def test_neither_file_on_either_side_prints_no_grant_line(self):
        self.set_grants(None, None)
        self.commit("no grants")
        self.point_origin_main(self.tip_with(None, None))
        self.assertIsNotNone(self.resolve("origin/main"), "scope: origin/main does not resolve")
        for rel in GRANT_FILES:
            self.assertIsNone(self.blob("HEAD", rel), "scope: HEAD has %s" % rel)
            self.assertIsNone(self.blob("origin/main", rel), "scope: origin/main has %s" % rel)
        self.assertEqual(self.grant_lines_of(self.run_checked()), [], "a grant line printed with neither file present")

    def test_uncommitted_grant_edits_print_no_grant_line(self):
        self.point_origin_main(self.head_sha())
        self.put(os.path.join(self.primary, "CLAUDE.md"), GRANT_FRESH)
        with open(os.path.join(self.primary, "CLAUDE.md"), encoding="utf-8") as handle:
            self.assertEqual(handle.read(), GRANT_FRESH, "scope: the working copy was not edited")
        self.assertEqual(self.blob("HEAD", "CLAUDE.md"), self.blob("origin/main", "CLAUDE.md"),
                         "scope: the committed CLAUDE.md differs")
        self.assertEqual(self.grant_lines_of(self.run_checked()), [], "a grant line printed for an uncommitted edit")

    # Refs. The ref the check reads, origin/main or origin/HEAD's target, and what it says when neither reads.

    def test_no_origin_main_and_no_origin_head_prints_one_unknown_line(self):
        # A grant file at HEAD is something to cite, and no ref is there to read it against: the one unknown case.
        self.assertIsNone(self.resolve("origin/main"), "scope: origin/main resolves")
        self.assertIsNone(self.resolve("origin/HEAD"), "scope: origin/HEAD resolves")
        self.assertTrue(any(self.blob("HEAD", rel) for rel in GRANT_FILES), "scope: HEAD holds no grant file")
        grant = self.grant_lines_of(self.run_checked())
        self.assertEqual(len(grant), 1, "want one unknown line, got %r" % grant)
        self.assertRegex(grant[0], GRANT_UNKNOWN, "the line is not the unknown line: %r" % grant[0])

    def test_no_grant_file_at_head_and_no_origin_ref_prints_no_grant_line(self):
        # Control: nothing to cite and no ref to read it against, so the check stays silent rather than unknown.
        self.set_grants(None, None)
        self.commit("no grants")
        self.assertIsNone(self.resolve("origin/main"), "scope: origin/main resolves")
        self.assertIsNone(self.resolve("origin/HEAD"), "scope: origin/HEAD resolves")
        for rel in GRANT_FILES:
            self.assertIsNone(self.blob("HEAD", rel), "scope: HEAD has %s" % rel)
        self.assertEqual(self.grant_lines_of(self.run_checked()), [],
                         "an unknown line printed with no grant file at HEAD")

    def test_origin_head_target_is_read_when_origin_main_is_absent(self):
        trunk = self.tip_with(GRANT_FRESH, GRANT_STALE_DOT)
        self.point_origin_head_at(trunk)
        self.assertIsNone(self.resolve("origin/main"), "scope: origin/main resolves")
        self.assertEqual(self.resolve("origin/HEAD"), trunk, "scope: origin/HEAD is not the trunk tip")
        self.assertNotEqual(self.blob("HEAD", "CLAUDE.md"), self.blob("origin/HEAD", "CLAUDE.md"),
                            "scope: CLAUDE.md does not differ from the trunk tip")
        self.assert_one_differ_line(self.run_checked(), "CLAUDE.md", "origin/trunk", trunk)

    def test_origin_main_is_read_before_origin_head(self):
        main = self.tip_with(GRANT_FRESH, GRANT_STALE_DOT)
        self.point_origin_main(main)
        self.point_origin_head_at(self.head_sha())
        self.assertEqual(self.blob("HEAD", "CLAUDE.md"), self.blob("origin/HEAD", "CLAUDE.md"),
                         "scope: origin/HEAD's CLAUDE.md differs from HEAD")
        self.assertNotEqual(self.blob("HEAD", "CLAUDE.md"), self.blob("origin/main", "CLAUDE.md"),
                            "scope: origin/main's CLAUDE.md does not differ")
        self.assert_one_differ_line(self.run_checked(), "CLAUDE.md", "origin/main", main)

    def test_origin_head_alone_prints_no_grant_line_while_origin_main_matches(self):
        self.point_origin_main(self.head_sha())
        self.point_origin_head_at(self.tip_with(GRANT_FRESH, GRANT_FRESH_DOT))
        self.assertNotEqual(self.blob("HEAD", "CLAUDE.md"), self.blob("origin/HEAD", "CLAUDE.md"),
                            "scope: origin/HEAD's CLAUDE.md does not differ")
        for rel in GRANT_FILES:
            self.assertEqual(self.blob("HEAD", rel), self.blob("origin/main", rel), "scope: origin/main's %s differs" % rel)
        self.assertEqual(self.grant_lines_of(self.run_checked()), [],
                         "origin/HEAD's target was read while origin/main matched")

    # Where the check runs, and the line's sha.

    def test_a_session_in_a_subfolder_reads_the_toplevel_grants(self):
        self.point_origin_main(self.tip_with(GRANT_FRESH, GRANT_STALE_DOT))
        sub = os.path.join(self.primary, "sub")
        os.makedirs(sub)
        self.assert_one_differ_line(self.run_checked(session_cwd=sub), "CLAUDE.md", "origin/main",
                                    self.resolve("origin/main"))

    def test_a_linked_worktree_session_compares_its_own_head(self):
        self.point_origin_main(self.tip_with(GRANT_FRESH, GRANT_STALE_DOT))
        linked = os.path.join(self.primary, ".claude", "worktrees", "agent-grants")
        vcs(self.primary, "worktree", "add", "-q", "--detach", linked, "HEAD")
        self.assertEqual(vcs(linked, "rev-parse", "HEAD").stdout.strip(), self.head_sha(),
                         "scope: the linked worktree is not at HEAD")
        self.assert_one_differ_line(self.run_checked(session_cwd=linked), "CLAUDE.md", "origin/main",
                                    self.resolve("origin/main"))

    # Cost: at most two git starts for the check, no fetch, no file written. Each cost case first asserts its
    # grant line, so a run that never made the check cannot pass on a low count.

    @unittest.skipIf(os.name == "nt", "the git shim is a POSIX sh script")
    def test_the_grant_check_starts_at_most_two_git_processes_when_origin_main_differs(self):
        self.point_origin_main(self.tip_with(GRANT_FRESH, GRANT_STALE_DOT))
        fixture.set_fetch_head(self.primary)
        self.assert_grant_check_is_cheap()

    @unittest.skipIf(os.name == "nt", "the git shim is a POSIX sh script")
    def test_the_grant_check_starts_at_most_two_git_processes_when_only_origin_head_is_readable(self):
        self.point_origin_head_at(self.tip_with(GRANT_FRESH, GRANT_STALE_DOT))
        fixture.set_fetch_head(self.primary)
        self.assert_grant_check_is_cheap()

    @unittest.skipIf(os.name == "nt", "the git shim is a POSIX sh script")
    def test_the_grant_check_starts_at_most_two_git_processes_when_no_origin_ref_is_readable(self):
        fixture.set_fetch_head(self.primary)
        self.assert_grant_check_is_cheap()

    def test_the_grant_check_writes_no_file_in_the_checkout_or_git_dir(self):
        self.point_origin_main(self.tip_with(GRANT_FRESH, GRANT_STALE_DOT))
        before = self.snapshot()
        lines = self.run_checked()
        after = self.snapshot()
        self.assertTrue(self.grant_lines_of(lines), "no grant line, so the check did not run: %r" % lines)
        changed = sorted(name for name in set(before) | set(after) if before.get(name) != after.get(name))
        self.assertEqual(changed, [], "the hook wrote or changed files: %r" % changed)


# The fetch half of rule grants-read-from-main. A refresh that fails leaves its grant line marked unrefreshed; the
# local main line counts behind and ahead against origin/main; a refresh that did not run says so.
REFRESH_FAILED = re.compile(r"^checkout .+: the origin fetch did not run, so origin refs may be stale; freshness unknown$")
UNREFRESHED = re.compile(r"^checkout .+: CLAUDE\.md differs from origin/main at ([0-9a-f]{7,40}); read the standing "
                         r"grants with git show origin/main:CLAUDE\.md; origin/main is unrefreshed$")
LOCAL_MAIN = re.compile(r"^checkout .+: local main is (\d+) commits? behind origin/main(?: and (\d+) commits? ahead)?$")
DEFAULT_BEHIND = re.compile(r"^checkout .+: main is (\d+) commits behind origin/main; pull before you read it$")


class SessionStartFetchTests(GitFixtureMixin, SessionStartAgentWorktreeNoticeTests):
    """Rule grants-read-from-main, fetch half. The session start refreshes origin/main with one `git fetch --quiet
    --no-tags origin` whose refspecs name that ref, and origin/HEAD's target when that is another branch. It runs on
    any branch, before the grants compare, and never prunes all of origin. A refresh that fails says so. Local main is
    compared with origin/main and never moved. Incident: a lane read a stale origin/main, so two stale copies of main
    were compared."""

    # The 51-worktree case builds 51 worktrees; this class does not repeat it.
    test_no_notice_at_fifty_and_one_notice_at_fifty_one = None

    def setUp(self):
        super().setUp()
        self.origin_repo = os.path.join(self.root, "origin.git")
        vcs(self.root, "init", "-q", "--bare", "-b", "main", "origin.git")
        vcs(self.primary, "remote", "add", "origin", self.origin_repo)
        self.set_grants(GRANT_STALE, GRANT_STALE_DOT)
        self.commit("stale grants")
        vcs(self.primary, "push", "-q", "origin", "main")

    def advance_origin_main(self, commits=1):
        """Another clone pushes `commits` commits to origin's main; the first carries fresh grants. The primary checkout
        does not fetch them. Returns the new tip's sha."""
        other = os.path.join(self.root, "other")
        vcs(self.root, "clone", "-q", self.origin_repo, other)
        self.put(os.path.join(other, "CLAUDE.md"), GRANT_FRESH)
        self.put(os.path.join(other, ".claude", "CLAUDE.md"), GRANT_STALE_DOT)
        vcs(other, "add", "-f", "--", "CLAUDE.md", ".claude/CLAUDE.md")
        vcs(other, "commit", "-q", "-m", "fresh grants at origin")
        for number in range(2, commits + 1):
            vcs(other, "commit", "-q", "--allow-empty", "-m", "origin commit %d" % number)
        vcs(other, "push", "-q", "origin", "HEAD:main")
        return vcs(other, "rev-parse", "HEAD").stdout.strip()

    def checkout_lane(self):
        vcs(self.primary, "checkout", "-q", "-b", "lane-x")

    @staticmethod
    def fetch_starts(starts):
        return [start for start in starts if start.split()[0] == "fetch"]

    @staticmethod
    def ls_remote_starts(starts):
        return [start for start in starts if start.split()[0] == "ls-remote"]

    def assert_one_origin_main_fetch(self, starts, branch=None):
        """Exactly one git fetch: quiet and untagged, origin first among its names, and refspecs for origin/main alone,
        plus one for `branch` when origin/HEAD names another branch. It never prunes and names no wildcard. Flag order
        is not pinned."""
        fetches = self.fetch_starts(starts)
        self.assertEqual(len(fetches), 1, "want one git fetch at session start, got %r" % starts)
        tokens = fetches[0].split()
        flags = {token for token in tokens[1:] if token.startswith("-")}
        names = [token for token in tokens[1:] if not token.startswith("-")]
        self.assertNotIn("--prune", flags, "the fetch prunes all of origin: %r" % fetches[0])
        self.assertEqual(flags, {"--quiet", "--no-tags"},
                         "the fetch's flags are not --quiet and --no-tags: %r" % fetches[0])
        self.assertEqual(names[:1], ["origin"], "the fetch does not name origin first: %r" % fetches[0])
        refspecs = names[1:]
        self.assertEqual([token for token in refspecs if "*" in token], [],
                         "the fetch names a wildcard refspec: %r" % fetches[0])
        want = ["+refs/heads/main:refs/remotes/origin/main"]
        if branch is not None:
            want.append("+refs/heads/%s:refs/remotes/origin/%s" % (branch, branch))
        self.assertEqual(sorted(refspecs), sorted(want),
                         "the fetch's refspecs are not the one-ref set: %r" % fetches[0])

    def assert_local_main_line(self, lines, behind, ahead):
        found = [line for line in lines if LOCAL_MAIN.match(line)]
        self.assertEqual(len(found), 1, "want one local main line, got %r" % lines)
        match = LOCAL_MAIN.match(found[0])
        self.assertEqual(match.group(1), behind, "the behind count is wrong: %r" % found[0])
        self.assertEqual(match.group(2), ahead, "the ahead count is wrong: %r" % found[0])

    # The refresh, on any branch and in any checkout.

    def test_a_lane_branch_fetches_origin_before_the_grants_compare(self):
        fresh = self.advance_origin_main()
        self.checkout_lane()
        self.assertNotEqual(self.resolve("origin/main"), fresh, "scope: origin/main is already fresh")
        self.assertEqual(self.blob("HEAD", "CLAUDE.md"), self.blob("origin/main", "CLAUDE.md"),
                         "scope: the lane's CLAUDE.md differs before the refresh")
        lines = self.run_checked()
        self.assert_one_differ_line(lines, "CLAUDE.md", "origin/main", fresh)

    def test_a_lane_branch_runs_one_fetch_of_origin_main(self):
        self.advance_origin_main()
        self.checkout_lane()
        _, starts = self.run_traced()
        self.assert_one_origin_main_fetch(starts)

    def test_a_detached_head_fetches_origin_before_the_grants_compare(self):
        fresh = self.advance_origin_main()
        vcs(self.primary, "checkout", "-q", "--detach")
        self.assertNotEqual(self.resolve("origin/main"), fresh, "scope: origin/main is already fresh")
        self.assertEqual(self.blob("HEAD", "CLAUDE.md"), self.blob("origin/main", "CLAUDE.md"),
                         "scope: the detached CLAUDE.md differs before the refresh")
        lines = self.run_checked()
        self.assert_one_differ_line(lines, "CLAUDE.md", "origin/main", fresh)

    def test_a_detached_head_runs_one_fetch_of_origin_main(self):
        self.advance_origin_main()
        vcs(self.primary, "checkout", "-q", "--detach")
        _, starts = self.run_traced()
        self.assert_one_origin_main_fetch(starts)

    def test_the_refresh_is_one_fetch_of_origin_main(self):
        self.checkout_lane()
        _, starts = self.run_traced()
        self.assert_one_origin_main_fetch(starts)

    def test_the_claude_settings_clone_refreshes_with_one_fetch_of_origin_main(self):
        # The checkout is the claude-settings clone: its own freshness check and the session's refresh are one fetch.
        self.put(os.path.join(self.config, "CLAUDE.md"), "@%s/CLAUDE.md\n" % self.primary.replace("\\", "/"))
        self.assertEqual(vcs(self.primary, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip(), "main",
                         "scope: the clone is not on main")
        _, starts = self.run_traced()
        self.assert_one_origin_main_fetch(starts)

    def test_the_default_branch_refreshes_with_one_fetch_of_origin_main(self):
        vcs(self.primary, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        self.assertEqual(self.resolve("origin/HEAD"), self.resolve("origin/main"),
                         "scope: origin/HEAD does not name origin/main")
        _, starts = self.run_traced()
        self.assert_one_origin_main_fetch(starts)

    def test_an_origin_head_on_another_branch_adds_that_branch_to_the_same_fetch(self):
        vcs(self.primary, "push", "-q", "origin", "HEAD:refs/heads/trunk")
        # The refresh reads origin's default with ls-remote, so origin's own HEAD must name trunk too.
        vcs(self.origin_repo, "symbolic-ref", "HEAD", "refs/heads/trunk")
        vcs(self.primary, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
        self.assertEqual(vcs(self.origin_repo, "symbolic-ref", "--short", "HEAD").stdout.strip(), "trunk",
                         "scope: origin's HEAD does not name trunk")
        self.assertEqual(vcs(self.primary, "symbolic-ref", "--short", "refs/remotes/origin/HEAD").stdout.strip(),
                         "origin/trunk", "scope: origin/HEAD does not name origin/trunk")
        _, starts = self.run_traced()
        self.assertEqual(len(self.ls_remote_starts(starts)), 1, "want one ls-remote, got %r" % starts)
        self.assert_one_origin_main_fetch(starts, branch="trunk")
        order = [start.split()[0] for start in starts]
        self.assertLess(order.index("ls-remote"), order.index("fetch"),
                        "the fetch ran before the ls-remote that reads origin's default: %r" % starts)

    def test_a_remote_with_no_main_refreshes_its_default_branch_and_reads_its_grants(self):
        # origin's default branch is master and origin has no main: the refresh must ask only for master.
        fresh = self.tip_with(GRANT_FRESH, GRANT_STALE_DOT)
        vcs(self.primary, "push", "-q", "origin", "%s:refs/heads/master" % fresh)
        vcs(self.origin_repo, "symbolic-ref", "HEAD", "refs/heads/master")
        vcs(self.origin_repo, "branch", "-q", "-D", "main")
        vcs(self.primary, "update-ref", "-d", "refs/remotes/origin/main")
        vcs(self.primary, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/master")
        self.assertEqual(self.resolve("origin/master"), fresh, "scope: origin/master is not the fresh tip")
        self.assertIsNone(self.resolve("origin/main"), "scope: origin/main still resolves")
        self.assertNotEqual(self.blob("HEAD", "CLAUDE.md"), self.blob("origin/master", "CLAUDE.md"),
                            "scope: the checkout's CLAUDE.md does not differ from origin/master")
        lines = self.run_checked()
        self.assertEqual([line for line in lines if "did not run" in line], [],
                         "the refresh failed on a remote with no main, so it asked for main: %r" % lines)
        self.assert_one_differ_line(lines, "CLAUDE.md", "origin/master", fresh)

    def remote_has_ref(self, name):
        """True when origin, the bare repo the tests share, holds the ref `name`."""
        answer = subprocess.run([VCS, "-C", self.origin_repo, "rev-parse", "-q", "--verify", name],
                                capture_output=True, text=True, timeout=60)
        return answer.returncode == 0

    def test_a_remote_whose_main_was_deleted_refreshes_trunk_and_drops_the_stale_main(self):
        # origin/HEAD names trunk, origin has no main, and this checkout still holds a stale origin/main.
        stale = self.head_sha()
        remote_tip = self.tip_with(GRANT_TRUNK, GRANT_STALE_DOT)
        vcs(self.primary, "push", "-q", "origin", "%s:refs/heads/trunk" % remote_tip)
        vcs(self.primary, "update-ref", "refs/remotes/origin/trunk", stale)
        vcs(self.primary, "update-ref", "refs/remotes/origin/main", self.tip_with(GRANT_FRESH, GRANT_STALE_DOT))
        vcs(self.origin_repo, "symbolic-ref", "HEAD", "refs/heads/trunk")
        vcs(self.origin_repo, "branch", "-q", "-D", "main")
        vcs(self.primary, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
        self.assertFalse(self.remote_has_ref("refs/heads/main"), "scope: origin still has main")
        self.assertEqual(self.resolve("origin/trunk"), stale, "scope: origin/trunk is not the stale tip")
        self.assertNotEqual(self.resolve("origin/main"), self.resolve("origin/trunk"),
                            "scope: origin/main is not a different stale tip")
        lines = self.run_checked()
        self.assertEqual([line for line in lines if "did not run" in line], [],
                         "the refresh printed did-not-run although trunk can be fetched: %r" % lines)
        self.assertEqual(self.resolve("origin/trunk"), remote_tip, "origin/trunk was not refreshed to the remote tip")
        self.assertIsNone(self.resolve("origin/main"), "the stale origin/main survived the refresh")
        # One grant line, for origin/trunk: a line that cites the stale origin/main would fail this too.
        self.assert_one_differ_line(lines, "CLAUDE.md", "origin/trunk", remote_tip)

    def test_a_trunk_default_with_no_local_main_still_reads_the_remote_main_grants(self):
        # origin/HEAD names trunk, this checkout holds no origin/main, and origin's main differs from HEAD.
        vcs(self.primary, "push", "-q", "origin", "HEAD:refs/heads/trunk")
        vcs(self.primary, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
        vcs(self.primary, "update-ref", "-d", "refs/remotes/origin/main")
        self.assertIsNone(self.resolve("origin/main"), "scope: origin/main still resolves")
        self.assertEqual(self.head_sha(), self.resolve("origin/trunk"), "scope: HEAD is not trunk's tip")
        fresh = self.advance_origin_main()
        self.assertNotEqual(fresh, self.head_sha(), "scope: origin's main is HEAD itself")
        self.assert_one_differ_line(self.run_checked(), "CLAUDE.md", "origin/main", fresh)

    def test_an_unreachable_origin_with_trunk_as_default_prints_one_did_not_run_line(self):
        # Control: the refresh fails once, and its one line prints once, not once per check that reads freshness.
        vcs(self.primary, "push", "-q", "origin", "HEAD:refs/heads/trunk")
        vcs(self.primary, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
        vcs(self.primary, "checkout", "-q", "-b", "trunk")
        vcs(self.primary, "remote", "set-url", "origin", os.path.join(self.root, "missing.git"))
        self.assertEqual(vcs(self.primary, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip(), "trunk",
                         "scope: the checkout is not on the default branch")
        lines = self.run_checked()
        refresh = [line for line in lines if "did not run" in line]
        self.assertEqual(len(refresh), 1, "want one did-not-run line, got %r" % refresh)
        self.assertIsNotNone(REFRESH_FAILED.match(refresh[0]), "the line is not the refresh line: %r" % refresh[0])

    def test_a_default_renamed_from_master_to_main_refreshes_main_with_no_did_not_run_line(self):
        # origin's default was master and is now main. origin/HEAD still names origin/master, and origin's main moved on.
        stale = self.head_sha()
        vcs(self.origin_repo, "update-ref", "refs/heads/master", stale)
        vcs(self.origin_repo, "symbolic-ref", "HEAD", "refs/heads/master")
        fresh = self.advance_origin_main()
        vcs(self.origin_repo, "symbolic-ref", "HEAD", "refs/heads/main")
        vcs(self.origin_repo, "branch", "-q", "-D", "master")
        vcs(self.primary, "update-ref", "refs/remotes/origin/master", stale)
        vcs(self.primary, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/master")
        self.assertFalse(self.remote_has_ref("refs/heads/master"), "scope: origin still has master")
        self.assertEqual(self.resolve("origin/main"), stale, "scope: origin/main is not the stale tip")
        self.assertEqual(vcs(self.primary, "symbolic-ref", "--short", "refs/remotes/origin/HEAD").stdout.strip(),
                         "origin/master", "scope: origin/HEAD does not name origin/master")
        self.assertNotEqual(self.blob("HEAD", "CLAUDE.md"), self.blob(fresh, "CLAUDE.md"),
                            "scope: the checkout's CLAUDE.md does not differ from the renamed main")
        lines = self.run_checked()
        self.assertEqual([line for line in lines if "did not run" in line], [],
                         "the refresh asked for master, which origin no longer has: %r" % lines)
        self.assertEqual(self.resolve("origin/main"), fresh, "origin/main was not refreshed to the renamed main's tip")
        self.assert_one_differ_line(lines, "CLAUDE.md", "origin/main", fresh)

    def test_a_remote_with_no_main_and_no_origin_head_prints_no_did_not_run_line(self):
        # origin's default is master and origin has no main. origin/HEAD is unset, so the refresh must learn the default
        # from origin and must not ask for main.
        fresh = self.tip_with(GRANT_FRESH, GRANT_STALE_DOT)
        vcs(self.primary, "push", "-q", "origin", "%s:refs/heads/master" % fresh)
        vcs(self.origin_repo, "symbolic-ref", "HEAD", "refs/heads/master")
        vcs(self.origin_repo, "branch", "-q", "-D", "main")
        vcs(self.primary, "update-ref", "-d", "refs/remotes/origin/main")
        self.assertEqual(self.resolve("origin/master"), fresh, "scope: origin/master is not the fresh tip")
        self.assertIsNone(self.resolve("origin/HEAD"), "scope: origin/HEAD is set")
        self.assertFalse(self.remote_has_ref("refs/heads/main"), "scope: origin still has main")
        self.assertNotEqual(self.blob("HEAD", "CLAUDE.md"), self.blob("origin/master", "CLAUDE.md"),
                            "scope: the checkout's CLAUDE.md does not differ from origin/master")
        lines = self.run_checked()
        self.assertEqual([line for line in lines if "did not run" in line], [],
                         "the refresh asked for main on a remote with no main: %r" % lines)
        self.assert_one_differ_line(lines, "CLAUDE.md", "origin/master", fresh)

    def test_a_refused_main_fetch_on_a_remote_with_main_keeps_origin_main_and_prints_one_line(self):
        # origin has main and trunk, and origin/HEAD names trunk. Every fetch that asks for main is refused with an exit
        # status, not a kill. The stale origin/main must survive a refused fetch, and one line says the refresh did not run.
        vcs(self.primary, "push", "-q", "origin", "HEAD:refs/heads/trunk")
        vcs(self.primary, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
        fresh = self.advance_origin_main()
        stale = self.resolve("origin/main")
        self.assertNotEqual(stale, fresh, "scope: origin/main is already fresh")
        self.assertTrue(self.remote_has_ref("refs/heads/main"), "scope: origin has no main")
        folder = self.make_git_stub("refused-main-shim", 'case "$*" in fetch*refs/heads/main*) exit 1;; esac')
        lines = self.run_checked(path_dir=folder)
        self.assert_stub_reached(folder, "fetch", "refs/heads/main")
        self.assertEqual(self.resolve("origin/main"), stale, "a refused fetch of main moved or deleted origin/main")
        refresh = [line for line in lines if REFRESH_FAILED.match(line)]
        self.assertEqual(len(refresh), 1, "want one did-not-run line, got %r" % lines)

    def test_no_origin_remote_starts_no_fetch_and_prints_no_refresh_line(self):
        vcs(self.primary, "remote", "remove", "origin")
        self.assertEqual(vcs(self.primary, "remote").stdout.strip(), "", "scope: a remote is still configured")
        fixture.set_fetch_head(self.primary)
        lines, starts = self.run_traced()
        self.assertEqual(self.fetch_starts(starts), [], "a fetch ran with no origin: %r" % starts)
        self.assertEqual([line for line in lines if REFRESH_FAILED.match(line)], [],
                         "a refresh line printed with no origin: %r" % lines)

    def test_a_stale_roadmap_ref_is_fetched_once_at_start(self):
        # No origin, so the grants refresh starts no fetch and writes no FETCH_HEAD: the roadmap read is the only one.
        long_ago = 1000000000  # an epoch second before any run, so the ref reads as stale
        vcs(self.primary, "remote", "remove", "origin")
        fixture.set_fetch_head(self.primary, when=long_ago)
        _lines, starts = self.run_traced()
        roadmap = [start for start in starts if start.split()[0] == "fetch" and "+roadmap:" in start]
        self.assertEqual(len(roadmap), 1, "a stale roadmap ref: want one fetch of roadmap, got %r" % roadmap)

    # A refresh that fails: one line says so, and the grant line it leaves is marked unrefreshed.

    def stage_a_lane_grant(self):
        """A lane whose CLAUDE.md differs from origin/main. Returns origin/main's tip, the sha the grant line names when
        no refresh lands."""
        self.checkout_lane()
        self.set_grants(GRANT_FRESH, GRANT_STALE_DOT)
        self.commit("lane grants")
        stale = self.resolve("origin/main")
        self.assertNotEqual(self.blob("HEAD", "CLAUDE.md"), self.blob("origin/main", "CLAUDE.md"),
                            "scope: the lane's CLAUDE.md does not differ")
        return stale

    def stage_a_lane_grant_against_a_missing_origin(self):
        """stage_a_lane_grant, with origin set to a path that does not exist. Returns origin/main's tip, which the grant
        line names once the refresh fails."""
        stale = self.stage_a_lane_grant()
        vcs(self.primary, "remote", "set-url", "origin", os.path.join(self.root, "missing.git"))
        return stale

    def test_a_failed_fetch_is_one_refresh_attempt(self):
        # The one attempt is the ls-remote that reads origin's default. Once it fails, no fetch starts.
        self.stage_a_lane_grant_against_a_missing_origin()
        fixture.set_fetch_head(self.primary)
        lines, starts = self.run_traced()
        self.assertEqual(len(self.ls_remote_starts(starts)), 1,
                         "want one refresh attempt, an ls-remote, got %r" % starts)
        self.assertEqual(self.fetch_starts(starts), [], "a fetch ran after the ls-remote failed: %r" % starts)
        refresh = [line for line in lines if REFRESH_FAILED.match(line)]
        self.assertEqual(len(refresh), 1, "want one did-not-run line, got %r" % lines)

    def test_a_failed_fetch_prints_one_refresh_line_and_marks_the_grant_line_unrefreshed(self):
        stale = self.stage_a_lane_grant_against_a_missing_origin()
        lines = self.run_checked()
        refresh = [line for line in lines if REFRESH_FAILED.match(line)]
        self.assertEqual(len(refresh), 1, "want one refresh line, got %r" % lines)
        grant = self.grant_lines_of(lines)
        self.assertEqual(len(grant), 1, "want one grant line, got %r" % grant)
        found = UNREFRESHED.match(grant[0])
        self.assertIsNotNone(found, "the grant line is not marked unrefreshed: %r" % grant[0])
        self.assertTrue(stale.startswith(found.group(1)), "the line's sha is not origin/main's old tip: %r" % grant[0])

    def test_a_grant_line_after_a_good_refresh_is_not_marked_unrefreshed(self):
        self.checkout_lane()
        self.set_grants(GRANT_FRESH, GRANT_STALE_DOT)
        self.commit("lane grants")
        stale = self.resolve("origin/main")
        lines = self.run_checked()
        self.assert_one_differ_line(lines, "CLAUDE.md", "origin/main", stale)

    def assert_a_hung_refresh_keeps_origin_main(self, command):
        """With origin ahead of origin/main, a `git <command>` that hangs past the bound leaves the refresh not run: one
        did-not-run line, a grant line marked unrefreshed, and origin/main at its old tip. The bound is one second, so
        the watchdog ends the hang; the stub's sleep only has to outlast it."""
        fresh = self.advance_origin_main()
        stale = self.stage_a_lane_grant()
        self.assertNotEqual(stale, fresh, "scope: origin/main is already fresh")
        folder = self.make_git_stub("hung-%s-shim" % command, 'if [ "$1" = %s ]; then sleep 20; fi' % command)
        lines = self.run_checked(path_dir=folder, fetch_timeout="1")
        self.assert_stub_reached(folder, command)
        refresh = [line for line in lines if REFRESH_FAILED.match(line)]
        self.assertEqual(len(refresh), 1, "want one did-not-run line for a hung %s, got %r" % (command, lines))
        self.assertEqual(self.resolve("origin/main"), stale, "origin/main moved in a run where git %s hangs" % command)
        grant = self.grant_lines_of(lines)
        self.assertEqual(len(grant), 1, "want one grant line, got %r" % grant)
        found = UNREFRESHED.match(grant[0])
        self.assertIsNotNone(found, "the grant line is not marked unrefreshed: %r" % grant[0])
        self.assertTrue(stale.startswith(found.group(1)), "the line's sha is not origin/main's kept tip: %r" % grant[0])

    def test_an_ls_remote_that_hangs_prints_one_did_not_run_line_and_keeps_origin_main(self):
        self.assert_a_hung_refresh_keeps_origin_main("ls-remote")

    def test_a_fetch_that_hangs_prints_one_did_not_run_line_and_keeps_origin_main(self):
        self.assert_a_hung_refresh_keeps_origin_main("fetch")

    def run_under_windows_form(self, folder, git_first):
        """The hook's lines, run through the Windows form with `folder` first on PATH. With git_first, the folder of the
        real git goes ahead of it, as Git for Windows' sh launcher leaves PATH; the form must put the stub back first."""
        with mock.patch.dict(globals(), {"WINDOWS_LAUNCH": True}):
            argv, env, payload, where = self.hook_launch(path_dir=folder)
        if git_first:
            env["PATH"] = os.pathsep.join([os.path.dirname(shutil.which("git")), env["PATH"]])
        answer = subprocess.run(argv, input=payload, capture_output=True, text=True, env=env, cwd=where, timeout=120)
        self.assertEqual(answer.returncode, 0, "the hook exited %d" % answer.returncode)
        return answer.stdout.splitlines()

    def assert_windows_form_reaches_the_stub(self, git_first):
        folder = self.make_git_stub("windows-form-shim", "")
        lines = self.run_under_windows_form(folder, git_first)
        self.assertTrue(any(line.startswith("checkout ") for line in lines),
                        "the hook printed no checkout line: %r" % lines)
        self.assertTrue(self.stub_starts(folder), "the git stub was not reached: the hook logged no git call to it")

    def test_the_windows_form_reaches_a_stub_that_the_launcher_left_behind_git(self):
        self.assert_windows_form_reaches_the_stub(git_first=True)

    def test_the_windows_form_reaches_a_stub_first_on_path_as_a_control(self):
        self.assert_windows_form_reaches_the_stub(git_first=False)

    # The grant line prints before a slow step, even when the refresh fails or is killed. The slow step is the caution
    # call, which runs before the grant block on main. run_to_slow_step cuts the run there.

    def assert_refresh_lines_before_the_cut(self, path_dir=None):
        """A refresh that failed or was killed: its did-not-run line and the unrefreshed grant line print before
        the cut."""
        lines, reached = self.run_to_slow_step(path_dir=path_dir)
        self.assertTrue(reached, "scope: the slow step was never reached, so the cut proves nothing: %r" % lines)
        refresh = [line for line in lines if REFRESH_FAILED.match(line)]
        self.assertEqual(len(refresh), 1, "the did-not-run line did not print before the slow step: %r" % lines)
        grant = self.grant_lines_of(lines)
        self.assertEqual(len(grant), 1, "the grant line did not print before the slow step: %r" % lines)
        self.assertIsNotNone(UNREFRESHED.match(grant[0]),
                             "the grant line before the slow step is not marked unrefreshed: %r" % grant[0])

    @unittest.skipIf(os.name == "nt", "the slow step is a POSIX sh shim with a pipe fd and a process group")
    def test_the_grant_line_prints_before_a_slow_step_is_cut_off(self):
        fresh = self.advance_origin_main()
        self.checkout_lane()
        self.assertNotEqual(self.resolve("origin/main"), fresh, "scope: origin/main is already fresh")
        self.assertEqual(self.blob("HEAD", "CLAUDE.md"), self.blob("origin/main", "CLAUDE.md"),
                         "scope: the lane's CLAUDE.md differs before the refresh")
        # Control: with no cut, the refresh lands and the grant line prints after the caution call.
        self.point_at()
        self.assert_one_differ_line(self.run_checked(), "CLAUDE.md", "origin/main", fresh)
        self.assertNotEqual(self.blob("HEAD", "CLAUDE.md"), self.blob("origin/main", "CLAUDE.md"),
                            "scope: the lane's CLAUDE.md does not differ from origin/main after the refresh")
        lines, reached = self.run_to_slow_step()
        self.assertTrue(reached, "scope: the slow step was never reached, so the cut proves nothing: %r" % lines)
        self.assertTrue(any(line.startswith("checkout ") for line in lines),
                        "the checkout line did not print before the cut: %r" % lines)
        self.assert_one_differ_line(lines, "CLAUDE.md", "origin/main", fresh)

    @unittest.skipIf(os.name == "nt", "the slow step is a POSIX sh shim with a pipe fd and a process group")
    def test_a_failed_fetch_prints_its_lines_before_a_slow_step_is_cut_off(self):
        self.stage_a_lane_grant_against_a_missing_origin()
        self.assert_refresh_lines_before_the_cut()

    @unittest.skipIf(os.name == "nt", "the slow step is a POSIX sh shim with a pipe fd and a process group")
    def test_a_killed_fetch_prints_its_lines_before_a_slow_step_is_cut_off(self):
        self.stage_a_lane_grant()
        self.assert_refresh_lines_before_the_cut(path_dir=self.make_fetch_killed_shim())

    # Local main: counted against origin/main, never moved.

    def test_local_main_behind_origin_main_prints_the_behind_count_and_moves_nothing(self):
        self.advance_origin_main()
        self.checkout_lane()
        main_before = self.resolve("refs/heads/main")
        self.assertEqual(main_before, self.resolve("origin/main"), "scope: local main is not at the stale origin/main")
        lines = self.run_checked()
        self.assertEqual(self.resolve("refs/heads/main"), main_before, "the session start moved local main")
        self.assert_local_main_line(lines, "1", None)

    def test_local_main_ahead_of_origin_main_prints_the_ahead_count(self):
        self.commit("local only")
        self.checkout_lane()
        main_before = self.resolve("refs/heads/main")
        self.assertNotEqual(main_before, self.resolve("origin/main"), "scope: local main equals origin/main")
        lines = self.run_checked()
        self.assertEqual(self.resolve("refs/heads/main"), main_before, "the session start moved local main")
        self.assert_local_main_line(lines, "0", "1")

    def test_local_main_diverged_from_origin_main_prints_both_counts(self):
        self.commit("local only")
        self.advance_origin_main()
        self.checkout_lane()
        main_before = self.resolve("refs/heads/main")
        lines = self.run_checked()
        self.assertEqual(self.resolve("refs/heads/main"), main_before, "the session start moved local main")
        self.assert_local_main_line(lines, "1", "1")

    def test_local_main_equal_to_origin_main_prints_no_local_main_line(self):
        self.checkout_lane()
        self.assertEqual(self.resolve("refs/heads/main"), self.resolve("origin/main"),
                         "scope: local main differs from origin/main")
        lines = self.run_checked()
        self.assertEqual([line for line in lines if LOCAL_MAIN.match(line)], [],
                         "a local main line printed for equal refs: %r" % lines)

    def test_no_local_main_prints_no_local_main_line(self):
        self.advance_origin_main()
        self.checkout_lane()
        vcs(self.primary, "branch", "-q", "-D", "main")
        self.assertIsNone(self.resolve("refs/heads/main"), "scope: local main still exists")
        self.assertIsNotNone(self.resolve("origin/main"), "scope: origin/main is gone")
        lines = self.run_checked()
        self.assertEqual([line for line in lines if LOCAL_MAIN.match(line)], [],
                         "a local main line printed with no local main: %r" % lines)

    def test_a_default_branch_behind_origin_prints_the_pull_line_and_no_local_main_line(self):
        self.advance_origin_main(commits=2)
        vcs(self.primary, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        main_before = self.resolve("refs/heads/main")
        self.assertEqual(vcs(self.primary, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip(), "main",
                         "scope: the primary checkout is not on main")
        self.assertEqual(self.resolve("origin/HEAD"), main_before, "scope: origin/HEAD does not name the stale origin/main")
        lines = self.run_checked()
        behind = [found.group(1) for found in map(DEFAULT_BEHIND.match, lines) if found]
        self.assertEqual(behind, ["2"], "want one pull line saying main is 2 commits behind origin/main, got %r" % lines)
        self.assertEqual([line for line in lines if LOCAL_MAIN.match(line)], [],
                         "a local main line printed beside the pull line for the same branch: %r" % lines)
        self.assertEqual(self.resolve("refs/heads/main"), main_before, "the session start moved local main")

    # The watchdog: when the fetch returns first, the hook's TERM must end the watchdog's sleep.

    def make_fetch_stall_shim(self, witness):
        """A folder whose `git fetch` waits, up to 10 seconds, until a `sleep 7` process runs, writes that process's pid
        to `witness`, and returns 0 at once. The fetch returns first, so the hook's TERM is what must end the sleep.
        Every other git call runs the real git."""
        real = shutil.which("git")
        folder = os.path.join(self.root, "stall-shim")
        os.makedirs(folder)
        script = os.path.join(folder, "git")
        lines = [
            "#!/bin/sh",
            'if [ "$1" = fetch ]; then',
            "  i=0",
            "  while [ $i -lt 200 ]; do",
            "    found=$(ps -eo pid=,args= | awk '$2 == \"sleep\" && $3 == \"7\" && NF == 3 { print $1 }')",
            '    if [ -n "$found" ]; then printf \'%s\\n\' "$found" > "' + witness + '"; exit 0; fi',
            "    i=$((i + 1))",
            "    sleep 0.05",
            "  done",
            "  exit 0",
            "fi",
            'exec "' + real + '" "$@"',
        ]
        with open(script, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
        os.chmod(script, 0o755)
        return folder

    @staticmethod
    def sleep_seven_pids():
        """The pids of the processes whose command line is exactly `sleep 7`, as ps lists them now."""
        answer = subprocess.run(["ps", "-eo", "pid=,args="], capture_output=True, text=True, timeout=60)
        return [fields[0] for fields in (line.split() for line in answer.stdout.splitlines())
                if fields[1:] == ["sleep", "7"]]

    @unittest.skipIf(os.name == "nt", "the reap check reads POSIX ps and the sh git stub, which Windows does not run")
    def test_the_watchdog_sleep_is_gone_when_the_fetch_returns_first(self):
        witness = os.path.join(self.root, "sleep-seen")
        folder = self.make_fetch_stall_shim(witness)
        self.run_checked(path_dir=folder, fetch_timeout="7")
        self.assertTrue(os.path.exists(witness),
                        "scope: the watchdog's sleep 7 never ran while the fetch held, so the case proves nothing")
        with open(witness, encoding="utf-8") as handle:
            pids = handle.read().split()
        self.assertTrue(pids, "scope: the witness names no pid")
        self.addCleanup(self.stop_sleeps, pids)
        left = sorted(set(pids) & set(self.sleep_seven_pids()))
        self.assertEqual(left, [], "the watchdog's sleep 7 is still running after the hook returned: pid %r" % left)

    @staticmethod
    def stop_sleeps(pids):
        """Ends any of the given pids that still run `sleep 7`, so a red run leaves no sleep behind."""
        for pid in sorted(set(pids) & set(SessionStartFetchTests.sleep_seven_pids())):
            os.kill(int(pid), signal.SIGTERM)

    # No prune: the refresh fetches origin/main alone, so every other remote-tracking ref stays as it was.

    def test_the_refresh_keeps_the_remote_ref_of_a_branch_deleted_on_origin(self):
        vcs(self.primary, "branch", "-q", "feature")
        vcs(self.primary, "push", "-q", "origin", "feature")
        vcs(self.origin_repo, "branch", "-q", "-D", "feature")
        self.checkout_lane()
        self.assertIsNotNone(self.resolve("origin/feature"), "scope: origin/feature is not set")
        self.assertIsNotNone(self.resolve("refs/heads/feature"), "scope: local feature is not set")
        self.run_checked()
        self.assertIsNotNone(self.resolve("origin/feature"),
                             "the refresh pruned origin/feature: it ran a whole-origin prune")
        self.assertIsNotNone(self.resolve("refs/heads/feature"), "the refresh removed the local branch")

    # Cost: the refresh writes only git's own refs, objects and FETCH_HEAD; the hook is wired at session start only.

    def test_the_refresh_writes_only_git_s_own_refs_objects_and_fetch_head(self):
        fresh = self.advance_origin_main()
        self.checkout_lane()
        before = self.snapshot()
        self.run_checked()
        after = self.snapshot()
        self.assertEqual(self.resolve("origin/main"), fresh, "scope: the refresh did not run")
        changed = sorted(name.replace(os.sep, "/") for name in set(before) | set(after)
                         if before.get(name) != after.get(name))
        allowed = (".git/FETCH_HEAD", ".git/packed-refs", ".git/refs/", ".git/objects/", ".git/logs/refs/remotes/")
        stray = [name for name in changed if not name.startswith(allowed)]
        self.assertEqual(stray, [], "the refresh wrote files other than git's refs, objects and FETCH_HEAD: %r" % stray)

    def test_session_start_is_wired_to_session_start_only(self):
        with open(os.path.join(HERE, "..", "settings.json"), encoding="utf-8") as handle:
            hooks = json.load(handle)["hooks"]

        def commands(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key == "command" and isinstance(value, str):
                        yield value
                    else:
                        yield from commands(value)
            elif isinstance(node, list):
                for value in node:
                    yield from commands(value)

        def wired(event):
            return [text for text in commands(hooks.get(event, [])) if "session_start" in text]

        self.assertTrue(wired("SessionStart"), "scope: SessionStart runs no session_start hook")
        for event in ("UserPromptSubmit", "PreToolUse"):
            self.assertEqual(wired(event), [], "session_start is wired to %s" % event)


# The platform's Stop-hook script, trimmed to what the stop-push cases need. The anchor line and the two lines around it
# are verbatim from the platform text (~/.claude/stop-hook-git-check.sh, lines 172-175); the rest is cut.
PLATFORM_ANCHOR = '  unpushed=$(git rev-list "$upstream..HEAD" --count 2>/dev/null) || unpushed=0'
PLATFORM_TEXT = """#!/bin/bash

input=$(cat)

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  exit 0
fi

if [[ -z "$(git remote)" ]]; then
  exit 0
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "There are uncommitted changes in the repository. Please commit and push these changes to the remote branch." >&2
  exit 2
fi

untracked_files=$(git ls-files --others --exclude-standard)
if [[ -n "$untracked_files" ]]; then
  echo "There are untracked files in the repository. Please commit and push these changes to the remote branch." >&2
  exit 2
fi

current_branch=$(git branch --show-current)
if [[ -n "$current_branch" ]]; then
  if git rev-parse "origin/$current_branch" >/dev/null 2>&1; then
    upstream="origin/$current_branch"
  else
    upstream="origin/HEAD"
  fi

  unpushed=$(git rev-list "$upstream..HEAD" --count 2>/dev/null) || unpushed=0
  if [[ "$unpushed" -gt 0 ]]; then
    if [[ "$upstream" == "origin/$current_branch" ]]; then
      echo "There are $unpushed unpushed commit(s) on branch '$current_branch'. Please push these changes to the remote repository." >&2
    else
      echo "Branch '$current_branch' has $unpushed unpushed commit(s) and no remote branch. Please push these changes to the remote repository." >&2
    fi
    exit 2
  fi
fi

exit 0
"""
STOP_MARKER = "# claude-settings: skip-merged"  # the marker the patch leaves; the platform script holds it once
STOP_CITATION = "owner, page item 464 b, 2026-11-09 13:09 CST"  # the ruling the patch cites


def full_size_text():
    """The trimmed text with 150 comment lines after the shebang, about the size of the platform's own script."""
    filler = "".join("# filler line %03d: the platform script carries its own comment block here\n" % number
                     for number in range(150))
    return PLATFORM_TEXT.replace("#!/bin/bash\n", "#!/bin/bash\n" + filler, 1)


class SessionStartRulingLinesTests(SessionStartAgentWorktreeNoticeTests):
    """The owner's open rulings print once at session start: the hook runs lint/ruled_store.py --session-line on the
    claude-settings clone that the config's pointer names. That clone is a second checkout, with no origin remote (so the
    hook's fetch never runs in it) and with lint/ copied from this repo. The session's own checkout holds no store, so a
    hook that reads the session checkout instead of the clone prints nothing."""

    def make_clone(self, store, main=None):
        """The pointer clone, with origin/roadmap at `store` and, when given, origin/main at `main`. The config's CLAUDE.md
        names it. lint/ is copied from this repo, as tracked_tree lists it."""
        clone = os.path.join(self.root, "clone")
        os.makedirs(clone)
        vcs(clone, "init", "-q", "-b", "main", ".")
        tracked_tree.copy_tracked(clone, "lint")
        vcs(clone, "add", "-A")
        vcs(clone, "commit", "-q", "-m", "claude-settings clone")
        fixture.point_ref(clone, fixture.STORE_REF, store, self.root)
        fixture.set_fetch_head(clone)
        if main is not None:
            fixture.point_ref(clone, fixture.MAIN_REF, main, self.root)
        with open(os.path.join(self.config, "CLAUDE.md"), "w", encoding="utf-8") as handle:
            handle.write("@%s/CLAUDE.md\n" % clone.replace("\\", "/"))

    def open_store_lines(self):
        """The hook's lines for a store with two open entries and one entry that main's text closes."""
        self.make_clone(
            fixture.ruling_files({
                "ruled-apps-keep": fixture.entry("ruled-apps-keep"),
                "ruled-pending": fixture.entry("ruled-pending", lands_in={"path": "docs/rules.md",
                                                                          "contains": "Rule two: keep the apps."}),
                "ruled-landed": fixture.entry("ruled-landed", lands_in={"path": "docs/rules.md",
                                                                        "contains": "Rule one: keep the apps."}),
            }),
            main={"docs/rules.md": "Rule one: keep the apps.\n"},
        )
        return self.run_hook(source="startup")

    def test_open_entries_print_the_header_at_start(self):
        lines = self.open_store_lines()
        self.assertTrue(any(line.startswith("checkout ") for line in lines),
                        "control: the hook printed no checkout line: %r" % lines)
        heads = [line for line in lines if line.startswith("rulings not on main: ")]
        self.assertEqual(heads, ["rulings not on main: 2 open (0 with no supersedes read yet), newest first"],
                         "the ruled header line is not the one for two open entries: %r" % heads)

    def test_each_open_entry_prints_one_line_and_the_entry_main_closes_does_not(self):
        lines = self.open_store_lines()
        self.assertTrue(any(line.startswith("checkout ") for line in lines),
                        "control: the hook printed no checkout line: %r" % lines)
        listed = sorted(line.split()[0] for line in lines if line.startswith("  ruled-"))
        self.assertEqual(listed, ["ruled-apps-keep", "ruled-pending"],
                         "the entry lines name %r, want the two open entries and not the one closed on main" % listed)

    def test_nothing_prints_when_no_entry_is_open(self):
        self.make_clone(
            fixture.ruling_files({
                "ruled-shut": fixture.entry("ruled-shut", status="closed"),
                "ruled-landed": fixture.entry("ruled-landed", lands_in={"path": "docs/rules.md",
                                                                        "contains": "Rule one: keep the apps."}),
            }),
            main={"docs/rules.md": "Rule one: keep the apps.\n"},
        )
        lines = self.run_hook(source="startup")
        self.assertTrue(any(line.startswith("checkout ") for line in lines),
                        "control: the hook printed no checkout line: %r" % lines)
        noise = [line for line in lines if line.startswith("rulings not on main") or line.startswith("  ruled-")]
        self.assertEqual(noise, [], "the hook printed a ruled line with no open entry: %r" % noise)


class SessionStartStopHookPatchTests(SessionStartAgentWorktreeNoticeTests):
    """The session-start hook patches the platform Stop-hook script once, so its unpushed-commits check skips a
    branch already merged into origin/main. Real git repos, the hook run as the harness runs it. The platform
    script is a fixture file in the config folder, never the live one."""

    def setUp(self):
        super().setUp()
        self.platform = os.path.join(self.config, "stop-hook-git-check.sh")

    def write_platform(self, text):
        with open(self.platform, "wb") as handle:
            handle.write(text.encode("utf-8"))
        os.chmod(self.platform, 0o755)

    def read_platform(self):
        with open(self.platform, "rb") as handle:
            return handle.read()

    def commit_file(self, where, name, text, message):
        self.put(os.path.join(where, name), text)
        vcs(where, "add", "--", name)
        vcs(where, "commit", "-q", "-m", message)
        return vcs(where, "rev-parse", "HEAD").stdout.strip()

    def make_work(self, local_commit=False):
        """A clone whose origin/main holds the feature commit, with origin/HEAD stale at the base commit and no
        origin/feat. The branch `feat` is checked out at that feature commit, which origin/main contains. Returns the
        clone's path."""
        seed = os.path.join(self.root, "seed")
        origin = os.path.join(self.root, "origin.git")
        work = os.path.join(self.root, "work")
        vcs(self.root, "init", "-q", "-b", "main", seed)
        base = self.commit_file(seed, "f.txt", "base\n", "base")
        feature = self.commit_file(seed, "g.txt", "feature\n", "feature work")
        self.commit_file(seed, "h.txt", "main moves on\n", "main moves on")
        vcs(self.root, "clone", "-q", "--bare", seed, origin)
        vcs(self.root, "clone", "-q", origin, work)
        vcs(work, "update-ref", "--no-deref", "refs/remotes/origin/HEAD", base)
        vcs(work, "checkout", "-q", "-b", "feat", feature)
        if local_commit:
            self.commit_file(work, "k.txt", "local work\n", "local work")
        return work

    def run_stop(self, work):
        """The platform script's exit code and stderr, run as the harness runs it: bash, the payload on stdin, in the clone."""
        answer = subprocess.run([sh_exe("bash"), self.platform], input="{}", capture_output=True, text=True,
                                cwd=work, timeout=120)
        return answer.returncode, answer.stderr

    def test_patch_adds_one_block_after_the_anchor(self):
        """One hook run puts one block right after the anchor: the is-ancestor line, the marker, the citation. The lines
        above and below keep their order, and the file keeps its mode."""
        for label, text in (("trimmed", PLATFORM_TEXT), ("full-size", full_size_text())):
            with self.subTest(text=label):
                self.write_platform(text)
                self.run_hook()
                self.assertEqual(self.last_stderr, "", "the hook wrote to stderr: %r" % self.last_stderr)
                patched = self.read_platform().decode("utf-8")
                count = patched.count(STOP_MARKER)
                self.assertEqual(count, 1, "one hook run leaves the skip-merged marker %d times in the platform script, want 1"
                                 % count)
                old, new = text.splitlines(), patched.splitlines()
                at = old.index(PLATFORM_ANCHOR)
                grown = len(new) - len(old)
                self.assertEqual(new[:at + 1], old[:at + 1], "the lines above the anchor changed")
                self.assertEqual(new[at + 1 + grown:], old[at + 1:], "the lines below the inserted block changed")
                block = new[at + 1:at + 1 + grown]
                ancestor = [line for line in block
                            if "unpushed=0" in line and "merge-base --is-ancestor HEAD origin/main" in line]
                self.assertEqual(len(ancestor), 1, "the block holds %d lines that set unpushed=0 on the is-ancestor check, "
                                 "want 1: %r" % (len(ancestor), block))
                self.assertTrue(any(STOP_MARKER in line for line in block), "the block holds no marker line: %r" % block)
                self.assertTrue(any(STOP_CITATION in line for line in block),
                                "the block does not cite the owner ruling: %r" % block)
                if os.name != "nt":
                    self.assertEqual(os.stat(self.platform).st_mode & 0o777, 0o755,
                                     "the patch changed the platform script's mode")

    def test_second_run_inserts_nothing(self):
        """Idempotent: the first run leaves one marker, and a second run leaves the bytes it found."""
        self.write_platform(PLATFORM_TEXT)
        self.run_hook()
        self.assertEqual(self.last_stderr, "", "the first run wrote to stderr: %r" % self.last_stderr)
        first = self.read_platform()
        count = first.decode("utf-8").count(STOP_MARKER)
        self.assertEqual(count, 1, "one hook run leaves the skip-merged marker %d times, want 1" % count)
        self.run_hook()
        self.assertEqual(self.last_stderr, "", "the second run wrote to stderr: %r" % self.last_stderr)
        self.assertEqual(self.read_platform(), first, "a second hook run changed the platform script")

    def test_merged_branch_without_a_remote_branch_exits_zero_after_the_patch(self):
        """A branch whose head origin/main contains, with no origin/feat: the patched check exits 0, not 2."""
        work = self.make_work()
        self.write_platform(PLATFORM_TEXT)
        rc, err = self.run_stop(work)
        # Control: the unpatched text names the merged branch as unpushed, so this fixture reaches the defect.
        self.assertEqual(rc, 2, "control: the unpatched check exits %d for the merged branch, want 2" % rc)
        self.assertIn("has 1 unpushed commit(s) and no remote branch", err,
                      "control: the unpatched check gave another message: %r" % err)
        self.run_hook()
        rc, err = self.run_stop(work)
        self.assertEqual(rc, 0, "after the hook ran, the check exits %d for a branch merged into origin/main, want 0: %r"
                         % (rc, err))
        self.assertEqual(err, "", "after the hook ran, the check still names a merged branch: %r" % err)

    def test_branch_with_a_real_unpushed_commit_still_exits_two_after_the_patch(self):
        """A branch with a commit origin/main lacks: the patch is applied, and the check still exits 2 with its nudge."""
        work = self.make_work(local_commit=True)
        self.write_platform(PLATFORM_TEXT)
        self.run_hook()
        count = self.read_platform().decode("utf-8").count(STOP_MARKER)
        self.assertEqual(count, 1, "the patch is not applied, so the skip-merged marker count is %d, want 1" % count)
        rc, err = self.run_stop(work)
        self.assertEqual(rc, 2, "a branch with a real unpushed commit exits %d after the patch, want 2" % rc)
        self.assertIn("has 2 unpushed commit(s) and no remote branch", err,
                      "the check did not print its unpushed nudge: %r" % err)

    def test_changed_platform_text_is_left_alone_and_one_line_says_so(self):
        """The anchor changed or doubled, or the file is empty: the file stays byte-identical, and the hook prints one
        line saying the patch was not applied because the platform text changed."""
        self.assertEqual(PLATFORM_TEXT.count(PLATFORM_ANCHOR), 1,
                         "fixture setup failed: the anchor is not once in the trimmed text")
        baseline = self.run_hook()  # no platform file yet, so these are the baseline lines
        self.assertTrue(any(line.startswith("checkout ") for line in baseline),
                        "the hook printed no checkout line: %r" % baseline)
        variants = (
            ("anchor token changed", PLATFORM_TEXT.replace("--count ", "--number ", 1)),
            ("anchor twice", PLATFORM_TEXT.replace(PLATFORM_ANCHOR + "\n", PLATFORM_ANCHOR + "\n" + PLATFORM_ANCHOR + "\n", 1)),
            ("empty file", ""),
        )
        for label, text in variants:
            with self.subTest(variant=label):
                self.write_platform(text)
                before = self.read_platform()
                lines = self.run_hook()
                self.assertEqual(self.read_platform(), before, "the hook changed the platform script (%s)" % label)
                extra = [line for line in lines if line not in baseline]
                self.assertEqual(len(extra), 1, "want one line saying the patch was not applied (%s), got %r" % (label, extra))
                self.assertIn("not applied", extra[0], "the line does not say the patch was not applied: %r" % extra[0])
                self.assertIn("changed", extra[0], "the line does not say the platform text changed: %r" % extra[0])
                self.assertEqual(self.last_stderr, "", "the hook wrote to stderr (%s): %r" % (label, self.last_stderr))

    def test_control_missing_platform_file_stays_silent(self):
        """Control: with no platform file the hook writes nothing, prints nothing about the
        patch and exits 0. It guards the new step's silence."""
        lines = self.run_hook()
        self.assertFalse(os.path.exists(self.platform), "the hook created the platform script")
        noise = [line for line in lines if STOP_MARKER in line or "not applied" in line or "stop-hook" in line]
        self.assertEqual(noise, [], "the hook printed about a missing platform script: %r" % noise)
        self.assertEqual(self.last_stderr, "", "the hook wrote to stderr: %r" % self.last_stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
