# section 42960
FAMILY = "paths"
#
# A `+` join whose left side is the working folder names a test path in that folder. `os.getcwd()`,
# `Path.cwd()` and an f-string's `{os.getcwd()}` read as the working folder of the call, as they already do
# inside `os.path.join`. A `+` join with an unknown left side reads as no repo path, and a temp folder is a
# system folder, so both stay allowed. B is the builder fixture of section 20369: a call from its linked
# worktree.

# RED. The working folder joined to a test path, by `+` or in an f-string, is a builder's test write.
sh("builder-test: heredoc write to os.getcwd() + '/tests/x.py' is refused",
   "python3 - <<'EOF'\nimport os\nopen(os.getcwd() + '/tests/x.py', 'w').write('x')\nEOF",
   "deny", rule=BT, **B)
sh("builder-test: heredoc write to str(Path.cwd()) + '/tests/x.py' is refused",
   "python3 - <<'EOF'\nfrom pathlib import Path\nopen(str(Path.cwd()) + '/tests/x.py', 'w').write('x')\nEOF",
   "deny", rule=BT, **B)
sh("builder-test: heredoc write to an f-string of os.getcwd() over /tests/x.py is refused",
   "python3 - <<'EOF'\nimport os\nopen(f'{os.getcwd()}/tests/x.py', 'w').write('x')\nEOF",
   "deny", rule=BT, **B)
sh("builder-test: python -c write to os.getcwd() + '/tests/x.py' is refused",
   '''python3 -c "import os; open(os.getcwd() + '/tests/x.py', 'w').write('x')"''',
   "deny", rule=BT, **B)
sh("builder-test: a name bound to os.getcwd() + '/tests/x.py', then written, is refused",
   "python3 - <<'EOF'\nimport os\np = os.getcwd() + '/tests/x.py'\nopen(p, 'w').write('x')\nEOF",
   "deny", rule=BT, **B)

# CONTROLS. Each pins a form the guard must allow: a refusal would be a false alarm.
# An unknown base, in a `+` or an f-string, names no repo path: the join is /tests/x.py, outside every repo.
sh("builder join: an unknown base joined to /tests/x.py by + is allowed",
   "python3 - <<'EOF'\nimport os\ntmpdir = os.environ['SCRATCH']\nopen(tmpdir + '/tests/x.py', 'w').write('x')\nEOF",
   "allow", **B)
sh("builder join: an unknown base in an f-string over /tests/x.py is allowed",
   "python3 - <<'EOF'\nimport os\ntmpdir = os.environ['SCRATCH']\nopen(f'{tmpdir}/tests/x.py', 'w').write('x')\nEOF",
   "allow", **B)
# A temp folder is a system folder, so a test path under it is no test of this checkout.
sh("builder join: a temp folder from mkdtemp + /tests/x.py is allowed",
   "python3 - <<'EOF'\nimport tempfile\ntmpdir = tempfile.mkdtemp()\nopen(tmpdir + '/tests/x.py', 'w').write('x')\nEOF",
   "allow", **B)
# A product file under the working folder is the builder's to write, and a read of a test is no write.
sh("builder-test: a write of src/app.py under os.getcwd() + a string is allowed",
   "python3 - <<'EOF'\nimport os\nopen(os.getcwd() + '/src/app.py', 'w').write('x')\nEOF", "allow", **B)
sh("builder-test: a read of tests/test_x.py under os.getcwd() + a string is allowed",
   "python3 - <<'EOF'\nimport os\nprint(open(os.getcwd() + '/tests/test_x.py').read())\nEOF", "allow", **B)
