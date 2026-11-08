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
import builtins
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile

from test_decision_watch import (_git, assistant_record, human_record, make_repo, write,
                                 write_transcript)
import precompact_handoff  # the handoff path the Stop check reads (hooks/precompact_handoff.py)

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE_PATH = os.environ.get("RULING_HOME_UNDER_TEST") or os.path.join(HERE, "ruling_home.py")

_spec = importlib.util.spec_from_file_location("ruling_home_under_test", MODULE_PATH)
rh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rh)

ROOT = tempfile.mkdtemp(prefix="ruling_home_cases_")
# Every handoff a case writes lands under ROOT, never in the real ~/.claude/handoffs.
os.environ["CLAUDE_CONFIG_DIR"] = os.path.join(ROOT, "claude-config")
FAILED = []

T0 = "2026-09-24T10:00:00.000Z"
OLD_MTIME = 946684800  # 2000-01-01, well before T0 regardless of the machine's real clock
FRESH_MTIME = 1790244010  # 2026-09-24T10:00:10Z, 10 seconds after T0


def check(name, condition, detail=""):
    if condition:
        print("PASS: %s" % name)
    else:
        FAILED.append(name)
        print("FAIL: %s  %s" % (name, detail))


def commit_all(repo, msg="init"):
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)


def write_tool_use(target_path):
    return {"type": "tool_use", "name": "Write", "input": {"file_path": target_path, "content": "x"}}


def bash_tool_use(command):
    return {"type": "tool_use", "name": "Bash", "input": {"command": command}}


def _new_session_at(base, name):
    """A transcript directory, separate from any git repo, the way a real Claude Code
    session lays it out: transcript.jsonl beside a memory/ folder."""
    session_dir = os.path.join(base, name)
    os.makedirs(session_dir, exist_ok=True)
    memory_dir = os.path.join(session_dir, "memory")
    os.makedirs(memory_dir, exist_ok=True)
    return session_dir, memory_dir


def new_session(name):
    return _new_session_at(ROOT, name)


# --------------------------------------------------------------------------- case a
# A written memory section with no home: line at all: blocks.

def case_a_no_home_line():
    # Rows: (row id, file text, mtime or None). mtime plays no part in the verdict, so the old row
    # reaches the same tool-use branch as the fresh one. A Write tool use names the file in both.
    for prefix, text, mtime in (
        ("case_a", "# Note\n\nSomething happened, no home line here.\n", None),
        ("tool_use_alone_old_mtime", "# Note\n\nNo home line.\n", OLD_MTIME),
    ):
        session_dir, memory_dir = new_session(prefix)
        mem_path = os.path.join(memory_dir, "notes.md")
        write(mem_path, text)
        if mtime is not None:
            os.utime(mem_path, (mtime, mtime))
        records = [
            human_record("do the thing", T0),
            assistant_record(tool_use=write_tool_use(mem_path)),
        ]
        path = write_transcript(session_dir, records)
        hook = {"transcript_path": path, "cwd": ROOT}
        reason = rh.run(hook)
        check(prefix + ": blocks", bool(reason), reason)
        check(prefix + ": names the file", "notes.md" in reason, reason)
        check(prefix + ": names the section", "Note" in reason, reason)


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


# --------------------------------------------------------------------------- idle turn
# THE CHEAP EXIT. Only this turn's records are read, from the tail of the transcript. A
# transcript whose whole-file reader raises must not matter on an idle turn, and a turn
# that wrote a memory file must still block (the known-bad half of the pair).

def case_idle_turn_never_parses_the_whole_transcript():
    rh._ensure_transcript_helpers()
    real = rh.read_transcript

    def boom(_path):
        raise AssertionError("the whole transcript was parsed")
    session_dir, memory_dir = new_session("case_idle_tail_only")
    mem_path = os.path.join(memory_dir, "notes.md")
    write(mem_path, "# Note\n\nNo home line.\n")
    old_turn = [human_record("write a note", T0), assistant_record(tool_use=write_tool_use(mem_path)),
                human_record("thanks", "2026-09-24T11:00:00.000Z"), assistant_record(text="You are welcome.")]
    hook = {"transcript_path": write_transcript(session_dir, old_turn), "cwd": ROOT}
    rh.read_transcript = boom
    try:
        idle = rh.run(hook)
    finally:
        rh.read_transcript = real
    check("idle_tail_only: an earlier turn's memory write is not reported", idle == "", idle)
    new_turn = old_turn + [assistant_record(tool_use=write_tool_use(mem_path))]
    hook = {"transcript_path": write_transcript(session_dir, new_turn), "cwd": ROOT}
    reason = rh.run(hook)
    check("idle_tail_only: this turn's memory write still blocks", "notes.md" in reason, reason)


# ---------------------------------------------------------------------------
# The Bash path, naming a specific file: a FRESH mtime, a Bash command naming that one
# file, blocks that file and only that file.

def case_bash_names_specific_file():
    session_dir, memory_dir = new_session("case_bash_specific")
    named_path = os.path.join(memory_dir, "named.md")
    other_path = os.path.join(memory_dir, "other.md")
    write(named_path, "# Note\n\nNo home line.\n")
    write(other_path, "# Note\n\nNo home line either.\n")
    os.utime(named_path, (FRESH_MTIME, FRESH_MTIME))
    os.utime(other_path, (FRESH_MTIME, FRESH_MTIME))
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


# ---------------------------------------------------------------------------
# The Bash path, naming only the folder: every .md file in it counts, each still checked on
# its own FRESH mtime.

def case_bash_names_folder_only():
    session_dir, memory_dir = new_session("case_bash_folder")
    missing_home = os.path.join(memory_dir, "missing.md")
    has_home = os.path.join(memory_dir, "has_home.md")
    write(missing_home, "# Note\n\nNo home line.\n")
    write(has_home, "# Note\n\nhome: process-only\n")
    os.utime(missing_home, (FRESH_MTIME, FRESH_MTIME))
    os.utime(has_home, (FRESH_MTIME, FRESH_MTIME))
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


# ---------------------------------------------------------------------------
# A read (`cat`/`ls`) never changes mtime. An OLD file a Bash command reads must stay
# silent, whether named specifically or only through the folder.

def case_bash_read_only_old_files_silent():
    # Rows: (row id, session slug, command template). The template takes the file ("mem") or the
    # folder ("folder"), so a cat of the named file and an ls of its folder are two rows.
    for label, slug, template in (
        ("bash_read_only_named: silent", "case_bash_read_only", "cat %(mem)s"),
        ("bash_ls_folder_old_files: silent", "case_bash_ls_old", "ls %(folder)s"),
    ):
        session_dir, memory_dir = new_session(slug)
        mem_path = os.path.join(memory_dir, "old.md")
        write(mem_path, "# Note\n\nNo home line.\n")
        os.utime(mem_path, (OLD_MTIME, OLD_MTIME))
        command = template % {"mem": mem_path, "folder": memory_dir}
        records = [
            human_record("check the note", T0),
            assistant_record(tool_use=bash_tool_use(command)),
        ]
        path = write_transcript(session_dir, records)
        hook = {"transcript_path": path, "cwd": ROOT}
        reason = rh.run(hook)
        check(label, reason == "", reason)


# ---------------------------------------------------------------------------
# The folder is also named through its ~ and $HOME forms.

def case_bash_names_folder_tilde_and_home_forms():
    fake_home = os.path.join(ROOT, "fake_home_for_tilde")
    os.makedirs(fake_home, exist_ok=True)
    prior_home = os.environ.get("HOME")
    os.environ["HOME"] = fake_home
    try:
        for label, form in (("tilde", "~"), ("dollar_home", "$HOME")):
            session_dir, memory_dir = _new_session_at(fake_home, "case_%s" % label)
            mem_path = os.path.join(memory_dir, "notes.md")
            write(mem_path, "# Note\n\nNo home line.\n")
            os.utime(mem_path, (FRESH_MTIME, FRESH_MTIME))
            rel = os.path.relpath(memory_dir, fake_home).replace(os.sep, "/")
            records = [
                human_record("check it", T0),
                assistant_record(tool_use=bash_tool_use("ls %s/%s" % (form, rel))),
            ]
            path = write_transcript(session_dir, records)
            hook = {"transcript_path": path, "cwd": ROOT}
            reason = rh.run(hook)
            check("bash_folder_%s: blocks" % label, bool(reason), reason)
            check("bash_folder_%s: names the file" % label, "notes.md" in reason, reason)
    finally:
        if prior_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = prior_home


# ---------------------------------------------------------------------------
# A file-name match is a whole path component, never a bare substring: a Bash write to
# data.md must not mark a.md.

def case_bash_whole_component_not_substring():
    check(
        "whole_component: unit, a.md does not match inside data.md",
        not rh._names_whole_component("cat memory/data.md", "a.md"),
    )
    check(
        "whole_component: unit, data.md matches itself",
        rh._names_whole_component("cat memory/data.md", "data.md"),
    )

    session_dir, memory_dir = new_session("case_whole_component")
    a_path = os.path.join(memory_dir, "a.md")
    data_path = os.path.join(memory_dir, "data.md")
    write(a_path, "# Note\n\nNo home line.\n")
    write(data_path, "# Note\n\nNo home line either.\n")
    os.utime(a_path, (FRESH_MTIME, FRESH_MTIME))
    os.utime(data_path, (FRESH_MTIME, FRESH_MTIME))
    records = [
        human_record("update data", T0),
        assistant_record(tool_use=bash_tool_use("cat %s" % data_path)),
    ]
    path = write_transcript(session_dir, records)
    hook = {"transcript_path": path, "cwd": ROOT}
    reason = rh.run(hook)
    prefix = "Ruling home: this turn's memory names no tracked home for "
    check("whole_component: reason has the expected shape", reason.startswith(prefix), reason)
    check("whole_component: the reason cites decision memory-is-never-a-rulings-only-home",
          "decision memory-is-never-a-rulings-only-home" in reason, reason)
    named_part = reason[len(prefix):].split(". Each written section")[0]
    entries = named_part.split("; ")
    check("whole_component: exactly data.md named, not a.md", entries == ["data.md (Note)"], entries)


# ---------------------------------------------------------------------------
# A home value that is no home is refused: every absolute path (even one that exists on disk),
# ".", "..", a path that leaves the repo, git pathspec-magic values, and a directory with or
# without a trailing slash. Rows: (row id, home value, cwd). The row id prints on FAIL.

def case_values_that_are_no_home():
    real_target = os.path.join(ROOT, "a_real_brief.md")
    write(real_target, "some brief text\n")
    repo = make_repo("case_invalid_home_repo")
    write(os.path.join(repo, "decisions", "real.md"), "# Real\n")
    commit_all(repo)
    rows = (
        ("absolute_value_refused", real_target, ROOT),
        # A tracked file in the repo, named by its absolute path. git also refuses the value, so
        # this row does not isolate the isabs check on its own.
        ("absolute_value_refused_in_repo", os.path.join(repo, "decisions", "real.md"), repo),
        ("refuses_dot", ".", repo),
        ("refuses_dotdot", "..", repo),
        ("refuses_leaves_repo", "../outside.md", repo),
        ("refuses_glob_star", "*", repo),
        ("refuses_glob_syntax", ":(glob)**", repo),
        ("dir_not_home_no_slash", "decisions", repo),
        ("dir_not_home_trailing_slash", "decisions/", repo),
    )
    for label, value, cwd in rows:
        session_dir, memory_dir = new_session("case_invalid_%s" % label)
        mem_path = os.path.join(memory_dir, "notes.md")
        write(mem_path, "# Note\n\nhome: %s\n" % value)
        records = [
            human_record("file it", T0),
            assistant_record(tool_use=write_tool_use(mem_path)),
        ]
        path = write_transcript(session_dir, records)
        hook = {"transcript_path": path, "cwd": cwd}
        reason = rh.run(hook)
        check("%s: blocks" % label, bool(reason), reason)


# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# A home: line that exists ONLY inside a fence, with real prose outside it, must still
# block: a fenced home never counts as the section's own home.

def case_home_only_inside_fence_blocks():
    session_dir, memory_dir = new_session("case_fence_only_home")
    mem_path = os.path.join(memory_dir, "notes.md")
    write(
        mem_path,
        "# Note\n\nSome real prose here, but the only home: line is fenced below.\n\n"
        "```\n"
        "home: process-only\n"
        "```\n",
    )
    records = [
        human_record("do the thing", T0),
        assistant_record(tool_use=write_tool_use(mem_path)),
    ]
    path = write_transcript(session_dir, records)
    hook = {"transcript_path": path, "cwd": ROOT}
    reason = rh.run(hook)
    check("home_only_inside_fence: blocks", bool(reason), reason)
    check("home_only_inside_fence: names the section", "Note" in reason, reason)


# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# One value, several refs, ONE git process (a batch-check call), not one process per ref.

def case_batch_check_single_process_call():
    repo = make_repo("case_batch_repo")
    write(os.path.join(repo, "x.md"), "hello\n")
    commit_all(repo)
    _git(repo, "checkout", "-q", "-b", "side-branch-2")
    write(os.path.join(repo, "y.md"), "hello2\n")
    commit_all(repo, "side add")
    _git(repo, "checkout", "-q", "-")

    refs = rh._list_refs(repo)
    check("batch_check: at least two refs to test with", len(refs) >= 2, refs)

    calls = {"cat_file": 0}
    real_run_git = rh._run_git

    def counting_run_git(cwd, args, input_text=None):
        if args and args[0] == "cat-file":
            calls["cat_file"] += 1
        return real_run_git(cwd, args, input_text=input_text)

    rh._run_git = counting_run_git
    try:
        resolved = rh._resolve_value(repo, refs, "x.md")
    finally:
        rh._run_git = real_run_git
    check("batch_check: resolves", resolved is True, resolved)
    check("batch_check: exactly one cat-file process for every ref", calls["cat_file"] == 1, calls["cat_file"])


# --------------------------------------------------------------------------- post-review fix 1
# One memory file that is not UTF-8 must not lose the other written file's own findings, and
# must not stand the whole hook down either.

def case_unreadable_file_skipped_others_still_reported():
    session_dir, memory_dir = new_session("case_unreadable")
    bad_path = os.path.join(memory_dir, "bad.md")
    good_path = os.path.join(memory_dir, "notes.md")
    with open(bad_path, "wb") as f:
        f.write(b"# Note\n\n\xff\xfe not valid utf-8 \x80\x81\n")
    write(good_path, "# Note\n\nNo home line.\n")
    records = [
        human_record("file both", T0),
        assistant_record(tool_use=write_tool_use(bad_path)),
        assistant_record(tool_use=write_tool_use(good_path)),
    ]
    path = write_transcript(session_dir, records)
    hook = {"transcript_path": path, "cwd": ROOT}
    reason = rh.run(hook)
    check("unreadable_file_skipped: blocks on the readable file", bool(reason), reason)
    check("unreadable_file_skipped: names the good file", "notes.md" in reason, reason)


# --------------------------------------------------------------------------- post-review fix 2
# batch-check's "missing" line echoes the input verbatim. A home: value that itself contains
# the word "blob" must not be misread as a resolved blob.

def case_batch_check_missing_echo_not_mistaken_for_blob():
    repo = make_repo("case_missing_echo_repo")
    write(os.path.join(repo, "x.md"), "hello\n")
    commit_all(repo)

    session_dir, memory_dir = new_session("case_missing_echo")
    mem_path = os.path.join(memory_dir, "notes.md")
    write(mem_path, "# Note\n\nhome: nothere blob\n")
    records = [
        human_record("file it", T0),
        assistant_record(tool_use=write_tool_use(mem_path)),
    ]
    path = write_transcript(session_dir, records)
    hook = {"transcript_path": path, "cwd": repo}
    reason = rh.run(hook)
    check("missing_echo_not_blob: blocks", bool(reason), reason)


# --------------------------------------------------------------------------- main(), end to end

def _run_main(hook_payload, env=None, timeout=30):
    return subprocess.run(
        [sys.executable, MODULE_PATH],
        input=json.dumps(hook_payload), capture_output=True, text=True, timeout=timeout, env=env,
    )


def _blocks(result):
    """True when main()'s stdout is a block decision. The known-bad half of every silent pair."""
    try:
        return json.loads(result.stdout.strip()).get("decision") == "block"
    except Exception:
        return False


def case_main_silent_no_memory_folder():
    session_dir = os.path.join(ROOT, "case_main_silent")
    os.makedirs(session_dir, exist_ok=True)
    records = [human_record("hi", T0)]
    path = write_transcript(session_dir, records)
    result = _run_main({"transcript_path": path, "cwd": ROOT})
    check("main_silent: exit 0", result.returncode == 0, result.returncode)
    check("main_silent: nothing printed", result.stdout.strip() == "", result.stdout)
    # KNOWN-BAD PAIR: silence proves nothing from a hook that is silent for every input. The same
    # transcript with a memory folder holding a note with no home line must block.
    memory_dir = os.path.join(session_dir, "memory")
    os.makedirs(memory_dir, exist_ok=True)
    mem_path = os.path.join(memory_dir, "notes.md")
    write(mem_path, "# Note\n\nNo home line.\n")
    bad = write_transcript(session_dir, [human_record("hi", T0),
                                         assistant_record(tool_use=write_tool_use(mem_path))])
    paired = _run_main({"transcript_path": bad, "cwd": ROOT})
    check("main_silent: known-bad pair blocks", _blocks(paired), paired.stdout)


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


# ---------------------------------------------------------------------------
# A missing git binary stands the whole hook down, silently, even though the memory file
# would otherwise resolve fine if git worked.

def case_main_missing_git_binary_stands_down():
    repo = make_repo("case_main_missing_git_repo")
    write(os.path.join(repo, "x.md"), "hello\n")
    commit_all(repo)

    session_dir, memory_dir = new_session("case_main_missing_git")
    mem_path = os.path.join(memory_dir, "notes.md")
    # An UNRESOLVED home, so that only a working git makes the hook speak. A home that resolves
    # reads silent with or without git, and the stand-down would prove nothing.
    write(mem_path, "# Note\n\nhome: no/such/file.md\n")
    records = [
        human_record("do the thing", T0),
        assistant_record(tool_use=write_tool_use(mem_path)),
    ]
    path = write_transcript(session_dir, records)
    control = _run_main({"transcript_path": path, "cwd": repo})
    check("main_missing_git: known-bad pair blocks with git present", _blocks(control), control.stdout)

    empty_path_dir = os.path.join(ROOT, "empty_path_for_git_test")
    os.makedirs(empty_path_dir, exist_ok=True)
    env = dict(os.environ)
    env["PATH"] = empty_path_dir
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = _run_main({"transcript_path": path, "cwd": repo}, env=env)
    check("main_missing_git: exit 0", result.returncode == 0, result.returncode)
    check("main_missing_git: nothing printed", result.stdout.strip() == "", result.stdout)


# ---------------------------------------------------------------------------
# A repo git itself cannot read -- a `.git` file pointing at a missing gitdir -- stands the
# hook down silently, even with a correct-looking home: value in the memory file.

def case_main_repo_git_cannot_read_stands_down():
    broken = os.path.join(ROOT, "broken_git_repo")
    os.makedirs(broken, exist_ok=True)
    write(os.path.join(broken, ".git"), "gitdir: /this/does/not/exist\n")

    session_dir, memory_dir = new_session("case_broken_git")
    mem_path = os.path.join(memory_dir, "notes.md")
    write(mem_path, "# Note\n\nhome: some/plausible/path.md\n")
    records = [
        human_record("file it", T0),
        assistant_record(tool_use=write_tool_use(mem_path)),
    ]
    path = write_transcript(session_dir, records)
    result = _run_main({"transcript_path": path, "cwd": broken})
    check("main_broken_git_repo: exit 0", result.returncode == 0, result.returncode)
    check("main_broken_git_repo: nothing printed", result.stdout.strip() == "", result.stdout)
    sound = make_repo("case_broken_git_control_repo")
    write(os.path.join(sound, "x.md"), "hello\n")
    commit_all(sound)
    control = _run_main({"transcript_path": path, "cwd": sound})
    check("main_broken_git_repo: known-bad pair blocks in a readable repo", _blocks(control),
          control.stdout)


# ---------------------------------------------------------------------------
# The handoff path. The Stop check reads this turn's session handoff, precompact_handoff.handoff_path
# (sid). Its seven step-4 sections come in the order hooks/precompact_handoff_prompt.md step 4 gives.
# A ruling premise in Working premises, or a list line under the NO HOME YET heading, must end with a
# `Home:` token that resolves. A line with none blocks, and the reason names its label.

DEFAULT_PREMISE = ("- P1 [measured] The Stop check reads one handoff per turn. Source: "
                   "hooks/ruling_home.py run(). Checked 2026-11-07.")
STATEMENT = "A guard or check change batches alone"
KNOWN_HOME = "docs/decisions/x.md"  # a tracked ruling home in handoff_repo()
REAL_BRANCH = "claude/rec-x"  # a branch handoff_repo() holds
FAKE_BRANCH = "claude/no-such-branch"
NO_HOME_HEADING = "Rulings with NO HOME YET"
KINDS = ("measured", "read", "notes", "assumed")
_HANDOFF_REPO = []


def handoff_text(no_home=("- none",), premises=(),
                 where=("- Branch claude/coord-pick-needs-record at 394ad48.",)):
    """The handoff with all seven step-4 sections in order. An empty `premises` keeps one measured line."""
    sections = (
        (NO_HOME_HEADING, list(no_home)),
        ("Goal", ["Fix the ruling-home check. Source: owner 2026-11-07."]),
        ("Working premises", list(premises) or [DEFAULT_PREMISE]),
        ("Where things stand", list(where)),
        ("Work in flight", ["- none"]),
        ("Next steps", ["- Write the cases."]),
        ("Files and commands that matter", ["- hooks/ruling_home.py"]),
    )
    return "# Handoff\n\n" + "".join("## %s\n%s\n\n" % (head, "\n".join(body))
                                    for head, body in sections)


def ruling(pid, home=None, text=STATEMENT):
    tail = "" if home is None else " Home: %s" % home
    return "- %s [ruling] %s. Source: coordinator 2026-11-07. Checked never.%s" % (pid, text, tail)


def assumed(pid):
    return "- %s [assumed] The pick is the owner's default. Source: none. Checked never." % pid


def no_home_line(home=None, text=STATEMENT):
    tail = "" if home is None else " Home: %s" % home
    return "- %s. Source: coordinator 2026-11-07.%s" % (text, tail)


def handoff_repo():
    """The repo the Stop check reads as cwd: docs/decisions/x.md and README.md tracked, REAL_BRANCH held."""
    if not _HANDOFF_REPO:
        repo = make_repo("ruling_handoff_repo")
        write(os.path.join(repo, "docs", "decisions", "x.md"), "# x\n")
        write(os.path.join(repo, "README.md"), "r\n")
        commit_all(repo)
        _git(repo, "branch", REAL_BRANCH)
        _HANDOFF_REPO.append(repo)
    return _HANDOFF_REPO[0]


def handoff_turn(name, text, mtime=FRESH_MTIME, wrote=False, memory=True, stop_active=False, cwd=None):
    """Write this session's handoff and its transcript. `wrote` adds a Write tool use that names the
    handoff in this turn. `mtime` None leaves the file's own mtime. Returns (hook, handoff path)."""
    session_dir = os.path.join(ROOT, name)
    os.makedirs(session_dir, exist_ok=True)
    if memory:
        os.makedirs(os.path.join(session_dir, "memory"), exist_ok=True)
    sid = "sid-" + name
    hpath = precompact_handoff.handoff_path(sid)
    write(hpath, text)
    if mtime is not None:
        os.utime(hpath, (mtime, mtime))
    records = [human_record("finish the handoff", T0)]
    if wrote:
        records.append(assistant_record(tool_use=write_tool_use(hpath)))
    hook = {"transcript_path": write_transcript(session_dir, records), "cwd": cwd or handoff_repo(),
            "session_id": sid}
    if stop_active:
        hook["stop_hook_active"] = True
    return hook, hpath


def handoff_reason(name, text, **kwargs):
    hook, _hpath = handoff_turn(name, text, **kwargs)
    return rh.run(hook)


def labels_in(reason):
    return set(re.findall(r"\bP\d+\b", reason or ""))


def opened_during(fn):
    """Run fn; return (its result, the normalized paths builtins.open was asked to open)."""
    real_open, seen = builtins.open, []

    def spy(file, *args, **kwargs):
        if isinstance(file, (str, bytes, os.PathLike)):
            seen.append(os.path.normcase(os.path.normpath(os.fsdecode(file))))
        return real_open(file, *args, **kwargs)

    builtins.open = spy
    try:
        result = fn()
    finally:
        builtins.open = real_open
    return result, seen


def case_handoff_ruling_no_home_blocks():
    """A ruling premise with no Home: token blocks, and the reason names that label only: P3, not the
    assumed P5. Two triggers for "written this turn": a Write tool use naming the handoff (old mtime),
    and a fresh mtime with no tool use (a peer's write)."""
    bad = handoff_text(premises=[ruling("P3"), assumed("P5")])
    for tag, mtime, wrote in (("write named", OLD_MTIME, True), ("fresh mtime", FRESH_MTIME, False)):
        reason = handoff_reason("hand_ruling_" + tag.replace(" ", "_"), bad, mtime=mtime, wrote=wrote)
        check("handoff ruling (%s): blocks" % tag, bool(reason), "reason is empty")
        check("handoff ruling (%s): the reason names P3 only" % tag, labels_in(reason) == {"P3"}, reason)


def case_no_home_yet_line_blocks():
    """A list line under the NO HOME YET heading with no Home: token blocks, and the reason names the section."""
    bad = handoff_text(no_home=[no_home_line()])
    reason = handoff_reason("hand_noh_no_token", bad, wrote=True)
    check("no home yet (no token): blocks", bool(reason), "reason is empty")
    check("no home yet (no token): the reason names the NO HOME YET section", NO_HOME_HEADING in reason,
          reason)


def case_no_home_yet_branch_must_be_a_ref():
    """`Home: NO HOME YET (branch <b>)` passes when some ref holds <b>, and blocks when none does."""
    ok = handoff_text(no_home=[no_home_line("NO HOME YET (branch %s)" % REAL_BRANCH)])
    bad = handoff_text(no_home=[no_home_line("NO HOME YET (branch %s)" % FAKE_BRANCH)])
    reason = handoff_reason("hand_noh_real", ok, wrote=True)
    check("no home yet (real branch): silent", reason == "", reason)
    reason = handoff_reason("hand_noh_fake", bad, wrote=True)
    check("no home yet (fake branch): blocks", bool(reason), "reason is empty")
    check("no home yet (fake branch): the reason names the NO HOME YET section", NO_HOME_HEADING in reason,
          reason)


def case_ruling_home_must_resolve():
    """A ruling's Home: passes when a branch tracks the file, and blocks when none does."""
    ok = handoff_text(premises=[ruling("P3", KNOWN_HOME)])
    bad = handoff_text(premises=[ruling("P3", "docs/decisions/missing.md")])
    reason = handoff_reason("hand_resolve_ok", ok, wrote=True)
    check("ruling home (tracked decision): silent", reason == "", reason)
    reason = handoff_reason("hand_resolve_bad", bad, wrote=True)
    check("ruling home (untracked decision): blocks", bool(reason), "reason is empty")
    check("ruling home (untracked decision): the reason names P3 only", labels_in(reason) == {"P3"}, reason)


def case_ruling_home_kind_refused():
    """A ruling's home must be a ruling-kind path. A tracked README.md, or a step: slug, blocks."""
    ok = handoff_text(premises=[ruling("P3", KNOWN_HOME)])
    reason = handoff_reason("hand_kind_ok", ok, wrote=True)
    check("ruling home kind (decisions path): silent", reason == "", reason)
    for tag, home in (("README", "README.md"), ("step slug", "step:coord-pick-needs-record")):
        bad = handoff_text(premises=[ruling("P3", home)])
        reason = handoff_reason("hand_kind_" + tag.replace(" ", "_"), bad, wrote=True)
        check("ruling home kind (%s): blocks" % tag, bool(reason), "reason is empty")
        check("ruling home kind (%s): the reason names P3 only" % tag, labels_in(reason) == {"P3"}, reason)


def case_assumed_pick_passes():
    """An [assumed] premise needs no home. An unhomed assumed line alone is silent. The same handoff with
    an unhomed ruling blocks, and names P3, not the assumed P5."""
    reason = handoff_reason("hand_assumed_only", handoff_text(premises=[assumed("P5")]), wrote=True)
    check("assumed pick: an unhomed assumed line alone is silent", reason == "", reason)
    both = handoff_text(premises=[assumed("P5"), ruling("P3")])
    reason = handoff_reason("hand_assumed_and_ruling", both, wrote=True)
    check("assumed pick: a ruling beside it blocks", bool(reason), "reason is empty")
    check("assumed pick: the reason names P3 only, not the assumed P5", labels_in(reason) == {"P3"}, reason)


def case_none_line_passes():
    """`- none` under NO HOME YET is an empty section, not a ruling line. An empty section with a homed ruling
    is silent. The same empty section with an unhomed ruling blocks, and names P3 but not the heading."""
    reason = handoff_reason("hand_none_ok", handoff_text(no_home=["- none"],
                                                         premises=[ruling("P1", KNOWN_HOME)]), wrote=True)
    check("none line: an empty NO HOME YET section with a homed ruling is silent", reason == "", reason)
    reason = handoff_reason("hand_none_bad", handoff_text(no_home=["- none"], premises=[ruling("P3")]),
                            wrote=True)
    check("none line: an unhomed ruling beside it blocks", bool(reason), "reason is empty")
    check("none line: the reason names P3, not the NO HOME YET heading",
          labels_in(reason) == {"P3"} and NO_HOME_HEADING not in reason, reason)


def case_handoff_not_written_this_turn_silent():
    """A handoff nobody wrote this turn (old mtime, no tool use) is silent. The same file with a fresh
    mtime blocks, so the silence is the rule for the turn and not a broken check."""
    text = handoff_text(premises=[ruling("P3")])
    reason = handoff_reason("hand_old_turn", text, mtime=OLD_MTIME)
    check("handoff not written this turn: silent", reason == "", reason)
    reason = handoff_reason("hand_fresh_turn", text, mtime=FRESH_MTIME)
    check("handoff not written this turn: the same file, written now, names P3", labels_in(reason) == {"P3"},
          reason)


def case_handoff_stop_hook_active_silent():
    """With stop_hook_active set, the Stop check stays silent. Without it, the same handoff blocks."""
    text = handoff_text(premises=[ruling("P3")])
    reason = handoff_reason("hand_stop_active", text, stop_active=True, wrote=True)
    check("stop_hook_active: silent", reason == "", reason)
    reason = handoff_reason("hand_stop_inactive", text, wrote=True)
    check("stop_hook_active: the same handoff without the flag names P3", labels_in(reason) == {"P3"}, reason)


def case_fenced_and_out_of_section_ignored():
    """A ruling line inside a code fence, or outside Working premises and NO HOME YET, is prose. An unhomed
    ruling in Working premises blocks, and names P1 only: the scope proof. A fenced P4 and a P9 under
    Where things stand are not named."""
    premises = [ruling("P1"), "```", ruling("P4"), "```"]
    text = handoff_text(premises=premises, where=[ruling("P9"), "- Branch claude/coord-pick-needs-record."])
    reason = handoff_reason("hand_fence_scope", text, wrote=True)
    check("fence and section: the unhomed ruling in Working premises blocks", bool(reason), "reason is empty")
    check("fence and section: names P1 only, not the fenced P4 or the P9 outside the sections",
          labels_in(reason) == {"P1"}, reason)


def case_reason_names_label_not_value():
    """The reason names the label and never the Home: value. The value here is a branch no ref holds."""
    secret = "zz-secret-branch-name"
    text = handoff_text(premises=[ruling("P3", "NO HOME YET (branch %s)" % secret)])
    reason = handoff_reason("hand_label_value", text, wrote=True)
    check("label not value: blocks", bool(reason), "reason is empty")
    check("label not value: names P3", labels_in(reason) == {"P3"}, reason)
    check("label not value: the reason holds no Home: value", secret not in reason, reason)


def case_handoff_git_failure_stands_down():
    """A repo git cannot read stands the Stop check down, silently. The same handoff in a readable repo blocks."""
    broken = os.path.join(ROOT, "hand_broken_git_repo")
    os.makedirs(broken, exist_ok=True)
    write(os.path.join(broken, ".git"), "gitdir: /this/does/not/exist\n")
    text = handoff_text(premises=[ruling("P3", "docs/decisions/missing.md")])
    hook, _hpath = handoff_turn("hand_git_broken", text, wrote=True, cwd=broken)
    result = _run_main(hook)
    check("handoff git failure: exit 0", result.returncode == 0, result.returncode)
    check("handoff git failure: nothing printed", result.stdout.strip() == "", result.stdout)
    hook, _hpath = handoff_turn("hand_git_sound", text, wrote=True)
    control = _run_main(hook)
    check("handoff git failure: the same handoff in a readable repo blocks", _blocks(control), control.stdout)


def case_idle_turn_reads_no_handoff():
    """Cost: a turn that writes no handoff opens none. One stat is allowed. Control: a turn that writes
    it opens it and blocks, which shows the spy sees a real read."""
    text = handoff_text(premises=[ruling("P3")])
    hook, hpath = handoff_turn("hand_idle", text, mtime=OLD_MTIME, wrote=True)
    session_dir = os.path.dirname(hook["transcript_path"])
    hnorm = os.path.normcase(os.path.normpath(hpath))
    # Scope first: a turn that writes the handoff opens it, so the spy below sees a real read.
    write_transcript(session_dir, [human_record("finish the handoff", T0),
                                   assistant_record(tool_use=write_tool_use(hpath))])
    busy, opened = opened_during(lambda: rh.run(hook))
    check("idle turn: control, a turn that writes the handoff opens it", hnorm in opened,
          "opened %d paths, the handoff not among them" % len(opened))
    check("idle turn: control, that turn names P3", labels_in(busy) == {"P3"}, busy)
    # The handoff was written in an earlier turn; the last turn is an idle "thanks".
    write_transcript(session_dir, [
        human_record("write the handoff", T0), assistant_record(tool_use=write_tool_use(hpath)),
        human_record("thanks", "2026-09-24T11:00:00.000Z"), assistant_record(text="You are welcome."),
    ])
    idle, opened = opened_during(lambda: rh.run(hook))
    check("idle turn: silent", idle == "", idle)
    check("idle turn: opens no handoff file", hnorm not in opened,
          "opened %d paths, the handoff among them" % len(opened))


def case_handoff_no_memory_folder_blocks():
    """The early return for a missing memory folder sits below the handoff check. A session with no memory
    folder still has its handoff checked. Not written this turn: silent. Written this turn: blocks, naming P3."""
    text = handoff_text(premises=[ruling("P3")])
    reason = handoff_reason("hand_nomem_old", text, mtime=OLD_MTIME, memory=False)
    check("no memory folder: a handoff not written this turn is silent", reason == "", reason)
    reason = handoff_reason("hand_nomem_fresh", text, memory=False)
    check("no memory folder: this turn's handoff blocks, naming P3", labels_in(reason) == {"P3"}, reason)


def case_handoff_scanner_odd_text():
    """Comment openers and a lone quote in a ruling line do not hide its Home:, and do not swallow the next
    line. A Home: in a fence, or mid-sentence in a backtick span, is not the line's home."""
    odd = ruling("P3", KNOWN_HOME, text='Use // or /* or # here, a lone " quote, see the note')
    reason = handoff_reason("hand_odd_ok", handoff_text(premises=[odd, assumed("P5")]), wrote=True)
    check("odd text: a ruling with Home: at its end, odd text before it, is silent", reason == "", reason)
    reason = handoff_reason("hand_odd_next", handoff_text(premises=[odd, ruling("P4")]), wrote=True)
    check("odd text: the unhomed line after it blocks, naming P4 only", labels_in(reason) == {"P4"}, reason)
    fenced = handoff_text(premises=[ruling("P6"), "```", "Home: %s" % KNOWN_HOME, "```"])
    reason = handoff_reason("hand_odd_fence", fenced, wrote=True)
    check("odd text: a Home: only inside a fence does not home P6", labels_in(reason) == {"P6"}, reason)
    mid = handoff_text(premises=["- P7 [ruling] Write `Home: %s` in a backtick span. Source: none. "
                                 "Checked never." % KNOWN_HOME])
    reason = handoff_reason("hand_odd_mid", mid, wrote=True)
    check("odd text: a Home: mid-sentence in a backtick span does not home P7", labels_in(reason) == {"P7"},
          reason)


def case_full_size_only_the_unhomed_label_named():
    """Full size: fifteen premises, one ruling unhomed. Only that label is named. Empty state: with every
    ruling homed and NO HOME YET set to `- none`, the handoff is silent."""
    def premises(unhomed_p11):
        rows = []
        for i in range(1, 16):
            pid = "P%d" % i
            if i == 11:
                rows.append(ruling(pid) if unhomed_p11 else ruling(pid, KNOWN_HOME))
            elif i % 3 == 0:
                rows.append(ruling(pid, KNOWN_HOME))
            else:
                rows.append("- %s [%s] Fact number %d. Source: notes. Checked never." % (pid, KINDS[i % 4], i))
        return rows

    reason = handoff_reason("hand_full_bad", handoff_text(premises=premises(True)), wrote=True)
    check("full size: blocks", bool(reason), "reason is empty")
    check("full size: names P11 only", labels_in(reason) == {"P11"}, reason)
    reason = handoff_reason("hand_full_ok", handoff_text(no_home=["- none"], premises=premises(False)), wrote=True)
    check("full size: all rulings homed and NO HOME YET empty is silent", reason == "", reason)


def case_no_home_list_forms_are_ruling_lines():
    """Under NO HOME YET every non-blank, non-fenced line is a ruling line. A `+` bullet, a numbered line and a
    plain paragraph line each block when unhomed, and the reason names that line's own label only. The `*`
    bullet is the control. `- none`, `- NONE` and `- None` claim nothing: beside an unhomed P6 they add no label."""
    forms = (
        ("plus bullet", "+ P3. Source: coordinator 2026-11-07.", "P3"),
        ("numbered line", "2. P4. Source: coordinator 2026-11-07.", "P4"),
        ("paragraph line", "P5. A guard or check change batches alone. Source: coordinator 2026-11-07.", "P5"),
        ("star bullet (control)", "* P8. Source: coordinator 2026-11-07.", "P8"),
    )
    for n, (tag, line, pid) in enumerate(forms):
        reason = handoff_reason("hand_noh_form_%d" % n, handoff_text(no_home=[line]), wrote=True)
        check("NO HOME YET %s with no Home: blocks" % tag, bool(reason), "reason is empty")
        check("NO HOME YET %s: the reason names %s only" % (tag, pid), labels_in(reason) == {pid}, reason)
    for n, none_line in enumerate(("- none", "- NONE", "- None")):
        text = handoff_text(no_home=[none_line], premises=[ruling("P6")])
        reason = handoff_reason("hand_noh_none_%d" % n, text, wrote=True)
        check("NO HOME YET %s claims no ruling: beside an unhomed P6 the reason names P6 only" % none_line,
              labels_in(reason) == {"P6"} and NO_HOME_HEADING not in reason, reason)
    rows = ["%d. P%d. Source: coordinator 2026-11-07.%s" % (i, 20 + i, (" Home: %s" % KNOWN_HOME) if i == 6 else "")
            for i in range(1, 13)]
    reason = handoff_reason("hand_noh_full", handoff_text(no_home=rows), wrote=True)
    want = {"P%d" % (20 + i) for i in range(1, 13) if i != 6}
    check("NO HOME YET full size: twelve numbered lines, one homed, name the eleven unhomed labels only",
          labels_in(reason) == want, reason)


def case_premise_bold_and_colon_ids_are_checked():
    """A ruling premise written `- **P4** [ruling]` or `- P5: [ruling]` has the label P4 or P5. Unhomed, it
    blocks and the reason names that label only. Homed on a tracked path, the same line is silent."""
    forms = (
        ("bold id", "- **P4** [ruling] %s. Source: coordinator 2026-11-07. Checked never." % STATEMENT, "P4"),
        ("colon id", "- P5: [ruling] %s. Source: coordinator 2026-11-07. Checked never." % STATEMENT, "P5"),
    )
    for n, (tag, line, pid) in enumerate(forms):
        reason = handoff_reason("hand_prem_form_%d" % n, handoff_text(premises=[line]), wrote=True)
        check("ruling premise, %s, unhomed: blocks" % tag, bool(reason), "reason is empty")
        check("ruling premise, %s, unhomed: the reason names %s only" % (tag, pid),
              labels_in(reason) == {pid}, reason)
        homed = handoff_text(premises=[line + " Home: %s" % KNOWN_HOME])
        reason = handoff_reason("hand_prem_form_homed_%d" % n, homed, wrote=True)
        check("ruling premise, %s, homed on a tracked path: silent" % tag, reason == "", reason)


def case_home_trailing_period_is_ignored():
    """One trailing period after a Home: value is ignored, in a ruling premise and on a NO HOME YET line. A
    tracked path with a period passes (control), and so does `NO HOME YET (branch <real ref>).`. The period
    does not excuse the value: an untracked path and a branch no ref holds still block, naming their label."""
    path = KNOWN_HOME + "."
    real = "NO HOME YET (branch %s)." % REAL_BRANCH
    cases = (
        ("ruling premise, tracked path with a period", handoff_text(premises=[ruling("P3", path)]), set()),
        ("ruling premise, NO HOME YET (branch <real ref>).", handoff_text(premises=[ruling("P3", real)]), set()),
        ("NO HOME YET line, tracked path with a period", handoff_text(no_home=[no_home_line(path)]), set()),
        ("NO HOME YET line, NO HOME YET (branch <real ref>).", handoff_text(no_home=[no_home_line(real)]), set()),
        ("ruling premise, untracked path with a period",
         handoff_text(premises=[ruling("P3", "docs/decisions/missing.md.")]), {"P3"}),
        ("ruling premise, NO HOME YET (branch <no ref>).",
         handoff_text(premises=[ruling("P3", "NO HOME YET (branch %s)." % FAKE_BRANCH)]), {"P3"}),
    )
    for n, (tag, text, want) in enumerate(cases):
        reason = handoff_reason("hand_period_%d" % n, text, wrote=True)
        if want:
            check("trailing period, %s: blocks, naming %s only" % (tag, ", ".join(sorted(want))),
                  labels_in(reason) == want, reason)
        else:
            check("trailing period, %s: silent" % tag, reason == "", reason)


def case_handoff_fenced_heading_is_prose():
    """A `# ` line inside a code fence, under NO HOME YET or Working premises, is prose: it neither ends its
    section nor counts as a line. Beside `- none` it blocks nothing. An unhomed line after it still blocks. A
    plain paragraph after it is line 1, so the reason names `NO HOME YET line 1` and never line 2."""
    fenced = ["```", "# shell comment", "```"]
    reason = handoff_reason("hand_fence_hash_none", handoff_text(no_home=fenced + ["- none"]), wrote=True)
    check("fenced # under NO HOME YET beside - none: silent, the fenced line counts as no line", reason == "",
          reason)
    line = "- P4. Source: coordinator 2026-11-07."
    reason = handoff_reason("hand_fence_hash_line", handoff_text(no_home=fenced + [line]), wrote=True)
    check("fenced # under NO HOME YET: the unhomed line after it blocks, naming P4 only",
          labels_in(reason) == {"P4"}, reason)
    para = "A guard or check change batches alone. Source: coordinator 2026-11-07."
    reason = handoff_reason("hand_fence_hash_para", handoff_text(no_home=fenced + [para]), wrote=True)
    check("fenced # under NO HOME YET: the paragraph after it is line 1, not line 2",
          "NO HOME YET line 1" in reason and "NO HOME YET line 2" not in reason, reason)
    prem = handoff_text(premises=[DEFAULT_PREMISE, "```", "# run the check", "```", ruling("P3")])
    reason = handoff_reason("hand_fence_hash_prem", prem, wrote=True)
    check("fenced # in Working premises: the unhomed ruling after it blocks, naming P3 only",
          labels_in(reason) == {"P3"}, reason)


def main():
    case_a_no_home_line()
    case_b_process_only_passes()
    case_c_ref_vs_uncommitted()
    case_d_peer_fresh_write_no_tool_use_silent()
    case_e_memory_md_ignored()
    case_f_no_memory_folder()
    case_g_stop_hook_active()
    case_h_two_sections_one_missing()
    case_idle_turn_never_parses_the_whole_transcript()
    case_bash_names_specific_file()
    case_bash_names_folder_only()
    case_bash_read_only_old_files_silent()
    case_bash_names_folder_tilde_and_home_forms()
    case_bash_whole_component_not_substring()
    case_values_that_are_no_home()
    case_fence_hides_fake_content()
    case_home_only_inside_fence_blocks()
    case_frontmatter_home_passes()
    case_wrapped_value_and_remedy_wording()
    case_git_failure_for_one_value_keeps_other_findings()
    case_deleted_path_and_unpushed_branch()
    case_batch_check_single_process_call()
    case_unreadable_file_skipped_others_still_reported()
    case_batch_check_missing_echo_not_mistaken_for_blob()
    case_main_silent_no_memory_folder()
    case_main_blocks()
    case_main_missing_git_binary_stands_down()
    case_main_repo_git_cannot_read_stands_down()
    case_handoff_ruling_no_home_blocks()
    case_no_home_yet_line_blocks()
    case_no_home_yet_branch_must_be_a_ref()
    case_ruling_home_must_resolve()
    case_ruling_home_kind_refused()
    case_assumed_pick_passes()
    case_none_line_passes()
    case_handoff_not_written_this_turn_silent()
    case_handoff_stop_hook_active_silent()
    case_fenced_and_out_of_section_ignored()
    case_reason_names_label_not_value()
    case_handoff_git_failure_stands_down()
    case_idle_turn_reads_no_handoff()
    case_handoff_no_memory_folder_blocks()
    case_handoff_scanner_odd_text()
    case_full_size_only_the_unhomed_label_named()
    case_no_home_list_forms_are_ruling_lines()
    case_premise_bold_and_colon_ids_are_checked()
    case_home_trailing_period_is_ignored()
    case_handoff_fenced_heading_is_prose()

    if FAILED:
        print("test_ruling_home FAIL: %d failing check(s)" % len(FAILED))
        return 1
    print("test_ruling_home PASS: all checks right")
    return 0


if __name__ == "__main__":
    sys.exit(main())
