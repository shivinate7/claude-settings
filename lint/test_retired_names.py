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
"""
import os
import shutil
import subprocess
import sys
import tempfile
import tokenize
import unittest

import _test_temp  # test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)
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


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    if "--repo" in sys.argv:
        i = sys.argv.index("--repo")
        RetiredNames.repo = sys.argv[i + 1]
        del sys.argv[i:i + 2]
    unittest.main()
