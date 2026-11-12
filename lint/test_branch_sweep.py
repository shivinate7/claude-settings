#!/usr/bin/env python3
"""Verdict cases for the branch sweep (roadmap step cloud-branch-delete).

A branch is deleted only when its last commit is on the default branch or on an archive/* branch (the standing grant
of the Oct 30 session, .claude/CLAUDE.md). main, master, roadmap, stable, archive/*, HEAD, and a branch that is the head or the
base of an open pull request are kept. A name with a character outside [A-Za-z0-9._/-], or one that starts with `-`, is kept too: the name goes raw
into a DELETE URL, and `#` ends the path.

CLI the builder provides (actions/branch-sweep/sweep.py):
    python3 actions/branch-sweep/sweep.py --repo DIR [--default NAME] [--open-head NAME]...
It reads refs/remotes/origin/* of DIR, the refs actions/checkout with fetch-depth 0 leaves. --default names the default
branch (main when not given). Each --open-head names a branch with an open pull request. It prints one line per branch:
`<delete|keep> <name> <reason>`. origin/HEAD is no branch and gets no line. A repo it cannot read exits nonzero and
prints no delete line.

The DeleteStep cases run the open-PR read step, then the delete step, from .github/workflows/branch-sweep.yml, each under
bash -eo pipefail as GitHub runs `shell: bash`. A fake gh serves the open pull requests through the workflow's own --jq
filter (jq) and refuses or accepts each DELETE. Before each DELETE the workflow reads the branch's tip with
`gh api repos/REPO/git/ref/heads/NAME` (singular: the plural git/refs/heads/ GET can return a list). The fake answers
that read from a map of branch to sha, or to an "HTTP <status>" refusal, and the sha is the checkout's tip unless a
case moves it. Any other gh call the fake does not know fails loudly.
Run: python3 lint/test_branch_sweep.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  fixture teardown removes the tree (testing/tracked_tree.py)

SWEEP = os.path.join(HERE, "..", "actions", "branch-sweep", "sweep.py")
WORKFLOW = os.path.join(HERE, "..", ".github", "workflows", "branch-sweep.yml")
ENV = _test_git.apply(dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
                           GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t"))
RUN_FOLDER = _test_temp.run_folder()

REPO_PATH = "repos/owner/repo"  # the REPO the run env names

# Stands in for gh: logs each call. A pulls call prints FAKE_GH_PULLS through the --jq filter the call names.
# A DELETE is refused with the HTTP status named in FAKE_GH_REFUSE. A tip read (GET git/ref/heads/NAME) answers from
# FAKE_GH_TIPS, a JSON map of branch to sha, or to "HTTP <status>" for a refusal. Any other call fails loudly.
FAKE_GH = """#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_GH_LOG"
jq_filter() {
  filter=""
  take=""
  for arg in "$@"; do
    if [ -n "$take" ]; then
      filter="$arg"
      take=""
    elif [ "$arg" = "--jq" ] || [ "$arg" = "-q" ]; then
      take=1
    fi
  done
  printf '%s' "$filter"
}
case "$*" in
  *"/pulls?"*)
    jq -r "$(jq_filter "$@")" < "$FAKE_GH_PULLS"
    exit $? ;;
  *DELETE*)
    if [ -n "$FAKE_GH_REFUSE" ]; then
      echo "gh: refused (HTTP $FAKE_GH_REFUSE)" >&2
      exit 1
    fi
    exit 0 ;;
  *"/git/ref/heads/"*)
    ref="${*#*/git/ref/heads/}"
    ref="${ref%% *}"
    value=$(jq -r --arg n "$ref" '.[$n] // "HTTP 500"' "$FAKE_GH_TIPS")
    case "$value" in
      "HTTP "*)
        echo "gh: refused ($value)" >&2
        exit 1 ;;
    esac
    filter=$(jq_filter "$@")
    if [ -n "$filter" ]; then
      printf '{"object":{"sha":"%s"}}\\n' "$value" | jq -r "$filter"
    else
      printf '{"object":{"sha":"%s"}}\\n' "$value"
    fi
    exit $? ;;
esac
echo "fake gh: unhandled call: $*" >&2
exit 1
"""


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


def deletes(verdict_text):
    """Sorted names that a verdict text marks delete."""
    return sorted(line.split(" ", 2)[1] for line in verdict_text.splitlines() if line.startswith("delete "))


def deleted(calls):
    """Sorted names of the branches that DELETE calls name."""
    return sorted(call.split("/heads/", 1)[1] for call in calls if "/heads/" in call)


def read_text(path):
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read()


def delete_calls(log):
    """The gh calls of a run that are DELETEs."""
    return [line for line in log if "DELETE" in line]


def call_on_ref(line, name, delete):
    """True when a gh call line is the DELETE (delete True) or the tip read (delete False) of one branch."""
    path = "%s/git/%s/heads/%s" % (REPO_PATH, "refs" if delete else "ref", name)
    return ("DELETE" in line) == delete and path in line.split()


def ref_call_index(log, name, delete):
    """Index in the gh log of a branch's DELETE or tip read, or -1 when no call made it."""
    for i, line in enumerate(log):
        if call_on_ref(line, name, delete):
            return i
    return -1


def annotations(done, *prefixes):
    """The annotation lines a step printed that start with one of the prefixes, such as ::warning::."""
    return [line for line in (done.stdout + done.stderr).splitlines() if line.startswith(prefixes)]


def log_lines_naming(done, verdict_text, name):
    """The lines a step printed past its verdict echo that name a branch."""
    echoed = set(verdict_text.splitlines())
    return [line for line in (done.stdout + done.stderr).splitlines() if name in line and line not in echoed]


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

    def test_stable_merged_into_default_is_kept(self):
        repo, m1, _ = self.main_chain()
        repo.branch("stable", m1)  # on main's history: the plan moves stable with green main, so each main push would reach it
        repo.branch("feature/merged", m1)  # control: merged and unprotected, so the sweep does delete it
        self.check(repo, {"main": "keep", "stable": "keep", "feature/merged": "delete"})
        out, _ = sweep(repo.root)
        reasons = {line.split(" ", 2)[1]: line.split(" ", 2)[2] for line in out.splitlines() if len(line.split(" ", 2)) == 3}
        self.assertIn("protected", reasons["stable"], "stable: the reason does not name it protected: %r" % reasons["stable"])

    def test_merged_name_outside_the_safe_set_is_kept(self):
        repo, m1, _ = self.main_chain()
        unsafe = ["-x", "a%2Fb", "a+b", "feat#1"]
        for name in unsafe:
            repo.branch(name, m1)  # merged into main, but the name would reach the DELETE URL raw
        want = {"main": "keep"}
        want.update((name, "keep") for name in unsafe)
        self.check(repo, want)

    def test_merged_name_of_safe_characters_is_deleted(self):
        repo, m1, _ = self.main_chain()
        repo.branch("feat-1.2_x/y", m1)  # letters, digits, dot, underscore, dash and slash only: no finding
        self.check(repo, {"main": "keep", "feat-1.2_x/y": "delete"})

    def test_roadmap_merged_into_main_is_kept(self):
        repo, m1, _ = self.main_chain()
        repo.branch("roadmap", m1)  # merged into main, still never deleted: it holds the roadmap record
        repo.branch("feature/merged", m1)
        self.check(repo, {"main": "keep", "roadmap": "keep", "feature/merged": "delete"})

    def test_default_other_than_main_is_the_default(self):
        repo = Repo(self)
        m1 = repo.commit("main 1")
        m2 = repo.commit("trunk 2", parent=m1)
        repo.branch("main", m1)
        repo.branch("trunk", m2)
        repo.branch("feature/on-trunk", m2)  # on trunk, not on main
        self.check(repo, {"main": "keep", "trunk": "keep", "feature/on-trunk": "delete"}, "--default", "trunk")

    def test_missing_default_exits_nonzero_with_no_delete(self):
        repo, m1, _ = self.main_chain()
        repo.branch("feature/merged", m1)
        self.check(repo, {"main": "keep", "feature/merged": "delete"})  # scope: the sweep reads this repo
        out, rc = sweep(repo.root, "--default", "trunk")
        self.assertNotEqual(rc, 0, "no origin/trunk, yet the sweep exited 0")
        self.assertFalse(any(line.startswith("delete ") for line in out.splitlines()),
                         "no origin/trunk, yet the sweep printed a delete line")

    def test_open_head_named_dash_x_is_read_as_a_value(self):
        repo, m1, _ = self.main_chain()
        repo.branch("feature/merged-pr", m1)  # merged, and a pull request is open on it
        repo.branch("feature/merged", m1)
        args = ("--open-head=-x", "--open-head=feature/merged-pr")
        self.check(repo, {"main": "keep", "feature/merged-pr": "keep", "feature/merged": "delete"}, *args)
        _, rc = sweep(repo.root, *args)
        self.assertEqual(rc, 0, "--open-head=-x made the sweep exit %d" % rc)

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


class DeleteStep(unittest.TestCase):
    """The open-PR read step and the delete step of the workflow, run as GitHub runs them, on a fixture repo whose
    branches are merged into main."""

    def run_block(self, *markers):
        """The body of the first run: | block of the real workflow file that holds every marker, dedented."""
        with open(WORKFLOW, encoding="utf-8") as f:
            lines = f.read().splitlines()
        for i, line in enumerate(lines):
            if line.strip() != "run: |":
                continue
            indent = len(line) - len(line.lstrip(" "))
            body = []
            for raw in lines[i + 1:]:
                if raw.strip() and len(raw) - len(raw.lstrip(" ")) <= indent:
                    break
                body.append(raw)
            text = textwrap.dedent("\n".join(body)) + "\n"
            if all(marker in text for marker in markers):
                return text
        self.fail("the workflow has no run: block that holds %s" % " and ".join(markers))

    def run_workflow(self, merged, open_prs, refuse=None, tip_reads=None):
        """(CompletedProcess of the delete step, every gh call in order, verdict text) of one run of both steps. The
        open-PR read runs first, as the workflow runs it, on pull requests that are (head, base) pairs in open_prs.
        tip_reads maps a merged branch to what its tip read answers: "moved" (a commit pushed after the checkout) or
        "HTTP <status>". A merged branch with no entry answers with its checkout tip."""
        self.assertIsNotNone(shutil.which("jq"), "jq is not on PATH, so the open-PR read step cannot run")
        repo = Repo(self)
        m1 = repo.commit("main 1")
        repo.branch("main", m1)
        for name in merged:
            repo.branch(name, m1)
        tracked_tree.copy_tracked(repo.root, "actions/branch-sweep")
        runner = tempfile.mkdtemp(prefix="bsweep-runner-", dir=RUN_FOLDER)
        self.addCleanup(tracked_tree.rm_tree, runner)
        bin_dir = os.path.join(runner, "bin")
        os.mkdir(bin_dir)
        gh = os.path.join(bin_dir, "gh")
        with open(gh, "w", encoding="utf-8") as f:
            f.write(FAKE_GH)
        os.chmod(gh, 0o755)
        pulls = os.path.join(runner, "pulls.json")
        with open(pulls, "w", encoding="utf-8") as f:
            json.dump([{"head": {"ref": head}, "base": {"ref": base}} for head, base in open_prs], f)
        tips = {}
        for name in merged:
            tips[name] = git(repo.root, "rev-parse", "refs/remotes/origin/" + name)
        for name, outcome in (tip_reads or {}).items():
            tips[name] = repo.commit("pushed after the checkout", parent=tips[name]) if outcome == "moved" else outcome
        tips_path = os.path.join(runner, "tips.json")
        with open(tips_path, "w", encoding="utf-8") as f:
            json.dump(tips, f)
        log = os.path.join(runner, "gh.log")
        env = dict(ENV, GH_TOKEN="t", REPO="owner/repo", DEFAULT_BRANCH="main", RUNNER_TEMP=runner,
                   FAKE_GH_LOG=log, FAKE_GH_PULLS=pulls, FAKE_GH_TIPS=tips_path,
                   PATH=bin_dir + os.pathsep + ENV["PATH"])
        if refuse:
            env["FAKE_GH_REFUSE"] = refuse
        steps = []
        for name, markers in (("read-step.sh", ("gh api", "pulls")), ("delete-step.sh", ("sweep.py",))):
            path = os.path.join(runner, name)
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.run_block(*markers))
            steps.append(path)
        read = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", steps[0]], cwd=repo.root,
                              capture_output=True, text=True, env=env)
        self.assertEqual(read.returncode, 0, "the open-PR read step exited %d: %s"
                         % (read.returncode, read.stderr.strip()))
        done = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", steps[1]], cwd=repo.root,
                              capture_output=True, text=True, env=env)
        return done, read_text(log).splitlines(), read_text(os.path.join(runner, "verdicts.txt"))

    def run_step(self, merged, open_prs, refuse=None):
        """(CompletedProcess of the delete step, DELETE calls, verdict text) of one run of both steps."""
        done, log, verdict_text = self.run_workflow(merged, open_prs, refuse=refuse)
        return done, delete_calls(log), verdict_text

    def assert_tip_read_just_before_each_delete(self, log, names):
        """The gh call right before each branch's DELETE is that branch's tip read. A read made earlier, with other
        calls between it and the DELETE, lets the branch move in between, which is the race the read closes."""
        for name in names:
            delete = ref_call_index(log, name, delete=True)
            self.assertGreater(delete, 0, "%s: no DELETE call for it" % name)
            self.assertTrue(call_on_ref(log[delete - 1], name, delete=False),
                            "%s: the gh call before its DELETE is not its tip read: %s" % (name, log[delete - 1]))

    def test_delete_loop_makes_every_delete_when_nothing_refuses(self):
        done, calls, verdict_text = self.run_step(["feature/a", "feature/b", "feature/c"], [])
        self.assertEqual(deletes(verdict_text), ["feature/a", "feature/b", "feature/c"],
                         "scope: the sweep named other deletes")
        self.assertEqual(done.returncode, 0, "no refusal, yet the step exited %d: %s"
                         % (done.returncode, done.stderr.strip()))
        self.assertEqual(len(calls), 3, "no refusal: want 3 delete calls, got %d" % len(calls))

    def test_delete_loop_stops_at_the_first_refusal(self):
        for status in ("403", "429"):
            with self.subTest(status=status):
                done, calls, verdict_text = self.run_step(["feature/a", "feature/b", "feature/c"], [], refuse=status)
                self.assertEqual(deletes(verdict_text), ["feature/a", "feature/b", "feature/c"],
                                 "scope: the sweep named other deletes")
                self.assertEqual(len(calls), 1, "an HTTP %s refusal: the loop made %d delete calls, want 1"
                                 % (status, len(calls)))
                self.assertEqual(done.returncode, 0, "an HTTP %s refusal: the step exited %d, want 0"
                                 % (status, done.returncode))
                lines = (done.stdout + done.stderr).splitlines()
                self.assertTrue(any(line.startswith("::warning::") for line in lines),
                                "an HTTP %s refusal: the step printed no ::warning:: line" % status)
                self.assertFalse(any(line.startswith("::error::") for line in lines),
                                 "an HTTP %s refusal: the step printed an ::error:: line, which reads red" % status)

    def test_gone_ref_counts_as_done(self):
        for status in ("422", "404"):
            with self.subTest(status=status):
                done, calls, verdict_text = self.run_step(["feature/a", "feature/b", "feature/c"], [], refuse=status)
                self.assertEqual(deletes(verdict_text), ["feature/a", "feature/b", "feature/c"],
                                 "scope: the sweep named other deletes")
                self.assertEqual(len(calls), 3, "an already-gone ref (HTTP %s): the loop made %d delete calls, want 3"
                                 % (status, len(calls)))
                self.assertEqual(done.returncode, 0, "an already-gone ref (HTTP %s): the step exited %d, want 0"
                                 % (status, done.returncode))
                annotations = [line for line in (done.stdout + done.stderr).splitlines()
                               if line.startswith(("::warning::", "::error::"))]
                self.assertEqual(annotations, [], "an already-gone ref (HTTP %s): the step printed an annotation"
                                 % status)

    def test_other_delete_failure_still_fails_the_job(self):
        done, _, verdict_text = self.run_step(["feature/a", "feature/b", "feature/c"], [], refuse="500")
        self.assertEqual(deletes(verdict_text), ["feature/a", "feature/b", "feature/c"],
                         "scope: the sweep named other deletes")
        self.assertNotEqual(done.returncode, 0, "an HTTP 500 delete failure: the step exited 0")

    def test_base_of_an_open_pull_request_is_kept(self):
        # lane-b is based on lane-a, which is merged. Deleting lane-a would close lane-b's pull request.
        done, calls, _ = self.run_step(["feature/lane-a", "feature/lane-b", "feature/merged"],
                                       [("feature/lane-b", "feature/lane-a")])
        self.assertIn("feature/merged", deleted(calls), "scope: the loop made no delete for the merged control branch")
        self.assertNotIn("feature/lane-a", deleted(calls), "the base of an open pull request was deleted")

    def test_open_head_with_a_safe_name_is_kept(self):
        done, calls, _ = self.run_step(["feature/a", "feature/open"], [("feature/open", "main")])
        self.assertIn("feature/a", deleted(calls), "scope: the loop made no delete for the merged control branch")
        self.assertNotIn("feature/open", deleted(calls), "the open head of a pull request was deleted")

    def test_full_page_of_open_pull_requests_keeps_every_base(self):
        bases = ["feature/base-%03d" % i for i in range(100)]
        open_prs = [("feature/head-%03d" % i, base) for i, base in enumerate(bases)]
        done, calls, _ = self.run_step(bases + ["feature/free"], open_prs)
        self.assertIn("feature/free", deleted(calls), "scope: the loop made no delete for the free branch")
        wrong = set(bases) & set(deleted(calls))
        self.assertEqual(len(wrong), 0, "%d bases of open pull requests were deleted" % len(wrong))

    def test_open_head_named_dash_x_does_not_stop_the_step(self):
        done, calls, _ = self.run_step(["feature/a", "-x"], [("-x", "main")])
        self.assertEqual(done.returncode, 0, "an open head named -x: the step exited %d: %s"
                         % (done.returncode, done.stderr.strip()))
        self.assertTrue(any("heads/feature/a" in call for call in calls),
                        "scope: the loop made no delete call for feature/a")
        self.assertFalse(any("heads/-x" in call for call in calls), "the open head -x was deleted")

    def test_matching_tip_is_read_just_before_its_delete(self):
        names = ["feature/a", "feature/b", "feature/c"]
        done, log, verdict_text = self.run_workflow(names, [])
        self.assertEqual(deletes(verdict_text), names, "scope: the sweep named other deletes")
        self.assertEqual(deleted(delete_calls(log)), names, "a tip that matches the checkout: a DELETE did not run")
        self.assertEqual(done.returncode, 0, "a tip that matches the checkout: the step exited %d" % done.returncode)
        self.assert_tip_read_just_before_each_delete(log, names)

    def test_branch_whose_tip_moved_is_not_deleted(self):
        names = ["feature/a", "feature/b", "feature/c"]
        done, log, verdict_text = self.run_workflow(names, [], tip_reads={"feature/b": "moved"})
        self.assertEqual(deletes(verdict_text), names, "scope: the sweep named other deletes")
        self.assertNotIn("feature/b", deleted(delete_calls(log)), "feature/b: its tip moved after the checkout, yet its DELETE ran")
        self.assertIn("feature/a", deleted(delete_calls(log)), "feature/a: its tip matched, yet its DELETE did not run")
        self.assertIn("feature/c", deleted(delete_calls(log)), "feature/c: not processed after feature/b moved")
        self.assertEqual(done.returncode, 0, "a moved tip: the step exited %d, want 0 (a red main trips the brake)"
                         % done.returncode)
        self.assertEqual(annotations(done, "::error::"), [], "a moved tip: the step printed an ::error:: line")
        self.assertTrue(log_lines_naming(done, verdict_text, "feature/b"),
                        "a moved tip: the step printed no log line naming feature/b")

    def test_tip_already_gone_is_done_without_a_delete(self):
        names = ["feature/a", "feature/b", "feature/c"]
        for status in ("404", "422"):
            with self.subTest(status=status):
                done, log, verdict_text = self.run_workflow(names, [], tip_reads={"feature/b": "HTTP " + status})
                self.assertEqual(deletes(verdict_text), names, "scope: the sweep named other deletes")
                self.assertIn("feature/a", deleted(delete_calls(log)), "feature/a: its DELETE did not run")
                self.assertNotIn("feature/b", deleted(delete_calls(log)),
                                 "a tip read that says HTTP %s: the DELETE ran anyway" % status)
                self.assertIn("feature/c", deleted(delete_calls(log)), "feature/c: not processed after feature/b")
                self.assertEqual(done.returncode, 0, "a tip read that says HTTP %s: the step exited %d, want 0"
                                 % (status, done.returncode))
                self.assertEqual(annotations(done, "::warning::", "::error::"), [],
                                 "a tip read that says HTTP %s: the step printed an annotation" % status)

    def test_tip_refusal_stops_the_loop(self):
        names = ["feature/a", "feature/b", "feature/c"]
        for status in ("403", "429"):
            with self.subTest(status=status):
                done, log, verdict_text = self.run_workflow(names, [], tip_reads={"feature/b": "HTTP " + status})
                self.assertEqual(deletes(verdict_text), names, "scope: the sweep named other deletes")
                self.assertEqual(deleted(delete_calls(log)), ["feature/a"],
                                 "a tip read refused with HTTP %s: the DELETE calls were not feature/a alone, so the loop "
                                 "did not stop at the refusal" % status)
                self.assertEqual(done.returncode, 0, "a tip read refused with HTTP %s: the step exited %d, want 0"
                                 % (status, done.returncode))
                self.assertTrue(annotations(done, "::warning::"),
                                "a tip read refused with HTTP %s: the step printed no ::warning:: line" % status)
                self.assertEqual(annotations(done, "::error::"), [],
                                 "a tip read refused with HTTP %s: the step printed an ::error:: line" % status)

    def test_refusal_after_a_failed_tip_read_exits_nonzero(self):
        names = ["feature/a", "feature/b", "feature/c"]
        done, log, verdict_text = self.run_workflow(names, [],
                                                    tip_reads={"feature/b": "HTTP 500", "feature/c": "HTTP 403"})
        self.assertEqual(deletes(verdict_text), names, "scope: the sweep named other deletes")
        self.assertEqual(deleted(delete_calls(log)), ["feature/a"],
                         "a tip read failed with HTTP 500, then one refused with HTTP 403: the DELETE calls were not "
                         "feature/a alone")
        self.assertNotEqual(done.returncode, 0, "the HTTP 500 on feature/b then the HTTP 403 on feature/c: the step "
                            "exited 0, want nonzero from the earlier failure")

    def test_other_tip_read_failure_skips_that_branch(self):
        names = ["feature/a", "feature/b", "feature/c"]
        done, log, verdict_text = self.run_workflow(names, [], tip_reads={"feature/b": "HTTP 500"})
        self.assertEqual(deletes(verdict_text), names, "scope: the sweep named other deletes")
        self.assertNotIn("feature/b", deleted(delete_calls(log)), "a tip read that failed with HTTP 500: the DELETE ran")
        self.assertIn("feature/c", deleted(delete_calls(log)), "feature/c: not processed after the failed read of feature/b")
        self.assertNotEqual(done.returncode, 0, "a tip read that failed with HTTP 500: the step exited 0, want nonzero")

    def test_full_size_sweep_skips_only_the_moved_branch(self):
        names = ["feature/lane-%02d" % i for i in range(60)]  # about one run's worth of lanes
        moved = "feature/lane-30"
        done, log, verdict_text = self.run_workflow(names, [], tip_reads={moved: "moved"})
        self.assertEqual(deletes(verdict_text), names, "scope: the sweep named other deletes")
        self.assertNotIn(moved, deleted(delete_calls(log)), "%s: its tip moved after the checkout, yet its DELETE ran" % moved)
        others = [name for name in names if name != moved]
        self.assertEqual(deleted(delete_calls(log)), others, "the other 59 branches were not all deleted")
        self.assertEqual(done.returncode, 0, "a moved tip in a full-size sweep: the step exited %d" % done.returncode)
        self.assert_tip_read_just_before_each_delete(log, others)

    def test_no_delete_verdict_makes_no_tip_read(self):
        done, log, verdict_text = self.run_workflow([], [])
        self.assertEqual(deletes(verdict_text), [], "scope: the sweep named a delete")
        self.assertEqual([line for line in log if "/git/ref" in line], [], "no delete verdict, yet the step read a tip")
        self.assertEqual(done.returncode, 0, "no delete verdict: the step exited %d" % done.returncode)


def tearDownModule():
    if os.path.isdir(RUN_FOLDER):
        tracked_tree.rm_tree(RUN_FOLDER)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    unittest.main()
