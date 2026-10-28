#!/usr/bin/env python3
"""No tracked file keeps a name that plan o13 retired (one word per meaning). Standard library only.

    python3 lint/test_retired_names.py [--repo DIR]     # DIR defaults to this script's repo

Each name below is an exact old file name, record slug, rule anchor, identifier, log value or
message of groups 1 and 5 to 9 of the plan: guard and check, grant and override, record, finding and
safety hole, refuse, round.
Each is distinctive, so a whole-word match in a tracked file is the old name coming back. This
file, GLOSSARY.md, whose "Not" cells list them, and the generated docs/records.md are the exceptions. A retired word in plain
prose ("the test will pass") is a reviewer's call, not this test's. The widened glossary check will replace this list.
"""
import os
import subprocess
import sys
import unittest

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
}


def hits(repo, name):
    """Tracked files that hold name as a whole word, any case, less the exceptions. None when git
    cannot run."""
    run = subprocess.run(["git", "-C", repo, "grep", "-l", "-i", "-w", "-F", "-e", name, "--", ".", ":!" + SELF,
                          ":!" + GLOSSARY, ":!" + RECORDS_PAGE],
                         capture_output=True, encoding="utf-8", errors="replace")
    if run.returncode not in (0, 1):  # 1 means no match; anything else is no reading
        return None
    return [p for p in run.stdout.splitlines() if p]


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


if __name__ == "__main__":
    if "--repo" in sys.argv:
        i = sys.argv.index("--repo")
        RetiredNames.repo = sys.argv[i + 1]
        del sys.argv[i:i + 2]
    unittest.main()
