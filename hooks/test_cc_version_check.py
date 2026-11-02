#!/usr/bin/env python3
"""Cases for the Claude Code compaction check: cc_facts() and cc_version_check() in
hooks/precompact_handoff.py, and the daily note that prints the check's line.

Run it from the repository root:

    python3 hooks/test_cc_version_check.py

or with pytest: python3 -m pytest hooks/test_cc_version_check.py -q

Spec: the step cc-update-behavior-diff. Standard library only, and no test runner. Every case
is red until its names exist. Each case asks for its names first, so the failure reads
"<name> is not defined in hooks/precompact_handoff.py yet", never a test bug.

Fixtures are synthetic byte blobs in the run folder, never the real binary. Each blob holds the
2.1.316 shapes the spec gives, for all eight facts. The "same facts" fixtures take their values
from the tracked baseline, hooks/cc_compaction_baseline.json. A baseline value of "unknown"
leaves that fact out of the fixture.
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
import precompact_handoff  # noqa: E402  the check's one home

RUN_FOLDER = _test_temp.run_folder()
NOTE = os.path.join(HERE, "daily_note.py")
BASELINE_PATH = os.path.join(HERE, "cc_compaction_baseline.json")
CACHE_NAME = "cc-behavior.json"
MAX_LINE = 240
VERSION = "2.1.316"
NEXT_VERSION = "2.1.320"
AI_AGENT = "claude-code_2-1-316_agent"
NEXT_AI_AGENT = "claude-code_2-1-320_agent"
NOW = "2026-11-02T10:00:00-06:00"  # the clock seam for daily_note: Central day 2026-11-02
TODAY = "2026-11-02"
ANCHORED = ("version", "idle_compaction_default", "auto_compact_enabled_default",
            "settings_keys", "env_vars", "summary_fraction_default")
# Minified identifiers. RENAMED is the false-alarm build: every identifier changes, no fact does.
NAMES = {"obj": "Yz", "N": "N", "I": "I", "Ks": "Ks", "Rd": "Rd", "E": "E", "V": "v",
         "oQt": "oQt", "rjr": "rjr", "gke": "gke", "out": "Pv", "blk": "Ab", "bf": "zb"}
RENAMED = {"obj": "Mn", "N": "Kp", "I": "Ww", "Ks": "Tq", "Rd": "Zb", "E": "Hb", "V": "Lq",
           "oQt": "Abc", "rjr": "h3m", "gke": "q9z", "out": "Gh", "blk": "Qz", "bf": "Ln"}

# Text a scanner must step over. Each one comes before the facts, so a scanner that reads a
# comment opener, an open template literal or a lone quote as code hides the facts after it.
COMMENT_OPENERS = ('var zc="/* not a comment */ // nor this # nor this";var zd="http://x/*";')
TEMPLATE_LITERAL = "var zt=`first line /* opens\nsecond // line\n# third`;"
LONE_QUOTE = "var zq=\"<p>Don't</p>\";"

SPAWNERS = ("Popen", "run", "call", "check_call", "check_output", "getoutput", "getstatusoutput")
SPAWN_OS = [name for name in dir(os)
            if name.startswith(("exec", "spawn", "posix_spawn")) or name in ("system", "popen")]


def _bang(value):
    return "!0" if value else "!1"


def binary_text(version, facts, names=NAMES, drop=(), prelude=""):
    """Minified JS text with each known fact in its spec shape. A fact that is "unknown" or in
    `drop` has no anchor in the text, so cc_facts must read it as "unknown"."""
    n = names

    def known(name):
        return name not in drop and facts.get(name, "unknown") != "unknown"

    parts =[prelude, 'var %s={VERSION:"%s",product:"claude-code"};' % (n["obj"], version)]
    if known("idle_compaction_default"):
        parts.append('%s("idleCompaction",%s);'
                     % (n["N"], _bang(facts["idle_compaction_default"])))
    if known("auto_compact_enabled_default"):
        parts.append('%s("autoCompactEnabled",%s);'
                     % (n["N"], _bang(facts["auto_compact_enabled_default"])))
    if known("settings_keys"):
        entries = ",".join("%s:()=>%s%d" % (key, n["I"], i)
                           for i, key in enumerate(facts["settings_keys"]))
        parts.append("var %s={%s};" % (n["Ks"], entries))
    if known("env_vars"):
        reads = ["%s.%s" % ("process.env" if i % 2 == 0 else n["E"], name)
                 for i, name in enumerate(facts["env_vars"])]
        parts.append("var %s=[%s];" % (n["Rd"], ",".join(reads)))
    if known("summary_fraction_default"):
        parts.append('var %s=13000;var %s=3000,%s=%r;%s("tengu_amber_rokovoko",%s);'
                     % (n["oQt"], n["rjr"], n["gke"], facts["summary_fraction_default"],
                        n["V"], n["gke"]))
    if known("output_reserve"):
        parts.append("Math.min(%s.maxOutputTokens,%s);var %s=%s;"
                     % (n["obj"], n["out"], n["out"], facts["output_reserve"]))
    if known("blocking_margin"):
        parts.append('var %s=%s;var %s={buf:(%s.limit)-%s:void 0,id:"autocompact_buffer"};'
                     % (n["blk"], facts["blocking_margin"], n["bf"], n["obj"], n["blk"]))
    return "".join(parts)


def binary_bytes(version, facts, names=NAMES, drop=(), prelude=""):
    """A small blob: an ELF-like header, the minified text, and bytes that are not UTF-8."""
    text = binary_text(version, facts, names, drop, prelude)
    return b"\x7fELF\x02\x01\x01\x00" + text.encode("ascii") + b"\x00\xff\xfe\x80"


@contextlib.contextmanager
def watch_reads(path):
    """Record each open of `path` through builtins.open, io.open or os.open."""
    target = os.path.normcase(os.path.abspath(path))
    opened = []
    real_open, real_os_open = io.open, os.open

    def named(file):
        return (isinstance(file, (str, bytes, os.PathLike))
                and os.path.normcase(os.path.abspath(os.fsdecode(file))) == target)

    def traced_open(file, *args, **kwargs):
        if named(file):
            opened.append(file)
        return real_open(file, *args, **kwargs)

    def traced_os_open(file, *args, **kwargs):
        if named(file):
            opened.append(file)
        return real_os_open(file, *args, **kwargs)

    with mock.patch("builtins.open", traced_open), mock.patch("io.open", traced_open), \
            mock.patch("os.open", traced_os_open):
        yield opened


@contextlib.contextmanager
def forbid_spawning():
    """Refuse every process start. Each attempt is recorded too, so a swallowed refusal still shows."""
    attempts = []

    def refuse(label):
        def refused(*args, **kwargs):
            attempts.append(label)
            raise AssertionError("%s was called: the check starts no process" % label)
        return refused

    with contextlib.ExitStack() as stack:
        for name in SPAWNERS:
            stack.enter_context(mock.patch.object(subprocess, name, refuse("subprocess." + name)))
        for name in SPAWN_OS:
            stack.enter_context(mock.patch.object(os, name, refuse("os." + name)))
        yield attempts


class ScratchCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="cc-version-", dir=RUN_FOLDER)
        self.config = self.scratch("config")
        self.bin = self.scratch("bin")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def scratch(self, name):
        path = os.path.join(self.root, name)
        os.makedirs(path, exist_ok=True)
        return path

    def need(self, name):
        value = getattr(precompact_handoff, name, None)
        if value is None:
            self.fail("%s is not defined in hooks/precompact_handoff.py yet: the check is not built"
                      % name)
        return value

    def baseline(self):
        self.assertTrue(os.path.isfile(BASELINE_PATH),
                        "hooks/cc_compaction_baseline.json does not exist yet: the baseline is not built")
        with open(BASELINE_PATH, encoding="utf-8") as handle:
            return json.load(handle)

    def write_binary(self, data):
        path = os.path.join(self.bin, "claude")
        with open(path, "wb") as handle:
            handle.write(data)
        return path

    def env(self, binary=None, agent=AI_AGENT):
        env = {"AI_AGENT": agent}
        if binary is not None:
            env["CLAUDE_CODE_EXECPATH"] = binary
        return env

    def assert_one_line(self, line):
        self.assertIsInstance(line, str)
        text = line.strip()
        self.assertTrue(text, "expected one line, got nothing")
        self.assertEqual(len(text.splitlines()), 1, "more than one line: %r" % line)
        self.assertLessEqual(len(text), MAX_LINE, "over %d characters: %r" % (MAX_LINE, line))

    def snapshot(self):
        tree = {}
        for dirpath, dirnames, filenames in os.walk(self.config):
            for name in dirnames:
                tree[os.path.relpath(os.path.join(dirpath, name), self.config) + os.sep] = None
            for name in filenames:
                path = os.path.join(dirpath, name)
                with open(path, "rb") as handle:
                    data = handle.read()
                tree[os.path.relpath(path, self.config)] = (data, os.stat(path).st_mtime_ns)
        return tree

    def run_note(self, binary):
        env = {key: value for key, value in os.environ.items()
               if key not in ("CLAUDE_CODE_EXECPATH", "AI_AGENT")}
        temp, home = self.scratch("temp"), self.scratch("home")
        env.update({"CLAUDE_CONFIG_DIR": self.config, "CLAUDE_DAILY_NOTE_NOW": NOW,
                    "CLAUDE_CODE_EXECPATH": binary, "AI_AGENT": AI_AGENT,
                    "TEMP": temp, "TMP": temp, "TMPDIR": temp,
                    "HOME": home, "USERPROFILE": home})
        return subprocess.run([sys.executable, NOTE], env=env, cwd=self.root, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=60)


class ChangedFactTests(ScratchCase):
    def test_a_changed_summary_fraction_prints_one_line_naming_both_values(self):
        check = self.need("cc_version_check")
        base = self.baseline()
        self.assertEqual(base["facts"]["summary_fraction_default"], 0.2)
        facts = dict(base["facts"], summary_fraction_default=0.25)
        line = check(env=self.env(self.write_binary(binary_bytes(NEXT_VERSION, facts))),
                     config=self.config)
        self.assert_one_line(line)
        self.assertIn("summary_fraction_default", line)
        self.assertRegex(line, r"(?<![\d.])0\.2(?!\d)")
        self.assertRegex(line, r"(?<![\d.])0\.25(?!\d)")


class FalseAlarmTests(ScratchCase):
    def test_a_new_version_with_renamed_identifiers_and_the_same_facts_prints_nothing(self):
        facts = self.need("cc_facts")
        check = self.need("cc_version_check")
        base = self.baseline()
        data = binary_bytes(NEXT_VERSION, base["facts"], names=RENAMED)
        self.assertEqual(facts(data), dict(base["facts"], version=NEXT_VERSION))
        line = check(env=self.env(self.write_binary(data)), config=self.config)
        self.assertEqual(line, "")


class MissingAnchorTests(ScratchCase):
    def test_a_missing_anchor_prints_one_line_that_says_unknown(self):
        facts = self.need("cc_facts")
        check = self.need("cc_version_check")
        base = self.baseline()
        data = binary_bytes(VERSION, base["facts"], drop=("summary_fraction_default",))
        self.assertEqual(facts(data)["summary_fraction_default"], "unknown")
        line = check(env=self.env(self.write_binary(data)), config=self.config)
        self.assert_one_line(line)
        self.assertIn("unknown", line)
        self.assertIn("summary_fraction_default", line)


class CostTests(ScratchCase):
    def test_the_same_binary_twice_reads_and_writes_once_and_starts_no_process(self):
        check = self.need("cc_version_check")
        base = self.baseline()
        binary = self.write_binary(binary_bytes(VERSION, base["facts"]))
        env = self.env(binary)
        before = self.snapshot()
        with watch_reads(binary) as reads, forbid_spawning() as attempts:
            first = check(env=env, config=self.config)
        after_first = self.snapshot()
        self.assertEqual(sorted(set(after_first) - set(before)), [CACHE_NAME],
                         "the first call should write exactly one file, %s" % CACHE_NAME)
        self.assertEqual(first, "")
        self.assertEqual(len(reads), 1,
                         "the first call should read the binary once, read %d times" % len(reads))
        with watch_reads(binary) as reads_again, forbid_spawning() as attempts_again:
            second = check(env=env, config=self.config)
        self.assertEqual(second, "")
        self.assertEqual(reads_again, [], "the second call read the binary again")
        self.assertEqual(self.snapshot(), after_first, "the second call wrote a file")
        self.assertEqual(attempts + attempts_again, [], "the check started a process")


class NoBinaryTests(ScratchCase):
    def test_no_binary_path_prints_one_unknown_line_per_version(self):
        check = self.need("cc_version_check")
        first = check(env=self.env(None), config=self.config)
        self.assert_one_line(first)
        self.assertIn("unknown", first)
        self.assertEqual(check(env=self.env(None), config=self.config), "")
        newer = check(env=self.env(None, NEXT_AI_AGENT), config=self.config)
        self.assert_one_line(newer)
        self.assertIn("unknown", newer)

    def test_an_unreadable_binary_path_prints_one_unknown_line_per_version(self):
        check = self.need("cc_version_check")
        missing = os.path.join(self.bin, "no-such-claude")
        first = check(env=self.env(missing), config=self.config)
        self.assert_one_line(first)
        self.assertIn("unknown", first)
        self.assertEqual(check(env=self.env(missing), config=self.config), "")


class DailyNoteTests(ScratchCase):
    def test_the_check_line_prints_when_the_done_today_stamp_already_holds_today(self):
        self.need("cc_version_check")
        base = self.baseline()
        data = binary_bytes(NEXT_VERSION, dict(base["facts"], summary_fraction_default=0.25))
        with open(os.path.join(self.config, "daily-note.stamp"), "w", encoding="utf-8") as handle:
            handle.write(TODAY + "\n")
        result = self.run_note(self.write_binary(data))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 1, "expected only the check line, got %r" % result.stdout)
        self.assert_one_line(lines[0])
        self.assertIn("summary_fraction_default", lines[0])
        self.assertIn("0.25", lines[0])


class ScannerTests(ScratchCase):
    """cc_facts scans minified source, so it gets the traps that building-scanner-respects-strings names."""

    def assert_facts_survive(self, prelude):
        facts = self.need("cc_facts")
        base = self.baseline()
        self.assertEqual(facts(binary_bytes(VERSION, base["facts"], prelude=prelude)), base["facts"])

    def test_comment_openers_inside_strings_do_not_hide_the_facts(self):
        self.assert_facts_survive(COMMENT_OPENERS)

    def test_a_multi_line_template_literal_does_not_hide_the_facts(self):
        self.assert_facts_survive(TEMPLATE_LITERAL)

    def test_a_lone_quote_in_text_does_not_hide_the_facts(self):
        self.assert_facts_survive(LONE_QUOTE)


class BaselineTests(ScratchCase):
    def test_the_baseline_facts_round_trip_through_a_fixture(self):
        facts = self.need("cc_facts")
        baseline_name = self.need("CC_BASELINE")
        self.assertEqual(os.path.normcase(os.path.abspath(os.path.join(ROOT, baseline_name))),
                         os.path.normcase(BASELINE_PATH))
        base = self.baseline()
        self.assertEqual(base["version"], VERSION)
        self.assertEqual(base["facts"]["version"], base["version"])
        for name in ANCHORED:
            self.assertNotEqual(base["facts"].get(name, "unknown"), "unknown",
                                "the baseline has no %s: the spec gives its anchor" % name)
        self.assertEqual(facts(binary_bytes(base["version"], base["facts"])), base["facts"])
        if hasattr(precompact_handoff, "SUMMARY_FRACTION"):
            self.assertEqual(precompact_handoff.SUMMARY_FRACTION,
                             base["facts"]["summary_fraction_default"])


class ReserveBaselineTests(ScratchCase):
    def test_the_baseline_holds_blocking_margin_13000_and_output_reserve_20000(self):
        base = self.baseline()
        self.assertEqual(base["facts"].get("blocking_margin"), 13000,
                         "the baseline does not hold blocking_margin 13000")
        self.assertEqual(base["facts"].get("output_reserve"), 20000,
                         "the baseline does not hold output_reserve 20000")


class BlockingBumpTests(ScratchCase):
    def test_a_blocking_margin_bump_from_13000_to_15000_prints_one_line_naming_both(self):
        check = self.need("cc_version_check")
        base = self.baseline()
        self.assertEqual(base["facts"].get("blocking_margin"), 13000,
                         "the baseline does not hold blocking_margin 13000")
        facts = dict(base["facts"], blocking_margin=15000)
        line = check(env=self.env(self.write_binary(binary_bytes(NEXT_VERSION, facts))),
                     config=self.config)
        self.assert_one_line(line)
        self.assertIn("blocking_margin", line)
        self.assertRegex(line, r"(?<!\d)13000(?!\d)")
        self.assertRegex(line, r"(?<!\d)15000(?!\d)")


class RenamedReserveTests(ScratchCase):
    def test_renamed_identifiers_with_the_same_two_values_stay_silent(self):
        facts = self.need("cc_facts")
        check = self.need("cc_version_check")
        base = self.baseline()
        self.assertEqual(base["facts"].get("blocking_margin"), 13000,
                         "the baseline does not hold blocking_margin 13000")
        self.assertEqual(base["facts"].get("output_reserve"), 20000,
                         "the baseline does not hold output_reserve 20000")
        data = binary_bytes(NEXT_VERSION, base["facts"], names=RENAMED)
        read = facts(data)
        self.assertEqual(read["blocking_margin"], 13000)
        self.assertEqual(read["output_reserve"], 20000)
        self.assertEqual(check(env=self.env(self.write_binary(data)), config=self.config), "")


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
