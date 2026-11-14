#!/usr/bin/env python3
"""Cases for lint/check_ruling_claims.py: a line that names an owner ruling needs a record behind it.
Standard library only.

    python3 lint/test_check_ruling_claims.py

Claims. A time claim carries a date (`YYYY-MM-DD H:MM`, or `Mon D H:MM` with an optional comma) and follows `owner ruling`,
`owner's ruling` or `ruled at`. A bare time is refused whatever the records hold. An id claim (a kebab slug of two or
more words) is read in backticks, after `ruling:`, after `owner ruling` or `decision`, or after a capitalised `Ruling`
or `RULING` that starts a line. A bare lowercase `ruling` followed by a word is prose, not a claim. A claim split across
two lines is read joined, and reported on its first line.

Backing. A dated time is backed by a record that holds its date and its time on one line: a decision record, CLAUDE.md,
or a rulings entry's `at` (its date and time as written in its own zone). An id is backed by a decision file stem, a
rulings entry `id`, or a CLAUDE.md rule marker. A line with `no record: <reason>` passes.

Each case runs the check as a subprocess on a fixture tree under this run's folder (test-temp-standard). A run passes
--root and --rulings-dir, except the store case, so no case reads origin/roadmap. A subtest starts its own tree, so one
subtest's record cannot back another subtest's claim.

RULING_CLAIMS_UNDER_TEST names the script under test (default: lint/check_ruling_claims.py).
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
# passes this file's own lines. The fixture text the cases write has no such marker, so the check reads it.
UNDATED = (
    "owner ruling 14:19 CST",  # no record: test fixture
    "owner's ruling 14:19 CST",  # no record: test fixture
    "Owner Ruling 14:19 CDT",  # no record: test fixture
)
DATED = "owner ruling 2026-11-13 14:19 CST"  # no record: test fixture
BARE_FORMS = (
    "owner ruling at 23:58",  # no record: test fixture
    "owner ruling, 23:58 CST",  # no record: test fixture
    "Owner ruling (23:58 CST)",  # no record: test fixture
    "owner ruling of 23:58",  # no record: test fixture
    "owner's ruling 23:58",  # no record: test fixture
    "ruled at 23:58",  # no record: test fixture
    "owner ruling 23.58",  # no record: test fixture
)
DATED_FORMS = (
    "owner ruling 2026-11-13 23:58 CST",  # no record: test fixture
    "owner ruling, 2026-11-13 23:58 CST",  # no record: test fixture
    "Owner ruling (2026-11-13 23:58 CST)",  # no record: test fixture
    "owner ruling of 2026-11-13 23:58",  # no record: test fixture
    "owner's ruling 2026-11-13 23:58",  # no record: test fixture
    "ruled at 2026-11-13 23:58",  # no record: test fixture
    "owner ruling 2026-11-13 23.58",  # no record: test fixture
)
ID_FORMS = (
    ("Ruling past-ruling-judge", "past-ruling-judge"),  # no record: test fixture
    ("RULING x-y", "x-y"),  # no record: test fixture
    ("ruling: x-y", "x-y"),  # no record: test fixture
    ("ruling `x-y`", "x-y"),  # no record: test fixture
    ("owner ruling past-ruling-judge", "past-ruling-judge"),  # no record: test fixture
    ("decision past-ruling-judge", "past-ruling-judge"),  # no record: test fixture
)
CTRL_FORM = "ruling `past-ruling-judge`"  # no record: test fixture
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

    def run_check(self, *args, rulings=None, root=None, store=True):
        """(exit code, output) of one check run. Its root and rulings store are this subtest's unless named.
        store=False passes no --rulings-dir, so the check reads the store of --root."""
        cmd = [sys.executable, MODULE, "--root", root or self.root]
        if store:
            cmd += ["--rulings-dir", rulings or self.rulings]
        cmd += list(args)
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

    def test_01_time_claim_without_a_date_is_refused__mutant_backs_any_clock(self):
        for claim in UNDATED:
            with self.subTest(claim=claim):
                self.fresh_tree()
                self.put("brief.md", brief(claim))
                rc, out = self.run_check("brief.md")
                self.assertEqual(rc, 1, "undated time claim: want exit 1, got %d\n%s" % (rc, out))
                self.assertIn("brief.md:3", out, "refusal does not name brief.md:3\n%s" % out)
                self.assertIn("14:19", out, "refusal does not print the claim\n%s" % out)
        with self.subTest("a decision record carries the bare time 14:19"):
            self.fresh_tree()
            self.put("docs/decisions/time-note.md", "# Time note\n\nDecided at 14:19 CST.\n")
            self.put("brief.md", brief(UNDATED[0]))
            rc, out = self.run_check("brief.md")
            self.assertEqual(rc, 1, "bare time backed by a decision record: want exit 1, got %d\n%s" % (rc, out))
        with self.subTest("CLAUDE.md carries the bare time 14:19"):
            self.fresh_tree()
            self.put("CLAUDE.md", "# Rules\n\nDecided at 14:19 CST.\n")
            self.put("brief.md", brief(UNDATED[0]))
            rc, out = self.run_check("brief.md")
            self.assertEqual(rc, 1, "bare time backed by CLAUDE.md: want exit 1, got %d\n%s" % (rc, out))

    def test_02_dated_time_claim_backed_by_a_same_line_record_passes__mutant_backs_time_alone(self):
        cases = (
            ("exact", DATED, "Decided 2026-11-13 14:19 CST.\n"),
            ("zone ignored", "owner ruling 2026-11-13 14:19 CDT", "Decided 2026-11-13 14:19 CST.\n"),  # no record: test fixture
            ("leading zero ignored", "owner ruling 2026-11-13 9:05 CST", "Decided 2026-11-13 09:05.\n"),  # no record: test fixture
            ("Mon D with comma", "owner ruling Nov 13, 19:53 CST", "Decided Nov 13, 19:53 CST.\n"),  # no record: test fixture
            ("Mon D without comma", "owner ruling Nov 13 19:53 CST", "Decided Nov 13 19:53 CST.\n"),  # no record: test fixture
        )
        for name, claim, record in cases:
            with self.subTest(name):
                self.fresh_tree()
                self.put("docs/decisions/time-note.md", "# Time note\n\n" + record)
                self.put("brief.md", brief(claim))
                rc, out = self.run_check("brief.md")
                self.assertEqual(rc, 0, "dated claim backed by a same-line record: want exit 0, got %d\n%s"
                         % (rc, out))
        controls = (
            ("date and time on different lines", DATED, "2026-11-13\nDecided at 14:19 CST.\n"),
            ("wrong date, same time", DATED, "Decided 2026-11-14 14:19 CST.\n"),
        )
        for name, claim, record in controls:
            with self.subTest(name):
                self.fresh_tree()
                self.put("docs/decisions/time-note.md", "# Time note\n\n" + record)
                self.put("brief.md", brief(claim))
                rc, out = self.run_check("brief.md")
                self.assertEqual(rc, 1, "record that does not hold date and time on one line backed the claim: "
                         "want exit 1, got %d\n%s" % (rc, out))
        with self.subTest("full size: the match is the last of 301 records"):
            self.fresh_tree()
            for n in range(300):
                self.put("docs/decisions/rec-%03d.md" % n, "# Note %d\n\nNothing dated.\n" % n)
            self.put("docs/decisions/rec-300.md", "# Last\n\nDecided 2026-11-13 14:19 CST.\n")
            self.put("brief.md", brief(DATED))
            rc, out = self.run_check("brief.md")
            self.assertEqual(rc, 0, "dated claim not backed by the last of 301 records: want exit 0, got %d\n%s"
                             % (rc, out))

    def test_03_dated_time_claim_backed_by_rulings_at_or_claude_md__mutant_drops_at_or_claude_md(self):
        with self.subTest("rulings entry at carries the date and time"):
            self.fresh_tree()
            self.put("roadmap/rulings/claim-cites-record.json", RULING_ENTRY)
            self.put("brief.md", brief(DATED))
            rc, out = self.run_check("brief.md", rulings=os.path.join(self.root, "roadmap", "rulings"))
            self.assertEqual(rc, 0, "dated claim backed by a rulings entry at: want exit 0, got %d\n%s" % (rc, out))
        with self.subTest("CLAUDE.md carries the date and time on one line"):
            self.fresh_tree()
            self.put("CLAUDE.md", "# Rules\n\nDecided 2026-11-13 14:19 CST.\n")
            self.put("brief.md", brief(DATED))
            rc, out = self.run_check("brief.md")
            self.assertEqual(rc, 0, "dated claim backed by CLAUDE.md: want exit 0, got %d\n%s" % (rc, out))
        with self.subTest("control: rulings entry at with another time"):
            self.fresh_tree()
            self.put("roadmap/rulings/claim-cites-record.json", RULING_ENTRY.replace("14:19", "14:20"))
            self.put("brief.md", brief(DATED))
            rc, out = self.run_check("brief.md", rulings=os.path.join(self.root, "roadmap", "rulings"))
            self.assertEqual(rc, 1, "rulings entry at 14:20 backed a 14:19 claim: want exit 1, got %d\n%s"
                             % (rc, out))
        with self.subTest("control: rulings entry at with another date"):
            self.fresh_tree()
            self.put("roadmap/rulings/claim-cites-record.json", RULING_ENTRY.replace("2026-11-13", "2026-11-14"))
            self.put("brief.md", brief(DATED))
            rc, out = self.run_check("brief.md", rulings=os.path.join(self.root, "roadmap", "rulings"))
            self.assertEqual(rc, 1, "rulings entry at 2026-11-14 backed a 2026-11-13 claim: want exit 1, got %d\n%s"
                             % (rc, out))

    def test_04_id_claim_forms_are_read_and_backed_by_stem_marker_or_rulings_id__mutant_reads_bare_prose(self):
        for form, ident in ID_FORMS:
            with self.subTest(form=form):
                self.fresh_tree()
                self.put("brief.md", "Lane brief.\n%s\n" % form)
                rc, out = self.run_check("brief.md")
                self.assertEqual(rc, 1, "unbacked id claim: want exit 1, got %d\n%s" % (rc, out))
                self.assertIn("brief.md:2", out, "refusal does not name brief.md:2\n%s" % out)
                self.fresh_tree()
                self.put("docs/decisions/%s.md" % ident, "# Judge\n\nDecided.\n")
                self.put("brief.md", "Lane brief.\n%s\n" % form)
                rc, out = self.run_check("brief.md")
                self.assertEqual(rc, 0, "id claim backed by a decision file stem: want exit 0, got %d\n%s"
                                 % (rc, out))
        with self.subTest("backed by a CLAUDE.md rule marker"):
            self.fresh_tree()
            self.put("CLAUDE.md", "# Rules\n\nJudge it. <!-- rule:x-y -->\n")
            self.put("brief.md", "Lane brief.\n%s\n" % ID_FORMS[3][0])
            rc, out = self.run_check("brief.md")
            self.assertEqual(rc, 0, "id claim backed by a CLAUDE.md rule marker: want exit 0, got %d\n%s" % (rc, out))
        with self.subTest("backed by a rulings entry id"):
            self.fresh_tree()
            self.put("rulings/x-y.json", RULING_ENTRY.replace("claim-cites-record", "x-y"))
            self.put("brief.md", "Lane brief.\n%s\n" % ID_FORMS[3][0])
            rc, out = self.run_check("brief.md")
            self.assertEqual(rc, 0, "id claim backed by a rulings entry id: want exit 0, got %d\n%s" % (rc, out))
        controls = (
            ("another decision stem", {"docs/decisions/other-ruling-judge.md": "# Other\n"}),
            ("a decision body names the id, stem differs", {"docs/decisions/other.md": "# Other\n\npast-ruling-judge\n"}),
            ("a CLAUDE.md marker for another id", {"CLAUDE.md": "# Rules\n\n<!-- rule:other-ruling-judge -->\n"}),
        )
        for name, files in controls:
            with self.subTest(name):
                self.fresh_tree()
                for rel, text in files.items():
                    self.put(rel, text)
                self.put("brief.md", "Lane brief.\n%s\n" % CTRL_FORM)
                rc, out = self.run_check("brief.md")
                self.assertEqual(rc, 1, "id claim backed by a record for another id: want exit 1, got %d\n%s"
                                 % (rc, out))

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
        self.put("lint/thing.js", "// ruling `claim-cites-record`\n")  # no record: test fixture
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
            ("tool.py", 'x = "owner ruling 2026-11-13 14:19 CST"\n'),  # no record: test fixture
            ("tool.js", 'const s = "see // ruling `claim-cites-record`";\n'),  # no record: test fixture
            ("tool.js", 'const c = "/* ruling `claim-cites-record` */";\n'),  # no record: test fixture
            ("tool.py", "# Don't: owner ruling 14:19 CST\n"),  # no record: test fixture
            ("page.html", "<p>Don't: ruling `claim-cites-record`</p>\n"),  # no record: test fixture
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
             "owner ruling 2026-11-13 14:19 CST no record: the lane's own call, not yet ruled\n", 0),  # no record: test fixture
            ("id claim, reason given", "ruling `claim-cites-record` no record: pending the owner\n", 0),  # no record: test fixture
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
            "ruling fb-1458-1",
            "ruling fb-1041-2",
            "ruling out-of-scope work",
            "the ruling per-lane applies",
            "a ruling re-pointed",
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
            self.put("brief.md", brief(UNDATED[0]))
            rc, out = self.run_check("--brief", "brief.md")
            self.assertEqual(rc, 1, "untracked brief with a claim: want exit 1, got %d\n%s" % (rc, out))
            self.assertIn("brief.md:3", out, "refusal does not name brief.md:3\n%s" % out)
        with self.subTest("brief committed on main and unchanged"):
            self.fresh_tree()
            self.start_repo({"brief.md": brief(UNDATED[0])})
            self.assertEqual(self.diff_of("brief.md"), "", "scope: the brief is in the diff")
            rc, out = self.run_check("--brief", "brief.md")
            self.assertEqual(rc, 1, "unchanged brief with a claim: want exit 1, got %d\n%s" % (rc, out))
            self.assertIn("brief.md:3", out, "refusal does not name brief.md:3\n%s" % out)
        with self.subTest("dated claim backed by a rulings entry"):
            self.fresh_tree()
            self.put("roadmap/rulings/claim-cites-record.json", RULING_ENTRY)
            self.put("brief.md", brief(DATED))
            rc, out = self.run_check("--brief", "brief.md", rulings=os.path.join(self.root, "roadmap", "rulings"))
            self.assertEqual(rc, 0, "brief claim backed by a rulings entry: want exit 0, got %d\n%s" % (rc, out))
        with self.subTest("two brief files, the second holds the claim"):
            self.fresh_tree()
            self.put("clean.md", CLEAN)
            self.put("bad.md", brief(UNDATED[0]))
            rc, out = self.run_check("--brief", "clean.md", "bad.md")
            self.assertEqual(rc, 1, "second brief with a claim: want exit 1, got %d\n%s" % (rc, out))
            self.assertIn("bad.md:3", out, "refusal does not name bad.md:3\n%s" % out)
        with self.subTest("full size: claim on line 2001"):
            self.fresh_tree()
            self.put("brief.md", CLEAN * 2000 + "Rule: %s.\n" % UNDATED[0])
            rc, out = self.run_check("--brief", "brief.md")
            self.assertEqual(rc, 1, "claim on line 2001 of a brief: want exit 1, got %d\n%s" % (rc, out))
            self.assertIn("brief.md:2001", out, "refusal does not name brief.md:2001\n%s" % out)

    def test_11_claim_wrapped_across_two_lines_is_read_and_reported_on_its_first_line__mutant_reads_lines_alone(self):
        with self.subTest("wrapped, no record"):
            self.fresh_tree()
            self.put("brief.md", "Lane brief.\nRule: owner ruling\n2026-11-13 23:58 CST.\n")  # no record: test fixture
            rc, out = self.run_check("brief.md")
            self.assertEqual(rc, 1, "wrapped dated claim not refused: want exit 1, got %d\n%s" % (rc, out))
            self.assertIn("brief.md:2", out, "refusal does not name the first line brief.md:2\n%s" % out)
        with self.subTest("wrapped, backed by a same-line record"):
            self.fresh_tree()
            self.put("docs/decisions/time-note.md", "# Time note\n\nDecided 2026-11-13 23:58 CST.\n")
            self.put("brief.md", "Lane brief.\nRule: owner ruling\n2026-11-13 23:58 CST.\n")  # no record: test fixture
            rc, out = self.run_check("brief.md")
            self.assertEqual(rc, 0, "wrapped dated claim backed by a record: want exit 0, got %d\n%s" % (rc, out))

    def test_12_bare_forms_are_refused_and_dated_forms_need_a_same_line_record__mutant_misses_the_forms(self):
        with self.subTest("bare forms refused, even with a record carrying 23:58"):
            for claim in BARE_FORMS:
                with self.subTest(claim=claim):
                    self.fresh_tree()
                    self.put("docs/decisions/time-note.md", "# Time note\n\nDecided at 23:58 CST.\n")
                    self.put("brief.md", brief(claim))
                    rc, out = self.run_check("brief.md")
                    self.assertEqual(rc, 1, "bare time claim %r: want exit 1, got %d\n%s" % (claim, rc, out))
        for claim in DATED_FORMS:
            with self.subTest(claim=claim):
                self.fresh_tree()
                self.put("brief.md", brief(claim))
                rc, out = self.run_check("brief.md")
                self.assertEqual(rc, 1, "unbacked dated claim %r: want exit 1, got %d\n%s" % (claim, rc, out))
                self.fresh_tree()
                self.put("docs/decisions/time-note.md", "# Time note\n\nDecided 2026-11-13 23:58 CST.\n")
                self.put("brief.md", brief(claim))
                rc, out = self.run_check("brief.md")
                self.assertEqual(rc, 0, "dated claim %r backed by a same-line record: want exit 0, got %d\n%s"
                                 % (claim, rc, out))

    def test_13_claims_are_refused_when_the_rulings_store_cannot_be_read__mutant_reads_empty_store_as_clear(self):
        for claim in (DATED, UNDATED[0]):
            with self.subTest(claim=claim):
                self.fresh_tree()
                self.put("brief.md", brief(claim))
                rc, out = self.run_check("brief.md", store=False)
                self.assertEqual(rc, 2, "claim present and the rulings store unreadable: want exit 2, got %d\n%s"
                                 % (rc, out))
                self.assertIn("UNKNOWN", out, "unreadable store is not reported as unknown\n%s" % out)


def tearDownModule():
    for folder in _RUN:
        shutil.rmtree(folder, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    unittest.main(verbosity=2)
