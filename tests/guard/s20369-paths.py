# section 20369
FAMILY = "paths"

for ordinary in (
    "npm test",
    "node harness/check-invariants.mjs",
    VCS + " status --short",
    VCS + " add -A",
    VCS + " add -A && " + VCS + " commit -m WIP",
    'grep -rn "tieOutState" src/',
    'sed -i "s/a/b/" src/components/Dashboard.tsx',
    "python hooks/test_guard.py",
):
    sh("ordinary: " + ordinary[:44], ordinary, "allow", cwd=NOGIT)
sh("ordinary: npm ci is not the PowerShell ci alias", "npm ci", "allow", tool="PowerShell",
   cwd=NOGIT)


# =========================================================================== builders do not edit tests
#
# The rule judges the RESULT: the diff a builder (or test-author) would commit, push or stop with.
# Only a payload with an agent_id AND a matching agent_type is judged. Three entry points read the
# same diff: a write tool (early warning, by path), `commit`/`push`, and SubagentStop.

BT = "builder-test-edit"
TA = "test-author-scope"
# Re-pointed in place (rule builders-cannot-edit-tests, refusal-vs-rule row builder-test-edit): a
# test path OUTSIDE every repository is no test of this repo, so these refusals run in a real linked
# worktree, as audit-high did for A below. The same shape checks then judge the same paths in-repo.
B = dict(agent_id="bld1", agent_type="builder", cwd=GITWT)
# audit-high (owner ruling 2026-10-13): product code is product code IN a repository. The cases
# below used to run in NOGIT, which is a temp folder in no repository, so their refusals pinned the
# outside-repo defect. Run in a real checkout, the same refusals hold on either reading of that rule.
A = dict(agent_id="auth1", agent_type="test-author", cwd=GITMAIN)

# ---- the early warning, by path (write tools)
for _tool, _field in (("Edit", "file_path"), ("Write", "file_path"), ("MultiEdit", "file_path"),
                      ("NotebookEdit", "notebook_path")):
    add("builder-test: %s of a test file is refused" % _tool, "deny", rule=BT, tool=_tool,
        carries=("test-author", "Report"), **{_field: "src/test_app.py"}, **B)
add("builder-test: the refusal routes a test-file merge conflict", "deny", rule=BT, tool="Edit",
    file_path="src/test_app.py", carries=("merge conflict", "test-author"), **B)
for _path in ("src/app_test.py", "pkg/app_test.go", "web/a.test.ts", "web/a.test.jsx",
              "web/a.spec.js", "tests/helper.py", "pkg/__tests__/x.js", "spec/models/user.rb",
              "src/tests/data/fixture.json", "test/x.txt", "src/conftest.py"):
    add("builder-test: Edit of %s is refused" % _path, "deny", rule=BT, tool="Edit",
        file_path=_path, new_string="x = 1", **B)
add("builder-test: addopts --deselect added to pytest.ini is refused", "deny", rule=BT,
    tool="Edit", file_path="pytest.ini", new_string="addopts = --deselect a::b", **B)
add("builder-test: a dependency added to pyproject.toml is allowed", "allow", tool="Edit",
    file_path="pyproject.toml", new_string='dependencies = ["requests"]', **B)
for _path in ("src/app.py", "src/contest.py", "latest_results.md", "docs/attest.md",
              "src/protest_handler.ts", "src/specs.md", "src/testing.py", "src/Contest.java"):
    add("builder-test: Edit of %s is allowed" % _path, "allow", tool="Edit", file_path=_path,
        new_string="x = 1", **B)
# The `testing` folder is a test folder at any depth and in any case, and it holds the shared fixtures,
# so a builder may not write there. A name that only contains `testing` (src/testing.py above) stays product code.
for _tool in ("Write", "Edit"):
    add("builder-test: %s of testing/x.py is refused" % _tool, "deny", rule=BT, tool=_tool,
        file_path="testing/x.py", carries=("test-author", "Report"), **B)
add("builder-test: Read of a test is allowed", "allow", tool="Read", file_path="tests/x.py", **B)
# refusal-vs-rule (builder-test-edit): a builder may write outside every repository (its own scratchpad,
# beside PRIVREPO) and a doc in a `spec` folder. A `spec` folder holds code too, so code there still
# refuses, and so does a guard test in either checkout.
PROBE = os.path.join(ROOT, FAKE_SESSION, "scratchpad", "test_probe.py")
add("builder-test: Write of a probe in its own scratchpad, outside every repository, is allowed",
    "allow", tool="Write", file_path=PROBE, **B)
add("builder-test: Write of a doc in a spec folder is allowed", "allow", tool="Write",
    file_path=os.path.join(GITWT, "docs", "spec", "api.md"), **B)
add("builder-test: Write of the guard's test file in its own worktree is refused", "deny", rule=BT,
    tool="Write", file_path=os.path.join(GITWT, "hooks", "test_guard.py"), **B)
# Rule 0, other-checkout, refuses this write before the builder rule runs. The pin names that rule.
add("builder-test: Write of the guard's test file in the main checkout, from a worktree, is refused",
    "deny", rule="other-checkout", tool="Write", file_path=os.path.join(GITMAIN, "hooks", "test_guard.py"),
    **B)
add("builder-test: Write of code in a spec folder is refused", "deny", rule=BT, tool="Write",
    file_path=os.path.join(GITWT, "spec", "foo_spec.rb"), **B)
add("builder-test: Write of a spec-named TypeScript file is refused", "deny", rule=BT, tool="Write",
    file_path=os.path.join(GITWT, "src", "x.spec.ts"), **B)
add("builder-test: a repo that lives under a tests folder is not all test files", "allow",
    tool="Edit", file_path=os.path.join(UNDERTESTS, "src", "app.py"), **B)
add("builder-test: a test inside that repo is still refused", "deny", rule=BT, tool="Edit",
    file_path=os.path.join(UNDERTESTS, "src", "test_app.py"), **B)
add("builder-test: main session may edit a test", "allow", tool="Edit",
    file_path="src/test_app.py", cwd=NOGIT)
add("builder-test: reviewer may edit a test", "allow", tool="Edit", file_path="src/test_app.py",
    agent_id="rev1", agent_type="reviewer", cwd=NOGIT)
add("builder-test: a session run with --agent builder (no agent_id) is not judged", "allow",
    tool="Edit", file_path="src/test_app.py", agent_type="builder", cwd=NOGIT)
# A builder call in no repository has no diff to read, so the path's shape alone decides it: a test file
# is refused, as it is in a checkout.
add("builder-test: a builder Write of a test file from no repository is refused by shape", "deny",
    rule=BT, tool="Write", file_path="src/test_app.py", carries=("test-author", "Report"),
    agent_id="bld1", agent_type="builder", cwd=NOGIT)
# THE JOIN WITH AN UNKNOWN HEAD. A builder's script joins a folder it cannot read (a temp folder from
# tempfile.mkdtemp(), which is in no repository) to test-looking pieces. The unknown head drops out of the
# join, so the pieces read as a repo test path: a false alarm. A join that resolves to the working folder
# or to a relative folder is a repo test path, and still refuses.
sh("builder join: a temp folder from mkdtemp joined to tests is allowed",
   "python3 - <<'EOF'\nimport os, tempfile\ntmpdir = tempfile.mkdtemp()\n"
   "open(os.path.join(tmpdir, 'tests', 'test_x.py'), 'w').write('x')\nEOF", "allow", **B)
sh("builder join: a temp folder from mkdtemp in python -c joined to tests is allowed",
   "python3 -c \"import os, tempfile; t = tempfile.mkdtemp(); "
   "open(os.path.join(t, 'tests', 'test_x.py'), 'w').write('x')\"", "allow", **B)
sh("builder join: a literal folder outside the repository joined to tests is allowed",
   "python3 - <<'EOF'\nimport os\nopen(os.path.join('/tmp/elsewhere', 'tests', 'test_x.py'), 'w').write('x')\nEOF",
   "allow", **B)
sh("builder join: a relative folder joined to tests still refuses",
   "python3 - <<'EOF'\nimport os\nopen(os.path.join('tests', 'test_x.py'), 'w').write('x')\nEOF",
   "deny", rule=BT, **B)
sh("builder join: a relative folder held in a variable and joined to tests still refuses",
   "python3 - <<'EOF'\nimport os\nrepo = '.'\nopen(os.path.join(repo, 'tests', 'test_x.py'), 'w').write('x')\nEOF",
   "deny", rule=BT, **B)
sh("builder join: the working folder from Path.cwd() joined to tests still refuses",
   "python3 - <<'EOF'\nfrom pathlib import Path\n(Path.cwd() / 'tests' / 'test_x.py').write_text('x')\nEOF",
   "deny", rule=BT, **B)
sh("builder join: the working folder from os.getcwd() joined to tests still refuses",
   "python3 - <<'EOF'\nimport os\nopen(os.path.join(os.getcwd(), 'tests', 'test_x.py'), 'w').write('x')\nEOF",
   "deny", rule=BT, **B)
# THE HEAD OF A JOIN IN python -c. An unknown head drops out of the join, so only a head from a temp source
# (tempfile.mkdtemp, mkstemp, gettempdir, TemporaryDirectory) is safe. A head the script takes from
# sys.argv, from subprocess output, from Path(__file__) or from os.path.dirname() names a folder in the repo,
# so the join to hooks/test_x.py still refuses.
sh("builder join: a repo head from sys.argv[1] joined to hooks in python -c still refuses",
   '''python3 -c "import os, sys; repo = sys.argv[1]; open(os.path.join(repo, 'hooks', 'test_x.py'), 'w').write('x')" .''',
   "deny", rule=BT, **B)
sh("builder join: a repo head from subprocess output joined to hooks in python -c still refuses",
   '''python3 -c "import os, subprocess; repo = subprocess.check_output(['git', 'rev-parse', '--show-toplevel']).decode().strip(); open(os.path.join(repo, 'hooks', 'test_x.py'), 'w').write('x')"''',
   "deny", rule=BT, **B)
sh("builder join: a repo head from Path(__file__).resolve().parents joined to hooks in python -c still refuses",
   '''python3 -c "import os; from pathlib import Path; repo = Path(__file__).resolve().parents[1]; open(os.path.join(repo, 'hooks', 'test_x.py'), 'w').write('x')"''',
   "deny", rule=BT, **B)
sh("builder join: a repo head from os.path.dirname joined to hooks in python -c still refuses",
   '''python3 -c "import os; repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); open(os.path.join(repo, 'hooks', 'test_x.py'), 'w').write('x')"''',
   "deny", rule=BT, **B)
sh("builder join: a temp folder from mkdtemp joined to hooks in python -c is allowed",
   '''python3 -c "import os, tempfile; tmp = tempfile.mkdtemp(); open(os.path.join(tmp, 'hooks', 'test_x.py'), 'w').write('x')"''',
   "allow", **B)
sh("builder join: a temp folder from gettempdir joined to hooks in python -c is allowed",
   '''python3 -c "import os, tempfile; tmp = tempfile.gettempdir(); open(os.path.join(tmp, 'hooks', 'test_x.py'), 'w').write('x')"''',
   "allow", **B)
sh("builder join: a temp folder from mkstemp joined to hooks in python -c is allowed",
   '''python3 -c "import os, tempfile; fd, tmp = tempfile.mkstemp(); os.close(fd); open(os.path.join(tmp, 'hooks', 'test_x.py'), 'w').write('x')"''',
   "allow", **B)
sh("builder join: a temp folder from TemporaryDirectory joined to hooks in python -c is allowed",
   '''python3 -c "import os, tempfile; with tempfile.TemporaryDirectory() as tmp: open(os.path.join(tmp, 'hooks', 'test_x.py'), 'w').write('x')"''',
   "allow", **B)
# THE dir= ARGUMENT OF mkdtemp. `dir='.'` and `dir=os.getcwd()` put the temp folder in the working folder, so a
# join to tests from it is a repo test path and refuses. Only the system temp folder is no repo folder. The inline
# join from the same call refuses too. A bare mkdtemp() inline stays allowed, as its held form does.
sh("builder join: a temp folder from mkdtemp(dir='.') held in a variable, joined to tests still refuses",
   '''python3 -c "import os, tempfile; d = tempfile.mkdtemp(dir='.'); open(os.path.join(d, 'tests', 'test_x.py'), 'w').write('x')"''',
   "deny", rule=BT, **B)
sh("builder join: a temp folder from mkdtemp(dir=os.getcwd()) held in a variable, joined to tests still refuses",
   '''python3 -c "import os, tempfile; d = tempfile.mkdtemp(dir=os.getcwd()); open(os.path.join(d, 'tests', 'test_x.py'), 'w').write('x')"''',
   "deny", rule=BT, **B)
sh("builder join: a temp folder from mkdtemp(dir='.') joined inline to tests still refuses",
   '''python3 -c "import os, tempfile; open(os.path.join(tempfile.mkdtemp(dir='.'), 'tests', 'test_x.py'), 'w').write('x')"''',
   "deny", rule=BT, **B)
sh("builder join: a temp folder from mkdtemp() joined inline to tests is allowed",
   '''python3 -c "import os, tempfile; open(os.path.join(tempfile.mkdtemp(), 'tests', 'test_x.py'), 'w').write('x')"''',
   "allow", **B)
# A TemporaryDirectory held in a variable and joined through its .name is still a system temp folder: allowed.
sh("builder join: a TemporaryDirectory held in a variable, joined through .name to tests is allowed",
   '''python3 -c "import os, tempfile; td = tempfile.TemporaryDirectory(); open(os.path.join(td.name, 'tests', 'test_x.py'), 'w')"''',
   "allow", **B)

# gh-comment-body. A quoted `>` in the body of a gh comment or review is text, not a redirect. Main's builder
# rule reads it as a redirect onto a test file, so each form reds. The controls: a path no test covers is
# allowed, and a redirect onto a test file that runs in the body is still refused.
for _gh_lead, _gh_label in (("gh pr comment 1", "gh pr comment"), ("gh issue comment 1", "gh issue comment"),
                            ("gh pr review 1 --comment", "gh pr review")):
    for _gh_flag, _gh_form in (("--body", '--body "a > %s"'), ("-b", '-b "a > %s"'),
                               ("glued --body=", '--body="a > %s"')):
        sh("builder-test: gh-comment-body, %s with a %s quoted > onto a test file, allows [gh-comment-body red]"
           % (_gh_label, _gh_flag), _gh_lead + " " + _gh_form % "src/test_app.py", "allow", **B)
sh("builder-test: gh-comment-body, a gh pr comment body with a quoted > onto a non-test path, allows [gh-comment-body control]",
   'gh pr comment 1 --body "a > src/x"', "allow", **B)
sh("builder-test: gh-comment-body, a redirect onto a test file from a gh pr comment body, denies [gh-comment-body control]",
   "gh pr comment 1 --body hi > src/test_app.py", "deny", rule=BT, **B)
sh("builder-test: gh-comment-body, a gh pr comment redirect inside bash -c onto a test file, denies [gh-comment-body control]",
   "bash -c \"gh pr comment 1 --body hi > src/test_app.py\"", "deny", rule=BT, **B)
sh("builder-test: gh-comment-body, a gh pr comment body that is only a $(echo) redirect onto a test file, denies [gh-comment-body control]",
   "gh pr comment 1 --body \"$(echo hi > src/test_app.py)\"", "deny", rule=BT, **B)

# ---- a script file a builder runs by name (debt script-file-runs-test-write)
# A shell call that runs a python or node file by name is judged by the writes that file's body makes,
# as a heredoc body is. Each script name says nothing about its body: probe.py writes a test path,
# reads_test.py only reads one. SCRIPTREPO is one real checkout that holds every script the cases run.
SCRIPTREPO = os.path.join(ROOT, "scriptrepo")
SCRIPTFRESH = os.path.join(SCRIPTREPO, "fresh")   # empty, so no probe.py sits beside the heredoc case
# A linked worktree of SCRIPTREPO, nested as the harness nests a lane. `..` from its root is the primary's
# .claude/worktrees folder, inside the primary checkout: a write there is a write into another checkout.
SCRIPTWT = os.path.join(SCRIPTREPO, ".claude", "worktrees", "scriptlane")
SB = dict(B, cwd=SCRIPTREPO)   # a builder, run in SCRIPTREPO
SA = dict(A, cwd=SCRIPTREPO)   # a test-author, run in SCRIPTREPO


# A script over guard_frozen's read limit (_SCRIPT_READ_LIMIT, 256 KB). The string runs past the limit, so the
# cut falls inside it and the read is no parseable python. Anything written before the cut is still read.
OVER_LIMIT_PAD = "PAD = '" + "x" * (300 * 1024) + "'\n"


def _build_scriptrepo():
    """SCRIPTREPO: the scripts the script-file cases run, committed in one real checkout."""
    make_repo(SCRIPTREPO, {
        "probe.py": "open('tests/test_x.py', 'w').write('x')\n",
        "probe.js": "const fs = require('fs');\nfs.writeFileSync('tests/test_x.js', 'x');\n",
        "tools/probe_abs.py": "open('tests/test_x.py', 'w').write('x')\n",
        "sub/probe_cd.py": "open('tests/test_x.py', 'w').write('x')\n",
        "tools/reads_test.py": "import tests.helper\nprint(open('tests/test_x.py').read())\n",
        "tools/names_test.py": "print('tests/test_x.py is named here, and not written')\n",
        "tools/writes_doc.py": "open('docs/out.md', 'w').write('x')\n",
        "scan/slash.js": "const fs = require('fs');\nconst u = '//host'; fs.writeFileSync('tests/test_x.js', 'x');\n",
        "scan/block.js": "const fs = require('fs');\nconst g = '/*'; fs.writeFileSync('tests/test_x.js', 'x');\n",
        "scan/quote.py": "print(\"Don't stop\")\nopen('tests/test_x.py', 'w').write('x')\n",
        "probe_dir.py/notes.txt": "a folder named like a script\n",
        # __file__ and __dirname bind to the script's own folder, so `..` from tools/ is the repo itself.
        "tools/regen.py": "import os\nopen(os.path.join(os.path.dirname(__file__), '..', 'tests', 'golden.json'),\n"
                          "     'w').write('{}')\n",
        "tools/gen.js": "const fs = require('fs');\nconst path = require('path');\n"
                        "fs.writeFileSync(path.join(__dirname, '..', 'tests', 'x.js'), 'x');\n",
        "tools/build.py": "import os\nopen(os.path.join(os.path.dirname(__file__), '..', 'dist', 'out.txt'),\n"
                          "     'w').write('x')\n",
        # Over the read limit. The first 256 KB hold a test-path literal beside a write to dist/.
        "tools/big_dist_write.py": "MARK = 'tests/test_x.py'\nout = 'dist/o.txt'\nopen(out, 'w').write(MARK)\n"
                                   + OVER_LIMIT_PAD,
        # Over the read limit, with the test write first: it lies within the first 256 KB, so it still counts.
        "tools/big_early_test.py": "open('tests/test_x.py', 'w').write('x')\n" + OVER_LIMIT_PAD,
        # A temp folder the script made, or os.tmpdir(), reached through a name or a join.
        "tools/gen_tmp_dir.js": "const fs = require('fs');\nconst os = require('os');\nconst path = require('path');\n"
                                "const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'x-'));\n"
                                "fs.writeFileSync(path.join(dir, 'a.test.js'), 'x');\n",
        "tools/gen_tmp_var.js": "const fs = require('fs');\nconst os = require('os');\nconst path = require('path');\n"
                                "const tmp = os.tmpdir();\nfs.writeFileSync(path.join(tmp, 'a.test.js'), 'x');\n",
        "tools/gen_tmp_tests.js": "const fs = require('fs');\nconst os = require('os');\nconst path = require('path');\n"
                                  "const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'x-'));\n"
                                  "fs.writeFileSync(path.join(dir, 'tests', 'a.js'), 'x');\n",
        # A repo-relative write into tests/: no temp folder, so it stays a test write.
        "tools/gen_rel_tests.js": "const fs = require('fs');\nconst path = require('path');\n"
                                  "fs.writeFileSync(path.join('tests', 'a.test.js'), 'x');\n",
    })
    run_vcs(SCRIPTREPO, "worktree", "add", "-q", SCRIPTWT, "-b", "scriptlane")
    os.makedirs(SCRIPTFRESH, exist_ok=True)
    # The scope before the subject: a case expects these to be there, or to be absent.
    if (os.listdir(SCRIPTFRESH) or os.path.exists(os.path.join(SCRIPTREPO, "tools", "missing.py"))
            or not os.path.isfile(os.path.join(SCRIPTREPO, "probe.py"))
            or not os.path.isdir(os.path.join(SCRIPTREPO, "probe_dir.py"))
            or not os.path.isfile(os.path.join(SCRIPTWT, "tools", "build.py"))
            # The over-limit cases need a script past the read limit, or they test nothing.
            or os.path.getsize(os.path.join(SCRIPTREPO, "tools", "big_dist_write.py")) <= 256 * 1024
            or os.path.getsize(os.path.join(SCRIPTREPO, "tools", "big_early_test.py")) <= 256 * 1024):
        sys.exit("fixture setup failed in _build_scriptrepo: %r lacks the scripts the cases name"
                 % SCRIPTREPO)


lazy_fixture([SCRIPTREPO, SCRIPTWT], _build_scriptrepo)

# RED: the write is in the script's body, and the shell call runs that body by name, by path, after a cd,
# or with a heredoc that writes it in the same command. Each must be refused as a heredoc body is.
sh("builder script file: a python file made beforehand, writing a test path, run by name, is refused",
   "python3 probe.py", "deny", rule=BT, **SB)
sh("builder script file: the same python file run by its absolute path is refused",
   "python3 " + slash(os.path.join(SCRIPTREPO, "tools", "probe_abs.py")), "deny", rule=BT, **SB)
sh("builder script file: a node file that writes a test path with fs.writeFileSync, run by name, is refused",
   "node probe.js", "deny", rule=BT, **SB)
sh("builder script file: a heredoc that writes a script and runs it in one command is refused",
   "cat > probe.py <<'EOF'\nopen('tests/test_x.py', 'w').write('x')\nEOF\npython3 probe.py", "deny",
   rule=BT, **dict(SB, cwd=SCRIPTFRESH))
sh("builder script file: a script run after a cd in the same command is refused",
   "cd sub && python3 probe_cd.py", "deny", rule=BT, **SB)
# RED, scanner: the body is read as source text, so a comment opener or a lone quote inside a string
# must not hide a write that follows it.
sh("builder script file: a // inside a string in a node file does not hide the test write after it",
   "node scan/slash.js", "deny", rule=BT, **SB)
sh("builder script file: a /* inside a string in a node file does not hide the test write after it",
   "node scan/block.js", "deny", rule=BT, **SB)
sh("builder script file: a lone quote in a string in a python file does not hide the test write after it",
   "python3 scan/quote.py", "deny", rule=BT, **SB)
# GREEN: a script that only reads a test path, names one in a string, or writes outside the tests stays
# allowed; so does a test-author's run, a script path that is no file, and a run that is only named.
sh("builder script file: a script that only reads a test path is allowed",
   "python3 tools/reads_test.py", "allow", **SB)
sh("builder script file: a script that names a test path only in a string it prints is allowed",
   "python3 tools/names_test.py", "allow", **SB)
sh("builder script file: a script that writes a non-test path is allowed",
   "python3 tools/writes_doc.py", "allow", **SB)
sh("builder script file: a test-author running the script that writes a test path is allowed",
   "python3 probe.py", "allow", **SA)
sh("builder script file: a script path that does not exist is allowed, as today",
   "python3 tools/missing.py", "allow", **SB)
sh("builder script file: a script path that is a folder, not a readable file, is allowed",
   "python3 probe_dir.py", "allow", **SB)
sh("builder script file: a run named in a double-quoted echo is allowed",
   'echo "python3 probe.py"', "allow", **SB)
sh("builder script file: a run named in a trailing # comment is allowed",
   "ls  # python3 probe.py", "allow", **SB)
sh("builder script file: a run named in a double-quoted string with an apostrophe is allowed",
   "echo \"don't run python3 probe.py\"", "allow", **SB)

# RED, a heredoc that adds to a script file: the file's own body on disk is judged, and each body the
# command writes to it is judged, not the first one only. A heredoc body never hides the file it adds to.
sh("builder script file: a heredoc that appends to a script whose own body writes a test path, then runs it, is refused",
   "cat >> probe.py <<'EOF'\nprint(1)\nEOF\npython3 probe.py", "deny", rule=BT, **SB)
sh("builder script file: a tee -a heredoc that appends to a script whose own body writes a test path, is refused",
   "tee -a probe.py <<'EOF'\nprint(1)\nEOF\npython3 probe.py", "deny", rule=BT, **SB)
sh("builder script file: two heredocs to one script, the second body writing a test path, then a run, is refused",
   "cat > d.py <<'EOF'\nprint(1)\nEOF\ncat >> d.py <<'EOF'\nopen('tests/test_x.py', 'w').write('x')\nEOF\n"
   "python3 d.py", "deny", rule=BT, **dict(SB, cwd=SCRIPTFRESH))
# RED, the script's own folder: __file__ and __dirname are the folder of tools/, so `..` climbs to the repo
# and its tests folder. Each write lands in a test path, and must be refused.
sh("builder script file: a python script writing os.path.join(dirname(__file__), '..', 'tests') is refused",
   "python3 tools/regen.py", "deny", rule=BT, **SB)
sh("builder script file: a node script writing path.join(__dirname, '..', 'tests') is refused",
   "node tools/gen.js", "deny", rule=BT, **SB)
# GREEN, any role: a script run from a linked worktree that writes dist/ by __file__ lands in that same
# checkout, so it is no write into another checkout and no test path. A test-author's run is allowed too.
sh("builder script file: a script run from a worktree, writing dist by __file__ in that checkout, is allowed",
   "python3 tools/build.py", "allow", **dict(B, cwd=SCRIPTWT))
sh("builder script file: a test-author running the same worktree script, writing dist, is allowed",
   "python3 tools/build.py", "allow", **dict(A, cwd=SCRIPTWT))

# RED, a script over the read limit. The cut falls inside OVER_LIMIT_PAD, so the read is no parseable python, and
# the fallback counts a test-path literal beside a write call. The write goes to dist/, so it is allowed.
sh("builder script file: a python script over 256 KB writing dist/o.txt, with a test path literal before the cut, is allowed",
   "python3 tools/big_dist_write.py", "allow", **SB)
# GREEN pair: the same over-limit script, with its test write inside the first 256 KB, stays refused.
sh("builder script file: a python script over 256 KB whose test write is within the first 256 KB is refused",
   "python3 tools/big_early_test.py", "deny", rule=BT, **SB)
# RED, a node script that writes under a temp folder it made. The join's head is a name bound to fs.mkdtempSync or
# os.tmpdir(), which the scan does not follow, so the bare test name is judged as a repo path.
sh("builder script file: a node script writing a.test.js under a folder from mkdtemp(os.tmpdir()) is allowed",
   "node tools/gen_tmp_dir.js", "allow", **SB)
sh("builder script file: a node script writing a.test.js under os.tmpdir() held in a variable is allowed",
   "node tools/gen_tmp_var.js", "allow", **SB)
sh("builder script file: a node script writing tests/a.js under a folder from mkdtemp(os.tmpdir()) is allowed",
   "node tools/gen_tmp_tests.js", "allow", **SB)
# GREEN, the node counterpart: a write into tests/ with no temp folder is refused. The __dirname form of the same
# write is the tools/gen.js case above.
sh("builder script file: a node script writing tests/a.test.js by a repo-relative path.join is refused",
   "node tools/gen_rel_tests.js", "deny", rule=BT, **SB)

add("test-author: Edit of product code is refused", "deny", rule=TA, tool="Edit",
    file_path="src/app.py", carries=("builder", "Report"), **A)
add("builder-test: a ruff --ignore script added to package.json is allowed", "allow", tool="Edit",
    file_path="package.json", new_string='"lint": "ruff check --ignore E501"', **B)
add("builder-test: a flake8 --ignore line added to setup.cfg is allowed", "allow", tool="Edit",
    file_path="setup.cfg", new_string="commands = flake8 --ignore=E203", **B)
add("builder-test: ignore-scripts added to package.json is allowed", "allow", tool="Edit",
    file_path="package.json", new_string='"ci": "npm ci --ignore-scripts"', **B)
add("test-author: Edit of package.json passes the early warning (the diff judges it)", "allow",
    tool="Edit", file_path="package.json", **A)
for _path in ("tests/test_a.py", "src/b_test.go", "pytest.ini", "pyproject.toml", "conftest.py",
              "jest.config.js"):
    add("test-author: Edit of %s is allowed" % _path, "allow", tool="Edit", file_path=_path, **A)
# The `testing` folder is a test folder for a test-author too, at any depth and in any case. A name that only
# contains `testing` (testing_utils/, src/testing.py) is no test folder, so it stays refused.
add("test-author: Write of testing/shallow_clone.py is allowed", "allow", tool="Write",
    file_path="testing/shallow_clone.py", **A)
add("test-author: Write of lib/testing/x.py is allowed", "allow", tool="Write",
    file_path="lib/testing/x.py", **A)
add("test-author: Write of Testing/x.py is allowed (case folds)", "allow", tool="Write",
    file_path="Testing/x.py", **A)
for _path in ("hooks/guard.py", "merge/merge.py", "testing_utils/x.py", "src/testing.py"):
    add("test-author: Write of %s is refused" % _path, "deny", rule=TA, tool="Write",
        file_path=_path, carries=("builder", "Report"), **A)
# Accepted cost, not a bug. Ruling: coordinator 02:47 CST Nov 8, option A, any depth like test/ and spec/.
add("test-author: Write of numpy/testing/_private/utils.py is allowed", "allow", tool="Write",
    file_path="numpy/testing/_private/utils.py", **A)
add("builder-test: Write of numpy/testing/x.py is refused", "deny", rule=BT, tool="Write",
    file_path="numpy/testing/x.py", carries=("test-author", "Report"), **B)
# ---- mutation tests are test code: hooks/mutate_*.py holds the mutants the guard suite is judged
# by, so a test-author edits them and a builder never does.
for _path in ("hooks/mutate_guard.py", "hooks/mutate_shared.py", "janitor/mutate_sweep.py"):
    add("test-author: Edit of mutation test %s is allowed" % _path, "allow", tool="Edit",
        file_path=_path, **A)
    add("test-author: Write of mutation test %s is allowed" % _path, "allow", tool="Write",
        file_path=_path, **A)
    add("builder-test: Edit of mutation test %s is refused" % _path, "deny", rule=BT, tool="Edit",
        file_path=_path, carries=("test-author", "Report"), **B)
    add("builder-test: Write of mutation test %s is refused" % _path, "deny", rule=BT, tool="Write",
        file_path=_path, carries=("test-author", "Report"), **B)
    add("builder-test: MultiEdit of mutation test %s is refused" % _path, "deny", rule=BT,
        tool="MultiEdit", file_path=_path, edits=[{"old_string": "x = 1", "new_string": "x = 2"}],
        carries=("test-author", "Report"), **B)
add("test-author: Edit of hooks/guard_core.py is refused", "deny", rule=TA, tool="Edit",
    file_path="hooks/guard_core.py", carries=("builder", "Report"), **A)
# The same refusal holds in the main checkout: a builder's Edit of a mutation test is refused there too.
add("builder-test: Edit of hooks/mutate_guard.py is refused", "deny", rule=BT, tool="Edit",
    file_path="hooks/mutate_guard.py", carries=("test-author", "Report"),
    agent_id="bld1", agent_type="builder", cwd=GITMAIN)
# A test-support helper goes flat, beside its tests, named _test_<name>.py (coordinator ruling, 03:58 CST, decision
# builders-cannot-edit-tests). The underscore name is no test path (TEST_BASENAME reads test_*.py), so a builder
# writes it and a test-author may not. The plain test_<name>.py form stays a test path, as the control.
for _tool in ("Edit", "Write"):
    add("builder-test: %s of hooks/_test_cost_probe.py is allowed" % _tool, "allow", tool=_tool,
        file_path="hooks/_test_cost_probe.py", **B)
    add("test-author: %s of hooks/_test_cost_probe.py is refused" % _tool, "deny", rule=TA, tool=_tool,
        file_path="hooks/_test_cost_probe.py", carries=("builder", "Report"), **A)
    add("test-author: %s of hooks/test_cost_probe.py is allowed (control)" % _tool, "allow", tool=_tool,
        file_path="hooks/test_cost_probe.py", **A)
    add("builder-test: %s of hooks/test_cost_probe.py is refused (control)" % _tool, "deny", rule=BT, tool=_tool,
        file_path="hooks/test_cost_probe.py", carries=("test-author", "Report"), **B)
# The near misses stay a builder's product code: a later mutate_*.py is not a mutation test. A listed
# name in another case is the same file on Windows, so it is refused for a builder too.
add("builder-test: Edit of hooks/mutate_x.py is allowed", "allow", tool="Edit",
    file_path="hooks/mutate_x.py", **B)
add("builder-test: Write of hooks/mutate_x.py is allowed", "allow", tool="Write",
    file_path="hooks/mutate_x.py", **B)
add("builder-test: Edit of HOOKS/mutate_guard.py is refused (case folds)", "deny", rule=BT, tool="Edit",
    file_path="HOOKS/mutate_guard.py", carries=("test-author", "Report"), **B)
add("builder-test: Write of HOOKS/mutate_guard.py is refused (case folds)", "deny", rule=BT, tool="Write",
    file_path="HOOKS/mutate_guard.py", carries=("test-author", "Report"), **B)
# The mutation test set is a list of exact names, not a shape: a near miss stays product code, a name with
# a colon is not a mutation test, and a name that differs only in case is the same file on Windows.
add("test-author: Edit of hooks/mutate_x.py is refused", "deny", rule=TA, tool="Edit",
    file_path="hooks/mutate_x.py", carries=("builder", "Report"), **A)
add("test-author: Edit of hooks/mutate_:guard_core.py is refused", "deny", rule=TA, tool="Edit",
    file_path="hooks/mutate_:guard_core.py", carries=("builder", "Report"), **A)
add("test-author: Edit of janitor/mutate_sweep.py is allowed", "allow", tool="Edit",
    file_path="janitor/mutate_sweep.py", **A)
add("test-author: Edit of HOOKS/mutate_guard.py is allowed (case folds)", "allow", tool="Edit",
    file_path="HOOKS/mutate_guard.py", **A)

# ---- workflow test-run steps. A test-author may add or remove a whole test-run step in a workflow; nothing else there.
# A builder may change any workflow line, except one that disables tests in a test-runner line. Each author row and
# its builder row share one old and one new text, so the two roles judge the same edit. An Edit is judged by
# old_string against new_string, never by new_string alone.
WF = ".github/workflows/checks.yml"
WF_YAML = ".github/workflows/checks.yaml"
LINT = "      - name: Lint\n        run: python3 lint/ste_lint.py\n"
LINT_RUN_CHANGED = LINT.replace("lint/ste_lint.py", "lint/other_lint.py")
TEST_LINUX = "      - name: Guard tests\n        run: python3 hooks/test_guard.py\n"
TEST_WINDOWS = "      - name: Guard tests (Windows)\n        run: python hooks/test_guard.py\n"
TEST_IF = "      - name: Guard tests\n        if: runner.os == 'Linux'\n        run: python3 hooks/test_guard.py\n"
TEST_APOSTROPHE = "      - name: Don't skip guard tests\n        run: python3 hooks/test_guard.py\n"
CLEAN = "      - name: Clean\n        run: rm -rf build\n"
DESELECT = "      - name: Unit\n        run: python3 -m pytest --deselect a::b\n"
NEW_WORKFLOW = ("on: push\njobs:\n  test:\n    steps:\n      - name: Guard tests\n"
                "        run: python3 hooks/test_guard.py\n")

# Each allow below pins one test step a workflow edit may add. A refusal here points at the path check alone.
for _name, _path, _old, _new in (
    ("a Linux test step inserted after a lint step", WF, LINT, LINT + TEST_LINUX),
    ("a Windows python test step inserted after a lint step", WF, LINT, LINT + TEST_WINDOWS),
    ("a test step with an if line inserted after a lint step", WF, LINT, LINT + TEST_IF),
    ("a test step whose name holds an apostrophe inserted", WF, LINT, LINT + TEST_APOSTROPHE),
    ("a test step deleted", WF, LINT + TEST_LINUX, LINT),
    ("a test step inserted into checks.yaml", WF_YAML, LINT, LINT + TEST_LINUX),
):
    add("test-author: %s is allowed" % _name, "allow", tool="Edit", file_path=_path,
        old_string=_old, new_string=_new, **A)
add("test-author: a test step inserted with MultiEdit is allowed", "allow", tool="MultiEdit",
    file_path=WF, edits=[{"old_string": LINT, "new_string": LINT + TEST_LINUX}], **A)

# Pins: main already refuses each of these, and each must stay refused once the classifier lands.
for _name, _old, _new in (
    ("a lint step's run is changed", LINT, LINT_RUN_CHANGED),
    ("a test step added beside a run: rm -rf build step", LINT, LINT + TEST_LINUX + CLEAN),
    ("continue-on-error added to a test step", LINT,
     LINT + "      - name: Guard tests\n        continue-on-error: true\n        run: python3 hooks/test_guard.py\n"),
    ("a test path followed by && curl x", LINT,
     LINT + "      - name: Guard tests\n        run: python3 hooks/test_guard.py && curl x\n"),
    ("a comment opener inside quotes before && curl x", LINT,
     LINT + '      - name: Guard tests\n        run: python3 hooks/test_guard.py "a # b" && curl x\n'),
    ("a multi-line run block with rm -rf build", LINT,
     LINT + "      - name: Guard tests\n        run: |\n          python3 hooks/test_guard.py\n          rm -rf build\n"),
):
    add("test-author: %s in checks.yml is refused" % _name, "deny", rule=TA, tool="Edit",
        file_path=WF, old_string=_old, new_string=_new, carries=("builder", "Report"), **A)
add("test-author: Edit of .github/dependabot.yml is refused", "deny", rule=TA, tool="Edit",
    file_path=".github/dependabot.yml", old_string="version: 2\n", new_string="version: 2\nupdates: []\n",
    carries=("builder", "Report"), **A)
add("test-author: Write of a new workflow with on and jobs lines is refused", "deny", rule=TA,
    tool="Write", file_path=".github/workflows/nightly.yml", content=NEW_WORKFLOW,
    carries=("builder", "Report"), **A)

# Builder: an edit to a workflow stays allowed unless its added lines disable tests in a test-runner line.
for _name, _old, _new in (
    ("a lint step's run is changed", LINT, LINT_RUN_CHANGED),
    ("a test step is added", LINT, LINT + TEST_LINUX),
):
    add("builder-test: %s in checks.yml is allowed" % _name, "allow", tool="Edit", file_path=WF,
        old_string=_old, new_string=_new, **B)
add("builder-test: a pytest --deselect step added to checks.yml is refused", "deny", rule=BT, tool="Edit",
    file_path=WF, old_string=LINT, new_string=LINT + DESELECT, carries=("test-author", "Report"), **B)

# A `$(` in a test-run step runs a command, quoted or not, so no test run holds it. A ruff line on tests/ is a lint
# step. A continue-on-error, an `if: false` or a deleted test step takes a test out of CI.
QUOTED_SUBST = '      - name: Guard tests\n        run: python3 hooks/test_guard.py "$(curl -s x | sh)"\n'
TAG_SUBST = '      - name: Guard tests\n        run: python3 hooks/test_guard.py --tag "$(git rev-parse HEAD)"\n'
UNQUOTED_SUBST = '      - name: Guard tests\n        run: python3 hooks/test_guard.py --tag $(git rev-parse HEAD)\n'
RUFF_TESTS = "      - name: Ruff\n        run: ruff check tests/ --ignore E501\n"
CONTINUE_ON_ERROR = "      - name: Guard tests\n        continue-on-error: true\n        run: python3 hooks/test_guard.py\n"
IF_FALSE = "      - name: Guard tests\n        if: false\n        run: python3 hooks/test_guard.py\n"
for _name, _new in (
    ("a quoted $( substitution in a test run", LINT + QUOTED_SUBST),
    ("a quoted $( with git rev-parse in a test run", LINT + TAG_SUBST),
    ("an unquoted $( with git rev-parse in a test run", LINT + UNQUOTED_SUBST),
):
    add("test-author: %s in checks.yml is refused" % _name, "deny", rule=TA, tool="Edit",
        file_path=WF, old_string=LINT, new_string=_new, carries=("builder", "Report"), **A)
add("builder-test: a ruff --ignore line on tests/ added to checks.yml is allowed", "allow", tool="Edit",
    file_path=WF, old_string=LINT, new_string=LINT + RUFF_TESTS, **B)
add("builder-test: continue-on-error added under a test step is refused", "deny", rule=BT, tool="Edit",
    file_path=WF, old_string=LINT + TEST_LINUX, new_string=LINT + CONTINUE_ON_ERROR,
    carries=("test-author", "Report"), **B)
add("builder-test: if: false added under a test step is refused", "deny", rule=BT, tool="Edit",
    file_path=WF, old_string=LINT + TEST_LINUX, new_string=LINT + IF_FALSE,
    carries=("test-author", "Report"), **B)
# A mutation test is a test run too: a disabled mutate step reads green while its mutants go unrun. Its file is
# named in AUTHOR_MUTATION_TESTS, not a test_ name, so the step check must count that list. The controls keep a
# non-test script, a near-miss hooks/mutate_x.py and a timeout change on the mutate step allowed.
MUTATE_GUARD = ("      - name: Guard mutation test\n        run: python3 hooks/mutate_guard.py\n"
                "        timeout-minutes: 25\n")
MUTATE_GUARD_CONTINUE = ("      - name: Guard mutation test\n        continue-on-error: true\n"
                         "        run: python3 hooks/mutate_guard.py\n        timeout-minutes: 25\n")
MUTATE_GUARD_IF_FALSE = ("      - name: Guard mutation test\n        if: false\n"
                         "        run: python3 hooks/mutate_guard.py\n        timeout-minutes: 25\n")
MUTATE_GUARD_TIMEOUT = MUTATE_GUARD.replace("minutes: 25", "minutes: 30")
MUTATE_SWEEP = "      - name: Mutate sweep\n        run: python3 janitor/mutate_sweep.py\n"
MUTATE_SWEEP_CONTINUE = ("      - name: Mutate sweep\n        continue-on-error: true\n"
                         "        run: python3 janitor/mutate_sweep.py\n")
SOME_TOOL = "      - name: Some tool\n        run: python3 hooks/some_tool.py\n"
SOME_TOOL_CONTINUE = ("      - name: Some tool\n        continue-on-error: true\n"
                      "        run: python3 hooks/some_tool.py\n")
MUTATE_X = "      - name: Mutate tool\n        run: python3 hooks/mutate_x.py\n"
MUTATE_X_CONTINUE = ("      - name: Mutate tool\n        continue-on-error: true\n"
                     "        run: python3 hooks/mutate_x.py\n")
add("builder-test: continue-on-error added under the mutate_guard step is refused", "deny", rule=BT, tool="Edit",
    file_path=WF, old_string=LINT + MUTATE_GUARD, new_string=LINT + MUTATE_GUARD_CONTINUE,
    carries=("test-author", "Report"), **B)
add("builder-test: continue-on-error added under the mutate_sweep step is refused", "deny", rule=BT, tool="Edit",
    file_path=WF, old_string=LINT + MUTATE_SWEEP, new_string=LINT + MUTATE_SWEEP_CONTINUE,
    carries=("test-author", "Report"), **B)
add("builder-test: if: false added under the mutate_guard step is refused", "deny", rule=BT, tool="Edit",
    file_path=WF, old_string=LINT + MUTATE_GUARD, new_string=LINT + MUTATE_GUARD_IF_FALSE,
    carries=("test-author", "Report"), **B)
add("builder-test: continue-on-error added to a step running hooks/some_tool.py is allowed", "allow", tool="Edit",
    file_path=WF, old_string=LINT + SOME_TOOL, new_string=LINT + SOME_TOOL_CONTINUE, **B)
add("builder-test: continue-on-error added to a step running hooks/mutate_x.py is allowed", "allow", tool="Edit",
    file_path=WF, old_string=LINT + MUTATE_X, new_string=LINT + MUTATE_X_CONTINUE, **B)
add("builder-test: a timeout change on the mutate_guard step is allowed", "allow", tool="Edit",
    file_path=WF, old_string=LINT + MUTATE_GUARD, new_string=LINT + MUTATE_GUARD_TIMEOUT, **B)
# A YAML comment after a disable value still disables the step, so the disable line must be read without its comment.
# A lone apostrophe in that comment must not stop the reader from finding the `#`: a quote-aware reader that throws on
# it would fall open. The controls keep a comment after a false value, and a quoted `#` on a run line, allowed.
MUTATE_GUARD_CONTINUE_FLAKY = ("      - name: Guard mutation test\n        continue-on-error: true  # flaky\n"
                               "        run: python3 hooks/mutate_guard.py\n        timeout-minutes: 25\n")
MUTATE_GUARD_IF_FALSE_FLAKY = ("      - name: Guard mutation test\n        if: false  # flaky\n"
                               "        run: python3 hooks/mutate_guard.py\n        timeout-minutes: 25\n")
MUTATE_GUARD_CONTINUE_APOSTROPHE = ("      - name: Guard mutation test\n        continue-on-error: true  # don't\n"
                                    "        run: python3 hooks/mutate_guard.py\n        timeout-minutes: 25\n")
TEST_GUARD_CONTINUE_FLAKY = ("      - name: Guard tests\n        continue-on-error: true  # flaky\n"
                             "        run: python3 hooks/test_guard.py\n")
MUTATE_GUARD_CONTINUE_FALSE = ("      - name: Guard mutation test\n        continue-on-error: false  # never\n"
                               "        run: python3 hooks/mutate_guard.py\n        timeout-minutes: 25\n")
MUTATE_GUARD_QUOTED_HASH = ("      - name: Guard mutation test\n"
                            "        run: echo \"a # b\" && python3 hooks/mutate_guard.py\n        timeout-minutes: 25\n")
add("builder-test: continue-on-error: true with a trailing # flaky comment under the mutate_guard step is refused",
    "deny", rule=BT, tool="Edit", file_path=WF, old_string=LINT + MUTATE_GUARD,
    new_string=LINT + MUTATE_GUARD_CONTINUE_FLAKY, carries=("test-author", "Report"), **B)
add("builder-test: if: false with a trailing # flaky comment under the mutate_guard step is refused", "deny", rule=BT,
    tool="Edit", file_path=WF, old_string=LINT + MUTATE_GUARD, new_string=LINT + MUTATE_GUARD_IF_FALSE_FLAKY,
    carries=("test-author", "Report"), **B)
add("builder-test: continue-on-error: true with a trailing # flaky comment under a test step is refused", "deny",
    rule=BT, tool="Edit", file_path=WF, old_string=LINT + TEST_LINUX, new_string=LINT + TEST_GUARD_CONTINUE_FLAKY,
    carries=("test-author", "Report"), **B)
add("builder-test: continue-on-error: true with a lone apostrophe in its # comment under the mutate_guard step "
    "is refused", "deny", rule=BT, tool="Edit", file_path=WF, old_string=LINT + MUTATE_GUARD,
    new_string=LINT + MUTATE_GUARD_CONTINUE_APOSTROPHE, carries=("test-author", "Report"), **B)
add("builder-test: continue-on-error: false with a trailing # comment under the mutate_guard step is allowed", "allow",
    tool="Edit", file_path=WF, old_string=LINT + MUTATE_GUARD, new_string=LINT + MUTATE_GUARD_CONTINUE_FALSE, **B)
add("builder-test: a quoted # on the mutate_guard run line ahead of the script is allowed", "allow", tool="Edit",
    file_path=WF, old_string=LINT + MUTATE_GUARD, new_string=LINT + MUTATE_GUARD_QUOTED_HASH, **B)
# A mutation test run through `cd hooks &&` or a `working-directory:` line names its script by the bare file name.
# The step check counts that run by the name (the basename against MUTATION_TEST_NAMES) and resolves no folder, so
# a disabled step in either form would read green without that count.
# The pins hold what a test file already keeps: the same forms on a test file are refused, by basename.
TEST_GUARD_CD = "      - name: Guard tests\n        run: cd hooks && python3 test_guard.py\n"
TEST_GUARD_CD_CONTINUE = ("      - name: Guard tests\n        continue-on-error: true\n"
                          "        run: cd hooks && python3 test_guard.py\n")
TEST_GUARD_WD = "      - name: Guard tests\n        working-directory: hooks\n        run: python3 test_guard.py\n"
TEST_GUARD_WD_IF_FALSE = ("      - name: Guard tests\n        if: false\n        working-directory: hooks\n"
                          "        run: python3 test_guard.py\n")
MUTATE_GUARD_CD = "      - name: Guard mutation test\n        run: cd hooks && python3 mutate_guard.py\n"
MUTATE_GUARD_CD_CONTINUE = ("      - name: Guard mutation test\n        continue-on-error: true\n"
                            "        run: cd hooks && python3 mutate_guard.py\n")
MUTATE_GUARD_WD = ("      - name: Guard mutation test\n        working-directory: hooks\n"
                   "        run: python3 mutate_guard.py\n")
MUTATE_GUARD_WD_IF_FALSE = ("      - name: Guard mutation test\n        if: false\n        working-directory: hooks\n"
                            "        run: python3 mutate_guard.py\n")
MUTATE_SWEEP_WD = "      - name: Mutate sweep\n        working-directory: janitor\n        run: python3 mutate_sweep.py\n"
MUTATE_SWEEP_WD_CONTINUE = ("      - name: Mutate sweep\n        continue-on-error: true\n"
                            "        working-directory: janitor\n        run: python3 mutate_sweep.py\n")
MUTATE_X_CD = "      - name: Mutate tool\n        run: cd hooks && python3 mutate_x.py\n"
MUTATE_X_CD_CONTINUE = ("      - name: Mutate tool\n        continue-on-error: true\n"
                        "        run: cd hooks && python3 mutate_x.py\n")
add("builder-test: continue-on-error added under the cd hooks mutate_guard step is refused", "deny", rule=BT,
    tool="Edit", file_path=WF, old_string=LINT + MUTATE_GUARD_CD, new_string=LINT + MUTATE_GUARD_CD_CONTINUE,
    carries=("test-author", "Report"), **B)
add("builder-test: if: false added under the working-directory mutate_guard step is refused", "deny", rule=BT,
    tool="Edit", file_path=WF, old_string=LINT + MUTATE_GUARD_WD, new_string=LINT + MUTATE_GUARD_WD_IF_FALSE,
    carries=("test-author", "Report"), **B)
add("builder-test: continue-on-error added under the working-directory mutate_sweep step is refused", "deny",
    rule=BT, tool="Edit", file_path=WF, old_string=LINT + MUTATE_SWEEP_WD, new_string=LINT + MUTATE_SWEEP_WD_CONTINUE,
    carries=("test-author", "Report"), **B)
add("builder-test: continue-on-error added to a cd hooks mutate_x.py step is allowed", "allow", tool="Edit",
    file_path=WF, old_string=LINT + MUTATE_X_CD, new_string=LINT + MUTATE_X_CD_CONTINUE, **B)
add("builder-test: continue-on-error added under the cd hooks test step is refused", "deny", rule=BT,
    tool="Edit", file_path=WF, old_string=LINT + TEST_GUARD_CD, new_string=LINT + TEST_GUARD_CD_CONTINUE,
    carries=("test-author", "Report"), **B)
add("builder-test: if: false added under the working-directory test step is refused", "deny", rule=BT,
    tool="Edit", file_path=WF, old_string=LINT + TEST_GUARD_WD, new_string=LINT + TEST_GUARD_WD_IF_FALSE,
    carries=("test-author", "Report"), **B)
# A mutation test's whole step is a test run too: deleting it leaves its mutants unrun, so the deletion is refused by
# the file name the step runs. The control deletes an upload step beside the kept mutate step, in the same job.
UPLOAD_REPORT = ("      - name: Upload report\n        uses: actions/upload-artifact@v4\n"
                 "        with:\n          name: report\n          path: out/report.json\n")
add("builder-test: a whole mutate_guard step deleted from checks.yml is refused", "deny", rule=BT, tool="Edit",
    file_path=WF, old_string=LINT + MUTATE_GUARD, new_string=LINT, carries=("test-author", "Report"), **B)
add("builder-test: a whole mutate_sweep step deleted from checks.yml is refused", "deny", rule=BT, tool="Edit",
    file_path=WF, old_string=LINT + MUTATE_SWEEP, new_string=LINT, carries=("test-author", "Report"), **B)
add("builder-test: an upload step deleted beside the mutate_guard step is allowed", "allow", tool="Edit",
    file_path=WF, old_string=LINT + MUTATE_GUARD + UPLOAD_REPORT, new_string=LINT + MUTATE_GUARD, **B)
add("builder-test: a whole test step deleted from checks.yml is refused", "deny", rule=BT, tool="Edit",
    file_path=WF, old_string=LINT + TEST_LINUX, new_string=LINT, carries=("test-author", "Report"), **B)
add("builder-test: a test step moved within checks.yml is allowed", "allow", tool="Edit", file_path=WF,
    old_string=LINT + TEST_LINUX + CLEAN, new_string=LINT + CLEAN + TEST_LINUX, **B)
add("builder-test: a test step's if: changed to another condition is allowed", "allow", tool="Edit",
    file_path=WF, old_string=TEST_IF,
    new_string=TEST_IF.replace("runner.os == 'Linux'", "github.event_name == 'push'"), **B)

# A test run keeps its test when its interpreter flag (-u, -X utf8), its ./ path or its shell flag (bash -x)
# changes, and when its step moves to another job. Removing a test run drops its test, and a flag that
# hides the test path from the run does not change that.
R3_UNIT = "      - name: Unit\n        run: python3 tests/test_a.py\n"
R3_UNIT_U = "      - name: Unit\n        run: python3 -u tests/test_a.py\n"
R3_JOBS_BEFORE = (
    "jobs:\n  lint:\n    steps:\n      - name: Lint\n        run: python3 lint/ste_lint.py\n"
    "  unit:\n    steps:\n      - name: Install\n        run: pip install -r requirements.txt\n"
    "      - name: Guard tests\n        run: python3 hooks/test_guard.py\n")
R3_JOBS_AFTER = (
    "jobs:\n  lint:\n    steps:\n      - name: Lint\n        run: python3 lint/ste_lint.py\n"
    "      - name: Guard tests\n        run: python3 hooks/test_guard.py\n"
    "  unit:\n    steps:\n      - name: Install\n        run: pip install -r requirements.txt\n")
add("builder-test: python3 -u in place of python3 on a test run is allowed", "allow", tool="Edit",
    file_path=WF, old_string=R3_UNIT, new_string=R3_UNIT_U, **B)
add("builder-test: python -X utf8 in place of python3 on a test run is allowed", "allow", tool="Edit",
    file_path=WF, old_string=R3_UNIT,
    new_string="      - name: Unit\n        run: python -X utf8 tests/test_a.py\n", **B)
add("builder-test: a ./ path in place of a test path on a test run is allowed", "allow", tool="Edit",
    file_path=WF, old_string=R3_UNIT,
    new_string="      - name: Unit\n        run: python3 ./tests/test_a.py\n", **B)
add("builder-test: bash -x in place of bash on a test run is allowed", "allow", tool="Edit",
    file_path=WF, old_string="      - name: Unit\n        run: bash tests/run.sh\n",
    new_string="      - name: Unit\n        run: bash -x tests/run.sh\n", **B)
add("builder-test: a test step moved to another job is allowed", "allow", tool="Edit",
    file_path=WF, old_string=R3_JOBS_BEFORE, new_string=R3_JOBS_AFTER, **B)
add("builder-test: a -u test run deleted from checks.yml is refused", "deny", rule=BT, tool="Edit",
    file_path=WF, old_string=LINT + R3_UNIT_U, new_string=LINT, carries=("test-author", "Report"), **B)
add("builder-test: an added run of a test path with --deselect is refused", "deny", rule=BT, tool="Edit",
    file_path=WF, old_string=LINT,
    new_string=LINT + "      - name: X\n        run: python3 hooks/x_test.py --deselect a\n",
    carries=("test-author", "Report"), **B)
# A wrapper runs the test it wraps, so a wrapped run is judged as the bare run it wraps. A builder's wrap of a bare
# run keeps its test, a test-author's wrapped single-line run is a test step, and deleting a wrapped run drops its test.
WRAPPED_RUNS = (
    "timeout 600 python3 tests/test_a.py",
    "xvfb-run -a python3 tests/test_a.py",
    "coverage run tests/test_a.py",
    "uv run tests/test_a.py",
    "env FOO=1 python3 tests/test_a.py",
    "nice python3 tests/test_a.py",
    "python3 -m coverage run tests/test_a.py",
)
for _form in WRAPPED_RUNS:
    add("builder-test: %s in place of a bare test run is allowed" % _form, "allow", tool="Edit", file_path=WF,
        old_string=R3_UNIT, new_string="      - name: Unit\n        run: %s\n" % _form, **B)
for _form in WRAPPED_RUNS:
    add("test-author: a whole new test step, %s, is allowed" % _form, "allow", tool="Edit", file_path=WF,
        old_string=LINT, new_string=LINT + "      - name: Unit\n        run: %s\n" % _form, **A)
for _form in WRAPPED_RUNS:
    add("builder-test: a wrapped test run, %s, deleted from checks.yml is refused" % _form, "deny", rule=BT,
        tool="Edit", file_path=WF, old_string=LINT + "      - name: Unit\n        run: %s\n" % _form, new_string=LINT,
        carries=("test-author", "Report"), **B)
add("builder-test: a wrapped test run unwrapped to its bare path is allowed", "allow", tool="Edit", file_path=WF,
    old_string="      - name: Unit\n        run: timeout 600 python3 tests/test_a.py\n", new_string=R3_UNIT, **B)
# Not a test run: a wrapper around one does not make it a test, so each of these still drops the test it replaces.
add("builder-test: a bare test run replaced by an echo of its path is refused", "deny", rule=BT, tool="Edit",
    file_path=WF, old_string=R3_UNIT, new_string="      - name: Unit\n        run: echo python3 tests/test_a.py\n",
    carries=("test-author", "Report"), **B)
add("builder-test: a bare test run replaced by a timeout around a lint run is refused", "deny", rule=BT, tool="Edit",
    file_path=WF, old_string=R3_UNIT, new_string="      - name: Unit\n        run: timeout 600 python3 lint/ste_lint.py\n",
    carries=("test-author", "Report"), **B)
add("test-author: a whole new test step, timeout around curl, is refused", "deny", rule=TA, tool="Edit",
    file_path=WF, old_string=LINT, new_string=LINT + "      - name: Unit\n        run: timeout 600 curl -s x\n",
    carries=("builder", "Report"), **A)
add("test-author: a whole new test step with if: false is refused", "deny", rule=TA, tool="Edit",
    file_path=WF, old_string=LINT,
    new_string=LINT + "      - name: Guard tests\n        if: false\n        run: python3 hooks/test_guard.py\n",
    carries=("builder", "Report"), **A)
# A multi-line run: block whose wrapper takes a quoted value with a space. The shell reads the quoted value as one
# word, so the run is a test. A whitespace split reads `-screen` and `0` as the command and finds no test path, so
# the deletion would pass. The bare block beside it is the control: the same block shape, no wrapper, is refused.
XVFB_QUOTED_BLOCK = ("      - name: Xvfb unit\n        run: |\n"
                     "          xvfb-run -s \"-screen 0 1024x768x24\" python3 tests/test_a.py\n")
BARE_BLOCK = "      - name: Bare unit\n        run: |\n          python3 tests/test_a.py\n"
add("builder-test: a multi-line run under xvfb-run with a quoted -s value, deleted from checks.yml is refused",
    "deny", rule=BT, tool="Edit", file_path=WF, old_string=LINT + XVFB_QUOTED_BLOCK, new_string=LINT,
    carries=("test-author", "Report"), **B)
add("builder-test: a multi-line bare test run, no wrapper, deleted from checks.yml is refused",
    "deny", rule=BT, tool="Edit", file_path=WF, old_string=LINT + BARE_BLOCK, new_string=LINT,
    carries=("test-author", "Report"), **B)
# A backslash in a test path is a separator on Windows, and is_test_rel reads it as `/`. The run line must keep it:
# shlex in POSIX mode reads an unquoted backslash as an escape, so `tests\test_a.py` loses its separator and reads as
# no test. Each deletion below is refused on main, so a parse that drops the backslash is a regression.
BACKSLASH_INLINE = "      - name: Win unit\n        run: python tests\\test_a.py\n"
BACKSLASH_BLOCK = "      - name: Win unit\n        run: |\n          python tests\\test_a.py\n"
BACKSLASH_NODE = "      - name: Win node\n        run: node tests\\run.js\n"
add("builder-test: a bare python run with a backslash test path, deleted from checks.yml is refused",
    "deny", rule=BT, tool="Edit", file_path=WF, old_string=LINT + BACKSLASH_INLINE, new_string=LINT,
    carries=("test-author", "Report"), **B)
add("builder-test: a multi-line python run with a backslash test path, deleted from checks.yml is refused",
    "deny", rule=BT, tool="Edit", file_path=WF, old_string=LINT + BACKSLASH_BLOCK, new_string=LINT,
    carries=("test-author", "Report"), **B)
add("builder-test: a node run with a backslash test path, deleted from checks.yml is refused",
    "deny", rule=BT, tool="Edit", file_path=WF, old_string=LINT + BACKSLASH_NODE, new_string=LINT,
    carries=("test-author", "Report"), **B)

# bash takes no value after -k or -p, so the test path after either flag is the script: a builder that drops
# that run drops its test.
R3_BASH_K = "      - name: Unit\n        run: bash -k tests/test_a.sh\n"
R3_BASH_P = "      - name: Unit\n        run: bash -p tests/test_a.sh\n"
add("builder-test: a bash -k test run deleted from checks.yml is refused", "deny", rule=BT, tool="Edit",
    file_path=WF, old_string=LINT + R3_BASH_K, new_string=LINT, carries=("test-author", "Report"), **B)
add("builder-test: a bash -p test run deleted from checks.yml is refused", "deny", rule=BT, tool="Edit",
    file_path=WF, old_string=LINT + R3_BASH_P, new_string=LINT, carries=("test-author", "Report"), **B)

# ---- test-path shapes: one table on the builder's early warning. Each row is one path, judged by
# a Write, for one role (the builder). A test shape is refused, a near miss is allowed. Shapes, with
# the incident that named each: self-test files (Banchi, 2026-10-02: `*-selftest.*`, `*_selftest.*`,
# `selftest_*.*` in any folder; a .md is prose); shell and PowerShell suites (2026-10-03: `test_*.sh`,
# `*_test.sh`, `*.test.ps1`, `*.Tests.ps1`); JS/TS test files (2026-10-07: `test_*.js/.mjs/.cjs/.ts/
# .jsx/.tsx`); Xcode/SPM names (Degen, 2026-10-11, decisions/builders-cannot-edit-tests.md, "Test
# path"): a FILE is `^\w+Tests\.swift$` (plural only), a FOLDER is `^[A-Z]\w*Tests$`. A bare
# Tests.swift, LoginTest.swift, SpeedTest.swift, ABTest.swift and abTests are no test path. A folder
# named exactly `Tests` is a test dir through TEST_DIRS, unchanged.
# Row: (prefix, path, expect, shape). A near miss has shape "".
TEST_SHAPE_ROWS = (
    ("builder-test", "scripts/guard-shell-selftest.sh", "deny", "self-test file"),
    ("builder-test", "scripts/docs_audit/selftest_env_map.py", "deny", "self-test file"),
    ("builder-test", "scripts/foo-selftest.py", "deny", "self-test file"),
    ("builder-test", "foo_selftest.py", "deny", "self-test file"),
    ("builder-test", "a/b/c/selftest_x.sh", "deny", "self-test file"),
    ("builder-test", "selftestify.py", "allow", ""),
    ("builder-test", "docs/selftest-notes.md", "allow", ""),
    ("builder-test", "myselftest.py", "allow", ""),
    ("builder-test", "docs/foo-selftest.md", "allow", ""),
    ("builder-test", "docs/selftest_notes.md", "allow", ""),
    ("builder-test", "scripts/selftest", "allow", ""),
    ("builder-test", "hooks/test_install_src.sh", "deny", "shell/ps1 test"),
    ("builder-test", "install.test.ps1", "deny", "shell/ps1 test"),
    ("builder-test", "scripts/foo_test.sh", "deny", "shell/ps1 test"),
    ("builder-test", "scripts/Foo.Tests.ps1", "deny", "shell/ps1 test"),
    ("builder-test", "install.ps1", "allow", ""),
    ("builder-test", "install.sh", "allow", ""),
    ("builder-test", "session_start.sh", "allow", ""),
    ("builder-test", "contest.sh", "allow", ""),
    ("builder-test", "latest.ps1", "allow", ""),
    ("builder-test", "actions/stamp/test_stamp.mjs", "deny", "JS/TS test"),
    ("builder-test", "test_x.js", "deny", "JS/TS test"),
    ("builder-test", "lib/test_x.cjs", "deny", "JS/TS test"),
    ("builder-test", "lib/test_x.ts", "deny", "JS/TS test"),
    ("builder-test", "web/test_x.jsx", "deny", "JS/TS test"),
    ("builder-test", "web/test_x.tsx", "deny", "JS/TS test"),
    ("builder-test", "contest.mjs", "allow", ""),
    ("builder-test", "latest_x.mjs", "allow", ""),
    ("builder-test", "test_notes.md", "allow", ""),
    ("builder-test", "actions/stamp/stamp.mjs", "allow", ""),
    ("swift-test", "native/DegenUITests/NBOpenLinkUITests.swift", "deny", "Xcode/SPM test"),
    ("swift-test", "native/DegenUITests/LaunchTests.swift", "deny", "Xcode/SPM test"),
    ("swift-test", "Sources/FooTests/Helper.swift", "deny", "Xcode/SPM test"),
    ("swift-test", "native/Tests/Helper.swift", "deny", "folder Tests, unchanged"),
    ("swift-test", "native/Contests/Board.swift", "allow", ""),
    ("swift-test", "native/Tests.swift", "allow", ""),
    ("swift-test", "native/LatestResults.swift", "allow", ""),
    ("swift-test", "native/Attests/x.swift", "allow", ""),
    ("swift-test", "native/UITestsHelper/x.swift", "allow", ""),
    ("swift-test", "native/Footests/x.swift", "allow", ""),
    ("swift-test", "App/LoginTest.swift", "allow", ""),
    ("swift-test", "native/SpeedTest.swift", "allow", ""),
    ("swift-test", "native/ABTest.swift", "allow", ""),
    ("swift-test", "native/DegenUITest/x.swift", "allow", ""),
    ("swift-test", "native/abTests/x.swift", "allow", ""),
)
for _prefix, _path, _expect, _shape in TEST_SHAPE_ROWS:
    if _expect == "deny":
        add("%s: Write of %s %s is refused" % (_prefix, _shape, _path), "deny", rule=BT,
            tool="Write", file_path=_path, **B)
    else:
        add("%s: Write of non-test %s is allowed" % (_prefix, _path), "allow", tool="Write",
            file_path=_path, **B)
# The three Edit rows stay, because mutate_guard.py names each one as the case its mutant must fail.
add("builder-test: Edit of self-test file scripts/foo-selftest.py is refused", "deny", rule=BT,
    tool="Edit", file_path="scripts/foo-selftest.py", **B)
add("swift-test: Edit of non-test App/LoginTest.swift is allowed", "allow", tool="Edit",
    file_path="App/LoginTest.swift", **B)
add("swift-test: Edit of non-test native/abTests/x.swift is allowed", "allow", tool="Edit",
    file_path="native/abTests/x.swift", **B)

# ---- an Xcode test plan is test config (Degen, 2026-10-11; decisions/builders-cannot-edit-tests.md,
# "Test path"). `native/Degen.xctestplan` is test config. A builder change that ADDS a skip
# (`skippedTests`) disables tests, so it is a test change. A new unrelated key (`codeCoverage`) stays
# allowed. A test-author may edit the plan. The write tool judges the new text. The diff check
# refuses the builder's skip at commit and push (the builder-refuse section), and logs the author's
# plan edit (`xctestplan_logs_case`).
XCTESTPLAN = "native/Degen.xctestplan"
add("builder-test: Edit of .xctestplan that adds skippedTests is refused", "deny", rule=BT,
    tool="Edit", file_path=XCTESTPLAN, new_string='"skippedTests" : [ "LaunchTests" ]', **B)
add("builder-test: Edit of .xctestplan that adds codeCoverage is allowed", "allow", tool="Edit",
    file_path=XCTESTPLAN, new_string='"codeCoverage" : true', **B)
add("test-author: Edit of .xctestplan is allowed", "allow", tool="Edit", file_path=XCTESTPLAN, **A)

# ---- a builder's shell write to a test file: a redirect, tee, sed -i, or a python or node script that
# opens it for write. A read, a write to product code and a recovery are allowed. BR is a builder in a checkout.
BR = dict(B, cwd=GITMAIN)
RULE_AUDIT_EDIT = ("python3 - <<'EOF'\np='lint/test_rule_audit.py'\ns=open(p).read()\n"
                   "s = s.replace('a', 'b')\nopen(p,'w').write(s)\nEOF")
PATHLIB_EDIT = ("python3 - <<'EOF'\nfrom pathlib import Path\np = Path('lint/test_rule_audit.py')\n"
                "p.write_text(p.read_text().replace('a', 'b'))\nEOF")
PY_C_WRITE = "python3 -c \"open('tests/x.py','w').write('x')\""
SCAN_TAIL = "cat > /tmp/scan.py <<'EOF'\nprint(1)\nEOF\npython3 /tmp/scan.py"
TEST_REDIRECTS = (
    "echo x > src/test_app.py", "echo x >> tests/helper.py", "printf x | tee src/test_app.py",
    "sed -i 's/a/b/' src/test_app.py", "cat > tests/x.py <<'EOF'\nx = 1\nEOF",
)
SHELL_TEST_WRITES = (
    ("incident heredoc, quoted EOF, rewrites lint/test_rule_audit.py", RULE_AUDIT_EDIT),
    ("incident heredoc, then a scan tail after EOF", RULE_AUDIT_EDIT + "\n" + SCAN_TAIL),
    ("incident git show redirected onto lint/test_rule_audit.py",
     "git show HEAD:lint/test_rule_audit.py > lint/test_rule_audit.py"),
    ("pathlib heredoc, quoted EOF, write_text on lint/test_rule_audit.py", PATHLIB_EDIT),
    ("heredoc, unquoted EOF, open-write of tests/x.py",
     "python3 - <<EOF\nopen('tests/x.py', 'w').write('x')\nEOF"),
    ("python -c open-write of tests/x.py", PY_C_WRITE),
    ("node -e writeFileSync of web/a.test.js",
     "node -e \"require('fs').writeFileSync('web/a.test.js','x')\""),
    ("echo redirect onto src/test_app.py", TEST_REDIRECTS[0]),
    ("echo append onto tests/helper.py", TEST_REDIRECTS[1]),
    ("printf piped to tee on src/test_app.py", TEST_REDIRECTS[2]),
    ("sed -i on src/test_app.py", TEST_REDIRECTS[3]),
    ("cat heredoc onto tests/x.py", TEST_REDIRECTS[4]),
    ("redirect after cd lint, onto test_rule_audit.py", "cd lint && echo x > test_rule_audit.py"),
    # A lone quote in a heredoc body must not hide the write after it (the scanner respects strings).
    ("heredoc with a lone quote line, then a write to tests/x.py",
     "python3 - <<'EOF'\n'\nopen('tests/x.py', 'w').write('x')\nEOF"),
    # A multi-line template literal must not hide the write after it.
    ("node heredoc with a multi-line template literal, then a write to web/a.test.js",
     "node - <<'EOF'\nconst s = `\nline one\nline two\n`;\nrequire('fs').writeFileSync('web/a.test.js', s)\nEOF"),
    # A comment opener inside quotes is text, so the redirect after it still writes the test.
    ("echo of a hash in quotes, redirected onto tests/x.py", "echo \"#\" > tests/x.py"),
)
for _name, _command in SHELL_TEST_WRITES:
    sh("builder-test: shell write, %s, is refused" % _name, _command, "deny", rule=BT,
       carries=("test-author",), **BR)
# A builder never writes a mutation test, by any shell form.
MUTATION_TESTS = ("hooks/mutate_guard.py", "hooks/mutate_shared.py", "janitor/mutate_sweep.py")
for _path in MUTATION_TESTS:
    for _form, _command in (
        ("redirect", "echo 'x = 1' > %s" % _path),
        ("tee", "printf 'x = 1' | tee %s" % _path),
        ("sed -i", "sed -i 's/a/b/' %s" % _path),
        ("cp", "cp src/app.py %s" % _path),
    ):
        sh("builder-test: shell %s onto %s is refused" % (_form, _path), _command, "deny", rule=BT,
           carries=("test-author",), **BR)

# The reads, the writes to product code, the quoted and commented text, and the recovery forms stay allowed.
SHELL_TEST_ALLOWS = (
    ("cat of tests/x.py", "cat tests/x.py"),
    ("grep of src/test_app.py", "grep -n foo src/test_app.py"),
    ("python heredoc that prints tests/x.py", "python3 - <<'EOF'\nprint(open('tests/x.py').read())\nEOF"),
    ("python heredoc that reads tests/x.py and writes src/app.py",
     "python3 - <<'EOF'\nfrom pathlib import Path\np = Path('tests/x.py')\n"
     "Path('src/app.py').write_text(p.read_text())\nEOF"),
    ("echo redirect onto src/app.py", "echo x > src/app.py"),
    ("python heredoc writing src/app.py", "python3 - <<'EOF'\nopen('src/app.py', 'w').write('x')\nEOF"),
    ("echo of a string that names tests/x.py", "echo \"edit tests/x.py > later\""),
    ("printf of a string that holds open(tests/x.py)", "printf '%s\\n' 'open(\"tests/x.py\",\"w\")'"),
    ("heredoc with a comment and a quote inside a string, naming tests/x.py",
     "python3 - <<'EOF'\n# don't touch tests/x.py\nprint(\"it's # fine\")\nEOF"),
    ("heredoc with a lone quote line, then a write to src/app.py",
     "python3 - <<'EOF'\n'\nopen('src/app.py', 'w').write('x')\nEOF"),
    ("product write with a comment naming a test path", "echo x > src/app.py # tests/x.py"),
    ("recovery by git checkout of tests/x.py", "git checkout -- tests/x.py"),
    ("recovery by git restore of tests/x.py", "git restore tests/x.py"),
    ("scan tail alone: a heredoc to /tmp, then python3 runs it", SCAN_TAIL),
    # The near miss stays product code for a builder (see the mutation test block above).
    ("echo redirect onto hooks/mutate_x.py", "echo 'x = 1' > hooks/mutate_x.py"),
)
for _name, _command in SHELL_TEST_ALLOWS:
    sh("builder-test: shell %s is allowed" % _name, _command, "allow", **BR)
# The test-author writes tests, so the same shell writes stay allowed to it. A main session, and a
# session run with --agent builder and no agent_id, is not judged.
for _name, _command in (
    ("incident heredoc", RULE_AUDIT_EDIT), ("pathlib heredoc", PATHLIB_EDIT),
    ("python -c open-write", PY_C_WRITE), ("echo redirect", TEST_REDIRECTS[0]),
    ("echo append", TEST_REDIRECTS[1]), ("printf piped to tee", TEST_REDIRECTS[2]),
    ("sed -i", TEST_REDIRECTS[3]), ("cat heredoc", TEST_REDIRECTS[4]),
    ("echo redirect onto a mutation test", "echo 'x = 1' > hooks/mutate_guard.py"),
):
    sh("builder-test: test-author shell write, %s, is allowed" % _name, _command, "allow", **A)
sh("builder-test: main session shell write of a test is allowed", RULE_AUDIT_EDIT, "allow",
   cwd=GITMAIN)
sh("builder-test: --agent builder with no agent_id shell write of a test is allowed",
   RULE_AUDIT_EDIT, "allow", agent_type="builder", cwd=GITMAIN)

# Review false alarms: a read whose argument is a mutating word stays allowed, and a name that a
# heredoc rebinds is read at its new value, so a write to product code after the rebind is allowed.
sh("builder-test: shell grep of tests/test_guard.py for a mutating word is allowed",
   "grep -n install tests/test_guard.py", "allow", **BR)
sh("builder-test: shell pytest -k with a mutating word is allowed",
   "python3 -m pytest -k copy tests/test_guard.py", "allow", **BR)
# A `bash -c` script is read at its command position, as the shell reads it: a mutating word that is only an
# argument of a test run inside it reads as a read. A write to a test inside the script stays refused, whether
# the write is the script's first command or a later one after `;`.
sh("builder-test: bash -c pytest -k with a mutating word on a test is allowed",
   'bash -c "pytest -k install tests/test_x.py"', "allow", **BR)
sh("builder-test: timeout around bash -c pytest -k with a mutating word on a test is allowed",
   'timeout 300 bash -c "pytest -k move tests/x.py"', "allow", **BR)
sh("builder-test: bash -c echo redirect onto a test is refused",
   'bash -c "echo x > tests/test_x.py"', "deny", rule=BT, carries=("test-author",), **BR)
sh("builder-test: bash -c cp onto a test is refused",
   'bash -c "cp /tmp/a tests/test_x.py"', "deny", rule=BT, carries=("test-author",), **BR)
sh("builder-test: bash -c install onto a test is refused",
   'bash -c "install -m 644 /tmp/a tests/test_x.py"', "deny", rule=BT, carries=("test-author",), **BR)
sh("builder-test: bash -c pytest read, then a cp onto a test after the semicolon, is refused",
   'bash -c "pytest -k install tests/test_x.py; cp /tmp/a tests/test_x.py"', "deny", rule=BT,
   carries=("test-author",), **BR)
# A real newline inside the bash -c string starts a new command, so a write after it is judged the same way.
sh("builder-test: bash -c with a newline before a cp onto a test is refused",
   'bash -c "set -e\ncp /tmp/a tests/test_x.py"', "deny", rule=BT, carries=("test-author",), **BR)
sh("builder-test: bash -c with a newline before a sed -i on a test is refused",
   'bash -c "echo hi\nsed -i s/a/b/ tests/test_x.py"', "deny", rule=BT, carries=("test-author",), **BR)
# A quoted argument with a real newline in it, and an escaped quote in a bash -c string, do not hide the write
# that follows: each is read at its command position, as the shell reads it.
sh("builder-test: sed -i with a newline in its quoted script, onto a test, is refused",
   "sed -i '1i\\\ntext' tests/test_x.py", "deny", rule=BT, carries=("test-author",), **BR)
sh("builder-test: cp of a quoted argument with a newline onto a test is refused",
   'cp "a\nb" tests/x.py', "deny", rule=BT, carries=("test-author",), **BR)
sh("builder-test: bash -c with an escaped quote, then ; and a cp onto a test, is refused",
   r'bash -c "echo \"x\"; cp /tmp/a tests/test_x.py"', "deny", rule=BT, carries=("test-author",), **BR)
sh("builder-test: bash -c with an escaped quote, then a pipe into a cp onto a test, is refused",
   r'bash -c "echo \"x\"|cp /tmp/a tests/test_x.py"', "deny", rule=BT, carries=("test-author",), **BR)
sh("builder-test: bash -c with an escaped quote, then a newline and a cp onto a test, is refused",
   'bash -c "echo \\"x\\"\ncp /tmp/a tests/test_x.py"', "deny", rule=BT, carries=("test-author",), **BR)
# The message after -m keeps its place in the words a git commit is read by, so a pathspec after it is read at its
# own place: a path named rm or mv is no git rm or git mv. A real git rm after the commit is still refused.
sh("builder-test: git commit with a message, then a pathspec named rm before a test, is allowed",
   'git commit -m "docs" rm tests/test_x.py', "allow", **BR)
sh("builder-test: git commit with a message, then a pathspec named mv before a test, is allowed",
   'git commit -m "docs" mv tests/test_x.py', "allow", **BR)
sh("builder-test: git commit with a message, then && and a git rm of a test, is refused",
   'git commit -m "docs" && git rm tests/test_x.py', "deny", rule=BT, carries=("test-author",), **BR)
sh("builder-test: python heredoc that reads tests/x.py, rebinds the name, then writes src/app.py is allowed",
   "python3 - <<'EOF'\np='tests/x.py'\nprint(open(p).read())\np='src/app.py'\nopen(p,'w').write('x')\nEOF",
   "allow", **BR)
# A write to a test path through the working folder is refused, however the path is built.
sh("builder-test: shell pathlib write to a test under Path.cwd() is refused",
   "python3 - <<'EOF'\nfrom pathlib import Path\nROOT = Path.cwd()\n"
   "(ROOT / 'tests' / 'test_x.py').write_text('x')\nEOF", "deny", rule=BT,
   carries=("test-author",), **BR)
sh("builder-test: shell open-write to a test under os.getcwd() is refused",
   "python3 - <<'EOF'\nimport os\nopen(os.path.join(os.getcwd(), 'tests', 'x.py'), 'w').write('x')\nEOF",
   "deny", rule=BT, carries=("test-author",), **BR)

# ---- the diff, judged at commit, push and SubagentStop
