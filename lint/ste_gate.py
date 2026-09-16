#!/usr/bin/env python3
"""Claude Code hook: Simplified Technical English gate.

Reads the hook JSON on stdin. Runs the vendored ste_lint.py next to this file at error
severity only. Prints JSON when there is something to say. Always exits 0.

PreToolUse on Write, Edit, MultiEdit for a *.md path: deny the write when the new text has
STE errors, and hand the findings back so the writer fixes them first.

Stop: block the turn once when the last reply has STE errors. When stop_hook_active is set
the reply is already a rewrite, so the gate lets it through.
"""
import json
import os
import subprocess
import sys
import tempfile

MD_SUFFIXES = (".md", ".markdown")
NOTE = "Code in backticks or a fence is exempt. Errors only: sentence length, semicolon, Latin abbreviation, contraction."


def lint(linter, text):
    """Return the error-level findings of ste_lint.py on text, as lines."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "gate.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        try:
            run = subprocess.run(
                [sys.executable, linter, "--no-color", "--format", "json", "--fail-on", "never", path],
                capture_output=True, text=True, timeout=15,
            )
            data = json.loads(run.stdout or "{}")
        except Exception:
            return []
    out = []
    for f in data.get("findings", []):
        if f.get("severity") != "error":
            continue
        out.append("line %s: %s %s" % (f.get("line"), f.get("code"), f.get("message")))
    return out


def last_reply(hook):
    text = hook.get("last_assistant_message")
    if text:
        return text
    path = hook.get("transcript_path")
    if not path or not os.path.exists(path):
        return ""
    text = ""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("type") != "assistant":
                    continue
                parts = [b.get("text", "") for b in (rec.get("message") or {}).get("content", [])
                         if isinstance(b, dict) and b.get("type") == "text"]
                if parts:
                    text = "\n".join(parts)
    except Exception:
        return ""
    return text


def main():
    try:
        hook = json.load(sys.stdin)
    except Exception:
        return
    linter = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ste_lint.py")
    if not os.path.exists(linter):
        return
    event = hook.get("hook_event_name")

    if event == "PreToolUse":
        tool = hook.get("tool_name")
        ti = hook.get("tool_input") or {}
        path = ti.get("file_path") or ""
        if not path.lower().endswith(MD_SUFFIXES):
            return
        if tool == "Write":
            text = ti.get("content") or ""
        elif tool == "Edit":
            text = ti.get("new_string") or ""
        elif tool == "MultiEdit":
            text = "\n\n".join((e or {}).get("new_string") or "" for e in ti.get("edits") or [])
        else:
            return
        findings = lint(linter, text)
        if not findings:
            return
        reason = "STE lint on the text for %s:\n%s\n%s Fix the text, then write again." % (
            os.path.basename(path), "\n".join(findings), NOTE)
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }}))
        return

    if event == "Stop":
        if hook.get("stop_hook_active"):
            return
        text = last_reply(hook)
        if not text.strip():
            return
        findings = lint(linter, text)
        if not findings:
            return
        reason = "STE lint on your last reply:\n%s\n%s Rewrite the reply, then stop." % (
            "\n".join(findings), NOTE)
        print(json.dumps({"decision": "block", "reason": reason}))


if __name__ == "__main__":
    main()
