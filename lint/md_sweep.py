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
"""
import json
import os
import re
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
# Copied and adapted from hooks/guard.py (`writes_to`, `_shell_write_hit`, `strip_heredoc_bodies`,
# `SEGMENT_SPLIT`, `REDIRECT`, `MUTATING_COMMAND`), not imported. hooks/guard.py is under edit by
# another builder while this hook is built, so an import would tie this hook's behavior to a file
# in flux. The shapes below match guard.py's own regexes. They are not the same objects, and a
# future change to guard.py does not reach here on its own.
#
# guard.py's `writes_to` answers one question: does this command write to ONE KNOWN path. This
# sweep asks the opposite question: which markdown paths, if any, does this command write to. So
# the word-scan below tests every `.md`/`.markdown` word it finds as a candidate, rather than one
# path handed in by the caller.

SEGMENT_SPLIT = re.compile(r"\|\||&&|[;|\n]")
REDIRECT = re.compile(r"(\d?>>?)")

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


# Commands that change a file named in their arguments. Copied verbatim from guard.py's
# MUTATING_COMMAND, so `tee`, `sed -i`, and the PowerShell write cmdlets all count here too.
MUTATING_COMMAND = (
    r"\b(?i:rm|mv|cp|chmod|truncate|tee|install|ln"
    r"|set-content|add-content|clear-content|out-file|new-item|remove-item|move-item|copy-item"
    r"|rename-item|set-itemproperty|ri|rd|rmdir|del|erase|move|copy|ren)\b"
)

# A Python one-liner that opens a markdown path in a write mode. `open('notes.md', 'w')`,
# `open('notes.md', "a")`, `open('notes.md', 'x')`. The mode must be the SECOND argument, so a
# path that itself starts with w, x, or a is never mistaken for a mode.
PYTHON_OPEN_WRITE_CALL = re.compile(
    r"""open\s*\(\s*['"]([^'"]+\.(?:md|markdown))['"]\s*,\s*['"][xaw]"""
)


def markdown_shell_targets(cmd):
    """Return the markdown paths this shell command writes to, in first-seen order."""
    stripped = strip_heredoc_bodies(cmd)
    found = []

    def note(path):
        if path and path not in found:
            found.append(path)

    for segment in SEGMENT_SPLIT.split(stripped):
        if not segment.strip():
            continue
        for m in PYTHON_OPEN_WRITE_CALL.finditer(segment):
            note(m.group(1))
        for word in REDIRECT.sub(r" \1 ", segment).split():
            if word.startswith("-") or REDIRECT.fullmatch(word):
                continue
            bare = word.strip("'\"")
            if not bare or bare in (">", ">>"):
                continue
            if not bare.lower().endswith(MD_SUFFIXES):
                continue
            if writes_to(word, segment):
                note(bare)
    return found


def writes_to(word, segment):
    """True when the segment looks like it writes to `word`, rather than merely naming it.

    Copied and adapted from hooks/guard.py `writes_to`. Three shapes: a redirect onto the word, a
    mutating command with the word somewhere after it, or `sed -i` with the word somewhere after
    it.
    """
    target = re.escape(word)
    if re.search(r"\d?>>?\s*['\"]?" + target, segment):
        return True
    if re.search(MUTATING_COMMAND + r"[^\n;|&]*" + target, segment):
        return True
    if re.search(r"\bsed\b[^\n;|&]*-i\b[^\n;|&]*" + target, segment):
        return True
    return False


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
