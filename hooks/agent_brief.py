#!/usr/bin/env python3
"""SubagentStart hook: give every spawned agent the standing rules, so briefs stop retyping them.

Owner ruling 2026-10-12. Prints `hookSpecificOutput` with `hookEventName` "SubagentStart" and
`additionalContext` (Claude Code hooks reference). The scope line varies by `agent_type` from
the hook input; an unknown or missing type gets the general scope text.
Advisory, fail-open by design: on any error it prints one stderr line and exits 0, so a bug here never
blocks an agent from starting.
"""
import json
import os
import re
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
]
READ_ONLY = {"reviewer", "Explore", "Plan", "claude-code-guide"}

SCOPE = {
    "builder": "Scope: builder. Never edit tests or test config. Add mutants to hooks/mutate_guard.py when the brief asks. Report a test change you need.",
    "test-author": "Scope: test-author. Edit tests and test config only. Never edit product code.",
    "reviewer": "Scope: reviewer. Never edit, write, stage, commit, or push. Read and run checks only.",
    "Explore": "Scope: Explore. Never edit. Read and search only.",
    "record-writer": "Scope: record-writer. Edit Markdown (*.md) files only. Report any other change needed.",
}
GENERAL = ("Scope: do only what your brief names. A builder never edits tests; "
           "a test-author never edits product code; a reviewer and Explore never edit; "
           "a record-writer edits Markdown only.")


# A capture group that is not a lookaround. The scan skips escapes and character classes.
GROUP = re.compile(r"\((?!\?)(?:\\.|\[[^\]]*\]|[^()\\\[])*\)")
# What is left of a pattern once groups and \b are filled: escapes and plain text, no regex syntax.
LITERAL = re.compile(r"(?:\\.|[^\\?*+|^$()\[\]{}])*")


def derive_form(cite, kinds):
    """A literal cite form read off cite.pattern, or None. A bandaid for a stamp.json with no cite.form:
    the group the pattern names for the prefix becomes the first kind's prefix, the slug group becomes
    "slug". A pattern with any other regex syntax gives None, never a guess."""
    pattern, count = cite.get("pattern"), [0]

    def fill(m):
        count[0] += 1
        if count[0] == cite.get("slugGroup", 1):
            return "slug"
        if count[0] == cite.get("prefixGroup") and kinds and isinstance(kinds[0].get("prefix"), str):
            return kinds[0]["prefix"]
        return "\0"  # an unknown group: fails LITERAL below

    if not isinstance(pattern, str):
        return None
    flat = GROUP.sub(fill, pattern).replace("\\b", "")
    if not LITERAL.fullmatch(flat) or "\0" in flat:
        return None
    return re.sub(r"\\(.)", r"\1", flat)


def cite_form(cwd):
    """The repo's cite form from <cwd>/.github/stamp.json: cite.form with {slug} read as "slug", else
    derived from cite.pattern. None when the repo defines none or the file cannot be read."""
    try:
        with open(os.path.join(cwd, ".github", "stamp.json"), encoding="utf-8") as fh:
            cfg = json.load(fh)
        cite, kinds = cfg["cite"], [k for k in cfg.get("kinds", []) if isinstance(k, dict)]
        form = cite.get("form")
        if isinstance(form, str) and form:
            prefix = kinds[0].get("prefix", "") if kinds else ""
            return form.replace("{prefix}", prefix if isinstance(prefix, str) else "").replace("{slug}", "slug")
        return derive_form(cite, kinds)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def build(agent_type, form=None):
    writes = agent_type not in READ_ONLY
    lines = [t for always, t in COMMON if always or writes]
    text = "\n".join(lines).format(scope=SCOPE.get(agent_type, GENERAL))
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
