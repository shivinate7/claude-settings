"""The guard's readonly family: the readonly-shell-write rule, a shell write by a read-only role.

guard.py is the only entry point, and it calls these checks in its fixed order. Other files reach these names
through `guard`. The rule index, in check order:

  readonly-shell-write
                       deny. A shell call by an agent of a read-only role (`READ_ONLY` in agent_brief.py) that
                       writes a file outside its own session's scratchpad: a redirect to a target that is no null
                       device, `tee`, `touch`, or `mktemp` without `-u`. The same forms in an ssh remote command,
                       where no scratchpad path is exempt. A `>` in quotes, a comment or a heredoc body is text.
                       The reason gives the scratchpad remedy. An override lifts it. (guard-guards-mistakes-only)
"""
import os
import re
import shlex

import guard_core
from guard_core import (
    POWERSHELL_CALL, REDIRECTION, SILENT_WRITE_REDIRECT, _REDIRECT_OPERATOR, basename, command_indexes,
    dir_before_segment, inner_commands, segment_tokens, shell_abs, split_segments, ssh_remote_script,
    strip_heredoc_bodies, strip_redirections, walk_quotes,
)
from guard_frozen import _resolve_vars
from guard_shared_tree import under_session_scratchpad
from guard_write import unquoted_at


# Rule readonly-shell-write. An agent whose type is a READ_ONLY role (hooks/agent_brief.py, the one home) writes no
# file from the shell: not by a redirect, `tee`, `touch` or `mktemp` (not `-u`). Its own session's scratchpad is
# the one place it may write. Over ssh the same forms are judged on the remote command, where the scratchpad
# exemption never applies: that path sits on the other machine. Quotes, comments and heredoc bodies are read as
# the other shell rules read them (`split_segments`, `strip_heredoc_bodies`, `strip_redirections`). Cost: pure
# text work inside the guard call already running; no process, no file.
READONLY_WRITE_DEPTH = 4          # nested shells, ssh commands and substitutions read; text nested deeper is not judged
READONLY_STREAMS = ("/dev/stdout", "/dev/stderr", "/dev/tty")   # open descriptors and the terminal: no file is written
READONLY_TOUCH_VALUE_FLAGS = ("-d", "-t", "-r", "--date", "--reference")   # `touch` flags that take the next word


def _null_device(path: str) -> bool:
    """True when `path` writes no file: a null device or a stream. The null devices are SILENT_WRITE_REDIRECT's list,
    narrowed by the tool: NUL and `$null` are PowerShell's, and on Bash `NUL` is an ordinary file name. The streams are
    READONLY_STREAMS."""
    if path in READONLY_STREAMS:
        return True
    if not SILENT_WRITE_REDIRECT.match(">" + path):
        return False
    return POWERSHELL_CALL[0] or path.strip("'\"").lower() != "nul"


READONLY_TEST_LEADS = guard_core.LOOP_KEYWORDS | {"!", "time"}   # words after which a `[[` or `((` still starts a command


def _command_start(text: str, at: int) -> bool:
    """True when `text[at]` starts a command: it opens the text or follows a command separator, an opening
    paren or backquote, or a keyword such as `if` or `!` that itself starts a command. Elsewhere `[[` and `((`
    are ordinary words, as `echo [[ x` shows."""
    before = text[:at].rstrip(" \t")
    if not before or before[-1] in ";&|\n(`":
        return True
    word = re.split(r"[\s;&|(`]", before)[-1]
    return word in READONLY_TEST_LEADS and _command_start(text, len(before) - len(word))


def _comparison_spans(text: str):
    """The (start, end) of each unquoted, closed `[[ ... ]]` test and `(( ... ))` or `$(( ... ))` arithmetic.
    A `>` inside one is a comparison, not a redirect. `[[` and `((` open one only at a command start; `$((` opens
    one anywhere. Bash reads `((` as arithmetic only when the paren after it closes right before the last `)`,
    so `((a) && b)` is two subshells. An opener never closed is no span: its `>` stays a redirect."""
    spans, open_at, depth = [], None, 0
    steps = [(at, bool(quote)) for at, _, quote in walk_quotes(text)]
    # walk_quotes skips the second char of an escape or `$'`: that char keeps the state of the one before it
    quoted = {at + gap for (at, inside), (after, _) in zip(steps, steps[1:] + [(len(text), False)])
              if inside for gap in range(after - at)}
    for at, char in enumerate(text):
        if at in quoted:
            continue
        if open_at is None:
            if text.startswith("[[", at) and text[at + 2:at + 3] in (" ", "\t") and _command_start(text, at):
                open_at, depth = at, -1
            elif text.startswith("((", at) and (text[at - 1:at] == "$" or _command_start(text, at)):
                open_at, depth = at, 1
        elif depth < 0:      # inside [[ ]]
            if text.startswith("]]", at) and text[at - 1] in " \t":
                spans.append((open_at, at + 2))
                open_at = None
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 1 and text[at + 1:at + 2] != ")":
                open_at = None   # the inner paren closed before the end: subshells, not arithmetic
            elif depth == 0:
                spans.append((open_at, at + 1))
                open_at = None
    return spans


def _mask_comparisons(text: str) -> str:
    """The text with each unquoted `>` inside a comparison span (`_comparison_spans`) made a space. The spans are
    found on the whole command, because `split_segments` cuts a test such as `[[ a > b || c ]]` at its `||`."""
    if "[[" not in text and "((" not in text:
        return text
    chars = list(text)
    for start, end in _comparison_spans(text):
        for at in range(start, end):
            if chars[at] == ">" and unquoted_at(text, at):
                chars[at] = " "
    return "".join(chars)


def _redirect_targets(segment: str):
    """The target of each unquoted output redirect in one segment that writes no file (`_null_device`) and is no
    descriptor duplicate (`2>&1`). An input redirect and a heredoc header (`<<`) write nothing. A comparison's `>`
    is already masked (`_mask_comparisons`)."""
    for target, _append in _redirect_writes(segment):
        yield target


def _redirect_writes(segment: str):
    """(target, append) for each redirect `_redirect_targets` counts; `append` is True for `>>`."""
    for found in REDIRECTION.finditer(segment):
        word = found.group()
        if word[0] == "<" or not unquoted_at(segment, found.start()):
            continue
        operator = _REDIRECT_OPERATOR.match(word).end()
        if SILENT_WRITE_REDIRECT.match(word) and _null_device(word[operator:].lstrip("&")):
            continue
        start = found.start() + operator
        target = segment[start:found.end()]
        if re.fullmatch(r"&(?:\d+|-)", target):
            continue
        target = target.lstrip("&|")   # `>&FILE` sends both streams, `>|FILE` overrides noclobber
        if not target:                 # a space after the operator: the next word is the file
            target = (segment[found.end():].split() or [""])[0]
        if target[:1] in ("'", '"') and target.count(target[0]) < 2:
            opened = segment.index(target[0], start)
            close = segment.find(target[0], opened + 1)
            target = segment[opened + 1:close] if close > 0 else target[1:]
        else:
            try:
                target = "".join(shlex.split(target.rstrip(")`") or target))
            except ValueError:
                pass
        if target and not _null_device(target):
            yield target, ">>" in word[:operator]


def _mktemp_paths(args):
    """The path a `mktemp` creates, as a list of one, or [] for a dry run (`-u`). '' when the place is the shell's
    own temp folder (no template and no `-p DIR`, `-t`, or a bare `--tmpdir`): no scratchpad exemption names it."""
    names, folder, temp, index = [], None, False, 0
    while index < len(args):
        arg, index = args[index], index + 1
        if arg == "--dry-run" or (arg.startswith("-") and not arg.startswith("--") and "u" in arg[1:]):
            return []
        if arg == "-p" and index < len(args):
            folder, index = args[index], index + 1
        elif arg.startswith("-p") and not arg.startswith("--"):
            folder = arg[2:]
        elif arg.startswith("--tmpdir="):
            folder = arg.split("=", 1)[1]
        elif arg == "--tmpdir" or (arg.startswith("-") and not arg.startswith("--") and "t" in arg[1:]):
            temp = True
        elif not arg.startswith("-"):
            names.append(arg)
    if temp and folder is None:
        return [""]
    if names:
        return [os.path.join(folder, names[0]) if folder else names[0]]
    return [folder or ""]


def _verb_written_paths(verb: str, args):
    """The paths one command word writes when it is `tee`, `touch` or `mktemp`, else []."""
    if verb == "mktemp":
        return _mktemp_paths(list(args))
    if verb not in ("tee", "touch"):
        return []
    paths, skip = [], False
    for arg in args:
        if skip:
            skip = False
        elif verb == "touch" and arg in READONLY_TOUCH_VALUE_FLAGS:
            skip = True
        elif not arg.startswith("-") or arg == "-":
            paths.append(arg)
    return [path for path in paths if not _null_device(path)]


def readonly_write_hit(command: str, cwd: str, session: str, remote: bool = False, depth: int = 0) -> str:
    """The path (or the verb) a read-only agent's shell command writes outside its own scratchpad, else ''.
    `remote` reads `command` as the text an ssh call runs on the far side: every write counts there."""
    if depth > READONLY_WRITE_DEPTH:
        return ""
    ends = []
    masked = _mask_comparisons(_resolve_vars(strip_heredoc_bodies(command, shells_only=True, per_body=True)))
    segments = split_segments(masked, ends)

    def outside(path: str, where: str) -> bool:
        if remote or not path:
            return True
        full = shell_abs(path, where)
        return not full or not under_session_scratchpad(full, session)

    for number, segment in enumerate(segments):
        if not segment.strip():
            continue
        where = dir_before_segment(segments, number, cwd, ends) or cwd
        for target in _redirect_targets(segment):
            if outside(target, where):
                return target
        tokens = segment_tokens(strip_redirections(segment))
        if not tokens:
            continue
        for at in command_indexes(tokens):
            verb = basename(tokens[at]).lower()
            for path in _verb_written_paths(verb, tokens[at + 1:]):
                if outside(path, where):
                    return path or verb
        remote_text = ssh_remote_script(tokens)
        for text in inner_commands(tokens):
            hit = readonly_write_hit(text, where, session, remote or text == remote_text, depth + 1)
            if hit:
                return hit
    return ""


READONLY_SHELL_WRITE_REASON = (
    "Rule (readonly-shell-write): a read-only agent changes no file outside its own session's scratchpad folder, "
    "and this shell call writes one (a redirect, tee, touch or mktemp), here or over ssh. "
    "Remedy: read with the shell, and write notes only to a file under your session's scratchpad folder; "
    "put any other finding in your report, and the orchestrator assigns the change to a builder. "
    "(decision guard-guards-mistakes-only, guards stop the mistakes Claude makes in normal work)"
)


# INSTALL_ID = "uninstalled"
