"""Fixture test for merge/repaired_merges.py: a planted revert and a planted batch-fix are counted, a clean merge is not."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "repaired_merges.py"
ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
       "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}


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
        commit(d, "Fix the batch-beta test that the merge left red")
        commit(d, "Unrelated work on batch-clean docs")
        r = run_script(d)
        assert r.returncode == 0, r.stderr
        first = r.stdout.splitlines()[0]
        assert first == "repaired merges in the last 14 days: 2", r.stdout
        assert reverted[:7] in r.stdout and "#11" in r.stdout, r.stdout
        assert fixed[:7] in r.stdout and "#12" in r.stdout, r.stdout
        assert "#13" not in r.stdout and "#9 " not in r.stdout, r.stdout
        print("ok")


if __name__ == "__main__":
    main()
