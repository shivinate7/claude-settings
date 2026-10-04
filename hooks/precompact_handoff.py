#!/usr/bin/env python3
"""Claude Code hook: get the session's handoff ready before compaction.

Spec: decisions/precompact-handoff.md. Two modes, one file. Neither mode calls a model:
the owner rejected a `claude -p` child, since it needs its own command-line login, and
the desktop app has none.

  PreCompact (stdin: session_id, transcript_path, cwd) -- builds a digest of the
  transcript's user/assistant text (last 60,000 characters), writes it to
  ~/.claude/state/handoff/<session_id>.digest.md, and records the outcome in
  ~/.claude/state/handoff/<session_id>.json (digest path, repo top level, ok or failed,
  time).

  SessionStart --reorient (stdin: session_id) -- reads that state and prints a short
  message: follow the installed prompt file, then use the digest (or, with no usable
  digest, the compaction summary and the prior handoff alone).

Never exits 2 and never blocks compaction: every failure is caught, logged to stderr,
and the hook still exits 0 (case_precompact_error_is_ok_false).
"""
import datetime
import json
import os
import sys

DIGEST_CAP = 60_000


def config_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude")


def digest_path(session_id):
    return os.path.join(config_dir(), "state", "handoff", "%s.digest.md" % session_id)


def state_path(session_id):
    return os.path.join(config_dir(), "state", "handoff", "%s.json" % session_id)


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


def run_reorient(payload):
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
    if not state or not state.get("ok") or not state.get("digest"):
        print("Context was compacted. Follow %s before anything else. The digest is "
              "missing: use the compaction summary and the prior handoff instead. "
              "Confirm checkout and branch before any git write. Then continue the "
              "last task." % prompt)
        return 0

    print("Context was compacted. Follow %s before anything else. Use the compaction "
          "summary, the digest at %s, and the prior handoff. Confirm checkout and "
          "branch before any git write. Then continue the last task."
          % (prompt, state.get("digest")))
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
        if "--reorient" in sys.argv[1:]:
            return run_reorient(payload)
        return run_precompact(payload)
    except Exception as e:
        sys.stderr.write("precompact_handoff: unexpected error: %s\n" % e)
        return 0


if __name__ == "__main__":
    sys.exit(main())
