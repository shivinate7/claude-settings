#!/usr/bin/env python3
"""Cases for hooks/shared_names.py, the one home of the names the guard and the config watch share.
Standard library only, and no test runner.

Run it from the repository root:

    python hooks/test_shared_names.py

WHAT IT PROVES. `shared_names` holds the watched settings file names (`PROJECT_FROZEN_FILES`, with the
leading slash the guard matches on) and `config_dir`. It imports only the standard library, so the
config watch's fast exit can read it before the guard loads. The guard's modules re-export those
very objects, and `config_watch.py` holds no literal copy of a watched name.

It also holds `MACHINE_TAGS`, the tags that mark a prompt as a notice. `local_time.py` reads it
from here, so its UserPromptSubmit path loads no guard module. No other file holds a literal copy.
"""

import ast
import contextlib
import glob
import importlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.append(os.path.join(HERE, "..", "lint"))  # append: no lint module shadows a hook this suite imports
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
RUN_FOLDER = _test_temp.run_folder()

# Today's values, pinned from hooks/guard_frozen.py and hooks/guard_core.py.
FROZEN_FILES = ("/.claude/settings.json", "/.claude/settings.local.json")
WATCHED = tuple(name.lstrip("/") for name in FROZEN_FILES)
MACHINE_TAGS = ("<system-reminder>", "<task-notification>")  # pinned; shared_names.py holds the one copy
CLOCK = "2026-07-04T10:30:00-05:00"
TIME_LINE = "Local time: 2026-07-04 10:30 CDT (UTC-05:00)\n"
# What local_time may load beyond the standard library: itself, shared_names, and the light
# siblings it already loaded before this lane (stdlib only at import: precompact_handoff,
# override, _nowindow).
LIGHT = {"local_time", "shared_names", "precompact_handoff", "override", "_nowindow"}
PROBE = r"""
import json, runpy, sys
before = set(sys.modules)
try:
    runpy.run_path(sys.argv[1], run_name="__main__")
except SystemExit:
    pass
print(json.dumps(sorted(m for m in set(sys.modules) - before
                        if m.split(".")[0] not in sys.stdlib_module_names)))
"""


def _shared():
    return importlib.import_module("shared_names")


def case_module_exists():
    path = os.path.join(HERE, "shared_names.py")
    return os.path.isfile(path), "hooks/shared_names.py is %s" % (
        "present" if os.path.isfile(path) else "missing")


def case_stdlib_only():
    path = os.path.join(HERE, "shared_names.py")
    if not os.path.isfile(path):
        return False, "hooks/shared_names.py is missing"
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            # A relative import is a sibling hook module, never the standard library.
            roots.add("." if node.level else (node.module or "").split(".")[0])
    foreign = sorted(root for root in roots if root not in sys.stdlib_module_names)
    return not foreign, "non-stdlib imports: %s" % (foreign or "none")


def case_values_pinned():
    shared = _shared()
    got = getattr(shared, "PROJECT_FROZEN_FILES", None)
    ok = got == FROZEN_FILES and callable(getattr(shared, "config_dir", None))
    return ok, "PROJECT_FROZEN_FILES=%r config_dir callable=%s" % (
        got, callable(getattr(shared, "config_dir", None)))


def case_config_dir_answers_as_guard():
    shared = _shared()
    saved = os.environ.get("CLAUDE_CONFIG_DIR")
    try:
        os.environ["CLAUDE_CONFIG_DIR"] = os.path.join(HERE, "cfg-probe")
        set_ok = shared.config_dir() == os.path.join(HERE, "cfg-probe")
        os.environ.pop("CLAUDE_CONFIG_DIR")
        unset = shared.config_dir()
    finally:
        if saved is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = saved
    expect = os.path.join(os.path.expanduser("~"), ".claude")
    return set_ok and unset == expect, "env set ok=%s, unset=%r" % (set_ok, unset)


def case_guard_reexports_same_objects():
    shared = _shared()
    frozen = importlib.import_module("guard_frozen")
    core = importlib.import_module("guard_core")
    guard = importlib.import_module("guard")
    same = (frozen.PROJECT_FROZEN_FILES is shared.PROJECT_FROZEN_FILES
            and core.config_dir is shared.config_dir
            and guard.PROJECT_FROZEN_FILES is shared.PROJECT_FROZEN_FILES)
    return same, ("guard_frozen names is shared=%s, guard_core.config_dir is shared=%s, "
                  "guard names is shared=%s") % (
        frozen.PROJECT_FROZEN_FILES is shared.PROJECT_FROZEN_FILES,
        core.config_dir is shared.config_dir,
        guard.PROJECT_FROZEN_FILES is shared.PROJECT_FROZEN_FILES)


def case_config_watch_has_no_literal_copy():
    with open(os.path.join(HERE, "config_watch.py"), encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    banned = set(WATCHED) | set(FROZEN_FILES)
    found = sorted({node.value for node in ast.walk(tree)
                    if isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and node.value in banned})
    return not found, "literal copies in config_watch.py: %s" % (found or "none")


def case_guard_modules_hold_no_literal_copy():
    """guard_frozen.py and guard_core.py import the names with no fallback. The install lands
    shared_names.py inside the guard set, so no `except ImportError` copy is needed."""
    banned = set(WATCHED) | set(FROZEN_FILES)
    found = []
    for module in ("guard_frozen.py", "guard_core.py"):
        with open(os.path.join(HERE, module), encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value in banned:
                found.append("%s:%d string %r" % (module, node.lineno, node.value))
            elif isinstance(node, ast.FunctionDef) and node.name == "config_dir":
                found.append("%s:%d def config_dir" % (module, node.lineno))
    return not found, "literal copies in the guard modules: %s" % (found or "none")


def _run_local_time(cfg, prompt, session="s1", probe=False):
    env = dict(os.environ, CLAUDE_CONFIG_DIR=cfg, LOCAL_TIME_NOW=CLOCK)
    argv = [sys.executable, "-c", PROBE, os.path.join(HERE, "local_time.py")] if probe else [
        sys.executable, os.path.join(HERE, "local_time.py")]
    return subprocess.run(argv, input=json.dumps({"session_id": session, "prompt": prompt}),
                          capture_output=True, text=True, env=env)


def case_machine_tags_pinned_and_shared():
    shared = _shared()
    got = getattr(shared, "MACHINE_TAGS", None)
    if got != MACHINE_TAGS:
        return False, "shared_names.MACHINE_TAGS=%r" % (got,)
    local_time = importlib.import_module("local_time")
    wrong = ["local_time"] if hasattr(local_time, "MACHINE_TAGS") and local_time.MACHINE_TAGS is not got else []
    return not wrong, "importers holding another object: %s" % (wrong or "none")


def case_no_literal_machine_tags_elsewhere():
    found = []
    for folder in ("hooks", "lint", "janitor"):
        for path in glob.glob(os.path.join(HERE, "..", folder, "*.py")):
            name = os.path.basename(path)
            if name.startswith("test_") or name == "shared_names.py":
                continue
            with open(path, encoding="utf-8") as handle:
                tree = ast.parse(handle.read())
            # Any string literal equal to a tag is a copy, whether alone or in a collection.
            # A tag without its angle brackets, as str or bytes (a pre-filter), is a copy too.
            bare = {t.strip("<>") for t in MACHINE_TAGS}
            found += ["%s/%s:%d" % (folder, name, n.lineno) for n in ast.walk(tree)
                      if isinstance(n, ast.Constant) and isinstance(n.value, (str, bytes))
                      and (n.value.decode("utf-8", "replace") if isinstance(n.value, bytes)
                           else n.value) in set(MACHINE_TAGS) | bare]
    return not found, "literal copies of a machine tag: %s" % (found or "none")


def case_local_time_loads_no_guard_module():
    with tempfile.TemporaryDirectory() as cfg:
        extra = {}
        for label, prompt in (("plain", "hello"), ("fb", "fb note"), ("override", "override"),
                              ("tagged", "<system-reminder>fb x")):
            done = _run_local_time(cfg, prompt, probe=True)
            try:
                extra[label] = sorted(set(json.loads(done.stdout.splitlines()[-1])) - LIGHT)
            except (ValueError, IndexError):
                extra[label] = ["(probe failed: rc=%s %s)" % (done.returncode, done.stderr[:80])]
    bad = {k: v for k, v in extra.items() if v}
    return not bad, "modules beyond local_time and its light siblings: %s" % (bad or "none")


def case_local_time_output_unchanged():
    """Pinned local_time output for a tagged, a plain, an fb and an override prompt. Tagged prompts save nothing."""
    with tempfile.TemporaryDirectory() as cfg:
        outs = [_run_local_time(cfg, p, s).stdout for p, s in (
            ("<system-reminder>fb x", "s1"), ("<task-notification>fb y", "s1"),
            ("hello", "s4"), ("fb real note", "s2"))]
        inbox = os.path.join(cfg, "handoffs", "s2.inbox.md")
        saved = open(inbox, encoding="utf-8").read() if os.path.isfile(inbox) else None
        s1 = os.path.exists(os.path.join(cfg, "handoffs", "s1.inbox.md"))
        override = _run_local_time(cfg, "override", "s3").stdout
    want_inbox = "### 2026-07-04 10:30 CDT (UTC-05:00)\n```\nfb real note\n```\n"
    want_override = TIME_LINE + ("Override: the next refused act goes through, once. "
                                 "It ends at 10:40 CDT if unused.\n")
    ok = (outs == [TIME_LINE] * 4 and saved == want_inbox and not s1 and override == want_override)
    return ok, "stdouts ok=%s, s2 inbox ok=%s, tagged prompts saved nothing=%s, override ok=%s" % (
        outs == [TIME_LINE] * 4, saved == want_inbox, not s1, override == want_override)


def case_local_time_fails_open_on_bad_shared_names():
    """A missing or stale shared_names.py (no MACHINE_TAGS) must not stop the time line or an
    override grant: the install can land local_time.py before its sibling."""
    bad = []
    for label in ("absent", "stale"):
        with tempfile.TemporaryDirectory() as scratch:
            hooks = os.path.join(scratch, "hooks")
            shutil.copytree(HERE, hooks, ignore=shutil.ignore_patterns("__pycache__"))
            target = os.path.join(hooks, "shared_names.py")
            if label == "absent":
                os.remove(target)
            else:
                with open(target, "w", encoding="utf-8") as handle:
                    handle.write("PROJECT_FROZEN_FILES = ()\n")
            cfg = os.path.join(scratch, "cfg")
            os.mkdir(cfg)
            env = dict(os.environ, CLAUDE_CONFIG_DIR=cfg, LOCAL_TIME_NOW=CLOCK)
            done = subprocess.run([sys.executable, os.path.join(hooks, "local_time.py")],
                                  input=json.dumps({"session_id": "s1", "prompt": "override"}),
                                  capture_output=True, text=True, env=env)
            if not (done.returncode == 0 and done.stdout.startswith(TIME_LINE)
                    and "Override:" in done.stdout):
                bad.append("%s: rc=%s stdout=%r" % (label, done.returncode, done.stdout[:60]))
    return not bad, "bad states: %s" % (bad or "none")


# ---- the merge role reader: MERGE_ROLES, role_path and read_merge_role live here, and merge/merge.py imports them.
# The role file is {"session": <CLAUDE_CODE_REMOTE_SESSION_ID>, "role": <tier>}. The id has the cse_ prefix a live
# coordinator's environment holds; the reader never reads a hook payload's session_id.
ROLE_SESSION = "cse_013NEJL2pASwRjgJDnsvnpNe"
ROLE_NAMES = ("MERGE_ROLES", "role_path", "read_merge_role")
MERGE_PY = os.path.join(os.path.dirname(HERE), "merge", "merge.py")


@contextlib.contextmanager
def role_env(config=None, session=ROLE_SESSION):
    """CLAUDE_CONFIG_DIR and CLAUDE_CODE_REMOTE_SESSION_ID set (None drops one) for the block, then put back."""
    wanted = {"CLAUDE_CONFIG_DIR": config, "CLAUDE_CODE_REMOTE_SESSION_ID": session}
    saved = {name: os.environ.get(name) for name in wanted}
    try:
        for name, value in wanted.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def put_role_file(config, text):
    os.makedirs(os.path.join(config, "state"), exist_ok=True)
    with open(os.path.join(config, "state", "merge-role.json"), "w", encoding="utf-8") as handle:
        handle.write(text)


def case_merge_role_names_live_in_shared_names():
    shared = _shared()
    roles = getattr(shared, "MERGE_ROLES", None)
    missing = [name for name in ROLE_NAMES if not hasattr(shared, name)]
    ok = not missing and set(roles) == {"coordinator", "batch-runner"} and all(
        callable(getattr(shared, name)) for name in ROLE_NAMES[1:])
    return ok, "missing from shared_names: %s, MERGE_ROLES=%r" % (missing or "none", roles)


def case_role_path_is_the_state_file_under_the_config_dir():
    shared = _shared()
    config = os.path.join(RUN_FOLDER, "role-path")
    home = os.path.join(os.path.expanduser("~"), ".claude")
    bad = []
    for set_to, folder in ((config, config), (None, home), ("", home)):
        with role_env(set_to):
            got = os.path.normpath(os.fspath(shared.role_path()))
        want = os.path.normpath(os.path.join(folder, "state", "merge-role.json"))
        if got != want:
            bad.append("CLAUDE_CONFIG_DIR=%r gave %r, want %r" % (set_to, got, want))
    return not bad, "wrong paths: %s" % (bad or "none")


def case_read_merge_role_matches_the_env_session_only():
    shared = _shared()
    config = os.path.join(RUN_FOLDER, "read-role")
    bad = []

    def read(text, session=ROLE_SESSION):
        put_role_file(config, text)
        with role_env(config, session):
            return shared.read_merge_role()

    for role in ("coordinator", "batch-runner"):
        got = read(json.dumps({"session": ROLE_SESSION, "role": role}))
        if got != role:
            bad.append("%s read as %r" % (role, got))
    for role in ("lane", "triage", "Coordinator", "coordinator ", "", None, ["coordinator"]):
        got = read(json.dumps({"session": ROLE_SESSION, "role": role}))
        if got is not None:
            bad.append("role %r read as %r, want None" % (role, got))
    # The file's session must equal the environment's id as written: no mapping of cse_<id> to session_<id>.
    for recorded in ("cse_01OtherSession", "session_013NEJL2pASwRjgJDnsvnpNe", ""):
        got = read(json.dumps({"session": recorded, "role": "coordinator"}))
        if got is not None:
            bad.append("a file for session %r read as %r, want None" % (recorded, got))
    for text in ("", '{"session": ', "[]", "null"):
        got = read(text)
        if got is not None:
            bad.append("file text %r read as %r, want None" % (text, got))
    for session in (None, ""):
        got = read(json.dumps({"session": session or "", "role": "coordinator"}), session)
        if got is not None:
            bad.append("env session %r read as %r, want None" % (session, got))
    shutil.rmtree(os.path.join(config, "state"))
    with role_env(config):
        if shared.read_merge_role() is not None:
            bad.append("no file read as a role")
    return not bad, "wrong reads: %s" % (bad or "none")


def case_merge_uses_the_shared_objects():
    """merge/merge.py holds the very objects shared_names holds, and defines none of the three itself."""
    shared = _shared()
    spec = importlib.util.spec_from_file_location("merge_for_shared_names", MERGE_PY)
    merge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(merge)
    different = [name for name in ROLE_NAMES
                 if getattr(shared, name, None) is None or getattr(merge, name, None) is not getattr(shared, name)]
    return not different, "merge.py names that are not shared_names' objects: %s" % (different or "none")


def case_no_second_home_for_the_merge_role_reader():
    """No module outside shared_names.py (merge.py, the guard modules, any other hook) defines the three names."""
    paths = [MERGE_PY] + [os.path.join(HERE, name) for name in sorted(os.listdir(HERE))
                          if name.endswith(".py") and name not in ("shared_names.py",)
                          and not name.startswith(("test_", "mutate_"))]
    found = []
    for path in paths:
        with open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in ROLE_NAMES:
                found.append("%s: def %s" % (os.path.basename(path), node.name))
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ROLE_NAMES for t in node.targets):
                found.append("%s: MERGE_ROLES = ..." % os.path.basename(path))
    return not found, "second definitions: %s" % (found or "none")


def case_the_run_folder_sweep_removes_an_old_sibling_and_keeps_a_new_one():
    """test-temp-standard: the first request of a run removes sibling run folders older than a day, and keeps newer ones."""
    root = os.path.join(RUN_FOLDER, "sweep")
    own, old, new = (os.path.join(root, "%d-%s" % (pid, uuid.uuid4().hex)) for pid in (1, 2, 3))
    for folder in (own, old, new):
        os.makedirs(folder)
    stale = time.time() - 2 * 24 * 60 * 60
    os.utime(old, (stale, stale))
    _test_temp.sweep(root, own)
    left = [os.path.isdir(folder) for folder in (own, old, new)]
    return left == [True, False, True], "own, old, new kept: %s, want [True, False, True]" % left


CASES = [
    ("(a) shared_names.py exists", case_module_exists),
    ("(a) shared_names.py imports only the standard library", case_stdlib_only),
    ("(b) shared_names holds today's watched names and config_dir", case_values_pinned),
    ("(b) shared_names.config_dir answers as the guard's does", case_config_dir_answers_as_guard),
    ("(c) the guard's names are shared_names' own objects", case_guard_reexports_same_objects),
    ("(d) config_watch.py holds no literal watched name", case_config_watch_has_no_literal_copy),
    ("(e) guard_frozen.py and guard_core.py hold no literal copy of a watched name or config_dir",
     case_guard_modules_hold_no_literal_copy),
    ("(f) shared_names holds MACHINE_TAGS, and every importer uses that object",
     case_machine_tags_pinned_and_shared),
    ("(g) no product file outside shared_names holds a string equal to a machine tag",
     case_no_literal_machine_tags_elsewhere),
    ("(h) local_time's prompt path loads no guard-family module",
     case_local_time_loads_no_guard_module),
    ("(i) local_time's output is unchanged for a fixed clock and tag",
     case_local_time_output_unchanged),
    ("(j) local_time keeps the time line and an override grant when shared_names.py is absent or stale",
     case_local_time_fails_open_on_bad_shared_names),
    ("(k) shared_names holds MERGE_ROLES, role_path and read_merge_role", case_merge_role_names_live_in_shared_names),
    ("(l) role_path is the state file under the config dir, or under ~/.claude",
     case_role_path_is_the_state_file_under_the_config_dir),
    ("(m) read_merge_role gives the role for the env's own cse_ session id and None for every other state",
     case_read_merge_role_matches_the_env_session_only),
    ("(n) merge.py's three names are shared_names' own objects", case_merge_uses_the_shared_objects),
    ("(o) no module outside shared_names.py defines the three names", case_no_second_home_for_the_merge_role_reader),
    ("(p) the run folder sweep removes an old sibling and keeps a new one",
     case_the_run_folder_sweep_removes_an_old_sibling_and_keeps_a_new_one),
]


def main() -> int:
    print("shared_names cases, %d in all" % len(CASES))
    failed = 0
    for name, run in CASES:
        try:
            ok, note = run()
        except Exception as error:
            ok, note = False, "case raised %s: %s" % (type(error).__name__, error)
        failed += 0 if ok else 1
        print("%s  %s  (%s)" % ("PASS" if ok else "FAIL", name, note))
    print()
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder
    if failed:
        print("test_shared_names FAIL: %d of %d cases wrong" % (failed, len(CASES)))
        return 1
    print("test_shared_names PASS: %d of %d cases right" % (len(CASES), len(CASES)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
