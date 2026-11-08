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


def _tag_names(value):
    """The strings of a tag list, else an empty list: a call whose list cannot be read adds or removes nothing."""
    return [str(tag) for tag in value] if isinstance(value, list) else []


def own_session_read(transcript, own_id, created=False, applied=False):
    """(tags, tagged_after, parent): the tags and parent_session_id of the newest get_session result
    whose ccr.id is own_id, else None for each, and whether a set_session_tags call follows that
    result. With `created`, a create_session call whose result names own_id is a record too: its tags
    are the call's input.tags, its parent is None unless the input names parent_session_id. The newest
    record of either kind decides. Without it, only get_session counts.
    With `applied`, the tags also hold what the session's own set_session_tags calls added since that
    record (or from the start, with no record): a call that names own_id, or whose id list cannot be
    read. A call's `remove` drops only a tag an earlier call in the same pass added since that record,
    never one the record holds, so a self-remove never loosens the verdict. The record's tags and
    tagged_after keep their meaning, and the default keeps the shape the callers rely on."""
    uses, newest, parent, tagged_after = set(), None, None, False
    added = []  # tags the own set_session_tags calls added since the newest record, in order
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
                        if applied:
                            given = block.get("input") if isinstance(block.get("input"), dict) else {}
                            added.extend(tag for tag in _tag_names(given.get("add")) if tag not in added)
                            dropped = set(_tag_names(given.get("remove")))
                            added = [tag for tag in added if tag not in dropped]
                elif block.get("type") == "tool_result" and (block.get("tool_use_id") in uses or block.get("tool_use_id") in creates):
                    body = block.get("content")
                    if isinstance(body, list):
                        body = "".join(b.get("text", "") for b in body if isinstance(b, dict))
                    if block.get("tool_use_id") in creates:
                        if _created_session_id(body) == own_id:
                            (newest, parent), tagged_after, added = creates[block.get("tool_use_id")], False, []
                        continue
                    if not isinstance(body, str):
                        continue
                    try:
                        ccr = _record_json(body)["ccr"]
                        if ccr["id"] == own_id and isinstance(ccr["tags"], list):
                            newest, tagged_after, added = ccr["tags"], False, []
                            found = ccr.get("parent_session_id")
                            parent = found if isinstance(found, str) and found else None
                    except (ValueError, KeyError, TypeError):
                        continue
    if applied and added:
        newest = [*(newest or []), *(tag for tag in added if tag not in (newest or []))]
    return newest, tagged_after, parent
