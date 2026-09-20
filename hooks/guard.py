#!/usr/bin/env python3
"""The global PreToolUse guard.

Claude Code runs this script before each matched tool call. The script reads one
JSON object on stdin and answers on stdout.

  stdin  : {"tool_name": str, "tool_input": {...}, "cwd": str}
  allow  : print nothing, exit 0
  refuse : print one hookSpecificOutput object with "deny" or "ask", exit 0

Fail open. Unreadable input, a payload that is not an object, or a missing key
all allow the call. A guard bug must never brick a session.

The rules below are the owner's global CLAUDE.md made mechanical. They run in
one fixed order, and the first match wins.

  1 shared-tree        a command that throws away a working tree, judged against the STATE OF
                       ITS SUBJECT: an empty subject passes, an unreadable subject is allowed
                       and logged as `noted`/`subject-unread`
  1b pointer-head      a command that moves HEAD off `main` in the POINTER checkout, the one
                       checkout every session on this machine runs its hooks and its lint from.
                       Always denied. A move TO `main` restores the invariant and passes.
  1c silent-write      a `commit`, `push`, `merge`, `tag`, `rebase`, or `cherry-pick` whose own
                       trace is silenced, by a redirect of either stream to a null device, or,
                       on `push`/`merge`/`rebase` only (MEASURED), by git's own `-q`/`--quiet`
                       flag alone. `commit`, `tag`, and `cherry-pick`'s own flags are measured
                       carve-outs. `merge --abort` is carved out, and every read subcommand is
                       untouched.
  2 machine-wide-kill  a kill by name or by pattern
  3 live-stream        a command that follows a stream and never ends on its own
  3 waiter             a shell segment whose command word is a sleep-and-poll
  4 force-push         a rewrite of a published branch
    destructive-delete a recursive delete at a root, a home or a glob
  5 env-file           any read or write of an environment file
  6 merge-main         a pull request merged into main. Allowed, and logged (Decision 8).
  7 frozen-path        a write to the settings, the hooks or the global CLAUDE.md, under
                       `${CLAUDE_CONFIG_DIR:-$HOME/.claude}`. Always denied.
  8 subagent-model-cap a write to a settings file whose content sets or changes
                       `CLAUDE_CODE_SUBAGENT_MODEL` or `CLAUDE_CODE_SUBAGENT_MODEL_FORCE`.
                       Always asked, never denied.

A project's own `.claude/settings.json`, `.claude/settings.local.json`, and
`.claude/hooks/*` are NOT frozen (Decision 7). They are allowed, and the guard appends
one log line with decision `noted` and rule `config-edit`, so a person can see the edit at
turn end. Nothing is printed for a noted edit; the config-report Stop hook is what surfaces
it to the transcript. `merge-main`, `conflict-resolve`, and `subject-unread` are logged the
same way: an ALLOW that a person still gets to see.

Rule 8 stands after rule 7 on purpose. The owner's user settings hold the subagent model cap,
`CLAUDE_CODE_SUBAGENT_MODEL` with `CLAUDE_CODE_SUBAGENT_MODEL_FORCE`, which stops a session
passing a model of its own when it starts a subagent. A project's own `.claude/settings.json` and
`.claude/settings.local.json` override user settings, so the write Decision 7 allows is also the
write that lifts the cap. The decision is `ask`, never `deny`, because that same write is how an
Opus worker gets enabled on purpose. The order does the rest: a write under
`${CLAUDE_CONFIG_DIR:-$HOME/.claude}` is already denied by rule 7 and never reaches rule 8, so
only the project-scoped case is asked.

That one ask NAMES the requested value and the file. It is not an exception to the remedy rule
below. A remedy hides the target because repeating it reads as permission to run it, while this
ask exists to tell the approver WHAT is being turned on and WHERE. An ask that hid both would ask
nothing. It is also the one reason in this file built from text a tool passed in, so the value and
the path are cleaned of control characters, cut at a bound, and marked where they were cut: a
reason that a caller can lengthen or forge lines inside is a reason an approver cannot trust.

A subject the guard could not read is the fourth such line. The call is allowed, because a
refusal whose ground could not be read is a guess, and the line names what could not be
read so a reader can tell "I could not confirm this" from "this destroys something". The
config-report Stop hook prints those lines for the turn that wrote them.

Decision 8 ("Merge into main: allow and report") makes `merge-main` the same shape: a
merge into main is allowed, never asked, and the guard logs `noted`/`merge-main` when
the base is `main` or unreadable, and always for the MCP merge tool, which carries no
base at all. CLAUDE.md's "merged only when I name the act" stays the model's rule; the
guard cannot read chat, so a prompt here would only repeat a decision the owner already
made in the conversation.

`conflict-resolve` is a third case in that same shape, inside rule 1. A `git checkout`
that carries `--ours`, `--theirs`, or `--merge` while a merge, rebase, cherry-pick or
revert is unresolved in the tree picks a conflict side; it does not discard work, and
git itself already holds the tree open. That one call is allowed and logged as
`noted`/`conflict-resolve`. Any other `git checkout` that names a path keeps rule 1's
ordinary deny or ask.

Rule 1c, `silent-write`, mechanizes CLAUDE.md's "Never discard a command's output" for
git. pkmnscan's `scripts/silent-write-guard.py` carries the measurement this rule ports:
a coordinator reported work as landed twice in one session when it had not, once because
a pre-commit refusal went to `/dev/null`, and once because the `git log` that followed
showed the PREVIOUS commit, indistinguishable at a glance from the one that should have
landed. A discarding redirect reproduces that on any of the six subcommands below: the
shell throws the stream away before git gets a say, so a refusal and a proof of landing
are both gone, together.

git's OWN quiet flag is judged separately, because it is git's choice of what to print,
not the shell's, and the choice is not the same for every subcommand. MEASURED
2026-09-19 and 2026-09-20, in throwaway repos, never a shared checkout, all six: `commit`
carves out, because a hook's refusal and a no-op's message both keep their own stream and
a nonzero exit, so a silent exit-0 commit is already unambiguous. `push`, `merge`, and
`rebase` do not carve out: each one's success and its own no-op are BOTH silent at exit 0,
so the flag erases the one line that told a real write from one that moved nothing. `tag`
carves out for a sharper reason: it has no `-q` or `--quiet` at all, so the flag is always
a loud, immediate option-parsing failure, never a silent write. `cherry-pick` carves out
too: its short form is invalid the same way `tag`'s is, and its long form still prints a
full commit summary, a full conflict, or a full "nothing to commit" in every state, so
nothing is silenced either way. A discarding redirect still denies any of the six.

The carve-outs are pinned by fixtures, not left to judgement. `git fetch -q`, every read
subcommand, and the test-by-exit-code shape `git rev-parse -q --verify <ref> >/dev/null
2>&1` that rule 1b already relies on, all stay allowed, because none of them is in
`SILENT_WRITE_SUBCOMMANDS`. `git merge --abort` is carved out inside the rule itself: an
abort lands nothing, so it has no landing to prove. No environment hatch. The permission
prompt is the grant here, the same as everywhere else in this file.

Every refusal names its rule and says what to do instead. A remedy never names
the refused command or the refused path, because a remedy that repeats the
target reads as permission to run it (CLAUDE.md, Git paragraph). The matched
text goes to the log instead, so a person can still see what fired.

This file is ported from two working guards, and the comments that record a
MEASURED defect are kept, because the measurement is the argument.

  job-cost-reporting  .claude/hooks/pretooluse_guard.py   shared trees
  q_max               .claude/hooks/pretooluse_guard.py   the environment wall

No override tokens. The earlier guards carried DESTRUCTIVE_OK, GIT_DISCARD_OK
and OWNER_MERGE. The decision of this port is that a permission prompt is the
grant, so the tokens are gone. An "ask" decision puts the answer in the owner's
hands, which is what the tokens were reaching for.
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
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
MERGE_TOOLS = ("mcp__github__merge_pull_request",)


def norm(path: str) -> str:
    return path.replace("\\", "/")


def basename(token: str) -> str:
    return token.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()


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
def split_segments(cmd: str):
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
    """
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
        if char in ("'", '"'):
            quote = char
            current.append(char)
            index += 1
            continue
        if char == "&" and cmd[index:index + 2] == "&&":
            segments.append("".join(current))
            current = []
            index += 2
            continue
        if char == "|":
            index += 2 if cmd[index:index + 2] == "||" else 1
            segments.append("".join(current))
            current = []
            continue
        if char in (";", "\n"):
            segments.append("".join(current))
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    segments.append("".join(current))
    return segments


# A leading `VAR=value` assignment, which is not a segment's command. Shared with the
# environment layer below, so the two never drift into judging an assignment two different ways.
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

# A wrapper that runs another program in its place, so the CALLED program is a segment's real
# command word, not the wrapper. `xargs pkill foo` runs pkill, so `xargs` unwraps the same as
# the rest: the token after it, once its own flags are skipped, is what actually runs.
COMMAND_WRAPPERS = {"sudo", "env", "command", "nohup", "nice", "time", "doas", "xargs"}

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
    try:
        return shlex.split(segment, posix=True)
    except ValueError:
        return None


def resolve_command(tokens):
    """Return the index of the command word in a tokenized segment, or None when it names none.

    Skips leading `VAR=value` assignments and leading loop keywords (`do`, `then`, `else`,
    `elif`, `while`, `until`, `if`, `{`, `(`), then unwraps command wrappers (`sudo`, `env`,
    `command`, `nohup`, `nice`, `time`, `doas`, `xargs`) along with each wrapper's own flags and
    any assignment it takes ahead of the program name, so the index returned is the program that
    actually runs, never the keyword or the wrapper carrying it there.
    """
    index = 0
    end = len(tokens)
    while index < end and (ASSIGNMENT.match(tokens[index]) or tokens[index] in LOOP_KEYWORDS):
        index += 1
    while index < end and basename(tokens[index]) in COMMAND_WRAPPERS:
        index += 1
        while index < end and tokens[index].startswith("-"):
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


def strip_heredoc_bodies(cmd: str) -> str:
    """Drop the body of every heredoc, and keep every header line."""
    if INTERPRETER_HEREDOC.search(cmd):
        return cmd  # the body may be executed, so keep it under inspection
    lines = cmd.split("\n")
    kept = []
    index = 0
    while index < len(lines):
        line = lines[index]
        kept.append(line)
        match = HEREDOC_HEADER.search(line)
        index += 1
        if not match:
            continue
        delimiter = match.group(2)
        while index < len(lines) and lines[index].strip() != delimiter:
            index += 1
        if index < len(lines):
            index += 1  # drop the closing delimiter line too
    return "\n".join(kept)


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


def git_calls(segment: str):
    """Return (subcommand, arguments) for every `git` call in one segment."""
    tokens = REDIRECTION.sub(" ", segment).split()
    calls = []
    index = 0
    while index < len(tokens):
        if basename(tokens[index]) in ("git", "git.exe"):
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
            if cursor < len(tokens):
                calls.append((tokens[cursor].lower(), tokens[cursor + 1:]))
            index = cursor + 1
            continue
        index += 1
    return calls


def checkout_names_a_path(args) -> str:
    """Return the matched text when a `git checkout` names a path, else ''."""
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


def push_is_forced(args) -> bool:
    """True when a `git push` rewrites the remote branch."""
    for arg in args:
        if arg == "--force" or arg.startswith("--force-with-lease"):
            return True
        if arg.startswith("-") and not arg.startswith("--") and "f" in arg:
            return True
    return False


# ------------------------------------------------------------------ the silent write
#
# Rule 1c. CLAUDE.md (Git): "Never discard a command's output." A discarding REDIRECT is denied on
# every one of these six subcommands, whatever the subcommand does with its own output: the shell
# throws the stream away before git ever gets a say, so a hook's refusal and git's own proof of
# landing are both gone, together, always.
SILENT_WRITE_SUBCOMMANDS = ("commit", "push", "merge", "tag", "rebase", "cherry-pick")

# git's OWN `-q`/`--quiet` flag is a narrower claim, and it does not read the same for every
# subcommand. MEASURED 2026-09-19 and 2026-09-20, in throwaway repos under this session's
# scratchpad, never in a shared checkout, `-q`/`--quiet` alone, no redirect, three states each: a
# write that succeeds, one a hook refuses (a `pre-commit`/`pre-receive` hook, or the conflict
# `merge`, `rebase`, and `cherry-pick` raise on their own), and a no-op (nothing staged or to
# push, an already-merged branch, nothing left to replay, a change already present).
#
#   git commit -q       success        exit 0, stdout '',                stderr ''
#                        hook refusal   exit 1, stdout '',                stderr the hook's own line
#                        no-op          exit 1, stdout "nothing to        stderr ''
#                                                commit ...",
#
#   git push --quiet    success        exit 0, stdout '',                stderr ''
#                        hook refusal   exit 1, stdout '',                stderr the full rejection
#                        no-op          exit 0, stdout '',                stderr ''
#
#   git merge -q         success        exit 0, stdout '',                stderr ''
#                        conflict       exit 1, stdout the full           stderr ''
#                                                CONFLICT message,
#                        no-op          exit 0, stdout '',                stderr ''
#
#   git rebase -q       success        exit 0, stdout '',                stderr ''
#                        conflict       exit 1, stdout the CONFLICT       stderr the apply error
#                                                message,                 and its hints,
#                        no-op          exit 0, stdout '',                stderr ''
#
#   git tag -q          every state    exit 129, stdout '',              stderr "error: unknown
#                                                                                switch `q'" plus
#                                                                                the full usage
#
#   git cherry-pick -q  every state    exit 129, stdout '',              stderr the full usage
#                                                                                ("-q" is not a
#                                                                                cherry-pick option)
#   git cherry-pick
#     --quiet            success        exit 0, stdout the full commit    stderr ''
#                                                summary line,
#                        conflict       exit 1, stdout the CONFLICT       stderr the apply error
#                                                message,                 and its hints,
#                        no-op          exit 1, stdout "nothing to        stderr "previous
#                                                commit ...",              cherry-pick is now
#                                                                          empty" and its hint
#
# `commit -q` hides nothing a session could not already read: a refusal keeps its own message on
# stderr, a no-op keeps its own message on stdout, and both keep a nonzero exit code, so silence
# at exit 0 is unambiguous proof of a landed commit. `commit` drops out of the quiet-flag arm.
#
# `push -q` and `merge -q` and `rebase -q` measure the same way as each other, and differently
# from `commit`. Each one's own refusal (a hook, or a real conflict) stays fully readable. But
# each one's success and its own no-op are BOTH silent and BOTH exit 0 (without `-q` they already
# differ: `push` prints "Everything up-to-date" against the `sha..sha  branch -> branch` summary,
# `merge` and `rebase` print their own "up to date"/"nothing to replay" line against a diffstat or
# a "Successfully rebased" line). `-q` erases the one line that told a real write from a no-op, so
# a session cannot read whether the write it just ran moved anything. All three keep the
# quiet-flag arm on this measurement, not on the flag's name.
#
# `tag` has NO `-q` and NO `--quiet` at all (git 2.39.3): both spellings exit 129 with "error:
# unknown switch" before git reads the tag name, the message, or the repository state. Every
# state measures identically, because the flag never gets past option parsing. `tag` therefore
# cannot use `-q`/`--quiet` to hide a success from a no-op or a refusal: the attempt is always a
# loud, immediate failure. `tag` drops out of the quiet-flag arm.
#
# `cherry-pick`'s short form, `-q`, is ALSO not a valid option (exit 129, the same shape as
# `tag`). Its long form, `--quiet`, IS valid, and measures as the least silent of the six: a
# success still prints the full one-line commit summary to stdout, a conflict prints its own
# CONFLICT message and hints in full, and a no-op (an already-applied change) prints "nothing to
# commit" and "previous cherry-pick is now empty" in full, at its own distinct nonzero exit. No
# state is silent, so nothing is lost by allowing either spelling. `cherry-pick` drops out of the
# quiet-flag arm.
QUIET_FLAG_SUBCOMMANDS = ("push", "merge", "rebase")

# A null-device target, on either stream, in the three shells this guard reads a command from:
# POSIX (`/dev/null`), Windows cmd (`NUL`), and PowerShell (`$null`). `2>&1` duplicates one stream
# onto another file descriptor and is not this: the line still reaches a stream the session reads.
SILENT_WRITE_REDIRECT = re.compile(
    r"(?:&>>?|\d?>>?)\s*(['\"]?)(?:/dev/null|NUL|\$null)\1(?=$|[\s;&|])",
    re.IGNORECASE,
)


def discards_output(segment: str) -> bool:
    """True when the segment redirects stdout or stderr, on any descriptor, to a null device."""
    return bool(SILENT_WRITE_REDIRECT.search(segment))


def quiet_write(args) -> bool:
    """True when a git call carries `-q` or `--quiet`."""
    return "-q" in args or "--quiet" in args


def silent_write_hit(segment: str):
    """Return (matched text, mechanism) for a write whose own trace is silenced, else ("", "").

    `mechanism` is `"redirect"` or `"quiet"`, so the caller can print the reason that matches
    what actually fired: a redirect can hide a refusal AND a proof of landing on any of the six
    subcommands, while the quiet flag is judged per subcommand against `QUIET_FLAG_SUBCOMMANDS`,
    the measured set. Only `SILENT_WRITE_SUBCOMMANDS` are judged at all. `fetch`, `rev-parse`, and
    every other read subcommand fall outside it, which is what keeps `git fetch -q` and the
    test-by-exit-code shape `git rev-parse -q --verify <ref> >/dev/null 2>&1` allowed. `merge
    --abort` is carved out inside the loop: it lands nothing, so it has no landing to prove.
    """
    for subcommand, args in git_calls(segment):
        if subcommand not in SILENT_WRITE_SUBCOMMANDS:
            continue
        if subcommand == "merge" and "--abort" in args:
            continue
        matched = ("git " + subcommand + " " + " ".join(args)).strip()
        if discards_output(segment):
            return matched, "redirect"
        if subcommand in QUIET_FLAG_SUBCOMMANDS and quiet_write(args):
            return matched, "quiet"
    return "", ""


SILENT_WRITE_REDIRECT_REASON = (
    "Rule (Git): a redirect silences this write's own output, so neither a refusal nor "
    "the line that proves it landed would reach the session. "
    "Remedy: run the same write without silencing either stream, and read what it "
    "prints before you say it landed."
)
SILENT_WRITE_QUIET_REASON = (
    "Rule (Git): this write's own quiet flag drops the one line that told a real update "
    "apart from one that moved nothing, so the session cannot read which one just ran. "
    "Remedy: run the same write without the quiet flag, and read what it prints before "
    "you say it landed."
)


STASH_READ_ACTIONS = {"list", "show"}
# `push`, `save` and a bare `git stash` PUT work onto the stack. They take it from the working
# tree, so the working tree is their subject. Every other action that is not a read TAKES an
# entry off the stack, so the stack is theirs.
STASH_TREE_ACTIONS = {"push", "save"}


def stash_action(args) -> str:
    """Return the stash call's own action word, or 'push' when the call names none.

    A bare `git stash` and `git stash -u` both push, the same as `git stash push`. `stash`
    takes no flag of its own before the action word, so the first plain word is the action.
    """
    for arg in args:
        if not arg.startswith("-"):
            return arg
    return "push"


def stash_takes_the_stack(args) -> bool:
    """True when a `git stash` call takes an entry OFF the shared stack.

    The predicate is the DIRECTION of the act, not a list of action words. A call reads the
    stack, puts work onto it, or takes an entry off it. `list` and `show` read. `push`, `save`
    and a bare `git stash` put work on. Every other action takes an entry off: `pop` and
    `branch` consume the entry they use, `drop` and `clear` destroy entries outright, and
    `apply` reads another session's work into this tree without that session's word.

    An action word this guard does not know falls on the stack side. That is the side where a
    wrong answer costs another session its work.
    """
    action = stash_action(args)
    return action not in STASH_READ_ACTIONS and action not in STASH_TREE_ACTIONS


def stash_discards(args) -> bool:
    """True when a `git stash` call can lose work.

    `list` and `show` read the stash and change nothing, so they pass. Every other action can
    lose work, and the SUBJECT READ below decides whether this call would lose any.

    OWNER'S RULING, 2026-09-19, which repeals the earlier exemption for `apply` and `pop`. The
    old argument was MEASURED and correct on its own facts: git refuses to overwrite a modified
    file rather than clobber it (2026-09-17, `git stash apply` aborted with "Please commit your
    changes or stash them before you merge" and left the file untouched). It was wrong about the
    SUBJECT. The thing at risk in an `apply` or a `pop` is not this tree. It is the shared stack.
    The entry consumed may belong to another session, and a tree with nothing in it is exactly
    when that theft leaves no trace.
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


def shared_tree_match(segment: str):
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
            named = checkout_names_a_path(args)
            if named:
                return "git checkout " + named, subcommand, args
    return None


def shared_tree_hit(segment: str) -> str:
    """Return the matched text when one segment discards a working tree, else ''."""
    match = shared_tree_match(segment)
    return match[0] if match else ""


# ------------------------------------------------------------------ which tree the command runs in
#
# THE COMMAND IS JUDGED WHERE IT RUNS, NOT WHERE THE HOOK LIVES. A lane is built in a worktree and a
# discard there loses only that lane's own work, so a worktree earns an "ask". The shared checkout is
# the owner's editor and every other session, so a discard there earns a "deny".
#
# The directory is the last `cd <path>` in the command, or a `git -C <path>`, or the shell's own cwd.
# MEASURED in job-cost-reporting on 2026-09-10: a gate that read the main checkout for every command
# judged a worktree command against another branch.
CD_RE = re.compile(r"(?:^|[;&|]\s*)cd\s+(['\"]?)([^'\";&|]+)\1")
GIT_C_RE = re.compile(r"\bgit\s+-C\s+(['\"]?)([^'\";&|\s]+)\1")
# `--work-tree` NAMES THE TREE THE FILES COME FROM, and it outranks `-C` and a `cd`, because git
# applies it after both. MEASURED 2026-09-19 with real git: from a CLEAN checkout A,
# `git --work-tree=B status --porcelain` reported B's modified file and B's untracked file. The
# files a call discards are B's, so B is the tree this rule must judge. Both the `=` and the
# spaced form are read, because git takes either.
GIT_WORK_TREE_RE = re.compile(r"--work-tree(?:=|\s+)(['\"]?)([^'\";&|\s]+)\1")


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


def _run_dir(cmd: str, shell_cwd: str) -> str:
    """Return the directory the command RUNS in: a `git -C`, else the last `cd`, else the cwd.

    This is the part both roots share. Neither `--work-tree` nor `--git-dir` is read here,
    because each answers a different question and each belongs to one caller.
    """
    where = None
    match = GIT_C_RE.search(cmd)
    if match:
        where = match.group(2)
    else:
        changes = list(CD_RE.finditer(cmd))
        if changes:
            where = changes[-1].group(2).strip()
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
            ["git", "-C", where, *args], capture_output=True, text=True, timeout=10
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
# (Owner's ruling, 2026-09-17. MEASURED on 1be660c in a pristine repository with an empty
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
PATHSPEC_FROM_FILE = "--pathspec-from-file"


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


def named_pathspecs(subcommand: str, args):
    """Return (pathspecs, complete) for a call that names paths.

    `complete` is False when the call's paths cannot be enumerated from its own arguments, and
    the caller then reads the whole tree rather than a subset it is not sure of.
    """
    if any(arg == PATHSPEC_FROM_FILE or arg.startswith(PATHSPEC_FROM_FILE + "=")
           for arg in args):
        return [], False
    if "--" in args:
        return args[args.index("--") + 1:], True
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
        return plain[1:], True  # a start point, then the paths
    return plain, True


def _tree_subject(where: str, pathspecs=(), complete: bool = True):
    """True when the working tree holds nothing under `pathspecs`, False when it holds
    something, None when it cannot be read.
    """
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
        if parts[index] == session_id and parts[index + 1] == "scratchpad":
            return True
    return False


TREE_DENY_REASON = (
    "Rule (shared trees): this command throws away work in a checkout that other "
    "sessions and the owner share, and no step puts it back. "
    "Remedy: copy the file to a name ending in .bak and change the copy. "
    "Commit work you must set aside on your own branch, never a stash: a stash entry "
    "belongs to no branch, and it outlives no session that holds its tag. "
    "Run the command in a worktree of your own when the tree must change."
)
TREE_ASK_REASON = (
    "Rule (shared trees): this command throws away work in a working tree. "
    "This checkout is a worktree, so the loss is limited to this lane. "
    "Commit work you must set aside on your own branch, never a stash. "
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
# commit that sets work aside on a branch of the caller's own. A worker sent here by the harness
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
# The owner's argument: `git checkout --theirs docs/DEBTS.md` during an unresolved merge does
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
        answer = _git(where, "rev-parse", "--verify", "-q", ref)
        if answer is None:
            return None
        if answer.returncode == 0:
            return True
        if answer.returncode != 1:
            return None  # not "ref not found": the tree itself could not be read
    gitdir = _git(where, "rev-parse", "--git-dir")
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


# ------------------------------------------------------------------ the pointer checkout's HEAD
#
# `<config>/lint/*`, `<config>/hooks/*` and `<config>/agents/*` are PER-FILE SYMLINKS into one
# checkout: the one the owner's global rules file names on its `@<path>` line. That checkout's HEAD
# decides WHICH COPY of the rules and of the gates every session on this machine runs. The owner
# has stated the rule: that checkout's HEAD is always `main`.
#
# OBSERVED 2026-09-19. The primary checkout sat on `feat/config-watch-post` while a session edited
# the guard on that branch. The live PreToolUse guard for every session on the machine, including
# the sessions reviewing that very change, was the unreviewed branch's copy. Nothing refused it and
# nothing reported it. `hooks/session_start.sh` now REPORTS the state at session start, which is
# detection after the fact. This rule is the refusal that stops it happening.
#
# THE POINTER LINE IS PARSED HERE RATHER THAN IMPORTED. The three other readers of that line are
# all shell: `install.sh`'s `pointer_dir`, the settings refresh hook, and `hooks/session_start.sh`.
# No import crosses from shell into Python, so a copy is forced, not chosen. This is the one Python
# copy, and it keeps the same three steps those three take: read the global rules file under
# `${CLAUDE_CONFIG_DIR:-$HOME/.claude}`, take the first `@<path>` line, and expand a leading `~/`
# against the home directory. It reads the file with `utf-8-sig`, because the Windows installer
# writes that file and a byte order mark there would hide the first line from a `^@` match.
#
# THE PREDICATE IS THE ACT, NOT THE SPELLING (decisions/predicate-is-the-act.md, judge the act).
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
    "Remedy: build the change in a worktree of your own, on a branch that does not exist yet, "
    "with `git worktree add -b <new-branch> <path>`. Git refuses a worktree for a branch this "
    "checkout already holds, so a NEW branch name is the shape that works the first time."
)


def pointer_checkout() -> str:
    """Return the normalized, resolved directory the global rules file points at, or ''.

    Returns '' on every unreadable step, so an unknown pointer makes the rule silent.
    """
    try:
        with open(os.path.join(config_dir(), "CLAUDE.md"), encoding="utf-8-sig") as handle:
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


# `--git-dir` NAMES WHERE HEAD LIVES. MEASURED 2026-09-19 with real git: from an unrelated
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
        answer = _git(where, "rev-parse", "--absolute-git-dir")
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


# ------------------------------------------------------------------ a machine-wide kill
#
# CLAUDE.md: "Never kill a process you did not start. Treat `pkill -f` and `lsof -t` as
# machine-wide." A kill BY NAME or BY PATTERN reaches every matching process on the machine,
# including another agent's dev server, another person's worker, and the editor itself.
#
# A KILL BY PID IS NOT ON THIS LIST, deliberately. A PID names one process. `taskkill /PID` and
# `Stop-Process -Id` are the same act under the other shell, and neither is refused.
#
# THE PREDICATE IS THE ACT, NOT THE TOOL OR THE SPELLING. The earlier version was four bare
# regexes over the whole command text, so the NAME tripped it wherever it sat: inside a quoted
# grep pattern, on the far side of a pipe, in a comment. MEASURED: the owner's
# `grep -n -i "...|make reap|pkill..." CLAUDE.md` was denied, though the command calls grep, not
# pkill. `cat notes.md | grep pkill` and `echo "pkill -f node"` are the same defect: the word is
# there, but nothing in the segment calls it.
#
# Every check below reads `resolve_command`'s answer for the segment's own tokens: the tool must
# sit in COMMAND POSITION, wrappers unwrapped, before its flags are read at all.
KILL_COMMAND_WORDS = {"pkill", "killall"}
TASKKILL_IMAGE_FLAGS = {"/im", "-im"}
STOP_PROCESS_NAME_FLAGS = {"-n", "-name"}


def kill_hit(tokens) -> str:
    """Return the matched text when a tokenized segment's command word is a machine-wide kill.

    `pkill` and `killall` deny outright: naming a process by pattern or by name always reaches
    every match, flags or none. `taskkill` and `Stop-Process` deny only with the flag that names
    a process by image or by name; `taskkill /PID` and `Stop-Process -Id` name one process and
    pass. `lsof` denies only with a `-t`/`-ti` flag, which feeds a kill list; `lsof -i :3000`
    asks which port is busy and kills nothing.
    """
    index = resolve_command(tokens)
    if index is None:
        return ""
    word = tokens[index]
    tool = basename(word)
    rest = tokens[index + 1:]
    if tool in KILL_COMMAND_WORDS:
        return word
    if tool == "taskkill" and any(flag.lower() in TASKKILL_IMAGE_FLAGS for flag in rest):
        return word
    if tool == "stop-process" and any(flag.lower() in STOP_PROCESS_NAME_FLAGS for flag in rest):
        return word
    if tool == "lsof":
        for arg in rest:
            if arg.startswith("-") and not arg.startswith("--") and "t" in arg:
                return word + " " + arg
    return ""


KILL_REASON = (
    "Rule (shared trees): this stops every process matching a name or a pattern, "
    "machine-wide. This machine runs other agents' servers and the owner's own editor. "
    "Remedy: name one process id that this session started, and stop that one process. "
    "Leave any other process alone."
)


# ------------------------------------------------------------------ a stream that never ends
#
# CLAUDE.md: "Never pipe a live stream through `tail`." A follow flag turns `tail` or
# `Get-Content` into a command that never exits on its own, so it outlives the turn and the
# agent that started it. The COMMAND WORD is checked first, so an unrelated `-f` on another
# program never matches.
#
# The short-flag test reads the WHOLE TOKEN for an `f` or an `F`, the same shape as
# `clean_deletes_files` and `push_is_forced` above, so `-fn 20` and `-nf` both match a combined
# flag. `-F` is `tail`'s own retry-on-rotate form of follow, so it counts too.
LIVE_STREAM_TAIL_TOOL = "tail"
LIVE_STREAM_GETCONTENT_TOOLS = ("get-content", "gc")


def live_stream_hit(segment: str) -> str:
    """Return the matched text when one segment follows a stream and never ends, else ''."""
    tokens = segment.split()
    for index, token in enumerate(tokens):
        tool = basename(token)
        if tool == LIVE_STREAM_TAIL_TOOL:
            for arg in tokens[index + 1:]:
                if arg == "--follow" or arg.startswith("--follow="):
                    return token + " " + arg
                if arg.startswith("-") and not arg.startswith("--") and (
                        "f" in arg or "F" in arg):
                    return token + " " + arg
        elif tool in LIVE_STREAM_GETCONTENT_TOOLS:
            for arg in tokens[index + 1:]:
                if arg.lower() == "-wait":
                    return token + " " + arg
    return ""


LIVE_STREAM_REASON = (
    "this command follows a stream and never ends on its own, so it outlives the turn "
    "and the agent that started it. "
    "Remedy: run the command in the foreground with a timeout, or in the background and "
    "wait for its completion notice."
)


# ------------------------------------------------------------------ a waiter loop
#
# Rule 9, approved by the owner: a shell segment whose command word is a sleep-and-poll turns
# waiting into a loop of turns that each print a word. Placed beside the live-stream rule, because
# both are about a command that should not be how a session waits.
#
# THE COMMAND WORD is read through `resolve_command`, wrappers and leading loop keywords skipped,
# not the segment's raw first token: `split_segments` cuts a loop's `while COND; do sleep 1;
# done` into `do sleep 1` as its own segment, and the command inside that block is `sleep`, not
# `do`. A segment `shlex` cannot parse fails open, this file's standing rule. The Windows
# `timeout /t` form is the one case where the wait is the SECOND word after the command, so it is
# read apart: `timeout /t 5` waits, `timeout /help` (no `/t`) does not.
WAITER_COMMANDS = ("sleep", "start-sleep")


def waiter_hit(segment: str) -> str:
    """Return the matched text when one segment's command word is a sleep-and-poll, else ''."""
    tokens = segment_tokens(segment)
    if not tokens:
        return ""
    index = resolve_command(tokens)
    if index is None:
        return ""
    word = basename(tokens[index])
    if word in WAITER_COMMANDS:
        return tokens[index]
    if word == "timeout" and any(t.lower() == "/t" for t in tokens[index + 1:]):
        return tokens[index] + " /t"
    return ""


WAITER_REASON = (
    "a pause between polls turns waiting into a loop of turns that each print a word. "
    "Remedy: run the long command in the background and wait for its completion notice, "
    "or use a tool that waits once, such as gh run watch <id> --exit-status. Avoid "
    "gh pr checks --watch, which serves a cached status. For a server warm-up, use a "
    "readiness check such as curl --retry."
)


# ------------------------------------------------------------------ a waiter loop over a pattern
#
# Ported from pkmnscan's `scripts/guard-shell.py:800-990` (predicate and wording only, not the
# file, and no override token: this repo ships none). MEASURED there, twice on 2026-09-12: a
# session wrote `until ! pgrep -f 'scratchpad/drive.sh'` to wait out its own driver script, and
# the condition never went false, because `pgrep -f` matches every process whose command line
# names the pattern, including that very invocation of itself. A second copy of the driver then
# raced the live one.
#
# THE CONDITION IS READ WHOLE, not only in command position: a negation (`while ! pgrep ...`) or
# a subshell can sit ahead of the poller, the same reason `live_stream_hit` below reads every
# token of its segment rather than only the first.
PATTERN_POLLERS = {"pgrep", "pkill", "lsof"}


def loop_condition_polls_a_pattern(segment: str) -> str:
    """Return the matched tool when a `while`/`until` segment's condition polls a pattern."""
    tokens = segment.split()
    if not tokens or tokens[0] not in ("while", "until"):
        return ""
    for token in tokens[1:]:
        if basename(token) in PATTERN_POLLERS:
            return token
    return ""


PATTERN_POLLER_REASON = (
    "the loop's own condition polls for a process by name or by pattern. That pattern can match "
    "every process whose command line names it, including this session's own wrapper for the "
    "same wait, so the condition can stay true long after the work is done. "
    "Remedy: wait on one pid this session started, such as `kill -0 $PID`, or use a tool that "
    "waits once, such as gh run watch <id> --exit-status."
)


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
WIDE_TARGET = r"(?:/|~|\.|\*|\$HOME|[A-Za-z]:/?)"
DESTRUCTIVE_DELETE = (
    re.compile(
        r"\brm\s+(?:-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r)\s+['\"]?"
        + WIDE_TARGET + r"['\"]?(?:\s|$)"
    ),
    re.compile(
        r"(?i)\b(?:remove-item|ri|rd|rmdir)\b"
        r"(?=[^\n;|&]*\s-r(?:ec(?:urse)?)?\b)"
        r"(?=[^\n;|&]*\s-f(?:o(?:rce)?)?\b)"
        r"[^\n;|&]*\s['\"]?" + WIDE_TARGET + r"['\"]?(?:\s|$)"
    ),
)

DELETE_REASON = (
    "Rule (shared trees): this deletes a whole root, a home directory or everything a "
    "glob matches. The loss reaches files that no session here can see. "
    "Remedy: name the one directory you mean, under the project or under the scratchpad."
)

PUSH_REASON = (
    "Rule (Git): this rewrites a branch that other people have already pulled. "
    "Their next pull then conflicts with history they already hold. "
    "Remedy: push a new commit on top when the branch is shared. "
    "The click in this prompt is the grant when the rewrite is the intent."
)


# ------------------------------------------------------------------ the environment file
#
# CLAUDE.md: the user manages the environment file, so its CONTENTS stay out of the session.
# Handing the file to a runner that loads it into its own environment prints nothing and puts
# nothing in the transcript, so this layer allows it by name.
#
# The check is a PATH TOKEN test and never a substring test. MEASURED in q_max on 2026-09-08: a
# substring test over the backslash-normalized command refused both of these:
#
#   grep -n "dotenv|VERIFY_DATABASE_URL|process\.env" harness/browser/verify.mjs
#   ls -la .env
#
# The first is normalization doing it. `process\.env` became `process/.env`, so the ENVIRONMENT
# ACCESSOR that every source file uses read as a path. That command does NOT match before
# normalization, which is why this layer reads the command with its own separators intact. The
# second is a listing, and a listing reads no contents at all.
#
# The shape is a path token and then a NAMED allowance. The default is refusal, so a printer, a
# writer and a commit each need no enumeration: `cat`, `>`, `tee` and `git add` are simply not on
# the allow list, and neither is the next one nobody thought of.

ENV_ALLOWED = ".env.example"

# The whole basename: `.env`, or a variant such as `.env.local`. The example file is checked in and
# is documentation, so it is exempt. A variant is held, because it holds the same secrets.
ENV_BASENAME = re.compile(r"^\.env(\.[A-Za-z0-9_.\-]+)?$")

# A word prefix that is a PATH, for deciding whether a backslash before `.env` is a separator or a
# regex escape. `.\.env` and `C:\Users\me\.env` are paths. The `process\.env` in a grep pattern is
# not. A separator is followed by a path segment, while `\.` and `\\` are regex escapes.
#
# MEASURED in q_max on 2026-09-09: reading ANY backslash as a separator refused
# `grep "import\.meta\.env"`, because the head `import\.meta` holds a backslash. One identifier
# deeper than the first case, and the same defect.
#
# The residue, stated rather than hidden: a RELATIVE Windows path whose every segment after the
# first begins with a dot, such as `foo\.config\.env`, is no longer read as a path. Text alone
# cannot tell it from a regex. The absolute form and the forward-slash form are unaffected.
ENV_PATH_PREFIX = re.compile(r"^(\.{1,2}|~|[A-Za-z]:|\S*(/|\\(?![.\\]))\S*)$")

# Runners that read the file into their own environment and echo nothing. `npm` and `npx` reach the
# flag through node, so `node --env-file=.env <npm-cli.js> run x` is the npm form.
ENV_LOADER_COMMANDS = (
    "node", "node.exe", "npm", "npm.cmd", "npm-cli.js", "npx", "npx.cmd", "npx-cli.js",
    "pnpm", "pnpm.cmd", "bun", "bun.exe", "deno", "deno.exe", "uv", "uv.exe",
    "docker", "docker.exe", "docker-compose", "docker-compose.exe", "podman", "podman.exe",
)
ENV_LOADER_FLAGS = ("--env-file", "--env-file-if-exists")

# Commands that ask whether the file is THERE. They read no contents.
ENV_EXISTENCE_COMMANDS = ("ls", "test", "[")

ENV_ADVICE = (
    "Remedy: ask the user for the value and never read the file. "
    "To RUN something that needs those variables, hand the file to the runner with the "
    "--env-file flag ahead of node, npm, npx or a container command. "
    "That loads it into one process's own environment and prints nothing. "
    "A listing and a test for existence are allowed."
)

# THE PRINTED REASONS, AND NONE OF THEM NAMES A FILE. Each one says which shape of access fired,
# so the reader knows what to change, and the log carries the file name for a person to read.
ENV_REDIRECT_REASON = "a redirect would overwrite an environment file"
ENV_VARIABLE_REASON = (
    "a shell variable holds the path of an environment file, and the guard cannot follow "
    "a variable to where it is used"
)
ENV_RUNNER_REASON = (
    "only a runner may be handed an environment file with the loader flag, and this command "
    "is not a runner"
)
ENV_CONTENTS_REASON = (
    "this command would read, write or commit the contents of an environment file"
)
ENV_TOOL_REASON = (
    "an environment file holds the user's own secrets, and this tool would put the contents "
    "in the session"
)

# One shell segment for the environment layer, ported whole. It breaks on `&` as well, because a
# background job is its own command.
SEGMENT_BREAK = re.compile(r"\|\||&&|[;\n|&]")
# A redirect operator, spaced into a word of its own before the words are read.
REDIRECT = re.compile(r"(\d?>>?)")
# ASSIGNMENT (a leading `VAR=value`) is defined once, above, and shared with `resolve_command`.


def env_reference(word: str) -> str:
    """Return the environment file that one shell word names as a path, else ''.

    A reference is the WHOLE BASENAME of the word and never a substring of it. That one property
    keeps `process.env`, `import.meta.env` and `dotenv` out, because in none of them does `.env`
    end a path segment.
    """
    word = word.strip("'\"")
    for separator in ("/", "\\"):
        head, found, tail = word.rpartition(separator)
        if not found:
            continue
        if separator == "\\" and not ENV_PATH_PREFIX.match(head):
            return ""  # `process\.env` is an escaped dot, not a Windows separator
        word = tail
        break
    if word == ENV_ALLOWED or not ENV_BASENAME.match(word):
        return ""
    return word


def env_refusal(cmd: str):
    """Return (printed reason, logged text) when the command touches an environment file.

    Both are the empty string when the command is clean.

    THE PRINTED REASON NAMES NO FILE. CLAUDE.md: "A refusal's printed remedy never names the
    forbidden target." The whole printed reason is covered, not the last sentence of it, so the
    reason says that an environment file was named and nothing more. The file name, the flag and
    the command word go to the log, where a person can read them and a session cannot.

    The command arrives with its own separators intact. Normalizing them is what made a search for
    the environment accessor read as a path.
    """
    for segment in SEGMENT_BREAK.split(cmd):
        words = REDIRECT.sub(r" \1 ", segment).split()
        if not words:
            continue
        # The command is the first word that is not a `VAR=value` assignment.
        position = 0
        while position < len(words) and ASSIGNMENT.match(words[position]):
            position += 1
        head = words[position] if position < len(words) else ""
        command = head.strip("'\"").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        for index, word in enumerate(words):
            prefix, assigned, rest = word.partition("=")
            flag = prefix if assigned and prefix.startswith("-") else ""
            named = env_reference(rest if assigned else word)
            if not named:
                continue
            previous = words[index - 1] if index else ""
            # A redirect onto the file overwrites it, whatever the command turns out to be.
            if REDIRECT.fullmatch(previous):
                return (ENV_REDIRECT_REASON,
                        "a redirect onto '%s' would overwrite the file" % named)
            # A shell variable holding the path. The assignment reads nothing, but the guard cannot
            # follow the variable to its use, so `E=.env; cat $E` would be a one-line way past this
            # whole layer.
            if assigned and not flag:
                return (ENV_VARIABLE_REASON,
                        "a shell variable holds '%s'" % named)
            loaded = flag in ENV_LOADER_FLAGS or previous in ENV_LOADER_FLAGS
            if loaded and command.lower() in ENV_LOADER_COMMANDS:
                continue  # a runner loading it into its own environment prints nothing
            if loaded:
                return (ENV_RUNNER_REASON,
                        "only a runner may be handed '%s' with %s, and '%s' is not one" % (
                            named, flag or previous, command))
            if command in ENV_EXISTENCE_COMMANDS:
                continue  # asking whether the file is there reads none of it
            actor = "'%s'" % command if command else "this command"
            return (ENV_CONTENTS_REASON,
                    "%s would read, write or commit the contents of '%s'" % (actor, named))
    return "", ""


def is_env(path: str) -> bool:
    name = norm(path).rsplit("/", 1)[-1]
    return name.startswith(".env") and name != ENV_ALLOWED


# ------------------------------------------------------------------ the merge into main
#
# Decision 8 ("Merge into main: allow and report") supersedes Decision 2 ("ask always"). CLAUDE.md
# still says "merged only when I name the act", but the owner names the act in chat, and the guard
# cannot read chat. A prompt here would only repeat a decision already made, so the call is
# allowed and NOTED in `guard.log` instead, for a person to read at turn end and the report to
# name under Done.
#
# THE BASE IS QUERIED, never guessed from the command. `gh pr merge 75 --squash` names no base at
# all, because the base is a property of the pull request. A merge into any other base is not
# noted at all, because an integration branch takes its lanes without asking anybody.
#
# AN UNREADABLE BASE IS NOT A SAFE ANSWER, so it is noted the same as a base of main.
GH_PR_MERGE = re.compile(r"\bgh\s+pr\s+merge\b")
PROTECTED_BASE = "main"


def merge_base(cmd: str) -> str:
    """Return the base branch of the pull request the command names, or '' when unreadable.

    The number is the first bare digit word after `merge`. With no number, the tool answers for the
    current branch's pull request, which is the same question one argument shorter.
    """
    named = re.search(r"\bgh\s+pr\s+merge\b([^\n;|&]*)", cmd)
    words = (named.group(1) if named else "").split()
    number = next((w for w in words if w.isdigit()), "")
    # RESOLVE THE PROGRAM FIRST. MEASURED on Windows 2026-09-16: CreateProcess appends `.exe` and
    # never reads PATHEXT, so a call of "gh" skipped a `gh.cmd` earlier on PATH and found a
    # `gh.exe` further along. `shutil.which` reads PATHEXT, so the resolved path is the one the
    # shell would run, and a missing tool is then plain to see.
    program = shutil.which("gh")
    if not program:
        return ""
    query = [program, "pr", "view"] + ([number] if number else []) + ["--json", "baseRefName"]
    try:
        answer = subprocess.run(query, capture_output=True, text=True, timeout=10)
    except Exception:
        return ""
    if answer.returncode != 0:
        return ""
    try:
        parsed = json.loads(answer.stdout)
    except Exception:
        return ""
    if not isinstance(parsed, dict):
        return ""
    return parsed.get("baseRefName", "") or ""


# ------------------------------------------------------------------ the frozen paths
#
# The harness configuration is the owner's. A session that edits its own settings, its own hooks or
# its own CLAUDE.md can grant itself anything, so those files change through a pull request on the
# clone of claude-settings and in no other way.
#
# THE CLONE ITSELF IS NOT FROZEN. `<clone>/settings.json` is the source that the install script
# copies into the config directory, so it must stay editable. The test is that a path is frozen only
# when it sits under the config directory. A file at the root of the clone does not.
#
# A PROJECT'S OWN `.claude/settings.json`, `.claude/settings.local.json`, and `.claude/hooks/*` are
# a SEPARATE, UNFROZEN set (Decision 7: "allow and report"). They decide only that one project's
# session, the owner is often away from the desk, and the edit is not sensitive enough for a hard
# wall. `is_project_config` answers that question; `is_frozen` never does.
CONFIG_FROZEN_FILES = (
    os.path.normcase("settings.json"),
    os.path.normcase("CLAUDE.md"),
)
# This tuple is a literal on purpose, not a read of landed-dirs.txt at the repo root (the
# manifest install.sh and install.ps1 both read). A frozen-path list read from a file shrinks
# to nothing when the file is missing or unreadable, which turns a missing file into a silent
# weakening of a security control. This list must not be shrinkable, so it stays hardcoded here.
# lint/check_landed_dirs.py checks by hand that this set and the manifest agree, `state` (below)
# excepted as a documented guard-only extra.
CONFIG_FROZEN_DIRS = (
    os.path.normcase("hooks"),
    os.path.normcase("lint"),
    os.path.normcase("agents"),
    # `state` holds the baseline `hooks/config_watch.py` restores a reverted file from. A session
    # that could rewrite the baseline could launder a cap lift into it, so the store is frozen on
    # the same terms as the hooks themselves. Rule 7 needs only the PATH, never the value, so this
    # covers every shape rule 8 misses for want of a readable value: `cp`, `mv` and `sed -i`
    # included. The two shapes that hide the path from PreToolUse, `python3 -c` and a script file,
    # are not covered here and `config_watch.py` reports a lost baseline as unknown, never clear.
    os.path.normcase("state"),
)
PROJECT_FROZEN_FILES = ("/.claude/settings.json", "/.claude/settings.local.json")
PROJECT_FROZEN_DIR = "/.claude/hooks/"

FROZEN_REASON = (
    "Rule (configuration): this file decides what a session is allowed to do, so a session "
    "does not change it. "
    "Remedy: edit the clone of claude-settings and open a pull request. "
    "Run the install script after the merge."
)


def config_dir() -> str:
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude"
    )


def _resolved(path: str, cwd: str) -> str:
    target = os.path.expandvars(os.path.expanduser(path.strip("'\"")))
    if re.match(r"^/[a-zA-Z]/", target):  # Git Bash `/c/Users/...` to `C:/Users/...`
        target = target[1].upper() + ":" + target[2:]
    if not os.path.isabs(target) and cwd:
        target = os.path.join(cwd, target)
    return os.path.normcase(os.path.realpath(target))


def is_frozen(path: str, cwd: str) -> bool:
    """True when the path is part of the harness configuration under the config directory.

    Paths are compared after normcase and realpath, so a `~`, a forward slash, a backslash and a
    difference of case all read the same on Windows. A project's own `.claude` files are a
    separate, unfrozen set: see `is_project_config`.
    """
    if not path:
        return False
    try:
        target = _resolved(path, cwd)
        root = os.path.normcase(os.path.realpath(config_dir()))
    except Exception:
        return False
    if not target.startswith(root + os.sep):
        return False
    parts = target[len(root) + 1:].split(os.sep)
    if len(parts) == 1 and parts[0] in CONFIG_FROZEN_FILES:
        return True
    if len(parts) > 1 and parts[0] in CONFIG_FROZEN_DIRS:
        return True
    return False


def is_project_config(path: str, cwd: str) -> bool:
    """True when the path is a project's own `.claude/settings*.json` or `.claude/hooks/*`.

    Decision 7: allowed in any checkout, never denied. The caller logs the edit as `noted` under
    rule `config-edit` instead of refusing it.
    """
    if not path:
        return False
    try:
        target = _resolved(path, cwd)
    except Exception:
        return False
    posix = norm(target)
    if any(posix.endswith(name) for name in PROJECT_FROZEN_FILES):
        return True
    return PROJECT_FROZEN_DIR in posix


# Commands that change a file named in their arguments. `cp` and `mv` stay on the list even when the
# frozen path is their source rather than their target, because guessing wrong on `mv` loses the
# file. Deliberate over-blocking, narrow in scope.
#
# MEASURED in q_max on 2026-09-09 with a POSIX-only list: `Set-Content`, `Out-File`, `Add-Content`
# and `Remove-Item` each wrote a frozen path unrefused. Matching folds case, as PowerShell does.
MUTATING_COMMAND = (
    r"\b(?i:rm|mv|cp|chmod|truncate|tee|install|ln"
    r"|set-content|add-content|clear-content|out-file|new-item|remove-item|move-item|copy-item"
    r"|rename-item|set-itemproperty|ri|rd|rmdir|del|erase|move|copy|ren)\b"
)


def writes_to(path: str, cmd: str) -> bool:
    """True when the command looks like it writes to the path, rather than merely naming it.

    Two ways to write a named file from a shell: redirect onto it, or hand it to a command that
    mutates its arguments. Everything else is a mention.

    MEASURED in q_max on 2026-08-20: reading the TARGET of the redirect is what separates
    `echo x > .claude/settings.json` from `cat .claude/settings.json 2>/dev/null`. The second
    redirects to the null device. It is also what stops a redirect elsewhere on the line from
    counting as a write to a path named in a comment.
    """
    target = re.escape(path)
    if re.search(r"\d?>>?\s*['\"]?" + target, cmd):
        return True
    if re.search(MUTATING_COMMAND + r"[^\n;|&]*" + target, cmd):
        return True
    if re.search(r"\bsed\b[^\n;|&]*-i\b[^\n;|&]*" + target, cmd):
        return True
    return False


def _shell_write_hit(cmd: str, cwd: str, predicate) -> str:
    """Return the path a shell command writes to that `predicate(path, cwd)` accepts, else ''."""
    for segment in split_segments(cmd):
        if not segment.strip():
            continue
        for word in REDIRECT.sub(r" \1 ", segment).split():
            if word.startswith("-") or REDIRECT.fullmatch(word):
                continue
            bare = word.strip("'\"")
            if not bare or bare in (">", ">>"):
                continue
            if predicate(bare, cwd) and writes_to(word, segment):
                return bare
    return ""


def frozen_shell_hit(cmd: str, cwd: str) -> str:
    """Return the frozen (config-dir) path a shell command writes to, else ''."""
    return _shell_write_hit(cmd, cwd, is_frozen)


def project_config_shell_hit(cmd: str, cwd: str) -> str:
    """Return the project config path a shell command writes to, else ''."""
    return _shell_write_hit(cmd, cwd, is_project_config)


# ------------------------------------------------------------------ the subagent model cap
#
# The owner's user settings cap a subagent's model with `CLAUDE_CODE_SUBAGENT_MODEL` and
# `CLAUDE_CODE_SUBAGENT_MODEL_FORCE`. User settings are one layer of the settings stack, and a
# project's own `.claude/settings.json` and `.claude/settings.local.json` override them. Decision 7
# allows a write to both, so the write that Decision 7 allows is also the write that lifts the cap.
#
# The answer is `ask`, never `deny`. The same write is how an Opus worker gets enabled on purpose,
# so the owner answers one call at a time. A wall here would only push the work off the guard's
# path.
#
# THE SETTINGS TEST IS A BASENAME, and it is taken from the RESOLVED path as well as from the
# spelling the tool passed. Rule 7 resolves its own paths with `realpath`, so a basename test on the
# spelling alone would leave rule 8 blind to a shape rule 7 already sees: a symlink named
# `alias.json` that points at a project's `.claude/settings.json`. The resolve sits inside a `try`,
# so the cannot-raise property of this rule holds. The managed settings file joins the list at the
# same price.
SETTINGS_BASENAMES = ("settings.json", "settings.local.json", "managed-settings.json")

# The cap's two variables, and a value beside one of them. The key side carries the optional
# `_FORCE` GREEDILY, so `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` reads as its own key and never as the
# shorter key followed by stray text. One value pattern covers a JSON pair (`"KEY": "value"`) and a
# shell assignment (`KEY=value`), because a heredoc body carries either.
SUBAGENT_CAP_KEY = re.compile(r"CLAUDE_CODE_SUBAGENT_MODEL(?:_FORCE)?")
SUBAGENT_CAP_ASSIGN = re.compile(
    r"(CLAUDE_CODE_SUBAGENT_MODEL(?:_FORCE)?)['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9][A-Za-z0-9._\-]*)"
)

# The fields a write tool carries its content in. `old_string` stands before `new_string`, so that
# `cap_change` reads the value the edit ARRIVES at, not the value it leaves.
#
# EVERY EDIT IS READ. An earlier version of this rule read the first 200 edits of a `MultiEdit`,
# and a review MEASURED the boundary that cap bought an attacker: 199 no-op edits ahead of the cap
# change asked, 200 allowed. A bound that hides a lift is worse than no bound, and the scan is
# cheap: MEASURED 2026-09-19 on this machine, the reading takes 2.8 ms over a 2 MB blob and 11.9 ms
# over an 8 MB blob, linear, and 29 ms over an edit list of 5000. Nothing is capped here, and the
# boundary is gone: 199, 200, 201, 400 and 5000 no-op edits ahead of the lift all ask.
CAP_CONTENT_FIELDS = ("content", "old_string", "new_string", "new_source")

# What the printed reason may carry. A reason is read by a person under time pressure, and it is the
# one reason in this file built from tool-supplied text, so the text is bounded and cleaned first.
CAP_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
CAP_MAX_VALUE = 60
CAP_MAX_CHANGE = 300
CAP_MAX_PATH = 200
CAP_CUT_MARK = " [cut]"

CAP_ASK_REASON = (
    "Rule (configuration): this write sets the subagent model cap, which the owner's user settings "
    "hold. A project settings file overrides user settings, so the write lifts the cap for every "
    "subagent started there. Requested: {change}. File: {where}. "
    "Approve it only when a model above Sonnet is wanted for this project."
)


def is_settings_file(path: str, cwd: str = "") -> bool:
    """True when the path, or the path it resolves to, names a settings file.

    The spelling is tested first, so a path that names no existing file still reads. The resolved
    spelling is tested next, which is what catches a symlink pointing at a settings file. The
    resolve is wrapped, so this predicate cannot raise.
    """
    if not path or not isinstance(path, str):
        return False
    if basename(path) in SETTINGS_BASENAMES:
        return True
    try:
        return basename(_resolved(path, cwd)) in SETTINGS_BASENAMES
    except Exception:
        return False


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


def _json_value_text(value) -> str:
    """Return a JSON value as text, or '' for a value that is not a scalar."""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return ""  # an object, a list or null: the key is named, the value is unread


def json_cap_values(text: str):
    """Return {key: value text} for each cap variable a JSON payload sets, else {}.

    The walk reads KEYS, so a key spelled with a JSON escape (`\\u0043LAUDE_CODE_...`) reads the
    same as a key spelled plainly, and a value the text pattern cannot read, an object or a number,
    still names its key. Content that does not parse as JSON returns {} and leaves the text passes
    to answer. The walk carries its own stack, so a deep payload cannot exhaust the interpreter's.
    """
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    found = {}
    stack = [parsed]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(key, str) and SUBAGENT_CAP_KEY.fullmatch(key.strip()):
                    found[key.strip()] = _json_value_text(value)
                if isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(node, list):
            for value in node:
                if isinstance(value, (dict, list)):
                    stack.append(value)
    return found


def _cap_reading(text: str):
    """Return an ordered {key: value text} for ONE text, empty when it names no cap variable.

    Three passes. THE TEXT PATTERN reads a `"KEY": "value"` pair and a `KEY=value` assignment, for
    text that is no whole JSON document: an `Edit` fragment, a heredoc body, a `sed` expression. The
    LAST assignment of a key wins there, which is what a `sed -i` expression carries: the
    replacement stands after the text it replaces. THE BARE KEY catches a key whose value the
    pattern cannot read, `"$OPUS_ID"` or an opening brace, and leaves it empty, which prints as
    `(value unread)`: the guard never guesses a value the text does not carry. THE JSON WALK reads
    the keys of text that parses as JSON, and its value wins, because it is the value the file will
    hold.

    Inside one text a READABLE value wins over a bare mention, because a key named twice in one blob
    is a settings pair plus a mention of it, not a change.

    THE LIMIT: a key spelled with a JSON escape inside text that does NOT parse as JSON, a heredoc
    body on one shell line for instance, is out of reach of all three passes. The shell route reads
    the whole command, and a command is no JSON document.
    """
    reading = {}
    if not isinstance(text, str) or not text:
        return reading
    for found in SUBAGENT_CAP_ASSIGN.finditer(text):
        reading[found.group(1)] = found.group(2)
    for found in SUBAGENT_CAP_KEY.finditer(text):
        reading.setdefault(found.group(0), "")
    for key, value in json_cap_values(text).items():
        if value or key not in reading:
            reading[key] = value
    return reading


def cap_change_parts(parts) -> str:
    """Return a short reading of each cap variable the write sets or changes, else ''.

    A LATER PART IS AUTHORITATIVE, an unreadable value included. The parts arrive in the order the
    write applies them, `old_string` before `new_string`, edit after edit, so the last part that
    names a key is the part that decides what the file ends up holding. An `Edit` from `"sonnet"` to
    `"$OPUS_ID"` therefore reads `(value unread)`, never `sonnet`: naming the value being LEFT would
    tell the approver the opposite of what is being turned on.
    """
    order = []
    values = {}
    for part in parts:
        for key, value in _cap_reading(part).items():
            if key not in values:
                order.append(key)
            values[key] = value
    if not order:
        return ""
    printed = [key + " = " + (cap_safe(values[key], CAP_MAX_VALUE) or "(value unread)")
               for key in order]
    return cap_safe(", ".join(printed), CAP_MAX_CHANGE)


def cap_change(text: str) -> str:
    """The one-text reading, for the shell route, which judges a whole command."""
    return cap_change_parts([text])


def write_content_parts(tool_input):
    """Return the texts a write tool would put in the file, IN THE ORDER IT APPLIES THEM.

    A list, never one joined blob, so `cap_change_parts` can tell the value an edit leaves from the
    value it arrives at. Every edit of a `MultiEdit` is read: see the measurement beside
    CAP_CONTENT_FIELDS.
    """
    if not isinstance(tool_input, dict):
        return []
    parts = []
    for field in CAP_CONTENT_FIELDS:
        value = tool_input.get(field, "")
        if isinstance(value, str):
            parts.append(value)
    edits = tool_input.get("edits", [])
    if isinstance(edits, list):
        for edit in edits:
            if not isinstance(edit, dict):
                continue
            for field in CAP_CONTENT_FIELDS:
                value = edit.get(field, "")
                if isinstance(value, str):
                    parts.append(value)
    return parts


def cap_ask_reason(change: str, where: str) -> str:
    """Build the printed ask, BOUNDED BY CONSTRUCTION.

    The template is fixed, the change holds at most the cap's two keys with a value of at most
    CAP_MAX_VALUE characters each, and the path is cut at CAP_MAX_PATH. So the reason cannot run
    past roughly 800 characters however long the value or the path a tool passed. `cap_safe` does
    the cleaning and marks each cut.
    """
    return CAP_ASK_REASON.format(change=cap_safe(change, CAP_MAX_CHANGE),
                                 where=cap_safe(where, CAP_MAX_PATH))


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


def record(tool: str, decision: str, rule: str, matched: str) -> None:
    try:
        folder = config_dir()
        os.makedirs(folder, exist_ok=True)
        line = "\t".join([
            datetime.now().isoformat(timespec="seconds"),
            tool or "",
            decision,
            rule,
            log_cut(matched, LOG_MAX_MATCHED),
        ])
        with open(os.path.join(folder, "guard.log"), "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
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


def judge_shell(tool: str, raw: str, cwd: str, session_id: str = "") -> None:
    stripped = strip_heredoc_bodies(raw)
    cmd = norm(stripped)

    # 1. Shared trees.
    for segment in split_segments(stripped):
        if not segment.strip():
            continue
        match = shared_tree_match(segment)
        if match is None:
            continue
        matched, subcommand, args = match
        root = command_root(stripped, cwd)
        resolved = checkout_conflict_resolve(segment, root)
        if resolved:
            record(tool, "noted", "conflict-resolve", resolved)
            continue
        # This session's own scratchpad: private by path, so nothing shared can be lost.
        if under_session_scratchpad(root, session_id):
            continue
        # The subject read. An empty subject is a silent pass. An unreadable subject is allowed
        # and logged under its OWN rule, so a reader can tell "I could not confirm this" from
        # "this destroys something", and the Stop hook names it at the end of the turn.
        state = subject_state(subcommand, args, root)
        if state is None:
            record(tool, "noted", "subject-unread", matched)
            continue
        if state is True:
            continue
        if subcommand == "stash" and stash_takes_the_stack(args):
            refuse(tool, "deny", "shared-tree", STACK_DENY_REASON, matched)
        # A stash PUT reaches here only when it would discard (state is not True above), and its
        # subject is `refs/stash`, the one ref every worktree of this clone already shares. The
        # worktree "ask" below is earned only for a subject that lives in THIS tree alone, so a
        # push denies here instead of falling into that ask.
        if subcommand == "stash":
            refuse(tool, "deny", "shared-tree", PUSH_DENY_REASON, matched)
        worktree = is_worktree(root)
        if worktree is True:
            refuse(tool, "ask", "shared-tree", TREE_ASK_REASON, matched)
        refuse(tool, "deny", "shared-tree", TREE_DENY_REASON, matched)

    # 1b. The pointer checkout's HEAD. Placed AFTER rule 1 on purpose: a `git checkout` that
    # names a path is a path operation, rule 1 already judges it, and this rule never sees it, so
    # the shared-tree clause keeps governing those calls unchanged.
    head_where = head_root(stripped, cwd)
    for segment in split_segments(stripped):
        if not segment.strip():
            continue
        matched = pointer_head_hit(segment, head_where)
        if matched:
            refuse(tool, "deny", "pointer-head", POINTER_HEAD_REASON, matched)

    # 1c. A git write whose own trace is silenced, by a redirect of either stream to a null
    # device, or, on the measured subcommands, by git's own quiet flag alone. Placed after the
    # pointer-head rule and before every rule below, so a silenced write is caught on its own
    # defect before anything else judges the same segment.
    for segment in split_segments(stripped):
        if not segment.strip():
            continue
        matched, mechanism = silent_write_hit(segment)
        if matched:
            reason = (SILENT_WRITE_REDIRECT_REASON if mechanism == "redirect"
                      else SILENT_WRITE_QUIET_REASON)
            refuse(tool, "deny", "silent-write", reason, matched)

    # 2. A machine-wide kill. Judged in COMMAND POSITION, from the segment's own tokens, never
    # by the word appearing anywhere in the text. A segment shlex cannot parse fails open:
    # judge nothing rather than guess what it would run.
    for segment in split_segments(stripped):
        if not segment.strip():
            continue
        tokens = segment_tokens(segment)
        if tokens is None:
            continue
        matched = kill_hit(tokens)
        if matched:
            refuse(tool, "deny", "machine-wide-kill", KILL_REASON, matched)

    # 3. A live stream that never ends, or a waiter loop (Rule 9). A waiter loop whose own
    # condition polls a pattern gets the more specific reason: the pattern can match the loop's
    # own command line and never go false.
    poller = ""
    for segment in split_segments(stripped):
        matched = live_stream_hit(segment)
        if matched:
            refuse(tool, "deny", "live-stream", LIVE_STREAM_REASON, matched)
        poller = loop_condition_polls_a_pattern(segment) or poller
        matched = waiter_hit(segment)
        if matched:
            if poller:
                refuse(tool, "deny", "waiter", PATTERN_POLLER_REASON, poller + " " + matched)
            refuse(tool, "deny", "waiter", WAITER_REASON, matched)

    # 4. A wide delete denies, and a force push asks.
    for pattern in DESTRUCTIVE_DELETE:
        found = pattern.search(cmd)
        if found:
            refuse(tool, "deny", "destructive-delete", DELETE_REASON, found.group(0))
    for segment in split_segments(stripped):
        for subcommand, args in git_calls(segment):
            if subcommand == "push" and push_is_forced(args):
                refuse(tool, "ask", "force-push", PUSH_REASON,
                       "git push " + " ".join(args))

    # 5. The environment file. This layer reads the command BEFORE normalization.
    refusal, logged = env_refusal(stripped)
    if refusal:
        refuse(tool, "deny", "env-file", refusal + ". " + ENV_ADVICE, logged)

    # 6. A merge into main: allow (Decision 8), and note it when the base is main or unreadable.
    if GH_PR_MERGE.search(cmd):
        base = merge_base(stripped)
        if base == PROTECTED_BASE:
            record(tool, "noted", "merge-main", "gh pr merge into " + base)
        elif base == "":
            record(tool, "noted", "merge-main", "gh pr merge, base unread")

    # 7. A frozen path.
    matched = frozen_shell_hit(stripped, cwd)
    if matched:
        refuse(tool, "deny", "frozen-path", FROZEN_REASON, matched)

    # 7b. A project config edit: allowed (Decision 7), and noted in the log only.
    matched = project_config_shell_hit(stripped, cwd)
    if matched:
        record(tool, "noted", "config-edit", matched)

    # 8. The subagent model cap. The PATH comes from the stripped command, the same machinery the
    # frozen path uses, so a redirect, a `tee`, a `sed -i` and a heredoc header all read as writes.
    # The CONTENT comes from the RAW command, because a heredoc body is the content being written
    # and rule 1 strips it. A command that writes a settings file and names the cap variable
    # somewhere else on the line is asked too: an over-trigger of one prompt, inside a scope this
    # narrow, beats a bypass by a second segment.
    matched = _shell_write_hit(stripped, cwd, is_settings_file)
    if matched:
        change = cap_change(raw)
        if change:
            refuse(tool, "ask", "subagent-model-cap", cap_ask_reason(change, matched),
                   log_path_and_text(matched, change))


def judge(payload) -> None:
    tool = payload.get("tool_name", "") or ""
    tool_input = payload.get("tool_input", {}) or {}
    if not isinstance(tool_input, dict):
        return
    cwd = payload.get("cwd", "") or os.getcwd() or ""
    if not isinstance(cwd, str):
        cwd = ""

    # A merge through the MCP tool carries no base for the guard to read, so every call is
    # allowed (Decision 8) and noted, the same as an unreadable `gh pr merge` base.
    if tool in MERGE_TOOLS:
        record(tool, "noted", "merge-main", tool)

    if tool in SHELL_TOOLS:
        command = tool_input.get("command", "") or ""
        if isinstance(command, str) and command.strip():
            judge_shell(tool, command, cwd, session_id_of(payload))
        return

    if tool not in READ_ONLY_TOOLS + WRITE_TOOLS:
        return

    target = (
        tool_input.get("file_path", "")
        or tool_input.get("path", "")
        or tool_input.get("notebook_path", "")
        or ""
    )
    if not isinstance(target, str) or not target:
        return

    # 5. The environment file. Every matched tool is refused, a read included, because the rule is
    # about the contents and a read is contents. The reason names no file, and the log holds the
    # path the tool asked for.
    if is_env(target):
        refuse(tool, "deny", "env-file", ENV_TOOL_REASON + ". " + ENV_ADVICE, target)

    # 7. A frozen path. A read-only tool may look, because reading the hook is how anyone finds out
    # what it does. A writing tool may not.
    if tool not in READ_ONLY_TOOLS:
        if is_frozen(target, cwd):
            refuse(tool, "deny", "frozen-path", FROZEN_REASON, target)
        # 7b. A project config edit: allowed (Decision 7), and noted in the log only.
        if is_project_config(target, cwd):
            record(tool, "noted", "config-edit", target)
        # 8. The subagent model cap. Rule 7 already denied the config directory's own settings, so
        # only a project-scoped or clone-scoped settings file reaches here. The content read is what
        # the tool would WRITE, so a file that carries the variable name anywhere in that content
        # asks, a permission string or a comment line included. That is an over-ask and it stays:
        # the alternative is a value test that a crafted spelling walks past. A write that does not
        # carry the name never fires, and no other file than a settings file reaches this rule.
        if is_settings_file(target, cwd):
            change = cap_change_parts(write_content_parts(tool_input))
            if change:
                refuse(tool, "ask", "subagent-model-cap", cap_ask_reason(change, target),
                       log_path_and_text(target, change))


def main() -> None:
    _force_utf8_streams()
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # fail open on unreadable input
    if not isinstance(payload, dict):
        sys.exit(0)  # fail open on a payload that is not an object
    try:
        judge(payload)
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)  # fail open on a guard defect
    sys.exit(0)


if __name__ == "__main__":
    main()
