#!/usr/bin/env python3
"""Ranks the files that merges conflict on. On demand only. Stdlib and git 2.38 or newer.

    python3 lint/conflict_hotspots.py --since YYYY-MM-DD [--base REF] [--top 20] [--repo .] [--exposure]
                                      [--into-branches] [--list]

--since takes YYYY-MM-DD only, a real calendar date; --top takes 1 or more. Any other value exits 1 with one line.
--base defaults to origin/main when refs/remotes/origin/main exists, else main: a clone's local main can lag the remote.

Finds each merge commit of two parents since DATE (committer date) that touches --base: the merge is on the base's
history, or one parent is. That covers a merge of main into a branch and a PR merge into main. Replays each with
`git merge-tree --write-tree --name-only <parent1> <parent2>` and counts, per file, the merges that conflict on it.
The replay is what git finds today, not what the author saw: a resolution by hand, rerere or a merge option can differ.

Three opt-in flags. Without them the output is unchanged.

    --exposure        each file row reads `<conflicts>/<exposure> <path>`. Exposure is the replayed merges where both
                      sides changed the file: it differs from the merge base on each parent (renames off, so a rename
                      changes both its old and new path). It tells a file that conflicts often from one that is merely
                      busy. A file no merge conflicts on gets no row. A conflict git names on a path that only one side
                      changed (a rename/delete) reads `1/0`. A merge with no merge base adds no exposure. With several
                      merge bases, git merge-base picks one.
    --into-branches   the filter runs before every count: only a merge of the base INTO a branch counts: the merge is off
                      the base's first-parent line, its first parent is off that line too, and exactly one parent is on
                      it (for two parents, the second). A merge whose first parent is on the line (a branch merged into
                      the base), a PR merge into the base, a merge of two branches, a merge whose parents reach the base
                      only through a PR merge, and a merge with no base parent are dropped and appear in no line,
                      `merges not replayed` included.
    --list            after the file rows, one line per conflicted merge: `merge <sha9> <paths>`, the merge commit and the
                      files git names for it, joined by single spaces. A clean or unknown merge has no line.

Output (summary lines start with a letter, file rows with a digit):

    base: <name> <sha9>      the base read and its commit, the first 9 hex digits
    merges replayed: N       every replay, an unknown one too
    merges conflicted: M
    merges unknown: U        a replay whose read failed (git exit other than 0 or 1): never counted as clean
    conflict rate: R%        M / N, one decimal; 0.0% when N is 0
    merges not replayed: K   not read at all: octopus merges (more than two parents), merges that miss the base
    <count> <path>           per conflicted file, count descending then path ascending, the first --top
    cost: merge-trees N, wall S s
    caveat: ...              three lines: a replay is not what the author resolved; squash and rebase merges are
                             absent; refs walked: all

Not seen: a squash or rebase merge leaves no merge commit, so it is absent from N. A file renamed by the merge shows
under the name git prints for the conflict. A shallow clone is not read: the history is cut, so every count would be a
lower bound. The run prints `history is cut at depth ...; counts are a lower bound` and no report, and exits 3 (unknown).

Cost, per run: one start each of git --version, rev-parse (the date, the object folder, the base, whether the clone is
shallow, whether origin/main exists), rev-list of the base, log of all refs, and one git merge-tree per replay. No process stays running. Added by --exposure: three git starts
per replayed merge (one merge-base, two diffs), so a run of N merges starts about 3N more git processes and its wall
time grows by about that share. Added by --into-branches: one rev-list --first-parent of the base. The cost line counts
merge-trees only. It writes nothing into the repo and
creates no ref: git writes the replay's new objects to a fresh folder under TMPDIR, which is removed before exit,
also on Ctrl-C. Exit 0 for a report (zero merges included), 2 for a git older than 2.38, 3 for a history cut at depth, 1 for any
other failure, a bad --since or --top included.
"""
import argparse
import datetime
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


class HistoryCut(Failure):
    """Unknown, not a count: a cut history hides merges, so no report is printed."""
    code = 3


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


def merges_since(repo, since, base, into_branches=False):
    """([(merge, parent1, parent2)] of each two-parent merge on the base since the date, octopus count, off-base count).
    With into_branches, a merge that is not a merge of the base into a branch is dropped first and counted nowhere."""
    cutoff = read_git(repo, ["rev-parse", "--since=" + since]).strip()
    m = re.fullmatch(r"--max-age=(\d+)", cutoff)
    if not m:
        raise Failure("cannot read the date %r" % since)
    cutoff = int(m.group(1))
    on_base = set(read_git(repo, ["rev-list", base, "--"]).split())
    trunk = set(read_git(repo, ["rev-list", "--first-parent", base, "--"]).split()) if into_branches else set()
    found, octopus, off_base = [], 0, 0
    for line in read_git(repo, ["log", "--all", "--merges", "--format=%H %ct %P"]).splitlines():
        fields = line.split()
        if len(fields) < 4 or int(fields[1]) < cutoff:
            continue
        commit, parents = fields[0], fields[2:]
        # A branch merged into the base has its first parent on the line; a merge of the base into a branch does not.
        if into_branches and (commit in trunk or parents[0] in trunk or sum(p in trunk for p in parents) != 1):
            continue
        if len(parents) != 2:
            octopus += 1
        elif commit in on_base or parents[0] in on_base or parents[1] in on_base:
            found.append((commit, parents[0], parents[1]))
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


def both_sides(repo, parents):
    """The paths that differ from the merge base on each parent, or None when the parents share no merge base."""
    rc, out, _ = run_git(repo, ["merge-base"] + list(parents))
    if rc:
        return None
    mb = out.decode("utf-8", "replace").strip()
    sides = []
    for parent in parents:
        names = read_git(repo, ["diff", "--name-only", "--no-renames", "-z", mb, parent])
        sides.append({n for n in names.split("\0") if n})
    return sides[0] & sides[1]


def check_args(since, top):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", since):
        raise Failure("--since must be YYYY-MM-DD, got %r" % since)
    try:
        datetime.date.fromisoformat(since)
    except ValueError:
        raise Failure("--since %s is not a real calendar date" % since)
    if top < 1:
        raise Failure("--top must be 1 or more, got %d" % top)


def check_whole_history(repo):
    shallow = read_git(repo, ["rev-parse", "--is-shallow-repository"]).strip()
    if shallow == "true":
        raise HistoryCut("history is cut at depth (shallow clone); counts are a lower bound")
    if shallow != "false":
        # Reported as unknown: a read that could not run never reads as a whole history.
        raise HistoryCut("cannot read whether the history is cut at depth (git said %r); counts are a lower bound"
                         % shallow)


def default_base(repo):
    """origin/main when the remote ref exists, else main: a clone's local main can lag the remote and miss merges."""
    rc, _, err = run_git(repo, ["rev-parse", "--verify", "--quiet", "refs/remotes/origin/main^{commit}"])
    if rc == 0:
        return "origin/main"
    if rc == 1:
        return "main"
    raise Failure("git rev-parse failed (%d): %s" % (rc, err or "no message"))


def report(repo, since, base, top, exposure=False, into_branches=False, list_merges=False):
    started = time.monotonic()
    check_args(since, top)
    check_version()
    check_whole_history(repo)
    base = base or default_base(repo)
    base_sha = read_git(repo, ["rev-parse", "--verify", base + "^{commit}"]).strip()
    found, octopus, off_base = merges_since(repo, since, base, into_branches)
    objects = os.path.abspath(read_git(repo, ["rev-parse", "--path-format=absolute", "--git-path", "objects"]).strip())
    counts, exposed, conflicted, unknown, starts, listed = {}, {}, 0, 0, 0, []
    scratch = tempfile.mkdtemp(prefix="conflict-hotspots-")
    try:
        env = git_env(scratch, objects)
        for commit, *parents in found:
            starts += 1
            if exposure:
                for path in both_sides(repo, parents) or ():
                    exposed[path] = exposed.get(path, 0) + 1
            verdict, paths = replay(repo, parents, env)
            if verdict == "conflict":
                conflicted += 1
                listed.append("merge %s %s" % (commit[:9], " ".join(sorted(set(paths)))))
                for path in set(paths):
                    counts[path] = counts.get(path, 0) + 1
            elif verdict == "unknown":
                unknown += 1
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    replayed = len(found)
    rate = 100.0 * conflicted / replayed if replayed else 0.0
    lines = ["base: %s %s" % (base, base_sha[:9]), "merges replayed: %d" % replayed, "merges conflicted: %d" % conflicted, "merges unknown: %d" % unknown,
             "conflict rate: %.1f%%" % rate,
             "merges not replayed: %d (octopus %d, off base %d)" % (octopus + off_base, octopus, off_base)]
    for path, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top]:
        lines.append("%d/%d %s" % (count, exposed.get(path, 0), path) if exposure else "%d %s" % (count, path))
    if list_merges:
        lines.extend(listed)
    lines.append("cost: merge-trees %d, wall %.1f s" % (starts, time.monotonic() - started))
    lines.append("caveat: a replay is what git finds now, not what the author resolved by hand, rerere or a merge option")
    lines.append("caveat: squash and rebase merges leave no merge commit, so they are absent")
    lines.append("caveat: refs walked: all")
    return lines


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", required=True, help="count merges committed on or after this date, YYYY-MM-DD only")
    ap.add_argument("--base", default=None,
                    help="the ref whose history a merge must touch (default origin/main when it exists, else main)")
    ap.add_argument("--top", type=int, default=20, help="file rows to print (default 20)")
    ap.add_argument("--repo", default=".", help="the repo to read (default the current folder)")
    ap.add_argument("--exposure", action="store_true",
                    help="rows read conflicts/exposure; adds three git starts per replayed merge")
    ap.add_argument("--into-branches", action="store_true",
                    help="count only merges of the base into a branch; adds one rev-list --first-parent")
    ap.add_argument("--list", action="store_true", help="after the file rows, one line per conflicted merge")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        lines = report(args.repo, args.since, args.base, args.top, args.exposure, args.into_branches, args.list)
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
