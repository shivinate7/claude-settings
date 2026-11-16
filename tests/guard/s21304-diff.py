# section 21304
FAMILY = "diff"
BASE_FILES = {
    "src/app.py": "x = 1\n", "src/contest.py": "y = 1\n", "latest_results.md": "ok\n",
    "tests/test_a.py": "def test_a():\n    assert True\n", "pyproject.toml": "[project]\nname = 'x'\n[tool.pytest.ini_options]\nminversion = '7'\n",
    "package.json": ('{"name": "x", "scripts": {"build": "tsc", "test": "jest"}, '
                     '"dependencies": {"a": "1"}, "devDependencies": {"b": "1"}}\n'),
    "requirements-dev.txt": "pytest\n",
}
DIFFROOT = os.path.join(ROOT, "diffrepos")


# A diff repo costs real git calls, and the mutation test runs this module once per mutant while
# `MUTATE_ONLY` selects one or two cases. So a repo is built LAZILY, the first time a case runs in
# it (`materialize`, called from `decide`). MEASURED on Windows CI: building all of them at import
# cost 1 min 52 s per run of this module.
def diff_repo(name, change, commit=False, cut_from=None, files=None):
    """A real linked worktree, as a builder runs in: a main checkout with a base commit, and a
    worktree on a new branch `work` cut from `cut_from` (default HEAD). `change` edits the
    worktree; `commit` then commits there. Returns the worktree's path. Built on first use."""
    main = os.path.join(DIFFROOT, name + "-main")
    where = os.path.join(DIFFROOT, name)

    def build():
        make_repo(main, files or BASE_FILES)
        made = run_vcs(main, "worktree", "add", "-q", "-b", "work", where,
                       *([cut_from] if cut_from else []))
        if made.returncode != 0:
            sys.exit("fixture setup failed: worktree in %r: %s" % (where, made.stderr.strip()))
        change(where)
        if commit:
            run_vcs(where, "add", "-A")
            done = run_vcs(where, *IDENT, "commit", "-q", "-m", "work")
            if done.returncode != 0:
                sys.exit("fixture setup failed: commit in %r: %s" % (where, done.stderr.strip()))
    lazy_fixture([where, main], build)
    return where


def _rm(rel):
    return lambda w: os.remove(os.path.join(w, rel))


def _put(rel, text):
    return lambda w: write(os.path.join(w, rel), text)


def _mv(src, dst):
    def go(w):
        os.makedirs(os.path.dirname(os.path.join(w, dst)), exist_ok=True)
        os.rename(os.path.join(w, src), os.path.join(w, dst))
    return go


def _link(target, rel):
    def go(w):
        os.makedirs(os.path.dirname(os.path.join(w, rel)), exist_ok=True)
        os.symlink(target, os.path.join(w, rel))
    go.needs_link = True  # the loops below skip it where os.symlink is refused
    return go


# Each bypass of the command reader ends in ONE of these trees. The guard never sees
# the command, only the tree.
BUILDER_RED = [
    ("deleted", _rm("tests/test_a.py")),                      # rm, find -delete, xargs rm, dd
    ("rewritten", _put("tests/test_a.py", "pass\n")),         # sed -i, patch, apply, rsync, bash -c
    ("new-untracked", _put("tests/test_new.py", "pass\n")),   # cp -t, a redirect through a variable
    ("moved-out", _mv("tests/test_a.py", "src/moved.py")),    # mv
    ("symlink-file", _link("../tests/test_a.py", "src/link.py")),
    ("symlink-dir", _link("tests", "src/linkdir")),
    ("backslash-name", _put("tests\\foo.py", "pass\n")),
    ("conftest", _put("conftest.py", "import pytest\n")),
    ("pytest-ini", _put("pytest.ini", "[pytest]\naddopts = --deselect tests/test_a.py\n")),
    ("pyproject-addopts", _put("pyproject.toml",
                               "[project]\nname = 'x'\n[tool.pytest.ini_options]\n"
                               "addopts = \"--ignore=tests\"\n")),
    ("jest-config", _put("jest.config.js", "module.exports = {testPathIgnorePatterns: ['/src/']}\n")),
    ("pytest-section-far-flag", _put("pyproject.toml", "[project]\nname = 'x'\n[tool.pytest.ini_options]\n"
                                     "minversion = '7'\na = 1\nb = 2\nc = 3\nflags = \"--ignore=tests\"\n")),
    ("test-script-deselect", _put("package.json", '{"name": "x", "scripts": {"test": '
                                  '"pytest --deselect a::b"}}\n')),
    ("pytest-ini-continued-addopts", _put("pytest.ini", "[pytest]\naddopts =\n    -q\n"
                                          "    --ignore=tests/slow\n")),
    ("package-json-jest", _put("package.json",
                               '{"name": "x", "jest": {"testPathIgnorePatterns": ["src"]}}\n')),
    ("spec-file", _put("web/a.spec.ts", "it.skip('x', () => {})\n")),
    ("testdata", _put("testdata/x.json", "{}\n")),
    ("snapshots", _put("src/__snapshots__/a.snap", "snap\n")),
    ("jest-setup", _put("jest.setup.js", "global.x = 1\n")),
    ("java-test", _put("src/FooTest.java", "class FooTest {}\n")),
    ("test-support", _put("test_support/helper.py", "pass\n")),
    # A mutation test is test code; its case fold is the same file on Windows.
    ("mutate-guard", _put("hooks/mutate_guard.py", "x = 1\n")),
    ("mutate-shared", _put("hooks/mutate_shared.py", "x = 1\n")),
    ("mutate-sweep", _put("janitor/mutate_sweep.py", "x = 1\n")),
    ("mutate-case-fold", _put("HOOKS/mutate_guard.py", "x = 1\n")),
]
BUILDER_GREEN = [
    ("clean-tree", lambda w: None),
    ("product-edit", _put("src/app.py", "x = 2\n")),
    ("contest-and-results", lambda w: (write(os.path.join(w, "src/contest.py"), "y = 2\n"),
                                       write(os.path.join(w, "latest_results.md"), "better\n"))),
    ("product-rename", _mv("src/app.py", "src/main.py")),
    ("product-delete", _rm("src/contest.py")),
    ("dependency-added", _put("pyproject.toml", "[project]\nname = 'x'\ndependencies = ['requests']\n")),
    ("script-added", _put("package.json", '{"name": "x", "scripts": {"build": "tsc"}}\n')),
    ("symlink-to-product", _link("../src/app.py", "src/alias.py")),
    ("ruff-ignore-script", _put("package.json", '{"name": "x", "scripts": {"lint": '
                                '"ruff check --ignore E501"}}\n')),
    ("flake8-ignore-flag", _put("tox.ini", "[testenv:lint]\ncommands = flake8 --ignore=E203\n")),
    ("ignore-scripts-flag", _put("package.json",
                                 '{"name": "x", "scripts": {"ci": "npm ci --ignore-scripts && jest"}}\n')),
    ("dev-requirements", _put("requirements-dev.txt", "pytest\nruff\n")),
    ("pyproject-non-pytest", _put("pyproject.toml",
                                  "[project]\nname = 'x'\ndependencies = ['y']\n"
                                  "[tool.pytest.ini_options]\nminversion = '7'\n")),
    # The near miss is a builder's product code (control for the mutation-test rows in BUILDER_RED).
    ("mutate-x-near-miss", _put("hooks/mutate_x.py", "x = 2\n")),
]
COMMIT, PUSH = VCS + " commit -m x", VCS + " push origin work"
# A builder's test change is REFUSED at commit and push, and BLOCKED at the first stop. The
# builder-refuse section below pins the base rule and the refusal text. The rule id is the one the refusal prints.
BDIFF = "builder-diff"
for _name, _change in BUILDER_RED:
    if getattr(_change, "needs_link", False) and not LINKS_MADE:
        continue
    _repo = diff_repo("b-" + _name, _change)
    sh("builder-diff: commit with a %s change is denied" % _name, COMMIT, "deny", rule=BDIFF,
       cwd=_repo, agent_id="bld1", agent_type="builder")
    sh("builder-diff: push with a %s change is denied" % _name, PUSH, "deny", rule=BDIFF,
       cwd=_repo, agent_id="bld1", agent_type="builder")
    add("builder-diff: stop with a %s change is blocked" % _name, "deny", rule=BDIFF,
        event="SubagentStop", cwd=_repo, agent_id="bld1", agent_type="builder")
# A mutation test the base already holds, changed or only added to, is refused at commit and at stop: a builder
# never writes one. The base holds each file, so these are modifications, not new files.
_CHANGED = {}
for _rel in MUTATION_TESTS:
    _slug = _rel.replace("/", "-").replace(".py", "")
    _CHANGED[_rel] = diff_repo("b-mutant-changed-" + _slug, _put(_rel, "x = 2\n"),
                               files={**BASE_FILES, _rel: "x = 1\n"})
    sh("builder-diff: commit that changes an existing line of %s is refused" % _rel, COMMIT, "deny",
       rule=BDIFF, cwd=_CHANGED[_rel], agent_id="bld1", agent_type="builder")
    add("builder-diff: stop after changing an existing line of %s is blocked" % _rel, "deny", rule=BDIFF,
        event="SubagentStop", cwd=_CHANGED[_rel], agent_id="bld1", agent_type="builder")
    _added = diff_repo("b-mutant-added-" + _slug, _put(_rel, "x = 1\ny = 2\n"),
                       files={**BASE_FILES, _rel: "x = 1\n"})
    sh("builder-diff: commit that only adds a line to %s is refused" % _rel, COMMIT, "deny",
       rule=BDIFF, cwd=_added, agent_id="bld1", agent_type="builder")
    add("builder-diff: stop after only adding a line to %s is blocked" % _rel, "deny", rule=BDIFF,
        event="SubagentStop", cwd=_added, agent_id="bld1", agent_type="builder")
# A builder's commit or stop from a subfolder is judged on the same diff as from the root.
_guard_changed = _CHANGED["hooks/mutate_guard.py"]
sh("builder-diff: commit from hooks/ with an edit to mutate_guard.py is refused", "cd hooks && " + COMMIT,
   "deny", rule=BDIFF, cwd=_guard_changed, agent_id="bld1", agent_type="builder")
sh("builder-diff: git -C hooks commit with an edit to mutate_guard.py is refused",
   VCS + " -C hooks commit -m x", "deny", rule=BDIFF, cwd=_guard_changed, agent_id="bld1", agent_type="builder")
add("builder-diff: stop from hooks/ with an edit to mutate_guard.py is blocked", "deny", rule=BDIFF,
    event="SubagentStop", cwd=os.path.join(_guard_changed, "hooks"), agent_id="bld1", agent_type="builder")
# The empty state is no exception: HEAD holds an empty MUTATIONS list, and a builder's first entry is refused too.
_empty_mut = diff_repo("b-mutants-empty", _put("hooks/mutate_guard.py", 'MUTATIONS = [\n    ("x", 1),\n]\n'),
                       files={**BASE_FILES, "hooks/mutate_guard.py": "MUTATIONS = [\n]\n"})
sh("builder-diff: commit that adds a first entry to an empty MUTATIONS list is refused", COMMIT, "deny",
   rule=BDIFF, cwd=_empty_mut, agent_id="bld1", agent_type="builder")
add("builder-diff: stop after adding a first entry to an empty MUTATIONS list is blocked", "deny", rule=BDIFF,
    event="SubagentStop", cwd=_empty_mut, agent_id="bld1", agent_type="builder")
add("builder-test: Edit of hooks/mutate_guard.py that adds a first entry to an empty MUTATIONS list is refused",
    "deny", rule=BT, tool="Edit", file_path="hooks/mutate_guard.py", old_string="MUTATIONS = [\n",
    new_string='MUTATIONS = [\n    ("x", 1),\n', carries=("test-author", "Report"), **B)
_repo = diff_repo("b-committed", _put("tests/test_a.py", "pass\n"), commit=True)
add("builder-diff: stop after COMMITTING a test change is blocked", "deny", rule=BDIFF,
    event="SubagentStop", cwd=_repo, agent_id="bld1", agent_type="builder")
sh("builder-diff: push after COMMITTING a test change is denied", PUSH, "deny", rule=BDIFF,
   cwd=_repo, agent_id="bld1", agent_type="builder")
_repo = diff_repo("b-reverted", lambda w: (write(os.path.join(w, "tests/test_a.py"), "pass\n"),
                                           write(os.path.join(w, "tests/test_a.py"),
                                                 BASE_FILES["tests/test_a.py"])))
add("builder-diff: a test change put back to the base bytes is no change", "allow",
    event="SubagentStop", cwd=_repo, agent_id="bld1", agent_type="builder")
_inh_main = os.path.join(DIFFROOT, "g-inherited-main")
_inh = os.path.join(DIFFROOT, "g-inherited")


def _build_inherited():
    make_repo(_inh_main, BASE_FILES)
    run_vcs(_inh_main, "checkout", "-q", "-b", "orch")
    write(os.path.join(_inh_main, "tests/test_a.py"), "pass\n")   # the orchestrator's own commit
    run_vcs(_inh_main, "add", "-A")
    run_vcs(_inh_main, *IDENT, "commit", "-q", "-m", "orch")
    run_vcs(_inh_main, "worktree", "add", "-q", "-b", "work", _inh, "orch")
    write(os.path.join(_inh, "src/app.py"), "x = 9\n")


lazy_fixture([_inh, _inh_main], _build_inherited)
add("builder-diff: test changes the branch inherited are not the builder's", "allow",
    event="SubagentStop", cwd=_inh, agent_id="bld1", agent_type="builder")


def _merge_main_in(own_test_edit):
    """Main gains a test change AFTER the builder's branch was cut; the builder merges main in."""
    def go(w):
        main = w + "-main"
        write(os.path.join(main, "tests/test_a.py"), "pass  # main's own change\n")
        run_vcs(main, "add", "-A")
        run_vcs(main, *IDENT, "commit", "-q", "-m", "main moves")
        merged = run_vcs(w, *IDENT, "merge", "-q", "--no-edit", "main")
        if merged.returncode != 0:
            sys.exit("fixture setup failed: merge in %r: %s" % (w, merged.stderr.strip()))
        write(os.path.join(w, "src/app.py"), "x = 5\n")
        if own_test_edit:
            write(os.path.join(w, "tests/test_b.py"), "pass\n")
    return go


_repo = diff_repo("g-merged-main", _merge_main_in(False))
add("builder-diff: test changes merged in from main are not the builder's", "allow",
    event="SubagentStop", cwd=_repo, agent_id="bld1", agent_type="builder")
sh("builder-diff: commit after merging main in is allowed", COMMIT, "allow", cwd=_repo,
   agent_id="bld1", agent_type="builder")
_repo = diff_repo("b-merged-main-own", _merge_main_in(True))
add("builder-diff: its OWN new test after merging main in is blocked", "deny", rule=BDIFF,
    event="SubagentStop", cwd=_repo, agent_id="bld1", agent_type="builder")


def _own_test_then_new_branch(w):
    write(os.path.join(w, "tests/test_a.py"), "pass\n")
    run_vcs(w, "add", "-A")
    run_vcs(w, *IDENT, "commit", "-q", "-m", "own test change")
    run_vcs(w, "switch", "-q", "-c", "b2")


_repo = diff_repo("b-new-branch-name", _own_test_then_new_branch)
add("builder-diff: a new branch name does not reset the base: the stop is blocked", "deny",
    rule=BDIFF, event="SubagentStop", cwd=_repo, agent_id="bld1", agent_type="builder")
sh("builder-diff: a new branch name does not reset the base: the push is denied", PUSH, "deny",
   rule=BDIFF, cwd=_repo, agent_id="bld1", agent_type="builder")

# The first stop with a test change is blocked (guard.py judge_stop). A dirty main tree is no
# builder change, so it does not change the verdict. The second stop is pinned in role_log_case.
_repo = diff_repo("b-giveup", lambda w: (write(os.path.join(w, "tests/test_a.py"), "pass\n"),
                                         # the MAIN tree is dirty too
                                         write(os.path.join(w + "-main", "tests", "test_x.py"), "pass\n")))
add("builder-diff: a stop with a test change is blocked", "deny", rule=BDIFF,
    event="SubagentStop", cwd=_repo, agent_id="bld1", agent_type="builder")
add("builder-diff: an unread diff logs role-diff-unread and the first stop is allowed", "allow",
    event="SubagentStop", cwd=NOGIT, agent_id="bld1", agent_type="builder")
add("builder-diff: a stop with no cwd is allowed (and logged)", "allow", event="SubagentStop",
    agent_id="bld1", agent_type="builder")
add("builder-diff: a stop whose cwd is a main checkout is allowed (and logged)", "allow",
    event="SubagentStop", cwd=os.path.join(DIFFROOT, "b-giveup-main"), agent_id="bld1",
    agent_type="builder")


def role_log_case():
    """Every stop the guard cannot judge LOGS, so an unjudged stop is never a silent pass."""
    materialize(os.path.join(DIFFROOT, "b-giveup"))
    folder = os.path.join(ROOT, "rolelog")
    os.makedirs(folder, exist_ok=True)
    env = dict(os.environ)
    env.pop("CLAUDE_CODE_REMOTE", None)
    env["CLAUDE_CONFIG_DIR"] = folder
    stops = [
        ({"cwd": os.path.join(DIFFROOT, "b-giveup-main")}, "role-diff-main-checkout"),
        ({"cwd": os.path.join(DIFFROOT, "b-giveup"), "stop_hook_active": True},
         "role-diff-unresolved"),
        ({"cwd": NOGIT}, "role-diff-unread"),
    ]
    problems = []
    for extra, want in stops:
        body = {"hook_event_name": "SubagentStop", "agent_id": "bld1", "agent_type": "builder"}
        body.update(extra)
        got = subprocess.run([sys.executable, GUARD], input=json.dumps(body), capture_output=True,
                             text=True, env=env, timeout=60)
        if got.stdout.strip():
            problems.append("%s: expected a silent allow, got %r" % (want, got.stdout[:60]))
    path = os.path.join(folder, "guard.log")
    text = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    for _, want in stops:
        if want not in text:
            problems.append("no log line for " + want)
    return (not problems), ("; ".join(problems) or "each unjudged stop is logged")


def _diff_log_run(folder, repo, agent_type, agent_id, commit=True):
    """Run commit, push and stop for one agent in `repo`, or push and stop alone when `commit` is False.
    Returns (stdout seen, guard.log rows)."""
    materialize(repo)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "guard.log")
    if os.path.exists(path):
        os.remove(path)
    env = dict(os.environ)
    env.pop("CLAUDE_CODE_REMOTE", None)
    env["CLAUDE_CONFIG_DIR"] = folder
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    env["CLAUDE_GUARD_ROOT_PID"] = str(os.getpid())
    bodies = [{"tool_name": "Bash", "tool_input": {"command": c}, "cwd": repo,
               "agent_id": agent_id, "agent_type": agent_type} for c in ((COMMIT, PUSH) if commit else (PUSH,))]
    bodies.append({"hook_event_name": "SubagentStop", "cwd": repo, "agent_id": agent_id,
                   "agent_type": agent_type})
    out = ""
    for body in bodies:
        got = subprocess.run([sys.executable, GUARD], input=json.dumps(body), capture_output=True,
                             text=True, env=env, timeout=120)
        out += got.stdout.strip()
    text = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    return out, [line.split("\t") for line in text.splitlines() if line.strip()]


def _guard_answers(text):
    """(decision, reason) for each JSON document in `text`, in order. A guard call prints one document."""
    found, decoder, index = [], json.JSONDecoder(), 0
    text = text.strip()
    while index < len(text):
        doc, index = decoder.raw_decode(text, index)
        found.append(read_decision(json.dumps(doc)))
        while index < len(text) and text[index].isspace():
            index += 1
    return found


def diff_refusal_case():
    """The diff check refuses a builder's test change at commit, push and stop, and logs a test-author's
    diff. A test-author's diff logs for the reviewer and never blocks: commit, push and stop print nothing
    and write one `noted` line each, named `author-diff`. The builder half is one run of the same three
    calls on the incident repo; BUILDER_RED pins each call on its own."""
    problems = []
    out, _rows = _diff_log_run(os.path.join(ROOT, "difflog-bd-incident"), _bd_inc, "builder", "bld1")
    got = [decision for decision, _reason in _guard_answers(out)]
    if got != ["deny", "deny", "deny"]:
        problems.append("builder: expected deny at commit, push and stop, got %r" % got)
    for label, agent_type, agent_id, rule in (
            ("a-product-edit", "test-author", "auth1", "author-diff"),
            # An untracked file: the mutant that reads tracked files only is caught by this row alone.
            ("a-product-new", "test-author", "auth1", "author-diff")):
        out, rows = _diff_log_run(os.path.join(ROOT, "difflog-" + label),
                                  os.path.join(DIFFROOT, label), agent_type, agent_id)
        if out:
            problems.append("%s: expected silent allows, got %r" % (label, out[:60]))
        hits = [r for r in rows if len(r) == 6 and r[2] == "noted" and r[3] == rule]  # six: session last
        if len(hits) != 3:
            problems.append("%s: expected 3 noted/%s lines, found %d" % (label, rule, len(hits)))
    return (not problems), ("; ".join(problems) or "builder refused at three calls; each author diff logged and allowed")


def _long_lived_main_tests(w):
    """A long-lived worktree: it was reset to a lane that main has since passed. Main gained test files
    and a test change, and the branch merged main in. The merge entry is then deleted from HEAD's
    reflog, so the lane tip and main's tip are two independent bases: the merge base with main is
    the only route to main's tip. Those test files equal main's, so they are not the builder's."""
    main = w + "-main"
    _must(main, "checkout", "-q", "-b", "lane")
    write(os.path.join(main, "src/app.py"), "x = 6\n")
    _must(main, "add", "-A")
    _must(main, *IDENT, "commit", "-q", "-m", "lane product")
    _must(main, "checkout", "-q", "main")
    _must(w, "reset", "-q", "--hard", "lane")
    write(os.path.join(main, "tests/test_late.py"), "pass  # main added this later\n")
    write(os.path.join(main, "tests/test_a.py"), "pass  # main edited this later\n")
    _must(main, "add", "-A")
    _must(main, *IDENT, "commit", "-q", "-m", "main moves")
    _must(w, *IDENT, "merge", "-q", "--no-edit", "main")
    _must(w, "reflog", "delete", "HEAD@{0}")
    write(os.path.join(w, "src/app.py"), "x = 7\n")


_long_lived = diff_repo("g-long-lived", _long_lived_main_tests)
add("builder-diff: a long-lived worktree with main's later tests merged in is allowed",
    "allow", event="SubagentStop", cwd=_long_lived, agent_id="bld1", agent_type="builder",
    silent=True)


def long_lived_no_log_case():
    out, rows = _diff_log_run(os.path.join(ROOT, "difflog-longlived"), _long_lived, "builder", "bld1")
    rows = [r for r in rows if len(r) > 3 and r[3] in ("builder-diff", "author-diff")]
    if out or rows:
        return False, "main's own test files were judged: %r %r" % (out[:60], rows)
    return True, "allowed with no builder-diff line"


_author_mutant = diff_repo("g-author-mutant", _put("hooks/mutate_guard.py", "pass\n"))


def author_mutant_no_log_case():
    """A test-author's edit of a mutation test is test code: commit and stop log no author-diff line."""
    out, rows = _diff_log_run(os.path.join(ROOT, "difflog-author-mutant"), _author_mutant,
                              "test-author", "auth1")
    rows = [r for r in rows if len(r) > 3 and r[3] == "author-diff"]
    if out or rows:
        return False, "a mutation test was judged: %r %r" % (out[:60], rows)
    return True, "a mutation test logs no author-diff line"


LOG_CHECKS_EXTRA = _TaggedLogs([
    ("role-diff: every unjudged stop is logged", role_log_case),
    ("builder-diff: the diff check refuses a builder's test change and logs a test-author's diff", diff_refusal_case),
    ("builder-diff: main's later tests merged into a long-lived worktree log nothing",
     long_lived_no_log_case),
    ("author-diff: a test-author's mutation test edit logs no author-diff line",
     author_mutant_no_log_case),
])
for _label, _check in LOG_CHECKS_EXTRA:  # the literal above is not appended: tag it here
    LOG_FAMILY.setdefault(_label, _family(_label))
# FLAG ORDER (pwsh-c-text-mode). POWERSHELL_CALL is one global that each judge sets for its own call. A
# caller that reads it without setting it reads the last call's tool. Each pin reads one caller on a
# PowerShell text, with the flag set by a PowerShell call, then judges a Bash call in this process and reads
# the caller again. The text's `\"` ends a string for PowerShell and hides a write for bash, so a caller
# that kept the Bash flag gives a different reading, and the pin fails.
FLAG_BUILD_TEXT = 'echo "x\\" ; Set-Content hooks/test_probe.py -Value 1 ; echo \\"D"'
FLAG_SESSION_TEXT = 'echo "x\\" ; Set-Content notes/out.txt -Value 1 ; echo \\"D"'
FLAG_SETTINGS_TEXT = ('echo "C:\\" ; Set-Content .claude/settings.local.json \''
                      + json.dumps({"env": {"CLAUDE_CODE_SUBAGENT_MODEL": "opus"}, "force": "1"})
                      + '\' ; echo \\"D"')


def _judge_bash_here(guard, cwd):
    """Judge one Bash call on this module, as the hook does, so POWERSHELL_CALL holds the Bash tool's value."""
    saved = os.environ.get("CLAUDE_CONFIG_DIR")
    os.environ["CLAUDE_CONFIG_DIR"] = CFG
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                guard.judge({"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": cwd})
            except SystemExit:
                pass
    finally:
        if saved is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = saved


def _flag_pin(label, guard, cwd, read):
    """`read()` is one caller's reading of a PowerShell text. Read with the PowerShell flag, it must find
    the write; after a Bash call in this process it must read the same."""
    guard.POWERSHELL_CALL[0] = True
    with_flag = read()
    if not with_flag:
        return False, "%s: the PowerShell reading finds no write, so the pin proves nothing" % label
    _judge_bash_here(guard, cwd)
    if guard.POWERSHELL_CALL[0]:
        return False, "%s: the Bash call left POWERSHELL_CALL set, so the pin proves nothing" % label
    after_bash = read()
    if after_bash != with_flag:
        return False, "%s: after a Bash call the caller read the text by bash rules and saw %r, not %r" % (
            label, after_bash, with_flag)
    return True, "%s: the caller reads the PowerShell text the same after a Bash call" % label


def flag_builder_case():
    guard = _load_guard_module()
    where = os.path.join(ROOT, "flag-builder")
    make_repo(where, {"hooks/test_seed.py": "x = 1\n"})
    stripped = guard.strip_heredoc_bodies(FLAG_BUILD_TEXT)
    return _flag_pin("builder shell-write caller", guard, where,
                     lambda: guard.builder_shell_test_hit(FLAG_BUILD_TEXT, stripped, where, tool="PowerShell"))


def flag_builder_bash_case():
    """A Bash-tool call on the same text reads it by bash rules, even after a PowerShell call set the flag."""
    guard = _load_guard_module()
    where = os.path.join(ROOT, "flag-builder-bash")
    make_repo(where, {"hooks/test_seed.py": "x = 1\n"})
    stripped = guard.strip_heredoc_bodies(FLAG_BUILD_TEXT)
    # The PowerShell call first leaves the flag set, so only the Bash call's own reset can make it read by bash rules.
    guard.builder_shell_test_hit(FLAG_BUILD_TEXT, stripped, where, tool="PowerShell")
    bash = guard.builder_shell_test_hit(FLAG_BUILD_TEXT, stripped, where, tool="Bash")
    if bash != "":
        return False, "builder shell-write caller: the Bash-tool call read the text by PowerShell rules and saw %r" % (
            bash,)
    return True, "builder shell-write caller: the Bash-tool call reads the text by bash rules and sees no write"


def flag_session_home_case():
    guard = _load_guard_module()
    primary = os.path.join(ROOT, "flag-primary")
    make_repo(primary, {"src/app.py": "print(1)\n"})
    session = "shome-" + uuid.uuid4().hex
    write(os.path.join(primary, ".git", "session-homes", session),
          os.path.join(primary, ".claude", "worktrees", "gone-lane") + "\n")
    payload = {"tool_name": "PowerShell", "tool_input": {"command": FLAG_SESSION_TEXT}, "cwd": primary,
               "session_id": session}
    return _flag_pin("session-home caller", guard, primary,
                     lambda: guard.session_home_hit(payload, "PowerShell", payload["tool_input"], primary))


def flag_never_lifted_case():
    guard = _load_guard_module()
    where = os.path.join(ROOT, "flag-settings")
    make_repo(where, {"README.md": "x\n"})
    payload = {"tool_name": "PowerShell", "tool_input": {"command": FLAG_SETTINGS_TEXT}, "cwd": where}
    return _flag_pin("never-lifted settings clause", guard, where,
                     lambda: guard.never_lifted(payload, "PowerShell", payload["tool_input"], where))


for _label, _check in (
    ("frozen: a builder's shell write, read after a Bash call, is the same as with the PowerShell flag",
     flag_builder_case),
    ("frozen: a Bash-tool call on a builder's shell-write text reads it by bash rules, after a PowerShell call",
     flag_builder_bash_case),
    ("frozen: the session-home caller, read after a Bash call, is the same as with the PowerShell flag",
     flag_session_home_case),
    ("frozen: the never-lifted settings clause, read after a Bash call, is the same as with the PowerShell flag",
     flag_never_lifted_case),
):
    LOG_CHECKS_EXTRA.append((_label, _check))
    LOG_FAMILY[_label] = "frozen"


# The base-copy cost check is appended here because LOG_CHECKS_EXTRA is defined here. Its family is the
# base-copy section's, set by hand. MUTATE_ONLY="base copies" runs it.
BASE_COPY_COST_LABEL = ("base copies: the pushed-copy read on the incident tree stays within its stated git "
                        "starts and writes no file")
LOG_CHECKS_EXTRA.append((BASE_COPY_COST_LABEL, base_copies_read_cost_case))
LOG_FAMILY[BASE_COPY_COST_LABEL] = "branch-worktree"
# The two MCP updates that mark nothing ready, read by _rpr_no_read (records-page-ready). They sit here because
# LOG_CHECKS_EXTRA is defined here.
for _label, _check in (
    ("records-page-ready: an MCP title edit on a stale page is allowed and starts no gh call", rpr_title_only_case),
    ("records-page-ready: an MCP close on a stale page is allowed and starts no gh call", rpr_closed_case),
):
    LOG_CHECKS_EXTRA.append((_label, _check))
    LOG_FAMILY[_label] = RPR_RULE
# The agent-branch refusal's opening words (defined in the push section). Registered here, where LOG_CHECKS_EXTRA is
# defined, and its family is the push section's, set by hand.
AGENT_OPENS_LABEL = "push-agent-branch: the refusal's reason opens with Rule (Git), after its rule id"
LOG_CHECKS_EXTRA.append((AGENT_OPENS_LABEL, agent_refusal_opens_with_rule_case))
LOG_FAMILY[AGENT_OPENS_LABEL] = "push-delete"
# The two-worktrees-one-branch log checks read the stand-in's call log. Each builds only its own fixture,
# through decide's materialize_for, so a family run need not build every lazy fixture.
TWO_OBSERVER_LABEL = "two-worktrees: the stand-in logs a worktree list read the guard makes today"
TWO_LIST_ONCE_LABEL = "two-worktrees: the refused form reads the worktree list exactly once"
TWO_NO_LIST_LABEL = "two-worktrees: an unrelated git command reads no worktree list"
LOG_CHECKS_EXTRA.append((TWO_OBSERVER_LABEL, two_worktrees_observer_case))
LOG_CHECKS_EXTRA.append((TWO_LIST_ONCE_LABEL, two_worktrees_reads_list_once_case))
TWO_OWN_TREE_LABEL = "two-worktrees: the holder's own checkout -B x is no hit in the rule's own logic, from the holder's root"
LOG_CHECKS_EXTRA.append((TWO_NO_LIST_LABEL, two_worktrees_unrelated_no_list_case))
LOG_CHECKS_EXTRA.append((TWO_OWN_TREE_LABEL, two_worktrees_own_tree_case))
for _label in (TWO_OBSERVER_LABEL, TWO_LIST_ONCE_LABEL, TWO_NO_LIST_LABEL, TWO_OWN_TREE_LABEL):
    LOG_FAMILY[_label] = TWO_RULE
FIXTURELESS_CHECKS.update((two_worktrees_observer_case, two_worktrees_reads_list_once_case,
                           two_worktrees_unrelated_no_list_case, two_worktrees_own_tree_case))
# The two unreadable-lone-operand checks. Their cases and labels sit in the shared-tree block, which runs
# before LOG_CHECKS_EXTRA exists, so they register here and their family is set by hand, as above.
LOG_CHECKS_EXTRA.append((UNREAD_NOGIT_LABEL, unread_lone_operand_no_git_case))
LOG_FAMILY[UNREAD_NOGIT_LABEL] = "shared-tree"
LOG_CHECKS_EXTRA.append((UNREAD_STATUS_LABEL, unread_lone_operand_status_case))
LOG_FAMILY[UNREAD_STATUS_LABEL] = "shared-tree"
# The agent-owned noted rows of the reset and restore ruling. agent_worktree_noted_case is defined far below,
# so each label stores a lambda that calls it when the check runs, not when this file loads.
for _label, _command in AGENT_NOTED_RULING:
    LOG_CHECKS_EXTRA.append((_label, lambda command=_command: agent_worktree_noted_case(command)))
    LOG_FAMILY[_label] = "shared-tree"
# The wait-until remedy checks are defined beside the wait-until cases. They are log checks, so they are
# registered here, where LOG_CHECKS_EXTRA is defined, and their family is set by hand.
for _constant in REMEDY_CONSTANTS:
    _remedy_label = "wait-until remedy: every command form the %s names is allowed" % _constant
    LOG_CHECKS_EXTRA.append((_remedy_label, remedy_check(_constant)))
    LOG_FAMILY[_remedy_label] = "stream"
# The check-timeout remedy and its hygiene check (section 6591) are registered here too. The remedy is not in
# REMEDY_CONSTANTS: that loop labels each entry as a wait-until remedy, and this one names a time limit.
CHECK_TIMEOUT_REMEDY_LABEL = "check-timeout remedy: every command form the CHECK_TIMEOUT_REASON names is allowed under the limit"
LOG_CHECKS_EXTRA.append((CHECK_TIMEOUT_REMEDY_LABEL, remedy_check(
    "CHECK_TIMEOUT_REASON",
    trigger=(CHECK_TIMEOUT_RULE, {"command": CHECK_TIMEOUT_LINT, "run_in_background": True,
                                  "timeout": CHECK_TIMEOUT_LOW_MS, "description": TAIL_BG_UNTIL}),
    limit=CHECK_TIMEOUT_MS)))
LOG_FAMILY[CHECK_TIMEOUT_REMEDY_LABEL] = "stream"
CHECK_TIMEOUT_HYGIENE_LABEL = "check-timeout: the refusal's remedy names the limit to use and no part of the refused call"
LOG_CHECKS_EXTRA.append((CHECK_TIMEOUT_HYGIENE_LABEL, check_timeout_hygiene_case))
LOG_FAMILY[CHECK_TIMEOUT_HYGIENE_LABEL] = "stream"
# The octopus-push remedy check is defined in its section above. It builds only the fixture it reads, through
# decide, so it is fixtureless and a family run does not build every fixture. Its family is set by hand.
OCT_REMEDY_LABEL = "octopus-push: the refusal's remedy names the two-parent form and not the forbidden target"
LOG_CHECKS_EXTRA.append((OCT_REMEDY_LABEL, octopus_remedy_case))
LOG_FAMILY[OCT_REMEDY_LABEL] = "octopus-push"
FIXTURELESS_CHECKS.add(octopus_remedy_case)
for _name, _change in BUILDER_GREEN:
    if getattr(_change, "needs_link", False) and not LINKS_MADE:
        continue
    _repo = diff_repo("g-" + _name, _change)
    sh("builder-diff: commit with %s is allowed" % _name, COMMIT, "allow", cwd=_repo,
       agent_id="bld1", agent_type="builder")
    add("builder-diff: stop with %s is allowed" % _name, "allow", event="SubagentStop",
        cwd=_repo, agent_id="bld1", agent_type="builder")
_dirty = diff_repo("main-dirty", _put("tests/test_a.py", "pass\n"))
sh("builder-diff: the main session may commit a test change", COMMIT, "allow", cwd=_dirty)
sh("builder-diff: a reviewer may commit a test change", COMMIT, "allow", cwd=_dirty,
   agent_id="rev1", agent_type="reviewer")
sh("builder-diff: a session run with --agent builder (no agent_id) is not judged", COMMIT,
   "allow", cwd=_dirty, agent_type="builder")
add("builder-diff: a reviewer stop with a test change is allowed", "allow", event="SubagentStop",
    cwd=_dirty, agent_id="rev1", agent_type="reviewer")
sh("builder-diff: a builder in a tree git cannot read is allowed and noted", COMMIT, "allow",
   cwd=NOGIT, agent_id="bld1", agent_type="builder")
sh("builder-diff: reads stay allowed in a dirty tree", "cat tests/test_a.py && ls tests",
   "allow", cwd=_dirty, agent_id="bld1", agent_type="builder")

# ---- hook-bypass: the one exemption. hooks/mutate_shared.py sets core.hooksPath for the throwaway worktree it
# makes, and the guard never sees that git call. The allow above holds only while that code path sets the key,
# so this check reads the file and finds the setting in the function that makes the worktree. A copy of the
# string in the guard would pass a check that reads the guard alone.
