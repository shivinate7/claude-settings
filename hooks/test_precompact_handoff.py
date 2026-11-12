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
import datetime
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
        # Each case sets its own window and flags. This run's shell may set the remote knobs (a
        # cloud session sets CLAUDE_CODE_REMOTE and CLAUDE_AUTOCOMPACT_PCT_OVERRIDE), and
        # CLAUDE_CODE_ENTRYPOINT picks the flag table's column, so none of them leaks in.
        # CLAUDE_CODE_REMOTE_SESSION_ID is the cloud session's own id (cse_<x>): a case that needs it sets
        # it through extra_env, so no other case inherits the run's own id.
        for name in ("CLAUDE_CODE_AUTO_COMPACT_WINDOW", "CLAUDE_CODE_REMOTE",
                     "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE", "CLAUDE_CODE_ENTRYPOINT",
                     "CLAUDE_CODE_REMOTE_SESSION_ID"):
            env.pop(name, None)
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

    def set_flags(self, features):
        """Write <config dir>/.claude.json with the cached feature flags summary_fraction reads."""
        put(os.path.join(self.cfg, ".claude.json"),
            json.dumps({"cachedGrowthBookFeatures": features}))

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
    # R40, the owner's compaction ruling (13:21 CST, Nov 11, "compaction: A"), sets the
    # compaction trigger to 92 in the settings env.
    check("settings: CLAUDE_AUTOCOMPACT_PCT_OVERRIDE is \"92\" (R40)",
          env.get("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE") == "92",
          "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE: %r" % env.get("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"))

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


def nudge(c, size, active=False, lines=None, seed=None, overhead=NUDGE_OVERHEAD, model=None,
          extra=None, via=None):
    """Run --nudge once. A first-turn entry of `overhead` tokens comes first, so the hook
    reads messages = `size` (default: last entry = size + overhead, split across the three
    input counters). With explicit `lines`, they follow the overhead entry. overhead=None
    prepends nothing. model, when set, names the model of the default entry. extra adds keys
    to the payload (an agent_id, for one); via runs the hook some way other than c.run."""
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
    payload.update(extra or {})
    return (via or c.run)(["--nudge"], payload)


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
    # room <= 0 keeps margin 50k: room -16k puts the top below zero, so any message count blocks.
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
        check("messages: the text cites decision precompact-handoff",
              "decision precompact-handoff" in reason, "reason: %r" % reason)
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
# Claude Code compacts at compact_threshold(limit) = min(E - round(E * f), E - 13k), with
# E = limit - 20k and f = summary_fraction(limit), read from the flag file (default 0.2). The
# nudge's top checkpoint sits 50k below it, so the nudge comes before compaction. Under test: the
# module's compact_threshold. Loaded by path, so a missing name fails its checks instead of the run.


def under_test():
    spec = importlib.util.spec_from_file_location("precompact_handoff_under_test", MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def case_compact_threshold():
    """The flag file holds the fraction 0.2, so these are the values from before the flag."""
    c = Case("cthr")
    try:
        c.set_flags(fraction_flags(0.2))
        for limit, want in ((500000, 384000), (200000, 144000)):
            got, err = threshold_at(c, limit)
            expect_value("threshold: compact_threshold(%d) is %d" % (limit, want), got, err, want)
    finally:
        c.cleanup()


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
    """checkpoints(room) on its own. The 200k floor goes when a step sits under 75k below the top
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
    # F2: the env var takes a k/m suffix.
    ("F2: env '200k' is a 200k window", {"autoCompactWindow": 500000}, {WINDOW_ENV: "200k"},
     A_MODEL, True),
    # W: a settings.json string is ignored, so the 500k default applies and 160k does not block.
    ("W: top-level '200K' string is ignored, 500k applies", {"autoCompactWindow": "200K"}, None,
     A_MODEL, False),
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


# F2, W: the env var takes the CLI's suffix forms (200k, 1m, 1.5m, any case). W: the env value is
# clamped to 100,000..1,000,000, so 1.5m is 1,000,000.
WINDOW_FORMS = (("200k", 200000), ("1m", 1000000), ("1.5m", 1000000),
                ("200K", 200000), ("1M", 1000000), ("1.5M", 1000000))


def window_at(c, env_value=None, settings=None, model=None):
    """window_limit(model) with the case's config dir. settings.json holds `settings` when it is
    not None, else is absent. As (value, error)."""
    path = os.path.join(c.cfg, "settings.json")
    if os.path.isfile(path):
        os.remove(path)
    if settings is not None:
        put(path, json.dumps(settings))
    with Env(CLAUDE_CONFIG_DIR=c.cfg, CLAUDE_CODE_AUTO_COMPACT_WINDOW=env_value):
        return call_under_test("window_limit", model)


def case_window_limit_suffix_forms():
    """F2, W: each suffix form gives its token count in the env var, clamped at 1,000,000. A
    settings.json string is ignored, so it falls to the 500k default. A value that is not a
    number and not a suffix form ('abc') still falls to the next tier."""
    c = Case("wsuffix")
    try:
        for text, want in WINDOW_FORMS:
            got, err = window_at(c, env_value=text)
            expect_value("window: env %r is %d" % (text, want), got, err, want)
        # W: settings strings do not count, so each suffix form falls to the default.
        for text, _ in WINDOW_FORMS:
            got, err = window_at(c, settings={"autoCompactWindow": text})
            expect_value("window: top-level autoCompactWindow %r is ignored, 500,000" % text,
                         got, err, 500000)
        # W: a modelSettings string is ignored too.
        got, err = window_at(c, model=A_MODEL,
                             settings={"modelSettings": {A_MODEL: {"autoCompactWindow": "1.5m"}}})
        expect_value("window: modelSettings autoCompactWindow '1.5m' is ignored, 500,000",
                     got, err, 500000)
        # W: the top-level fallback is an int now, since a settings string is ignored.
        got, err = window_at(c, env_value="abc", settings={"autoCompactWindow": 200000})
        expect_value("window: env 'abc' falls to top-level 200,000", got, err, 200000)
        got, err = window_at(c, settings={"autoCompactWindow": "abc"})
        expect_value("window: top-level 'abc' falls to the 500k default", got, err, 500000)
    finally:
        c.cleanup()


# W (round-2 finding, Claude Code 2.1.316): only the env var takes a k/m suffix, and its value is
# clamped to 100,000..1,000,000. settings.json counts only ints in that range. A string, or an int
# outside it, falls to the next tier.
WINDOW_VALUE_ROWS = (
    # (name, env value, settings.json object, want)
    ("env '1.5m' clamps to 1,000,000", "1.5m", None, 1000000),
    ("env '2m' clamps to 1,000,000", "2m", None, 1000000),
    ("env '200' clamps to 100,000", "200", None, 100000),
    ("env '200k' is 200,000", "200k", None, 200000),
    ("env '500K' is 500,000", "500K", None, 500000),
    ("settings '1m' is ignored, 500,000", None, {"autoCompactWindow": "1m"}, 500000),
    ("settings 2,000,000 is ignored, 500,000", None, {"autoCompactWindow": 2000000}, 500000),
    ("settings 50,000 is ignored, 500,000", None, {"autoCompactWindow": 50000}, 500000),
    ("settings 300,000 is 300,000", None, {"autoCompactWindow": 300000}, 300000),
)


def case_window_value_rows():
    """W: window_limit's value for each row, with the env var and settings.json as given."""
    c = Case("wvalue")
    try:
        for name, env_value, settings, want in WINDOW_VALUE_ROWS:
            got, err = window_at(c, env_value=env_value, settings=settings)
            expect_value("W: window " + name, got, err, want)
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


def window_missing(step_text, wants, span=2):
    """The wants the closest window of step_text lacks; empty when one window holds them all.

    A window is up to `span` sentences or bullets in a row. All wants must sit in one window,
    so words spread over the step (a "never" far from any list) cannot satisfy it.
    """
    # A bullet marker after a sentence end splits twice, which leaves an empty unit: drop it,
    # or it would sit between two neighbours and break their window.
    units = [squash(u) for u in re.split(r"(?<=[.!?])\s+|^\s*[-*]\s+", step_text, flags=re.M)]
    units = [u for u in units if u]
    windows = [" ".join(units[i:i + k]) for k in range(1, span + 1) for i in range(len(units) - k + 1)]
    best = [label for label, _ in wants]
    for window in windows:
        miss = [label for label, rx in wants if not re.search(rx, window)]
        if len(miss) < len(best):
            best = miss
    return best


def case_prompt_step5_names_checked_stamp():
    """Step 5 names the rule that refuses a restamp of a premise without evidence (decision precompact-handoff,
    item 10; roadmap step handoff-checked-stamp), so a session reading step 5 knows the write will be checked."""
    step5 = step_body(prompt_source(), 5) or ""
    check("prompt step 5: names the handoff-checked-stamp rule",
          "handoff-checked-stamp" in step5, "step 5 holds %d characters and no rule name" % len(step5))


def list_home_missing(step_text):
    return window_missing(step_text, LIST_HOME_WANTS)


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


# --------------------------------------------------------------------------- summary fraction
# summary_fraction(limit) reads Claude Code's cached flags from <config dir>/.claude.json, or from
# ~/.claude.json when CLAUDE_CONFIG_DIR is unset (key cachedGrowthBookFeatures). Order: the
# tengu_amber_moleskin table (the entry for str(limit), else "default"; "sdk" when the entrypoint
# starts with "sdk", else "repl"; any out-of-range or non-dict entry makes the table malformed),
# then the scalar tengu_amber_rokovoko, then 0.2. Case.set_flags writes the file.


def fraction_flags(f):
    """A flag table that gives every window and entrypoint the same fraction f."""
    return {"tengu_amber_moleskin": {"default": {"repl": f, "sdk": f}}}


class Env(object):
    """Set os.environ names for one block, then put each back. None unsets a name."""

    def __init__(self, **values):
        self.values = values
        self.saved = {}

    def __enter__(self):
        for name, value in self.values.items():
            self.saved[name] = os.environ.get(name)
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = str(value)
        return self

    def __exit__(self, *exc):
        for name, old in self.saved.items():
            if old is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = old
        return False


def call_under_test(name, *args, **kwargs):
    """(value, None), or (None, "Type: message") when the module's function raises or is missing.
    A missing name fails its checks and never stops the rest of the run."""
    try:
        return getattr(under_test(), name)(*args, **kwargs), None
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, e)


def expect_value(name, got, err, want):
    check(name, err is None and got == want, err or "got %r, want %r" % (got, want))


def fraction_at(c, limit, entrypoint=None):
    """summary_fraction(limit) with the case's config dir, as (value, error)."""
    with Env(CLAUDE_CONFIG_DIR=c.cfg, CLAUDE_CODE_ENTRYPOINT=entrypoint):
        return call_under_test("summary_fraction", limit)


def case_summary_fraction_table():
    c = Case("sftab")
    try:
        c.set_flags(fraction_flags(0.15))
        got, err = fraction_at(c, 500000)
        expect_value("summary: table default 0.15 applies to 500k", got, err, 0.15)
        got, err = fraction_at(c, 200000)
        expect_value("summary: table default 0.15 applies to 200k", got, err, 0.15)
    finally:
        c.cleanup()


def case_summary_fraction_exact_key_beats_default():
    c = Case("sfkey")
    try:
        c.set_flags({"tengu_amber_moleskin": {
            "500000": {"repl": 0.08, "sdk": 0.08}, "default": {"repl": 0.15, "sdk": 0.15}}})
        got, err = fraction_at(c, 500000)
        expect_value("summary: exact key \"500000\" (0.08) beats default (0.15)", got, err, 0.08)
        got, err = fraction_at(c, 200000)
        expect_value("summary: 200k has no key, so default 0.15 applies", got, err, 0.15)
    finally:
        c.cleanup()


def case_summary_fraction_sdk_or_repl():
    c = Case("sfsdk")
    try:
        c.set_flags({"tengu_amber_moleskin": {"default": {"repl": 0.15, "sdk": 0.05}}})
        for tag, entry, want in (("unset", None, 0.15), ("cli", "cli", 0.15),
                                 ("remote", "remote", 0.15), ("sdk-ts", "sdk-ts", 0.05)):
            got, err = fraction_at(c, 500000, entrypoint=entry)
            expect_value("summary: entrypoint %s picks %s" % (tag, want), got, err, want)
    finally:
        c.cleanup()


def case_summary_fraction_falls_to_scalar():
    """A malformed table, or one with no entry for this window, falls to the scalar 0.1."""
    c = Case("sfbad")
    try:
        rows = (
            ("the table has an out-of-range fraction (1.2)",
             {"tengu_amber_moleskin": {"default": {"repl": 1.2, "sdk": 0.15}},
              "tengu_amber_rokovoko": 0.1}),
            ("the table has a non-dict entry",
             {"tengu_amber_moleskin": {"500000": 0.08,
                                       "default": {"repl": 0.15, "sdk": 0.15}},
              "tengu_amber_rokovoko": 0.1}),
            ("an entry under another window is out of range (the whole table is malformed)",
             {"tengu_amber_moleskin": {"200000": {"repl": -0.1, "sdk": 0.1},
                                       "default": {"repl": 0.15, "sdk": 0.15}},
              "tengu_amber_rokovoko": 0.1}),
            ("the table has no entry for 500k and no default",
             {"tengu_amber_moleskin": {"200000": {"repl": 0.08, "sdk": 0.08}},
              "tengu_amber_rokovoko": 0.1}),
        )
        for tag, features in rows:
            c.set_flags(features)
            got, err = fraction_at(c, 500000)
            expect_value("summary: %s, so the scalar 0.1 applies" % tag, got, err, 0.1)
    finally:
        c.cleanup()


def case_summary_fraction_defaults():
    """The scalar must be in 0 <= f < 1; anything else, a missing file or a bad file gives 0.2."""
    c = Case("sfdef")
    try:
        rows = (
            ("scalar 0.0 is in range", {"tengu_amber_rokovoko": 0.0}, 0.0),
            ("scalar 1.5 is out of range", {"tengu_amber_rokovoko": 1.5}, 0.2),
            ("scalar 1.0 is out of range", {"tengu_amber_rokovoko": 1.0}, 0.2),
            ("no flag named", {"other_flag": 1}, 0.2),
        )
        for tag, features, want in rows:
            c.set_flags(features)
            got, err = fraction_at(c, 500000)
            expect_value("summary: %s" % tag, got, err, want)
        put(os.path.join(c.cfg, ".claude.json"), "{not json")
        got, err = fraction_at(c, 500000)
        expect_value("summary: an unreadable file gives 0.2", got, err, 0.2)
        os.remove(os.path.join(c.cfg, ".claude.json"))
        got, err = fraction_at(c, 500000)
        expect_value("summary: a missing file gives 0.2", got, err, 0.2)
    finally:
        c.cleanup()


def case_summary_fraction_reads_config_dir_file():
    c = Case("sfloc")
    try:
        home = os.path.join(c.root, "home")
        put(os.path.join(home, ".claude.json"),
            json.dumps({"cachedGrowthBookFeatures": {"tengu_amber_rokovoko": 0.07}}))
        c.set_flags({"tengu_amber_rokovoko": 0.09})
        with Env(CLAUDE_CONFIG_DIR=c.cfg, HOME=home, USERPROFILE=home):
            got, err = call_under_test("summary_fraction", 500000)
        expect_value("summary: CLAUDE_CONFIG_DIR's .claude.json is read, not the home one",
                     got, err, 0.09)
        with Env(CLAUDE_CONFIG_DIR=None, HOME=home, USERPROFILE=home):
            got, err = call_under_test("summary_fraction", 500000)
        expect_value("summary: with no CLAUDE_CONFIG_DIR, ~/.claude.json is read",
                     got, err, 0.07)
    finally:
        c.cleanup()


# --------------------------------------------------------------------------- compact threshold
# compact_threshold(500k) with the flag fraction: 0.2 gives 384,000, 0.08 gives 441,600.
# F1: CLAUDE_AUTOCOMPACT_PCT_OVERRIDE = p applies to every window, remote or not, so the second
# term is min(floor(E * p / 100), E - 13k), where E = limit - 20k, for 0 < p <= 100.


def threshold_at(c, limit, remote=None, pct=None):
    """compact_threshold(limit) with the case's config dir and remote knobs, as (value, error)."""
    with Env(CLAUDE_CONFIG_DIR=c.cfg, CLAUDE_CODE_ENTRYPOINT=None,
             CLAUDE_CODE_REMOTE=remote, CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=pct):
        return call_under_test("compact_threshold", limit)


def case_compact_threshold_reads_flag_and_remote():
    c = Case("cthf")
    try:
        for f, want in ((0.2, 384000), (0.08, 441600), (0.15, 408000), (0.0, 467000)):
            c.set_flags(fraction_flags(f))
            got, err = threshold_at(c, 500000)
            expect_value("threshold: 500k with fraction %s is %d" % (f, want), got, err, want)

        c.set_flags(fraction_flags(0.2))
        got, err = threshold_at(c, 200000, remote="1", pct="80")
        expect_value("threshold: 200k remote pct 80, fraction 0.2 is 144,000", got, err, 144000)
        # F1: the percent override has no remote gate and no 200k gate, so PCT 80 applies at 500k.
        c.set_flags(fraction_flags(0.08))
        got, err = threshold_at(c, 500000, pct="80")
        expect_value("threshold: 500k PCT 80, fraction 0.08 is 384,000 (no remote gate)",
                     got, err, 384000)

        c.set_flags(fraction_flags(0.01))
        got, err = threshold_at(c, 200000)
        expect_value("threshold: 200k no remote pct 80, fraction 0.01 is 167,000", got, err, 167000)
        # F1: PCT 80 without CLAUDE_CODE_REMOTE is applied, so 200k is 144,000, not 167,000.
        got, err = threshold_at(c, 200000, pct="80")
        expect_value("threshold: 200k pct 80 without CLAUDE_CODE_REMOTE is applied",
                     got, err, 144000)
        got, err = threshold_at(c, 200000, remote="1", pct="80")
        expect_value("threshold: 200k remote pct 80, fraction 0.01 is 144,000 (override lower)",
                     got, err, 144000)
        for pct in ("0", "-5", "abc"):
            got, err = threshold_at(c, 200000, remote="1", pct=pct)
            expect_value("threshold: 200k remote, pct %s is not 0 < p <= 100, so ignored" % pct,
                         got, err, 167000)
    finally:
        c.cleanup()


def case_compact_threshold_pct_override_every_window():
    """F1: the percent override applies in every session and window, with no remote gate. An
    unset, unparsable or out-of-range value (0, 150, abc) is ignored."""
    c = Case("cthpct")
    try:
        c.set_flags(fraction_flags(0.2))
        got, err = threshold_at(c, 500000, pct="50")
        expect_value("threshold: PCT 50, no remote, 500k, fraction 0.2 is 240,000",
                     got, err, 240000)
        c.set_flags(fraction_flags(0.08))
        got, err = threshold_at(c, 500000)
        expect_value("threshold: PCT unset, 500k, fraction 0.08 is 441,600", got, err, 441600)
        for pct in ("abc", "0", "150"):
            got, err = threshold_at(c, 500000, pct=pct)
            expect_value("threshold: 500k, PCT %s is not 0 < p <= 100, so ignored" % pct,
                         got, err, 441600)
        # P (round-2 finding): the value parses like JS parseFloat, so the leading 80 counts.
        got, err = threshold_at(c, 500000, pct="80%")
        expect_value("threshold: 500k, PCT '80%' parses as 80, so 384,000", got, err, 384000)
    finally:
        c.cleanup()


# --------------------------------------------------------------------------- nudge with the flag
# The nudge reads the same threshold. Flag fraction 0.08 on 500k, overhead 30k: threshold
# 441,600, room 411,600, top at messages 361,600 = total 391,600.


def case_nudge_reads_summary_flag():
    c = Case("nflag")
    try:
        c.set_flags(fraction_flags(0.08))
        first = usage_line(30000)
        p = nudge(c, 0, overhead=None, lines=[first, usage_line(230000)])
        check("flag nudge: total 230k (200k messages) blocks at the first checkpoint",
              is_block(c, p) and stored_bucket(c) == 0,
              "out=%r bucket=%r" % (p.stdout, stored_bucket(c)))
        p = nudge(c, 0, overhead=None, lines=[first, usage_line(340000)])
        check("flag nudge: total 340k is silent (the 0.2 top of 334k no longer applies)",
              p.returncode == 0 and not p.stdout.strip() and stored_bucket(c) == 0,
              "out=%r bucket=%r" % (p.stdout, stored_bucket(c)))
        p = nudge(c, 0, overhead=None, lines=[first, usage_line(391599)])
        check("flag nudge: total 391,599 is silent (one under the top, 391,600)",
              p.returncode == 0 and not p.stdout.strip() and stored_bucket(c) == 0,
              "out=%r bucket=%r" % (p.stdout, stored_bucket(c)))
        p = nudge(c, 0, overhead=None, lines=[first, usage_line(392000)])
        check("flag nudge: total 392,000 blocks at the top bucket",
              is_block(c, p) and stored_bucket(c) == 1,
              "out=%r bucket=%r" % (p.stdout, stored_bucket(c)))
        p = nudge(c, 0, overhead=None, lines=[first, usage_line(455000)])
        check("flag nudge: 455k after the top is silent", p.returncode == 0
              and not p.stdout.strip() and stored_bucket(c) == 1,
              "out=%r bucket=%r" % (p.stdout, stored_bucket(c)))
    finally:
        c.cleanup()


# --------------------------------------------------------------------------- digest since handoff
# PreCompact's digest runs from the last handoff rewrite (the handoff file's mtime, in epoch
# seconds) when that file exists, capped at DIGEST_SINCE_CAP characters. A "## Refused acts"
# section then lists the refused tool results after that point. Without a handoff, the digest is
# the last DIGEST_CAP (60,000) characters, as before.

SINCE_ISO = "2026-10-03T10:00:00Z"  # the handoff's mtime in these cases
BEFORE_ISO = "2026-10-03T09:00:00Z"
AFTER_ISO = "2026-10-03T11:00:00Z"


def epoch(iso):
    """Epoch seconds of a UTC time written like 2026-10-03T10:00:00Z."""
    when = datetime.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")
    return when.replace(tzinfo=datetime.timezone.utc).timestamp()


def text_entry(text, ts):
    return transcript_line("user", [{"type": "text", "text": text}], timestamp=ts)


def tool_result(content, ts, is_error=True, tool_use_id="tu-1"):
    """A user entry holding one tool_result. is_error None leaves the key out."""
    block = {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}
    if is_error is not None:
        block["is_error"] = is_error
    return transcript_line("user", [block], timestamp=ts)


def filler(marker, n):
    """A string of exactly n characters that starts with marker."""
    return (marker + " " + "x" * n)[:n]


def digest_at(c, lines, since=None):
    """build_digest over these transcript lines, as (digest, error)."""
    tp = os.path.join(c.root, "digest-transcript.jsonl")
    write_transcript(tp, lines)
    if since is None:
        return call_under_test("build_digest", tp)
    return call_under_test("build_digest", tp, since=since)


def refused_lines(digest):
    """The lines under "## Refused acts", blank lines dropped. [] when there is no such section."""
    if digest is None or "## Refused acts" not in digest:
        return []
    return [ln for ln in digest.split("## Refused acts", 1)[1].splitlines() if ln.strip()]


def case_digest_since_keeps_text_after_handoff():
    c = Case("dgsince")
    try:
        since = epoch(SINCE_ISO)
        lines = [text_entry("BEFOREMARK earlier work", BEFORE_ISO),
                 text_entry("AFTERMARK later work", AFTER_ISO)]
        d, err = digest_at(c, lines, since)
        check("digest since: text before the handoff is dropped",
              d is not None and "BEFOREMARK" not in d, err or "digest: %r" % (d,))
        check("digest since: text after the handoff is kept",
              d is not None and "AFTERMARK" in d, err or "digest: %r" % (d,))

        # 90,000 characters after the handoff: past the 60,000 cap, so all of it stays.
        lines = [text_entry(filler("FIRSTNEW", 30000), AFTER_ISO),
                 text_entry(filler("MIDNEW", 30000), AFTER_ISO),
                 text_entry(filler("LASTNEW", 30000), AFTER_ISO)]
        d, err = digest_at(c, lines, since)
        check("digest since: 90k after the handoff is kept whole, past the 60k cap",
              d is not None and all(m in d for m in ("FIRSTNEW", "MIDNEW", "LASTNEW"))
              and len(d) >= 90000, err or "len=%r" % (len(d) if d is not None else None))
        d, err = digest_at(c, lines)
        check("digest without a handoff: only the last 60,000 characters",
              d is not None and len(d) <= 60000 and "FIRSTNEW" not in d and "LASTNEW" in d,
              err or "len=%r" % (len(d) if d is not None else None))

        # 250,000 characters after the handoff: the 200,000 cap keeps the newest.
        lines = [text_entry(filler("OLDEST200", 50000), AFTER_ISO)]
        lines += [text_entry(filler("MID%d" % i, 50000), AFTER_ISO) for i in range(3)]
        lines += [text_entry(filler("NEWEST200", 50000), AFTER_ISO)]
        d, err = digest_at(c, lines, since)
        check("digest since: capped at 200,000 characters, the newest kept",
              d is not None and len(d) <= 200000 and "NEWEST200" in d and "OLDEST200" not in d,
              err or "len=%r" % (len(d) if d is not None else None))
        try:
            cap = under_test().DIGEST_SINCE_CAP
        except Exception as e:
            cap = "%s: %s" % (type(e).__name__, e)
        check("digest since: DIGEST_SINCE_CAP is 200000", cap == 200000, "got %r" % (cap,))

        # Millisecond timestamps, as Claude Code writes them, compare as times.
        lines = [text_entry("EARLYMILLI before the handoff", "2026-10-03T09:59:59.900Z"),
                 text_entry("LATEMILLI after the handoff", "2026-10-03T10:00:00.500Z")]
        d, err = digest_at(c, lines, since)
        check("digest since: millisecond timestamps compare as times",
              d is not None and "LATEMILLI" in d and "EARLYMILLI" not in d,
              err or "digest: %r" % (d,))
    finally:
        c.cleanup()


def case_digest_lists_refused_acts_after_handoff():
    c = Case("dgref")
    try:
        since = epoch(SINCE_ISO)
        lines = [tool_result("PreToolUse:Bash hook error: [guard] denied: REFUSEDMARK1 blocked "
                             "by the merge guard", AFTER_ISO),
                 tool_result([{"type": "text", "text": "Refused: REFUSEDMARK2 push to main"}],
                             AFTER_ISO),
                 tool_result("REFUSEDSTALE, before the handoff: denied", BEFORE_ISO)]
        d, err = digest_at(c, lines, since)
        listed = refused_lines(d)
        check("refused: a PreToolUse hook error after the handoff is listed",
              any("REFUSEDMARK1" in ln for ln in listed), err or "section: %r" % (listed,))
        check("refused: a list-form tool_result with 'Refused' is listed",
              any("REFUSEDMARK2" in ln for ln in listed), err or "section: %r" % (listed,))
        check("refused: a refusal before the handoff is not listed",
              d is not None and "REFUSEDSTALE" not in d, err or "digest: %r" % (d,))
        check("refused: the newest refusal is listed last",
              bool(listed) and "REFUSEDMARK2" in listed[-1], "section: %r" % (listed,))

        d, err = digest_at(c, lines[:1])
        check("refused: with no handoff, a refusal in the transcript is still listed",
              any("REFUSEDMARK1" in ln for ln in refused_lines(d)), err or "digest: %r" % (d,))
    finally:
        c.cleanup()


def case_digest_plain_errors_are_not_refusals():
    c = Case("dgplain")
    try:
        since = epoch(SINCE_ISO)
        lines = [tool_result("Exit code 1\nPLAINERRMARK tests failed", AFTER_ISO),
                 tool_result("permission denied: PLAINDENIEDMARK", AFTER_ISO, is_error=None),
                 text_entry("some text after the handoff", AFTER_ISO)]
        d, err = digest_at(c, lines, since)
        check("refused: a plain is_error 'Exit code 1' is not listed, and no section is written",
              d is not None and "## Refused acts" not in d, err or "digest: %r" % (d,))
    finally:
        c.cleanup()


# F5, R: only the listed refusal shapes make a failed tool result a refusal; the rest are not.
# R (round-2 finding): the four rows after the first three are refusal shapes too.
REFUSAL_ROWS = (
    ("PreToolUse:Bash hook error: [guard] blocked", True),
    ("The user doesn't want to proceed with this tool use. The tool use was rejected", True),
    ("Permission to use Bash has been denied", True),
    ("Permission to use Read with .env has been denied.", True),
    ("Permission for this action has been denied. Reason: x", True),
    ("The tool call was denied by the Claude Code auto mode classifier.", True),
    ("This agent is isolated in the worktree X, but the command runs elsewhere. "
     "Refusing to run it", True),
    ("Permission to read .env has been denied.", True),
    ("Permission to edit ~/.claude/settings.json has been denied.", True),
    ("Permission for this tool use was denied: it requires interactive approval", True),
    ("Permission for this command was denied by a built-in Claude Code safety check", True),
    ("Permission to read /home/user/My Docs/x.txt has been denied.", True),
    ("Error: connect ECONNREFUSED 127.0.0.1", False),
    ("bash: /x: Permission denied", False),
    ("Nobody refused it", False),
    ("Exit code 1", False),
)


def case_digest_refusal_shapes():
    """F5: each row's text, alone in its own transcript, is the one listed line when the row says
    so, and no refused-acts section at all when it does not."""
    c = Case("dgshape")
    try:
        since = epoch(SINCE_ISO)
        for text, want in REFUSAL_ROWS:
            d, err = digest_at(c, [tool_result(text, AFTER_ISO)], since)
            listed = refused_lines(d)
            ok = listed == [text] if want else "## Refused acts" not in (d or "")
            check("refused shape: %r is %s" % (text, "listed" if want else "not listed"),
                  ok, err or "section: %r" % (listed,))
    finally:
        c.cleanup()


def case_digest_refused_line_limits():
    c = Case("dgline")
    try:
        since = epoch(SINCE_ISO)
        long_first = "denied: REFUSEDLONG " + "y" * 300
        d, err = digest_at(c, [tool_result(long_first + "\nSECONDLINEMARK", AFTER_ISO)], since)
        longs = [ln for ln in refused_lines(d) if "REFUSEDLONG" in ln]
        check("refused: only the first line of a refusal is listed",
              d is not None and "SECONDLINEMARK" not in d and len(longs) == 1,
              err or "section: %r" % (refused_lines(d),))
        check("refused: the listed line is at most 200 characters",
              len(longs) == 1 and len(longs[0]) <= 200,
              "lengths: %r" % ([len(ln) for ln in longs],))

        many = [tool_result("denied: REFUSEDNUM%02d" % i, AFTER_ISO) for i in range(60)]
        d, err = digest_at(c, many, since)
        listed = refused_lines(d)
        check("refused: at most 50 lines are listed", 0 < len(listed) <= 50,
              err or "listed %d" % len(listed))
        check("refused: the newest refusal is kept, last", bool(listed)
              and "REFUSEDNUM59" in listed[-1], err or "last: %r" % (listed[-1:],))
    finally:
        c.cleanup()


def case_precompact_digest_starts_at_handoff():
    """PreCompact passes the handoff's mtime as `since`: text before it drops, after it stays."""
    c = Case("pcsince")
    try:
        put(c.handoff_path(), "# handoff\n")
        mtime = epoch(SINCE_ISO)
        os.utime(c.handoff_path(), (mtime, mtime))
        tpath = os.path.join(c.root, "transcript.jsonl")
        write_transcript(tpath, [
            text_entry("OLDPCMARK earlier work", BEFORE_ISO),
            text_entry("NEWPCMARK later work", AFTER_ISO),
            tool_result("PreToolUse:Bash hook error: [guard] denied: PCREFUSEDMARK force push",
                        AFTER_ISO),
        ])
        proc = c.run_precompact(tpath)
        digest = c.read_digest()
        check("pre-handoff: PreCompact exits 0", proc.returncode == 0,
              "returncode=%r stderr=%r" % (proc.returncode, proc.stderr[-300:]))
        check("pre-handoff: the digest keeps text after the handoff mtime",
              digest is not None and "NEWPCMARK" in digest, "digest: %r" % (digest,))
        check("pre-handoff: the digest drops text before the handoff mtime",
              digest is not None and "OLDPCMARK" not in digest, "digest: %r" % (digest,))
        check("pre-handoff: the digest lists the refused act",
              any("PCREFUSEDMARK" in ln for ln in refused_lines(digest)),
              "section: %r" % (refused_lines(digest),))
    finally:
        c.cleanup()


def case_precompact_digest_without_handoff():
    c = Case("pcnone")
    try:
        tpath = os.path.join(c.root, "transcript.jsonl")
        write_transcript(tpath, [text_entry("OLDPCMARK earlier work", BEFORE_ISO),
                                 text_entry("NEWPCMARK later work", AFTER_ISO)])
        proc = c.run_precompact(tpath)
        digest = c.read_digest()
        check("no handoff: PreCompact exits 0", proc.returncode == 0,
              "returncode=%r" % proc.returncode)
        check("no handoff: the digest keeps the earlier text too",
              digest is not None and "OLDPCMARK" in digest and "NEWPCMARK" in digest,
              "digest: %r" % (digest,))
    finally:
        c.cleanup()


# --------------------------------------------------------------------------- handoff sections
# A handoff holds six sections. Step 4 of the prompt names them once, in a marker line, and the code
# reads that marker at run time; no code copies the list. The Stop cases below build handoffs from
# these bodies, so a case states only what it removes.
SECTION_NAMES = ("Goal", "Working premises", "Where things stand", "Work in flight", "Next steps",
                 "Files and commands")
SECTION_BODIES = {
    "Goal": "Ship the handoff section check (owner message, 2026-11-08).\n",
    "Working premises": "- P1 [ruling] Six sections are required. Source: owner, 2026-11-08. Checked 2026-11-08.\n",
    "Where things stand": "Branch hsk-tests at 2ac382cc6. No pull request.\n",
    "Work in flight": "Nothing in flight.\n",
    "Next steps": "The builder adds the check.\n",
    "Files and commands": "hooks/guard.py and hooks/precompact_handoff.py.\n",
}
MARKER_LINE = re.compile(r"<!--\s*handoff-sections:\s*(.*?)\s*-->")
MTIME_1 = 1800000000   # fixed handoff mtimes: a case sets them, and never waits for the clock
MTIME_2 = MTIME_1 + 3600


def handoff_text(omit=()):
    """A handoff holding every section but those in `omit`, each under its own `## ` heading."""
    parts = ["# Handoff\n\n"]
    for name in SECTION_NAMES:
        if name not in omit:
            parts.append("## %s\n%s\n" % (name, SECTION_BODIES[name]))
    return "".join(parts)


def names_in(text):
    """The section names a text holds, in any case, as whole phrases."""
    return {n for n in SECTION_NAMES if re.search(r"\b%s\b" % re.escape(n), text or "", re.I)}


def prompt_source():
    with open(os.path.join(HERE, "precompact_handoff_prompt.md"), "r", encoding="utf-8") as f:
        return f.read()


def install_prompt(c, text):
    """The installed prompt, which the code reads: the config folder's copy, not the repo's."""
    put(c.prompt_path(), text)


def block_reason(proc):
    """The reason of the block a Stop run printed; None when it printed no block."""
    try:
        obj = json.loads(proc.stdout or "")
    except ValueError:
        return None
    if not isinstance(obj, dict) or obj.get("decision") != "block":
        return None
    return obj.get("reason", "")


def nudge_at(c, text, mtime, active=False):
    """Write the handoff as `text` leaves it, set its mtime, then run one Stop. The messages sit below
    the first checkpoint, so only the section check can block."""
    put(c.handoff_path(), text)
    os.utime(c.handoff_path(), (mtime, mtime))
    return nudge(c, NUDGE_OVERHEAD, active=active, lines=[])


def case_prompt_marker_names_the_sections():
    text = prompt_source()
    found = MARKER_LINE.findall(text)
    step4 = step_body(text, 4) or ""
    check("sections marker: the prompt holds one handoff-sections marker, in step 4",
          len(found) == 1 and MARKER_LINE.search(step4) is not None,
          "markers: %d, in step 4: %s" % (len(found), MARKER_LINE.search(step4) is not None))
    names = [n.strip() for n in found[0].split("|")] if found else []
    check("sections marker: it names the six sections, each once",
          sorted(names) == sorted(SECTION_NAMES), "names: %r" % names)


def case_step4_bullets_lead_with_the_marker_names():
    """Each section name on the marker leads a bullet of step 4, so the list the prompt shows reads as the list the
    guard enforces. The lead is the name itself, followed by a mark or a space, at the start of a bullet. A bullet's
    wrapped lines are indented, so they are no bullet of their own."""
    text = prompt_source()
    step4 = step_body(text, 4) or ""
    found = MARKER_LINE.findall(text)
    names = [n.strip() for n in found[0].split("|") if n.strip()] if found else []
    bullets = [b.strip() for b in re.findall(r"^- (.*)$", step4, re.M)]
    check("step 4 leads: scope: step 4 holds the marker, and at least one bullet per marker name",
          bool(names) and MARKER_LINE.search(step4) is not None and len(bullets) >= len(names),
          "names: %r, bullets: %d" % (names, len(bullets)))
    for name in names:
        lead = re.compile(r"^%s(?!\w)" % re.escape(name), re.I)
        check("step 4 leads: a bullet of step 4 leads with %r" % name,
              any(lead.match(b) for b in bullets),
              "no bullet leads with it; the bullets begin: %r" % [b[:32] for b in bullets])


def case_code_holds_no_section_names():
    """The six names live in the prompt's marker and nowhere in the code, so no copy can go stale. Python's
    own tokenizer reads the module: a name in a comment is no copy, and a name in a string or a docstring is.
    The scan must reach the module's last token before it may assert on what it found."""
    import io
    import tokenize
    with open(MODULE, "r", encoding="utf-8") as f:
        source = f.read()
    patterns = [(n, re.compile(r"\b%s\b" % r"\s+".join(re.escape(w) for w in n.split()), re.I))
                for n in SECTION_NAMES]
    hits = []
    reached_end = False
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.ENDMARKER:
            reached_end = True
        if tok.type == tokenize.COMMENT:
            continue
        for name, rx in patterns:
            if rx.search(tok.string):
                hits.append("%s at line %d" % (name, tok.start[0]))
    check("sections in code: the scan reached the end of the module", reached_end,
          "the tokenizer stopped early")
    check("sections in code: no section name in the module outside comments",
          not hits, "hits: %s" % "; ".join(hits))


def case_nudge_flags_a_damaged_handoff_once_per_mtime():
    c = Case("nudge_sections")
    try:
        install_prompt(c, prompt_source())
        omitted = ("Work in flight", "Next steps", "Files and commands")
        damaged = handoff_text(omit=omitted)
        first = nudge_at(c, damaged, MTIME_1)
        with open(c.handoff_path(), "r", encoding="utf-8") as f:
            on_disk = f.read()
        check("sections nudge: scope: the handoff on disk is the damaged one", on_disk == damaged,
              "on disk: %r" % on_disk[:120])
        reason = block_reason(first)
        check("sections nudge: a Stop after a damaging write blocks",
              reason is not None, "stdout: %r" % first.stdout[:200])
        check("sections nudge: the block names the three missing sections and no other",
              names_in(reason) == set(omitted), "named: %r" % sorted(names_in(reason)))

        again = nudge_at(c, damaged, MTIME_1)
        check("sections nudge: the same handoff mtime is silent on the next Stop",
              not (again.stdout or "").strip(), "stdout: %r" % again.stdout[:200])

        newer = handoff_text(omit=("Next steps",))
        third = nudge_at(c, newer, MTIME_2)
        reason3 = block_reason(third)
        check("sections nudge: a new damaging mtime blocks again",
              reason3 is not None, "stdout: %r" % third.stdout[:200])
        check("sections nudge: the second block names Next steps only",
              names_in(reason3) == {"Next steps"}, "named: %r" % sorted(names_in(reason3)))
    finally:
        c.cleanup()


def case_nudge_sections_quiet_when_complete_absent_or_active():
    damaged = handoff_text(omit=("Next steps",))
    variants = (
        ("a damaged handoff, not active: the control", damaged, False, True),
        ("a complete handoff", handoff_text(), False, False),
        ("no handoff file at all", None, False, False),
        ("a damaged handoff with stop_hook_active", damaged, True, False),
    )
    for label, text, active, want_block in variants:
        c = Case("nudge_quiet")
        try:
            install_prompt(c, prompt_source())
            if text is None:
                check("sections nudge (%s): scope: no handoff file" % label,
                      not os.path.exists(c.handoff_path()), "a file exists")
                proc = nudge(c, NUDGE_OVERHEAD, active=active, lines=[])
            else:
                proc = nudge_at(c, text, MTIME_1, active=active)
            blocked = block_reason(proc) is not None
            check("sections nudge (%s): %s" % (label, "blocks" if want_block else "is silent"),
                  blocked == want_block, "stdout: %r" % proc.stdout[:200])
        finally:
            c.cleanup()


def numbered_text(omit=()):
    """A handoff whose headings carry the prompt's step numbers: `## 1. Goal`, and `# 5. Next steps` at H1."""
    parts = ["# Handoff\n\n"]
    for number, name in enumerate(SECTION_NAMES, 1):
        if name not in omit:
            level = "#" if name == "Next steps" else "##"
            parts.append("%s %d. %s\n%s\n" % (level, number, name, SECTION_BODIES[name]))
    return "".join(parts)


def case_nudge_sections_count_numbered_headings():
    """A heading numbered like the prompt's steps holds its section. A `N)` heading does not: the prompt numbers its
    steps with `N.` only, and the premises reader reads unnumbered headings, so the readers would part on it."""
    variants = (
        ("every heading numbered N., one at H1", numbered_text(), set()),
        ("the N. headings, with Next steps gone", numbered_text(omit=("Next steps",)), {"Next steps"}),
        ("a 3) heading for Where things stand, the rest unnumbered",
         handoff_text().replace("## Where things stand\n", "## 3) Where things stand\n"), {"Where things stand"}),
    )
    for label, text, want in variants:
        c = Case("nudge_numbered")
        try:
            install_prompt(c, prompt_source())
            proc = nudge_at(c, text, MTIME_1)
            reason = block_reason(proc)
            named = names_in(reason) if reason is not None else set()
            check("sections nudge (%s): %s" % (label, "blocks, naming %s" % ", ".join(sorted(want)) if want
                                                else "is silent"),
                  named == want and (reason is not None) == bool(want),
                  "stdout: %r, named: %r" % (proc.stdout[:200], sorted(named)))
        finally:
            c.cleanup()


def case_one_reader_for_the_premises_section():
    """Both readers of the prompt's marker agree on the premises section. With no installed prompt file,
    required_sections() falls back to the prompt beside the module, and premises_section() names the premises entry of
    that same list. The control installs the prompt: there the two agree, and the premises name is one of the required
    names."""
    repo_copy = os.path.join(os.path.dirname(os.path.abspath(MODULE)), "precompact_handoff_prompt.md")
    c = Case("reader")
    try:
        check("one reader: scope: the repo's prompt copy beside the module is there", os.path.isfile(repo_copy),
              "no file at %s" % repo_copy)
        check("one reader: scope: the config folder holds no installed prompt", not os.path.exists(c.prompt_path()),
              "a prompt exists at %s" % c.prompt_path())
        with Env(CLAUDE_CONFIG_DIR=c.cfg):
            req, err = call_under_test("required_sections")
            prem, perr = call_under_test("premises_section")
        expected = next((n for n in (req or []) if "premises" in n.lower()), None)
        check("one reader: with no installed prompt, premises_section() names what required_sections() lists",
              err is None and perr is None and prem == expected,
              "required_sections() = %r, premises_section() = %r" % (req, prem))

        install_prompt(c, prompt_source())
        with Env(CLAUDE_CONFIG_DIR=c.cfg):
            req2, err2 = call_under_test("required_sections")
            prem2, perr2 = call_under_test("premises_section")
        expected2 = next((n for n in (req2 or []) if "premises" in n.lower()), None)
        check("one reader: control: with the installed prompt, the premises name is listed and matches",
              err2 is None and perr2 is None and expected2 is not None and prem2 == expected2,
              "required_sections() = %r, premises_section() = %r" % (req2, prem2))
    finally:
        c.cleanup()


def put_bytes(path, data):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def case_nudge_sections_fail_open_on_bad_prompt():
    damaged = handoff_text(omit=("Next steps",))
    text = prompt_source()
    c = Case("nudge_control")
    try:
        install_prompt(c, text)
        control = nudge_at(c, damaged, MTIME_1)
        check("sections fail open: control: the intact prompt blocks the damaged handoff",
              block_reason(control) is not None, "stdout: %r" % control.stdout[:200])
    finally:
        c.cleanup()

    def dir_prompt(c):
        os.makedirs(c.prompt_path(), exist_ok=True)

    def bytes_prompt(c):
        put_bytes(c.prompt_path(), b"\xff\xfe" + text.encode("utf-8"))

    bad = (
        ("the prompt has no marker line", lambda c: install_prompt(c, MARKER_LINE.sub("", text))),
        ("the prompt path is a directory", dir_prompt),
        ("the prompt is not UTF-8", bytes_prompt),
    )
    for label, install in bad:
        c = Case("nudge_bad")
        try:
            install(c)
            proc = nudge_at(c, damaged, MTIME_1)
            check("sections fail open (%s): exit 0" % label, proc.returncode == 0,
                  "rc=%r stderr=%r" % (proc.returncode, proc.stderr[-200:]))
            check("sections fail open (%s): no block" % label, block_reason(proc) is None,
                  "stdout: %r" % proc.stdout[:200])
        finally:
            c.cleanup()


def case_nudge_sections_flags_an_empty_handoff():
    c = Case("nudge_empty")
    try:
        install_prompt(c, prompt_source())
        proc = nudge_at(c, "", MTIME_1)
        reason = block_reason(proc)
        check("sections nudge (empty): an empty handoff blocks", reason is not None,
              "stdout: %r" % proc.stdout[:200])
        check("sections nudge (empty): the block names all six sections",
              names_in(reason) == set(SECTION_NAMES), "named: %r" % sorted(names_in(reason)))
    finally:
        c.cleanup()


# --------------------------------------------------------------------------- the run


def case_prompt_names_audit_agent():
    with open(os.path.join(HERE, "precompact_handoff_prompt.md"), "r", encoding="utf-8") as f:
        prompt = " ".join(f.read().split())
    for name, needle in (
            ("the compaction trigger, not a Stop checkpoint",
             "After a compaction, also send one Explore agent"),
            ("one Explore agent on Sonnet", "one Explore agent on Sonnet"),
            ("no earlier marker reads from the start", "with no earlier marker, from the start"),
            ("the transcript's path", "<session_id>.jsonl"),
            ("a marker is a compact_boundary record, never quoted text",
             "A marker is a `compact_boundary` system record"),
            ("the Audit: marker on the brief's first line", "first line is `Audit:`"),
            ("reads from the previous continuation marker", "This session is being continued"),
            ("the missing list", "MISSING"), ("the stale list", "STALE"), ("the done list", "DONE"),
            ("the 40-line cap", "40 lines or fewer"),
            ("the handoff is rewritten whole from the report", "rewrite the handoff whole")):
        check("audit step: the prompt names " + name, needle in prompt, "missing %r" % needle)


# --------------------------------------------------------------------------- owner waits
# Decision precompact-handoff, item 14. A coordinator's handoff keeps every item
# waiting on the owner in this session under OWNER_HEADING. The Stop nudge blocks once when that
# heading is missing, or when a refused act has no later success and the section does not name
# it. Each case runs the hook as a subprocess, the way the Stop hook runs it.

OWNER_HEADING = "## Waiting on the owner in this session"
OWNER_TITLE = "Waiting on the owner in this session"
COORD_TAG = "cs-build:coordinator"
LANE_TAG = "cs-build:lane"
REFUSED_CMD = "gh pr merge 2046 --squash"
REFUSED_TEXT = "PreToolUse:Bash hook error: [guard] blocked: a merge needs the owner's yes"
OWNER_TS = "2026-11-08T10:00:00Z"
OWNER_PROMPT_WANTS = (
    ("one line per item", r"\bone line\b"),
    ("the owner", r"\bowner\b"),
    ("a page item named by its number", r"\bnumber\b"),
    ("none when empty", r"\bnone\b"),
)
# The audit hook logs each process start the hook makes, to the file named by OWNER_WAITS_AUDIT_LOG.
AUDIT_WRAPPER = "\n".join([
    "import os, runpy, sys",
    "log = os.environ['OWNER_WAITS_AUDIT_LOG']",
    "def audit(event, args):",
    "    if event.startswith(('subprocess.', 'os.exec', 'os.spawn', 'os.posix_spawn', 'os.fork', 'os.system')):",
    "        with open(log, 'a', encoding='utf-8') as f:",
    "            f.write(event + '\\n')",
    "sys.addaudithook(audit)",
    "sys.path.insert(0, os.path.dirname(os.path.abspath(sys.argv[1])))",
    "sys.argv = sys.argv[1:]",
    "runpy.run_path(sys.argv[0], run_name='__main__')",
]) + "\n"


def as_coordinator(c, tags, sid=None):
    """A get_session result for the own session (or for sid, the record id it is known by), carrying these tags."""
    record_id = sid or c.session_id
    body = json.dumps({"ccr": {"id": record_id, "tags": tags}})
    call = {"type": "tool_use", "id": "tu-get", "name": "mcp__claude-code-remote__get_session",
            "input": {"session_id": record_id}}
    return [transcript_line("assistant", [call], timestamp=OWNER_TS),
            transcript_line("user", [{"type": "tool_result", "tool_use_id": "tu-get", "content": body}],
                            timestamp=OWNER_TS)]


def tagged_by_call(c, add, sid=None):
    """A set_session_tags call that adds these tags to sid (the own session by default)."""
    call = {"type": "tool_use", "id": "tu-set", "name": "mcp__claude-code-remote__set_session_tags",
            "input": {"session_ids": [sid or c.session_id], "add": add}}
    return [transcript_line("assistant", [call], timestamp=OWNER_TS),
            transcript_line("user", [{"type": "tool_result", "tool_use_id": "tu-set", "content": "ok"}],
                            timestamp=OWNER_TS)]


def bash_call(tu, command, description=None):
    inp = {"command": command}
    if description is not None:
        inp["description"] = description
    call = {"type": "tool_use", "id": tu, "name": "Bash", "input": inp}
    return transcript_line("assistant", [call], timestamp=OWNER_TS)


def refused_act(tu, command, description=None):
    """A Bash call and the hook's refusal of it, with no answer after it."""
    return [bash_call(tu, command, description), tool_result(REFUSED_TEXT, OWNER_TS, tool_use_id=tu)]


def coord_refusal(c):
    """A coordinator's transcript with one unanswered refused Bash call."""
    return as_coordinator(c, [COORD_TAG]) + refused_act("tu-r", REFUSED_CMD)


def owner_handoff(section, rest=None):
    """A complete handoff (handoff_text, every section but Next steps) with the owner section before
    Next steps, so only the owner check can block it. section None leaves the heading out."""
    lines = [handoff_text(omit=("Next steps",)).rstrip("\n"), ""]
    if section is not None:
        lines += [OWNER_HEADING, section, ""]
    lines += ["## Next steps", rest or "- Check the batch once the owner answers.", ""]
    return "\n".join(lines)


def stop_reason(proc):
    """The reason of a Stop block, or None when the Stop did not block. Empty or non-JSON output is no block."""
    try:
        obj = json.loads(proc.stdout or "")
    except ValueError:
        return None
    if isinstance(obj, dict) and obj.get("decision") == "block":
        return str(obj.get("reason", ""))
    return None


def owner_stop(c, lines, handoff, active=False, extra=None, via=None):
    """One Stop with this transcript. handoff None writes no handoff."""
    if handoff is not None:
        put(c.handoff_path(), handoff)
    return nudge(c, 0, active=active, lines=lines, extra=extra, via=via)


def coordinator_scope(make_lines):
    """The scope, asserted before each subject: a coordinator's Stop blocks on a handoff with no
    heading. The subject checks read the hook through this scope, so it is checked first."""
    c = Case("ow_scope")
    try:
        blocked = stop_reason(owner_stop(c, make_lines(c), handoff=owner_handoff(None))) is not None
        check("owner waits scope: a coordinator's Stop blocks on a handoff with no heading", blocked,
              "no block: the subject checks after this read an unread scope")
    finally:
        c.cleanup()


def config_state(cfg):
    """Every file under the config dir, as {relative path: bytes}."""
    state = {}
    for root, _dirs, files in os.walk(cfg):
        for name in files:
            path = os.path.join(root, name)
            with open(path, "rb") as f:
                state[os.path.relpath(path, cfg)] = f.read()
    return state


def run_audited(c, args, payload):
    """Case.run, with an audit hook in the interpreter that logs each process start the hook makes."""
    env = c.env()
    env["OWNER_WAITS_AUDIT_LOG"] = os.path.join(c.root, "audit.log")
    return subprocess.run([sys.executable, "-c", AUDIT_WRAPPER, MODULE] + list(args),
                          input=json.dumps(payload), capture_output=True, text=True, env=env, cwd=c.repo)


def audit_events(c):
    """The process starts the hook logged for this case, as event names."""
    path = os.path.join(c.root, "audit.log")
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip()]


def case_prompt_owner_waits_section():
    with open(os.path.join(HERE, "precompact_handoff_prompt.md"), "r", encoding="utf-8") as f:
        text = f.read()
    step4 = step_body(text, 4) or ""
    check("prompt owner waits: step 4 still exists", bool(step4.strip()), "no '## 4.' step")
    pos_head = step4.find(OWNER_HEADING)
    pos_rulings = step4.lower().find("rulings with no home yet")
    check("prompt owner waits: step 4 names the section %r" % OWNER_HEADING, pos_head >= 0,
          "no heading in step 4")
    check("prompt owner waits: the section comes after the Rulings with NO HOME YET bullet",
          pos_rulings >= 0 and pos_head > pos_rulings,
          "heading at %d, rulings bullet at %d" % (pos_head, pos_rulings))
    missing = window_missing(step4, OWNER_PROMPT_WANTS, span=3)
    check("prompt owner waits: three sentences or bullets of step 4 say one line per thing the owner "
          "clears, a page item by its number, and none when empty", not missing,
          "closest window lacks: %s" % "; ".join(missing))


def case_owner_waits_heading_missing_blocks():
    for name, label, make in (
            ("ow_heading_get", "get_session tags", lambda c: as_coordinator(c, [COORD_TAG])),
            ("ow_heading_set", "set_session_tags add", lambda c: tagged_by_call(c, [COORD_TAG]))):
        c = Case(name)
        try:
            proc = owner_stop(c, make(c), handoff=owner_handoff(None))
            reason = stop_reason(proc)
            check("owner waits heading (%s): exits 0" % label, proc.returncode == 0,
                  "rc=%r" % proc.returncode)
            check("owner waits heading (%s): a coordinator's Stop blocks when the handoff lacks %r"
                  % (label, OWNER_HEADING), reason is not None, "stdout: %r" % (proc.stdout or "")[:200])
            low = squash(reason)
            check("owner waits heading (%s): the block names the heading and step 4" % label,
                  OWNER_TITLE.lower() in low and "step 4" in low, "reason: %r" % reason)
        finally:
            c.cleanup()


def case_owner_waits_refused_act_blocks():
    coordinator_scope(coord_refusal)
    c = Case("ow_refused")
    try:
        proc = owner_stop(c, coord_refusal(c), handoff=owner_handoff(
            "- Page item 219: owner allow-once for an open prompt.",
            rest="- After the owner's yes, run `%s`." % REFUSED_CMD))
        reason = stop_reason(proc)
        check("owner waits refused act: exits 0", proc.returncode == 0, "rc=%r" % proc.returncode)
        check("owner waits refused act: the coordinator's Stop blocks when the section does not name the "
              "refused act (a Next steps line outside the section names it)",
              reason is not None, "stdout: %r" % (proc.stdout or "")[:200])
        check("owner waits refused act: the block names the refused act",
              reason is not None and (REFUSED_CMD in reason or "Bash" in reason), "reason: %r" % reason)
    finally:
        c.cleanup()


def case_owner_waits_none_with_refusal_blocks():
    coordinator_scope(coord_refusal)
    for count in (1, 60):  # one refused act, then a full transcript of sixty
        c = Case("ow_none_%d" % count)
        try:
            lines = as_coordinator(c, [COORD_TAG])
            for i in range(count):
                lines += refused_act("tu-%d" % i, "echo step-%02d" % i)
            reason = stop_reason(owner_stop(c, lines, handoff=owner_handoff("none")))
            check("owner waits none (%d refused): section none with an unanswered refusal blocks" % count,
                  reason is not None, "reason: %r" % reason)
            named = [i for i in range(count) if ("echo step-%02d" % i) in (reason or "")]
            check("owner waits none (%d refused): the block names one of the refused acts" % count,
                  bool(named), "reason: %r" % (reason or "")[:200])
        finally:
            c.cleanup()


def case_owner_waits_other_call_does_not_clear_refusal():
    coordinator_scope(coord_refusal)
    c = Case("ow_other_call")
    try:
        lines = coord_refusal(c) + [bash_call("tu-ok", "echo ok"),
                                    tool_result("ok", OWNER_TS, is_error=False, tool_use_id="tu-ok")]
        reason = stop_reason(owner_stop(c, lines, handoff=owner_handoff("none")))
        check("owner waits other call: a later success of another command does not clear the refused act",
              reason is not None and (REFUSED_CMD in reason or "Bash" in reason), "reason: %r" % reason)
    finally:
        c.cleanup()


def case_owner_waits_cleared_by_later_success():
    coordinator_scope(coord_refusal)
    c = Case("ow_cleared")
    try:
        lines = coord_refusal(c) + [bash_call("tu-ok", REFUSED_CMD),
                                    tool_result("merged", OWNER_TS, is_error=False, tool_use_id="tu-ok")]
        reason = stop_reason(owner_stop(c, lines, handoff=owner_handoff("none")))
        check("owner waits cleared: a refused act that a later identical call completed does not block",
              reason is None, "reason: %r" % reason)
    finally:
        c.cleanup()
    c = Case("ow_clean")
    try:
        reason = stop_reason(owner_stop(c, as_coordinator(c, [COORD_TAG]), handoff=owner_handoff("none")))
        check("owner waits none, nothing refused: section none with no unanswered refusal does not block",
              reason is None, "reason: %r" % reason)
    finally:
        c.cleanup()


def case_owner_waits_plain_error_is_not_refusal():
    coordinator_scope(coord_refusal)
    c = Case("ow_plain_error")
    try:
        lines = as_coordinator(c, [COORD_TAG]) + [bash_call("tu-e", "ls /nope"),
                                                  tool_result("Exit code 2", OWNER_TS, tool_use_id="tu-e")]
        reason = stop_reason(owner_stop(c, lines, handoff=owner_handoff("none")))
        check("owner waits plain error: a failed call that no hook or permission refused is not an "
              "omitted act", reason is None, "reason: %r" % reason)
    finally:
        c.cleanup()


def case_owner_waits_named_section_passes():
    coordinator_scope(coord_refusal)
    c = Case("ow_named")
    try:
        items = ["- Page item %d: owner allow-once, still open." % i for i in range(1, 16)]
        section = "\n".join(items + ["- Gate: `%s` waits for the owner's yes." % REFUSED_CMD])
        proc = owner_stop(c, coord_refusal(c), handoff=owner_handoff(section))
        check("owner waits named: a 16-line section that names the refused act on its last line passes",
              stop_reason(proc) is None and proc.returncode == 0, "reason: %r" % stop_reason(proc))
    finally:
        c.cleanup()


def case_owner_waits_blocks_once_per_stop():
    c = Case("ow_once")
    try:
        lines = coord_refusal(c)
        first = owner_stop(c, lines, handoff=owner_handoff(None))
        check("owner waits once: the first Stop blocks", stop_reason(first) is not None,
              "stdout: %r" % (first.stdout or "")[:200])
        again = owner_stop(c, lines, handoff=owner_handoff(None), active=True)
        check("owner waits once: a Stop with stop_hook_active set exits quietly",
              stop_reason(again) is None and again.returncode == 0, "stdout: %r" % (again.stdout or "")[:200])
    finally:
        c.cleanup()


def case_owner_waits_agent_payload_stays_quiet():
    main_case = Case("ow_agent_main")
    try:
        blocked = stop_reason(owner_stop(main_case, coord_refusal(main_case), handoff=owner_handoff(None)))
        check("owner waits agent: a session's own Stop with this transcript blocks (the scope)",
              blocked is not None, "reason: %r" % blocked)
    finally:
        main_case.cleanup()
    c = Case("ow_agent")
    try:
        proc = owner_stop(c, coord_refusal(c), handoff=owner_handoff(None), extra={"agent_id": "a1b2c3"})
        check("owner waits agent: a Stop whose payload has an agent_id exits quietly",
              stop_reason(proc) is None and proc.returncode == 0, "stdout: %r" % (proc.stdout or "")[:200])
    finally:
        c.cleanup()


def case_owner_waits_non_coordinator_stays_quiet():
    for name, label, make in (
            ("ow_lane", "lane tag", lambda c: as_coordinator(c, [LANE_TAG]) + refused_act("tu-r", REFUSED_CMD)),
            ("ow_untagged", "no tag", lambda c: refused_act("tu-r", REFUSED_CMD)),
            ("ow_tag_elsewhere", "tag set on another session",
             lambda c: tagged_by_call(c, [COORD_TAG], sid="sess-other") + refused_act("tu-r", REFUSED_CMD))):
        c = Case(name)
        try:
            proc = owner_stop(c, make(c), handoff=owner_handoff(None))
            check("owner waits non-coordinator (%s): a Stop with no heading stays quiet" % label,
                  stop_reason(proc) is None and proc.returncode == 0, "stdout: %r" % (proc.stdout or "")[:200])
        finally:
            c.cleanup()


def case_owner_waits_no_handoff_stays_quiet():
    coordinator_scope(coord_refusal)
    c = Case("ow_no_handoff")
    try:
        proc = owner_stop(c, coord_refusal(c), handoff=None)
        check("owner waits no handoff: a coordinator's Stop with no handoff file exits 0 and does not block",
              stop_reason(proc) is None and proc.returncode == 0, "stdout: %r" % (proc.stdout or "")[:200])
    finally:
        c.cleanup()


def case_owner_waits_fails_open():
    coordinator_scope(coord_refusal)
    c = Case("ow_open_transcript")
    try:
        payload = {"session_id": c.session_id, "transcript_path": os.path.join(c.root, "missing.jsonl"),
                   "hook_event_name": "Stop", "stop_hook_active": False}
        proc = c.run(["--nudge"], payload)
        check("owner waits fails open: an unreadable transcript exits 0 and does not block",
              proc.returncode == 0 and stop_reason(proc) is None,
              "rc=%r stdout=%r" % (proc.returncode, (proc.stdout or "")[:200]))
    finally:
        c.cleanup()
    c = Case("ow_open_handoff")
    try:
        os.makedirs(os.path.dirname(c.handoff_path()), exist_ok=True)
        with open(c.handoff_path(), "wb") as f:
            f.write(b"## Goal\n\xff\xfe not UTF-8\n")
        proc = nudge(c, 0, lines=coord_refusal(c))
        check("owner waits fails open: an undecodable handoff exits 0 and does not block",
              proc.returncode == 0 and stop_reason(proc) is None,
              "rc=%r stdout=%r" % (proc.returncode, (proc.stdout or "")[:200]))
    finally:
        c.cleanup()


def case_owner_waits_writes_no_file_and_starts_no_process():
    coordinator_scope(coord_refusal)
    c = Case("ow_cost")
    try:
        put(c.handoff_path(), owner_handoff(None))
        # The nudge bookkeeping every Stop rewrites with the same bytes: a run that changes nothing
        # else leaves the config dir exactly as it was.
        put(c.nudge_path(), json.dumps({"bucket": -1}))
        before = config_state(c.cfg)
        proc = nudge(c, 0, lines=coord_refusal(c), via=lambda args, payload: run_audited(c, args, payload))
        check("owner waits cost: the coordinator's Stop blocks on this run",
              stop_reason(proc) is not None, "stdout: %r" % (proc.stdout or "")[:200])
        after = config_state(c.cfg)
        changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
        check("owner waits cost: the run changes no file in the config dir", not changed,
              "changed: %r" % changed)
        started = audit_events(c)
        check("owner waits cost: the run starts no process", not started, "started: %r" % started)
    finally:
        c.cleanup()


# --- owner waits: cloud record id, act-keyed answers, scan cost, fenced sections ------------------
# A cloud session names itself three ways: the Stop payload by UUID, its env by cse_<x>, and its
# get_session record and set_session_tags calls by session_<x>. The hook must read the record id.
REMOTE_PAYLOAD_ID = "5f2b8c1e-3d4a-4b6e-9c7f-0a1b2c3d4e5f"
REMOTE_CSE = "cse_Hq3vN8rT"
REMOTE_SESSION = "session_Hq3vN8rT"
OTHER_SESSION = "session_Zp7kLw2b"
MERGE_PR12 = "gh pr merge 12"
COST_PAIRS = 1000  # a plain transcript of 2000 lines: Bash calls and their successful results
FENCED_SECTION = "\n".join([
    "- Page item 219: owner allow-once for an open prompt.",
    "```bash",
    "# merge after the owner's yes",
    "echo waiting",
    "```",
    "- Gate: `%s` waits for the owner's yes." % REFUSED_CMD,
])
UNFENCED_SECTION = "\n".join([
    "- Page item 219: owner allow-once for an open prompt.",
    "# merge after the owner's yes",
    "echo waiting",
    "- Gate: `%s` waits for the owner's yes." % REFUSED_CMD,
])


def cloud_case(name):
    """A Case for a cloud session: the Stop payload names it by UUID, and the env names it cse_<x>."""
    c = Case(name, extra_env={"CLAUDE_CODE_REMOTE_SESSION_ID": REMOTE_CSE})
    c.session_id = REMOTE_PAYLOAD_ID
    return c


def case_owner_waits_cloud_record_id_blocks():
    coordinator_scope(coord_refusal)
    c = cloud_case("ow_cloud_get")
    try:
        proc = owner_stop(c, as_coordinator(c, [COORD_TAG], sid=REMOTE_SESSION), handoff=owner_handoff(None))
        reason = stop_reason(proc)
        check("owner waits cloud id (get_session): a cloud coordinator whose record is session_<x> blocks when "
              "its handoff lacks the heading", reason is not None and proc.returncode == 0,
              "rc=%r stdout: %r" % (proc.returncode, (proc.stdout or "")[:200]))
    finally:
        c.cleanup()


def case_owner_waits_cloud_set_tags_blocks():
    coordinator_scope(coord_refusal)
    c = cloud_case("ow_cloud_set")
    try:
        reason = stop_reason(owner_stop(c, tagged_by_call(c, [COORD_TAG], sid=REMOTE_SESSION),
                                        handoff=owner_handoff(None)))
        check("owner waits cloud id (set_session_tags): a set_session_tags call that names session_<x> tags a "
              "cloud coordinator, and its Stop blocks", reason is not None, "reason: %r" % reason)
    finally:
        c.cleanup()


def case_owner_waits_cloud_other_record_stays_quiet():
    coordinator_scope(coord_refusal)
    c = cloud_case("ow_cloud_other")
    try:
        reason = stop_reason(owner_stop(c, as_coordinator(c, [COORD_TAG], sid=OTHER_SESSION),
                                        handoff=owner_handoff(None)))
        check("owner waits cloud id (other record): a coordinator record for another session does not make "
              "this cloud session a coordinator", reason is None, "reason: %r" % reason)
    finally:
        c.cleanup()


def case_owner_waits_answer_key_is_the_act():
    coordinator_scope(coord_refusal)
    c = Case("ow_answer_key")
    try:
        lines = as_coordinator(c, [COORD_TAG]) + refused_act("tu-r", MERGE_PR12, description="Merge PR 12") + [
            bash_call("tu-ok", MERGE_PR12, description="Merge pull request 12 now"),
            tool_result("merged", OWNER_TS, is_error=False, tool_use_id="tu-ok")]
        reason = stop_reason(owner_stop(c, lines, handoff=owner_handoff("none")))
        check("owner waits answer key: a refused act that a later success of the same command answers does not "
              "block, though the two descriptions differ", reason is None, "reason: %r" % reason)
    finally:
        c.cleanup()
    c = Case("ow_answer_other")
    try:
        lines = as_coordinator(c, [COORD_TAG]) + refused_act("tu-r", MERGE_PR12, description="Merge PR 12") + [
            bash_call("tu-ok", "gh pr merge 13", description="Merge PR 12"),
            tool_result("merged", OWNER_TS, is_error=False, tool_use_id="tu-ok")]
        reason = stop_reason(owner_stop(c, lines, handoff=owner_handoff("none")))
        check("owner waits answer key control: a success of another command with the same description does not "
              "answer the refused act", reason is not None and MERGE_PR12 in reason, "reason: %r" % reason)
    finally:
        c.cleanup()


def plain_lines(pairs):
    """Bash calls and their successful results. No coordinator tag text anywhere."""
    lines = []
    for i in range(pairs):
        tu = "tu-p%d" % i
        lines.append(bash_call(tu, "echo step-%04d" % i))
        lines.append(tool_result("step-%04d done" % i, OWNER_TS, is_error=False, tool_use_id=tu))
    return lines


def gap_with_decodes(c, lines):
    """owner_waits_gap over these transcript lines, in-process, as (reason, error, JSON decodes it made).
    Every json.loads reaches JSONDecoder.raw_decode, so counting there sees a parse in any module."""
    tp = os.path.join(c.root, "cost-transcript.jsonl")
    write_transcript(tp, lines)
    decodes = [0]
    original = json.decoder.JSONDecoder.raw_decode

    def counting(self, s, idx=0):
        decodes[0] += 1
        return original(self, s, idx)

    json.decoder.JSONDecoder.raw_decode = counting
    try:
        with Env(CLAUDE_CONFIG_DIR=c.cfg, CLAUDE_CODE_REMOTE_SESSION_ID=None):
            reason, err = call_under_test("owner_waits_gap", {"session_id": c.session_id, "transcript_path": tp})
    finally:
        json.decoder.JSONDecoder.raw_decode = original
    return reason, err, decodes[0]


def case_owner_waits_cost_skips_plain_transcripts():
    coordinator_scope(coord_refusal)
    c = Case("ow_cost_parse")
    try:
        # A handoff must exist, or the hook returns before it reads the transcript at all.
        put(c.handoff_path(), owner_handoff(None))
        plain = plain_lines(COST_PAIRS)
        reason, err, decodes = gap_with_decodes(c, plain)
        check("owner waits cost (parse): the owner waits check runs without error on a plain transcript",
              err is None, "error: %r" % err)
        check("owner waits cost (parse): a session with no coordinator tag text gets no reason",
              not reason, "reason: %r" % reason)
        check("owner waits cost (parse): a plain transcript of %d lines is not decoded line by line "
              "(%d decodes)" % (len(plain), decodes), decodes * 10 < len(plain),
              "%d decodes for %d lines" % (decodes, len(plain)))
        coord_reason, coord_err, _ = gap_with_decodes(c, as_coordinator(c, [COORD_TAG]) + plain)
        check("owner waits cost (parse): a coordinator's transcript of the same size still blocks when the "
              "handoff lacks the heading", coord_err is None and bool(coord_reason),
              "error: %r reason: %r" % (coord_err, coord_reason))
    finally:
        c.cleanup()


def case_owner_waits_fenced_comment_keeps_section():
    coordinator_scope(coord_refusal)
    c = Case("ow_fenced")
    try:
        proc = owner_stop(c, coord_refusal(c), handoff=owner_handoff(FENCED_SECTION))
        reason = stop_reason(proc)
        check("owner waits fence: a '# comment' line inside a fenced block does not end the section, so the "
              "refused act named after the block is named", reason is None and proc.returncode == 0,
              "rc=%r reason: %r" % (proc.returncode, reason))
    finally:
        c.cleanup()
    c = Case("ow_unfenced")
    try:
        proc = owner_stop(c, coord_refusal(c), handoff=owner_handoff(UNFENCED_SECTION))
        reason = stop_reason(proc)
        check("owner waits fence control: the same comment line outside a fence still ends the section, so the "
              "act named after it blocks", reason is not None, "reason: %r" % reason)
    finally:
        c.cleanup()


# --- owner waits: act names, odd transcript lines, tag spelling -----------------------------------
# The handoff check names a refused act by the whole first line of its command. Two commands that
# share their first 60 characters must each be named, or one name would cover both.
SAME_HEAD = "cd /home/user/claude-settings/.claude/worktrees/agent-release-candidate && npm publish"
PUBLISH_A = SAME_HEAD + " a"
PUBLISH_B = SAME_HEAD + " b --force"
ONLY_A_SECTION = "- Gate: `%s` waits for the owner's yes." % PUBLISH_A
ONLY_B_SECTION = "- Gate: `%s` waits for the owner's yes." % PUBLISH_B
ODD_MESSAGE_LINE = json.dumps({"type": "system", "message": "hello"})
SPELLED_TAG = "CS-Build:Coordinator "
NEAR_MISS_TAG = "cs-build:coordinatorx"
# An assistant text line with the lowercase tag text. The raw read finds it; no record or call carries it.
TAG_TEXT_LINE = transcript_line("assistant", [{"type": "text", "text": "Tagged cs-build:coordinator on the record."}])


def two_refusals(c):
    """A coordinator's transcript with two unanswered refusals of commands that share their first 60 characters."""
    return as_coordinator(c, [COORD_TAG]) + refused_act("tu-a", PUBLISH_A) + refused_act("tu-b", PUBLISH_B)


def case_owner_waits_same_head_acts():
    coordinator_scope(two_refusals)
    check("owner waits same head (data): the two refused commands differ and share their first 60 characters",
          PUBLISH_A != PUBLISH_B and PUBLISH_A[:60] == PUBLISH_B[:60],
          "A: %r B: %r" % (PUBLISH_A, PUBLISH_B))
    c = Case("ow_head_only_a")
    try:
        reason = stop_reason(owner_stop(c, two_refusals(c), handoff=owner_handoff(ONLY_A_SECTION)))
        check("owner waits same head (names A only): a section that names only the first refused command does "
              "not cover the second, so the Stop blocks", reason is not None, "reason: %r" % reason)
    finally:
        c.cleanup()
    c = Case("ow_head_only_b")
    try:
        reason = stop_reason(owner_stop(c, two_refusals(c), handoff=owner_handoff(ONLY_B_SECTION)))
        check("owner waits same head (names B only): a section that names only the second refused command does "
              "not cover the first, so the Stop blocks", reason is not None, "reason: %r" % reason)
    finally:
        c.cleanup()
    c = Case("ow_head_both")
    try:
        proc = owner_stop(c, two_refusals(c), handoff=owner_handoff("\n".join([ONLY_A_SECTION, ONLY_B_SECTION])))
        check("owner waits same head (names both): a section that names both refused commands passes",
              stop_reason(proc) is None and proc.returncode == 0,
              "rc=%r reason: %r" % (proc.returncode, stop_reason(proc)))
    finally:
        c.cleanup()
    c = Case("ow_head_labels")
    try:
        reason = stop_reason(owner_stop(c, two_refusals(c), handoff=owner_handoff("none")))
        check("owner waits same head (blocks): a section of 'none' with two refusals blocks",
              reason is not None, "reason: %r" % reason)
        labels = re.findall(r"Bash `([^`]*)`", reason or "")
        check("owner waits same head (labels): the block labels the two refused commands with distinct text",
              len(labels) == 2 and labels[0] != labels[1], "labels: %r" % labels)
    finally:
        c.cleanup()


def case_owner_waits_odd_message_line_still_blocks():
    coordinator_scope(coord_refusal)
    c = Case("ow_odd_message")
    try:
        lines = as_coordinator(c, [COORD_TAG]) + [ODD_MESSAGE_LINE] + refused_act("tu-r", REFUSED_CMD)
        proc = owner_stop(c, lines, handoff=owner_handoff("none"))
        reason = stop_reason(proc)
        check("owner waits odd line: a transcript line whose message is a string does not switch the check off, "
              "so a coordinator's unnamed refusal after it blocks", reason is not None,
              "reason: %r stderr: %r" % (reason, (proc.stderr or "")[-200:]))
    finally:
        c.cleanup()


def case_owner_waits_tag_precheck_reads_any_spelling():
    coordinator_scope(coord_refusal)
    c = Case("ow_tag_precheck")
    try:
        put(c.handoff_path(), owner_handoff("none"))
        lines = as_coordinator(c, [SPELLED_TAG]) + plain_lines(50) + refused_act("tu-r", REFUSED_CMD)
        reason, err, decodes = gap_with_decodes(c, lines)
        check("owner waits tag spelling (pre-check): a record tagged 'CS-Build:Coordinator ' is read, so the "
              "transcript is parsed", err is None and decodes > 0,
              "error: %r decodes: %r reason: %r" % (err, decodes, reason))
    finally:
        c.cleanup()


def case_owner_waits_tag_spelling_record_blocks():
    coordinator_scope(coord_refusal)
    c = Case("ow_tag_record")
    try:
        lines = [TAG_TEXT_LINE] + as_coordinator(c, [SPELLED_TAG]) + refused_act("tu-r", REFUSED_CMD)
        reason = stop_reason(owner_stop(c, lines, handoff=owner_handoff("none")))
        check("owner waits tag spelling (record): a get_session record tagged 'CS-Build:Coordinator ' makes the "
              "session a coordinator, so its unnamed refusal blocks", reason is not None, "reason: %r" % reason)
    finally:
        c.cleanup()


def case_owner_waits_tag_spelling_set_tags_blocks():
    coordinator_scope(coord_refusal)
    c = Case("ow_tag_set")
    try:
        lines = [TAG_TEXT_LINE] + tagged_by_call(c, [SPELLED_TAG]) + refused_act("tu-r", REFUSED_CMD)
        reason = stop_reason(owner_stop(c, lines, handoff=owner_handoff("none")))
        check("owner waits tag spelling (set_session_tags): a call that adds 'CS-Build:Coordinator ' makes the "
              "session a coordinator, so its unnamed refusal blocks", reason is not None, "reason: %r" % reason)
    finally:
        c.cleanup()


def case_owner_waits_near_miss_tag_stays_quiet():
    coordinator_scope(coord_refusal)
    c = Case("ow_tag_near")
    try:
        lines = [TAG_TEXT_LINE] + as_coordinator(c, [NEAR_MISS_TAG]) + refused_act("tu-r", REFUSED_CMD)
        reason = stop_reason(owner_stop(c, lines, handoff=owner_handoff("none")))
        check("owner waits tag near miss: a record tagged 'cs-build:coordinatorx' is no coordinator, so its "
              "refusal stays quiet", reason is None, "reason: %r" % reason)
    finally:
        c.cleanup()


# --- owner waits: a name that is text inside another name ---------------------------------------
# The handoff check looks for each refused act's identifier as text in the section. The plain push is
# text inside the force push, so a section that names only the force push must still leave the plain
# push unnamed.
PUSH_PLAIN = "git push"
PUSH_FORCE = "git push --force origin main"
PUSH_PLAIN_LINE = "- Gate: `%s` waits for the owner's yes." % PUSH_PLAIN
PUSH_FORCE_LINE = "- Gate: `%s` waits for the owner's yes." % PUSH_FORCE


def two_pushes(c):
    """A coordinator's transcript with two unanswered refusals: a command, and a longer command that holds it as text."""
    return as_coordinator(c, [COORD_TAG]) + refused_act("tu-push", PUSH_PLAIN) + refused_act("tu-force", PUSH_FORCE)


def case_owner_waits_substring_act_blocks():
    coordinator_scope(two_pushes)
    check("owner waits substring (data): the first refused command is text inside the second",
          PUSH_FORCE.startswith(PUSH_PLAIN) and PUSH_PLAIN != PUSH_FORCE,
          "plain: %r force: %r" % (PUSH_PLAIN, PUSH_FORCE))
    c = Case("ow_substring_only_force")
    try:
        reason = stop_reason(owner_stop(c, two_pushes(c), handoff=owner_handoff(PUSH_FORCE_LINE)))
        check("owner waits substring: a section that names only `%s` does not name the refused `%s`, which "
              "it holds as text, so the Stop blocks on the plain push" % (PUSH_FORCE, PUSH_PLAIN),
              reason is not None and "Bash `%s`" % PUSH_PLAIN in reason and "Bash `%s`" % PUSH_FORCE not in reason,
              "reason: %r" % reason)
    finally:
        c.cleanup()
    c = Case("ow_substring_both")
    try:
        proc = owner_stop(c, two_pushes(c), handoff=owner_handoff("\n".join([PUSH_PLAIN_LINE, PUSH_FORCE_LINE])))
        check("owner waits substring (control): a section that names both refused commands passes",
              stop_reason(proc) is None and proc.returncode == 0,
              "rc=%r reason: %r" % (proc.returncode, stop_reason(proc)))
    finally:
        c.cleanup()


def main() -> int:
    case_prompt_names_audit_agent()
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
    case_window_limit_suffix_forms()
    case_window_value_rows()
    case_handoff_path_not_frozen()
    case_handoffs_dir_is_made()
    case_handoffs_dir_keeps_other_sessions()
    case_prompt_lists_working_premises()
    case_prompt_step5_names_checked_stamp()
    case_prompt_names_list_home_not_copy()
    case_prompt_owner_waits_section()
    case_reorient_lists_weak_premises()
    case_reorient_premise_lines_survive_odd_text()
    case_reorient_flags_missing_premises()
    case_reorient_survives_undecodable_handoff()
    case_nudge_points_at_step4()
    case_premise_kinds_one_home()
    case_premise_strength_comes_from_kinds()
    case_summary_fraction_table()
    case_summary_fraction_exact_key_beats_default()
    case_summary_fraction_sdk_or_repl()
    case_summary_fraction_falls_to_scalar()
    case_summary_fraction_defaults()
    case_summary_fraction_reads_config_dir_file()
    case_compact_threshold_reads_flag_and_remote()
    case_compact_threshold_pct_override_every_window()
    case_nudge_reads_summary_flag()
    case_digest_since_keeps_text_after_handoff()
    case_digest_lists_refused_acts_after_handoff()
    case_digest_plain_errors_are_not_refusals()
    case_digest_refusal_shapes()
    case_digest_refused_line_limits()
    case_precompact_digest_starts_at_handoff()
    case_precompact_digest_without_handoff()
    case_prompt_marker_names_the_sections()
    case_step4_bullets_lead_with_the_marker_names()
    case_code_holds_no_section_names()
    case_nudge_flags_a_damaged_handoff_once_per_mtime()
    case_nudge_sections_quiet_when_complete_absent_or_active()
    case_nudge_sections_fail_open_on_bad_prompt()
    case_nudge_sections_flags_an_empty_handoff()
    case_nudge_sections_count_numbered_headings()
    case_one_reader_for_the_premises_section()
    case_owner_waits_heading_missing_blocks()
    case_owner_waits_refused_act_blocks()
    case_owner_waits_none_with_refusal_blocks()
    case_owner_waits_other_call_does_not_clear_refusal()
    case_owner_waits_cleared_by_later_success()
    case_owner_waits_plain_error_is_not_refusal()
    case_owner_waits_named_section_passes()
    case_owner_waits_blocks_once_per_stop()
    case_owner_waits_agent_payload_stays_quiet()
    case_owner_waits_non_coordinator_stays_quiet()
    case_owner_waits_no_handoff_stays_quiet()
    case_owner_waits_fails_open()
    case_owner_waits_writes_no_file_and_starts_no_process()
    case_owner_waits_cloud_record_id_blocks()
    case_owner_waits_cloud_set_tags_blocks()
    case_owner_waits_cloud_other_record_stays_quiet()
    case_owner_waits_answer_key_is_the_act()
    case_owner_waits_cost_skips_plain_transcripts()
    case_owner_waits_fenced_comment_keeps_section()
    case_owner_waits_same_head_acts()
    case_owner_waits_odd_message_line_still_blocks()
    case_owner_waits_tag_precheck_reads_any_spelling()
    case_owner_waits_tag_spelling_record_blocks()
    case_owner_waits_tag_spelling_set_tags_blocks()
    case_owner_waits_near_miss_tag_stays_quiet()
    case_owner_waits_substring_act_blocks()

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
