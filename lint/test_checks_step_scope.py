"""Pins the scope gate on the `checks` job's steps (lane ci-skip-untouched-steps, slice 2).

ci-scope.sh sets `code` false for a change that touches only .md files. A step that reads no .md file takes the gate
`needs.scope.outputs.code == 'true' || github.event_name != 'pull_request'`, so a docs-only pull request skips it. A
step that reads a .md file stays ungated. The step lists are the audit of main's checks.yml when this was written, by step name.

Pinned here:
  1. each NO-MD and NAMES-ONLY step carries the gate, exactly.
  2. each MUST-STAY-UNGATED step has no scope output in its `if:`, and each PR-only step keeps its own `if:`.
  3. the checks job's step names equal MAIN_STEPS: no rename, add or drop.
  4. a docs-only pull request leaves `code` false, skips each gated step, and leaves STE lint running.
     The fail-safe flags are not repeated: lint/test_ci_scope.py pins them in Scope.test_push_schedule_and_dispatch_run_everything_even_for_docs,
     Scope.test_unreadable_diff_runs_everything, and Scope.test_merge_change_turns_the_merge_job_on (a .py change sets code).
  5. the entry file of each gated step names no tracked .md file, unless ALLOWED lists that name with a reason.

Steps are read by lint/workflow_steps.py. The `if:` evaluator is eval_if in lint/test_windows_split.py.
The pure-parse guard reads the entry file only, and a name split across arguments is not seen.
"""
import os
import re
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import workflow_steps as ws  # noqa: E402  the one home of the step parser
from test_ci_scope import run as scope_run  # noqa: E402  ci-scope.sh run in a temp repo: the one home of the scope run
from test_windows_split import NO_MD_GATE, eval_if  # noqa: E402  the one home of the `if:` evaluator and of the gate

ROOT = os.path.normpath(os.path.join(HERE, ".."))
WORKFLOW = ".github/workflows/checks.yml"
JOB = "checks"
GATE = "${{ %s }}" % NO_MD_GATE
PR_ONLY_IF = "${{ github.event_name == 'pull_request' }}"
STE_LINT = "STE lint"
DOC = "docs/decisions/x.md"

# The audit's NO-MD steps: each reads no .md file at run time, so each takes the gate.
NO_MD = [
    'Config watch fixture suite',
    'Config watch fast-exit suite',
    'Claude Code compaction check fixture suite',
    'Decision watch fixture suite',
    'Reply judge fixture suite',
    'Prose judge fixture suite',
    'Refusal note fixture suite',
    'Refusal note agent row suite',
    'Refusal note route row suite',
    'Call judge fixture suite',
    'Question form option-key gap suite',
    'Question form option-label suite',
    'Question form letters-frozen suite',
    'Remove-prompt answer fixture suite',
    'Local time line fixture suite',
    'CI wake-up fixture suite',
    'Feedback inbox fixture suite',
    'Waiting export check suite',
    'Git mailbox suite',
    'No-window helper fixture suite',
    'Auto-mode allow entry suite',
    'Stall watch fixture suite',
    'Stall watch stop suite',
    'Simulator boot-record fixture suite',
    'Guard wrappers fixture suite',
    'Deny checks never raise suite',
    'Session start notice suite',
    'Directory before a segment suite',
    'Refusal settle fixture suite',
    'Stop-hook triage hold suite',
    'Stop-hook question route suite',
    'Stop-hook page writer suite',
    'Stop-hook stamped copy suite',
    'Stop-hook route row falsifier suite',
    'Stop-hook hand-off cite suite',
    'Clause parser suite',
    'Stop-hook landing fixture suite',
    'Ruling home fixture suite',
    'Scratchpad owner fixture suite',
    'Ruling census fixture suite',
    'Ruled store fixture suite',
    'Guard log report fixture suite',
    'Verdict runner fixture suite',
    'Wait-pid helper fixture suite',
    'Wait-until helper fixture suite',
    'sim-lease fixture suite',
    'Fixture copy helper suite',
    'Test-run signing opt-out fixture suite',
    'Debt notes union merge fixture suite',
    'all-jobs-passed needs every pull-request job',
    'Scope detector fixture suite',
    'Touched-test selector fixture suite',
    'Mutation report-mode fixture suite',
    'Mutation JS engine fixture suite',
    'Hook platform exit fixture suite',
    'Hook dup-name fixture suite',
    'Plan refuter fixture suite',
    'Copy finder fixture suite',
    'Time-pinned finder fixture suite',
    'Hook dup-name check',
    'Label once fixture suite',
    'Repo colour fixture suite',
    'Waiting page staleness fixture suite',
    'Waiting page splice fixture suite',
    'Waiting page grant check suite',
    'Waiting page grant answer-label suite',
    'Waiting page grant held suite',
    'Waiting page question source suite',
    'Artifact cite fixture suite',
    'Roadmap builder fixture suite',
    'Layout readers hold no record path',
    'Shared resource declaration fixture suite',
    'Shared resource declaration check',
    'iPhone mockup check fixture suite',
    'CLAUDE.md size fixture suite',
    'ios-apps skill starter suite',
    'Unknown-read contract fixture suite',
    'Skill model rows fixture suite',
    'Python 3.9 floor check',
    'Playwright setup action suite',
    'Record stamp engine fixture suite',
    'Scanner trap lint',
    'Record stamp action fixture suite',
]

# The audit's NAMES-ONLY steps: each names a file, or copies only hooks/ and lint/ files, which already set `code`.
NAMES_ONLY = [
    'Shared names suite',
    'Guard probe helper fixture suite',
    'Job runner fixture suite (bin/ci-job)',
    'Windows split guard',
    'Mutation replay fixture suite',
    'Mutation CI report fixture suite',
    'Hook stub fixture suite',
    'Record slug fixture suite',
    'Red-run trailer fixture suite',
    'Hook stub check',
]

# The audit's MUST-STAY-UNGATED steps: each reads a .md file at run time, so each stays ungated.
MUST_STAY_UNGATED = [
    'STE lint',
    'Rule mechanization audit',
    'Glossary fixture suite',
    'Glossary homes and avoided names',
    'Retired names, one word per meaning',
    'Map check',
    'Record slug length',
    'Cost line pins',
    'Artifact cite check',
    'Hook catalog fixture suite',
    'Hook catalog check',
    'CLAUDE.md size (warns, never fails)',
    'Stop-hook guard fixture suite',
    'Stop-hook cannot-claim suite',
    'Stop-hook owner-safe reason suite',
    'Stop-hook review-record fixture suite',
    'Rule audit fixture suite',
    'Stale prose check fixture suite',
    'Agent and skill model floor',
    'Agent and skill model floor fixture suite',
    'Agent push form fixture suite',
    'Skill model rows check',
    'Retired repo fixture suite',
    'project-ops skill scaffold suite',
    'Compliance probes fixture suite',
    'Waiting page park relay prose suite',
    'Settings matcher fixture suite',
    'Route judge measure fixture suite',
    'Question form fixture suite',
    'Agent brief fixture suite',
    'Blind brief fixture suite',
    'SendMessage state fixture suite',
    'Precompact handoff fixture suite',
    'Handoff wave-2 fixture suite',
    'Git mailbox wait suite',
    'Daily note fixture suite',
    'Now-central helper fixture suite',
    'Landed-directory check fixture suite',
    'Python 3.9 floor fixture suite',
    'STE lint action fixture suite',
    'Layout fixture suite',
    'Mod version fixture suite',
    'Mod version bump',
    'Code check',
    'Workflow supply-chain audit (zizmor)',
    'Silent undo fixture suite',
    'Debt retire fixture suite',
    'Comment narration fixture suite',
    'Ruling kind fixture suite',
    'Checks step scope suite',  # names tracked .md files as data; a docs-only rename would turn main red if it were gated
]

# The steps that run only on a pull request, each with its own `if:`. The scope gate does not touch them.
PR_ONLY = [
    'Red-run trailer',
    'Plan refuter line',
    'Ruling kind check',
    'Silent undo check',
    'Comment narration check',
]

# The checks job's step names. An unnamed step is its `uses:` reference.
MAIN_STEPS = [
    'uses: actions/checkout@08c6903cd8c0fde910a37f88322edcfb5dd907a8',
    'uses: actions/setup-python@e797f83bcb11b83ae66e0230d6156d7c80228e7c',
    'Workflow supply-chain audit (zizmor)',
    'Code-check tools',
    'Code check',
    'Action metadata loads',
    'Code-check action',
    'Ruling-kind records-dir input',
    'Janitor sweep fixture suite',
    'Janitor sweep mutation test',
    'Reap proof Git Bash one-home suite',
    'Config watch fixture suite',
    'Config watch fast-exit suite',
    'Shared names suite',
    'Precompact handoff fixture suite',
    'Claude Code compaction check fixture suite',
    'Handoff wave-2 fixture suite',
    'Decision watch fixture suite',
    'Reply judge fixture suite',
    'Prose judge fixture suite',
    'SendMessage state fixture suite',
    'Refusal note fixture suite',
    'Refusal note agent row suite',
    'Refusal note route row suite',
    'Call judge fixture suite',
    'Question form fixture suite',
    'Question form option-key gap suite',
    'Question form option-label suite',
    'Question form letters-frozen suite',
    'Remove-prompt answer fixture suite',
    'Agent brief fixture suite',
    'Blind brief fixture suite',
    'Local time line fixture suite',
    'Guard probe helper fixture suite',
    'CI wake-up fixture suite',
    'Feedback inbox fixture suite',
    'Waiting export check suite',
    'Daily note fixture suite',
    'Git mailbox suite',
    'Git mailbox wait suite',
    'No-window helper fixture suite',
    'Auto-mode allow entry suite',
    'Stall watch fixture suite',
    'Stall watch stop suite',
    'Simulator boot-record fixture suite',
    'Guard wrappers fixture suite',
    'Deny checks never raise suite',
    'Session start notice suite',
    'Directory before a segment suite',
    'Refusal settle fixture suite',
    'Stop-hook guard fixture suite',
    'Stop-hook triage hold suite',
    'Stop-hook question route suite',
    'Stop-hook page writer suite',
    'Stop-hook stamped copy suite',
    'Stop-hook route row falsifier suite',
    'Stop-hook hand-off cite suite',
    'Clause parser suite',
    'Stop-hook cannot-claim suite',
    'Stop-hook landing fixture suite',
    'Stop-hook owner-safe reason suite',
    'Stop-hook review-record fixture suite',
    'STE auto-fix fixture suite',
    'Ruling home fixture suite',
    'Scratchpad owner fixture suite',
    'Ruling census fixture suite',
    'Rule audit fixture suite',
    'Stale prose check fixture suite',
    'Ruled store fixture suite',
    'Route judge measure fixture suite',
    'Guard log report fixture suite',
    'Verdict runner fixture suite',
    'Wait-pid helper fixture suite',
    'Wait-until helper fixture suite',
    'Now-central helper fixture suite',
    'sim-lease fixture suite',
    'Fixture copy helper suite',
    'Test-run signing opt-out fixture suite',
    'Debt notes union merge fixture suite',
    'Job runner fixture suite (bin/ci-job)',
    'Rule mechanization audit',
    'Windows split guard',
    'all-jobs-passed needs every pull-request job',
    'Scope detector fixture suite',
    'Touched-test selector fixture suite',
    'rm shim fixture suite',
    'Mutation verdict fixture suite',
    'Mutation report-mode fixture suite',
    'Mutation JS engine fixture suite',
    'Mutation replay fixture suite',
    'Mutation CI report fixture suite',
    'Landed-directory check fixture suite',
    'Settings matcher fixture suite',
    'Hook platform exit fixture suite',
    'Hook stub fixture suite',
    'Hook dup-name fixture suite',
    'Record slug fixture suite',
    'Cost line pin fixture suite',
    'Red-run trailer fixture suite',
    'Plan refuter fixture suite',
    'Copy finder fixture suite',
    'Time-pinned finder fixture suite',
    'Mod version fixture suite',
    'Hook catalog fixture suite',
    'Hook catalog check',
    'Hook stub check',
    'Hook dup-name check',
    'Record slug length',
    'Cost line pins',
    'Red-run trailer',
    'Plan refuter line',
    'Map check',
    'Layout fixture suite',
    'Label once fixture suite',
    'Repo colour fixture suite',
    'Retired repo fixture suite',
    'Waiting page staleness fixture suite',
    'Waiting page splice fixture suite',
    'Waiting page grant check suite',
    'Waiting page grant answer-label suite',
    'Waiting page grant held suite',
    'Waiting page question source suite',
    'Waiting page park relay prose suite',
    'Artifact cite fixture suite',
    'Artifact cite check',
    'Roadmap builder fixture suite',
    'Layout readers hold no record path',
    'Shared resource declaration fixture suite',
    'Shared resource declaration check',
    'iPhone mockup check fixture suite',
    'Compliance probes fixture suite',
    'CLAUDE.md size fixture suite',
    'CLAUDE.md size (warns, never fails)',
    'Glossary fixture suite',
    'Glossary homes and avoided names',
    'Retired names, one word per meaning',
    'project-ops skill scaffold suite',
    'ios-apps skill starter suite',
    'Mod version bump',
    'Ruling kind fixture suite',
    'Ruling kind check',
    'Silent undo fixture suite',
    'Debt retire fixture suite',
    'Silent undo check',
    'Comment narration fixture suite',
    'Comment narration check',
    'Unknown-read contract fixture suite',
    'Unknown-read contract (guard + session_start)',
    'Landed-directory manifest agreement',
    'Agent and skill model floor',
    'Agent and skill model floor fixture suite',
    'Agent push form fixture suite',
    'Skill model rows check',
    'Skill model rows fixture suite',
    'Python 3.9 floor check',
    'Python 3.9 floor fixture suite',
    'No-window spawn check',
    'PowerShell syntax check, install.ps1',
    'Pointer encoding test, install.test.ps1',
    'STE lint',
    'STE lint action fixture suite',
    'Playwright setup action suite',
    'Record stamp engine fixture suite',
    'Scanner trap lint',
    'Record stamp action fixture suite',
    'Opt-in CI template fixture suites',
    'Mod and map-skill tests',
    'Checks step scope suite',
]

# Each entry file that names a tracked .md file, with the names and one reason. A name here is written into a temp
# folder or repo, named in a comment, or a hook's payload: it is not read from the repo. A new name in a gated entry
# turns the guard red; so does a listed name the file no longer names.
ALLOWED = {
    "actions/stamp/test_stamp.mjs": (["CLAUDE.md", "README.md"], "written into each case's temp root"),
    "hooks/test_call_judge.py": (["README.md", "docs/design/last-answer-notes.md"], "README.md is written into a temp repo; the other name is in comments"),
    "hooks/test_checks_never_raise.py": (["CLAUDE.md"], "written into a temp CLAUDE_CONFIG_DIR"),
    "hooks/test_decision_watch.py": (["CLAUDE.md", "decisions/reply-judge-samples-never-refuses.md"], "CLAUDE.md is written into temp repos; the record name is in a comment"),
    "hooks/test_feedback_inbox.py": ([".claude/CLAUDE.md", "CLAUDE.md", "README.md", "docs/todo.md"], "fixture repos track or write these names in temp dirs"),
    "hooks/test_mutate_replay.py": (["README.md"], "the base file of each temp repo"),
    "hooks/test_prose_judge.py": (["README.md", "decisions/test-strategy-reset.md"], "a hook payload's file path and edit text"),
    "hooks/test_question_form_letters_frozen.py": (["docs/decisions/option-keys-are-letters.md"], "named in the module docstring"),
    "hooks/test_session_start.py": ([".claude/CLAUDE.md", "CLAUDE.md"], "written into temp config and checkout dirs"),
    "hooks/test_waiting_export.py": (["README.md"], "a fixture tool result line"),
    "lint/check_python_floor.py": (["README.md"], "named in the module docstring; the check does not open it"),
    "lint/test_check_claude_md_size.py": ([".claude/CLAUDE.md", "CLAUDE.md"], "written into a temp tree"),
    "lint/test_check_hook_stubs.py": (["README.md"], "committed into temp git repos"),
    "lint/test_check_record_slugs.py": (["debts/README.md", "debts/notes.md"], "folder files the check skips, named as constants"),
    "lint/test_check_skill_model_rows.py": (["decisions/agent-model-cap.md"], "the record path is a name in a temp tree"),
    "lint/test_ci_job.py": (["AGENTS.md", "CLAUDE.md"], "written into temp roots"),
    "lint/test_ci_scope.py": ([
        "README.md", "reference/copies-and-accounts.md", "reference/repo-pages.md", "skills/ci-hygiene/SKILL.md",
        "skills/waiting-page/SKILL.md", "skills/waiting-page/reference/copies-and-accounts.md",
        "skills/waiting-page/reference/designs.md", "skills/waiting-page/reference/repo-pages.md",
        "skills/waiting-page/reference/republish.md", "skills/waiting-page/reference/routing-and-sessions.md",
        "tests/fixture/docs/map/core.md", "tests/fixture/docs/map/traces/home.md",
    ], "paths that run() commits into temp git repos"),
    "lint/test_find_copies.py": ([
        ".github/pull_request_template.md", "reference/document.md", "skills/impeccable/SKILL.md",
        "skills/impeccable/reference/document.md", "skills/plain-english-map/SKILL.md",
    ], "written into the temp tree by make_parent"),
    "lint/test_notes_union_merge.py": (["docs/catalog.md", "docs/debts/notes.md", "docs/records.md"], "merge fixtures in temp repos"),
    "lint/test_report_guard_stalled.py": (["skills/roadmap/SKILL.md"], "a command in a fixture transcript"),
    "lint/test_ruled_store.py": (["README.md"], "a fixture file in make_repo"),
    "lint/test_sim_lease.py": (["decisions/test-temp-standard.md"], "named in the module docstring"),
    "lint/test_touched_tests.py": (["README.md", "skills/plain-english-map/SKILL.md"], "fixture docs and a path given to the selector"),
    "skills/roadmap/test_build.py": (["README.md", "docs/todo.md"], "fixture repo files"),
    "skills/waiting-page/test_stale_pages.py": (["CLAUDE.md"], "written into a temp claude folder"),
}

ENTRY = re.compile(r"(?:^|[\s;&|(])(?:python3?|bash|node)\s+(?!-)([^\s'\"]+)", re.M)
MD_TOKEN = re.compile(r"[\w.\-/]*\.md\b")


def read_repo(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def value(st, key):
    v = ws.step_key(st, key)
    return None if v is None else ws.drop_comment(v)


def identity(st):
    name = value(st, "name")
    return name if name is not None else "uses: " + value(st, "uses")


def if_of(st):
    return value(st, "if")


def checks_steps():
    """The checks job's steps, or None when the workflow has no checks job."""
    block = ws.job_block(read_repo(WORKFLOW), JOB)
    return None if block is None else ws.step_blocks(block)


def runs_on_pull_request_with(st, code):
    """True when the step runs on a pull request whose scope `code` flag is `code` (every scope output set alike)."""
    expr = if_of(st)
    return True if expr is None else eval_if(expr, "pull_request", code)


def entries(st):
    """The python3, bash or node files a step runs, in order."""
    return ENTRY.findall(ws.run_body(st) or "")


def tracked_md():
    out = subprocess.run(["git", "ls-files", "*.md"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return out.split()


def md_names_reached(text, tracked):
    """The tokens of `text` that name a tracked .md file: the same path, or a path that ends in one. A name written
    whole is seen; a name split across arguments, such as os.path.join(root, "docs", "x.md"), is not."""
    reached = set()
    for tok in MD_TOKEN.findall(text):
        for name in tracked:
            if tok == name or ("/" in tok and name.endswith("/" + tok)):
                reached.add(tok)
                break
    return reached


def gated_steps(steps):
    """(identity, step) for each step the entry guard covers: the audit's NO-MD and NAMES-ONLY steps, and any other step
    that carries the gate. A named step missing from the job is left out here; the gate test reports it."""
    by_id = {identity(st): st for st in steps}
    names = NO_MD + NAMES_ONLY
    found = [(n, by_id[n]) for n in names if n in by_id]
    found += [(identity(st), st) for st in steps if if_of(st) == GATE and identity(st) not in names]
    return found


class ChecksStepBase(unittest.TestCase):
    def steps(self):
        steps = checks_steps()
        self.assertIsNotNone(steps, "%s has no `%s` job" % (WORKFLOW, JOB))
        return steps

    def named(self, steps, name):
        for st in steps:
            if identity(st) == name:
                return st
        self.fail("step %r is not in the %s job" % (name, JOB))


class GateOnNoMdSteps(ChecksStepBase):
    def test_each_no_md_and_names_only_step_carries_the_gate(self):
        steps = self.steps()
        for name in NO_MD + NAMES_ONLY:
            with self.subTest(step=name):
                got = if_of(self.named(steps, name))
                self.assertEqual(got, GATE, "step %r: if is %r, want the scope gate" % (name, got))


class UngatedAndPrOnlySteps(ChecksStepBase):
    def test_each_must_stay_ungated_step_reads_no_scope_output(self):
        steps = self.steps()
        for name in MUST_STAY_UNGATED:
            with self.subTest(step=name):
                expr = if_of(self.named(steps, name)) or ""
                self.assertNotIn("needs.scope.outputs", expr, "step %r is gated on a scope output: %r" % (name, expr))

    def test_each_pr_only_step_keeps_its_pull_request_if(self):
        steps = self.steps()
        for name in PR_ONLY:
            with self.subTest(step=name):
                got = if_of(self.named(steps, name))
                self.assertEqual(got, PR_ONLY_IF, "step %r: if is %r, want its pull-request if" % (name, got))


class StepNames(ChecksStepBase):
    def test_the_checks_job_has_main_step_names(self):
        got = sorted(identity(st) for st in self.steps())
        self.assertEqual(got, sorted(MAIN_STEPS), "the checks job's step names differ from main's")

    def test_each_hard_coded_list_names_a_main_step(self):
        for name in NO_MD + NAMES_ONLY + MUST_STAY_UNGATED + PR_ONLY:
            with self.subTest(step=name):
                self.assertIn(name, MAIN_STEPS, "a pinned list names a step main does not have")

    def test_no_step_is_on_two_lists(self):
        listed = NO_MD + NAMES_ONLY + MUST_STAY_UNGATED + PR_ONLY
        twice = sorted({n for n in listed if listed.count(n) > 1})
        self.assertEqual(twice, [], "a step is on two pinned lists")


class DocsOnlyPullRequest(ChecksStepBase):
    def test_a_decision_doc_change_leaves_code_false(self):
        got = scope_run([DOC])
        self.assertEqual(got["code"], "false", "a docs-only change set code: %r" % got)

    def test_every_gated_step_skips_on_that_pull_request(self):
        got = scope_run([DOC])
        self.assertEqual(got["code"], "false", "a docs-only change set code: %r" % got)
        steps = self.steps()
        for name in NO_MD + NAMES_ONLY:
            with self.subTest(step=name):
                self.assertFalse(runs_on_pull_request_with(self.named(steps, name), got["code"]),
                                 "step %r still runs on a docs-only pull request" % name)

    def test_ste_lint_stays_ungated_so_it_runs_on_that_pull_request(self):
        got = scope_run([DOC])
        self.assertEqual(got["code"], "false", "a docs-only change set code: %r" % got)
        st = self.named(self.steps(), STE_LINT)
        self.assertTrue(runs_on_pull_request_with(st, got["code"]), "STE lint is gated: if %r" % if_of(st))


class MdNamesInText(unittest.TestCase):
    TRACKED = ["CLAUDE.md", "README.md", "docs/decisions/x.md", ".claude/CLAUDE.md"]

    def test_a_whole_tracked_path_in_a_string_is_reached(self):
        text = 'open(os.path.join(ROOT, "docs/decisions/x.md"))'
        self.assertEqual(md_names_reached(text, self.TRACKED), {"docs/decisions/x.md"})

    def test_a_suffix_path_reaches_the_tracked_file_it_ends(self):
        self.assertEqual(md_names_reached('write("decisions/x.md")', self.TRACKED), {"decisions/x.md"})

    def test_a_name_after_a_hash_inside_a_string_is_reached(self):
        self.assertEqual(md_names_reached('label = "# README.md"', self.TRACKED), {"README.md"})

    def test_a_name_on_a_later_line_of_a_template_literal_is_reached(self):
        text = "const t = `\nRead the rules in\nCLAUDE.md\n`;\n"
        self.assertEqual(md_names_reached(text, self.TRACKED), {"CLAUDE.md"})

    def test_a_lone_quote_in_text_does_not_hide_a_name(self):
        self.assertEqual(md_names_reached("Don't read CLAUDE.md first", self.TRACKED), {"CLAUDE.md"})

    def test_a_dotted_claude_path_is_its_own_name(self):
        self.assertEqual(md_names_reached('"(.claude/CLAUDE.md)"', self.TRACKED), {".claude/CLAUDE.md"})

    def test_an_untracked_name_is_not_reached(self):
        self.assertEqual(md_names_reached('open("missing.md")', self.TRACKED), set())

    def test_empty_text_and_empty_tracked_list_reach_nothing(self):
        self.assertEqual(md_names_reached("", self.TRACKED), set())
        self.assertEqual(md_names_reached('"CLAUDE.md"', []), set())

    def test_every_tracked_name_is_reached_at_full_size(self):
        tracked = tracked_md()
        self.assertTrue(tracked, "git ls-files lists no .md file")
        text = "\n".join('"%s"' % name for name in tracked)
        self.assertEqual(md_names_reached(text, tracked), set(tracked))


class GatedEntriesNameNoUnlistedMd(ChecksStepBase):
    def test_each_gated_entry_names_no_tracked_md_file_it_does_not_list(self):
        steps = self.steps()
        tracked = tracked_md()
        for name, st in gated_steps(steps):
            with self.subTest(step=name):
                files = entries(st)
                self.assertTrue(files, "step %r runs no python3, bash or node file the guard can read" % name)
                for entry in files:
                    with self.subTest(entry=entry):
                        self.assertTrue(os.path.isfile(os.path.join(ROOT, entry)), "%s is not a file" % entry)
                        listed = set(ALLOWED.get(entry, ([], ""))[0])
                        extra = sorted(md_names_reached(read_repo(entry), tracked) - listed)
                        self.assertEqual(extra, [], "%s names a tracked .md file that ALLOWED does not list" % entry)

    def test_each_allowance_is_gated_and_still_names_its_file(self):
        steps = self.steps()
        tracked = tracked_md()
        gated = {entry for _, st in gated_steps(steps) for entry in entries(st)}
        for entry, (names, reason) in ALLOWED.items():
            with self.subTest(entry=entry):
                self.assertIn(entry, gated, "%s is allowed, but no gated step runs it" % entry)
                stale = sorted(set(names) - md_names_reached(read_repo(entry), tracked))
                self.assertEqual(stale, [], "%s no longer names %s: drop those names from ALLOWED" % (entry, stale))


if __name__ == "__main__":
    unittest.main()
