"""The guard's push-delete family: a forced push and a wide delete.

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import os
import re
import stat

import guard_core
from guard_core import (
    CMD_EXE_NAMES, GIT_OPT_WITH_VALUE, _absolute, _segment_cd_move,
    _segment_git_c_target, dir_before_segment, expand_folder_word, shell_abs, CONTRACTION, quote_advance, _git_subcommand_index,
    bare_words, basename, command_indexes, inner_commands,
    is_powershell, norm, resolve_command, segment_tokens, split_segments,
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
    answer = guard_core._git(cwd, "symbolic-ref", "-q", "HEAD") if cwd else None
    if answer is None or answer.returncode != 0 or not answer.stdout.strip():
        return None
    # no `--short`: it prints `heads/<name>` when a tag has the branch's name
    return answer.stdout.strip().removeprefix("refs/heads/")


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

    `guard_core.read_default_base` answers for the PUSHED remote. A
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


def push_target(segments, ends, number: int, cwd: str):
    """(directory, config overrides) a `git push` in `segments[number]` runs against.

    `segments` and `ends` are the caller's own `split_segments` result, so the segment is read in
    the list the caller walks, never in a second reading of the command. The directory is the
    segment's own `git -C <dir>`, else the folder the shell is in when the push runs
    (`dir_before_segment`: each earlier `cd` or `pushd`, a subshell's `cd` ended with its
    parenthesis, a failed `cd` that left the shell where it was, a `cd` into a folder an earlier
    `mkdir` makes), else the session's cwd. A segment or folder that cannot be read gives ('', {}):
    a directory that does not exist, which the verdict reads as unknown, and unknown asks.
    """
    tokens = segment_tokens(segments[number])
    if tokens is None:
        return "", {}
    where = dir_before_segment(segments, number, cwd, ends, failed_cd_stays=True, read_variables=True)
    git_c = _segment_git_c_target(tokens)
    if git_c is not None:
        if expand_folder_word(git_c) is None:
            return "", {}
        where = _absolute(git_c, where or "")
    if not where or not os.path.isabs(where):
        return "", {}
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


def _push_parse(args):
    """The one reader of `git push` arguments: (force, mirror, every, includes, unpinned, leased,
    delete, upstream, remote, refspecs). `upstream` is a `-u` or `--set-upstream` push. `--branches` is
    git's alias of `--all`. The remote is '' when none is named."""
    force = mirror = every = includes = unpinned = leased = delete = upstream = False
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
            elif name in ("--all", "--branches"):
                every = True
            elif len(name) >= 6 and "--set-upstream".startswith(name):
                upstream = True
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
                upstream = upstream or letter == "u"
        else:
            plain.append(arg)
    if not remote and plain:
        remote, plain = plain[0], plain[1:]
    return force, mirror, every, includes, unpinned, leased, delete, upstream, remote, plain


def _push_dest(spec: str, bare: bool, cwd: str, overrides=None):
    """The branch one refspec writes: `HEAD` and a bare push read the checkout's current branch.
    None when that cannot be read."""
    source, colon, target = spec.lstrip("+").partition(":")
    target = target if colon else source
    if bare:
        return _push_bare_destination(cwd, overrides)
    if target in ("HEAD", "@"):
        return _push_current_branch(cwd)
    return target


_DESTINATIONS = {}   # (args, cwd, overrides) -> destinations, for the life of one hook process


def push_destinations(args, cwd: str, overrides=None):
    """The branch names a `git push` with these arguments writes, `refs/heads/` cut off, a deletion
    included. None stands for a destination it cannot resolve. One hook call is one process and reads
    each push's destinations once, so the record-branch check and the conflict-markers check share the
    reads (`git symbolic-ref`, `git config`) a HEAD or bare push needs."""
    key = (tuple(args), cwd, tuple(sorted((overrides or {}).items())))
    if key not in _DESTINATIONS:
        plain = _push_parse(args)[-1]
        found = [_push_dest(spec, not plain, cwd, overrides) for spec in plain or [""]]
        _DESTINATIONS[key] = [t.removeprefix("refs/heads/") if t else t for t in found]
    return _DESTINATIONS[key]


def _colon_delete(delete, plain):
    """True for a push that deletes: a delete flag, or a refspec with no source (`:ref`)."""
    return delete or any(spec.startswith(":") for spec in plain)


def push_refspecs(args):
    """(remote, refspecs) of a push that names the refs it sends, else None: `--all`, `--branches`,
    `--mirror`, a deletion and a tags-only push send no range this reader can name. The remote is ''
    when none is named, and the refspecs are empty for a bare push."""
    _force, mirror, every, _includes, _unpinned, _leased, delete, _upstream, remote, plain = _push_parse(args)
    delete = _colon_delete(delete, plain)
    if mirror or every or delete or (_push_tags_only(args) and not plain):
        return None
    return remote, plain


def push_verdict(args, cwd: str, overrides=None) -> str:
    """'' for an allowed push, else 'ask' or 'deny', for the `git push` arguments `args`.

    Not forced: ''. Forced or deleting at the default branch, or at a destination this cannot
    resolve: 'ask'. Forced by `--force`, `-f`, a `--fo...` prefix or a `+refspec`: 'deny'. Forced
    by a lease: '' when `--force-if-includes` rides with it, or every lease names its own sha;
    else 'deny'. A deletion off the default branch is ''.
    """
    force, mirror, every, includes, unpinned, leased, delete, _upstream, remote, plain = _push_parse(args)
    plus = any(spec.startswith("+") for spec in plain)
    delete = _colon_delete(delete, plain)
    if not (force or leased or plus or mirror or delete):
        return ""
    if not remote:
        remote = _push_config(
            cwd, "branch." + (_push_current_branch(cwd) or "") + ".remote", overrides)
    defaults = _push_default_branches(cwd, remote or "origin")
    reaches = mirror or every or defaults is None
    for spec in plain or [""]:
        target = _push_dest(spec, not plain, cwd, overrides)
        if target is None or "*" in target:
            reaches = True
        elif target.removeprefix("refs/heads/") in (defaults or ()):
            reaches = True
    if reaches:
        return "ask"
    if force or plus:
        return "deny"
    return "" if includes or not unpinned else "deny"


def _push_tags_only(args) -> bool:
    """True when the push carries `--tags` (or an unambiguous prefix): with no refspec it moves tags only."""
    for arg in args:
        name = arg.partition("=")[0]
        if name.startswith("--") and len(name) >= 4 and "--tags".startswith(name):
            return True
    return False


def _push_branch_config(cwd: str, current: str, with_default: bool, overrides=None):
    """(remote, merge, push.default) of `current`: '' for a key that is unset, None for all three when git
    cannot answer. One `git config --get-regexp` spawn answers all of them. A `git -c push.default=`
    override wins, as in `_push_config`."""
    pattern = r"^(branch\.|push\.default$)" if with_default else r"^branch\."
    answer = guard_core._git(cwd, "config", "--get-regexp", pattern) if cwd else None
    if answer is None or answer.returncode not in (0, 1):
        return None, None, None
    found = {}
    for line in answer.stdout.splitlines():
        key, _, value = line.partition(" ")
        found.setdefault(key, value.strip())
    default = overrides["push.default"] if overrides and "push.default" in overrides else found.get(
        "push.default", "")
    return (found.get("branch." + current + ".remote", ""),
            found.get("branch." + current + ".merge", "").removeprefix("refs/heads/"), default)


def push_ask_hit(args, cwd: str, overrides=None) -> str:
    """'main', 'stray', 'unread' or '' for the `git push` arguments `args`, a push `push_verdict` let through.

    'main' (rule push-main): a non-forced push whose destination is literally `main` or `master`, `--all`
    included. The remote's HEAD is never read. 'stray' (rule push-stray-branch): a push with an implied
    destination (a bare push, `HEAD`, `@`, or a colon-less refspec naming the current branch) that writes a
    name other than the branch's upstream. It needs an upstream, the pushed remote equal to
    branch.<cur>.remote, and an upstream that is not main or master. A `-u` push is silent here: its
    implied destination is the local name, which becomes the new upstream. A bare push under push.default
    simple writes the current branch only when the upstream carries its name, else git refuses it. A
    deletion, a forced push, a mirror, and a push of tags alone are never judged here. 'unread' (rule
    push-unread-folder, decision plain-push-asks): a bare push, `HEAD` or `@` whose folder cannot be read (`cwd` is
    '' or no directory), so its destination is unknown, as `push_verdict` asks on the same folder. A folder
    that exists but is no repository, a detached HEAD and a push.default that names no branch are allowed.
    Reads: none for a literal destination; the current branch for an implied one; one `git config
    --get-regexp` when the upstream is needed.
    """
    force, mirror, every, includes, unpinned, leased, delete, upstream, remote, plain = _push_parse(args)
    if force or leased or mirror or delete or any(spec.startswith(("+", ":")) for spec in plain):
        return ""
    if every:
        return "main"
    if not plain and _push_tags_only(args):
        return ""
    state = {}
    unread = "unread" if not (cwd and os.path.isdir(cwd)) else ""

    def current():
        if "cur" not in state:
            state["cur"] = _push_current_branch(cwd)
        return state["cur"]

    def config():
        if "cfg" not in state:
            state["cfg"] = _push_branch_config(cwd, current(), not plain, overrides)
        return state["cfg"]

    implied = False
    if not plain:
        cur = current()
        merge, mode = config()[1:] if cur else (None, None)
        if cur is None or mode is None:
            return unread
        if mode in ("", "simple"):
            dest = cur if merge == cur else None
        elif mode == "current":
            dest = cur
            implied = True
        elif mode in ("upstream", "tracking"):
            dest = merge or None
        else:
            dest = None
        if dest in DEFAULT_BRANCH_FALLBACK:
            return "main"
    else:
        for spec in plain:
            source, colon, target = spec.partition(":")
            if colon:
                if target.removeprefix("refs/heads/") in DEFAULT_BRANCH_FALLBACK:
                    return "main"
            elif source.removeprefix("refs/heads/") in DEFAULT_BRANCH_FALLBACK:
                return "main"
            elif source in ("HEAD", "@") or (current() is not None and source == current()):
                implied = True
        if implied and current() in DEFAULT_BRANCH_FALLBACK:
            return "main"
    if not implied:
        return ""
    if current() is None:
        return unread
    remote_cfg, merge, _mode = config()
    pushed = remote or remote_cfg
    if not merge or not remote_cfg or pushed != remote_cfg or merge in DEFAULT_BRANCH_FALLBACK:
        return ""
    # A -u push of the local name sets that name as the new upstream on purpose (a lane stacked on a lane).
    return "stray" if merge != current() and not upstream else ""


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
    r"(?:/\*?|(?:~|\.|\$HOME|\$\{HOME\}|%USERPROFILE%|\$env:USERPROFILE)(?:/\*?)?|\*|[A-Za-z]:/?\*?)"
)
# The POSIX `rm -rf` form is read by TOKENS (`rm_delete_hit`), not by a pattern: a quoted `rm -rf /`
# in an echo or a commit message is text. `RM_RAW` reads raw text only for a segment shlex cannot
# parse. There a match inside quotes is text too, and a quote the shell leaves open hides what
# follows it, as it does from the shell. An escaped quote (`it\'s`, kept by `delete_text`) and a
# contraction open no quote.
_ESCAPED = re.compile(r"\\(.?)", re.S)


def delete_text(segment):
    """`segment` with its backslashes turned into slashes, as `norm` does, so `C:\\` reads as `C:/`.
    In bash a backslash before a quote stays: `it\\'s` and `"a\\"b"` open no quote, and `it/'s`
    would. Each pair is read whole, so `\\\\'` is an escaped backslash and then an open quote."""
    if is_powershell(segment):
        return type(segment)(norm(segment))
    return type(segment)(_ESCAPED.sub(
        lambda m: m.group(0) if m.group(1) in ("'", '"') else "/" + norm(m.group(1)), segment))


class UnquotedStart:
    """A compiled pattern whose `search` skips a match that starts inside quotes. It has a
    pattern's own `search`, so a caller loops over it without knowing the difference. An
    apostrophe shaped like a contraction is text, as in split_segments' second reading: a lone
    `don't` must not turn the rest of the line into one quote."""

    def __init__(self, pattern):
        self.pattern = pattern

    def search(self, text):
        inside, quote, index = set(), "", 0
        while index < len(text):
            if not quote and text[index] == "'" and CONTRACTION.match(text, index):
                width, after = 1, ""
            else:
                width, after = quote_advance(text, index, quote)
            if quote:
                inside.update(range(index, index + width))
            quote, index = after, index + width
        return next((m for m in self.pattern.finditer(text) if m.start() not in inside), None)


RM_RAW = UnquotedStart(re.compile(
    r"\brm\s+-[a-zA-Z]*[rR][a-zA-Z]*\s+['\"]?" + WIDE_TARGET + r"['\"]?(?:\s|\)|$)"
))


DESTRUCTIVE_DELETE = (
    re.compile(
        r"(?i)\b(?:remove-item|ri|rd|rmdir|del|erase|rm)\b"
        r"(?=[^\n;|&]*\s-r(?:ec(?:urse)?)?\b)"
        r"(?=[^\n;|&]*\s-f(?:o(?:rce)?)?\b)"
        r"[^\n;|&]*\s['\"]?" + WIDE_TARGET + r"['\"]?(?:\s|\)|$)"
    ),
    # Recursion alone is enough for the PowerShell names. `rm` is read by tokens, not here. A match
    # that starts inside quotes is text (an echo, a commit message), so it is not read.
    UnquotedStart(re.compile(
        r"(?i)\b(?:remove-item|ri|rd|rmdir|del|erase)\b"
        r"(?=[^\n;|&]*\s-r(?:ec(?:urse)?)?\b)"
        r"[^\n;|&]*\s['\"]?" + WIDE_TARGET + r"['\"]?(?:\s|\)|$)"
    )),
)
# The one set of wide targets, read by the pattern fallbacks and, by tokens, by `rm -rf`: a root, a
# home, the working directory or a glob of one, with an optional trailing slash and `*`. `.*` and
# `..` are not here: they were allowed before.
RM_WIDE_TARGET = re.compile(WIDE_TARGET)


def _rm_args_wide(args) -> str:
    """The first wide target of `rm`'s arguments when they hold a recursive flag, else ''. Long
    flags count, `--` ends the flags, and one letter cluster may hold R or r. Force is no part of it."""
    recursive = after_dashes = False
    targets = []
    for arg in args:
        if after_dashes or not arg.startswith("-") or arg == "-":
            targets.append(arg)
        elif arg == "--":
            after_dashes = True
        elif arg.startswith("--"):
            recursive = recursive or arg == "--recursive"
        else:
            recursive = recursive or "r" in arg or "R" in arg
    if recursive:
        return next((t for t in targets if RM_WIDE_TARGET.fullmatch(t)), "")
    return ""


# A substitution glued to an assignment or a backtick (`x=$(rm`, `` `rm ``): the command follows it.
SUBST_OPEN = re.compile(r"^(?:[A-Za-z_]\w*=)?(\$\(|`)(?=.)")


def _in_group(args, tick=False):
    """`args` up to the `)` (or, with `tick`, the backtick) that closes a group opened before them,
    with that mark cut off its token: `(rm -rf .)` hands rm `.)`, and rm's target is `.`. A `)` that
    closes a `$(` inside `args` stays."""
    depth, out = 0, []
    for arg in args:
        if tick:
            cut = arg.find("`")
            if cut >= 0:
                out += [arg[:cut]] if cut else []
                break
        else:
            depth += arg.count("(")
            extra = arg.count(")") - depth
            if extra > 0:
                out += [arg[:-extra]] if arg[:-extra] else []
                break
            depth -= arg.count(")")
        out.append(arg)
    return out


def _git_subcommands(words):
    """The indexes of the words that name a git subcommand, such as the `rm` of `git rm -r .`. Such
    a word is no command word. A force flag keeps the word read: `git rm` without one refuses to drop an edited
    file, so git can restore what it removes, and `git rm -f` discards the edits."""
    found = set()
    for at, word in enumerate(words):
        if basename(word) in ("git", "git.exe"):
            sub = _git_subcommand_index(words, at)
            args = words[sub + 1:]
            args = args[:args.index("--")] if "--" in args else args
            if not any(a == "--force" or (a[:1] == "-" and a[1:2] != "-" and "f" in a) for a in args):
                found.add(sub)
    return found


def _command_hit(segment: str, names, judge, raw=None, by_word=False) -> str:
    """The first text `judge` returns for the arguments of a command named in `names`, in one parsed
    segment, else ''. The command word sits behind its wrappers or a
    subshell, or inside the script a shell, `eval` or `ssh` hands on. The one reader of these forms.
    A group's closing `)` is no part of the last argument. A segment shlex cannot parse is read as
    raw text with the pattern `raw`, when there is one. With `by_word`, `judge` also gets the
    command word it judges."""
    tokens = segment_tokens(segment)
    if tokens is None:
        found = raw.search(segment) if raw else None
        return found.group(0) if found else ""
    quoted = getattr(tokens, "quoted", ())
    views = [(tokens, False)]
    for at, token in enumerate(tokens):
        opened = SUBST_OPEN.match(token) if at not in quoted else None
        if opened:
            views.append(([token[opened.end():]] + tokens[at + 1:], opened.group(1) == "`"))
    for view, tick in views:
        for start in command_indexes(view):
            if basename(view[start]) in names:
                args = _in_group(view[start + 1:], tick)
                found = judge(args, basename(view[start])) if by_word else judge(args)
                if found:
                    return found
    words, bare = bare_words(segment)
    for at in sorted(bare - _git_subcommands(words)):
        opened = SUBST_OPEN.match(words[at])
        word = words[at][opened.end():] if opened else words[at]
        args = _in_group(words[at + 1:], bool(opened) and opened.group(1) == "`")
        found = basename(word) in names and (
            judge(args, basename(word)) if by_word else judge(args))
        if found:
            return found
    for script in inner_commands(tokens):
        for inner in split_segments(script):
            found = _command_hit(inner, names, judge, raw, by_word)
            if found:
                return found
    return ""


def _rm_wide_text(args) -> str:
    target = _rm_args_wide(args)
    return "rm -rf " + target if target else ""


def rm_delete_hit(segment: str) -> str:
    """Return the matched text when one segment runs `rm -rf` at a root, a home, the working
    directory or a glob, else ''. A segment shlex cannot parse is read as raw text."""
    return _command_hit(segment, ("rm",), _rm_wide_text, RM_RAW)


# ------------------------------------------------------------ `.`, a parent, the working folder
#
# A recursive delete, forced or not, of `.`, a relative parent, the working folder or a folder above
# it (decision rm-path-wrapper). The rm shim holds the same line on Mac and Linux, at run time; on
# Windows this reader is the only one. It reads the command text, and resolves a named folder through
# links already on disk, so it misses a link made earlier in the same command. One reader serves
# `rm`, the PowerShell delete verbs and the cmd.exe verbs, in either shell. `.`, `..` and a relative
# parent deny by their text, so a folder change ahead of them needs no tracking. Any other relative name is
# resolved against the shell's own folder only when no folder change comes first.
REL_PARENT = re.compile(r"(?:\.{1,2}/)*\.{1,2}(?:/\*?)?")
CMD_FLAG = re.compile(r"/[A-Za-z?]")
RM_PARENT_RAW = UnquotedStart(re.compile(
    r"\brm\s+(?:-\S+\s+)*?-(?:[a-zA-Z]*[rR][a-zA-Z]*|-recursive)\s+(?:-\S+\s+)*['\"]?"
    + REL_PARENT.pattern + r"['\"]?(?:\s|\)|$)"
))


def _pwd_as_dot(target: str) -> str:
    """`target` with a leading `$(pwd)` read as `.`, the working folder the substitution names, so
    `$(pwd)/*` is judged as `./*` and `$(pwd)/build` as `./build`. Quotes are already gone from a
    parsed token. `$PWD` is left alone: the variable rule (rm-var-unguarded) refuses it."""
    return "." + target[len("$(pwd)"):] if target.startswith("$(pwd)") else target


def _parent_target(target: str, cwd: str, moved: bool) -> bool:
    """True when `target` is `.`, a relative parent, or the working folder or a folder above it,
    or a glob of one."""
    target = _pwd_as_dot(target)
    if REL_PARENT.fullmatch(target):
        return True
    if not cwd or not target or RM_WIDE_TARGET.fullmatch(target):
        return False   # a root, a home or a drive root is the wide readers' to judge, not this one's
    path = shell_abs(target[:-2] if target.endswith("/*") else target, None if moved else cwd)
    if not path:
        return False
    try:
        here, there = (os.path.normcase(os.path.realpath(p)) for p in (cwd, path))
    except (OSError, ValueError):
        return False
    return here == there or here.startswith(there.rstrip(os.sep) + os.sep)


def _parent_delete_text(args, word: str, cwd: str, moved: bool) -> str:
    """`word -r <target>` for the first target of a recursive delete that is `.`, a parent or the
    working folder, else ''. Recursion is `/s` for the cmd.exe verbs, a prefix of `-Recurse` for the
    PowerShell verbs, and `-r`, `-R` or `--recursive` for `rm`."""
    cmd_verb = word in CMD_EXE_DELETE_WORDS
    recursive = after_dashes = False
    targets = []
    for arg in args:
        low = arg.lower()
        if cmd_verb and not after_dashes and CMD_FLAG.fullmatch(arg):
            recursive = recursive or low == "/s"
        elif after_dashes or not arg.startswith("-") or arg == "-":
            targets.append(arg)
        elif arg == "--":
            after_dashes = True
        elif arg.startswith("--"):
            recursive = recursive or "recursive".startswith(low[2:])
        else:
            body = low[1:]
            recursive = recursive or "recurse".startswith(body) or (
                word == "rm" and "r" in body and not "force".startswith(body))
    if not recursive:
        return ""
    for target in targets:
        if _parent_target(target, cwd, moved):
            return "%s %s %s" % (word, "/s" if cmd_verb else "-r", target)
    return ""


PARENT_DELETE_REASON = (
    "Rule (shared trees): this deletes the working folder, a folder above it, or everything in one "
    "of them. The loss reaches files that no session here can see. "
    "Remedy: name the one directory you mean, below the working folder, such as build."
)
PARENT_MOVED_REASON = (
    "Rule (shared trees): this deletes `.` or a parent of it after a folder change, and this hook "
    "does not follow the folder change, so it cannot tell which folder that is. "
    "Remedy: %s"
)
PARENT_MOVED_REMEDY = {
    False: "`rm -rf ./build/*` empties a folder, and `rm -rf build` deletes it by name.",
    True: "`Remove-Item -Recurse build` deletes a folder by name.",
}


def parent_delete_hit(segments, number: int, cwd: str):
    """(matched text, reason) when `segments[number]` runs a recursive delete of `.`, a relative
    parent, the working folder or a folder above it, else ('', ''). Any folder-change command in an
    earlier segment makes the reason name the rewrite that passes."""
    moved = any(
        tokens and _segment_cd_move(tokens) is not None
        for tokens in map(segment_tokens, segments[:number]))
    segment = segments[number]
    matched = _command_hit(
        segment, DELETE_WORDS, lambda args, word: _parent_delete_text(args, word, cwd, moved),
        RM_PARENT_RAW, by_word=True)
    if not matched:
        return "", ""
    if moved and REL_PARENT.fullmatch(_pwd_as_dot(matched.split()[-1].strip("'\""))):
        return matched, PARENT_MOVED_REASON % PARENT_MOVED_REMEDY[is_powershell(segment)]
    return matched, PARENT_DELETE_REASON


# ------------------------------------------------------------------ a link to another install
#
# Some worktrees link their node_modules to another checkout's install with a junction or a symlink.
# Through that link a hand-run `npm ci`, or a recursive delete of what is inside it, empties the
# other checkout's install. The rule reads the filesystem: a real folder, or none, is judged as it
# always was. A bare `rm node_modules` removes only the link, so it stays allowed.
# ponytail: `-w` and `--workspace` are not read; the install is judged against the working folder
# alone, and `install-test` and its aliases are not listed.
NPM_ALIASES = {
    "ci": "ci", "clean-install": "ci", "install-clean": "ci", "ic": "ci", "cit": "ci",
    "install": "install", "i": "install", "in": "install", "ins": "install", "isntall": "install",
    "add": "install", "uninstall": "uninstall", "remove": "uninstall", "rm": "uninstall",
    "r": "uninstall", "un": "uninstall", "update": "update", "up": "update", "upgrade": "update",
}
# Global options that take the next word as their value, so that word is not the subcommand.
NPM_VALUE_FLAGS = {
    "--loglevel", "--prefix", "--cache", "--registry", "--userconfig", "--globalconfig",
    "--workspace", "-w", "--tag", "--otp", "--scope", "--before", "--omit", "--include",
    "--install-strategy", "--logs-dir",
}
# Options after which the command changes nothing in the working folder's install.
NPM_NO_CHANGE = {"-g", "--global", "--location=global", "--help", "-h", "--dry-run"}
DELETE_WORDS = ("rm", "remove-item", "ri", "del", "erase", "rd", "rmdir")


def _nm_recursive_delete(args) -> bool:
    """True when the delete arguments hold a recursive flag: `-r`, `-R`, `-rf`, `--recursive`, or
    a PowerShell `-Recurse` spelled in full or in part."""
    for arg in args:
        flag = arg.lower()
        if flag == "--recursive" or (len(flag) > 1 and "-recurse".startswith(flag)) or (
                re.fullmatch(r"-[rfivd]*r[rfivd]*", flag)):
            return True
    return False


def is_link(path: str) -> bool:
    """True for a symlink, or a junction. A junction is a reparse point: `os.path.isjunction` reads
    it only from Python 3.12, so the file attribute is read instead."""
    if os.path.islink(path):
        return True
    if os.name != "nt":
        return False
    try:
        return bool(os.stat(path, follow_symlinks=False).st_file_attributes
                    & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except OSError:
        return False


def _nm_inside(arg: str, where: str) -> str:
    """The folder whose `node_modules` this path reaches into, or '' when it names no file inside
    one. `node_modules` alone is the link itself, so it names none."""
    parts = arg.replace("\\", "/").split("/")
    for at, part in enumerate(parts):
        if part.lower() == "node_modules":
            return _absolute("/".join(parts[:at]) or ".", where) if at + 1 < len(parts) else ""
    return ""


def npm_prefix(where: str) -> str:
    """The folder npm installs into, as `npm prefix` finds it: the first folder from `where` upward
    that holds a package.json or a node_modules. With none up to the drive root, npm uses `where`."""
    folder = where
    while True:
        if any(os.path.lexists(os.path.join(folder, name)) for name in ("package.json", "node_modules")):
            return folder
        parent = os.path.dirname(folder)
        if parent == folder:
            return where
        folder = parent


def npm_prefix_flag(words, where: str) -> str:
    """The folder `--prefix <dir>` or `--prefix=<dir>` names, from `where` when relative, else ''. npm uses
    that folder as the prefix as it stands, with no walk upward. The last flag wins, as in npm."""
    value = ""
    for at, word in enumerate(words):
        if word == "--prefix" and at + 1 < len(words):
            value = words[at + 1]
        elif word.startswith("--prefix="):
            value = word[len("--prefix="):]
    value = value.strip("\"'")
    if "$" in value or "`" in value or value.startswith("~"):
        return ""  # the shell fills these in, so the guard cannot name the folder: the walk from `where` decides
    return os.path.join(where, value) if value else ""


def linked_nm_hit(segment: str, where: str) -> str:
    """Return the matched text when one segment runs a dependency install in `where`, or a
    recursive delete of what is inside a `node_modules`, and that `node_modules` is a link, else ''."""
    def delete(args):
        if _nm_recursive_delete(args) and any(
                (folder := _nm_inside(arg, where)) and is_link(os.path.join(folder, "node_modules"))
                for arg in args):
            return "recursive delete inside a linked node_modules"
        return ""

    def install(args):
        # A `)` glued to the last word closes the subshell or substitution the command sits in.
        words = [arg.rstrip(")") for arg in args]
        subcommand, at = "", 0
        while at < len(words):
            if words[at] in NPM_VALUE_FLAGS:
                at += 2
            elif words[at].startswith("-"):
                at += 1
            else:
                subcommand = NPM_ALIASES.get(words[at].lower(), "")
                break
        if subcommand and not NPM_NO_CHANGE.intersection(words) and is_link(
                os.path.join(npm_prefix_flag(words, where) or npm_prefix(where), "node_modules")):
            return "npm " + subcommand + " in a folder whose node_modules is a link"
        return ""

    return _command_hit(segment, DELETE_WORDS, delete) or _command_hit(segment, ("npm", "npm.cmd"), install)


LINKED_NM_REASON = (
    "node_modules here is a link to another checkout's install, and this command would change that "
    "install through the link, for every checkout that shares it. "
    "Remedy: replace the link with a real folder first, for example with the repo's setup script "
    "(npm run setup where it exists), then run the command again. "
    "(decision guard-linked-node-modules, a command that would change another checkout's install through a link is refused)"
)


DELETE_REASON = (
    "Rule (shared trees): this deletes a whole root, a home directory or everything a "
    "glob matches. The loss reaches files that no session here can see. "
    "Remedy: name the one directory you mean, under the project or under the scratchpad."
)

# THE CMD.EXE VERBS. `rd`/`rmdir` and `del`/`erase` take slash flags, never `rm`'s or
# `Remove-Item`'s dash flags, so neither pattern above ever reads them: `/s` is the recurse
# switch, and `/q` (optional, never required) only silences the confirmation prompt.
# `rd /s /q C:\Users\x`, `cmd /c rd /s /q %USERPROFILE%` and `del /s /q C:\*` deny, as their twins do.
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
PUSH_MAIN_REASON = (
    "Rule (Git): this push writes the default branch, main or master. Main moves only by pull request "
    "(rule git-main-only-by-pr, decision plain-push-asks). Approving the prompt lets this one push through; it is not a grant."
)
PUSH_STRAY_REASON = (
    "Rule (Git): this push writes a branch name other than the one this branch tracks (its upstream), "
    "so it may land on a stray branch. Check the destination (decision plain-push-asks). "
    "Approving the prompt lets this one push through; it is not a grant."
)
PUSH_UNREAD_REASON = (
    "Rule (Git): this push takes its destination from the folder it runs in, and that folder cannot be read "
    "(a cd through a variable or $(...), or a -C folder that is not there), so where it writes is unknown "
    "(decision plain-push-asks). Approving the prompt lets this one push through; it is not a grant."
)
PUSH_ASK_REASON = (
    "Rule (Git): this forced push may rewrite the default branch, or its target is unreadable. "
    "The click in this prompt is the grant."
)

# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
