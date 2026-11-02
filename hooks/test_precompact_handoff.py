#!/usr/bin/env python3
"""Cases for hooks/precompact_handoff.py. Standard library only, and no test runner.

Run it from the repository root:

    python hooks/test_precompact_handoff.py

Spec: decisions/precompact-handoff.md: no `claude -p` child, no second login. PreCompact
writes a digest file and a state file. Reorient prints a message naming the prompt file and the
digest, and never spawns anything.

Each case gets its own temp root: a real git repo (the hook's `cwd`, and its own top
level), a `CLAUDE_CONFIG_DIR`, and a `bin` dir on PATH holding a fake `claude` (the same
extension-less-plus-`.cmd`-shim trick `put_shim` uses in merge/test_merge.py, needed because
Windows `shutil.which` never matches an extension-less script). The fake only records that
it ran -- this spec never calls it, so any record at all is the defect.
"""
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
MODULE = os.environ.get("PRECOMPACT_HANDOFF_UNDER_TEST") or os.path.join(
    HERE, "precompact_handoff.py")
sys.path.insert(0, os.path.join(REPO_ROOT, "lint"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
RUN_FOLDER = _test_temp.run_folder()

FAILED = []


def check(name, condition, detail=""):
    if condition:
        print("PASS: %s" % name)
    else:
        FAILED.append(name)
        print("FAIL: %s  %s" % (name, detail))


def put(path, text):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def put_shim(path, text):
    """Write an extension-less fake program and make it runnable from PATH.

    Copied in spirit from merge/test_merge.py's `put_shim`: on Windows, PATH resolution
    only matches a PATHEXT extension, never an extension-less script, so a matching
    `<name>.cmd` beside it re-dispatches through this same Python.
    """
    put(path, text)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
    if os.name == "nt":
        put(path + ".cmd", '@"%s" "%%~dp0%s" %%*\n' % (sys.executable, os.path.basename(path)))


# The fake just proves it ran. This spec calls no model at all, so a record file existing
# is itself the failure -- there is nothing to script.
FAKE_CLAUDE = (
    "import json, os, sys\n"
    "HERE = os.path.dirname(os.path.abspath(__file__))\n"
    "with open(os.path.join(HERE, 'fake_claude_record.json'), 'w', encoding='utf-8') as f:\n"
    "    json.dump({'argv': sys.argv[1:]}, f)\n"
    "sys.exit(0)\n"
)


def _git(cwd, *args):
    subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True, check=True)


def make_repo(root):
    os.makedirs(root, exist_ok=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    put(os.path.join(root, "README.md"), "x\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return root


def transcript_line(kind, blocks, timestamp="2026-10-03T10:00:00Z"):
    return json.dumps({"type": kind, "message": {"content": blocks}, "timestamp": timestamp})


def write_transcript(path, lines):
    put(path, "\n".join(lines) + "\n")


def flat_values(obj):
    """Yield every string found anywhere in a JSON-shaped value, so a case can look for a
    path without pinning the key that carries it."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            for s in flat_values(v):
                yield s
    elif isinstance(obj, list):
        for v in obj:
            for s in flat_values(v):
                yield s


def state_names_path(state, target):
    """True when some value in `state` is the same file as `target` (normalized, so a
    trailing slash or a different separator does not matter)."""
    if state is None:
        return False
    want = os.path.normcase(os.path.normpath(target))
    for s in flat_values(state):
        try:
            if os.path.normcase(os.path.normpath(s)) == want:
                return True
        except Exception:
            continue
    return False


class Case(object):
    """One temp root with its own repo, config dir and fake `claude` on PATH."""

    def __init__(self, name, extra_env=None):
        self.root = tempfile.mkdtemp(prefix="precompact_%s_" % name, dir=RUN_FOLDER)
        self.extra_env = dict(extra_env or {})
        self.repo = make_repo(os.path.join(self.root, "repo"))
        self.cfg = os.path.join(self.root, "cfg")
        os.makedirs(self.cfg, exist_ok=True)
        self.bin = os.path.join(self.root, "bin")
        os.makedirs(self.bin, exist_ok=True)
        put_shim(os.path.join(self.bin, "claude"), FAKE_CLAUDE)
        self.session_id = "sess-%s" % name

    def claude_was_called(self):
        return os.path.isfile(os.path.join(self.bin, "fake_claude_record.json"))

    def env(self):
        env = dict(os.environ)
        env.pop("CLAUDE_CODE_AUTO_COMPACT_WINDOW", None)  # each case sets its own window
        env["CLAUDE_CONFIG_DIR"] = self.cfg
        env["PATH"] = self.bin + os.pathsep + env.get("PATH", "")
        env.update(self.extra_env)
        return env

    def run(self, args, payload):
        return subprocess.run([sys.executable, MODULE] + args, input=json.dumps(payload),
                               capture_output=True, text=True, env=self.env(), cwd=self.repo)

    def run_precompact(self, transcript_path):
        payload = {"session_id": self.session_id, "transcript_path": transcript_path,
                   "cwd": self.repo, "hook_event_name": "PreCompact"}
        return self.run([], payload)

    def run_reorient(self):
        payload = {"session_id": self.session_id, "hook_event_name": "SessionStart",
                   "source": "compact", "cwd": self.repo}
        return self.run(["--reorient"], payload)

    def digest_path(self):
        return os.path.join(self.cfg, "state", "handoff", "%s.digest.md" % self.session_id)

    def state_path(self):
        return os.path.join(self.cfg, "state", "handoff", "%s.json" % self.session_id)

    def nudge_path(self):
        return os.path.join(self.cfg, "state", "handoff", "%s.nudge.json" % self.session_id)

    def prompt_path(self):
        return os.path.join(self.cfg, "hooks", "precompact_handoff_prompt.md")

    def handoff_path(self):
        return os.path.join(self.cfg, "handoffs", "%s.md" % self.session_id)

    def read_state(self):
        path = self.state_path()
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def read_digest(self):
        path = self.digest_path()
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


# --------------------------------------------------------------------------- PreCompact


def case_precompact_writes_digest_and_state():
    c = Case("basic")
    try:
        old_block = "OLDBLOCK" + ("A" * 40000)
        new_block = "NEWBLOCK" + ("B" * 40000)
        lines = [
            transcript_line("user", [{"type": "text", "text": old_block}]),
            transcript_line("assistant",
                            [{"type": "thinking", "thinking": "THINKINGMARKER" + "T" * 500}]),
            transcript_line("assistant",
                            [{"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]),
            transcript_line("user",
                            [{"type": "tool_result", "content": "TOOLRESULTMARKER" + "R" * 500}]),
            transcript_line("assistant", [{"type": "text", "text": new_block}]),
        ]
        tpath = os.path.join(c.root, "transcript.jsonl")
        write_transcript(tpath, lines)
        proc = c.run_precompact(tpath)

        check("basic: hook never exits 2", proc.returncode != 2,
              "returncode=%r" % proc.returncode)
        check("basic: hook exits 0", proc.returncode == 0,
              "returncode=%r stderr=%r" % (proc.returncode, proc.stderr[-300:]))
        out = (proc.stdout or "").lower()
        check("basic: no block decision printed",
              '"block"' not in out and '"deny"' not in out, "stdout: %r" % proc.stdout)
        check("basic: never calls claude -- this spec has no child",
              not c.claude_was_called(), "the fake claude ran at least once")

        digest = c.read_digest()
        check("basic: digest file written", digest is not None,
              "no digest file at %s" % c.digest_path())
        if digest is not None:
            check("basic: newest user/assistant text kept", "NEWBLOCK" in digest,
                  "the most recent text never reached the digest")
            check("basic: oldest text cut by the 60,000-char cap", "OLDBLOCK" not in digest,
                  "text past the cap still reached the digest")
            check("basic: tool_result content dropped", "TOOLRESULTMARKER" not in digest,
                  "a tool_result block reached the digest")
            check("basic: thinking content dropped", "THINKINGMARKER" not in digest,
                  "a thinking block reached the digest")
            kept_filler = sum(1 for ch in digest if ch in "AB")
            check("basic: kept text is near the 60,000-char cap, not the full ~80,000",
                  kept_filler <= 60000 + 1000,
                  "kept %d filler chars, want roughly <= 60,000" % kept_filler)

        state = c.read_state()
        check("basic: state file written", state is not None,
              "no state file at %s" % c.state_path())
        if state is not None:
            check("basic: state ok=true", state.get("ok") is True, "state: %r" % state)
            check("basic: state has a time", bool(state.get("time")), "state: %r" % state)
            check("basic: state names the digest path",
                  state_names_path(state, c.digest_path()), "state: %r" % state)
            check("basic: state names the repo top level",
                  state_names_path(state, c.repo), "state: %r" % state)
    finally:
        c.cleanup()


def case_precompact_error_is_ok_false():
    c = Case("error")
    try:
        missing_transcript = os.path.join(c.root, "does_not_exist.jsonl")
        proc = c.run_precompact(missing_transcript)
        check("error: hook never exits 2", proc.returncode != 2,
              "returncode=%r" % proc.returncode)
        check("error: hook exits 0", proc.returncode == 0,
              "returncode=%r stderr=%r" % (proc.returncode, proc.stderr[-300:]))
        out = (proc.stdout or "").lower()
        check("error: no block decision printed",
              '"block"' not in out and '"deny"' not in out, "stdout: %r" % proc.stdout)
        check("error: never calls claude", not c.claude_was_called(),
              "the fake claude ran at least once")
        state = c.read_state()
        check("error: state written", state is not None, "no state file")
        if state is not None:
            check("error: state ok=false", state.get("ok") is False, "state: %r" % state)
    finally:
        c.cleanup()


# --------------------------------------------------------------------------- reorient


def case_reorient_ok_names_prompt_and_digest():
    c = Case("reorient_ok")
    try:
        lines = [transcript_line("user", [{"type": "text", "text": "hello"}])]
        tpath = os.path.join(c.root, "transcript.jsonl")
        write_transcript(tpath, lines)
        c.run_precompact(tpath)  # a real, passing PreCompact run: no field names to guess

        proc = c.run_reorient()
        out = proc.stdout or ""
        check("reorient-ok: exits 0", proc.returncode == 0,
              "returncode=%r stderr=%r" % (proc.returncode, proc.stderr[-300:]))
        check("reorient-ok: names the prompt file", c.prompt_path() in out, "stdout: %r" % out)
        check("reorient-ok: names the digest path", c.digest_path() in out, "stdout: %r" % out)
        check("reorient-ok: names the per-session handoff path", c.handoff_path() in out,
              "stdout: %r" % out)
    finally:
        c.cleanup()


def case_reorient_no_state_says_digest_missing():
    c = Case("reorient_missing")
    try:
        proc = c.run_reorient()  # no PreCompact run first: no state file at all
        out = proc.stdout or ""
        check("reorient-missing: exits 0", proc.returncode == 0,
              "returncode=%r stderr=%r" % (proc.returncode, proc.stderr[-300:]))
        check("reorient-missing: says the digest is missing", "missing" in out.lower(),
              "stdout: %r" % out)
        check("reorient-missing: still names the prompt file", c.prompt_path() in out,
              "stdout: %r" % out)
        check("reorient-missing: still names the per-session handoff path",
              c.handoff_path() in out, "stdout: %r" % out)
    finally:
        c.cleanup()


def case_reorient_failed_state_says_digest_missing():
    c = Case("reorient_failed")
    try:
        missing_transcript = os.path.join(c.root, "does_not_exist.jsonl")
        c.run_precompact(missing_transcript)  # a real, failing PreCompact run: ok=false

        proc = c.run_reorient()
        out = proc.stdout or ""
        check("reorient-failed: exits 0", proc.returncode == 0,
              "returncode=%r stderr=%r" % (proc.returncode, proc.stderr[-300:]))
        check("reorient-failed: says the digest is missing", "missing" in out.lower(),
              "stdout: %r" % out)
        check("reorient-failed: still names the prompt file", c.prompt_path() in out,
              "stdout: %r" % out)
    finally:
        c.cleanup()


# --------------------------------------------------------------------------- settings.json


def case_settings_json():
    path = os.path.join(REPO_ROOT, "settings.json")
    with open(path, "r", encoding="utf-8") as f:
        settings = json.load(f)
    check("settings: autoCompactWindow is 500000",
          settings.get("autoCompactWindow") == 500000, "settings: %r" % settings)
    env = settings.get("env", {})
    check("settings: CLAUDE_AUTOCOMPACT_PCT_OVERRIDE is gone -- autoCompactWindow replaces it",
          "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE" not in env, "env: %r" % env)

    hooks = settings.get("hooks", {})

    def entries(event):
        out = []
        for group in hooks.get(event, []):
            for h in group.get("hooks", []):
                out.append((group.get("matcher"), h))
        return out

    precompact = entries("PreCompact")
    # Not pinning a timeout value here: the design does its work inline, with no model call to
    # budget for, so any timeout number is fine.
    found = [h for (_, h) in precompact if "precompact_handoff.py" in h.get("command", "")]
    check("settings: a PreCompact hook runs precompact_handoff.py",
          bool(found), "PreCompact hooks: %r" % precompact)

    session_start = entries("SessionStart")
    found2 = [(m, h) for (m, h) in session_start
              if m == "compact" and "precompact_handoff.py" in h.get("command", "")
              and "--reorient" in h.get("command", "")]
    check("settings: a SessionStart hook, matcher 'compact', runs it with --reorient",
          bool(found2), "SessionStart hooks: %r" % session_start)


# --------------------------------------------------------------------------- Stop --nudge
# On Stop, `--nudge` blocks once per checkpoint: 200k, then the top, compact_threshold - 50k.


def usage_line(inp, cc=0, cr=0, model=None):
    msg = {"content": [{"type": "text", "text": "hi"}],
           "usage": {"input_tokens": inp, "cache_creation_input_tokens": cc,
                     "cache_read_input_tokens": cr, "output_tokens": 5}}
    if model is not None:
        msg["model"] = model
    return json.dumps({"type": "assistant", "timestamp": "2026-10-07T10:00:00Z", "message": msg})


NUDGE_OVERHEAD = 1000  # the first-turn entry the helper prepends: messages = last - this


def nudge(c, size, active=False, lines=None, seed=None, overhead=NUDGE_OVERHEAD, model=None):
    """Run --nudge once. A first-turn entry of `overhead` tokens comes first, so the hook
    reads messages = `size` (default: last entry = size + overhead, split across the three
    input counters). With explicit `lines`, they follow the overhead entry. overhead=None
    prepends nothing. model, when set, names the model of the default entry."""
    tp = os.path.join(c.root, "t.jsonl")
    if lines is None:
        lines = [usage_line(size + (overhead or 0) - 60000 - 30000, 30000, 60000, model=model)]
    if overhead is not None:
        lines = [usage_line(overhead)] + lines
    write_transcript(tp, lines)
    if seed is not None:
        put(c.nudge_path(), json.dumps({"bucket": seed}))
    payload = {"session_id": c.session_id, "transcript_path": tp,
               "hook_event_name": "Stop", "stop_hook_active": active}
    return c.run(["--nudge"], payload)


def stored_bucket(c):
    try:
        with open(c.nudge_path(), "r", encoding="utf-8") as f:
            return json.load(f).get("bucket")
    except Exception:
        return None


def is_block(c, proc):
    try:
        obj = json.loads(proc.stdout)
    except Exception:
        return False
    r = obj.get("reason", "")
    return (obj.get("decision") == "block" and c.handoff_path() in r
            and "precompact_handoff_prompt.md" in r)


def case_nudge():
    Case.nudge_path = lambda self: os.path.join(
        self.cfg, "state", "handoff", "%s.nudge.json" % self.session_id)
    c = Case("nudge")
    try:
        p = nudge(c, 150000)
        check("nudge: 150k is silent and exits 0", p.returncode == 0 and not p.stdout.strip(),
              "rc=%r out=%r" % (p.returncode, p.stdout))
        check("nudge: 150k stores bucket -1", stored_bucket(c) == -1, "got %r" % stored_bucket(c))

        p = nudge(c, 210000)
        check("nudge: 210k first time blocks, names handoff path and prompt file",
              p.returncode == 0 and is_block(c, p), "rc=%r out=%r" % (p.returncode, p.stdout))
        check("nudge: 210k stores bucket 0", stored_bucket(c) == 0, "got %r" % stored_bucket(c))

        p = nudge(c, 330000)
        check("nudge: 330k after 210k is silent (below the top checkpoint)",
              p.returncode == 0 and not p.stdout.strip(), "out=%r" % p.stdout)
        check("nudge: 330k keeps bucket 0", stored_bucket(c) == 0, "got %r" % stored_bucket(c))

        p = nudge(c, 360000)
        check("nudge: 360k blocks at the top checkpoint", is_block(c, p), "out=%r" % p.stdout)
        check("nudge: 360k stores bucket 1", stored_bucket(c) == 1, "got %r" % stored_bucket(c))

        p = nudge(c, 455000)
        check("nudge: 455k after the top is silent (no checkpoint above it)",
              p.returncode == 0 and not p.stdout.strip(), "out=%r" % p.stdout)
        check("nudge: 455k keeps bucket 1", stored_bucket(c) == 1, "got %r" % stored_bucket(c))

        p = nudge(c, 120000)
        check("nudge: 120k after 455k (compaction) is silent",
              p.returncode == 0 and not p.stdout.strip(), "out=%r" % p.stdout)
        check("nudge: compaction resets stored bucket to -1", stored_bucket(c) == -1,
              "got %r" % stored_bucket(c))

        p = nudge(c, 210000)
        check("nudge: 210k blocks again after reset", is_block(c, p), "out=%r" % p.stdout)
    finally:
        c.cleanup()


def case_nudge_exact_boundary():
    c = Case("nudgeb")
    try:
        p = nudge(c, 199999)
        check("nudge: 199,999 is silent", not p.stdout.strip(), "out=%r" % p.stdout)
        p = nudge(c, 200000)
        check("nudge: exactly 200,000 blocks (bucket 0)", is_block(c, p), "out=%r" % p.stdout)
    finally:
        c.cleanup()


def case_nudge_uses_last_assistant_entry_and_sums_cache():
    c = Case("nudgel")
    try:
        lines = [usage_line(500000), usage_line(1000, 120000, 130000)]  # last = 251000
        p = nudge(c, 0, lines=lines)
        check("nudge: size is input+cache_creation+cache_read of the LAST assistant entry",
              is_block(c, p) and stored_bucket(c) == 0,
              "out=%r bucket=%r" % (p.stdout, stored_bucket(c)))
    finally:
        c.cleanup()


def case_nudge_stop_hook_active():
    c = Case("nudgea")
    try:
        p = nudge(c, 410000, active=True)
        check("nudge: stop_hook_active is silent", p.returncode == 0 and not p.stdout.strip(),
              "out=%r" % p.stdout)
        check("nudge: stop_hook_active changes nothing", not os.path.exists(c.nudge_path()),
              "state file written")
    finally:
        c.cleanup()


def case_nudge_failures_are_silent():
    c = Case("nudgef")
    try:
        p = nudge(c, 0, overhead=None,
                  lines=[transcript_line("assistant", [{"type": "text", "text": "x"}])])
        check("nudge: no usage is silent, exit 0",
              p.returncode == 0 and not p.stdout.strip(), "rc=%r out=%r" % (p.returncode, p.stdout))
        p = c.run(["--nudge"], {"session_id": c.session_id,
                                "transcript_path": os.path.join(c.root, "missing.jsonl"),
                                "stop_hook_active": False})
        check("nudge: unreadable transcript is silent, exit 0",
              p.returncode == 0 and not p.stdout.strip(), "rc=%r out=%r" % (p.returncode, p.stdout))
        put(c.nudge_path(), "{not json")
        p = nudge(c, 260000)
        check("nudge: corrupt state never exits 2", p.returncode == 0, "rc=%r" % p.returncode)
    finally:
        c.cleanup()


def set_limit(c, limit):
    put(os.path.join(c.cfg, "settings.json"), json.dumps({"autoCompactWindow": limit}))


def case_nudge_limit_checkpoints():
    Case.nudge_path = lambda self: os.path.join(
        self.cfg, "state", "handoff", "%s.nudge.json" % self.session_id)
    # default limit 500k (no settings.json): checkpoints 200k, then the top at 334k total
    c = Case("nlim5")
    try:
        nudge(c, 210000)
        p = nudge(c, 340000)
        check("limit: 340k blocks at the top checkpoint after 210k fired (500k limit)",
              is_block(c, p), "out=%r" % p.stdout)
        check("limit: 340k stores bucket 1", stored_bucket(c) == 1, "got %r" % stored_bucket(c))
        p = nudge(c, 460000)
        check("limit: 460k after the top is silent", p.returncode == 0 and not p.stdout.strip(),
              "out=%r" % p.stdout)
    finally:
        c.cleanup()
    c = Case("nlimexp")
    try:
        set_limit(c, 500000)
        nudge(c, 210000)
        p = nudge(c, 340000)
        check("limit: explicit 500k setting behaves like the default", is_block(c, p),
              "out=%r" % p.stdout)
    finally:
        c.cleanup()
    # unreadable settings: default 500k
    c = Case("nlimbad")
    try:
        put(os.path.join(c.cfg, "settings.json"), "{not json")
        nudge(c, 210000)
        p = nudge(c, 340000)
        check("limit: unreadable settings falls back to 500k", is_block(c, p),
              "out=%r" % p.stdout)
    finally:
        c.cleanup()
    # limit 800k: threshold 624k, so checkpoints 200k, 350k, then the top at 574k total
    c = Case("nlim8")
    try:
        set_limit(c, 800000)
        nudge(c, 410000)
        p = nudge(c, 455000)
        check("limit 800k: 455k silent after 410k fired (next is the top, 574k)",
              p.returncode == 0 and not p.stdout.strip(), "out=%r" % p.stdout)
        p = nudge(c, 755000)
        check("limit 800k: 755k blocks", is_block(c, p), "out=%r" % p.stdout)
        check("limit 800k: 755k stores bucket 2", stored_bucket(c) == 2,
              "got %r" % stored_bucket(c))
    finally:
        c.cleanup()
    # limit 200k: threshold 144k, top 94k total, the only checkpoint
    c = Case("nlim2")
    try:
        set_limit(c, 200000)
        p = nudge(c, 160000)
        check("limit 200k: 160k blocks", is_block(c, p), "out=%r" % p.stdout)
        check("limit 200k: 160k stores bucket 0", stored_bucket(c) == 0, "got %r" % stored_bucket(c))
    finally:
        c.cleanup()


def case_nudge_reads_messages_not_total():
    Case.nudge_path = lambda self: os.path.join(
        self.cfg, "state", "handoff", "%s.nudge.json" % self.session_id)
    # margin = min(50k, room/2): room -16k puts the top below zero, so any message count blocks.
    c = Case("nmsg1")
    try:
        set_limit(c, 200000)
        big = usage_line(160000)
        p = nudge(c, 0, overhead=None, lines=[big])
        check("messages: a 160k first turn alone is silent at limit 200k (messages 0)",
              p.returncode == 0 and not p.stdout.strip(), "out=%r" % p.stdout)
        p = nudge(c, 0, overhead=None, lines=[big, usage_line(160000)])
        check("messages: a second entry equal to the first (messages 0) is silent",
              p.returncode == 0 and not p.stdout.strip(), "out=%r" % p.stdout)
        p = nudge(c, 0, overhead=None, lines=[big, usage_line(175000)])
        check("messages: 15k messages after a 160k overhead blocks (room is short)",
              is_block(c, p), "out=%r" % p.stdout)
    finally:
        c.cleanup()
    # limit 500k, overhead 85k: first checkpoint at messages 200k = total 285k
    c = Case("nmsg2")
    try:
        first = usage_line(85000)
        p = nudge(c, 0, overhead=None, lines=[first, usage_line(284999)])
        check("messages: total 284,999 (messages 199,999) is silent at 85k overhead",
              p.returncode == 0 and not p.stdout.strip(), "out=%r" % p.stdout)
        # item 2 (75k drop): checkpoints(299000) = [249k]; the 200k floor is 49k under it, dropped.
        p = nudge(c, 0, overhead=None, lines=[first, usage_line(285000)])
        check("messages: total 285,000 (messages 200,000) is silent: the 200k floor is dropped",
              p.returncode == 0 and not p.stdout.strip() and stored_bucket(c) == -1,
              "out=%r bucket=%r" % (p.stdout, stored_bucket(c)))
        p = nudge(c, 0, overhead=None, lines=[first, usage_line(333999)])
        check("messages: total 333,999 is silent at bucket -1 (the one checkpoint is total 334k)",
              p.returncode == 0 and not p.stdout.strip() and stored_bucket(c) == -1,
              "out=%r bucket=%r" % (p.stdout, stored_bucket(c)))
        p = nudge(c, 0, overhead=None, lines=[first, usage_line(334000)])
        check("messages: total 334,000 blocks at the one checkpoint (bucket 0)",
              is_block(c, p) and stored_bucket(c) == 0,
              "out=%r bucket=%r" % (p.stdout, stored_bucket(c)))
        try:
            reason = json.loads(p.stdout).get("reason", "")
        except Exception:
            reason = ""
        check("messages: the text names the total and the messages",
              "Context is about 334k tokens, messages about 249k." in reason,
              "reason: %r" % reason)
    finally:
        c.cleanup()


def case_nudge_close_checkpoint_dropped_and_bogus_first_entry():
    Case.nudge_path = lambda self: os.path.join(
        self.cfg, "state", "handoff", "%s.nudge.json" % self.session_id)
    # 700k, overhead 90k: threshold 544k, room 454k, top 404k. A 350k checkpoint would sit 54k
    # below it, so it is dropped. At 500k no 350k step fits under the top, so the drop needs 700k.
    c = Case("nmsg3")
    try:
        set_limit(c, 700000)
        first = usage_line(90000)
        blocks = []
        for total in (290000, 430000, 440000, 494000):
            p = nudge(c, 0, overhead=None, lines=[first, usage_line(total)])
            blocks.append((total, is_block(c, p)))
        check("close checkpoint: one nudge between total 430k and 494k, none at 440k",
              blocks == [(290000, True), (430000, False), (440000, False), (494000, True)],
              "got %r" % blocks)
    finally:
        c.cleanup()
    # a bogus first entry is not the overhead
    for tag, bad in (("sidechain", entry(20000, side=True)),
                     ("synthetic", entry(20000, model="<synthetic>")),
                     ("zero usage", entry(0))):
        c = Case("nmsg4")
        try:
            p = nudge(c, 0, overhead=None, lines=[bad, usage_line(1000), usage_line(201000)])
            check("bogus first entry (%s) is not overhead: messages 200k blocks" % tag,
                  is_block(c, p), "out=%r" % p.stdout)
        finally:
            c.cleanup()


def entry(inp, model="claude-sonnet-5-5", side=False):
    obj = json.loads(usage_line(inp))
    obj["message"]["model"] = model
    if side:
        obj["isSidechain"] = True
    return json.dumps(obj)


def case_nudge_ignores_bogus_last_entries():
    Case.nudge_path = lambda self: os.path.join(
        self.cfg, "state", "handoff", "%s.nudge.json" % self.session_id)
    real = entry(250000)
    for tag, bad in (("synthetic zero-usage", entry(0, model="<synthetic>")),
                     ("non-synthetic zero-usage", entry(0)),
                     ("sidechain 20k", entry(20000, side=True))):
        c = Case("nbog")
        try:
            p = nudge(c, 0, lines=[real])
            check("bogus: 250k blocks (%s)" % tag, is_block(c, p), "out=%r" % p.stdout)
            p = nudge(c, 0, lines=[real, bad])
            check("bogus: last entry %s is silent" % tag,
                  p.returncode == 0 and not p.stdout.strip(), "out=%r" % p.stdout)
            check("bogus: last entry %s leaves bucket 0" % tag, stored_bucket(c) == 0,
                  "got %r" % stored_bucket(c))
            p = nudge(c, 0, lines=[real, bad, real])
            check("bogus: 250k again after %s is silent" % tag,
                  p.returncode == 0 and not p.stdout.strip(), "out=%r" % p.stdout)
        finally:
            c.cleanup()


def case_nudge_settings():
    with open(os.path.join(REPO_ROOT, "settings.json"), "r", encoding="utf-8") as f:
        stop = json.load(f).get("hooks", {}).get("Stop", [])
    cmds = [h.get("command", "") for g in stop for h in g.get("hooks", [])]
    check("settings: a Stop hook runs precompact_handoff.py with --nudge",
          any("precompact_handoff.py" in x and "--nudge" in x for x in cmds), "Stop: %r" % cmds)


# --------------------------------------------------------------------------- compact threshold
# Claude Code compacts at compact_threshold(window) = (window - 20k) * (1 - 0.2). The nudge's top
# checkpoint sits 50k below it, so the nudge comes before compaction. Under test: the module's
# compact_threshold. Loaded by path, so a missing name fails its checks instead of the whole run.


def under_test():
    spec = importlib.util.spec_from_file_location("precompact_handoff_under_test", MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def case_compact_threshold():
    for limit, want in ((500000, 384000), (200000, 144000)):
        try:
            got = under_test().compact_threshold(limit)
        except Exception as e:
            got = "%s: %s" % (type(e).__name__, e)
        check("threshold: compact_threshold(%d) is %d" % (limit, want), got == want,
              "got %r" % (got,))


def case_nudge_top_checkpoint_at_threshold():
    """500k window: the top checkpoint is threshold - 50k = 334k total. With a 30k overhead
    that is 304k messages, so the 340k case below blocks at the top bucket and nothing above
    it fires."""
    Case.nudge_path = lambda self: os.path.join(
        self.cfg, "state", "handoff", "%s.nudge.json" % self.session_id)
    first = usage_line(30000)
    c = Case("ntop1")
    try:
        p = nudge(c, 0, overhead=None, lines=[first, usage_line(340000)])
        check("top: a 340k transcript (30k overhead) blocks at the top bucket",
              is_block(c, p) and stored_bucket(c) == 1,
              "out=%r bucket=%r" % (p.stdout, stored_bucket(c)))
        p = nudge(c, 0, overhead=None, lines=[first, usage_line(445000)])
        check("top: 445k after 340k is not a new block (top bucket already reached)",
              p.returncode == 0 and not p.stdout.strip() and stored_bucket(c) == 1,
              "out=%r bucket=%r" % (p.stdout, stored_bucket(c)))
    finally:
        c.cleanup()
    c = Case("ntop2")
    try:
        p = nudge(c, 0, overhead=None, lines=[first, usage_line(240000)])
        check("top: 240k blocks at bucket 0 before the top",
              is_block(c, p) and stored_bucket(c) == 0,
              "out=%r bucket=%r" % (p.stdout, stored_bucket(c)))
        p = nudge(c, 0, overhead=None, lines=[first, usage_line(333999)])
        check("top: 333,999 is below the top checkpoint (silent, bucket 0)",
              p.returncode == 0 and not p.stdout.strip() and stored_bucket(c) == 0,
              "out=%r bucket=%r" % (p.stdout, stored_bucket(c)))
        p = nudge(c, 0, overhead=None, lines=[first, usage_line(334000)])
        check("top: 334,000 (threshold - 50k) reaches the top bucket",
              is_block(c, p) and stored_bucket(c) == 1,
              "out=%r bucket=%r" % (p.stdout, stored_bucket(c)))
    finally:
        c.cleanup()


def case_checkpoint_ladder():
    """checkpoints(room) on its own. The 200k floor goes when a step sits within 75k of the top
    (item 2 of precompact-handoff), and the top sits margin = min(50k, room/2) under the room."""
    for room, want in (
            (299000, [249000]),  # item 2 (75k drop): the 200k floor is 49k under the top
            (384000, [200000, 334000]),  # item 2: the floor is 134k under the top, so it stays
            (44000, [22000]),  # margin = min(50k, room/2): room 44k, top 22k
            (100000, [50000])):  # margin = min(50k, room/2): room 100k, the 50k cap
        try:
            got = under_test().checkpoints(room)
        except Exception as e:
            got = "%s: %s" % (type(e).__name__, e)
        check("ladder: checkpoints(%d) is %r" % (room, want), got == want, "got %r" % (got,))


def case_nudge_small_room_margin():
    """100k window, 20k overhead: room 44k, so the one checkpoint is margin = min(50k, room/2) =
    22k. The sizes are the last entry's total, so messages are 23k and 10k. size is unused when
    lines is given."""
    c = Case("nsmall43")
    try:
        set_limit(c, 100000)
        p = nudge(c, 0, overhead=20000, lines=[usage_line(43000)])
        check("small room: total 43k (messages 23k) blocks at the 22k top",
              is_block(c, p) and stored_bucket(c) == 0,
              "out=%r bucket=%r" % (p.stdout, stored_bucket(c)))
    finally:
        c.cleanup()
    c = Case("nsmall30")
    try:
        set_limit(c, 100000)
        p = nudge(c, 0, overhead=20000, lines=[usage_line(30000)])
        check("small room: total 30k (messages 10k) is silent below the 22k top",
              p.returncode == 0 and not p.stdout.strip(), "out=%r" % p.stdout)
    finally:
        c.cleanup()


# --------------------------------------------------------------------------- window tiers
# The nudge's window, highest first: env CLAUDE_CODE_AUTO_COMPACT_WINDOW, then
# modelSettings.<model>.autoCompactWindow, then top-level autoCompactWindow, then 500k. A bad
# value falls to the next tier. Model names are fake. 160k messages blocks only at a 200k window.

A_MODEL = "test-model-a"
B_MODEL = "test-model-b"
WINDOW_ENV = "CLAUDE_CODE_AUTO_COMPACT_WINDOW"


def ms(k, v, top=500000):
    return {"autoCompactWindow": top, "modelSettings": {k: {"autoCompactWindow": v}}}


# (name, settings.json as an object or raw text, extra env, transcript model, blocks?)
WINDOW_ROWS = [
    ("env wins over both settings tiers", ms(A_MODEL, 500000), {WINDOW_ENV: "200000"},
     A_MODEL, True),
    ("env wins with unreadable settings", "{bad", {WINDOW_ENV: "200000"}, A_MODEL, True),
    ("modelSettings exact key wins over top-level", ms(A_MODEL, 200000), None, A_MODEL, True),
    ("modelSettings exact key wins over an earlier [1m] key",
     {"autoCompactWindow": 500000, "modelSettings": {
         A_MODEL + "[1m]": {"autoCompactWindow": 900000},
         A_MODEL: {"autoCompactWindow": 200000}}}, None, A_MODEL, True),
    ("modelSettings matches a dated model", ms(A_MODEL, 200000), None,
     A_MODEL + "-20260101", True),
    ("modelSettings matches a [1m] model", ms(A_MODEL, 200000), None, A_MODEL + "[1m]", True),
    ("modelSettings [1m] key matches plain model", ms(A_MODEL + "[1m]", 200000), None,
     A_MODEL, True),
    ("modelSettings for another model is ignored", ms(B_MODEL, 200000), None, A_MODEL, False),
    ("modelSettings key is not a prefix match", ms("test-model", 200000), None, A_MODEL, False),
    ("modelSettings key longer than the model is ignored", ms(A_MODEL, 200000), None,
     "test-model", False),
    ("top-level fallback", ms(B_MODEL, 900000, top=200000), None, A_MODEL, True),
    ("bad env 'abc' falls to modelSettings", ms(A_MODEL, 200000), {WINDOW_ENV: "abc"},
     A_MODEL, True),
    ("bad env '0' falls through", {"autoCompactWindow": 500000}, {WINDOW_ENV: "0"},
     A_MODEL, False),
    ("bad env '-5' falls through", {"autoCompactWindow": 500000}, {WINDOW_ENV: "-5"},
     A_MODEL, False),
    ("bad modelSettings value true falls to top-level", ms(A_MODEL, True, top=600000), None,
     A_MODEL, False),
    ("bad modelSettings value '1' falls to top-level", ms(A_MODEL, "1", top=600000), None,
     A_MODEL, False),
    ("modelSettings entry not a dict falls to top-level",
     {"autoCompactWindow": 200000, "modelSettings": {A_MODEL: 5}}, None, A_MODEL, True),
    ("modelSettings not a dict falls to top-level",
     {"autoCompactWindow": 200000, "modelSettings": []}, None, A_MODEL, True),
    ("bad top-level falls to default 500k", {"autoCompactWindow": 0}, None, A_MODEL, False),
    ("settings not an object falls to default", "[1]", None, A_MODEL, False),
    ("no model in transcript uses top-level", ms(B_MODEL, 900000, top=200000), None, None, True),
]


def case_window_tiers_table():
    for name, settings, env, model, want in WINDOW_ROWS:
        c = Case("window", extra_env=env)
        try:
            put(os.path.join(c.cfg, "settings.json"),
                settings if isinstance(settings, str) else json.dumps(settings))
            p = nudge(c, 160000, model=model)  # 160k messages: blocks only at a 200k window
            check("window: " + name, is_block(c, p) == want,
                  "want block=%r, out=%r" % (want, p.stdout))
        finally:
            c.cleanup()


def case_window_tier_follows_transcript_model():
    """End to end through --nudge: the window is the one for the model of the last counted
    entry. A sidechain entry after it, on another model, is not counted."""
    c = Case("window_e2e")
    try:
        put(os.path.join(c.cfg, "settings.json"), json.dumps(
            {"autoCompactWindow": 500000,
             "modelSettings": {A_MODEL: {"autoCompactWindow": 200000},
                               B_MODEL: {"autoCompactWindow": 900000}}}))
        lines = [usage_line(1000, model=B_MODEL), usage_line(161000, model=A_MODEL),
                 entry(20000, model=B_MODEL, side=True)]
        p = nudge(c, 0, overhead=None, lines=lines)
        check("window e2e: the last counted entry's model picks the 200k window, so it blocks",
              is_block(c, p), "out=%r" % p.stdout)
    finally:
        c.cleanup()


def case_handoff_path_not_frozen():
    """Judge the path by guard's own rule 7 probe, `is_frozen`, with cfg as the config dir."""
    sys.path.insert(0, HERE)
    import guard
    c = Case("frozen")
    old = os.environ.get("CLAUDE_CONFIG_DIR")
    os.environ["CLAUDE_CONFIG_DIR"] = c.cfg  # same lookup as guard.config_dir()
    try:
        old_path = os.path.join(c.cfg, "state", "handoff", "%s.handoff.md" % c.session_id)
        check("frozen-probe: guard calls the old state/handoff path frozen",
              guard.is_frozen(old_path, c.repo) is True)
        m = re.search(r"Your handoff is (.+?\.md)\.", c.run_reorient().stdout or "")
        emitted = m.group(1) if m else ""
        check("handoff-path: the path the hook emits is not frozen (a session can write it)",
              bool(emitted) and guard.is_frozen(emitted, c.repo) is False,
              "emitted: %r" % emitted)
    finally:
        if old is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = old
        c.cleanup()


def case_handoffs_dir_is_made():
    """A fresh cfg has no handoffs dir. Each run that names the path must make it."""
    def has_dir(c):
        return os.path.isdir(os.path.dirname(c.handoff_path()))

    c = Case("hdir_reo")
    try:
        c.run_reorient()
        check("handoffs-dir: --reorient without a prior PreCompact makes it", has_dir(c))
    finally:
        c.cleanup()
    c = Case("hdir_reo2")
    try:
        tp = os.path.join(c.root, "transcript.jsonl")
        write_transcript(tp, [transcript_line("user", [{"type": "text", "text": "hello"}])])
        c.run_precompact(tp)
        shutil.rmtree(os.path.dirname(c.handoff_path()), ignore_errors=True)
        c.run_reorient()
        check("handoffs-dir: --reorient after a PreCompact makes it", has_dir(c))
    finally:
        c.cleanup()
    c = Case("hdir_nudge")
    try:
        p = nudge(c, 260000)
        check("handoffs-dir: a blocking --nudge makes it", is_block(c, p) and has_dir(c),
              "block=%r out=%r" % (is_block(c, p), p.stdout))
    finally:
        c.cleanup()
    c = Case("hdir_pre")
    try:
        tp = os.path.join(c.root, "transcript.jsonl")
        write_transcript(tp, [transcript_line("user", [{"type": "text", "text": "hello"}])])
        c.run_precompact(tp)
        check("handoffs-dir: PreCompact makes it", has_dir(c))
    finally:
        c.cleanup()


def case_handoffs_dir_keeps_other_sessions():
    """Another session's handoff stays untouched by reorient, a blocking nudge and PreCompact."""
    c = Case("hdir_keep")
    try:
        other = os.path.join(c.cfg, "handoffs", "other-session.md")
        put(other, "OTHER SESSION HANDOFF")
        tp = os.path.join(c.root, "transcript.jsonl")
        write_transcript(tp, [transcript_line("user", [{"type": "text", "text": "hello"}])])
        c.run_reorient()
        nudge(c, 260000)
        c.run_precompact(tp)
        try:
            with open(other, "r", encoding="utf-8") as f:
                got = f.read()
        except OSError:
            got = None
        check("handoffs-dir: another session's handoff file is kept, content unchanged",
              got == "OTHER SESSION HANDOFF", "got %r" % got)
    finally:
        c.cleanup()


# --------------------------------------------------------------------------- premises
# Spec to build: a handoff holds a `## Working premises` section, one line per premise:
#   - P<n> [<kind>] <statement> Source: <where>. Checked <date or never>.
# The kinds are ruling, measured, read, notes and assumed. After a compaction the reorient
# message lists every premise id except a `ruling`. After /clear or a fork it lists every id.

PREMISE_KIND_NAMES = {"ruling", "measured", "read", "notes", "assumed"}
HANDOFF_WITH_PREMISES = (
    "# Handoff\n\n## Goal\nFix the handoff. Source: owner 2026-10-21.\n\n"
    "## Working premises\n"
    "- P1 [ruling] An audit Explore may run Opus. Source: owner 2026-10-21, "
    "decisions/agent-model-cap.md. Checked 2026-10-21.\n"
    "- P2 [read] The guard denies only a Haiku model below the floor. Source: "
    "hooks/guard.py:1577 at 73ed71a7. Checked 2026-10-21.\n"
    "- P3 [measured] test_handoff_wave2 passes on this branch. Source: verdict run "
    "2026-10-21 14:02 CDT, at 9f1c2ab. Checked 2026-10-21.\n"
    "- P4 [notes] Lane A of c13 merged the config_watch fast exit. Source: roadmap c13 "
    "note. Checked never.\n"
    "- P5 [assumed] Agent hooks accept a full model id. Source: none. Checked never.\n\n"
    "## Next steps\n- Go on.\n")
NO_SECTION_MESSAGE = "no working premises section"
NOTES_SENTENCE = "facts in the compaction summary are notes until checked"


def ids_in(text):
    return set(re.findall(r"\bP\d+\b", text or ""))


def squash(text):
    return " ".join((text or "").lower().split())


def step_body(prompt_text, number):
    """The text of one numbered step of the prompt file, heading excluded; None when absent."""
    m = re.search(r"^## %d\.[^\n]*\n(.*?)(?=^## \d+\.|\Z)" % number, prompt_text, re.M | re.S)
    return m.group(1) if m else None


def case_prompt_lists_working_premises():
    with open(os.path.join(HERE, "precompact_handoff_prompt.md"), "r", encoding="utf-8") as f:
        text = f.read()
    step4 = step_body(text, 4) or ""
    low = step4.lower()
    check("prompt: step 4 still exists", bool(step4.strip()), "no '## 4.' step")
    pos = {k: low.find(k) for k in ("no home yet", "goal", "working premises", "where things stand")}
    check("prompt: step 4 names Goal and Working premises",
          pos["goal"] >= 0 and pos["working premises"] >= 0, "positions: %r" % pos)
    check("prompt: Goal and Working premises come second, after NO HOME YET and before "
          "Where things stand",
          0 <= pos["no home yet"] < pos["goal"] < pos["working premises"]
          < pos["where things stand"], "positions: %r" % pos)
    heads = re.findall(r"^## \d+\.[^\n]*check premises[^\n]*\n(.*?)(?=^## |\Z)", text,
                       re.M | re.S | re.I)
    check("prompt: a numbered step 'Check premises' exists", len(heads) == 1,
          "found %d" % len(heads))
    body = heads[0].lower() if heads else ""
    check("prompt: Check premises says a premise is a statement, weak or stale ones are "
          "checked first, then the line is rewritten",
          "statement" in body and ("weak" in body or "stale" in body) and "rewrite" in body,
          "body: %r" % body[:200])


LIST_HOME_WANTS = (
    ("the word 'list'", r"\blists?\b"),
    ("'copy' or 'copies'", r"\b(?:copy|copies)\b"),
    ("a negation: 'never', 'not' or \"don't\"", r"\b(?:never|not|don['’]t)\b"),
    ("a home: 'page', 'roadmap' or 'git ref'", r"\b(?:pages?|roadmaps?|git refs?)\b"),
)


def list_home_missing(step_text):
    """The wants the closest window of step_text lacks; empty when one window holds all four.

    A window is one sentence or bullet, or that unit plus the sentence right after it. All
    four wants must sit in one window, so words spread over the step (a "never" far from any
    list) cannot satisfy it.
    """
    # A bullet marker after a sentence end splits twice, which leaves an empty unit: drop it,
    # or it would sit between two neighbours and break their window.
    units = [squash(u) for u in re.split(r"(?<=[.!?])\s+|^\s*[-*]\s+", step_text, flags=re.M)]
    units = [u for u in units if u]
    windows = units + [a + " " + b for a, b in zip(units, units[1:])]
    best = [label for label, _ in LIST_HOME_WANTS]
    for window in windows:
        miss = [label for label, rx in LIST_HOME_WANTS if not re.search(rx, window)]
        if len(miss) < len(best):
            best = miss
    return best


def case_prompt_names_list_home_not_copy():
    # Step 4 must say to name where a list lives and never to copy it: a copy goes stale.
    with open(os.path.join(HERE, "precompact_handoff_prompt.md"), "r", encoding="utf-8") as f:
        text = f.read()
    step4 = step_body(text, 4) or ""
    check("prompt: step 4 still exists (list-home check)", bool(step4.strip()), "no '## 4.' step")
    missing = list_home_missing(step4)
    check("prompt: a sentence or bullet of step 4, with the sentence after it, says to name "
          "where a list lives (a page, a roadmap ref or a git ref) and never to copy the list",
          not missing,
          "no window of step 4 holds all four; the closest lacks: %s" % "; ".join(missing))


def write_compaction(c):
    tp = os.path.join(c.root, "transcript.jsonl")
    write_transcript(tp, [transcript_line("user", [{"type": "text", "text": "hello"}])])
    c.run_precompact(tp)


def case_reorient_lists_weak_premises():
    for tag, with_digest in (("digest ok", True), ("digest missing", False)):
        c = Case("weak_" + tag.split()[1])
        try:
            if with_digest:
                write_compaction(c)
            put(c.handoff_path(), HANDOFF_WITH_PREMISES)
            proc = c.run_reorient()
            out = proc.stdout or ""
            ids = ids_in(out)
            check("weak premises (%s): exits 0" % tag, proc.returncode == 0,
                  "rc=%r err=%r" % (proc.returncode, proc.stderr[-200:]))
            check("weak premises (%s): lists P2 read, P3 measured, P4 notes, P5 assumed" % tag,
                  {"P2", "P3", "P4", "P5"} <= ids, "listed: %r" % sorted(ids))
            check("weak premises (%s): does not list the ruling P1" % tag, "P1" not in ids,
                  "listed: %r" % sorted(ids))
            check("weak premises (%s): says summary facts are notes until checked" % tag,
                  NOTES_SENTENCE in squash(out), "stdout: %r" % out[-300:])
            check("weak premises (%s): calls no model" % tag, not c.claude_was_called())
        finally:
            c.cleanup()


def case_reorient_premise_lines_survive_odd_text():
    """The parser reads text, not code, but a premise line holds comment openers, a lone quote
    and a wrapped backtick span. The line after it must still be listed."""
    odd = ("## Working premises\n"
           "- P6 [notes] Docs say: don't use // or /* here (see # note), a lone \" quote, and "
           "a `span\n  that wraps` over two lines. Source: https://example.com/a//b. "
           "Checked never.\n"
           "- P7 [assumed] After the odd line. Source: none. Checked never.\n")
    c = Case("odd")
    try:
        put(c.handoff_path(), odd)
        out = c.run_reorient().stdout or ""
        check("odd text: lists P6 and the P7 that follows it", {"P6", "P7"} <= ids_in(out),
              "listed: %r" % sorted(ids_in(out)))
    finally:
        c.cleanup()


def case_reorient_flags_missing_premises():
    cases = (
        ("no section", "# Handoff\n\n## Next steps\n- Go on.\n", True),
        ("section with no premise line", "## Working premises\nNothing here yet.\n", True),
        ("section with premises (twin)", HANDOFF_WITH_PREMISES, False),
    )
    for i, (tag, text, want_warning) in enumerate(cases):
        for with_digest in (True, False):
            c = Case("miss%d%d" % (i, with_digest))
            label = "%s, %s" % (tag, "digest ok" if with_digest else "digest missing")
            try:
                if with_digest:
                    write_compaction(c)
                put(c.handoff_path(), text)
                proc = c.run_reorient()
                low = squash(proc.stdout)
                check("missing premises (%s): exits 0" % label, proc.returncode == 0,
                      "rc=%r err=%r" % (proc.returncode, proc.stderr[-200:]))
                if want_warning:
                    check("missing premises (%s): says the handoff has no Working premises "
                          "section and to add it per step 4" % label,
                          NO_SECTION_MESSAGE in low and "step 4" in low,
                          "stdout: %r" % low[-300:])
                else:
                    check("missing premises (%s): no warning" % label,
                          NO_SECTION_MESSAGE not in low, "stdout: %r" % low[-300:])
                check("missing premises (%s): says summary facts are notes until checked" % label,
                      NOTES_SENTENCE in low, "stdout: %r" % low[-300:])
            finally:
                c.cleanup()


def _not_utf8(data):
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


UNREADABLE_WORDS = re.compile(r"unreadable|not readable|could not (?:be )?read|cannot be read|"
                              r"can't (?:be )?read|unable to read")


def case_reorient_survives_undecodable_handoff():
    """A handoff with one byte that is not UTF-8 (a cut write, a paste from another code page)
    must not silence the reorient message: it is the only thing that sends the session back to
    its handoff. The premises read as none or unreadable (or are read past the bad byte); the
    rest of the message stays whole. Three paths: compaction with and without a digest, and a
    fork (which lists every premise)."""
    base = HANDOFF_WITH_PREMISES.encode("utf-8")
    variants = (
        ("stray 0xff in the Goal", base.replace(b"Fix the handoff.", b"Fix the \xff handoff.")),
        ("cut multi-byte char in a premise line",
         base.replace(b"passes on this branch.", b"passes on this branch \xe2\x82.")),
    )
    for vi, (vtag, data) in enumerate(variants):
        check("undecodable (%s): the test bytes are not UTF-8" % vtag,
              data != base and _not_utf8(data))
        for mi, mode in enumerate(("compaction, digest ok", "compaction, digest missing", "fork")):
            label = "%s, %s" % (vtag, mode)
            c = Case("badbyte%d%d" % (vi, mi))
            try:
                if mode == "fork":
                    other = "sess-other"
                    old = os.path.join(c.cfg, "handoffs", other + ".md")
                    os.makedirs(os.path.dirname(old), exist_ok=True)
                    with open(old, "wb") as f:
                        f.write(data)
                    put(os.path.join(c.cfg, "state", "handoff", other + ".dir"), c.repo)
                    proc = c.run(["--reorient"], {"session_id": c.session_id, "source": "fork",
                                                  "hook_event_name": "SessionStart",
                                                  "cwd": c.repo})
                else:
                    if mode.endswith("digest ok"):
                        write_compaction(c)
                    os.makedirs(os.path.dirname(c.handoff_path()), exist_ok=True)
                    with open(c.handoff_path(), "wb") as f:
                        f.write(data)
                    proc = c.run_reorient()
                out = proc.stdout or ""
                low = squash(out)
                why = "rc=%r stdout=%r stderr=%r" % (proc.returncode, out[-200:],
                                                     proc.stderr[-200:])
                check("undecodable (%s): exits 0" % label, proc.returncode == 0, why)
                check("undecodable (%s): the reorient message still prints, with the prompt "
                      "file and the session's own handoff path" % label,
                      c.prompt_path() in out and c.handoff_path() in out, why)
                if mode == "fork":
                    check("undecodable (%s): names the handoff to read" % label, old in out, why)
                else:
                    check("undecodable (%s): says summary facts are notes until checked" % label,
                          NOTES_SENTENCE in low, why)
                    if mode.endswith("digest ok"):
                        check("undecodable (%s): names the digest path" % label,
                              c.digest_path() in out, why)
                check("undecodable (%s): premises read as none, unreadable, or past the bad "
                      "byte" % label,
                      NO_SECTION_MESSAGE in low or bool(UNREADABLE_WORDS.search(low))
                      or {"P2", "P3", "P4", "P5"} <= ids_in(out), why)
            finally:
                c.cleanup()


def case_nudge_points_at_step4():
    Case.nudge_path = lambda self: os.path.join(
        self.cfg, "state", "handoff", "%s.nudge.json" % self.session_id)
    c = Case("nudge4")
    try:
        p = nudge(c, 260000)
        check("nudge step 4: still blocks, naming the handoff and the prompt file",
              is_block(c, p), "out=%r" % p.stdout)
        try:
            reason = json.loads(p.stdout).get("reason", "")
        except Exception:
            reason = ""
        low = squash(reason)
        check("nudge step 4: the reason names step 4", "step 4" in low, "reason: %r" % reason)
        copied = [s for s in ("no home yet", "where things stand", "rulings with their homes",
                              "work in flight", "files and commands") if s in low]
        check("nudge step 4: the reason copies no part of the section list (step 4 is its "
              "one home)", not copied, "copied: %r" % copied)
    finally:
        c.cleanup()


KIND_ROW = re.compile(r"^\|\s*`([a-z]+)`\s*\|", re.M)


def case_premise_kinds_one_home():
    """The kinds the parser accepts are the kinds the record lists: one home, no copy.
    Parser seam: precompact_handoff.PREMISE_KINDS (any iterable of the kind names).
    Record: decisions/premise-format.md, one table row per kind, the kind in backticks in
    the first cell. Exactly one decision may carry that table."""
    homes = {}
    ddir = os.path.join(REPO_ROOT, "docs", "decisions")
    for name in sorted(os.listdir(ddir)):
        if name.endswith(".md"):
            with open(os.path.join(ddir, name), "r", encoding="utf-8") as f:
                kinds = KIND_ROW.findall(f.read())
            if "assumed" in kinds:
                homes[name] = set(kinds)
    check("kinds home: decisions/premise-format.md lists the kinds, and no other decision does",
          list(homes) == ["premise-format.md"], "decisions with a kinds table: %r" % list(homes))
    record = homes.get("premise-format.md", set())
    check("kinds home: the record lists at least ruling, measured, read, notes, assumed",
          PREMISE_KIND_NAMES <= record, "record kinds: %r" % sorted(record))
    code = None
    try:
        spec = importlib.util.spec_from_file_location("precompact_handoff_under_test", MODULE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        code = set(getattr(mod, "PREMISE_KINDS"))
    except Exception as e:
        print("kinds home: no usable PREMISE_KINDS in the module: %r" % e)
    check("kinds home: the parser's PREMISE_KINDS exists and is not empty", bool(code),
          "got %r" % code)
    check("kinds home: PREMISE_KINDS equals the record's kinds", bool(code) and code == record,
          "code %r, record %r" % (sorted(code or []), sorted(record)))
    with open(os.path.join(HERE, "precompact_handoff_prompt.md"), "r", encoding="utf-8") as f:
        prompt = f.read()
    shown = {k for k in PREMISE_KIND_NAMES
             if re.search(r"\[[^\]\n]*\b%s\b[^\]\n]*\]" % k, prompt)}
    check("kinds home: the prompt shows each kind in brackets, so a session writes a kind the "
          "parser accepts", shown == PREMISE_KIND_NAMES, "shown: %r" % sorted(shown))


# Runs `--reorient` in a child where precompact_handoff.PREMISE_KINDS is replaced by argv[2]
# before main() runs, so a test can change the constant without touching the file.
PATCHED_REORIENT = (
    "import importlib.util, json, os, sys\n"
    "sys.path.insert(0, os.path.dirname(sys.argv[1]))\n"
    "spec = importlib.util.spec_from_file_location('precompact_handoff_patched', sys.argv[1])\n"
    "mod = importlib.util.module_from_spec(spec)\n"
    "spec.loader.exec_module(mod)\n"
    "if len(sys.argv) > 2:\n"
    "    mod.PREMISE_KINDS = tuple(json.loads(sys.argv[2]))\n"
    "sys.argv = [sys.argv[1], '--reorient']\n"
    "sys.exit(mod.main())\n")


def premises_listed(c, kinds_of_lines, patched_kinds=None):
    """Write a handoff with one premise per entry of kinds_of_lines (P1, P2, ...; None writes
    no [kind] at all), run the compaction reorient, and return (ids it lists, the process).
    patched_kinds replaces PREMISE_KINDS in the child; None leaves the module's own."""
    text = "## Working premises\n" + "".join(
        "- P%d%s A statement. Source: none. Checked never.\n"
        % (i, "" if k is None else " [%s]" % k) for i, k in enumerate(kinds_of_lines, 1))
    put(c.handoff_path(), text)
    args = [sys.executable, "-c", PATCHED_REORIENT, MODULE]
    if patched_kinds is not None:
        args.append(json.dumps(list(patched_kinds)))
    payload = {"session_id": c.session_id, "hook_event_name": "SessionStart",
               "source": "compact", "cwd": c.repo}
    proc = subprocess.run(args, input=json.dumps(payload), capture_output=True, text=True,
                          env=c.env(), cwd=c.repo)
    return ids_in(proc.stdout), proc


def case_premise_strength_comes_from_kinds():
    """The parser's strong/weak split comes from PREMISE_KINDS, not from a kind named in code.
    Seam (the record says the kinds run strongest first): at reorient time the first entry of
    precompact_handoff.PREMISE_KINDS is the one kind a compaction reorient leaves out of its
    list; every other entry, and every kind outside the constant, is listed. The constant is
    read at call time, so a test can replace it."""
    mod_kinds = None
    try:
        spec = importlib.util.spec_from_file_location("precompact_handoff_kinds", MODULE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod_kinds = tuple(mod.PREMISE_KINDS)
    except Exception as e:
        print("strength: no usable PREMISE_KINDS in the module: %r" % e)
    check("strength: PREMISE_KINDS lists the strongest kind first, `ruling`, as the record does",
          bool(mod_kinds) and mod_kinds[0] == "ruling", "got %r" % (mod_kinds,))
    if not mod_kinds:
        return
    c = Case("strength")
    try:
        # Every kind in the constant is classified, and a kind outside it is weak: a kind the
        # record does not list, an empty [], and no brackets at all.
        outside = ["final", "", None]
        probe = list(mod_kinds) + outside
        listed, proc = premises_listed(c, probe)
        want = {"P%d" % i for i in range(2, len(probe) + 1)}
        check("strength: the first kind of PREMISE_KINDS is the only one left out; the rest of "
              "the constant, an unknown kind, an empty [] and no kind are all listed",
              listed == want, "listed %r, want %r, stderr %r"
              % (sorted(listed), sorted(want), proc.stderr[-200:]))
        # Rename the strongest kind in the constant: the new name is now left out, and the old
        # name, now outside the constant, is listed. A literal "ruling" in the parser fails this.
        renamed = ("decree",) + mod_kinds[1:]
        listed, proc = premises_listed(c, ["decree", "ruling", mod_kinds[1]], renamed)
        check("strength: with PREMISE_KINDS = decree first, a [decree] premise is left out and "
              "a [ruling] premise is listed (the strong kind is read from the constant, not "
              "named in the parser)",
              listed == {"P2", "P3"}, "listed %r, want ['P2', 'P3'], stderr %r"
              % (sorted(listed), proc.stderr[-200:]))
    finally:
        c.cleanup()


# --------------------------------------------------------------------------- the run


def main() -> int:
    case_precompact_writes_digest_and_state()
    case_precompact_error_is_ok_false()
    case_reorient_ok_names_prompt_and_digest()
    case_reorient_no_state_says_digest_missing()
    case_reorient_failed_state_says_digest_missing()
    case_settings_json()
    case_nudge()
    case_nudge_exact_boundary()
    case_nudge_uses_last_assistant_entry_and_sums_cache()
    case_nudge_stop_hook_active()
    case_nudge_failures_are_silent()
    case_nudge_limit_checkpoints()
    case_nudge_reads_messages_not_total()
    case_nudge_close_checkpoint_dropped_and_bogus_first_entry()
    case_nudge_ignores_bogus_last_entries()
    case_nudge_settings()
    case_compact_threshold()
    case_nudge_top_checkpoint_at_threshold()
    case_checkpoint_ladder()
    case_nudge_small_room_margin()
    case_window_tiers_table()
    case_window_tier_follows_transcript_model()
    case_handoff_path_not_frozen()
    case_handoffs_dir_is_made()
    case_handoffs_dir_keeps_other_sessions()
    case_prompt_lists_working_premises()
    case_prompt_names_list_home_not_copy()
    case_reorient_lists_weak_premises()
    case_reorient_premise_lines_survive_odd_text()
    case_reorient_flags_missing_premises()
    case_reorient_survives_undecodable_handoff()
    case_nudge_points_at_step4()
    case_premise_kinds_one_home()
    case_premise_strength_comes_from_kinds()

    if FAILED:
        print()
        print("test_precompact_handoff FAIL: %d failing check(s)" % len(FAILED))
        return 1
    print()
    print("test_precompact_handoff PASS: all checks right")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        shutil.rmtree(RUN_FOLDER, ignore_errors=True)
