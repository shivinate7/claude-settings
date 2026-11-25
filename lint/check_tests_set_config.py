#!/usr/bin/env python3
"""Fails when a test_*.py removes CLAUDE_CONFIG_DIR from the environment at import time and does not set it again.

Such a file runs its cases with the variable unset, so a case that reads the config folder reads the real ~/.claude. Only an import-time
removal counts: a pop, a del, os.environ.clear(), or patch.dict(os.environ, ..., clear=True).start(), also in a loop over a tuple or dict
that holds the name or over os.environ itself (a sweep by prefix is flagged whatever its prefix: the check does not evaluate prefixes). It reaches every case. A pop inside one test method, or inside patch.dict, is that
case's own choice. The file is clean when a set follows its last removal at import time: a set at module level, or in a function the
module calls at module level. A set in setUpModule() clears it too. A set under `if False:`, under `if __name__ == "__main__":`, in one test method, or inside a
with patch.dict block does not. A set is a subscript or annotated assignment, `os.environ |= {...}`, os.environ.update, setdefault or
putenv of the name, a patch.dict(os.environ, ...).start(), a call to a module function that sets it, or enter_context(isolated_config(...)).
The checker reads the names the file binds: an alias of os.environ, a name bound (also with an annotation) to the string or imported from
a module that holds it, a module-level tuple of names, and a module-level dict that holds the name as a key. A module that other files
import is parsed once per run. A test file that does not parse is a problem too.

    python3 lint/check_tests_set_config.py [--root DIR]     # DIR defaults to this script's repo
"""
import ast
import os
import sys

VAR = "CLAUDE_CONFIG_DIR"
SETTERS = ("update", "setdefault")  # os.environ.<name>(...) forms that set a key
SKIP_DIRS = ("node_modules", "__pycache__")
HERE = os.path.dirname(os.path.abspath(__file__))
COMPOUND = (ast.If, ast.For, ast.While, ast.Try, ast.With, ast.ClassDef)
COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)


def is_var(node):
    return isinstance(node, ast.Constant) and node.value == VAR


def holds_var(node):
    """True for a tuple, list or set literal with VAR among its elements."""
    return isinstance(node, (ast.Tuple, ast.List, ast.Set)) and any(is_var(element) for element in node.elts)


_CONSTANTS = {}  # path -> {name: string constant}, or None when the file does not parse; one parse per module per run


def module_constants(path):
    """The constants the module at `path` binds at its top level (annotated or not), read with ast; None when it does not parse."""
    path = os.path.abspath(path)
    if path not in _CONSTANTS:
        try:
            with open(path, encoding="utf-8") as handle:
                tree = ast.parse(handle.read(), filename=path)
        except (OSError, SyntaxError, ValueError):
            _CONSTANTS[path] = None
        else:
            found = {}
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    targets, value = node.targets, node.value
                elif isinstance(node, ast.AnnAssign) and node.value is not None:
                    targets, value = [node.target], node.value
                else:
                    continue
                if isinstance(value, ast.Constant):
                    for target in targets:
                        if isinstance(target, ast.Name):
                            found[target.id] = value.value
            _CONSTANTS[path] = found
    return _CONSTANTS[path]


def imported_value(module, name, folders):
    """The string constant `name` holds in `<module>.py`, found in one of `folders` and read with ast (never copied), else None."""
    for folder in folders:
        path = os.path.join(folder, module + ".py")
        if not os.path.isfile(path):
            continue
        constants = module_constants(path)
        if constants is None:
            return None
        if name in constants:
            return constants[name]
    return None


def is_main_guard(node):
    """True for `if __name__ == "__main__":`, whose body the tests never run."""
    test = node.test
    return isinstance(test, ast.Compare) and isinstance(test.left, ast.Name) and test.left.id == "__name__" \
        and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq) and len(test.comparators) == 1 \
        and isinstance(test.comparators[0], ast.Constant) and test.comparators[0].value == "__main__"


def is_patch_dict_call(node):
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "dict"


class Names:
    """What the file's own module level binds, read before the walk: `environs` (names that alias os.environ), `var_names` (names that
    hold VAR), `var_tuples` (names bound to a tuple that holds VAR), `var_dicts` (names bound to a dict that holds VAR as a key), and
    `helpers` (module functions that set VAR, directly or through another helper, whatever the order of the defs)."""

    def __init__(self, tree, folder):
        self.environs = set()
        self.var_names = set()
        self.var_tuples = set()
        self.var_dicts = set()
        self.helpers = set()
        for node in tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if not isinstance(target, ast.Name):
                        continue
                    if self.is_environ(node.value):
                        self.environs.add(target.id)
                    elif is_var(node.value):
                        self.var_names.add(target.id)
                    elif holds_var(node.value):
                        self.var_tuples.add(target.id)
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                for alias in node.names:
                    if node.module == "os" and alias.name == "environ":
                        self.environs.add(alias.asname or alias.name)
                    elif imported_value(node.module, alias.name, (folder, HERE)) == VAR:
                        self.var_names.add(alias.asname or alias.name)
        for node in tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None and self.dict_has_var(node.value, ()):
                for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                    if isinstance(target, ast.Name):
                        self.var_dicts.add(target.id)
        functions = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name != "setUpModule"]
        grown = True
        while grown:  # a helper may call one defined after it, so read until no def joins
            grown = False
            for node in functions:
                if node.name not in self.helpers and self.sets_var(node, ()):
                    self.helpers.add(node.name)
                    grown = True

    def is_environ(self, node):
        """True for `os.environ`, a bare `environ`, or a name bound to one."""
        return (isinstance(node, ast.Attribute) and node.attr == "environ") \
            or (isinstance(node, ast.Name) and (node.id == "environ" or node.id in self.environs))

    def names_var(self, node, loop_names):
        """True when `node` is the string VAR, a name that holds it, or a loop variable that iterates over a tuple holding it."""
        return is_var(node) or (isinstance(node, ast.Name) and (node.id in loop_names or node.id in self.var_names))

    def loops_over_var(self, iterable):
        """True when a loop over `iterable` may visit VAR: its expression mentions os.environ anywhere, or a tuple or a dict that
        holds VAR. A name inside a string does not count."""
        return any(self.is_environ(part) or holds_var(part) or (isinstance(part, ast.Name) and part.id in self.var_tuples)
                   or self.dict_has_var(part, ()) for part in ast.walk(iterable))

    def sweeps_environ(self, iterable):
        """True when a loop over `iterable` may visit names that the check cannot read: its expression mentions os.environ."""
        return any(self.is_environ(part) for part in ast.walk(iterable))

    def clears_environ(self, call):
        """True for `patch.dict(os.environ, ..., clear=X)` unless X is the constant False, and unless its values name VAR. An X
        the check cannot read counts as a clear (unknown never passes)."""
        if not (is_patch_dict_call(call) and call.args and self.is_environ(call.args[0])):
            return False
        flag = call.args[2] if len(call.args) > 2 else next((keyword.value for keyword in call.keywords if keyword.arg == "clear"), None)
        if flag is None or (isinstance(flag, ast.Constant) and not flag.value):
            return False
        return not (any(self.dict_has_var(arg, ()) for arg in call.args[1:2]) or self.keywords_have_var(call.keywords, ()))

    def removal_line(self, statement, loop_names):
        """The line of an os.environ pop, del or clear of VAR in this one statement, else None."""
        if isinstance(statement, ast.Delete):
            for target in statement.targets:
                if isinstance(target, ast.Subscript) and self.is_environ(target.value) and self.names_var(target.slice, loop_names):
                    return statement.lineno
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
            call = statement.value
            if isinstance(call.func, ast.Attribute) and call.func.attr == "start" and self.clears_environ(call.func.value):
                return statement.lineno
            if isinstance(call.func, ast.Attribute) and self.is_environ(call.func.value):
                if call.func.attr == "pop" and call.args and self.names_var(call.args[0], loop_names):
                    return statement.lineno
                if call.func.attr == "clear" and not call.args:
                    return statement.lineno
        return None

    def dict_has_var(self, node, loop_names):
        """True when `node` is a dict display, a name bound to one, or a dict(...) call, that holds VAR as a key."""
        if isinstance(node, ast.Dict):
            return any(key is not None and self.names_var(key, loop_names) for key in node.keys) \
                or any(key is None and self.dict_has_var(value, loop_names) for key, value in zip(node.keys, node.values))
        if isinstance(node, ast.Name):
            return node.id in self.var_dicts
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "dict":
            return any(self.dict_has_var(arg, loop_names) for arg in node.args) or self.keywords_have_var(node.keywords, loop_names)
        return False

    def keywords_have_var(self, keywords, loop_names):
        """True when a call's keywords name VAR, as `VAR=...` or inside `**{...}`."""
        return any(keyword.arg == VAR or (keyword.arg is None and self.dict_has_var(keyword.value, loop_names)) for keyword in keywords)

    def call_sets(self, call, loop_names):
        """True when this one call sets VAR: os.environ.update or setdefault, os.putenv, patch.dict(os.environ, ...).start(),
        enter_context(isolated_config(...)), or a call to a helper that sets it."""
        func = call.func
        if isinstance(func, ast.Name):
            return func.id in self.helpers
        if not isinstance(func, ast.Attribute):
            return False
        if func.attr in SETTERS and self.is_environ(func.value):
            if func.attr == "setdefault" and call.args and self.names_var(call.args[0], loop_names):
                return True
            return any(self.dict_has_var(arg, loop_names) for arg in call.args) or self.keywords_have_var(call.keywords, loop_names)
        if func.attr == "putenv":
            return bool(call.args) and self.names_var(call.args[0], loop_names)
        if func.attr == "start" and is_patch_dict_call(func.value) and func.value.args and self.is_environ(func.value.args[0]):
            return any(self.dict_has_var(arg, loop_names) for arg in func.value.args[1:]) \
                or self.keywords_have_var(func.value.keywords, loop_names)
        if func.attr == "enter_context" and call.args and isinstance(call.args[0], ast.Call):
            entered = call.args[0].func
            return (isinstance(entered, ast.Name) and entered.id == "isolated_config") \
                or (isinstance(entered, ast.Attribute) and entered.attr == "isolated_config")
        return False

    def sets_var(self, node, loop_names):
        """True when `node` is, or holds, a set of VAR in os.environ, or a call that sets it (see call_sets)."""
        for part in ast.walk(node):
            if isinstance(part, (ast.Assign, ast.AnnAssign)):
                targets = part.targets if isinstance(part, ast.Assign) else [part.target] if part.value is not None else []
                for target in targets:
                    if isinstance(target, ast.Subscript) and self.is_environ(target.value) and self.names_var(target.slice, loop_names):
                        return True
            elif isinstance(part, ast.AugAssign):
                if isinstance(part.op, ast.BitOr) and self.is_environ(part.target) and self.dict_has_var(part.value, loop_names):
                    return True
            elif isinstance(part, ast.Call) and self.call_sets(part, loop_names):
                return True
        return False


def is_patch_dict(item):
    return is_patch_dict_call(item.context_expr)


def bind_loop(target, iterable, names, loop_names, swept):
    """The (loop_names, swept) a loop or comprehension clause `for target in iterable` adds: its variable, when `iterable` may visit VAR."""
    if not names.loops_over_var(iterable):
        return loop_names, swept
    if isinstance(target, ast.Tuple) and target.elts:  # `for key, value in os.environ.items()`
        target = target.elts[0]
    if not isinstance(target, ast.Name):
        return loop_names, swept
    return loop_names + (target.id,), (swept + (target.id,) if names.sweeps_environ(iterable) else swept)


def comprehension_elements(statement, names, loop_names, swept):
    """Yield the element expression of a comprehension statement as a statement of its own, with the comprehension's loop variables
    bound as a `for` loop binds them, so it is judged by the same rules as the loop form."""
    comprehension = statement.value
    for generator in comprehension.generators:
        loop_names, swept = bind_loop(generator.target, generator.iter, names, loop_names, swept)
    elements = [comprehension.key, comprehension.value] if isinstance(comprehension, ast.DictComp) else [comprehension.elt]
    for element in elements:
        yield ast.copy_location(ast.Expr(value=element), statement), loop_names, swept


def import_time(body, names, loop_names=(), swept=()):
    """Yield each statement that runs at import time, in source order: the module body, and what sits in its if, for, while, try, with
    and class blocks. A def is skipped, so is a with patch.dict block, whose changes the block undoes, and so is the branch of an
    `if` on a constant that never runs, and so is the body of `if __name__ == "__main__":`. `loop_names` holds the loop variables that iterate over a tuple naming VAR or over os.environ; `swept` is the part of it
    that iterates over os.environ. Each yield is (statement, loop_names, swept)."""
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if isinstance(node, ast.With) and any(is_patch_dict(item) for item in node.items):
            continue
        yield node, loop_names, swept
        if isinstance(node, ast.Expr) and isinstance(node.value, COMPREHENSIONS):
            yield from comprehension_elements(node, names, loop_names, swept)
        inner, inner_swept = loop_names, swept
        if isinstance(node, ast.For):
            inner, inner_swept = bind_loop(node.target, node.iter, names, loop_names, swept)
        if isinstance(node, ast.If) and isinstance(node.test, ast.Constant):
            blocks = [node.body if node.test.value else node.orelse]
        elif isinstance(node, ast.If) and is_main_guard(node):
            blocks = [node.orelse]
        else:
            blocks = [getattr(node, field, None) or [] for field in ("body", "orelse", "finalbody")]
        for block in blocks:
            yield from import_time(block, names, inner, inner_swept)
        for handler in getattr(node, "handlers", None) or []:
            yield from import_time(handler.body, names, inner, inner_swept)


def file_problem(path, rel):
    """One problem string for the test file at `path`, else None."""
    try:
        with open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read(), filename=path)
    except (OSError, SyntaxError, ValueError) as error:  # ValueError: a null byte; UnicodeDecodeError is one
        return "%s: does not parse (%s), so it is not known to set %s" % (rel, error.__class__.__name__, VAR)
    names = Names(tree, os.path.dirname(os.path.abspath(path)))
    if any(isinstance(node, ast.FunctionDef) and node.name == "setUpModule" and names.sets_var(node, ()) for node in tree.body):
        return None
    # The import-time events in source order: ("remove", line, swept) or ("set", line, False). The file is bad when a removal follows
    # the last set. A removal is swept when it names only a loop variable over os.environ: the check cannot tell which name it removes.
    events = []
    for node, loop_names, swept in import_time(tree.body, names):
        line = names.removal_line(node, loop_names)
        if line:
            events.append(("remove", line, names.removal_line(node, tuple(name for name in loop_names if name not in swept)) is None))
        elif not isinstance(node, COMPOUND) and names.sets_var(node, loop_names):
            events.append(("set", getattr(node, "lineno", 0), False))
    last_set = max([index for index, event in enumerate(events) if event[0] == "set"], default=-1)
    unset = [(line, swept) for kind, line, swept in events[last_set + 1:] if kind == "remove"]
    if not unset:
        return None
    line, swept = min(unset)
    if swept:
        return "%s:%d: sweeps os.environ at import, which may remove %s, and never sets it after, so its cases may read the real ~/.claude" \
            % (rel, line, VAR)
    return "%s:%d: removes %s at import and never sets it after, so its cases read the real ~/.claude" % (rel, line, VAR)


def problems(root):
    """One string per test_*.py under `root` that removes VAR at import and does not set it after, each starting with `<path>:`."""
    found = []
    _CONSTANTS.clear()
    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(name for name in dirs if not name.startswith(".") and name not in SKIP_DIRS)
        for name in sorted(files):
            if name.startswith("test_") and name.endswith(".py"):
                path = os.path.join(folder, name)
                problem = file_problem(path, os.path.relpath(path, root).replace(os.sep, "/"))
                if problem:
                    found.append(problem)
    return found


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    if argv[:1] == ["--root"] and len(argv) > 1:
        root = argv[1]
    found = problems(root)
    for line in found:
        print(line)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
