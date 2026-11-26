# section 43830
# The write-family move (decision guard-split-by-family, the first family move). The silent-write family, its helpers and
# its three reason texts leave guard.py for hooks/guard_write.py. guard.py imports the names it uses back by name, so
# judge_shell and the other callers keep their names, and guard.<name> still resolves. These cases read the module and
# guard.py as text and tree, never by line, so a later edit that moves a line does not move the cases.
FAMILY = "write"  # the cases after this section keep the write family

WRITE_MOVED = (
    "SILENT_WRITE_SUBCOMMANDS", "QUIET_FLAG_SUBCOMMANDS", "unquoted_at", "discards_output", "tail_discards",
    "GREP_VALUE_FLAGS", "GREP_LONG_VALUE_FLAGS", "grep_inverts", "SED_VALUE_FLAGS", "sed_scripts", "sed_deletes",
    "stage_drops_lines", "quiet_write", "VALUE_FLAGS", "SUBCOMMAND_VALUE_FLAGS", "takes_next", "LISTING",
    "FETCH_VALUE_FLAGS", "read_verb", "fetch_moves_branch", "silent_write_hit", "SILENT_WRITE_REDIRECT_REASON",
    "SILENT_WRITE_FILTER_REASON", "SILENT_WRITE_QUIET_REASON",
)  # the 24 top-level units of the family, in their order in guard.py before the move
WRITE_PICKS = ("silent_write_hit", "quiet_write", "SILENT_WRITE_REDIRECT_REASON")  # names a caller reaches by name
WRITE_MODULE = os.path.join(os.path.dirname(GUARD), "guard_write.py")


def _tree(path):
    with open(path, encoding="utf-8") as handle:
        return ast.parse(handle.read(), filename=path)


def _top_level_names(path):
    """The names a module binds at its top level: each def, class and assignment target. An import is not counted:
    a name guard.py imports from guard_write is not guard.py's definition of it."""
    names = set()
    for node in _tree(path).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(target.id for target in node.targets if isinstance(target, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def _python_says(code):
    """The stdout of a fresh Python run of `code`, or the last line of its stderr when it fails."""
    run = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                         cwd=os.path.dirname(GUARD))
    if run.returncode != 0:
        return "error: %s" % (run.stderr.strip().splitlines() or ["no stderr"])[-1]
    return run.stdout.strip()


def _write_module_defines_the_family():
    if not os.path.exists(WRITE_MODULE):
        return False, "guard_write.py is not beside guard.py, so the write family has no module"
    defined = _top_level_names(WRITE_MODULE)
    absent = [name for name in WRITE_MOVED if name not in defined]
    if absent:
        return False, "guard_write.py does not define %s" % ", ".join(absent)
    return True, "guard_write.py defines all %d units of the write family" % len(WRITE_MOVED)


def _guard_no_longer_defines_the_family():
    defined = _top_level_names(GUARD)
    still = [name for name in WRITE_MOVED if name in defined]
    if still:
        return False, "guard.py still defines %s: the family is moved, not copied" % ", ".join(still)
    return True, "guard.py defines none of the %d write-family units" % len(WRITE_MOVED)


def _guard_imports_the_names_it_uses():
    """Each write-family name guard.py loads is imported from guard_write by name, so a load in guard.py resolves to the moved code."""
    tree = _tree(GUARD)
    used = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}
    imported = {alias.asname or alias.name for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module == "guard_write" for alias in node.names}
    absent = [name for name in WRITE_MOVED if name in used and name not in imported]
    if absent:
        return False, "guard.py uses %s without importing it from guard_write" % ", ".join(absent)
    return True, "guard.py imports every write-family name it uses from guard_write"


def _write_module_serves_the_picks():
    if not os.path.exists(WRITE_MODULE):
        return False, "guard_write.py is not beside guard.py, so it cannot be imported"
    code = ("import sys; sys.path.insert(0, %r); import guard_write; "
            "print([n for n in %r if not hasattr(guard_write, n)])") % (os.path.dirname(GUARD), WRITE_PICKS)
    got = _python_says(code)
    if got != "[]":
        return False, "guard_write does not serve the picks: %s" % got
    return True, "guard_write imports and serves %s" % ", ".join(WRITE_PICKS)


def _guard_reaches_the_picks_by_name():
    """guard.<name> resolves for each pick, moved or not, so a caller that reaches the name through guard keeps working."""
    code = ("import sys; sys.path.insert(0, %r); import guard; "
            "print([n for n in %r if not hasattr(guard, n)])") % (os.path.dirname(GUARD), WRITE_PICKS)
    got = _python_says(code)
    if got != "[]":
        return False, "guard.<name> does not resolve the picks: %s" % got
    return True, "guard.<name> resolves for %s" % ", ".join(WRITE_PICKS)


# LOG_CHECKS_EXTRA joined LOG_CHECKS in section 40805, so this section's checks join LOG_CHECKS directly, as the
# section 43820 checks do. Each reads text and runs one fresh Python, and builds no fixture.
WRITE_MOVE_CHECKS = (
    ("write family move: guard_write.py defines the 24 write-family units", _write_module_defines_the_family),
    ("write family move: guard.py defines none of them, so the family is moved, not copied",
     _guard_no_longer_defines_the_family),
    ("write family move: guard.py imports from guard_write each name it uses", _guard_imports_the_names_it_uses),
    ("write family move: guard_write imports in a fresh run and serves the three picks",
     _write_module_serves_the_picks),
    ("write family move: guard.<name> still resolves for the three picks", _guard_reaches_the_picks_by_name),
)
for _label, _check in WRITE_MOVE_CHECKS:
    LOG_CHECKS = LOG_CHECKS + ((_label, _check),)
    LOG_FAMILY[_label] = FAMILY
    FIXTURELESS_CHECKS.add(_check)
