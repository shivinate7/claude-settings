#!/usr/bin/env python3
"""CLI tests for the scope detector (.github/scripts/ci-scope.sh) and the mod test runner (.github/scripts/mod-tests.sh).

Each scope case builds a scratch git repo, commits a base, commits the changed paths, runs the script
with EVENT and BASE_SHA set, and reads the name=value lines it wrote to $GITHUB_OUTPUT.
CI_SCOPE overrides the script path (for a successor). Needs bash on PATH. The mod runner cases build a
scratch tree with a copy of mod-tests.sh and run it there; they need node on PATH.

Output names pinned (the `scope` job re-exports them as job outputs):
  JOB_FLAGS  one per check job except the lint job `checks`: checks_windows, checks_windows_merge,
             checks_windows_rest, checks_macos, shell_macos, pointer_windows
  STEP_FLAGS code, guard, sweep, mods, shoot (the suite flags; shoot turns on the whole checks-shoot job)
  GUARD_SPLIT guard_windows_full, guard_windows_slice (the Windows guard split; GuardWindowsSplit pins them)

Run with:  python3 lint/test_ci_scope.py -v
"""
import ast
import os
import posixpath
import shutil
import subprocess
import tempfile
import unittest

import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  copies the script under test into a scratch tree; rm_tree removes the run folder
import layout  # noqa: E402  lint/layout.py, the reader the guard calls for the decisions folder (it reads files only when called)
SCRIPT =os.environ.get("CI_SCOPE") or os.path.join(HERE, "..", ".github", "scripts", "ci-scope.sh")
REPO = os.path.abspath(os.path.join(HERE, ".."))
JOB_FLAGS = ["checks_windows", "checks_windows_merge", "checks_windows_rest", "checks_macos", "shell_macos", "pointer_windows"]
STEP_FLAGS = ["code", "guard", "sweep", "mods", "shoot"]
# Flags derived from others, kept out of JOB_FLAGS so the exact-set cases below stay about the base flags:
# checks_windows_sweep is set with checks_windows_rest. checks_guard is set when both `code` and `guard` are set, or
# directly by the arm for actions/playwright-setup and .github/shoot (the paths checks-guard installs from).
DERIVED_FLAGS = ["checks_windows_sweep", "checks_guard"]
ALL = JOB_FLAGS + STEP_FLAGS
# The Windows guard split. Kept out of ALL and DERIVED_FLAGS: those lists are checked in every case, and the cases that
# predate the split would then fail on the old script for a missing output. GuardWindowsSplit pins both names.
GUARD_FULL = "guard_windows_full"
GUARD_SLICE = "guard_windows_slice"
GUARD_SPLIT = (GUARD_FULL, GUARD_SLICE)
BASH = shutil.which("bash")


def pre_split(got):
    """The outputs the script wrote before the guard split: every output but GUARD_SPLIT."""
    return {n: v for n, v in got.items() if n not in GUARD_SPLIT}


def guard_assign(name):
    """The value node of hooks/guard.py's module-level assignment to `name`, read from the file's syntax tree, so guard.py
    is not imported (its load starts the guard's own reads). Every case that reads a guard constant goes through here."""
    with open(os.path.join(HERE, "..", "hooks", "guard.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return node.value
    raise AssertionError(f"hooks/guard.py has no module-level {name}")


def family_files():
    """hooks/<module>.py for each module in hooks/guard.py's _FAMILY_MODULES."""
    return [f"hooks/{m}.py" for m in ast.literal_eval(guard_assign("_FAMILY_MODULES"))]


def role_table_path():
    """The decision record the guard reads for the role table (hooks/guard.py role_model_table): the decisions folder from
    lint/layout.json, read by the reader the guard calls, then ROLE_TABLE_FILE from hooks/guard.py. Both come from the code."""
    folder = layout.layout()["kinds"]["decisions"]["path"].strip("/")
    return "/".join(folder.split("/") + [ast.literal_eval(guard_assign("ROLE_TABLE_FILE"))])


# The files the guard suite loads, derived from the code of GUARD_SEEDS, not listed by hand. A file is in the closure when
# a file in it imports it, or loads it by a path (_refs reads each file's syntax tree):
#   import x, from x import y, importlib.import_module("x"): x is the basename of a repo .py file;
#   os.path.join whose literal segments have a `..`, or whose run-time root is the file's own folder (__file__, _HERE):
#     the file of that name in that folder;
#   os.path.join of literal segments with no run-time root: a repo path, from the repo root;
#   a spec_from_file_location or SourceFileLoader path: its Name read through to the os.path.join assigned to it.
# Not followed: a join with a run-time root and literal segments, and a join with a spread folder (`*folder.split("/")`, how a
# layout-built path is joined). In a product module each is named in LOAD_EXCEPTIONS; in a test module it is a fixture path
# inside a temp folder, and is not named. A loader path with no literal repo file is named.
GUARD_SEEDS = ("hooks/guard.py", "hooks/test_guard.py")
# Each load guard_closure finds but does not follow, as "file:line": why. A line that moves makes its entry stale.
LOAD_EXCEPTIONS = {
    "hooks/decision_watch.py:88": "GUARD_UNDER_TEST, a test override of guard.py's path (guard.py is in the closure by import)",
    "hooks/decision_watch.py:327": "a path git status reports as changed, joined under the checkout: whichever file changed, not a fixed one",
    "hooks/feedback_guard.py:328": "a home folder the layout (or the repo's extras) names, tested for existence: a folder, not a fixed file",
    "hooks/feedback_guard.py:948": "each task kind's home folder from the layout, read for its todo and notes text: the folders the layout names",
    "hooks/git_reads.py:294": "LAYOUT_EXTRAS, .claude/layout-extras.json: the repo's own extras file, read for its roadmap object",
    "hooks/guard.py:2673": "role_model_table: the decisions folder from lint/layout.json, then ROLE_TABLE_FILE, the role table record; GuardWindowsSplit's role-table case covers its scope",
    "hooks/guard_merge.py:169": "the merge tool at a clone root, MERGE_TOOL_REL (guard_merge.py:108): merge/merge.py is in the closure",
    "hooks/guard_merge.py:239": "a stamp read from a clone root found by walking up: a fixture root in the suite, the checkout in a real run",
    "hooks/override.py:173": "the override state file of a session id, under the Claude config folder: the installer's state, not a repo file",
    "hooks/precompact_handoff.py:152": "the installed prompt under config_dir(), the installer's copy, not the repo's file",
    "hooks/test_guard.py:3362": "a sibling of GUARD, hooks/ by default: git_reads.py is in the closure by import",
    "hooks/test_guard.py:4622": "a sibling of GUARD: guard_rm_var.py is in the closure by import",
    "hooks/test_guard.py:14122": "a sibling of GUARD: own_session.py is in the closure by import",
    "hooks/test_guard.py:19743": "GUARD itself: guard.py, or the GUARD_UNDER_TEST copy, which is in the closure by import",
    "hooks/test_guard.py:25627": "READ_CHECK: reread_check.py by default, which is in the closure by import",
    "hooks/test_guard.py:27735": "a sibling of GUARD: shared_names.py is in the closure by import",
    "lint/check_silent_undo.py:583": "gen.RECORDS_PAGE (hook_catalog's records page), in the head's worktree: the page the check compares",
    "lint/check_silent_undo.py:586": "a checkout's hook_catalog.py, the oracle of the silent-undo check: in the closure by merge.py's import",
    "lint/check_skill_model_rows.py:23": "the decisions folder from the layout, then agent-model-cap.md: the same role table record hooks/guard.py:2673 reads",
    "lint/hook_catalog.py:90": "read(rel): a path from the catalog's own tables (the hooks and pages it checks), read by path",
    "lint/hook_catalog.py:97": "has_file(rel): the same catalog paths as read(), tested for existence",
    "lint/hook_catalog.py:695": "listed_folders(): a folder the layout lists for a kind, read for its files",
    "lint/hook_catalog.py:790": "the catalog's generated pages, written at paths from its own table: the writer of the pages it then checks",
    "lint/layout.py:65": "_extras: the repo's own extras file, at the path the layout's extras key names: a repo file, not this one",
    "lint/layout.py:507": "item['preflight']: a path a repo's own preflight item names, tested for existence: a repo file",
    "lint/layout.py:531": "mockup_homes: the repo's design folder from the layout, returned as a path; no file is read here",
    "lint/report_guard.py:1142": "the decisions folder from the layout, then each id: the record files, tested for existence",
    "lint/rule_audit.py:92": "ROOT, the repo root by definition, a fixture root in the suite: lint/rule_mechanisms.json is not in the closure",
    "lint/rule_audit.py:93": "ROOT: .github/workflows/checks.yml, already a fail-safe path in ci-scope.sh",
    "lint/rule_audit.py:405": "ROOT: hooks/config_watch.py is not in the closure",
    "lint/stale_cites.py:320": "PY_FACTS: skills/plain-english-map/scripts/lib/py-facts.py is in the closure by a `..` load",
    "merge/merge.py:1554": "RECORDS_PAGE in the merge's own worktree: the records page the merge proves fresh",
    "merge/merge.py:1773": "the checkout's own workflow, .github/workflows/checks.yml, already a fail-safe path in ci-scope.sh",
    "merge/merge.py:1785": "read(path) in hit_suites: a module a checks suite imports, read from the checkout: whichever modules those suites import",
    "merge/merge.py:1803": "the suite a checks.yml run line names, read from the checkout: whichever suite files the workflow runs",
    "merge/merge.py:1876": "CI_SCOPE, the scope script, tested for existence in the merge's worktree: already a fail-safe path in ci-scope.sh",
    "merge/merge.py:3375": "IDLE_BUILD: skills/roadmap/build.py is in the closure by a `..` load",
    "skills/waiting-page/export_page.py:429": "an export label's target under the out folder: a write, not a load",
    "skills/waiting-page/export_page.py:444": "a stale export label removed under the out folder: a write, not a load",
    "skills/waiting-page/export_page.py:472": "entry['export'] under the worktree: the export file the page entry names",
    "skills/waiting-page/stale_pages.py:259": "the user's ~/.claude/CLAUDE.md, not this repo's .claude/CLAUDE.md",
}
_CLOSURE = {}


def _repo_files():
    """Every file under the repo, as '/' paths. Skips .git, build folders, and .claude/worktrees (each worktree copies the repo)."""
    out = []
    worktrees = os.path.join(REPO, ".claude", "worktrees")
    for dirpath, dirnames, filenames in os.walk(REPO):
        dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules", "__pycache__")
                       and os.path.join(dirpath, d) != worktrees]
        out += [os.path.relpath(os.path.join(dirpath, n), REPO).replace(os.sep, "/") for n in filenames]
    return out


def _callee(call):
    """The dotted name a call is made through, such as `importlib.import_module`; '' when it is not a plain name."""
    parts, f = [], call.func
    while isinstance(f, ast.Attribute):
        parts.append(f.attr)
        f = f.value
    if not isinstance(f, ast.Name):
        return ""
    return ".".join([f.id] + parts[::-1])


def _join_segments(call):
    """The literal segments of an os.path.join call after its last run-time argument, split on '/', and whether a
    run-time argument came before them (a run-time root)."""
    segs, lead = [], False
    for a in call.args:
        if isinstance(a, ast.Constant) and isinstance(a.value, str):
            segs.append(a.value)
        else:
            segs, lead = [], True
    return [p for s in segs for p in s.split("/") if p], lead


def _loader_joins(arg, call, tree, parents):
    """The os.path.join calls a loader's path argument can hold: the argument itself, or the joins assigned to its Name
    in the enclosing function (the module when there is none)."""
    if isinstance(arg, ast.Call) and _callee(arg) == "os.path.join":
        return [arg]
    if not isinstance(arg, ast.Name):
        return []
    scope, node = tree, call
    while node in parents:
        node = parents[node]
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scope = node
            break
    return [n.value for n in ast.walk(scope) if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call)
            and _callee(n.value) == "os.path.join" and any(isinstance(t, ast.Name) and t.id == arg.id for t in n.targets)]


def _uses_file(node):
    return any(isinstance(n, ast.Name) and n.id == "__file__" for n in ast.walk(node))


def _join_file(f, call, tracked, own_names):
    """-> (path, kind) for an os.path.join: kind 'dir' when the path is read from the loading file's folder (a `..`
    segment, or a run-time root that is that folder: an expression built from __file__, or a module-level Name in
    own_names bound to one, such as guard.py's _HERE), 'root' when it is a repo path from the repo root with no run-time
    root, 'run-time' when a run-time root comes before a repo path (a checkout or a fixture), or (None, None)."""
    segs, lead = _join_segments(call)
    if not segs:
        return None, None
    first = call.args[0]
    own = _uses_file(first) or (isinstance(first, ast.Name) and first.id in own_names)
    if ".." in segs or (lead and own):
        c = posixpath.normpath(posixpath.join(posixpath.dirname(f), *segs))
        if c in tracked:
            return c, "dir"
    if len(segs) >= 2:
        c = posixpath.normpath("/".join(segs))
        if c in tracked:
            return c, "run-time" if lead else "root"
    return None, None


def _refs(f, tree, tracked):
    """What one repo file loads, from its syntax tree: (module names it imports, repo files it loads by path, loader
    targets, loads it does not follow as (line, what))."""
    parents = {c: n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
    own_names = {t.id for st in tree.body if isinstance(st, ast.Assign) and _uses_file(st.value)
                 for t in st.targets if isinstance(t, ast.Name)}
    test = posixpath.basename(f).startswith("test_")
    modules, paths, loads, unfollowed = set(), set(), set(), []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            name = _callee(node)
            if name == "importlib.import_module":
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    modules.add(node.args[0].value.split(".")[0])
                else:
                    unfollowed.append((node.lineno, "importlib.import_module of a name built at run time"))
            elif name == "os.path.join":
                c, kind = _join_file(f, node, tracked, own_names)
                if kind == "run-time":
                    if not test:  # a test's join under a run-time root is a fixture path, not a repo load
                        unfollowed.append((node.lineno, f"os.path.join with a run-time root, then {c}"))
                elif c:
                    paths.add(c)
                elif not test and any(isinstance(a, ast.Starred) for a in node.args):
                    # A spread folder (`*folder.split("/")`) is how a layout-built path is joined. Its file is not known here.
                    unfollowed.append((node.lineno, "os.path.join of a spread folder: a layout-built path the closure does not follow"))
            elif name.endswith("spec_from_file_location") or name.endswith("SourceFileLoader"):
                arg = node.args[1] if len(node.args) > 1 else None
                hits, named = [], False
                for j in _loader_joins(arg, node, tree, parents):
                    c, kind = _join_file(f, j, tracked, own_names)
                    if kind == "run-time":
                        named = True
                        unfollowed.append((node.lineno, f"a loader path with a run-time root, then {c}"))
                    elif c:
                        hits.append(c)
                loads.update(hits)
                if not hits and not named:
                    unfollowed.append((node.lineno, "a loader path with no literal repo file"))
    return modules, paths, loads, unfollowed


def guard_closure():
    """-> (files, unfollowed): the repo files the guard suite loads, sorted, and the loads not followed, as
    (file, line, what). Read from the code of GUARD_SEEDS (see above), once per run."""
    if not _CLOSURE:
        tracked = set(_repo_files())
        by_name = {}
        for p in tracked:
            if p.endswith(".py"):
                by_name.setdefault(posixpath.basename(p)[:-3], []).append(p)
        files, unfollowed, parsed = set(), [], set()
        todo = [(s, True) for s in GUARD_SEEDS]
        while todo:
            f, is_python = todo.pop()
            if f not in tracked:
                raise AssertionError(f"{f} is a guard seed or a load target, and the repo does not have it")
            files.add(f)
            if f in parsed or not is_python:
                continue
            parsed.add(f)
            with open(os.path.join(REPO, f), encoding="utf-8") as h:
                tree = ast.parse(h.read(), filename=f)
            modules, paths, loads, here = _refs(f, tree, tracked)
            todo += [(c, True) for m in modules for c in by_name.get(m, [])]
            todo += [(c, c.endswith(".py")) for c in paths]
            todo += [(c, True) for c in loads]
            unfollowed += [(f, line, what) for line, what in here]
        _CLOSURE.update(files=sorted(files), unfollowed=sorted(unfollowed))
    return _CLOSURE["files"], _CLOSURE["unfollowed"]


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def run(paths, event="pull_request", base="auto", existing=(), landed=None, head_ref=""):
    """-> {name: 'true'|'false'} the script wrote. `paths` are committed on top of one base commit. `head_ref` is HEAD_REF,
    empty when not given, so no HEAD_REF of the caller's environment reaches the script."""
    with tempfile.TemporaryDirectory() as d:
        git(d, "init", "-q")
        git(d, "config", "user.email", "t@t")
        git(d, "config", "user.name", "t")
        git(d, "config", "commit.gpgsign", "false")
        # No background gc or maintenance after a commit: it can write into .git while the temp dir is removed.
        git(d, "config", "gc.auto", "0")
        git(d, "config", "maintenance.auto", "false")
        open(os.path.join(d, "seed.txt"), "w").write("seed\n")
        # The base holds landed-dirs.txt: the repo's own, or `landed` (a list of dir names) in its place.
        with open(os.path.join(HERE, "..", "landed-dirs.txt")) as f:
            real = f.read()
        open(os.path.join(d, "landed-dirs.txt"), "w").write(real if landed is None else chr(10).join(landed) + chr(10))
        for p in existing:  # in the base commit, so the head commit modifies them
            os.makedirs(os.path.dirname(os.path.join(d, p)), exist_ok=True)
            open(os.path.join(d, p), "w").write("old\n")
        git(d, "add", "-A")
        git(d, "commit", "-qm", "base")
        sha = git(d, "rev-parse", "HEAD")
        for p in paths:
            full = os.path.join(d, p)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            open(full, "w").write("changed\n")
        git(d, "add", "-A")
        git(d, "commit", "-qm", "head", "--allow-empty")
        out = os.path.join(d, "..", f"out-{os.getpid()}.txt")
        env = dict(os.environ, EVENT=event, GITHUB_OUTPUT=out, HEAD_REF=head_ref,
                   BASE_SHA=sha if base == "auto" else base)
        r = subprocess.run([BASH, os.path.abspath(SCRIPT)], cwd=d, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        lines = open(out).read().split()
        os.remove(out)
        return dict(l.split("=", 1) for l in lines)


@unittest.skipUnless(BASH, "bash not on PATH")
class DerivedFlags(unittest.TestCase):
    PATHS = [["hooks/guard.py"], ["hooks/test_guard.py"], ["janitor/sweep.py"], ["hooks/test_config_watch.py"], ["merge/merge.py"],
             ["README.md"], ["skills/ci-hygiene/SKILL.md"], ["bin/ios-ship"], ["lint/layout.json"], ["actions/stamp/stamp.mjs"],
             ["install.ps1"], ["unlisted/new-file.txt"], ["bin/verdict"], ["settings.json"], ["bin/shoot"]]

    def check(self, got):
        for n in DERIVED_FLAGS:
            self.assertIn(n, got, f"output {n} missing: {got}")
        self.assertEqual(got["checks_windows_sweep"], got["checks_windows_rest"], got)
        # PATHS touch neither direct arm, so the both-flags rule is the whole rule for them.
        both = got["code"] == "true" and got["guard"] == "true"
        self.assertEqual(got["checks_guard"], "true" if both else "false", got)

    def test_sweep_flag_follows_rest_and_guard_flag_needs_code_and_guard(self):
        seen = set()
        for paths in self.PATHS:
            for event in ("pull_request", "push"):
                with self.subTest(paths=paths, event=event):
                    got = run(paths, event=event)
                    self.check(got)
                    seen.add((got["checks_windows_rest"], got["checks_guard"]))
        # The sample reaches both ends: everything on, and a docs-only change with everything off.
        self.assertTrue({("true", "true"), ("false", "false")} <= seen, seen)

    def test_unreadable_diff_turns_the_derived_flags_on(self):
        self.check(run(["hooks/guard.py"], base="0" * 40))
        self.assertEqual(run(["hooks/guard.py"], base="0" * 40)["checks_guard"], "true")


@unittest.skipUnless(BASH, "bash not on PATH")
class Scope(unittest.TestCase):
    def assertFlags(self, got, want_true=(), want_false=()):
        for n in ALL:
            self.assertIn(n, got, f"output {n} missing: {got}")
        for n in want_true:
            self.assertEqual(got[n], "true", f"{n}: {got}")
        for n in want_false:
            self.assertEqual(got[n], "false", f"{n}: {got}")

    def test_docs_only_pr_turns_every_job_off(self):
        got = run(["README.md", "decisions/some-record.md"])
        self.assertFlags(got, want_false=ALL)

    def test_merge_change_turns_the_merge_job_on(self):
        got = run(["merge/merge.py"])
        self.assertFlags(got, want_true=["checks_windows_merge", "code"])

    def test_guard_change_turns_the_guard_suites_on(self):
        got = run(["hooks/guard.py"])
        self.assertFlags(got, want_true=["checks_windows", "checks_macos", "guard", "sweep", "code"])
        # The selector's test
        # and mutation test also turn `guard` on. Named failure: the guard suite runs in no job.
        for p in ("hooks/test_guard.py", "hooks/mutate_guard.py"):
            with self.subTest(path=p):
                self.assertFlags(run([p]), want_true=["guard"])

    def test_a_merge_change_leaves_a_job_that_never_runs_merge_suites_off(self):
        got = run(["merge/merge.py"])
        self.assertFlags(got, want_false=["pointer_windows", "shell_macos"])

    def test_workflow_or_scope_script_change_runs_everything(self):
        for p in (".github/workflows/checks.yml", ".github/scripts/ci-scope.sh"):
            self.assertFlags(run([p]), want_true=ALL)

    def test_a_test_run_signing_helper_change_runs_everything(self):
        # Every suite loads the helper, so a change to any of its three twins runs every job.
        for p in ("lint/_test_git.py", "lint/_test_git.sh", "lint/_test_git.mjs"):
            with self.subTest(path=p):
                self.assertFlags(run([p]), want_true=ALL + DERIVED_FLAGS)

    def test_unmapped_path_runs_everything(self):
        self.assertFlags(run(["zz-unmapped/blob.bin"]), want_true=ALL)

    def test_unreadable_diff_runs_everything(self):
        bogus = "f" * 40
        self.assertFlags(run(["README.md"], base=bogus), want_true=ALL)
        self.assertFlags(run(["README.md"], base=""), want_true=ALL)

    def test_push_schedule_and_dispatch_run_everything_even_for_docs(self):
        for ev in ("push", "schedule", "workflow_dispatch"):
            self.assertFlags(run(["README.md"], event=ev), want_true=ALL)

    # Map gaps found in review: each path is read by a suite in another job.
    def test_merge_tool_change_turns_on_the_suites_that_load_it(self):
        self.assertFlags(run(["merge/merge.py"]), want_true=["checks_windows", "checks_macos", "guard", "checks_windows_merge"])

    def test_layout_change_turns_on_the_guard_and_merge_suites(self):
        for path in ("lint/layout.json", "lint/layout.py"):
            self.assertFlags(run([path]), want_true=["checks_windows", "checks_macos", "guard", "code", "checks_windows_merge"])

    def test_janitor_launcher_change_turns_on_the_install_suite(self):
        # `guard` too: the janitor launcher turns the guard suite on.
        self.assertFlags(run(["bin/claude-janitor"]), want_true=["checks_windows", "shell_macos", "guard"])

    def test_windows_install_test_change_turns_on_the_windows_install_job(self):
        # The file is in the base, so an edit to it is no new file in a landed dir; the job that runs it must start.
        self.assertFlags(run(["hooks/test_install_windows.sh"], existing=["hooks/test_install_windows.sh"]),
                         want_true=["checks_windows", "code"])

    def test_silent_undo_checker_change_turns_on_the_merge_job(self):
        self.assertFlags(run(["lint/check_silent_undo.py"]), want_true=["checks_windows_merge"])

    def test_session_start_change_turns_on_the_unknown_read_contract_job(self):
        self.assertFlags(run(["hooks/session_start.sh"]), want_true=["checks_windows_rest"])

    def test_a_new_file_in_a_landed_dir_turns_on_the_install_suite(self):
        for p in ("agents/new.md", "skills/new/SKILL.md", "output-styles/new.md", "lint/new.py"):
            self.assertFlags(run([p]), want_true=["checks_windows", "shell_macos"])
        # Named failure: review
        # finding on #305. The guard suite reads this path; if `guard` stays off, cut F runs it in no job.
        self.assertFlags(run(["lint/zz_new.py"]), want_true=["guard"])

    def test_a_modified_md_under_skills_turns_on_nothing(self):
        self.assertFlags(run(["skills/old/SKILL.md"], existing=["skills/old/SKILL.md"]), want_false=ALL)

    def test_a_new_file_in_hooks_or_janitor_turns_on_the_install_suite(self):
        for p in ("hooks/new.py", "janitor/new.py"):
            self.assertFlags(run([p]), want_true=["checks_windows", "shell_macos"])

    def test_the_landed_dirs_come_from_landed_dirs_txt(self):
        # A made-up dir in the scratch repo's landed-dirs.txt: the script reads the file, it does not copy the list.
        self.assertFlags(run(["zz-made-up/new.md"], landed=["zz-made-up"]), want_true=["checks_windows", "shell_macos"])

    def test_an_empty_or_comment_only_landed_list_turns_everything_on(self):
        for landed in ([], ["# only a comment", ""]):
            self.assertFlags(run(["docs/new.md"], landed=landed), want_true=ALL)

    def test_a_trailing_slash_in_landed_dirs_is_read_as_the_dir(self):
        self.assertFlags(run(["zz-made-up/new.md"], landed=["zz-made-up/"]), want_true=["checks_windows", "shell_macos"])

    # Cut F: checks-windows-guard and checks-mutate-guard skip on the `guard` flag. The slice selector
    # (GUARD_TESTS) is read from hooks/test_guard.py, so an edit to that file must turn `guard` on,
    # or a pull request that changes the slice would run no guard job at all.
    # Control: a docs-only path must keep `guard` off, or the new rules over-trigger (false red).
    def test_a_docs_only_path_keeps_the_guard_flag_off(self):
        for p in ("README.md", "decisions/some-record.md"):
            self.assertFlags(run([p]), want_false=["guard"])

    # lint/guard_log_report.py imports hooks/guard_core.py at load, and decision_watch
    # reads guard.log through it at run time. So a change to it must select the same jobs as
    # lint/_transcript.py, the other module the decision watch loads (the rules at its line 36, 51).
    def test_guard_log_reader_change_selects_the_jobs_of_the_transcript_reader(self):
        reader = self.true_set(run(["lint/guard_log_report.py"]))
        self.assertEqual(reader, self.true_set(run(["lint/_transcript.py"])))
        self.assertTrue({"checks_windows_rest", "checks_macos", "code", "guard"} <= reader, reader)

    # Guard family: hooks/guard_<anything>.py is split out of hooks/guard.py. Each sibling must set
    # exactly the flags guard.py sets, as a new file and as an edit. Today the generic hooks/* rule
    # gives a new sibling no sweep flag, and an edited one no Windows or shell job.
    # The siblings compare the outputs that predate the guard split. Their split flags are not decided here: guard_core.py is
    # shared code, not a rule family (hooks/guard.py _FAMILY_MODULES), and guard_rules.py is not a file yet. GuardWindowsSplit
    # pins the split flags of the family modules.
    GUARD_SIBLINGS = ["hooks/guard_core.py", "hooks/guard_merge.py", "hooks/guard_rules.py"]

    def true_set(self, got):
        return {n for n in ALL if got[n] == "true"}

    def test_guard_sibling_new_file_sets_the_same_flags_as_guard_py(self):
        got = run(["hooks/guard.py"])
        self.assertFlags(got, want_true=["checks_windows", "checks_windows_rest", "checks_macos", "code", "guard", "sweep"],
                         want_false=["checks_windows_merge", "pointer_windows"])
        want = pre_split(got)
        for p in self.GUARD_SIBLINGS:
            with self.subTest(path=p):
                self.assertEqual(pre_split(run([p])), want)

    def test_guard_sibling_edit_sets_the_same_flags_as_guard_py(self):
        got = run(["hooks/guard.py"], existing=["hooks/guard.py"])
        self.assertFlags(got, want_true=["checks_windows", "checks_windows_rest", "checks_macos", "code", "guard", "sweep"],
                         want_false=["checks_windows_merge", "shell_macos", "pointer_windows"])
        want = pre_split(got)
        for p in self.GUARD_SIBLINGS:
            with self.subTest(path=p):
                self.assertEqual(pre_split(run([p], existing=[p])), want)

    def test_shared_names_change_sets_the_same_flags_as_guard_py(self):
        # guard_core.py and config_watch.py import it, so the guard mutation tests must run on it.
        want = pre_split(run(["hooks/guard.py"]))
        self.assertEqual(pre_split(run(["hooks/shared_names.py"])), want)
        self.assertEqual(pre_split(run(["hooks/shared_names.py"], existing=["hooks/shared_names.py"])),
                         pre_split(run(["hooks/guard.py"], existing=["hooks/guard.py"])))

    def test_git_reads_change_sets_the_same_flags_as_guard_py(self):
        # guard_core.py and the janitor's sweep.py and session_end_sweep.py import it, so the guard
        # and sweep mutation tests must run on it.
        want = pre_split(run(["hooks/guard.py"]))
        self.assertEqual(pre_split(run(["hooks/git_reads.py"])), want)
        self.assertEqual(pre_split(run(["hooks/git_reads.py"], existing=["hooks/git_reads.py"])),
                         pre_split(run(["hooks/guard.py"], existing=["hooks/guard.py"])))

    # Control: the guard test file keeps today's flags. A family rule must not catch it.
    def test_guard_test_file_keeps_its_current_flags(self):
        p = "hooks/guard_test_x.py"
        self.assertEqual(self.true_set(run([p])),
                         {"checks_windows", "checks_windows_rest", "checks_macos", "shell_macos", "code", "guard"})
        self.assertEqual(self.true_set(run([p], existing=[p])), {"checks_windows_rest", "checks_macos", "code", "guard"})

    # Control: the guard selector test keeps today's flags.
    def test_test_guard_keeps_its_current_flags(self):
        p = "hooks/test_guard.py"
        self.assertEqual(self.true_set(run([p])), {"checks_windows", "checks_macos", "shell_macos", "code", "guard"})
        self.assertEqual(self.true_set(run([p], existing=[p])), {"checks_windows", "checks_macos", "code", "guard"})

    # Mod and map-skill tests run as a step of the checks, checks-windows and checks-macos jobs, run only on the
    # `mods` flag. A job runs on its own flag, so a path that turns on `mods` must turn on checks_windows and
    # checks_macos too, or a mod-only pull request starts neither job and the step never runs there.
    # `mods` is in ALL, so every fail-safe case in the Scope class carries the mods check.
    MOD_JOBS = ["checks_windows", "checks_macos"]
    def test_a_mods_path_sets_the_mods_flag(self):
        for p in ("mods/plain-diff/check.mjs", "mods/session-board/session-board.test.mjs"):
            with self.subTest(path=p):
                self.assertEqual(run([p]).get("mods"), "true")
        self.assertEqual(run(["README.md", "mods/plain-diff/check.mjs"]).get("mods"), "true")

    def test_a_mods_only_diff_sets_the_mod_jobs_and_no_other_flag(self):
        got = run(["mods/plain-diff/check.mjs"])
        self.assertFlags(got, want_true=["mods"] + self.MOD_JOBS,
                         want_false=[n for n in ALL if n not in ["mods"] + self.MOD_JOBS])

    def test_a_docs_only_diff_leaves_the_mods_flag_off(self):
        self.assertEqual(run(["README.md", "decisions/some-record.md"]).get("mods"), "false")

    # mods/decision-watch/decision-watch.test.mjs imports lint/test_scanner_traps.mjs,
    # and the mod-tests.sh step runs that test. The lint/* rule sets `code` only, so a diff naming only the lint
    # file would skip its test.
    def test_a_scanner_trap_lint_change_sets_the_mods_flag(self):
        self.assertFlags(run(["lint/test_scanner_traps.mjs"]), want_true=["mods", "code"] + self.MOD_JOBS)

    # Each arm that turns `mods` on starts both mod jobs, as a new file and as an edit. An edit leaves every
    # other job flag off, so the set is exact. A new file under lint/ or skills/ is in a landed dir, which adds
    # shell_macos and guard by its own rule, so a new file is checked for the jobs it must not start.
    # `.gitignore` is an arm too: skills/plain-english-map/tests/typescript-home.test.mjs reads it, so a .gitignore-only
    # pull request must run the CI step. It keeps `code`, which its lint suites read.
    MOD_ARMS = ["mods/zz-new/a.mjs", "lint/test_scanner_traps.mjs", "skills/plain-english-map/README.md", ".gitignore"]

    def test_each_mods_arm_starts_the_windows_and_macos_jobs(self):
        for p in self.MOD_ARMS:
            with self.subTest(path=p, edit=True):
                code_arm = p.startswith("lint/") or p == ".gitignore"
                want = {"mods", "checks_windows", "checks_macos"} | ({"code"} if code_arm else set())
                self.assertEqual(self.true_set(run([p], existing=[p])), want,
                                 msg=f"{p}: the mods arm must start the CI step and both mod jobs, and keep code")
            with self.subTest(path=p, edit=False):
                self.assertFlags(run([p]), want_true=["mods"] + self.MOD_JOBS,
                                 want_false=["checks_windows_merge", "checks_windows_rest", "pointer_windows"])

    # Any path under the map skill turns `mods` on, .md files included, as a new file or an edit.
    # The checks job runs the skill's tests only when `mods` is on. Those tests read SKILL.md and
    # .md fixtures, so a .md path with no flag would skip them. The skill and its tests live in
    # this repo (ruling `map-skill-lives-here`: the tests run in the checks workflow).
    MAP_SKILL = "skills/plain-english-map/"

    def test_a_map_skill_md_change_turns_on_mods(self):
        for p in (self.MAP_SKILL + "SKILL.md", self.MAP_SKILL + "tests/fixture/docs/map/core.md",
                  self.MAP_SKILL + "tests/fixture/docs/map/traces/home.md"):
            for existing in ((), (p,)):
                with self.subTest(path=p, edit=bool(existing)):
                    got = run([p], existing=existing)
                    self.assertFlags(got, want_true=["mods"] + self.MOD_JOBS)

    # Control: the fix must not narrow the skill's non-.md paths. They stay on the fail-safe arm.
    def test_a_map_skill_script_change_still_turns_everything_on(self):
        p = self.MAP_SKILL + "scripts/map-check.mjs"
        for existing in ((), (p,)):
            with self.subTest(edit=bool(existing)):
                self.assertFlags(run([p], existing=existing), want_true=ALL)

    # Control: another skill's .md keeps today's flags. The new rule must name the map skill only.
    def test_another_skills_md_keeps_its_current_flags(self):
        p = "skills/ci-hygiene/SKILL.md"
        self.assertFlags(run([p], existing=[p]), want_false=ALL)
        self.assertEqual(self.true_set(run([p])), {"checks_windows", "shell_macos", "code", "guard"})

    # The rm shim suite also runs in checks-macos: BSD rm and the /var symlink change what the shim reads,
    # and a Linux pass proves neither. ci-scope.sh maps bin/rm and the suite to that job ahead of
    # the lint/* rule, which sets `code` only, so a diff that names the suite alone still reaches it.
    def test_an_rm_shim_suite_change_turns_on_the_macos_job(self):
        self.assertFlags(run(["lint/test_rm_shim.py"], existing=["lint/test_rm_shim.py"]), want_true=["checks_macos", "code"])

    # bin/ios-ship and its suite run in the shell-macos job only (macOS /bin/bash 3.2). An edit to either turns on that
    # job and `code`, and no other flag. Without the arm, an unmapped path turns every flag on, so this goes red.
    # Only the edit is exact: a new file under bin/ also sets the install-suite flags (the landed-dirs rule).
    def test_ios_ship_edit_turns_on_only_the_macos_shell_job(self):
        for p in ("bin/ios-ship", "lint/test_ios_ship.sh"):
            with self.subTest(path=p):
                self.assertEqual(self.true_set(run([p], existing=[p])), {"shell_macos", "code"})

    # bin/sim-test and bin/sim-lease are loaded by the guard suite (GuardClosure derives both), so an edit to either also
    # turns on `guard`, the full Windows guard shards and the checks-guard job. The suite script, lint/test_sim_test.sh,
    # is not loaded by it: its edit turns on the macOS shell job and nothing else.
    def test_sim_test_and_sim_lease_edit_turns_on_the_guard_suite_and_the_suite_script_does_not(self):
        for p in ("bin/sim-test", "bin/sim-lease"):
            with self.subTest(path=p):
                got = run([p], existing=[p])
                self.assertEqual(self.true_set(got), {"shell_macos", "code", "guard"}, f"{p}: {got}")
                self.assertEqual(got[GUARD_FULL], "true", f"{GUARD_FULL} for {p}: {got}")
                self.assertEqual(got["checks_guard"], "true", f"checks_guard for {p}: {got}")
        with self.subTest(path="lint/test_sim_test.sh"):
            got = run(["lint/test_sim_test.sh"], existing=["lint/test_sim_test.sh"])
            self.assertEqual(self.true_set(got), {"shell_macos", "code"}, f"lint/test_sim_test.sh: {got}")
            self.assertEqual(got[GUARD_FULL], "false", f"{GUARD_FULL} for lint/test_sim_test.sh: {got}")
            self.assertEqual(got["checks_guard"], "false", f"checks_guard for lint/test_sim_test.sh: {got}")

    # bin/shoot's suite installs a browser, so its own paths and the browser installers turn `shoot` on. An edit sets
    # `code` and `shoot` and no other flag in true_set (checks_guard is outside ALL; the cases below pin it).
    # An unrelated code change leaves `shoot` off.
    def test_shoot_edit_turns_on_only_the_shoot_suite(self):
        for p in ("bin/shoot", "lint/test_shoot.mjs", "testing/skip-locally-fail-in-ci.mjs", ".github/shoot/package-lock.json",
                  "actions/playwright-setup/action.yml"):
            with self.subTest(path=p):
                self.assertEqual(self.true_set(run([p], existing=[p])), {"code", "shoot"})
        self.assertFlags(run(["lint/test_verdict.py"], existing=["lint/test_verdict.py"]), want_false=["shoot"])

    # checks-guard and checks-shoot both install actions/playwright-setup, and checks-guard gates on checks_guard
    # alone (checks.yml). An edit to the action must set checks_guard directly, with `shoot` for checks-shoot.
    # Named failure: the action arm sets code and shoot only, so checks-guard skips its install and guard suite.
    def test_playwright_action_edit_turns_on_the_checks_guard_job(self):
        p = "actions/playwright-setup/action.yml"
        got = run([p], existing=[p])
        self.assertFlags(got, want_true=["code", "shoot"])
        self.assertIn("checks_guard", got, got)
        self.assertEqual(got["checks_guard"], "true", f"checks_guard: {got}")

    # Control: a bin/shoot edit keeps checks_guard off, so the action's arm must not widen to bin/shoot.
    def test_shoot_edit_keeps_checks_guard_off(self):
        p = "bin/shoot"
        got = run([p], existing=[p])
        self.assertFlags(got, want_true=["code", "shoot"])
        self.assertIn("checks_guard", got, got)
        self.assertEqual(got["checks_guard"], "false", f"checks_guard: {got}")

    # checks-guard installs the Playwright that .github/shoot pins, so a change to that pin must start the job.
    # Named failure: the pin path sets code and shoot only, and checks-guard installs the old browser.
    def test_shoot_package_lock_edit_turns_on_the_checks_guard_job(self):
        p = ".github/shoot/package-lock.json"
        got = run([p], existing=[p])
        self.assertFlags(got, want_true=["code", "shoot"])
        self.assertIn("checks_guard", got, got)
        self.assertEqual(got["checks_guard"], "true", f"checks_guard: {got}")

    # pin.sh is the install script checks-guard runs from actions/playwright-setup. Named failure: an edit that
    # starts checks-shoot alone leaves the checks-guard install on the old script.
    def test_playwright_pin_script_edit_turns_on_the_checks_guard_job(self):
        p = "actions/playwright-setup/pin.sh"
        got = run([p], existing=[p])
        self.assertFlags(got, want_true=["code", "shoot"])
        self.assertIn("checks_guard", got, got)
        self.assertEqual(got["checks_guard"], "true", f"checks_guard: {got}")

    # A .md edit under the action is docs, so neither job starts. Named failure: without the *.md carve-out, the
    # action arm starts checks-shoot and checks-guard for a README edit.
    def test_playwright_readme_edit_turns_on_no_job(self):
        p = "actions/playwright-setup/README.md"
        got = run([p], existing=[p])
        self.assertFlags(got, want_false=["code", "shoot"])
        self.assertIn("checks_guard", got, got)
        self.assertEqual(got["checks_guard"], "false", f"checks_guard: {got}")


# The mod phase must run each mods check script (mods/**/check.mjs), not only *.test.mjs. The script cds to its own
# root, so each case runs a copy of it inside a scratch tree under the run folder.
@unittest.skipUnless(BASH, "bash not on PATH")
class ModTestsRunsEveryCheck(unittest.TestCase):
    SENTINEL = "zz-mod-check-ran"
    # Candidate names for the passing test file. find lists by the filesystem's directory order, which depends on
    # the names, so a case tries these until one lists check.mjs where it needs it.
    TEST_NAMES = ["plain-diff.test.mjs"] + [f"{c}.test.mjs" for c in "abcdefghijklmnop"]

    @classmethod
    def setUpClass(cls):
        cls.run_dir = _test_temp.run_folder()

    @classmethod
    def tearDownClass(cls):
        tracked_tree.rm_tree(cls.run_dir)

    def setUp(self):
        # In CI a missing node is a red run, never a skip: the mod phase cannot run without it.
        if shutil.which("node") is None:
            if os.environ.get("CI"):
                self.fail("node is not on PATH in CI, so the mod phase cannot run")
            self.skipTest("node not on PATH")

    @staticmethod
    def node_script(exit_code, say=None):
        """A node file that prints `say` to stderr, then exits with `exit_code`."""
        printed = f"console.error({say!r});\n" if say else ""
        return printed + f"process.exit({exit_code});\n"

    def make_tree(self, name, test=None, check=None, test_name="plain-diff.test.mjs"):
        """A scratch tree: mod-tests.sh, one mod test file (passing by default), and mods/plain-diff/check.mjs if `check` is given."""
        tree = os.path.join(self.run_dir, name)
        tracked_tree.copy_tracked(tree, ".github/scripts")
        plain = os.path.join(tree, "mods", "plain-diff")
        os.makedirs(plain)
        with open(os.path.join(plain, test_name), "w") as f:
            f.write(test or self.node_script(0))
        if check is not None:
            with open(os.path.join(plain, "check.mjs"), "w") as f:
                f.write(check)
        return tree

    def run_phase(self, tree):
        """The mods phase of the copied script, run from `tree`, which holds every file the phase can see."""
        return subprocess.run([BASH, os.path.join(tree, ".github", "scripts", "mod-tests.sh"), "mods"],
                              cwd=tree, capture_output=True, text=True)

    def listing(self, tree):
        """The .mjs files under mods/ in the order find lists them. The mod phase lists a subset of these in the same order."""
        r = subprocess.run(["find", "mods", "-type", "f", "-name", "*.mjs"], cwd=tree, capture_output=True, text=True, check=True)
        return r.stdout.split()

    def tree_listing_check(self, name, check_last):
        """A scratch tree with one passing test file and the red check, listed last (check_last) or first."""
        for i, test_name in enumerate(self.TEST_NAMES):
            tree = self.make_tree(f"{name}-{i}", check=self.node_script(1, self.SENTINEL), test_name=test_name)
            listed = self.listing(tree)
            if len(listed) == 2 and listed[-1].endswith("check.mjs") == check_last:
                return tree
        self.fail(f"no candidate test name lists check.mjs {'last' if check_last else 'first'} on this filesystem")

    # Scope first: the phase ran at all. The asserts after it say what the phase did with the check file. Both orders run,
    # because a phase that takes only the last file's exit code hides a red check listed before a passing file.
    def test_a_red_check_script_fails_the_mod_phase_in_either_order(self):
        for check_last in (True, False):
            with self.subTest(check_last=check_last):
                r = self.run_phase(self.tree_listing_check(f"red-check-{check_last}", check_last))
                self.assertIn("mod tests:", r.stdout, "the mod phase printed no count line, so it did not run")
                # Named failure: check.mjs never runs, because the phase globs *.test.mjs only.
                self.assertIn(self.SENTINEL, r.stdout + r.stderr, "mods/plain-diff/check.mjs did not run: the mod phase skips it")
                self.assertNotEqual(r.returncode, 0, "mods/plain-diff/check.mjs failed, and the mod phase still exited 0")

    # Green control: a passing check file leaves the phase green, so the fix cannot turn it red.
    def test_a_green_check_script_leaves_the_mod_phase_green(self):
        r = self.run_phase(self.make_tree("green-check", check=self.node_script(0, self.SENTINEL)))
        self.assertIn("mod tests:", r.stdout, "the mod phase printed no count line, so it did not run")
        self.assertEqual(r.returncode, 0, f"a passing mods/plain-diff/check.mjs turned the mod phase red:\n{r.stdout}{r.stderr}")

    # Green control: a red *.test.mjs already fails the phase.
    def test_a_red_test_file_fails_the_mod_phase(self):
        r = self.run_phase(self.make_tree("red-test", test=self.node_script(1)))
        self.assertIn("mod tests:", r.stdout, "the mod phase printed no count line, so it did not run")
        self.assertNotEqual(r.returncode, 0, "a red *.test.mjs passed the mod phase")


@unittest.skipUnless(BASH, "bash not on PATH")
class GuardWindowsSplit(unittest.TestCase):
    """The Windows guard suite on a pull_request. guard_windows_full turns on the full shards (checks-windows-guard's shard 1
    and each checks-windows-guard-<i>). guard_windows_slice turns on the slice, which is guard on and full off, so the two never run
    together. Push, schedule, dispatch and the fail-safe paths turn full on and slice off."""

    def test_a_guard_family_pr_turns_the_full_windows_guard_on(self):
        for p in ["hooks/guard.py", "hooks/test_guard.py", "settings.json"] + family_files():
            for existing in ((), (p,)):
                with self.subTest(path=p, edit=bool(existing)):
                    got = run([p], existing=existing)
                    self.assertEqual(got["guard"], "true", f"scope: guard is off for {p}")
                    self.assertEqual(got.get(GUARD_FULL), "true",
                                     f"{GUARD_FULL} is {got.get(GUARD_FULL)!r} for {p}, want 'true': its full shards would not run")

    def test_a_non_family_guard_hook_pr_runs_the_slice_and_not_the_full_shards(self):
        got = run(["hooks/daily_note.py"])
        self.assertEqual(got["guard"], "true", "scope: guard is off for hooks/daily_note.py")
        with self.subTest(output=GUARD_SLICE):
            self.assertEqual(got.get(GUARD_SLICE), "true",
                             f"{GUARD_SLICE} is {got.get(GUARD_SLICE)!r} for hooks/daily_note.py, want 'true'")
        with self.subTest(output=GUARD_FULL):
            self.assertEqual(got.get(GUARD_FULL), "false",
                             f"{GUARD_FULL} is {got.get(GUARD_FULL)!r} for hooks/daily_note.py, want 'false': not a guard family")

    def test_a_docs_only_pr_turns_both_split_flags_off(self):
        got = run(["README.md", "docs/x.md"])
        self.assertEqual(got["guard"], "false", "scope: a docs-only pull_request sets guard")
        for name in GUARD_SPLIT:
            with self.subTest(output=name):
                self.assertEqual(got.get(name), "false", f"{name} is {got.get(name)!r} on a docs-only pull_request, want 'false'")

    def test_the_slice_is_guard_on_and_full_off_on_every_kind_of_path(self):
        # One path of each kind, with its three flags on a pull_request as absolute values: a family module, a non-family
        # guard hook, a guard test file, a guard-arm module, a guard load outside the guard (merge/merge.py), and a docs file.
        # A push turns the full shards on and the slice off, for each path.
        want = {  # path: (guard, full, slice) on a pull_request
            "hooks/guard.py": ("true", "true", "false"),
            "hooks/daily_note.py": ("true", "false", "true"),
            "hooks/guard_test_x.py": ("true", "false", "true"),
            "lint/guard_log_report.py": ("true", "true", "false"),
            "merge/merge.py": ("true", "true", "false"),
            "README.md": ("false", "false", "false"),
        }
        for p, (guard, full, slice_) in want.items():
            with self.subTest(path=p, event="pull_request"):
                got = run([p])
                self.assertEqual((got["guard"], got.get(GUARD_FULL), got.get(GUARD_SLICE)), (guard, full, slice_),
                                 f"guard, {GUARD_FULL}, {GUARD_SLICE} for {p} on a pull_request")
            with self.subTest(path=p, event="push"):
                got = run([p], event="push")
                self.assertEqual((got.get(GUARD_FULL), got.get(GUARD_SLICE)), ("true", "false"),
                                 f"{GUARD_FULL}, {GUARD_SLICE} for {p} on a push")

    def test_push_schedule_dispatch_and_an_unreadable_diff_run_the_full_guard_and_not_the_slice(self):
        runs = [(f"event {ev}", run(["README.md"], event=ev)) for ev in ("push", "schedule", "workflow_dispatch")]
        runs.append(("an unreadable diff", run(["hooks/guard.py"], base="0" * 40)))
        for label, got in runs:
            with self.subTest(case=label):
                self.assertEqual(got["guard"], "true", f"scope: guard is off for {label}")
                self.assertEqual(got.get(GUARD_FULL), "true",
                                 f"{GUARD_FULL} is {got.get(GUARD_FULL)!r} for {label}, want 'true'")
                self.assertEqual(got.get(GUARD_SLICE), "false",
                                 f"{GUARD_SLICE} is {got.get(GUARD_SLICE)!r} for {label}, want 'false': the slice would run beside the full shards")

    def test_a_fail_safe_path_runs_the_full_guard_and_not_the_slice(self):
        for p in (".github/scripts/ci-scope.sh", ".github/workflows/checks.yml", ".gitattributes", "zz-unmapped/blob.bin"):
            with self.subTest(path=p):
                got = run([p])
                self.assertEqual(got["guard"], "true", f"scope: guard is off for {p}")
                self.assertEqual(got.get(GUARD_FULL), "true", f"{GUARD_FULL} is {got.get(GUARD_FULL)!r} for {p}, want 'true'")
                self.assertEqual(got.get(GUARD_SLICE), "false", f"{GUARD_SLICE} is {got.get(GUARD_SLICE)!r} for {p}, want 'false'")

    def test_a_full_size_guard_pr_turns_the_full_guard_on_once(self):
        # Every guard file in one pull_request, not one file at a time: the full state of the split.
        got = run(["hooks/guard.py", "hooks/test_guard.py", "settings.json"] + family_files())
        self.assertEqual(got["guard"], "true", "scope: guard is off for the full set of guard files")
        with self.subTest(output=GUARD_FULL):
            self.assertEqual(got.get(GUARD_FULL), "true", f"{GUARD_FULL} is {got.get(GUARD_FULL)!r} for the full set, want 'true'")
        with self.subTest(output=GUARD_SLICE):
            self.assertEqual(got.get(GUARD_SLICE), "false", f"{GUARD_SLICE} is {got.get(GUARD_SLICE)!r} for the full set, want 'false'")

    def test_a_family_module_sets_the_same_outputs_as_guard_py(self):
        # A family module is a sibling of guard.py: every output matches it, the split flags included.
        for edit in (False, True):
            want = run(["hooks/guard.py"], existing=["hooks/guard.py"] if edit else ())
            for p in family_files():
                with self.subTest(path=p, edit=edit):
                    self.assertEqual(run([p], existing=[p] if edit else ()), want, f"{p}: its outputs differ from guard.py's")

    def test_a_role_table_edit_turns_on_the_guard_and_the_full_windows_guard(self):
        # The guard reads this record at run time (hooks/guard.py role_model_table), and the guard suite checks the real
        # file (hooks/test_guard.py role_real_table_check). It is a .md, so only a scope arm that names it turns the guard on.
        path = role_table_path()
        for existing in ((), (path,)):
            with self.subTest(path=path, edit=bool(existing)):
                got = run([path], existing=existing)
                self.assertEqual(got["code"], "true", f"scope: code is off for {path}")
                self.assertEqual(got["guard"], "true", f"scope: guard is off for {path}: the guard reads its role table")
                self.assertEqual(got.get(GUARD_FULL), "true",
                                 f"{GUARD_FULL} is {got.get(GUARD_FULL)!r} for {path}, want 'true': the guard suite checks it on the real repo")


@unittest.skipUnless(BASH, "bash not on PATH")
class GuardClosure(unittest.TestCase):
    """The files the guard suite loads (guard_closure, read from the code of its two seeds) turn the full Windows guard
    shards on for a pull_request. A loaded file that the scope leaves to the slice runs no full shard."""

    def test_every_file_the_guard_suite_loads_turns_the_full_windows_guard_on(self):
        # A new file only: the full-shard flag reads the path, and the one rule that reads whether a file is new (landed
        # dirs) sets no full flag, so an edit would run the same arm.
        files, _ = guard_closure()
        self.assertTrue(set(GUARD_SEEDS) <= set(files), f"the closure lacks a seed: {files}")
        for p in files:
            with self.subTest(path=p):
                got = run([p])
                self.assertEqual(got.get(GUARD_FULL), "true",
                                 f"{GUARD_FULL} is {got.get(GUARD_FULL)!r} for {p}, want 'true': the guard suite loads it")

    def test_every_load_the_closure_does_not_follow_is_named_in_load_exceptions(self):
        _, unfollowed = guard_closure()
        found = {f"{f}:{line}" for f, line, _ in unfollowed}
        missing, stale = sorted(found - set(LOAD_EXCEPTIONS)), sorted(set(LOAD_EXCEPTIONS) - found)
        self.assertEqual((missing, stale), ([], []),
                         f"LOAD_EXCEPTIONS is out of step: unnamed loads {missing}, entries with no such load {stale}")

    def test_the_derivation_reads_each_kind_of_load(self):
        # One named load of each kind, so a derivation that finds nothing fails here: an import (guard_kill imports
        # _nowindow), a literal repo path (guard.py's RECORD_LAYOUT_FILE), and a loader path (guard.py's sim-lease load).
        files, _ = guard_closure()
        for p in ("hooks/_nowindow.py", "lint/layout.json", "bin/sim-lease"):
            with self.subTest(path=p):
                self.assertIn(p, files)

    def test_a_spread_path_in_a_product_module_is_named_as_a_load_the_closure_does_not_follow(self):
        # A spread folder (`*folder.split("/")`) is how a layout-built path is joined. The closure cannot read it, so the derivation
        # must name it among the unfollowed loads, and LOAD_EXCEPTIONS must name it too. Otherwise a new one drops out silently.
        src = "\n".join(["import os", "", "", "def read(root, folder, name):", '    return os.path.join(root, *folder.split("/"), name)', ""])
        _, _, _, unfollowed = _refs("hooks/spread_probe.py", ast.parse(src), set())
        self.assertEqual([line for line, _ in unfollowed], [5], f"the spread join on line 5 is not named as unfollowed: {unfollowed}")

    def test_a_literal_join_in_a_product_module_is_not_named_as_a_spread(self):
        # Control: a literal repo path is followed or left alone, never named as a spread.
        src = "\n".join(["import os", "", "def read(root):", '    return os.path.join(root, "docs", "x.md")', ""])
        _, _, _, unfollowed = _refs("hooks/literal_probe.py", ast.parse(src), set())
        self.assertEqual(unfollowed, [], f"a literal join is named as unfollowed: {unfollowed}")

    def test_a_spread_join_in_a_test_module_is_a_fixture_path_and_is_not_named(self):
        # Control: a test module's join is a fixture path, as its joins under a run-time root already are.
        src = "\n".join(["import os", "", "def read(root, folder):", '    return os.path.join(root, *folder.split("/"))', ""])
        _, _, _, unfollowed = _refs("lint/test_spread_probe.py", ast.parse(src), set())
        self.assertEqual(unfollowed, [], f"a test module's spread join is named as unfollowed: {unfollowed}")


@unittest.skipUnless(BASH, "bash not on PATH")
class MutationReport(unittest.TestCase):
    """The mutation_report output: on a pull request only from a `batch-` branch, and on every other event."""

    # Named failure: the mutation-report job starts on every pull request, or on none, not only the batch ones.
    def test_only_a_batch_pull_request_turns_it_on_and_a_push_always_does(self):
        feature = run(["README.md"], head_ref="feature-x")
        self.assertIn("mutation_report", feature, feature)
        self.assertEqual(feature["mutation_report"], "false", f"a pull request from feature-x: {feature}")
        batch = run(["README.md"], head_ref="batch-11")
        self.assertEqual(batch["mutation_report"], "true", f"a pull request from batch-11: {batch}")
        push = run(["README.md"], event="push")
        self.assertEqual(push["mutation_report"], "true", f"a push: {push}")


if __name__ == "__main__":
    unittest.main()
