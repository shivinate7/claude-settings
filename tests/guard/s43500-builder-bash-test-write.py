# section 43500
FAMILY = "builder-bash-test-write"
# builder-bash-test-write (decision builders-cannot-edit-tests). The incident: a builder wrote 64 tests/guard/s*.py
# files with its own Python script, run through Bash. The PreToolUse check reads the command text, and the script
# computed its paths, so the call was allowed; the diff check refused only at the builder's stop. The PostToolUse
# check reads the worktree after each builder shell call: one `git status --porcelain` in the payload's cwd, and each
# changed path is tested with is_builder_test_rel, the one test-path function. A git that cannot answer logs unread.
import test_wrappers as wrappers  # noqa: E402  the settings-entry home: hook lookup and the sh run (hooks/test_wrappers.py)

BBTW_RULE = "builder-bash-test-write"
BBTW_UNREAD = "builder-bash-test-write-unread"
BBTW_SESSION = "bbtw-session"
# A script that writes the test files itself: no test path is in the command text, so PreToolUse reads it as allowed.
BBTW_SCRIPT = "python3 scripts/make_checks.py"
BBTW_PS_SCRIPT = "python scripts/make_checks.py"
# The reason's undo route: restore each changed test to HEAD, delete each added one, and name the test-author.
BBTW_UNDO = (("restore", "Restore"), "HEAD", ("delete", "Delete"), "test-author")
BBTW_NO_ENTRY = "no PostToolUse entry with matcher Bash|PowerShell runs hooks/guard.py, so nothing checks a shell call after it runs"
BBTW_GUARD_NEEDLE = '/hooks/guard.py"'
NO_SH_ENTRY = "the settings entry is a POSIX shell line, and this Windows run has no python stand-in the line can find"


def bbtw_body(cwd, command, agent="builder", tool="Bash"):
    """The PostToolUse payload of one shell call. `agent` is the agent_type, or '' for the main session."""
    body = {"hook_event_name": "PostToolUse", "tool_name": tool, "tool_input": {"command": command},
            "cwd": cwd, "session_id": BBTW_SESSION}
    if agent:
        body["agent_id"] = "bbtw-" + agent
        body["agent_type"] = agent
    return body


def _bbtw_raw(where, command=BBTW_SCRIPT, agent="builder", tool="Bash"):
    return json.dumps(bbtw_body(where, command, agent, tool))


def bbtw_add(name, expected, where, agent="builder", tool="Bash", command=None, env_path=None, **kw):
    """One case that runs the PostToolUse payload of a shell call in `where` through the guard."""
    if command is None:
        command = BBTW_PS_SCRIPT if tool == "PowerShell" else BBTW_SCRIPT
    add(name, expected, raw=_bbtw_raw(where, command, agent, tool), cwd=where, tool=tool, env_path=env_path, **kw)


# ---------------------------------------------------------------- fixtures: real worktrees, built on first use
# The shapes come from the builder-diff section (diff_repo, _put, _rm, _mv and BASE_FILES), so one set of
# worktrees serves both checks. Each name is registered once.
BBTW_UNTRACKED = diff_repo("bbtw-untracked", _put("tests/foo.py", "def test_foo():\n    assert 1\n"))
BBTW_MODIFIED = diff_repo("bbtw-modified", _put("tests/test_a.py", "pass\n"))
BBTW_MUTANT_BASE = dict(BASE_FILES)
BBTW_MUTANT_BASE["hooks/mutate_guard.py"] = "x = 0\n"   # the mutation test is tracked, so its change is a modify
BBTW_MUTANT = diff_repo("bbtw-mutant", _put("hooks/mutate_guard.py", "x = 1\n"), files=BBTW_MUTANT_BASE)
BBTW_DELETED = diff_repo("bbtw-deleted", _rm("tests/test_a.py"))
BBTW_MOVED = diff_repo("bbtw-moved", _mv("tests/test_a.py", "src/moved.py"))
# The full-size state: the incident wrote 64 test files, so the reason must hold for all of them, naming none.
BBTW_MANY_FILES = ["tests/guard/s%05d-incident.py" % n for n in range(64)]


def _bbtw_many(w):
    for rel in BBTW_MANY_FILES:
        write(os.path.join(w, rel), "def test_incident():\n    assert 1\n")


BBTW_MANY = diff_repo("bbtw-many", _bbtw_many)


def _bbtw_product(w):
    write(os.path.join(w, "hooks/x.py"), "x = 1\n")
    write(os.path.join(w, "docs/a.md"), "# a\n")


BBTW_PRODUCT = diff_repo("bbtw-product", _bbtw_product)
BBTW_CLEAN = diff_repo("bbtw-clean", lambda w: None)   # the empty state: nothing changed

# A test in a new untracked folder. Plain `git status` lists that folder alone, not its files.
BBTW_NEWDIR = diff_repo("bbtw-newdir", _put("src/newdir/test_n.py", "def test_n():\n    assert 1\n"))
# A test whose name holds a space, and one whose name holds a non-ASCII letter. Plain `git status` quotes both.
BBTW_SPACE = diff_repo("bbtw-space", _put("tests/my test.py", "def test_space():\n    assert 1\n"))
BBTW_UNICODE = diff_repo("bbtw-unicode", _put("tests/test_café.py", "def test_caf():\n    assert 1\n"))
# The undo route's fallback: a builder that cannot undo the change stops and reports it.
BBTW_STOP = ("cannot undo it yourself", "stop and report")
BBTW_MERGE_ABORT = "git merge --abort"


def _bbtw_merge_conflict(w):
    """A real merge that stops on a conflict in tests/test_a.py, so git leaves MERGE_HEAD in the worktree's git dir.
    Branch `other` and the worktree's branch `work` each rewrite the test; the merge of `other` into `work` conflicts."""
    def git(*args):
        done = run_vcs(w, *args)
        if done.returncode != 0:
            sys.exit("fixture setup failed: git %s in %r: %s" % (" ".join(args), w, done.stderr.strip()))
    git("checkout", "-q", "-b", "other")
    write(os.path.join(w, "tests/test_a.py"), "def test_a():\n    assert 2\n")
    git("add", "-A")
    git(*IDENT, "commit", "-q", "-m", "other side")
    git("checkout", "-q", "work")
    write(os.path.join(w, "tests/test_a.py"), "def test_a():\n    assert 3\n")
    git("add", "-A")
    git(*IDENT, "commit", "-q", "-m", "work side")
    if run_vcs(w, *IDENT, "merge", "-q", "--no-edit", "other").returncode == 0:
        sys.exit("fixture setup failed: the merge in %r did not conflict" % w)


BBTW_MERGE = diff_repo("bbtw-merge", _bbtw_merge_conflict)

# ---------------------------------------------------------------- the stopped states (rule builder-bash-test-write-merging)
# A merge, a rebase or a cherry-pick that stops on a product conflict brings the other side's files into the worktree,
# so `git status` lists them as changed. The check reads the state file in the worktree's git dir (a file read, no git
# call). With a stop in progress and no unmerged test path, it allows the call and logs builder-bash-test-write-merging,
# noted, and the merge-aware commit and stop check judges the change. An unmerged test path still refuses.
BBTW_MERGING = "builder-bash-test-write-merging"
BBTW_SRC = "src/app.py"            # a product file both sides rewrite, so bringing the other side in conflicts on it
BBTW_INCOMING = "tests/test_n.py"  # the test file the other side adds, which comes in clean
BBTW_TEST_A = "tests/test_a.py"    # the test file both sides rewrite in the unmerged-test controls
PRODUCT_OTHER = {BBTW_SRC: "x = 2\n", BBTW_INCOMING: "def test_n():\n    assert 1\n"}
PRODUCT_WORK = {BBTW_SRC: "x = 3\n"}
PRODUCT_WANT = (("A ", BBTW_INCOMING), ("UU", BBTW_SRC))
MANY_OTHER = {BBTW_SRC: "x = 2\n"}   # the full-size state: the other side adds 64 test files
MANY_OTHER.update((rel, "def test_incident():\n    assert 1\n") for rel in BBTW_MANY_FILES)
MANY_WANT = (("A ", BBTW_MANY_FILES[0]), ("A ", BBTW_MANY_FILES[-1]), ("UU", BBTW_SRC))
MIXED_OTHER = {BBTW_SRC: "x = 2\n", BBTW_TEST_A: "def test_a():\n    assert 2\n"}
MIXED_WORK = {BBTW_SRC: "x = 3\n", BBTW_TEST_A: "def test_a():\n    assert 3\n"}
MIXED_WANT = (("UU", BBTW_SRC), ("UU", BBTW_TEST_A))
TEST_OTHER = {BBTW_TEST_A: "def test_a():\n    assert 2\n"}
TEST_WORK = {BBTW_TEST_A: "def test_a():\n    assert 3\n"}
TEST_WANT = (("UU", BBTW_TEST_A),)
ONLY_OTHER = {BBTW_SRC: "x = 2\n"}   # the empty test state: no test path changes at all
ONLY_WANT = (("UU", BBTW_SRC),)


def _bbtw_run(where, *args):
    """A git call that builds a stop. A call that fails stops the run: the state a case needs was never made."""
    done = run_vcs(where, *args)
    if done.returncode != 0:
        sys.exit("fixture setup failed in %r: %s" % (where, done.stderr.strip()))
    return done


def _bbtw_side_commits(where, other, work):
    """Branch `other` commits the files `other` maps. Then `work`, the worktree's branch, commits the files `work` maps.
    Both sides rewrite the same lines of a file, so bringing `other` in by merge, rebase or cherry-pick conflicts."""
    _bbtw_run(where, "checkout", "-q", "-b", "other")
    for rel, text in other.items():
        write(os.path.join(where, rel), text)
    _bbtw_run(where, "add", "-A")
    _bbtw_run(where, *IDENT, "commit", "-q", "-m", "other side")
    _bbtw_run(where, "checkout", "-q", "work")
    for rel, text in work.items():
        write(os.path.join(where, rel), text)
    _bbtw_run(where, "add", "-A")
    _bbtw_run(where, *IDENT, "commit", "-q", "-m", "work side")


def _bbtw_state_scope(where, state, want):
    """P7: the worktree is in `state` (a file or folder in its git dir, found with git), and git status of it holds
    each (code, path) in `want`. '' when both hold, else the one failure note. Read before any case judges the stop.
    _bbtw_merge_scope stays as the read of the existing merge case."""
    gitdir = run_vcs(where, "rev-parse", "--git-dir")
    if gitdir.returncode != 0:
        return "the fixture is not a repository: git rev-parse fails"
    if not os.path.exists(os.path.join(where, gitdir.stdout.strip(), state)):
        return "the fixture holds no %s in progress: none in its git dir" % state
    status = run_vcs(where, "status", "--porcelain", "--untracked-files=all")
    lines = status.stdout.splitlines()
    for code, path in want:
        if not any(line[:2] == code and line[3:] == path for line in lines):
            return "the fixture does not hold %s %s: git status reads %r" % (code, path, status.stdout.strip()[:120])
    return ""


def _bbtw_stop_build(state, op, other, work, want, first=None):
    """A diff_repo change: the two sides are committed, `first` is checked out when given, and `op` (the git args that
    bring `other` in) must stop on a conflict. The stop is checked with git here, before any case reads it."""
    def build(where):
        _bbtw_side_commits(where, other, work)
        if first:
            _bbtw_run(where, "checkout", "-q", first)
        if run_vcs(where, *IDENT, *op).returncode == 0:
            sys.exit("fixture setup failed: git %s in %r did not stop on a conflict" % (" ".join(op), where))
        note = _bbtw_state_scope(where, state, want)
        if note:
            sys.exit("fixture setup failed: " + note)
    return build


# A merge, a rebase (rebase-merge and rebase-apply) and a cherry-pick each stop in the worktree's own git dir.
BBTW_MERGE_PRODUCT = diff_repo("bbtw-merge-product", _bbtw_stop_build(
    "MERGE_HEAD", ("merge", "--no-edit", "other"), PRODUCT_OTHER, PRODUCT_WORK, PRODUCT_WANT))
BBTW_MERGE_MANY = diff_repo("bbtw-merge-many", _bbtw_stop_build(
    "MERGE_HEAD", ("merge", "--no-edit", "other"), MANY_OTHER, PRODUCT_WORK, MANY_WANT))
BBTW_REBASE_PRODUCT = diff_repo("bbtw-rebase-product", _bbtw_stop_build(
    "rebase-merge", ("rebase", "work"), PRODUCT_OTHER, PRODUCT_WORK, PRODUCT_WANT, first="other"))
BBTW_REBASE_APPLY = diff_repo("bbtw-rebase-apply", _bbtw_stop_build(
    "rebase-apply", ("rebase", "--apply", "work"), PRODUCT_OTHER, PRODUCT_WORK, PRODUCT_WANT, first="other"))
BBTW_PICK_PRODUCT = diff_repo("bbtw-pick-product", _bbtw_stop_build(
    "CHERRY_PICK_HEAD", ("cherry-pick", "other"), PRODUCT_OTHER, PRODUCT_WORK, PRODUCT_WANT))
BBTW_MERGE_MIXED = diff_repo("bbtw-merge-mixed", _bbtw_stop_build(
    "MERGE_HEAD", ("merge", "--no-edit", "other"), MIXED_OTHER, MIXED_WORK, MIXED_WANT))
BBTW_REBASE_TEST = diff_repo("bbtw-rebase-test", _bbtw_stop_build(
    "rebase-merge", ("rebase", "work"), TEST_OTHER, TEST_WORK, TEST_WANT, first="other"))
BBTW_PICK_TEST = diff_repo("bbtw-pick-test", _bbtw_stop_build(
    "CHERRY_PICK_HEAD", ("cherry-pick", "other"), TEST_OTHER, TEST_WORK, TEST_WANT))
BBTW_MERGE_PRODUCT_ONLY = diff_repo("bbtw-merge-product-only", _bbtw_stop_build(
    "MERGE_HEAD", ("merge", "--no-edit", "other"), ONLY_OTHER, PRODUCT_WORK, ONLY_WANT))

# A git stand-in that answers every call but a status read. It is POSIX only, so its cases skip on Windows.
BBTW_NO_ANSWER_BIN = os.path.join(ROOT, "bbtw-no-answer")
BBTW_NO_ANSWER_PATH = BBTW_NO_ANSWER_BIN + os.pathsep + os.environ.get("PATH", "")


def _bbtw_build_no_answer():
    """The probe runs in the builder worktree: the stand-in must fail status alone, and let rev-parse answer."""
    make_git_stand_in(BBTW_NO_ANSWER_BIN, fail_on="status")
    materialize(BBTW_UNTRACKED)
    git = os.path.join(BBTW_NO_ANSWER_BIN, VCS)
    status = subprocess.run([git, "status", "--porcelain"], cwd=BBTW_UNTRACKED, capture_output=True, text=True)
    top = subprocess.run([git, "rev-parse", "--show-toplevel"], cwd=BBTW_UNTRACKED, capture_output=True, text=True)
    if status.returncode == 0 or top.returncode != 0:
        sys.exit("fixture setup failed: the no-answer git stand-in in %r does not fail status alone"
                 % BBTW_NO_ANSWER_BIN)


if os.name != "nt":
    lazy_fixture([BBTW_NO_ANSWER_BIN], _bbtw_build_no_answer)


# ---------------------------------------------------------------- cases the guard answers (run_cases)
# A refusal reads as "deny" (read_decision maps the PostToolUse `block` value). A check that fails for the named cause is red.
bbtw_add("builder-bash-test-write: a builder's script that adds tests/foo.py is refused at PostToolUse, with the undo route and the test-author named, and no path named",
         "deny", BBTW_UNTRACKED, rule=BBTW_RULE, carries=BBTW_UNDO, lacks=("tests/foo.py",))
bbtw_add("builder-bash-test-write: a builder's script that rewrites a tracked test is refused at PostToolUse",
         "deny", BBTW_MODIFIED, rule=BBTW_RULE, carries=BBTW_UNDO, lacks=("tests/test_a.py",))
bbtw_add("builder-bash-test-write: a builder's script that rewrites a mutation test is refused at PostToolUse",
         "deny", BBTW_MUTANT, rule=BBTW_RULE, carries=BBTW_UNDO, lacks=("hooks/mutate_guard.py",))
bbtw_add("builder-bash-test-write: a builder's script that deletes a tracked test is refused at PostToolUse",
         "deny", BBTW_DELETED, rule=BBTW_RULE, carries=BBTW_UNDO, lacks=("tests/test_a.py",))
bbtw_add("builder-bash-test-write: a builder's script that moves a tracked test out of tests/ is refused at PostToolUse",
         "deny", BBTW_MOVED, rule=BBTW_RULE, carries=BBTW_UNDO, lacks=("tests/test_a.py",))
bbtw_add("builder-bash-test-write: a builder's script that writes 64 test files is refused once, naming none",
         "deny", BBTW_MANY, rule=BBTW_RULE, carries=BBTW_UNDO, lacks=("tests/guard/",))
bbtw_add("builder-bash-test-write: a builder's PowerShell call that adds tests/foo.py is refused at PostToolUse",
         "deny", BBTW_UNTRACKED, tool="PowerShell", rule=BBTW_RULE, carries=BBTW_UNDO, lacks=("tests/foo.py",))

bbtw_add("builder-bash-test-write: a builder's call that changed only product code is allowed silently",
         "allow", BBTW_PRODUCT, silent=True)
# No fall-through: a command the PreToolUse kill rule refuses still reads only the PostToolUse check, which allows it.
bbtw_add("builder-bash-test-write: a builder's PostToolUse call with a refused command is judged only by the PostToolUse check, and allowed silently",
         "allow", BBTW_PRODUCT, command="pkill -f node", silent=True)
bbtw_add("builder-bash-test-write: a builder's call on a clean worktree is allowed silently",
         "allow", BBTW_CLEAN, silent=True)
bbtw_add("builder-bash-test-write: a test-author's call that adds tests/foo.py is allowed silently",
         "allow", BBTW_UNTRACKED, agent="test-author", silent=True)
bbtw_add("builder-bash-test-write: the main session's call that adds tests/foo.py is allowed silently",
         "allow", BBTW_UNTRACKED, agent="", silent=True)
bbtw_add("builder-bash-test-write: a builder's call in no repository is allowed silently",
         "allow", NOGIT, silent=True)
if os.name != "nt":
    bbtw_add("builder-bash-test-write: a builder's call whose git status fails is allowed silently",
             "allow", BBTW_UNTRACKED, env_path=BBTW_NO_ANSWER_PATH, silent=True)
else:
    skip_case("builder-bash-test-write: a builder's call whose git status fails is allowed silently", NO_STAND_IN)

# Each case names one shape. The folder and merge shapes get their own checks below, which read the fixture first.
bbtw_add("builder-bash-test-write: a builder's call that leaves a space-named test, tests/my test.py, is refused at PostToolUse",
         "deny", BBTW_SPACE, rule=BBTW_RULE, carries=BBTW_UNDO, lacks=("my test.py",))
bbtw_add("builder-bash-test-write: a builder's call that leaves a non-ASCII-named test is refused at PostToolUse",
         "deny", BBTW_UNICODE, rule=BBTW_RULE, carries=BBTW_UNDO, lacks=("test_caf",))
bbtw_add("builder-bash-test-write: a builder's refusal says to stop and report when it cannot undo the test change",
         "deny", BBTW_UNTRACKED, rule=BBTW_RULE, carries=BBTW_STOP, lacks=("tests/foo.py",))

# The stopped states. An unmerged test path still refuses in each. The reason names the merge-abort step only in a
# merge, the one state `git merge --abort` ends. A refusal outside a merge, or in a rebase or cherry-pick, does not name it.
# The five cases below are CONTROLS: each passes on the old code too. They pin what the new check must keep (the refusal
# on an unmerged test path, in each state) and the negative pins on the merge-abort step (the reason names it only in a merge).
bbtw_add("builder-bash-test-write: a builder's call in a merge with a product conflict and an unmerged test path is refused, and names the merge-abort step",
         "deny", BBTW_MERGE_MIXED, rule=BBTW_RULE, carries=BBTW_UNDO + (BBTW_MERGE_ABORT,), lacks=(BBTW_TEST_A,))
bbtw_add("builder-bash-test-write: a builder's call in a rebase with an unmerged test path is refused, and does not name the merge-abort step",
         "deny", BBTW_REBASE_TEST, rule=BBTW_RULE, carries=BBTW_UNDO, lacks=(BBTW_MERGE_ABORT, BBTW_TEST_A))
bbtw_add("builder-bash-test-write: a builder's call in a cherry-pick with an unmerged test path is refused, and does not name the merge-abort step",
         "deny", BBTW_PICK_TEST, rule=BBTW_RULE, carries=BBTW_UNDO, lacks=(BBTW_MERGE_ABORT, BBTW_TEST_A))
bbtw_add("builder-bash-test-write: a builder's call that rewrites a tracked test outside any merge is refused, and does not name the merge-abort step",
         "deny", BBTW_MODIFIED, rule=BBTW_RULE, carries=BBTW_UNDO, lacks=(BBTW_MERGE_ABORT, BBTW_TEST_A))
bbtw_add("builder-bash-test-write: a builder's call in a merge with only a product conflict is allowed silently, with no merge-abort step",
         "allow", BBTW_MERGE_PRODUCT_ONLY, silent=True)


# ---------------------------------------------------------------- checks the log and the git spy (LOG_CHECKS)
def _bbtw_scope(where, want):
    """P7: the fixture holds the change a checker judges, read with git before the guard's answer is read.
    '' when git's status of `where` names `want`, else the one failure note."""
    done = run_vcs(where, "status", "--porcelain", "--untracked-files=all")
    if done.returncode == 0 and want in done.stdout:
        return ""
    return "the fixture does not hold %s: git status reads %r" % (want, (done.stdout + done.stderr).strip()[:120])


def _bbtw_subcommands(path):
    """The git subcommand of each call a stand-in logged, in order. The guard's reads pass `-C <dir>` first; it is skipped."""
    if not os.path.exists(path):
        return []
    names = []
    with open(path, encoding="utf-8") as handle:
        for line in handle.read().splitlines():
            words = line.split()
            while len(words) >= 2 and words[0] == "-C":
                words = words[2:]
            names.append(words[0] if words else "")
    return names


def _bbtw_judge(tag, raw, env_path=None, count_git=False):
    """One PostToolUse judgement by decide, with a config folder of its own. With `count_git`, a git stand-in
    on PATH logs each call. -> (decision, reason, config folder, git subcommands, or None when not counted)."""
    folder = os.path.join(ROOT, "bbtw-" + tag)
    os.makedirs(folder, exist_ok=True)
    calls = os.path.join(folder, "git-calls.txt")
    if count_git:
        bin_dir = os.path.join(folder, "bin")
        make_git_stand_in(bin_dir, log=calls)
        env_path = bin_dir + os.pathsep + os.environ.get("PATH", "")
    got, reason = decide({"raw": raw, "tool": "Bash", "cwd": None, "session": None, "env_path": env_path,
                          "config": folder, "tool_input": {}})
    return got, reason, folder, (_bbtw_subcommands(calls) if count_git else None)


def _bbtw_rows(folder, rule):
    """The guard.log rows of one rule (column 4 of each tab-separated line)."""
    rows = [line.split("\t") for line in _guard_log_lines(folder) if line.strip()]
    return [row for row in rows if len(row) > 3 and row[3] == rule]


def bbtw_refuse_line_case():
    """A refusal writes one row for the rule, logged `deny`. Pins the log: a refusal the log cannot show is no evidence."""
    _got, _reason, folder, _ = _bbtw_judge("refuse-line", _bbtw_raw(BBTW_UNTRACKED))
    rows = _bbtw_rows(folder, BBTW_RULE)
    if len(rows) != 1 or rows[0][2] != "deny":
        return False, "want one row logged deny for %s in guard.log, got %r" % (BBTW_RULE, rows)
    return True, "one row logged deny for %s in guard.log" % BBTW_RULE


def _bbtw_unread_case(tag, where, env_path=None):
    _got, _reason, folder, _ = _bbtw_judge(tag, _bbtw_raw(where), env_path=env_path)
    rows = _bbtw_rows(folder, BBTW_UNREAD)
    if len(rows) != 1 or rows[0][2] != "noted":
        return False, "want one noted %s line in guard.log, got %r" % (BBTW_UNREAD, rows)
    return True, "a call git could not read is logged %s, noted" % BBTW_UNREAD


def bbtw_unread_no_repo_case():
    return _bbtw_unread_case("unread-no-repo", NOGIT)


def bbtw_unread_git_fails_case():
    return _bbtw_unread_case("unread-git-fails", BBTW_UNTRACKED, env_path=BBTW_NO_ANSWER_PATH)


def bbtw_status_once_test_case():
    """Cost: one git status for a builder call that changed a test. P7: the test change is in the fixture first."""
    materialize(BBTW_UNTRACKED)
    note = _bbtw_scope(BBTW_UNTRACKED, "tests/foo.py")
    if note:
        return False, note
    _got, _reason, _folder, names = _bbtw_judge("cost-builder-test", _bbtw_raw(BBTW_UNTRACKED), count_git=True)
    if names.count("status") != 1:
        return False, "git status ran %d times in one builder call that changed a test, want 1" % names.count("status")
    return True, "one git status in a builder call that changed a test"


def bbtw_status_once_product_case():
    """Cost: one git status for every builder call, here one that changed only product code."""
    materialize(BBTW_PRODUCT)
    note = _bbtw_scope(BBTW_PRODUCT, "hooks/x.py")
    if note:
        return False, note
    _got, _reason, _folder, names = _bbtw_judge("cost-builder-product", _bbtw_raw(BBTW_PRODUCT), count_git=True)
    if names.count("status") != 1:
        return False, "git status ran %d times in one builder call that changed only product code, want 1" % names.count("status")
    return True, "one git status in a builder call that changed only product code"


def bbtw_no_git_author_case():
    """A test-author's call runs no git at all: a PostToolUse call returns before any PreToolUse read."""
    materialize(BBTW_UNTRACKED)
    note = _bbtw_scope(BBTW_UNTRACKED, "tests/foo.py")
    if note:
        return False, note
    _got, _reason, _folder, names = _bbtw_judge("cost-author", _bbtw_raw(BBTW_UNTRACKED, agent="test-author"), count_git=True)
    if names:
        return False, "git ran %d times in a test-author's call, want none: %r" % (len(names), names[:3])
    return True, "no git call in a test-author's call"


def bbtw_no_git_main_case():
    """The main session's call runs no git at all: the guard checks for the builder role before any read."""
    materialize(BBTW_UNTRACKED)
    note = _bbtw_scope(BBTW_UNTRACKED, "tests/foo.py")
    if note:
        return False, note
    _got, _reason, _folder, names = _bbtw_judge("cost-main", _bbtw_raw(BBTW_UNTRACKED, agent=""), count_git=True)
    if names:
        return False, "git ran %d times in the main session's call, want none: %r" % (len(names), names[:3])
    return True, "no git call in the main session's call"


def _bbtw_stdout(raw, folder):
    """The guard's exit code and stdout for one payload. decide returns only the verdict, which reads both refusal
    shapes as deny, so this reads the printed JSON itself. The environment is the one decide sets."""
    env = dict(os.environ)
    for name in ("CLAUDE_CODE_REMOTE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_REMOTE_SESSION_ID", "CLAUDE_PROJECT_DIR"):
        env.pop(name, None)
    env["CLAUDE_CONFIG_DIR"] = folder
    env["CLAUDE_GUARD_ROOT_PID"] = str(os.getpid())
    done = subprocess.run([sys.executable, GUARD], input=raw, capture_output=True, text=True, env=env, timeout=120)
    return done.returncode, done.stdout


def bbtw_block_shape_case():
    """A refusal is a PostToolUse answer: {"decision": "block", "reason": ...} on stdout. Claude Code ignores a
    PreToolUse hookSpecificOutput on this event, so that shape would let the call through with no refusal."""
    materialize(BBTW_UNTRACKED)
    note = _bbtw_scope(BBTW_UNTRACKED, "tests/foo.py")
    if note:
        return False, note
    code, out = _bbtw_stdout(_bbtw_raw(BBTW_UNTRACKED), os.path.join(ROOT, "bbtw-block-shape"))
    if code != 0:
        return False, "the guard exited %d, want 0" % code
    try:
        parsed = json.loads(out)
    except ValueError:
        return False, "stdout is not one JSON object: %r" % out[:80]
    if not isinstance(parsed, dict):
        return False, "stdout is JSON but not an object: %r" % out[:80]
    if "hookSpecificOutput" in parsed:
        return False, "the answer is a PreToolUse hookSpecificOutput, not the PostToolUse {decision: block} answer"
    if parsed.get("decision") != "block":
        return False, "decision is %r, want block" % parsed.get("decision")
    if not isinstance(parsed.get("reason"), str) or not parsed["reason"].strip():
        return False, "the refusal carries no reason text"
    return True, "the refusal is {decision: block, reason} on stdout"


# ---------------------------------------------------------------- the settings entry (settings.json, read only)
def _bbtw_entry(settings):
    """The PostToolUse hook whose group has matcher Bash|PowerShell and whose command runs hooks/guard.py, or None."""
    for group in settings.get("hooks", {}).get("PostToolUse", []):
        if group.get("matcher") != "Bash|PowerShell":
            continue
        for hook in group.get("hooks", []):
            if BBTW_GUARD_NEEDLE in wrappers.command_of(hook):
                return hook
    return None


def bbtw_entry_case():
    if _bbtw_entry(wrappers.load()) is None:
        return False, BBTW_NO_ENTRY
    return True, "a PostToolUse hook for Bash|PowerShell runs hooks/guard.py"


def _bbtw_entry_inputs():
    """(tag, payload text, payload dict): three builder payloads first, then the two that must not start the guard."""
    builder = bbtw_body(BBTW_UNTRACKED, BBTW_SCRIPT)
    ps = bbtw_body(BBTW_UNTRACKED, BBTW_PS_SCRIPT, tool="PowerShell")
    main = bbtw_body(BBTW_UNTRACKED, BBTW_SCRIPT, agent="")
    author = bbtw_body(BBTW_UNTRACKED, BBTW_SCRIPT, agent="test-author")
    return [("builder-compact", json.dumps(builder, separators=(",", ":")), builder),
            ("builder-spaced", json.dumps(builder), builder),
            ("builder-powershell", json.dumps(ps), ps),
            ("main-session", json.dumps(main), main),
            ("test-author", json.dumps(author), author)]


def _bbtw_entry_stdin(entry, tag, text):
    """Runs the entry's command with CLAUDE_CONFIG_DIR at a folder whose hooks/guard.py stub writes its stdin to
    ran.txt. -> the stdin the stub read, or None when the settings entry never started the stub."""
    cfg = os.path.join(ROOT, "bbtw-entry-" + tag)
    write(os.path.join(cfg, "hooks", "guard.py"),
          "import os, sys\n"
          "with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ran.txt'), 'w', encoding='utf-8') as h:\n"
          "    h.write(sys.stdin.read())\n")
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = cfg
    wrappers.run_sh(wrappers.command_of(entry), env, stdin=text)
    ran = os.path.join(cfg, "hooks", "ran.txt")
    if not os.path.exists(ran):
        return None
    with open(ran, encoding="utf-8") as handle:
        return handle.read()


def bbtw_entry_passes_case():
    """The settings entry lets each builder payload through to the guard, unchanged: compact and spaced JSON, and PowerShell."""
    entry = _bbtw_entry(wrappers.load())
    if entry is None:
        return False, BBTW_NO_ENTRY
    for tag, text, body in _bbtw_entry_inputs()[:3]:
        got = _bbtw_entry_stdin(entry, tag, text)
        if got is None:
            return False, "the settings entry did not start the guard for the %s payload" % tag
        try:
            same = json.loads(got) == body
        except ValueError:
            same = False
        if not same:
            return False, "the guard read a payload other than the %s payload" % tag
    return True, "the settings entry starts the guard for compact, spaced and PowerShell builder payloads, unchanged"


def bbtw_entry_stops_case():
    """The settings entry starts no python for the main session or a test-author: their calls cost no process."""
    entry = _bbtw_entry(wrappers.load())
    if entry is None:
        return False, BBTW_NO_ENTRY
    for tag, text, _body in _bbtw_entry_inputs()[3:]:
        if _bbtw_entry_stdin(entry, tag, text) is not None:
            return False, "the settings entry started the guard for the %s payload, which is not a builder's" % tag
    return True, "the settings entry starts no guard for the main session or a test-author"


def _bbtw_folder_scope(where, folder):
    """P7: the fixture holds `folder` as one new untracked entry, the default status shape the no-flag mutant reads.
    '' when it does, else the one failure note."""
    done = run_vcs(where, "status", "--porcelain")
    if done.returncode != 0:
        return "the fixture is not a repository: git status fails"
    if ("?? %s/" % folder) not in done.stdout:
        return "the fixture does not hold %s/ as a new untracked folder: git status reads %r" % (
            folder, done.stdout.strip()[:120])
    return ""


def bbtw_new_folder_case():
    """A builder's call that creates a test in a new untracked folder is refused, and the reason names no path."""
    materialize(BBTW_NEWDIR)
    note = _bbtw_folder_scope(BBTW_NEWDIR, "src/newdir")
    if note:
        return False, note
    got, reason, _folder, _names = _bbtw_judge("new-folder", _bbtw_raw(BBTW_NEWDIR))
    if got != "deny":
        return False, "a builder's test in a new untracked folder is %s, want a refusal" % got
    if "src/newdir" in reason:
        return False, "the refusal names the folder"
    return True, "a test in a new untracked folder is refused, and the reason names no path"


def _bbtw_merge_scope(where):
    """P7: a merge is in progress (MERGE_HEAD in the worktree's git dir) and the test path is unmerged.
    '' when both hold, else the one failure note."""
    git_dir = run_vcs(where, "rev-parse", "--git-dir")
    if git_dir.returncode != 0:
        return "the fixture is not a repository: git rev-parse fails"
    if not os.path.exists(os.path.join(where, git_dir.stdout.strip(), "MERGE_HEAD")):
        return "the fixture holds no merge in progress: no MERGE_HEAD in its git dir"
    return _bbtw_scope(where, "tests/test_a.py")


def bbtw_merge_abort_case():
    """A builder's call in a merge that conflicts in a test path is refused, and the refusal names the merge-abort step."""
    materialize(BBTW_MERGE)
    note = _bbtw_merge_scope(BBTW_MERGE)
    if note:
        return False, note
    got, reason, _folder, _names = _bbtw_judge("merge-abort", _bbtw_raw(BBTW_MERGE))
    if got != "deny":
        return False, "a builder's call in a merge with a test conflict is %s, want a refusal" % got
    if BBTW_MERGE_ABORT not in reason:
        return False, "the refusal does not name the merge-abort step %r" % BBTW_MERGE_ABORT
    return True, "a refusal in a merge with a test conflict names the merge-abort step"


def _bbtw_merging_noted(tag, where, what):
    """A builder's call in a stop that holds an incoming test path and no unmerged test path: allowed, silently, and
    logged builder-bash-test-write-merging as noted, so the merge-aware commit and stop check judges the change.
    The stop was checked with git when its fixture was built (_bbtw_stop_build)."""
    materialize(where)
    got, reason, folder, _names = _bbtw_judge(tag, _bbtw_raw(where))
    if got != "allow":
        return False, "a builder's call in %s with an incoming test is %s, want allow: %s" % (what, got, reason[:90])
    if reason:
        return False, "an allow in %s printed a reason, want silence: %s" % (what, reason[:90])
    rows = _bbtw_rows(folder, BBTW_MERGING)
    if len(rows) != 1 or rows[0][2] != "noted":
        return False, "want one noted %s line in guard.log, got %r" % (BBTW_MERGING, rows)
    return True, "a builder's call in %s with an incoming test is allowed and logged %s, noted" % (what, BBTW_MERGING)


def bbtw_merging_merge_case():
    return _bbtw_merging_noted("merging-merge", BBTW_MERGE_PRODUCT, "a merge")


def bbtw_merging_many_case():
    return _bbtw_merging_noted("merging-many", BBTW_MERGE_MANY, "a merge that brings 64 test files")


def bbtw_merging_rebase_case():
    return _bbtw_merging_noted("merging-rebase", BBTW_REBASE_PRODUCT, "a rebase (rebase-merge)")


def bbtw_merging_rebase_apply_case():
    return _bbtw_merging_noted("merging-rebase-apply", BBTW_REBASE_APPLY, "a rebase (rebase-apply)")


def bbtw_merging_pick_case():
    return _bbtw_merging_noted("merging-pick", BBTW_PICK_PRODUCT, "a cherry-pick")


def bbtw_status_once_merge_case():
    """CONTROL, green on the old code: a builder call in a merge reads git status once and makes no other git call.
    The new stop read is a file read, so this pins that it adds no git call."""
    materialize(BBTW_MERGE_PRODUCT)
    _got, _reason, _folder, names = _bbtw_judge("cost-merge", _bbtw_raw(BBTW_MERGE_PRODUCT), count_git=True)
    if names != ["status"]:
        return False, "git ran %r in a builder call in a merge, want one status and no other call" % names
    return True, "one git status, and no other git call, in a builder call in a merge"


BBTW_CHECKS = (
    ("builder-bash-test-write: a refusal writes one row, logged deny, for the rule to guard.log", bbtw_refuse_line_case),
    ("builder-bash-test-write: a call git cannot read because it is no repository logs builder-bash-test-write-unread, noted",
     bbtw_unread_no_repo_case),
    ("builder-bash-test-write: a call whose git status fails logs builder-bash-test-write-unread, noted",
     bbtw_unread_git_fails_case),
    ("builder-bash-test-write: a builder call that changed a test reads git status once", bbtw_status_once_test_case),
    ("builder-bash-test-write: a builder call that changed only product code reads git status once",
     bbtw_status_once_product_case),
    ("builder-bash-test-write: a test-author's call runs no git at all", bbtw_no_git_author_case),
    ("builder-bash-test-write: the main session's call runs no git at all", bbtw_no_git_main_case),
    ("builder-bash-test-write: a refusal is the PostToolUse {decision: block, reason} on stdout", bbtw_block_shape_case),
    ("builder-bash-test-write: settings.json has a PostToolUse entry for Bash|PowerShell that runs hooks/guard.py",
     bbtw_entry_case),
    ("builder-bash-test-write: the settings entry starts the guard for each builder payload, unchanged",
     bbtw_entry_passes_case),
    ("builder-bash-test-write: the settings entry starts no guard for the main session or a test-author",
     bbtw_entry_stops_case),
    ("builder-bash-test-write: a builder's test in a new untracked folder is refused, and the reason names no path",
     bbtw_new_folder_case),
    ("builder-bash-test-write: a builder's call in a merge with a test conflict names the merge-abort step",
     bbtw_merge_abort_case),
    ("builder-bash-test-write: a builder call in a merge that stops on a product conflict, with an incoming test, "
     "is allowed and logs builder-bash-test-write-merging, noted", bbtw_merging_merge_case),
    ("builder-bash-test-write: a builder call in a merge that brings 64 test files and stops on a product conflict "
     "is allowed and logs builder-bash-test-write-merging, noted", bbtw_merging_many_case),
    ("builder-bash-test-write: a builder call in a rebase (rebase-merge) that stops on a product conflict, with an "
     "incoming test, is allowed and logs builder-bash-test-write-merging, noted", bbtw_merging_rebase_case),
    ("builder-bash-test-write: a builder call in a rebase (rebase-apply) that stops on a product conflict, with an "
     "incoming test, is allowed and logs builder-bash-test-write-merging, noted", bbtw_merging_rebase_apply_case),
    ("builder-bash-test-write: a builder call in a cherry-pick that stops on a product conflict, with an incoming "
     "test, is allowed and logs builder-bash-test-write-merging, noted", bbtw_merging_pick_case),
    ("builder-bash-test-write: a builder call in a merge reads git status once and makes no other git call",
     bbtw_status_once_merge_case),
)
# A git stand-in is POSIX only. A settings entry runs its command under sh, which Windows cannot run here.
BBTW_STAND_IN_CHECKS = (bbtw_unread_git_fails_case, bbtw_status_once_test_case, bbtw_status_once_product_case,
                        bbtw_no_git_author_case, bbtw_no_git_main_case, bbtw_status_once_merge_case)
BBTW_ENTRY_CHECKS = (bbtw_entry_passes_case, bbtw_entry_stops_case)
for _label, _check in BBTW_CHECKS:
    LOG_FAMILY[_label] = FAMILY
    if os.name == "nt" and _check in BBTW_STAND_IN_CHECKS:
        skip_case(_label, NO_STAND_IN)
    elif os.name == "nt" and _check in BBTW_ENTRY_CHECKS:
        skip_case(_label, NO_SH_ENTRY)
    else:
        LOG_CHECKS = LOG_CHECKS + ((_label, _check),)
    if _check is bbtw_entry_case:
        FIXTURELESS_CHECKS.add(_check)
