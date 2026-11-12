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
BBTW_NO_ENTRY = "no PostToolUse entry with matcher Bash|PowerShell runs hooks/guard.py, so there is no gate to run"
BBTW_GUARD_NEEDLE = '/hooks/guard.py"'
NO_SH_GATE = "the gate is a POSIX shell line, and this Windows run has no python stand-in the line can find"


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
# A block reads as "deny" (read_decision maps the PostToolUse block). A check that fails for the named cause is red.
bbtw_add("builder-bash-test-write: a builder's script that adds tests/foo.py is blocked at PostToolUse, with the undo route and the test-author named, and no path named",
         "deny", BBTW_UNTRACKED, rule=BBTW_RULE, carries=BBTW_UNDO, lacks=("tests/foo.py",))
bbtw_add("builder-bash-test-write: a builder's script that rewrites a tracked test is blocked at PostToolUse",
         "deny", BBTW_MODIFIED, rule=BBTW_RULE, carries=BBTW_UNDO, lacks=("tests/test_a.py",))
bbtw_add("builder-bash-test-write: a builder's script that rewrites a mutation test is blocked at PostToolUse",
         "deny", BBTW_MUTANT, rule=BBTW_RULE, carries=BBTW_UNDO, lacks=("hooks/mutate_guard.py",))
bbtw_add("builder-bash-test-write: a builder's script that deletes a tracked test is blocked at PostToolUse",
         "deny", BBTW_DELETED, rule=BBTW_RULE, carries=BBTW_UNDO, lacks=("tests/test_a.py",))
bbtw_add("builder-bash-test-write: a builder's script that moves a tracked test out of tests/ is blocked at PostToolUse",
         "deny", BBTW_MOVED, rule=BBTW_RULE, carries=BBTW_UNDO, lacks=("tests/test_a.py",))
bbtw_add("builder-bash-test-write: a builder's script that writes 64 test files is blocked once, naming none",
         "deny", BBTW_MANY, rule=BBTW_RULE, carries=BBTW_UNDO, lacks=("tests/guard/",))
bbtw_add("builder-bash-test-write: a builder's PowerShell call that adds tests/foo.py is blocked at PostToolUse",
         "deny", BBTW_UNTRACKED, tool="PowerShell", rule=BBTW_RULE, carries=BBTW_UNDO, lacks=("tests/foo.py",))

bbtw_add("builder-bash-test-write: a builder's call that changed only product code is allowed silently",
         "allow", BBTW_PRODUCT, silent=True)
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


def bbtw_deny_line_case():
    """A block writes one deny line for the rule. Pins the log: a block the log cannot show is no evidence."""
    _got, _reason, folder, _ = _bbtw_judge("deny-line", _bbtw_raw(BBTW_UNTRACKED))
    rows = _bbtw_rows(folder, BBTW_RULE)
    if len(rows) != 1 or rows[0][2] != "deny":
        return False, "want one deny line for %s in guard.log, got %r" % (BBTW_RULE, rows)
    return True, "one deny line for %s in guard.log" % BBTW_RULE


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


def bbtw_no_status_author_case():
    """A test-author's call reads no git status: the check gates on the builder role first."""
    materialize(BBTW_UNTRACKED)
    note = _bbtw_scope(BBTW_UNTRACKED, "tests/foo.py")
    if note:
        return False, note
    _got, _reason, _folder, names = _bbtw_judge("cost-author", _bbtw_raw(BBTW_UNTRACKED, agent="test-author"), count_git=True)
    if "status" in names:
        return False, "git status ran in a test-author's call, want none"
    return True, "no git status in a test-author's call"


def bbtw_no_git_main_case():
    """The main session's call runs no git at all: the check gates on the builder role before any read."""
    materialize(BBTW_UNTRACKED)
    note = _bbtw_scope(BBTW_UNTRACKED, "tests/foo.py")
    if note:
        return False, note
    _got, _reason, _folder, names = _bbtw_judge("cost-main", _bbtw_raw(BBTW_UNTRACKED, agent=""), count_git=True)
    if names:
        return False, "git ran %d times in the main session's call, want none: %r" % (len(names), names[:3])
    return True, "no git call in the main session's call"


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


def _bbtw_gate_inputs():
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


def _bbtw_gate_stdin(entry, tag, text):
    """Runs the entry's command with CLAUDE_CONFIG_DIR at a folder whose hooks/guard.py stub writes its stdin to
    ran.txt. -> the stdin the stub read, or None when the gate never started the stub."""
    cfg = os.path.join(ROOT, "bbtw-gate-" + tag)
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


def bbtw_gate_passes_case():
    """The gate lets each builder payload through to the guard, unchanged: compact and spaced JSON, and PowerShell."""
    entry = _bbtw_entry(wrappers.load())
    if entry is None:
        return False, BBTW_NO_ENTRY
    for tag, text, body in _bbtw_gate_inputs()[:3]:
        got = _bbtw_gate_stdin(entry, tag, text)
        if got is None:
            return False, "the gate did not start the guard for the %s payload" % tag
        try:
            same = json.loads(got) == body
        except ValueError:
            same = False
        if not same:
            return False, "the guard read a payload other than the %s payload" % tag
    return True, "the gate starts the guard for compact, spaced and PowerShell builder payloads, unchanged"


def bbtw_gate_stops_case():
    """The gate starts no python for the main session or a test-author: their calls cost no process."""
    entry = _bbtw_entry(wrappers.load())
    if entry is None:
        return False, BBTW_NO_ENTRY
    for tag, text, _body in _bbtw_gate_inputs()[3:]:
        if _bbtw_gate_stdin(entry, tag, text) is not None:
            return False, "the gate started the guard for the %s payload, which is not a builder's" % tag
    return True, "the gate starts no guard for the main session or a test-author"


BBTW_CHECKS = (
    ("builder-bash-test-write: a block writes one deny line for the rule to guard.log", bbtw_deny_line_case),
    ("builder-bash-test-write: a call git cannot read because it is no repository logs builder-bash-test-write-unread, noted",
     bbtw_unread_no_repo_case),
    ("builder-bash-test-write: a call whose git status fails logs builder-bash-test-write-unread, noted",
     bbtw_unread_git_fails_case),
    ("builder-bash-test-write: a builder call that changed a test reads git status once", bbtw_status_once_test_case),
    ("builder-bash-test-write: a builder call that changed only product code reads git status once",
     bbtw_status_once_product_case),
    ("builder-bash-test-write: a test-author's call reads no git status", bbtw_no_status_author_case),
    ("builder-bash-test-write: the main session's call runs no git at all", bbtw_no_git_main_case),
    ("builder-bash-test-write: settings.json has a PostToolUse entry for Bash|PowerShell that runs hooks/guard.py",
     bbtw_entry_case),
    ("builder-bash-test-write: the settings entry's gate starts the guard for each builder payload, unchanged",
     bbtw_gate_passes_case),
    ("builder-bash-test-write: the settings entry's gate starts no guard for the main session or a test-author",
     bbtw_gate_stops_case),
)
# A git stand-in is POSIX only. A gate runs the settings line under sh, which Windows cannot run here.
BBTW_STAND_IN_CHECKS = (bbtw_unread_git_fails_case, bbtw_status_once_test_case, bbtw_status_once_product_case,
                        bbtw_no_status_author_case, bbtw_no_git_main_case)
BBTW_GATE_CHECKS = (bbtw_gate_passes_case, bbtw_gate_stops_case)
for _label, _check in BBTW_CHECKS:
    LOG_FAMILY[_label] = FAMILY
    if os.name == "nt" and _check in BBTW_STAND_IN_CHECKS:
        skip_case(_label, NO_STAND_IN)
    elif os.name == "nt" and _check in BBTW_GATE_CHECKS:
        skip_case(_label, NO_SH_GATE)
    else:
        LOG_CHECKS = LOG_CHECKS + ((_label, _check),)
    if _check is bbtw_entry_case:
        FIXTURELESS_CHECKS.add(_check)
