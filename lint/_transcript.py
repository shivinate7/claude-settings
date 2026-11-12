"""Shared transcript readers for the hooks fired off a Stop event.

`lint/report_guard.py`, `hooks/decision_watch.py` and `hooks/feedback_guard.py` import this module, so the readers have one
copy. The send predicates (a send_message, an ArtifactData items write, the page writer id) live here too: the
feedback guard and the pick guard in report_guard both read them.

read_transcript / is_last_human / owner_text / tool_uses / records_after_last_human walk the JSONL
transcript and its `content` blocks. last_reply returns the text of the last assistant reply.
"""
import json
import os
import re

SEND_TOOLS = ("mcp__claude-code-remote__send_message", "SendMessage")
ARTIFACT_DATA = ("ArtifactData", "mcp__ArtifactData")
WRITE_VERBS = ("set", "update", "batch")


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
    # A cross-session reply is type user too, but it is a peer's words, never the owner's.
    return is_incoming(rec) and not _is_peer(rec.get("origin"))


def is_incoming(rec):
    """True for a message that starts a turn: a main-session user record with text and no tool
    result, whoever sent it. A lane's input is peer messages, which is_last_human skips."""
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


# A resumed session stores `api-request-blob` records: copies of earlier requests, with no timestamp. Their
# calls and results are not this turn's, so neither reader yields from one.
BLOB_TYPE = "api-request-blob"


def tool_uses(rec):
    if rec.get("type") == BLOB_TYPE:
        return
    msg = rec.get("message") or {}
    content = msg.get("content")
    if not isinstance(content, list):
        return
    for b in content:
        if isinstance(b, dict) and b.get("type") == "tool_use":
            yield b


def tool_results(rec):
    if rec.get("type") == BLOB_TYPE:
        return
    msg = rec.get("message") or {}
    content = msg.get("content")
    if not isinstance(content, list):
        return
    for b in content:
        if isinstance(b, dict) and b.get("type") == "tool_result":
            yield b


def failed_tool_use_ids(records):
    """The tool_use ids whose result failed, read two ways. A tool_result block with is_error true: a failed
    cloud send_message (measured). Or a user record whose toolUseResult is a dict with success false: a failed
    local SendMessage, which sets no is_error (measured)."""
    failed = set()
    for r in records:
        if r.get("type") != "user":
            continue
        tur = r.get("toolUseResult")
        no_success = isinstance(tur, dict) and tur.get("success") is False
        failed.update(b["tool_use_id"] for b in tool_results(r)
                      if isinstance(b.get("tool_use_id"), str) and (b.get("is_error") is True or no_success))
    return failed


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


def peer_sender(rec):
    """The id of the session that sent a peer message record (origin.fromSession), else None."""
    origin = rec.get("origin")
    found = origin.get("fromSession") if _is_peer(origin) else None
    return found if isinstance(found, str) and found else None


def last_incoming_index(records, acks=None):
    """Index of the last incoming message (is_incoming), or None when the transcript has none.

    `acks` maps a sender id to the send targets that reach it. A peer message from that sender, after a
    send of the same turn to one of those targets, is the ack of that send: it starts no turn, and the
    sends before it stay in the turn. The ack uses up that sender's targets, so only its first reply is an
    ack; a later message from it starts a turn."""
    found, sent = None, set()
    for i, rec in enumerate(records):
        if is_incoming(rec):
            reach = acks.get(peer_sender(rec), set()) if acks else set()
            if reach & sent:
                sent -= reach
                continue
            found, sent = i, set()
        elif acks and not rec.get("isSidechain"):
            for use in tool_uses(rec):
                sent |= send_targets(use)
    return found


def _in_items(d):
    return (d.get("collection") == "items"
            or any(isinstance(d.get(k), str) and d[k].startswith("items/") for k in ("doc_id", "path")))


def is_write(d):
    """False for a dict whose action or op is a verb other than set, update, batch."""
    verb = d.get("action", d.get("op"))
    return not isinstance(verb, str) or verb in WRITE_VERBS


def is_n(v, n):
    """True when the field value v is the item number n: an int (not a bool) or a digit string."""
    return (isinstance(v, int) and not isinstance(v, bool) and v == int(n)) or (
        isinstance(v, str) and v.isdigit() and int(v) == int(n))


def _has_n(node, n):
    if isinstance(node, dict):
        if not is_write(node):
            return False
        if is_n(node.get("n"), n):
            return True
        return any(_has_n(c, n) for c in node.values())
    return isinstance(node, list) and any(_has_n(c, n) for c in node)


def writes_n(node, n):
    """True when a write dict that names the items collection holds key n == n at any depth below it."""
    if isinstance(node, dict):
        if not is_write(node):
            return False
        return (_in_items(node) and _has_n(node, n)) or any(writes_n(c, n) for c in node.values())
    return isinstance(node, list) and any(writes_n(c, n) for c in node)


def items_write(node):
    """True when a set, update or batch call writes under the items collection at any depth: the page
    writer's own write of an item. A get, a list or another collection is no write to items."""
    if isinstance(node, dict):
        if not is_write(node):
            return False
        return _in_items(node) or any(items_write(c) for c in node.values())
    return isinstance(node, list) and any(items_write(c) for c in node)


def send_targets(use):
    """The ids a send_message / SendMessage tool_use names (session_id and to), else an empty set."""
    inp = use.get("input")
    if use.get("name") not in SEND_TOOLS or not isinstance(inp, dict):
        return set()
    return {v for v in (inp.get("session_id"), inp.get("to")) if isinstance(v, str)}


def result_text(block):
    body = block.get("content")
    if isinstance(body, list):
        body = "".join(b.get("text", "") for b in body if isinstance(b, dict))
    return body if isinstance(body, str) else ""


def delivered_tool_use_ids(records):
    """The tool_use ids of sends that reached their session: a tool_result whose text parses as the cloud
    send_message success body {"status": "delivered"}, and no failure by `failed_tool_use_ids`. Only that cloud
    body counts: the local SendMessage success shape is not measured, so it fails closed."""
    failed = failed_tool_use_ids(records)
    delivered = set()
    for r in records:
        if r.get("type") != "user":
            continue
        for b in tool_results(r):
            use_id = b.get("tool_use_id")
            if not isinstance(use_id, str) or use_id in failed:
                continue
            try:
                body = json.loads(result_text(b))
            except ValueError:
                continue
            if isinstance(body, dict) and body.get("status") == "delivered":
                delivered.add(use_id)
    return delivered


def _finds_writer(node):
    if isinstance(node, dict):
        if isinstance(node.get("writer"), str) and node["writer"]:
            return node["writer"]
        for child in node.values():
            found = _finds_writer(child)
            if found:
                return found
    elif isinstance(node, list):
        for child in node:
            found = _finds_writer(child)
            if found:
                return found
    return None


def _page_reads(records):
    """(ran, writer): whether the main session ran an ArtifactData get of meta/page, and the `writer` string
    in the newest such result, else None."""
    pending, writer, ran = set(), None, False
    for rec in records:
        if rec.get("isSidechain"):
            continue
        for use in tool_uses(rec):
            inp = use.get("input")
            if (str(use.get("name", "")).startswith(ARTIFACT_DATA) and isinstance(inp, dict)
                    and inp.get("action") == "get"
                    and (inp.get("path") == "meta/page"
                         or (inp.get("collection") == "meta" and inp.get("doc_id") == "page"))):
                pending.add(use.get("id"))
                ran = True
        content = (rec.get("message") or {}).get("content")
        for block in content if isinstance(content, list) else ():
            if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("tool_use_id") in pending:
                text = result_text(block)
                try:
                    found = _finds_writer(json.loads(text))
                except ValueError:
                    m = re.search(r'"writer"\s*:\s*"([^"]+)"', text)
                    found = m.group(1) if m else None
                if found:
                    writer = found
    return ran, writer


def page_writer_id(records):
    """The `writer` string in the newest ArtifactData get of meta/page result in the main session, else None."""
    return _page_reads(records)[1]


def page_read_ran(records):
    """True when the main session ran an ArtifactData get of meta/page, whatever its result named."""
    return _page_reads(records)[0]


# ---- the finish of a background job or agent: the one reader hooks/stall_watch.py and hooks/guard_merge.py share.
# agent_state reads an Agent or Task spawn. A Workflow agent has no such spawn, so workflow_agent below reads its finish.
# No watcher side effects: each function reads what it is given. The notice tag (hooks/shared_names.py
# TASK_NOTIFICATION_TAG) is a parameter, since lint/ does not import hooks/. A tag of None reads no notice.
TERMINAL = ("completed", "failed", "killed", "stopped")
RUNNING, FINISHED, UNKNOWN = "running", "finished", "unknown"
LAUNCHED = "async_launched"
STOP_TOOL = "TaskStop"
TASK_ID = re.compile(r"<task-id>(.*?)</task-id>", re.S)
TOOL_USE_ID = re.compile(r"<tool-use-id>(.*?)</tool-use-id>", re.S)
TASK_STATUS = re.compile(r"<status>(.*?)</status>", re.S)
STOPPED = re.compile(r"\s*Successfully stopped task: (\S+)")


def text_of(content):
    """The text of a message content: a string, or the text and tool_result strings of a list."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = [b.get("text") or b.get("content") for b in content if isinstance(b, dict)]
    return "\n".join(p for p in parts if isinstance(p, str))


def notice_blocks(text, tag):
    """[(task id, tool use id, status)] for each <task-notification> block in text. An id or the status the block
    does not carry is None; the status is lower-cased and stripped. A block with neither id is left out."""
    blocks = []
    if not tag or not isinstance(text, str):
        return blocks
    for note in text.split(tag)[1:]:
        tid, uid, st = TASK_ID.search(note), TOOL_USE_ID.search(note), TASK_STATUS.search(note)
        if tid or uid:
            blocks.append((tid.group(1).strip() if tid else None, uid.group(1).strip() if uid else None,
                           st.group(1).strip().lower() if st else None))
    return blocks


def closed_by_notice(text, tag):
    """The task ids of the <task-notification> blocks in text with a terminal status."""
    return [tid for tid, _uid, st in notice_blocks(text, tag) if tid and st in TERMINAL]


def stopped_ids(content):
    """The id a TaskStop result closes: its message starts 'Successfully stopped task: <id>'. The
    result is a JSON string with a message field; the whole id is matched, never a prefix."""
    content = text_of(content)
    try:
        body = json.loads(content)
        msg = body["message"] if isinstance(body, dict) else content
    except Exception:
        msg = content
    m = STOPPED.match(msg) if isinstance(msg, str) else None
    return [m.group(1)] if m else []


def notice_text(rec):
    """The text a record can carry a notice in: a queued_command attachment's prompt, a queue-operation's
    content, or a user message's content."""
    kind = rec.get("type")
    if kind == "attachment":
        att = rec.get("attachment")
        return att.get("prompt") if isinstance(att, dict) else ""
    if kind == "queue-operation":
        return rec.get("content")
    if kind == "user":
        return text_of((rec.get("message") or {}).get("content"))
    return ""


def agent_state(records, tool_use_id, tag):
    """RUNNING, FINISHED or UNKNOWN for the Agent or Task spawn whose call id is `tool_use_id`.
    FINISHED: the result is a plain tool_result (no toolUseResult) or a toolUseResult with a terminal status
    (a foreground spawn), or a background launch whose agent id a terminal notice or a TaskStop result later closed.
    RUNNING: an async_launched result and no such close. UNKNOWN: anything else the read cannot place, never
    FINISHED: no result, an error result, a toolUseResult of another shape, a launch with no agentId, or a notice
    that names the spawn with no or a non-terminal status. A notice names the spawn by its tool use id or its agent id.
    `records` are the main session's, in order."""
    found = None
    for i, rec in enumerate(records):
        for res in tool_results(rec):
            if res.get("tool_use_id") == tool_use_id:
                found = (i, rec, res)
    if found is None or found[2].get("is_error") is True:
        return UNKNOWN
    at, rec, _res = found
    if "toolUseResult" not in rec:
        return FINISHED
    launch = rec["toolUseResult"]
    if not isinstance(launch, dict):
        return UNKNOWN
    status = launch.get("status")
    if isinstance(status, str) and status.strip().lower() in TERMINAL:
        return FINISHED
    agent = launch.get("agentId")
    if status != LAUNCHED or not isinstance(agent, str) or not agent:
        return UNKNOWN
    stops, unclear = set(), False
    for later in records[at + 1:]:
        for tid, uid, st in notice_blocks(notice_text(later), tag):
            if tid == agent or uid == tool_use_id:
                if st in TERMINAL:
                    return FINISHED
                unclear = True
        for use in tool_uses(later):
            if use.get("name") == STOP_TOOL and isinstance(use.get("id"), str):
                stops.add(use["id"])
        for res in tool_results(later):
            if res.get("tool_use_id") in stops and agent in stopped_ids(res.get("content")):
                return FINISHED
    return UNKNOWN if unclear else RUNNING


# ---- the finish of a Workflow agent: it has no Agent or Task spawn in the transcript, so agent_state cannot place it.
# This is the one reader of a Workflow agent's finish; hooks/guard_merge.py resume_finished_hit calls agent_state for a
# spawn and workflow_agent for a name no spawn holds. Its run's journal, beside the transcript at
# <transcript minus .jsonl>/subagents/workflows/<runId>/journal.jsonl, holds a `started` line (agentId, label) and,
# once the agent finishes, a `result` line. A stopped agent leaves only the `started` line (measured, run
# wf_cc6c76b5-d5f), so the run record <transcript minus .jsonl>/workflows/<runId>.json settles it: its status is
# `killed` for a stopped run and `completed` for a finished one (same run). Its role is `agentType` in
# agent-<agentId>.meta.json beside the journal; a meta with `spawnedWithWorktree` true marks an agent spawned with
# isolation worktree (measured, run wf_19ac2aae-ebb).
WORKFLOWS_DIR = os.path.join("subagents", "workflows")
RUN_RECORDS_DIR = "workflows"
RUN_RECORD_FINISHED = ("killed", "completed")
_AGENT_ID = re.compile(r"[A-Za-z0-9_.-]+")


def _agent_meta(run_dir, agent_id):
    """The agent's meta file as a dict, or {} when the id is no plain file name, or the file is missing, unreadable or
    not an object."""
    if not _AGENT_ID.fullmatch(agent_id):
        return {}
    try:
        with open(os.path.join(run_dir, "agent-%s.meta.json" % agent_id), encoding="utf-8") as f:
            meta = json.load(f)
    except Exception:
        return {}
    return meta if isinstance(meta, dict) else {}


def _run_record_state(transcript, run):
    """FINISHED when the run record's status is killed or completed, RUNNING when the record is missing, UNKNOWN when
    it is unreadable, is not an object, or holds another status."""
    path = os.path.join(os.path.splitext(transcript)[0], RUN_RECORDS_DIR, run + ".json")
    try:
        with open(path, encoding="utf-8") as f:
            record = json.load(f)
    except FileNotFoundError:
        return RUNNING
    except Exception:
        return UNKNOWN
    status = record.get("status") if isinstance(record, dict) else None
    if isinstance(status, str) and status.strip().lower() in RUN_RECORD_FINISHED:
        return FINISHED
    return UNKNOWN


def workflow_agent(transcript, target):
    """(state, agent_type, worktree) for the Workflow agent that `target` names by its agentId or its started line's label, or
    None when no journal beside `transcript` names it. The latest started line that matches wins: a later line in a
    journal, and a run whose journal was written later. state is FINISHED when the journal holds a result line for the
    id. With only a started line, the run record settles it (_run_record_state): FINISHED when killed or completed,
    RUNNING when there is no record, UNKNOWN when it cannot be read. State is also UNKNOWN when a journal in the folder
    exists but cannot be read and none names the target. agent_type is the meta file's agentType, or None. worktree is
    True when the meta shows spawnedWithWorktree true. Reads only that transcript's own folders, and only when called:
    one directory listing and one read per journal, then for the one agent that wins, one meta read, and one run-record
    read when it has no result line."""
    root = os.path.join(os.path.splitext(transcript)[0], WORKFLOWS_DIR)
    try:
        runs = [entry for entry in os.scandir(root) if entry.is_dir()]
    except OSError:
        return None
    journals = []
    for entry in runs:
        path = os.path.join(entry.path, "journal.jsonl")
        try:
            journals.append((os.stat(path).st_mtime_ns, entry.name, entry.path, path))
        except OSError:
            continue
    best, unreadable = None, False
    for _mtime, name, run_dir, path in sorted(journals):
        try:
            records = read_transcript(path)
        except OSError:
            unreadable = True
            continue
        results = {rec.get("agentId") for rec in records if rec.get("type") == "result"}
        for rec in records:
            agent_id = rec.get("agentId")
            if (rec.get("type") == "started" and isinstance(agent_id, str) and agent_id
                    and target in (agent_id, rec.get("label"))):
                best = (name, run_dir, agent_id, agent_id in results)
    if best is None and unreadable:
        return UNKNOWN, None, False
    if best is None:
        return None
    run, run_dir, agent_id, has_result = best
    meta = _agent_meta(run_dir, agent_id)
    kind = meta.get("agentType")
    state = FINISHED if has_result else _run_record_state(transcript, run)
    return (state, kind.strip() if isinstance(kind, str) and kind.strip() else None,
            meta.get("spawnedWithWorktree") is True)
