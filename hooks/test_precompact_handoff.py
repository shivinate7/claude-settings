#!/usr/bin/env python3
"""Cases for hooks/precompact_handoff.py. Standard library only, and no test runner.

Run it from the repository root:

    python hooks/test_precompact_handoff.py

RED BEFORE GREEN. `hooks/precompact_handoff.py` does not exist yet (decisions/precompact-
handoff.md is the spec), so every case below must fail now, and fail for the right reason:
the hook file is missing, so it never calls the child, never writes state, never prints a
reorient message. Once the builder lands the file, every case must go green.

Each case gets its own temp root: a real git repo (the hook's `cwd`, and its own top
level), a `CLAUDE_CONFIG_DIR`, and a `bin` dir on PATH holding a fake `claude` (the same
extension-less-plus-`.cmd`-shim trick `put_shim` uses in merge/test_merge.py, needed because
Windows `shutil.which` never matches an extension-less script). The fake records its own
argv, cwd and env to a JSON file next to itself -- found via its OWN script path, never via
an inherited env var or a fixed cwd, so it works whether the hook inherits this process's
environment for the child or builds the child's env from scratch. It then prints whatever
this case scripted, and exits with whatever code this case scripted.
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


def word_in(word, text):
    """True when `word` appears as a whole token in `text`, not as part of a longer one --
    so a tool list joined with commas or spaces both read the same, and "Bash" never
    matches inside some other word that happens to contain it."""
    return re.search(r'(?<![A-Za-z])%s(?![A-Za-z])' % re.escape(word), text) is not None


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


FAKE_CLAUDE = (
    "import json, os, sys\n"
    "HERE = os.path.dirname(os.path.abspath(__file__))\n"
    "cfg = {}\n"
    "cfg_path = os.path.join(HERE, 'fake_claude_config.json')\n"
    "if os.path.isfile(cfg_path):\n"
    "    with open(cfg_path, 'r', encoding='utf-8') as f:\n"
    "        cfg = json.load(f)\n"
    "record = {\n"
    "    'argv': sys.argv[1:],\n"
    "    'cwd': os.getcwd(),\n"
    "    'child_flag': os.environ.get('CLAUDE_HANDOFF_CHILD'),\n"
    "    'stdin': sys.stdin.read(),\n"
    "}\n"
    "with open(os.path.join(HERE, 'fake_claude_record.json'), 'w', encoding='utf-8') as f:\n"
    "    json.dump(record, f)\n"
    "stdout = cfg.get('stdout', '')\n"
    "if stdout:\n"
    "    sys.stdout.write(stdout)\n"
    "sys.exit(cfg.get('exit_code', 0))\n"
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

    def configure_claude(self, stdout="", exit_code=0):
        put(os.path.join(self.bin, "fake_claude_config.json"),
            json.dumps({"stdout": stdout, "exit_code": exit_code}))

    def record(self):
        path = os.path.join(self.bin, "fake_claude_record.json")
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def env(self, extra=None):
        env = dict(os.environ)
        env["CLAUDE_CONFIG_DIR"] = self.cfg
        env["PATH"] = self.bin + os.pathsep + env.get("PATH", "")
        if extra:
            env.update(extra)
        return env

    def run(self, args, payload, extra_env=None):
        env = self.env(extra_env)
        return subprocess.run([sys.executable, MODULE] + args, input=json.dumps(payload),
                               capture_output=True, text=True, env=env, cwd=self.repo)

    def run_precompact(self, transcript_lines, extra_env=None):
        tpath = os.path.join(self.root, "transcript.jsonl")
        write_transcript(tpath, transcript_lines)
        payload = {"session_id": self.session_id, "transcript_path": tpath, "cwd": self.repo,
                   "hook_event_name": "PreCompact"}
        return self.run([], payload, extra_env)

    def run_reorient(self):
        payload = {"session_id": self.session_id, "hook_event_name": "SessionStart",
                   "source": "compact", "cwd": self.repo}
        return self.run(["--reorient"], payload)

    def state_path(self):
        return os.path.join(self.cfg, "state", "handoff", "%s.json" % self.session_id)

    def read_state(self):
        path = self.state_path()
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


# --------------------------------------------------------------------------- PreCompact


def case_precompact_calls_child_once():
    c = Case("basic")
    try:
        handoff_path = os.path.join(c.repo, "HANDOFF.md")
        plan_path = os.path.join(c.repo, "plans", "p1.md")
        last_line = json.dumps({"handoff": handoff_path, "plan": plan_path})
        c.configure_claude(stdout="some chatter the child printed first\n" + last_line + "\n")
        lines = [transcript_line("user", [{"type": "text", "text": "hello"}])]
        c.run_precompact(lines)
        rec = c.record()
        check("basic: child ran once", rec is not None, "fake claude was never invoked")
        if rec is not None:
            argv_text = " ".join(rec["argv"])
            check("basic: model sonnet", word_in("sonnet", argv_text),
                  "argv carried no 'sonnet' token: %r" % rec["argv"])
            check("basic: cwd is the repo top level",
                  os.path.realpath(rec["cwd"]) == os.path.realpath(c.repo),
                  "child cwd was %r, not the repo %r" % (rec["cwd"], c.repo))
            check("basic: env CLAUDE_HANDOFF_CHILD=1", rec["child_flag"] == "1",
                  "child env carried CLAUDE_HANDOFF_CHILD=%r" % rec["child_flag"])
            for tool in ("Read", "Write", "Edit", "Glob", "Grep"):
                check("basic: tool %s granted" % tool, word_in(tool, argv_text),
                      "argv never named %s: %r" % (tool, rec["argv"]))
            check("basic: Bash NOT granted", not word_in("Bash", argv_text),
                  "argv named Bash, which must be excluded: %r" % rec["argv"])
        state = c.read_state()
        check("basic: state file written", state is not None,
              "no state file at %s" % c.state_path())
        if state is not None:
            check("basic: state ok=true", state.get("ok") is True, "state: %r" % state)
            check("basic: state records the handoff path",
                  state.get("handoff") == handoff_path, "state: %r" % state)
            check("basic: state records the plan path",
                  state.get("plan") == plan_path, "state: %r" % state)
    finally:
        c.cleanup()


def case_digest_filters_and_caps():
    c = Case("digest")
    try:
        old_block = "OLDBLOCK" + ("A" * 100000)
        new_block = "NEWBLOCK" + ("B" * 100000)
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
        c.configure_claude(stdout=json.dumps(
            {"handoff": os.path.join(c.repo, "HANDOFF.md"), "plan": None}) + "\n")
        c.run_precompact(lines)
        rec = c.record()
        check("digest: child ran", rec is not None, "fake claude was never invoked")
        if rec is not None:
            haystack = " ".join(rec["argv"]) + "\n" + (rec.get("stdin") or "")
            check("digest: newest user/assistant text reached the child",
                  "NEWBLOCK" in haystack,
                  "the most recent text never reached the child")
            check("digest: oldest text was cut by the 150,000-char cap",
                  "OLDBLOCK" not in haystack,
                  "text past the cap still reached the child")
            check("digest: tool_result content dropped", "TOOLRESULTMARKER" not in haystack,
                  "a tool_result block reached the child")
            check("digest: thinking content dropped", "THINKINGMARKER" not in haystack,
                  "a thinking block reached the child")
            kept_filler = sum(1 for ch in haystack if ch in "AB")
            check("digest: kept text is near the 150,000-char cap, not the full ~200,000",
                  kept_filler <= 150000 + 1000,
                  "kept %d filler chars, want roughly <= 150,000" % kept_filler)
    finally:
        c.cleanup()


def case_recursion_guard():
    c = Case("recursion")
    try:
        c.configure_claude(stdout=json.dumps({"handoff": "x", "plan": None}) + "\n")
        lines = [transcript_line("user", [{"type": "text", "text": "hi"}])]
        proc = c.run_precompact(lines, extra_env={"CLAUDE_HANDOFF_CHILD": "1"})
        check("recursion: hook exits 0", proc.returncode == 0,
              "returncode=%r stderr=%r" % (proc.returncode, proc.stderr[-300:]))
        check("recursion: the child is never invoked", c.record() is None,
              "the fake claude ran even though CLAUDE_HANDOFF_CHILD was already set")
    finally:
        c.cleanup()


def case_failure_child_exits_nonzero():
    c = Case("fail_exit")
    try:
        c.configure_claude(stdout="", exit_code=3)
        lines = [transcript_line("user", [{"type": "text", "text": "hi"}])]
        proc = c.run_precompact(lines)
        check("fail-exit: hook never exits 2", proc.returncode != 2,
              "returncode=%r" % proc.returncode)
        check("fail-exit: hook exits 0", proc.returncode == 0,
              "returncode=%r stderr=%r" % (proc.returncode, proc.stderr[-300:]))
        out = (proc.stdout or "").lower()
        check("fail-exit: no block decision printed",
              '"block"' not in out and '"deny"' not in out,
              "stdout: %r" % proc.stdout)
        state = c.read_state()
        check("fail-exit: state written", state is not None, "no state file")
        if state is not None:
            check("fail-exit: state ok=false", state.get("ok") is False, "state: %r" % state)
    finally:
        c.cleanup()


def case_failure_child_prints_no_json():
    c = Case("fail_nojson")
    try:
        c.configure_claude(stdout="I did some work but forgot the summary line\n", exit_code=0)
        lines = [transcript_line("user", [{"type": "text", "text": "hi"}])]
        proc = c.run_precompact(lines)
        check("fail-nojson: hook never exits 2", proc.returncode != 2,
              "returncode=%r" % proc.returncode)
        check("fail-nojson: hook exits 0", proc.returncode == 0,
              "returncode=%r stderr=%r" % (proc.returncode, proc.stderr[-300:]))
        out = (proc.stdout or "").lower()
        check("fail-nojson: no block decision printed",
              '"block"' not in out and '"deny"' not in out,
              "stdout: %r" % proc.stdout)
        state = c.read_state()
        check("fail-nojson: state written", state is not None, "no state file")
        if state is not None:
            check("fail-nojson: state ok=false", state.get("ok") is False, "state: %r" % state)
    finally:
        c.cleanup()


# --------------------------------------------------------------------------- reorient


def case_reorient_ok_with_plan():
    c = Case("reorient_ok")
    try:
        handoff_path = os.path.join(c.repo, "HANDOFF.md")
        plan_path = os.path.join(c.repo, "plans", "p1.md")
        put(c.state_path(), json.dumps({"handoff": handoff_path, "plan": plan_path, "ok": True}))
        proc = c.run_reorient()
        out = proc.stdout or ""
        check("reorient-ok: exits 0", proc.returncode == 0,
              "returncode=%r stderr=%r" % (proc.returncode, proc.stderr[-300:]))
        check("reorient-ok: names the handoff path", handoff_path in out, "stdout: %r" % out)
        check("reorient-ok: names the plan path", plan_path in out, "stdout: %r" % out)
    finally:
        c.cleanup()


def case_reorient_ok_no_plan():
    c = Case("reorient_noplan")
    try:
        handoff_path = os.path.join(c.repo, "HANDOFF.md")
        put(c.state_path(), json.dumps({"handoff": handoff_path, "plan": None, "ok": True}))
        proc = c.run_reorient()
        out = proc.stdout or ""
        check("reorient-noplan: exits 0", proc.returncode == 0,
              "returncode=%r stderr=%r" % (proc.returncode, proc.stderr[-300:]))
        check("reorient-noplan: names the handoff path", handoff_path in out, "stdout: %r" % out)
        check("reorient-noplan: no plan clause, since no plan was set",
              "plan" not in out.lower(),
              "stdout named a plan with none set: %r" % out)
    finally:
        c.cleanup()


def case_reorient_missing_state():
    c = Case("reorient_missing")
    try:
        proc = c.run_reorient()
        out = proc.stdout or ""
        check("reorient-missing: exits 0", proc.returncode == 0,
              "returncode=%r stderr=%r" % (proc.returncode, proc.stderr[-300:]))
        check("reorient-missing: says the handoff update failed", "fail" in out.lower(),
              "stdout: %r" % out)
    finally:
        c.cleanup()


def case_reorient_failed_state():
    c = Case("reorient_failed")
    try:
        put(c.state_path(), json.dumps({"handoff": None, "plan": None, "ok": False}))
        proc = c.run_reorient()
        out = proc.stdout or ""
        check("reorient-failed: exits 0", proc.returncode == 0,
              "returncode=%r stderr=%r" % (proc.returncode, proc.stderr[-300:]))
        check("reorient-failed: says the handoff update failed", "fail" in out.lower(),
              "stdout: %r" % out)
    finally:
        c.cleanup()


# --------------------------------------------------------------------------- settings.json


def case_settings_json():
    path = os.path.join(REPO_ROOT, "settings.json")
    with open(path, "r", encoding="utf-8") as f:
        settings = json.load(f)
    env = settings.get("env", {})
    check("settings: CLAUDE_AUTOCOMPACT_PCT_OVERRIDE is \"50\"",
          env.get("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE") == "50", "env: %r" % env)

    hooks = settings.get("hooks", {})

    def entries(event):
        out = []
        for group in hooks.get(event, []):
            for h in group.get("hooks", []):
                out.append((group.get("matcher"), h))
        return out

    precompact = entries("PreCompact")
    found = [h for (_, h) in precompact
             if "precompact_handoff.py" in h.get("command", "") and h.get("timeout") == 300]
    check("settings: a PreCompact hook runs precompact_handoff.py with timeout 300",
          bool(found), "PreCompact hooks: %r" % precompact)

    session_start = entries("SessionStart")
    found2 = [(m, h) for (m, h) in session_start
              if m == "compact" and "precompact_handoff.py" in h.get("command", "")
              and "--reorient" in h.get("command", "")]
    check("settings: a SessionStart hook, matcher 'compact', runs it with --reorient",
          bool(found2), "SessionStart hooks: %r" % session_start)


# --------------------------------------------------------------------------- the run


def main() -> int:
    case_precompact_calls_child_once()
    case_digest_filters_and_caps()
    case_recursion_guard()
    case_failure_child_exits_nonzero()
    case_failure_child_prints_no_json()
    case_reorient_ok_with_plan()
    case_reorient_ok_no_plan()
    case_reorient_missing_state()
    case_reorient_failed_state()
    case_settings_json()

    if FAILED:
        print()
        print("test_precompact_handoff FAIL: %d failing check(s)" % len(FAILED))
        return 1
    print()
    print("test_precompact_handoff PASS: all checks right")
    return 0


if __name__ == "__main__":
    sys.exit(main())
