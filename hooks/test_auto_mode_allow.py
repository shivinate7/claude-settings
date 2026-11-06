#!/usr/bin/env python3
"""Suite for settings.json's autoMode block. Run: python3 hooks/test_auto_mode_allow.py -v

Claude Code's auto-mode classifier reads autoMode from ~/.claude/settings.json, which install.sh
links or copies from this repo's settings.json. Its built-in "Git Destructive" rule re-asked the
owner about a branch delete after the archive push that guard_branch_worktree's remedy hands over
(decision auto-mode-owner-acts). This suite pins:
- autoMode.allow keeps the built-in exceptions ("$defaults"), and no autoMode list drops its own.
- One allow entry quotes every command in the guard's remedy verbatim, read from
  BRANCH_DELETE_DENY_REASON itself, so a change to the remedy fails here until the entry follows.
- One "Owner PR Housekeeping:" entry quotes the measured PR close, names the bound shivinate7,
  and never covers merge, approve, branch delete, force push, a base branch change, or a repo
  outside it (decision auto-mode-owner-acts). Its Covers text names the visible conversation
  and the batch's integration pull request.
- One "Owner Session Message:" entry quotes mcp__claude-code-remote__send_message. Its Covers text
  lets a session tagged cs-build:coordinator send a batch runner it created (tags
  cs-build:batch-runner and the coordinator's own cs-repo: tag) a merge go for a named pull
  request, because decision standing-merge-grant has the runner run every merge under the
  coordinator's grant. Its Never covers names permissions, settings, override, a merge ask to any
  other session or from a session that is not a coordinator, and a request to approve a pull
  request (decision auto-mode-owner-acts).
  Its Covers text names the session that started this one as a target.
  Its Covers text lets a message that asks for no act (pull request number, batch heads) through.
- One "Relayed Grant:" entry quotes page_grant.py's COMMAND and COUNTED_LINE, read from the
  checker itself, and its Never covers names each act in RELAYED_REFUSED (decision
  relayed-grant-read-from-page).
AUTO_MODE_SETTINGS names another settings file to read (default: this repo's settings.json), so the
same cases run against a copy with a clause removed and show red there.
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

sys.path.insert(0, os.path.join(REPO_ROOT, "skills", "waiting-page"))
import page_grant  # noqa: E402

LISTS = ("environment", "allow", "soft_deny", "hard_deny")
ARCHIVE = "Archived Branch Delete:"
OWNER_PR = "Owner PR Housekeeping:"
RELAYED = "Relayed Grant:"
OWNER_MESSAGE = "Owner Session Message:"
PR_CLOSE = "gh api -X PATCH repos/shivinate7/joyous/pulls/54 -f state=closed"
SEND_MESSAGE = "mcp__claude-code-remote__send_message"
# (name, case-insensitive pattern) for each act an entry's "Never covers" sentence must name.
PR_REFUSED = (("merge", "merg"), ("approve", "approv"), ("branch delete", "branch"),
              ("force push", "force[- ]push"),
              ("another owner or outside", "another owner|outside"))
MESSAGE_REFUSED = (("permissions", "permission"), ("settings", "setting"),
                   ("override", "override"),
                   ("merge ask to any other session", "merge ask to any other session"),
                   ("approve", "approv"))
PR_EXTRA_REFUSED = (("--delete-branch", "--delete-branch"), ("auto-merge", "auto[- ]merge"))
MESSAGE_EXTRA_REFUSED = (("posted_to_shared_channel", "posted_to_shared_channel"),)
# (name, case-insensitive pattern) for each term an entry names before its "Never covers" sentence.
PR_SCOPE = (("owner", "owned by shivinate7"),
            ("coordinator or batch runner", "coordinator or batch runner"),
            ("replaced, empty or batched", "replaced, empty or batched"))
MESSAGE_SCOPE = (("own account", "own account"), ("Remote Control", "Remote Control"))
# The Covers text names the coordinator's merge go to its batch runner; the Never covers names the
# merge asks that stay refused.
MERGE_GO_SCOPE = (("sender tag cs-build:coordinator", "`cs-build:coordinator` may send"),
                  ("cs-build:batch-runner", "cs-build:batch-runner"),
                  ("batch runner it created", "batch runner it created"),
                  ("cs-repo:", "cs-repo:"), ("coordinator's own cs-repo:", "own `cs-repo:`"),
                  ("standing-merge-grant", "standing-merge-grant"), ("merge go", "merge go"),
                  ("named PR", "for a named PR"))
# Each act the Relayed Grant entry's "Never covers" sentence must name (decision relayed-grant-read-from-page).
RELAYED_REFUSED = (("peer session's message", "peer session's message"), ("page comment", "a page comment"),
                   ("lastAnswer", "lastAnswer"), ("reply", "reply"),
                   ("answer for another item", "an answer for another item"), ("choice none", "choice none"),
                   ("task answer", "any task answer"), ("time with no zone", "time has no zone"),
                   ("older than added", "an answer older than the item's added"),
                   ("closed item", "a closed item"), ("arbiter overturn only", r"except an arbiter overturn"),
                   ("permissions", "permissions"), ("settings", "settings"), ("overrides", "overrides"),
                   ("no counted line", "no `counted` line in this session"))
MERGE_GO_REFUSED = (("any other session", "any other session"),
                    ("not a coordinator", "not a coordinator"))
# The Covers text names the session that started this one, and the no-act report it lets through.
MESSAGE_TARGET = (("the session that started this one", "the session that started this one"),)
MESSAGE_REPORT = (("asks for no act", "asks for no act"), ("pull request number", "pull request number"),
                  ("batch heads", "batch heads"))
MESSAGE_QUESTION = (("a question about state", "a question about state"),)
MESSAGE_REQUEST = (("ready to merge", "ready to merge"), ("however phrased", "however phrased"))
MESSAGE_ONLY = (("only informs and asks for no act", "only informs and asks for no act"),)
MESSAGE_OUTSIDE = (("never a session outside the owner's account", "never a session outside the owner's account"),)


def auto_mode():
    path = os.environ.get("AUTO_MODE_SETTINGS") or os.path.join(REPO_ROOT, "settings.json")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle).get("autoMode", {})


def remedy_commands():
    """Every backticked span of the remedy: the archive push, the delete, the fallback name."""
    return re.findall(r"`([^`]+)`", guard_branch_worktree.BRANCH_DELETE_DENY_REASON)


def allow_entry(prefix):
    """The one autoMode.allow entry starting with prefix, or None when there is not exactly one."""
    hits = [e for e in auto_mode().get("allow", []) if e.startswith(prefix)]
    return hits[0] if len(hits) == 1 else None


def never_covers_match(entry):
    """The 'Never covers' match of an entry (any case), its sentence ending at a period, or None."""
    return re.search(r"never covers[^.]*", entry or "", re.I)


def never_covers(entry):
    """The 'Never covers' sentence of an entry, or None when it has none."""
    found = never_covers_match(entry)
    return found.group(0) if found else None


def bounds_text(entry):
    """The entry's text before its 'Never covers' sentence, or all of it when it has none."""
    found = never_covers_match(entry)
    return (entry or "")[:found.start()] if found else (entry or "")


def unnamed_terms(clause, terms):
    """The names in terms whose pattern the clause does not match, ignoring case."""
    return [name for name, pattern in terms if not re.search(pattern, clause, re.I)]


class AutoModeKeepsTheBuiltInRules(unittest.TestCase):
    def test_allow_list_keeps_defaults(self):
        self.assertIn("$defaults", auto_mode().get("allow", []))

    def test_no_list_drops_its_defaults(self):
        block = auto_mode()
        dropped = [k for k in LISTS if k in block and "$defaults" not in block[k]]
        self.assertFalse(dropped, "autoMode lists set without $defaults: %r" % dropped)


class ArchivedBranchDeleteIsAllowed(unittest.TestCase):
    def test_one_entry_names_the_archived_delete(self):
        self.assertIsNotNone(allow_entry(ARCHIVE),
                             "need exactly one 'Archived Branch Delete:' entry in autoMode.allow")

    def test_entry_quotes_every_remedy_command(self):
        entry = allow_entry(ARCHIVE) or ""
        commands = remedy_commands()
        self.assertGreaterEqual(len(commands), 2, "remedy lost its commands: %r" % commands)
        missing = [c for c in commands if "`%s`" % c not in entry]
        self.assertFalse(missing, "allow entry does not quote the remedy's %r" % missing)

    def test_entry_never_covers_an_archive_ref(self):
        entry = allow_entry(ARCHIVE) or ""
        self.assertRegex(entry, r"Never covers[^.]*`archive/`")


class RelayedGrantIsAllowed(unittest.TestCase):
    def test_one_entry_names_the_relayed_grant(self):
        self.assertIsNotNone(allow_entry(RELAYED),
                             "need exactly one '%s' entry in autoMode.allow" % RELAYED)

    def test_entry_quotes_the_page_grant_command_and_counted_line(self):
        entry = bounds_text(allow_entry(RELAYED))
        self.assertIn("`%s`" % page_grant.COMMAND, entry, "entry must quote page_grant.COMMAND in full")
        self.assertIn("`%s`" % page_grant.COUNTED_LINE, entry, "entry must quote page_grant.COUNTED_LINE")

    def test_never_covers_names_each_refused_act(self):
        clause = never_covers(allow_entry(RELAYED))
        self.assertIsNotNone(clause, "need a 'Never covers' sentence in the Relayed Grant entry")
        missing = unnamed_terms(clause, RELAYED_REFUSED)
        self.assertFalse(missing, "Never covers does not name %r" % missing)


class OwnerPrHousekeepingIsAllowed(unittest.TestCase):
    def test_one_entry_names_the_pr_housekeeping(self):
        self.assertIsNotNone(allow_entry(OWNER_PR),
                             "need exactly one '%s' entry in autoMode.allow" % OWNER_PR)

    def test_entry_quotes_the_measured_pr_close(self):
        entry = allow_entry(OWNER_PR) or ""
        self.assertIn("`%s`" % PR_CLOSE, entry, "entry must quote the measured PR close")

    def test_entry_binds_the_owner(self):
        unquoted = re.sub(r"`[^`]+`", "", allow_entry(OWNER_PR) or "")
        self.assertIn("shivinate7", unquoted, "entry must name the bound owner outside quotes")

    def test_never_covers_names_each_refused_act(self):
        clause = never_covers(allow_entry(OWNER_PR))
        self.assertIsNotNone(clause, "need a 'Never covers' sentence in the PR housekeeping entry")
        missing = unnamed_terms(clause, PR_REFUSED)
        self.assertFalse(missing, "Never covers does not name %r" % missing)

    def test_scope_is_named_before_never_covers(self):
        missing = unnamed_terms(bounds_text(allow_entry(OWNER_PR)), PR_SCOPE)
        self.assertFalse(missing, "text before Never covers does not name %r" % missing)

    def test_never_covers_names_delete_branch_flag_and_auto_merge(self):
        clause = never_covers(allow_entry(OWNER_PR))
        self.assertIsNotNone(clause, "need a 'Never covers' sentence in the PR housekeeping entry")
        missing = unnamed_terms(clause, PR_EXTRA_REFUSED)
        self.assertFalse(missing, "Never covers does not name %r" % missing)

    def test_covers_names_the_visible_conversation(self):
        self.assertRegex(bounds_text(allow_entry(OWNER_PR)), r"(?i)visible conversation",
                         "Covers text must name the visible conversation")

    def test_covers_names_the_integration_pull_request(self):
        self.assertRegex(bounds_text(allow_entry(OWNER_PR)), r"(?i)integration pull request",
                         "Covers text must bound marking ready to the integration pull request")

    def test_never_covers_names_the_base_branch(self):
        self.assertRegex(never_covers(allow_entry(OWNER_PR)) or "", r"(?i)\bbase\b",
                         "Never covers must name changing a pull request's base branch")


class OwnerSessionMessageIsAllowed(unittest.TestCase):
    def test_one_entry_names_the_owner_message(self):
        self.assertIsNotNone(allow_entry(OWNER_MESSAGE),
                             "need exactly one '%s' entry in autoMode.allow" % OWNER_MESSAGE)

    def test_entry_quotes_the_send_message_tool(self):
        entry = allow_entry(OWNER_MESSAGE) or ""
        self.assertIn("`%s`" % SEND_MESSAGE, entry, "entry must quote the send tool in backticks")

    def test_never_covers_names_each_refused_act(self):
        clause = never_covers(allow_entry(OWNER_MESSAGE))
        self.assertIsNotNone(clause, "need a 'Never covers' sentence in the owner message entry")
        missing = unnamed_terms(clause, MESSAGE_REFUSED)
        self.assertFalse(missing, "Never covers does not name %r" % missing)

    def test_scope_is_named_before_never_covers(self):
        missing = unnamed_terms(bounds_text(allow_entry(OWNER_MESSAGE)), MESSAGE_SCOPE)
        self.assertFalse(missing, "text before Never covers does not name %r" % missing)

    def test_never_covers_names_shared_channel_post(self):
        clause = never_covers(allow_entry(OWNER_MESSAGE))
        self.assertIsNotNone(clause, "need a 'Never covers' sentence in the owner message entry")
        missing = unnamed_terms(clause, MESSAGE_EXTRA_REFUSED)
        self.assertFalse(missing, "Never covers does not name %r" % missing)

    def test_covers_names_the_already_granted_act(self):
        covers = bounds_text(allow_entry(OWNER_MESSAGE))
        self.assertRegex(covers, r"(?i)already granted",
                         "Covers text must limit the message to acts already granted")
        sentence = re.search(r"[^.]*already granted[^.]*", covers, re.I)
        self.assertRegex(sentence.group(0) if sentence else "", r"(?i)\bask\b",
                         "the sentence holding 'already granted' must say the message asks")

    def test_never_covers_names_priority_now(self):
        self.assertRegex(never_covers(allow_entry(OWNER_MESSAGE)) or "", r"(?i)priority:\s*now",
                         "Never covers must name interrupting the target's turn with priority: now")

    def test_covers_names_the_merge_go_to_its_batch_runner(self):
        entry = allow_entry(OWNER_MESSAGE)
        self.assertIsNotNone(entry, "need exactly one '%s' entry in autoMode.allow" % OWNER_MESSAGE)
        self.assertIsNotNone(never_covers(entry), "need a 'Never covers' sentence to bound Covers")
        missing = unnamed_terms(bounds_text(entry), MERGE_GO_SCOPE)
        self.assertFalse(missing, "Covers text does not name the merge go to a batch runner: %r"
                         % missing)

    def test_never_covers_names_other_sessions_and_non_coordinators(self):
        clause = never_covers(allow_entry(OWNER_MESSAGE))
        self.assertIsNotNone(clause, "need a 'Never covers' sentence in the owner message entry")
        missing = unnamed_terms(clause, MERGE_GO_REFUSED)
        self.assertFalse(missing, "Never covers does not name the merge-ask limits %r" % missing)

    def owner_message_part(self, never=False):
        """The owner message's Never covers sentence (never=True), else its Covers text."""
        entry = allow_entry(OWNER_MESSAGE)
        self.assertIsNotNone(entry, "need exactly one '%s' entry in autoMode.allow" % OWNER_MESSAGE)
        self.assertIsNotNone(never_covers(entry), "need a 'Never covers' sentence to bound Covers")
        return never_covers(entry) if never else bounds_text(entry)

    def test_covers_names_the_session_that_started_this_one(self):
        missing = unnamed_terms(self.owner_message_part(), MESSAGE_TARGET)
        self.assertFalse(missing, "Covers text does not name the session that started this one: %r"
                         % missing)

    def test_covers_names_the_no_act_report(self):
        missing = unnamed_terms(self.owner_message_part(), MESSAGE_REPORT)
        self.assertFalse(missing,
                         "Covers text does not name the no-act report wording %r" % missing)

    def test_covers_names_a_question_about_state(self):
        missing = unnamed_terms(self.owner_message_part(), MESSAGE_QUESTION)
        self.assertFalse(missing, "Covers text does not name a question about state: %r" % missing)

    def test_covers_names_a_request_however_phrased(self):
        missing = unnamed_terms(self.owner_message_part(), MESSAGE_REQUEST)
        self.assertFalse(missing,
                         "Covers text does not say a request is a message that asks: %r" % missing)

    def test_covers_says_only_informs_and_asks_for_no_act(self):
        missing = unnamed_terms(self.owner_message_part(), MESSAGE_ONLY)
        self.assertFalse(missing,
                         "Covers text does not say 'only informs and asks for no act': %r"
                         % missing)

    def test_never_covers_names_a_session_outside_the_owners_account(self):
        missing = unnamed_terms(self.owner_message_part(never=True), MESSAGE_OUTSIDE)
        self.assertFalse(missing,
                         "Never covers does not name a session outside the owner's account: %r"
                         % missing)


class NeverCoversSentence(unittest.TestCase):
    def test_finds_the_clause_in_any_case(self):
        self.assertEqual(never_covers("Ok. never covers a merge."), "never covers a merge")
        self.assertEqual(never_covers("Ok. NEVER COVERS a merge."), "NEVER COVERS a merge")

    def test_sentence_ends_at_its_period(self):
        self.assertEqual(never_covers("Never covers a merge. Other text."), "Never covers a merge")

    def test_none_without_a_clause(self):
        self.assertIsNone(never_covers("Allowed, with no bound."))


if __name__ == "__main__":
    unittest.main()
