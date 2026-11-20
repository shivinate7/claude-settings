#!/usr/bin/env python3
"""Selects the test files a draft lane PR touches, for .github/workflows/lane-touched-tests.yml.

Input (env): BASE_SHA, the PR's base commit. The checkout is at HEAD.
Output: lines written to $GITHUB_OUTPUT (stdout when unset):
  files, any                    every test either OS runs (the union), and whether it is non-empty
  files_windows, any_windows    the tests the Windows job runs
  files_macos, any_macos        the tests the macOS job runs, less the shared hooks suites (MACOS_SHARED, read for MACOS_WORDS), which are skipped with a reason
  matrix                        {"include": [{"os", "files"}]}, one entry per OS that has tests; files is a JSON list as text
  commands_windows, commands_macos   {path: cmd} over that OS's files. cmd is the interpreter its checks.yml run line starts
                                with: sh, bash, node, node --test, python, python3, powershell or pwsh (mod-tests.sh files:
                                `node` for a mods test, `node --test` for a map skill test). Each OS names its own, so a
                                test run as `python` on Windows and `python3` on macOS has both.
Stdout also names every touched path and what became of it, so the run log shows each decision.

A touched path selects:
  a test file (patterns TEST_PATTERNS)                                       -> itself
  dir/x.py                                                                   -> dir/test_x.py, and every tracked test_*.py (any
                                                                               folder) that imports the module x, by `import x` or
                                                                               `from x import ...`, even inside a function, or by a
                                                                               loader call that hooks/mutate_guard.py
                                                                               `_load_profile` reads (import_module, a loader path
                                                                               that ends in x.py as a string, a constant, a join, an
                                                                               `or` or if-else default). The
                                                                               imports are read with `ast`, so a name in a comment
                                                                               or a string selects nothing. A test it cannot read
                                                                               or parse is selected: unknown is not skip.
  dir/x.sh                                                                   -> dir/test_x.sh, dir/x.test.sh
  dir/x.ps1                                                                  -> dir/x.test.ps1, dir/x-*.test.ps1
  any non-.md, non-test path under mods/<mod>/                               -> every *.test.mjs, *.test.js and check.mjs under
                                                                               mods/<mod>/, not node_modules (that mod's only:
                                                                               mod-tests.sh runs every mod's, each with `node`)
  dir/x.mjs, dir/x.js                                                        -> dir/x.test.{mjs,js}, dir/tests/x.test.{mjs,js}; x.mjs also dir/test_x.mjs
  any non-.md path under skills/plain-english-map/                           -> every test in its tests folder
  any non-.md, non-test path under a folder named tests                      -> every test under that folder
Each selected test then lands in one of these places, each printed with its reason, none dropped silently:
  HEAVY           the batch shards it in its own jobs; running it per lane push is a cost blow-up
                  A touched HEAVY .py suite is read with `ast` first, and the job exits 1 when it uses a POSIX_ONLY name outside a guard
                  that excludes Windows, on a line the change adds (see posix_offences). No lane run reaches a HEAVY suite on Windows, so this is its only read.
  NEEDS_SETUP     needs a browser or a tool this workflow does not install, or runs on one OS only
  per OS          listed for an OS when a job of checks.yml at HEAD runs on that OS and names it (see os_runs);
                  skipped on each other OS, and on both with "no CI job runs it" when no Windows or macOS job names it
An unreadable diff (no BASE_SHA, git fails) or a checks.yml it cannot read exits 1 and writes no output
(decision ci-unknown-is-red). A checks.yml it cannot read is a runs-on it cannot place, no jobs, a tab indent, a
flow-style step (`- {`), a one-line `steps: [...]`, a `defaults:` block, or a run line that names a test after anything but
an interpreter (`FOO=x node t`, `cd a && node t`) or after a chain (`&&`, `;`, `|` outside quotes: `node a.mjs && node t`).
The exit names the line. A trailing backslash joins a line to the next. A step with `shell: powershell` or `pwsh` is read
with each backslash as a slash, and a trailing backtick joins its line to the next.
"""
import ast
import fnmatch
import importlib.util
import json
import os
import re
import subprocess
import sys

# Test-file name patterns, matched on the file's own name.
TEST_PATTERNS = ("*.test.mjs", "*.test.js", "test_*.mjs", "test_*.py", "test_*.sh", "*.test.sh", "*.test.ps1")

# The workflow whose jobs decide each OS's list. It is read from the HEAD commit, so a lane that moves a test between
# jobs is judged by its own checks.yml.
CI_PATH = ".github/workflows/checks.yml"
# runs-on prefix -> the OS word the lists and log lines use. A Linux runner runs nothing here. Any other runner is
# unknown, and exits 1.
OS_RUNNERS = {"windows-": "windows", "macos-": "macos"}
LINUX_RUNNERS = ("ubuntu-",)
# The runner scripts a run text may name in place of a test path, with the tests each phase runs and the command that
# script runs each with (script -> {argument: ((glob, cmd), ...)}; "" is no argument). Read from
# .github/scripts/mod-tests.sh: phase_mods runs `node <f>` on every *.test.mjs, *.test.js and check.mjs under mods/, and
# phase_skill runs `node --test` in the map skill's tests folder. A change to that script's file lists changes this table
# and MOD_CHECK too.
MOD_CHECK = "check.mjs"
MODS_TESTS = (("mods/*.test.mjs", "node"), ("mods/*.test.js", "node"), (f"mods/*/{MOD_CHECK}", "node"))
SKILL_TESTS = (("skills/plain-english-map/tests/*.test.mjs", "node --test"),
               ("skills/plain-english-map/tests/*.test.js", "node --test"))
RUNNER_SCRIPTS = {
    ".github/scripts/mod-tests.sh": {"mods": MODS_TESTS, "skill": SKILL_TESTS, "": MODS_TESTS + SKILL_TESTS},
}

# The suites checks.yml runs in shard jobs or under a step cap of its own (glob -> reason).
HEAVY = {
    "hooks/test_guard.py": "heavy: runs in the batch's shard jobs (GUARD_SHARD)",
    "tests/guard/*": "heavy: section files of hooks/test_guard.py, which runs in the batch's shard jobs (GUARD_SHARD)",
    "merge/test_merge.py": "heavy: runs in the batch's shard jobs (MERGE_SHARD)",
    "janitor/test_sweep.py": "heavy: runs in the batch's checks-windows-sweep job",
    "hooks/test_install_src.sh": "heavy: runs in the batch's shell-macos job under its own step cap",
}

# The POSIX-only names a HEAVY suite may use only inside a guard that excludes Windows (module -> attribute names).
POSIX_ONLY = {
    "os": ("killpg", "getpgid", "setsid"),
    "signal": ("SIGHUP", "SIGKILL", "SIGQUIT", "SIGUSR1", "SIGUSR2"),
}

# Suites that need a browser or a tool this workflow does not install (glob -> reason).
NEEDS_SETUP = {
    "*/tests/page.test.mjs": "needs Playwright and Chromium; runs in checks-shoot (roadmap) or checks-waiting-page (waiting page) on Linux only",
    "skills/waiting-page/tests/test_check_designs.mjs": "needs Playwright and Chromium; runs in checks-waiting-page on Linux only",
    "lint/test_shoot.mjs": "needs Playwright and Chromium; runs in checks-shoot on Linux only",
    "lint/test_ios_ship.sh": "needs macOS tooling (bin/ios-ship); runs in shell-macos only",
    "lint/test_sim_test.sh": "needs macOS tooling (bin/sim-test); runs in shell-macos only",
}

# R61 part 4: the macOS leg of a lane runs a test only when its subject is macOS. A shared suite (one that runs the same on every
# OS) proves nothing more on a lane push, and the batch's macOS run covers it. A hooks test is shared by default (MACOS_SHARED,
# glob -> reason), unless its own text names a macOS thing (MACOS_WORDS: the file is read) or MACOS_SUBJECT names it. An
# unreadable file and a test no list covers stay on the macOS leg: unknown is not skip. ci-scope.sh's checks_macos flag is too
# wide to define this (any hooks/ edit sets it), so these lists are the one home. A product file selects its test through
# candidates(), so a change to janitor/install_launchd.py reaches janitor/test_install_launchd.py.
MACOS_SHARED = {
    "hooks/test_*.py": "a hook suite with no macOS word in its text runs the same on every OS",
}
# The words that make a test a macOS subject: darwin (also a faked Darwin uname), macos, launchd and xcrun.
MACOS_WORDS = re.compile(r"darwin|macos|launchd|xcrun", re.IGNORECASE)
# A test that runs code with a darwin arm or macOS-only tooling. It stays on the macOS leg even inside a shared glob.
MACOS_SUBJECT = {
    "janitor/test_install_launchd.py": "tests the launchd installer",
    "janitor/test_session_end_sweep.py": "tests the session-end sweep, whose process-start read has a darwin arm",
    "hooks/test_guard_load_os.py": "checks the guard's load reader against the macOS tools (its darwin arm)",
    "lint/test_rm_shim.py": "tests the rm shim over the real macOS rm (its darwin arm)",
    "hooks/test_sim_boot_record.py": "tests the iOS simulator boot record, which reads macOS launchd state",
}


def shared_on_macos(test):
    """The reason `test` is a shared suite that the macOS leg skips, or None when it stays. It stays when MACOS_SUBJECT names
    it, when its own text has a MACOS_WORDS word, and when the file cannot be read (unknown is not skip)."""
    why = reason(test, MACOS_SHARED)
    if not why or reason(test, MACOS_SUBJECT):
        return None
    try:
        with open(test, encoding="utf-8", errors="replace") as f:
            return None if MACOS_WORDS.search(f.read()) else why
    except OSError:
        return None

MAP_DIR = "skills/plain-english-map/"
MAP_TESTS = MAP_DIR + "tests/"


def fail(message):
    print(f"touched-tests: {message}", file=sys.stderr)
    sys.exit(1)


def git(*args):
    r = subprocess.run(["git", *args], capture_output=True)
    if r.returncode:
        fail(f"git {args[0]} failed: {r.stderr.decode(errors='replace').strip()}")
    return r.stdout.decode(errors="replace")


def is_test(path):
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in TEST_PATTERNS)


def reason(path, table):
    for glob, why in table.items():
        if fnmatch.fnmatchcase(path, glob):
            return why
    return None


def _dotted(node):
    """The dotted name an Attribute or Name chain spells ("os.name"), or None."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    return ".".join([node.id, *reversed(parts)])


def _constants(node):
    """The values of a constant, or of a tuple, list or set of constants. None when any element is not a constant."""
    items = node.elts if isinstance(node, (ast.Tuple, ast.List, ast.Set)) else [node]
    if all(isinstance(i, ast.Constant) for i in items):
        return [i.value for i in items]
    return None


def on_windows(test, env=None):
    """What the condition `test` evaluates to on Windows (os.name "nt", sys.platform "win32"): True, False, or None when it is
    not a plain os.name or sys.platform test. Three-valued, so `and`, `or` and `not` carry the unknown through. An `if` body
    runs only when its condition is true, so the body is safe on Windows when this is False, and the else arm when it is
    True. skipIf skips when true, so it excuses a suite when this is True; skipUnless, when False. Evaluating on Windows,
    never matching a spelling, is what makes the direction count: skipIf(os.name == "posix") is False here.
    `env` is {name: expression} for the flags in scope (scope_env): a name in it is read as its expression."""
    env = env or {}
    if isinstance(test, ast.Name):
        if test.id not in env:
            return None
        return on_windows(env[test.id], {k: v for k, v in env.items() if k != test.id})
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        inner = on_windows(test.operand, env)
        return None if inner is None else not inner
    if isinstance(test, ast.BoolOp):
        seen = [on_windows(v, env) for v in test.values]
        decisive = isinstance(test.op, ast.Or)
        if decisive in seen:
            return decisive
        return None if None in seen else not decisive
    if isinstance(test, ast.Compare) and len(test.ops) == 1 and len(test.comparators) == 1:
        windows = {"os.name": "nt", "sys.platform": "win32"}.get(_dotted(test.left))
        values = _constants(test.comparators[0])
        if windows is None or values is None:
            return None
        if isinstance(test.ops[0], (ast.Eq, ast.In)):
            return windows in values
        if isinstance(test.ops[0], (ast.NotEq, ast.NotIn)):
            return windows not in values
        return None
    if (isinstance(test, ast.Call) and isinstance(test.func, ast.Attribute) and test.func.attr == "startswith"
            and _dotted(test.func.value) == "sys.platform" and len(test.args) == 1 and not test.keywords):
        prefixes = _constants(test.args[0])
        if prefixes is None or not all(isinstance(p, str) for p in prefixes):
            return None
        return any("win32".startswith(p) for p in prefixes)
    return None


def skip_decorator_excuses(decorator, env=None):
    """True when `decorator` is unittest's skipIf or skipUnless with a condition that skips the test on Windows."""
    if not isinstance(decorator, ast.Call) or not decorator.args:
        return False
    name = (_dotted(decorator.func) or "").rsplit(".", 1)[-1]
    if name not in ("skipIf", "skipUnless"):
        return False
    return on_windows(decorator.args[0], env) is (name == "skipIf")


def scope_env(outer, body, params=(), poisoned=frozenset()):
    """The flags in scope inside a module or def body: `outer`, less each name this scope binds, plus each name this scope
    binds once, by a plain `name = <expression>` (or an annotated one), as {name: expression}. A name bound twice, by a loop,
    an import, a def or a global in any def (`poisoned`) is no flag. Bodies of nested defs, classes and lambdas are their own
    scopes. on_windows() reads a flag's expression, so only an os.name or sys.platform test gives a value."""
    counts, bound = {}, {}

    def bind(name, n=1):
        counts[name] = counts.get(name, 0) + n

    def visit(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bind(child.name)
                continue
            if isinstance(child, ast.Lambda):
                continue
            if isinstance(child, ast.Name) and isinstance(child.ctx, (ast.Store, ast.Del)):
                bind(child.id)
            elif isinstance(child, (ast.Import, ast.ImportFrom)):
                for alias in child.names:
                    bind((alias.asname or alias.name).split(".")[0])
            elif isinstance(child, (ast.Global, ast.Nonlocal)):
                for name in child.names:
                    bind(name, 2)
            elif isinstance(child, ast.Assign) and len(child.targets) == 1 and isinstance(child.targets[0], ast.Name):
                bound[child.targets[0].id] = child.value
            elif isinstance(child, ast.AnnAssign) and child.value is not None and isinstance(child.target, ast.Name):
                bound[child.target.id] = child.value
            visit(child)

    for stmt in body:
        visit(ast.Module(body=[stmt], type_ignores=[]))
    for name in params:
        bind(name, 2)
    env = {k: v for k, v in outer.items() if k not in counts}
    env.update({k: v for k, v in bound.items() if counts.get(k) == 1 and k not in poisoned})
    return env


def exits(stmts):
    """True when the statement list `stmts` always ends the enclosing function, module, test or loop pass on reaching it: a
    return, raise, continue or break, a call to skipTest (any receiver), sys.exit, exit or quit, or an `if` whose two arms both exit."""
    for stmt in stmts:
        if isinstance(stmt, (ast.Return, ast.Raise, ast.Continue, ast.Break)):
            return True
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            func = stmt.value.func
            if (isinstance(func, ast.Attribute) and func.attr == "skipTest") or _dotted(func) in ("sys.exit", "exit", "quit"):
                return True
        if isinstance(stmt, ast.If) and exits(stmt.body) and exits(stmt.orelse):
            return True
    return False


def posix_offences(path, source, added=None):
    """One `path:line: message` string for each POSIX_ONLY name that `source` uses outside a guard that excludes Windows, and
    one for a source that cannot be parsed (unknown is red, not skip). A guard is a def or class under skipIf or skipUnless
    that skips Windows, an `if` body whose condition is false on Windows, or the else arm of an `if` whose condition is true
    on Windows, or each statement after an `if` whose Windows arm always exits (see exits). A guard covers everything nested in
    it. A name bound once to an os.name or sys.platform test is read as that test (scope_env). The source is read with `ast`, so a name in a comment or a string
    counts for nothing. A name is `os.killpg`, `from os import killpg` (the import line is the offence: on Windows the import
    itself raises) or `s.SIGHUP` under `import signal as s`. With `added` (a set of line numbers), only a name on such a line
    counts: a call already on the base is an existing offence, and this change does not own it."""
    try:
        tree = ast.parse(source, filename=path)
    except (SyntaxError, ValueError, RecursionError) as e:
        return [f"{path}:{getattr(e, 'lineno', None) or 1}: cannot parse this heavy suite, so its POSIX-only calls are unread ({e})"]
    found = []
    modules = {m: m for m in POSIX_ONLY}
    poisoned = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update({a.asname: a.name for a in node.names if a.asname and a.name in POSIX_ONLY})
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            poisoned.update(node.names)

    def hit(line, name):
        if added is None or line in added:
            found.append(f"{path}:{line}: {name} is POSIX-only and has no guard that excludes Windows (skipIf on os.name == 'nt', "
                         "skipUnless on os.name != 'nt', an if on os.name or sys.platform, or an earlier `if` on Windows that "
                         "returns, raises, continues, calls skipTest or sys.exit)")

    def block(stmts, guarded, env):
        """Walk a statement list in order. An `if` whose Windows arm always exits guards each statement after it in this list."""
        for stmt in stmts:
            walk(stmt, guarded, env)
            if not guarded and isinstance(stmt, ast.If):
                verdict = on_windows(stmt.test, env)
                arm = stmt.body if verdict is True else stmt.orelse if verdict is False else None
                guarded = bool(arm) and exits(arm)

    def walk(node, guarded, env):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            guarded = guarded or any(skip_decorator_excuses(d, env) for d in node.decorator_list)
            if isinstance(node, ast.ClassDef):
                # A class body binds names that its methods do not read, so keep only the flags it leaves alone.
                inner = scope_env(env, node.body, poisoned=poisoned)
                env = {k: v for k, v in env.items() if inner.get(k) is v}
            else:
                args = node.args
                names = [a.arg for a in args.posonlyargs + args.args + args.kwonlyargs] + [a.arg for a in (args.vararg, args.kwarg) if a]
                env = scope_env(env, node.body, names, poisoned)
        if isinstance(node, ast.If):
            verdict = on_windows(node.test, env)
            walk(node.test, guarded, env)
            block(node.body, guarded or verdict is False, env)
            block(node.orelse, guarded or verdict is True, env)
            return
        if not guarded and isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            module = modules.get(node.value.id)
            if module and node.attr in POSIX_ONLY[module]:
                hit(node.lineno, f"{module}.{node.attr}")
        if not guarded and isinstance(node, ast.ImportFrom) and node.level == 0:
            for alias in node.names:
                if alias.name in POSIX_ONLY.get(node.module, ()):
                    hit(node.lineno, f"{node.module}.{alias.name}")
        for field, value in ast.iter_fields(node):
            if isinstance(value, list) and value and all(isinstance(v, ast.stmt) for v in value):
                block(value, guarded, env)
            elif isinstance(value, list):
                for child in value:
                    if isinstance(child, ast.AST):
                        walk(child, guarded, env)
            elif isinstance(value, ast.AST):
                walk(value, guarded, env)

    try:
        block(tree.body, False, scope_env({}, tree.body, poisoned=poisoned))
    except RecursionError as e:
        return [f"{path}:1: cannot read this heavy suite, so its POSIX-only calls are unread ({e})"]
    return found


def added_lines(base, path):
    """The set of line numbers the change from `base` to HEAD adds or rewrites in `path`, from the zero-context diff hunks."""
    added = set()
    for start, count in re.findall(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@", git("diff", "-U0", "--no-renames", f"{base}...HEAD", "--", path),
                                   re.MULTILINE):
        added.update(range(int(start), int(start) + (1 if count == "" else int(count))))
    return added


def heavy_offences(test, base):
    """posix_offences() of the touched HEAVY .py suite `test`, read from the checkout, for the lines the change from `base` adds.
    An unreadable file is an offence."""
    try:
        with open(test, "rb") as f:
            return posix_offences(test, f.read(), added_lines(base, test))
    except OSError as e:
        return [f"{test}:1: cannot read this heavy suite, so its POSIX-only calls are unread ({e})"]


# {(root, test): (stat key, module names)}, kept while the file's size and mtime hold. A run asks about each tracked test once per
# touched .py path, and this parses it once.
_IMPORTS = {}

# The scanner for "which module does this test load by a loader call" has one home, hooks/mutate_guard.py (`_load_profile`: import_module,
# __import__, spec_from_file_location, SourceFileLoader, run_path, constants, joins, `or` and if-else defaults, parameters). It is
# stdlib-only, so this script loads it by path from the checkout it sits in.
_HOME = None


def load_profile(source):
    """`_load_profile` of hooks/mutate_guard.py for `source`: (import stems, loader basenames, read basenames)."""
    global _HOME
    if _HOME is None:
        hooks = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "hooks")
        sys.path.insert(0, hooks)
        spec = importlib.util.spec_from_file_location("mutate_guard_home", os.path.join(hooks, "mutate_guard.py"))
        _HOME = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_HOME)
    return _HOME._load_profile(source)


def loaded_modules(source):
    """The module names the test text `source` loads by a loader call or an import by name: a loader path that ends in x.py names x."""
    stems, loads, _reads = load_profile(source)
    return set(stems) | {base[:-3] for base in loads if base.endswith(".py")}


def imported_modules(test, root):
    """The top-level module names the Python test `test` imports, or None when it cannot be read or parsed. `import a.b` names a,
    `from a import b` names a, and `from . import a` names a. A loader call names its module too: `import_module("a.b")` names a,
    and `spec_from_file_location(name, path)` names the stem of a .py path. The parser sees every import in the file, a lazy one
    inside a function included, and no name in a comment or a string."""
    full = os.path.join(root, *test.split("/"))
    try:
        info = os.stat(full)
        key = (info.st_size, info.st_mtime_ns)
        cached = _IMPORTS.get((root, test))
        if cached and cached[0] == key:
            return cached[1]
        with open(full, "rb") as f:
            raw = f.read()
        tree = ast.parse(raw, filename=test)
    except (OSError, SyntaxError, ValueError):
        return None
    names = loaded_modules(raw.decode("utf-8", errors="replace"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.partition(".")[0])
            elif node.level:
                names.update(alias.name.partition(".")[0] for alias in node.names)
    _IMPORTS[(root, test)] = (key, frozenset(names))
    return _IMPORTS[(root, test)][1]


def importers(module, tracked, root):
    """The tracked Python tests, in any folder, that import the module named `module`. A test whose imports cannot be read is
    listed: a test the selector cannot read must not read as a test that does not import it."""
    found = set()
    for t in tracked:
        if t.endswith(".py") and is_test(t):
            names = imported_modules(t, root)
            if names is None or module in names:
                found.add(t)
    return found


def candidates(path, tracked, root="."):
    """The test files `path` selects, from the tracked paths at HEAD. `root` is the checkout the tracked paths sit in: the selector
    reads each test's imports there, not in the current folder."""
    # A file that a HEAVY glob names is selected even when its name is no test name (a section file), so the log skips it with its reason.
    if is_test(path) or reason(path, HEAVY):
        return {path}
    found = set()
    directory, _, name = path.rpartition("/")
    prefix = directory + "/" if directory else ""
    stem, dot, ext = name.rpartition(".")
    if dot and ext == "py":
        found.add(f"{prefix}test_{stem}.py")
        found |= importers(stem, tracked, root)
    elif dot and ext == "sh":
        found.add(f"{prefix}test_{stem}.sh")
        found.add(f"{prefix}{stem}.test.sh")
    elif dot and ext == "ps1":
        found.add(f"{prefix}{stem}.test.ps1")
        found |= {t for t in tracked if t.rpartition("/")[0] == directory
                  and fnmatch.fnmatchcase(t.rpartition("/")[2], f"{stem}-*.test.ps1")}
    elif dot and ext in ("mjs", "js"):
        for test_ext in ("mjs", "js"):
            found.add(f"{prefix}{stem}.test.{test_ext}")
            found.add(f"{prefix}tests/{stem}.test.{test_ext}")
        if ext == "mjs":
            found.add(f"{prefix}test_{stem}.mjs")
    if not path.endswith(".md"):
        if path.startswith(MAP_DIR):
            found |= {t for t in tracked if t.startswith(MAP_TESTS) and is_test(t)}
        parts = path.split("/")
        if parts[0] == "mods" and len(parts) > 2 and "node_modules" not in parts:
            mod = "/".join(parts[:2]) + "/"
            found |= {t for t in tracked if t.startswith(mod) and "node_modules" not in t.split("/")
                      and (t.endswith((".test.mjs", ".test.js")) or t.rpartition("/")[2] == MOD_CHECK)}
        if "tests" in parts[:-1]:
            folder = "/".join(parts[: parts.index("tests") + 1]) + "/"
            found |= {t for t in tracked if t.startswith(folder) and is_test(t)}
    return {c for c in found if c in tracked}


# A YAML mapping key line: indent, an optional "- " list dash, the key, and the rest of the line.
KEY_LINE = re.compile(r"^(?P<indent> *)(?P<dash>- +)?(?P<key>[A-Za-z0-9_.-]+):(?:[ \t]+(?P<value>.*?))?[ \t]*$")


def one_line_scalar(value):
    """A one-line YAML scalar's text, with its comment cut and its quotes removed; None when it is not one."""
    value = (value or "").strip()
    if value[:1] in ("'", '"'):
        end = value.find(value[0], 1)
        if end < 0:
            return None
        tail = value[end + 1:]
        # Only whitespace, or a comment that follows whitespace, may come after the closing quote.
        return value[1:end] if not tail.strip() or (tail[0] in " \t" and tail.strip().startswith("#")) else None
    value = re.split(r"[ \t]#", value, maxsplit=1)[0].strip()
    return value if value and value[0] not in "#[{|>&*!" and "${{" not in value else None


def ci_jobs(text):
    """{job: (runs-on, [(line, run text, line join)])} for each job under the top-level `jobs:` of a workflow. A hand
    parser: the runner image has no YAML module. `line join` is the step shell's line continuation. A run text is the line's
    value plus every deeper line after it, so a block scalar (`run: |`), a folded one and a plain continuation are each
    read whole. `line` is the number of the `run:` key's line, so the nth line of its text is line + n - 1. A job this cannot read exits 1: a job read as no job would drop its
    tests in silence."""
    jobs, job, job_indent, prop_indent, in_jobs = {}, None, None, None, False
    in_steps, step_indent, step_col, step_no = False, None, None, 0
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if line[indent] == "\t":
            fail(f"{CI_PATH} line {i} is indented with a tab")
        m = KEY_LINE.match(line)
        if indent == 0:
            if m and m["key"] == "defaults":
                fail(f"{CI_PATH} line {i} sets workflow-level defaults, which this cannot read: a default shell would change how a step reads")
            in_jobs = bool(m) and m["key"] == "jobs" and not m["dash"] and one_line_scalar(m["value"]) is None
            job = None
            continue
        if not in_jobs:
            continue
        if job_indent is None:
            job_indent = indent
        if indent < job_indent:
            fail(f"{CI_PATH} line {i} sits between the top level and the jobs: {line.strip()!r}")
        if indent == job_indent:
            if not m or m["dash"] or m["value"]:
                fail(f"{CI_PATH} line {i} is not a job name: {line.strip()!r}")
            job, prop_indent = m["key"], None
            if job in jobs:
                fail(f"{CI_PATH} names job {job} twice")
            jobs[job] = [None, [], {}]
            in_steps, step_indent, step_col, step_no = False, None, None, 0
            continue
        if prop_indent is None:
            prop_indent = indent
        if indent == prop_indent and m and not m["dash"]:
            in_steps = m["key"] == "steps"
            step_indent, step_col, step_no = None, None, 0
            if m["key"] == "defaults":
                fail(f"{CI_PATH} line {i} sets job {job}'s defaults, which this cannot read: a default shell would change how a step reads")
            if in_steps and m["value"] and not m["value"].startswith("#"):
                fail(f"{CI_PATH} line {i} writes job {job}'s steps on one line, which this cannot read: {line.strip()!r}")
        if in_steps and re.match(r"-[ \t]+\{", line.lstrip(" ")) and step_indent in (None, indent):
            fail(f"{CI_PATH} line {i} is a flow-style step, which this cannot read; the job {job} would be misread: "
                 f"{line.strip()!r}")
        if not m:
            continue
        key_col = indent + len(m["dash"] or "")
        if in_steps and m["dash"] and step_indent in (None, indent):
            step_indent, step_col, step_no = indent, key_col, step_no + 1
        if m["key"] == "runs-on" and indent == prop_indent and not m["dash"]:
            runner = one_line_scalar(m["value"])
            if runner is None or jobs[job][0] is not None:
                fail(f"{CI_PATH} job {job}: cannot read runs-on {m['value']!r}; the OS lists would be unknown")
            jobs[job][0] = runner
        elif m["key"] == "shell" and in_steps and key_col == step_col:
            jobs[job][2][step_no] = one_line_scalar(m["value"])
        elif m["key"] == "run":
            start, body = i, [m["value"] or ""]
            while i < len(lines) and (not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip(" ")) > key_col):
                body.append(lines[i])
                i += 1
            jobs[job][1].append((step_no if in_steps else 0, start, "\n".join(body)))
    if not jobs:
        fail(f"{CI_PATH} has no jobs this can read")
    for name, (runner, _, _) in jobs.items():
        if runner is None:
            fail(f"{CI_PATH} job {name} has no runs-on this can read; the OS lists would be unknown")
    # A powershell step names a path with a backslash (lint\\test_x.py). Read it as the slash form the lists use. Its
    # line continuation is a trailing backtick; a bash step's is a trailing backslash.
    out = {}
    for name, (runner, runs, shells) in jobs.items():
        out[name] = (runner, [])
        for step, start, text in runs:
            if shells.get(step) in POWERSHELLS:
                out[name][1].append((start, text.replace("\\", "/"), "`"))
            else:
                out[name][1].append((start, text, "\\"))
    return out


POWERSHELLS = ("powershell", "pwsh")


def os_of(job, runner):
    for prefix, word in OS_RUNNERS.items():
        if runner.startswith(prefix):
            return word
    if runner.startswith(LINUX_RUNNERS):
        return None
    fail(f"{CI_PATH} job {job} runs on {runner!r}, a runner this cannot place on an OS")


def name_match(text, path):
    """The match of `path` named as a whole path in `text`, not as part of a longer one; None when it is not named."""
    return re.search(rf"(?<![\w./\\-])(?:\./)?{re.escape(path)}(?![\w./\\-])", text)


# The interpreters a run line may start with. The command a test runs with is this word (`node --test` for node's runner).
INTERPRETERS = ("sh", "bash", "node", "python", "python3", "powershell", "pwsh")
# The directories an interpreter may be named from by absolute path (`/bin/bash`). Only these exact forms read as the
# bare interpreter; any other absolute path (`/tmp/bash`) may be a different program, so it is not read.
INTERPRETER_DIRS = ("/bin", "/usr/bin", "/usr/local/bin")


def interpreter_word(word):
    """The bare interpreter `word` names, as `bash` or as `<dir>/bash` with a dir of INTERPRETER_DIRS; None otherwise."""
    directory, _, name = word.rpartition("/")
    if name in INTERPRETERS and (not directory and "/" not in word or directory in INTERPRETER_DIRS):
        return name
    return None


def chain_before(prefix):
    """The first chain operator (`&&`, `;`, `|`) in `prefix` outside quotes, or None. `||` reads as `|`."""
    quote = None
    for k, ch in enumerate(prefix):
        if quote:
            quote = None if ch == quote else quote
        elif ch in "'\"":
            quote = ch
        elif ch in ";|" or prefix.startswith("&&", k):
            return prefix[k:k + 2] if ch == "&" else ch
    return None


def line_command(start, text, match, join):
    """The command the run line that names the path `match` found starts with: a word of INTERPRETERS, or `node --test`
    for node's test runner. `start` is the line number of text's first line. The line is the logical line, so a
    trailing `join` (a backslash, or a backtick in a powershell step) joins the next line. Anything else before the
    interpreter (an env prefix, `cd a &&`, `if`, the path itself), or a chain between the interpreter and the path,
    exits 1 naming the line: the run could not be reproduced from its command word alone."""
    rows = text.split("\n")
    index = text.count("\n", 0, match.start())
    first = index
    while first > 0 and rows[first - 1].rstrip().endswith(join):
        first -= 1
    column = match.start() - (text.rfind("\n", 0, match.start()) + 1)
    joined = [row.rstrip().removesuffix(join) for row in rows[first:index]]
    words = " ".join(joined + [rows[index]]).split()
    chain = chain_before(" ".join(joined + [rows[index][:column]]))
    if chain:
        fail(f"{CI_PATH} line {start + first} names a test after a chain ({chain!r}), so its command cannot be read from "
             f"the line's first word: {' '.join(words)!r}")
    interpreter = interpreter_word(words[0]) if words else None
    if interpreter is None:
        fail(f"{CI_PATH} line {start + first} names a test after {words[0] if words else 'nothing'!r}, not an interpreter "
             f"({', '.join(INTERPRETERS)}), so its command cannot be read: {' '.join(words)!r}")
    return "node --test" if interpreter == "node" and words[1:2] == ["--test"] else interpreter


def script_globs(text):
    """The (test glob, command) pairs of each runner script (RUNNER_SCRIPTS) that `text` names, by the phase argument
    it passes."""
    globs = []
    for script, phases in RUNNER_SCRIPTS.items():
        for m in re.finditer(rf"(?<![\w./\\-])(?:\./)?{re.escape(script)}(?![\w./\\-])(?:[ \t]+(\w+))?", text):
            arg = m[1] or ""
            if arg not in phases:
                fail(f"{CI_PATH} runs {script} with argument {arg!r}, which names no phase this knows")
            globs.extend(phases[arg])
    return globs


def os_runs():
    """{OS word: [(line, run text, line join)]} for the Windows and macOS jobs of checks.yml at HEAD."""
    texts = {word: [] for word in OS_RUNNERS.values()}
    for job, (runner, runs) in ci_jobs(git("show", f"HEAD:{CI_PATH}")).items():
        word = os_of(job, runner)
        if word:
            texts[word].extend(runs)
    return texts


def command_for(test, runs):
    """The command a run text of `runs` runs `test` with: the interpreter its run line starts with, or the command of
    the runner script whose globs cover it. None when no run text names it. `runs` is [(line, run text, line join)]."""
    for start, text, join in runs:
        found = name_match(text, test)
        if found:
            return line_command(start, text, found, join)
        for glob, cmd in script_globs(text):
            if fnmatch.fnmatchcase(test, glob):
                return cmd
    return None


def flag(listed):
    return "true" if listed else "false"


def write_outputs(windows, macos, cmds):
    """`cmds` is {OS word: {test: command}}."""
    files = sorted(set(windows) | set(macos))
    matrix = [{"os": name, "files": json.dumps(sorted(listed))}
              for name, listed in (("windows-latest", windows), ("macos-latest", macos)) if listed]
    lines = (f"files={json.dumps(files)}\nany={flag(files)}\n"
             f"files_windows={json.dumps(windows)}\nany_windows={flag(windows)}\n"
             f"files_macos={json.dumps(macos)}\nany_macos={flag(macos)}\n"
             f"matrix={json.dumps({'include': matrix})}\n"
             f"commands_windows={json.dumps(cmds['windows'])}\ncommands_macos={json.dumps(cmds['macos'])}\n")
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with open(target, "a", encoding="utf-8", newline="\n") as f:
            f.write(lines)
    else:
        sys.stdout.write(lines)


def main():
    base = os.environ.get("BASE_SHA", "").strip()
    if not base:
        fail("BASE_SHA is not set: the diff is unknown, so no test list can be trusted")
    touched = git("diff", "--name-only", "--no-renames", "-z", f"{base}...HEAD").split("\0")
    tracked = set(git("ls-tree", "-r", "--name-only", "-z", "HEAD").split("\0")) - {""}
    touched = sorted(p for p in touched if p and p in tracked)
    selected = set()
    for path in touched:
        found = sorted(candidates(path, tracked))
        print(f"touched {path} -> {', '.join(found) if found else 'no test file maps to it'}")
        selected |= set(found)
    texts = os_runs()
    lists = {word: [] for word in texts}
    cmds = {word: {} for word in texts}
    labels = {"windows": "Windows", "macos": "macOS"}
    offences = []
    for test in sorted(selected):
        why = reason(test, HEAVY) or reason(test, NEEDS_SETUP)
        if reason(test, HEAVY) and test.endswith(".py") and test in touched:
            offences += heavy_offences(test, base)
        if why:
            print(f"skip {test}: {why}")
            continue
        for word in texts:
            cmd = command_for(test, texts[word])
            if cmd is not None:
                cmds[word][test] = cmd
        on = [word for word in texts if word in cmds and test in cmds[word]]
        if not on:
            print(f"skip {test} on {' and '.join(texts)}: no CI job runs it on Windows or macOS ({CI_PATH})")
            continue
        shared = shared_on_macos(test)
        listed = [word for word in on if word != "macos" or not shared]
        for word in texts:
            if word in listed:
                lists[word].append(test)
            elif word in on:
                del cmds[word][test]
                print(f"skip {test} on {word}: not a macOS subject ({shared}), so a lane's macOS leg leaves it to the batch's macOS run")
            else:
                print(f"skip {test} on {word}: {CI_PATH} runs it on no {labels[word]} job")
        if listed:
            print(f"run {test} on {' and '.join(listed)}")
    if offences:
        for line in offences:
            print(f"touched-tests: {line}", file=sys.stderr)
        sys.exit(1)
    write_outputs(lists["windows"], lists["macos"], cmds)


if __name__ == "__main__":
    main()
