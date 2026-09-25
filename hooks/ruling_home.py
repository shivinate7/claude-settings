#!/usr/bin/env python3
"""Claude Code hook: ruling-home check (Stop).

`decisions/memory-is-never-a-rulings-only-home.md`, "The mechanism", names the defect this
closes: an orchestrator's auto-memory can hold an owner ruling that reaches no tracked file in
the repo. This hook is that mechanism.

WHAT IT CHECKS. The memory folder is `<dirname(transcript_path)>/memory`, the folder Claude
Code's own auto-memory keeps beside the session's transcript. If that folder does not exist,
this hook does nothing. It keys on an ACT, not on prose (`decisions/predicate-is-the-act.md`):
a `.md` file in that folder (`MEMORY.md`, the index, excepted) counts as written THIS TURN when
a `Write`, `Edit`, or `MultiEdit` tool use since the last human message names it, or its mtime
is newer than that message. Frontmatter stripped, each written file is split into sections at
its own `#` headings (a file with no heading is one section). A section with no non-blank line
is skipped. Every other section needs one `home:` line (the key read case-insensitively) whose
value is `process-only`, an absolute path to a file that exists, or a repo-relative path some
git ref holds (`git -C <cwd> log --all -1 --format=%h -- <path>`, non-empty). The hook checks
only that the value RESOLVES. It never compares text, so a paraphrase of an already-recorded
ruling cannot make it cry wolf (`decisions/guard-that-cries-wolf-is-spent.md`): "A guard that
goes red when nothing is wrong is spent, because the reader learns to scroll past it."

WHAT IT DOES ON A MISS. Blocks once: `{"decision": "block", "reason": "..."}`, naming each
offending file and section heading and saying what a valid `home:` value is. The reason never
prints the bad value itself (CLAUDE.md, "a refusal's printed remedy never names the forbidden
target").

FAIL OPEN. `stop_hook_active` set means this Stop firing is already a rewrite, so the hook
stays quiet. Any error reading the transcript or running git also exits 0 with no block:
per `decisions/recovery-must-not-gate-on-its-own-state.md`, a recovery control (here, the
owner's own path to seeing a ruling was not filed) must not depend on the very state it is
meant to recover from. A hook that blocks on its own read failure would brick the turn on the
one kind of turn -- an unreadable transcript or a broken git call -- where the owner most needs
the turn to still end.

Windows: paths are built with `os.path` throughout, and every path comparison runs
`os.path.normcase(os.path.normpath(...))` first, so a case-insensitive filesystem and a mixed
`/`/`\\` separator do not turn a real match into a miss.
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LINT_DIR = os.path.join(HERE, "..", "lint")
sys.path.insert(0, LINT_DIR)
from _transcript import is_last_human, tool_uses, records_after_last_human, read_transcript  # noqa: E402

# is_last_human, tool_uses, records_after_last_human, and read_transcript live in
# lint/_transcript.py, imported above, the same shared reader hooks/config_report.py and the
# lint/*_gate.py modules already use.

MEMORY_DIRNAME = "memory"
INDEX_FILE = "MEMORY.md"
FILE_TOOLS = ("Write", "Edit", "MultiEdit")
GIT_TIMEOUT = 10

HOME_RE = re.compile(r"^\s*[-*]?\s*home:\s*(.+?)\s*$", re.IGNORECASE)
PROCESS_ONLY = "process-only"

REMEDY = (
    "Each written section needs a home: line: %r, an absolute path to an existing file, or a "
    "repo-relative path some git ref holds." % PROCESS_ONLY
)


class _GitFailure(Exception):
    """A git call this hook needed could not be trusted (missing binary, timeout, or a
    non-zero exit from a repo already confirmed to exist). The caller aborts the whole check
    silently rather than guessing whether a home: value resolves. See the module docstring's
    FAIL OPEN section."""


def _norm(path):
    return os.path.normcase(os.path.normpath(path))


def _parse_utc_timestamp(text):
    from datetime import datetime, timezone
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


def _last_human_baseline(records):
    stamp = ""
    for rec in records:
        if is_last_human(rec):
            value = rec.get("timestamp") or ""
            stamp = value if isinstance(value, str) else ""
    return _parse_utc_timestamp(stamp)


# ------------------------------------------------------------------ which memory files exist

def find_memory_files(memory_dir):
    """Return the `.md` basenames directly under `memory_dir`, sorted, MEMORY.md excluded."""
    out = []
    for name in sorted(os.listdir(memory_dir)):
        if name == INDEX_FILE:
            continue
        if not name.lower().endswith(".md"):
            continue
        full = os.path.join(memory_dir, name)
        if os.path.isfile(full):
            out.append(name)
    return out


# ------------------------------------------------------------------ written-this-turn

def _written_targets(after_records, memory_dir):
    """Return the normalized paths a Write/Edit/MultiEdit tool use named directly inside
    `memory_dir`, since the last human message."""
    norm_dir = _norm(memory_dir)
    targets = set()
    for rec in after_records:
        for tu in tool_uses(rec):
            if tu.get("name") not in FILE_TOOLS:
                continue
            inp = tu.get("input") or {}
            if not isinstance(inp, dict):
                continue
            target = inp.get("file_path") or inp.get("path")
            if not isinstance(target, str) or not target:
                continue
            if _norm(os.path.dirname(target)) == norm_dir:
                targets.add(_norm(target))
    return targets


def _was_written_this_turn(full_path, written_targets, baseline):
    if _norm(full_path) in written_targets:
        return True
    if baseline is None:
        return False
    try:
        return os.path.getmtime(full_path) > baseline
    except OSError:
        return False


# ------------------------------------------------------------------ sections

def strip_frontmatter(text):
    """Return `text` with a leading `---`/`---` YAML block removed. Text with no opening
    `---` on its first line, or no closing `---` at all, is returned unchanged."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[i + 1:])
    return text


def split_sections(text):
    """Return [(heading_line_or_None, body_lines)], split at lines starting with `#`.

    A file with no heading is one section, heading None. Content before the first heading,
    when there is one, is its own heading-less section.
    """
    sections = []
    heading = None
    body = []
    for line in text.splitlines():
        if line.startswith("#"):
            if heading is not None or body:
                sections.append((heading, body))
            heading = line
            body = []
        else:
            body.append(line)
    sections.append((heading, body))
    return sections


def _section_label(heading):
    return heading.lstrip("#").strip() if heading else "(no heading)"


# ------------------------------------------------------------------ resolving a home: value

def is_git_work_tree(path):
    current = os.path.realpath(path)
    while True:
        if os.path.exists(os.path.join(current, ".git")):
            return True
        parent = os.path.dirname(current)
        if parent == current:
            return False
        current = parent


def _run_git(cwd, args):
    try:
        run = subprocess.run(
            ["git", "-C", cwd] + args, capture_output=True, text=True, timeout=GIT_TIMEOUT,
        )
    except Exception as exc:
        raise _GitFailure(str(exc)) from exc
    if run.returncode != 0:
        raise _GitFailure("git exited %s: %s" % (run.returncode, (run.stderr or "")[:200]))
    return run.stdout


def value_resolves(value, cwd):
    """True when a home: value resolves. See the module docstring for the three shapes."""
    value = value.strip()
    if value == PROCESS_ONLY:
        return True
    if os.path.isabs(value):
        return os.path.isfile(value)
    if not cwd or not os.path.isdir(cwd) or not is_git_work_tree(cwd):
        return False  # not a git repo: a relative path never resolves, per the brief
    stdout = _run_git(cwd, ["log", "--all", "-1", "--format=%h", "--", value])
    return bool(stdout.strip())


# ------------------------------------------------------------------ per-file check

def check_file(full_path, display_name, cwd):
    """Return [(display_name, section_label), ...] for each section of `full_path` that has
    no home: line, or whose home: value does not resolve."""
    with open(full_path, "r", encoding="utf-8") as f:
        text = f.read()
    text = strip_frontmatter(text)
    findings = []
    for heading, body in split_sections(text):
        if not any(line.strip() for line in body):
            continue
        home_value = None
        for line in body:
            m = HOME_RE.match(line)
            if m:
                home_value = m.group(1)
                break
        if home_value is None or not value_resolves(home_value, cwd):
            findings.append((display_name, _section_label(heading)))
    return findings


# ------------------------------------------------------------------ orchestration

def run(hook):
    """Return a block reason string, or '' when there is nothing to report."""
    if hook.get("stop_hook_active"):
        return ""

    path = hook.get("transcript_path")
    if not path or not isinstance(path, str) or not os.path.exists(path):
        return ""

    memory_dir = os.path.join(os.path.dirname(path), MEMORY_DIRNAME)
    if not os.path.isdir(memory_dir):
        return ""

    records = read_transcript(path)
    after = records_after_last_human(records)
    baseline = _last_human_baseline(records)

    cwd = hook.get("cwd") or ""
    if not isinstance(cwd, str):
        cwd = ""

    written_targets = _written_targets(after, memory_dir)

    findings = []
    for name in find_memory_files(memory_dir):
        full = os.path.join(memory_dir, name)
        if not _was_written_this_turn(full, written_targets, baseline):
            continue
        findings.extend(check_file(full, name, cwd))

    if not findings:
        return ""

    named = "; ".join("%s (%s)" % (name, label) for name, label in findings)
    return (
        "Ruling home: this turn's memory names no tracked home for %s. %s"
        % (named, REMEDY)
    )


def main():
    try:
        hook = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if not isinstance(hook, dict):
        sys.exit(0)

    try:
        reason = run(hook)
    except Exception:
        # Any error reading the transcript or running git: exit 0, no block. See the module
        # docstring's FAIL OPEN section.
        sys.exit(0)

    if reason:
        print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


if __name__ == "__main__":
    main()
