"""Fixture test for merge/repaired_merges.py: a planted revert and a planted batch-fix are counted, a clean merge is not."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lint"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
SCRIPT = HERE / "repaired_merges.py"
ENV = _test_git.apply({**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
       "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull})


def git(repo, *args, env=None):
    r = subprocess.run(["git", *args], cwd=repo, env=env or ENV, capture_output=True, text=True)
    assert r.returncode == 0, f"git {args}: {r.stderr}"
    return r.stdout.strip()


def merge_pr(repo, n, branch, env=None):
    git(repo, "checkout", "-q", "-b", branch, "main", env=env)
    Path(repo, f"{branch}.txt").write_text(branch)
    git(repo, "add", "-A", env=env)
    git(repo, "commit", "-q", "-m", f"work on {branch}", env=env)
    git(repo, "checkout", "-q", "main", env=env)
    git(repo, "merge", "-q", "--no-ff", "-m", f"Merge pull request #{n} from owner/{branch}", branch, env=env)
    return git(repo, "rev-parse", "HEAD", env=env)


def merge_branch(repo, n, branch, msgs, revert_of=None, env=None):
    """Merge a PR whose branch holds extra commits (messages msgs) and, if revert_of, a revert of that merge."""
    git(repo, "checkout", "-q", "-b", branch, "main", env=env)
    Path(repo, f"{branch}.txt").write_text(branch)
    git(repo, "add", "-A", env=env)
    git(repo, "commit", "-q", "-m", f"work on {branch}", env=env)
    for m in msgs:
        git(repo, "commit", "-q", "--allow-empty", "-m", m, env=env)
    if revert_of:
        git(repo, "revert", "--no-edit", "-m", "1", revert_of, env=env)
    git(repo, "checkout", "-q", "main", env=env)
    git(repo, "merge", "-q", "--no-ff", "-m", f"Merge pull request #{n} from owner/{branch}", branch, env=env)
    return git(repo, "rev-parse", "HEAD", env=env)


def commit(repo, msg):
    git(repo, "commit", "-q", "--allow-empty", "-m", msg)


def run_script(repo, *args):
    return subprocess.run([sys.executable, str(SCRIPT), "--repo", str(repo), *args], capture_output=True, text=True)


def main():
    with tempfile.TemporaryDirectory() as d:
        git(d, "init", "-q", "-b", "main")
        commit(d, "base")
        reverted = merge_pr(d, 11, "batch-alpha")
        fixed = merge_pr(d, 12, "batch-beta")
        merge_pr(d, 13, "batch-clean")
        old_env = {**ENV, "GIT_AUTHOR_DATE": "2020-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2020-01-01T00:00:00Z"}
        # A merge outside the window is not counted, even though a later commit repairs it.
        old = merge_pr(d, 9, "batch-old", env=old_env)
        git(d, "revert", "--no-edit", "-m", "1", reverted)
        git(d, "revert", "--no-edit", "-m", "1", old)
        commit(d, "Fix #12 test that the merge left red")
        commit(d, "Unrelated work on batch-clean docs")
        # A fix commit inside the batch it names is no repair: it never reached main before the merge did.
        merge_branch(d, 15, "batch-gamma", ["Fix #15 flake before it lands"])
        # A repair that arrives inside a later batch merge is a second-parent commit, and counts.
        shaky = merge_pr(d, 17, "batch-eps")
        merge_branch(d, 18, "batch-zeta", [], revert_of=shaky)
        # Not repairs: a commit that only mentions the branch as a bare word, a "revert" in a body only, a Reapply.
        merge_pr(d, 20, "ios-ship")
        commit(d, "c48 part 1: review fixes for ios-ship profile")
        merge_pr(d, 21, "batch-eta")
        commit(d, "Add a check\n\nThe note for batch #21 says a revert of the old rule is wanted.")
        theta = merge_pr(d, 22, "batch-theta")
        theta_work = git(d, "rev-parse", f"{theta}^2")
        commit(d, f'Reapply "Join #22 fix into the batch"\n\nThis reverts commit {theta_work}.')
        # A repair: a later merge whose branch name carries a fix word and names the repaired branch.
        iota = merge_pr(d, 23, "batch-iota")
        merge_pr(d, 24, "fix-batch-iota")
        r = run_script(d)
        assert r.returncode == 0, r.stderr
        first = r.stdout.splitlines()[0]
        assert first == "repaired merges in the last 14 days: 4", r.stdout
        assert reverted[:7] in r.stdout and "#11" in r.stdout, r.stdout
        assert fixed[:7] in r.stdout and "#12" in r.stdout, r.stdout
        assert shaky[:7] in r.stdout and "#17" in r.stdout, r.stdout
        assert iota[:7] in r.stdout and "#23" in r.stdout, r.stdout
        for n in ("#20", "#21", "#22", "#24"):
            assert n not in r.stdout, (n, r.stdout)
        assert "#15" not in r.stdout and "#18" not in r.stdout, r.stdout
        assert "#13" not in r.stdout and "#9 " not in r.stdout, r.stdout
        print("ok")


if __name__ == "__main__":
    main()
