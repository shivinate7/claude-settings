"""The guard's branch-worktree family: branch delete and worktree remove/prune.

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import shlex

from guard_core import (
    basename, branch_is_empty, clone_worktrees, git_calls, long_flag_abbrev, path_is_inside,
    resolve_default_base,
)


BRANCH_DELETE_FLAGS = {"-d", "-D", "--delete"}
HEADS_PREFIX = "refs/heads/"


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

# Two worktrees never hold one branch. Git 2.43 refuses a plain `checkout x` of a branch another
# worktree holds, but lets `checkout -B x` and `switch -C x` re-point it with no warning, and a
# commit in either tree then moves the branch under the other tree. The forms this rule reads:
#   `checkout -B <name>`, `switch -C <name>` (also `--force-create`): refused when another worktree holds <name>.
#   `worktree add -f|--force`: refused when another worktree holds the branch the add would take.
#   `checkout|switch --ignore-other-worktrees`: refused with any branch, so no list is read.
#   `update-ref [-d] refs/heads/<name> ...`: refused when another worktree holds <name>. Git checks no worktree
#     for a ref write, so a move or delete leaves the holder's index at the old commit.
#   `symbolic-ref HEAD refs/heads/<name>`: refused when another worktree holds <name>, since the running tree
#     would then hold it too. A `symbolic-ref HEAD` with no target only reads, and passes.
# `update-ref --stdin` names its refs on stdin, which the guard cannot read, so it passes.
# Any other call, a plain `checkout x` and an unforced add included, is git's own refusal to make.
# The list is read once, only for a refused form; a read that fails refuses.
TWO_WORKTREES_REFUSE_REASON = (
    "Rule (shared trees): another worktree of this clone holds this branch, or the call turns off "
    "git's check that no two worktrees hold one branch. `update-ref` and `symbolic-ref HEAD` write "
    "the branch with no such check. A commit in either tree then moves the "
    "branch under the other tree, whose files stay at the old commit, and a commit there reverts "
    "the other tree's work with a diff that looks like a normal edit. "
    "Remedy: in your own worktree, run `git -C <own worktree> checkout --detach origin/<branch>`, "
    "commit there, then `git -C <own worktree> push origin HEAD:<branch>`. Name the worktree with "
    "-C, because a shell's cwd can reset to another checkout. To read the other tree, use "
    "`git -C <dir>`. To move the branch itself, move its ref, index and files together from the tree "
    "that holds it, as `git -C <holder> merge --ff-only <commit>`. `update-ref` moves the ref alone "
    "and leaves that tree's index at the old commit. If the holder's folder is gone but the list "
    "still shows its branch, `git worktree prune` drops that record. "
    "(decision two-worktrees-one-branch, two worktrees never hold one branch)"
)


def _ref_name(name: str) -> str:
    """A branch name as `refs/heads/` writes it, for a commit-ish that may spell the full or short ref."""
    for prefix in (HEADS_PREFIX, "heads/"):
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def _positionals(args, value_flags: str):
    """The words of `args` that are not options, in order. `value_flags` are the short options whose
    value is the rest of the cluster or the next word (`-m <msg>`). Words after `--` are all positional."""
    words = []
    take = False
    for index, arg in enumerate(args):
        if take:
            take = False
        elif arg == "--":
            words.extend(args[index + 1:])
            break
        elif arg.startswith("--") or (arg.startswith("-") and arg != "-"):
            if not arg.startswith("--"):
                for offset, char in enumerate(arg[1:], start=2):
                    if char in value_flags:
                        take = not arg[offset:]
                        break
        else:
            words.append(arg)
    return words


def _branch_of_ref(ref: str):
    """The branch name when `ref` spells a full `refs/heads/` ref, else None."""
    if ref.startswith(HEADS_PREFIX) and len(ref) > len(HEADS_PREFIX):
        return ref[len(HEADS_PREFIX):]
    return None


def two_worktrees_form(subcommand: str, args):
    """Return (ignore, names) for a call this rule reads, else None.

    `ignore` is True when the call carries `--ignore-other-worktrees`. `names` are the branch names
    the call would take: a `-B`/`-C` value, the branch a forced `worktree add` checks out, the
    `refs/heads/` ref an `update-ref` writes, or the branch a `symbolic-ref HEAD` points at. A
    call that is none of the forms, or a forced add that takes no branch, returns None.
    """
    if subcommand == "update-ref":
        words = _positionals(args, "m")
        name = _branch_of_ref(words[0]) if words else None
        return (False, [name]) if name else None
    if subcommand == "symbolic-ref":
        words = _positionals(args, "m")
        name = _branch_of_ref(words[1]) if len(words) >= 2 and words[0] == "HEAD" else None
        return (False, [name]) if name else None
    if subcommand in ("checkout", "switch"):
        reset, create = ("C", "c") if subcommand == "switch" else ("B", "b")
        ignore = False
        names = []
        take = skip = False
        for arg in args:
            if arg == "--":
                break
            if take:
                names.append(arg)
                take = False
            elif skip:
                skip = False
            elif arg.startswith("--"):
                if long_flag_abbrev(arg, "--ignore-other-worktrees", "--ignore-o"):
                    ignore = True
                elif subcommand == "switch" and long_flag_abbrev(arg, "--force-create", "--force-c"):
                    if "=" in arg:
                        names.append(arg.split("=", 1)[1])
                    else:
                        take = True
            elif arg.startswith("-") and arg != "-":
                # a short cluster: the first branch-name option ends it, its value is the rest or the next word
                for offset, char in enumerate(arg[1:], start=2):
                    if char in (reset, create):
                        value = arg[offset:]
                        if char == reset and value:
                            names.append(value)
                        elif char == reset:
                            take = True
                        else:
                            skip = not value
                        break
        return (ignore, names) if ignore or names else None
    if subcommand == "worktree" and args[:1] == ["add"]:
        force = detach = skip = take = False
        taken = []
        plain = []
        for index, arg in enumerate(args[1:], start=1):
            if take:
                taken.append(arg)
                take = False
            elif skip:
                skip = False
            elif arg == "--":
                plain.extend(args[index + 1:])
                break
            elif arg.startswith("--"):
                force = force or long_flag_abbrev(arg, "--force", "--f")
                detach = detach or long_flag_abbrev(arg, "--detach", "--d")
                skip = arg == "--reason"
            elif arg.startswith("-") and arg != "-":
                for offset, char in enumerate(arg[1:], start=2):
                    if char == "f":
                        force = True
                    elif char == "d":
                        detach = True
                    elif char in "bB":
                        if arg[offset:]:
                            taken.append(arg[offset:])
                        else:
                            take = True
                        break
            else:
                plain.append(arg)
        if not force:
            return None
        if taken:
            names = taken
        elif detach:
            return None
        elif len(plain) >= 2:
            names = [_ref_name(plain[1])]
        elif plain:
            names = [basename(plain[0].rstrip("/\\"))]
        else:
            return None
        return False, names
    return None


def two_worktrees_hit(segment: str, root: str) -> str:
    """Return the matched text when one segment is a refused form (see TWO_WORKTREES_REFUSE_REASON), else ''.

    ROOT is the tree the call runs in. Only a worktree other than ROOT's own counts as a holder, so
    the holder's own `checkout -B x` passes. The worktree whose root is the deepest one holding ROOT
    is the own tree, since a linked worktree can sit inside the primary checkout.
    """
    for subcommand, args in git_calls(segment):
        form = two_worktrees_form(subcommand, args)
        if form is None:
            continue
        ignore, names = form
        matched = " ".join(["git", subcommand] + list(args)).strip()
        if ignore:
            return matched
        trees = clone_worktrees(root)
        if trees is None:
            return matched   # a failed read refuses; [] is no clone at all, where git refuses the call itself
        own = max((tree for tree, _ref in trees if path_is_inside(root, tree)), key=len, default=None)
        held = {ref for tree, ref in trees if ref and tree != own}
        if any(HEADS_PREFIX + name in held for name in names):
            return matched
    return ""


# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
