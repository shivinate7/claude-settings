# section 43830
FAMILY = "force-push-main"

# Rule force-push refuses a non-forced push that writes the default branch. Each MAIN row is such a form: the refusal
# is force-push's, its reason names the default branch and the lane-branch remedy, and it carries no lease retry. The
# FORCED rows keep force-push's own refusal for a forced push to another branch, a delete of the default branch, and a
# forced push to the default branch. The CONTROLS and NEIGHBOURS pass: a lease that cannot overwrite newer work, a dry
# run, a local-path origin, and the agent and all-branch refusals keep their own rules.
MERGED_RULE = "force-push"
MAIN_NAMES = ("default branch", "git push origin HEAD:")
MAIN_LACKS = (REMEDY, CHAIN_ASK, "HEAD:main", "HEAD:master", "push origin main", "push origin master")


def merged_main(name, command, cwd=PUSHFEAT, tool="Bash", config=None, carries=MAIN_NAMES):
    """A non-forced push that writes the default branch. The refusal is force-push's, and its reason names the default branch."""
    sh("force-push-main: " + name, command, "deny", MERGED_RULE, tool=tool, cwd=cwd, config=config,
       carries=carries, lacks=MAIN_LACKS)


# MAIN rows: explicit refspecs to a network origin. PUSHFEAT's origin/HEAD names main.
merged_main("a plain push of main", VCS + " push origin main")
merged_main("HEAD:main from a feature branch", VCS + " push origin HEAD:main")
merged_main("master as the destination", VCS + " push origin HEAD:master")
merged_main("master as the source", VCS + " push origin master")
merged_main("a full ref to refs/heads/main", VCS + " push origin x:refs/heads/main")
merged_main("main, then a lane name", VCS + " push origin main HEAD:lane-x")
merged_main("a second refspec that reaches main", VCS + " push origin HEAD:push-guard-asks HEAD:main")
merged_main("HEAD:main where origin/HEAD names trunk", VCS + " push origin HEAD:main", cwd=PUSHTRUNK)
merged_main("HEAD:main with no origin/HEAD, the main and master fallback", VCS + " push origin HEAD:main",
            cwd=PUSHNOHEADMAIN)

# MAIN rows: the implied destination, read from the checkout's branch and push.default.
merged_main("on main, origin main", VCS + " push origin main", cwd=PUSHMAIN)
merged_main("on main, -u HEAD", VCS + " push -u origin HEAD", cwd=PUSHMAIN)
merged_main("on main, a bare push under push.default current", VCS + " -c push.default=current push", cwd=PUSHMAIN)
merged_main("on main with no upstream, a bare push under autoSetupRemote",
            VCS + " -c push.autoSetupRemote=true push", cwd=PUSHMAIN)
merged_main("tracking origin/main, a bare push", VCS + " push", cwd=PUSHMAINUP)
merged_main("tracking origin/main, a bare push under push.default simple",
            VCS + " -c push.default=simple push", cwd=PUSHMAINUP)
merged_main("tracking origin/main, HEAD", VCS + " push origin HEAD", cwd=PUSHMAINUP)
merged_main("a feature branch whose push.default upstream follows main", VCS + " push", cwd=PUSHUP)

# MAIN rows: a -C or a cd names the checkout the push runs in.
merged_main("-C into the main checkout, from a feature checkout", VCS + " -C " + slash(PUSHMAIN) + " push origin main")
merged_main("-C into a network origin, from a repo with no remote",
            VCS + " -C " + slash(PUSHFEAT) + " push origin main", cwd=PUSHNOREMOTE)
merged_main("cd into the main checkout, then origin main",
            "cd " + slash(PUSHMAIN) + " && " + VCS + " push origin main")
merged_main("cd into a folder that is not there, then origin main",
            "cd " + slash(os.path.join(ROOT, "pushmissing")) + " && " + VCS + " push origin main", cwd=PUSHLOCALMAIN)
merged_main("-C into a folder that is not there, then origin main",
            VCS + " -C " + slash(os.path.join(ROOT, "nowhere")) + " push origin main")

# MAIN rows: PowerShell.
merged_main("PowerShell, origin main", VCS + " push origin main", tool="PowerShell")
merged_main("PowerShell, HEAD:main", VCS + " push origin HEAD:main", tool="PowerShell")
merged_main("PowerShell, a bare push from a checkout that tracks origin/main", VCS + " push", cwd=PUSHMAINUP,
            tool="PowerShell")
merged_main("PowerShell, Set-Location into the main checkout, then origin main",
            "Set-Location " + slash(PUSHMAIN) + "; " + VCS + " push origin main", tool="PowerShell")

# MAIN rows: the remote named by its URL, by a shell expansion, or by git -c.
merged_main("an scp-form origin", VCS + " push origin main", cwd=PUSHSSH)
merged_main("a network URL named as the remote, from a repo with no remote",
            VCS + " push https://example.invalid/r.git main", cwd=PUSHNOREMOTE)
merged_main("a double-quoted shell variable as the remote", VCS + ' push "$REMOTE" main')
merged_main("an unquoted shell variable as the remote, HEAD:main", VCS + " push $REMOTE HEAD:main")
merged_main("a backtick as the remote", VCS + " push `printf origin` main")
merged_main("a command substitution as the remote", VCS + " push $(printf origin) main")
merged_main("a bare push with a shell variable as the remote, on main",
            VCS + ' -c push.default=current push "$REMOTE"', cwd=PUSHMAIN)
merged_main("a local origin made a network remote by git -c",
            VCS + " -c remote.origin.url=https://example.invalid/r.git push origin main", cwd=PUSHLOCAL)
# A merge-tool repo: its reason is the merge-tool text, which names the merge tool as the way in.
merged_main("a merge-tool repo, a network remote by git -c, origin main",
            VCS + " -c remote.origin.url=https://example.invalid/r.git push origin main", cwd=STAMPREPO,
            carries=MAIN_NAMES + ("merge tool",))

# MAIN rows: a push to main inside a chain, a wrapper, or a command substitution, or with a split command word.
merged_main("a comment opener inside a string before a push to main", 'echo "#" && ' + VCS + " push origin main",
            cwd=PUSHMAIN)
merged_main("a lone quote in a commit message before a push to main",
            VCS + ' commit -m "don\'t" && ' + VCS + " push origin main")
merged_main("bash -c wrapping a push to main", "bash -c '" + VCS + " push origin main'")
merged_main("sh -c wrapping a push to HEAD:main", "sh -c '" + VCS + " push origin HEAD:main'")
merged_main("a push to main inside a command substitution", "x=$(" + VCS + " push origin main)")
for _word in SPLIT_ANSI_WORDS + SPLIT_SHELL_WORDS:
    merged_main("split word " + _word + " pushes to main", _word + " push origin HEAD:main")

# FORCED rows: a forced push to a branch that is not the default. force-push's own refusal, unchanged.
sh("force-push-main: a forced push to a feature branch denies, with the lease retry",
   VCS + " push --force origin feat", "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY,
   lacks=("default branch",))
sh("force-push-main: -f to a feature branch denies, with the lease retry",
   VCS + " push -f origin HEAD:feat", "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY,
   lacks=("default branch",))
sh("force-push-main: a plus refspec to a feature branch denies, with the lease retry",
   VCS + " push origin +HEAD:feat", "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY,
   lacks=("default branch",))
sh("force-push-main: a bare lease to a feature branch denies, with the lease retry",
   VCS + " push --force-with-lease origin feat", "deny", "force-push", cwd=PUSHFEAT, carries=REMEDY,
   lacks=("default branch",))
sh("force-push-main: a forced push to a feature branch from the main checkout denies, with the lease retry",
   VCS + " push --force origin HEAD:feat", "deny", "force-push", cwd=PUSHMAIN, carries=REMEDY,
   lacks=("default branch",))
# A delete of the default branch is a forced push that reaches it: force-push's ask, which already names it.
sh("force-push-main: a delete of main denies under force-push, naming the default branch",
   VCS + " push origin :main", "deny", "force-push", cwd=PUSHFEAT, carries=MAIN_NAMES, lacks=(REMEDY,))
# A forced push that reaches main already denies under force-push (refuse-main, see s08727).
sh("force-push-main: a forced push to main denies under force-push, naming the default branch",
   VCS + " push --force origin HEAD:main", "deny", "force-push", cwd=PUSHFEAT, carries=MAIN_NAMES,
   lacks=(REMEDY,))

# CONTROLS: a lease that cannot overwrite newer work, a dry run, a local-path origin and a non-default target pass.
sh("force-push-main: a lease with includes to a feature branch allows",
   VCS + " push --force-with-lease --force-if-includes origin feat", "allow", cwd=PUSHFEAT, silent=True)
sh("force-push-main: a dry run of a push to main allows",
   VCS + " push --dry-run origin main", "allow", cwd=PUSHFEAT, silent=True)
sh("force-push-main: a push to main on a local-path origin allows",
   VCS + " push origin main", "allow", cwd=PUSHLOCAL, silent=True)
sh("force-push-main: a plain push to a feature branch from the main checkout allows",
   VCS + " push origin HEAD:feat", "allow", cwd=PUSHMAIN, silent=True)

# NEIGHBOURS: a push that writes an agent-named branch as well as main keeps push-agent-branch's refusal, with its
# own remedy and no default-branch reason. An --all push that would update main keeps push-all-main.
sh("force-push-main: main then an agent name keeps the agent rule, not the default-branch reason",
   VCS + " push origin main claude/agent-deadbeef01", "deny", PUSH_AGENT_RULE, cwd=PUSHFEAT,
   carries=(PUSH_AGENT_REMEDY,), lacks=PUSH_AGENT_LACKS + ("claude/agent-deadbeef01", "default branch"))
sh("force-push-main: --all that would update main keeps the push-all-main rule",
   VCS + " push --all origin", "deny", PUSH_ALL_RULE, cwd=PUSHAHEAD)
