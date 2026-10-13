#!/usr/bin/env python3
"""Cases for hooks/local_time.py. Standard library only, and no test runner.

Run it from the repository root:

    python hooks/test_local_time.py

Contract the builder codes against:

    line(clock=None) -> str
        clock: a zero-argument callable that returns an aware datetime in UTC.
               None means the real clock.
        Returns one line, for example "Local time: 2026-10-13 21:40 CDT (UTC-05:00)".
        24-hour clock, America/Chicago, DST-aware. Winter reads CST and UTC-06:00.

    As a script: reads and ignores stdin, prints line() once, exits 0 (also when
    no tz database is present).

Set LOCAL_TIME_UNDER_TEST to test another file.

No-tz-database cases: a child Python gets PYTHONTZPATH set to an empty folder and the
`tzdata` package blocked. A precondition case first proves that zoneinfo cannot load
America/Chicago in that child, so the exact-string cases cannot pass by accident.
The machine-zone case runs a child with TZ=Asia/Tokyo: the answer must not follow the OS zone.

The expected strings are hardcoded here. They are never computed with zoneinfo in this file.
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE_PATH = os.environ.get("LOCAL_TIME_UNDER_TEST") or os.path.join(HERE, "local_time.py")
ROOT = tempfile.mkdtemp(prefix="local_time_cases_")
EMPTY_TZPATH = os.path.join(ROOT, "empty_tzpath")
os.makedirs(EMPTY_TZPATH, exist_ok=True)
FAILED = []

LINE_FULL = re.compile(
    r"Local time: \d{4}-\d{2}-\d{2} \d{2}:\d{2} (?:CDT \(UTC-05:00\)|CST \(UTC-06:00\))"
)


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


# (name, UTC instant, exact expected line). Checked by hand against America/Chicago.
TABLE = [
    ("brief example: local date differs from UTC date", utc(2026, 10, 14, 2, 40),
     "Local time: 2026-10-13 21:40 CDT (UTC-05:00)"),
    ("summer is CDT", utc(2026, 7, 1, 17, 0),
     "Local time: 2026-07-01 12:00 CDT (UTC-05:00)"),
    ("winter is CST", utc(2026, 1, 15, 18, 0),
     "Local time: 2026-01-15 12:00 CST (UTC-06:00)"),
    ("spring forward, one minute before the change", utc(2026, 3, 8, 7, 59),
     "Local time: 2026-03-08 01:59 CST (UTC-06:00)"),
    ("spring forward, at the change", utc(2026, 3, 8, 8, 0),
     "Local time: 2026-03-08 03:00 CDT (UTC-05:00)"),
    ("fall back, first 01:30 is CDT", utc(2026, 11, 1, 6, 30),
     "Local time: 2026-11-01 01:30 CDT (UTC-05:00)"),
    ("fall back, second 01:30 is CST", utc(2026, 11, 1, 7, 30),
     "Local time: 2026-11-01 01:30 CST (UTC-06:00)"),
    ("24-hour afternoon", utc(2026, 7, 1, 18, 5),
     "Local time: 2026-07-01 13:05 CDT (UTC-05:00)"),
    ("leading zero after midnight", utc(2026, 7, 1, 5, 7),
     "Local time: 2026-07-01 00:07 CDT (UTC-05:00)"),
]

SUMMER = TABLE[1]

# Loads the module under test. A missing or broken file is reported by each case, never a crash.
LT = None
LOAD_ERROR = ""
try:
    _spec = importlib.util.spec_from_file_location("local_time_under_test", MODULE_PATH)
    LT = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(LT)
except Exception as e:
    LT = None
    LOAD_ERROR = "%s: %s" % (type(e).__name__, e)


def check(name, condition, detail=""):
    if condition:
        print("PASS: %s" % name)
    else:
        FAILED.append(name)
        print("FAIL: %s  %s" % (name, detail))


def missing_note():
    return "module missing or not loadable (%s)" % LOAD_ERROR


def call_line(instant):
    """Returns (line, error). The error says why no line came back."""
    if LT is None:
        return None, missing_note()
    try:
        return LT.line(clock=lambda: instant), ""
    except Exception as e:
        return None, "line() raised %s: %s" % (type(e).__name__, e)


def case_table_in_process():
    for name, instant, want in TABLE:
        got, err = call_line(instant)
        check("in process: " + name, got == want, "want %r, got %r %s" % (want, got, err))


def case_real_clock():
    if LT is None:
        check("real clock: one Central line", False, missing_note())
        return
    try:
        got = LT.line()
    except Exception as e:
        got = None
        check("real clock: one Central line", False, "line() raised %s: %s" % (type(e).__name__, e))
        return
    check("real clock: one Central line",
          isinstance(got, str) and LINE_FULL.fullmatch(got) is not None,
          "got %r" % (got,))


# A child process that loads the module with a fixed clock per instant and prints one JSON line.
# argv: mode ("blocked" or "normal"), module path, JSON list of ISO UTC instants.
DRIVER = r'''
import importlib.util, json, sys
from datetime import datetime
mode, mod_path, instants = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
out = {"precondition": "not checked", "lines": [], "error": ""}
if mode == "blocked":
    sys.modules["tzdata"] = None  # the tzdata package is absent
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try:
        ZoneInfo("America/Chicago")
        out["precondition"] = "loaded"
    except ZoneInfoNotFoundError:
        out["precondition"] = "missing"
try:
    spec = importlib.util.spec_from_file_location("local_time_child", mod_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for iso in instants:
        t = datetime.fromisoformat(iso)
        try:
            out["lines"].append(mod.line(clock=lambda t=t: t))
        except Exception as e:
            out["lines"].append("ERROR %s: %s" % (type(e).__name__, e))
except Exception as e:
    out["error"] = "%s: %s" % (type(e).__name__, e)
print(json.dumps(out))
'''


def run_driver(mode, instants, env_extra=None, drop=()):
    """Returns (result dict or None, why). why carries the child's stderr tail when no result came back."""
    env = dict(os.environ)
    for k in drop:
        env.pop(k, None)
    env.update(env_extra or {})
    payload = json.dumps([t.isoformat() for t in instants])
    try:
        proc = subprocess.run([sys.executable, "-c", DRIVER, mode, MODULE_PATH, payload],
                              capture_output=True, text=True, env=env, timeout=30)
    except subprocess.TimeoutExpired:
        return None, "child timed out after 30 s"
    why = "rc=%d stderr=%s" % (proc.returncode, proc.stderr.strip()[-300:])
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1]), why
    except (IndexError, ValueError):
        return None, "no result line; " + why


def describe(res, why):
    if res is not None and res.get("error"):
        return "module error: " + res["error"]
    return why


def case_no_tz_database():
    res, why = run_driver("blocked", [t for _, t, _ in TABLE],
                          env_extra={"PYTHONTZPATH": EMPTY_TZPATH})
    check("no tz database: zoneinfo cannot load America/Chicago (precondition)",
          res is not None and res["precondition"] == "missing",
          "precondition %r; %s" % (res and res.get("precondition"), describe(res, why)))
    lines = res["lines"] if res else []
    for i, (name, _, want) in enumerate(TABLE):
        got = lines[i] if i < len(lines) else None
        check("no tz database: " + name, got == want,
              "want %r, got %r; %s" % (want, got, describe(res, why)))


def case_machine_zone_is_not_used():
    name, instant, want = SUMMER
    res, why = run_driver("normal", [instant], env_extra={"TZ": "Asia/Tokyo"},
                          drop=("PYTHONTZPATH",))
    got = res["lines"][0] if res and res["lines"] else None
    check("TZ=Asia/Tokyo child, summer instant still Central",
          got == want, "want %r, got %r; %s" % (want, got, describe(res, why)))


def case_cli_hook_shape():
    payload = json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": "check", "cwd": HERE})
    try:
        proc = subprocess.run([sys.executable, MODULE_PATH], input=payload,
                              capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired:
        check("CLI as UserPromptSubmit hook: finishes within 20 s", False, "timed out")
        return
    lines = proc.stdout.splitlines()
    check("CLI as UserPromptSubmit hook: exit 0", proc.returncode == 0,
          "rc=%d stderr=%s" % (proc.returncode, proc.stderr.strip()[-300:]))
    check("CLI as UserPromptSubmit hook: one Central line on stdout",
          len(lines) == 1 and LINE_FULL.fullmatch(lines[0]) is not None,
          "stdout=%r" % proc.stdout[-200:])
    check("CLI as UserPromptSubmit hook: no traceback", "Traceback" not in proc.stderr,
          "stderr=%r" % proc.stderr[-300:])


# Runs the real script as __main__ with the tz database blocked. Only the shape is checked here:
# the clock is real, and the exact answers are covered by the driver cases above.
CLI_BLOCKED = (
    "import runpy, sys\n"
    "sys.modules['tzdata'] = None\n"
    "path = sys.argv[1]\n"
    "sys.argv = [path]\n"
    "runpy.run_path(path, run_name='__main__')\n"
)


def case_cli_no_tz_database():
    env = dict(os.environ)
    env["PYTHONTZPATH"] = EMPTY_TZPATH
    try:
        proc = subprocess.run([sys.executable, "-c", CLI_BLOCKED, MODULE_PATH],
                              capture_output=True, text=True, env=env, timeout=30)
    except subprocess.TimeoutExpired:
        check("CLI with no tz database: finishes within 30 s", False, "timed out")
        return
    lines = proc.stdout.splitlines()
    check("CLI with no tz database: exit 0", proc.returncode == 0,
          "rc=%d stderr=%s" % (proc.returncode, proc.stderr.strip()[-300:]))
    check("CLI with no tz database: one Central line on stdout",
          len(lines) == 1 and LINE_FULL.fullmatch(lines[0]) is not None,
          "stdout=%r" % proc.stdout[-200:])


def main():
    try:
        case_table_in_process()
        case_real_clock()
        case_no_tz_database()
        case_machine_zone_is_not_used()
        case_cli_hook_shape()
        case_cli_no_tz_database()
    finally:
        shutil.rmtree(ROOT, ignore_errors=True)
    if FAILED:
        print("FAILED: %d case(s)" % len(FAILED))
        return 1
    print("all cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
