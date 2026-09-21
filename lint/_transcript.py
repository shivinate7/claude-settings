"""Shared transcript readers for the hooks fired off a Stop event.

`hooks/config_report.py` already imports `lint/report_gate.py`, which already imports
`lint/ste_gate.py` (see `hooks/config_report.py`'s own docstring). The "no import between two
hooks fired by the same Stop event" rule that once justified copying these readers into each
hook is retired, so this module holds the one copy and the four hooks import it.

read_transcript / is_last_human / tool_uses / records_after_last_human walk the JSONL transcript
and its `content` blocks. paragraph_blocks / format_finding are the STE-lint-result helpers
`lint/ste_gate.py` and `lint/md_sweep.py` both used to carry.
"""
import json


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


def paragraph_blocks(text):
    """Return (start_line, end_line) 1-indexed ranges, one per run of non-blank lines.

    A block is a paragraph: lines bounded by blank lines. A blank line is one that is empty
    or holds only whitespace. This is the same unit ste_lint.py's own `segment_markdown`
    flushes a paragraph at, which is why a multi-line STE001 sentence, reported at the line
    it starts on, always lands inside the one block its later lines also belong to.
    """
    lines = text.split("\n")
    blocks = []
    start = None
    for i, line in enumerate(lines, start=1):
        if line.strip() == "":
            if start is not None:
                blocks.append((start, i - 1))
                start = None
        elif start is None:
            start = i
    if start is not None:
        blocks.append((start, len(lines)))
    return blocks


def format_finding(f):
    return "line %s: %s %s" % (f.get("line"), f.get("code"), f.get("message"))
