#!/usr/bin/env python3
"""Cases for lint/check_hook_stubs.py. Standard library only.

    python3 lint/test_check_hook_stubs.py

A session keeps the settings.json it started with. So a hook script that any settings.json version
on main called must still exist at HEAD, even as an exit-0 stub. No day window: a version from any
age counts, and the check never reads the clock.

Each case builds a temp git repo with dated commits and runs the real script on it with --repo.
CHECK_HOOK_STUBS_UNDER_TEST overrides the module path.
"""
import json
import os
import shutil
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
MODULE = os.environ.get("CHECK_HOOK_STUBS_UNDER_TEST") or os.path.join(HERE, "check_hook_stubs.py")
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  copies what git lists, so no fixture lists files (testing/tracked_tree.py)

CONFIG = "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
HEAD = "2026-10-25T12:00:00+00:00"  # the head commit's date
OLD = "2026-09-01T12:00:00+00:00"  # an early call
EARLY_DROP = "2026-09-15T12:00:00+00:00"  # a drop, after OLD
MID = "2026-10-12T12:00:00+00:00"  # a call, after OLD
LATE = "2026-10-20T12:00:00+00:00"  # a drop, after MID
YEARS_OLD = "2019-03-01T12:00:00+00:00"  # a call years before HEAD
YEARS_DROP = "2020-06-01T12:00:00+00:00"  # a drop, after YEARS_OLD


def settings(*paths):
    """A settings.json with one wrapper-form hook command per path."""
    cmds = [f'g="{CONFIG}/{p}"; [ -f "$g" ] || exit 0; python3 "$g"' for p in paths]
    groups = [{"matcher": "Write|Edit", "hooks": [{"type": "command", "command": c}]} for c in cmds]
    return json.dumps({"hooks": {"PreToolUse": groups}}, indent=2) + "\n"


class HookStubsTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(MODULE), "module absent: lint/check_hook_stubs.py")
        root = _test_temp.run_folder()  # test-temp-standard: this run's folder, removed at teardown
        self.addCleanup(tracked_tree.rm_tree, root)
        self.tool = os.path.join(root, "tool")  # the script lives outside the repo it checks
        tracked_tree.copy_tracked(self.tool, "lint", "hooks")  # the check's imports, whatever they become
        shutil.copyfile(MODULE, os.path.join(self.tool, "lint", "check_hook_stubs.py"))
        self.repo = os.path.join(root, "repo")
        os.makedirs(self.repo)
        self.root = root
        self.git("init", "-q", "-b", "main")

    def git(self, *args, date=None, cwd=None):
        env = dict(os.environ)
        if date:
            env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
        r = subprocess.run(["git", "-C", cwd or self.repo, "-c", "user.name=test",
                            "-c", "user.email=test@example.com", *args],
                           check=True, capture_output=True, text=True, env=env)
        return r.stdout

    def commit(self, date, files=None, delete=()):
        for rel, text in (files or {}).items():
            path = os.path.join(self.repo, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
        for rel in delete:
            os.remove(os.path.join(self.repo, *rel.split("/")))
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", "c", date=date)

    def run_check(self, *args, ci=False, repo=None):
        env = dict(os.environ)
        env.pop("CI", None)
        if ci:
            env["CI"] = "1"
        cmd = [sys.executable, os.path.join(self.tool, "lint", "check_hook_stubs.py"),
               *(args or ("--repo", repo or self.repo))]
        r = subprocess.run(cmd, cwd=self.root, env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        return r.returncode, r.stdout + r.stderr

    def fails(self, out):
        return [ln for ln in out.splitlines() if ln.startswith("check_hook_stubs: FAIL:")]

    def called_then_dropped(self, call_date, drop_date, stub=False):
        """x.py is called from call_date, then its entry and file go at drop_date; head is later."""
        self.commit(call_date, {"settings.json": settings("hooks/x.py"), "hooks/x.py": "print(1)\n"})
        if stub:
            self.commit(drop_date, {"settings.json": settings(), "hooks/x.py": "raise SystemExit(0)\n"})
        else:
            self.commit(drop_date, {"settings.json": settings()}, delete=["hooks/x.py"])
        self.commit(HEAD, {"README.md": "head\n"})

    def test_1_deleted_script_called_and_then_dropped_fails(self):
        self.called_then_dropped(MID, LATE)
        rc, out = self.run_check("--repo", self.repo)
        self.assertEqual(rc, 1, out)
        lines = self.fails(out)
        self.assertEqual(len(lines), 1, out)
        self.assertIn("hooks/x.py", lines[0])

    def test_2_a_stub_at_head_passes(self):
        self.called_then_dropped(MID, LATE, stub=True)
        rc, out = self.run_check("--repo", self.repo)
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.fails(out), [], out)
        self.assertIn("check_hook_stubs: OK", out)

    def test_3_deleting_a_script_no_settings_ever_called_passes(self):
        self.commit(MID, {"settings.json": settings("hooks/x.py"),
                          "hooks/x.py": "print(1)\n", "hooks/y.py": "print(2)\n"})
        self.commit(HEAD, delete=["hooks/y.py"])
        rc, out = self.run_check("--repo", self.repo)
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.fails(out), [], out)

    def test_4_a_call_older_than_recent_history_still_fails(self):
        # Called on 09-01 and dropped on 09-15. No window: the version that made the call stays in history.
        self.called_then_dropped(OLD, EARLY_DROP)
        rc, out = self.run_check("--repo", self.repo)
        self.assertEqual(rc, 1, out)
        lines = self.fails(out)
        self.assertEqual(len(lines), 1, out)
        self.assertIn("hooks/x.py", lines[0])

    def test_5_a_call_in_an_older_version_counts(self):
        # The call is from 09-01 and the drop is later, so a session started before the drop
        # still holds the call.
        self.called_then_dropped(OLD, LATE)
        rc, out = self.run_check("--repo", self.repo)
        self.assertEqual(rc, 1, out)
        lines = self.fails(out)
        self.assertEqual(len(lines), 1, out)
        self.assertIn("hooks/x.py", lines[0])

    def test_6_side_branch_settings_version_is_ignored(self):
        self.commit(OLD, {"settings.json": settings(), "README.md": "base\n"})
        self.git("checkout", "-q", "-b", "side")
        self.commit(MID, {"settings.json": settings("hooks/z.py"), "hooks/z.py": "print(1)\n"})
        self.commit(LATE, delete=["hooks/z.py"])
        self.git("checkout", "-q", "main")
        self.commit(LATE, {"README.md": "main\n"})
        # -s ours: the side commits become ancestors, but main's settings.json never changes.
        self.git("merge", "-q", "--no-ff", "-s", "ours", "-m", "merge side", "side", date=HEAD)
        rc, out = self.run_check("--repo", self.repo)
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.fails(out), [], out)

    def test_7_shallow_clone_is_unknown(self):
        self.called_then_dropped(MID, LATE)
        shallow = os.path.join(self.root, "shallow")
        self.git("clone", "-q", "--depth", "1", "file://" + self.repo, shallow, cwd=self.root)
        rc, out = self.run_check("--repo", shallow, ci=True)
        self.assertIn("check_hook_stubs: UNKNOWN", out)
        self.assertEqual(rc, 1, "CI set: unknown is red\n" + out)
        rc, out = self.run_check("--repo", shallow)
        self.assertIn("check_hook_stubs: UNKNOWN", out)
        self.assertEqual(rc, 0, "CI unset: unknown is not red\n" + out)

    def test_8_both_script_forms_are_collected(self):
        self.commit(MID, {"settings.json": settings("lint/a.py", "janitor/b.sh"),
                          "lint/a.py": "print(1)\n", "janitor/b.sh": "echo 1\n"})
        self.commit(LATE, {"settings.json": settings()}, delete=["lint/a.py", "janitor/b.sh"])
        self.commit(HEAD, {"README.md": "head\n"})
        rc, out = self.run_check("--repo", self.repo)
        self.assertEqual(rc, 1, out)
        lines = self.fails(out)
        self.assertEqual(len(lines), 2, out)
        self.assertTrue(any("lint/a.py" in ln for ln in lines), out)
        self.assertTrue(any("janitor/b.sh" in ln for ln in lines), out)

    def test_9_unknown_option_fails(self):
        self.called_then_dropped(MID, LATE, stub=True)
        for args in (["--bogus"], ["--repo", self.repo, "--bogus"]):
            with self.subTest(args=args):
                rc, out = self.run_check(*args)
                self.assertEqual(rc, 1, out)
                self.assertNotIn("Traceback", out)

    def test_10_a_command_naming_a_script_no_commit_added_fails_at_any_age(self):
        # The command was added on 09-01. HEAD still names hooks/never.py, which no commit ever added.
        self.commit(OLD, {"settings.json": settings("hooks/never.py")})
        self.commit(HEAD, {"README.md": "head\n"})
        rc, out = self.run_check("--repo", self.repo)
        self.assertEqual(rc, 1, out)
        lines = self.fails(out)
        self.assertEqual(len(lines), 1, out)
        self.assertIn("hooks/never.py", lines[0])

    def test_11_a_call_from_years_back_still_fails(self):
        # No window of any length: a call in 2019, dropped in 2020, still fails at HEAD in 2026.
        self.called_then_dropped(YEARS_OLD, YEARS_DROP)
        rc, out = self.run_check("--repo", self.repo)
        self.assertEqual(rc, 1, out)
        lines = self.fails(out)
        self.assertEqual(len(lines), 1, out)
        self.assertIn("hooks/x.py", lines[0])


if __name__ == "__main__":
    unittest.main()
