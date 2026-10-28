#!/usr/bin/env python3
"""UserPromptSubmit and SubagentStart hook: tell the session the time in US Central (America/Chicago). On UserPromptSubmit it also saves each owner message to the session's feedback inbox.

Modes:
- UserPromptSubmit: Tells the session the time in US Central, and saves the owner's message to the
  session's inbox file (decision owner-feedback-inbox).
  A prompt whose first word is `override` also grants a one-act owner override, and the rest is the
  reason, logged to guard.log. `override <n>[m|h]` and `override off` mean that only as the whole prompt
  (decision owner-override; hooks/override.py). It prints one more line.
- --agent: At SubagentStart, gives the agent the time in US Central as context.

Sessions speak times in US Central, 24-hour clock (decision local-time-central). Prints one line, for example "Local time: 2026-10-13 21:40 CDT (UTC-05:00)".
Plain stdout is context for UserPromptSubmit. SubagentStart takes context only as JSON, so
`--agent` prints `hookSpecificOutput` with `additionalContext` (Claude Code hooks reference).
The US rule is coded here, not read from zoneinfo: Windows Python often has no tz database.
Advisory, fail-open: any error prints one stderr line and exits 0.

This hook is also the owner feedback inbox's capture (decision owner-feedback-inbox). Every
UserPromptSubmit prompt is appended verbatim to <config dir>/handoffs/<session_id>.inbox.md, with its
Central time, in a backtick fence longer than any backtick run in the text. No word opens or closes
capture. A notice (a prompt that starts with a shared_names.MACHINE_TAGS tag) is never saved.
`--agent` never reads stdin and never saves. The Stop guard that reads the inbox, and decides which
messages need items, is feedback_guard.py. LOCAL_TIME_NOW (ISO-8601 with an offset) replaces the
clock; tests set it.
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone


CST = timedelta(hours=-6)


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


def line(clock=clock):
    now = clock().astimezone(timezone.utc)
    # US rule since 2007: DST runs from 02:00 CST on the 2nd Sunday of March (08:00 UTC)
    # to 02:00 CDT on the 1st Sunday of November (07:00 UTC).
    start = nth_sunday(now.year, 3, 2).replace(hour=8)
    end = nth_sunday(now.year, 11, 1).replace(hour=7)
    dst = start <= now < end
    local = now + CST + (timedelta(hours=1) if dst else timedelta())
    name, off = ("CDT", "UTC-05:00") if dst else ("CST", "UTC-06:00")
    return "Local time: %s %s (%s)" % (local.strftime("%Y-%m-%d %H:%M"), name, off)


def central_hhmm(at):
    """`HH:MM CDT` (or CST) for an instant: the time line's own clock, cut to the end of an override."""
    return " ".join(line(lambda: at).split()[3:5])


def override_line(result):
    """The context line for a grant() result: names the override and when it ends, Central time."""
    kind, until = result[:2]
    if kind == "off":
        return "Override: ended."
    if kind == "opus-off":
        return "Opus override: ended."
    if kind == "opus":
        who = "%s spawns" % result[2] if result[2] else "spawns"
        return "Opus override: Opus %s go through without the ask until %s." % (who, central_hhmm(until))
    if kind == "once":
        return "Override: the next refused act goes through, once. It ends at %s if unused." % central_hhmm(until)
    return "Override: every refused act goes through until %s." % central_hhmm(until)


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
    # JSON can carry a lone surrogate, which UTF-8 cannot encode: save U+FFFD in its place.
    prompt = re.sub("[\ud800-\udfff]", "\ufffd", prompt)
    try:
        fence = "`" * max([3] + [len(r) + 1 for r in re.findall(r"`+", prompt)])
        os.makedirs(os.path.dirname(paths[0]), exist_ok=True)
        with open(paths[0], "ab") as f:  # bytes: "\n" stays "\n" on Windows, and the text stays verbatim
            f.write(("### %s\n%s\n%s\n%s\n" % (stamp, fence, prompt, fence)).encode("utf-8"))
    except (OSError, ValueError) as e:  # stderr never reaches the owner or the session: use stdout
        print("Feedback capture: this message was not saved (%s). Jot it by hand into the handoff." % e)


def grant_override(raw, at):
    """Owner prompt `override`, `override <reason>`, `override <n>[m|h]`, `override off` or the Opus word
    (`opus <n>[m|h]`, `opus <role> <n>[m|h]`, `opus off`; decision owner-override): grants or ends
    the session's override and prints one line. Any failure is one stderr line, no override."""
    try:
        hook = json.loads(raw.decode("utf-8"))
        import override
        result = override.grant(hook.get("session_id"), hook.get("prompt"), at)
        if result:
            print(override_line(result))
    except (ValueError, AttributeError):
        pass  # stdin is no hook payload: capture() reports that once
    except Exception as e:  # advisory: the time line and capture still run
        print("local_time: override: %s" % e, file=sys.stderr)


OLD_FLAG_ENDS = "2026-11-09"


def main(argv):
    try:
        now = clock()
        stamp = text = line(lambda: now)
        # `--subagent` is the flag's old name, kept until OLD_FLAG_ENDS for a session that read its
        # hook list before the rename. Delete it on that day.
        agent = "--agent" in argv or "--subagent" in argv
        if agent:
            text = json.dumps({"hookSpecificOutput": {"hookEventName": "SubagentStart",
                                                      "additionalContext": text}})
        print(text)
        if not agent:
            raw = sys.stdin.buffer.read()
            grant_override(raw, now)
            capture(raw, stamp[len("Local time: "):])
    except Exception as e:  # advisory hook: fail open; one stderr line shows in --debug
        print("local_time: %s" % e, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
