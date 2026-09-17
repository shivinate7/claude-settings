#!/usr/bin/env python3
"""Mutation test for hooks/guard.py.

Stdlib only. For each mutation below, it copies guard.py to a temp file, applies one
literal string replacement, and runs hooks/test_guard.py against the copy with
GUARD_UNDER_TEST=<copy> and CLAUDE_CONFIG_DIR=<temp dir>. The suite must go red
(a nonzero exit backed by at least one FAIL line). A mutation the suite does not
catch is "survived", and any survivor fails this run.

A mutation whose replacement string is not found in the current guard.py is STALE:
the source moved on and the mutation no longer proves anything. That must fail
loudly, not be skipped, so it exits 1 with an error line instead of counting the
mutation either way.

Run:
    python hooks/mutate_guard.py

Ported from a prior run at
.../scratchpad/mutate3.py (fourteen mutations), plus five added for rules
guard.py grew since that run: the live-stream rule, the waiter rule (Rule 9),
the REDIRECTION strip in git_calls, and the Decision 7 config-edit log line.
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "guard.py")
SUITE = os.path.join(HERE, "test_guard.py")

# (name, anchor text found once in the source, its mutated replacement).
# Each one breaks exactly one rule. One mutation per rule at least:
# shared-tree, machine-wide kill, live-stream, waiter, force push, destructive
# delete, env-file, merge-main, frozen-path, the redirect strip, and the log.
MUTATIONS = [
    ("shared-tree: drop the git clean arm",
     '        if subcommand == "clean" and clean_deletes_files(args):',
     '        if False and clean_deletes_files(args):'),
    ("shared-tree: call every tree a worktree",
     '    return own != common',
     '    return True'),
    ("env-file: read only the bare environment basename",
     'ENV_BASENAME = re.compile(r"^\\.env(\\.[A-Za-z0-9_.\\-]+)?$")',
     'ENV_BASENAME = re.compile(r"^\\.env$")'),
    ("shared-tree: drop the interpreter heredoc exception",
     '    if INTERPRETER_HEREDOC.search(cmd):\n        return cmd',
     '    if False:\n        return cmd'),
    ("frozen-path: freeze nothing",
     '    if not path:\n        return False',
     '    if path:\n        return False'),
    ("force-push: forget the force push",
     'def push_is_forced(args) -> bool:',
     'def push_is_forced(args) -> bool:\n    return False'),
    ("merge-main: trust an unreadable merge base",
     '        elif base == "":',
     '        elif base == "never":'),
    ("machine-wide-kill: pkill and killall no longer deny in command position",
     '    if tool in KILL_COMMAND_WORDS:\n        return word',
     '    if False:\n        return word'),
    ("machine-wide-kill: taskkill's image flag no longer denies",
     '    if tool == "taskkill" and any(flag.lower() in TASKKILL_IMAGE_FLAGS for flag in rest):\n'
     '        return word',
     '    if False:\n        return word'),
    ("machine-wide-kill: Stop-Process's name flag no longer denies",
     '    if tool == "stop-process" and any('
     'flag.lower() in STOP_PROCESS_NAME_FLAGS for flag in rest):\n        return word',
     '    if False:\n        return word'),
    ("machine-wide-kill: lsof -t no longer feeds a kill list",
     '            if arg.startswith("-") and not arg.startswith("--") and "t" in arg:\n'
     '                return word + " " + arg',
     '            if False:\n                return word + " " + arg'),
    ("command word: a wrapper such as xargs no longer unwraps to what it runs",
     '    while index < end and basename(tokens[index]) in COMMAND_WRAPPERS:',
     '    while False:'),
    ("shell segments: a quote never closes, so a real call after it is swallowed whole",
     '            if char == quote:\n                quote = ""',
     '            if False:\n                quote = ""'),
    ("conflict-resolve: a conflict-side flag no longer exempts the checkout",
     'CHECKOUT_CONFLICT_FLAGS = {"--ours", "--theirs", "--merge"}',
     'CHECKOUT_CONFLICT_FLAGS = set()'),
    ("conflict-resolve: every tree reads as mid-conflict",
     '    return any(os.path.isdir(os.path.join(path, name)) for name in REBASE_STATE_DIRS)',
     '    return True'),
    ("log: stop logging refusals",
     '        with open(os.path.join(folder, "guard.log"), "a", encoding="utf-8") as handle:\n'
     '            handle.write(line + "\\n")',
     '        pass'),
    ("shared-tree: keep heredoc bodies in every rule",
     '    lines = cmd.split("\\n")',
     '    return cmd\n    lines = cmd.split("\\n")'),
    ("env-file: name the file in the environment reason, the reviewed defect",
     '        refuse(tool, "deny", "env-file", ENV_TOOL_REASON + ". " + ENV_ADVICE, target)',
     '        refuse(tool, "deny", "env-file", ENV_TOOL_REASON + " " + target + ". "'
     ' + ENV_ADVICE, target)'),
    ("env-file: name the file in the shell environment reason, the reviewed defect",
     '        refuse(tool, "deny", "env-file", refusal + ". " + ENV_ADVICE, logged)',
     '        refuse(tool, "deny", "env-file", logged + ". " + ENV_ADVICE, logged)'),
    ("frozen-path: name the path in the frozen reason",
     '        refuse(tool, "deny", "frozen-path", FROZEN_REASON, target)',
     '        refuse(tool, "deny", "frozen-path", FROZEN_REASON + " " + target, target)'),
    # Added: rules guard.py grew after the prior mutation run.
    ("live-stream: never refuse a live stream",
     '    for segment in split_segments(stripped):\n'
     '        matched = live_stream_hit(segment)\n'
     '        if matched:\n'
     '            refuse(tool, "deny", "live-stream", LIVE_STREAM_REASON, matched)',
     '    for segment in split_segments(stripped):\n'
     '        matched = live_stream_hit(segment)\n'
     '        if False:\n'
     '            refuse(tool, "deny", "live-stream", LIVE_STREAM_REASON, matched)'),
    ("waiter: never refuse a waiter loop (Rule 9)",
     '        matched = waiter_hit(segment)\n'
     '        if matched:\n'
     '            refuse(tool, "deny", "waiter", WAITER_REASON, matched)',
     '        matched = waiter_hit(segment)\n'
     '        if False:\n'
     '            refuse(tool, "deny", "waiter", WAITER_REASON, matched)'),
    ("destructive-delete: blind the wide-delete patterns",
     "    for pattern in DESTRUCTIVE_DELETE:\n        found = pattern.search(cmd)",
     "    for pattern in ():\n        found = pattern.search(cmd)"),
    ("git-call parsing: drop the redirect strip before tokenizing",
     '    tokens = REDIRECTION.sub(" ", segment).split()',
     '    tokens = segment.split()'),
    ("config-edit: stop noting project config edits, shell tool",
     '    matched = project_config_shell_hit(stripped, cwd)\n'
     '    if matched:\n'
     '        record(tool, "noted", "config-edit", matched)',
     '    matched = project_config_shell_hit(stripped, cwd)\n'
     '    if False:\n'
     '        record(tool, "noted", "config-edit", matched)'),
    # Added: the stash/reset/restore split (Decision 12). Each mutation collapses one predicate
    # back to a bare name match, the exact defect this split fixes, so a later edit that redoes
    # that collapse goes red here.
    ("shared-tree: stash collapses back to a name match on every action",
     '    return action not in STASH_READ_ACTIONS and action not in STASH_RESTORE_ACTIONS',
     '    return True'),
    ("shared-tree: reset collapses back to a name match, --hard or not",
     '    return "--hard" in args',
     '    return True'),
    # Added: the subject read. One per arm. Each mutation blinds ONE subject read, which must
    # turn that arm's empty-subject case red: a guard that refuses without reading its subject is
    # the defect these arms fix.
    ("subject: the reset arm never reads the working tree",
     'def reset_subject(args, where: str):',
     'def reset_subject(args, where: str):\n    return False'),
    ("subject: the stash arm never reads the tree or the stack",
     'def stash_subject(args, where: str):',
     'def stash_subject(args, where: str):\n    return False'),
    ("subject: the restore arm never reads its paths",
     'def restore_subject(args, where: str):',
     'def restore_subject(args, where: str):\n    return False'),
    ("subject: the checkout arm never reads its paths",
     'def checkout_subject(args, where: str):',
     'def checkout_subject(args, where: str):\n    return False'),
    ("subject: the clean arm never reads the untracked entries",
     'def clean_subject(args, where: str):',
     'def clean_subject(args, where: str):\n    return False'),
    ("subject: a clean exclude pattern is read as a pathspec, so the read narrows wrongly",
     'CLEAN_OPT_WITH_VALUE = {"-e", "--exclude"}',
     'CLEAN_OPT_WITH_VALUE = set()'),
    ("subject: an unreadable subject is refused instead of allowed and logged",
     '        if state is None:\n'
     '            record(tool, "noted", "subject-unread", matched)\n'
     '            continue',
     '        if False:\n'
     '            record(tool, "noted", "subject-unread", matched)\n'
     '            continue'),
    ("scratchpad: this session's own scratchpad stops being private",
     'def under_session_scratchpad(where: str, session_id: str) -> bool:',
     'def under_session_scratchpad(where: str, session_id: str) -> bool:\n    return False'),
    ("scratchpad: every path reads as this session's scratchpad",
     '    parts = real.split(os.sep)',
     '    return True\n    parts = real.split(os.sep)'),
    ("shared-tree: restore collapses back to a name match, --staged or not",
     '    staged = "--staged" in args or "-S" in args\n'
     '    worktree = "--worktree" in args or "-W" in args\n'
     '    return worktree or not staged',
     '    return True'),
]


def run_suite(guard_path: str, config_dir: str):
    """Run the fixture suite against one guard copy. Return (exit code, FAIL lines)."""
    env = dict(os.environ)
    env["GUARD_UNDER_TEST"] = guard_path
    env["CLAUDE_CONFIG_DIR"] = config_dir
    result = subprocess.run(
        [sys.executable, SUITE], capture_output=True, text=True, env=env, timeout=1200,
    )
    red = [line for line in result.stdout.splitlines() if line.startswith("FAIL")]
    return result.returncode, red


def safe_name(label: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in label)[:60]


def main() -> int:
    with open(GUARD, encoding="utf-8") as handle:
        source = handle.read()

    work = tempfile.mkdtemp(prefix="mutate_guard_")
    survivors = 0
    try:
        for label, old, new in MUTATIONS:
            if old not in source:
                print("ERROR stale mutation, anchor text not found: %s" % label)
                return 1
            mutated = source.replace(old, new, 1)
            copy_path = os.path.join(work, "guard_%s.py" % safe_name(label))
            with open(copy_path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(mutated)
            config_dir = os.path.join(work, "cfg_%s" % safe_name(label))
            os.makedirs(config_dir, exist_ok=True)
            code, red = run_suite(copy_path, config_dir)
            if code == 0 or not red:
                survivors += 1
                print("SURVIVED  %-64s %2d red" % (label, len(red)))
            else:
                print("KILLED    %-64s %2d red" % (label, len(red)))
        print()
        print("%d of %d mutations killed" % (len(MUTATIONS) - survivors, len(MUTATIONS)))
        return 1 if survivors else 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
