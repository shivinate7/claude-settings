#!/usr/bin/env python3
"""No tracked file keeps a name that plan o13 retired (one word per meaning). Standard library only.

    python3 lint/test_retired_names.py [--repo DIR]     # DIR defaults to this script's repo

Each name below is an exact old file name, record slug, rule anchor, identifier, log value or
message of groups 1 and 5 to 9 of the plan: guard and check, grant and override, record, finding and
safety hole, refuse, round.
Each is distinctive, so a whole-word match in a tracked file is the old name coming back. This
file, GLOSSARY.md, whose "Not" cells list them, and the generated docs/records.md are the exceptions. A HISTORY
file may keep its name only on a line whose comment holds the opt-out marker. A retired word in plain
prose ("the test will pass") is a reviewer's call, not this test's. The widened glossary check will replace this list.
RepoRetiredNamesTests scans each tracked text file for the names in RETIRED_PATTERN, so a retired name cannot return
in any file. RepoGlossaryTests checks the real GLOSSARY.md. The ready check runs both, from this file.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tokenize
import unittest

import _test_temp  # test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)
import check_glossary  # the check module: the real GLOSSARY.md cases read its rows() and words()
from check_glossary import OPT_OUT  # the one home of the opt-out marker, a line that holds it is skipped

RUN_FOLDER = _test_temp.run_folder()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SELF = "lint/test_retired_names.py"
GLOSSARY = "GLOSSARY.md"  # its "Not" cells name retired words on purpose
RECORDS_PAGE = "docs/records.md"  # generated; the merge tool rebuilds it from the renamed sources (records-index-at-merge)

# old name -> the name that replaced it
RETIRED = {
    "outcomes-word-covers-named-act": "outcomes-grant-covers-named-act",
    "git-one-entry-per-question": "git-one-record-per-question",
    "verification-never-dry-run-blocklist": "verification-never-dry-run-refusal-list",
    "roles-holes-are-debts": "roles-findings-are-debts-or-notes",
    "owner-override-pass": "owner-override",
    "cite-by-id-blocks-unread-file": "cite-by-id-refuses-unread-file",
    "reply-judge-samples-never-blocks": "reply-judge-samples-never-refuses",
    "git-env-set-denied": "git-env-set-refused",
    "settled-question-check-gap": "settled-question-unchecked",
    "override_pass": "override",
    "set_pass_context": "set_override_context",
    "set_pass_veto": "set_override_veto",
    "_pass_who": "_override_who",
    "never_passed": "never_lifted",
    "OPUS_PASSED": "OPUS_LIFTED",
    '"opus-pass"': '"opus-override"',
    "Override pass:": "Override:",
    "override pass": "override",
    "owner's word": "owner's grant",
    "recovery-must-not-gate-on-its-own-state": "recovery-independent-of-state",
    "gates-job-near-timeout": "checks-job-near-timeout",
    "verification-recovery-not-gated-on-own-state": "verification-recovery-independent-of-state",
    "roles-third-try-steps-up": "roles-third-round-steps-up",
    "merge_gate": "merge_check",
    "outcomes-tests-are-claims": "outcomes-tests-are-statements",
    "ux-claims-are-true": "ux-statements-are-true",
    "measured-claims-no-home": "measured-statements-no-home",
    "roles-sonnet-is-the-default": "roles-model-per-role-table",
    "running_lane_hit": "running_agent_hit",
    "RUNNING_LANE_TOOLS": "RUNNING_AGENT_TOOLS",
    "LANE_TOOLS": "START_TOOLS",
    "Lane kind:": "Designer kind:",
}

# old name -> the tracked file that may keep it, on each line whose comment holds the opt-out marker. The one home of
# the marker is lint/check_glossary.py, which skips the same line. The fixtures quote the old header to refuse it.
# Any other file, or an unmarked line, that holds a retired name is a hit.
HISTORY = {
    "Lane kind:": ("hooks/test_blind_brief.py",),
}


def marked_lines(path):
    """Line numbers of the comments in a Python file that hold OPT_OUT, read by the tokenizer, so a marker inside a
    string marks nothing. A file the tokenizer cannot read has none."""
    try:
        with open(path, "rb") as handle:
            return {tok.start[0] for tok in tokenize.tokenize(handle.readline)
                    if tok.type == tokenize.COMMENT and OPT_OUT in tok.string}
    except (OSError, tokenize.TokenError, SyntaxError):
        return set()


def hits(repo, name):
    """Tracked files that hold name as a whole word, any case, less the exceptions. None when git
    cannot run. A HISTORY file's line is not a hit when its comment holds OPT_OUT."""
    run = subprocess.run(["git", "-C", repo, "grep", "-n", "-i", "-w", "-F", "-e", name, "--", ".", ":!" + SELF,
                          ":!" + GLOSSARY, ":!" + RECORDS_PAGE],
                         capture_output=True, encoding="utf-8", errors="replace")
    if run.returncode not in (0, 1):  # 1 means no match; anything else is no reading
        return None
    marks, found = {}, []
    for line in run.stdout.splitlines():  # path:number:text
        path, _, rest = line.partition(":")
        number = rest.partition(":")[0]
        if path in HISTORY.get(name, ()):
            if path not in marks:
                marks[path] = marked_lines(os.path.join(repo, path))
            if number.isdigit() and int(number) in marks[path]:
                continue
        if path not in found:
            found.append(path)
    return found


class RetiredNames(unittest.TestCase):
    repo = ROOT

    def test_no_retired_name(self):
        found = {}
        for name in RETIRED:
            paths = hits(self.repo, name)
            self.assertIsNotNone(paths, "git grep could not read %s" % self.repo)
            if paths:
                found[name] = paths
        self.assertEqual(found, {}, "retired names still in use (old -> new: %s)" %
                         "; ".join("%s -> %s in %s" % (n, RETIRED[n], ", ".join(p)) for n, p in found.items()))

    def test_no_retired_file_path(self):
        files = subprocess.run(["git", "-C", self.repo, "ls-files"], capture_output=True, encoding="utf-8").stdout
        old = [p for p in files.splitlines() if any(n.strip('"') in p for n in RETIRED if "-" in n or "_" in n)]
        self.assertEqual(old, [], "files still under a retired name")


def tracked(repo):
    """The tracked paths of repo, relative to it."""
    return set(subprocess.run(["git", "-C", repo, "ls-files"], capture_output=True, encoding="utf-8",
                              errors="replace").stdout.splitlines())


def make_repo(files):
    """A git repo in this run's folder that tracks `files` (path -> text). Each case makes its own."""
    repo = tempfile.mkdtemp(prefix="repo-", dir=RUN_FOLDER)
    subprocess.run(["git", "-C", repo, "init", "-q"], check=True)
    for path, text in files.items():
        full = os.path.join(repo, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as handle:
            handle.write(text)
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    return repo


class History(unittest.TestCase):
    def test_every_history_path_is_a_tracked_file(self):
        files = tracked(ROOT)
        for name, paths in HISTORY.items():
            for path in paths:
                self.assertTrue(path in files, "HISTORY exempts %s for %r, and no such file is tracked" % (path, name))


class LineScope(unittest.TestCase):
    OLD = "Lane kind:"
    FILE = "hooks/test_blind_brief.py"

    def test_unmarked_old_header_line_in_its_file_is_a_hit(self):
        repo = make_repo({self.FILE: 'old = brief(header="Lane kind: blind")\n'})
        self.assertTrue(self.FILE in tracked(repo), "the fixture does not track %s" % self.FILE)
        self.assertEqual(hits(repo, self.OLD), [self.FILE])

    def test_marked_old_header_line_in_its_file_is_not_a_hit(self):
        repo = make_repo({self.FILE: 'old = brief(header="Lane kind: blind")  # glossary-ok: quoted to be refused\n'})
        self.assertTrue(self.FILE in tracked(repo), "the fixture does not track %s" % self.FILE)
        self.assertEqual(hits(repo, self.OLD), [])

    def test_marker_inside_a_string_on_one_line_is_not_a_marker(self):
        # A comment opener inside a string opens no comment, so the marker there marks nothing.
        repo = make_repo({self.FILE: 'old = brief(header="Lane kind: blind  # glossary-ok: quoted")\n'})
        self.assertTrue(self.FILE in tracked(repo), "the fixture does not track %s" % self.FILE)
        self.assertEqual(hits(repo, self.OLD), [self.FILE])

    def test_marker_inside_a_multi_line_string_is_not_a_marker(self):
        repo = make_repo({self.FILE: 'doc = """\nold = brief(header="Lane kind: blind")  # glossary-ok: quoted\n"""\n'})
        self.assertTrue(self.FILE in tracked(repo), "the fixture does not track %s" % self.FILE)
        self.assertEqual(hits(repo, self.OLD), [self.FILE])

    def test_lone_quote_in_a_comment_keeps_its_marker(self):
        # Green control: the apostrophe sits in the comment, so the comment still holds the marker.
        repo = make_repo({self.FILE: 'old = "Lane kind: blind"  # don\'t drop this glossary-ok: quoted\n'})
        self.assertTrue(self.FILE in tracked(repo), "the fixture does not track %s" % self.FILE)
        self.assertEqual(hits(repo, self.OLD), [])

    def test_marker_does_not_exempt_another_file(self):
        other = "hooks/other.py"
        repo = make_repo({other: 'old = "Lane kind: blind"  # glossary-ok: quoted to be refused\n'})
        self.assertTrue(other in tracked(repo), "the fixture does not track %s" % other)
        self.assertEqual(hits(repo, self.OLD), [other])


def plural_forms(word):
    """The word with a plural `s`, `es` or `ies` taken off, so gaps, tries and claims reach gap, try and claim."""
    out = {word, word[:-1] if word.endswith("s") else word}
    if word.endswith("es"):
        out.add(word[:-2])
    if word.endswith("ies"):
        out.add(word[:-3] + "y")
    return out


class RepoGlossaryTests(unittest.TestCase):
    def test_repo_glossary_homes_resolve(self):
        """The real GLOSSARY.md: every home resolves. A path list keeps git out of it."""
        r = subprocess.run([sys.executable, check_glossary.__file__, "README.md"], cwd=ROOT,
                           capture_output=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_real_not_names_use_this_sense_only_and_keep_gap_try_claim_plain(self):
        """The real GLOSSARY.md, read through the check's own rows(): each tag is (this sense), and gap,
        try and claim are everyday words, so no "not" name may be one of them."""
        with open(os.path.join(ROOT, "GLOSSARY.md"), encoding="utf-8") as f:
            table = check_glossary.rows(f.read())
        self.assertTrue(table, "GLOSSARY.md has no rows under ## Terms")
        problems = []
        for term, _homes, names in table:
            for name in names:
                if "(" in name and not re.fullmatch(r"[^()]+ \(this sense\)", name):
                    problems.append("row '%s': not name '%s' has a tag other than (this sense)" % (term, name))
                for word in check_glossary.words(name.split(" (")[0]):
                    if plural_forms(word) & {"gap", "try", "claim"}:
                        problems.append("row '%s': not name '%s' holds '%s'; gap, try and claim are plain words"
                                        % (term, name, word))
        self.assertEqual(problems, [], "\n".join(problems))


# retired-names: pattern block begins
# o13 lane B retired these names (GLOSSARY.md rows agent, mutation test, red run, command). Claude
# Code's own names stay: the hook events, `subagent_type`, the CLAUDE_CODE_* settings keys and the
# `subagents/` transcript folder. Two old names stay readable until their end day, each in one file:
# the `--subagent` flag of local_time.py and the `_subagentCapUntil` field of config_watch.py.
RETIRED_PATTERN = (r"(?i)sub-?agent|harness[-_ ]scope|HARNESS_SCOPE|mutation harness|AUTHOR_HARNESS"
                   r"|ask-steps-run-alone|\b(?:ask|count|harmless|background)_steps?\b|\b(?:ask|harmless|chained) steps?\b"
                   r"|roles-one-role-per-worker|output-never-echo-worker-report|worker_transcript"
                   r"|WORKER_FOLDED_KEYS|(?i:red[- ]proof)")
PLATFORM = (r"SubagentStop|SubagentStart|subagent_type|(?:\\u0043|C)LAUDE_CODE_\w+"
            r"|[\"'/`]subagents(?=[\"'/`])|subagents/|SUBAGENT_MODEL")
STAYS = {  # path: the one old name it may still hold, and why
    "hooks/local_time.py": "--subagent",            # read until OLD_FLAG_ENDS
    "hooks/config_watch.py": "_subagentCapUntil",   # read until OLD_NAME_ENDS
    "hooks/test_local_time.py": "--subagent",       # pins the old flag until then
    "hooks/test_config_watch.py": "_subagentCapUntil",
    "testing/skip-locally-fail-in-ci.test.mjs": "Red proof",  # header shared with copies in other repos
    "lint/test_find_copies.py": "Red proof",        # the fixture copy of that header
    "mods/plain-diff/docs/mockup.html": "red proof",  # sample diff text
    # the writer-label alternation of OTHER_WRITER_ROW_RE: the harness writes "Subagent report:". Only this fragment
    # stays, so a bare "subagent" elsewhere in the file still fails.
    "lint/report_guard.py": "agent|subagent|",
}
# retired-names: pattern block ends
# The scan skips the paths in SKIP: an exact file, or a folder (its name ends in /) and every path under it.
SKIP = ("skills/impeccable/", "GLOSSARY.md")  # GLOSSARY.md names the retired words in its "Not" cells, on purpose
BLOCK_BEGIN = "# retired-names: pattern block begins"  # the scan reads this file as data between the two markers
BLOCK_END = "# retired-names: pattern block ends"


def skipped(rel):
    """True for a path the whole-tree scan skips: an exact SKIP file, or a path under a SKIP folder."""
    return any(rel == entry or (entry.endswith("/") and rel.startswith(entry)) for entry in SKIP)


def scanned_lines(rel, lines):
    """(number, text) for each line the scan reads in a tracked file. In this file the lines from BLOCK_BEGIN to
    BLOCK_END are data, and are left out. Each marker must stand alone once, begin before end; otherwise None, a hit,
    so an unpaired marker cannot exempt the rest of the file."""
    if rel != SELF:
        return list(enumerate(lines, 1))
    begin = [n for n, line in enumerate(lines, 1) if line.strip() == BLOCK_BEGIN]
    end = [n for n, line in enumerate(lines, 1) if line.strip() == BLOCK_END]
    if len(begin) != 1 or len(end) != 1 or end[0] < begin[0]:
        return None
    return [(n, line) for n, line in enumerate(lines, 1) if not begin[0] <= n <= end[0]]


def retired_hits(repo):
    """The hits of the whole-tree scan of repo, one text line each: a path, or a numbered line, that holds a retired
    name. None when git cannot list repo."""
    listed = subprocess.run(["git", "-C", repo, "ls-files"], capture_output=True, encoding="utf-8")
    if listed.returncode != 0:
        return None
    retired, platform = re.compile(RETIRED_PATTERN), re.compile(PLATFORM)
    found = []
    for rel in listed.stdout.splitlines():
        if skipped(rel):
            continue
        if retired.search(rel):
            found.append("%s: the path" % rel)
        try:
            with open(os.path.join(repo, rel), encoding="utf-8") as f:
                text = f.read()
        except (OSError, UnicodeDecodeError):
            continue
        text = platform.sub("", text)
        if rel in STAYS:
            text = text.replace(STAYS[rel], "")
        lines = scanned_lines(rel, text.splitlines())
        if lines is None:
            found.append("%s: the pattern block markers are not one begin, then one end" % rel)
            continue
        for number, line in lines:
            hit = retired.search(line)
            if hit:
                found.append("%s:%d: %s" % (rel, number, hit.group(0)))
    return found


class RepoRetiredNamesTests(unittest.TestCase):
    def test_no_retired_name_in_tracked_files(self):
        """Every tracked path and text file, less the SKIP paths and this file's pattern block: no name o13 lane B
        retired, outside the platform's own."""
        found = retired_hits(ROOT)
        self.assertIsNotNone(found, "git ls-files could not list %s" % ROOT)
        self.assertEqual(found, [], "\n".join(found[:40]))


PLANTED = "HARNESS_" "SCOPE"  # a retired name, split so this file's own source holds none in matchable form


class ScanScope(unittest.TestCase):
    """retired_hits reads this file outside its pattern block, and every other tracked file less SKIP. Each case
    plants a name in a scratch repo, so the scan's reach is shown, not assumed."""

    def this_file(self):
        with open(os.path.join(ROOT, SELF), encoding="utf-8") as f:
            return f.read()

    def test_unplanted_copy_of_this_file_is_clean(self):
        repo = make_repo({SELF: self.this_file()})
        self.assertIn(SELF, tracked(repo), "the fixture does not track %s" % SELF)
        self.assertEqual(retired_hits(repo), [])

    def test_name_planted_outside_the_pattern_block_is_named(self):
        text = self.this_file()
        repo = make_repo({SELF: text + '\nNOTE = "%s"\n' % PLANTED})
        self.assertIn(SELF, tracked(repo), "the fixture does not track %s" % SELF)
        self.assertEqual(retired_hits(repo), ["%s:%d: %s" % (SELF, text.count("\n") + 2, PLANTED)])

    def test_name_planted_inside_the_pattern_block_is_not_a_hit(self):
        text = self.this_file()
        planted = text.replace(BLOCK_BEGIN + "\n", BLOCK_BEGIN + '\nNOTE = "%s"\n' % PLANTED, 1)
        self.assertNotEqual(planted, text, "the fixture did not plant the name")
        repo = make_repo({SELF: planted})
        self.assertIn(SELF, tracked(repo), "the fixture does not track %s" % SELF)
        self.assertEqual(retired_hits(repo), [])

    def test_unpaired_block_marker_is_a_hit(self):
        kept = [line for line in self.this_file().splitlines() if line.strip() != BLOCK_END]
        repo = make_repo({SELF: "\n".join(kept) + "\n"})
        self.assertEqual(retired_hits(repo),
                         ["%s: the pattern block markers are not one begin, then one end" % SELF])

    def test_bak_sibling_of_this_file_is_scanned(self):
        repo = make_repo({SELF + ".bak": 'NOTE = "%s"\n' % PLANTED})
        self.assertIn(SELF + ".bak", tracked(repo), "the fixture does not track %s.bak" % SELF)
        self.assertEqual(retired_hits(repo), ["%s.bak:1: %s" % (SELF, PLANTED)])

    def test_skip_entries_match_exact_paths_and_folders_only(self):
        planted = 'NOTE = "%s"\n' % PLANTED
        repo = make_repo({"GLOSSARY.md": planted, "GLOSSARY.md.bak": planted,
                          "skills/impeccable/a.md": planted, "skills/impeccable-old/a.md": planted})
        self.assertIn("GLOSSARY.md.bak", tracked(repo), "the fixture does not track GLOSSARY.md.bak")
        self.assertEqual(retired_hits(repo), ["GLOSSARY.md.bak:1: %s" % PLANTED,
                                              "skills/impeccable-old/a.md:1: %s" % PLANTED])

    def test_marker_pair_in_another_file_is_still_a_hit(self):
        """The markers exempt lines of this file only. A pair around a retired name in README.md is a hit."""
        repo = make_repo({"README.md": "%s\nNOTE = \"%s\"\n%s\n" % (BLOCK_BEGIN, PLANTED, BLOCK_END)})
        self.assertIn("README.md", tracked(repo), "the fixture does not track README.md")
        self.assertEqual(retired_hits(repo), ["README.md:2: %s" % PLANTED])


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    if "--repo" in sys.argv:
        i = sys.argv.index("--repo")
        RetiredNames.repo = sys.argv[i + 1]
        del sys.argv[i:i + 2]
    unittest.main()
