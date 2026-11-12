# section 42850
FAMILY = "branch-slug-no-git"
#
# A NEW BRANCH NAME NEVER HOLDS THE WORD git. Claude Code's own worktree check refuses an agent's git
# command that names such a branch, so a lane that makes one cannot run its own checkout or push. The rule
# refuses a creation of such a name in every form that creates a branch: checkout -b, -B and --orphan;
# switch -c, -C, --create, --force-create and --orphan; branch <new>; worktree add -b and -B; and a push to a
# destination the clone holds no remote-tracking ref for. A branch that already exists keeps its name, so a
# switch to it and a push to it pass, and the word in quoted text is not a call. A creation from origin/<name>
# is an existing branch brought local, so it passes too, and a refused push says to fetch origin and retry.
RULE = "branch-slug-no-git"
BSORIGIN = os.path.join(ROOT, "branchslug-origin.git")
BSREPO = os.path.join(ROOT, "branchslug-repo")


def _build_branch_slug():
    """One clone of a bare origin, on lane/slug-rule. The origin and the clone both hold git-old-lane, an
    existing branch whose name holds the word, so the controls name a real one. fix-git-remote is a branch
    on origin that the clone holds only as origin/fix-git-remote. git-local-only is a local branch that was
    never pushed. Nothing holds fix-git-thing or fix-git-new, so each refused form names a branch that does
    not exist yet. Each state is read back with git before a case relies on it."""
    make_repo(BSREPO, {"f.txt": "one\n"})
    _base_git(ROOT, "init", "-q", "--bare", BSORIGIN)
    _base_git(BSREPO, "remote", "add", "origin", slash(BSORIGIN))
    _base_git(BSREPO, "branch", "git-old-lane")
    _base_git(BSREPO, "push", "-q", "origin", "git-old-lane")
    _base_git(BSREPO, "checkout", "-q", "-b", "lane/slug-rule")
    _base_git(BSREPO, "push", "-q", "origin", "lane/slug-rule:refs/heads/fix-git-remote")
    _base_git(BSREPO, "branch", "git-local-only")
    for args, want in ((("symbolic-ref", "-q", "HEAD"), "refs/heads/lane/slug-rule"),
                       (("config", "--get", "remote.origin.url"), slash(BSORIGIN))):
        got = run_vcs(BSREPO, *args).stdout.strip()
        if got != want:
            sys.exit("fixture setup failed in build_fixtures: git %s in %r reads %r, want %r"
                     % (" ".join(args), BSREPO, got, want))
    for ref, present in (("refs/heads/git-old-lane", True),
                         ("refs/remotes/origin/git-old-lane", True),
                         ("refs/heads/fix-git-thing", False),
                         ("refs/remotes/origin/fix-git-new", False),
                         ("refs/remotes/origin/fix-git-remote", True),
                         ("refs/heads/fix-git-remote", False),
                         ("refs/heads/git-local-only", True),
                         ("refs/remotes/origin/git-local-only", False)):
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

# THE START POINT NAMES THE REMOTE BRANCH. fix-git-remote is on origin, and the clone holds it only as
# origin/fix-git-remote. A new local branch of that name, made from that remote branch, is an existing branch
# brought local, so it passes. With no start point, the same name is a new branch and is still refused.
sh("branch-slug: checkout -b of a name made from origin/<same name> is allowed",
   VCS + " checkout -b fix-git-remote origin/fix-git-remote", "allow", cwd=BSREPO)
sh("branch-slug: switch -c --track of a name made from origin/<same name> is allowed",
   VCS + " switch -c fix-git-remote --track origin/fix-git-remote", "allow", cwd=BSREPO)
sh("branch-slug: worktree add -b of a name made from origin/<same name> is allowed",
   VCS + " worktree add -b fix-git-remote ../fix-git-remote-wt origin/fix-git-remote", "allow", cwd=BSREPO)
sh("branch-slug: branch <name> made from origin/<same name> is allowed",
   VCS + " branch fix-git-remote origin/fix-git-remote", "allow", cwd=BSREPO)
sh("branch-slug: checkout -b with no start point of a name the clone holds only on origin is refused",
   VCS + " checkout -b fix-git-remote", "deny", RULE, cwd=BSREPO)

# A PUSH OF A LOCAL BRANCH THAT EXISTS. git-local-only is held here and was never pushed, so its first push
# names no new branch. A push to a name held neither locally nor on origin is still refused, and the refusal
# tells Claude to fetch origin and retry: the branch may exist on origin, which this clone has not fetched.
sh("branch-slug: the first push -u of an existing local branch holding git is allowed",
   VCS + " push -u origin git-local-only", "allow", cwd=BSREPO)
sh("branch-slug: a refused push to a new name holding git says to fetch origin and retry",
   VCS + " push origin HEAD:fix-git-new", "deny", RULE, carries="fetch", cwd=BSREPO)

# RULED ALLOWS THE FIRST RUN DID NOT NAME. checkout -B of an existing local branch resets it and names no new
# branch. branch -d names a branch to delete, not one to create. A -- pathspec after a creation names files.
sh("branch-slug: checkout -B of an existing local branch holding git keeps its name",
   VCS + " checkout -B git-old-lane", "allow", cwd=BSREPO)
sh("branch-slug: branch -d of a name holding git is not a creation",
   VCS + " branch -d fix-git-gone", "allow", cwd=BSREPO)
sh("branch-slug: git -C <dir> checkout -b of a new name holding git is refused",
   VCS + " -C " + slash(BSREPO) + " checkout -b fix-git-thing", "deny", RULE, cwd=BSREPO)
sh("branch-slug: a -- pathspec holding git after a new name without the word is not a name",
   VCS + " checkout -b fix-slug-thing -- git-notes.md", "allow", cwd=BSREPO)

# PUSHES THAT NAME NO BRANCH TO CREATE. A glob, a colon delete, --delete, --all and a shell expansion in the
# spec each name no new branch this rule reads, so each passes.
sh("branch-slug: a push with a glob spec holding git is not read",
   VCS + " push origin 'fix-git-*'", "allow", cwd=BSREPO)
sh("branch-slug: a push that deletes with a colon spec holding git is not read",
   VCS + " push origin :fix-git-gone", "allow", cwd=BSREPO)
sh("branch-slug: a push with --delete of a name holding git is not read",
   VCS + " push --delete origin fix-git-gone", "allow", cwd=BSREPO)
sh("branch-slug: a push with --all is not read",
   VCS + " push --all origin", "allow", cwd=BSREPO)
sh("branch-slug: a push whose spec holds a shell expansion is not read",
   VCS + ' push origin "HEAD:$(printf fix-git-x)"', "allow", cwd=BSREPO)

# THE OTHER CREATE FORMS, REFUSED. Each names a new branch that holds the word, in a form the rows above do
# not cover.
sh("branch-slug: switch -C of a new name holding git is refused",
   VCS + " switch -C fix-git-thing", "deny", RULE, cwd=BSREPO)
sh("branch-slug: switch --create of a new name holding git is refused",
   VCS + " switch --create fix-git-thing", "deny", RULE, cwd=BSREPO)
sh("branch-slug: switch --force-create of a new name holding git is refused",
   VCS + " switch --force-create fix-git-thing", "deny", RULE, cwd=BSREPO)
sh("branch-slug: switch --orphan of a new name holding git is refused",
   VCS + " switch --orphan fix-git-thing", "deny", RULE, cwd=BSREPO)
sh("branch-slug: worktree add -B of a new name holding git is refused",
   VCS + " worktree add -B fix-git-thing ../fix-git-thing-wt", "deny", RULE, cwd=BSREPO)
sh("branch-slug: checkout -fb of a new name holding git is refused",
   VCS + " checkout -fb fix-git-thing", "deny", RULE, cwd=BSREPO)
