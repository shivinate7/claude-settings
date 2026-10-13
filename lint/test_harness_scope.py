#!/usr/bin/env python3
"""CLI tests for the scope detector (.github/scripts/harness-scope.sh).

Each case builds a scratch git repo, commits a base, commits the changed paths, runs the script
with EVENT, BASE_SHA and BEFORE_SHA set, and reads the name=value lines it wrote to $GITHUB_OUTPUT.
HARNESS_SCOPE overrides the script path (for a successor). Needs bash on PATH.

Output names pinned (the `scope` job re-exports them as job outputs):
  JOB_FLAGS       one per gate job except the lint job `gates`: gates_windows, gates_windows_merge,
                  gates_windows_rest, gates_macos, shell_macos, pointer_windows
  STEP_FLAGS      code, guard, sweep (the suite flags the steps inside a job read)
  guard_families  the families the guard suite runs. "" when no guard path changed, "all" when any
                  changed path cannot be mapped, else a sorted, comma-joined list of names from
                  FAMILIES in hooks/test_guard.py, with no spaces. Only a case line of
                  hooks/test_guard.py maps to a family. Everything else maps to "all".

Run with:  python3 lint/test_harness_scope.py -v
"""
import ast
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.environ.get("HARNESS_SCOPE") or os.path.join(HERE, "..", ".github", "scripts", "harness-scope.sh")
GUARD_SUITE = os.path.join(HERE, "..", "hooks", "test_guard.py")
GUARD_PATH = "hooks/test_guard.py"
JOB_FLAGS = ["gates_windows", "gates_windows_merge", "gates_windows_rest", "gates_macos", "shell_macos", "pointer_windows"]
STEP_FLAGS = ["code", "guard", "sweep"]
ALL = JOB_FLAGS + STEP_FLAGS
GF = "guard_families"
BASH = shutil.which("bash")


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def landed_text(landed=None):
    """The base's landed-dirs.txt: the repo's own, or `landed` (a list of dir names) in its place."""
    if landed is None:
        with open(os.path.join(HERE, "..", "landed-dirs.txt")) as f:
            return f.read()
    return chr(10).join(landed) + chr(10)


def write_all(d, files):
    for p, text in files.items():
        full = os.path.join(d, p)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(text)


def scope(base_files, head_files, event="pull_request", base="auto", before="auto"):
    """-> {name: value} the script wrote. The base commit holds base_files (path -> text). The head
    commit writes head_files (path -> text) on top of it."""
    with tempfile.TemporaryDirectory() as d:
        git(d, "init", "-q")
        git(d, "config", "user.email", "t@t")
        git(d, "config", "user.name", "t")
        git(d, "config", "commit.gpgsign", "false")
        write_all(d, base_files)
        git(d, "add", "-A")
        git(d, "commit", "-qm", "base")
        sha = git(d, "rev-parse", "HEAD")
        write_all(d, head_files)
        git(d, "add", "-A")
        git(d, "commit", "-qm", "head", "--allow-empty")
        out = os.path.join(d, "..", f"out-{os.getpid()}.txt")
        env = dict(os.environ, EVENT=event, GITHUB_OUTPUT=out,
                   BASE_SHA=sha if base == "auto" else base, BEFORE_SHA=sha if before == "auto" else before)
        r = subprocess.run([BASH, os.path.abspath(SCRIPT)], cwd=d, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        with open(out) as f:
            lines = f.read().split()
        os.remove(out)
        return dict(l.split("=", 1) for l in lines)


def run(paths, event="pull_request", base="auto", before="auto", existing=(), landed=None):
    """-> {name: 'true'|'false'} the script wrote. `paths` are committed on top of one base commit."""
    base_files = {"seed.txt": "seed\n", "landed-dirs.txt": landed_text(landed)}
    base_files.update({p: "old\n" for p in existing})  # in the base commit, so the head commit modifies them
    return scope(base_files, {p: "changed\n" for p in paths}, event, base, before)


def known_families():
    """The names in FAMILIES of hooks/test_guard.py, read with the language's own parser."""
    with open(GUARD_SUITE, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "FAMILIES" for t in node.targets):
            return set(ast.literal_eval(node.value))
    raise AssertionError("no FAMILIES in hooks/test_guard.py")


# A synthetic guard suite: four sections, a docstring that holds a FAMILY line, a comment opener and
# a lone quote inside case strings, an rm-var case, a LOG_CHECKS table, and a helper def.
SYNTH_GUARD = r'''FAMILIES = {
    "pointer": "the pointer",
    "kill": "machine-wide kills",
    "rm-var": "every case named rm-var",
    "misc": "anything outside a tagged section",
}
FAMILY = "misc"


def helper():
    return 1


FAMILY = "pointer"
sh("pointer: first case", "git status", "allow")
sh("pointer: a hash # inside a string", "echo # FAMILY = \"kill\"", "allow")
sh("pointer: a lone quote in text", "echo Don't", "allow")
DOC = """
FAMILY = "frozen"
"""
sh("pointer: after the docstring", "git status", "allow")

FAMILY = "kill"
sh("kill: a case", "kill -9 1", "deny")
sh("rm-var: a loop", "rm -rf $S/x", "deny")

LOG_CHECKS = (
    ("log: one", "pointer"),
)
'''

# (old, new) edits to SYNTH_GUARD. Each `old` must occur once.
E_CASE = (r'''sh("pointer: first case", "git status", "allow")''', r'''sh("pointer: first case", "git status -s", "allow")''')
E_HASH = (r'''"echo # FAMILY = \"kill\"", "allow")''', r'''"echo # FAMILY = \"kill\"", "deny")''')
E_LONE = (r'''"echo Don't", "allow")''', r'''"echo Don't now", "allow")''')
E_AFTER = (r'''sh("pointer: after the docstring", "git status", "allow")''', r'''sh("pointer: after the docstring", "git status -s", "allow")''')
E_KILL = (r'''sh("kill: a case", "kill -9 1", "deny")''', r'''sh("kill: a case", "kill -9 2", "deny")''')
E_RMVAR = (r'''sh("rm-var: a loop", "rm -rf $S/x", "deny")''', r'''sh("rm-var: a loop", "rm -rf $S/y", "deny")''')
E_DEF = ("    return 1", "    return 2")
E_FAMILY_LINE = ('FAMILY = "kill"', 'FAMILY = "misc"')
E_LOGS = ('("log: one", "pointer"),', '("log: one", "kill"),')
E_TABLE = ('"pointer": "the pointer",', '"pointer": "the pointer family",')

GUARD_PATHS = ["hooks/guard.py", "hooks/test_guard.py", "lint/check_record_slugs.py", "CLAUDE.md",
               "settings.json", "merge/merge.py"]
NO_GUARD_PATHS = ["README.md", "bin/verdict", "merge/launch.py"]


def synth(edits=(), landed=None, extra_head=None, event="pull_request"):
    """-> the outputs when the head edits the synthetic guard suite (and writes extra_head)."""
    head = SYNTH_GUARD
    for old, new in edits:
        assert head.count(old) == 1, old
        head = head.replace(old, new)
    base_files = {"seed.txt": "seed\n", "landed-dirs.txt": landed_text(landed),
                  "hooks/guard.py": "old\n", GUARD_PATH: SYNTH_GUARD}
    head_files = {GUARD_PATH: head, **(extra_head or {})}
    got = scope(base_files, head_files, event)
    assert GF in got, f"output {GF} missing: {got}"  # a failure, not a KeyError, on a tree without the output
    return got


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
        self.assertFlags(got, want_true=["gates_windows_merge", "code"])

    def test_guard_change_turns_the_guard_suites_on(self):
        got = run(["hooks/guard.py"])
        self.assertFlags(got, want_true=["gates_windows", "gates_macos", "guard", "sweep", "code"])

    def test_a_merge_change_leaves_a_job_that_never_runs_merge_suites_off(self):
        got = run(["merge/merge.py"])
        self.assertFlags(got, want_false=["pointer_windows", "shell_macos"])

    def test_workflow_or_scope_script_change_runs_everything(self):
        for p in (".github/workflows/gates.yml", ".github/scripts/harness-scope.sh"):
            self.assertFlags(run([p]), want_true=ALL)

    def test_unmapped_path_runs_everything(self):
        self.assertFlags(run(["zz-unmapped/blob.bin"]), want_true=ALL)

    def test_unreadable_diff_runs_everything(self):
        bogus = "f" * 40
        self.assertFlags(run(["README.md"], base=bogus), want_true=ALL)
        self.assertFlags(run(["README.md"], base=""), want_true=ALL)

    def test_push_schedule_and_dispatch_run_everything_even_for_docs(self):
        for ev in ("push", "schedule", "workflow_dispatch"):
            self.assertFlags(run(["README.md"], event=ev), want_true=ALL)

    def test_push_with_an_unreadable_range_runs_everything(self):
        self.assertFlags(run(["README.md"], event="push", before="e" * 40), want_true=ALL)

    # Map gaps found in review: each path is read by a suite in another job.
    def test_merge_tool_change_turns_on_the_suites_that_load_it(self):
        self.assertFlags(run(["merge/merge.py"]), want_true=["gates_windows", "gates_macos", "guard", "gates_windows_merge"])

    def test_record_slug_checker_change_turns_on_the_guard_suites(self):
        self.assertFlags(run(["lint/check_record_slugs.py"]), want_true=["gates_windows", "gates_macos", "guard", "code"])

    def test_janitor_launcher_change_turns_on_the_install_suite(self):
        self.assertFlags(run(["bin/claude-janitor"]), want_true=["gates_windows", "shell_macos"])

    def test_silent_undo_checker_change_turns_on_the_merge_job(self):
        self.assertFlags(run(["lint/check_silent_undo.py"]), want_true=["gates_windows_merge"])

    def test_session_start_change_turns_on_the_unknown_read_contract_job(self):
        self.assertFlags(run(["hooks/session_start.sh"]), want_true=["gates_windows_rest"])

    def test_a_new_file_in_a_landed_dir_turns_on_the_install_suite(self):
        for p in ("agents/new.md", "skills/new/SKILL.md", "output-styles/new.md", "lint/new.py"):
            self.assertFlags(run([p]), want_true=["gates_windows", "shell_macos"])

    def test_a_modified_md_under_skills_turns_on_nothing(self):
        self.assertFlags(run(["skills/old/SKILL.md"], existing=["skills/old/SKILL.md"]), want_false=ALL)

    def test_a_new_file_in_hooks_or_janitor_turns_on_the_install_suite(self):
        for p in ("hooks/new.py", "janitor/new.py"):
            self.assertFlags(run([p]), want_true=["gates_windows", "shell_macos"])

    def test_the_landed_dirs_come_from_landed_dirs_txt(self):
        # A made-up dir in the scratch repo's landed-dirs.txt: the script reads the file, it does not copy the list.
        self.assertFlags(run(["zz-made-up/new.md"], landed=["zz-made-up"]), want_true=["gates_windows", "shell_macos"])

    def test_an_empty_or_comment_only_landed_list_turns_everything_on(self):
        for landed in ([], ["# only a comment", ""]):
            self.assertFlags(run(["docs/new.md"], landed=landed), want_true=ALL)

    def test_a_trailing_slash_in_landed_dirs_is_read_as_the_dir(self):
        self.assertFlags(run(["zz-made-up/new.md"], landed=["zz-made-up/"]), want_true=["gates_windows", "shell_macos"])

    # Cut F: gates-windows-guard and gates-mutate-guard skip on the `guard` flag. The slice selector
    # (GUARD_TESTS) is read from hooks/test_guard.py, so an edit to that file must turn `guard` on,
    # or a pull request that changes the slice would run no guard job at all.
    def test_the_guard_selector_and_its_harness_turn_the_guard_flag_on(self):
        for p in ("hooks/test_guard.py", "hooks/mutate_guard.py", "hooks/guard.py"):
            self.assertFlags(run([p]), want_true=["guard"])

    # Review finding on #305: the guard suite reads these two paths, but the rules did not set `guard`,
    # so after cut F a pull request touching them ran the guard suite in no job (false green).
    def test_a_new_file_under_a_landed_dir_turns_on_the_guard_suite(self):
        self.assertFlags(run(["lint/zz_new.py"]), want_true=["guard"])

    def test_the_janitor_launcher_turns_on_the_guard_suite(self):
        self.assertFlags(run(["bin/claude-janitor"]), want_true=["guard"])

    # Control: a docs-only path must keep `guard` off, or the new rules over-trigger (false red).
    def test_a_docs_only_path_keeps_the_guard_flag_off(self):
        for p in ("README.md", "decisions/some-record.md"):
            self.assertFlags(run([p]), want_false=["guard"])


@unittest.skipUnless(BASH, "bash not on PATH")
class GuardFamilies(unittest.TestCase):
    """The guard_families output: which families of hooks/test_guard.py the guard job runs."""

    def scope_of(self, paths, **kw):
        got = run(paths, **kw)
        self.assertIn(GF, got, f"output {GF} missing: {got}")
        return got

    def test_guard_families_is_written_on_every_run(self):
        self.scope_of(["README.md"])

    def test_no_guard_path_gives_guard_off_and_no_families(self):
        for p in NO_GUARD_PATHS:
            with self.subTest(path=p):
                got = self.scope_of([p], existing=[p])
                self.assertEqual(got["guard"], "false", got)
                self.assertEqual(got[GF], "", got)

    def test_guard_flag_and_families_never_disagree(self):
        for p in GUARD_PATHS + NO_GUARD_PATHS:
            with self.subTest(path=p):
                got = self.scope_of([p], existing=[p])
                self.assertEqual(got["guard"] == "true", got[GF] != "", got)

    def test_values_are_all_or_sorted_known_family_names(self):
        known = known_families()
        for p in GUARD_PATHS:
            with self.subTest(path=p):
                value = self.scope_of([p], existing=[p])[GF]
                if value == "all":
                    continue
                names = value.split(",")
                self.assertTrue(names == sorted(set(names)) and set(names) <= known, value)

    def test_guard_readers_outside_the_case_lines_give_all(self):
        for p in ("hooks/guard.py", "hooks/mutate_guard.py", "hooks/mutate_shared.py",
                  "hooks/test_mutate_shared.py", GUARD_PATH, "hooks/decision_watch.py",
                  "lint/check_record_slugs.py", "merge/merge.py", "settings.json", "CLAUDE.md",
                  "landed-dirs.txt", "install.sh", "hooks/session_start.sh", "bin/claude-janitor"):
            with self.subTest(path=p):
                got = self.scope_of([p], existing=[p])
                self.assertEqual(got["guard"], "true", got)
                self.assertEqual(got[GF], "all", got)

    def test_a_new_file_in_a_landed_dir_gives_all(self):
        self.assertEqual(self.scope_of(["lint/zz_new.py"])[GF], "all")

    def test_push_schedule_dispatch_and_an_empty_diff_give_all(self):
        for ev in ("push", "schedule", "workflow_dispatch"):
            with self.subTest(event=ev):
                self.assertEqual(self.scope_of(["README.md"], event=ev)[GF], "all")
        with self.subTest(event="push", path="case line"):
            self.assertEqual(synth([E_CASE], event="push")[GF], "all")
        with self.subTest(event="pull_request", path="empty diff"):
            self.assertEqual(self.scope_of([])[GF], "all")

    def test_an_unreadable_diff_gives_all(self):
        for base in ("f" * 40, ""):
            with self.subTest(base=base):
                self.assertEqual(self.scope_of(["README.md"], base=base)[GF], "all")

    def test_an_empty_landed_list_gives_all_even_for_a_case_line(self):
        self.assertEqual(synth([E_CASE], landed=[])[GF], "all")

    # The case-line map. A line of a case (sh/add call or its tuple table) maps to the family of the
    # nearest FAMILY assignment above it in the file. The scanner must read Python source, not text.
    def test_a_case_line_maps_to_its_section_family(self):
        self.assertEqual(synth([E_CASE])[GF], "pointer")

    def test_a_comment_opener_inside_a_string_does_not_move_the_family(self):
        self.assertEqual(synth([E_HASH])[GF], "pointer")

    def test_a_lone_quote_in_text_does_not_move_the_family(self):
        self.assertEqual(synth([E_LONE])[GF], "pointer")

    def test_a_family_line_inside_a_docstring_does_not_switch_the_family(self):
        self.assertEqual(synth([E_AFTER])[GF], "pointer")

    def test_a_kill_case_line_maps_to_kill(self):
        self.assertEqual(synth([E_KILL])[GF], "kill")

    def test_an_rm_var_named_line_adds_rm_var(self):
        self.assertEqual(synth([E_RMVAR])[GF], "kill,rm-var")

    def test_two_sections_name_both_families(self):
        self.assertEqual(synth([E_CASE, E_KILL])[GF], "kill,pointer")

    def test_harness_edits_give_all(self):
        for name, edit in (("def body", E_DEF), ("FAMILY line", E_FAMILY_LINE),
                           ("LOG_CHECKS table", E_LOGS), ("FAMILIES table", E_TABLE)):
            with self.subTest(edit=name):
                self.assertEqual(synth([edit])[GF], "all")

    def test_a_case_line_with_a_guard_py_change_gives_all(self):
        self.assertEqual(synth([E_CASE], extra_head={"hooks/guard.py": "changed\n"})[GF], "all")

    def test_a_docs_change_beside_a_case_line_adds_no_family(self):
        self.assertEqual(synth([E_CASE], extra_head={"README.md": "changed\n"})[GF], "pointer")


if __name__ == "__main__":
    unittest.main()
