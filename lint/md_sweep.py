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

Inside a changed file, it lints only the BLOCKS the diff against HEAD touched, not the whole
file. An untracked file, or one with no HEAD baseline, has nothing to diff against, so it
lints in full, same as before this scoping existed. See "SCOPING TO CHANGED BLOCKS" below.

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
4. Outside a git tree, mtime alone decides, from a plain filesystem walk. Inside one, a
   failed git call returns nothing at all, never mtime alone: see `collect_markdown_targets`.
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

SCOPING TO CHANGED BLOCKS.

A whole-file lint means editing one line forces fixing every pre-existing error in that
file. Once a file is clean, it also means adding a rule to ste_lint.py later breaks every
clean file at once, on the next turn that touches any one of them. Both costs come from
linting the whole file when only a part of it changed.

This hook instead lints only the BLOCKS `git diff HEAD --unified=0` marks changed. A block
is a paragraph, a run of lines bounded by blank lines. THE TRAP: STE001 is a sentence rule,
and a sentence can run over more than one source line. A finding is reported at the line the
sentence STARTS on. A plain line filter would drop a finding whose sentence starts outside
the diff but only crosses the word limit because of a later, changed line. Filtering by
block instead of by line closes that hole, because a sentence never crosses a blank line:
ste_lint.py's own `segment_markdown` flushes its paragraph at every blank line, the same unit
`paragraph_blocks` below reconstructs.

An untracked file, and a file with no HEAD baseline at all, such as one added and committed
in the same working tree state git diff can't reach, keeps no diff to scope by, so it lints
in full. A brand new file stays strict: every error in it still blocks.

A git diff call that fails, inside a real work tree, drops that one file from linting rather
than widening it back to the whole file. This mirrors the rule `collect_markdown_targets`
already applies to its own git failures: never widen scope on an error, only narrow it.
"""
import json
import os
import re
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
    `node_modules`, build output, and anything else the repository's own `.gitignore` names,
    with no separate skip list to keep in step with it.
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


def git_status_entries(cwd):
    """Return {absolute path: 2-char porcelain status} from `git status --porcelain`, or None.

    Returns None when the command fails, for the caller to read against `is_git_work_tree`.
    The 2-char code is git's own, `??` for untracked. A rename or a copy entry carries a
    second, NUL-separated field for its old path, which is consumed and dropped here, never
    counted as a target on its own.
    """
    run = _run_git(cwd, ["status", "--porcelain", "-z", "--untracked-files=all", "--", "."])
    if run is None or run.returncode != 0:
        return None
    entries = {}
    fields = run.stdout.split("\0")
    index = 0
    while index < len(fields):
        entry = fields[index]
        index += 1
        if not entry:
            continue
        status, rel = entry[:2], entry[3:]
        entries[os.path.realpath(os.path.join(cwd, rel))] = status
        if status[0] in ("R", "C"):
            index += 1  # the next field is the rename or copy source path, not a target
    return entries


def git_dirty_paths(cwd):
    """Return the absolute paths `git status --porcelain` marks dirty against HEAD, or None.

    A thin view over `git_status_entries`, kept for the callers that only need membership,
    never the status code itself.
    """
    entries = git_status_entries(cwd)
    return None if entries is None else set(entries)


def collect_markdown_targets(cwd, baseline):
    """Return (targets, status_entries): the markdown files under cwd newer than baseline,
    first-seen order and deduplicated, plus the git status entries used to filter them.

    Outside a git work tree, a plain filesystem walk and the mtime check alone decide, and
    `status_entries` is None: there is no git status to hand back, and the caller reads that
    None as "no git baseline at all", the same signal it uses to skip block-scoping and lint
    a survivor in full.

    Inside a work tree, git decides both the file list and the dirty filter, and a failure of
    either git call returns no targets. It never widens to the walk. The hook's own SCOPE
    promise, an old file with old errors is not this turn's debt, holds only while the
    dirty filter runs. Falling back to the walk would break that promise to keep the mtime
    check alive. Doing nothing keeps both. A stale `index.lock` left by a concurrent agent
    in a shared checkout is one real way this branch fires, and it must not turn into a
    false block. On that failure `status_entries` is also None, but the caller never reaches
    it: an empty target list returns before block-scoping runs at all.
    """
    if not is_git_work_tree(cwd):
        return _newer_than(markdown_files_walk(cwd), None, baseline), None

    files = markdown_files_git(cwd)
    entries = git_status_entries(cwd) if files is not None else None
    dirty = set(entries) if entries is not None else None
    if files is None or dirty is None:
        return [], None
    return _newer_than(files, dirty, baseline), entries


def _newer_than(files, dirty, baseline):
    """Filter `files` to those newer than `baseline`, and dirty when `dirty` is given.

    `dirty`, a set or None, is the git dirty-path filter. None means skip it, the plain
    mtime-only path this function shares with the git path.
    """
    seen = []
    seen_set = set()
    for path in files:
        if path in seen_set:
            continue
        # A vanished path, deleted mid-turn, is dropped here rather than crashing the walk.
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


# ------------------------------------------------------------------ scoping to changed blocks
#
# See "SCOPING TO CHANGED BLOCKS" in the module docstring for why this lints blocks, not
# lines, and what a git failure here does.

HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


class _DropFile:
    """Sentinel: the git diff call for this file failed. The caller drops the file rather
    than widen it back to a whole-file lint."""


DROP_FILE = _DropFile()


def paragraph_blocks(text):
    """Return (start_line, end_line) 1-indexed ranges, one per run of non-blank lines.

    A block is a paragraph: lines bounded by blank lines. A blank line is one that is empty
    or holds only whitespace. This is the same unit ste_lint.py's own `segment_markdown`
    flushes a paragraph at, which is why a multi-line STE001 sentence, reported at the line
    it starts on, always lands inside the one block its later lines also belong to.
    """
    lines = text.split("\n")
    blocks = []
    start = None
    for i, line in enumerate(lines, start=1):
        if line.strip() == "":
            if start is not None:
                blocks.append((start, i - 1))
                start = None
        elif start is None:
            start = i
    if start is not None:
        blocks.append((start, len(lines)))
    return blocks


def git_diff_changed_lines(cwd, path):
    """Return the 1-indexed lines of `path` ON DISK that `git diff HEAD --unified=0` marks
    changed, or None when the git call itself fails.

    `--unified=0` keeps a hunk header the only output for that hunk, so no untouched context
    line is ever mistaken for a changed one. A pure deletion hunk has a new-side count of 0:
    nothing was added, and its line number instead marks the point the deletion sits at. Both
    the line before and the line after that point are counted as changed, so the block on
    either side of a deleted line is still caught, whichever side the reported line prefers.
    """
    # `path` is always a realpath (see `_newer_than`), while `cwd` comes straight from the
    # hook JSON and can hold a symlinked component, macOS's /tmp for one. relpath against the
    # raw cwd would then walk back out through the realpath's own directories and land
    # outside the repository. Resolving cwd first keeps both sides in the same form.
    rel = os.path.relpath(path, os.path.realpath(cwd))
    run = _run_git(cwd, ["diff", "HEAD", "--unified=0", "--", rel])
    if run is None or run.returncode != 0:
        return None
    changed = set()
    for line in run.stdout.splitlines():
        m = HUNK_RE.match(line)
        if not m:
            continue
        new_start = int(m.group(1))
        new_count = int(m.group(2)) if m.group(2) is not None else 1
        if new_count == 0:
            changed.add(max(new_start, 1))
            changed.add(new_start + 1)
        else:
            changed.update(range(new_start, new_start + new_count))
    return changed


def scope_for(cwd, path, untracked):
    """Return the lines of `path` in scope for linting.

    None means lint the whole file: `untracked` is True, so git has no baseline to diff
    against. DROP_FILE means the git diff call failed: drop the file rather than widen to the
    whole file, the same fail-closed rule `collect_markdown_targets` already applies to its
    own git failures. Otherwise, a set of the lines every touched block spans.
    """
    if untracked:
        return None
    changed = git_diff_changed_lines(cwd, path)
    if changed is None:
        return DROP_FILE
    if not changed:
        return set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return DROP_FILE
    in_scope = set()
    for start, end in paragraph_blocks(text):
        if any(n in changed for n in range(start, end + 1)):
            in_scope.update(range(start, end + 1))
    return in_scope


# ------------------------------------------------------------------ linting from disk

def lint_files(paths, exclude):
    """Return {path: [finding dict]} for the error-level findings of ste_lint.py on paths.

    Every path here was already checked to exist and to be readable. That check runs before
    this call, not during it. If a path vanishes in the gap between the two, ste_lint.py
    exits 2 with no JSON on stdout at all, and this function then returns an empty result
    for every path in the batch, not only the one that vanished. The `except Exception`
    below catches that empty-stdout case along with a timeout or a crash, all as one
    silent, fail-open miss.
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
        by_path.setdefault(f.get("path"), []).append(f)
    return by_path


def format_finding(f):
    return "line %s: %s %s" % (f.get("line"), f.get("code"), f.get("message"))


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
        targets, status_entries = collect_markdown_targets(cwd, baseline)
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

    # SCOPING. status_entries is None only when cwd is not a git work tree at all (a git
    # failure inside a work tree already returned above, with an empty target list). With no
    # git baseline to diff against, every survivor lints in full, the rule this hook already
    # had before block-scoping existed. Inside a work tree, each survivor gets its own scope:
    # None (untracked, lint in full), DROP_FILE (its git diff call failed, skip it), or the
    # set of lines its changed blocks span.
    scopes = {}
    for resolved in readable:
        if status_entries is None:
            scopes[resolved] = None
        else:
            untracked = status_entries.get(resolved, "")[:2] == "??"
            try:
                scopes[resolved] = scope_for(cwd, resolved, untracked)
            except Exception:
                scopes[resolved] = DROP_FILE

    lintable = [p for p in readable if scopes[p] is not DROP_FILE]
    if not lintable:
        return

    exclude = os.environ.get(EXCLUDE_VAR, "")
    by_path = lint_files(lintable, exclude)
    if not by_path:
        return

    lines = []
    for resolved in lintable:
        findings = by_path.get(resolved)
        if not findings:
            continue
        scope = scopes[resolved]
        if scope is not None:
            findings = [f for f in findings if f.get("line") in scope]
        if not findings:
            continue
        lines.append("%s:" % os.path.basename(resolved))
        lines.extend("  " + format_finding(f) for f in findings)
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
