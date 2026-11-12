# section 4342
FAMILY = "two-worktrees-one-branch"
#
# Rule two-worktrees-one-branch (the decision of the same name): the guard refuses a git command that
# checks out a branch another worktree of the clone already holds. The forms are `checkout -B` and
# `switch -C`, `checkout` and `switch` with --ignore-other-worktrees, and `worktree add -f` or `--force`.
# Git 2.43 lets the first two through with no warning. That is the incident: a lane session re-pointed
# a branch that a builder's worktree held, and a commit there would have undone the builder's fix.
#
# BOTH DIRECTIONS ARE PINNED. A checkout that takes a branch no other worktree holds, a switch that
# creates one, a plain checkout that git refuses itself, and the holder's own checkout all stay
# allowed. The worktree list is read only for the forms above.
TWO_RULE = "two-worktrees-one-branch"


def _sh_quote(text):
    return "'" + text.replace("'", "'\\''") + "'"


def make_git_stand_in(folder, log=None, fail_on=None):
    """Put a `git` on PATH that hands each call to the real git.

    With `log`, each call's argv is appended to that file, one line a call, before the hand-off. With
    `fail_on`, a call whose argv holds that text is answered with an error and the real git never runs
    for it. The real git is named by its absolute path, so the stand-in never calls itself. This is a
    POSIX script: Windows does not run it, so each case that uses one is skipped there.
    """
    os.makedirs(folder, exist_ok=True)
    lines = ["#!/bin/sh"]
    if log:
        lines.append("printf '%s\\n' \"$*\" >> " + _sh_quote(log))
    if fail_on:
        lines.append("case \"$*\" in *" + _sh_quote(fail_on)
                     + "*) echo 'stand-in: read failed' >&2; exit 128;; esac")
    lines.append("exec " + _sh_quote(os.path.join(GIT_PATH, VCS)) + " \"$@\"")
    script = os.path.join(folder, VCS)
    write(script, "\n".join(lines) + "\n")
    os.chmod(script, 0o755)


def _worktree_branches(where):
    """{real path: branch ref, or None when detached} for each worktree `where` lists, read with git itself."""
    listing = run_vcs(where, "worktree", "list", "--porcelain")
    if listing.returncode != 0:
        sys.exit("fixture setup failed in build_fixtures: git worktree list --porcelain failed in %r. "
                 "stderr: %s" % (where, listing.stderr.strip()))
    held = {}
    path = None
    for line in listing.stdout.splitlines():
        if line.startswith("worktree "):
            path = os.path.realpath(line[len("worktree "):].strip())
            held[path] = None
        elif line.startswith("branch ") and path:
            held[path] = line[len("branch "):].strip()
    return held


def _build_two_worktrees():
    """The two-worktrees-one-branch repos: a base on main, a linked worktree holding x, a linked worktree
    that acts on its own branch, and the two stand-ins. The scope is read back with git before a case
    relies on it, so a broken build stops the run instead of passing for the wrong reason."""
    make_repo(TWBASE, {"f.txt": "one\n"})
    for where, branch in ((TWHOLD, "x"), (TWACT, "actor-lane")):
        added = run_vcs(TWBASE, "worktree", "add", "-q", where, "-b", branch)
        if added.returncode != 0:
            sys.exit("fixture setup failed in build_fixtures: worktree add %r failed. stderr: %s"
                     % (where, added.stderr.strip()))
    held = _worktree_branches(TWBASE)
    for where, ref in ((TWBASE, "refs/heads/main"), (TWHOLD, "refs/heads/x"),
                       (TWACT, "refs/heads/actor-lane")):
        if held.get(os.path.realpath(where)) != ref:
            sys.exit("fixture setup failed in build_fixtures: %r should hold %s, worktree list reads %r"
                     % (where, ref, held))
    make_git_stand_in(TWLOGSHIM, log=os.path.join(TWLOGSHIM, "calls.log"))
    make_git_stand_in(TWFAILSHIM, fail_on="worktree list")


lazy_fixture([TWBASE, TWHOLD, TWACT, TWLOGSHIM, TWFAILSHIM], _build_two_worktrees)


def stand_in_sh(name, command, expected, rule=None, **kw):
    """sh() with a stand-in git on PATH. Windows does not run a POSIX stand-in, so the case is skipped there."""
    if os.name == "nt":
        skip_case(name, NO_STAND_IN)
    else:
        sh(name, command, expected, rule, **kw)


# THE REFUSED FORMS. Each runs from TWACT, a linked worktree on its own branch, while TWHOLD holds x.
sh("two-worktrees: checkout -B of a branch another worktree holds is refused",
   VCS + " checkout -B x", "deny", TWO_RULE, cwd=TWACT)
sh("two-worktrees: switch -C of a branch another worktree holds is refused",
   VCS + " switch -C x", "deny", TWO_RULE, cwd=TWACT)
# THE INCIDENT SHAPE. The lane session ran `checkout -B <branch> origin/<branch>`: a start point after the name.
sh("two-worktrees: the incident shape, checkout -B with a start point, is refused",
   VCS + " checkout -B x origin/x", "deny", TWO_RULE, cwd=TWACT)
sh("two-worktrees: switch -C with a start point is refused",
   VCS + " switch -C x origin/x", "deny", TWO_RULE, cwd=TWACT)
# THE LONG SPELLING. `--force-create` is `switch -C` written out: a value after it, or after `=`. Git 2.43
# takes all three forms, and the guard reads each as the same branch, so each is refused.
sh("two-worktrees: switch --force-create of a branch another worktree holds is refused",
   VCS + " switch --force-create x", "deny", TWO_RULE, cwd=TWACT)
sh("two-worktrees: switch --force-create with a start point is refused",
   VCS + " switch --force-create x origin/x", "deny", TWO_RULE, cwd=TWACT)
sh("two-worktrees: switch --force-create=x, the equals spelling, is refused",
   VCS + " switch --force-create=x", "deny", TWO_RULE, cwd=TWACT)
sh("two-worktrees: checkout --ignore-other-worktrees of a held branch is refused",
   VCS + " checkout --ignore-other-worktrees x", "deny", TWO_RULE, cwd=TWACT)
sh("two-worktrees: switch --ignore-other-worktrees of a held branch is refused",
   VCS + " switch --ignore-other-worktrees x", "deny", TWO_RULE, cwd=TWACT)
sh("two-worktrees: worktree add -f of a held branch is refused",
   VCS + " worktree add -f ../w2 x", "deny", TWO_RULE, cwd=TWACT)
sh("two-worktrees: worktree add --force of a held branch is refused",
   VCS + " worktree add --force ../w2 x", "deny", TWO_RULE, cwd=TWACT)
# A QUOTED NAME is still the held branch once the shell strips the quotes.
sh("two-worktrees: a quoted branch name is the held branch, and is refused",
   VCS + ' checkout -B "x"', "deny", TWO_RULE, cwd=TWACT)
# THE IGNORE FLAG REFUSES ANY BRANCH, even one no worktree holds (the ruling, settled in its record).
sh("two-worktrees: checkout --ignore-other-worktrees of a branch no worktree holds is refused",
   VCS + " checkout --ignore-other-worktrees y", "deny", TWO_RULE, cwd=TWACT)
sh("two-worktrees: switch --ignore-other-worktrees of a branch no worktree holds is refused",
   VCS + " switch --ignore-other-worktrees y", "deny", TWO_RULE, cwd=TWACT)
# THE -C TREE. The tree a command runs in is the one `git -C` names, else the cwd. A -C naming another
# tree that lacks x is refused while the holder holds x.
sh("two-worktrees: git -C <other> checkout -B x, where the holder holds x, is refused",
   VCS + " -C " + slash(TWACT) + " checkout -B x", "deny", TWO_RULE, cwd=TWACT)
# A READ THAT FAILS REFUSES. The stand-in fails only the worktree list read, and `-B y` names no held
# branch, so the refusal can only come from the failed read.
stand_in_sh("two-worktrees: a failed worktree list read refuses, even for a branch no worktree holds",
            VCS + " checkout -B y", "deny", TWO_RULE, cwd=TWACT, env_path=TWFAILSHIM + os.pathsep + GIT_PATH)

# THE CONTROLS. Each must pass now, before the rule is built, and after it.
sh("two-worktrees: checkout -B of a branch no other worktree holds is allowed",
   VCS + " checkout -B y", "allow", cwd=TWACT)
sh("two-worktrees: switch -c of a new branch is allowed",
   VCS + " switch -c z", "allow", cwd=TWACT)
sh("two-worktrees: a plain checkout of a held branch is git's own refusal, not this rule's",
   VCS + " checkout x", "allow", cwd=TWACT)
sh("two-worktrees: checkout -B of x in the worktree that already holds x is allowed",
   VCS + " checkout -B x", "allow", cwd=TWHOLD)
sh("two-worktrees: a plain status is allowed", VCS + " status", "allow", cwd=TWACT)
sh("two-worktrees: the form inside an echo's quotes is text, not a checkout",
   "echo 'git switch -C x'", "allow", cwd=TWACT)
sh("two-worktrees: a commit message that quotes the form is text, not a checkout",
   VCS + " commit -m 'git checkout -B x'", "allow", cwd=TWACT)
sh("two-worktrees: worktree add of a new branch, with no force, is allowed",
   VCS + " worktree add -b w3-new ../w3", "allow", cwd=TWACT)
sh("two-worktrees: worktree add of a held branch, with no force, is git's own refusal, not this rule's",
   VCS + " worktree add ../w4 x", "allow", cwd=TWACT)
sh("two-worktrees: git -C <holder> checkout -B x, run in the holder's own tree, is allowed",
   VCS + " -C " + slash(TWHOLD) + " checkout -B x", "allow", cwd=TWHOLD)

# THE TREE PER SEGMENT. A `git -C` moves only the call it heads, and the next call runs in the cwd again.
# One command can therefore run calls in several trees, and each call is judged in the tree it runs in.
# W is the holder (TWHOLD, holds x). The cwd is TWACT (holds no x) for the first two cases, and the primary
# checkout TWBASE (on main, holds no x) for the third. A `cd` is not used: other-checkout refuses a cd into
# another checkout of the clone before this rule runs, unless the session has a recorded home there. A write
# that a `git -C` sends into another checkout is refused by other-checkout too, so the third case writes in its cwd.
sh("two-worktrees: checkout -B x after a git -C that names the holder is refused, the checkout runs in the cwd",
   VCS + " -C ../twobr-holder status && " + VCS + " checkout -B x", "deny", TWO_RULE, cwd=TWACT)
sh("two-worktrees: checkout -B x before a git -C that names the holder is refused, the checkout runs in the cwd",
   VCS + " checkout -B x && " + VCS + " -C ../twobr-holder status", "deny", TWO_RULE, cwd=TWACT)
sh("two-worktrees: checkout -B x in the primary checkout is refused while the holder holds x, after a git -C to the holder",
   VCS + " -C ../twobr-holder status && " + VCS + " checkout -B x", "deny", TWO_RULE, cwd=TWBASE)
# THE OWN TREE, FUNCTION LEVEL. From another cwd the hook never reaches the holder's own tree: a write that a
# `git -C` sends into the holder is refused by other-checkout first, and that rule runs before this one. So the
# own-tree exclusion is checked on the function, in two_worktrees_own_tree_case.
# THE -C WRITE, REFUSED BY OTHER-CHECKOUT. From the primary checkout, the holder's `checkout -B x` is a write into
# another checkout, so the deny names other-checkout, not this rule.
sh("two-worktrees: git -C <holder> checkout -B x, from the primary checkout, is refused by other-checkout",
   VCS + " -C ../twobr-holder checkout -B x", "deny", "other-checkout", cwd=TWBASE)
# A `cd` inside quotes is text, so the checkout still runs in the cwd.
sh("two-worktrees: a cd inside an echo's quotes moves no tree, so checkout -B x runs in the cwd and is refused",
   "echo 'cd ../twobr-holder' && " + VCS + " checkout -B x", "deny", TWO_RULE, cwd=TWACT)

# THE CLUSTERED FLAGS. A short flag can share a cluster with -B or -C (`-fB`, `-qC`), and git reads the
# letter as its own option. Each clustered form is refused the same as its plain spelling.
sh("two-worktrees: checkout -fB of a branch another worktree holds is refused",
   VCS + " checkout -fB x", "deny", TWO_RULE, cwd=TWACT)
sh("two-worktrees: checkout -qB of a branch another worktree holds is refused",
   VCS + " checkout -qB x", "deny", TWO_RULE, cwd=TWACT)
sh("two-worktrees: switch -fC of a branch another worktree holds is refused",
   VCS + " switch -fC x", "deny", TWO_RULE, cwd=TWACT)
sh("two-worktrees: switch -qC of a branch another worktree holds is refused",
   VCS + " switch -qC x", "deny", TWO_RULE, cwd=TWACT)
sh("two-worktrees: checkout -fB of a branch no worktree holds is allowed",
   VCS + " checkout -fB y", "allow", cwd=TWACT)
sh("two-worktrees: switch -fC of a branch no worktree holds is allowed",
   VCS + " switch -fC y", "allow", cwd=TWACT)
# THE LONG SPELLING, ALLOWED. A new-branch name that no worktree holds passes, so the refused cases above
# are the held branch and not the spelling.
sh("two-worktrees: switch --force-create of a branch no worktree holds is allowed",
   VCS + " switch --force-create y", "allow", cwd=TWACT)

# THE FALSE ALARM. `-d` is --detach for worktree add (git 2.43 reads it), so a forced add with -d takes
# no branch, and the guard must not read the held name `x` as one. The long spelling is the control.
sh("two-worktrees: worktree add -f -d, a forced detached add that takes no branch, is allowed",
   VCS + " worktree add -f -d ../n x", "allow", cwd=TWACT)
sh("two-worktrees: worktree add -f --detach, a forced detached add that takes no branch, is allowed",
   VCS + " worktree add -f --detach ../n2 x", "allow", cwd=TWACT)


def _two_worktrees_calls(command, cwd):
    """Run `command` through the guard with the logging stand-in on PATH. Returns (decision, reason, the
    argv lines the stand-in logged for this one run)."""
    log = os.path.join(TWLOGSHIM, "calls.log")
    if os.path.exists(log):
        os.remove(log)
    decision, reason = decide({"raw": None, "tool": "Bash", "cwd": cwd, "session": None,
                               "env_path": TWLOGSHIM + os.pathsep + GIT_PATH,
                               "tool_input": {"command": command}})
    calls = open(log, encoding="utf-8").read().splitlines() if os.path.exists(log) else []
    return decision, reason, calls


def two_worktrees_reads_list_once_case():
    """The refused form reads the worktree list exactly once, the one read the rule makes. The check goes red
    on the old code because it reads no list at all, and the stand-in shows that it can see one."""
    if os.name == "nt":
        return SKIP, NO_STAND_IN
    decision, _reason, calls = _two_worktrees_calls(VCS + " checkout -B x", TWACT)
    listed = [line for line in calls if "worktree list" in line]
    if len(listed) == 1:
        return True, "checkout -B of a held branch reads the worktree list once"
    return False, "checkout -B x reads the worktree list %d time(s), want exactly 1 (decision %s, calls %r)" % (
        len(listed), decision, calls[:4])


def two_worktrees_observer_case():
    """The stand-in sees a worktree list read that the guard makes today: `worktree remove` reads the list on the
    old code. Green there, so the empty log of an unrelated command means no read, not a blind stand-in."""
    if os.name == "nt":
        return SKIP, NO_STAND_IN
    _decision, _reason, calls = _two_worktrees_calls(VCS + " worktree remove " + slash(TWHOLD), TWBASE)
    if any("worktree list" in line for line in calls):
        return True, "the stand-in logs the worktree list the guard reads for worktree remove"
    return False, "worktree remove logged no worktree list, so the stand-in cannot see the guard's reads: %r" % (
        calls[:4],)


def two_worktrees_unrelated_no_list_case():
    """An unrelated git command reads no worktree list. The observer case above proves the stand-in sees reads."""
    if os.name == "nt":
        return SKIP, NO_STAND_IN
    for command in (VCS + " status", VCS + " switch -c z"):
        _decision, _reason, calls = _two_worktrees_calls(command, TWACT)
        listed = [line for line in calls if "worktree list" in line]
        if listed:
            return False, "%s read the worktree list: %s" % (command, listed[0])
    return True, "a plain status and a new-branch switch read no worktree list"


def two_worktrees_own_tree_case():
    """The own-tree exclusion, read on the function. Scope first: the holder's own worktree list holds x on the
    holder, and from the actor's tree the same `checkout -B x` is a hit. Then the subject: from the holder's own
    tree the same call is no hit, since x there is the holder's own. The hook cannot reach this from another cwd,
    because other-checkout refuses the write first. GUARD may be a mutated copy, so the module loads from its folder."""
    import importlib.util
    materialize(TWHOLD)
    spec = importlib.util.spec_from_file_location(
        "guard_branch_worktree_under_test", os.path.join(os.path.dirname(GUARD), "guard_branch_worktree.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    holder = os.path.realpath(TWHOLD)
    actor = os.path.realpath(TWACT)
    segment = VCS + " checkout -B x"
    held = dict(module.clone_worktrees(holder) or [])
    if held.get(holder) != "refs/heads/x":
        return False, "scope: the holder's worktree list reads %r for the holder, want refs/heads/x" % (held.get(holder),)
    if not module.two_worktrees_hit(segment, actor):
        return False, "scope: from the actor's tree, %r is no hit on the holder's x" % segment
    own = module.two_worktrees_hit(segment, holder)
    if own:
        return False, "own tree: from the holder's own tree, %r is a hit (%r), want no hit" % (segment, own)
    return True, "from the holder's own tree, checkout -B x is no hit; from the actor's tree it is a hit"


# =========================================================================== 1b. the pointer HEAD
