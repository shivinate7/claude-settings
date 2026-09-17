#!/usr/bin/env python3
"""Claude Code hook: markdown sweep (Stop).

THE DEFECT THIS CLOSES. The PreToolUse STE gate (ste_gate.py) only sees a Write, Edit, or
MultiEdit call on a *.md path. A markdown file written through Bash never passes through
those tools. A heredoc, a `>` redirect, a `sed -i`, a `tee`, and a `python -c` that opens
the file for writing all skip the PreToolUse gate. The predicate that gate checks is the
tool or the file extension spelled in a tool call, not the act of writing a markdown file.
This hook checks the act instead, at the end of the turn.

SEVERITY. This hook blocks the turn once when it finds an error, the same severity as the
PreToolUse gate. A gate a lane can skip by picking another tool is not a gate.

SCOPE. This hook lints only the markdown files this turn changed, whatever tool wrote them.
It walks the transcript from the last human message, the way hooks/config_report.py does.
It never scans the whole repository. An old file with old errors is not this turn's debt.

Reads the hook JSON on stdin. Always exits 0. Fails open on bad input, a missing transcript,
a parse error, a missing file, a file outside the project, or a file this hook cannot read.
A hook must never brick a session.

Off switch: set MD_SWEEP_DISABLE to any non-empty value. The sweep then does nothing at all.

Exclude: set MD_SWEEP_EXCLUDE to a comma-separated list of glob patterns. Each pattern goes
straight to ste_lint.py's own `--exclude` flag, so a generated report can name its own path
or a glob for its folder, from the shell, with no edit to this repo.

Stop: when this turn wrote a markdown file through Write, Edit, MultiEdit, NotebookEdit, or
a Bash or PowerShell command, read each such file from disk and lint it at error severity.
Block once, naming every file and its findings, when any file has an error. When
stop_hook_active is set, the reply is already a rewrite, so the gate stays quiet.

SHAPES CAUGHT. A heredoc, a `>` or `>>` redirect, `sed -i`, `perl -i`, `ruby -i`, `tee`,
`mv`, `cp`, `install`, `chmod`, `truncate`, `ln`, the PowerShell write cmdlets, `dd of=`,
`awk`/`gawk` with an output redirect inside the program text, a `python -c` that opens the
path as a string literal or uses `pathlib.Path(...).write_text` or `.open("w")`, a `perl -e`
that opens the path for writing, and a `node -e` that calls `fs.writeFileSync`,
`fs.appendFileSync`, or `fs.createWriteStream`.

SHAPE NOT CAUGHT, ON PURPOSE. A path held in a shell VARIABLE, not written as a literal in
the command text, stays out of scope. `f=notes.md; sed -i s/a/b/ "$f"` is not seen. This
hook reads literal path arguments only. It never expands a variable, because a variable can
hold anything at hook time, and guessing its value would be exactly the kind of workaround
this repo avoids. This is a known hole, not a defect: name it in the report, do not silently
patch it with a guess.

Each shell segment is judged by its COMMAND WORD, the way hooks/guard.py judges a shell
segment. A program name inside a quoted argument, for example `grep -n "fs.writeFileSync"
notes.md`, is never mistaken for that program running.
"""
import json
import os
import re
import shlex
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LINTER = os.path.join(HERE, "ste_lint.py")

MD_SUFFIXES = (".md", ".markdown")
FILE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
SHELL_TOOLS = {"Bash", "PowerShell"}

DISABLE_VAR = "MD_SWEEP_DISABLE"
EXCLUDE_VAR = "MD_SWEEP_EXCLUDE"

NOTE = ("Code in backticks or a fence is exempt. Errors only: sentence length, semicolon, "
        "Latin abbreviation, contraction.")


# ------------------------------------------------------------------ transcript walking
#
# Copied from lint/report_gate.py, not imported. This keeps the hook in one file, with no
# import between two hooks fired by the same Stop event.

def is_last_human(rec):
    if rec.get("type") != "user":
        return False
    if rec.get("isSidechain"):
        return False
    msg = rec.get("message") or {}
    content = msg.get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        has_text = any(isinstance(b, dict) and b.get("type") == "text" for b in content)
        has_tool_result = any(
            isinstance(b, dict) and b.get("type") == "tool_result" for b in content
        )
        return has_text and not has_tool_result
    return False


def tool_uses(rec):
    msg = rec.get("message") or {}
    content = msg.get("content")
    if not isinstance(content, list):
        return
    for b in content:
        if isinstance(b, dict) and b.get("type") == "tool_use":
            yield b


def records_after_last_human(records):
    last_human_idx = None
    for i, rec in enumerate(records):
        if is_last_human(rec):
            last_human_idx = i
    if last_human_idx is None:
        return []
    return records[last_human_idx + 1:]


def read_transcript(path):
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if isinstance(rec, dict):
                records.append(rec)
    return records


# ------------------------------------------------------------------ shell write detection
#
# Copied and adapted from hooks/guard.py (`split_segments`, `segment_tokens`, `resolve_command`,
# `strip_heredoc_bodies`), not imported. hooks/guard.py is under edit by another builder while
# this hook is built, so an import would tie this hook's behavior to a file in flux. This repo's
# convention is to copy small helpers across `lint/` and `hooks/` rather than import them, the
# same choice hooks/config_report.py made for its own transcript walk. These copies are not the
# same objects, and a future change to guard.py does not reach here on its own.
#
# guard.py's `resolve_command` answers one question: which token is THE command that runs. This
# sweep asks a different question: which markdown paths, if any, does that command write. So the
# code below tests each segment's command word, then reads that command's own arguments for a
# markdown path, rather than checking one path handed in by a caller.

HEREDOC_HEADER = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
INTERPRETER_HEREDOC = re.compile(
    r"\b(bash|sh|zsh|dash|ksh|python3?|perl|ruby|node)\b[^\n]*<<"
)


def strip_heredoc_bodies(cmd):
    """Drop the body of every heredoc, and keep every header line.

    A heredoc body is data, not a command. Text inside it must not read as a write. The header
    line is kept, so `cat <<'EOF' > notes.md` still counts as a write to notes.md.
    """
    if INTERPRETER_HEREDOC.search(cmd):
        return cmd  # an interpreter may run the body, so keep it under inspection
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


# ------------------------------------------------------------------ quote-aware segment split
#
# Copied from hooks/guard.py `split_segments`, verbatim in behavior. A blind split on `;`
# and `|` cuts a quoted argument that holds one of those characters into a segment of its
# own, and whatever word lands first in that fragment then reads as a COMMAND. MEASURED
# defect class: `sed -i 's/a;b/c/' notes.md` split on the naive splitter puts `b/c/'
# notes.md` in its own fragment, so the sweep never sees `notes.md` as an argument of the
# `sed -i` call that actually writes it.
def split_segments(cmd):
    """Split into shell segments on unquoted `;`, `|`, `||`, `&&`, and newline.

    Quoted text, single or double, is copied whole into the current segment, so a delimiter
    inside a quote never starts a new one. An unterminated quote runs to the end of the
    string, which keeps the remainder inside it rather than guessing where it would close.
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


def basename(token):
    """Copied from hooks/guard.py `basename`. The final path component, lowercased."""
    return token.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()


# A leading `VAR=value` assignment, which is not a segment's command. Copied from guard.py.
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

# A wrapper that runs another program in its place. Copied from guard.py `COMMAND_WRAPPERS`.
COMMAND_WRAPPERS = {"sudo", "env", "command", "nohup", "nice", "time", "doas", "xargs"}


def segment_tokens(segment):
    """Tokenize one segment with shlex, or return None when it cannot be parsed.

    An unmatched quote or a stray backslash means this hook cannot tell what the segment
    would run. Fail open here: judge nothing rather than guess.
    """
    try:
        return shlex.split(segment, posix=True)
    except ValueError:
        return None


def resolve_command(tokens):
    """Return the index of the command word in a tokenized segment, or None when it names none.

    Copied from hooks/guard.py `resolve_command`. Skips leading `VAR=value` assignments, then
    unwraps command wrappers (`sudo`, `env`, `command`, `nohup`, `nice`, `time`, `doas`,
    `xargs`) along with each wrapper's own flags, so the index returned is the program that
    actually runs.
    """
    index = 0
    end = len(tokens)
    while index < end and ASSIGNMENT.match(tokens[index]):
        index += 1
    while index < end and basename(tokens[index]) in COMMAND_WRAPPERS:
        index += 1
        while index < end and tokens[index].startswith("-"):
            index += 1
        while index < end and ASSIGNMENT.match(tokens[index]):
            index += 1
    return index if index < end else None


# ------------------------------------------------------------------ write shapes
#
# A Python one-liner that opens a markdown path in a write mode. `open('notes.md', 'w')`,
# `open('notes.md', "a")`, `open('notes.md', 'x')`. The mode must be the SECOND argument, so a
# path that itself starts with w, x, or a is never mistaken for a mode. Scanned over the raw
# segment text, unchanged from the earlier version of this hook.
PYTHON_OPEN_WRITE_CALL = re.compile(
    r"""open\s*\(\s*['"]([^'"]+\.(?:md|markdown))['"]\s*,\s*['"][xaw]"""
)

# A `pathlib.Path` write. `Path("notes.md").write_text(...)`, `.write_bytes(...)`, or
# `.open("w")` / `.open("a")` / `.open("x")`.
PATHLIB_WRITE_TEXT = re.compile(
    r"""Path\s*\(\s*['"]([^'"]+\.(?:md|markdown))['"]\s*\)\s*\.\s*(?:write_text|write_bytes)\s*\("""
)
PATHLIB_OPEN_WRITE = re.compile(
    r"""Path\s*\(\s*['"]([^'"]+\.(?:md|markdown))['"]\s*\)\s*\.\s*open\s*\(\s*['"][xaw]"""
)

# A Node one-liner that writes with the `fs` module. `fs.writeFileSync("notes.md", ...)`,
# `fs.appendFileSync(...)`, `fs.createWriteStream(...)`.
NODE_WRITE_CALL = re.compile(
    r"""fs\.(?:writeFileSync|appendFileSync|createWriteStream)\s*\(\s*['"]([^'"]+\.(?:md|markdown))['"]"""
)

# A Perl `open` for writing. The two-arg form folds the mode into the path string,
# `open(FH, ">notes.md")`. The three-arg form keeps them apart, `open(FH, '>', 'notes.md')`.
PERL_OPEN_WRITE_2ARG = re.compile(
    r"""open\s*\(?\s*[A-Za-z_][A-Za-z0-9_]*\s*,\s*['"]>>?\s*([^'"]+\.(?:md|markdown))['"]"""
)
PERL_OPEN_WRITE_3ARG = re.compile(
    r"""open\s*\(?\s*[A-Za-z_][A-Za-z0-9_]*\s*,\s*['"]>>?['"]\s*,\s*['"]([^'"]+\.(?:md|markdown))['"]"""
)

# `awk`/`gawk` write inside their own program text, not at the shell. `{ print > "notes.md" }`.
# The program is one shell argument (usually one shlex token), so this is matched against each
# of the command's own arguments, never against the whole segment.
AWK_PROGRAM_REDIRECT = re.compile(r'>>?\s*"([^"]+\.(?:md|markdown))"')

# Commands whose own arguments name the path they write, once the command word is confirmed.
# Flags are skipped. Copied in spirit from the earlier MUTATING_COMMAND list, plus the shapes
# this task adds.
SIMPLE_WRITE_COMMANDS = {
    "mv", "cp", "chmod", "truncate", "install", "ln", "tee",
    "set-content", "add-content", "clear-content", "out-file", "new-item",
    "remove-item", "move-item", "copy-item", "rename-item", "set-itemproperty",
    "ri", "rd", "rmdir", "del", "erase", "move", "copy", "ren",
}

# Interpreters whose `-i` (in-place) flag turns their own file arguments into writes.
INPLACE_EDIT_COMMANDS = {"sed", "perl", "ruby"}

# `-i`, `-i.bak`, `--in-place`, or a combined short form such as `-pi` or `-ni`. Matches only
# a token that starts with one dash and holds an `i`, which is the shape sed/perl/ruby use.
INPLACE_FLAG = re.compile(r"^-[a-z]*i[a-z0-9._-]*$")


def _has_inplace_flag(args):
    for arg in args:
        if arg in ("-i", "--in-place") or arg.startswith("--in-place"):
            return True
        if arg.startswith("-") and not arg.startswith("--") and INPLACE_FLAG.match(arg):
            return True
    return False


def _flag_value(args, flags):
    """Return the value of the first matching flag, spaced or attached, or None."""
    for index, arg in enumerate(args):
        for flag in flags:
            if arg == flag and index + 1 < len(args):
                return args[index + 1]
            if arg.startswith(flag) and len(arg) > len(flag):
                return arg[len(flag):]
    return None


def _literal_args(args):
    return [a for a in args if not a.startswith("-")]


def command_targets(word, args):
    """Return candidate markdown paths this one command call writes, judged by its own word.

    `word` is the resolved command word, already unwrapped from `sudo`/`env`/etc. `args` are
    its own tokens, quote-stripped by shlex. A path in a VARIABLE, not a literal, is invisible
    here on purpose: this function never expands `$foo`, it only reads literal tokens.
    """
    targets = []
    if word in SIMPLE_WRITE_COMMANDS:
        targets += _literal_args(args)
    if word in INPLACE_EDIT_COMMANDS and _has_inplace_flag(args):
        targets += _literal_args(args)
    if word in ("awk", "gawk"):
        for arg in args:
            targets += AWK_PROGRAM_REDIRECT.findall(arg)
    if word == "dd":
        for arg in args:
            if arg.startswith("of="):
                targets.append(arg[3:])
    if word in ("python", "python3"):
        script = _flag_value(args, ("-c",))
        if script:
            targets += PYTHON_OPEN_WRITE_CALL.findall(script)
            targets += PATHLIB_WRITE_TEXT.findall(script)
            targets += PATHLIB_OPEN_WRITE.findall(script)
    if word == "node":
        script = _flag_value(args, ("-e", "-p", "--eval"))
        if script:
            targets += NODE_WRITE_CALL.findall(script)
    if word == "perl":
        script = _flag_value(args, ("-e",))
        if script:
            targets += PERL_OPEN_WRITE_2ARG.findall(script)
            targets += PERL_OPEN_WRITE_3ARG.findall(script)
    return [t for t in targets if t.lower().endswith(MD_SUFFIXES)]


# A shell redirection operator, spaced or attached to its target: `>`, `>>`, `2>`, or the
# same attached to a following word, `>notes.md`. Read off shlex tokens, so a redirect
# character sitting inside a quoted argument never reaches this check.
REDIRECT_TOKEN = re.compile(r"^(\d?>>?)(.*)$")


def redirect_targets_in_tokens(tokens):
    """Return the words a segment's tokens redirect onto, in order."""
    targets = []
    index = 0
    while index < len(tokens):
        match = REDIRECT_TOKEN.match(tokens[index])
        if match:
            rest = match.group(2)
            if rest:
                targets.append(rest)
            elif index + 1 < len(tokens):
                targets.append(tokens[index + 1])
        index += 1
    return targets


def markdown_shell_targets(cmd):
    """Return the markdown paths this shell command writes to, in first-seen order.

    Splits on the quote-aware splitter, then judges each segment by its own command word,
    the way hooks/guard.py judges a segment. A segment shlex cannot parse is skipped: fail
    open, never guess.
    """
    stripped = strip_heredoc_bodies(cmd)
    found = []

    def note(path):
        bare = path.strip("'\"") if path else ""
        if bare and bare.lower().endswith(MD_SUFFIXES) and bare not in found:
            found.append(bare)

    for segment in split_segments(stripped):
        if not segment.strip():
            continue
        # Kept ungated, over the raw segment text: the shape this hook already caught.
        for m in PYTHON_OPEN_WRITE_CALL.finditer(segment):
            note(m.group(1))

        tokens = segment_tokens(segment)
        if tokens is None:
            continue

        for target in redirect_targets_in_tokens(tokens):
            note(target)

        index = resolve_command(tokens)
        if index is None:
            continue
        word = basename(tokens[index])
        for target in command_targets(word, tokens[index + 1:]):
            note(target)
    return found


# ------------------------------------------------------------------ collecting this turn's targets

def _resolve_path(path, cwd):
    target = os.path.expandvars(os.path.expanduser(path.strip("'\"")))
    if not os.path.isabs(target) and cwd:
        target = os.path.join(cwd, target)
    return os.path.realpath(target)


def _within_project(path, cwd):
    try:
        root = os.path.realpath(cwd)
    except Exception:
        return False
    return path == root or path.startswith(root + os.sep)


def collect_markdown_targets(records, cwd):
    """Return the markdown paths (resolved, absolute) this turn's tools wrote, first-seen order."""
    seen = []
    resolved_set = set()

    def note(raw_path):
        if not raw_path or not isinstance(raw_path, str):
            return
        try:
            resolved = _resolve_path(raw_path, cwd)
        except Exception:
            return
        if resolved in resolved_set:
            return
        resolved_set.add(resolved)
        seen.append(resolved)

    for rec in records:
        for b in tool_uses(rec):
            name = b.get("name")
            inp = b.get("input") or {}
            if not isinstance(inp, dict):
                continue
            if name in FILE_TOOLS:
                target = (
                    inp.get("file_path") or inp.get("path") or inp.get("notebook_path") or ""
                )
                if isinstance(target, str) and target.lower().endswith(MD_SUFFIXES):
                    note(target)
            elif name in SHELL_TOOLS:
                cmd = inp.get("command") or ""
                if isinstance(cmd, str) and cmd.strip():
                    for md_path in markdown_shell_targets(cmd):
                        note(md_path)
    return seen


# ------------------------------------------------------------------ linting from disk

def lint_files(paths, exclude):
    """Return {path: [finding lines]} for the error-level findings of ste_lint.py on paths.

    Every path here is already checked to exist and to be readable, so a bad path never keeps
    ste_lint.py from printing JSON for the paths that ARE good.
    """
    if not os.path.exists(LINTER) or not paths:
        return {}
    cmd = [sys.executable, LINTER, "--no-color", "--format", "json", "--fail-on", "never"]
    if exclude:
        cmd += ["--exclude", exclude]
    cmd += paths
    try:
        run = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        data = json.loads(run.stdout or "{}")
    except Exception:
        return {}
    by_path = {}
    for f in data.get("findings", []):
        if f.get("severity") != "error":
            continue
        by_path.setdefault(f.get("path"), []).append(
            "line %s: %s %s" % (f.get("line"), f.get("code"), f.get("message")))
    return by_path


def main():
    try:
        hook = json.load(sys.stdin)
    except Exception:
        return
    if not isinstance(hook, dict):
        return
    if hook.get("hook_event_name") not in (None, "Stop"):
        return
    if hook.get("stop_hook_active"):
        return
    if os.environ.get(DISABLE_VAR):
        return

    path = hook.get("transcript_path")
    if not path or not os.path.exists(path):
        return

    try:
        records = read_transcript(path)
    except Exception:
        return

    after = records_after_last_human(records)
    if not after:
        return

    cwd = hook.get("cwd") or ""
    if not isinstance(cwd, str) or not cwd:
        cwd = os.getcwd()

    targets = collect_markdown_targets(after, cwd)
    if not targets:
        return

    # Fail open: a missing file, a file outside the project, or a file this hook cannot read is
    # dropped here and never reaches the linter or the block message.
    readable = []
    for resolved in targets:
        try:
            if not _within_project(resolved, cwd):
                continue
            if not os.path.isfile(resolved):
                continue
            with open(resolved, "r", encoding="utf-8") as f:
                f.read(0)  # a cheap probe: raises on a permission or decode problem
        except Exception:
            continue
        readable.append(resolved)
    if not readable:
        return

    exclude = os.environ.get(EXCLUDE_VAR, "")
    by_path = lint_files(readable, exclude)
    if not by_path:
        return

    lines = []
    for resolved in readable:
        findings = by_path.get(resolved)
        if not findings:
            continue
        lines.append("%s:" % os.path.basename(resolved))
        lines.extend("  " + x for x in findings)
    if not lines:
        return

    reason = (
        "This turn wrote markdown outside Write, Edit, or MultiEdit. STE lint found errors "
        "in the file on disk after the write.\n%s\n%s Fix the text, then finish the turn."
        % ("\n".join(lines), NOTE)
    )
    print(json.dumps({"decision": "block", "reason": reason}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
