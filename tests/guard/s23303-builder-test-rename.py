# section 23303
# A builder may rename a test and edit its comments and docstrings, when the parsed test bodies and the test
# count are unchanged (decision builders-cannot-edit-tests). Every other
# edit to a test file stays refused, as before. The allow cases, and the refuse cases that name a gap (a rename onto
# a name another statement binds, a fixture rename), are red on the old code. The other refuse cases are its green
# controls.
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
# BR_BIND binds a test name a second way: an import, an assignment after a def, and a class attribute above a method.
# BR_SCAN holds text that a naive scan misreads: a `#` inside a string, a triple-quoted string after the docstring,
# and a lone quote in a comment. BR_FIX holds a decorated fixture named test_, which is no test.
BR_BIND_REL = "tests/test_bind.py"
BR_BIND = (
    "from helpers import test_items\n"
    "\n"
    "\n"
    "def test_add():\n"
    "    assert 1 + 1 == 2\n"
    "\n"
    "\n"
    "def test_double():\n"
    "    assert 2 * 2 == 4\n"
    "\n"
    "\n"
    "test_cases = [1, 2]\n"
    "\n"
    "\n"
    "class TestCalc:\n"
    "    test_limits = 3\n"
    "\n"
    "    def test_plus(self):\n"
    "        assert 1 + 2 == 3\n"
)
BR_SCAN_REL = "tests/test_scan.py"
BR_SCAN = (
    "def test_label():\n"
    '    label = "one"\n'
    '    assert label == "#one"\n'
    "\n"
    "\n"
    "def test_block():\n"
    '    """Adding gives the sum."""\n'
    "    assert 1 + 1 == 2\n"
    '    """A note: the sum is two."""\n'
    "\n"
    "\n"
    "def test_lone_quote():\n"
    "    # don't check the sum\n"
    "    assert 1 + 1 == 2\n"
)
BR_FIX_REL = "tests/test_fixture.py"
BR_FIX = (
    "import pytest\n"
    "\n"
    "\n"
    "@pytest.fixture\n"
    "def test_value():\n"
    "    return 2\n"
    "\n"
    "\n"
    "def test_double(test_value):\n"
    "    assert test_value * 2 == 4\n"
)
BR_FILES = {BR_CALC_REL: BR_CALC, BR_FULL_REL: BR_FULL, BR_EMPTY_REL: "",  # the empty file: the empty state
            BR_BIND_REL: BR_BIND, BR_SCAN_REL: BR_SCAN, BR_FIX_REL: BR_FIX}
BR_WT = diff_repo("bt-rename", lambda w: None, files=BR_FILES)


def _br_once(text, pairs):
    """`text` with each (old, new) pair applied, each old text held exactly once. A miss stops the run."""
    for old, new in pairs:
        if text.count(old) != 1:
            sys.exit("fixture setup failed: %r is not exactly one match in a test file" % old[:48])
        text = text.replace(old, new, 1)
    return text


def _br_is_fixture(node):
    """True for a def decorated `@pytest.fixture` or `@fixture`, bare or called. A fixture is no test."""
    import ast

    for deco in node.decorator_list:
        head = deco.func if isinstance(deco, ast.Call) else deco
        if (isinstance(head, ast.Attribute) and head.attr == "fixture") or (
                isinstance(head, ast.Name) and head.id == "fixture"):
            return True
    return False


def _br_is_test_def(node):
    """True for a def the runner collects as a test: its name starts with `test`, and it is no fixture."""
    return node.name.startswith("test") and not _br_is_fixture(node)


def _br_collide(text):
    """True when one scope (the module, or a class body) binds a test name twice: a test def, and also an assign,
    an import or a class attribute of that name. Text that does not parse stops the run."""
    import ast

    try:
        tree = ast.parse(text)
    except SyntaxError:
        sys.exit("fixture setup failed: a test file in this section does not parse as python")
    for scope in [tree] + [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]:
        defs, others = set(), set()
        for node in scope.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _br_is_test_def(node):
                defs.add(node.name)
            elif isinstance(node, ast.Assign):
                others |= {name.id for target in node.targets for name in ast.walk(target)
                           if isinstance(name, ast.Name)}
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                others |= {(alias.asname or alias.name).split(".")[0] for alias in node.names}
        if defs & others:
            return True
    return False


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
            if _br_is_test_def(node):
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


def _br_check(old, new, allowed, label, mode="shape"):
    """Stop the run unless `new` changes `old` the way the case says. An allow case changes names, comments and
    docstrings only. A refuse case of mode `shape` changes a body, a count or a collection. Mode `collide` is a pure
    rename onto a name another statement of its scope binds. Mode `fixture` renames a fixture: no test name moves."""
    old_names, old_shape = _br_parts(old)
    new_names, new_shape = _br_parts(new)
    if allowed:
        ok = old_shape == new_shape and len(old_names) == len(new_names) == len(set(new_names))
    elif mode == "collide":
        ok = old_shape == new_shape and _br_collide(new) and not _br_collide(old)
    elif mode == "fixture":
        ok = old_shape != new_shape and old_names == new_names
    else:
        ok = (old_shape != new_shape or len(set(new_names)) != len(set(old_names))
              or len(set(new_names)) != len(new_names))
    if not ok:
        sys.exit("fixture setup failed: %s does not change its test file the way its case says" % label)


def _br_edit(name, expected, rel, old_s, new_s, mode="shape"):
    """One Edit of a test file. The Edit tool needs `old_s` once in the file on disk, so it is checked here."""
    base = BR_FILES[rel]
    new = _br_once(base, [(old_s, new_s)])
    _br_check(base, new, expected == "allow", name, mode)
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

# ---- refuse: the gaps. A rename onto a name another statement of its scope binds is refused, whatever the order of
# the two statements, since the runner may then collect one test fewer. A fixture is no test, so its rename is not a
# test rename, and the route does not cover it (red on the old code: each of these is allowed there).
_br_edit("builder-test-rename refuse: Edit renames a test onto a name a module assignment binds", "deny",
         BR_BIND_REL, "def test_add():", "def test_cases():", mode="collide")
_br_edit("builder-test-rename refuse: Edit renames a test onto a name an import binds", "deny",
         BR_BIND_REL, "def test_double():", "def test_items():", mode="collide")
_br_edit("builder-test-rename refuse: Edit renames a test method onto a name a class attribute binds", "deny",
         BR_BIND_REL, "    def test_plus(self):", "    def test_limits(self):", mode="collide")
_br_edit("builder-test-rename refuse: Edit renames a decorated pytest fixture named test_", "deny",
         BR_FIX_REL, "def test_value():", "def test_seed():", mode="fixture")

# ---- scanner cases: the verdict reads the parsed tree. A `#` inside a string and a triple-quoted string after the
# docstring are code, so they are refused; a lone quote in a comment is free, so it is allowed.
_br_edit("builder-test-rename control: Edit changes a string that holds a #", "deny",
         BR_SCAN_REL, 'assert label == "#one"', 'assert label == "#two"')
_br_edit("builder-test-rename control: Edit changes a triple-quoted string after the docstring", "deny",
         BR_SCAN_REL, '"""A note: the sum is two."""', '"""A note: the sum is three."""')
_br_edit("builder-test-rename: Edit changes a comment that holds a lone quote", "allow",
         BR_SCAN_REL, "    # don't check the sum", "    # don't check the total")

FAMILY = _BR_PRIOR_FAMILY
