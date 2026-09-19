#!/usr/bin/env python3
"""Claude Code hook: markdown sweep (Stop).

THE DEFECT THIS CLOSES. The PreToolUse STE gate (ste_gate.py) only sees a Write, Edit, or
MultiEdit call on a *.md path. A markdown file written through Bash never passes through
that gate. The earlier version of this hook chased the hole by matching SHAPES in the Bash
command text. It looked for a heredoc, a `>` redirect, `sed -i`, a `python -c` string, and
more. That list can only grow, never finish. `python3 gen.py`, `bash gen.sh`,
`pandoc -o notes.md`, and `make docs` were all invisible to it. The hole is the class
"any program not on the list," not one shape.

This hook now checks the ACT, not the command shape. A file counts when it is markdown under
`cwd`, and its mtime is newer than this turn's last human message. In a git work tree it
must also be dirty against HEAD. It never reads a command string.

SEVERITY. This hook blocks the turn once when it finds an error, the same severity as the
PreToolUse gate. A gate a lane can skip by picking another tool is not a gate.

SCOPE. This hook lints only the markdown files this turn changed, whatever tool wrote them.
It reads the last human message's timestamp from the transcript, the way
hooks/config_report.py reads that same field for its own turn boundary.
It never scans the whole repository. An old file with old errors is not this turn's debt.

Reads the hook JSON on stdin. Always exits 0. Fails open on bad input, a missing transcript,
or a parse error. It also fails open on a missing file, a file outside the project, or a
file this hook cannot read. A hook must never brick a session.

Off switch: set MD_SWEEP_DISABLE to any non-empty value. The sweep then does nothing at all.

Exclude: set MD_SWEEP_EXCLUDE to a comma-separated list of glob patterns. Each pattern goes
straight to ste_lint.py's own `--exclude` flag. A generated report can then name its own
path, or a glob for its folder, from the shell, with no edit to this repo.

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

A file this turn wrote can end up matching HEAD exactly. This happens when a later edit
undoes an earlier one in the same turn. That match reads as clean against HEAD. The git
filter drops the file, even though this turn did touch it.

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
    # A sidechain record is a sub-agent's own turn.
    if rec.get("type") != "user":
        return False
    if rec.get("isSidechain"):
        return False
    # Plain text content is always a human message.
    msg = rec.get("message") or {}
    content = msg.get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        # A tool result reads as the assistant's own turn continuing.
        has_text = any(isinstance(b, dict) and b.get("type") == "text" for b in content)
        # Checked separately from the text block above.
        has_tool_result = any(
            isinstance(b, dict) and b.get("type") == "tool_result" for b in content
        )
        # Text with no tool result is the human's own words.
        return has_text and not has_tool_result
    return False


def read_transcript(path):
    # One JSON object per line.
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            # A blank line carries nothing to parse.
            line = line.strip()
            if not line:
                continue
            # A line that fails to parse is skipped, not fatal.
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


def is_git_work_tree(cwd):
    """Return True when cwd is inside a git work tree, found on disk alone.

    This never runs git. It walks upward from cwd for a `.git` entry, a directory for an
    ordinary checkout or a file for a worktree or a submodule. A broken `GIT_DIR`, or any
    other reason the git BINARY itself might fail, cannot corrupt this answer. That failure
    mode is exactly the case this check exists to separate from "not a work tree at all".
    """
    current = os.path.realpath(cwd)
    while True:
        if os.path.exists(os.path.join(current, ".git")):
            return True
        parent = os.path.dirname(current)
        if parent == current:
            return False
        current = parent


def markdown_files_git(cwd):
    """Return absolute markdown paths under cwd, from git's own file listing, or None.

    Covers tracked files and untracked files git does not ignore, scoped to cwd's own
    subtree with the trailing `-- .` pathspec. Returns None when the command fails, for the
    caller to read against `is_git_work_tree`. This listing already skips `.git`,
    `node_modules`, build output, and anything else the repository's own `.gitignore`
    names. There is no separate skip list to keep in step with it.
    """
    # A non-zero exit reads as a failure, not an empty repository.
    run = _run_git(cwd, ["ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "."])
    if run is None or run.returncode != 0:
        return None
    # NUL-separated relative paths, filtered to the two markdown suffixes this hook covers.
    paths = []
    for rel in run.stdout.split("\0"):
        if rel and rel.lower().endswith(MD_SUFFIXES):
            paths.append(os.path.realpath(os.path.join(cwd, rel)))
    return paths


def markdown_files_walk(cwd):
    """Return absolute markdown paths under cwd, from a plain filesystem walk.

    Used only when `is_git_work_tree(cwd)` is False. A git failure inside a real work tree
    does NOT fall back here. Skips `.git`, `node_modules`, and every other dot-directory, so
    the walk never descends into a huge generated or vendored tree a real turn never touches.
    """
    paths = []
    for root, dirs, files in os.walk(cwd):
        dirs[:] = [d for d in dirs if d not in SKIP_DIR_NAMES and not d.startswith(".")]
        for name in files:
            if name.lower().endswith(MD_SUFFIXES):
                paths.append(os.path.realpath(os.path.join(root, name)))
    return paths


def git_dirty_paths(cwd):
    """Return the absolute paths `git status --porcelain` marks dirty against HEAD, or None.

    Returns None when the command fails, for the caller to read against `is_git_work_tree`.
    A rename or a copy entry carries a second, NUL-separated field for its old path. That
    field is consumed and dropped here, never counted as a dirty target on its own.
    """
    # A non-zero exit reads as a failure, never as an empty result.
    run = _run_git(cwd, ["status", "--porcelain", "-z", "--untracked-files=all", "--", "."])
    # No result and a bad exit code both mean the same thing here.
    if run is None or run.returncode != 0:
        return None
    # Walk the NUL-separated fields by hand.
    dirty = set()
    fields = run.stdout.split("\0")
    index = 0
    while index < len(fields):
        entry = fields[index]
        index += 1
        # A trailing empty field ends the list.
        if not entry:
            continue
        # The status is the first two characters, the path is the rest.
        status, rel = entry[:2], entry[3:]
        dirty.add(os.path.realpath(os.path.join(cwd, rel)))
        # A rename or a copy status consumes one extra field, the old path.
        if status[0] in ("R", "C"):
            index += 1
    return dirty


def collect_markdown_targets(cwd, baseline):
    """Return markdown files under cwd newer than baseline, first-seen order, deduplicated.

    Outside a git work tree, a plain filesystem walk and the mtime check alone decide.
    Inside one, git decides both the file list and the dirty filter, and a failure of
    either git call returns no targets. It never widens to the walk. The hook's own SCOPE
    promise, an old file with old errors is not this turn's debt, holds only while the
    dirty filter runs. Falling back to the walk would break that promise to keep the mtime
    check alive. Doing nothing keeps both. A stale `index.lock` left by a concurrent agent in
    a shared checkout is one real way this branch fires. It must not turn into a false block.
    """
    if not is_git_work_tree(cwd):
        return _newer_than(markdown_files_walk(cwd), None, baseline)

    files = markdown_files_git(cwd)
    dirty = git_dirty_paths(cwd) if files is not None else None
    if files is None or dirty is None:
        return []
    return _newer_than(files, dirty, baseline)


def _newer_than(files, dirty, baseline):
    """Filter `files` to those newer than `baseline`, and dirty when `dirty` is given.

    `dirty`, a set or None, is the git dirty-path filter. None means skip it, the plain
    mtime-only path this function shares with the git path.
    """
    seen = []
    seen_set = set()
    for path in files:
        # A duplicate path, seen once already, is skipped.
        if path in seen_set:
            continue
        # A vanished path, deleted mid-turn, is dropped rather than crashing the walk.
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if mtime <= baseline:
            continue
        # The git dirty filter, when given, is the last check.
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

    Every path here was already checked to exist and to be readable. That check runs before
    this call, not during it. A path can still vanish in the gap between the two. When one
    does, ste_lint.py exits 2 with no JSON on stdout at all. This function then returns an
    empty result for every path in the batch, not only the one that vanished. The
    `except Exception` below catches that empty-stdout case, along with a timeout or a
    crash, all as one silent, fail-open miss.
    """
    # An absent linter, or an empty path list, has nothing to run.
    if not os.path.exists(LINTER) or not paths:
        return {}
    # Build the command line: error severity, JSON output, never a nonzero exit.
    cmd = [sys.executable, LINTER, "--no-color", "--format", "json", "--fail-on", "never"]
    # An exclude glob, when given, is ste_lint.py's own flag, added last.
    if exclude:
        cmd += ["--exclude", exclude]
    cmd += paths
    # A timeout, a crash, or bad JSON all read as one fail-open miss.
    try:
        run = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        data = json.loads(run.stdout or "{}")
    except Exception:
        return {}
    # Keep only the error-severity findings, grouped by their own path.
    by_path = {}
    for f in data.get("findings", []):
        if f.get("severity") != "error":
            continue
        by_path.setdefault(f.get("path"), []).append(
            "line %s: %s %s" % (f.get("line"), f.get("code"), f.get("message")))
    return by_path


def main():
    # Bad JSON on stdin ends the hook.
    try:
        hook = json.load(sys.stdin)
    except Exception:
        return
    # So does a JSON value that is not an object.
    if not isinstance(hook, dict):
        return
    # The wrong event, a rewrite already in flight, or the off switch, all end the hook too.
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

    # Fail open: a file outside the project is dropped here. So is one this hook cannot
    # read. Neither reaches the linter or the block message.
    readable = []
    for resolved in targets:
        # A path outside cwd, from a symlink, or one no longer a plain file, is dropped.
        try:
            if not _within_project(resolved, cwd):
                continue
            if not os.path.isfile(resolved):
                continue
            # A cheap read probe: it raises on a permission or a decode problem.
            with open(resolved, "r", encoding="utf-8") as f:
                f.read(0)
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
