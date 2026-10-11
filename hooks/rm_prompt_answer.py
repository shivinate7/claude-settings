#!/usr/bin/env python3
"""PermissionRequest hook on Bash: answer allow for a delete whose every variable is guarded.

Decision rm-on-a-variable-needs-a-guard (owner ruling, 2026-10-11), item 2. It answers allow only
when the whole command is `rm` commands, simple assignments and `for` loops, and each `rm` target
has every expansion written `${NAME:?}`. A target with `$HOME`, a command substitution, an
unguarded expansion or a literal critical path gets no output, so the owner is still asked. Bad
input gets no output and exit 0. The shell reading comes from guard.py (`rm_call`, `RM_GUARDED`).
KNOWN LIMIT: `:?` stops an empty variable only. Assignment and loop values must be literals, and
`..`, `~`, the root or a top-level folder in one of them is a prompt.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard  # noqa: E402

ALLOW = {"hookSpecificOutput": {"hookEventName": "PermissionRequest",
                                "decision": {"behavior": "allow"}}}
# What may remain in a word once its guarded expansions are removed.
_UNSAFE = re.compile(r"[$`<>&()\\]")
_FLAG = re.compile(r"^(-[A-Za-z]+|--)$")


def critical(value: str) -> bool:
    """True for a literal that names the home folder, a parent, the root or a top-level folder."""
    parts = [p for p in value.split("/") if p and p != "."]
    return (value.startswith("~") or ".." in parts or value in (".", "")
            or (value.startswith("/") and len(parts) <= 1))


def literal_ok(word: str) -> bool:
    return not _UNSAFE.search(word) and not critical(word)


def segment_ok(segment: str) -> str:
    """Return "rm" for an allowed delete, "other" for an allowed assignment or loop, else ''."""
    tokens = guard.segment_tokens(segment)
    if not tokens:
        return ""
    if tokens in (["do"], ["done"]):
        return "other"
    if tokens[0] == "for" and len(tokens) >= 4 and tokens[2] == "in":
        return "other" if all(literal_ok(t) for t in tokens[3:]) else ""
    if all(guard.ASSIGNMENT.match(t) for t in tokens):
        return "other" if all(literal_ok(t.split("=", 1)[1]) for t in tokens) else ""
    call = guard.rm_call(segment)
    if not call:
        return ""
    ts, at, flags, targets, _ = call
    if ts[at] != "rm" or any(t != "do" for t in ts[:at]) or not targets:
        return ""
    if not all(_FLAG.match(w) for w in flags):
        return ""
    for word in targets:
        if _UNSAFE.search(guard.RM_GUARDED.sub("", word)):
            return ""
        if "$" not in word and not literal_ok(word.strip("'\"")):
            return ""
    return "rm"


def main() -> None:
    try:
        data = json.load(sys.stdin)
        command = data["tool_input"]["command"]
        if data.get("tool_name") != "Bash" or not isinstance(command, str):
            return
        kinds = [segment_ok(s) for s in guard.split_segments(command) if s.strip()]
    except Exception:
        return
    if kinds and all(kinds) and "rm" in kinds:
        print(json.dumps(ALLOW))


if __name__ == "__main__":
    main()
