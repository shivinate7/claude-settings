#!/usr/bin/env python3
"""Count merges to main that a later commit had to repair.

Usage: python3 merge/repaired_merges.py [--days N] [--ref main] [--repo DIR]

A first-parent merge commit on the ref, made in the last N days (default 14), is repaired when a commit
that landed on the ref in a LATER first-parent step (a later merge brings its second-parent commits with it) either
  (a) says "This reverts commit <sha>" for the merge or for any commit the merge brought in, or
  (b) has a fix word (fix, repair, hotfix, broke, revert) in its subject line and names the merge's PR
      ("#N") there, or is a merge whose subject holds the merge's full branch name as a token (from
      "Merge pull request #N from owner/<branch>"). A bare branch word in a plain commit subject does not count.
A commit whose subject starts with "Reapply" is skipped: it re-lands work, and the earlier revert was the repair.
Prints the count, then one line per repaired merge: merge sha, PR, repairing commit sha.

Cost (rule outcomes-mechanize-rules): read on demand, never on a timer. Starts one `git log` plus one
`git log` per first-parent commit on the ref (426 on this repo, about 4 s); it scans the whole first-parent
history, not just the window. Writes no file and starts no long-lived process.
"""
import argparse
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)

FIX = re.compile(r"\b(fix|fixes|fixed|fixing|repair|repairs|repaired|hotfix|broke|broken|revert|reverts)\b", re.I)
MERGE_SUBJECT = re.compile(r"^Merge pull request #(\d+) from [^/\s]+/(\S+)")
REVERTS = re.compile(r"This reverts commit ([0-9a-f]{7,40})")


def git(repo, *args):
    r = _nowindow.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def names_pr(subject, pr):
    return bool(re.search(rf"(?<![\w/]){'#' + pr}(?!\d)", subject))


def names_branch(subject, branch):
    """The full branch name as a token of a merge subject ("Merge pull request #N from o/fix-<branch>" or
    "Merge branch '<branch>'"). A bare word in a commit subject does not count."""
    if not subject.startswith("Merge"):
        return False
    return bool(re.search(rf"(?<![A-Za-z0-9._]){re.escape(branch)}(?![A-Za-z0-9._])", subject))


def repairing_commit(pr, branch, brought, later):
    """Return the short sha of the first commit that landed after the merge and repairs it, or None.
    later: (sha, subject, body) of every commit that landed on the ref in a later first-parent step.
    A Reapply re-lands work, so it repairs nothing. The fix word is read in the subject line only."""
    for sha, subject, body in later:
        if subject.startswith("Reapply"):
            continue
        if any(h.startswith(rev) for rev in REVERTS.findall(body) for h in brought):
            return sha[:7]
        if FIX.search(subject) and (names_pr(subject, pr) or names_branch(subject, branch)):
            return sha[:7]
    return None


def landings(repo, ref):
    """[(first-parent commit, [(sha, message) of every commit it brought to the ref])], oldest first.
    A merge brings its second-parent commits with it, so a repair inside a later batch merge is seen."""
    steps = git(repo, "log", "--first-parent", "--reverse", "--format=%H%x00%ct%x00%P%x00%s", ref).splitlines()
    out = []
    for row in steps:
        sha, when, parents, subject = row.split("\x00", 3)
        rng = f"{sha}^1..{sha}" if parents else sha
        log = git(repo, "log", "--format=%H%x00%s%x00%b%x01", rng)
        commits = [tuple(c.strip("\n").split("\x00", 2)) for c in log.split("\x01") if c.strip()]
        out.append((sha, int(when), parents.count(" ") == 1, subject, commits))
    return out


def repaired(repo, ref, days):
    # Dates are filtered here: git's own --since stops walking at the first old commit, so one commit with an
    # old date would hide every merge below it.
    cutoff = time.time() - days * 86400
    steps = landings(repo, ref)
    found = []
    for i, (sha, when, is_merge, subject, commits) in enumerate(steps):
        m = MERGE_SUBJECT.match(subject)
        if not (is_merge and m) or when < cutoff:
            continue
        pr, branch = m.group(1), m.group(2)
        brought = {c[0] for c in commits}
        later = [c for step in steps[i + 1:] for c in step[4]]
        fix = repairing_commit(pr, branch, brought, later)
        if fix:
            found.append((sha[:7], pr, fix))
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--ref", default="main")
    ap.add_argument("--repo", default=".")
    a = ap.parse_args()
    found = repaired(a.repo, a.ref, a.days)
    print(f"repaired merges in the last {a.days} days: {len(found)}")
    for sha, pr, fix in found:
        print(f"{sha} #{pr} repaired by {fix}")


if __name__ == "__main__":
    sys.exit(main())
