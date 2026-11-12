# section 43012
FAMILY = "shared-tree"
#
# A discard with `git -C` takes its folder from the shell's own walk, read against the folder the shell stands in
# when that segment runs, as a bare git segment after a cd is. The cwd here is a folder that is no checkout, so a
# -C read against the cwd finds no tree at all.
# The command names only ROOT, so the lazy builder would not build the two checkouts for these cases: build them here.
materialize(SUBJDIRTY)
materialize(SUBJCLEAN)

# RED on a -C read against the call's cwd: the reset would be judged in NOGIT/subjdirty, which is not a checkout.
# The shell stands in ROOT when the reset runs, and there subjdirty is a checkout with uncommitted work.
sh("cd-walk: a reset with git -C into a dirty folder, after a cd to the folder above it, denies",
   "cd " + slash(ROOT) + " && " + VCS + " -C " + os.path.basename(SUBJDIRTY) + " reset --hard HEAD",
   "deny", "shared-tree", cwd=NOGIT)
# GREEN. The same shape on the clean checkout: a reset of a clean tree is allowed.
sh("cd-walk: a reset with git -C into a clean folder, after the same cd, allows",
   "cd " + slash(ROOT) + " && " + VCS + " -C " + os.path.basename(SUBJCLEAN) + " reset --hard HEAD",
   "allow", cwd=NOGIT)
