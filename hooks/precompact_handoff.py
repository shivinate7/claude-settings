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
  transcript's user/assistant text (last 60,000 characters), writes it to
  ~/.claude/state/handoff/<session_id>.digest.md, and records the outcome in
  ~/.claude/state/handoff/<session_id>.json (digest path, repo top level, ok or failed,
  time).

  SessionStart --reorient (stdin: session_id) -- reads that state and prints a short
  message: follow the installed prompt file, rewrite the session's own handoff at
  ~/.claude/handoffs/<session_id>.md, then use the digest (or, with no usable
  digest, the compaction summary and the prior handoff alone).

  Stop --nudge (stdin: session_id, transcript_path, stop_hook_active) -- reads the last
  main-chain, non-synthetic assistant entry's usage, if above 0 (input + cache_creation +
  cache_read tokens) as the context size. Overhead = the first such entry's size. Messages
  = size - overhead, at least 0 (a proxy: record hook-inputs-carry-token-counts). Bucket =
  index of the highest checkpoint that messages reached, -1 below the first, and -1 when
  messages is 0 (checkpoints(limit - overhead): 200k, +150k while below the top, then the
  top = room - 50k; limit = autoCompactWindow in <config dir>/settings.json, default
  500,000). The last checkpoint is at size = limit - 50k. The bucket lives in
  ~/.claude/state/handoff/<session_id>.nudge.json as {"bucket": N}. A higher bucket
  than stored prints {"decision": "block", "reason": ...}: rewrite the handoff per the
  prompt file's step 4. A lower bucket (after compaction) is stored silently. Nothing
  prints when stop_hook_active is true or on any error.

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
import os
import re
import sys
import time

DIGEST_CAP = 60_000
# A .dir or .reread record this old has no live session: Claude Code deletes a transcript after
# cleanupPeriodDays (default 30), so no session that old can resume. The record sets no value.
STALE_AGE = 30 * 86400
NUDGE_FLOOR = 200_000
NUDGE_STEP = 150_000
NUDGE_MARGIN = 50_000
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


def build_digest(transcript_path, cap=DIGEST_CAP):
    """User and assistant text only, tool results and thinking dropped, last `cap`
    characters kept (the tail: newest text matters most, see docs/decisions/precompact-
    handoff.md's "Known limits"). Raises OSError when the transcript cannot be read, so
    the caller can tell "nothing to digest" from "an empty session"."""
    parts = []
    with open(transcript_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("type") not in ("user", "assistant"):
                continue
            content = (entry.get("message") or {}).get("content")
            if isinstance(content, str):
                parts.append(content)
                continue
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text")
                    if isinstance(text, str):
                        parts.append(text)
    digest = "\n".join(parts)
    if len(digest) > cap:
        digest = digest[-cap:]
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
        digest = build_digest(transcript_path)
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
        import feedback_gate
        import local_time
        paths = local_time.inbox_paths(session_id)
        if paths is None or not os.path.exists(paths[0]):
            return ""
        with open(paths[0], encoding="utf-8") as f:
            ids = feedback_gate.open_ids(feedback_gate.parse(f.read()))
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
        note = (" Premises are claims. Check each before you act on it, then rewrite its "
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


def checkpoints(limit):
    """Nudge sizes: 200k, then +150k while below limit-50k, then limit-50k itself
    (500k: 200, 350, 450k). When limit-50k <= 200k, only limit-50k. A step within
    NUDGE_STEP // 2 of limit-50k is dropped: two rewrites that close are one too many."""
    top = limit - NUDGE_MARGIN
    if top <= NUDGE_FLOOR:
        return [top]
    cps = [NUDGE_FLOOR]
    while cps[-1] + NUDGE_STEP < top:
        cps.append(cps[-1] + NUDGE_STEP)
    while len(cps) > 1 and top - cps[-1] < NUDGE_STEP // 2:
        cps.pop()
    return cps + [top]


def window_limit():
    # ponytail: the model's own window can be smaller than autoCompactWindow and this
    # hook cannot see it; nudges then come late. The first one now comes `overhead` tokens
    # later in total, so a model window smaller than autoCompactWindow can skip it. Upgrade: read the window from the model.
    try:
        with open(os.path.join(config_dir(), "settings.json"), "r", encoding="utf-8") as f:
            v = json.load(f).get("autoCompactWindow")
        return v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else DEFAULT_WINDOW
    except Exception:
        return DEFAULT_WINDOW


def run_nudge(payload):
    try:
        record_dir(payload.get("session_id", ""), payload.get("cwd"))
    except Exception as e:
        sys.stderr.write("precompact_handoff: could not record the dir: %s\n" % e)
    if payload.get("stop_hook_active"):
        return 0
    try:
        session_id = payload.get("session_id", "")
        size = overhead = None
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
        if size is None:
            return 0
        # Proxy (record hook-inputs-carry-token-counts): the first turn is mostly overhead.
        messages = max(size - overhead, 0)
        if messages == 0:
            bucket = -1  # nothing to hand off, even when the room left is zero or negative
        else:
            bucket = sum(1 for c in checkpoints(window_limit() - overhead)
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
