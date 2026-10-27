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

    As a script: prints line() once, exits 0 (also when no tz database is present),
    whatever stdin holds. As a UserPromptSubmit hook it also saves each owner prompt; those cases
    are in test_feedback_inbox.py. With --agent, prints one JSON object:
    {"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": line}}.
    As a UserPromptSubmit hook it also grants the owner override when the prompt starts with the
    word `override` (the rest is the reason, logged to guard.log). The whole-prompt forms
    `override <n>[m|h]` and `override off` keep their meaning. The cases for that are the override_* ones.

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
from datetime import datetime, timedelta, timezone

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
    ("fall back, switch instant is CST (DST end bound)", utc(2026, 11, 1, 7, 0),
     "Local time: 2026-11-01 01:00 CST (UTC-06:00)"),
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


def case_cli_agent(flag="--agent"):
    payload = json.dumps({"hook_event_name": "SubagentStart", "agent_type": "test-author",
                          "cwd": HERE})
    try:
        proc = subprocess.run([sys.executable, MODULE_PATH, flag], input=payload,
                              capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired:
        check("CLI %s: finishes within 20 s" % flag, False, "timed out")
        return
    check("CLI %s: exit 0" % flag, proc.returncode == 0,
          "rc=%d stderr=%s" % (proc.returncode, proc.stderr.strip()[-300:]))
    try:
        hso = json.loads(proc.stdout)["hookSpecificOutput"]
        event, ctx = hso["hookEventName"], hso["additionalContext"]
    except (ValueError, KeyError, TypeError) as e:
        check("CLI %s: stdout is hookSpecificOutput JSON" % flag, False,
              "stdout=%r (%s)" % (proc.stdout[-200:], e))
        return
    check("CLI %s: hookEventName is SubagentStart" % flag, event == "SubagentStart",
          "got %r" % (event,))
    check("CLI %s: additionalContext starts with 'Local time: '" % flag,
          isinstance(ctx, str) and ctx.startswith("Local time: "), "got %r" % (ctx,))
    check("CLI %s: additionalContext is one Central line" % flag,
          isinstance(ctx, str) and LINE_FULL.fullmatch(ctx) is not None, "got %r" % (ctx,))


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
        # stdin=DEVNULL: local_time.py reads stdin as a hook. An inherited open pipe never closes.
        proc = subprocess.run([sys.executable, "-c", CLI_BLOCKED, MODULE_PATH],
                              capture_output=True, text=True, env=env, timeout=30,
                              stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        check("CLI with no tz database: finishes within 30 s", False, "timed out")
        return
    lines = proc.stdout.splitlines()
    check("CLI with no tz database: exit 0", proc.returncode == 0,
          "rc=%d stderr=%s" % (proc.returncode, proc.stderr.strip()[-300:]))
    check("CLI with no tz database: one Central line on stdout",
          len(lines) == 1 and LINE_FULL.fullmatch(lines[0]) is not None,
          "stdout=%r" % proc.stdout[-200:])


# OWNER OVERRIDE. local_time.py is the only UserPromptSubmit hook, so it is where the owner's
# word `override` becomes an override. It calls override.grant(session_id, prompt, now), which writes
# <config dir>/state/override/<session_id>.json as {"kind": "once" or "timed", "until": a time}.
# The keyword counts only as the FIRST word of the prompt, in any case, after leading whitespace: an override
# spent on a word inside a sentence, a notice, or text another agent wrote would be an override the owner
# never gave. A prompt that starts with the word is a one-act override and the rest is the reason, written
# to guard.log. `override <n>[m|h]` and `override off` keep their meaning as the whole prompt. These
# cases drive the hook as a child, as Claude Code does, with the clock and the config directory in its
# environment.
OV_NOW = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)  # 13:00 in US Central (CDT)
OV_SESSION = "ov-session-0001"


def ov_cfg():
    return tempfile.mkdtemp(prefix="cfg_", dir=ROOT)


def ov_type(cfg, prompt, session=OV_SESSION):
    """The owner types `prompt`. Returns the finished child, or None when it timed out."""
    env = dict(os.environ)
    for name in ("PYTHONUTF8", "PYTHONIOENCODING"):
        env.pop(name, None)
    env.update(CLAUDE_CONFIG_DIR=cfg, HOME=cfg, USERPROFILE=cfg, LOCAL_TIME_NOW=OV_NOW.isoformat())
    payload = json.dumps({"hook_event_name": "UserPromptSubmit", "session_id": session,
                          "prompt": prompt, "cwd": HERE})
    try:
        return subprocess.run([sys.executable, MODULE_PATH], input=payload, capture_output=True,
                              text=True, env=env, timeout=30)
    except subprocess.TimeoutExpired:
        return None


def ov_pass(cfg, session=OV_SESSION):
    """(kind, until as an aware datetime) from the session's override file, or None when it is missing or
    unreadable. `until` may be an ISO-8601 string or epoch seconds."""
    path = os.path.join(cfg, "state", "override", session + ".json")
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        until = data["until"]
        if isinstance(until, (int, float)):
            until = datetime.fromtimestamp(until / 1000 if until > 1e11 else until, timezone.utc)
        else:
            until = datetime.fromisoformat(str(until).replace("Z", "+00:00"))
            until = until if until.tzinfo else until.replace(tzinfo=timezone.utc)
        return data["kind"], until
    except (OSError, ValueError, KeyError, TypeError):
        return None


def ov_files(cfg):
    """Every file under the config directory, as paths relative to it."""
    return sorted(os.path.relpath(os.path.join(folder, name), cfg)
                  for folder, _, names in os.walk(cfg) for name in names)


def ov_pass_files(cfg):
    """The files under state/override/. A grant may log to guard.log or write other state, so the
    cases that want "no override" look only here."""
    return [f for f in ov_files(cfg) if f.startswith(os.path.join("state", "override") + os.sep)]


def ov_log(cfg):
    """The lines of guard.log in the config directory, or [] when there is none. Splits on \\n only:
    a reason that holds a newline must not make a second line."""
    try:
        with open(os.path.join(cfg, "guard.log"), encoding="utf-8", newline="") as handle:
            return [l for l in handle.read().split("\n") if l]
    except (OSError, UnicodeError):  # a log that cannot be read is no line
        return []


# (name, prompt, kind, how long the override lasts)
OV_GRANTS = [
    ("`override` is a one-act override that ends after 10 minutes", "override", "once", timedelta(minutes=10)),
    ("`override 15m` is a 15-minute override", "override 15m", "timed", timedelta(minutes=15)),
    ("`override 15`: a bare number is minutes", "override 15", "timed", timedelta(minutes=15)),
    ("`override 3h` is a 3-hour override", "override 3h", "timed", timedelta(hours=3)),
    ("`override 72h`: the owner picks the length, there is no cap", "override 72h", "timed",
     timedelta(hours=72)),
    ("`OVERRIDE 2H`: keyword and unit ignore case", "OVERRIDE 2H", "timed", timedelta(hours=2)),
    ("`override 2h` is a 2-hour override", "override 2h", "timed", timedelta(hours=2)),
]


def case_override_grants():
    for name, prompt, kind, length in OV_GRANTS:
        cfg = ov_cfg()
        proc = ov_type(cfg, prompt)
        got = ov_pass(cfg)
        want = (kind, OV_NOW + length)
        ok = (proc is not None and got is not None and got[0] == want[0]
              and abs((got[1] - want[1]).total_seconds()) <= 1)
        check("override: " + name, ok, "want %r, got %r; files %r; stderr %r" % (
            want, got, ov_files(cfg), proc.stderr.strip()[-120:] if proc else "timed out"))


def case_override_context_line():
    # The session learns the override exists and when it ends: the owner's grant reached the guard.
    for prompt, ends in (("override", "13:10"), ("override 3h", "16:00"),
                         ("override: use opus for that one review agent", "13:10")):
        proc = ov_type(ov_cfg(), prompt)
        lines = proc.stdout.splitlines() if proc else []
        named = [l for l in lines if "override" in l.lower()]
        check("override: `%s` prints one line that names the override and its end %s" % (prompt, ends),
              any(ends in l for l in named) and any(LINE_FULL.fullmatch(l) for l in lines),
              "stdout=%r" % (proc.stdout[-200:] if proc else "timed out"))


def case_opus_context_line():
    # The Opus word prints one line naming the override, its role and its end; `opus off` names the end of
    # the override, and `override off` leaves an Opus override in place.
    cfg = ov_cfg()
    for prompt, want in (("opus 3h", "16:00"), ("opus builders 2h", "builder spawns"),
                         ("opus off", "Opus override: ended.")):
        proc = ov_type(cfg, prompt)
        lines = proc.stdout.splitlines() if proc else []
        check("opus: `%s` prints one line that names the Opus override and %s" % (prompt, want),
              sum(l.startswith("Opus override:") for l in lines) == 1 and any(want in l for l in lines)
              and any(LINE_FULL.fullmatch(l) for l in lines),
              "stdout=%r" % (proc.stdout[-200:] if proc else "timed out"))
    cfg = ov_cfg()
    ov_type(cfg, "opus 2h")
    ov_type(cfg, "override off")
    check("opus: `override off` leaves an Opus override in place",
          os.path.exists(os.path.join(cfg, "state", "override", "opus", OV_SESSION + ".json")),
          "files %r" % ov_pass_files(cfg))


def case_override_off():
    cfg = ov_cfg()
    ov_type(cfg, "override 15m")
    before = ov_pass(cfg)
    proc = ov_type(cfg, "override off")
    check("override: `override off` removes a timed override",
          before is not None and proc is not None and ov_pass(cfg) is None and not ov_pass_files(cfg),
          "before %r, after %r, files %r" % (before, ov_pass(cfg), ov_pass_files(cfg)))
    cfg = ov_cfg()
    ov_type(cfg, "override")
    before = ov_pass(cfg)
    ov_type(cfg, "override off")
    check("override: `override off` removes a one-act override", before is not None and ov_pass(cfg) is None,
          "before %r, after %r" % (before, ov_pass(cfg)))
    cfg = ov_cfg()
    proc = ov_type(cfg, "override off")
    check("override: `override off` with no override is quiet and writes nothing",
          proc is not None and proc.returncode == 0 and "Traceback" not in proc.stderr
          and not ov_pass_files(cfg), "rc=%s files %r" % (proc and proc.returncode, ov_pass_files(cfg)))


# A prompt that starts with the word `override` is a one-act override, and the rest is the reason. The
# reason goes to guard.log on ONE line: the log is one record per line, tab-separated, so a newline
# or a tab in the owner's text is folded to a space. The log line may be built any way; the cases only
# look for the reason's text. (name, prompt, the reason as it must read in the log line)
OV_WORDS = [
    ("the owner's example, a colon and then the reason", "override: use opus for that one review agent",
     "use opus for that one review agent"),
    ("no colon: the rest is still the reason", "override use opus for that one review agent",
     "use opus for that one review agent"),
    ("a reason that starts with `the`", "override the guard for me", "the guard for me"),
    ("leading whitespace and a capital letter", "   Override: use opus for that one review agent\n",
     "use opus for that one review agent"),
    ("upper case keyword: the reason keeps its own case", "OVERRIDE: Use Opus for that ONE agent",
     "Use Opus for that ONE agent"),
    ("the word on one line and the reason on the next", "override\nrun the tests", "run the tests"),
    ("a newline and a tab in the reason fold to one log line",
     "override: use opus\nfor the review agent\twith a tab", "use opus for the review agent with a tab"),
    ("a lone quote in the reason", "override: don't ask twice", "don't ask twice"),
]


def case_override_takes_words():
    for name, prompt, reason in OV_WORDS:
        cfg = ov_cfg()
        proc = ov_type(cfg, prompt)
        got = ov_pass(cfg)
        hits = [l for l in ov_log(cfg) if reason in l]
        ok = (proc is not None and proc.returncode == 0 and got is not None and got[0] == "once"
              and abs((got[1] - (OV_NOW + timedelta(minutes=10))).total_seconds()) <= 1
              and len(hits) == 1)
        check("override: takes words, %s" % name, ok,
              "override %r; log lines holding the reason %d of %r; files %r; stderr %r" % (
                  got, len(hits), ov_log(cfg), ov_files(cfg), proc.stderr.strip()[-120:] if proc else "timed out"))


# None of these starts with the word `override` as a word of its own, so none grants an override and none
# writes a log line. The word as a plural, a past participle or an -ing form is a different word. So is
# a name that only begins with it: a hyphenated flag, a call, a possessive.
# Each of these holds the word `override`, and none of them is the whole prompt. The notice forms are
# the tags shared_names.MACHINE_TAGS lists: text a tool or an agent wrote, never the owner.
OV_NO_GRANT = [
    ("a word at the end of a message", "please override"),
    ("the word inside a sentence", "please don't override this"),
    ("the word at the end of a longer prompt", "run the tests, then override"),
    ("a plural", "overrides"),
    ("a plural and then a reason", "overrides: use opus"),
    ("a past participle", "overridden by me"),
    ("an -ing form", "overriding the guard"),
    ("a length with no space", "override15m"),
    ("a hyphenated flag name", "override-flag is not set, check the config"),
    ("a call", "override() should return the parent value"),
    ("a possessive", "override's behaviour is wrong when the override is spent"),
    ("the word at the start of a later line", "run the tests\noverride: use opus"),
    ("a system-reminder notice", "<system-reminder>\noverride\n</system-reminder>"),
    ("a system-reminder notice that holds a reason", "<system-reminder>\noverride: use opus\n</system-reminder>"),
    ("a task-notification notice", "<task-notification>override</task-notification>"),
]


def case_override_not_the_first_word():
    for name, prompt in OV_NO_GRANT:
        cfg = ov_cfg()
        proc = ov_type(cfg, prompt)
        check("override: grants nothing for " + name,
              proc is not None and proc.returncode == 0 and not ov_pass_files(cfg) and not ov_log(cfg),
              "files %r; log %r" % (ov_pass_files(cfg), ov_log(cfg)))


def case_override_reason_goes_through_the_log_writer():
    # guard.log has one locked writer, guard_core.record. The reason line must use it: a second writer
    # with no lock can interleave with a guard line. Patch the writer and count the calls, so the case
    # needs no race. With the writer patched out, no other code may write guard.log either.
    hooks = os.path.dirname(MODULE_PATH)
    cfg = ov_cfg()
    saved_env = {k: os.environ.get(k) for k in ("CLAUDE_CONFIG_DIR", "HOME", "USERPROFILE")}
    calls = []
    guard_core = None
    real_record = None
    got = error = None
    try:
        sys.path.insert(0, hooks)
        import guard_core
        real_record = guard_core.record
        guard_core.record = lambda *args, **kwargs: calls.append(args + tuple(kwargs.values()))
        spec = importlib.util.spec_from_file_location("override_under_test",
                                                      os.path.join(hooks, "override.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # after the patch, so a `from guard_core import record` is patched too
        os.environ.update(CLAUDE_CONFIG_DIR=cfg, HOME=cfg, USERPROFILE=cfg)
        got = module.grant(OV_SESSION, "override: use opus for that one review agent", OV_NOW)
    except Exception as e:
        error = "%s: %s" % (type(e).__name__, e)
    finally:
        if guard_core is not None and real_record is not None:
            guard_core.record = real_record
        for name, value in saved_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        if hooks in sys.path:
            sys.path.remove(hooks)
    named = [c for c in calls if "use opus for that one review agent" in " ".join(str(a) for a in c)]
    check("override: the reason line goes through guard_core.record, once, and no other writer",
          error is None and got is not None and got[0] == "once" and len(calls) == 1 and len(named) == 1
          and "guard.log" not in ov_files(cfg),
          "error %r; grant %r; record calls %r; files %r" % (error, got, calls, ov_files(cfg)))


def case_override_reason_with_a_lone_surrogate():
    # A lone surrogate cannot be encoded as UTF-8. A write that raises on it and swallows the error
    # drops the reason line without a trace. The override still stands, and the line must still land.
    cfg = ov_cfg()
    proc = ov_type(cfg, "override: use opus \ud800 for the review agent")
    got = ov_pass(cfg)
    log = ov_log(cfg)
    hits = [l for l in log if "use opus" in l and "for the review agent" in l]
    check("override: a reason with a lone surrogate still writes one log line",
          proc is not None and proc.returncode == 0 and got is not None and got[0] == "once"
          and len(log) == 1 and len(hits) == 1,
          "override %r; log %r; files %r; stderr %r" % (got, log, ov_files(cfg),
                                                    proc.stderr.strip()[-120:] if proc else "timed out"))


def case_override_corrupt_file_replaced():
    cfg = ov_cfg()
    path = os.path.join(cfg, "state", "override", OV_SESSION + ".json")
    os.makedirs(os.path.dirname(path))
    with open(path, "wb") as handle:
        handle.write(b"not json {")
    proc = ov_type(cfg, "override 15m")
    got = ov_pass(cfg)
    check("override: a corrupt override file is replaced by the next grant",
          proc is not None and got is not None and got[0] == "timed"
          and abs((got[1] - (OV_NOW + timedelta(minutes=15))).total_seconds()) <= 1,
          "got %r" % (got,))
    # A new grant never reads the old one, so a timed override does not stretch a later one-act override.
    cfg = ov_cfg()
    ov_type(cfg, "override 3h")
    ov_type(cfg, "override")
    got = ov_pass(cfg)
    check("override: a later `override` replaces a timed override with a one-act override",
          got is not None and got[0] == "once"
          and abs((got[1] - (OV_NOW + timedelta(minutes=10))).total_seconds()) <= 1, "got %r" % (got,))


def case_override_session_id_stays_inside():
    # The session id names the override file. An id that climbs out must not write outside state/override/.
    # guard.log at the top of the config directory is not an override file, so a grant may write it.
    for session in ("../escape", "../../escape", "..\\escape", "a/b"):
        cfg = ov_cfg()
        proc = ov_type(cfg, "override", session=session)
        stray = [f for f in ov_files(cfg)
                 if f != "guard.log" and os.path.dirname(f) != os.path.join("state", "override")]
        check("override: session id %r writes no file outside state/override" % session,
              proc is not None and proc.returncode == 0 and not stray, "files %r" % (ov_files(cfg),))


def case_override_fail_open():
    # An advisory hook: a pass that cannot be written must not break the time line or the exit code.
    blocker = os.path.join(ROOT, "not_a_folder")
    with open(blocker, "w", encoding="utf-8") as handle:
        handle.write("x")
    proc = ov_type(blocker, "override 15m")
    lines = proc.stdout.splitlines() if proc else []
    check("override: a config directory that cannot be written still prints the time and exits 0",
          proc is not None and proc.returncode == 0 and any(LINE_FULL.fullmatch(l) for l in lines)
          and "Traceback" not in proc.stderr,
          "rc=%s stdout=%r stderr=%r" % (proc and proc.returncode, proc and proc.stdout[-120:],
                                         proc and proc.stderr[-120:]))


def main():
    try:
        case_table_in_process()
        case_real_clock()
        case_no_tz_database()
        case_machine_zone_is_not_used()
        case_cli_hook_shape()
        case_cli_agent()
        case_cli_agent("--subagent")  # the old flag, read until local_time.OLD_FLAG_ENDS
        case_cli_no_tz_database()
        case_override_grants()
        case_override_context_line()
        case_override_off()
        case_opus_context_line()
        case_override_takes_words()
        case_override_reason_goes_through_the_log_writer()
        case_override_reason_with_a_lone_surrogate()
        case_override_not_the_first_word()
        case_override_corrupt_file_replaced()
        case_override_session_id_stays_inside()
        case_override_fail_open()
    finally:
        shutil.rmtree(ROOT, ignore_errors=True)
    if FAILED:
        print("FAILED: %d case(s)" % len(FAILED))
        return 1
    print("all cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
