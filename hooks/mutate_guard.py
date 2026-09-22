#!/usr/bin/env python3
"""Mutation test for hooks/guard.py.

Stdlib only. For each mutation below, it copies guard.py to a temp file, applies one
literal string replacement, and runs hooks/test_guard.py against the copy with
GUARD_UNDER_TEST=<copy> and CLAUDE_CONFIG_DIR=<temp dir>. The suite must go red
(a nonzero exit backed by at least one FAIL line). A mutation the suite does not
catch is "survived", and any survivor fails this run.

A RED SUITE IS NOT ENOUGH. A nonzero exit plus any red line used to count as "killed", even
when every red line belonged to some OTHER case than the one the mutation's label names. A
mutant that breaks the waiter rule could die on an unrelated shared-tree case and still count
as caught, which proves nothing about the rule its label names. Every mutation below therefore
carries a fifth field: the case name (or a distinctive fragment of it) that MUST appear among
the suite's own FAIL lines. A mutant whose red lines miss that name is "WRONG CAUSE", kept
distinct from "survived", and fails this run exactly as a survivor does. The field is mandatory:
`mutation_parts` and `run_mutant` refuse a mutation that carries none.

A mutation whose replacement string is not found in the current guard.py is STALE:
the source moved on and the mutation no longer proves anything. That must fail
loudly, not be skipped, so it exits 1 with an error line instead of counting the
mutation either way.

The mutants run IN PARALLEL, one suite process per mutant, up to the CPU count at once
(MUTATE_JOBS overrides). Each mutant gets its own guard copy and its own config directory, so
the runs share nothing but the read-only fixture tree the suite builds under its own temp
root. MEASURED 2026-09-19 on a 4-core machine: 38 mutants serial, 14 min 8 s (22 s each);
47 mutants parallel, 4 min 29 s. The suite itself spawns guard.py once per case, which is
where the time goes.

Run:
    python hooks/mutate_guard.py

Ported from a prior run at
.../scratchpad/mutate3.py (fourteen mutations), plus five added for rules
guard.py grew since that run: the live-stream rule, the waiter rule (Rule 9),
the REDIRECTION strip in git_calls, and the Decision 7 config-edit log line.
"""

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "guard.py")
SUITE = os.path.join(HERE, "test_guard.py")
WATCH = os.path.join(HERE, "config_watch.py")
WATCH_SUITE = os.path.join(HERE, "test_config_watch.py")

# How many red lines a wrong cause prints before it stops. A wrong cause usually carries one or
# two, and the bound keeps a mutation that breaks half the suite from burying the rest of the run.
WRONG_CAUSE_LINES_SHOWN = 10

# A mutation names the file it breaks and the suite that must catch it. "guard" is the default, so
# every mutation written before the watch existed reads unchanged.
TARGETS = {
    "guard": (GUARD, SUITE, "GUARD_UNDER_TEST", "guard"),
    "watch": (WATCH, WATCH_SUITE, "WATCH_UNDER_TEST", "config_watch"),
}

# (label, anchor text found once in the source, its mutated replacement, target, required case
# name). Each one breaks exactly one rule. One mutation per rule at least:
# shared-tree, machine-wide kill, live-stream, waiter, force push, destructive
# delete, env-file, merge-main, frozen-path, the redirect strip, and the log.
#
# THE FIFTH FIELD is the case name, or a distinctive fragment of it, that must show up among the
# suite's own FAIL lines: `hooks/test_guard.py`'s FAIL line already prints `case["name"]` verbatim,
# and `hooks/test_config_watch.py`'s does the same with `entry["name"]`, so no second file needed
# a change to carry this. Each name was MEASURED against this file's own mutants, not guessed: a
# label's prose is a claim about which rule breaks, and the required name is the proof that some
# case actually reads that break, not a different one nearby.
MUTATIONS = [
    # THE TWO ROOTS. `--work-tree` names whose FILES a call discards, and `--git-dir` names whose
    # HEAD it moves. Each mutant makes one of them unread, or makes one root answer the other's
    # question.
    ("work-tree: the tree option goes unread, so rule 1 judges the wrong tree",
     'GIT_WORK_TREE_RE = re.compile(r"--work-tree(?:=|\\s+)([\'\\"]?)([^\'\\";&|\\s]+)\\1")',
     'GIT_WORK_TREE_RE = re.compile(r"--never-a-real-option(\\A\\Z)(\\A\\Z)")', "guard", 'work-tree: a clean cwd pointed at a dirty tree is judged on the dirty tree'),
    ("pointer-head: the git directory option goes unread",
     'GIT_DIR_RE = re.compile(r"--git-dir(?:=|\\s+)([\'\\"]?)([^\'\\";&|\\s]+)\\1")',
     'GIT_DIR_RE = re.compile(r"--never-a-real-option(\\A\\Z)(\\A\\Z)")', "guard", 'pointer: --git-dir reaches the pointer HEAD from an unrelated directory'),
    ("pointer-head: the HEAD root falls back through the work tree, naming the wrong HEAD",
     '        return run_dir\n    return _absolute(match.group(2), run_dir)',
     '        return command_root(cmd, shell_cwd)\n    return _absolute(match.group(2), run_dir)', "guard", 'pointer: --work-tree alone moves no HEAD in the pointer checkout'),
    ("pointer-head: read the shared common git directory, so a worktree reads as its primary",
     '        answer = _git(where, "rev-parse", "--absolute-git-dir")',
     '        answer = _git(where, "rev-parse", "--git-common-dir")', "guard", 'pointer: switch of a branch in another checkout is allowed'),
    # RULE 1b, the pointer checkout's HEAD. Each mutant breaks one arm: the act test, the tree
    # test, the main exemption, the two path-operation arms, the `switch` subcommand, the top-level
    # read, and the pointer parse.
    ("pointer-head: no command ever moves HEAD",
     'def head_move_target(subcommand: str, args) -> str:',
     'def head_move_target(subcommand: str, args) -> str:\n    return ""', "guard", 'pointer: checkout of a branch in the pointer checkout is refused'),
    ("pointer-head: call every tree the pointer checkout",
     '    return mine == theirs',
     '    return True', "guard", 'pointer: checkout of a branch in another checkout is allowed'),
    ("pointer-head: lose the exemption for a move to main",
     '    if target == PROTECTED_BASE:\n        return ""',
     '    if target == "no-such-branch":\n        return ""', "guard", 'pointer: a move back to main restores the invariant and passes'),
    ("pointer-head: read a double dash as a branch",
     '    if "--" in args:\n        return ""\n    switching = subcommand == "switch"',
     '    if False:\n        return ""\n    switching = subcommand == "switch"', "guard", 'pointer: a double dash names a path, and no HEAD moves'),
    ("pointer-head: forget the path-operation flags",
     'CHECKOUT_PATH_FLAGS = {"--ours", "--theirs", "--patch", "-p", "--overlay", "--no-overlay"}',
     'CHECKOUT_PATH_FLAGS = set()', "guard", 'pointer: --theirs with an extensionless path is no branch switch'),
    ("pointer-head: watch checkout and not switch",
     'HEAD_MOVE_SUBCOMMANDS = ("checkout", "switch")',
     'HEAD_MOVE_SUBCOMMANDS = ("checkout",)', "guard", 'pointer: switch of a branch in the pointer checkout is refused'),
    ("pointer-head: compare the directory as written, not the git directory git reports",
     '    mine = git_dir_of(root)',
     '    mine = os.path.normcase(os.path.realpath(root)) if root else ""', "guard", 'pointer: a subdirectory of the pointer checkout is still the pointer checkout'),
    ("pointer-head: a pointer line that never parses",
     'POINTER_LINE = re.compile(r"^@(.+)/CLAUDE\\.md[ \\t]*$", re.MULTILINE)',
     'POINTER_LINE = re.compile(r"^@@(.+)/CLAUDE\\.md[ \\t]*$", re.MULTILINE)', "guard", 'pointer: a new branch with -b is refused'),
    ("shared-tree: drop the git clean arm",
     '        if subcommand == "clean" and clean_deletes_files(args):',
     '        if False and clean_deletes_files(args):', "guard", 'clean: -fd deletes untracked files'),
    ("shared-tree: call every tree a worktree",
     '    return own != common',
     '    return True', "guard", 'worktree: a hard reset in the shared checkout denies'),

    # ---- rule 1's three new git forms: branch delete, worktree remove, worktree prune. Each
    # mutation breaks one arm of the state read the plan named as the hole in this rule.
    ("branch-delete: -D no longer marks a delete call",
     'BRANCH_DELETE_FLAGS = {"-d", "-D", "--delete"}',
     'BRANCH_DELETE_FLAGS = {"-d", "--delete"}', "guard",
     'branch: a commit found nowhere else is the only copy, and the rule denies'),
    ("branch-delete: -d no longer marks a delete call",
     'BRANCH_DELETE_FLAGS = {"-d", "-D", "--delete"}',
     'BRANCH_DELETE_FLAGS = {"-D", "--delete"}', "guard",
     'branch: -d over the same only-copy branch still denies'),
    ("branch-delete: the ancestor test asks the question backwards",
     '    answer = _git(where, "merge-base", "--is-ancestor", branch, base)',
     '    answer = _git(where, "merge-base", "--is-ancestor", base, branch)', "guard",
     'branch: a commit found nowhere else is the only copy, and the rule denies'),
    ("branch-delete: cherry never reads as empty, so a rebased patch looks unique",
     '    return not any(line.startswith("+") for line in answer.stdout.splitlines())',
     '    return False', "guard",
     "branch: a rebased commit's patch already sits on origin/main, cherry proves it"),
    ("branch-delete: no remote ever contains a branch",
     '    return bool(answer.stdout.strip())',
     '    return False', "guard", 'branch: a commit pushed to the remote is not the only copy'),
    ("branch-delete: the only-copy branch never denies",
     '        if empty is False:\n            return False\n    return True',
     '        if False:\n            return False\n    return True', "guard",
     'branch: a commit found nowhere else is the only copy, and the rule denies'),
    ("branch-delete: the base never falls back past origin/HEAD",
     '    for name in ("main", "master"):\n        answer = _git(where, "rev-parse", "--verify", '
     '"-q", "refs/heads/" + name)',
     '    for name in ():\n        answer = _git(where, "rev-parse", "--verify", "-q", '
     '"refs/heads/" + name)', "guard",
     'branch: local main\'s fallback still denies an only-copy branch'),

    ("worktree-remove: --force is read as the path, missing the real target",
     '    for arg in args:\n        if arg.startswith("-"):\n            continue\n        '
     'return _absolute(arg, where)\n    return ""',
     '    for arg in args:\n        if False:\n            continue\n        '
     'return _absolute(arg, where)\n    return ""', "guard",
     'worktree remove: the force flag does not skip the subject read'),
    ("worktree-remove: uncommitted and untracked work no longer denies",
     '    lines = porcelain(target)\n    if lines is None:\n        return None\n    if lines:\n'
     '        return False',
     '    lines = porcelain(target)\n    if lines is None:\n        return None\n    if False:\n'
     '        return False', "guard", 'worktree remove: uncommitted and untracked work denies'),
    ("worktree-remove: a locked tree no longer denies",
     '    locked = worktree_locked(where, target)\n    if locked is None:\n        return None\n'
     '    if locked:\n        return False',
     '    locked = worktree_locked(where, target)\n    if locked is None:\n        return None\n'
     '    if False:\n        return False', "guard",
     'worktree remove: a locked tree denies even though it is clean'),
    ("worktree-remove: a live session no longer denies",
     '    live = worktree_live_session(target)\n    if live is None:\n        return None\n'
     '    if live:\n        return False',
     '    live = worktree_live_session(target)\n    if live is None:\n        return None\n'
     '    if False:\n        return False', "guard",
     'worktree remove: a live session standing in a clean tree still denies'),
    ("worktree-remove: any session record counts as live, recycled pid included",
     '    return abs(actual - started) <= SESSION_LIVE_TOLERANCE_MS',
     '    return True', "guard", 'does not deny'),

    ("worktree-prune: reads only stdout, missing git's own stderr message",
     '    return not (answer.stdout.strip() or answer.stderr.strip())',
     '    return not answer.stdout.strip()', "guard",
     'worktree prune: a stale record asks, never denies'),
    ("worktree-prune: never asks, so a dropped record is silent",
     '        if subcommand == "worktree-prune":\n'
     '            refuse(tool, "ask", "shared-tree", WORKTREE_PRUNE_ASK_REASON, matched)',
     '        if False:\n'
     '            refuse(tool, "ask", "shared-tree", WORKTREE_PRUNE_ASK_REASON, matched)', "guard",
     'worktree prune: a stale record asks, never denies'),
    ("worktree-prune: the call's own -n no longer reads as a pure read",
     '                if any(a in ("-n", "--dry-run") for a in args[1:]):\n'
     '                    continue  # the call\'s own dry run is a read, never a discard',
     '                if False:\n'
     '                    continue  # the call\'s own dry run is a read, never a discard', "guard",
     'worktree prune: -n itself is a read, not a discard, so it passes unconditionally'),
    ("env-file: read only the bare environment basename",
     'ENV_BASENAME = re.compile(r"^\\.env(\\.[A-Za-z0-9_.\\-]+)?$")',
     'ENV_BASENAME = re.compile(r"^\\.env$")', "guard", 'env: a path token wherever the path puts it, cat .env.local'),
    ("shared-tree: drop the interpreter heredoc exception",
     '    if INTERPRETER_HEREDOC.search(cmd):\n        return cmd',
     '    if False:\n        return cmd', "guard", 'heredoc: a body fed to a shell stays under inspection'),
    ("frozen-path: freeze nothing",
     '    if not path:\n        return False\n    try:\n        target = _resolved(path, cwd)\n'
     '        root = os.path.normcase(os.path.realpath(config_dir()))',
     '    if path:\n        return False\n    try:\n        target = _resolved(path, cwd)\n'
     '        root = os.path.normcase(os.path.realpath(config_dir()))', "guard", 'frozen: Write of the global CLAUDE.md'),
    ("force-push: forget the force push",
     'def push_is_forced(args) -> bool:',
     'def push_is_forced(args) -> bool:\n    return False', "guard", 'push: the long force flag'),
    ("merge-main: trust an unreadable merge base",
     '        elif base == "":',
     '        elif base == "never":', "guard", 'log: a merge into main is allowed and noted where the base is unsafe'),
    ("machine-wide-kill: pkill and killall no longer deny in command position",
     '    if tool in KILL_COMMAND_WORDS:\n        return word',
     '    if False:\n        return word', "guard", 'kill: pkill by pattern'),
    ("machine-wide-kill: taskkill's image flag no longer denies",
     '    if tool == "taskkill" and any(flag.lower() in TASKKILL_IMAGE_FLAGS for flag in rest):\n'
     '        return word',
     '    if False:\n        return word', "guard", 'kill: taskkill by image name'),
    ("machine-wide-kill: Stop-Process's name flag no longer denies",
     '    if tool == "stop-process" and any('
     'flag.lower() in STOP_PROCESS_NAME_FLAGS for flag in rest):\n        return word',
     '    if False:\n        return word', "guard", 'kill: Stop-Process by name'),
    ("machine-wide-kill: lsof -t no longer feeds a kill list",
     '            if arg.startswith("-") and not arg.startswith("--") and "t" in arg:\n'
     '                return word + " " + arg',
     '            if False:\n                return word + " " + arg', "guard", 'kill: lsof -t feeds a kill list'),
    ("command word: a wrapper such as xargs no longer unwraps to what it runs",
     '    while index < end and basename(tokens[index]) in COMMAND_WRAPPERS:',
     '    while False:', "guard", 'kill: xargs unwraps to the real command it runs'),
    ("shell segments: a quote never closes, so a real call after it is swallowed whole",
     '            if char == quote:\n                quote = ""',
     '            if False:\n                quote = ""', "guard", 'kill: a quoted phrase ahead of a real chained kill still denies'),
    ("conflict-resolve: a conflict-side flag no longer exempts the checkout",
     'CHECKOUT_CONFLICT_FLAGS = {"--ours", "--theirs", "--merge"}',
     'CHECKOUT_CONFLICT_FLAGS = set()', "guard", 'checkout: --theirs resolves a real, unresolved merge conflict'),
    ("conflict-resolve: every tree reads as mid-conflict",
     '    return any(os.path.isdir(os.path.join(path, name)) for name in REBASE_STATE_DIRS)',
     '    return True', "guard", "checkout: the same call with no conflict in progress keeps today's decision"),
    ("log: stop logging refusals",
     '        with open(os.path.join(folder, "guard.log"), "a", encoding="utf-8") as handle:\n'
     '            handle.write(line + "\\n")',
     '        pass', "guard", 'log: one line per refusal and none for an allow'),
    ("shared-tree: keep heredoc bodies in every rule",
     '    lines = cmd.split("\\n")',
     '    return cmd\n    lines = cmd.split("\\n")', "guard", 'heredoc: prose naming the stash with no interpreter'),
    ("env-file: name the file in the environment reason, the reviewed defect",
     '        refuse(tool, "deny", "env-file", ENV_TOOL_REASON + ". " + ENV_ADVICE, target)',
     '        refuse(tool, "deny", "env-file", ENV_TOOL_REASON + " " + target + ". "'
     ' + ENV_ADVICE, target)', "guard", 'env: Read of the file'),
    ("env-file: name the file in the shell environment reason, the reviewed defect",
     '        refuse(tool, "deny", "env-file", refusal + ". " + ENV_ADVICE, logged)',
     '        refuse(tool, "deny", "env-file", logged + ". " + ENV_ADVICE, logged)', "guard", 'env: an absolute Windows path is still a path'),
    ("frozen-path: name the path in the frozen reason",
     '        refuse(tool, "deny", "frozen-path", FROZEN_REASON, target)',
     '        refuse(tool, "deny", "frozen-path", FROZEN_REASON + " " + target, target)', "guard", 'frozen: Write of a config hook'),
    # Added: rules guard.py grew after the prior mutation run.
    ("live-stream: never refuse a live stream",
     '    for segment in split_segments(stripped):\n'
     '        matched = live_stream_hit(segment)\n'
     '        if matched:\n'
     '            refuse(tool, "deny", "live-stream", LIVE_STREAM_REASON, matched)',
     '    for segment in split_segments(stripped):\n'
     '        matched = live_stream_hit(segment)\n'
     '        if False:\n'
     '            refuse(tool, "deny", "live-stream", LIVE_STREAM_REASON, matched)', "guard", 'stream: tail -f never ends'),
    ("waiter: never refuse a waiter loop (Rule 9)",
     '        matched = waiter_hit(segment)\n'
     '        if matched:\n'
     '            if poller:\n'
     '                refuse(tool, "deny", "waiter", PATTERN_POLLER_REASON, poller + " " + matched)\n'
     '            refuse(tool, "deny", "waiter", WAITER_REASON, matched)',
     '        matched = waiter_hit(segment)\n'
     '        if False:\n'
     '            if poller:\n'
     '                refuse(tool, "deny", "waiter", PATTERN_POLLER_REASON, poller + " " + matched)\n'
     '            refuse(tool, "deny", "waiter", WAITER_REASON, matched)', "guard",
     'waiter: a bare sleep'),
    ("command word: a loop keyword no longer yields to the command inside it (Rule 9's own gap)",
     '    while index < end and (ASSIGNMENT.match(tokens[index]) or tokens[index] in '
     'LOOP_KEYWORDS):',
     '    while index < end and (ASSIGNMENT.match(tokens[index]) or False):', "guard",
     'waiter: an until-loop over a plain readiness check, MEASURED wrongly allowed'),
    ("waiter: a pattern-polling loop condition no longer gets its own reason",
     '            if poller:\n'
     '                refuse(tool, "deny", "waiter", PATTERN_POLLER_REASON, poller + " " + matched)',
     '            if False:\n'
     '                refuse(tool, "deny", "waiter", PATTERN_POLLER_REASON, poller + " " + matched)',
     "guard",
     'waiter: a while-loop with a pattern-polling condition, MEASURED wrongly allowed'),
    ("destructive-delete: blind the wide-delete patterns",
     "    for pattern in DESTRUCTIVE_DELETE:\n        found = pattern.search(cmd)",
     "    for pattern in ():\n        found = pattern.search(cmd)", "guard", 'delete: the root'),
    ("git-call parsing: drop the redirect strip before tokenizing",
     '    tokens = REDIRECTION.sub(" ", segment).split()',
     '    tokens = segment.split()', "guard", 'checkout: a start point survives a merged-output redirect'),
    ("config-edit: stop noting project config edits, shell tool",
     '    matched = project_config_shell_hit(stripped, cwd)\n'
     '    if matched:\n'
     '        record(tool, "noted", "config-edit", matched)',
     '    matched = project_config_shell_hit(stripped, cwd)\n'
     '    if False:\n'
     '        record(tool, "noted", "config-edit", matched)', "guard", 'log: a project config edit is allowed and noted'),
    # Added: the stash/reset/restore split (Decision 12). Each mutation collapses one predicate
    # back to a bare name match, the exact defect this split fixes, so a later edit that redoes
    # that collapse goes red here.
    ("shared-tree: stash collapses back to a name match on every action",
     '    return stash_action(args) not in STASH_READ_ACTIONS',
     '    return True', "guard", 'stash: list only reads, no subcommand match'),
    # Added 2026-09-19 with the stack clause. The first mutant blinds the DIRECTION predicate, so
    # every stash call is read against the working tree. The second puts back the exact defect
    # this change fixes: only `drop` and `clear` read the stack, so `pop`, `apply` and `branch`
    # pass over a clean tree that carries another session's entry.
    ("shared-tree: no stash action is read as taking an entry off the stack",
     'def stash_takes_the_stack(args) -> bool:',
     'def stash_takes_the_stack(args) -> bool:\n    return False', "guard", 'subject: dropping a real stash entry still denies'),
    ("subject: only drop and clear read the stack, the narrow clause put back",
     '    if stash_takes_the_stack(args):\n        stack = stash_stack(where)',
     '    if stash_action(args) in ("drop", "clear"):\n        stack = stash_stack(where)', "guard", 'subject: popping a real entry from a CLEAN checkout still denies'),
    ("shared-tree: reset collapses back to a name match, --hard or not",
     '    return "--hard" in args',
     '    return True', "guard", 'reset: a plain reset only unstages, the working tree is untouched'),
    # Added: the subject read. One per arm. Each mutation blinds ONE subject read, which must
    # turn that arm's empty-subject case red: a guard that refuses without reading its subject is
    # the defect these arms fix.
    ("subject: the reset arm never reads the working tree",
     'def reset_subject(args, where: str):',
     'def reset_subject(args, where: str):\n    return False', "guard", 'subject: a hard reset in a clean tree takes nothing'),
    ("subject: a hard reset at any commit passes on a clean tree, the owner's narrowing undone",
     '    if reset_target(args) not in RESET_HEAD_TARGETS:\n        return False',
     '    if False:\n        return False', "guard", 'subject: a hard reset one commit back moves the branch, clean tree or not'),
    ("subject: the stash arm never reads the tree or the stack",
     'def stash_subject(args, where: str):',
     'def stash_subject(args, where: str):\n    return False', "guard", 'subject: setting aside a clean tree takes nothing'),
    ("subject: the restore arm never reads its paths",
     'def restore_subject(args, where: str):',
     'def restore_subject(args, where: str):\n    return False', "guard", 'subject: restoring a clean path inside a dirty tree changes nothing'),
    ("subject: the checkout arm never reads its paths",
     'def checkout_subject(args, where: str):',
     'def checkout_subject(args, where: str):\n    return False', "guard", 'subject: checking out a clean path inside a dirty tree changes nothing'),
    ("subject: the clean arm never reads the untracked entries",
     'def clean_subject(args, where: str):',
     'def clean_subject(args, where: str):\n    return False', "guard", 'subject: a clean with no untracked file deletes nothing'),
    ("subject: a clean exclude pattern is read as a pathspec, so the read narrows wrongly",
     'CLEAN_OPT_WITH_VALUE = {"-e", "--exclude"}',
     'CLEAN_OPT_WITH_VALUE = set()', "guard", 'subject: an exclude pattern is not a pathspec'),
    # POSIX-only mutant: its required case ("subject: a git that cannot answer the status read
    # allows, rather than guess") is itself gated `if os.name != "nt":` in test_guard.py, because
    # `make_blind_git`'s own docstring records a Windows measurement (2026-09-16): CreateProcess
    # appends `.exe` and never reads PATHEXT, so a `git.cmd` stand-in is skipped and the real
    # `git.exe` further on PATH answers instead, which would make the case pass for the wrong
    # reason. The case is therefore SKIPPED on Windows entirely, so the required name can never
    # appear among that platform's FAIL lines, whatever else the run turns up.
    ("subject: an unreadable subject is refused instead of allowed and logged",
     '        if state is None:\n'
     '            record(tool, "noted", "subject-unread", matched)\n'
     '            continue',
     '        if False:\n'
     '            record(tool, "noted", "subject-unread", matched)\n'
     '            continue', "guard", 'subject: a git that cannot answer the status read allows, rather than guess', "posix"),
    ("scratchpad: this session's own scratchpad stops being private",
     'def under_session_scratchpad(where: str, session_id: str) -> bool:',
     'def under_session_scratchpad(where: str, session_id: str) -> bool:\n    return False', "guard", "scratchpad: a discard in this session's own scratchpad is private"),
    ("scratchpad: every path reads as this session's scratchpad",
     '    parts = real.split(os.sep)',
     '    return True\n    parts = real.split(os.sep)', "guard", "scratchpad: another session's scratchpad is not this session's"),
    ("shared-tree: restore collapses back to a name match, --staged or not",
     '    staged = "--staged" in args or "-S" in args\n'
     '    worktree = "--worktree" in args or "-W" in args\n'
     '    return worktree or not staged',
     '    return True', "guard", 'restore: staged alone only touches the index'),
    # Added: the subagent model cap (rule 8, PR #42). These are the mutations its builder ran by hand
    # on `.bak` copies, now in CI. Each one undoes one thing the review made the rule do, so a later
    # edit that redoes it goes red here.
    ("cap: the edit-count cap comes back, so 200 no-op edits hide a lift",
     '    if isinstance(edits, list):\n        for edit in edits:',
     '    if isinstance(edits, list):\n        for edit in edits[:200]:', "guard", 'cap: the lift in the last of 400 edits still asks'),
    ("cap: the resolved-basename branch is gone, so a symlink to a settings file walks past",
     '        return basename(_resolved(path, cwd)) in SETTINGS_BASENAMES\n'
     '    except Exception:\n        return False',
     '        return False\n'
     '    except Exception:\n        return False', "guard", 'cap: a symlink to a project settings file resolves and asks'),
    ("cap: the JSON key walk is gone, so a JSON-escaped key walks past",
     '    for key, value in json_cap_values(text).items():',
     '    for key, value in ():', "guard", 'cap: a JSON-escaped key in the content asks'),
    ("cap: cap_safe passes text through, so a long value is neither cut nor marked",
     '    clean = CAP_CONTROL.sub(" ", text or "")',
     '    return text or ""\n    clean = CAP_CONTROL.sub(" ", text or "")', "guard", 'cap: a very long model value is cut and the cut is marked'),
    ("cap: the bare-key pass is gone, so an unreadable value walks past",
     '    for found in SUBAGENT_CAP_KEY.finditer(text):\n'
     '        reading.setdefault(found.group(0), "")',
     '    for found in ():\n'
     '        reading.setdefault(found.group(0), "")', "guard", 'cap: a value the pattern cannot read still asks'),
    ("cap: the rule runs ahead of the frozen-path deny, so the config settings ask instead",
     '        if is_frozen(target, cwd):\n'
     '            refuse(tool, "deny", "frozen-path", FROZEN_REASON, target)',
     '        if is_settings_file(target, cwd):\n'
     '            change = cap_change_parts(write_content_parts(tool_input))\n'
     '            if change:\n'
     '                refuse(tool, "ask", "subagent-model-cap", cap_ask_reason(change, target),\n'
     '                       target + " " + change)\n'
     '        if is_frozen(target, cwd):\n'
     '            refuse(tool, "deny", "frozen-path", FROZEN_REASON, target)', "guard", 'cap: the config settings stay denied, never asked'),
    ("cap: the shell route runs ahead of the frozen-path deny, so a heredoc onto the config "
     "settings asks instead",
     '    matched = frozen_shell_hit(stripped, cwd)\n'
     '    if matched:\n'
     '        refuse(tool, "deny", "frozen-path", FROZEN_REASON, matched)',
     '    matched = _shell_write_hit(stripped, cwd, is_settings_file)\n'
     '    if matched:\n'
     '        change = cap_change(raw)\n'
     '        if change:\n'
     '            refuse(tool, "ask", "subagent-model-cap", cap_ask_reason(change, matched),\n'
     '                   matched + " " + change)\n'
     '    matched = frozen_shell_hit(stripped, cwd)\n'
     '    if matched:\n'
     '        refuse(tool, "deny", "frozen-path", FROZEN_REASON, matched)', "guard", 'cap: a heredoc onto the config settings stays denied'),
    ("cap: the shell route reads the stripped command, so a heredoc body's cap change walks past",
     '        change = cap_change(raw)',
     '        change = cap_change(stripped)', "guard", 'cap: a heredoc writing a project settings file asks'),
    ("cap: an earlier part wins, so an Edit names the value it leaves, not the one it arrives at",
     '            values[key] = value',
     '            values.setdefault(key, value)', "guard", 'cap: Edit turning the force flag off asks'),
    ("frozen-path: the config-watch baseline store is not frozen",
     '    os.path.normcase("state"),',
     '    os.path.normcase("state_unfrozen"),', "guard", 'frozen: Write of the config-watch baseline store'),

    # ---- Rule 1c, the silent write (Decision, silent-write-leaves-a-trace). One mutant per arm:
    # the rule disabled outright, each of the two silencing detectors on its own, the two
    # in-loop carve-outs, and each subcommand set a carve-out depends on staying the shape it was
    # measured to be.
    # REQUIRED CASE NAMES, for the fifth `mutation_parts` field once it lands: each label below
    # names the silent-write test case its own red line must carry.
    #   "silent-write: the rule never denies at all"
    #     -> "silent-write: push's own quiet flag needs no redirect at all"
    #   "silent-write: the quiet-flag arm no longer fires for any subcommand"
    #     -> "silent-write: push's own quiet flag needs no redirect at all"
    #   "silent-write: a discarding redirect no longer silences anything"
    #     -> "silent-write: a discarded proof of landing, stdout alone"
    #   "silent-write: the merge --abort carve-out is gone"
    #     -> "silent-write: an abort lands nothing, so it is carved out"
    #   "silent-write: fetch joins the denied subcommands"
    #     -> "silent-write: fetch's own quiet flag is a carve-out"
    #   "silent-write: commit, tag, and cherry-pick rejoin the quiet-flag arm, the measured
    #   carve-outs undone"
    #     -> "silent-write: commit's own quiet flag is a carve-out, MEASURED 2026-09-19"
    ("silent-write: the rule never denies at all",
     '        matched, mechanism = silent_write_hit(segment)\n'
     '        if matched:\n'
     '            reason = (SILENT_WRITE_REDIRECT_REASON if mechanism == "redirect"\n'
     '                      else SILENT_WRITE_QUIET_REASON)\n'
     '            refuse(tool, "deny", "silent-write", reason, matched)',
     '        matched, mechanism = silent_write_hit(segment)\n'
     '        if False:\n'
     '            reason = (SILENT_WRITE_REDIRECT_REASON if mechanism == "redirect"\n'
     '                      else SILENT_WRITE_QUIET_REASON)\n'
     '            refuse(tool, "deny", "silent-write", reason, matched)', "guard",
     "silent-write: a discarded proof of landing, stdout alone"),
    ("silent-write: the quiet-flag arm no longer fires for any subcommand",
     '        if subcommand in QUIET_FLAG_SUBCOMMANDS and quiet_write(args):',
     '        if False and quiet_write(args):', "guard",
     "silent-write: push's own quiet flag needs no redirect at all"),
    ("silent-write: a discarding redirect no longer silences anything",
     '        if discards_output(segment):\n            return matched, "redirect"',
     '        if False:\n            return matched, "redirect"', "guard",
     'silent-write: a discarded proof of landing, stdout alone'),
    ("silent-write: the merge --abort carve-out is gone",
     '        if subcommand == "merge" and "--abort" in args:\n            continue',
     '        if False:\n            continue', "guard",
     'silent-write: an abort lands nothing, so it is carved out'),
    ("silent-write: fetch joins the denied subcommands",
     'SILENT_WRITE_SUBCOMMANDS = ("commit", "push", "merge", "tag", "rebase", "cherry-pick")',
     'SILENT_WRITE_SUBCOMMANDS = ("commit", "push", "merge", "tag", "rebase", "cherry-pick", '
     '"fetch")', "guard",
     "silent-write: fetch discarding both streams is a carve-out"),
    ("silent-write: commit, tag, and cherry-pick rejoin the quiet-flag arm, the measured "
     "carve-outs undone",
     'QUIET_FLAG_SUBCOMMANDS = ("push", "merge", "rebase")',
     'QUIET_FLAG_SUBCOMMANDS = ("commit", "push", "merge", "tag", "rebase", "cherry-pick")', "guard",
     "silent-write: commit's own quiet flag is a carve-out, MEASURED 2026-09-19"),

    # ---- the PostToolUse watch. These break `hooks/config_watch.py` and must be killed by
    # `hooks/test_config_watch.py`, which writes the cap for real and reads the file back.
    ("watch: never restore, only report",
     '    if not restore(path, baseline["content"]):',
     '    if False and not restore(path, baseline["content"]):', "watch", 'cp from another file'),
    ("watch: restore in silence, so a revert is never reported",
     '    if messages:\n        print(json.dumps({"systemMessage": " ".join(messages)}))',
     '    if False:\n        print(json.dumps({"systemMessage": " ".join(messages)}))', "watch", 'sed -i in place'),
    ("watch: treat every write as explained, so nothing is ever undone",
     'not (explained and explained == resolve(path, cwd))',
     'not (True)', "watch", 'mv from another file'),
    ("watch: compare the bytes, not the cap reading, so an ordinary edit is reverted too",
     'if reading != was and not (',
     'if True and not (', "watch", 'an ordinary project config edit is allowed and not reverted'),
    ("watch: watch settings.json alone, so the local file is unwatched",
     'WATCHED_NAMES = tuple(name.lstrip("/") for name in guard.PROJECT_FROZEN_FILES)',
     'WATCHED_NAMES = ("\x2eclaude/settings.json",)', "watch", 'python3 -c writes the path'),
    ("watch: an absent file reads the same as an empty one, so a created file is not a change",
     '    if content is None:\n        return ""\n    return hashlib.sha256(content).hexdigest()',
     '    return hashlib.sha256(content or b"").hexdigest()', "watch",
     'a file goes from empty to absent before a lift, so the revert removes it, not empties it'),
    ("watch: a missing baseline is read as clear rather than recorded",
     '    if baseline is None:\n        save_baseline(path, current)',
     '    if baseline is None:\n        save_baseline(path, None)', "watch", 'a write to an unrelated file triggers nothing'),

    # ---- the expiry rule, added 2026-09-20. Nothing killed a mutant here before this block:
    # every case below is new, exercising `cap_lift_value`, `next_prior`, `expiry_problem`, and
    # the expiry tail of `judge_path` that `hooks/test_config_watch.py`'s "expiry" cases guard.
    ("watch: the 24-hour ceiling runs backwards, so only a SAFE deadline reads as too far ahead",
     '    if ahead > EXPIRY_MAX_AHEAD_HOURS * 3600:',
     '    if ahead < EXPIRY_MAX_AHEAD_HOURS * 3600:', "watch",
     'more than 24h ahead is revoked'),
    ("watch: the 24-hour bound is negated, so even a one-hour deadline reads as too far ahead",
     '    if ahead > EXPIRY_MAX_AHEAD_HOURS * 3600:',
     '    if ahead > -(EXPIRY_MAX_AHEAD_HOURS * 3600):', "watch",
     'a valid, current _subagentCapUntil is NOT reverted'),
    ("watch: the passed-deadline test is inverted, so an expired deadline reads as current",
     '    if ahead < 0:\n        return "already passed"',
     '    if ahead > 0:\n        return "already passed"', "watch",
     'already passed is revoked'),
    ("watch: the missing-expiry branch is turned off, so a lift with no deadline survives",
     '    if where is None:\n        return "missing"',
     '    if False:\n        return "missing"', "watch",
     'a missing _subagentCapUntil is revoked'),
    ("watch: next_prior carries the first lift's own content forward, so a later revert "
     "installs an override instead of the true baseline",
     '    if cap_lift_value(was):\n        return baseline.get("prior")',
     '    if cap_lift_value(was):\n        return baseline["content"]', "watch",
     "keeps the ORIGINAL pre-lift content as prior"),

    # ---- the 24-hour boundary itself, added 2026-09-20 (round 3). `expiry_problem` now takes
    # an injectable `clock`, so `hooks/test_config_watch.py`'s boundary cases can pin a
    # fixture's `_subagentCapUntil` and the watch's own "now" to the SAME instant, and an
    # off-by-one at the exact edge is no longer invisible to this harness.
    ("watch: the too-far-ahead check admits its own edge, so a deadline exactly 24h out is "
     "wrongly revoked",
     '    if ahead > EXPIRY_MAX_AHEAD_HOURS * 3600:',
     '    if ahead >= EXPIRY_MAX_AHEAD_HOURS * 3600:', "watch",
     "exactly 24 hours ahead is accepted"),
    ("watch: the passed-deadline check admits its own edge, so the deadline instant itself "
     "reads as already passed",
     '    if ahead < 0:',
     '    if ahead <= 0:', "watch",
     "exactly at the deadline instant is accepted"),
    ("watch: the 24-hour ceiling is one second too loose, so a deadline one second over is "
     "wrongly accepted",
     '    if ahead > EXPIRY_MAX_AHEAD_HOURS * 3600:',
     '    if ahead > EXPIRY_MAX_AHEAD_HOURS * 3600 + 1:', "watch",
     "one second outside the 24h bound is revoked"),
    ("watch: the 24-hour ceiling is one second too tight, so a deadline exactly on it is "
     "wrongly revoked",
     '    if ahead > EXPIRY_MAX_AHEAD_HOURS * 3600:',
     '    if ahead > EXPIRY_MAX_AHEAD_HOURS * 3600 - 1:', "watch",
     "exactly 24 hours ahead is accepted"),

    # ---- the liveness oracle's alive/dead/unreadable split, added for Windows parity. Each
    # mutant here folds the new third state back into one of the other two, the exact shape of
    # the bug this whole change fixes.
    # POSIX-only mutant: it breaks `_process_start_ms`'s `ps`-exit-code arm, which
    # `_process_start_ms` never reaches on Windows (it routes straight to the ctypes Windows arm
    # instead, see guard.py's `_process_start_ms`). `process_start_ms_case` in test_guard.py
    # already skips its dead/unreadable POSIX-only sub-cases on Windows (`os.name == "nt"`), so
    # nothing on that platform can ever observe this mutation. The sixth field marks it
    # posix-only so the run loop skips it there instead of reporting a false survivor.
    ("liveness: a bad ps exit code reads as CONFIRMED dead instead of unreadable",
     '        if answer.returncode == 1 and not answer.stdout.strip():\n            return None\n'
     '        return PROCESS_START_UNREADABLE',
     '        return None',
     "guard", "liveness: process_start_ms splits alive/dead/unreadable apart", "posix"),
    ("liveness: session_is_live folds the unreadable third state back into False",
     '    if actual is PROCESS_START_UNREADABLE:\n        return None\n    if actual is None:',
     '    if actual is None:',
     "guard", "liveness: session_is_live carries True/False/None, never coercing unreadable to False"),
    ("liveness: worktree_live_session drops an unreadable record instead of answering None",
     '        live = session_is_live(record)\n        if live is True:\n            return True\n'
     '        if live is None:\n            saw_unreadable = True',
     '        if not session_is_live(record):\n            continue',
     "guard", "liveness: worktree_live_session answers None on an unreadable record under target"),
    ("liveness: the windows arm reads access-denied (error 5) as CONFIRMED dead",
     '        if error == 87:  # ERROR_INVALID_PARAMETER: no such process\n            return None',
     '        if error in (87, 5):\n            return None',
     "guard", "liveness: windows arm splits dead (error 87) from unreadable (error 5)"),
    ("liveness: the windows arm reads no-such-process (error 87) as unreadable, not dead",
     '        if error == 87:  # ERROR_INVALID_PARAMETER: no such process\n            return None\n'
     '        return PROCESS_START_UNREADABLE  # 5 (ERROR_ACCESS_DENIED) or any other code',
     '        return PROCESS_START_UNREADABLE',
     "guard", "liveness: windows arm splits dead (error 87) from unreadable (error 5)"),
]


def run_suite(suite: str, variable: str, copy_path: str, config_dir: str):
    """Run one fixture suite against one mutated copy. Return (exit code, FAIL lines)."""
    env = dict(os.environ)
    env.pop("GUARD_UNDER_TEST", None)
    env.pop("WATCH_UNDER_TEST", None)
    env[variable] = copy_path
    env["CLAUDE_CONFIG_DIR"] = config_dir
    result = subprocess.run(
        [sys.executable, suite], capture_output=True, text=True, env=env, timeout=1200,
    )
    red = [line for line in result.stdout.splitlines() if line.startswith("FAIL")]
    return result.returncode, red


def safe_name(label: str) -> str:
    """Turn a mutation label into a filesystem stem that stays unique, even case-insensitively.

    MEASURED: two real labels here differ only in the case of one letter. One reads "-D",
    the other reads "-d", inside the branch-delete flags. The old alnum-to-underscore
    mapping kept letter case. Both then produced the identical name on a case-insensitive
    filesystem (Windows). One file. One config directory. Two mutant runs raced to write it.
    The digest covers the exact label text. It does not depend on letter case. It does not
    depend on where the mutation sits in MUTATIONS. Two different labels collide here only
    if their digests also collide.
    """
    base = "".join(ch if ch.isalnum() else "_" for ch in label)[:60]
    digest = hashlib.sha1(label.encode("utf-8")).hexdigest()[:8]
    return "%s_%s" % (base, digest)


def mutation_parts(entry):
    """Return (label, old, new, target, required, only_on) for one mutation.

    `target` defaults to "guard" for a 3-element entry, which is the shape every mutation
    written before the watch target existed still carries on disk until it is ported. `required`
    reads the same way for the port: absent on a 3- or 4-element entry.

    ONCE EVERY ENTRY CARRIES FIVE FIELDS, as they all do now, `required` is MANDATORY. A mutation
    with no required case name is as unproven as one that dies wrong: it says which rule breaks,
    but nothing checks that the suite's own red line is about THAT rule. The tolerant read above
    stays only so a future port has somewhere to land mid-edit; a caller that wants the field
    enforced asserts `len(entry) == 5` itself, which `run_mutant` below does.

    `only_on` is a SIXTH, optional field: "posix" or "windows", for a mutation whose broken code
    path only exists on one platform (e.g. `_process_start_ms`'s POSIX `ps` arm, never reached
    on Windows). Absent on every other entry, which runs on every platform as before.
    """
    label, old, new = entry[0], entry[1], entry[2]
    target = entry[3] if len(entry) > 3 else "guard"
    required = entry[4] if len(entry) > 4 else None
    only_on = entry[5] if len(entry) > 5 else None
    return label, old, new, target, required, only_on


def skip_reason(only_on):
    """Return why a mutation marked `only_on` does not run on this platform, or None to run it."""
    if only_on is None:
        return None
    here = "windows" if sys.platform.startswith("win") else "posix"
    if only_on == here:
        return None
    return "%s-only, this platform is %s" % (only_on, here)


def run_mutant(sources, work: str, entry):
    """Apply one mutation, run its suite against it, and return (label, code, FAIL lines,
    required, skip).

    `required` is the case name (or a distinctive fragment of it) the caller must find among the
    FAIL lines before trusting this mutant's death: see the verdict loop in `main`. `skip`, when
    not None, is why this mutant did not run on this platform at all: the caller reports it and
    counts it as neither killed, survived, nor wrong cause.
    """
    label, old, new, target, required, only_on = mutation_parts(entry)
    if required is None:
        raise ValueError("mutation carries no required case name: %s" % label)
    skip = skip_reason(only_on)
    if skip:
        return label, None, [], required, skip
    _path, suite, variable, stem = TARGETS[target]
    mutated = sources[target].replace(old, new, 1)
    copy_path = os.path.join(work, "%s_%s.py" % (stem, safe_name(label)))
    with open(copy_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(mutated)
    config_dir = os.path.join(work, "cfg_%s" % safe_name(label))
    os.makedirs(config_dir, exist_ok=True)
    code, red = run_suite(suite, variable, copy_path, config_dir)
    return label, code, red, required, None


def job_count() -> int:
    """How many suites to run at once: MUTATE_JOBS, else the CPU count, at least one."""
    try:
        wanted = int(os.environ.get("MUTATE_JOBS", "") or 0)
    except ValueError:
        wanted = 0
    return max(1, wanted or os.cpu_count() or 1)


def main() -> int:
    sources = {}
    for name, (path, _suite, _variable, _stem) in TARGETS.items():
        with open(path, encoding="utf-8") as handle:
            sources[name] = handle.read()

    # Every anchor is checked BEFORE any suite runs, so a stale mutation fails in the first
    # second, not after the mutants ahead of it in the list have spent their minutes. A mutation
    # whose anchor sits in the WRONG file is stale too, which is what the target lookup catches.
    # The required-name field is checked here too: every entry must carry one, not just the ones
    # a reviewer remembered to fill in.

    # Two mutants must never write to the same path. safe_name already appends a digest of
    # the exact label, so this must not happen (see its docstring). Trust a guard only after
    # it goes red on the defect it guards. So this check recomputes the real file name for
    # each mutant, case-folded the way Windows reads names, instead of trusting the fix alone.
    seen_paths = {}
    for index, entry in enumerate(MUTATIONS):
        label, old, _new, target, required, _only_on = mutation_parts(entry)
        if target not in TARGETS:
            print("ERROR unknown mutation target %r: %s" % (target, label))
            return 1
        if old not in sources[target]:
            print("ERROR stale mutation, anchor text not found: %s" % label)
            return 1
        if not required:
            print("ERROR mutation carries no required case name: %s" % label)
            return 1
        _tpath, _tsuite, _tvariable, stem = TARGETS[target]
        safed = safe_name(label)
        # Two different entries land here. The same entry never returns twice. `index` marks
        # identity, not `label`. A literal duplicate label is still caught. That case is worse
        # than a case-only match, and the check treats it as a real collision, not a repeat
        # visit.
        for candidate in ("%s_%s.py" % (stem, safed), "cfg_%s" % safed):
            key = candidate.lower()
            other = seen_paths.get(key)
            if other is not None and other[0] != index:
                print("ERROR two mutations share one path on a case-insensitive filesystem: "
                      "%r and %r both produce %s" % (other[1], label, candidate))
                return 1
            seen_paths[key] = (index, label)

    work = tempfile.mkdtemp(prefix="mutate_guard_")
    # A "watch" mutant is a copy of config_watch.py that runs OUTSIDE hooks/, as its own
    # subprocess, and it does a plain `import guard` (never GUARD_UNDER_TEST: a mutation of the
    # watch must never be killed by a guard that moved with it, which is why
    # `test_config_watch.py`'s own `Project.env()` strips that variable before it spawns the
    # copy). Without the REAL guard.py sitting next to it, that import fails on every watch
    # mutant alike, and the crash reads as "the watch missed it" for EVERY case regardless of
    # which line was mutated: a kill with no bearing on the defect the mutation names, the exact
    # failure this file exists to catch. MEASURED: before this line, all seven `watch` mutants
    # printed the identical nine-case failure list, whatever the mutation.
    with open(os.path.join(work, "guard.py"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(sources["guard"])

    survivors = 0
    wrong_cause = 0
    skipped = 0
    jobs = job_count()
    print("%d mutations, %d at a time" % (len(MUTATIONS), jobs))
    try:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            results = pool.map(lambda entry: run_mutant(sources, work, entry), MUTATIONS)
            for label, code, red, required, skip in results:
                if skip:
                    skipped += 1
                    print("SKIPPED     %-62s %s" % (label, skip), flush=True)
                elif code == 0 or not red:
                    survivors += 1
                    print("SURVIVED    %-62s %2d red" % (label, len(red)), flush=True)
                elif not any(required in line for line in red):
                    wrong_cause += 1
                    print("WRONG CAUSE %-62s %2d red, missing %r" % (
                        label, len(red), required), flush=True)
                    # The lines it DID see, never the count alone. A wrong cause says the suite
                    # went red somewhere else, and the count says nothing about where. MEASURED
                    # on real Windows CI, run 35678689541: this mutant reported "1 red" and
                    # nothing more, so which case broke stayed unknown, and
                    # decisions/branch-delete-wrong-cause-was-a-filename-collision.md was written
                    # against a fact nobody could read. A bounded print is the difference
                    # between one CI run and a guessing round.
                    for line in red[:WRONG_CAUSE_LINES_SHOWN]:
                        print("            saw: %s" % line.strip(), flush=True)
                    if len(red) > WRONG_CAUSE_LINES_SHOWN:
                        print("            saw: ... and %d more" % (
                            len(red) - WRONG_CAUSE_LINES_SHOWN), flush=True)
                else:
                    print("KILLED      %-62s %2d red" % (label, len(red)), flush=True)
        print()
        ran = len(MUTATIONS) - skipped
        killed = ran - survivors - wrong_cause
        print("%d of %d mutations killed (%d survived, %d wrong cause, %d skipped)" % (
            killed, ran, survivors, wrong_cause, skipped))
        return 1 if (survivors or wrong_cause) else 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
