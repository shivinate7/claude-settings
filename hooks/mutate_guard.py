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
.../scratchpad/mutate3.py (fourteen mutations), plus three added for rules
guard.py grew since that run: the live-stream rule and the REDIRECTION strip
in git_calls.
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
# shared-tree, machine-wide kill, live-stream, force push, destructive delete,
# env-file, merge-main, frozen-path, the redirect strip, and the log.
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
     '        if base == "":',
     '        if base == "never":'),
    ("machine-wide-kill: blind the name and image kill patterns",
     "    for pattern in MACHINE_WIDE_KILL:\n        found = pattern.search(cmd)",
     "    for pattern in ():\n        found = pattern.search(cmd)"),
    ("machine-wide-kill: blind the flag-aware kill arm",
     '    tokens = segment.split()\n    for index, token in enumerate(tokens):\n'
     '        tool = basename(token)',
     '    return ""\n    tokens = segment.split()\n    for index, token in enumerate(tokens):\n'
     '        tool = basename(token)'),
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
     '    for segment in SEGMENT_SPLIT.split(stripped):\n'
     '        matched = live_stream_hit(segment)\n'
     '        if matched:\n'
     '            refuse(tool, "deny", "live-stream", LIVE_STREAM_REASON, matched)',
     '    for segment in SEGMENT_SPLIT.split(stripped):\n'
     '        matched = live_stream_hit(segment)\n'
     '        if False:\n'
     '            refuse(tool, "deny", "live-stream", LIVE_STREAM_REASON, matched)'),
    ("destructive-delete: blind the wide-delete patterns",
     "    for pattern in DESTRUCTIVE_DELETE:\n        found = pattern.search(cmd)",
     "    for pattern in ():\n        found = pattern.search(cmd)"),
    ("git-call parsing: drop the redirect strip before tokenizing",
     '    tokens = REDIRECTION.sub(" ", segment).split()',
     '    tokens = segment.split()'),
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
