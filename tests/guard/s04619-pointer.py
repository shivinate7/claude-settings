# section 4619
FAMILY = "pointer"
#
# The pointer checkout is the one checkout whose HEAD decides which copy of the rules and the guards
# every session on this machine runs. Its HEAD stays `main`.
#
# BOTH DIRECTIONS ARE PINNED, and the GREEN half carries the weight here: a rule this broad would
# stop every lane from switching a branch anywhere. So the same two commands are run in a
# non-pointer checkout and in a real linked worktree of the pointer checkout itself, and both must
# be allowed.

sh("pointer: checkout of a branch in the pointer checkout is refused",
   VCS + " checkout somebranch", "deny", "pointer-head", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: switch of a branch in the pointer checkout is refused",
   VCS + " switch somebranch", "deny", "pointer-head", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: a new branch with -b is refused",
   VCS + " checkout -b somebranch", "deny", "pointer-head", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: a new branch with -b and a start point is refused",
   VCS + " checkout -b somebranch origin/main", "deny", "pointer-head", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: -B resets and switches, so it is refused",
   VCS + " checkout -B somebranch", "deny", "pointer-head", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: an orphan branch is refused",
   VCS + " checkout --orphan somebranch", "deny", "pointer-head", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: switch -c is the new-branch form of switch",
   VCS + " switch -c somebranch", "deny", "pointer-head", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: detaching leaves no branch named at all",
   VCS + " checkout --detach", "deny", "pointer-head", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: switch -d detaches too",
   VCS + " switch -d somebranch", "deny", "pointer-head", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: the previous-branch shorthand is a switch",
   VCS + " checkout -", "deny", "pointer-head", cwd=PTRMAIN, config=PTRCFG)
# A remote-tracking ref detaches HEAD rather than putting it on `main`, so the exemption for the
# bare name `main` must not reach it.
sh("pointer: origin/main detaches, so it is not the main exemption",
   VCS + " checkout origin/main", "deny", "pointer-head", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: a subdirectory of the pointer checkout is still the pointer checkout",
   "cd " + slash(os.path.join(PTRMAIN, "docs")) + " && " + VCS + " switch somebranch", "deny",
   "pointer-head", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: -C reaches the pointer checkout from anywhere",
   VCS + " -C " + slash(PTRMAIN) + " switch somebranch", "deny", "pointer-head", cwd=NOGIT,
   config=PTRCFG)
# A switch named by its own -C is judged in the pointer checkout, though the last git segment names a folder
# that is no checkout. The pointer rule must read the -C segment's folder, not only the bare segments' folders.
sh("pointer: a switch with -C into the pointer checkout, then a status in a folder that is no checkout, is refused",
   VCS + " -C " + slash(PTRMAIN) + " switch somebranch; " + VCS + " -C " + slash(NOGIT) + " status",
   "deny", "pointer-head", cwd=NOGIT, config=PTRCFG)
# GREEN. The same shape with the linked worktree of the pointer checkout, whose HEAD is not the pointer's.
sh("pointer: a switch with -C into the linked worktree, then the same status, is allowed",
   VCS + " -C " + slash(PTRWT) + " switch somebranch; " + VCS + " -C " + slash(NOGIT) + " status",
   "allow", cwd=NOGIT, config=PTRCFG)

# THE MOVE TO MAIN IS THE REPAIR. A deny there would wall off the one command that restores the
# invariant this rule exists to protect.
sh("pointer: a move back to main restores the invariant and passes",
   VCS + " checkout main", "allow", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: switch main passes for the same reason",
   VCS + " switch main", "allow", cwd=PTRMAIN, config=PTRCFG)
# refusal-vs-rule (pointer-head, recovery-independent-of-state): a move TO main is the recovery act and
# passes. A reset of main onto origin/main is a move to main too. The pin runs both on main and in a
# checkout that is off main, so the verdict cannot rest on HEAD already naming main.
sh("pointer: switch -C main onto origin/main passes, from a checkout on main",
   VCS + " switch -C main origin/main", "allow", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: checkout -B main onto origin/main passes, from a checkout on main",
   VCS + " checkout -B main origin/main", "allow", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: switch -C main onto origin/main passes, from a checkout off main",
   VCS + " switch -C main origin/main", "allow", cwd=PTROFF, config=PTROFFCFG)
# Near misses, refused: a detach names no branch, so the exemption for main does not reach it, and a
# reset onto any other branch is a new branch.
sh("pointer: switch --detach main detaches, so it is refused", VCS + " switch --detach main", "deny",
   "pointer-head", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: switch -C of another branch onto origin/main is refused", VCS + " switch -C somebranch origin/main",
   "deny", "pointer-head", cwd=PTRMAIN, config=PTRCFG)
# The reset is a move to main only when it drops nothing, and only origin/main can say so. Local main
# one commit ahead of origin/main: the reset would drop that commit, so it is refused.
sh("pointer: switch -C main onto origin/main is refused when local main holds a commit origin/main lacks",
   VCS + " switch -C main origin/main", "deny", "pointer-head", cwd=PTRAHEAD, config=PTRAHEADCFG)
sh("pointer: checkout -B main onto origin/main is refused when local main holds a commit origin/main lacks",
   VCS + " checkout -B main origin/main", "deny", "pointer-head", cwd=PTRAHEAD, config=PTRAHEADCFG)
# No origin/main at all: nothing shows the reset drops no commit, so it is refused.
sh("pointer: switch -C main onto origin/main is refused when origin/main does not exist",
   VCS + " switch -C main origin/main", "deny", "pointer-head", cwd=PTRNOORIGIN,
   config=PTRNOORIGINCFG)
sh("pointer: checkout -B main onto origin/main is refused when origin/main does not exist",
   VCS + " checkout -B main origin/main", "deny", "pointer-head", cwd=PTRNOORIGIN,
   config=PTRNOORIGINCFG)

# READS NEVER FIRE.
sh("pointer: listing branches only reads", VCS + " branch --list", "allow", cwd=PTRMAIN,
   config=PTRCFG)
sh("pointer: status only reads", VCS + " status", "allow", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: a bare checkout names no branch and moves no HEAD", VCS + " checkout", "allow",
   cwd=PTRMAIN, config=PTRCFG)
sh("pointer: worktree add is the remedy, not the act",
   VCS + " worktree add -b somebranch " + slash(os.path.join(ROOT, "newlane")), "allow",
   cwd=PTRMAIN, config=PTRCFG)

# THE RULE IS NOT TOO BROAD. The same two commands in another checkout, and in a real linked
# worktree of the pointer checkout, are allowed.
sh("pointer: checkout of a branch in another checkout is allowed",
   VCS + " checkout somebranch", "allow", cwd=GITMAIN, config=PTRCFG)
sh("pointer: switch of a branch in another checkout is allowed",
   VCS + " switch somebranch", "allow", cwd=GITMAIN, config=PTRCFG)
sh("pointer: checkout of a branch in a worktree of the pointer checkout is allowed",
   VCS + " checkout somebranch", "allow", cwd=PTRWT, config=PTRCFG)
sh("pointer: switch of a branch in a worktree of the pointer checkout is allowed",
   VCS + " switch somebranch", "allow", cwd=PTRWT, config=PTRCFG)
sh("pointer: a branch switch in a directory that is no git tree is allowed",
   VCS + " switch somebranch", "allow", cwd=NOGIT, config=PTRCFG)

# THE PATH-OPERATION ARMS OF THIS RULE, REACHED. Rule 1 answers first for a dirty or
# file-shaped pathspec, so these two are the cases where rule 1b's own `--` and `--theirs` arms
# are what decides. `docs` is a real, clean, extensionless directory in the fixture, which rule 1
# reads as neither a path nor a discard, so the call arrives at rule 1b untouched.
sh("pointer: a double dash names a path, and no HEAD moves", VCS + " checkout -- docs", "allow",
   cwd=PTRMAIN, config=PTRCFG)
sh("pointer: --theirs with an extensionless path is no branch switch",
   VCS + " checkout --theirs docs", "allow", cwd=PTRMAIN, config=PTRCFG)

# THE GIT DIRECTORY IS WHERE HEAD LIVES. MEASURED 2026-09-19 with real git: from an unrelated
# directory, `git --git-dir=<X>/.git switch other` moved HEAD inside X, with no `-C`, no `cd` and
# no `--work-tree` on the line. So the rule reads `--git-dir`, and the comparison is between git
# directories rather than between top levels.
PTR_GITDIR = slash(os.path.join(PTRMAIN, ".git"))
OTHER_GITDIR = slash(os.path.join(GITMAIN, ".git"))
PTRWT_GITDIR = slash(os.path.join(PTRMAIN, ".git", "worktrees", "ptrlane"))

sh("pointer: --git-dir reaches the pointer HEAD from an unrelated directory",
   VCS + " --git-dir=" + PTR_GITDIR + " switch somebranch", "deny", "pointer-head", cwd=NOGIT,
   config=PTRCFG)
sh("pointer: the spaced --git-dir form is the same act",
   VCS + " --git-dir " + PTR_GITDIR + " checkout somebranch", "deny", "pointer-head", cwd=NOGIT,
   config=PTRCFG)
sh("pointer: --git-dir with a move to main keeps the exemption",
   VCS + " --git-dir=" + PTR_GITDIR + " checkout main", "allow", cwd=NOGIT, config=PTRCFG)
sh("pointer: --git-dir naming another clone is allowed",
   VCS + " --git-dir=" + OTHER_GITDIR + " switch somebranch", "allow", cwd=NOGIT, config=PTRCFG)
# A linked worktree keeps its own HEAD in its own per-worktree git directory, so naming that
# directory is not naming the primary checkout's HEAD.
sh("pointer: --git-dir naming a worktree of the pointer clone is allowed",
   VCS + " --git-dir=" + PTRWT_GITDIR + " switch somebranch", "allow", cwd=NOGIT, config=PTRCFG)
sh("pointer: a --git-dir that is not there fires nothing",
   VCS + " --git-dir=" + slash(os.path.join(ROOT, "nosuchgitdir")) + " switch somebranch",
   "allow", cwd=NOGIT, config=PTRCFG)
# `--work-tree` retargets the FILES and leaves HEAD where the call runs, so it must NOT be read as
# a pointer HEAD move. Run from a directory that is no git tree, this names the pointer checkout's
# files and no checkout's HEAD.
sh("pointer: --work-tree alone moves no HEAD in the pointer checkout",
   VCS + " --work-tree=" + slash(PTRMAIN) + " switch somebranch", "allow", cwd=NOGIT,
   config=PTRCFG)

# FAIL OPEN. An unreadable pointer means no rule, never a broken session.
sh("pointer: a rules file with no pointer line fires nothing",
   VCS + " switch somebranch", "allow", cwd=PTRMAIN, config=PTRBADCFG)
sh("pointer: a pointer naming a directory that is gone fires nothing",
   VCS + " switch somebranch", "allow", cwd=PTRMAIN, config=PTRGONECFG)
sh("pointer: no global rules file at all fires nothing",
   VCS + " switch somebranch", "allow", cwd=PTRMAIN, config=PTRNOCFG)


# =========================================================================== 1b. the pointer's own files
