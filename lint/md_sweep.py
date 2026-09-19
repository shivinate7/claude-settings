#!/usr/bin/env python3
"""Claude Code hook: markdown sweep (Stop).

THE DEFECT THIS CLOSES. The PreToolUse STE gate (ste_gate.py) only sees a Write, Edit, or
MultiEdit call on a *.md path. A markdown file written through Bash never passes through
that gate. The earlier version of this hook chased the hole by matching SHAPES in the Bash
command text: a heredoc, a `>` redirect, `sed -i`, a `python -c` string, and more. That list
can only grow, never finish. `python3 gen.py`, `bash gen.sh`, `pandoc -o notes.md`, and
`make docs` were all invisible to it, because the hole is the class "any program not on the
list," not one shape.

This hook now checks the ACT, not the command shape: a markdown file under `cwd` whose mtime
is newer than this turn's last human message, kept only when it is also dirty against HEAD in
a git work tree. It never reads a command string.

SEVERITY. This hook blocks the turn once when it finds an error, the same severity as the
PreToolUse gate. A gate a lane can skip by picking another tool is not a gate.

SCOPE. This hook lints only the markdown files this turn changed, whatever tool wrote them.
It reads the last human message's timestamp from the transcript, the way
hooks/config_report.py reads that same field for its own turn boundary.
It never scans the whole repository. An old file with old errors is not this turn's debt.

Reads the hook JSON on stdin. Always exits 0. Fails open on bad input, a missing transcript,
a parse error, a missing file, a file outside the project, or a file this hook cannot read.
A hook must never brick a session.

Off switch: set MD_SWEEP_DISABLE to any non-empty value. The sweep then does nothing at all.

Exclude: set MD_SWEEP_EXCLUDE to a comma-separated list of glob patterns. Each pattern goes
straight to ste_lint.py's own `--exclude` flag, so a generated report can name its own path
or a glob for its folder, from the shell, with no edit to this repo.

THE PREDICATE.

1. Find the last human message record in the transcript. Read its `timestamp` field, an
   ISO-8601 UTC string such as `2026-08-29T18:56:54.926Z`.
2. Find every `.md` and `.markdown` file under `cwd` whose mtime is newer than that
   timestamp.
3. When `cwd` is a git work tree, keep only the files `git status --porcelain` also marks
   dirty against HEAD. A `git pull` or a branch switch mid-turn rewrites the mtime of many
   markdown files the turn did not author. A pull or a switch leaves those files clean, so
   this filter drops them.
4. Outside a git tree, or when git is missing or fails, mtime alone decides.
5. Lint the survivors from disk with ste_lint.py at error severity, exactly as before. Block
   once, naming every file and its findings.

HOLES IN THE NEW PREDICATE, NAMED HONESTLY.

A last human record with no `timestamp` field gives no baseline. The sweep then does
nothing at all. This is a silent miss, not a crash.

A file this turn wrote, whose final content ends up identical to HEAD, for example an edit
undone by a later edit in the same turn, reads as clean against HEAD. The git filter drops
it, even though this turn did touch it.

A concurrent agent writing markdown into the same checkout, from a second session sharing
this working directory, is attributed to this turn. The predicate reads mtime and git status
only. It has no notion of which session wrote a file.

A large clock skew between the machine that stamped the transcript timestamp and the
filesystem clock that stamps mtimes would corrupt the comparison. Both clocks are the same
machine in the normal case, so this is named as a hole, not treated as a live defect.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
LINTER = os.path.join(HERE, "ste_lint.py")

MD_SUFFIXES = (".md", ".markdown")
SKIP_DIR_NAMES = {"node_modules"}

DISABLE_VAR = "MD_SWEEP_DISABLE"
EXCLUDE_VAR = "MD_SWEEP_EXCLUDE"

NOTE = ("Code in backticks or a fence is exempt. Errors only: sentence length, semicolon, "
        "Latin abbreviation, contraction.")


# ------------------------------------------------------------------ transcript walking
#
# Copied from hooks/config_report.py, not imported. This keeps the hook in one file, with no
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


def last_human_stamp(records):
    """Return the `timestamp` field of the last human message, else an empty string.

    A transcript can hold more than one human record. This turn's boundary is the LAST one,
    so a later record's stamp always wins over an earlier one.
    """
    stamp = ""
    for rec in records:
        if is_last_human(rec):
            value = rec.get("timestamp") or ""
            stamp = value if isinstance(value, str) else ""
    return stamp


def parse_utc_timestamp(text):
    """Parse an ISO-8601 transcript timestamp into POSIX epoch seconds, or return None.

    The transcript field looks like `2026-08-29T18:56:54.926Z`. `datetime.fromisoformat`
    does not accept a trailing `Z` on every supported Python version, so it is swapped for
    `+00:00` first. A value with no zone offset at all is treated as UTC, because every real
    record on this machine carries the `Z`. Anything that still fails to parse gives no
    baseline, the same as a missing field.
    """
    text = (text or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except Exception:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.timestamp()


# ------------------------------------------------------------------ finding markdown files

def _run_git(cwd, args, timeout=20):
    """Run one git command rooted at cwd. Return the finished process, or None on any failure.

    None covers a missing git binary, a timeout, and any other exception. It never covers a
    plain non-zero exit, which the caller reads from `returncode`.
    """
    try:
        return subprocess.run(
            ["git", "-C", cwd] + args, capture_output=True, text=True, timeout=timeout,
        )
    except Exception:
        return None


def markdown_files_git(cwd):
    """Return absolute markdown paths under cwd, from git's own file listing.

    Covers tracked files and untracked files git does not ignore, scoped to cwd's own
    subtree with the trailing `-- .` pathspec. Returns None when git is missing, cwd is not a
    work tree, or the command fails, so the caller falls back to a filesystem walk. This
    listing already skips `.git`, `node_modules`, build output, and anything else the
    repository's own `.gitignore` names, with no separate skip list to keep in step with it.
    """
    run = _run_git(cwd, ["ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "."])
    if run is None or run.returncode != 0:
        return None
    paths = []
    for rel in run.stdout.split("\0"):
        if rel and rel.lower().endswith(MD_SUFFIXES):
            paths.append(os.path.realpath(os.path.join(cwd, rel)))
    return paths


def markdown_files_walk(cwd):
    """Return absolute markdown paths under cwd, from a plain filesystem walk.

    Used only when cwd is not a git work tree, or git is missing or fails. Skips `.git`,
    `node_modules`, and every other dot-directory, so the walk never descends into a huge
    generated or vendored tree that a real turn never touches.
    """
    paths = []
    for root, dirs, files in os.walk(cwd):
        dirs[:] = [d for d in dirs if d not in SKIP_DIR_NAMES and not d.startswith(".")]
        for name in files:
            if name.lower().endswith(MD_SUFFIXES):
                paths.append(os.path.realpath(os.path.join(root, name)))
    return paths


def git_dirty_paths(cwd):
    """Return the absolute paths `git status --porcelain` marks dirty against HEAD.

    Return None when git is missing, cwd is not a work tree, or the command fails, so the
    caller skips the dirty filter rather than dropping every file on a guess. A rename or a
    copy entry carries a second, NUL-separated field for its old path, which is consumed and
    dropped here, never counted as a dirty target on its own.
    """
    run = _run_git(cwd, ["status", "--porcelain", "-z", "--untracked-files=all", "--", "."])
    if run is None or run.returncode != 0:
        return None
    dirty = set()
    fields = run.stdout.split("\0")
    index = 0
    while index < len(fields):
        entry = fields[index]
        index += 1
        if not entry:
            continue
        status, rel = entry[:2], entry[3:]
        dirty.add(os.path.realpath(os.path.join(cwd, rel)))
        if status[0] in ("R", "C"):
            index += 1  # the next field is the rename or copy source path, not a target
    return dirty


def collect_markdown_targets(cwd, baseline):
    """Return markdown files under cwd newer than baseline, first-seen order, deduplicated.

    In a git work tree, a file must also be dirty against HEAD to survive. Outside a git
    tree, or when git is missing or fails, the mtime check alone decides.
    """
    files = markdown_files_git(cwd)
    dirty = git_dirty_paths(cwd) if files is not None else None
    if files is None:
        files = markdown_files_walk(cwd)

    seen = []
    seen_set = set()
    for path in files:
        if path in seen_set:
            continue
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if mtime <= baseline:
            continue
        if dirty is not None and path not in dirty:
            continue
        seen_set.add(path)
        seen.append(path)
    return seen


# ------------------------------------------------------------------ project and readability checks

def _within_project(path, cwd):
    try:
        root = os.path.realpath(cwd)
    except Exception:
        return False
    return path == root or path.startswith(root + os.sep)


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

    baseline = parse_utc_timestamp(last_human_stamp(records))
    if baseline is None:
        return  # no timestamp on the last human record: no baseline, so no sweep

    cwd = hook.get("cwd") or ""
    if not isinstance(cwd, str) or not cwd:
        cwd = os.getcwd()
    if not os.path.isdir(cwd):
        return

    try:
        targets = collect_markdown_targets(cwd, baseline)
    except Exception:
        return
    if not targets:
        return

    # Fail open: a file outside the project, or a file this hook cannot read, is dropped here
    # and never reaches the linter or the block message.
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
