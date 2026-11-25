#!/usr/bin/env python3
"""Fixture suite for lint/check_stable_readers.py. Run: python3 lint/test_check_stable_readers.py

The PR-only step "Stable readers accept this tree" runs the stable copy's readers against the PR head's tree. Each case builds
two throwaway git trees in its own folder under this run's temp root (decision test-temp-standard): a stable tree and a head
tree. Both hold this checkout's merge/, lint/ and hooks/, copied at run time and never committed here, plus a fixture config,
workflow and, where a case needs it, a records page. A case that needs an older reader patches its stable copy at one named
anchor; the patch asserts the anchor occurs once, so a changed anchor fails the fixture, not the case.

Exit contract the script keeps: 0 accept, 1 refuse (one finding, named by its reader and its key), 2 bad call. A refusal case
pins exit 1 exactly, so a script that is missing (exit 2) fails the case and never reads as a refusal. Each case with a
"control" method is a green check on the same fixture: it shows the fixture reaches the reader the step calls.
No case reads the network, the real config, or the clock.
"""
import atexit, importlib.util, json, os, re, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: the run folder's one home (lint/_test_temp.py)
from workflow_steps import job_block, step_blocks, step_key  # noqa: E402  the one step parser

SCRIPT = os.path.join(HERE, "check_stable_readers.py")
STEP = "Stable readers accept this tree"
RUN = os.path.realpath(_test_temp.run_folder())
atexit.register(shutil.rmtree, RUN, True)
os.environ.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                  GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")

CODE_DIRS = ("merge", "lint", "hooks", "actions")  # merge/ reads actions/ too (ci-alarm's events file), one level up
SKIP_NAMES = shutil.ignore_patterns("__pycache__", "test_*.py", "*.pyc")
# A records page needs a layout that lists the decisions folder (as the debt fixture's rolled-out repo does) and one record to list.
RECORDS_FIXTURE = {
    ".claude/layout-extras.json": '{"kinds": {}, "rolled-out": true}\n',
    "docs/decisions/fixture-record.md": "# Fixture record\n\n**Decision.** A fixture record for the stable readers case.\n\n**Status.** Ruled.\n",
}
MERGE = os.path.join("merge", "merge.py")
BASE_CONFIG = {
    "defaultBranch": "main",
    "merge": {"method": "merge", "requiredChecks": "protection", "deadlineMinutes": 80, "afterMerge": [],
              "deleteBranch": True, "readyChecks": ["STE lint"]},
}
WORKFLOW = ("name: checks\non: [pull_request]\njobs:\n  checks:\n    runs-on: ubuntu-latest\n"
            "    timeout-minutes: 30\n    steps:\n      - run: echo ok\n")
# The older reader's anchors, each one occurrence in this checkout's merge/merge.py (the patch asserts it).
OLD_LINT_SUITES = (MERGE, '"readyChecks", "lintSuites", "standingGrant"}', '"readyChecks", "standingGrant"}')
OLD_FIRST_PROOF = [
    (MERGE, 'PINNED_STRINGS = ("none", FIRST_PROOF)', 'PINNED_STRINGS = ("none",)'),
    (MERGE, 'rc in PINNED_STRINGS or isinstance(rc, list)', 'rc in ("none", FIRST_PROOF) or isinstance(rc, list)'),
]
OLD_READY_JOB_PREFIX = (MERGE, r're.compile(r"^([a-z][a-z0-9_-]*):(.+)$")', r're.compile(r"^([a-z][a-z0-9_-]*):(\w+)$")')


def put(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def git(cwd, *args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, (args, r.stderr)
    return r.stdout.strip()


def commit_all(root, message):
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)


def build_tree(root, config=None, patches=(), records=False):
    """A fixture tree at `root`: this checkout's code (each patch applied once at its anchor), the config and the workflow, committed.
    `records=True` adds the layout and one record, so the generator writes a records page."""
    for d in CODE_DIRS:
        shutil.copytree(os.path.join(REPO, d), os.path.join(root, d), ignore=SKIP_NAMES)
    for rel, old, new in patches:
        path = os.path.join(root, rel)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        assert text.count(old) == 1, f"fixture anchor is not unique in {rel}: {old!r}"
        put(path, text.replace(old, new))
    put(os.path.join(root, ".github", "stamp.json"), json.dumps(config or BASE_CONFIG, indent=1))
    put(os.path.join(root, ".github", "workflows", "checks.yml"), WORKFLOW)
    if records:
        for rel, text in RECORDS_FIXTURE.items():
            put(os.path.join(root, rel), text)
    git(root, "init", "-q")
    commit_all(root, "fixture")
    return root


def config_with(**merge_keys):
    """A copy of the fixture config with the given merge keys set."""
    config = json.loads(json.dumps(BASE_CONFIG))
    config["merge"].update(merge_keys)
    return config


def case_dir():
    return tempfile.mkdtemp(prefix="case-", dir=RUN)


def run_step(stable, head):
    """The step's script on the two trees: (exit code, its output)."""
    r = subprocess.run([sys.executable, SCRIPT, "--stable-tree", stable, "--head-tree", head],
                       capture_output=True, text=True, cwd=REPO)
    return r.returncode, r.stdout + r.stderr


def load_merge(tree, name):
    """The merge tool of one fixture tree, loaded under its own module name (the control reads its constants and its readers)."""
    spec = importlib.util.spec_from_file_location(name, os.path.join(tree, MERGE))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EqualTrees(unittest.TestCase):
    def test_1_equal_trees_exit_zero(self):
        d = case_dir()
        stable = build_tree(os.path.join(d, "stable"))
        head = build_tree(os.path.join(d, "head"))
        self.assertEqual(git(stable, "rev-parse", "HEAD^{tree}"), git(head, "rev-parse", "HEAD^{tree}"),
                         "fixture: the two trees are not equal")
        rc, out = run_step(stable, head)
        self.assertEqual(rc, 0, out)


class StableRefuses(unittest.TestCase):
    def test_2_unknown_merge_key_names_parse_config_and_key(self):
        d = case_dir()
        stable = build_tree(os.path.join(d, "stable"), patches=[OLD_LINT_SUITES])
        head = build_tree(os.path.join(d, "head"), config=config_with(lintSuites=["Cost line pins"]))
        rc, out = run_step(stable, head)
        self.assertEqual(rc, 1, out)
        self.assertIn("parse_config", out, out)
        self.assertIn("lintSuites", out, out)

    def test_2_control_stable_copy_raises_on_lintsuites(self):
        d = case_dir()
        stable = build_tree(os.path.join(d, "stable"), patches=[OLD_LINT_SUITES])
        head = build_tree(os.path.join(d, "head"))
        old = load_merge(stable, "stable_merge_control_2")
        with self.assertRaises(old.Stop) as caught:
            old.parse_config(head, config_with(lintSuites=["Cost line pins"]), "HEAD", "head", ".github/stamp.json", "")
        self.assertIn("lintSuites", str(caught.exception))

    def test_3_job_step_name_grouped_differently_names_ready_job_groups(self):
        d = case_dir()
        stable = build_tree(os.path.join(d, "stable"), patches=[OLD_READY_JOB_PREFIX])
        head = build_tree(os.path.join(d, "head"),
                          config=config_with(readyChecks=["STE lint", "checks-rest:Cost line pins"]))
        rc, out = run_step(stable, head)
        self.assertEqual(rc, 1, out)
        self.assertIn("ready_job_groups", out, out)

    def test_3_control_old_regex_groups_the_name_under_checks(self):
        d = case_dir()
        stable = build_tree(os.path.join(d, "stable"), patches=[OLD_READY_JOB_PREFIX])
        head = build_tree(os.path.join(d, "head"))
        names = ["STE lint", "checks-rest:Cost line pins"]
        old = load_merge(stable, "stable_merge_control_3").ready_job_groups(names)
        new = load_merge(head, "head_merge_control_3").ready_job_groups(names)
        self.assertIn("checks-rest:Cost line pins", [declared for declared, _ in old["checks"]])
        self.assertIn("checks-rest", new)
        self.assertNotEqual(old, new)

    def hand_edited_head(self, root):
        """A head tree whose records page is the generator's page with one line added by hand, committed."""
        head = build_tree(root, records=True)
        gen = subprocess.run([sys.executable, os.path.join("lint", "hook_catalog.py"), "--records-only", "--root", head],
                             capture_output=True, text=True, cwd=head)
        self.assertEqual(gen.returncode, 0, gen.stdout + gen.stderr)
        page = os.path.join(head, "docs", "records.md")
        self.assertTrue(os.path.isfile(page), "fixture: the generator wrote no records page")
        with open(page, encoding="utf-8") as f:
            text = f.read()
        put(page, text + "\nA line by hand: the generator never writes this.\n")
        commit_all(head, "records page edited by hand")
        return head

    def test_4_hand_edited_records_page_names_page_is_generated(self):
        d = case_dir()
        head = self.hand_edited_head(os.path.join(d, "head"))
        stable = build_tree(os.path.join(d, "stable"))
        rc, out = run_step(stable, head)
        self.assertEqual(rc, 1, out)
        self.assertIn("page_is_generated", out, out)

    def test_4_control_hand_edited_page_is_not_generated(self):
        d = case_dir()
        head = self.hand_edited_head(os.path.join(d, "head"))
        mod = load_merge(head, "head_merge_control_4")
        self.assertIs(mod.page_is_generated(head, git(head, "rev-parse", "HEAD")), False)


class SilentForm(unittest.TestCase):
    def test_5_silent_first_proof_reads_unpinned_names_pinned_required(self):
        d = case_dir()
        stable = build_tree(os.path.join(d, "stable"), patches=OLD_FIRST_PROOF)
        head = build_tree(os.path.join(d, "head"), config=config_with(requiredChecks="first-proof"))
        rc, out = run_step(stable, head)
        self.assertEqual(rc, 1, out)
        self.assertIn("pinned_required", out, out)

    def test_5_control_old_copy_leaves_first_proof_unpinned(self):
        d = case_dir()
        stable = build_tree(os.path.join(d, "stable"), patches=OLD_FIRST_PROOF)
        head = build_tree(os.path.join(d, "head"))
        self.assertNotIn("first-proof", load_merge(stable, "stable_merge_control_5").PINNED_STRINGS)
        self.assertIn("first-proof", load_merge(head, "head_merge_control_5").PINNED_STRINGS)


def needs_of(block):
    """The job names a job block lists under `needs:`, in block form or inline."""
    m = re.search(r"^    needs:\s*\n((?:      - .*\n?)+)", block or "", re.M)
    if m:
        return [line.split("- ", 1)[1].strip() for line in m.group(1).splitlines() if line.strip()]
    inline = re.search(r"^    needs:\s*\[([^\]]*)\]", block or "", re.M)
    return [n.strip() for n in inline.group(1).split(",") if n.strip()] if inline else []


class StepInWorkflow(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(REPO, ".github", "workflows", "checks.yml"), encoding="utf-8") as f:
            self.text = f.read()

    def test_6_step_runs_on_pull_request_and_feeds_the_rollup(self):
        holders = {}
        for job in re.findall(r"^  ([\w-]+):\s*$", self.text, re.M):
            for step in step_blocks(job_block(self.text, job)):
                if step_key(step, "name") == STEP:
                    holders[job] = step
        self.assertEqual(len(holders), 1, f"checks.yml has {len(holders)} job(s) with a step named {STEP!r}; want exactly one")
        ((job, step),) = holders.items()
        cond = step_key(step, "if") or ""
        self.assertIn("github.event_name == 'pull_request'", cond, f"step {STEP!r} in job {job!r} is not gated on pull_request: {cond!r}")
        self.assertNotIn("github.event_name == 'push'", cond, f"step {STEP!r} in job {job!r} also runs on push")
        self.assertIn(job, needs_of(job_block(self.text, "all-jobs-passed")),
                      f"job {job!r} holding {STEP!r} is not in all-jobs-passed's needs")


if __name__ == "__main__":
    unittest.main()
