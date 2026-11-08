"""The guard's branch-worktree family: branch delete and worktree remove/prune.

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import shlex

from guard_core import (
    _git, branch_is_ancestor, branch_is_empty, branch_on_remote, design_files,
    resolve_default_base,
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


# A design file on a branch's tip is the only copy of that file when no ref on origin holds the tip
# (the incident: an unmerged design branch deleted, with its picked mockup). A local delete leaves
# origin's copy, so it is judged only when the default branch cannot be read (rule shared-trees-
# archive-then-delete). A remote delete removes origin's copy, so a tip that is on the default
# branch, or that any `archive/*` ref on origin holds, keeps the file; a tip it cannot read asks.
# The tip is the last-fetched tracking ref. `<branch>` is a placeholder (rule git-remedy-never-names-target).
_ARCHIVE_REMEDY = (
    "Remedy: push the branch to an archive name first, `git push origin "
    "<branch>:refs/heads/archive/<branch>`, with <branch> the branch you are deleting, never "
    "with force. Once the archive holds the tip, this rule allows the delete. Nothing is lost, "
    "so this needs no question to the owner."
)
DESIGN_DELETE_REFUSE_REASON = (
    "Archive before delete (rule shared-trees-archive-then-delete): the tip of this remote branch holds a file under "
    "the design folder that the default branch lacks, and no archive branch on origin holds that "
    "tip. Deleting the branch loses the file. " + _ARCHIVE_REMEDY
)
DESIGN_DELETE_ASK_REASON = (
    "Archive before delete (rule shared-trees-archive-then-delete): a read that says whether this "
    "branch's design file survives the delete did not answer (the branch tip, its design files, "
    "the archive refs or the default branch). " + _ARCHIVE_REMEDY
)


def _tip_of(where: str, *refs):
    """The commit id of the first of `refs` that resolves, else None (none does, or git failed)."""
    for ref in refs:
        answer = _git(where, "rev-parse", "--verify", "--quiet", ref + "^{commit}")
        if answer is None:
            return None
        if answer.returncode == 0 and answer.stdout.strip():
            return answer.stdout.strip()
    return None


def _is_tag(where: str, name: str) -> bool:
    """True when `refs/tags/<name>` resolves. False when it does not, or git cannot answer."""
    answer = _git(where, "rev-parse", "--verify", "--quiet", "refs/tags/" + name)
    return answer is not None and answer.returncode == 0


def design_branch_delete_ask(args, where: str, folder) -> bool:
    """True when a `git branch -d/-D` names a branch whose tip holds a design file, no remote ref
    holds that tip, and the default branch is unreadable. Callers send only a call whose subject
    read came back unreadable. An unread design folder (FOLDER None) asks for any named branch,
    since no design file can be told from none. A read that fails here is False: the unread note
    stays."""
    if not folder:
        # An unread design folder cannot tell a design file from none: it asks, never allows.
        return bool(branch_delete_names(args))
    for name in branch_delete_names(args):
        tip = _tip_of(where, "refs/heads/" + name)
        if tip is None:
            continue
        files = design_files(where, tip, folder, resolve_default_base(where))
        if files and branch_on_remote(where, tip) is False:
            return True
    return False


def design_push_delete_verdict(where: str, remote: str, names, folder) -> str:
    """'deny', 'ask' or '' for a push that deletes `names` on `remote`. A name counts when its tip
    (the remote-tracking ref, else the local branch) is not on the default branch, holds a file
    under `folder` that the default branch lacks, and no other ref on the remote holds the tip. A
    ref this push deletes is no holder, so an archive branch is not its own holder. A tip that
    does not resolve, a failed read of the design files or of the remote refs, an
    unreadable default branch and an unread design folder (FOLDER None) each ask: the delete
    removes origin's copy, so an unread tip never allows. Only a delete pushed to `origin` is judged; another remote keeps the other push rules.
    A name with no tip that is a local tag is skipped: a tag is not a branch. The default branch is
    read at the first resolved tip, so a name with no tip starts no git beyond the tip and tag
    lookups."""
    if remote != "origin":
        return ""
    if not folder:
        # An unread design folder cannot tell a design file from none: it asks, never allows. A name
        # that is only a local tag is not a branch, so it alone does not ask.
        for name in names:
            tip = _tip_of(where, "refs/remotes/%s/%s" % (remote, name), "refs/heads/" + name)
            if tip is not None or not _is_tag(where, name):
                return "ask"
        return ""
    base = None
    base_read = False
    verdict = ""
    # Every ref this push deletes is no holder of a tip: it is gone once the push lands.
    deleted = {"refs/remotes/%s/%s" % (remote, name) for name in names}
    for name in names:
        tip = _tip_of(where, "refs/remotes/%s/%s" % (remote, name), "refs/heads/" + name)
        if tip is None and _is_tag(where, name):
            continue
        if tip is None:
            verdict = "ask"
            continue
        if not base_read:
            base, base_read = resolve_default_base(where, remote), True
        if base is not None and branch_is_ancestor(where, base, tip):
            continue
        files = design_files(where, tip, folder, base)
        if files is None:
            verdict = "ask"
            continue
        if not files:
            continue
        archived = branch_on_remote(where, tip, "refs/remotes/" + remote, deleted)
        if archived:
            continue
        if archived is None or base is None:
            verdict = "ask"
        else:
            return "deny"
    return verdict


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

# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
