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

It also surfaces the guard's `noted`/`subject-unread` lines. The shared-tree rule reads the
SUBJECT of a discarding git call, and a subject it could not read is allowed rather than refused
on a guess. That allow must not be silent, so the guard logs one line and this hook names it at
turn end. The lines come from `guard.log`, bounded by the timestamp of the last human message, so
an older turn's line is not reported again. The guard writes a LOCAL time and the transcript
carries a UTC time, so the bound is converted to local time rather than compared across zones,
and one second is taken off it because the guard truncates its stamp to whole seconds.

Decision 8 ("Merge into main: allow and report") makes this hook also surface a merge into main
landed this turn: a `Bash`/`PowerShell` tool_use whose command matches `gh pr merge`, and any
`mcp__github__merge_pull_request` tool_use. The guard already allows and logs these; this hook is
how the owner still SEES them at turn end, so the reply can name them under Done.
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
SHELL_TOOLS = {"Bash", "PowerShell"}
MERGE_TOOLS = {"mcp__github__merge_pull_request"}

GH_PR_MERGE = re.compile(r"\bgh\s+pr\s+merge\b")

CONFIG_MESSAGE = "Config files changed this turn: %s."
MERGE_MESSAGE = "Merges into main this turn: %s."
UNREAD_MESSAGE = (
    "The guard could not read the subject of these commands, and allowed them: %s."
)
TAIL = " Name them in the report."
UNREAD_RULE = "subject-unread"


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


def collect_merges(records):
    """Return the merges into main this turn's tools named, in first-seen order."""
    seen = []

    def note(text):
        if text and text not in seen:
            seen.append(text)

    for rec in records:
        for b in tool_uses(rec):
            name = b.get("name")
            inp = b.get("input") or {}
            if not isinstance(inp, dict):
                continue
            if name in MERGE_TOOLS:
                note(name)
            elif name in SHELL_TOOLS:
                cmd = inp.get("command") or ""
                if isinstance(cmd, str) and GH_PR_MERGE.search(cmd):
                    note(cmd.strip())
    return seen


def last_human_stamp(records):
    """Return the timestamp of the last human message, else ''."""
    stamp = ""
    for rec in records:
        if is_last_human(rec):
            value = rec.get("timestamp") or ""
            stamp = value if isinstance(value, str) else ""
    return stamp


def _turn_bound(stamp):
    """Return the last human message time as a naive LOCAL datetime, else None.

    The transcript stamp is UTC and the guard's log stamp is local, so the bound is converted
    rather than compared across zones. One second is taken off, because the guard truncates its
    own stamp to whole seconds and a line written in the same second would otherwise be dropped.
    """
    text = (stamp or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except Exception:
        return None
    if moment.tzinfo is not None:
        moment = moment.astimezone().replace(tzinfo=None)
    return moment - timedelta(seconds=1)


def collect_unread(stamp):
    """Return the matched text of each `noted`/`subject-unread` guard line from this turn."""
    bound = _turn_bound(stamp)
    if bound is None:
        return []
    try:
        import guard  # PreToolUse guard.py, same directory
        path = os.path.join(guard.config_dir(), "guard.log")
    except Exception:
        return []
    if not os.path.exists(path):
        return []
    seen = []
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except Exception:
        return []
    for line in lines:
        fields = line.split("\t")
        if len(fields) != 5 or fields[3] != UNREAD_RULE:
            continue
        try:
            when = datetime.fromisoformat(fields[0])
        except Exception:
            continue
        if when < bound:
            continue
        text = fields[4].strip()
        if text and text not in seen:
            seen.append(text)
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
    merges = collect_merges(after)
    unread = collect_unread(last_human_stamp(records))
    if not hits and not merges and not unread:
        return

    parts = []
    if hits:
        parts.append(CONFIG_MESSAGE % ", ".join(hits))
    if merges:
        parts.append(MERGE_MESSAGE % ", ".join(merges))
    if unread:
        parts.append(UNREAD_MESSAGE % ", ".join(unread))
    print(json.dumps({"systemMessage": " ".join(parts) + TAIL}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
