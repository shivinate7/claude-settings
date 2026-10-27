#!/usr/bin/env python3
"""Count merges to main that a later commit had to repair.

Usage: python3 merge/repaired_merges.py [--days N] [--ref main] [--repo DIR]

A first-parent merge commit on the ref, made in the last N days (default 14), is repaired when a later
first-parent commit either
  (a) says "This reverts commit <sha>" for the merge or for any commit the merge brought in, or
  (b) names the merge's PR ("#N") or its branch (from "Merge pull request #N from owner/<branch>")
      on the same line as a fix word (fix, repair, hotfix, broke, revert).
Prints the count, then one line per repaired merge: merge sha, PR, repairing commit sha.

Cost (rule outcomes-mechanize-rules): read on demand, never on a timer. Starts about 3 git processes
per merge in the window and one `git log` for the later commits. Writes no file and starts no
long-lived process.
"""
import argparse
import re
import subprocess
import sys
import time

FIX = re.compile(r"\b(fix|fixes|fixed|fixing|repair|repairs|repaired|hotfix|broke|broken|revert|reverts)\b", re.I)
MERGE_SUBJECT = re.compile(r"^Merge pull request #(\d+) from [^/\s]+/(\S+)")
REVERTS = re.compile(r"This reverts commit ([0-9a-f]{7,40})")


def git(repo, *args):
    r = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def names(line, pr, branch):
    """True when the line names the PR number or the branch as a whole token."""
    pr_hit = re.search(rf"#{pr}(?!\d)", line)
    branch_hit = re.search(rf"(?<![\w./-]){re.escape(branch)}(?![\w./-])", line)
    return bool(pr_hit or branch_hit)


def repairing_commit(merge, pr, branch, brought, later):
    """Return the short sha of the first later commit that repairs this merge, or None."""
    for sha, body in later:
        for rev in REVERTS.findall(body):
            if any(h.startswith(rev) for h in brought):
                return sha[:7]
        if any(FIX.search(line) and names(line, pr, branch) for line in body.splitlines()):
            return sha[:7]
    return None


def repaired(repo, ref, days):
    # Filter by date here: git's own --since stops walking at the first old commit, so one commit with an
    # old date would hide every merge below it.
    cutoff = time.time() - days * 86400
    out = git(repo, "log", "--first-parent", "--merges", "--format=%H%x00%ct%x00%s", ref)
    found = []
    for row in out.splitlines():
        sha, when, subject = row.split("\x00", 2)
        if int(when) < cutoff:
            continue
        m = MERGE_SUBJECT.match(subject)
        if not m:
            continue
        pr, branch = m.group(1), m.group(2)
        brought = {sha, *git(repo, "rev-list", f"{sha}^1..{sha}^2").split()}
        log = git(repo, "log", "--first-parent", "--reverse", "--format=%H%x00%B%x01", f"{sha}..{ref}")
        later = [(c.partition("\x00")[0].strip(), c.partition("\x00")[2]) for c in log.split("\x01") if c.strip()]
        fix = repairing_commit(sha, pr, branch, brought, later)
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
