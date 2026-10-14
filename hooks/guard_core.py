"""The guard's shared code: stream encoding, shell segments, heredoc bodies, git call parsing,
command roots, tree and worktree reads, session liveness, the config folder, and the log.

guard.py is the only entry point. It loads this module from its own folder (decision
guard-split-by-family). Other files reach these names through `guard`. A test or the janitor
that patches one of them patches it here, on the one object that every caller reads.
"""
import errno
import functools
import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime


# ------------------------------------------------------------------ the stream encoding
#
# MEASURED 2026-09-09 in a Claude Code session on Windows: `sys.stderr.encoding` was `cp1252`, so
# an em dash in a refusal was written as the single byte 0x97. Claude Code decodes the stream as
# UTF-8, and 0x97 is not valid UTF-8, so it arrived as one replacement character.
#
# ONE replacement character per em dash is the whole measurement, and it names the direction. cp1252
# bytes read as UTF-8 give exactly that. UTF-8 bytes read as cp1252 would have given three mojibake
# characters instead. So the consumer was right and the writer was wrong.
#
# It is not cosmetic. A refusal exists to SAY what to do instead. A mangled dash is merely ugly, but
# the same corruption on a path or a flag would destroy the remedy the message carries.
#
# It never raises. `reconfigure` landed in Python 3.7 and a stream can be something other than a
# text wrapper, so a failure here leaves the old encoding rather than bricking the hook.
def _force_utf8_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


SHELL_TOOLS = ("Bash", "PowerShell")
READ_ONLY_TOOLS = ("Read", "Grep")
WRITE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")


def norm(path: str) -> str:
    return path.replace("\\", "/")


def basename(token: str) -> str:
    return token.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()


@functools.lru_cache(maxsize=8)
def _split_segments_cached(cmd: str, powershell: bool):
    # powershell is part of the key: split_segments reads POWERSHELL_CALL[0] too
    return tuple(split_segments(cmd, []))


# ------------------------------------------------------------------ shell segments and command words
#
# ONE SHELL SEGMENT of the command. Each segment is judged on its own, so an allowed first half
# licenses nothing in the second half.
#
# QUOTE-AWARE, deliberately, and the only splitter left in the file. A blind split on `|` and
# `;` cuts a quoted argument that happens to hold one of those characters into a segment of its
# own, and whatever word lands first in that fragment then reads as a COMMAND. MEASURED: the
# owner's `grep -n -i "...|make reap|pkill..." CLAUDE.md` splits on the pipes INSIDE the quotes
# under a blind splitter, and one fragment starts with `pkill`. A rule that then judged the
# fragment's first word would deny a grep as if it were a kill.
def split_segments(cmd: str, ends=None):
    """Split into shell segments on unquoted `;`, `|`, `||`, `&&`, and newline.

    Quoted text, single or double, is copied whole into the current segment, so a delimiter
    inside a quote never starts a new one. An unterminated quote runs to the end of the string,
    which keeps the remainder inside it rather than guessing where it would have closed.

    THE COMMENT RULE, measured before it was written: without it, the `'` in `# the driver's
    shape` opens a quote that runs to the end of the text, and `guard-shell-selftest.sh`'s
    runaway-driver fixture — a script whose second line is exactly that comment — went from
    refused to ALLOWED once the parent's per-line reader was replaced by this function. An
    unquoted `#` that STARTS A WORD (index 0, or the previous character is space, tab,
    newline, `;`, `|`, `&`, or `(`) is a comment to the end of its line — the shell's own
    rule. `fix#3` and `'#300'` are not comments under it.

    `ends`, when a list, gets what closed each segment (`|`, `||`, `&&`, `;`, newline, or '' for
    the last), so a caller can tell a segment whose stdout is piped onward from the rest.
    """
    if ends is None:   # the same command is split by many rules: split it once
        return list(_split_segments_cached(cmd, POWERSHELL_CALL[0]))
    segments = []
    current = []
    quote = ""
    index = 0
    length = len(cmd)
    while index < length:
        char = cmd[index]
        if quote:
            current.append(char)
            if char == quote:
                quote = ""
            index += 1
            continue
        if char == "#" and (index == 0 or cmd[index - 1] in " \t\n;|&("):
            while index < length and cmd[index] != "\n":
                index += 1
            continue
        if char == "\\" and cmd[index + 1:index + 2] == "\\":
            current.append(cmd[index:index + 2])   # an escaped backslash, so no continuation
            index += 2
            continue
        if char == "\\" and cmd[index + 1:index + 2] == "\n" and not POWERSHELL_CALL[0]:
            index += 2   # a POSIX backslash-newline is a continuation; in PowerShell it ends a path
            continue
        if char in ("'", '"'):
            quote = char
            current.append(char)
            index += 1
            continue
        if char == "&" and cmd[index:index + 2] == "&&":
            segments.append("".join(current))
            ends is None or ends.append("&&")
            current = []
            index += 2
            continue
        if char == "|" and cmd[index - 1:index] == ">":
            current.append(char)   # `>|` overrides noclobber: a redirect, no pipe
            index += 1
            continue
        if char == "|":
            width = 2 if cmd[index:index + 2] == "||" else 1
            ends is None or ends.append(cmd[index:index + width])
            index += width
            segments.append("".join(current))
            current = []
            continue
        if char in (";", "\n"):
            segments.append("".join(current))
            ends is None or ends.append(char)
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    segments.append("".join(current))
    ends is None or ends.append("")
    return segments


# A leading `VAR=value` assignment, which is not a segment's command. Shared with the
# environment layer below, so the two never drift into judging an assignment two different ways.
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

# PowerShell's own assignment, `$name = value`, two tokens under shlex rather than one: `$sg`
# then `=`. MEASURED against a real launch, `$sg = Start-Process npx ... -PassThru`, the exact
# shape PowerShell's own remedy for rule 2b recommends. Before this, `resolve_command` read
# `$sg` itself as the command word on that line, which matches no rule's tool name, so every
# command-word rule silently missed the real command sitting right after it.
POWERSHELL_ASSIGNMENT = re.compile(r"^\$[A-Za-z_][A-Za-z0-9_]*$")

# A wrapper that runs another program in its place, so the CALLED program is a segment's real
# command word, not the wrapper. `xargs pkill foo` runs pkill, so `xargs` unwraps the same as
# the rest: the token after it, once its own flags are skipped, is what actually runs.
COMMAND_WRAPPERS = {"sudo", "env", "command", "nohup", "nice", "time", "doas", "xargs",
                    "timeout", "verdict", "python", "python3"}
# `timeout` and `python` unwrap only in their wrapper shape: `timeout [flags] DURATION cmd` (Windows
# `timeout /t 5` is the waiter, not a wrapper) and `python bin/verdict cmd` (the repo's runner).
DURATION = re.compile(r"^\d+(\.\d+)?[smhd]?$")
TIMEOUT_FLAGS_WITH_VALUE = {"-k", "-s", "--kill-after", "--signal"}
TIMEOUT_FLAGS_BARE = {"--preserve-status", "--foreground"}

# A leading shell keyword that opens or joins a control-flow block, never a command itself.
# `split_segments` cuts on `;`, so the segment after a loop's own semicolon starts with `do`, and
# the word after THAT is the command. MEASURED against the live guard: `while ! pgrep -f server;
# do sleep 1; done` allowed the sleep, because the segment `do sleep 1` resolved to `do` as its
# command word. Skip a keyword the same way a wrapper is skipped, so every rule that reads a
# command word sees the command inside the block, never the keyword that opens it.
LOOP_KEYWORDS = {"do", "then", "else", "elif", "while", "until", "if", "{", "("}


def segment_tokens(segment: str):
    """Tokenize one segment with shlex, or return None when it cannot be parsed.

    An unmatched quote or a stray backslash means the guard cannot tell what the segment would
    run. That must fail open, this file's existing stance: judge nothing rather than guess.
    """
    # PowerShell's escape is the backtick, so a backslash there is a path separator. Doubling it
    # keeps posix shlex from eating it (`C:\\repo` would read as `C:repo`).
    if POWERSHELL_CALL[0]:
        segment = segment.replace("\\", "\\\\")
    found = _segment_tokens(segment)
    return None if found is None else list(found)


@functools.lru_cache(maxsize=16384)   # holds every distinct segment of a 4000-rm command
def _segment_tokens(segment: str):
    try:
        return tuple(shlex.split(segment, posix=True))
    except ValueError:
        return None


POWERSHELL_CALL = [False]   # set per call by judge_shell: the tool being judged is PowerShell


def _skip_assignments_and_keywords(tokens, index=0):
    """Return the index of the first token that is neither an assignment (POSIX `VAR=value` or
    PowerShell `$name` `=`) nor a leading loop keyword, starting from `index`. Shared by
    `resolve_command`, which then unwraps wrappers from there, and by the detached-launch
    checks below, which must see a wrapper such as `nohup` BEFORE any unwrap, not after."""
    end = len(tokens)
    while index < end:
        if ASSIGNMENT.match(tokens[index]) or tokens[index] in LOOP_KEYWORDS:
            index += 1
            continue
        if tokens[index][:1] == "(" and ASSIGNMENT.match(tokens[index][1:]):
            index += 1   # `(VAR=x cmd`: a subshell paren glued to the first assignment
            continue
        if (POWERSHELL_ASSIGNMENT.match(tokens[index]) and index + 1 < end
                and tokens[index + 1] == "="):
            index += 2
            continue
        break
    return index


def resolve_command(tokens):
    """Return the index of the command word in a tokenized segment, or None when it names none.

    Skips leading `VAR=value` assignments and leading loop keywords (`do`, `then`, `else`,
    `elif`, `while`, `until`, `if`, `{`, `(`), then unwraps command wrappers (`sudo`, `env`,
    `command`, `nohup`, `nice`, `time`, `doas`, `xargs`) along with each wrapper's own flags and
    any assignment it takes ahead of the program name, so the index returned is the program that
    actually runs, never the keyword or the wrapper carrying it there.
    """
    return _resolve_command(tuple(tokens))


@functools.lru_cache(maxsize=4096)   # every rule asks again for each segment of a long command
def _resolve_command(tokens):
    end = len(tokens)
    index = _skip_assignments_and_keywords(tokens)
    while index < end and basename(tokens[index]) in COMMAND_WRAPPERS:
        word, start = basename(tokens[index]), index
        index += 1
        while index < end and tokens[index].startswith("-"):
            index += 2 if word == "timeout" and tokens[index] in TIMEOUT_FLAGS_WITH_VALUE else 1
        if word == "timeout" and not (index < end and DURATION.match(tokens[index])):
            return start
        if word == "timeout":
            index += 1
        if word in ("python", "python3"):
            if not (index < end and basename(tokens[index]) == "verdict"):
                return start
            index += 1
        while index < end and ASSIGNMENT.match(tokens[index]):
            index += 1
    return index if index < end else None


# ------------------------------------------------------------------ heredoc bodies
#
# A heredoc body is DATA being written, not a command being run. A commit message that DISCUSSES a
# refused command must not trip the guard. MEASURED in job-cost-reporting on 2026-08-20: a commit
# message naming the protected folder was refused, and that was one of three false positives in the
# guard's first week.
#
# The HEADER LINE is kept, so a redirect in the header still counts as a write:
# `cat <<'EOF' > .claude/settings.json` writes the settings file.
#
# EXCEPTION: a heredoc fed to an interpreter can be executed, so the body stays under inspection.
HEREDOC_HEADER = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
INTERPRETER_HEREDOC = re.compile(
    r"\b(bash|sh|zsh|dash|ksh|python3?|perl|ruby|node)\b[^\n]*<<"
)


def _split_heredocs(cmd: str):
    """Return (kept lines, [(quote, body)]): every header line kept, every body set apart.
    The one walk `_drop_heredoc_bodies` and the environment layer both need."""
    lines = cmd.split("\n")
    kept = []
    bodies = []
    index = 0
    while index < len(lines):
        line = lines[index]
        kept.append(line)
        match = HEREDOC_HEADER.search(line)
        index += 1
        if not match:
            continue
        delimiter = match.group(2)
        start = index
        while index < len(lines) and lines[index].strip() != delimiter:
            index += 1
        bodies.append((match.group(1), "\n".join(lines[start:index])))
        if index < len(lines):
            index += 1  # drop the closing delimiter line too
    return kept, bodies


def _drop_heredoc_bodies(cmd: str) -> str:
    """Drop the body of every heredoc, keeping every header line. The one loop
    `strip_heredoc_bodies` and `_strip_heredoc_bodies_unconditionally` both need: the first
    guards it with the interpreter exception, the second never does, and neither re-implements
    the walk itself."""
    return "\n".join(_split_heredocs(cmd)[0])


def strip_heredoc_bodies(cmd: str) -> str:
    """Drop the body of every heredoc, and keep every header line."""
    if INTERPRETER_HEREDOC.search(cmd):
        return cmd  # the body may be executed, so keep it under inspection
    return _drop_heredoc_bodies(cmd)


# ------------------------------------------------------------------ git call parsing
#
# Judge the BEHAVIOUR of a git call, not the text beside it. `git checkout -b name` and
# `git checkout main` move a branch and keep every file, so they pass. `git checkout <path>`
# overwrites a file from the index, so it is refused.

# `git` reads these options before the subcommand, and each one takes a value.
GIT_OPT_WITH_VALUE = {
    "-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path",
    "--super-prefix", "--config-env",
}

# `stash`, `reset`, and `restore` each cover both a read and a discard, so the SUBCOMMAND NAME
# alone never proves the act. MEASURED: `git stash list` only reads, yet it tripped this rule
# under the old name match. The predicates below read the ACT each one takes, never the spelling
# of the subcommand.

# These options are followed by a NEW branch name, which is never a path.
GIT_CHECKOUT_TAKES_NAME = {"-b", "-B", "--orphan"}

# An argument shaped like a file, not like a branch. A branch name may hold a slash
# (`claude/my-lane`), so a slash alone proves nothing. An extension, a leading `./`, a drive letter
# or a backslash does.
PATH_PREFIX = re.compile(r"^(?:\.{1,2}$|\.{1,2}[/\\]|[/~]|[A-Za-z]:[/\\])")
PATH_EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,6}$")

# A shell redirection, dropped before a segment is tokenized for a git call. `2>&1` is a false
# positive, MEASURED in guard.log: `git checkout origin/claude/pass3-seam 2>&1` was refused as
# `git checkout origin/claude/pass3-seam` was not, because `2>&1` reached `git_calls` as one more
# plain word, and `checkout_names_a_path` reads two plain words as a start point plus a path.
#
# The redirect information itself is NOT lost. The frozen-path rule reads it from `writes_to`,
# against the raw command text, which this function never touches. This regex only shrinks the
# copy that decides what a `git` call's OWN arguments are.
#
# Order matters: `&>file` starts with a literal `&`, which the third branch would not reach on its
# own, so it is tried first. The other three shapes (`>file`, `>>file`, `<file`, and the fd forms
# `2>&1`, `>&2`, `1>&2`) all share one greedy `\S+` for the target, spaced or not.
REDIRECTION = re.compile(
    r"&>>?\s*\S+"       # &>file, &>>file
    r"|<\s*\S+"         # <file
    r"|\d?>>?\s*\S+"    # >file, >>file, 2>file, 2>>file, 2>&1, >&2, 1>&2
)


def _git_subcommand_index(tokens, index: int) -> int:
    """Return the index of the subcommand of the `git` word at `index`, past git's own options."""
    cursor = index + 1
    while cursor < len(tokens):
        token = tokens[cursor]
        if token in GIT_OPT_WITH_VALUE:
            cursor += 2
            continue
        if token.startswith("-"):
            cursor += 1
            continue
        break
    return cursor


def git_calls(segment: str):
    """Return (subcommand, arguments) for every `git` call in one segment."""
    text = REDIRECTION.sub(" ", segment)
    # shlex unquotes a pathspec (`'*.json'`, `"f.txt"`); a segment it cannot parse falls back to
    # a whitespace split, the old reader.
    tokens = segment_tokens(text)
    if tokens is None:
        tokens = text.split()
    calls = []
    index = 0
    while index < len(tokens):
        if basename(tokens[index]) in ("git", "git.exe"):
            cursor = _git_subcommand_index(tokens, index)
            if cursor < len(tokens):
                calls.append((tokens[cursor].lower(), tokens[cursor + 1:]))
            index = cursor + 1
            continue
        index += 1
    return calls


def long_flag_abbrev(arg: str, full: str, shortest: str) -> bool:
    """True when `arg` spells the long flag `full`, or a prefix of it at least as long as
    `shortest`. Git's parse-options accepts any unique prefix; `shortest` is the shortest one
    that no other option of the command shares. A `=value` tail is ignored."""
    name = arg.split("=", 1)[0]
    return len(name) >= len(shortest) and full.startswith(name)


def pathspec_from_file_flag(arg: str) -> bool:
    """True for `--pathspec-from-file` or any prefix of it git accepts (`--pathspec-from`, ...)."""
    return long_flag_abbrev(arg, "--pathspec-from-file", "--pathspec-f")


# ------------------------------------------------------------------ which tree the command runs in
#
# THE COMMAND IS JUDGED WHERE IT RUNS, NOT WHERE THE HOOK LIVES. A lane is built in a worktree and a
# discard there loses only that lane's own work, so a worktree earns an "ask". The shared checkout is
# the owner's editor and every other session, so a discard there earns a "deny".
#
# The directory is the last `cd <path>` in the command, or a `git -C <path>`, or the shell's own cwd.
# MEASURED in job-cost-reporting on 2026-09-10: a gate that read the main checkout for every command
# judged a worktree command against another branch.
#
# READ OFF PARSED TOKENS, NOT THE RAW STRING. A regex over the raw text cannot tell a real `cd`
# from one sitting inside a quoted argument or a `#` comment. MEASURED against this file before
# this fix: `bash -c 'true; cd /elsewhere; rm -rf x'; <destructive>` and `# note; cd
# /elsewhere\n<destructive>` both resolved to `/elsewhere`, because the old `CD_RE` only asked
# whether `cd` was preceded by `^`, `;`, `&`, or `|` in the raw text — true for both, despite the
# `cd` in each case never running. `split_segments` (quote- and comment-aware) plus
# `segment_tokens` (shlex) are the readers already used elsewhere in this file for the same
# reason. Lifted from `~/Developer/banchi/scripts/shell_parse.py`, which paid this debt first
# by reading `cd` and `git -C` off tokens instead of a raw-text regex.
# `--work-tree` NAMES THE TREE THE FILES COME FROM, and it outranks `-C` and a `cd`, because git
# applies it after both. MEASURED 2026-09-19 with real git: from a CLEAN checkout A,
# `git --work-tree=B status --porcelain` reported B's modified file and B's untracked file. The
# files a call discards are B's, so B is the tree this rule must judge. Both the `=` and the
# spaced form are read, because git takes either. This one stays a raw-text regex: it is outside
# this fix's scope (the recorded debt named only `_run_dir`'s `cd`/`git -C` reading).
GIT_WORK_TREE_RE = re.compile(r"--work-tree(?:=|\s+)(['\"]?)([^'\";&|\s]+)\1")


def _segment_cd_target(tokens):
    """Return the path a tokenized segment's `cd` would take, or None when it names none, or
    when the segment's command word is not `cd`."""
    index = resolve_command(tokens)
    if index is None or basename(tokens[index]) != "cd":
        return None
    for token in tokens[index + 1:]:
        if token.startswith("-"):
            continue
        return token
    return None


def _segment_git_c_target(tokens):
    """Return a tokenized segment's `git -C <path>` target, or None when it names none, or
    when the segment's command word is not `git`.

    ONLY THE SPACED FORM, `-C <path>`, IS READ. MEASURED against the real binary: `git
    -C/some/path status` and `git -C=/some/path status` both fail with `unknown option:
    -C/some/path` (or `-C=...`) and never run. An earlier version of this function also
    accepted an attached `-C<path>` as if it named a tree, which let a command text attach any
    path it liked to `-C` and have `_run_dir` read that path as though it were real, even
    though git itself refused the call and the command ran wherever the shell's own cwd (or an
    earlier, real `cd`) put it. Found in review of PR #75, reproduced against real git and
    against the live guard: the attached form ALLOWED a `git reset --hard HEAD` that ran in a
    real dirty checkout, because the fake `-C<path>` pointed the subject read at an unrelated
    clean one.
    """
    index = resolve_command(tokens)
    if index is None or basename(tokens[index]) not in ("git", "git.exe"):
        return None
    cursor = index + 1
    found = None
    while cursor < len(tokens):
        token = tokens[cursor]
        if token == "-C":
            if cursor + 1 >= len(tokens):
                return None
            value = tokens[cursor + 1]
            # git chains every `-C`: a relative one joins onto the one before it
            found = os.path.join(found, value) if found and value else (value or found)
            cursor += 2
            continue
        if token in GIT_OPT_WITH_VALUE:
            cursor += 2
            continue
        if token.startswith("-"):
            cursor += 1
            continue
        break
    return found


def _absolute(where: str, shell_cwd: str) -> str:
    """Expand and absolutize one directory taken from a command."""
    where = os.path.expandvars(os.path.expanduser(where))
    if re.match(r"^/[a-zA-Z]/", where):  # Git Bash `/c/Users/...` to `C:/Users/...`
        where = where[1].upper() + ":" + where[2:]
    # Python 3.13 and later on Windows: a bare `/x` is not absolute, so test the converted
    # form, and only then join a relative path onto the cwd.
    if not os.path.isabs(where) and shell_cwd:
        where = os.path.join(shell_cwd, where)
    return where


def _strip_heredoc_bodies_unconditionally(cmd: str) -> str:
    """Drop the body of every heredoc, header line kept, even one fed to an interpreter.

    `strip_heredoc_bodies` keeps an INTERPRETER heredoc's body under inspection, on purpose,
    because that body may be executed. But "may be executed" means the INTERPRETER runs it, not
    the outer shell: a `cd` inside a `python3 <<'EOF'` body changes python's notion of a
    directory, never the outer shell's cwd, so `_run_dir` must never read it as a live segment.
    Found in review of PR #75, reproduced against the live guard: a `cd <clean checkout>` line
    inside such a body ALLOWED a `git reset --hard HEAD` that actually ran in a real dirty
    checkout named by the command's own cwd, because `_run_dir` read the heredoc body's `cd` as
    though the outer shell had run it. `_run_dir` is the only caller that wants the interpreter
    body dropped this way; every other caller of `strip_heredoc_bodies` still needs that body
    kept for its OWN question, which is what a write or a refused command might say, not where
    the shell sits. The walk itself is `_drop_heredoc_bodies`, shared with that function.
    """
    return _drop_heredoc_bodies(cmd)


def _run_dir(cmd: str, shell_cwd: str) -> str:
    """Return the directory the command RUNS in: a `git -C`, else the last `cd`, else the cwd.

    This is the part both roots share. Neither `--work-tree` nor `--git-dir` is read here,
    because each answers a different question and each belongs to one caller.

    READ OFF TOKENS, PER SEGMENT, not a regex over the raw string: a `cd` or `git -C` sitting
    inside a quoted argument or a `#` comment is text, not a command, and only a segment that
    tokenizes to `cd`/`git` as its OWN command word (via `resolve_command`, which already steps
    over wrappers and loop keywords) counts. A segment that fails to tokenize (an unmatched
    quote) is skipped, the same fail-open stance `segment_tokens` documents elsewhere. The FIRST
    `git -C` found, across all segments in order, still wins over every `cd`, matching this
    function's behaviour before this fix; failing that, the LAST `cd` found wins.

    HEREDOC BODIES ARE STRIPPED FIRST, unconditionally, even an interpreter body that
    `strip_heredoc_bodies` keeps for other callers: a `cd` line inside one never moves the
    OUTER shell, which is the tree this function answers about.
    """
    cmd = _strip_heredoc_bodies_unconditionally(cmd)
    where = None
    last_cd = None
    for segment in split_segments(cmd):
        tokens = segment_tokens(segment)
        if tokens is None:
            continue
        if where is None:
            git_c = _segment_git_c_target(tokens)
            if git_c is not None:
                where = git_c
        cd = _segment_cd_target(tokens)
        if cd is not None:
            last_cd = cd
    if where is None:
        where = last_cd
    if where:
        where = _absolute(where, shell_cwd)
    return where or shell_cwd or ""


def command_root(cmd: str, shell_cwd: str) -> str:
    """Return the WORKING TREE the command acts on.

    This answers "whose files does this call write or discard". It is NOT the answer to "whose
    HEAD does this call move": a git directory and a work tree are set separately and can name
    two different checkouts. `head_root` answers that second question.
    """
    match = GIT_WORK_TREE_RE.search(cmd)
    if match:
        return _absolute(match.group(2), _run_dir(cmd, shell_cwd))
    return _run_dir(cmd, shell_cwd)


def _git(where: str, *args):
    try:
        return subprocess.run(
            ["git", "-C", where, *args], capture_output=True, encoding="utf-8", errors="replace", timeout=10
        )
    except Exception:
        return None


def is_worktree(where: str):
    """True in a linked worktree, False in an ordinary checkout, None when unknown.

    A worktree is the tree whose git directory differs from the repository's common git directory.
    MEASURED on this machine: an ordinary checkout answers `.git` to both questions, while a linked
    worktree answers `<repo>/.git/worktrees/<name>` and `<repo>/.git`.
    """
    if not where or not os.path.isdir(where):
        return None
    top = _git(where, "rev-parse", "--show-toplevel")
    if top is None or top.returncode != 0 or not top.stdout.strip():
        return None
    root = top.stdout.strip()
    answer = _git(root, "rev-parse", "--git-dir", "--git-common-dir")
    if answer is None or answer.returncode != 0:
        return None
    lines = answer.stdout.splitlines()
    if len(lines) < 2:
        return None
    own = os.path.normcase(os.path.realpath(os.path.join(root, lines[0].strip())))
    common = os.path.normcase(os.path.realpath(os.path.join(root, lines[1].strip())))
    return own != common


def _common_dir(where: str):
    """Return the absolute, realpath'd git COMMON directory for `where`, or None when it could
    not be read. `git rev-parse --show-toplevel` answers `where` itself when `where` sits inside
    an ordinary checkout, but it answers the WORKTREE's own path when `where` sits inside a
    linked worktree. `git rev-parse --git-common-dir` names the ONE `.git` directory every
    worktree of a clone shares. Two `_git` calls, on purpose: the toplevel, then
    `--git-common-dir` run FROM that toplevel.

    The one read `primary_checkout` and `git_common_dir` both build on, so the two never drift
    apart (CLAUDE.md, "building-allow-list-is-the-constant").
    """
    top = _git(where, "rev-parse", "--show-toplevel")
    if top is None or top.returncode != 0:
        return None
    toplevel = top.stdout.strip()
    if not toplevel:
        return None
    common = _git(toplevel, "rev-parse", "--git-common-dir")
    if common is None or common.returncode != 0:
        return None
    common_dir = common.stdout.strip()
    if not common_dir:
        return None
    try:
        return os.path.realpath(os.path.join(toplevel, common_dir))
    except Exception:
        return None


def primary_checkout(where: str):
    """Return the PRIMARY checkout that `where` belongs to, or None when it could not be read.

    The common directory's parent (`dirname`) is always the primary checkout, ordinary checkout
    or linked worktree alike.

    Callers that need this to name a remedy (`janitor/install_launchd.py`) or to sweep the right
    repository (`janitor/session_end_sweep.py`) both used to carry their own copy of this same
    read; this is the one constant they now both point at (CLAUDE.md,
    "building-allow-list-is-the-constant").
    """
    common_dir = _common_dir(where)
    if not common_dir:
        return None
    primary = os.path.dirname(common_dir)
    if not primary or not os.path.isdir(primary):
        return None
    return primary


def git_common_dir(where: str):
    """Return the absolute git common directory for `where`, or None when it could not be read.

    This is the directory every worktree of the clone shares, so a record written here survives
    the removal of any one worktree. See `agent_home_record_path`.
    """
    return _common_dir(where)


def _inside_work_tree(where: str):
    """True inside a git working tree, False when git says this is no git tree, None when git
    gives no answer at all (git missing, a timeout, a crash).
    """
    if not where:
        return False
    answer = _git(where, "rev-parse", "--is-inside-work-tree")
    if answer is None:
        return None
    if answer.returncode == 0:
        return answer.stdout.strip() == "true"
    return False


def porcelain(where: str, pathspecs=(), ignored: bool = False):
    """Return the lines of `git status --porcelain`, or None when it cannot be read."""
    args = ["status", "--porcelain"]
    if ignored:
        args.append("--ignored")
    if pathspecs:
        args.append("--")
        args.extend(pathspecs)
    answer = _git(where, *args)
    if answer is None or answer.returncode != 0:
        return None
    return [line for line in answer.stdout.splitlines() if line.strip()]


def stash_stack(where: str):
    """Return the lines of `git stash list`, or None when it cannot be read."""
    answer = _git(where, "stash", "list")
    if answer is None or answer.returncode != 0:
        return None
    return [line for line in answer.stdout.splitlines() if line.strip()]


# ------------------------------------------------------------------ a branch's only copy
#
# `git branch -d/-D <name>` throws away a branch pointer. The FILES never move, so this is not a
# working-tree read at all: the subject is the WORK the branch names, and the question is whether
# that work exists anywhere else.
#
# Resolve the base in this order: `origin/HEAD`, then local `main`, then local `master` (owner's
# ruling, this plan). None answering is UNREADABLE, never a silent pass and never a silent deny:
# a repository with no default branch this rule can find is one this rule cannot judge.
#
# THREE TESTS, ANY ONE PASSING PROVES THE WORK SURVIVES the branch:
#   ancestor       `git merge-base --is-ancestor <branch> <base>`. The branch's tip is already
#                  reachable from the base, commit id for commit id.
#   cherry-empty   `git cherry <base> <branch>` prints a `+` for every commit NOT already on the
#                  base by PATCH id, so no `+` line means every commit's content is already
#                  there, even after a rebase changed every commit id.
#   remote-contains a remote-tracking ref's history already contains the branch's tip, so a
#                  clone elsewhere holds the same commit.
# Any one of the three failing to ANSWER (not "false", but "git could not tell") makes the whole
# read unreadable, because a read that skipped a test it could not run is a guess, not a proof.
def resolve_default_base(where: str):
    """Return the ref name of the repository's default branch, or None when none answers.

    `origin/HEAD` first, then local `main`, then local `master` (owner's ruling). A branch is
    read against whichever one resolves; the others are never tried once one does.
    """
    origin_head = _git(where, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
    if origin_head is not None and origin_head.returncode == 0 and origin_head.stdout.strip():
        ref = origin_head.stdout.strip()
        live = _git(where, "rev-parse", "--verify", "--quiet", ref + "^{commit}")
        if live is None:  # git could not run: unreadable, never "does not exist"
            return None
        if live.returncode == 0:  # a dangling origin/HEAD (git answered no) falls through
            return ref
    for name in ("main", "master"):
        answer = _git(where, "rev-parse", "--verify", "-q", "refs/heads/" + name)
        if answer is not None and answer.returncode == 0:
            return name
    return None


def branch_is_ancestor(where: str, base: str, branch: str):
    """True when `branch`'s tip is already reachable from `base`, False when it plainly is not,
    None when the question could not be answered (an unresolvable revision, a git that would not
    run)."""
    answer = _git(where, "merge-base", "--is-ancestor", branch, base)
    if answer is None:
        return None
    if answer.returncode == 0:
        return True
    if answer.returncode == 1:
        return False
    return None


def branch_cherry_empty(where: str, base: str, branch: str):
    """True when `git cherry <base> <branch>` prints no `+` line: every commit's PATCH already
    sits on the base, even one a rebase or a cherry-pick gave a new commit id. None when the
    read failed."""
    answer = _git(where, "cherry", base, branch)
    if answer is None or answer.returncode != 0:
        return None
    return not any(line.startswith("+") for line in answer.stdout.splitlines())


def branch_on_remote(where: str, branch: str):
    """True when some remote-tracking ref's history already contains `branch`'s tip, False when
    none does, None when the read failed."""
    answer = _git(
        where, "for-each-ref", "--contains", branch, "--format=%(refname)", "refs/remotes"
    )
    if answer is None or answer.returncode != 0:
        return None
    return bool(answer.stdout.strip())


def branch_is_empty(where: str, base: str, branch: str):
    """True when `branch` holds no work absent elsewhere, False when it holds the only copy,
    None when any one of the three tests could not be read."""
    ancestor = branch_is_ancestor(where, base, branch)
    if ancestor is None:
        return None
    if ancestor:
        return True
    cherry_empty = branch_cherry_empty(where, base, branch)
    if cherry_empty is None:
        return None
    if cherry_empty:
        return True
    on_remote = branch_on_remote(where, branch)
    if on_remote is None:
        return None
    return on_remote


# ------------------------------------------------------------------ a removed or pruned worktree
#
# `git worktree remove <path>` throws away one worktree's own files. Its subject lives at PATH,
# never at `where` (the checkout the command RUNS in): removing a worktree is ordinarily typed
# from the primary checkout or from any other worktree of the same clone, never from inside the
# tree it deletes.
#
# THREE THINGS MAKE THE SUBJECT NON-EMPTY, so the call denies: uncommitted or untracked work in
# that tree (`git status --porcelain`), a lock (`git worktree list --porcelain` naming it
# `locked`), or a LIVE SESSION still standing in it. None of the three is a guess: each is read
# straight off git or off the session record git-worktree-remove would run past.
def worktree_remove_target(args, where: str) -> str:
    """Return the absolute path a `git worktree remove` call would delete, or '' when it names
    none (`git worktree remove` with no path is not a call this rule can happen upon; the
    matcher already required at least the subcommand)."""
    for arg in args:
        if arg.startswith("-"):
            continue
        return _absolute(arg, where)
    return ""


def worktree_locked(where: str, target: str):
    """True when TARGET is registered as a locked worktree, False when it is registered and
    unlocked, None when the registration cannot be read, or TARGET is not a registered worktree
    of this clone at all (an unreadable state: nothing here says the removal is safe)."""
    answer = _git(where, "worktree", "list", "--porcelain")
    if answer is None or answer.returncode != 0:
        return None
    try:
        target_real = os.path.normcase(os.path.realpath(target))
    except Exception:
        return None
    for block in answer.stdout.split("\n\n"):
        lines = block.splitlines()
        if not lines or not lines[0].startswith("worktree "):
            continue
        path = lines[0][len("worktree "):].strip()
        if os.path.normcase(os.path.realpath(path)) != target_real:
            continue
        return any(line == "locked" or line.startswith("locked ") for line in lines[1:])
    return None


# Liveness reads `~/.claude/sessions/*.json` (or `${CLAUDE_CONFIG_DIR}/sessions`, the same
# override `config_dir` already answers for the frozen-path rule). A missing directory is a real,
# readable answer: zero sessions have ever recorded liveness here, so nothing stands in any tree.
# A directory that exists but cannot be LISTED is unreadable, and a bad individual record is
# skipped rather than treated as a read failure, so one corrupt file cannot make an otherwise
# readable directory look unreadable.
#
# MEASURED on Windows: a session record's `startedAt` is written 1.7 to 3.2 seconds after the
# kernel's own process-creation time. A correct read can fall outside a 5-second window under
# load, so the tolerance widens to 60 seconds on every platform.
SESSION_LIVE_TOLERANCE_MS = 60000

# `_process_start_ms` returns this sentinel, never `None`, when the read itself could not tell
# whether the process is alive or dead. `None` stays reserved for a CONFIRMED dead pid, so a
# caller can never coerce "I could not tell" into "it is dead." See
# `decisions/liveness-read-is-platform-specific-and-unreadable-is-not-death.md`.
PROCESS_START_UNREADABLE = object()


def session_records():
    """Return this machine's session records, or None when the session directory exists but
    cannot be listed at all."""
    folder = os.path.join(config_dir(), "sessions")
    if not os.path.isdir(folder):
        return []
    try:
        names = os.listdir(folder)
    except Exception:
        return None
    records = []
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as handle:
                records.append(json.load(handle))
        except Exception:
            continue  # one bad record does not make the whole directory unreadable
    return records


def _process_start_ms_windows(pid: int):
    """Windows arm of `_process_start_ms`. Only called when `sys.platform` says Windows, so the
    Windows-only `ctypes` import stays out of every Linux gate run.

    `OpenProcess` with `PROCESS_QUERY_LIMITED_INFORMATION` (0x1000) asks for the least a read
    needs. A NULL handle is read through `GetLastError`. Code 87 (`ERROR_INVALID_PARAMETER`)
    means no process at all exists at this pid, the CONFIRMED dead case, matched to
    `_process_start_ms`'s existing `None` contract. Code 5 (`ERROR_ACCESS_DENIED`) means the
    process exists but this read cannot see into it. Any other code is also unreadable: this
    function never guesses a code it has not measured into a definite dead or alive answer.

    A valid handle's `GetProcessTimes` creation FILETIME is UTC-anchored by definition. `ps
    -o lstart=` below prints local time with no zone marker at all. FILETIME carries no such
    trap: no zone is assumed, because none is ever ambiguous.

    MEASURED cost on the reference machine: 0.137 ms per call.
    """
    import ctypes
    import ctypes.wintypes

    kernel32 = ctypes.windll.kernel32
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        error = ctypes.GetLastError()
        if error == 87:  # ERROR_INVALID_PARAMETER: no such process
            return None
        return PROCESS_START_UNREADABLE  # 5 (ERROR_ACCESS_DENIED) or any other code
    try:
        creation = ctypes.wintypes.FILETIME()
        exit_time = ctypes.wintypes.FILETIME()
        kernel_time = ctypes.wintypes.FILETIME()
        user_time = ctypes.wintypes.FILETIME()
        ok = kernel32.GetProcessTimes(
            handle, ctypes.byref(creation), ctypes.byref(exit_time),
            ctypes.byref(kernel_time), ctypes.byref(user_time),
        )
        if not ok:
            return PROCESS_START_UNREADABLE
        value = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        return value // 10000 - 11644473600000
    finally:
        kernel32.CloseHandle(handle)


def _process_start_ms(pid: int):
    """Return a live process's start time in epoch milliseconds. Return `None` when the pid is
    CONFIRMED not running (dead). Return `PROCESS_START_UNREADABLE` when the read could not
    tell either way. A caller must never fold the third state into the second: an unreadable
    read is not proof of death. See
    `decisions/liveness-read-is-platform-specific-and-unreadable-is-not-death.md`.

    POSIX: `ps -o lstart=` prints the start time in THIS machine's own local clock, with no
    timezone marker at all. Read it with `time.mktime`. That call turns a naive `struct_time`
    into an epoch by treating it as LOCAL time on THIS SAME machine. The number it returns then
    lines up with the epoch millisecond a session record already carries, written by
    `Date.now()` on the same local machine.
    MEASURED trap, named in the plan this task comes from. Parsing the identical string as UTC
    introduced a five-hour offset and made a live session look expired. `calendar.timegm` and
    `datetime.fromisoformat(...).timestamp()` after tagging the string UTC both carry that trap.
    `mktime` does not, because it never assumes a zone the string never named.

    Windows has no such trap: see `_process_start_ms_windows`, called below when `sys.platform`
    says Windows.
    """
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return None
    if sys.platform.startswith("win"):
        return _process_start_ms_windows(pid)
    try:
        answer = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return PROCESS_START_UNREADABLE  # exec failed or timed out, not a dead-pid answer
    if answer.returncode != 0:
        # `ps` answers exit code 1 with empty stdout for "no such pid": CONFIRMED dead. Any
        # other nonzero code is a read failure, not a death, and stays unreadable.
        if answer.returncode == 1 and not answer.stdout.strip():
            return None
        return PROCESS_START_UNREADABLE
    text = answer.stdout.strip()
    if not text:
        return None
    try:
        parsed = time.strptime(text, "%a %b %d %H:%M:%S %Y")
        return int(time.mktime(parsed) * 1000)
    except Exception:
        return PROCESS_START_UNREADABLE  # output that does not parse is not a death either


def session_is_live(record):
    """True when the record's process id is alive AND its recorded start time still matches
    that live process's own start time, within a tolerance for the read's own granularity.
    False when the pid is CONFIRMED dead, or the record itself is malformed. None when the
    liveness read could not tell either way (`_process_start_ms` returned
    `PROCESS_START_UNREADABLE`), which a caller must treat as "cannot tell," never as False.

    A recycled pid then cannot inherit a dead session's claim. The process at that pid today
    started at a different moment than the one the record names.

    The tolerance is one-sided. `actual` (read now, fixed forever once the kernel records a
    process's creation FILETIME) more than the tolerance AHEAD of `started` (written 1.7-3.2s
    later by `Date.now()`, MEASURED) is the recycled-pid signature -- but a clock stepping
    BACKWARDS between those two original measurements produces the exact same shape for a
    process that never died: `started` reads too small because it was captured after the step.
    The two are indistinguishable from this reading alone, so that direction answers None
    (cannot tell), never a confident False. The other direction (`started` far AHEAD of
    `actual`) has no such legitimate reading -- `started` is always written strictly after
    `actual` -- so it stays a confident False, unchanged."""
    if not isinstance(record, dict):
        return False
    pid = record.get("pid")
    started = record.get("startedAt")
    if not isinstance(started, (int, float)) or isinstance(started, bool):
        return False
    actual = _process_start_ms(pid)
    if actual is PROCESS_START_UNREADABLE:
        return None
    if actual is None:
        return False
    diff = actual - started
    if diff > SESSION_LIVE_TOLERANCE_MS:
        return None
    return diff >= -SESSION_LIVE_TOLERANCE_MS


def _path_identity(path: str):
    """A key identifying PATH's underlying file, stable across different path spellings of one
    physical location (a Windows `subst` drive or a mapped network drive against its UNC or
    local equivalent). `None` when the identity itself could not be read.

    MEASURED: `os.path.realpath` does not reliably canonicalise such a spelling to the same
    string as its equivalent -- mapping drive `T:` to a UNC share left `realpath` naming
    the UNC path for one spelling and the local path for the other, so they never compared
    equal as strings. `os.stat`'s `(st_dev, st_ino)` agreed for both. That pair, not the path
    string, is the identity this function reports."""
    try:
        info = os.stat(path)
        return (info.st_dev, info.st_ino)
    except Exception:
        return None


def _under_by_identity(cwd_resolved: str, target_identity):
    """True when some ancestor of CWD_RESOLVED (itself included) is the same underlying file as
    TARGET_IDENTITY. False when every ancestor's own identity resolves and none matches. None
    when TARGET_IDENTITY itself is unreadable, or some ancestor's identity could not be read
    without another ancestor already matching -- that leaves the question open, never "no"."""
    if target_identity is None:
        return None
    ancestor = cwd_resolved
    unresolved = False
    while True:
        identity = _path_identity(ancestor)
        if identity is None:
            unresolved = True
        elif identity == target_identity:
            return True
        parent = os.path.dirname(ancestor)
        if parent == ancestor:
            break
        ancestor = parent
    return None if unresolved else False


def worktree_live_session(target: str):
    """True when a live session's cwd sits at or under TARGET. False when every session under
    TARGET is confirmed not live, or none has a cwd under TARGET at all. None when the session
    directory itself could not be read. None also when some session's cwd sits under TARGET,
    but its own liveness read came back unreadable rather than confirmed dead. None also when a
    record's cwd cannot be MATCHED against TARGET at all: neither the string compare nor the
    file-identity fallback (`_under_by_identity`) could tell, so it might be an unmatched
    spelling of a live session's own worktree.

    A record with an unreadable liveness read is never dropped by `continue` as though it were
    confirmed dead. Doing so would fold "could not tell" back into "not live," the exact bug
    this read exists to avoid. See
    `decisions/liveness-read-is-platform-specific-and-unreadable-is-not-death.md`."""
    records = session_records()
    if records is None:
        return None
    try:
        target_resolved = os.path.realpath(target)
    except Exception:
        return None
    target_real = os.path.normcase(target_resolved) + os.sep
    target_identity = _path_identity(target_resolved)
    saw_unreadable = False
    for record in records:
        if not isinstance(record, dict):
            continue
        cwd = record.get("cwd")
        if not isinstance(cwd, str) or not cwd:
            continue
        try:
            cwd_resolved = os.path.realpath(cwd)
        except Exception:
            continue
        cwd_real = os.path.normcase(cwd_resolved) + os.sep
        under = cwd_real.startswith(target_real)
        if not under:
            # The string spellings differ. Before concluding "not under," check whether they
            # are two spellings of the one physical location (see `_path_identity`).
            under = _under_by_identity(cwd_resolved, target_identity)
        if under is None:
            saw_unreadable = True
            continue
        if not under:
            continue
        live = session_is_live(record)
        if live is True:
            return True
        if live is None:
            saw_unreadable = True
    return None if saw_unreadable else False


def worktree_remove_subject(args, where: str):
    """The subject of `git worktree remove <path>` is PATH's own uncommitted and untracked work,
    widened by whether it is locked and whether a live session still stands in it."""
    target = worktree_remove_target(args, where)
    if not target:
        return None
    lines = porcelain(target)
    if lines is None:
        return None
    # An untracked symlink is not work: removing it deletes the link, never its target.
    # A path git quotes (core.quotePath) keeps its quotes here, is no link, and still counts.
    lines = [l for l in lines
             if not (l.startswith("?? ") and os.path.islink(os.path.join(target, l[3:].rstrip("/"))))]
    if lines:
        return False
    locked = worktree_locked(where, target)
    if locked is None:
        return None
    if locked:
        return False
    live = worktree_live_session(target)
    if live is None:
        return None
    if live:
        return False
    return True


# `git worktree prune` deletes no files at all: it drops the ADMINISTRATIVE RECORD of a worktree
# whose directory is already gone. `-n` is the read git itself offers for exactly this question,
# the same shape `git status --porcelain` is for a working tree elsewhere in this file: it is not
# a dry run of a block list (CLAUDE.md: never dry-run a block list), because nothing here compares
# the answer against a list of names. An empty answer means nothing would be pruned, so the call
# passes; any line named means a record would go, and the caller turns that into an ASK, never a
# deny, because the record is not a file and the loss is the record alone.
def worktree_prune_subject(args, where: str):
    """True when `git worktree prune -n` names nothing to prune, False when it names something,
    None when the dry run could not be read.

    MEASURED: git prints each worktree it would remove to STDERR, not stdout (`Removing
    worktrees/<name>: <reason>`), so both streams are read. A non-empty stderr from a `-n` call
    that still exits 0 is this message, never an error: an error exits non-zero, which the
    caller above already turns into `None`.
    """
    answer = _git(where, "worktree", "prune", "-n")
    if answer is None or answer.returncode != 0:
        return None
    return not (answer.stdout.strip() or answer.stderr.strip())


def config_dir() -> str:
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude"
    )


def _expanded(path: str, cwd: str) -> str:
    """`~`, env vars, a Git-Bash drive spelling and a relative path resolved against `cwd`. No
    symlink is followed here, and nothing is realpath'd: see `_resolved` and `_literal_resolved`.
    """
    target = os.path.expandvars(os.path.expanduser(path.strip("'\"")))
    if re.match(r"^/[a-zA-Z]/", target):  # Git Bash `/c/Users/...` to `C:/Users/...`
        target = target[1].upper() + ":" + target[2:]
    if not os.path.isabs(target) and cwd:
        target = os.path.join(cwd, target)
    return target


def _resolved(path: str, cwd: str) -> str:
    return os.path.normcase(os.path.realpath(_expanded(path, cwd)))

# What the printed reason may carry. A reason is read by a person under time pressure, and it is the
# one reason in this file built from tool-supplied text, so the text is bounded and cleaned first.
CAP_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
CAP_CUT_MARK = " [cut]"


def cap_safe(text: str, limit: int) -> str:
    """Return text fit to print inside a reason: cleaned, bounded, and a cut MARKED.

    A control character becomes a space, so a crafted value or path cannot print a line of its own
    that reads like an approval. A text over the limit is cut and the cut is marked, so a shortened
    value is never read as the whole value.
    """
    clean = CAP_CONTROL.sub(" ", text or "")
    if len(clean) > limit:
        return clean[:limit] + CAP_CUT_MARK
    return clean


# ------------------------------------------------------------------ the log
#
# One line for each refusal, and nothing for an allow. An allow is the ordinary case, so logging it
# would bury the refusals. A failure to write the log never changes the decision.
#
# THE MATCHED FIELD IS BOUNDED, so a crafted command or a deep path cannot fill the log file. The
# bound cuts from the TAIL, which is right for a command, because a command says what it is in its
# first words. A CUT IS MARKED, the same contract `cap_safe` holds for the printed reason: a
# shortened field must never read as a whole one. An unmarked cut is what hid the defect below.
LOG_MAX_MATCHED = 120
LOG_CUT_MARK = " [cut]"

# A PATH IS SHORTENED FROM ITS HEAD, never from its tail. The tail of a path names the project, the
# folder and the file, which is what a reader needs. The head names only the machine's temporary or
# home root, which no reader needs.
LOG_PATH_MARK = "..."

# The tail of the path that survives whatever else shares the field. MEASURED: the widest ORDINARY
# reading rule 8 writes is both cap variables with a full model id,
# `CLAUDE_CODE_SUBAGENT_MODEL = claude-sonnet-5, CLAUDE_CODE_SUBAGENT_MODEL_FORCE = 1`, at 82
# characters. LOG_MAX_MATCHED less that reading and the one space between the parts leaves 37, so
# the ordinary reading and a path tail of 37 both fit whole, at any path depth.
LOG_MIN_PATH = LOG_MAX_MATCHED - 1 - 82


def log_cut(text: str, limit: int) -> str:
    """Return one log field, whitespace folded to spaces, no longer than `limit`, cut MARKED.

    The mark is inside the limit, never added past it, so a caller can budget a field by adding up
    the parts and trust the sum.
    """
    text = re.sub(r"\s+", " ", text or "")
    if len(text) <= limit:
        return text
    return (text[:max(limit - len(LOG_CUT_MARK), 0)] + LOG_CUT_MARK)[:limit]


def log_path(path: str, limit: int) -> str:
    """Return a path as a log field of at most `limit` characters, shortened from the HEAD."""
    path = re.sub(r"\s+", " ", path or "")
    if len(path) <= limit:
        return path
    keep = max(limit - len(LOG_PATH_MARK), 0)
    return (LOG_PATH_MARK + path[len(path) - keep:])[:limit]


def log_path_and_text(where: str, text: str) -> str:
    """Compose a log field out of a PATH and a TEXT so that BOTH survive the field's bound.

    THE DEFECT THIS FIXES, MEASURED 2026-09-19 on macOS: rule 8 handed `record` the path and the
    cap reading joined into one string, and `record` cut the join at LOG_MAX_MATCHED from the tail.
    A macOS temporary root is long (`/var/folders/nv/mtfv7k2n11g3m1zvzw6bffym0000gn/T/...`), so the
    path alone ate the field and the line ended `... CLAUDE_CODE_SUBAG`: the variable cut mid-token
    and the MODEL GONE. The model is the part that says how far the cap was lifted, so the log line
    lost the one thing it is written for. Ubuntu passed only because `/tmp` is short, which is the
    platform reading a green check proves and nothing more.

    THE FIX IS A BUDGET, not a bigger bound. A bigger bound moves the cliff to a deeper path. Here
    the text takes the room it needs, the path takes the rest and never less than LOG_MIN_PATH
    characters of its tail, and each part marks its own cut. A path of any depth now leaves the
    ordinary reading whole, and a crafted text of any length still leaves the path readable.
    """
    text = re.sub(r"\s+", " ", text or "")
    room = LOG_MAX_MATCHED - 1  # the one space between the two parts
    for_path = min(len(re.sub(r"\s+", " ", where or "")),
                   max(LOG_MIN_PATH, room - len(text)))
    for_path = max(0, min(for_path, room))
    short = log_path(where, for_path)
    return short + " " + log_cut(text, room - len(short))


SESSION_LOG_PLACEHOLDER = "-"
SESSION_LOG_MAX = 64
# Controls and line separators go before the cut. A lone surrogate cannot be encoded as UTF-8, so
# one in the id would lose the whole log line at the write. It goes after the cut, so the cut
# never leaves one at the end.
_SESSION_LOG_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")
_SESSION_LOG_SURROGATE = re.compile(r"[\ud800-\udfff]")
_log_session = SESSION_LOG_PLACEHOLDER


def session_log_field(value) -> str:
    """Return the guard.log session column: the id without control characters, cut at 64, else "-".

    A guard.log line ends in this field. It reads the hook input's id only, never the environment
    (an environment id can belong to a parent session), so it is not session_id_of. It never raises.
    """
    try:
        if not isinstance(value, str):
            return SESSION_LOG_PLACEHOLDER
        text = _SESSION_LOG_CONTROL.sub("", value).strip()[:SESSION_LOG_MAX]
        text = _SESSION_LOG_SURROGATE.sub("", text).strip()
        return text or SESSION_LOG_PLACEHOLDER
    except Exception:
        return SESSION_LOG_PLACEHOLDER


def set_log_session(value) -> None:
    """Name the session whose hook call this process judges. Each `record` line carries it.

    A hook process judges one call, so the entry point sets it once instead of every rule passing it
    down to every `record` and `refuse` call.
    """
    global _log_session
    _log_session = session_log_field(value)


def record(tool: str, decision: str, rule: str, matched: str) -> None:
    try:
        folder = config_dir()
        os.makedirs(folder, exist_ok=True)
        fields = [
            datetime.now().isoformat(timespec="seconds"),
            tool or "",
            decision,
            rule,
            log_cut(matched, LOG_MAX_MATCHED),
        ]
        session = globals().get("_log_session")  # absent: a five-field line, never a lost one
        if session is not None:
            fields.append(session)
        line = "\t".join(fields)
        with open(os.path.join(folder, "guard.log"), "a", encoding="utf-8") as handle:
            locked = _log_lock(handle)
            try:
                handle.write(line + "\n")
                handle.flush()  # the line leaves while the lock is held
            finally:
                if locked:
                    _log_unlock(handle)
    except Exception:
        pass


LOG_LOCK_WAIT = 2.0  # seconds; then the line is written unlocked, never dropped
LOG_LOCK_OFFSET = 1 << 40  # a byte past any log data, so a reader never meets the lock


def _log_lock(handle) -> bool:
    """Take a short exclusive lock on the open log. False if it cannot: the caller writes anyway.

    Two processes appending to one file can lose lines on Windows, where an append seeks and then
    writes. The lock makes each line land whole. Stdlib only: msvcrt on Windows, fcntl elsewhere.
    """
    try:
        fd = handle.fileno()
        deadline = time.monotonic() + LOG_LOCK_WAIT
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    os.lseek(fd, LOG_LOCK_OFFSET, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except OSError as exc:
                # Only contention is worth a retry: msvcrt gives EACCES or EDEADLK, flock gives
                # BlockingIOError (EAGAIN) or EACCES. Any other error returns at once.
                busy = isinstance(exc, BlockingIOError) or exc.errno in (
                    errno.EACCES, errno.EAGAIN, errno.EDEADLK)
                if not busy or time.monotonic() >= deadline:
                    return False
                time.sleep(0.001)
    except Exception:
        return False


def _log_unlock(handle) -> None:
    try:
        fd = handle.fileno()
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, LOG_LOCK_OFFSET, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_UN)
    except Exception:
        pass


def refuse(tool: str, decision: str, rule: str, reason: str, matched: str) -> None:
    record(tool, decision, rule, matched)
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": rule + ": " + reason,
        }
    }))
    sys.exit(0)


# ------------------------------------------------------------------ builders do not edit tests
#
# EVIDENCE: ImpossibleBench (arXiv 2510.20270): read-only tests block a worker's direct edits of
# the tests that grade it, with little loss of real performance. A builder that cannot pass a test
# may otherwise delete it, skip it, or rewrite it to pass.
#
# THE RULE JUDGES THE RESULT, NOT THE COMMANDS (decisions/predicate-is-the-act.md). A first
# version read shell commands (`rm`, `mv`, `sed -i`, a redirect). A review found a bypass for
# each: `bash -c`, `find -delete`, `xargs rm`, `dd`, `rsync`, `patch`, a variable, a symlink. The
# commands are not the act. The act is a test path in the diff. So the diff is judged, at three
# points: a Write/Edit tool call (the early warning, by path), the builder's own `git commit` and
# `git push`, and its SubagentStop. Each reads the SAME diff: the working tree against the commit
# the agent's branch was created from, plus untracked files, with every path normalised for
# backslashes and resolved through symlinks.
#
# THE ROLE is read from the payload: it carries an `agent_id` (a subagent) and an `agent_type`.
# The main session, a reviewer, an Explore agent, and a session started with `--agent builder` (no
# `agent_id`; unmeasured, so it stays allowed) pass untouched. `test-author` is the inverse: it may
# change ONLY test paths and test config, never product code (agents/test-author.md).
# `record-writer` (owner ruling 2026-10-10) may change ONLY `*.md` files (case-insensitive
# extension; agents/*.md and CLAUDE.md included), never anything else (agents/record-writer.md).
#
# A TEST PATH is read from the path's own parts, never from a substring: a basename shape
# (`test_*.py`, `*_test.py`, `*_test.go`, `*.test.{ts,js,tsx,jsx}`, `*.spec.*`, `conftest.py`) or a
# directory part named tests, test, __tests__ or spec. Parts count from the repository root, so a
# clone that lives under a folder named `tests` is not all test files. TEST CONFIG (pytest.ini,
# pyproject.toml, jest.config.*, ...) is a test path for a builder only when the change ADDS a line
# that disables tests (`--deselect`, `testpaths`, `testPathIgnorePatterns`, ...), so a new
# dependency in pyproject.toml stays allowed. For a test-author, test config is always its own.
# `contest.py` and `latest_results.md` match no shape.
# Xcode/SPM (incident 2026-10-11, Degen): a part `^[A-Z]\w*Tests$` (`DegenUITests`) and a basename `^\w+Tests\.swift$`, case-sensitive.
# The decisions: predicate-is-the-act, guard-that-cries-wolf-is-spent, builders-cannot-edit-tests.
BUILDER_ROLE = "builder"
AUTHOR_ROLE = "test-author"
WRITER_ROLE = "record-writer"


def agent_role(payload) -> str:
    """BUILDER_ROLE, AUTHOR_ROLE or WRITER_ROLE for a subagent of that type, else ''."""
    role = payload.get("agent_type")
    if not payload.get("agent_id") or not isinstance(role, str):
        return ""
    role = role.strip().lower()
    return role if role in (BUILDER_ROLE, AUTHOR_ROLE, WRITER_ROLE) else ""


# ------------------------------------------------------------------ helpers several families share
# A null-device target, on either stream, in the three shells this guard reads a command from:
# POSIX (`/dev/null`), Windows cmd (`NUL`), and PowerShell (`$null`). `2>&1` duplicates one stream
# onto another file descriptor and is not this: the line still reaches a stream the session reads.
SILENT_WRITE_REDIRECT = re.compile(
    r"(?:&>>?|\d?>>?&?)\s*(['\"]?)(?:/dev/null|NUL|\$null)\1(?=$|[\s;&|])"
    r"|\d?>&-(?=$|[\s;&|])",   # a closed descriptor
    re.IGNORECASE,
)


def _norm_dir(path: str):
    """A resolved, case-folded form of `path` for a prefix compare, or None when it cannot be
    read. `os.path.realpath` needs no existing file, so a removed worktree's path still
    normalizes: the home record must still compare correctly once the folder is gone."""
    if not path or not isinstance(path, str):
        return None
    try:
        return os.path.normcase(os.path.realpath(path))
    except Exception:
        return None


def path_is_inside(path: str, root: str):
    """True when `path` sits at or under `root`, False when it plainly does not, None when
    either could not be resolved. Existence of either is never required."""
    p, r = _norm_dir(path), _norm_dir(root)
    if p is None or r is None:
        return None
    if p == r:
        return True
    return (p + os.sep).startswith(r + os.sep)


# A shell that runs its `-c` argument as a script. The script is judged by this same rule.
# MEASURED 2026-09-26 on Windows (PR #144): `sh -c 'cmd &'` was allowed, and the server outlived
# its call. The `&` sat inside one quoted token, where no per-segment read above can see it.
INLINE_SCRIPT_SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "sh.exe", "bash.exe"}
_C_FLAG = re.compile(r"^-[A-Za-z]*c[A-Za-z]*$")


def inline_script(tokens) -> str:
    """Return the script a `sh -c SCRIPT` segment runs, else ''."""
    index = resolve_command(tokens)
    if index is None or basename(tokens[index]) not in INLINE_SCRIPT_SHELLS:
        return ""
    has_c = False
    for tok in tokens[index + 1:]:
        if tok.startswith("-"):
            has_c = has_c or bool(_C_FLAG.match(tok))
            continue
        return tok if has_c else ""
    return ""


# A redirect operator, spaced into a word of its own before the words are read.
REDIRECT = re.compile(r"(\d?>>?)")


# A search command's pattern is a regex, never a path: a lone dot-star pattern reads no
# environment file. MEASURED in guard.log 2026-09-16 to 10-02: 65 false `env-file` denies.
ENV_PATTERN_COMMANDS = ("grep", "egrep", "fgrep", "rg", "ag", "ack")


PLAYWRIGHT_PS_SHELLS = ("pwsh", "powershell", "pwsh.exe", "powershell.exe")


def _pwsh_script(tokens) -> str:
    """The script text after `-c` or `-Command` of a pwsh launch, else ''."""
    for at, tok in enumerate(tokens[:-1]):
        if re.fullmatch(r"-c(?:ommand)?", tok, re.I):
            return " ".join(tokens[at + 1:])
    return ""


CMD_EXE_NAMES = {"cmd", "cmd.exe"}

# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
