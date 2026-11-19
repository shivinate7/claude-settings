#!/usr/bin/env python3
"""Cases for hooks/start_check.py, the SessionStart hook. On a startup it flags the session with additionalContext
when the machine is full (decision machine-load-brake). It flags no model: a Haiku start is not flagged (decision
start-checks-after-call). It never stops a session: its one line carries no continue key and no stopReason key. Stdlib only. Run it from the
repository root:

    python3 hooks/test_start_check.py

Each case runs the hook as a subprocess, as Claude Code runs it: the SessionStart payload on stdin, the flag read back
from stdout, the exit code read back. A driver patches the load reading, the cloud check and process spawning in
hooks/guard.py, then runs the hook file, so no case reads the real machine load. A case that expects silence first
checks that the same reading at startup prints one flag, so a hook that never ran cannot pass as silent.

It also covers hooks/start_session_audit.py, the PostToolUse audit of a start_session call. It flags a start only when
the calling session's handoff is unread. The cases here pin that a Haiku start gets no flag for its model in either
hook, and that the audit's stop text comes only from an unread handoff.
"""
import collections
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "start_check.py")
AUDIT = os.path.join(HERE, "start_session_audit.py")
sys.path.insert(0, os.path.join(HERE, "..", "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
RUN_FOLDER = _test_temp.run_folder()
sys.path.insert(0, HERE)
import guard  # noqa: E402  the one home of the load reading, the cloud check and the model floor (hooks/guard.py)
import precompact_handoff  # noqa: E402  the one home of the handoff and re-read flag paths

HOOK_WAIT = 120  # a hang guard for the subprocess; no assert reads it
SESSION = "start-check-cases"  # the session id every payload here carries, and the one whose handoff a case leaves unread
ABSENT = object()  # a payload with no such key
FULL = {"memory_pct": 96.0, "disk_free_gb": 50.0, "disk_total_gb": 100.0}
BUSY = {"memory_pct": 90.0, "disk_free_gb": 50.0, "disk_total_gb": 100.0}
NORMAL = {"memory_pct": 40.0, "disk_free_gb": 50.0, "disk_total_gb": 100.0}
UNREAD = {"memory_pct": None, "disk_free_gb": None, "disk_total_gb": None}
HAIKU = "claude-haiku-5-5"
SONNET = "claude-sonnet-5-5"
OPUS = "claude-opus-5-1"
MODEL_DECISION = "agent-model-cap"
LOAD_DECISION = "machine-load-brake"
LANE_TAG = "cs-build:lane"  # a lane is a session whose own get_session record carries this tag
NO_WORK = ("no work", "do nothing", "not do any work")
OWNER_WITHOUT_TAG = ("without the tag", "without " + LANE_TAG, "no " + LANE_TAG, "lacks the tag", "not tagged")
OWNER_GOES_ON = ("goes on", "carries on", "may go on", "continues")
STOP_WORDS = ("stop it", "interrupt_session", "archive_session")  # the audit's remedy: the caller ends the new session
Run = collections.namedtuple("Run", "code out err")

# The driver runs as `python3 -c`. It patches guard before the hook file runs. It writes SPAWN to stderr when a
# process is started, and READ when the hook reads the load. A hook that is absent makes runpy raise, so the run
# exits 1 with no stdout. A name in the payload's "hide" list is made unimportable, so an import of it fails.
DRIVER = r'''
import json, os, runpy, subprocess, sys
hooks, hook = os.environ["START_CHECK_HOOKS"], os.environ["START_CHECK_HOOK"]
patch = json.loads(os.environ["START_CHECK_PATCH"])


def refuse(*args, **kwargs):
    sys.stderr.write("SPAWN\n")
    raise OSError("a process was started")


subprocess.Popen = refuse
os.system = refuse
os.popen = refuse
sys.path.insert(0, hooks)
hidden = patch.get("hide", [])
for name in hidden:
    sys.modules[name] = None
if "guard" not in hidden:
    import guard
    real_read_load = guard.read_load


    def read_load():
        sys.stderr.write("READ\n")
        if patch.get("read_error"):
            raise OSError("the probe read failed")
        if "reading" in patch:
            return patch["reading"]
        return real_read_load()


    guard.read_load = read_load
    guard.is_cloud = lambda: bool(patch.get("cloud"))
    if "load_full" in patch:
        guard.load_full = lambda reading: list(patch["load_full"])
code = 0
try:
    runpy.run_path(hook, run_name="__main__")
except SystemExit as exc:
    code = exc.code
sys.exit(code)
'''


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)


def new_case():
    """One folder per case under the run folder, with an empty cwd and a home that holds the config folder."""
    case = tempfile.mkdtemp(dir=RUN_FOLDER)
    os.makedirs(os.path.join(case, "home"))
    os.makedirs(os.path.join(case, "cwd"))
    return case


def run_hook(case, stdin_text, patch=None, cloud=False, hook=HOOK):
    env = dict(os.environ)
    env.pop("CLAUDE_CODE_REMOTE", None)
    if cloud:
        env["CLAUDE_CODE_REMOTE"] = "true"
    home = os.path.join(case, "home")
    env.update({"HOME": home, "USERPROFILE": home, "CLAUDE_CONFIG_DIR": os.path.join(home, ".claude"),
                "PYTHONDONTWRITEBYTECODE": "1", "START_CHECK_HOOKS": HERE, "START_CHECK_HOOK": hook,
                "START_CHECK_PATCH": json.dumps(dict(patch or {}, cloud=cloud))})
    proc = subprocess.run([sys.executable, "-c", DRIVER], input=stdin_text.encode("utf-8"),
                          cwd=os.path.join(case, "cwd"), env=env, capture_output=True, timeout=HOOK_WAIT)
    return Run(proc.returncode, proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace"))


def payload_text(case, source="startup", model=ABSENT, transcript=ABSENT):
    body = {"session_id": SESSION, "cwd": os.path.join(case, "cwd"), "hook_event_name": "SessionStart"}
    if source is not ABSENT:
        body["source"] = source
    if model is not ABSENT:
        body["model"] = model
    if transcript is not ABSENT:
        body["transcript_path"] = transcript
    return json.dumps(body)


def owner_transcript(case, text):
    """A transcript under the case folder whose last owner turn is `text`, then one reply from Claude, as Claude Code
    writes it. guard.owner_names_model reads the owner's words from it."""
    path = os.path.join(case, "transcript.jsonl")
    records = [{"type": "user", "message": {"role": "user", "content": text}},
               {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Ok."}]}}]
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("".join(json.dumps(record) + "\n" for record in records))
    return path


def audit_payload_text(case, model, transcript=ABSENT):
    """A PostToolUse payload for a start_session call that started a session, as the desktop app sends it to
    hooks/start_session_audit.py."""
    body = {"session_id": SESSION, "cwd": os.path.join(case, "cwd"), "hook_event_name": "PostToolUse",
            "tool_name": "mcp__ccd_session__start_session", "tool_input": {"model": model, "prompt": "Run the audit."},
            "tool_response": "Started session session_newcase01."}
    if transcript is not ABSENT:
        body["transcript_path"] = transcript
    return json.dumps(body)


def leave_handoff_unread(case):
    """The calling session's handoff, unread: the re-read flag and the handoff file, at the paths the handoff module
    names (precompact_handoff, the one home of them), under the case's config folder. The audit flags only this."""
    with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": os.path.join(case, "home", ".claude")}):
        paths = (precompact_handoff.reread_flag_path(SESSION), precompact_handoff.handoff_path(SESSION))
    for path in paths:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("handoff\n")


def audit_run(model, text, unread):
    """The audit's run on a start on `model`, with the owner's last typed turn `text` in the transcript the payload
    names, and the calling session's handoff unread or not. The audit reads the handoff, not the turn."""
    case = new_case()
    transcript = owner_transcript(case, text)
    if unread:
        leave_handoff_unread(case)
    return run_hook(case, audit_payload_text(case, model, transcript), hook=AUDIT)


def flag_of(test, run, cause):
    """The additionalContext of the one flag line the run printed. The line is the flag shape: a SessionStart
    hookSpecificOutput, and no continue key and no stopReason key. The run exits 0."""
    lines = [line for line in run.out.splitlines() if line.strip()]
    test.assertEqual(len(lines), 1, "%s: want one flag line on stdout, got %d (exit %s)" % (cause, len(lines), run.code))
    try:
        out = json.loads(lines[0])
    except ValueError:
        test.fail("%s: the flag line is not JSON: %r" % (cause, lines[0]))
    test.assertTrue(isinstance(out, dict) and "hookSpecificOutput" in out,
                    "%s: the line is not the flag shape, which has hookSpecificOutput: %r" % (cause, lines[0]))
    test.assertNotIn("continue", out, "%s: the flag line carries a continue key, which the flag shape forbids" % cause)
    test.assertNotIn("stopReason", out, "%s: the flag line carries a stopReason key, which the flag shape forbids" % cause)
    test.assertEqual(sorted(out), ["hookSpecificOutput"],
                     "%s: the flag line has keys %r, want hookSpecificOutput only" % (cause, sorted(out)))
    hso = out["hookSpecificOutput"]
    test.assertTrue(isinstance(hso, dict) and hso.get("hookEventName") == "SessionStart",
                    "%s: hookSpecificOutput does not name SessionStart: %r" % (cause, hso))
    context = hso.get("additionalContext")
    test.assertTrue(isinstance(context, str) and context, "%s: hookSpecificOutput has no additionalContext text" % cause)
    test.assertEqual(run.code, 0, "%s: want exit 0, got %s" % (cause, run.code))
    return context


def assert_flag_facts(test, context, named, decision, cause):
    """The facts the flag text carries. The model or the reading and the decision are named as they are. A lane is a
    session whose own get_session record carries the tag cs-build:lane: it does no work and tells its parent. A session
    without the tag goes on. A parent_session_id alone is no test of a lane (decision machine-load-brake), so every
    sentence that states the no-work rule must name the tag. The clauses are pinned by key tokens, not wording."""
    lower = context.lower()
    test.assertIn(named, context, "%s: the flag does not name %r" % (cause, named))
    test.assertIn(decision, context, "%s: the flag does not name the decision %s" % (cause, decision))
    test.assertIn(LANE_TAG, context, "%s: the flag does not name the lane tag %s" % (cause, LANE_TAG))
    test.assertIn("get_session", context, "%s: the flag does not say to read the session with get_session" % cause)
    test.assertTrue(any(token in lower for token in NO_WORK), "%s: the flag does not say a lane does no work" % cause)
    test.assertIn("parent", lower.replace("parent_session_id", ""),
                  "%s: the flag does not say a lane tells its parent" % cause)
    test.assertTrue(any(token in lower for token in OWNER_WITHOUT_TAG),
                    "%s: the flag does not say a session without the tag is the owner's" % cause)
    test.assertTrue(any(token in lower for token in OWNER_GOES_ON),
                    "%s: the flag does not say a session without the tag goes on" % cause)
    for sentence in lower.replace(";", ".").split("."):
        if any(token in sentence for token in NO_WORK):
            test.assertIn(LANE_TAG, sentence,
                          "%s: the no-work rule hangs on a test other than %s: %r" % (cause, LANE_TAG, sentence.strip()))


def assert_silent(test, run, cause):
    """No stdout, exit 0, and no traceback: the hook fails open."""
    test.assertEqual(run.out.strip(), "", "%s: want no stdout, got %r" % (cause, run.out))
    test.assertEqual(run.code, 0, "%s: want exit 0, got %s" % (cause, run.code))
    test.assertNotIn("Traceback", run.err, "%s: the hook raised an error" % cause)


def assert_fails_open(test, run, cause):
    """No stdout and exit 0. stderr may carry one line, and no more."""
    test.assertEqual(run.out.strip(), "", "%s: want no stdout, got %r" % (cause, run.out))
    test.assertEqual(run.code, 0, "%s: want exit 0, got %s" % (cause, run.code))
    lines = [line for line in run.err.splitlines() if line.strip()]
    test.assertLessEqual(len(lines), 1, "%s: stderr has %d lines, want at most one" % (cause, len(lines)))


def flag_text_or_silence(test, run, cause):
    """The additionalContext of the one flag the run printed, or "" when it printed none. Either way the exit is 0."""
    test.assertEqual(run.code, 0, "%s: want exit 0, got %s" % (cause, run.code))
    if not run.out.strip():
        return ""
    return flag_of(test, run, cause)


def audit_text(test, run, cause):
    """The additionalContext of the PostToolUse flag the audit printed, or "" when it printed none. The exit is 0."""
    test.assertEqual(run.code, 0, "%s: want exit 0, got %s" % (cause, run.code))
    lines = [line for line in run.out.splitlines() if line.strip()]
    test.assertLessEqual(len(lines), 1, "%s: want at most one flag line, got %d" % (cause, len(lines)))
    if not lines:
        return ""
    try:
        out = json.loads(lines[0])
    except ValueError:
        test.fail("%s: the flag line is not JSON: %r" % (cause, lines[0]))
    hso = out.get("hookSpecificOutput") if isinstance(out, dict) else None
    test.assertTrue(isinstance(hso, dict) and hso.get("hookEventName") == "PostToolUse",
                    "%s: the flag is not a PostToolUse flag: %r" % (cause, lines[0]))
    context = hso.get("additionalContext")
    test.assertTrue(isinstance(context, str) and context, "%s: the flag has no additionalContext text" % cause)
    return context


def listing(root):
    """Every folder and file under root, relative to it, so a write of any name shows."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            found.append(os.path.relpath(os.path.join(dirpath, name), root))
    return sorted(found)


class StartupLoadBrake(unittest.TestCase):
    def test_full_memory_at_startup_flags_once_naming_the_reading(self):
        case = new_case()
        run = run_hook(case, payload_text(case), {"reading": FULL})
        context = flag_of(self, run, "startup on a full memory reading")
        want = guard.load_full(FULL)
        self.assertTrue(want, "scope: guard.load_full calls the full memory reading normal, so there is no text to expect")
        assert_flag_facts(self, context, want[0], LOAD_DECISION, "startup on a full memory reading")

    def test_full_disk_at_startup_flags_once_naming_the_reading(self):
        case = new_case()
        disk = {"memory_pct": 40.0, "disk_free_gb": 4.9, "disk_total_gb": 100.0}
        run = run_hook(case, payload_text(case), {"reading": disk})
        context = flag_of(self, run, "startup on a disk with 4.9 GB free of 100 GB")
        want = guard.load_full(disk)
        self.assertTrue(want, "scope: guard.load_full calls 4.9 GB free of 100 GB normal, so there is no text to expect")
        assert_flag_facts(self, context, want[0], LOAD_DECISION, "startup on a full disk")

    def test_disk_full_line_is_the_smaller_of_five_percent_and_five_gb(self):
        # The line for a 40 GB disk is 2 GB (five percent), not 5 GB.
        case = new_case()

        def small(free):
            return {"memory_pct": 40.0, "disk_free_gb": free, "disk_total_gb": 40.0}

        scope = run_hook(case, payload_text(case), {"reading": small(1.9)})
        flag_of(self, scope, "scope: startup on a 40 GB disk with 1.9 GB free")
        subject = run_hook(case, payload_text(case), {"reading": small(2.5)})
        assert_silent(self, subject, "startup on a 40 GB disk with 2.5 GB free, above the 2 GB line")

    def test_memory_exactly_at_the_full_line_is_not_full(self):
        case = new_case()
        scope = run_hook(case, payload_text(case), {"reading": dict(NORMAL, memory_pct=95.1)})
        flag_of(self, scope, "scope: startup at 95.1% memory")
        subject = run_hook(case, payload_text(case), {"reading": dict(NORMAL, memory_pct=95.0)})
        assert_silent(self, subject, "startup at 95.0% memory, the full line itself")

    def test_busy_machine_is_not_braked_at_startup(self):
        case = new_case()
        scope = run_hook(case, payload_text(case), {"reading": FULL})
        flag_of(self, scope, "scope: startup on a full reading")
        subject = run_hook(case, payload_text(case), {"reading": BUSY})
        assert_silent(self, subject, "startup on a busy reading at 90% memory")

    def test_unread_reading_prints_nothing(self):
        case = new_case()
        scope = run_hook(case, payload_text(case), {"reading": FULL})
        flag_of(self, scope, "scope: startup on a full reading")
        subject = run_hook(case, payload_text(case), {"reading": UNREAD})
        assert_silent(self, subject, "startup on a reading with no value read")

    def test_read_error_prints_nothing_and_exits_zero(self):
        case = new_case()
        scope = run_hook(case, payload_text(case), {"reading": FULL})
        flag_of(self, scope, "scope: startup on a full reading")
        subject = run_hook(case, payload_text(case), {"read_error": True})
        assert_silent(self, subject, "startup when the load read raises")

    def test_one_unread_value_does_not_hide_a_full_value(self):
        case = new_case()
        reading = {"memory_pct": 97.0, "disk_free_gb": None, "disk_total_gb": None}
        run = run_hook(case, payload_text(case), {"reading": reading})
        context = flag_of(self, run, "startup with memory 97% and the disk unread")
        want = guard.load_full(reading)
        self.assertTrue(want, "scope: guard.load_full calls memory 97% with the disk unread full, so there is no text to expect")
        self.assertIn(want[0], context, "startup with memory 97%% and the disk unread: the flag does not name %r" % want[0])

    def test_a_reading_that_is_not_a_dict_prints_nothing(self):
        case = new_case()
        scope = run_hook(case, payload_text(case), {"reading": FULL})
        flag_of(self, scope, "scope: startup on a full reading")
        subject = run_hook(case, payload_text(case), {"reading": "full"})
        assert_silent(self, subject, "startup when the load read returns a string")

    def test_flag_text_comes_from_guard_load_full(self):
        # The hook takes its words from guard.load_full, one home, so the probe text must reach the flag.
        case = new_case()
        run = run_hook(case, payload_text(case), {"reading": NORMAL, "load_full": ["probe reading text"]})
        context = flag_of(self, run, "startup where guard.load_full returns a probe reading")
        self.assertIn("probe reading text", context, "the flag does not carry the text guard.load_full returned")


class BrakeOnlyAtStartup(unittest.TestCase):
    def test_resume_compact_clear_and_fork_print_nothing_on_a_full_machine(self):
        case = new_case()
        scope = run_hook(case, payload_text(case, source="startup"), {"reading": FULL})
        flag_of(self, scope, "scope: startup on a full reading")
        for source in ("resume", "compact", "clear", "fork"):
            with self.subTest(source=source):
                run = run_hook(case, payload_text(case, source=source), {"reading": FULL})
                assert_silent(self, run, "source %s on a full reading" % source)

    def test_a_payload_with_no_source_prints_nothing(self):
        case = new_case()
        scope = run_hook(case, payload_text(case), {"reading": FULL})
        flag_of(self, scope, "scope: startup on a full reading")
        subject = run_hook(case, payload_text(case, source=ABSENT), {"reading": FULL})
        assert_silent(self, subject, "a payload with no source key on a full reading")


class CloudSession(unittest.TestCase):
    def test_a_cloud_session_is_never_braked(self):
        case = new_case()
        scope = run_hook(case, payload_text(case), {"reading": FULL})
        flag_of(self, scope, "scope: startup on a full reading, not cloud")
        subject = run_hook(case, payload_text(case), {"reading": FULL}, cloud=True)
        assert_silent(self, subject, "startup on a full reading in a cloud session")

    def test_cloud_session_skips_the_brake_on_haiku_too(self):
        case = new_case()
        scope = run_hook(case, payload_text(case, model=HAIKU), {"reading": FULL})
        flag_of(self, scope, "scope: non-cloud startup on model %s and a full reading" % HAIKU)
        subject = run_hook(case, payload_text(case, model=HAIKU), {"reading": FULL}, cloud=True)
        assert_silent(self, subject, "cloud startup on model %s and a full reading" % HAIKU)
        scope = run_hook(case, payload_text(case, model=SONNET), {"reading": FULL})
        flag_of(self, scope, "scope: non-cloud startup on a full reading with a good model")
        subject = run_hook(case, payload_text(case, model=SONNET), {"reading": FULL}, cloud=True)
        assert_silent(self, subject, "cloud startup on a full reading with a good model")


class HaikuAtStartup(unittest.TestCase):
    """No model floor at startup, by owner ruling (2026-11-18 19:03 CST): no guard sits on the floor. A Haiku start gets
    no flag for its model. Each silence has a scope: the same payload on a full reading flags the load, so a hook that
    never ran cannot pass as silent."""

    def test_haiku_at_startup_is_not_flagged_for_the_model(self):
        case = new_case()
        scope = run_hook(case, payload_text(case, model=HAIKU), {"reading": FULL})
        context = flag_of(self, scope, "scope: startup on model %s and a full reading" % HAIKU)
        self.assertNotIn(HAIKU, context, "scope: the load flag names the model %s" % HAIKU)
        run = run_hook(case, payload_text(case, model=HAIKU), {"reading": NORMAL})
        assert_silent(self, run, "startup on model %s" % HAIKU)

    def test_no_haiku_spelling_is_flagged_for_the_model(self):
        for model in (HAIKU, "haiku", "Claude-Haiku-5-5"):
            with self.subTest(model=model):
                case = new_case()
                scope = run_hook(case, payload_text(case, model=model), {"reading": FULL})
                flag_of(self, scope, "scope: startup on model %s and a full reading" % model)
                run = run_hook(case, payload_text(case, model=model), {"reading": NORMAL})
                assert_silent(self, run, "startup on model %s" % model)

    def test_sonnet_opus_and_no_model_print_nothing(self):
        case = new_case()
        scope = run_hook(case, payload_text(case, model=HAIKU), {"reading": FULL})
        flag_of(self, scope, "scope: startup on model %s and a full reading" % HAIKU)
        for model in (SONNET, OPUS, ABSENT, "", None):
            with self.subTest(model=model):
                run = run_hook(case, payload_text(case, model=model), {"reading": NORMAL})
                assert_silent(self, run, "startup on model %r" % (model,))

    def test_haiku_is_braked_only_at_startup(self):
        case = new_case()
        scope = run_hook(case, payload_text(case, model=HAIKU), {"reading": FULL})
        flag_of(self, scope, "scope: startup on model %s and a full reading" % HAIKU)
        for source in ("resume", "compact", "clear", "fork"):
            with self.subTest(source=source):
                run = run_hook(case, payload_text(case, source=source, model=HAIKU), {"reading": FULL})
                assert_silent(self, run, "source %s on model %s and a full reading" % (source, HAIKU))

    def test_a_haiku_startup_on_a_full_machine_gives_one_flag_for_the_load(self):
        # The load is still braked at startup. The one flag names the reading and the load decision, never the model.
        case = new_case()
        run = run_hook(case, payload_text(case, model=HAIKU), {"reading": FULL})
        context = flag_of(self, run, "startup on model %s and a full reading" % HAIKU)
        self.assertIn("96.0", context, "startup on %s and a full reading: the flag does not name the reading" % HAIKU)
        self.assertIn(LOAD_DECISION, context,
                      "startup on %s and a full reading: the flag does not name %s" % (HAIKU, LOAD_DECISION))
        self.assertNotIn(HAIKU, context, "startup on %s and a full reading: the flag names the model" % HAIKU)
        self.assertNotIn(MODEL_DECISION, context,
                         "startup on %s and a full reading: the flag names %s" % (HAIKU, MODEL_DECISION))


class OwnersWordForHaiku(unittest.TestCase):
    """The owner's last typed turn names haiku or negates it. The start hook reads no model and no turn, so the word
    changes no flag here: a normal machine stays unflagged. Each case writes the transcript its payload names."""

    def test_a_startup_on_haiku_the_owner_named_is_not_told_to_do_no_work(self):
        case = new_case()
        transcript = owner_transcript(case, "Run the model audit on haiku.")
        self.assertTrue(guard.owner_names_model({"transcript_path": transcript}, HAIKU),
                        "scope: guard.owner_names_model does not read the owner's word for haiku in this transcript")
        run = run_hook(case, payload_text(case, model=HAIKU, transcript=transcript), {"reading": NORMAL})
        context = flag_text_or_silence(self, run, "startup on %s with the owner's word for haiku" % HAIKU)
        lower = context.lower()
        for token in NO_WORK + STOP_WORDS:
            self.assertNotIn(token, lower,
                             "startup on %s with the owner's word for haiku: the flag tells the session %r, which the "
                             "owner's word lifts: %r" % (HAIKU, token, context))

    def test_a_startup_on_haiku_with_the_owners_word_negated_is_not_flagged(self):
        case = new_case()
        transcript = owner_transcript(case, "Don't use haiku.")
        self.assertFalse(guard.owner_names_model({"transcript_path": transcript}, HAIKU),
                         "scope: guard.owner_names_model reads the negated turn \"Don't use haiku.\" as the owner's word")
        scope = run_hook(case, payload_text(case, model=HAIKU, transcript=transcript), {"reading": FULL})
        flag_of(self, scope, "scope: startup on %s with the owner's negated word and a full reading" % HAIKU)
        run = run_hook(case, payload_text(case, model=HAIKU, transcript=transcript), {"reading": NORMAL})
        assert_silent(self, run, "startup on %s with the owner's negated word for haiku" % HAIKU)


class StartSessionAudit(unittest.TestCase):
    """hooks/start_session_audit.py, run after a start_session call. It stops a start only for an unread handoff, so a
    start on haiku is not told to stop it, with or without the owner's word. Each silence has a scope: the same start with
    its handoff unread is told to stop it, so a dead audit cannot pass as silent."""

    def test_an_audit_of_a_start_on_haiku_the_owner_named_does_not_tell_the_caller_to_stop_it(self):
        case = new_case()
        transcript = owner_transcript(case, "Run the model audit on haiku.")
        self.assertTrue(guard.owner_names_model({"transcript_path": transcript}, HAIKU),
                        "scope: guard.owner_names_model does not read the owner's word for haiku in this transcript")
        run = run_hook(case, audit_payload_text(case, HAIKU, transcript), hook=AUDIT)
        context = audit_text(self, run, "audit of a start on %s the owner named" % HAIKU)
        lower = context.lower()
        for token in STOP_WORDS + NO_WORK:
            self.assertNotIn(token, lower,
                             "audit of a start on %s the owner named: the text tells the caller %r, which the owner's word "
                             "lifts: %r" % (HAIKU, token, context))

    def test_an_audit_of_a_start_on_haiku_with_no_grant_does_not_tell_the_caller_to_stop_it(self):
        premise = owner_transcript(new_case(), "Run the model audit.")
        self.assertFalse(guard.owner_names_model({"transcript_path": premise}, HAIKU),
                         "scope: guard.owner_names_model reads a turn with no model name as the owner's word for haiku")
        scope = audit_run(HAIKU, "Run the model audit.", unread=True)
        flagged = audit_text(self, scope, "scope: audit of a start on %s with an unread handoff" % HAIKU)
        self.assertIn("stop it", flagged.lower(),
                      "scope: the audit does not stop a start with an unread handoff: %r" % flagged)
        run = audit_run(HAIKU, "Run the model audit.", unread=False)
        self.assertEqual(audit_text(self, run, "audit of a start on %s with no grant" % HAIKU), "",
                         "audit of a start on %s with no grant printed a flag" % HAIKU)

    def test_an_audit_of_a_start_on_haiku_with_the_owners_word_negated_does_not_tell_the_caller_to_stop_it(self):
        premise = owner_transcript(new_case(), "Don't use haiku.")
        self.assertFalse(guard.owner_names_model({"transcript_path": premise}, HAIKU),
                         "scope: guard.owner_names_model reads the negated turn \"Don't use haiku.\" as the owner's word")
        scope = audit_run(HAIKU, "Don't use haiku.", unread=True)
        flagged = audit_text(self, scope, "scope: audit of a start on %s with an unread handoff" % HAIKU)
        self.assertIn("stop it", flagged.lower(), "scope: the audit does not stop a start with an unread handoff: %r" % flagged)
        run = audit_run(HAIKU, "Don't use haiku.", unread=False)
        self.assertEqual(audit_text(self, run, "audit of a start on %s with the owner's negated word" % HAIKU), "",
                         "audit of a start on %s with the owner's negated word printed a flag" % HAIKU)

    def test_an_audit_of_a_start_on_sonnet_prints_nothing(self):
        scope = audit_run(SONNET, "Run the model audit.", unread=True)
        flagged = audit_text(self, scope, "scope: audit of a start on %s with an unread handoff" % SONNET)
        self.assertIn("stop it", flagged.lower(),
                      "scope: the audit does not stop a start on %s with an unread handoff, so the silence below proves "
                      "nothing: %r" % (SONNET, flagged))
        subject = audit_run(SONNET, "Run the model audit.", unread=False)
        self.assertEqual(audit_text(self, subject, "audit of a start on %s" % SONNET), "",
                         "audit of a start on %s printed a flag" % SONNET)


class FailOpen(unittest.TestCase):
    def test_bad_payloads_print_nothing_and_exit_zero_even_on_a_full_machine(self):
        case = new_case()
        scope = run_hook(case, payload_text(case), {"reading": FULL})
        flag_of(self, scope, "scope: startup on a full reading")
        bad = ("", "not json", "{", "[]", '"startup"', "null", "42", "{}", '{"source": 5}',
               '{"source": null}', '{"source": ["startup"]}')
        for text in bad:
            with self.subTest(payload=text):
                run = run_hook(case, text, {"reading": FULL})
                assert_silent(self, run, "payload %r on a full reading" % text)

    def test_guard_import_failure_on_a_haiku_startup_fails_open(self):
        case = new_case()
        scope = run_hook(case, payload_text(case, model=HAIKU), {"reading": FULL})
        flag_of(self, scope, "scope: startup on model %s and a full reading with guard importable" % HAIKU)
        subject = run_hook(case, payload_text(case, model=HAIKU), {"hide": ["guard"]})
        assert_fails_open(self, subject, "startup on model %s with the guard import failing" % HAIKU)

    def test_guard_import_failure_on_a_full_machine_startup_fails_open(self):
        case = new_case()
        scope = run_hook(case, payload_text(case), {"reading": FULL})
        flag_of(self, scope, "scope: startup on a full reading with guard importable")
        subject = run_hook(case, payload_text(case), {"hide": ["guard"]})
        assert_fails_open(self, subject, "startup on a full reading with the guard import failing")


class CostProof(unittest.TestCase):
    def test_a_braked_startup_starts_no_process_and_writes_no_file(self):
        case = new_case()
        before = (listing(case), listing(HERE))
        run = run_hook(case, payload_text(case), {"reading": FULL})
        flag_of(self, run, "scope: startup on a full reading")
        self.assertNotIn("SPAWN", run.err, "startup on a full reading started a process")
        self.assertEqual((listing(case), listing(HERE)), before, "startup on a full reading wrote a file")

    def test_a_model_floor_flag_starts_no_process_and_writes_no_file(self):
        """Cited by decision start-checks-after-call, so the name stays. A Haiku startup reads the load, starts no process
        and writes no file."""
        case = new_case()
        scope = run_hook(case, payload_text(case, model=HAIKU), {"reading": FULL})
        flag_of(self, scope, "scope: startup on model %s and a full reading" % HAIKU)
        before = (listing(case), listing(HERE))
        run = run_hook(case, payload_text(case, model=HAIKU), {"reading": NORMAL})
        assert_silent(self, run, "startup on model %s" % HAIKU)
        self.assertIn("READ", run.err, "scope: a startup on model %s did not read the load" % HAIKU)
        self.assertNotIn("SPAWN", run.err, "a startup on model %s started a process" % HAIKU)
        self.assertEqual((listing(case), listing(HERE)), before, "a startup on model %s wrote a file" % HAIKU)

    def test_an_unflagged_startup_reads_the_load_and_starts_no_process(self):
        # No reading is patched, so the hook reads the real load on this machine. A flag, if any, is not asserted.
        case = new_case()
        before = (listing(case), listing(HERE))
        run = run_hook(case, payload_text(case, model=SONNET), {})
        self.assertIn("READ", run.err, "scope: a startup did not read the load")
        self.assertEqual(run.code, 0, "a startup that reads the load exits %s, want 0" % run.code)
        self.assertNotIn("SPAWN", run.err, "a startup that reads the load started a process")
        self.assertEqual((listing(case), listing(HERE)), before, "a startup that reads the load wrote a file")


class HarnessControls(unittest.TestCase):
    """Green on the code as it stands. They pin the guard readings the hook uses, and that the driver's patches
    and spawn refusal reach guard, so a red above is the hook's and not the harness's."""

    def test_control_load_full_names_the_memory_reading(self):
        full = guard.load_full(FULL)
        self.assertEqual(len(full), 1, "guard.load_full names %r for a full memory reading, want one line" % (full,))
        self.assertIn("96.0", full[0])
        self.assertEqual(guard.load_full(NORMAL), [], "guard.load_full names a normal reading as full")

    def test_control_floor_reading_names_only_haiku(self):
        self.assertEqual(guard.floor_hit(guard.SESSION_TOOL, {"model": HAIKU}), HAIKU)
        self.assertEqual(guard.floor_hit(guard.SESSION_TOOL, {"model": SONNET}), "")

    def test_control_driver_patch_reaches_guard(self):
        case = new_case()
        stand_in = os.path.join(case, "probe_hook.py")
        with open(stand_in, "w", encoding="utf-8") as handle:
            handle.write("import guard, json\nprint(json.dumps(guard.read_load()))\n")
        run = run_hook(case, "{}", {"reading": FULL}, hook=stand_in)
        self.assertEqual(run.code, 0, "the driver probe exits %s, want 0: %s" % (run.code, run.err[-200:]))
        self.assertEqual(json.loads(run.out), FULL, "the driver's reading patch does not reach guard.read_load")

    def test_control_importing_guard_starts_no_process(self):
        case = new_case()
        stand_in = os.path.join(case, "empty_hook.py")
        with open(stand_in, "w", encoding="utf-8") as handle:
            handle.write("pass\n")
        run = run_hook(case, "{}", {}, hook=stand_in)
        self.assertNotIn("SPAWN", run.err, "importing hooks/guard.py started a process")
        self.assertEqual(run.code, 0, "the import probe exits %s, want 0" % run.code)


if __name__ == "__main__":
    unittest.main(verbosity=2)
