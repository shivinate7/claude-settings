# section 22868
FAMILY = "paths"
# ---- the test-author, inverted: only tests and test config may change
AUTHOR_GREEN = [
    ("new-test", _put("tests/test_new.py", "pass\n")),
    ("edited-test", _put("tests/test_a.py", "pass\n")),
    ("test-config", _put("pytest.ini", "[pytest]\naddopts = --deselect x\n")),
    ("conftest", _put("conftest.py", "import pytest\n")),
    ("clean-tree", lambda w: None),
    ("dev-dependency", _put("package.json", '{"name": "x", "scripts": {"build": "tsc", "test": '
                            '"jest"}, "dependencies": {"a": "1"}, "devDependencies": {"b": "2"}}\n')),
    ("test-script", _put("package.json", '{"name": "x", "scripts": {"build": "tsc", "test": '
                         '"jest --ci", "test:unit": "jest u"}, "dependencies": {"a": "1"}, '
                         '"devDependencies": {"b": "1"}}\n')),
    ("dev-requirements", _put("requirements-dev.txt", "pytest\nhypothesis\n")),
    ("testdata", _put("testdata/x.json", "{}\n")),
    ("snapshots", _put("src/__snapshots__/a.snap", "snap\n")),
    ("jest-setup", _put("jest.setup.js", "global.x = 1\n")),
    ("java-test", _put("src/FooTest.java", "class FooTest {}\n")),
    ("test-support", _put("test_support/helper.py", "pass\n")),
    # A test-author writes a mutation test, so the same change is allowed to it (control for BUILDER_RED).
    ("mutation-test", _put("hooks/mutate_guard.py", "x = 2\n")),
    ("pytest-section", _put("pyproject.toml", "[project]\nname = 'x'\n[tool.pytest.ini_options]\n"
                            "minversion = '8'\naddopts = '-q'\n")),
]
AUTHOR_RED = [
    ("product-edit", _put("src/app.py", "x = 2\n")),
    ("product-new", _put("src/new.py", "x = 2\n")),
    ("product-delete", _rm("src/contest.py")),
    ("docs-edit", _put("latest_results.md", "better\n")),
    ("package-json", _put("package.json", '{"name": "y"}\n')),
    ("runtime-dependency", _put("package.json", '{"name": "x", "scripts": {"build": "tsc", '
                                '"test": "jest"}, "dependencies": {"a": "2"}, "devDependencies": '
                                '{"b": "1"}}\n')),
    ("build-script", _put("package.json", '{"name": "x", "scripts": {"build": "make", "test": '
                          '"jest"}, "dependencies": {"a": "1"}, "devDependencies": {"b": "1"}}\n')),
    ("pyproject-project-section", _put("pyproject.toml", "[project]\nname = 'x'\ndependencies = "
                                       "['y']\n[tool.pytest.ini_options]\nminversion = '7'\n")),
    ("mixed", lambda w: (write(os.path.join(w, "tests/test_new.py"), "pass\n"),
                         write(os.path.join(w, "src/app.py"), "x = 3\n"))),
    ("test-symlink-to-product", _link("../src/app.py", "tests/alias.py")),
]
for _name, _change in AUTHOR_RED:
    if getattr(_change, "needs_link", False) and not LINKS_MADE:
        continue
    _repo = diff_repo("a-" + _name, _change)
    sh("author-diff: commit with a %s change is allowed and logged" % _name, COMMIT, "allow",
       cwd=_repo, agent_id="auth1", agent_type="test-author")
    sh("author-diff: push with a %s change is allowed and logged" % _name, PUSH, "allow",
       cwd=_repo, agent_id="auth1", agent_type="test-author")
    add("author-diff: stop with a %s change is allowed and logged" % _name, "allow",
        event="SubagentStop", cwd=_repo, agent_id="auth1", agent_type="test-author")
for _name, _change in AUTHOR_GREEN:
    _repo = diff_repo("ag-" + _name, _change)
    sh("author-diff: commit with %s is allowed" % _name, COMMIT, "allow", cwd=_repo,
       agent_id="auth1", agent_type="test-author")
    add("author-diff: stop with %s is allowed" % _name, "allow", event="SubagentStop",
        cwd=_repo, agent_id="auth1", agent_type="test-author")


# ---- workflow files at commit time: the diff a test-author or a builder would commit (role_offences). A
# test-author's lint change is logged and allowed. A builder's test change is refused at commit.
WF_BASE = LINT + TEST_LINUX
WF_FILES = {**BASE_FILES, WF: WF_BASE}
_repo = diff_repo("wfa-lint-run", _put(WF, LINT_RUN_CHANGED + TEST_LINUX), files=WF_FILES)
sh("author-diff: commit with a workflow lint change is allowed and logged", COMMIT, "allow", cwd=_repo,
   agent_id="auth1", agent_type="test-author")
for _slug, _label, _text, _expect in (
    ("wfb-deselect", "a --deselect pytest line", LINT + DESELECT, "deny"),
    ("wfb-continue-on-error", "a continue-on-error test step", LINT + CONTINUE_ON_ERROR, "deny"),
    ("wfb-delete-test-step", "a deleted test step", LINT, "deny"),
    ("wfb-ruff-tests", "a ruff --ignore line on tests/", LINT + TEST_LINUX + RUFF_TESTS, "allow"),
):
    _repo = diff_repo(_slug, _put(WF, _text), files=WF_FILES)
    if _expect == "deny":
        sh("builder-diff: commit with %s in checks.yml is denied" % _label, COMMIT, "deny", rule=BDIFF,
           cwd=_repo, agent_id="bld1", agent_type="builder")
    else:
        sh("builder-diff: commit with %s in checks.yml is allowed" % _label, COMMIT, "allow", cwd=_repo,
           agent_id="bld1", agent_type="builder")


# ---- record-writer: Markdown only (owner ruling 2026-10-10). Writing prose and records is not
# building, so a Haiku record-writer may change `*.md` files and nothing else. The limit is the
# point: without it the role is a Haiku builder under a new label. Failure classes: false allow (a
# non-.md path slips through) and false deny (an .md path is blocked).
RW = dict(agent_id="rw1", agent_type="record-writer", cwd=NOGIT)
RW_RULE = "record-writer-scope"
# One allow row per tool and per path spelling that the rule reads: a markdown file in a folder, and
# the upper-case extension. The Write tool takes the same branch as Edit for an .md path.
for _tool, _path in (("Edit", "docs/x.md"), ("Write", "decisions/y.md"), ("Edit", "README.MD")):
    add("record-writer: %s of %s is allowed" % (_tool, _path), "allow", tool=_tool,
        file_path=_path, new_string="x", **RW)
for _tool in ("Edit", "Write"):
    for _path in ("hooks/guard.py", "lint/x.json", ".github/workflows/checks.yml",
                  "hooks/test_guard.py", "settings.json", "notes.md.py"):
        add("record-writer: %s of %s is refused" % (_tool, _path), "deny", rule=RW_RULE,
            carries=("Markdown", "Report"), tool=_tool, file_path=_path, new_string="x", **RW)

# ---- designer: the design folder only (decision design-agents). A designer writes mockups, not product code. The folder is the `design` kind of
# lint/layout.json, read from the file. Failure classes: false allow (a path outside the folder, or a
# near-miss name, slips through) and false deny (a mockup, its notes, or a scratch file is blocked).
DZ = dict(agent_id="dz1", agent_type="designer", cwd=GITMAIN)
DZ_RULE = "designer-scope"
for _tool, _path in (("Write", "docs/design/robots.html"), ("Edit", "docs/design/robots-notes.md"),
                     ("Write", os.path.join(GITMAIN, "docs", "design", "tabs", "a.css")),
                     ("Write", "Docs/Design/x.html")):
    add("designer: %s of %s is allowed" % (_tool, _path), "allow", tool=_tool, file_path=_path,
        new_string="x", content="x", **DZ)
for _tool in ("Edit", "Write"):
    for _path in ("src/App.tsx", "docs/designs/x.html", "docs/design.md", "docs/design",
                  "docs/design/../x.py", "CLAUDE.md", "hooks/guard.py", "x/docs/design/y.html"):
        add("designer: %s of %s is refused" % (_tool, _path), "deny", rule=DZ_RULE,
            carries=("design folder", "Report"), tool=_tool, file_path=_path, new_string="x",
            content="x", **DZ)
    add("designer: %s of a temp file in no repo is allowed" % _tool, "allow", tool=_tool,
        file_path=os.path.join(ROOT, "outside", "shot.png"), content="x", new_string="x", **DZ)
add("designer: a decoy mockup path does not hide a product path in another field", "deny",
    rule=DZ_RULE, tool="NotebookEdit", file_path="docs/design/x.html", notebook_path="src/a.ipynb",
    **DZ)
# Controls: the design reviewer never writes, and the builder's own scope is unchanged by the new role.
add("designer-control: a builder may still write docs/design/x.html", "allow", tool="Write",
    file_path="docs/design/x.html", content="x", **dict(B, cwd=GITMAIN))
add("designer-control: a design-reviewer Write is not a designer write", "allow", tool="Write",
    file_path="src/App.tsx", content="x", agent_id="dr1", agent_type="design-reviewer",
    cwd=GITMAIN)

# ---- audit-high (owner ruling 2026-10-13): the test-author's own scratch writes.
# A path in no repository was judged by its full path, so the session scratchpad and a temp file
# were refused (incident: 403 denies a week). Product code IN a repository stays refused. The
# scratchpad allowance is the one under_session_scratchpad gives, keyed by the session id the payload
# carries. A scratchpad inside a repository tells that check apart from the outside-repo rule: only
# the matching session id is allowed there.
SCRATCH_SID = "audit-high-session-01"
SCRATCH_OTHER = "audit-high-session-02"
OUTSIDE_TEMP = os.path.join(ROOT, "outside", "notes.txt")
SESSION_SCRATCH = os.path.join(ROOT, SCRATCH_SID, "scratchpad", "notes", "out.txt")
REPO_SCRATCH = os.path.join(GITMAIN, SCRATCH_SID, "scratchpad", "notes", "out.txt")
REPO_OTHER_SCRATCH = os.path.join(GITMAIN, SCRATCH_OTHER, "scratchpad", "notes", "out.txt")
for _tool in ("Edit", "Write"):
    add("audit-high paths: test-author %s of a temp file in no repo is allowed" % _tool, "allow",
        tool=_tool, file_path=OUTSIDE_TEMP, **A)
    add("audit-high paths: test-author %s of its session scratchpad is allowed" % _tool, "allow",
        tool=_tool, file_path=SESSION_SCRATCH, session=SCRATCH_SID, **A)
    add("audit-high paths: test-author %s of its session scratchpad in a repo is allowed" % _tool,
        "allow", tool=_tool, file_path=REPO_SCRATCH, session=SCRATCH_SID, **A)
    add("audit-high paths: test-author %s of another session's scratchpad in a repo is refused"
        % _tool, "deny", rule=TA, tool=_tool, file_path=REPO_OTHER_SCRATCH, session=SCRATCH_SID,
        **A)
    add("audit-high paths: test-author %s of product code in a repo is refused" % _tool, "deny",
        rule=TA, tool=_tool, file_path=os.path.join(GITMAIN, "src", "app.py"), **A)
add("audit-high paths: record-writer Write of a temp file in no repo is still refused", "deny",
    rule=RW_RULE, carries=("Markdown", "Report"), tool="Write", file_path=OUTSIDE_TEMP, **RW)
# The ruling covers ITS OWN session scratchpad. Another session's scratchpad outside every
# repository is refused too: the outside-repo allowance above does not reach it.
OTHER_SCRATCH_OUT = os.path.join(ROOT, SCRATCH_OTHER, "scratchpad", "notes", "out.txt")
for _tool in ("Edit", "Write"):
    add("audit-high paths: test-author %s of another session's scratchpad outside a repo is refused"
        % _tool, "deny", rule=TA, tool=_tool, file_path=OTHER_SCRATCH_OUT, session=SCRATCH_SID, **A)
# Windows folder names are case-insensitive: `Scratchpad` and `SCRATCHPAD` are the same folder as
# `scratchpad`, so another session's folder spelled either way is refused there. On Linux and macOS
# they are different folders, judged as no scratchpad, so allowed.
for _tool in ("Edit", "Write"):
    for _spelling in ("Scratchpad", "SCRATCHPAD"):
        _path = os.path.join(ROOT, SCRATCH_OTHER, _spelling, "notes", "out.txt")
        add("audit-high paths: test-author %s of another session's %s outside a repo, by OS"
            % (_tool, _spelling), "deny" if os.name == "nt" else "allow",
            rule=TA if os.name == "nt" else None, tool=_tool, file_path=_path,
            session=SCRATCH_SID, **A)
# A git clone under the test-author's own scratchpad (PRIVREPO sits under FAKE_SESSION's
# scratchpad): a write to a file in that clone stays allowed, with the clone as the cwd.
for _tool in ("Edit", "Write"):
    add("audit-high paths: test-author %s of a file in a clone under its own scratchpad is allowed"
        % _tool, "allow", tool=_tool, file_path=os.path.join(PRIVREPO, "f.txt"),
        session=FAKE_SESSION, **dict(A, cwd=PRIVREPO))

# ---- every path field a write call carries is judged. The guard picks ONE target,
# the first non-empty of file_path, path, notebook_path, so a harmless decoy in file_path hid a real
# target in another field. Failure classes: false allow (a decoy still passes) and false deny (an
# all-allowed multi-field call, or a normal single-field call, is blocked).
add("decoy: NotebookEdit record-writer, notebook_path=lint/x.ipynb beside file_path=docs/x.md is refused",
    "deny", rule=RW_RULE, tool="NotebookEdit", carries=("Markdown", "Report"),
    notebook_path="lint/x.ipynb", file_path="docs/x.md", **RW)
add("decoy: NotebookEdit builder, notebook_path=tests/x.ipynb beside file_path=src/a.py is refused",
    "deny", rule=BT, tool="NotebookEdit", notebook_path="tests/x.ipynb",
    file_path="src/a.py", **B)
add("decoy: Edit test-author, file_path=tests/t.py beside path=hooks/guard.py is refused",
    "deny", rule=TA, tool="Edit", file_path="tests/t.py", path="hooks/guard.py", **A)
add("decoy: Edit main session, file_path=docs/x.md beside path=.env is refused",
    "deny", rule="env-file", tool="Edit", cwd=NOGIT, file_path="docs/x.md", path=ENV)
add("decoy: Edit main session, file_path=docs/x.md beside path=the config hook is refused",
    "deny", rule="frozen-path", tool="Edit", cwd=NOGIT, file_path="docs/x.md", path=CFG_HOOK)
add("decoy: Edit builder, file_path=src/a.py beside path=tests/test_a.py is refused",
    "deny", rule=BT, tool="Edit", file_path="src/a.py", path="tests/test_a.py", **B)
add("decoy: Edit builder, an empty file_path does not hide notebook_path=tests/x.ipynb",
    "deny", rule=BT, tool="NotebookEdit", file_path="", notebook_path="tests/x.ipynb", **B)
# Controls: every field on an allowed path stays allowed, and a single field keeps its verdict.
add("decoy-control: Edit record-writer, two .md fields are allowed", "allow", tool="Edit",
    file_path="docs/x.md", path="decisions/y.md", **RW)
add("decoy-control: Edit builder, two source fields are allowed", "allow", tool="Edit",
    file_path="src/a.py", path="src/b.py", **B)
add("decoy-control: NotebookEdit builder, two source fields are allowed", "allow",
    tool="NotebookEdit", notebook_path="src/a.ipynb", file_path="src/b.py", **B)
add("decoy-control: Edit test-author, two test fields are allowed", "allow", tool="Edit",
    file_path="tests/t.py", path="tests/u.py", **A)
add("decoy-control: Edit main session, two ordinary fields are allowed", "allow", tool="Edit",
    cwd=NOGIT, file_path="docs/x.md", path="src/b.py")
add("decoy-control: NotebookEdit record-writer, a lone lint notebook is refused", "deny",
    rule=RW_RULE, tool="NotebookEdit", notebook_path="lint/x.ipynb", **RW)
add("decoy-control: Edit test-author, a lone test file is allowed", "allow", tool="Edit",
    file_path="tests/t.py", **A)
add("decoy-control: Edit builder, a lone source path is allowed", "allow", tool="Edit",
    path="src/a.py", **B)
add("decoy-control: Edit main session, a lone config hook is refused", "deny", rule="frozen-path",
    tool="Edit", cwd=NOGIT, path=CFG_HOOK)

# ---- an earlier field's ASK must not mask a later field's DENY. The write
# loop refused on rule 8's ask at the first settings field and exited, so a deny in a later field
# was never judged. Every deny now runs over all fields first; the cap ask runs after them. Failure
# classes: false allow (an ask masks a deny) and false deny (a lone ask becomes a deny).
CAP_LINE = "CLAUDE_CODE_SUBAGENT_MODEL=haiku\n"
CLONE_ENV = slash(os.path.join(CLONE, ENV))
add("gap: NotebookEdit, settings cap in file_path beside notebook_path=.env is denied as env-file",
    "deny", "env-file", tool="NotebookEdit", cwd=NOGIT, file_path=PROJ_LOCAL, new_source=CAP_LINE,
    notebook_path=CLONE_ENV)
add("gap-control: NotebookEdit, the env file in file_path beside the settings cap is denied as env-file",
    "deny", "env-file", tool="NotebookEdit", cwd=NOGIT, file_path=CLONE_ENV, notebook_path=PROJ_LOCAL,
    new_source=CAP_LINE)
add("gap-control: NotebookEdit main session, an ordinary file_path beside notebook_path=.env is denied",
    "deny", "env-file", tool="NotebookEdit", cwd=NOGIT, file_path="docs/x.md", notebook_path=CLONE_ENV)
add("gap: NotebookEdit, settings cap in file_path beside notebook_path=the config hook is denied as frozen-path",
    "deny", "frozen-path", tool="NotebookEdit", cwd=NOGIT, file_path=PROJ_LOCAL,
    new_source=cap_settings(), notebook_path=CFG_HOOK)
add("gap-control: NotebookEdit, a lone settings cap in file_path still asks",
    "ask", "agent-model-cap", tool="NotebookEdit", cwd=NOGIT, file_path=PROJ_LOCAL,
    new_source=cap_settings(), carries=(OPUS,))
add("gap-control: NotebookEdit, a settings cap in file_path beside an ordinary notebook still asks",
    "ask", "agent-model-cap", tool="NotebookEdit", cwd=NOGIT, file_path=PROJ_LOCAL,
    new_source=cap_settings(), notebook_path="docs/x.ipynb", carries=(OPUS,))
# Rule 8 runs over every path field, so a settings file in a LATER field (notebook_path) still asks.
# Failure class: a rule-8 loop that judges only the first field lets this settings cap through.
add("gap: NotebookEdit, settings cap in notebook_path beside file_path=docs/x.ipynb still asks",
    "ask", "agent-model-cap", tool="NotebookEdit", cwd=NOGIT, file_path="docs/x.ipynb",
    new_source=cap_settings(), notebook_path=PROJ_LOCAL, carries=(OPUS,))

# The diff, judged at commit, push and stop. A non-.md path logs `writer-diff` (never blocks);
# an all-.md diff logs nothing.
RW_RED = (
    ("product-edit", _put("src/app.py", "x = 2\n")),
    ("test-new", _put("tests/test_new.py", "pass\n")),
    ("config-new", _put("lint/x.json", "{}\n")),
)
RW_GREEN = (
    ("markdown-only", lambda w: (write(os.path.join(w, "latest_results.md"), "better\n"),
                                 write(os.path.join(w, "docs/new.md"), "# new\n"),
                                 write(os.path.join(w, "decisions/y.md"), "# y\n"))),
)
for _name, _change in RW_RED:
    _repo = diff_repo("rw-" + _name, _change)
    sh("record-writer-diff: commit with a %s change is allowed" % _name, COMMIT, "allow",
       cwd=_repo, agent_id="rw1", agent_type="record-writer")
    sh("record-writer-diff: push with a %s change is allowed" % _name, PUSH, "allow",
       cwd=_repo, agent_id="rw1", agent_type="record-writer")
    add("record-writer-diff: stop with a %s change is allowed" % _name, "allow",
        event="SubagentStop", cwd=_repo, agent_id="rw1", agent_type="record-writer")
for _name, _change in RW_GREEN:
    _repo = diff_repo("rw-" + _name, _change)
    sh("record-writer-diff: commit with an all-.md change is allowed", COMMIT, "allow",
       cwd=_repo, agent_id="rw1", agent_type="record-writer", silent=True)
    sh("record-writer-diff: push with an all-.md change is allowed", PUSH, "allow",
       cwd=_repo, agent_id="rw1", agent_type="record-writer", silent=True)
    add("record-writer-diff: stop with an all-.md change is allowed", "allow",
        event="SubagentStop", cwd=_repo, agent_id="rw1", agent_type="record-writer", silent=True)


def rw_diff_logs_case():
    """A record-writer's non-.md diff is logged once each at commit, push and stop, and never
    blocks."""
    out, rows = _diff_log_run(os.path.join(ROOT, "difflog-rw-product"),
                              os.path.join(DIFFROOT, "rw-product-edit"), "record-writer", "rw1")
    problems = []
    if out:
        problems.append("expected silent allows, got %r" % out[:60])
    hits = [r for r in rows if len(r) == 6 and r[2] == "noted" and r[3] == "writer-diff"]  # six
    if len(hits) != 3:
        problems.append("expected 3 noted/writer-diff lines, found %d" % len(hits))
    return (not problems), ("; ".join(problems) or "non-.md diff logged at commit, push and stop")


def rw_markdown_logs_case():
    """A record-writer's all-.md diff logs no writer-diff line at commit, push or stop."""
    out, rows = _diff_log_run(os.path.join(ROOT, "difflog-rw-markdown"),
                              os.path.join(DIFFROOT, "rw-markdown-only"), "record-writer", "rw1")
    rows = [r for r in rows if len(r) > 3 and r[3] == "writer-diff"]
    if out or rows:
        return False, "an all-.md diff was judged: %r %r" % (out[:60], rows)
    return True, "an all-.md diff logs no writer-diff line"


LOG_CHECKS_EXTRA.append(("record-writer-diff: a non-.md diff is logged at commit, push and stop",
                         rw_diff_logs_case))
LOG_CHECKS_EXTRA.append(("record-writer-diff: an all-.md diff logs no writer-diff line",
                         rw_markdown_logs_case))


# A designer's diff: a path outside the design folder logs `designer-diff` once each at commit, push and
# stop; a diff inside the folder logs nothing (decision design-agents).
DZ_RED = (("product-edit", _put("src/app.py", "x = 2\n")),)
DZ_GREEN = (("design-only", lambda w: (write(os.path.join(w, "docs/design/robots.html"), "<p>x</p>\n"),
                                       write(os.path.join(w, "docs/design/robots-notes.md"), "# x\n"))),)
for _name, _change in DZ_RED + DZ_GREEN:
    diff_repo("dz-" + _name, _change)


def dz_diff_case(name, want):
    def case():
        out, rows = _diff_log_run(os.path.join(ROOT, "difflog-dz-" + name),
                                  os.path.join(DIFFROOT, "dz-" + name), "designer", "dz1")
        hits = [r for r in rows if len(r) == 6 and r[2] == "noted" and r[3] == "designer-diff"]
        if out or len(hits) != want:
            return False, "expected %d noted/designer-diff lines and silent allows, got %d, %r" % (
                want, len(hits), out[:60])
        return True, "%d designer-diff lines" % want
    return case


LOG_CHECKS_EXTRA.append(("designer-diff: a product path is logged at commit, push and stop",
                         dz_diff_case("product-edit", 3)))
LOG_CHECKS_EXTRA.append(("designer-diff: a design-folder diff logs no designer-diff line",
                         dz_diff_case("design-only", 0)))


def dz_unread_layout_case():
    """With no readable lint/layout.json the design folder is unknown, so a designer may write no repo
    path: a false deny the designer reports, never a false allow. A readable layout still allows a mockup."""
    guard = _load_guard_module()
    empty = os.path.join(ROOT, "dz-no-layout")
    os.makedirs(empty, exist_ok=True)
    guard.settings_roots = lambda: [empty]
    del guard._DESIGN_FOLDER[:]
    if guard.designer_path_ok("/docs/design/robots.html"):
        return False, "an unread layout allowed a mockup path"
    guard = _load_guard_module()
    if not guard.designer_path_ok("/docs/design/robots.html"):
        return False, "a readable layout refused a mockup path"
    return True, "an unread layout allows no path; a readable one allows the mockup"


LOG_CHECKS_EXTRA.append(("designer-scope: an unread layout allows no path", dz_unread_layout_case))


# An .xctestplan diff: a builder's ADDED skippedTests line is logged once each at commit, push and
# stop; a builder's added codeCoverage line logs nothing; a test-author's plan edit logs nothing.
XCTESTPLAN_BASE = '{\n  "configurations" : [ ],\n  "testTargets" : [ ]\n}\n'
XCTESTPLAN_SKIP = ('{\n  "configurations" : [ ],\n  "testTargets" : [\n'
                   '    {\n      "skippedTests" : [ "LaunchTests" ]\n    }\n  ]\n}\n')
XCTESTPLAN_COVERAGE = '{\n  "codeCoverage" : true,\n  "configurations" : [ ],\n  "testTargets" : [ ]\n}\n'


def _plan_repo(name, text):
    """A worktree whose base holds the plan, and whose change rewrites it to `text`."""
    return diff_repo(name, _put(XCTESTPLAN, text), files={**BASE_FILES, XCTESTPLAN: XCTESTPLAN_BASE})


def xctestplan_logs_case():
    """A builder's added codeCoverage line logs nothing. A test-author's plan edit logs no
    author-diff line. A builder's added skippedTests line is refused, not logged: see the
    builder-refuse section, which builds the same plan repo (`xctestplan-skip`) once."""
    problems = []
    skip = os.path.join(DIFFROOT, "xctestplan-skip")
    out, rows = _diff_log_run(os.path.join(ROOT, "difflog-xctestplan-coverage"),
                              _plan_repo("xctestplan-coverage", XCTESTPLAN_COVERAGE), "builder",
                              "bld1")
    if out or rows:
        problems.append("coverage: expected no log, got %r %r" % (out[:60], rows))
    out, rows = _diff_log_run(os.path.join(ROOT, "difflog-xctestplan-author"), skip,
                              "test-author", "auth1")
    rows = [r for r in rows if len(r) > 3 and r[3] == "author-diff"]
    if out or rows:
        problems.append("author: a plan edit was judged: %r %r" % (out[:60], rows))
    return (not problems), ("; ".join(problems) or
                            "codeCoverage logs nothing; a test-author's plan edit logs no author-diff line")


LOG_CHECKS_EXTRA.append(("xctestplan-diff: a builder's codeCoverage line logs nothing, and a "
                         "test-author's plan edit logs no author-diff line", xctestplan_logs_case))


# =========================================================================== builder refusal
#
# A builder's test change is REFUSED at `git commit` and `git push`, and BLOCKED at its first
# SubagentStop (decision builders-cannot-edit-tests). These cases pin the base rule in guard.py
# diff_bases and diff_violation: each commit HEAD was handed by a reset, checkout, merge or pull is
# a base. A base that holds one of the agent's own commits still vouches for each path that commit
# did not change. A path offends only if it differs from every base that vouches for it. A test
# file that both sides changed in a hand-resolved merge offends whatever it holds. The rows that pin
# a stop, the write tool and a clean builder sit beside these.
