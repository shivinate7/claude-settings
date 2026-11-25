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
READY = ["STE lint", "checks-rest:Cost line pins"]  # a job:step name the older regex groups under "checks"
CI_REF_VARS = ("GITHUB_BASE_REF", "GITHUB_REF")  # read by hook_catalog.py --check, so no verdict may depend on the caller's shell
PAGE = "docs/records.md"  # the records page, in git's forward slashes
HAND_LINE = "\nA line by hand: the generator never writes this.\n"
BROKEN_MERGE = (MERGE, "#!/usr/bin/env python3",
                '#!/usr/bin/env python3\nraise RuntimeError("fixture: this merge tool does not load")')


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


def child_env():
    """The caller's environment minus the runner's ref variables, and no bytecode written into a fixture tree."""
    env = {k: v for k, v in os.environ.items() if k not in CI_REF_VARS}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def run_step(stable, head, base_ref=None):
    """The step's script on the two trees, judging the records page against `base_ref` when given: (exit code, its output)."""
    cmd = [sys.executable, SCRIPT, "--stable-tree", stable, "--head-tree", head]
    if base_ref:
        cmd += ["--base-ref", base_ref]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO, env=child_env())
    return r.returncode, r.stdout + r.stderr


def load_merge(tree, name):
    """The merge tool of one fixture tree, loaded under its own module name (the control reads its constants and its readers)."""
    spec = importlib.util.spec_from_file_location(name, os.path.join(tree, MERGE))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def generated_head(root):
    """A head tree whose records page is the generator's own page, committed as a base for a pull request."""
    head = build_tree(root, records=True)
    gen = subprocess.run([sys.executable, os.path.join("lint", "hook_catalog.py"), "--records-only", "--root", head],
                         capture_output=True, text=True, cwd=head, env=child_env())
    assert gen.returncode == 0, gen.stdout + gen.stderr
    assert os.path.isfile(os.path.join(head, *PAGE.split("/"))), "fixture: the generator wrote no records page"
    commit_all(head, "records page from the generator")
    return head


def commit_pr(root, edits):
    """Commit `edits` ({path: text}, git's forward slashes) on top of the tree at `root` as one pull request commit. -> the base sha."""
    base = git(root, "rev-parse", "HEAD")
    for rel, text in edits.items():
        put(os.path.join(root, *rel.split("/")), text)
    commit_all(root, "pull request")
    return base


def changed_paths(root, base):
    """The paths the tree at `root` changes against `base`, sorted."""
    return sorted(git(root, "diff", "--name-only", base, "HEAD").split())


def reader_edit(root):
    """The edits of a pull request that changes only a reader: one comment line added to merge/merge.py."""
    with open(os.path.join(root, "merge", "merge.py"), encoding="utf-8") as f:
        return {"merge/merge.py": f.read() + "# a reader-only pull request\n"}


def page_edit(root):
    """The edits of a pull request that adds one line to the records page by hand."""
    with open(os.path.join(root, *PAGE.split("/")), encoding="utf-8") as f:
        return {PAGE: f.read() + HAND_LINE}


def hand_edited_head(root):
    """A head tree whose records page is the generator's page with one line added by hand, as a pull request's commit."""
    head = generated_head(root)
    commit_pr(head, page_edit(head))
    return head


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

    def test_4_hand_edited_records_page_names_page_is_generated(self):
        d = case_dir()
        head = hand_edited_head(os.path.join(d, "head"))
        stable = build_tree(os.path.join(d, "stable"))
        rc, out = run_step(stable, head)
        self.assertEqual(rc, 1, out)
        self.assertIn("page_is_generated", out, out)

    def test_4_control_hand_edited_page_is_not_generated(self):
        d = case_dir()
        head = hand_edited_head(os.path.join(d, "head"))
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


class UnloadableHead(unittest.TestCase):
    def test_7_head_merge_tool_that_does_not_load_is_unknown_naming_merge_py(self):
        d = case_dir()
        stable = build_tree(os.path.join(d, "stable"))
        head = build_tree(os.path.join(d, "head"), patches=[BROKEN_MERGE])
        rc, out = run_step(stable, head)
        self.assertNotEqual(rc, 0, out)
        self.assertTrue(any("merge.py" in line and "unknown" in line for line in out.splitlines()), out)

    def test_7_control_head_merge_tool_raises_when_loaded(self):
        d = case_dir()
        head = build_tree(os.path.join(d, "head"), patches=[BROKEN_MERGE])
        with self.assertRaises(Exception):
            load_merge(head, "head_merge_control_7")


class ReaderOnlyPullRequest(unittest.TestCase):
    def test_8_reader_only_pull_request_waives_difference_on_unchanged_data(self):
        d = case_dir()
        stable = build_tree(os.path.join(d, "stable"), patches=[OLD_READY_JOB_PREFIX])
        head = build_tree(os.path.join(d, "head"), config=config_with(readyChecks=READY))
        base = commit_pr(head, reader_edit(head))
        self.assertEqual(changed_paths(head, base), ["merge/merge.py"], "fixture: the pull request changes more than its reader")
        rc, out = run_step(stable, head, base)
        self.assertEqual(rc, 0, out)
        self.assertEqual(sum("merge.readyChecks" in line for line in out.splitlines()), 1, out)

    def test_8_control_changed_ready_checks_is_still_refused(self):
        d = case_dir()
        stable = build_tree(os.path.join(d, "stable"), patches=[OLD_READY_JOB_PREFIX])
        head = build_tree(os.path.join(d, "head"), config=config_with(readyChecks=["STE lint"]))
        base = commit_pr(head, {".github/stamp.json": json.dumps(config_with(readyChecks=READY), indent=1)})
        self.assertEqual(changed_paths(head, base), [".github/stamp.json"], "fixture: the pull request changes more than the config")
        rc, out = run_step(stable, head, base)
        self.assertEqual(rc, 1, out)
        self.assertIn("ready_job_groups", out, out)

    def test_8_control_data_file_change_gets_no_waiver(self):
        d = case_dir()
        stable = build_tree(os.path.join(d, "stable"), patches=[OLD_READY_JOB_PREFIX])
        head = build_tree(os.path.join(d, "head"), config=config_with(readyChecks=READY))
        base = commit_pr(head, {".github/stamp.json": json.dumps(config_with(readyChecks=READY, deadlineMinutes=90), indent=1)})
        self.assertEqual(changed_paths(head, base), [".github/stamp.json"], "fixture: the pull request changes more than the config")
        rc, out = run_step(stable, head, base)
        self.assertEqual(rc, 1, out)
        self.assertIn("ready_job_groups", out, out)


class RecordsPageUnderBase(unittest.TestCase):
    def test_9_records_page_the_base_already_holds_is_not_judged(self):
        d = case_dir()
        stable = build_tree(os.path.join(d, "stable"))
        head = hand_edited_head(os.path.join(d, "head"))
        base = git(head, "rev-parse", "HEAD")
        commit_pr(head, reader_edit(head))
        self.assertEqual(changed_paths(head, base), ["merge/merge.py"], "fixture: the pull request changes the records page")
        rc, out = run_step(stable, head, base)
        self.assertIn(rc, (0, 1), out)
        self.assertIn("stable readers", out, out)
        self.assertNotIn("page_is_generated", out, out)

    def test_9_control_records_page_without_base_ref_is_judged(self):
        d = case_dir()
        stable = build_tree(os.path.join(d, "stable"))
        head = hand_edited_head(os.path.join(d, "head"))
        rc, out = run_step(stable, head)
        self.assertEqual(rc, 1, out)
        self.assertIn("page_is_generated", out, out)

    def test_9_records_page_the_pull_request_changes_is_judged(self):
        d = case_dir()
        stable = build_tree(os.path.join(d, "stable"))
        head = generated_head(os.path.join(d, "head"))
        base = git(head, "rev-parse", "HEAD")
        commit_pr(head, page_edit(head))
        self.assertEqual(changed_paths(head, base), [PAGE], "fixture: the pull request does not change the records page")
        rc, out = run_step(stable, head, base)
        self.assertEqual(rc, 1, out)
        self.assertIn("page_is_generated", out, out)


if __name__ == "__main__":
    unittest.main()
