#!/usr/bin/env python3
"""Cases for the CI-wait cap: how long a check-in that waits on CI may wait.

Run it from the repository root:

    python3 hooks/test_ci_wait_cap.py

Standard library only, and no test runner. The cap is a dated cache fact, not a limit on the run: a
check-in that waits on CI waits at most cap_minutes() minutes, so its wake stays inside the prompt cache.
The number lives in one data file, hooks/ci_wait_cap.json, which names its source and read date. The
reader is hooks/ci_wait_cap.py: cap_minutes() reads the file on each call, through cap_path(). The CLAUDE.md
rule git-ci-wait-checks-in, its copy in skills/project-ops/templates/operating-model.md, and the decision
ci-wait-reads-run-status state the cap in words, and the cases here hold each copy to the file.

A case that fails names its cause in the message. A bad data file must make cap_minutes() raise: a
return of None or 0 is a failure, not a quiet cap. ControlTests and ScannerTests show the readers work.
"""
import datetime
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
from rule_audit import claude_md_anchors  # noqa: E402  the one home of the anchor pattern (lint/rule_audit.py)
from stale_cites import anchor_sentences  # noqa: E402  the one home of a rule's prose, read from its anchor

RUN_FOLDER = _test_temp.run_folder()
DATA_PATH = os.path.join(HERE, "ci_wait_cap.json")
READER_PATH = os.path.join(HERE, "ci_wait_cap.py")
CLAUDE_MD = os.path.join(ROOT, "CLAUDE.md")
DECISION = os.path.join(ROOT, "docs", "decisions", "ci-wait-reads-run-status.md")
TEMPLATE_REL = "skills/project-ops/templates/operating-model.md"
TEMPLATE = os.path.join(ROOT, TEMPLATE_REL)
RULE = "git-ci-wait-checks-in"
FALLBACK_START = "- The fallback:"
TEMPLATE_START = "- A session that waits on CI sets a one-time check-in"
CAP_PHRASE = re.compile(r"never\s+past\s+(\d+)\s+minutes")
INT_FIELDS = ("cache_lifetime_seconds", "overage_lifetime_seconds", "cap_minutes")


def read_text(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def write_text(path, text):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def record(cap, **changes):
    """A complete data record for the reader's fixtures. Its values are fixtures, not the real fact."""
    data = {"claim": "A check-in that waits on CI waits at most the cap.",
            "source": "Claude Code docs: prompt cache lifetime, 1 hour; 5 minutes in overage.",
            "read": "2026-11-12", "cache_lifetime_seconds": 3600,
            "overage_lifetime_seconds": 300, "cap_minutes": cap}
    data.update(changes)
    return data


def read_data(case):
    """The data file as a dict. A missing file, invalid JSON or a non-object fails the case, named."""
    case.assertTrue(os.path.isfile(DATA_PATH),
                    "hooks/ci_wait_cap.json is missing: the CI-wait cap has no dated source file")
    try:
        data = json.loads(read_text(DATA_PATH))
    except ValueError as error:
        case.fail("hooks/ci_wait_cap.json is not valid JSON: %s" % error)
    case.assertIsInstance(data, dict, "hooks/ci_wait_cap.json does not hold one JSON object")
    return data


def load_reader(case):
    """The reader module, loaded fresh from its file. A missing file, a load error or a missing
    function fails the case, named."""
    case.assertTrue(os.path.isfile(READER_PATH),
                    "hooks/ci_wait_cap.py is missing: no reader gives the CI-wait cap")
    spec = importlib.util.spec_from_file_location("ci_wait_cap_case", READER_PATH)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as error:
        case.fail("hooks/ci_wait_cap.py does not load: %r" % (error,))
    for name in ("cap_minutes", "cap_path"):
        case.assertTrue(callable(getattr(module, name, None)),
                        "hooks/ci_wait_cap.py has no function %s()" % name)
    return module


def read_template(case):
    """The operating-model template's text. A missing file fails the case, named."""
    case.assertTrue(os.path.isfile(TEMPLATE),
                    "%s is missing: the CI-wait rule's copy has no file to read" % TEMPLATE_REL)
    return read_text(TEMPLATE)


def assert_each_raises(case, module, bad):
    """Each label's file text must make cap_minutes() raise. A label whose call returns fails the case, named.
    A None text leaves that label's file absent."""
    for label, text in bad.items():
        with case.subTest(file=label):
            path = os.path.join(case.scratch, label.replace(" ", "-") + ".json")
            if text is not None:
                write_text(path, text)
            with mock.patch.object(module, "cap_path", return_value=path):
                try:
                    value = module.cap_minutes()
                except Exception:
                    continue  # the loud failure the reader's docstring promises
            case.fail("cap_minutes() returned %r for the '%s' file: it must raise" % (value, label))


def rule_prose(text, slug):
    """The prose of rule `slug`: from the previous anchor to its own, or None unless the anchor occurs
    once. anchor_sentences is the one home of that read."""
    if claude_md_anchors(text).count(slug) != 1:
        return None
    return anchor_sentences(text).get(slug)


def cap_in(prose):
    """The minutes that a prose gives as 'never past N minutes', or None."""
    if prose is None:
        return None
    found = CAP_PHRASE.search(prose)
    return int(found.group(1)) if found else None


def bullets_starting(text, start):
    """(line number, bullet) for each bullet whose first line starts with `start`, its wrapped lines joined.
    A line that is not blank and does not start with -, * or # continues the bullet above it. Lines count from 1."""
    lines = text.splitlines()
    found = []
    for index, line in enumerate(lines):
        if not line.startswith(start):
            continue
        parts = [line]
        for follow in lines[index + 1:]:
            if not follow.strip() or follow.lstrip()[:1] in ("-", "*", "#"):
                break
            parts.append(follow.strip())
        found.append((index + 1, " ".join(parts)))
    return found


def fallback_bullets(text):
    """Each bullet that starts with FALLBACK_START, with its wrapped lines joined."""
    return [bullet for _, bullet in bullets_starting(text, FALLBACK_START)]


class ScratchCase(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.mkdtemp(prefix="ci-wait-cap-", dir=RUN_FOLDER)

    def tearDown(self):
        shutil.rmtree(self.scratch, ignore_errors=True)


class DataFileTests(unittest.TestCase):
    def test_claim_and_source_are_non_empty_text(self):
        data = read_data(self)
        for key in ("claim", "source"):
            with self.subTest(field=key):
                value = data.get(key)
                self.assertIsInstance(value, str, "hooks/ci_wait_cap.json: %s is not text" % key)
                self.assertTrue(value.strip(), "hooks/ci_wait_cap.json: %s is empty" % key)

    def test_read_is_an_iso_date(self):
        value = read_data(self).get("read")
        self.assertIsInstance(value, str, "hooks/ci_wait_cap.json: read is not text")
        self.assertIsNotNone(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value),
                             "hooks/ci_wait_cap.json: read must be YYYY-MM-DD, got %r" % (value,))
        try:
            datetime.date.fromisoformat(value)
        except ValueError:
            self.fail("hooks/ci_wait_cap.json: read %r is not a calendar date" % (value,))

    def test_lifetimes_and_cap_are_positive_whole_numbers(self):
        data = read_data(self)
        for key in INT_FIELDS:
            with self.subTest(field=key):
                value = data.get(key)
                self.assertIsInstance(value, int, "hooks/ci_wait_cap.json: %s is not a whole number" % key)
                self.assertNotIsInstance(value, bool, "hooks/ci_wait_cap.json: %s is a boolean" % key)
                self.assertGreater(value, 0, "hooks/ci_wait_cap.json: %s is not positive" % key)

    def test_cap_fits_inside_the_one_hour_cache(self):
        data = read_data(self)
        cap, cache = data.get("cap_minutes"), data.get("cache_lifetime_seconds")
        self.assertIsInstance(cap, int, "hooks/ci_wait_cap.json: cap_minutes is not a whole number")
        self.assertIsInstance(cache, int, "hooks/ci_wait_cap.json: cache_lifetime_seconds is not a whole number")
        self.assertLess(cap * 60, cache,
                        "cap_minutes * 60 is %d s, not under cache_lifetime_seconds %d: a wake at the cap "
                        "would miss the cache" % (cap * 60, cache))


class ReaderTests(ScratchCase):
    def test_cap_minutes_returns_the_value_in_the_real_file(self):
        module = load_reader(self)
        value = module.cap_minutes()
        self.assertIsInstance(value, int, "cap_minutes() returned %r, not an int" % (value,))
        self.assertEqual(value, read_data(self).get("cap_minutes"),
                         "cap_minutes() differs from hooks/ci_wait_cap.json")

    def test_cap_minutes_reads_the_file_on_every_call(self):
        module = load_reader(self)
        path = os.path.join(self.scratch, "cap.json")
        write_text(path, json.dumps(record(37)))
        with mock.patch.object(module, "cap_path", return_value=path):
            first = module.cap_minutes()
            write_text(path, json.dumps(record(41)))
            second = module.cap_minutes()
        self.assertEqual(first, 37, "cap_minutes() did not return the 37 that the file holds")
        self.assertEqual(second, 41, "cap_minutes() kept 37 after the file changed to 41: it caches the value")

    def test_a_missing_empty_or_malformed_file_raises(self):
        module = load_reader(self)
        bad = {
            "absent": None,
            "empty": "",
            "not json": "{not json",
            "no cap_minutes": "{}",
            "cap as text": json.dumps(record(cap="55")),
        }
        assert_each_raises(self, module, bad)

    def test_a_cap_that_is_not_a_positive_whole_number_raises(self):
        module = load_reader(self)
        bad = {
            "cap as true": json.dumps(record(True)),
            "cap as 55.5": json.dumps(record(55.5)),
            "cap as zero": json.dumps(record(0)),
            "cap as negative": json.dumps(record(-5)),
        }
        assert_each_raises(self, module, bad)


class RuleTests(unittest.TestCase):
    def test_rule_anchor_occurs_once(self):
        count = claude_md_anchors(read_text(CLAUDE_MD)).count(RULE)
        self.assertEqual(count, 1, "CLAUDE.md holds %d copies of the %s anchor, not 1" % (count, RULE))

    def test_rule_states_the_cap_the_file_holds(self):
        text = read_text(CLAUDE_MD)
        count = claude_md_anchors(text).count(RULE)
        self.assertEqual(count, 1, "CLAUDE.md holds %d copies of the %s anchor, not 1" % (count, RULE))
        rule_minutes = cap_in(rule_prose(text, RULE))
        self.assertIsNotNone(rule_minutes, "rule %s does not say 'never past N minutes'" % RULE)
        expected = read_data(self).get("cap_minutes")
        self.assertEqual(rule_minutes, expected,
                         "rule %s says %d minutes; hooks/ci_wait_cap.json says %r"
                         % (RULE, rule_minutes, expected))


class DecisionTests(unittest.TestCase):
    def test_fallback_bullet_is_found_once(self):
        count = len(fallback_bullets(read_text(DECISION)))
        self.assertEqual(count, 1, "the CI-wait decision holds %d '- The fallback:' bullets, not 1" % count)

    def test_fallback_bullet_cites_the_data_file(self):
        bullets = fallback_bullets(read_text(DECISION))
        self.assertEqual(len(bullets), 1, "the CI-wait decision holds %d '- The fallback:' bullets, not 1"
                         % len(bullets))
        self.assertTrue("hooks/ci_wait_cap.json" in bullets[0],
                        "the fallback bullet of decision ci-wait-reads-run-status does not cite "
                        "hooks/ci_wait_cap.json")

    def test_fallback_bullet_states_the_cap_the_file_holds(self):
        bullets = fallback_bullets(read_text(DECISION))
        self.assertEqual(len(bullets), 1, "the CI-wait decision holds %d '- The fallback:' bullets, not 1"
                         % len(bullets))
        bullet_minutes = cap_in(bullets[0])
        self.assertIsNotNone(bullet_minutes, "the fallback bullet does not say 'never past N minutes'")
        expected = read_data(self).get("cap_minutes")
        self.assertEqual(bullet_minutes, expected,
                         "the fallback bullet says %d minutes; hooks/ci_wait_cap.json says %r"
                         % (bullet_minutes, expected))


class TemplateTests(unittest.TestCase):
    def test_operating_model_copy_states_the_cap_the_file_holds(self):
        copies = bullets_starting(read_template(self), TEMPLATE_START)
        self.assertEqual(len(copies), 1, "%s holds %d CI-wait bullets, not 1" % (TEMPLATE_REL, len(copies)))
        line, bullet = copies[0]
        copy_minutes = cap_in(bullet)
        self.assertIsNotNone(copy_minutes, "%s:%d: the copy of rule %s does not say 'never past N minutes'"
                             % (TEMPLATE_REL, line, RULE))
        expected = load_reader(self).cap_minutes()
        self.assertEqual(copy_minutes, expected, "%s:%d says %d minutes; cap_minutes() in hooks/ci_wait_cap.json is %r"
                         % (TEMPLATE_REL, line, copy_minutes, expected))


class ControlTests(unittest.TestCase):
    def test_template_copy_still_says_each_wider_apart(self):
        copies = bullets_starting(read_template(self), TEMPLATE_START)
        self.assertEqual(len(copies), 1, "%s holds %d CI-wait bullets, not 1" % (TEMPLATE_REL, len(copies)))
        line, bullet = copies[0]
        self.assertIn("each wider apart", bullet, "%s:%d no longer says 'each wider apart'" % (TEMPLATE_REL, line))

    def test_rule_and_bullet_still_say_each_wider_apart(self):
        prose = rule_prose(read_text(CLAUDE_MD), RULE)
        self.assertIsNotNone(prose, "CLAUDE.md: the %s anchor is not found once" % RULE)
        self.assertTrue("each wider apart" in prose,
                        "rule %s no longer says 'each wider apart', or the reader takes the wrong span" % RULE)
        bullets = fallback_bullets(read_text(DECISION))
        self.assertEqual(len(bullets), 1, "the CI-wait decision holds %d fallback bullets, not 1" % len(bullets))
        self.assertTrue("each wider apart" in bullets[0],
                        "the fallback bullet no longer says 'each wider apart'")


class ScannerTests(unittest.TestCase):
    def test_a_comment_opener_in_a_code_span_does_not_hide_the_cap(self):
        text = ("Prose with `<!--`, `/*`, `//` and `#` in code. Each wider apart, never past 40 minutes."
                "<!-- rule:r -->")
        self.assertEqual(cap_in(rule_prose(text, "r")), 40, "a comment opener in a code span hid the cap")

    def test_a_cap_wrapped_across_lines_is_read(self):
        text = "Each wider apart,\nnever past\n40 minutes.<!-- rule:r -->"
        self.assertEqual(cap_in(rule_prose(text, "r")), 40, "a cap wrapped across lines was not read")

    def test_a_lone_quote_in_text_does_not_hide_the_cap(self):
        text = ('Owner\'s note: "all checks done" sends no wake. Each wider apart, never past 40 minutes.'
                "<!-- rule:r -->")
        self.assertEqual(cap_in(rule_prose(text, "r")), 40, "a lone quote in the text hid the cap")

    def test_a_cap_in_an_earlier_rule_is_not_read(self):
        text = "Never past 99 minutes.<!-- rule:prev --> Each wider apart.<!-- rule:r -->"
        self.assertIsNone(cap_in(rule_prose(text, "r")), "the reader took a cap from an earlier rule")

    def test_an_anchor_that_occurs_twice_reads_nothing(self):
        text = "Each wider apart, never past 40 minutes.<!-- rule:r --> More.<!-- rule:r -->"
        self.assertIsNone(rule_prose(text, "r"), "an anchor that occurs twice still gave a rule's prose")

    def test_a_fallback_bullet_wrapped_onto_a_second_line_keeps_its_citation(self):
        text = "- The fallback: a check-in.\n  Cites `hooks/ci_wait_cap.json`.\n\n- Other bullet\n"
        bullets = fallback_bullets(text)
        self.assertEqual(len(bullets), 1, "a wrapped fallback bullet was not read as one bullet")
        self.assertIn("hooks/ci_wait_cap.json", bullets[0], "the wrapped line of a fallback bullet was dropped")

    def test_a_bullet_with_a_comment_opener_and_a_lone_quote_is_read_whole(self):
        text = ("- The fallback: a check-in.\n  Code `<!--` and Owner's \"done\" note, never past 55 minutes.\n\n"
                "- Other bullet\n")
        bullets = fallback_bullets(text)
        self.assertEqual(len(bullets), 1,
                         "a fallback bullet with a comment opener and a lone quote was not read as one bullet")
        self.assertEqual(cap_in(bullets[0]), 55, "a comment opener or a lone quote hid the cap of a fallback bullet")


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
