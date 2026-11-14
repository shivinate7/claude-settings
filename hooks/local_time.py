#!/usr/bin/env python3
"""UserPromptSubmit, SubagentStart and PostToolUse hook: tell the session the time in US Central (America/Chicago). On UserPromptSubmit it also saves each owner message to the session's feedback inbox. After an ArtifactData read of `answers` it saves a waiting-page note to the same inbox.

Modes:
- UserPromptSubmit: Tells the session the time in US Central, and saves the owner's message to the
  session's inbox file (decision owner-feedback-inbox).
  A prompt whose first word is `override` also grants a one-act owner override, and the rest is the
  reason, logged to guard.log. `override` plus a length is timed, with no model call: `15m`, `2 hours` or `4h`, with
  any words after it, or a bare `15` as the whole rest. `override 15 please` is a reason, unless the model call below
  says yes: then 15 is minutes. `override off` means that only as the whole prompt. A grant prints one receipt line
  (override_line).
  A plain typed ask that holds the word `override` may grant one too, after a model call
  (decision owner-override; hooks/override.py). A grant by that ask prints its receipt line the same way.
- --agent: At SubagentStart, gives the agent the time in US Central as context.
- --page-note: After an ArtifactData read of one waiting-page answer, saves the owner's note on it to the session's inbox, like a chat message (decision owner-feedback-inbox). It prints no time line.

Sessions speak times in US Central, 24-hour clock (decision local-time-central). Prints one line, for example "Local time: YYYY-MM-DD 21:40 CDT (UTC-05:00) Later times: run ~/.claude/bin/now-central, never from memory."
The pointer follows the time line on the same line. The inbox stamp and `line()` carry no pointer. The helper bin/now-central prints later times from this module's clock.
Plain stdout is context for UserPromptSubmit. SubagentStart takes context only as JSON, so
`--agent` prints `hookSpecificOutput` with `additionalContext` (Claude Code hooks reference).
The US rule is coded here, not read from zoneinfo: Windows Python often has no tz database.
Advisory, fail-open: any error prints one stderr line and exits 0.

This hook is also the owner feedback inbox's capture (decision owner-feedback-inbox). Every
UserPromptSubmit prompt is appended verbatim to <config dir>/handoffs/<session_id>.inbox.md, with its
Central time, in a backtick fence longer than any backtick run in the text. No word opens or closes
capture. A notice or an agent hand-back (a prompt that starts with a shared_names.MACHINE_TAGS
entry) is never saved.
After a save, capture writes `<session_id>.inbox.repo` once, when the payload cwd is inside a git
repo (a `.git` found by walking up; no process starts): the real path of the cwd. The Stop guard reads
it to find other sessions' inboxes of the same repo (decision owner-feedback-inbox, "Repeats"). Cost:
one small file per session.
`--agent` never reads stdin and never saves. The Stop guard that reads the inbox, and decides which
messages need items, is feedback_guard.py. LOCAL_TIME_NOW (ISO-8601 with an offset) replaces the
clock; tests set it.

`--page-note` is the waiting page's capture (PostToolUse, matcher ArtifactData). It acts only on a
`get` of collection `answers`: the routing session's re-read of `answers/<id>`, just before it routes
the answer, so an undone or withdrawn answer is never saved. A `list`, `query`, write or other tool
saves nothing. It collects every string in `tool_response` (a str, content blocks, nested dicts). A
line that loads as a JSON object with a dict `data` is a document. Only one-line JSON documents in
text are read: a dict-shaped or pretty-printed document saves nothing. A document with `data.parked` true (a
parked-line act, `answers/park.<id>`) saves nothing: its note is the entry's own text, not the owner's words. Each other
document whose `data.note` is
a string, non-empty after strip and not `accepted pick`, becomes one inbox block, stamped with the
answer's `data.at` in Central (the clock when `at` does not parse), with the text
`Waiting page note, item <n> (<item>): <note>`. The label joins the note's first line, so it adds no
line. A read with `out_dir` returns file paths only, so it saves nothing. Each saved note leaves a key
`<url>|<doc_id>|<at>` in `<session_id>.inbox.pagenotes`, and a key already there saves nothing. A failed
save prints a PostToolUse `additionalContext` saying the note was not saved. Cost: one process start
per ArtifactData call. Files are written only when a read of `answers` returns a new note: the inbox
and the pagenotes file.
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone


CST = timedelta(hours=-6)
# The inbox heading and stamp, written here and read by feedback_guard.py.
HEADING_PREFIX = "### "
STAMP_FORMAT = "%Y-%m-%d %H:%M"
STAMP_ZONES = {"CDT": "UTC-05:00", "CST": "UTC-06:00"}  # zone name -> offset text
# Matches a stamp; groups 1 and 2 are its hour and minute. It mirrors STAMP_FORMAT.
STAMP_PATTERN = r"\d{4}-\d{2}-\d{2} (\d{2}):(\d{2}) (?:%s) \((?:%s)\)" % (
    "|".join(STAMP_ZONES), "|".join(re.escape(o) for o in STAMP_ZONES.values()))


def nth_sunday(year, month, n):
    d = datetime(year, month, 1, tzinfo=timezone.utc)
    d += timedelta(days=(6 - d.weekday()) % 7 + 7 * (n - 1))
    return d


def clock():
    """The hook's clock: LOCAL_TIME_NOW (ISO-8601 with an offset) when set, else the real time."""
    try:
        at = datetime.fromisoformat(os.environ.get("LOCAL_TIME_NOW", ""))
        return at if at.tzinfo else at.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def central_parts(at):
    """(local time, zone name) in US Central for an instant: the one home of the DST rule below."""
    now = at.astimezone(timezone.utc)
    # US rule since 2007: DST runs from 02:00 CST on the 2nd Sunday of March (08:00 UTC)
    # to 02:00 CDT on the 1st Sunday of November (07:00 UTC).
    start = nth_sunday(now.year, 3, 2).replace(hour=8)
    end = nth_sunday(now.year, 11, 1).replace(hour=7)
    dst = start <= now < end
    local = now + CST + (timedelta(hours=1) if dst else timedelta())
    return local, "CDT" if dst else "CST"


def line(clock=clock):
    local, name = central_parts(clock())
    return "Local time: %s %s (%s)" % (local.strftime(STAMP_FORMAT), name, STAMP_ZONES[name])


def central_hhmm(at):
    """`HH:MM CDT` (or CST) for an instant: the time line's own clock, cut to the end of an override.
    A display helper that never raises: anything that is not a datetime (or one out of range) gives "", not a guessed time."""
    try:
        return " ".join(line(lambda: at).split()[3:5])
    except (AttributeError, TypeError, ValueError, OverflowError):
        return ""


def central_full(at):
    """`YYYY-MM-DD HH:MM CDT` (or CST) for an instant: the stamp without the offset text."""
    local, name = central_parts(at)
    return "%s %s" % (local.strftime(STAMP_FORMAT), name)


def central_iso(at, seconds=True):
    """`YYYY-MM-DDTHH:MM:SS-05:00` (or -06:00) for an instant: ISO-8601 with the Central offset.
    `seconds=False` drops the seconds, as a refusal's reason prints the time.
    A display helper that never raises: anything that is not a datetime (or one out of range) gives "", not a guessed time."""
    try:
        local, name = central_parts(at)
        return local.strftime("%Y-%m-%dT%H:%M:%S" if seconds else "%Y-%m-%dT%H:%M") + STAMP_ZONES[name][len("UTC"):]
    except (AttributeError, TypeError, ValueError, OverflowError):
        return ""


def override_line(result):
    """The context line for a grant() result, the one receipt of a grant: `Override: one act, ...` or
    `Override: until HH:MM <zone>`, Central time. A lift prints nothing: its receipt is the guard.log line."""
    kind, until = result[:2]
    if kind == "off":
        return "Override: ended."
    if kind == "opus-off":
        return "Opus override: ended."
    if kind == "opus":
        roles = " and ".join(result[2]) if isinstance(result[2], list) else result[2]  # one role, or a list of 2 or more
        who = "%s spawns" % roles if roles else "spawns"
        return "Opus override: the model-cap refusal is lifted for Opus %s until %s." % (who, central_hhmm(until))
    if kind == "once":
        return "Override: one act, ends at %s if unused." % central_hhmm(until)
    return "Override: until %s" % central_hhmm(until)


def inbox_paths(session_id):
    """(inbox, turn state) for a session, or None when the id cannot be a file name. The one home
    of these paths: feedback_guard.py calls it. precompact_handoff owns the handoffs folder."""
    base = _session_base(session_id)
    return None if base is None else (base + ".inbox.md", base + ".inbox.turns")


def _session_base(session_id):
    if not re.fullmatch(r"[\w.-]+", session_id or "") or session_id.startswith("."):
        return None
    import precompact_handoff
    return os.path.join(os.path.dirname(precompact_handoff.handoff_path(session_id)), session_id)


def report_marker_path(session_id):
    """The file report_guard.py writes when it blocks for a missing report, or None. Same folder
    as the inbox files."""
    base = _session_base(session_id)
    return None if base is None else base + ".report-block"


def repo_marker_path(session_id):
    """The sidecar that binds a session's inbox to the repo it worked in, or None. Beside the inbox:
    feedback_guard.py reads it to find other sessions' inboxes of the same repo."""
    base = _session_base(session_id)
    return None if base is None else base + ".inbox.repo"


def repo_root(start):
    """The nearest folder at or above `start` that holds `.git` (a folder, or a file in a linked
    worktree), or None. It starts no process."""
    here = os.path.realpath(start)
    while True:
        if os.path.exists(os.path.join(here, ".git")):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            return None
        here = parent


def bind_repo(session_id, cwd):
    """Writes the session's sidecar, the real path of `cwd`, once, when `cwd` is inside a repo.
    A sidecar that exists is left as it is."""
    marker = repo_marker_path(session_id)
    if marker is None or not isinstance(cwd, str) or not os.path.isdir(cwd) or repo_root(cwd) is None:
        return
    try:
        with open(marker, "xb") as f:
            f.write(os.path.realpath(cwd).encode("utf-8", "replace"))
    except FileExistsError:
        pass


def page_notes_path(session_id):
    """The file of page-note keys already saved for a session, or None. Beside the inbox."""
    base = _session_base(session_id)
    return None if base is None else base + ".inbox.pagenotes"


def save_message(inbox, stamp, text):
    """The one fenced write to the inbox, for a chat prompt and a page note. Returns None when saved,
    else the error text."""
    # JSON can carry a lone surrogate, which UTF-8 cannot encode: save U+FFFD in its place.
    text = re.sub("[\ud800-\udfff]", "\ufffd", text)
    try:
        fence = "`" * max([3] + [len(r) + 1 for r in re.findall(r"`+", text)])
        os.makedirs(os.path.dirname(inbox), exist_ok=True)
        with open(inbox, "ab") as f:  # bytes: "\n" stays "\n" on Windows, and the text stays verbatim
            f.write(("%s%s\n%s\n%s\n%s\n" % (HEADING_PREFIX, stamp, fence, text, fence)).encode("utf-8"))
    except (OSError, ValueError) as e:
        return str(e)
    return None


def not_saved(what, err):
    """The line that tells the session a capture failed. Stderr never reaches the owner or the session."""
    return "Feedback capture: this %s was not saved (%s). Jot it by hand into the handoff." % (what, err)


def capture(raw, stamp):
    """Saves one owner prompt to the inbox. `raw` is the hook's stdin as bytes."""
    hook = json.loads(raw.decode("utf-8"))
    prompt = hook.get("prompt")
    paths = inbox_paths(hook.get("session_id"))
    if paths is None or not isinstance(prompt, str):
        return
    try:
        from shared_names import MACHINE_TAGS  # stdlib only: this hook loads no guard module
    except ImportError:  # missing or stale helper: only the notice check degrades; capture and the grant run on
        MACHINE_TAGS = ()
    if MACHINE_TAGS and prompt.strip().startswith(MACHINE_TAGS):
        return  # a notice is not an owner message
    err = save_message(paths[0], stamp, prompt)
    if err is not None:
        print(not_saved("message", err))
        return
    try:
        bind_repo(hook.get("session_id"), hook.get("cwd"))
    except (OSError, ValueError) as e:  # the message is saved; only the repeat check loses this inbox
        print("local_time: repo sidecar: %s" % e, file=sys.stderr)


def _strings(obj):
    """Every string in a tool_response of any shape: a str, a list, a dict, nested."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _strings(v)


def _documents(response):
    """The (doc_id, data) of each document in a get's text: a line that loads as a JSON object with a
    dict `data`. Banner lines are not documents."""
    for text in _strings(response):
        for ln in text.split("\n"):  # not splitlines(): U+2028 and U+0085 inside a note must not split it
            ln = ln.strip()
            if not ln.startswith("{"):
                continue
            try:
                doc = json.loads(ln)
            except ValueError:
                continue
            if isinstance(doc, dict) and isinstance(doc.get("data"), dict):
                yield doc.get("id"), doc["data"]


def _at_clock(at):
    """The instant of an answer's `at` (ISO-8601, `Z` or an offset), else the hook's clock()."""
    try:
        when = datetime.fromisoformat(at.replace("Z", "+00:00"))
        return when if when.tzinfo else when.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return clock()


def page_note_text(data):
    """The inbox text of one answer's note: a label, then the note on the same line."""
    n, item = data.get("n"), data.get("item")
    parts = []
    if n not in (None, ""):
        parts.append("item %s" % n)
    if item not in (None, ""):
        parts.append("(%s)" % item)
    return "Waiting page note%s: %s" % ((", " + " ".join(parts)) if parts else "", data["note"])


def page_note(raw):
    """PostToolUse on ArtifactData: saves the note of each new answer a `get` of `answers` returned.
    Saves nothing for any other call. Prints a PostToolUse additionalContext JSON when a save fails."""
    hook = json.loads(raw.decode("utf-8"))
    inp = hook.get("tool_input")
    if (hook.get("tool_name") != "ArtifactData" or not isinstance(inp, dict)
            or inp.get("action") != "get" or inp.get("collection") != "answers"):
        return
    paths = inbox_paths(hook.get("session_id"))
    notes = []
    for doc_id, data in _documents(hook.get("tool_response")):
        note = data.get("note")
        if data.get("parked") is True:
            continue  # a parked act's note is the entry's own text, not the owner's words
        if isinstance(note, str) and note.strip() and note.strip() != "accepted pick":
            notes.append((doc_id, data))
    if paths is None or not notes:
        return
    keys_path = page_notes_path(hook.get("session_id"))
    try:
        with open(keys_path, "rb") as f:  # bytes, split on "\n" only: a key may hold U+2028 or "\r"
            seen = set(f.read().decode("utf-8", "replace").split("\n"))
    except OSError:
        seen = set()
    failures = []
    for doc_id, data in notes:
        at = data.get("at")
        key = "%s|%s|%s" % (inp.get("url"), doc_id, at)
        if "\n" in key or key in seen:
            continue
        stamp = line(lambda: _at_clock(at))[len("Local time: "):]
        err = save_message(paths[0], stamp, page_note_text(data))
        if err is not None:
            failures.append(err)
            continue
        seen.add(key)
        try:  # the note is saved: a failed key only risks one repeat
            with open(keys_path, "ab") as f:
                f.write((key + "\n").encode("utf-8", "replace"))
        except OSError as e:
            print("local_time: page note key: %s" % e, file=sys.stderr)
    if failures:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": not_saved("page note", "; ".join(failures))}}))


def grant_override(raw, at):
    """Owner prompt `override`, `override <reason>`, `override <length> [words]`, `override off` or the Opus word
    (`opus <n>[m|h]`, `opus <role> <n>[m|h]`, `opus off`; decision owner-override): grants or ends
    the session's override and prints one line. A prompt no keyword form grants goes to
    override.grant_opus_ask, the plain Opus ask (`send opus judges`): one model call, only for an owner prompt
    that carries the word `opus`, none otherwise. An ask that names no role also reads the owner's earlier typed
    prompts for the roles they name: one more model call, only after a yes and only when such a prompt exists; no
    role named means every role (decision owner-override). A prompt neither grants goes last to
    override.grant_override_ask, the plain override ask (`yes override that`): one model call, only for an owner
    prompt that holds the whole word `override` outside code spans and passes its gates, none otherwise. It also gives
    the result of a first-word `override` prompt that grant() deferred because its rest holds a length. At most one
    judge call per prompt. Those calls are why the settings.json row has "timeout": 30. Any failure is one stderr
    line, no override."""
    try:
        hook = json.loads(raw.decode("utf-8"))
        import override
        result = override.grant(hook.get("session_id"), hook.get("prompt"), at,
                                transcript=hook.get("transcript_path"), source=hook.get("source"))
        if result is None:
            result = override.grant_opus_ask(hook.get("session_id"), hook.get("prompt"), at,
                                             transcript=hook.get("transcript_path"),
                                             source=hook.get("source"))
        if result is None:
            result = override.grant_override_ask(hook.get("session_id"), hook.get("prompt"), at,
                                                 transcript=hook.get("transcript_path"),
                                                 source=hook.get("source"))
        if result:
            print(override_line(result))
    except (ValueError, AttributeError):
        pass  # stdin is no hook payload: capture() reports that once
    except Exception as e:  # advisory: the time line and capture still run
        print("local_time: override: %s" % e, file=sys.stderr)


def mail_lines(raw):
    """Prints the mailbox's open messages after the time line (hooks/mail.py). It starts no process of its own."""
    try:
        hook = json.loads(raw.decode("utf-8"))
    except ValueError:
        return
    try:
        import mail
        lines = mail.turn_start_lines(hook if isinstance(hook, dict) else {}, os.environ)
    except Exception as e:  # an unread mailbox shows as unknown, never as empty
        lines = ["mail unknown: %s" % (" ".join(str(e).split())[:120] or type(e).__name__)]
    for text in lines:
        print(text)


OLD_FLAG_ENDS = "2026-11-09"
# Printed after the time line only, never in the capture stamp. The helper is bin/now-central.
NOW_CENTRAL_POINTER = " Later times: run ~/.claude/bin/now-central, never from memory."


def main(argv):
    try:
        if "--page-note" in argv:
            page_note(sys.stdin.buffer.read())
            return 0
        now = clock()
        stamp = text = line(lambda: now)
        text += NOW_CENTRAL_POINTER
        # `--subagent` is the flag's old name, kept until OLD_FLAG_ENDS for a session that read its
        # hook list before the rename. Delete it on that day.
        agent = "--agent" in argv or "--subagent" in argv
        if agent:
            text = json.dumps({"hookSpecificOutput": {"hookEventName": "SubagentStart",
                                                      "additionalContext": text}})
        print(text)
        if not agent:
            raw = sys.stdin.buffer.read()
            try:
                capture(raw, stamp[len("Local time: "):])
            except Exception as e:  # a capture error never stops the grant
                print("local_time: capture: %s" % e, file=sys.stderr)
            grant_override(raw, now)
            mail_lines(raw)
    except Exception as e:  # advisory hook: fail open; one stderr line shows in --debug
        print("local_time: %s" % e, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
