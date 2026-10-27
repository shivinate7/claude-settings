"""The guard's kill family: a machine-wide kill, a detached launch and the Playwright browser cache.

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import itertools
import os
import re
import subprocess
try:
    import _nowindow  # the one home of a no-window child start; a flat hooks/ file, not a guard-set member
except ImportError:  # install-hooks-whole: the guard set lands whole, the helper beside it a moment later; the guard still judges
    _nowindow = subprocess
import sys
try:
    from proc_env import holds_session_tag  # the one home of the exec-environment read (hooks/proc_env.py)
except ImportError:  # same fallback as _nowindow above: no read, so a PPID-1 pid stays foreign
    def holds_session_tag(pid, session_id):
        return False

from guard_core import (
    QUOTE_MARKS,
    ASSIGNMENT, CMD_EXE_NAMES, ENV_PATTERN_COMMANDS, PLAYWRIGHT_PS_SHELLS,
    POWERSHELL_CALL, PowerShellScript, SILENT_WRITE_REDIRECT, _pwsh_script, _skip_assignments_and_keywords,
    _split_heredocs, _strip_heredoc_bodies_unconditionally, basename, inline_script,
    resolve_command, segment_tokens, split_segments,
)
from guard_env import _substitutions


# ------------------------------------------------------------------ a machine-wide kill
#
# Rule `shared-trees-no-machine-wide-kill`: never kill a process you did not start. A kill BY NAME
# or BY PATTERN reaches every matching process on the machine, including another agent's dev
# server, another person's agent, and the editor itself.
#
# A KILL BY PID NAMES ONE PROCESS, so the name rules below pass it. It is judged by OWNERSHIP
# instead: see `foreign_pid_kill`. `taskkill /PID` and `Stop-Process -Id` are the same act under
# the other shell, and neither is refused (unmeasured there: no `ps`).
#
# THE PREDICATE IS THE ACT, NOT THE TOOL OR THE SPELLING. The earlier version was four bare
# regexes over the whole command text, so the NAME tripped it wherever it sat: inside a quoted
# grep pattern, on the far side of a pipe, in a comment. MEASURED: the owner's
# `grep -n -i "...|make reap|pkill..." CLAUDE.md` was refused, though the command calls grep, not
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
    pass. `lsof` refuses only with a `-t`/`-ti` flag, which feeds a kill list; `lsof -i :3000`
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
    # By port, the same act as `lsof -t | xargs kill`: `fuser -k` (alone or in a cluster, `-kn`) and
    # `kill-port`, run directly or through a package runner.
    if tool == "fuser" and any(
            arg == "--kill" or (arg.startswith("-") and not arg.startswith("--") and "k" in arg)
            for arg in rest):
        return word
    if tool == "kill-port" or (
            (tool in ("npx", "pnpx", "bunx") or (tool in ("npm", "pnpm", "yarn")
                                                 and ("exec" in rest or "dlx" in rest)))
            and any(arg.split("@")[0] == "kill-port" for arg in rest)):
        return word + " kill-port"
    return ""


KILL_PID_RE = re.compile(r"^-?[0-9]+$")
ROOT_PID_RE = re.compile(r"[0-9]+")
PID_LISTERS = {"pgrep", "pidof"}   # a kill fed by these names its target by pattern
# `lsof` counts only with a `-t` flag, which makes it a pid list; `lsof -i :3000` lists and no more.
PID_SUBSTITUTION_RE = re.compile(
    r"(?:\$\(|`)\s*(?:command\s+)?(?:\S*/)?(pgrep|pidof|lsof(?=[^)`]*\s-[A-Za-z]*t))\b")
KILL_SIGNAL_ARG_FLAGS = {"-s", "-n"}   # these two take the next token as a signal


def _ps_ppid(pid: int):
    """Parent pid of `pid`; 0 when no such process; None when `ps` could not answer.

    No such process is exit 1 with no output at all. Any other failure is unknown, not death.
    """
    try:
        answer = _nowindow.run(["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True,
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
            name = _nowindow.run(["ps", "-o", "comm=", "-p", str(parent)], capture_output=True,
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


AGENT_WORKTREE_RE = re.compile(r"/\.claude/worktrees/agent-([A-Za-z0-9_-]{1,64})(?:/|$)")


def _pid_cwd(pid: int):
    """Current directory of `pid`, or None when it could not be read."""
    try:
        if sys.platform.startswith("linux"):
            return os.readlink("/proc/%d/cwd" % pid)
        answer = _nowindow.run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
                                capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    for line in answer.stdout.splitlines():
        if line.startswith("n"):
            return line[1:]
    return None


def in_own_agent_worktree(pid: int, transcript: str) -> bool:
    """True when `pid`'s cwd is inside `.claude/worktrees/agent-<id>` and this session's
    `subagents/` folder holds `agent-<id>.jsonl`, and its parent is init (PPID 1). The folder is the transcript path minus `.jsonl`.
    Any unreadable part reads False (foreign). Decision a-kill-by-pid-needs-an-owned-pid."""
    if not transcript.endswith(".jsonl") or _ps_ppid(pid) != 1:
        return False   # left-behind only: a pid whose parent is alive stays foreign
    cwd = _pid_cwd(pid)
    found = AGENT_WORKTREE_RE.search((cwd or "").replace("\\", "/"))
    return bool(found) and os.path.isfile(
        os.path.join(transcript[:-len(".jsonl")], "subagents", "agent-%s.jsonl" % found.group(1)))


def _kill_pids(tokens):
    """The numeric pid arguments of a `kill` segment, as text, in order. Nothing for any other
    command, or for `kill -l`. Signal flags and their values are skipped."""
    index = resolve_command(tokens)
    if index is None or basename(tokens[index]) != "kill":
        return
    rest = tokens[index + 1:]
    if any(arg == "-l" or arg == "-L" for arg in rest):
        return
    skip = after_dashes = signal_given = False
    for arg in rest:
        if skip:
            skip = False
            continue
        # A flag after the signal that reads `-1` is pid -1 (every process): `kill -9 -1`.
        if not after_dashes and arg.startswith("-") and arg != "-" and not (
                signal_given and arg == "-1"):
            after_dashes = arg == "--"
            skip = arg in KILL_SIGNAL_ARG_FLAGS
            signal_given = signal_given or not after_dashes
            continue
        if KILL_PID_RE.match(arg):
            yield arg


def kills_group_pid(tokens) -> bool:
    """True when a `kill` segment names pid 0, 1 or -1. No override lifts it."""
    return any(int(arg) in (0, 1, -1) for arg in _kill_pids(tokens))   # a whole group, init, every process


def foreign_pid_kill(tokens, transcript: str = "", session_id: str = "") -> str:
    """Return the first numeric pid a `kill` segment names that this session did not start.

    Only literal numbers are judged. `$!`, `$PID`, `%1` and `$(...)` cannot be read here, and
    the remedy tells the agent to kill by `$!`. When the session root or `ps` cannot be read, the
    answer is "" (unknown, so allowed), never a guess. A PPID-1 pid is also owned when its exec
    environment holds `CLAUDE_CODE_SESSION_ID=<session_id>` exactly (`proc_env.holds_session_tag`),
    read only after the walk says foreign, so an allowed kill costs nothing new. ponytail: a pid
    reused since launch reads as foreign; a forked shell stub carries no tag, so a left-behind
    shell reads foreign too; stop either through the harness.
    """
    root = None
    for arg in _kill_pids(tokens):
        number = int(arg)
        if number in (0, 1, -1):   # a whole group, init, or every process: judged with no root
            return arg
        if root is None:
            root = session_root_pid()
        if not root:
            return ""
        if in_own_agent_worktree(abs(number), transcript):
            continue
        if pid_is_owned(abs(number) if number < -1 else number, root) is False:
            if _ps_ppid(abs(number)) == 1 and holds_session_tag(abs(number), session_id):
                continue
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
# MEASURED on macOS: a background job in a subshell,
# `(python3 -m http.server 8000 >/tmp/http_server_wtweb.log 2>&1 &)`, exits the subshell at
# once. Pid 1 adopts the server, the harness never tracks it, and no pid is kept. Rule 2 above
# refuses `pkill -f` and `lsof -t`, and its remedy needs a pid this session started, so the
# server stays up. This rule refuses the LAUNCH, before a session reaches a machine-wide kill.
#
# THE SAME "resolve, not match" STANCE as rule 2 (see the comment above `KILL_COMMAND_WORDS`):
# every check below reads a segment's OWN tokens, from `segment_tokens`, quote-aware and
# heredoc-safe (the caller already ran `strip_heredoc_bodies`), never the raw text. A quoted
# `"nohup foo &"` passed to `echo` or `grep` is one token to shlex, never equal to the bare
# tokens `nohup`, `&`, or `disown` this file checks for, so it never fires here either.
#
# `nohup`/`setsid` MUST be read BEFORE `resolve_command` unwraps them: `nohup pkill foo` names a
# real kill in command position, and rule 2 above already refuses that on its own, unwrapped
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
    `disown` has no use but to detach a job, so it refuses in command position anywhere."""
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

    `Start-Job` always refuses: it hands the work to a job object in a separate PowerShell
    process, and this session never holds a pid for it at all. `Start-Process` refuses only
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

    The `&` must come AFTER the command word: a leading `&` is PowerShell's call operator,
    never a background job. Every heredoc body is dropped first: an `&` there is not a job.
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


# THE PLAYWRIGHT BROWSER CACHE. A scratch PLAYWRIGHT_BROWSERS_PATH hides the real causes of a
# missing chromium_headless_shell: a stale `__dirlock` from a half-stopped install, and an install
# that hangs while it unpacks under Node 26.11 with Playwright 1.58. See the record playwright-browsers-path.
# A set is an inline `VAR=v`, `env VAR=v`, `export VAR=v`, `cmd /c set VAR=v`, any of these inside
# `bash -c` or `eval`, a write of the assignment into a file, or a PowerShell `$env:VAR = v`,
# `Set-Item env:VAR` or `SetEnvironmentVariable`. A read, a grep, and `unset` set nothing. The name
# is folded to upper case in every form. Shell words come from `segment_tokens`, assignments from
# `ASSIGNMENT`, and the file write from `_VAR_TOKEN`: no parser of its own.
# KNOWN LIMITS: `cross-env` is refused. Not covered: `timeout N env`, `setx`, a PowerShell block,
# a `<<<` here-string, a CI yaml `env:` key, and `node -e` or `python -c`.
PLAYWRIGHT_VAR = "PLAYWRIGHT_BROWSERS_PATH"
ASSIGNING_BUILTINS = ("export", "declare", "typeset", "readonly", "local", "set")


# Search tools. Local here, not in the shared ENV_PATTERN_COMMANDS.
PLAYWRIGHT_PS_READERS = ("select-string", "sls")
PLAYWRIGHT_PS_SET = re.compile(
    r"\$\{?env:" + PLAYWRIGHT_VAR + r"\}?\s*[-+*/]?=(?!=)"
    r"|^\s*(?:set-item|si|new-item|ni|set-content|sc)\b[^;|]*\benv:\\?" + PLAYWRIGHT_VAR + r"\b"
    r"|SetEnvironmentVariable\(\s*['\"]?" + PLAYWRIGHT_VAR + r"\b", re.I)


# A shell profile or `.envrc`: a write there sets the variable for every later shell.
PLAYWRIGHT_PROFILE = re.compile(r"\.(?:zshrc|zshenv|zlogin|bashrc|profile|zprofile|bash_profile|bash_login|envrc)\b")
# SILENT_WRITE_REDIRECT (the null-device redirects) leaves `N>&N` alone, because that rule wants
# a duplicate to count as output. Here a duplicate is no file target, so it is dropped as well.
_FD_DUP = re.compile(r"\d*>&\d+")
_PRINTF_DIRECTIVE = re.compile(r"%%|%[-+ #0-9.]*[a-zA-Z]|\\[nrtabfv\\]")
_REDIRECT_TO_PROFILE = re.compile(r">+\|?\s*[^\s|;&]*" + PLAYWRIGHT_PROFILE.pattern)


# A watched set of variable names: (names, fold_case). Both rules fold the name to upper case,
# because the environment is case-blind on Windows. The git rule passes a bare lower-case
# assignment with no command after it, `git_dir=$(...)`, as the plain shell variable it is.
# PowerShell's `env:` is read with re.I below.
PLAYWRIGHT_WATCH = ((PLAYWRIGHT_VAR,), True)
GIT_ENV_WATCH = (("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"), True)
_ASSIGN_NAME = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\+?=")


def _assigned_var(token: str, watch) -> str:
    """The watched name a `VAR=value` (or `VAR+=value`) token assigns, else ''."""
    found = _ASSIGN_NAME.match(token)
    name = (found.group(1).upper() if watch[1] else found.group(1)) if found else ""
    return name if name in watch[0] else ""


_PS_CMDLETS = ("set-item", "si", "new-item", "ni", "set-content", "sc")
_PS_UNSET = ("$null", "")


# A script block or a group that runs its body: `{`, `&{`, `.{`, `(`, `$(`, `@(`.
_PS_BLOCK_OPEN = re.compile(r"[&.]?\{|[&.$@]?\(")
_PS_GLUED_BRACE = re.compile(r"(?<!\$)\{")


def _open_script_blocks(tokens):
    """Split each glued script block or paren group (`{$env:X=1}`, `&{...}`, `($env:X=1)`) into
    its opener and its body, after any token: `if (...) {...}`, `ForEach-Object {...}`,
    `try {...}`. A token that starts inside quotes (`'{$env:X=1}'`, `tokens.quoted`) is text and
    stays whole. Known ceiling: an unquoted block passed as a plain argument (`Write-Host {...}`)
    is read as code too, a false deny, the safe side."""
    quoted = getattr(tokens, "quoted", ())
    out = []
    for i, tok in enumerate(tokens):
        if i in quoted:
            out.append(tok)
            continue
        while (opens := _PS_BLOCK_OPEN.match(tok)) and len(tok) > opens.end():
            out.append(opens.group(0)[-1])
            tok = tok[opens.end():].rstrip("})")
        # A `{` glued to its word (`%{`, `){`, `try{`, `$sb={`) opens a block too. `${` is a
        # braced variable name, so it stays whole.
        head, *rest = _PS_GLUED_BRACE.split(tok) if len(tok) > 1 else [tok]
        out.append(head)
        for part in rest:
            out.append("{")
            if part.rstrip("})"):   # a `{` that ends its token leaves no empty piece behind
                out.append(part.rstrip("})"))
    return out


def _ps_env_set(tokens, watch) -> str:
    """Return the matched text when a PowerShell statement sets a watched name in the process
    environment, else ''. Reads the statement's own tokens, so a name inside quoted text, which
    is one token, never fires. A statement starts at the first token, or after `{`, `(` or `&`.
    `$env:X = $null` and an empty value unset the name and pass."""
    alt = "|".join(map(re.escape, watch[0]))
    tokens = _open_script_blocks(tokens)
    start = _skip_assignments_and_keywords(tokens)
    for i, tok in enumerate(tokens):
        if i != start and not (i and (tokens[i - 1] in ("{", "(", "&") or tokens[i - 1].endswith("{"))):
            continue
        found = re.fullmatch(r"\$\{?env:(" + alt + r")\}?(?:([-+*/]?=)(.*))?", tok, re.I | re.S)
        if found:
            if found.group(2):
                value = found.group(3) or "".join(tokens[i + 1:i + 2])
            elif re.fullmatch(r"[-+*/]?=", "".join(tokens[i + 1:i + 2])):
                value = "".join(tokens[i + 2:i + 3])
            else:
                continue
            if value not in _PS_UNSET:
                return "$env:" + found.group(1)
            continue
        if basename(tok).lower() in _PS_CMDLETS:
            rest = tokens[i + 1:]
            named = [m.group(1) for t in rest if (m := re.fullmatch(
                r"(?:-\w+:)?env:\\?(" + alt + ")", t, re.I))]
            if named and rest[-1] not in _PS_UNSET:
                return tok + " env:" + named[0]
        found = re.search(r"SetEnvironmentVariable\s*\(\s*(" + alt + r")\s*,(.*)",
                          " ".join(tokens[i:i + 4]), re.I)
        if found and not re.match(r"\s*(?:\$null\b|,|\)|$)", found.group(2)):
            return "SetEnvironmentVariable " + found.group(1)
    return ""




# Decision playwright-install-once (one Playwright browser install, Node 22 cli.js form, never a
# agent). `install` below is "main" or "sub" in install mode: the same walk then runs, with the
# install test as its leaf in place of the PLAYWRIGHT_BROWSERS_PATH tests.
_PW_RUNNERS = ("npx", "pnpm", "yarn", "bunx", "bun", "npm")
_PW_NAMES = ("playwright", "playwright-core", "@playwright/test")
_PW_VALUE_FLAGS = ("-C", "--prefix", "--cwd", "--dir", "-F", "--filter", "-w", "--workspace")
_PW_NPX_VALUE_FLAGS = ("--prefix", "-w", "--workspace")   # npm's own
_PW_CLIS = ("playwright/cli.js", "playwright-core/cli.js")
_PW_NODE22_CLIS = tuple("node_modules/" + c for c in _PW_CLIS)


def _pw_name(token) -> bool:
    """True when a token names the Playwright CLI: a bin path, `name@version`, or its cli.js."""
    name = ("@" + token[1:].split("@")[0]) if token.startswith("@") else token.split("@")[0]
    return name in _PW_NAMES or (not name.startswith("@") and basename(name) in _PW_NAMES) or (
        token.endswith(tuple("/" + c for c in _PW_CLIS)))


def _playwright_install_hit(word, rest, who) -> str:
    """Return the install text when the call installs Playwright browsers and `who` may not.

    A call is an install when a Playwright name is followed at once by the word `install`. Only a
    runner, node, or the Playwright CLI itself counts as the call, so `echo` of the text is none.
    """
    if not (word in _PW_RUNNERS or word == "node" or word.startswith("node@") or _pw_name(word)):
        return ""
    toks = [word] + rest
    # A name right after a folder or filter flag is that flag's value (`pnpm -C playwright
    # install`), so it is skipped. Under npx only npm's own value flags count. Known ceiling: an
    # unlisted folder flag is read as a command and can only cause a false deny, the safe direction.
    at = next((i for i, t in enumerate(toks) if _pw_name(t) and toks[i + 1:i + 2] == ["install"]
               and (i == 0 or toks[i - 1] not in (
                   _PW_NPX_VALUE_FLAGS if word == "npx" else _PW_VALUE_FLAGS))), None)
    if at is None:
        return ""
    allowed = toks[at].endswith(_PW_NODE22_CLIS) and toks[:1] == ["npx"] and toks[1:at] in (
        ["node@22"], ["-y", "node@22"], ["--yes", "node@22"])
    return "" if allowed and who == "main" else "playwright install"


def _playwright_tokens_hit(tokens, depth=0, install=None, watch=PLAYWRIGHT_WATCH) -> str:
    tokens = [t for t in ([tokens[0].lstrip("(")] + tokens[1:] if tokens else []) if t]
    if not tokens or depth > 3:
        return ""
    at = resolve_command(tokens)
    for t in ([] if install else tokens[:len(tokens) if at is None else at]):
        name = _assigned_var(t, watch)
        # a lower-case name is a plain shell variable unless a command follows it as a prefix,
        # and a substitution (`git_dir=$(...)`, split by shlex at its spaces) is no prefix
        if name and (watch is PLAYWRIGHT_WATCH or t.startswith(name)
                     or (at is not None and "$(" not in t and "`" not in t)):
            return name + " assignment"
    if at is None:
        return ""
    word, rest = basename(tokens[at]).lower(), tokens[at + 1:]
    if install:
        hit = _playwright_install_hit(word, rest, install)
        if hit:
            return hit
    elif watch is GIT_ENV_WATCH and word == "export" and any(
            re.fullmatch(r"-[a-zA-Z]*n[a-zA-Z]*", t) for t in itertools.takewhile(
                lambda t: t.startswith("-") and t != "--", rest)):
        # `export -n NAME` takes the name OUT of the environment. Only a leading option counts:
        # export stops reading options at its first name, so `export GIT_DIR=x -n` still sets.
        pass
    elif word in ASSIGNING_BUILTINS and any(_assigned_var(t, watch) for t in rest):
        return word + " " + next(_assigned_var(t, watch) for t in rest if _assigned_var(t, watch))
    elif watch is GIT_ENV_WATCH and word in ("setx", "setx.exe") and any(
            t.upper() in watch[0] for t in rest):
        return word + " " + next(t for t in rest if t.upper() in watch[0])   # a persistent set
    elif watch is GIT_ENV_WATCH and (word == "export" or (word in ("declare", "typeset") and any(
            re.fullmatch(r"-[a-zA-Z]*x[a-zA-Z]*", t) for t in rest))) and any(
            t.upper() in watch[0] for t in rest):
        # a bare name exports the shell variable of that name, however it was filled
        # (`read -r`, `printf -v`)
        return word + " " + next(t for t in rest if t.upper() in watch[0])
    npx_script = ""
    if word == "npx":
        # `npx -c 'script'` runs the string in a shell: walk it like `sh -c`.
        for flag, value in zip(rest, rest[1:]):
            if flag in ("-c", "--call"):
                npx_script = value
        rest = [t for t in rest if not t.startswith("-")] or [""]
        word, rest = rest[0], rest[1:]
    if word == "cross-env":
        for token in rest:
            if not ASSIGNMENT.match(token):
                break
            if _assigned_var(token, watch) and not install:
                return word + " " + _assigned_var(token, watch)
    cmd_flag = next((n for n, t in enumerate(rest) if t.lower() in ("/c", "/k")), None)
    script = PowerShellScript(" ".join(rest[cmd_flag + 1:])) \
        if word in CMD_EXE_NAMES and cmd_flag is not None \
        else None
    if script is None:
        script = npx_script or (" ".join(rest) if word == "eval" else (
            _pwsh_script(tokens) if word in PLAYWRIGHT_PS_SHELLS else inline_script(tokens)))
        if word in PLAYWRIGHT_PS_SHELLS and POWERSHELL_CALL[0]:
            # the outer PowerShell takes its backtick escapes (`` `$env:X ``) before pwsh runs the
            # script. Known ceiling: a backtick in outer single quotes stays literal; dropping it
            # there too can only cause a false deny.
            script = re.sub(r"`(.)", r"\1", script)
    for segment in split_segments(script) if script else ():
        hit = playwright_path_hit(segment, depth + 1, ps_inner=word in PLAYWRIGHT_PS_SHELLS,
                                  install=install, watch=watch)
        if hit:
            return hit
    return ""


def playwright_path_hit(segment: str, depth=0, to_file=False, ps_inner=False,
                        install=None, watch=PLAYWRIGHT_WATCH) -> str:
    """Return the matched text when a segment sets a watched name (PLAYWRIGHT_BROWSERS_PATH
    unless `watch` names others), else ''.

    `to_file` says the segment's output goes to a profile (a `tee` further down the pipe). The
    file-write form counts only when the written text starts with the assignment.
    """
    tokens = segment_tokens(segment) or []
    if watch is not PLAYWRIGHT_WATCH and segment_tokens(segment) is None:
        # An unterminated quote (`echo don't; export GIT_DIR=x`) makes the shared reader keep the
        # rest of the line in one segment. Read each piece between unquoted-looking separators on
        # its own; a piece that still cannot be read is skipped, as everywhere else.
        for piece in re.split(r"[;&|\n]", segment):
            if piece != segment and piece.strip():
                hit = playwright_path_hit(piece, depth, ps_inner=ps_inner, watch=watch)
                if hit:
                    return hit
    if install:
        return _playwright_tokens_hit(tokens, depth, install)
    at = resolve_command(tokens) if tokens else None
    word = basename(tokens[at]).lower() if at is not None else ""
    # A pwsh launch with a script is judged through that script (ps_inner), statement by statement.
    outer_ps = word in PLAYWRIGHT_PS_SHELLS and not _pwsh_script(tokens)
    if (POWERSHELL_CALL[0] or outer_ps or ps_inner) and word not in (
            ENV_PATTERN_COMMANDS + PLAYWRIGHT_PS_READERS):
        if watch is not PLAYWRIGHT_WATCH:
            hit = _ps_env_set(tokens, watch)
            if hit:
                return hit
        found = PLAYWRIGHT_PS_SET.search(segment) if watch is PLAYWRIGHT_WATCH else None
        # inside pwsh -c, a `$env:` text counts only as a statement, not inside another command's argument
        if found and not (ps_inner and found.group(0).startswith(("$", "{")) and not re.match(
                r"\s*" + re.escape(found.group(0)), segment)):
            return found.group(0)
    cleaned = _FD_DUP.sub(" ", SILENT_WRITE_REDIRECT.sub(" ", segment))
    if (to_file or _REDIRECT_TO_PROFILE.search(cleaned)) and len(tokens) > 1 and basename(
            tokens[0]) in ("echo", "printf"):
        words = [t for t in tokens[1:] if not t.startswith("-")]
        if basename(tokens[0]) == "printf":   # drop printf directives and escapes, keep the text
            words = [_PRINTF_DIRECTIVE.sub("", t) for t in words]
        written = " ".join(w for w in words if w)
        name = _assigned_var(written.removeprefix("export ").lstrip(), watch)
        if name:
            return name + " written to a file"
    return _playwright_tokens_hit(tokens, depth, watch=watch)


def playwright_command_hit(raw: str, stripped: str, watch=PLAYWRIGHT_WATCH) -> str:
    """Judge a whole command: each segment, plus a profile-bound heredoc body and `tee` pipe."""
    to_file = bool(re.search(r"\btee\b[^|;&]*" + PLAYWRIGHT_PROFILE.pattern, stripped))
    for segment in split_segments(stripped):
        matched = playwright_path_hit(segment, to_file=to_file, watch=watch)
        if matched:
            return matched
    for _, body, header in _split_heredocs(raw)[1]:
        if PLAYWRIGHT_PROFILE.search(header):
            for line in body.split("\n"):
                matched = playwright_path_hit(line, watch=watch)
                if matched:
                    return matched
    return ""


# GIT LOCATION VARIABLES. A GIT_DIR or GIT_WORK_TREE set in PowerShell reaches a child `git init`,
# which writes core.worktree into the shared .git/config, so every checkout reads the wrong tree.
# One walk with the Playwright rule (same segments, same wrappers, same `sh -c`/`eval`/`pwsh -c` reach),
# with a different watch list and a quote-safe PowerShell reader. KNOWN LIMITS: those of the
# Playwright rule, plus `VAR+=x cmd` as an inline prefix and PowerShell `New-Item` forms beyond
# the cmdlets listed in `_PS_CMDLETS`. `git --git-dir` and `git -C` are options, not sets.
# The quick test in git_env_command_hit strips from a text what shlex drops (`QUOTE_MARKS`), then
# looks for a watched name, case-blind. Rule: the quick test drops at least what the walk drops
# before it reads a name, or it sends the text on to the walk. The walk reads each substitution as `x` in the text around
# it, so `GIT_INDE$(echo X)_FILE` reads as the name `GIT_INDEx_FILE`: a command with a
# substitution is tested text by text, as the walk reads it, never by its raw text alone.
_GIT_ENV_NAMES = re.compile("|".join(map(re.escape, GIT_ENV_WATCH[0])), re.I)
_SUBSTITUTION_OPEN = re.compile(r"[$<>]\(|`")   # `$(`, `<(`, `>(` and a backtick: what _substitutions cuts


def _holds_git_env_name(text: str) -> bool:
    text = QUOTE_MARKS.sub("", text)
    # printf's directives and escapes (`_PRINTF_DIRECTIVE`) are the one step past shlex that drops
    # text inside a name, and the walk takes it only for a printf word. No ordering of that strip
    # with QUOTE_MARKS reads every case (`%''s`, an unquoted `\\n`), and a strip over the whole
    # text eats a name's first letter (`x=5% GIT_DIR=...`): any printf goes on to the walk.
    return "printf" in text.lower() or bool(_GIT_ENV_NAMES.search(text))


def git_env_command_hit(raw: str, stripped: str) -> str:
    """Judge a whole command for a set of GIT_DIR, GIT_WORK_TREE or GIT_INDEX_FILE. Each command
    substitution (`$(...)`, backticks, in double quotes too) is judged as a command of its own,
    through the one reader in guard_env; one nested past its depth bound is refused."""
    in_raw = _holds_git_env_name(raw)
    if not in_raw and not _SUBSTITUTION_OPEN.search(raw):
        return ""   # every hit below needs a watched name as text, once quotes and escapes fall away
    found, too_deep = _substitutions(stripped, powershell=POWERSHELL_CALL[0])
    texts = [text for text, _in_message in found]
    if too_deep:   # the env-file rule refuses a nesting this deep; judge the text as it stands
        texts = [stripped]
    # An UNQUOTED heredoc body runs its substitutions; the body text around them is data. A quoted
    # delimiter (`<<'EOF'`) runs nothing. A quote mark in the body is text (`don't`, `'$(...)'`).
    # A body nested too deep is refused by env_heredoc_refusal.
    texts = [text for quote, body, _ in _split_heredocs(raw)[1] if not quote
             for text, _in_message in _substitutions(body, heredoc=True)[0][:-1]] + texts   # command stays last
    for text in texts:
        last = text == texts[-1]
        if not (in_raw and last) and not _holds_git_env_name(text):
            continue   # no name in this text as the walk reads it (the last also reads raw's heredoc bodies)
        matched = playwright_command_hit(raw if last else text, text, GIT_ENV_WATCH)
        if matched:
            return matched
    return ""


GIT_ENV_REASON = (
    "a shell that sets the git location variables points every child git at another tree. "
    "Measured in q_max on 2026-10-14: a test's child `git init` inherited them and wrote "
    "core.worktree into the shared config, and every checkout read the wrong tree. "
    "Remedy: pass the repo path with `git -C <dir>`, or scrub every GIT_* name from the child's "
    "own environment."
)


def playwright_install_hit(stripped: str, agent: bool) -> str:
    """Judge a command for a Playwright browser install (see playwright-install-once)."""
    for segment in split_segments(stripped):
        hit = playwright_path_hit(segment, install="sub" if agent else "main")
        if hit:
            return hit
    return ""


PLAYWRIGHT_INSTALL_REASON = (
    "the Playwright browsers are shared in ~/Library/Caches/ms-playwright, and a parallel install "
    "fights over its lock. An agent asks the orchestrator for the install. The orchestrator "
    "installs once, with `npx -y node@22 node_modules/playwright/cli.js install`."
)


PLAYWRIGHT_PATH_REASON = (
    "a missing browser build has two measured causes, and a changed cache location hides both. "
    "One is a stale `__dirlock` in the Playwright cache, left by an install that stopped "
    "halfway. The other is an install that hangs while it unpacks under Node 26.11 with "
    "Playwright 1.58. "
    "Remedy: run `pgrep -fl playwright` to confirm that no install is running, then remove the "
    "stale `__dirlock`. If the install still hangs, run it under Node 22 with `npx -y node@22 "
    "node_modules/playwright/cli.js install`, which unpacks in under a second."
)

# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
