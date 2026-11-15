"""The one reader of a session's own get_session and create_session records in its transcript, and of the session
roster: the Standing sessions rows of the repo's roadmap record, and the session ids a transcript's list_sessions,
get_session and create_session results show (decision brief-ids-in-roster).

hooks/guard_merge.py (merge role, trust card, archive proofs) and lint/report_guard.py (lane or
owner-facing pick guard) both read it. It is its own small module so the Stop hook can import it
without loading the whole guard.
Cost: one transcript read per call, no file written. An agent's own record is a second file read, by the
caller, through agent_transcript_path.
"""
import json
import os
import re
import sys

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


def tag_name(tag):
    """A tag as it is compared: stripped and casefolded, as hooks/guard.py reads tags."""
    return str(tag).strip().casefold()


def record_tags(body, own_id):
    """The tags, by tag_name, of the get_session record `body` holds when its ccr.id is own_id, else None."""
    try:
        ccr = _record_json(body)["ccr"]
        if ccr["id"] == own_id and isinstance(ccr["tags"], list):
            return {tag_name(t) for t in ccr["tags"]}
    except (ValueError, KeyError, TypeError):
        pass
    return None


def move_tags(tags, call_input):
    """Apply one set_session_tags call's `add` and `remove` lists, by tag_name, to the set `tags`, in place."""
    for key, op in (("add", tags.update), ("remove", tags.difference_update)):
        given = call_input.get(key) if isinstance(call_input, dict) else None
        if isinstance(given, list):
            op(tag_name(t) for t in given)


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


# ---- The session roster (decision brief-ids-in-roster). The roadmap record's Standing sessions section holds one bullet
# per standing session. The ids a transcript shows from the sessions tools are the second source: a lane has no row, but
# the session that started or listed it saw its id.
ROSTER_REF = "refs/remotes/origin/roadmap"  # the record branch as the checkout last fetched it; never fetched here
ROSTER_PATH = "CLAUDE.md"
_ROSTER_HEADING = re.compile(r"##\s+Standing sessions\b")
_ROSTER_END = re.compile(r"#{1,2}\s")  # the next section; a ### line inside the roster stays inside it
_ROSTER_ID = re.compile(r"(?<![A-Za-z0-9_])session_[0-9][A-Za-z0-9]*")
_ROSTER_ROLE = re.compile(r"[^:(]+")
_ROSTER_TITLE = re.compile(r'"([^"]+)"')


def roster_record(where):
    """The text of CLAUDE.md on the roadmap ref of the checkout `where`, else None (no ref, no file, no git, no
    folder). One local git read, never a fetch."""
    if not isinstance(where, str) or not where or not os.path.isdir(where):
        return None
    from git_reads import _git
    shown = _git(where, "cat-file", "blob", ROSTER_REF + ":" + ROSTER_PATH)
    return shown.stdout if shown is not None and shown.returncode == 0 else None


def roster_rows(text):
    """[(role, title, id)] for each bullet of the Standing sessions section of `text` that holds a session id, in
    order. A bullet may wrap onto indented lines. The id is the first one in the bullet; a bullet with none, such as the
    template's `<session id>` placeholder, is no row. The title is "" when the bullet quotes none."""
    bullets, current, inside = [], None, False
    for line in text.splitlines():
        if _ROSTER_HEADING.match(line):
            inside = True
            continue
        if not inside:
            continue
        if _ROSTER_END.match(line):
            break
        if line.startswith("- "):
            if current is not None:
                bullets.append(current)
            current = line[2:].strip()
        elif current is not None and line[:1] in (" ", "\t") and line.strip():
            current += " " + line.strip()
        elif current is not None:
            bullets.append(current)
            current = None
    if current is not None:
        bullets.append(current)
    rows = []
    for bullet in bullets:
        found = _ROSTER_ID.search(bullet)
        if not found:
            continue
        role = _ROSTER_ROLE.match(bullet)
        title = _ROSTER_TITLE.search(bullet)
        rows.append((role.group(0).strip() if role else "", title.group(1) if title else "", found.group(0)))
    return rows


def _listed_rows(parsed):
    """[(id, tags)] from one parsed get_session or list_sessions result: a record with an id, or a list of them under
    `ccr.data`, `data` or `sessions`, or a bare list. A row with no string id or no list of tags is skipped."""
    if isinstance(parsed, dict):
        inner = parsed.get("ccr") if isinstance(parsed.get("ccr"), dict) else parsed
        if "id" in inner:
            rows = [inner]
        else:
            rows = next((inner[k] for k in ("data", "sessions") if isinstance(inner.get(k), list)), [])
    else:
        rows = parsed if isinstance(parsed, list) else []
    return [(row["id"], [str(t) for t in row["tags"]]) for row in rows
            if isinstance(row, dict) and isinstance(row.get("id"), str) and isinstance(row.get("tags"), list)]


def _sessions_seen(transcript):
    """The pass behind sessions_seen. Raises OSError when the transcript cannot be read."""
    kinds, seen = {}, []
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
                name = str(block.get("name", ""))
                if block.get("type") == "tool_use":
                    for kind in ("list_sessions", "get_session", "create_session"):
                        if name.endswith(kind):
                            given = block.get("input", {}).get("tags") if isinstance(block.get("input"), dict) else None
                            kinds[block.get("id")] = (kind, given)
                elif block.get("type") == "tool_result" and block.get("tool_use_id") in kinds:
                    kind, given = kinds[block.get("tool_use_id")]
                    body = block.get("content")
                    if isinstance(body, list):
                        body = "".join(b.get("text", "") for b in body if isinstance(b, dict))
                    if not isinstance(body, str):
                        continue
                    if kind == "create_session":
                        created = _created_session_id(body)
                        if created and isinstance(given, list):
                            seen.append((created, [str(t) for t in given]))
                        continue
                    try:
                        seen += _listed_rows(_record_json(body))
                    except (ValueError, KeyError, TypeError):
                        continue
    return seen


def sessions_seen(transcript):
    """[(id, tags)] for each session the transcript's get_session, list_sessions and create_session results show, each
    sighting its own entry. A create_session result names the id and the call's input names the tags. A line or result
    that does not parse is skipped. The ids are data. Never raises, because the guard's checks must not crash on any
    input: a transcript it cannot read (no path, a missing file, a folder) is None, which is not the same as an empty list."""
    if not isinstance(transcript, (str, os.PathLike)):
        return None
    try:
        return _sessions_seen(transcript)
    except (OSError, TypeError, ValueError, RecursionError):
        return None


def roster_session_lines(where):
    """The lines SessionStart prints for the roster of the checkout `where`, a list of strings. Rows come from
    roster_rows; the source and the status words say the roster is the record's, not live."""
    from git_reads import github_repo
    text = roster_record(where)
    rows = roster_rows(text) if text is not None else []
    if not rows:
        return ["roster: no roster record with standing session rows on the roadmap ref (read from CLAUDE.md, "
                "Standing sessions); ask the coordinator or run list_sessions for the ids, and never type an id by hand."]
    repo = github_repo(where) or "unknown repo"
    lines = ["standing sessions of %s, from the Standing sessions section of CLAUDE.md on the roadmap ref:" % repo]
    for role, title, sid in rows:
        lines.append("  %s%s, %s, repo %s" % (role, ' "%s"' % title if title else "", sid, repo))
    lines.append("Status is from the record, not live: run list_sessions for live status (tag cs-repo:%s). A brief names "
                 "a role or a slug, never an id typed by hand; send_message takes the id from a row above or from "
                 "your own list_sessions read." % repo)
    return lines


if __name__ == "__main__":
    # `own_session.py roster-lines <checkout>`: the SessionStart roster block. Silent on any failure.
    if len(sys.argv) == 3 and sys.argv[1] == "roster-lines":
        try:
            print("\n".join(roster_session_lines(sys.argv[2])))
        except Exception:
            pass
