"""The guard's branch-worktree family: branch delete, worktree remove/prune, and a commit from a
tree its branch moved under (stale-tree-commit).

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import fnmatch
import os
import shlex
import stat

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
# one hash-object of the changed paths' work-tree copies. A dry run makes none.

# `commit` options that take a value in the next word (or glued to a short flag).
COMMIT_VALUE_FLAGS = {
    "-m", "-F", "-C", "-c", "-t", "--message", "--file", "--author", "--date", "--reuse-message",
    "--reedit-message", "--fixup", "--squash", "--cleanup", "--template", "--trailer",
    "--pathspec-from-file",
}
COMMIT_VALUE_LETTERS = "mFCct"   # a short cluster ends where one of these starts its value


def commit_scope(args):
    """(all, include, paths, only, dry) of a `git commit` call's arguments. `all` is `-a`/`--all`;
    `include` is `-i`/`--include`; `only` is `-o`/`--only`; `paths` are the named pathspecs, which
    commit the work-tree copies; `dry` is `--dry-run`, or a prefix of it that git accepts."""
    every = include = only = dry = False
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
            elif name == "--only":
                only = True
            elif len(name) >= 4 and "--dry-run".startswith(name):
                dry = True
            elif name in COMMIT_VALUE_FLAGS and "=" not in arg:
                skip = True
        else:
            for at, letter in enumerate(arg[1:], 1):
                if letter == "a":
                    every = True
                elif letter == "i":
                    include = True
                elif letter == "o":
                    only = True
                elif letter in COMMIT_VALUE_LETTERS:
                    skip = at == len(arg) - 1
                    break
                elif letter in "Su":   # optional value, always glued
                    break
    return every, include, paths, only, dry


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


def _newest_entries(gitdir):
    """The newest two HEAD reflog entries of a git directory, oldest first, each (old, new,
    message). One entry when the log holds one or the earlier line is unreadable; [] for no log,
    an empty log or an unreadable newest line. Reads the tail of the file only."""
    try:
        with open(os.path.join(gitdir, "logs", "HEAD"), "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - 8192))
            tail = handle.read().decode("utf-8", "replace")
    except OSError:
        return []
    entries = []
    for line in [line for line in tail.split("\n") if line.strip()][-2:]:
        head, _, message = line.partition("\t")
        fields = head.split()
        entries.append((fields[0], fields[1], message.strip()) if len(fields) >= 2 else None)
    if not entries or entries[-1] is None:
        return []
    return entries if entries[0] is not None else entries[-1:]


def _moved_from(entries, head):
    """(X, reset_only). X is the commit this checkout's index may still be cut from, or "" for
    none (decision stale-tree-commit, step 1), judged from the newest two HEAD log entries.
    `reset_only` is True when a `reset:` entry alone gave X: the log writes the same message for
    `--soft` and `--hard`, so the caller counts only a copy equal to X's."""
    if not entries:
        return "", False
    old, new, message = entries[-1]
    before = entries[-2] if len(entries) > 1 else None
    if new != head:
        return new, False                 # the branch moved under this checkout
    if before and old != before[1]:
        return before[1], False           # a gap: it moved before the newest entry
    if before and message == "":
        return before[1], False           # update-ref: it leaves the index and the tree alone
    if before and message.startswith("reset:"):
        return before[1], True            # --soft keeps the old copies, --hard does not
    return "", False


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
    every, include, paths, only, dry = commit_scope(args)
    if dry:
        return ""                         # a dry run writes no commit
    first = _git(where, "rev-parse", "--absolute-git-dir", "--show-toplevel", "HEAD")
    if first is None or first.returncode != 0:
        return ""
    lines = [line.strip() for line in first.stdout.split("\n")]
    if len(lines) < 3 or not all(lines[:3]):
        return ""
    gitdir, top, head = lines[:3]
    if _is_detached(gitdir):
        return ""
    moved, reset_only = _moved_from(_newest_entries(gitdir), head)
    if not moved.strip("0") or moved == head:
        return ""
    ancestor = _git(where, "merge-base", "--is-ancestor", moved, head)
    if ancestor is None or ancestor.returncode != 0:
        return ""                         # a squash or a reset back: not a move forward
    include = include and not only
    # The copy the commit records per path: the index's, except that `-a` takes the work tree's
    # for each path the index tracks, and named paths take the work tree's. `-i` with paths takes
    # the index for every path and the work tree for the named ones.
    from_index = not paths or include
    # Without `-i`, only the named paths are recorded, so the move is read for them alone. With
    # `-i` the index decides every path, so the move is read whole and the names matched here.
    spec = ["--", *paths] if paths and not include else []
    changed = _raw_pairs(where, ["diff-tree", "-r", "-z", "--no-abbrev", moved, head, *spec])
    if not changed:
        return ""
    staged = {}
    if from_index:
        staged = _raw_pairs(top, ["diff-index", "--cached", "-r", "-z", "--no-abbrev", head])
        if staged is None:
            return ""
    reads = []                            # the paths whose recorded copy is the work tree's
    if paths and include:
        # bash reads `..` in a cd target by its text, realpath reads it through a link: normalize first.
        real_where, real_top = os.path.realpath(os.path.normpath(where)), os.path.realpath(top)
    for name, (_, after) in changed.items():
        if paths:
            reads_it = not include or _named_by(name, paths, real_where, real_top)
        elif every:
            reads_it = staged[name][1] != "" if name in staged else after != ""
        else:
            reads_it = False
        if reads_it:
            reads.append(name)
    # A symlink or a gitlink (a submodule's folder) in the work tree passes: hash-object would hash
    # the link's target file, or fail on the folder, not the copy git records.
    files, odd = [], set()
    for name in reads:
        try:
            mode = os.lstat(os.path.join(top, name)).st_mode
        except OSError:
            continue                      # a file the work tree lacks records as deleted
        if stat.S_ISREG(mode):
            files.append(name)
        else:
            odd.add(name)
    shas = {}
    if files:
        hashed = _git(top, "hash-object", "--", *files)
        if hashed is None or hashed.returncode != 0:
            return ""
        shas = dict(zip(files, hashed.stdout.split()))
    for name, (before, after) in changed.items():
        if name in odd:
            continue
        if name in reads:
            copy = shas.get(name, "")     # a file the work tree lacks records as deleted
        else:
            copy = staged[name][1] if name in staged else after   # diff-index lists only differences
        if (copy == before) if reset_only else (copy != after):
            return name
    return ""


def _named_by(name, paths, where, top):
    """True when a literal or glob pathspec in PATHS (relative to WHERE) covers the top-relative
    NAME. Used only for `-i` with paths. A path that resolves to the top folder names every path.
    The caller passes WHERE and TOP as real paths: git's top is a real path, and the cwd may reach
    it through a symlink (macOS /var -> /private/var). The paths stay as typed."""
    for path in paths:
        full = os.path.relpath(os.path.join(where, path), top).replace(os.sep, "/")
        if full == "." or name == full or name.startswith(full.rstrip("/") + "/") or fnmatch.fnmatchcase(name, full):
            return True
    return False


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
