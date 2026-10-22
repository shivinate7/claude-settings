"""Shared transcript readers for the hooks fired off a Stop event.

`lint/report_gate.py` and `hooks/decision_watch.py` import this module, so the readers have one
copy.

read_transcript / is_last_human / tool_uses / records_after_last_human walk the JSONL transcript
and its `content` blocks. last_reply returns the text of the last assistant reply.

format_finding turns an STE-lint finding's `message` into text for a person or the model to read.
That text is attacker-reachable: ste_lint.py's STE003, STE007, STE008, STE009, STE011, STE013,
STE015 and STE017 rules build a finding's message with %r around a substring matched out of the
file under lint. `safe_finding_text` gives it the same treatment hooks/guard.py's `cap_safe`
gives a tool-supplied reason, so a crafted value cannot print a line of its own that reads like an
approval. It is copied, not imported, so this module does not depend on hooks/guard.py.
"""
import json
import os
import re
import subprocess
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
try:
    import _nowindow  # the one home of a no-window child start (hooks/_nowindow.py)
except ImportError:  # a hook never dies for a missing helper (it lands a moment after the hook in an install)
    _nowindow = subprocess

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


def last_reply(hook):
    """The last assistant reply's text: the hook's own field, else the last text in the transcript."""
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


def parse_utc_timestamp(text):
    """Epoch seconds for a transcript `timestamp` (a trailing Z is read as UTC), or None."""
    from datetime import datetime, timezone
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


def _lines_backwards(path, chunk=1 << 18, limit=None):
    """Yield the transcript's lines (bytes), last first, reading only as far as asked.
    `limit` caps the bytes read from the end; the line cut by the cap is dropped."""
    with open(path, "rb") as f:
        pos = f.seek(0, 2)
        stop = 0 if limit is None else max(0, pos - limit)
        carry = b""
        while pos > stop:
            n = min(chunk, pos - stop)
            pos -= n
            f.seek(pos)
            lines = (f.read(n) + carry).split(b"\n")
            carry = lines[0] if pos > 0 else b""
            for line in reversed(lines[1:] if pos > 0 else lines):
                yield line


def tail_records(path, limit):
    """Yield the transcript's records, last first, from the last `limit` bytes only."""
    for line in _lines_backwards(path, limit=limit):
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if isinstance(rec, dict):
            yield rec


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
    try:
        run = _nowindow.run(["git", "-C", cwd] + list(args), capture_output=True, encoding="utf-8", errors="replace",
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


def format_finding(f):
    return "line %s: %s %s" % (f.get("line"), f.get("code"), safe_finding_text(f.get("message")))
