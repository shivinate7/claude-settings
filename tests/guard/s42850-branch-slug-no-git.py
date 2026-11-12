# section 42850
FAMILY = "branch-slug-no-git"
#
# A NEW BRANCH NAME NEVER HOLDS THE WORD git. Claude Code's own worktree check refuses an agent's git
# command that names such a branch, so a lane that makes one cannot run its own checkout or push. The rule
# refuses a creation of such a name in every form that creates a branch: checkout -b, -B and --orphan;
# switch -c and -C; branch <new>; worktree add -b; and a push to a destination the clone holds no
# remote-tracking ref for. A branch that already exists keeps its name, so a switch to it and a push to it
# pass, and the word in quoted text is not a call.
RULE = "branch-slug-no-git"
BSORIGIN = os.path.join(ROOT, "branchslug-origin.git")
BSREPO = os.path.join(ROOT, "branchslug-repo")


def _build_branch_slug():
    """One clone of a bare origin, on lane/slug-rule. The origin and the clone both hold git-old-lane, an
    existing branch whose name holds the word, so the controls name a real one. Nothing holds fix-git-thing
    or fix-git-new, so each refused form names a branch that does not exist yet. Each state is read back
    with git before a case relies on it."""
    make_repo(BSREPO, {"f.txt": "one\n"})
    _base_git(ROOT, "init", "-q", "--bare", BSORIGIN)
    _base_git(BSREPO, "remote", "add", "origin", slash(BSORIGIN))
    _base_git(BSREPO, "branch", "git-old-lane")
    _base_git(BSREPO, "push", "-q", "origin", "git-old-lane")
    _base_git(BSREPO, "checkout", "-q", "-b", "lane/slug-rule")
    for args, want in ((("symbolic-ref", "-q", "HEAD"), "refs/heads/lane/slug-rule"),
                       (("config", "--get", "remote.origin.url"), slash(BSORIGIN))):
        got = run_vcs(BSREPO, *args).stdout.strip()
        if got != want:
            sys.exit("fixture setup failed in build_fixtures: git %s in %r reads %r, want %r"
                     % (" ".join(args), BSREPO, got, want))
    for ref, present in (("refs/heads/git-old-lane", True),
                         ("refs/remotes/origin/git-old-lane", True),
                         ("refs/heads/fix-git-thing", False),
                         ("refs/remotes/origin/fix-git-new", False)):
        found = run_vcs(BSREPO, "show-ref", "--verify", "-q", ref).returncode == 0
        if found != present:
            sys.exit("fixture setup failed in build_fixtures: %s exists=%s in %r, want %s"
                     % (ref, found, BSREPO, present))


lazy_fixture([BSREPO, BSORIGIN], _build_branch_slug)

# THE REFUSED FORMS. Each one creates a branch whose name holds the word, so the rule decides on the name.
sh("branch-slug: checkout -b of a new name holding git is refused",
   VCS + " checkout -b fix-git-thing", "deny", RULE, cwd=BSREPO)
sh("branch-slug: checkout -B of a new name holding git is refused",
   VCS + " checkout -B fix-git-thing", "deny", RULE, cwd=BSREPO)
sh("branch-slug: checkout --orphan of a new name holding git is refused",
   VCS + " checkout --orphan fix-git-thing", "deny", RULE, cwd=BSREPO)
sh("branch-slug: switch -c of a new name holding git is refused",
   VCS + " switch -c fix-git-thing", "deny", RULE, cwd=BSREPO)
sh("branch-slug: branch <new> of a name holding git is refused",
   VCS + " branch fix-git-thing", "deny", RULE, cwd=BSREPO)
sh("branch-slug: worktree add -b of a new name holding git is refused",
   VCS + " worktree add -b fix-git-thing ../fix-git-thing-wt", "deny", RULE, cwd=BSREPO)
sh("branch-slug: a push to a new destination holding git is refused",
   VCS + " push origin HEAD:fix-git-new", "deny", RULE, cwd=BSREPO)
sh("branch-slug: the word at the start of a new name is refused",
   VCS + " checkout -b git-fix-thing", "deny", RULE, cwd=BSREPO)
sh("branch-slug: the word at the end of a new name is refused",
   VCS + " checkout -b fix-thing-git", "deny", RULE, cwd=BSREPO)
sh("branch-slug: the word after a slash in a new name is refused",
   VCS + " checkout -b lane/git-cleanup", "deny", RULE, cwd=BSREPO)

# THE CONTROLS. Each passes on the old code and must keep passing: a name without the word, an existing
# branch that holds it, and the word only as quoted text.
sh("branch-slug: checkout -b of a new name without the word is allowed",
   VCS + " checkout -b fix-slug-thing", "allow", cwd=BSREPO)
sh("branch-slug: switch -c of a new name without the word is allowed",
   VCS + " switch -c fix-slug-thing", "allow", cwd=BSREPO)
sh("branch-slug: branch <new> of a name without the word is allowed",
   VCS + " branch fix-slug-thing", "allow", cwd=BSREPO)
sh("branch-slug: worktree add -b of a name without the word is allowed",
   VCS + " worktree add -b fix-slug-thing ../fix-slug-thing-wt", "allow", cwd=BSREPO)
sh("branch-slug: checkout of an existing branch holding git keeps its name",
   VCS + " checkout git-old-lane", "allow", cwd=BSREPO)
sh("branch-slug: switch to an existing branch holding git keeps its name",
   VCS + " switch git-old-lane", "allow", cwd=BSREPO)
sh("branch-slug: worktree add of an existing branch holding git keeps its name",
   VCS + " worktree add ../git-old-wt git-old-lane", "allow", cwd=BSREPO)
sh("branch-slug: a push to an existing remote branch holding git is allowed",
   VCS + " push origin HEAD:git-old-lane", "allow", cwd=BSREPO)
sh("branch-slug: a push to a new destination without the word is allowed",
   VCS + " push origin HEAD:fix-slug-new", "allow", cwd=BSREPO)
sh("branch-slug: the word inside quoted echo text is not a branch call",
   "echo 'git checkout -b fix-git-thing'", "allow", cwd=BSREPO)
