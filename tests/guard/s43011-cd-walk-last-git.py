# section 43011
#
# Cases for the folder a git write runs in, read off the cd walk (_run_dir in hooks/guard_core.py). A git
# segment runs where the shell stands when it runs, so a discard is judged from the folder the shell is in
# when that discard runs, not from the folder a later git segment stands in.

# A DISCARD BEFORE A CD TO A CLEAN FOLDER. The reset runs in the dirty folder. The cd after it moves the shell
# to a clean folder, where the status is a read. The call ends in the dirty folder again.
FAMILY = "shared-tree"
# RED. The reset runs in the dirty folder, so the call denies. Judged from the folder of the last git
# segment (the clean one), the call allows.
sh("cd-walk: a reset in a dirty folder, then a status in a clean one, then a cd back to the dirty folder, denies",
   "cd " + slash(SUBJDIRTY) + " && " + VCS + " reset --hard HEAD; cd " + slash(SUBJCLEAN) + " && " + VCS
   + " status; cd " + slash(SUBJDIRTY), "deny", "shared-tree", cwd=NOGIT)
# RED. The same shape with the reset under watch. The walk reads watch as a wrapper, so the reset is a git segment.
sh("cd-walk: a watch-wrapped reset in a dirty folder, then a status in a clean one, then a cd back, denies",
   "cd " + slash(SUBJDIRTY) + " && watch " + VCS + " reset --hard HEAD; cd " + slash(SUBJCLEAN) + " && " + VCS
   + " status; cd " + slash(SUBJDIRTY), "deny", "shared-tree", cwd=NOGIT)
# RED. The same shape with the reset under gtimeout, the macOS name of timeout.
sh("cd-walk: a gtimeout-wrapped reset in a dirty folder, then a status in a clean one, then a cd back, denies",
   "cd " + slash(SUBJDIRTY) + " && gtimeout 5 " + VCS + " reset --hard HEAD; cd " + slash(SUBJCLEAN) + " && "
   + VCS + " status; cd " + slash(SUBJDIRTY), "deny", "shared-tree", cwd=NOGIT)
# RED, A FALSE ALARM. The mirror shape. The reset runs in the clean folder, where a reset of a clean tree is
# allowed. The status after the cd is in the dirty folder, and the call ends in the clean one. Judged from the
# folder of the last git segment (the dirty one), the reset is refused.
sh("cd-walk: a reset in a clean folder, then a status in a dirty one, then a cd back to the clean folder, allows",
   "cd " + slash(SUBJCLEAN) + " && " + VCS + " reset --hard HEAD; cd " + slash(SUBJDIRTY) + " && " + VCS
   + " status; cd " + slash(SUBJCLEAN), "allow", cwd=NOGIT)
# GREEN. A reset under watch in a dirty folder is a discard, so it denies, as a bare reset does.
sh("cd-walk: a watch-wrapped reset in a dirty folder denies", "watch " + VCS + " reset --hard HEAD",
   "deny", "shared-tree", cwd=SUBJDIRTY)
# GREEN. gtimeout is a wrapper like timeout, so a reset under it in a dirty folder denies.
sh("cd-walk: a gtimeout-wrapped reset in a dirty folder denies", "gtimeout 5 " + VCS + " reset --hard HEAD",
   "deny", "shared-tree", cwd=SUBJDIRTY)

# A WRAPPER IN THE VERDICT PIPE. verdict-pipe reads the verdict stage through the command wrappers, as timeout
# is one. gtimeout is the macOS name of timeout, so a pipe out of it hides a verdict the same way.
FAMILY = "stream"
# The verdict pipe reads through gtimeout as it reads through timeout. This case pins that reading.
sh("verdict-pipe: gtimeout 60 verdict pytest piped to tail denies, as timeout 60 does",
   "gtimeout 60 verdict pytest | tail -3", "deny", VERDICT_PIPE, cwd=NOGIT)
