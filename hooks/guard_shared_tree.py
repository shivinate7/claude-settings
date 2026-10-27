"""The guard's shared-tree family: stash, reset, restore, checkout, clean and the subject read.

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import os
import re
import tempfile

import guard_core
from guard_core import (
    GIT_CHECKOUT_TAKES_NAME, PATH_EXTENSION, PATH_PREFIX, REDIRECTION, _inside_work_tree,
    _segment_git_c_target, basename, git_calls, long_flag_abbrev, pathspec_from_file_flag, porcelain,
    resolve_command,
    segment_tokens, split_segments, stash_stack, worktree_prune_subject, worktree_remove_subject,
)
from guard_branch_worktree import (
    branch_delete_names, branch_delete_subject,
)


def checkout_names_a_path(args, root: str = "") -> str:
    """Return the matched text when a `git checkout` names a path, else ''.

    Also matched: a forced switch (`-f`, `--force`), a pathspec file, and, when `root` is given,
    a lone bare operand that is a folder under `root` (git reads it as a path)."""
    if "--" in args:
        return " ".join(["--"] + args[args.index("--") + 1:]).strip()
    plain = []
    take_name = False
    for arg in args:
        if arg.startswith("-"):
            take_name = arg in GIT_CHECKOUT_TAKES_NAME
            continue
        if take_name:
            take_name = False
            continue
        plain.append(arg)
    if len(plain) >= 2:  # a start point plus a path
        return " ".join(plain)
    for arg in plain:
        if (
            PATH_PREFIX.match(arg)
            or PATH_EXTENSION.search(arg)
            or "\\" in arg
            or arg.endswith("/")
        ):
            return arg
    if root and len(plain) == 1 and os.path.isdir(os.path.join(root, plain[0])):
        return plain[0]
    for arg in args:
        if arg in ("-f", "--force") or pathspec_from_file_flag(arg):
            return arg
    return ""


def clean_deletes_files(args) -> bool:
    """True when `git clean` carries the force flag that makes it delete."""
    for arg in args:
        if arg == "--force":
            return True
        if arg.startswith("--"):
            continue
        if arg.startswith("-") and "f" in arg:
            return True
    return False


STASH_READ_ACTIONS = {"list", "show", "help"}
# `push`, `save` and a bare `git stash` PUT work onto the stack. They take it from the working
# tree, so the working tree is their subject. Every other action that is not a read TAKES an
# entry off the stack, so the stack is theirs.
STASH_TREE_ACTIONS = {"push", "save"}


# Every action word git's `stash` knows.
STASH_ACTIONS = {"list", "show", "drop", "pop", "apply", "clear", "branch", "push", "save",
                 "create", "store", "export", "import"}


def stash_option_takes_next_word(arg: str) -> bool:
    """True when a `git stash push` option takes the NEXT word as its value.

    The options that take one are the two in git's synopsis: `-m`/`--message <msg>` and
    `--pathspec-from-file <file>`. Git reads `-qm list`, `-um show`,
    `--mess list` as a push with the message `list` or `show`. So a short cluster ending in `m`
    takes the next word, a long option takes it by any prefix git accepts, and a value glued on
    (`-mfoo`, `--message=x`) takes nothing more. `-U`/`--unified` and `--inter-hunk-context`
    (diff options for `-p`, not in the synopsis) are left out on purpose: their value is a
    number, and a word wrongly read as an action word fails closed, as a push.
    """
    if arg.startswith("--"):
        if "=" in arg:
            return False
        return (long_flag_abbrev(arg, "--message", "--m") or pathspec_from_file_flag(arg))
    return arg.startswith("-") and arg.find("m") == len(arg) - 1


def stash_action(args) -> str:
    """Return the stash call's own action word, or 'push' when the call names none.

    A bare `git stash`, `git stash -u`, `git stash -- <path>` and `git stash -m <msg>` all push,
    the same as `git stash push`. Options are skipped, and an option that takes a value skips its
    value too (stash_option_takes_next_word). The first word left is the action when git knows
    it. After `--` the call is a push, because a pathspec follows. A sole `-h` or `--help` is
    the action `help`, a read. Any other call with a help flag keeps its verdict.

    A plain word that is no known action is NOT a push in git: `git stash <path>` with no `--`
    is refused ("subcommand wasn't specified; 'push' can't be assumed", measured). The guard
    reads it as a push anyway, to fail closed, so the tree is judged and nothing falls through.

    No word is left unknown, so none lands on the stack side. What lands there is a KNOWN word
    that is not a read and not a push: pop, apply, drop, clear, branch, create, store, export and
    import. Git 2.55 lists `export` and `import` in `git stash -h`, so they are known words.
    """
    args = list(args)
    if args in (["-h"], ["--help"]):
        return "help"  # Owner ruling 2026-10-17: a sole help flag prints usage and reads nothing.
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            return "push"
        if arg.startswith("-"):
            i += 2 if stash_option_takes_next_word(arg) else 1
        else:
            return arg if arg in STASH_ACTIONS else "push"
    return "push"


def stash_takes_the_stack(args) -> bool:
    """True when a `git stash` call takes an entry OFF the shared stack.

    The predicate is the DIRECTION of the act, not a list of action words. A call reads the
    stack, puts work onto it, or takes an entry off it. `list` and `show` read. `push`, `save`
    and a bare `git stash` put work on. Every other action takes an entry off: `pop` and
    `branch` consume the entry they use, `drop` and `clear` destroy entries outright, and
    `apply` reads another session's work into this tree without that session's word. `create`,
    `store`, `export` and `import` touch the stack's entries or refs, so the stack is their
    subject too, and they fall on its side with the rest.

    A word that is no known action is a pathspec, which stash_action reads as a push. Only a
    known action word that is neither a read nor a push falls on the stack side, the side where
    a wrong answer costs another session its work.
    """
    action = stash_action(args)
    return action not in STASH_READ_ACTIONS and action not in STASH_TREE_ACTIONS


def stash_discards(args) -> bool:
    """True when a `git stash` call can lose work.

    `list` and `show` read the stash and change nothing, so they pass. Every other action can
    lose work, and the SUBJECT READ below decides whether this call would lose any.

    `apply` and `pop` count: the thing at risk is not this tree but the shared stack. The entry
    consumed may belong to another session, and a tree with nothing in it is exactly when that
    theft leaves no trace.
    """
    return stash_action(args) not in STASH_READ_ACTIONS


def reset_discards(args) -> bool:
    """True when a `git reset` call can overwrite the working tree with no way back.

    Only `--hard` rewrites tracked files in the working tree unconditionally (MEASURED against
    a real uncommitted change, 2026-09-17: it was gone after the reset). The default, with no
    flag and no paths, and `--soft`, `--mixed`, `--keep`, and `--merge` all leave the working
    tree alone or abort when a local change would be overwritten (MEASURED the same day: `git
    reset --keep` and `git reset --merge` both stopped with "error: Entry 'f.txt' not uptodate.
    Cannot merge." against a modified file, and the file kept its uncommitted line). A `reset`
    that names paths only ever touches the index, and git refuses to combine `--hard` with a
    path at all ("fatal: Cannot do hard reset with paths."), so no path form can lose the
    working tree either.
    """
    return "--hard" in args


def restore_discards(args) -> bool:
    """True when a `git restore` call writes the working tree.

    The working tree is the DEFAULT target `restore` writes to, so the bare form with neither
    flag overwrites it (MEASURED, 2026-09-17: an uncommitted line was gone after a plain `git
    restore f.txt`). `--worktree`, alone or together with `--staged`, does the same. `--staged`
    alone writes only the index and leaves the working tree file as it was (MEASURED the same
    day: the uncommitted line survived).
    """
    staged = "--staged" in args or "-S" in args
    worktree = "--worktree" in args or "-W" in args
    return worktree or not staged


def shared_tree_match(segment: str, root: str = ""):
    """Return (matched text, subcommand, arguments) for the first call in one segment that
    discards a working tree, else None.

    The subcommand and the arguments travel with the matched text because the SUBJECT READ
    below needs them. A matched text alone says what fired; only the arguments say what the
    call would take.
    """
    for subcommand, args in git_calls(segment):
        if subcommand == "stash":
            if stash_discards(args):
                return ("git stash " + " ".join(args)).strip(), subcommand, args
            continue
        if subcommand == "reset":
            if reset_discards(args):
                return ("git reset " + " ".join(args)).strip(), subcommand, args
            continue
        if subcommand == "restore":
            if restore_discards(args):
                return ("git restore " + " ".join(args)).strip(), subcommand, args
            continue
        if subcommand == "clean" and clean_deletes_files(args):
            return ("git clean " + " ".join(args)).strip(), subcommand, args
        if subcommand == "checkout":
            named = checkout_names_a_path(args, root)
            if named:
                return "git checkout " + named, subcommand, args
        if subcommand == "branch":
            names = branch_delete_names(args)
            if names:
                return ("git branch " + " ".join(args)).strip(), "branch-delete", args
            continue
        if subcommand == "worktree":
            action = args[0] if args else ""
            if action == "remove":
                matched = ("git worktree " + " ".join(args)).strip()
                return matched, "worktree-remove", args[1:]
            if action == "prune":
                if any(a in ("-n", "--dry-run") for a in args[1:]):
                    continue  # the call's own dry run is a read, never a discard
                matched = ("git worktree " + " ".join(args)).strip()
                return matched, "worktree-prune", args[1:]
            continue
    return None


def shared_tree_hit(segment: str) -> str:
    """Return the matched text when one segment discards a working tree, else ''."""
    match = shared_tree_match(segment)
    return match[0] if match else ""


# ------------------------------------------------------------------ reading the subject
#
# READ THE SUBJECT BEFORE REFUSING OVER IT. The rule above judges the ACT of a git call. This
# layer judges what the act would TAKE. A command that takes nothing destroys nothing, whichever
# checkout it runs in.
#
# MEASURED on 6e179ae with the real hook: `git reset --hard HEAD` in a CLEAN tree answered deny,
# though nothing was uncommitted, so nothing could be lost. The same call in a fresh `git init`
# repository under the session scratchpad answered deny too, though no other session can reach
# that repository.
#
# The subject is read WITH GIT, the same two reads git itself makes:
#
#   git status --porcelain   for every arm whose subject is the working tree: `reset --hard`,
#                            `restore` in the forms that write the worktree, `stash push`/`save`
#                            /bare, `checkout <path>`, and `clean -f`
#   git stash list           for every arm whose subject is the stack: every `stash` action that
#                            takes an entry off it, which is all of them but the two reads and
#                            the three that put work on
#
# An EMPTY subject is a PASS. There is nothing to take and nothing to destroy, and git itself
# errors on an empty stack. For `checkout <path>` and `restore <path>` the pass is PER PATH: the
# pathspec goes to `git status --porcelain -- <paths>`, so git resolves the path, the directory,
# the glob and the quoting, and an empty answer proves the write changes nothing. For `clean -f`
# the subject is the untracked part of that same output, plus the ignored part when `-x` or `-X`
# widens the delete to ignored files.
#
# A path-scoped read passes ONLY when the call's paths can be enumerated. `--pathspec-from-file`
# holds them in a file, so that form falls back to the whole tree instead of guessing.
#
# A DIRECTORY THAT IS NOT A GIT TREE IS NOT AN UNREADABLE SUBJECT. `_inside_work_tree` answers
# False there, and the rule keeps its old fail-closed deny: nothing was read, so nothing is
# proven. Only git failing to ANSWER is unreadable, which is arm 2 below.
#
# A CLEAN TREE PASSES A `reset --hard` ONLY AT `HEAD`, OR WITH NO TARGET AT ALL. A `reset --hard`
# can lose two different things, and the subject read covers only one of them.
#
#   uncommitted work  has no copy anywhere. `git status --porcelain` reports it, so an empty
#                     answer proves there is none to lose.
#   a commit          is lost differently. The BRANCH MOVES. Another session standing in that
#                     checkout is then on rewritten history, and the reflog that recovers the
#                     commit belongs to the tree that ran the reset, NOT to theirs.
#
# The outcome this rule protects is the OTHER session's tree, so the reflog does not make the
# named-commit form safe: it makes it whole for one tree only. `git reset --hard HEAD~1` therefore
# keeps today's answer, deny in a shared checkout and ask in a worktree, whatever the tree holds.
# (MEASURED on 1be660c in a pristine repository with an empty
# porcelain: `git reset --hard HEAD` answered allow, and so did `git reset --hard HEAD~1`.)
RESTORE_OPT_WITH_VALUE = {"-s", "--source", "--conflict", "--pathspec-from-file"}
# `git reset` takes a value after this one. A pathspec form cannot carry `--hard` at all ("fatal:
# Cannot do hard reset with paths."), which `reset_discards` above already records, so the plain
# operand of a `--hard` call is always the target and never a path.
RESET_OPT_WITH_VALUE = {"--pathspec-from-file"}
RESET_HEAD_TARGETS = ("", "HEAD")
# `git clean -e <pattern>` carries a value. Without this, the pattern would land in the pathspec
# list, the read would narrow to it, and a delete of everything else would pass on an empty
# answer. A wrong PASS is the one failure this layer must not have.
CLEAN_OPT_WITH_VALUE = {"-e", "--exclude"}


def named_pathspecs(subcommand: str, args):
    """Return (pathspecs, complete) for a call that names paths.

    `complete` is False when the call's paths cannot be enumerated from its own arguments, and
    the caller then reads the whole tree rather than a subset it is not sure of.
    """
    if any(pathspec_from_file_flag(arg) for arg in args):
        return [], False
    if "--" in args:
        after = args[args.index("--") + 1:]
        if subcommand != "restore":
            return after, True
        # a restore operand before `--` is a path too (`--source` takes a commit, not a path)
        before, _ = named_pathspecs(subcommand, args[:args.index("--")])
        return before + after, True
    plain = []
    skip = False
    for arg in args:
        if skip:
            skip = False
            continue
        if arg.startswith("-"):
            if subcommand == "checkout" and arg in GIT_CHECKOUT_TAKES_NAME:
                skip = True
            elif subcommand == "restore" and arg in RESTORE_OPT_WITH_VALUE:
                skip = True
            elif subcommand == "clean" and arg in CLEAN_OPT_WITH_VALUE:
                skip = True
            continue
        plain.append(arg)
    if subcommand == "checkout" and len(plain) >= 2:
        return plain, True  # a start point, then the paths; the start point is read as a path too
    return plain, True


def _tree_subject(where: str, pathspecs=(), complete: bool = True):
    """True when the working tree holds nothing under `pathspecs`, False when it holds
    something, None when it cannot be read.
    """
    if complete and any(c in spec for spec in pathspecs for c in "$`{}*?["):
        return False  # a pathspec the guard cannot expand is a discard of unknown size, never clean
    lines = porcelain(where, pathspecs if complete else ())
    if lines is None:
        return None
    return not lines


def reset_target(args):
    """Return the commit a `git reset` names, '' when it names none, or None when the operands
    cannot be read as one target.

    Operands stop at `--`, flags are skipped, and the one flag that carries a value takes its
    value with it. More than one plain operand is a form this does not understand, and an
    unreadable target is never a pass.
    """
    plain = []
    skip = False
    for arg in args:
        if skip:
            skip = False
            continue
        if arg == "--":
            break
        if arg.startswith("-"):
            if arg in RESET_OPT_WITH_VALUE:
                skip = True
            continue
        plain.append(arg)
    if not plain:
        return ""
    if len(plain) == 1:
        return plain[0]
    return None


def reset_subject(args, where: str):
    """The subject of `git reset --hard HEAD` is the whole working tree.

    A `reset --hard` that names ANY OTHER commit also moves the branch, so it keeps today's
    answer whatever the tree holds. See the ruling above the option tables.
    """
    if reset_target(args) not in RESET_HEAD_TARGETS:
        return False
    return _tree_subject(where)


def stash_subject(args, where: str):
    """`push`, `save` and a bare `stash` take the working tree. Every action that takes an entry
    off the stack is read against the STACK, so each one is read where its own subject lives.

    A CLEAN TREE IS NO REASON TO PASS A STACK ACTION. The tree says nothing about what the stack
    holds, and an empty tree is the state in which taking another session's entry is invisible.
    """
    if stash_takes_the_stack(args):
        stack = stash_stack(where)
        if stack is None:
            return None
        return not stack
    return _tree_subject(where)


def restore_subject(args, where: str):
    """`git restore` writes the paths it names, so the read is per path."""
    specs, complete = named_pathspecs("restore", args)
    return _tree_subject(where, specs, complete)


def checkout_subject(args, where: str):
    """`git checkout <path>` writes the paths it names, so the read is per path."""
    if "--" not in args and any(a in ("-f", "--force") for a in args):
        return _tree_subject(where)  # a forced switch rewrites the whole tree
    specs, complete = named_pathspecs("checkout", args)
    return _tree_subject(where, specs, complete)


def clean_reads_ignored(args) -> bool:
    """True when `git clean` also deletes ignored files, which porcelain hides by default."""
    for arg in args:
        if arg.startswith("--"):
            continue
        if arg.startswith("-") and ("x" in arg or "X" in arg):
            return True
    return False


def clean_subject(args, where: str):
    """The subject of `git clean -f` is the untracked part of the status output, widened to the
    ignored part when `-x` or `-X` is on the call.
    """
    specs, complete = named_pathspecs("clean", args)
    ignored = clean_reads_ignored(args)
    lines = porcelain(where, specs if complete else (), ignored=ignored)
    if lines is None:
        return None
    return not [line for line in lines if line[:2] in ("??", "!!")]


SUBJECT_READS = {
    "reset": reset_subject,
    "stash": stash_subject,
    "restore": restore_subject,
    "checkout": checkout_subject,
    "clean": clean_subject,
    "branch-delete": branch_delete_subject,
    "worktree-remove": worktree_remove_subject,
    "worktree-prune": worktree_prune_subject,
}


def subject_state(subcommand: str, args, where: str):
    """True when the call's subject holds nothing, False when it holds something, None when the
    subject cannot be read at all.
    """
    if not where or not os.path.isdir(where):
        return False
    inside = _inside_work_tree(where)
    if inside is None:
        return None
    if inside is not True:
        return False  # not a git tree: nothing was read, so the old decision stands
    reader = SUBJECT_READS.get(subcommand)
    if reader is None:
        return False
    return reader(args, where)


# ------------------------------------------------------------------ this session's scratchpad
#
# A repository under THIS SESSION'S scratchpad is private. No other session and no editor holds
# it, so a discard there loses only work this session made minutes ago.
#
# BY PATH ONLY. The wider tests are guesses: counting worktrees says nothing about who else reads
# the tree, and "this session created it" cannot be read back from a path at all. The path itself
# carries the proof, because the scratchpad of a session is named after that session.
#
# The session id comes from the hook payload Claude Code writes, never from the command and never
# from a token the agent types, so Decision 1 stands: this is not an escape hatch. The
# environment variable is read only as a fallback for a payload that carries no session id, and
# the guard's environment is Claude Code's own, which a `Bash` call cannot change.
#
# SYMLINKS ARE RESOLVED ON BOTH SIDES, with `os.path.realpath`, so a symlink into the scratchpad
# passes and a symlink out of it does not. An environment that names no scratchpad, or a session
# id the payload does not carry, simply fails the test and keeps the old decision.
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,200}$")


def session_id_of(payload) -> str:
    """Return this session's id, from the hook payload, else from the environment."""
    value = ""
    if isinstance(payload, dict):
        value = payload.get("session_id", "") or ""
    if not isinstance(value, str) or not value:
        value = os.environ.get("CLAUDE_CODE_SESSION_ID", "") or ""
    return value if SESSION_ID_RE.match(value or "") else ""


def under_session_scratchpad(where: str, session_id: str) -> bool:
    """True when `where` resolves to a path inside this session's own scratchpad."""
    if not where or not session_id or not SESSION_ID_RE.match(session_id):
        return False
    try:
        real = os.path.realpath(where)
        temp = os.path.realpath(tempfile.gettempdir())
    except Exception:
        return False
    if not (os.path.normcase(real) + os.sep).startswith(os.path.normcase(temp) + os.sep):
        return False
    parts = real.split(os.sep)
    for index in range(len(parts) - 1):
        if parts[index] == session_id and os.path.normcase(parts[index + 1]) == "scratchpad":
            return True
    return False


def in_any_session_scratchpad(where: str) -> bool:
    """True when `where` resolves into the scratchpad of ANY session under the temp folder."""
    try:
        real = os.path.realpath(where)
        temp = os.path.realpath(tempfile.gettempdir())
    except Exception:
        return False
    if not (os.path.normcase(real) + os.sep).startswith(os.path.normcase(temp) + os.sep):
        return False
    parts = real.split(os.sep)
    return any(os.path.normcase(parts[i + 1]) == "scratchpad" and SESSION_ID_RE.match(parts[i])
               for i in range(len(parts) - 1))


TREE_DENY_REASON = (
    "Rule (shared trees): this command throws away work in a checkout that other "
    "sessions and the owner share, and no step puts it back. "
    "Remedy: copy the file to a name ending in .bak and change the copy. "
    "Commit work you must set aside on your own branch, never a stash: a stash entry "
    "belongs to no branch, and it outlives no session that holds its tag. "
    "Run the command in a worktree of your own when the tree must change."
)
_MOVES_SHELL = re.compile(
    r"(?<![\w.-])(?:cd|pushd|popd|set-location|sl|chdir|push-location|pop-location)(?![\w-])"
    r"|(?<![\w.-])env\s[^;&|\n]*?(?<![\w-])(?:-[a-z]*c[a-z]*|--c(?:h(?:d(?:i(?:r)?)?)?)?)(?![\w-])", re.I)
# a option, variable or config that points the call at another work tree than the cwd or `-C`
_REPOINTS_GIT = re.compile(r"--work-tree|--git-dir|GIT_WORK_TREE|GIT_DIR|GIT_COMMON_DIR|core\.worktree", re.I)


def one_place(cmd: str) -> bool:
    """True when the whole command acts on one tree: no `cd`, `pushd` or `popd` token anywhere
    and at most one distinct `git -C` target. Only then may the per-file allow apply, because
    every other shape can hide a shared checkout behind the lane."""
    if _MOVES_SHELL.search(cmd):
        return False
    if _REPOINTS_GIT.search(cmd):
        return False
    targets = set()
    git_targets = []   # one entry per call segment: its `-C` target, or None
    for segment in split_segments(cmd):
        words = segment_tokens(segment)
        target = _segment_git_c_target(words) if words else None
        if target is not None:
            targets.add(target)
        at = resolve_command(words) if words else None
        if at is not None and basename(words[at]) in ("git", "git.exe"):
            git_targets.append(target)
    if targets and None in git_targets:
        return False   # a call with no `-C` runs in the cwd, not in the lane another call names
    return len(targets) <= 1


RESTORE_PER_FILE_FLAGS = {"--staged", "--worktree", "-S", "-W"}


def names_only_files(subcommand: str, args, root: str, segment: str = "") -> bool:
    """True when a `git checkout` or `git restore` is one of the per-file forms: `restore` with
    only the flags in RESTORE_PER_FILE_FLAGS, `checkout` with `--` before the paths or, without
    `--`, one operand that is an existing file. Every path is not `.`, has no glob character or
    pathspec magic, and is not a directory. Any other flag or form, or a segment that cannot be
    tokenized, is False."""
    if subcommand not in ("checkout", "restore"):
        return False
    if segment and segment_tokens(REDIRECTION.sub(" ", segment)) is None:
        return False
    dashed = "--" in args
    head, specs = (args[:args.index("--")], args[args.index("--") + 1:]) if dashed else ([], list(args))
    flags = [a for a in head + ([] if dashed else specs) if a.startswith("-")]
    if subcommand == "restore":
        if any(f not in RESTORE_PER_FILE_FLAGS for f in flags):
            return False
        # every non-flag operand is a path, before `--` too
        specs = [a for a in head if not a.startswith("-")] + [a for a in specs if dashed or not a.startswith("-")]
    else:
        if flags:
            return False
        if not dashed and not (len(specs) == 1 and os.path.isfile(os.path.join(root, specs[0]))):
            return False
    if not specs:
        return False
    for spec in specs:
        if any(c in spec for c in "$`{}"):  # unreadable: a discard of unknown size
            return False
        if spec in (".", "") or spec[0] == ":" or any(c in spec for c in "*?["):
            return False
        if os.path.isdir(os.path.join(root, spec)):
            return False
    return True


TREE_ASK_REASON = (
    "Rule (shared trees): this command throws away work in a working tree. "
    "This checkout is a worktree, so the loss is limited to this lane. "
    "Commit work you must set aside on your own branch, never a stash. "
    "A per-file discard in a worktree runs with no ask when the command holds no cd: "
    "git -C <lane> restore <file>. "
    "The click in this prompt is the grant."
)


# The stash stack is one ref, `refs/stash`, kept in the COMMON git directory, so every worktree
# of a clone reads and writes the same stack (MEASURED 2026-09-19: from a linked worktree,
# `git rev-parse --git-path refs/stash` answered `<repo>/.git/refs/stash`, not the worktree's own
# `.git/worktrees/<name>`). A worktree therefore limits nothing for an action that takes an entry
# off the stack: the entry taken may be another session's, or the owner's. Those arms deny
# everywhere.
#
# THE REMEDY NAMES NO FORBIDDEN COMMAND. It names the two reads, which stay allowed, and the
# commit that sets work aside on a branch of the caller's own. An agent sent here by the harness
# reminder, which asks for a tagged entry and a later restore, reads what to do instead.
STACK_DENY_REASON = (
    "Rule (shared trees): this command takes a stash entry, and the stash stack belongs to the "
    "whole clone, so the entry may hold another session's work and a worktree does not limit "
    "the loss. "
    "Remedy: read the entry with `git stash list` and `git stash show -p stash@{N}`, commit any "
    "patch you need on a branch of your own, and leave the entry for its owner. "
    "Set your own work aside with a commit on your own branch, never on the stack."
)
# `push`, `save` and a bare `git stash` PUT work onto that same one ref. A worktree limits a
# `reset --hard` or a `restore`, because those write the WORKTREE's own tree. They do not limit
# a stash push, because `refs/stash` is not the worktree's own ref: it is the one the primary
# checkout and every other linked worktree already share (MEASURED above, TREE_ASK_REASON's own
# comment). A push from a worktree lands on the same branchless, one-entry-wide stack a `pop` or
# an `apply` would take from, so the worktree exemption that TREE_ASK_REASON grants never
# applies here.
PUSH_DENY_REASON = (
    "Rule (shared trees): this command puts work onto the stash stack, and that stack is one "
    "ref shared by the whole clone, not by this tree alone, so a worktree does not limit the "
    "loss. "
    "Remedy: commit the work on a branch of your own instead. "
    "Set work aside with a commit on your own branch, never a stash: a stash entry belongs to "
    "no branch, and it outlives no session that holds its tag."
)


# ------------------------------------------------------------------ picking a conflict side
#
# A carve-out of rule 1 (shared-tree), with no rule name or log line of its own. The owner's argument: `git checkout --theirs docs/DEBTS.md` during an unresolved merge does
# not discard uncommitted work. It picks a conflict side, and the file is already in a
# conflicted state that git itself will not let the caller leave silently. `checkout_names_a_path`
# still flags the call, because a bare `git checkout <path>` overwrites from the index, so the
# state of the TREE is what tells the two apart, not the flags alone.
#
# THE STATE IS READ WITH GIT, NEVER GUESSED FROM THE COMMAND TEXT. CLAUDE.md: "Never guess an
# answer the code should give you." `MERGE_HEAD`, `CHERRY_PICK_HEAD`, and `REVERT_HEAD` each
# name an in-progress operation when the ref exists. A rebase is checked twice: `REBASE_HEAD` is
# a ref once a rebase has stopped on a conflict, and a `rebase-merge` or `rebase-apply` directory
# in the git dir also marks one in progress.
#
# `git rev-parse --verify -q <ref>` answers three ways: 0 when the ref exists (a conflict IS in
# progress), 1 when it plainly does not (quiet, no stderr), and anything else (128, "not a git
# repository", a timeout) when the tree cannot be read at all. Only the last one is UNKNOWN, and
# an unknown state keeps today's decision rather than assuming either answer.
CHECKOUT_CONFLICT_FLAGS = {"--ours", "--theirs", "--merge"}
CONFLICT_STATE_REFS = ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "REBASE_HEAD")
REBASE_STATE_DIRS = ("rebase-merge", "rebase-apply")


def conflict_in_progress(where: str):
    """True when a merge, rebase, cherry-pick or revert is unresolved in the tree, False when
    none is, None when the state cannot be read.
    """
    if not where or not os.path.isdir(where):
        return None
    for ref in CONFLICT_STATE_REFS:
        answer = guard_core._git(where, "rev-parse", "--verify", "-q", ref)
        if answer is None:
            return None
        if answer.returncode == 0:
            return True
        if answer.returncode != 1:
            return None  # not "ref not found": the tree itself could not be read
    gitdir = guard_core._git(where, "rev-parse", "--git-dir")
    if gitdir is None or gitdir.returncode != 0 or not gitdir.stdout.strip():
        return None
    path = gitdir.stdout.strip()
    if not os.path.isabs(path):
        path = os.path.join(where, path)
    return any(os.path.isdir(os.path.join(path, name)) for name in REBASE_STATE_DIRS)


def checkout_conflict_resolve(segment: str, root: str) -> str:
    """Return the matched `git checkout` text when it picks a conflict side during an unresolved
    merge, rebase, cherry-pick or revert in `root`, else ''.

    Only `--ours`, `--theirs`, and `--merge` qualify: each picks a side of an existing conflict
    rather than overwriting a clean file from the index. An unreadable tree state keeps today's
    decision, so the caller still runs `shared_tree_hit`'s ordinary deny or ask.
    """
    for subcommand, args in git_calls(segment):
        if subcommand != "checkout":
            continue
        if not any(flag in CHECKOUT_CONFLICT_FLAGS for flag in args):
            continue
        if conflict_in_progress(root) is True:
            return ("git checkout " + " ".join(args)).strip()
    return ""

# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
