#!/usr/bin/env python3
"""Claude Code hook: ruling-home check (Stop).

`decisions/memory-is-never-a-rulings-only-home.md`, "The mechanism", names the defect this
closes: an orchestrator's auto-memory can hold an owner ruling that reaches no tracked file in
the repo. This hook is that mechanism. It matches that section's 9 numbered items exactly.

WHAT IT CHECKS. The memory folder is `<dirname(transcript_path)>/memory`. If that folder does
not exist, this hook does nothing. It keys on an ACT, not on prose
(`decisions/predicate-is-the-act.md`): a `.md` file in the folder (`MEMORY.md`, the index,
excepted) counts as written THIS SESSION when a `Write`, `Edit`, or `MultiEdit` tool use since
the last human message names it, OR a `Bash` tool use since the last human message names the
memory folder in its command text (item 1). All sessions of one project share the memory
folder, so a Bash-named file counts only when its own mtime is after the last human message: a
read does not change mtime, so `cat`/`ls` never blocks, and a peer session's write this session
never named never blocks either (item 2). A Bash command names the folder when its text holds
the folder's absolute path, its `~` form, or its `$HOME` form; a name it also holds is matched
as a whole path component, never a bare substring, so a write to `data.md` can never mark
`a.md` (item 3). A write through `cd` and a relative path, a shell variable, a script, or
`python -c` is out of this hook's reach on purpose (item 3).

Each written file is split into sections at its own `#` headings, a heading inside a fenced
code block (a line starting with ``` or ~~~ toggles the fence) is not a heading, and a file
with no heading is one section (item 4). A section with no non-blank line is skipped. Every
other section needs a `home:` line in its body (the key read case-insensitively, a line inside
a fence does not count); for the section before the first heading, a `home:` key in the YAML
frontmatter also counts (item 5). The value, unwrapped of one surrounding pair of backticks or
quotes, is `process-only` (exact case) or a repo-relative path to a FILE, never a directory,
that the tree of some branch holds now: refused outright if absolute, if it normalizes to `.`
or `..`, or if it leaves the repository tree; otherwise resolved by asking whether any local or
remote branch's tree holds a BLOB (never a tree) at that path right now (item 6). A brief does
not count: this hook only ever looks inside THIS repository's own tree (item 7). The hook
checks only that the value RESOLVES, never comparing text, so a paraphrase of an
already-recorded ruling cannot make it cry wolf (item 8;
`decisions/guard-that-cries-wolf-is-spent.md`): "A guard that goes red when nothing is wrong is
spent, because the reader learns to scroll past it."

RESOLUTION, ONE GIT PROCESS PER VALUE. `git for-each-ref` lists every `refs/heads` and
`refs/remotes` ref once per run; each home: value then asks about every ref at once with one
`git cat-file --batch-check` call fed `<ref>:<path>` lines on stdin, never one process per ref,
and reads the type back for each: only a `blob` answer resolves, so a directory (`tree`) never
does. Both calls run with `--literal-pathspecs`, so a value like `*` or `:(glob)**` is looked up
as a literal path, never expanded. A deleted path resolves through no ref.

WHAT IT DOES ON A MISS. Blocks once: `{"decision": "block", "reason": "..."}`, naming each
offending file and section heading and saying what a valid `home:` value is. The reason never
prints the bad value itself (CLAUDE.md, "a refusal's printed remedy never names the forbidden
target").

FAIL OPEN, NARROWLY (item 9). `stop_hook_active` set means this Stop firing is already a
rewrite, so the hook stays quiet. Otherwise it stands down (exit 0, no block) only for an
unreadable transcript, a missing `git` binary, a `git` call that times out, or a repository git
itself cannot read (`for-each-ref` exiting non-zero, e.g. a `.git` file pointing at a missing
gitdir): per `decisions/recovery-must-not-gate-on-its-own-state.md`, a recovery control (here,
the owner's own path to seeing a ruling was not filed) must not depend on the very state it is
meant to recover from. It never stands down over one value's own git answer (`cat-file
--batch-check` exiting non-zero, or simply answering "not a blob"): that value alone does not
resolve, and every other finding this turn still reports. `lint/_transcript.py`'s import is
deferred to inside `run()`, itself inside `main()`'s fail-open `try`, so a missing or broken
copy of that shared module also stands down rather than crashing the hook before `main()` can
catch anything.

Windows: paths are built with `os.path` throughout, and every path comparison runs
`os.path.normcase(os.path.normpath(...))` first, so a case-insensitive filesystem and a mixed
`/`/`\\` separator do not turn a real match into a miss. A resolved value is turned to `/`
before it reaches `git`, which wants POSIX-style tree paths on every platform.
"""
import json
import os
import re
import subprocess
import sys

MEMORY_DIRNAME = "memory"
INDEX_FILE = "MEMORY.md"
FILE_TOOLS = ("Write", "Edit", "MultiEdit")
GIT_TIMEOUT = 10
FENCE_MARKERS = ("```", "~~~")
WRAP_CHARS = ("`", '"', "'")
FS_NAME_CHAR = re.compile(r"[A-Za-z0-9_.\-]")

HOME_RE = re.compile(r"^\s*[-*]?\s*home:\s*(.+?)\s*$", re.IGNORECASE)
PROCESS_ONLY = "process-only"

REMEDY = (
    "Each written section needs a home: line, plain text, in the section body: "
    "process-only, or a repo-relative path some branch's tree holds now."
)

# Set by _ensure_transcript_helpers(), called at the top of run(). Kept as module globals so
# every other function below can call is_last_human/tool_uses/records_after_last_human/
# read_transcript as plain names, the same as if they had been imported at module load time --
# the only thing that changed is WHEN the import runs, so a missing lint/_transcript.py raises
# from inside run(), which main() already wraps in a fail-open try (see the module docstring).
is_last_human = None
tool_uses = None
records_after_last_human = None
read_transcript = None


def _ensure_transcript_helpers():
    global is_last_human, tool_uses, records_after_last_human, read_transcript
    if tool_uses is not None:
        return
    here = os.path.dirname(os.path.abspath(__file__))
    lint_dir = os.path.join(here, "..", "lint")
    if lint_dir not in sys.path:
        sys.path.insert(0, lint_dir)
    from _transcript import (
        is_last_human as _ilh, tool_uses as _tu,
        records_after_last_human as _rah, read_transcript as _rt,
    )
    is_last_human, tool_uses, records_after_last_human, read_transcript = _ilh, _tu, _rah, _rt


class _GitFailure(Exception):
    """`git` itself could not be trusted to answer, or the repository itself could not be
    read: the binary is missing, the call timed out, or `for-each-ref` -- a repository-wide
    listing, never a per-value lookup -- exited non-zero (item 9). The caller stands the whole
    check down. A plain non-zero exit from `cat-file --batch-check`, a per-VALUE lookup, is
    never this -- see value_resolves and the module docstring's FAIL OPEN section."""


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


# ------------------------------------------------------------------ written-this-session

def _folder_mentions(memory_dir):
    """Return the literal strings that count as "naming this folder" in a Bash command: the
    folder's absolute path, and, when it sits under the user's home directory, its `~` and
    `$HOME` forms (item 3)."""
    mentions = [memory_dir]
    home = os.environ.get("HOME") or os.path.expanduser("~")
    if not home or home == "~" or not os.path.isabs(home):
        return mentions
    home_norm = os.path.normpath(home)
    dir_norm = os.path.normpath(memory_dir)
    if dir_norm == home_norm:
        rest = ""
    elif dir_norm.startswith(home_norm + os.sep):
        rest = dir_norm[len(home_norm):]
    else:
        return mentions
    rest_posix = rest.replace(os.sep, "/")
    mentions.append("~" + rest_posix)
    mentions.append("$HOME" + rest_posix)
    return mentions


def _names_folder(cmd, memory_dir):
    return any(mention and mention in cmd for mention in _folder_mentions(memory_dir))


def _names_whole_component(cmd, name):
    """True when `name` appears in `cmd` as a whole path component: never preceded or
    followed by another filename character, so a write to `data.md` can never match `a.md`
    (item 3)."""
    start = 0
    while True:
        idx = cmd.find(name, start)
        if idx == -1:
            return False
        before = cmd[idx - 1] if idx > 0 else ""
        after = cmd[idx + len(name)] if idx + len(name) < len(cmd) else ""
        if not FS_NAME_CHAR.match(before) and not FS_NAME_CHAR.match(after):
            return True
        start = idx + 1


def _written_names(after_records, baseline, memory_dir, candidate_names):
    """Return the subset of `candidate_names` (memory-folder .md basenames) that THIS
    session's own tool uses wrote since the last human message.

    A Write/Edit/MultiEdit naming a file directly in `memory_dir` writes that one name,
    regardless of mtime. A Bash tool use whose command text names `memory_dir` (item 3) marks
    every candidate name its command text also names as a whole path component, or, when it
    names only the folder, every candidate name -- but a Bash-marked name counts only when its
    own mtime is after `baseline` (item 2): with no baseline at all, no Bash-marked name counts,
    the same narrow, never-guess direction as every other fail-open branch in this hook.
    """
    norm_dir = _norm(memory_dir)
    written = set()
    bash_marked = set()
    for rec in after_records:
        for tu in tool_uses(rec):
            name = tu.get("name")
            inp = tu.get("input") or {}
            if not isinstance(inp, dict):
                continue
            if name in FILE_TOOLS:
                target = inp.get("file_path") or inp.get("path")
                if not isinstance(target, str) or not target:
                    continue
                if _norm(os.path.dirname(target)) != norm_dir:
                    continue
                base = os.path.basename(target)
                if base in candidate_names:
                    written.add(base)
            elif name == "Bash":
                cmd = inp.get("command")
                if not isinstance(cmd, str) or not cmd:
                    continue
                if not _names_folder(cmd, memory_dir):
                    continue
                named = [n for n in candidate_names if _names_whole_component(cmd, n)]
                bash_marked.update(named if named else candidate_names)

    if baseline is not None:
        for name in bash_marked:
            full = os.path.join(memory_dir, name)
            try:
                if os.path.getmtime(full) > baseline:
                    written.add(name)
            except OSError:
                continue
    return written


# ------------------------------------------------------------------ sections, fence-aware

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


def _frontmatter_home(text):
    """Return the frontmatter's own `home:` value, or None: no opening/closing `---` pair,
    or no `home:` line between them."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    close_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            close_idx = i
            break
    if close_idx is None:
        return None
    for line in lines[1:close_idx]:
        m = HOME_RE.match(line)
        if m:
            return m.group(1)
    return None


def split_sections(text):
    """Return [(heading_line_or_None, [(line, in_fence), ...]), ...], split at lines
    starting with `#` -- except inside a fenced code block (a line starting with ``` or ~~~
    toggles the fence), where a `#` line is not a heading at all.

    A file with no heading is one section, heading None. Content before the first heading,
    when there is one, is its own heading-less section.
    """
    sections = []
    heading = None
    body = []
    in_fence = False
    for line in text.splitlines():
        if line.startswith(FENCE_MARKERS):
            in_fence = not in_fence
            body.append((line, True))
            continue
        if not in_fence and line.startswith("#"):
            if heading is not None or body:
                sections.append((heading, body))
            heading = line
            body = []
        else:
            body.append((line, in_fence))
    sections.append((heading, body))
    return sections


def _section_label(heading):
    return heading.lstrip("#").strip() if heading else "(no heading)"


def _unwrap(value):
    """Strip one matching pair of backticks or quotes wrapping `value`, else return it as is."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in WRAP_CHARS:
        return value[1:-1]
    return value


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


def _run_git(cwd, args, input_text=None):
    """Run one git call, `--literal-pathspecs` always set. Return the finished process.

    Raises _GitFailure only when git itself could not be trusted to answer at all: the binary
    is missing, or the call timed out. A plain non-zero exit is returned to the caller like
    any other result, never raised here -- see _list_refs and _resolve_value for which of
    those callers turns a non-zero exit into a stand-down and which reads it as "no answer".
    """
    try:
        return subprocess.run(
            ["git", "--literal-pathspecs", "-C", cwd] + args,
            input=input_text, capture_output=True, text=True, timeout=GIT_TIMEOUT,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise _GitFailure(str(exc)) from exc


def _list_refs(cwd):
    """Return every `refs/heads` and `refs/remotes` ref name.

    A non-zero exit here means the REPOSITORY itself could not be read (a `.git` file
    pointing at a missing gitdir, for one) -- item 9 names this as a stand-down, not a
    per-value miss, so it raises _GitFailure rather than returning an empty list.
    """
    run = _run_git(cwd, ["for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes"])
    if run.returncode != 0:
        raise _GitFailure("for-each-ref exited %s: %s" % (run.returncode, (run.stderr or "")[:200]))
    return [line for line in run.stdout.splitlines() if line.strip()]


def _resolve_value(cwd, refs, git_path):
    """True when ANY ref's tree holds a blob (never a tree/directory) at `git_path`.

    One `git cat-file --batch-check` call answers for every ref at once, fed `<ref>:<path>`
    lines on stdin, rather than one process per ref (the performance fix this exists for). A
    non-zero exit, or an object that batch-check reports missing or of any type but `blob`,
    reads as "this value does not resolve" -- never a stand-down: see the module docstring.
    """
    if not refs:
        return False
    stdin_text = "".join("%s:%s\n" % (ref, git_path) for ref in refs)
    run = _run_git(cwd, ["cat-file", "--batch-check"], input_text=stdin_text)
    if run.returncode != 0:
        return False
    for line in run.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[1] == "blob":
            return True
    return False


def value_resolves(value, cwd):
    """True when a home: value resolves. See the module docstring for what counts."""
    if value == PROCESS_ONLY:
        return True
    if os.path.isabs(value):
        return False  # every absolute path is refused, briefs included
    normalized = os.path.normpath(value)
    if normalized in (".", ".."):
        return False
    if normalized.startswith(".." + os.sep):
        return False  # leaves the repository tree
    if not cwd or not os.path.isdir(cwd) or not is_git_work_tree(cwd):
        return False
    git_path = normalized.replace(os.sep, "/")
    refs = _list_refs(cwd)  # a repo git cannot read raises _GitFailure: see _list_refs
    return _resolve_value(cwd, refs, git_path)


# ------------------------------------------------------------------ per-file check

def check_file(full_path, display_name, cwd):
    """Return [(display_name, section_label), ...] for each section of `full_path` that has
    no home: line, or whose home: value does not resolve."""
    with open(full_path, "r", encoding="utf-8") as f:
        text = f.read()
    frontmatter_home = _frontmatter_home(text)
    body_text = strip_frontmatter(text)
    findings = []
    for index, (heading, body) in enumerate(split_sections(body_text)):
        if not any(line.strip() for line, _fenced in body):
            continue
        home_value = frontmatter_home if (heading is None and index == 0) else None
        for line, fenced in body:
            if fenced:
                continue
            m = HOME_RE.match(line)
            if m:
                home_value = m.group(1)
                break
        if home_value is None:
            findings.append((display_name, _section_label(heading)))
            continue
        home_value = _unwrap(home_value.strip())
        if not value_resolves(home_value, cwd):
            findings.append((display_name, _section_label(heading)))
    return findings


# ------------------------------------------------------------------ orchestration

def run(hook):
    """Return a block reason string, or '' when there is nothing to report."""
    if hook.get("stop_hook_active"):
        return ""

    _ensure_transcript_helpers()

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

    candidate_names = find_memory_files(memory_dir)
    written = _written_names(after, baseline, memory_dir, candidate_names)

    findings = []
    for name in candidate_names:
        if name not in written:
            continue
        full = os.path.join(memory_dir, name)
        findings.extend(check_file(full, name, cwd))

    if not findings:
        return ""

    named = "; ".join("%s (%s)" % (name, label) for name, label in findings)
    return "Ruling home: this turn's memory names no tracked home for %s. %s" % (named, REMEDY)


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
        # An unreadable transcript, a missing git binary, a git timeout, a repository git
        # cannot read, or a missing lint/_transcript.py: exit 0, no block. See the module
        # docstring's FAIL OPEN section.
        sys.exit(0)

    if reason:
        print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


if __name__ == "__main__":
    main()
