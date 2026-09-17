#!/usr/bin/env python3
"""Claude Code hook: report-shape gate.

Reads the hook JSON on stdin. Always exits 0. Fails open on bad input, a missing
transcript, or a parse error.

Stop: when this turn ran `git commit`, `git push`, `git merge`, or a GitHub MCP write tool
after the last human message, block once unless the reply ends with one blockquote holding
the bold labels Done, Deviations, Input Needed, Next, in that order (CLAUDE.md, "Reports, in
order"). When the last human message asks a question, prose may sit above the report, so the
answer does not have to hide inside it. Nothing may follow the report either way. When
stop_hook_active is set, the reply is already a rewrite, so the gate stays quiet.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ste_gate import last_reply  # noqa: E402

LANDING_COMMAND = re.compile(r"\bgit\s+(?:-C\s+\S+\s+)?(commit|push|merge)(?!\S)")
LANDING_TOOLS = {
    "mcp__github__merge_pull_request",
    "mcp__github__create_pull_request",
    "mcp__github__push_files",
    "mcp__github__create_or_update_file",
}
LABEL_ORDER = ["Done", "Deviations", "Input Needed", "Next"]
LABEL_RE = re.compile(r"^\*\*(.+?)\*\*")

BLOCK_REASON_HEAD = (
    "Report-shape gate: this turn landed a commit, push, or merge, so the reply must end "
    "with the report. One blockquote, bold labels Done, Deviations, Input Needed, Next in "
    "that order, drop a label that does not apply, no code fence, nothing after it."
)
BLOCK_REASON_NO_PREFIX = (
    " Nothing may sit above the report on this turn. Write the whole reply again as the "
    "report alone. Do not repeat the prose you already wrote."
)
BLOCK_REASON_PREFIX_OK = (
    " The last human message asks a question, so prose may sit above the report. Write the "
    "whole reply again: the answer first, then the report last."
)


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
        has_tool_result = any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content)
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


def turn_landed(records):
    for rec in records:
        for b in tool_uses(rec):
            name = b.get("name")
            if name == "Bash":
                cmd = (b.get("input") or {}).get("command") or ""
                if LANDING_COMMAND.search(cmd):
                    return True
            elif name in LANDING_TOOLS:
                return True
    return False


def asked_question(rec):
    """True when the last human message holds a question mark."""
    msg = rec.get("message") or {}
    content = msg.get("content")
    if isinstance(content, str):
        return "?" in content
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text" and "?" in (b.get("text") or ""):
                return True
    return False


def report_shape_ok(text, allow_prefix=False):
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.lstrip().startswith(">"):
            start = i
            break
    if start is None:
        return False
    if start > 0 and not allow_prefix:
        return False
    seen = []
    any_label = False
    for line in lines[start:]:
        if not line.strip():
            continue
        if not line.lstrip().startswith(">"):
            return False
        if "```" in line:
            return False
        stripped = line.lstrip()
        stripped = stripped[1:] if stripped.startswith(">") else stripped
        stripped = stripped.lstrip()
        m = LABEL_RE.match(stripped)
        if not m:
            continue
        label = m.group(1)
        any_label = True
        if label not in LABEL_ORDER:
            return False
        seen.append(label)
    if not any_label:
        return False
    if seen and seen[0] != "Done":
        return False
    idxs = [LABEL_ORDER.index(l) for l in seen]
    if idxs != sorted(set(idxs)) or len(set(idxs)) != len(idxs):
        return False
    return True


def main():
    try:
        hook = json.load(sys.stdin)
    except Exception:
        return
    if not isinstance(hook, dict):
        return
    if hook.get("hook_event_name") != "Stop":
        return
    if hook.get("stop_hook_active"):
        return

    path = hook.get("transcript_path")
    if not path or not os.path.exists(path):
        return

    records = []
    try:
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
    except Exception:
        return

    last_human_idx = None
    for i, rec in enumerate(records):
        if is_last_human(rec):
            last_human_idx = i
    if last_human_idx is None:
        return

    after = records[last_human_idx + 1:]
    if not turn_landed(after):
        return

    allow_prefix = asked_question(records[last_human_idx])
    text = last_reply(hook)
    if report_shape_ok(text, allow_prefix):
        return
    tail = BLOCK_REASON_PREFIX_OK if allow_prefix else BLOCK_REASON_NO_PREFIX
    print(json.dumps({"decision": "block", "reason": BLOCK_REASON_HEAD + tail}))


if __name__ == "__main__":
    main()
