#!/usr/bin/env python3
"""Claude Code hook: config-edit report (Stop).

Decision 7 ("Project config edits: allow and report") lets a session edit a project's own
`.claude/hooks/*`, `.claude/settings.json`, or `.claude/settings.local.json` without a permission
prompt. This hook is how the owner still SEES the edit at turn end: it prints a `systemMessage`
naming every such file changed since the last human message, so the reply can name it under
Deviations.

Reads the hook JSON on stdin. Always exits 0. Fails open on bad input, a missing transcript, or a
parse error, and on any failure to import `guard.py` (the path test then never fires, which is a
missed report, never a wrong one).

Stop: when this turn edited a project config file (an `Edit`/`Write`/`MultiEdit`/`NotebookEdit`
tool_use, or a `Bash`/`PowerShell` command that writes to one) after the last human message, print
`{"systemMessage": "..."}` naming the files. Otherwise print nothing. When `stop_hook_active` is
set, the reply is already a rewrite, so the gate stays quiet.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
SHELL_TOOLS = {"Bash", "PowerShell"}

MESSAGE = "Config files changed this turn: %s. Name them under Deviations."


# ------------------------------------------------------------------ transcript walking
#
# Copied from lint/report_gate.py rather than imported, so this hook has no dependency on the STE
# lint package.

def is_last_human(rec):
    if rec.get("type") != "user":
        return False
    if rec.get("isSidechain"):
        return False
    msg = rec.get("message") or {}
    content = msg.get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        has_text = any(isinstance(b, dict) and b.get("type") == "text" for b in content)
        has_tool_result = any(
            isinstance(b, dict) and b.get("type") == "tool_result" for b in content
        )
        return has_text and not has_tool_result
    return False


def tool_uses(rec):
    msg = rec.get("message") or {}
    content = msg.get("content")
    if not isinstance(content, list):
        return
    for b in content:
        if isinstance(b, dict) and b.get("type") == "tool_use":
            yield b


def records_after_last_human(records):
    last_human_idx = None
    for i, rec in enumerate(records):
        if is_last_human(rec):
            last_human_idx = i
    if last_human_idx is None:
        return []
    return records[last_human_idx + 1:]


def read_transcript(path):
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if isinstance(rec, dict):
                records.append(rec)
    return records


# ------------------------------------------------------------------ the path test

def collect_paths(records, cwd):
    """Return the project config paths this turn's tools touched, in first-seen order."""
    try:
        import guard  # PreToolUse guard.py, same directory
    except Exception:
        guard = None

    seen = []

    def note(path):
        if path and path not in seen:
            seen.append(path)

    for rec in records:
        for b in tool_uses(rec):
            name = b.get("name")
            inp = b.get("input") or {}
            if not isinstance(inp, dict):
                continue
            if name in FILE_TOOLS:
                target = (
                    inp.get("file_path") or inp.get("path") or inp.get("notebook_path") or ""
                )
                if not isinstance(target, str) or not target:
                    continue
                if guard is None:
                    continue
                try:
                    hit = guard.is_project_config(target, cwd)
                except Exception:
                    hit = False
                if hit:
                    note(target)
            elif name in SHELL_TOOLS:
                cmd = inp.get("command") or ""
                if not isinstance(cmd, str) or not cmd.strip():
                    continue
                if guard is None:
                    continue
                try:
                    matched = guard.project_config_shell_hit(cmd, cwd)
                except Exception:
                    matched = ""
                if matched:
                    note(matched)
    return seen


def main():
    try:
        hook = json.load(sys.stdin)
    except Exception:
        return
    if not isinstance(hook, dict):
        return
    if hook.get("stop_hook_active"):
        return

    path = hook.get("transcript_path")
    if not path or not os.path.exists(path):
        return

    try:
        records = read_transcript(path)
    except Exception:
        return

    after = records_after_last_human(records)
    if not after:
        return

    cwd = hook.get("cwd") or ""
    if not isinstance(cwd, str):
        cwd = ""

    hits = collect_paths(after, cwd)
    if not hits:
        return

    print(json.dumps({"systemMessage": MESSAGE % ", ".join(hits)}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
