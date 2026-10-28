#!/usr/bin/env python3
"""Cases for the fast exit of hooks/config_watch.py. Standard library only, and no test runner.

Run it from the repository root:

    python hooks/test_config_watch_fast_exit.py

WHAT IT PROVES. The watch hashes the watched settings files on every call, BEFORE it imports the
guard, and imports the guard only when a hash differs from the stored baseline. The hash is the
only test of "unchanged": a same-size edit with its mtime reset must still count as changed. A
missing or unreadable baseline record means "check now".

THE SEAM. Each case runs the hook as `__main__` inside a probe process with the real stdin
payload. The probe then reports which `guard` and `guard_*` modules the process imported, and
which non-stdlib modules the hook loaded at all. The cases assume nothing about the hook's
function names or the baseline file format: a baseline is made by running the hook once, and a
corrupt baseline is made by overwriting whatever files that run left in the state folder.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_config_watch as base  # noqa: E402  (fixtures: Project, WATCH, LIFT, SONNET, KEY)

# Runs the hook file as __main__, then writes the guard-family module names and every module
# loaded beyond a bare interpreter to a side file. The hook's own stdout and exit code pass through.
PROBE = r"""
import json, runpy, sys
hook, side = sys.argv[1], sys.argv[2]
before = set(sys.modules)
code = 0
try:
    runpy.run_path(hook, run_name="__main__")
except SystemExit as stop:
    code = stop.code or 0
loaded = sorted(set(sys.modules) - before)
guards = sorted(m for m in sys.modules if m == "guard" or m.startswith("guard_"))
with open(side, "w", encoding="utf-8") as handle:
    json.dump({"guards": guards, "loaded": loaded}, handle)
sys.exit(code)
"""

NOOP = "pass\n"


def probe(project, tool, tool_input, clock=None):
    """Run the hook once, as Claude Code does. Return (rc, stdout, guards, loaded)."""
    side = os.path.join(project.root, "probe.json")
    env = project.env()
    if clock is not None:
        env[base.TEST_CLOCK_ENV] = clock
    done = subprocess.run(
        [sys.executable, "-c", PROBE, base.WATCH, side],
        input=json.dumps(project.payload(tool, tool_input)),
        capture_output=True, text=True, env=env)
    try:
        with open(side, "r", encoding="utf-8") as handle:
            seen = json.load(handle)
    except Exception:
        seen = {"guards": ["(probe wrote nothing)"], "loaded": []}
    # One word for the whole family keeps a failure line readable.
    imported = ["%d guard modules" % len(seen["guards"])] if seen["guards"] else []
    return done.returncode, done.stdout, imported, seen["loaded"]


def message_of(stdout):
    try:
        return json.loads(stdout).get("systemMessage", "") if stdout.strip() else ""
    except Exception:
        return "(stdout is not JSON: %r)" % stdout[:80]


def store_files(project):
    folder = os.path.join(project.cfg, "state", "config-watch")
    if not os.path.isdir(folder):
        return []
    return sorted(os.path.join(folder, name) for name in os.listdir(folder)
                  if not name.endswith(".tmp"))


def stdlib_only(loaded):
    """Return the loaded modules whose top-level name is not in the standard library."""
    return [m for m in loaded
            if m.split(".")[0] not in sys.stdlib_module_names and not m.startswith("_")]


EDIT = ("Edit", lambda p: {"file_path": p.other})
BASH = ("Bash", lambda p: {"command": "echo hi"})
STOP = ("", lambda p: {})

CASES = []


def case(name):
    def register(fn):
        CASES.append((name, fn))
        return fn
    return register


def fast(rc, out, guards):
    return rc == 0 and out == "" and not guards


# --------------------------------------------------------------------------- (a) unchanged


@case("a unchanged files: exit 0, silent, no guard import (Edit, Bash and Stop calls)")
def unchanged_exits_fast(project):
    project.settle()
    for tool, build in (EDIT, BASH, STOP):
        rc, out, guards, _ = probe(project, tool, build(project))
        if not fast(rc, out, guards):
            return False, "tool=%r rc=%s stdout=%r guards=%s" % (tool, rc, out[:60], guards)
    return True, "three calls on unchanged files exit 0, print nothing, import no guard module"


# --------------------------------------------------------------------------- (b) changed


@case("b1 unasked cap raise: guard imported, raise reverted and reported")
def raise_is_reverted(project):
    project.settle()
    base.write(project.settings, base.LIFT)
    rc, out, guards, _ = probe(project, "Bash", {"command": "cp x .claude/settings.local.json"})
    message = message_of(out)
    ok = (rc == 0 and guards and "unasked write" in message
          and not project.lifted())
    return ok, "rc=%s guards=%s lifted=%s message=%r" % (
        rc, guards, project.lifted(), message[:60])


@case("b2 non-cap edit: guard imported, silent, content kept")
def plain_edit_is_kept(project):
    project.settle()
    base.write(project.settings, base.UNRELATED)
    rc, out, guards, _ = probe(project, *(EDIT[0], EDIT[1](project)))
    ok = rc == 0 and out == "" and guards and project.content() == base.UNRELATED
    return ok, "rc=%s stdout=%r guards=%s kept=%s" % (
        rc, out[:40], guards, project.content() == base.UNRELATED)


@case("b3 after a handled change the new baseline holds: the next call is fast")
def change_rebaselines(project):
    project.settle()
    base.write(project.settings, base.UNRELATED)
    probe(project, *(EDIT[0], EDIT[1](project)))
    rc, out, guards, _ = probe(project, *(EDIT[0], EDIT[1](project)))
    return fast(rc, out, guards), "rc=%s stdout=%r guards=%s" % (rc, out[:40], guards)


@case("b4 the other watched file changes: guard imported")
def other_file_change(project):
    project.settle()
    other = os.path.join(project.dot, "settings.json")
    base.write(other, json.dumps({"theme": "dark"}))
    rc, out, guards, _ = probe(project, *(EDIT[0], EDIT[1](project)))
    return rc == 0 and guards, "rc=%s guards=%s" % (rc, guards)


# --------------------------------------------------------------------------- (c) same size


@case("c same size, content changed, mtime reset: still caught and reverted")
def same_size_same_mtime(project):
    project.settle()
    before = os.stat(project.settings)
    # Same byte count: the padding sits outside the JSON string, so the cap reads "opus".
    lifted = base.SONNET.replace('"sonnet"', '"opus"  ')
    assert len(lifted.encode()) == len(base.SONNET.encode()) and lifted != base.SONNET
    base.write(project.settings, lifted)
    os.utime(project.settings, ns=(before.st_atime_ns, before.st_mtime_ns))
    after = os.stat(project.settings)
    assert (after.st_size, after.st_mtime_ns) == (before.st_size, before.st_mtime_ns)
    rc, out, guards, _ = probe(project, "Bash", {"command": "sed -i s/a/b/ x"})
    ok = rc == 0 and guards and "unasked write" in message_of(out) \
        and project.content() == base.SONNET
    return ok, "rc=%s guards=%s reverted=%s" % (rc, guards, project.content() == base.SONNET)


# --------------------------------------------------------------------------- (d) bad baseline


@case("d1 missing record: guard imported, record made, next call fast")
def missing_record(project):
    rc, out, guards, _ = probe(project, *(EDIT[0], EDIT[1](project)))
    made = bool(store_files(project))
    again = probe(project, *(EDIT[0], EDIT[1](project)))
    ok = rc == 0 and out == "" and guards and made and fast(again[0], again[1], again[2])
    return ok, "first guards=%s record made=%s second guards=%s" % (guards, made, again[2])


@case("d2 missing record and a lifted file: reported unknown, never silent")
def missing_record_lifted(project):
    base.write(project.settings, base.LIFT)
    rc, out, guards, _ = probe(project, *(EDIT[0], EDIT[1](project)))
    ok = rc == 0 and guards and "no baseline" in message_of(out)
    return ok, "rc=%s guards=%s message=%r" % (rc, guards, message_of(out)[:60])


def first_sight_case(label, body, silent):
    """First sight of a file that sets only the given cap keys. Only a Sonnet cap stays silent."""
    verdict = "silent" if silent else "reported unknown"

    @case("d2 first sight, %s: %s" % (label, verdict))
    def run(project):
        base.write(project.settings, body)
        rc, out, guards, _ = probe(project, *(EDIT[0], EDIT[1](project)))
        message = message_of(out)
        heard = "no baseline" in message
        ok = rc == 0 and guards and (out == "" if silent else heard)
        return ok, "rc=%s guards=%s message=%r" % (rc, guards, message[:60])


first_sight_case("force key = opus alone", base.cap_json(force="opus"), silent=False)
first_sight_case("model key = opus alone", base.cap_json(model="opus"), silent=False)
first_sight_case("workflow force key = opus alone", json.dumps(
    {"env": {"CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL_FORCE": "opus"}}), silent=False)
first_sight_case("model key = sonnet",base.cap_json(model="sonnet"), silent=True)


@case("d3 one of two records missing: guard imported")
def one_record_missing(project):
    project.settle()
    files = store_files(project)
    if len(files) < 2:
        return False, "expected a record per watched file, found %d" % len(files)
    os.remove(files[0])
    rc, out, guards, _ = probe(project, *(EDIT[0], EDIT[1](project)))
    return rc == 0 and guards, "rc=%s guards=%s" % (rc, guards)


def corrupt_case(label, damage):
    @case("d %s record: guard imported, no crash, no skip" % label)
    def run(project):
        project.settle()
        files = store_files(project)
        if not files:
            return False, "the settle run left no record to damage"
        for path in files:
            damage(path)
        rc, out, guards, _ = probe(project, *(EDIT[0], EDIT[1](project)))
        ok = rc == 0 and guards and not message_of(out).startswith("(stdout")
        return ok, "rc=%s guards=%s stdout=%r" % (rc, guards, out[:40])

    @case("d %s record and a lifted file: reported unknown, never silent" % label)
    def run_lifted(project):
        project.settle()
        files = store_files(project)
        if not files:
            return False, "the settle run left no record to damage"
        for path in files:
            damage(path)
        base.write(project.settings, base.LIFT)
        rc, out, guards, _ = probe(project, *(EDIT[0], EDIT[1](project)))
        ok = rc == 0 and guards and "no baseline" in message_of(out)
        return ok, "rc=%s guards=%s message=%r" % (rc, guards, message_of(out)[:60])


def overwrite(text):
    def damage(path):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    return damage


def truncate_half(path):
    with open(path, "rb") as handle:
        data = handle.read()
    with open(path, "wb") as handle:
        handle.write(data[: len(data) // 2])


corrupt_case("garbage", overwrite("not json {{{"))
corrupt_case("truncated", truncate_half)
corrupt_case("empty", overwrite(""))
corrupt_case("wrong-shape", overwrite("[]"))
corrupt_case("empty-object", overwrite("{}"))


# --------------------------------------------------------------------------- (e) stdlib only


# shared_names is the one home of the watched names and is stdlib only, so the fast path
# imports it. The hook's own module name is allowed for a probe that runs it by name.
FAST_PATH_MODULES = {"config_watch", "shared_names"}


@case("e the unchanged-path run loads only standard-library modules plus shared_names")
def stdlib_only_hash_step(project):
    project.settle()
    control = os.path.join(project.root, "noop.py")
    base.write(control, NOOP)
    side = os.path.join(project.root, "control.json")
    subprocess.run([sys.executable, "-c", PROBE, control, side],
                   capture_output=True, text=True, env=project.env())
    with open(side, "r", encoding="utf-8") as handle:
        baseline_loaded = set(json.load(handle)["loaded"])
    rc, out, guards, loaded = probe(project, *(EDIT[0], EDIT[1](project)))
    extra = [m for m in stdlib_only(set(loaded) - baseline_loaded)
             if m not in FAST_PATH_MODULES]
    ok = rc == 0 and not extra and not guards
    return ok, "rc=%s non-stdlib modules=%s guards=%s" % (rc, extra, guards)


# --------------------------------------------------------------------------- (f) expiry


@case("f unchanged file whose approved lift passed its deadline: still revoked")
def expired_lift_on_unchanged_file(project):
    # An expiry is a clock event, never a write, so an unchanged hash alone cannot clear a file
    # whose baseline reads as a lift.
    project.settle()
    until = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=1)
    lift = base.cap_json(model="opus", force="1", until=base._fmt(until))
    base.write(project.settings, lift)
    approve = {"file_path": project.settings, "content": lift}
    probe(project, "Write", approve)
    later = base._fmt(until + timedelta(hours=2))
    rc, out, guards, _ = probe(project, *STOP, clock=later) if False else \
        probe(project, "", {}, clock=later)
    ok = rc == 0 and "expired" in message_of(out) and not project.lifted()
    return ok, "rc=%s guards=%s lifted=%s message=%r" % (
        rc, guards, project.lifted(), message_of(out)[:60])


# --------------------------------------------------------------------------- (g) fast-path fault


# Runs the hook as `probe` does, but first makes every content hash raise until the guard is
# imported. A path hash (the store key, which ends in ".json") still works, so the fault sits in
# `unchanged` itself and not in the baseline loader's own try block. The full check runs after the
# guard loads, so a hook that falls through to it is unaffected.
FAULT_PRELUDE = r"""
import hashlib, sys
_real = hashlib.sha256
def _faulty(data=b"", *args, **kwargs):
    guard_loaded = any(name in sys.modules for name in ("guard", "guard_under_test"))
    if not guard_loaded and not bytes(data).endswith(b".json"):
        raise RuntimeError("injected fault in the fast path")
    return _real(data, *args, **kwargs)
hashlib.sha256 = _faulty
"""


def fault_probe(project, tool, tool_input):
    """Run the hook with the fast-path fault in place. Return (rc, stdout, guards)."""
    side = os.path.join(project.root, "fault.json")
    code = FAULT_PRELUDE + PROBE
    done = subprocess.run(
        [sys.executable, "-c", code, base.WATCH, side],
        input=json.dumps(project.payload(tool, tool_input)),
        capture_output=True, text=True, env=project.env())
    try:
        with open(side, "r", encoding="utf-8") as handle:
            seen = json.load(handle)
    except Exception:
        seen = {"guards": []}
    return done.returncode, done.stdout, seen["guards"]


@case("g1 a fault in the fast check on a changed file: full check runs, raise reverted")
def fault_falls_through_to_revert(project):
    project.settle()
    base.write(project.settings, base.LIFT)
    rc, out, guards = fault_probe(project, "Bash", {"command": "cp x .claude/settings.local.json"})
    ok = rc == 0 and bool(guards) and "unasked write" in message_of(out) and not project.lifted()
    return ok, "rc=%s guards=%s lifted=%s stdout=%r" % (rc, guards, project.lifted(), out[:60])


@case("g2 a fault in the fast check on unchanged files: the guard is still imported")
def fault_imports_guard(project):
    project.settle()
    rc, out, guards = fault_probe(project, *(EDIT[0], EDIT[1](project)))
    return rc == 0 and bool(guards), "rc=%s guards=%s stdout=%r" % (rc, guards, out[:60])


def main() -> int:
    print("config_watch fast-exit cases, %d in all" % len(CASES))
    failed = 0
    for name, run in CASES:
        root = tempfile.mkdtemp(prefix="config_watch_fast_")
        try:
            project = base.Project(root, start=base.SONNET)
            try:
                ok, note = run(project)
            except Exception as error:
                ok, note = False, "case raised %s: %s" % (type(error).__name__, error)
        finally:
            shutil.rmtree(root, ignore_errors=True)
        failed += 0 if ok else 1
        print("%s  %s  (%s)" % ("PASS" if ok else "FAIL", name, note))
    print()
    if failed:
        print("test_config_watch_fast_exit FAIL: %d of %d cases wrong" % (failed, len(CASES)))
        return 1
    print("test_config_watch_fast_exit PASS: %d of %d cases right" % (len(CASES), len(CASES)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
