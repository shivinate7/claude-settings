#!/usr/bin/env python3
"""Ranks the files that merges conflict on. On demand only. Stdlib and git 2.38 or newer.

    python3 lint/conflict_hotspots.py --since DATE [--base main] [--top 20] [--repo .]

Finds each merge commit of two parents since DATE (committer date) that touches --base: the merge is on the base's
history, or one parent is. That covers a merge of main into a branch and a PR merge into main. Replays each with
`git merge-tree --write-tree --name-only <parent1> <parent2>` and counts, per file, the merges that conflict on it.
The replay is what git finds today, not what the author saw: a resolution by hand, rerere or a merge option can differ.

Output (summary lines start with a letter, file rows with a digit):

    merges replayed: N       every replay, an unknown one too
    merges conflicted: M
    merges unknown: U        a replay whose read failed (git exit other than 0 or 1): never counted as clean
    conflict rate: R%        M / N, one decimal; 0.0% when N is 0
    merges not replayed: K   not read at all: octopus merges (more than two parents), merges that miss the base
    <count> <path>           per conflicted file, count descending then path ascending, the first --top
    cost: merge-trees N, wall S s

Not seen: a squash or rebase merge leaves no merge commit, so it is absent from N. A file renamed by the merge shows
under the name git prints for the conflict.

Cost, per run: one start each of git --version, rev-parse (the date, the object folder), rev-list of the base,
log of all refs, and one git merge-tree per replay. No process stays running. It writes nothing into the repo and
creates no ref: git writes the replay's new objects to a fresh folder under TMPDIR, which is removed before exit,
also on Ctrl-C. Exit 0 for a report (zero merges included), 2 for a git older than 2.38, 1 for any other failure.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

# The variables that point git at a repo or an object folder: a caller's value would send each call elsewhere.
REPO_POINTERS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                 "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR")
MIN_GIT = (2, 38)  # the first git with `merge-tree --write-tree`


class Failure(Exception):
    """A read the run cannot go on without. Its text is the one line printed. Exit code 1."""
    code = 1


class GitTooOld(Failure):
    code = 2


def git_env(object_dir=None, alternates=None):
    env = {k: v for k, v in os.environ.items() if k not in REPO_POINTERS}
    env["GIT_OPTIONAL_LOCKS"] = "0"
    if object_dir:
        env["GIT_OBJECT_DIRECTORY"] = object_dir
        env["GIT_ALTERNATE_OBJECT_DIRECTORIES"] = alternates
    return env


def run_git(repo, args, env=None):
    p = subprocess.run(["git", "-C", repo] + args, env=env or git_env(), capture_output=True)
    return p.returncode, p.stdout, p.stderr.decode("utf-8", "replace").strip()


def read_git(repo, args):
    rc, out, err = run_git(repo, args)
    if rc:
        raise Failure("git %s failed (%d): %s" % (" ".join(args[:2]), rc, err or "no message"))
    return out.decode("utf-8", "replace")


def check_version():
    p = subprocess.run(["git", "--version"], env=git_env(), capture_output=True, text=True)
    m = re.search(r"(\d+)\.(\d+)", p.stdout)
    if p.returncode or not m or (int(m.group(1)), int(m.group(2))) < MIN_GIT:
        raise GitTooOld("git %d.%d or newer is needed for merge-tree --write-tree; found: %s"
                      % (MIN_GIT + (p.stdout.strip() or "none",)))


def merges_since(repo, since, base):
    """([(parent1, parent2)] of each two-parent merge on the base since the date, octopus count, off-base count)."""
    cutoff = read_git(repo, ["rev-parse", "--since=" + since]).strip()
    m = re.fullmatch(r"--max-age=(\d+)", cutoff)
    if not m:
        raise Failure("cannot read the date %r" % since)
    cutoff = int(m.group(1))
    on_base = set(read_git(repo, ["rev-list", base, "--"]).split())
    found, octopus, off_base = [], 0, 0
    for line in read_git(repo, ["log", "--all", "--merges", "--format=%H %ct %P"]).splitlines():
        fields = line.split()
        if len(fields) < 4 or int(fields[1]) < cutoff:
            continue
        commit, parents = fields[0], fields[2:]
        if len(parents) != 2:
            octopus += 1
        elif commit in on_base or parents[0] in on_base or parents[1] in on_base:
            found.append(tuple(parents))
        else:
            off_base += 1
    return found, octopus, off_base


def replay(repo, parents, env):
    """(verdict, [paths]) of one merge-tree. Verdict: 'clean', 'conflict' or 'unknown'."""
    rc, out, _ = run_git(repo, ["merge-tree", "--write-tree", "--name-only", "-z"] + list(parents), env)
    if rc == 0:
        return "clean", []
    if rc != 1:
        return "unknown", []
    # -z output: tree id, then each conflicted path, an empty field, then the messages.
    fields = out.split(b"\0")[1:]
    paths = []
    for field in fields:
        if not field:
            break
        paths.append(field.decode("utf-8", "replace"))
    return "conflict", paths


def report(repo, since, base, top):
    started = time.monotonic()
    check_version()
    found, octopus, off_base = merges_since(repo, since, base)
    objects = os.path.abspath(read_git(repo, ["rev-parse", "--path-format=absolute", "--git-path", "objects"]).strip())
    counts, conflicted, unknown, starts = {}, 0, 0, 0
    scratch = tempfile.mkdtemp(prefix="conflict-hotspots-")
    try:
        env = git_env(scratch, objects)
        for parents in found:
            starts += 1
            verdict, paths = replay(repo, parents, env)
            if verdict == "conflict":
                conflicted += 1
                for path in set(paths):
                    counts[path] = counts.get(path, 0) + 1
            elif verdict == "unknown":
                unknown += 1
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    replayed = len(found)
    rate = 100.0 * conflicted / replayed if replayed else 0.0
    lines = ["merges replayed: %d" % replayed, "merges conflicted: %d" % conflicted, "merges unknown: %d" % unknown,
             "conflict rate: %.1f%%" % rate,
             "merges not replayed: %d (octopus %d, off base %d)" % (octopus + off_base, octopus, off_base)]
    for path, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top]:
        lines.append("%d %s" % (count, path))
    lines.append("cost: merge-trees %d, wall %.1f s" % (starts, time.monotonic() - started))
    return lines


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", required=True, help="count merges committed on or after this date, such as 2026-11-18")
    ap.add_argument("--base", default="main", help="the ref whose history a merge must touch (default main)")
    ap.add_argument("--top", type=int, default=20, help="file rows to print (default 20)")
    ap.add_argument("--repo", default=".", help="the repo to read (default the current folder)")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        lines = report(args.repo, args.since, args.base, args.top)
    except Failure as e:
        print(e)
        return e.code
    except KeyboardInterrupt:
        print("interrupted")
        return 130
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
