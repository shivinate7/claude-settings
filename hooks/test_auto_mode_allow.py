#!/usr/bin/env python3
"""Suite for settings.json's autoMode block. Run: python3 hooks/test_auto_mode_allow.py -v

Claude Code's auto-mode classifier reads autoMode from ~/.claude/settings.json, which install.sh
links or copies from this repo's settings.json. Its built-in "Git Destructive" rule re-asked the
owner about a branch delete after the archive push that guard_branch_worktree's remedy hands over
(decision archived-branch-delete-allowed). This suite pins:
- autoMode.allow keeps the built-in exceptions ("$defaults"), and no autoMode list drops its own.
- One allow entry quotes every command in the guard's remedy verbatim, read from
  BRANCH_DELETE_DENY_REASON itself, so a change to the remedy fails here until the entry follows.
"""
import json
import os
import re
import sys
import unittest

HOOKS = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HOOKS)
sys.path.insert(0, HOOKS)

import guard_branch_worktree  # noqa: E402

LISTS = ("environment", "allow", "soft_deny", "hard_deny")


def auto_mode():
    with open(os.path.join(REPO_ROOT, "settings.json"), encoding="utf-8") as handle:
        return json.load(handle).get("autoMode", {})


def remedy_commands():
    """Every backticked span of the remedy: the archive push, the delete, the fallback name."""
    return re.findall(r"`([^`]+)`", guard_branch_worktree.BRANCH_DELETE_DENY_REASON)


def archive_entry(allow):
    hits = [e for e in allow if e.startswith("Archived Branch Delete:")]
    return hits[0] if len(hits) == 1 else None


class AutoModeKeepsTheBuiltInRules(unittest.TestCase):
    def test_allow_list_keeps_defaults(self):
        self.assertIn("$defaults", auto_mode().get("allow", []))

    def test_no_list_drops_its_defaults(self):
        block = auto_mode()
        dropped = [k for k in LISTS if k in block and "$defaults" not in block[k]]
        self.assertFalse(dropped, "autoMode lists set without $defaults: %r" % dropped)


class ArchivedBranchDeleteIsAllowed(unittest.TestCase):
    def test_one_entry_names_the_archived_delete(self):
        self.assertIsNotNone(archive_entry(auto_mode().get("allow", [])),
                             "need exactly one 'Archived Branch Delete:' entry in autoMode.allow")

    def test_entry_quotes_every_remedy_command(self):
        entry = archive_entry(auto_mode().get("allow", [])) or ""
        commands = remedy_commands()
        self.assertGreaterEqual(len(commands), 2, "remedy lost its commands: %r" % commands)
        missing = [c for c in commands if "`%s`" % c not in entry]
        self.assertFalse(missing, "allow entry does not quote the remedy's %r" % missing)

    def test_entry_never_covers_an_archive_ref(self):
        entry = archive_entry(auto_mode().get("allow", [])) or ""
        self.assertRegex(entry, r"Never covers[^.]*`archive/`")


if __name__ == "__main__":
    unittest.main()
