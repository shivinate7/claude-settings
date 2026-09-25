#!/usr/bin/env python3
"""Read-only counter for where a ruling lands: memory, scratchpad, or a tracked file.

See decisions/memory-is-never-a-rulings-only-home.md (on branch claude/ruling-home) for the
finding this counts. It reads Claude Code transcripts under a projects root. It writes no
file and makes no network call. Its only outside call is a local `git log`, per repo, to run
the reach test.

Run it from the repository root:

    python3 lint/ruling_census.py
    python3 lint/ruling_census.py --root ~/.claude/projects --since 2026-09-01
    python3 lint/ruling_census.py --json

Columns: project, sessions, answers, memory writes, scratchpad writes, "ruling" lines,
process-only lines, reach found, reach not found, unknown.

A "session" is one `*.jsonl` file directly inside a project folder. A file nested deeper
(for example under a project folder's own `subagents/`) is a child transcript of that
session, not a second session.

The reach test takes each memory-write line and each AskUserQuestion answer with 8 or more
words, collapses its whitespace, and asks `git log --all -S<text>` in the transcript's own
`cwd`. A "not found" is a verbatim miss, not proof that a ruling was lost: the same idea in
different words, a paraphrase, or a squashed commit all read as "not found" here.

Two assumptions this script makes, because the source data does not spell them out:
  - "contains the word ruling" is read as a case-insensitive substring, so it also
    catches "rulings" and "overruling".
  - `--since` filters by a transcript's file mtime, not by a timestamp field inside it,
    since only some record types carry one.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _transcript import read_transcript, tool_uses  # noqa: E402

GIT_TIMEOUT_SECONDS = 10
REACH_WORD_MIN = 8
MEMORY_WRITE_NAMES = ("Write", "Edit", "MultiEdit")

ASK_ANSWER_RE = re.compile(r'"([^"]*)"="([^"]*)"')
PROCESS_ONLY_RE = re.compile(r"^\s*home:\s*process-only\s*$", re.IGNORECASE)

COLUMNS = (
    "project", "sessions", "answers", "memory writes", "scratchpad writes",
    '"ruling" lines', "process-only lines", "reach found", "reach not found", "unknown",
)
COUNT_KEYS = (
    "sessions", "answers", "memory_writes", "scratchpad_writes", "ruling_lines",
    "process_only_lines", "reach_found", "reach_not_found", "unknown",
)

NOT_FOUND_NOTE = 'a "not found" is a verbatim miss, not proof that a ruling was lost.'


def default_root():
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    return os.path.join(base, "projects")


def zero_counts():
    return {k: 0 for k in COUNT_KEYS}


def add_counts(into, other):
    for k in COUNT_KEYS:
        into[k] += other[k]


def _strings(value):
    """Yield every string value nested inside a tool_use `input`, dict or list."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def is_scratchpad_tool_use(block):
    inp = block.get("input") or {}
    return any("/scratchpad/" in s for s in _strings(inp))


def memory_write_texts(block, project_dir):
    """Return the list of new-text strings a memory write puts on disk, or None if `block`
    is not a Write/Edit/MultiEdit tool use under `project_dir`'s own memory/ folder.
    """
    name = block.get("name")
    if name not in MEMORY_WRITE_NAMES:
        return None
    inp = block.get("input") or {}
    file_path = inp.get("file_path")
    if not file_path:
        return None
    norm = file_path.replace("\\", "/")
    prefix = os.path.normpath(project_dir).replace("\\", "/") + "/memory/"
    if not norm.startswith(prefix):
        return None
    if name == "Write":
        return [inp.get("content") or ""]
    if name == "Edit":
        return [inp.get("new_string") or ""]
    texts = []
    for edit in inp.get("edits") or []:
        if isinstance(edit, dict):
            texts.append(edit.get("new_string") or "")
    return texts


def tool_results(rec):
    msg = rec.get("message") or {}
    content = msg.get("content")
    if not isinstance(content, list):
        return
    for b in content:
        if isinstance(b, dict) and b.get("type") == "tool_result":
            yield b


def result_text(block):
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [c.get("text") or "" for c in content
                 if isinstance(c, dict) and c.get("type") == "text"]
        return "\n".join(parts)
    return ""


def assistant_texts(rec):
    if rec.get("type") != "assistant":
        return
    msg = rec.get("message") or {}
    content = msg.get("content")
    if not isinstance(content, list):
        return
    for b in content:
        if isinstance(b, dict) and b.get("type") == "text":
            yield b.get("text") or ""


def find_cwd(records):
    for rec in records:
        cwd = rec.get("cwd")
        if cwd:
            return cwd
    return None


def reach_words(text):
    return len(text.split())


def reach_test(cwd, text, timeouts):
    """Return "found", "not_found", or "unknown". `timeouts` is a one-item counter list,
    bumped on a per-item git timeout so the caller can report how many items timed out.
    """
    if not cwd:
        return "unknown"
    collapsed = " ".join(text.split())
    if not collapsed:
        return "unknown"
    try:
        run = subprocess.run(
            ["git", "-C", cwd, "log", "--all", "-S", collapsed, "-1", "--format=%h"],
            capture_output=True, text=True, timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        timeouts[0] += 1
        return "unknown"
    except OSError:
        return "unknown"
    if run.returncode != 0:
        return "unknown"
    return "found" if run.stdout.strip() else "not_found"


def scan_memory_folder(project_dir):
    """Count `home: process-only` lines across the project's current memory files."""
    memory_dir = os.path.join(project_dir, "memory")
    if not os.path.isdir(memory_dir):
        return 0
    count = 0
    for dirpath, _dirs, files in os.walk(memory_dir):
        for name in files:
            path = os.path.join(dirpath, name)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
            except OSError:
                continue
            for line in text.splitlines():
                if PROCESS_ONLY_RE.match(line):
                    count += 1
    return count


def scan_transcript(path, project_dir, timeouts):
    counts = zero_counts()
    counts["sessions"] = 1
    records = read_transcript(path)
    cwd = find_cwd(records)

    ask_ids = set()
    for rec in records:
        for block in tool_uses(rec):
            if block.get("name") == "AskUserQuestion":
                ask_ids.add(block.get("id"))
            if is_scratchpad_tool_use(block):
                counts["scratchpad_writes"] += 1
            mem_texts = memory_write_texts(block, project_dir)
            if mem_texts is not None:
                counts["memory_writes"] += 1
                for text in mem_texts:
                    for line in text.splitlines():
                        if reach_words(line) >= REACH_WORD_MIN:
                            verdict = reach_test(cwd, line, timeouts)
                            if verdict == "found":
                                counts["reach_found"] += 1
                            elif verdict == "not_found":
                                counts["reach_not_found"] += 1
                            else:
                                counts["unknown"] += 1
        for block in tool_results(rec):
            if block.get("tool_use_id") not in ask_ids:
                continue
            text = result_text(block)
            for _question, answer in ASK_ANSWER_RE.findall(text):
                counts["answers"] += 1
                if reach_words(answer) >= REACH_WORD_MIN:
                    verdict = reach_test(cwd, answer, timeouts)
                    if verdict == "found":
                        counts["reach_found"] += 1
                    elif verdict == "not_found":
                        counts["reach_not_found"] += 1
                    else:
                        counts["unknown"] += 1
        for text in assistant_texts(rec):
            for line in text.splitlines():
                if "ruling" in line.lower():
                    counts["ruling_lines"] += 1
    return counts


def transcript_date(path):
    ts = os.path.getmtime(path)
    return datetime.fromtimestamp(ts, tz=timezone.utc).date()


def run_census(root, since, timeouts):
    """Return (list of (project_name, counts), total_counts)."""
    rows = []
    total = zero_counts()
    if not os.path.isdir(root):
        return rows, total
    for name in sorted(os.listdir(root)):
        project_dir = os.path.join(root, name)
        if not os.path.isdir(project_dir):
            continue
        counts = zero_counts()
        for entry in sorted(os.listdir(project_dir)):
            if not entry.endswith(".jsonl"):
                continue
            path = os.path.join(project_dir, entry)
            if not os.path.isfile(path):
                continue
            if since is not None and transcript_date(path) < since:
                continue
            add_counts(counts, scan_transcript(path, project_dir, timeouts))
        counts["process_only_lines"] = scan_memory_folder(project_dir)
        rows.append((name, counts))
        add_counts(total, counts)
    return rows, total


def counts_row(project, counts):
    return [project] + [str(counts[k]) for k in COUNT_KEYS]


def print_table(rows, total, timeouts):
    header = list(COLUMNS)
    table = [header] + [counts_row(name, counts) for name, counts in rows]
    table.append(counts_row("TOTAL", total))
    widths = [max(len(r[i]) for r in table) for i in range(len(header))]
    for i, row in enumerate(table):
        line = "  ".join(cell.ljust(widths[j]) for j, cell in enumerate(row))
        print(line)
        if i == 0:
            print("  ".join("-" * w for w in widths))
    print(NOT_FOUND_NOTE)
    print("Timed out: %d item(s), counted as unknown." % timeouts[0])


def to_json(root, since, rows, total, timeouts):
    return {
        "root": root,
        "since": since.isoformat() if since else None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "projects": [dict(project=name, **counts) for name, counts in rows],
        "total": dict(project="TOTAL", **total),
        "timed_out": timeouts[0],
        "note": NOT_FOUND_NOTE,
    }


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Count where rulings land: memory, scratchpad, or a tracked file.")
    parser.add_argument("--root", default=None,
                         help="Projects root (default: $CLAUDE_CONFIG_DIR or ~/.claude, "
                              "plus /projects)")
    parser.add_argument("--since", default=None, help="Only sessions on or after YYYY-MM-DD")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    args = parser.parse_args(argv)
    if args.root is None:
        args.root = default_root()
    return args


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    since = None
    if args.since:
        since = datetime.strptime(args.since, "%Y-%m-%d").date()
    timeouts = [0]
    rows, total = run_census(args.root, since, timeouts)
    if args.json:
        print(json.dumps(to_json(args.root, since, rows, total, timeouts), indent=2))
    else:
        print_table(rows, total, timeouts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
