"""The guard's pointer family: the pointer checkout's HEAD.

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import os
import re

import guard_core
from guard_core import (
    GIT_CHECKOUT_TAKES_NAME, PATH_EXTENSION, PATH_PREFIX, _absolute, _run_dir, git_calls,
)


# ------------------------------------------------------------------ the pointer checkout's HEAD
#
# `<config>/lint/*`, `<config>/hooks/*` and `<config>/agents/*` are PER-FILE SYMLINKS into one
# checkout: the one the owner's global rules file names on its `@<path>` line. That checkout's HEAD
# decides WHICH COPY of the rules and of the gates every session on this machine runs. The owner
# has stated the rule: that checkout's HEAD is always `main`.
#
# THE POINTER LINE IS PARSED HERE RATHER THAN IMPORTED. The three other readers of that line are
# all shell: `install.sh`'s `pointer_dir`, the settings refresh hook, and `hooks/session_start.sh`.
# No import crosses from shell into Python, so a copy is forced, not chosen. This is the one Python
# copy, and it keeps the same three steps those three take: read the global rules file under
# `${CLAUDE_CONFIG_DIR:-$HOME/.claude}`, take the first `@<path>` line, and expand a leading `~/`
# against the home directory. It reads the file with `utf-8-sig`, because the Windows installer
# writes that file and a byte order mark there would hide the first line from a `^@` match.
#
# THE PREDICATE IS THE ACT, NOT THE SPELLING (docs/decisions/predicate-is-the-act.md, judge the act).
# The act is "HEAD in that one checkout stops naming `main`". `checkout` and `switch` are the two
# subcommands that take it.
#
#   fires   `checkout <branch>` and `switch <branch>`, including the `-` shorthand
#           `checkout -b|-B|--orphan <name>` and `switch -c|-C|--orphan <name>`
#           `checkout --detach` and `switch --detach|-d`, which leave no branch named at all
#   passes  a move whose one target is `main`. That call RESTORES the invariant this rule
#           protects, and it is how a checkout left on a branch gets repaired. A deny there would
#           wall off the only repair, which is the "fix the cause" failure in miniature.
#   passes  a path operation: `--`, `--ours`, `--theirs`, `--patch`, `--pathspec-from-file`, or one
#           plain argument shaped like a file. HEAD does not move, and rule 1 governs those calls
#           unchanged.
#   passes  the same commands in EVERY OTHER TREE, a linked worktree of this same clone included.
#           A worktree has its own HEAD and its own top level, so it swaps no live gate.
#
# NOT ON THIS LIST, on purpose. `git reset --hard <commit>` and `git merge` move the commit that
# HEAD resolves to while leaving the checkout on the SAME BRANCH, so neither swaps the branch whose
# copy of the gates runs, and `reset --hard` is already rule 1's subject. `git branch -f` cannot
# touch a checked-out branch, because git itself refuses it. `git worktree add` moves no HEAD in
# this checkout at all, and it is this rule's remedy.
#
# FAIL OPEN, EVERY STEP. A missing global rules file, a file carrying no `@<path>` line, a line
# naming a directory that is gone, and a git that cannot answer the top level each mean the rule
# does not fire. A guard must never brick a session.
POINTER_READ_MAX = 64 * 1024
POINTER_LINE = re.compile(r"^@(.+)/CLAUDE\.md[ \t]*$", re.MULTILINE)

# `switch` spells the new-branch options differently from `checkout`, and it takes `-d` for a
# detach where `checkout` takes only the long form.
SWITCH_TAKES_NAME = {"-c", "-C", "--orphan"}
CHECKOUT_DETACH_FLAGS = {"--detach"}
SWITCH_DETACH_FLAGS = {"--detach", "-d"}
# Options that make a `checkout` a PATH operation whatever its remaining arguments look like. A
# bare name after one of these is a file, not a branch.
CHECKOUT_PATH_FLAGS = {"--ours", "--theirs", "--patch", "-p", "--overlay", "--no-overlay"}
HEAD_MOVE_SUBCOMMANDS = ("checkout", "switch")

POINTER_HEAD_REASON = (
    "Rule (pointer checkout): this one checkout is what the owner's global rules point at, and "
    "every session on this machine runs its hooks, its lint and its agents through symlinks into "
    "it. Moving its HEAD off main makes unreviewed work the live gate for every session, "
    "including the sessions reviewing that work. Its HEAD stays main. "
    "Remedy: build the change in a worktree of your own. Call the EnterWorktree tool to make one "
    "on a new branch, because git refuses a worktree for a branch this checkout already holds."
)


def pointer_checkout() -> str:
    """Return the normalized, resolved directory the global rules file points at, or ''.

    Returns '' on every unreadable step, so an unknown pointer makes the rule silent.
    """
    try:
        with open(os.path.join(guard_core.config_dir(), "CLAUDE.md"), encoding="utf-8-sig") as handle:
            text = handle.read(POINTER_READ_MAX)
    except Exception:
        return ""
    match = POINTER_LINE.search(text)
    if not match:
        return ""
    target = match.group(1).strip()
    if target.startswith("~/") or target.startswith("~\\"):
        target = os.path.join(os.path.expanduser("~"), target[2:])
    target = os.path.expandvars(os.path.expanduser(target))
    if not os.path.isdir(target):
        return ""
    return os.path.normcase(os.path.realpath(target))


# `--git-dir` NAMES WHERE HEAD LIVES. From an unrelated
# directory, `git --git-dir=<X>/.git switch other` moved HEAD inside X from `main` to `other`, with
# no `-C`, no `cd` and no `--work-tree` anywhere on the line. The git directory alone decides whose
# HEAD a call moves, so the pointer rule reads it and the shared-tree rule does not.
GIT_DIR_RE = re.compile(r"--git-dir(?:=|\s+)(['\"]?)([^'\";&|\s]+)\1")


def head_root(cmd: str, shell_cwd: str) -> str:
    """Return the directory whose HEAD the command would move.

    A `--git-dir` on the line names that HEAD directly, wherever the call runs from. With none,
    the HEAD that moves belongs to the tree the call RUNS in.
    """
    run_dir = _run_dir(cmd, shell_cwd)
    match = GIT_DIR_RE.search(cmd)
    if not match:
        # NOT `command_root`. A `--work-tree` retargets the FILES and leaves HEAD where the call
        # runs, so reading it here would name the wrong checkout's HEAD.
        return run_dir
    return _absolute(match.group(2), run_dir)


def git_dir_of(where: str) -> str:
    """Return the normalized, resolved git directory that holds `where`'s own HEAD, or ''.

    `--absolute-git-dir` answers the PER-WORKTREE directory, never the shared common one, which
    is the point: HEAD is per worktree. A linked worktree of a clone therefore answers
    `<repo>/.git/worktrees/<name>` and never `<repo>/.git`, so it is not mistaken for its primary
    checkout. A path that is already a git directory answers itself.
    """
    if not where:
        return ""
    if os.path.isdir(where):
        answer = guard_core._git(where, "rev-parse", "--absolute-git-dir")
        if answer is not None and answer.returncode == 0 and answer.stdout.strip():
            return os.path.normcase(os.path.realpath(answer.stdout.strip()))
        return ""
    return ""


def in_pointer_checkout(root: str) -> bool:
    """True when the HEAD at `root` is the POINTER CHECKOUT'S OWN HEAD.

    The comparison is between GIT DIRECTORIES read from git, never between the two paths as
    written. That is what makes each of these come out right:

      a subdirectory of the pointer checkout    same git directory, so it counts
      `--git-dir=<pointer>/.git` from anywhere  the git directory IS the pointer's, so it counts
      a linked worktree of the same clone       its own `<repo>/.git/worktrees/<name>`, so it
                                                does NOT count: its HEAD is its own
      a `--git-dir` naming a directory that is  unreadable, so the rule does not fire
      gone
    """
    pointer = pointer_checkout()
    if not pointer:
        return False
    mine = git_dir_of(root)
    if not mine:
        # A `--git-dir` may name the git directory itself, which is not a work tree git can be
        # asked about. Compare it directly in that case.
        if root and os.path.isdir(root):
            mine = os.path.normcase(os.path.realpath(root))
        if not mine:
            return False
    theirs = git_dir_of(pointer)
    if not theirs:
        return False
    return mine == theirs


def head_move_target(subcommand: str, args) -> str:
    """Return the arguments of a `git checkout` or `git switch` call that moves HEAD off the
    branch it is on, else ''. A move whose one target is `main` returns '' as well.
    """
    if subcommand not in HEAD_MOVE_SUBCOMMANDS:
        return ""
    if "--" in args:
        return ""
    switching = subcommand == "switch"
    takes_name = SWITCH_TAKES_NAME if switching else GIT_CHECKOUT_TAKES_NAME
    detach_flags = SWITCH_DETACH_FLAGS if switching else CHECKOUT_DETACH_FLAGS
    plain = []
    new_branch = False
    detached = False
    take_name = False
    for arg in args:
        # A lone `-` is the previous-branch shorthand, an argument and not an option.
        if arg.startswith("-") and arg != "-":
            if not switching and (
                arg in CHECKOUT_PATH_FLAGS or arg.startswith("--pathspec-from-file")
            ):
                return ""
            if arg in detach_flags:
                detached = True
            take_name = arg in takes_name
            continue
        if take_name:
            take_name = False
            new_branch = True
            continue
        plain.append(arg)
    matched = " ".join(args).strip()
    if new_branch or detached:
        return matched
    if len(plain) != 1:
        # None names a branch, or two name a start point plus a path, which rule 1 governs.
        return ""
    target = plain[0]
    if (
        PATH_PREFIX.match(target)
        or PATH_EXTENSION.search(target)
        or "\\" in target
        or target.endswith("/")
    ):
        return ""
    if target == PROTECTED_BASE:
        return ""
    return matched


PROTECTED_BASE = "main"


def pointer_head_hit(segment: str, root: str) -> str:
    """Return the matched text when one segment moves HEAD in the pointer checkout, else ''.

    The cheap text predicate runs first, so the two git reads happen only for a call that would
    move HEAD somewhere.
    """
    for subcommand, args in git_calls(segment):
        target = head_move_target(subcommand, args)
        if not target:
            continue
        if in_pointer_checkout(root):
            return ("git " + subcommand + " " + target).strip()
    return ""

# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
