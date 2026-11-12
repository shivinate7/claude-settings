# section 20370
FAMILY = "paths"

# ---- a builder's shell write fed by find, xargs, a for list or a $( ) substitution (decision
# builders-cannot-edit-tests). The shell check reads the command's own words. It does not read the test
# paths that a fed command takes from another command. Each deny row names a literal tests root, so the
# path shape decides it and no file on disk does. Each deny row is red until the reader reads its fed
# path. The controls name product roots and read-only fed commands, and stay allowed.
FED_TEST_WRITES = (
    ("find piped to xargs, sed -i over tests", "find tests|xargs sed -i s/a/b/"),
    ("find piped to xargs with -I, sed -i over tests", "find tests|xargs -I{} sed -i s/a/b/ {}"),
    ("find -print0 piped to xargs -0, sed -i over tests", "find tests -print0 | xargs -0 sed -i s/a/b/"),
    ("find -exec sed -i over tests *.py", "find tests -name '*.py' -exec sed -i s/a/b/ {} +"),
    ("find -execdir sed -i over tests", "find tests -execdir sed -i s/a/b/ {} +"),
    ("for loop over tests/*.py, sed -i on $f", "for f in tests/*.py; do sed -i s/a/b/ $f; done"),
    ("for loop over tests/*.py, sed -i on \"$f\"", "for f in tests/*.py; do sed -i s/a/b/ \"$f\"; done"),
    ("find substitution over tests, body on two lines, sed -i", "sed -i s/a/b/ $(\nfind tests -name '*.py'\n)"),
    ("find with two -exec terminators, then find tests piped to xargs, sed -i",
     "find src -exec true {} + -exec true {} +; find tests | xargs sed -i s/a/b/"),
    # A lone apostrophe inside double quotes is text, so the fed write after it still lands on a test.
    ("lone apostrophe in double quotes, then find piped to xargs, sed -i over tests",
     "echo \"don't\"; find tests|xargs sed -i s/a/b/"),
    ("lone apostrophe in double quotes, then for loop over tests/*.py, sed -i on $f",
     "echo \"don't\"; for f in tests/*.py; do sed -i s/a/b/ $f; done"),
    # A comment opener inside quotes is text (the scanner respects strings).
    ("comment opener in double quotes, then find piped to xargs, sed -i over tests",
     "echo \"# x\"; find tests | xargs sed -i s/a/b/"),
    # A quoted string over two lines must not hide the find pipe after it.
    ("two-line quoted string, then find piped to xargs, sed -i over tests",
     "echo \"one\ntwo\"; find tests|xargs sed -i s/a/b/"),
)
for _name, _command in FED_TEST_WRITES:
    sh("builder-test: shell write, %s, is refused" % _name, _command, "deny", rule=BT,
       carries=("test-author",), **BR)
# A substitution over a literal tests root already refuses on main. These are controls, so a later change
# that stops reading a `$( )` body, or a backtick body, fails here.
FED_SUBST_CONTROLS = (
    ("grep substitution over tests, sed -i", "sed -i s/a/b/ $(grep -rl a tests)"),
    ("backtick substitution over tests, sed -i", "sed -i s/a/b/ `grep -rl a tests`"),
    ("find substitution over tests, sed -i", "sed -i s/a/b/ $(find tests -name 'test_*.py' -type f)"),
)
for _name, _command in FED_SUBST_CONTROLS:
    sh("builder-test: shell write, %s, is refused [substitution control]" % _name, _command, "deny",
       rule=BT, carries=("test-author",), **BR)

# The same fed shapes on product roots, and the read-only fed forms, stay allowed. A -path value and a
# grep pattern are no root, and a mention of a fed write inside quotes is text.
FED_SHELL_ALLOWS = (
    ("find over src piped to xargs, sed -i", "find src|xargs sed -i s/a/b/"),
    ("find over src piped to xargs -0, sed -i", "find src -print0 | xargs -0 sed -i s/a/b/"),
    ("for loop over src/*.py, sed -i on $f", "for f in src/*.py; do sed -i s/a/b/ $f; done"),
    ("find src with -not -path tests/*, -exec sed -i", "find src -not -path 'tests/*' -exec sed -i s/a/b/ {} +"),
    ("grep pattern tests over src piped to xargs, sed -i", "grep -rl tests src|xargs sed -i s/a/b/"),
    ("find over tests piped to xargs, grep -n", "find tests|xargs grep -n foo"),
    ("echo of a find pipe that names tests in quotes", "echo \"find tests | xargs sed -i\""),
    ("lone apostrophe in double quotes, then find piped to xargs over src",
     "echo \"don't\"; find src|xargs sed -i s/a/b/"),
    ("two-line quoted string, then find piped to xargs over src",
     "echo \"one\ntwo\"; find src|xargs sed -i s/a/b/"),
)
for _name, _command in FED_SHELL_ALLOWS:
    sh("builder-test: shell %s is allowed" % _name, _command, "allow", **BR)
