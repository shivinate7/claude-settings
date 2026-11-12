# section 4861
FAMILY = "git-after-cd"

# A subshell's cd ends at its `)`, so the shell after `;` is still in the folder the failed cd left. The
# `&&` after the subshell runs the push there: the subshell's own cd does not carry out of it.
sh("git-after-cd: a cd into a missing folder, then ; a subshell cd, then && a git push is refused",
   "cd /tmp/w; (cd /tmp) && %s push" % VCS, "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

# A `||` after a failed cd runs `exit`, so the push after `;` never runs in the stranded folder.
sh("git-after-cd: a cd into a missing folder, then || exit 1, then ; a git push passes, the shell exits first",
   "cd /tmp/w || exit 1; %s push" % VCS, "allow", cwd=NOGIT)

# A top-level `return` does not stop bash: outside a function or a sourced script it fails and the shell
# goes on, so the push after `;` still runs in the stranded folder. Only `exit` stops the shell here.
sh("git-after-cd: a cd into a missing folder, then || return 1, then ; a git push is refused",
   "cd /tmp/w || return 1; %s push" % VCS, "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

# A subshell's exit ends only the subshell, and each part of a pipeline runs in a subshell. The shell goes on
# after the failed cd, so the push after the group still runs in the stranded folder. Real bash runs it.
sh("git-after-cd: a cd into a missing folder, then || (exit 1), then ; a git push is refused",
   "cd /tmp/w || (exit 1); %s push" % VCS, "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

sh("git-after-cd: a cd into a missing folder, then || (exit 1), then a newline and a git push is refused",
   "cd /tmp/w || (exit 1)\n%s push" % VCS, "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

sh("git-after-cd: a cd into a missing folder, then || exit 1 | cat, then ; a git push is refused",
   "cd /tmp/w || exit 1 | cat; %s push" % VCS, "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

sh("git-after-cd: a cd into a missing folder, then || a braced exit 1 in a pipe, then ; a git push is refused",
   "cd /tmp/w || { exit 1; } | cat; %s push" % VCS, "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

# Coverage: each of these holds today. The else branch runs when the test fails, so its push runs in the stranded folder.
sh("git-after-cd: a cd into a missing folder as an if test, then the push in the else branch is refused",
   "if cd /tmp/w; then :; else %s push; fi" % VCS, "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

# Coverage: a read under a failed cd, joined by ;, passes. A dry run, a listing and a value read write nothing.
sh("git-after-cd: a cd into a missing folder, then ; git add -n . is a dry run, passes",
   "cd /tmp/w; %s add -n ." % VCS, "allow", cwd=NOGIT)

sh("git-after-cd: a cd into a missing folder, then ; git tag -l is a listing, passes",
   "cd /tmp/w; %s tag -l" % VCS, "allow", cwd=NOGIT)

sh("git-after-cd: a cd into a missing folder, then ; git config --get user.name is a read, passes",
   "cd /tmp/w; %s config --get user.name" % VCS, "allow", cwd=NOGIT)

sh("git-after-cd: a cd into a missing folder, then ; git worktree list is a read, passes",
   "cd /tmp/w; %s worktree list" % VCS, "allow", cwd=NOGIT)

# A failed `if` test skips the then branch, so the push there never runs in the stranded folder.
sh("git-after-cd: a cd into a missing folder as an if test, then a git push in the then branch passes",
   "if cd /tmp/w; then %s push; fi" % VCS, "allow", cwd=NOGIT)

# The fi of a nested if closes only that if: the push after it is still in the outer then branch.
sh("git-after-cd: a cd into a missing folder as an if test, then a nested if and fi, then a git push in the then branch passes",
   "if cd /tmp/w; then if true; then :; fi; %s push; fi" % VCS, "allow", cwd=NOGIT)

# The write verbs the rule does not name yet: each runs in the stranded folder after a failed cd and ;.
sh("git-after-cd: a cd into a missing folder, then ; git add -A is refused",
   "cd /tmp/w; %s add -A" % VCS, "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

sh("git-after-cd: a cd into a missing folder, then ; git tag v1 is refused",
   "cd /tmp/w; %s tag v1" % VCS, "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

sh("git-after-cd: a cd into a missing folder, then ; git config user.name x is refused",
   "cd /tmp/w; %s config user.name x" % VCS, "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

sh("git-after-cd: a cd into a missing folder, then ; git worktree add ../w is refused",
   "cd /tmp/w; %s worktree add ../w" % VCS, "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))
