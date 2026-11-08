#!/usr/bin/env python3
"""Cases for the `lane-lint-push` rule in hooks/guard.py, a PreToolUse Bash hook. Standard library and unittest.

Run it from the repository root:

    python3 hooks/test_guard_lane_lint_push.py

GUARD_UNDER_TEST points the run at another copy of the guard, as in hooks/test_guard.py.

WHAT IT PROVES. Before a `git push` leaves, the guard runs the lane lint's fast range check, the silent-undo
check (lint/check_silent_undo.py), on the pushed head against origin's default branch. It runs the command that
CI's silent-undo step names in the workflow file of the pushed head, with the step's own env. A range that
fails is refused before the push runs. A range that cannot be read (UNKNOWN) is allowed, with one guard.log line
and one stderr line that say unknown. A push the lint does not judge starts no lint.

THE SEAMS THE GUARD HONORS.
  CAP_ENV          seconds one lint run may take, read from the guard's environment. Case 7b sets it to 1 and
                   runs a lint step that sleeps. A guard that reads no such name waits for its own default cap,
                   and the case still passes once the lint is cut.
  LINT_TOKEN       a lint launch is a child whose argv names check_silent_undo or undo_step_stub.
  Launch counts    the guard's own process starts: its children, and each git read it makes. A probe runs the
                   guard as __main__ in a child, with subprocess.Popen recorded. PUSH_LAUNCHES_BEFORE and
                   NON_PUSH_LAUNCHES are measured before the lane lint, on the fixtures of cases 8a and 8b.
                   LINT_LAUNCHES is what one lint run adds: one child, whose git reads run inside that child and
                   are not the guard's starts. A lint run built in-process would count its git reads here, so
                   that design changes these constants and its record.

FIXTURES. Each case builds its own repository under the run folder: a bare origin, a clone, a
lint/check_silent_undo.py that runs the product's own check at its real path, and .github/workflows/checks.yml.
The workflow is read from the pushed head, as CI reads a pull request's head.
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
REPO = os.path.dirname(HERE)
GUARD = os.environ.get("GUARD_UNDER_TEST") or os.path.join(HERE, "guard.py")
REAL_UNDO = os.path.join(REPO, "lint", "check_silent_undo.py")
sys.path.insert(0, os.path.join(REPO, "lint"))
sys.path.insert(0, os.path.join(REPO, "testing"))
import _test_git  # noqa: E402,F401  the one home of the test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per test run (lint/_test_temp.py)
import shallow_clone  # noqa: E402  the one shallow-clone fixture (testing/shallow_clone.py)

RUN = _test_temp.run_folder()

RULE = "lane-lint-push"
CAP_ENV = "LANE_LINT_PUSH_SECONDS"
LINT_TOKEN = re.compile(r"check_silent_undo|undo_step_stub")
PUSH_LAUNCHES_BEFORE = 10  # a clean push's guard launches, measured before the lane lint (case 8b's fixture)
NON_PUSH_LAUNCHES = 9      # a `git commit` call's guard launches, measured before the lane lint (case 8a's command)
LINT_LAUNCHES = 1          # what one lint run adds to a push's launches: one child process

GIT = ["git", "-c", "user.name=lane-lint test", "-c", "user.email=lane-lint-test@example.invalid"]
NOTES = "alpha\nbeta\n"
DELTA_NOTES = NOTES + "delta\n"
STUB_REL = "lint/undo_step_stub.py"
SHIM = ("#!/usr/bin/env python3\n"
        "# A fixture's lint/check_silent_undo.py: runs the product's own check, so the fixture reads what CI reads.\n"
        "import runpy\n"
        "runpy.run_path(%r, run_name=\"__main__\")\n" % REAL_UNDO)
SILENT_RUN = 'python3 lint/check_silent_undo.py --upstream "origin/$BASE_REF" --head "$HEAD_SHA" --strict'
STUB_RUN = 'python3 lint/undo_step_stub.py --upstream "origin/$BASE_REF" --head "$HEAD_SHA" --strict'

PROBE = r"""
import json, runpy, subprocess, sys
guard, log = sys.argv[1], sys.argv[2]
starts = []
real_popen = subprocess.Popen


class RecordingPopen(real_popen):
    def __init__(self, args, *rest, **kwargs):
        argv = args if isinstance(args, (list, tuple)) else [args]
        starts.append({"argv": [str(a) for a in argv], "cwd": str(kwargs.get("cwd") or "")})
        super().__init__(args, *rest, **kwargs)


subprocess.Popen = RecordingPopen
sys.argv = [guard]
try:
    runpy.run_path(guard, run_name="__main__")
finally:
    with open(log, "w", encoding="utf-8") as handle:
        json.dump(starts, handle)
"""


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def git(where, *args):
    done = subprocess.run(GIT + list(args), cwd=where, capture_output=True, text=True)
    if done.returncode:
        raise RuntimeError("fixture setup failed: git %s in %s: %s" % (" ".join(args), where, done.stderr.strip()))
    return done.stdout.strip()


def commit(where, files, subject, body=""):
    for rel, text in files.items():
        write(os.path.join(where, rel), text)
    git(where, "add", "-A")
    git(where, "commit", "-q", "-m", subject + ("\n\n" + body if body else ""))


def workflow(run=SILENT_RUN):
    """checks.yml with the silent-undo step's run line set to `run`. None: a workflow with no such step."""
    text = ("name: checks\non: [pull_request]\njobs:\n  checks:\n    runs-on: ubuntu-latest\n    steps:\n"
            "      - uses: actions/checkout@v4\n        with:\n          fetch-depth: 0\n")
    if run is None:
        return text + "      - name: Mod version bump\n        run: python3 lint/check_mod_versions.py\n"
    return text + ("      - name: Silent undo check\n"
                   "        if: ${{ github.event_name == 'pull_request' }}\n"
                   "        env:\n"
                   "          BASE_REF: ${{ github.base_ref }}\n"
                   "          HEAD_SHA: ${{ github.event.pull_request.head.sha }}\n"
                   "        run: %s\n" % run)


def stub_program(seen, lines, code, sleep_s=0):
    """A fixture stand-in for the lint step's program. It records its argv in `seen`, prints `lines`, waits
    `sleep_s` seconds and exits `code`. It is not the product."""
    return ("#!/usr/bin/env python3\n"
            "# A fixture stand-in for the lint step's program (hooks/test_guard_lane_lint_push.py). Not the product.\n"
            "import json, sys, time\n"
            "with open(%r, 'w', encoding='utf-8') as handle:\n"
            "    json.dump(sys.argv[1:], handle)\n"
            "time.sleep(%r)\n"
            "for line in %r:\n"
            "    print(line)\n"
            "sys.exit(%r)\n" % (seen, sleep_s, list(lines), code))


def base_repo(case, run=SILENT_RUN):
    """A bare origin and a clone whose `main` holds the base files and the workflow, pushed to origin."""
    origin = os.path.join(case, "origin.git")
    clone = os.path.join(case, "clone")
    git(case, "init", "-q", "--bare", "-b", "main", origin)
    git(case, "init", "-q", "-b", "main", clone)
    git(clone, "remote", "add", "origin", origin)
    commit(clone, {"notes.txt": NOTES, "policy.txt": "v1\n", "lint/check_silent_undo.py": SHIM,
                   ".github/workflows/checks.yml": workflow(run)}, "main: base")
    git(clone, "push", "-q", "origin", "main")
    git(clone, "remote", "set-head", "origin", "main")
    return clone, origin


def drop_repo(case, pushed=False, run=SILENT_RUN, lane_step=None, merge_body=""):
    """Branch `topic` holds a lane commit, then merges origin/main's later commit and drops the line main added
    (notes.txt), so the merge reads as a silent undo. origin/topic is the lane commit. With `pushed`, the merge
    is pushed to origin/topic first, and one more lane commit is left to push. `lane_step` is a (run, stub
    text) pair the lane commits to its own workflow before the merge. `merge_body` is the merge message's body."""
    clone, _origin = base_repo(case, run)
    git(clone, "checkout", "-q", "-b", "topic")
    if lane_step is not None:
        commit(clone, {".github/workflows/checks.yml": workflow(lane_step[0]), STUB_REL: lane_step[1]},
               "lane: its own lint step")
    commit(clone, {"lane.txt": "lane work\n"}, "lane: add lane.txt")
    git(clone, "push", "-q", "origin", "topic")
    git(clone, "checkout", "-q", "main")
    commit(clone, {"notes.txt": DELTA_NOTES}, "main adds delta")
    git(clone, "push", "-q", "origin", "main")
    git(clone, "checkout", "-q", "topic")
    git(clone, "merge", "-q", "--no-ff", "--no-commit", "origin/main")
    commit(clone, {"notes.txt": NOTES}, "merge main into lane", merge_body)
    if pushed:
        git(clone, "push", "-q", "origin", "topic")
        commit(clone, {"more.txt": "more\n"}, "lane: more")
    return clone


def revert_repo(case, existing_topic):
    """main's commit X sets policy.txt to v2. The lane reverts X: on a new branch `lane` cut from main
    (existing_topic False), or on `topic`, whose origin/topic predates X, after a merge of main (True)."""
    clone, _origin = base_repo(case)
    if existing_topic:
        git(clone, "checkout", "-q", "-b", "topic")
        commit(clone, {"lane.txt": "lane work\n"}, "lane: add lane.txt")
        git(clone, "push", "-q", "origin", "topic")
        git(clone, "checkout", "-q", "main")
    commit(clone, {"policy.txt": "v2\n"}, "main X: policy v2")
    git(clone, "push", "-q", "origin", "main")
    if existing_topic:
        git(clone, "checkout", "-q", "topic")
        git(clone, "merge", "-q", "--no-ff", "--no-commit", "origin/main")
        git(clone, "commit", "-q", "-m", "merge main into lane")
        git(clone, "revert", "--no-edit", "origin/main")
    else:
        git(clone, "checkout", "-q", "-b", "lane")
        git(clone, "revert", "--no-edit", "HEAD")
    return clone


def clean_repo(case, commits=2, name="lane-clean"):
    """Branch `name` holds `commits` ordinary commits on top of main, and nothing is pushed yet."""
    clone, _origin = base_repo(case)
    git(clone, "checkout", "-q", "-b", name)
    for index in range(commits):
        commit(clone, {"lane-%d.txt" % index: "lane %d\n" % index}, "lane: add lane-%d.txt" % index)
    return clone


def shallow_repo(case):
    """A clone cut to one commit (depth 1) of origin, on a new branch with one clean commit on top."""
    clone, origin = base_repo(case)
    main_sha = git(clone, "rev-parse", "main")
    shallow = os.path.join(case, "shallow")
    error = shallow_clone.make(origin, shallow, main_sha)
    if error:
        raise RuntimeError("fixture setup failed: the shallow clone: %s" % error)
    git(shallow, "checkout", "-q", "-b", "lane-shallow")
    commit(shallow, {"lane.txt": "lane work\n"}, "lane: add lane.txt")
    return shallow


def real_undo(where, upstream):
    """(exit code, stdout) of the real silent-undo check over `upstream`..HEAD in `where`, with --strict."""
    done = subprocess.run([sys.executable, REAL_UNDO, "--repo", where, "--upstream", upstream, "--head", "HEAD",
                           "--strict"], cwd=where, capture_output=True, text=True)
    return done.returncode, done.stdout


def scope(condition, message):
    """A fixture that does not hold the scope a case names is a fixture error, not a verdict."""
    if not condition:
        raise RuntimeError("fixture scope: " + message)


class Outcome:
    def __init__(self, decision="", reason="", stderr="", starts=(), notes=(), error=""):
        self.decision, self.reason, self.stderr = decision, reason, stderr
        self.starts, self.notes, self.error = list(starts), list(notes), error


def read_decision(stdout):
    out = stdout.strip()
    if not out:
        return "allow", ""
    try:
        block = json.loads(out)["hookSpecificOutput"]
        return block["permissionDecision"], block.get("permissionDecisionReason", "")
    except (ValueError, KeyError, TypeError):
        return "unparsed", out[:200]


def guard_run(case, clone, command, env=None):
    """Judge one Bash call from the clone, under the guard under test, in a fresh config folder."""
    cfg = tempfile.mkdtemp(prefix="cfg-", dir=case)
    spawn_log = os.path.join(cfg, "spawns.json")
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": clone})
    environ = dict(os.environ)
    for name in ("TMPDIR", "TEMP", "TMP"):
        environ[name] = case
    for name in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_REMOTE_SESSION_ID", "CLAUDE_CODE_REMOTE",
                 "CLAUDE_PROJECT_DIR", CAP_ENV):
        environ.pop(name, None)
    environ.update({"CLAUDE_CONFIG_DIR": cfg, "CLAUDE_GUARD_ROOT_PID": str(os.getpid())})
    environ.update(env or {})
    try:
        done = subprocess.run([sys.executable, "-c", PROBE, GUARD, spawn_log], input=payload,
                              capture_output=True, text=True, env=environ, timeout=180)
    except subprocess.TimeoutExpired:
        return Outcome(error="the guard ran past 180 s")
    if done.returncode != 0:
        return Outcome(error="the guard exited %d: %s" % (done.returncode, done.stderr.strip()[-300:]))
    decision, reason = read_decision(done.stdout)
    starts = []
    if os.path.exists(spawn_log):
        with open(spawn_log, encoding="utf-8") as handle:
            starts = json.load(handle)
    lines = []
    log = os.path.join(cfg, "guard.log")
    if os.path.exists(log):
        with open(log, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    return Outcome(decision, reason, done.stderr, starts, [line for line in lines if RULE in line])


def lint_starts(out):
    return [s for s in out.starts if any(LINT_TOKEN.search(part) for part in s["argv"])]


def seen_argv(case):
    """The argv a stand-in lint program recorded in `case`, or None when it never ran."""
    path = os.path.join(case, "seen.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def tearDownModule():
    shutil.rmtree(RUN, ignore_errors=True)


class LaneLintCase(unittest.TestCase):
    def case(self):
        return tempfile.mkdtemp(prefix="case-", dir=RUN)

    def assert_denied(self, out, finding_file, lints=1):
        """Each part is its own subtest, so a failure names the one cause it shows."""
        with self.subTest("the guard ran"):
            self.assertEqual(out.error, "", "the guard did not run: %s" % out.error)
        with self.subTest("the push is refused"):
            self.assertEqual(out.decision, "deny", "the push was allowed, want a refusal by rule %s" % RULE)
        with self.subTest("the refusal names the rule"):
            self.assertIn(RULE, out.reason, "the refusal does not name rule %s" % RULE)
        with self.subTest("the refusal names the file that holds the finding"):
            self.assertIn(finding_file, out.reason, "the refusal does not name %s" % finding_file)
        with self.subTest("the lint runs once before the refusal"):
            self.assertEqual(len(lint_starts(out)), lints, "lint launches before the refusal")

    def assert_allowed(self, out, lints=None):
        with self.subTest("the guard ran"):
            self.assertEqual(out.error, "", "the guard did not run: %s" % out.error)
        with self.subTest("the push is allowed"):
            self.assertEqual(out.decision, "allow", "the push was refused: %s" % out.reason[:200])
        if lints is not None:
            with self.subTest("the lint launches on the push"):
                self.assertEqual(len(lint_starts(out)), lints, "lint launches on an allowed push")

    def assert_unknown_note(self, out):
        """An unknown lint allows the push, with one guard.log line and one stderr line that say unknown."""
        with self.subTest("an unknown lint does not refuse"):
            self.assertEqual(out.decision, "allow", "an unknown lint refused the push: %s" % out.reason[:200])
        with self.subTest("one guard.log line for the rule, and it says unknown"):
            self.assertEqual(len(out.notes), 1, "guard.log lines for %s, want exactly one" % RULE)
            self.assertIn("unknown", out.notes[0].lower(), "the guard.log line does not say unknown")
        with self.subTest("one stderr line says unknown"):
            said = [line for line in out.stderr.splitlines() if "unknown" in line.lower()]
            self.assertEqual(len(said), 1, "stderr lines that say unknown, want exactly one")


class DenyCases(LaneLintCase):
    def test_1a_merge_that_drops_a_main_line_is_refused_before_it_leaves(self):
        case = self.case()
        clone = drop_repo(case)
        code, stdout = real_undo(clone, "origin/main")
        scope(code == 1 and "notes.txt" in stdout, "the real check does not fail the merge against origin/main")
        out = guard_run(case, clone, "git push origin topic")
        self.assert_denied(out, "notes.txt")

    def test_1b_bad_merge_already_on_the_remote_branch_refuses_a_clean_commit_sent_on_top(self):
        case = self.case()
        clone = drop_repo(case, pushed=True)
        code, _stdout = real_undo(clone, "origin/main")
        scope(code == 1, "the real check does not fail the merge against origin/main")
        code, _stdout = real_undo(clone, "origin/topic")
        scope(code == 0, "the real check fails against origin/topic, so the tracking-ref trap is not set")
        out = guard_run(case, clone, "git push origin topic")
        self.assert_denied(out, "notes.txt")

    def test_2a_pushed_revert_of_a_main_commit_is_refused(self):
        case = self.case()
        clone = revert_repo(case, existing_topic=False)
        code, stdout = real_undo(clone, "origin/main")
        scope(code == 1 and "policy.txt" in stdout, "the real check does not fail the revert against origin/main")
        out = guard_run(case, clone, "git push origin lane")
        self.assert_denied(out, "policy.txt")

    def test_2b_revert_of_a_main_commit_on_an_existing_branch_is_refused(self):
        case = self.case()
        clone = revert_repo(case, existing_topic=True)
        code, stdout = real_undo(clone, "origin/main")
        scope(code == 1 and "policy.txt" in stdout, "the real check does not fail the revert against origin/main")
        code, _stdout = real_undo(clone, "origin/topic")
        scope(code == 0, "the real check fails against origin/topic, so the tracking-ref trap is not set")
        out = guard_run(case, clone, "git push origin topic")
        self.assert_denied(out, "policy.txt")


class AllowCases(LaneLintCase):
    def test_3_clean_lane_push_is_allowed_and_linted_once(self):
        for commits in (2, 25):
            with self.subTest(commits=commits):
                case = self.case()
                clone = clean_repo(case, commits=commits)
                code, _stdout = real_undo(clone, "origin/main")
                scope(code == 0, "the real check fails the clean lane")
                out = guard_run(case, clone, "git push origin lane-clean")
                self.assert_allowed(out, lints=LINT_LAUNCHES)

    def test_3b_push_with_nothing_to_send_is_allowed(self):
        case = self.case()
        clone = clean_repo(case, commits=1)
        git(clone, "push", "-q", "origin", "lane-clean")
        scope(git(clone, "rev-list", "origin/lane-clean..lane-clean") == "", "the push still has commits to send")
        out = guard_run(case, clone, "git push origin lane-clean")
        self.assert_allowed(out)

    def test_4_shallow_clone_pushing_a_clean_commit_is_allowed_with_one_unknown_note(self):
        case = self.case()
        clone = shallow_repo(case)
        code, stdout = real_undo(clone, "origin/main")
        scope(code == 1 and "UNKNOWN" in stdout, "the real check does not read the shallow clone as UNKNOWN")
        out = guard_run(case, clone, "git push origin lane-shallow")
        self.assert_allowed(out, lints=LINT_LAUNCHES)
        self.assert_unknown_note(out)

    def test_5_drops_lines_trailer_excuses_the_drop(self):
        case = self.case()
        clone = drop_repo(case, merge_body="Drops-lines: notes.txt -- the lane removes the line main added")
        code, stdout = real_undo(clone, "origin/main")
        scope(code == 0 and "ALLOWED" in stdout, "the real check does not excuse the drop with the trailer")
        out = guard_run(case, clone, "git push origin topic")
        self.assert_allowed(out, lints=LINT_LAUNCHES)


class SkipCases(LaneLintCase):
    def test_6_pushes_the_lint_does_not_judge_start_no_lint(self):
        case = self.case()
        clone = drop_repo(case)
        git(clone, "push", "-q", "origin", "topic~1:refs/heads/gone")
        git(clone, "tag", "lint-skip-tag", "topic")
        skipped = (
            ("dry run", "git push --dry-run origin topic"),
            ("delete", "git push origin --delete gone"),
            ("tag push", "git push origin refs/tags/lint-skip-tag"),
            ("destination archive/*", "git push origin topic:archive/topic"),
        )
        for label, command in skipped:
            with self.subTest(label):
                out = guard_run(case, clone, command)
                self.assert_allowed(out, lints=0)
        with self.subTest("record branch"):
            out = guard_run(case, clone, "git push origin topic:roadmap")
            self.assertEqual(out.error, "", "the guard did not run: %s" % out.error)
            self.assertNotIn(RULE, out.reason, "the record-branch push was judged by %s" % RULE)
            self.assertEqual(len(lint_starts(out)), 0, "lint launches on a record-branch push")
        with self.subTest("control: the same merge, pushed plainly, is linted"):
            out = guard_run(case, clone, "git push origin topic")
            self.assert_denied(out, "notes.txt")


class UnknownCases(LaneLintCase):
    def test_7a_a_ref_other_than_head_is_unknown_and_allowed(self):
        case = self.case()
        clone = drop_repo(case)
        git(clone, "checkout", "-q", "-b", "other", "origin/main")
        commit(clone, {"lane-other.txt": "other\n"}, "lane: other")
        out = guard_run(case, clone, "git push origin topic:topic")
        self.assert_unknown_note(out)

    def test_7b_a_lint_run_past_the_time_cap_is_unknown_and_allowed(self):
        case = self.case()
        clone = drop_repo(case, lane_step=(STUB_RUN, stub_program(os.path.join(case, "seen.json"), [], 0,
                                                                   sleep_s=600)))
        scope(seen_argv(case) is None, "the stand-in ran before the push")
        out = guard_run(case, clone, "git push origin topic", env={CAP_ENV: "1"})
        self.assert_allowed(out, lints=LINT_LAUNCHES)
        self.assert_unknown_note(out)

    def test_7c_a_workflow_with_no_silent_undo_step_is_unknown_and_allowed(self):
        case = self.case()
        clone = drop_repo(case, run=None)
        out = guard_run(case, clone, "git push origin topic")
        self.assert_allowed(out, lints=0)
        self.assert_unknown_note(out)


class CostCases(LaneLintCase):
    def test_8a_a_non_push_call_starts_no_added_process(self):
        case = self.case()
        clone = clean_repo(case, commits=1)
        out = guard_run(case, clone, "git commit -m 'lane: note'")
        self.assertEqual(out.error, "", "the guard did not run: %s" % out.error)
        self.assertEqual(out.decision, "allow", "the commit call was refused: %s" % out.reason[:200])
        self.assertEqual(len(out.starts), NON_PUSH_LAUNCHES,
                         "guard launches for a non-push call, want %d (the old count: no lint on a non-push)"
                         % NON_PUSH_LAUNCHES)

    def test_8b_a_push_starts_only_the_processes_the_record_names(self):
        case = self.case()
        clone = clean_repo(case, commits=2)
        out = guard_run(case, clone, "git push origin lane-clean")
        self.assert_allowed(out)
        want = PUSH_LAUNCHES_BEFORE + LINT_LAUNCHES
        self.assertEqual(len(out.starts), want,
                         "guard launches for a clean push, want %d (%d before the lint, plus %d lint launch)"
                         % (want, PUSH_LAUNCHES_BEFORE, LINT_LAUNCHES))


class StepCases(LaneLintCase):
    def test_9a_the_guard_runs_the_command_the_step_names(self):
        case = self.case()
        seen = os.path.join(case, "seen.json")
        clone = clean_repo(case, commits=2)
        commit(clone, {".github/workflows/checks.yml": workflow(STUB_RUN),
                       STUB_REL: stub_program(seen, ["silent-undo: FAIL: notes.txt: stub finding"], 1)},
               "lane: the step runs a stand-in that fails")
        code, _stdout = real_undo(clone, "origin/main")
        scope(code == 0, "the real check fails the clean lane, so the stand-in is not the only failure")
        out = guard_run(case, clone, "git push origin lane-clean")
        self.assert_denied(out, "notes.txt")
        argv = seen_argv(case)
        self.assertIsNotNone(argv, "the step's program did not run")
        head = git(clone, "rev-parse", "lane-clean")
        self.assertIn("origin/main", argv, "the step's --upstream is not origin's default branch: %r" % argv)
        self.assertIn(head, argv, "the step's --head is not the pushed head: %r" % argv)

    def test_9b_the_guard_allows_a_merge_the_step_passes(self):
        case = self.case()
        seen = os.path.join(case, "seen.json")
        clone = drop_repo(case, lane_step=(STUB_RUN, stub_program(seen, [], 0)))
        code, _stdout = real_undo(clone, "origin/main")
        scope(code == 1, "the real check passes the merge, so the stand-in does not decide alone")
        out = guard_run(case, clone, "git push origin topic")
        self.assert_allowed(out, lints=LINT_LAUNCHES)
        argv = seen_argv(case)
        self.assertIsNotNone(argv, "the step's program did not run")
        head = git(clone, "rev-parse", "topic")
        self.assertIn(head, argv, "the step's --head is not the pushed head: %r" % argv)


if __name__ == "__main__":
    unittest.main()
