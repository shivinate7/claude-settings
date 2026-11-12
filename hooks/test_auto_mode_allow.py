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
  Its Covers text names a report that relays a grant or hands off an act, and `next: merge`, and
  limits the already granted act to messages that ask.
- One "Relayed Grant:" entry quotes page_grant.py's COMMAND and COUNTED_LINE, read from the
  checker itself, and its Never covers names each act in RELAYED_REFUSED (decision
  relayed-grant-read-from-page). Its Covers text names the one settings change: a label that names
  `settings.json` and the entry by its exact title or key, one entry per grant. Its "Never covers wins"
  sentence follows the Never covers sentence and settles any clash with Covers.
- One "Own Branch Lease Push:" entry quotes the lease push with a named sha and the guard remedy's
  command form, read from PUSH_REASON, and that remedy names the same sha form. Its Covers text names
  the 9 lease-push refusals, requires
  the branch was pushed earlier in this session, and binds the sha to the tip this session last
  pushed. Its Never covers names each act in LEASE_REFUSED (decision auto-mode-owner-acts).
- One "Own Branch Lease Push, refspec form:" entry quotes both lease forms typed with a source ref,
  `origin <src>:<branch>`, and names <src> as a local branch, `HEAD` or a commit sha. Its Covers text
  requires the same earlier push and binds the sha as the lease entry does. Its Never covers names each
  act in REFSPEC_REFUSED (decision auto-mode-owner-acts).
- One "Relayed Merge Yes:" entry quotes the merge command derived from merge/cloud_allow.json's
  one `--confirm` merge rule with the head flag read from merge/merge.py's argparse.
  Its Covers text names the coordinator that relays (cs-build:coordinator),
  the batch runner that merges (cs-build:batch-runner), and the pull request the relay names. Its
  Never covers names each act in RELAYED_MERGE_REFUSED, the reason flags, and a session not tagged
  cs-build:batch-runner (decision `auto-mode-owner-acts`).
- One "Batch Runner Merge:" entry quotes the same derived merge command with the head flag
  (`--head <sha>`) in its Covers text. Its Covers text names the coordinator that sends the merge go
  (cs-build:coordinator), the batch runner (cs-build:batch-runner), `merge go`, and the pull request
  the merge go names. Its Never covers names each act in BATCH_MERGE_REFUSED, the reason flags, a
  merge with no `--head`, and a merge go from a session not tagged cs-build:coordinator (decision
  `auto-mode-owner-acts`).
AUTO_MODE_SETTINGS names another settings file to read (default: this repo's settings.json), so the
same cases run against a copy with a clause removed and show red there.
"""
import ast
import json
import os
import re
import sys
import unittest

HOOKS = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HOOKS)
MERGE_PY = os.path.join(REPO_ROOT, "merge", "merge.py")
sys.path.insert(0, HOOKS)

import guard_branch_worktree  # noqa: E402
import guard_push_delete  # noqa: E402

sys.path.insert(0, os.path.join(REPO_ROOT, "skills", "waiting-page"))
import page_grant  # noqa: E402

LISTS = ("environment", "allow", "soft_deny", "hard_deny")
ARCHIVE = "Archived Branch Delete:"
OWNER_PR = "Owner PR Housekeeping:"
RELAYED = "Relayed Grant:"
RELAYED_MERGE = "Relayed Merge Yes:"
BATCH_MERGE = "Batch Runner Merge:"
MERGE_CLOUD_ALLOW = os.path.join(REPO_ROOT, "merge", "cloud_allow.json")
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
# One settings change is covered only when its label names the file and entry, so a settings change without
# that naming stays refused, and so do the entry's own change, hooks, env, and an autoMode.allow entry the label
# does not name.
RELAYED_REFUSED = (("peer session's message", "peer session's message"), ("page comment", "a page comment"),
                   ("lastAnswer", "lastAnswer"), ("reply", "reply"),
                   ("answer for another item", "an answer for another item"), ("choice none", "choice none"),
                   ("task answer", "any task answer"), ("time with no zone", "time has no zone"),
                   ("older than added", "an answer older than the item's added"),
                   ("closed item", "a closed item"), ("arbiter overturn only", r"except an arbiter overturn"),
                   ("permissions", "permissions"), ("overrides", "overrides"),
                   ("settings change without file and entry",
                    "a settings change whose label does not name the file and entry"),
                   ("Relayed Grant entry itself", "a change to the Relayed Grant entry itself"),
                   ("a change to hooks", "a change to hooks"), ("a change to env", r"a change to env\b"),
                   ("an autoMode.allow entry the label does not name",
                    r"an autoMode\.allow entry the label does not name"),
                   ("no counted line", "no `counted` line in this session"))
# Each term the Relayed Grant entry's Covers text names for its one settings change.
RELAYED_SETTINGS_COVERS = (("one settings change", "one settings change"),
                           ("label names the settings file and entry", r"label.*?settings file.*?entry"),
                           ("settings.json", r"settings\.json"), ("exact title or key", r"\bexact\b"),
                           ("one entry per grant", "one entry"))
# Each act the Relayed Merge Yes entry's "Never covers" sentence must name (decision `auto-mode-owner-acts`).
RELAYED_MERGE_REFUSED = (("another pull request", "another pull request"),
                         ("not tagged cs-build:coordinator", "not tagged `cs-build:coordinator`"),
                         ("failing", "failing"), ("running", "running"), ("approval", "approv"),
                         ("review", "review"), ("admin", "admin"), ("force push", "force[- ]push"),
                         ("permissions", "permission"), ("settings", "setting"),
                         ("overrides", "override"), ("any other act", "any other act"))
# Each act the Batch Runner Merge entry's "Never covers" sentence must name (decision `auto-mode-owner-acts`).
BATCH_MERGE_REFUSED = (("not tagged cs-build:batch-runner", "not tagged `cs-build:batch-runner`"),
                       ("nobody named", "nobody named"),
                       ("failing", "failing"), ("running", "running"), ("approval", "approv"),
                       ("review", "review"), ("admin", "admin"), ("force push", "force[- ]push"),
                       ("permissions", "permission"), ("settings", "setting"),
                       ("overrides", "override"), ("any other act", "any other act"))
# The reason flags that lift a merge check (merge/merge.py); each entry's Never covers names both.
REASON_FLAGS_REFUSED = (("--base-red-ok", "--base-red-ok"),
                        ("--undo-check-unknown-ok", "--undo-check-unknown-ok"))
MERGE_GO_REFUSED = (("any other session", "any other session"),
                    ("not a coordinator", "not a coordinator"))
# The Covers text names the session that started this one, and the no-act report it lets through.
MESSAGE_TARGET = (("the session that started this one", "the session that started this one"),)
MESSAGE_REPORT = (("asks for no act", "asks for no act"), ("pull request number", "pull request number"),
                  ("batch heads", "batch heads"))
MESSAGE_QUESTION = (("a question about state", "a question about state"),)
MESSAGE_REQUEST = (("ready to merge", "ready to merge"), ("however phrased", "however phrased"))
MESSAGE_RELAY = (("relays a grant", "relays a grant"), ("hands off an act", "hands off an act"))
MESSAGE_NEXT_MERGE = (("next: merge", "next: merge"),)
MESSAGE_ONLY = (("only informs and asks for no act", "only informs and asks for no act"),)
MESSAGE_OUTSIDE = (("never a session outside the owner's account", "never a session outside the owner's account"),)
LEASE = "Own Branch Lease Push:"
LEASE_SHA_FORM = "`git push --force-with-lease=<branch>:<sha> origin <branch>`"
LEASE_INCIDENT = "9 lease-push refusals"
# (name, case-insensitive pattern) for each condition the lease Covers text must state.
LEASE_SCOPE = (("earlier in this session", "earlier in this session"),
               ("pushed that same branch", "pushed that same branch"), ("same remote", "same remote"))
# (name, case-insensitive pattern) for the sha the lease Covers text binds to the last tip pushed.
LEASE_BINDING = (("sha is the tip this session last pushed",
                  r"<sha> is the tip this session last pushed"),)
# (name, case-insensitive pattern) for each act the lease "Never covers" must name. Backticks anchor
# the flags, because --force-if-includes contains --force and -f.
LEASE_REFUSED = (("--force", r"`--force`"), ("-f", r"`-f`"), ("+refspec", r"`\+refspec`"),
                 ("a lease with neither --force-if-includes nor a named sha",
                  r"lease with neither `--force-if-includes` nor a named sha"),
                 ("the default branch", "default branch"), ("archive/", r"`archive/`"),
                 ("roadmap", r"`roadmap`"), ("merge-lock", r"`merge-lock`"),
                 ("a branch this session did not push earlier", "did not push earlier"),
                 ("--mirror", r"`--mirror`"), ("--all", r"`--all`"), ("delete", r"\bdelete\b"))
REFSPEC = "Own Branch Lease Push, refspec form:"
REFSPEC_IF_INCLUDES_FORM = "`git push --force-with-lease --force-if-includes origin <src>:<branch>`"
REFSPEC_SHA_FORM = "`git push --force-with-lease=<branch>:<sha> origin <src>:<branch>`"
# (name, case-insensitive pattern) for the source ref the refspec Covers text names.
REFSPEC_SRC = (("src is a local branch, HEAD or a commit sha",
                r"<src> is a local branch, `HEAD` or a commit sha"),)
# The refspec Never covers names the lease entry's acts, with the `+` read before either ref and the
# delete named with its empty <src>. The shared items keep their one home in LEASE_REFUSED.
REFSPEC_REFUSED = tuple(item for item in LEASE_REFUSED if item[0] not in ("+refspec", "delete")) + (
    ("a + before either ref", r"`\+` before either ref"),
    ("delete (an empty <src>)", r"a delete \(an empty <src>\)"))


def auto_mode():
    path = os.environ.get("AUTO_MODE_SETTINGS") or os.path.join(REPO_ROOT, "settings.json")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle).get("autoMode", {})


def remedy_commands():
    """Every backticked span of the remedy: the archive push, the delete, the fallback name."""
    return re.findall(r"`([^`]+)`", guard_branch_worktree.BRANCH_DELETE_DENY_REASON)


def merge_rules():
    """The --confirm merge rules in merge/cloud_allow.json, as written there.

    The trailing-flag rule `Bash(~/.claude/bin/merge * --confirm *)` is left out on purpose. Its extra
    arguments take the reason flags, which each Relayed or Batch entry's Never covers names, so an entry
    quotes only the bare rule's command.
    """
    with open(MERGE_CLOUD_ALLOW, encoding="utf-8") as handle:
        allow = json.load(handle).get("permissions", {}).get("allow", [])
    return [rule for rule in allow
            if rule.startswith("Bash(~/.claude/bin/merge ") and rule.endswith(" --confirm)")]


def merge_command():
    """The one merge rule's command with its `*` read as <pr>, or None when there is not exactly one rule."""
    rules = merge_rules()
    if len(rules) != 1:
        return None
    return rules[0][len("Bash("):-1].replace("*", "<pr>")


def head_flag():
    """The option string of merge.py's argparse flag typed head_arg (the sha a relay names), or None when there is not exactly one.
    Read from the parser's own add_argument calls, so a renamed flag moves the derived command with it."""
    with open(MERGE_PY, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    flags = [node.args[0].value for node in ast.walk(tree)
             if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "add_argument"
             and node.args and isinstance(node.args[0], ast.Constant)
             and any(k.arg == "type" and isinstance(k.value, ast.Name) and k.value.id == "head_arg" for k in node.keywords)]
    return flags[0] if len(flags) == 1 else None


def allow_entry(prefix):
    """The one autoMode.allow entry starting with prefix, or None when there is not exactly one."""
    hits = [e for e in auto_mode().get("allow", []) if e.startswith(prefix)]
    return hits[0] if len(hits) == 1 else None


def never_covers_match(entry):
    """The 'Never covers' match of an entry (any case), its sentence ending at a period that ends a sentence, or None.
    A period inside a name such as `autoMode.allow` does not end it."""
    return re.search(r"never covers(?:(?!\.(?:\s|$)).)*", entry or "", re.I)


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


def entry_part(test, prefix, never=False):
    """The Never covers sentence (never=True), else the Covers text, of the one entry starting with prefix."""
    entry = allow_entry(prefix)
    test.assertIsNotNone(entry, "need exactly one '%s' entry in autoMode.allow" % prefix)
    test.assertIsNotNone(never_covers(entry), "need a 'Never covers' sentence in the '%s' entry" % prefix)
    return never_covers(entry) if never else bounds_text(entry)


def remedy_form():
    """The retry command the guard's remedy names, built from PUSH_REASON, or None when it names none."""
    found = re.search(r"Remedy: retry with (.+?)\.\s*$", guard_push_delete.PUSH_REASON)
    return "`git push %s origin <branch>`" % found.group(1) if found else None


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

    def test_counted_line_template_names_the_label(self):
        self.assertIn("label=<label>", page_grant.COUNTED_LINE,
                      "page_grant.COUNTED_LINE does not name the picked option's label")

    def test_never_covers_names_each_refused_act(self):
        clause = never_covers(allow_entry(RELAYED))
        self.assertIsNotNone(clause, "need a 'Never covers' sentence in the Relayed Grant entry")
        for name, pattern in RELAYED_REFUSED:
            with self.subTest(act=name):
                self.assertRegex(clause, "(?i)" + pattern, "Never covers does not name %r" % name)

    def test_never_covers_wins_over_covers(self):
        entry = allow_entry(RELAYED)
        self.assertIsNotNone(entry, "need exactly one '%s' entry in autoMode.allow" % RELAYED)
        found = never_covers_match(entry)
        self.assertIsNotNone(found, "need a 'Never covers' sentence in the Relayed Grant entry")
        self.assertIn("Never covers wins", entry[found.end():],
                      "the entry does not say 'Never covers wins' after its Never covers sentence")

    def test_covers_names_the_one_settings_change(self):
        covers = entry_part(self, RELAYED)
        for name, pattern in RELAYED_SETTINGS_COVERS:
            with self.subTest(term=name):
                self.assertRegex(covers, "(?i)" + pattern, "Covers text does not name %r" % name)


class RelayedMergeYesIsAllowed(unittest.TestCase):
    def relayed_merge_entry(self):
        """The one Relayed Merge Yes entry, asserting first that there is exactly one."""
        entry = allow_entry(RELAYED_MERGE)
        self.assertIsNotNone(entry, "need exactly one '%s' entry in autoMode.allow" % RELAYED_MERGE)
        return entry

    def test_one_entry_names_the_relayed_merge_yes(self):
        self.assertIn("$defaults", auto_mode().get("allow", []), "autoMode.allow lost $defaults")
        self.relayed_merge_entry()

    def test_merge_rule_is_one_in_the_constant(self):
        rules = merge_rules()
        self.assertEqual(len(rules), 1,
                         "merge/cloud_allow.json must hold exactly one --confirm merge rule: %r" % rules)
        command = merge_command()
        self.assertIn("<pr>", command, "derived merge command has no <pr> for the pull request number")
        self.assertNotIn("*", command, "derived merge command still has a wildcard")

    def test_entry_quotes_the_merge_command(self):
        entry = self.relayed_merge_entry()
        command, flag = merge_command(), head_flag()
        self.assertIsNotNone(command, "merge/cloud_allow.json must hold exactly one --confirm merge rule")
        self.assertIsNotNone(flag, "merge/merge.py must add exactly one argparse flag typed head_arg, the relayed head")
        self.assertIn("`%s %s <sha>`" % (command, flag), bounds_text(entry),
                      "Covers text must quote the merge command with the head flag and <sha> for the relayed head")

    def test_covers_names_the_coordinator_tag(self):
        entry = self.relayed_merge_entry()
        self.assertIn("cs-build:coordinator", bounds_text(entry),
                      "Covers text must require a session tagged cs-build:coordinator")

    def test_covers_names_the_pull_request_the_relay_names(self):
        entry = self.relayed_merge_entry()
        self.assertIn("the pull request the relay names", bounds_text(entry),
                      "Covers text must say the pull request the relay names")

    def test_covers_names_the_batch_runner_that_merges(self):
        entry = self.relayed_merge_entry()
        self.assertIn("cs-build:batch-runner", bounds_text(entry),
                      "Covers text must name cs-build:batch-runner as the session that merges")

    def test_never_covers_names_a_batch_runner_not_tagged(self):
        clause = never_covers(self.relayed_merge_entry())
        self.assertIsNotNone(clause, "need a 'Never covers' sentence in the Relayed Merge Yes entry")
        self.assertIn("not tagged `cs-build:batch-runner`", clause,
                      "Never covers does not name a session not tagged cs-build:batch-runner")

    def test_never_covers_names_each_refused_act(self):
        clause = never_covers(self.relayed_merge_entry())
        self.assertIsNotNone(clause, "need a 'Never covers' sentence in the Relayed Merge Yes entry")
        missing = unnamed_terms(clause, RELAYED_MERGE_REFUSED)
        self.assertFalse(missing, "Never covers does not name %r" % missing)

    def test_never_covers_names_the_reason_flags(self):
        clause = never_covers(self.relayed_merge_entry())
        self.assertIsNotNone(clause, "need a 'Never covers' sentence in the Relayed Merge Yes entry")
        missing = unnamed_terms(clause, REASON_FLAGS_REFUSED)
        self.assertFalse(missing, "Never covers does not name the reason flags %r" % missing)

    def test_never_covers_names_a_head_the_relay_did_not_name(self):
        clause = never_covers(self.relayed_merge_entry())
        self.assertIsNotNone(clause, "need a 'Never covers' sentence in the Relayed Merge Yes entry")
        self.assertIn("a head the relay did not name", clause,
                      "Never covers does not name a head the relay did not name")

    def test_never_covers_names_a_merge_with_no_head_flag(self):
        clause = never_covers(self.relayed_merge_entry())
        flag = head_flag()
        self.assertIsNotNone(clause, "need a 'Never covers' sentence in the Relayed Merge Yes entry")
        self.assertIsNotNone(flag, "merge/merge.py must add exactly one argparse flag typed head_arg, the relayed head")
        self.assertIn("a merge with no `%s`" % flag, clause,
                      "Never covers does not name a merge with no `%s`" % flag)


class BatchRunnerMergeIsAllowed(unittest.TestCase):
    def batch_merge_entry(self):
        """The one Batch Runner Merge entry, asserting first that there is exactly one."""
        entry = allow_entry(BATCH_MERGE)
        self.assertIsNotNone(entry, "need exactly one '%s' entry in autoMode.allow" % BATCH_MERGE)
        return entry

    def test_one_entry_names_the_batch_runner_merge(self):
        self.batch_merge_entry()

    def test_entry_quotes_the_merge_command(self):
        entry = self.batch_merge_entry()
        command, flag = merge_command(), head_flag()
        self.assertIsNotNone(command, "merge/cloud_allow.json must hold exactly one --confirm merge rule")
        self.assertIsNotNone(flag, "merge/merge.py must add exactly one argparse flag typed head_arg, the head the CI ran on")
        self.assertIn("`%s %s <sha>`" % (command, flag), bounds_text(entry),
                      "Covers text must quote the merge command with the head flag and <sha> for the head the CI ran on")

    def test_covers_names_the_batch_runner_tag(self):
        entry = self.batch_merge_entry()
        self.assertIn("cs-build:batch-runner", bounds_text(entry),
                      "Covers text must require a session tagged cs-build:batch-runner")

    def test_covers_names_merge_go(self):
        entry = self.batch_merge_entry()
        self.assertIn("merge go", bounds_text(entry), "Covers text must name the merge go")

    def test_covers_names_the_coordinator_as_sender(self):
        entry = self.batch_merge_entry()
        self.assertIn("cs-build:coordinator", bounds_text(entry),
                      "Covers text must name cs-build:coordinator as the merge go's sender")

    def test_covers_names_the_pull_request_the_merge_go_names(self):
        entry = self.batch_merge_entry()
        self.assertIn("the pull request the merge go names", bounds_text(entry),
                      "Covers text must say the pull request the merge go names")

    def test_never_covers_names_a_merge_go_from_a_non_coordinator(self):
        clause = never_covers(self.batch_merge_entry())
        self.assertIsNotNone(clause, "need a 'Never covers' sentence in the Batch Runner Merge entry")
        self.assertIn("a merge go from a session not tagged `cs-build:coordinator`", clause,
                      "Never covers does not name a merge go from a session not tagged cs-build:coordinator")

    def test_never_covers_names_each_refused_act(self):
        clause = never_covers(self.batch_merge_entry())
        self.assertIsNotNone(clause, "need a 'Never covers' sentence in the Batch Runner Merge entry")
        missing = unnamed_terms(clause, BATCH_MERGE_REFUSED)
        self.assertFalse(missing, "Never covers does not name %r" % missing)

    def test_never_covers_names_the_reason_flags(self):
        clause = never_covers(self.batch_merge_entry())
        self.assertIsNotNone(clause, "need a 'Never covers' sentence in the Batch Runner Merge entry")
        missing = unnamed_terms(clause, REASON_FLAGS_REFUSED)
        self.assertFalse(missing, "Never covers does not name the reason flags %r" % missing)

    def test_never_covers_names_a_merge_with_no_head_flag(self):
        clause = never_covers(self.batch_merge_entry())
        flag = head_flag()
        self.assertIsNotNone(clause, "need a 'Never covers' sentence in the Batch Runner Merge entry")
        self.assertIsNotNone(flag, "merge/merge.py must add exactly one argparse flag typed head_arg, the head the CI ran on")
        self.assertIn("a merge with no `%s`" % flag, clause,
                      "Never covers does not name a merge with no `%s`" % flag)


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
        self.assertRegex(covers, r"(?i)the already granted limit applies to messages that ask",
                         "Covers text must say the already granted limit applies to messages that ask")

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
        return entry_part(self, OWNER_MESSAGE, never)

    def test_covers_names_the_session_that_started_this_one(self):
        missing = unnamed_terms(self.owner_message_part(), MESSAGE_TARGET)
        self.assertFalse(missing, "Covers text does not name the session that started this one: %r"
                         % missing)

    def test_covers_names_a_report_that_relays_or_hands_off(self):
        missing = unnamed_terms(self.owner_message_part(), MESSAGE_RELAY)
        self.assertFalse(missing,
                         "Covers text does not say a report that relays a grant or hands off an act asks: %r"
                         % missing)

    def test_covers_names_the_next_merge_report(self):
        missing = unnamed_terms(self.owner_message_part(), MESSAGE_NEXT_MERGE)
        self.assertFalse(missing, "Covers text does not name the 'next: merge' report: %r" % missing)

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


class OwnBranchLeasePushIsAllowed(unittest.TestCase):
    def test_one_entry_names_the_lease_push(self):
        hits = [e for e in auto_mode().get("allow", []) if e.startswith(LEASE)]
        self.assertEqual(len(hits), 1, "need exactly one '%s' entry in autoMode.allow, found %d"
                         % (LEASE, len(hits)))

    def test_covers_quotes_the_sha_push_form(self):
        self.assertIn(LEASE_SHA_FORM, entry_part(self, LEASE),
                      "Covers text does not quote the lease push with a named sha")

    def test_entry_quotes_the_guard_remedy_form(self):
        form = remedy_form()
        self.assertIsNotNone(form, "PUSH_REASON names no retry command to quote")
        self.assertIn(form, entry_part(self, LEASE), "entry does not quote the guard remedy's command form")

    def test_guard_remedy_names_the_sha_form_the_entry_allows(self):
        self.assertEqual(remedy_form(), LEASE_SHA_FORM,
                         "the guard remedy names a retry form the lease entry does not allow")

    def test_covers_names_the_incident(self):
        self.assertIn(LEASE_INCIDENT, entry_part(self, LEASE),
                      "Covers text does not name the incident '%s'" % LEASE_INCIDENT)

    def test_covers_requires_a_push_earlier_in_this_session(self):
        missing = unnamed_terms(entry_part(self, LEASE), LEASE_SCOPE)
        self.assertFalse(missing, "Covers text does not require an earlier push this session: %r" % missing)

    def test_covers_binds_the_sha_to_the_tip_last_pushed(self):
        missing = unnamed_terms(entry_part(self, LEASE), LEASE_BINDING)
        self.assertFalse(missing, "Covers text does not bind the lease sha to the tip this session last pushed: %r"
                         % missing)

    def test_never_covers_names_each_refused_act(self):
        missing = unnamed_terms(entry_part(self, LEASE, never=True), LEASE_REFUSED)
        self.assertFalse(missing, "Never covers does not name %r" % missing)


class OwnBranchLeaseRefspecPushIsAllowed(unittest.TestCase):
    def test_one_entry_names_the_refspec_form(self):
        hits = [e for e in auto_mode().get("allow", []) if e.startswith(REFSPEC)]
        self.assertEqual(len(hits), 1, "need exactly one '%s' entry in autoMode.allow, found %d"
                         % (REFSPEC, len(hits)))

    def test_covers_quotes_the_if_includes_form(self):
        self.assertIn(REFSPEC_IF_INCLUDES_FORM, entry_part(self, REFSPEC),
                      "Covers text does not quote the --force-if-includes form with a source ref")

    def test_covers_quotes_the_sha_form(self):
        self.assertIn(REFSPEC_SHA_FORM, entry_part(self, REFSPEC),
                      "Covers text does not quote the lease push with a named sha and a source ref")

    def test_covers_requires_a_push_earlier_in_this_session(self):
        missing = unnamed_terms(entry_part(self, REFSPEC), LEASE_SCOPE)
        self.assertFalse(missing, "Covers text does not require an earlier push this session: %r" % missing)

    def test_covers_binds_the_sha_to_the_tip_last_pushed(self):
        missing = unnamed_terms(entry_part(self, REFSPEC), LEASE_BINDING)
        self.assertFalse(missing, "Covers text does not bind the lease sha to the tip this session last pushed: %r"
                         % missing)

    def test_covers_names_the_source_ref(self):
        missing = unnamed_terms(entry_part(self, REFSPEC), REFSPEC_SRC)
        self.assertFalse(missing, "Covers text does not name <src> as a local branch, HEAD or a commit sha: %r"
                         % missing)

    def test_never_covers_names_each_refused_act(self):
        missing = unnamed_terms(entry_part(self, REFSPEC, never=True), REFSPEC_REFUSED)
        self.assertFalse(missing, "Never covers does not name %r" % missing)


class NeverCoversSentence(unittest.TestCase):
    def test_finds_the_clause_in_any_case(self):
        self.assertEqual(never_covers("Ok. never covers a merge."), "never covers a merge")
        self.assertEqual(never_covers("Ok. NEVER COVERS a merge."), "NEVER COVERS a merge")

    def test_sentence_ends_at_its_period(self):
        self.assertEqual(never_covers("Never covers a merge. Other text."), "Never covers a merge")

    def test_dotted_name_does_not_end_the_sentence(self):
        self.assertEqual(never_covers("Never covers a change to another autoMode.allow entry. Other."),
                         "Never covers a change to another autoMode.allow entry")

    def test_none_without_a_clause(self):
        self.assertIsNone(never_covers("Allowed, with no bound."))


if __name__ == "__main__":
    unittest.main()
