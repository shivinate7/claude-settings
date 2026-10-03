"""Shared transcript readers for the hooks fired off a Stop event.

`hooks/decision_watch.py`'s config report section already imports `lint/report_gate.py`, which
already imports `lint/ste_gate.py`. The "no import between two
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
import os
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


def parse_utc_timestamp(text):
    """Epoch seconds for a transcript `timestamp` (a trailing Z is read as UTC), or None."""
    from datetime import datetime, timezone  # lazy: ste_gate runs on every Write
    text = (text or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except Exception:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.timestamp()


def _lines_backwards(path, chunk=1 << 18):
    """Yield the transcript's lines (bytes), last first, reading only as far as asked."""
    with open(path, "rb") as f:
        pos = f.seek(0, 2)
        carry = b""
        while pos > 0:
            n = min(chunk, pos)
            pos -= n
            f.seek(pos)
            lines = (f.read(n) + carry).split(b"\n")
            carry = lines[0] if pos > 0 else b""
            for line in reversed(lines[1:] if pos > 0 else lines):
                yield line


def read_turn(path):
    """Return (last human record or None, the records after it), read from the END.

    The same answer as `records_after_last_human(read_transcript(path))`, for the cost of
    this turn's records alone. Raises OSError when the file cannot be read.
    """
    after = []
    for line in _lines_backwards(path):
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if not isinstance(rec, dict):
            continue
        if is_last_human(rec):
            return rec, after[::-1]
        after.append(rec)
    return None, []


def last_human_epoch(path):
    """Epoch seconds of the last human message, or None.

    None means "no human record, no timestamp, or unreadable": callers read it as "cannot tell"
    and keep running. A line is parsed only when it mentions "user", so an idle turn costs a
    few KB of reads, not the whole file.
    """
    try:
        for line in _lines_backwards(path):
            if b'"user"' not in line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if isinstance(rec, dict) and is_last_human(rec):
                value = rec.get("timestamp")
                return parse_utc_timestamp(value) if isinstance(value, str) else None
    except Exception:
        return None
    return None


def _git(cwd, *args):
    import subprocess  # lazy, same reason
    try:
        run = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True,
                             timeout=10)
    except Exception:
        return None
    return run.stdout if run.returncode == 0 else None


def head_moved_since(cwd, base):
    """True when HEAD took a commit (or any move) after `base`, False when not, None if unknown.

    Reads HEAD's reflog mtime, with no subprocess: every commit appends to it. A checkout or
    reset also touches it, which only ever answers True, the safe side. With no reflog file
    it returns None, and the caller asks `git log` itself.
    """
    here = os.path.realpath(cwd)
    while True:
        dot = os.path.join(here, ".git")
        if os.path.isdir(dot):
            gitdir = dot
            break
        if os.path.isfile(dot):  # a linked work tree: `gitdir: <path>`
            try:
                with open(dot, encoding="utf-8") as f:
                    line = f.readline().strip()
            except OSError:
                return None
            if not line.startswith("gitdir:"):
                return None
            gitdir = os.path.join(here, line[7:].strip())
            break
        parent = os.path.dirname(here)
        if parent == here:
            return None
        here = parent
    reflog = os.path.join(gitdir, "logs", "HEAD")
    try:
        return os.path.getmtime(reflog) >= base - 1
    except OSError:
        return None


def landed_work(path, cwd):
    """The early exit for a Stop hook that scans dirty files: False only when none is newer.

    False means the last human message is known, and since it no file under `cwd` is dirty
    in the work tree with a newer mtime (a deleted one counts as newer). Any read that cannot
    run, a missing timestamp, no work tree, a stat error, answers True, so the hook runs as it
    did before. A commit alone is not a signal: a hook that scans only dirty files cannot get
    a target from one. A hook whose fire has another cause (a clock, a baseline, a PR merge)
    adds its own check beside this call.
    """
    base = last_human_epoch(path)
    if base is None or not cwd or not os.path.isdir(cwd):
        return True
    try:
        status = _git(cwd, "status", "--porcelain", "-z", "--untracked-files=all", "--", ".")
        if status is None:
            return True
        fields = status.split("\0")
        i = 0
        while i < len(fields):
            entry = fields[i]
            i += 1
            if not entry:
                continue
            if entry[0] in "RC":
                i += 1  # the rename/copy source path, not a target
            # A deleted file has no mtime: getmtime raises, and the except below answers True.
            if os.path.getmtime(os.path.join(cwd, *entry[3:].split("/"))) > base:
                return True
        return False
    except Exception:
        return True


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
