# section 43013
#
# Cases for the folder a wrapped script segment runs in (judge_shell rule 1, hooks/guard.py). A script that
# `sh -c '...'` runs takes the folder of the outer segment it came from. The fixtures and the discarding write
# are those of section 43011: a dirty checkout, a clean checkout, and a reset --hard.
FAMILY = "shared-tree"
materialize(SUBJDIRTY)
materialize(SUBJCLEAN)

# A WRAPPED DISCARD TAKES THE FOLDER OF ITS OUTER SEGMENT. The reset runs in the dirty folder the cd names.
sh("cd-walk: a reset in sh -c after a cd into a dirty folder denies",
   "cd " + slash(SUBJDIRTY) + " && sh -c '" + VCS + " reset --hard HEAD'", "deny", "shared-tree", cwd=NOGIT)
# GREEN. The same wrapped reset after a cd into a clean folder is a reset of a clean tree, so it allows.
sh("cd-walk: a reset in sh -c after a cd into a clean folder allows",
   "cd " + slash(SUBJCLEAN) + " && sh -c '" + VCS + " reset --hard HEAD'", "allow", cwd=NOGIT)
# A cd after the wrapped discard moves the shell only for the segments after it. The reset still runs in the
# dirty folder, so the call denies.
sh("cd-walk: a reset in sh -c in a dirty folder, then a cd to a clean folder, denies",
   "cd " + slash(SUBJDIRTY) + " && sh -c '" + VCS + " reset --hard HEAD'; cd " + slash(SUBJCLEAN),
   "deny", "shared-tree", cwd=NOGIT)
