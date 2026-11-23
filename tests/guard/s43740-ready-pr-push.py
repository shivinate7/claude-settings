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
# FAILED READ. A failed pull-request list read is allowed, with one stderr line that names the read that failed. Owner
# ruling handed-in-push-fourth-way, 21:17 CST Nov 18, point 2: a refusal on a failed read would block every push when GitHub
# cannot be reached. The rule reads GitHub only for a `git push` command, and at most twice per push (the cost pins below).
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
RPP_COUNT = os.path.join(RPP, "gh-calls.log")                  # the call log of the cost pins: one line per gh call of a fake that names it
RPP_WT = os.path.join(RPR, "wt-current")                       # a linked worktree of RPR_REPO on feat-current

PPUSH_LAST = "If this refusal looks wrong for your task, comply anyway and say so in your report."
PPUSH_CARRIES = (("cancel",), ("wait",), "gh pr ready --undo", ("red job",))   # why, the way out, the red-job exception
PPUSH_READ_NAMES = ("pull request", "pr list")                                 # the stderr line names the failed read by one of these
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
                 runs=[{"status": "in_progress", "conclusion": None, "name": "checks"}], count_file=RPP_COUNT)
    make_fake_gh(GHPUSH_EMPTY, "main", head_sha=stale, head_ref="feat-stale", draft=False, checks=[], runs=[])
    make_fake_gh(GHPUSH_RED, "main", head_sha=stale, head_ref="feat-stale", draft=False,
                 checks=[{"name": "checks", "bucket": "fail", "link": ""}],
                 runs=[{"status": "completed", "conclusion": "failure", "name": "checks"}], count_file=RPP_COUNT)
    make_fake_gh(GHPUSH_DRAFT, "main", head_sha=stale, head_ref="feat-stale", draft=True, count_file=RPP_COUNT)
    make_fake_gh(GHPUSH_OTHER, "main", head_sha=current, head_ref="feat-other", draft=False, count_file=RPP_COUNT)
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

# FAILED READ. The pull request read cannot run: gh answers text that is not JSON, or gh is missing. Allowed, and one stderr
# line names the failed read (the stderr checks below). Each allow passes on the old code too: it is the control.
ppush_allow("a bare git push when the pull request read answers text that is not JSON", VCS + " push", RPR_NOSEL, GHPUSH_BROKEN)
sh("ready-pr-push: a bare git push when gh is missing from PATH is allowed", VCS + " push", "allow", cwd=RPR_NOSEL,
   env_path=GHNONE_PATH)

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


# THE COST PINS. The rule reads GitHub only for a git push, and by what the branch holds: one read of the open pull request
# list when no ready pull request holds the pushed branch, and a second read, of the head's check runs, when one does. Another
# call reads it not at all.
def _ppush_reads(command, cwd, fake):
    """(the number of gh calls the guard made for this call, its verdict). The call log is RPP_COUNT, reset first."""
    materialize(fake)
    if os.path.exists(RPP_COUNT):
        os.remove(RPP_COUNT)
    got, _reason = decide(_rr_case(command, cwd, _rpr_env(fake)))
    calls = 0
    if os.path.exists(RPP_COUNT):
        with open(RPP_COUNT, encoding="utf-8") as log:
            calls = len([line for line in log if line.strip()])
    return calls, got


def ppush_one_read_case():
    """A push to a branch no ready pull request holds reads GitHub exactly once, the pull request list. Why: the list is the
    one read that tells a draft or no pull request from a ready one, so a push that needs no check read must not pay for one."""
    for fake, state in ((GHPUSH_DRAFT, "a draft pull request"), (GHPUSH_OTHER, "no pull request for it")):
        calls, got = _ppush_reads(VCS + " push origin feat-stale", RPR_NOSEL, fake)
        if got != "allow":
            return False, "a push to feat-stale with %s is %s, want allow before its read is counted" % (state, got)
        if calls != 1:
            return False, "a push to feat-stale with %s makes %d gh call(s), want exactly 1" % (state, calls)
    return True, "a push to a branch no ready pull request holds makes exactly one gh call"


def ppush_two_reads_case():
    """A push to a ready branch reads GitHub exactly twice: the pull request list, then the head's check runs. Why: a ready
    pull request's red or green lives only in its check runs, so the second read is the one the verdict needs, and a third
    would be a GitHub call the decision does not allow a push."""
    for fake, state, want in ((GHPUSH_GREEN, "run green", "deny"), (GHPUSH_RUNNING, "run running", "deny"),
                              (GHPUSH_RED, "run with a red job", "allow")):
        calls, got = _ppush_reads(VCS + " push origin feat-stale", RPR_NOSEL, fake)
        if got != want:
            return False, "a push to the ready branch feat-stale, %s, is %s, want %s before its read is counted" % (state, got, want)
        if calls != 2:
            return False, "a push to the ready branch feat-stale, %s, makes %d gh call(s), want exactly 2" % (state, calls)
    return True, "a push to a ready branch makes exactly two gh calls, whatever its run's state"


def ppush_no_read_case():
    """A commit and a status on the ready branch make no gh call. Why: only a git push reads GitHub, so every other Bash call
    stays free of the read."""
    for command in (VCS + " commit --allow-empty -m s", VCS + " status"):
        calls, got = _ppush_reads(command, RPR_NOSEL, GHPUSH_GREEN)
        if calls != 0:
            return False, "`%s` on the ready branch makes %d gh call(s), want none" % (command, calls)
    return True, "a commit and a status on the ready branch make no gh call"


# THE FAILED READ'S LINE. A failed read is allowed, with one warning line on stderr that names the read. decide drops a
# run's stderr, so the check runs the guard through section 43501's wrapper (TGT_WRAP): it runs the guard named by TGT_GUARD,
# and writes that run's stderr to TGT_STDERR.
def _ppush_stderr_run(command, cwd, fake, stderr_file, env_path=None):
    """(the decision, its reason, the non-empty stderr lines) of one push judged through the stderr wrapper."""
    materialize(fake)
    if os.path.exists(stderr_file):
        os.remove(stderr_file)
    case = _rr_case(command, cwd, env_path if env_path is not None else _rpr_env(fake))
    case["guard"] = TGT_WRAP
    case["env"] = {"TGT_GUARD": GUARD, "TGT_STDERR": stderr_file}
    got, reason = decide(case)
    lines = []
    if os.path.exists(stderr_file):
        with open(stderr_file, encoding="utf-8") as handle:
            lines = [line for line in handle.read().splitlines() if line.strip()]
    return got, reason, lines


def _ppush_warning(name, command, cwd, fake, stderr_name, env_path=None):
    """The failed read is allowed, and its stderr holds exactly one line that names the read."""
    stderr_file = os.path.join(RPP, stderr_name)
    got, reason, lines = _ppush_stderr_run(command, cwd, fake, stderr_file, env_path)
    if got != "allow":
        return False, "%s: expected allow, got %s (%s)" % (name, got, reason[:70])
    if len(lines) != 1:
        return False, "%s: expected one stderr line, found %d" % (name, len(lines))
    if not any(word in lines[0].lower() for word in PPUSH_READ_NAMES):
        return False, "%s: the stderr line names no read: %r" % (name, lines[0][:120])
    return True, "%s: allowed, and one stderr line names the read" % name


def ppush_warn_json_case():
    """The pull request read answers text, not JSON: the push is allowed, and one stderr line names the read."""
    return _ppush_warning("a bare git push when the pull request read answers text that is not JSON", VCS + " push",
                          RPR_NOSEL, GHPUSH_BROKEN, "read-broken.stderr")


def ppush_warn_missing_case():
    """gh is missing from PATH: the push is allowed, and one stderr line names the read. The fake is not on this PATH."""
    return _ppush_warning("a bare git push when gh is missing from PATH", VCS + " push", RPR_NOSEL, GHPUSH_BROKEN,
                          "read-missing.stderr", env_path=GHNONE_PATH)


PPUSH_ONE_READ_LABEL = ("ready-pr-push: a push to a branch no ready pull request holds reads GitHub exactly once, the pull "
                        "request list")
PPUSH_TWO_READS_LABEL = ("ready-pr-push: a push to a ready branch reads GitHub exactly twice, the pull request list then the "
                         "check runs")
PPUSH_NO_READ_LABEL = "ready-pr-push: a commit or a status on a ready branch reads GitHub not at all"
PPUSH_WARN_JSON_LABEL = ("ready-pr-push: a failed pull-request read that answers text, not JSON, is allowed, with one stderr "
                         "line naming the read")
PPUSH_WARN_MISSING_LABEL = ("ready-pr-push: a failed pull-request read with gh missing from PATH is allowed, with one stderr "
                            "line naming the read")
LOG_FAMILY[PPUSH_ONE_READ_LABEL] = FAMILY
LOG_FAMILY[PPUSH_TWO_READS_LABEL] = FAMILY
LOG_FAMILY[PPUSH_NO_READ_LABEL] = FAMILY
LOG_FAMILY[PPUSH_WARN_JSON_LABEL] = FAMILY
LOG_FAMILY[PPUSH_WARN_MISSING_LABEL] = FAMILY
LOG_CHECKS = LOG_CHECKS + ((PPUSH_ENDS_LABEL, ppush_ends_case), (PPUSH_ONE_READ_LABEL, ppush_one_read_case),
                           (PPUSH_TWO_READS_LABEL, ppush_two_reads_case), (PPUSH_NO_READ_LABEL, ppush_no_read_case),
                           (PPUSH_WARN_JSON_LABEL, ppush_warn_json_case), (PPUSH_WARN_MISSING_LABEL, ppush_warn_missing_case))
