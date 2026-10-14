#!/usr/bin/env python3
"""UserPromptSubmit and SubagentStart hook: tell the session the time in US Central (America/Chicago). On UserPromptSubmit it also captures owner feedback: a prompt that opens with `fb` is saved to the session's inbox file until a prompt of `fb done`.

Owner ruling 2026-10-13: sessions speak times in US Central, 24-hour clock. See decision
local-time-central. Prints one line, for example "Local time: 2026-10-13 21:40 CDT (UTC-05:00)".
Plain stdout is context for UserPromptSubmit. SubagentStart takes context only as JSON, so
`--subagent` prints `hookSpecificOutput` with `additionalContext` (Claude Code hooks reference).
The US rule is coded here, not read from zoneinfo: Windows Python often has no tz database.
Advisory, fail-open: any error prints one stderr line and exits 0.

This hook is also the owner feedback inbox's capture (decision owner-feedback-inbox). A UserPromptSubmit
prompt whose first word is `fb` or `fb:` opens capture; a prompt that is only `fb done` closes it
(also `fb:`, any whitespace before `done`, any case, trailing punctuation). With capture closed, no
`fb ... done` form opens it; with capture open, `fb - done` is captured as a message.
While open, each prompt is appended verbatim to <config dir>/handoffs/<session_id>.inbox.md in a
backtick fence longer than any backtick run in the text. Open state is the marker file
<session_id>.inbox.open beside it. `--subagent` never reads stdin and never captures. The gate that
reads the inbox is feedback_gate.py.
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

CST = timedelta(hours=-6)


def nth_sunday(year, month, n):
    d = datetime(year, month, 1, tzinfo=timezone.utc)
    d += timedelta(days=(6 - d.weekday()) % 7 + 7 * (n - 1))
    return d


def line(clock=None):
    now = (clock or (lambda: datetime.now(timezone.utc)))().astimezone(timezone.utc)
    # US rule since 2007: DST runs from 02:00 CST on the 2nd Sunday of March (08:00 UTC)
    # to 02:00 CDT on the 1st Sunday of November (07:00 UTC).
    start = nth_sunday(now.year, 3, 2).replace(hour=8)
    end = nth_sunday(now.year, 11, 1).replace(hour=7)
    dst = start <= now < end
    local = now + CST + (timedelta(hours=1) if dst else timedelta())
    name, off = ("CDT", "UTC-05:00") if dst else ("CST", "UTC-06:00")
    return "Local time: %s %s (%s)" % (local.strftime("%Y-%m-%d %H:%M"), name, off)


def inbox_paths(session_id):
    """(inbox, open marker) for a session, or None when the id cannot be a file name. The one home
    of these paths: feedback_gate.py calls it. precompact_handoff owns the handoffs folder."""
    if not re.fullmatch(r"[\w.-]+", session_id or "") or session_id.startswith("."):
        return None
    import precompact_handoff
    base = os.path.join(os.path.dirname(precompact_handoff.handoff_path(session_id)), session_id)
    return base + ".inbox.md", base + ".inbox.open"


def capture(raw, stamp):
    """Opens, closes or appends for one owner prompt. `raw` is the hook's stdin as bytes."""
    hook = json.loads(raw.decode("utf-8"))
    prompt = hook.get("prompt")
    paths = inbox_paths(hook.get("session_id"))
    if paths is None or not isinstance(prompt, str):
        return
    inbox, marker = paths
    is_open = os.path.exists(marker)
    said = prompt.strip()
    # JSON can carry a lone surrogate, which UTF-8 cannot encode: save U+FFFD in its place.
    prompt = re.sub("[\ud800-\udfff]", "�", prompt)
    try:
        if re.fullmatch(r"fb:?\s+done[\W_]*", said, re.I):  # any case, trailing punctuation
            if is_open:
                os.remove(marker)
            return
        if not is_open and ((prompt.split() or [""])[0] not in ("fb", "fb:")
                            or re.fullmatch(r"fb[\W_]+done[\W_]*", said, re.I)):
            return  # closed: only an opener opens, and never a near-miss of `fb done`
        fence = "`" * max([3] + [len(r) + 1 for r in re.findall(r"`+", prompt)])
        os.makedirs(os.path.dirname(inbox), exist_ok=True)
        with open(inbox, "ab") as f:  # bytes: "\n" stays "\n" on Windows, and the text stays verbatim
            f.write(("### %s\n%s\n%s\n%s\n" % (stamp, fence, prompt, fence)).encode("utf-8"))
        if not is_open:
            open(marker, "wb").close()
    except (OSError, ValueError) as e:  # stderr never reaches the owner or the session: use stdout
        print("Feedback capture: this message was not saved, or capture state did not change (%s)."
              " Jot it by hand into the handoff." % e)


def main(argv):
    try:
        stamp = text = line()
        if "--subagent" in argv:
            text = json.dumps({"hookSpecificOutput": {"hookEventName": "SubagentStart",
                                                      "additionalContext": text}})
        print(text)
        if "--subagent" not in argv:
            capture(sys.stdin.buffer.read(), stamp[len("Local time: "):])
    except Exception as e:  # advisory hook: fail open; one stderr line shows in --debug
        print("local_time: %s" % e, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
