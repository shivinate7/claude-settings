"""Pins the scope condition on the `checks` job's steps (lane ci-skip-untouched-steps, slice 2).

ci-scope.sh sets `code` false for a change that touches only .md files. A step that reads no .md file takes the scope condition
`needs.scope.outputs.code == 'true'`, with no event fallback, so a docs-only pull request skips it, and so does a push whose flag is
false. A step that reads a .md file stays unscoped. The step lists are the audit of main's checks.yml when this was written, by step name.

Pinned here:
  1. each NO-MD and NAMES-ONLY step carries the scope condition, exactly.
  2. each MUST-STAY-UNSCOPED step has no scope output in its `if:`, and each PR-only step keeps its own `if:`.
  3. each MAIN_STEPS name is a step of the checks job (no rename or drop), and a step outside MAIN_STEPS reads no scope output.
  4. a docs-only pull request leaves `code` false, skips each scoped step, and leaves STE lint running.
     The fail-safe flags are not repeated: lint/test_ci_scope.py pins them in Scope.test_push_schedule_and_dispatch_run_everything_even_for_docs,
     Scope.test_unreadable_diff_runs_everything, and Scope.test_merge_change_turns_the_merge_job_on (a .py change sets code).
  5. the entry file of each scoped step names no tracked .md file, unless ALLOWED lists that name with a reason.
  6. no file a scoped step reaches within TRANSITIVE_DEPTH hops reads test_guard.py or a tracked .md file
     (TRANSITIVE_MD_READERS), unless TRANSITIVE_ALLOWED lists that name for the file with a reason.
  7. each doc step (DOC_STEPS) carries the scope condition of its doc groups, one constant per group set, and the .md names
     its entry names are under a doc flag its `if:` reads (ALLOWED names aside).
  8. a docs-only change runs exactly the doc steps that list its group, or `any`, with no other step's change.

Steps are read by lint/workflow_steps.py. The `if:` evaluator is eval_if in lint/test_windows_split.py.
Item 5 reads the entry file only. Item 7 reads each name as md_names_reached reads it: a whole path, or the constant
arguments of an os.path.join, so join(ROOT, "docs", "decisions", "x.md") reads docs/decisions/x.md. A leading `..` segment
is folded, so join(HERE, "..", "docs", "x.md") reads docs/x.md. A join through pathlib `/` or an f-string is not read: a
stated limit. Item 6 follows imports
and read calls (open, run, join and the like), so a read one or two files down is seen. A comment names nothing in Python.
"""
import ast
import os
import posixpath
import re
import subprocess
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import workflow_steps as ws  # noqa: E402  the one home of the step parser
from test_ci_scope import DOC_CASES, DOC_FLAGS, doc_groups, run as scope_run  # noqa: E402  ci-scope.sh run in a temp repo, and the doc groups
from test_windows_split import (  # noqa: E402  the one home of the `if:` evaluator, the scope conditions and the doc condition builder
    NO_MD_SCOPE_CONDITION, SCOPE_DOC_AGENTS, SCOPE_DOC_ANY, SCOPE_DOC_DECISIONS, SCOPE_DOC_DECISIONS_MAP_OTHER, SCOPE_DOC_DECISIONS_OTHER,
    SCOPE_DOC_DECISIONS_RULES, SCOPE_DOC_DECISIONS_RULES_OTHER, SCOPE_DOC_RULES, SCOPE_DOC_SKILLS, SCOPE_DOC_SKILLS_AGENTS,
    SCOPE_DOC_SKILLS_DECISIONS, SCOPE_DOC_SKILLS_OTHER, doc_scope_condition, drop_condition, eval_if, keep_running_off, run_lines, unwrap,
    LINUX_SUITES)
from test_windows_split import PUSH_RULING, top_level_conjuncts, top_level_disjuncts, yaml_scalar  # noqa: E402  the one home of the splitters, the scalar reader and the ruling

ROOT = os.path.normpath(os.path.join(HERE, ".."))
WORKFLOW = ".github/workflows/checks.yml"
JOB = "checks"
SPLIT_JOBS = ("checks", "checks-hooks", "checks-rest")  # the old checks job split into these three; the rest of CHECKS_SUITE_JOBS were never part of it
SCOPE_CONDITION = "${{ %s }}" % NO_MD_SCOPE_CONDITION
PR_ONLY_IF = "${{ github.event_name == 'pull_request' }}"
# The same if, narrowed by one lint flag that ci-scope.sh sets (step ci-skip-untouched-steps slice 1).
PR_ONLY_LINT_IF = re.compile(r"^\$\{\{ github\.event_name == 'pull_request' && needs\.scope\.outputs\.lint_\w+ == 'true' \}\}$")
STE_LINT = "STE lint"
DOC = "docs/decisions/x.md"
# The Linux jobs whose steps a push run reads: the checks job and its split, and the guard and shoot jobs. The mutate-guard jobs and
# mutation-report stay out: their job-level `if:` skips every push (`github.event_name != 'push'`), so no push run reads a step of theirs.
LINUX_SUITE_JOBS = ("checks", "checks-hooks", "checks-rest", "checks-guard", "checks-guard-2", "checks-guard-3", "checks-guard-4",
                    "checks-shoot", "checks-waiting-page")
FALLBACK = "github.event_name != 'pull_request'"

# The audit's NO-MD steps: each reads no .md file at run time, so each takes the scope condition.
NO_MD = [
    'Config watch fixture suite',
    'Config watch fast-exit suite',
    'Claude Code compaction check fixture suite',
    'Decision watch fixture suite',
    'Prose judge fixture suite',
    'Refusal note fixture suite',
    'Refusal note agent row suite',
    'Refusal note route row suite',
    'Call judge fixture suite',
    'Question form option-key gap suite',
    'Question form option-label suite',
    'Question form letters-frozen suite',
    'Question form placeholder suite',
    'Remove-prompt answer fixture suite',
    'Local time line fixture suite',
    'CI wake-up fixture suite',
    'Feedback inbox fixture suite',
    'Waiting export check suite',
    'Page link check suite',
    'Git mailbox suite',
    'No-window helper fixture suite',
    'Tree export symlink fixture suite',
    'Auto-mode allow entry suite',
    'Stall watch fixture suite',
    'Stall watch stop suite',
    'Simulator boot-record fixture suite',
    'Start check suite',
    'Directory before a segment suite',
    'Refusal settle fixture suite',
    'Stop-hook triage hold suite',
    'Stop-hook question route suite',
    'Stop-hook placeholder suite',
    'Stop-hook page writer suite',
    'Stop-hook stamped copy suite',
    'Stop-hook route row falsifier suite',
    'Stop-hook hand-off cite suite',
    'Clause parser suite',
    'Stop-hook landing fixture suite',
    'Ruling home fixture suite',
    'Ruling census fixture suite',
    'Ruled store fixture suite',
    'Guard log report fixture suite',
    'Guard outcome claims fixture suite',
    'Verdict runner fixture suite',
    'Wait-pid helper fixture suite',
    'Wait-until helper fixture suite',
    'sim-lease fixture suite',
    'Fixture copy helper suite',
    'Test-run signing opt-out fixture suite',
    'Debt notes union merge fixture suite',
    'all-jobs-passed needs every pull-request job',
    'Scope detector fixture suite',
    'install.sh shard pins',
    'Touched-test selector fixture suite',
    'Mutation report-mode fixture suite',
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
    'Unknown-read contract fixture suite',
    'Python 3.9 floor check',
    'Playwright setup action suite',
    'Mutant anchor census',
    'Mutant anchor census fixture suite',
]

# The audit's NAMES-ONLY steps: each names a file, or copies only hooks/ and lint/ files, which already set `code`.
NAMES_ONLY = [
    'Windows split guard',
    'Hook stub check',
]

# The audit's MUST-STAY-UNSCOPED steps: each reads a .md file at run time, or is not audited yet (fail safe), so each stays unscoped.
# The doc steps are not listed here: DOC_STEPS below gives each one the scope condition of the doc groups it reads.
MUST_STAY_UNSCOPED = [
    'Skill model rows check',
    'Precompact handoff fixture suite',
    'Handoff wave-2 fixture suite',
    'Daily note fixture suite',
    'Layout fixture suite',
    'Mod version fixture suite',
    'Mod version bump',
    'Code check',
    'Workflow supply-chain audit (zizmor)',
    'Debt retire fixture suite',
    'Comment narration fixture suite',
    'Ruling kind fixture suite',
    'Checks step scope suite',  # names tracked .md files as data; a docs-only rename would turn main red if it carried the scope condition
    'Scratchpad owner fixture suite',  # runs test_guard.py, whose section files read skills/impeccable/SKILL.md
    'Guard wrappers fixture suite',  # runs test_guard.py through drive_test_guard
    'Skill model rows fixture suite',  # its checks job step has no `if:` (test_check_skill_model_rows.py pins it)
    'Project-ops roles check',  # reads the session-tiers record and the project-ops templates at run time (audit hook, run-time open)
    'Project-ops roles fixture suite',  # its real-repo case reads the same record and templates at run time
    'Reply judge fixture suite',  # reads CLAUDE.md at run time (hooks/test_reply_judge.py), so a CLAUDE.md-only pull request must run it
    'Nightly skip fixture suite',  # not audited yet, so it stays unscoped (fail safe)
    'Proc env read suite',  # not audited yet, so it stays unscoped (fail safe)
    'Stable workflow move job suite',  # not audited yet, so it stays unscoped (fail safe)
    'Hook stub fixture suite',  # copies hooks/precompact_handoff_prompt.md into its fixture tree (audit hook, run-time open)
    'Record slug fixture suite',  # copies hooks/precompact_handoff_prompt.md into its fixture tree (audit hook, run-time open)
    'Red-run trailer fixture suite',  # copies hooks/precompact_handoff_prompt.md into its fixture tree (audit hook, run-time open)
    'Shared names suite',  # copies hooks/precompact_handoff_prompt.md into its fixture tree (audit hook, run-time open)
    'Guard probe helper fixture suite',  # copies hooks/precompact_handoff_prompt.md into its fixture tree (audit hook, run-time open)
    'Job runner fixture suite (bin/ci-job)',  # copies hooks/precompact_handoff_prompt.md into its fixture tree (audit hook, run-time open)
    'Deny checks never raise suite',  # opens hooks/precompact_handoff_prompt.md at run time (audit hook, run-time open)
    'CLAUDE.md size fixture suite',  # opens CLAUDE.md at run time (audit hook, run-time open)
    'Mutation JS engine fixture suite',  # not audited: a multi-line, node or bash run that the in-process audit hook could not watch (fail safe)
    'Mutation replay fixture suite',  # not audited: a multi-line, node or bash run that the in-process audit hook could not watch (fail safe)
    'Mutation CI report fixture suite',  # not audited: a multi-line, node or bash run that the in-process audit hook could not watch (fail safe)
    'Record stamp engine fixture suite',  # not audited: a multi-line, node or bash run that the in-process audit hook could not watch (fail safe)
    'Scanner trap lint',  # not audited: a multi-line, node or bash run that the in-process audit hook could not watch (fail safe)
    'Record stamp action fixture suite',  # not audited: a multi-line, node or bash run that the in-process audit hook could not watch (fail safe)
]

# The doc steps. Each reads the doc groups listed (ci-scope.sh's doc_<group> flags), so its `if:` is the scope condition of those
# groups. A step whose read is wider than its groups, or not verified, takes ("any",): it runs on every docs-only pull request.
# Each entry script is read to pin its groups. Not pinned here, and left in MUST_STAY_UNSCOPED as on main:
#   'Mod version fixture suite' and 'Mod version bump': the map gives them code and doc_other, but their reads are mods/ paths.
#   'CLAUDE.md size fixture suite': the #3408 list keeps it unscoped on purpose (it opens CLAUDE.md at run time).
#   'Skill model rows check': its `if:` stays absent (test_check_skill_model_rows.py pins it).
DOC_STEPS = {
    # One group.
    'SendMessage state fixture suite': ("decisions",),
    'Stop-hook owner-safe reason suite': ("decisions",),
    'Settings matcher fixture suite': ("decisions",),
    'Session start notice suite': ("decisions",),  # its test class SessionStartRolePickTests reads docs/decisions/session-tiers.md
    'Stop-hook review-record fixture suite': ("rules",),
    'CLAUDE.md size (warns, never fails)': ("rules",),
    'Landed-directory manifest agreement': ("skills",),
    'project-ops skill scaffold suite': ("skills",),
    'ios-apps skill starter suite': ("skills",),
    'Agent brief fixture suite': ("agents",),
    # Several groups.
    'Blind brief fixture suite': ("skills", "agents"),
    'Git mailbox wait suite': ("skills", "decisions"),
    'Stop-hook cannot-claim suite': ("decisions", "rules"),  # its slug check stats docs/decisions/<id>.md (lint/report_guard.py _names_rule_id)
    'Rule audit fixture suite': ("decisions", "rules"),
    'Rule mechanization audit': ("decisions", "rules"),
    'Route judge measure fixture suite': ("decisions", "rules", "other"),
    'Landed-directory check fixture suite': ("skills", "decisions"),  # HelperHomeRecordTests reads the helper-home decision record
    'Artifact cite check': ("decisions", "other"),
    'Waiting page park relay prose suite': ("skills", "other"),
    'Map check': ("decisions", "map", "other"),  # reads the map pages and debt records; map.config.json sets no decisionsDir, so no decision record is read
    # Any .md: the read is wider than the groups above, or not verified.
    # lint/report_guard.py reaches hooks/question_form.py past_rulings, which opens docs/decisions and docs/debts; whether its verdict
    # depends on their content is unmeasured, so the step fails safe on every doc group.
    'Stop-hook guard fixture suite': ("any",),
    'Glossary homes and avoided names': ("any",),  # reads every home (decisions, rule anchors, agents, debts) and any .md path
    'Glossary fixture suite': ("any",),
    'STE lint': ("any",),
    'STE lint action fixture suite': ("any",),
    'Retired names, one word per meaning': ("any",),
    'Retired repo fixture suite': ("any",),
    'Record slug length': ("any",),
    'Cost line pins': ("any",),
    'Cost line pin fixture suite': ("any",),
    'Hook catalog fixture suite': ("any",),
    'Hook catalog check': ("any",),
    'Stale prose check fixture suite': ("any",),
    'Compliance probes fixture suite': ("any",),
    'Now-central helper fixture suite': ("any",),
    'Python 3.9 floor fixture suite': ("any",),
    'Silent undo fixture suite': ("any",),
    'Question form fixture suite': ("any",),
    'Agent and skill model floor': ("any",),
    'Agent and skill model floor fixture suite': ("any",),
    'Agent push form fixture suite': ("any",),
}

# One constant per distinct group set of DOC_STEPS (lint/test_windows_split.py builds each one from its groups).
SCOPE_OF = {
    frozenset(["any"]): SCOPE_DOC_ANY,
    frozenset(["decisions"]): SCOPE_DOC_DECISIONS,
    frozenset(["rules"]): SCOPE_DOC_RULES,
    frozenset(["skills"]): SCOPE_DOC_SKILLS,
    frozenset(["agents"]): SCOPE_DOC_AGENTS,
    frozenset(["skills", "agents"]): SCOPE_DOC_SKILLS_AGENTS,
    frozenset(["decisions", "rules"]): SCOPE_DOC_DECISIONS_RULES,
    frozenset(["decisions", "rules", "other"]): SCOPE_DOC_DECISIONS_RULES_OTHER,
    frozenset(["decisions", "other"]): SCOPE_DOC_DECISIONS_OTHER,
    frozenset(["decisions", "map", "other"]): SCOPE_DOC_DECISIONS_MAP_OTHER,
    frozenset(["skills", "other"]): SCOPE_DOC_SKILLS_OTHER,
    frozenset(["skills", "decisions"]): SCOPE_DOC_SKILLS_DECISIONS,
}
DOC_FLAG = re.compile(r"needs\.scope\.outputs\.doc_(\w+)")


def expected_if(groups):
    """The `if:` a doc step carries: the scope condition of its groups, as the workflow writes it. The one builder of that string."""
    return "${{ %s }}" % SCOPE_OF[frozenset(groups)]


def doc_flags_of(expr):
    """The doc groups an `if:` reads: the doc_<group> flags it names."""
    return set(DOC_FLAG.findall(expr or ""))


def tracked_groups(tok, tracked):
    """The doc groups of the tracked .md file a name stands for: the file itself, or each file the name is the end of."""
    full = [tok] if tok in tracked else [n for n in tracked if n.endswith("/" + tok)]
    return set().union(*[doc_groups(n) for n in full]) if full else set()


def doc_name_problems(entry, flags, text, tracked):
    """The .md names in an entry's text that no flag in `flags` covers, as "name (groups)". A name ALLOWED for the entry is
    written or named there, not read, so it is not counted. The `any` flag covers every name."""
    allowed = set(ALLOWED.get(entry, ([], ""))[0])
    problems = []
    for tok in sorted(md_names_reached(text, tracked) - allowed):
        groups = tracked_groups(tok, tracked)
        if "any" in flags or (groups - {"any"}) & flags:
            continue
        problems.append("%s (%s)" % (tok, ", ".join(sorted(groups - {"any"})) or "any only"))
    return problems


def runs_on(expr, flags):
    """Whether a step runs on a pull request whose output is `flags` (each doc flag and `code`; a flag it lacks reads 'false').
    A step with no `if:` runs."""
    if expr is None:
        return True
    e = re.sub(r"needs\.scope\.outputs\.(\w+) == 'true'", lambda m: "'%s' == 'true'" % flags.get(m.group(1), "false"), expr)
    return eval_if(e, "pull_request", "false")


# The steps that run only on a pull request, each with its own `if:`. The scope condition does not touch them.
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
    'Question form placeholder suite',
    'Remove-prompt answer fixture suite',
    'Agent brief fixture suite',
    'Blind brief fixture suite',
    'Local time line fixture suite',
    'Guard probe helper fixture suite',
    'CI wake-up fixture suite',
    'Feedback inbox fixture suite',
    'Waiting export check suite',
    'Page link check suite',
    'Daily note fixture suite',
    'Git mailbox suite',
    'Git mailbox wait suite',
    'No-window helper fixture suite',
    'Tree export symlink fixture suite',
    'Auto-mode allow entry suite',
    'Stall watch fixture suite',
    'Stall watch stop suite',
    'Proc env read suite',
    'Simulator boot-record fixture suite',
    'Guard wrappers fixture suite',
    'Deny checks never raise suite',
    'Session start notice suite',
    'Start check suite',
    'Directory before a segment suite',
    'Refusal settle fixture suite',
    'Stop-hook guard fixture suite',
    'Stop-hook triage hold suite',
    'Stop-hook question route suite',
    'Stop-hook placeholder suite',
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
    'Guard outcome claims fixture suite',
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
    'install.sh shard pins',
    'Touched-test selector fixture suite',
    'Nightly skip fixture suite',
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
    'Mutant anchor census',
    'Mutant anchor census fixture suite',
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
    'Guard-set lists (guardset4, guardset7, guardset8)',
    'Landed-directory manifest agreement',
    'Agent and skill model floor',
    'Agent and skill model floor fixture suite',
    'Agent push form fixture suite',
    'Skill model rows check',
    'Skill model rows fixture suite',
    'Project-ops roles check',
    'Project-ops roles fixture suite',
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
    'Stable workflow move job suite',
    'Opt-in CI template fixture suites',
    'Mod and map-skill tests',
    'Checks step scope suite',
]

# Each entry file that names a tracked .md file, with the names and one reason. A name here is written into a temp
# folder or repo, named in a comment, or a hook's payload: it is not read from the repo. A new name in a scoped entry
# turns the guard red; so does a listed name the file no longer names.
ALLOWED = {
    "hooks/test_agent_brief.py": (["debts/notes.md", "docs/debts/notes.md"], "the old notes file names the brief is compared against, in its text and in a temp cwd; neither file is opened"),
    "hooks/test_call_judge.py": (["README.md", "docs/design/last-answer-notes.md"], "README.md is written into a temp repo; the other name is in comments"),
    "hooks/test_decision_watch.py": (["CLAUDE.md", "decisions/reply-judge-samples-never-refuses.md"], "CLAUDE.md is written into temp repos; the record name is in a comment"),
    "hooks/test_feedback_inbox.py": ([".claude/CLAUDE.md", "CLAUDE.md", "README.md", "docs/debts/notes.md", "docs/notes/README.md", "docs/todo.md"], "fixture repos track or write these names in temp dirs; docs/notes/README.md is written into a temp repo, and the suite never reads the root copy; the frozen notes file is named by the case that checks the home judge refuses it"),
    "hooks/test_prose_judge.py": (["README.md", "decisions/test-strategy-reset.md"], "a hook payload's file path and edit text"),
    "hooks/test_question_form_letters_frozen.py": (["docs/decisions/option-keys-are-letters.md"], "named in the module docstring"),
    "hooks/test_session_start.py": ([".claude/CLAUDE.md", "CLAUDE.md"], "written into temp config and checkout dirs"),
    "hooks/test_page_link_check.py": (["README.md"], "the shared fixture writes it into a temp repo; it is never read"),
    "hooks/test_waiting_export.py": (["README.md"], "a fixture tool result line"),
    "lint/check_python_floor.py": (["README.md"], "named in the module docstring; the check does not open it"),
    "hooks/test_sendmessage_state.py": (["CLAUDE.md", "README.md"], "written into a temp CLAUDE_CONFIG_DIR and a temp repo"),
    "skills/project-ops/tests/test_scaffold.py": (["CLAUDE.md"], "written into temp folders; the scaffold's own file list names it"),
    "lint/test_all_jobs_passed.py": (["README.md"], "a changed path handed to the scope detector as a fixture; the file is never read"),
    "lint/test_ci_scope.py": ([
        "README.md", "reference/copies-and-accounts.md", "reference/repo-pages.md", "skills/ci-hygiene/SKILL.md",
        "CLAUDE.md", ".claude/CLAUDE.md", "AGENTS.md", "GLOSSARY.md", "output-styles/shiv-stylisms.md", "skills/waiting-page/SKILL.md",
        "skills/waiting-page/reference/copies-and-accounts.md",
        "skills/waiting-page/reference/designs.md", "skills/waiting-page/reference/repo-pages.md",
        "skills/waiting-page/reference/republish.md", "skills/waiting-page/reference/routing-and-sessions.md",
        "tests/fixture/docs/map/core.md", "tests/fixture/docs/map/traces/home.md", "docs/records.md",
        "agents/builder.md", "docs/decisions/agent-model-cap.md", "skills/impeccable/SKILL.md",
    ], "paths that run() commits into temp git repos, the doc-group cases' rule and glossary paths and the guard-inputs cases' three modified .md files included; the records-only skip "
       "fixtures name the generated page as the one file a records push changes; the file reads no tracked .md at run time"),
    "lint/test_find_copies.py": ([
        ".github/pull_request_template.md", "reference/document.md", "skills/impeccable/SKILL.md",
        "skills/impeccable/reference/document.md", "skills/plain-english-map/SKILL.md",
    ], "written into the temp tree by make_parent"),
    "lint/test_notes_union_merge.py": (["docs/catalog.md", "docs/debts/notes.md", "docs/records.md"], "merge fixtures in temp repos"),
    "lint/test_report_guard_stalled.py": (["skills/roadmap/SKILL.md"], "a command in a fixture transcript"),
    "lint/test_ruled_store.py": (["README.md"], "a fixture file in make_repo"),
    "lint/test_sim_lease.py": (["decisions/test-temp-standard.md"], "named in the module docstring"),
    "lint/test_touched_tests.py": (["README.md", "skills/plain-english-map/SKILL.md"], "fixture docs and a path given to the selector"),
    "skills/roadmap/test_build.py": (["README.md", "debts/notes.md", "docs/debts/notes.md", "docs/todo.md"],
                                     "fixture repo files, and the expected home and panel text of the notes cases; none is read from the repo"),
    "skills/waiting-page/test_stale_pages.py": (["CLAUDE.md"], "written into a temp claude folder"),
}

ENTRY = re.compile(r"(?:^|[\s;&|(])(?:python3?|bash|node)\s+(?!-)([^\s'\"]+)", re.M)
MD_TOKEN = re.compile(r"[\w.\-/]*\.md\b")
CODE_TOKEN = re.compile(r"[\w.\-/]*\.(?:py|sh|mjs)\b")
# A read a step's run makes: a call that runs a process, opens a file or joins a path. A name in its arguments is a read.
READ_CALLS = {"run", "call", "check_call", "check_output", "Popen", "system", "join", "open", "read_text", "read_bytes"}
TRANSITIVE_DEPTH = 3  # hops from a scoped entry; the entry is hop 0
TRANSITIVE_CAP = 200  # files one walk may reach; past it the reach is unknown, which fails
# A reader: a name for a read of a tracked .md file, or of test_guard.py. test_guard.py loads tests/guard/*.py, and one
# of those reads skills/impeccable/SKILL.md, so a step that reaches the runner reads a .md file at run time.
TRANSITIVE_MD_READERS = ["skills/impeccable/SKILL.md", "test_guard.py", "drive_test_guard", "tests/guard"]
# A reader named in a file that does not read it at run time, with one reason. The ALLOWED rule, for these names.
TRANSITIVE_ALLOWED = {
    "lint/test_ci_scope.py": (["test_guard.py"], "a changed path the scope detector is given; no file is run"),
    "hooks/guard.py": (["skills/impeccable/SKILL.md"], "impeccable_command_verbs opens it only when a command verb check runs; an in-process audit hook over the 83 scoped python suites saw no open (read 13:32 CST Nov 14; a suite's own child processes were not watched)"),
    "lint/rule_audit.py": (["test_guard.py"], "section_dir and _with_sections only parse hooks/test_guard.py and tests/guard/*.py as Python; nothing runs them or opens skills/impeccable"),
    "lint/test_rule_audit.py": (["test_guard.py", "tests/guard"], "builds its own hooks/test_guard.py and tests/guard fixture in a temp tree"),
    "lint/test_check_hook_dup_names.py": (["tests/guard"], "writes its own tests/guard fixture sections in a temp tree; the check parses them as Python and opens no .md"),
    "hooks/mutate_guard.py": (["test_guard.py"], "strace, round 1 review: no open of skills/impeccable at run time"),
    "hooks/test_mutate_ci.py": (["test_guard.py"], "strace, round 1 review: no open of skills/impeccable at run time"),
    "lint/check_unknown_reads_contract.py": (["test_guard.py"], "strace, round 1 review: no open of skills/impeccable at run time"),
}
# A shell or JS line that runs or reads something. A line without one (a case pattern, a comment) names no read.
INVOKE = re.compile(r"\b(python3?|node|bash|sh|source|cat|readFileSync|readFile|spawnSync|spawn|execFileSync|execFile|exec)\b")


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
    """A checks-job step's `if:` without its keep-running guard (keep_running_off, the one home of that strip)."""
    return keep_running_off(value(st, "if"))


def checks_steps():
    """The steps of the checks job and the two jobs it split into, or None when the workflow has no checks job."""
    text = read_repo(WORKFLOW)
    blocks = [ws.job_block(text, j) for j in SPLIT_JOBS]
    if blocks[0] is None:
        return None
    return [st for b in blocks if b is not None for st in ws.step_blocks(b)]


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


def folded_path(run):
    """The path a run of constant join arguments names. `.` and `..` segments fold, and a leading `..` is dropped: the repo's
    readers start in lint/ or hooks/, so join(HERE, "..", "docs", "x.md") names docs/x.md. "" when nothing is left."""
    p = posixpath.normpath("/".join(run))
    while p.startswith("../"):
        p = p[3:]
    return "" if p in (".", "..") else p


def split_join_names(text):
    """The paths that os.path.join builds from runs of constant arguments: join(ROOT, "docs", "x.md") is docs/x.md (folded_path).
    A non-constant argument ends a run. A join through pathlib `/` or an f-string is not read: a stated limit. Empty when
    `text` does not parse as Python: its joins are then read as text."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and callee(node) == "join":
            run = []
            for arg in node.args + [None]:  # None closes the last run
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    run.append(arg.value)
                    continue
                path = folded_path(run) if run else ""
                if path:
                    out.add(path)
                run = []
    return out


def md_names_reached(text, tracked):
    """The tokens of `text` that name a tracked .md file: the same path, or a path that ends in one. A name written
    whole is seen, and so is a path split across the constant arguments of os.path.join (split_join_names)."""
    reached = set()
    for tok in MD_TOKEN.findall(text) + sorted(split_join_names(text)):
        for name in tracked:
            if tok == name or ("/" in tok and name.endswith("/" + tok)):
                reached.add(tok)
                break
    return reached


def tracked_code():
    """The tracked .py, .sh and .mjs files: what a read can name."""
    out = subprocess.run(["git", "ls-files", "*.py", "*.sh", "*.mjs"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return out.split()


def name_index(code):
    """{base name: [paths]} of the code files."""
    index = {}
    for path in code:
        index.setdefault(os.path.basename(path), []).append(path)
    return index


def named_files(name, here, index):
    """The code files a name can mean: a path, or a path that ends in it (`name` has a `/`), else a file of that base name,
    the one in folder `here` first."""
    if "/" in name:
        return {p for paths in index.values() for p in paths if p == name or p.endswith("/" + name)}
    same = index.get(name, [])
    return set([p for p in same if os.path.dirname(p) == here] or same)


def callee(node):
    f = node.func
    return f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""


def read_strings(arg):
    """The strings inside one argument of a read call. An os.path.join of constants also counts as one string, so
    join(HERE, "tests", "guard") reads as tests/guard."""
    out = []
    for sub in ast.walk(arg):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            out.append(sub.value)
        elif isinstance(sub, ast.Call) and callee(sub) == "join":
            out.append("/".join(a.value for a in sub.args if isinstance(getattr(a, "value", None), str)))
    return out


def scan_file(rel, text, index):
    """(files reached, names read) for one file. A Python file is read with ast: its imports, and the strings and names
    of its read calls, so a comment or a docstring names nothing. Any other file, or a Python file that does not parse,
    is read line by line: an INVOKE line, not a comment. A name ALLOWED for the file reaches no file either."""
    here = os.path.dirname(rel)
    allowed = TRANSITIVE_ALLOWED.get(rel, ([], ""))[0]

    def targets(name):
        return set() if any(a in name for a in allowed) else named_files(name, here, index)

    tree = None
    if rel.endswith(".py"):
        try:
            tree = ast.parse(text)
        except SyntaxError:
            tree = None
    reaches, names = set(), []
    if tree is None:
        names = [ln for ln in text.splitlines() if INVOKE.search(ln) and not ln.lstrip().startswith(("#", "//"))]
    else:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    reaches |= targets(alias.name.split(".")[-1] + ".py")
            elif isinstance(node, ast.ImportFrom) and node.module:
                reaches |= targets(node.module.split(".")[-1] + ".py")
            elif isinstance(node, ast.Name):
                names.append(node.id)
            elif isinstance(node, ast.FunctionDef):
                names.append(node.name)
            elif isinstance(node, ast.Call) and callee(node) in READ_CALLS:
                for arg in node.args + [k.value for k in node.keywords]:
                    names.extend(read_strings(arg))
                if callee(node) != "join":
                    continue
            if isinstance(node, ast.Call) and callee(node) == "join":
                names.extend(read_strings(node))  # a join held in a constant and opened later still names its path
    for name in names:
        for token in CODE_TOKEN.findall(name):
            reaches |= targets(token)
    return reaches, names


def readers_in(rel, names):
    """The TRANSITIVE_MD_READERS names a file reads: its own path holds one, or one of its names does and TRANSITIVE_ALLOWED
    does not list it for the file."""
    allowed = TRANSITIVE_ALLOWED.get(rel, ([], ""))[0]
    return [m for m in TRANSITIVE_MD_READERS if m in rel or (m not in allowed and any(m in n for n in names))]


def walk_readers(entry, read_text, index, memo):
    """(hits, cut). hits holds (reader, file, chain) for each reader the entry reaches within TRANSITIVE_DEPTH hops, and
    cut is True when the walk stopped at TRANSITIVE_CAP files. read_text(rel) gives a file's text, or None when it is absent.
    memo caches each file's scan across the walks that share it."""
    chains = {entry: (entry,)}
    queue, hits = [entry], []
    while queue:
        rel = queue.pop(0)
        if rel not in memo:
            memo[rel] = scan_file(rel, read_text(rel) or "", index)
        reaches, names = memo[rel]
        hits += [(m, rel, chains[rel]) for m in readers_in(rel, names)]
        if len(chains[rel]) > TRANSITIVE_DEPTH:
            continue
        for nxt in sorted(reaches):
            if nxt not in chains:
                chains[nxt] = chains[rel] + (nxt,)
                queue.append(nxt)
        if len(chains) > TRANSITIVE_CAP:
            return hits, True
    return hits, False


def repo_text(rel):
    """A tracked file's text, or None when the file is absent."""
    return read_repo(rel) if os.path.isfile(os.path.join(ROOT, rel)) else None


def describe_hits(hits):
    return "; ".join("%s in %s, reached as %s" % (m, rel, " > ".join(chain)) for m, rel, chain in hits)


def scoped_steps(steps):
    """(identity, step) for each step the entry guard covers: the audit's NO-MD and NAMES-ONLY steps. A named step missing from the
    job is left out here; the scope condition test reports it. An unlisted step is no audit step even when its `if:` is the bare
    code flag: that form is also a flag-only step's, and the flag-only steps are not audited."""
    by_id = {identity(st): st for st in steps}
    names = NO_MD + NAMES_ONLY
    return [(n, by_id[n]) for n in names if n in by_id]


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


class ScopeConditionOnNoMdSteps(ChecksStepBase):
    def test_each_no_md_and_names_only_step_carries_the_scope_condition(self):
        steps = self.steps()
        checks = {identity(st) for st in ws.step_blocks(ws.job_block(read_repo(WORKFLOW), JOB))}
        for name in NO_MD + NAMES_ONLY:
            with self.subTest(step=name):
                got = if_of(self.named(steps, name))
                # Outside the checks job, the records-only condition may follow the scope condition: `${{ (SCOPE) && RECORDS_ONLY_CONDITION }}`.
                conditioned_ok = name not in checks and drop_condition(unwrap(got)) == NO_MD_SCOPE_CONDITION
                self.assertTrue(got == SCOPE_CONDITION or conditioned_ok,
                                "step %r: if is %r, want the scope condition with no event fallback (%s)" % (name, got, PUSH_RULING))


class UnscopedAndPrOnlySteps(ChecksStepBase):
    def test_each_must_stay_unscoped_step_reads_no_scope_output(self):
        steps = self.steps()
        for name in MUST_STAY_UNSCOPED:
            with self.subTest(step=name):
                expr = if_of(self.named(steps, name)) or ""
                self.assertNotIn("needs.scope.outputs", expr, "step %r reads a scope output in its if: %r" % (name, expr))

    def test_each_pr_only_step_keeps_its_pull_request_if(self):
        steps = self.steps()
        for name in PR_ONLY:
            with self.subTest(step=name):
                got = if_of(self.named(steps, name))
                self.assertTrue(got == PR_ONLY_IF or PR_ONLY_LINT_IF.match(got or ""),
                                "step %r: if is %r, want its pull-request if, with at most one lint_* flag" % (name, got))


class StepNames(ChecksStepBase):
    def test_each_main_step_name_is_in_the_checks_job(self):
        got = [identity(st) for st in self.steps()]
        for name in MAIN_STEPS:
            with self.subTest(step=name):
                self.assertIn(name, got, "pinned step %r is missing or renamed in the checks job" % name)

    def test_each_step_outside_main_steps_reads_no_scope_output(self):
        for st in self.steps():
            name = identity(st)
            if name in MAIN_STEPS:
                continue
            with self.subTest(step=name):
                expr = if_of(st) or ""
                self.assertNotIn("needs.scope.outputs", expr, "unlisted step %r reads a scope output: %r" % (name, expr))

    def test_each_hard_coded_list_names_a_main_step(self):
        for name in NO_MD + NAMES_ONLY + MUST_STAY_UNSCOPED + PR_ONLY + list(DOC_STEPS):
            with self.subTest(step=name):
                self.assertIn(name, MAIN_STEPS, "a pinned list names a step main does not have")

    def test_no_step_is_on_two_lists(self):
        listed = NO_MD + NAMES_ONLY + MUST_STAY_UNSCOPED + PR_ONLY + list(DOC_STEPS)
        twice = sorted({n for n in listed if listed.count(n) > 1})
        self.assertEqual(twice, [], "a step is on two pinned lists")


class DocsOnlyPullRequest(ChecksStepBase):
    def test_a_decision_doc_change_leaves_code_false(self):
        got = scope_run([DOC])
        self.assertEqual(got["code"], "false", "a docs-only change set code: %r" % got)

    def test_every_scoped_step_skips_on_that_pull_request(self):
        got = scope_run([DOC])
        self.assertEqual(got["code"], "false", "a docs-only change set code: %r" % got)
        steps = self.steps()
        for name in NO_MD + NAMES_ONLY:
            with self.subTest(step=name):
                self.assertFalse(runs_on_pull_request_with(self.named(steps, name), got["code"]),
                                 "step %r still runs on a docs-only pull request" % name)

    def test_ste_lint_runs_on_a_docs_only_pull_request_through_doc_any(self):
        got = scope_run([DOC])
        self.assertIn("doc_any", got, "output doc_any missing: %r" % got)
        st = self.named(self.steps(), STE_LINT)
        self.assertEqual(if_of(st), expected_if(("any",)), "STE lint: if is %r, want the doc_any scope condition" % if_of(st))
        self.assertTrue(runs_on(if_of(st), got), "STE lint does not run on a docs-only pull request: %r" % got)


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

    def test_a_path_split_across_join_arguments_is_reached(self):
        text = 'path = os.path.join(ROOT, "docs", "decisions", "x.md")\n'
        self.assertEqual(md_names_reached(text, self.TRACKED), {"docs/decisions/x.md"})

    # A parent segment at the front of a join: the repo's own reads climb from lint/ to the repo root this way.
    def test_a_join_through_a_parent_segment_is_reached(self):
        text = 'path = os.path.join(HERE, "..", "docs", "decisions", "x.md")\n'
        self.assertEqual(md_names_reached(text, self.TRACKED), {"docs/decisions/x.md"})

    # Control: a name between two constants ends the run, so the two pieces are not joined into a tracked path. The joined
    # path "docs/catalog.md" is tracked, so a run that is not reset (the over-join mutant) reaches it and goes red.
    def test_a_join_with_a_name_between_its_constants_joins_nothing(self):
        text = 'path = os.path.join("docs", SUB, "catalog.md")\n'
        self.assertEqual(md_names_reached(text, self.TRACKED + ["docs/catalog.md"]), set())

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


class ScopedEntriesNameNoUnlistedMd(ChecksStepBase):
    def test_each_scoped_entry_names_no_tracked_md_file_it_does_not_list(self):
        steps = self.steps()
        tracked = tracked_md()
        for name, st in scoped_steps(steps):
            with self.subTest(step=name):
                files = entries(st)
                self.assertTrue(files, "step %r runs no python3, bash or node file the guard can read" % name)
                for entry in files:
                    with self.subTest(entry=entry):
                        self.assertTrue(os.path.isfile(os.path.join(ROOT, entry)), "%s is not a file" % entry)
                        listed = set(ALLOWED.get(entry, ([], ""))[0])
                        extra = sorted(md_names_reached(read_repo(entry), tracked) - listed)
                        self.assertEqual(extra, [], "%s names a tracked .md file that ALLOWED does not list" % entry)

    def test_each_allowance_is_scoped_and_still_names_its_file(self):
        steps = self.steps()
        tracked = tracked_md()
        scoped = {entry for _, st in scoped_steps(steps) for entry in entries(st)}
        scoped |= {entry for name in DOC_STEPS for entry in entries(self.named(steps, name))}  # a doc step's ALLOWED names are not read
        for entry, (names, reason) in ALLOWED.items():
            with self.subTest(entry=entry):
                self.assertIn(entry, scoped, "%s is allowed, but no scoped step runs it" % entry)
                # A listed name no longer tracked was renamed or removed by the change; only names still in the repo are checked.
                listed = [n for n in names if n in tracked]
                stale = sorted(set(listed) - md_names_reached(read_repo(entry), tracked))
                self.assertEqual(stale, [], "%s no longer names %s: drop those names from ALLOWED" % (entry, stale))


class AllowanceNamesAfterAMove(unittest.TestCase):
    ENTRY = "hooks/test_call_judge.py"  # a scoped entry that ALLOWED lists with its names
    GONE = "docs/renamed-away-for-test.md"  # not tracked, as after a rename

    def failures_with(self, names):
        with mock.patch.dict(ALLOWED, {self.ENTRY: (names, "fixture")}):
            result = unittest.TestResult()
            ScopedEntriesNameNoUnlistedMd("test_each_allowance_is_scoped_and_still_names_its_file").run(result)
        return result.failures + result.errors

    def test_a_listed_name_no_longer_tracked_is_not_red(self):
        self.assertEqual(self.failures_with(ALLOWED[self.ENTRY][0] + [self.GONE]), [])

    def test_a_listed_name_still_tracked_but_unnamed_is_red(self):
        tracked = tracked_md()
        named = md_names_reached(read_repo(self.ENTRY), tracked)
        still = next(n for n in tracked if n not in named)
        failures = self.failures_with(ALLOWED[self.ENTRY][0] + [still])
        self.assertTrue(any(repr(still) in err for _, err in failures), "a tracked name the entry does not name is not red")


class TransitiveReaders(ChecksStepBase):
    def test_no_scoped_step_reaches_a_reader_of_a_md_file(self):
        steps = self.steps()
        index, memo = name_index(tracked_code()), {}
        for name, st in scoped_steps(steps):
            for entry in entries(st):
                with self.subTest(step=name, entry=entry):
                    hits, cut = walk_readers(entry, repo_text, index, memo)
                    self.assertFalse(cut, "the walk from %s passed %d files, so its reach is unknown" % (entry, TRANSITIVE_CAP))
                    self.assertEqual(hits, [], "step %r reads at run time: %s" % (name, describe_hits(hits)))

    def test_the_walk_sees_the_scratchpad_owner_reader(self):
        # A control: the walk is not blind to a reader it must catch (hooks/test_scratchpad_owner.py runs test_guard.py).
        hits, _ = walk_readers("hooks/test_scratchpad_owner.py", repo_text, name_index(tracked_code()), {})
        self.assertIn("test_guard.py", [m for m, _, _ in hits], "the walk does not see test_guard.py from its runner")


class TransitiveWalkFixtures(unittest.TestCase):
    def walk(self, files, entry="a/entry.py"):
        return walk_readers(entry, files.get, name_index(list(files)), {})

    def test_a_read_reached_through_an_import_is_a_hit(self):
        files = {"a/entry.py": "import helper\n",
                 "a/helper.py": "import os, subprocess\nsubprocess.run(['python3', os.path.join(HERE, 'test_guard.py')])\n",
                 "hooks/test_guard.py": "x = 1\n"}
        hits, _ = self.walk(files)
        self.assertIn("a/helper.py", [rel for _, rel, _ in hits], "the read in the imported file is not seen")

    def test_a_path_joined_into_a_constant_and_opened_later_is_a_hit(self):
        files = {"a/entry.py": "import helper\n",
                 "a/helper.py": "import os\nSKILL = os.path.join(HERE, '..', 'skills', 'impeccable', 'SKILL.md')\nopen(SKILL)\n"}
        hits, _ = self.walk(files)
        self.assertIn("a/helper.py", [rel for _, rel, _ in hits], "a path held in a constant is not seen")

    def test_a_read_three_hops_out_is_a_hit(self):
        files = {"a/entry.py": "import one\n", "a/one.py": "import two\n", "a/two.py": "import three\n",
                 "a/three.py": "import subprocess\nsubprocess.run(['python3', 'test_guard.py'])\n"}
        hits, _ = self.walk(files)
        self.assertIn("a/three.py", [rel for _, rel, _ in hits], "a read at the depth limit is not seen")

    def test_a_name_only_in_a_comment_is_not_a_read(self):
        files = {"a/entry.py": "# Do not run hooks/test_guard.py here, it's slow\nX = '#'\n"}
        self.assertEqual(self.walk(files)[0], [], "a comment that names the runner counts as a read")

    def test_a_comment_opener_inside_a_string_does_not_hide_a_read(self):
        files = {"a/entry.py": "LABEL = '# not a comment'\nsubprocess.run(['python3', 'hooks/test_guard.py'])\n"}
        self.assertEqual([m for m, _, _ in self.walk(files)[0]], ["test_guard.py"], "a read after a '#' string is not seen")

    def test_a_js_template_line_and_a_lone_quote_do_not_hide_a_read(self):
        files = {"a/entry.mjs": "const t = `\nspawnSync('node', ['hooks/test_guard.py'])\n`;\necho Don't run it; python3 hooks/test_guard.py\n"}
        self.assertEqual([m for m, _, _ in self.walk(files, entry="a/entry.mjs")[0]], ["test_guard.py"],
                         "a read on a template or a quoted line is not seen")

    def test_an_empty_file_reaches_and_reads_nothing(self):
        self.assertEqual(self.walk({"a/entry.py": ""}), ([], False))

    def test_a_walk_past_the_cap_says_its_reach_is_unknown(self):
        files = {"a/entry.py": "\n".join("import m%d" % i for i in range(TRANSITIVE_CAP + 1)) + "\n"}
        for i in range(TRANSITIVE_CAP + 1):
            files["a/m%d.py" % i] = "x = 1\n"
        self.assertTrue(self.walk(files)[1], "a walk past TRANSITIVE_CAP files reports no cut")

class WholeTreeReadersOnAModsChange(ChecksStepBase):
    """The whole-tree readers run on a mods-only pull request. A non-.md path under mods/ sets `code` (lint/test_ci_scope.py pins the
    flags), and each reader runs on `code` or a doc flag. Named failure: a mods-only change skips the retired-names, retired-repo,
    glossary and hook-catalog readers, which read every tracked file."""
    PATH = "mods/plain-diff/check.mjs"
    READERS = ("Retired repo fixture suite", "Retired names, one word per meaning", "Glossary homes and avoided names", "Hook catalog check")

    def test_each_whole_tree_reader_runs_on_a_mods_only_change(self):
        got = scope_run([self.PATH], existing=[self.PATH])
        self.assertEqual(got.get("mods"), "true", "the mods change did not set mods: %r" % got)
        # Scope first: which steps run means nothing without the flags. A mods-only change must set code, or these readers skip it.
        self.assertEqual(got.get("code"), "true", "the mods-only change does not set code, so the whole-tree readers skip it: %r" % got)
        steps = self.steps()
        for name in self.READERS:
            with self.subTest(step=name):
                self.assertTrue(runs_on(if_of(self.named(steps, name)), got), "step %r skips a mods-only change: %r" % (name, got))


class DocStepScopeConditions(ChecksStepBase):
    # A records-only push still runs each doc step, since each reads a .md file (decision records-index-at-merge).
    def test_each_doc_step_carries_the_scope_condition_of_its_groups(self):
        steps = self.steps()
        for name, groups in DOC_STEPS.items():
            with self.subTest(step=name):
                got = if_of(self.named(steps, name))
                self.assertEqual(got, expected_if(groups), "step %r: if is %r, want the scope condition of %s alone, with no event fallback (%s)"
                                 % (name, got, groups, PUSH_RULING))

    def test_each_doc_step_group_set_has_one_constant_built_from_its_groups(self):
        for groups in sorted({tuple(g) for g in DOC_STEPS.values()}):
            with self.subTest(groups=groups):
                self.assertIn(frozenset(groups), SCOPE_OF, "no constant for the groups %r" % (groups,))
        for key, constant in SCOPE_OF.items():
            with self.subTest(groups=sorted(key)):
                self.assertEqual(constant, doc_scope_condition(tuple(sorted(key))), "the constant is not built from its groups")


class DocStepEntriesReadOnlyTheirFlags(ChecksStepBase):
    def test_each_doc_step_entry_names_only_files_its_if_reads(self):
        steps, tracked = self.steps(), tracked_md()
        for name in DOC_STEPS:
            st = self.named(steps, name)
            flags = doc_flags_of(if_of(st))
            for entry in entries(st):
                with self.subTest(step=name, entry=entry):
                    problems = doc_name_problems(entry, flags, read_repo(entry), tracked)
                    self.assertEqual(problems, [], "%s names .md files its if: does not read: %s" % (name, ", ".join(problems)))

    def test_a_name_under_a_flag_the_if_does_not_read_is_reported(self):
        # Control: the Blind brief suite names a skill file, so a flag set without `skills` must report it.
        entry = "hooks/test_blind_brief.py"
        got = doc_name_problems(entry, {"agents"}, read_repo(entry), tracked_md())
        self.assertTrue(any(p.startswith("skills/design-explore/SKILL.md") for p in got), got)

    # Named failure: a decision record read through os.path.join arguments is not reported when the step's if does not read the
    # decisions group, so a docs-only edit to that record skips a step that reads it. The entry is in no ALLOWED list.
    def test_a_split_join_read_of_a_decision_record_is_reported_without_its_flag(self):
        entry = "fixture/split_read.py"
        text = 'import os\nROOT = "."\nRECORD = os.path.join(ROOT, "docs", "decisions", "x.md")\n'
        tracked = ["docs/decisions/x.md", "skills/a/SKILL.md"]
        self.assertEqual(doc_name_problems(entry, {"skills"}, text, tracked), ["docs/decisions/x.md (decisions)"],
                         "the split read of a decision record is not reported when the if reads only skills")

    # Control beside it: the same read is no problem once the if reads the decisions group.
    def test_a_split_join_read_of_a_decision_record_with_its_flag_is_no_problem(self):
        entry = "fixture/split_read.py"
        text = 'import os\nROOT = "."\nRECORD = os.path.join(ROOT, "docs", "decisions", "x.md")\n'
        tracked = ["docs/decisions/x.md", "skills/a/SKILL.md"]
        self.assertEqual(doc_name_problems(entry, {"decisions"}, text, tracked), [])


class DocStepsAgreeWithLinuxSplit(ChecksStepBase):
    def test_each_doc_step_run_in_the_linux_split_has_its_groups_condition(self):
        steps = self.steps()
        for name, groups in DOC_STEPS.items():
            for cmd in run_lines(self.named(steps, name)):
                if cmd not in LINUX_SUITES:
                    continue
                with self.subTest(step=name, cmd=cmd):
                    want = doc_scope_condition(tuple(groups))
                    self.assertEqual(LINUX_SUITES[cmd][0], want, "%r: row condition is %r, want %r (%s)" % (cmd, LINUX_SUITES[cmd][0], want, PUSH_RULING))


class DocsOnlyPullRequestSteps(ChecksStepBase):
    def assert_steps_run_by_groups(self, path):
        got = scope_run([path], existing=[path])
        for f in DOC_FLAGS:  # the flags come first: which steps run means nothing without them
            self.assertIn(f, got, "output %s missing for %s: %r" % (f, path, got))
        self.assertEqual(got["code"], "false", "%s set code: %r" % (path, got))
        steps = self.steps()
        ran = {name for name in DOC_STEPS if runs_on(if_of(self.named(steps, name)), got)}
        want = {name for name, groups in DOC_STEPS.items() if set(groups) & doc_groups(path)}
        self.assertEqual(sorted(ran), sorted(want), "%s: the doc steps that run are not the ones that list its groups" % path)

    def test_a_decision_doc_change_runs_exactly_the_steps_that_list_decisions_or_any(self):
        self.assert_steps_run_by_groups("docs/decisions/x.md")

    def test_each_doc_path_runs_exactly_the_steps_that_list_its_groups(self):
        for path, _ in DOC_CASES:
            with self.subTest(path=path):
                self.assert_steps_run_by_groups(path)

    # Named failure: a new decision record does not run the cannot-claim suite. Its slug check stats the record, so a record
    # that names a rule id (the pre-push-hook record) turns that suite's cannot-claim case red, and the step skipped it.
    def test_a_new_decision_record_runs_the_cannot_claim_suite(self):
        path = "docs/decisions/pre-push-hook.md"
        got = scope_run([path])
        self.assertEqual(got.get("doc_decisions"), "true", f"doc_decisions is not on for {path}: {got}")
        self.assertEqual(got.get("code"), "false", f"{path} set code: {got}")
        step = self.named(self.steps(), "Stop-hook cannot-claim suite")
        self.assertTrue(runs_on(if_of(step), got),
                        f"the cannot-claim suite skips a docs-only edit to {path}: its if is {if_of(step)!r}")

    # Named failure: a docs-only edit to the helper-home decision record skips the landed-dirs suite, which opens that record. The
    # flags are read first (P7): the record's decisions flag is on and code is off, then the step's `if:` decides.
    def test_a_docs_only_edit_to_the_helper_home_record_runs_the_landed_dirs_suite(self):
        path = "docs/decisions/builders-cannot-edit-tests.md"
        got = scope_run([path], existing=[path])
        self.assertEqual(got.get("doc_decisions"), "true", f"doc_decisions is not on for {path}: {got}")
        self.assertEqual(got.get("code"), "false", f"{path} set code: {got}")
        step = self.named(self.steps(), "Landed-directory check fixture suite")
        self.assertTrue(runs_on(if_of(step), got),
                        f"the landed-dirs suite skips a docs-only edit to {path}: its if is {if_of(step)!r}")

    # Control beside it: a docs-only edit to a doc that no skill or decision group holds skips the landed-dirs suite, as before.
    def test_a_docs_only_edit_outside_the_skill_and_decision_groups_skips_the_landed_dirs_suite(self):
        path = "docs/notes.md"
        got = scope_run([path], existing=[path])
        self.assertEqual(got.get("doc_other"), "true", f"doc_other is not on for {path}: {got}")
        self.assertEqual(got.get("code"), "false", f"{path} set code: {got}")
        step = self.named(self.steps(), "Landed-directory check fixture suite")
        self.assertFalse(runs_on(if_of(step), got), f"the landed-dirs suite runs for a docs-only edit to {path}: its if is {if_of(step)!r}")


# A failed step does not stop the later steps of the `checks` job. Every test and lint step runs, and the job ends red when any step
# failed. A step keeps running when `!cancelled()` is a top-level `&&` part of its `if:`,
# joined with its own condition. GitHub reads a step with no `if:` as success(), which stops at the first failure.
KEEP_RUNNING = "!cancelled()"
# The steps with no keep-running condition, by label: the checkout, which every later step needs, and setup-python, which every later
# step runs under. No other step is exempt: a step with no `if:` is skipped once an earlier step fails, and the steps that use its
# tools then fail for a missing tool. A label is the step's name, else `uses:` and its action path (no pin).
KEEP_RUNNING_EXEMPT = ("uses: actions/checkout", "uses: actions/setup-python")


def step_label(st):
    name = ws.step_key(st, "name")
    if name is not None:
        return yaml_scalar(name)
    uses = ws.step_key(st, "uses")
    return ("uses: " + yaml_scalar(uses).split("@")[0]) if uses is not None else "(no name, no uses)"


def keeps_running(expr):
    """True when a step's raw `if:` (or None, which GitHub reads as success()) has `!cancelled()` as a top-level `&&` part."""
    return KEEP_RUNNING in top_level_conjuncts(expr)


class KeepRunningAfterFailure(unittest.TestCase):
    """On checks.yml: every step of the `checks` job after the checkout and setup steps keeps running after a failure, and no
    step is allowed to go green past one (continue-on-error). Each case reads the real file."""

    def steps(self):
        block = ws.job_block(read_repo(WORKFLOW), JOB)
        self.assertIsNotNone(block, "%s has no `%s` job" % (WORKFLOW, JOB))
        return ws.step_blocks(block)

    def test_each_step_after_setup_carries_the_keep_running_condition(self):
        # Named failure: a step with no `if:`, or an `if:` without `!cancelled()` as a top-level part, stops at the first failed step.
        missing = [step_label(st) for st in self.steps()
                   if step_label(st) not in KEEP_RUNNING_EXEMPT and not keeps_running(ws.step_key(st, "if"))]
        self.assertEqual(missing, [], "%d step(s) of the %s job lack %s as a top-level part of their if:, so a failure stops them: %s"
                         % (len(missing), JOB, KEEP_RUNNING, missing))

    def test_no_step_of_the_checks_job_uses_continue_on_error(self):
        # Named failure: continue-on-error on a step, or on the job, lets a red step leave the job green.
        found = [step_label(st) for st in self.steps() if ws.step_key(st, "continue-on-error") is not None]
        self.assertEqual(found, [], "these steps set continue-on-error, so a red step leaves the job green: %s" % found)
        job_level = re.search(r"^    continue-on-error:", ws.job_block(read_repo(WORKFLOW), JOB), re.M)
        self.assertIsNone(job_level, "the %s job sets continue-on-error at job level, so a red step leaves it green" % JOB)

    def test_the_exemption_names_only_steps_of_the_checks_job_and_each_once(self):
        # Named failure: an exemption names no step of the job, so it is stale, or it repeats, so it is no one list.
        labels = [step_label(st) for st in self.steps()]
        stale = [n for n in KEEP_RUNNING_EXEMPT if n not in labels]
        self.assertEqual(stale, [], "these exempt labels name no step of the %s job: %s" % (JOB, stale))
        self.assertEqual(len(set(KEEP_RUNNING_EXEMPT)), len(KEEP_RUNNING_EXEMPT), "the exemption list repeats a label")

    def test_the_keep_running_reader_takes_only_a_top_level_conjunct(self):
        # Scanner cases (building-scanner-respects-strings): a comment opener or a doubled quote inside a string is text, and a
        # `!cancelled()` under an `||`, inside quotes, or with a lone quote before it is no keep-running condition.
        self.assertTrue(keeps_running("${{ !cancelled() }}"))
        self.assertTrue(keeps_running("${{ needs.scope.outputs.code == 'true' && !cancelled() }}"))
        self.assertTrue(keeps_running("${{ (a || b) && !cancelled() }}"))
        self.assertTrue(keeps_running("${{ x == '#' && !cancelled() }}"))
        self.assertTrue(keeps_running("${{ a == 'it''s' && !cancelled() }}"))
        self.assertFalse(keeps_running("${{ a || !cancelled() }}"))
        self.assertFalse(keeps_running("${{ x == '!cancelled()' }}"))
        self.assertFalse(keeps_running("${{ x == 'Don't' && !cancelled() }}"))
        self.assertFalse(keeps_running(None))


class CodeCheckToolsKeepRunning(unittest.TestCase):
    """F1, on checks.yml. The code-check tools step has no `if:`, so a failed step before it skips it, and the Code-check action after
    it reds for the missing tool. The exemption list holds only the checkout and setup steps."""

    steps = KeepRunningAfterFailure.steps

    def test_code_check_tools_carries_the_keep_running_condition(self):
        # Named failure: "Code-check tools" has no `if:`, so it does not keep running after a failed step.
        found = [st for st in self.steps() if step_label(st) == "Code-check tools"]
        self.assertEqual(len(found), 1, "the %s job has %d steps labelled Code-check tools, want one" % (JOB, len(found)))
        raw = ws.step_key(found[0], "if")
        self.assertTrue(keeps_running(raw), "Code-check tools does not keep running after a failed step: its if is %r" % raw)

    def test_each_exempt_step_is_the_checkout_or_a_setup_step(self):
        # Control: the two exempt steps are the checkout and a setup step, each one a step every later step needs.
        loose = [n for n in KEEP_RUNNING_EXEMPT
                 if not (n.startswith("uses: actions/checkout") or n.startswith("uses: actions/setup-"))]
        self.assertEqual(loose, [], "these exempt steps are neither the checkout nor a setup step: %s" % loose)


def fallback_steps(steps):
    """The identities of the steps whose `if:` has the event fallback as a top-level `||` term beside a term that reads a scope output."""
    found = []
    for st in steps:
        expr = if_of(st)
        if expr is None:
            continue
        terms = top_level_disjuncts(drop_condition(unwrap(expr)))  # the records-only conjunct comes off: `(E) && RECORDS_ONLY` reads E
        if FALLBACK in terms and any("needs.scope.outputs." in t for t in terms):
            found.append(identity(st))
    return found


class LinuxSuiteStepsObeyTheirFlag(unittest.TestCase):
    """The event fallback comes off each Linux suite step's `if:` (PUSH_RULING). A step whose flag is false is skipped on a push as on a
    pull request. ci-scope.sh turns every flag on for a push, so no push run changes its verdict."""

    def setUp(self):
        self.text = read_repo(WORKFLOW)

    def test_each_linux_suite_job_is_in_the_workflow_on_ubuntu(self):
        for job in LINUX_SUITE_JOBS:
            with self.subTest(job=job):
                block = ws.job_block(self.text, job)
                self.assertIsNotNone(block, "%s is not a job of %s, so the case reads none of its steps" % (job, WORKFLOW))
                self.assertRegex(block, r"(?m)^    runs-on: ubuntu-latest$", "%s is not an ubuntu job; the Linux case reads it" % job)

    def test_no_linux_suite_step_holds_the_event_fallback_beside_its_scope_flag(self):
        for job in LINUX_SUITE_JOBS:
            with self.subTest(job=job):
                got = fallback_steps(ws.step_blocks(ws.job_block(self.text, job)))
                self.assertEqual(got, [], "%s: these steps hold `%s` beside a scope flag, so a push runs them with the flag false (%s): %s"
                                 % (job, FALLBACK, PUSH_RULING, got))

    def test_a_step_whose_flag_is_false_is_skipped_on_a_push_as_on_a_pull_request(self):
        for job in LINUX_SUITE_JOBS:
            for st in ws.step_blocks(ws.job_block(self.text, job)):
                expr = if_of(st)
                if expr is None or "needs.scope.outputs." not in expr:
                    continue
                with self.subTest(job=job, step=identity(st)):
                    self.assertFalse(eval_if(expr, "pull_request", "false"), "%s: step %r runs on a pull request with its flag false: %r"
                                     % (job, identity(st), expr))
                    self.assertFalse(eval_if(expr, "push", "false"), "%s: step %r runs on a push with its flag false (%s): %r"
                                     % (job, identity(st), PUSH_RULING, expr))

    def test_the_windows_steps_stay_outside_the_case_and_keep_the_fallback(self):
        # Control: the case reads only the Linux suite jobs, and the Windows steps keep their fallback.
        for job in ("checks-windows", "checks-windows-rest"):
            with self.subTest(job=job):
                self.assertNotIn(job, LINUX_SUITE_JOBS)
                flagged = [st for st in ws.step_blocks(ws.job_block(self.text, job)) if "needs.scope.outputs." in (if_of(st) or "")]
                self.assertTrue(any(eval_if(if_of(st), "push", "false") for st in flagged),
                                "%s: no step runs on a push with its flag false, so the Windows fallback is gone; the ruling covers Linux only" % job)


class FallbackStepShapes(unittest.TestCase):
    """fallback_steps on one-job fixtures: the step shapes the case must tell apart. Each value is one `if:` as checks.yml writes it."""

    def flagged(self, *values):
        text = "".join("      - name: step %d\n        if: %s\n        run: echo %d\n" % (i, v, i) for i, v in enumerate(values))
        return fallback_steps(ws.step_blocks(text))

    def test_the_fallback_beside_a_flag_is_flagged(self):
        self.assertEqual(self.flagged("${{ needs.scope.outputs.code == 'true' || github.event_name != 'pull_request' }}"), ["step 0"])

    def test_the_fallback_inside_the_keep_running_pair_is_flagged(self):
        self.assertEqual(self.flagged("${{ !cancelled() && (needs.scope.outputs.code == 'true' || github.event_name != 'pull_request') }}"),
                         ["step 0"])

    def test_the_flag_alone_is_not_flagged(self):
        self.assertEqual(self.flagged("${{ !cancelled() && needs.scope.outputs.code == 'true' }}"), [])

    def test_a_fallback_with_no_scope_flag_is_not_flagged_here(self):
        # A step with no scope flag is the existing rules' case (ScopeConditionOnNoMdSteps and the MAIN_STEPS pins), not this one.
        self.assertEqual(self.flagged("${{ github.event_name != 'pull_request' }}"), [])

    def test_a_flag_and_not_pull_request_is_no_fallback(self):
        # On a push the flag decides this step, so it is no fallback.
        self.assertEqual(self.flagged("${{ needs.scope.outputs.code == 'true' && github.event_name != 'pull_request' }}"), [])

    def test_a_lone_quote_in_a_trailing_comment_does_not_hide_the_fallback(self):
        self.assertEqual(self.flagged("${{ needs.scope.outputs.code == 'true' || github.event_name != 'pull_request' }} # don't"), ["step 0"])

    def test_an_empty_job_has_no_fallback_step(self):
        self.assertEqual(fallback_steps(ws.step_blocks("")), [])

    def test_every_step_of_a_full_job_is_named(self):
        values = ["${{ needs.scope.outputs.code == 'true' || github.event_name != 'pull_request' }}"] * 40
        self.assertEqual(self.flagged(*values), ["step %d" % i for i in range(40)])


class KeepRunningTopLevelOr(unittest.TestCase):
    """F2. GitHub reads `!cancelled() && x || y` as `(!cancelled() && x) || y`, so a step with that condition runs after a failure
    through `y`. Only a `||` inside parentheses after the guard keeps the guard a top-level conjunct."""

    def test_a_top_level_or_after_the_guard_is_not_keep_running(self):
        # Named failure: keeps_running takes the guard as a conjunct of an `||` expression, so the step runs past a failure it should not.
        for expr in ("${{ !cancelled() && x || y }}",
                     "${{ !cancelled() && needs.scope.outputs.code == 'true' || github.event_name != 'pull_request' }}",
                     "${{ !cancelled() && a && b || c }}"):
            with self.subTest(expr=expr):
                self.assertFalse(keeps_running(expr), "keeps_running reads %r as keep-running, but GitHub reads its `||` at the top level" % expr)

    def test_a_parenthesised_or_after_the_guard_is_keep_running(self):
        # Control: the `||` inside parentheses is one condition, so the guard stays a top-level conjunct.
        for expr in ("${{ !cancelled() && (x || y) }}", "${{ !cancelled() && x && (y || z) }}"):
            with self.subTest(expr=expr):
                self.assertTrue(keeps_running(expr), "keeps_running does not keep %r running, but its `||` is inside parentheses" % expr)


if __name__ == "__main__":
    unittest.main()
