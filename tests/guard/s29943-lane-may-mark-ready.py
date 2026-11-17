# section 29943
FAMILY = "lane-may-mark-ready"  # GUARD_FAMILY=lane-may-mark-ready selects this section's cases
#
# Decision draft-until-reviewed, ruling Q2: a lane marks its own lane PR ready once. The lane runs
# `merge --role lane --step <its step> <pr> --ready`. The guard lets that call through only when the
# lane's own record proves the step (a cs-step tag, with the claude-settings repo tag) and the pull
# request's head is that step's branch, in either lane head form (shared_names.lane_head_refs).
#
# The bare `merge <pr> --ready` from a lane has no step, so it stays refused. s29942 pins that row.
# Case 1 and case 1b are red on the guard before the change: the lane ready refusal denies them with
# merge-role-proof. The other cases are controls, green on the old guard too.

LANE_READY_ROLE = MERGE_SHIM + " --role lane --step " + ARCHIVE_SLUG + " 12"  # pull request 12 is the fake gh's own number
LANE_READY_NOW = LANE_READY_ROLE + " --ready"
LANE_READY_CONFIRM = LANE_READY_ROLE + " --confirm"
LANE_READY_SHA = "d" * 40
LANE_READY_ENV = {**ROLE_ENV, "CLAUDE_CODE_REMOTE": "true"}  # the cloud env of s29942's CLOUD_ENV
LANE_READY_OWN = os.path.join(ROOT, "lane-ready-own")          # pull request 12's head is the lane's step
LANE_READY_FORM = os.path.join(ROOT, "lane-ready-form")        # its head is lane/<step>
LANE_READY_OTHER = os.path.join(ROOT, "lane-ready-other")      # its head is another step's branch
LANE_READY_PREFIX = os.path.join(ROOT, "lane-ready-prefix")    # its head is a prefix of the step's slug, not the slug
LANE_READY_BROKEN = os.path.join(ROOT, "lane-ready-broken")    # every gh call answers with a failure


def _build_lane_ready_gh():
    """The fake gh of each lane-ready case: a draft pull request 12 on claude-settings, with the head each folder names."""
    for folder, head in ((LANE_READY_OWN, ARCHIVE_SLUG), (LANE_READY_FORM, "lane/" + ARCHIVE_SLUG),
                         (LANE_READY_OTHER, "other-step"), (LANE_READY_PREFIX, "lane-closes")):
        make_fake_gh(folder, "main", need=[ARCH_REPO_SETTINGS], head_sha=LANE_READY_SHA, head_ref=head, draft=True)
    make_fake_gh(LANE_READY_BROKEN, "main", need=[ARCH_REPO_SETTINGS], head_sha=LANE_READY_SHA, head_ref=ARCHIVE_SLUG,
                 draft=True, broken=True)


lazy_fixture([LANE_READY_OWN, LANE_READY_FORM, LANE_READY_OTHER, LANE_READY_PREFIX, LANE_READY_BROKEN], _build_lane_ready_gh)


def lane_ready_path(folder):
    """The PATH a guard run gets to find the fake gh in `folder`, then the interpreter's and git's."""
    return folder + os.pathsep + PY_PATH + os.pathsep + GIT_PATH


# Case 1 (red on the old guard): the lane's own step, and the head is the step's branch.
sh("merge-role-proof: a lane marks its own lane PR ready with --role lane --step <its step> <pr> --ready is allowed",
   LANE_READY_NOW, "allow", silent=True, cwd=LANE_REPO, env=LANE_READY_ENV, transcript=role_path("lane-step"),
   env_path=lane_ready_path(LANE_READY_OWN), config=LT_EMPTY)
# Case 1b (red on the old guard): the same, with the head in the lane/<step> form.
sh("merge-role-proof: a lane marks its lane PR ready when the head is lane/<its step>, the other form of its branch, is allowed",
   LANE_READY_NOW, "allow", silent=True, cwd=LANE_REPO, env=LANE_READY_ENV, transcript=role_path("lane-step"),
   env_path=lane_ready_path(LANE_READY_FORM), config=LT_EMPTY)

# Case 2 (control, green on the old guard): the same lane on a pull request whose head is not its step's branch is refused.
sh("merge-role-proof: a lane marks a lane PR ready when its head is another step's branch is refused",
   LANE_READY_NOW, "deny", rule=ROLE_RULE, cwd=LANE_REPO, env=LANE_READY_ENV, transcript=role_path("lane-step"),
   env_path=lane_ready_path(LANE_READY_OTHER), config=LT_EMPTY)
sh("merge-role-proof: a lane marks a lane PR ready when its head is a prefix of its step's slug is refused",
   LANE_READY_NOW, "deny", rule=ROLE_RULE, cwd=LANE_REPO, env=LANE_READY_ENV, transcript=role_path("lane-step"),
   env_path=lane_ready_path(LANE_READY_PREFIX), config=LT_EMPTY)
# A pull request read that cannot run is refused, whatever rule names it: the guard fails closed.
sh("merge-role-proof: a lane marks a lane PR ready when the pull request read fails is refused",
   LANE_READY_NOW, "deny", cwd=LANE_REPO, env=LANE_READY_ENV, transcript=role_path("lane-step"),
   env_path=lane_ready_path(LANE_READY_BROKEN), config=LT_EMPTY)
# The step must prove itself: no --step is refused, and so is a --step the lane's record does not carry, even when the head is that branch.
sh("merge-role-proof: a lane marks a lane PR ready with no --step is refused",
   MERGE_SHIM + " --role lane 12 --ready", "deny", rule=ROLE_RULE, cwd=LANE_REPO, env=LANE_READY_ENV,
   transcript=role_path("lane-step"), env_path=lane_ready_path(LANE_READY_OWN), config=LT_EMPTY)
sh("merge-role-proof: a lane marks a lane PR ready with a --step its record does not carry is refused, though the head is that branch",
   MERGE_SHIM + " --role lane --step other-step 12 --ready", "deny", rule=ROLE_RULE, cwd=LANE_REPO, env=LANE_READY_ENV,
   transcript=role_path("lane-step"), env_path=lane_ready_path(LANE_READY_OTHER), config=LT_EMPTY)

# Controls (green on the old guard): --confirm is judged as before, so the lane ready change does not widen it.
sh("merge-role-proof: a lane's --confirm of its own lane PR, in its own checkout, is allowed as before",
   LANE_READY_CONFIRM, "allow", silent=True, cwd=LANE_REPO, env=LANE_READY_ENV, transcript=role_path("lane-step"),
   env_path=lane_ready_path(LANE_READY_OWN), config=LT_EMPTY)
sh("merge-confirm-repo: a lane's --confirm run from another repo's checkout is refused as before",
   LANE_READY_CONFIRM, "deny", rule=REPO_RULE, cwd=REPO_A, env=LANE_READY_ENV, transcript=role_path("lane-step"),
   env_path=lane_ready_path(LANE_READY_OWN), config=LT_EMPTY)
