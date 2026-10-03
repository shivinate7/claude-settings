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

  0 worktree-home      a call from a subagent (a payload carrying `agent_id`) whose shell `cwd`,
                       or whose Write/Edit/MultiEdit/NotebookEdit target, sits outside that
                       agent's own recorded worktree. Always denied. Read/Grep are never judged
                       here, so a stranded agent can still read and report. No record at all
                       (a non-isolated agent, or the orchestrator) allows everything.
  1 shared-tree        a command that throws away work, judged against the STATE OF ITS SUBJECT:
                       a working tree's uncommitted or untracked files, a deleted branch's only
                       copy, a removed worktree's files, or a pruned worktree's stale record. An
                       empty subject passes, an unreadable subject is allowed and logged as
                       `noted`/`subject-unread`
  1b pointer-head      a command that moves HEAD off `main` in the POINTER checkout, the one
                       checkout every session on this machine runs its hooks and its lint from.
                       Always denied. A move TO `main` restores the invariant and passes.
  1c silent-write      a `commit`, `push`, `merge`, `tag`, `rebase`, or `cherry-pick` whose own
                       trace is silenced, by a redirect of either stream to a null device, or,
                       on `push`/`merge`/`rebase` only (MEASURED), by git's own `-q`/`--quiet`
                       flag alone. `commit`, `tag`, and `cherry-pick`'s own flags are measured
                       carve-outs. `merge --abort` is carved out, and every read subcommand is
                       untouched.
  1d cite-by-id        a `git commit` message or `gh pr create|edit` body that cites a record by
                       its path. Denied. See "three git acts" below.
  2 machine-wide-kill  a kill by name or by pattern, or `kill <pid>` of a live process that is
                       not a descendant of this session's own `claude` process
  2b detached-launch   a command that starts a process and detaches it from the session: a
                       background job inside a subshell (`( cmd & )`), a `nohup`/`setsid`
                       wrapper, `disown` in command position, a bare background job in
                       any segment whose pid nothing in the command captures, the same
                       shapes inside a `sh -c`/`bash -c` script, PowerShell's
                       `Start-Job`, `Start-Process` with neither `-Wait` nor `-PassThru`, or
                       `cmd`/`cmd.exe /c start ...` from either shell. Always denied, the same
                       as rule 2, because a detached process leaves no pid this session can
                       name to stop it later.
  3 live-stream        a command that follows a stream and never ends on its own
  3 waiter             a shell segment whose command word is a sleep-and-poll
  4 force-push         a forced push. Allowed with a lease plus --force-if-includes, denied
                       with --force or a +refspec, asked when it reaches the default branch.
    destructive-delete a recursive delete at a root, a home or a glob
  5 env-file           any read or write of an environment file
  6 merge-checks       a `gh pr merge` (or the MCP merge tool) while the head has a check or run
                       pending or red, or the read could not run. Denied, `--auto` too.
  7 frozen-path        a write to the settings, the hooks or the global CLAUDE.md, under
                       `${CLAUDE_CONFIG_DIR:-$HOME/.claude}`. Always denied.
  8 subagent-model-cap a write to a settings file whose content sets or changes
                       `CLAUDE_CODE_SUBAGENT_MODEL` or `CLAUDE_CODE_SUBAGENT_MODEL_FORCE`.
                       Always asked, never denied.
  9 subagent-model-floor an `Agent` or legacy `Task` call whose `model` is a Haiku model, by alias or
                       by any full id. Always denied. Sonnet is the floor (owner ruling 2026-09-28).
                       An agent file's own `model:` key never reaches this rule, so
                       lint/check_agent_models.py checks the files.

A project's own `.claude/settings.json`, `.claude/settings.local.json`, and
`.claude/hooks/*` are NOT frozen (Decision 7). They are allowed, and the guard appends
one log line with decision `noted` and rule `config-edit`, so a person can see the edit at
turn end. Nothing is printed for a noted edit; the config-report Stop hook is what surfaces
it to the transcript. `subject-unread` is logged the same way: an ALLOW that a person still
gets to see.

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

A merge into main is allowed and never logged by the guard (decisions/guard-trims-from-the-audit.md,
guard trims from the 2026-10-02 audit). `hooks/decision_watch.py` names each merge from the
transcript at turn end. A `git checkout` that carries `--ours`, `--theirs`, or `--merge` while a
merge, rebase, cherry-pick or revert is unresolved in the tree picks a conflict side; it does not
discard work, so rule 1 passes it, with no log line of its own. Any other `git checkout` that
names a path keeps rule 1's ordinary deny or ask.

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

import fnmatch
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
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
            ends is None or ends.append("&&")
            current = []
            index += 2
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
    # PowerShell's escape is the backtick, so a backslash there is a path separator. Doubling it
    # keeps posix shlex from eating it (`C:\\repo` would read as `C:repo`).
    if POWERSHELL_CALL[0]:
        segment = segment.replace("\\", "\\\\")
    try:
        return shlex.split(segment, posix=True)
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
    end = len(tokens)
    index = _skip_assignments_and_keywords(tokens)
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
    tokens = REDIRECTION.sub(" ", segment).split()
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


# `-o` is read in the short-flag loop, where its value may be glued on.
PUSH_VALUE_OPTS = {"--receive-pack", "--exec", "--push-option"}
DEFAULT_BRANCH_FALLBACK = ("main", "master")


def _push_config(cwd: str, key: str, overrides=None):
    """The config value, '' when the key is unset, None when git cannot answer.

    A `git -c key=value` override on the push call wins over the repository's own config.
    """
    if overrides and key.lower() in overrides:
        return overrides[key.lower()]
    answer = _git(cwd, "config", "--get", key) if cwd else None
    if answer is None or answer.returncode not in (0, 1):
        return None
    return answer.stdout.strip()


def _push_current_branch(cwd: str):
    answer = _git(cwd, "symbolic-ref", "-q", "--short", "HEAD") if cwd else None
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

    `refs/remotes/<remote>/HEAD` answers when it exists. A repository with no such ref falls back
    to main and master. No readable repository is unknown, and unknown is never safe.
    """
    if not cwd or not os.path.isdir(cwd):
        return None
    repo = _git(cwd, "rev-parse", "--git-dir")
    if repo is None or repo.returncode != 0:
        return None
    prefix = "refs/remotes/" + remote + "/"
    head = _git(cwd, "symbolic-ref", "-q", prefix + "HEAD")
    if head is not None and head.returncode == 0 and head.stdout.strip().startswith(prefix):
        return (head.stdout.strip()[len(prefix):],)
    return DEFAULT_BRANCH_FALLBACK


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


# ------------------------------------------------------------------ the silent write
#
# Rule 1c. CLAUDE.md (Git): "Never discard a command's output." A discarding REDIRECT is denied on
# every one of these six subcommands, whatever the subcommand does with its own output: the shell
# throws the stream away before git ever gets a say, so a hook's refusal and git's own proof of
# landing are both gone, together, always.
SILENT_WRITE_SUBCOMMANDS = ("commit", "push", "merge", "tag", "rebase", "cherry-pick", "pull")

# Gap roster, 2026-10-03. Banchi's scripts/silent-write-guard.py refused these shapes and this
# shared guard missed them. Each one moves a ref or lands a merge, so each is a write when its
# output is silenced: `pull` (a fetch plus a merge; its `-q` joins the quiet arm), a `fetch` that
# names a `src:dst` refspec (it moves a local ref; a bare `fetch` stays a read), `make merge`,
# `gh pr merge`, and a closed descriptor (`2>&-`, `>&-`), which silences like /dev/null.
# `--dry-run` moves nothing and stays allowed. Output sent to a FILE stays allowed: the owner held
# that until measured.

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
QUIET_FLAG_SUBCOMMANDS = ("push", "merge", "rebase", "pull", "fetch")

# A null-device target, on either stream, in the three shells this guard reads a command from:
# POSIX (`/dev/null`), Windows cmd (`NUL`), and PowerShell (`$null`). `2>&1` duplicates one stream
# onto another file descriptor and is not this: the line still reaches a stream the session reads.
SILENT_WRITE_REDIRECT = re.compile(
    r"(?:&>>?|\d?>>?&?)\s*(['\"]?)(?:/dev/null|NUL|\$null)\1(?=$|[\s;&|])"
    r"|\d?>&-(?=$|[\s;&|])",   # a closed descriptor
    re.IGNORECASE,
)


def discards_output(segment: str) -> bool:
    """True when the segment redirects stdout or stderr, on any descriptor, to a null device."""
    return bool(SILENT_WRITE_REDIRECT.search(segment))


# PIPES, Banchi review #666 (2026-10-03): a write piped into `cat >/dev/null` threw its output
# away through the pipe's LAST command, and the rule judged only the write's own segment.
# A write whose output feeds a pipe is judged by that pipe's tail: silenced by a redirect, or a
# `grep -q`, which prints nothing by itself. A printing tail (`| tail -5`, `| tee f`) is not.
# `bash -c '...'` stays unparsed, a known gap the owner left.
def tail_discards(tail: str) -> bool:
    """True when a pipe's last segment prints nothing the session can read."""
    tail = tail.strip().lstrip("&").strip()   # `|&` leaves a leading `&`
    if discards_output(tail):
        return True
    tokens = segment_tokens(tail) or []
    index = resolve_command(tokens) if tokens else None
    return (index is not None and basename(tokens[index]) == "grep"
            and any(t in ("-q", "--quiet", "--silent") for t in tokens[index + 1:]))


def quiet_write(args) -> bool:
    """True when a git call carries `-q` or `--quiet`."""
    return "-q" in args or "--quiet" in args


def silent_write_hit(segment: str, tail: str = ""):
    """Return (matched text, mechanism) for a write whose own trace is silenced, else ("", "").

    `mechanism` is `"redirect"` or `"quiet"`, so the caller can print the reason that matches
    what actually fired: a redirect can hide a refusal AND a proof of landing on any of the six
    subcommands, while the quiet flag is judged per subcommand against `QUIET_FLAG_SUBCOMMANDS`,
    the measured set. Only `SILENT_WRITE_SUBCOMMANDS` are judged at all. `fetch`, `rev-parse`, and
    every other read subcommand fall outside it, which is what keeps `git fetch -q` and the
    test-by-exit-code shape `git rev-parse -q --verify <ref> >/dev/null 2>&1` allowed. `merge
    --abort` is carved out inside the loop: it lands nothing, so it has no landing to prove.
    `tail` is the last segment of the pipe this segment feeds, if any (see `tail_discards`).
    """
    silenced = discards_output(segment) or (bool(tail) and tail_discards(tail))
    for subcommand, args in git_calls(segment):
        if subcommand == "fetch":
            # Only a fetch that moves a local ref (`src:dst`) is a write; a bare one is a read.
            if not any(":" in a and not a.startswith("-") for a in args):
                continue
        elif subcommand not in SILENT_WRITE_SUBCOMMANDS:
            continue
        if subcommand == "merge" and "--abort" in args:
            continue
        if subcommand in ("fetch", "pull") and "--dry-run" in args:
            continue
        matched = ("git " + subcommand + " " + " ".join(args)).strip()
        if silenced:
            return matched, "redirect"
        if subcommand in QUIET_FLAG_SUBCOMMANDS and quiet_write(args):
            return matched, "quiet"
    if silenced:
        tokens = segment_tokens(segment)
        index = resolve_command(tokens) if tokens else None
        if index is not None:
            word, rest = basename(tokens[index]), tokens[index + 1:]
            if (word == "make" and "merge" in rest) or (
                    word in ("gh", "gh.exe") and rest[:2] == ["pr", "merge"]):
                return word + " " + " ".join(rest), "redirect"
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
# reason. Lifted from `~/Developer/pkmnscan/scripts/shell_parse.py`, which paid this debt first
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
    while cursor < len(tokens):
        token = tokens[cursor]
        if token == "-C":
            return tokens[cursor + 1] if cursor + 1 < len(tokens) else None
        if token in GIT_OPT_WITH_VALUE:
            cursor += 2
            continue
        if token.startswith("-"):
            cursor += 1
            continue
        break
    return None


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


# ------------------------------------------------------------------ each subagent's own worktree
#
# MEASURED 2026-09-27, macOS, one Explore agent with `isolation: 'worktree'`: a PreToolUse payload
# from a subagent carries `agent_id` (e.g. `a64a7f84210a8721d`) and `agent_type`. The
# orchestrator's own payloads carry no `agent_id`. `session_id` is the SAME for the orchestrator
# and its agents, so it never tells them apart. The subagent's `cwd` was
# `<primary>/.claude/worktrees/agent-<agent_id>`, on branch `worktree-agent-<agent_id>`.
#
# An agent resumed after the harness auto-removed its worktree loses BOTH the folder and the
# branch, so git alone cannot tell "never had a worktree" from "worktree was removed". A RECORD
# is needed: decisions/an-agent-outside-its-home-tree-must-stop.md.
#
# The record lives under the CLONE's git common directory, not inside any one worktree, so it
# survives that worktree's removal (`git_common_dir` above). Unmeasured: Windows, and the
# Write/Edit payload shape; covered by fixture in `test_guard.py`, not by a live probe.
AGENT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


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


def agent_home_record_path(where: str, agent_id: str):
    """Return the file that holds `agent_id`'s recorded worktree home, or None when the clone's
    common directory could not be read. Stored under
    `<git-common-dir>/agent-homes/<agent_id>`, so it survives the worktree's own removal."""
    common = git_common_dir(where)
    return os.path.join(common, "agent-homes", agent_id) if common else None


def read_agent_home(where: str, agent_id: str):
    """Return the recorded home for `agent_id`, `''` when no record exists yet, or None when the
    record could not be read at all (no git, no common dir, an unreadable file). `None` is
    UNKNOWN, never a hit: decisions/liveness-read-is-platform-specific-and-unreadable-is-not-death.md."""
    path = agent_home_record_path(where, agent_id)
    if not path:
        return None
    if not os.path.exists(path):
        return ""
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read().strip()
    except Exception:
        return None


def write_agent_home(where: str, agent_id: str, home: str) -> None:
    path = agent_home_record_path(where, agent_id)
    if not path:
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(home)
    except Exception:
        pass


def agent_worktree_home(payload, cwd: str):
    """Return (status, home, primary) for this call's agent.

    status:
      "none"      no valid `agent_id` on the payload: the orchestrator, or a call this rule does
                  not judge at all.
      "unknown"   an `agent_id` is present, but the home record could not be read (no git, no
                  common directory, an unreadable file). Allowed, never a hit (Decision:
                  liveness-read-is-platform-specific-and-unreadable-is-not-death).
      "no-record" the record reads clean and holds nothing, and this call's own `cwd` is not the
                  agent's worktree shape either: a non-isolated agent. Allow everything.
      "home"      `home` names the agent's recorded worktree, whether just written on this call
                  or read back from an earlier one.
    """
    agent_id = payload.get("agent_id") if isinstance(payload, dict) else None
    if not isinstance(agent_id, str) or not AGENT_ID.match(agent_id):
        return "none", "", None
    if not isinstance(cwd, str) or not cwd:
        return "unknown", "", None
    primary = primary_checkout(cwd)
    if not primary:
        return "unknown", "", None
    candidate = os.path.join(primary, ".claude", "worktrees", "agent-" + agent_id)
    recorded = read_agent_home(cwd, agent_id)
    if recorded is None:
        return "unknown", "", primary
    if recorded:
        return "home", recorded, primary
    if path_is_inside(cwd, candidate) is True:
        write_agent_home(cwd, agent_id, candidate)
        return "home", candidate, primary
    return "no-record", "", primary


WORKTREE_HOME_REASON = (
    "Rule (worktree home): this agent's own working tree is gone, or this call reaches outside "
    "it. "
    "Remedy: make no further change. Stop, and report this to your orchestrator."
)


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
        return origin_head.stdout.strip()
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


def worktree_remove_subject(args, where: str):
    """The subject of `git worktree remove <path>` is PATH's own uncommitted and untracked work,
    widened by whether it is locked and whether a live session still stands in it."""
    target = worktree_remove_target(args, where)
    if not target:
        return None
    lines = porcelain(target)
    if lines is None:
        return None
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
# A branch deletion always denies here, never asks: the branch ref lives in the COMMON git
# directory, the same one every worktree of the clone reads, so which checkout the delete runs
# from limits nothing about what is lost. This mirrors PUSH_DENY_REASON's own reasoning for the
# stash stack.
BRANCH_DELETE_DENY_REASON = (
    "Rule (shared trees): this branch holds work that exists nowhere else. It is not an "
    "ancestor of the repository's default branch, its patches are not already on that branch, "
    "and no remote ref contains it. Deleting it loses the only copy. "
    "Remedy: push the branch, or merge it, before it is deleted."
)
# A worktree removal always denies here too. The tree it deletes is not the tree the command RUNS
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
# use, so this asks, never denies, whatever the run location.
WORKTREE_PRUNE_ASK_REASON = (
    "Rule (shared trees): this drops the administrative record of a worktree whose directory no "
    "longer exists. It deletes no files, but the record it drops could belong to another "
    "session. "
    "The click in this prompt is the grant."
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


# ------------------------------------------------------------------ a machine-wide kill
#
# CLAUDE.md: "Never kill a process you did not start. Treat `pkill -f` and `lsof -t` as
# machine-wide." A kill BY NAME or BY PATTERN reaches every matching process on the machine,
# including another agent's dev server, another person's worker, and the editor itself.
#
# A KILL BY PID NAMES ONE PROCESS, so the name rules below pass it. It is judged by OWNERSHIP
# instead: see `foreign_pid_kill`. `taskkill /PID` and `Stop-Process -Id` are the same act under
# the other shell, and neither is refused (unmeasured there: no `ps`).
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


KILL_PID_RE = re.compile(r"^-?[0-9]+$")
ROOT_PID_RE = re.compile(r"[0-9]+")
PID_LISTERS = {"pgrep", "pidof"}   # a kill fed by these names its target by pattern
PID_SUBSTITUTION_RE = re.compile(r"(?:\$\(|`)\s*(?:command\s+)?(?:\S*/)?(pgrep|pidof)\b")
KILL_SIGNAL_ARG_FLAGS = {"-s", "-n"}   # these two take the next token as a signal


def _ps_ppid(pid: int):
    """Parent pid of `pid`; 0 when no such process; None when `ps` could not answer.

    No such process is exit 1 with no output at all. Any other failure is unknown, not death.
    """
    try:
        answer = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True,
                                text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    text = answer.stdout.strip()
    if ROOT_PID_RE.fullmatch(text):
        return int(text)
    return 0 if answer.returncode == 1 and not text and not answer.stderr.strip() else None


def session_root_pid():
    """The pid of this session's own `claude` process, or 0 when it cannot be found.

    MEASURED: every command this session runs, and every hook it fires, descends from one
    process whose command path ends in `claude`. A process another session or the owner's editor
    runs does not. `CLAUDE_GUARD_ROOT_PID` replaces the walk, for the test suite. The harness
    sets the hook's environment, so a command cannot set it, but a settings.json `env` block can.
    """
    forced = os.environ.get("CLAUDE_GUARD_ROOT_PID", "")
    if ROOT_PID_RE.fullmatch(forced):
        return int(forced)
    pid = os.getpid()
    for _ in range(64):
        parent = _ps_ppid(pid)
        if not parent or parent <= 1:
            return 0
        try:
            name = subprocess.run(["ps", "-o", "comm=", "-p", str(parent)], capture_output=True,
                                  text=True, timeout=5).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return 0
        if basename(name) == "claude":
            return parent
        pid = parent
    return 0


def pid_is_owned(pid: int, root: int):
    """True when `pid` is dead or descends from `root`; False when it does not; None unknown.

    `root` itself does not descend from `root`, so it reads False with no check of its own.
    """
    for _ in range(64):
        parent = _ps_ppid(pid)
        if parent is None:
            return None
        if parent <= 1:
            return parent == 0   # dead is owned; reparented to init is not
        if parent == root:
            return True
        pid = parent
    return None


def foreign_pid_kill(tokens) -> str:
    """Return the first numeric pid a `kill` segment names that this session did not start.

    Only literal numbers are judged. `$!`, `$PID`, `%1` and `$(...)` cannot be read here, and
    the remedy tells the agent to kill by `$!`. When the session root or `ps` cannot be read, the
    answer is "" (unknown, so allowed), never a guess. ponytail: a pid reused since launch, or
    a child that reparented to init, reads as foreign; stop it through the harness.
    """
    index = resolve_command(tokens)
    if index is None or basename(tokens[index]) != "kill":
        return ""
    rest = tokens[index + 1:]
    if any(arg == "-l" or arg == "-L" for arg in rest):
        return ""
    root = None
    skip = after_dashes = False
    for arg in rest:
        if skip:
            skip = False
            continue
        if not after_dashes and arg.startswith("-") and arg != "-":
            after_dashes = arg == "--"
            skip = arg in KILL_SIGNAL_ARG_FLAGS
            continue
        if not KILL_PID_RE.match(arg):
            continue
        number = int(arg)
        if number in (0, 1, -1):   # a whole group, init, or every process: judged with no root
            return arg
        if root is None:
            root = session_root_pid()
        if not root:
            return ""
        if pid_is_owned(abs(number) if number < -1 else number, root) is False:
            return arg
    return ""


def kill_fed_by_name(tokens) -> str:
    """Return the matched text when `kill` takes its pids from `pgrep` or `pidof`.

    Two shapes: `kill $(pgrep x)` or a backtick form, and `pgrep x | xargs kill`. Both name the
    target by pattern, the same act as `pkill`. The pipe form reads the segment before the pipe.
    """
    index = resolve_command(tokens)
    if index is None or basename(tokens[index]) != "kill":
        return ""
    found = PID_SUBSTITUTION_RE.search(" ".join(tokens[index + 1:]))
    return "kill " + found.group(1) if found else ""


def kill_fed_by_pipe(tokens, previous) -> str:
    """The `xargs kill` half of `pgrep x | xargs kill`; `previous` is the segment before it."""
    index = resolve_command(tokens)
    if index is None or basename(tokens[index]) != "kill" or not previous:
        return ""
    if not any(basename(word) == "xargs" for word in tokens[:index]):
        return ""
    before = resolve_command(previous)
    if before is not None and basename(previous[before]) in PID_LISTERS:
        return "xargs kill"
    return ""


KILL_PID_REASON = (
    "Rule (shared trees): this stops a process this session did not start. That process may be "
    "another agent's server or the owner's editor. "
    "Remedy: stop only a pid this session started, taken from the $! its own launch printed, "
    "or stop a run_in_background job through the harness's own stop tool. "
    "Leave any other process alone."
)

KILL_REASON = (
    "Rule (shared trees): this stops every process matching a name or a pattern, "
    "machine-wide. This machine runs other agents' servers and the owner's own editor. "
    "Remedy: name one process id that this session started, and stop that one process. "
    "Get that pid from the $! this session's own launch printed, or stop a run_in_background "
    "job through the harness's own stop tool. "
    "Leave any other process alone."
)


# ------------------------------------------------------------------ a detached launch
#
# MEASURED 2026-09-23 on macOS: a subagent ran a background job inside a subshell,
# `(python3 -m http.server 8000 >/tmp/http_server_wtweb.log 2>&1 &)`. The subshell exited at
# once, pid 1 adopted the server, the harness never tracked it, and no pid was kept. Rule 2
# above then correctly refused `pkill -f` and `lsof -t`, but its own remedy asks for "one
# process id that this session started" and gives no way to get one, so the agent left the
# server running. This rule closes that gap: it denies the LAUNCH, before a session can ever
# reach a machine-wide kill trying to clean one up.
#
# THE SAME "resolve, not match" STANCE as rule 2 (see the comment above `KILL_COMMAND_WORDS`):
# every check below reads a segment's OWN tokens, from `segment_tokens`, quote-aware and
# heredoc-safe (the caller already ran `strip_heredoc_bodies`), never the raw text. A quoted
# `"nohup foo &"` passed to `echo` or `grep` is one token to shlex, never equal to the bare
# tokens `nohup`, `&`, or `disown` this file checks for, so it never fires here either.
#
# `nohup`/`setsid` MUST be read BEFORE `resolve_command` unwraps them: `nohup pkill foo` names a
# real kill in command position, and rule 2 above already denies that on its own, unwrapped
# reading. This rule reads the wrapper word ITSELF, with `_skip_assignments_and_keywords`, the
# same prefix skip `resolve_command` uses before it unwraps, so a plain detached launch such as
# `nohup python3 server.py &` is caught here without duplicating rule 2's kill list.
DETACH_WRAPPERS = {"nohup", "setsid"}


def _ends_in_background_paren(tokens) -> bool:
    """Return True when a tokenized segment's last token closes a subshell right after a bare
    background job: `( cmd & )` (spaced, two trailing tokens) or `(cmd &)` (fused, one)."""
    if len(tokens) < 2:
        return False
    last = tokens[-1]
    if last == ")":
        return tokens[-2] == "&"
    return last.endswith(")") and last[:-1].endswith("&")


def detach_wrapper_hit(tokens) -> str:
    """Return the matched word when a segment's own head, BEFORE any wrapper unwrap, is `nohup`
    or `setsid`, else ''."""
    index = _skip_assignments_and_keywords(tokens)
    if index >= len(tokens):
        return ""
    word = tokens[index]
    return word if basename(word) in DETACH_WRAPPERS else ""


def disown_after_background_hit(tokens) -> str:
    """Return "& disown" when a bare background job (`&` in token position) in this segment is
    followed by `disown` in command position, else ''. Also "disown" when the segment's OWN
    command word is `disown`: MEASURED 2026-09-26 on Windows, `cmd &` then `disown` on the next
    line was allowed, and the server outlived the agent (the start-shapes entry, PR #144).
    `disown` has no use but to detach a job, so it denies in command position anywhere."""
    j = _skip_assignments_and_keywords(tokens)
    if j < len(tokens) and basename(tokens[j]) == "disown":
        return "disown"
    for i, tok in enumerate(tokens):
        if tok != "&":
            continue
        rest = tokens[i + 1:]
        j = _skip_assignments_and_keywords(rest)
        if j < len(rest) and basename(rest[j]) == "disown":
            return "& disown"
    return ""


def windows_detach_hit(tokens) -> str:
    """Return the matched word when a segment's command word is a PowerShell launch the
    harness cannot track, else ''.

    `Start-Job` always denies: it hands the work to a job object in a separate PowerShell
    process, and this session never holds a pid for it at all. `Start-Process` denies only
    when neither `-Wait` (blocks until the child exits, so nothing outlives the turn) nor
    `-PassThru` (hands back the process object, whose `.Id` is the pid the remedy needs) is
    present, whatever else it carries, `-WindowStyle Hidden` included. MEASURED 2026-09-24
    against local transcripts: every real `Start-Process` call found (4, all through the
    PowerShell tool) already carries `-PassThru`, and `Start-Job` never appears at all, so
    this condition refuses none of them.
    """
    index = resolve_command(tokens)
    if index is None:
        return ""
    word = tokens[index]
    tool = basename(word)
    if tool == "start-job":
        return word
    if tool == "start-process":
        rest = {t.lower() for t in tokens[index + 1:]}
        if "-wait" in rest or "-passthru" in rest:
            return ""
        return word
    return ""


def cmd_start_hit(tokens) -> str:
    """Return the matched text when a segment's command word is `cmd`/`cmd.exe` and its `/c`
    or `/k` flag runs `start`, else ''.

    Windows' own `start` opens a new, untracked window the same way a subshell background job
    does on POSIX: the launched program outlives `cmd.exe`'s own exit, and no rule here ever
    gets a pid for it. Checked from EITHER shell: PowerShell can call `cmd.exe /c start ...`
    exactly as Bash can. MEASURED 2026-09-24 against local transcripts: 0 occurrences, so this
    shape refuses no harmless command this session has actually seen run.
    """
    index = resolve_command(tokens)
    if index is None:
        return ""
    if basename(tokens[index]) not in ("cmd", "cmd.exe"):
        return ""
    rest = tokens[index + 1:]
    for i in range(len(rest) - 1):
        if rest[i].lower() in ("/c", "/k") and rest[i + 1].lower() == "start":
            return tokens[index] + " " + rest[i] + " start"
    return ""


def bare_background_hit(cmd: str) -> str:
    """Return the matched text when ANY segment holds a bare background job (`&` as its own
    token, after the command word) with no pid captured anywhere in the command, else ''.

    MEASURED 2026-09-24 against this machine's own local transcripts (`~/.claude/projects/*/
    *.jsonl`, read-only): 16571 Bash commands across 116 sessions, 0 ended in a bare trailing
    `&`. This shape refuses no harmless command this session has actually seen run.

    MEASURED 2026-09-26 on Windows (the start-shapes entry, PR #144): an earlier version read
    the LAST segment only, so `cmd &` followed by another line was allowed, and that server
    outlived the agent. The `&` must come AFTER the command word: a leading `&` is
    PowerShell's call operator, never a background job.

    MEASURED 2026-09-26 against 13312 distinct local Bash commands in 118 sessions: the
    any-segment read refused 6 that the old rule allowed. All 6 were an `&` inside a python
    heredoc body, Python code, not a shell job. So this read drops every heredoc body first.
    """
    cmd = _strip_heredoc_bodies_unconditionally(cmd)
    if "$!" in cmd:
        return ""
    for segment in split_segments(cmd):
        tokens = segment_tokens(segment) if segment.strip() else None
        if not tokens:
            continue
        start = _skip_assignments_and_keywords(tokens)
        for i in range(start + 1, len(tokens)):
            if tokens[i] == "&":
                return tokens[i - 1] + " &"
    return ""


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


def detached_launch_hit(cmd: str) -> str:
    """Return the matched text when the command starts a process and detaches it from the
    session, else ''. Checked per segment first (the subshell, the wrapper, and disown), then
    once over the whole command (the bare trailing background job, whose "no pid captured"
    half of the test is not a per-segment question)."""
    for segment in split_segments(cmd):
        if not segment.strip():
            continue
        tokens = segment_tokens(segment)
        if not tokens:
            continue
        if tokens[0].startswith("(") and _ends_in_background_paren(tokens):
            return tokens[0] + " ... " + tokens[-1]
        matched = (detach_wrapper_hit(tokens) or disown_after_background_hit(tokens)
                   or windows_detach_hit(tokens) or cmd_start_hit(tokens))
        if matched:
            return matched
        script = inline_script(tokens)
        if script and detached_launch_hit(script):
            return basename(tokens[resolve_command(tokens)]) + " -c '" + detached_launch_hit(
                script) + "'"
    return bare_background_hit(cmd)


DETACHED_LAUNCH_REASON = (
    "this starts a process and detaches it from the session, so no rule here can later name a "
    "pid to stop it. "
    "Remedy: use the Bash or PowerShell tool's run_in_background so the harness tracks the "
    "process. Or capture a pid yourself: `cmd & echo $!` in Bash, or `$p = Start-Process ... "
    "-PassThru` in PowerShell, then stop it later with `kill <pid>` or `Stop-Process -Id "
    "<id>`. Take a free port, such as port 0 or a random high port, never a port another "
    "project may own, such as 8000, 5173, 3000, or 8080."
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


# A COMMAND THAT NARRATES WHILE IT WAITS, piped into `tail` or `head`. Ported from pkmnscan's
# `scripts/guard-shell.py` (the heartbeat clause), behaviour only. The merge tool waits minutes for
# a claim commit's checks and prints a line a minute. A pipe block-buffers that heartbeat and the
# filter keeps one end of it, so a working wait reads as a hang. The roster is NAMED, one entry per
# incident, because "does this command narrate for minutes" cannot be resolved from the system, and
# refusing every `| tail` is the cry-wolf guard (decisions/guard-that-cries-wolf-is-spent.md). `tee`
# keeps every byte, so it is not refused. Only `--confirm` reaches the wait: a bare `merge <pr>` is a
# preview that returns in seconds, so piping it is allowed.
NARRATING_COMMANDS = ("merge", "merge.cmd")
NARRATING_SCRIPT_TAILS = ("merge/merge.py", "merge/launch.py")
TRUNCATING_FILTERS = ("tail", "head")


def narrating_stage(segment: str) -> str:
    """The command word when one segment is a long, narrating `--confirm` run, else ''."""
    tokens = segment_tokens(segment)
    if not tokens or "--confirm" not in tokens:
        return ""
    index = resolve_command(tokens)
    if index is None:
        return ""
    word = basename(tokens[index])
    if word in NARRATING_COMMANDS:
        return word
    for token in tokens[index:]:
        if token.replace("\\", "/").endswith(NARRATING_SCRIPT_TAILS):
            return word + " " + basename(token)
    return ""


def narrated_tail_hit(stripped: str) -> str:
    """Return the matched text when a narrating stage is piped straight into `tail`/`head`."""
    ends = []
    segments = split_segments(stripped, ends)
    for index in range(len(segments) - 1):
        if ends[index] != "|":
            continue
        stage = narrating_stage(segments[index])
        if not stage:
            continue
        tokens = segment_tokens(segments[index + 1])
        if not tokens:
            continue
        at = resolve_command(tokens)
        if at is not None and basename(tokens[at]) in TRUNCATING_FILTERS:
            return stage + " | " + basename(tokens[at])
    return ""


NARRATED_TAIL_REASON = (
    "this command waits for minutes and prints a line as it goes, and a pipe into a filter "
    "that keeps one end of the stream hides that line until the end, so a working wait looks "
    "like a hang. "
    "Remedy: run the command with nothing after it and read its output as it arrives, or "
    "redirect to a file you read back afterwards, or use tee to keep a full copy."
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
WIDE_TARGET = (
    r"(?:/|~|\.|\*|\$HOME|%USERPROFILE%|\$env:USERPROFILE|[A-Za-z]:/?\*?)"
)
DESTRUCTIVE_DELETE = (
    re.compile(
        r"\brm\s+(?:-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r)\s+['\"]?"
        + WIDE_TARGET + r"['\"]?(?:\s|$)"
    ),
    re.compile(
        r"(?i)\b(?:remove-item|ri|rd|rmdir|del|erase|rm)\b"
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
CMD_EXE_NAMES = {"cmd", "cmd.exe"}


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
ENV_EXISTENCE_COMMANDS = ("ls", "test", "[", "[[")

# Commands that only print their own arguments. An env name among the arguments is TEXT, printed to
# stdout or written to a file that is NOT an environment file (`echo <name> > .worktreeinclude`),
# and no environment file is read or written. A redirect onto an environment file is refused first. `cat <name> > x` is not on the list, so it stays held.
ENV_TEXT_COMMANDS = ("echo", "printf")
# A search command's pattern is a regex, never a path: a lone dot-star pattern reads no
# environment file. MEASURED in guard.log 2026-09-16 to 10-02: 65 false `env-file` denies.
ENV_PATTERN_COMMANDS = ("grep", "egrep", "fgrep", "rg", "ag", "ack")
ENV_PATTERN_FLAGS = ("-e", "--regexp")
ENV_PATTERN_VALUE_FLAGS = ("-A", "-B", "-C", "-m")  # a count follows, never the pattern

# The message or body of a commit or a pull request is text. Its value is blanked before the words
# are read, so an env name in prose reads no contents. A substitution in the value is cut out
# and judged as a command first, by `_substitutions`.
ENV_MESSAGE_COMMAND = re.compile(r"\s*(git\s+commit|gh\s+pr\s+create)\b")
ENV_MESSAGE_ARG = re.compile(
    r"""(?P<flag>(?:-m|--message|--title|--body)(?:=|\s+))"""
    r"""(?P<value>"(?:[^"\\]|\\.)*"|'[^']*')""")
# The text ahead of a substitution that sits inside a message argument, so a substitution that
# only prints text there is text.
ENV_IN_MESSAGE = re.compile(r"(?:-m|--message|--title|--body)(?:=|\s+)\"(?:[^\"\\]|\\.)*$")


def _blank_messages(segment: str) -> str:
    if not ENV_MESSAGE_COMMAND.match(segment):
        return segment

    def blank(match):
        value = match.group("value")
        return match.group("flag") + value[0] + "x" + value[0]

    return ENV_MESSAGE_ARG.sub(blank, segment)

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

# A redirect operator, spaced into a word of its own before the words are read.
REDIRECT = re.compile(r"(\d?>>?)")
# A `<` redirect (not `<<` or `<<<`), spaced into a word of its own. The word after it is READ.
READ_REDIRECT = re.compile(r"(?<![<])<(?![<(])")
# ASSIGNMENT (a leading `VAR=value`) is defined once, above, and shared with `resolve_command`.


def _ampersand_split(segment: str):
    """Split one `split_segments` segment further, on a bare, unquoted `&`.

    `split_segments` cuts on `;`, `|`, `||`, `&&` and newline, but not on a LONE `&`, because
    that splitter serves callers for whom a backgrounded command is still one segment. The
    environment layer needs the opposite: a background job is its own command, so `cat .env &`
    must not let the backgrounding operator hide the read behind an empty tail. This is the one
    genuinely different rule env_refusal needs on top of `split_segments`, kept small and
    quote-aware the same way: text inside a quote is never split, whatever character it holds.
    """
    parts = []
    current = []
    quote = ""
    for char in segment:
        if quote:
            current.append(char)
            if char == quote:
                quote = ""
            continue
        if char in ("'", '"'):
            quote = char
            current.append(char)
            continue
        if char == "&":
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return parts


# The deepest nest of substitutions the guard reads. A command nested deeper is REFUSED: a nest that
# no honest command needs is a way to make the reader give up, and giving up must not allow it.
ENV_MAX_DEPTH = 64
ENV_DEPTH_REASON = "substitutions are nested too deep for the guard to read"


def _substitutions(cmd: str, depth: int = 0):
    """Return ([(text, in a message)], too_deep). The last text is the command itself.

    One pass, no recursion. Each command substitution `$(...)`, backtick pair or process
    substitution `<(...)` `>(...)` met OUTSIDE single quotes is its own text, and its place in the
    text around it is `x`. Every text is then judged as a command of its own, at any depth. The
    work is linear: a text holds only its own characters and one `x` per child.

    ponytail: a backtick body is read again by a recursive call. A nested backtick needs a
    backslash per level, so honest input never nests them, and past ENV_MAX_DEPTH it is refused.
    """
    if depth > ENV_MAX_DEPTH:
        return [], True
    done = []
    # a frame: [pieces of its text, open quote, paren depth, it is a message value, its open
    # quote holds a message value]
    stack = [[[], "", 0, False, False]]
    i, n = 0, len(cmd)

    def close():
        pieces, _, _, message, _ = stack.pop()
        done.append(("".join(pieces), message))

    def opens_message(pieces):
        """True when a `"` opened now is the value of a message flag of a commit or a PR."""
        if not re.search(r"(?:-m|--message|--title|--body)(?:=|\s+)$", "".join(pieces[-12:])):
            return False
        tail = []
        for piece in reversed(pieces):
            if piece in ";|&\n":
                break
            tail.append(piece)
        return bool(ENV_MESSAGE_COMMAND.match("".join(reversed(tail))))

    while i < n:
        char = cmd[i]
        frame = stack[-1]
        pieces, quote = frame[0], frame[1]
        if char == "\\" and quote != "'":
            pieces.append(cmd[i:i + 2])
            i += 2
            continue
        if quote == "'":
            frame[1] = "" if char == "'" else quote
        elif char == "'" and quote == "":
            frame[1] = "'"
        elif char == '"':
            frame[1] = "" if quote == '"' else '"'
            frame[4] = quote == "" and opens_message(pieces)
        elif char == "`":
            j = i + 1
            while j < n and cmd[j] != "`":
                j += 2 if cmd[j] == "\\" else 1
            inner, deep = _substitutions(cmd[i + 1:j].replace("\\`", "`"), depth + 1)
            if deep:
                return [], True
            done.extend(inner)
            pieces.append("`x`")
            i = j + 1
            continue
        elif cmd[i:i + 2] == "$(" or (quote == "" and cmd[i:i + 2] in ("<(", ">(")):
            if len(stack) + depth > ENV_MAX_DEPTH:
                return [], True
            message = quote == '"' and frame[4]
            pieces.append("x")
            stack.append([[], "", 0, message, False])
            i += 2
            continue
        elif quote == "" and len(stack) > 1 and char == "(":
            frame[2] += 1
        elif quote == "" and len(stack) > 1 and char == ")":
            if frame[2] == 0:
                close()
                i += 1
                continue
            frame[2] -= 1
        pieces.append(char)
        i += 1
    while stack:
        close()
    # the outermost text closed last, so it is last
    return done, False


# A word that holds a glob. It is an environment word when it could match `.env`, or `.env.` and any
# suffix. The test is a sample of the pattern itself (each glob filled in as the shortest and a one
# letter match), so `.env.s*` and `.env.bak*` count with no list of suffixes to keep. A word that
# starts with the example file's name stays exempt, as the example file is.
#
# ACCEPTED LIMITS, each named so nobody trusts this layer past them:
#   - a brace or variable split (`.env{,.x}`, `.e$Xnv`) cannot be read statically;
#   - a dot glob such as `cat .*` or `tar .*` refuses, on purpose, as it sweeps in `.env`;
#   - `find -name '.env*'` refuses, and `ls` or `git ls-files` is the way to list;
#   - a relay split across two separate tool calls (write the name to a file in one, read the file
#     in the next) cannot be seen by a per-command guard;
#   - the relay check matches the literal path, so another spelling of the same file (`./f`, or
#     `~/f` against `$HOME/f`) is not caught. The guard does not resolve paths.
ENV_GLOB = re.compile(r"[?*\[]")
ENV_GLOB_PART = re.compile(r"\[[!^]?([^\]])[^\]]*\]|\?|\*")


def _glob_could_name_env(word: str) -> bool:
    if word.startswith(ENV_ALLOWED):
        return False
    if any(fnmatch.fnmatchcase(name, word) for name in (".env", ".env.x")):
        return True
    for fill in ("", "x"):
        sample = ENV_GLOB_PART.sub(
            lambda m: (m.group(1) or "a") if m.group(0) != "*" else fill, word)
        if sample == ".env" or sample.startswith(".env."):
            return True
    return False


def env_reference(word: str) -> str:
    """Return the environment file that one shell word names as a path, else ''.

    A reference is the WHOLE BASENAME of the word and never a substring of it. That one property
    keeps `process.env`, `import.meta.env` and `dotenv` out, because in none of them does `.env`
    end a path segment.

    The word is normalized first, the way the shell reads it: inner quotes go, so `.e""nv` and
    `'.e'nv` are `.env`, and so does a backslash that is not an escaped dot, so `.e\\nv` is. A
    glob that starts with a dot and could match a name, such as `.en?` or `.env*`, is the name.
    """
    word = re.sub(r"[\"'`]", "", word).strip("()")
    for separator in ("/", "\\"):
        head, found, tail = word.rpartition(separator)
        if not found:
            continue
        if separator == "\\" and not ENV_PATH_PREFIX.match(head):
            break  # `process\.env` is an escaped dot, not a Windows separator
        word = tail
        break
    word = re.sub(r"\\(?!\.)", "", word)
    if word == ENV_ALLOWED:
        return ""
    if ENV_GLOB.search(word) and word.startswith("."):
        return word if _glob_could_name_env(word) else ""
    if not ENV_BASENAME.match(word):
        return ""
    return word


def env_refusal(cmd: str, subs_only: bool = False):
    """Return (printed reason, logged text) when the command touches an environment file.

    Both are the empty string when the command is clean.

    THE PRINTED REASON NAMES NO FILE. CLAUDE.md: "A refusal's printed remedy never names the
    forbidden target." The whole printed reason is covered, not the last sentence of it, so the
    reason says that an environment file was named and nothing more. The file name, the flag and
    the command word go to the log, where a person can read them and a session cannot.

    The command arrives with its own separators intact. Normalizing them is what made a search for
    the environment accessor read as a path.

    Every substitution is cut out and judged as a command of its own, at any depth. `text_ok` is
    set for one that sits in a commit or pull request message: an `echo` or `printf` there only
    prints text, so its arguments are data. `subs_only` judges the substitutions and not the text
    around them, for the body of a heredoc.
    """
    texts, too_deep = _substitutions(cmd)
    if too_deep:
        return ENV_DEPTH_REASON, "substitutions nested past %d levels" % ENV_MAX_DEPTH
    if subs_only:
        texts = texts[:-1]
        if not texts:
            return "", ""  # a body with no substitution is text: nothing to judge, and no crash
    for index, (text, in_message) in enumerate(texts):
        # The command itself is last. Its `echo` or `printf` prints to stdout or a file, and an env
        # name among the arguments is text. A substitution's output is an ARGUMENT of the command
        # around it, so only a message value may treat it as text.
        refusal = _env_flat(text, in_message or index == len(texts) - 1)
        if refusal[0]:
            return refusal
    return _env_relay(texts)


def env_heredoc_refusal(raw: str):
    """`env_refusal` for the substitutions in the body of each UNQUOTED heredoc.

    `strip_heredoc_bodies` drops a body before the layers run, and that is right for text. An
    unquoted body still runs its `$(...)`, backticks and `<(...)`, so those are judged. A quoted
    delimiter (`<<'EOF'`) makes the body text, and it stays dropped.
    """
    for quote, body in _split_heredocs(raw)[1]:
        if not quote:
            refusal = env_refusal(body, subs_only=True)
            if refusal[0]:
                return refusal
    return "", ""


def _env_parts(piece: str):
    """`_ampersand_split` of one segment, with an fd duplication (`2>&1`, `>&2`) taken out first.
    Its `&` is no background operator, and left in, it cut the text command from the pipe after it.
    `&>` and `>&file` are a plain redirect."""
    piece = re.sub(r"\d*>&(\d+|-)", " ", piece)
    piece = re.sub(r"&>>?|>&(?![\d-])", lambda m: m.group(0).replace("&", ""), piece)
    return _ampersand_split(piece)


def _pattern_words(words, position: int):
    """Return the indexes of the words a search command reads as its PATTERN, never as a path.

    With `-e` or `--regexp`, the word after each one is a pattern. Without, the first plain word
    is. A flag's own value (`-A 3`) can stand first and is then skipped in the pattern's place,
    which only ever leaves a real path judged, never hides one.
    """
    if any(w in ("-f", "--file") or w.startswith("--file=") for w in words[position + 1:]):
        return set()  # patterns come from a file: its name is a path, and every word is judged
    marked = {i + 1 for i, w in enumerate(words) if w in ENV_PATTERN_FLAGS and i > position}
    if marked:
        return marked
    for i in range(position + 1, len(words)):
        if (words[i].startswith("-") or REDIRECT.fullmatch(words[i])
                or REDIRECT.fullmatch(words[i - 1]) or words[i - 1] in ENV_PATTERN_VALUE_FLAGS):
            continue
        return {i}
    return set()


def _assignment_end(words, position: int) -> int:
    """Return the index after the `VAR=value` assignment that starts at `position`. A quoted value
    with a space (`ADMINS='Shivam Semwal'`) spans several words, and its tail must not read as the
    command word. MEASURED: 29 false `env-file` denies named an author's surname as the command."""
    quote = next((c for c in "'\"" if words[position].partition("=")[2].count(c) % 2), "")
    end = position
    while quote and end + 1 < len(words):
        end += 1
        if quote in words[end]:
            break
    return end + 1


def _env_words(segment: str):
    """Return (words, command word) of one segment, redirects spaced into words of their own."""
    words = READ_REDIRECT.sub(" < ", REDIRECT.sub(
        r" \1 ", _blank_messages(segment))).split()
    # The command is the first word that is not a `VAR=value` assignment.
    position = 0
    while position < len(words) and ASSIGNMENT.match(words[position]):
        position = _assignment_end(words, position)
    head = words[position] if position < len(words) else ""
    command = head.strip("'\"").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if command in ENV_TEXT_COMMANDS:
        # `printf '<name>\n'` prints the name and a newline: the escape ends the word.
        words = re.sub(r"\\[ntr]", " ", " ".join(words)).split()
    return words, position, command


# Commands that take a file name and read none of its contents to run it: they ask, list or record.
ENV_RELAY_SAFE = ENV_EXISTENCE_COMMANDS + ENV_TEXT_COMMANDS + ("git",)


def _env_relay(texts):
    """Return (reason, log) when a text command writes an env name into a file that another
    segment of the SAME command reads. `echo <name> > f; cat $(cat f)` prints the name to a file
    and then reads the file the name points at. A relay split across two separate tool calls
    cannot be seen by a per-command guard, and that is an accepted limit.
    """
    segments = [[_env_words(seg) for piece in split_segments(text) for seg in _env_parts(piece)]
                for text, _ in texts]

    def gives_a_name(words, command):
        return command in ENV_TEXT_COMMANDS and any(
            env_reference(w) for i, w in enumerate(words)
            if i and not REDIRECT.fullmatch(words[i - 1]))

    def targets(words):
        return {w for i, w in enumerate(words) if i and REDIRECT.fullmatch(words[i - 1])}

    def reads(words, command, files):
        return command not in ENV_RELAY_SAFE and any(
            w in files and not (i and REDIRECT.fullmatch(words[i - 1]))
            for i, w in enumerate(words))

    # The command itself is the last text, and its segments run in order: a read before the write
    # is the check-then-write setup, and is no relay. A substitution runs at a place this scan
    # does not track, so a read inside one counts against every write.
    written = set()
    for text in segments:
        for words, _, command in text:
            if gives_a_name(words, command):
                written |= targets(words)
    for text in segments[:-1]:
        if any(reads(words, command, written) for words, _, command in text):
            return ENV_CONTENTS_REASON, "a substitution reads a file that was given an environment name"
    written = set()
    for words, _, command in segments[-1]:
        if reads(words, command, written):
            return (ENV_CONTENTS_REASON,
                    "'%s' would read a file that was just given an environment name" % command)
        if gives_a_name(words, command):
            written |= targets(words)
    return "", ""


def _env_flat(cmd: str, text_ok: bool = False):
    """The segment rules over one text whose substitutions are already cut out."""
    ends = []
    pieces = split_segments(cmd, ends)
    for piece, end in zip(pieces, ends):
        parts = _env_parts(piece)
        for number, segment in enumerate(parts):
            words, position, command = _env_words(segment)
            if not words:
                continue
            # A segment that pipes onward hands its output to another command, which may read it
            # as a path. Only its stdout to the terminal or to a file keeps the text allowance.
            piped = end == "|" and number == len(parts) - 1
            # `git check-ignore <path>` asks git whether a path is ignored. It reads no contents.
            rest_words = [w for w in words[position + 1:] if not w.startswith("-")]
            # Only positional paths. `--stdin`, `-z` and a `<` redirect feed it contents to print.
            names_only = (
                command == "git" and rest_words[:1] == ["check-ignore"] and "<" not in segment
                and not any(w == "--stdin" or re.fullmatch(r"-[A-Za-z]*z[A-Za-z]*", w)
                            for w in words))
            # A text command's arguments are data. A redirect onto an environment file is refused
            # below, first.
            text_to_file = command in ENV_TEXT_COMMANDS and text_ok and not piped
            patterns = _pattern_words(words, position) if command in ENV_PATTERN_COMMANDS else ()
            for index, word in enumerate(words):
                if index in patterns:
                    continue
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
                # A shell variable holding the path. The assignment reads nothing, but the guard
                # cannot follow the variable to its use, so `E=.env; cat $E` would be a one-line
                # way past this whole layer.
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
                if names_only or text_to_file:
                    continue  # the name is data, and no contents are read or written
                if command in ENV_EXISTENCE_COMMANDS:
                    continue  # asking whether the file is there reads none of it
                actor = "'%s'" % command if command else "this command"
                return (ENV_CONTENTS_REASON,
                        "%s would read, write or commit the contents of '%s'" % (actor, named))
    return "", ""


def is_env(path: str) -> bool:
    name = norm(path).rsplit("/", 1)[-1]
    return name.startswith(".env") and name != ENV_ALLOWED


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
    # janitor/sweep.py deletes branches and worktrees. A session must not rewrite a program that
    # deletes things, same reasoning as hooks/lint/agents, so it lands here too (plan:
    # janitor-build-plan.md, "The code lands in a new janitor/ directory").
    os.path.normcase("janitor"),
    # bin/ holds the merge shim that every merge runs. Same reasoning as janitor.
    os.path.normcase("bin"),
    # output-styles/ holds the rules for the main session's replies. A session that could rewrite
    # its own style could loosen those rules, same reasoning as agents/.
    os.path.normcase("output-styles"),
    # `state` holds the baseline `hooks/config_watch.py` restores a reverted file from. A session
    # that could rewrite the baseline could launder a cap lift into it, so the store is frozen on
    # the same terms as the hooks themselves. Rule 7 needs only the PATH, never the value, so this
    # covers every shape rule 8 misses for want of a readable value: `cp`, `mv` and `sed -i`
    # included. The two shapes that hide the path from PreToolUse, `python3 -c` and a script file,
    # are not covered here and `config_watch.py` reports a lost baseline as unknown, never clear.
    os.path.normcase("state"),
)
# skills/ is NOT frozen whole: a person's own skills under ~/.claude/skills stay writable.
# Only the skills this repo ships are frozen, one name per entry, because a skill's frontmatter
# `allowed-tools` can grant tools without a prompt, so a session that could edit a landed skill
# could grant itself tools the same way it could through a rewritten hook. lint/check_landed_dirs.py
# checks by hand that this set matches the repo's own skills/*/ subdirectories.
CONFIG_FROZEN_SKILLS = (
    os.path.normcase("ci-hygiene"),
    os.path.normcase("compliance-check"),
    os.path.normcase("fresh-prose"),
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


def _literal_resolved(path: str, cwd: str) -> str:
    """Same reading as `_resolved`, but stops short of following a symlink: `..`, a trailing
    slash and case are normalized, the path's own leaf is not.

    `install.sh` lands every frozen file under the config directory as a symlink INTO the clone
    (`~/.claude/hooks/guard.py -> <clone>/hooks/guard.py`). `_resolved`'s realpath follows that
    link and reports a path that has already left the config directory, which is the live-path
    gap `is_frozen` closes by also checking this literal reading.
    """
    return os.path.normcase(os.path.normpath(_expanded(path, cwd)))


def is_frozen(path: str, cwd: str) -> bool:
    """True when the path is part of the harness configuration under the config directory.

    A path is frozen when EITHER its literal spelling (no symlink followed) OR its fully
    resolved spelling (every symlink followed) sits under the config directory. The literal
    reading catches the LIVE path itself, which `install.sh` lands as a symlink into the clone:
    realpath alone follows that link back out and misses it. The resolved reading keeps
    catching a symlink a session creates ELSEWHERE that points INTO the config directory -- a
    symlink is a spelling of the file it points at, same as rule 8's alias case. Case and a
    trailing slash read the same either way, so a `~`, a forward slash and a backslash all
    still read the same on Windows. A skill under `skills/<name>` freezes the same way: a whole
    shipped skill directory lands as one directory symlink, so the literal reading is what
    keeps it frozen too, while a user's own unlisted skill directory stays unfrozen. A
    project's own `.claude` files are a separate, unfrozen set: see `is_project_config`.
    """
    if not path:
        return False
    try:
        literal = _literal_resolved(path, cwd)
        resolved = _resolved(path, cwd)
        literal_root = os.path.normcase(os.path.normpath(config_dir()))
        resolved_root = os.path.normcase(os.path.realpath(config_dir()))
    except Exception:
        return False
    for target, root in ((literal, literal_root), (resolved, resolved_root)):
        if not target.startswith(root + os.sep):
            continue
        parts = target[len(root) + 1:].split(os.sep)
        if len(parts) == 1 and parts[0] in CONFIG_FROZEN_FILES:
            return True
        if len(parts) > 1 and parts[0] in CONFIG_FROZEN_DIRS:
            return True
        if len(parts) > 1 and parts[0] == os.path.normcase("skills") and parts[1] in CONFIG_FROZEN_SKILLS:
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


# ------------------------------------------------------------------ three git acts
#
# Each clause below judges the ACT a segment performs, read off its command word (decisions/
# predicate-is-the-act.md), never a substring of the text. `echo git commit`, a `git log`, a
# quoted message and a heredoc body name an act and perform none.
#
# 1. merge-checks (CLAUDE.md `git-wait-for-required-checks`): a merge made outside the merge tool is
#    refused while the head has a check or a workflow run pending or red, or when that read could
#    not run. The merge tool (merge/merge.py) runs its own `gh pr merge` as a subprocess, so no hook
#    sees it; it has already waited. The read below is the tool's own `Host.head_read`, one home.
# 2. cite-by-id (CLAUDE.md `git-cite-by-id`): a commit message or PR body that cites a record by
#    its path is refused. The id is the record's file name without folder or `.md`, the slug
#    lint/check_record_slugs.py measures, or the number the stamp claims at merge.

def git_call_of(segment: str):
    """Return (subcommand, args) when the segment's COMMAND WORD is git, else None.

    Args come from shlex, so a quoted message stays one token. A segment shlex cannot parse
    judges nothing: the same fail-open stance as `segment_tokens`.
    """
    tokens = segment_tokens(segment)
    if not tokens:
        return None
    index = resolve_command(tokens)
    if index is None or basename(tokens[index]) not in ("git", "git.exe"):
        return None
    cursor = _git_subcommand_index(tokens, index)
    if cursor >= len(tokens):
        return None
    return tokens[cursor].lower(), tokens[cursor + 1:]


def gh_call_of(segment: str):
    """Return the tokens after `gh` when the segment's COMMAND WORD is gh, else None."""
    tokens = segment_tokens(segment)
    if not tokens:
        return None
    index = resolve_command(tokens)
    if index is None or basename(tokens[index]) not in ("gh", "gh.exe"):
        return None
    return tokens[index + 1:]


# ---- a merge made outside the merge tool
MERGE_TOOLS = ("mcp__github__merge_pull_request",)
MERGE_VALUE_FLAGS = {"-R", "--repo", "-b", "--body", "-F", "--body-file", "-t", "--subject",
                     "--match-head-commit", "-A", "--author-email"}
# Seconds per `gh` call. The gate makes three calls: 3 * 3 = 9 s, under the 20 s hook timeout in
# settings.json.
MERGE_READ_TIMEOUT = 3
MERGE_TOOL_REL = os.path.join("merge", "merge.py")


def merge_call_of(segment: str):
    """Return (selector, repo) for a `gh pr merge` segment, else None.

    `selector` is the first positional word, '' for the current branch's pull request. `--auto` is
    judged like any merge: GitHub's auto-merge waits only on REQUIRED checks, and a base with none
    merges at once.
    """
    rest = gh_call_of(segment)
    if rest is None or rest[:2] != ["pr", "merge"]:
        return None
    selector, repo = "", ""
    args = rest[2:]
    if "-h" in args or "--help" in args:
        return None   # help merges nothing
    index = 0
    while index < len(args):
        arg = args[index]
        index += 1
        if arg in ("-R", "--repo"):
            repo = args[index] if index < len(args) else ""
            index += 1
        elif arg.startswith("--repo="):
            repo = arg[len("--repo="):]
        elif arg in MERGE_VALUE_FLAGS:
            index += 1
        elif arg.startswith("-"):
            continue
        elif not selector:
            selector = arg
    return selector, repo


_MERGE_MODULE = []


def settings_roots():
    """The clones of claude-settings this guard may read a sibling file from: the one beside its
    own real path (the hooks are symlinks into the clone), then the one the global rules file
    points at."""
    roots = [os.path.dirname(os.path.dirname(os.path.realpath(__file__)))]
    pointer = pointer_checkout()
    if pointer:
        roots.append(pointer)
    return roots


def merge_module():
    """Load merge/merge.py, the merge tool, or return None. Looked up beside this file's real
    path first (the hooks are symlinks into the clone), then in the clone the global rules
    file points at. An unloadable tool is an unknown read, never a pass."""
    if _MERGE_MODULE:
        return _MERGE_MODULE[0]
    for root in settings_roots():
        path = os.path.join(root, MERGE_TOOL_REL)
        if not os.path.isfile(path):
            continue
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("merge_tool", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.SH_TIMEOUT = MERGE_READ_TIMEOUT
            _MERGE_MODULE.append(module)
            return module
        except Exception:
            continue
    return None


def has_workflows(where: str) -> bool:
    """True when the checkout at `where` holds a workflow file, or when that cannot be told: a
    head with nothing reported is then unsettled, never green."""
    try:
        folder = os.path.join(where, ".github", "workflows")
        return any(name.endswith((".yml", ".yaml")) for name in os.listdir(folder))
    except FileNotFoundError:
        return False
    except Exception:
        return True


def merge_gate(selector, repo: str, where: str):
    """Return (verdict, detail) for the head of the named pull request: green, pending, red or
    unknown. One read, no wait, run in `where` so `gh` names the repo the command names."""
    module = merge_module()
    if module is None:
        return "unknown", "the merge tool's check reader could not be loaded"
    where = os.path.normpath(where) if where else ""   # a `cd` target may carry either separator
    host = module.Host(repo=repo or None, cwd=where or None)
    return host.head_read(selector, nothing_is_green=not has_workflows(where))


MERGE_GATE_REASON = (
    "Rule (Git): this head is not settled: %s. A merge waits for every check and workflow run on "
    "the head, required or not, and a read that could not run counts as not settled. "
    "Remedy: run the merge tool, `merge <pr> --confirm`, which waits on every check, then "
    "merges the head it waited on."
)


def merge_gate_reason(verdict: str, detail: str) -> str:
    return MERGE_GATE_REASON % (verdict + (" (" + cap_safe(detail, 160) + ")" if detail else ""))


# ---- a message that cites a record by path
RECORD_DIRS_FILE = os.path.join("lint", "check_record_slugs.py")   # its DIRS is the one list
_RECORD_PATTERN = []


def record_path_pattern():
    """The pattern for a repo-root record path, or None when the record folders cannot be read.

    The folders are the `DIRS` of lint/check_record_slugs.py, read from the file (it runs on
    import, so it cannot be imported). A path counts only at the START of a word: after a space,
    quote, bracket or `=`, with an optional `./`. A URL, `lint/decisions/x.md` and
    `docs/decisions/0001.md` have a `/` or a word before the folder, so they are not repo-root
    record paths and stay allowed.
    """
    if _RECORD_PATTERN:
        return _RECORD_PATTERN[0]
    for root in settings_roots():
        try:
            with open(os.path.join(root, RECORD_DIRS_FILE), encoding="utf-8") as handle:
                text = handle.read(MESSAGE_FILE_MAX)
        except Exception:
            continue
        block = re.search(r"^DIRS\s*=\s*\(([^)]*)\)", text, re.MULTILINE)
        names = re.findall(r'"([\w.-]+)/"', block.group(1)) if block else []
        if names:
            pattern = re.compile(
                r"(?:^|(?<=[\s\"'`(\[<,;=@]))(?:\./)?(?:" + "|".join(map(re.escape, names))
                + r")/[\w.-]+\.md\b")
            _RECORD_PATTERN.append(pattern)
            return pattern
    return None
MESSAGE_VALUE_FLAGS = {"-m", "--message", "-b", "--body"}
MESSAGE_FILE_FLAGS = {"-F", "--file", "--body-file"}
MESSAGE_FILE_MAX = 64 * 1024

CITE_REASON = (
    "Rule (Git): this message cites a record by its path. A record is cited by its id, with a "
    "short gloss, like \"D12, short titles for records\". "
    "Remedy: write the id the record carries, or its slug while the number is unclaimed, "
    "and leave the folder and the file extension out."
)


def message_sources(args):
    """Return (texts, files, stdin) the message flags of a commit or PR call carry.

    `texts` are the inline values, `files` the named files, `stdin` True for `-F -`. Reads
    `-m x`, `--message=x`, `-mx`, a short cluster ending in m (`-am x`), and the long and short
    body and file flags. A flag glued to a value in any other way is a form this does not read.
    """
    texts, files, stdin = [], [], False
    index = 0
    while index < len(args):
        arg = args[index]
        index += 1
        value = None
        is_file = False
        if arg in MESSAGE_VALUE_FLAGS or (re.match(r"^-[A-Za-z]+$", arg) and arg.endswith("m")
                                          and not arg.startswith("--")):
            value = args[index] if index < len(args) else ""
            index += 1
        elif arg in MESSAGE_FILE_FLAGS:
            value = args[index] if index < len(args) else ""
            index += 1
            is_file = True
        elif arg.startswith(("--message=", "--body=")):
            value = arg.split("=", 1)[1]
        elif arg.startswith(("--file=", "--body-file=")):
            value = arg.split("=", 1)[1]
            is_file = True
        elif arg.startswith("-m") and not arg.startswith("--") and len(arg) > 2:
            value = arg[2:]
        if value is None:
            continue
        if not is_file:
            texts.append(value)
        elif value == "-":
            stdin = True
        else:
            files.append(value)
    return texts, files, stdin


UNREAD_MARK = "\0unread:"
UNREAD_REASON = (
    "Rule (Git): the message file could not be read, so the guard cannot tell whether it cites a "
    "record by its path. "
    "Remedy: pass the message inline, or name a file this directory can read."
)


def cited_record_path(segment: str, raw: str, where: str) -> str:
    """Return the first record path a commit message or PR body cites, else ''. A message file
    that cannot be read returns UNREAD_MARK + its name: an unread message is not a clean one.

    Acts: `git commit` and `gh pr create|edit`. A heredoc body belongs to the act only when the
    segment itself carries the `<<` header, so a heredoc that writes a record file never counts.
    """
    call = git_call_of(segment)
    if call is not None:
        if call[0] != "commit":
            return ""
        args = call[1]
    else:
        rest = gh_call_of(segment)
        if rest is None or rest[:1] != ["pr"] or rest[1:2] not in (["create"], ["edit"]):
            return ""
        args = rest[2:]
    pattern = record_path_pattern()
    if pattern is None:
        # An unread folder list is logged, as every unread subject is, and the rule stands down.
        record("Bash", "noted", "subject-unread", "cite-by-id: record folders unread")
        return ""
    texts, files, stdin = message_sources(args)
    for name in files:
        if is_env(name):
            continue   # never opened here: the environment-file rule judges it, and refuses
        try:
            with open(os.path.normpath(_absolute(name, where)), encoding="utf-8",
                      errors="replace") as handle:
                texts.append(handle.read(MESSAGE_FILE_MAX))
        except Exception:
            return UNREAD_MARK + name   # unknown, never a pass
    if "<<" in segment:
        texts.extend(body for _, body in _split_heredocs(raw)[1])
    for text in texts:
        found = pattern.search(norm(text))
        if found:
            return found.group(0)
    return ""


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
#
# A TEST PATH is read from the path's own parts, never from a substring: a basename shape
# (`test_*.py`, `*_test.py`, `*_test.go`, `*.test.{ts,js,tsx,jsx}`, `*.spec.*`, `conftest.py`) or a
# directory part named tests, test, __tests__ or spec. Parts count from the repository root, so a
# clone that lives under a folder named `tests` is not all test files. TEST CONFIG (pytest.ini,
# pyproject.toml, jest.config.*, ...) is a test path for a builder only when the change ADDS a line
# that disables tests (`--deselect`, `testpaths`, `testPathIgnorePatterns`, ...), so a new
# dependency in pyproject.toml stays allowed. For a test-author, test config is always its own.
# `contest.py` and `latest_results.md` match no shape.
# The decisions: predicate-is-the-act, guard-that-cries-wolf-is-spent, builders-cannot-edit-tests.
BUILDER_ROLE = "builder"
AUTHOR_ROLE = "test-author"
TEST_BASENAME = re.compile(
    r"^(?:test_.*\.py|.*_test\.(?:py|go)|.*\.test\.[cm]?[jt]sx?|.*\.spec\..+|conftest\.py"
    r"|jest\.setup\..+|(?:.*[-_]selftest|selftest_.*)\.(?!md$).+"
    # Shell/PowerShell test suites (incident 2026-10-03): `test_*.sh`, `*_test.sh`, `*.test.ps1`,
    # `*.Tests.ps1` (match runs on the lowercased basename, so `.Tests.ps1` arrives as `.tests.ps1`).
    r"|test_.*\.sh|.*_test\.sh|.*\.tests?\.ps1)$")
# SELF-TEST files (`*-selftest.*`, `*_selftest.*`, `selftest_*.*`) are test paths, except .md notes.
# Incident 2026-10-02: Banchi self-test files had the role split inverted (builder edited them).
# `selftestify.py`, `myselftest.py` and a bare `scripts/selftest` match no shape.
# Case matters: `FooTest.java` is a test, `Contest.java` is not.
JAVA_TEST = re.compile(r"^\w*Tests?\.java$")
TEST_DIRS = {"tests", "test", "__tests__", "spec", "testdata", "__snapshots__", "test_support"}
# Dependency lists only a test-author owns. A builder may add a dev dependency.
AUTHOR_BASENAMES = {"requirements-dev.txt"}
TEST_CONFIG = re.compile(
    r"^(?:pytest\.ini|tox\.ini|setup\.cfg|pyproject\.toml|package\.json"
    r"|(?:jest|vitest|playwright|karma)\.conf(?:ig)?\.\w+|vitest\.workspace\.\w+|\.mocharc(?:\.\w+)?)$")
# What disables tests. NAMES are test-runner settings that no lint tool shares, so they count in any
# test config. FLAGS (`--ignore` is also ruff's and flake8's) count only in a test-runner context:
# pytest `addopts`, a `[tool.pytest*]` section, or a line that calls a test runner.
TEST_DISABLE_NAMES = re.compile(
    r"collect_ignore|norecursedirs|testpaths|testPathIgnorePatterns|testIgnore|testMatch"
    r"|testRegex|xfail|passWithNoTests"
    r"|pytest\.(?:mark\.)?skip|unittest\.(?:skip|expectedFailure)|\.skip\(|\bx(?:it|describe)\("
    r"|\bt\.Skip(?:Now)?\(")
TEST_DISABLE_FLAGS = re.compile(
    r"--(?:deselect|ignore|ignore-glob|collect-only)(?![\w-])|-p\s+no:|-[km]\s*['\"]?not\b")
TEST_RUNNER_CONTEXT = re.compile(
    r"addopts|\b(?:pytest|py\.test|jest|vitest|mocha|playwright|karma)\b|go\s+test")


def disables_tests(new_lines, old_lines) -> bool:
    """True when the ADDED lines (those of `new_lines` not in `old_lines`) disable tests."""
    section = ""
    for index, line in enumerate(new_lines):
        header = re.match(r"^\s*\[([^\]]+)\]", line)
        if header:
            section = header.group(1)
        if line in old_lines:
            continue
        if TEST_DISABLE_NAMES.search(line):
            return True
        if TEST_DISABLE_FLAGS.search(line) and (
                "pytest" in section
                or any(TEST_RUNNER_CONTEXT.search(near) for near in new_lines[max(0, index - 3):index + 1])):
            return True
    return False
BUILDER_TEST_REASON = (
    "A builder does not change tests or test config. Report the needed test change in your "
    "report. The orchestrator assigns it to a test-author."
)
AUTHOR_SCOPE_REASON = (
    "A test-author changes only tests and test config. Report the needed product change in your "
    "report. The orchestrator assigns it to a builder."
)


def agent_role(payload) -> str:
    """BUILDER_ROLE or AUTHOR_ROLE for a subagent of that type, else ''."""
    role = payload.get("agent_type")
    if not payload.get("agent_id") or not isinstance(role, str):
        return ""
    role = role.strip().lower()
    return role if role in (BUILDER_ROLE, AUTHOR_ROLE) else ""


def is_test_rel(rel: str) -> bool:
    """True when a repository-relative path is a test path (see the block comment above)."""
    parts = [part for part in norm(rel).split("/") if part]
    return bool(parts) and (
        bool(TEST_BASENAME.match(parts[-1].lower())) or bool(JAVA_TEST.match(parts[-1]))
        or any(p.lower() in TEST_DIRS for p in parts)
    )


def is_test_config_rel(rel: str) -> bool:
    return bool(TEST_CONFIG.match(basename(rel)))


def author_path_ok(rel: str) -> bool:
    """A test-author may change a test path, test config, or a dev dependency list. `package.json`
    and `pyproject.toml` pass here and are read by content in `role_offences`."""
    return is_test_rel(rel) or is_test_config_rel(rel) or basename(rel) in AUTHOR_BASENAMES


def repo_rel(path: str, cwd: str):
    """The path relative to its repository root (the nearest parent holding `.git`), posix, or the
    full path when it sits in no repository. None when it cannot be read."""
    if not path or not isinstance(path, str):
        return None
    try:
        full = norm(_literal_resolved(path, cwd))
    except Exception:
        return None
    parent = os.path.dirname(full)
    while parent and parent != os.path.dirname(parent):
        if os.path.exists(os.path.join(parent, ".git")):
            return full[len(parent):]
        parent = os.path.dirname(parent)
    return full


def role_write_hit(role: str, tool_input, target: str, cwd: str) -> str:
    """The early warning for a write tool call: the target path a role may not change, else ''."""
    rel = repo_rel(target, cwd)
    if rel is None:
        return ""
    if role == AUTHOR_ROLE:
        return "" if author_path_ok(rel) else target
    if is_test_rel(rel):
        return target
    if is_test_config_rel(rel) and any(
            disables_tests(part.splitlines(), []) for part in write_content_parts(tool_input)):
        return target
    return ""


def diff_bases(root: str):
    """The commits this agent's own work is measured against. Empty when git could not answer.

    TWO candidates, and a path counts only if it differs from BOTH:
      - the oldest `HEAD` reflog entry: the commit the worktree was cut from. It survives a new
        branch name (`switch -c b2`), which a branch reflog would not.
      - the merge base of HEAD with the default branch. It moves forward each time main is merged
        or rebased in.
    The work the parent branch handed over differs from the first and not the second only if the
    parent is the default branch; the work main later gained differs from the second and not the
    first. Only the agent's own change differs from both."""
    bases = []
    log = _git(root, "reflog", "show", "--format=%H", "HEAD")
    lines = log.stdout.split() if log is not None and log.returncode == 0 else []
    if lines:
        bases.append(lines[-1])
    default = resolve_default_base(root)
    if default:
        merged = _git(root, "merge-base", "HEAD", default)
        if merged is not None and merged.returncode == 0 and merged.stdout.strip():
            if merged.stdout.strip() not in bases:
                bases.append(merged.stdout.strip())
    return bases


def package_json_author_ok(old: str, new: str) -> bool:
    """A test-author may change `devDependencies`, `jest`, and the test scripts of a manifest, and
    nothing else in it."""
    try:
        before, after = json.loads(old), json.loads(new)
    except Exception:
        return False
    if not isinstance(before, dict) or not isinstance(after, dict):
        return False

    def scripts(manifest):
        found = manifest.get("scripts")
        found = found if isinstance(found, dict) else {}
        return {k: v for k, v in found.items() if not re.match(r"^(?:pre|post)?test", k)}

    for key in set(before) | set(after):
        if key in ("devDependencies", "jest"):
            continue
        if key == "scripts":
            if scripts(before) != scripts(after):
                return False
        elif before.get(key) != after.get(key):
            return False
    return True


def toml_sections(text: str):
    """Split TOML text into {header: body}, the lines before any header under ''."""
    sections, name = {"": []}, ""
    for line in text.splitlines():
        found = re.match(r"^\s*\[\[?([^\]]+)\]\]?\s*$", line)
        if found:
            name = found.group(1).strip()
            sections.setdefault(name, [])
        else:
            sections[name].append(line.strip())
    return {key: "\n".join(body).strip() for key, body in sections.items()}


def pyproject_author_ok(old: str, new: str) -> bool:
    """A test-author may change the `[tool.pytest*]` sections of a project file, and nothing else."""
    before, after = toml_sections(old), toml_sections(new)
    return all(before.get(key) == after.get(key)
               for key in set(before) | set(after) if not key.startswith("tool.pytest"))


def base_text(root: str, base: str, rel: str) -> str:
    """The file's text at the base commit, or '' when it did not exist there."""
    answer = _git(root, "show", base + ":" + norm(rel))
    return answer.stdout if answer is not None and answer.returncode == 0 else ""


def work_text(root: str, rel: str) -> str:
    try:
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except Exception:
        return ""


def disabling_added(root: str, base: str, rel: str) -> bool:
    """True when the lines a change ADDS to one file, against the base, disable tests."""
    return disables_tests(work_text(root, rel).splitlines(), base_text(root, base, rel).splitlines())


def role_offences(root: str, top: str, base: str, role: str):
    """The paths whose change, against ONE base, the role may not make; None when git failed.

    The files are the working tree against the base (committed, staged and unstaged work in one
    read; a change put back to the base's own bytes is no change) plus untracked files. Each path
    is checked as spelled and as resolved through symlinks."""
    tracked = _git(root, "diff", "--name-only", "-z", "--no-renames", base)
    fresh = _git(root, "ls-files", "--others", "--exclude-standard", "-z")
    if tracked is None or fresh is None or tracked.returncode or fresh.returncode:
        return None
    found = []
    for rel in [p for p in tracked.stdout.split("\0") if p] + sorted(
            p for p in fresh.stdout.split("\0") if p):
        # `is_test_rel` is the one place a backslash becomes `/`. A path outside the repository
        # reads `../...`, which no role owns.
        real = os.path.realpath(os.path.join(top, rel))
        names = [rel, os.path.relpath(real, top)]
        if role == AUTHOR_ROLE:
            bad = not all(author_path_ok(n) for n in names)
            if not bad and basename(rel) == "package.json":
                bad = not package_json_author_ok(base_text(root, base, rel), work_text(root, rel))
            if not bad and basename(rel) == "pyproject.toml":
                bad = not pyproject_author_ok(base_text(root, base, rel), work_text(root, rel))
        else:
            bad = any(is_test_rel(n) for n in names) or (
                is_test_config_rel(rel) and disabling_added(root, base, rel))
        if bad:
            found.append(rel)
    return found


def diff_violation(root: str, role: str):
    """Judge the agent's whole result. Returns ('', base) when clean, (the first offending path,
    base) when not, and (None, base) when git could not answer: UNKNOWN, never clear.

    A path offends only if it offends against EVERY base (see `diff_bases`)."""
    bases = diff_bases(root)
    top = _git(root, "rev-parse", "--show-toplevel")
    if not bases or top is None or top.returncode != 0:
        return None, ""
    top = os.path.realpath(top.stdout.strip())
    sets = [role_offences(root, top, base, role) for base in bases]
    if any(s is None for s in sets):
        return None, bases[0]
    both = [rel for rel in sets[0] if all(rel in s for s in sets[1:])]
    return (both[0] if both else ""), bases[0]


def diff_rule(role: str) -> str:
    return "author-diff" if role == AUTHOR_ROLE else "builder-diff"


def diff_refusal(tool: str, role: str, root: str) -> None:
    """Log a role's diff at commit or push for the reviewer. Never blocks: the base can count the
    parent branch's files as the agent's own (decisions/builders-cannot-edit-tests.md)."""
    found, _ = diff_violation(root, role)
    if found is None:
        record(tool, "noted", "role-diff-unread", root)
    elif found:
        record(tool, "noted", diff_rule(role), found)


def judge_stop(payload) -> None:
    """A builder or test-author that stops has its whole diff judged. The stop is never blocked:
    an offence logs as `builder-diff` or `author-diff`. Every path that cannot judge logs too: a
    missing cwd, a cwd that is the main checkout, and a diff that could not be read."""
    role = agent_role(payload)
    if not role:
        return
    where = payload.get("cwd", "")
    if not isinstance(where, str) or not where:
        record("SubagentStop", "noted", "role-diff-nocwd", role)
        return
    if is_worktree(where) is False:
        record("SubagentStop", "noted", "role-diff-main-checkout", where)
        return
    found, _ = diff_violation(where, role)
    if found != "" and payload.get("stop_hook_active"):
        # kept: role_log_case still expects this line on a second stop
        record("SubagentStop", "noted", "role-diff-unresolved", found or "unread")
    elif found is None:
        record("SubagentStop", "noted", "role-diff-unread", where)
    elif found:
        record("SubagentStop", "noted", diff_rule(role), found)


# ------------------------------------------------------------------ two ported shell traps
#
# Ported from pkmnscan's `scripts/guard-shell.py` (behaviour, not code shape). Each clause below is
# self-contained so it merges cleanly beside other edits to this file.

# `gh api` with a field flag and no method. `-f`/`-F` give the request a body and gh then sends POST,
# so a call meant as a GET silently becomes a write (hung past a 120s timeout in Banchi, 2026-09-12).
# A named method (`-X`, `--method`, in any spelling) is the caller saying what they mean. `graphql`
# is a POST by design and takes no method.
GH_FIELD_FLAGS = ("-f", "-F", "--field", "--raw-field")
GH_METHOD_FLAGS = ("-X", "--method")
GH_VALUE_FLAGS = ("-H", "--header", "--hostname", "--jq", "-q", "--template", "-t", "--cache",
                  "--input", "-p", "--preview")


def gh_api_post_hit(segment: str) -> str:
    """Return the matched text when a `gh api` call has a field and no method, else ''."""
    tokens = segment_tokens(segment)
    if not tokens:
        return ""
    at = resolve_command(tokens)
    if at is None or basename(tokens[at]) not in ("gh", "gh.exe"):
        return ""
    # gh's own global flags may sit ahead of `api`: `gh --repo o/r api ...`.
    sub_at = at + 1
    while sub_at < len(tokens) and tokens[sub_at].startswith("-"):
        sub_at += 2 if tokens[sub_at] in ("-R", "--repo") else 1
    if tokens[sub_at:sub_at + 1] != ["api"]:
        return ""
    rest = tokens[sub_at + 1:]
    fielded = False
    endpoint = ""
    index = 0
    while index < len(rest):
        token = rest[index]
        index += 1
        if token in GH_METHOD_FLAGS or token.startswith(("--method=", "-X")):
            return ""
        if token in GH_FIELD_FLAGS:
            fielded = True
            index += 1
        elif token.startswith(("--field=", "--raw-field=")) or (
                token[:2] in ("-f", "-F") and len(token) > 2 and not token.startswith("--")):
            fielded = True
        elif token in GH_VALUE_FLAGS:
            index += 1
        elif not token.startswith("-") and not endpoint:
            endpoint = token
    if not fielded or endpoint.strip("/") == "graphql":
        return ""
    return "gh api " + endpoint + " with a field and no method"


GH_API_METHOD_REASON = (
    "a field flag gives the request a body, and gh sends a body with POST, so with no method named "
    "this is a write and not the read it looks like. "
    "Remedy: put a read's parameters in the query string of the endpoint, or name the method with "
    "--method when the body is what you want."
)


# `ln -s` where the link name is a directory that is already there. ln does not fail: it creates the
# link INSIDE that directory (`images/images`), the original is still in place, and the call exits 0
# (Banchi 2026-08-29, which ended with a real directory renamed away). A real directory always
# descends, whatever flags. A symlink to a directory descends unless `-n`/`-h`, so `-sf` over one is
# the trap and `-sfn` is the answer. Nothing else is refused: a file or a link to a file either
# fails loudly or, with `-f`, is replaced as asked, and neither loses anything silently. A trailing
# slash, `-t`, and `-T` each say the destination is, or is not, a directory, so each is allowed.
# `-sf` over a link to a file is therefore allowed: it replaces the link, which is what `-f` means.
def ln_descends_hit(segment: str, where: str) -> str:
    """Return the matched text when `ln -s` would create a link inside an existing directory."""
    tokens = segment_tokens(segment)
    if not tokens:
        return ""
    at = resolve_command(tokens)
    if at is None or basename(tokens[at]) != "ln":
        return ""
    symbolic = no_deref = False
    operands = []
    index = at + 1
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if token == "--":
            operands.extend(tokens[index:])
            break
        if token in ("-t", "--target-directory", "--no-target-directory") or token.startswith(
                "--target-directory="):
            return ""
        if token.startswith("--"):
            symbolic = symbolic or token == "--symbolic"
            no_deref = no_deref or token == "--no-dereference"
        elif token.startswith("-") and len(token) > 1:
            if "T" in token[1:] or "t" in token[1:]:
                return ""
            symbolic = symbolic or "s" in token[1:]
            no_deref = no_deref or "n" in token[1:] or "h" in token[1:]
        else:
            operands.append(token)
    if not symbolic or len(operands) != 2:
        return ""
    dest = operands[1]
    if dest.endswith(("/", "\\")) or "$" in dest or "*" in dest:
        return ""
    full = _absolute(os.path.expanduser(dest), where or os.getcwd())
    if not os.path.isdir(full):
        return ""
    if os.path.islink(full) and no_deref:
        return ""
    return "ln -s over an existing directory"


LN_DESCENDS_REASON = (
    "the link name is a directory that already exists, so ln does not replace it: it creates the "
    "link inside it and exits 0, leaving the original where it was. "
    "Remedy: add -n beside -f to replace a link to a directory, check that the path is free first "
    "with a test such as [ -e path ], or end the destination with a slash when you mean a link "
    "inside the directory."
)


SPAWN_TOOLS = ("Agent", "Task")
MODEL_FLOOR_REASON = (
    "Sonnet is the floor for every subagent. Start the subagent with model sonnet or opus, "
    "or name no model and let the default apply."
)


def below_the_floor(model) -> bool:
    return "haiku" in str(model).lower()


def judge_shell(tool: str, raw: str, cwd: str, session_id: str = "", role: str = "") -> None:
    POWERSHELL_CALL[0] = tool == "PowerShell"
    stripped = strip_heredoc_bodies(raw)
    cmd = norm(stripped)

    # 0b. A builder or test-author's `git commit` or `git push` is judged on the diff it would send.
    if role:
        for segment in split_segments(stripped):
            for subcommand, _ in git_calls(segment):
                if subcommand in ("commit", "push"):
                    diff_refusal(tool, role, command_root(stripped, cwd))

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
            continue
        # This session's own scratchpad: private by path, so nothing shared can be lost.
        if under_session_scratchpad(root, session_id):
            continue
        # The subject read. An empty subject is a silent pass. An unreadable subject is allowed
        # and logged under its OWN rule, so a reader can tell "I could not confirm this" from
        # "this destroys something", and the Stop hook names it at the end of the turn.
        state = subject_state(subcommand, args, root)
        if state is None:
            # An unforced remove is refused by the VCS itself when the tree is dirty or locked,
            # so a note protects nothing (owner ruling, decisions/guard-that-cries-wolf-is-spent.md).
            if subcommand != "worktree-remove" or worktree_remove_forced(args):
                record(tool, "noted", "subject-unread", matched)
            continue
        if state is True:
            continue
        # A branch's ref and a worktree's own tree are never the running checkout's own lane, so
        # neither earns the worktree-scoped "ask" below: each is judged on its own terms, before
        # that generic split runs.
        if subcommand == "branch-delete":
            refuse(tool, "deny", "shared-tree", BRANCH_DELETE_DENY_REASON, matched)
        if subcommand == "worktree-remove":
            refuse(tool, "deny", "shared-tree", WORKTREE_REMOVE_DENY_REASON, matched)
        if subcommand == "worktree-prune":
            refuse(tool, "ask", "shared-tree", WORKTREE_PRUNE_ASK_REASON, matched)
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
    ends = []
    segments = split_segments(stripped, ends)
    for number, segment in enumerate(segments):
        if not segment.strip():
            continue
        last = number
        while last < len(segments) - 1 and ends[last] == "|":
            last += 1
        matched, mechanism = silent_write_hit(segment, segments[last] if last > number else "")
        if matched:
            reason = (SILENT_WRITE_REDIRECT_REASON if mechanism == "redirect"
                      else SILENT_WRITE_QUIET_REASON)
            refuse(tool, "deny", "silent-write", reason, matched)

    # 1d. A commit message or PR body that cites a record by its path.
    cite_where = command_root(stripped, cwd)
    for segment in split_segments(stripped):
        if not segment.strip():
            continue
        matched = cited_record_path(segment, raw, cite_where)
        if matched.startswith(UNREAD_MARK):
            refuse(tool, "deny", "cite-by-id", UNREAD_REASON, matched[len(UNREAD_MARK):])
        if matched:
            refuse(tool, "deny", "cite-by-id", CITE_REASON, matched)

    # 2. A machine-wide kill. Judged in COMMAND POSITION, from the segment's own tokens, never
    # by the word appearing anywhere in the text. A segment shlex cannot parse fails open:
    # judge nothing rather than guess what it would run.
    previous = None
    for segment in split_segments(stripped):
        if not segment.strip():
            continue
        tokens = segment_tokens(segment)
        if tokens is None:
            previous = None
            continue
        matched = kill_hit(tokens) or kill_fed_by_name(tokens) or kill_fed_by_pipe(tokens, previous)
        previous = tokens
        if matched:
            refuse(tool, "deny", "machine-wide-kill", KILL_REASON, matched)
        matched = foreign_pid_kill(tokens)
        if matched:
            refuse(tool, "deny", "machine-wide-kill", KILL_PID_REASON, matched)

    # 2b. A detached launch: a subshell background job, a nohup/setsid wrapper, disown right
    # after a background job, or a bare trailing background job with no pid captured anywhere
    # in the command. Same decision as rule 2, deny, for the same reason: no pid survives to
    # stop it later.
    matched = detached_launch_hit(stripped)
    if matched:
        refuse(tool, "deny", "detached-launch", DETACHED_LAUNCH_REASON, matched)

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
    matched = narrated_tail_hit(stripped)
    if matched:
        refuse(tool, "deny", "live-stream", NARRATED_TAIL_REASON, matched)

    # 3b. Two traps ported from pkmnscan's `scripts/guard-shell.py`: `gh api` with a field and no
    # method, and `ln -s` onto a directory that is already there. Each reads the segment's own
    # command word, never a substring, and `ln` reads the filesystem rather than the text.
    run_in = _run_dir(stripped, cwd)
    for segment in split_segments(stripped):
        matched = gh_api_post_hit(segment)
        if matched:
            refuse(tool, "deny", "gh-api-method", GH_API_METHOD_REASON, matched)
        matched = ln_descends_hit(segment, run_in)
        if matched:
            refuse(tool, "deny", "ln-over-directory", LN_DESCENDS_REASON, matched)

    # 4. A wide delete denies, and a force push asks.
    for pattern in DESTRUCTIVE_DELETE:
        found = pattern.search(cmd)
        if found:
            refuse(tool, "deny", "destructive-delete", DELETE_REASON, found.group(0))
    for segment in split_segments(cmd):
        matched = cmd_exe_delete_hit(segment)
        if matched:
            refuse(tool, "deny", "destructive-delete", DELETE_REASON, matched)
    for segment in split_segments(stripped):
        for subcommand, args in git_calls(push_text(segment)):
            where, overrides = push_target(segment, stripped, cwd) if subcommand == "push" else ("", {})
            verdict = push_verdict(args, where, overrides) if subcommand == "push" else ""
            if verdict:
                refuse(tool, verdict, "force-push",
                       PUSH_REASON if verdict == "deny" else PUSH_ASK_REASON,
                       "git push " + " ".join(args))

    # 5. The environment file. This layer reads the command BEFORE normalization.
    refusal, logged = env_refusal(stripped)
    if not refusal:
        refusal, logged = env_heredoc_refusal(raw)
    if refusal:
        refuse(tool, "deny", "env-file", refusal + ". " + ENV_ADVICE, logged)

    # 6. A merge outside the merge tool, while the head has a check pending or red, or the read
    # could not run. Judged per segment from the command word, so quoted text never fires it.
    for segment in split_segments(stripped):
        merging = merge_call_of(segment) if segment.strip() else None
        if merging is None:
            continue
        verdict, detail = merge_gate(merging[0], merging[1], cite_where)
        if verdict != "green":
            refuse(tool, "deny", "merge-checks", merge_gate_reason(verdict, detail),
                   "gh pr merge " + merging[0] + " " + verdict)

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
    if payload.get("hook_event_name") == "SubagentStop":
        judge_stop(payload)
        return
    tool = payload.get("tool_name", "") or ""
    tool_input = payload.get("tool_input", {}) or {}
    if not isinstance(tool_input, dict):
        return
    # Read and Grep: no rule judges them, so the guard leaves at once and spends no git call.
    # worktree-home never judged them, the settings deny list owns Read(.env) and Read(.env.*),
    # and a frozen path stays readable (decisions/guard-trims-from-the-audit.md).
    if tool in READ_ONLY_TOOLS:
        return
    cwd = payload.get("cwd", "") or os.getcwd() or ""
    if not isinstance(cwd, str):
        cwd = ""

    # 0. Each subagent stays inside its own worktree. `status` is "none" for the orchestrator
    # (no `agent_id`) and for tools this rule does not judge; "unknown" when the record could
    # not be read at all, which allows (an unreadable state is never a hit); "no-record" for a
    # non-isolated agent, which allows everything; "home" once the agent's worktree is known,
    # from this call or an earlier one. Read/Grep are never checked here: the agent must still be
    # able to read and report (decisions/an-agent-outside-its-home-tree-must-stop.md).
    home_status, home, home_primary = agent_worktree_home(payload, cwd)
    if home_status == "home":
        if tool in SHELL_TOOLS:
            if path_is_inside(cwd, home) is False:
                refuse(tool, "deny", "worktree-home", WORKTREE_HOME_REASON,
                       "shell cwd outside recorded agent home")
        elif tool in WRITE_TOOLS:
            write_target = (
                tool_input.get("file_path", "")
                or tool_input.get("path", "")
                or tool_input.get("notebook_path", "")
                or ""
            )
            if isinstance(write_target, str) and write_target and home_primary:
                # A relative `file_path` resolves against the CALLER's cwd, the payload's own
                # `cwd`, never the guard process's. `_resolved` (already used by `is_frozen` and
                # `is_project_config` for the same reason) joins it before either check.
                try:
                    resolved_target = _resolved(write_target, cwd)
                except Exception:
                    resolved_target = write_target
                if (path_is_inside(resolved_target, home_primary) is True
                        and path_is_inside(resolved_target, home) is False):
                    refuse(tool, "deny", "worktree-home", WORKTREE_HOME_REASON,
                           "write target outside recorded agent home")

    # 9. The subagent model floor. A spawn that names a Haiku model is denied. The reason names no
    # model; the log holds what the call asked for.
    if tool in SPAWN_TOOLS and below_the_floor(tool_input.get("model")):
        refuse(tool, "deny", "subagent-model-floor", MODEL_FLOOR_REASON, str(tool_input.get("model")))

    # A merge through the MCP tool is judged by the same check gate as `gh pr merge`.
    if tool in MERGE_TOOLS:
        owner, name, number = (tool_input.get(k) for k in ("owner", "repo", "pullNumber"))
        repo = owner + "/" + name if isinstance(owner, str) and isinstance(name, str) else ""
        verdict, detail = merge_gate("" if number is None else str(number), repo, cwd)
        if verdict != "green":
            refuse(tool, "deny", "merge-checks", merge_gate_reason(verdict, detail),
                   "merge tool " + verdict)

    if tool in SHELL_TOOLS:
        command = tool_input.get("command", "") or ""
        if isinstance(command, str) and command.strip():
            judge_shell(tool, command, cwd, session_id_of(payload), agent_role(payload))
        return

    if tool not in WRITE_TOOLS:
        return

    target = (
        tool_input.get("file_path", "")
        or tool_input.get("path", "")
        or tool_input.get("notebook_path", "")
        or ""
    )
    if not isinstance(target, str) or not target:
        return

    # 0b. The early warning for a builder or test-author write (see BUILDER_ROLE). A read is allowed.
    role = agent_role(payload)
    if role and tool in WRITE_TOOLS:
        matched = role_write_hit(role, tool_input, target, cwd)
        if matched:
            refuse(tool, "deny", "test-author-scope" if role == AUTHOR_ROLE else "builder-test-edit",
                   AUTHOR_SCOPE_REASON if role == AUTHOR_ROLE else BUILDER_TEST_REASON, matched)

    # 5. The environment file. Every writing tool is refused. A read is not judged here: the
    # settings deny list blocks Read(.env) and Read(.env.*). The reason names no file, and the log
    # holds the path the tool asked for.
    if is_env(target):
        refuse(tool, "deny", "env-file", ENV_TOOL_REASON + ". " + ENV_ADVICE, target)

    # 7. A frozen path. Only a writing tool reaches here, so a frozen path stays readable.
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
    except Exception as exc:
        # Fail open, but never silently: a crash that hides a rule must show in the log.
        record(str(payload.get("tool_name", "")), "crash", "guard-crash",
               cap_safe(type(exc).__name__ + ": " + str(exc), 200))
        sys.exit(0)  # fail open on a guard defect
    sys.exit(0)


if __name__ == "__main__":
    main()
