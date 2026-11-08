"""The guard's branch-worktree family: branch delete and worktree remove/prune.

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import os
import shlex

import guard_core
from guard_core import (
    branch_is_empty, git_calls, resolve_default_base,
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

# ------------------------------------------------------------------ a held branch, reset in place
#
# `git checkout -B <b>` and `git switch -C <b>` move branch <b> to the start point. When ANOTHER
# worktree of the clone holds <b>, git 2.43 moves the ref under that worktree anyway: its files and
# index keep the old commit, so its next `git status` shows the reverse of the reset as staged work
# (lane #1777 incident, Nov 7, reproduced Nov 8). The worktree the command runs in is not that case:
# on git 2.43.0 its own -B resets cleanly, so its own branch passes (decision checkout-b-held-branch).
# The ref lives in the COMMON git directory, so the holder may be any worktree of the clone, and one
# `git worktree list --porcelain` names them all.
#
# THE READ RUNS ONLY FOR A -B/-C CALL. The text predicate comes first, so every other git command
# costs no process. FAIL OPEN: a list or run root that cannot be read judges nothing, this family's
# stance for an unread subject (see branch_delete_subject above).
#
# NOT HERE: the pointer checkout. Its reset of `main` onto `origin/main` is the session-start
# recovery path, and guard.py leaves that checkout to the pointer-head rule
# (decision recovery-independent-of-state). That exemption lives at the call site, because
# guard_pointer loads after this module.
FORCE_CREATE_FLAGS = {"checkout": ("-B",), "switch": ("-C", "--force-create")}


def forced_branch_names(subcommand: str, args):
    """Return the branch names a `git checkout -B` or `git switch -C` call would reset, else [].

    Reads the spaced form (`-B name`), the glued short form (`-Bname`) and, for switch, the long
    option with `=` or a space. Arguments after `--` name paths, so they are not read.
    """
    flags = FORCE_CREATE_FLAGS.get(subcommand)
    if not flags:
        return []
    names = []
    take = False
    for arg in args:
        if take:
            names.append(arg)
            take = False
            continue
        if arg == "--":
            break
        if arg in flags:
            take = True
            continue
        for flag in flags:
            if flag.startswith("--"):
                if arg.startswith(flag + "="):
                    names.append(arg[len(flag) + 1:])
            elif arg.startswith(flag) and not arg.startswith("--"):
                names.append(arg[len(flag):])
    return [name for name in names if name]


def held_branch_names(segment: str):
    """The branch names a segment's `checkout -B` and `switch -C` calls would reset. The cheap text
    read: no git process runs here."""
    names = []
    for subcommand, args in git_calls(segment):
        names.extend(forced_branch_names(subcommand, args))
    return names


def _same_path(left: str, right: str) -> bool:
    return os.path.normcase(os.path.realpath(left)) == os.path.normcase(os.path.realpath(right))


def sibling_held_branches(where: str):
    """Return the set of branches held by worktrees of `where`'s clone OTHER than the one `where`
    is in, or None when the list or the run root cannot be read."""
    root = guard_core._git(where, "rev-parse", "--show-toplevel")
    listing = guard_core._git(where, "worktree", "list", "--porcelain")
    if root is None or root.returncode != 0 or listing is None or listing.returncode != 0:
        return None
    own = root.stdout.strip()
    held = set()
    found_own = False
    path = ""
    for line in listing.stdout.splitlines():
        if line.startswith("worktree "):
            path = line[len("worktree "):].strip()
            found_own = found_own or _same_path(path, own)
        elif line.startswith("branch refs/heads/") and not _same_path(path, own):
            held.add(line[len("branch refs/heads/"):].strip())
    return held if found_own else None


def held_branch_hit(segment: str, where: str) -> str:
    """Return the matched text when one segment resets a branch a sibling worktree holds, else ''.
    One `rev-parse` and one `worktree list` read, only for a segment that holds a -B/-C call."""
    names = held_branch_names(segment)
    if not names:
        return ""
    held = sibling_held_branches(where)
    if not held:
        return ""
    if any(name in held for name in names):
        return segment.strip()
    return ""


HELD_BRANCH_REASON = (
    "Rule (shared trees): this call resets a branch that another working tree of this clone has "
    "checked out. Git moves the branch under that tree, whose files and index keep the old commit, "
    "so its next status shows the reset as staged changes and its work is easy to lose. "
    "Remedy: choose a new branch name for the reset, one no other working tree holds. Or do the reset "
    "inside the working tree that holds the branch, where the files move with it "
    "(decision checkout-b-held-branch, a reset must not move a branch under the tree that holds it)."
)

# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
