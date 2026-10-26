#!/usr/bin/env python3
"""UserPromptSubmit and SubagentStart hook: tell the session the time in US Central (America/Chicago). On UserPromptSubmit it also captures owner feedback: a prompt that opens with `fb` is saved to the session's inbox file until a prompt of `fb done`.

Modes:
- UserPromptSubmit: Tells the session the time in US Central. A prompt that opens with
  `fb` also starts feedback capture to the session's inbox file. Capture ends at `fb done`,
  after 10 minutes of quiet, or when a judge says a prompt is not feedback.
  A prompt whose first word is `override` also grants a one-act owner override pass, and the rest is the
  reason, logged to guard.log. `override <n>[m|h]` and `override off` mean that only as the whole prompt
  (decision owner-override-pass; hooks/override_pass.py). It prints one more line.
- --agent: At SubagentStart, gives the agent the time in US Central as context.

Sessions speak times in US Central, 24-hour clock (decision local-time-central). Prints one line, for example "Local time: 2026-10-13 21:40 CDT (UTC-05:00)".
Plain stdout is context for UserPromptSubmit. SubagentStart takes context only as JSON, so
`--agent` prints `hookSpecificOutput` with `additionalContext` (Claude Code hooks reference).
The US rule is coded here, not read from zoneinfo: Windows Python often has no tz database.
Advisory, fail-open: any error prints one stderr line and exits 0.

This hook is also the owner feedback inbox's capture (decision owner-feedback-inbox). A UserPromptSubmit
prompt whose first word is `fb` or `fb:` opens capture. While open, a prompt that starts with `fb done`
or `fb: done` (any case, any whitespace between the words) closes it, and the rest of that prompt is
not saved. A prompt that ends with a line `fb done` (same match) is saved without that line and closes
capture in the same message, whether capture was closed (the prompt opens with `fb`) or open. Capture also ends by itself: when the last captured owner message is more than GAP old, and
when the Sonnet judge says a prompt is not feedback. Every prompt is saved first. A detached child
(feedback_judge.py) judges it, off the prompt path: the call takes 8 s or more. On a not-feedback
answer the child adds a note item under that message and closes capture, if no newer message was
captured. A failed or late judge changes nothing. A notice (a prompt that starts with a
shared_names.MACHINE_TAGS tag) is never captured or judged, and does not close capture. With
capture closed, no `fb ... done` form opens it;
with capture open, `fb - done` is captured as a message.
While open, each prompt is appended verbatim to <config dir>/handoffs/<session_id>.inbox.md in a
backtick fence longer than any backtick run in the text. Open state is the marker file
<session_id>.inbox.open beside it; its text is the time of the last captured message. `is_open` is the
one home of "is capture open": feedback_gate.py and precompact_handoff.py call it. LOCAL_TIME_NOW
(ISO-8601 with an offset) replaces the clock; tests set it. `--agent` never reads stdin and never
captures. The gate that reads the inbox is feedback_gate.py.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
try:
    import _nowindow  # the one home of a no-window child start (hooks/_nowindow.py)
except ImportError:  # a hook never dies for a missing helper (it lands a moment after the hook in an install)
    _nowindow = subprocess

CST = timedelta(hours=-6)
GAP = timedelta(minutes=10)  # quiet time that ends capture
CLOSE = re.compile(r"fb:?\s+done\b", re.I)  # matched at the start of the stripped prompt
CLOSE_LINE = re.compile(r"\n[ \t]*fb:?\s+done[^\w\s`]*\s*$", re.I)  # a last line of `fb done`: saves the rest, then closes
NEAR_MISS = re.compile(r"fb[\W_]+done\b", re.I)  # while closed: never opens
MESSAGE_MAX = 4000  # the most of a message the judge child gets on its command line


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
    """`HH:MM CDT` (or CST) for an instant: the time line's own clock, cut to the end of a pass."""
    return " ".join(line(lambda: at).split()[3:5])


def override_line(result):
    """The context line for a grant() result: names the pass and when it ends, Central time."""
    kind, until = result[:2]
    if kind == "off":
        return "Override pass: ended."
    if kind == "opus-off":
        return "Opus pass: ended."
    if kind == "opus":
        who = "%s spawns" % result[2] if result[2] else "spawns"
        return "Opus pass: Opus %s go through without the ask until %s." % (who, central_hhmm(until))
    if kind == "once":
        return "Override pass: the next refused act goes through, once. It ends at %s if unused." % central_hhmm(until)
    return "Override pass: every refused act goes through until %s." % central_hhmm(until)


def inbox_paths(session_id):
    """(inbox, open marker) for a session, or None when the id cannot be a file name. The one home
    of these paths: feedback_gate.py calls it. precompact_handoff owns the handoffs folder."""
    if not re.fullmatch(r"[\w.-]+", session_id or "") or session_id.startswith("."):
        return None
    import precompact_handoff
    base = os.path.join(os.path.dirname(precompact_handoff.handoff_path(session_id)), session_id)
    return base + ".inbox.md", base + ".inbox.open"


def is_open(marker, at=None):
    """True when capture is open: the marker exists and its last captured message is at most GAP old.
    The marker's text is that message's time; an empty or damaged marker falls back to its mtime."""
    try:
        with open(marker, "rb") as f:
            text = f.read().decode("ascii", "ignore").strip()
        try:
            last = datetime.fromisoformat(text)
            last = last if last.tzinfo else last.replace(tzinfo=timezone.utc)
        except ValueError:
            last = datetime.fromtimestamp(os.path.getmtime(marker), timezone.utc)
    except OSError:
        return False
    return (at or clock()) - last <= GAP


def capture(raw, stamp, at=None):
    """Opens, closes or appends for one owner prompt. `raw` is the hook's stdin as bytes."""
    hook = json.loads(raw.decode("utf-8"))
    prompt = hook.get("prompt")
    paths = inbox_paths(hook.get("session_id"))
    if paths is None or not isinstance(prompt, str):
        return
    inbox, marker = paths
    said = prompt.strip()
    try:
        from shared_names import MACHINE_TAGS  # stdlib only: this hook loads no guard module
    except ImportError:  # missing or stale helper: only the notice check degrades; capture and the grant run on
        MACHINE_TAGS = ()
    if MACHINE_TAGS and said.startswith(MACHINE_TAGS):
        return  # a notice is not an owner message: never captured, judged or closing
    at = at or clock()
    opened = is_open(marker, at)
    # JSON can carry a lone surrogate, which UTF-8 cannot encode: save U+FFFD in its place.
    prompt = re.sub("[\ud800-\udfff]", "�", prompt)
    try:
        opener = (prompt.split() or [""])[0] in ("fb", "fb:")
        if not opened:
            if os.path.exists(marker):
                os.remove(marker)  # quiet time ended capture
            if not opener or NEAR_MISS.match(said):
                return  # closed: only an opener opens, and never a near-miss of `fb done`
        elif CLOSE.match(said):
            os.remove(marker)
            return
        closing = CLOSE_LINE.search(prompt)
        if closing:
            prompt = prompt[:closing.start()]  # the `fb done` line is not part of the note
        judge = opened and not opener and not closing  # saved first, judged after: the judge runs detached
        fence = "`" * max([3] + [len(r) + 1 for r in re.findall(r"`+", prompt)])
        os.makedirs(os.path.dirname(inbox), exist_ok=True)
        with open(inbox, "ab") as f:  # bytes: "\n" stays "\n" on Windows, and the text stays verbatim
            f.write(("### %s\n%s\n%s\n%s\n" % (stamp, fence, prompt, fence)).encode("utf-8"))
        if closing:
            if os.path.exists(marker):
                os.remove(marker)  # saved, and closed in the same message
        else:
            with open(marker, "wb") as f:  # the last captured message's time: the quiet-time clock
                f.write(at.isoformat().encode("ascii"))
        if judge:
            try:  # the same detached-child pattern as janitor/agent_end_reap.py; the hook does not wait
                child = _nowindow.Popen([sys.executable, os.path.join(HERE, "feedback_judge.py"),
                                  hook["session_id"], at.isoformat(), prompt[:MESSAGE_MAX]], stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                if os.environ.get("FEEDBACK_JUDGE_INLINE"):
                    child.wait()  # test seam: the hook waits for the judge
            except OSError:
                pass  # no judge: the message stays saved and capture stays open
    except (OSError, ValueError) as e:  # stderr never reaches the owner or the session: use stdout
        print("Feedback capture: this message was not saved, or capture state did not change (%s)."
              " Jot it by hand into the handoff." % e)


def grant_override(raw, at):
    """Owner prompt `override`, `override <reason>`, `override <n>[m|h]`, `override off` or the Opus word
    (`opus <n>[m|h]`, `opus <role> <n>[m|h]`, `opus off`; decision owner-override-pass): grants or ends
    the session's pass and prints one line. Any failure is one stderr line, no pass."""
    try:
        hook = json.loads(raw.decode("utf-8"))
        import override_pass
        result = override_pass.grant(hook.get("session_id"), hook.get("prompt"), at)
        if result:
            print(override_line(result))
    except (ValueError, AttributeError):
        pass  # stdin is no hook payload: capture() reports that once
    except Exception as e:  # advisory: the time line and capture still run
        print("local_time: override pass: %s" % e, file=sys.stderr)


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
            capture(raw, stamp[len("Local time: "):], now)
    except Exception as e:  # advisory hook: fail open; one stderr line shows in --debug
        print("local_time: %s" % e, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
