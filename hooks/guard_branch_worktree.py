"""The guard's branch-worktree family: branch delete, worktree remove/prune, and a commit from a
tree its branch moved under (stale-tree-commit).

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import os
import shlex

from guard_core import (
    _git, _segment_git_c_target, basename, branch_is_empty, dir_before_segment, git_calls,
    resolve_command, resolve_default_base, segment_tokens, shell_abs,
)


BRANCH_DELETE_FLAGS = {"-d", "-D", "--delete"}


def branch_delete_names(args):
    """Return the branch names a `git branch -d/-D` call would delete, else [].

    Any other `git branch` call (create, rename, list, `-a`, `-r`, ...) returns []. Only the
    exact delete flags mark the call: a short flag glued to others (`-df`) is a form this does
    not read, the same stance `checkout_names_a_path` above takes for its own flag set.
    """
    delete = False
    names = []
    for arg in args:
        if arg in BRANCH_DELETE_FLAGS:
            delete = True
            continue
        if arg.startswith("-"):
            continue
        names.append(arg)
    return names if delete else []


def branch_delete_subject(args, where: str):
    """The subject of `git branch -d/-D <name>...` is the work each named branch holds, read
    against the repository's own default branch. One name that holds the only copy makes the
    whole call's subject non-empty."""
    names = branch_delete_names(args)
    if not names:
        return True  # defensive: the matcher only sends real delete calls here
    base = resolve_default_base(where)
    if base is None:
        return None
    for name in names:
        empty = branch_is_empty(where, base, name)
        if empty is None:
            return None
        if empty is False:
            return False
    return True


def worktree_remove_forced(args) -> bool:
    """True when the call may carry force: `--force` or any prefix of it (`--f`, `--fo`), or a
    short cluster holding `f` (`-f`, `-ff`). Args are unquoted like segment_tokens does. An arg
    shlex cannot read counts as forced, so the note is kept."""
    for arg in args:
        try:
            tokens = shlex.split(arg)
        except ValueError:
            return True
        for tok in tokens:
            if tok == "--":
                return False
            if tok.startswith("--"):
                if len(tok) > 2 and "--force".startswith(tok):
                    return True
            elif tok.startswith("-") and "f" in tok[1:]:
                return True
    return False


# A branch deletion always refuses here, never asks: the branch ref lives in the COMMON git
# directory, the same one every worktree of the clone reads, so which checkout the delete runs
# from limits nothing about what is lost. This mirrors PUSH_DENY_REASON's own reasoning for the
# stash stack. The remedy hands over the one lossless fix as commands, so a session runs it and
# asks no one: the archive push puts the tip under a remote ref, which the remote-contains test
# reads. `archive/` keeps the copy out of the live branch names, and is the janitor's documented
# protected prefix. `<branch>` is a placeholder (rule git-remedy-never-names-target).
BRANCH_DELETE_DENY_REASON = (
    "Rule (shared trees): this branch holds work that exists nowhere else. It is not an "
    "ancestor of the repository's default branch, its patches are not already on that branch, "
    "and no remote ref contains it. Deleting it loses the only copy. "
    "Remedy: archive it on origin, then delete it. Run "
    "`git push origin <branch>:refs/heads/archive/<branch>`, then `git branch -D <branch>`, "
    "with <branch> the name you are deleting. If origin already holds that archive name at "
    "another tip, push to a new name such as `archive/<branch>-2`, never with force. Once the "
    "push succeeds, the work is kept, so this rule allows the delete. Nothing is lost, so this "
    "needs no question to the owner."
)
# A worktree removal always refuses here too. The tree it deletes is not the tree the command RUNS
# in, so the running checkout's own worktree-ness (the split every other arm in this rule reads)
# says nothing about whether the loss is confined to one lane: it is confined to the REMOVED
# tree's lane regardless, and that tree is never the one asking permission.
WORKTREE_REMOVE_DENY_REASON = (
    "Rule (shared trees): this working tree holds uncommitted or untracked work, is locked, or a "
    "live session still stands in it, and removing it puts nothing back. "
    "Remedy: commit or set aside the work on its own branch first, never a shared stash, "
    "unlock the tree if a lock holds it, and let a session standing in it finish or leave "
    "before the tree is removed."
)
# Pruning deletes no files: it drops the administrative record of a worktree whose directory is
# already gone. The worst case is clearing another session's record of a tree it still means to
# use, so this asks, never refuses, whatever the run location.
WORKTREE_PRUNE_ASK_REASON = (
    "Rule (shared trees): this drops the administrative record of a worktree whose directory no "
    "longer exists. It deletes no files, but the record it drops could belong to another "
    "session. "
    "The click in this prompt is the grant."
)

# ------------------------------------------------------------------ stale-tree-commit
#
# Decision stale-tree-commit, "The ruling". Read the per-worktree HEAD reflog FILE, not `git reflog
# HEAD`: with the worktree's own log missing, git falls back to the clone's logs, and the rule
# must read that as "no evidence". The git directory comes from the one `rev-parse` call; the log
# and the HEAD file are read as files, so the reflog and the detached check cost no git call.
# A commit makes at most five git calls: rev-parse, the ancestor test, what the branch changed
# (diff-tree), the staged paths (diff-index, not for named paths), and, for `-a` or named paths,
# one hash-object of the changed paths' work-tree copies.

# `commit` options that take a value in the next word (or glued to a short flag).
COMMIT_VALUE_FLAGS = {
    "-m", "-F", "-C", "-c", "-t", "--message", "--file", "--author", "--date", "--reuse-message",
    "--reedit-message", "--fixup", "--squash", "--cleanup", "--template", "--trailer",
    "--pathspec-from-file",
}
COMMIT_VALUE_LETTERS = "mFCct"   # a short cluster ends where one of these starts its value


def commit_scope(args):
    """(all, include, paths) of a `git commit` call's arguments. `all` is `-a`/`--all`; `include`
    is `-i`/`--include`; `paths` are the named pathspecs, which commit the work-tree copies."""
    every = include = False
    paths = []
    ended = False
    skip = False
    for arg in args:
        if skip:
            skip = False
            continue
        if arg == "-" or ended or not arg.startswith("-"):
            paths.append(arg)
        elif arg == "--":
            ended = True
        elif arg.startswith("--"):
            name = arg.split("=", 1)[0]
            if name == "--all":
                every = True
            elif name == "--include":
                include = True
            elif name in COMMIT_VALUE_FLAGS and "=" not in arg:
                skip = True
        else:
            for at, letter in enumerate(arg[1:], 1):
                if letter == "a":
                    every = True
                elif letter == "i":
                    include = True
                elif letter in COMMIT_VALUE_LETTERS:
                    skip = at == len(arg) - 1
                    break
                elif letter in "Su":   # optional value, always glued
                    break
    return every, include, paths


def _raw_pairs(where, args):
    """{path: (old_sha, new_sha)} of a raw `-z` diff command in `where`, or None when it failed.
    A missing side is "". Rename detection is off: the plumbing commands default to it off."""
    answer = _git(where, *args)
    if answer is None or answer.returncode != 0:
        return None
    parts = answer.stdout.split("\0")
    pairs = {}
    at = 0
    while at + 1 < len(parts):
        meta = parts[at]
        if not meta.startswith(":"):
            break
        fields = meta[1:].split()
        if len(fields) < 5:
            return None
        pairs[parts[at + 1]] = tuple("" if not sha.strip("0") else sha for sha in fields[2:4])
        at += 2
    return pairs


def _newest_entry(gitdir):
    """The newest HEAD reflog entry of a git directory as (old, new, message), or None for no
    log, an empty log or an unreadable line. Reads the tail of the file only."""
    try:
        with open(os.path.join(gitdir, "logs", "HEAD"), "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - 8192))
            tail = handle.read().decode("utf-8", "replace")
    except OSError:
        return None
    lines = [line for line in tail.split("\n") if line.strip()]
    if not lines:
        return None
    head, _, message = lines[-1].partition("\t")
    fields = head.split()
    if len(fields) < 2:
        return None
    return fields[0], fields[1], message.strip()


def _is_detached(gitdir):
    try:
        with open(os.path.join(gitdir, "HEAD"), encoding="utf-8", errors="replace") as handle:
            return not handle.read().startswith("ref:")
    except OSError:
        return True


def stale_tree_hit(where, args) -> str:
    """The stale path's name when a `git commit` with these arguments, run in `where`, would undo
    a change the branch made under this checkout (decision stale-tree-commit), else ''. Every
    read that fails passes."""
    first = _git(where, "rev-parse", "--absolute-git-dir", "--show-toplevel", "HEAD")
    if first is None or first.returncode != 0:
        return ""
    lines = [line.strip() for line in first.stdout.split("\n")]
    if len(lines) < 3 or not all(lines[:3]):
        return ""
    gitdir, top, head = lines[:3]
    if _is_detached(gitdir):
        return ""
    last = _newest_entry(gitdir)
    if last is None:
        return ""
    old, new, message = last
    if new != head:
        moved = new                       # the branch moved under this checkout
    elif message == "" or message.startswith("reset:"):
        moved = old                       # a move that leaves the index alone
    else:
        return ""                         # commit, pull, merge, rebase, checkout: the index synced
    if not moved.strip("0") or moved == head:
        return ""
    ancestor = _git(where, "merge-base", "--is-ancestor", moved, head)
    if ancestor is None or ancestor.returncode != 0:
        return ""                         # a squash or a reset back: not a move forward
    every, include, paths = commit_scope(args)
    # Named paths commit only those paths' work-tree copies, so the move is read for them alone.
    spec = ["--", *paths] if paths else []
    changed = _raw_pairs(where, ["diff-tree", "-r", "-z", "--no-abbrev", moved, head, *spec])
    if not changed:
        return ""
    if include or every or not paths:
        staged = _raw_pairs(top, ["diff-index", "--cached", "-r", "-z", "--no-abbrev", head])
        if staged is None:
            return ""
        for name, (_, index_sha) in staged.items():
            if name in changed and index_sha == changed[name][0]:
                return name
    if every or paths:
        # `-a` takes the work-tree copy of every path HEAD still tracks; a path the move added
        # is judged by the index read above.
        names = [name for name, (before, after) in changed.items() if after and (before or paths)]
        files = [name for name in names if os.path.isfile(os.path.join(top, name))]
        shas = []
        if files:
            hashed = _git(top, "hash-object", "--", *files)
            if hashed is None or hashed.returncode != 0:
                return ""
            shas = hashed.stdout.split()
        present = dict(zip(files, shas))
        for name in names:
            if present.get(name, "") == changed[name][0]:
                return name
    return ""


def stale_tree_commit_hit(segments, number: int, cwd: str, ends=()) -> str:
    """The stale path's name when `segments[number]` is a `git commit` that would undo what its
    branch changed under the tree it runs in, else ''. The tree is the shell's cwd after earlier
    `cd` steps (`dir_before_segment`), then the call's own `-C`. Only a commit makes a git call."""
    segment = segments[number]
    commits = [args for subcommand, args in git_calls(segment) if subcommand == "commit"]
    if not commits:
        return ""
    tokens = segment_tokens(segment)
    index = resolve_command(tokens) if tokens else None
    if index is None or basename(tokens[index]) not in ("git", "git.exe"):
        return ""
    where = dir_before_segment(segments, number, cwd, ends)
    named = _segment_git_c_target(tokens)
    if named is not None:
        where = None if any(mark in named for mark in "$%`") else shell_abs(named, where)
    if not where or not os.path.isdir(where):
        return ""
    return stale_tree_hit(where, commits[0])


STALE_TREE_REASON = (
    "Rule (stale tree): the branch moved under this checkout. Its index or files still hold old "
    "copies of files that the branch changed, so a commit here would undo the commits it missed, "
    "and the diff would look like a normal edit. "
    "Remedy: stop and report it to your orchestrator, which starts a fresh agent with your "
    "report. Commit nothing here (decision stale-tree-commit, a commit never runs from a tree its branch moved under)."
)

# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
