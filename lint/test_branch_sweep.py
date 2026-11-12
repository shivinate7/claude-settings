#!/usr/bin/env python3
"""Verdict cases for the branch sweep (roadmap step cloud-branch-delete).

A branch is deleted only when its last commit is on the default branch or on an archive/* branch (the standing grant
of the Oct 30 session, .claude/CLAUDE.md). main, master, archive/*, HEAD, and a branch with an open pull request are kept.

CLI the builder provides (actions/branch-sweep/sweep.py):
    python3 actions/branch-sweep/sweep.py --repo DIR [--default NAME] [--open-head NAME]...
It reads refs/remotes/origin/* of DIR, the refs actions/checkout with fetch-depth 0 leaves. --default names the default
branch (main when not given). Each --open-head names a branch with an open pull request. It prints one line per branch:
`<delete|keep> <name> <reason>`. origin/HEAD is no branch and gets no line. A repo it cannot read exits nonzero and
prints no delete line.

On the old commit the sweep does not exist, so no branch gets a verdict. The keep cases share that red. Their own red
needs a built sweep that wrongly deletes, which the builder's mutant shows after the build.
Run: python3 lint/test_branch_sweep.py
"""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  fixture teardown removes the tree (testing/tracked_tree.py)

SWEEP = os.path.join(HERE, "..", "actions", "branch-sweep", "sweep.py")
ENV = _test_git.apply(dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
                           GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t"))
RUN_FOLDER = _test_temp.run_folder()


def git(cwd, *args, stdin=None):
    done = subprocess.run(["git", "-C", cwd, *args], input=stdin, capture_output=True, text=True, env=ENV)
    if done.returncode:
        raise RuntimeError("git %s failed: %s" % (" ".join(args), done.stderr.strip()))
    return done.stdout.strip()


class Repo:
    """A fixture repo whose remote-tracking refs are the branches of origin."""

    def __init__(self, test):
        self.root = tempfile.mkdtemp(prefix="bsweep-", dir=RUN_FOLDER)
        test.addCleanup(tracked_tree.rm_tree, self.root)
        git(self.root, "init", "-q")
        self.tree = git(self.root, "mktree", stdin="")

    def commit(self, msg, parent=None):
        args = ["commit-tree", self.tree, "-m", msg]
        if parent:
            args += ["-p", parent]
        return git(self.root, *args)

    def branch(self, name, sha):
        git(self.root, "update-ref", "refs/remotes/origin/" + name, sha)

    def bulk(self, pairs):
        git(self.root, "update-ref", "--stdin", stdin="".join("update refs/remotes/origin/%s %s\n" % p for p in pairs))


def sweep(root, *args):
    """(stdout, returncode) of the sweep on one repo. The exit code is not a verdict: a missing sweep prints nothing."""
    done = subprocess.run([sys.executable, SWEEP, "--repo", root, *args], capture_output=True, text=True, env=ENV)
    return done.stdout, done.returncode


def verdicts(out):
    """{name: verdict} from the sweep's lines. A line that is not `<verdict> <name> <reason>` gives no verdict."""
    got = {}
    for line in out.splitlines():
        parts = line.split(" ", 2)
        if len(parts) == 3 and parts[0] in ("delete", "keep") and parts[2].strip():
            got[parts[1]] = parts[0]
    return got


class Verdicts(unittest.TestCase):
    def main_chain(self):
        """A repo whose origin/main is two commits, m1 then m2."""
        repo = Repo(self)
        m1 = repo.commit("main 1")
        m2 = repo.commit("main 2", parent=m1)
        repo.branch("main", m2)
        return repo, m1, m2

    def check(self, repo, want, *args):
        """Scope first: the sweep names every branch the fixture made. Then each verdict is the wanted one."""
        got = verdicts(sweep(repo.root, *args)[0])
        for name in sorted(want):
            self.assertIn(name, got, "%s: the sweep printed no verdict line for it" % name)
        for name in sorted(want):
            self.assertEqual(got[name], want[name], "%s: want %s, got %s" % (name, want[name], got[name]))
        return got

    def test_merged_into_default_is_deleted(self):
        repo, m1, _ = self.main_chain()
        repo.branch("feature/merged", m1)  # an ancestor of main: its last commit is on the default branch
        self.check(repo, {"main": "keep", "feature/merged": "delete"})

    def test_head_on_archive_is_deleted(self):
        repo, m1, _ = self.main_chain()
        u1 = repo.commit("unmerged work", parent=m1)
        repo.branch("feature/archived", u1)
        repo.branch("archive/old-u1", u1)  # the archive holds the branch's last commit
        self.check(repo, {"main": "keep", "feature/archived": "delete", "archive/old-u1": "keep"})

    def test_unmerged_is_kept(self):
        repo, m1, m2 = self.main_chain()
        repo.branch("feature/wip", repo.commit("forked from an older main", parent=m1))
        repo.branch("feature/ahead", repo.commit("ahead of main", parent=m2))
        self.check(repo, {"main": "keep", "feature/wip": "keep", "feature/ahead": "keep"})

    def test_archive_branch_is_kept(self):
        repo, m1, _ = self.main_chain()
        repo.branch("archive/merged-one", m1)  # merged into main, still never deleted
        repo.branch("feature/merged", m1)
        self.check(repo, {"main": "keep", "archive/merged-one": "keep", "feature/merged": "delete"})

    def test_open_pr_head_is_kept(self):
        repo, m1, _ = self.main_chain()
        repo.branch("feature/merged-pr", m1)  # merged, but a pull request is open on it
        repo.branch("feature/merged", m1)
        self.check(repo, {"main": "keep", "feature/merged-pr": "keep", "feature/merged": "delete"},
                   "--open-head", "feature/merged-pr")

    def test_protected_names_are_kept(self):
        repo, _, m2 = self.main_chain()
        repo.branch("master", m2)  # merged into main, still a protected name
        git(repo.root, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        got = self.check(repo, {"main": "keep", "master": "keep"})
        self.assertNotIn("HEAD", got, "HEAD: origin/HEAD is no branch and got a verdict line")

    def test_empty_repo_deletes_nothing(self):
        repo, _, _ = self.main_chain()
        got = self.check(repo, {"main": "keep"})
        self.assertEqual(got, {"main": "keep"}, "the only branch is main: the sweep named more branches")

    def test_full_size_fixture_gets_one_verdict_per_branch(self):
        repo, m1, _ = self.main_chain()
        pairs, want = [], {"main": "keep"}
        for i in range(200):
            name = "feature/merged-%03d" % i
            pairs.append((name, m1))
            want[name] = "delete"
        for i in range(100):
            name = "feature/wip-%03d" % i
            pairs.append((name, repo.commit("wip %d" % i, parent=m1)))
            want[name] = "keep"
        repo.bulk(pairs)
        self.check(repo, want)

    def test_unreadable_repo_fails_closed(self):
        repo, m1, _ = self.main_chain()
        repo.branch("feature/merged", m1)
        self.check(repo, {"main": "keep", "feature/merged": "delete"})  # a readable repo first: scope, then verdicts
        not_repo = tempfile.mkdtemp(prefix="bsweep-notrepo-", dir=RUN_FOLDER)
        self.addCleanup(tracked_tree.rm_tree, not_repo)
        out, rc = sweep(not_repo)
        self.assertNotEqual(rc, 0, "a repo it cannot read exited 0: a sweep that cannot read refs must fail")
        self.assertFalse(any(line.startswith("delete ") for line in out.splitlines()),
                         "a repo it cannot read printed a delete line")


def tearDownModule():
    if os.path.isdir(RUN_FOLDER):
        tracked_tree.rm_tree(RUN_FOLDER)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    unittest.main()
