#!/usr/bin/env python3
"""Cases for the hook command wrappers in settings.json. Standard library only.

Run it from the repository root:

    python hooks/test_wrappers.py

Contract, from decision gate-hooks-fail-closed:
- The four gate entries (PreToolUse guard, ste_gate, question_outcome; PermissionRequest
  rm_prompt_answer) carry no `onFailure`: a timeout under load must not refuse every call.
- A gate whose script is missing exits 2 and prints a remedy line naming install.sh and install.ps1.
- A gate whose script exists but has no python on PATH exits 2. Its remedy line names "Python"
  and both installers, so the reader installs Python 3 before running either one.
- A gate whose script exists runs it: stdin reaches the script, its stdout comes back, and its
  exit code is the script's own. Checked for exit 0 and exit 3.
- stall_watch and sim_boot_record are advisory: every entry that runs them carries no `onFailure`
  and exits 0 when the script is missing.
- Advisory entries (SessionStart, Stop, PreCompact, SessionEnd, PostToolUse, SubagentStop) exit 0
  when their script is missing, and carry no `onFailure`.
- CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL equals CLAUDE_CODE_SUBAGENT_MODEL in `env`.
- Python launcher: every command hook that runs a script through a `g="..."` assignment never
  execs a python candidate whose `command -v` path contains `/WindowsApps/`. The Microsoft Store
  alias there hung the guard for 30 s (2026-10-12). A stub alias ahead of a real python must be
  skipped, so every wrapper runs the real one. With only the alias on PATH, a gate exits 2 with
  the no-python remedy and an advisory hook exits 0.

Each command string runs through `sh -c` (Git Bash on Windows). The no-python case runs with
PATH set to one empty folder. The gate commands use only shell builtins, so no python can be found.
The shell is started by absolute path, so it still runs.

Override the settings file with the env var WRAPPERS_SETTINGS_UNDER_TEST (used for the red run on
main: `git show origin/main:settings.json > <scratch>/settings.json`).
"""
import json
import os
import re
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
    "lint/ste_gate.py": "PreToolUse",
    "hooks/question_outcome.py": "PreToolUse",
    "hooks/rm_prompt_answer.py": "PermissionRequest",
}
# scripts in the advisory class: they never deny
MOVED = ("hooks/stall_watch.py", "hooks/sim_boot_record.py")
ADVISORY_EVENTS = ("SessionStart", "Stop", "PreCompact", "SessionEnd", "PostToolUse", "SubagentStop")
REMEDY = ("install.sh", "install.ps1")
PAYLOAD = '{"probe": "d1-7f3a"}'
# a stand-in gate: echoes its stdin with a marker, then exits with the code the case picks
FAKE_GATE = "import sys\nprint('stdin=' + sys.stdin.read())\nsys.exit(%d)\n"


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


def entries_running(settings, script):
    """Every hook entry, in any event, whose command runs the script."""
    needle = "/%s\"" % script
    return [h for _ev, h in hook_entries(settings) if needle in command_of(h)]


def run_sh(cmd, env, stdin="{}"):
    if SH is None:
        raise RuntimeError("no sh on PATH; these tests need Git Bash on Windows")
    return subprocess.run([SH, "-c", cmd], env=env, capture_output=True, text=True, input=stdin, timeout=60)


def remedy_ok(r, reason):
    if r.returncode != 2:
        return False, "exit %d, want 2: %s" % (r.returncode, r.stderr.strip()[:120])
    missing = [n for n in REMEDY if n not in r.stderr]
    if missing or reason not in r.stderr:
        return False, "stderr lacks %s / %r: %s" % (missing, reason, r.stderr.strip()[:120])
    return True, "exit 2, remedy names %r and install.sh and install.ps1" % reason


def case_on_failure(script):
    def check():
        h = gate_entry(load(), script)
        if h is None:
            return False, "no single %s entry for %s" % (GATES[script], script)
        got = h.get("onFailure")
        return got is None, "onFailure is %r" % got
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
        return remedy_ok(r, "Python")
    return check


def case_exec_runs_script(script, code):
    def check():
        h = gate_entry(load(), script)
        if h is None:
            return False, "no single %s entry for %s" % (GATES[script], script)
        with tempfile.TemporaryDirectory() as cfg:
            path = os.path.join(cfg, script)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(FAKE_GATE % code)
            # PATH holds only the folder of the interpreter running this suite. The wrapper tries
            # python3 first, and on Windows that name can be an App Execution Alias that hangs on
            # piped stdin. That folder has no python3, so the wrapper falls through to python.
            py_dir = os.path.dirname(os.path.abspath(sys.executable))
            r = run_sh(command_of(h), {"CLAUDE_CONFIG_DIR": cfg, "PATH": py_dir}, PAYLOAD)
        want = "stdin=" + PAYLOAD
        ok = r.returncode == code and r.stdout.strip() == want
        return ok, "exit %d want %d; stdout %r want %r; stderr %s" % (
            r.returncode, code, r.stdout.strip()[:120], want, r.stderr.strip()[:120])
    return check


def case_advisory_exit0(h):
    def check():
        with tempfile.TemporaryDirectory() as cfg:
            env = dict(os.environ, CLAUDE_CONFIG_DIR=cfg)
            env.pop("CLAUDE_CODE_REMOTE", None)
            r = run_sh(command_of(h), env)
        return r.returncode == 0, "exit %d: %s" % (r.returncode, r.stderr.strip()[:120])
    return check


def case_moved_advisory(script):
    def check():
        hits = entries_running(load(), script)
        if not hits:
            return False, "no entry runs %s" % script
        for h in hits:
            if "onFailure" in h:
                return False, "onFailure on an entry that runs %s" % script
            ok, note = case_advisory_exit0(h)()
            if not ok:
                return False, note
        return True, "%d entry/entries: no onFailure, exit 0 when missing" % len(hits)
    return check


def check_advisory_no_onfailure():
    bad = [ev for ev, h in hook_entries(load()) if ev in ADVISORY_EVENTS and "onFailure" in h]
    return not bad, "onFailure on advisory events: %s" % bad


def check_env_subagent_model():
    env = load().get("env", {})
    w = env.get("CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL")
    s = env.get("CLAUDE_CODE_SUBAGENT_MODEL")
    return w is not None and w == s, "workflow=%r subagent=%r" % (w, s)


# a wrapper's script: the `g="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/<script>"` assignment
LAUNCH_RE = re.compile(r'g="\$\{CLAUDE_CONFIG_DIR:-\$HOME/\.claude\}/([^"]+)"')


def launcher_wrappers():
    """Every command hook that runs a python script, as (id, script, hook)."""
    out = []
    for n, (ev, h) in enumerate(hook_entries(load())):
        m = LAUNCH_RE.search(command_of(h))
        if m:
            out.append(("%s#%d %s" % (ev, n, m.group(1)), m.group(1), h))
    return out


def write_file(path, body=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:  # LF: the shebang must not get a CR
        f.write(body)


def make_stubs(root):
    """A fake WindowsApps alias that prints ALIAS and exits 9, and a fake real python that prints REAL."""
    alias_dir = os.path.join(root, "WindowsApps")
    real_dir = os.path.join(root, "real")
    for d, name, body in ((alias_dir, "python3", "echo ALIAS\nexit 9"), (real_dir, "python", "echo REAL")):
        path = os.path.join(d, name)
        write_file(path, "#!/bin/sh\n%s\n" % body)
        os.chmod(path, 0o755)
    return alias_dir, real_dir


def run_launcher(h, script, path_value):
    """Run one wrapper with the script present, so the python loop is reached."""
    with tempfile.TemporaryDirectory() as cfg:
        write_file(os.path.join(cfg, script))
        return run_sh(command_of(h), {"CLAUDE_CONFIG_DIR": cfg, "PATH": path_value}, PAYLOAD)


def launcher_real_ok(r):
    ok = r.returncode == 0 and r.stdout.strip() == "REAL"
    return ok, "exit %d; stdout %r; stderr %s" % (r.returncode, r.stdout.strip()[:120], r.stderr.strip()[:120])


def case_launcher(h, script, alias_first):
    def check():
        with tempfile.TemporaryDirectory() as stubs:
            alias_dir, real_dir = make_stubs(stubs)
            path = os.pathsep.join([alias_dir, real_dir]) if alias_first else real_dir
            r = run_launcher(h, script, path)
        return launcher_real_ok(r)
    return check


def check_launcher_selection():
    scripts = {s for _id, s, _h in launcher_wrappers()}
    missing = sorted(set(GATES) - scripts)
    return not missing and len(scripts) > 0, "wrapper scripts found: %d; gates missing: %s" % (len(scripts), missing)


def check_alias_only_gates():
    gates = [(i, s, h) for i, s, h in launcher_wrappers() if "exit 2" in command_of(h)]
    bad = []
    for i, s, h in gates:
        with tempfile.TemporaryDirectory() as stubs:
            alias_dir, _real = make_stubs(stubs)
            r = run_launcher(h, s, alias_dir)
        ok, note = remedy_ok(r, "Python")
        if not ok or "ALIAS" in r.stdout:
            bad.append("%s: %s, stdout %r" % (i, note, r.stdout.strip()[:40]))
    return (not bad and len(gates) == len(GATES)), "gates checked %d; wrong: %s" % (len(gates), bad)


def check_alias_only_advisory():
    adv = [(i, s, h) for i, s, h in launcher_wrappers() if "exit 2" not in command_of(h)]
    bad = []
    for i, s, h in adv:
        with tempfile.TemporaryDirectory() as stubs:
            alias_dir, _real = make_stubs(stubs)
            r = run_launcher(h, s, alias_dir)
        if r.returncode != 0 or "ALIAS" in r.stdout:
            bad.append("%s: exit %d, stdout %r" % (i, r.returncode, r.stdout.strip()[:40]))
    return (not bad and len(adv) > 0), "advisory checked %d; wrong: %s" % (len(adv), bad)


def build_cases():
    settings = load()
    cases = []
    for s in GATES:
        cases.append(("gate %s carries no onFailure" % s, case_on_failure(s)))
    for s in GATES:
        cases.append(("gate %s exits 2 when script missing" % s, case_missing_script(s)))
    for s in GATES:
        cases.append(("gate %s exits 2 when no python" % s, case_no_python(s)))
    for s in GATES:
        for code in (0, 3):
            cases.append(("gate %s runs present script, exit %d, stdin and stdout pass" % (s, code),
                          case_exec_runs_script(s, code)))
    for s in MOVED:
        cases.append(("moved %s is advisory: no onFailure, exit 0 when script missing" % s,
                      case_moved_advisory(s)))
    for ev, h in hook_entries(settings):
        if ev in ADVISORY_EVENTS and command_of(h):
            cases.append(("advisory %s exits 0 when script missing: %s" % (ev, command_of(h)[:60]),
                          case_advisory_exit0(h)))
    cases.append(("launcher selection: python wrappers found, includes every GATE", check_launcher_selection))
    for i, s, h in launcher_wrappers():
        cases.append(("launcher control %s: real python alone runs REAL" % i, case_launcher(h, s, False)))
    for i, s, h in launcher_wrappers():
        cases.append(("launcher %s: WindowsApps python3 skipped, REAL runs" % i, case_launcher(h, s, True)))
    cases.append(("launcher alias-only gates: exit 2 with no-python remedy, no ALIAS", check_alias_only_gates))
    cases.append(("launcher alias-only advisory: exit 0, no ALIAS", check_alias_only_advisory))
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
