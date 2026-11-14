#!/usr/bin/env python3
"""Cases for lint/check_ruling_claims.py: a line that names an owner ruling needs a record behind it.
Standard library only.

    python3 lint/test_check_ruling_claims.py

The check reads a claim in any text, prose, comment or string alike. A time claim is `owner ruling <H:MM>`, with an
optional zone. An id claim is `ruling <id>`, where <id> is a kebab-case slug of two or more words. A time is backed by
a decision record, CLAUDE.md or a rulings entry. An id is backed by a decision file stem, a rulings entry's `id`, or a
CLAUDE.md rule marker. A line with `no record: <reason>` passes.

Each case runs the check as a subprocess on a fixture tree under this run's folder (test-temp-standard). Every run
passes --root and --rulings-dir, so no case reads origin/roadmap. A subtest starts its own tree, so one subtest's
record cannot back another subtest's claim.

RULING_CLAIMS_UNDER_TEST names the script under test (default: lint/check_ruling_claims.py). Pointed at
lint/red_run_stub_test.py, which exits 0 and prints nothing, each case that expects a refusal or exit 2 fails on its
exit-code assertion, and the clean-pass cases stay green. That is the behavioural red for a new check.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per test run (lint/_test_temp.py)

MODULE = os.path.abspath(os.environ.get("RULING_CLAIMS_UNDER_TEST") or os.path.join(HERE, "check_ruling_claims.py"))
_RUN = []  # this run's folder, made on first use so that importing this file starts nothing


def run_folder():
    """This run's temp folder (test-temp-standard), made on the first call."""
    if not _RUN:
        _RUN.append(_test_temp.run_folder())
    return _RUN[0]


# This file's source holds claim text on purpose. A line that holds claim text also holds `no record:`, so the check
# passes this file's own lines. The fixture text the cases write has no such marker, so the check refuses it.
TIME_CLAIMS = (
    "owner ruling 14:19 CST",  # no record: test fixture
    "owner's ruling 14:19 CST",  # no record: test fixture
    "Owner Ruling 14:19 CDT",  # no record: test fixture
)
ID_CLAIM = "ruling past-ruling-judge"  # no record: test fixture
RULING_ENTRY = ('{"id": "claim-cites-record", "at": "2026-11-13T14:19:00-06:00", '
                '"ruling": "Cite the record.", "source": "test fixture"}\n')
CLEAN = "Lane brief.\n"


def brief(claim):
    """A three-line brief with the claim on line 3."""
    return "Lane brief.\n\nRule: %s.\n" % claim


class RulingClaimsTests(unittest.TestCase):
    def fresh_tree(self):
        """An empty fixture root for one subtest: its own folder and its own empty rulings store."""
        self.root = tempfile.mkdtemp(prefix="rcl_", dir=run_folder())
        self.rulings = os.path.join(self.root, "rulings")
        os.makedirs(self.rulings)

    def put(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def read(self, rel):
        with open(os.path.join(self.root, rel), encoding="utf-8") as f:
            return f.read()

    def run_check(self, *args, rulings=None, root=None):
        """(exit code, output) of one check run. Its root and rulings store are this subtest's unless named."""
        cmd = [sys.executable, MODULE, "--root", root or self.root, "--rulings-dir", rulings or self.rulings, *args]
        r = subprocess.run(cmd, cwd=self.root, capture_output=True, text=True, encoding="utf-8", errors="replace")
        return r.returncode, r.stdout + r.stderr

    def git(self, *args):
        subprocess.run(["git", "-C", self.root, "-c", "user.name=test", "-c", "user.email=test@example.com", *args],
                       check=True, capture_output=True, text=True)

    def start_repo(self, base_files):
        """A fixture repo whose main holds `base_files`, with a change branch checked out."""
        for rel, text in base_files.items():
            self.put(rel, text)
        self.git("init", "-q")
        self.git("symbolic-ref", "HEAD", "refs/heads/main")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        self.git("checkout", "-q", "-b", "change")

    def commit_change(self):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "change")

    def diff_of(self, rel):
        r = subprocess.run(["git", "-C", self.root, "diff", "--unified=0", "main", "--", rel],
                           capture_output=True, text=True, check=True)
        return r.stdout

    def test_01_time_claim_with_no_record_is_refused__mutant_never_refuses(self):
        for claim in TIME_CLAIMS:
            with self.subTest(claim=claim):
                self.fresh_tree()
                self.put("brief.md", brief(claim))
                rc, out = self.run_check("brief.md")
                self.assertEqual(rc, 1, "unbacked time claim: want exit 1, got %d\n%s" % (rc, out))
                self.assertIn("brief.md:3", out, "refusal does not name brief.md:3\n%s" % out)
                self.assertIn("14:19", out, "refusal does not print the claim\n%s" % out)

    def test_02_time_claim_backed_by_a_decision_record_passes__mutant_ignores_docs_decisions(self):
        cases = (
            ("exact time", "owner ruling 14:19 CST", "Decided at 14:19 CST.\n"),  # no record: test fixture
            ("zone ignored", "owner ruling 14:19 CDT", "Decided at 14:19 CST.\n"),  # no record: test fixture
            ("leading zero ignored", "owner ruling 9:05 CST", "Decided at 09:05.\n"),  # no record: test fixture
        )
        for name, claim, record in cases:
            with self.subTest(name):
                self.fresh_tree()
                self.put("docs/decisions/time-note.md", "# Time note\n\n" + record)
                self.put("brief.md", brief(claim))
                rc, out = self.run_check("brief.md")
                self.assertEqual(rc, 0, "time claim backed by a decision record: want exit 0, got %d\n%s"
                                 % (rc, out))
        with self.subTest("full size: the match is the last of 301 records"):
            self.fresh_tree()
            for n in range(300):
                self.put("docs/decisions/rec-%03d.md" % n, "# Note %d\n\nNothing dated.\n" % n)
            self.put("docs/decisions/rec-300.md", "# Last\n\nDecided at 14:19 CST.\n")
            self.put("brief.md", brief(TIME_CLAIMS[0]))
            rc, out = self.run_check("brief.md")
            self.assertEqual(rc, 0, "time claim not backed by the last of 301 decision records: want exit 0, got %d\n%s"
                             % (rc, out))

    def test_03_time_claim_backed_by_rulings_or_claude_md_passes__mutant_drops_rulings_or_claude_md(self):
        with self.subTest("rulings entry carries the time"):
            self.fresh_tree()
            self.put("roadmap/rulings/claim-cites-record.json", RULING_ENTRY)
            self.put("brief.md", brief(TIME_CLAIMS[0]))
            rc, out = self.run_check("brief.md", rulings=os.path.join(self.root, "roadmap", "rulings"))
            self.assertEqual(rc, 0, "time claim backed by a rulings entry: want exit 0, got %d\n%s" % (rc, out))
        with self.subTest("CLAUDE.md carries the time"):
            self.fresh_tree()
            self.put("CLAUDE.md", "# Rules\n\nDecided at 14:19 CST.\n")
            self.put("brief.md", brief(TIME_CLAIMS[0]))
            rc, out = self.run_check("brief.md")
            self.assertEqual(rc, 0, "time claim backed by CLAUDE.md: want exit 0, got %d\n%s" % (rc, out))
        with self.subTest("control: a rulings entry with another time does not back it"):
            self.fresh_tree()
            self.put("roadmap/rulings/claim-cites-record.json", RULING_ENTRY.replace("14:19", "14:20"))
            self.put("brief.md", brief(TIME_CLAIMS[0]))
            rc, out = self.run_check("brief.md", rulings=os.path.join(self.root, "roadmap", "rulings"))
            self.assertEqual(rc, 1, "rulings entry with 14:20 backed a 14:19 claim: want exit 1, got %d\n%s"
                             % (rc, out))

    def test_04_id_claim_backed_by_stem_marker_or_rulings_id__mutant_ignores_slug_arms(self):
        rulings_entry = RULING_ENTRY.replace("claim-cites-record", "past-ruling-judge")
        cases = (
            ("no record", {}, None, 1),
            ("decision file stem", {"docs/decisions/past-ruling-judge.md": "# Judge\n\nDecided.\n"}, None, 0),
            ("CLAUDE.md rule marker", {"CLAUDE.md": "# Rules\n\nJudge it. <!-- rule:past-ruling-judge -->\n"}, None, 0),
            ("rulings entry id", {}, rulings_entry, 0),
            ("control: another decision stem", {"docs/decisions/other-ruling-judge.md": "# Other\n"}, None, 1),
            ("control: a decision body names the id, stem differs",
             {"docs/decisions/other.md": "# Other\n\npast-ruling-judge\n"}, None, 1),
            ("control: a CLAUDE.md marker for another id",
             {"CLAUDE.md": "# Rules\n\n<!-- rule:other-ruling-judge -->\n"}, None, 1),
        )
        for name, files, rulings_text, want in cases:
            with self.subTest(name):
                self.fresh_tree()
                for rel, text in files.items():
                    self.put(rel, text)
                if rulings_text is not None:
                    self.put("rulings/past-ruling-judge.json", rulings_text)
                self.put("brief.md", brief(ID_CLAIM))
                rc, out = self.run_check("brief.md")
                self.assertEqual(rc, want, "id claim, %s: want exit %d, got %d\n%s" % (name, want, rc, out))

    def test_05_base_mode_checks_added_lines_only__mutant_checks_whole_file(self):
        self.fresh_tree()
        self.start_repo({
            "lint/old.py": "# owner ruling 09:05 CST\n",  # no record: test fixture
            "lint/test_thing.py": "import os\n",
        })
        self.assertIn("09:05", self.read("lint/old.py"), "scope: the claim line is not on main")
        self.put("lint/test_thing.py", "import os\nx = 1\n")
        self.commit_change()
        self.assertEqual(self.diff_of("lint/old.py"), "", "scope: the claim line on main is in the diff")
        rc, out = self.run_check("--base", "main")
        self.assertEqual(rc, 0, "a line already on main was checked: want exit 0, got %d\n%s" % (rc, out))
        self.put("lint/test_thing.py", "import os\nx = 1\n# owner ruling 09:05 CST\n")  # no record: test fixture
        self.put("lint/thing.js", "// ruling claim-cites-record\n")  # no record: test fixture
        self.commit_change()
        rc, out = self.run_check("--base", "main")
        self.assertEqual(rc, 1, "an added claim line was not refused under --base: want exit 1, got %d\n%s"
                         % (rc, out))
        self.assertIn("lint/test_thing.py:3", out, "refusal does not name the added test comment\n%s" % out)
        self.assertIn("lint/thing.js:1", out, "refusal does not name the added code comment\n%s" % out)
        self.assertNotIn("lint/old.py", out, "a line already on main was named\n%s" % out)

    def test_06_claims_are_read_inside_strings_and_after_comment_openers__mutant_parses_comments_only(self):
        cases = (
            ("tool.py", 'label = "a # b owner ruling 14:19 CST"\n'),  # no record: test fixture
            ("tool.js", 'const s = "see // ruling claim-cites-record";\n'),  # no record: test fixture
            ("tool.js", 'const c = "/* ruling claim-cites-record */";\n'),  # no record: test fixture
            ("tool.py", "# Don't: owner ruling 14:19 CST\n"),  # no record: test fixture
            ("page.html", "<p>Don't: ruling claim-cites-record</p>\n"),  # no record: test fixture
        )
        for rel, text in cases:
            with self.subTest(rel=rel, text=text):
                self.fresh_tree()
                self.put(rel, text)
                rc, out = self.run_check(rel)
                self.assertEqual(rc, 1, "claim inside a string or after a lone quote not refused: want exit 1, got %d\n%s"
                                 % (rc, out))
                self.assertIn(rel + ":1", out, "refusal does not name %s:1\n%s" % (rel, out))
        with self.subTest("multi-line template literal, added under --base"):
            self.fresh_tree()
            self.start_repo({"note.js": "// base\n"})
            self.put("note.js", "// base\nconst note = `\n  owner ruling 14:19 CST\n`;\n")  # no record: test fixture
            self.commit_change()
            rc, out = self.run_check("--base", "main")
            self.assertEqual(rc, 1, "claim on line 3 of a template literal not refused: want exit 1, got %d\n%s"
                             % (rc, out))
            self.assertIn("note.js:3", out, "refusal does not name note.js:3\n%s" % out)

    def test_07_no_record_marker_passes_only_with_a_reason__mutant_exempts_bare_marker(self):
        cases = (
            ("time claim, reason given",
             "owner ruling 14:19 CST no record: the lane's own call, not yet ruled\n", 0),  # no record: test fixture
            ("id claim, reason given", "ruling claim-cites-record no record: pending the owner\n", 0),  # no record: test fixture
            ("bare no record", "owner ruling 14:19 CST no record\n", 1),  # no record: test fixture
            ("empty reason", "owner ruling 14:19 CST no record:\n", 1),  # no record: test fixture
        )
        for name, text, want in cases:
            with self.subTest(name):
                self.fresh_tree()
                self.put("lane.md", text)
                rc, out = self.run_check("lane.md")
                self.assertEqual(rc, want, "%s: want exit %d, got %d\n%s" % (name, want, rc, out))

    def test_08_words_that_are_not_claims_pass__mutant_matches_the_bare_word(self):
        cases = (
            "We are ruling out the old branch.",
            "The ruling holds for this lane.",
            "See ruling 5 in the thread.",
            "The owner ruling applies to this lane.",
            "Rule: ruling foo.",
            "A ruling-based design.",
            "",
        )
        for text in cases:
            with self.subTest(text=text):
                self.fresh_tree()
                self.put("brief.md", text + "\n" if text else "")
                rc, out = self.run_check("brief.md")
                self.assertEqual(rc, 0, "a non-claim was refused: want exit 0, got %d\n%s" % (rc, out))

    def test_09_unreadable_input_exits_2_and_names_it__mutant_exits_0_on_error(self):
        with self.subTest("missing file"):
            self.fresh_tree()
            rc, out = self.run_check("no-such-file-rcl.md")
            self.assertEqual(rc, 2, "missing file: want exit 2, got %d\n%s" % (rc, out))
            self.assertIn("no-such-file-rcl.md", out, "missing file is not named\n%s" % out)
        with self.subTest("missing --brief file"):
            self.fresh_tree()
            rc, out = self.run_check("--brief", "no-such-brief-rcl.md")
            self.assertEqual(rc, 2, "missing brief: want exit 2, got %d\n%s" % (rc, out))
            self.assertIn("no-such-brief-rcl.md", out, "missing brief is not named\n%s" % out)
        with self.subTest("root folder missing"):
            self.fresh_tree()
            self.put("brief.md", CLEAN)
            bad = os.path.join(self.root, "no-such-root-rcl")
            rc, out = self.run_check("brief.md", root=bad)
            self.assertEqual(rc, 2, "missing root: want exit 2, got %d\n%s" % (rc, out))
            self.assertIn("no-such-root-rcl", out, "missing root is not named\n%s" % out)
        with self.subTest("root names a file"):
            self.fresh_tree()
            self.put("brief.md", CLEAN)
            self.put("not-a-root-rcl.txt", "x\n")
            rc, out = self.run_check("brief.md", root=os.path.join(self.root, "not-a-root-rcl.txt"))
            self.assertEqual(rc, 2, "root that is a file: want exit 2, got %d\n%s" % (rc, out))
            self.assertIn("not-a-root-rcl.txt", out, "root that is a file is not named\n%s" % out)

    def test_10_brief_mode_checks_the_whole_brief__mutant_checks_only_diff_lines(self):
        with self.subTest("untracked brief, no git"):
            self.fresh_tree()
            self.put("brief.md", brief(TIME_CLAIMS[0]))
            rc, out = self.run_check("--brief", "brief.md")
            self.assertEqual(rc, 1, "untracked brief with a claim: want exit 1, got %d\n%s" % (rc, out))
            self.assertIn("brief.md:3", out, "refusal does not name brief.md:3\n%s" % out)
        with self.subTest("brief committed on main and unchanged"):
            self.fresh_tree()
            self.start_repo({"brief.md": brief(TIME_CLAIMS[0])})  # no record: test fixture
            self.assertEqual(self.diff_of("brief.md"), "", "scope: the brief is in the diff")
            rc, out = self.run_check("--brief", "brief.md")
            self.assertEqual(rc, 1, "unchanged brief with a claim: want exit 1, got %d\n%s" % (rc, out))
            self.assertIn("brief.md:3", out, "refusal does not name brief.md:3\n%s" % out)
        with self.subTest("backed by a rulings entry"):
            self.fresh_tree()
            self.put("roadmap/rulings/claim-cites-record.json", RULING_ENTRY)
            self.put("brief.md", brief(TIME_CLAIMS[0]))
            rc, out = self.run_check("--brief", "brief.md", rulings=os.path.join(self.root, "roadmap", "rulings"))
            self.assertEqual(rc, 0, "brief claim backed by a rulings entry: want exit 0, got %d\n%s" % (rc, out))
        with self.subTest("two brief files, the second holds the claim"):
            self.fresh_tree()
            self.put("clean.md", CLEAN)
            self.put("bad.md", brief(TIME_CLAIMS[0]))
            rc, out = self.run_check("--brief", "clean.md", "bad.md")
            self.assertEqual(rc, 1, "second brief with a claim: want exit 1, got %d\n%s" % (rc, out))
            self.assertIn("bad.md:3", out, "refusal does not name bad.md:3\n%s" % out)
        with self.subTest("full size: claim on line 2001"):
            self.fresh_tree()
            self.put("brief.md", CLEAN * 2000 + "Rule: %s.\n" % TIME_CLAIMS[0])
            rc, out = self.run_check("--brief", "brief.md")
            self.assertEqual(rc, 1, "claim on line 2001 of a brief: want exit 1, got %d\n%s" % (rc, out))
            self.assertIn("brief.md:2001", out, "refusal does not name brief.md:2001\n%s" % out)


def tearDownModule():
    for folder in _RUN:
        shutil.rmtree(folder, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    unittest.main(verbosity=2)
