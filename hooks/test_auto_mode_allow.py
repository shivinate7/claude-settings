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
- One "Own Branch Lease Push:" entry quotes guard_push_delete's LEASE_PUSH_FORM, read from the guard
  itself. The force-push refusal (PUSH_REASON) names that form as its remedy, and the guard lets the
  filled form through. Its Covers text names an
  explicit expected sha and a branch this session itself pushed, and its Never covers names each
  lease act it refuses (decision auto-mode-owner-acts).
- One "Own CI Run Cancel:" entry quotes the run cancel command and names its method, and its Never
  covers names each run act it refuses (decision auto-mode-owner-acts).
- One "Own Check-in Delete:" entry names the delete tool and the create and send tools that make a
  check-in, and its Never covers names each check-in act it refuses (decision auto-mode-owner-acts).
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
import guard_push_delete  # noqa: E402

sys.path.insert(0, os.path.join(REPO_ROOT, "skills", "waiting-page"))
import page_grant  # noqa: E402

LISTS = ("environment", "allow", "soft_deny", "hard_deny")
ARCHIVE = "Archived Branch Delete:"
OWNER_PR = "Owner PR Housekeeping:"
RELAYED = "Relayed Grant:"
OWNER_MESSAGE = "Owner Session Message:"
OWN_LEASE = "Own Branch Lease Push:"
LEASE_FORM = getattr(guard_push_delete, "LEASE_PUSH_FORM", "")
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
# (name, case-insensitive pattern) for each lease act the Own Branch Lease Push "Never covers" must name.
LEASE_REFUSED = (("default branch", "default branch"), ("archive/ ref", "`archive/`"),
                 ("roadmap", "`roadmap`"), ("merge-lock", "`merge-lock`"),
                 ("bare --force", "bare `--force`"),
                 ("lease with no expected sha", "lease with no expected sha"),
                 ("branch this session did not visibly push",
                  "branch this session did not visibly push"))
# (name, case-insensitive pattern) for each term its Covers text names before its "Never covers".
LEASE_SCOPE = (("explicit expected sha", "explicit expected sha"),
               ("branch this session itself pushed", "this session itself pushed"))
OWN_CI = "Own CI Run Cancel:"
CI_CANCEL = "gh api -X POST repos/shivinate7/q_max/actions/runs/41377928751/cancel"
CI_METHOD = "cancel_workflow_run"
# (name, case-insensitive pattern) for each run act the Own CI Run Cancel "Never covers" must name.
CI_REFUSED = (("default branch", "default branch"),
              ("branch this session did not visibly push", "branch this session did not visibly push"),
              ("run_workflow", "`run_workflow`"), ("rerun_failed_jobs", "`rerun_failed_jobs`"),
              ("delete_workflow_run_logs", "`delete_workflow_run_logs`"),
              ("repo outside shivinate7", "outside shivinate7"))
OWN_CHECKIN = "Own Check-in Delete:"
CHECKIN_DELETE = "mcp__claude-code-remote__delete_trigger"
# (name, case-insensitive pattern) for each check-in tool the Own Check-in Delete entry must name.
CHECKIN_MAKERS = (("create_trigger", "`create_trigger`"), ("send_later", "`send_later`"))
# (name, case-insensitive pattern) for each check-in act the Own Check-in Delete "Never covers" must name.
CHECKIN_REFUSED = (("list_triggers", "`list_triggers`"), ("update_trigger", "`update_trigger`"),
                   ("fire_trigger", "`fire_trigger`"),
                   ("trigger this session did not visibly create",
                    "trigger this session did not visibly create"),
                   ("create_new_session_on_fire", "`create_new_session_on_fire`"),
                   ("persistent_session_id", "`persistent_session_id`"))


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
        self.assertRegex(bounds_text(allow_entry(OWNER_MESSAGE)), r"(?i)already granted",
                         "Covers text must limit the message to acts already granted")

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


class OwnBranchLeasePushIsAllowed(unittest.TestCase):
    def test_one_entry_names_the_own_branch_lease_push(self):
        self.assertIsNotNone(allow_entry(OWN_LEASE),
                             "need exactly one '%s' entry in autoMode.allow" % OWN_LEASE)

    def test_entry_quotes_the_measured_lease_form(self):
        entry = allow_entry(OWN_LEASE)
        self.assertIsNotNone(entry, "need exactly one '%s' entry in autoMode.allow" % OWN_LEASE)
        self.assertIn("`%s`" % LEASE_FORM, entry, "entry must quote the measured lease push form")

    def test_never_covers_names_each_refused_lease_act(self):
        entry = allow_entry(OWN_LEASE)
        self.assertIsNotNone(entry, "need exactly one '%s' entry in autoMode.allow" % OWN_LEASE)
        clause = never_covers(entry)
        self.assertIsNotNone(clause, "need a 'Never covers' sentence in the Own Branch Lease Push entry")
        missing = unnamed_terms(clause, LEASE_REFUSED)
        self.assertFalse(missing, "Never covers does not name %r" % missing)

    def test_scope_is_named_before_never_covers(self):
        entry = allow_entry(OWN_LEASE)
        self.assertIsNotNone(entry, "need exactly one '%s' entry in autoMode.allow" % OWN_LEASE)
        self.assertIsNotNone(never_covers(entry), "need a 'Never covers' sentence to bound Covers")
        missing = unnamed_terms(bounds_text(entry), LEASE_SCOPE)
        self.assertFalse(missing, "text before Never covers does not name %r" % missing)

    def test_refusal_names_the_form_the_entry_covers(self):
        self.assertTrue(LEASE_FORM, "guard_push_delete must define LEASE_PUSH_FORM")
        self.assertIn("`%s`" % LEASE_FORM, guard_push_delete.PUSH_REASON,
                      "the force-push refusal must name the lease form the entry covers")
        self.assertNotIn("--force-if-includes", guard_push_delete.PUSH_REASON,
                         "the refusal must not offer a lease form the entry does not cover")

    def test_guard_lets_the_filled_form_through(self):
        self.assertTrue(LEASE_FORM, "guard_push_delete must define LEASE_PUSH_FORM")
        filled = LEASE_FORM.replace("<branch>", "feat").replace("<expected sha>", "0" * 40)
        args = filled.split()[2:] + ["origin", "feat"]
        self.assertEqual(guard_push_delete.push_verdict(args, ""), "")
        self.assertEqual(guard_push_delete.push_verdict(["--force-with-lease", "origin", "feat"], ""), "deny")


class OwnCiRunCancelIsAllowed(unittest.TestCase):
    def test_one_entry_names_the_own_ci_run_cancel(self):
        self.assertIsNotNone(allow_entry(OWN_CI), "need exactly one '%s' entry in autoMode.allow" % OWN_CI)

    def test_entry_quotes_the_run_cancel_command(self):
        entry = allow_entry(OWN_CI)
        self.assertIsNotNone(entry, "need exactly one '%s' entry in autoMode.allow" % OWN_CI)
        self.assertIn("`%s`" % CI_CANCEL, entry, "entry must quote the run cancel command")

    def test_entry_names_the_cancel_method(self):
        entry = allow_entry(OWN_CI)
        self.assertIsNotNone(entry, "need exactly one '%s' entry in autoMode.allow" % OWN_CI)
        self.assertIn("`%s`" % CI_METHOD, entry, "entry must name the cancel_workflow_run method")

    def test_never_covers_names_each_refused_run_act(self):
        entry = allow_entry(OWN_CI)
        self.assertIsNotNone(entry, "need exactly one '%s' entry in autoMode.allow" % OWN_CI)
        clause = never_covers(entry)
        self.assertIsNotNone(clause, "need a 'Never covers' sentence in the Own CI Run Cancel entry")
        missing = unnamed_terms(clause, CI_REFUSED)
        self.assertFalse(missing, "Never covers does not name %r" % missing)


class OwnCheckinDeleteIsAllowed(unittest.TestCase):
    def test_one_entry_names_the_own_checkin_delete(self):
        self.assertIsNotNone(allow_entry(OWN_CHECKIN),
                             "need exactly one '%s' entry in autoMode.allow" % OWN_CHECKIN)

    def test_entry_quotes_the_delete_tool(self):
        entry = allow_entry(OWN_CHECKIN)
        self.assertIsNotNone(entry, "need exactly one '%s' entry in autoMode.allow" % OWN_CHECKIN)
        self.assertIn("`%s`" % CHECKIN_DELETE, entry, "entry must quote the delete_trigger tool")

    def test_entry_names_the_create_and_send_tools(self):
        entry = allow_entry(OWN_CHECKIN)
        self.assertIsNotNone(entry, "need exactly one '%s' entry in autoMode.allow" % OWN_CHECKIN)
        missing = unnamed_terms(entry, CHECKIN_MAKERS)
        self.assertFalse(missing, "entry does not name the check-in tools %r" % missing)

    def test_never_covers_names_each_refused_checkin_act(self):
        entry = allow_entry(OWN_CHECKIN)
        self.assertIsNotNone(entry, "need exactly one '%s' entry in autoMode.allow" % OWN_CHECKIN)
        clause = never_covers(entry)
        self.assertIsNotNone(clause, "need a 'Never covers' sentence in the Own Check-in Delete entry")
        missing = unnamed_terms(clause, CHECKIN_REFUSED)
        self.assertFalse(missing, "Never covers does not name %r" % missing)


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
