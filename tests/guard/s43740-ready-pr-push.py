# section 43740
FAMILY = "ready-pr-push"
#
# `ready-pr-push`. A `git push` whose branch has an open pull request that is ready (not a draft) is refused while that
# pull request's run is running, green or not yet reported. A push cancels the running CI run (checks.yml cancels in
# progress), so the refusal names the way out: wait for the run; or `gh pr ready --undo` to draft, push, and mark ready
# again. A red job is the one state a push may fix, so it is allowed. Ruling: owner, 13:05 CST Nov 23, option a of question
# Q4 (one CI run per PR, never restarted by a push). It narrows the standing merge grant (decision standing-merge-grant).
#
# THE FIXTURE. The records-page-ready repo (section 16449): RPR_REPO on main, RPR_NOSEL on feat-stale, and the seed's
# heads. Each case's verdict comes from this rule alone, so the fake gh answers name the pull request and its run. The
# fakes are make_fake_gh stand-ins (section 442): one pull request per fake, its head, its draft flag and its run. RPP_WT is
# a linked worktree of RPR_REPO on feat-current, for the push-from-a-worktree form.
#
# UNREADABLE READ. A read that cannot run is refused, unknown. Main's ready-state rules refuse the same way (records-page-ready
# and merge-checks, guard-hooks-fail-closed), so this rule does too: it must not pass a push that might cancel a run.
# The rule reads GitHub only for a `git push` command, and at most once per push (the cost pin below).
#
# THE MERGE TOOL. The guard recognises the merge tool as caller by its command word (guard_merge.merge_tool_args: the shim
# or python on merge/merge.py). The tool's own pushes run as subprocesses no hook sees, so the one call the rule meets is the
# shim call itself, which pushes nothing the hook reads. A `git push` written beside a merge-tool word is still a push.

PPUSH_RULE = "ready-pr-push"
RPP =os.path.join(RPR, "ready-push")                          # the fake answers and their call log, under the records-page-ready repo
GHPUSH_GREEN = os.path.join(RPP, "gh-green")                   # feat-stale: a ready pull request, checks passed, run succeeded
GHPUSH_CURRENT = os.path.join(RPP, "gh-current-green")          # feat-current: the same, for the linked worktree
GHPUSH_RUNNING = os.path.join(RPP, "gh-running")               # feat-stale: ready, a check pending, the run in progress
GHPUSH_EMPTY = os.path.join(RPP, "gh-empty")                   # feat-stale: ready, no check and no run reported yet
GHPUSH_RED = os.path.join(RPP, "gh-red")                       # feat-stale: ready, one job failed, the run failed
GHPUSH_DRAFT = os.path.join(RPP, "gh-draft")                   # feat-stale: a draft pull request, checks passed
GHPUSH_OTHER = os.path.join(RPP, "gh-other-branch")            # the only pull request is for feat-other: none for feat-stale
GHPUSH_BROKEN = os.path.join(RPP, "gh-broken")                 # feat-stale: ready, but every call answers text that is not JSON
RPP_COUNT = os.path.join(RPP, "gh-calls.log")                  # the call log of GHPUSH_GREEN: one line per gh call
RPP_WT = os.path.join(RPR, "wt-current")                       # a linked worktree of RPR_REPO on feat-current

PPUSH_LAST = "If this refusal looks wrong for your task, comply anyway and say so in your report."
PPUSH_CARRIES = (("cancel",), ("wait",), "gh pr ready --undo", ("red job",))   # why, the way out, the red-job exception
PPUSH_UNKNOWN = ("could not be read", "could not run", "unknown")
PPUSH_LACKS = ("git switch", "cherry-pick", "replacement PR", "--force")      # the acts a refusal must never name


def _build_ready_push():
    materialize(RPR)  # the records-page-ready repo: its heads and its clones are the ones the cases name
    os.makedirs(RPP, exist_ok=True)
    stale = _rpr_git(RPR_SEED, "rev-parse", "--verify", "feat-stale")
    current = _rpr_git(RPR_SEED, "rev-parse", "--verify", "feat-current")
    if stale == current:  # scope before subject: the two branches must hold different heads, or a case cannot tell them apart
        sys.exit("fixture setup failed in the ready-pr-push fixtures: feat-stale and feat-current hold one head")
    make_fake_gh(GHPUSH_GREEN, "main", head_sha=stale, head_ref="feat-stale", draft=False, count_file=RPP_COUNT)
    make_fake_gh(GHPUSH_CURRENT, "main", head_sha=current, head_ref="feat-current", draft=False)
    make_fake_gh(GHPUSH_RUNNING, "main", head_sha=stale, head_ref="feat-stale", draft=False,
                 checks=[{"name": "checks", "bucket": "pending", "link": ""}],
                 runs=[{"status": "in_progress", "conclusion": None, "name": "checks"}])
    make_fake_gh(GHPUSH_EMPTY, "main", head_sha=stale, head_ref="feat-stale", draft=False, checks=[], runs=[])
    make_fake_gh(GHPUSH_RED, "main", head_sha=stale, head_ref="feat-stale", draft=False,
                 checks=[{"name": "checks", "bucket": "fail", "link": ""}],
                 runs=[{"status": "completed", "conclusion": "failure", "name": "checks"}])
    make_fake_gh(GHPUSH_DRAFT, "main", head_sha=stale, head_ref="feat-stale", draft=True)
    make_fake_gh(GHPUSH_OTHER, "main", head_sha=current, head_ref="feat-other", draft=False)
    make_fake_gh(GHPUSH_BROKEN, "main", head_sha=stale, head_ref="feat-stale", draft=False, broken=True)
    if not os.path.isdir(RPP_WT):
        _rpr_git(RPR_REPO, "worktree", "add", "-q", "-b", "feat-current", RPP_WT, "origin/feat-current")


lazy_fixture([RPP_WT, GHPUSH_GREEN, GHPUSH_CURRENT, GHPUSH_RUNNING, GHPUSH_EMPTY, GHPUSH_RED, GHPUSH_DRAFT,
              GHPUSH_OTHER, GHPUSH_BROKEN], _build_ready_push)


def ppush_refuse(name, command, cwd, fake, carries=PPUSH_CARRIES, lacks=PPUSH_LACKS, env_path=None):
    """A push the rule refuses. The reason names the rule, the why and the way out, and never the acts in `lacks`."""
    sh("ready-pr-push: " + name, command, "deny", PPUSH_RULE, cwd=cwd,
       env_path=env_path if env_path is not None else _rpr_env(fake), carries=carries, lacks=lacks)


def ppush_allow(name, command, cwd, fake, config=None, env_path=None):
    """A call the rule allows. Each allow is a control: it passes on the old code too, and holds the refusal above it honest."""
    sh("ready-pr-push: " + name, command, "allow", cwd=cwd,
       env_path=env_path if env_path is not None else _rpr_env(fake), config=config)


# REFUSED. The branch of a ready pull request, named every way a session writes the push. Each is red on the old code.
ppush_refuse("a bare git push from a checkout of the ready branch feat-stale, run green", VCS + " push", RPR_NOSEL, GHPUSH_GREEN)
ppush_refuse("git push origin feat-stale, the ready branch, run green", VCS + " push origin feat-stale", RPR_NOSEL, GHPUSH_GREEN)
ppush_refuse("git push -u origin feat-stale, the ready branch, run green", VCS + " push -u origin feat-stale", RPR_NOSEL,
             GHPUSH_GREEN)
ppush_refuse("git push origin HEAD from the ready branch, run green", VCS + " push origin HEAD", RPR_NOSEL, GHPUSH_GREEN)
ppush_refuse("git push origin HEAD:feat-stale from the ready branch, run green", VCS + " push origin HEAD:feat-stale", RPR_NOSEL,
             GHPUSH_GREEN)
ppush_refuse("git push origin feat-stale from a checkout on main, run green", VCS + " push origin feat-stale", RPR_REPO, GHPUSH_GREEN)
ppush_refuse("a bare git push from a linked worktree on the ready branch feat-current, run green", VCS + " push", RPP_WT,
             GHPUSH_CURRENT)
ppush_refuse("a bare git push on the ready branch, the run running", VCS + " push", RPR_NOSEL, GHPUSH_RUNNING)
ppush_refuse("a bare git push on the ready branch, no check or run reported yet", VCS + " push", RPR_NOSEL, GHPUSH_EMPTY)
ppush_refuse("a commit, then git push, on the ready branch, run green", VCS + ' commit --allow-empty -m s && ' + VCS + " push",
             RPR_NOSEL, GHPUSH_GREEN)
ppush_refuse("a push after a quoted comment opener on the ready branch, run green", 'echo "# note" && ' + VCS + " push",
             RPR_NOSEL, GHPUSH_GREEN)
ppush_refuse("a merge-tool word in another segment does not make git push on the ready branch the tool's",
             "echo merge 12 && " + VCS + " push origin feat-stale", RPR_NOSEL, GHPUSH_GREEN)

# UNKNOWN. The pull request read cannot run: gh answers text that is not JSON, or gh is missing. Refused, named unknown.
ppush_refuse("a bare git push when the pull request read answers text that is not JSON", VCS + " push", RPR_NOSEL, GHPUSH_BROKEN,
             carries=PPUSH_UNKNOWN)
sh("ready-pr-push: a bare git push when gh is missing from PATH is refused unknown", VCS + " push", "deny", PPUSH_RULE,
   cwd=RPR_NOSEL, env_path=GHNONE_PATH, carries=PPUSH_UNKNOWN, lacks=PPUSH_LACKS)

# ALLOWED. The states and forms the rule must not touch. Each passes on the old code: they are the controls.
ppush_allow("a bare git push on a branch whose pull request is a draft", VCS + " push", RPR_NOSEL, GHPUSH_DRAFT)
ppush_allow("a bare git push on a branch with no pull request (the one pull request is for feat-other)", VCS + " push",
            RPR_NOSEL, GHPUSH_OTHER)
ppush_allow("a bare git push on a ready branch whose run has a red job", VCS + " push", RPR_NOSEL, GHPUSH_RED)
ppush_allow("git push origin feat-other from the ready branch's checkout, feat-other has no pull request",
            VCS + " push origin feat-other", RPR_NOSEL, GHPUSH_GREEN)
ppush_allow("git push origin HEAD:archive/feat-stale from the ready branch, an archive name",
            VCS + " push origin HEAD:archive/feat-stale", RPR_NOSEL, GHPUSH_GREEN)
ppush_allow("the merge tool's own call on the ready pull request, merge 12 --ready",
            MERGE_SHIM + " 12 --ready", RPR_REPO, GHPUSH_GREEN, config=MERGECFG)
ppush_allow("git push written inside a quoted string is no push", 'echo "' + VCS + ' push origin feat-stale"', RPR_NOSEL,
            GHPUSH_GREEN)
ppush_allow("git push written inside a heredoc body is no push",
            "cat <<'EOF'\n" + VCS + " push origin feat-stale\nEOF", RPR_NOSEL, GHPUSH_GREEN)
ppush_allow("a commit with no push on the ready branch", VCS + " commit --allow-empty -m s", RPR_NOSEL, GHPUSH_GREEN)


# THE REFUSAL TEXT. The last sentence is the comply-anyway line, every refusal of this rule ends with it.
def ppush_ends_case():
    """A refused push's reason ends with the comply-anyway sentence. Why: that sentence is the one line an agent whose task the
    refusal misjudges must read before it complies and says so in its report."""
    materialize(GHPUSH_GREEN)
    got, reason = decide(_rr_case(VCS + " push", RPR_NOSEL, _rpr_env(GHPUSH_GREEN)))
    if got != "deny" or PPUSH_RULE not in reason:
        return False, "a bare push on the ready branch is %s, want deny under %s: %s" % (got, PPUSH_RULE, reason[:100])
    if not reason.rstrip().endswith(PPUSH_LAST):
        return False, "the refusal does not end with the comply-anyway sentence: %s" % reason[-120:]
    return True, "the refusal ends with the comply-anyway sentence"


PPUSH_ENDS_LABEL = ("ready-pr-push: a refused push's reason ends with the comply-anyway sentence, after the why and the "
                    "way out")
LOG_FAMILY[PPUSH_ENDS_LABEL] = FAMILY


# THE COST PIN. The rule reads GitHub only for a git push, once per push. Another call reads it not at all.
def _ppush_reads(command, cwd, fake):
    """(the number of gh calls the guard made for this call, its verdict). The call log is the fake's own, reset first."""
    materialize(fake)
    if os.path.exists(RPP_COUNT):
        os.remove(RPP_COUNT)
    got, _reason = decide(_rr_case(command, cwd, _rpr_env(fake)))
    calls = 0
    if os.path.exists(RPP_COUNT):
        with open(RPP_COUNT, encoding="utf-8") as log:
            calls = len([line for line in log if line.strip()])
    return calls, got


def ppush_cost_case():
    """A push to the ready branch reads GitHub exactly once. Why: the refusal needs one read of the pull request, and a second
    read would add a GitHub call to every push, the cost the decision holds the guard to."""
    calls, got = _ppush_reads(VCS + " push origin feat-stale", RPR_NOSEL, GHPUSH_GREEN)
    if got != "deny":
        return False, "a push to the ready branch is %s, want deny before its read is counted" % got
    if calls != 1:
        return False, "a push to the ready branch makes %d gh call(s), want exactly 1" % calls
    return True, "a push to the ready branch makes exactly one gh call"


def ppush_no_read_case():
    """A commit and a status on the ready branch make no gh call. Why: only a git push reads GitHub, so every other Bash call
    stays free of the read."""
    for command in (VCS + " commit --allow-empty -m s", VCS + " status"):
        calls, got = _ppush_reads(command, RPR_NOSEL, GHPUSH_GREEN)
        if calls != 0:
            return False, "`%s` on the ready branch makes %d gh call(s), want none" % (command, calls)
    return True, "a commit and a status on the ready branch make no gh call"


PPUSH_PUSH_READS_LABEL = "ready-pr-push: a push to a ready branch reads GitHub exactly once"
PPUSH_NO_READ_LABEL = "ready-pr-push: a commit or a status on a ready branch reads GitHub not at all"
LOG_FAMILY[PPUSH_PUSH_READS_LABEL] = FAMILY
LOG_FAMILY[PPUSH_NO_READ_LABEL] = FAMILY
LOG_CHECKS = LOG_CHECKS + ((PPUSH_ENDS_LABEL, ppush_ends_case), (PPUSH_PUSH_READS_LABEL, ppush_cost_case),
                           (PPUSH_NO_READ_LABEL, ppush_no_read_case))
