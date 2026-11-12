# section 3975
FAMILY = "branch-worktree"
FAMILIES["branch-worktree"] = "branch delete and worktree remove/prune"
#
# The three git forms the machine-wide janitor plan named as a safety hole in this rule: `git branch
# -d/-D`, `git worktree remove`, `git worktree prune`. Each is judged on the STATE OF ITS SUBJECT,
# the same shape every other arm of this rule already uses, never a name list.
#
# BOTH `-d` AND `-D` ARE READ THE SAME WAY. Neither creates, renames nor lists a branch, so a
# non-delete `git branch` call must keep allowing, unchanged.
sh("branch: a plain branch call only lists, no delete flag", VCS + " branch", "allow", cwd=NOGIT)
sh("branch: creating a branch is not a delete", VCS + " branch newname", "allow", cwd=NOGIT)
sh("branch: renaming a branch is not a delete", VCS + " branch -m old new", "allow", cwd=NOGIT)

# THE THREE TESTS THAT MAKE A BRANCH'S SUBJECT EMPTY, each proven with real history pushed to a
# real bare remote (BRANCHREPO), so `git cherry` and `git for-each-ref --contains` answer for
# real, never a mock.
sh("branch: an ancestor of origin/main deletes clean with -d",
   VCS + " branch -d ancestor-work", "allow", cwd=BRANCHREPO)
sh("branch: the same ancestor deletes clean with -D",
   VCS + " branch -D ancestor-work", "allow", cwd=BRANCHREPO)
sh("branch: a rebased commit's patch already sits on origin/main, cherry proves it",
   VCS + " branch -D rebased-work", "allow", cwd=BRANCHREPO)
sh("branch: a commit pushed to the remote is not the only copy",
   VCS + " branch -D pushed-work", "allow", cwd=BRANCHREPO)
# THE ONLY-COPY CASE. unmerged-work is not an ancestor, its patch is not on origin/main, and no
# remote ref contains it: this is the defect the plan measured against the live hook.
sh("branch: a commit found nowhere else is the only copy, and the rule denies",
   VCS + " branch -D unmerged-work", "deny", "shared-tree", cwd=BRANCHREPO,
   carries=("`git push origin <branch>:refs/heads/archive/<branch>`", "`git branch -D <branch>`",
            "no question"),
   lacks=("unmerged-work", "push the branch, or merge it"))
sh("branch: the refusal's handed remedy, once run, makes the rule allow the delete",
   VCS + " branch -D archived-work", "allow", cwd=BRANCHREPO)
sh("branch: -d over the same only-copy branch still denies",
   VCS + " branch -d unmerged-work", "deny", "shared-tree", cwd=BRANCHREPO)
# TWO NAMES IN ONE CALL. One safe and one unsafe name still denies: one held-only-copy makes the
# whole call's subject non-empty.
sh("branch: one safe name and one only-copy name in the same call still denies",
   VCS + " branch -D ancestor-work unmerged-work", "deny", "shared-tree", cwd=BRANCHREPO)

# THE RESOLVE ORDER'S OTHER TWO STEPS. BRANCHFALLBACKMAIN and BRANCHFALLBACKMASTER carry no
# remote at all, so each proves its own step answers when the step before it cannot.
sh("branch: local main answers when there is no origin/HEAD",
   VCS + " branch -D ancestor-fallback", "allow", cwd=BRANCHFALLBACKMAIN)
sh("branch: local master answers when there is no main and no origin/HEAD",
   VCS + " branch -D ancestor-fallback-master", "allow", cwd=BRANCHFALLBACKMASTER)
# THE FALLBACK MUST DENY TOO, not just pass. A base that silently gave up would read as
# unreadable and let an only-copy branch through; these prove the fallback is a real read.
sh("branch: local main's fallback still denies an only-copy branch",
   VCS + " branch -D unmerged-fallback", "deny", "shared-tree", cwd=BRANCHFALLBACKMAIN)
sh("branch: local master's fallback still denies an only-copy branch",
   VCS + " branch -D unmerged-fallback-master", "deny", "shared-tree", cwd=BRANCHFALLBACKMASTER)
# NONE OF THE THREE ANSWERS. The base is unreadable, so the call is allowed and logged, never
# denied and never silently passed over an unproven subject.
sh("branch: no origin/HEAD, no local main, no local master: unreadable, allowed",
   VCS + " branch -D orphan-work", "allow", cwd=BRANCHNOBASE)

# `git worktree remove <path>`. The subject lives at PATH, not at the checkout the command runs
# in, so every case below runs from WTMAIN and names one of its own linked worktrees.
sh("worktree remove: a clean, unlocked tree with no live session passes",
   VCS + " worktree remove " + slash(WTCLEAN), "allow", cwd=WTMAIN)
sh("worktree remove: uncommitted and untracked work denies",
   VCS + " worktree remove " + slash(WTDIRTY), "deny", "shared-tree", cwd=WTMAIN)
sh("worktree remove: the force flag does not skip the subject read",
   VCS + " worktree remove --force " + slash(WTDIRTY), "deny", "shared-tree", cwd=WTMAIN)
sh("worktree remove: a locked tree denies even though it is clean",
   VCS + " worktree remove " + slash(WTLOCKED), "deny", "shared-tree", cwd=WTMAIN)
# A LIVE SESSION. WTLIVECFG's one record names THIS TEST RUNNER'S OWN pid and its real start
# time, read back with `ps` exactly as the guard reads it, so the process really is alive and
# the start time really does match.
sh("worktree remove: a live session standing in a clean tree still denies",
   VCS + " worktree remove " + slash(WTLIVE), "deny", "shared-tree", cwd=WTMAIN,
   config=WTLIVECFG)
# A RECYCLED PID CANNOT INHERIT A DEAD SESSION'S CLAIM. Two ways a record goes stale: the pid no
# longer runs at all, or the pid runs but its start time no longer matches (another process now
# holds that number).
sh("worktree remove: a session record for a pid that is no longer running does not deny",
   VCS + " worktree remove " + slash(WTDEADSESSION), "allow", cwd=WTMAIN, config=WTDEADCFG)
sh("worktree remove: a live pid whose recorded start time does not match does not deny",
   VCS + " worktree remove " + slash(WTSTALESTART), "allow", cwd=WTMAIN, config=WTSTALESTARTCFG)

# BASE COPIES. Each case is a tree in the state built by _build_base_copies. Case 1 is the incident: its
# staged files are the base copy, an ancestor of HEAD, and nothing else is wrong, so it passes. Cases 2 to 5
# each break one condition, and cases 7 and 8 keep the locked and live reads on the incident tree. Each of
# those is refused today on the dirty read. After the build, each must be refused on its own condition.
# Case 5 pairs with case 1: the matching commit is pushed in case 1 and unpushed in case 5. Case 6 is a
# clean tree on a pushed branch, and it keeps today's allow.
sh("worktree remove: base copies, the incident tree, whose index is an ancestor of HEAD, passes",
   VCS + " worktree remove " + slash(BCINC), "allow", cwd=BCMAIN)
sh("worktree remove: base copies, the same incident tree passes with the force flag",
   VCS + " worktree remove --force " + slash(BCINC), "allow", cwd=BCMAIN)
sh("worktree remove: base copies, one worktree edit whose content is in no commit still denies",
   VCS + " worktree remove " + slash(BCUNIQUE), "deny", "shared-tree", cwd=BCMAIN)
sh("worktree remove: base copies, an untracked file beside the incident tree still denies",
   VCS + " worktree remove " + slash(BCUNTRACKED), "deny", "shared-tree", cwd=BCMAIN)
sh("worktree remove: base copies, an unpushed commit on HEAD still denies",
   VCS + " worktree remove " + slash(BCUNPUSHED), "deny", "shared-tree", cwd=BCMAIN)
sh("worktree remove: base copies, a staged blob held only by an unpushed commit still denies",
   VCS + " worktree remove " + slash(BCBYPASS), "deny", "shared-tree", cwd=BCMAIN)
sh("worktree remove: base copies, the same staged blob with the force flag still denies",
   VCS + " worktree remove --force " + slash(BCBYPASS), "deny", "shared-tree", cwd=BCMAIN)
sh("worktree remove: base copies, a clean tree on a pushed branch keeps today's allow",
   VCS + " worktree remove " + slash(BCCLEAN), "allow", cwd=BCMAIN)
sh("worktree remove: base copies, the incident tree, locked, still denies",
   VCS + " worktree remove " + slash(BCLOCKED), "deny", "shared-tree", cwd=BCMAIN)
sh("worktree remove: base copies, the incident tree under a live session still denies",
   VCS + " worktree remove " + slash(BCLIVE), "deny", "shared-tree", cwd=BCMAIN, config=BCLIVECFG)

# THE EXEC BIT. BCEXEC is the incident tree with f.txt at mode 100755 in its base and 0655 in the worktree.
# git reads that copy as 100644, so the tree holds a change no pushed commit has. The guard must refuse it.
if os.name != "nt":
    sh("worktree remove: base copies, the incident tree whose exec bit differs in the worktree still denies",
       VCS + " worktree remove " + slash(BCEXEC), "deny", "shared-tree", cwd=BCMAIN)
else:
    skip_case("worktree remove: base copies, the incident tree whose exec bit differs in the worktree still denies",
              NO_EXEC_BIT)


# THE COST OF THE PUSHED-COPY READ. dirty_paths_are_pushed_copies (git_reads.py) states its cost: at most 14
# fixed git starts, then one ls-tree per candidate tried and one for-each-ref per candidate a match uses, with
# 2 + BASE_COPY_REFLOG_CAP candidates at most. Each git start of that read goes through `_git`, so the count is
# taken there, on a fresh load of git_reads.py. The incident tree must answer True: a False would stop the
# read early and the count would prove nothing about the whole read.
def _load_git_reads():
    """git_reads.py, loaded fresh from the folder GUARD sits in, so a patch to it touches no other load."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "git_reads_cost_case", os.path.join(os.path.dirname(GUARD), "git_reads.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tree_marks(where):
    """{path: mtime_ns} of every file and folder under WHERE, a `.git` entry excluded. A write moves one."""
    marks = {}
    for folder, dirnames, filenames in os.walk(where):
        for name in dirnames + filenames:
            if name != ".git":
                path = os.path.join(folder, name)
                marks[path] = os.lstat(path).st_mtime_ns
    return marks


def base_copies_read_cost_case():
    """The stated cost of dirty_paths_are_pushed_copies, measured on the incident tree, writes nothing."""
    materialize(BCINC)
    git_reads = _load_git_reads()
    starts = []
    real_git = git_reads._git

    def counting_git(where, *args):
        starts.append(args)
        return real_git(where, *args)

    lines = _porcelain(BCINC)
    marks = _tree_marks(BCINC)
    git_reads._git = counting_git
    try:
        got = git_reads.dirty_paths_are_pushed_copies(BCINC, lines)
    finally:
        git_reads._git = real_git
    fixed = [args for args in starts if "ls-tree" not in args and "for-each-ref" not in args]
    ls_tree = [args for args in starts if "ls-tree" in args]
    for_each_ref = [args for args in starts if "for-each-ref" in args]
    candidates = 2 + git_reads.BASE_COPY_REFLOG_CAP
    problems = []
    if got is not True:
        problems.append("the incident tree read as %r, want True" % (got,))
    if len(fixed) > 14:
        problems.append("%d fixed git starts, want at most 14" % len(fixed))
    if len(ls_tree) > candidates:
        problems.append("%d ls-tree starts, want at most %d candidates" % (len(ls_tree), candidates))
    if len(for_each_ref) > len(ls_tree):
        problems.append("%d for-each-ref starts, want at most one per candidate tried (%d)"
                        % (len(for_each_ref), len(ls_tree)))
    if _tree_marks(BCINC) != marks:
        problems.append("a file or folder in the tree changed mtime during the read")
    if _porcelain(BCINC) != lines:
        problems.append("git status --porcelain changed during the read")
    if problems:
        return False, "; ".join(problems)
    return True, "fixed %d (bound 14), ls-tree %d and for-each-ref %d (candidate bound %d), no file written" % (
        len(fixed), len(ls_tree), len(for_each_ref), candidates)


FIXTURELESS_CHECKS.add(base_copies_read_cost_case)  # builds only the base-copy trees it reads

# `git worktree prune`. This deletes NO FILES, only an administrative record, so the worst case
# is an ASK, never a deny, whatever the run location.
sh("worktree prune: a stale record asks, never denies",
   VCS + " worktree prune", "ask", "shared-tree", cwd=WTPRUNE)
sh("worktree prune: nothing to prune passes", VCS + " worktree prune", "allow", cwd=WTMAIN)
sh("worktree prune: -n itself is a read, not a discard, so it passes unconditionally",
   VCS + " worktree prune -n", "allow", cwd=WTPRUNE)
# DATA, NOT A PRUNE. A prune named inside a JSON payload piped to python, at the same stale record,
# changes no record, so it allows.
sh("worktree prune data: a prune named in a JSON payload piped to python, at a stale record, allows",
   "printf '%s' '" + json.dumps({"tool_input": {"command": VCS + " worktree prune"}})
   + "' | python hooks/guard.py", "allow", cwd=WTPRUNE)

# SYMLINKS ARE NOT WORK (owner ruling 2026-10-11). Git lists an untracked symlink as a file, so
# `?? app/node_modules` read as real work and the removal was refused. Deleting a link deletes
# only the link, never its target, so a tree whose only untracked entry is a link passes, with
# or without the force flag. The link's target may sit outside the tree or inside it.
if LINKS_MADE:
    sh("worktree remove: a detached tree whose only untracked entry links outside it passes",
       VCS + " worktree remove " + slash(WTLINKDIR), "allow", cwd=LINKMAIN)
    sh("worktree remove: the same link-only tree passes with the force flag",
       VCS + " worktree remove --force " + slash(WTLINKDIR), "allow", cwd=LINKMAIN)
    sh("worktree remove: a detached tree whose only untracked entry links to a file inside it passes",
       VCS + " worktree remove " + slash(WTLINKFILE), "allow", cwd=LINKMAIN)
    sh("worktree remove: the same in-tree link passes with the force flag",
       VCS + " worktree remove --force " + slash(WTLINKFILE), "allow", cwd=LINKMAIN)
    # THE CONTROLS. Each has a real piece of work beside or inside the link, so each still denies.
    sh("worktree remove: a link next to an untracked real file still denies",
       VCS + " worktree remove " + slash(WTCTRLFILE), "deny", "shared-tree", cwd=LINKMAIN)
    sh("worktree remove: a link next to a tracked change still denies",
       VCS + " worktree remove " + slash(WTCTRLTRACKED), "deny", "shared-tree", cwd=LINKMAIN)
sh("worktree remove: a real untracked node_modules directory holding a file still denies",
   VCS + " worktree remove " + slash(WTCTRLDIR), "deny", "shared-tree", cwd=LINKMAIN)
if LINKS_MADE:
    # A link inside an untracked REAL directory: git shows the directory, not the link, so the
    # directory is the work and it denies.
    sh("worktree remove: a link inside an untracked real directory still denies",
       VCS + " worktree remove " + slash(WTCTRLNESTED), "deny", "shared-tree", cwd=LINKMAIN)


# --------------------------------------------------------------------------- git_reads.branch_is_ancestor in a shallow clone
#
# `git merge-base --is-ancestor` exits 1 both when a branch is not an ancestor and when a shallow clone has cut the
# history between the two. Only the first is False. A shallow clone that holds the pin but cuts the path to it is
# unknown, so branch_is_ancestor answers None. The cases load git_reads by path: the liveness cases patch
# sys.modules["git_reads"] and never restore it.
sys.path.insert(0, os.path.join(REPO, "testing"))
import shallow_clone  # noqa: E402  the one shallow-clone fixture (testing/shallow_clone.py)


def _load_git_reads():
    import importlib.util
    spec = importlib.util.spec_from_file_location("git_reads_by_path", os.path.join(HERE, "git_reads.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _history_repo(name):
    """A repo under this run's folder: main with two commits, and `side`, one commit off the first and not on main.
    Returns (path, sha of the first commit, sha of the side commit)."""
    where = os.path.join(tempfile.mkdtemp(prefix=name + "-", dir=ROOT), "repo")
    make_repo(where, {"a.txt": "one\n"})
    first = run_vcs(where, "rev-parse", "HEAD").stdout.strip()
    write(os.path.join(where, "b.txt"), "two\n")
    run_vcs(where, "add", "-A")
    run_vcs(where, *IDENT, "commit", "-q", "-m", "second")
    run_vcs(where, "checkout", "-q", "-b", "side", first)
    write(os.path.join(where, "side.txt"), "side\n")
    run_vcs(where, "add", "-A")
    run_vcs(where, *IDENT, "commit", "-q", "-m", "side")
    side = run_vcs(where, "rev-parse", "HEAD").stdout.strip()
    run_vcs(where, "checkout", "-q", "main")
    return where, first, side


def git_reads_ancestor_true_case():
    where, first, _ = _history_repo("ancestor-true")
    got = _load_git_reads().branch_is_ancestor(where, "main", first)
    if got is True:
        return True, "an ancestor of main reads True"
    return False, "branch_is_ancestor(main, first commit) reads %r, want True" % (got,)


def git_reads_ancestor_false_case():
    where, _, side = _history_repo("ancestor-false")
    got = _load_git_reads().branch_is_ancestor(where, "main", side)
    if got is False:
        return True, "a commit off main, in a full clone, reads False"
    return False, "branch_is_ancestor(main, side commit) in a full clone reads %r, want False" % (got,)


def git_reads_ancestor_unknown_rev_case():
    where, _, _ = _history_repo("ancestor-unknown")
    got = _load_git_reads().branch_is_ancestor(where, "main", "f" * 40)
    if got is None:
        return True, "a revision git cannot resolve reads None"
    return False, "branch_is_ancestor(main, unknown sha) reads %r, want None" % (got,)


def git_reads_ancestor_shallow_case():
    source, first, _ = _history_repo("ancestor-shallow")
    where = os.path.join(tempfile.mkdtemp(prefix="shallow-", dir=ROOT), "clone")
    error = shallow_clone.make(source, where, first)
    if error:
        return False, "the shallow fixture could not be built: " + error
    facts = shallow_clone.facts(where, first)
    if not (facts["shallow"] and facts["pin_present"] and facts["ancestor_rc"] == 1):
        return False, "the fixture does not reach the bug: %r" % (facts,)
    got = _load_git_reads().branch_is_ancestor(where, "HEAD", first)
    if got is None:
        return True, "a shallow clone that cuts the path to its pin reads None, unknown"
    return False, "branch_is_ancestor(HEAD, pin) in a shallow clone reads %r, want None (unknown)" % (got,)


def git_reads_origin_one_segment_case():
    """An origin path with one segment names no owner, so origin_slug reads None. A pin of the current parse."""
    got = _load_git_reads().origin_slug("https://host/r")
    if got is None:
        return True, "an origin whose path has one segment, https://host/r, reads None"
    return False, "origin_slug('https://host/r') reads %r, want None (no owner segment)" % (got,)


def _branch_delete_in(where, branch):
    """Claude's `git branch -D <branch>` in `where`, decided by the guard under its own config folder. Returns
    (decision, reason, config folder); the folder holds the guard.log that the call wrote."""
    cfg = tempfile.mkdtemp(prefix="branch-del-cfg-", dir=ROOT)
    decision, reason = decide({"raw": None, "tool": "Bash", "cwd": where, "session": None, "env_path": None,
                               "config": cfg, "tool_input": {"command": VCS + " branch -D " + branch}})
    return decision, reason or "", cfg


def _guard_log_lines(cfg):
    path = os.path.join(cfg, "guard.log")
    return open(path, encoding="utf-8").read().splitlines() if os.path.exists(path) else []


def git_reads_branch_only_copy_shallow_case():
    """`branch -D` in a shallow clone, on a branch whose one commit is on no remote and not on main: the only copy.
    The guard denies it with the archive remedy, as it does in a full clone. The cut history makes the ancestry
    unknown, so the cherry and remote tests must decide it. Today branch_proof stops at the unknown ancestry and
    the guard allows."""
    source, _, side = _history_repo("branch-only-copy")
    where = os.path.join(tempfile.mkdtemp(prefix="shallow-", dir=ROOT), "clone")
    error = shallow_clone.make(source, where, side)
    if error:
        return False, "the shallow fixture could not be built: " + error
    if run_vcs(where, "branch", "lone", side).returncode:
        return False, "could not name the side commit as branch lone in the shallow clone"
    decision, reason, _ = _branch_delete_in(where, "lone")
    if decision == "deny" and "`git push origin <branch>:refs/heads/archive/<branch>`" in reason:
        return True, "a shallow clone's only-copy branch is denied, with the archive remedy"
    return False, "branch -D lone in a shallow clone reads %r, want deny with the archive remedy: %s" % (
        decision, reason[:200])


def git_reads_branch_on_remote_shallow_case():
    """`branch -D` in a shallow clone, on a branch whose commit is truly on main but cut from the clone's history, and
    that a remote-tracking ref also holds. The on-remote proof allows it, so the guard writes no unread note. Today
    the cut makes the ancestry unknown, the proof is never read, and the guard allows with a subject-unread note."""
    source, first, _ = _history_repo("branch-on-remote")
    where = os.path.join(tempfile.mkdtemp(prefix="shallow-", dir=ROOT), "clone")
    error = shallow_clone.make(source, where, first)
    if error:
        return False, "the shallow fixture could not be built: " + error
    facts = shallow_clone.facts(where, first)
    if not (facts["shallow"] and facts["pin_present"] and facts["ancestor_rc"] == 1):
        return False, "the fixture does not reach the bug: %r" % (facts,)
    if run_vcs(where, "branch", "pushed", first).returncode or run_vcs(
            where, "update-ref", "refs/remotes/origin/pushed", first).returncode:
        return False, "could not name the pushed branch and its remote-tracking ref in the shallow clone"
    decision, reason, cfg = _branch_delete_in(where, "pushed")
    noted = [line for line in _guard_log_lines(cfg) if "subject-unread" in line]
    if decision == "allow" and not noted:
        return True, "a shallow clone's on-remote branch is allowed, with no unread note"
    return False, "branch -D pushed in a shallow clone reads %r with %d subject-unread line(s), want allow by the on-remote proof: %s" % (
        decision, len(noted), reason[:200])


# ============================================================ 1a. two worktrees, one branch
