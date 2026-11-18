# section 23303
# A builder may rename a test and edit its comments and docstrings, when the parsed test bodies and the test
# count are unchanged (decision builders-cannot-edit-tests). Every other
# edit to a test file stays refused, as before. The allow cases are red on the old code; the refuse cases are its
# green controls.
#
# The fixture is one real linked worktree (diff_repo, section 21304), with the test files committed on main, so
# the Edit tool's old text is the file on disk. Each case's old and new text are checked with ast before the case
# is registered: an allow case changes names, comments or docstrings only; a refuse case changes a body, drops a
# test, adds a name that collides with another, or takes a test out of the runner's collection. A fixture that
# builds the wrong change would make a verdict mean nothing, so it stops the run.
_BR_PRIOR_FAMILY = FAMILY
FAMILY = "builder-refuse"

BR_AGENT = dict(agent_id="bld-rename", agent_type="builder")
BR_CALC_REL = "tests/test_calc.py"
BR_FULL_REL = "tests/test_full.py"
BR_EMPTY_REL = "tests/test_empty.py"
BR_CALC = (
    "def double(x):\n"
    "    return x * 2\n"
    "\n"
    "\n"
    "def test_add():\n"
    '    """Adding two numbers gives their sum."""\n'
    "    # check the sum\n"
    "    assert 1 + 1 == 2\n"
    "\n"
    "\n"
    "def test_double():\n"
    '    """Doubling gives twice the value."""\n'
    "    assert double(3) == 6\n"
    "\n"
    "\n"
    "class TestCalc:\n"
    '    """Calculator checks."""\n'
    "\n"
    "    def test_plus(self):\n"
    '        """Plus gives the sum."""\n'
    "        assert 1 + 2 == 3\n"
)
BR_TEST_DOUBLE_BLOCK = 'def test_double():\n    """Doubling gives twice the value."""\n    assert double(3) == 6\n\n\n'
# Thirty tests: the full-size state of a test file.
BR_FULL = "".join("def test_case_%02d():\n    assert %d == %d\n\n\n" % (n, n, n) for n in range(30))
BR_FILES = {BR_CALC_REL: BR_CALC, BR_FULL_REL: BR_FULL, BR_EMPTY_REL: ""}  # the empty file: the empty state
BR_WT = diff_repo("bt-rename", lambda w: None, files=BR_FILES)


def _br_once(text, pairs):
    """`text` with each (old, new) pair applied, each old text held exactly once. A miss stops the run."""
    for old, new in pairs:
        if text.count(old) != 1:
            sys.exit("fixture setup failed: %r is not exactly one match in a test file" % old[:48])
        text = text.replace(old, new, 1)
    return text


def _br_parts(text):
    """The test function names of `text` in file order, and its ast dump with each test name and each
    docstring blanked. A comment is no node, so it is free. Text that does not parse stops the run."""
    import ast

    class Strip(ast.NodeTransformer):
        def __init__(self):
            self.names = []

        def drop_docstring(self, node):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(
                    first.value.value, str):
                node.body = node.body[1:] or [ast.Pass()]

        def visit_FunctionDef(self, node):
            self.generic_visit(node)
            if node.name.startswith("test"):
                self.names.append(node.name)
                node.name = ""
            self.drop_docstring(node)
            return node

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_ClassDef(self, node):
            self.generic_visit(node)
            self.drop_docstring(node)
            return node

        def visit_Module(self, node):
            self.generic_visit(node)
            self.drop_docstring(node)
            return node

    stripper = Strip()
    try:
        tree = stripper.visit(ast.parse(text))
    except SyntaxError:
        sys.exit("fixture setup failed: a test file in this section does not parse as python")
    return stripper.names, ast.dump(tree)


def _br_check(old, new, allowed, label):
    """Stop the run unless `new` changes `old` the way the case says: names, comments and docstrings only when
    `allowed`; otherwise a body, a count or a name that collides or leaves the runner's collection."""
    old_names, old_shape = _br_parts(old)
    new_names, new_shape = _br_parts(new)
    if allowed:
        ok = old_shape == new_shape and len(old_names) == len(new_names) == len(set(new_names))
    else:
        ok = (old_shape != new_shape or len(set(new_names)) != len(set(old_names))
              or len(set(new_names)) != len(new_names))
    if not ok:
        sys.exit("fixture setup failed: %s does not change its test file the way its case says" % label)


def _br_edit(name, expected, rel, old_s, new_s):
    """One Edit of a test file. The Edit tool needs `old_s` once in the file on disk, so it is checked here."""
    base = BR_FILES[rel]
    new = _br_once(base, [(old_s, new_s)])
    _br_check(base, new, expected == "allow", name)
    add(name, expected, rule=None if expected == "allow" else BT,
        carries=() if expected == "allow" else ("test-author", "Report"),
        tool="Edit", cwd=BR_WT, file_path=os.path.join(BR_WT, rel),
        old_string=old_s, new_string=new_s, **BR_AGENT)


def _br_write(name, expected, rel, content):
    """One Write of a test file: the whole new content, checked against the file on disk."""
    _br_check(BR_FILES[rel], content, expected == "allow", name)
    add(name, expected, rule=None if expected == "allow" else BT,
        carries=() if expected == "allow" else ("test-author", "Report"),
        tool="Write", cwd=BR_WT, file_path=os.path.join(BR_WT, rel), content=content, **BR_AGENT)


# ---- allow: red on the old code. Names, comments and docstrings change; every parsed body and the count hold.
_br_edit("builder-test-rename: Edit renames a test function, its body kept", "allow",
         BR_CALC_REL, "def test_add():", "def test_sum():")
_br_edit("builder-test-rename: Edit changes only a test's comment", "allow",
         BR_CALC_REL, "    # check the sum", "    # check the total")
_br_edit("builder-test-rename: Edit changes only a test's docstring", "allow",
         BR_CALC_REL, '    """Doubling gives twice the value."""', '    """Doubling returns twice the value."""')
_br_edit("builder-test-rename: Edit renames a test method in a test class", "allow",
         BR_CALC_REL, "    def test_plus(self):", "    def test_addition(self):")
_br_edit("builder-test-rename: Edit renames a test and edits its docstring in one call", "allow",
         BR_CALC_REL, 'def test_double():\n    """Doubling gives twice the value."""',
         'def test_twice():\n    """Twice the value."""')
_br_write("builder-test-rename: Write renames a test, edits a comment and a docstring, every body kept", "allow",
          BR_CALC_REL, _br_once(BR_CALC, [("def test_add():", "def test_sum():"),
                                          ("    # check the sum", "    # check the total"),
                                          ('    """Calculator checks."""', '    """Checks of the calculator."""')]))
_br_edit("builder-test-rename: Edit renames one test in a 30-test file", "allow",
         BR_FULL_REL, "def test_case_07():", "def test_seven():")

# ---- refuse: the green controls. Each change is one the rule does not allow.
_br_edit("builder-test-rename control: Edit changes an assertion", "deny",
         BR_CALC_REL, "    assert 1 + 1 == 2", "    assert 1 + 1 == 3")
_br_write("builder-test-rename control: Write removes a test function", "deny",
          BR_CALC_REL, _br_once(BR_CALC, [(BR_TEST_DOUBLE_BLOCK, "")]))
_br_edit("builder-test-rename control: Edit renames a test and changes its body", "deny",
         BR_CALC_REL, 'def test_double():\n    """Doubling gives twice the value."""\n    assert double(3) == 6',
         'def test_twice():\n    """Doubling gives twice the value."""\n    assert double(3) == 7')
_br_edit("builder-test-rename control: Edit changes a comment and an assertion in one call", "deny",
         BR_CALC_REL, "    # check the sum\n    assert 1 + 1 == 2", "    # check the total\n    assert 1 + 1 == 3")
_br_edit("builder-test-rename control: Edit renames a test onto another test's name", "deny",
         BR_CALC_REL, "def test_add():", "def test_double():")
_br_edit("builder-test-rename control: Edit renames a test to a name the runner does not collect", "deny",
         BR_CALC_REL, "def test_add():", "def check_add():")
_br_edit("builder-test-rename control: Edit comments out an assertion", "deny",
         BR_CALC_REL, "    assert double(3) == 6", "    # assert double(3) == 6")
_br_edit("builder-test-rename control: Edit adds a skip mark to a test", "deny",
         BR_CALC_REL, "def test_add():", "@pytest.mark.skip(reason='later')\ndef test_add():")
_br_write("builder-test-rename control: Write adds a test to an empty test file", "deny",
          BR_EMPTY_REL, "def test_new():\n    assert 1 == 1\n")
_br_edit("builder-test-rename control: Edit removes one test of a 30-test file", "deny",
         BR_FULL_REL, "def test_case_07():\n    assert 7 == 7\n\n\n", "")

FAMILY = _BR_PRIOR_FAMILY
