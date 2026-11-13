#!/usr/bin/env python3
"""The files a rule anchor may sit in, one list for every test case that names them.

Imported by lint/test_rule_audit.py, lint/test_check_ruling_kind.py, lint/test_check_glossary.py and
lint/test_hook_catalog.py. Run on its own, it checks the list against the repo and rule_audit.RULE_FILES.

DESTINATIONS are the files a rule moves into when it leaves CLAUDE.md. Each one must be read as a
rule file: an anchor there is seen by the audit, a Home may name it, a glossary home may name it,
and the records page lists it. CLAUDE.md is not here, because every case already reads it.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rule_audit  # noqa: E402  the one home of the rule file list (RULE_FILES)

DESTINATIONS = (
    "skills/waiting-page/SKILL.md",
    "skills/fresh-prose/SKILL.md",
    "skills/design-review/SKILL.md",
    ".claude/rules/hooks.md",
)

# The RULE_FILES entries that are not destinations: CLAUDE.md (above), and the output style, which holds the
# style's own rules and is not a file a rule moves into.
NOT_DESTINATIONS = ("CLAUDE.md", "output-styles/shiv-stylisms.md")


def _as_paths(paths):
    """The paths with "/" separators, as DESTINATIONS spells them."""
    return {p.replace(os.sep, "/") for p in paths}


class DestinationsTests(unittest.TestCase):
    """The list names real rule files, and RULE_FILES is the list plus the NOT_DESTINATIONS entries."""

    def test_every_destination_is_a_file_in_the_repo(self):
        gone = [rel for rel in DESTINATIONS if not os.path.isfile(os.path.join(rule_audit.ROOT, rel))]
        self.assertEqual(gone, [], "not a file in the repo: " + ", ".join(gone))

    def test_every_destination_is_in_rule_files(self):
        outside = sorted(set(DESTINATIONS) - _as_paths(rule_audit.RULE_FILES))
        self.assertEqual(outside, [], "not in rule_audit.RULE_FILES: " + ", ".join(outside))

    def test_rule_files_has_no_entry_the_list_lacks_beyond_the_named_two(self):
        lacks = sorted(_as_paths(rule_audit.RULE_FILES) - set(DESTINATIONS))
        self.assertEqual(lacks, sorted(NOT_DESTINATIONS),
                         "rule_audit.RULE_FILES has entries the list lacks: " + ", ".join(lacks))


if __name__ == "__main__":
    unittest.main()
