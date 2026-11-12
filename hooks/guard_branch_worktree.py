"""The guard's branch-worktree family: branch delete and worktree remove/prune.

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import shlex

from guard_core import (
    _git, basename, branch_is_empty, clone_worktrees, git_calls, long_flag_abbrev, path_is_inside,
    resolve_default_base,
)
from guard_push_delete import push_destinations, push_refspecs


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

# Two worktrees never hold one branch. Git 2.43 refuses a plain `checkout x` of a branch another
# worktree holds, but lets `checkout -B x` and `switch -C x` re-point it with no warning, and a
# commit in either tree then moves the branch under the other tree. The forms this rule reads:
#   `checkout -B <name>`, `switch -C <name>` (also `--force-create`): refused when another worktree holds <name>.
#   `worktree add -f|--force`: refused when another worktree holds the branch the add would take.
#   `checkout|switch --ignore-other-worktrees`: refused with any branch, so no list is read.
# Any other call, a plain `checkout x` and an unforced add included, is git's own refusal to make.
# The list is read once, only for a refused form; a read that fails refuses.
TWO_WORKTREES_REFUSE_REASON = (
    "Rule (shared trees): another worktree of this clone holds this branch, or the call turns off "
    "git's check that no two worktrees hold one branch. A commit in either tree then moves the "
    "branch under the other tree, whose files stay at the old commit, and a commit there reverts "
    "the other tree's work with a diff that looks like a normal edit. "
    "Remedy: in your own worktree, run `git -C <own worktree> checkout --detach origin/<branch>`, "
    "commit there, then `git -C <own worktree> push origin HEAD:<branch>`. Name the worktree with "
    "-C, because a shell's cwd can reset to another checkout. To read the other tree, use "
    "`git -C <dir>`. "
    "(decision two-worktrees-one-branch, two worktrees never hold one branch)"
)


def _ref_name(name: str) -> str:
    """A branch name as `refs/heads/` writes it, for a commit-ish that may spell the full or short ref."""
    for prefix in ("refs/heads/", "heads/"):
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def two_worktrees_form(subcommand: str, args):
    """Return (ignore, names) for a call this rule reads, else None.

    `ignore` is True when the call carries `--ignore-other-worktrees`. `names` are the branch names
    the call would take: a `-B`/`-C` value, or the branch a forced `worktree add` checks out. A
    call that is none of the forms, or a forced add that takes no branch, returns None.
    """
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
        if any("refs/heads/" + name in held for name in names):
            return matched
    return ""


# A new branch name never holds the word git. Claude Code's own worktree check refuses an agent's git
# command that names such a branch, so a lane that made one could not run its own checkout or push.
# The forms this rule reads, each one a creation of a name:
#   `checkout -b|-B|--orphan <name>`, `switch -c|-C|--create|--force-create|--orphan <name>`,
#   `branch <name>` (flags that only tune the create are skipped; any other flag is not read),
#   `worktree add -b|-B <name>`, and `push <remote> <spec>` whose spec and destination hold the word
#   and whose destination the clone holds neither as a local branch nor as a remote-tracking ref.
# A name that already exists keeps its name: a local branch, or a new local branch made from
# `<remote>/<same name>` (a remote branch brought local), for the first four forms; a local branch or a
# remote-tracking ref for the push. The word is the lowercase substring `git`, as the owner's rule reads it.
# A read that fails passes, since nothing then shows a creation. A push refusal has its own reason: the
# branch may sit on origin, never fetched. Neither remedy names a command of the refused form
# (rule git-remedy-never-names-target).
BRANCH_SLUG_REFUSE_REASON = (
    "Rule (branch-slug-no-git): this call creates a branch whose name holds the word git. Claude Code's "
    "own worktree check refuses any later command of yours that names such a branch, so the lane could "
    "not run its own checkout or push. "
    "Remedy: pick a slug without that word, such as the lane's topic in plain words, and create the branch "
    "under that name. A branch that already exists keeps its name. "
    "(decision branch-slug-no-git, a new branch name never holds the word git)"
)
BRANCH_SLUG_WORD = "git"
BRANCH_SLUG_PUSH_REFUSE_REASON = (
    "Rule (branch-slug-no-git): this push would create a branch whose name holds the word git, and this "
    "clone holds that name neither as a local branch nor as a remote-tracking ref. Claude Code's own "
    "worktree check refuses any later command of yours that names such a branch. "
    "Remedy: the branch may already exist on origin and never have been fetched, so fetch origin and "
    "retry the push. If it is still missing, the name is new: pick a slug without that word and push "
    "under that name. "
    "(decision branch-slug-no-git, a new branch name never holds the word git)"
)
# `git branch` flags that tune a create and take no value. Any other flag makes the call one this rule
# does not read: a delete, a rename, a copy, a list or an upstream edit.
_BRANCH_CREATE_FLAGS = {"-f", "--force", "-t", "--track", "--no-track", "-q", "--quiet", "--create-reflog"}


def new_branch_names(subcommand: str, args):
    """The branch names a checkout, switch, branch or worktree-add call would create, else [].

    The creates are the value of `-b`/`-B` (checkout, worktree add), `-c`/`-C`, `--create`,
    `--force-create` (switch) and `--orphan` (checkout, switch); the first plain word of a `branch`
    call that has no flag outside _BRANCH_CREATE_FLAGS. A short cluster ends at its first create
    letter, whose value is the rest of the word or the next word. This reads only the creates, where
    two_worktrees_form reads only the resets, so the two stay apart.
    """
    names = []
    if subcommand in ("checkout", "switch", "worktree"):
        if subcommand == "worktree":
            if args[:1] != ["add"]:
                return []
            args, letters = args[1:], "bB"
        else:
            letters = "cC" if subcommand == "switch" else "bB"
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
                flag = arg.split("=", 1)[0]
                if (long_flag_abbrev(arg, "--orphan", "--orp") and subcommand != "worktree") or (
                        subcommand == "switch" and (long_flag_abbrev(arg, "--create", "--cr")
                                                    or long_flag_abbrev(arg, "--force-create", "--force-c"))):
                    if "=" in arg:
                        names.append(arg.split("=", 1)[1])
                    else:
                        take = True
                elif subcommand == "worktree" and flag == "--reason":
                    skip = "=" not in arg
            elif arg.startswith("-") and arg != "-":
                for offset, char in enumerate(arg[1:], start=2):
                    if char in letters:
                        if arg[offset:]:
                            names.append(arg[offset:])
                        else:
                            take = True
                        break
        return names
    if subcommand == "branch":
        plain = []
        for arg in args:
            if arg.startswith("-"):
                if arg.split("=", 1)[0] not in _BRANCH_CREATE_FLAGS:
                    return []
            else:
                plain.append(arg)
        return plain[:1]
    return []


def _local_branch_exists(root: str, name: str):
    """True when `refs/heads/<name>` exists, False when it does not, None when git cannot say."""
    answer = _git(root, "show-ref", "--verify", "-q", "refs/heads/" + name)
    if answer is None or answer.returncode not in (0, 1):
        return None
    return answer.returncode == 0


def _remote_ref_exists(root: str, remote: str, name: str):
    """True when a remote-tracking ref holds `name`: under REMOTE when one is named, else under any
    remote. None when git cannot say."""
    if remote:
        answer = _git(root, "show-ref", "--verify", "-q", "refs/remotes/%s/%s" % (remote, name))
        if answer is None or answer.returncode not in (0, 1):
            return None
        return answer.returncode == 0
    answer = _git(root, "for-each-ref", "--format=%(refname)", "refs/remotes")
    if answer is None or answer.returncode != 0:
        return None
    return any(ref.split("/", 3)[-1] == name for ref in answer.stdout.splitlines())


def _made_from_remote_branch(root: str, name: str, args):
    """True when a word of ARGS is `<remote>/<name>` and that remote-tracking ref exists: the new local
    branch NAME is then a remote branch brought local, which is no new name. None when git cannot say."""
    for arg in args:
        if arg.endswith("/" + name) and not arg.startswith("-"):
            answer = _git(root, "show-ref", "--verify", "-q", "refs/remotes/" + arg)
            if answer is None or answer.returncode not in (0, 1):
                return None
            if answer.returncode == 0:
                return True
    return False


def _new_push_names(args, root: str):
    """The destinations of a push whose spec and destination both hold the word, for each of which the
    clone holds neither a local branch nor a remote-tracking ref. A push that names no refspec, a deletion, `--all`, `--mirror` and a
    tags-only push return []: push_refspecs reads none of them, and none names a branch to create."""
    named = push_refspecs(args)
    if named is None or not named[1]:
        return []
    remote, specs = named
    found = []
    for spec, dest in zip(specs, push_destinations(args, root)):
        # a glob, a tag or other non-branch ref, or a shell expansion (`$(git branch --show-current)`
        # holds the word as a command, not as a name) is no branch name this can read
        if not dest or dest.startswith("refs/") or any(char in spec + dest for char in "*$`("):
            continue
        if (BRANCH_SLUG_WORD in spec and BRANCH_SLUG_WORD in dest
                and _remote_ref_exists(root, remote, dest) is False
                and _local_branch_exists(root, dest) is False):
            found.append(dest)
    return found


def branch_slug_hit(segment: str, root: str):
    """Return (matched text, reason) when one segment creates a branch whose name holds the word git, else
    ('', ''). ROOT is the tree the call runs in. Git is asked only for a call that names the word, once per
    name. A push gets BRANCH_SLUG_PUSH_REFUSE_REASON, every other form BRANCH_SLUG_REFUSE_REASON."""
    for subcommand, args in git_calls(segment):
        if subcommand == "push":
            names, reason = _new_push_names(args, root), BRANCH_SLUG_PUSH_REFUSE_REASON
        else:
            names = [name for name in new_branch_names(subcommand, args)
                     if BRANCH_SLUG_WORD in name and _local_branch_exists(root, name) is False
                     and _made_from_remote_branch(root, name, args) is False]
            reason = BRANCH_SLUG_REFUSE_REASON
        if names:
            return " ".join(["git", subcommand] + list(args)).strip(), reason
    return "", ""


# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
