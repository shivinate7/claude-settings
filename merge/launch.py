#!/usr/bin/env python3
"""Fresh-code guard. Usage: launch.py <checkout> [--dev] [merge args...]

Fetches origin main, runs merge/merge.py from a detached temporary worktree at that SHA, and
fast-forwards the checkout only when it is on main, clean and behind. When fresh code cannot
be proven, prints a warning block and runs the checkout's own tree. --dev runs the checkout's
own tree and nothing else. Plan: plans/shared-merge-tool.md, "The fresh-code guard".
"""
import os, shutil, stat, subprocess, sys, tempfile

def git(co, *a):
    r = subprocess.run(["git", "-C", co, *a], capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()

def rmtree_retry(path):  # own copy: bin/merge is a standalone shim and can't import this
    def handler(func, p, exc):
        try:
            os.chmod(p, stat.S_IWRITE); func(p)
        except OSError as e:
            print(f"merge: couldn't remove {p}: {e}", file=sys.stderr)
    if sys.version_info >= (3, 12): shutil.rmtree(path, onexc=handler)
    else: shutil.rmtree(path, onerror=lambda f, p, ei: handler(f, p, ei[1]))

def run(tree, args):
    return subprocess.run([sys.executable, os.path.join(tree, "merge", "merge.py"), *args]).returncode

def warn(sha, behind, why):
    b = f"{behind} commit(s) behind origin/main as of the last fetch" if behind is not None else "distance behind origin/main unknown"
    print("=" * 60 + f"\nWARNING: merge cannot prove it runs fresh code.\n  Running: claude-settings {sha} ({b})\n  Why: {why}\n" + "=" * 60, file=sys.stderr)

def main(co, args):
    sha = git(co, "rev-parse", "--short=12", "HEAD")[1]
    if "--dev" in args:
        print(f"merge: --dev, running the checkout's own tree at {sha}", file=sys.stderr)
        return run(co, [a for a in args if a != "--dev"])
    code, out = git(co, "fetch", "-q", "origin", "+refs/heads/main:refs/remotes/origin/main")
    behind = None
    if git(co, "rev-parse", "-q", "--verify", "origin/main")[0] == 0:
        n = git(co, "rev-list", "--count", "HEAD..origin/main")[1]
        behind = int(n) if n.isdigit() else None
    if code:  # offline or fetch refused: run the code we have
        warn(sha, behind, "fetch of origin main failed: " + (out.splitlines() or ["no output"])[-1])
        return run(co, args)
    want = git(co, "rev-parse", "origin/main")[1]
    tmp = os.path.realpath(tempfile.mkdtemp(prefix="merge-fresh-"))  # /var is a symlink on macOS
    wt = os.path.join(tmp, "tree")
    try:
        c, o = git(co, "worktree", "add", "-q", "--detach", wt, want)
        got = git(wt, "rev-parse", "HEAD")[1] if c == 0 else ""
        if got != want:
            warn(sha, behind, "temporary worktree at origin/main failed or did not match: " + (o or got))
            return run(co, args)
        branch = git(co, "rev-parse", "--abbrev-ref", "HEAD")[1]
        clean = git(co, "status", "--porcelain")[1] == ""
        if behind:
            if branch == "main" and clean:
                if git(co, "merge", "-q", "--ff-only", "origin/main")[0]:
                    print("merge: checkout not fast-forwarded: ff-only merge refused", file=sys.stderr)
            else:
                print(f"merge: checkout left as is: {'not on main' if branch != 'main' else 'dirty tree'}", file=sys.stderr)
        print(f"merge: running claude-settings {want[:12]} (origin/main)", file=sys.stderr)
        return run(wt, args)
    finally:
        git(co, "worktree", "remove", "--force", wt)
        rmtree_retry(tmp)  # belt-and-suspenders: Windows can leave read-only pack files behind git's own remove
        git(co, "worktree", "prune")  # drop the registration once the directory is actually gone

if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2:]))
