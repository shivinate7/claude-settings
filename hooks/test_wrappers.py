#!/usr/bin/env python3
"""Cases for the hook command wrappers in settings.json. Standard library only.

Run it from the repository root:

    python hooks/test_wrappers.py

Contract, from decision guard-hooks-fail-closed:
- The two guard entries (PreToolUse guard; PermissionRequest rm_prompt_answer) carry no `onFailure`:
  a timeout under load must not refuse every call.
- A guard whose script is missing exits 2 and prints a remedy line naming install.sh and install.ps1.
- A guard whose script exists but has no python on PATH exits 2. Its remedy line names "Python"
  and both installers, so the reader installs Python 3 before running either one.
- A guard whose script exists runs it: stdin reaches the script, its stdout comes back, and its
  exit code is the script's own. Checked for exit 0 and exit 3.
- stall_watch and sim_boot_record are advisory: every entry that runs them carries no `onFailure`
  and exits 0 when the script is missing.
- Advisory entries (SessionStart, Stop, PreCompact, SessionEnd, PostToolUse, SubagentStop) exit 0
  when their script is missing, and carry no `onFailure`.
- CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL equals CLAUDE_CODE_SUBAGENT_MODEL in `env`.
- From decision agent-model-cap, `env` holds CLAUDE_CODE_SUBAGENT_MODEL = "sonnet" and
  CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH = "1", both as strings.
- Python launcher: every command hook that runs a script through a `g="..."` assignment never
  execs a python candidate whose `command -v` path contains `/WindowsApps/`. The Microsoft Store
  alias there hangs the guard for 30 s. A stub alias ahead of a real python must be
  skipped, so every wrapper runs the real one. With only the alias on PATH, a guard exits 2 with
  the no-python remedy and an advisory hook exits 0.
- The guard split: a copied guard.py takes split_segments from its
  own guard_core.py sibling, never the real one. With the sibling missing, a Bash call is refused with
  the reinstall step named (decision guard-hooks-fail-closed), and one fallback line naming
  guard_core goes to guard.log. Every name other
  files reach through `guard` still resolves.
- The install stamp (decision install-hooks-whole): guard.py and each guard_*.py in hooks/ hold exactly one
  line equal to the placeholder that install.sh and install.ps1 stamp. A line that drifted would install
  unstamped, and the guard would then deny every call.
- The SessionStart clone refresh runs merge/install_from_main.sh. That helper runs install.sh in the pin on
  Linux and Darwin, and install.ps1 under a MINGW, MSYS or CYGWIN uname, so install.sh never runs there.

Each command string runs through `sh -c` (Git Bash on Windows). The no-python case runs with
PATH set to one empty folder. The guard commands use only shell builtins, so no python can be found.
The shell is started by absolute path, so it still runs.

Override the settings file with the env var WRAPPERS_SETTINGS_UNDER_TEST, and the refresh helper with
REFRESH_HELPER_UNDER_TEST.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

from mutate_shared import guard_tree  # run as a script, so hooks/ is on sys.path

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS = os.environ.get("WRAPPERS_SETTINGS_UNDER_TEST") or os.path.join(HERE, "..", "settings.json")
HELPER = os.environ.get("REFRESH_HELPER_UNDER_TEST") or os.path.join(HERE, "..", "merge", "install_from_main.sh")
SH = shutil.which("sh")

# guard script -> the event whose entry must run it
GUARDS = {
    "hooks/guard.py": "PreToolUse",
    "hooks/rm_prompt_answer.py": "PermissionRequest",
}
# scripts in the advisory class: they never deny
MOVED = ("hooks/stall_watch.py", "hooks/sim_boot_record.py")
ADVISORY_EVENTS = ("SessionStart", "Stop", "PreCompact", "SessionEnd", "PostToolUse", "SubagentStop")
REMEDY = ("install.sh", "install.ps1")
PAYLOAD = '{"probe": "d1-7f3a"}'
# a stand-in guard: echoes its stdin with a marker, then exits with the code the case picks
FAKE_GUARD = "import sys\nprint('stdin=' + sys.stdin.read())\nsys.exit(%d)\n"


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


def guard_entry(settings, script):
    """The one entry in the guard's event whose command runs the script, or None."""
    needle = "/%s\"" % script  # the commands read "$g" = "${CLAUDE_CONFIG_DIR...}/hooks/guard.py"
    hits = [h for ev, h in hook_entries(settings) if ev == GUARDS[script] and needle in command_of(h)]
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
        h = guard_entry(load(), script)
        if h is None:
            return False, "no single %s entry for %s" % (GUARDS[script], script)
        got = h.get("onFailure")
        return got is None, "onFailure is %r" % got
    return check


def case_missing_script(script):
    def check():
        h = guard_entry(load(), script)
        if h is None:
            return False, "no single entry for %s" % script
        with tempfile.TemporaryDirectory() as cfg:
            r = run_sh(command_of(h), {"CLAUDE_CONFIG_DIR": cfg, "PATH": os.environ.get("PATH", "")})
        return remedy_ok(r, "script missing")
    return check


def case_no_python(script):
    def check():
        h = guard_entry(load(), script)
        if h is None:
            return False, "no single entry for %s" % script
        with tempfile.TemporaryDirectory() as cfg, tempfile.TemporaryDirectory() as empty:
            for s in GUARDS:  # every guard script exists, so the only failure left is python
                path = os.path.join(cfg, s)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                open(path, "w").close()
            r = run_sh(command_of(h), {"CLAUDE_CONFIG_DIR": cfg, "PATH": empty})
        return remedy_ok(r, "Python")
    return check


def case_exec_runs_script(script, code):
    def check():
        h = guard_entry(load(), script)
        if h is None:
            return False, "no single %s entry for %s" % (GUARDS[script], script)
        with tempfile.TemporaryDirectory() as cfg:
            path = os.path.join(cfg, script)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(FAKE_GUARD % code)
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


def check_env_agent_model():
    env = load().get("env", {})
    w = env.get("CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL")
    s = env.get("CLAUDE_CODE_SUBAGENT_MODEL")
    return w is not None and w == s, "workflow=%r agent=%r" % (w, s)


def check_env_equals(key, want):
    """`env[key]` is the string `want`: env values are strings, so a bare number or a missing key fails."""
    def check():
        got = load().get("env", {}).get(key)
        return got == want, "%s=%r, want %r" % (key, got, want)
    return check


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


# Git for Windows' bin/sh.exe puts /usr/bin (the real uname) ahead of PATH. A row that calls uname would
# then see MINGW whatever stub is on PATH. This prefix sets PATH again, in POSIX form, before the row runs.
PATH_FIRST = 'if command -v cygpath >/dev/null 2>&1; then PATH=$(cygpath -up "$STUB_PATH"); export PATH; fi; '


def run_launcher(h, script, path_value):
    """Run one wrapper with the script present, so the python loop is reached. Rows that exit before
    python where their hook does nothing (xcrun missing, MINGW uname) get stubs that make it work."""
    with tempfile.TemporaryDirectory() as cfg:
        write_file(os.path.join(cfg, script))
        tools = os.path.join(cfg, "tools")
        for name, body in (("xcrun", "exit 0"), ("uname", "echo Linux")):
            write_file(os.path.join(tools, name), "#!/bin/sh\n%s\n" % body)
            os.chmod(os.path.join(tools, name), 0o755)
        path = os.pathsep.join([path_value, tools])
        return run_sh(PATH_FIRST + command_of(h), {"CLAUDE_CONFIG_DIR": cfg, "PATH": path, "STUB_PATH": path}, PAYLOAD)


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
    missing = sorted(set(GUARDS) - scripts)
    return not missing and len(scripts) > 0, "wrapper scripts found: %d; guards missing: %s" % (len(scripts), missing)


def check_alias_only_guards():
    guards = [(i, s, h) for i, s, h in launcher_wrappers() if "exit 2" in command_of(h)]
    bad = []
    for i, s, h in guards:
        with tempfile.TemporaryDirectory() as stubs:
            alias_dir, _real = make_stubs(stubs)
            r = run_launcher(h, s, alias_dir)
        ok, note = remedy_ok(r, "Python")
        if not ok or "ALIAS" in r.stdout:
            bad.append("%s: %s, stdout %r" % (i, note, r.stdout.strip()[:40]))
    return (not bad and len(guards) == len(GUARDS)), "guards checked %d; wrong: %s" % (len(guards), bad)


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


# Guard split. guard.py stays the entry point; shared code lives in
# guard_core.py beside it. The pins below fail on a guard.py that has no sibling.
GUARD_PY = os.path.join(HERE, "guard.py")
SPLIT_LABEL = "split_segments: a comment starting a word"  # a test_guard.py log check
# Built from parts, so this file cannot trip the guard it tests (as test_guard.py does).
DENIED_COMMAND = "rm -" + "rf /"
SPLIT_MUTANT = (
    "\n# MUTANT: split_segments answers its input whole, which the real one never does.\n"
    "def split_segments(cmd, ends=None):\n"
    "    return [cmd]\n"
)
# Every name a file outside guard.py reaches through `guard`, grepped from hooks/, janitor/ and lint/:
# config_watch, decision_watch, rm_prompt_answer, report_guard,
# check_agent_models, test_precompact_handoff, janitor/*, the sweep mutants, and test_guard.py.
# `re` is listed because config_watch calls guard.re.sub. The four test_guard.py names are
# POWERSHELL_CALL, judge, mask_script and session_is_live.
GUARD_NAMES = (
    "CAP_MAX_CHANGE", "CAP_MAX_PATH", "CAP_MAX_VALUE", "PROJECT_FROZEN_FILES", "SHELL_TOOLS",
    "AGENT_CAP_KEY", "WRITE_TOOLS", "_cap_reading", "_force_utf8_streams", "_resolved",
    "_shell_write_hit", "cap_change", "cap_change_parts", "cap_safe", "config_dir",
    "is_settings_file", "log_path_and_text", "re", "record", "strip_heredoc_bodies",
    "write_content_parts", "CONFIG_FROZEN_DIRS", "is_project_config", "project_config_shell_hit",
    "split_segments", "ASSIGNMENT", "_rm_target_bad", "segment_tokens", "is_frozen", "git_calls",
    "HAIKU_ROLES", "primary_checkout", "worktree_live_session", "is_worktree", "_git",
    "branch_cherry_empty", "branch_is_ancestor", "branch_is_empty", "porcelain", "session_records",
    "worktree_locked", "PROCESS_START_UNREADABLE", "SESSION_LIVE_TOLERANCE_MS", "_process_start_ms",
    "_process_start_ms_windows", "_path_identity", "git_common_dir", "resolve_default_base",
    "worktree_remove_subject", "POWERSHELL_CALL", "judge", "mask_script", "session_is_live",
)


def clean_env(**extra):
    """The environment with the guard-test switches and every GIT_* key removed, then `extra` set. A git hook
    sets GIT_DIR, which would point a fixture's git at the real repo."""
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("GIT_") or key in ("GUARD_UNDER_TEST", "MUTATE_ONLY", "PYTHONPATH"):
            env.pop(key)
    env.update(extra)
    return env


def split_tree(mutant):
    """A scratch folder holding guard.py and its guard_* siblings, the way mutate_guard copies them.
    With `mutant`, the sibling guard_core.py (created if absent) ends in SPLIT_MUTANT, so a load that
    takes split_segments from that sibling shows it. Without it, the sibling is left as it is."""
    tree = tempfile.mkdtemp(prefix="guard-split-")
    guard_tree(tree)
    if mutant:
        with open(os.path.join(tree, "guard_core.py"), "a", encoding="utf-8") as handle:
            handle.write(SPLIT_MUTANT)
    return tree


def drive_test_guard(tree):
    """Run test_guard.py on the guard copy at `tree`, filtered to the split_segments log check."""
    cfg = tempfile.mkdtemp(prefix="guard-split-cfg-")
    try:
        env = clean_env(GUARD_UNDER_TEST=os.path.join(tree, "guard.py"), MUTATE_ONLY=SPLIT_LABEL,
                        CLAUDE_CONFIG_DIR=cfg)
        return subprocess.run([sys.executable, os.path.join(HERE, "test_guard.py")],
                              capture_output=True, text=True, env=env, timeout=900)
    finally:
        shutil.rmtree(cfg, ignore_errors=True)


def split_row(run):
    """The one output row for the split_segments check, or None."""
    rows = [line for line in run.stdout.splitlines() if SPLIT_LABEL in line]
    return rows[0] if rows else None


def split_mutant_case():
    """A copied guard.py loads split_segments from its scratch sibling, not from the real hooks/."""
    tree = split_tree(mutant=True)
    try:
        run = drive_test_guard(tree)
    finally:
        shutil.rmtree(tree, ignore_errors=True)
    row = split_row(run)
    if run.returncode == 1 and row and row.startswith("FAIL"):
        return True, "the mutant sibling's split_segments reached the check: " + row[:100]
    return False, "exit %d, row %r: the copy did not take split_segments from its sibling" % (
        run.returncode, row)


def split_control_case():
    """Control for split_mutant_case: the same copy with its sibling unmutated passes the check."""
    tree = split_tree(mutant=False)
    try:
        run = drive_test_guard(tree)
    finally:
        shutil.rmtree(tree, ignore_errors=True)
    row = split_row(run)
    if run.returncode == 0 and row and row.startswith("PASS"):
        return True, "the unmutated copy passes the check"
    return False, "exit %d, row %r: the unmutated copy does not pass the check" % (
        run.returncode, row)


def missing_sibling_case():
    """Decision guard-hooks-fail-closed: a copied guard.py with
    no guard_core.py beside it refuses the call. Stdout carries a deny whose reason names the
    reinstall step and no file, the exit is 0 as for any other deny, and one fallback line naming
    guard_core goes to guard.log. The payload is a command the guard refuses when it can judge."""
    scratch = tempfile.mkdtemp(prefix="guard-nosib-")
    cfg = os.path.join(scratch, "cfg")
    # guard.py imports git_reads, shared_names and the other folder modules it reaches; guard_core.py
    # is the one module this case leaves out
    siblings = sorted(
        name for name in os.listdir(HERE)
        if name.endswith(".py") and name not in ("guard.py", "guard_core.py", "test_wrappers.py"))
    try:
        shutil.copy(GUARD_PY, os.path.join(scratch, "guard.py"))
        for name in siblings:
            shutil.copy(os.path.join(HERE, name), os.path.join(scratch, name))
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": DENIED_COMMAND},
                              "cwd": scratch})
        run = subprocess.run([sys.executable, os.path.join(scratch, "guard.py")], input=payload,
                             capture_output=True, text=True, env=clean_env(CLAUDE_CONFIG_DIR=cfg),
                             timeout=60)
        log = os.path.join(cfg, "guard.log")
        lines = []
        if os.path.exists(log):
            with open(log, encoding="utf-8") as handle:
                lines = [line for line in handle.read().splitlines() if line.strip()]
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    problems = []
    if run.returncode != 0:
        problems.append("exit %d" % run.returncode)
    decision, reason = "", ""
    try:
        block = json.loads(run.stdout.strip())["hookSpecificOutput"]
        decision, reason = block["permissionDecision"], block["permissionDecisionReason"]
    except Exception:
        pass  # an empty or unreadable stdout leaves decision "", and that is a problem below
    if decision != "deny":
        problems.append("decision %r with guard_core missing, want deny (stdout %r)"
                        % (decision, run.stdout.strip()[:60]))
    if not any(step in reason for step in ("install.sh", "install.ps1")):
        problems.append("the reason names no reinstall step: %r" % reason[:90])
    if "guard_core" in reason:
        problems.append("the reason names guard_core, the missing file")
    if len(lines) != 1:
        problems.append("%d guard.log lines, want 1" % len(lines))
    elif "guard_core" not in lines[0]:
        problems.append("the log line does not name guard_core: %r" % lines[0][-120:])
    if problems:
        return False, "; ".join(problems)
    return True, "refused with exit 0, the reason names the reinstall step, one log line names guard_core"


def guard_names_case():
    """Every name in GUARD_NAMES resolves on `guard` in a fresh process, from GUARD_UNDER_TEST or
    hooks/guard.py. The check reads the attribute, which a module __getattr__ also serves."""
    path = os.environ.get("GUARD_UNDER_TEST") or GUARD_PY
    code = ("import sys\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "import guard\n"
            "print([n for n in sys.argv[2:] if not hasattr(guard, n)])\n")
    run = subprocess.run([sys.executable, "-c", code, os.path.dirname(path)] + list(GUARD_NAMES),
                         capture_output=True, text=True, env=clean_env(), timeout=60)
    if run.returncode != 0:
        return False, "import guard failed: %s" % run.stderr.strip()[-160:]
    if run.stdout.strip() != "[]":
        return False, "names that do not resolve on guard: %s" % run.stdout.strip()
    return True, "all %d names resolve on guard" % len(GUARD_NAMES)


def guard_sentinel_case():
    """A name no guard module defines must raise AttributeError through `guard`. A catch-all
    module __getattr__ would answer it and still pass guard_names_case, so this pins the other side."""
    path = os.environ.get("GUARD_UNDER_TEST") or GUARD_PY
    code = ("import sys\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "import guard\n"
            "try:\n"
            "    getattr(guard, 'no_such_guard_name')\n"
            "except AttributeError:\n"
            "    print('raised')\n"
            "else:\n"
            "    print('resolved')\n")
    run = subprocess.run([sys.executable, "-c", code, os.path.dirname(path)],
                         capture_output=True, text=True, env=clean_env(), timeout=60)
    if run.returncode != 0:
        return False, "import guard failed: %s" % run.stderr.strip()[-160:]
    if run.stdout.strip() != "raised":
        return False, "the sentinel name resolved on guard: a catch-all __getattr__?"
    return True, "the sentinel name raises AttributeError"


def stamp_lines_case():
    """The stampers (install.sh, install.ps1) swap one whole placeholder line in guard.py and each guard_*.py for the
    install id. A file whose line drifts installs unstamped: the installer exits 0 and the guard then denies every call.
    The placeholder is read from install.sh and install.ps1, never copied here. Each hooks/guard*.py holds exactly one."""
    root = os.path.dirname(HERE)
    found = {}
    for name, pattern in (("install.sh", r"^STAMP_PLACEHOLDER='([^'\n]*)'\r?$"),
                          ("install.ps1", r"^\$StampPlaceholder = '([^'\n]*)'\r?$")):
        with open(os.path.join(root, name), encoding="utf-8") as f:
            m = re.search(pattern, f.read(), re.M)
        if not m or not m.group(1):
            return False, "%s names no placeholder text" % name
        found[name] = m.group(1)
    if len(set(found.values())) != 1:
        return False, "the stampers disagree: %r" % found
    want = found["install.sh"]
    files = sorted(n for n in os.listdir(HERE) if re.fullmatch(r"guard(_\w+)?\.py", n))
    if "guard.py" not in files or "guard_core.py" not in files:
        return False, "the guard files were not found in %s" % HERE
    bad = []
    for name in files:
        with open(os.path.join(HERE, name), encoding="utf-8", newline="") as f:
            hits = sum(1 for line in f.read().split("\n") if line.rstrip("\r") == want)
        if hits != 1:
            bad.append("%s has %d placeholder lines" % (name, hits))
    if bad:
        return False, "%s; want exactly one line equal to %r" % ("; ".join(bad), want)
    return True, "%d guard files each hold one placeholder line" % len(files)


WINDOWS_UNAMES = ("MINGW64_NT-10.0-26200", "MSYS_NT-10.0-26200", "CYGWIN_NT-10.0-26200")
OTHER_UNAMES = ("Linux", "Darwin")


def wiring_case():
    """The clone refresh runs the helper. No SessionStart entry runs install.sh itself."""
    cmds = [command_of(h) for ev, h in hook_entries(load()) if ev == "SessionStart"]
    direct = [c for c in cmds if "install.sh" in c]
    runs = [c for c in cmds if "install_from_main.sh" in c]
    if direct:
        return False, "%d SessionStart entries name install.sh" % len(direct)
    if len(runs) != 1:
        return False, "%d SessionStart entries name install_from_main.sh, want 1" % len(runs)
    return True, "one SessionStart entry runs install_from_main.sh"


def refresh_case(uname_value, runs):
    """The helper runs install.sh in the pin on Linux and Darwin. Under MINGW, MSYS or CYGWIN it runs install.ps1,
    and install.sh must not run there: it takes 80 to 90 s at each start. The helper runs in a throwaway clone on
    main, with stub uname, powershell.exe and cygpath. The clone's install.sh writes a marker file next to itself,
    so the marker shows that install.sh ran in the pin."""
    def check():
        with tempfile.TemporaryDirectory() as root:
            clone, cfg, tools = (os.path.join(root, n) for n in ("clone", "cfg", "tools"))
            write_file(os.path.join(clone, "install.sh"), 'printf ran > "$(dirname "$0")/ran-sh.txt"\n')
            write_file(os.path.join(clone, "install.ps1"), "")
            for a in (("init", "-q", "-b", "main"), ("add", "."),
                      ("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "c")):
                subprocess.run(["git", "-C", clone, *a], capture_output=True, text=True, check=True, env=clean_env())
            for name, body in (("uname", "echo %s" % uname_value), ("powershell.exe", "exit 0"),
                               ("cygpath", 'echo "$2"')):
                if name == "cygpath" and shutil.which("cygpath"):
                    continue
                write_file(os.path.join(tools, name), "#!/bin/sh\n%s\n" % body)
                os.chmod(os.path.join(tools, name), 0o755)
            # Git's bash sits after the stubs, so the helper's own bash call never finds the WSL stub first.
            path = os.pathsep.join([tools, os.path.dirname(SH or ""), os.environ.get("PATH", "")])
            r = run_sh(PATH_FIRST + 'cd "$CLONE" && bash "$HELPER"',
                       clean_env(CLAUDE_CONFIG_DIR=cfg, HOME=root, PATH=path, STUB_PATH=path,
                                 CLONE=clone.replace("\\", "/"),
                                 HELPER=os.path.abspath(HELPER).replace("\\", "/")))
            ran = os.path.exists(os.path.join(clone + "-live", "ran-sh.txt"))
        note = "exit %d; install.sh ran: %s; stderr %s" % (r.returncode, ran, r.stderr.strip()[:160])
        return r.returncode == 0 and ran == runs, note
    return check


def build_cases():
    settings = load()
    cases = []
    for s in GUARDS:
        cases.append(("guard %s carries no onFailure" % s, case_on_failure(s)))
    for s in GUARDS:
        cases.append(("guard %s exits 2 when script missing" % s, case_missing_script(s)))
    for s in GUARDS:
        cases.append(("guard %s exits 2 when no python" % s, case_no_python(s)))
    for s in GUARDS:
        for code in (0, 3):
            cases.append(("guard %s runs present script, exit %d, stdin and stdout pass" % (s, code),
                          case_exec_runs_script(s, code)))
    for s in MOVED:
        cases.append(("moved %s is advisory: no onFailure, exit 0 when script missing" % s,
                      case_moved_advisory(s)))
    for ev, h in hook_entries(settings):
        if ev in ADVISORY_EVENTS and command_of(h):
            cases.append(("advisory %s exits 0 when script missing: %s" % (ev, command_of(h)[:60]),
                          case_advisory_exit0(h)))
    cases.append(("launcher selection: python wrappers found, includes every GUARD", check_launcher_selection))
    for i, s, h in launcher_wrappers():
        cases.append(("launcher control %s: real python alone runs REAL" % i, case_launcher(h, s, False)))
    for i, s, h in launcher_wrappers():
        cases.append(("launcher %s: WindowsApps python3 skipped, REAL runs" % i, case_launcher(h, s, True)))
    cases.append(("launcher alias-only guards: exit 2 with no-python remedy, no ALIAS", check_alias_only_guards))
    cases.append(("launcher alias-only advisory: exit 0, no ALIAS", check_alias_only_advisory))
    cases.append(("no advisory entry carries onFailure", check_advisory_no_onfailure))
    cases.append(("CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL equals CLAUDE_CODE_SUBAGENT_MODEL",
                  check_env_agent_model))
    cases.append(("CLAUDE_CODE_SUBAGENT_MODEL is \"sonnet\"",
                  check_env_equals("CLAUDE_CODE_SUBAGENT_MODEL", "sonnet")))
    cases.append(("CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH is \"1\"",
                  check_env_equals("CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH", "1")))
    cases.append(("guard split: a copied guard loads split_segments from its sibling, not the real one",
                  split_mutant_case))
    cases.append(("guard split control: the same copy with its sibling unmutated passes the check",
                  split_control_case))
    cases.append(("audit-high fail-closed: a missing guard_core refuses the call and logs one line",
                  missing_sibling_case))
    cases.append(("guard split: every name other files reach through guard still resolves",
                  guard_names_case))
    cases.append(("guard split: a name no guard module defines raises AttributeError through guard",
                  guard_sentinel_case))
    cases.append(("install stamp: each hooks/guard*.py holds exactly one placeholder line, as the stampers write it",
                  stamp_lines_case))
    cases.append(("refresh hook: the SessionStart entry runs install_from_main.sh, not install.sh", wiring_case))
    for u in WINDOWS_UNAMES:
        cases.append(("refresh hook: uname %s does not run install.sh" % u, refresh_case(u, False)))
    for u in OTHER_UNAMES:
        cases.append(("refresh hook: uname %s runs install.sh" % u, refresh_case(u, True)))
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
