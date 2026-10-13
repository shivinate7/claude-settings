#!/usr/bin/env python3
"""Claude Code hook: get the session's handoff ready before compaction.

Spec: decisions/precompact-handoff.md. Three modes, one file. No mode calls a model:
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
  main-chain, non-synthetic assistant entry's usage, if above 0 (input + cache_creation + cache_read tokens) as the context
  size. Bucket = index of the highest checkpoint reached, -1 below the first (checkpoints():
  200k, +150k while below limit-50k, then limit-50k; limit = autoCompactWindow in
  <config dir>/settings.json, default 500,000). The bucket lives in
  ~/.claude/state/handoff/<session_id>.nudge.json as {"bucket": N}. A higher bucket
  than stored prints {"decision": "block", "reason": ...}: rewrite the handoff per the
  prompt file's step 4. A lower bucket (after compaction) is stored silently. Nothing
  prints when stop_hook_active is true or on any error.

  SessionEnd --session-end (stdin: session_id, reason, cwd) -- reason `clear` writes
  one pointer file, ~/.claude/state/handoff/pointers/<session_id>.json, holding the old
  session id and the project dir. Any other reason writes nothing.

  SessionStart --reorient with source `clear` or `fork` -- names the handoff of the
  newest pointer for the same project dir; with no pointer, the newest handoff whose
  PreCompact state `repo` is that dir; with none, says "no handoff". It also names the
  new session's own handoff. Spec: decisions/handoff-hooks-wave-2.md.

Never exits 2 and never blocks compaction: every failure is caught, logged to stderr,
and the hook still exits 0 (case_precompact_error_is_ok_false).
"""
import datetime
import json
import os
import sys

DIGEST_CAP = 60_000
NUDGE_FLOOR = 200_000
NUDGE_STEP = 150_000
NUDGE_MARGIN = 50_000
DEFAULT_WINDOW = 500_000


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
    reaches it (decisions/precompact-handoff.md). It lives in <config_dir>/handoffs/, not
    the frozen state dir, so a session can write it. The digest, .json and .nudge.json
    stay in state/handoff/."""
    return os.path.join(config_dir(), "handoffs", "%s.md" % session_id)


def ensure_handoff_dir(session_id):
    """Create <config_dir>/handoffs/ so the session can write its handoff. Creates only;
    never touches files in it. A failure never blocks."""
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
    characters kept (the tail: newest text matters most, see decisions/precompact-
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


def _same_dir(a, b):
    """The same folder: equal after normpath, or after realpath (a short 8.3 name and
    its long name on Windows)."""
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


def run_session_end(payload):
    """SessionEnd: only reason `clear` leaves a pointer to the old session."""
    session_id = payload.get("session_id", "")
    if payload.get("reason") != "clear" or not session_id:
        return 0
    os.makedirs(pointer_dir(), exist_ok=True)
    path = os.path.join(pointer_dir(), "%s.json" % session_id)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"session_id": session_id, "cwd": payload.get("cwd") or os.getcwd()}, f)
    os.replace(tmp, path)
    return 0


def _newest(paths):
    return max(paths, key=os.path.getmtime) if paths else None


def find_old_handoff(cwd, new_sid):
    """The handoff to read after /clear or a fork: the newest pointer for this dir, else
    the newest handoff whose PreCompact state names this dir. None when there is none.
    ponytail: matches by dir only, so two sessions clearing in one dir at once can swap
    pointers (decisions/handoff-hooks-wave-2.md, named limits)."""
    def usable(sid):
        return bool(sid) and sid != new_sid and os.path.isfile(handoff_path(sid))

    pointers = {}  # pointer file -> old session id
    pdir = pointer_dir()
    for name in os.listdir(pdir) if os.path.isdir(pdir) else []:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(pdir, name), "r", encoding="utf-8") as f:
                ptr = json.load(f)
        except Exception:
            continue
        if isinstance(ptr, dict) and _same_dir(ptr.get("cwd"), cwd) and usable(
                ptr.get("session_id")):
            pointers[os.path.join(pdir, name)] = ptr["session_id"]
    best = _newest(pointers)
    if best:
        return handoff_path(pointers[best])

    sdir = os.path.dirname(state_path("x"))
    found = []
    for name in os.listdir(sdir) if os.path.isdir(sdir) else []:
        if name.count(".") != 1 or not name.endswith(".json"):
            continue  # skips <sid>.nudge.json and <sid>.digest.md
        sid = name[:-len(".json")]
        try:
            with open(os.path.join(sdir, name), "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            continue
        if isinstance(state, dict) and _same_dir(state.get("repo"), cwd) and usable(sid):
            found.append(handoff_path(sid))
    return _newest(found)


def run_reorient_cleared(payload):
    session_id = payload.get("session_id", "")
    ensure_handoff_dir(session_id)
    mine = handoff_path(session_id)
    old = find_old_handoff(payload.get("cwd") or os.getcwd(), session_id)
    if not old:
        print("This session started after /clear or a fork. There is no handoff for this "
              "project dir. Your handoff is %s. Write it as you work; never append." % mine)
        return 0
    print("This session started after /clear or a fork. Read %s first; it is the handoff of "
          "the session this one follows. Then follow %s and rewrite your own handoff at %s "
          "from it. Rewrite it whole; never append. Confirm checkout and branch before any "
          "git write. Then continue the last task." % (old, prompt_path(), mine))
    return 0


def run_reorient(payload):
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
              "continue the last task." % (prompt, handoff))
        return 0

    print("Context was compacted. Follow %s before anything else. Your handoff is %s. "
          "Rewrite it whole; never append. Use the compaction summary, the digest at %s, and the prior handoff. Confirm "
          "checkout and branch before any git write. Then continue the last task."
          % (prompt, handoff, state.get("digest")))
    return 0


def checkpoints(limit):
    """Nudge sizes: 200k, then +150k while below limit-50k, then limit-50k itself
    (500k: 200, 350, 450k). When limit-50k <= 200k, only limit-50k."""
    top = limit - NUDGE_MARGIN
    if top <= NUDGE_FLOOR:
        return [top]
    cps = [NUDGE_FLOOR]
    while cps[-1] + NUDGE_STEP < top:
        cps.append(cps[-1] + NUDGE_STEP)
    return cps + [top]


def window_limit():
    # ponytail: the model's own window can be smaller than autoCompactWindow and this
    # hook cannot see it; nudges then come late. Upgrade: read the window from the model.
    try:
        with open(os.path.join(config_dir(), "settings.json"), "r", encoding="utf-8") as f:
            v = json.load(f).get("autoCompactWindow")
        return v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else DEFAULT_WINDOW
    except Exception:
        return DEFAULT_WINDOW


def run_nudge(payload):
    if payload.get("stop_hook_active"):
        return 0
    try:
        session_id = payload.get("session_id", "")
        size = None
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
                    size = n
        if size is None:
            return 0
        bucket = sum(1 for c in checkpoints(window_limit()) if size >= c) - 1
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
                "Context is about %dk tokens. Rewrite your handoff at %s now, the whole "
                "file; never append. Follow step 4 of %s: rulings with NO HOME YET first, "
                "where things stand, rulings with their homes, work in flight, next "
                "steps, the files and commands that matter. Then continue."
                % (size // 1000, handoff_path(session_id), prompt_path()))}))
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
