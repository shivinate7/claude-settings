#!/usr/bin/env python3
"""The guard inputs list, .github/guard-inputs.txt: one glob per line, `#` comments. .github/scripts/ci-scope.sh reads it for windows_guard.

A diff that touches no guard input runs no Windows guard shard, so the list must name every repo file the guard suite reads.
GuardInputsList proves: (a) every path in TRACED_READS matches a glob, and each one is a tracked repo file; (b) every string
constant in hooks/test_guard.py and tests/guard/*.py that equals a tracked repo file, or an os.path.join of constants that
does, matches a glob; (c) every module that hooks/guard.py or hooks/test_guard.py imports, at any depth, matches a glob; (d) every
glob names at least one tracked file.

Cost of this test: one `git ls-files` process per run (a walk of the tree where .git is absent, as in a git archive copy), one
read of the list, and an ast parse of hooks/test_guard.py, tests/guard/*.py and the import closure of the two guard entry points.
No clock, no sleep, no other process.

Run with:  python3 lint/test_guard_inputs.py -v
"""
import ast
import fnmatch
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.realpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  rm_tree removes the run folder
from test_ci_scope import imported_names  # noqa: E402  the one home of the import walk (lint/test_ci_scope.py)

RUN_DIR = None


def setUpModule():
    global RUN_DIR
    RUN_DIR = _test_temp.run_folder()


def tearDownModule():
    tracked_tree.rm_tree(RUN_DIR)


GUARD_INPUTS_REL = ".github/guard-inputs.txt"
GUARD_INPUTS = os.path.join(ROOT, *GUARD_INPUTS_REL.split("/"))
# The guard's two entry points: the import walk starts here. test_guard.py also loads tests/guard/*.py (guard_reader_files).
IMPORT_ROOTS = ("hooks/guard.py", "hooks/test_guard.py")
# Folders the guard's imports resolve in: hooks/ and lint/ go on sys.path, and merge/merge.py is loaded by path.
IMPORT_DIRS = ("hooks", "lint", "merge", "janitor", "testing", "skills/waiting-page")

# Seed: the repo files the guard suite opened in an strace of its twelve shards (Linux, absolute opens), normalised to tracked
# repo paths, with __pycache__, .git and directories left out. Kept beside its only reader. Case (a) reads it.
TRACED_READS = (
    ".claude/layout-extras.json",
    "actions/ci-alarm/events.json",
    "agents/builder.md",
    "agents/claude-code-guide.md",
    "agents/design-reviewer.md",
    "agents/designer.md",
    "agents/explore.md",
    "agents/plan.md",
    "agents/record-writer.md",
    "agents/refuter.md",
    "agents/reviewer.md",
    "agents/test-author.md",
    "bin/sim-lease",
    "bin/sim-test",
    "docs/decisions/agent-model-cap.md",
    "hooks/_nowindow.py",
    "hooks/action_pin.py",
    "hooks/agent_brief.py",
    "hooks/blind_brief.py",
    "hooks/call_judge.py",
    "hooks/case_runner_test.py",
    "hooks/ci_wait_cap.json",
    "hooks/ci_wait_cap.py",
    "hooks/ci_wake.py",
    "hooks/config_watch.py",
    "hooks/daily_note.py",
    "hooks/decision_watch.py",
    "hooks/denial_note.py",
    "hooks/feedback_gate.py",
    "hooks/feedback_guard.py",
    "hooks/git_bash.py",
    "hooks/git_reads.py",
    "hooks/guard.py",
    "hooks/guard_argv.py",
    "hooks/guard_branch_worktree.py",
    "hooks/guard_core.py",
    "hooks/guard_env.py",
    "hooks/guard_frozen.py",
    "hooks/guard_kill.py",
    "hooks/guard_mask_script.py",
    "hooks/guard_merge.py",
    "hooks/guard_pointer.py",
    "hooks/guard_push_delete.py",
    "hooks/guard_rm_var.py",
    "hooks/guard_shared_tree.py",
    "hooks/guard_stream.py",
    "hooks/guard_wsl.py",
    "hooks/local_time.py",
    "hooks/mail.py",
    "hooks/mutate_shared.py",
    "hooks/override.py",
    "hooks/own_session.py",
    "hooks/pin_note.py",
    "hooks/precompact_handoff.py",
    "hooks/precompact_handoff_prompt.md",
    "hooks/probe.py",
    "hooks/proc_env.py",
    "hooks/prose_judge.py",
    "hooks/question_form.py",
    "hooks/refusal_note.py",
    "hooks/reply_judge.py",
    "hooks/required_check.py",
    "hooks/reread_check.py",
    "hooks/rm_prompt_answer.py",
    "hooks/route_match.py",
    "hooks/ruling_home.py",
    "hooks/sendmessage_state.py",
    "hooks/session_role.py",
    "hooks/shared_names.py",
    "hooks/sim_boot_record.py",
    "hooks/stale_install.py",
    "hooks/stall_watch.py",
    "hooks/start_check.py",
    "hooks/start_session_audit.py",
    "hooks/test_guard.py",
    "hooks/tool_lists_test.py",
    "hooks/wait_common.py",
    "install.sh",
    "janitor/sweep.py",
    "janitor/temp_sweep.py",
    "lint/_clause.py",
    "lint/_test_git.py",
    "lint/_transcript.py",
    "lint/check_red_run.py",
    "lint/check_skill_model_rows.py",
    "lint/hook_catalog.py",
    "lint/layout.json",
    "lint/layout.py",
    "lint/report_guard.py",
    "lint/rule_audit.py",
    "lint/ruled_store.py",
    "lint/stale_cites.py",
    "merge/install_from_main.sh",
    "merge/merge.py",
    "package.json",
    "settings.json",
    "skills/impeccable/SKILL.md",
    "skills/waiting-page/check_designs.mjs",
    "skills/waiting-page/page.html",
    "skills/waiting-page/page_check.py",
    "skills/waiting-page/splice.py",
    "skills/waiting-page/stale_pages.py",
    "testing/shallow_clone.py",
    "tests/guard/s00442-misc.py",
    "tests/guard/s02747-shared-tree.py",
    "tests/guard/s03975-branch-worktree.py",
    "tests/guard/s04342-two-worktrees-one-branch.py",
    "tests/guard/s04619-pointer.py",
    "tests/guard/s04769-pointer-edit.py",
    "tests/guard/s04855-hand-made-worktree.py",
    "tests/guard/s05163-kill.py",
    "tests/guard/s06578-wsl.py",
    "tests/guard/s06590-stream.py",
    "tests/guard/s06591-check-timeout.py",
    "tests/guard/s07779-wsl.py",
    "tests/guard/s08198-env.py",
    "tests/guard/s08204-write.py",
    "tests/guard/s08727-push-delete.py",
    "tests/guard/s08728-push-delete-archive-guard.py",
    "tests/guard/s10425-linked-node-modules.py",
    "tests/guard/s10739-env.py",
    "tests/guard/s12634-git-env.py",
    "tests/guard/s12965-hook-bypass.py",
    "tests/guard/s13406-merge.py",
    "tests/guard/s13410-local-role.py",
    "tests/guard/s14736-lane-closes-after-records.py",
    "tests/guard/s15173-lane-one-topic.py",
    "tests/guard/s15303-message-time-matches-clock.py",
    "tests/guard/s15866-sendmessage-session-id.py",
    "tests/guard/s15918-cite.py",
    "tests/guard/s16334-scratchpad-message.py",
    "tests/guard/s16449-records-page-ready.py",
    "tests/guard/s16689-records-page.py",
    "tests/guard/s17500-conflict-markers.py",
    "tests/guard/s17973-octopus-push.py",
    "tests/guard/s18211-frozen.py",
    "tests/guard/s19328-model-cap.py",
    "tests/guard/s19834-ask-alone.py",
    "tests/guard/s20106-ask-alone.py",
    "tests/guard/s20369-paths.py",
    "tests/guard/s21304-diff.py",
    "tests/guard/s21893-hook-bypass.py",
    "tests/guard/s21922-frozen.py",
    "tests/guard/s22063-merge.py",
    "tests/guard/s22192-lane-closes-after-records.py",
    "tests/guard/s22669-lane-closes-after-records.py",
    "tests/guard/s22868-paths.py",
    "tests/guard/s23264-builder-refuse.py",
    "tests/guard/s24995-paths.py",
    "tests/guard/s25010-impeccable.py",
    "tests/guard/s25339-branch-worktree.py",
    "tests/guard/s25354-port-question.py",
    "tests/guard/s25539-page-stale.py",
    "tests/guard/s25798-page-item-design.py",
    "tests/guard/s26314-uniform-pick.py",
    "tests/guard/s26433-press-link.py",
    "tests/guard/s26657-command-in-item.py",
    "tests/guard/s26800-gh-login-switch.py",
    "tests/guard/s26952-task-names-check.py",
    "tests/guard/s27028-owner-judge.py",
    "tests/guard/s27279-question-departs.py",
    "tests/guard/s27394-item-field-rendered.py",
    "tests/guard/s27664-owner-judge.py",
    "tests/guard/s28192-option-letter-keys.py",
    "tests/guard/s28433-rework-off-page.py",
    "tests/guard/s28508-rule9.py",
    "tests/guard/s29483-workflow-args.py",
    "tests/guard/s29526-agent-remote-tools.py",
    "tests/guard/s29666-rule9.py",
    "tests/guard/s29942-merge.py",
    "tests/guard/s30130-rule9.py",
    "tests/guard/s32594-worktree-home.py",
    "tests/guard/s33355-misc.py",
    "tests/guard/s33514-worktree-home.py",
    "tests/guard/s33527-session-home.py",
    "tests/guard/s34371-scratchpad-owner.py",
    "tests/guard/s35192-mask-script.py",
    "tests/guard/s35537-push-delete.py",
    "tests/guard/s35555-mask-script.py",
    "tests/guard/s35642-fail-closed.py",
    "tests/guard/s35850-reload-stamp.py",
    "tests/guard/s36081-fail-closed.py",
    "tests/guard/s36421-override.py",
    "tests/guard/s37949-handoff-unread.py",
    "tests/guard/s38287-handoff-sections.py",
    "tests/guard/s38500-start-session-audit.py",
    "tests/guard/s38816-handoff-checked-stamp.py",
    "tests/guard/s38950-page-thread-reply.py",
    "tests/guard/s39497-load-brake.py",
    "tests/guard/s40805-role-model.py",
    "tests/guard/s41900-simulator.py",
    "tests/guard/s42840-simulator.py",
    "tests/guard/s42841-readonly-shell-write.py",
    "tests/guard/s43100-lane-title-slug.py",
    "tests/guard/s43200-ci-wait-cap.py",
    "tests/guard/s43300-brief-ids-in-roster.py",
    "tests/guard/s43400-red-run-push.py",
    "tests/guard/s43405-red-run-pending-revert.py",
    "tests/guard/s43410-red-run-commit.py",
    "tests/guard/s43420-red-run-commit-chain.py",
    "tests/guard/s43421-red-run-replay.py",
)


# Tracked files the guard suite names as data: a fixture written into a temp tree, or a name inside a command string. The guard
# reads the temp copy, never the repo file, and the trace opens none of them. Case (b) passes these names without a glob. Each
# entry is checked against the suite every run, so an entry the suite stops naming fails too. A new name here needs its reason.
FIXTURE_NAMES = {
    "CLAUDE.md": "a fixture file written into a temp config or repo",
    "README.md": "a fixture repo file and a command string",
    "docs/records.md": "a fixture records page written into temp repos",
    "docs/decisions/premise-format.md": "a record name inside a fixture's text",
    ".github/dependabot.yml": "a fixture file written into a temp repo",
    ".github/workflows/checks.yml": "a fixture file written into a temp repo; ci-scope.sh's own rule turns on for the real file",
    "install.ps1": "a fixture file in temp clones",
    "install.test.ps1": "a name inside a fixture's text",
    "actions/stamp/stamp.mjs": "a name inside a fixture command string",
    "actions/stamp/test_stamp.mjs": "a name inside a fixture command string",
    "bin/merge": "a command string",
    "bin/wait-pid": "a command string",
}


def read_globs(path=GUARD_INPUTS):
    """The list's globs, in file order: each line with its `#` comment and surrounding space taken off, blank lines dropped.
    A `#` starts a comment anywhere on a line, so a glob cannot hold one."""
    if not os.path.isfile(path):
        return []  # no list yet: no glob matches, so each case that needs one names the paths it leaves uncovered
    with open(path, encoding="utf-8") as f:
        return [s for s in (line.split("#", 1)[0].strip() for line in f) if s]


def matches(path, globs):
    return any(fnmatch.fnmatchcase(path, g) for g in globs)


def tracked_files():
    """The repo files git tracks, as repo-relative paths with `/`. Where .git is absent (a git archive copy holds only tracked
    files) it walks the tree instead, skipping .git and __pycache__."""
    if os.path.exists(os.path.join(ROOT, ".git")):
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        return {p for p in out.split("\0") if p}
    found = set()
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__")]
        for name in filenames:
            found.add(os.path.relpath(os.path.join(dirpath, name), ROOT).replace(os.sep, "/"))
    return found


def guard_reader_files():
    """hooks/test_guard.py, then the tests/guard/*.py sections it loads."""
    sections = sorted(f"tests/guard/{n}" for n in os.listdir(os.path.join(ROOT, "tests", "guard")) if n.endswith(".py"))
    return ["hooks/test_guard.py"] + sections


def is_repo_join(call):
    """True for `os.path.join(REPO, ...)`, the guard suite's own spelling of a path in the repo (REPO is the repo root)."""
    fn = call.func
    return (isinstance(fn, ast.Attribute) and fn.attr == "join" and isinstance(fn.value, ast.Attribute)
            and fn.value.attr == "path" and isinstance(fn.value.value, ast.Name) and fn.value.value.id == "os"
            and bool(call.args) and isinstance(call.args[0], ast.Name) and call.args[0].id == "REPO")


def named_in_source(source, rel, tracked):
    """-> [(path, line)] for the module text `source` (`rel` names it in a syntax error): each string constant that equals a
    tracked file, and each os.path.join(REPO, ...) whose other arguments are all string constants spelling a tracked file. A
    join with a variable piece is not read here: the trace in TRACED_READS covers what ran. The ast reads the strings, so a
    comment names nothing."""
    tree = ast.parse(source, rel)
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in tracked:
            hits.append((node.value, node.lineno))
        elif isinstance(node, ast.Call) and is_repo_join(node):
            pieces = node.args[1:]
            if pieces and all(isinstance(a, ast.Constant) and isinstance(a.value, str) for a in pieces):
                joined = "/".join(a.value for a in pieces)
                if joined in tracked:
                    hits.append((joined, node.lineno))
    return hits


def named_repo_files(rel, tracked):
    """named_in_source for the repo file `rel`."""
    with open(os.path.join(ROOT, *rel.split("/")), encoding="utf-8") as f:
        return named_in_source(f.read(), rel, tracked)


def module_file(name):
    """The repo .py file a module name stands for in IMPORT_DIRS, or None: a/b.py, or a/b/__init__.py for a package."""
    rel = name.replace(".", "/")
    for folder in IMPORT_DIRS:
        for cand in (f"{folder}/{rel}.py", f"{folder}/{rel}/__init__.py"):
            if os.path.isfile(os.path.join(ROOT, *cand.split("/"))):
                return cand
    return None


def import_closure(roots):
    """The repo .py files the roots import, at any depth, the roots included."""
    found, todo = set(roots), list(roots)
    while todo:
        rel = todo.pop()
        with open(os.path.join(ROOT, *rel.split("/")), encoding="utf-8") as f:
            tree = ast.parse(f.read(), rel)
        for name in imported_names(tree):
            hit = module_file(name)
            if hit and hit not in found:
                found.add(hit)
                todo.append(hit)
    return found


class GuardInputsList(unittest.TestCase):
    # The list reader is a line scanner: a whole-line comment, an inline comment, a lone apostrophe inside a comment and blank lines
    # each read as the globs alone. Named failure: a comment or a blank line reaches the globs and matches nothing, or a glob is lost.
    def test_the_list_reader_drops_comments_blank_lines_and_apostrophes(self):
        path = os.path.join(RUN_DIR, "guard-inputs.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("# whole-line comment\n\nhooks/*\nlint/*  # the guard's lint folder, don't read it as code\n   tests/guard/*   \n")
        self.assertEqual(read_globs(path), ["hooks/*", "lint/*", "tests/guard/*"])

    def globs(self):
        return read_globs()

    # Named failure: a file the guard suite reads is not in the list, so a diff to it runs no guard shard.
    def test_every_traced_read_matches_a_glob(self):
        globs = self.globs()
        misses = [p for p in TRACED_READS if not matches(p, globs)]
        self.assertEqual(misses, [], f"traced reads that no glob of {GUARD_INPUTS_REL} matches: {misses}")

    def test_every_traced_read_is_a_tracked_file(self):
        tracked = tracked_files()
        gone = [p for p in TRACED_READS if p not in tracked]
        self.assertEqual(gone, [], f"TRACED_READS names paths that are not tracked repo files: {gone}")

    def test_the_scan_reaches_the_guard_readers(self):
        readers = guard_reader_files()
        self.assertIn("hooks/test_guard.py", readers)
        self.assertGreaterEqual(len(readers), 12, f"the guard readers are too few: {readers}")

    # Named failure: the guard suite names a tracked repo file that no glob of the list matches, and that is not a fixture name.
    def test_every_repo_file_the_guard_suite_names_matches_a_glob(self):
        globs = self.globs()
        tracked = tracked_files()
        misses = [f"{rel}:{line} names {path}" for rel in guard_reader_files() for path, line in named_repo_files(rel, tracked)
                  if not matches(path, globs) and path not in FIXTURE_NAMES]
        self.assertEqual(misses, [], f"the guard suite names a repo file that {GUARD_INPUTS_REL} does not match: {misses}")

    # Named failure: FIXTURE_NAMES keeps a name the guard suite no longer names, so the exemption outlives its use.
    def test_every_fixture_name_is_still_named_by_the_suite(self):
        tracked = tracked_files()
        named = {path for rel in guard_reader_files() for path, _ in named_repo_files(rel, tracked)}
        stale = sorted(n for n in FIXTURE_NAMES if n not in named)
        self.assertEqual(stale, [], f"FIXTURE_NAMES lists a name the guard suite no longer names: {stale}")

    # Mutant reads, each one an unlisted tracked file joined from pieces. The scan must report the path in every shape. The
    # plain consecutive shape is the control: it was already read. Named failure: a read joined through a variable, a literal
    # list or a helper's *parts is invisible to the scan, so no glob is checked for the file it reads.
    def test_a_read_joined_from_pieces_is_seen_in_every_shape(self):
        target = "docs/decisions/session-tiers.md"
        shapes = {
            "a starred tuple held in a variable": 'parts = ("docs", "decisions", "session-tiers.md")\n'
                                                   "text = open(os.path.join(REPO, *parts)).read()\n",
            "a starred list literal": 'text = open(os.path.join(REPO, *["docs", "decisions", "session-tiers.md"])).read()\n',
            "a helper that joins its *parts": 'def repo_path(*parts):\n    return os.path.join(REPO, *parts)\n'
                                              'text = open(repo_path("docs", "decisions", "session-tiers.md")).read()\n',
            "consecutive literal arguments": 'text = open(os.path.join(REPO, "docs", "decisions", "session-tiers.md")).read()\n',
        }
        header = "import os\nREPO = os.path.dirname(os.path.abspath(__file__))\n"
        for shape, body in shapes.items():
            with self.subTest(shape=shape):
                hits = {path for path, _ in named_in_source(header + body, "hooks/mutant.py", {target})}
                self.assertIn(target, hits, f"the scan does not see {target} read as {shape}: {sorted(hits)}")

    def test_the_import_walk_reaches_the_guard(self):
        self.assertIn("hooks/guard.py", import_closure(IMPORT_ROOTS))

    # Named failure: a module the guard imports is not in the list, so a diff to it runs no guard shard.
    def test_every_module_the_guard_imports_matches_a_glob(self):
        globs = self.globs()
        misses = [p for p in sorted(import_closure(IMPORT_ROOTS)) if not matches(p, globs)]
        self.assertEqual(misses, [], f"modules the guard imports that {GUARD_INPUTS_REL} does not match: {misses}")

    # Named failure: a glob in the list names no tracked file, so the list has drifted from the repo.
    def test_every_glob_matches_a_tracked_file(self):
        globs = self.globs()
        tracked = tracked_files()
        dead = [g for g in globs if not any(fnmatch.fnmatchcase(p, g) for p in tracked)]
        self.assertEqual(dead, [], f"globs in {GUARD_INPUTS_REL} that match no tracked file: {dead}")


if __name__ == "__main__":
    unittest.main()
