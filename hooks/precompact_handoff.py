#!/usr/bin/env python3
"""Claude Code hook: get the session's handoff ready before compaction.

Modes:
- PreCompact: Before compaction, builds a digest of the session's user and assistant
  text and records the outcome in the session's handoff state. Never refuses compaction.
- --nudge: At Stop, refuses once each time the context size passes a new checkpoint, and
  tells the session to rewrite its handoff. Silent on stop_hook_active or an error.
- --reorient: At SessionStart after compact, clear or fork, tells the session to rewrite
  its handoff from the digest. After clear or fork, it also names the handoff of the prior
  session for the same project.
- --session-end: At SessionEnd with reason clear, writes a pointer file that holds the old
  session id and the project folder, so the next session can find the old handoff.

Spec: docs/decisions/precompact-handoff.md. Three modes, one file. No mode calls a model:
the owner rejected a `claude -p` child, since it needs its own command-line login, and
the desktop app has none.

  PreCompact (stdin: session_id, transcript_path, cwd) -- builds a digest of the
  transcript's user/assistant text, writes it to ~/.claude/state/handoff/<session_id>.digest.md,
  and records the outcome in ~/.claude/state/handoff/<session_id>.json (digest path, repo top
  level, ok or failed, time). With a handoff file, the digest runs from that file's last
  rewrite (its mtime), capped at 200,000 characters; with none, it is the last 60,000
  characters. A "## Refused acts" section ends it: the first line (200 characters at most) of
  the newest 50 refused tool results in that span, oldest first. Cost: one extra small JSON file
  read (~/.claude.json) at PreCompact; no process start, no file written beyond the digest.
  The Claude config file is read at each Stop only, not at PreCompact.

  SessionStart --reorient (stdin: session_id) -- reads that state and prints a short
  message: follow the installed prompt file, rewrite the session's own handoff at
  ~/.claude/handoffs/<session_id>.md, then use the digest (or, with no usable
  digest, the compaction summary and the prior handoff alone).

  Stop --nudge (stdin: session_id, transcript_path, stop_hook_active) -- reads the last
  main-chain, non-synthetic assistant entry's usage, if above 0 (input + cache_creation +
  cache_read tokens) as the context size. Overhead = the first such entry's size. Messages
  = size - overhead, at least 0 (a proxy: record hook-inputs-carry-token-counts). Bucket =
  index of the highest checkpoint that messages reached, -1 below the first, and -1 when
  messages is 0 (checkpoints(compact_threshold(limit) - overhead): 200k, +150k while below
  the top, then the top = room - margin; limit = window_limit(model of the last such entry): env
  CLAUDE_CODE_AUTO_COMPACT_WINDOW (a count, or a k/m suffix such as 200k, 1.5m), then modelSettings.<model>.autoCompactWindow, then
  autoCompactWindow in <config dir>/settings.json, default 500,000). compact_threshold follows
  Claude Code's own compaction trigger: min(E - round(E * f), E - 13k), E = limit - 20k, and f =
  summary_fraction(limit), the summary buffer fraction in the flags Claude Code caches in
  $CLAUDE_CONFIG_DIR/.claude.json (else ~/.claude.json): the tengu_amber_moleskin table, then
  tengu_amber_rokovoko, then 0.2 (384k on 500k with 0.2; 441.6k with 0.08).
  CLAUDE_AUTOCOMPACT_PCT_OVERRIDE (0 < p <= 100) can lower it in every session and window.
  The hook cannot read the session's live state, so it reads the same cached flag. The last
  checkpoint is at size = threshold - margin, margin = min(50k, room // 2), so it always sits
  below the live threshold. The bucket lives in
  ~/.claude/state/handoff/<session_id>.nudge.json as {"bucket": N}. A higher bucket
  than stored prints {"decision": "block", "reason": ...}: rewrite the handoff per the
  prompt file's step 4. A lower bucket (after compaction) is stored silently. Nothing
  prints when stop_hook_active is true or on any error. Cost: one extra small JSON file read
  (~/.claude.json) at each Stop; no process start, no file written.

  SessionEnd --session-end (stdin: session_id, reason, cwd) -- reason `clear` writes
  one pointer file, ~/.claude/state/handoff/pointers/<session_id>.json, holding the old
  session id and the project dir. Any other reason writes nothing.

  SessionStart --reorient with source `clear` or `fork` -- names the handoff of the
  newest pointer for the same project dir (none when that session has no handoff); with no
  pointer, the newest handoff whose PreCompact state `repo` is that dir; with none, says
  "no handoff". It also names the new session's own handoff. Every reorient then sweeps
  unusable pointers and stale .dir and .reread records (sweep()).
  Spec: docs/decisions/precompact-handoff.md, item 8.

Never exits 2 and never refuses compaction: every failure is caught, logged to stderr,
and the hook still exits 0 (case_precompact_error_is_ok_false).
"""
import datetime
import json
import math
import os
import re
import sys
import time

DIGEST_CAP = 60_000
# With a handoff, the digest runs from its last rewrite, so it needs room for all of that span.
DIGEST_SINCE_CAP = 200_000
REFUSED_MAX_LINES = 50
REFUSED_MAX_CHARS = 200
# A .dir or .reread record this old has no live session: Claude Code deletes a transcript after
# cleanupPeriodDays (default 30), so no session that old can resume. The record sets no value.
STALE_AGE = 30 * 86400
NUDGE_FLOOR = 200_000
NUDGE_STEP = 150_000
NUDGE_MARGIN = 50_000
# Claude Code's effective window is window minus 20,000 (the reserve for the summary's output).
# Auto-compact fires at the effective window minus a summary buffer of fraction f of it, and never
# above the effective window minus 13,000. summary_fraction reads f from the flags Claude Code
# caches. CLAUDE_AUTOCOMPACT_PCT_OVERRIDE can lower it in every session and window.
OUTPUT_RESERVE = 20_000
BUFFER_FLOOR = 13_000
DEFAULT_SUMMARY_FRACTION = 0.2
DEFAULT_WINDOW = 500_000
# The source kinds of a handoff premise, strongest first. docs/decisions/premise-format.md says what
# each means and lists the same names; case_premise_kinds_one_home keeps the two equal.
PREMISE_KINDS = ("ruling", "measured", "read", "notes", "assumed")
_PREMISES_HEAD = re.compile(r"^##[ \t]+Working premises[ \t]*$", re.I | re.M)
_PREMISE_LINE = re.compile(r"^[ \t]*[-*][ \t]+(P\d+)\b(?:[ \t]*\[([^\]\n]*)\])?", re.M)


def config_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude")


def digest_path(session_id):
    return os.path.join(config_dir(), "state", "handoff", "%s.digest.md" % session_id)


def state_path(session_id):
    return os.path.join(config_dir(), "state", "handoff", "%s.json" % session_id)


def handoff_path(session_id):
    """The session's own handoff: per session and outside git, so concurrent sessions on
    their own branches never collide on it, and outside Temp, so temp cleanup never
    reaches it (docs/decisions/precompact-handoff.md). It lives in <config_dir>/handoffs/, not
    the frozen state dir, so a session can write it. The digest, .json and .nudge.json
    stay in state/handoff/."""
    return os.path.join(config_dir(), "handoffs", "%s.md" % session_id)


def ensure_handoff_dir(session_id):
    """Create <config_dir>/handoffs/ so the session can write its handoff. Creates only;
    never touches files in it. A failure never refuses."""
    try:
        os.makedirs(os.path.dirname(handoff_path(session_id)), exist_ok=True)
    except Exception as e:
        sys.stderr.write("precompact_handoff: could not create handoffs dir: %s\n" % e)


def prompt_path():
    """The installed prompt file: ~/.claude/hooks/precompact_handoff_prompt.md, not this
    repo's own copy -- the reorient message must name the path the session actually
    reads, under CLAUDE_CONFIG_DIR, the way `claude-settings` installs hooks."""
    return os.path.join(config_dir(), "hooks", "precompact_handoff_prompt.md")


def _entry_time(entry):
    """The entry's timestamp as epoch seconds, or None when it has none or it is unreadable."""
    ts = entry.get("timestamp")
    if not isinstance(ts, str):
        return None
    try:
        when = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if when.tzinfo is None:
            when = when.replace(tzinfo=datetime.timezone.utc)
        return when.timestamp()
    except ValueError:
        return None


def _result_text(block):
    """The text of a tool_result block, whether its content is a string or a list of blocks."""
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b["text"] for b in content
                         if isinstance(b, dict) and isinstance(b.get("text"), str))
    return ""


# A refused act: a failed tool result whose first line says a hook or a permission turned it away:
# "<Event>:<Tool> hook error", the user's "doesn't want to proceed" / "tool use was rejected",
# "Permission to use <Tool> has been denied", or a first line that starts "denied:" or "refused:".
# A plain failure ("Exit code 1", ECONNREFUSED, an OS "Permission denied") is not one.
_REFUSAL = re.compile(
    r"hook error|(?:doesn['\u2019]t|does not) want to proceed|tool use was rejected"
    r"|permission to use \S+ has been denied|^(?:denied|refused):", re.I)


def _refusal_line(block):
    """The first line of a refused tool result, cut to REFUSED_MAX_CHARS, else None."""
    if block.get("type") != "tool_result" or block.get("is_error") is not True:
        return None
    lines = _result_text(block).strip().splitlines()
    first = lines[0].strip() if lines else ""
    return first[:REFUSED_MAX_CHARS] if _REFUSAL.search(first) else None


def build_digest(transcript_path, since=None, cap=DIGEST_CAP):
    """User and assistant text, then a "## Refused acts" section. Tool results and thinking are
    dropped except refusals. With `since` (epoch seconds, the handoff's last rewrite), only entries
    from then on count and the text cap is DIGEST_SINCE_CAP; an entry with no readable time stays.
    Without it, the last `cap` characters (the tail: newest text matters most, see docs/decisions/
    precompact-handoff.md's "Known limits"). The section lists the first line of the newest
    REFUSED_MAX_LINES refusals, oldest first. Raises OSError when the transcript cannot be read, so
    the caller can tell "nothing to digest" from "an empty session"."""
    if since is not None and cap == DIGEST_CAP:
        cap = DIGEST_SINCE_CAP
    parts = []
    refused = []
    with open(transcript_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if not isinstance(entry, dict) or entry.get("type") not in ("user", "assistant"):
                continue
            if since is not None:
                when = _entry_time(entry)
                if when is not None and when < since:
                    continue
            content = (entry.get("message") or {}).get("content")
            if isinstance(content, str):
                parts.append(content)
                continue
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    text = block.get("text")
                    if isinstance(text, str):
                        parts.append(text)
                else:
                    first = _refusal_line(block)
                    if first:
                        refused.append(first)
    digest = "\n".join(parts)
    if len(digest) > cap:
        digest = digest[-cap:]
    if refused:
        digest += "\n\n## Refused acts\n" + "\n".join(refused[-REFUSED_MAX_LINES:]) + "\n"
    return digest


def _repo_top_level(cwd):
    """The repo top level. The hook input's own `cwd` already is that top level in
    normal use (the session's project directory); record it as given, so the path
    this hook writes is the same string the rest of the session already uses."""
    return cwd


def _write_state(session_id, digest_path_, repo_top, ok, failure):
    path = state_path(session_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    state = {
        "digest": digest_path_,
        "repo": repo_top,
        "ok": bool(ok),
        "time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    if failure:
        state["failure"] = failure
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(tmp, path)


def run_precompact(payload):
    session_id = payload.get("session_id", "")
    transcript_path = payload.get("transcript_path", "")
    cwd = payload.get("cwd") or os.getcwd()
    repo_top = _repo_top_level(cwd)
    ensure_handoff_dir(session_id)

    ok = False
    digest_path_ = None
    failure = None
    try:
        try:
            since = os.path.getmtime(handoff_path(session_id))
        except OSError:
            since = None
        digest = build_digest(transcript_path, since=since)
        digest_path_ = digest_path(session_id)
        os.makedirs(os.path.dirname(digest_path_), exist_ok=True)
        tmp = digest_path_ + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(digest)
        os.replace(tmp, digest_path_)
        ok = True
    except Exception as e:
        failure = "could not build the digest: %s" % e
        digest_path_ = None

    try:
        _write_state(session_id, digest_path_, repo_top, ok, failure)
    except Exception as e:
        sys.stderr.write("precompact_handoff: could not write state: %s\n" % e)
    if failure:
        sys.stderr.write("precompact_handoff: %s\n" % failure)
    return 0


def same_dir(a, b):
    """The same folder: equal after normpath, or after realpath (a short 8.3 name and
    its long name on Windows). Also used by reread_check for the handoff file."""
    if not a or not b:
        return False
    if os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b)):
        return True
    try:
        return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))
    except (OSError, ValueError):
        return False


def pointer_dir():
    return os.path.join(config_dir(), "state", "handoff", "pointers")


def reread_flag_path(session_id):
    """The flag reread_check sets after compaction. Defined here so SessionEnd can drop it."""
    return os.path.join(config_dir(), "state", "handoff", "%s.reread" % session_id)


def record_dir(session_id, cwd):
    """Record the session's project dir in <sid>.dir, so the fork fallback finds a session
    that never compacted. Every handoff hook that runs for a session calls this."""
    if not session_id or not cwd:
        return
    path = os.path.join(os.path.dirname(state_path(session_id)), "%s.dir" % session_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(cwd)


def recorded_dir(session_id):
    """The project dir of a session: its .dir record, else the PreCompact state's repo."""
    try:
        with open(state_path(session_id)[:-len(".json")] + ".dir", "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        pass
    try:
        with open(state_path(session_id), "r", encoding="utf-8") as f:
            return json.load(f).get("repo")
    except Exception:
        return None


def run_session_end(payload):
    """SessionEnd: record the dir for any reason. Only reason `clear` leaves a pointer to
    the old session, and drops that session's re-read flag."""
    session_id = payload.get("session_id", "")
    if not session_id:
        return 0
    cwd = payload.get("cwd") or os.getcwd()
    record_dir(session_id, cwd)
    if payload.get("reason") != "clear":
        return 0
    try:
        os.remove(reread_flag_path(session_id))
    except OSError:
        pass
    os.makedirs(pointer_dir(), exist_ok=True)
    path = os.path.join(pointer_dir(), "%s.json" % session_id)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"session_id": session_id, "cwd": cwd}, f)
    os.replace(tmp, path)
    return 0


def _newest(paths):
    return max(paths, key=os.path.getmtime) if paths else None


def _remove(path):
    """Delete one file. A failure is logged, naming the file: a silent failure hides it."""
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError as e:
        sys.stderr.write("precompact_handoff: could not remove %s: %s\n" % (path, e))


def pointers():
    """{pointer file: (old session id, project dir)}; (None, None) for a malformed one."""
    found = {}
    pdir = pointer_dir()
    for name in os.listdir(pdir) if os.path.isdir(pdir) else []:
        if not name.endswith(".json"):
            continue
        path = os.path.join(pdir, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                ptr = json.load(f)
            sid, pcwd = ptr["session_id"], ptr["cwd"]
            if not (isinstance(sid, str) and sid and isinstance(pcwd, str)):
                raise ValueError
        except OSError:
            continue   # unreadable now, maybe in use: leave it
        except Exception:
            sid = pcwd = None
        found[path] = (sid, pcwd)
    return found


def sweep(cwd):
    """Drop records no session can use: a malformed pointer, a pointer for this dir whose
    session has no handoff, and a .dir or .reread record older than STALE_AGE. Another dir's
    pointer stays: that dir can be mid-/clear. Each failed delete is logged."""
    for path, (sid, pcwd) in pointers().items():
        if sid is None or (same_dir(pcwd, cwd) and not os.path.isfile(handoff_path(sid))):
            _remove(path)
    sdir = os.path.dirname(state_path("x"))
    now = time.time()
    for name in os.listdir(sdir) if os.path.isdir(sdir) else []:
        base, ext = os.path.splitext(name)
        path = os.path.join(sdir, name)
        if ext in (".dir", ".reread") and "." not in base and os.path.isfile(path):
            try:
                old = now - os.path.getmtime(path) > STALE_AGE
            except OSError:
                continue
            if old:
                _remove(path)


def find_newest_handoff(cwd, usable):
    """The newest handoff file of a session recorded in this dir, or None."""
    sdir = os.path.dirname(state_path("x"))
    sids = set()
    for name in os.listdir(sdir) if os.path.isdir(sdir) else []:
        base, ext = os.path.splitext(name)
        if ext in (".dir", ".json") and "." not in base:
            sids.add(base)  # skips <sid>.nudge.json and <sid>.digest.md
    return _newest([handoff_path(s) for s in sids
                    if usable(s) and same_dir(recorded_dir(s), cwd)])


def run_reorient_cleared(payload):
    """clear: the newest pointer for this dir, which is used up and deleted. Its session's
    handoff is named, or none when it has none: never another session's. fork: no pointer
    (it can name an older cleared session), only the newest handoff for the dir. Either way,
    with no pointer the newest handoff for the dir. ponytail: matches by dir only, so two
    sessions clearing in one dir at once can swap pointers (docs/decisions/precompact-handoff.md, item 8)."""
    session_id = payload.get("session_id", "")
    cwd = payload.get("cwd") or os.getcwd()
    ensure_handoff_dir(session_id)
    mine = handoff_path(session_id)

    def usable(sid):
        return bool(sid) and sid != session_id and os.path.isfile(handoff_path(sid))

    ptr = None
    if payload.get("source") == "clear":
        found = {p: sid for p, (sid, pcwd) in pointers().items() if sid and same_dir(pcwd, cwd)}
        ptr = _newest(found)
    if ptr:
        _remove(ptr)
        old = handoff_path(found[ptr]) if usable(found[ptr]) else None
    else:
        old = find_newest_handoff(cwd, usable)
    if not old:
        print("This session started after /clear or a fork. There is no handoff for this "
              "project dir. Your handoff is %s. Write it as you work; never append." % mine)
        return 0
    print("This session started after /clear or a fork. Read %s first; it is the handoff of "
          "the session this one follows. Then follow %s and rewrite your own handoff at %s "
          "from it. Rewrite it whole; never append. Confirm checkout and branch before any "
          "git write. Then continue the last task.%s"
          % (old, prompt_path(), mine, premise_note(old, True)))
    return 0


def inbox_note(session_id):
    """The owner feedback inbox's "After compaction" line (decision owner-feedback-inbox): the open
    item ids (ruling, task, standing) from <session_id>.inbox.md. "" when there is nothing to say.
    Never raises: the reorient message must still print."""
    try:
        import feedback_guard
        import local_time
        paths = local_time.inbox_paths(session_id)
        if paths is None or not os.path.exists(paths[0]):
            return ""
        with open(paths[0], encoding="utf-8") as f:
            ids = feedback_guard.open_ids(feedback_guard.parse(f.read()))
    except Exception as e:
        sys.stderr.write("precompact_handoff: inbox note failed: %s\n" % e)
        return ""
    if not ids:
        return ""
    return (" Open feedback items: %s. Keep each standing item in the handoff, and give"
            " each ruling and task its tracked home: a decision record or rule, or the"
            " repo's todo or debt store." % ", ".join(ids))


def handoff_premises(path):
    """[(id, kind)] of the premise lines in the handoff's Working premises section, in order,
    one entry per id. [] when the file is unreadable or the section is missing or has no line.
    Reads text only. A kind outside PREMISE_KINDS is kept as written, so the caller lists it."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except (OSError, ValueError):  # ValueError: a byte that is not UTF-8
        return []
    head = _PREMISES_HEAD.search(text)
    if not head:
        return []
    body = text[head.end():]
    end = re.search(r"^#{1,2}[ \t]", body, re.M)
    found = {}
    for m in _PREMISE_LINE.finditer(body[:end.start()] if end else body):
        found.setdefault(m.group(1), (m.group(2) or "").strip().lower())
    return list(found.items())


def premise_note(path, everyone):
    """The reorient text on premises; "" when the handoff file does not exist. everyone: list
    every premise, since the handoff came from another session. Else list all but the strongest
    kind, PREMISE_KINDS[0].
    A kind outside PREMISE_KINDS is not a ruling, so it is listed."""
    if not os.path.isfile(path):
        return ""
    prem = handoff_premises(path)
    if not prem:
        note = " The handoff has no Working premises section. Add it per step 4."
    else:
        weak = ["%s (%s)" % (i, k or "no kind") for i, k in prem if everyone or k != PREMISE_KINDS[0]]
        note = (" Premises are statements. Check each before you act on it, then rewrite its "
                "line: %s." % ", ".join(weak)) if weak else ""
    if not everyone:
        note += " Facts in the compaction summary are notes until checked."
    return note


def run_reorient(payload):
    try:
        return _run_reorient(payload)
    finally:
        try:
            sweep(payload.get("cwd") or os.getcwd())
        except Exception as e:
            sys.stderr.write("precompact_handoff: sweep error: %s\n" % e)


def _run_reorient(payload):
    if payload.get("source") in ("clear", "fork"):
        return run_reorient_cleared(payload)
    session_id = payload.get("session_id", "")
    state = None
    try:
        path = state_path(session_id)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)
    except Exception:
        state = None

    prompt = prompt_path()
    ensure_handoff_dir(session_id)
    handoff = handoff_path(session_id)
    if not state or not state.get("ok") or not state.get("digest"):
        print("Context was compacted. Follow %s before anything else. Your handoff is "
              "%s. Rewrite it whole; never append. The digest is missing: use the "
              "compaction summary and the prior handoff instead. Confirm checkout and branch before any git write. Then "
              "continue the last task.%s%s"
              % (prompt, handoff, premise_note(handoff, False), inbox_note(session_id)))
        return 0

    print("Context was compacted. Follow %s before anything else. Your handoff is %s. "
          "Rewrite it whole; never append. Use the compaction summary, the digest at %s, and the prior handoff. Confirm "
          "checkout and branch before any git write. Then continue the last task.%s%s"
          % (prompt, handoff, state.get("digest"), premise_note(handoff, False),
             inbox_note(session_id)))
    return 0


def checkpoints(room):
    """Nudge message sizes for `room` tokens of messages before compaction. The top is
    room - margin, with margin = min(NUDGE_MARGIN, room // 2), so a small room keeps a
    positive top. Below the top: 200k, then +150k while below the top. A step under
    NUDGE_STEP // 2 below the top is dropped, the 200k floor included: two rewrites that
    close are one too many (room 384k: 200k, 334k; room 299k: 249k). When top <= 200k, only
    the top. For room <= 0, only room - NUDGE_MARGIN, whatever its sign."""
    margin = min(NUDGE_MARGIN, room // 2) if room > 0 else NUDGE_MARGIN
    top = room - margin
    if top <= NUDGE_FLOOR:
        return [top]
    cps = [NUDGE_FLOOR]
    while cps[-1] + NUDGE_STEP < top:
        cps.append(cps[-1] + NUDGE_STEP)
    while cps and top - cps[-1] < NUDGE_STEP // 2:
        cps.pop()
    return cps + [top]


def _model_key(name):
    """A model or modelSettings key without a trailing `[...]` tag or `-YYYYMMDD` date."""
    return re.sub(r"-\d{8}$", "", re.sub(r"\[[^\]]*\]$", "", name))


def _fraction_ok(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v < 1


def _flag_table_fraction(table, limit):
    """The fraction from the tengu_amber_moleskin table, or None when the table is malformed or
    has no entry for this window and entrypoint. Every entry must be a dict whose repl and sdk
    values, where present, are valid; one bad entry makes the whole table malformed."""
    if not isinstance(table, dict):
        return None
    for entry in table.values():
        if not isinstance(entry, dict):
            return None
        if any(k in entry and not _fraction_ok(entry[k]) for k in ("repl", "sdk")):
            return None
    entry = table.get(str(limit), table.get("default"))
    column = "sdk" if os.environ.get("CLAUDE_CODE_ENTRYPOINT", "").startswith("sdk") else "repl"
    return entry.get(column) if entry else None


def summary_fraction(limit):
    """The summary buffer fraction Claude Code compacts with, from its cached flags in
    $CLAUDE_CONFIG_DIR/.claude.json (else ~/.claude.json), key cachedGrowthBookFeatures: the
    tengu_amber_moleskin table, then the scalar tengu_amber_rokovoko, then
    DEFAULT_SUMMARY_FRACTION. A missing or bad file gives the default. The hook cannot read the
    session's live state, so it reads the same cached flag."""
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~")
    try:
        with open(os.path.join(base, ".claude.json"), "r", encoding="utf-8") as f:
            features = json.load(f)["cachedGrowthBookFeatures"]
        if not isinstance(features, dict):
            return DEFAULT_SUMMARY_FRACTION
    except Exception:
        return DEFAULT_SUMMARY_FRACTION
    f = _flag_table_fraction(features.get("tengu_amber_moleskin"), limit)
    if _fraction_ok(f):
        return f
    f = features.get("tengu_amber_rokovoko")
    return f if _fraction_ok(f) else DEFAULT_SUMMARY_FRACTION


def _remote_pct():
    """CLAUDE_AUTOCOMPACT_PCT_OVERRIDE as a number in (0, 100], else None. Claude Code 2.1.316
    applies it in every session and window."""
    try:
        p = float(os.environ.get("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE", ""))
    except ValueError:
        return None
    return p if 0 < p <= 100 else None


def compact_threshold(limit):
    """The context size at which Claude Code compacts a window of `limit` tokens. Mirrors Claude
    Code 2.1.316: effective window E = limit - OUTPUT_RESERVE, summary buffer fraction f, and the
    percent override. The hook cannot read the session's live state, so it reads the same cached
    flag (summary_fraction).

    Claude Code compacts at the second term, min(floor(E * p / 100), E - 13k), when the percent
    override is set. The first term, min(E - round(E * f), E - 13k), is its early-summary
    (precompute) point. The hook takes the lower of the two, since what a precomputed summary
    keeps is not read."""
    eff = limit - OUTPUT_RESERVE
    cap = eff - BUFFER_FLOOR
    threshold = min(eff - math.floor(eff * summary_fraction(limit) + 0.5), cap)  # JS Math.round
    pct = _remote_pct()
    if pct is not None:
        threshold = min(threshold, min(math.floor(eff * pct / 100), cap))
    return int(threshold)


_WINDOW_SUFFIX = re.compile(r"(\d+(?:\.\d+)?)([km])", re.I)


def window_limit(model=None):
    """The session's auto-compact window: env CLAUDE_CODE_AUTO_COMPACT_WINDOW, then
    modelSettings.<model>.autoCompactWindow, then top-level autoCompactWindow in
    <config dir>/settings.json, then DEFAULT_WINDOW. A bad value falls to the next tier."""
    # shortcut: the model's own window is not read, so a model window smaller than every
    # tier makes nudges late and can skip the first one. Upgrade when hook input carries it.
    def parse(v):
        """A token count: a positive int, or a string with a k/m suffix ("200k", "1.5M"), else None."""
        if isinstance(v, int) and not isinstance(v, bool):
            return v if v > 0 else None
        if isinstance(v, str):
            m = _WINDOW_SUFFIX.fullmatch(v.strip())
            if m:
                unit = 1000 if m.group(2).lower() == "k" else 1_000_000
                n = int(round(float(m.group(1)) * unit))
                return n if n > 0 else None
        return None
    env = os.environ.get("CLAUDE_CODE_AUTO_COMPACT_WINDOW", "")
    try:
        v = int(env)
        if v > 0:
            return v
    except ValueError:
        v = parse(env)
        if v:
            return v
    try:
        with open(os.path.join(config_dir(), "settings.json"), "r", encoding="utf-8") as f:
            settings = json.load(f)
    except Exception:
        return DEFAULT_WINDOW
    if not isinstance(settings, dict):
        return DEFAULT_WINDOW
    per_model = settings.get("modelSettings")
    if isinstance(model, str) and isinstance(per_model, dict):
        want = _model_key(model)
        for key in sorted(per_model, key=lambda k: k != model):  # an exact key first
            entry = per_model[key]
            if _model_key(key) == want and isinstance(entry, dict):
                v = parse(entry.get("autoCompactWindow"))
                if v:
                    return v
    return parse(settings.get("autoCompactWindow")) or DEFAULT_WINDOW


def run_nudge(payload):
    try:
        record_dir(payload.get("session_id", ""), payload.get("cwd"))
    except Exception as e:
        sys.stderr.write("precompact_handoff: could not record the dir: %s\n" % e)
    if payload.get("stop_hook_active"):
        return 0
    try:
        session_id = payload.get("session_id", "")
        size = overhead = model = None
        with open(payload.get("transcript_path", ""), "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if entry.get("type") != "assistant" or entry.get("isSidechain") is True:
                    continue
                msg = entry.get("message") or {}
                u = msg.get("usage")
                if msg.get("model") == "<synthetic>" or not isinstance(u, dict):
                    continue
                n = sum(u.get(k) or 0 for k in (
                    "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
                if n > 0:
                    if overhead is None:
                        overhead = n
                    size = n
                    model = msg.get("model") or model
        if size is None:
            return 0
        # Proxy (record hook-inputs-carry-token-counts): the first turn is mostly overhead.
        messages = max(size - overhead, 0)
        if messages == 0:
            bucket = -1  # nothing to hand off, even when the room left is zero or negative
        else:
            bucket = sum(1 for c in checkpoints(compact_threshold(window_limit(model)) - overhead)
                         if messages >= c) - 1
        path = os.path.join(config_dir(), "state", "handoff", "%s.nudge.json" % session_id)
        try:
            with open(path, "r", encoding="utf-8") as f:
                stored = int(json.load(f)["bucket"])
        except Exception:
            stored = -1
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"bucket": bucket}, f)
        if bucket > stored:
            ensure_handoff_dir(session_id)
            print(json.dumps({"decision": "block", "reason": (
                "Context is about %dk tokens, messages about %dk. Rewrite your handoff at %s now, the whole "
                "file; never append. Follow step 4 of %s for its sections and their order. "
                "Then continue."
                % (size // 1000, messages // 1000, handoff_path(session_id), prompt_path()))}))
    except Exception as e:
        sys.stderr.write("precompact_handoff: nudge error: %s\n" % e)
    return 0


def main():
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        payload = {}

    try:
        if "--nudge" in sys.argv[1:]:
            return run_nudge(payload)
        if "--session-end" in sys.argv[1:]:
            return run_session_end(payload)
        if "--reorient" in sys.argv[1:]:
            return run_reorient(payload)
        return run_precompact(payload)
    except Exception as e:
        sys.stderr.write("precompact_handoff: unexpected error: %s\n" % e)
        return 0


if __name__ == "__main__":
    sys.exit(main())
