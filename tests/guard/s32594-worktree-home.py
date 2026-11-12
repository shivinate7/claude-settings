# section 32594
FAMILY = "worktree-home"
FAMILIES["worktree-home"] = "rule 0: an agent's shell call outside its recorded home, and the path forms it reads"
XCL_ORIGIN = "https://github.com/example-owner/claude-settings.git"  # the own clone's origin
XCL_PRIMARY = os.path.join(ROOT, "xcl_primary")                     # the own clone, with that origin
XCL_LANE = os.path.join(XCL_PRIMARY, ".claude", "worktrees", "lane-a")  # its own linked worktree
XCL_NESTED = os.path.join(XCL_PRIMARY, "vendor", "nested")          # a repo inside the own checkout
XCL_SEP = os.path.join(ROOT, "xcl_sep")                             # a separate clone, same origin
XCL_SEP_SSH = os.path.join(ROOT, "xcl_sep_ssh")                     # the same repo, ssh origin
XCL_SEP_PROXY = os.path.join(ROOT, "xcl_sep_proxy")                 # the same repo, proxy URL origin
XCL_SEP_LOCAL = os.path.join(ROOT, "xcl_sep_local")                 # cloned from the own clone's path
XCL_SEP_LINKED = os.path.join(ROOT, "xcl_sep_linked")               # a linked worktree of XCL_THIRD
XCL_THIRD = os.path.join(ROOT, "xcl_third")                         # a third clone of the same repo
XCL_SEP_NOORIGIN = os.path.join(ROOT, "xcl_sep_noorigin")           # a clone with no origin at all
XCL_SEP_BADCONF = os.path.join(ROOT, "xcl_sep_badconf")             # a config file that is no config
XCL_SEP_EMPTY = os.path.join(ROOT, "xcl_sep_empty")                 # the same origin, no commit yet
XCL_DIFF = os.path.join(ROOT, "xcl_other")                          # a different repo
XCL_NEAR = os.path.join(ROOT, "xcl_near")                           # a repo name that only starts the same
XCL_PLAIN = os.path.join(ROOT, "xcl_sep_like")                      # no .git anywhere above it
XCL_TEMP = os.path.join(ROOT, "tmp")                                # the guard's temp folder for this block
XCL_TMP = os.path.join(XCL_TEMP, "xcl_tmp_clone")                   # the same repo, under the temp folder
XCL_SCRATCH = os.path.join(XCL_TEMP, FAKE_SESSION, "scratchpad", "xcl_clone")  # the session's scratchpad
XCL_KEYS = (XCL_PRIMARY, XCL_NESTED, XCL_SEP, XCL_SEP_SSH, XCL_SEP_PROXY, XCL_SEP_LOCAL, XCL_SEP_LINKED,
            XCL_SEP_NOORIGIN, XCL_SEP_BADCONF, XCL_SEP_EMPTY, XCL_DIFF, XCL_NEAR, XCL_PLAIN, XCL_TMP,
            XCL_SCRATCH)


def _xcl_clone(where, origin=None, commit=True):
    """A clone of its own, with one commit unless `commit` is False, and the origin the case names."""
    if commit:
        make_repo(where, {"src/app.py": "print(1)\n"})
    else:
        os.makedirs(where, exist_ok=True)
        init = run_vcs(where, "init", "-q", "-b", "main", ".")
        if init.returncode != 0:
            sys.exit("fixture setup failed: the init in %r: %s" % (where, init.stderr.strip()))
    if origin:
        added = run_vcs(where, "remote", "add", "origin", origin)
        if added.returncode != 0:
            sys.exit("fixture setup failed: the origin add in %r: %s" % (where, added.stderr.strip()))


def _build_separate_clones():
    """The own clone and the clones around it. Each one is named by a case; none is copied from another."""
    primary = _cross_checkout_fixture("xcl", origin=XCL_ORIGIN)[0]
    _xcl_clone(XCL_NESTED, XCL_ORIGIN)
    _xcl_clone(XCL_SEP, XCL_ORIGIN)
    _xcl_clone(XCL_SEP_SSH, "git@github.com:example-owner/claude-settings.git")
    _xcl_clone(XCL_SEP_PROXY, "http://proxy@127.0.0.1:8080/git/example-owner/claude-settings")
    _xcl_clone(XCL_SEP_NOORIGIN)
    _xcl_clone(XCL_SEP_BADCONF, XCL_ORIGIN)
    write(os.path.join(XCL_SEP_BADCONF, ".git", "config"), "this is not a git config\n")
    _xcl_clone(XCL_SEP_EMPTY, XCL_ORIGIN, commit=False)
    _xcl_clone(XCL_DIFF, "https://github.com/example-owner/other-repo.git")
    _xcl_clone(XCL_NEAR, "https://github.com/example-owner/claude-settings-old.git")
    _xcl_clone(XCL_TMP, XCL_ORIGIN)
    _xcl_clone(XCL_SCRATCH, XCL_ORIGIN)
    _xcl_clone(XCL_THIRD, XCL_ORIGIN)
    made = run_vcs(XCL_THIRD, "worktree", "add", "-q", XCL_SEP_LINKED, "-b", "xcl-linked")
    if made.returncode != 0:
        sys.exit("fixture setup failed: the worktree add at %r: %s" % (XCL_SEP_LINKED, made.stderr.strip()))
    cloned = run_vcs(ROOT, "clone", "-q", primary, XCL_SEP_LOCAL)  # its origin is the own clone's path
    if cloned.returncode != 0:
        sys.exit("fixture setup failed: the clone to %r: %s" % (XCL_SEP_LOCAL, cloned.stderr.strip()))
    write(os.path.join(XCL_PLAIN, "src", "app.py"), "print(1)\n")
    # A missing clone would also read as an allow, so a refusal row could go red for the wrong cause. Stop here.
    for where in (XCL_LANE, XCL_SEP, XCL_SEP_SSH, XCL_SEP_PROXY, XCL_SEP_LOCAL, XCL_SEP_LINKED, XCL_SEP_EMPTY):
        if not os.path.exists(os.path.join(where, ".git")):
            sys.exit("fixture setup failed: no .git at %r" % where)


lazy_fixture(XCL_KEYS, _build_separate_clones)

# The guard reads XCL_TEMP as its temp folder for every row here, so a clone under ROOT is outside it.
# Left at the system temp, the clones would sit inside it and read as throwaways.
TEMP_DIR = XCL_TEMP

# Refused: a separate clone of this repo, from the own lane, the own checkout, or a stranded cwd.
sh("other-checkout: a bare cd into a separate clone of the same repo is refused",
   "cd " + slash(XCL_SEP), "deny", "other-checkout", cwd=XCL_LANE)
sh("other-checkout: a cd into a separate clone, chained to a build, is refused",
   "cd " + slash(XCL_SEP) + " && make", "deny", "other-checkout", cwd=XCL_LANE)
sh("other-checkout: a cd into a separate clone by a relative climb is refused",
   "cd ../" + os.path.basename(XCL_SEP), "deny", "other-checkout", cwd=XCL_PRIMARY)
sh("other-checkout: a cd into a separate clone in a subshell is refused",
   "(cd %s && touch x)" % slash(XCL_SEP), "deny", "other-checkout", cwd=XCL_PRIMARY)
sh("other-checkout: a pushd into a separate clone is refused",
   "pushd " + slash(XCL_SEP), "deny", "other-checkout", cwd=XCL_PRIMARY)
sh("other-checkout: an absolute shell redirect into a separate clone, with no cd, is refused",
   "echo x > " + slash(os.path.join(XCL_SEP, "note.txt")), "deny", "other-checkout", cwd=XCL_PRIMARY)
add("other-checkout: a Write into a separate clone of the same repo is refused",
    "deny", "other-checkout", tool="Write", cwd=XCL_LANE,
    file_path=os.path.join(XCL_SEP, "note.txt"), content="x")
add("other-checkout: an Edit into a separate clone of the same repo is refused",
    "deny", "other-checkout", tool="Edit", cwd=XCL_LANE,
    file_path=os.path.join(XCL_SEP, "src", "app.py"), old_string="print(1)", new_string="print(2)")
add("other-checkout: a Write under folders that do not exist yet in a separate clone is refused",
    "deny", "other-checkout", tool="Write", cwd=XCL_PRIMARY,
    file_path=os.path.join(XCL_SEP, "new", "dir", "note.txt"), content="x")
add("other-checkout: a Write into an empty same-repo clone, with no commit yet, is refused",
    "deny", "other-checkout", tool="Write", cwd=XCL_PRIMARY,
    file_path=os.path.join(XCL_SEP_EMPTY, "note.txt"), content="x")
add("other-checkout: a Write into a linked worktree of a third clone of the same repo is refused",
    "deny", "other-checkout", tool="Write", cwd=XCL_PRIMARY,
    file_path=os.path.join(XCL_SEP_LINKED, "note.txt"), content="x")
add("other-checkout: a Write into a same-repo clone with an ssh origin is refused",
    "deny", "other-checkout", tool="Write", cwd=XCL_PRIMARY,
    file_path=os.path.join(XCL_SEP_SSH, "note.txt"), content="x")
add("other-checkout: a Write into a same-repo clone with a proxy URL origin is refused",
    "deny", "other-checkout", tool="Write", cwd=XCL_PRIMARY,
    file_path=os.path.join(XCL_SEP_PROXY, "note.txt"), content="x")
add("other-checkout: a Write into a clone cloned from the own clone's path is refused",
    "deny", "other-checkout", tool="Write", cwd=XCL_PRIMARY,
    file_path=os.path.join(XCL_SEP_LOCAL, "note.txt"), content="x")
sh("other-checkout: a cwd stranded in a separate clone refuses a relative shell write when CLAUDE_PROJECT_DIR "
   "names the home clone",
   "echo x > note.txt", "deny", "other-checkout", cwd=XCL_SEP, env={"CLAUDE_PROJECT_DIR": XCL_PRIMARY})
add("other-checkout: a cwd stranded in a separate clone refuses a relative Write when CLAUDE_PROJECT_DIR "
    "names the home clone",
    "deny", "other-checkout", tool="Write", cwd=XCL_SEP, env={"CLAUDE_PROJECT_DIR": XCL_PRIMARY},
    file_path="note.txt", content="x")
add("other-checkout: a cwd stranded in a separate clone refuses an absolute Write into that clone when "
    "CLAUDE_PROJECT_DIR names the home clone",
    "deny", "other-checkout", tool="Write", cwd=XCL_SEP, env={"CLAUDE_PROJECT_DIR": XCL_PRIMARY},
    file_path=os.path.join(XCL_SEP, "src", "app.py"), content="x")

# Allowed: the own checkout, a repo inside it, a different repo, the temp folder, a clone that cannot be
# read, and a plain folder. Each one is a false alarm the act must not raise.
add("other-checkout: a Write within its own linked worktree is allowed",
    "allow", tool="Write", cwd=XCL_LANE, file_path=os.path.join(XCL_LANE, "src", "new.txt"), content="x")
sh("other-checkout: a cd to a folder inside the own checkout is allowed",
   "cd %s && ls" % slash(os.path.join(XCL_PRIMARY, "src")), "allow", cwd=XCL_PRIMARY)
add("other-checkout: a Write into a nested repo inside the own checkout is allowed",
    "allow", tool="Write", cwd=XCL_PRIMARY, file_path=os.path.join(XCL_NESTED, "note.txt"), content="x")
sh("other-checkout: a cd into a nested repo inside the own checkout is allowed",
   "cd %s && ls" % slash(XCL_NESTED), "allow", cwd=XCL_PRIMARY)
add("other-checkout: a Write into a clone of a different repo is allowed",
    "allow", tool="Write", cwd=XCL_PRIMARY, file_path=os.path.join(XCL_DIFF, "note.txt"), content="x")
sh("other-checkout: a cd into a clone of a different repo is allowed",
   "cd %s && make" % slash(XCL_DIFF), "allow", cwd=XCL_PRIMARY)
add("other-checkout: a Write into a clone whose repo name only starts with this one's is allowed",
    "allow", tool="Write", cwd=XCL_PRIMARY, file_path=os.path.join(XCL_NEAR, "note.txt"), content="x")
add("other-checkout: a Write into a separate clone with no origin is allowed",
    "allow", tool="Write", cwd=XCL_PRIMARY, file_path=os.path.join(XCL_SEP_NOORIGIN, "note.txt"), content="x")
add("other-checkout: a Write into a separate clone whose config is unreadable is allowed",
    "allow", tool="Write", cwd=XCL_PRIMARY, file_path=os.path.join(XCL_SEP_BADCONF, "note.txt"), content="x")
add("other-checkout: a Write into a folder with no .git, named like a clone, is allowed",
    "allow", tool="Write", cwd=XCL_PRIMARY, file_path=os.path.join(XCL_PLAIN, "src", "new.txt"), content="x")
add("other-checkout: a Write into a same-repo clone under the temp folder is allowed",
    "allow", tool="Write", cwd=XCL_PRIMARY, file_path=os.path.join(XCL_TMP, "note.txt"), content="x")
add("other-checkout: a Write into a same-repo clone in this session's scratchpad is allowed",
    "allow", tool="Write", cwd=XCL_PRIMARY, session=FAKE_SESSION,
    file_path=os.path.join(XCL_SCRATCH, "note.txt"), content="x")
add("other-checkout: a Read of a separate clone is allowed",
    "allow", tool="Read", cwd=XCL_PRIMARY, file_path=os.path.join(XCL_SEP, "src", "app.py"))
sh("other-checkout: a shell read of a separate clone is allowed",
   "cat " + slash(os.path.join(XCL_SEP, "src", "app.py")), "allow", cwd=XCL_PRIMARY)
sh("other-checkout: a git read run with -C into a separate clone is allowed",
   VCS + " -C " + slash(XCL_SEP) + " log --oneline -1", "allow", cwd=XCL_PRIMARY)
add("other-checkout: a Grep into a separate clone is allowed",
    "allow", tool="Grep", cwd=XCL_PRIMARY, pattern="print", path=XCL_SEP)
sh("other-checkout: a cd word in quotes names no move into a separate clone",
   'echo "cd %s && make"' % slash(XCL_SEP), "allow", cwd=XCL_PRIMARY)
sh("other-checkout: a cd word in a comment names no move into a separate clone",
   "# cd %s\nls" % slash(XCL_SEP), "allow", cwd=XCL_PRIMARY)
sh("other-checkout: a stranded cwd with CLAUDE_PROJECT_DIR unset writes its own files",
   "echo x > note.txt", "allow", cwd=XCL_SEP, env={"CLAUDE_PROJECT_DIR": None})
add("other-checkout: a stranded cwd with CLAUDE_PROJECT_DIR unset takes a relative Write",
    "allow", tool="Write", cwd=XCL_SEP, env={"CLAUDE_PROJECT_DIR": None}, file_path="note.txt", content="x")
add("other-checkout: a cwd in a separate clone with CLAUDE_PROJECT_DIR unset takes an absolute Write into it",
    "allow", tool="Write", cwd=XCL_SEP, env={"CLAUDE_PROJECT_DIR": None},
    file_path=os.path.join(XCL_SEP, "src", "app.py"), content="x")
sh("other-checkout: a cwd in a separate clone, with CLAUDE_PROJECT_DIR naming that clone, is not stranded",
   "echo x > note.txt", "allow", cwd=XCL_SEP, env={"CLAUDE_PROJECT_DIR": XCL_SEP})
sh("other-checkout: a cwd in a separate clone, with CLAUDE_PROJECT_DIR naming a different repo, is not stranded",
   "echo x > note.txt", "allow", cwd=XCL_SEP, env={"CLAUDE_PROJECT_DIR": XCL_DIFF})
sh("other-checkout: a cwd in a separate clone, with CLAUDE_PROJECT_DIR naming a folder with no .git, is not "
   "stranded",
   "echo x > note.txt", "allow", cwd=XCL_SEP, env={"CLAUDE_PROJECT_DIR": XCL_PLAIN})
sh("other-checkout: a stranded cwd's cd back into the home clone is allowed",
   "cd " + slash(XCL_PRIMARY), "allow", cwd=XCL_SEP, env={"CLAUDE_PROJECT_DIR": XCL_PRIMARY})
sh("other-checkout: a stranded cwd's cd into a checkout of the home clone, then a command, is allowed",
   "cd %s && ls" % slash(XCL_LANE), "allow", cwd=XCL_SEP, env={"CLAUDE_PROJECT_DIR": XCL_PRIMARY})
sh("other-checkout: a stranded cwd's shell read of its own clone is allowed",
   "cat " + slash(os.path.join(XCL_SEP, "src", "app.py")), "allow", cwd=XCL_SEP,
   env={"CLAUDE_PROJECT_DIR": XCL_PRIMARY})

# Git writes from a stranded cwd, and into a separate clone from the own checkout. The verbs are
# SESSION_HOME_GIT_VERBS. The stranded refusal's reason must not read as the own checkout's.
sh("other-checkout: a git commit from a cwd stranded in a separate clone is refused when CLAUDE_PROJECT_DIR "
   "names the home clone",
   VCS + " commit -m x", "deny", "other-checkout", cwd=XCL_SEP, env={"CLAUDE_PROJECT_DIR": XCL_PRIMARY})
sh("other-checkout: a git reset --hard from a cwd stranded in a separate clone is refused when "
   "CLAUDE_PROJECT_DIR names the home clone",
   VCS + " reset --hard", "deny", "other-checkout", cwd=XCL_SEP, env={"CLAUDE_PROJECT_DIR": XCL_PRIMARY})
sh("other-checkout: a git checkout main from a cwd stranded in a separate clone is refused when "
   "CLAUDE_PROJECT_DIR names the home clone",
   VCS + " checkout main", "deny", "other-checkout", cwd=XCL_SEP, env={"CLAUDE_PROJECT_DIR": XCL_PRIMARY})
sh("other-checkout: a stranded refusal's reason does not name the checkout this session stands in",
   VCS + " commit -m x", "deny", "other-checkout", cwd=XCL_SEP, env={"CLAUDE_PROJECT_DIR": XCL_PRIMARY},
   lacks="the checkout this session stands in")
sh("other-checkout: a git -C commit into a separate clone of the same repo is refused",
   VCS + " -C " + slash(XCL_SEP) + " commit -m x", "deny", "other-checkout", cwd=XCL_PRIMARY)
sh("other-checkout: a git -C reset --hard into a separate clone of the same repo is refused",
   VCS + " -C " + slash(XCL_SEP) + " reset --hard", "deny", "other-checkout", cwd=XCL_PRIMARY)
sh("other-checkout: a stranded cwd's git status is allowed",
   VCS + " status", "allow", cwd=XCL_SEP, env={"CLAUDE_PROJECT_DIR": XCL_PRIMARY})
sh("other-checkout: a stranded cwd's git log is allowed",
   VCS + " log --oneline -1", "allow", cwd=XCL_SEP, env={"CLAUDE_PROJECT_DIR": XCL_PRIMARY})
sh("other-checkout: a stranded cwd's git fetch is allowed",
   VCS + " fetch origin", "allow", cwd=XCL_SEP, env={"CLAUDE_PROJECT_DIR": XCL_PRIMARY})
sh("other-checkout: a git -C log into a separate clone of the same repo is allowed",
   VCS + " -C " + slash(XCL_SEP) + " log --oneline -1", "allow", cwd=XCL_PRIMARY)
sh("other-checkout: a git -C show HEAD into a separate clone of the same repo is allowed",
   VCS + " -C " + slash(XCL_SEP) + " show HEAD", "allow", cwd=XCL_PRIMARY)
# `git stash create` writes a stash commit object and takes no entry, so it is a read through `git -C`
# as well. The clone's stack is judged as its own: a pop and a drop stay refused.
sh("other-checkout: a git -C stash create into a separate clone of the same repo is allowed",
   VCS + " -C " + slash(XCL_SEP) + " stash create", "allow", cwd=XCL_PRIMARY)
sh("other-checkout: a git -C stash pop into a separate clone of the same repo is refused",
   VCS + " -C " + slash(XCL_SEP) + " stash pop", "deny", "other-checkout", cwd=XCL_PRIMARY)
sh("other-checkout: a git -C stash drop into a separate clone of the same repo is refused",
   VCS + " -C " + slash(XCL_SEP) + " stash drop", "deny", "other-checkout", cwd=XCL_PRIMARY)
sh("other-checkout: a git -C commit into a clone of a different repo is allowed",
   VCS + " -C " + slash(XCL_DIFF) + " commit -m x", "allow", cwd=XCL_PRIMARY)
sh("other-checkout: a stranded cwd with CLAUDE_PROJECT_DIR unset takes a git commit",
   VCS + " commit -m x", "allow", cwd=XCL_SEP, env={"CLAUDE_PROJECT_DIR": None})

# A commit message is text. From a lane's own worktree, `../docs` resolves into the primary's
# `.claude/worktrees` folder, a folder that holds no `docs` checkout. The write scan reads the message's
# words as paths only when the scan fails closed on the text (an escaped quote, a curly quote, a line break
# or a hash inside the quotes) and the text also holds a `->` or a move-type word. The rows below are red
# on a guard that refuses that text as another checkout. A plain message and a quoted heredoc body pass
# already, so they are green controls for the same path.
UP_SEP = slash(os.path.relpath(XCL_SEP, XCL_LANE))   # the separate clone, as a path from the lane
BACKTICK = chr(96)
sh("other-checkout: a commit message naming ../docs, with an escaped quote and a move word, is allowed",
   VCS + ' commit -m "move \\"pins\\" to ../docs"', "allow", cwd=XCL_LANE)
sh("other-checkout: a commit message naming ../docs, with an escaped quote and an arrow, is allowed",
   VCS + ' commit -m "re-point \\"pins\\" -> ../docs"', "allow", cwd=XCL_LANE)
sh("other-checkout: a commit message naming ../docs, with a curly apostrophe and an arrow, is allowed",
   VCS + ' commit -m "re-point pins -> ../docs don’t"', "allow", cwd=XCL_LANE)
sh("other-checkout: a multi-line commit message naming ../docs, with an escaped quote and an arrow, is allowed",
   VCS + ' commit -m "re-point \\"pins\\" -> ../docs\n\nsee \\"walk\\""', "allow", cwd=XCL_LANE)
sh("other-checkout: a commit message naming ../docs, with an escaped quote, an arrow and a hash, is allowed",
   VCS + ' commit -m "re-point \\"pins\\" -> ../docs # not a comment"', "allow", cwd=XCL_LANE)
sh("other-checkout: a commit message naming ../docs, with no write word, is allowed",
   VCS + ' commit -m "re-point pins to ../docs"', "allow", cwd=XCL_LANE)
sh("other-checkout: a quoted heredoc commit body naming ../docs is allowed",
   VCS + " commit -F - <<'EOF'\nre-point \"pins\" -> ../docs\nEOF", "allow", cwd=XCL_LANE)
sh("other-checkout: a quoted heredoc in a substitution, naming ../docs in a commit message, is allowed",
   VCS + " commit -m \"$(cat <<'EOF'\nfix: walk ../docs\nEOF\n)\"", "allow", cwd=XCL_LANE)
sh("other-checkout: a commit message with a lone apostrophe, naming ../docs, is allowed",
   VCS + ' commit -m "re-point pins -> ../docs, don\'t"', "allow", cwd=XCL_LANE)

# Still refused: a real move into a separate clone, from the lane. A relative path to a clone is judged too,
# and so is a backtick in a message, which the shell runs as a command.
sh("other-checkout: a cd into a separate clone by a relative path, chained to a commit, is refused",
   "cd " + UP_SEP + " && " + VCS + ' commit -m "msg"', "deny", "other-checkout", cwd=XCL_LANE)
sh("other-checkout: a git -C commit into a separate clone by a relative path is refused",
   VCS + " -C " + UP_SEP + ' commit -m "msg"', "deny", "other-checkout", cwd=XCL_LANE)
sh("other-checkout: a backtick copy into a separate clone, inside a commit message, is refused",
   VCS + ' commit -m "' + BACKTICK + "cp note.txt " + UP_SEP + "/note.txt" + BACKTICK + '"',
   "deny", "other-checkout", cwd=XCL_LANE)

# Two clones whose origin is one local bare repository. A local-path origin names no owner and repo, so the
# same-repo test must read the two clones as one repo by the bare path they share.
XCL_REMOTE = os.path.join(ROOT, "xcl_remote.git")  # the bare repository both clones name as origin
XCL_BARE_A = os.path.join(ROOT, "xcl_bare_a")      # a clone whose origin is XCL_REMOTE
XCL_BARE_B = os.path.join(ROOT, "xcl_bare_b")      # a second clone whose origin is XCL_REMOTE


def _build_shared_bare_origin():
    """A bare repository, and two clones each with it as origin."""
    os.makedirs(XCL_REMOTE, exist_ok=True)
    made = run_vcs(XCL_REMOTE, "init", "-q", "--bare", ".")
    if made.returncode != 0:
        sys.exit("fixture setup failed: the bare init at %r: %s" % (XCL_REMOTE, made.stderr.strip()))
    _xcl_clone(XCL_BARE_A, XCL_REMOTE)
    _xcl_clone(XCL_BARE_B, XCL_REMOTE)


lazy_fixture((XCL_REMOTE, XCL_BARE_A, XCL_BARE_B), _build_shared_bare_origin)
add("other-checkout: a Write into a clone that shares a local bare origin with this clone is refused",
    "deny", "other-checkout", tool="Write", cwd=XCL_BARE_A,
    file_path=os.path.join(XCL_BARE_B, "note.txt"), content="x")
TEMP_DIR = None  # back to the system temp for the sections below


def xcl_override_write_case():
    """The separate-clone act is liftable: under a timed owner override a Write into a separate clone
    passes, because the owner may mean the write. Refused before the override."""
    config = ov_config("xcl-write")
    session = "ov-xcl-write"
    target = os.path.join(XCL_SEP, "note.txt")
    call = lambda s: ov_call("Write", {"file_path": target, "content": "x"}, XCL_LANE, config, session, s,
                             temp=XCL_TEMP)
    problem = ov_want(*call(0), "deny", "other-checkout")
    if problem:
        return False, "before the override: " + problem
    note = ov_type(config, session, "override 15m", 30)
    ok, why = ov_story([("under a timed override", lambda: call(60), "allow", "other-checkout")], note)
    return ok, why or "refused before the override, lifted under it"


def xcl_override_cd_case():
    """The separate-clone cd act is liftable: under a timed owner override a bare cd into a separate
    clone passes. Refused before the override."""
    config = ov_config("xcl-cd")
    session = "ov-xcl-cd"
    call = lambda s: ov_call("Bash", {"command": "cd " + slash(XCL_SEP)}, XCL_LANE, config, session, s,
                             temp=XCL_TEMP)
    problem = ov_want(*call(0), "deny", "other-checkout")
    if problem:
        return False, "before the override: " + problem
    note = ov_type(config, session, "override 15m", 30)
    ok, why = ov_story([("under a timed override", lambda: call(60), "allow", "other-checkout")], note)
    return ok, why or "refused before the override, lifted under it"


def xcl_override_stranded_case():
    """The stranded-cwd act is liftable too: under a timed owner override a relative write from a cwd
    stranded in a separate clone passes. Refused before the override."""
    config = ov_config("xcl-stranded")
    session = "ov-xcl-stranded"
    call = lambda s: ov_call("Bash", {"command": "echo x > note.txt"}, XCL_SEP, config, session, s,
                             env={"CLAUDE_PROJECT_DIR": XCL_PRIMARY}, temp=XCL_TEMP)
    problem = ov_want(*call(0), "deny", "other-checkout")
    if problem:
        return False, "before the override: " + problem
    note = ov_type(config, session, "override 15m", 30)
    ok, why = ov_story([("under a timed override", lambda: call(60), "allow", "other-checkout")], note)
    return ok, why or "refused before the override, lifted under it"


LOG_CHECKS_EXTRA.append(("other-checkout: an owner override lifts a Write into a separate clone",
                         xcl_override_write_case))
LOG_CHECKS_EXTRA.append(("other-checkout: an owner override lifts a cd into a separate clone",
                         xcl_override_cd_case))
LOG_CHECKS_EXTRA.append(("other-checkout: an owner override lifts a stranded cwd's relative write",
                         xcl_override_stranded_case))


# ------------------------------------------------------------------ other-checkout: git -C into a checkout
#
# `git -C <path>` names the folder a git verb runs in, so a verb that changes files there changes that
# checkout as `cd <path> && git <verb>` would. The cd act refuses that move; the -C form must be refused
# the same way. The -C target is read by the same resolver (`_segment_git_c_target`, through
# session_home_git_hit) and judged by the same exemptions as elsewhere() gives a cd: the agent's own
# checkout, its own red-run folder, a scratch clone under the temp folder, and for a top-level call its
# own scratchpad worktree (an agent call gets no scratchpad exemption). Each row is one registered case,
# so a failure names one form. An agent row first asserts its scope: the recording call from its own
# lane is allowed and writes its home record, so the verdict read is the agent rule's, not a missing home.
# Decision: an-agent-outside-its-home-tree-must-stop (other-checkout).
GCX_HOME = "gcxhome01"                 # the agent whose worktree is the recorded home
GCX_SIB = "gcxsib02"                   # a sibling agent's worktree: another checkout of the same clone
GCX_SESSION = "gcx-session-0001"       # a session id in the shape SESSION_ID_RE accepts
GCX_OTHER_SESSION = "gcx-session-0002"  # a second session, whose scratchpad holds none of the fixture
GCX_ORIGIN = XCL_ORIGIN                # names the scratch clones' repo, the same one as the separate-clone rows
GCX_TEMP = os.path.join(ROOT, "gcx_tmp")  # the temp folder the guard reads for these rows
GCX_FIX = {}                           # the fixture's paths, built once by _gcx_fixture
# Each @NAME in a command becomes the folder it names, so a command reads as the shell would type it.
GCX_TOKENS = (("@SCRATCH_WT", "scratch_wt"), ("@SCRATCH_CLONE", "scratch_clone"), ("@TMP_CLONE", "tmp_clone"),
              ("@PRIMARY", "primary"), ("@HOME", "home"), ("@SIB", "sib"), ("@RED", "red"), ("@EMPTY", "empty"))


def _gcx_fixture():
    """The primary checkout with the agent's lane, a sibling lane, the agent's red-run folder, a scratchpad
    worktree of the primary, a scratchpad clone of the same repo, a same-repo clone under the temp folder
    and a linked worktree on an orphan branch, which has no commit yet. Built once. Returns the paths by name."""
    if GCX_FIX:
        return GCX_FIX
    primary, home, sib, _ = _cross_checkout_fixture(
        "gcx", lanes=("agent-" + GCX_HOME, "agent-" + GCX_SIB), origin=GCX_ORIGIN)
    red = sh_add_lane(primary, "agent-" + GCX_HOME + "-red")[0]
    # A session's own lane, not an agent's: a top-level call records it as the session's home, and a session
    # record never names an agent-shaped tree (session_home_agent_tree).
    lane = sh_add_lane(primary, "lane-gcx")[0]
    pad = os.path.join(GCX_TEMP, "-home-user-claude-settings", GCX_SESSION, "scratchpad")
    scratch_wt = os.path.join(pad, "wt-notes")
    scratch_clone = os.path.join(pad, "clone")
    tmp_clone = os.path.join(GCX_TEMP, "tmp-clone")
    empty = os.path.join(primary, ".claude", "worktrees", "gcx-empty")
    os.makedirs(pad, exist_ok=True)
    added = run_vcs(primary, "worktree", "add", "-q", scratch_wt, "-b", "gcx-scratch-notes")
    if added.returncode != 0:
        sys.exit("fixture setup failed: the scratchpad worktree at %r: %s" % (scratch_wt, added.stderr.strip()))
    orphaned = run_vcs(primary, "worktree", "add", "-q", "--orphan", "-b", "gcx-empty-notes", empty)
    if orphaned.returncode != 0 or not os.path.exists(os.path.join(empty, ".git")):
        sys.exit("fixture setup failed: the orphan worktree at %r: %s" % (empty, orphaned.stderr.strip()))
    _xcl_clone(scratch_clone, GCX_ORIGIN)
    _xcl_clone(tmp_clone, GCX_ORIGIN)
    GCX_FIX.update(primary=primary, home=home, sib=sib, red=red, lane=lane, scratch_wt=scratch_wt,
                   scratch_clone=scratch_clone, tmp_clone=tmp_clone, empty=empty)
    return GCX_FIX


def _gcx_command(template):
    """TEMPLATE with each @NAME token replaced by its folder, slashed."""
    fix = _gcx_fixture()
    text = template
    for token, key in GCX_TOKENS:
        text = text.replace(token, slash(fix[key]))
    return text


def _gcx_listed(fix):
    """'' when `git worktree list` names every checkout of the fixture, else the key of the first it does not."""
    listed = run_vcs(fix["primary"], "worktree", "list", "--porcelain")
    if listed.returncode != 0:
        return "git worktree list failed: %s" % listed.stderr.strip()
    named = {os.path.realpath(line[len("worktree "):]) for line in listed.stdout.splitlines()
             if line.startswith("worktree ")}
    for key in ("primary", "home", "sib", "red", "lane", "scratch_wt", "empty"):
        if os.path.realpath(fix[key]) not in named:
            return "git worktree list does not name the %s checkout" % key
    return ""


def _gcx_scope_problem(fix):
    """'' when the agent's recording call from its own lane is allowed and writes its home record, and git
    lists every fixture checkout. A -C row reads its target as a checkout only when git lists it."""
    got, reason = _decide_full("Bash", fix["home"], agent_id=GCX_HOME, temp=GCX_TEMP, command="echo hi")
    if got != "allow":
        return "the agent's recording call: want allow, got %s (%s)" % (got, reason[:120])
    if not os.path.isfile(os.path.join(fix["primary"], ".git", "agent-homes", GCX_HOME)):
        return "the agent's recording call wrote no home record"
    return _gcx_listed(fix)


def _gcx_row(expect, cwd_key, template, agent=GCX_HOME, session=None, scope=None):
    """One case: the verdict on the command TEMPLATE from the folder named CWD_KEY ("home" or "primary"),
    as the agent GCX_HOME, or as a top-level call when AGENT is None. A deny must name other-checkout and
    no path. An allow must pass. SCOPE is the scope check of a top-level row, run where an agent row
    runs `_gcx_scope_problem`."""
    def check():
        fix = _gcx_fixture()
        if agent:
            problem = _gcx_scope_problem(fix)
            if problem:
                return False, problem
        elif scope:
            problem = scope(fix)
            if problem:
                return False, problem
        command = _gcx_command(template)
        got, reason = _decide_full("Bash", fix[cwd_key], agent_id=agent, session=session,
                                   temp=GCX_TEMP, command=command)
        if got != expect:
            return False, "%s: want %s, got %s (%s)" % (command, expect, got, reason[:120])
        if expect == "allow":
            return True, "allowed"
        names = [ROOT, slash(ROOT), GCX_TEMP, slash(GCX_TEMP)]
        names += list(fix.values()) + [slash(path) for path in fix.values()]
        problems = _other_checkout_problems(command, got, reason, names)
        return (False, "; ".join(problems)) if problems else (True, "refused as other-checkout, no path named")
    return check


def gcx_scope_case():
    """The scope the agent rows read: the agent's recording call from its own lane is allowed, writes its
    home record, and git lists every fixture checkout. A row below is read only once this holds."""
    problem = _gcx_scope_problem(_gcx_fixture())
    return (False, problem) if problem else (True, "the agent's recording call is allowed, writes its home "
                                                   "record, and git lists every checkout")


LOG_CHECKS_EXTRA.append(("other-checkout: an agent's own lane call is judged as its own checkout and records its "
                         "home", gcx_scope_case))
# Refused: an agent's git -C that changes files in another checkout of the clone, whatever form names it.
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C commit into the primary checkout is refused",
                         _gcx_row("deny", "home", "git -C @PRIMARY commit -m x")))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C add into the primary checkout is refused",
                         _gcx_row("deny", "home", "git -C @PRIMARY add f")))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's cd into its own lane, then git -C commit into the primary "
                         "checkout, is refused",
                         _gcx_row("deny", "home", "cd @HOME && git -C @PRIMARY commit -m x")))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C commit by a relative path that resolves to the "
                         "primary checkout is refused",
                         _gcx_row("deny", "home", "git -C ../../.. commit -m x")))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C commit chained to -C the primary checkout is refused",
                         _gcx_row("deny", "home", "git -C @HOME -C @PRIMARY commit -m x")))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C commit whose relative -C chain ends at the primary "
                         "checkout is refused",
                         _gcx_row("deny", "home", "git -C @PRIMARY/.claude -C .. commit -m x")))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C commit after && into the primary checkout is refused",
                         _gcx_row("deny", "home", "true && git -C @PRIMARY commit -m x")))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C commit into a sibling agent's worktree is refused",
                         _gcx_row("deny", "home", "git -C @SIB commit -m x")))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C commit into a linked worktree in its own scratchpad "
                         "is refused",
                         _gcx_row("deny", "home", "git -C @SCRATCH_WT commit -m x", session=GCX_SESSION)))
LOG_CHECKS_EXTRA.append(("other-checkout: a top-level git -C commit into a linked worktree in another session's "
                         "scratchpad is refused",
                         _gcx_row("deny", "primary", "git -C @SCRATCH_WT commit -m x", agent=None,
                                  session=GCX_OTHER_SESSION)))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C commit into a checkout with no commit yet is refused",
                         _gcx_row("deny", "home", "git -C @EMPTY commit -m x")))
# A quote, a `#` or an apostrophe inside a string is text, and the real call beside it still counts.
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C commit after an echo whose quoted text holds a # is refused",
                         _gcx_row("deny", "home", 'echo "# note" && git -C @PRIMARY commit -m x')))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C commit whose message holds a quoted apostrophe is refused",
                         _gcx_row("deny", "home", 'git -C @PRIMARY commit -m "pins, don\'t"')))
# A walk through the agent's own red-run folder name is judged on the folder it resolves to, as a cd form is:
# the `..` after the name climbs out of it. The name alone must not pass the walk.
GCX_RED_WALK = "../agent-" + GCX_HOME + "-red"
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C add by a relative walk through its own red-run folder "
                         "name to the primary checkout is refused",
                         _gcx_row("deny", "home", "git -C " + GCX_RED_WALK + "/../../.. add f")))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C commit by the same walk to the primary checkout is refused",
                         _gcx_row("deny", "home", "git -C " + GCX_RED_WALK + "/../../.. commit -m x")))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C add by the same walk ending at a sibling agent's worktree "
                         "is refused",
                         _gcx_row("deny", "home", "git -C " + GCX_RED_WALK + "/../agent-" + GCX_SIB + " add f")))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C add by an absolute walk through its own red-run folder "
                         "to the primary checkout is refused",
                         _gcx_row("deny", "home", "git -C @RED/../../.. add f")))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's cd by the same walk into the primary checkout, then git add, is "
                         "refused",
                         _gcx_row("deny", "home", "cd " + GCX_RED_WALK + "/../../.. && git add f")))
# Allowed: the agent's own checkout and red-run folder, the reads, a folder no word names, a text-only
# git -C, a scratch clone, and a -C chain whose last folder is the agent's own.
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C commit in its own worktree is allowed",
                         _gcx_row("allow", "home", "git -C @HOME commit -m x")))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C status of the primary checkout is allowed",
                         _gcx_row("allow", "home", "git -C @PRIMARY status")))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C log of the primary checkout is allowed",
                         _gcx_row("allow", "home", "git -C @PRIMARY log --oneline -1")))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C diff of the primary checkout is allowed",
                         _gcx_row("allow", "home", "git -C @PRIMARY diff")))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C add in its own red-run folder is allowed",
                         _gcx_row("allow", "home", "git -C @RED add f")))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C add in a folder under its own red-run folder is allowed",
                         _gcx_row("allow", "home", "git -C @RED/src add f")))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C commit into a folder named by an unset variable is "
                         "allowed",
                         _gcx_row("allow", "home", "git -C $GCX_TARGET commit -m x")))
LOG_CHECKS_EXTRA.append(("other-checkout: a git -C commit into the primary checkout, quoted as an echo argument, "
                         "is allowed",
                         _gcx_row("allow", "home", 'echo "git -C @PRIMARY commit -m x"')))
LOG_CHECKS_EXTRA.append(("other-checkout: a git -C commit into the primary checkout, in a comment, is allowed",
                         _gcx_row("allow", "home", "# git -C @PRIMARY commit -m x\nls")))
# A multi-line quoted string and a quoted heredoc body are text across lines, as a template literal is.
LOG_CHECKS_EXTRA.append(("other-checkout: a git -C commit into the primary checkout, in a multi-line quoted string, "
                         "is allowed",
                         _gcx_row("allow", "home", 'echo "first line\ngit -C @PRIMARY commit -m x"')))
LOG_CHECKS_EXTRA.append(("other-checkout: a git -C commit into the primary checkout, in a quoted heredoc body, is "
                         "allowed",
                         _gcx_row("allow", "home", "cat <<'EOF'\ngit -C @PRIMARY commit -m x\nEOF")))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C commit into a scratch clone in its scratchpad is allowed",
                         _gcx_row("allow", "home", "git -C @SCRATCH_CLONE commit -m x")))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C add into a scratch clone in its scratchpad is allowed",
                         _gcx_row("allow", "home", "git -C @SCRATCH_CLONE add f")))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C commit into a same-repo clone under the temp folder is "
                         "allowed",
                         _gcx_row("allow", "home", "git -C @TMP_CLONE commit -m x")))
LOG_CHECKS_EXTRA.append(("other-checkout: a git -C chain that ends at the agent's own lane is allowed after a -C "
                         "into the primary checkout",
                         _gcx_row("allow", "home", "git -C @PRIMARY -C @HOME commit -m x")))
# A top-level call (no agent_id) passes its own scratchpad worktree and clone, as elsewhere() gives it.
LOG_CHECKS_EXTRA.append(("other-checkout: a top-level git -C commit into a linked worktree in its own scratchpad is "
                         "allowed",
                         _gcx_row("allow", "primary", "git -C @SCRATCH_WT commit -m x", agent=None,
                                  session=GCX_SESSION)))
LOG_CHECKS_EXTRA.append(("other-checkout: a top-level git -C commit into a clone in its own scratchpad is allowed",
                         _gcx_row("allow", "primary", "git -C @SCRATCH_CLONE commit -m x", agent=None,
                                  session=GCX_SESSION)))

# ------------------------------------------------------------------ other-checkout: git -C verbs
#
# The rows pin other_checkout_hit's `git -C` judgment. It judges `git -C <other checkout>` for every verb in
# OTHER_CHECKOUT_GIT_VERBS, including the verbs that change a checkout's files or index without moving a branch
# (`rm`, `mv`, `update-index`, `read-tree`, `checkout-index`), and passes the reads. The -C form gets the verdict
# the cd form gets: `git -C <primary> rm f` is refused as `cd <primary> && git rm f` is. A `git -C` into a
# session's recorded lane is refused as its `cd && git` form is, so no row asks it to pass.
GCX_TOP_SESSION = "gcx-session-0003"  # a session whose top-level call from its own lane records that lane


def _gcx_top_lane_scope(fix):
    """'' when a top-level call from the session's lane is allowed and records that lane as the session's
    home, else the problem. A top-level row reads its verdict only once this holds."""
    got, reason = _decide_full("Bash", fix["lane"], session=GCX_TOP_SESSION, temp=GCX_TEMP, command="echo hi")
    if got != "allow":
        return "the session's recording call: want allow, got %s (%s)" % (got, reason[:120])
    if not sh_holds(fix["primary"], GCX_TOP_SESSION, fix["lane"]):
        return "the session's recording call wrote no session record naming its lane"
    return ""


# Refused: a git verb that changes a checkout's files or index, run by `git -C` into the primary checkout,
# by an absolute path or a relative one that resolves there.
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C rm in the primary checkout, by a relative path that "
                         "resolves there, is refused",
                         _gcx_row("deny", "home", "git -C ../../.. rm f")))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C mv in the primary checkout is refused",
                         _gcx_row("deny", "home", "git -C @PRIMARY mv a b")))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C update-index in the primary checkout is refused",
                         _gcx_row("deny", "home", "git -C @PRIMARY update-index --add f")))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C read-tree in the primary checkout is refused",
                         _gcx_row("deny", "home", "git -C @PRIMARY read-tree HEAD")))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C checkout-index in the primary checkout is refused",
                         _gcx_row("deny", "home", "git -C @PRIMARY checkout-index -a")))
# The cd form of the rm row is refused, and the git -C rm above is refused the same way.
LOG_CHECKS_EXTRA.append(("the cd form of the git -C rm row: an agent's cd into the primary checkout, then git rm, is "
                         "refused",
                         _gcx_row("deny", "home", "cd @PRIMARY && git rm f")))
# Allowed: the reads of the primary checkout, by an absolute path and by a relative one.
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C ls-files of the primary checkout is allowed",
                         _gcx_row("allow", "home", "git -C @PRIMARY ls-files")))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C ls-files by a relative path to the primary checkout "
                         "is allowed",
                         _gcx_row("allow", "home", "git -C ../../.. ls-files")))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C status by a relative path to the primary checkout "
                         "is allowed",
                         _gcx_row("allow", "home", "git -C ../../.. status")))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C rev-parse of the primary checkout is allowed",
                         _gcx_row("allow", "home", "git -C @PRIMARY rev-parse HEAD")))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's git -C show of the primary checkout is allowed",
                         _gcx_row("allow", "home", "git -C @PRIMARY show HEAD")))
# A top-level call whose session record names its own lane still gets no exemption for a sibling agent's
# home: the git -C commit is refused. Scope first: the session's recording call from its lane writes the record.
LOG_CHECKS_EXTRA.append(("other-checkout: a top-level git -C commit into a sibling agent's home, with a session record "
                         "naming another lane, is refused",
                         _gcx_row("deny", "primary", "git -C @SIB commit -m x", agent=None,
                                  session=GCX_TOP_SESSION, scope=_gcx_top_lane_scope)))

# env -C and env --chdir set the folder the git after them runs in, so a git verb that env moves into a
# checkout is judged there, as the git -C form is. Each row is one spelling, so a failure names one form.
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's env -C commit into the primary checkout is refused",
                         _gcx_row("deny", "home", "env -C @PRIMARY git commit -m x")))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's env --chdir add in the primary checkout is refused",
                         _gcx_row("deny", "home", "env --chdir @PRIMARY git add f")))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's env --chdir=<path> add in the primary checkout is refused",
                         _gcx_row("deny", "home", "env --chdir=@PRIMARY git add f")))
# Read from the agent's home, the git -C part alone stays inside the home, so only the env -C climb reaches
# the primary checkout.
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's env -C then git -C, two relative folders that together reach "
                         "the primary checkout, is refused",
                         _gcx_row("deny", "home", "env -C ../../.. git -C . rm f")))
# These rows pin the allows the guard must keep, so each is a guard, not a red case.
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's env -C status of the primary checkout is allowed",
                         _gcx_row("allow", "home", "env -C @PRIMARY git status")))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's env -C commit into a variable folder is allowed",
                         _gcx_row("allow", "home", 'env -C "$WT" git commit -m x')))
LOG_CHECKS_EXTRA.append(("other-checkout: an agent's env -C commit into its own home is allowed",
                         _gcx_row("allow", "home", "env -C @HOME git commit -m x")))
def _guard_core_under_test():
    """The guard_core module the run-folder rows read: the folder of GUARD, loaded fresh on each call, so a
    GUARD_UNDER_TEST copy is the one read."""
    import importlib.util
    folder = os.path.dirname(GUARD)
    if folder not in sys.path:
        sys.path.insert(0, folder)
    spec = importlib.util.spec_from_file_location("guard_core_under_test", os.path.join(folder, "guard_core.py"))
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)
    return core


def run_dir_env_c_case():
    """_run_dir returns the folder an `env -C <dir>` names, as it returns the folder a `git -C <dir>` names.
    The git -C form is the control and pins the reader's answer; the env -C form must match it, not the cwd.
    guard_core loads from the folder of GUARD, so a GUARD_UNDER_TEST copy is the one read. Both folders are
    named under ROOT, the run folder, and nothing is read or written on disk."""
    core = _guard_core_under_test()
    target = os.path.join(ROOT, "run-dir-target")
    cwd = os.path.join(ROOT, "run-dir-cwd")
    control = core._run_dir("git -C \"%s\" status" % slash(target), cwd)
    if os.path.normpath(control) != os.path.normpath(target):
        return False, "control: git -C reads %s, want %s" % (control, target)
    got = core._run_dir("env -C \"%s\" git status" % slash(target), cwd)
    if os.path.normpath(got) != os.path.normpath(target):
        return False, "env -C reads %s, want %s (the cwd is %s)" % (got, target, cwd)
    return True, "env -C and git -C both read the named folder"


LOG_CHECKS_EXTRA.append(("other-checkout: _run_dir reads the folder an env -C names, as it reads a git -C",
                         run_dir_env_c_case))


# THE RUN FOLDER OF A COMMAND TYPED FROM A LINKED LANE. _run_dir names the folder each spelling runs in: a
# relative env -C joins onto the folder the earlier cd left, not the shell cwd, and a cd after an env -C sets
# the folder over it. Each row is one spelling, so a failure names one form. Scope before subject (P7): the
# plain cd into the primary is read first, and a row reports on its own spelling only when that cd reads right.
RUN_DIR_PRIM = os.path.join(ROOT, "run-dir-prim")   # the primary checkout
RUN_DIR_LANE = os.path.join(ROOT, "run-dir-lane")   # the linked lane the command is typed from
RUN_DIR_CLEAN = os.path.join(ROOT, "run-dir-clean")  # another folder, neither the primary nor the lane


def _run_dir_names(command, want, cause):
    """_run_dir of `command`, typed from RUN_DIR_LANE, names `want`. `cause` is the one misreading a miss shows."""
    core = _guard_core_under_test()
    scope = core._run_dir("cd %s && git status" % slash(RUN_DIR_PRIM), RUN_DIR_LANE)
    if os.path.normpath(scope) != os.path.normpath(RUN_DIR_PRIM):
        return False, "scope: a plain cd into the primary checkout reads %s, want %s" % (scope, RUN_DIR_PRIM)
    got = core._run_dir(command, RUN_DIR_LANE)
    if os.path.normpath(got) != os.path.normpath(want):
        return False, "%s: _run_dir reads %s, want %s" % (cause, got, want)
    return True, "_run_dir reads %s for: %s" % (want, command)


def _run_dir_row(command, want, cause):
    """One row: a zero-argument case that runs _run_dir_names on one spelling."""
    return lambda: _run_dir_names(command, want, cause)


_RELATIVE_ENV_C = "a relative env -C joined onto the shell cwd, not onto the folder the earlier cd left"
LOG_CHECKS_EXTRA.append(("other-checkout: _run_dir joins a relative env -C onto the folder an earlier cd left",
                         _run_dir_row("cd %s && env -C . git status" % slash(RUN_DIR_PRIM), RUN_DIR_PRIM,
                                      _RELATIVE_ENV_C)))
LOG_CHECKS_EXTRA.append(("other-checkout: _run_dir joins a relative env -C sub onto the folder an earlier cd left",
                         _run_dir_row("cd %s && env -C sub git status" % slash(RUN_DIR_PRIM),
                                      os.path.join(RUN_DIR_PRIM, "sub"), _RELATIVE_ENV_C)))
LOG_CHECKS_EXTRA.append(("other-checkout: _run_dir lets a cd after an env -C decide the folder over the env -C",
                         _run_dir_row("env -C %s git status && cd %s && git status"
                                      % (slash(RUN_DIR_LANE), slash(RUN_DIR_PRIM)),
                                      RUN_DIR_PRIM, "an env -C folder beat the cd after it")))
# A guard row: an env -C of the primary checkout alone must be read as the primary, or the guard judges the wrong checkout.
LOG_CHECKS_EXTRA.append(("other-checkout guard: _run_dir reads an env -C of the primary checkout as the primary",
                         _run_dir_row("env -C %s git status" % slash(RUN_DIR_PRIM), RUN_DIR_PRIM,
                                      "an env -C of the primary checkout was read as something else")))

# An env -C moves only the program it runs. Its folder reaches a bare git that follows it only when EVERY git
# segment of the command carries an env -C folder. Otherwise a bare git runs in the shell's folder: the cwd,
# or the folder the last cd left. The three red rows are the three places a bare git can sit beside an env -C
# into another folder: after it, after a cd and it, and ahead of it. Each row is one spelling, so a failure
# names one form.
LOG_CHECKS_EXTRA.append(("other-checkout: _run_dir reads a bare git after an env -C into another folder in the shell's folder",
                         _run_dir_row("env -C %s git status && git log" % slash(RUN_DIR_CLEAN), RUN_DIR_LANE,
                                      "a bare git after an env -C reads the env folder, as if the env -C moved the shell")))
LOG_CHECKS_EXTRA.append(("other-checkout: _run_dir reads a bare git after a cd and an env -C in the cd's folder",
                         _run_dir_row("cd %s && env -C %s git status && git log" % (slash(RUN_DIR_PRIM), slash(RUN_DIR_CLEAN)),
                                      RUN_DIR_PRIM,
                                      "a bare git after a cd and an env -C reads the env folder, as if the env -C moved the shell past the cd")))
LOG_CHECKS_EXTRA.append(("other-checkout: _run_dir reads a bare git ahead of an env -C into another folder in the shell's folder",
                         _run_dir_row("git status && env -C %s git log" % slash(RUN_DIR_CLEAN), RUN_DIR_LANE,
                                      "a bare git ahead of an env -C reads the env folder, as if the env -C moved the shell for it")))
# The guards below pin what each red row must keep. A git -C under an env -C joins onto that env folder, and a
# relative one chains onto it. A non-git env -C moves nothing. A relative git -C after a cd reads the shell's
# folder, and a git -C ahead of a cd keeps its folder over the cd. With an env -C on every git segment, the last
# env -C folder is read.
LOG_CHECKS_EXTRA.append(("other-checkout guard: _run_dir joins a git -C onto the env -C folder of its own segment",
                         _run_dir_row("env -C a git -C b status", os.path.join(RUN_DIR_LANE, "a", "b"),
                                      "a git -C under an env -C was not joined onto that env folder")))
LOG_CHECKS_EXTRA.append(("other-checkout guard: _run_dir reads a git after an env -C of a non-git program as the shell's folder",
                         _run_dir_row("env -C %s true && git status" % slash(RUN_DIR_PRIM), RUN_DIR_LANE,
                                      "an env -C of a non-git program moved the shell's folder")))
LOG_CHECKS_EXTRA.append(("other-checkout guard: _run_dir reads a relative git -C after a cd in the shell's folder",
                         _run_dir_row("cd %s && git -C . status" % slash(RUN_DIR_PRIM), RUN_DIR_LANE,
                                      "a relative git -C after a cd joined onto the cd folder, not the shell's folder")))
LOG_CHECKS_EXTRA.append(("other-checkout guard: _run_dir reads a git -C ahead of a cd in its own folder, not the cd's",
                         _run_dir_row("git -C %s status && cd %s && git status" % (slash(RUN_DIR_LANE), slash(RUN_DIR_PRIM)),
                                      RUN_DIR_LANE,
                                      "a cd after a git -C decided the folder over the git -C")))
LOG_CHECKS_EXTRA.append(("other-checkout guard: _run_dir reads the last env -C folder when every git segment carries one",
                         _run_dir_row("env -C %s git status && env -C %s git log" % (slash(RUN_DIR_PRIM), slash(RUN_DIR_CLEAN)),
                                      RUN_DIR_CLEAN,
                                      "with an env -C on every git segment, the first env -C folder was read, not the last")))


# The checkers that read the log. THE COUNT IS READ FROM THIS LIST, never written beside it: a
# literal count drifts the moment a case is added, and a suite that miscounts its own cases is a
# suite a reader stops trusting.
