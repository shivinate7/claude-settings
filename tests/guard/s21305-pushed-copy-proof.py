# section 21305
#
# THE PUSHED-COPY PROOF'S READ COUNT AND ITS CLOCK (dirty_paths_are_pushed_copies, hooks/git_reads.py). The proof
# reads every candidate tree while any dirty path stays unmatched. A path whose worktree entry differs from its index
# entry can never match, so a tree with an edit in no commit reads every candidate, each one an `ls-tree` over all of
# the tree's paths. On a large tree that outlasts the PreToolUse hook's timeout, and a timed-out guard lets the call
# through. So the proof must answer False at once when a path can never match, and must answer False once its deadline
# has passed, between candidate reads.
#
# THE CONTRACT THE BUILDER MEETS. `git_reads._now` is a zero-argument callable that returns seconds (time.monotonic by
# default). The proof reads it at entry and before each candidate's `ls-tree`. Past its deadline it answers False. The
# cases install `_now` with mock.patch.object(..., create=True), so on a head without the seam they run and assert,
# and do not crash.
#
# NO CASE WAITS. The fake clock stands at 0 until the first `ls-tree` has run. Then it jumps by PROOF_TRIP_SECONDS, far
# past any budget, so no case encodes a budget's value. The cases read answers and read counts, never seconds, except
# the budget-against-timeout case at the end, which asserts only an inequality between the budget and the guard hook's
# timeout, both read from settings.json.

PD_MANY = 250  # past the 200 paths the removed cap held
PD_EDITS = os.path.join(ROOT, "pd-edits")      # PD_MANY edits, each in no commit, on a pushed branch
PD_STAGED = os.path.join(ROOT, "pd-staged")    # the same paths, staged, so each index blob is in no commit
PROOF_TRIP_SECONDS = 1e9  # far past any deadline a budget gives


def _grow_history(where, branch):
    """Four pushed commits, each on its own file: four more reflog commits the proof can read."""
    for i in range(4):
        name = "history%d.txt" % i
        write(os.path.join(where, name), "history %d\n" % i)
        _base_git(where, "add", name)
        _base_git(where, *IDENT, "commit", "-q", "-m", "history %d on %s" % (i, branch))
    _base_git(where, "push", "-q", "origin", branch)


def _build_proof_trees():
    """Two trees of PD_MANY paths, each a worktree of BCMAIN pushed at its base, then four more pushed commits.
    PD_EDITS edits every path in no commit. PD_STAGED stages the same edits, so each index blob is in no commit."""
    materialize(BCMAIN)
    for where, branch in ((PD_EDITS, "pd-edits"), (PD_STAGED, "pd-staged")):
        _base_copy_tree(where, branch, many=PD_MANY, moved=False)
        _grow_history(where, branch)
    for name in _numbered_paths(PD_MANY):
        write(os.path.join(PD_EDITS, name), "edit %s, in no commit\n" % name)
        write(os.path.join(PD_STAGED, name), "staged %s, in no commit\n" % name)
    _base_git(PD_STAGED, "add", "-A")


lazy_fixture([PD_EDITS, PD_STAGED], _build_proof_trees)


def _proof_scope(tree, status, reflog_min=0):
    """None when TREE holds the status lines named, is pushed whole, and has at least REFLOG_MIN distinct commits in
    HEAD's reflog (0 skips that read). Otherwise the one thing that differs. A case reads its scope before its subject."""
    lines = sorted(_porcelain(tree))
    if lines != sorted(status):
        return "%s holds %d status line(s), want the %d named" % (tree, len(lines), len(status))
    unpushed = run_vcs(tree, "rev-list", "HEAD", "--not", "--remotes").stdout.split()
    if unpushed:
        return "%s has %d commit(s) of HEAD on no remote-tracking ref, want none" % (tree, len(unpushed))
    commits = set(run_vcs(tree, "log", "-g", "--format=%H", "HEAD").stdout.split())
    if len(commits) < reflog_min:
        return "%s has %d distinct reflog commit(s), want at least %d" % (tree, len(commits), reflog_min)
    return None


def _proof_read(tree, trip, budget=None, module_at=None, config_dir=None):
    """(answer, candidate reads) of the proof on TREE, with `git_reads._now` installed at 0. With TRIP, the first
    `ls-tree` the proof makes moves the clock past every deadline, so from the next candidate on the proof must answer
    as it does past its budget. BUDGET, when given, stands in for `_proof_budget`. MODULE_AT, when given, is the path
    the module is taken to live at, so the real `_proof_budget` reads from there. CONFIG_DIR is the CLAUDE_CONFIG_DIR
    the budget may read; left None it is the repo, whose settings.json the real module reads from its own folder. Each
    git read is counted. Nothing sleeps and no real clock is read."""
    git_reads = _load_git_reads()
    lines = _porcelain(tree)
    now, ls_trees = [0.0], []
    real_git = git_reads._git

    def counting_git(where, *args):
        answer = real_git(where, *args)
        if "ls-tree" in args:
            ls_trees.append(args)
            if trip and len(ls_trees) == 1:
                now[0] = PROOF_TRIP_SECONDS
        return answer

    git_reads._git = counting_git
    try:
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": REPO if config_dir is None else config_dir}), \
                mock.patch.object(git_reads, "_now", lambda: now[0], create=True), \
                mock.patch.object(git_reads, "_proof_budget",
                                  git_reads._proof_budget if budget is None else budget), \
                mock.patch.object(git_reads, "__file__", git_reads.__file__ if module_at is None else module_at):
            got = git_reads.dirty_paths_are_pushed_copies(tree, lines)
    finally:
        git_reads._git = real_git
    return got, len(ls_trees)


def base_copies_edits_no_candidate_case():
    """PD_MANY paths, each an edit in no commit, on a tree with several candidates: the proof answers False at once."""
    materialize(PD_EDITS)
    scope = _proof_scope(PD_EDITS, [" M " + name for name in _numbered_paths(PD_MANY)], reflog_min=3)
    if scope:
        return False, "scope: " + scope
    got, reads = _proof_read(PD_EDITS, trip=False)
    if got is not False:
        return False, "answered %r, want False: a path's content is in no commit" % (got,)
    if reads:
        return False, ("read %d candidate tree(s) for %d paths that can never match, want none: a path whose "
                       "worktree entry differs from its index entry is refused at once" % (reads, PD_MANY))
    return True, "%d paths with an edit in no commit answer False and read no candidate tree" % PD_MANY


def base_copies_staged_past_deadline_case():
    """PD_MANY staged blobs in no commit: False with the clock on time, and past the deadline the proof reads at most
    the first candidate before it answers False."""
    materialize(PD_STAGED)
    scope = _proof_scope(PD_STAGED, ["M  " + name for name in _numbered_paths(PD_MANY)], reflog_min=3)
    if scope:
        return False, "scope: " + scope
    got, _ = _proof_read(PD_STAGED, trip=False)
    if got is not False:
        return False, "answered %r with the clock on time, want False: a staged blob is in no commit" % (got,)
    got, reads = _proof_read(PD_STAGED, trip=True)
    if got is not False:
        return False, "answered %r once past its deadline, want False" % (got,)
    if reads > 2:
        return False, ("read %d candidate tree(s) after the clock passed its deadline, want at most 2: the proof "
                       "runs on past its deadline" % reads)
    return True, "%d staged paths in no commit answer False, and past the deadline read %d candidate tree(s)" % (
        PD_MANY, reads)


def base_copies_deadline_mid_loop_case():
    """The incident tree, whose match is on its second candidate. Past the deadline before that read, the proof answers
    False, not the True it gives on time."""
    materialize(BCINC)
    scope = _proof_scope(BCINC, BC_INCIDENT)
    if scope:
        return False, "scope: " + scope
    got, reads = _proof_read(BCINC, trip=False)
    if got is not True or reads < 2:
        return False, ("scope: with the clock on time the proof answered %r after %d candidate tree(s), want True after "
                       "at least 2: the match is not on a later candidate" % (got, reads))
    got, _ = _proof_read(BCINC, trip=True)
    if got is not False:
        return False, "answered %r once past its deadline before the second candidate, want False" % (got,)
    return True, "the incident tree answers False once the clock passes its deadline before its second candidate"


def base_copies_one_candidate_control_case():
    """Green control: the incident tree, whose paths all match one candidate, answers True with the clock on time."""
    materialize(BCINC)
    scope = _proof_scope(BCINC, BC_INCIDENT)
    if scope:
        return False, "scope: " + scope
    got, _ = _proof_read(BCINC, trip=False)
    if got is not True:
        return False, "answered %r with the clock on time, want True: every path matches one pushed candidate" % (got,)
    return True, "the incident tree, whose paths all match one candidate, answers True with the clock on time"


def base_copies_many_pushed_control_case():
    """Green control: 201 changed paths that are all pushed copies answer True with the clock on time."""
    materialize(BCCAP)
    scope = _proof_scope(BCCAP, ["M  " + name for name in _numbered_paths(201)])
    if scope:
        return False, "scope: " + scope
    got, _ = _proof_read(BCCAP, trip=False)
    if got is not True:
        return False, "answered %r with the clock on time, want True: 201 pushed copies" % (got,)
    return True, "201 changed paths that are all pushed copies answer True with the clock on time"


# THE BUDGET IS READ FROM THE INSTALL. _proof_budget reads the guard hook's timeout from the settings.json of the install
# its module runs in, and answers None when that read fails. The proof then answers None before any candidate read. The
# guard refuses None and False alike (guard_core.py, worktree remove), so these cases pin the proof's own answer: None
# says the read failed. False would say the tree holds work it cannot prove pushed. The cases do not pin the route to
# that file. A module at hooks/ reads the settings.json beside hooks/. A module at hooks/guard.d/<id>/, the installed
# layout, reads the one at the install root. The install root is also the config directory each case names, so either
# route reads the same file.

GUARD_HOOK_COMMAND = "python3 ${HOME}/.claude/hooks/guard.py"  # names /hooks/guard.py, the row _proof_budget reads


def _settings_text(hook_row):
    """settings.json text with one PreToolUse row holding HOOK_ROW, or with no row at all when HOOK_ROW is None."""
    rows = [] if hook_row is None else [{"matcher": "Bash", "hooks": [hook_row]}]
    return json.dumps({"hooks": {"PreToolUse": rows}})


GUARD_D_ID = "cases-install-id"  # the folder name guard.py gives an installed copy's guard.d/<id>/ (INSTALL_ID)


def _install_layout(name, settings, guard_d):
    """(install folder, module path) under this run's folder. The install folder holds SETTINGS as its settings.json
    beside `hooks/`, or no settings.json when SETTINGS is None. The module sits at `hooks/git_reads.py` when GUARD_D is
    false, and at `hooks/guard.d/<id>/git_reads.py` when true: the installed layout, where guard.py loads its modules from
    the folder of its own id (hooks/guard.py, _SET_DIR). Both folders are made real, so a read fails for the content it
    reads, never for a missing folder. Nothing is copied: the budget reads paths, not the module's bytes."""
    folder = os.path.join(ROOT, name)
    module_dir = os.path.join(folder, "hooks", "guard.d", GUARD_D_ID) if guard_d else os.path.join(folder, "hooks")
    os.makedirs(module_dir, exist_ok=True)
    if settings is not None:
        write(os.path.join(folder, "settings.json"), settings)
    return folder, os.path.join(module_dir, "git_reads.py")


def _budget_beside(module_at, config_dir):
    """What the real `_proof_budget` reads for a module at MODULE_AT, with CONFIG_DIR as its config directory: a number,
    or None when it cannot read one."""
    git_reads = _load_git_reads()
    with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": config_dir}), \
            mock.patch.object(git_reads, "__file__", module_at):
        return git_reads._proof_budget()


def _incident_scope():
    """None when the incident tree holds its state, else the one thing that differs."""
    materialize(BCINC)
    scope = _proof_scope(BCINC, BC_INCIDENT)
    return ("scope: " + scope) if scope else None


def _allowed_incident_scope():
    """None when the incident tree is in its state and the proof allows it on a readable budget, else the one thing
    that differs. The unreadable-budget cases read this first, so a None answer is not a tree never allowed."""
    scope = _incident_scope()
    if scope:
        return scope
    got, _ = _proof_read(BCINC, trip=False)
    if got is not True:
        return ("scope: the incident tree answered %r with a readable budget, want True: it is not an allowed tree"
                % (got,))
    return None


def base_copies_unreadable_budget_case():
    """The incident tree, allowed with a readable budget, answers None once `_proof_budget` answers None."""
    scope = _allowed_incident_scope()
    if scope:
        return False, scope
    got, _ = _proof_read(BCINC, trip=False, budget=lambda: None)
    if got is not None:
        return False, "answered %r with _proof_budget None, want None: a failed budget read is None" % (got,)
    return True, "the incident tree answers None, not False or True, when _proof_budget is None"


def _unreadable_budget_case(name, settings, why, guard_d=False):
    """The incident tree, allowed with a readable budget, answers None once the real budget read beside its module
    fails for WHY. The install root is also the config directory, so a route to settings.json through either reads the
    same file."""
    scope = _allowed_incident_scope()
    if scope:
        return False, scope
    install, module_at = _install_layout(name, settings, guard_d)
    if _budget_beside(module_at, install) is not None:
        return False, "scope: the budget beside %s reads a number, want None: %s" % (name, why)
    got, _ = _proof_read(BCINC, trip=False, module_at=module_at, config_dir=install)
    if got is not None:
        return False, ("answered %r with the budget unreadable (%s), want None: a failed budget read is None"
                       % (got, why))
    return True, "the incident tree answers None, not False or True, when the budget is unreadable: %s" % why


def base_copies_no_settings_budget_case():
    """The incident tree with no settings.json beside its hooks folder: the budget reads None, so the answer is None."""
    return _unreadable_budget_case("budget-no-settings", None, "no settings.json beside the hooks folder")


def base_copies_no_timeout_budget_case():
    """The incident tree with a guard hook row that has no timeout: the budget reads None, the proof answers None."""
    settings = _settings_text({"type": "command", "command": GUARD_HOOK_COMMAND})
    return _unreadable_budget_case("budget-no-timeout", settings, "the guard hook row has no timeout")


def base_copies_no_guard_row_budget_case():
    """The incident tree with no PreToolUse row: nothing names the guard, the budget reads None, so the answer is None."""
    return _unreadable_budget_case("budget-no-row", _settings_text(None), "no PreToolUse row names the guard")


def base_copies_no_settings_guard_d_case():
    """The installed layout with no settings.json anywhere: the install root holds none, and it is the config directory,
    so the budget reads None and the incident tree answers None."""
    return _unreadable_budget_case("budget-guard-d-none", None,
                                   "no settings.json at the install root, beside hooks/, or in the config directory",
                                   guard_d=True)


FIXTURE_GUARD_TIMEOUT = 60  # the guard row's timeout in the settings.json the readable cases write


def _readable_budget_case(guard_d, layout, cause):
    """The incident tree, under a readable budget, answers True on time. The budget beside the module is above zero and
    below the guard row's timeout, read back from the settings.json the case wrote at the install root. LAYOUT names the
    module's place in the messages, and CAUSE says why a None budget is wrong there."""
    settings = _settings_text({"type": "command", "command": GUARD_HOOK_COMMAND, "timeout": FIXTURE_GUARD_TIMEOUT})
    install, module_at = _install_layout("budget-guard-d" if guard_d else "budget-flat", settings, guard_d)
    scope = _incident_scope()
    if scope:
        return False, scope
    settings_at = os.path.join(install, "settings.json")
    if not os.path.isfile(settings_at) or not os.path.isdir(os.path.dirname(module_at)):
        return False, "scope: the %s layout is not on disk, so the budget read has no file to find" % layout
    timeout = _guard_row_timeout(settings_at)
    if timeout is None:
        return False, "scope: %s has no PreToolUse row that names /hooks/guard.py with a numeric timeout" % settings_at
    budget = _budget_beside(module_at, install)
    if budget is None:
        return False, "_proof_budget answered None for the module %s, want a number: %s" % (layout, cause)
    if not 0 < budget < timeout:
        return False, ("_proof_budget answered %g s, want above zero and below the guard hook's %g s timeout"
                       % (budget, timeout))
    got, _ = _proof_read(BCINC, trip=False, module_at=module_at, config_dir=install)
    if got is not True:
        return False, ("answered %r with the clock on time, want True: a readable budget of %g s lets the incident "
                       "tree through" % (got, budget))
    return True, ("a budget of %g s, above zero and below the guard hook's %g s timeout, lets the incident tree "
                  "through (%s)" % (budget, timeout, layout))


def base_copies_readable_budget_control_case():
    """Green control, the flat layout: the module at hooks/, its settings.json beside hooks/. The budget is readable and
    the incident tree is allowed under it."""
    return _readable_budget_case(False, "at hooks/, with settings.json beside hooks/",
                                 "the settings.json beside hooks/ is not read from a module at hooks/")


def base_copies_guard_d_budget_case():
    """The installed layout: the module at hooks/guard.d/<id>/, settings.json at the install root beside hooks/, which
    is also the config directory. The budget is readable and the incident tree is allowed under it."""
    return _readable_budget_case(True, "at hooks/guard.d/<id>/, with settings.json at the install root",
                                 "the install root's settings.json is not read from a module under hooks/guard.d/<id>/")


def _guard_row_timeout(settings):
    """The timeout of the first PreToolUse hook that names /hooks/guard.py in SETTINGS: the row the proof reads. None
    when the file cannot be read or that row has no numeric timeout. A second reader on purpose: _proof_budget returns
    half this timeout, so reading the timeout through it would test the budget against itself."""
    try:
        with open(settings, encoding="utf-8") as f:
            rows = json.load(f)["hooks"]["PreToolUse"]
        for row in rows:
            for hook in row["hooks"]:
                if "/hooks/guard.py" in (hook.get("command") or ""):
                    return float(hook["timeout"])
    except Exception:
        return None
    return None


def base_copies_budget_below_guard_timeout_case():
    """The proof's budget is above zero and below the guard hook's own timeout, both read from the repo's settings.json:
    the file the real module reads from its folder, and the one the config directory names here. A budget at or past
    that timeout is the hole this section guards: a timed-out guard lets the call through. So `* 2` in place of `/ 2`
    (twice the timeout) fails this case. It asserts an inequality, not a number."""
    git_reads = _load_git_reads()
    settings = os.path.join(REPO, "settings.json")
    timeout = _guard_row_timeout(settings)
    if timeout is None:
        return False, ("scope: %s has no PreToolUse row that names /hooks/guard.py with a numeric timeout, so there is "
                       "no timeout to bound the budget against" % settings)
    with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": REPO}):
        budget = git_reads._proof_budget()
    if budget is None:
        return False, ("_proof_budget answered None with the guard hook's timeout %g s read, want a number" % timeout)
    if budget <= 0:
        return False, "_proof_budget answered %g s, want above zero" % budget
    if budget >= timeout:
        return False, ("_proof_budget answered %g s, not below the guard hook's %g s timeout: a timed-out guard "
                       "lets the call through" % (budget, timeout))
    return True, "the proof's budget is above zero and below the guard hook's own timeout, both read from settings.json"


for _label, _check in (
    ("base copies: 250 paths with an edit in no commit answer False and read no candidate tree",
     base_copies_edits_no_candidate_case),
    ("base copies: 250 staged paths in no commit answer False, and past the deadline read at most two candidate trees",
     base_copies_staged_past_deadline_case),
    ("base copies: the incident tree answers False once the clock passes its deadline before its second candidate",
     base_copies_deadline_mid_loop_case),
    ("base copies: the incident tree, whose paths all match one candidate, answers True with the clock on time",
     base_copies_one_candidate_control_case),
    ("base copies: 201 pushed copies answer True with the clock on time", base_copies_many_pushed_control_case),
    ("base copies: the incident tree answers None, not False or True, when _proof_budget is None",
     base_copies_unreadable_budget_case),
    ("base copies: the incident tree answers None with no settings.json beside its hooks folder",
     base_copies_no_settings_budget_case),
    ("base copies: the incident tree answers None when its guard hook row has no timeout",
     base_copies_no_timeout_budget_case),
    ("base copies: the incident tree answers None when no PreToolUse row names the guard",
     base_copies_no_guard_row_budget_case),
    ("base copies: a readable budget beside its settings.json lets the incident tree through",
     base_copies_readable_budget_control_case),
    ("base copies: a readable budget under hooks/guard.d/<id>/, with settings.json at the install root, lets the "
     "incident tree through", base_copies_guard_d_budget_case),
    ("base copies: the incident tree answers None with no settings.json anywhere, under hooks/guard.d/<id>/",
     base_copies_no_settings_guard_d_case),
    ("base copies: the proof's budget is above zero and below the guard hook's timeout in settings.json",
     base_copies_budget_below_guard_timeout_case),
):
    LOG_CHECKS_EXTRA.append((_label, _check))
    LOG_FAMILY[_label] = "branch-worktree"
    FIXTURELESS_CHECKS.add(_check)
