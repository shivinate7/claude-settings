#!/usr/bin/env python3
"""Fixture suite for lint/check_guardset_lists.py, and the pin that job checks runs it.

The guard set is one list, the manifest hooks/guard-set.txt: one file name per line, sorted, in the form of
landed-dirs.txt. install.sh, install.ps1 (its PowerShell set loop and the post-merge hook it writes) and ci-scope.sh
read it at run time and hold no list of their own. hooks/test_install_src.sh checks the manifest names each flat
module a guard file imports (guardset4, guardset7, guardset8), but only job checks-install-checkout runs that file.
Lane lint runs job checks alone, so a short manifest can pass lane lint while the install checkout job goes red.

Each behaviour case finds the step in job checks first, then runs the command that step runs, in a fixture
built from disk. On a commit with no such step, every behaviour case fails on that one named cause.
A manifest case edits the fixture's manifest (make_fixture's `manifest`), and a copy case writes a list into a file that
must not hold one (`edits`). On a tree whose check ignores the manifest, each such case exits 0 where it wants 1.
"""
import os
import re
import shutil
import subprocess
import sys
import unittest
import uuid

HERE = os.path.dirname(os.path.realpath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  the one home of the run folder and its sweep (lint/_test_temp.py)
from workflow_steps import job_block, run_body, step_blocks, step_key  # noqa: E402  the one home of the step parser (lint/workflow_steps.py)

CHECK = "lint/check_guardset_lists.py"
CONTROL = "lint/check_unknown_reads_contract.py"  # a step that job checks already runs: the locator's green control
CHECKS_YML = os.path.join(REPO, ".github", "workflows", "checks.yml")
PROBE = "zz_guardset_probe.py"  # a flat module that no guard-set list names
MANIFEST = os.path.join("hooks", "guard-set.txt")  # the one list of the guard set's files
MANIFEST_NAME = "guard-set.txt"  # how a failure names it
# Ten files the manifest names today. A line that names eight or more of them is a copy of the list. The names are a sample, not
# the list: a copy needs no more than these to be one.
SAMPLE = ("shared_names.py git_reads.py question_form.py own_session.py precompact_handoff.py merge_options.py "
          "override.py _nowindow.py proc_env.py reread_check.py").split()
SORT_A, SORT_B = "zz_sort_a.py", "zz_sort_b.py"  # two hooks files for the order cases: each is a real file, so no other cause fails
INSTALL_SH, INSTALL_PS1 = "install.sh", "install.ps1"
CI_SCOPE = os.path.join(".github", "scripts", "ci-scope.sh")
FIXTURE_DIRS = ("hooks", "lint", "testing", os.path.join(".github", "scripts"))
FIXTURE_FILES = ("install.sh", "install.ps1", "landed-dirs.txt")
TIMEOUT = 300  # hang guard: the guard-set cases run in about 5 s
SUITE = os.path.join("hooks", "test_install_src.sh")
HANG_SUITE = "#!/bin/sh\nexec sleep 60\n"  # runs 60 s, so a cap of 1 s always ends it first
# A suite whose every guard-set case passes at once. A case about the manifest's form, the readers or a copied list runs the check with
# it, so the only cause of a red verdict is the one the case names, and the run skips the suite's own 5 s.
PASSING_SUITE = "#!/bin/sh\n" + "".join("echo 'ok   - guardset%d: fake'\n" % n for n in range(1, 21))
OK_THEN_EXIT_ONE = ("#!/bin/sh\necho 'ok   - guardset4: fake'\necho 'ok   - guardset7: fake'\n"
                    "echo 'ok   - guardset8: fake'\nexit 1\n")
NO_STEP = "job checks in .github/workflows/checks.yml has no step that runs `python3 %s`, so a short guard-set list passes lane lint"
RUN = ""  # this run's folder, made in setUpModule


def tail(text, lines=30):
    return "\n".join(text.splitlines()[-lines:])


def checks_steps():
    """(name, run text) of each step of job checks, read by line."""
    with open(CHECKS_YML, encoding="utf-8") as fh:
        block = job_block(fh.read(), "checks") or ""
    return [(step_key(step, "name") or "", run_body(step) or "") for step in step_blocks(block)]


def find_step(script):
    """(name, command) of the step of job checks whose run is `python3 <script>` alone, or None."""
    line = re.compile(r"^python3 %s[ \t]*$" % re.escape(script), re.M)
    for name, body in checks_steps():
        m = line.search(body)
        if m:
            return name, m.group(0).strip()
    return None


def run_command(command, cwd):
    done = subprocess.run(command.split(), cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT)
    return done.returncode, done.stdout + done.stderr


def make_fixture(name, probe=False, drop_case=None, suite=None, cap=None, manifest=0, edits=(), files=None):
    """A git-initialised copy of the guard-set tree, built from disk. `probe` adds one flat module that a guard
    file imports and no list names. `drop_case` takes one `run <case>` line out of the case list, so it never runs.
    `suite` replaces the text of the suite file, and `cap` sets the check's TIMEOUT to that many seconds.
    `manifest` changes hooks/guard-set.txt: a function from its text ("" when the tree has none) to the new text, or None
    to remove it. `edits` is (path, function) pairs: each function turns that file's text into the text written back,
    read and written with no line-end change. `files` maps a new path to its text."""
    root = os.path.join(RUN, name)
    os.makedirs(root)
    for d in FIXTURE_DIRS:
        shutil.copytree(os.path.join(REPO, d), os.path.join(root, d),
                        ignore=shutil.ignore_patterns("__pycache__", ".git"))
    for f in FIXTURE_FILES:
        shutil.copy2(os.path.join(REPO, f), os.path.join(root, f))
    # tracked_tree.sh lists the fixture's files with git, so the fixture is a repository of its own.
    subprocess.run(["git", "init", "-q", root], check=True, capture_output=True)
    if probe:
        with open(os.path.join(root, "hooks", PROBE), "w", encoding="utf-8") as fh:
            fh.write("# A flat module that a guard file imports. No guard-set list names it.\n")
        with open(os.path.join(root, "hooks", "guard.py"), "a", encoding="utf-8") as fh:
            fh.write("\nimport %s  # the guard-set probe\n" % PROBE[:-3])
    if drop_case:
        path = os.path.join(root, SUITE)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        line = "\nrun %s\n" % drop_case
        if text.count(line) != 1:
            raise AssertionError("the case list holds `run %s` %d times, want once" % (drop_case, text.count(line)))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text.replace(line, "\n"))
    if suite is not None:
        with open(os.path.join(root, SUITE), "w", encoding="utf-8") as fh:
            fh.write(suite)
    if cap is not None:
        path = os.path.join(root, CHECK)
        with open(path, encoding="utf-8") as fh:
            text, n = re.subn(r"^TIMEOUT = \d+", "TIMEOUT = %d" % cap, fh.read(), flags=re.M)
        if n != 1:
            raise AssertionError("the check holds `TIMEOUT = <n>` %d times, want once" % n)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    for rel, text in (files or {}).items():
        with open(os.path.join(root, rel), "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
    for rel, change in edits:
        edit_file(root, rel, change)
    if manifest != 0:
        path = os.path.join(root, MANIFEST)
        if manifest is None:
            if os.path.exists(path):
                os.remove(path)
        else:
            edit_file(root, MANIFEST, manifest, missing_ok=True)
    return root


def edit_file(root, rel, change, missing_ok=False):
    """Rewrite one fixture file through `change`, with its line ends as they are. A file the tree lacks reads as ''
    only when `missing_ok`: the manifest of a tree that has none yet."""
    path = os.path.join(root, rel)
    if missing_ok and not os.path.exists(path):
        text = ""
    else:
        with open(path, encoding="utf-8", newline="") as fh:
            text = fh.read()
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(change(text))


def add_entries(*names):
    """A manifest change: each name as a last line, in the order given."""
    def change(text):
        return text + ("" if not text or text.endswith("\n") else "\n") + "".join(n + "\n" for n in names)
    return change


def crlf(change):
    """A manifest change that gives every line of what `change` made a CRLF end."""
    return lambda text: change(text).replace("\r\n", "\n").replace("\n", "\r\n")


def append_lines(*lines):
    """An `edits` change: the lines at the end of the file."""
    return lambda text: text + ("" if text.endswith("\n") else "\n") + "".join(l + "\n" for l in lines)


def in_hook_here_string(line):
    """An `edits` change for install.ps1: the line first inside the here-string that holds the post-merge hook."""
    def change(text):
        marker = '    $hook = @"\n'
        if text.count(marker) != 1:
            raise AssertionError("install.ps1 holds the hook's here-string opener %d times, want once" % text.count(marker))
        return text.replace(marker, marker + line + "\n")
    return change


def without_manifest_name(outside_here_string):
    """An `edits` change for install.ps1 that makes each `guard-set.txt` in the text outside the post-merge hook's here-string
    (`outside_here_string`), or inside it, a name no file has. The other part is left as it is."""
    def change(text):
        opener, closer = '    $hook = @"\n', '\n"@\n'
        if text.count(opener) != 1 or text.count(closer) != 1:
            raise AssertionError("install.ps1 does not hold the hook's here-string once")
        head, rest = text.split(opener)
        body, tail = rest.split(closer)
        gone = lambda part: part.replace("guard-set.txt", "guard-set.gone")
        if outside_here_string:
            return gone(head) + opener + body + closer + gone(tail)
        return head + opener + gone(body) + closer + tail
    return change


def setUpModule():
    global RUN
    RUN = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN, ignore_errors=True)


class Base(unittest.TestCase):
    def locate(self):
        """The check's step in job checks. Found before any fixture is built: the wiring is the subject."""
        found = find_step(CHECK)
        self.assertIsNotNone(found, NO_STEP % CHECK)
        return found


class WiringPin(Base):
    def test_checks_job_has_a_step_that_runs_the_check(self):
        self.locate()

    def test_ci_job_plan_lists_the_check_step(self):
        name, _ = self.locate()
        done = subprocess.run([sys.executable, os.path.join(REPO, "bin", "ci-job"), "checks", "--plan"],
                              cwd=REPO, capture_output=True, text=True, timeout=TIMEOUT)
        listed = re.search(r"^would run[ \t]+%s[ \t]*$" % re.escape(name), done.stdout, re.M)
        self.assertIsNotNone(listed, "bin/ci-job checks --plan does not list the step %r as `would run` (exit %d)"
                             % (name, done.returncode))


class LocatorControl(unittest.TestCase):
    def test_locator_finds_a_step_that_job_checks_already_runs(self):
        self.assertIsNotNone(find_step(CONTROL), "the locator finds no step in job checks that runs `python3 %s`" % CONTROL)


class GuardSetCheck(Base):
    def test_a_short_list_exits_one_and_names_the_probe(self):
        _, command = self.locate()
        code, out = run_command(command, make_fixture("short", probe=True))
        self.assertEqual(code, 1, "the step exits %d on a short list, want 1:\n%s" % (code, tail(out)))
        self.assertIn(PROBE, out, "the output does not name %s:\n%s" % (PROBE, tail(out)))
        self.assertIn(MANIFEST_NAME, out, "the output does not name the list to edit, %s:\n%s" % (MANIFEST_NAME, tail(out)))

    def test_a_module_named_only_in_the_manifest_exits_zero(self):
        _, command = self.locate()
        code, out = run_command(command, make_fixture("listed", probe=True, manifest=add_entries(PROBE)))
        self.assertEqual(code, 0, "the step exits %d when the manifest names %s, want 0:\n%s" % (code, PROBE, tail(out)))

    def test_a_manifest_with_crlf_line_ends_exits_zero(self):
        _, command = self.locate()
        code, out = run_command(command, make_fixture("crlf", probe=True, manifest=crlf(add_entries(PROBE))))
        self.assertEqual(code, 0, "the step exits %d when each manifest line ends CRLF and names %s, want 0:\n%s" % (code, PROBE, tail(out)))

    def test_complete_lists_exit_zero(self):
        _, command = self.locate()
        code, out = run_command(command, make_fixture("complete"))
        self.assertEqual(code, 0, "the step exits %d on the repo's lists, want 0:\n%s" % (code, tail(out)))

    def test_a_case_that_does_not_run_exits_one_and_names_it(self):
        _, command = self.locate()
        code, out = run_command(command, make_fixture("dropped", drop_case="guardset7"))
        self.assertEqual(code, 1, "the step exits %d when guardset7 never runs, want 1:\n%s" % (code, tail(out)))
        self.assertIn("guardset7", out, "the output does not name guardset7:\n%s" % tail(out))

    def test_a_suite_past_its_cap_exits_one_and_says_it_did_not_finish(self):
        _, command = self.locate()
        code, out = run_command(command, make_fixture("hang", suite=HANG_SUITE, cap=1))
        self.assertEqual(code, 1, "the step exits %d when the suite runs past its cap, want 1:\n%s" % (code, tail(out)))
        self.assertIn("did not finish", out, "the output does not say the suite did not finish:\n%s" % tail(out))

    def test_every_case_ok_then_suite_exit_non_zero_exits_one(self):
        _, command = self.locate()
        code, out = run_command(command, make_fixture("exit-after-ok", suite=OK_THEN_EXIT_ONE))
        self.assertEqual(code, 1, "the step exits %d when each case prints ok and the suite exits 1, want 1:\n%s" % (code, tail(out)))
        self.assertIn("exited 1", out, "the output does not say the suite exited 1:\n%s" % tail(out))


class ManifestForm(Base):
    """The manifest is one file name per line, sorted, none twice, each a file in hooks/, with at least one. A name is a whole line:
    a merge of two lanes that each add a line must leave a list the check can still read. One cause per case."""
    SORT_FILES = {os.path.join("hooks", SORT_A): "# a hooks file for the order cases\n",
                  os.path.join("hooks", SORT_B): "# a hooks file for the order cases\n"}

    def refuses(self, name, why, *must_name, **fixture):
        _, command = self.locate()
        code, out = run_command(command, make_fixture(name, suite=PASSING_SUITE, **fixture))
        self.assertEqual(code, 1, "the step exits %d on %s, want 1:\n%s" % (code, why, tail(out)))
        for text in must_name:
            self.assertIn(text, out, "the output does not name %s:\n%s" % (text, tail(out)))

    def test_an_unsorted_manifest_exits_one_and_names_the_entry(self):
        self.refuses("unsorted", "%s listed before %s" % (SORT_B, SORT_A), SORT_A, MANIFEST_NAME,
                     files=self.SORT_FILES, manifest=add_entries(SORT_B, SORT_A))

    def test_a_sorted_manifest_with_the_same_two_entries_exits_zero(self):  # control: the order is the only difference
        _, command = self.locate()
        code, out = run_command(command, make_fixture("sorted", suite=PASSING_SUITE, files=self.SORT_FILES, manifest=add_entries(SORT_A, SORT_B)))
        self.assertEqual(code, 0, "the step exits %d on %s then %s, want 0:\n%s" % (code, SORT_A, SORT_B, tail(out)))

    def test_a_repeated_entry_exits_one_and_names_it(self):
        self.refuses("repeated", "%s listed twice" % SORT_A, SORT_A, MANIFEST_NAME,
                     files=self.SORT_FILES, manifest=add_entries(SORT_A, SORT_A))

    def test_an_entry_that_names_no_file_exits_one_and_names_it(self):
        self.refuses("no-file", "an entry with no file in hooks/", "zz_no_such_module.py", MANIFEST_NAME,
                     manifest=add_entries("zz_no_such_module.py"))

    def test_a_manifest_with_no_entry_exits_one_and_names_it(self):
        self.refuses("empty", "a manifest of comments only", MANIFEST_NAME,
                     manifest=lambda text: "# the guard set's files: none yet\n")

    def test_a_missing_manifest_exits_one_and_names_it(self):
        self.refuses("missing", "no manifest", MANIFEST_NAME, manifest=None)


class OneListScan(Base):
    """The list lives in the manifest alone. A line of install.sh, install.ps1 or ci-scope.sh that names eight or more files of it is a
    copy that drifts (the copies it replaces had already drifted: ci-scope.sh lacked lease.py, the comments lacked answered_claims.py).
    The scan reads text, never the language: it counts a name after a `#` inside a quoted string, in a comment, after a lone quote, and
    inside the here-string that holds the post-merge hook. ci-scope.sh's shoot arm names members for the page export suite's own
    import list, which lint/test_ci_scope.py walks, so a line that sets the shoot flag is no copy."""
    NAMES = " ".join(SAMPLE)

    def copy_in(self, label, rel, change, want_name):
        _, command = self.locate()
        code, out = run_command(command, make_fixture("copy-" + re.sub(r"\W+", "-", label), suite=PASSING_SUITE, edits=((rel, change),)))
        self.assertEqual(code, 1, "the step exits %d with a ten-name list as %s in %s, want 1:\n%s" % (code, label, rel, tail(out)))
        self.assertIn(want_name, out, "the output does not name %s:\n%s" % (want_name, tail(out)))

    def test_a_list_in_install_sh_exits_one_and_names_it(self):
        contexts = (
            ("a code line", ['SAMPLE_COPY="%s"' % self.NAMES]),
            ("a comment line", ["# the set: %s" % self.NAMES]),
            ("a name after a # inside a string", ['x="# a"; : %s' % self.NAMES]),
            ("a line after a lone quote", ["# Don't miss the set below", ': %s' % self.NAMES]),
        )
        for label, lines in contexts:
            with self.subTest(context=label):
                self.copy_in(label, INSTALL_SH, append_lines(*lines), INSTALL_SH)

    def test_a_list_in_install_ps1_exits_one_and_names_it(self):
        contexts = (
            ("a PowerShell line", append_lines("$SampleCopy = '%s'" % self.NAMES)),
            ("a line inside the hook's here-string", in_hook_here_string(": %s" % self.NAMES)),
        )
        for label, change in contexts:
            with self.subTest(context=label):
                self.copy_in(label, INSTALL_PS1, change, INSTALL_PS1)

    def test_a_list_in_ci_scope_exits_one_and_names_it(self):
        self.copy_in("a case arm", CI_SCOPE, append_lines('      hooks/zz.py|%s) on="$on code " ;;' % "|".join("hooks/" + n for n in SAMPLE)),
                     "ci-scope.sh")

    def test_a_line_naming_seven_members_exits_zero(self):  # control: seven is no copy, so the boundary is the count
        _, command = self.locate()
        code, out = run_command(command, make_fixture("seven", suite=PASSING_SUITE, edits=((INSTALL_SH, append_lines(": " + " ".join(SAMPLE[:7]))),)))
        self.assertEqual(code, 0, "the step exits %d with a seven-name line in install.sh, want 0:\n%s" % (code, tail(out)))


class ManifestReaders(Base):
    """install.sh, and install.ps1 in its PowerShell set loop and in the hook it writes, each name the manifest in a line that is no
    comment. Without it the file holds no list and reads none, so a guard set lands empty. install.sh's reads are run by
    hooks/test_install_src.sh (guardset10 to guardset14); this check is the one that job checks runs. PowerShell cannot run here, so
    the text is what job checks reads. The reader must take LF and CRLF line ends and run on Windows PowerShell 5.1: the helper that
    reads landed-dirs.txt (Get-LandedDirs, Get-Content) is the form."""

    def refuses(self, name, rel, change, why):
        _, command = self.locate()
        code, out = run_command(command, make_fixture(name, suite=PASSING_SUITE, edits=((rel, change),)))
        self.assertEqual(code, 1, "the step exits %d when %s, want 1:\n%s" % (code, why, tail(out)))
        self.assertIn(rel.replace(os.sep, "/").split("/")[-1], out, "the output does not name %s:\n%s" % (rel, tail(out)))

    def test_install_sh_that_never_names_the_manifest_exits_one_and_names_it(self):
        self.refuses("sh-no-reader", INSTALL_SH, lambda text: text.replace(MANIFEST_NAME, "guard-set.gone"),
                     "install.sh never names %s" % MANIFEST_NAME)

    def test_install_ps1_that_never_names_the_manifest_in_powershell_exits_one_and_names_it(self):
        self.refuses("ps1-no-reader", INSTALL_PS1, without_manifest_name(outside_here_string=True),
                     "install.ps1 names %s only inside the hook's here-string" % MANIFEST_NAME)

    def test_install_ps1_hook_that_never_names_the_manifest_exits_one_and_names_it(self):
        self.refuses("hook-no-reader", INSTALL_PS1, without_manifest_name(outside_here_string=False),
                     "install.ps1's post-merge hook never names %s" % MANIFEST_NAME)


class RunFolderSweep(unittest.TestCase):
    def test_sweep_removes_an_old_sibling_and_keeps_a_new_one(self):
        temp_root = os.path.join(RUN, "sweep")
        now = 1800000000.0  # a synthetic clock: the sweep reads ages from it, never the real date
        old = os.path.join(temp_root, "999999-%s" % uuid.uuid4().hex)
        new = os.path.join(temp_root, "999998-%s" % uuid.uuid4().hex)
        own = os.path.join(temp_root, "%d-%s" % (os.getpid(), uuid.uuid4().hex))
        for path, age in ((old, 2 * 86400), (new, 60), (own, 2 * 86400)):
            os.makedirs(path)
            os.utime(path, (now - age, now - age))
        _test_temp.sweep(temp_root, own, now=now)
        self.assertFalse(os.path.exists(old), "the sweep kept a sibling two days old")
        self.assertTrue(os.path.exists(new), "the sweep removed a sibling one minute old")
        self.assertTrue(os.path.exists(own), "the sweep removed the run's own folder")


if __name__ == "__main__":
    unittest.main()
