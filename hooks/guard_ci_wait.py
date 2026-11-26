"""The guard's ci-wait family: the ci-wait-cap rules on how long a session waits for a CI run.

guard.py is the only entry point, and it calls these checks in its fixed order. Other files reach
these names through `guard`.

Rule index (moved from guard.py):

  ci-wait-cap
      deny. A claude-code-remote send_later whose message says it waits on CI (the whole word CI,
      checks, pipeline, check run, PR run(s), workflow run(s) or GitHub Actions, in any case,
      anywhere in the message) and whose wait is more than cap_minutes() in hooks/ci_wait_cap.py:
      delay_minutes (a number or a string of digits) over it, or an `at` (ISO-8601; with no offset it
      reads in the clock's offset) more than that many minutes after the clock (local_time.clock).
      The limit is inclusive. A call with no CI word, or with no delay or `at`, passes. An agent's
      call is refused first (agent-no-remote-tools). The reason names send_later, delay_minutes and
      the cap. A missing cap file crashes the rule, which fails open and logs. An override lifts it.
      (ci-wait-cap-guard)
"""
import re

from shared_names import REMOTE_SERVER  # the one home of the remote server name


# A send_later check-in that waits on CI for longer than the cap (rule ci-wait-cap; decision ci-wait-cap-guard).
# Mistake: a session sets a CI check-in that wakes after the 1-hour prompt cache ends. Harm: the wake pays a full
# context rewrite. The cap is cap_minutes() in hooks/ci_wait_cap.py, read on each call and never copied here. The message
# is plain text, so comment openers and lone quotes in it carry no meaning to the scan. A missing cap file raises, and
# main() logs the crash and lets the call through: a lost source is never turned into a made-up limit.
CI_WAIT_TOOL = REMOTE_SERVER + "__send_later"
CI_WAIT_WORDS = re.compile(
    r"(?<!\w)(?:ci|checks|pr\s+runs?|workflow\s+runs?|check\s+runs?|pipelines?|github\s+actions)(?!\w)", re.IGNORECASE)
CI_WAIT_DIGITS = re.compile(r"\d+(?:\.\d+)?")
CI_WAIT_REASON = ("A check-in that waits on CI may wait at most %d minutes, because under the 1-hour prompt cache a later "
                  "wake pays a full context rewrite. Set send_later with delay_minutes of %d or less, or an `at` no more "
                  "than %d minutes ahead, then set the next check-in when this one wakes. "
                  "(decision ci-wait-cap-guard, a CI check-in stays inside the prompt cache)")


def ci_wait_minutes(tool_input: dict):
    """The wait a send_later call asks for, in minutes: the larger of delay_minutes and the `at` time's distance from
    the clock. delay_minutes is a number or a string of digits. An `at` with no offset reads in the clock's own offset.
    None when neither reads: no field, or a value that is not a number or an ISO-8601 time."""
    waits = []
    delay = tool_input.get("delay_minutes")
    if isinstance(delay, str) and CI_WAIT_DIGITS.fullmatch(delay.strip()):
        waits.append(float(delay))
    elif isinstance(delay, (int, float)) and not isinstance(delay, bool):
        waits.append(delay)
    at = tool_input.get("at")
    if isinstance(at, str):
        import local_time  # the one home of the clock, which LOCAL_TIME_NOW replaces in tests
        from datetime import datetime
        text = at.strip()
        try:
            when = datetime.fromisoformat(text[:-1] + "+00:00" if text[-1:] in ("Z", "z") else text)
        except ValueError:
            when = None
        if when is not None:
            now = local_time.clock()
            if when.tzinfo is None:
                when = when.replace(tzinfo=now.tzinfo)
            waits.append((when - now).total_seconds() / 60)
    return max(waits) if waits else None


def ci_wait_hit(tool: str, tool_input: dict) -> str:
    """The refusal reason when this send_later waits on CI past the cap, else "". Reads the whole message."""
    if tool != CI_WAIT_TOOL:
        return ""
    message = tool_input.get("message")
    if not isinstance(message, str) or not CI_WAIT_WORDS.search(message):
        return ""
    wait = ci_wait_minutes(tool_input)
    if wait is None:
        return ""
    import ci_wait_cap  # the one home of the cap
    cap = ci_wait_cap.cap_minutes()
    return CI_WAIT_REASON % (cap, cap, cap) if wait > cap else ""


# INSTALL_ID = "uninstalled"
