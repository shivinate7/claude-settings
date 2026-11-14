#!/usr/bin/env python3
"""The one home of the revert rule: does a live revert on a branch lift a red run?

merge/merge.py imports REVERT_LINE, revert_map and net_reverted (Host.base_state and read_lanes read them from a local git log);
actions/ci-alarm/alarm.sh calls this file as a command, which reads the same rule through the API, as the alarm has no checkout.

The rule. A red run R with head sha H is lifted when a commit C reachable from the branch, other than H, carries
`This reverts commit <H>` (40 hex) in its message and is not net-reverted: a revert of C, and a revert of that revert, so an odd
chain is a revert (net_reverted). Each red run needs its own revert, since the revert names the head. It never clears a cancelled run,
a re-run in flight or a failed read; the caller (alarm.sh) does not pass those here.

The API read (command). One `search/commits` read per head, filtered here to the 40-hex revert line (a hit that names the head some
other way, a short sha, or a sha one digit off is no revert), and one `compare` read per hit, `<hit>...<branch>`: status `ahead` or
`identical` means the hit is reachable from the branch, `behind` or `diverged` means it is not. Each reachable hit is followed the same
way for its own revert, so a chain costs one search and one compare per link. When a commit has several reverters, the OLDEST reachable one by
commit date is followed, as merge.py's revert_map keeps the oldest of a log read newest first; a missing date or a tie reads unknown. Commit search reads the default branch only, so a branch
that is not the default usually finds no revert: it alarms and never clears. A reply that is not JSON, has no status, or is a page
that cuts hits off (`incomplete_results`, or `total_count` above the items) is a failed read.

Command: revert_rule.py --repo OWNER/REPO --branch BRANCH --head SHA. Calls `gh api`. Exit 0 when a live revert lifts the run, 1 when
none does, 2 on a failed read or any reply it cannot judge (unknown, never lifted). Stdlib only: the action runs from a bare action path with no checkout.
"""
import argparse
import datetime
import json
import re
import subprocess
import sys

REVERT_LINE = re.compile(r"This reverts commit ([0-9a-f]{40})")
GH_TIMEOUT = 60  # seconds for one gh call


class Unread(Exception):
    """A read failed or gave a reply that cannot be judged: the verdict is unknown."""


def revert_map(recs):
    """-> {commit: the commit that reverts it}, from the "This reverts commit <sha>." lines of `recs` ((sha, parents, body) rows, newest first)."""
    undone = {}
    for h, _, body in recs:
        for r in REVERT_LINE.findall(body):
            undone[r] = h
    return undone


def net_reverted(undone, h):
    """True when commit `h` is undone: a revert of it, and a revert of that revert, so an odd chain is a revert. The one home of the net-revert read,
    which merge.py's read_lanes and Host.base_state and the alarm's live_revert all call."""
    n, seen = 0, set()
    while h in undone and h not in seen:
        seen.add(h)
        h, n = undone[h], n + 1
    return n % 2 == 1


def gh_json(*args):
    """The JSON reply of one `gh api` call; a failed call or a reply that is not a JSON object raises Unread."""
    try:
        # nowindow: runs on a Linux CI runner only; the action path has no hooks/_nowindow.py beside it
        done = subprocess.run(["gh", "api", *args], capture_output=True, text=True, timeout=GH_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Unread(f"gh api {args[-1] if args else ''} did not run: {e}")
    if done.returncode:
        raise Unread(f"gh api failed: {(done.stderr.strip().splitlines() or ['?'])[-1]}")
    try:
        reply = json.loads(done.stdout)
    except ValueError:
        raise Unread("gh api gave a reply that is not JSON")
    if not isinstance(reply, dict):
        raise Unread("gh api gave a reply that is not an object")
    return reply


def commit_time(item):
    """-> the commit's committer date (else author date) as an aware datetime, or None when the hit carries none that parses."""
    commit = item.get("commit")
    for who in ("committer", "author"):
        person = commit.get(who) if isinstance(commit, dict) else None
        stamp = person.get("date") if isinstance(person, dict) else None
        if isinstance(stamp, str):
            try:
                when = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            except ValueError:
                return None
            return when if when.tzinfo else None
    return None


def revert_hits(repo, head):
    """-> [(sha, committer time or None)] of the commits whose message has the revert line for `head`, other than `head`. One search read."""
    reply = gh_json("-X", "GET", "search/commits", "-f", f'q="This reverts commit {head}" repo:{repo}', "-f", "per_page=100")
    items = reply.get("items")
    if not isinstance(items, list) or reply.get("incomplete_results") or (isinstance(reply.get("total_count"), int) and reply["total_count"] > len(items)):
        raise Unread(f"the revert search for {head[:9]} gave no whole list of commits")
    hits = []
    for it in items:
        sha = it.get("sha") if isinstance(it, dict) else None
        commit = it.get("commit") if isinstance(it, dict) else None
        message = commit.get("message") if isinstance(commit, dict) else None
        if not isinstance(sha, str) or not isinstance(message, str):
            raise Unread(f"the revert search for {head[:9]} gave a hit with no sha or message")
        if sha != head and head in REVERT_LINE.findall(message):
            hits.append((sha, commit_time(it)))
    return hits


def reachable(repo, branch, sha):
    """True when `sha` is an ancestor of (or is) the tip of `branch`: compare status ahead or identical. One compare read."""
    status = gh_json(f"repos/{repo}/compare/{sha}...{branch}?per_page=1").get("status")
    if status in ("ahead", "identical"):
        return True
    if status in ("behind", "diverged"):
        return False
    raise Unread(f"the compare of {sha[:9]} with {branch} gave no status")


def live_hit(repo, branch, sha, seen):
    """The reachable reverter of `sha` that revert_map would keep, or None (one search, one compare per hit read).
    merge.py reads `git log` newest first and revert_map lets the later line overwrite, so the OLDEST reachable reverter of a commit wins, whatever
    order search lists them in. Hits are tried oldest first by committer date, and the first reachable one is the pick. With two or more hits, a hit
    whose date is missing or does not parse, or a pick whose date ties another reachable hit's, cannot be ordered as git log orders them:
    unknown (Unread), never a guess. A pick already in `seen` ends the chain, as net_reverted ends it on a cycle."""
    hits = revert_hits(repo, sha)
    if len(hits) > 1 and any(when is None for _, when in hits):
        raise Unread(f"the revert search for {sha[:9]} gave reverters with no usable commit date, so the oldest cannot be told")
    ordered = sorted(hits, key=lambda h: h[1]) if len(hits) > 1 else hits
    for i, (h, when) in enumerate(ordered):
        if not reachable(repo, branch, h):
            continue
        if h in seen:
            return None
        if any(w == when and reachable(repo, branch, o) for o, w in ordered[i + 1:]):
            raise Unread(f"two reachable reverters of {sha[:9]} share one commit date, so the oldest cannot be told")
        return h
    return None


def live_revert(repo, branch, head):
    """-> the sha of a live revert of `head` on `branch`, or None. Raises Unread on a failed read.
    Builds `undone` for each reachable revert's chain, then asks net_reverted, as merge.py does with its git log."""
    seen = {head}
    for first, _ in revert_hits(repo, head):
        if first in seen or not reachable(repo, branch, first):
            continue
        undone, link = {}, first
        seen.add(first)
        while True:
            nxt = live_hit(repo, branch, link, seen)
            if nxt is None:
                break
            undone[link] = nxt
            seen.add(nxt)
            link = nxt
        if not net_reverted(undone, first):
            return first
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--branch", required=True)
    ap.add_argument("--head", required=True)
    a = ap.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{40}", a.head):
        return 1  # no whole head sha, so no revert line can name it
    try:
        return 0 if live_revert(a.repo, a.branch, a.head) else 1
    except Unread as e:
        print(f"revert_rule: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # a reply shape or text this rule did not expect is unknown: an escaped exception exits 1, which alarm.sh reads as no revert
        print(f"revert_rule: unread reply ({type(e).__name__}: {e})", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
