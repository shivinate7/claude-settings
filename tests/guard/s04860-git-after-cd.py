# section 4860
FAMILY = "git-after-cd"

# A GIT WRITE AFTER A CD. Decision git-after-cd-joins-with-and: once a cd is seen, a `;`, a newline
# or `||` reopens the path a failed cd takes, so every git write after it is refused. A chain joined
# only by `&&` passes, and so does `-C <absolute path>`; the cd's scope ends at the `)` of a subshell.

sh("git-after-cd: the 2026-11-07 incident, a cd joined by && then ; git writes, is refused",
   "cd /tmp/w/b-int && %s status --short; %s fetch origin; "
   "%s checkout -B claude/int-batch-banchi-1107b origin/main; %s merge --no-ff claude/lane-a"
   % ((VCS,) * 4), "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

sh("git-after-cd: a cd then ; then a git push is refused",
   "cd /tmp/w; %s push" % VCS, "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

sh("git-after-cd: a cd then a newline then a git merge is refused",
   "cd /tmp/w\n%s merge claude/lane-a" % VCS, "deny", "git-after-cd", cwd=NOGIT,
   carries=("&&", "-C"))

sh("git-after-cd: a cd then || then a git commit is refused",
   "cd /tmp/w || %s commit -m m" % VCS, "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

sh("git-after-cd: a cd and && make, then ; then a git reset --soft is refused",
   "cd /tmp/w && make; %s reset --soft HEAD~1" % VCS, "deny", "git-after-cd", cwd=NOGIT,
   carries=("&&", "-C"))

sh("git-after-cd: a cd in a subshell, then ; then a git push inside it is refused",
   "(cd /tmp/w; %s push)" % VCS, "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

sh("git-after-cd: a cd then ; then a git branch -f is refused",
   "cd /tmp/w; %s branch -f main HEAD" % VCS, "deny", "git-after-cd", cwd=NOGIT,
   carries=("&&", "-C"))

sh("git-after-cd: a hash inside a word is no comment, the push after a cd is refused",
   "cd /tmp/w; %s push origin fix#3" % VCS, "deny", "git-after-cd", cwd=NOGIT,
   carries=("&&", "-C"))

sh("git-after-cd: an apostrophe in a comment after the push does not hide it",
   "cd /tmp/w; %s push # the driver's shape" % VCS, "deny", "git-after-cd", cwd=NOGIT,
   carries=("&&", "-C"))

sh("git-after-cd: a cd and && then a git checkout passes",
   "cd /tmp/w && %s checkout lane-a" % VCS, "allow", cwd=NOGIT)

sh("git-after-cd: a cd joined by && all the way to a git push passes",
   "cd /tmp/w && %s status && %s push" % (VCS, VCS), "allow", cwd=NOGIT)

sh("git-after-cd: a git push with -C an absolute path passes",
   "%s -C /tmp/x push" % VCS, "allow", cwd=NOGIT)

sh("git-after-cd: a cd then ; then a git push with -C an absolute path passes",
   "cd /tmp/w; %s -C /tmp/x push" % VCS, "allow", cwd=NOGIT)

sh("git-after-cd: a cd then ; then ls passes",
   "cd /tmp/w; ls", "allow", cwd=NOGIT)

sh("git-after-cd: a cd then ; then git status and git log pass",
   "cd /tmp/w; %s status; %s log" % (VCS, VCS), "allow", cwd=NOGIT)

sh("git-after-cd: a subshell's cd ends at its ), so the git commit after it passes",
   "(cd /tmp/w && %s push); %s commit -m m" % (VCS, VCS), "allow", cwd=NOGIT)

sh("git-after-cd: a cd then ; then git branch -l, a read, passes",
   "cd /tmp/w; %s branch -l" % VCS, "allow", cwd=NOGIT)

sh("git-after-cd: a git push after a comment opener on the cd line is in the comment and passes",
   "cd /tmp/w # it's; %s push" % VCS, "allow", cwd=NOGIT)

sh("git-after-cd: an echo of a cd then ; then git push, inside quotes, passes",
   'echo "cd /tmp/w; %s push"' % VCS, "allow", cwd=NOGIT)

sh("git-after-cd: a cd then ; then git branch --force is refused",
   "cd /tmp/w; %s branch --force main HEAD" % VCS, "deny", "git-after-cd", cwd=NOGIT,
   carries=("&&", "-C"))

sh("git-after-cd: a cd then ; then git stash list passes",
   "cd /tmp/w; %s stash list" % VCS, "allow", cwd=NOGIT)

sh("git-after-cd: a cd then ; then git stash show passes",
   "cd /tmp/w; %s stash show" % VCS, "allow", cwd=NOGIT)

sh("git-after-cd: a cd then ; then git clean -n, a dry run, passes",
   "cd /tmp/w; %s clean -n" % VCS, "allow", cwd=NOGIT)

sh("git-after-cd: a cd then ; then git -C with a variable folder passes",
   'cd /tmp/w; %s -C "$D" push' % VCS, "allow", cwd=NOGIT)

sh("git-after-cd: a cd then ; then git -C with a relative folder is refused",
   "cd /tmp/w; %s -C rel push" % VCS, "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

sh("git-after-cd: a cd then ; then git update-ref is refused",
   "cd /tmp/w; %s update-ref refs/heads/main HEAD" % VCS, "deny", "git-after-cd", cwd=NOGIT,
   carries=("&&", "-C"))

sh("git-after-cd: a cd then ; then git rm is refused",
   "cd /tmp/w; %s rm old.txt" % VCS, "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

sh("git-after-cd: a cd then ; then git mv is refused",
   "cd /tmp/w; %s mv a.txt b.txt" % VCS, "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

sh("git-after-cd: a cd then ; then git fetch with a src:dst refspec is refused",
   "cd /tmp/w; %s fetch origin main:main" % VCS, "deny", "git-after-cd", cwd=NOGIT,
   carries=("&&", "-C"))

sh("git-after-cd: a cd then ; then git branch -m is refused",
   "cd /tmp/w; %s branch -m old new" % VCS, "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

sh("git-after-cd: a cd then ; then git branch -M is refused",
   "cd /tmp/w; %s branch -M main" % VCS, "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

# shared-tree refuses a named branch delete in this harness, so the delete cases use the nameless forms.
sh("git-after-cd: a cd then ; then git branch -D is refused",
   "cd /tmp/w; %s branch -D" % VCS, "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

sh("git-after-cd: a cd then ; then git branch -d is refused",
   "cd /tmp/w; %s branch -d" % VCS, "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

sh("git-after-cd: a cd then ; then git branch --delete is refused",
   "cd /tmp/w; %s branch --delete" % VCS, "deny", "git-after-cd", cwd=NOGIT,
   carries=("&&", "-C"))

sh("git-after-cd: a cd then ; then git branch --move a b is refused",
   "cd /tmp/w; %s branch --move a b" % VCS, "deny", "git-after-cd", cwd=NOGIT,
   carries=("&&", "-C"))

sh("git-after-cd: a cd then ; then a bare git fetch, a read, passes",
   "cd /tmp/w; %s fetch" % VCS, "allow", cwd=NOGIT)

sh("git-after-cd: a cd then ; then git push --dry-run passes",
   "cd /tmp/w; %s push --dry-run" % VCS, "allow", cwd=NOGIT)

sh("git-after-cd: a cd then ; then git push -n passes",
   "cd /tmp/w; %s push -n" % VCS, "allow", cwd=NOGIT)

# The && skip ends at the next ; or ||. The cd after a failed cd never runs, so the shell stays in the
# folder it started in, and the write after ; or || runs there. ROOT is the run folder: a real folder.
sh("git-after-cd: a failed cd, then && a cd that is skipped, then ; a git push is refused",
   "cd /tmp/w && cd %s ; %s push" % (slash(ROOT), VCS), "deny", "git-after-cd", cwd=NOGIT,
   carries=("&&", "-C"))

sh("git-after-cd: a failed cd, then && a cd that is skipped, then || a git push is refused",
   "cd /tmp/w && cd %s || %s push" % (slash(ROOT), VCS), "deny", "git-after-cd", cwd=NOGIT,
   carries=("&&", "-C"))

# A subshell's ) ends its cd, but the && chain goes on, so the git push after it is still skipped.
sh("git-after-cd: a failed cd, then && a subshell, then && a git push passes, the chain stops at the cd",
   "cd /tmp/w && (true) && %s push" % VCS, "allow", cwd=NOGIT)

# The ) of the subshell puts the shell back where it was before the failed cd, so the push after ; runs in cwd.
sh("git-after-cd: a failed cd inside ( ... ), then ; a git push after the ) passes",
   "(cd /tmp/w; true); %s push" % VCS, "allow", cwd=NOGIT)
