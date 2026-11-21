#!/usr/bin/env python3
"""Cases for lint/find_copies.py. Standard library only.

    python3 lint/test_find_copies.py

Each case builds a temp parent and a temp child, then runs the real script on them. The
fixtures copy the shape of the worked examples: q_max's drifted plain-english-map skill,
q_max's verbatim copy of a parent test with a header added, and the impeccable copies in
ios-adblock, joyous and degen, which differ from the parent and from each other.
FIND_COPIES_UNDER_TEST overrides the module path.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _test_temp  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.environ.get("FIND_COPIES_UNDER_TEST") or os.path.join(HERE, "find_copies.py")
RUN_FOLDER = _test_temp.run_folder()  # test-temp-standard (one run folder per test run)

SKILL_MD = "---\nname: {name}\ndescription: A shared skill for the fixture.\n---\n\n" + "".join(
    f"Step {i}: do the shared thing number {i} with care.\n" for i in range(12)
)
HELPER = "".join(f"export function helper{i}(value) {{ return value * {i} + 1; }}\n" for i in range(15))
TEST = "// Red proof: node --test testing/\nimport { helper } from './helper.mjs';\n" + "".join(
    f"test('case {i} keeps its promise', () => assert.equal(helper({i}), {i * 2}));\n" for i in range(15)
)
# Comment openers inside strings, a multi-line template literal and a lone quote in text.
TRAPS = (
    "const a = 'not /* a comment';\nconst b = \"not // a comment either\";\nconst c = `line one\n"
    "line two # not a comment`;\nconst d = <p>Don't stop here</p>;\n"
    + "".join(f"const keep{i} = 'value number {i} for the trap file';\n" for i in range(10))
)

# A PR template the size of the real one: over MIN_BYTES and over MIN_LINES significant lines,
# so a miss is a real miss and not boilerplate that a floor skips.
PR_TEMPLATE = (
    "## Summary\n\n"
    + "".join(f"Summary line {i}: say what this pull request changes and why it matters.\n" for i in range(12))
    + "\n## Test plan\n\n"
    + "".join(f"Check {i}: name the command you ran and its verdict for this change.\n" for i in range(6))
)
OWN_TEMPLATE = ".github/pull_request_template.md"  # a child's own copy of the parent's PR template
CONTROL = "vendor/whatever.mjs"  # a child copy of another parent file, reported in every run
# A parent file of 20 significant lines, none of them in PR_TEMPLATE. A child template that holds the
# template and this file whole scores 1.0 for both, and the ranking picks the template.
Z_TEXT = "".join(f"export function zed{i}(value) {{ return value + {i}; }}\n" for i in range(20))
Z_EDITED = Z_TEXT.replace("return value + 3;", "return value + 33;", 1)  # a near copy: 19 of 20 lines
# The parent's twin of the template at a second path, drifted on line 3 only, and a 100-line parent file
# that shares no line with the template.
TWIN = ".claude/pull_request_template.md"
DRIFTED_TWIN = PR_TEMPLATE.replace("Summary line 0: say", "Summary line 0: this parent says", 1)
LONG = "testing/long.mjs"
LONG_TEXT = "".join(f"export function long{i}(value) {{ return value - {i}; }}\n" for i in range(100))


def module_under_test():
    """The module under test, loaded to read its floors: MIN_BYTES, MIN_LINES, significant_lines."""
    spec = importlib.util.spec_from_file_location("find_copies_under_test", MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def text_reports(stdout, child):
    """True when the text report has a file line for this child path."""
    return any(line.startswith("file " + child + " ") for line in stdout.splitlines())


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def make_parent(root):
    write(root, "skills/impeccable/SKILL.md", SKILL_MD.format(name="impeccable"))
    write(root, "skills/impeccable/scripts/run.mjs", HELPER)
    write(root, "skills/impeccable/reference/document.md", "".join(f"Rule {i} of the reference.\n" for i in range(12)))
    write(root, "skills/plain-english-map/SKILL.md", SKILL_MD.format(name="plain-english-map"))
    write(root, "skills/plain-english-map/scripts/map-check.mjs", HELPER)
    write(root, "skills/plain-english-map/scripts/map-upgrade.mjs", HELPER.replace("helper", "upgrade"))
    write(root, "testing/skip-locally-fail-in-ci.test.mjs", TEST)
    write(root, "lint/traps.mjs", TRAPS)
    write(root, OWN_TEMPLATE, PR_TEMPLATE)
    write(root, "LICENSE", "MIT License\n" * 30)
    write(root, "actions/stamp/examples/frontmatter.stamp.json", HELPER)


def run(parent, child, *extra):
    proc = subprocess.run(
        [sys.executable, MODULE, child, "--parent", parent, *extra],
        capture_output=True, text=True, timeout=60,
    )
    return proc


def reaped_child_pid():
    """A pid whose process has run to its end, so no live process holds it."""
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait(timeout=60)
    return child.pid


def aged_folder(root, name, hours):
    path = os.path.join(root, name)
    os.makedirs(path)
    stamp = time.time() - hours * 3600
    os.utime(path, (stamp, stamp))
    return path


SYNTHETIC_NOW = 1800000000  # the sweep's clock in the hold case: a fixed epoch, so no case reads the real one


def folder_aged_at(root, name, now, days):
    path = os.path.join(root, name)
    os.makedirs(path)
    mtime = now - days * 24 * 60 * 60
    os.utime(path, (mtime, mtime))
    return path


def end_holder(proc):
    """Close the holder's stdin, so it reads EOF and exits, then reap it."""
    proc.stdin.close()
    proc.wait(timeout=60)


MERGE_TOOL = os.path.join(HERE, "..", "merge", "merge.py")


def merge_tool():
    """The merge tool loaded as its own module, the way lint/_test_temp.py loads it, so a case patches the copy its hold check calls."""
    spec = importlib.util.spec_from_file_location("merge_tool_under_test", MERGE_TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def janitor_sweep():
    """janitor/sweep.py, the module the merge tool's hold check reads a folder's processes through."""
    sys.path.insert(0, os.path.join(HERE, "..", "janitor"))
    import sweep  # janitor/sweep.py, the one reader of a process's cwd; merge.py imports it under this name
    return sweep


def fake_proc_stat(proc, pid, comm, flags, tpgid=0):
    """A fake /proc with one stat line for PID: its comm in parentheses, as the kernel writes it, the tpgid word as field 8 and the flags word as field 9."""
    write(proc, "%d/stat" % pid, "%d (%s) S 2 0 0 0 %d %d 0 0 0 0 0 0 0 20 0 1 0 1 0 0 0\n" % (pid, comm, tpgid, flags))


class RunFolderSweepTest(unittest.TestCase):
    """The sweep of test-temp-standard: a run folder whose pid is dead goes after an hour, and a live run's folder stays."""

    def test_old_sibling_goes_and_new_one_stays(self):
        root = os.path.join(RUN_FOLDER, "root")
        old = os.path.join(root, "1-" + "a" * 32)
        new = os.path.join(root, "2-" + "b" * 32)
        other = os.path.join(root, "not-a-run-folder")
        for path in (old, new, other):
            os.makedirs(path)
        two_days_ago = time.time() - 2 * 24 * 60 * 60
        os.utime(old, (two_days_ago, two_days_ago))
        os.utime(other, (two_days_ago, two_days_ago))
        own = _test_temp.run_folder(root)
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.isdir(new))
        self.assertTrue(os.path.isdir(other))
        self.assertTrue(os.path.isdir(own))

    def test_a_dead_pid_folder_over_an_hour_old_goes(self):
        root = os.path.join(RUN_FOLDER, "sweep-dead-hour")
        stale = aged_folder(root, "%d-%s" % (reaped_child_pid(), "c" * 32), 2)
        own = _test_temp.run_folder(root)
        self.assertFalse(os.path.exists(stale), "a run folder whose pid is dead and that is over an hour old must be swept")
        self.assertTrue(os.path.isdir(own), "the sweep must keep the run's own folder")

    def test_a_dead_pid_folder_under_an_hour_old_stays(self):
        root = os.path.join(RUN_FOLDER, "sweep-dead-fresh")
        control = aged_folder(root, "%d-%s" % (reaped_child_pid(), "c" * 32), 2)
        fresh = aged_folder(root, "%d-%s" % (reaped_child_pid(), "d" * 32), 0.5)
        _test_temp.run_folder(root)
        self.assertFalse(os.path.exists(control), "positive control: a dead-pid folder over an hour old must be swept in this run")
        self.assertTrue(os.path.isdir(fresh), "a run folder whose pid is dead but that is under an hour old must stay")

    def test_a_live_pid_folder_an_hour_old_stays(self):
        root = os.path.join(RUN_FOLDER, "sweep-live-hour")
        control = aged_folder(root, "%d-%s" % (reaped_child_pid(), "c" * 32), 2)
        live = aged_folder(root, "%d-%s" % (os.getpid(), "e" * 32), 2)
        _test_temp.run_folder(root)
        self.assertFalse(os.path.exists(control), "positive control: a dead-pid folder over an hour old must be swept in this run")
        self.assertTrue(os.path.isdir(live), "a run folder whose pid is alive must stay: a parallel run owns it")

    # A folder that a live process holds stays, whatever its age. The holder's cwd is the folder: the shape of a red-run copy.
    @unittest.skipUnless(sys.platform.startswith("linux"), "the hold read is /proc/<pid>/cwd; a Mac or Windows read is not designed yet")
    def test_a_folder_a_live_process_holds_stays_whatever_its_age(self):
        root = os.path.join(RUN_FOLDER, "sweep-held")
        os.makedirs(root)
        control = folder_aged_at(root, "%d-%s" % (os.getpid(), "c" * 32), SYNTHETIC_NOW, 2)
        held = folder_aged_at(root, "%d-%s" % (os.getpid(), "d" * 32), SYNTHETIC_NOW, 2)
        holder = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"], cwd=held, stdin=subprocess.PIPE)
        self.addCleanup(end_holder, holder)
        _test_temp.sweep(root, os.path.join(root, "own-run"), now=SYNTHETIC_NOW)
        self.assertFalse(os.path.exists(control), "positive control: an unheld folder two days old must be swept")
        self.assertTrue(os.path.isdir(held), "a run folder that a live process holds must stay, whatever its age")

    # A holder whose cwd cannot be read: the sweep cannot tell which folder it runs in, so the folder stays. Root reads every cwd here,
    # so the read is refused for the holder's pid alone. The unpatched read first shows that the holder does run in the folder.
    @unittest.skipUnless(sys.platform.startswith("linux"), "the hold read is /proc/<pid>/cwd; a Mac or Windows read is not designed yet")
    def test_a_folder_whose_holder_cwd_cannot_be_read_stays(self):
        sweep = janitor_sweep()
        root = os.path.join(RUN_FOLDER, "sweep-unreadable-holder")
        os.makedirs(root)
        held = folder_aged_at(root, "%d-%s" % (os.getpid(), "d" * 32), SYNTHETIC_NOW, 2)
        holder = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"], cwd=held, stdin=subprocess.PIPE)
        self.addCleanup(end_holder, holder)
        self.assertEqual(os.path.realpath(sweep.process_cwd(holder.pid)), os.path.realpath(held),
                         "control: the holder's cwd, read unpatched, is not the folder it was started in")
        reads = []
        real_process_cwd = sweep.process_cwd

        def refuse_the_holder(pid):
            reads.append(pid)
            return None if pid == holder.pid else real_process_cwd(pid)

        with mock.patch.object(sweep, "process_cwd", refuse_the_holder):
            _test_temp.sweep(root, os.path.join(root, "own-run"), now=SYNTHETIC_NOW)
        self.assertIn(holder.pid, reads, "scope: the sweep never read the holder's cwd, so the refusal was not reached")
        self.assertTrue(os.path.isdir(held), "a run folder whose holder's cwd cannot be read must stay: the sweep reaped it")

    # An unreadable pid below the folder's owner holds the folder, unless it is a kernel thread: a kernel thread's cwd is unreadable to a
    # user, and it descends from pid 2, so it must not tie to a folder named for this run. The child is this run's, so only the kernel
    # flag differs between the control and the case. The hold check is called on the merge tool's own module, whose kernel_thread is patched.
    @unittest.skipUnless(sys.platform.startswith("linux"), "the hold read is /proc/<pid>/stat and fd; a Mac or Windows read is not designed yet")
    def test_a_kernel_thread_holds_no_folder(self):
        tool = merge_tool()
        sweep = janitor_sweep()
        folder = os.path.join(RUN_FOLDER, "kthread-hold", "%d-%s" % (os.getpid(), "e" * 32))
        os.makedirs(folder)
        child = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE)
        self.addCleanup(end_holder, child)
        with mock.patch.object(sweep, "processes_in", return_value=([], [child.pid])):
            with mock.patch.object(tool, "kernel_thread", return_value=False, create=True):
                control = tool.held_by_live_process(folder)
            with mock.patch.object(tool, "kernel_thread", return_value=True, create=True):
                kernel = tool.held_by_live_process(folder)
        self.assertTrue(control, "positive control: an unreadable child of this run that is not a kernel thread must hold the folder")
        self.assertFalse(kernel, "a kernel thread holds no folder: the hold check kept a folder for an unreadable kernel thread")

    # kernel_thread reads field 9 after the last ")" of the stat, because the comm between the parentheses may hold both.
    def test_a_kernel_thread_with_parentheses_in_its_comm_reads_true(self):
        proc = os.path.join(RUN_FOLDER, "proc-kthread")
        fake_proc_stat(proc, 4242, "kworker/0:1 (x) y", 0x200000)
        self.assertTrue(merge_tool().kernel_thread(4242, proc=proc),
                        "a stat whose flags carry PF_KTHREAD reads as a kernel thread, whatever its comm holds")

    def test_a_comm_with_parentheses_and_no_kernel_flag_reads_false(self):
        proc = os.path.join(RUN_FOLDER, "proc-plain")
        # The kernel bit sits in field 8, where a parser that splits at the first ")" reads field 9. The flags word is 0.
        fake_proc_stat(proc, 4243, "a b) c", 0, tpgid=0x200000)
        self.assertFalse(merge_tool().kernel_thread(4243, proc=proc),
                         "a stat whose flags lack PF_KTHREAD reads as no kernel thread, whatever its comm holds")

    def test_a_missing_stat_reads_false(self):
        proc = os.path.join(RUN_FOLDER, "proc-missing")
        os.makedirs(proc)
        self.assertFalse(merge_tool().kernel_thread(4244, proc=proc),
                         "a pid whose stat cannot be read is never proven a kernel thread")


class FindCopiesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=RUN_FOLDER)
        self.parent = os.path.join(self.tmp.name, "parent")
        self.child = os.path.join(self.tmp.name, "child")
        make_parent(self.parent)
        os.makedirs(self.child)

    def tearDown(self):
        self.tmp.cleanup()

    def findings(self, *extra):
        proc = run(self.parent, self.child, "--json", *extra)
        self.assertIn(proc.returncode, (0, 1), proc.stderr)
        return proc.returncode, json.loads(proc.stdout)

    def test_clean_child_is_quiet(self):
        write(self.child, "src/app.ts", "".join(f"export const own{i} = {i};\n" for i in range(20)))
        write(self.child, "LICENSE", "MIT License\n" * 30)
        proc = run(self.parent, self.child)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("no copies", proc.stdout)

    def test_drifted_skill_copy(self):
        # q_max shape: the copy lags the parent, with edits and a missing file.
        base = ".claude/skills/plain-english-map"
        write(self.child, f"{base}/SKILL.md", SKILL_MD.format(name="plain-english-map") + "A local edit.\n")
        write(self.child, f"{base}/scripts/map-check.mjs", HELPER)
        code, out = self.findings()
        self.assertEqual(code, 1)
        skills = [f for f in out["skills"] if f["skill"] == "plain-english-map"]
        self.assertEqual(len(skills), 1, out)
        s = skills[0]
        self.assertEqual(s["child_path"], base)
        self.assertEqual(s["state"], "drifted")
        self.assertEqual(s["differ"], ["SKILL.md"])
        self.assertEqual(s["only_in_parent"], ["scripts/map-upgrade.mjs"])
        # Files inside a reported skill copy are not reported again as file copies.
        self.assertEqual([f for f in out["files"] if f["child"].startswith(base)], [])

    def test_identical_skill_copy_is_still_a_copy(self):
        base = ".claude/skills/impeccable"
        write(self.child, f"{base}/SKILL.md", SKILL_MD.format(name="impeccable"))
        write(self.child, f"{base}/scripts/run.mjs", HELPER)
        write(self.child, f"{base}/reference/document.md", "".join(f"Rule {i} of the reference.\n" for i in range(12)))
        code, out = self.findings()
        self.assertEqual(code, 1)
        self.assertEqual([(s["skill"], s["state"]) for s in out["skills"]], [("impeccable", "same")])

    def test_three_impeccable_copies_that_differ(self):
        # ios-adblock, joyous and degen each hold a copy that differs from the parent and from
        # the others. Each child is its own run, so each run reports its own copy.
        edits = {
            "ios-adblock": ("SKILL.md", "Edited for ios-adblock.\n"),
            "joyous": ("scripts/run.mjs", "// joyous edit\n"),
            "degen": ("reference/document.md", "Degen's own rule.\n"),
        }
        for repo, (rel, extra) in edits.items():
            child = os.path.join(self.tmp.name, repo)
            base = os.path.join(child, ".claude/skills/impeccable")
            write(base, "SKILL.md", SKILL_MD.format(name="impeccable"))
            write(base, "scripts/run.mjs", HELPER)
            write(base, "reference/document.md", "".join(f"Rule {i} of the reference.\n" for i in range(12)))
            with open(os.path.join(base, rel), "a", encoding="utf-8") as f:
                f.write(extra)
            proc = run(self.parent, child, "--json")
            self.assertEqual(proc.returncode, 1, repo + proc.stderr)
            out = json.loads(proc.stdout)
            self.assertEqual(len(out["skills"]), 1, repo)
            self.assertEqual(out["skills"][0]["state"], "drifted", repo)
            self.assertEqual(out["skills"][0]["differ"], [rel], repo)

    def test_skill_found_by_frontmatter_name_under_another_folder(self):
        write(self.child, "tools/map-skill/SKILL.md", SKILL_MD.format(name="plain-english-map"))
        code, out = self.findings()
        self.assertEqual(code, 1)
        self.assertEqual([(s["skill"], s["child_path"]) for s in out["skills"]],
                         [("plain-english-map", "tools/map-skill")])

    def test_verbatim_test_copy_with_header(self):
        # q_max shape: the parent test, with a provenance header added on top.
        header = "// Copied verbatim from claude-settings, testing/skip-locally-fail-in-ci.test.mjs.\n// Import path adapted.\n"
        write(self.child, "harness/tests/skip-locally-fail-in-ci.test.mjs", header + TEST)
        code, out = self.findings()
        self.assertEqual(code, 1)
        self.assertEqual(len(out["files"]), 1, out)
        f = out["files"][0]
        self.assertEqual(f["parent"], "testing/skip-locally-fail-in-ci.test.mjs")
        self.assertEqual(f["child"], "harness/tests/skip-locally-fail-in-ci.test.mjs")
        self.assertEqual(f["kind"], "near-equal")
        self.assertGreaterEqual(f["score"], 0.8)

    def test_byte_equal_file_under_another_name(self):
        write(self.child, "vendor/whatever.mjs", TEST)
        code, out = self.findings()
        self.assertEqual(code, 1)
        self.assertEqual([(f["parent"], f["kind"]) for f in out["files"]],
                         [("testing/skip-locally-fail-in-ci.test.mjs", "byte-equal")])

    def test_scanner_traps_compare_as_plain_text(self):
        write(self.child, "src/traps.mjs", TRAPS)
        code, out = self.findings()
        self.assertEqual(code, 1)
        self.assertEqual([(f["parent"], f["kind"]) for f in out["files"]], [("lint/traps.mjs", "byte-equal")])

    def test_large_file_that_quotes_a_parent_file_is_not_a_copy(self):
        write(self.child, "src/big.mjs", TEST + "".join(f"const mine{i} = 'own line {i}';\n" for i in range(60)))
        code, out = self.findings()
        self.assertEqual(code, 0, out)

    def test_scanner_traps_near_equal(self):
        write(self.child, "src/traps.mjs", "// local header\n" + TRAPS)
        code, out = self.findings()
        self.assertEqual([(f["parent"], f["kind"]) for f in out["files"]], [("lint/traps.mjs", "near-equal")])

    def test_shared_boilerplate_is_not_a_copy(self):
        # A file that shares a few common lines with a parent file is not a copy.
        write(self.child, "src/other.mjs", HELPER[:200] + "".join(f"const mine{i} = {i};\n" for i in range(40)))
        code, out = self.findings()
        self.assertEqual(code, 0, out)

    def test_parent_example_is_meant_to_be_copied(self):
        write(self.child, ".github/stamp.json", HELPER.replace("helper1(", "local1("))
        code, out = self.findings()
        self.assertEqual([f["parent"] for f in out["files"]],
                         ["skills/impeccable/scripts/run.mjs"])

    def test_missing_child_is_unknown(self):
        proc = run(self.parent, os.path.join(self.tmp.name, "nowhere"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("unknown", proc.stdout + proc.stderr)

    def own_template_run(self, text, *extra):
        # Scope first (P7): the fixture clears the floors, and the control shows the scan reached the child.
        mod = module_under_test()
        self.assertGreaterEqual(len(PR_TEMPLATE.encode()), mod.MIN_BYTES, "fixture: the PR template is under MIN_BYTES")
        self.assertGreaterEqual(len(mod.significant_lines(PR_TEMPLATE.encode())), mod.MIN_LINES,
                                "fixture: the PR template is under MIN_LINES")
        write(self.child, OWN_TEMPLATE, text)
        write(self.child, CONTROL, TEST)
        return run(self.parent, self.child, *extra)

    def assert_own_template_not_reported(self, text, mode):
        if mode == "json":
            proc = self.own_template_run(text, "--json")
            self.assertIn(proc.returncode, (0, 1), proc.stderr)
            reported = [f["child"] for f in json.loads(proc.stdout)["files"]]
            self.assertIn(CONTROL, reported, "control: the run did not report the other copy")
            self.assertNotIn(OWN_TEMPLATE, reported, "the child's own PR template is reported as a copy")
        else:
            proc = self.own_template_run(text)
            self.assertIn(proc.returncode, (0, 1), proc.stderr)
            self.assertTrue(text_reports(proc.stdout, CONTROL), "control: the run did not report the other copy")
            self.assertFalse(text_reports(proc.stdout, OWN_TEMPLATE), "the child's own PR template is reported as a copy")

    def test_own_pr_template_copy_is_not_reported(self):
        for mode in ("json", "text"):
            with self.subTest(mode=mode):
                self.assert_own_template_not_reported(PR_TEMPLATE, mode)

    def near_variants(self):
        edited = PR_TEMPLATE.replace("Check 0: name", "Check 0: this repo names", 1)
        self.assertNotEqual(edited, PR_TEMPLATE, "fixture: the one-line edit did not change the template")
        return {
            "header added": "<!-- added in this repo -->\n" + PR_TEMPLATE,
            "one line edited": edited,
        }

    def test_own_pr_template_near_copy_is_not_reported(self):
        for label, text in self.near_variants().items():
            for mode in ("json", "text"):
                with self.subTest(variant=label, mode=mode):
                    self.assert_own_template_not_reported(text, mode)

    def test_pr_template_copy_elsewhere_is_still_reported(self):
        write(self.child, "docs/pr.md", PR_TEMPLATE)
        code, out = self.findings()
        self.assertEqual([(f["child"], f["parent"], f["kind"]) for f in out["files"]],
                         [("docs/pr.md", OWN_TEMPLATE, "byte-equal")],
                         "a copy of the parent's PR template outside .github/ is not reported")

    def test_near_pr_template_copy_elsewhere_is_still_reported(self):
        write(self.child, "docs/pr-draft.md", "<!-- draft header -->\n" + PR_TEMPLATE)
        code, out = self.findings()
        self.assertEqual([(f["child"], f["parent"], f["kind"]) for f in out["files"]],
                         [("docs/pr-draft.md", OWN_TEMPLATE, "near-equal")],
                         "a near copy of the parent's PR template outside .github/ is not reported")

    def test_other_parent_copy_at_pr_template_path_is_still_reported(self):
        write(self.child, OWN_TEMPLATE, TEST)
        code, out = self.findings()
        self.assertEqual([(f["child"], f["parent"], f["kind"]) for f in out["files"]],
                         [(OWN_TEMPLATE, "testing/skip-locally-fail-in-ci.test.mjs", "byte-equal")],
                         "a copy of another parent file at the PR template path is not reported")

    def test_empty_own_pr_template_is_quiet(self):
        write(self.child, OWN_TEMPLATE, "")
        code, out = self.findings()
        self.assertEqual((code, out["files"]), (0, []), "an empty child PR template is reported")

    def assert_template_holds_parent_file(self, text):
        # Scope first (P7): the fixtures clear the floors and sit inside the growth bound, so a miss is the subject's.
        mod = module_under_test()
        tlines, zlines = mod.significant_lines(PR_TEMPLATE.encode()), mod.significant_lines(Z_TEXT.encode())
        clines = mod.significant_lines(text.encode())
        self.assertGreaterEqual(len(Z_TEXT.encode()), mod.MIN_BYTES, "fixture: the parent file is under MIN_BYTES")
        self.assertGreaterEqual(len(zlines), mod.MIN_LINES, "fixture: the parent file is under MIN_LINES")
        self.assertFalse(tlines & zlines, "fixture: the parent file shares a line with the template")
        self.assertTrue(tlines <= clines, "fixture: the child does not hold the whole template")
        self.assertGreaterEqual(len(zlines & clines) / len(zlines), 0.8,
                                "fixture: the child holds too little of the parent file")
        self.assertLessEqual(len(clines), mod.CHILD_GROWTH * min(len(tlines), len(zlines)),
                             "fixture: the child is over the growth bound for one of the two")
        write(self.parent, "testing/z.mjs", Z_TEXT)
        write(self.child, OWN_TEMPLATE, text)
        write(self.child, CONTROL, TEST)
        with self.subTest(mode="json"):
            proc = run(self.parent, self.child, "--json")
            self.assertIn(proc.returncode, (0, 1), proc.stderr)
            pairs = [(f["child"], f["parent"], f["kind"]) for f in json.loads(proc.stdout)["files"]]
            self.assertIn((CONTROL, "testing/skip-locally-fail-in-ci.test.mjs", "byte-equal"), pairs,
                          "control: the run did not report the other copy")
            self.assertIn((OWN_TEMPLATE, "testing/z.mjs", "near-equal"), pairs,
                          "the child's PR template holding a copy of testing/z.mjs is not reported as that copy")
        with self.subTest(mode="text"):
            proc = run(self.parent, self.child)
            self.assertIn(proc.returncode, (0, 1), proc.stderr)
            self.assertTrue(text_reports(proc.stdout, CONTROL), "control: the run did not report the other copy")
            lines = proc.stdout.splitlines()
            self.assertTrue(any(line.startswith(f"file {OWN_TEMPLATE} copies testing/z.mjs (near-equal, ")
                                for line in lines),
                            "the child's PR template holding a copy of testing/z.mjs is not reported as that copy")

    def test_own_pr_template_holding_a_parent_file_is_reported(self):
        # The template and the parent file tie at 1.0, and the ranking picks the template, so the old code excuses the file.
        self.assert_template_holds_parent_file(PR_TEMPLATE + Z_TEXT)

    def test_own_pr_template_holding_a_near_copy_of_a_parent_file_is_reported(self):
        self.assertNotEqual(Z_EDITED, Z_TEXT, "fixture: the one-line edit did not change the parent file")
        self.assert_template_holds_parent_file(PR_TEMPLATE + Z_EDITED)

    def test_own_pr_template_twin_in_parent_is_not_reported(self):
        # The parent keeps the same template at a second path. The child's own copy matches its own path.
        write(self.parent, ".claude/pull_request_template.md", PR_TEMPLATE)
        self.assertTrue(os.path.isfile(os.path.join(self.parent, ".claude", "pull_request_template.md")),
                        "fixture: the parent has no twin template")
        variants = {"copy": PR_TEMPLATE, **self.near_variants()}
        for label, text in variants.items():
            for mode in ("json", "text"):
                with self.subTest(variant=label, mode=mode):
                    self.assert_own_template_not_reported(text, mode)

    def assert_twin_would_be_reported(self, text):
        # Scope first (P7): the twin is a near copy of this child text, so the scan would report it without the rule.
        mod = module_under_test()
        tlines, clines = mod.significant_lines(DRIFTED_TWIN.encode()), mod.significant_lines(text.encode())
        self.assertGreaterEqual(len(DRIFTED_TWIN.encode()), mod.MIN_BYTES, "fixture: the twin is under MIN_BYTES")
        self.assertGreaterEqual(len(tlines), mod.MIN_LINES, "fixture: the twin is under MIN_LINES")
        self.assertLessEqual(len(clines), mod.CHILD_GROWTH * len(tlines),
                             "fixture: the child is over the growth bound for the twin")
        self.assertGreaterEqual(len(tlines & clines) / len(tlines), 0.8,
                                "fixture: the child holds too little of the twin")

    def test_own_pr_template_near_copy_is_not_reported_against_drifted_twin(self):
        # The parent keeps the template at a second path, drifted on line 3. The child keeps its own
        # template, so the drifted twin does not make that template a copy.
        write(self.parent, TWIN, DRIFTED_TWIN)
        for label, text in self.near_variants().items():
            self.assert_twin_would_be_reported(text)
            for mode in ("json", "text"):
                with self.subTest(variant=label, mode=mode):
                    self.assert_own_template_not_reported(text, mode)

    def test_own_pr_template_holding_a_whole_parent_file_beside_drifted_twin_is_reported(self):
        # The control for the drifted twin: the same parent, and a child template that holds the whole
        # template and a 100-line parent file. The rule excuses the template, never that parent file.
        mod = module_under_test()
        write(self.parent, TWIN, DRIFTED_TWIN)
        write(self.parent, LONG, LONG_TEXT)
        llines = mod.significant_lines(LONG_TEXT.encode())
        clines = mod.significant_lines((PR_TEMPLATE + LONG_TEXT).encode())
        self.assertGreaterEqual(len(LONG_TEXT.encode()), mod.MIN_BYTES, "fixture: the parent file is under MIN_BYTES")
        self.assertEqual(len(llines), 100, "fixture: the parent file is not 100 significant lines")
        self.assertFalse(llines & mod.significant_lines(PR_TEMPLATE.encode()),
                         "fixture: the parent file shares a line with the template")
        self.assertTrue(llines <= clines, "fixture: the child does not hold the whole parent file")
        self.assertLessEqual(len(clines), mod.CHILD_GROWTH * len(llines),
                             "fixture: the child is over the growth bound for the parent file")
        write(self.child, OWN_TEMPLATE, PR_TEMPLATE + LONG_TEXT)
        write(self.child, CONTROL, TEST)
        with self.subTest(mode="json"):
            proc = run(self.parent, self.child, "--json")
            self.assertIn(proc.returncode, (0, 1), proc.stderr)
            pairs = [(f["child"], f["parent"], f["kind"]) for f in json.loads(proc.stdout)["files"]]
            self.assertIn((CONTROL, "testing/skip-locally-fail-in-ci.test.mjs", "byte-equal"), pairs,
                          "control: the run did not report the other copy")
            self.assertIn((OWN_TEMPLATE, LONG, "near-equal"), pairs,
                          "the child's PR template holding a whole parent file is not reported as that copy")
        with self.subTest(mode="text"):
            proc = run(self.parent, self.child)
            self.assertIn(proc.returncode, (0, 1), proc.stderr)
            self.assertTrue(text_reports(proc.stdout, CONTROL), "control: the run did not report the other copy")
            self.assertTrue(any(line.startswith(f"file {OWN_TEMPLATE} copies {LONG} (near-equal, ")
                                for line in proc.stdout.splitlines()),
                            "the child's PR template holding a whole parent file is not reported as that copy")

    def test_reads_only(self):
        write(self.child, "harness/tests/copy.test.mjs", TEST)
        before = sorted(os.walk(self.child))
        run(self.parent, self.child)
        self.assertEqual(before, sorted(os.walk(self.child)))


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        shutil.rmtree(RUN_FOLDER, ignore_errors=True)
