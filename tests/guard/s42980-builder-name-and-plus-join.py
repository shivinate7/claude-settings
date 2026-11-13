# section 42980
FAMILY = "paths"
#
# A name bound to the working folder, then joined to a test path by `+` or in an f-string, names a test path in
# that folder, as the join written out does (section 42960). A name bound to an unknown call, or to a temp folder,
# names no repo path, so it stays allowed. A known `+` join (`'tests/' + 'x.py'`) reads as the path it spells.
# B is the builder fixture of section 20369.

# RED. A name bound to the working folder, joined to a test path, is a builder's test write.
sh("builder-test: a name bound to os.getcwd(), joined to /tests/x.py by +, is refused",
   "python3 - <<'EOF'\nimport os\nd = os.getcwd()\nopen(d + '/tests/x.py', 'w').write('x')\nEOF",
   "deny", rule=BT, **B)
sh("builder-test: a name bound to os.getcwd(), in an f-string over /tests/x.py, is refused",
   "python3 - <<'EOF'\nimport os\nd = os.getcwd()\nopen(f'{d}/tests/x.py', 'w').write('x')\nEOF",
   "deny", rule=BT, **B)
sh("builder-test: a name bound to os.getcwd(), then a name bound to it + /tests, then + /x.py, is refused",
   "python3 - <<'EOF'\nimport os\nROOT = os.getcwd()\nTESTS = ROOT + '/tests'\nopen(TESTS + '/x.py', 'w').write('x')\nEOF",
   "deny", rule=BT, **B)

# CONTROLS. Each pins a form the guard must allow: a refusal would be a false alarm.
# An unknown call names no repo path, by + or in an f-string.
sh("builder join: a name bound to an unknown call, joined to /tests/x.py by +, is allowed",
   "python3 - <<'EOF'\nd = tempfile_unknown()\nopen(d + '/tests/x.py', 'w').write('x')\nEOF", "allow", **B)
sh("builder join: a name bound to an unknown call, in an f-string over /tests/x.py, is allowed",
   "python3 - <<'EOF'\nd = tempfile_unknown()\nopen(f'{d}/tests/x.py', 'w').write('x')\nEOF", "allow", **B)
# A temp folder is a system folder, so a test path under it is no test of this checkout.
sh("builder join: a name bound to a temp folder from mkdtemp, joined to /tests/x.py by +, is allowed",
   "python3 - <<'EOF'\nimport tempfile\nd = tempfile.mkdtemp()\nopen(d + '/tests/x.py', 'w').write('x')\nEOF",
   "allow", **B)
# A product file under the working folder is the builder's to write.
sh("builder-test: a name bound to os.getcwd(), joined to /src/app.py by +, is allowed",
   "python3 - <<'EOF'\nimport os\nd = os.getcwd()\nopen(d + '/src/app.py', 'w').write('x')\nEOF", "allow", **B)

# Known `+` joins, `'tests/' + 'x.py'` and `os.getcwd() + '/tests' + '/x.py'`, are refused today, so these pass.
# Their red is a mutant of `_py_concat` that returns no path: the two refusal cases must go red under it.
sh("builder-test: heredoc write to 'tests/' + 'x.py' is refused",
   "python3 - <<'EOF'\nopen('tests/' + 'x.py', 'w').write('x')\nEOF", "deny", rule=BT, **B)
sh("builder-test: heredoc write to os.getcwd() + '/tests' + '/x.py' is refused",
   "python3 - <<'EOF'\nimport os\nopen(os.getcwd() + '/tests' + '/x.py', 'w').write('x')\nEOF",
   "deny", rule=BT, **B)
sh("builder join: a known + join, 'src/' + 'app.py', is a product file and allowed",
   "python3 - <<'EOF'\nopen('src/' + 'app.py', 'w').write('x')\nEOF", "allow", **B)
