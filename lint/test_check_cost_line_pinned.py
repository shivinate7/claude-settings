#!/usr/bin/env python3
"""Cases for lint/check_cost_line_pinned.py, the check that each file a decision's cost line names is pinned by a test.
Standard library only.

    python3 lint/test_check_cost_line_pinned.py

The definitions the cases pin. The check reads raw text, with no parser:
- A cost line is a line that starts with the label `Cost` (a bullet or bold allowed), the lines indented
  deeper under it, and the body of a `## Cost` heading up to the next heading or a footer label such as `Home:`.
  Only these lines name files for this check. A file named anywhere else in a decision is not read.
- A named file is a token with a file extension that resolves to a tracked file. A token with a folder is
  that exact path. A bare token is every tracked file with that basename. A token that names no tracked file
  is skipped: a stale name is lint/stale_cites.py's finding.
- A named file is pinned when it is a test path (hooks/guard.py is_test_rel): the test file is the pin. Or when
  a test file's raw text names the token as written, as a whole token: a path by its full path, a bare name by
  its basename. A longer name does not count. A mention in a non-test file, such as a decision, does not count.
  A mention counts wherever it sits in the test's text: in a string, after a `#`, or after a lone quote.

The check runs as lint/check_cost_line_pinned.py in each fixture repo, with `--root <fixture>`. It prints one line
per unpinned file as `<decision>:<line>: <file> ...` and exits 1, or exits 0 when every named file is pinned.
CHECK_COST_LINE_PINNED_UNDER_TEST overrides the module path. A stub run points it at a script that exits 0 and
prints nothing, which is the repo before the check: each case that expects a flag then fails on its exit-code
assertion, a behavioural red and not a missing module. The sweep of old run folders is proved in
lint/test_find_copies.py (RunFolderSweepTest).
"""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  removes a fixture folder, read-only git objects included (testing/tracked_tree.py)

MODULE = os.path.abspath(os.environ.get("CHECK_COST_LINE_PINNED_UNDER_TEST")
                         or os.path.join(HERE, "check_cost_line_pinned.py"))
DECISION = "docs/decisions/fixture-cost.md"
GIT_ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
for _name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
    GIT_ENV.pop(_name, None)  # the outer shell's git state never leaks into a fixture
RUN_FOLDER = None


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    if RUN_FOLDER and os.path.isdir(RUN_FOLDER):
        tracked_tree.rm_tree(RUN_FOLDER)  # test-temp-standard: teardown removes the run folder


def decision(body):
    """A decision file's text: a title, then the body the case names its cost lines in."""
    return "# Fixture decision\n\n" + body


class CostFixture(unittest.TestCase):
    """A fixture repo per case: each file is written and committed, then the check runs in it."""

    def setUp(self):
        self.tree = tempfile.mkdtemp(dir=RUN_FOLDER, prefix="clp_")
        self.addCleanup(tracked_tree.rm_tree, self.tree)
        self.git("init", "-q")
        self.git("symbolic-ref", "HEAD", "refs/heads/main")

    def git(self, *args):
        done = subprocess.run(["git", "-C", self.tree, "-c", "user.name=test", "-c", "user.email=test@example.com",
                               "-c", "core.autocrlf=false", *args],
                              check=True, capture_output=True, text=True, env=GIT_ENV)
        return done.stdout.strip()

    def build(self, files):
        """Write each path -> text, commit them, and prove each one is tracked, so the check sees it (P7)."""
        for rel, text in files.items():
            path = os.path.join(self.tree, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(text)
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", "fixture")
        tracked = self.git("ls-files").split("\n")
        for rel in files:
            self.assertIn(rel, tracked, "the fixture did not track %s, so the check would not see it" % rel)

    def text(self, rel):
        with open(os.path.join(self.tree, *rel.split("/")), encoding="utf-8") as f:
            return f.read()

    def check(self):
        """Run the check on the fixture. Returns (exit code, stdout and stderr)."""
        done = subprocess.run([sys.executable, MODULE, "--root", self.tree], cwd=self.tree,
                              capture_output=True, text=True, encoding="utf-8", errors="replace", env=GIT_ENV)
        return done.returncode, done.stdout + done.stderr


class CostLinePinned(CostFixture):
    """Cases for lint/check_cost_line_pinned.py. Each red case names one cause; each green case is its control."""

    def test_cost_file_no_test_mentions_fails(self):
        self.build({
            DECISION: decision("Cost: one read of `hooks/unpinned_reader.py` per run.\n"),
            "hooks/unpinned_reader.py": "READ = 1\n",
            "hooks/test_other.py": 'OTHER = "other_reader.py"\n',
        })
        self.assertNotIn("hooks/unpinned_reader.py", self.text("hooks/test_other.py"))  # P7: the subject is absent
        rc, out = self.check()
        self.assertEqual(rc, 1, "a cost line names hooks/unpinned_reader.py and no test mentions it, so the check passed it:\n" + out)
        self.assertIn(DECISION, out, "the failure does not name the decision that holds the cost line:\n" + out)
        self.assertIn("hooks/unpinned_reader.py", out, "the failure does not name the unpinned file:\n" + out)

    def test_cost_file_a_test_names_passes(self):
        self.build({
            DECISION: decision("Cost: one read of `hooks/pinned_reader.py` per run.\n"),
            "hooks/pinned_reader.py": "READ = 1\n",
            "hooks/test_reads.py": 'READER = "hooks/pinned_reader.py"\n',
        })
        self.assertIn("hooks/pinned_reader.py", self.text("hooks/test_reads.py"))  # P7: the test names the path
        rc, out = self.check()
        self.assertEqual(rc, 0, "a test names hooks/pinned_reader.py as written, yet the check flagged it:\n" + out)

    def test_cost_line_naming_no_file_passes(self):
        self.build({
            DECISION: decision("Cost: no new process, no file written, no timer.\n"),
            "hooks/test_reads.py": 'READER = "unrelated.py"\n',
        })
        rc, out = self.check()
        self.assertEqual(rc, 0, "a cost line that names no file was flagged:\n" + out)

    def test_mention_in_a_decision_does_not_pin(self):
        self.build({
            DECISION: decision("Cost: one read of `hooks/self_reader.py` per run.\n\n"
                               "Proof: `hooks/self_reader.py` is read once in CI.\n"),
            "hooks/self_reader.py": "READ = 1\n",
            "hooks/test_other.py": 'OTHER = "other.py"\n',
        })
        rc, out = self.check()
        self.assertEqual(rc, 1, "the decision's own Proof line pinned hooks/self_reader.py; only a test may pin it:\n" + out)
        self.assertIn("hooks/self_reader.py", out, "the failure does not name the file the decision pins by itself:\n" + out)

    def test_longer_bare_name_does_not_pin(self):
        self.build({
            DECISION: decision("Cost: one read of `reader.py` per run.\n"),
            "hooks/reader.py": "READ = 1\n",
            "hooks/test_other.py": 'NAME = "my_reader.py"\n',
        })
        rc, out = self.check()
        self.assertEqual(rc, 1, "the test names my_reader.py, a longer name, so it pinned reader.py:\n" + out)

    def test_mention_in_a_string_or_after_a_quote_pins(self):
        self.build({
            DECISION: decision("Cost: one read of `hooks/hash_reader.py` and `hooks/quote_reader.py` per run.\n"),
            "hooks/hash_reader.py": "READ = 1\n",
            "hooks/quote_reader.py": "READ = 2\n",
            "hooks/test_mentions.py": ('NOTE = "# hooks/hash_reader.py is read once"\n'
                                       "DONT = 'the test does not skip it: hooks/quote_reader.py'\n"),
        })
        rc, out = self.check()
        self.assertEqual(rc, 0, "a mention after a # in a string, or after a lone quote, did not pin its file:\n" + out)

    def test_lone_quote_in_cost_line_does_not_hide_the_file(self):
        self.build({
            DECISION: decision("Cost: the guard's read of `hooks/quote_cost_reader.py` runs once per run.\n"),
            "hooks/quote_cost_reader.py": "READ = 1\n",
            "hooks/test_other.py": 'OTHER = "other.py"\n',
        })
        rc, out = self.check()
        self.assertEqual(rc, 1, "a lone apostrophe before the path hid hooks/quote_cost_reader.py from the check:\n" + out)
        self.assertIn("hooks/quote_cost_reader.py", out, "the failure does not name the file after the apostrophe:\n" + out)

    def test_heading_cost_section_is_read(self):
        self.build({
            DECISION: decision("## Cost\n\n- Read: `hooks/section_reader.py` once per run.\n"),
            "hooks/section_reader.py": "READ = 1\n",
            "hooks/test_other.py": 'OTHER = "other.py"\n',
        })
        rc, out = self.check()
        self.assertEqual(rc, 1, "a file named in a `## Cost` section passed unpinned: hooks/section_reader.py:\n" + out)

    def test_sub_bullet_under_cost_label_is_read(self):
        self.build({
            DECISION: decision("- Cost:\n  - Guard: reads `hooks/bullet_reader.py` once per run.\n"),
            "hooks/bullet_reader.py": "READ = 1\n",
            "hooks/test_other.py": 'OTHER = "other.py"\n',
        })
        rc, out = self.check()
        self.assertEqual(rc, 1, "a file named in a sub-bullet under the Cost label passed unpinned: hooks/bullet_reader.py:\n" + out)

    def test_footer_ends_the_cost_section(self):
        self.build({
            DECISION: decision("## Cost\n\nNo new process.\n\nHome: hooks/footer_reader.py\n"),
            "hooks/footer_reader.py": "READ = 1\n",
            "hooks/test_other.py": 'OTHER = "other.py"\n',
        })
        rc, out = self.check()
        self.assertEqual(rc, 0, "a Home footer after a Cost section was read as cost, naming hooks/footer_reader.py:\n" + out)

    def test_file_named_outside_a_cost_line_is_not_read(self):
        self.build({
            DECISION: decision("Proof: `hooks/proof_reader.py` is read once.\n\n"
                               "Cost: no new process, no file written.\n"),
            "hooks/proof_reader.py": "READ = 1\n",
            "hooks/test_other.py": 'OTHER = "other.py"\n',
        })
        rc, out = self.check()
        self.assertEqual(rc, 0, "a file named on a Proof line was read as a cost line:\n" + out)

    def test_named_test_file_is_its_own_pin(self):
        self.build({
            DECISION: decision("Cost: one run of `hooks/test_named_proof.py`, which proves the call counts.\n"),
            "hooks/test_named_proof.py": "COUNTS = 1\n",
        })
        rc, out = self.check()
        self.assertEqual(rc, 0, "a cost line that names a test file flagged that test file as unpinned:\n" + out)

    def test_bare_name_pinned_by_its_basename(self):
        self.build({
            DECISION: decision("Cost: one read of `reader_bare.py` per run.\n"),
            "hooks/reader_bare.py": "READ = 1\n",
            "hooks/test_bare.py": 'NAME = "reader_bare.py"\n',
        })
        rc, out = self.check()
        self.assertEqual(rc, 0, "a test names reader_bare.py, the bare name a cost line uses, yet the check flagged it:\n" + out)

    def test_one_violation_names_only_its_own_file(self):
        self.build({
            DECISION: decision("Cost: one read of `hooks/pinned_one.py` and `hooks/unpinned_two.py` per run.\n"),
            "hooks/pinned_one.py": "READ = 1\n",
            "hooks/unpinned_two.py": "READ = 2\n",
            "hooks/test_reads.py": 'READER = "hooks/pinned_one.py"\n',
        })
        rc, out = self.check()
        self.assertEqual(rc, 1, "hooks/unpinned_two.py is named by a cost line and no test mentions it, so the check passed it:\n" + out)
        self.assertIn("hooks/unpinned_two.py", out, "the failure does not name the unpinned file:\n" + out)
        self.assertNotIn("hooks/pinned_one.py", out, "the failure names a file a test pins, so it reports the wrong cause:\n" + out)


if __name__ == "__main__":
    unittest.main()
