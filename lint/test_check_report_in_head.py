#!/usr/bin/env python3
"""Cases for lint/check_report_in_head.py. Standard library and git only.

    python3 lint/test_check_report_in_head.py

A builder's report names the files it changed. The check reads the one `Files:` line of the report and
checks each listed path against the diff of the pushed branch head (refs/heads/<branch> on origin).
Exit contract:

    0  every listed path is in the diff
    1  a listed path is not in the diff; the output names each one
    2  UNKNOWN: branch not on origin, a git failure, no Files line, an empty list, or an absolute path entry

Each case builds a fixture under this run's folder (lint/_test_temp.py): a bare origin and a work tree.
The check runs as lint/check_report_in_head.py by its absolute path. CHECK_REPORT_IN_HEAD_UNDER_TEST
overrides that path, which a mutant run uses.

CheckCase needs the check. On a tree without it, each case fails at its module assert, before it builds a
fixture. ControlCase needs no check: it proves the fixture facts the check cases rely on, and passes there.
"""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  rm_tree removes a fixture, read-only git objects included (testing/tracked_tree.py)

MODULE = os.path.abspath(os.environ.get("CHECK_REPORT_IN_HEAD_UNDER_TEST")
                         or os.path.join(HERE, "check_report_in_head.py"))
GIT_ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
for _name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
    GIT_ENV.pop(_name, None)  # the outer shell's repo never leaks into a fixture

BRANCH = "lane/widget-edit"
WIDGET = "lint/widget.py"
OTHER = "lint/other.py"
WIDGET_TEXT = "def widget():\n    return 1\n"
OTHER_TEXT = "def other():\n    return 2\n"
RENAMED_TEXT = "def renamed():\n    return 3\n"
WORKTREE = "/home/x/wt"
ABS_PATH = WORKTREE + "/lint/widget.py"
A_MD = "a.md"
LINT_A = "lint/a.py"
LINT_B = "lint/b.py"
X_FILE = "lint/x.py"
X_TEXT = "X = 2\n"

RUN_FOLDER = None


def counting_shim():
    """A runner that loads the check and records each git call it makes, then runs the check's main."""
    return COUNTING_SHIM.replace("MODULE_PATH", repr(MODULE))


COUNTING_SHIM = """import importlib.util, sys
spec = importlib.util.spec_from_file_location("check_report_in_head", MODULE_PATH)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)
calls = []
real_run = check._nowindow.run
def counted(argv, **kwargs):
    calls.append(argv[1])
    return real_run(argv, **kwargs)
check._nowindow.run = counted
rc = check.main(sys.argv[1:])
print("GIT_CALLS " + " ".join(calls))
sys.exit(rc)
"""


def close_stdin():
    """Runs in the child before it execs the check: fd 0 is closed, as `<&-` leaves it."""
    os.close(0)


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    if RUN_FOLDER and os.path.isdir(RUN_FOLDER):
        tracked_tree.rm_tree(RUN_FOLDER)  # test-temp-standard: teardown removes the run folder


class Fixture(unittest.TestCase):
    """A bare origin and a work tree whose main is pushed. A case adds branches on top."""

    def setUp(self):
        self.root = tempfile.mkdtemp(dir=RUN_FOLDER, prefix="crh_")
        self.addCleanup(tracked_tree.rm_tree, self.root)
        self.origin = os.path.join(self.root, "origin.git")
        self.work = os.path.join(self.root, "work")
        subprocess.run(["git", "init", "-q", "--bare", self.origin], check=True, capture_output=True, env=GIT_ENV)
        subprocess.run(["git", "init", "-q", self.work], check=True, capture_output=True, env=GIT_ENV)
        self.git("symbolic-ref", "HEAD", "refs/heads/main")
        self.git("remote", "add", "origin", self.origin)
        self.commit({"lint/base.py": "BASE = 1\n"}, "fixture base")
        self.git("push", "-q", "origin", "HEAD:refs/heads/main")

    def git(self, *args, cwd=None):
        done = subprocess.run(["git", "-C", cwd or self.work, "-c", "user.name=test",
                               "-c", "user.email=test@example.com",
                               "-c", "core.autocrlf=false", *args],
                              check=True, capture_output=True, text=True, encoding="utf-8", env=GIT_ENV)
        return done.stdout.strip()

    def commit(self, files, subject, cwd=None):
        """Write `files` (a None value deletes one), commit them, and return the new head sha."""
        base = cwd or self.work
        for rel, text in files.items():
            path = os.path.join(base, *rel.split("/"))
            if text is None:
                os.remove(path)
                continue
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(text)
        self.git("add", "-A", "--", *files, cwd=cwd)
        self.git("commit", "-q", "-m", subject, cwd=cwd)
        return self.git("rev-parse", "HEAD", cwd=cwd)

    def on_main(self, files, subject):
        """A commit on main, pushed, so a branch made after it starts from it."""
        self.git("checkout", "-q", "main")
        self.commit(files, subject)
        self.git("push", "-q", "origin", "HEAD:refs/heads/main")

    def local_only(self, name, files):
        """A branch off main with one commit of `files`, not pushed. The work tree is left on main."""
        self.git("checkout", "-q", "-b", name, "main")
        sha = self.commit(files, "builder work on " + name)
        self.git("checkout", "-q", "main")
        return sha

    def pushed_branch(self, name, files):
        """A branch off main with one commit of `files`, pushed to origin. Returns the pushed head sha."""
        sha = self.local_only(name, files)
        self.git("push", "-q", "origin", "%s:refs/heads/%s" % (name, name))
        return sha

    def unpushed_commit(self, name, files):
        """One more commit on the existing branch `name`, not pushed. The work tree is left on main."""
        self.git("checkout", "-q", name)
        sha = self.commit(files, "unpushed work on " + name)
        self.git("checkout", "-q", "main")
        return sha

    def origin_head(self, name):
        """The sha origin holds for refs/heads/<name>, or '' when origin lacks the branch."""
        out = self.git("ls-remote", "origin", "refs/heads/" + name)
        return out.split()[0] if out else ""

    def diff_names(self, ref):
        """The paths in the diff from main to `ref`, read with no renames as the check reads it."""
        return self.git("diff", "--name-only", "--no-renames", "main", ref).split()

    def run_check(self, branch, report="", args=(), cwd=None, env=GIT_ENV):
        """Run the check for `branch` with `report` on stdin. Returns (exit code, stdout and stderr)."""
        done = subprocess.run([sys.executable, MODULE, "--branch", branch, *args],
                              cwd=cwd or self.work, input=report, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=env)
        return done.returncode, done.stdout + done.stderr


class CheckCase(Fixture):
    """Cases that need the check. Each fails on a tree without lint/check_report_in_head.py, the old commit."""

    def setUp(self):
        self.assertTrue(os.path.isfile(MODULE), "module absent: lint/check_report_in_head.py")
        super().setUp()

    def scope(self, branch, *names):
        """Scope first: the pushed head's diff holds each name, so the case reaches the diff it probes."""
        diff = self.diff_names(self.origin_head(branch))
        for name in names:
            self.assertIn(name, diff, "the pushed head of %s lacks %s from its diff" % (branch, name))

    def assertPasses(self, branch, report, args=(), cwd=None):
        rc, out = self.run_check(branch, report, args, cwd)
        self.assertEqual(rc, 0, "exit %d, want 0:\n%s" % (rc, out))
        self.assertNotIn("Traceback", out, out)

    def assertFlags(self, branch, report, missing, args=()):
        rc, out = self.run_check(branch, report, args)
        self.assertEqual(rc, 1, "exit %d, want 1:\n%s" % (rc, out))
        for path in missing:
            self.assertTrue(any(path in line for line in out.splitlines()),
                            "no output line names missing path %s:\n%s" % (path, out))

    def assertUnknown(self, branch, report, named, args=(), env=GIT_ENV):
        rc, out = self.run_check(branch, report, args, env=env)
        self.assertEqual(rc, 2, "exit %d, want 2 (UNKNOWN):\n%s" % (rc, out))
        for word in named:
            self.assertIn(word, out, "output names no %r:\n%s" % (word, out))
        for stray in ("can't open file", "usage:", "Traceback"):
            self.assertNotIn(stray, out, "exit 2 from %r, not from the check's UNKNOWN:\n%s" % (stray, out))

    def run_check_closed_stdin(self, branch, args=()):
        """Run the check with fd 0 closed, as `<&-` leaves it. Returns (exit code, stdout and stderr decoded)."""
        done = subprocess.run([sys.executable, MODULE, "--branch", branch, *args], cwd=self.work,
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              preexec_fn=close_stdin, env=GIT_ENV)
        return done.returncode, done.stdout + done.stderr

    def run_check_bytes(self, branch, data, args=()):
        """Run the check with `data` (bytes) on stdin. Returns (exit code, stdout and stderr decoded)."""
        # strict UTF-8 on stdin, whatever the runner's locale: a C locale would read the bytes without error
        env = dict(GIT_ENV, PYTHONIOENCODING="utf-8:strict")
        done = subprocess.run([sys.executable, MODULE, "--branch", branch, *args], cwd=self.work, input=data,
                              capture_output=True, env=env)
        return done.returncode, (done.stdout + done.stderr).decode("utf-8", "replace")

    def test_reported_file_missing_from_the_diff_is_flagged(self):
        self.pushed_branch(BRANCH, {WIDGET: WIDGET_TEXT})
        self.scope(BRANCH, WIDGET)
        self.assertFlags(BRANCH, "Files: %s, lint/never_applied.py\n" % WIDGET, missing=["lint/never_applied.py"])

    def test_path_in_the_diff_with_a_range_passes(self):
        self.pushed_branch(BRANCH, {WIDGET: WIDGET_TEXT, OTHER: OTHER_TEXT})
        self.scope(BRANCH, WIDGET, OTHER)
        for report in ("Files: %s:10-20, %s:5\n" % (WIDGET, OTHER), "Files: %s:5\n" % WIDGET):
            with self.subTest(report=report):
                self.assertPasses(BRANCH, report)

    def test_a_deleted_file_listed_passes(self):
        self.on_main({"lint/old.py": OTHER_TEXT}, "main gets the old file")
        self.pushed_branch(BRANCH, {"lint/old.py": None})
        self.scope(BRANCH, "lint/old.py")
        self.assertPasses(BRANCH, "Files: lint/old.py\n")

    def test_a_renamed_file_passes_under_its_new_and_its_old_name(self):
        self.on_main({"lint/old_name.py": RENAMED_TEXT}, "main gets the file to rename")
        self.pushed_branch(BRANCH, {"lint/old_name.py": None, "lint/new_name.py": RENAMED_TEXT})
        self.scope(BRANCH, "lint/old_name.py", "lint/new_name.py")
        for name in ("lint/new_name.py", "lint/old_name.py"):
            with self.subTest(name=name):
                self.assertPasses(BRANCH, "Files: %s\n" % name)

    def test_worktree_and_branch_lines_are_not_read_as_paths(self):
        self.pushed_branch(BRANCH, {WIDGET: WIDGET_TEXT})
        self.scope(BRANCH, WIDGET)
        self.assertPasses(BRANCH, "Worktree: %s\n%s\nBranch: %s\nFiles: %s\n" % (WORKTREE, WORKTREE, BRANCH, WIDGET))

    def test_branch_not_on_origin_is_unknown(self):
        self.local_only(BRANCH, {WIDGET: WIDGET_TEXT})
        self.assertEqual(self.origin_head(BRANCH), "")  # scope: the branch exists here and not on origin
        for branch in (BRANCH, "lane/never-made"):
            with self.subTest(branch=branch):
                self.assertUnknown(branch, "Files: %s\n" % WIDGET, named=[branch])

    def test_a_report_with_no_usable_files_line_is_unknown(self):
        self.pushed_branch(BRANCH, {WIDGET: WIDGET_TEXT})
        self.scope(BRANCH, WIDGET)  # the branch is valid, so only the report can fail
        reports = {
            "no Files line": "Worktree: %s\nBranch: %s\nDone: widget edited\n" % (WORKTREE, BRANCH),
            "empty Files line": "Files:\n",
            "blank Files line": "Files:   \n",
        }
        for label, report in reports.items():
            with self.subTest(label):
                self.assertUnknown(BRANCH, report, named=["Files"])

    def test_an_absolute_path_entry_is_unknown(self):
        self.pushed_branch(BRANCH, {WIDGET: WIDGET_TEXT})
        self.scope(BRANCH, WIDGET)
        for report in ("Files: %s\n" % ABS_PATH, "Files: %s, %s\n" % (WIDGET, ABS_PATH)):
            with self.subTest(report=report):
                self.assertUnknown(BRANCH, report, named=[ABS_PATH])

    def test_the_pushed_head_is_read_not_the_local_commit(self):
        self.pushed_branch(BRANCH, {OTHER: OTHER_TEXT})
        local = self.unpushed_commit(BRANCH, {WIDGET: WIDGET_TEXT})
        self.scope(BRANCH, OTHER)
        self.assertNotIn(WIDGET, self.diff_names(self.origin_head(BRANCH)))
        self.assertIn(WIDGET, self.diff_names(local))
        report = "Files: %s\n" % WIDGET
        self.assertFlags(BRANCH, report, missing=[WIDGET])
        self.git("push", "-q", "origin", "%s:refs/heads/%s" % (BRANCH, BRANCH))
        self.assertPasses(BRANCH, report)  # the same report passes once the head is pushed

    def test_markup_around_the_files_line_parses(self):
        self.pushed_branch(BRANCH, {WIDGET: WIDGET_TEXT, OTHER: OTHER_TEXT})
        self.scope(BRANCH, WIDGET, OTHER)
        forms = (
            "Files: `%s`, `%s:10-20`" % (WIDGET, OTHER),
            "Files: ./%s, ./%s" % (WIDGET, OTHER),
            "**Files:** %s, %s" % (WIDGET, OTHER),
            "> Files: %s, %s" % (WIDGET, OTHER),
            "> **Files:** `%s`, `./%s:5`" % (WIDGET, OTHER),
            "- Files: %s, %s" % (WIDGET, OTHER),
            "* Files: %s, %s" % (WIDGET, OTHER),
            "  Files: %s, %s" % (WIDGET, OTHER),
        )
        for line in forms:
            with self.subTest(line=line):
                self.assertPasses(BRANCH, line + "\n")

    def test_a_full_size_report_passes_and_a_gap_in_it_is_named(self):
        names = ["lint/gen_%02d.py" % i for i in range(40)]
        self.pushed_branch(BRANCH, {name: "VALUE = %d\n" % i for i, name in enumerate(names)})
        self.scope(BRANCH, *names)
        entries = [("`%s`" % name) if i % 2 else ("./" + name) for i, name in enumerate(names)]
        self.assertPasses(BRANCH, "Files: %s\n" % ", ".join(entries))
        self.assertFlags(BRANCH, "Files: %s\n" % ", ".join(entries + ["lint/never_applied.py"]),
                         missing=["lint/never_applied.py"])

    def test_report_flag_reads_the_file_and_dash_reads_stdin(self):
        self.pushed_branch(BRANCH, {WIDGET: WIDGET_TEXT})
        self.scope(BRANCH, WIDGET)
        path = os.path.join(self.root, "builder-report.txt")
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("Files: %s\n" % WIDGET)
        self.assertPasses(BRANCH, "", args=("--report", path))  # stdin is empty, so the file must be read
        self.assertPasses(BRANCH, "Files: %s\n" % WIDGET, args=("--report", "-"))

    def test_root_and_base_flags_name_the_repo_and_the_base(self):
        self.pushed_branch(BRANCH, {WIDGET: WIDGET_TEXT})
        self.scope(BRANCH, WIDGET)
        self.assertPasses(BRANCH, "Files: %s\n" % WIDGET, args=("--root", self.work, "--base", "origin/main"),
                          cwd=self.root)

    def test_a_non_default_base_changes_the_diff_the_report_is_read_against(self):
        self.pushed_branch("lane/parent", {OTHER: OTHER_TEXT})
        self.git("checkout", "-q", "-b", BRANCH, "lane/parent")  # the builder's branch starts from the parent
        self.commit({WIDGET: WIDGET_TEXT}, "builder work on " + BRANCH)
        self.git("push", "-q", "origin", "%s:refs/heads/%s" % (BRANCH, BRANCH))
        self.git("checkout", "-q", "main")
        self.scope(BRANCH, OTHER, WIDGET)  # against main, the parent's file is in the builder's change too
        self.assertEqual(self.git("diff", "--name-only", "--no-renames", "origin/lane/parent",
                                  self.origin_head(BRANCH)).split(), [WIDGET])  # against the parent, it is not
        report = "Files: %s\n" % OTHER
        self.assertPasses(BRANCH, report)  # the default base reads OTHER as in the diff
        self.assertFlags(BRANCH, report, missing=[OTHER], args=("--base", "origin/lane/parent"))


    def test_a_range_entry_after_a_comma_continues_the_prior_range(self):
        self.pushed_branch(BRANCH, {A_MD: "notes\n", LINT_A: "X = 1\n"})
        self.scope(BRANCH, A_MD)
        self.assertPasses(BRANCH, "Files: %s:10-20, 30-40\n" % A_MD)  # 30-40 is a range, not a path

    def test_a_backticked_path_with_its_range_outside_the_backticks_passes(self):
        self.pushed_branch(BRANCH, {A_MD: "notes\n", LINT_A: "X = 1\n"})
        self.scope(BRANCH, LINT_A)
        self.assertPasses(BRANCH, "Files: `%s`:10-20\n" % LINT_A)

    def test_a_range_with_an_en_dash_passes(self):
        self.pushed_branch(BRANCH, {A_MD: "notes\n", LINT_A: "X = 1\n"})
        self.scope(BRANCH, LINT_A)
        self.assertPasses(BRANCH, "Files: %s:10–20\n" % LINT_A)

    def test_a_bold_path_passes(self):
        self.pushed_branch(BRANCH, {A_MD: "notes\n", LINT_A: "X = 1\n"})
        self.scope(BRANCH, LINT_A)
        self.assertPasses(BRANCH, "Files: **%s**\n" % LINT_A)

    def test_a_non_utf8_report_on_stdin_is_unknown_without_a_traceback(self):
        self.pushed_branch(BRANCH, {WIDGET: WIDGET_TEXT})
        self.scope(BRANCH, WIDGET)
        data = b"Files: " + WIDGET.encode("ascii") + b"\nDone: \x93widget\x94 fixed\n"  # cp1252 curly quotes
        rc, out = self.run_check_bytes(BRANCH, data)
        self.assertEqual(rc, 2, "exit %d, want 2 (UNKNOWN) for a cp1252 report on stdin:\n%s" % (rc, out))
        self.assertNotIn("Traceback", out, out)

    def test_a_stale_local_base_ref_is_not_trusted_for_the_base(self):
        base_main = self.git("rev-parse", "main")  # the work tree's origin/main ref, which nothing fetches here
        other = os.path.join(self.root, "other")
        subprocess.run(["git", "clone", "-q", self.origin, other], check=True, capture_output=True, env=GIT_ENV)
        self.git("checkout", "-q", "-b", BRANCH, "origin/main", cwd=other)
        self.commit({WIDGET: WIDGET_TEXT}, "builder work on " + BRANCH, cwd=other)
        self.git("push", "-q", "origin", "%s:refs/heads/%s" % (BRANCH, BRANCH), cwd=other)
        self.git("checkout", "-q", "-B", "main", "origin/main", cwd=other)
        self.commit({X_FILE: X_TEXT}, "real main moves on", cwd=other)
        self.git("push", "-q", "origin", "main:refs/heads/main", cwd=other)
        self.git("checkout", "-q", BRANCH, cwd=other)
        self.git("merge", "-q", "--no-edit", "main", cwd=other)  # the head takes real main in, changes nothing of X
        self.git("push", "-q", "origin", "%s:refs/heads/%s" % (BRANCH, BRANCH), cwd=other)
        # scope, read in the clone that holds every object: the head's own change leaves X out, the stale base has it
        self.assertEqual(self.git("diff", "--name-only", "--no-renames", "origin/main", BRANCH, cwd=other).split(),
                         [WIDGET])
        self.assertIn(X_FILE, self.git("diff", "--name-only", "--no-renames", base_main, BRANCH, cwd=other).split())
        self.assertNotEqual(self.origin_head("main"), base_main)  # origin's real main moved past the local ref
        self.assertFlags(BRANCH, "Files: %s\n" % X_FILE, missing=[X_FILE])

    def test_a_fix_round_base_sha_leaves_out_a_fix_that_never_landed(self):
        self.git("checkout", "-q", "-b", BRANCH, "main")
        self.commit({X_FILE: X_TEXT}, "round one touches the file")
        round_one = self.commit({OTHER: OTHER_TEXT}, "round one ends here")
        self.commit({OTHER: "OTHER = 3\n"}, "round two changes another file")
        self.git("push", "-q", "origin", "%s:refs/heads/%s" % (BRANCH, BRANCH))
        self.git("checkout", "-q", "main")
        head = self.origin_head(BRANCH)
        # scope: against main the file is in the branch's change, and against the round-one sha it is not
        self.assertIn(X_FILE, self.git("diff", "--name-only", "--no-renames", "main", head).split())
        self.assertNotIn(X_FILE, self.git("diff", "--name-only", "--no-renames", round_one, head).split())
        self.assertPasses(BRANCH, "Files: %s\n" % X_FILE)  # against main, the earlier touch counts
        self.assertFlags(BRANCH, "Files: %s\n" % X_FILE, missing=[X_FILE], args=("--base", round_one))

    def test_a_check_run_makes_three_git_calls(self):
        self.pushed_branch(BRANCH, {WIDGET: WIDGET_TEXT})
        self.scope(BRANCH, WIDGET)
        shim = os.path.join(self.root, "count_calls.py")
        with open(shim, "w", encoding="utf-8") as f:
            f.write(counting_shim())
        done = subprocess.run([sys.executable, shim, "--branch", BRANCH], cwd=self.work,
                              input="Files: %s\n" % WIDGET, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=GIT_ENV)
        out = done.stdout + done.stderr
        self.assertEqual(done.returncode, 0, "exit %d, want 0:\n%s" % (done.returncode, out))
        calls = [line.split()[1:] for line in done.stdout.splitlines() if line.startswith("GIT_CALLS")]
        self.assertEqual(calls, [["fetch", "rev-parse", "diff"]], "git calls per run, want fetch, rev-parse, diff:\n" + out)

    @unittest.skipIf(os.name == "nt", "closing fd 0 needs POSIX (preexec_fn)")
    def test_a_closed_stdin_with_no_report_flag_is_unknown(self):
        self.pushed_branch(BRANCH, {WIDGET: WIDGET_TEXT})
        self.scope(BRANCH, WIDGET)
        rc, out = self.run_check_closed_stdin(BRANCH)
        self.assertEqual(rc, 2, "exit %d, want 2 (UNKNOWN) with stdin closed and no --report:\n%s" % (rc, out))
        self.assertIn("UNKNOWN", out, out)
        self.assertNotIn("Traceback", out, out)

    @unittest.skipIf(os.name == "nt", "closing fd 0 needs POSIX (preexec_fn)")
    def test_a_closed_stdin_with_a_report_file_reads_the_file(self):
        self.pushed_branch(BRANCH, {WIDGET: WIDGET_TEXT})
        self.scope(BRANCH, WIDGET)
        path = os.path.join(self.root, "closed-stdin-report.txt")
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("Files: %s\n" % WIDGET)
        rc, out = self.run_check_closed_stdin(BRANCH, args=("--report", path))
        self.assertEqual(rc, 0, "exit %d, want 0 with stdin closed and --report naming a file:\n%s" % (rc, out))
        self.assertNotIn("Traceback", out, out)

    def test_label_range_period_and_semicolon_forms_pass(self):
        self.pushed_branch(BRANCH, {LINT_A: "X = 1\n", LINT_B: "Y = 2\n"})
        self.scope(BRANCH, LINT_A, LINT_B)
        self.assertPasses(BRANCH, "Files: %s\n" % LINT_A)  # control: the plain form passes
        forms = (
            "%s (new)" % LINT_A,
            "%s:10-20 (new)" % LINT_A,
            "**%s**:10-20" % LINT_A,
            "%s : 10-20" % LINT_A,
            "%s (lines 10-20)" % LINT_A,
            "%s:L10-L20" % LINT_A,
            "%s." % LINT_A,
            "%s; %s" % (LINT_A, LINT_B),
        )
        for form in forms:
            with self.subTest(form=form):
                self.assertPasses(BRANCH, "Files: %s\n" % form)

    def test_a_form_with_a_missing_path_still_fails_and_names_it(self):
        self.pushed_branch(BRANCH, {LINT_A: "X = 1\n"})
        self.scope(BRANCH, LINT_A)
        missing = "lint/never_applied.py"
        self.assertNotIn(missing, self.diff_names(self.origin_head(BRANCH)))  # scope: the path is not in the diff
        forms = ("%s (new)" % missing, "%s; %s" % (LINT_A, missing), "**%s**:10-20" % missing, "%s." % missing)
        for form in forms:
            with self.subTest(form=form):
                self.assertFlags(BRANCH, "Files: %s\n" % form, missing=[missing])

    def test_a_files_line_naming_none_is_unknown(self):
        self.pushed_branch(BRANCH, {WIDGET: WIDGET_TEXT})
        self.scope(BRANCH, WIDGET)
        self.assertUnknown(BRANCH, "Files: none\n", named=["UNKNOWN"])

    def test_a_missing_report_file_is_unknown(self):
        self.pushed_branch(BRANCH, {WIDGET: WIDGET_TEXT})
        self.scope(BRANCH, WIDGET)
        path = os.path.join(self.root, "no-such-report.txt")
        self.assertFalse(os.path.exists(path))  # scope: the report file is absent
        self.assertUnknown(BRANCH, "", named=["UNKNOWN"], args=("--report", path))

    def test_a_bad_root_is_unknown(self):
        self.pushed_branch(BRANCH, {WIDGET: WIDGET_TEXT})
        self.scope(BRANCH, WIDGET)
        notrepo = os.path.join(self.root, "notrepo")
        os.makedirs(notrepo)
        absent = os.path.join(self.root, "no-such-dir")
        # the ceiling stops git from finding the repo above the fixture, so notrepo is not in one
        env = dict(GIT_ENV, GIT_CEILING_DIRECTORIES=self.root)
        self.assertFalse(os.path.isdir(absent))  # scope: the directory is absent
        self.assertNotEqual(subprocess.run(["git", "-C", notrepo, "rev-parse"], capture_output=True,
                                           env=env).returncode, 0, "scope: notrepo is a repo")
        for label, root in (("no such directory", absent), ("not a repo", notrepo)):
            with self.subTest(label):
                self.assertUnknown(BRANCH, "Files: %s\n" % WIDGET, named=["UNKNOWN"],
                                   args=("--root", root), env=env)

    def test_two_files_lines_are_unknown(self):
        self.pushed_branch(BRANCH, {WIDGET: WIDGET_TEXT, OTHER: OTHER_TEXT})
        self.scope(BRANCH, WIDGET, OTHER)
        self.assertUnknown(BRANCH, "Files: %s\nFiles: %s\n" % (WIDGET, OTHER), named=["UNKNOWN"])

    def test_a_range_with_no_path_before_it_is_unknown(self):
        self.pushed_branch(BRANCH, {WIDGET: WIDGET_TEXT})
        self.scope(BRANCH, WIDGET)
        for report in ("Files: 10-20\n", "Files: 10-20, %s\n" % WIDGET):
            with self.subTest(report=report):
                self.assertUnknown(BRANCH, report, named=["UNKNOWN"])


class ControlCase(Fixture):
    """Fixture facts the check cases rely on. No case here runs the check, so each passes on a tree without it."""

    def test_origin_holds_the_pushed_head_and_main(self):
        head = self.pushed_branch(BRANCH, {WIDGET: WIDGET_TEXT})
        self.assertEqual(self.origin_head(BRANCH), head)
        self.assertEqual(self.origin_head("main"), self.git("rev-parse", "main"))

    def test_a_local_commit_is_not_on_origin(self):
        self.pushed_branch(BRANCH, {OTHER: OTHER_TEXT})
        local = self.unpushed_commit(BRANCH, {WIDGET: WIDGET_TEXT})
        self.assertNotEqual(self.origin_head(BRANCH), local)

    def test_a_local_only_branch_is_not_on_origin(self):
        self.local_only(BRANCH, {WIDGET: WIDGET_TEXT})
        self.assertTrue(self.git("rev-parse", "--verify", BRANCH))
        self.assertEqual(self.origin_head(BRANCH), "")

    def test_a_rename_reads_as_a_rename_under_detection(self):
        self.on_main({"lint/old_name.py": RENAMED_TEXT}, "main gets the file to rename")
        head = self.pushed_branch(BRANCH, {"lint/old_name.py": None, "lint/new_name.py": RENAMED_TEXT})
        status = self.git("diff", "--name-status", "-M", "main", head)
        self.assertTrue(any(line.startswith("R") for line in status.splitlines()), status)


if __name__ == "__main__":
    unittest.main()
