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
import glob
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.append(os.path.join(HERE, "..", "lint"))  # appended: a lint module never shadows a hook module
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
RUN = _test_temp.run_folder()  # removed when the suite ends
HOOKS_UNDER_TEST = os.environ.get("HOOKS_UNDER_TEST") or HERE  # a fixture copy of hooks/ may be scanned instead

# Today's values, pinned from hooks/guard_frozen.py and hooks/guard_core.py.
FROZEN_FILES = ("/.claude/settings.json", "/.claude/settings.local.json")
WATCHED = tuple(name.lstrip("/") for name in FROZEN_FILES)
MACHINE_TAGS = (  # pinned; shared_names.py holds the one copy
    "<system-reminder>",
    "<task-notification>",
    "<agent-message>",
    "<agent-message ",
    "<agent-message\t",
    "<agent-message\n",
    "<agent-message\r",
    "Another Claude session sent a message:\n<agent-message>",
    "Another Claude session sent a message:\n<agent-message ",
    "Another Claude session sent a message:\n<agent-message\t",
    "Another Claude session sent a message:\n<agent-message\n",
    "Another Claude session sent a message:\n<agent-message\r",
    "Another Claude session sent a message while you were working:\n<agent-message>",
    "Another Claude session sent a message while you were working:\n<agent-message ",
    "Another Claude session sent a message while you were working:\n<agent-message\t",
    "Another Claude session sent a message while you were working:\n<agent-message\n",
    "Another Claude session sent a message while you were working:\n<agent-message\r",
    "<cross-session-message>",
    "<cross-session-message ",
    "<cross-session-message\t",
    "<cross-session-message\n",
    "<cross-session-message\r",
)
GH_DEFAULT_LOGIN, GH_FALLBACK_LOGIN = "shivinate7", "ssemwal-cdc"  # the default and fallback gh logins (decision `act-in-place`)
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


def _printed_line():
    """The line local_time prints: the time line, then NOW_CENTRAL_POINTER on that same line. The
    constant is read from local_time, never copied (building-allow-list-is-the-constant)."""
    pointer = getattr(importlib.import_module("local_time"), "NOW_CENTRAL_POINTER", None)
    if not isinstance(pointer, str):
        raise AssertionError("local_time has no NOW_CENTRAL_POINTER string, so the printed line is not pinned")
    return TIME_LINE.rstrip("\n") + pointer + "\n"


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


def case_gh_logins_pinned():
    """shivinate7 is the default gh login; ssemwal-cdc is the fallback, for a
    repo shivinate7 cannot reach (decision `act-in-place`). Both names live here, once, for the guard and the reply judge."""
    shared = _shared()
    default = getattr(shared, "GH_DEFAULT_LOGIN", None)
    fallback = getattr(shared, "GH_FALLBACK_LOGIN", None)
    return (default == GH_DEFAULT_LOGIN and fallback == GH_FALLBACK_LOGIN,
            "GH_DEFAULT_LOGIN=%r GH_FALLBACK_LOGIN=%r" % (default, fallback))


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
    printed = _printed_line()
    want_override = printed + ("Override: the next refused act goes through, once. "
                               "It ends at 10:40 CDT if unused.\n")
    ok = (outs == [printed] * 4 and saved == want_inbox and not s1 and override == want_override)
    return ok, "stdouts ok=%s, s2 inbox ok=%s, tagged prompts saved nothing=%s, override ok=%s" % (
        outs == [printed] * 4, saved == want_inbox, not s1, override == want_override)


def case_local_time_fails_open_on_bad_shared_names():
    """A missing or stale shared_names.py (no MACHINE_TAGS) must not stop the time line or an
    override grant: the install can land local_time.py before its sibling."""
    printed = _printed_line()
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
            if not (done.returncode == 0 and done.stdout.startswith(printed)
                    and "Override:" in done.stdout):
                bad.append("%s: rc=%s stdout=%r" % (label, done.returncode, done.stdout[:60]))
    return not bad, "bad states: %s" % (bad or "none")


def case_lane_head_refs_pinned():
    """lane_head_refs(slug) is the one home of the head refs a lane's pull request may carry: the bare step slug and
    `lane/<slug>`. Both forms are real (a pull request on `lane/reviewer-spawn-model` exists). A missing name is a
    failed case, not a crash, so the report names the cause."""
    shared = _shared()
    fn = getattr(shared, "lane_head_refs", None)
    if not callable(fn):
        return False, "shared_names.lane_head_refs is absent"
    got = fn("lane-x")
    return (isinstance(got, (tuple, list)) and tuple(got) == ("lane-x", "lane/lane-x"),
            "lane_head_refs('lane-x')=%r" % (got,))


def case_one_home_for_lane_heads():
    """build.py and the archive guard (hooks/guard_merge.py) import lane_head_refs from shared_names. Neither defines
    its own copy, and neither holds the `lane/` prefix as a literal, so the two forms cannot drift apart."""
    problems = []
    for rel in ("hooks/guard_merge.py", "skills/roadmap/build.py"):
        with open(os.path.join(HERE, "..", rel), encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        imported = any(isinstance(node, ast.ImportFrom) and node.module == "shared_names"
                       and any(alias.name == "lane_head_refs" for alias in node.names)
                       for node in ast.walk(tree))
        copied = [node.lineno for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef) and node.name == "lane_head_refs"]
        literal = [node.lineno for node in ast.walk(tree)
                   if isinstance(node, ast.Constant) and node.value == "lane/"]
        if not imported:
            problems.append("%s does not import lane_head_refs from shared_names" % rel)
        if copied:
            problems.append("%s defines its own lane_head_refs at line %d" % (rel, copied[0]))
        if literal:
            problems.append("%s holds the literal 'lane/' at line %d" % (rel, literal[0]))
    return not problems, "; ".join(problems) or "both read the one home"


def _hooks_without_shared_names(scratch):
    """A copy of hooks/ under `scratch` with shared_names.py removed: the install that lands a hook before its sibling."""
    hooks = os.path.join(scratch, "hooks")
    shutil.copytree(HERE, hooks, ignore=shutil.ignore_patterns("__pycache__"))
    os.remove(os.path.join(hooks, "shared_names.py"))
    return hooks


def case_sim_boot_record_exits_zero_without_shared_names():
    """sim_boot_record.py exits 0 in every case (its docstring). With shared_names.py absent, a Bash call that
    names no simulator tool still exits 0 and writes nothing to stdout."""
    scratch = os.path.join(RUN, "sim-boot-no-shared")
    hooks = _hooks_without_shared_names(scratch)
    cfg = os.path.join(scratch, "cfg")
    os.makedirs(cfg)
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": "s-nosh", "cwd": scratch,
               "tool_input": {"command": "export FOO=1"}}
    done = subprocess.run([sys.executable, os.path.join(hooks, "sim_boot_record.py")], input=json.dumps(payload),
                          capture_output=True, text=True, env=dict(os.environ, CLAUDE_CONFIG_DIR=cfg), cwd=scratch)
    return (done.returncode == 0 and done.stdout.strip() == ""), "rc=%s stdout=%r stderr=%r" % (
        done.returncode, done.stdout[:80], done.stderr[-160:])


def case_precompact_builds_its_digest_without_shared_names():
    """A hook that lands before its shared_names.py still does its job: the PreCompact run writes the digest."""
    scratch = os.path.join(RUN, "precompact-no-shared")
    hooks = _hooks_without_shared_names(scratch)
    cfg, repo = os.path.join(scratch, "cfg"), os.path.join(scratch, "repo")
    os.makedirs(cfg)
    os.makedirs(repo)
    transcript = os.path.join(scratch, "transcript.jsonl")
    with open(transcript, "w", encoding="utf-8") as handle:
        handle.write(json.dumps({"type": "user", "message": {"role": "user", "content": "hello"}}) + "\n")
    payload = {"session_id": "s-nosh", "transcript_path": transcript, "cwd": repo, "hook_event_name": "PreCompact"}
    done = subprocess.run([sys.executable, os.path.join(hooks, "precompact_handoff.py")], input=json.dumps(payload),
                          capture_output=True, text=True, env=dict(os.environ, CLAUDE_CONFIG_DIR=cfg), cwd=repo)
    digest = os.path.join(cfg, "state", "handoff", "s-nosh.digest.md")
    return (done.returncode == 0 and os.path.isfile(digest)), "rc=%s digest written=%s stderr=%r" % (
        done.returncode, os.path.isfile(digest), done.stderr[-160:])


# The four hook modules that may hold a config dir copy (debt config-dir-copies). HOOKS_UNDER_TEST, when set,
# names a fixture copy of hooks/, so the scan can be shown red on a copy outside the fallback.
CONFIG_DIR_MODULES = ("daily_note.py", "override.py", "precompact_handoff.py", "sim_boot_record.py")
CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"
HOME_DIRS = (".claude", "~/.claude")  # the default folder that shared_names.config_dir falls back to


def _parents(tree):
    """Each node of `tree` mapped to its parent."""
    return {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}


def _scope(node, parents):
    """The innermost function, or the module, that holds `node`."""
    while not isinstance(node, (ast.FunctionDef, ast.Module)):
        node = parents[node]
    return node


def _imports_shared_names(stmt):
    return any((isinstance(node, ast.ImportFrom) and node.module == "shared_names")
               or (isinstance(node, ast.Import) and any(alias.name == "shared_names" for alias in node.names))
               for node in ast.walk(stmt))


def _in_import_fallback(node, parents):
    """True when `node` sits in the `except ImportError` branch of a try whose body imports shared_names."""
    cur = node
    while cur in parents:
        cur = parents[cur]
        if isinstance(cur, ast.ExceptHandler) and isinstance(cur.type, ast.Name) and cur.type.id == "ImportError":
            trying = parents.get(cur)
            if isinstance(trying, ast.Try) and any(_imports_shared_names(stmt) for stmt in trying.body):
                return True
    return False


def _names_home(scope, functions):
    """True when `scope` names the .claude default, or calls a function of the module that names it, directly or
    through another call: the default may sit in a helper the copy calls."""
    todo, seen = [scope], set()
    while todo:
        cur = todo.pop()
        if any(isinstance(inner, ast.Constant) and inner.value in HOME_DIRS for inner in ast.walk(cur)):
            return True
        for inner in ast.walk(cur):
            callee = inner.func.id if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name) else None
            if callee in functions and callee not in seen:
                seen.add(callee)
                todo.append(functions[callee])
    return False


def _unguarded_copies(path):
    """The lines of `path` where a config dir copy sits outside the import fallback. A copy reads CLAUDE_CONFIG_DIR
    in a scope that names the .claude default, or calls a function that does, whatever the function is called."""
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    parents = _parents(tree)
    functions = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value == CONFIG_DIR_ENV:
            if _names_home(_scope(node, parents), functions) and not _in_import_fallback(node, parents):
                lines.append(node.lineno)
    return sorted(lines)


def case_config_dir_copies_sit_only_in_the_import_fallback():
    """A config dir copy in these four modules sits only in the `except ImportError` branch of a shared_names import:
    the install may land a hook before shared_names.py, and the fallback keeps it running. Any other copy is a second
    home (debt config-dir-copies). A source scan with the ast parser; the function's name does not matter."""
    problems = []
    for module in CONFIG_DIR_MODULES:
        for line in _unguarded_copies(os.path.join(HOOKS_UNDER_TEST, module)):
            problems.append("%s line %d copies the config dir outside the import fallback" % (module, line))
    return not problems, "; ".join(problems) or "every copy sits in the import fallback"


# Fixture modules for the scan, written under this run's folder. In each, the copy's own function names no home:
# the `.claude` default sits in a helper that the copy calls.
HELPER_DEFAULT_COPY = '''import os


def _default_dir():
    return os.path.join(os.path.expanduser("~"), ".claude")


def config_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or _default_dir()
'''
HELPER_DEFAULT_COPY_LINE = 9  # the CLAUDE_CONFIG_DIR read in config_dir
HELPER_DEFAULT_IN_FALLBACK = '''import os

try:
    from shared_names import config_dir
except ImportError:
    def _default_dir():
        return os.path.join(os.path.expanduser("~"), ".claude")

    def config_dir():
        return os.environ.get("CLAUDE_CONFIG_DIR") or _default_dir()
'''


def _fixture_module(name, text):
    """Writes a fixture module under this run's folder and returns its path."""
    path = os.path.join(RUN, "copy-fixtures", name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


def case_scan_flags_a_copy_whose_default_sits_in_a_helper():
    """A copy outside the import fallback that reads its `.claude` default through a helper it calls is a second home.
    The scan reads only the copy's own function, so it must follow the call and flag the CLAUDE_CONFIG_DIR read."""
    lines = _unguarded_copies(_fixture_module("helper_default.py", HELPER_DEFAULT_COPY))
    return lines == [HELPER_DEFAULT_COPY_LINE], "lines flagged %s, want [%d]" % (lines, HELPER_DEFAULT_COPY_LINE)


def case_scan_passes_a_fallback_copy_whose_default_sits_in_a_helper():
    """Control: the same copy inside the `except ImportError` branch is the fallback, so it is never flagged. Following
    helpers must not flag the fallback."""
    lines = _unguarded_copies(_fixture_module("helper_default_fallback.py", HELPER_DEFAULT_IN_FALLBACK))
    return lines == [], "lines flagged %s, want none" % (lines,)


def case_guard_lane_tag_is_the_shared_object():
    """hooks/guard.py holds LANE_TAG as shared_names.LANE_TAG, the one object. A literal copy of the same string
    reads equal to it, so the case asks for identity."""
    shared = _shared()
    guard = importlib.import_module("guard")
    got = getattr(guard, "LANE_TAG", None)
    return got is shared.LANE_TAG, "guard.LANE_TAG=%r is shared_names.LANE_TAG: %s" % (
        got, got is shared.LANE_TAG)


def case_report_guard_lane_tag_is_the_shared_object():
    """lint/report_guard.py holds LANE_TAG as shared_names.LANE_TAG, the one object. A literal copy of the same
    string reads equal to it, so the case asks for identity."""
    shared = _shared()
    report_guard = importlib.import_module("report_guard")
    got = getattr(report_guard, "LANE_TAG", None)
    return got is shared.LANE_TAG, "report_guard.LANE_TAG=%r is shared_names.LANE_TAG: %s" % (
        got, got is shared.LANE_TAG)


def case_guard_merge_binds_tag_prefixes_to_shared_names():
    """hooks/guard_merge.py binds ROLE_TAG_PREFIX and TOPIC_TAG_PREFIX to the shared_names tags, by an imported name,
    not to a copied literal. TOPIC_TAG_PREFIX already reads TOPIC_TAG, so it is the green control beside ROLE_TAG_PREFIX."""
    with open(os.path.join(HERE, "guard_merge.py"), encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    imported = {alias.asname or alias.name for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module == "shared_names" for alias in node.names}
    bound = {node.targets[0].id: node.value for node in tree.body
             if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)}
    problems = []
    for name, tag in (("ROLE_TAG_PREFIX", "BUILD_TAG"), ("TOPIC_TAG_PREFIX", "TOPIC_TAG")):
        value = bound.get(name)
        if value is None:
            problems.append("%s is not bound at module level" % name)
        elif not (isinstance(value, ast.Name) and value.id == tag and tag in imported):
            problems.append("%s is not %s from shared_names (line %d)" % (name, tag, value.lineno))
    return not problems, "; ".join(problems) or "both prefixes read the shared tags"


# ------------------------------------------------------------------ the Mac artifact calls, normalised
#
# Roadmap step artifact-guard-matcher-names. A Mac session calls mcp__claude-artifacts__* tools whose inputs
# differ from ArtifactData's. shared_names.normalize_data_call(tool_name, tool_input) returns the
# (canonical name, ArtifactData-shaped input) that the guards judge. The input shapes are the owner's answer to
# item 440 (12:28 CST Nov 8): db_write `ops` of {op, path, data, ifVersion} with op in set/merge/update/delete,
# db_get and db_str_replace `path` as <collection>/<id>, db_query and db_list a bare collection, publish_files
# `files` of {as, path}. The ArtifactData batch names its entries `writes`, each {op, collection, doc_id, data}.
# A Mac call with no recognised artifact id is judged as a waiting-page write; that is a guard case, not here.

MAC_PREFIX = "mcp__claude-artifacts__"
NOT_NORMALISED = ("hooks/shared_names.py has no normalize_data_call, so a Mac artifact call is not normalised "
                  "and no guard reads its fields")


def _normalised(tool_name, tool_input):
    """(canonical name, input) from normalize_data_call, or None when the function is not there yet."""
    fn = getattr(_shared(), "normalize_data_call", None)
    return None if fn is None else fn(tool_name, tool_input)


def _expect_normalised(tool_name, tool_input, want_name):
    """The canonical name a call normalises to, or a named failure. Each case then reads the input's fields."""
    got = _normalised(tool_name, tool_input)
    if got is None:
        return None, NOT_NORMALISED
    if got[0] != want_name:
        return None, "%s normalises to %r, want %r" % (tool_name, got[0], want_name)
    return got[1], ""


def _writes_of(data_input):
    """The (op, collection, doc_id, data-or-absent) rows of a batch input's writes, in order."""
    rows = []
    for write in data_input.get("writes") or []:
        rows.append((write.get("op"), write.get("collection"), write.get("doc_id"),
                     write.get("data", "absent")))
    return rows


def case_normalize_db_write_batch_maps_ops_to_writes():
    ops = [{"op": "set", "path": "items/it-1", "data": {"kind": "decision"}, "ifVersion": 3},
           {"op": "merge", "path": "items/it-2", "data": {"status": "closed"}},
           {"op": "delete", "path": "items/it-3"}]
    out, note = _expect_normalised(MAC_PREFIX + "db_write", {"ops": ops}, "ArtifactData")
    if out is None:
        return False, note
    rows = _writes_of(out)
    want = [("set", "items", "it-1", {"kind": "decision"}),
            ("update", "items", "it-2", {"status": "closed"}),
            ("delete", "items", "it-3", "absent")]
    ok = out.get("action") == "batch" and rows == want
    return ok, "action %r, writes %r, want batch with set, update (from merge) and delete: %r" % (
        out.get("action"), rows, want)


def case_normalize_db_write_splits_every_collection():
    ops = [{"op": "set", "path": "receipts/r-1", "data": {"amount": 1}},
           {"op": "set", "path": "groups/g-1", "data": {"name": "a"}},
           {"op": "update", "path": "meta/m-1", "data": {"v": 2}}]
    out, note = _expect_normalised(MAC_PREFIX + "db_write", {"ops": ops}, "ArtifactData")
    if out is None:
        return False, note
    got = [(w.get("collection"), w.get("doc_id")) for w in out.get("writes") or []]
    want = [("receipts", "r-1"), ("groups", "g-1"), ("meta", "m-1")]
    return got == want, "collection and doc_id per write %r, want %r" % (got, want)


def case_normalize_db_write_one_op_is_still_a_batch():
    ops = [{"op": "set", "path": "items/it-9", "data": {"kind": "task"}}]
    out, note = _expect_normalised(MAC_PREFIX + "db_write", {"ops": ops}, "ArtifactData")
    if out is None:
        return False, note
    return out.get("action") == "batch" and len(out.get("writes") or []) == 1, (
        "one op normalises to action %r with %d write(s), want batch with one" % (
            out.get("action"), len(out.get("writes") or [])))


def case_normalize_db_get_splits_the_path():
    out, note = _expect_normalised(MAC_PREFIX + "db_get", {"path": "answers/ans-4"}, "ArtifactData")
    if out is None:
        return False, note
    got = (out.get("action"), out.get("collection"), out.get("doc_id"))
    return got == ("get", "answers", "ans-4"), "action, collection, doc_id %r, want get answers ans-4" % (got,)


def case_normalize_db_str_replace_takes_the_item_and_field():
    out, note = _expect_normalised(MAC_PREFIX + "db_str_replace",
                                   {"path": "items/it-1", "field": "context"}, "ArtifactData")
    if out is None:
        return False, note
    got = (out.get("action"), out.get("collection"), out.get("doc_id"), out.get("field"))
    return got == ("str_replace", "items", "it-1", "context"), (
        "action, collection, doc_id, field %r, want str_replace items it-1 context" % (got,))


def case_normalize_db_str_replace_keeps_unknown_text_in_new_str():
    # Review finding F1: a Mac db_str_replace names its replacement text under a key shared_names does not map. Every
    # unknown top-level string value (not path, field or url) reaches new_str, conservatively, so a judge reads it. Three
    # unknown keys are used, so the rule is pinned for any key, not only `new` or `replacement`.
    texts = ("RWTEXT_NEW_KEY", "RWTEXT_REPLACEMENT_KEY", "RWTEXT_OTHER_KEY")
    tool_input = {"path": "items/it-1", "field": "context", "url": "https://claude.ai/artifact/x1",
                  "new": texts[0], "replacement": texts[1], "text": texts[2]}
    out, note = _expect_normalised(MAC_PREFIX + "db_str_replace", dict(tool_input), "ArtifactData")
    if out is None:
        return False, note
    new_str = out.get("new_str")
    if not isinstance(new_str, str):
        return False, "new_str is %r, want the unknown text as one string" % (new_str,)
    missing = [t for t in texts if t not in new_str]
    leaked = [tool_input[k] for k in ("path", "field", "url") if tool_input[k] in new_str]
    return not missing and not leaked, (
        "new_str %r lacks the unknown text %r and carries path, field or url text %r" % (new_str, missing, leaked))


def case_normalize_db_str_replace_with_no_text_has_no_new_str():
    # The control beside the case above: a call that carries no text gives no new text to judge.
    out, note = _expect_normalised(MAC_PREFIX + "db_str_replace", {"path": "items/it-1", "field": "context"},
                                   "ArtifactData")
    if out is None:
        return False, note
    got = out.get("new_str")
    return got in (None, ""), "new_str is %r, want none or empty for a call with no text" % (got,)


def case_normalize_db_query_and_list_take_a_bare_collection():
    # The key that carries the bare collection is not named in item 440; `collection` is the ArtifactData key
    # the guards read, so the case pins that the collection reaches it.
    notes = []
    for short, action in (("db_query", "query"), ("db_list", "list")):
        out, note = _expect_normalised(MAC_PREFIX + short, {"collection": "items"}, "ArtifactData")
        if out is None:
            notes.append(note)
            continue
        got = (out.get("action"), out.get("collection"), out.get("doc_id"))
        if got != (action, "items", None):
            notes.append("%s gives %r, want %s items with no doc_id" % (short, got, action))
    return not notes, "; ".join(notes) or "db_query gives query, db_list gives list, each on items"


def case_normalize_publish_files_is_the_page_check():
    # The page check is the Artifact arm of guard.py (PAGE_TOOL). Which `files` entry becomes the page's
    # file is not pinned here; the name is.
    got = _normalised(MAC_PREFIX + "publish_files", {"files": [{"as": "index.html", "path": "out/index.html"}]})
    if got is None:
        return False, NOT_NORMALISED
    return got[0] == "Artifact", "publish_files normalises to %r, want Artifact" % (got[0],)


def case_normalize_artifactdata_passes_through():
    tool_input = {"action": "get", "url": "https://claude.ai/artifact/x1", "collection": "items", "doc_id": "it-1"}
    got = _normalised("ArtifactData", dict(tool_input))
    if got is None:
        return False, NOT_NORMALISED
    return got == ("ArtifactData", tool_input), "ArtifactData call changed to %r" % (got,)


def case_normalize_other_names_pass_through():
    tool_input = {"command": "ls"}
    got = _normalised("Bash", dict(tool_input))
    if got is None:
        return False, NOT_NORMALISED
    return got == ("Bash", tool_input), "a Bash call changed to %r" % (got,)


MAC_CASES = [
    ("(r) a db_write batch maps ops to ArtifactData writes: set, merge as update, delete",
     case_normalize_db_write_batch_maps_ops_to_writes),
    ("(s) a db_write batch splits each path into its collection and doc_id, for every collection",
     case_normalize_db_write_splits_every_collection),
    ("(t) a db_write with one op is still an ArtifactData batch",
     case_normalize_db_write_one_op_is_still_a_batch),
    ("(u) a db_get path splits into a get of its collection and doc_id",
     case_normalize_db_get_splits_the_path),
    ("(v) a db_str_replace takes its item and field as a str_replace",
     case_normalize_db_str_replace_takes_the_item_and_field),
    ("(v2) a db_str_replace keeps every unknown top-level text in new_str, and no path, field or url text",
     case_normalize_db_str_replace_keeps_unknown_text_in_new_str),
    ("(v3) a db_str_replace with no text has no new_str",
     case_normalize_db_str_replace_with_no_text_has_no_new_str),
    ("(w) db_query and db_list take a bare collection as a query and a list",
     case_normalize_db_query_and_list_take_a_bare_collection),
    ("(x) a publish_files call is the Artifact page check",
     case_normalize_publish_files_is_the_page_check),
    ("(y) an ArtifactData call passes through unchanged",
     case_normalize_artifactdata_passes_through),
    ("(z) a call that is not an artifact data call passes through unchanged",
     case_normalize_other_names_pass_through),
]

CASES = [
    ("(a) shared_names.py exists", case_module_exists),
    ("(a) shared_names.py imports only the standard library", case_stdlib_only),
    ("(b) shared_names holds today's watched names and config_dir", case_values_pinned),
    ("(b) shared_names.config_dir answers as the guard's does", case_config_dir_answers_as_guard),
    ("(b2) shared_names holds the gh login pair: shivinate7 default, ssemwal-cdc fallback", case_gh_logins_pinned),
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
    ("(k) shared_names holds lane_head_refs: the bare step slug and lane/<slug>", case_lane_head_refs_pinned),
    ("(k2) build.py and the archive guard import lane_head_refs, with no copy of it or the lane/ prefix",
     case_one_home_for_lane_heads),
    ("(l) guard.py holds LANE_TAG as shared_names' own object", case_guard_lane_tag_is_the_shared_object),
    ("(l2) lint/report_guard.py holds LANE_TAG as shared_names' own object",
     case_report_guard_lane_tag_is_the_shared_object),
    ("(l3) guard_merge binds ROLE_TAG_PREFIX and TOPIC_TAG_PREFIX to shared_names' tags, not literals",
     case_guard_merge_binds_tag_prefixes_to_shared_names),
    ("(m) every config dir copy in the four hook modules sits only in an ImportError fallback of shared_names",
     case_config_dir_copies_sit_only_in_the_import_fallback),
    ("(n) sim_boot_record exits 0 with shared_names.py absent", case_sim_boot_record_exits_zero_without_shared_names),
    ("(o) precompact_handoff still writes its digest with shared_names.py absent",
     case_precompact_builds_its_digest_without_shared_names),
    ("(p) a copy whose .claude default sits in a helper, outside the import fallback, is flagged",
     case_scan_flags_a_copy_whose_default_sits_in_a_helper),
    ("(q) a fallback copy whose .claude default sits in a helper is not flagged",
     case_scan_passes_a_fallback_copy_whose_default_sits_in_a_helper),
]


CASES.extend(MAC_CASES)


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
    if failed:
        print("test_shared_names FAIL: %d of %d cases wrong" % (failed, len(CASES)))
        return 1
    print("test_shared_names PASS: %d of %d cases right" % (len(CASES), len(CASES)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        shutil.rmtree(RUN, ignore_errors=True)
