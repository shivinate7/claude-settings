#!/usr/bin/env python3
"""SubagentStart hook: give every spawned agent the standing rules, so briefs stop retyping them.

Owner ruling 2026-10-12. Prints `hookSpecificOutput` with `hookEventName` "SubagentStart" and
`additionalContext` (Claude Code hooks reference). The scope line varies by `agent_type` from
the hook input; an unknown or missing type gets the general scope text.
Advisory, fail-open by design: on any error it prints nothing and exits 0, so a bug here never
blocks an agent from starting.
"""
import json
import sys

COMMON = [
    "Standing rules for this agent:",
    "- Never run git stash, git reset, git checkout <path>, or git restore.",
    "- Push only with: git push origin HEAD:<branch>.",
    "- Make no gh call unless your brief names it.",
    "- {scope}",
    "- Report in 25 lines or fewer unless the brief sets a cap. Order: Done, Deviations, Input Needed, Next.",
    "- End each commit message with: Co-Authored-By: <model> <noreply@anthropic.com>",
    "- Name no record path in a commit message. The only exception is the Drops-lines: trailer.",
]

SCOPE = {
    "builder": "Scope: builder. Never edit tests, test config, or hooks/mutate_guard.py. Report a test change you need.",
    "test-author": "Scope: test-author. Edit tests and test config only. Never edit product code.",
    "reviewer": "Scope: reviewer. Never edit, write, stage, commit, or push. Read and run checks only.",
    "Explore": "Scope: Explore. Never edit. Read and search only.",
    "record-writer": "Scope: record-writer. Edit Markdown (*.md) files only. Report any other change needed.",
}
GENERAL = ("Scope: do only what your brief names. A builder never edits tests or hooks/mutate_guard.py; "
           "a test-author never edits product code; a reviewer and Explore never edit; "
           "a record-writer edits Markdown only.")


def build(agent_type):
    return "\n".join(COMMON).format(scope=SCOPE.get(agent_type, GENERAL))


def main():
    try:
        data = json.loads(sys.stdin.read())
        agent_type = data.get("agent_type") if isinstance(data, dict) else None
        if not isinstance(agent_type, str):
            agent_type = None
        out = {"hookSpecificOutput": {"hookEventName": "SubagentStart",
                                      "additionalContext": build(agent_type)}}
        print(json.dumps(out))
    except Exception:  # advisory hook: fail open, print nothing
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
