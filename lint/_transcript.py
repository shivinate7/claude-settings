"""Shared transcript readers for the hooks fired off a Stop event.

`lint/report_guard.py`, `hooks/decision_watch.py` and `hooks/feedback_guard.py` import this module, so the readers have one
copy.

read_transcript / is_last_human / owner_text / tool_uses / records_after_last_human walk the JSONL
transcript and its `content` blocks. last_reply returns the text of the last assistant reply.
"""
import json
import os


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


def _is_peer(origin):
    return isinstance(origin, dict) and origin.get("kind") == "peer"


def is_last_human(rec):
    if rec.get("type") != "user":
        return False
    if rec.get("isSidechain"):
        return False
    # A cross-session reply is type user too, but it is a peer's words, never the owner's.
    if _is_peer(rec.get("origin")):
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


def owner_text(rec, notice_tags=()):
    """The text of an owner message record, or None for any other record.

    An owner message is a user record that is_last_human accepts, or a queued_command attachment
    (an owner message typed while the session runs; its text is attachment.prompt) with no peer
    origin. Text that starts with one of `notice_tags` (shared_names.MACHINE_TAGS) is a machine
    notice, never the owner's: the notice queued while a task runs is a queued_command too.
    """
    if rec.get("type") == "user":
        text = (rec.get("message") or {}).get("content") if is_last_human(rec) else None
    elif rec.get("type") == "attachment" and not rec.get("isSidechain"):
        att = rec.get("attachment")
        if (not isinstance(att, dict) or att.get("type") != "queued_command"
                or _is_peer(rec.get("origin")) or _is_peer(att.get("origin"))):
            return None
        text = att.get("prompt")
    else:
        return None
    if isinstance(text, list):
        text = "\n".join(b["text"] for b in text if isinstance(b, dict) and b.get("type") == "text"
                         and isinstance(b.get("text"), str))
    if not isinstance(text, str) or (notice_tags and text.strip().startswith(tuple(notice_tags))):
        return None
    return text


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
