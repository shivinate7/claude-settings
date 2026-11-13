# section 17973
FAMILY = "octopus-push"
OCT_RULE = "octopus-push"
OCT_TARGET_WORD = "octopus"                       # the forbidden target, as a remedy would name it
OCT_THREE = os.path.join(ROOT, "oct-three")       # topic: a commit, a merge of x and y (three parents), a commit
OCT_FOUR = os.path.join(ROOT, "oct-four")         # topic: a commit, a merge of x, y and z (four parents)
OCT_TWO = os.path.join(ROOT, "oct-two")           # topic: a commit, then a merge of x and a merge of y (two parents each)
OCT_PLAIN = os.path.join(ROOT, "oct-plain")       # topic: two commits, no merge
OCT_REMOTE = os.path.join(ROOT, "oct-remote")     # topic: a three-parent merge already pushed, then a clean commit
OCT_EMPTY = os.path.join(ROOT, "oct-empty")       # topic: a three-parent merge already pushed, nothing unpushed
OCT_MAIN = os.path.join(ROOT, "oct-main")         # main: a commit, then an unpushed three-parent merge


def _oct_branch(where, name, rel, text):
    """Cut `name` from main and commit one file on it. The caller picks the branch to merge into."""
    _cmk_run(where, "checkout", "-q", "-b", name, "main")
    _cmk_commit(where, rel, text, "change on " + name)


def _oct_merge(where, into, names):
    """Merge `names` into branch `into` as one merge commit. --no-ff keeps a fast-forward from hiding it."""
    _cmk_run(where, "checkout", "-q", into)
    _cmk_run(where, "merge", "-q", "--no-ff", "--no-edit", *names)


def _oct_parents(where, rng):
    """The parent count of each merge in `rng`, sorted, as git reads them. `rng` may hold several words, such
    as `HEAD --not --remotes=origin`, which names the commits a push would send to the remote."""
    out = _cmk_run(where, "rev-list", "--merges", "--parents", *rng.split())
    return sorted(len(line.split()) - 1 for line in out.splitlines())


def _oct_must(where, rng, want, what):
    """Stop the suite unless the merges in `rng` have the parent counts `want`. Each fixture's scope is read
    this way before a case judges it, so a fixture that built nothing fails here, not as a wrong case."""
    got = _oct_parents(where, rng)
    if got != want:
        sys.exit("fixture setup failed in the octopus-push fixtures: %s: merges in %r have parents %r, want %r"
                 % (what, rng, got, want))


def _oct_remote(where):
    """Topic with a three-parent merge pushed to its remote, and no commit after it."""
    _cmk_pushed(where, {"a.txt": "base\n"})
    _cmk_commit(where, "t1.txt", "t1\n", "topic one")
    _oct_branch(where, "x", "x.txt", "x\n")
    _oct_branch(where, "y", "y.txt", "y\n")
    _oct_merge(where, "topic", ["x", "y"])
    _cmk_run(where, "push", "-q", "origin", "topic")
    _oct_must(where, "origin/topic", [3], "the merge on the remote")


def _build_octopus_push():
    _cmk_pushed(OCT_THREE, {"a.txt": "base\n"})
    _cmk_commit(OCT_THREE, "t1.txt", "t1\n", "topic one")
    _oct_branch(OCT_THREE, "x", "x.txt", "x\n")
    _oct_branch(OCT_THREE, "y", "y.txt", "y\n")
    _oct_merge(OCT_THREE, "topic", ["x", "y"])
    _cmk_commit(OCT_THREE, "t2.txt", "t2\n", "topic two, after the merge")
    _oct_must(OCT_THREE, "origin/topic..HEAD", [3], "the unpushed three-parent merge")

    _cmk_pushed(OCT_FOUR, {"a.txt": "base\n"})
    _cmk_commit(OCT_FOUR, "t1.txt", "t1\n", "topic one")
    for name in ("x", "y", "z"):
        _oct_branch(OCT_FOUR, name, name + ".txt", name + "\n")
    _oct_merge(OCT_FOUR, "topic", ["x", "y", "z"])
    _oct_must(OCT_FOUR, "origin/topic..HEAD", [4], "the unpushed four-parent merge")

    _cmk_pushed(OCT_TWO, {"a.txt": "base\n"})
    _cmk_commit(OCT_TWO, "t1.txt", "t1\n", "topic one")
    _oct_branch(OCT_TWO, "x", "x.txt", "x\n")
    _oct_merge(OCT_TWO, "topic", ["x"])
    _oct_branch(OCT_TWO, "y", "y.txt", "y\n")
    _oct_merge(OCT_TWO, "topic", ["y"])
    _oct_must(OCT_TWO, "origin/topic..HEAD", [2, 2], "two unpushed two-parent merges")

    _cmk_pushed(OCT_PLAIN, {"a.txt": "base\n"})
    _cmk_commit(OCT_PLAIN, "t1.txt", "t1\n", "topic one")
    _cmk_commit(OCT_PLAIN, "t2.txt", "t2\n", "topic two")
    _oct_must(OCT_PLAIN, "origin/topic..HEAD", [], "no merge, unpushed")

    _oct_remote(OCT_REMOTE)
    _cmk_commit(OCT_REMOTE, "b.txt", "clean\n", "clean change, unpushed")
    _oct_must(OCT_REMOTE, "origin/topic..HEAD", [], "only the clean commit, unpushed")

    _oct_remote(OCT_EMPTY)
    _oct_must(OCT_EMPTY, "origin/topic..HEAD", [], "nothing unpushed")

    _cmk_pushed(OCT_MAIN, {"a.txt": "base\n"})
    _oct_branch(OCT_MAIN, "x", "x.txt", "x\n")
    _oct_branch(OCT_MAIN, "y", "y.txt", "y\n")
    _cmk_run(OCT_MAIN, "checkout", "-q", "main")
    _cmk_commit(OCT_MAIN, "m.txt", "m\n", "main one, unpushed")
    _oct_merge(OCT_MAIN, "main", ["x", "y"])
    _oct_must(OCT_MAIN, "origin/main..HEAD", [3], "the unpushed three-parent merge on main")
    # push-main reads the remote's URL, and a local bare path is no network remote, so the ask would go silent.
    # Give origin the network URL that the push-main fixtures use (PUSHREMOTE). The guard never contacts it, and
    # the tracking refs above stay as they are.
    _cmk_run(OCT_MAIN, "config", "remote.origin.url", PUSHREMOTE)


lazy_fixture([OCT_THREE, OCT_FOUR, OCT_TWO, OCT_PLAIN, OCT_REMOTE, OCT_EMPTY, OCT_MAIN], _build_octopus_push)

# The false-alarm fixtures. origin/main gains a three-parent merge O, and local main stays at the base, so O is
# on the remote only. A push of a topic that merges origin/main sends no new octopus, and neither does a push of
# a new branch cut from origin/main.
OCT_ALARM = os.path.join(ROOT, "oct-alarm")          # topic, at the base and pushed, merges origin/main
OCT_ALARM_NEW = os.path.join(ROOT, "oct-alarm-new")  # as oct-alarm, plus a new three-parent merge on topic
OCT_ALARM_REMOTE = os.path.join(CMKREMOTE, os.path.basename(OCT_ALARM) + ".git")   # the bare remote of oct-alarm
OCT_FRESH = os.path.join(ROOT, "oct-fresh")          # branch fresh, cut from origin/main, with no tracking ref
OCT_FRESH_TRUNK = os.path.join(ROOT, "oct-fresh-trunk")  # as oct-fresh, but origin's default branch is trunk, at the base


def _oct_on_origin_main(where, trunk=False):
    """origin/main gains a three-parent merge O of x and y. Local main stays at the base, so O is on the
    remote only. With `trunk`, origin's default branch (origin/HEAD) is trunk, still at the base, so the
    remote's default base lacks O. The scope is read before any case judges it."""
    _cmk_pushed(where, {"a.txt": "base\n"})
    if trunk:
        _cmk_run(where, "push", "-q", "origin", "main:refs/heads/trunk")
        _cmk_run(where, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
    _oct_branch(where, "x", "x.txt", "x\n")
    _oct_branch(where, "y", "y.txt", "y\n")
    _cmk_run(where, "checkout", "-q", "-b", "src", "main")
    _cmk_commit(where, "m.txt", "m\n", "src one")
    _oct_merge(where, "src", ["x", "y"])
    _cmk_run(where, "push", "-q", "origin", "src:refs/heads/main")
    _oct_must(where, "origin/main", [3], "the octopus on origin/main")
    _oct_must(where, "main", [], "local main holds no merge")


def _oct_merged_origin(where):
    """Topic, at the base and pushed, merges origin/main: a two-parent merge that brings O in."""
    _oct_on_origin_main(where)
    _cmk_run(where, "checkout", "-q", "topic")
    _cmk_run(where, "merge", "-q", "--no-ff", "--no-edit", "origin/main")
    _oct_must(where, "origin/topic..HEAD", [2, 3], "the merge and O both sit past the tracking tip")
    _oct_must(where, "HEAD --not --remotes=origin", [2], "only the merge is new to the remote")


def _build_octopus_origin():
    _oct_merged_origin(OCT_ALARM)
    _oct_must(OCT_ALARM_REMOTE, "main", [3], "the bare remote of oct-alarm holds the octopus on main")
    _oct_merged_origin(OCT_ALARM_NEW)
    _oct_branch(OCT_ALARM_NEW, "x2", "x2.txt", "x2\n")
    _oct_branch(OCT_ALARM_NEW, "y2", "y2.txt", "y2\n")
    _oct_merge(OCT_ALARM_NEW, "topic", ["x2", "y2"])
    _oct_must(OCT_ALARM_NEW, "HEAD --not --remotes=origin", [2, 3], "the new three-parent merge and the merge")

    _oct_on_origin_main(OCT_FRESH)
    _cmk_run(OCT_FRESH, "checkout", "-q", "-b", "fresh", "--no-track", "origin/main")
    if run_vcs(OCT_FRESH, "rev-parse", "--verify", "-q", "refs/remotes/origin/fresh").returncode == 0:
        sys.exit("fixture setup failed in the octopus-push fixtures: fresh has a remote-tracking ref")
    if run_vcs(OCT_FRESH, "rev-parse", "--verify", "-q", "fresh@{upstream}").returncode == 0:
        sys.exit("fixture setup failed in the octopus-push fixtures: fresh has an upstream")
    _oct_must(OCT_FRESH, "HEAD", [3], "the new branch is cut from origin/main, which holds O")

    _oct_on_origin_main(OCT_FRESH_TRUNK, trunk=True)
    _cmk_run(OCT_FRESH_TRUNK, "checkout", "-q", "-b", "fresh", "--no-track", "origin/main")
    _oct_must(OCT_FRESH_TRUNK, "origin/trunk", [], "the remote's default branch holds no merge")
    _oct_must(OCT_FRESH_TRUNK, "HEAD", [3], "the new branch is cut from origin/main, which holds O")


lazy_fixture([OCT_ALARM, OCT_ALARM_NEW, OCT_FRESH, OCT_FRESH_TRUNK], _build_octopus_origin)


def oct_refuse(name, command, cwd):
    sh("octopus-push: %s is refused" % name, command, "deny", OCT_RULE, cwd=cwd)


def oct_allow(name, command, cwd):
    sh("octopus-push: %s is allowed" % name, command, "allow", cwd=cwd)


# A push is refused when a commit it would send is a merge of more than two parents, whatever the refspec.
oct_refuse("a push of a three-parent merge in the range", VCS + " push", OCT_THREE)
oct_refuse("a push by an explicit refspec of a three-parent merge in the range",
           VCS + " push origin HEAD:refs/heads/topic", OCT_THREE)
oct_refuse("a push of a four-parent merge in the range", VCS + " push", OCT_FOUR)

# Only what the push sends is judged: two-parent merges pass, and so does a range with no merge at all.
oct_allow("a push of a range holding only two-parent merges", VCS + " push", OCT_TWO)
oct_allow("a push of a range with no merge", VCS + " push", OCT_PLAIN)

# A merge already in the remote-tracking tip's history is outside the range, so the push passes. The empty
# range is the state where nothing is unpushed at all.
oct_allow("a push of a clean commit, with a three-parent merge already on the remote", VCS + " push", OCT_REMOTE)
oct_allow("a push with nothing unpushed, its three-parent merge already on the remote", VCS + " push", OCT_EMPTY)

# Main is out of scope. The push-main ask is queued, not raised, so a deny from this rule would win over it:
# this case fails if a builder's rule forgets the main exemption.
sh("octopus-push: a push of main with a three-parent merge keeps its push-main ask",
   VCS + " push origin main", "ask", PUSH_MAIN_RULE, cwd=OCT_MAIN)

# A false alarm: the range is what the push adds to the remote. An octopus already on a remote ref is not sent,
# so a merge that brings it in, or a new branch cut from it, passes. A new octopus above those is still refused.
oct_allow("a push of a topic that merges origin/main, whose octopus is already on origin/main",
          VCS + " push origin topic", OCT_ALARM)
oct_allow("a push of a new branch cut from origin/main, whose octopus is already on origin/main",
          VCS + " push origin fresh", OCT_FRESH)
oct_allow("a push of a new branch cut from origin/main, when origin's default branch lacks that octopus",
          VCS + " push origin fresh", OCT_FRESH_TRUNK)

# A push to a URL names no configured remote, so no remote-tracking ref is read for it. The bare repository holds
# the octopus on main, so the push sends only the merge, and it passes.
oct_allow("a push to the remote's path, whose octopus is already on its main",
          VCS + " push " + slash(OCT_ALARM_REMOTE) + " topic", OCT_ALARM)
oct_refuse("a push of a topic with a new three-parent merge above a merge of origin/main",
           VCS + " push origin topic", OCT_ALARM_NEW)

# A dry run sends nothing, so it passes whatever the range holds.
oct_allow("a dry run, --dry-run, of a push with a three-parent merge in the range",
          VCS + " push --dry-run origin topic", OCT_THREE)
oct_allow("a dry run, -n, of a push with a three-parent merge in the range",
          VCS + " push -n origin topic", OCT_THREE)


def octopus_remedy_case():
    """The octopus-push refusal names the two-parent form in its remedy, and never the forbidden target
    (git-remedy-never-names-target). The rule's name sits in the reason's header, so the target word is read
    only after the `Remedy:` label, in lower case."""
    got, reason = decide({
        "raw": None, "tool": "Bash", "cwd": OCT_THREE, "session": None,
        "env_path": None, "tool_input": {"command": VCS + " push"},
    })
    if got != "deny":
        return False, "expected deny, got %s" % got
    remedy = reason.lower().partition("remedy:")[2]
    if "two-parent" not in remedy:
        return False, "the remedy does not name the two-parent form: %s" % reason[:90]
    if OCT_TARGET_WORD in remedy:
        return False, "the remedy names the forbidden target %r: %s" % (OCT_TARGET_WORD, remedy[:90])
    leak = names_the_target(reason, OCT_RULE)
    if leak:
        return False, "the reason names the forbidden target %r" % leak
    return True, "refused, and the remedy names the two-parent form and not the octopus merge"


# =========================================================================== 6. frozen paths
