#!/usr/bin/env python3
"""Cases for hooks/ruling_home.py. Standard library only, and no test runner.

Run it from the repository root:

    python hooks/test_ruling_home.py

Each case builds a temp transcript file, a temp `memory` folder beside it, and a temp git
repo (used as the hook's `cwd`, for the `home:` values that need a ref), then calls
`ruling_home.run(hook)` exactly as `main()` would and reads back the block reason string
(empty string means "print nothing").
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE_PATH = os.environ.get("RULING_HOME_UNDER_TEST") or os.path.join(HERE, "ruling_home.py")

_spec = importlib.util.spec_from_file_location("ruling_home_under_test", MODULE_PATH)
rh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rh)

ROOT = tempfile.mkdtemp(prefix="ruling_home_cases_")
FAILED = []

T0 = "2026-09-24T10:00:00.000Z"


def check(name, condition, detail=""):
    if condition:
        print("PASS: %s" % name)
    else:
        FAILED.append(name)
        print("FAIL: %s  %s" % (name, detail))


def _git(cwd, *args):
    subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True, check=True)


def make_repo(name):
    repo = os.path.join(ROOT, name)
    os.makedirs(repo, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    return repo


def commit_all(repo, msg="init"):
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)


def write(path, text):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def human_record(text, ts):
    return {
        "type": "user",
        "timestamp": ts,
        "message": {"role": "user", "content": [{"type": "text", "text": text}]},
    }


def assistant_record(text=None, tool_use=None):
    content = []
    if text is not None:
        content.append({"type": "text", "text": text})
    if tool_use is not None:
        content.append(tool_use)
    return {"type": "assistant", "message": {"role": "assistant", "content": content}}


def write_tool_use(target_path):
    return {"type": "tool_use", "name": "Write", "input": {"file_path": target_path, "content": "x"}}


def write_transcript(session_dir, records):
    path = os.path.join(session_dir, "transcript.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    return path


def new_session(name):
    """A transcript directory, separate from any git repo, the way a real Claude Code
    session lays it out: transcript.jsonl beside a memory/ folder."""
    session_dir = os.path.join(ROOT, name)
    os.makedirs(session_dir, exist_ok=True)
    memory_dir = os.path.join(session_dir, "memory")
    os.makedirs(memory_dir, exist_ok=True)
    return session_dir, memory_dir


# --------------------------------------------------------------------------- case a
# A written memory section with no home: line at all: blocks.

def case_a_no_home_line():
    session_dir, memory_dir = new_session("case_a")
    mem_path = os.path.join(memory_dir, "notes.md")
    write(mem_path, "# Note\n\nSomething happened, no home line here.\n")
    records = [
        human_record("do the thing", T0),
        assistant_record(tool_use=write_tool_use(mem_path)),
    ]
    path = write_transcript(session_dir, records)
    hook = {"transcript_path": path, "cwd": ROOT}
    reason = rh.run(hook)
    check("case_a: blocks", bool(reason), reason)
    check("case_a: names the file", "notes.md" in reason, reason)
    check("case_a: names the section", "Note" in reason, reason)


# --------------------------------------------------------------------------- case b
# home: process-only passes.

def case_b_process_only_passes():
    session_dir, memory_dir = new_session("case_b")
    mem_path = os.path.join(memory_dir, "notes.md")
    write(mem_path, "# Note\n\nSomething happened.\n\nhome: process-only\n")
    records = [
        human_record("do the thing", T0),
        assistant_record(tool_use=write_tool_use(mem_path)),
    ]
    path = write_transcript(session_dir, records)
    hook = {"transcript_path": path, "cwd": ROOT}
    reason = rh.run(hook)
    check("case_b: silent", reason == "", reason)


# --------------------------------------------------------------------------- case c
# home: <path a ref holds> passes. home: <path in no ref> blocks (an uncommitted file
# does not count).

def case_c_ref_vs_uncommitted():
    repo = make_repo("case_c_repo")
    write(os.path.join(repo, "decisions", "committed.md"), "# A committed decision\n")
    commit_all(repo)
    write(os.path.join(repo, "decisions", "uncommitted.md"), "# Not yet committed\n")
    # uncommitted.md exists on disk but was never `git add`+committed: no ref holds it.

    session_dir, memory_dir = new_session("case_c")
    good_path = os.path.join(memory_dir, "good.md")
    bad_path = os.path.join(memory_dir, "bad.md")
    write(good_path, "# Ruling\n\nhome: decisions/committed.md\n")
    write(bad_path, "# Ruling\n\nhome: decisions/uncommitted.md\n")
    records = [
        human_record("file the rulings", T0),
        assistant_record(tool_use=write_tool_use(good_path)),
        assistant_record(tool_use=write_tool_use(bad_path)),
    ]
    path = write_transcript(session_dir, records)
    hook = {"transcript_path": path, "cwd": repo}
    reason = rh.run(hook)
    check("case_c: blocks", bool(reason), reason)
    check("case_c: names only the unresolved file", "bad.md" in reason and "good.md" not in reason, reason)


# --------------------------------------------------------------------------- case d
# A memory file not written this turn (old mtime, no tool use naming it) is ignored, even
# though it has no home: line at all.

def case_d_not_written_this_turn_ignored():
    session_dir, memory_dir = new_session("case_d")
    mem_path = os.path.join(memory_dir, "old.md")
    write(mem_path, "# Old note\n\nNo home line, but this is old.\n")
    old_time = 946684800  # 2000-01-01, well before T0 regardless of the machine's real clock
    os.utime(mem_path, (old_time, old_time))
    records = [human_record("do something unrelated", T0)]
    path = write_transcript(session_dir, records)
    hook = {"transcript_path": path, "cwd": ROOT}
    reason = rh.run(hook)
    check("case_d: silent, old file ignored", reason == "", reason)


# --------------------------------------------------------------------------- case e
# MEMORY.md, the index, is always ignored, even when freshly written with no home: line.

def case_e_memory_md_ignored():
    session_dir, memory_dir = new_session("case_e")
    mem_path = os.path.join(memory_dir, "MEMORY.md")
    write(mem_path, "# Index\n\nNo home line here either.\n")
    records = [
        human_record("update the index", T0),
        assistant_record(tool_use=write_tool_use(mem_path)),
    ]
    path = write_transcript(session_dir, records)
    hook = {"transcript_path": path, "cwd": ROOT}
    reason = rh.run(hook)
    check("case_e: MEMORY.md silent", reason == "", reason)


# --------------------------------------------------------------------------- case f
# No memory folder at all beside the transcript: silent.

def case_f_no_memory_folder():
    session_dir = os.path.join(ROOT, "case_f")
    os.makedirs(session_dir, exist_ok=True)
    records = [human_record("hi", T0)]
    path = write_transcript(session_dir, records)
    hook = {"transcript_path": path, "cwd": ROOT}
    reason = rh.run(hook)
    check("case_f: no memory folder, silent", reason == "", reason)


# --------------------------------------------------------------------------- case g
# stop_hook_active set: silent, even with a clear violation.

def case_g_stop_hook_active():
    session_dir, memory_dir = new_session("case_g")
    mem_path = os.path.join(memory_dir, "notes.md")
    write(mem_path, "# Note\n\nNo home line.\n")
    records = [
        human_record("do the thing", T0),
        assistant_record(tool_use=write_tool_use(mem_path)),
    ]
    path = write_transcript(session_dir, records)
    hook = {"transcript_path": path, "cwd": ROOT, "stop_hook_active": True}
    reason = rh.run(hook)
    check("case_g: stop_hook_active, silent", reason == "", reason)


# --------------------------------------------------------------------------- case h
# Two sections, one with a home and one without: blocks, and names only the second.

def case_h_two_sections_one_missing():
    session_dir, memory_dir = new_session("case_h")
    mem_path = os.path.join(memory_dir, "notes.md")
    write(
        mem_path,
        "# First\n\nhome: process-only\n\n# Second\n\nNo home line here.\n",
    )
    records = [
        human_record("do the thing", T0),
        assistant_record(tool_use=write_tool_use(mem_path)),
    ]
    path = write_transcript(session_dir, records)
    hook = {"transcript_path": path, "cwd": ROOT}
    reason = rh.run(hook)
    check("case_h: blocks", bool(reason), reason)
    check("case_h: names the second section", "Second" in reason, reason)
    check("case_h: does not name the first section", "First" not in reason, reason)


# --------------------------------------------------------------------------- main(), end to end

def _run_main(hook_payload, timeout=30):
    return subprocess.run(
        [sys.executable, MODULE_PATH],
        input=json.dumps(hook_payload), capture_output=True, text=True, timeout=timeout,
    )


def case_main_silent_no_memory_folder():
    session_dir = os.path.join(ROOT, "case_main_silent")
    os.makedirs(session_dir, exist_ok=True)
    records = [human_record("hi", T0)]
    path = write_transcript(session_dir, records)
    result = _run_main({"transcript_path": path, "cwd": ROOT})
    check("main_silent: exit 0", result.returncode == 0, result.returncode)
    check("main_silent: nothing printed", result.stdout.strip() == "", result.stdout)


def case_main_blocks():
    session_dir, memory_dir = new_session("case_main_blocks")
    mem_path = os.path.join(memory_dir, "notes.md")
    write(mem_path, "# Note\n\nNo home line.\n")
    records = [
        human_record("do the thing", T0),
        assistant_record(tool_use=write_tool_use(mem_path)),
    ]
    path = write_transcript(session_dir, records)
    result = _run_main({"transcript_path": path, "cwd": ROOT})
    check("main_blocks: exit 0", result.returncode == 0, result.returncode)
    try:
        payload = json.loads(result.stdout.strip())
    except Exception:
        payload = None
    check("main_blocks: prints a block decision", (payload or {}).get("decision") == "block", result.stdout)
    check("main_blocks: reason names the file", "notes.md" in (payload or {}).get("reason", ""), result.stdout)


def main():
    case_a_no_home_line()
    case_b_process_only_passes()
    case_c_ref_vs_uncommitted()
    case_d_not_written_this_turn_ignored()
    case_e_memory_md_ignored()
    case_f_no_memory_folder()
    case_g_stop_hook_active()
    case_h_two_sections_one_missing()
    case_main_silent_no_memory_folder()
    case_main_blocks()

    if FAILED:
        print("test_ruling_home FAIL: %d failing check(s)" % len(FAILED))
        return 1
    print("test_ruling_home PASS: all checks right")
    return 0


if __name__ == "__main__":
    sys.exit(main())
