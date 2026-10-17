"""The guard's push-delete family: a forced push and a wide delete.

guard.py is the only entry point, and it runs these checks in its fixed order (decision
guard-split-by-family). Other files reach these names through `guard`.
"""
import os
import re

import guard_core
from guard_core import (
    CMD_EXE_NAMES, GIT_OPT_WITH_VALUE, _absolute, _segment_cd_target, _segment_git_c_target,
    _strip_heredoc_bodies_unconditionally, basename, command_indexes, nested_script,
    resolve_command, segment_tokens, split_segments, ssh_remote_script,
)


# `-o` is read in the short-flag loop, where its value may be glued on.
PUSH_VALUE_OPTS = {"--receive-pack", "--exec", "--push-option"}
DEFAULT_BRANCH_FALLBACK = ("main", "master")


def _push_config(cwd: str, key: str, overrides=None):
    """The config value, '' when the key is unset, None when git cannot answer.

    A `git -c key=value` override on the push call wins over the repository's own config.
    """
    if overrides and key.lower() in overrides:
        return overrides[key.lower()]
    answer = guard_core._git(cwd, "config", "--get", key) if cwd else None
    if answer is None or answer.returncode not in (0, 1):
        return None
    return answer.stdout.strip()


def _push_current_branch(cwd: str):
    answer = guard_core._git(cwd, "symbolic-ref", "-q", "--short", "HEAD") if cwd else None
    if answer is None or answer.returncode != 0 or not answer.stdout.strip():
        return None
    return answer.stdout.strip()


def _push_bare_destination(cwd: str, overrides=None):
    """Where a push with no refspec goes, read through push.default, else None (unknown).

    `simple` and `current` push the current branch to its own name. `upstream` pushes to the
    branch's upstream ref. `matching`, `nothing`, an unset upstream or an unreadable config is
    unknown, and unknown is never safe.
    """
    current = _push_current_branch(cwd)
    mode = _push_config(cwd, "push.default", overrides)
    if current is None or mode is None:
        return None
    if mode in ("", "simple", "current"):
        return current
    if mode in ("upstream", "tracking"):
        merge = _push_config(cwd, "branch." + current + ".merge", overrides)
        return merge.removeprefix("refs/heads/") if merge else None
    return None


def _push_default_branches(cwd: str, remote: str):
    """The default branch names, or None when git cannot be read at all.

    `guard_core.read_default_base` answers for the PUSHED remote (owner's ruling 2026-10-16). A
    resolved `<remote>/HEAD` names the one branch. Any other answer (HEAD unset, dangling, or a
    read that did not answer) protects main AND master, plus the name HEAD holds. No readable
    repository is unknown, and unknown is never safe.
    """
    if not cwd or not os.path.isdir(cwd):
        return None
    repo = guard_core._git(cwd, "rev-parse", "--git-dir")
    if repo is None or repo.returncode != 0:
        return None
    base, head = guard_core.read_default_base(cwd, remote)
    named = (head[len(remote) + 1:],) if head else ()
    if base is not None and base == head:
        return named
    return DEFAULT_BRANCH_FALLBACK + named


# A quoted run with a space in it is text (a commit message, an echo), never a push. A quoted
# single word stays: it is a refspec or a remote, and the shell would unquote it.
PUSH_QUOTED = re.compile(r"\"[^\"\s]*\s[^\"]*\"|'[^'\s]*\s[^']*'")


def push_target(segment: str, cmd: str, cwd: str):
    """(directory, config overrides) a `git push` in this segment runs against.

    The directory is the segment's own `git -C <dir>`, else the command's last `cd`, else the
    session's cwd. A segment that cannot be read gives ('', {}): a directory that does not
    exist, which the verdict reads as unknown, and unknown asks.
    """
    tokens = segment_tokens(segment)
    if tokens is None:
        return "", {}
    # The last `cd` only: `_run_dir` would also take the first `git -C` of ANY segment.
    run_dir = cwd
    for other in split_segments(_strip_heredoc_bodies_unconditionally(cmd)):
        words = segment_tokens(other)
        cd = _segment_cd_target(words) if words else None
        if cd is not None:
            run_dir = _absolute(cd, run_dir)
    git_c = _segment_git_c_target(tokens)
    where = _absolute(git_c, run_dir) if git_c is not None else run_dir
    overrides = {}
    index = resolve_command(tokens)
    cursor = index + 1 if index is not None else len(tokens)
    while cursor < len(tokens) and tokens[cursor].startswith("-"):
        if tokens[cursor] == "-c" and cursor + 1 < len(tokens):
            key, _, value = tokens[cursor + 1].partition("=")
            overrides[key.lower()] = value
        cursor += 2 if tokens[cursor] in GIT_OPT_WITH_VALUE else 1
    return where, overrides


def push_text(segment: str) -> str:
    """The segment with quoted multi-word text blanked: a quoted `--force` is text, not a push."""
    return PUSH_QUOTED.sub(" ", segment)


def push_verdict(args, cwd: str, overrides=None) -> str:
    """'' for an allowed push, else 'ask' or 'deny', for the `git push` arguments `args`.

    Not forced: ''. Forced or deleting at the default branch, or at a destination this cannot
    resolve: 'ask'. Forced by `--force`, `-f`, a `--fo...` prefix or a `+refspec`: 'deny'. Forced
    by a lease: '' when `--force-if-includes` rides with it, or every lease names its own sha;
    else 'deny'. A deletion off the default branch is ''.
    """
    force = mirror = every = includes = unpinned = leased = delete = False
    remote = ""
    plain = []
    skip = repo_next = False
    for arg in args:
        arg = arg.replace('"', "").replace("'", "")
        if repo_next:
            repo_next, remote = False, arg
        elif skip:
            skip = False
        elif arg in PUSH_VALUE_OPTS:
            skip = True
        elif arg.startswith("--"):
            name, _, value = arg.partition("=")
            if name == "--repo":
                remote, repo_next = value, not value
            elif name == "--force-if-includes" or (
                    len(name) >= 9 and "--force-if-includes".startswith(name)):
                includes = True
            elif name == "--no-force-if-includes":
                includes = False
            elif name == "--no-force-with-lease":
                leased = unpinned = False
            elif name == "--force-with-lease" or (
                    len(name) >= 9 and "--force-with-lease".startswith(name)):
                leased = True
                unpinned = unpinned or not value.partition(":")[2]
            elif name == "--mirror":
                mirror = True
            elif name == "--all":
                every = True
            elif name == "--delete":
                delete = True
            elif len(name) >= 4 and "--force".startswith(name):
                force = True
        elif arg.startswith("-") and len(arg) > 1:
            for index, letter in enumerate(arg[1:]):
                if letter == "o":  # a push option: the rest of the word, or the next word
                    skip = index == len(arg) - 2
                    break
                force = force or letter == "f"
                delete = delete or letter == "d"
        else:
            plain.append(arg)
    if not remote and plain:
        remote, plain = plain[0], plain[1:]
    plus = any(spec.startswith("+") for spec in plain)
    delete = delete or any(spec.startswith(":") for spec in plain)
    if not (force or leased or plus or mirror or delete):
        return ""
    if not remote:
        remote = _push_config(
            cwd, "branch." + (_push_current_branch(cwd) or "") + ".remote", overrides)
    defaults = _push_default_branches(cwd, remote or "origin")
    reaches = mirror or every or defaults is None
    for spec in plain or [""]:
        source, colon, target = spec.lstrip("+").partition(":")
        target = target if colon else source
        if not plain:
            target = _push_bare_destination(cwd, overrides)
        elif target in ("HEAD", "@"):
            target = _push_current_branch(cwd)
        if target is None or "*" in target:
            reaches = True
        elif target.removeprefix("refs/heads/") in (defaults or ()):
            reaches = True
    if reaches:
        return "ask"
    if force or plus:
        return "deny"
    return "" if includes or not unpinned else "deny"


# ------------------------------------------------------------------ a rewrite and a wide delete
#
# A force push rewrites a branch other people have pulled. It is sometimes right, so it asks rather
# than refuses.
#
# The recursive delete keeps the SAME SHAPE in both shells, deliberately. `rm -rf node_modules` is
# allowed, so `Remove-Item -Recurse -Force node_modules` must be allowed too. A guard that answers
# differently for the same act teaches which tool to reach for. PowerShell folds case and
# abbreviates parameter names, so `-r`, `-rec` and `-recurse` are one flag. The command text is
# read with backslashes already turned into forward slashes, which is why a drive root reads
# as `C:/`.
WIDE_TARGET = (
    r"(?:/|~|\.|\*|\$HOME|%USERPROFILE%|\$env:USERPROFILE|[A-Za-z]:/?\*?)"
)
# The POSIX `rm -rf` form is read by TOKENS (`rm_delete_hit`), not by a pattern: a quoted `rm -rf /`
# in an echo or a commit message is text. `RM_RAW` reads raw text only for a segment shlex cannot
# parse, so an unmatched quote elsewhere in the line does not hide a delete.
RM_RAW = re.compile(
    r"\brm\s+(?:-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r)\s+['\"]?"
    + WIDE_TARGET + r"['\"]?(?:\s|$)"
)
DESTRUCTIVE_DELETE = (
    re.compile(
        r"(?i)\b(?:remove-item|ri|rd|rmdir|del|erase|rm)\b"
        r"(?=[^\n;|&]*\s-r(?:ec(?:urse)?)?\b)"
        r"(?=[^\n;|&]*\s-f(?:o(?:rce)?)?\b)"
        r"[^\n;|&]*\s['\"]?" + WIDE_TARGET + r"['\"]?(?:\s|$)"
    ),
)
# A target `rm -rf` must not take: a root, a home, the working directory or a glob of one, with an
# optional trailing slash and `*`. `.*` and `..` are not here: they were allowed before.
RM_WIDE_TARGET = re.compile(
    r"/\*?|(?:~|\.|\$HOME|\$\{HOME\}|%USERPROFILE%|\$env:USERPROFILE)(?:/\*?)?|\*|[A-Za-z]:/?\*?"
)


def _rm_args_wide(args) -> str:
    """The first wide target of `rm`'s arguments when they hold a recursive AND a force flag, else
    ''. Long flags count, `--` ends the flags, and one letter cluster may hold R, r and f."""
    recursive = force = after_dashes = False
    targets = []
    for arg in args:
        if after_dashes or not arg.startswith("-") or arg == "-":
            targets.append(arg)
        elif arg == "--":
            after_dashes = True
        elif arg.startswith("--"):
            recursive = recursive or arg == "--recursive"
            force = force or arg == "--force"
        else:
            recursive = recursive or "r" in arg or "R" in arg
            force = force or "f" in arg
    if recursive and force:
        return next((t for t in targets if RM_WIDE_TARGET.fullmatch(t)), "")
    return ""


def rm_delete_hit(segment: str) -> str:
    """Return the matched text when one segment runs `rm -rf` at a root, a home, the working
    directory or a glob, else ''. Read by tokens: the command word is `rm`, behind its wrappers
    or a subshell, or inside the script a shell, `eval` or `ssh` hands on. A segment shlex cannot
    parse is read as raw text."""
    tokens = segment_tokens(segment)
    if tokens is None:
        found = RM_RAW.search(segment)
        return found.group(0) if found else ""
    for start in command_indexes(tokens):
        if basename(tokens[start]) == "rm":
            target = _rm_args_wide(tokens[start + 1:])
            if target:
                return "rm -rf " + target
    for script in (nested_script(tokens), ssh_remote_script(tokens)):
        for inner in split_segments(script) if script else ():
            found = rm_delete_hit(inner)
            if found:
                return found
    return ""

DELETE_REASON = (
    "Rule (shared trees): this deletes a whole root, a home directory or everything a "
    "glob matches. The loss reaches files that no session here can see. "
    "Remedy: name the one directory you mean, under the project or under the scratchpad."
)

# THE CMD.EXE VERBS. `rd`/`rmdir` and `del`/`erase` take slash flags, never `rm`'s or
# `Remove-Item`'s dash flags, so neither pattern above ever reads them: `/s` is the recurse
# switch, and `/q` (optional, never required) only silences the confirmation prompt. MEASURED
# 2026-09-24: `rd /s /q C:\Users\x`, `cmd /c rd /s /q %USERPROFILE%` and `del /s /q C:\*` all
# passed, on both tool names, though their `rm`/`Remove-Item` twins deny.
#
# Checked by TOKENS, not by a whole-string search like the two patterns above, so a name sitting
# inside a quoted argument or a grep pattern never reads as a command: `echo "rd /s /q"` and
# `grep "del /s" notes.md` are text, and neither segment's own command word is `rd` or `del`.
# `segment_tokens` is quote-aware for the same reason `split_segments` is (see its own comment),
# and this reads `cmd`, the backslash-normalized text, same as the patterns above, so a token can
# be compared to `WIDE_TARGET` with no backslash left to confuse it.
#
# `cmd /c` and `cmd.exe /c` are unwrapped IN PLACE, deliberately, rather than folded into the
# shared `COMMAND_WRAPPERS` every rule reads: that set feeds `resolve_command`, which rules 2 and
# 3 also call, and widening it here would change what THEY skip past too.
CMD_EXE_DELETE_WORDS = {"rd", "rmdir", "del", "erase"}


def cmd_exe_delete_hit(segment: str) -> str:
    """Return the matched text when one segment runs a cmd.exe recursive delete at a
    root, a home or a glob, else ''.

    Reached directly, or through a `cmd /c`/`cmd.exe /c` prefix, from either shell.
    """
    tokens = segment_tokens(segment)
    if not tokens:
        return ""
    index = 0
    if (len(tokens) >= 2 and basename(tokens[0]) in CMD_EXE_NAMES
            and tokens[1].lower() == "/c"):
        index = 2
    if index >= len(tokens):
        return ""
    word = tokens[index]
    if basename(word) not in CMD_EXE_DELETE_WORDS:
        return ""
    rest = tokens[index + 1:]
    if not any(arg.lower() == "/s" for arg in rest):
        return ""
    for arg in rest:
        if re.fullmatch("(?i)" + WIDE_TARGET, arg):
            return word + " /s " + arg
    return ""


PUSH_REASON = (
    "Rule (Git): a forced push can overwrite newer remote work with a stale copy. "
    "Remedy: retry with --force-with-lease --force-if-includes."
)
PUSH_ASK_REASON = (
    "Rule (Git): this forced push may rewrite the default branch, or its target is unreadable. "
    "The click in this prompt is the grant."
)

# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
