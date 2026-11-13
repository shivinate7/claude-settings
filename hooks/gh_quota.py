"""The one home of the GitHub REST quota read, for merge/merge.py (Host.gh) and hooks/ci_wake.py (watch_run).

`gh api -i` prints the quota with every reply: X-RateLimit-Limit, X-RateLimit-Remaining and X-RateLimit-Reset (an epoch). A caller reads it from
the reply it already has, so the check costs no extra API call and writes no file.
"""
import math
import re

WAIT_CAP = 900   # seconds: the longest wait on a quota, the last rung of merge.py's RATE_LADDER
POLL_PACE = 30   # seconds between two reads of a poll loop; ci_wake's STATUS_PAUSE and merge.py's SETTLE_SECONDS are the same pace

# What `gh api -i` prints first: the status line, the headers, a blank line. An empty body leaves no blank line: the block then runs to the end.
_HEAD_BLOCK = re.compile(r"HTTP/\d(?:\.\d)? \d{3}\b[^\n]*(?:\n(.*?\r?\n)?\r?\n|\n?.*\Z)", re.S)


def split_headers(out):
    """-> (headers, body). A reply that starts with a status line has a header block: its names are lower case in `headers`, and `body` has no block.
    A header-like line anywhere else is text, and the body is the whole reply."""
    m = _HEAD_BLOCK.match(out)
    if not m:
        return {}, out
    pairs = (line.partition(":") for line in m.group(0).splitlines()[1:])
    return {k.strip().lower(): v.strip() for k, sep, v in pairs if sep}, out[m.end():]


def _whole(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def read(headers, now, pace=POLL_PACE):
    """-> (remaining, limit, wait) when the quota is low, else None. `wait` is whole seconds to the reset, at most WAIT_CAP.
    The mark is derived, not fixed: the quota is low when what is left cannot cover the reads this caller makes before the reset, one every
    `pace` seconds. Missing or unreadable headers, a Remaining outside 0..Limit, or a reset not in the future read as unknown: None, so the
    caller never waits on a quota it could not read."""
    limit, left, reset = (_whole(headers.get(k)) for k in ("x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset"))
    if limit is None or left is None or reset is None or limit <= 0 or not 0 <= left <= limit or reset <= now:
        return None
    if left * pace >= reset - now:
        return None
    return left, limit, min(math.ceil(reset - now), WAIT_CAP)
