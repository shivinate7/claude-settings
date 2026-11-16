# section 21305
#
# THE PUSHED-COPY PROOF'S READ COUNT AND ITS CLOCK (dirty_paths_are_pushed_copies, hooks/git_reads.py). The proof
# reads every candidate tree while any dirty path stays unmatched. A path whose worktree entry differs from its index
# entry can never match, so a tree with an edit in no commit reads every candidate, each one an `ls-tree` over all of
# the tree's paths. On a large tree that outlasts the PreToolUse hook's timeout, and a timed-out guard lets the call
# through. So the proof must answer False at once when a path can never match, and must answer False once its deadline
# has passed, between candidate reads.
#
# THE CONTRACT THE BUILDER MEETS. `git_reads._now` is a zero-argument callable that returns seconds (time.monotonic by
# default). The proof reads it at entry and before each candidate's `ls-tree`. Past its deadline it answers False. The
# cases install `_now` with mock.patch.object(..., create=True), so on a head without the seam they run and assert,
# and do not crash.
#
# NO CASE WAITS. The fake clock stands at 0 until the first `ls-tree` has run. Then it jumps by PROOF_TRIP_SECONDS, far
# past any budget, so no case encodes a budget's value. The cases read answers and read counts, never seconds.

PD_MANY = 250  # past the 200 paths the removed cap held
PD_EDITS = os.path.join(ROOT, "pd-edits")      # PD_MANY edits, each in no commit, on a pushed branch
PD_STAGED = os.path.join(ROOT, "pd-staged")    # the same paths, staged, so each index blob is in no commit
PROOF_TRIP_SECONDS = 1e9  # far past any deadline a budget gives


def _grow_history(where, branch):
    """Four pushed commits, each on its own file: four more reflog commits the proof can read."""
    for i in range(4):
        name = "history%d.txt" % i
        write(os.path.join(where, name), "history %d\n" % i)
        _base_git(where, "add", name)
        _base_git(where, *IDENT, "commit", "-q", "-m", "history %d on %s" % (i, branch))
    _base_git(where, "push", "-q", "origin", branch)


def _build_proof_trees():
    """Two trees of PD_MANY paths, each a worktree of BCMAIN pushed at its base, then four more pushed commits.
    PD_EDITS edits every path in no commit. PD_STAGED stages the same edits, so each index blob is in no commit."""
    materialize(BCMAIN)
    for where, branch in ((PD_EDITS, "pd-edits"), (PD_STAGED, "pd-staged")):
        _base_copy_tree(where, branch, many=PD_MANY, moved=False)
        _grow_history(where, branch)
    for name in _numbered_paths(PD_MANY):
        write(os.path.join(PD_EDITS, name), "edit %s, in no commit\n" % name)
        write(os.path.join(PD_STAGED, name), "staged %s, in no commit\n" % name)
    _base_git(PD_STAGED, "add", "-A")


lazy_fixture([PD_EDITS, PD_STAGED], _build_proof_trees)


def _proof_scope(tree, status, reflog_min=0):
    """None when TREE holds the status lines named, is pushed whole, and has at least REFLOG_MIN distinct commits in
    HEAD's reflog (0 skips that read). Otherwise the one thing that differs. A case reads its scope before its subject."""
    lines = sorted(_porcelain(tree))
    if lines != sorted(status):
        return "%s holds %d status line(s), want the %d named" % (tree, len(lines), len(status))
    unpushed = run_vcs(tree, "rev-list", "HEAD", "--not", "--remotes").stdout.split()
    if unpushed:
        return "%s has %d commit(s) of HEAD on no remote-tracking ref, want none" % (tree, len(unpushed))
    commits = set(run_vcs(tree, "log", "-g", "--format=%H", "HEAD").stdout.split())
    if len(commits) < reflog_min:
        return "%s has %d distinct reflog commit(s), want at least %d" % (tree, len(commits), reflog_min)
    return None


def _proof_read(tree, trip):
    """(answer, candidate reads) of the proof on TREE, with `git_reads._now` installed at 0. With TRIP, the first
    `ls-tree` the proof makes moves the clock past every deadline, so from the next candidate on the proof must answer
    as it does past its budget. Each git read is counted. Nothing sleeps and no real clock is read."""
    git_reads = _load_git_reads()
    lines = _porcelain(tree)
    now, ls_trees = [0.0], []
    real_git = git_reads._git

    def counting_git(where, *args):
        answer = real_git(where, *args)
        if "ls-tree" in args:
            ls_trees.append(args)
            if trip and len(ls_trees) == 1:
                now[0] = PROOF_TRIP_SECONDS
        return answer

    git_reads._git = counting_git
    try:
        with mock.patch.object(git_reads, "_now", lambda: now[0], create=True):
            got = git_reads.dirty_paths_are_pushed_copies(tree, lines)
    finally:
        git_reads._git = real_git
    return got, len(ls_trees)


def base_copies_edits_no_candidate_case():
    """PD_MANY paths, each an edit in no commit, on a tree with several candidates: the proof answers False at once."""
    materialize(PD_EDITS)
    scope = _proof_scope(PD_EDITS, [" M " + name for name in _numbered_paths(PD_MANY)], reflog_min=3)
    if scope:
        return False, "scope: " + scope
    got, reads = _proof_read(PD_EDITS, trip=False)
    if got is not False:
        return False, "answered %r, want False: a path's content is in no commit" % (got,)
    if reads:
        return False, ("read %d candidate tree(s) for %d paths that can never match, want none: a path whose "
                       "worktree entry differs from its index entry is refused at once" % (reads, PD_MANY))
    return True, "%d paths with an edit in no commit answer False and read no candidate tree" % PD_MANY


def base_copies_staged_past_deadline_case():
    """PD_MANY staged blobs in no commit: False with the clock on time, and past the deadline the proof reads at most
    the first candidate before it answers False."""
    materialize(PD_STAGED)
    scope = _proof_scope(PD_STAGED, ["M  " + name for name in _numbered_paths(PD_MANY)], reflog_min=3)
    if scope:
        return False, "scope: " + scope
    got, _ = _proof_read(PD_STAGED, trip=False)
    if got is not False:
        return False, "answered %r with the clock on time, want False: a staged blob is in no commit" % (got,)
    got, reads = _proof_read(PD_STAGED, trip=True)
    if got is not False:
        return False, "answered %r once past its deadline, want False" % (got,)
    if reads > 2:
        return False, ("read %d candidate tree(s) after the clock passed its deadline, want at most 2: the proof "
                       "runs on past its deadline" % reads)
    return True, "%d staged paths in no commit answer False, and past the deadline read %d candidate tree(s)" % (
        PD_MANY, reads)


def base_copies_deadline_mid_loop_case():
    """The incident tree, whose match is on its second candidate. Past the deadline before that read, the proof answers
    False, not the True it gives on time."""
    materialize(BCINC)
    scope = _proof_scope(BCINC, BC_INCIDENT)
    if scope:
        return False, "scope: " + scope
    got, reads = _proof_read(BCINC, trip=False)
    if got is not True or reads < 2:
        return False, ("scope: with the clock on time the proof answered %r after %d candidate tree(s), want True after "
                       "at least 2: the match is not on a later candidate" % (got, reads))
    got, _ = _proof_read(BCINC, trip=True)
    if got is not False:
        return False, "answered %r once past its deadline before the second candidate, want False" % (got,)
    return True, "the incident tree answers False once the clock passes its deadline before its second candidate"


def base_copies_one_candidate_control_case():
    """Green control: the incident tree, whose paths all match one candidate, answers True with the clock on time."""
    materialize(BCINC)
    scope = _proof_scope(BCINC, BC_INCIDENT)
    if scope:
        return False, "scope: " + scope
    got, _ = _proof_read(BCINC, trip=False)
    if got is not True:
        return False, "answered %r with the clock on time, want True: every path matches one pushed candidate" % (got,)
    return True, "the incident tree, whose paths all match one candidate, answers True with the clock on time"


def base_copies_many_pushed_control_case():
    """Green control: 201 changed paths that are all pushed copies answer True with the clock on time."""
    materialize(BCCAP)
    scope = _proof_scope(BCCAP, ["M  " + name for name in _numbered_paths(201)])
    if scope:
        return False, "scope: " + scope
    got, _ = _proof_read(BCCAP, trip=False)
    if got is not True:
        return False, "answered %r with the clock on time, want True: 201 pushed copies" % (got,)
    return True, "201 changed paths that are all pushed copies answer True with the clock on time"


for _label, _check in (
    ("base copies: 250 paths with an edit in no commit answer False and read no candidate tree",
     base_copies_edits_no_candidate_case),
    ("base copies: 250 staged paths in no commit answer False, and past the deadline read at most two candidate trees",
     base_copies_staged_past_deadline_case),
    ("base copies: the incident tree answers False once the clock passes its deadline before its second candidate",
     base_copies_deadline_mid_loop_case),
    ("base copies: the incident tree, whose paths all match one candidate, answers True with the clock on time",
     base_copies_one_candidate_control_case),
    ("base copies: 201 pushed copies answer True with the clock on time", base_copies_many_pushed_control_case),
):
    LOG_CHECKS_EXTRA.append((_label, _check))
    LOG_FAMILY[_label] = "branch-worktree"
    FIXTURELESS_CHECKS.add(_check)
