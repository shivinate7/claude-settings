# section 4855
FAMILY = "hand-made-worktree"
#
# A worktree comes only from the Agent tool's `isolation: 'worktree'` or the EnterWorktree tool
# (debt agents-write-main-clone; decision predicate-is-the-act). The act refused is a real
# `git worktree add` whose NEW TREE path resolves outside `<primary>/.claude/worktrees/`. The
# primary is the one of the repo the call acts on. A repo that sits under the guard's temp folder is
# a throwaway and passes: the rule judges the REPO, never the target, so a non-temp repo adding a
# tree INTO temp is the incident and denies.
#
# These cases run with the guard's temp folder set to ROOT/tmp. The default temp (TEMP_DIR None)
# is the system temp that holds ROOT, which would put every fixture repo "under temp".
TEMP_DIR = os.path.join(ROOT, "tmp")
HMMAIN = os.path.join(ROOT, "hmmain")                          # a primary checkout, not under temp
HMLANE = os.path.join(HMMAIN, ".claude", "worktrees", "lane1")  # a real linked tree of it, in home
HMTMPREPO = os.path.join(TEMP_DIR, "hmtmprepo")                # a repo UNDER the guard's temp folder
HMSCRATCH = slash(os.path.join(TEMP_DIR, "scratch", "lane-a"))  # a scratch target under temp
HM_AGENT = "hmagentown1"                                        # an agent id, whose home tree is built
HM_SIBLING = "hmagentsib2"                                      # a second agent id, named in the denies
HMHOME = os.path.join(HMMAIN, ".claude", "worktrees", "agent-" + HM_AGENT)  # that agent's own home
HM_GONE = "hmagentgone4"    # an agent whose home was built, recorded, then removed by the harness
HM_BADREC = "hmagentbad5"   # an agent whose home record is a folder, so reading it raises
HMGONE = os.path.join(HMMAIN, ".claude", "worktrees", "agent-" + HM_GONE)  # that agent's gone home


def _build_hand_made():
    make_repo(HMMAIN, {"f.txt": "base\n"})
    run_vcs(HMMAIN, "worktree", "add", "-q", HMLANE, "-b", "hmlane1")
    run_vcs(HMMAIN, "worktree", "add", "-q", HMHOME, "-b", "worktree-agent-" + HM_AGENT)
    # The record the guard writes on an agent's first call from its home, then the harness removes the
    # folder and its branch together. The record outlives the folder, in the clone's common directory.
    run_vcs(HMMAIN, "worktree", "add", "-q", HMGONE, "-b", "worktree-agent-" + HM_GONE)
    run_vcs(HMMAIN, "worktree", "remove", "--force", HMGONE)
    run_vcs(HMMAIN, "branch", "-D", "worktree-agent-" + HM_GONE)
    records = os.path.join(HMMAIN, ".git", "agent-homes")
    os.makedirs(records, exist_ok=True)
    write(os.path.join(records, HM_GONE), os.path.realpath(HMGONE))
    os.makedirs(os.path.join(records, HM_BADREC), exist_ok=True)  # a folder where the record should be
    make_repo(HMTMPREPO, {"f.txt": "base\n"})
    for where in (HMMAIN, HMTMPREPO):
        if run_vcs(where, "rev-parse", "--git-dir").returncode != 0:
            sys.exit("fixture setup failed in _build_hand_made: %r is no repository" % where)
    if not os.path.isdir(HMLANE):
        sys.exit("fixture setup failed in _build_hand_made: no linked tree at %r" % HMLANE)
    if not os.path.isdir(HMHOME):
        sys.exit("fixture setup failed in _build_hand_made: no agent home tree at %r" % HMHOME)
    if os.path.exists(HMGONE):
        sys.exit("fixture setup failed in _build_hand_made: the gone home still exists at %r" % HMGONE)


lazy_fixture([HMMAIN, HMLANE, HMHOME, HMTMPREPO], _build_hand_made)
HM = "hand-made-worktree"
HMADD = VCS + " worktree add "
HMIN = slash(HMMAIN)


def hm_refuse(name, command, **kw):
    kw.setdefault("cwd", HMMAIN)
    sh("hand-made worktree: " + name, command, "deny", HM, **kw)


def hm_allow(name, command, **kw):
    kw.setdefault("cwd", HMMAIN)
    sh("hand-made worktree: " + name, command, "allow", **kw)


# DENY. The new tree lands outside <primary>/.claude/worktrees/.
hm_refuse("a relative sibling path from the primary is refused", HMADD + "../lane-x")
hm_refuse("-C reaches the primary from elsewhere, and a scratch path is refused",
        VCS + " -C " + HMIN + " worktree add " + HMSCRATCH, cwd=NOGIT)
hm_refuse("cd into a non-temp primary, then a tree in the temp folder, is the incident",
        "cd " + HMIN + " && " + HMADD + HMSCRATCH, cwd=NOGIT)
hm_refuse("-b before the path does not hide it", HMADD + "-b hmx ../lane-x")
hm_refuse("-B before the path does not hide it", HMADD + "-B hmx ../lane-x")
hm_refuse("--detach before the path does not hide it", HMADD + "--detach ../lane-x")
hm_refuse("--lock --reason r before the path does not hide it",
        HMADD + "--lock --reason r ../lane-x")
hm_refuse("a double dash ends the options, and the path after it is judged",
        HMADD + "-- ../lane-x")
hm_refuse("a dash-led name after a double dash is still a path", HMADD + "-- -lane-x")
hm_refuse("a .claude/worktrees-x prefix is outside the home folder",
        HMADD + ".claude/worktrees-x/foo")
hm_refuse("a .claude/worktreesX name is outside the home folder", HMADD + ".claude/worktreesX")
hm_refuse("a dot-dot that climbs out of the home folder is outside",
        HMADD + ".claude/worktrees/../../lane-x")
hm_refuse("from inside a linked tree, a sibling of the primary is still outside",
        HMADD + "../../../lane-x", cwd=HMLANE)
hm_refuse("a PowerShell call is judged the same",
        "Set-Location " + HMIN + "; " + VCS + " worktree add ../lane-x", tool="PowerShell",
        cwd=NOGIT)
hm_refuse("a PowerShell call with -C and a scratch path is refused",
        VCS + " -C " + HMIN + " worktree add " + HMSCRATCH, tool="PowerShell", cwd=NOGIT)
hm_refuse("a Windows drive path is outside", HMADD + "C:\\scratch\\lane-a")
hm_refuse("a Git Bash drive path is outside", HMADD + "/c/scratch/lane-a")
# A cd into a variable folder is judged where the shell runs the command, so it takes the verdict of its
# literal twin. The -C form reads its variable on another branch only, so it has no row here.
hm_refuse("a variable folder, cd \"$R\", then a tree outside home is refused, as the literal cd is",
        "R=" + HMIN + "; cd \"$R\" && " + HMADD + HMSCRATCH, cwd=NOGIT)
hm_refuse("a braced variable folder, cd \"${R}\", then a tree outside home is refused",
        "R=" + HMIN + "; cd \"${R}\" && " + HMADD + HMSCRATCH, cwd=NOGIT)
hm_refuse("the literal twin: cd into the primary, then a tree outside home, is refused",
        "cd " + HMIN + " && " + HMADD + HMSCRATCH, cwd=NOGIT)
hm_refuse("a for loop that builds the tree path from its variable is the incident",
        "for c in A B; do " + VCS + " worktree add -q --detach " + HMSCRATCH + "/wt-$c $c; done")

# ALLOW. Nothing here is the act, or the act lands in the home folder, or the repo is a throwaway.
hm_allow("an absolute path under the primary's home folder passes",
         HMADD + HMIN + "/.claude/worktrees/lane2")
hm_allow("a relative path under the home folder passes", HMADD + ".claude/worktrees/lane2")
hm_allow("-b and a path under the home folder passes",
         HMADD + "-b hmlane3 .claude/worktrees/lane3")
hm_allow("from inside a linked tree of the same clone, an absolute home path passes",
         HMADD + HMIN + "/.claude/worktrees/lane4", cwd=HMLANE)
hm_allow("from inside a linked tree of the same clone, a relative home path passes",
         HMADD + "../lane5", cwd=HMLANE)
hm_allow("a repo under the guard's temp folder is a throwaway, so any target passes",
         HMADD + "../hmtmp-sibling", cwd=HMTMPREPO)
hm_allow("worktree list only reads", VCS + " worktree list")
hm_allow("worktree lock names no new tree", VCS + " worktree lock " + slash(HMLANE))
hm_allow("worktree add --help only reads", HMADD + "--help")
hm_allow("worktree add -h only reads", HMADD + "-h")
hm_allow("a help flag after the path still only reads", HMADD + "../lane-x --help")
hm_allow("an echo that only mentions it passes", 'echo "git worktree add ../x"')
hm_allow("a commit message that holds the words passes",
         VCS + ' commit -m "docs: never run git worktree add ../x by hand"')
hm_allow("a gh pr create body that holds the words passes",
         'gh pr create --draft --title t --body "the old remedy was git worktree add ../x"')
hm_allow("a heredoc body that holds the words passes",
         "cat <<'EOF'\ngit worktree add ../x\nEOF")
hm_allow("a folder that is no git tree passes, since unknown is no hit",
         HMADD + "../lane-x", cwd=NOGIT)
hm_allow("a variable folder holding the primary's home folder, cd \"$R\", then a tree in home passes",
         "R=" + HMIN + "; cd \"$R\" && " + HMADD + ".claude/worktrees/lane6", cwd=NOGIT)
hm_allow("a variable folder holding a throwaway repo, cd \"$R\", then a tree beside it passes",
         "R=" + slash(HMTMPREPO) + "; cd \"$R\" && " + HMADD + "../hmtmp-sibling", cwd=NOGIT)
hm_allow("the literal twin: cd into a throwaway repo, then a tree beside it passes",
         "cd " + slash(HMTMPREPO) + " && " + HMADD + "../hmtmp-sibling", cwd=NOGIT)

# AGENT. A call with a valid agent_id that adds a tree inside the primary's folder is refused, unless
# the tree is the agent's own recorded home or its own red-run folder. Each call runs from that home,
# so the call itself records the home, and no case depends on another case having run first.
HMAG = dict(cwd=HMHOME, agent_id=HM_AGENT)
HMWT = os.path.join(HMMAIN, ".claude", "worktrees")
HMAGENT_SIB_RED = slash(os.path.join(HMWT, "agent-" + HM_SIBLING + "-red"))
HMAGENT_PREFIX_RED = slash(os.path.join(HMWT, "agent-" + HM_AGENT + "b-red"))
HMAGENT_OWN_RED = slash(os.path.join(HMWT, "agent-" + HM_AGENT + "-red"))
HMAGENT_LANE9 = slash(os.path.join(HMWT, "lane9"))
hm_refuse("an agent adds a sibling agent's red-run folder, by absolute path, is refused",
        HMADD + HMAGENT_SIB_RED, **HMAG)
hm_refuse("an agent adds a sibling agent's red-run folder, by a relative path, is refused",
        HMADD + "../agent-" + HM_SIBLING + "-red", **HMAG)
hm_refuse("an agent adds a folder whose name only starts with its own id is refused",
        HMADD + HMAGENT_PREFIX_RED, **HMAG)
hm_refuse("an agent adds a non-agent folder, lane9, under the primary's folder is refused",
        HMADD + HMAGENT_LANE9, **HMAG)
hm_refuse("a PowerShell call by an agent, adding a sibling's red-run folder, is refused",
        HMADD + HMAGENT_SIB_RED, tool="PowerShell", **HMAG)
hm_refuse("an agent adds a tree outside the primary's folder is refused, as before",
        HMADD + slash(os.path.join(ROOT, "hm-agent-outside")), **HMAG)
# The agent's own red-run folder, added the way the test-author's red run adds it, and the agent's
# own home, both pass. The same lane9 add with no agent_id passes too, so the refusal above is the agent's.
hm_allow("an agent adds its own red-run folder, as the red run does, passes",
         HMADD + "--detach " + HMAGENT_OWN_RED + " HEAD", **HMAG)
hm_allow("an agent adds its own recorded home tree passes", HMADD + slash(HMHOME), **HMAG)
hm_allow("with no agent_id, the lane9 add from the primary passes", HMADD + HMAGENT_LANE9)
# An agent with no home record yet, called from the primary, has no home to match: a tree in the
# folder is refused, and its own red-run folder still passes. No case records this id's home.
HM_NOREC = "hmagentnr3"
HMNOREC = dict(cwd=HMMAIN, agent_id=HM_NOREC)
hm_refuse("an agent with no home record adds lane9 under the primary's folder is refused",
        HMADD + HMAGENT_LANE9, **HMNOREC)
hm_allow("an agent with no home record adds its own red-run folder, as the red run does, passes",
         HMADD + "--detach " + slash(os.path.join(HMWT, "agent-" + HM_NOREC + "-red")) + " HEAD",
         **HMNOREC)
# Only the agent's home itself passes. A tree nested inside it is a new tree in the folder.
hm_refuse("an agent adds a tree nested inside its own recorded home is refused",
        HMADD + slash(os.path.join(HMHOME, "sub")), **HMAG)

# GONE HOME. The agent's record names its home, but the folder it calls from is gone. The shell falls
# back to the primary with a `cd`, so the add still lands in the folder and must be refused.
HMGONE_CALL = dict(cwd=HMGONE, agent_id=HM_GONE)
hm_refuse("an agent whose home folder is gone adds lane9 after a cd into the primary is refused",
        "cd " + HMIN + " && " + HMADD + ".claude/worktrees/lane9", **HMGONE_CALL)
hm_allow("an agent whose home folder is gone adds its own red-run folder after a cd, passes",
         "cd " + HMIN + " && " + HMADD + "--detach .claude/worktrees/agent-" + HM_GONE + "-red HEAD",
         **HMGONE_CALL)

# AN UNREADABLE RECORD. The record path is a folder, so reading it raises and the status is unknown.
# An add inside the folder passes: nothing is known about the agent's home, and unknown is no hit.
hm_allow("an agent whose home record cannot be read adds lane9 under the primary's folder, passes",
         HMADD + HMAGENT_LANE9, cwd=HMMAIN, agent_id=HM_BADREC)

# A DOT-DOT WALK. The agent's own red-run folder is matched by name before the `..` is applied, so a
# walk out of it must not pass. The sibling's folder reached the same way is refused too. The caller
# has no home record, so the worktree-home rule, which reads a recorded home, judges nothing here.
HMDOT_CALL = dict(cwd=HMWT, agent_id=HM_NOREC)
hm_refuse("an agent walks out of its own red-run folder with .. to add lane9 is refused",
        HMADD + "./agent-" + HM_NOREC + "-red/../lane9", **HMDOT_CALL)
hm_refuse("an agent walks out of its own red-run folder with .. to add a sibling's red-run folder is refused",
        HMADD + "./agent-" + HM_NOREC + "-red/../agent-" + HM_SIBLING + "-red", **HMDOT_CALL)

# AGENT TYPE ALONE. A payload that names an agent type and no agent_id is an agent's call: other rules
# already read agent_type alone as an agent. Its tree in the folder is refused. The control with neither
# field is the lane9 add from the primary, above: "with no agent_id, the lane9 add from the primary passes".
hm_refuse("a call that names an agent_type and no agent_id adds lane9 under the primary's folder is refused",
        HMADD + HMAGENT_LANE9, agent_type="test-author")

add("hand-made worktree: an Agent call with no isolation, whose prompt names a worktree path, passes",
    "allow", tool="Agent", cwd=HMMAIN, subagent_type="general-purpose", description="lane",
    prompt="Work in the worktree at ../lane-x. Run `git worktree add ../lane-x` first.")
add("hand-made worktree: an Explore Agent call with no isolation passes", "allow", tool="Agent",
    cwd=HMMAIN, subagent_type="Explore", description="look", prompt="Read the repo.")

# VARIABLE TARGETS. The shell expands `$S` and `${S}` before git sees the path, so a target that holds a
# variable is judged by the value the same command gives it. A variable the command does not set reads as
# unknown, and a worktree add from a non-temp primary with an unknown target is refused.
HMVAR_SCRATCH = "S=" + HMSCRATCH + "; "
hm_refuse("a scratch path set in the same command, added from the non-temp primary as $S, is refused",
        HMVAR_SCRATCH + HMADD + '"$S"')
hm_refuse("a scratch path set in the same command, added from the non-temp primary as $S/lane-x, is refused",
        HMVAR_SCRATCH + HMADD + '"$S/lane-x"')
hm_refuse("a scratch path set in the same command, added from the non-temp primary as ${S}, is refused",
        HMVAR_SCRATCH + HMADD + '"${S}"')
hm_refuse("a variable this command does not set, added from the non-temp primary as $S/lane, is refused",
        HMADD + '"$S/lane"')
hm_refuse("an agent sets a variable to a tree in its folder that is not its home, and adds it, is refused",
        "S=.claude/worktrees/lane9; " + HMADD + '"$S"', **HMAG)
hm_allow("a variable set in the same command to a path under the home folder, with no agent, passes",
         "S=.claude/worktrees/lane2; " + HMADD + '"$S"')
hm_allow("a repo under the guard's temp folder adds a variable's path, and the throwaway rule passes it",
         "S=../hmtmp-sibling; " + HMADD + '"$S"', cwd=HMTMPREPO)
hm_allow("an agent sets a variable to its own red-run folder, as the red run does, and adds it, passes",
         "R=" + HMAGENT_OWN_RED + "; " + HMADD + '--detach "$R" HEAD', **HMAG)
# A variable the command never sets, in a throwaway repo: the throwaway rule judges the repo first, so the
# unknown target passes there. The refusal for an unknown target sits after that rule.
hm_allow("a repo under the guard's temp folder runs a variable target no command sets, and the throwaway rule passes it",
         HMADD + '"$S/lane"', cwd=HMTMPREPO)

# A VARIABLE IN -C. The shell expands `$R` in `-C "$R"` before git runs, so a -C target that holds a
# variable is judged as unknown, and a worktree add that reaches the primary is refused. The assignment
# may end its segment with `&&` or a newline: both pin the variable target resolved from the same command.
hm_refuse("a -C variable set in the same command, from a folder with no repo, reaches the primary and is refused",
        "R=" + HMIN + "; " + VCS + ' -C "$R" worktree add ' + HMSCRATCH, cwd=NOGIT)
hm_refuse("a scratch path set with && in the same command, added from the non-temp primary as $S, is refused",
        "S=" + HMSCRATCH + " && " + HMADD + '"$S"')
hm_refuse("a scratch path set on its own line in the same command, added from the non-temp primary as $S, is refused",
        "S=" + HMSCRATCH + "\n" + HMADD + '"$S"')
# A -C VARIABLE READ FROM THE SAME COMMAND. The -C value is resolved from an earlier assignment, so a tree
# under the primary's home folder passes, and a throwaway repo passes whatever its target is.
hm_allow("a -C variable set in the same command to the primary, with a home-folder target and no agent, passes",
         "R=" + HMIN + "; " + VCS + ' -C "$R" worktree add .claude/worktrees/lane2', cwd=NOGIT)
hm_allow("a -C variable set in the same command to a throwaway repo, with an unset target, passes",
         "R=" + slash(HMTMPREPO) + "; " + VCS + ' -C "$R" worktree add "$S/lane"', cwd=NOGIT)

TEMP_DIR = None   # back to the system temp for the sections below

# THE REFUSAL TEXT and THE POINTER REMEDY, judged on the printed reason (see the two checks below).
HM_REFUSED_PATH = "hm-text-lane"
# The call shape every EnterWorktree remedy names. A `path` makes Claude Code ask the owner to approve the worktree.
ENTER_WORKTREE_SHAPE = "with a `name` and no `path`"
# An existing checkout needs `path`, not `name`; the approval prompt a `path` triggers is the accepted cost.
OTHER_CHECKOUT_ENTER_SHAPE = "call the EnterWorktree tool with `path` set to"


def hand_made_refusal_text_case():
    """The refusal tells the next step and names neither the refused path nor the refused act."""
    got, reason = decide({
        "raw": None, "tool": "Bash", "cwd": HMMAIN, "session": None, "env_path": None,
        "temp": os.path.join(ROOT, "tmp"),
        "tool_input": {"command": HMADD + "../" + HM_REFUSED_PATH}})
    if got != "deny":
        return False, "expected deny, got %s: %s" % (got, reason[:90])
    if "Rule (hand-made worktree)" not in reason:
        return False, "the reason does not hold 'Rule (hand-made worktree)': %s" % reason[:90]
    for want in ("isolation", "EnterWorktree", ENTER_WORKTREE_SHAPE):
        if want not in reason:
            return False, "the reason does not name %r: %s" % (want, reason[:90])
    if not re.search(r"which layer", reason):
        return False, "the reason does not say to report which layer refused: %s" % reason[:90]
    for bad in (HM_REFUSED_PATH, "worktree add"):
        if bad in reason:
            return False, "the reason holds %r, which it must not" % bad
    return True, "holds 'Rule (hand-made worktree)', names isolation, EnterWorktree, its shape and the layer"


POINTER_OWN_WORKTREE_HINT = "If you already have a worktree, run `git -C <that worktree> ...`"


def pointer_remedy_names_enter_worktree_case():
    """The pointer refusal sends Claude to EnterWorktree, so it never contradicts the rule above."""
    got, reason = decide({
        "raw": None, "tool": "Bash", "cwd": PTRMAIN, "session": None, "env_path": None,
        "config": PTRCFG, "tool_input": {"command": VCS + " checkout somebranch"}})
    if got != "deny" or "Rule (pointer checkout)" not in reason:
        return False, "expected the pointer deny, got %s: %s" % (got, reason[:90])
    if "worktree add" in reason:
        return False, "the pointer remedy still names 'worktree add'"
    if "EnterWorktree" not in reason:
        return False, "the pointer remedy does not name EnterWorktree: %s" % reason[:90]
    if ENTER_WORKTREE_SHAPE not in reason:
        return False, "the pointer remedy does not say %s: %s" % (ENTER_WORKTREE_SHAPE, reason[:90])
    # An agent with no readable home record, whose shell directory reset out of its worktree, hits
    # this rule rather than rule 0, so the remedy also aims git at the worktree it already has.
    if POINTER_OWN_WORKTREE_HINT not in reason:
        return False, "the pointer remedy does not say %r: %s" % (POINTER_OWN_WORKTREE_HINT, reason[-120:])
    return True, "the pointer remedy names EnterWorktree, its call shape, the git -C hint, and no 'worktree add'"


# =========================================================================== 2. machine-wide kills
