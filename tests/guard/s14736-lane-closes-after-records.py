# section 14736
FAMILY = "lane-closes-after-records"
#
# Rule lane-closes-after-records. The cases pin when archive_session of a lane is refused and when it is allowed.
# A lane must not close while its records pull request is open, or those records are lost. The guard reads
# the target's newest get_session record in this session's own transcript, as merge-role-proof and
# trust-card-in-build read theirs:
#   - the record has no cs-build:lane tag: allow, the target is not a lane;
#   - a lane, with no record of the target in the transcript: refuse, and the remedy steers to get_session;
#   - a lane: the guard reads the open pull requests of the lane's cs-repo. Any open one whose head names the
#     cs-step slug refuses. None allows. A read that cannot run refuses: guards fail closed.
#   - a lane whose record names branches (external_metadata.current_branches): each branch ahead of its repo's
#     default branch, on no pull request in any state, refuses. A 404 on the branch's compare means the branch is not
#     in that repo. Any other failed read refuses. A branch equal to the default, or behind it, or archive/..., is skipped.
#     A branch whose archive copy holds its tip is covered. The copies are listed under archive/<branch>, and only the
#     exact name and `<branch>-<digits>` count; a listed copy under any other name is never compared.
# The allows are as load-bearing as the refusals: a false alarm on a finished lane blocks the batch runner.
ARCHIVE_TOOL = "mcp__claude-code-remote__archive_session"
ARCHIVE_RULE = "lane-closes-after-records"
ARCHIVE_NAMED = ("archive_session",)  # the refusal never names the tool, so it never invites the same act
ARCHIVE_STEER = ("get_session", "alone", ("retry", "Retry"))  # the remedy: get_session on the target alone, then retry
ARCHIVE_READ_PIN = ("could not be read",)  # the reason of every unreadable read
ARCHIVE_RETRY_PIN = ("Retry once gh answers",)  # the remedy of an unreadable read that is no 403 or 404: retry, and name no act
ARCHIVE_NO_ACT = ("add_repo",)  # a refusal that names no act to add a repo
ARCHIVE_OWNER = "5c2e7d1a-0000-4000-8000-00000000a7c1"  # the calling session's payload id, which an override names
AGENT_NO_REMOTE = "agent-no-remote-tools"  # the rule id the refusal names; the agent-remote-tools section reads it too


def fake_gh_path(folder):
    """The PATH a guard run gets to find the fake gh in `folder`, as the merge cases give it."""
    return folder + os.pathsep + PY_PATH


def archive_refuse(name, transcript, env_path, carries=(), lacks=(), agent_id=None):
    """An archive_session of the target the guard refuses. The reason names its rule, never the tool. `lacks`
    adds fragments the reason must not hold, so a case can tell one refusal reason from another. `agent_id`, when
    given, makes the call an agent's, as the harness sends it."""
    more = (lacks,) if isinstance(lacks, str) else tuple(lacks)
    add("lane-closes-after-records: " + name, "deny", rule=ARCHIVE_RULE, tool=ARCHIVE_TOOL, cwd=NOGIT,
        lacks=ARCHIVE_NAMED + more, carries=carries, transcript=transcript, env=ROLE_ENV, env_path=env_path,
        session_id=ROLE_OTHER, agent_id=agent_id)


def archive_allow(name, transcript, env_path, agent_id=None):
    """An archive_session of the target the guard lets through silently. `agent_id` as in archive_refuse."""
    add("lane-closes-after-records: " + name, "allow", tool=ARCHIVE_TOOL, cwd=NOGIT, silent=True,
        transcript=transcript, env=ROLE_ENV, env_path=env_path, session_id=ROLE_OTHER, agent_id=agent_id)


def agent_archive_refuse(name, transcript, env_path, agent_id):
    """An agent's archive_session of a target lane-closes allows, refused by agent-no-remote-tools after it. The reason
    names that rule and none of the lane's reasons, so a refusal that came from the lane logic does not pass."""
    add("lane-closes-after-records: " + name, "deny", rule=AGENT_NO_REMOTE, tool=ARCHIVE_TOOL, cwd=NOGIT,
        lacks=ARCHIVE_NAMED + ARCHIVE_OPEN_PIN + ARCHIVE_NO_RECORD_PIN + ARCHIVE_READ_PIN, transcript=transcript,
        env=ROLE_ENV, env_path=env_path, session_id=ROLE_OTHER, agent_id=agent_id)


# A lane whose open pull request has a head exactly equal to its step slug is its own pull request: refused.
archive_refuse("a lane whose open head is exactly its slug is refused", role_path("archive-lane"),
               fake_gh_path(ARCHOPEN))
# A lane whose slug pull request was closed as replaced, or merged, has no open one: the archive is allowed.
archive_allow("a lane whose slug pull request was closed as replaced is allowed", role_path("archive-lane"),
              fake_gh_path(ARCHCLOSED))
archive_allow("a lane whose slug pull request was merged is allowed", role_path("archive-lane"),
              fake_gh_path(ARCHMERGED))
# The match is exact: an open head that only contains the lane's step id is another pull request, not the lane's.
archive_allow("a lane c1 with an open head c10 is allowed: c10 is not c1", role_path("archive-lane-c1"),
              fake_gh_path(ARCHNEAR_C10))
archive_allow("a lane c1 with an open head claude/c10-x1 is allowed: that head is not c1", role_path("archive-lane-c1"),
              fake_gh_path(ARCHNEAR_C10X))
archive_allow("a lane ci with an open head claude/fix-ci-retry-x1 is allowed: that head is not ci",
              role_path("archive-lane-ci"), fake_gh_path(ARCHNEAR_CI))
# A target whose record names no lane is not judged, even with an open pull request on the slug.
archive_allow("a target tagged cs-build:triage is allowed, though a slug pull request is open",
              role_path("archive-triage"), fake_gh_path(ARCHOPEN))
# The same target, its record wrapped as another session's untrusted text. The record still decides: a triage target
# is allowed. A reader that json-parses the whole body finds no record, and refuses.
archive_allow("a wrapped record of a non-lane target (cs-build:triage) is allowed: the record is read inside its wrapper",
              role_path("archive-wrapped-triage"), fake_gh_path(ARCHOPEN))
# No record of the target: the guard cannot tell it is no lane, so it refuses and steers to get_session. The
# gh here has no open slug pull request, so a guard that skips the record and reads gh alone would allow.
archive_refuse("no record of the target in the transcript is refused, and the remedy steers to get_session",
               role_path("archive-no-target"), fake_gh_path(ARCHCLOSED), carries=ARCHIVE_STEER)
# The calling session's own lane record is not the target's: a lane-tagged own record does not stand for it.
archive_refuse("an own lane record with no record of the target is refused, and the remedy steers to get_session",
               role_path("archive-own-lane"), fake_gh_path(ARCHCLOSED), carries=ARCHIVE_STEER)
# A read that cannot run refuses: a broken gh, and a missing gh.
archive_refuse("a lane whose open pull requests cannot be read is refused", role_path("archive-lane"),
               fake_gh_path(GHBROKEN))
archive_refuse("a lane with no gh on the path is refused, and says retry: no act to add a repo",
               role_path("archive-lane"), GHNONE_PATH, carries=ARCHIVE_READ_PIN + ARCHIVE_RETRY_PIN, lacks=ARCHIVE_NO_ACT)
# Every page of the open list is read: the slug's pull request sits on page two.
archive_refuse("a lane whose slug pull request is on page two of the open list is refused",
               role_path("archive-lane"), fake_gh_path(ARCHPAGE))
# The newest record of the target counts. A read untagged, then a read tagged lane, is a lane.
archive_refuse("a target read untagged, then tagged lane, is refused: the newest record counts",
               role_path("archive-stale-then-lane"), fake_gh_path(ARCHOPEN))
# No transcript at all: no record can be read, so the target's tags are unknown, and the call is refused.
archive_refuse("a payload with no transcript_path is refused", None, fake_gh_path(ARCHOPEN))
# The containment read. An open draft lane pull request whose head is already in main has landed through the integration
# pull request, so it no longer blocks the archive. Only a draft is released; a read that fails refuses, and says so.
# The two refusal reasons are told apart by a fragment each: the open-pull-request reason says "still open", and the
# read-failure reason says "could not be read". A case pins its own reason and not the other's.
ARCHIVE_OPEN_PIN = ("still open",)


def add_repo_pin(repo):
    """The fragment a 403 or 404 on the read of `repo` names: the act, then the retry. The reason keeps ARCHIVE_READ_PIN too."""
    return "add_repo " + repo + " (read), then retry"


# Only a 403 or 404 on a repo's read names add_repo for that repo. Every other failure (a 500, a timeout, a refused
# connection, no gh, text that is not JSON, a shape the read does not know) says to retry, and names no act.
archive_refuse("a lane whose open pull requests answer non-JSON names no add_repo, and says retry",
               role_path("archive-lane"), fake_gh_path(GHBROKEN), carries=ARCHIVE_READ_PIN + ARCHIVE_RETRY_PIN,
               lacks=ARCHIVE_NO_ACT)
# The branch arm: q_max's pull request list for the branch is a server error, and the refusal names no act.
archive_refuse("a lane whose branch pull request list in q_max is a server error names no add_repo, and says retry",
               role_path("archive-inc"), fake_gh_path(ARCHINC_PULLS500),
               carries=ARCHIVE_READ_PIN + ARCHIVE_RETRY_PIN, lacks=ARCHIVE_NO_ACT)
archive_refuse("a lane whose q_max default-branch read is a server error names no add_repo, and says retry",
               role_path("archive-inc"), fake_gh_path(ARCHINC_REPO500),
               carries=ARCHIVE_READ_PIN + ARCHIVE_RETRY_PIN, lacks=ARCHIVE_NO_ACT)
# Two cs-repo tags, claude-settings first and q_max second. Each case fails one repo's open-list read with a 500.
archive_refuse("a lane whose second cs-repo open pull request list is a server error names no add_repo, and says retry",
               role_path("archive-inc"), fake_gh_path(ARCHINC_OPENLIST_QMAX),
               carries=ARCHIVE_READ_PIN + ARCHIVE_RETRY_PIN, lacks=ARCHIVE_NO_ACT)
archive_refuse("a lane whose first cs-repo open pull request list is a server error names no add_repo, and says retry",
               role_path("archive-inc"), fake_gh_path(ARCHINC_OPENLIST_SETTINGS),
               carries=ARCHIVE_READ_PIN + ARCHIVE_RETRY_PIN, lacks=ARCHIVE_NO_ACT)
# A 403 or 404 on a repo's read names add_repo for that repo, and for that repo only. An unattached repo answers 403.
archive_refuse("a lane whose second cs-repo open pull request list answers 403 names add_repo for q_max, not claude-settings",
               role_path("archive-inc"), fake_gh_path(ARCHINC_OPENLIST403_QMAX),
               carries=(add_repo_pin(ARCH_REPO_QMAX),) + ARCHIVE_READ_PIN, lacks=("add_repo " + ARCH_REPO_SETTINGS,))
# A rate limit answers 403 too, with gh's rate-limit text, and it is no answer about the repo: the refusal names no add_repo.
# The control is the 403 above, the same repo and the same read; only the text differs, so add_repo is what the text decides.
archive_refuse("a lane whose second cs-repo open pull request list answers a rate-limit 403 names no add_repo, and says retry",
               role_path("archive-inc"), fake_gh_path(ARCHINC_OPENLIST_RATELIMIT_QMAX),
               carries=ARCHIVE_READ_PIN + ARCHIVE_RETRY_PIN, lacks=ARCHIVE_NO_ACT)
archive_refuse("a lane whose first cs-repo open pull request list answers 404 names add_repo for claude-settings, not q_max",
               role_path("archive-inc"), fake_gh_path(ARCHINC_OPENLIST404_SETTINGS),
               carries=(add_repo_pin(ARCH_REPO_SETTINGS),) + ARCHIVE_READ_PIN, lacks=("add_repo " + ARCH_REPO_QMAX,))
archive_refuse("a lane whose q_max pull request list for its branch answers 403 names add_repo for q_max, not claude-settings",
               role_path("archive-inc"), fake_gh_path(ARCHINC_PULLS403),
               carries=(add_repo_pin(ARCH_REPO_QMAX),) + ARCHIVE_READ_PIN, lacks=("add_repo " + ARCH_REPO_SETTINGS,))
archive_refuse("a lane whose q_max pull request list for its branch answers 404 names add_repo for q_max, not claude-settings",
               role_path("archive-inc"), fake_gh_path(ARCHINC_PULLS404),
               carries=(add_repo_pin(ARCH_REPO_QMAX),) + ARCHIVE_READ_PIN, lacks=("add_repo " + ARCH_REPO_SETTINGS,))
archive_refuse("a lane whose q_max default-branch read answers 403 names add_repo for q_max, not claude-settings",
               role_path("archive-inc"), fake_gh_path(ARCHINC_REPO403),
               carries=(add_repo_pin(ARCH_REPO_QMAX),) + ARCHIVE_READ_PIN, lacks=("add_repo " + ARCH_REPO_SETTINGS,))
archive_refuse("a lane whose q_max compare of its branch answers 403 names add_repo for q_max, not claude-settings",
               role_path("archive-inc"), fake_gh_path(ARCHINC_COMPARE403),
               carries=(add_repo_pin(ARCH_REPO_QMAX),) + ARCHIVE_READ_PIN, lacks=("add_repo " + ARCH_REPO_SETTINGS,))
# The refusals that are not an unreadable read name no repo to add: an open pull request, no record, no cs-repo tag.
archive_refuse("a lane with an open pull request names no add_repo", role_path("archive-lane"), fake_gh_path(ARCHOPEN),
               carries=ARCHIVE_OPEN_PIN, lacks=("add_repo",))
archive_refuse("a target with no record names no add_repo", role_path("archive-no-target"), fake_gh_path(ARCHCLOSED),
               carries=ARCHIVE_STEER, lacks=("add_repo",))
archive_refuse("a lane with no cs-repo tag names no add_repo: it has no repo to add", role_path("archive-lane-no-repo"),
               fake_gh_path(ARCHOPEN), carries=("no cs-step tag or no cs-repo tag",), lacks=("add_repo",))
# The merge tool does not load. The guard copy has no merge/ beside it, and its config directory has no rules file, so neither
# place the tool is looked for holds it. This is the copy merge_tool_missing_case (s30130) builds. The lane has two cs-repo tags,
# so a refusal that named every tag would show both: the refusal says retry, and names no act and no tag.
ARCHIVE_NOTOOL_GUARD = os.path.join(ROOT, "archive-notool", "hooks", "guard.py")  # the copy the case runs in place of this repo's guard
ARCHIVE_NOTOOL_CFG = os.path.join(ROOT, "archive-notool", "cfg")  # the config directory, with no rules file
ARCHIVE_TAG_PINS = ("cs-repo:", "cs-step:", "cs-build:")  # the prefixes of the lane's tags, which a refusal must not spell out


def build_archive_notool():
    """The guard copy and its empty config directory, built the first time a case names the copy."""
    os.makedirs(os.path.dirname(ARCHIVE_NOTOOL_GUARD), exist_ok=True)
    os.makedirs(ARCHIVE_NOTOOL_CFG, exist_ok=True)
    copy_guard_family(os.path.dirname(ARCHIVE_NOTOOL_GUARD))


lazy_fixture([ARCHIVE_NOTOOL_GUARD], build_archive_notool)
add("lane-closes-after-records: a lane whose merge tool does not load is refused as unreadable, says retry, and names no act or tag",
    "deny", rule=ARCHIVE_RULE, tool=ARCHIVE_TOOL, cwd=NOGIT,
    lacks=ARCHIVE_NAMED + ARCHIVE_NO_ACT + ARCHIVE_TAG_PINS + (ARCH_REPO_SETTINGS, ARCH_REPO_QMAX),
    carries=ARCHIVE_READ_PIN + ARCHIVE_RETRY_PIN, transcript=role_path("archive-inc"), env=ROLE_ENV,
    env_path=fake_gh_path(ARCHOPEN), session_id=ROLE_OTHER, guard=ARCHIVE_NOTOOL_GUARD, config=ARCHIVE_NOTOOL_CFG)
archive_allow("an open draft lane pull request whose head is behind main is allowed: its commits have landed",
              role_path("archive-lane"), fake_gh_path(ARCHDRAFT_BEHIND))
archive_allow("an open draft lane pull request whose head is identical to main is allowed: its commits have landed",
              role_path("archive-lane"), fake_gh_path(ARCHDRAFT_IDENT))
# The same release on the lane/<slug> head form: the draft's head is behind main, so the lane's commits have landed.
archive_allow("an open draft on head lane/<slug> whose head is behind main is allowed: the lane/ head form releases too",
              role_path("archive-lane"), fake_gh_path(ARCHDRAFT_LANE_BEHIND))
archive_refuse("an open draft lane pull request whose head is ahead of main is refused: its commits have not landed",
               role_path("archive-lane"), fake_gh_path(ARCHDRAFT_AHEAD), carries=ARCHIVE_OPEN_PIN, lacks=ARCHIVE_READ_PIN)
archive_refuse("an open draft lane pull request whose head diverged from main is refused",
               role_path("archive-lane"), fake_gh_path(ARCHDRAFT_DIVERGED), carries=ARCHIVE_OPEN_PIN, lacks=ARCHIVE_READ_PIN)
archive_refuse("an open ready lane pull request whose head is behind main is refused: only a draft is released",
               role_path("archive-lane"), fake_gh_path(ARCHREADY_BEHIND), carries=ARCHIVE_OPEN_PIN, lacks=ARCHIVE_READ_PIN)
archive_refuse("an open draft lane pull request whose containment read fails is refused, and the reason says the read failed",
               role_path("archive-lane"), fake_gh_path(ARCHDRAFT_READFAIL), carries=ARCHIVE_READ_PIN + ARCHIVE_RETRY_PIN,
               lacks=ARCHIVE_OPEN_PIN + ARCHIVE_NO_ACT)
# A draft whose base is not the repo's default branch is not released, though its head is behind main. The default
# branch is read from the row (base.repo.default_branch, main); the draft based on main above is the release case.
# This refusal also holds on main, which refuses every open lane pull request. It pins the base check for the release.
archive_refuse("an open draft lane pull request based on integration/b1, not the default branch, is refused though its head is behind main",
               role_path("archive-lane"), fake_gh_path(ARCHDRAFT_INTEG), carries=ARCHIVE_OPEN_PIN, lacks=ARCHIVE_READ_PIN)
# A lane's open pull request on the `lane/<slug>` head form is its own records pull request: refused, as the bare slug is.
archive_refuse("a lane whose open pull request has head lane/<slug> is refused: the lane/ head form counts",
               role_path("archive-lane"), fake_gh_path(ARCHOPEN_LANE), carries=ARCHIVE_OPEN_PIN, lacks=ARCHIVE_READ_PIN)
# The wrapped record in the real shape: the closing tag carries the opening tag's nonce, so the lane's record is read
# inside its wrapper and its open pull request refuses the archive.
archive_refuse("a lane's record in the real wrapper, the nonce on both tags, is read: its open pull request refuses",
               role_path("archive-wrapped-lane"), fake_gh_path(ARCHOPEN), carries=ARCHIVE_OPEN_PIN, lacks=ARCHIVE_READ_PIN)
# Fail closed: a wrapper that does not close with its own nonce, has no closing tag, or has text after the JSON gives
# no record of the target. The lane's open pull request is not judged on a record that was never read.
ARCHIVE_NO_RECORD_PIN = ("holds no get_session record of the target",)
archive_refuse("a closing tag with another nonce than the opening tag's is no record of the target",
               role_path("archive-wrapped-nonce-close"), fake_gh_path(ARCHOPEN), carries=ARCHIVE_NO_RECORD_PIN,
               lacks=ARCHIVE_OPEN_PIN)
archive_refuse("a wrapper with no closing tag is no record of the target",
               role_path("archive-wrapped-unclosed"), fake_gh_path(ARCHOPEN), carries=ARCHIVE_NO_RECORD_PIN,
               lacks=ARCHIVE_OPEN_PIN)
archive_refuse("text after the JSON inside the wrapper is no record of the target",
               role_path("archive-wrapped-trailing-text"), fake_gh_path(ARCHOPEN), carries=ARCHIVE_NO_RECORD_PIN,
               lacks=ARCHIVE_OPEN_PIN)
# Fail closed: a forged closing tag and a triage record inside the JSON title do not win. The real lane record is read.
archive_refuse("a forged closing tag and triage record in the JSON title do not win: the archive is refused",
               role_path("archive-wrapped-forged-title"), fake_gh_path(ARCHOPEN))
# Fail closed: the same forged pair as raw text after the JSON does not make the triage record win.
archive_refuse("a forged closing tag and triage record as raw text after the JSON do not win: the archive is refused",
               role_path("archive-wrapped-forged-text"), fake_gh_path(ARCHOPEN))
# A get_session result with no text body before the lane's record: the reader skips the body and reads the record. A
# reader that raises on the body reads no record, so the archive refuses on no record and never judges the lane.
archive_refuse("a get_session result with no content before the lane's record: the lane's open pull request refuses",
               role_path("body-missing-then-lane"), fake_gh_path(ARCHOPEN), carries=ARCHIVE_OPEN_PIN)
archive_refuse("a get_session result whose content is a dict before the lane's record: the lane's open pull request refuses",
               role_path("body-dict-then-lane"), fake_gh_path(ARCHOPEN), carries=ARCHIVE_OPEN_PIN)
archive_refuse("a get_session result whose content is an int before the lane's record: the lane's open pull request refuses",
               role_path("body-int-then-lane"), fake_gh_path(ARCHOPEN), carries=ARCHIVE_OPEN_PIN)

# The branch read. The record's current_branches names each branch of the lane. A branch that is ahead of its repo's
# default branch, on no pull request in any state, refuses the archive. The refusal names that shape, never a branch.
# Each repo answers for itself: a 404 on a compare means the branch is not in that repo, and any other failed read refuses.
ARCHIVE_NOPR_PIN = ("has no pull request",)
ARCHIVE_NO_BRANCH = (ARCH_BRANCH, ARCH_BRANCH_OTHER, "could not be read")  # a no-pull-request refusal names neither branch
ARCHIVE_READ_LACKS = (ARCHIVE_NOPR_PIN[0], ARCH_BRANCH)  # a read-failure refusal is not the no-pull-request one
archive_refuse("an incident lane: its branch is ahead of main in q_max, on no pull request, and claude-settings has no such branch: refused",
               role_path("archive-inc"), fake_gh_path(ARCHINC_NOPR), carries=ARCHIVE_NOPR_PIN, lacks=ARCHIVE_NO_BRANCH)
archive_refuse("a lane whose branch has no pull request, while another branch of its repo has an open one: refused",
               role_path("archive-inc"), fake_gh_path(ARCHINC_OTHERPR), carries=ARCHIVE_NOPR_PIN, lacks=ARCHIVE_NO_BRANCH)
archive_refuse("a lane with two branches, the first on an open pull request and the second on none: refused for the second",
               role_path("archive-inc-two"), fake_gh_path(ARCHINC_OTHERPR), carries=ARCHIVE_NOPR_PIN, lacks=ARCHIVE_NO_BRANCH)
archive_refuse("a lane whose branch compare in q_max is a server error: refused, and the reason says the branch read failed, not the open list",
               role_path("archive-inc"), fake_gh_path(ARCHINC_COMPARE500), carries=ARCHIVE_READ_PIN + ARCHIVE_RETRY_PIN,
               lacks=ARCHIVE_READ_LACKS + ("open pull requests",) + ARCHIVE_NO_ACT)
archive_refuse("a lane whose branch compare in q_max is a refused connection, not a 404: refused, and the reason says the read failed",
               role_path("archive-inc"), fake_gh_path(ARCHINC_NETWORK), carries=ARCHIVE_READ_PIN + ARCHIVE_RETRY_PIN,
               lacks=ARCHIVE_READ_LACKS + ARCHIVE_NO_ACT)
archive_refuse("a lane whose pull request list for its branch in q_max is a server error: refused, and the reason says the read failed",
               role_path("archive-inc"), fake_gh_path(ARCHINC_PULLS500), carries=ARCHIVE_READ_PIN, lacks=ARCHIVE_READ_LACKS)
archive_refuse("a lane whose pull request list for its branch in q_max is not JSON: refused, and the reason says the read failed",
               role_path("archive-inc"), fake_gh_path(ARCHINC_PULLSJUNK), carries=ARCHIVE_READ_PIN + ARCHIVE_RETRY_PIN,
               lacks=ARCHIVE_READ_LACKS + ARCHIVE_NO_ACT)
archive_refuse("a lane whose q_max default branch cannot be read: refused, and the reason says the read failed",
               role_path("archive-inc"), fake_gh_path(ARCHINC_REPO500), carries=ARCHIVE_READ_PIN, lacks=ARCHIVE_READ_LACKS)
archive_refuse("a lane whose q_max default branch is trunk: its branch is judged against trunk, not main, and refused",
               role_path("archive-inc"), fake_gh_path(ARCHINC_TRUNK), carries=ARCHIVE_NOPR_PIN, lacks=ARCHIVE_NO_BRANCH)
# Allowed: a branch with a pull request in any state, a branch the rule skips, and a record that names no branch.
archive_allow("an incident lane whose branch has a merged pull request is allowed: a squash leaves the branch ahead",
              role_path("archive-inc"), fake_gh_path(ARCHINC_MERGED))
archive_allow("an incident lane whose branch has a closed, unmerged pull request is allowed: it was closed as replaced",
              role_path("archive-inc"), fake_gh_path(ARCHINC_CLOSED))
archive_allow("an incident lane whose branch has an open pull request is allowed",
              role_path("archive-inc"), fake_gh_path(ARCHINC_OPEN))
archive_allow("a branch named archive/... is skipped, though it is ahead with no pull request",
              role_path("archive-inc-archive"), fake_gh_path(ARCHINC_ARCHIVE))
archive_allow("a branch behind main with no pull request is allowed",
              role_path("archive-inc"), fake_gh_path(ARCHINC_BEHIND))
archive_allow("a branch identical to main with no pull request is allowed",
              role_path("archive-inc"), fake_gh_path(ARCHINC_IDENT))
archive_allow("a branch equal to its repo's default branch is skipped, though the compare would read it diverged",
              role_path("archive-inc-default"), fake_gh_path(ARCHINC_DEFAULT))
archive_allow("a branch the compare reads as a 404 in every repo is in none of them: allowed",
              role_path("archive-inc"), fake_gh_path(ARCHINC_404ALL))
archive_allow("a null branch value is no branch: allowed, though a read of the null as a branch would find one ahead",
              role_path("archive-inc-null"), fake_gh_path(ARCHINC_NOPR))
archive_allow("an empty current_branches names no branch: allowed, and reading it does not fail the archive",
              role_path("archive-inc-empty"), fake_gh_path(ARCHINC_NOPR))
archive_allow("a record with no external_metadata is judged as before the branch read: allowed",
              role_path("archive-inc-nometa"), fake_gh_path(ARCHINC_NOPR))
# A repo the record names only through session_context.sources is read too: a branch ahead there, on no pull request, refuses.
archive_refuse("a lane whose branch lives only in a repo its record names through sources, not a cs-repo tag: refused",
               role_path("archive-inc-source-only"), fake_gh_path(ARCHINC_NOPR), carries=ARCHIVE_NOPR_PIN, lacks=ARCHIVE_NO_BRANCH)
# A compare that reads diverged is a branch off main that is not in it: ahead of main for the rule, so no pull request refuses.
archive_refuse("a branch whose compare in q_max is diverged, on no pull request: refused",
               role_path("archive-inc"), fake_gh_path(ARCHINC_DIVERGED), carries=ARCHIVE_NOPR_PIN, lacks=ARCHIVE_NO_BRANCH)
# A source URL ending in .git names the same repo: its branch, ahead there on no pull request, refuses as it does without it.
archive_refuse("a source URL ending in .git names its repo: a branch ahead there on no pull request is refused",
               role_path("archive-inc-source-git"), fake_gh_path(ARCHINC_NOPR), carries=ARCHIVE_NOPR_PIN, lacks=ARCHIVE_NO_BRANCH)
# A repo named only by a source whose own read answers 404 is unreadable, not skipped: the archive refuses, and names add_repo
# for that repo, since a 404 on the repo's read is one of the two answers that name the act.
archive_refuse("a sources-only repo whose own read answers 404 is refused, and names add_repo for that repo",
               role_path("archive-inc-source-only"), fake_gh_path(ARCHINC_REPO404),
               carries=(add_repo_pin(ARCH_REPO_QMAX),) + ARCHIVE_READ_PIN,
               lacks=ARCHIVE_READ_LACKS)
# Shape drift fails closed: a current_branches that is not a map is a shape the read does not know, so it refuses as unreadable.
# A shape error names no act and no repo: no add_repo, and no list of every cs-repo tag. Both repos are tagged here, so an
# all-tags list would show two acts.
archive_refuse("a current_branches that is a list, not a map, is refused, and says retry: no add_repo for either repo",
               role_path("archive-inc-list"), fake_gh_path(ARCHINC_NOPR), carries=ARCHIVE_READ_PIN + ARCHIVE_RETRY_PIN,
               lacks=ARCHIVE_READ_LACKS + ARCHIVE_NO_ACT)
archive_refuse("a current_branches that is a string, not a map, is refused, and says retry: no add_repo for either repo",
               role_path("archive-inc-str"), fake_gh_path(ARCHINC_NOPR), carries=ARCHIVE_READ_PIN + ARCHIVE_RETRY_PIN,
               lacks=ARCHIVE_READ_LACKS + ARCHIVE_NO_ACT)
# One read budget covers the branch reads (MERGE_READ_TIMEOUT, 25s). Each q_max compare sleeps 13s, under the budget alone;
# the second outlasts what the first left, so the archive refuses as unreadable. A budget per call would let both through.
# A timeout is no 403 or 404, so it names no act: the refusal says to retry.
archive_refuse("a lane whose two branch compares outlast one read budget, each under it alone, is refused, and says retry",
               role_path("archive-inc-slow"), fake_gh_path(ARCHINC_SLOW), carries=ARCHIVE_READ_PIN + ARCHIVE_RETRY_PIN,
               lacks=ARCHIVE_READ_LACKS + ARCHIVE_NO_ACT)
# One read budget across the whole archive check, not one per read: the draft's containment read and the branch read sum
# past MERGE_READ_TIMEOUT. The branch read runs out of the shared budget and refuses as unreadable. A budget per read lets
# the branch read run its own 25s, and the lane is refused for its branch instead, with no read failing.
ARCHIVE_BRANCH_READ_LACKS = ARCHIVE_READ_LACKS + ("open pull requests",)  # a branch-read refusal is neither the open-list one nor the no-pull-request one
archive_refuse("a lane whose slug draft containment read and branch read sum past one read budget, each under it alone, is refused, and says retry",
               role_path("archive-inc"), fake_gh_path(ARCHDRAFT_SLOW), carries=ARCHIVE_READ_PIN + ARCHIVE_RETRY_PIN,
               lacks=ARCHIVE_BRANCH_READ_LACKS + ARCHIVE_NO_ACT)
# Shape drift in the record's sources and branch values fails closed, with the branch read's reason. The branch is behind main
# in q_max (or sits in its own tagged repo), so only the drift can refuse the archive.
archive_refuse("a session_context.sources that is a string, not a list, is refused, and says retry: no add_repo",
               role_path("archive-inc-sources-str"), fake_gh_path(ARCHINC_BEHIND), carries=ARCHIVE_READ_PIN + ARCHIVE_RETRY_PIN,
               lacks=ARCHIVE_BRANCH_READ_LACKS + ARCHIVE_NO_ACT)
# A github.com source with a trailing path is read as the repo it names: q_max, whose branch is ahead on no pull request.
archive_refuse("a github.com source with a trailing /tree/main path is read as its owner/repo: the branch ahead there is refused",
               role_path("archive-inc-source-tree"), fake_gh_path(ARCHINC_NOPR), carries=ARCHIVE_NOPR_PIN, lacks=ARCHIVE_NO_BRANCH)
# A github.com source that names no owner and repo is unreadable, not skipped.
archive_refuse("a github.com source that names no owner and repo is refused, and says retry: no add_repo",
               role_path("archive-inc-source-bare"), fake_gh_path(ARCHINC_BEHIND), carries=ARCHIVE_READ_PIN + ARCHIVE_RETRY_PIN,
               lacks=ARCHIVE_BRANCH_READ_LACKS + ARCHIVE_NO_ACT)
# current_branches [] names no branch: allowed, and the branch read makes no call (see the call case below).
archive_allow("a current_branches that is an empty list names no branch: allowed",
              role_path("archive-inc-list-empty"), fake_gh_path(ARCHINC_NOPR))
# A current_branches key that names owner/repo adds that repo to the repos read: its branch, ahead there on no pull request, refuses.
archive_refuse("a current_branches key that names owner/repo reads that repo: its branch ahead there on no pull request is refused",
               role_path("archive-inc-key-repo"), fake_gh_path(ARCHINC_NOPR), carries=ARCHIVE_NOPR_PIN, lacks=ARCHIVE_NO_BRANCH)
# A merged pull request covers its branch only while its head is the branch tip. A commit pushed after the squash, with no new
# pull request, leaves the branch uncovered: refused. The control is the same merged pull request with the tip at its head (ARCHINC_MERGED).
archive_refuse("a lane whose merged pull request head is not the branch tip, and no new pull request, is refused",
               role_path("archive-inc"), fake_gh_path(ARCHINC_MERGEDMOVED), lacks=ARCHIVE_NO_BRANCH)
# A closed, unmerged pull request covers its branch only when the tip is contained in an open or merged pull request's head.
# With no such pull request the branch is uncovered, and the refusal names both ways out.
archive_refuse("a lane whose only pull request is closed unmerged, with no replacement, is refused, and names both ways out",
               role_path("archive-inc"), fake_gh_path(ARCHINC_CLOSEDALONE), carries=("open a pull request", "push an archive copy"),
               lacks=ARCHIVE_NO_BRANCH)
# A left branch: one of the repo's branches under the lane's slug forms (`<slug>` and `lane/<slug>`, and their `-*` variants),
# ahead of main, on no pull request, and not named by current_branches. The lane's own record names no branch here.
archive_refuse("a left branch under the lane's lane/<slug>-r2 form, ahead of main on no pull request, is refused",
               role_path("archive-lane"), fake_gh_path(ARCHLEFT_NOPR), carries=ARCHIVE_NOPR_PIN,
               lacks=("lane/" + ARCHIVE_SLUG + "-r2", "could not be read"))
archive_allow("a left branch under the slug form that has an open pull request is allowed",
              role_path("archive-lane"), fake_gh_path(ARCHLEFT_PR))
archive_allow("a branch named <slug>x, no -* variant of the slug, is not read: allowed though ahead on no pull request",
              role_path("archive-lane"), fake_gh_path(ARCHLEFT_NEAR))
# A closed pull request on lane/<slug> is covered by its merged replacement on lane/<slug>-r2 when the replacing head holds the
# lane branch's tip (the compare of that head with the tip reads behind). The ruling: a closed pull request counts as cover only
# when the branch tip is contained in an open or merged pull request's head. Its control reads ahead, so the tip is not contained.
archive_allow("a lane branch closed unmerged, replaced by a merged pull request on its lane/<slug>-r2 form that holds the tip, is allowed",
              role_path("archive-lane"), fake_gh_path(ARCHLEFT_REPLACED))
archive_refuse("a lane branch closed unmerged, replaced by a merged pull request whose head does not hold the tip, is refused",
               role_path("archive-lane"), fake_gh_path(ARCHLEFT_REPLACED_AHEAD), carries=("open a pull request", "push an archive copy"),
               lacks=("could not be read",))
# A lane branch ahead of main on no pull request is covered by its archive/ copy when the copy holds the tip. The copy is
# listed by the prefix read of archive/<branch>, then compared with the tip. The two cases differ in one value: that compare.
archive_allow("a lane branch ahead on no pull request, whose archive/ copy holds its tip, is allowed",
              role_path("archive-copy-lane"), fake_gh_path(ARCHCOPY_IDENT))
archive_refuse("a lane branch ahead on no pull request, whose archive/ copy is at an older tip, is refused as no pull request",
               role_path("archive-copy-lane"), fake_gh_path(ARCHCOPY_AHEAD), carries=ARCHIVE_NOPR_PIN,
               lacks=(ARCH_COPY_BRANCH, "could not be read"))
# No archive/ copy at all: the listing answers []. The refusal is the plain no-pull-request one, not a failed read.
# A guard that read an empty listing as a failure would refuse as "could not be read" and fail here.
archive_refuse("a lane branch ahead on no pull request, with no archive/ copy, is refused as no pull request",
               role_path("archive-copy-lane"), fake_gh_path(ARCHCOPY_MISSING), carries=ARCHIVE_NOPR_PIN,
               lacks=(ARCH_COPY_BRANCH, "could not be read"))
# The copy under archive/<branch>-2 holds the tip, and the exact copy is diverged: the -2 copy is one the guard counts.
# Red on the old code, which compares only the exact copy.
archive_allow("a lane branch ahead on no pull request, whose archive/<branch>-2 copy holds its tip, is allowed though archive/<branch> is diverged",
              role_path("archive-copy-lane"), fake_gh_path(ARCHCOPY_NUMBERED))
# Neither counted copy holds the tip: the exact copy is diverged and the -2 copy is ahead. Refused as no pull request.
archive_refuse("a lane branch ahead on no pull request, whose counted copies both miss its tip, is refused as no pull request",
               role_path("archive-copy-lane"), fake_gh_path(ARCHCOPY_NUMBERED_NONE), carries=ARCHIVE_NOPR_PIN,
               lacks=(ARCH_COPY_BRANCH, "could not be read"))
# A listed copy under a name that is neither the exact one nor `-<digits>` is not counted, though it holds the tip.
archive_refuse("a lane branch ahead on no pull request, whose only copy is archive/<branch>y holding its tip, is refused as no pull request",
               role_path("archive-copy-lane"), fake_gh_path(ARCHCOPY_LOOKALIKE), carries=ARCHIVE_NOPR_PIN,
               lacks=(ARCH_COPY_BRANCH, "could not be read"))
archive_refuse("a lane branch ahead on no pull request, whose only copy is archive/<branch>-r2 holding its tip, is refused as no pull request",
               role_path("archive-copy-lane"), fake_gh_path(ARCHCOPY_SUFFIX_R2), carries=ARCHIVE_NOPR_PIN,
               lacks=(ARCH_COPY_BRANCH, "could not be read"))
archive_refuse("a current_branches value that is an int is refused, and says retry: no add_repo",
               role_path("archive-inc-branch-int"), fake_gh_path(ARCHINC_NOPR), carries=ARCHIVE_READ_PIN + ARCHIVE_RETRY_PIN,
               lacks=ARCHIVE_BRANCH_READ_LACKS + ARCHIVE_NO_ACT)
archive_refuse("a current_branches value that is a map is refused, and says retry: no add_repo",
               role_path("archive-inc-branch-map"), fake_gh_path(ARCHINC_NOPR), carries=ARCHIVE_READ_PIN + ARCHIVE_RETRY_PIN,
               lacks=ARCHIVE_BRANCH_READ_LACKS + ARCHIVE_NO_ACT)
# Case-insensitive host match, with an optional www.: the source names q_max, and its branch, ahead there, is refused.
archive_refuse("a source URL on www.github.com names its repo: a branch ahead there on no pull request is refused",
               role_path("archive-inc-source-www"), fake_gh_path(ARCHINC_NOPR), carries=ARCHIVE_NOPR_PIN, lacks=ARCHIVE_NO_BRANCH)
archive_refuse("a source URL on GitHub.com in capitals names its repo: a branch ahead there on no pull request is refused",
               role_path("archive-inc-source-upper"), fake_gh_path(ARCHINC_NOPR), carries=ARCHIVE_NOPR_PIN, lacks=ARCHIVE_NO_BRANCH)
# Allowed: a source on another host is skipped, so the lane's branch, behind main in q_max, is judged on its tagged repos.
archive_allow("a source on gitlab.com is skipped: the lane's branch behind main in q_max is allowed",
              role_path("archive-inc-source-gitlab"), fake_gh_path(ARCHINC_BEHIND))


# The agent's own record. An agent (a call with an `agent_id`) made its get_session call in its own transcript, which
# sits beside the main transcript at `<transcript_path minus .jsonl>/subagents/agent-<agent_id>.jsonl`. The guard reads
# that file for the agent's call. A lane is refused when either record says lane. An orchestrator call (no agent_id)
# reads the main record alone. A malformed agent_id reads no file at all.
AGENT_OWN_ID = "ab12cd34ef56a7890"  # an agent id as the harness sends it: 17 hex characters
AGENT_QUIET = [role_use("m0", "Bash"), role_result("m0", "ok")]  # a transcript with no get_session call
# name -> (the main transcript's lines, [(agent_id, the agent file's lines), ...]). An agent id that the guard
# must refuse still gets its file written at the raw path it names, so a reader that skipped the check would read it.
AGENT_FIXTURES = {
    "agent-own-triage": (AGENT_QUIET, [(AGENT_OWN_ID, role_target_call("g1", ARCH_TRIAGE_TAGS))]),
    "agent-own-lane": (AGENT_QUIET, [(AGENT_OWN_ID, role_target_call("g1", ARCH_LANE_TAGS))]),
    "agent-no-record": (AGENT_QUIET, [(AGENT_OWN_ID, AGENT_QUIET)]),
    "agent-quiet-main-triage": (role_target_call("g1", ARCH_TRIAGE_TAGS), [(AGENT_OWN_ID, AGENT_QUIET)]),
    "orchestrator-agent-file": (role_target_call("g1", ARCH_TRIAGE_TAGS),
                                [(AGENT_OWN_ID, role_target_call("g1", ARCH_LANE_TAGS))]),
    "main-triage-agent-lane": (role_target_call("g1", ARCH_TRIAGE_TAGS),
                               [(AGENT_OWN_ID, role_target_call("g1", ARCH_LANE_TAGS))]),
    "main-lane-agent-triage": (role_target_call("g1", ARCH_LANE_TAGS),
                               [(AGENT_OWN_ID, role_target_call("g1", ARCH_TRIAGE_TAGS))]),
    "agent-malformed-id": (AGENT_QUIET, [("x.y", role_target_call("g1", ARCH_TRIAGE_TAGS))]),
    "agent-own-triage-slug": (AGENT_QUIET, [(AGENT_OWN_ID, role_target_call("g1", ARCH_TRIAGE_SLUG_TAGS))]),
    "agent-file-absent": (role_target_call("g1", ARCH_TRIAGE_TAGS), []),
    "agent-dir-at-file": (role_target_call("g1", ARCH_TRIAGE_TAGS), [(AGENT_OWN_ID, None)]),
    "main-lane-agent-second-step": (role_target_call("g1", ARCH_LANE_TAGS),
                                    [(AGENT_OWN_ID, role_target_call("g1", ARCH_AGENT_LANE_TAGS))]),
    # The main transcript holds no record of the target: the lane's record is only in the agent's own file, with a branch.
    "agent-own-branch-lane": (AGENT_QUIET, [(AGENT_OWN_ID, role_target_raw("g1", role_wrapped(arch_record(
        ARCH_INC_TAGS, {"": ARCH_BRANCH}, [ARCH_QMAX_SOURCE]))))]),
}


def agent_transcript(name, agent_id):
    """The agent's own transcript for the main transcript role_path(name): `<main minus .jsonl>/subagents/agent-<id>.jsonl`."""
    return os.path.join(role_path(name)[:-len(".jsonl")], "subagents", "agent-" + agent_id + ".jsonl")


def write_agent_transcripts():
    """Write each main transcript, and each agent file beside it, as the harness lays them out."""
    os.makedirs(ROLE_DIR, exist_ok=True)  # this builder may run before write_role_transcripts makes the folder
    for name, (main, agents) in AGENT_FIXTURES.items():
        with open(role_path(name), "w", encoding="utf-8") as handle:
            handle.write("\n".join(main) + "\n")
        for agent_id, lines in agents:
            path = agent_transcript(name, agent_id)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if lines is None:  # a folder where the agent's file would be: reading it fails, and not as a missing file
                os.makedirs(path, exist_ok=True)
                continue
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("\n".join(lines) + "\n")
        if not agents:  # the scope of the no-file case: nothing at its agent path, so the read finds no file
            assert not os.path.exists(agent_transcript(name, AGENT_OWN_ID)), name


lazy_fixture([role_path(name) for name in AGENT_FIXTURES], write_agent_transcripts)
# An agent whose own record names a non-lane target passes lane-closes-after-records, and agent-no-remote-tools refuses
# it after that (decision session-tiers: no agent archives a session). The refusal names that rule, not a lane reason.
agent_archive_refuse("an agent whose own record is a non-lane target is refused by agent-no-remote-tools",
                     role_path("agent-own-triage"), fake_gh_path(ARCHOPEN), agent_id=AGENT_OWN_ID)
# An agent whose own record is a lane with an open records pull request: refused, for that pull request. The reason pin
# proves the agent's record was read: a guard that missed it would refuse for having no record.
archive_refuse("an agent whose own record is a lane with an open records pull request is refused, for the open pull request",
               role_path("agent-own-lane"), fake_gh_path(ARCHOPEN), agent_id=AGENT_OWN_ID,
               carries=ARCHIVE_OPEN_PIN, lacks=ARCHIVE_NO_RECORD_PIN)
# No record in either transcript: refused for no record, and the open list is not read.
archive_refuse("an agent with no record in its own transcript or the main one is refused, for no record",
               role_path("agent-no-record"), fake_gh_path(ARCHOPEN), agent_id=AGENT_OWN_ID,
               carries=ARCHIVE_NO_RECORD_PIN, lacks=ARCHIVE_OPEN_PIN)
# An orchestrator call (no agent_id) reads the main transcript only: its lane record refuses for the open pull request.
archive_refuse("an orchestrator call with a lane record in the main transcript is refused, for the open pull request",
               role_path("archive-lane"), fake_gh_path(ARCHOPEN), carries=ARCHIVE_OPEN_PIN, lacks=ARCHIVE_NO_RECORD_PIN)
# An agent whose main record is non-lane, and whose own file reads clean but holds no record of the target: lane-closes
# allows it, so the refusal is the agent rule's. A lane reader that refused for no record would fail this case.
agent_archive_refuse("an agent whose main record is non-lane is refused by agent-no-remote-tools, though its own file holds no record",
                     role_path("agent-quiet-main-triage"), fake_gh_path(ARCHOPEN), agent_id=AGENT_OWN_ID)
# The same agent file, on an orchestrator call with no agent_id: the file is not its record, so the main record decides.
archive_allow("an orchestrator call with a non-lane main record is allowed though an agent file beside it holds a lane",
              role_path("orchestrator-agent-file"), fake_gh_path(ARCHOPEN))
# Precedence: a lane in either record refuses. The agent's own record is a lane, the main record is not.
archive_refuse("a lane in the agent's own record is refused though the main record says non-lane",
               role_path("main-triage-agent-lane"), fake_gh_path(ARCHOPEN), agent_id=AGENT_OWN_ID,
               carries=ARCHIVE_OPEN_PIN, lacks=ARCHIVE_NO_RECORD_PIN)
# Precedence the other way: the main record is a lane, the agent's own record is not. It still refuses.
archive_refuse("a lane in the main record is refused though the agent's own record says non-lane",
               role_path("main-lane-agent-triage"), fake_gh_path(ARCHOPEN), agent_id=AGENT_OWN_ID,
               carries=ARCHIVE_OPEN_PIN, lacks=ARCHIVE_NO_RECORD_PIN)
# A malformed agent_id: the file its raw text names holds a non-lane record. It is not read, so the call is refused for no
# record. A reader that skipped the AGENT_ID check would read that record and allow the archive. The id `x.y` has a dot,
# which AGENT_ID refuses, and its file name is legal on Windows, unlike an id with a path separator.
archive_refuse("a malformed agent_id reads no agent file: a non-lane record at its raw path is not read, and the call is refused for no record",
               role_path("agent-malformed-id"), fake_gh_path(ARCHOPEN), agent_id="x.y",
               carries=ARCHIVE_NO_RECORD_PIN, lacks=ARCHIVE_OPEN_PIN)
# No file at the agent's path, and a non-lane main record: no agent record is read, so lane-closes allows it, and
# agent-no-remote-tools refuses it after. A reader that refused on a missing agent file would fail this case for no record.
agent_archive_refuse("an agent with no file at its agent path is refused by agent-no-remote-tools: the main record is non-lane",
                     role_path("agent-file-absent"), fake_gh_path(ARCHOPEN), agent_id=AGENT_OWN_ID)
# A folder at the agent's file path, and a non-lane main record: the read fails with an error other than a missing file, so
# the archive is refused for no record. A reader that caught every read error as a missing file would allow it.
archive_refuse("an agent whose file path is a folder is refused, for no record: a read error is not a missing agent file",
               role_path("agent-dir-at-file"), fake_gh_path(ARCHOPEN), agent_id=AGENT_OWN_ID,
               carries=ARCHIVE_NO_RECORD_PIN, lacks=ARCHIVE_OPEN_PIN)
# Both records are lanes on different steps of the same repo. The open pull request is on the agent record's step only, so
# the archive is refused for it only when the agent record's step is read too. A reader that kept only the main record's
# step would allow it.
archive_refuse("a lane in both records, with the open pull request on the agent record's step only, is refused for that pull request",
               role_path("main-lane-agent-second-step"), fake_gh_path(ARCHOPEN_AGENT), agent_id=AGENT_OWN_ID,
               carries=ARCHIVE_OPEN_PIN, lacks=ARCHIVE_NO_RECORD_PIN + ARCHIVE_READ_PIN)
# The mirror: the open pull request is on the main record's step only. A reader that kept only the agent record's step
# would allow it. Together with the case above, each record's step alone fails, whichever record comes first.
archive_refuse("a lane in both records, with the open pull request on the main record's step only, is refused for that pull request",
               role_path("main-lane-agent-second-step"), fake_gh_path(ARCHOPEN), agent_id=AGENT_OWN_ID,
               carries=ARCHIVE_OPEN_PIN, lacks=ARCHIVE_NO_RECORD_PIN + ARCHIVE_READ_PIN)
# The branch read takes the target's record from the main transcript only. Here the lane's record, with a branch
# ahead of main on no pull request, is in the agent's own transcript alone, so the branch read must find it there too.
archive_refuse("an agent's archive of a lane known only from the agent's transcript is refused for a stranded branch",
               role_path("agent-own-branch-lane"), fake_gh_path(ARCHINC_NOPR), agent_id=AGENT_OWN_ID,
               carries=ARCHIVE_NOPR_PIN, lacks=ARCHIVE_NO_BRANCH + ARCHIVE_NO_RECORD_PIN)


# =========================================================================== 5h. one lane, one topic
