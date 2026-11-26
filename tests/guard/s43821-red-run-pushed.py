# section 43821
FAMILY = "red-run"  # the push check on test commits (rule red-run); the cases after this section keep it

# A commit that already sits on a remote ref was sent before this push, so a push does not refuse it for a missing
# Red-run line. The guard judges base..source, and the base is the first of: the destination's remote-tracking ref,
# the source's upstream, then the default base (hooks/guard_merge.py _checked_range). Each form of an already-pushed
# commit has a case, and so do the two forms the push must still refuse: a new commit on top of pushed ones, and a
# commit on no remote ref under a trailered one.
RRP_ROOT = os.path.join(ROOT, "rr-pushed")                # this section's folder under the run folder
RRP_OWN = os.path.join(RRP_ROOT, "own-ref")               # two untrailered commits on origin/topic, a trailered one on top
RRP_STALE = os.path.join(RRP_ROOT, "stale-ref")           # origin/topic still at the base; the old commits are on the remote
RRP_STALE_OTHER = os.path.join(RRP_ROOT, "stale-other")   # the second clone that pushed the old commits to origin/topic
RRP_OTHER = os.path.join(RRP_ROOT, "other-branch")        # no remote-tracking ref for topic; the old commits sit on origin/other
RRP_NEWPLAIN = os.path.join(RRP_ROOT, "new-plain")        # two untrailered commits on origin/topic, a new untrailered one on top
RRP_NOREMOTE = os.path.join(RRP_ROOT, "no-remote")        # origin/topic at the base; an untrailered commit on no remote ref
RRP_OLD = ("hooks/test_x.py", "hooks/test_z.py")          # the test paths of the two commits that are already pushed
RRP_NEW = "hooks/test_y.py"                               # the test path of the commit the push is about


def _rrp_pushed_checkout(where):
    """A checkout of RR_BASE on main, pushed with `git push -u` to a bare remote `where`.git, then on branch topic with
    no upstream. The remote is a real bare repository, so each push and fetch in a case is a real one."""
    make_repo(where, RR_BASE)
    remote = where + ".git"
    os.makedirs(remote, exist_ok=True)
    _rr_run(remote, "init", "-q", "--bare")
    _rr_run(where, "remote", "add", "origin", remote)
    _rr_run(where, "push", "-q", "-u", "origin", "main")
    _rr_run(where, "checkout", "-q", "-b", "topic")
    return remote


def _build_rrp_own():
    _rrp_pushed_checkout(RRP_OWN)
    _rr_commit(RRP_OWN, {RRP_OLD[0]: RR_TEST_TEXT}, "add hooks/test_x.py")
    _rr_commit(RRP_OWN, {RRP_OLD[1]: RR_TEST_TEXT}, "add hooks/test_z.py")
    _rr_run(RRP_OWN, "push", "-q", "-u", "origin", "topic")   # origin/topic holds both old commits
    _rr_commit(RRP_OWN, {RRP_NEW: RR_TEST_TEXT}, "add hooks/test_y.py", RR_NONE_LINE)


def _build_rrp_stale():
    remote = _rrp_pushed_checkout(RRP_STALE)
    _rr_run(RRP_STALE, "push", "-q", "-u", "origin", "topic")  # origin/topic is the base, and stays so below
    _rr_run(RRP_ROOT, "clone", "-q", remote, RRP_STALE_OTHER)
    _rr_run(RRP_STALE_OTHER, "checkout", "-q", "topic")
    _rr_commit(RRP_STALE_OTHER, {RRP_OLD[0]: RR_TEST_TEXT}, "add hooks/test_x.py")
    _rr_commit(RRP_STALE_OTHER, {RRP_OLD[1]: RR_TEST_TEXT}, "add hooks/test_z.py")
    _rr_run(RRP_STALE_OTHER, "push", "-q", "origin", "topic")  # the remote moves ahead of this clone's tracking ref
    # A fetch by URL names no remote, so no remote-tracking ref moves: this clone gets the old commits, and origin/topic
    # stays at the base.
    _rr_run(RRP_STALE, "fetch", "-q", remote, "refs/heads/topic")
    _rr_run(RRP_STALE, "merge", "-q", "--ff-only", "FETCH_HEAD")
    if run_vcs(RRP_STALE, "rev-parse", "refs/remotes/origin/topic").stdout == run_vcs(RRP_STALE, "rev-parse", "topic").stdout:
        sys.exit("fixture setup failed in the red-run pushed fixtures: origin/topic is not stale in %r" % RRP_STALE)
    _rr_commit(RRP_STALE, {RRP_NEW: RR_TEST_TEXT}, "add hooks/test_y.py", RR_NONE_LINE)


def _build_rrp_other():
    _rrp_pushed_checkout(RRP_OTHER)
    _rr_commit(RRP_OTHER, {RRP_OLD[0]: RR_TEST_TEXT}, "add hooks/test_x.py")
    _rr_commit(RRP_OTHER, {RRP_OLD[1]: RR_TEST_TEXT}, "add hooks/test_z.py")
    _rr_run(RRP_OTHER, "push", "-q", "origin", "topic:other")  # the old commits reach origin/other; topic gets no ref
    if run_vcs(RRP_OTHER, "rev-parse", "-q", "--verify", "refs/remotes/origin/topic").returncode == 0:
        sys.exit("fixture setup failed in the red-run pushed fixtures: origin/topic exists in %r" % RRP_OTHER)
    _rr_commit(RRP_OTHER, {RRP_NEW: RR_TEST_TEXT}, "add hooks/test_y.py", RR_NONE_LINE)


def _build_rrp_newplain():
    _rrp_pushed_checkout(RRP_NEWPLAIN)
    _rr_commit(RRP_NEWPLAIN, {RRP_OLD[0]: RR_TEST_TEXT}, "add hooks/test_x.py")
    _rr_commit(RRP_NEWPLAIN, {RRP_OLD[1]: RR_TEST_TEXT}, "add hooks/test_z.py")
    _rr_run(RRP_NEWPLAIN, "push", "-q", "-u", "origin", "topic")
    _rr_commit(RRP_NEWPLAIN, {RRP_NEW: RR_TEST_TEXT}, "add hooks/test_y.py")  # no trailer, never pushed


def _build_rrp_noremote():
    _rrp_pushed_checkout(RRP_NOREMOTE)
    _rr_run(RRP_NOREMOTE, "push", "-q", "-u", "origin", "topic")  # origin/topic is the base
    _rr_commit(RRP_NOREMOTE, {RRP_OLD[0]: RR_TEST_TEXT}, "add hooks/test_x.py")  # on no remote ref, no trailer
    _rr_commit(RRP_NOREMOTE, {RRP_NEW: RR_TEST_TEXT}, "add hooks/test_y.py", RR_NONE_LINE)


lazy_fixture([RRP_OWN], _build_rrp_own)
lazy_fixture([RRP_STALE], _build_rrp_stale)
lazy_fixture([RRP_OTHER], _build_rrp_other)
lazy_fixture([RRP_NEWPLAIN], _build_rrp_newplain)
lazy_fixture([RRP_NOREMOTE], _build_rrp_noremote)

# The two forms a push must allow: the commits lacking a trailer are already on a remote ref, and only the new commit
# is sent. The own-ref form is allowed on main already, so it pins the behaviour; the two others are refused on main.
rr_allow("two untrailered test commits already on origin/topic, a trailered commit on top",
         VCS + " push origin topic", RRP_OWN)
rr_allow("origin/topic stale at the base, the untrailered test commits on the remote from another clone",
         VCS + " push origin topic", RRP_STALE)
rr_allow("no remote-tracking ref for topic, the untrailered test commits on origin/other",
         VCS + " push origin topic", RRP_OTHER)

# The two forms a push must still refuse: a new commit that was never pushed, and an untrailered commit that is on no
# remote ref, even under a trailered commit.
rr_refuse("two untrailered test commits on origin/topic, then a new untrailered test commit never pushed",
          VCS + " push origin topic", RRP_NEWPLAIN)
rr_refuse("an untrailered test commit on no remote ref, under a trailered test commit",
          VCS + " push origin topic", RRP_NOREMOTE)
