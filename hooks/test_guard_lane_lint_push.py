#!/usr/bin/env python3
"""Cases for the `lane-lint-push` rule in hooks/guard.py, a PreToolUse Bash hook. Standard library and unittest.

Run it from the repository root:

    python3 hooks/test_guard_lane_lint_push.py

GUARD_UNDER_TEST points the run at another copy of the guard, as in hooks/test_guard.py.

WHAT IT PROVES. Before a `git push` leaves, the guard judges the findings the sent commits add. It runs the
silent-undo check (lint/check_silent_undo.py) on the pushed head against origin's default branch, with the command
that CI's silent-undo step names in the pushed head's workflow file, and that step's own env. When origin already
holds the destination branch, it runs the same check on that remote tip too, and refuses only the findings the
first run has and the second lacks. So a finding origin already holds does not refuse a later push, and a finding
the sent commits add does. A ref other than HEAD is judged by its own sha. A range that cannot be read (UNKNOWN)
is allowed, with one guard.log line and one stderr line that say unknown, and that stderr line names the fix
`git fetch --unshallow origin`. A push that follows a commit-making segment in the same call (commit, merge, revert,
cherry-pick, rebase, am, pull) is refused, and the refusal says to run the push in a call of its own. A fast step is
a lint command under bin/ci-job's is_lint whose env takes a pull-request value. Any other step never runs at push, and
its if: is not read. A step that takes only the base ref reads the checked-out HEAD and runs once: against origin's
default branch, or against the destination when origin holds it. A workflow with no fast step, and a checkout with no
checks.yml, is skipped in silence. A push the lint does not judge starts no lint.

THE SEAMS THE GUARD HONORS.
  CAP_ENV          seconds one lint run may take, read from the guard's environment. Case 7b sets it to 1 and runs
                   a lint step that sleeps. A guard that reads no such name waits for its own default cap, and the
                   case still passes once the lint is cut.
  LINT_TOKEN       a lint launch is a child whose argv names check_silent_undo or undo_step_stub.
  Launch counts    the guard's own process starts: its children, and each git read it makes. A probe runs the guard
                   as __main__ in a child, with subprocess.Popen recorded. PUSH_LAUNCHES_BEFORE,
                   PUSH_LAUNCHES_BEFORE_EXISTING and NON_PUSH_LAUNCHES are measured before the lane lint. Each lint
                   run is one child process, and its git reads run inside it, so they are not the guard's starts.
                   A lint built in-process would count its git reads here, so that design changes these constants
                   and its record.

FIXTURES. Each case builds its own repository under the run folder: a bare origin, a clone, a
lint/check_silent_undo.py that runs the product's own check at its real path, and .github/workflows/checks.yml.
The workflow is read from the pushed head, as CI reads a pull request's head.
"""

import glob
import json
import os
import re
import runpy
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
from workflow_steps import step_blocks, step_key  # noqa: E402  the one home of the step parser

RUN = _test_temp.run_folder()

RULE = "lane-lint-push"
CAP_ENV = "LANE_LINT_PUSH_SECONDS"
LINT_TOKEN = re.compile(r"check_silent_undo|undo_step_stub")
PUSH_LAUNCHES_BEFORE = 10            # a clean push to a new destination (case 8b's fixture)
PUSH_LAUNCHES_BEFORE_EXISTING = 5   # a clean push to a destination origin holds (case 8c's fixture)
NON_PUSH_LAUNCHES = 9                # a `git commit` call (case 8a's command)
LINT_LAUNCHES = 1                    # a push to a new destination: one run, against the pushed head
LINT_LAUNCHES_EXISTING = 2           # a push to a destination origin holds: that run, and one against its remote tip

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
BASE_RUN = 'python3 lint/check_silent_undo.py --upstream "origin/$BASE_REF" --strict'   # reads the checked-out HEAD
HEAVY_REL = "heavy.sh"
HEAVY_RUN = "bash heavy.sh"   # a run that bin/ci-job's is_lint does not read as a lint command
HEAVY_NAME = "Heavy suite"
CI_JOB = os.path.join(REPO, "bin", "ci-job")

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


def workflow(run=SILENT_RUN, cond="github.event_name == 'pull_request'", head=True, name="Silent undo check"):
    """checks.yml with one step named `name`: its run line set to `run`, its if: set to `cond`, and its env: the base
    ref, with the head sha too when `head`. None: a workflow with no such step."""
    text = ("name: checks\non: [pull_request]\njobs:\n  checks:\n    runs-on: ubuntu-latest\n    steps:\n"
            "      - uses: actions/checkout@v4\n        with:\n          fetch-depth: 0\n")
    if run is None:
        return text + "      - name: Mod version bump\n        run: python3 lint/check_mod_versions.py\n"
    head_env = "          HEAD_SHA: ${{ github.event.pull_request.head.sha }}\n" if head else ""
    return text + ("      - name: %s\n"
                   "        if: ${{ %s }}\n"
                   "        env:\n"
                   "          BASE_REF: ${{ github.base_ref }}\n"
                   "%s"
                   "        run: %s\n" % (name, cond, head_env, run))


def stub_program(seen, lines, code, sleep_s=0):
    """A fixture stand-in for the lint step's program. Each run writes its argv to its own file, `seen` plus its pid,
    so two runs that start together (the head's and the remote tip's) never overwrite each other's record. It prints
    `lines`, waits `sleep_s` seconds and exits `code`. It is not the product."""
    return ("#!/usr/bin/env python3\n"
            "# A fixture stand-in for the lint step's program (hooks/test_guard_lane_lint_push.py). Not the product.\n"
            "import json, os, sys, time\n"
            "with open(%r + '.' + str(os.getpid()), 'w', encoding='utf-8') as handle:\n"
            "    json.dump(sys.argv[1:], handle)\n"
            "time.sleep(%r)\n"
            "for line in %r:\n"
            "    print(line)\n"
            "sys.exit(%r)\n" % (seen, sleep_s, list(lines), code))


def base_repo(case, run=SILENT_RUN, checks=True, head=True):
    """A bare origin and a clone whose `main` holds the base files and the workflow, pushed to origin. `checks`
    False leaves .github/workflows/checks.yml out of the tree altogether. `head` False gives the step no head sha."""
    origin = os.path.join(case, "origin.git")
    clone = os.path.join(case, "clone")
    git(case, "init", "-q", "--bare", "-b", "main", origin)
    git(case, "init", "-q", "-b", "main", clone)
    git(clone, "remote", "add", "origin", origin)
    files = {"notes.txt": NOTES, "policy.txt": "v1\n", "lint/check_silent_undo.py": SHIM}
    if checks:
        files[".github/workflows/checks.yml"] = workflow(run, head=head)
    commit(clone, files, "main: base")
    git(clone, "push", "-q", "origin", "main")
    git(clone, "remote", "set-head", "origin", "main")
    return clone, origin


def drop_repo(case, pushed=False, run=SILENT_RUN, lane_step=None, merge_body="", checks=True, head=True):
    """Branch `topic` holds a lane commit, then merges origin/main's later commit and drops the line main added
    (notes.txt), so the merge reads as a silent undo. origin/topic is the lane commit. With `pushed`, the merge
    is pushed to origin/topic first, and one more lane commit is left to push. `lane_step` is a (run, stub
    text) pair the lane commits to its own workflow before the merge. `merge_body` is the merge message's body.
    `checks` False builds the repo with no checks.yml at all. `head` False gives the workflow's step no head sha."""
    clone, _origin = base_repo(case, run, checks, head)
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


def second_undo_repo(case):
    """drop_repo, pushed: origin/topic holds the first merge, and the lane's last commit is on top. Then main gains
    extra.txt, and the lane merges it and empties the file: a second silent undo, not yet pushed."""
    clone = drop_repo(case, pushed=True)
    git(clone, "checkout", "-q", "main")
    commit(clone, {"extra.txt": "keep\n"}, "main adds keep")
    git(clone, "push", "-q", "origin", "main")
    git(clone, "checkout", "-q", "topic")
    git(clone, "merge", "-q", "--no-ff", "--no-commit", "origin/main")
    commit(clone, {"extra.txt": ""}, "merge main into lane, emptying extra.txt")
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


def reverted_on_remote_repo(case):
    """The lane's revert of main's X is pushed to origin/topic, and one more lane commit is left to push."""
    clone = revert_repo(case, existing_topic=True)
    git(clone, "push", "-q", "origin", "topic")
    commit(clone, {"more.txt": "more\n"}, "lane: more")
    return clone


def clean_repo(case, commits=2, name="lane-clean"):
    """Branch `name` holds `commits` ordinary commits on top of main, and nothing is pushed yet."""
    clone, _origin = base_repo(case)
    git(clone, "checkout", "-q", "-b", name)
    for index in range(commits):
        commit(clone, {"lane-%d.txt" % index: "lane %d\n" % index}, "lane: add lane-%d.txt" % index)
    return clone


def stub_lane(case, lines, code):
    """clean_repo's lane with two commits, and its own workflow whose one fast step runs STUB_RUN: a stand-in that
    prints `lines` and exits `code`. Returns the clone."""
    seen = os.path.join(case, "seen.json")
    clone = clean_repo(case, commits=2)
    commit(clone, {".github/workflows/checks.yml": workflow(STUB_RUN), STUB_REL: stub_program(seen, lines, code)},
           "lane: the step runs a stand-in")
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


def real_undo(where, upstream, head="HEAD"):
    """(exit code, stdout) of the real silent-undo check over `upstream`..`head` in `where`, with --strict."""
    done = subprocess.run([sys.executable, REAL_UNDO, "--repo", where, "--upstream", upstream, "--head", head,
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


def seen_runs(case):
    """The argv of each run a stand-in lint program made in `case`, in file-name order, or None when none ran."""
    paths = sorted(glob.glob(os.path.join(glob.escape(case), "seen.json.*")))
    if not paths:
        return None
    runs = []
    for path in paths:
        with open(path, encoding="utf-8") as handle:
            runs.append(json.load(handle))
    return runs


def launches_of(out, text):
    """The guard's own process starts whose argv names `text`."""
    return [s for s in out.starts if any(text in part for part in s["argv"])]


def ref_exists(where, ref):
    return subprocess.run(GIT + ["rev-parse", "--verify", "-q", ref], cwd=where, capture_output=True).returncode == 0


def ci_job_is_lint(text, name):
    """Whether bin/ci-job's is_lint reads the step named `name` in workflow `text` as a lint command. The module runs
    as a library (its main does not run), so the selector's one home answers, and no copy of it is kept here."""
    is_lint = runpy.run_path(CI_JOB, run_name="ci_job_scope")["is_lint"]
    found = [block for block in step_blocks(text) if step_key(block, "name") == name]
    if len(found) != 1:
        raise RuntimeError("fixture scope: no single step named %r in the workflow" % name)
    return bool(is_lint(found[0]))


def tearDownModule():
    shutil.rmtree(RUN, ignore_errors=True)


def unknown_stderr_lines(out):
    return [line for line in out.stderr.splitlines() if "unknown" in line.lower()]


class LaneLintCase(unittest.TestCase):
    def case(self):
        return tempfile.mkdtemp(prefix="case-", dir=RUN)

    def assert_denied(self, out, finding_file, lints=LINT_LAUNCHES, remedy=None):
        """Each part is its own subtest, so a failure names the one cause it shows. A None finding_file, lints or
        remedy skips that part."""
        with self.subTest("the guard ran"):
            self.assertEqual(out.error, "", "the guard did not run: %s" % out.error)
        with self.subTest("the push is refused"):
            self.assertEqual(out.decision, "deny", "the push was allowed, want a refusal by rule %s" % RULE)
        with self.subTest("the refusal names the rule"):
            self.assertIn(RULE, out.reason, "the refusal does not name rule %s" % RULE)
        if finding_file is not None:
            with self.subTest("the refusal names the file that holds the finding"):
                self.assertIn(finding_file, out.reason, "the refusal does not name %s" % finding_file)
        if lints is not None:
            with self.subTest("the lint launches before the refusal"):
                self.assertEqual(len(lint_starts(out)), lints, "lint launches before the refusal")
        if remedy is not None:
            with self.subTest("the refusal gives the remedy"):
                self.assertIn(remedy, out.reason, "the refusal does not say %r" % remedy)

    def assert_allowed(self, out, lints=None):
        with self.subTest("the guard ran"):
            self.assertEqual(out.error, "", "the guard did not run: %s" % out.error)
        with self.subTest("the push is allowed"):
            self.assertEqual(out.decision, "allow", "the push was refused: %s" % out.reason[:200])
        if lints is not None:
            with self.subTest("the lint launches on the push"):
                self.assertEqual(len(lint_starts(out)), lints, "lint launches on an allowed push")

    def assert_silent_allow(self, out):
        """A push the lint skips in silence: allowed, no lint launch, no guard.log line for the rule, no stderr."""
        with self.subTest("the guard ran"):
            self.assertEqual(out.error, "", "the guard did not run: %s" % out.error)
        with self.subTest("the push is allowed"):
            self.assertEqual(out.decision, "allow", "the push was refused: %s" % out.reason[:200])
        with self.subTest("no lint launch on the push"):
            self.assertEqual(len(lint_starts(out)), 0, "lint launches on a push the lint skips")
        with self.subTest("no guard.log line for the rule"):
            self.assertEqual(out.notes, [], "guard.log lines for %s, want none" % RULE)
        with self.subTest("no stderr"):
            self.assertEqual(out.stderr.strip(), "", "stderr, want none: %s" % out.stderr[:200])

    def assert_unknown_note(self, out):
        """An unknown lint allows the push, with one guard.log line and one stderr line that say unknown."""
        with self.subTest("an unknown lint does not refuse"):
            self.assertEqual(out.decision, "allow", "an unknown lint refused the push: %s" % out.reason[:200])
        with self.subTest("one guard.log line for the rule, and it says unknown"):
            self.assertEqual(len(out.notes), 1, "guard.log lines for %s, want exactly one" % RULE)
            self.assertIn("unknown", out.notes[0].lower(), "the guard.log line does not say unknown")
        with self.subTest("one stderr line says unknown"):
            self.assertEqual(len(unknown_stderr_lines(out)), 1, "stderr lines that say unknown, want exactly one")


class RefuseCases(LaneLintCase):
    def test_1a_merge_that_drops_a_main_line_is_refused_before_it_leaves(self):
        case = self.case()
        clone = drop_repo(case)
        code, stdout = real_undo(clone, "origin/main")
        scope(code == 1 and "notes.txt" in stdout, "the real check does not fail the merge against origin/main")
        out = guard_run(case, clone, "git push origin topic")
        self.assert_denied(out, "notes.txt", lints=LINT_LAUNCHES_EXISTING)

    def test_1c_a_new_silent_undo_in_the_sent_commits_refuses_the_push(self):
        case = self.case()
        clone = second_undo_repo(case)
        code, stdout = real_undo(clone, "origin/main")
        scope(code == 1 and "extra.txt" in stdout, "the real check does not fail the new merge against origin/main")
        code, stdout = real_undo(clone, "origin/main", "origin/topic")
        scope(code == 1 and "notes.txt" in stdout and "extra.txt" not in stdout,
              "the remote tip does not hold exactly the old finding")
        out = guard_run(case, clone, "git push origin topic")
        self.assert_denied(out, "extra.txt", lints=LINT_LAUNCHES_EXISTING)

    def test_2a_pushed_revert_of_a_main_commit_is_refused(self):
        case = self.case()
        clone = revert_repo(case, existing_topic=False)
        code, stdout = real_undo(clone, "origin/main")
        scope(code == 1 and "policy.txt" in stdout, "the real check does not fail the revert against origin/main")
        out = guard_run(case, clone, "git push origin lane")
        self.assert_denied(out, "policy.txt", lints=LINT_LAUNCHES)

    def test_2b_revert_of_a_main_commit_sent_on_an_existing_branch_is_refused(self):
        case = self.case()
        clone = revert_repo(case, existing_topic=True)
        code, stdout = real_undo(clone, "origin/main")
        scope(code == 1 and "policy.txt" in stdout, "the real check does not fail the revert against origin/main")
        code, _stdout = real_undo(clone, "origin/main", "origin/topic")
        scope(code == 0, "the remote tip already holds the reversal, so the finding is not new")
        out = guard_run(case, clone, "git push origin topic")
        self.assert_denied(out, "policy.txt", lints=LINT_LAUNCHES_EXISTING)

    def test_7a_a_ref_other_than_head_is_linted_by_its_own_sha(self):
        case = self.case()
        clone = drop_repo(case)
        git(clone, "checkout", "-q", "-b", "other-branch")
        git(clone, "checkout", "-q", "-b", "clean-head", "origin/main")
        code, stdout = real_undo(clone, "origin/main", "other-branch")
        scope(code == 1 and "notes.txt" in stdout, "the real check does not fail other-branch")
        code, _stdout = real_undo(clone, "origin/main")
        scope(code == 0, "the clean HEAD does not pass the real check")
        out = guard_run(case, clone, "git push origin other-branch:topic")
        self.assert_denied(out, "notes.txt", lints=LINT_LAUNCHES_EXISTING)

    def test_1d_a_commit_made_earlier_in_the_same_call_refuses_the_push(self):
        case = self.case()
        clone = clean_repo(case, name="topic")
        code, _stdout = real_undo(clone, "origin/main")
        scope(code == 0, "the real check fails the clean lane, so a refusal could come from a finding")
        chains = (
            ("commit", "git add -A && git commit -m x"),
            ("merge", "git merge --no-ff origin/main"),
            ("revert", "git revert --no-edit HEAD"),
            ("cherry-pick", "git cherry-pick origin/main"),
            ("rebase", "git rebase origin/main"),
            ("am", "git am patch.mbox"),
            ("pull --rebase", "git pull --rebase"),
            ("pull --ff-only", "git pull --ff-only"),
        )
        for verb, before in chains:
            with self.subTest(verb):
                out = guard_run(case, clone, before + " && git push origin topic")
                self.assert_denied(out, None, lints=None, remedy="call of its own")
        with self.subTest("control: a pull with no push after it is allowed"):
            self.assert_allowed(guard_run(case, clone, "git pull --rebase"))


class AllowCases(LaneLintCase):
    def test_1b_a_finding_origin_already_holds_does_not_refuse_a_clean_commit_sent_on_top(self):
        case = self.case()
        clone = drop_repo(case, pushed=True)
        code, stdout = real_undo(clone, "origin/main")
        scope(code == 1 and "notes.txt" in stdout, "the real check does not fail the merge the lane pushed earlier")
        code, stdout = real_undo(clone, "origin/main", "origin/topic")
        scope(code == 1 and "notes.txt" in stdout, "the remote tip does not hold the finding")
        out = guard_run(case, clone, "git push origin topic")
        self.assert_allowed(out, lints=LINT_LAUNCHES_EXISTING)

    def test_2c_a_reversal_origin_already_holds_does_not_refuse_a_clean_commit_sent_on_top(self):
        case = self.case()
        clone = reverted_on_remote_repo(case)
        code, stdout = real_undo(clone, "origin/main", "origin/topic")
        scope(code == 1 and "policy.txt" in stdout, "the remote tip does not hold the reversal")
        out = guard_run(case, clone, "git push origin topic")
        self.assert_allowed(out, lints=LINT_LAUNCHES_EXISTING)

    def test_1e_a_chain_with_no_commit_verb_before_the_push_is_still_linted(self):
        case = self.case()
        clone = clean_repo(case, name="topic")
        code, _stdout = real_undo(clone, "origin/main")
        scope(code == 0, "the real check fails the clean lane")
        controls = (
            ("status chained before the push", "git status && git push origin topic"),
            ("a quoted commit is text, not a commit verb", 'echo "git commit -m x" && git push origin topic'),
        )
        for label, command in controls:
            with self.subTest(label):
                out = guard_run(case, clone, command)
                self.assert_allowed(out, lints=LINT_LAUNCHES)

    def test_3_clean_lane_push_is_allowed_and_linted(self):
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

    def test_4_shallow_clone_pushing_a_clean_commit_is_allowed_with_one_unknown_note_naming_the_fix(self):
        case = self.case()
        clone = shallow_repo(case)
        code, stdout = real_undo(clone, "origin/main")
        scope(code == 1 and "UNKNOWN" in stdout, "the real check does not read the shallow clone as UNKNOWN")
        out = guard_run(case, clone, "git push origin lane-shallow")
        self.assert_allowed(out, lints=LINT_LAUNCHES)
        self.assert_unknown_note(out)
        with self.subTest("the one stderr line names the fix: git fetch --unshallow origin"):
            said = unknown_stderr_lines(out)
            self.assertTrue(any("git fetch --unshallow origin" in line for line in said),
                            "the unknown stderr line does not name the fix: %s" % said)

    def test_5_drops_lines_trailer_excuses_the_drop(self):
        case = self.case()
        clone = drop_repo(case, merge_body="Drops-lines: notes.txt -- the lane removes the line main added")
        code, stdout = real_undo(clone, "origin/main")
        scope(code == 0 and "ALLOWED" in stdout, "the real check does not excuse the drop with the trailer")
        out = guard_run(case, clone, "git push origin topic")
        self.assert_allowed(out, lints=LINT_LAUNCHES_EXISTING)


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
            self.assert_denied(out, "notes.txt", lints=LINT_LAUNCHES_EXISTING)

    def test_7c_a_workflow_with_no_fast_step_is_skipped_in_silence(self):
        case = self.case()
        clone = drop_repo(case, run=None)
        code, stdout = real_undo(clone, "origin/main")
        scope(code == 1 and "notes.txt" in stdout, "the real check does not fail the merge, so silence hides nothing")
        out = guard_run(case, clone, "git push origin topic")
        self.assert_silent_allow(out)

    def test_7d_a_repo_with_no_checks_yml_is_skipped_in_silence(self):
        case = self.case()
        clone = drop_repo(case, checks=False)
        scope(not os.path.exists(os.path.join(clone, ".github", "workflows", "checks.yml")),
              "the checkout holds a checks.yml")
        code, stdout = real_undo(clone, "origin/main")
        scope(code == 1 and "notes.txt" in stdout, "the real check does not fail the merge, so silence hides nothing")
        out = guard_run(case, clone, "git push origin topic")
        self.assert_silent_allow(out)

    def test_11a_a_step_whose_run_is_not_a_lint_command_never_runs_at_push(self):
        case = self.case()
        heavy = workflow(HEAVY_RUN, head=False, name=HEAVY_NAME)
        scope(not ci_job_is_lint(heavy, HEAVY_NAME), "bin/ci-job's is_lint reads the heavy step as a lint command")
        clone = clean_repo(case, commits=1)
        commit(clone, {".github/workflows/checks.yml": heavy, HEAVY_REL: "exit 0\n"},
               "lane: a heavy step that takes the base ref")
        out = guard_run(case, clone, "git push origin lane-clean")
        self.assert_silent_allow(out)
        with self.subTest("no launch of the heavy step on the push"):
            self.assertEqual(launches_of(out, HEAVY_REL), [], "the guard launched %r on a push" % HEAVY_RUN)
        with self.subTest("control: a lint command that takes only the base ref runs on the same push"):
            control = self.case()
            base_only = workflow(BASE_RUN, head=False)
            scope(ci_job_is_lint(base_only, "Silent undo check"), "bin/ci-job's is_lint does not read the control as lint")
            clone = clean_repo(control, commits=1)
            commit(clone, {".github/workflows/checks.yml": base_only}, "lane: a lint step that takes the base ref")
            self.assert_allowed(guard_run(control, clone, "git push origin lane-clean"), lints=LINT_LAUNCHES)

    def test_11c_a_non_lint_step_whose_if_the_guard_cannot_read_prints_nothing(self):
        case = self.case()
        heavy = workflow(HEAVY_RUN, cond="contains(github.ref, 'release')", head=False, name=HEAVY_NAME)
        scope(not ci_job_is_lint(heavy, HEAVY_NAME), "bin/ci-job's is_lint reads the heavy step as a lint command")
        clone = clean_repo(case, commits=1)
        commit(clone, {".github/workflows/checks.yml": heavy, HEAVY_REL: "exit 0\n"},
               "lane: a heavy step with an if the guard cannot read")
        out = guard_run(case, clone, "git push origin lane-clean")
        self.assert_silent_allow(out)
        with self.subTest("no launch of the heavy step on the push"):
            self.assertEqual(launches_of(out, HEAVY_REL), [], "the guard launched %r on a push" % HEAVY_RUN)


class UnknownCases(LaneLintCase):
    def test_7b_a_lint_run_past_the_time_cap_is_unknown_and_allowed(self):
        case = self.case()
        seen = os.path.join(case, "seen.json")
        clone = drop_repo(case, lane_step=(STUB_RUN, stub_program(seen, [], 0, sleep_s=600)))
        scope(seen_runs(case) is None, "the stand-in ran before the push")
        out = guard_run(case, clone, "git push origin topic", env={CAP_ENV: "1"})
        with self.subTest("a lint run started and was cut"):
            self.assertGreaterEqual(len(lint_starts(out)), 1, "no lint launch on the push")
        self.assert_allowed(out)
        self.assert_unknown_note(out)

    def test_7e_a_fast_step_whose_if_the_guard_cannot_read_stays_unknown(self):
        case = self.case()
        clone = clean_repo(case, name="topic")
        commit(clone, {".github/workflows/checks.yml": workflow(cond="contains(github.ref, 'release')")},
               "lane: a fast step with an if the guard cannot read")
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

    def test_8b_a_push_to_a_new_destination_starts_only_the_processes_the_record_names(self):
        case = self.case()
        clone = clean_repo(case, commits=2)
        out = guard_run(case, clone, "git push origin lane-clean")
        self.assert_allowed(out)
        want = PUSH_LAUNCHES_BEFORE + LINT_LAUNCHES
        self.assertEqual(len(out.starts), want,
                         "guard launches for a clean push to a new destination, want %d (%d before the lint, "
                         "plus %d lint launch)" % (want, PUSH_LAUNCHES_BEFORE, LINT_LAUNCHES))

    def test_8c_a_push_to_an_existing_destination_starts_one_more_lint_run(self):
        case = self.case()
        clone = clean_repo(case, commits=1)
        git(clone, "push", "-q", "origin", "lane-clean")
        commit(clone, {"lane-next.txt": "next\n"}, "lane: add lane-next.txt")
        out = guard_run(case, clone, "git push origin lane-clean")
        self.assert_allowed(out)
        want = PUSH_LAUNCHES_BEFORE_EXISTING + LINT_LAUNCHES_EXISTING
        self.assertEqual(len(out.starts), want,
                         "guard launches for a clean push to an existing destination, want %d (%d before the lint, "
                         "plus %d lint launches)" % (want, PUSH_LAUNCHES_BEFORE_EXISTING, LINT_LAUNCHES_EXISTING))


class StepCases(LaneLintCase):
    def test_9a_the_guard_runs_the_command_the_step_names(self):
        case = self.case()
        clone = stub_lane(case, ["silent-undo: FAIL: notes.txt: stub finding"], 1)
        code, _stdout = real_undo(clone, "origin/main")
        scope(code == 0, "the real check fails the clean lane, so the stand-in is not the only failure")
        out = guard_run(case, clone, "git push origin lane-clean")
        self.assert_denied(out, "notes.txt", lints=LINT_LAUNCHES)
        runs = seen_runs(case)
        self.assertIsNotNone(runs, "the step's program did not run")
        flat = [arg for run in runs for arg in run]
        self.assertIn("origin/main", flat, "the step's --upstream is not origin's default branch: %r" % runs)
        self.assertIn(git(clone, "rev-parse", "lane-clean"), flat, "the step's --head is not the pushed head")

    def test_9b_the_guard_allows_a_merge_the_step_passes(self):
        case = self.case()
        seen = os.path.join(case, "seen.json")
        clone = drop_repo(case, lane_step=(STUB_RUN, stub_program(seen, [], 0)))
        code, _stdout = real_undo(clone, "origin/main")
        scope(code == 1, "the real check passes the merge, so the stand-in does not decide alone")
        out = guard_run(case, clone, "git push origin topic")
        self.assert_allowed(out, lints=LINT_LAUNCHES_EXISTING)
        runs = seen_runs(case)
        self.assertIsNotNone(runs, "the step's program did not run")
        heads = [run[run.index("--head") + 1] for run in runs if "--head" in run]
        self.assertIn(git(clone, "rev-parse", "topic"), heads, "the step was not run on the pushed head")
        self.assertIn(git(clone, "rev-parse", "origin/topic"), heads, "the step was not run on the remote tip")

    def test_11b_a_refusal_lists_finding_lines_and_no_remedy_allowed_or_unknown_line(self):
        case = self.case()
        clone = drop_repo(case)
        code, stdout = real_undo(clone, "origin/main")
        remedy = [line for line in stdout.splitlines() if line.startswith("silent-undo: REMEDY")]
        scope(code == 1 and len(remedy) == 1, "the real check does not print one REMEDY line for the merge")
        out = guard_run(case, clone, "git push origin topic")
        self.assert_denied(out, "notes.txt", lints=LINT_LAUNCHES_EXISTING)
        with self.subTest("the real check's REMEDY line is not in the refusal"):
            self.assertNotIn(remedy[0], out.reason, "the refusal lists the REMEDY line")

        stand_in = self.case()
        clone = stub_lane(stand_in, ["silent-undo: ALLOWED notes.txt: allowed-token",
                                     "silent-undo: FAIL: policy.txt: stub finding",
                                     "silent-undo: REMEDY: remedy-token"], 1)
        code, _stdout = real_undo(clone, "origin/main")
        scope(code == 0, "the real check fails the clean lane, so the stand-in is not the only failure")
        out = guard_run(stand_in, clone, "git push origin lane-clean")
        self.assert_denied(out, "policy.txt", lints=LINT_LAUNCHES)
        with self.subTest("an ALLOWED line is not in the refusal"):
            self.assertNotIn("allowed-token", out.reason, "the refusal lists the ALLOWED line")
        with self.subTest("a REMEDY line is not in the refusal"):
            self.assertNotIn("remedy-token", out.reason, "the refusal lists the REMEDY line")

        mixed = self.case()
        clone = stub_lane(mixed, ["silent-undo: FAIL: policy.txt: stub finding",
                                  "silent-undo: UNKNOWN: unknown-token"], 1)
        out = guard_run(mixed, clone, "git push origin lane-clean")
        with self.subTest("a finding beside an UNKNOWN line is unknown and allowed, not refused"):
            self.assert_unknown_note(out)


class BaseOnlyCases(LaneLintCase):
    """A step that takes only the base ref reads the checked-out HEAD and runs once: against origin's default branch,
    or against the destination when origin holds it."""

    def test_12a_a_finding_in_the_sent_commits_refuses_a_push_to_a_new_destination(self):
        case = self.case()
        clone = drop_repo(case, run=BASE_RUN, head=False)
        code, stdout = real_undo(clone, "origin/main")
        scope(code == 1 and "notes.txt" in stdout, "the real check does not fail the merge against origin/main")
        scope(not ref_exists(clone, "refs/remotes/origin/lane-new"), "origin already holds lane-new")
        out = guard_run(case, clone, "git push origin topic:lane-new")
        self.assert_denied(out, "notes.txt", lints=LINT_LAUNCHES)

    def test_12b_a_finding_origin_already_holds_does_not_refuse_the_push_to_the_destination(self):
        case = self.case()
        clone = drop_repo(case, pushed=True, run=BASE_RUN, head=False)
        code, stdout = real_undo(clone, "origin/main")
        scope(code == 1 and "notes.txt" in stdout, "the real check does not fail the merge against origin/main")
        code, _stdout = real_undo(clone, "origin/topic")
        scope(code == 0, "the commits past origin/topic hold a finding, so the push would not test the held case")
        out = guard_run(case, clone, "git push origin topic")
        self.assert_allowed(out, lints=LINT_LAUNCHES)

    def test_12c_a_ref_other_than_head_is_allowed_with_one_unknown_note(self):
        case = self.case()
        clone = drop_repo(case, run=BASE_RUN, head=False)
        git(clone, "checkout", "-q", "-b", "other-branch")
        git(clone, "checkout", "-q", "-b", "clean-head", "origin/main")
        code, stdout = real_undo(clone, "origin/main", "other-branch")
        scope(code == 1 and "notes.txt" in stdout, "the real check does not fail other-branch")
        out = guard_run(case, clone, "git push origin other-branch:topic")
        self.assert_allowed(out, lints=LINT_LAUNCHES)
        self.assert_unknown_note(out)
        with self.subTest("the one note says the step reads HEAD, not the pushed ref"):
            self.assertTrue(any("other than the checked-out HEAD" in note for note in out.notes),
                            "the guard.log line does not say it: %s" % out.notes)


if __name__ == "__main__":
    unittest.main()
