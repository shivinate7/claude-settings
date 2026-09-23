#!/usr/bin/env python3
"""Claude Code hook: Simplified Technical English gate.

Reads the hook JSON on stdin. Runs the vendored ste_lint.py next to this file at error
severity only. Prints JSON when there is something to say. Always exits 0.

PreToolUse on Write, Edit, MultiEdit for a *.md path: deny the write when the new text has
STE errors, and hand the findings back so the writer fixes them first.

SCOPING TO CHANGED BLOCKS. This hook sees the proposed content before the write lands. It
replays the tool's own edit onto the file currently on disk to get the FULL proposed text,
the same content the write would leave behind, then lints only the BLOCKS that differ from
disk. A block is a paragraph, a run of lines bounded by blank lines: STE001 is a sentence
rule and a sentence can run over more than one line, reported at the line it starts on, so a
plain line filter could drop a finding whose sentence starts outside the edit. A sentence
never crosses a blank line, so filtering by block instead of by line closes that hole.

A file that does not exist on disk yet is entirely new, so it lints in full. So does a Write
or Edit this hook cannot replay onto disk content alone, an Edit whose `old_string` is not on
disk, or matched more than once without `replace_all`: rather than guess which blocks
changed, it lints the whole proposed text, the strict, no-worse-than-before default.
"""
import difflib
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _transcript import paragraph_blocks, format_finding  # noqa: E402

MD_SUFFIXES = (".md", ".markdown")
NOTE = ("Code in backticks or a fence is exempt. Errors only: sentence length, nominalization, "
        "semicolon, Latin abbreviation, contraction, phrasal verb, bloat, double negative, "
        "condition order, omitted 'that', gendered language.")


def lint(linter, text):
    """Return the error-level findings of ste_lint.py on text, as finding dicts."""
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
    return [f for f in data.get("findings", []) if f.get("severity") == "error"]


# paragraph_blocks and format_finding live in lint/_transcript.py, imported above. This hook,
# lint/md_sweep.py, lint/report_gate.py, and hooks/config_report.py share that one copy;
# hooks/config_report.py already imports lint/report_gate.py, which already imports this
# module, so the readers these hooks share are no longer split one-per-file.

# ------------------------------------------------------------------ scoping to changed blocks

def changed_new_lines(old_text, new_text):
    """Return the 1-indexed lines of `new_text` that differ from `old_text`.

    A pure deletion, text removed with nothing put in its place, has no line of its own in
    `new_text`. Both the line before and the line after the point it sat at are counted as
    changed instead, so the block on either side of a deletion is still caught.
    """
    old_lines = old_text.split("\n")
    new_lines = new_text.split("\n")
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    changed = set()
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if j2 > j1:
            changed.update(range(j1 + 1, j2 + 1))
        else:
            changed.add(j1 + 1)
            if j1 > 0:
                changed.add(j1)
    return changed


def scope_of_change(old_text, new_text):
    """Return the lines of `new_text` in scope for linting: every line of every block that
    differs from `old_text`. Empty when the two texts are identical."""
    changed = changed_new_lines(old_text, new_text)
    if not changed:
        return set()
    in_scope = set()
    for start, end in paragraph_blocks(new_text):
        if any(n in changed for n in range(start, end + 1)):
            in_scope.update(range(start, end + 1))
    return in_scope


def apply_edit(text, old_string, new_string, replace_all):
    """Return `text` with `old_string` replaced by `new_string`, the way the Edit tool itself
    resolves a replacement, or None when that cannot be resolved from `text` alone:
    `old_string` empty or absent, or present more than once without `replace_all`.
    """
    if not old_string:
        return None
    count = text.count(old_string)
    if count == 0:
        return None
    if replace_all:
        return text.replace(old_string, new_string)
    if count > 1:
        return None
    index = text.find(old_string)
    return text[:index] + new_string + text[index + len(old_string):]


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
                if not isinstance(rec, dict) or rec.get("type") != "assistant":
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
    if not isinstance(hook, dict):
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

        try:
            with open(path, "r", encoding="utf-8") as f:
                old_text = f.read()
        except Exception:
            old_text = None  # no file on disk yet: entirely new, lint in full

        # `resolved` holds the full proposed content once known. None means the edit could
        # not be replayed against disk content alone, so the fallback text below is linted
        # in full rather than guessed at.
        resolved = None
        if tool == "Write":
            text = ti.get("content") or ""
            resolved = text
        elif tool == "Edit":
            text = ti.get("new_string") or ""
            if old_text is not None:
                resolved = apply_edit(old_text, ti.get("old_string") or "", text,
                                       bool(ti.get("replace_all")))
        elif tool == "MultiEdit":
            edits = ti.get("edits") or []
            text = "\n\n".join((e or {}).get("new_string") or "" for e in edits)
            if old_text is not None:
                resolved = old_text
                for e in edits:
                    e = e or {}
                    applied = apply_edit(resolved, e.get("old_string") or "",
                                          e.get("new_string") or "", bool(e.get("replace_all")))
                    if applied is None:
                        resolved = None
                        break
                    resolved = applied
        else:
            return

        if old_text is None or resolved is None:
            scope = None  # new file, or an edit this hook could not replay: lint in full
            full_text = resolved if resolved is not None else text
        else:
            full_text = resolved
            scope = scope_of_change(old_text, full_text)

        findings = lint(linter, full_text)
        if scope is not None:
            findings = [f for f in findings if f.get("line") in scope]
        if not findings:
            return
        lines = [format_finding(f) for f in findings]
        reason = "STE lint on the text for %s:\n%s\n%s Fix the text, then write again." % (
            os.path.basename(path), "\n".join(lines), NOTE)
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }}))


if __name__ == "__main__":
    main()
