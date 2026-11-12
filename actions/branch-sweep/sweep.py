#!/usr/bin/env python3
"""Prints a verdict per remote branch: delete only what the Oct 30 grant allows (.claude/CLAUDE.md, standing grants).

    python3 actions/branch-sweep/sweep.py --repo DIR [--default NAME] [--open-head NAME]...

It reads refs/remotes/origin/*, the refs actions/checkout with fetch-depth 0 leaves, and prints one line per
branch: `<delete|keep> <name> <reason>`. origin/HEAD is no branch and gets no line.

A branch is deleted only when its last commit is on the default branch or on an archive/* branch. Never deleted:
the default branch, main, master, roadmap (the record branch), archive/*, and a branch named by --open-head
(deleting the head of an open pull request closes the pull request).

A repo it cannot read, or one with no origin/<default>, exits 2 before any line is printed. The sweep then
deletes nothing, because a verdict made from partial refs could name an unmerged branch as merged.
"""
import argparse
import subprocess
import sys

REMOTE = "refs/remotes/origin/"
# Names kept whatever their history. roadmap holds the roadmap record and is never merged into main.
PROTECTED = ("main", "master", "roadmap")


def git(repo, *args, stdin=None):
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
        elif sha in on_default:
            yield "delete", name, "last commit is on %s" % default
        elif sha in on_archive:
            yield "delete", name, "last commit is on an archive branch"
        else:
            yield "keep", name, "last commit is on no merged or archived branch"


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--default", default="main")
    parser.add_argument("--open-head", action="append", default=[], dest="open_heads")
    args = parser.parse_args(argv)
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
