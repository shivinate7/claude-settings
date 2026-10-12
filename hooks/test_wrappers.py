#!/usr/bin/env python3
"""Cases for the hook command wrappers in settings.json. Standard library only.

Run it from the repository root:

    python hooks/test_wrappers.py

Contract, from decision gate-hooks-fail-closed:
- The six gate entries (PreToolUse guard, stall_watch, ste_gate, question_outcome,
  sim_boot_record; PermissionRequest rm_prompt_answer) carry `"onFailure": "block"`.
- A gate whose script is missing exits 2 and prints a remedy line naming install.sh and install.ps1.
- A gate whose script exists but has no python on PATH exits 2 with the same remedy names.
- Advisory entries (SessionStart, Stop, PreCompact, SessionEnd, PostToolUse, SubagentStop) exit 0
  when their script is missing, and carry no `onFailure`.
- CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL equals CLAUDE_CODE_SUBAGENT_MODEL in `env`.

Each command string runs through `sh -c` (Git Bash on Windows). The no-python case runs with
PATH set to one empty folder. The gate commands use only shell builtins, so no python can be found.
The shell is started by absolute path, so it still runs.

Override the settings file with the env var WRAPPERS_SETTINGS_UNDER_TEST (used for the red run on
main: `git show origin/main:settings.json > <scratch>/settings.json`).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS = os.environ.get("WRAPPERS_SETTINGS_UNDER_TEST") or os.path.join(HERE, "..", "settings.json")
SH = shutil.which("sh")

# gate script -> the event whose entry must run it
GATES = {
    "hooks/guard.py": "PreToolUse",
    "hooks/stall_watch.py": "PreToolUse",
    "lint/ste_gate.py": "PreToolUse",
    "hooks/question_outcome.py": "PreToolUse",
    "hooks/sim_boot_record.py": "PreToolUse",
    "hooks/rm_prompt_answer.py": "PermissionRequest",
}
ADVISORY_EVENTS = ("SessionStart", "Stop", "PreCompact", "SessionEnd", "PostToolUse", "SubagentStop")
REMEDY = ("install.sh", "install.ps1")


def load():
    with open(SETTINGS, encoding="utf-8") as f:
        return json.load(f)


def hook_entries(settings):
    """Yield (event, hook) for every hook in settings."""
    for ev, groups in settings["hooks"].items():
        for group in groups:
            for h in group.get("hooks", []):
                yield ev, h


def command_of(h):
    return h.get("command") or ""


def gate_entry(settings, script):
    """The one entry in the gate's event whose command runs the script, or None."""
    needle = "/%s\"" % script  # the commands read "$g" = "${CLAUDE_CONFIG_DIR...}/hooks/guard.py"
    hits = [h for ev, h in hook_entries(settings) if ev == GATES[script] and needle in command_of(h)]
    return hits[0] if len(hits) == 1 else None


def run_sh(cmd, env):
    if SH is None:
        raise RuntimeError("no sh on PATH; these tests need Git Bash on Windows")
    return subprocess.run([SH, "-c", cmd], env=env, capture_output=True, text=True, input="{}", timeout=60)


def remedy_ok(r, reason):
    if r.returncode != 2:
        return False, "exit %d, want 2: %s" % (r.returncode, r.stderr.strip()[:120])
    missing = [n for n in REMEDY if n not in r.stderr]
    if missing or reason not in r.stderr:
        return False, "stderr lacks %s / %r: %s" % (missing, reason, r.stderr.strip()[:120])
    return True, "exit 2, remedy names install.sh and install.ps1"


def case_on_failure(script):
    def check():
        h = gate_entry(load(), script)
        if h is None:
            return False, "no single %s entry for %s" % (GATES[script], script)
        got = h.get("onFailure")
        return got == "block", "onFailure is %r" % got
    return check


def case_missing_script(script):
    def check():
        h = gate_entry(load(), script)
        if h is None:
            return False, "no single entry for %s" % script
        with tempfile.TemporaryDirectory() as cfg:
            r = run_sh(command_of(h), {"CLAUDE_CONFIG_DIR": cfg, "PATH": os.environ.get("PATH", "")})
        return remedy_ok(r, "script missing")
    return check


def case_no_python(script):
    def check():
        h = gate_entry(load(), script)
        if h is None:
            return False, "no single entry for %s" % script
        with tempfile.TemporaryDirectory() as cfg, tempfile.TemporaryDirectory() as empty:
            for s in GATES:  # every gate script exists, so the only failure left is python
                path = os.path.join(cfg, s)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                open(path, "w").close()
            r = run_sh(command_of(h), {"CLAUDE_CONFIG_DIR": cfg, "PATH": empty})
        return remedy_ok(r, "no python")
    return check


def case_advisory_exit0(h):
    def check():
        with tempfile.TemporaryDirectory() as cfg:
            env = dict(os.environ, CLAUDE_CONFIG_DIR=cfg)
            env.pop("CLAUDE_CODE_REMOTE", None)
            r = run_sh(command_of(h), env)
        return r.returncode == 0, "exit %d: %s" % (r.returncode, r.stderr.strip()[:120])
    return check


def check_advisory_no_onfailure():
    bad = [ev for ev, h in hook_entries(load()) if ev in ADVISORY_EVENTS and "onFailure" in h]
    return not bad, "onFailure on advisory events: %s" % bad


def check_env_subagent_model():
    env = load().get("env", {})
    w = env.get("CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL")
    s = env.get("CLAUDE_CODE_SUBAGENT_MODEL")
    return w is not None and w == s, "workflow=%r subagent=%r" % (w, s)


def build_cases():
    settings = load()
    cases = []
    for s in GATES:
        cases.append(("gate %s carries onFailure block" % s, case_on_failure(s)))
    for s in GATES:
        cases.append(("gate %s exits 2 when script missing" % s, case_missing_script(s)))
    for s in GATES:
        cases.append(("gate %s exits 2 when no python" % s, case_no_python(s)))
    for ev, h in hook_entries(settings):
        if ev in ADVISORY_EVENTS and command_of(h):
            cases.append(("advisory %s exits 0 when script missing: %s" % (ev, command_of(h)[:60]),
                          case_advisory_exit0(h)))
    cases.append(("no advisory entry carries onFailure", check_advisory_no_onfailure))
    cases.append(("CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL equals CLAUDE_CODE_SUBAGENT_MODEL",
                  check_env_subagent_model))
    return cases


def main():
    cases = build_cases()
    failed = 0
    for name, fn in cases:
        try:
            ok, note = fn()
        except Exception as e:  # a crash is a failed case, not a crash of the run
            ok, note = False, "raised %s: %s" % (type(e).__name__, e)
        failed += 0 if ok else 1
        print("%s  %s  %s" % ("PASS" if ok else "FAIL", name, "" if ok else "(%s)" % note))
    print()
    if failed:
        print("test_wrappers FAIL: %d of %d cases wrong" % (failed, len(cases)))
        return 1
    print("test_wrappers PASS: %d of %d cases right" % (len(cases), len(cases)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
