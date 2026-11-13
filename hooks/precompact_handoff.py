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
  the newest 50 refused tool results in that span, oldest first. Cost: no extra file read, no
  process start, no file written beyond the digest. The Claude config file (~/.claude.json) is
  read at each Stop only.

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
  the top, then the top = room - margin, then a late one at room - 20k when 25k or more past the top; limit = window_limit(model of the last such entry): env
  CLAUDE_CODE_AUTO_COMPACT_WINDOW (a count, or a k/m suffix such as 200k, 1.5m; a positive value
  is clamped to 100,000..1,000,000), then modelSettings.<model>.autoCompactWindow, then
  autoCompactWindow in <config dir>/settings.json (each an int in 100,000..1,000,000), default
  500,000). compact_threshold follows
  Claude Code's own compaction trigger: min(E - round(E * f), E - 13k), E = limit - 20k, and f =
  summary_fraction(limit), the summary buffer fraction in the flags Claude Code caches in
  $CLAUDE_CONFIG_DIR/.claude.json (else ~/.claude.json): the tengu_amber_moleskin table, then
  tengu_amber_rokovoko, then 0.2 (408k on 500k with 0.15).
  CLAUDE_AUTOCOMPACT_PCT_OVERRIDE (its leading number p, 0 < p <= 100) can lower it in every session and window.
  Cloud sessions set it per session, read live at each Stop (92 gives 441,600 on 500k; 80 gives 384,000).
  The hook cannot read the session's live state, so it reads the same cached flag. The top
  checkpoint is at size = threshold - margin, margin = min(50k, room // 2), so it always sits
  below the live threshold. The bucket lives in
  ~/.claude/state/handoff/<session_id>.nudge.json as {"bucket": N}. A higher bucket
  than stored prints {"decision": "block", "reason": ...}: rewrite the handoff per the
  prompt file's step 4. A lower bucket (after compaction) is stored silently. Nothing
  prints when stop_hook_active is true or on any error. Cost: one extra small JSON file read
  (~/.claude.json) at each Stop; no process start, no file written.
  The same Stop also checks the handoff's sections: when the session's handoff exists and
  missing_sections() finds a required section absent, it blocks once per handoff mtime, naming the
  missing ones, and keeps that mtime as "sections_mtime" in the same <session_id>.nudge.json (no new
  file). Silent when the handoff is absent or complete. Cost: one small read of the prompt file and of
  the handoff at each Stop; no new log, hook, file or process start. Spec: docs/decisions/precompact-handoff.md,
  item 14.

  The required sections are the names on the marker line `<!-- handoff-sections: A | B | ... -->` in
  step 4 of the installed prompt file, read at run time by missing_sections(); no code holds the list.
  A prompt or marker that cannot be read gives none, so the check fails open. hooks/guard.py calls
  missing_sections() to refuse a write to a handoff that drops one (rule handoff-sections).

  SessionEnd --session-end (stdin: session_id, reason, cwd) -- reason `clear` writes
  one pointer file, ~/.claude/state/handoff/pointers/<session_id>.json, holding the old
  session id and the project dir. Any other reason writes nothing.

  SessionStart --reorient with source `clear` or `fork` -- names the handoff of the
  newest pointer for the same project dir (none when that session has no handoff); with no
  pointer, the newest handoff whose PreCompact state `repo` is that dir; with none, says
  "no handoff". It also names the new session's own handoff. Every reorient then sweeps
  unusable pointers and stale .dir and .reread records (sweep()).
  Spec: docs/decisions/precompact-handoff.md, item 8.

Compaction check (no mode; hooks/daily_note.py calls it at SessionStart): cc_version_check()
reads the Claude Code binary at env CLAUDE_CODE_EXECPATH, else `claude` on env PATH through its link,
in-process, once per new binary (path, size, mtime; one cache entry per path), by anchor strings (setting keys, env names, a flag name, never minified names).
cc_facts() gives each fact or "unknown"; the facts are cached in <config dir>/cc-behavior.json and
compared with hooks/cc_compaction_baseline.json. A changed fact prints one line, for the
session to name under Input Needed. Starts no process. Spec: docs/decisions/precompact-handoff.md,
item 12.

Never exits 2 and never refuses compaction: every failure is caught, logged to stderr,
and the hook still exits 0 (case_precompact_error_is_ok_false).
"""
import datetime
import json
import math
import os
import re
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from shared_names import config_dir  # noqa: E402  the one home of the config dir
except ImportError:  # a copy by need: the hook lands before its sibling in an install, and must still build its digest
    def _config_dir_fallback():
        return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    config_dir = _config_dir_fallback

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
# The late checkpoint: 20k under the room, kept when it sits NUDGE_LATE_GAP or more past the top one.
NUDGE_LATE_MARGIN = 20_000
NUDGE_LATE_GAP = 25_000
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
# The required sections are named once, in the prompt file's step 4 marker line (SECTIONS_MARKER). No code
# copies that list: the premises section is the marker name that holds the word "premises".
SECTIONS_MARKER = re.compile(r"<!--[ \t]*handoff-sections:[ \t]*(.*?)[ \t]*-->")


def section_heading(name_rx):
    """The one heading matcher: a `#` or `##` heading line that starts with the name, which may carry the
    prompt's step number first (`## 2. `) and may be followed by text. `N)` is no step number."""
    return re.compile(r"^#{1,2}[ \t]+(?:\d+\.[ \t]+)?(?:%s)(?!\w)" % name_rx, re.I | re.M)


_PREMISE_LINE = re.compile(r"^[ \t]*[-*][ \t]+(P\d+)\b(?:[ \t]*\[([^\]\n]*)\])?", re.M)


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


def _marker_names(path):
    """The section names on the marker line of the prompt file at `path`, in order. [] when the file
    cannot be read, is not UTF-8, or has no marker. Never raises."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            m = SECTIONS_MARKER.search(f.read())
    except Exception:  # OSError (missing, a directory), ValueError (not UTF-8)
        return []
    return [n.strip() for n in m.group(1).split("|") if n.strip()] if m else []


def required_sections():
    """The sections a handoff must hold, from the marker: the installed prompt's, or, when no installed
    prompt file exists, the copy beside this module (the installed one in an install, the repo's own in a
    checkout). The one reader of the marker: the section check and the premises name both call it. []
    when the prompt cannot be read: the check then fails open."""
    path = prompt_path()
    if not os.path.exists(path):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "precompact_handoff_prompt.md")
    return _marker_names(path)


def premises_section(names=None):
    """The marker's name for the premises section (the one that holds the word "premises"), or None. `names` is
    required_sections()'s value, passed by a caller that has read the prompt already."""
    for name in required_sections() if names is None else names:
        if "premises" in name.lower():
            return name
    return None


def _premises_head(name=None):
    name = premises_section() if name is None else name
    return section_heading(re.escape(name) if name else r"(?:[A-Za-z]+[ \t]+)?premises")


def missing_sections(text, names=None):
    """The required sections that `text` lacks, in the marker's order. A section is present when a
    `#` or `##` heading line starts with its name (any case, text may follow). `names` is the list
    from `required_sections()`, passed by a caller that judges two texts so the prompt is read once.
    [] when the marker cannot be read. Never raises."""
    try:
        names = required_sections() if names is None else names
        if not names:
            return []
        text = text if isinstance(text, str) else ""
        return [n for n in names if not section_heading(re.escape(n)).search(text)]
    except Exception:
        return []


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
# "Permission to use <Tool> [with <x>] has been denied", "Permission to read|edit|write <path> has
# been denied", "Permission for this action|tool use|command has been|was denied", "was denied by
# the Claude Code auto mode classifier", "Refusing to run it", or a first line that starts
# "denied:" or "refused:". A plain failure ("Exit code 1", ECONNREFUSED, an OS "Permission
# denied") is not one.
_REFUSAL = re.compile(
    r"hook error|(?:doesn['\u2019]t|does not) want to proceed|tool use was rejected"
    r"|permission to use \S+(?: with .*?)? has been denied"
    r"|permission for this (?:action|tool use|command) (?:has been|was) denied"
    r"|permission to (?:read|edit|write) .+? has been denied"
    r"|was denied by the claude code auto mode classifier|refusing to run it"
    r"|^(?:denied|refused):", re.I)


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


def _premise_lines(text, name=None):
    """[(id, kind, line)] of the premise lines in the premises section of `text`, in order, one entry per id (the
    first wins). `line` is the whole line. [] when the section is missing or holds no line. `name` is the
    marker's premises name, when the caller has it; else the prompt is read for it."""
    head = _premises_head(name).search(text)
    if not head:
        return []
    body = text[head.end():]
    end = re.search(r"^#{1,2}[ \t]", body, re.M)
    if end:
        body = body[:end.start()]
    found = {}
    for m in _PREMISE_LINE.finditer(body):
        stop = body.find("\n", m.end())
        found.setdefault(m.group(1), ((m.group(2) or "").strip().lower(), body[m.start():stop if stop >= 0 else len(body)]))
    return [(pid, kind, line) for pid, (kind, line) in found.items()]


def handoff_premises(path):
    """[(id, kind)] of the premise lines in the handoff's premises section, in order,
    one entry per id. [] when the file is unreadable or the section is missing or has no line.
    Reads text only. A kind outside PREMISE_KINDS is kept as written, so the caller lists it."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except (OSError, ValueError):  # ValueError: a byte that is not UTF-8
        return []
    return [(pid, kind) for pid, kind, _line in _premise_lines(text)]


# The parts of a premise line that the checked-stamp rule reads (decision precompact-handoff, item 15). The stamp is
# the line's text from its last `Checked` (or `Re-checked`) word to its end, so a spelling such as `Checked: x` counts.
_STAMP_WORD = re.compile(r"\b(?:Re-?c|C)hecked\b")
_STAMP_LEAD = re.compile(r"^(?:re-?)?checked\b[ \t:]*")
_LINE_SOURCE = re.compile(r"\bSource:[ \t]*(.*)")
# A Source token: a URL, a path (with a slash, or a file name with an extension), a 7+ hex hash with a digit, a
# backticked command, or the slug or number after a record word. Text outside these is no token.
_TOKEN_PATH = re.compile(r"https?://[^\s)`\]>]+|(?<![\w./~-])((?:[\w.~-]+(?:/[\w.~-]+)+)|(?:[\w-]+(?:\.[\w-]+)*\.[A-Za-z][A-Za-z0-9]{1,4}))(?::\d+(?:-\d+)?)?(?![\w/])")
_TOKEN_HASH = re.compile(r"(?<![\w./-])[0-9a-f]{7,40}(?![\w-])")
_TOKEN_TICKS = re.compile(r"`([^`\n]+)`")
_TOKEN_RECORD = re.compile(r"\b(?:decision|debt|record|step|rule|lane|roadmap step|item)[ \t]+`?([a-z][a-z0-9]*(?:-[a-z0-9]+)+)\b"
                           r"|\b(?:PR|pull request|issue)[ \t]+#?(\d+)\b", re.I)
# A shell call that reads backs a premise; one that writes does not.
SHELL_TOOLS = ("Bash", "PowerShell")
READ_TOOLS = ("Read", "Grep", "Glob", "WebFetch", "WebSearch") + SHELL_TOOLS
READ_MCP_WORDS = ("get", "list", "read", "query", "search", "view")
# A whole name segment that makes an MCP tool a writer or a sender, whatever else its name says.
WRITE_MCP_WORDS = ("write", "create", "update", "delete", "send", "set", "post", "add", "remove", "merge", "push",
                   "resolve", "submit", "edit", "put", "patch", "run", "trigger", "reply", "comment", "fork")
GIT_WRITES = ("commit", "push", "add", "tag", "merge", "rebase", "reset", "restore", "checkout", "switch", "stash",
              "cherry-pick", "apply", "am", "rm", "mv", "clean", "pull", "revert", "init", "clone", "config")
SHELL_WRITES = ("rm", "mv", "cp", "touch", "mkdir", "tee", "chmod", "ln", "install", "truncate", "dd")


def source_tokens(source):
    """The tokens of a premise's Source text, in order, each once. [] when it holds none: then any one read backs it."""
    found = [m.group(1).strip() for m in _TOKEN_TICKS.finditer(source)]
    for m in _TOKEN_PATH.finditer(source):
        token = (m.group(1) or m.group(0)).rstrip(".,;")
        for lead in ("./", "~/"):
            token = token[len(lead):] if token.startswith(lead) else token
        found.append(token)
    found += [m.group(0) for m in _TOKEN_HASH.finditer(source) if any(c.isdigit() for c in m.group(0))]
    found += [m.group(1) or m.group(2) for m in _TOKEN_RECORD.finditer(source)]
    return [t for t in dict.fromkeys(found) if t]


def premise_stamps(text, name=None):
    """{id: (kind, source, stamp)} of the premise lines in `text`. `stamp` is the line's text from its last `Checked`
    or `Re-checked` word to its end, lowercased, spaces folded, a closing period dropped, or None when the line has
    none. `source` is the text after `Source:` up to the stamp, minus a closing period, or "" when the line has none.
    `name` as in _premise_lines."""
    stamps = {}
    for pid, kind, line in _premise_lines(text if isinstance(text, str) else "", name):
        words = list(_STAMP_WORD.finditer(line))
        at = words[-1].start() if words else len(line)
        stamp = " ".join(line[at:].lower().split()).rstrip(" .") if words else None
        source = _LINE_SOURCE.search(line[:at])
        stamps[pid] = (kind, source.group(1).strip().rstrip(".").strip() if source else "", stamp)
    return stamps


def _stamp_value(stamp):
    """What a stamp says after its `Checked` word, or "" when it says nothing (or `stamp` is None)."""
    return _STAMP_LEAD.sub("", stamp, count=1) if stamp else ""


def stamp_changes(before, after, name=None):
    """[(id, tokens)] of the premises of `after` whose stamp, spelling included, is new or differs from `before`'s, and
    that need evidence. A stamp with no value counts as absent. A stamp present before and absent after is a change.
    A premise whose kind in `before` is a `ruling` needs none, whatever the write relabels it to; a line new in `after`
    is judged by its own kind. `Checked never` needs none. `name` is the marker's premises name, when the caller has it."""
    old = premise_stamps(before, name)
    need = []
    for pid, (kind, source, stamp) in premise_stamps(after, name).items():
        was = old[pid][2] if pid in old else None
        if not _stamp_value(stamp):
            stamp = None
        if not _stamp_value(was):
            was = None
        if (old[pid][0] if pid in old else kind) == PREMISE_KINDS[0] or stamp == was or _stamp_value(stamp) == "never":
            continue
        need.append((pid, source_tokens(source)))
    return need


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _is_read(name):
    """True for a tool that reads: a read tool, a shell, or an MCP tool with a whole name segment of get, list, read,
    query, search or view and none of a write or send (`pull_request_review_write`, `send_message`, `resolve_review_thread`)."""
    if not isinstance(name, str):
        return False
    if not name.startswith("mcp__"):
        return name in READ_TOOLS
    parts = set(re.split(r"[^a-z0-9]+", name.rsplit("__", 1)[-1].lower()))
    return bool(parts & set(READ_MCP_WORDS)) and not parts & set(WRITE_MCP_WORDS)


def _shell_reads(command):
    """False when a shell command line changes something: a git call that writes, a write command, `sed -i`, or a
    redirect onto a file. A bandaid, not a parser: it reads segments and tokens with guard_core's splitters, and an
    unparsable segment counts as a read, the same stance as that module."""
    import guard_core
    if not isinstance(command, str):
        return True
    for segment in guard_core.split_segments(command):
        if any(sub in GIT_WRITES for sub, _rest in guard_core.git_calls(segment)):
            return False
        tokens = guard_core.segment_tokens(segment) or []
        at = guard_core.resolve_command(tokens) if tokens else None
        if at is not None:
            word = guard_core.basename(tokens[at])
            if word in SHELL_WRITES or (word == "sed" and any(re.match(r"-[a-z]*i\b|--in-place", t) for t in tokens[at + 1:])):
                return False
        for i, token in enumerate(tokens):
            m = re.match(r"^\d?>>?(.*)$", token)
            target = (m.group(1) or (tokens[i + 1] if i + 1 < len(tokens) else "")) if m else "&"
            if m and not target.startswith("&") and target != "/dev/null":
                return False
    return True


def _same_path(a, b):
    norm = lambda p: os.path.normcase(os.path.normpath(os.path.expanduser(p)))
    return norm(a) == norm(b)


def backed_premises(transcript, need, handoff):
    """The ids of `need` ([(id, tokens)] from stamp_changes) that the session's own transcript backs, or None when the
    transcript cannot be read or `need` is not a list of (id, tokens) pairs (the caller fails open). Evidence is a
    read-type tool_use (`_is_read`; a shell call must not write) of the main session after the newest `compact_boundary` record (none: the whole transcript) whose input
    holds a token of the premise's Source; a premise with no token is backed by any one such call. Not evidence: a
    record of an agent (isSidechain, or an agent_id), a Write or Edit, a send (`_transcript.SEND_TOOLS`), a Read of
    `handoff` itself, and a call whose result failed (`_transcript.failed_tool_use_ids`, over the whole transcript).
    One open of the transcript."""
    if not isinstance(need, (list, tuple)) or not all(
            isinstance(pair, (list, tuple)) and len(pair) == 2 and isinstance(pair[0], str)
            and isinstance(pair[1], (list, tuple)) for pair in need):
        return None
    lint = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lint")
    if lint not in sys.path:
        sys.path.insert(0, lint)
    try:
        import _transcript
        records = _transcript.read_transcript(transcript)
    except (OSError, ValueError):
        return None
    failed = _transcript.failed_tool_use_ids(records)
    backed = set()
    for rec in records:
        if rec.get("isSidechain") or rec.get("agent_id"):
            continue
        if rec.get("type") == "system" and rec.get("subtype") == "compact_boundary":
            backed.clear()
            continue
        for use in _transcript.tool_uses(rec):
            name, given = use.get("name"), use.get("input")
            if not isinstance(given, dict) or use.get("id") in failed or name in _transcript.SEND_TOOLS \
                    or not _is_read(name):
                continue
            if name in SHELL_TOOLS and not _shell_reads(given.get("command")):
                continue
            if name == "Read" and isinstance(given.get("file_path"), str) and _same_path(given["file_path"], handoff):
                continue
            text = "\n".join(_strings(given))
            for pid, tokens in need:
                if pid not in backed and (not tokens or any(t in text for t in tokens)):
                    backed.add(pid)
    return {pid for pid, _tokens in need if pid in backed}


def premise_note(path, everyone):
    """The reorient text on premises; "" when the handoff file does not exist. everyone: list
    every premise, since the handoff came from another session. Else list all but the strongest
    kind, PREMISE_KINDS[0].
    A kind outside PREMISE_KINDS is not a ruling, so it is listed."""
    if not os.path.isfile(path):
        return ""
    prem = handoff_premises(path)
    if not prem:
        note = " The handoff has no %s section. Add it per step 4." % (premises_section() or "premises")
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
    the top. For room <= 0, only room - NUDGE_MARGIN, whatever its sign. After the top comes the late
    checkpoint, room - NUDGE_LATE_MARGIN, when it sits NUDGE_LATE_GAP or more past the top (room 295,931:
    245,931 and 275,931). The top alone left a cloud session 84k to 108k tokens short of the live line."""
    margin = min(NUDGE_MARGIN, room // 2) if room > 0 else NUDGE_MARGIN
    top = room - margin
    late = [room - NUDGE_LATE_MARGIN] if room > 0 and margin - NUDGE_LATE_MARGIN >= NUDGE_LATE_GAP else []
    if top <= NUDGE_FLOOR:
        return [top] + late
    cps = [NUDGE_FLOOR]
    while cps[-1] + NUDGE_STEP < top:
        cps.append(cps[-1] + NUDGE_STEP)
    while cps and top - cps[-1] < NUDGE_STEP // 2:
        cps.pop()
    return cps + [top] + late


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


# JS parseFloat's leading number: "80%" is 80. Infinity is out of range anyway, so it is not read.
_LEADING_FLOAT = re.compile(r"\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)")


def _pct_override():
    """CLAUDE_AUTOCOMPACT_PCT_OVERRIDE as a number in (0, 100], else None. Claude Code 2.1.316
    applies it in every session and window, and parses it with parseFloat."""
    m = _LEADING_FLOAT.match(os.environ.get("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE", ""))
    if not m:
        return None
    p = float(m.group(1))
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
    pct = _pct_override()
    if pct is not None:
        threshold = min(threshold, min(math.floor(eff * pct / 100), cap))
    return int(threshold)


_WINDOW_SUFFIX = re.compile(r"(\d+(?:\.\d+)?)([km])", re.I)
WINDOW_MIN = 100_000
WINDOW_MAX = 1_000_000


def window_limit(model=None):
    """The session's auto-compact window: env CLAUDE_CODE_AUTO_COMPACT_WINDOW, then
    modelSettings.<model>.autoCompactWindow, then top-level autoCompactWindow in
    <config dir>/settings.json, then DEFAULT_WINDOW. As in Claude Code 2.1.316, only the env var
    takes a k/m suffix, and a positive env value is clamped to WINDOW_MIN..WINDOW_MAX. A settings
    value counts only as an int in that range. A bad value falls to the next tier."""
    # shortcut: the model's own window is not read, so a model window smaller than every
    # tier makes nudges late and can skip the first one. Upgrade when hook input carries it.
    def parse(v):
        """A settings value: an int in WINDOW_MIN..WINDOW_MAX, else None."""
        if isinstance(v, int) and not isinstance(v, bool) and WINDOW_MIN <= v <= WINDOW_MAX:
            return v
        return None
    env = os.environ.get("CLAUDE_CODE_AUTO_COMPACT_WINDOW", "").strip()
    if re.fullmatch(r"[+-]?\d+", env):  # Python's int() also takes "1_000"
        v = int(env)
    else:
        m = _WINDOW_SUFFIX.fullmatch(env)
        v = int(round(float(m.group(1)) * (1000 if m.group(2).lower() == "k" else 1_000_000))) \
            if m else 0
    if v > 0:
        return max(WINDOW_MIN, min(v, WINDOW_MAX))
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


def _checkpoint_facts(payload, state):
    """(size, messages) when the context size passed a new checkpoint, else None. Sets state["bucket"]
    when the transcript gave a size."""
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
        return None
    # Proxy (record hook-inputs-carry-token-counts): the first turn is mostly overhead.
    messages = max(size - overhead, 0)
    if messages == 0:
        bucket = -1  # nothing to hand off, even when the room left is zero or negative
    else:
        bucket = sum(1 for c in checkpoints(compact_threshold(window_limit(model)) - overhead)
                     if messages >= c) - 1
    try:
        stored = int(state["bucket"])
    except Exception:
        stored = -1
    state["bucket"] = bucket
    return (size, messages) if bucket > stored else None


def _unflagged_missing(session_id, state):
    """The required sections the session's handoff lacks, when it exists and this mtime was not flagged
    yet (state["sections_mtime"], set here), else []."""
    path = handoff_path(session_id)
    try:
        mtime = os.stat(path).st_mtime_ns
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except (OSError, ValueError):  # no handoff, or a byte that is not UTF-8
        return []
    missing = missing_sections(text)
    if not missing or state.get("sections_mtime") == mtime:
        return []
    state["sections_mtime"] = mtime
    return missing


def run_nudge(payload):
    try:
        record_dir(payload.get("session_id", ""), payload.get("cwd"))
    except Exception as e:
        sys.stderr.write("precompact_handoff: could not record the dir: %s\n" % e)
    if payload.get("stop_hook_active"):
        return 0
    session_id = payload.get("session_id", "")
    path = os.path.join(config_dir(), "state", "handoff", "%s.nudge.json" % session_id)
    state = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            state = loaded
    except Exception:
        pass
    before = dict(state)
    facts, missing = None, []
    try:
        facts = _checkpoint_facts(payload, state)
    except Exception as e:
        sys.stderr.write("precompact_handoff: nudge error: %s\n" % e)
    if not facts:  # a checkpoint block already says to rewrite the handoff; the sections wait for the next Stop
        try:
            missing = _unflagged_missing(session_id, state)
        except Exception as e:
            sys.stderr.write("precompact_handoff: nudge error: %s\n" % e)
    try:
        if state != before:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(state, f)
        if facts:
            size, messages = facts
            ensure_handoff_dir(session_id)
            reason = ("Context is about %dk tokens, messages about %dk. Rewrite your handoff at %s now, the "
                      "whole file; never append. Follow step 4 of %s for its sections and their order. "
                      "Then continue. (decision precompact-handoff)"
                      % (size // 1000, messages // 1000, handoff_path(session_id), prompt_path()))
        elif missing:
            reason = ("Your handoff at %s lacks these sections: %s. Rewrite the whole file with each under "
                      "its own ## heading, per step 4 of %s. (decision precompact-handoff)"
                      % (handoff_path(session_id), ", ".join(missing), prompt_path()))
        else:
            reason = ""
        if reason:
            print(json.dumps({"decision": "block", "reason": reason}))
    except Exception as e:
        sys.stderr.write("precompact_handoff: nudge error: %s\n" % e)
    return 0


# --- Claude Code compaction check (step cc-update-behavior-diff) -------------------------
# Claude Code is minified: its identifiers change on every build. Each fact below is read from
# an anchor that survives a rename: a setting key, an env var name, a flag name, a property
# name. A minified identifier is only followed to its `IDENT=<number>` declaration. Raw byte
# search steps over comment openers, template literals and quotes without parsing them.
CC_BASELINE = os.path.join("hooks", "cc_compaction_baseline.json")
CC_CACHE_NAME = "cc-behavior.json"
CC_MAX_LINE = 240
CC_CACHE_PATHS = 8
CC_SETTINGS_KEYS = ("idleCompaction", "autoCompactWindow", "autoCompactEnabled",
                    "precomputeCompactionEnabled")
CC_ENV_VARS = ("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE", "CLAUDE_CODE_AUTO_COMPACT_WINDOW")
CC_TAIL = (". Name this under Input Needed in your report. Read: decision precompact-handoff, "
           "item 12; step cc-update-behavior-diff.")
_CC_IDENT = rb"[A-Za-z_$][\w$]*"
_CC_NUMBER = re.compile(rb"(\d+(?:\.\d+)?|\.\d+)(?=[;,)])")
_CC_WORD = frozenset(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_$")


def _cc_hits(blob, needle):
    """Offsets of each occurrence of `needle`, by plain byte search."""
    pos = blob.find(needle)
    while pos >= 0:
        yield pos
        pos = blob.find(needle, pos + 1)


def _cc_same(values):
    """The one value all sightings agree on, else "unknown": a split reading is no fact."""
    values = list(values)
    return values[0] if values and all(v == values[0] for v in values) else "unknown"


_CC_DECLARED = re.compile(rb"(?:^|[^\w$.])(?:var|let|const)\s+$")


def _cc_assigned(blob, ident, anchor):
    """The number `ident` is declared with, `var|let|const IDENT=<number>` or `,IDENT=<number>`,
    read from its own declaration: the nearest one before `anchor`, else the nearest after it
    (a var can be hoisted). Minified names repeat across scopes, and a bare `IDENT=7` is an
    assignment, not a declaration. Both are skipped. "unknown" when no declaration is found."""
    head = ident + b"="
    before = after = None
    for pos in _cc_hits(blob, head):
        lead = blob[max(0, pos - 16):pos]
        m = _CC_NUMBER.match(blob, pos + len(head))
        if not m or not (lead.endswith(b",") or _CC_DECLARED.search(lead)):
            continue
        value = float(m.group(1)) if b"." in m.group(1) else int(m.group(1))
        if pos < anchor:
            before = value  # the last one seen before the anchor is the nearest
        elif after is None:
            after = value
            break
    return before if before is not None else after if after is not None else "unknown"


def _cc_default(blob, key):
    """The default of a setting read as `("key",!0)` (true) or `("key",!1)` (false)."""
    head = b'"%s",' % key
    seen = [blob[pos + len(head):pos + len(head) + 3] for pos in _cc_hits(blob, head)]
    return _cc_same(s == b"!0)" for s in seen if s in (b"!0)", b"!1)"))


def _cc_ident_args(blob, head):
    """(offset, identifier) for each `<head>IDENT)`, in file order."""
    pattern = re.compile(re.escape(head) + rb"(%s)\)" % _CC_IDENT)
    return [(pos, m.group(1)) for pos, m in ((pos, pattern.match(blob, pos))
                                             for pos in _cc_hits(blob, head)) if m]


def cc_facts(blob):
    """Fact name -> value read from a Claude Code binary, or "unknown" when an anchor is missing
    or its value can not be resolved. blocking_margin and output_reserve are left out when their
    anchors are missing, and cc_version_check compares only the facts the baseline holds."""
    facts = {}
    versions = []
    for pos in _cc_hits(blob, b'VERSION:"'):
        m = re.compile(rb'VERSION:"(\d+\.\d+\.\d+)"').match(blob, pos)
        if m and (pos == 0 or blob[pos - 1] not in _CC_WORD):  # not SEMVER_SPEC_VERSION
            versions.append(m.group(1).decode("ascii"))
    facts["version"] = _cc_same(versions)
    facts["idle_compaction_default"] = _cc_default(blob, b"idleCompaction")
    facts["auto_compact_enabled_default"] = _cc_default(blob, b"autoCompactEnabled")
    # A schema entry is `key:()=>NAME`. `key:()=>e.options.key` is a state object, not the schema.
    schema = []
    for key in CC_SETTINGS_KEYS:
        head = key.encode("ascii") + b":()=>"
        entry = re.compile(rb"%s(?![\w$.])" % _CC_IDENT)
        if any((pos == 0 or blob[pos - 1] not in _CC_WORD) and entry.match(blob, pos + len(head))
               for pos in _cc_hits(blob, head)):
            schema.append(key)
    facts["settings_keys"] = sorted(schema) or "unknown"
    # An env var is read in code as `process.env.NAME` or `ident.NAME`, not as a bare string.
    read = []
    for name in CC_ENV_VARS:
        head = b"." + name.encode("ascii")
        if any(pos and blob[pos - 1] in _CC_WORD
               and not (blob[pos + len(head):pos + len(head) + 1] or b"\0")[0] in _CC_WORD
               for pos in _cc_hits(blob, head)):
            read.append(name)
    facts["env_vars"] = sorted(read) or "unknown"
    facts["summary_fraction_default"] = _cc_same(
        _cc_assigned(blob, ident, pos)
        for pos, ident in _cc_ident_args(blob, b'"tengu_amber_rokovoko",'))
    # Optional. output_reserve: the identifier that follows `.maxOutputTokens,` and ends in `)`.
    # blocking_margin: the /context buffer is the identifier subtracted in the last `)-IDENT:void 0,`
    # within 2500 bytes before the "autocompact_buffer" id.
    reserves = [_cc_assigned(blob, ident, pos)
                for pos, ident in _cc_ident_args(blob, b".maxOutputTokens,")]
    margins = []
    for pos in _cc_hits(blob, b'id:"autocompact_buffer"'):
        subtracted = re.findall(rb"\)-(%s):void 0," % _CC_IDENT, blob[max(0, pos - 2500):pos])
        if subtracted:
            margins.append(_cc_assigned(blob, subtracted[-1], pos))
    for name, values in (("blocking_margin", margins), ("output_reserve", reserves)):
        value = _cc_same(values)
        if value != "unknown":
            facts[name] = value
    return facts


def _cc_show(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "+".join(value)
    return str(value)


def _cc_line(head, changes):
    """One line of at most CC_MAX_LINE characters. Each change is "name old -> new"."""
    shown = []
    for i, change in enumerate(changes):
        if shown and len(head + "; ".join(shown + [change, "+%d more" % len(changes)])
                         + CC_TAIL) > CC_MAX_LINE:
            shown.append("+%d more" % (len(changes) - i))
            break
        shown.append(change)
    return (head + "; ".join(shown) + CC_TAIL)[:CC_MAX_LINE]


def cc_version_check(env=None, config=None):
    """The one line to print about the installed Claude Code, or "". It starts no process. The
    binary at env CLAUDE_CODE_EXECPATH is read once per new binary (path, size, mtime). When that
    variable is missing or its file can not be read, one `claude` lookup on env PATH (never
    os.environ), followed to its real file, stands in for it. The cache,
    <config dir>/cc-behavior.json, holds one entry per binary path (at most CC_CACHE_PATHS), so two
    apps with two paths do not evict each other. A fact that differs from the baseline
    (CC_BASELINE) prints one line. A baseline that can not be read raises before anything is
    written, so the next start reads the binary again. A binary that can not be read or found prints one
    "unknown" line per version. With neither CLAUDE_CODE_EXECPATH nor AI_AGENT set, this is no
    Claude Code session: "". The `version` fact alone is not a change; "unknown" on one side
    only is."""
    env = os.environ if env is None else env
    config = config or config_dir()
    cache_path = os.path.join(config, CC_CACHE_NAME)
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)
        if not isinstance(cache, dict):
            cache = {}
    except (OSError, ValueError):
        cache = {}
    entries = cache.get("paths") if isinstance(cache.get("paths"), dict) else {}

    def save(data):
        os.makedirs(config, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    path = env.get("CLAUDE_CODE_EXECPATH")
    agent = re.search(r"claude-code_(\d+)-(\d+)-(\d+)", env.get("AI_AGENT") or "")
    if not path and not agent:
        return ""
    shown = ".".join(agent.groups()) if agent else "unknown"

    def read_binary(candidate):
        """(blob, key) for a binary not yet in the cache, ("", None) for one that is, or None."""
        try:
            st = os.stat(candidate)
            key = [candidate, st.st_size, st.st_mtime_ns]
            if isinstance(entries.get(candidate), dict) and entries[candidate].get("key") == key:
                return "", None
            with open(candidate, "rb") as f:
                return f.read(), key
        except OSError:
            return None

    found = read_binary(path) if path else None
    on_path = None
    if found is None:
        # Only the injected env's PATH: os.environ would answer for the hook's own session.
        search_path = env.get("PATH")
        on_path = shutil.which("claude", path=search_path) if search_path else None
        if on_path:
            path = os.path.realpath(on_path)  # the cache keys on the file, not on the link
            found = read_binary(path)
    if found is not None and found[1] is None:
        return ""
    if found is None:
        if cache.get("unknown_for") == shown:
            return ""
        save({"paths": entries, "unknown_for": shown})
        return ("Claude Code %s compaction facts are unknown: CLAUDE_CODE_EXECPATH %s and %s%s" % (
            shown, "can not be read" if env.get("CLAUDE_CODE_EXECPATH") else "is not set",
            "the claude on PATH can not be read" if on_path else "no claude on PATH",
            CC_TAIL))[:CC_MAX_LINE]
    blob, key = found
    facts = cc_facts(blob)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", CC_BASELINE),
              encoding="utf-8") as f:
        base = json.load(f)
    changes = []
    for name, old in base["facts"].items():
        new = facts.get(name, "unknown")
        if name != "version" and old != new:
            changes.append("%s %s -> %s" % (name, _cc_show(old), _cc_show(new)))
    entries.pop(path, None)  # a re-seen path moves to the newest place
    entries[path] = {"key": key, "version": facts["version"], "facts": facts}
    for old_path in list(entries)[:-CC_CACHE_PATHS]:
        del entries[old_path]
    save({"paths": entries})
    if not changes:
        return ""
    return _cc_line("Claude Code %s -> %s changed compaction facts: "
                    % (base["version"], facts["version"]), changes)
# --- end of the Claude Code compaction check ---------------------------------------------


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
