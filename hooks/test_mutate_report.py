#!/usr/bin/env python3
"""Cases for the report mode of hooks/mutate_shared.py (`score_target`, `format_report`, `ast_mutants`,
`classify_run`). Standard library only.

    python3 hooks/test_mutate_report.py

The report mode answers one question for a verdict-deciding file: do its tests pin anything, or do
some pin a static result? Each case builds a tiny scaffold (one subject, a few suites) and asks for
the score. The failure classes under test:

- a suite that pins nothing kills no mutant and is listed as silent;
- a suite that asserts kills a mutant;
- a suite that CRASHES (a throw, with no FAIL line) is no kill;
- a suite that is red on the unmutated source is UNKNOWN, never a killer;
- a file the engine cannot run (parse error, missing suite, red baseline) reads UNKNOWN, never green.
"""
import os
import sys
import tempfile
import unittest

HOOKS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HOOKS)
import mutate_shared  # noqa: E402

SUBJECT = '''\
def is_big(n):
    if n > 10:
        return True
    return False


def pick(table):
    return table["key"]
'''

# Asserts both sides of the comparison and the returned value: every mutant of is_big dies here.
ASSERTING = '''\
import sys
sys.path.insert(0, ".")
import subject
bad = []
if subject.is_big(11) is not True:
    bad.append("big is true")
if subject.is_big(5) is not False:
    bad.append("small is false")
if subject.is_big(10) is not False:
    bad.append("boundary is false")
for name in bad:
    print("FAIL: " + name)
sys.exit(1 if bad else 0)
'''

# Calls the subject and checks nothing: a static pass.
PINS_NOTHING = '''\
import sys
sys.path.insert(0, ".")
import subject
subject.is_big(11)
subject.pick({"key": "v"})
print("PASS: it ran")
'''

# Green on the clean source. Under a mutant that returns None, `.upper()` throws: a crash, no FAIL line.
CRASHES_ON_MUTANT = '''\
import sys
sys.path.insert(0, ".")
import subject
value = subject.pick({"key": "v"}).upper()
print("PASS: " + value)
'''

# Red on the clean source by a throw, for a reason unrelated to the subject.
CRASHES_ALWAYS = '''\
raise RuntimeError("unrelated import failure")
'''

# Red on the clean source with a FAIL line: an already-red suite proves nothing about a mutant.
RED_BASELINE = '''\
import sys
print("FAIL: red before any mutation")
sys.exit(1)
'''


def scaffold(files):
    tmp = tempfile.TemporaryDirectory()
    for name, text in files.items():
        with open(os.path.join(tmp.name, name), "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    return tmp


def score(files, tests, target="subject.py", limit=40):
    tmp = scaffold(files)
    try:
        return mutate_shared.score_target(tmp.name, target, tests, limit=limit, timeout=60, jobs=2, git_init=False)
    finally:
        tmp.cleanup()


class ScoreTests(unittest.TestCase):

    def test_an_asserting_suite_kills_mutants(self):
        row = score({"subject.py": SUBJECT, "test_a.py": ASSERTING}, ["test_a.py"])
        self.assertEqual(row["status"], "OK", row)
        self.assertGreater(row["made"], 0)
        self.assertGreater(row["killed"], 0)
        self.assertEqual(row["killers"]["test_a.py"], row["killed"])
        self.assertEqual(row["silent"], [])

    def test_a_suite_that_pins_nothing_kills_zero_and_is_silent(self):
        row = score({"subject.py": SUBJECT, "test_n.py": PINS_NOTHING}, ["test_n.py"])
        self.assertEqual(row["status"], "OK", row)
        self.assertGreater(row["made"], 0)
        self.assertEqual(row["killed"], 0)
        self.assertEqual(row["rate"], 0.0)
        self.assertEqual(row["silent"], ["test_n.py"])

    def test_silent_list_names_only_the_suite_that_killed_nothing(self):
        row = score({"subject.py": SUBJECT, "test_a.py": ASSERTING, "test_n.py": PINS_NOTHING},
                    ["test_a.py", "test_n.py"])
        self.assertEqual(row["silent"], ["test_n.py"])
        self.assertGreater(row["killers"]["test_a.py"], 0)

    def test_a_crash_under_the_mutant_is_not_a_kill(self):
        row = score({"subject.py": "def pick(table):\n    return table[\"key\"]\n",
                     "test_c.py": CRASHES_ON_MUTANT}, ["test_c.py"])
        self.assertEqual(row["status"], "OK", row)
        self.assertEqual(row["killed"], 0, "a throw with no FAIL line was counted as a kill")
        self.assertGreater(row["crashed"], 0)
        self.assertEqual(row["silent"], ["test_c.py"])

    def test_a_suite_that_crashes_on_the_clean_source_is_unknown_not_a_killer(self):
        row = score({"subject.py": SUBJECT, "test_a.py": ASSERTING, "test_x.py": CRASHES_ALWAYS},
                    ["test_a.py", "test_x.py"])
        self.assertEqual(row["status"], "OK", row)
        self.assertIn("test_x.py", row["unusable"])
        self.assertNotIn("test_x.py", row["killers"])
        self.assertNotIn("test_x.py", row["silent"])

    def test_every_suite_red_on_the_clean_source_reads_unknown(self):
        row = score({"subject.py": SUBJECT, "test_r.py": RED_BASELINE}, ["test_r.py"])
        self.assertEqual(row["status"], "UNKNOWN", row)
        self.assertIsNone(row["rate"])

    def test_a_parse_error_reads_unknown(self):
        row = score({"subject.py": "def broken(:\n", "test_a.py": ASSERTING}, ["test_a.py"])
        self.assertEqual(row["status"], "UNKNOWN", row)
        self.assertIsNone(row["rate"])

    def test_a_missing_suite_reads_unknown(self):
        row = score({"subject.py": SUBJECT}, ["test_gone.py"])
        self.assertEqual(row["status"], "UNKNOWN", row)

    def test_a_missing_target_reads_unknown(self):
        row = score({"test_a.py": ASSERTING}, ["test_a.py"])
        self.assertEqual(row["status"], "UNKNOWN", row)


class PartsTests(unittest.TestCase):

    def test_classify_run_tells_an_assertion_from_a_crash(self):
        classify = mutate_shared.classify_run
        self.assertEqual(classify(0, "PASS: x\n", False), "pass")
        self.assertEqual(classify(1, "PASS: a\nFAIL: b detail\n", False), "assert")
        self.assertEqual(classify(1, "FAIL  allow (want deny) case\n", False), "assert")
        self.assertEqual(classify(1, "FAIL: test_x (m.T.test_x)\nERROR: test_y (m.T.test_y)\n", False), "assert")
        self.assertEqual(classify(1, "ERROR: test_y (m.T.test_y)\nTraceback (most recent call last):\n", False), "crash")
        self.assertEqual(classify(1, "Traceback (most recent call last):\nKeyError: 'k'\n", False), "crash")
        self.assertEqual(classify(1, "FAIL: slow\n", True), "timeout")
        self.assertEqual(classify(0, "", True), "timeout")

    def test_ast_mutants_are_valid_distinct_and_bounded(self):
        mutants = mutate_shared.ast_mutants(SUBJECT, limit=3)
        self.assertEqual(len(mutants), 3)
        self.assertEqual(len({text for _label, text in mutants}), 3)
        for _label, text in mutants:
            compile(text, "mutant", "exec")
            self.assertNotEqual(text, SUBJECT)
        self.assertEqual(mutants, mutate_shared.ast_mutants(SUBJECT, limit=3), "the sample must be repeatable")

    def test_ast_mutants_cover_the_named_operators(self):
        text = "def f(a, b):\n    if a == b and not a:\n        return True\n    return a\n"
        kinds = " ".join(label for label, _ in mutate_shared.ast_mutants(text, limit=100))
        for word in ("==", "and", "not", "True", "return"):
            self.assertIn(word, kinds)

    def test_ast_mutants_of_unparsable_source_raise(self):
        with self.assertRaises(SyntaxError):
            mutate_shared.ast_mutants("def broken(:\n", limit=5)

    def test_format_report_prints_unknown_never_a_rate(self):
        rows = [
            {"file": "a.py", "status": "OK", "made": 10, "killed": 4, "crashed": 1, "survived": 5, "rate": 0.4,
             "silent": ["test_n.py"], "unusable": {}, "reason": "", "target": 0.9},
            {"file": "b.py", "status": "UNKNOWN", "made": 0, "killed": 0, "crashed": 0, "survived": 0,
             "rate": None, "silent": [], "unusable": {}, "reason": "baseline red", "target": 0.9},
        ]
        text = mutate_shared.format_report(rows)
        self.assertIn("a.py", text)
        self.assertIn("40%", text)
        line = [ln for ln in text.splitlines() if ln.startswith("b.py")][0]
        self.assertIn("UNKNOWN", line)
        self.assertNotIn("%", line)
        self.assertIn("test_n.py", text)


if __name__ == "__main__":
    unittest.main()
