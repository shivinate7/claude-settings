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


# A failed fetch. origin's main holds O, and lane adds a three-parent merge that no remote ref holds, so the push is a
# hit. The remote's URL names no repository, so the one fetch fails: the hit survives, and the refusal says the refs
# could not be refreshed. Why: a refusal that rests on stale refs must say that the refresh failed.
OCT_BROKEN = os.path.join(ROOT, "oct-broken")               # as oct-newdest-ctrl, with origin's URL broken
OCT_BROKEN_URL = os.path.join(ROOT, "oct-broken-gone.git")  # names no repository, so `git fetch origin` fails


def _build_octopus_broken():
    _oct_new_branch(OCT_BROKEN, control=True)
    _cmk_run(OCT_BROKEN, "config", "remote.origin.url", OCT_BROKEN_URL)
    _oct_must(OCT_BROKEN, "lane --not --remotes=origin", [3], "the three-parent merge on no remote ref")
    if run_vcs(OCT_BROKEN, "fetch", "--quiet", "origin").returncode == 0:
        sys.exit("fixture setup failed in the octopus-push fixtures: a fetch of origin succeeds with a broken URL")


lazy_fixture([OCT_BROKEN], _build_octopus_broken)
sh("octopus-push: a push whose remote cannot be fetched is refused, and the reason says the refs could not be "
   "refreshed", VCS + " push origin lane", "deny", OCT_RULE, cwd=OCT_BROKEN, carries="could not be refreshed")


# The same broken remote, read for the remedy. The stale-refs sentence is in this refusal, and it must not name the
# forbidden target after `Remedy:`. The case above passes on the same refusal, because it reads only the sentence.
# The scope is read first: the refusal must be the stale-refs variant, so the remedy judged is the one that sentence adds to.
OCT_BROKEN_REMEDY_LABEL = ("octopus-push: a refusal on a failed fetch names the two-parent form in its remedy, and not "
                           "the forbidden target")


def octopus_broken_remedy_case():
    materialize(OCT_BROKEN)
    got, reason = decide({
        "raw": None, "tool": "Bash", "cwd": OCT_BROKEN, "session": None,
        "env_path": None, "tool_input": {"command": VCS + " push origin lane"},
    })
    if got != "deny":
        return False, "expected deny, got %s" % got
    if "could not be refreshed" not in reason:
        return False, "the refusal does not say the refresh failed: %s" % reason[:90]
    fault = octopus_remedy_fault(reason)
    if fault:
        return False, fault
    return True, "refused on a failed fetch, and the remedy names the two-parent form and not the octopus merge"


# The fetch of a hit, pinned at its call. fetch_remote runs one fetch with three flags that keep it to tracking refs.
# A git that refuses those flags (exit 129, a usage error) gets one more fetch without them. The runner is stubbed, so
# no git runs. The flags are written out here, not read from the product: a product constant would not exist on an older head.
FETCH_TRACKING_FLAGS = ("--no-tags", "--no-write-fetch-head", "--no-auto-maintenance")
FETCH_USAGE_EXIT = 129
FETCH_FLAGS_LABEL = ("octopus-push: a fetch of a hit runs once, with --no-tags, --no-write-fetch-head and "
                     "--no-auto-maintenance")
FETCH_RETRY_LABEL = ("octopus-push: a fetch that git refuses with exit 129 runs once more, without those three flags")
FETCH_NO_RETRY_LABEL = "octopus-push: a fetch that fails with any other exit runs once, with no retry"


def _fetch_with_codes(codes):
    """Run git_reads.fetch_remote for origin with its runner stubbed. Call n returns codes[n]; a call past the list
    returns 0. Returns (the fetch's result, the argv of each call). The real runner is put back before it returns."""
    import git_reads
    calls = []
    left = list(codes)

    class _Runner(object):
        @staticmethod
        def run(argv, **kwargs):
            calls.append(list(argv))
            return subprocess.CompletedProcess(argv, left.pop(0) if left else 0, "", "")

    real = git_reads._nowindow
    git_reads._nowindow = _Runner
    try:
        result = git_reads.fetch_remote(ROOT, "origin")
    finally:
        git_reads._nowindow = real
    return result, calls


def octopus_fetch_flags_case():
    result, calls = _fetch_with_codes([0])
    if len(calls) != 1:
        return False, "a fetch that exits 0 ran %d times, want one" % len(calls)
    if calls[0][3:4] != ["fetch"]:
        return False, "the call is not a fetch: %r" % calls[0]
    if result is not True:
        return False, "a fetch that exits 0 is reported as failed"
    for flag in FETCH_TRACKING_FLAGS:
        if flag not in calls[0]:
            return False, "the fetch runs without %s: %r" % (flag, calls[0])
    return True, "one fetch, with --no-tags, --no-write-fetch-head and --no-auto-maintenance"


def octopus_fetch_retry_case():
    result, calls = _fetch_with_codes([FETCH_USAGE_EXIT, 0])
    if len(calls) != 2:
        return False, "a fetch refused with exit 129 ran %d time(s), want two" % len(calls)
    if [call[3:4] for call in calls] != [["fetch"], ["fetch"]]:
        return False, "a call is not a fetch: %r" % calls
    for flag in FETCH_TRACKING_FLAGS:
        if flag in calls[1]:
            return False, "the retry still passes %s: %r" % (flag, calls[1])
    if result is not True:
        return False, "a retry that exits 0 is reported as failed"
    return True, "exit 129 runs one more fetch, without the three flags, and reports its result"


def octopus_fetch_no_retry_case():
    result, calls = _fetch_with_codes([128])
    if len(calls) != 1:
        return False, "a fetch that exits 128 ran %d times, want one" % len(calls)
    if result is not False:
        return False, "a fetch that exits 128 is reported as ok"
    return True, "exit 128 runs one fetch and reports it failed"


# A fetch on a hit, pinned in the push cost table (the helper of section 13406). A push whose range holds an octopus
# runs one `git fetch` of its remote and reads the range again. A clean push runs no fetch. Each row's scope is read
# before its counts are judged. The check builds only the two fixtures it names, through materialize, so it is
# fixtureless, as octopus_remedy_case is.
OCT_FETCH_COST_LABEL = ("octopus-push: a hit fetches its remote once and reads its range again, and a clean push "
                        "runs no fetch")


def octopus_fetch_cost_case():
    if os.name == "nt":
        return SKIP, "skipped: a stand-in git is not reached through CreateProcess"
    log, path = _stand_in_git("octfetch")
    if path is None:
        return False, "no git on PATH"
    materialize(OCT_NEWDEST_CTRL)
    materialize(OCT_NEWDEST)
    _oct_must(OCT_NEWDEST_CTRL, "lane --not --remotes=origin", [3], "the octopus sits in the push range")
    _oct_must(OCT_NEWDEST, "lane --not --remotes=origin", [], "no octopus sits in the push range")
    # The two rows differ by one fetch and one more rev-list, the range read again after the refresh. Every other count
    # is the same on both rows, and the table pins each count, so a new read anywhere in the push shows here.
    problems = _push_cost_problems((
        ("an octopus-push hit", "push origin lane",
         {"config": 1, "diff": 3, "fetch": 1, "log": 1, "rev-list": 2, "rev-parse": 3, "symbolic-ref": 2},
         OCT_NEWDEST_CTRL),
        ("a clean push", "push origin lane",
         {"config": 1, "diff": 3, "log": 1, "rev-list": 1, "rev-parse": 3, "symbolic-ref": 2},
         OCT_NEWDEST),
    ), log, path)
    if problems:
        return False, "; ".join(problems)
    return True, "one fetch on a hit, and none on a clean push"
