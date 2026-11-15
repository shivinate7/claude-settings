#!/usr/bin/env python3
"""Cases for hooks/start_check.py, the SessionStart hook. On a startup it flags the session with additionalContext
when the model is below the floor (decision agent-model-cap) or when the machine is full (decision machine-load-brake).
It never stops a session: its one line carries no continue key and no stopReason key. Stdlib only. Run it from the
repository root:

    python3 hooks/test_start_check.py

Each case runs the hook as a subprocess, as Claude Code runs it: the SessionStart payload on stdin, the flag read back
from stdout, the exit code read back. A driver patches the load reading, the cloud check and process spawning in
hooks/guard.py, then runs the hook file, so no case reads the real machine load. A case that expects silence first
checks that the same reading at startup prints one flag, so a hook that never ran cannot pass as silent.
"""
import collections
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "start_check.py")
sys.path.insert(0, os.path.join(HERE, "..", "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
RUN_FOLDER = _test_temp.run_folder()
sys.path.insert(0, HERE)
import guard  # noqa: E402  the one home of the load reading, the cloud check and the model floor (hooks/guard.py)

HOOK_WAIT = 120  # a hang guard for the subprocess; no assert reads it
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


def payload_text(case, source="startup", model=ABSENT):
    body = {"session_id": "start-check-cases", "cwd": os.path.join(case, "cwd"), "hook_event_name": "SessionStart"}
    if source is not ABSENT:
        body["source"] = source
    if model is not ABSENT:
        body["model"] = model
    return json.dumps(body)


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

    def test_cloud_session_keeps_the_model_floor_and_skips_the_brake(self):
        case = new_case()
        run = run_hook(case, payload_text(case, model=HAIKU), {"reading": NORMAL}, cloud=True)
        context = flag_of(self, run, "cloud startup on model %s" % HAIKU)
        want = guard.floor_hit(guard.SESSION_TOOL, {"model": HAIKU})
        self.assertTrue(want, "scope: guard.floor_hit does not name %s below the floor" % HAIKU)
        assert_flag_facts(self, context, want, MODEL_DECISION, "cloud startup on %s" % HAIKU)
        scope = run_hook(case, payload_text(case, model=SONNET), {"reading": FULL})
        flag_of(self, scope, "scope: non-cloud startup on a full reading with a good model")
        subject = run_hook(case, payload_text(case, model=SONNET), {"reading": FULL}, cloud=True)
        assert_silent(self, subject, "cloud startup on a full reading with a good model")


class ModelFloor(unittest.TestCase):
    def test_haiku_at_startup_flags_once_naming_the_model_and_decision(self):
        case = new_case()
        run = run_hook(case, payload_text(case, model=HAIKU), {"reading": NORMAL})
        context = flag_of(self, run, "startup on model %s" % HAIKU)
        want = guard.floor_hit(guard.SESSION_TOOL, {"model": HAIKU})
        self.assertTrue(want, "scope: guard.floor_hit does not name %s below the floor" % HAIKU)
        assert_flag_facts(self, context, want, MODEL_DECISION, "startup on %s" % HAIKU)

    def test_each_below_the_floor_spelling_flags(self):
        for model in (HAIKU, "haiku", "Claude-Haiku-5-5"):
            with self.subTest(model=model):
                case = new_case()
                run = run_hook(case, payload_text(case, model=model), {"reading": NORMAL})
                context = flag_of(self, run, "startup on model %s" % model)
                self.assertIn(model, context, "startup on model %s: the flag does not name the model" % model)

    def test_sonnet_opus_and_no_model_print_nothing(self):
        case = new_case()
        scope = run_hook(case, payload_text(case, model=HAIKU), {"reading": NORMAL})
        flag_of(self, scope, "scope: startup on model %s" % HAIKU)
        for model in (SONNET, OPUS, ABSENT, "", None):
            with self.subTest(model=model):
                run = run_hook(case, payload_text(case, model=model), {"reading": NORMAL})
                assert_silent(self, run, "startup on model %r" % (model,))

    def test_the_floor_applies_only_at_startup(self):
        case = new_case()
        scope = run_hook(case, payload_text(case, model=HAIKU), {"reading": NORMAL})
        flag_of(self, scope, "scope: startup on model %s" % HAIKU)
        for source in ("resume", "compact", "clear", "fork"):
            with self.subTest(source=source):
                run = run_hook(case, payload_text(case, source=source, model=HAIKU), {"reading": NORMAL})
                assert_silent(self, run, "source %s on model %s" % (source, HAIKU))

    def test_a_haiku_startup_on_a_full_machine_gives_one_flag_naming_the_model(self):
        # The model is checked before the load, so this one flag names the model.
        case = new_case()
        run = run_hook(case, payload_text(case, model=HAIKU), {"reading": FULL})
        context = flag_of(self, run, "startup on model %s and a full reading" % HAIKU)
        want = guard.floor_hit(guard.SESSION_TOOL, {"model": HAIKU})
        self.assertTrue(want, "scope: guard.floor_hit does not name %s below the floor" % HAIKU)
        self.assertIn(want, context, "startup on %s and a full reading: the flag does not name the model" % HAIKU)
        self.assertIn(MODEL_DECISION, context,
                      "startup on %s and a full reading: the flag does not name %s" % (HAIKU, MODEL_DECISION))


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
        scope = run_hook(case, payload_text(case, model=HAIKU), {"reading": NORMAL})
        flag_of(self, scope, "scope: startup on model %s with guard importable" % HAIKU)
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
        case = new_case()
        before = (listing(case), listing(HERE))
        run = run_hook(case, payload_text(case, model=HAIKU), {"reading": NORMAL})
        flag_of(self, run, "scope: startup on model %s" % HAIKU)
        self.assertNotIn("SPAWN", run.err, "a startup below the floor started a process")
        self.assertEqual((listing(case), listing(HERE)), before, "a startup below the floor wrote a file")

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
