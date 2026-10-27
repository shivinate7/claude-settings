#!/usr/bin/env python3
"""At SubagentStart, gives each spawned agent the standing rules, so a brief need not retype them. The scope line depends on the agent type.

Decision agents-get-standing-rules. Prints `hookSpecificOutput` with `hookEventName` "SubagentStart" and
`additionalContext` (Claude Code hooks reference). The scope line varies by `agent_type` from
the hook input; an unknown or missing type gets the general scope text.
Advisory, fail-open by design: on any error it prints one stderr line and exits 0, so a bug here never
blocks an agent from starting.
"""
import json
import os
import sys

# Each line carries a flag: True = every type, False = only types that commit and push.
COMMON = [
    (True, "Standing rules for this agent:"),
    (True, "- Never run git stash, git reset, git checkout <path>, or git restore."),
    (False, "- Push only with: git push origin HEAD:<branch>."),
    (True, "- Make no gh call unless your brief names it."),
    (True, "- {scope}"),
    (True, "- Report in 25 lines or fewer unless the brief sets a cap. Order: Done, Deviations, Input Needed, Next."),
    (False, "- End each commit message with: Co-Authored-By: <model> <noreply@anthropic.com>"),
    (False, "- Name no record path in a commit message. The only exception is the Drops-lines: trailer."),
    (False, "- Before you end, stop each server you started, by the $! from the same call or through the harness."),
]
READ_ONLY = {"reviewer", "Explore", "Plan", "claude-code-guide", "design-reviewer"}

SCOPE = {
    "builder": "Scope: builder. Never edit tests or test config. Add mutants to hooks/mutate_guard.py when the brief asks. Report a test change you need.",
    "test-author": "Scope: test-author. Edit tests and test config only. Never edit product code.",
    "reviewer": "Scope: reviewer. Never edit, write, stage, commit, or push. Read and run checks only.",
    "Explore": "Scope: Explore. Never edit. Read and search only.",
    "record-writer": "Scope: record-writer. Edit Markdown (*.md) files only. Report any other change needed.",
    "designer": ("Scope: designer. Edit files in the repo's design folder only. Report any other change needed. "
                 "Your brief names your lane kind: blind, informed or directed. In a blind lane, never read "
                 "the current screen, its code, its screenshots, its mockups, or the repo's design spec and tokens."),
    "design-reviewer": "Scope: design-reviewer. Never edit, write, stage, commit, or push. Read and render only.",
}
GENERAL = ("Scope: do only what your brief names. A builder never edits tests; "
           "a test-author never edits product code; a reviewer and Explore never edit; "
           "a record-writer edits Markdown only.")


def cite_form(cwd):
    """The repo's cite form from <cwd>/.github/stamp.json: cite.form, filled per kind ({prefix} is the
    kind's prefix, {slug} reads as "slug"), joined in kind order with repeats dropped. None when the
    file or the field is missing or unreadable."""
    try:
        with open(os.path.join(cwd, ".github", "stamp.json"), encoding="utf-8") as fh:
            cfg = json.load(fh)
        form = cfg["cite"]["form"]
        if not isinstance(form, str) or not form:
            return None
        prefixes = [k.get("prefix") for k in cfg.get("kinds", []) if isinstance(k, dict)]
        forms = [form.replace("{prefix}", p).replace("{slug}", "slug") for p in prefixes if isinstance(p, str)]
        return ", ".join(dict.fromkeys(forms or [form.replace("{prefix}", "").replace("{slug}", "slug")]))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def build(agent_type, form=None):
    key = agent_type.lower() if isinstance(agent_type, str) else agent_type  # the match ignores case
    writes = key not in {t.lower() for t in READ_ONLY}
    lines = [t for always, t in COMMON if always or writes]
    text = "\n".join(lines).format(scope=next((v for k, v in SCOPE.items() if k.lower() == key), GENERAL))
    if form:  # appended after format(): a form may hold braces
        text += "\n- Cite a record in this repo's form: %s. Any other wrapper around a slug stays dead text." % form
    return text


def main():
    try:
        data = json.loads(sys.stdin.read())
        agent_type = data.get("agent_type") if isinstance(data, dict) else None
        if not isinstance(agent_type, str):
            agent_type = None
        else:
            agent_type = agent_type.rsplit(":", 1)[-1]  # plugin prefix: my-plugin:builder
        cwd = data.get("cwd") if isinstance(data, dict) else None
        form = cite_form(cwd) if isinstance(cwd, str) and cwd else None
        out = {"hookSpecificOutput": {"hookEventName": "SubagentStart",
                                      "additionalContext": build(agent_type, form)}}
        print(json.dumps(out))
    except Exception as e:  # advisory hook: fail open; one stderr line shows in --debug
        print(f"agent_brief: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
