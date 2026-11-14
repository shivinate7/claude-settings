#!/usr/bin/env python3
"""Cases for lint/roadmap_ref.py, the one reader of origin/roadmap that fetches a stale ref before it judges.
Standard library only.

    python3 lint/test_roadmap_ref.py

fresh_ref(repo_dir, now=None, fetch=None) returns "" when the ref is fresh or was just fetched, else the note
"read as of HH:MM TZ" (US Central, the time of the last fetch). The ref is stale when .git/FETCH_HEAD is missing or
older than MAX_AGE. A stale ref gets one `git fetch origin roadmap:refs/remotes/origin/roadmap`, bounded by
FETCH_TIMEOUT. A fetch that fails, times out or has no origin gives the note and never raises. `fetch(repo_dir,
timeout)` is the injected fetch: it returns True when the ref was fetched, and returns False or raises when not.

The readers' own cases sit in lint/test_ruled_store.py (StaleRefReadTests) and hooks/test_feedback_inbox.py. This file
holds the helper's cases and the scan that no other product file fetches the roadmap. Each case builds real git repos
under this run's folder, with the fixtures of lint/test_ruled_store.py. No network: every origin is a local path.
"""
import ast
import datetime
import glob
import os
import re
import shutil
import subprocess
import sys
import json
import signal
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "hooks"))
import test_ruled_store as fixture  # noqa: E402  the store and roadmap-ref fixtures (git plumbing, run folder)

# A fixed clock, so no case reads the real one. NOW is 12:45 CST; LAST_FETCH is 11:05 CST.
NOW = datetime.datetime(2026, 11, 13, 18, 45, tzinfo=datetime.timezone.utc).timestamp()
LAST_FETCH = datetime.datetime(2026, 11, 13, 17, 5, tzinfo=datetime.timezone.utc).timestamp()  # 11:05 CST
NOTE = "read as of 11:05 CST"
NOTE_SHAPE = re.compile(r"^read as of \d{2}:\d{2} (CST|CDT)$")
OLD_STORE = fixture.ruling_files({"old": fixture.entry("old")})


def helper():
    """The helper module, imported inside each case so that a case reads the module as it is when the case runs."""
    import roadmap_ref  # noqa: E402
    return roadmap_ref


def counting_fetch(result=True):
    """(fetch, calls): an injected fetch that records each call's repo dir and timeout, and returns `result`."""
    calls = []

    def fetch(repo_dir, timeout):
        calls.append((repo_dir, timeout))
        return result

    return fetch, calls


def fetches_roadmap(text):
    """True when a string is a git fetch of the roadmap: it opens with `git fetch` or `fetch` and names roadmap."""
    return re.match(r"\s*(?:git\s+)?fetch\b.*\broadmap", text, re.S) is not None


def fetch_sites(source):
    """Line numbers of the code in `source` that fetch the roadmap: a string literal that is a fetch command, or a list
    or tuple of strings that holds `fetch` and a roadmap word. Docstrings are skipped: they describe, and run nothing.
    Comments are not in the tree at all, so a comment never counts."""
    tree = ast.parse(source)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docstrings.add(id(first.value))
    sites = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstrings and fetches_roadmap(node.value):
                sites.add(node.lineno)
        elif isinstance(node, (ast.List, ast.Tuple)):
            words = [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
            if "fetch" in words and any("roadmap" in word for word in words):
                sites.add(node.lineno)
    return sorted(sites)


def product_files():
    """The product sources: the Python files of lint/ and hooks/ that are not test files, as repo-relative names."""
    found = []
    for folder in ("lint", "hooks"):
        for path in sorted(glob.glob(os.path.join(REPO, folder, "*.py"))):
            name = os.path.basename(path)
            if not name.startswith(("test_", "_test_")):
                found.append("%s/%s" % (folder, name))
    return found


class FreshRefTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="roadmap_ref_", dir=fixture.run_folder())
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_a_stale_ref_is_fetched_and_the_note_is_empty(self):
        newer = fixture.ruling_files({"old": fixture.entry("old"), "new": fixture.entry("new")})
        origin = fixture.bare_origin(self.root, "fetched", OLD_STORE)
        repo = fixture.clone_with_origin(self.root, "stale", origin, OLD_STORE)
        fixture.point_ref(origin, "refs/heads/roadmap", newer, self.root)
        newest = fixture.git(origin, "rev-parse", "refs/heads/roadmap")
        fixture.without_fetch_head(repo)
        note = helper().fresh_ref(repo, now=NOW)
        self.assertEqual(note, "", "a stale ref that could be fetched gave the note %r, want empty" % note)
        self.assertEqual(fixture.ref_sha(repo), newest, "the stale ref did not move to origin's roadmap commit")

    def test_a_stale_ref_with_no_origin_path_gives_the_note_and_does_not_raise(self):
        repo = fixture.clone_with_origin(self.root, "offline", os.path.join(self.root, "gone.git"), OLD_STORE)
        fixture.set_fetch_head(repo, LAST_FETCH)
        before = fixture.ref_sha(repo)
        note = helper().fresh_ref(repo, now=NOW)
        self.assertEqual(note, NOTE, "a failed fetch gave %r, want %r" % (note, NOTE))
        self.assertEqual(fixture.ref_sha(repo), before, "a failed fetch moved the ref")

    def test_a_repo_with_no_origin_remote_gives_the_note(self):
        repo = fixture.clone_with_origin(self.root, "no-remote", None, OLD_STORE)
        fixture.set_fetch_head(repo, LAST_FETCH)
        note = helper().fresh_ref(repo, now=NOW)
        self.assertEqual(note, NOTE, "a repo with no origin gave %r, want %r" % (note, NOTE))

    def test_a_fresh_ref_starts_no_fetch(self):
        repo = fixture.clone_with_origin(self.root, "fresh", None, OLD_STORE)
        fixture.set_fetch_head(repo, NOW - 30)
        fetch, calls = counting_fetch()
        note = helper().fresh_ref(repo, now=NOW, fetch=fetch)
        self.assertEqual(calls, [], "a fresh ref started %d fetch(es), want none" % len(calls))
        self.assertEqual(note, "", "a fresh ref gave the note %r, want empty" % note)

    def test_the_age_limit_is_sixty_seconds_and_a_missing_fetch_head_is_stale(self):
        module = helper()
        self.assertEqual(module.MAX_AGE, 60, "MAX_AGE is %r, want 60 seconds" % module.MAX_AGE)
        self.assertEqual(module.FETCH_TIMEOUT, 2.0, "FETCH_TIMEOUT is %r, want 2.0 seconds" % module.FETCH_TIMEOUT)
        for label, age, starts in (("missing", None, 1), ("59 s old", 59, 0), ("61 s old", 61, 1)):
            repo = fixture.clone_with_origin(self.root, "age-" + label.split()[0], None, OLD_STORE)
            if age is None:
                fixture.without_fetch_head(repo)
            else:
                fixture.set_fetch_head(repo, NOW - age)
            fetch, calls = counting_fetch()
            module.fresh_ref(repo, now=NOW, fetch=fetch)
            self.assertEqual(len(calls), starts, "a FETCH_HEAD %s: %d fetch(es), want %d" % (label, len(calls), starts))

    def test_a_fetch_cut_at_the_timeout_gives_the_note(self):
        seen = []

        def slow(repo_dir, timeout):
            seen.append(timeout)
            simulated = 10.0  # how long this fetch would take, in seconds; the case waits for nothing
            if simulated > timeout:
                raise subprocess.TimeoutExpired(["git", "fetch"], timeout)
            return True

        repo = fixture.clone_with_origin(self.root, "slow", None, OLD_STORE)
        fixture.set_fetch_head(repo, LAST_FETCH)
        note = helper().fresh_ref(repo, now=NOW, fetch=slow)
        self.assertEqual(seen, [2.0], "the fetch was not bounded at FETCH_TIMEOUT: timeouts %r" % seen)
        self.assertEqual(note, NOTE, "a fetch cut at the timeout gave %r, want %r" % (note, NOTE))

    def test_a_fetch_that_reports_failure_or_raises_gives_the_note(self):
        def refuses(repo_dir, timeout):
            return False

        def errors(repo_dir, timeout):
            raise OSError("no git")

        for label, fetch in (("returns False", refuses), ("raises OSError", errors)):
            with self.subTest(fetch=label):
                repo = fixture.clone_with_origin(self.root, "fail-" + label.split()[1], None, OLD_STORE)
                fixture.set_fetch_head(repo, LAST_FETCH)
                note = helper().fresh_ref(repo, now=NOW, fetch=fetch)
                self.assertEqual(note, NOTE, "a fetch that %s gave %r, want %r" % (label, note, NOTE))

    def test_the_note_names_the_last_fetch_in_central_time_with_dst(self):
        summer = datetime.datetime(2026, 7, 1, 17, 5, tzinfo=datetime.timezone.utc).timestamp()  # 12:05 CDT
        repo = fixture.clone_with_origin(self.root, "summer", None, OLD_STORE)
        fixture.set_fetch_head(repo, summer)
        fetch, _calls = counting_fetch(result=False)
        note = helper().fresh_ref(repo, now=summer + 600, fetch=fetch)
        self.assertEqual(note, "read as of 12:05 CDT", "a July fetch gave %r, want the CDT time" % note)

    def test_a_missing_fetch_head_with_a_failed_fetch_gives_a_timed_note(self):
        repo = fixture.clone_with_origin(self.root, "never", None, OLD_STORE)
        fixture.without_fetch_head(repo)
        fetch, _calls = counting_fetch(result=False)
        note = helper().fresh_ref(repo, now=NOW, fetch=fetch)
        self.assertRegex(note, NOTE_SHAPE, "a ref never fetched gave %r, want read as of HH:MM CST or CDT" % note)

    def test_only_the_helper_fetches_the_roadmap(self):
        scanned = product_files()
        self.assertIn("lint/ruled_store.py", scanned, "the scan does not reach lint/ruled_store.py")
        self.assertIn("hooks/feedback_guard.py", scanned, "the scan does not reach hooks/feedback_guard.py")
        flagged = {}
        for rel in scanned:
            with open(os.path.join(REPO, rel), encoding="utf-8", errors="replace") as f:
                sites = fetch_sites(f.read())
            if sites:
                flagged[rel] = sites
        self.assertIn("lint/roadmap_ref.py", flagged, "lint/roadmap_ref.py holds no fetch of the roadmap")
        extra = {rel: flagged[rel] for rel in flagged if rel != "lint/roadmap_ref.py"}
        self.assertEqual(extra, {}, "product files outside the helper fetch the roadmap (file: lines): %r" % extra)

    def test_the_scan_flags_a_fetch_argv_and_ignores_docstrings_comments_and_messages(self):
        argv = "def f():\n    return ['git', 'fetch', 'origin', 'roadmap:refs/x']\n"
        command = "CMD = 'git fetch origin roadmap:refs/x'\n"
        docstring = "def f():\n    '''Reads the roadmap, never fetched: git fetch roadmap is not run here.'''\n    return 1\n"
        message = "NOTE = 'run `git fetch origin %s` to refresh'\n"
        comment = "# git fetch origin roadmap\nX = 1\n"
        self.assertEqual(fetch_sites(argv), [2], "an argv fetch of the roadmap was not flagged")
        self.assertEqual(fetch_sites(command), [1], "a fetch command string was not flagged")
        self.assertEqual(fetch_sites(docstring), [], "a docstring that describes a fetch was flagged")
        self.assertEqual(fetch_sites(message), [], "a message that names a fetch for the owner was flagged")
        self.assertEqual(fetch_sites(comment), [], "a comment was flagged")


LINT = HERE
FAKE_GIT = r'''
import json, os, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(sys.argv[0]))
with open(os.path.join(HERE, "conf.json"), encoding="utf-8") as handle:
    conf = json.load(handle)
argv = sys.argv[1:]
verb = next((word for word in argv if word in ("fetch", "log")), "")
try:
    devnull = os.path.samestat(os.fstat(0), os.stat(os.devnull))
except OSError:
    devnull = None
record = {"verb": verb, "stdin_devnull": devnull,
          "env": {key: os.environ.get(key) for key in ("GIT_TERMINAL_PROMPT", "GIT_ASKPASS", "GIT_SSH_COMMAND")}}
with open(conf["log"], "a", encoding="utf-8") as handle:
    handle.write(json.dumps(record) + "\n")
if verb == "fetch" and conf["hang"]:
    if conf["grandchild"]:
        child = subprocess.Popen(["sleep", "30"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
        with open(conf["pid"], "w", encoding="utf-8") as handle:
            handle.write(str(child.pid))
    time.sleep(30)
sys.exit(1)
'''


def make_fake_git(folder, hang=False, grandchild=False):
    """A `git` for one case, to put first on PATH. Each start appends its verb, its stdin and the git environment to
    starts.log. A fetch with `hang` sleeps past FETCH_TIMEOUT; with `grandchild` it first starts a child and writes the
    child's pid to grandchild.pid. Returns (folder, starts.log, grandchild.pid)."""
    os.makedirs(folder)
    log, pid = os.path.join(folder, "starts.log"), os.path.join(folder, "grandchild.pid")
    with open(os.path.join(folder, "conf.json"), "w", encoding="utf-8") as handle:
        json.dump({"log": log, "pid": pid, "hang": hang, "grandchild": grandchild}, handle)
    path = os.path.join(folder, "git")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("#!%s\n" % sys.executable + FAKE_GIT)
    os.chmod(path, 0o755)
    return folder, log, pid


def git_starts(log, verb):
    """The records of the starts with `verb` that the fake git logged, oldest first."""
    if not os.path.exists(log):
        return []
    with open(log, encoding="utf-8") as handle:
        records = [json.loads(line) for line in handle if line.strip()]
    return [record for record in records if record["verb"] == verb]


def on_path(folder):
    """The PATH with `folder` first, for mock.patch.dict."""
    return {"PATH": folder + os.pathsep + os.environ.get("PATH", "")}


def alive(pid):
    """True while `pid` runs. A zombie, exited but not yet reaped, is not running."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    stat = "/proc/%d/stat" % pid
    if os.path.exists(stat):
        try:
            return proc_state(pid) != "Z"
        except OSError:  # reaped between the kill probe and the read
            return False
    return True


def proc_state(pid):
    """The state letter in /proc/<pid>/stat, or "no /proc entry" when there is none."""
    try:
        with open("/proc/%d/stat" % pid, encoding="utf-8") as handle:
            return handle.read().rsplit(")", 1)[1].split()[0]
    except OSError:
        return "no /proc entry"


# A group member that SIGKILL reaches leaves the running state within about a millisecond. The bound is for a loaded
# runner: a process still running at the bound is the failure, and its state is named in the message.
GONE_BOUND = 5.0  # seconds
GONE_STEP = 0.02  # seconds between polls


def wait_until_dead(pid, bound=GONE_BOUND):
    """True once `pid` is no longer running (gone, or a zombie), polled every GONE_STEP seconds up to `bound` seconds."""
    end = time.monotonic() + bound
    while alive(pid):
        if time.monotonic() >= end:
            return False
        time.sleep(GONE_STEP)
    return True


def kill_quietly(pid):
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


class FetchRuleTests(unittest.TestCase):
    """The roadmap ref is fresh only when FETCH_HEAD names the roadmap branch. A fresh FETCH_HEAD of another branch
    says nothing about the roadmap, so the roadmap is fetched."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="roadmap_rule_", dir=fixture.run_folder())
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_a_fresh_fetch_head_of_another_branch_is_not_a_fresh_roadmap(self):
        repo = fixture.clone_with_origin(self.root, "master-only", None, OLD_STORE)
        fixture.write_fetch_head(repo, "master", NOW - 30)
        fetch, calls = counting_fetch()
        helper().fresh_ref(repo, now=NOW, fetch=fetch)
        self.assertEqual(len(calls), 1, "a fresh FETCH_HEAD of master counted as a fresh roadmap: %d roadmap fetch(es),"
                         " want 1" % len(calls))

    def test_a_fresh_roadmap_line_starts_no_fetch(self):
        repo = fixture.clone_with_origin(self.root, "roadmap-fresh", None, OLD_STORE)
        fixture.write_fetch_head(repo, "roadmap", NOW - 30)
        fetch, calls = counting_fetch()
        note = helper().fresh_ref(repo, now=NOW, fetch=fetch)
        self.assertEqual(calls, [], "a fresh roadmap line started %d fetch(es), want none" % len(calls))
        self.assertEqual(note, "", "a fresh roadmap line gave the note %r, want empty" % note)


@unittest.skipUnless(os.name == "posix", "the fake git is a POSIX script, and a process group is a POSIX notion")
class FetchProcessTests(unittest.TestCase):
    """The fetch child runs in its own process group, which a timeout kills whole. It reads no prompt and no stdin."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="roadmap_proc_", dir=fixture.run_folder())
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_a_timed_out_fetch_is_killed_with_its_process_group(self):
        folder, _log, pid_file = make_fake_git(os.path.join(self.root, "hang-group"), hang=True, grandchild=True)
        repo = fixture.clone_with_origin(self.root, "group", None, OLD_STORE)
        with mock.patch.dict(os.environ, on_path(folder)):
            helper().fresh_ref(repo, now=NOW)
        self.assertTrue(os.path.exists(pid_file), "the fake fetch never started its grandchild")
        with open(pid_file, encoding="utf-8") as handle:
            grandchild = int(handle.read())
        self.addCleanup(kill_quietly, grandchild)
        self.assertTrue(wait_until_dead(grandchild), "the fetch's grandchild still ran %ss after the timeout: its process"
                        " group was not killed; /proc state %s" % (GONE_BOUND, proc_state(grandchild)))

    def fetch_env(self, name, preset=None):
        """The environment one roadmap fetch starts with, after one fresh_ref with no value preset for the git
        variables, or with `preset` (a dict) added to the environment."""
        folder, log, _pid = make_fake_git(os.path.join(self.root, name))
        repo = fixture.clone_with_origin(self.root, name + "-repo", None, OLD_STORE)
        with mock.patch.dict(os.environ, dict(on_path(folder), **(preset or {}))):
            if not preset:
                for key in ("GIT_TERMINAL_PROMPT", "GIT_ASKPASS", "GIT_SSH_COMMAND"):
                    os.environ.pop(key, None)
            helper().fresh_ref(repo, now=NOW)
        fetches = git_starts(log, "fetch")
        self.assertEqual(len(fetches), 1, "control: the roadmap fetch starts: %r, want one" % fetches)
        return fetches[0]["env"]

    def test_the_fetch_never_prompts_for_a_password(self):
        env = self.fetch_env("prompt")
        self.assertEqual(env["GIT_TERMINAL_PROMPT"], "0", "the fetch may prompt: GIT_TERMINAL_PROMPT is %r"
                         % env["GIT_TERMINAL_PROMPT"])

    def test_the_fetch_askpass_is_a_no_op(self):
        env = self.fetch_env("askpass")
        self.assertEqual(env["GIT_ASKPASS"], "true", "GIT_ASKPASS is %r, want the no-op true" % env["GIT_ASKPASS"])

    def test_the_fetch_ssh_is_batch_mode(self):
        env = self.fetch_env("batch")
        self.assertIn("BatchMode=yes", env["GIT_SSH_COMMAND"] or "", "GIT_SSH_COMMAND is %r, want BatchMode=yes"
                      % env["GIT_SSH_COMMAND"])

    def test_a_preset_ssh_command_is_kept(self):
        folder, log, _pid = make_fake_git(os.path.join(self.root, "ssh"))
        repo = fixture.clone_with_origin(self.root, "ssh-repo", None, OLD_STORE)
        with mock.patch.dict(os.environ, dict(on_path(folder), GIT_SSH_COMMAND="ssh -i /fixture/key")):
            helper().fresh_ref(repo, now=NOW)
        fetches = git_starts(log, "fetch")
        self.assertEqual(len(fetches), 1, "control: the roadmap fetch did not start: %r" % fetches)
        self.assertEqual(fetches[0]["env"]["GIT_SSH_COMMAND"], "ssh -i /fixture/key",
                         "a preset GIT_SSH_COMMAND was replaced")

    def test_the_fetch_child_reads_no_stdin_of_its_parent(self):
        folder, log, _pid = make_fake_git(os.path.join(self.root, "stdin"))
        repo = fixture.clone_with_origin(self.root, "stdin-repo", None, OLD_STORE)
        code = ("import sys; sys.path.insert(0, sys.argv[1]); import roadmap_ref; "
                "roadmap_ref.fresh_ref(sys.argv[2], now=float(sys.argv[3]))")
        env = dict(os.environ, PATH=folder + os.pathsep + os.environ.get("PATH", ""))
        done = subprocess.run([sys.executable, "-c", code, LINT, repo, repr(NOW)], input=b"", env=env,
                              capture_output=True, timeout=60)
        self.assertEqual(done.returncode, 0, "the child that reads the ref failed: %s"
                         % done.stderr.decode("utf-8", "replace")[-300:])
        fetches = git_starts(log, "fetch")
        self.assertEqual(len(fetches), 1, "control: the roadmap fetch did not start: %r" % fetches)
        self.assertIs(fetches[0]["stdin_devnull"], True, "the fetch read its parent's stdin, not /dev/null")

    def test_a_timed_out_fetch_is_not_followed_by_a_tip_read(self):
        folder, log, _pid = make_fake_git(os.path.join(self.root, "tip"), hang=True)
        repo = fixture.clone_with_origin(self.root, "tip-repo", None, OLD_STORE)
        fixture.without_fetch_head(repo)
        with mock.patch.dict(os.environ, on_path(folder)):
            note = helper().fresh_ref(repo, now=NOW)
        self.assertEqual(len(git_starts(log, "fetch")), 1, "control: the roadmap fetch did not start")
        tips = git_starts(log, "log")
        self.assertEqual(tips, [], "a timed-out fetch was followed by %d tip read(s): a second wait of up to"
                         " FETCH_TIMEOUT" % len(tips))
        self.assertTrue(note.startswith("read as of "), "the note is %r" % note)


READERS = ("lint/ruled_store.py", "hooks/feedback_guard.py", "hooks/sendmessage_state.py", "hooks/override.py",
           "hooks/question_form.py")


def calls_fresh_ref(source):
    """True when `source` calls fresh_ref, as an attribute or a name. A mention in a string or a docstring is no call."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name == "fresh_ref":
                return True
    return False


class ReaderScanTests(unittest.TestCase):
    def test_the_scan_sees_a_call_and_no_mention(self):
        self.assertTrue(calls_fresh_ref("import roadmap_ref\nroadmap_ref.fresh_ref(repo)\n"), "a call was not seen")
        self.assertFalse(calls_fresh_ref('"""fresh_ref is read here."""\nx = 1\n'), "a docstring mention counted")

    def test_each_reader_of_the_roadmap_calls_fresh_ref(self):
        for rel in READERS:
            with self.subTest(reader=rel):
                self.assertTrue(os.path.exists(os.path.join(REPO, rel)), "scope: %s is not in the repo" % rel)
                with open(os.path.join(REPO, rel), encoding="utf-8", errors="replace") as handle:
                    source = handle.read()
                self.assertTrue(calls_fresh_ref(source), "%s reads origin/roadmap without calling"
                                " roadmap_ref.fresh_ref" % rel)


def tearDownModule():
    for folder in fixture._RUN:
        shutil.rmtree(folder, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    unittest.main(verbosity=2)
