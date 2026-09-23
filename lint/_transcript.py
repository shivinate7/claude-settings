"""Shared transcript readers for the hooks fired off a Stop event.

`hooks/config_report.py` already imports `lint/report_gate.py`, which already imports
`lint/ste_gate.py` (see `hooks/config_report.py`'s own docstring). The "no import between two
hooks fired by the same Stop event" rule that once justified copying these readers into each
hook is retired, so this module holds the one copy and the four hooks import it.

read_transcript / is_last_human / tool_uses / records_after_last_human walk the JSONL transcript
and its `content` blocks. paragraph_blocks / format_finding are the STE-lint-result helpers
`lint/ste_gate.py` and `lint/md_sweep.py` both used to carry.

format_finding is also the one place both of those hooks turn a finding's `message` into text
for a reason a person or the model reads: ste_gate.py's permissionDecisionReason, live on every
Write, Edit and MultiEdit, and md_sweep.py's Stop block reason. That text is attacker-reachable:
ste_lint.py's STE003, STE007, STE008, STE009, STE011, STE013, STE015 and STE017 rules build a
finding's message with %r around a substring matched out of the file under lint, so a turn that
copies untrusted content into a markdown file puts that content into the next finding.
`safe_finding_text` gives it the same treatment hooks/guard.py's `cap_safe` gives a
tool-supplied reason, so a crafted value cannot print a line of its own that reads like an
approval, and copied rather than imported: lint/ste_gate.py and lint/md_sweep.py do not
otherwise depend on hooks/guard.py, and importing it here would give them that dependency
for the first time.
"""
import json
import re

FINDING_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
FINDING_MAX = 300
FINDING_CUT_MARK = " [cut]"


def safe_finding_text(text):
    """Return `text` fit to print inside a finding's line: control characters cleared,
    length capped with a marked cut. See the module docstring."""
    clean = FINDING_CONTROL.sub(" ", text or "")
    if len(clean) > FINDING_MAX:
        return clean[:FINDING_MAX] + FINDING_CUT_MARK
    return clean


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
    return "line %s: %s %s" % (f.get("line"), f.get("code"), safe_finding_text(f.get("message")))
