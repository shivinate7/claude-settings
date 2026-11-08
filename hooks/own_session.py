"""The one reader of a session's own get_session record in its transcript.

hooks/guard_merge.py (merge role, trust card, archive proofs) and lint/report_guard.py (lane or
owner-facing pick guard) both read it. It is its own small module so the Stop hook can import it
without loading the whole guard.
Cost: one transcript read per call, no file written.
session_rows_read is the second reader, for rule lane-step-dup. It stays apart from own_session_read because it reads
many rows (every session the transcript has seen), where own_session_read follows one id and its set_session_tags calls.
"""
import json
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


def own_session_read(transcript, own_id, created=False):
    """(tags, tagged_after, parent): the tags and parent_session_id of the newest get_session result
    whose ccr.id is own_id, else None for each, and whether a set_session_tags call follows that
    result. With `created`, a create_session call whose result names own_id is a record too: its tags
    are the call's input.tags, its parent is None unless the input names parent_session_id. The newest
    record of either kind decides. Without it, only get_session counts."""
    uses, newest, parent, tagged_after = set(), None, None, False
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
                            (newest, parent), tagged_after = creates[block.get("tool_use_id")], False
                        continue
                    if not isinstance(body, str):
                        continue
                    try:
                        ccr = _record_json(body)["ccr"]
                        if ccr["id"] == own_id and isinstance(ccr["tags"], list):
                            newest, tagged_after = ccr["tags"], False
                            found = ccr.get("parent_session_id")
                            parent = found if isinstance(found, str) and found else None
                    except (ValueError, KeyError, TypeError):
                        continue
    return newest, tagged_after, parent


# How the list_sessions reads of a transcript add up: none was made, the newest did not parse, it is a page that does not
# finish a chain, or one of them is the whole list. Only LIST_FULL proves that no session outside the transcript carries a step.
LIST_NONE, LIST_BAD, LIST_MORE, LIST_FULL = "none", "bad", "more", "full"


def _is_tool(name, base):
    """True when `name` is the tool `base`, bare or behind an `mcp__<server>__` prefix. A name that only ends in the
    same letters (unarchive_session for archive_session) is another tool."""
    return name == base or name.endswith("__" + base)


def _result_text(block):
    """The text of a tool_result block: its string content, or its text blocks joined. None when it has neither."""
    body = block.get("content")
    if isinstance(body, list):
        body = "".join(b.get("text", "") for b in body if isinstance(b, dict))
    return body if isinstance(body, str) else None


def _list_rows(body):
    """(rows, has_more) of a list_sessions body: `{"ccr": {"data": [rows], "has_more": bool}}`, bare or in the
    untrusted wrapper. Raises ValueError, KeyError or TypeError when the body is not that, or a row is not readable."""
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


def session_rows_read(transcript):
    """(records, listing, unknown): `records` maps each session id this transcript has seen to (tags, archived), the
    newest sight deciding. A sight is a row of a list_sessions result, a get_session result, or a create_session call
    whose result names the id (its tags are the call's input.tags). A session is archived when its newest sight has an
    ARCHIVED session_status, or an archive_session call on it, answered without error, follows that sight; an
    unarchive_session call answered without error makes it live again. `unknown` is the ids whose tags a
    set_session_tags call may have changed after their newest sight (a call with no readable id list may have named
    any of them), because the call's result does not say what the tags are now.
    `listing` is LIST_FULL when the transcript holds a whole list_sessions read: a later partial read does not cancel
    it, because every session it missed is a sight in `records`. A read is whole when it is a chain: a read with no
    cursor, then reads whose after_id is the previous page's last row id, the last with has_more false (the tool caps
    a page, so a long list is never one read). A read with a tags or mine arg lists only a part of the sessions, and a
    before_id read or an after_id that is not the previous page's last row id breaks the chain; it is partial, and the
    next whole read must start again with no cursor. Otherwise `listing` is the state of the newest read: a page that
    does not finish a chain is LIST_MORE; a body that is not a whole list page is LIST_BAD; no read is LIST_NONE.
    Cost: one read of the transcript; no file written, no process."""
    records, listing, whole, unknown = {}, LIST_NONE, False, set()
    chain = None  # the last row id of the newest page of a chain that no filter or stray cursor has broken, else None
    uses = {}  # tool_use id -> (kind, the id acted on, or the (after_id, partial) of a list read) of a call whose result is judged
    creates = {}  # tool_use id -> the tags a create_session call set
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
                name, given = str(block.get("name", "")), block.get("input")
                if block.get("type") == "tool_use":
                    target = given.get("session_id") if isinstance(given, dict) else None
                    target = target if isinstance(target, str) else None
                    if _is_tool(name, "list_sessions"):
                        # A filter or a before_id makes the read partial for good; only an after_id can continue a chain.
                        partial = not isinstance(given, dict) or bool(
                            given.get("before_id") or given.get("tags") or given.get("mine"))
                        after = given.get("after_id") if isinstance(given, dict) and not partial else None
                        uses[block.get("id")] = ("list", (after if isinstance(after, str) and after else None, partial))
                    elif _is_tool(name, "get_session"):
                        uses[block.get("id")] = ("get", None)
                    elif _is_tool(name, "archive_session"):
                        uses[block.get("id")] = ("archive", target)
                    elif _is_tool(name, "unarchive_session"):
                        uses[block.get("id")] = ("unarchive", target)
                    elif _is_tool(name, "create_session"):
                        tags = given.get("tags") if isinstance(given, dict) else None
                        if isinstance(tags, list):
                            creates[block.get("id")] = [str(t) for t in tags]
                    elif _is_tool(name, "set_session_tags"):
                        ids = given.get("session_ids") if isinstance(given, dict) else None
                        unknown.update(r for r in records if not isinstance(ids, list) or r in ids)
                elif block.get("type") == "tool_result":
                    key, body = block.get("tool_use_id"), _result_text(block)
                    if key in creates:
                        made = _created_session_id(body)
                        if made:
                            records[made] = (creates[key], False)
                            unknown.discard(made)
                    elif key in uses and uses[key][0] in ("archive", "unarchive"):
                        sid = uses[key][1]
                        if not block.get("is_error") and sid in records:
                            records[sid] = (records[sid][0], uses[key][0] == "archive")
                    elif key in uses and uses[key][0] == "get" and body is not None:
                        try:
                            ccr = _record_json(body)["ccr"]
                            if isinstance(ccr["id"], str) and isinstance(ccr["tags"], list):
                                records[ccr["id"]] = ([str(t) for t in ccr["tags"]],
                                                      "ARCHIVED" in str(ccr.get("session_status", "")).upper())
                                unknown.discard(ccr["id"])
                        except (ValueError, KeyError, TypeError):
                            continue
                    elif key in uses and uses[key][0] == "list":
                        try:
                            rows, more = _list_rows(body)
                        except (ValueError, KeyError, TypeError, AttributeError):
                            listing, chain = LIST_BAD, None
                            continue
                        for sid, tags, archived in rows:
                            records[sid] = (tags, archived)
                            unknown.discard(sid)
                        after, partial = uses[key][1]
                        # A page opens a chain with no cursor, or continues it with the previous page's last row id.
                        linked = not partial and (after is None or (chain is not None and after == chain))
                        if linked and not more:
                            listing, whole, chain = LIST_FULL, True, None
                        else:
                            listing = LIST_MORE
                            chain = rows[-1][0] if linked and rows else None
    return records, LIST_FULL if whole else listing, unknown
