# section 43502
FAMILY = "amend-foreign-head"  # rule amend-foreign-head: a Bash `git commit --amend` on a commit this checkout did not make

# A Bash `git commit --amend` is refused when HEAD's commit was not made by this checkout. An own entry (`commit:` or
# `commit (amend):`) whose new sha is HEAD allows the amend. Any other route to HEAD (a clone, a reset, a switch, a
# pull, a cherry-pick) refuses it. The `-C` form reads the same target, through a folder inside the checkout.
#
# Not pinned, because another rule refuses these first on the old guard. An agent's call outside its own home is
# refused by worktree-home, and a `-C` into another checkout of the clone by other-checkout. So a home-based deny
# cannot be this rule's red. The session form (no agent_id, in another agent's worktree, the literal incident) is in
# no rule's reach on the old guard, and is left for the owner to rule.
#
# The fixtures are real checkouts under the run folder. TEMP_DIR points the guard's temp folder elsewhere, so no
# fixture reads as a throwaway repo, as in the hand-made worktree section.
TEMP_DIR = os.path.join(ROOT, "tmp")

AF_RULE = "amend-foreign-head"
AMROOT = os.path.join(ROOT, "amendfh")
AF_OTHER = os.path.join(AMROOT, "other")          # main holds a commit this checkout never made
AF_OWN = os.path.join(AMROOT, "own")              # HEAD made by a plain commit here
AF_OWN_AMEND = os.path.join(AMROOT, "own-amend")  # HEAD made by an amend here
AF_CLONE = os.path.join(AMROOT, "clone")          # a fresh clone of AF_OWN: HEAD's reflog says clone
AF_RESET = os.path.join(AMROOT, "reset")          # an own commit, then reset --hard to AF_OTHER's commit
AF_SWITCH = os.path.join(AMROOT, "switch")        # checkout -b onto AF_OTHER's commit
AF_PULLSRC = os.path.join(AMROOT, "pullsrc")      # the origin of AF_PULL, one commit ahead of its clone
AF_PULL = os.path.join(AMROOT, "pull")            # a clone of AF_PULLSRC, fast-forwarded: HEAD says pull
AF_CHERRY = os.path.join(AMROOT, "cherry")        # AF_OTHER's commit cherry-picked here: HEAD says cherry-pick
AF_LONG = os.path.join(AMROOT, "long")            # the own commit sits far down a long reflog, HEAD still on it
AF_NOHEAD = os.path.join(AMROOT, "nohead")        # a repo with no commit at all

AM_PRIMARY = os.path.join(AMROOT, "amprimary")    # a primary checkout that holds two agent homes
AM_OTHER_AGENT = "amother1"
AM_CALLER_AGENT = "amcaller2"
AM_OTHER_HOME = os.path.join(AM_PRIMARY, ".claude", "worktrees", "agent-" + AM_OTHER_AGENT)
AM_CALLER_HOME = os.path.join(AM_PRIMARY, ".claude", "worktrees", "agent-" + AM_CALLER_AGENT)


def _af_reflog(where):
    """HEAD's reflog subjects in `where`, newest first."""
    return run_vcs(where, "reflog", "show", "--format=%gs", "HEAD").stdout.splitlines()


def _af_scope(where, want, depth=0):
    """Stop the suite unless HEAD's reflog in `where` holds a subject that starts with `want`, at least `depth`
    entries down. Scope comes before subject: a fixture that lost its entry would pass its cases for the wrong reason."""
    subjects = _af_reflog(where)
    hits = [index for index, subject in enumerate(subjects) if subject.startswith(want)]
    if not hits or hits[0] < depth:
        sys.exit("fixture setup failed in the amend-foreign-head fixtures: no %r entry at depth %d in HEAD's reflog "
                 "of %r: %r" % (want, depth, where, subjects[:4]))


def _build_amend_foreign_head():
    make_repo(AF_OTHER, {"g.txt": "x\n"})
    _rr_commit(AF_OTHER, {"g.txt": "x2\n"}, "other: the commit this checkout never made")

    make_repo(AF_OWN, {"f.txt": "a\n"})
    _rr_commit(AF_OWN, {"f.txt": "b\n"}, "own: a commit made here")
    _af_scope(AF_OWN, "commit:")
    os.makedirs(os.path.join(AF_OWN, "sub"), exist_ok=True)

    make_repo(AF_OWN_AMEND, {"k.txt": "a\n"})
    _rr_commit(AF_OWN_AMEND, {"k.txt": "b\n"}, "own: before the amend")
    _rr_run(AF_OWN_AMEND, "commit", "-q", "--amend", "-m", "own: after the amend")
    _af_scope(AF_OWN_AMEND, "commit (amend):")

    _rr_run(AMROOT, "clone", "-q", AF_OWN, AF_CLONE)
    _af_scope(AF_CLONE, "clone:")
    os.makedirs(os.path.join(AF_CLONE, "sub"), exist_ok=True)

    make_repo(AF_RESET, {"r.txt": "a\n"})
    _rr_commit(AF_RESET, {"r.txt": "b\n"}, "own: then reset off it")
    _rr_run(AF_RESET, "fetch", "-q", AF_OTHER, "main")
    _rr_run(AF_RESET, "reset", "-q", "--hard", "FETCH_HEAD")
    _af_scope(AF_RESET, "reset:")

    make_repo(AF_SWITCH, {"s.txt": "a\n"})
    _rr_run(AF_SWITCH, "fetch", "-q", AF_OTHER, "main")
    _rr_run(AF_SWITCH, "checkout", "-q", "-b", "elsewhere", "FETCH_HEAD")
    _af_scope(AF_SWITCH, "checkout:")

    make_repo(AF_PULLSRC, {"p.txt": "a\n"})
    _rr_run(AMROOT, "clone", "-q", AF_PULLSRC, AF_PULL)
    _rr_commit(AF_PULLSRC, {"p.txt": "b\n"}, "upstream: one commit ahead")
    _rr_run(AF_PULL, "pull", "-q", "--ff-only")
    _af_scope(AF_PULL, "pull")

    make_repo(AF_CHERRY, {"g.txt": "x\n"})
    _rr_run(AF_CHERRY, "fetch", "-q", AF_OTHER, "main")
    _rr_run(AF_CHERRY, "cherry-pick", "FETCH_HEAD")
    _af_scope(AF_CHERRY, "cherry-pick")

    make_repo(AF_LONG, {"l.txt": "a\n"})
    _rr_commit(AF_LONG, {"l.txt": "b\n"}, "own: the one far back")
    _rr_run(AF_LONG, "checkout", "-q", "-b", "side")
    for _ in range(40):
        _rr_run(AF_LONG, "checkout", "-q", "main")
        _rr_run(AF_LONG, "checkout", "-q", "side")
    _rr_run(AF_LONG, "checkout", "-q", "main")
    _af_scope(AF_LONG, "commit:", depth=60)

    os.makedirs(AF_NOHEAD, exist_ok=True)
    _rr_run(AF_NOHEAD, "init", "-q", "-b", "main", ".")
    if run_vcs(AF_NOHEAD, "rev-parse", "--verify", "-q", "HEAD").returncode == 0:
        sys.exit("fixture setup failed in the amend-foreign-head fixtures: %r has a HEAD" % AF_NOHEAD)


def _build_amend_homes():
    make_repo(AM_PRIMARY, {"f.txt": "base\n"})
    _rr_run(AM_PRIMARY, "worktree", "add", "-q", AM_OTHER_HOME, "-b", "worktree-agent-" + AM_OTHER_AGENT)
    _rr_run(AM_PRIMARY, "worktree", "add", "-q", AM_CALLER_HOME, "-b", "worktree-agent-" + AM_CALLER_AGENT)
    _rr_commit(AM_OTHER_HOME, {"h.txt": "other\n"}, "other agent: work in its own home")
    _rr_commit(AM_CALLER_HOME, {"c.txt": "caller\n"}, "caller agent: work in its own home")
    _af_scope(AM_OTHER_HOME, "commit:")
    _af_scope(AM_CALLER_HOME, "commit:")
    # The home record each agent's call reads: the clone's common directory names the agent's own home.
    records = os.path.join(AM_PRIMARY, ".git", "agent-homes")
    write(os.path.join(records, AM_OTHER_AGENT), os.path.realpath(AM_OTHER_HOME))
    write(os.path.join(records, AM_CALLER_AGENT), os.path.realpath(AM_CALLER_HOME))


lazy_fixture([AF_OTHER, AF_OWN, AF_OWN_AMEND, AF_CLONE, AF_RESET, AF_SWITCH, AF_PULLSRC, AF_PULL, AF_CHERRY,
              AF_LONG, AF_NOHEAD], _build_amend_foreign_head)
lazy_fixture([AM_PRIMARY, AM_OTHER_HOME, AM_CALLER_HOME], _build_amend_homes)


def af_refuse(name, command, cwd, **kw):
    sh("amend-foreign-head: " + name, command, "deny", AF_RULE, cwd=cwd, **kw)


def af_allow(name, command, cwd, **kw):
    sh("amend-foreign-head: " + name, command, "allow", cwd=cwd, **kw)


AMEND = VCS + " commit --amend --no-edit"

# DENY, Tier A. HEAD got there by a route that is no own commit entry whose new sha is HEAD.
af_refuse("a fresh clone's HEAD, git commit --amend --no-edit", AMEND, AF_CLONE)
af_refuse("a fresh clone's HEAD, git commit --amend -m", VCS + ' commit --amend -m "reword"', AF_CLONE)
af_refuse("a fresh clone's HEAD, with -q before --amend", VCS + " commit -q --amend --no-edit", AF_CLONE)
af_refuse("a fresh clone's HEAD, with --amend -C HEAD", VCS + " commit --amend -C HEAD", AF_CLONE)
af_refuse("a fresh clone's HEAD, after git add in the same call",
          VCS + " add f.txt && " + AMEND, AF_CLONE)
af_refuse("HEAD reset off an own commit onto another checkout's commit", AMEND, AF_RESET)
af_refuse("HEAD switched onto a branch made in another checkout", AMEND, AF_SWITCH)
af_refuse("HEAD fast-forwarded by a pull", AMEND, AF_PULL)
af_refuse("HEAD cherry-picked from another checkout", AMEND, AF_CHERRY)
af_refuse("-C names a folder inside the HEAD-foreign checkout",
          VCS + " -C " + slash(os.path.join(AF_CLONE, "sub")) + " commit --amend --no-edit", AF_CLONE)

# ALLOW, the green controls. HEAD is a commit this checkout made, or the checkout is the caller's own home.
af_allow("HEAD made by a plain commit here, git commit --amend --no-edit", AMEND, AF_OWN)
af_allow("HEAD made by a plain commit here, git commit --amend -m", VCS + ' commit --amend -m "reword"', AF_OWN)
af_allow("HEAD made by an earlier amend here", AMEND, AF_OWN_AMEND)
af_allow("the own commit far down a long reflog, HEAD still on it", AMEND, AF_LONG)
af_allow("a repo with no HEAD: git has nothing to amend, and unknown is no hit", AMEND, AF_NOHEAD)
af_allow("-C names a folder inside the own checkout",
         VCS + " -C " + slash(os.path.join(AF_OWN, "sub")) + " commit --amend --no-edit", AF_OWN)
af_allow("the home's own agent amends the commit it made in its own home",
         AMEND, AM_OTHER_HOME, agent_id=AM_OTHER_AGENT)
af_allow("the caller amends the commit it made in its own home", AMEND, AM_CALLER_HOME,
         agent_id=AM_CALLER_AGENT)

TEMP_DIR = None   # back to the system temp for the sections below
