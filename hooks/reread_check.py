#!/usr/bin/env python3
"""Claude Code hook: after compaction, check the session re-read its handoff.

Modes:
- --post-compact: After compaction, sets the session's flag that its handoff is not read, and
  a second flag that the handoff audit (prompt step 3) is owed. An agent's compaction (`agent_id`,
  or a transcript under a `subagents` folder) sets nothing: the agent shares its parent's session_id.
- --pre-read: Before a Read of the session's handoff, adds the lines the Read covers to the flag
  file, and clears the flag once the ranges cover every line (decision precompact-handoff, "Every
  handoff and compaction check", rule 2). Never refuses the read. A payload with `agent_id` (the hook
  fired inside an agent) changes nothing: only the session's own Read counts.
- --stop: At Stop, while the session's flag that its handoff is not read is set and the
  handoff exists, refuses once per turn and names the handoff path. With that flag cleared
  and the audit flag still set, it refuses once per turn and names the Audit: remedy. With the audit
  flag cleared and the rewrite flag set, it runs the rewrite check: the rewritten handoff must still hold
  the ids it held at PreCompact, the audit's MISSING items and each running job or agent.

Spec: docs/decisions/precompact-handoff.md, items 9 and 16. Three flag files per session,
<config dir>/state/handoff/<session_id>.reread, <session_id>.audit and <session_id>.rewrite. Three modes, JSON on stdin:

  --post-compact (PostCompact)  sets both flags.
  --pre-read (PreToolUse, Read)  records the lines read when file_path is the session's own
      handoff, spelled as a full path, with forward slashes, as a short or long Windows
      name, or as ~/.claude/..., and clears the flag when they cover every line. The flag file holds
      JSON, {"ranges": [[first, last], ...], "agent": bool}; the old text `1` means no ranges.
      Never refuses the read.
  unread_handoff(payload) (import, no flag)  the guard's PreToolUse check calls it. Returns the
      handoff path while the flag is set and the handoff exists, else "".
  audit_pending(payload) (import, no flag)  the guard's PreToolUse check calls it. Returns the
      handoff path while the audit flag is set, the re-read flag is already cleared and the call is
      the main session's, else "".
  audit_spawn(payload, spawn_tools) (import)  true for a spawn from the main session whose brief's
      first non-blank line carries the audit marker (shared_names.EXPLORE_AUDIT_MARKER, `Audit:`) and that names
      the session's transcript path (the payload's transcript_path, compared as a string; the brief that
      `precompact_handoff.py --audit-brief` prints does). A payload with no transcript_path is judged by the marker
      alone. audit_clear(payload) drops the audit flag and sets the rewrite flag, <sid>.rewrite; the guard's main()
      calls it when judge() returns, or when a later rule crashes after the spawn was marked.
  --stop (Stop), with the audit flag cleared and the rewrite flag set: judges the rewritten handoff (rewrite_check).
      Required: each `#N` and `fb-` id the handoff held at PreCompact (the baseline in the state file), each
      token the audit's MISSING list names, and each job or agent that still runs (stall_watch.scan_jobs). A token
      the audit's DONE or STALE list names may go. It stays quiet while the audit agent itself still runs. A passing
      check, or a baseline that is unreadable, clears the rewrite flag. It reads no PR state.
  --stop (Stop)  with the flag set and the handoff file present, prints
      {"decision": "block", "reason": ...} naming the handoff path. Exits quietly on
      stop_hook_active, so it cannot loop. The flag stays set until the handoff is read,
      so it refuses once per turn. SessionEnd (clear) deletes both flags.

Never exits 2: bad stdin, a failed import of the sibling precompact_handoff, and every
other failure exit 0. Importing this module never exits: without the sibling,
`unread_handoff` and `audit_pending` return "".
"""
import hashlib
import importlib
import json
import os
import re
import sys

try:
    sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
    import precompact_handoff as ph  # one home for the handoff and flag paths
except Exception as e:
    ph = None
    sys.stderr.write("reread_check: cannot import precompact_handoff: %s\n" % e)

# The names this file takes from precompact_handoff. A copy that imports but lacks one is as good as no copy
# (decision install-hooks-whole): ph is None, and the guard's load check refuses it as guard-crash.
PH_NAMES = ("same_dir", "handoff_path", "reread_flag_path")
if ph is not None and any(not hasattr(ph, name) for name in PH_NAMES):
    sys.stderr.write("reread_check: precompact_handoff lacks %s\n" % ", ".join(
        name for name in PH_NAMES if not hasattr(ph, name)))
    ph = None

try:
    # The audit marker's one home is shared_names.py: its first-line audit row of BRIEF_MARKERS, which the guard's
    # marker_hits reads too. This reader compiles that row, so the two cannot drift.
    from shared_names import BRIEF_MARKERS, EXPLORE_AUDIT_MARKER
    AUDIT_ROW = re.compile(next(rx for kind, rx, position in BRIEF_MARKERS
                                if kind == "audit" and position == "first-line"))
except Exception as e:
    AUDIT_ROW = EXPLORE_AUDIT_MARKER = None
    sys.stderr.write("reread_check: cannot read the audit marker from shared_names: %s\n" % e)


# The handoff's size limit and the size of a Read that counts (decision precompact-handoff, "Every handoff and
# compaction check", rules 1 and 2). The one home of both numbers. Step 4 of hooks/precompact_handoff_prompt.md says
# the limit in prose.
HANDOFF_MAX_TOKENS = 10000
READ_CAP_TOKENS = 25000   # the Read tool's own cap
READ_MAX_LINES = 2000     # the Read tool's default line count


def estimate_tokens(nbytes):
    """ceil(nbytes / 3.5), in whole numbers."""
    return (2 * nbytes + 6) // 7


def text_bytes(text):
    return len(text.encode("utf-8", "surrogatepass"))


def too_big_estimate(result, path):
    """The token estimate of a write's result when it is over HANDOFF_MAX_TOKENS and not smaller than the handoff
    is now, else 0. `result` is the guard's (before, after) pair of texts. A Write has no before (None): the file on
    disk is its before, a missing one is 0 bytes, and the stat runs only for a result over the limit. Never raises."""
    try:
        before, after = result
        size = text_bytes(after)
        tokens = estimate_tokens(size)
        if tokens <= HANDOFF_MAX_TOKENS:
            return 0
        if before is None:
            try:
                now = os.path.getsize(path)
            except OSError:
                now = 0
        else:
            now = text_bytes(before)
        return tokens if size >= now else 0
    except Exception:
        return 0


def read_flag(sid):
    """(ranges, agent) from the session's re-read flag file: the line ranges read so far, and whether an agent's
    rewrite set it. The old text `1`, or any file that is not that JSON, is no ranges and no agent."""
    try:
        with open(ph.reread_flag_path(sid), "r", encoding="utf-8") as f:
            data = json.loads(f.read())
        return [(int(a), int(b)) for a, b in data["ranges"]], data.get("agent") is True
    except Exception:
        return [], False


def write_flag(sid, ranges=(), agent=False):
    flag = ph.reread_flag_path(sid)
    os.makedirs(os.path.dirname(flag), exist_ok=True)
    with open(flag, "w", encoding="utf-8") as f:
        f.write(json.dumps({"ranges": [list(r) for r in ranges], "agent": bool(agent)}))


def handoff_lines(handoff):
    """The handoff's lines as bytes, counted as the Read tool counts them: a final newline ends a line, it starts none."""
    with open(handoff, "rb") as f:
        lines = f.read().split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    return lines


def read_range(tool_input, lines):
    """(first, last), the 1-based lines a Read asked for, clipped to the file, when the range counts, else None.
    It counts when it is at most READ_MAX_LINES lines and its text estimates at most READ_CAP_TOKENS (the hook sees
    the range asked for, not the range returned). No offset and no limit is lines 1 to READ_MAX_LINES."""
    try:
        offset, limit = tool_input.get("offset"), tool_input.get("limit")
        if isinstance(offset, bool) or isinstance(limit, bool):
            return None
        first = 1 if offset is None else max(int(offset), 1)   # the Read tool starts offset 0 at line 1
        count = READ_MAX_LINES if limit is None else int(limit)
        if int(offset or 0) < 0 or count < 1:
            return None
        last = min(first + count - 1, len(lines))
        if last < first or last - first + 1 > READ_MAX_LINES:
            return None
        nbytes = sum(len(line) + 1 for line in lines[first - 1:last])
        return (first, last) if estimate_tokens(nbytes) <= READ_CAP_TOKENS else None
    except Exception:
        return None


def unread_ranges(ranges, total):
    """The (first, last) ranges of lines 1..total that `ranges` leave unread, in order."""
    gaps, at = [], 1
    for first, last in sorted(ranges):
        if first > at:
            gaps.append((at, min(first - 1, total)))
        at = max(at, last + 1)
    if at <= total:
        gaps.append((at, total))
    return [(a, b) for a, b in gaps if a <= b]


def span_text(spans):
    return ", ".join(str(a) if a == b else "%d-%d" % (a, b) for a, b in spans)


def unread_note(payload):
    """(agent, unread) for the guard's handoff-unread refusal: whether an agent's rewrite set the flag, and the lines
    still unread as text such as `11-50` ("" when they cannot be worked out). It reads the flag and the handoff, so it
    runs on a refusal only. Never raises."""
    try:
        sid = payload["session_id"]
        ranges, agent = read_flag(sid)
        return agent, span_text(unread_ranges(ranges, len(handoff_lines(ph.handoff_path(sid)))))
    except Exception:
        return False, ""


def agent_rewrite(payload):
    """Set the session's re-read flag, marked as an agent's rewrite, when an agent's Write, Edit or MultiEdit names the
    session's handoff. The audit flag stays as it is. The main session's own write sets nothing. The guard calls this
    once judge() has let the call through. Only a path compare runs on any other call. Never raises."""
    try:
        if ph is None or payload.get("tool_name") not in ("Write", "Edit", "MultiEdit") or not from_agent(payload):
            return
        sid = payload.get("session_id")
        fp = (payload.get("tool_input") or {}).get("file_path")
        if sid and isinstance(sid, str) and isinstance(fp, str) and fp and names_handoff(fp, sid):
            write_flag(sid, (), True)
    except Exception:
        pass


def names_handoff(file_path, session_id):
    return any(ph.same_dir(os.path.expanduser(file_path), want) for want in (
        ph.handoff_path(session_id),
        os.path.expanduser("~/.claude/handoffs/%s.md" % session_id)))


def unread_handoff(payload):
    """The session's handoff path while its re-read flag is set and the handoff exists, else "".
    An agent's call (`agent_id` on the payload) and a bad payload give "". Checks the flag first,
    so a session with no flag costs one existence check. Never raises."""
    try:
        if ph is None or not isinstance(payload, dict) or payload.get("agent_id"):
            return ""
        sid = payload.get("session_id")
        if not sid or not isinstance(sid, str) or not os.path.isfile(ph.reread_flag_path(sid)):
            return ""
        handoff = ph.handoff_path(sid)
        return handoff if os.path.isfile(handoff) else ""
    except Exception:
        return ""


def audit_pending(payload):
    """The session's handoff path while its audit flag is set, its re-read flag is already cleared (the
    handoff-unread check speaks first) and the call is the main session's, else "". An agent's call
    (`agent_id` on the payload) and a bad payload give "". Checks the audit flag first, so a session
    with no flag costs one existence check. Never raises."""
    try:
        if ph is None or not isinstance(payload, dict) or payload.get("agent_id"):
            return ""
        sid = payload.get("session_id")
        if not sid or not isinstance(sid, str) or not os.path.isfile(ph.audit_flag_path(sid)):
            return ""
        if os.path.isfile(ph.reread_flag_path(sid)):
            return ""
        return ph.handoff_path(sid)
    except Exception:
        return ""


def audit_spawn(payload, spawn_tools):
    """True when the call is a spawn (its tool is in `spawn_tools`, the guard's SPAWN_TOOLS) from the
    main session whose brief's first non-blank line carries the audit marker, as the one home reads it
    (shared_names.BRIEF_MARKERS, the first-line audit row: case-sensitive, text or markup may stand ahead of it),
    and whose brief names the payload's transcript_path as a string. That path rule enforces the brief that
    `precompact_handoff.py --audit-brief` prints; a payload with no transcript_path skips it, since no remedy could
    satisfy it. A line quoted further down does not count. Never raises."""
    try:
        if not isinstance(payload, dict) or payload.get("agent_id") or payload.get("tool_name") not in spawn_tools:
            return False
        tool_input = payload.get("tool_input")
        prompt = tool_input.get("prompt") if isinstance(tool_input, dict) else None
        if not isinstance(prompt, str):
            return False
        path = payload.get("transcript_path")
        if isinstance(path, str) and path and path not in prompt:
            return False   # a stray `Audit:` brief: the helper's brief names the session's transcript
        first = next((line for line in prompt.split("\n") if line.strip()), "")   # the guard's brief_first_line pick
        return AUDIT_ROW is not None and AUDIT_ROW.search(first) is not None
    except Exception:
        return False


def audit_clear(payload):
    """Drop the session's audit flag and set its rewrite flag: the next Stop judges the rewritten handoff. Never raises."""
    try:
        os.remove(ph.audit_flag_path(payload["session_id"]))
    except Exception:
        pass
    try:
        flag = ph.rewrite_flag_path(payload["session_id"])
        os.makedirs(os.path.dirname(flag), exist_ok=True)
        with open(flag, "w", encoding="utf-8") as f:
            f.write("1")
    except Exception:
        pass


def _esc(text):
    return text.replace("%", "%%")


# The one remedy text for an owed audit. The Stop block uses it, and so does the guard's compaction-audit refusal
# (guard.COMPACTION_AUDIT_REASON), so the two cannot drift. It holds one `%s`: the handoff path.
AUDIT_OWED = "context was compacted and the handoff audit is still owed. "
# The audit helper's command, in the one form the remedy prints and the guard's compaction-audit rule lets through.
AUDIT_HELPER_HEAD = ('python3 "' + os.path.join(os.path.dirname(os.path.realpath(__file__)), "precompact_handoff.py")
                     + '" --audit-brief --handoff "')


def audit_helper_command(handoff):
    """The helper command with the handoff path filled in: the exact text the guard allows while the audit is owed."""
    return AUDIT_HELPER_HEAD + handoff + '"'


AUDIT_REMEDY = (
    "Remedy: print the brief with `" + _esc(AUDIT_HELPER_HEAD) + "%s\"`, then spawn one Explore agent on Sonnet with "
    "exactly that brief, whose first line is `" + _esc(EXPLORE_AUDIT_MARKER or "Audit:") + "` (step 3 of the handoff "
    "prompt). The brief names this session's transcript path, and a spawn whose brief does not name it clears nothing. "
    "That spawn clears this check. Then repeat the call. (decision precompact-handoff, item 16)")


def audit_reason(handoff):
    """The Stop block's text for an owed audit."""
    return AUDIT_OWED[0].upper() + AUDIT_OWED[1:] + AUDIT_REMEDY % handoff


# The spawn tools. guard.SPAWN_TOOLS names the same two; this file cannot import the guard, which imports it.
SPAWN_NAMES = ("Agent", "Task")
# A heading is MISSING, STALE or DONE in any case, then an optional count or title, then a colon with items after it, or
# the end of the line. A count or title in brackets may end the line: `MISSING`, `MISSING (2 items)`. A title after a
# space needs the colon: `Missing items:`. A prose line such as `Done reading the transcript` is no heading.
_HEADING = re.compile(r"^[\s#*_>`-]*(MISSING|STALE|DONE)\b(?:"
                      r"(?:\s*\([^)\n]{0,30}\)|\s+[A-Za-z][A-Za-z ]{0,30}?)?[\s*_`]*:[\s*_]*(?P<inline>.*)"
                      r"|(?:\s*\([^)\n]{0,30}\))?[\s:*_`]*)$", re.IGNORECASE)
_TICKS = re.compile(r"`([^`\n]+)`")


def _text(content):
    """The text of a message content or a tool result: a string, or the text of a list's blocks, nested."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(_text(b.get("text") if b.get("type") == "text" else b.get("content"))
                         for b in content if isinstance(b, dict))
    return ""


def _item_tokens(heading, line):
    """The backticked tokens one item line adds to its list. The audit brief asks for exactly one token per item, so a
    MISSING item requires its first token only: a second span is prose, not a required token."""
    tokens = [t.strip() for t in _TICKS.findall(line) if t.strip()]
    return tokens[:1] if heading == "MISSING" else tokens


def parse_audit(text):
    """{heading: [backticked tokens]} for the audit's reply: a line that is a MISSING, STALE or DONE heading (see
    _HEADING) starts a list, and each token in backticks after it, on the heading line or the lines below, joins that
    list (a MISSING line adds its first token only). None when the text has no heading."""
    lists, cur = {}, None
    for line in text.splitlines():
        found = _HEADING.match(line)
        if found:
            cur = found.group(1).upper()
            lists.setdefault(cur, [])
            lists[cur] += _item_tokens(cur, found.group("inline") or "")
        elif cur:
            lists[cur] += _item_tokens(cur, line)
    return lists or None


def audit_reply(transcript):
    """(agent id, parsed lists) for the session's newest audit spawn in `transcript`: the agent id when that spawn
    launched a background agent (else None), and parse_audit of its reply, taken from the spawn's own tool result or,
    for a background agent, from a later record that names the agent id. (None, None) when the transcript holds no
    such spawn or its reply cannot be read. Never raises."""
    tu, agent, texts = None, None, []
    try:
        with open(transcript, "rb") as f:
            for line in f:
                call = b"tool_use" in line and any(b'"%s"' % name.encode() in line for name in SPAWN_NAMES)
                if not call and not (tu and (tu.encode() in line or (agent and agent.encode() in line))):
                    continue
                try:
                    rec = json.loads(line)
                    content = rec["message"]["content"] if isinstance(rec.get("message"), dict) else None
                except Exception:
                    continue
                blocks = [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []
                answered = False
                for b in blocks:
                    if b.get("type") == "tool_use" and audit_spawn(
                            {"tool_name": b.get("name"), "tool_input": b.get("input"), "transcript_path": transcript},
                            SPAWN_NAMES):
                        tu, agent, texts = b.get("id"), None, []
                    elif tu and b.get("type") == "tool_result" and b.get("tool_use_id") == tu:
                        answered = True
                        texts.append(_text(b.get("content")))
                        result = rec.get("toolUseResult")
                        if isinstance(result, dict) and result.get("isAsync") is True \
                                and isinstance(result.get("agentId"), str):
                            agent = result["agentId"]
                if agent and not answered and agent.encode() in line:   # the background agent's own report
                    note = rec.get("attachment")
                    texts.append(_text(content) or (note.get("prompt") if isinstance(note, dict) else ""))
        parsed = next((p for p in (parse_audit(t) for t in reversed(texts) if isinstance(t, str)) if p), None)
        return agent, parsed
    except Exception:
        return None, None


def _held(text, token):
    """True when `text` holds `token` as a whole word: `#38731` does not hold `#3873`."""
    lead = "(?<!&)" if token.startswith("#") else r"(?<!\w)"
    return re.search(lead + re.escape(token) + r"(?!\w)", text) is not None


REWRITE_WHY = {"base": "in the handoff at compaction", "missing": "the audit lists it MISSING",
               "live": "a job or agent that still runs"}
REWRITE_SHOWN = 12


def rewrite_check(payload):
    """Judge the rewritten handoff once the audit spawn has set the rewrite flag. Returns the Stop block's reason, or
    "" to pass. Required in the handoff: the `#N` and `fb-` ids it held at PreCompact (the state file's baseline), the
    tokens the audit's MISSING list names, and the jobs and agents that still run (stall_watch.scan_jobs). A token the
    audit's DONE or STALE list names may go. An audit reply the transcript cannot give leaves the baseline and the
    live jobs, and no token may go. It stays quiet while the audit agent itself runs. A state file with no usable
    baseline passes and clears the flag, with one line on stderr. A pass clears the flag. A block stamps the flag with
    the handoff's hash, and a Stop with stop_hook_active true on that same text passes. So it blocks once per Stop
    chain: a Stop without stop_hook_active judges the text again, and a changed text blocks again. Reads no PR state.
    Never raises."""
    try:
        sid = payload["session_id"]
        flag = ph.rewrite_flag_path(sid)
        try:
            with open(ph.handoff_path(sid), "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            return ""
        seen = "blocked:" + hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()
        if payload.get("stop_hook_active"):
            try:
                with open(flag, "r", encoding="utf-8") as f:
                    if f.read() == seen:
                        return ""   # one block per chain: this handoff is the one the last block judged
            except OSError:
                pass
        try:
            with open(ph.state_path(sid), "r", encoding="utf-8") as f:
                state = json.load(f)
            base = state["tokens"] if state.get("ok") is True else None
            base = base if isinstance(base, list) and all(isinstance(t, str) for t in base) else None
        except Exception:
            base = None
        if base is None:
            os.remove(flag)
            sys.stderr.write("reread_check: the handoff baseline that PreCompact stores is unreadable, "
                             "so the rewrite is not judged\n")
            return ""
        path = payload.get("transcript_path")
        agent, parsed, live = None, None, []
        if isinstance(path, str) and path:
            agent, parsed = audit_reply(path)
            try:
                # By name, not an import statement: only this Stop process reads the jobs, and the guard that imports
                # this file never runs stall_watch (hooks/test_guard.py's macOS arm check follows import statements).
                live = list(importlib.import_module("stall_watch").scan_jobs(path)[0])
            except Exception as e:
                sys.stderr.write("reread_check: cannot read the running jobs: %s\n" % e)
        if agent and agent in live:
            return ""   # the audit has not reported: nothing to judge against yet
        gone = {t for key in ("DONE", "STALE") for t in (parsed or {}).get(key, [])}
        need = [(t, "base") for t in base if t not in gone]
        need += [(t, "missing") for t in (parsed or {}).get("MISSING", [])]
        need += [(t, "live") for t in live if t != agent]
        lacking = list(dict.fromkeys((t, REWRITE_WHY[why]) for t, why in need if not _held(text, t)))
        if not lacking:
            os.remove(flag)
            return ""
        with open(flag, "w", encoding="utf-8") as f:
            f.write(seen)
        shown = "; ".join("`%s` (%s)" % pair for pair in lacking[:REWRITE_SHOWN])
        more = " and %d more" % (len(lacking) - REWRITE_SHOWN) if len(lacking) > REWRITE_SHOWN else ""
        why_none = "" if parsed else " (the audit's reply could not be read, so none may go on its account)"
        return ("The handoff you rewrote after compaction leaves out %d item(s) that must stay: %s%s. "
                "Remedy: write the whole handoff again and keep each token, in a few words on its line. A token may go "
                "only when the audit's DONE or STALE list names it%s, or when it is a job that no longer runs. "
                "If the audit missed that, keep the token for this one rewrite. If the size limit leaves no room, "
                "summarize text, never drop a token. (decision precompact-handoff)"
                % (len(lacking), shown, more, why_none))
    except Exception as e:
        sys.stderr.write("reread_check: rewrite check: %s\n" % e)
        return ""


def from_agent(payload):
    """True when the hook fired inside an agent: `agent_id` on the payload, or a transcript_path with a `subagents`
    folder segment (the agent's own file, own_session.agent_transcript_dir). An agent shares its parent's
    session_id, so only the main session's own events may touch the session's flags. Never raises."""
    try:
        if payload.get("agent_id"):
            return True
        tp = payload.get("transcript_path")
        return isinstance(tp, str) and "subagents" in re.split(r"[\\/]+", tp)
    except Exception:
        return False


def note_read(sid, flag, tool_input):
    """Add the lines this Read covers to the flag file, and remove the flag once the ranges cover every line. A handoff
    that cannot be read clears the flag: there is nothing left to read."""
    try:
        lines = handoff_lines(ph.handoff_path(sid))
        ranges, agent = read_flag(sid)
        got = read_range(tool_input, lines)
        if got:
            ranges.append(got)
        if not unread_ranges(ranges, len(lines)):
            os.remove(flag)
        elif got:
            write_flag(sid, ranges, agent)
    except OSError:
        if os.path.isfile(flag):
            os.remove(flag)


def main():
    if ph is None:
        return 0
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:   # bad JSON, or a read that fails
        return 0
    sid = payload.get("session_id") if isinstance(payload, dict) else None
    if not sid or not isinstance(sid, str):
        return 0
    args = sys.argv[1:]
    try:
        flag = ph.reread_flag_path(sid)
        audit_flag = ph.audit_flag_path(sid)   # inside the try: a stale sibling without it must still exit 0
        if "--post-compact" in args:
            if from_agent(payload):
                return 0
            os.makedirs(os.path.dirname(flag), exist_ok=True)
            with open(flag, "w", encoding="utf-8") as f:
                f.write("1")
            with open(audit_flag, "w", encoding="utf-8") as f:
                f.write("1")
            try:   # the last compaction's rewrite flag would judge against a baseline this compaction replaces
                os.remove(ph.rewrite_flag_path(sid))
            except OSError:
                pass
        elif "--pre-read" in args:
            if from_agent(payload):
                return 0
            tool_input = payload.get("tool_input") or {}
            fp = tool_input.get("file_path")
            if isinstance(fp, str) and fp and names_handoff(fp, sid) and os.path.isfile(flag):
                note_read(sid, flag, tool_input)
        elif "--stop" in args:
            if (not payload.get("stop_hook_active") and os.path.isfile(flag)
                    and os.path.isfile(ph.handoff_path(sid))):
                print(json.dumps({"decision": "block", "reason": (
                    "Context was compacted and you have not re-read your handoff. Read %s "
                    "now, then continue. (decision precompact-handoff)" % ph.handoff_path(sid))}))
            elif not payload.get("stop_hook_active") and audit_pending(payload):
                print(json.dumps({"decision": "block", "reason": audit_reason(ph.handoff_path(sid))}))
            elif not from_agent(payload) and os.path.isfile(ph.rewrite_flag_path(sid)):
                reason = rewrite_check(payload)
                if reason:
                    print(json.dumps({"decision": "block", "reason": reason}))
    except Exception as e:
        sys.stderr.write("reread_check: %s\n" % e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
