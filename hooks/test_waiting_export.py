#!/usr/bin/env python3
"""Cases for the Stop check that refuses a stop after an ArtifactData write to the waiting page when no
export has landed since (roadmap step waiting-export-check). Standard library only, and no test runner.

Run it from the repository root:

    python3 hooks/test_waiting_export.py

Stop cases run hooks/feedback_guard.py as the Stop hook does: one JSON object on stdin, no inbox file,
CLAUDE_CONFIG_DIR and HOME in the run folder. A probe counts each call to ruling_home._run_git, then runs
the guard as __main__. FEEDBACK_GUARD_UNDER_TEST overrides the guard's path.

Unit cases call feedback_guard.export_check(cwd, transcript_path), which returns (reason, note): reason is
the block text or None, note is the systemMessage text or None.

Each pass case is the base case S1 with one change, so a pass is caused by that change. S1 is the red
anchor: it blocks once the check exists. Times are fixed epochs in one UTC day. Commit dates and
transcript timestamps are set in the fixtures, never read from the clock.
"""
import datetime
import json
import os
import shutil
import subprocess
import sys
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "lint"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
sys.path.insert(0, HERE)
from mac_artifact_shapes_test import mac_of_cloud  # noqa: E402  the Mac input shapes of owner item 440

ROOT = _test_temp.run_folder()
GUARD_PATH = os.environ.get("FEEDBACK_GUARD_UNDER_TEST") or os.path.join(HERE, "feedback_guard.py")
PROBE_PATH = os.path.join(ROOT, "guard_probe.py")
FAILED = []
RED_CASES = []
CASES = []
RUNS = [0]

SESSION = "sid-waiting-export"
BRANCH = "roadmap"  # the record branch, the default of layout.record_branch
FOLDER = "waiting"  # the copy folder when the registry entry names no export
PAGE_ID, PAGE_URL = "waitpage", "https://claude.ai/artifact/waitpage"
REF_ID, REF_URL = "refdata", "https://claude.ai/artifact/refdata"
ARTIFACT_TOOL = "ArtifactData"
EXPORT_CMD = "python3 skills/waiting-page/export_page.py --page " + PAGE_URL
SCRIPT = "export_page.py"
SECTION = "Keep a copy in the repo"
NOT_CHECKED = "not checked"
FULL_SIZE = 3000  # filler records in the full-size transcript
REMOTE_ENV = "CLAUDE_CODE_REMOTE_SESSION_ID"  # the env that override.remote_session_id reads, as cse_<x>
QUEUE_ID, QUEUE_URL = "queue", "https://claude.ai/artifact/queue"  # a waiting page whose id is not "waitpage"
EXPORT_ALL = "python3 skills/waiting-page/export_page.py --all"


# --------------------------------------------------------------------------- harness helpers

def check(name, cond, detail=""):
    if cond:
        print("PASS: %s" % name)
    else:
        FAILED.append(name)
        print("FAIL: %s  %s" % (name, " ".join(str(detail).split())[:600]))


def at(hour, minute=0):
    """Epoch seconds for hh:mm UTC on the fixture day: the one clock every case uses."""
    moment = datetime.datetime(2026, 11, 5, hour, minute, tzinfo=datetime.timezone.utc)
    return int(moment.timestamp())


def iso(epoch):
    moment = datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def write_file(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


GIT_ID = ("-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
          "-c", "init.defaultBranch=main")


def git_run(where, *args, env=None):
    return subprocess.run(["git", *GIT_ID, "-C", where, *args], capture_output=True, timeout=30, env=env)


def git(where, *args, env=None):
    cp = git_run(where, *args, env=env)
    if cp.returncode != 0:
        raise RuntimeError("git %s: %s" % (" ".join(args), cp.stderr.decode("utf-8", "replace")))
    return cp.stdout.decode("utf-8", "replace")


# --------------------------------------------------------------------------- repo fixtures

def registry(page_export=None, page_id=PAGE_ID, page_url=PAGE_URL):
    """The repo's extras file: a waiting page and a reference artifact. `page_export` names the copy folder."""
    page = {"id": page_id, "url": page_url, "role": "waiting-page", "account": "shivam"}
    if page_export is not None:
        page["export"] = page_export
    reference = {"id": REF_ID, "url": REF_URL, "role": "reference", "account": "shivam",
                 "collections": ["notes"]}
    return json.dumps({"kinds": {}, "artifacts": [page, reference]})


def make_repo(name, extras):
    """A repo under the run folder: the extras file and one commit on main."""
    root = os.path.join(ROOT, "repos", name)
    os.makedirs(root)
    git(root, "init", "-q")
    write_file(os.path.join(root, ".claude", "layout-extras.json"), extras)
    write_file(os.path.join(root, "README.md"), "fixture\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "fixture")
    return root


def roadmap_repo(name, commits, extras=None):
    """A repo whose origin/roadmap ref holds `commits`: (epoch, {path: text}) in order, each dated at its
    epoch. Only the ref holds them, as after a fetch. Main's working tree holds no copy."""
    root = make_repo(name, registry() if extras is None else extras)
    git(root, "checkout", "-q", "-b", BRANCH)
    for when, files in commits:
        for rel, text in files.items():
            write_file(os.path.join(root, *rel.split("/")), text)
        git(root, "add", "-A")
        dated = dict(os.environ, GIT_AUTHOR_DATE="%d +0000" % when, GIT_COMMITTER_DATE="%d +0000" % when)
        git(root, "commit", "-q", "-m", "roadmap record", env=dated)
    git(root, "checkout", "-q", "main")
    git(root, "update-ref", "refs/remotes/origin/" + BRANCH, "refs/heads/" + BRANCH)
    git(root, "update-ref", "-d", "refs/heads/" + BRANCH)
    return root


def base_repo(name):
    """The base fixture: the copy's last commit at 17:00, then a commit at 21:00 that touches no copy folder."""
    return roadmap_repo(name, [(at(17), item(FOLDER, 1)), (at(21), {"roadmap/data/steps/x.json": "{}\n"})])


def item(folder, n):
    """One waiting-copy item file, as the copy commits it."""
    return {"%s/items/fb-%d.json" % (folder, n): json.dumps({"id": "fb-%d" % n, "n": n}) + "\n"}


def torn_ref(root):
    """Points origin/roadmap at an object that does not exist, so git cannot read the copy."""
    write_file(os.path.join(root, ".git", "refs", "remotes", "origin", *BRANCH.split("/")), "f" * 40 + "\n")


def newest_copy(root, folder):
    """The commit time of the newest commit on origin/roadmap that touches `folder`, or None."""
    out = git(root, "log", "-1", "--format=%ct", "refs/remotes/origin/" + BRANCH, "--", folder + "/").strip()
    return int(out) if out else None


def copy_readable(root, folder):
    return git_run(root, "log", "-1", "--format=%ct", "refs/remotes/origin/" + BRANCH,
                   "--", folder + "/").returncode == 0


# --------------------------------------------------------------------------- transcript records

def rec(when, kind, content, sidechain=False):
    """One transcript record. `kind` is user or assistant; `content` is a string or a list of blocks."""
    return {"type": kind, "isSidechain": sidechain, "timestamp": iso(when),
            "message": {"role": kind, "content": content}}


def owner(when, text="fix the page"):
    return rec(when, "user", text)


def say(when, text="done"):
    return rec(when, "assistant", [{"type": "text", "text": text}])


def call(when, tid, name, tool_input, sidechain=False):
    return rec(when, "assistant", [{"type": "tool_use", "id": tid, "name": name, "input": tool_input}],
               sidechain)


def result(when, tid, content, is_error=False, sidechain=False):
    return rec(when, "user", [{"type": "tool_result", "tool_use_id": tid, "content": content,
                               "is_error": is_error}], sidechain)


def page_write(when, tid="w1", action="set", url=PAGE_URL, name=ARTIFACT_TOOL, sidechain=False,
               is_error=False, collection="items", doc_id="fb-1", path=None):
    """An ArtifactData call and its result. The result is an error when `is_error`. A `collection`, a `doc_id`
    or a `path` of None leaves that key out."""
    tool_input = {"action": action, "url": url, "data": {"n": 1}}
    if doc_id is not None:
        tool_input["doc_id"] = doc_id
    if path is not None:
        tool_input["path"] = path
    if collection is not None:
        tool_input["collection"] = collection
    return [call(when, tid, name, tool_input, sidechain),
            result(when + 1, tid, "error: 403" if is_error else "ok", is_error, sidechain)]


def export_run(when, tid="e1", verdict="same", command=EXPORT_CMD, name="Bash"):
    """A call of export_page.py (Bash, or PowerShell by `name`) and its result, the verdict as the last line."""
    return [call(when, tid, name, {"command": command}), result(when + 1, tid, verdict + "\n")]


def writer_get(when, writer, tid="m1"):
    """An ArtifactData get of meta/page and its result, which names the page writer's session."""
    return [call(when, tid, ARTIFACT_TOOL, {"action": "get", "url": PAGE_URL, "collection": "meta",
                                            "doc_id": "page"}),
            result(when + 1, tid, json.dumps({"writer": writer}))]


def with_writer(records, writer=SESSION):
    """The records behind a meta/page get that names `writer`, first. A `writer` of None, or no records,
    returns them unchanged, so the writer is unknown."""
    if writer is None or records is None:
        return records
    return writer_get(at(18, 30), writer) + records


# Owner item 440: the Mac tool names the same call. mac_page_write is page_write, rewritten to the Mac name and
# shape of its cloud call (mac_of_cloud builds both), so the two carry the same data.
def mac_page_write(when, tid="w1", action="set", collection="items", doc_id="fb-1", url=PAGE_URL):
    records = page_write(when, tid=tid, action=action, url=url, collection=collection, doc_id=doc_id)
    block = records[0]["message"]["content"][0]
    block["name"], block["input"] = mac_of_cloud("ArtifactData", block["input"])
    return records


def mac_writer_get(when, writer, tid="m1"):
    """The writer's meta/page get, named by the Mac tool, whose result names the writer: writer_get's twin."""
    name, shape = mac_of_cloud("ArtifactData", {"action": "get", "url": PAGE_URL, "collection": "meta",
                                                "doc_id": "page"})
    return [call(when, tid, name, shape), result(when + 1, tid, json.dumps({"writer": writer}))]


def transcript(folder, records):
    """The transcript file, one JSON record a line. `records` None writes an empty file."""
    path = os.path.join(folder, "transcript.jsonl")
    write_file(path, "" if records is None else "".join(json.dumps(r) + "\n" for r in records))
    return path


# --------------------------------------------------------------------------- hook runs

PROBE_SOURCE = r'''import json, os, runpy, sys
sys.path.insert(0, sys.argv[1])
import ruling_home
_real_run_git = ruling_home._run_git


def _counted(*args, **kwargs):
    log = os.environ.get("RUN_GIT_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps([str(a) for a in args]) + "\n")
    return _real_run_git(*args, **kwargs)


ruling_home._run_git = _counted
sys.argv = [sys.argv[2]] + sys.argv[3:]
runpy.run_path(sys.argv[0], run_name="__main__")
'''


class Proc:
    def __init__(self, code, out, err, git_calls, inbox):
        self.code, self.out, self.err, self.git_calls, self.inbox = code, out, err, git_calls, inbox

    def desc(self):
        return "rc=%s stdout=%r stderr=%r" % (self.code, self.out[-300:], self.err[-300:])


def run_dir(label):
    RUNS[0] += 1
    path = os.path.join(ROOT, "runs", "%03d-%s" % (RUNS[0], label))
    os.makedirs(path)
    return path


def run_stop(label, cwd, records, stop_active=False, count_git=False, writer=SESSION, extra_env=None):
    """One Stop of the guard in `cwd`, with the transcript `records`. `writer` is the session the transcript
    names as the page writer (None: unknown). `extra_env` adds variables for this run. No inbox file is written."""
    folder = run_dir(label)
    records = with_writer(records, writer)
    cfg, home = os.path.join(folder, "cfg"), os.path.join(folder, "home")
    os.makedirs(cfg)
    os.makedirs(home)
    payload = {"hook_event_name": "Stop", "session_id": SESSION, "stop_hook_active": stop_active,
               "cwd": cwd, "transcript_path": transcript(folder, records)}
    if not os.path.exists(PROBE_PATH):
        write_file(PROBE_PATH, PROBE_SOURCE)
    env = dict(os.environ)
    for name in ("PYTHONUTF8", "PYTHONIOENCODING", "CLAUDE_CONFIG_DIR", "RUN_GIT_LOG", REMOTE_ENV):
        env.pop(name, None)
    env.update(CLAUDE_CONFIG_DIR=cfg, HOME=home, USERPROFILE=home)
    env.update(extra_env or {})
    git_log = os.path.join(folder, "run-git.log")
    if count_git:
        env["RUN_GIT_LOG"] = git_log
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    inbox = os.path.join(cfg, "handoffs", SESSION + ".inbox.md")
    try:
        cp = subprocess.run([sys.executable, PROBE_PATH, HERE, GUARD_PATH], input=raw, capture_output=True,
                            env=env, cwd=home, timeout=60)
    except subprocess.TimeoutExpired:
        return Proc(-1, "", "timed out after 60 s", None, inbox)
    calls = None
    if count_git:
        calls = 0
        if os.path.exists(git_log):
            with open(git_log, encoding="utf-8") as f:
                calls = sum(1 for _ in f)
    return Proc(cp.returncode, cp.stdout.decode("utf-8", "replace"), cp.stderr.decode("utf-8", "replace"),
                calls, inbox)


def decision_of(p):
    """The guard's stdout as a dict: {} for no output, else the last line parsed as JSON."""
    text = p.out.strip()
    if not text:
        return {}
    try:
        return json.loads(text.splitlines()[-1])
    except ValueError:
        return {"not-json": text}


def expect_block(name, p, phrases):
    obj = decision_of(p)
    reason = obj.get("reason") or ""
    check(name + ": exits 0", p.code == 0, p.desc())
    check(name + ": blocks the stop", obj.get("decision") == "block", p.desc())
    for phrase in phrases:
        check("%s: the reason names %r" % (name, phrase), phrase in reason, reason)
    return obj


def expect_pass(name, p):
    obj = decision_of(p)
    check(name + ": exits 0", p.code == 0, p.desc())
    check(name + ": no block", obj.get("decision") != "block", p.desc())
    return obj


def expect_note(name, p):
    """A pass whose systemMessage says the export check did not run."""
    obj = expect_pass(name, p)
    note = obj.get("systemMessage") or ""
    check(name + ": a systemMessage is written", bool(note), p.desc())
    check(name + ": the systemMessage names the export check as not checked", NOT_CHECKED in note, note)


# --------------------------------------------------------------------------- Stop cases

def case_s1_block_when_copy_is_older_than_the_write():
    """The base case and red anchor: a page write, the newest copy commit older than it, and a later commit
    that touches no copy folder. No inbox file is written, so the check must fire before the inbox read."""
    root = base_repo("s1")
    check("S1 scope: the newest copy commit is the 17:00 one", newest_copy(root, FOLDER) == at(17),
          newest_copy(root, FOLDER))
    p = run_stop("s1", root, [owner(at(18, 50))] + page_write(at(19)))
    check("S1 scope: no inbox file exists", not os.path.exists(p.inbox), p.inbox)
    expect_block("S1", p, (SCRIPT, SECTION))


def case_s2_later_copy_commit_passes():
    """S1 with one change: a copy commit after the write."""
    root = roadmap_repo("s2", [(at(17), item(FOLDER, 1)), (at(20), item(FOLDER, 2)),
                               (at(21), {"roadmap/data/steps/x.json": "{}\n"})])
    check("S2 scope: the newest copy commit is the 20:00 one", newest_copy(root, FOLDER) == at(20),
          newest_copy(root, FOLDER))
    p = run_stop("s2", root, [owner(at(18, 50))] + page_write(at(19)))
    expect_pass("S2", p)


def case_s3_same_export_after_the_write_passes():
    """S1 with one change: a later export_page.py run whose verdict is `same`."""
    root = base_repo("s3")
    records = [owner(at(18, 50))] + page_write(at(19)) + export_run(at(19, 5), verdict="same")
    expect_pass("S3", run_stop("s3", root, records))


def case_s3b_verdict_other_than_same_does_not_clear_it():
    """S3 with one change: the verdict is `changed 2`. The copy was written but not committed, so it still blocks."""
    root = base_repo("s3b")
    records = [owner(at(18, 50))] + page_write(at(19)) + export_run(at(19, 5), verdict="changed 2")
    expect_block("S3b", run_stop("s3b", root, records), (SCRIPT,))


def case_s3c_grep_of_the_script_is_no_export_run():
    """S3 with one change: a grep of the script whose output has `same` mid-line. That is no export run."""
    root = base_repo("s3c")
    grep = [call(at(19, 5), "g1", "Bash", {"command": "grep -n same skills/waiting-page/export_page.py"}),
            result(at(19, 6), "g1", "20:  same       nothing differs; exit 0\n")]
    expect_block("S3c", run_stop("s3c", root, [owner(at(18, 50))] + page_write(at(19)) + grep), (SCRIPT,))


def case_s4_write_to_reference_artifact_passes():
    """S1 with one change: the write goes to the reference artifact, not the waiting page."""
    root = base_repo("s4")
    expect_pass("S4", run_stop("s4", root, [owner(at(18, 50))] + page_write(at(19), url=REF_URL)))


def case_s5_failed_write_passes():
    """S1 with one change: the write's result is an error, so nothing was written."""
    root = base_repo("s5")
    expect_pass("S5", run_stop("s5", root, [owner(at(18, 50))] + page_write(at(19), is_error=True)))


def case_s6_no_page_write_passes_with_no_git_call():
    """A page read and a shell call: no page write, so no git call."""
    root = base_repo("s6a")
    read = [call(at(19), "r1", ARTIFACT_TOOL, {"action": "get", "url": PAGE_URL, "collection": "items",
                                               "doc_id": "fb-1"}),
            result(at(19, 1), "r1", "{}")]
    shell = [call(at(19, 2), "b1", "Bash", {"command": "ls"}), result(at(19, 3), "b1", "README.md\n")]
    p = run_stop("s6a", root, [owner(at(18, 50))] + read + shell, count_git=True)
    expect_pass("S6a", p)
    check("S6a: no _run_git call on a transcript with no page write", p.git_calls == 0,
          "calls %s" % p.git_calls)


def case_s6_empty_transcript_passes_with_no_git_call():
    """The empty state: a transcript file with no records."""
    p = run_stop("s6b", base_repo("s6b"), None, count_git=True)
    expect_pass("S6b", p)
    check("S6b: no _run_git call on an empty transcript", p.git_calls == 0, "calls %s" % p.git_calls)


def case_s6_page_write_runs_git():
    """The count sees git on a page write, so the zero counts in S6a and S6b mean something."""
    p = run_stop("s6c", base_repo("s6c"), [owner(at(18, 50))] + page_write(at(19)), count_git=True)
    check("S6c: a page write makes at least one _run_git call", (p.git_calls or 0) > 0,
          "calls %s" % p.git_calls)


def case_s7a_no_roadmap_ref_passes_with_a_note():
    """No origin/roadmap ref at all: the check cannot tell whether the copy is current, so it passes and says so."""
    root = make_repo("s7a", registry())
    check("S7a scope: origin/roadmap is absent", not copy_readable(root, FOLDER), "the copy reads")
    expect_note("S7a", run_stop("s7a", root, [owner(at(18, 50))] + page_write(at(19))))


def case_s7b_unreadable_roadmap_ref_passes_with_a_note():
    """A torn origin/roadmap ref: git fails on it, so the check passes and says so."""
    root = base_repo("s7b")
    torn_ref(root)
    check("S7b scope: the copy cannot be read", not copy_readable(root, FOLDER), "the copy reads")
    expect_note("S7b", run_stop("s7b", root, [owner(at(18, 50))] + page_write(at(19))))


def case_s7c_no_commit_touched_the_copy_folder_blocks():
    """The copy ref exists, but no commit on it ever touched the copy folder. The write is newer than any copy,
    so it blocks. A report names this choice."""
    root = roadmap_repo("s7c", [(at(21), {"roadmap/data/steps/x.json": "{}\n"})])
    check("S7c scope: no commit on the copy ref touches the copy folder", newest_copy(root, FOLDER) is None,
          newest_copy(root, FOLDER))
    expect_block("S7c", run_stop("s7c", root, [owner(at(18, 50))] + page_write(at(19))), (SCRIPT,))


def case_s8_stop_hook_active_does_not_block():
    """S1 with one change: stop_hook_active is true."""
    expect_pass("S8", run_stop("s8", base_repo("s8"), [owner(at(18, 50))] + page_write(at(19)),
                               stop_active=True))


def case_s9_sidechain_write_is_ignored():
    """S1 with one change: the write is in a sidechain (an agent's record, not the main session's)."""
    records = [owner(at(18, 50))] + page_write(at(19), sidechain=True)
    expect_pass("S9", run_stop("s9", base_repo("s9"), records))


def case_s10a_registry_export_is_the_copy_folder():
    """The registry entry's export names the copy folder. A later commit in the default folder does not count."""
    root = roadmap_repo("s10a", [(at(17), item("waitcopy", 1)), (at(21), item(FOLDER, 9))],
                        extras=registry(page_export="waitcopy"))
    check("S10a scope: the export folder's newest commit is 17:00", newest_copy(root, "waitcopy") == at(17),
          newest_copy(root, "waitcopy"))
    check("S10a scope: the default folder has a later commit at 21:00", newest_copy(root, FOLDER) == at(21),
          newest_copy(root, FOLDER))
    expect_block("S10a", run_stop("s10a", root, [owner(at(18, 50))] + page_write(at(19))), (SCRIPT,))


def case_s10b_commit_in_the_export_folder_passes():
    """S10a with one change: the later commit lands in the export folder."""
    root = roadmap_repo("s10b", [(at(17), item("waitcopy", 1)), (at(20), item("waitcopy", 2))],
                        extras=registry(page_export="waitcopy"))
    check("S10b scope: the export folder's newest commit is 20:00", newest_copy(root, "waitcopy") == at(20),
          newest_copy(root, "waitcopy"))
    expect_pass("S10b", run_stop("s10b", root, [owner(at(18, 50))] + page_write(at(19))))


def case_s11_write_in_an_earlier_turn_still_blocks():
    """The write is in an earlier turn, with no export since. The check reads the whole transcript, so the
    write still blocks. A turn-only read would let the copy go stale across turns."""
    records = ([owner(at(18, 40), "first turn")] + page_write(at(18, 45)) + [say(at(18, 46)),
               owner(at(19, 30), "second turn"), say(at(19, 31))])
    expect_block("S11", run_stop("s11", base_repo("s11"), records), (SCRIPT,))


def case_s12_reads_of_the_page_pass():
    """Only get and query calls on the page: no write."""
    records = ([owner(at(18, 50))] + page_write(at(19), action="get")
               + page_write(at(19, 2), tid="w2", action="query"))
    expect_pass("S12", run_stop("s12", base_repo("s12"), records))


def case_s13a_prefixed_tool_name_blocks():
    """S1 with one change: the tool is named with the mcp__ prefix."""
    expect_block("S13a", run_stop("s13a", base_repo("s13a"),
                                  [owner(at(18, 50))] + page_write(at(19), name="mcp__ArtifactData")),
                 (SCRIPT,))


def case_s13b_update_verb_blocks():
    """S1 with one change: the action is update, a write verb."""
    expect_block("S13b", run_stop("s13b", base_repo("s13b"),
                                  [owner(at(18, 50))] + page_write(at(19), action="update")), (SCRIPT,))


def case_s14_newest_write_after_the_copy_commit_blocks():
    """An older write, covered by the 17:00 copy commit, does not cover a newer write at 19:00."""
    root = base_repo("s14")
    early = [owner(at(16))] + page_write(at(16, 30))
    expect_pass("S14 control: the older write alone is covered by the 17:00 commit",
                run_stop("s14-early", root, early))
    expect_block("S14", run_stop("s14", root, early + page_write(at(19), tid="w2")), (SCRIPT,))


def case_s15_export_run_before_the_write_does_not_clear_it():
    """An export run before the write is not later than it."""
    records = [owner(at(18, 50))] + export_run(at(18, 30)) + page_write(at(19))
    expect_block("S15", run_stop("s15", base_repo("s15"), records), (SCRIPT,))


def case_s16_full_size_transcript_blocks():
    """The full-size state: a transcript of a few thousand records, the write at the end."""
    records = [owner(at(18))] + [say(at(18), "filler %d" % k) for k in range(FULL_SIZE)] + page_write(at(19))
    check("S16 scope: the transcript holds %d or more records" % FULL_SIZE, len(records) > FULL_SIZE,
          len(records))
    expect_block("S16", run_stop("s16", base_repo("s16"), records), (SCRIPT,))


# --------------------------------------------------------------------------- writer, collection and verdict cases

# Owner item 440: the Mac twins of the page-write cases above. Each carries its cloud case's verdict.
def case_m1_mac_writer_read_names_the_writer_of_a_mac_write():
    """The writer's meta/page get, named by the Mac tool, names the writer, so the writer's Mac set of an item
    blocks as the cloud set does (case_s1). The writer is named only by the Mac get here."""
    records = mac_writer_get(at(18, 30), SESSION) + [owner(at(18, 50))] + mac_page_write(at(19))
    expect_block("M1", run_stop("mac1", base_repo("mac1"), records, writer=None), (SCRIPT, SECTION))


def case_m2_mac_update_of_an_item_blocks():
    """The Mac db_write update of an item is the cloud update, which blocks (case_s13b)."""
    records = [owner(at(18, 50))] + mac_page_write(at(19), action="update")
    expect_block("M2", run_stop("mac2", base_repo("mac2"), records), (SCRIPT,))


def case_m3_mac_write_to_receipts_passes():
    """The Mac db_write of receipts is no export, so it passes as the cloud set of receipts does (case_n15)."""
    records = [owner(at(18, 50))] + mac_page_write(at(19), collection="receipts", doc_id="r1")
    expect_pass("M3", run_stop("mac3", base_repo("mac3"), records))


def queue_repo(name):
    """A repo whose waiting page is QUEUE_ID, with its copy one commit at 17:00 and a later commit elsewhere."""
    root = roadmap_repo(name, [(at(17), item(FOLDER, 1)), (at(21), {"roadmap/data/steps/x.json": "{}\n"})],
                        extras=registry(page_id=QUEUE_ID, page_url=QUEUE_URL))
    check("%s scope: the newest copy commit is the 17:00 one" % name.upper(), newest_copy(root, FOLDER) == at(17),
          newest_copy(root, FOLDER))
    return root


def case_n1_non_writer_set_of_an_unexported_collection_passes():
    """A session that the transcript names as not the page writer, setting a collection the copy does not export."""
    records = [owner(at(18, 50))] + page_write(at(19), collection=None, doc_id="receipts/x")
    expect_pass("N1", run_stop("n1", base_repo("n1"), records, writer="session_other"))


def case_n2_non_writer_update_of_an_item_passes():
    """A session the transcript names as not the page writer, updating an item."""
    records = [owner(at(18, 50))] + page_write(at(19), action="update", collection=None, doc_id="items/5")
    expect_pass("N2", run_stop("n2", base_repo("n2"), records, writer="session_other"))


def case_n3_writer_update_of_an_item_blocks():
    """The writer updates an item that the copy has not seen."""
    records = [owner(at(18, 50))] + page_write(at(19), action="update", collection=None, doc_id="items/5")
    expect_block("N3", run_stop("n3", base_repo("n3"), records), (SCRIPT,))


def case_n4_export_history_alone_makes_the_writer_block():
    """No meta/page get names a writer, but an earlier export run is in the transcript: this session wrote the copy."""
    records = [owner(at(18, 50))] + export_run(at(18, 30), verdict="changed 1") + page_write(at(19))
    expect_block("N4", run_stop("n4", base_repo("n4"), records, writer=None), (SCRIPT,))


def case_n5_writer_delete_of_an_exported_collection_blocks():
    """A delete is a write, and answers is an exported collection."""
    records = [owner(at(18, 50))] + page_write(at(19), action="delete", collection=None, doc_id="answers/a1")
    expect_block("N5", run_stop("n5", base_repo("n5"), records), (SCRIPT,))


def case_n6_all_form_verdict_for_the_page_id_passes():
    """export_page.py --all prints `<id>: <verdict>` for each artifact. The waiting page's own line clears a write."""
    records = ([owner(at(18, 50))] + page_write(at(19), url=QUEUE_URL)
               + export_run(at(19, 5), verdict=QUEUE_ID + ": same", command=EXPORT_ALL))
    expect_pass("N6", run_stop("n6", queue_repo("n6"), records))


def case_n6b_all_form_verdict_for_another_artifact_blocks():
    """The `--all` line of the reference artifact says nothing about the waiting page."""
    records = ([owner(at(18, 50))] + page_write(at(19), url=QUEUE_URL)
               + export_run(at(19, 5), verdict=REF_ID + ": same", command=EXPORT_ALL))
    expect_block("N6b", run_stop("n6b", queue_repo("n6b"), records), (SCRIPT,))


def case_n7_powershell_run_with_same_passes():
    """The same verdict from a PowerShell run of export_page.py clears a write."""
    records = [owner(at(18, 50))] + page_write(at(19)) + export_run(at(19, 5), verdict="same", name="PowerShell")
    expect_pass("N7", run_stop("n7", base_repo("n7"), records))


def case_n8_no_repo_and_no_page_write_gives_no_note():
    """A session in no git repo, writing a non-page artifact: the check has nothing to read and says nothing."""
    outside = run_dir("n8-outside")
    obj = expect_pass("N8", run_stop("n8", outside, [owner(at(18, 50))] + page_write(at(19), url=REF_URL),
                                     writer=None))
    check("N8: no systemMessage", not obj.get("systemMessage"), obj.get("systemMessage"))


def case_n10_unknown_writer_passes_with_no_note():
    """No meta/page get names a writer and no export run is in the transcript: the writer is unknown, so pass."""
    p = run_stop("n10", base_repo("n10"), [owner(at(18, 50))] + page_write(at(19)), writer=None)
    obj = expect_pass("N10", p)
    check("N10: no systemMessage", not obj.get("systemMessage"), obj.get("systemMessage"))


def case_n11_writer_named_by_the_remote_session_id_blocks():
    """The writer is session_9f, and this run's env names it as cse_9f, which override.remote_session_id maps back."""
    p = run_stop("n11", base_repo("n11"), [owner(at(18, 50))] + page_write(at(19)), writer="session_9f",
                 extra_env={REMOTE_ENV: "cse_9f"})
    expect_block("N11", p, (SCRIPT,))


def case_n12_remote_writer_without_the_env_passes():
    """The same writer, with the env unset: session_9f is not this session's id, so this session is no writer."""
    p = run_stop("n12", base_repo("n12"), [owner(at(18, 50))] + page_write(at(19)), writer="session_9f")
    expect_pass("N12", p)


def case_n13_another_writer_is_not_overruled_by_a_mention_of_the_script():
    """The page names another writer. Earlier shell runs that only mention export_page.py do not make this
    session the writer: the grep is no export run, and the test file's name ends in export_page.py."""
    for label, command in (("n13a", "grep -n main skills/waiting-page/export_page.py"),
                           ("n13b", "python3 skills/waiting-page/test_export_page.py")):
        records = (export_run(at(18, 40), verdict="12:def main():", command=command)
                   + page_write(at(19), action="update", collection=None, doc_id="items/fb-9"))
        expect_pass("N13 %s" % label, run_stop(label, base_repo(label), [owner(at(18, 50))] + records,
                                              writer="session_other"))


def case_n14_no_writer_named_and_an_export_run_makes_the_writer_block():
    """No meta/page get names a writer, and an earlier run of export_page.py is in the transcript: this session
    is the writer, and its stale write blocks."""
    command = "python3 ~/.claude/skills/waiting-page/export_page.py --fetched f --out o --page p"
    records = [owner(at(18, 50))] + export_run(at(18, 40), verdict="changed 2", command=command) + page_write(at(19))
    expect_block("N14", run_stop("n14", base_repo("n14"), records, writer=None), (SCRIPT,))


def case_n15_writer_set_of_receipts_passes():
    """The writer sets receipts/x by doc_id: receipts is no exported collection."""
    records = [owner(at(18, 50))] + page_write(at(19), collection=None, doc_id="receipts/x")
    expect_pass("N15", run_stop("n15", base_repo("n15"), records))


def case_n16_writer_write_by_path_to_receipts_passes():
    """The writer writes receipts/x by its path key: the same collection filter, through the path."""
    records = [owner(at(18, 50))] + page_write(at(19), collection=None, doc_id=None, path="receipts/x")
    expect_pass("N16", run_stop("n16", base_repo("n16"), records))


def case_n17_writer_write_by_path_to_items_blocks():
    """The writer writes items/5 by its path key, stale: the path prefix names an exported collection."""
    records = [owner(at(18, 50))] + page_write(at(19), collection=None, doc_id=None, path="items/5")
    expect_block("N17", run_stop("n17", base_repo("n17"), records), (SCRIPT,))


# --------------------------------------------------------------------------- unit cases

def guard_module():
    """feedback_guard imported in this process, its config folder in the run folder."""
    os.environ["CLAUDE_CONFIG_DIR"] = os.path.join(ROOT, "unit-config")
    import feedback_guard
    return feedback_guard


def export_check_of(fg, label):
    """export_check(cwd, transcript_path) from the guard module. The assert on its presence is the red."""
    fn = getattr(fg, "export_check", None)
    check("%s: feedback_guard defines export_check(cwd, transcript_path)" % label, callable(fn),
          "the module has no export_check")
    return fn


def case_u1_export_check_returns_the_reason():
    """The unit shape: a block reason that names the script, and no note."""
    fn = export_check_of(guard_module(), "U1")
    if fn is None:
        return
    root = base_repo("u1")
    tpath = transcript(run_dir("u1"), with_writer([owner(at(18, 50))] + page_write(at(19))))
    reason, note = fn(root, tpath, SESSION)
    check("U1: a page write with no later copy commit gives a reason", reason is not None, repr(reason))
    check("U1: the reason names export_page.py", reason is not None and SCRIPT in reason, repr(reason))
    check("U1: a clean block gives no note", note is None, repr(note))


def case_u2_git_failure_gives_a_note_and_no_reason():
    """A git read that raises (the binary is missing): unknown, so no reason and a note."""
    fn = export_check_of(guard_module(), "U2")
    if fn is None:
        return
    import ruling_home
    root = base_repo("u2")
    tpath = transcript(run_dir("u2"), with_writer([owner(at(18, 50))] + page_write(at(19))))
    with mock.patch.object(ruling_home, "_run_git", side_effect=ruling_home._GitFailure("git missing")):
        reason, note = fn(root, tpath, SESSION)
    check("U2: a git failure gives no block", reason is None, repr(reason))
    check("U2: a git failure gives a note that says the check was not checked",
          bool(note) and NOT_CHECKED in note, repr(note))


CASES.extend((
    case_s1_block_when_copy_is_older_than_the_write,
    case_s2_later_copy_commit_passes,
    case_s3_same_export_after_the_write_passes,
    case_s3b_verdict_other_than_same_does_not_clear_it,
    case_s3c_grep_of_the_script_is_no_export_run,
    case_s4_write_to_reference_artifact_passes,
    case_s5_failed_write_passes,
    case_s6_no_page_write_passes_with_no_git_call,
    case_s6_empty_transcript_passes_with_no_git_call,
    case_s6_page_write_runs_git,
    case_s7a_no_roadmap_ref_passes_with_a_note,
    case_s7b_unreadable_roadmap_ref_passes_with_a_note,
    case_s7c_no_commit_touched_the_copy_folder_blocks,
    case_s8_stop_hook_active_does_not_block,
    case_s9_sidechain_write_is_ignored,
    case_s10a_registry_export_is_the_copy_folder,
    case_s10b_commit_in_the_export_folder_passes,
    case_s11_write_in_an_earlier_turn_still_blocks,
    case_s12_reads_of_the_page_pass,
    case_s13a_prefixed_tool_name_blocks,
    case_s13b_update_verb_blocks,
    case_s14_newest_write_after_the_copy_commit_blocks,
    case_s15_export_run_before_the_write_does_not_clear_it,
    case_s16_full_size_transcript_blocks,
    case_n1_non_writer_set_of_an_unexported_collection_passes,
    case_n2_non_writer_update_of_an_item_passes,
    case_n3_writer_update_of_an_item_blocks,
    case_n4_export_history_alone_makes_the_writer_block,
    case_n5_writer_delete_of_an_exported_collection_blocks,
    case_n6_all_form_verdict_for_the_page_id_passes,
    case_n6b_all_form_verdict_for_another_artifact_blocks,
    case_n7_powershell_run_with_same_passes,
    case_n8_no_repo_and_no_page_write_gives_no_note,
    case_n10_unknown_writer_passes_with_no_note,
    case_n11_writer_named_by_the_remote_session_id_blocks,
    case_n12_remote_writer_without_the_env_passes,
    case_n13_another_writer_is_not_overruled_by_a_mention_of_the_script,
    case_n14_no_writer_named_and_an_export_run_makes_the_writer_block,
    case_n15_writer_set_of_receipts_passes,
    case_n16_writer_write_by_path_to_receipts_passes,
    case_n17_writer_write_by_path_to_items_blocks,
    case_m1_mac_writer_read_names_the_writer_of_a_mac_write,
    case_m2_mac_update_of_an_item_blocks,
    case_m3_mac_write_to_receipts_passes,
    case_u1_export_check_returns_the_reason,
    case_u2_git_failure_gives_a_note_and_no_reason,
))


def run_case(case):
    before = len(FAILED)
    try:
        case()
    except Exception as exc:  # a case that cannot run is red, never silently green
        check("%s: case ran" % case.__name__, False, "%s: %s" % (type(exc).__name__, exc))
    if len(FAILED) > before:
        RED_CASES.append(case.__name__)


def main():
    try:
        for case in CASES:
            run_case(case)
    finally:
        shutil.rmtree(ROOT, ignore_errors=True)
    if RED_CASES:
        print("test_waiting_export FAIL: %d of %d cases red" % (len(RED_CASES), len(CASES)))
        print("red: " + ", ".join(RED_CASES))
        return 1
    print("test_waiting_export PASS: all %d cases green" % len(CASES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
