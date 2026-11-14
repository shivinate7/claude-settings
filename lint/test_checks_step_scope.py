"""Pins the scope condition on the `checks` job's steps (lane ci-skip-untouched-steps, slice 2).

ci-scope.sh sets `code` false for a change that touches only .md files. A step that reads no .md file takes the scope condition
`needs.scope.outputs.code == 'true' || github.event_name != 'pull_request'`, so a docs-only pull request skips it. A
step that reads a .md file stays unscoped. The step lists are the audit of main's checks.yml when this was written, by step name.

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

Steps are read by lint/workflow_steps.py. The `if:` evaluator is eval_if in lint/test_windows_split.py.
Item 5 reads the entry file only, and a name split across arguments is not seen. Item 6 follows imports and read
calls (open, run, join and the like), so a read one or two files down is seen. A comment names nothing in Python.
"""
import ast
import os
import re
import subprocess
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import workflow_steps as ws  # noqa: E402  the one home of the step parser
from test_ci_scope import run as scope_run  # noqa: E402  ci-scope.sh run in a temp repo: the one home of the scope run
from test_windows_split import NO_MD_SCOPE_CONDITION, eval_if  # noqa: E402  the one home of the `if:` evaluator and of the scope condition

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
    'ios-apps skill starter suite',
    'Unknown-read contract fixture suite',
    'Python 3.9 floor check',
    'Playwright setup action suite',
    'Record stamp engine fixture suite',
    'Scanner trap lint',
    'Record stamp action fixture suite',
]

# The audit's NAMES-ONLY steps: each names a file, or copies only hooks/ and lint/ files, which already set `code`.
NAMES_ONLY = [
    'Windows split guard',
    'Mutation replay fixture suite',
    'Mutation CI report fixture suite',
    'Hook stub check',
]

# The audit's MUST-STAY-UNSCOPED steps: each reads a .md file at run time, or is not audited yet (fail safe), so each stays unscoped.
MUST_STAY_UNSCOPED = [
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
    'Checks step scope suite',  # names tracked .md files as data; a docs-only rename would turn main red if it carried the scope condition
    'Scratchpad owner fixture suite',  # runs test_guard.py, whose section files read skills/impeccable/SKILL.md
    'Guard wrappers fixture suite',  # runs test_guard.py through drive_test_guard
    'Skill model rows fixture suite',  # its checks job step has no `if:` (test_check_skill_model_rows.py pins it)
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
]

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
    'Proc env read suite',
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
    'Stable workflow move job suite',
    'Opt-in CI template fixture suites',
    'Mod and map-skill tests',
    'Checks step scope suite',
]

# Each entry file that names a tracked .md file, with the names and one reason. A name here is written into a temp
# folder or repo, named in a comment, or a hook's payload: it is not read from the repo. A new name in a scoped entry
# turns the guard red; so does a listed name the file no longer names.
ALLOWED = {
    "actions/stamp/test_stamp.mjs": (["CLAUDE.md", "README.md"], "written into each case's temp root"),
    "hooks/test_call_judge.py": (["README.md", "docs/design/last-answer-notes.md"], "README.md is written into a temp repo; the other name is in comments"),
    "hooks/test_decision_watch.py": (["CLAUDE.md", "decisions/reply-judge-samples-never-refuses.md"], "CLAUDE.md is written into temp repos; the record name is in a comment"),
    "hooks/test_feedback_inbox.py": ([".claude/CLAUDE.md", "CLAUDE.md", "README.md", "docs/todo.md"], "fixture repos track or write these names in temp dirs"),
    "hooks/test_mutate_replay.py": (["README.md"], "the base file of each temp repo"),
    "hooks/test_prose_judge.py": (["README.md", "decisions/test-strategy-reset.md"], "a hook payload's file path and edit text"),
    "hooks/test_question_form_letters_frozen.py": (["docs/decisions/option-keys-are-letters.md"], "named in the module docstring"),
    "hooks/test_session_start.py": ([".claude/CLAUDE.md", "CLAUDE.md"], "written into temp config and checkout dirs"),
    "hooks/test_waiting_export.py": (["README.md"], "a fixture tool result line"),
    "lint/check_python_floor.py": (["README.md"], "named in the module docstring; the check does not open it"),
    "lint/test_all_jobs_passed.py": (["README.md"], "a changed path handed to the scope detector as a fixture; the file is never read"),
    "lint/test_ci_scope.py": ([
        "README.md", "reference/copies-and-accounts.md", "reference/repo-pages.md", "skills/ci-hygiene/SKILL.md",
        "CLAUDE.md", "output-styles/shiv-stylisms.md", "skills/waiting-page/SKILL.md", "skills/waiting-page/reference/copies-and-accounts.md",
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
    return value(st, "if")


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
    """(identity, step) for each step the entry guard covers: the audit's NO-MD and NAMES-ONLY steps, and any other step
    that carries the scope condition. A named step missing from the job is left out here; the scope condition test reports it."""
    by_id = {identity(st): st for st in steps}
    names = NO_MD + NAMES_ONLY
    found = [(n, by_id[n]) for n in names if n in by_id]
    found += [(identity(st), st) for st in steps if if_of(st) == SCOPE_CONDITION and identity(st) not in names]
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


class ScopeConditionOnNoMdSteps(ChecksStepBase):
    def test_each_no_md_and_names_only_step_carries_the_scope_condition(self):
        steps = self.steps()
        for name in NO_MD + NAMES_ONLY:
            with self.subTest(step=name):
                got = if_of(self.named(steps, name))
                self.assertEqual(got, SCOPE_CONDITION, "step %r: if is %r, want the scope condition" % (name, got))


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
        for name in NO_MD + NAMES_ONLY + MUST_STAY_UNSCOPED + PR_ONLY:
            with self.subTest(step=name):
                self.assertIn(name, MAIN_STEPS, "a pinned list names a step main does not have")

    def test_no_step_is_on_two_lists(self):
        listed = NO_MD + NAMES_ONLY + MUST_STAY_UNSCOPED + PR_ONLY
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

    def test_ste_lint_stays_unscoped_so_it_runs_on_that_pull_request(self):
        got = scope_run([DOC])
        self.assertEqual(got["code"], "false", "a docs-only change set code: %r" % got)
        st = self.named(self.steps(), STE_LINT)
        self.assertTrue(runs_on_pull_request_with(st, got["code"]), "STE lint carries the scope condition: if %r" % if_of(st))


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


if __name__ == "__main__":
    unittest.main()
