"""The one reader of a session's own get_session and create_session records in its transcript.

hooks/guard_merge.py (merge role, trust card, archive proofs) and lint/report_guard.py (lane or
owner-facing pick guard) both read it. It is its own small module so the Stop hook can import it
without loading the whole guard.
Cost: one transcript read per call, no file written. An agent's own record is a second file read, by the
caller, through agent_transcript_path.
"""
import json
import os
import re

# A get_session result for another session arrives as its untrusted text: an opening tag with a nonce, a preamble,
# the record, then a closing tag. Only a closing tag with the opening nonce ends the wrapper.
_OTHER_SESSION = re.compile(
    r'<other-session nonce="([0-9A-Fa-f]+)" untrusted="true">(.*)</other-session nonce="\1">', re.DOTALL)
_CREATED_ID = re.compile(r"session_[A-Za-z0-9_-]+")


def _created_session_id(body):
    """The id a create_session result names: the `id` or `session_id` of a JSON object, else the first
    `session_...` word of the body. None when the result names none."""
    if not isinstance(body, str):
        return None
    try:
        parsed = json.loads(body)
    except ValueError:
        parsed = None
    if isinstance(parsed, dict):
        for key in ("id", "session_id"):
            if isinstance(parsed.get(key), str):
                return parsed[key]
    found = _CREATED_ID.search(body)
    return found.group(0) if found else None


def _record_json(body):
    """The record a get_session body holds: bare JSON, or the one JSON object a nonce-matched wrapper holds.
    Anything else raises ValueError: text after the object, a closer with another nonce, an open wrapper."""
    wrapped = _OTHER_SESSION.fullmatch(body.strip())
    if not wrapped:
        return json.loads(body)
    inner = wrapped.group(2)
    start = inner.index("{")  # ValueError when the wrapper holds no object
    record, end = json.JSONDecoder().raw_decode(inner, start)
    if inner[end:].strip():
        raise ValueError("text after the record")
    return record


def agent_transcript_dir(transcript):
    """The folder the harness writes a session's agents' transcripts to: `<transcript minus .jsonl>/subagents`.
    The one home of that layout: the guards, the stall watch, the report guard and the ruling census all name
    it through here. Cost: a string join, no read, no file written."""
    root = transcript[:-len(".jsonl")] if transcript.endswith(".jsonl") else transcript
    return os.path.join(root, "subagents")


def agent_transcript_path(transcript, agent_id):
    """The agent's own transcript: `agent-<agent_id>.jsonl` in agent_transcript_dir. The caller passes an agent_id
    already checked against guard.AGENT_ID."""
    return os.path.join(agent_transcript_dir(transcript), "agent-" + agent_id + ".jsonl")


def own_session_read(transcript, own_id, created=False):
    """(tags, tagged_after, parent): the tags and parent_session_id of the newest get_session result
    whose ccr.id is own_id, else None for each, and whether a set_session_tags call follows that
    result. With `created`, a create_session call whose result names own_id is a record too: its tags
    are the call's input.tags, its parent is None unless the input names parent_session_id. The newest
    record of either kind decides. Without it, only get_session counts."""
    return _scan(transcript, own_id, created)[:3]


def own_session_ccr(transcript, own_id):
    """The whole `ccr` dict of the newest get_session result whose ccr.id is own_id, else None. The
    branch and source fields of the record are read from it (lane-closes-after-records).

    Never raises, because the guard's checks must not crash on any input. A transcript it cannot read
    (no path, a missing file, a folder, bad text) is None, the same as "no record"; a caller that needs
    the record treats None as no record. The type check comes first because open() reads an int as a file
    descriptor and would open, then close, a descriptor the caller owns."""
    if not isinstance(transcript, (str, os.PathLike)):
        return None
    try:
        return _scan(transcript, own_id, False)[3]
    except (OSError, TypeError, ValueError, RecursionError):
        return None


def _scan(transcript, own_id, created):
    """(tags, tagged_after, parent, ccr): the one pass over the transcript behind both readers."""
    uses, newest, parent, tagged_after, newest_ccr = set(), None, None, False, None
    creates = {}  # tool_use id -> (tags, parent) a create_session call set
    with open(transcript, encoding="utf-8") as handle:
        for line in handle:
            try:
                content = json.loads(line)["message"]["content"]
            except (ValueError, KeyError, TypeError):
                continue
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use" and str(block.get("name", "")).endswith("get_session"):
                    uses.add(block.get("id"))
                elif created and block.get("type") == "tool_use" and str(block.get("name", "")).endswith("create_session"):
                    given = block.get("input", {}).get("tags") if isinstance(block.get("input"), dict) else None
                    if isinstance(given, list):
                        named = block["input"].get("parent_session_id")
                        creates[block.get("id")] = ([str(t) for t in given], named if isinstance(named, str) and named else None)
                elif block.get("type") == "tool_use" and str(block.get("name", "")).endswith("set_session_tags"):
                    # Only a call that names the own session changes the own tags. A call with no readable
                    # list of ids counts too: the safe reading is that it may have named this session.
                    ids = (block.get("input") or {}).get("session_ids") if isinstance(block.get("input"), dict) else None
                    if not isinstance(ids, list) or own_id in ids:
                        tagged_after = True
                elif block.get("type") == "tool_result" and (block.get("tool_use_id") in uses or block.get("tool_use_id") in creates):
                    body = block.get("content")
                    if isinstance(body, list):
                        body = "".join(b.get("text", "") for b in body if isinstance(b, dict))
                    if block.get("tool_use_id") in creates:
                        if _created_session_id(body) == own_id:
                            (newest, parent), tagged_after, newest_ccr = creates[block.get("tool_use_id")], False, None
                        continue
                    if not isinstance(body, str):
                        continue
                    try:
                        ccr = _record_json(body)["ccr"]
                        if ccr["id"] == own_id and isinstance(ccr["tags"], list):
                            newest, tagged_after, newest_ccr = ccr["tags"], False, ccr
                            found = ccr.get("parent_session_id")
                            parent = found if isinstance(found, str) and found else None
                    except (ValueError, KeyError, TypeError):
                        continue
    return newest, tagged_after, parent, newest_ccr


def _list_rows(body):
    """(rows, has_more) of a list_sessions body: `{"ccr": {"data": [rows], "has_more": bool}}`, bare or in the
    untrusted wrapper. Each row is (id, tags, archived). Raises ValueError, KeyError, TypeError or AttributeError when
    the body is not that."""
    ccr = _record_json(body)["ccr"]
    rows, more = ccr["data"], ccr["has_more"]
    if not isinstance(rows, list) or not isinstance(more, bool):
        raise ValueError("not a list page")
    found = []
    for row in rows:
        tags = row.get("tags") or []
        if not isinstance(row.get("id"), str) or not isinstance(tags, list):
            raise ValueError("not a session row")
        found.append((row["id"], [str(t) for t in tags], "ARCHIVED" in str(row.get("session_status", "")).upper()))
    return found, more


def list_sessions_read(transcript):
    """(rows, whole) of the list_sessions reads in a transcript (rule lane-step-dup). `rows` maps each session id a read
    showed to (tags, archived), the newest row deciding. `whole` is True when one chain of reads is the whole list: a
    read with no cursor, then reads whose after_id is the previous page's last row id, the last with has_more false.
    A tags, mine or before_id read lists only part of the sessions and breaks a chain, as does an after_id that is not
    the previous page's last row id. A read whose text does not parse adds no rows and breaks the chain. A whole read
    stays whole after later reads, because every session they show is a row here.
    Cost: one read of the transcript; no file written, no process."""
    rows, whole, chain = {}, False, None  # chain: the last row id of the newest page of an unbroken chain, else None
    reads = {}  # tool_use id -> (after_id, partial) of a list_sessions call
    with open(transcript, encoding="utf-8") as handle:
        for line in handle:
            try:
                content = json.loads(line)["message"]["content"]
            except (ValueError, KeyError, TypeError):
                continue
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                given = block.get("input")
                if block.get("type") == "tool_use" and str(block.get("name", "")).endswith("list_sessions"):
                    partial = not isinstance(given, dict) or bool(given.get("before_id") or given.get("tags") or given.get("mine"))
                    after = given.get("after_id") if isinstance(given, dict) and not partial else None
                    reads[block.get("id")] = (after if isinstance(after, str) and after else None, partial)
                elif block.get("type") == "tool_result" and block.get("tool_use_id") in reads:
                    body = block.get("content")
                    if isinstance(body, list):
                        body = "".join(b.get("text", "") for b in body if isinstance(b, dict))
                    try:
                        page, more = _list_rows(body)
                    except (ValueError, KeyError, TypeError, AttributeError):
                        chain = None
                        continue
                    for sid, tags, archived in page:
                        rows[sid] = (tags, archived)
                    after, partial = reads[block.get("tool_use_id")]
                    linked = not partial and (after is None or (chain is not None and after == chain))
                    if linked and not more:
                        whole, chain = True, None
                    else:
                        chain = page[-1][0] if linked and page else None
    return rows, whole
