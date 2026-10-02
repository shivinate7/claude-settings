#!/usr/bin/env python3
"""The shared merge tool, git half. Plan: plans/shared-merge-tool.md, "The flow".

  merge <pr>              preview: what it would claim and merge. Presses nothing.
  merge <pr> --confirm    lock, claim, push, wait, merge, sync local main, clean up.
  merge --unlock          remove this repo's merge lock. Reads no lock state first.

Git half: the merge lock, the temporary worktree, the claim, the push, the revert, resume, the
local main, afterMerge and the branch delete. GitHub half (`Host`): required checks, the wait,
the minute read and `gh pr merge --match-head-commit`.
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile, time, uuid

STAMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "actions", "stamp", "stamp.mjs")

class Stop(Exception):
    """A refusal. The message is the whole report."""

class Held(Stop):
    pass

def sh(args, cwd=None, input=None, env=None):
    r = subprocess.run(args, cwd=cwd, input=input, env=env, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()

def git(cwd, *a, input=None):
    return sh(["git", "-C", cwd, *a], input=input)

SETTLE_SECONDS = 30

def undo_check(wt, base_ref):
    """The shared silent-undo lint (lint/check_silent_undo.py), run on the branch before anything is pushed.
    A finding or an unreadable history refuses: the merge cannot be taken back."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lint"))
    import check_silent_undo as undo
    try:
        problems = undo.check(wt, base_ref, "HEAD", 60)
    except undo.Unknown as e:
        raise Stop(f"silent-undo check could not read the history: {e}")
    if problems:
        raise Stop("the branch silently undoes earlier work:\n  " + "\n  ".join(problems) + f"\nPut it back, or add the trailer `{undo.TRAILER}: <path>` to a commit message.")

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
        if cur:  # ponytail: the API cannot delete "only if the ref is still X". Window: from this run's read of the expired lock to its delete. If another run breaks the lock and creates a live one inside that window, this delete removes the live lock, and the create below then succeeds, so both runs hold it. The window is a few API calls. Close it with a lock backend that has compare-and-swap.
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

class Host:
    """The GitHub half: `gh` for the pull request, the required checks, the wait and the merge.
    Tests pass a fake with the same pr, wait_checks and merge, or a `gh` shim on PATH."""

    def __init__(self, required="protection", base="main", minute=60, now=time.time, pause=time.sleep, ignore=None):
        self.required, self.base, self.minute, self.now, self.pause = required, base, minute, now, pause
        self.ignore = ignore or {}  # check name -> reason, from ignore_checks()

    def pr(self, n):
        """-> {head, branch, base, state, mergeable, merge_state}"""
        c, out = sh(["gh", "pr", "view", str(n), "--json", "headRefOid,headRefName,baseRefName,state,mergeable,mergeStateStatus"])
        if c:
            raise Stop("gh pr view failed: " + out)
        d = json.loads(out)
        return {"head": d["headRefOid"], "branch": d["headRefName"], "base": d["baseRefName"], "state": d["state"],
                "mergeable": d["mergeable"], "merge_state": d["mergeStateStatus"]}

    def required_names(self):
        """The required check names. Never empty: an empty list would pass the wait without a read."""
        if isinstance(self.required, list):
            names = self.required
        else:
            c, out = sh(["gh", "api", f"repos/{{owner}}/{{repo}}/branches/{self.base}/protection/required_status_checks", "--jq", ".contexts"])
            if c:
                raise Stop(f"cannot read the required checks of {self.base} (no branch protection?). "
                           f"Set merge.requiredChecks to a list of check names.\n{out}")
            names = json.loads(out)
        clash = [k for k in names if k in self.ignore]
        if clash:
            raise Stop("merge.ignoreChecks names a required check: " + ", ".join(clash) + ". A required check is never ignored.")
        if not names:
            raise Stop(f"no required checks are named for {self.base} (merge.requiredChecks or the branch protection is empty). "
                       "The tool never merges with nothing to wait for. Name the checks.")
        return names

    def checks(self, n):
        """-> {check name: [(bucket, link), ...]} from `gh pr checks`, every entry kept. It exits non-zero on red or pending, so read the JSON, not the code."""
        c, out = sh(["gh", "pr", "checks", str(n), "--json", "name,bucket,link"])
        try:
            rows = json.loads(out)
        except ValueError:
            if "no checks reported" in out:
                return {}
            raise Stop("gh pr checks failed: " + out)
        got = {}
        for d in rows:
            got.setdefault(d["name"], []).append((d["bucket"], d.get("link") or ""))
        return got

    def wait_checks(self, n, sha, deadline_minutes, prior=None):
        """Wait until every check on `sha` has finished and none failed. -> (ok, why). `prior` is the head before this run's push.
        Each pass reads the pull request first: a third head, DIRTY or CONFLICTING ends the wait. A head
        that still reads as `prior` is GitHub lagging the push: keep waiting. Any red check, required or
        not, ends the wait, and any pending check, required or not, is waited on. No sleep: a pending check blocks in `gh run watch <id> --exit-status` for at
        most a minute, then the loop reads again."""
        names = self.required_names()
        end = self.now() + deadline_minutes * 60
        settled = False
        while True:
            info = self.pr(n)
            if info["head"] == prior and prior != sha:
                if self.now() >= end:
                    return False, f"the deadline of {deadline_minutes} minutes passed. GitHub still shows the head before the push."
                self.pause(self.minute)
                continue
            if info["head"] != sha:
                return False, f"the branch head moved to {info['head'][:9]} during the wait ({sha[:9]} was waited on). Run again."
            if info["mergeable"] == "CONFLICTING" or info["merge_state"] == "DIRTY":
                return False, "the pull request went DIRTY during the wait. Merge the base into the branch and run again."
            got = self.checks(n)
            red, pending, ignored = self.classify(got, names, self.ignore)
            r_red, r_pending = self.run_state(sha)
            red, pending = red + r_red, pending + r_pending
            if red:
                return False, "a check is red: " + "; ".join(red)
            if not pending and not settled:
                # ponytail: a workflow GitHub has not created yet still reads as green. The runs read and this settle read close most of the window. Ceiling: a workflow that appears after SETTLE_SECONDS.
                self.pause(SETTLE_SECONDS)
                settled = True
                continue
            if not pending:
                if ignored:
                    say("merge: ignored by merge.ignoreChecks: " + "; ".join(ignored))
                return True, ""
            if self.now() >= end:
                return False, f"the deadline of {deadline_minutes} minutes passed. Still pending: " + ", ".join(pending)
            settled = False
            self.block(pending, got)

    def run_state(self, sha):
        """-> (red, pending) from the workflow runs of `sha`. A run that is not completed holds the wait even
        when its jobs are not listed as checks yet. Only success, skipped and neutral pass."""
        c, out = sh(["gh", "run", "list", "--commit", sha, "--limit", "100", "--json", "status,conclusion,name"])
        try:
            runs = json.loads(out)
        except ValueError:
            raise Stop("gh run list failed: " + out)
        runs = [r for r in runs if r["name"] not in self.ignore]
        red = [f"workflow {r['name']}: {r['conclusion']}" for r in runs if r["status"] == "completed" and r["conclusion"] not in ("success", "skipped", "neutral")]
        pending = [f"workflow {r['name']}" for r in runs if r["status"] != "completed"]
        return red, pending

    @staticmethod
    def classify(got, names, ignore=None):
        """-> (red, pending, ignored). Every check on the head counts, required or not. Red: any bucket
        that is not pass, skipping or pending (fail, cancel, and any bucket gh adds later: closed).
        Pending: a pending entry, or a required name with no entry. `ignore` maps a name to its reason:
        those checks are left out of red and pending, and named in `ignored`."""
        ignore = ignore or {}
        live = {k: rows for k, rows in got.items() if k not in ignore or k in names}
        red = [f"{k}: {b} {l}".strip() for k, rows in live.items() for b, l in rows if b not in ("pass", "skipping", "pending")]
        pending = sorted({k for k, rows in live.items() if any(b == "pending" for b, _ in rows)} | {k for k in names if not got.get(k)})
        ignored = [f"{k} ({ignore[k]}): " + "/".join(sorted({b for b, _ in rows})) for k, rows in got.items() if k in ignore]
        return red, pending, ignored

    def head_state(self, n):
        """One read of the head's own checks, for the preview: green, pending, or red: <name>. Reads only, never waits."""
        try:
            got = self.checks(n)
            red, pending, ignored = self.classify(got, self.required_names(), self.ignore)
        except Stop as e:
            return f"unknown ({e})"
        s = "red: " + "; ".join(red) if red else "pending: " + ", ".join(pending) if pending else "green"
        return s + (" (ignored: " + "; ".join(ignored) + ")" if ignored else "")

    def block(self, pending, got):
        """Wait up to a minute for something to change."""
        ids = [m.group(1) for k in pending for _, l in got.get(k, []) for m in [re.search(r"/actions/runs/(\d+)", l)] if m]
        if not ids:  # ponytail: a check outside Actions has no run to watch, so this is a plain pause. Fine while the loop exits at the deadline.
            self.pause(self.minute)
            return
        t0 = self.now()
        try:
            subprocess.run(["gh", "run", "watch", ids[0], "--exit-status"], capture_output=True, text=True, timeout=self.minute)
        except subprocess.TimeoutExpired:
            pass
        if self.now() - t0 < 1:  # watch returned at once: do not spin on the API
            self.pause(self.minute)

    def merge(self, n, method, sha):
        """`gh pr merge --match-head-commit sha`. Never --admin, never --delete-branch (cut_branch does that).
        -> (merge commit oid or None, message)."""
        c, out = sh(["gh", "pr", "merge", str(n), f"--{method}", "--match-head-commit", sha])
        if c:
            return None, out
        c, out = sh(["gh", "pr", "view", str(n), "--json", "state,mergeCommit"])
        try:
            d = json.loads(out)
            if d["state"] == "MERGED" and d["mergeCommit"]:
                return d["mergeCommit"]["oid"], ""
        except (ValueError, KeyError, TypeError):
            pass
        return None, "gh pr merge passed, but the pull request shows no merge commit: " + out

# ------------------------------------------------------------------ git steps

def node_stamp(wt, cfgrel, mode, base):
    # GITHUB_REF and GITHUB_BASE_REF name the runner's checkout, not this worktree. stamp would read them as the worktree's branch.
    env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_REF", "GITHUB_BASE_REF")}
    return sh(["node", STAMP, f"--{mode}", "--base", base, "--config", os.path.join(wt, cfgrel), "--root", wt], env=env)

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
    who = [] if git(wt, "config", "user.email")[1] and git(wt, "config", "user.name")[1] else ["-c", "user.name=merge", "-c", "user.email=merge@localhost"]  # a runner has no identity
    c, out = git(wt, *who, "commit", "-q", "-m", "Claim record numbers", "-m", trailer)
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
            raise Stop(f"{tree} has uncommitted changes. Fast-forward {base} there by hand.")
        c, out = git(tree, "merge", "-q", "--ff-only", commit)
    else:
        c, out = git(root, "fetch", "-q", "origin", f"{base}:{base}")
    if c:
        raise Stop("the local main did not move. " + out)
    say(f"merge: local {base} is at {commit[:9]}.")

def cut_branch(root, branch, merged):
    """Delete the head branch on origin, and here unless a worktree holds it or it has local-only
    commits (its tip must be an ancestor of `merged`, the head that merged). Never fails the merge."""
    c, out = git(root, "push", "-q", "origin", "--delete", branch)
    # A gone remote ref is a deleted branch: the repo may set delete_branch_on_merge.
    gone = c and "remote ref does not exist" in out
    say(f"merge: origin/{branch}: " + ("deleted." if not c else "already deleted." if gone else "not deleted: " + (out.splitlines() or ["?"])[-1]))
    if git(root, "rev-parse", "-q", "--verify", f"refs/heads/{branch}")[0]:
        return
    held = holder(root, branch)
    if held:
        say(f"merge: {branch} kept here: checked out in {held}.")
    elif git(root, "merge-base", "--is-ancestor", f"refs/heads/{branch}", merged)[0]:
        say(f"merge: {branch} kept here: its tip is not in the merged head {merged[:9]}, so it holds local-only commits.")
    else:
        c, out = git(root, "branch", "-D", branch)
        say(f"merge: {branch} here: " + ("deleted." if not c else "not deleted: " + out))

def after_merge(root, cmds):
    """Run each command. True when every one passed. A failure never undoes the merge."""
    ok = True
    for cmd in cmds:
        c = subprocess.run(["bash", "-c", cmd], cwd=root).returncode
        say(f"merge: afterMerge `{cmd}`: " + ("done." if not c else f"FAILED (exit {c}). The merge landed and stays."))
        ok = ok and not c
    return ok

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
    tmp = os.path.realpath(tempfile.mkdtemp(prefix="merge-wt-"))  # /var is a symlink on macOS
    wt = os.path.join(tmp, "tree")
    c, out = git(root, "worktree", "add", "-q", "--detach", "--lock", "--reason", f"merge tool, pid {os.getpid()}", wt, info["head"])  # a locked tree survives the janitor sweep
    if c:
        shutil.rmtree(tmp, ignore_errors=True)
        raise Stop("cannot make the worktree: " + out)
    return tmp, wt

def drop_worktree(root, tmp, wt):
    git(root, "worktree", "unlock", wt)
    git(root, "worktree", "remove", "--force", wt)
    git(root, "worktree", "prune")
    shutil.rmtree(tmp, ignore_errors=True)

def ignore_checks(cfg):
    """merge.ignoreChecks -> {name: reason}. An entry without a name or a non-empty reason refuses the config."""
    out = {}
    for e in cfg.get("merge", {}).get("ignoreChecks", []):
        if not isinstance(e, dict) or not str(e.get("name", "")).strip() or not str(e.get("reason", "")).strip():
            raise Stop(f"merge.ignoreChecks entry {e!r} needs a name and a non-empty reason. Config refused.")
        out[e["name"]] = e["reason"]
    return out

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
        f"  head checks: {host.head_state(n)}",
        "  claim:  " + (f"already claimed ({resumed}); a run resumes at the wait" if resumed else trailer or "nothing to claim"),
        f"  then:   push HEAD:{info['branch']}, wait for the checks, `gh pr merge --{m.get('method', '?')} --match-head-commit`,",
        f"          move local {base}, run {len(m.get('afterMerge', []))} afterMerge command(s)" + (", delete the branch." if m.get("deleteBranch") else "."))

def confirm(root, cfg, cfgrel, n, host, lock):
    m = cfg.get("merge", {})
    for k in ("method", "deadlineMinutes"):
        if k not in m:
            raise Stop(f"{cfgrel} has no merge.{k}. Read it from the repo; the tool never guesses it.")
    base, base_ref = cfg["defaultBranch"], f"origin/{cfg['defaultBranch']}"
    token = lock.acquire(base, (2 * m["deadlineMinutes"] + 10) * 60)  # two waits: the head, then the claim
    tmp = wt = claim_sha = None
    try:
        info = host.pr(n)
        refuse_bad_pr(info)
        host.required_names()  # an empty or unreadable list stops here, before anything is pushed
        branch = info["branch"]
        tmp, wt = open_worktree(root, info, base)
        undo_check(wt, base_ref)
        resumed = own_claim(wt, cfgrel, base_ref)
        if resumed:
            claim_sha = info["head"]
            say(f"merge: resumed. {branch} already holds the claim {resumed}.")
        else:
            trailer = do_claim(wt, cfgrel, base_ref)
            if trailer:
                # check first, then claim: a claim push cancels the head's own run and would hide a red already there
                try:
                    ok, why = host.wait_checks(n, info["head"], m["deadlineMinutes"])
                except Stop as e:
                    ok, why = False, str(e)
                if not ok:
                    raise Stop("the head's own checks are not green, so nothing was claimed or pushed: " + why)
                claim_sha = commit_claim(wt, trailer)
                push_branch(wt, branch)
                say(f"merge: {trailer} pushed to {branch} at {claim_sha[:9]}.")
            else:
                say("merge: nothing to claim.")
        sha = claim_sha or info["head"]

        def fail(why):
            if claim_sha:
                if not os.path.isfile(os.path.join(wt, cfgrel)):  # the tree is gone (swept or cleaned): the revert needs one
                    shutil.rmtree(tmp, ignore_errors=True)
                    git(root, "worktree", "unlock", wt)
                    git(root, "worktree", "prune")
                    os.makedirs(tmp)
                    c, out = git(root, "worktree", "add", "-q", "--detach", "--lock", "--reason", f"merge tool, pid {os.getpid()}", wt, claim_sha)
                    if c:
                        raise Stop(f"{why}\nmerge: the worktree is gone and cannot be rebuilt ({out}). The claim {claim_sha[:9]} stays on {branch}. Run again to resume, or revert it by hand.")
                revert_claim(root, wt, branch, claim_sha)
            raise Stop(why)

        try:  # after the push only a Stop may leave: any other error reverts the claim first
            try:
                ok, why = host.wait_checks(n, sha, m["deadlineMinutes"], info["head"] if claim_sha else None)
            except Stop as e:  # a read that fails in the wait still reverts the claim
                ok, why = False, str(e)
            if not ok:
                fail(why)
            c, out = git(root, "fetch", "-q", "origin", f"+refs/heads/{base}:refs/remotes/origin/{base}")
            if c:  # never check against a stale base tip
                fail(f"cannot fetch origin {base}, so the claim cannot be proved fresh:\n" + out)
            try:  # main may have moved during the wait: read the branch against the tip fetched just now
                undo_check(wt, base_ref)
            except Stop as e:
                fail(str(e))
            if not os.path.isfile(os.path.join(wt, cfgrel)):  # stamp would crash on it with a raw traceback
                fail(f"the worktree lost {cfgrel}, so the claim cannot be proved fresh.")
            c, out = node_stamp(wt, cfgrel, "check", base_ref)  # each claimed number must still be free on the base tip
            if c or "UNKNOWN:" in out:
                fail("the base moved and the claim is stale, or the check could not read the base:\n" + out)
            commit, msg = host.merge(n, m["method"], sha)
            if not commit:
                fail("the merge was refused:\n" + msg)
        except Stop:
            raise
        except Exception as e:
            fail(f"unexpected {type(e).__name__} after the claim was pushed: {e}")
        say(f"merge: #{n} merged as {commit[:9]}.")
        ok = True
        try:
            ff_main(root, base, commit)
        except Stop as e:  # the merge landed: report, go on, exit non-zero at the end
            say(f"merge: the merge landed. The local {base} did not move: {e}")
            ok = False
        ok = after_merge(root, m.get("afterMerge", [])) and ok
        if m.get("deleteBranch"):
            cut_branch(root, branch, sha)
        return 0 if ok else 1  # the merge landed either way; a failed ff or afterMerge exits non-zero
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
        ignore = ignore_checks(cfg)
        return (confirm if a.confirm else preview)(root, cfg, a.config, a.pr, host or Host(cfg.get("merge", {}).get("requiredChecks", "protection"), cfg["defaultBranch"], ignore=ignore), lock) or 0
    except Stop as e:
        print(f"merge: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
