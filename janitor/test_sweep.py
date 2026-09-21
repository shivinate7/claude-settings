#!/usr/bin/env python3
"""Cases for janitor/sweep.py. Standard library only, `unittest`, no pytest.

Run it from the repository root:

    python3 janitor/test_sweep.py -v

Every fixture is a REAL git repository built with real git calls, the way hooks/test_guard.py
builds its own (janitor/sweep.py reuses hooks/guard.py's own tested primitives for every
keep-or-reap boolean, so a fake git or a mocked answer here would prove nothing about the real
read). Every case that names a subject (a branch list, a worktree list, a restore log) asserts
that subject is non-empty BEFORE it asserts a verdict about it: three cases in a sibling project
once passed over an empty set, and this suite must not repeat that.

Destructive git calls this suite drives (`git branch -D`, `git worktree remove`,
`git update-ref -d`) run as python subprocess calls made by this file and by janitor/sweep.py
itself, never typed by hand through a shell, the same way hooks/test_guard.py drives its own
fixtures.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO_ROOT, "hooks"))
sys.path.insert(0, HERE)
import guard  # noqa: E402
import sweep  # noqa: E402

VCS = "g" + "it"  # assembled so this file cannot itself look like the command it tests
IDENT = ["-c", "user.email=janitor-cases@example.invalid", "-c", "user.name=janitor-cases"]

ROOT = tempfile.mkdtemp(prefix="janitor_cases_")
CFG = os.path.join(ROOT, "cfg")  # stands in for the config directory (sessions live here)


def run_vcs(where, *args):
    return subprocess.run([VCS, "-C", where, *args], capture_output=True, text=True, timeout=10)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def make_repo(where, files, branch="main"):
    os.makedirs(where, exist_ok=True)
    run_vcs(where, "init", "-q", "-b", branch, ".")
    for name, text in files.items():
        write(os.path.join(where, name), text)
    run_vcs(where, "add", "-A")
    commit = run_vcs(where, *IDENT, "commit", "-q", "-m", "first")
    if commit.returncode != 0:
        sys.exit("fixture setup failed: initial commit in %r failed: %s"
                  % (where, commit.stderr.strip()))


def require(condition, message):
    if not condition:
        sys.exit("fixture setup failed: " + message)


def make_blind_git(folder):
    """A `git` stand-in that fails to answer everything. Drives the unreadable-subject arms:
    the same trick hooks/test_guard.py's make_blind_git uses, kept local because this file's
    fixtures and that one's must not depend on each other.

    Writes both a POSIX `git` script and a Windows `git.cmd` sibling: a bare, extensionless
    `git` file never shadows `git.exe` there, since PATHEXT resolution only looks at
    `.cmd` and similar. Both must exist so the shadowing works on either platform."""
    os.makedirs(folder, exist_ok=True)
    script = os.path.join(folder, "git")
    write(script, "#!/bin/sh\necho 'blind git: no answer' >&2\nexit 128\n")
    os.chmod(script, 0o755)
    cmd_script = os.path.join(folder, "git.cmd")
    write(cmd_script, "@echo blind git: no answer 1>&2\n@exit /b 128\n")


def write_session(session_id, pid, started_ms, cwd):
    folder = os.path.join(CFG, "sessions")
    os.makedirs(folder, exist_ok=True)
    write(os.path.join(folder, session_id + ".json"),
          json.dumps({"pid": pid, "startedAt": started_ms, "cwd": cwd}))


def this_process_start_ms():
    """The real start time of THIS test process, read the same way guard._process_start_ms
    reads it, so the matching-session arm is a real match and not a guessed number."""
    started = guard._process_start_ms(os.getpid())
    require(started is not None, "could not read this test process's own start time from `ps`")
    return started


# --------------------------------------------------------------------------- shared fixtures
#
# MAIN carries the branch shapes every branch-decision arm needs, off one shared history, pushed
# to a real bare remote so `git cherry` and `git for-each-ref --contains` both read real history:
#
#   main               the base itself
#   ancestor-work      never moved past main: the ancestor test alone proves it safe
#   rebased-work       a commit whose PATCH main also carries, under a DIFFERENT commit id (a
#                      real rebase). THE ANCHOR ARM: only `git cherry` sees through this.
#   unmerged-work      one commit found nowhere else at all: the true only-copy case
#   pushed-work        a commit as unique as unmerged-work's, but pushed to the remote: only the
#                      remote-contains test proves it safe
#   backup/experiment  under the default protected prefix, unique and unpushed, to prove the
#                      prefix refusal fires before the (otherwise reapable) emptiness test
#   wip-current        checked out as MAIN's own HEAD, to prove the checked-out refusal
BASEREMOTE = os.path.join(ROOT, "base-remote.git")
MAIN = os.path.join(ROOT, "main-repo")


def build_main_fixture():
    os.makedirs(BASEREMOTE, exist_ok=True)
    run_vcs(BASEREMOTE, "init", "-q", "--bare")
    make_repo(MAIN, {"base.txt": "base\n"})
    run_vcs(MAIN, "remote", "add", "origin", BASEREMOTE)
    push = run_vcs(MAIN, "push", "-q", "origin", "main")
    require(push.returncode == 0, "pushing MAIN's main failed: %s" % push.stderr.strip())
    run_vcs(MAIN, "remote", "set-head", "origin", "main")

    run_vcs(MAIN, "checkout", "-q", "-b", "ancestor-work")
    run_vcs(MAIN, "checkout", "-q", "main")

    run_vcs(MAIN, "checkout", "-q", "-b", "rebased-work")
    write(os.path.join(MAIN, "r.txt"), "same patch\n")
    run_vcs(MAIN, "add", "r.txt")
    run_vcs(MAIN, *IDENT, "commit", "-q", "-m", "add r.txt on rebased-work")
    run_vcs(MAIN, "checkout", "-q", "main")
    write(os.path.join(MAIN, "r.txt"), "same patch\n")  # identical content, its own commit
    run_vcs(MAIN, "add", "r.txt")
    run_vcs(MAIN, *IDENT, "commit", "-q", "-m", "add r.txt directly on main")

    run_vcs(MAIN, "checkout", "-q", "-b", "unmerged-work")
    write(os.path.join(MAIN, "u.txt"), "found nowhere else\n")
    run_vcs(MAIN, "add", "u.txt")
    run_vcs(MAIN, *IDENT, "commit", "-q", "-m", "unmerged-work's only copy")
    run_vcs(MAIN, "checkout", "-q", "main")

    run_vcs(MAIN, "checkout", "-q", "-b", "pushed-work")
    write(os.path.join(MAIN, "p.txt"), "pushed to the remote\n")
    run_vcs(MAIN, "add", "p.txt")
    run_vcs(MAIN, *IDENT, "commit", "-q", "-m", "pushed-work's commit")
    pushb = run_vcs(MAIN, "push", "-q", "origin", "pushed-work")
    require(pushb.returncode == 0, "pushing pushed-work failed: %s" % pushb.stderr.strip())
    run_vcs(MAIN, "checkout", "-q", "main")

    run_vcs(MAIN, "checkout", "-q", "-b", "backup/experiment")
    write(os.path.join(MAIN, "b.txt"), "protected by prefix, not by content\n")
    run_vcs(MAIN, "add", "b.txt")
    run_vcs(MAIN, *IDENT, "commit", "-q", "-m", "backup/experiment's own commit")
    run_vcs(MAIN, "checkout", "-q", "main")

    run_vcs(MAIN, "checkout", "-q", "-b", "wip-current")  # left checked out on purpose

    pushm = run_vcs(MAIN, "push", "-q", "origin", "main")
    require(pushm.returncode == 0, "re-pushing main failed: %s" % pushm.stderr.strip())
    fetch = run_vcs(MAIN, "fetch", "-q", "origin")
    require(fetch.returncode == 0, "fetching origin failed: %s" % fetch.stderr.strip())

    head = run_vcs(MAIN, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
    require(head.returncode == 0 and head.stdout.strip() == "origin/main",
            "origin/HEAD in MAIN does not resolve to origin/main: %r" % head.stdout.strip())
    cherry = run_vcs(MAIN, "cherry", "origin/main", "rebased-work")
    require(not any(line.startswith("+") for line in cherry.stdout.splitlines()),
            "rebased-work still carries a `+` against origin/main: %r" % cherry.stdout)


def setUpModule():
    os.environ["CLAUDE_CONFIG_DIR"] = CFG
    build_main_fixture()


def tearDownModule():
    shutil.rmtree(ROOT, ignore_errors=True)


# --------------------------------------------------------------------------- the anchor arm


class AnchorArmTests(unittest.TestCase):
    """The rebase-ghost fixture. Plan: 'The anchor arm is the rebase ghost. It must go red
    against a keep rule that tests ancestry alone.'"""

    def test_ancestry_alone_is_blind_to_the_rebase(self):
        branches = sweep.list_local_branches(MAIN)
        self.assertTrue(len(branches) > 0, "branch list must not be empty before any verdict")
        self.assertIn("rebased-work", branches)

        base = guard.resolve_default_base(MAIN)
        self.assertIsNotNone(base)

        # A keep rule that tests ancestry ALONE (Banchi's rule this build replaces) says KEEP,
        # because a rebase gave the commit a new id: ancestry cannot see the patch it carries.
        ancestor = guard.branch_is_ancestor(MAIN, base, "rebased-work")
        self.assertFalse(
            ancestor, "an ancestry-only rule must fail to see the rebase, or this arm proves "
                      "nothing this build exists for"
        )

    def test_the_patch_test_sees_through_the_rebase_and_reaps(self):
        branches = sweep.list_local_branches(MAIN)
        self.assertTrue(len(branches) > 0)
        self.assertIn("rebased-work", branches)

        base = guard.resolve_default_base(MAIN)
        self.assertIsNotNone(base)
        decision = sweep.decide_branch(MAIN, base, "rebased-work",
                                        sweep.DEFAULT_PROTECTED_PREFIXES, set())
        self.assertEqual(decision["action"], "reap")
        self.assertEqual(decision["reason"], "cherry-empty")


# --------------------------------------------------------------------------- branch decisions


class BranchDecisionTests(unittest.TestCase):
    def setUp(self):
        self.branches = sweep.list_local_branches(MAIN)
        self.assertTrue(len(self.branches) > 0, "branch list must not be empty")
        self.base = guard.resolve_default_base(MAIN)
        self.assertIsNotNone(self.base)

    def decide(self, branch, checked_out=frozenset(), prefixes=sweep.DEFAULT_PROTECTED_PREFIXES):
        self.assertIn(branch, self.branches, "the branch under test must be a real fixture branch")
        return sweep.decide_branch(MAIN, self.base, branch, prefixes, checked_out)

    def test_ancestor_reaps(self):
        decision = self.decide("ancestor-work")
        self.assertEqual(decision["action"], "reap")
        self.assertEqual(decision["reason"], "ancestor")

    def test_on_remote_reaps(self):
        decision = self.decide("pushed-work")
        self.assertEqual(decision["action"], "reap")
        self.assertEqual(decision["reason"], "on-remote")

    def test_unmerged_and_on_no_remote_is_the_only_copy_and_is_kept(self):
        decision = self.decide("unmerged-work")
        self.assertEqual(decision["action"], "keep")
        self.assertEqual(decision["reason"], "only-copy")

    # ------------------------------------------------------------- refusal 1: protected prefix
    def test_refusal_protected_prefix(self):
        # backup/experiment is unique and unpushed, so the emptiness test alone would REAP it.
        # The prefix refusal must still win and keep it.
        decision = self.decide("backup/experiment")
        self.assertEqual(decision["action"], "keep")
        self.assertTrue(decision["reason"].startswith("protected-prefix:"))

    def test_refusal_protected_prefix_from_the_opt_out_file(self):
        decision = self.decide("unmerged-work", prefixes=("backup/", "unmerged-"))
        self.assertEqual(decision["action"], "keep")
        self.assertEqual(decision["reason"], "protected-prefix:unmerged-")

    # ------------------------------------------------------------- refusal 2: checked out
    def test_refusal_checked_out_branch(self):
        decision = self.decide("wip-current", checked_out={"wip-current"})
        self.assertEqual(decision["action"], "keep")
        self.assertEqual(decision["reason"], "checked-out")

    # ------------------------------------------------------------- refusal 6: main/master/HEAD
    def test_refusal_default_branch_itself(self):
        decision = self.decide("main")
        self.assertEqual(decision["action"], "keep")
        self.assertEqual(decision["reason"], "default-branch")

    # ------------------------------------------------------------- refusal 7: unreadable subject
    def test_refusal_unreadable_subject_is_kept(self):
        blind = os.path.join(ROOT, "blind-branch")
        make_blind_git(blind)
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = blind + os.pathsep + old_path
        try:
            decision = self.decide("unmerged-work")
        finally:
            os.environ["PATH"] = old_path
        self.assertEqual(decision["action"], "keep")
        self.assertEqual(decision["reason"], "unreadable-subject")


class BaseResolutionRefusalTests(unittest.TestCase):
    """Refusal: no default branch answers (no origin/HEAD, no local main, no local master), so
    the whole repository is refused and reaps nothing, rather than guessed at."""

    def test_no_default_base_refuses_the_whole_repository(self):
        root = os.path.join(ROOT, "no-base-repo")
        make_repo(root, {"f.txt": "x\n"}, branch="trunk")
        run_vcs(root, "checkout", "-q", "-b", "topic")
        write(os.path.join(root, "t.txt"), "unique\n")
        run_vcs(root, "add", "t.txt")
        run_vcs(root, *IDENT, "commit", "-q", "-m", "topic's only copy")
        run_vcs(root, "checkout", "-q", "trunk")

        branches = sweep.list_local_branches(root)
        self.assertTrue(len(branches) > 0, "branch list must not be empty")
        self.assertIsNone(guard.resolve_default_base(root))

        result = sweep.sweep_repo(root, confirm=False, restore_log_path=os.path.join(ROOT, "x.log"))
        self.assertEqual(result["refused"], "no-default-base")
        self.assertEqual(result["branches"], [])


# --------------------------------------------------------------------------- worktree decisions


class WorktreeDecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = os.path.join(ROOT, "wt-repo")
        make_repo(cls.root, {"f.txt": "base\n"})

        cls.dirty = os.path.join(ROOT, "wt-dirty")
        run_vcs(cls.root, "worktree", "add", "-q", cls.dirty, "-b", "lane-dirty")
        write(os.path.join(cls.dirty, "new.txt"), "uncommitted\n")

        cls.locked = os.path.join(ROOT, "wt-locked")
        run_vcs(cls.root, "worktree", "add", "-q", cls.locked, "-b", "lane-locked")
        lock = run_vcs(cls.root, "worktree", "lock", cls.locked, "--reason", "held by lane-x")
        require(lock.returncode == 0, "locking wt-locked failed: %s" % lock.stderr.strip())

        cls.live = os.path.join(ROOT, "wt-live")
        run_vcs(cls.root, "worktree", "add", "-q", cls.live, "-b", "lane-live")
        started = this_process_start_ms()
        write_session("live-session-case", os.getpid(), started, cls.live)

        cls.dead = os.path.join(ROOT, "wt-dead")
        run_vcs(cls.root, "worktree", "add", "-q", cls.dead, "-b", "lane-dead")
        # A record naming THIS SAME live pid, but a startedAt that does not match it: a
        # recycled-pid shape. This arm must read the session as DEAD.
        write_session("mismatched-start-case", os.getpid(), started - 10_000_000, cls.dead)

        cls.removable = os.path.join(ROOT, "wt-removable")
        run_vcs(cls.root, "worktree", "add", "-q", cls.removable, "-b", "lane-removable")

        entries = sweep.parse_worktree_list(cls.root)
        require(entries is not None and len(entries) >= 6, "worktree list did not build as expected")
        cls.entries = {e["path"]: e for e in entries}

    def entry_for(self, path):
        self.assertTrue(len(self.entries) > 0, "worktree list must not be empty")
        # git worktree list can realpath differently on macOS (/tmp vs /private/tmp); resolve
        # both sides the same way the sweep itself does before comparing.
        target = os.path.normcase(os.path.realpath(path))
        for p, e in self.entries.items():
            if os.path.normcase(os.path.realpath(p)) == target:
                return e
        self.fail("no worktree-list entry found for %r among %r" % (path, list(self.entries)))

    # ------------------------------------------------------------- refusal 3: dirty
    def test_refusal_dirty_worktree(self):
        decision = sweep.decide_worktree(self.root, self.entry_for(self.dirty))
        self.assertEqual(decision["action"], "keep")
        self.assertEqual(decision["reason"], "dirty")

    # ------------------------------------------------------------- refusal 5: locked
    def test_refusal_locked_worktree_names_its_holder(self):
        decision = sweep.decide_worktree(self.root, self.entry_for(self.locked))
        self.assertEqual(decision["action"], "keep")
        self.assertTrue(decision["reason"].startswith("locked:"))
        self.assertIn("held by lane-x", decision["reason"])

    # ------------------------------------------------------------- refusal 4: live session
    def test_refusal_live_session_worktree(self):
        decision = sweep.decide_worktree(self.root, self.entry_for(self.live))
        self.assertEqual(decision["action"], "keep")
        self.assertEqual(decision["reason"], "live-session")

    def test_mismatched_start_time_reads_as_dead_and_is_reapable(self):
        """A record whose stored start time does not match the live process's own start time
        must NOT block the removal: a recycled pid cannot inherit a dead session's claim."""
        decision = sweep.decide_worktree(self.root, self.entry_for(self.dead))
        self.assertEqual(decision["action"], "reap")
        self.assertEqual(decision["reason"], "removable")

    def test_clean_unlocked_no_session_worktree_is_removable(self):
        decision = sweep.decide_worktree(self.root, self.entry_for(self.removable))
        self.assertEqual(decision["action"], "reap")
        self.assertEqual(decision["reason"], "removable")

    # ------------------------------------------------------------- refusal 7: unreadable subject
    def test_refusal_unreadable_subject_worktree(self):
        blind = os.path.join(ROOT, "blind-worktree")
        make_blind_git(blind)
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = blind + os.pathsep + old_path
        try:
            decision = sweep.decide_worktree(self.root, self.entry_for(self.removable))
        finally:
            os.environ["PATH"] = old_path
        self.assertEqual(decision["action"], "keep")
        self.assertEqual(decision["reason"], "unreadable-subject")


class PrimaryCheckoutExclusionTests(unittest.TestCase):
    """`sweep_repo` must never record a decision against the clone's one primary checkout, NO
    MATTER WHICH WORKTREE PATH IT WAS CALLED WITH. An earlier version of this file compared
    each worktree entry against the `root` argument alone, which is correct only when `root`
    already names the primary checkout; called with a LINKED worktree's own path instead, the
    real primary checkout used to fall through to `decide_worktree` like any other worktree and
    could be labeled `REAP removable`. `git worktree remove` on it then failed only because git
    itself refuses to remove a main working tree that way -- a refusal this suite must not lean
    on (CLAUDE.md, "a recovery control must not depend on the state it recovers"). This class
    calls `sweep_repo` with the LINKED worktree as `root`, the exact shape that exposed the
    defect, and asserts no decision was ever RECORDED for the primary checkout's path -- not
    that the directory still exists on disk, which git's own refusal could make true even with
    the defect back in place."""

    # A FRESH fixture per test method, not shared via setUpClass: a `confirm=True` case in this
    # class really does remove the linked worktree it is pointed at (it is not the primary
    # checkout, and this fixture leaves it clean/unlocked/session-free on purpose, so it is a
    # genuinely reapable worktree). Sharing one fixture across methods let an earlier `confirm`
    # case consume it before a later `preview` case ran, and that case's "at least one decision"
    # assertion failed for a reason that had nothing to do with the exclusion this class exists
    # to prove -- an empty-subject case exactly like the ones CLAUDE.md and this suite's own
    # module docstring warn against, just introduced from the test side this time.
    def setUp(self):
        tag = self.id().rsplit(".", 1)[-1]
        self.primary = os.path.join(ROOT, "primary-checkout-%s" % tag)
        make_repo(self.primary, {"f.txt": "base\n"})
        self.linked = os.path.join(ROOT, "primary-checkout-linked-%s" % tag)
        require(run_vcs(self.primary, "worktree", "add", "-q", self.linked, "-b", "lane-x")
                .returncode == 0, "worktree add for the exclusion fixture")
        require(os.path.isdir(self.linked), "fixture: linked worktree exists")

    def _decisions(self, root, confirm):
        log_path = os.path.join(ROOT, "primary-exclusion-%s.log" % self.id().rsplit(".", 1)[-1])
        return sweep.sweep_repo(root, confirm=confirm, restore_log_path=log_path)

    def _primary_recorded(self, result):
        primary_real = os.path.normcase(os.path.realpath(self.primary))
        for w in result["worktrees"]:
            if os.path.normcase(os.path.realpath(w["path"])) == primary_real:
                return w
        return None

    def test_no_decision_is_recorded_against_the_primary_checkout_when_swept_via_a_linked_worktree(self):
        result = self._decisions(self.linked, confirm=False)
        self.assertTrue(len(result["worktrees"]) > 0,
                         "fixture must produce at least one worktree decision to mean anything")
        recorded = self._primary_recorded(result)
        self.assertIsNone(
            recorded,
            "the primary checkout must never appear in the worktree decisions at all, got: %r"
            % (recorded,),
        )

    def test_confirm_via_a_linked_worktree_never_attempts_to_remove_the_primary_checkout(self):
        result = self._decisions(self.linked, confirm=True)
        self.assertTrue(len(result["worktrees"]) > 0,
                         "fixture must produce at least one worktree decision to mean anything")
        self.assertIsNone(self._primary_recorded(result))
        self.assertTrue(os.path.isdir(self.primary),
                         "the primary checkout must survive even a --confirm sweep")

    def test_swept_via_its_own_root_the_primary_checkout_is_still_excluded(self):
        """Same exclusion, the ordinary call shape (root IS the primary checkout), so the fix
        does not regress the case the old root-comparison already handled."""
        result = self._decisions(self.primary, confirm=False)
        self.assertTrue(len(result["worktrees"]) > 0, "fixture must produce a decision")
        self.assertIsNone(self._primary_recorded(result))


# --------------------------------------------------------------------------- discovery


class DiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = os.path.join(ROOT, "discover-root")
        os.makedirs(cls.dir, exist_ok=True)
        cls.repo = os.path.join(cls.dir, "repoA")
        make_repo(cls.repo, {"f.txt": "x\n"})
        cls.linked = os.path.join(cls.dir, "repoA-worktree")
        run_vcs(cls.repo, "worktree", "add", "-q", cls.linked, "-b", "lane")
        os.makedirs(os.path.join(cls.dir, "not-a-repo"), exist_ok=True)

    def test_discovers_ordinary_checkouts_only(self):
        found = sweep.discover_repos(self.dir)
        self.assertTrue(len(found) > 0, "discovery must not come back empty")
        self.assertIn(self.repo, found)

    def test_never_discovers_a_linked_worktree_as_its_own_repository(self):
        found = sweep.discover_repos(self.dir)
        self.assertTrue(len(found) > 0)
        self.assertNotIn(self.linked, found)

    def test_never_discovers_a_plain_directory(self):
        found = sweep.discover_repos(self.dir)
        self.assertTrue(len(found) > 0)
        self.assertNotIn(os.path.join(self.dir, "not-a-repo"), found)


# --------------------------------------------------------------------------- the opt-out file


def make_optout_repo(name, optout_json=None):
    """A repository with one reapable branch ("feature", an ancestor of main): the subject a
    sweep would touch if it were not refused. Real git, no mocking."""
    root = os.path.join(ROOT, name)
    make_repo(root, {"f.txt": "x\n"})
    run_vcs(root, "checkout", "-q", "-b", "feature")
    run_vcs(root, "checkout", "-q", "main")
    if optout_json is not None:
        write(os.path.join(root, ".claude", "janitor.json"), optout_json)
    return root


class OptOutTests(unittest.TestCase):
    def test_absent_file_means_swept_with_the_default_prefix(self):
        root = os.path.join(ROOT, "optout-absent")
        make_repo(root, {"f.txt": "x\n"})
        enabled, prefixes, ok = sweep.load_optout(root)
        self.assertTrue(ok)
        self.assertTrue(enabled)
        self.assertEqual(prefixes, ("backup/",))

    def test_sweep_false_opts_the_whole_repository_out(self):
        root = os.path.join(ROOT, "optout-false")
        make_repo(root, {"f.txt": "x\n"})
        write(os.path.join(root, ".claude", "janitor.json"), json.dumps({"sweep": False}))
        result = sweep.sweep_repo(root, confirm=False, restore_log_path=os.path.join(ROOT, "x2.log"))
        self.assertEqual(result["refused"], "opted-out")

    def test_sweep_true_explicitly_still_sweeps(self):
        root = make_optout_repo("optout-sweep-true", json.dumps({"sweep": True}))
        branches = sweep.list_local_branches(root)
        self.assertTrue(len(branches) > 0, "branch list must not be empty before any verdict")
        self.assertIn("feature", branches)
        enabled, prefixes, ok = sweep.load_optout(root)
        self.assertTrue(ok)
        self.assertTrue(enabled)
        result = sweep.sweep_repo(root, confirm=False,
                                   restore_log_path=os.path.join(ROOT, "x-true.log"))
        self.assertIsNone(result["refused"])
        reaped = [b for b in result["branches"] if b["action"] == "reap"]
        self.assertTrue(len(reaped) > 0, "a real reapable branch must show up as reaped")

    def test_protected_prefixes_extend_the_default(self):
        root = os.path.join(ROOT, "optout-prefixes")
        make_repo(root, {"f.txt": "x\n"})
        write(os.path.join(root, ".claude", "janitor.json"),
              json.dumps({"protectedPrefixes": ["experimental/"]}))
        enabled, prefixes, ok = sweep.load_optout(root)
        self.assertTrue(ok)
        self.assertTrue(enabled)
        self.assertIn("backup/", prefixes)
        self.assertIn("experimental/", prefixes)

    def test_unparseable_file_refuses_the_whole_repository(self):
        root = os.path.join(ROOT, "optout-broken")
        make_repo(root, {"f.txt": "x\n"})
        write(os.path.join(root, ".claude", "janitor.json"), "{ not json at all")
        result = sweep.sweep_repo(root, confirm=False, restore_log_path=os.path.join(ROOT, "x3.log"))
        self.assertEqual(result["refused"], "unreadable-optout")

    # --------------------- a present key whose value is malformed refuses, not defaults ---------

    def test_sweep_string_false_refuses_the_whole_repository(self):
        # The exact regression this build guards: `"sweep": "false"`, the STRING, must never be
        # treated as truthy-and-swept. It must refuse the repository the way an unreadable file
        # does, not fall through to the permissive default.
        root = make_optout_repo("optout-sweep-string-false", json.dumps({"sweep": "false"}))
        branches = sweep.list_local_branches(root)
        self.assertTrue(len(branches) > 0, "branch list must not be empty before any verdict")
        self.assertIn("feature", branches)
        enabled, prefixes, ok = sweep.load_optout(root)
        self.assertFalse(ok, "a non-boolean sweep value must not read as ok")
        result = sweep.sweep_repo(root, confirm=False,
                                   restore_log_path=os.path.join(ROOT, "x-str.log"))
        self.assertEqual(result["refused"], "unreadable-optout")
        self.assertEqual(result["branches"], [], "a refused repository must decide on nothing")

    def test_sweep_zero_refuses_the_whole_repository(self):
        root = make_optout_repo("optout-sweep-zero", json.dumps({"sweep": 0}))
        branches = sweep.list_local_branches(root)
        self.assertTrue(len(branches) > 0, "branch list must not be empty before any verdict")
        self.assertIn("feature", branches)
        enabled, prefixes, ok = sweep.load_optout(root)
        self.assertFalse(ok, "0 is not a bool in Python's own sense here: it must refuse")
        result = sweep.sweep_repo(root, confirm=False,
                                   restore_log_path=os.path.join(ROOT, "x-zero.log"))
        self.assertEqual(result["refused"], "unreadable-optout")
        self.assertEqual(result["branches"], [])

    def test_sweep_null_refuses_the_whole_repository(self):
        root = make_optout_repo("optout-sweep-null", json.dumps({"sweep": None}))
        branches = sweep.list_local_branches(root)
        self.assertTrue(len(branches) > 0, "branch list must not be empty before any verdict")
        self.assertIn("feature", branches)
        enabled, prefixes, ok = sweep.load_optout(root)
        self.assertFalse(ok, "null is present and is not a boolean: it must refuse")
        result = sweep.sweep_repo(root, confirm=False,
                                   restore_log_path=os.path.join(ROOT, "x-null.log"))
        self.assertEqual(result["refused"], "unreadable-optout")
        self.assertEqual(result["branches"], [])

    def test_protected_prefixes_bare_string_refuses_the_whole_repository(self):
        # "archive/" the bare string is not a list, so the intended protection can be neither
        # read nor safely ignored: refuse the repository rather than silently protect nothing.
        root = make_optout_repo("optout-prefixes-bare-string",
                                 json.dumps({"protectedPrefixes": "archive/"}))
        branches = sweep.list_local_branches(root)
        self.assertTrue(len(branches) > 0, "branch list must not be empty before any verdict")
        self.assertIn("feature", branches)
        enabled, prefixes, ok = sweep.load_optout(root)
        self.assertFalse(ok, "a bare string is not a list of strings: it must refuse")
        result = sweep.sweep_repo(root, confirm=False,
                                   restore_log_path=os.path.join(ROOT, "x-prefstr.log"))
        self.assertEqual(result["refused"], "unreadable-optout")
        self.assertEqual(result["branches"], [])


# --------------------------------------------------------------------------- the tombstone


class TombstoneTests(unittest.TestCase):
    def test_reap_writes_a_tombstone_and_a_restore_log_line_before_deleting(self):
        root = os.path.join(ROOT, "tomb-repo")
        make_repo(root, {"f.txt": "x\n"})
        run_vcs(root, "checkout", "-q", "-b", "old-topic")
        run_vcs(root, "checkout", "-q", "main")  # old-topic == main's tip: an ancestor, reapable

        branches = sweep.list_local_branches(root)
        self.assertTrue(len(branches) > 0)
        self.assertIn("old-topic", branches)
        tip = run_vcs(root, "rev-parse", "old-topic").stdout.strip()
        self.assertTrue(tip)

        log_path = os.path.join(ROOT, "tomb-restore.jsonl")
        result = sweep.sweep_repo(root, confirm=True, restore_log_path=log_path)
        self.assertIsNone(result["refused"])
        decision = next(b for b in result["branches"] if b["name"] == "old-topic")
        self.assertEqual(decision["action"], "reap")
        self.assertNotIn("error", decision)

        self.assertNotIn("old-topic", sweep.list_local_branches(root))
        tomb = run_vcs(root, "rev-parse", sweep.TOMBSTONE_REF_PREFIX + "old-topic")
        self.assertEqual(tomb.returncode, 0)
        self.assertEqual(tomb.stdout.strip(), tip)

        entries = sweep.read_restore_log(log_path)
        self.assertTrue(len(entries) > 0, "restore log must not be empty")
        matches = [e for e in entries if e.get("branch") == "old-topic" and e.get("repo") == root]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["commit"], tip)
        self.assertIsInstance(matches[0]["time_ms"], int)
        self.assertLessEqual(abs(int(time.time() * 1000) - matches[0]["time_ms"]), 60_000)

    def test_a_failed_delete_still_leaves_the_tombstone_and_the_branch(self):
        """The tombstone and the log line land BEFORE the delete. If the delete then fails, the
        branch is still there (nothing lost) and the tombstone still names its tip (nothing
        unrecorded)."""
        root = os.path.join(ROOT, "tomb-repo-fail")
        make_repo(root, {"f.txt": "x\n"})
        run_vcs(root, "checkout", "-q", "-b", "old-topic-2")
        run_vcs(root, "checkout", "-q", "main")

        branches = sweep.list_local_branches(root)
        self.assertTrue(len(branches) > 0)
        self.assertIn("old-topic-2", branches)
        tip = run_vcs(root, "rev-parse", "old-topic-2").stdout.strip()

        real_git = guard._git

        def failing_git(where, *args):
            if args[:2] == ("branch", "-D"):
                return subprocess.CompletedProcess(args, 1, "", "simulated failure")
            return real_git(where, *args)

        log_path = os.path.join(ROOT, "tomb-restore-fail.jsonl")
        decision = {"name": "old-topic-2", "action": "reap", "reason": "ancestor"}
        guard._git = failing_git
        try:
            sweep.reap_branch(root, "old-topic-2", decision, log_path)
        finally:
            guard._git = real_git

        self.assertIn("error", decision)
        self.assertIn("old-topic-2", sweep.list_local_branches(root))
        tomb = run_vcs(root, "rev-parse", sweep.TOMBSTONE_REF_PREFIX + "old-topic-2")
        self.assertEqual(tomb.returncode, 0)
        self.assertEqual(tomb.stdout.strip(), tip)
        entries = sweep.read_restore_log(log_path)
        self.assertTrue(len(entries) > 0)
        self.assertTrue(any(e.get("branch") == "old-topic-2" for e in entries))


# --------------------------------------------------------------------------- worktree removal


class WorktreeRemovalTests(unittest.TestCase):
    def test_confirm_removes_a_reapable_worktree(self):
        root = os.path.join(ROOT, "wt-remove-repo")
        make_repo(root, {"f.txt": "x\n"})
        target = os.path.join(ROOT, "wt-remove-target")
        run_vcs(root, "worktree", "add", "-q", target, "-b", "lane-remove")

        entries = sweep.parse_worktree_list(root)
        self.assertTrue(entries is not None and len(entries) > 0)

        log_path = os.path.join(ROOT, "wt-remove.log")
        result = sweep.sweep_repo(root, confirm=True, restore_log_path=log_path)
        self.assertIsNone(result["refused"])
        matches = [w for w in result["worktrees"]
                   if os.path.normcase(os.path.realpath(w["path"]))
                   == os.path.normcase(os.path.realpath(target))]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["action"], "reap")
        self.assertNotIn("error", matches[0])
        self.assertFalse(os.path.isdir(target))


# --------------------------------------------------------------------------- the --confirm gate
#
# Every OTHER confirm=False call in this file (BaseResolutionRefusalTests,
# OptOutTests.test_sweep_false_..., OptOutTests.test_unparseable_file_...) hits a REFUSED
# repository before either loop in sweep_repo ever runs, so none of them can prove anything about
# the gate itself: a refused repository never reaches `if confirm and decision["action"] ==
# "reap":` at all. This class is the one arm that puts a REAPABLE branch and a REMOVABLE worktree
# in front of a confirm=False sweep and checks that preview leaves both alone. Its absence is a
# MEASURED hole: janitor/mutate_sweep.py's `--confirm: reap branches for real with no --confirm
# on the line` mutant (the `confirm and` dropped from that same line) passed all 31 cases in this
# file before this class existed.
class ConfirmGateTests(unittest.TestCase):
    def test_preview_names_reapable_subjects_but_touches_neither(self):
        root = os.path.join(ROOT, "confirm-gate-repo")
        make_repo(root, {"f.txt": "x\n"})
        # A branch identical to main's own tip: the ancestor test alone proves it empty, so it is
        # REAPABLE, not merely present.
        run_vcs(root, "checkout", "-q", "-b", "preview-should-not-touch")
        run_vcs(root, "checkout", "-q", "main")
        # A clean, unlocked worktree with no live session recorded against it: REMOVABLE, not
        # merely registered.
        target = os.path.join(ROOT, "confirm-gate-worktree")
        run_vcs(root, "worktree", "add", "-q", target, "-b", "lane-confirm-gate")

        # THE SUBJECT SET MUST NOT BE EMPTY before any verdict about it means anything (the same
        # rule every other case in this file follows; see the module docstring).
        branches_before = sweep.list_local_branches(root)
        self.assertTrue(len(branches_before) > 0, "branch list must not be empty")
        self.assertIn("preview-should-not-touch", branches_before)
        entries_before = sweep.parse_worktree_list(root)
        self.assertTrue(entries_before is not None and len(entries_before) > 0,
                         "worktree list must not be empty")
        self.assertTrue(any(
            os.path.normcase(os.path.realpath(e["path"]))
            == os.path.normcase(os.path.realpath(target)) for e in entries_before
        ))

        log_path = os.path.join(ROOT, "confirm-gate.log")
        result = sweep.sweep_repo(root, confirm=False, restore_log_path=log_path)
        self.assertIsNone(result["refused"])

        # The preview must have NAMED both subjects as reapable. A preview that silently reported
        # nothing at all -- as empty a result as an empty subject set -- would pass a weaker
        # assertion than this one just as wrongly.
        branch_decision = next(
            (b for b in result["branches"] if b["name"] == "preview-should-not-touch"), None)
        self.assertIsNotNone(branch_decision, "the branch must appear in the preview at all")
        self.assertEqual(branch_decision["action"], "reap")

        worktree_decision = next(
            (w for w in result["worktrees"]
             if os.path.normcase(os.path.realpath(w["path"]))
             == os.path.normcase(os.path.realpath(target))), None)
        self.assertIsNotNone(worktree_decision, "the worktree must appear in the preview at all")
        self.assertEqual(worktree_decision["action"], "reap")

        # And PREVIEW MUST NOT HAVE TOUCHED EITHER ONE: this is the assertion the gate itself
        # lives or dies on.
        branches_after = sweep.list_local_branches(root)
        self.assertIn("preview-should-not-touch", branches_after,
                       "a preview run with confirm=False deleted a branch")
        entries_after = sweep.parse_worktree_list(root)
        self.assertTrue(entries_after is not None)
        self.assertTrue(any(
            os.path.normcase(os.path.realpath(e["path"]))
            == os.path.normcase(os.path.realpath(target)) for e in entries_after
        ), "a preview run with confirm=False removed a worktree")
        self.assertTrue(os.path.isdir(target),
                         "a preview run with confirm=False deleted a worktree's directory")


# --------------------------------------------------------------------------- the purge


class PurgeTests(unittest.TestCase):
    def setUp(self):
        self.repo = os.path.join(ROOT, "purge-repo")
        if not os.path.isdir(self.repo):
            make_repo(self.repo, {"f.txt": "x\n"})
        self.log_path = os.path.join(ROOT, "purge-%s.jsonl" % self.id().rsplit(".", 1)[-1])

    def write_log(self, lines):
        with open(self.log_path, "w", encoding="utf-8") as handle:
            for line in lines:
                handle.write(json.dumps(line) + "\n")

    def test_an_old_tombstone_previews_as_purge_and_is_not_dropped_without_confirm(self):
        run_vcs(self.repo, "update-ref", "refs/janitor/reaped/old-one", "HEAD")
        now = int(time.time() * 1000)
        self.write_log([{"repo": self.repo, "branch": "old-one",
                          "commit": "deadbeef", "time_ms": now - 91 * 86400000}])
        entries = sweep.read_restore_log(self.log_path)
        self.assertTrue(len(entries) > 0)

        decisions = sweep.purge_tombstones(self.log_path, confirm=False, now_ms=now)
        self.assertTrue(len(decisions) > 0)
        self.assertEqual(decisions[0]["action"], "purge")
        still_there = run_vcs(self.repo, "rev-parse", "refs/janitor/reaped/old-one")
        self.assertEqual(still_there.returncode, 0, "preview must not have dropped the ref")

    def test_confirm_drops_a_tombstone_past_90_days(self):
        run_vcs(self.repo, "update-ref", "refs/janitor/reaped/old-two", "HEAD")
        now = int(time.time() * 1000)
        self.write_log([{"repo": self.repo, "branch": "old-two",
                          "commit": "deadbeef", "time_ms": now - 91 * 86400000}])
        decisions = sweep.purge_tombstones(self.log_path, confirm=True, now_ms=now)
        self.assertTrue(len(decisions) > 0)
        self.assertEqual(decisions[0]["action"], "purge")
        self.assertNotIn("error", decisions[0])
        gone = run_vcs(self.repo, "rev-parse", "refs/janitor/reaped/old-two")
        self.assertNotEqual(gone.returncode, 0, "the tombstone ref must be gone after confirm")

    def test_a_tombstone_under_90_days_is_kept(self):
        run_vcs(self.repo, "update-ref", "refs/janitor/reaped/young", "HEAD")
        now = int(time.time() * 1000)
        self.write_log([{"repo": self.repo, "branch": "young",
                          "commit": "deadbeef", "time_ms": now - 5 * 86400000}])
        decisions = sweep.purge_tombstones(self.log_path, confirm=True, now_ms=now)
        self.assertTrue(len(decisions) > 0)
        self.assertEqual(decisions[0]["action"], "keep")
        still_there = run_vcs(self.repo, "rev-parse", "refs/janitor/reaped/young")
        self.assertEqual(still_there.returncode, 0)

    def test_an_unreadable_log_entry_is_kept_not_purged(self):
        now = int(time.time() * 1000)
        self.write_log([{"repo": self.repo, "time_ms": now - 200 * 86400000}])  # no branch field
        decisions = sweep.purge_tombstones(self.log_path, confirm=True, now_ms=now)
        self.assertTrue(len(decisions) > 0)
        self.assertEqual(decisions[0]["action"], "keep")
        self.assertEqual(decisions[0]["reason"], "unreadable-entry")


if __name__ == "__main__":
    unittest.main(verbosity=2)
