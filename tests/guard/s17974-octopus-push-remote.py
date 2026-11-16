# section 17974
FAMILY = "octopus-push"
# A merge the remote already holds, which this clone's remote-tracking refs do not show. The guard reads
# `--not --remotes=<remote>` (`_octopus_hit`) in the directory the push runs in, so a tracking ref behind the
# remote hides a merge the push does not send. Each builder reuses the octopus helpers of section 17973 and the
# bare remote of `_cmk_pushed` (section 17500).

OCT_NEWDEST = os.path.join(ROOT, "oct-newdest")            # origin's main holds O; a new branch adds one plain commit
OCT_NEWDEST_CTRL = os.path.join(ROOT, "oct-newdest-ctrl")  # as oct-newdest, plus a new three-parent merge
OCT_STALE = os.path.join(ROOT, "oct-stale")                # origin's main holds O; this clone's tracking ref does not
OCT_STALE_WT = os.path.join(ROOT, "oct-stale-wt")          # a linked worktree of oct-stale, on a branch with a plain commit
OCT_STALE_REMOTE = os.path.join(CMKREMOTE, os.path.basename(OCT_STALE) + ".git")   # the bare remote of oct-stale


def _oct_new_branch(where, control):
    """origin's main gains O. A branch cut from origin/main adds one plain commit, so the push sends that commit
    alone. With `control`, the branch also takes a new three-parent merge that no remote ref holds."""
    _oct_on_origin_main(where)
    _cmk_run(where, "checkout", "-q", "-b", "lane", "--no-track", "origin/main")
    _cmk_commit(where, "p.txt", "p\n", "plain commit on a new branch")
    _oct_must(where, "origin/main..HEAD", [], "one plain commit past origin/main")
    if control:
        _oct_branch(where, "x3", "x3.txt", "x3\n")
        _oct_branch(where, "y3", "y3.txt", "y3\n")
        _oct_merge(where, "lane", ["x3", "y3"])
        _oct_must(where, "origin/main..HEAD", [3], "the new three-parent merge, on no remote ref")


def _build_octopus_newdest():
    _oct_new_branch(OCT_NEWDEST, control=False)


def _build_octopus_newdest_ctrl():
    _oct_new_branch(OCT_NEWDEST_CTRL, control=True)


def _build_octopus_stale():
    """origin's main gains O, then this clone's origin/main tracking ref is put back to the base, as a clone holds
    that never fetched the push. The branch cut from src (which holds O) adds a plain commit. The remote holds O,
    and no tracking ref of this clone does."""
    _oct_on_origin_main(OCT_STALE)
    base = _cmk_run(OCT_STALE, "rev-parse", "main")
    _cmk_run(OCT_STALE, "update-ref", "refs/remotes/origin/main", base)
    _oct_must(OCT_STALE, "origin/main", [], "the stale tracking ref holds no merge")
    _oct_must(OCT_STALE_REMOTE, "main", [3], "the remote's main holds the octopus")
    _cmk_run(OCT_STALE, "checkout", "-q", "-b", "lane", "src")
    _cmk_commit(OCT_STALE, "p.txt", "p\n", "plain commit on lane")
    _oct_must(OCT_STALE, "lane --not --remotes=origin", [3], "the octopus sits in the push range")
    _cmk_run(OCT_STALE, "worktree", "add", "-q", "-b", "lane-wt", OCT_STALE_WT, "src")
    _cmk_commit(OCT_STALE_WT, "p2.txt", "p2\n", "plain commit on lane-wt")
    _oct_must(OCT_STALE_WT, "lane-wt --not --remotes=origin", [3], "the octopus sits in the worktree's push range")


lazy_fixture([OCT_NEWDEST], _build_octopus_newdest)
lazy_fixture([OCT_NEWDEST_CTRL], _build_octopus_newdest_ctrl)
lazy_fixture([OCT_STALE, OCT_STALE_WT, OCT_STALE_REMOTE], _build_octopus_stale)

# origin's main holds the octopus, and the branch is new: the push sends one plain commit. The control adds a new
# three-parent merge that no remote ref holds, so it is refused.
oct_allow("a push of a new branch with one plain commit, cut from origin/main, whose octopus is on origin/main",
          VCS + " push origin lane", OCT_NEWDEST)
oct_refuse("a push of a new branch with a new three-parent merge that no remote ref holds, above origin/main",
           VCS + " push origin lane", OCT_NEWDEST_CTRL)

# The remote holds the octopus, and this clone's origin/main tracking ref does not. The push sends one plain commit,
# so it passes. A linked worktree shares the clone's refs. `git -C` names the directory the push runs in.
oct_allow("a push from a clone whose origin/main tracking ref lacks an octopus that the remote holds",
          VCS + " push origin lane", OCT_STALE)
oct_allow("a push from a linked worktree of a clone whose origin/main tracking ref lacks that octopus",
          VCS + " push origin lane-wt", OCT_STALE_WT)
oct_allow("a push with git -C of a clone whose origin/main tracking ref lacks that octopus, run from another clone",
          VCS + " -C " + slash(OCT_STALE) + " push origin lane", OCT_PLAIN)
# The control for `git -C`: the named clone holds the octopus in its tracking ref, and the cwd's stale ref must not decide.
oct_allow("a push with git -C of a clone whose origin/main tracking ref holds the octopus, run from a stale clone",
          VCS + " -C " + slash(OCT_NEWDEST) + " push origin lane", OCT_STALE)
