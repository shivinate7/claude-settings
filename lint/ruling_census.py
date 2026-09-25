#!/usr/bin/env python3
"""Read-only counter for where a ruling lands: memory, scratchpad, or a tracked file.

See decisions/memory-is-never-a-rulings-only-home.md (on branch claude/ruling-home) for the
finding this counts. It reads Claude Code transcripts under a projects root. It writes no
file. Its only outside call is a local `git log`, per repo, to run the reach test. On a
partial clone, `git log -S` can make git fetch a missing blob over the network, so this is
not a blanket claim of "no network call": it depends on the repo `git log` runs against.

Run it from the repository root:

    python3 lint/ruling_census.py
    python3 lint/ruling_census.py --root ~/.claude/projects --since 2026-09-01
    python3 lint/ruling_census.py --json
    python3 lint/ruling_census.py --sample 20 --seed 1

Columns: project, sessions, worker transcripts, answers, memory writes, scratchpad writes,
"ruling" lines, process-only lines, reach found, reach not found, unknown.

`--sample N` prints N AskUserQuestion answers as JSON Lines instead of the table, for a judge
to read whether each ruling reached a tracked file. One line per answer: project (the
transcript's `cwd`), remote (`git -C <cwd> remote get-url origin`, or null when unknown),
session (the transcript's file name), timestamp (the record's own `timestamp`, or null),
question, and answer. The pick spreads across projects (round-robin by project, in random
order under `--seed`, default 0, so a run repeats) and includes worker transcripts. Each text
field is capped at 2,000 characters, with a cut marked ` [cut]`. `--sample` writes no file.
Its own git call is `git remote get-url origin`, a read of local config, never the network.

`--sample --present-only` keeps only answers whose transcript `cwd` exists on this machine
and is a readable git repo (`git -C <cwd> rev-parse --git-dir` succeeds), for a machine that
holds only some of the repos. It prints how many candidate answers it skipped as not present
to stderr, as its last line. Without the flag, `--sample` behaves as documented above.

A "session" is one `*.jsonl` file directly inside a project folder. A "worker transcript" is
a `*.jsonl` file under that session's own `subagents/` folder
(`<project>/<session-id>/subagents/*.jsonl`), one per sub-agent the session spawned. A worker
transcript's memory writes, scratchpad writes and answers are folded into its project's own
counts (with their own reach-test verdicts, since that test runs wherever a memory write or
an answer does). Its `sessions` and `"ruling" lines` are not: sessions stays a count of
top-level transcripts, and "ruling" is read as a note to the person a session answers to, a
frame a worker's own transcript does not carry the same way.

The reach test takes each memory-write line and each AskUserQuestion answer with 8 or more
words, collapses its whitespace, and asks `git log --all -S<text>` in the transcript's own
`cwd`. A "not found" is a verbatim miss, not proof that a ruling was lost: the same idea in
different words, a paraphrase, or a squashed commit all read as "not found" here.

"Scratchpad writes" counts only Write, Edit and MultiEdit tool uses whose `file_path`
contains "/scratchpad/" (backslashes normalized to `/` first, so a Windows path still
matches). Bash is left out: a shell command string does not reliably say whether it reads or
writes, and counting every Bash call that names a scratchpad path would count reads too.

A transcript that is not valid UTF-8, a memory file that is not valid UTF-8, or a
Write/Edit/MultiEdit tool use whose `file_path` is not a string, each count toward `unknown`
for that one file or item. The census keeps going rather than crash. A memory folder can
hold non-text litter such as `.DS_Store`, so only `.md` files there are read at all.

A memory write's `file_path` is matched against the project folder through
`os.path.realpath` plus `os.path.normcase` on both sides, not a plain string prefix. A
symlinked temp directory (macOS puts `TMPDIR` under `/var`, itself a symlink to
`/private/var`) can otherwise give the two sides different spellings of the same folder.

Two assumptions this script makes, because the source data does not spell them out:
  - "contains the word ruling" is read as a case-insensitive substring, so it also
    catches "rulings" and "overruling".
  - `--since` filters by a transcript's file mtime, not by a timestamp field inside it,
    since only some record types carry one.
"""
import argparse
import json
import os
import random
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

# A file was not a memory write we could classify: its file_path was not a usable string.
# Distinct from None ("this tool use is not a memory write at all").
BAD_FILE_PATH = object()

ASK_ANSWER_RE = re.compile(r'"([^"]*)"="([^"]*)"')

# The hook's own line pattern (hooks/ruling_home.py's HOME_RE), reused so the two readers
# agree on what a `home:` line looks like. The key match is case-insensitive. The value must
# equal "process-only" exactly, once one pair of surrounding backticks or quotes is stripped.
HOME_LINE_RE = re.compile(r"^\s*[-*]?\s*home:\s*(.+?)\s*$", re.IGNORECASE)
PROCESS_ONLY = "process-only"
FENCE_PAIRS = (("`", "`"), ('"', '"'), ("'", "'"))

COLUMNS = (
    "project", "sessions", "worker transcripts", "answers", "memory writes",
    "scratchpad writes", '"ruling" lines', "process-only lines", "reach found",
    "reach not found", "unknown",
)
COUNT_KEYS = (
    "sessions", "worker_transcripts", "answers", "memory_writes", "scratchpad_writes",
    "ruling_lines", "process_only_lines", "reach_found", "reach_not_found", "unknown",
)
# Fields folded into a project's totals from a worker transcript's own counts. Not
# "sessions" (stays top-level only) and not "ruling_lines" (see the module docstring).
WORKER_FOLDED_KEYS = (
    "answers", "memory_writes", "scratchpad_writes",
    "reach_found", "reach_not_found", "unknown",
)

NOT_FOUND_NOTE = 'a "not found" is a verbatim miss, not proof that a ruling was lost.'

SAMPLE_TEXT_MAX = 2000
SAMPLE_CUT_MARK = " [cut]"


def default_root():
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    return os.path.join(base, "projects")


def zero_counts():
    return {k: 0 for k in COUNT_KEYS}


def add_counts(into, other):
    for k in COUNT_KEYS:
        into[k] += other[k]


def comparison_path(path):
    """A path spelling stable across a symlinked temp dir (macOS puts TMPDIR under /var,
    itself a symlink to /private/var) and across / vs \\ separators. Backslashes normalize
    to / first, since os.path.realpath does not treat them as separators on a POSIX host.
    Used wherever a tool-use path is matched against a memory folder or project folder,
    never for display: the caller's own path stays whatever spelling it was given.
    """
    return os.path.normcase(os.path.realpath(path.replace("\\", "/")))


def strip_one_fence(value):
    for open_c, close_c in FENCE_PAIRS:
        if len(value) >= 2 and value.startswith(open_c) and value.endswith(close_c):
            return value[1:-1]
    return value


def is_process_only_line(line):
    m = HOME_LINE_RE.match(line)
    if not m:
        return False
    return strip_one_fence(m.group(1).strip()) == PROCESS_ONLY


def is_scratchpad_write(block):
    if block.get("name") not in MEMORY_WRITE_NAMES:
        return False
    inp = block.get("input")
    if not isinstance(inp, dict):
        return False
    file_path = inp.get("file_path")
    if not isinstance(file_path, str):
        return False
    return "/scratchpad/" in file_path.replace("\\", "/")


def memory_write_texts(block, project_dir):
    """Return the list of new-text strings a memory write puts on disk, None if `block` is
    not a Write/Edit/MultiEdit tool use under `project_dir`'s own memory/ folder, or the
    BAD_FILE_PATH sentinel when it is one of those tool names but its `input` is not an
    object (for example a list) or its `file_path` is not a string (so we cannot tell
    where it points).
    """
    name = block.get("name")
    if name not in MEMORY_WRITE_NAMES:
        return None
    inp = block.get("input")
    if not isinstance(inp, dict):
        return BAD_FILE_PATH
    file_path = inp.get("file_path")
    if file_path is None:
        return None
    if not isinstance(file_path, str):
        return BAD_FILE_PATH
    if not file_path:
        return None
    norm = comparison_path(file_path)
    prefix = comparison_path(project_dir) + os.sep + "memory" + os.sep
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


def ask_question_texts(block):
    """Question text for each entry in an AskUserQuestion tool_use's own `input["questions"]`
    list, in order. `None` in a slot whose entry is not a dict or has no string `question`
    field. Empty list when `input` is not a dict or `questions` is not a list. Never raises.
    """
    inp = block.get("input")
    if not isinstance(inp, dict):
        return []
    questions = inp.get("questions")
    if not isinstance(questions, list):
        return []
    texts = []
    for q in questions:
        if isinstance(q, dict) and isinstance(q.get("question"), str):
            texts.append(q.get("question"))
        else:
            texts.append(None)
    return texts


def iter_ask_answers(records):
    """Yield (rec, question, answer) for every AskUserQuestion answer found in `records`, in
    transcript order. `rec` is the tool_result's own top-level record, so `rec["timestamp"]`
    is the answer's timestamp. `question` is read positionally from the matching tool_use's
    own input (`ask_question_texts`), not parsed back out of the flattened result string:
    when a question itself quotes another string, a `"key"="value"` split of that string
    breaks on the inner quotes, though it still leaves the answers' own order and text
    intact, which is why counting and pairing key off of them here is safe.
    """
    ask_questions = {}
    for rec in records:
        for block in tool_uses(rec):
            if block.get("name") == "AskUserQuestion":
                ask_questions[block.get("id")] = ask_question_texts(block)
        for block in tool_results(rec):
            tool_use_id = block.get("tool_use_id")
            if tool_use_id not in ask_questions:
                continue
            texts = ask_questions[tool_use_id]
            for i, (_question, answer) in enumerate(
                    ASK_ANSWER_RE.findall(result_text(block))):
                question = texts[i] if i < len(texts) else None
                yield rec, question, answer


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
    """Count `home: process-only` lines across the project's current memory files. Returns
    (process_only_count, unknown_count). Only `.md` files are read. A file that cannot be
    read as UTF-8, or at all, adds to unknown_count instead of crashing the census.
    """
    memory_dir = os.path.join(project_dir, "memory")
    if not os.path.isdir(memory_dir):
        return 0, 0
    process_only = 0
    unknown = 0
    for dirpath, _dirs, files in os.walk(memory_dir):
        for name in files:
            if not name.endswith(".md"):
                continue
            path = os.path.join(dirpath, name)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
            except (OSError, UnicodeDecodeError):
                unknown += 1
                continue
            for line in text.splitlines():
                if is_process_only_line(line):
                    process_only += 1
    return process_only, unknown


def safe_read_transcript(path):
    """read_transcript, except a transcript that is not valid UTF-8 (or unreadable outright)
    returns None instead of crashing the whole census.
    """
    try:
        return read_transcript(path)
    except (UnicodeDecodeError, OSError):
        return None


def scan_transcript(path, project_dir, timeouts):
    counts = zero_counts()
    counts["sessions"] = 1
    records = safe_read_transcript(path)
    if records is None:
        counts["unknown"] += 1
        return counts
    cwd = find_cwd(records)

    for rec in records:
        for block in tool_uses(rec):
            if is_scratchpad_write(block):
                counts["scratchpad_writes"] += 1
            mem_texts = memory_write_texts(block, project_dir)
            if mem_texts is BAD_FILE_PATH:
                counts["unknown"] += 1
            elif mem_texts is not None:
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
        for text in assistant_texts(rec):
            for line in text.splitlines():
                if "ruling" in line.lower():
                    counts["ruling_lines"] += 1

    for _rec, _question, answer in iter_ask_answers(records):
        counts["answers"] += 1
        if reach_words(answer) >= REACH_WORD_MIN:
            verdict = reach_test(cwd, answer, timeouts)
            if verdict == "found":
                counts["reach_found"] += 1
            elif verdict == "not_found":
                counts["reach_not_found"] += 1
            else:
                counts["unknown"] += 1
    return counts


def worker_transcript_paths(project_dir, session_stem):
    """`*.jsonl` files directly under a session's own subagents/ folder."""
    subdir = os.path.join(project_dir, session_stem, "subagents")
    if not os.path.isdir(subdir):
        return []
    paths = []
    for entry in sorted(os.listdir(subdir)):
        if entry.endswith(".jsonl"):
            full = os.path.join(subdir, entry)
            if os.path.isfile(full):
                paths.append(full)
    return paths


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

            session_stem = entry[:-len(".jsonl")]
            for worker_path in worker_transcript_paths(project_dir, session_stem):
                counts["worker_transcripts"] += 1
                worker_counts = scan_transcript(worker_path, project_dir, timeouts)
                for key in WORKER_FOLDED_KEYS:
                    counts[key] += worker_counts[key]
        process_only, mem_unknown = scan_memory_folder(project_dir)
        counts["process_only_lines"] = process_only
        counts["unknown"] += mem_unknown
        rows.append((name, counts))
        add_counts(total, counts)
    return rows, total


def get_remote(cwd, cache):
    """`git -C <cwd> remote get-url origin`, or None when `cwd` is falsy, git cannot resolve
    it, or the call fails outright. Reads local git config only, so it never reaches the
    network. Memoized in `cache` (one lookup per distinct cwd, across the whole sample).
    """
    if not cwd:
        return None
    if cwd in cache:
        return cache[cwd]
    remote = None
    try:
        run = subprocess.run(
            ["git", "-C", cwd, "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=GIT_TIMEOUT_SECONDS,
        )
        if run.returncode == 0:
            remote = run.stdout.strip() or None
    except (subprocess.TimeoutExpired, OSError):
        remote = None
    cache[cwd] = remote
    return remote


def cwd_present(cwd, cache):
    """True when `cwd` exists on this machine and git can read a repo there
    (`git -C <cwd> rev-parse --git-dir` succeeds). False for a falsy `cwd`, a path that does
    not exist, or any git failure. Uses `os.path.isdir`, not a string check, so a Windows-style
    `cwd` (`C:\\Users\\x\\repo`) works on the machine it names. Memoized in `cache`.
    """
    if not cwd:
        return False
    if cwd in cache:
        return cache[cwd]
    present = False
    if os.path.isdir(cwd):
        try:
            run = subprocess.run(
                ["git", "-C", cwd, "rev-parse", "--git-dir"],
                capture_output=True, text=True, timeout=GIT_TIMEOUT_SECONDS,
            )
            present = run.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            present = False
    cache[cwd] = present
    return present


def filter_present_pools(pools):
    """Return (pools with every answer whose transcript cwd is not present here removed,
    the number of answers removed). A project left with no answer is dropped entirely.
    """
    cache = {}
    filtered = {}
    skipped = 0
    for name, items in pools.items():
        kept = [item for item in items if cwd_present(item["project"], cache)]
        skipped += len(items) - len(kept)
        if kept:
            filtered[name] = kept
    return filtered, skipped


def collect_transcript_answers(path, items, remote_cache):
    """Append one dict per AskUserQuestion answer in the transcript at `path` to `items`."""
    records = safe_read_transcript(path)
    if records is None:
        return
    cwd = find_cwd(records)
    remote = get_remote(cwd, remote_cache)
    session = os.path.basename(path)
    for rec, question, answer in iter_ask_answers(records):
        items.append({
            "project": cwd,
            "remote": remote,
            "session": session,
            "timestamp": rec.get("timestamp"),
            "question": question,
            "answer": answer,
        })


def collect_sample_pools(root):
    """Return {project folder name: [answer dict, ...]}, in the same project and session
    order `run_census` walks, folder names with no answer left out. Worker transcripts'
    answers are folded into their own project's list, same as their other counts.
    """
    pools = {}
    remote_cache = {}
    if not os.path.isdir(root):
        return pools
    for name in sorted(os.listdir(root)):
        project_dir = os.path.join(root, name)
        if not os.path.isdir(project_dir):
            continue
        items = []
        for entry in sorted(os.listdir(project_dir)):
            if not entry.endswith(".jsonl"):
                continue
            path = os.path.join(project_dir, entry)
            if not os.path.isfile(path):
                continue
            collect_transcript_answers(path, items, remote_cache)
            session_stem = entry[:-len(".jsonl")]
            for worker_path in worker_transcript_paths(project_dir, session_stem):
                collect_transcript_answers(worker_path, items, remote_cache)
        if items:
            pools[name] = items
    return pools


def pick_sample(pools, n, seed):
    """Pick up to `n` answers out of `pools` ({project name: [answer dict, ...]}),
    round-robin by project, in random order under `seed`: the project order is shuffled
    once, each project's own answer list is shuffled once, then one item is taken from each
    project in turn, cycling, until `n` are picked or every list runs out. Same `pools` and
    `seed` always give the same pick.
    """
    rng = random.Random(seed)
    names = sorted(pools)
    rng.shuffle(names)
    buckets = {name: list(pools[name]) for name in names}
    for name in names:
        rng.shuffle(buckets[name])
    picked = []
    while len(picked) < n and any(buckets[name] for name in names):
        for name in names:
            if len(picked) >= n:
                break
            if buckets[name]:
                picked.append(buckets[name].pop(0))
    return picked


def cap_text(text):
    """`text` cut to SAMPLE_TEXT_MAX characters, cut marked with SAMPLE_CUT_MARK. Passes a
    non-string value (None included) through unchanged.
    """
    if not isinstance(text, str):
        return text
    if len(text) > SAMPLE_TEXT_MAX:
        return text[:SAMPLE_TEXT_MAX] + SAMPLE_CUT_MARK
    return text


def sample_row(item):
    return {k: cap_text(v) for k, v in item.items()}


def run_sample(root, n, seed, present_only=False):
    pools = collect_sample_pools(root)
    skipped = 0
    if present_only:
        pools, skipped = filter_present_pools(pools)
    for item in pick_sample(pools, n, seed):
        print(json.dumps(sample_row(item)))
    if present_only:
        print("Skipped %d candidate answer(s): transcript cwd not present here."
              % skipped, file=sys.stderr)


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
    parser.add_argument("--sample", type=int, default=None,
                         help="Print N AskUserQuestion answers as JSON Lines, for a judge "
                              "to read, instead of the table or --json")
    parser.add_argument("--seed", type=int, default=0,
                         help="Seed for --sample's pick, so a run can be repeated (default 0)")
    parser.add_argument("--present-only", action="store_true",
                         help="With --sample, keep only answers whose transcript cwd "
                              "exists here and is a readable git repo")
    args = parser.parse_args(argv)
    if args.root is None:
        args.root = default_root()
    args.root = os.path.abspath(args.root)
    return args


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.sample is not None:
        run_sample(args.root, args.sample, args.seed, args.present_only)
        return 0
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
