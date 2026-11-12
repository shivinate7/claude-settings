#!/usr/bin/env python3
"""Prints a verdict per remote branch: delete only what the Oct 30 grant allows (.claude/CLAUDE.md, standing grants).

    python3 actions/branch-sweep/sweep.py --repo DIR [--default NAME] [--open-head NAME]...
    python3 actions/branch-sweep/sweep.py --budget-reserve

It reads refs/remotes/origin/*, the refs actions/checkout with fetch-depth 0 leaves, and prints one line per
branch: `<delete|keep> <name> <reason>`. origin/HEAD is no branch and gets no line.

A branch is deleted only when its last commit is on the default branch or on an archive/* branch. Never deleted:
the default branch, main, master, roadmap (the record branch), stable (it moves with green main, and child CI
installs from it), archive/*, a branch named by --open-head
(deleting the head of an open pull request closes the pull request), and a branch whose name has a character
outside [A-Za-z0-9._/-] or starts with "-". The workflow puts the name raw into a DELETE URL, where `#` ends the
path and could delete another branch, and a leading "-" reads as an option.

A repo it cannot read, or one with no origin/<default>, exits 2 before any line is printed. The sweep then
deletes nothing, because a verdict made from partial refs could name an unmerged branch as merged.

--budget-reserve prints BUDGET_RESERVE and exits. The workflow reads the reserve from here, so the number has one home.
"""
import argparse
import re
import subprocess
import sys

REMOTE = "refs/remotes/origin/"
# Names kept whatever their history. roadmap holds the roadmap record and is never merged into main. stable moves with green main (restart-plan R42 part 2), so its tip is always on main's history.
PROTECTED = ("main", "master", "roadmap", "stable")
# GitHub requests the delete step aims to leave unspent. The step reads the remaining budget once per run and counts two requests per
# branch (tip read, DELETE) locally, not a fresh read per delete. It stops green when the count is below this before a delete; a check
# at the reserve passes and the delete spends 2, so the real floor is 298. The next run finishes the rest only after the hourly reset,
# on a later push to main or a dispatch. Other runs in the repo share the pool.
BUDGET_RESERVE = 300
SAFE_NAME = re.compile(r"[A-Za-z0-9._/-]+")


def git(repo, *args, stdin=None):
    # nowindow: runs on an ubuntu runner only, and the workflow test copies actions/branch-sweep alone, so hooks/_nowindow.py is not on the path
    done = subprocess.run(["git", "-C", repo, *args], input=stdin, capture_output=True, text=True)
    if done.returncode:
        raise RuntimeError("git %s failed: %s" % (" ".join(args), done.stderr.strip()))
    return done.stdout


def remote_branches(repo):
    """{name: sha} for every origin branch but HEAD."""
    out = git(repo, "for-each-ref", "--format=%(refname) %(objectname)", REMOTE)
    branches = {}
    for line in out.splitlines():
        ref, sha = line.split(" ", 1)
        name = ref[len(REMOTE):]
        if name != "HEAD":
            branches[name] = sha
    return branches


def reachable(repo, tips):
    """Every commit reachable from the tips. Tips go through stdin: a repo can hold thousands of archive branches."""
    if not tips:
        return set()
    return set(git(repo, "rev-list", "--stdin", stdin="".join(t + "\n" for t in tips)).split())


def verdicts(repo, default, open_heads):
    branches = remote_branches(repo)
    if default not in branches:
        raise RuntimeError("origin/%s does not exist" % default)
    archives = sorted(sha for name, sha in branches.items() if name.startswith("archive/"))
    on_default = reachable(repo, [branches[default]])
    on_archive = reachable(repo, archives)
    for name in sorted(branches):
        sha = branches[name]
        if name == default or name in PROTECTED:
            yield "keep", name, "protected name"
        elif name.startswith("archive/"):
            yield "keep", name, "archive branch"
        elif name in open_heads:
            yield "keep", name, "open pull request"
        elif not SAFE_NAME.fullmatch(name) or name.startswith("-"):
            yield "keep", name, "name has a character a delete URL cannot carry safely"
        elif sha in on_default:
            yield "delete", name, "last commit is on %s" % default
        elif sha in on_archive:
            yield "delete", name, "last commit is on an archive branch"
        else:
            yield "keep", name, "last commit is on no merged or archived branch"


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--repo")
    parser.add_argument("--budget-reserve", action="store_true", dest="budget_reserve")
    parser.add_argument("--default", default="main")
    parser.add_argument("--open-head", action="append", default=[], dest="open_heads")
    args = parser.parse_args(argv)
    if args.budget_reserve:
        print(BUDGET_RESERVE)
        return 0
    if not args.repo:
        parser.error("--repo is required")
    try:
        lines = list(verdicts(args.repo, args.default, set(args.open_heads)))
    except (RuntimeError, OSError) as err:
        print("branch-sweep: %s" % err, file=sys.stderr)
        return 2
    for verb, name, reason in lines:
        print("%s %s %s" % (verb, name, reason))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
