# section 43421
from guard_core import REPLAY_MARKS  # noqa: E402  the marks a replay leaves in the git dir: the one home, never copied here
FAMILY = "red-run"  # the commit-time check on test commits (rule red-run, decision red-run-trailer-on-test-commits)

# A lone `git commit` with test lines staged is not judged while a replay is in progress. `_replaying` in guard_merge
# reads MERGE_HEAD and each mark of REPLAY_MARKS in the git dir. Each mark has a case on a state that git itself leaves
# with that mark, and each commit's -m holds no trailer, so an allow is the replay's doing. A merge in a linked worktree
# keeps MERGE_HEAD in the worktree's own git dir, reached through its `.git` file, so it has a case of its own. Each
# state is checked before its cases run: a state that lost its mark would let an allow pass for the wrong reason.

RPROOT = os.path.join(ROOT, "replay")                 # one folder per state, under the run folder
RP_SQUASH = os.path.join(RPROOT, "rp-squash")         # git merge --squash: SQUASH_MSG
RP_CHERRY = os.path.join(RPROOT, "rp-cherry")         # a cherry-pick stopped on a conflict, then resolved: CHERRY_PICK_HEAD
RP_PICK = os.path.join(RPROOT, "rp-pick")             # git cherry-pick --no-commit: MERGE_MSG, and no other mark
RP_REVERT = os.path.join(RPROOT, "rp-revert")         # git revert --no-commit: REVERT_HEAD
RP_REBASE = os.path.join(RPROOT, "rp-rebase")         # a merge-backend rebase stopped on a conflict, then resolved: rebase-merge
RP_APPLY = os.path.join(RPROOT, "rp-apply")           # a rebase --apply stopped on a conflict, then resolved: rebase-apply
RP_MAIN = os.path.join(RPROOT, "rp-main")             # the main checkout the two linked worktrees below belong to
RP_LANE = os.path.join(RPROOT, "rp-lane")             # a linked worktree: git merge --no-commit of main in progress
RP_PLAIN = os.path.join(RPROOT, "rp-plain")           # a linked worktree with no merge in progress: the control

# The mark each replay state holds, for the coverage check below. MERGE_MSG appears in several states too; RP_PICK is
# the state where it is the only mark.
RP_STATE_OF = {
    "SQUASH_MSG": RP_SQUASH,
    "CHERRY_PICK_HEAD": RP_CHERRY,
    "MERGE_MSG": RP_PICK,
    "REVERT_HEAD": RP_REVERT,
    "rebase-merge": RP_REBASE,
    "rebase-apply": RP_APPLY,
}


def _rp_stop(where, *args):
    """A git call that must stop on a conflict, the stop a replay state is made of. Exit 0 means no conflict, so the
    state is not the one its case names: the suite stops here, not in a case."""
    done = run_vcs(where, *IDENT, *args)
    if done.returncode == 0:
        sys.exit("fixture setup failed in the replay fixtures: git %s in %r did not stop on a conflict: %s"
                 % (" ".join(args), where, done.stdout.strip()))


def _rp_scope(where, mark):
    """Stop the suite unless `mark` is in the git dir that `where` reads, and hooks/test_x.py is staged there. Scope
    comes before the subject: a state that lost its mark would make its case pass for the wrong reason."""
    path = run_vcs(where, "rev-parse", "--git-path", mark).stdout.strip()
    if not os.path.exists(os.path.join(where, path)):
        sys.exit("fixture setup failed in the replay fixtures: %s is not in the git dir of %r, where %r reads it"
                 % (mark, where, path))
    _rc_scope(where, [RR_TEST], "A ")


def _build_rp_squash():
    make_repo(RP_SQUASH, {"a.txt": "base\n"})
    _rr_run(RP_SQUASH, "checkout", "-b", "topic")
    _rr_commit(RP_SQUASH, {"b.txt": "topic\n"}, "topic b")
    _rr_run(RP_SQUASH, "checkout", "main")
    _rr_run(RP_SQUASH, "merge", "--squash", "topic")
    _rc_stage(RP_SQUASH, {RR_TEST: RR_TEST_TEXT})
    _rp_scope(RP_SQUASH, "SQUASH_MSG")


def _build_rp_cherry():
    make_repo(RP_CHERRY, {"a.txt": "base\n"})
    _rr_run(RP_CHERRY, "checkout", "-b", "topic")
    _rr_commit(RP_CHERRY, {"a.txt": "topic\n"}, "topic a")
    _rr_run(RP_CHERRY, "checkout", "main")
    _rr_commit(RP_CHERRY, {"a.txt": "main\n"}, "main a")
    _rp_stop(RP_CHERRY, "cherry-pick", "topic")
    _rc_stage(RP_CHERRY, {"a.txt": "resolved\n", RR_TEST: RR_TEST_TEXT})
    _rp_scope(RP_CHERRY, "CHERRY_PICK_HEAD")


def _build_rp_pick():
    make_repo(RP_PICK, {"a.txt": "base\n"})
    _rr_run(RP_PICK, "checkout", "-b", "topic")
    _rr_commit(RP_PICK, {"b.txt": "topic\n"}, "topic b")
    _rr_run(RP_PICK, "checkout", "main")
    _rr_run(RP_PICK, "cherry-pick", "--no-commit", "topic")
    _rc_stage(RP_PICK, {RR_TEST: RR_TEST_TEXT})
    _rp_scope(RP_PICK, "MERGE_MSG")


def _build_rp_revert():
    make_repo(RP_REVERT, {"a.txt": "base\n"})
    _rr_commit(RP_REVERT, {"b.txt": "second\n"}, "add b")
    _rr_run(RP_REVERT, "revert", "--no-commit", "HEAD")
    _rc_stage(RP_REVERT, {RR_TEST: RR_TEST_TEXT})
    _rp_scope(RP_REVERT, "REVERT_HEAD")


def _build_rp_rebase():
    make_repo(RP_REBASE, {"a.txt": "base\n"})
    _rr_run(RP_REBASE, "checkout", "-b", "topic")
    _rr_commit(RP_REBASE, {"a.txt": "topic\n"}, "topic a")
    _rr_run(RP_REBASE, "checkout", "main")
    _rr_commit(RP_REBASE, {"a.txt": "main\n"}, "main a")
    _rr_run(RP_REBASE, "checkout", "topic")
    _rp_stop(RP_REBASE, "rebase", "--merge", "main")
    _rc_stage(RP_REBASE, {"a.txt": "resolved\n", RR_TEST: RR_TEST_TEXT})
    _rp_scope(RP_REBASE, "rebase-merge")


def _build_rp_apply():
    make_repo(RP_APPLY, {"a.txt": "base\n"})
    _rr_run(RP_APPLY, "checkout", "-b", "topic")
    _rr_commit(RP_APPLY, {"a.txt": "topic\n"}, "topic a")
    _rr_run(RP_APPLY, "checkout", "main")
    _rr_commit(RP_APPLY, {"a.txt": "main\n"}, "main a")
    _rr_run(RP_APPLY, "checkout", "topic")
    _rp_stop(RP_APPLY, "rebase", "--apply", "main")
    _rc_stage(RP_APPLY, {"a.txt": "resolved\n", RR_TEST: RR_TEST_TEXT})
    _rp_scope(RP_APPLY, "rebase-apply")


def _build_rp_worktrees():
    make_repo(RP_MAIN, {"a.txt": "base\n"})
    _rr_run(RP_MAIN, "worktree", "add", "-b", "lane-merge", RP_LANE, "main")
    _rr_run(RP_MAIN, "worktree", "add", "-b", "lane-plain", RP_PLAIN, "main")
    _rr_commit(RP_LANE, {"lane.txt": "lane\n"}, "lane change")
    _rr_commit(RP_MAIN, {"c.txt": "main\n"}, "main change")
    _rr_run(RP_LANE, "merge", "--no-commit", "--no-ff", "main")
    _rc_stage(RP_LANE, {RR_TEST: RR_TEST_TEXT})
    _rp_scope(RP_LANE, "MERGE_HEAD")
    _rc_stage(RP_PLAIN, {RR_TEST: RR_TEST_TEXT})
    _rc_scope(RP_PLAIN, [RR_TEST], "A ")


lazy_fixture([RP_SQUASH], _build_rp_squash)
lazy_fixture([RP_CHERRY], _build_rp_cherry)
lazy_fixture([RP_PICK], _build_rp_pick)
lazy_fixture([RP_REVERT], _build_rp_revert)
lazy_fixture([RP_REBASE], _build_rp_rebase)
lazy_fixture([RP_APPLY], _build_rp_apply)
lazy_fixture([RP_MAIN, RP_LANE, RP_PLAIN], _build_rp_worktrees)


# 1. One case per mark: a lone commit with test lines staged and no trailer is allowed while the state holds the mark.
rc_allow("a commit -m squash x during git merge --squash (SQUASH_MSG), with test lines staged",
         VCS + ' commit -m "squash x"', RP_SQUASH)
rc_allow("a commit -m during a cherry-pick stopped on a conflict (CHERRY_PICK_HEAD), with test lines staged",
         VCS + ' commit -m "finish x"', RP_CHERRY)
rc_allow("a commit -m during a cherry-pick --no-commit (MERGE_MSG, the only mark), with test lines staged",
         VCS + ' commit -m "finish x"', RP_PICK)
rc_allow("a commit -m during a revert --no-commit (REVERT_HEAD), with test lines staged",
         VCS + ' commit -m "finish x"', RP_REVERT)
rc_allow("a commit -m during a merge-backend rebase stopped on a conflict (rebase-merge), with test lines staged",
         VCS + ' commit -m "finish x"', RP_REBASE)
rc_allow("a commit -m during a rebase --apply stopped on a conflict (rebase-apply), with test lines staged",
         VCS + ' commit -m "finish x"', RP_APPLY)

# 2. A merge in a linked worktree: MERGE_HEAD sits in the worktree's own git dir, reached through its `.git` file.
rc_allow("a commit -m in a linked worktree during git merge --no-commit (MERGE_HEAD in its own git dir), with test lines staged",
         VCS + ' commit -m "finish x"', RP_LANE)

# 3. The control for the linked worktree: the same commit with no merge in progress is refused, so the allow above is
# the merge's doing and not a linked worktree that the judge never reads.
rc_refuse("a commit -m in a linked worktree with no merge in progress, adding hooks/test_x.py with no Red-run line",
          VCS + ' commit -m "finish x"', RP_PLAIN)


RP_COVER_LABEL = ("red-run: each mark in REPLAY_MARKS has a replay state of its own in section 43421, so a new mark "
                  "cannot ship without a case")
LOG_FAMILY[RP_COVER_LABEL] = FAMILY


def rp_cover_case():
    """Every mark the guard reads in a replay has a state here. A mark with no state is a replay the cases never reach."""
    missing = [mark for mark in REPLAY_MARKS if mark not in RP_STATE_OF]
    if missing:
        return False, "REPLAY_MARKS names %s with no replay state in section 43421" % ", ".join(missing)
    extra = [mark for mark in RP_STATE_OF if mark not in REPLAY_MARKS]
    if extra:
        return False, "section 43421 has a replay state for %s, which REPLAY_MARKS does not name" % ", ".join(extra)
    return True, "each of the %d marks in REPLAY_MARKS has a replay state" % len(REPLAY_MARKS)


LOG_CHECKS = LOG_CHECKS + ((RP_COVER_LABEL, rp_cover_case),)
