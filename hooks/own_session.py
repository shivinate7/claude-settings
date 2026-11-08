"""The one reader of a session's own get_session record in its transcript.

hooks/guard_merge.py (merge role, trust card, archive proofs) and lint/report_guard.py (lane or
owner-facing pick guard) both read it. It is its own small module so the Stop hook can import it
without loading the whole guard.
Cost: one transcript read per call, no file written.
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


def _listed_rows(body):
    """The session records a list_sessions result holds: each `ccr` object, and each object that carries a string `id` and a list `tags`, at any
    depth of its JSON. [] when the body is not JSON."""
    text = body.strip()
    wrapped = _OTHER_SESSION.fullmatch(text)
    if wrapped:  # a wrapped list opens with `[` or `{`, whichever comes first after the preamble
        text = wrapped.group(2)
    starts = [at for at in (text.find("["), text.find("{")) if at >= 0]
    if not starts:
        return []
    try:
        parsed = json.JSONDecoder().raw_decode(text, min(starts))[0]
    except ValueError:
        return []
    rows, todo = [], [parsed]
    while todo:
        item = todo.pop()
        if isinstance(item, list):
            todo.extend(item)
        elif isinstance(item, dict):
            if isinstance(item.get("ccr"), dict):
                todo.append(item["ccr"])
            if isinstance(item.get("id"), str) and isinstance(item.get("tags"), list):
                rows.append(item)
            todo.extend(v for v in item.values() if isinstance(v, (list, dict)))
    return rows


def own_session_read(transcript, own_id, created=False, listed=False):
    """(tags, tagged_after, parent): the tags and parent_session_id of the newest get_session result
    whose ccr.id is own_id, else None for each, and whether a set_session_tags call follows that
    result. With `created`, a create_session call whose result names own_id is a record too: its tags
    are the call's input.tags, its parent is None unless the input names parent_session_id. The newest
    record of either kind decides. Without it, only get_session counts. With `listed`, a list_sessions row whose
    id is own_id is a record too, and the newest record of any kind decides; the default leaves a list_sessions
    result unread, so the own-role proof never rests on a list."""
    uses, newest, parent, tagged_after = set(), None, None, False
    lists = set()  # tool_use ids of list_sessions calls, read only when `listed`
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
                elif listed and block.get("type") == "tool_use" and str(block.get("name", "")).endswith("list_sessions"):
                    lists.add(block.get("id"))
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
                elif block.get("type") == "tool_result" and (block.get("tool_use_id") in uses or block.get("tool_use_id") in creates
                                                             or block.get("tool_use_id") in lists):
                    body = block.get("content")
                    if isinstance(body, list):
                        body = "".join(b.get("text", "") for b in body if isinstance(b, dict))
                    if block.get("tool_use_id") in lists:
                        for row in (_listed_rows(body) if isinstance(body, str) else []):
                            if row["id"] == own_id:
                                newest, tagged_after = [str(t) for t in row["tags"]], False
                                found = row.get("parent_session_id")
                                parent = found if isinstance(found, str) and found else None
                        continue
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
