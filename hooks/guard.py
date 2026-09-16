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

  1 shared-tree        a command that throws away a working tree
  2 machine-wide-kill  a kill by name or by pattern
  3 live-stream        a command that follows a stream and never ends on its own
  3 waiter             a shell segment whose command word is a sleep-and-poll
  4 force-push         a rewrite of a published branch
    destructive-delete a recursive delete at a root, a home or a glob
  5 env-file           any read or write of an environment file
  6 merge-main         a pull request merged into main. Allowed, and logged (Decision 8).
  7 frozen-path        a write to the settings, the hooks or the global CLAUDE.md, under
                       `${CLAUDE_CONFIG_DIR:-$HOME/.claude}`. Always denied.

A project's own `.claude/settings.json`, `.claude/settings.local.json`, and
`.claude/hooks/*` are NOT frozen (Decision 7). They are allowed, and the guard appends
one log line with decision `noted` and rule `config-edit`. This is the one place the
guard logs an ALLOW rather than a refusal, so a person can see the edit at turn end.
Nothing is printed for a noted edit; the config-report Stop hook is what surfaces it to
the transcript.

Decision 8 ("Merge into main: allow and report") makes `merge-main` the same shape: a
merge into main is allowed, never asked, and the guard logs `noted`/`merge-main` when
the base is `main` or unreadable, and always for the MCP merge tool, which carries no
base at all. CLAUDE.md's "merged only when I name the act" stays the model's rule; the
guard cannot read chat, so a prompt here would only repeat a decision the owner already
made in the conversation.

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
import shutil
import subprocess
import sys
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


# One shell segment of the command. Each segment is judged on its own, so an allowed first half
# licenses nothing in the second half.
SEGMENT_SPLIT = re.compile(r"\|\||&&|[;|\n]")


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

# A subcommand that discards the working tree on its own.
TREE_DISCARD = {"stash", "reset", "restore"}

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


def shared_tree_hit(segment: str) -> str:
    """Return the matched text when one segment discards a working tree, else ''."""
    for subcommand, args in git_calls(segment):
        if subcommand in TREE_DISCARD:
            return ("git " + subcommand + " " + " ".join(args)).strip()
        if subcommand == "clean" and clean_deletes_files(args):
            return ("git clean " + " ".join(args)).strip()
        if subcommand == "checkout":
            named = checkout_names_a_path(args)
            if named:
                return "git checkout " + named
    return ""


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


def command_root(cmd: str, shell_cwd: str) -> str:
    """Return the directory the command acts on."""
    where = None
    match = GIT_C_RE.search(cmd)
    if match:
        where = match.group(2)
    else:
        changes = list(CD_RE.finditer(cmd))
        if changes:
            where = changes[-1].group(2).strip()
    if where:
        where = os.path.expandvars(os.path.expanduser(where))
        if re.match(r"^/[a-zA-Z]/", where):  # Git Bash `/c/Users/...` to `C:/Users/...`
            where = where[1].upper() + ":" + where[2:]
        # Python 3.13 and later on Windows: a bare `/x` is not absolute, so test the converted
        # form, and only then join a relative `cd` onto the cwd.
        if not os.path.isabs(where) and shell_cwd:
            where = os.path.join(shell_cwd, where)
    return where or shell_cwd or ""


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


TREE_DENY_REASON = (
    "Rule (shared trees): this command throws away work in a checkout that other "
    "sessions and the owner share, and no step puts it back. "
    "Remedy: copy the file to a name ending in .bak and change the copy. "
    "Make a commit for work you must set aside. "
    "Run the command in a worktree of your own when the tree must change."
)
TREE_ASK_REASON = (
    "Rule (shared trees): this command throws away work in a working tree. "
    "This checkout is a worktree, so the loss is limited to this lane. "
    "The click in this prompt is the grant."
)


# ------------------------------------------------------------------ a machine-wide kill
#
# CLAUDE.md: "Never kill a process you did not start. Treat `pkill -f` and `lsof -t` as
# machine-wide." A kill BY NAME or BY PATTERN reaches every matching process on the machine,
# including another agent's dev server, another person's worker, and the editor itself.
#
# A KILL BY PID IS NOT ON THIS LIST, deliberately. A PID names one process. `taskkill /PID` and
# `Stop-Process -Id` are the same act under the other shell, and neither is refused.
MACHINE_WIDE_KILL = (
    re.compile(r"\bpkill\b"),
    re.compile(r"\bkillall\b"),
    re.compile(r"(?i)\btaskkill\b(?=[^\n;|&]*\s[/-]im\b)"),
    re.compile(r"(?i)\bstop-process\b(?=[^\n;|&]*\s-n(?:ame)?\b)"),
)

# The flag-aware form, ported from job-cost-reporting. It catches `lsof -t` and `lsof -ti`, which
# feed a kill list, and leaves `lsof -i :3000` alone, because asking which port is busy kills
# nothing.
PROC_TOOLS = {"pkill", "lsof"}


def machine_wide_process_call(segment: str) -> str:
    """Return the matched text when a call reaches processes by pattern."""
    tokens = segment.split()
    for index, token in enumerate(tokens):
        tool = basename(token)
        if tool not in PROC_TOOLS:
            continue
        for arg in tokens[index + 1:]:
            if not arg.startswith("-"):
                continue
            if tool == "pkill" and (arg == "--full" or
                                    (not arg.startswith("--") and "f" in arg)):
                return token + " " + arg
            if tool == "lsof" and not arg.startswith("--") and "t" in arg:
                return token + " " + arg
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
# THE COMMAND WORD is the segment's first token, so an unrelated later argument never matches. The
# Windows `timeout /t` form is the one case where the wait is the SECOND word, so it is read apart:
# `timeout /t 5` waits, `timeout /help` (no `/t`) does not.
WAITER_COMMANDS = ("sleep", "start-sleep")


def waiter_hit(segment: str) -> str:
    """Return the matched text when one segment's command word is a sleep-and-poll, else ''."""
    tokens = segment.split()
    if not tokens:
        return ""
    word = basename(tokens[0])
    if word in WAITER_COMMANDS:
        return tokens[0]
    if word == "timeout" and any(t.lower() == "/t" for t in tokens[1:]):
        return tokens[0] + " /t"
    return ""


WAITER_REASON = (
    "a pause between polls turns waiting into a loop of turns that each print a word. "
    "Remedy: run the long command in the background and wait for its completion notice, "
    "or use a tool that waits once, such as gh pr checks --watch or gh run watch "
    "--exit-status. For a server warm-up, use a readiness check such as curl --retry."
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
# A leading `VAR=value` assignment, which is not the segment's command.
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


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
CONFIG_FROZEN_DIRS = (
    os.path.normcase("hooks"),
    os.path.normcase("lint"),
    os.path.normcase("agents"),
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
    for segment in SEGMENT_SPLIT.split(cmd):
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


# ------------------------------------------------------------------ the log
#
# One line for each refusal, and nothing for an allow. An allow is the ordinary case, so logging it
# would bury the refusals. A failure to write the log never changes the decision.
def record(tool: str, decision: str, rule: str, matched: str) -> None:
    try:
        folder = config_dir()
        os.makedirs(folder, exist_ok=True)
        line = "\t".join([
            datetime.now().isoformat(timespec="seconds"),
            tool or "",
            decision,
            rule,
            re.sub(r"\s+", " ", matched or "")[:120],
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


def judge_shell(tool: str, raw: str, cwd: str) -> None:
    stripped = strip_heredoc_bodies(raw)
    cmd = norm(stripped)

    # 1. Shared trees.
    for segment in SEGMENT_SPLIT.split(stripped):
        if not segment.strip():
            continue
        matched = shared_tree_hit(segment)
        if not matched:
            continue
        worktree = is_worktree(command_root(stripped, cwd))
        if worktree is True:
            refuse(tool, "ask", "shared-tree", TREE_ASK_REASON, matched)
        refuse(tool, "deny", "shared-tree", TREE_DENY_REASON, matched)

    # 2. A machine-wide kill.
    for pattern in MACHINE_WIDE_KILL:
        found = pattern.search(cmd)
        if found:
            refuse(tool, "deny", "machine-wide-kill", KILL_REASON, found.group(0))
    for segment in SEGMENT_SPLIT.split(stripped):
        matched = machine_wide_process_call(segment)
        if matched:
            refuse(tool, "deny", "machine-wide-kill", KILL_REASON, matched)

    # 3. A live stream that never ends, or a waiter loop (Rule 9).
    for segment in SEGMENT_SPLIT.split(stripped):
        matched = live_stream_hit(segment)
        if matched:
            refuse(tool, "deny", "live-stream", LIVE_STREAM_REASON, matched)
        matched = waiter_hit(segment)
        if matched:
            refuse(tool, "deny", "waiter", WAITER_REASON, matched)

    # 4. A wide delete denies, and a force push asks.
    for pattern in DESTRUCTIVE_DELETE:
        found = pattern.search(cmd)
        if found:
            refuse(tool, "deny", "destructive-delete", DELETE_REASON, found.group(0))
    for segment in SEGMENT_SPLIT.split(stripped):
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
            judge_shell(tool, command, cwd)
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
