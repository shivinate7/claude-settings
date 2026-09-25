#!/usr/bin/env python3
"""Cases for hooks/ruling_home.py. Standard library only, and no test runner.

Run it from the repository root:

    python hooks/test_ruling_home.py

Each case builds a temp transcript file, a temp `memory` folder beside it, and, where a
home: value needs a git answer, a temp git repo (used as the hook's `cwd`). Most cases call
`ruling_home.run(hook)` directly and read back the block reason string (empty string means
"print nothing"); a few run `main()` itself, as a real subprocess, to prove the fail-open
contract end to end.
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
OLD_MTIME = 946684800  # 2000-01-01, well before T0 regardless of the machine's real clock


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


def bash_tool_use(command):
    return {"type": "tool_use", "name": "Bash", "input": {"command": command}}


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
# home: <path a ref's tree holds now> passes. home: <path in no ref> blocks (an
# uncommitted file does not count).

def case_c_ref_vs_uncommitted():
    repo = make_repo("case_c_repo")
    write(os.path.join(repo, "decisions", "committed.md"), "# A committed decision\n")
    commit_all(repo)
    write(os.path.join(repo, "decisions", "uncommitted.md"), "# Not yet committed\n")
    # uncommitted.md exists on disk but was never `git add`+committed: no ref's tree holds it.

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
# Finding 1's red/green case: a peer session's fresh write, with none of THIS session's
# own tool uses naming it, must stay silent. mtime plays no part any more, so a FRESH
# mtime with no tool use must be just as silent as an old one.

def case_d_peer_fresh_write_no_tool_use_silent():
    session_dir, memory_dir = new_session("case_d")
    mem_path = os.path.join(memory_dir, "peer.md")
    write(mem_path, "# Peer note\n\nNo home line, and no tool use of mine touched this.\n")
    records = [human_record("do something unrelated", T0)]
    path = write_transcript(session_dir, records)
    hook = {"transcript_path": path, "cwd": ROOT}
    reason = rh.run(hook)
    check("case_d: silent, peer write with no tool use ignored", reason == "", reason)


# --------------------------------------------------------------------------- case e
# MEMORY.md, the index, is always ignored, even when a tool use names it.

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


# --------------------------------------------------------------------------- finding 1
# The tool-use path alone: an OLD mtime, but a Write tool use naming the file, still blocks.

def case_tool_use_alone_old_mtime_blocks():
    session_dir, memory_dir = new_session("case_tool_use_old_mtime")
    mem_path = os.path.join(memory_dir, "notes.md")
    write(mem_path, "# Note\n\nNo home line.\n")
    os.utime(mem_path, (OLD_MTIME, OLD_MTIME))
    records = [
        human_record("do the thing", T0),
        assistant_record(tool_use=write_tool_use(mem_path)),
    ]
    path = write_transcript(session_dir, records)
    hook = {"transcript_path": path, "cwd": ROOT}
    reason = rh.run(hook)
    check("tool_use_alone_old_mtime: blocks", bool(reason), reason)
    check("tool_use_alone_old_mtime: names the file", "notes.md" in reason, reason)


# --------------------------------------------------------------------------- finding 1
# The Bash path, naming a specific file: an OLD mtime, a Bash command naming that one
# file, blocks that file and only that file.

def case_bash_names_specific_file():
    session_dir, memory_dir = new_session("case_bash_specific")
    named_path = os.path.join(memory_dir, "named.md")
    other_path = os.path.join(memory_dir, "other.md")
    write(named_path, "# Note\n\nNo home line.\n")
    write(other_path, "# Note\n\nNo home line either.\n")
    os.utime(named_path, (OLD_MTIME, OLD_MTIME))
    os.utime(other_path, (OLD_MTIME, OLD_MTIME))
    records = [
        human_record("update the named note", T0),
        assistant_record(tool_use=bash_tool_use("cat %s" % named_path)),
    ]
    path = write_transcript(session_dir, records)
    hook = {"transcript_path": path, "cwd": ROOT}
    reason = rh.run(hook)
    check("bash_specific: blocks", bool(reason), reason)
    check("bash_specific: names the file the command named", "named.md" in reason, reason)
    check("bash_specific: does not name the other file", "other.md" not in reason, reason)


# --------------------------------------------------------------------------- finding 1
# The Bash path, naming only the folder: every .md file in it counts.

def case_bash_names_folder_only():
    session_dir, memory_dir = new_session("case_bash_folder")
    missing_home = os.path.join(memory_dir, "missing.md")
    has_home = os.path.join(memory_dir, "has_home.md")
    write(missing_home, "# Note\n\nNo home line.\n")
    write(has_home, "# Note\n\nhome: process-only\n")
    os.utime(missing_home, (OLD_MTIME, OLD_MTIME))
    os.utime(has_home, (OLD_MTIME, OLD_MTIME))
    records = [
        human_record("look through the memory folder", T0),
        assistant_record(tool_use=bash_tool_use("ls %s" % memory_dir)),
    ]
    path = write_transcript(session_dir, records)
    hook = {"transcript_path": path, "cwd": ROOT}
    reason = rh.run(hook)
    check("bash_folder: blocks", bool(reason), reason)
    check("bash_folder: names the file missing a home", "missing.md" in reason, reason)
    check("bash_folder: does not name the resolved file", "has_home.md" not in reason, reason)


# --------------------------------------------------------------------------- finding 3
# Every absolute path is refused now, even one that exists on disk.

def case_absolute_value_refused():
    real_target = os.path.join(ROOT, "a_real_brief.md")
    write(real_target, "some brief text\n")
    session_dir, memory_dir = new_session("case_absolute")
    mem_path = os.path.join(memory_dir, "notes.md")
    write(mem_path, "# Note\n\nhome: %s\n" % real_target)
    records = [
        human_record("file it", T0),
        assistant_record(tool_use=write_tool_use(mem_path)),
    ]
    path = write_transcript(session_dir, records)
    hook = {"transcript_path": path, "cwd": ROOT}
    reason = rh.run(hook)
    check("absolute_value_refused: blocks", bool(reason), reason)


# --------------------------------------------------------------------------- finding 4
# Refuse ".", "..", a path that leaves the repo, and git pathspec-magic values.

def case_refuses_dot_dotdot_and_glob():
    repo = make_repo("case_refuse_repo")
    write(os.path.join(repo, "decisions", "real.md"), "# Real\n")
    commit_all(repo)

    for label, value in (
        ("dot", "."),
        ("dotdot", ".."),
        ("leaves_repo", "../outside.md"),
        ("glob_star", "*"),
        ("glob_syntax", ":(glob)**"),
    ):
        session_dir, memory_dir = new_session("case_refuse_%s" % label)
        mem_path = os.path.join(memory_dir, "notes.md")
        write(mem_path, "# Note\n\nhome: %s\n" % value)
        records = [
            human_record("file it", T0),
            assistant_record(tool_use=write_tool_use(mem_path)),
        ]
        path = write_transcript(session_dir, records)
        hook = {"transcript_path": path, "cwd": repo}
        reason = rh.run(hook)
        check("refuses_%s: blocks" % label, bool(reason), reason)


# --------------------------------------------------------------------------- finding 5
# A fenced code block can hold text that LOOKS like a heading and a home-less section. A
# fence-blind reader would split on it and wrongly block; the real, single section already
# carries its own real home: line and must read as silent.

def case_fence_hides_fake_content():
    session_dir, memory_dir = new_session("case_fence")
    mem_path = os.path.join(memory_dir, "notes.md")
    write(
        mem_path,
        "# Real heading\n\n"
        "home: process-only\n\n"
        "```\n"
        "# fake heading inside fence\n"
        "no home line in here at all\n"
        "```\n",
    )
    records = [
        human_record("do the thing", T0),
        assistant_record(tool_use=write_tool_use(mem_path)),
    ]
    path = write_transcript(session_dir, records)
    hook = {"transcript_path": path, "cwd": ROOT}
    reason = rh.run(hook)
    check("fence: silent, the fenced fake heading is not a real section", reason == "", reason)


# --------------------------------------------------------------------------- finding 6
# A home: key in the YAML frontmatter counts for the section before the first heading.

def case_frontmatter_home_passes():
    session_dir, memory_dir = new_session("case_frontmatter")
    mem_path = os.path.join(memory_dir, "notes.md")
    write(
        mem_path,
        "---\nhome: process-only\n---\n\nSome notes, no heading, no home line in the body.\n",
    )
    records = [
        human_record("do the thing", T0),
        assistant_record(tool_use=write_tool_use(mem_path)),
    ]
    path = write_transcript(session_dir, records)
    hook = {"transcript_path": path, "cwd": ROOT}
    reason = rh.run(hook)
    check("frontmatter_home: silent", reason == "", reason)


# --------------------------------------------------------------------------- finding 7
# A value wrapped in one pair of backticks or quotes is accepted, unwrapped. The remedy
# prints process-only with no quotes, as plain text.

def case_wrapped_value_and_remedy_wording():
    for label, home_line in (
        ("backtick", "home: `process-only`"),
        ("double_quote", 'home: "process-only"'),
        ("single_quote", "home: 'process-only'"),
    ):
        session_dir, memory_dir = new_session("case_wrap_%s" % label)
        mem_path = os.path.join(memory_dir, "notes.md")
        write(mem_path, "# Note\n\n%s\n" % home_line)
        records = [
            human_record("do the thing", T0),
            assistant_record(tool_use=write_tool_use(mem_path)),
        ]
        path = write_transcript(session_dir, records)
        hook = {"transcript_path": path, "cwd": ROOT}
        reason = rh.run(hook)
        check("wrap_%s: silent" % label, reason == "", reason)

    session_dir, memory_dir = new_session("case_remedy_wording")
    mem_path = os.path.join(memory_dir, "notes.md")
    write(mem_path, "# Note\n\nNo home line.\n")
    records = [
        human_record("do the thing", T0),
        assistant_record(tool_use=write_tool_use(mem_path)),
    ]
    path = write_transcript(session_dir, records)
    reason = rh.run({"transcript_path": path, "cwd": ROOT})
    check("remedy_wording: names process-only as plain text", "plain text, in the section body" in reason, reason)
    check("remedy_wording: process-only appears bare", "process-only" in reason, reason)
    check("remedy_wording: not single-quoted", "'process-only'" not in reason, reason)
    check("remedy_wording: not double-quoted", '"process-only"' not in reason, reason)


# --------------------------------------------------------------------------- finding 2
# A git non-zero exit for one value (a syntactically fine path no ref's tree holds) must
# not turn off the OTHER section's own finding.

def case_git_failure_for_one_value_keeps_other_findings():
    repo = make_repo("case_git_failure_repo")
    write(os.path.join(repo, "x.md"), "hello\n")
    commit_all(repo)

    session_dir, memory_dir = new_session("case_git_failure")
    mem_path = os.path.join(memory_dir, "notes.md")
    write(
        mem_path,
        "# Never existed\n\nhome: decisions/never-existed.md\n\n"
        "# No home at all\n\nNo home line here.\n",
    )
    records = [
        human_record("file it", T0),
        assistant_record(tool_use=write_tool_use(mem_path)),
    ]
    path = write_transcript(session_dir, records)
    hook = {"transcript_path": path, "cwd": repo}
    reason = rh.run(hook)
    check("git_failure_keeps_others: blocks", bool(reason), reason)
    check("git_failure_keeps_others: names the unresolved-value section", "Never existed" in reason, reason)
    check("git_failure_keeps_others: names the missing-home section too", "No home at all" in reason, reason)


# --------------------------------------------------------------------------- decision item 5
# A deleted path resolves through no ref. A local branch that is not pushed still counts.

def case_deleted_path_and_unpushed_branch():
    repo = make_repo("case_branches_repo")
    write(os.path.join(repo, "gone.md"), "will be deleted\n")
    commit_all(repo)
    os.remove(os.path.join(repo, "gone.md"))
    commit_all(repo, "delete gone.md")

    _git(repo, "checkout", "-q", "-b", "side-branch")
    write(os.path.join(repo, "only-on-side.md"), "only here\n")
    commit_all(repo, "add only-on-side.md")
    _git(repo, "checkout", "-q", "-")

    session_dir, memory_dir = new_session("case_branches")
    deleted_path = os.path.join(memory_dir, "deleted.md")
    side_path = os.path.join(memory_dir, "side.md")
    write(deleted_path, "# Ruling\n\nhome: gone.md\n")
    write(side_path, "# Ruling\n\nhome: only-on-side.md\n")
    records = [
        human_record("file both", T0),
        assistant_record(tool_use=write_tool_use(deleted_path)),
        assistant_record(tool_use=write_tool_use(side_path)),
    ]
    path = write_transcript(session_dir, records)
    hook = {"transcript_path": path, "cwd": repo}
    reason = rh.run(hook)
    check("deleted_path: blocks (deleted.md, not resolved)", "deleted.md" in reason, reason)
    check("unpushed_branch: side.md resolves, not named", "side.md" not in reason, reason)


# --------------------------------------------------------------------------- main(), end to end

def _run_main(hook_payload, env=None, timeout=30):
    return subprocess.run(
        [sys.executable, MODULE_PATH],
        input=json.dumps(hook_payload), capture_output=True, text=True, timeout=timeout, env=env,
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


# --------------------------------------------------------------------------- finding 8 / FAIL OPEN
# A missing git binary stands the whole hook down, silently, even though the memory file
# would otherwise resolve fine if git worked.

def case_main_missing_git_binary_stands_down():
    repo = make_repo("case_main_missing_git_repo")
    write(os.path.join(repo, "x.md"), "hello\n")
    commit_all(repo)

    session_dir, memory_dir = new_session("case_main_missing_git")
    mem_path = os.path.join(memory_dir, "notes.md")
    write(mem_path, "# Note\n\nhome: x.md\n")
    records = [
        human_record("do the thing", T0),
        assistant_record(tool_use=write_tool_use(mem_path)),
    ]
    path = write_transcript(session_dir, records)

    empty_path_dir = os.path.join(ROOT, "empty_path_for_git_test")
    os.makedirs(empty_path_dir, exist_ok=True)
    env = dict(os.environ)
    env["PATH"] = empty_path_dir
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = _run_main({"transcript_path": path, "cwd": repo}, env=env)
    check("main_missing_git: exit 0", result.returncode == 0, result.returncode)
    check("main_missing_git: nothing printed", result.stdout.strip() == "", result.stdout)


def main():
    case_a_no_home_line()
    case_b_process_only_passes()
    case_c_ref_vs_uncommitted()
    case_d_peer_fresh_write_no_tool_use_silent()
    case_e_memory_md_ignored()
    case_f_no_memory_folder()
    case_g_stop_hook_active()
    case_h_two_sections_one_missing()
    case_tool_use_alone_old_mtime_blocks()
    case_bash_names_specific_file()
    case_bash_names_folder_only()
    case_absolute_value_refused()
    case_refuses_dot_dotdot_and_glob()
    case_fence_hides_fake_content()
    case_frontmatter_home_passes()
    case_wrapped_value_and_remedy_wording()
    case_git_failure_for_one_value_keeps_other_findings()
    case_deleted_path_and_unpushed_branch()
    case_main_silent_no_memory_folder()
    case_main_blocks()
    case_main_missing_git_binary_stands_down()

    if FAILED:
        print("test_ruling_home FAIL: %d failing check(s)" % len(FAILED))
        return 1
    print("test_ruling_home PASS: all checks right")
    return 0


if __name__ == "__main__":
    sys.exit(main())
