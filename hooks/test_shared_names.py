#!/usr/bin/env python3
"""Cases for hooks/shared_names.py, the one home of the names the guard and the config watch share.
Standard library only, and no test runner.

Run it from the repository root:

    python hooks/test_shared_names.py

THE CLAIM. `shared_names` holds the watched settings file names (`PROJECT_FROZEN_FILES`, with the
leading slash the guard matches on) and `config_dir`. It imports only the standard library, so the
config watch's fast exit can read it before the guard loads. The guard's modules re-export those
very objects, and `config_watch.py` holds no literal copy of a watched name.
"""

import ast
import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Today's values, pinned from hooks/guard_frozen.py and hooks/guard_core.py.
FROZEN_FILES = ("/.claude/settings.json", "/.claude/settings.local.json")
WATCHED = tuple(name.lstrip("/") for name in FROZEN_FILES)


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


CASES = [
    ("(a) shared_names.py exists", case_module_exists),
    ("(a) shared_names.py imports only the standard library", case_stdlib_only),
    ("(b) shared_names holds today's watched names and config_dir", case_values_pinned),
    ("(b) shared_names.config_dir answers as the guard's does", case_config_dir_answers_as_guard),
    ("(c) the guard's names are shared_names' own objects", case_guard_reexports_same_objects),
    ("(d) config_watch.py holds no literal watched name", case_config_watch_has_no_literal_copy),
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
    if failed:
        print("test_shared_names FAIL: %d of %d cases wrong" % (failed, len(CASES)))
        return 1
    print("test_shared_names PASS: %d of %d cases right" % (len(CASES), len(CASES)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
