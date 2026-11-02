"""The one home of a session's own record, read from its own transcript. Standard library only.

lint/report_guard.py (a Stop hook) and hooks/guard_merge.py both read it, so nothing here may import
the guard or any sibling hook.
"""
import json

# A lane session's record tag. hooks/guard.py imports it from here.
LANE_TAG = "cs-build:lane"


def read(transcript: str, own_id: str):
    """(tags, tagged_after, parent): from the newest get_session result in the transcript whose ccr.id
    is own_id, its tags (None when there is no such result) and its parent_session_id ("" when it has
    none); tagged_after says whether a set_session_tags call follows that result."""
    uses, newest, parent, tagged_after = set(), None, "", False
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
                elif block.get("type") == "tool_use" and str(block.get("name", "")).endswith("set_session_tags"):
                    tagged_after = True
                elif block.get("type") == "tool_result" and block.get("tool_use_id") in uses:
                    body = block.get("content")
                    if isinstance(body, list):
                        body = "".join(b.get("text", "") for b in body if isinstance(b, dict))
                    try:
                        ccr = json.loads(body)["ccr"]
                        if ccr["id"] == own_id and isinstance(ccr["tags"], list):
                            found = ccr.get("parent_session_id")
                            newest, parent, tagged_after = ccr["tags"], found if isinstance(found, str) else "", False
                    except (ValueError, KeyError, TypeError):
                        continue
    return newest, tagged_after, parent


def is_lane(tags, parent):
    """True when the own record carries the lane tag or names a parent session."""
    return bool(parent) or any(isinstance(t, str) and t.strip().casefold() == LANE_TAG for t in tags or ())
