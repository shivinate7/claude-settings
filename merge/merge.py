#!/usr/bin/env python3
"""The shared merge tool, git half. Plan: plans/shared-merge-tool.md, "The flow".

  merge <pr>              preview: what it would claim and merge. Presses nothing.
  merge <pr> --confirm    lock, claim, push, wait, merge, sync local main, clean up.
  merge --unlock          remove this repo's merge lock. Reads no lock state first.

Git half (lane 3b): the merge lock, the temporary worktree, the claim, the push, the revert,
resume, the local main, afterMerge and the branch delete. The GitHub half (required checks,
the wait, `gh pr merge`) is lane 4. It plugs in at `Host.wait_checks` and `Host.merge`.
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile, time, uuid

STAMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "actions", "stamp", "stamp.mjs")

class Stop(Exception):
    """A refusal. The message is the whole report."""

class Held(Stop):
    pass

def sh(args, cwd=None, input=None):
    r = subprocess.run(args, cwd=cwd, input=input, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()

def git(cwd, *a, input=None):
    return sh(["git", "-C", cwd, *a], input=input)

def say(*lines):
    print(*lines, flush=True)

# ------------------------------------------------------------------ the merge lock
# A lock is a commit that a ref points at. The commit message holds the expiry. The ref is
# refs/merge-lock/<defaultBranch>. Two backends, one interface: acquire, release, unlock.

def lock_message(ttl, now):
    return f"merge lock\nexpires: {int(now + ttl)}\nowner: {uuid.uuid4().hex}"

def expiry_of(message):
    m = re.search(r"^expires: (\d+)$", message, re.M)
    return int(m.group(1)) if m else float("inf")  # not ours: never expires, only --unlock removes it

class GitLock:
    """Any git remote. Tests use a local bare origin. The create-only push is the one arbiter."""
    def __init__(self, root, now=time.time):
        self.root, self.now = root, now

    def read(self, b):
        ref = f"refs/merge-lock/{b}"
        c, out = git(self.root, "ls-remote", "origin", ref)
        if c:
            raise Stop("cannot read the merge lock: " + out)
        if not out:
            return None
        if git(self.root, "fetch", "-q", "origin", ref)[0]:
            return out.split()[0], float("inf")
        return out.split()[0], expiry_of(git(self.root, "log", "-1", "--format=%B", "FETCH_HEAD")[1])

    def acquire(self, b, ttl):
        ref = f"refs/merge-lock/{b}"
        cur = self.read(b)
        if cur and cur[1] > self.now():
            raise Held(f"the merge lock on {b} is held (expires in {cur[1] - self.now():.0f}s). Wait, or run: merge --unlock")
        tree = git(self.root, "mktree", input="")[1]
        c, sha = git(self.root, "-c", "user.name=merge", "-c", "user.email=merge@localhost",
                     "commit-tree", tree, "-m", lock_message(ttl, self.now()))
        if c:
            raise Stop("cannot make the lock commit: " + sha)
        # --force-with-lease with an empty expect creates only. With a sha it swaps only that
        # expired lock. So two runs that break one expired lock cannot both win.
        lease = f"--force-with-lease={ref}:{cur[0] if cur else ''}"
        c, out = git(self.root, "push", "-q", lease, "origin", f"{sha}:{ref}")
        if c:
            raise Held("another run took the merge lock first")
        return sha

    def release(self, b, token):
        ref = f"refs/merge-lock/{b}"
        git(self.root, "push", "-q", f"--force-with-lease={ref}:{token}", "origin", f":{ref}")

    def unlock(self, b):
        c, out = git(self.root, "push", "-q", "origin", f":refs/merge-lock/{b}")
        if c and "does not exist" not in out:
            raise Stop("unlock failed: " + out)

class GhLock:
    """Real use: the GitHub API. The API refuses a ref that exists, so one run wins."""
    def __init__(self, now=time.time):
        self.now = now

    def api(self, *a):
        c, out = sh(["gh", "api", *a])
        return c, out

    def read(self, b):
        c, sha = self.api(f"repos/{{owner}}/{{repo}}/git/ref/merge-lock/{b}", "--jq", ".object.sha")
        if c:
            if "404" in sha or "Not Found" in sha:
                return None
            raise Stop("cannot read the merge lock: " + sha)
        c, out = self.api(f"repos/{{owner}}/{{repo}}/git/commits/{sha}", "--jq", ".message")
        return sha, (expiry_of(out) if not c else float("inf"))

    def acquire(self, b, ttl):
        cur = self.read(b)
        if cur and cur[1] > self.now():
            raise Held(f"the merge lock on {b} is held (expires in {cur[1] - self.now():.0f}s). Wait, or run: merge --unlock")
        if cur:  # ponytail: the API has no compare-and-swap, so two breakers of one expired lock can both pass for a few ms. The create below still refuses the second.
            self.api("-X", "DELETE", f"repos/{{owner}}/{{repo}}/git/refs/merge-lock/{b}")
        c, head = self.api(f"repos/{{owner}}/{{repo}}/git/ref/heads/{b}", "--jq", ".object.sha")
        c2, tree = self.api(f"repos/{{owner}}/{{repo}}/git/commits/{head}", "--jq", ".tree.sha") if not c else (c, head)
        if c2:
            raise Stop("cannot read the base branch: " + tree)
        c, sha = self.api("-X", "POST", "repos/{owner}/{repo}/git/commits", "-f", f"message={lock_message(ttl, self.now())}",
                          "-f", f"tree={tree}", "--jq", ".sha")
        if c:
            raise Stop("cannot make the lock commit: " + sha)
        c, out = self.api("-X", "POST", "repos/{owner}/{repo}/git/refs", "-f", f"ref=refs/merge-lock/{b}", "-f", f"sha={sha}")
        if c:
            raise Held("another run took the merge lock first")
        return sha

    def release(self, b, token):
        cur = self.read(b)
        if cur and cur[0] == token:
            self.api("-X", "DELETE", f"repos/{{owner}}/{{repo}}/git/refs/merge-lock/{b}")

    def unlock(self, b):
        c, out = self.api("-X", "DELETE", f"repos/{{owner}}/{{repo}}/git/refs/merge-lock/{b}")
        if c and "404" not in out and "Not Found" not in out and "does not exist" not in out:
            raise Stop("unlock failed: " + out)

# ------------------------------------------------------------------ the GitHub half (the seam)

class NotBuilt(Stop):
    pass

class Host:
    """Lane 4 fills wait_checks and merge. Tests pass a fake with the same three methods."""
    built = False

    def pr(self, n):
        """-> {head, branch, base, state, mergeable, merge_state}"""
        c, out = sh(["gh", "pr", "view", str(n), "--json", "headRefOid,headRefName,baseRefName,state,mergeable,mergeStateStatus"])
        if c:
            raise Stop("gh pr view failed: " + out)
        d = json.loads(out)
        return {"head": d["headRefOid"], "branch": d["headRefName"], "base": d["baseRefName"], "state": d["state"],
                "mergeable": d["mergeable"], "merge_state": d["mergeStateStatus"]}

    def wait_checks(self, n, sha, deadline_minutes):
        """Wait for the required checks on `sha`. -> (ok, why). Lane 4."""
        raise NotBuilt("the GitHub half (required checks, the wait) is lane 4 and is not built")

    def merge(self, n, method, sha):
        """`gh pr merge --match-head-commit sha`. -> (merge commit oid or None, message). Lane 4."""
        raise NotBuilt("the GitHub half (gh pr merge) is lane 4 and is not built")

# ------------------------------------------------------------------ git steps

def node_stamp(wt, cfgrel, mode, base):
    return sh(["node", STAMP, f"--{mode}", "--base", base, "--config", os.path.join(wt, cfgrel), "--root", wt])

def own_claim(wt, cfgrel, base):
    """The trailer ids when HEAD is this tool's claim and each number is still free, else None."""
    ids = git(wt, "log", "-1", "--format=%(trailers:key=Record-claim,valueonly)", "HEAD")[1].strip()
    if not ids:
        return None
    c, out = node_stamp(wt, cfgrel, "check", base)
    return None if c or "UNKNOWN:" in out else ids  # UNKNOWN is a failure: it exits 0 outside Actions

def do_claim(wt, cfgrel, base):
    """Run the claim in the worktree. -> the Record-claim line, or None when nothing was claimed."""
    c, out = node_stamp(wt, cfgrel, "claim", base)
    if c:
        raise Stop("the claim was refused. Nothing is on origin.\n" + out)
    lines = [l for l in out.splitlines() if l.strip()]
    return lines[-1] if lines and lines[-1].startswith("Record-claim: ") else None

def commit_claim(wt, trailer):
    git(wt, "add", "-A")
    c, out = git(wt, "commit", "-q", "-m", "Claim record numbers", "-m", trailer)
    if c:
        raise Stop("cannot commit the claim: " + out)
    return git(wt, "rev-parse", "HEAD")[1]

def push_branch(wt, branch):
    """A plain push. Never force: a moved branch refuses it, and nothing reaches origin."""
    c, out = git(wt, "push", "-q", "origin", f"HEAD:refs/heads/{branch}")
    if c:
        raise Stop(f"the push of {branch} was refused. Nothing is on origin from this run. Run again.\n{out}")

def origin_head(root, branch):
    return git(root, "ls-remote", "origin", f"refs/heads/{branch}")[1].split("\t")[0]

def revert_claim(root, wt, branch, claim_sha):
    """Revert only while the origin head is the claim commit. Else the claim commit can be gone."""
    if origin_head(root, branch) != claim_sha:
        say(f"merge: origin {branch} is not the claim commit {claim_sha[:9]}. Nothing reverted. Run again.")
        return False
    cmd = f"git fetch origin {branch} && git checkout {branch} && git revert --no-edit {claim_sha} && git push origin {branch}"
    c, out = git(wt, "revert", "--no-edit", claim_sha)
    if not c:
        c, out = git(wt, "push", "-q", "origin", f"HEAD:refs/heads/{branch}")
    if c:
        say(f"merge: the revert was refused. The claim stays on {branch}. Run:\n  {cmd}\n{out}")
        return False
    say(f"merge: claim {claim_sha[:9]} reverted on {branch}.")
    return True

def holder(root, branch):
    path = None
    for line in git(root, "worktree", "list", "--porcelain")[1].splitlines():
        if line.startswith("worktree "):
            path = line[9:].strip()
        elif line.strip() == f"branch refs/heads/{branch}":
            return path
    return None

def ff_main(root, base, commit):
    """Move the local default branch onto `commit`, a commit that origin holds."""
    c, out = git(root, "fetch", "-q", "origin")
    if c:
        raise Stop("git fetch origin failed, so the local main cannot be moved: " + out)
    if git(root, "merge-base", "--is-ancestor", commit, f"refs/remotes/origin/{base}")[0]:
        raise Stop(f"{commit[:9]} is not on origin/{base}. Nothing was moved.")
    tree = holder(root, base)
    if tree:
        if git(tree, "rev-parse", "--abbrev-ref", "HEAD")[1] != base:
            raise Stop(f"{tree} is not on {base}. Nothing was moved.")
        dirty = git(tree, "status", "--porcelain")[1]
        if dirty:
            raise Stop(f"{tree} has uncommitted changes. The merge is done. Fast-forward {base} there by hand.")
        c, out = git(tree, "merge", "-q", "--ff-only", commit)
    else:
        c, out = git(root, "fetch", "-q", "origin", f"{base}:{base}")
    if c:
        raise Stop("the local main did not move. The merge is done. " + out)
    say(f"merge: local {base} is at {commit[:9]}.")

def cut_branch(root, branch):
    """Delete the head branch on origin, and here unless a worktree holds it. Never fails the merge."""
    c, out = git(root, "push", "-q", "origin", "--delete", branch)
    say(f"merge: origin/{branch}: " + ("deleted." if not c else "not deleted: " + (out.splitlines() or ["?"])[-1]))
    if git(root, "rev-parse", "-q", "--verify", f"refs/heads/{branch}")[0]:
        return
    held = holder(root, branch)
    if held:
        say(f"merge: {branch} kept here: checked out in {held}.")
    else:
        c, out = git(root, "branch", "-D", branch)
        say(f"merge: {branch} here: " + ("deleted." if not c else "not deleted: " + out))

def after_merge(root, cmds):
    for cmd in cmds:
        c = subprocess.run(["bash", "-c", cmd], cwd=root).returncode
        say(f"merge: afterMerge `{cmd}`: " + ("done." if not c else f"FAILED (exit {c}). The merge stays."))

# ------------------------------------------------------------------ the flow

def load_config(root, path):
    p = os.path.join(root, path)
    try:
        with open(p, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError) as e:
        raise Stop(f"cannot read the config {p}: {e}")
    if not cfg.get("defaultBranch"):
        raise Stop(f"{path} has no defaultBranch")
    return cfg

def refuse_bad_pr(info):
    if info["state"] != "OPEN":
        raise Stop(f"the pull request is {info['state']}")
    if info["mergeable"] == "CONFLICTING" or info["merge_state"] == "DIRTY":
        raise Stop("the pull request is CONFLICTING. Merge the base into the branch and run again. Nothing was claimed.")

def open_worktree(root, info, base):
    """Fetch, check that the head is the one gh named, and make a detached worktree there."""
    for ref in (base, info["branch"]):
        c, out = git(root, "fetch", "-q", "origin", f"+refs/heads/{ref}:refs/remotes/origin/{ref}")
        if c:
            raise Stop(f"git fetch origin {ref} failed: {out}")
    got = git(root, "rev-parse", f"refs/remotes/origin/{info['branch']}")[1]
    if got != info["head"]:
        raise Stop(f"{info['branch']} moved: gh says {info['head'][:9]}, origin holds {got[:9]}. Run again. Nothing was claimed.")
    tmp = tempfile.mkdtemp(prefix="merge-wt-")
    wt = os.path.join(tmp, "tree")
    c, out = git(root, "worktree", "add", "-q", "--detach", wt, info["head"])
    if c:
        shutil.rmtree(tmp, ignore_errors=True)
        raise Stop("cannot make the worktree: " + out)
    return tmp, wt

def drop_worktree(root, tmp, wt):
    git(root, "worktree", "remove", "--force", wt)
    git(root, "worktree", "prune")
    shutil.rmtree(tmp, ignore_errors=True)

def preview(root, cfg, cfgrel, n, host, lock):
    base = cfg["defaultBranch"]
    info = host.pr(n)
    refuse_bad_pr(info)
    tmp, wt = open_worktree(root, info, base)
    try:
        resumed = own_claim(wt, cfgrel, f"origin/{base}")
        trailer = None if resumed else do_claim(wt, cfgrel, f"origin/{base}")
    finally:
        drop_worktree(root, tmp, wt)
    m = cfg.get("merge", {})
    held = lock.read(base)
    say(f"merge: PREVIEW for #{n} ({info['branch']} at {info['head'][:9]}). Nothing was pressed.",
        f"  lock:   " + ("held" if held and held[1] > lock.now() else "free"),
        "  claim:  " + (f"already claimed ({resumed}); a run resumes at the wait" if resumed else trailer or "nothing to claim"),
        f"  then:   push HEAD:{info['branch']}, wait for the checks, `gh pr merge --{m.get('method', '?')} --match-head-commit`,",
        f"          move local {base}, run {len(m.get('afterMerge', []))} afterMerge command(s)" + (", delete the branch." if m.get("deleteBranch") else "."))

def confirm(root, cfg, cfgrel, n, host, lock):
    m = cfg.get("merge", {})
    for k in ("method", "deadlineMinutes"):
        if k not in m:
            raise Stop(f"{cfgrel} has no merge.{k}. Read it from the repo; the tool never guesses it.")
    if not host.built:
        raise Stop("the GitHub half (lane 4) is not built, so --confirm cannot finish a merge. Use the preview.")
    base, base_ref = cfg["defaultBranch"], f"origin/{cfg['defaultBranch']}"
    token = lock.acquire(base, (m["deadlineMinutes"] + 10) * 60)
    tmp = wt = claim_sha = None
    try:
        info = host.pr(n)
        refuse_bad_pr(info)
        branch = info["branch"]
        tmp, wt = open_worktree(root, info, base)
        resumed = own_claim(wt, cfgrel, base_ref)
        if resumed:
            claim_sha = info["head"]
            say(f"merge: resumed. {branch} already holds the claim {resumed}.")
        else:
            trailer = do_claim(wt, cfgrel, base_ref)
            if trailer:
                claim_sha = commit_claim(wt, trailer)
                push_branch(wt, branch)
                say(f"merge: {trailer} pushed to {branch} at {claim_sha[:9]}.")
            else:
                say("merge: nothing to claim.")
        sha = claim_sha or info["head"]

        def fail(why):
            if claim_sha:
                revert_claim(root, wt, branch, claim_sha)
            raise Stop(why)

        ok, why = host.wait_checks(n, sha, m["deadlineMinutes"])
        if not ok:
            fail(why)
        git(root, "fetch", "-q", "origin", f"+refs/heads/{base}:refs/remotes/origin/{base}")
        c, out = node_stamp(wt, cfgrel, "check", base_ref)  # each claimed number must still be free on the base tip
        if c or "UNKNOWN:" in out:
            fail("the base moved and the claim is stale, or the check could not read the base:\n" + out)
        commit, msg = host.merge(n, m["method"], sha)
        if not commit:
            fail("the merge was refused:\n" + msg)
        say(f"merge: #{n} merged as {commit[:9]}.")
        try:
            ff_main(root, base, commit)
        except Stop as e:  # the merge is done: report, go on
            say(f"merge: {e}")
        after_merge(root, m.get("afterMerge", []))
        if m.get("deleteBranch"):
            cut_branch(root, branch)
    finally:
        if wt:
            drop_worktree(root, tmp, wt)
        lock.release(base, token)

def main(argv, host=None, lock=None):
    p = argparse.ArgumentParser(prog="merge", description=__doc__.split("\n\n")[0])
    p.add_argument("pr", nargs="?", type=int)
    p.add_argument("--confirm", action="store_true")
    p.add_argument("--unlock", action="store_true")
    p.add_argument("--config", default=".github/stamp.json")
    a = p.parse_args(argv)
    if a.unlock == (a.pr is not None) or (a.unlock and a.confirm):
        p.error("give a pull request number, or --unlock")
    try:
        c, root = sh(["git", "rev-parse", "--show-toplevel"])
        if c:
            raise Stop("not in a git checkout")
        cfg = load_config(root, a.config)
        lock = lock or GhLock()
        if a.unlock:
            lock.unlock(cfg["defaultBranch"])
            say(f"merge: lock on {cfg['defaultBranch']} removed.")
            return 0
        (confirm if a.confirm else preview)(root, cfg, a.config, a.pr, host or Host(), lock)
        return 0
    except Stop as e:
        print(f"merge: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
