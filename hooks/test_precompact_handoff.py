#!/usr/bin/env python3
"""Cases for hooks/precompact_handoff.py. Standard library only, and no test runner.

Run it from the repository root:

    python hooks/test_precompact_handoff.py

Spec: decisions/precompact-handoff.md, rewritten 2026-10-03: no `claude -p` child, no
second login. PreCompact writes a digest file and a state file. Reorient prints a message
naming the prompt file and the digest, and never spawns anything.

RED BEFORE GREEN. As of this file's own red run, `hooks/precompact_handoff.py` still runs
a `claude -p` child (the OLD design) -- so the "never calls claude" case must fail red, for
that exact reason, not a crash.

Each case gets its own temp root: a real git repo (the hook's `cwd`, and its own top
level), a `CLAUDE_CONFIG_DIR`, and a `bin` dir on PATH holding a fake `claude` (the same
extension-less-plus-`.cmd`-shim trick `put_shim` uses in merge/test_merge.py, needed because
Windows `shutil.which` never matches an extension-less script). The fake only records that
it ran -- this spec never calls it, so any record at all is the defect.
"""
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

    def __init__(self, name):
        self.root = tempfile.mkdtemp(prefix="precompact_%s_" % name)
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
        env["CLAUDE_CONFIG_DIR"] = self.cfg
        env["PATH"] = self.bin + os.pathsep + env.get("PATH", "")
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
    # Not pinning a timeout value here: the owner's rewritten design does its work inline,
    # with no model call to budget for, so a timeout number is the builder's call to make.
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
# Owner ruling 2026-10-07: on Stop, `--nudge` blocks once per 100k bucket from 200k up.


def usage_line(inp, cc=0, cr=0):
    return json.dumps({"type": "assistant", "timestamp": "2026-10-07T10:00:00Z",
                       "message": {"content": [{"type": "text", "text": "hi"}],
                                   "usage": {"input_tokens": inp,
                                             "cache_creation_input_tokens": cc,
                                             "cache_read_input_tokens": cr,
                                             "output_tokens": 5}}})


def nudge(c, size, active=False, lines=None, seed=None):
    """Run --nudge once. `size` is split across the three input counters."""
    tp = os.path.join(c.root, "t.jsonl")
    if lines is None:
        lines = [usage_line(size - 60000 - 30000, 30000, 60000)]
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

        p = nudge(c, 250000)
        check("nudge: 250k after 210k is silent", p.returncode == 0 and not p.stdout.strip(),
              "out=%r" % p.stdout)
        check("nudge: 250k keeps bucket 0", stored_bucket(c) == 0, "got %r" % stored_bucket(c))

        p = nudge(c, 310000)
        check("nudge: 310k blocks", is_block(c, p), "out=%r" % p.stdout)
        check("nudge: 310k stores bucket 1", stored_bucket(c) == 1, "got %r" % stored_bucket(c))

        p = nudge(c, 410000)
        check("nudge: 410k blocks", is_block(c, p), "out=%r" % p.stdout)
        check("nudge: 410k stores bucket 2", stored_bucket(c) == 2, "got %r" % stored_bucket(c))

        p = nudge(c, 120000)
        check("nudge: 120k after 410k (compaction) is silent",
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
        lines = [usage_line(500000), usage_line(1000, 100000, 120000)]  # last = 221000
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
        p = nudge(c, 0, lines=[transcript_line("assistant", [{"type": "text", "text": "x"}])])
        check("nudge: no usage is silent, exit 0",
              p.returncode == 0 and not p.stdout.strip(), "rc=%r out=%r" % (p.returncode, p.stdout))
        p = c.run(["--nudge"], {"session_id": c.session_id,
                                "transcript_path": os.path.join(c.root, "missing.jsonl"),
                                "stop_hook_active": False})
        check("nudge: unreadable transcript is silent, exit 0",
              p.returncode == 0 and not p.stdout.strip(), "rc=%r out=%r" % (p.returncode, p.stdout))
        put(c.nudge_path(), "{not json")
        p = nudge(c, 210000)
        check("nudge: corrupt state never exits 2", p.returncode == 0, "rc=%r" % p.returncode)
    finally:
        c.cleanup()


def set_limit(c, limit):
    put(os.path.join(c.cfg, "settings.json"), json.dumps({"autoCompactWindow": limit}))


def case_nudge_limit_checkpoints():
    Case.nudge_path = lambda self: os.path.join(
        self.cfg, "state", "handoff", "%s.nudge.json" % self.session_id)
    # default limit 500k (no settings.json): checkpoints 200,300,400,450
    c = Case("nlim5")
    try:
        nudge(c, 410000)
        p = nudge(c, 455000)
        check("limit: 455k blocks after 410k fired (limit-50k checkpoint, 500k limit)",
              is_block(c, p), "out=%r" % p.stdout)
        check("limit: 455k stores bucket 3", stored_bucket(c) == 3, "got %r" % stored_bucket(c))
        p = nudge(c, 460000)
        check("limit: 460k after 455k is silent", p.returncode == 0 and not p.stdout.strip(),
              "out=%r" % p.stdout)
    finally:
        c.cleanup()
    c = Case("nlimexp")
    try:
        set_limit(c, 500000)
        nudge(c, 410000)
        p = nudge(c, 455000)
        check("limit: explicit 500k setting behaves like the default", is_block(c, p),
              "out=%r" % p.stdout)
    finally:
        c.cleanup()
    # unreadable settings: default 500k
    c = Case("nlimbad")
    try:
        put(os.path.join(c.cfg, "settings.json"), "{not json")
        nudge(c, 410000)
        p = nudge(c, 455000)
        check("limit: unreadable settings falls back to 500k", is_block(c, p),
              "out=%r" % p.stdout)
    finally:
        c.cleanup()
    # limit 800k: 200..700, then 750
    c = Case("nlim8")
    try:
        set_limit(c, 800000)
        nudge(c, 410000)
        p = nudge(c, 455000)
        check("limit 800k: 455k silent after 410k fired (next is 500k)",
              p.returncode == 0 and not p.stdout.strip(), "out=%r" % p.stdout)
        p = nudge(c, 755000)
        check("limit 800k: 755k blocks", is_block(c, p), "out=%r" % p.stdout)
        check("limit 800k: 755k stores bucket 6", stored_bucket(c) == 6, "got %r" % stored_bucket(c))
    finally:
        c.cleanup()
    # limit 200k: limit-50k = 150k <= 200k, only checkpoint is 150k
    c = Case("nlim2")
    try:
        set_limit(c, 200000)
        p = nudge(c, 160000)
        check("limit 200k: 160k blocks", is_block(c, p), "out=%r" % p.stdout)
        check("limit 200k: 160k stores bucket 0", stored_bucket(c) == 0, "got %r" % stored_bucket(c))
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
        p = nudge(c, 210000)
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
        put(other, "OTHER SESSION HANDOFF
")
        tp = os.path.join(c.root, "transcript.jsonl")
        write_transcript(tp, [transcript_line("user", [{"type": "text", "text": "hello"}])])
        c.run_reorient()
        nudge(c, 210000)
        c.run_precompact(tp)
        try:
            with open(other, "r", encoding="utf-8") as f:
                got = f.read()
        except OSError:
            got = None
        check("handoffs-dir: another session's handoff file is kept, content unchanged",
              got == "OTHER SESSION HANDOFF
", "got %r" % got)
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
    case_nudge_ignores_bogus_last_entries()
    case_nudge_settings()
    case_handoff_path_not_frozen()
    case_handoffs_dir_is_made()
    case_handoffs_dir_keeps_other_sessions()

    if FAILED:
        print()
        print("test_precompact_handoff FAIL: %d failing check(s)" % len(FAILED))
        return 1
    print()
    print("test_precompact_handoff PASS: all checks right")
    return 0


if __name__ == "__main__":
    sys.exit(main())
