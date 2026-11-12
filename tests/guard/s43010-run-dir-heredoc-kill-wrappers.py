# section 43010
#
# Cases for three readers in hooks/guard_core.py and hooks/guard_kill.py. Each gap has a RED case,
# which main gets wrong, and a GREEN control, which main gets right and the fix must keep.

# THE FOLDER A COMMAND RUNS IN (_run_dir). A git segment runs where the shell stands when it runs. A
# `cd` after it moves the shell only for the segments after it.
FAMILY = "pointer"

# RED. The switch runs in the pointer checkout, before the cd. _run_dir reads the last cd of the call, so
# the switch is judged in NOGIT and allows.
sh("run-dir: a switch in the pointer checkout, then a cd out of it, denies, because the switch runs in the pointer",
   VCS + " switch somebranch; cd " + slash(NOGIT), "deny", "pointer-head", cwd=PTRMAIN, config=PTRCFG)
# GREEN. The cd comes first, so the switch runs in NOGIT and is not the pointer's.
sh("run-dir: a cd out of the pointer checkout, then a switch, allows, because the switch runs in the folder the cd left",
   "cd " + slash(NOGIT) + " && " + VCS + " switch somebranch", "allow", cwd=PTRMAIN, config=PTRCFG)

# THE CHECKOUT A git -C NAMES. A -C names the tree its own segment runs in. _run_dir reads the FIRST -C of
# the call for every segment, so a verdict can name the wrong checkout.
# RED. The pointer switch carries its own -C, after a -C into NOGIT. The verdict must name the pointer.
sh("run-dir: a status -C into a folder in no checkout, then a switch -C into the pointer checkout, denies",
   VCS + " -C " + slash(NOGIT) + " status; " + VCS + " -C " + slash(PTRMAIN) + " switch somebranch",
   "deny", "pointer-head", cwd=NOGIT, config=PTRCFG)
# RED, the other direction. The switch -C names NOGIT, which is no pointer, after a status -C into the pointer.
# A first -C that names the pointer must not deny a switch that runs elsewhere.
sh("run-dir: a switch -C into a folder in no checkout, after a status -C into the pointer checkout, allows",
   VCS + " -C " + slash(PTRMAIN) + " status; " + VCS + " -C " + slash(NOGIT) + " switch somebranch",
   "allow", cwd=NOGIT, config=PTRCFG)
# GREEN. A status is a read, so no -C order makes it a pointer move.
sh("run-dir: a status -C into the pointer checkout, after a -C elsewhere, is a read and allows",
   VCS + " -C " + slash(NOGIT) + " status; " + VCS + " -C " + slash(PTRMAIN) + " status",
   "allow", cwd=NOGIT, config=PTRCFG)

# AN INDENTED CLOSER DOES NOT CLOSE A HEREDOC (_walk_heredocs). Bash closes a heredoc only on a line that is
# exactly the delimiter. With `<<-`, bash strips leading tabs only. So a reset after an indented EOF is body
# text, and the call allows. Main strips the line, reads the reset as live, and refuses it in the dirty tree.
FAMILY = "shared-tree"
# RED. A space-indented EOF is body text under a plain heredoc.
sh("heredoc: a space-indented EOF does not close a quoted heredoc, so a reset after it is body text and allows",
   "cat <<'EOF'\n  EOF\n" + VCS + " reset --hard HEAD\nEOF", "allow", cwd=SUBJDIRTY)
# RED. A space-indented EOF is body text under `<<-` too: only tabs are stripped.
sh("heredoc: a space-indented EOF does not close a <<- heredoc, so a reset after it is body text and allows",
   "cat <<-'EOF'\n  EOF\n" + VCS + " reset --hard HEAD\nEOF", "allow", cwd=SUBJDIRTY)
# GREEN. A column-zero EOF closes the body, so the reset after it is a live command and denies.
sh("heredoc: a column-zero EOF closes a quoted heredoc, so a reset after it denies",
   "cat <<'EOF'\nEOF\n" + VCS + " reset --hard HEAD", "deny", "shared-tree", cwd=SUBJDIRTY)
# GREEN. A tab-indented EOF closes a `<<-` heredoc. A fix that matches the closer exactly must keep this.
sh("heredoc: a tab-indented EOF closes a <<- heredoc, so a reset after it denies",
   "cat <<-'EOF'\n\tEOF\n" + VCS + " reset --hard HEAD", "deny", "shared-tree", cwd=SUBJDIRTY)

# A WRAPPER OUTSIDE COMMAND_WRAPPERS HIDES THE KILL FROM kill_hit. gtimeout is the macOS name of timeout,
# and watch runs its command on a timer. kill_hit reads the command word after the wrappers it knows.
FAMILY = "kill"
# RED. gtimeout is timeout under another name, and the stream rule already unwraps it.
sh("kill: gtimeout 5 pkill -f node is refused, as timeout 5 pkill is",
   "gtimeout 5 pkill -f node", "deny", "machine-wide-kill", cwd=NOGIT)
# RED. watch runs pkill again and again.
sh("kill: watch pkill -f node is refused", "watch pkill -f node", "deny", "machine-wide-kill", cwd=NOGIT)
# RED. watch's value flag -n is skipped, and the pkill after it is the command.
sh("kill: watch -n 2 pkill -f node is refused, its value flag skipped",
   "watch -n 2 pkill -f node", "deny", "machine-wide-kill", cwd=NOGIT)
# GREEN. timeout is already a wrapper, so the kill behind it is refused today.
sh("kill: timeout 5 pkill -f node is refused", "timeout 5 pkill -f node", "deny", "machine-wide-kill",
   cwd=NOGIT)
# GREEN. A wrapper around a harmless command is no kill.
sh("kill: gtimeout 5 ls is no kill", "gtimeout 5 ls", "allow", cwd=NOGIT)
sh("kill: watch -n 2 ls is no kill", "watch -n 2 ls", "allow", cwd=NOGIT)
