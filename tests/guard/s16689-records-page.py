# section 16689
FAMILY = "records-page"
FAMILIES["records-page"] = "a lane commit of the generated records page: refused unless the page is the base's"
#
# `records-page`. Owner ruling 2026-10-16 10:28 CDT ("Also add a guard"), decision records-index-at-merge.
# The page docs/records.md is rebuilt only at merge, by the merge tool. A lane never commits a change
# to it. Incident 2026-10-16: each lane rebuilt the page, and three batches conflicted on it. The guard
# refuses a lane commit whose page differs from the page on the lane's base. A merge of the base into
# the lane brings the base's page, so that commit is allowed.
#
# THE SEAM. The base is `resolve_default_base(root)` of guard_core (origin/HEAD, then local main, then
# local master), read at its TIP. The fixture makes local `main` STALE (page v0) while `origin/main`
# holds page v1, and every lane is cut from the stale `main`. So a guard that reads local `main`, or
# the merge base, reads v0 and refuses the merge case. A commit is refused only when the page it would
# hold differs from HEAD's page AND from the base tip's page. Any read that fails is no hit.
#
# ALSO PINNED (stage then commit): the hook runs BEFORE the shell chain, so
# `git add -A && git commit` and `git commit -am` stage the page after the hook has read the index.
# Those are the usual way an agent commits the page it just rebuilt, so they are pinned here too.
RECORDS_RULE = "records-page"
RECORDS_SAYS = ("docs/records.md", "merge", ("drop", "Drop"))   # the rule named plainly, and the remedy
RECORDS_NEVER = (VCS + " restore", VCS + " reset", VCS + " stash", VCS + " checkout")
# The rule acts only when the base page opens with the generated header (RECORDS_HEADER of guard_merge),
# so each fixture page starts with it.
REC_V0 = "# Records index\nrecords page v0, as the lane was cut\n"
REC_V1 = "# Records index\nrecords page v1, rebuilt on main\n"
REC_LANE = "# Records index\nrecords page v2, rebuilt by the lane\n"
REC_FEAT = "# Records index\nrecords page on the feature branch\n"
REC_REBUILT = "# Records index\nrecords page rebuilt by hand after the merge\n"
REC_MOVED_TEXT = "# Records index\nrecords page v3, moved on again on main\n"
REC_STACK_CUT = "# Records index\nrecords page on the stacked base, as the lane was cut\n"
REC_STACK_MOVED = "# Records index\nrecords page on the stacked base, moved on\n"
RECROOT = os.path.join(ROOT, "recpage")
RECMAIN = os.path.join(RECROOT, "main")
# One linked worktree per index state, each cut from the stale local `main`: a case only reads, but
# the index is per tree.
REC_LANES = {name: os.path.join(RECROOT, "lane-" + name) for name in (
    "staged", "staged-edit", "unstaged", "product", "merge", "merge-rebuilt", "copy-base", "deleted")}
REC_NOPAGE = os.path.join(RECROOT, "nopage")   # a repository that has no page at all
REC_NOBASE = os.path.join(RECROOT, "nobase")   # a page change staged, and no origin, main or master


def _rec_run(where, *args):
    done = run_vcs(where, *IDENT, *args)
    if done.returncode != 0:
        sys.exit("fixture setup failed in the records-page fixtures: %s %s in %r: %s"
                 % (VCS, " ".join(args), where, done.stderr.strip()))
    return done.stdout.strip()


def _rec_run_at(when, where, *args):
    """_rec_run with the author and committer dates fixed at `when` (unix seconds)."""
    env = dict(os.environ, GIT_AUTHOR_DATE="@%d +0000" % when, GIT_COMMITTER_DATE="@%d +0000" % when)
    done = subprocess.run([VCS, *IDENT, *args], cwd=where, env=env, capture_output=True, text=True)
    if done.returncode != 0:
        sys.exit("fixture setup failed in the records-page fixtures: %s %s in %r: %s"
                 % (VCS, " ".join(args), where, done.stderr.strip()))
    return done.stdout.strip()


def _rec_need(ok, what):
    if not ok:
        sys.exit("fixture setup failed in the records-page fixtures: " + what)


def _rec_page(where):
    return os.path.join(where, "docs", "records.md")


def _build_records_page():
    run, need, page = _rec_run, _rec_need, _rec_page

    make_repo(RECMAIN, {"docs/records.md": REC_V0, "src/app.py": "x = 1\n"})
    run(RECMAIN, "checkout", "-q", "-b", "advance")           # main's tip moves the page after the cut
    write(page(RECMAIN), REC_V1)
    run(RECMAIN, "commit", "-q", "-am", "main moves the page")
    run(RECMAIN, "update-ref", "refs/remotes/origin/main", "advance")
    run(RECMAIN, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    run(RECMAIN, "checkout", "-q", "main")                    # local main stays at the cut: stale
    run(RECMAIN, "branch", "-q", "-D", "advance")
    need(run(RECMAIN, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD") == "origin/main",
         "origin/HEAD does not resolve to origin/main")
    need(run(RECMAIN, "show", "origin/main:docs/records.md") == REC_V1.strip(), "origin/main page is not v1")
    need(run(RECMAIN, "show", "main:docs/records.md") == REC_V0.strip(), "local main page is not v0")
    for name, where in REC_LANES.items():
        run(RECMAIN, "worktree", "add", "-q", "-b", "lane-" + name, where, "main")

    def merged(name):
        run(REC_LANES[name], "merge", "-q", "--no-commit", "--no-ff", "origin/main")
        need(run(REC_LANES[name], "rev-parse", "--verify", "-q", "MERGE_HEAD"),
             "no merge is in progress in the lane %r" % name)

    def stage(name, rel):
        run(REC_LANES[name], "add", rel)

    write(page(REC_LANES["staged"]), REC_LANE)           # rebuilt, then staged
    stage("staged", "docs/records.md")
    write(page(REC_LANES["staged-edit"]), REC_LANE)      # rebuilt and staged, then a product file edited
    stage("staged-edit", "docs/records.md")
    write(os.path.join(REC_LANES["staged-edit"], "src", "app.py"), "x = 3\n")
    write(page(REC_LANES["unstaged"]), REC_LANE)         # rebuilt, nothing staged
    write(os.path.join(REC_LANES["product"], "src", "app.py"), "x = 2\n")   # a product edit only
    stage("product", "src/app.py")
    merged("merge")                                      # origin/main merged in: the page is the base's
    merged("merge-rebuilt")                              # the same merge, then the page rebuilt by hand
    write(page(REC_LANES["merge-rebuilt"]), REC_LANE)
    stage("merge-rebuilt", "docs/records.md")
    write(page(REC_LANES["copy-base"]), REC_V1)          # the base's page copied over, no merge
    stage("copy-base", "docs/records.md")
    run(REC_LANES["deleted"], "rm", "docs/records.md")   # the page removed and staged, no merge in progress
    staged = lambda name: run(REC_LANES[name], "diff", "--cached", "--name-only")   # noqa: E731
    need(run(REC_LANES["staged"], "show", ":docs/records.md") == REC_LANE.strip(), "staged page is not v2")
    need(staged("unstaged") == "" and run(REC_LANES["unstaged"], "diff", "--name-only") == "docs/records.md",
         "the unstaged lane is not 'page edited, nothing staged'")
    need(staged("product") == "src/app.py", "the product lane stages more than src/app.py")
    need(staged("staged-edit") == "docs/records.md"
         and run(REC_LANES["staged-edit"], "diff", "--name-only") == "src/app.py",
         "the staged-edit lane is not 'page staged, src/app.py edited and unstaged'")
    need(run(REC_LANES["merge"], "show", ":docs/records.md") == REC_V1.strip(), "the merged lane page is not v1")
    need(run(REC_LANES["merge-rebuilt"], "show", ":docs/records.md") == REC_LANE.strip(),
         "the rebuilt merge lane page is not v2")
    need(run(REC_LANES["copy-base"], "show", ":docs/records.md") == REC_V1.strip(), "the copy-base page is not v1")
    need(staged("deleted") == "docs/records.md" and run(REC_LANES["deleted"], "ls-files", "--", "docs/records.md") == "",
         "the deleted lane does not stage the page's removal")

    make_repo(REC_NOPAGE, {"src/app.py": "x = 1\n"})
    write(os.path.join(REC_NOPAGE, "src", "app.py"), "x = 2\n")
    run(REC_NOPAGE, "add", "src/app.py")
    os.makedirs(REC_NOBASE, exist_ok=True)
    run(REC_NOBASE, "init", "-q", "-b", "trunk", ".")
    write(page(REC_NOBASE), REC_V0)
    run(REC_NOBASE, "add", "-A")
    run(REC_NOBASE, "commit", "-q", "-m", "first")
    write(page(REC_NOBASE), REC_LANE)
    run(REC_NOBASE, "add", "docs/records.md")
    need(run_vcs(REC_NOBASE, "rev-parse", "--verify", "-q", "refs/heads/main").returncode != 0
         and run_vcs(REC_NOBASE, "rev-parse", "--verify", "-q", "refs/heads/master").returncode != 0
         and not run(REC_NOBASE, "remote"), "the nobase repository has a base")


lazy_fixture([RECMAIN, REC_NOPAGE, REC_NOBASE, *REC_LANES.values()], _build_records_page)

# Three more repositories. The base is a property of the repository
# (origin/HEAD, local main, origin/main), so each needs its own, not a worktree of RECMAIN.
RECMORE = os.path.join(ROOT, "recmore")
# origin/HEAD names a ref that does not exist, so the base is local `main`, which lags origin/main:
# local main holds v0, origin/main holds v1. The owner's resolve order stays as it is.
REC_DANGLE = os.path.join(RECMORE, "dangle")
REC_DANGLE_LANES = {name: os.path.join(RECMORE, "dangle-" + name) for name in ("merge", "fresh", "rebuilt")}
# The page was added on main after the lane was cut: HEAD has no page, the base (origin/main) has v1.
REC_NEW = os.path.join(RECMORE, "new")
REC_NEW_LANE = os.path.join(RECMORE, "new-lane")
# The base has no page at all: a lane that creates it is the first adoption.
REC_ADOPT = os.path.join(RECMORE, "adopt")
REC_ADOPT_LANE = os.path.join(RECMORE, "adopt-lane")
# The base page is hand-written: it does not open with the generated header, so the rule is no hit.
REC_PLAIN = os.path.join(RECMORE, "plain")
REC_PLAIN_LANES = {name: os.path.join(RECMORE, "plain-" + name) for name in ("staged", "product")}
# origin/main holds a page newer than the page a lane's merge brought. Each lane holds one state.
REC_MOVED = os.path.join(RECMORE, "moved")
REC_MOVED_LANES = {name: os.path.join(RECMORE, "moved-" + name) for name in (
    "merge", "rebuilt", "quit", "product", "nonbase", "take", "base")}
# A branch merged into origin/main: its tip is in origin/main's history, off the first-parent line.
REC_ANC = os.path.join(RECMORE, "ancestor")
REC_ANC_LANE = os.path.join(RECMORE, "ancestor-lane")
# A stacked base: a branch with a page commit of its own, cut from main and never merged into it, so its tip is
# off origin/main's history. Each lane is cut from it, the base moves on, and the lane merges it again.
REC_STACK = os.path.join(RECMORE, "stacked")
REC_STACK_LANES = {name: os.path.join(RECMORE, "stacked-" + name) for name in ("merge", "rebuilt", "quit")}
# A criss-cross stacked base: the base is cut from main at R, merges origin/main at M1 and moves on to S2. Each lane is
# cut from the base's first commit S1 and merges origin/main at M2, a later main commit. The lane's merge with the base
# then has two best merge bases, S1 (off origin/main) and M1 (on it). Commits carry fixed dates, REC_T0 plus an offset,
# so the order of the bases does not depend on the clock.
REC_T0 = 1700000000
REC_MAIN_LATER = "# Records index\nrecords page on main, after the stacked base merged it\n"
REC_CRISS_HAND = "# Records index\nrecords page written by hand on the criss-cross lane\n"
REC_CRISS = os.path.join(RECMORE, "criss")
REC_CRISS_LANES = {name: os.path.join(RECMORE, "criss-" + name) for name in ("merge", "hand")}
# A lane cut from main that merges an unrelated unmerged branch B. B is cut from a commit X1 that main has merged, and
# B merged origin/main at an older commit A1, so the lane's two best merge bases are A1 and X1, both on origin/main.
REC_UNREL_PAGE = "# Records index\nrecords page on an unrelated unmerged branch\n"
REC_UNREL = os.path.join(RECMORE, "unrelated")
REC_UNREL_LANE = os.path.join(RECMORE, "unrelated-lane")
# A repository with no origin, so no origin/main ref. The base is local `main`, and `merge-base --is-ancestor` against
# origin/main exits 128: a failed read, not "not an ancestor". The lane merges a feature branch's page, so the staged
# page is MERGE_HEAD's.
REC_NOORIGIN = os.path.join(RECMORE, "noorigin")
REC_NOORIGIN_LANE = os.path.join(RECMORE, "noorigin-lane")


def _build_records_more():
    run, need, page = _rec_run, _rec_need, _rec_page

    def advance(where, files, origin_head, start="HEAD", when=None):
        # origin/main moves on after the lane's cut; local main stays at the cut
        run(where, "checkout", "-q", "-b", "advance", start)
        for rel, text in files.items():
            write(os.path.join(where, rel), text)
        run(where, "add", "-A")
        if when is None:
            run(where, "commit", "-q", "-m", "main moves the page")
        else:
            _rec_run_at(when, where, "commit", "-q", "-m", "main moves the page")
        run(where, "update-ref", "refs/remotes/origin/main", "advance")
        run(where, "symbolic-ref", "refs/remotes/origin/HEAD", origin_head)
        run(where, "checkout", "-q", "main")
        run(where, "branch", "-q", "-D", "advance")

    make_repo(REC_DANGLE, {"docs/records.md": REC_V0, "src/app.py": "x = 1\n"})
    advance(REC_DANGLE, {"docs/records.md": REC_V1}, "refs/remotes/origin/gone")
    need(run(REC_DANGLE, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD") == "origin/gone"
         and run_vcs(REC_DANGLE, "rev-parse", "--verify", "-q", "origin/gone").returncode != 0,
         "origin/HEAD in the dangle repository does not dangle")
    need(run(REC_DANGLE, "show", "main:docs/records.md") == REC_V0.strip()
         and run(REC_DANGLE, "show", "origin/main:docs/records.md") == REC_V1.strip(),
         "the dangle repository is not 'local main v0, origin/main v1'")
    for name, where in REC_DANGLE_LANES.items():
        run(REC_DANGLE, "worktree", "add", "-q", "-b", "lane-" + name, where, "main")
    for name in ("merge", "rebuilt"):
        run(REC_DANGLE_LANES[name], "merge", "-q", "--no-commit", "--no-ff", "origin/main")
        need(run(REC_DANGLE_LANES[name], "rev-parse", "--verify", "-q", "MERGE_HEAD"),
             "no merge is in progress in the dangle lane %r" % name)
    write(page(REC_DANGLE_LANES["rebuilt"]), REC_LANE)
    run(REC_DANGLE_LANES["rebuilt"], "add", "docs/records.md")
    need(run(REC_DANGLE_LANES["merge"], "show", ":docs/records.md") == REC_V1.strip()
         and run(REC_DANGLE_LANES["rebuilt"], "show", ":docs/records.md") == REC_LANE.strip(),
         "the dangle merge lanes hold the wrong staged pages")

    make_repo(REC_NEW, {"src/app.py": "x = 1\n"})
    advance(REC_NEW, {"docs/records.md": REC_V1}, "refs/remotes/origin/main")
    run(REC_NEW, "worktree", "add", "-q", "-b", "lane-new", REC_NEW_LANE, "main")
    write(page(REC_NEW_LANE), REC_LANE)                   # the generator wrote a page: untracked
    write(os.path.join(REC_NEW_LANE, "src", "app.py"), "x = 2\n")   # and a tracked edit, unstaged
    need(run(REC_NEW_LANE, "ls-tree", "HEAD", "--", "docs/records.md") == ""
         and run(REC_NEW_LANE, "ls-files", "--others", "--exclude-standard") == "docs/records.md"
         and run(REC_NEW_LANE, "show", "origin/main:docs/records.md") == REC_V1.strip(),
         "the new lane is not 'no page at HEAD, an untracked page, base has v1'")

    make_repo(REC_ADOPT, {"src/app.py": "x = 1\n"})
    run(REC_ADOPT, "worktree", "add", "-q", "-b", "lane-adopt", REC_ADOPT_LANE, "main")
    write(page(REC_ADOPT_LANE), REC_LANE)
    run(REC_ADOPT_LANE, "add", "docs/records.md")
    need(run(REC_ADOPT_LANE, "ls-tree", "main", "--", "docs/records.md") == ""
         and run(REC_ADOPT_LANE, "diff", "--cached", "--name-only") == "docs/records.md",
         "the adopt lane is not 'base has no page, page staged as new'")

    make_repo(REC_PLAIN, {"docs/records.md": "hand-written page v0\n", "src/app.py": "x = 1\n"})
    advance(REC_PLAIN, {"docs/records.md": "hand-written page v1\n"}, "refs/remotes/origin/main")
    for name, where in REC_PLAIN_LANES.items():
        run(REC_PLAIN, "worktree", "add", "-q", "-b", "lane-" + name, where, "main")
    write(page(REC_PLAIN_LANES["staged"]), "hand-written page v2\n")    # a staged edit of the page
    run(REC_PLAIN_LANES["staged"], "add", "docs/records.md")
    write(os.path.join(REC_PLAIN_LANES["product"], "src", "app.py"), "x = 2\n")   # a product edit only
    run(REC_PLAIN_LANES["product"], "add", "src/app.py")
    need(not run(REC_PLAIN, "show", "origin/main:docs/records.md").startswith("# Records index")
         and run(REC_PLAIN_LANES["staged"], "diff", "--cached", "--name-only") == "docs/records.md"
         and run(REC_PLAIN_LANES["product"], "diff", "--cached", "--name-only") == "src/app.py",
         "the plain lanes are not 'base page has no header; page staged / product file staged'")

    # The moved repository. Each lane is cut from main (page v0), and holds its own page edit, committed.
    # origin/main is v1 when the lanes merge it, so MERGE_HEAD is v1. Then origin/main moves to v3, on
    # top of v1. `base` merges v3, so its MERGE_HEAD page is the base's own page.
    make_repo(REC_MOVED, {"docs/records.md": REC_V0, "src/app.py": "x = 1\n"})
    advance(REC_MOVED, {"docs/records.md": REC_V1}, "refs/remotes/origin/main")
    run(REC_MOVED, "checkout", "-q", "-b", "feat")
    write(page(REC_MOVED), REC_FEAT)
    run(REC_MOVED, "add", "-A")
    run(REC_MOVED, "commit", "-q", "-m", "feature page")
    run(REC_MOVED, "checkout", "-q", "main")
    for name, where in REC_MOVED_LANES.items():
        run(REC_MOVED, "worktree", "add", "-q", "-b", "lane-moved-" + name, where, "main")
        write(page(where), REC_LANE)
        write(os.path.join(where, "src", "app.py"), "x = 2\n")
        run(where, "add", "-A")
        run(where, "commit", "-q", "-m", "lane page")

    def conflicted(name, ref):
        where = REC_MOVED_LANES[name]
        run_vcs(where, *IDENT, "merge", "--no-commit", "--no-ff", ref)   # a conflict exits 1: that state is the point
        _require_conflict(where, "docs/records.md")

    def take(name):
        """The lane takes MERGE_HEAD's page into its index, as a test-author does after a conflict."""
        where = REC_MOVED_LANES[name]
        write(page(where), run_vcs(where, "show", "MERGE_HEAD:docs/records.md").stdout)
        run(where, "add", "docs/records.md")

    for name in ("merge", "rebuilt", "quit", "product", "take"):
        conflicted(name, "origin/main")                      # MERGE_HEAD is v1
    conflicted("nonbase", "feat")                            # MERGE_HEAD is the feature branch's page
    advance(REC_MOVED, {"docs/records.md": REC_MOVED_TEXT}, "refs/remotes/origin/main",
            start="refs/remotes/origin/main")                # origin/main moves on: v3
    conflicted("base", "origin/main")                        # MERGE_HEAD is v3
    take("merge")
    write(page(REC_MOVED_LANES["rebuilt"]), REC_REBUILT)
    run(REC_MOVED_LANES["rebuilt"], "add", "docs/records.md")
    take("quit")
    run(REC_MOVED_LANES["quit"], "merge", "--quit")          # MERGE_HEAD removed; the index keeps v1
    take("product")
    write(os.path.join(REC_MOVED_LANES["product"], "src", "app.py"), "x = 3\n")
    run(REC_MOVED_LANES["product"], "add", "src/app.py")
    take("nonbase")
    take("base")
    take("take")                                             # the page is in the tree, as a take leaves it
    write(os.path.join(REC_MOVED_LANES["base"], "src", "app.py"), "x = 3\n")
    run(REC_MOVED_LANES["base"], "add", "src/app.py")
    need(run(REC_MOVED, "show", "origin/main:docs/records.md") == REC_MOVED_TEXT.strip(),
         "origin/main did not move to v3 in the moved repository")
    need(run(REC_MOVED_LANES["merge"], "show", ":docs/records.md") == REC_V1.strip()
         and run(REC_MOVED_LANES["base"], "show", ":docs/records.md") == REC_MOVED_TEXT.strip(),
         "the moved lanes do not hold MERGE_HEAD's pages (v1 for merge, v3 for base)")
    need(run(REC_MOVED_LANES["nonbase"], "show", ":docs/records.md") == REC_FEAT.strip()
         and run_vcs(REC_MOVED_LANES["quit"], "rev-parse", "--verify", "-q", "MERGE_HEAD").returncode != 0,
         "the moved nonbase lane does not hold the feature page, or the quit lane still has a merge")
    need(run(REC_MOVED_LANES["take"], "show", ":docs/records.md") == REC_V1.strip()
         and run(REC_MOVED_LANES["take"], "show", "HEAD:docs/records.md") == REC_LANE.strip(),
         "the take lane does not hold MERGE_HEAD's page in its index, over the lane's own HEAD page")

    # The branch 'feat-merged' carries its own page. origin/main takes it in a merge that keeps origin's page,
    # so the branch's tip is in origin/main's history, and not on its first-parent line. The lane is cut
    # from main before that merge, holds its own page, and merges the branch.
    make_repo(REC_ANC, {"docs/records.md": REC_V0, "src/app.py": "x = 1\n"})
    run(REC_ANC, "checkout", "-q", "-b", "feat-merged")
    write(page(REC_ANC), REC_FEAT)
    run(REC_ANC, "add", "-A")
    run(REC_ANC, "commit", "-q", "-m", "merged branch page")
    run(REC_ANC, "checkout", "-q", "main")
    advance(REC_ANC, {"docs/records.md": REC_V1}, "refs/remotes/origin/main")          # origin/main: v1
    run(REC_ANC, "checkout", "-q", "-b", "onmain", "refs/remotes/origin/main")
    run_vcs(REC_ANC, *IDENT, "merge", "--no-ff", "--no-edit", "feat-merged")            # conflicts on the page
    _require_conflict(REC_ANC, "docs/records.md")
    run(REC_ANC, "checkout", "--ours", "docs/records.md")                               # origin's page stays
    run(REC_ANC, "add", "docs/records.md")
    run(REC_ANC, "commit", "-q", "--no-edit")
    run(REC_ANC, "update-ref", "refs/remotes/origin/main", "onmain")
    run(REC_ANC, "update-ref", "refs/remotes/origin/feat-merged", "feat-merged")
    run(REC_ANC, "checkout", "-q", "main")
    run(REC_ANC, "branch", "-q", "-D", "onmain")
    run(REC_ANC, "worktree", "add", "-q", "-b", "lane-ancestor", REC_ANC_LANE, "main")  # cut before the merge
    write(page(REC_ANC_LANE), REC_LANE)
    run(REC_ANC_LANE, "add", "docs/records.md")
    run(REC_ANC_LANE, "commit", "-q", "-m", "lane page")
    run_vcs(REC_ANC_LANE, *IDENT, "merge", "--no-commit", "--no-ff", "origin/feat-merged")
    _require_conflict(REC_ANC_LANE, "docs/records.md")
    write(page(REC_ANC_LANE), run_vcs(REC_ANC_LANE, "show", "MERGE_HEAD:docs/records.md").stdout)
    run(REC_ANC_LANE, "add", "docs/records.md")
    feat = run(REC_ANC, "rev-parse", "refs/heads/feat-merged")
    first_parent = run(REC_ANC, "rev-list", "--first-parent", "refs/remotes/origin/main").split()
    need(run_vcs(REC_ANC, "merge-base", "--is-ancestor", feat, "refs/remotes/origin/main").returncode == 0
         and feat not in first_parent
         and run(REC_ANC_LANE, "show", ":docs/records.md") == REC_FEAT.strip(),
         "the ancestor fixture: feat-merged is not in origin/main's history off its first-parent line, "
         "or the lane does not hold the branch's page")

    # The stacked base `stack-base` is cut from main with its own page commit (B1). Its tip is NOT in origin/main's
    # history. Each lane is cut from it at B1, then the base moves on to B2, and each lane merges it again.
    make_repo(REC_STACK, {"docs/records.md": REC_V0, "src/app.py": "x = 1\n"})
    advance(REC_STACK, {"docs/records.md": REC_V1}, "refs/remotes/origin/main")   # origin/main: v1
    run(REC_STACK, "checkout", "-q", "-b", "stack-base")
    write(page(REC_STACK), REC_STACK_CUT)
    run(REC_STACK, "add", "-A")
    run(REC_STACK, "commit", "-q", "-m", "stacked base page")
    run(REC_STACK, "update-ref", "refs/remotes/origin/stack-base", "stack-base")
    run(REC_STACK, "checkout", "-q", "main")
    for name, where in REC_STACK_LANES.items():
        run(REC_STACK, "worktree", "add", "-q", "-b", "lane-stack-" + name, where, "stack-base")
        write(os.path.join(where, "src", "app.py"), "x = 2\n")   # the lane's own commit, so the merge is no fast-forward
        run(where, "add", "-A")
        run(where, "commit", "-q", "-m", "lane change")
    run(REC_STACK, "checkout", "-q", "stack-base")
    write(page(REC_STACK), REC_STACK_MOVED)
    run(REC_STACK, "add", "-A")
    run(REC_STACK, "commit", "-q", "-m", "stacked base moves on")
    run(REC_STACK, "update-ref", "refs/remotes/origin/stack-base", "stack-base")
    run(REC_STACK, "checkout", "-q", "main")
    base_tip = run(REC_STACK, "rev-parse", "refs/heads/stack-base")
    need(base_tip not in run(REC_STACK, "rev-list", "--first-parent", "origin/main").split(),
         "the stacked fixture: the base's tip is on origin/main's first-parent line")
    need(run(REC_STACK, "show", "origin/main:docs/records.md") == REC_V1.strip(),
         "the stacked fixture: origin/main's page is not v1")
    for name in REC_STACK_LANES:
        run(REC_STACK_LANES[name], "merge", "-q", "--no-commit", "--no-ff", "origin/stack-base")
        need(run(REC_STACK_LANES[name], "rev-parse", "--verify", "-q", "MERGE_HEAD") == base_tip,
             "the stacked fixture: MERGE_HEAD is not the base's tip in the lane %r" % name)
    lane = REC_STACK_LANES["merge"]
    cut = run(lane, "merge-base", "HEAD", "MERGE_HEAD")
    need(run_vcs(REC_STACK, "merge-base", "--is-ancestor", cut, "origin/main").returncode == 1,
         "the stacked fixture: the lane's merge base with the base is on origin/main, so no unmerged history is shared")
    need(run(lane, "show", "HEAD:docs/records.md") == REC_STACK_CUT.strip(),
         "the stacked fixture: the merge lane's HEAD page is not the page it was cut with")
    need(run(lane, "show", ":docs/records.md") == REC_STACK_MOVED.strip(),
         "the stacked fixture: the merge lane's staged page is not the base's moved page")
    write(page(REC_STACK_LANES["rebuilt"]), REC_REBUILT)
    run(REC_STACK_LANES["rebuilt"], "add", "docs/records.md")
    need(run(REC_STACK_LANES["rebuilt"], "show", ":docs/records.md") == REC_REBUILT.strip(),
         "the stacked fixture: the rebuilt lane's staged page is not the hand-written page")
    run(REC_STACK_LANES["quit"], "merge", "--quit")          # MERGE_HEAD removed; the index keeps the base's page
    need(run_vcs(REC_STACK_LANES["quit"], "rev-parse", "--verify", "-q", "MERGE_HEAD").returncode != 0,
         "the stacked fixture: the quit lane still has a merge in progress")
    need(run(REC_STACK_LANES["quit"], "show", ":docs/records.md") == REC_STACK_MOVED.strip(),
         "the stacked fixture: the quit lane's staged page is not the base's moved page")

    # The criss-cross stacked base. Plain `git merge-base` must print M1 here, or the criss-cross case proves nothing,
    # so the fixture stops when it does not.
    make_repo(REC_CRISS, {"docs/records.md": REC_V0, "src/app.py": "x = 1\n"})
    advance(REC_CRISS, {"docs/records.md": REC_V1}, "refs/remotes/origin/main", when=REC_T0 + 2000)   # origin/main: M1
    m1 = run(REC_CRISS, "rev-parse", "origin/main")
    run(REC_CRISS, "checkout", "-q", "-b", "criss-base", "main")                                       # cut from R
    write(page(REC_CRISS), REC_STACK_CUT)
    run(REC_CRISS, "add", "-A")
    _rec_run_at(REC_T0 + 1000, REC_CRISS, "commit", "-q", "-m", "stacked base page")                    # S1
    s1 = run(REC_CRISS, "rev-parse", "criss-base")
    for name, lane in REC_CRISS_LANES.items():
        run(REC_CRISS, "worktree", "add", "-q", "-b", "lane-criss-" + name, lane, "criss-base")
        write(os.path.join(lane, "src", "app.py"), "x = 2\n")
        run(lane, "add", "-A")
        _rec_run_at(REC_T0 + 1100, lane, "commit", "-q", "-m", "lane change, " + name)
    run(REC_CRISS, "checkout", "-q", "criss-base")
    run_vcs(REC_CRISS, *IDENT, "merge", "--no-commit", "--no-ff", m1)                                  # the base merges M1
    _require_conflict(REC_CRISS, "docs/records.md")
    write(page(REC_CRISS), REC_STACK_MOVED)
    run(REC_CRISS, "add", "docs/records.md")
    _rec_run_at(REC_T0 + 2100, REC_CRISS, "commit", "-q", "--no-edit")                                # S2
    s2 = run(REC_CRISS, "rev-parse", "criss-base")
    run(REC_CRISS, "checkout", "-q", "main")
    advance(REC_CRISS, {"docs/records.md": REC_MAIN_LATER}, "refs/remotes/origin/main",
            start="refs/remotes/origin/main", when=REC_T0 + 2200)                                      # origin/main: M2
    m2 = run(REC_CRISS, "rev-parse", "origin/main")
    for name, text in (("merge", REC_STACK_MOVED), ("hand", REC_CRISS_HAND)):
        lane = REC_CRISS_LANES[name]
        _rec_run_at(REC_T0 + 2300, lane, "merge", "--no-edit", "-X", "ours", m2)                     # keeps its own page
        run_vcs(lane, *IDENT, "merge", "--no-commit", "--no-ff", s2)                                # then the base's tip
        need(run(lane, "rev-parse", "--verify", "-q", "MERGE_HEAD") == s2,
             "the criss-cross fixture: MERGE_HEAD is not the base's tip in the lane %r" % name)
        write(page(lane), text)
        run(lane, "add", "docs/records.md")
    lane = REC_CRISS_LANES["merge"]
    need(set(run(lane, "merge-base", "--all", "HEAD", "MERGE_HEAD").split()) == {m1, s1},
         "the criss-cross fixture: the lane's merge bases are not M1 and S1 (merge-base --all)")
    need(run(lane, "merge-base", "HEAD", "MERGE_HEAD") == m1,
         "the criss-cross fixture: plain merge-base does not print the main commit M1")
    need(run_vcs(REC_CRISS, "merge-base", "--is-ancestor", m1, "origin/main").returncode == 0
         and run_vcs(REC_CRISS, "merge-base", "--is-ancestor", s1, "origin/main").returncode == 1,
         "the criss-cross fixture: M1 is not on origin/main, or S1 is")
    need(run(lane, "show", ":docs/records.md") == REC_STACK_MOVED.strip()
         and run(lane, "show", "HEAD:docs/records.md") == REC_STACK_CUT.strip(),
         "the criss-cross fixture: the merge lane's staged page is not the base's moved page")
    need(run(REC_CRISS_LANES["hand"], "show", ":docs/records.md") == REC_CRISS_HAND.strip(),
         "the criss-cross fixture: the hand lane's staged page is not the hand-written page")

    # A lane cut from main merges an unrelated unmerged branch B. X1 is a branch commit that main has merged; B is cut
    # from X1 and merges origin/main at A1. The lane merges origin/main at M, the merge commit that holds X1.
    make_repo(REC_UNREL, {"docs/records.md": REC_V0, "src/app.py": "x = 1\n"})
    run(REC_UNREL, "checkout", "-q", "-b", "feat-x")
    write(os.path.join(REC_UNREL, "src", "x.py"), "y = 1\n")
    run(REC_UNREL, "add", "-A")
    _rec_run_at(REC_T0 + 1000, REC_UNREL, "commit", "-q", "-m", "feature x")                          # X1
    x1 = run(REC_UNREL, "rev-parse", "HEAD")
    run(REC_UNREL, "checkout", "-q", "main")
    write(page(REC_UNREL), REC_V1)
    run(REC_UNREL, "add", "-A")
    _rec_run_at(REC_T0 + 1100, REC_UNREL, "commit", "-q", "-m", "main moves the page")                # A1
    a1 = run(REC_UNREL, "rev-parse", "HEAD")
    run(REC_UNREL, "update-ref", "refs/remotes/origin/main", a1)
    run(REC_UNREL, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    run(REC_UNREL, "checkout", "-q", "-b", "unrelated", x1)
    write(page(REC_UNREL), REC_UNREL_PAGE)
    run(REC_UNREL, "add", "-A")
    _rec_run_at(REC_T0 + 1200, REC_UNREL, "commit", "-q", "-m", "unrelated page")                     # B1
    _rec_run_at(REC_T0 + 1300, REC_UNREL, "merge", "--no-edit", "-X", "ours", a1)                     # B2: origin/main at A1
    b2 = run(REC_UNREL, "rev-parse", "HEAD")
    run(REC_UNREL, "checkout", "-q", "main")
    _rec_run_at(REC_T0 + 1400, REC_UNREL, "merge", "--no-edit", "--no-ff", "feat-x")                  # main takes X1: M
    run(REC_UNREL, "update-ref", "refs/remotes/origin/main", "main")
    run(REC_UNREL, "worktree", "add", "-q", "-b", "lane-unrelated", REC_UNREL_LANE, a1)               # cut from main at A1
    write(os.path.join(REC_UNREL_LANE, "src", "app.py"), "x = 2\n")
    run(REC_UNREL_LANE, "add", "-A")
    _rec_run_at(REC_T0 + 1500, REC_UNREL_LANE, "commit", "-q", "-m", "lane change")
    _rec_run_at(REC_T0 + 1600, REC_UNREL_LANE, "merge", "--no-edit", "origin/main")                    # origin/main at M
    run_vcs(REC_UNREL_LANE, *IDENT, "merge", "--no-commit", "--no-ff", b2)
    need(run(REC_UNREL_LANE, "rev-parse", "--verify", "-q", "MERGE_HEAD") == b2,
         "the unrelated fixture: MERGE_HEAD is not the unrelated branch's tip")
    write(page(REC_UNREL_LANE), REC_UNREL_PAGE)
    run(REC_UNREL_LANE, "add", "docs/records.md")
    bases = set(run(REC_UNREL_LANE, "merge-base", "--all", "HEAD", "MERGE_HEAD").split())
    need(bases == {a1, x1}, "the unrelated fixture: the lane's merge bases are not A1 and X1 (merge-base --all)")
    need(all(run_vcs(REC_UNREL, "merge-base", "--is-ancestor", base, "origin/main").returncode == 0 for base in bases),
         "the unrelated fixture: a merge base is not on origin/main")
    need(run(REC_UNREL_LANE, "show", ":docs/records.md") == REC_UNREL_PAGE.strip(),
         "the unrelated fixture: the lane's staged page is not the unrelated branch's page")

    make_repo(REC_NOORIGIN, {"docs/records.md": REC_V0, "src/app.py": "x = 1\n"})
    run(REC_NOORIGIN, "checkout", "-q", "-b", "feat-page")
    write(page(REC_NOORIGIN), REC_FEAT)
    run(REC_NOORIGIN, "add", "-A")
    _rec_run_at(REC_T0 + 1000, REC_NOORIGIN, "commit", "-q", "-m", "feature page")
    feat = run(REC_NOORIGIN, "rev-parse", "refs/heads/feat-page")
    run(REC_NOORIGIN, "checkout", "-q", "main")
    run(REC_NOORIGIN, "worktree", "add", "-q", "-b", "lane-noorigin", REC_NOORIGIN_LANE, "main")
    write(os.path.join(REC_NOORIGIN_LANE, "src", "app.py"), "x = 2\n")
    run(REC_NOORIGIN_LANE, "add", "-A")
    _rec_run_at(REC_T0 + 1100, REC_NOORIGIN_LANE, "commit", "-q", "-m", "lane change")
    run_vcs(REC_NOORIGIN_LANE, *IDENT, "merge", "--no-commit", "--no-ff", "feat-page")
    need(run_vcs(REC_NOORIGIN, "rev-parse", "--verify", "-q", "refs/remotes/origin/main").returncode != 0
         and not run(REC_NOORIGIN, "remote"), "the noorigin fixture has an origin or an origin/main ref")
    need(run(REC_NOORIGIN_LANE, "rev-parse", "--verify", "-q", "MERGE_HEAD") == feat,
         "the noorigin fixture: MERGE_HEAD is not the feature branch's tip")
    need(run(REC_NOORIGIN_LANE, "show", ":docs/records.md") == REC_FEAT.strip(),
         "the noorigin fixture: the lane's staged page is not the feature branch's page")
    need(run(REC_NOORIGIN_LANE, "show", "HEAD:docs/records.md") == REC_V0.strip()
         and run(REC_NOORIGIN_LANE, "show", "main:docs/records.md") == REC_V0.strip(),
         "the noorigin fixture: HEAD's page or the base's page is not v0")
    bases = run(REC_NOORIGIN_LANE, "merge-base", "--all", "HEAD", "MERGE_HEAD").split()
    need(bases and all(run_vcs(REC_NOORIGIN, "merge-base", "--is-ancestor", base, "origin/main").returncode == 128
                       for base in bases),
         "the noorigin fixture: a merge base's is-ancestor read against origin/main does not exit 128")
    need(run_vcs(REC_NOORIGIN, "rev-list", "--first-parent", "origin/main").returncode != 0,
         "the noorigin fixture: rev-list --first-parent origin/main does not fail")


lazy_fixture([REC_DANGLE, REC_NEW, REC_ADOPT, REC_PLAIN, *REC_DANGLE_LANES.values(), REC_NEW_LANE,
              REC_ADOPT_LANE, *REC_PLAIN_LANES.values(), REC_MOVED, *REC_MOVED_LANES.values(),
              REC_ANC, REC_ANC_LANE, REC_STACK, *REC_STACK_LANES.values(),
              REC_CRISS, *REC_CRISS_LANES.values(), REC_UNREL, REC_UNREL_LANE,
              REC_NOORIGIN, REC_NOORIGIN_LANE], _build_records_more)


def records_refuse(name, command, lane, **kw):
    sh("records-page: %s is refused" % name, command, "deny", RECORDS_RULE, cwd=REC_LANES.get(lane, lane),
       carries=RECORDS_SAYS, lacks=RECORDS_NEVER, **kw)


def records_allow(name, command, cwd, **kw):
    sh("records-page: %s is allowed" % name, command, "allow", cwd=cwd, **kw)


# 1. A staged page that is not the base's page: refused, under Bash and PowerShell, and for a builder.
records_refuse("a lane commit of a staged page that differs from the base's", VCS + " commit -m x", "staged")
records_refuse("a lane commit of a staged page that differs from the base's, under PowerShell",
             VCS + " commit -m x", "staged", tool="PowerShell")
records_refuse("a builder's commit of a staged page that differs from the base's", VCS + " commit -m x",
             "staged", agent_id="bld1", agent_type="builder")
# A merge commit is no exemption: only the base's own page rides in on a merge.
records_refuse("a merge commit whose page was rebuilt by hand", VCS + " commit -m x", "merge-rebuilt")
# Stage then commit in one call (beyond the brief's five cases): the page is staged when the commit runs.
records_refuse("stage then commit: commit -am with an edited page", VCS + ' commit -am x', "unstaged")
records_refuse("stage then commit: commit -am with an edited page, under PowerShell", VCS + " commit -am x",
             "unstaged", tool="PowerShell")
records_refuse("stage then commit: add -A and commit with an edited page",
             VCS + " add -A && " + VCS + " commit -m x", "unstaged")
records_refuse("stage then commit: add -A and commit with an edited page, under PowerShell",
             VCS + " add -A; " + VCS + " commit -m x", "unstaged", tool="PowerShell")
records_refuse("stage then commit: add . and commit with an edited page",
             VCS + " add . && " + VCS + " commit -m x", "unstaged")
records_refuse("stage then commit: add of the page and commit with an edited page",
             VCS + " add docs/records.md && " + VCS + " commit -m x", "unstaged")

# 2. No staged change to the page: allowed, though the base's page moved after the lane was cut.
records_allow("a commit that stages no page change, with the base's page moved on", VCS + " commit -m x",
              REC_LANES["product"])
records_allow("a commit that stages no page change, under PowerShell", VCS + " commit -m x",
              REC_LANES["product"], tool="PowerShell")
# The page edited and left unstaged is no commit of the page. A guard that refuses every commit after
# a lint run is a false alarm.
records_allow("a plain commit with an edited page left unstaged", VCS + " commit -m x", REC_LANES["unstaged"])
records_allow("a commit of a product file added alone, with an edited page left unstaged",
              VCS + " add src/app.py && " + VCS + " commit -m x", REC_LANES["unstaged"])
records_allow("an add of the page, with no commit", VCS + " add docs/records.md", REC_LANES["unstaged"])

# 3. The base's own page: allowed, as a merge of the base into the lane, or as a copy of its page.
records_allow("a merge commit that brings the base's page", VCS + " commit -m x", REC_LANES["merge"])
records_allow("a merge commit that brings the base's page, under PowerShell", VCS + " commit -m x",
              REC_LANES["merge"], tool="PowerShell")
records_allow("a commit of the base's own page copied over", VCS + " commit -m x", REC_LANES["copy-base"])
# Refused: a commit that deletes the page from the index, with no merge in progress. No merge is in progress to
# bring a page, so the commit holds no page the rule accepts.
records_refuse("a commit that deletes the page, with no merge in progress", VCS + " commit -m x", "deleted")
# The stage-then-commit forms must hold the same line. A guard that refuses whenever the page on disk
# differs from HEAD's, with no look at the base, refuses the merge and the remedy: both false alarms.
for _lane in ("merge", "copy-base"):
    records_allow("stage then commit: commit -am with the base's page, lane %s" % _lane, VCS + " commit -am x",
                  REC_LANES[_lane])
    records_allow("stage then commit: add -A and commit with the base's page, lane %s" % _lane,
                  VCS + " add -A && " + VCS + " commit -m x", REC_LANES[_lane])
records_allow("stage then commit: add -A and commit with the base's page, under PowerShell",
              VCS + " add -A; " + VCS + " commit -m x", REC_LANES["copy-base"], tool="PowerShell")

# 4. Nothing to compare, or git cannot be read: no hit.
records_allow("a commit in a repository with no page", VCS + " commit -m x", REC_NOPAGE)
records_allow("a commit of a staged page when the base cannot be read", VCS + " commit -m x", REC_NOBASE)
records_allow("a commit in a directory that is no repository", VCS + " commit -m x", NOGIT)
if os.name != "nt":
    records_allow("a commit of a staged page when git cannot answer", VCS + " commit -m x",
                  REC_LANES["staged"], env_path=GITBLIND)
else:
    skip_case("records-page: a commit of a staged page when git cannot answer is allowed", NO_STAND_IN)

# 5. Text that only names the page is no commit of it.
for _name, _command in (
    ("a message that names the page", VCS + ' commit -m "docs/records.md is rebuilt only at merge"'),
    ("a message that names the page, in a -F heredoc",
     VCS + " commit -F - <<'EOF'\nthe page docs/records.md is not mine to rebuild\nEOF"),
    ("an echo of a commit of the page", "echo '" + VCS + " commit -m x docs/records.md'"),
    ("a log of the page", VCS + " log --oneline -- docs/records.md"),
    ("a show of the page", VCS + " show origin/main:docs/records.md"),
    ("a read of the page", "cat docs/records.md"),
):
    records_allow(_name, _command, REC_LANES["product"])

# ---- the same two readings of a lone quote, a multi-line quoted message and a comment opener in a
# string, building-scanner-respects-strings: the guard reads the command for a commit, so a quote or an
# opener inside a message must neither hide a commit of the page nor invent one.
records_refuse("a commit of a staged page after a lone apostrophe", "echo don't\n" + VCS + " commit -m x",
             "staged")
records_refuse("a commit of a staged page after a comment opener inside a string",
             'echo "# note // /* x"\n' + VCS + " commit -m x", "staged")
records_refuse("a commit of a staged page with a multi-line quoted message",
             VCS + ' commit -m "first line\nsecond line"', "staged")
records_allow("an echo of a commit inside a multi-line quoted string, with a staged page",
              'echo "first\n' + VCS + ' commit -m x\nlast"', REC_LANES["staged"])

GEN, ADD_A, COMMIT_X = "python3 lint/hook_catalog.py", VCS + " add -A", VCS + " commit -m x"
# One chain runs the generator, then stages and commits. The hook reads before the chain runs, so the
# page on disk still equals HEAD's: the generator is what rewrites it. The generator is named by its
# script, alone, with --records-only, or by a path. `--check` writes nothing.
for _name, _command, _kw in (
    ("--records-only", GEN + " --records-only && " + ADD_A + " && " + COMMIT_X, {}),
    ("no flag", GEN + " && " + ADD_A + " && " + COMMIT_X, {}),
    ("a path", "python3 /home/dev/claude-settings/lint/hook_catalog.py --records-only && " + ADD_A + " && "
     + COMMIT_X, {}),
    ("--records-only, under PowerShell", GEN + " --records-only; " + ADD_A + "; " + COMMIT_X,
     {"tool": "PowerShell"}),
):
    records_refuse("a chain that runs the generator with %s, then add -A and commit, the page on disk equal to HEAD's"
                 % _name, _command, "product", **_kw)
records_allow("a chain that runs the generator with --check, then add -A and commit",
              GEN + " --check && " + ADD_A + " && " + COMMIT_X, REC_LANES["product"])
records_allow("a chain whose commit message names the generator",
              ADD_A + " && " + VCS + ' commit -m "ran python3 lint/hook_catalog.py --records-only"',
              REC_LANES["product"])
records_allow("a chain that only echoes the generator",
              'echo "' + GEN + ' --records-only" && ' + ADD_A + " && " + COMMIT_X, REC_LANES["product"])

# The base is a stale local `main` (origin/HEAD dangles), and the lane merged origin/main: its page is
# v1, which is origin/main's page, so it is allowed. A page that equals HEAD's, the base's or
# origin/<base>'s page passes. A hand-rebuilt page is still refused. The chain form from a clean lane is
# judged before the merge runs.
_dl = REC_DANGLE_LANES
records_allow("a merge commit that brings origin/main's page when origin/HEAD dangles", COMMIT_X, _dl["merge"])
records_allow("a merge commit that brings origin/main's page when origin/HEAD dangles, under PowerShell",
              COMMIT_X, _dl["merge"], tool="PowerShell")
records_allow("commit -am after a merge of origin/main when origin/HEAD dangles", VCS + " commit -am x",
              _dl["merge"])
records_allow("add -A and commit after a merge of origin/main when origin/HEAD dangles",
              ADD_A + " && " + COMMIT_X, _dl["merge"])
records_allow("a merge --no-commit of origin/main and a commit in one chain, origin/HEAD dangling",
              VCS + " merge --no-commit origin/main && " + COMMIT_X, _dl["fresh"])
records_refuse("a hand-rebuilt page after a merge when origin/HEAD dangles", COMMIT_X, _dl["rebuilt"])

# The page is untracked at HEAD (the base added it after the lane was cut). `commit -a` never stages an
# untracked file, so it commits no page. `add -A` and an add of the page do.
records_allow("commit -am when the page is untracked at HEAD", VCS + " commit -am x", REC_NEW_LANE)
records_allow("commit -am when the page is untracked at HEAD, under PowerShell", VCS + " commit -am x",
              REC_NEW_LANE, tool="PowerShell")
records_allow("a plain commit when the page is untracked at HEAD", COMMIT_X, REC_NEW_LANE)
records_refuse("add -A and commit when the page is untracked at HEAD", ADD_A + " && " + COMMIT_X, REC_NEW_LANE)
records_refuse("add of the page and commit when the page is untracked at HEAD",
             VCS + " add docs/records.md && " + COMMIT_X, REC_NEW_LANE)

# A commit that names its paths (`--` or --only) commits those paths and ignores the other staged
# entries, so a page staged earlier rides in on no such commit. Naming the page itself still refuses.
records_allow("a commit of src/app.py by path, with the page staged earlier", COMMIT_X + " -- src/app.py",
              REC_LANES["staged-edit"])
records_allow("a commit with --only of src/app.py, with the page staged earlier",
              VCS + " commit --only -m x src/app.py", REC_LANES["staged-edit"])
records_refuse("a plain commit with the page staged earlier and src/app.py edited", COMMIT_X, "staged-edit")
records_refuse("a commit by path that names the page, with the page staged earlier",
             COMMIT_X + " -- src/app.py docs/records.md", "staged-edit")

# First adoption: the base has no page, and the lane creates it. Allowed (the rule reads a base with no
# page as no hit). A limit, named in the decision's safety holes.
records_allow("a lane that creates the page where the base has none", COMMIT_X, REC_ADOPT_LANE)
records_allow("a chain that runs the generator, then add -A and commit, where the base has no page",
              GEN + " --records-only && " + ADD_A + " && " + COMMIT_X, REC_ADOPT_LANE)

# The generator is read by its command word (or the script of a python interpreter), never by a token that
# only names it. A reader, a linter, a log and a `--print` run write no page. A tool that runs it as its
# command word, by a path or through `env`, does.
records_allow("a chain that lints the generator, then add -A and commit",
              "ruff check lint/hook_catalog.py && " + ADD_A + " && " + COMMIT_X, REC_LANES["product"])
records_allow("a chain that reads the generator with cat, then add -A and commit",
              "cat lint/hook_catalog.py && " + ADD_A + " && " + COMMIT_X, REC_LANES["product"])
records_allow("a chain that logs the generator's history, then add -A and commit",
              VCS + " log --oneline -- lint/hook_catalog.py && " + ADD_A + " && " + COMMIT_X, REC_LANES["product"])
records_allow("a chain that runs the generator with --print, then add -A and commit",
              GEN + " --print && " + ADD_A + " && " + COMMIT_X, REC_LANES["product"])
records_refuse("a chain that runs the generator as its own command word, then add -A and commit",
             "./lint/hook_catalog.py && " + ADD_A + " && " + COMMIT_X, "product")
records_refuse("a chain that runs the generator through env, then add -A and commit",
             "env python3 lint/hook_catalog.py && " + ADD_A + " && " + COMMIT_X, "product")

# The rule acts only when the base page opens with the generated header. A hand-written base page is no
# hit: a staged edit of it, and a generator chain over it, pass.
records_allow("a commit of a staged page edit where the base page is hand-written", COMMIT_X,
              REC_PLAIN_LANES["staged"])
records_allow("a chain that runs the generator, then add -A and commit, where the base page is hand-written",
              GEN + " --records-only && " + ADD_A + " && " + COMMIT_X, REC_PLAIN_LANES["product"])

# ---- a merge commit's own page (decision records-index-at-merge: the page is rebuilt only at merge)
#
# A merge of origin/main brings the page of the base tip it merged, MERGE_HEAD's page. When origin/main
# holds a newer page, that page is neither HEAD's, the base tip's nor origin/<base>'s, and the merge commit
# holds it. The rule allows exactly that page, and only when MERGE_HEAD is a base tip on origin/<base>'s
# first-parent line, or when the lane shares unmerged history with its base (some best merge base of HEAD and
# MERGE_HEAD is not on origin/<base>). Any other page is refused.
#
# The scope is exact blob equality with MERGE_HEAD's page: a rebuilt page, the page of a branch merged off
# the first-parent line, and a page taken once the merge state is gone are refused.
RECORDS_AUTHOR = {"agent_id": "rec-auth1", "agent_type": "test-author"}
_mv = REC_MOVED_LANES
_mv_page = _rec_page(_mv["merge"])

# Allowed: the merge's own page, committed by a test-author or a plain session, in each form a merge is finished with.
records_allow("a test-author commit of the merge's own page, after origin/main moved on", VCS + " commit -m x",
              _mv["merge"], **RECORDS_AUTHOR)
records_allow("a test-author commit of the merge's own page, after origin/main moved on, under PowerShell",
              VCS + " commit -m x", _mv["merge"], tool="PowerShell", **RECORDS_AUTHOR)
records_allow("a plain session's commit of the merge's own page, after origin/main moved on", VCS + " commit -m x",
              _mv["merge"])
records_allow("a test-author commit -am of the merge's own page, after origin/main moved on",
              VCS + " commit -am x", _mv["merge"], **RECORDS_AUTHOR)
records_allow("a test-author add -A and commit of the merge's own page, after origin/main moved on",
              VCS + " add -A && " + VCS + " commit -m x", _mv["merge"], **RECORDS_AUTHOR)
records_allow("a test-author commit --no-edit of the merge's own page, after origin/main moved on",
              VCS + " commit --no-edit", _mv["merge"], **RECORDS_AUTHOR)
# Allowed: the page is in the tree before the chain runs, so the hook judges the page there. The chain's add
# and commit are the acts that follow.
records_allow("a test-author add -A and commit of MERGE_HEAD's page already in the tree, origin/main moved on",
              ADD_A + " && " + COMMIT_X, _mv["take"], **RECORDS_AUTHOR)
# Allowed: a product file staged with the merge's page. The product path is out of a test-author's role, so
# it is logged and never refused (decision builders-cannot-edit-tests).
records_allow("a test-author commit of the merge's own page with a clean product file staged",
              VCS + " commit -m x", _mv["product"], **RECORDS_AUTHOR)

# Refused: a page rebuilt by hand after the merge, a merge of a branch that is not the base, and a page staged
# after merge --quit, when no merge is in progress.
records_refuse("a test-author commit of a page rebuilt after the merge, origin/main moved on", VCS + " commit -m x",
             _mv["rebuilt"], **RECORDS_AUTHOR)
records_refuse("a test-author commit of a non-base merge's page, the feature branch's, origin/main moved on",
             VCS + " commit -m x", _mv["nonbase"], **RECORDS_AUTHOR)
records_refuse("a test-author commit of the merge's page after merge --quit, no merge in progress",
             VCS + " commit -m x", _mv["quit"], **RECORDS_AUTHOR)
# Allowed: the base's own page in a merge, with a product file staged. The test-author scope adds no refusal
# for a product path in a merge.
records_allow("a test-author merge commit of origin/main's page with a clean product file staged",
              VCS + " commit -m x", _mv["base"], **RECORDS_AUTHOR)
# Refused: a test-author's Edit of the page, under the test-author scope.
add("records-page: a test-author Edit of the merge's page is refused", "deny", rule="test-author-scope", tool="Edit",
    file_path=_mv_page, cwd=_mv["merge"], **RECORDS_AUTHOR)
# Allowed: writing MERGE_HEAD's page into the tree, with no commit.
records_allow("a test-author writes MERGE_HEAD's page into the tree, with no commit, origin/main moved on",
              VCS + " show MERGE_HEAD:docs/records.md > docs/records.md", _mv["take"], **RECORDS_AUTHOR)
# Refused: the page of a branch whose tip is in origin/main's history, off its first-parent line. The merge of
# that tip is not a merge of a base tip, so the page it brings is not the base's own page.
records_refuse("a test-author commit of a page from a branch merged into origin/main off its first-parent line",
             VCS + " commit -m x", REC_ANC_LANE, **RECORDS_AUTHOR)

# A stacked base's merge: the base is cut from main, never merged into it, and the lane is cut from it. The base
# moves on and the lane merges it again, so the merge brings the base's page and the lane shares unmerged history
# with that base. Allowed. A page the lane wrote by hand, and a commit after `merge --quit`, stay refused.
records_allow("a lane's merge of its unmerged stacked base, which moved on, with the base's page staged",
              VCS + " commit -m x", REC_STACK_LANES["merge"])
records_refuse("a lane's merge of its unmerged stacked base, with a page rebuilt by hand",
               VCS + " commit -m x", REC_STACK_LANES["rebuilt"])
records_refuse("a lane's commit of the stacked base's page after merge --quit, no merge in progress",
               VCS + " commit -m x", REC_STACK_LANES["quit"])

# A criss-cross stacked base: the lane and its base each merged origin/main at a different commit, so the lane's merge
# has two best merge bases, S1 (off origin/main) and M1 (on it). Plain merge-base prints M1, which is on origin/main, so
# the check must read every best base, not that one. The base's own page passes. A page written by hand is refused.
records_allow("a lane's merge of a criss-cross stacked base, with the base's page staged", VCS + " commit -m x",
              REC_CRISS_LANES["merge"])
records_refuse("a lane's merge of a criss-cross stacked base, with a page written by hand", VCS + " commit -m x",
               REC_CRISS_LANES["hand"])
# A lane cut from main that merges an unrelated unmerged branch. Both best merge bases are on origin/main, so no base is
# off main and the branch's page is refused.
records_refuse("a lane's merge of an unrelated unmerged branch, whose merge bases are both on origin/main",
               VCS + " commit -m x", REC_UNREL_LANE)
# A failed is-ancestor read gives no stacked pass. origin/main is missing, so `merge-base --is-ancestor` exits 128, and
# the first-parent read fails too. The commit is refused, though a branch's page is staged. An exit of 0 or 1 is a
# read that answered.
records_refuse("a lane's merge of a feature page, with no origin/main, so the is-ancestor read fails",
               VCS + " commit -m x", REC_NOORIGIN_LANE)

# =========================================================================== 5d. conflict markers
#
# `conflict-markers`. A Bash `git commit` is refused when the commit would hold a git conflict marker:
# one file's added lines hold all three of a `<<<<<<< ` line, a line of exactly `=======`, and a
# `>>>>>>> ` line. Only the leftover-marker findings of `git diff --check` count, never its whitespace
# findings. Incident: a conflict-fix script failed, and the next command in its chain
# (`fix && git add -A && git commit`) committed the markers.
#
# THE SEAM. The hook runs BEFORE the shell chain, so it cannot see what an earlier step does to the tree.
# A commit, or a `--continue`, is judged on the index, plus the working-tree files its adds, `commit -a`
# or `commit <path>` cover. A blind step (one that can change the tree) before a commit gives no hit,
# unless a push follows the commit in the call and the commit covers a triplet already in the tree. A git
# step in the chain that makes a conflict is refused. A `git push` is judged on the net change it sends: upstream..HEAD, or the
# refspec, or HEAD's range when the refspec does not resolve. A fence does not exempt a full triplet. A
# read that fails (no HEAD yet) is no hit.
#
# NO CONTEXT SKIPS A MARKER. Git writes a marker inside a string, a comment or a template literal too, so
# a lone apostrophe, a multi-line template literal and a comment opener inside a string do not hide one
# (building-scanner-respects-strings).
