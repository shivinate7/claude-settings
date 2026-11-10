#!/usr/bin/env python3
"""Fails when a product file in hooks/ or lint/ needs a newer Python than the 3.9 floor.

README.md and lint/ste_lint.py state a floor of Python 3.9 for the guards and the lint. CI runs 3.11, so a
3.10+ call passes CI and crashes a guard on a 3.9 install, where the guard fails open. The incident:
`glob.iglob(root_dir=...)` (3.10). Two passes read each product file. vermin (`-t=3.9-`, `--eval-annotations`)
finds newer calls, modules and syntax. An ast pass finds a union type `int | None`, which vermin does not flag.
Both read the source with the host's `ast`, so the host Python must be 3.9 or newer.

A product file is a .py file under hooks/ or lint/ that is not a test: a path `is_test_rel` (hooks/guard.py, the
one home of what a test path is) calls a test, or a name `_test*.py`. A `# novermin` line comment excuses its
line, in both passes; the same text in a string does not. Use it on an import that a try/except ImportError
guards.

The ast pass flags each `|` in an annotation that runs: an argument or return annotation, or a module or class
annotation. A flag OR is never a valid annotation, so any `|` there is a union type, `Foo | Bar` too. In a module
or class assignment value, or the second argument of isinstance or issubclass, it flags a `|` only when an
operand is None, a builtin type name (int, str, list and the like) or a subscript of one, so a bit-flag OR such as
`re.MULTILINE | re.DOTALL` stays silent. Under `from __future__ import annotations` the annotations are exempt.
A local annotation in a function body and a string annotation are not flagged.

    python3 lint/check_python_floor.py [--root DIR]

DIR holds hooks/ and lint/ and defaults to the repo root. The check installs its own vermin: VERMIN_PIN, the one
home of the pin, goes into a cached venv under the temp folder (floor-vermin-<pin>-py<major><minor>; env
FLOOR_VENV_DIR overrides the path). A cache counts only with its `.ok` marker, written after a good install. The
venv is built in a sibling temp folder and renamed into place, so a parallel run never sees a half-made cache; the
loser of the rename uses the winner's. Ordinary PIP_* env applies to the install. Env FLOOR_VERMIN_CMD (split like a
shell line) replaces the venv and skips the bootstrap.

Cost: first use is four process starts (venv create, its ensurepip child, pip install, the `import vermin`
probe), about 15 MB under the temp folder, and network. Later runs reuse the cache: each starts one probe
(`import vermin`) and writes nothing. A cache whose probe fails is rebuilt. A cache folder that holds other files
(neither `.ok` nor `pyvenv.cfg`) is refused, never deleted.

Exits 0 and prints nothing when clean. Exits 1 and prints one line per offending file for vermin (file and
feature) and one line per union type (file:line). Exits 2, naming the cause, when vermin cannot run or be
installed (the message names the pin), a product file cannot be read, or a file cannot be parsed: an unread file is
never clean.

Limits: vermin's tables miss `subprocess.run(process_group=)` and `datetime.fromisoformat` with a "Z" suffix, both
3.11 behaviour, so neither is caught. A symlinked folder under hooks/ or lint/ is not followed. An assignment value
or isinstance argument that joins non-builtin names (`Alias = Foo | Bar`) is not caught, since it reads the same
as a bit-flag OR.
"""
import ast
import io
import os
import re
import shlex
import shutil
import sys
import tempfile
import tokenize

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)
import guard  # noqa: E402  is_test_rel is the one home of what a test path is (hooks/guard.py)

FOLDERS = ("hooks", "lint")
TARGET = "3.9-"
VERMIN_PIN = "1.9.2"  # the one home of the vermin version
# vermin 1.9.2 ships no __main__, so `python -m vermin` fails; its console script runs main() like this.
VERMIN_CODE = "import sys; from vermin import main; sys.exit(main())"
OK_MARKER = ".ok"
FLAGS = ["-t=" + TARGET, "--eval-annotations", "--no-tips", "--violations", "--quiet", "--no-make-paths-absolute"]
CHUNK = 100  # files per vermin run, so a Windows command line stays short
TIMEOUT = 900  # interim stopgap (owner 12:11 CST Nov 10, decision ci-job-caps; ends with step time-pinned-tests-go)
BUILTIN_TYPES = frozenset(("int", "str", "float", "bool", "bytes", "list", "dict", "set", "tuple", "frozenset",
                           "type", "object"))
MARKER = re.compile(r"#\s*(?:novermin|novm)\b")  # vermin's own marker words
UNION_NEEDS = "union type `|` needs 3.10"


class Unreadable(Exception):
    """vermin could not run, or a file could not be read: exit 2."""


def product_files(root):
    """Relative paths (with /) of the product .py files under root/hooks and root/lint, sorted."""
    found = []
    for folder in FOLDERS:
        top = os.path.join(root, folder)
        if not os.path.isdir(top):
            raise Unreadable("%s is not a folder" % top)
        for base, dirs, names in os.walk(top):
            dirs[:] = [d for d in dirs if d != "__pycache__" and not d.startswith(".")]
            for name in names:
                if not name.endswith(".py"):
                    continue
                rel = os.path.relpath(os.path.join(base, name), root).replace(os.sep, "/")
                if guard.is_test_rel(rel) or name.startswith("_test"):
                    continue
                found.append(rel)
    return sorted(found)


def venv_python(venv):
    parts = ("Scripts", "python.exe") if os.name == "nt" else ("bin", "python")
    return os.path.join(venv, *parts)


def cache_dir():
    override = os.environ.get("FLOOR_VENV_DIR")
    if override:
        return os.path.abspath(override)
    name = "floor-vermin-%s-py%d%d" % ((VERMIN_PIN,) + tuple(sys.version_info[:2]))
    return os.path.join(tempfile.gettempdir(), name)


def run_step(what, cmd):
    """Run one bootstrap process. Raises Unreadable, naming the pin and the cause, when it does not succeed."""
    try:
        proc = _nowindow.run(cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=TIMEOUT)
    except (OSError, ValueError) as err:
        raise Unreadable("cannot install vermin==%s: %s cannot start: %s" % (VERMIN_PIN, what, err))
    except Exception as err:  # subprocess.TimeoutExpired
        raise Unreadable("cannot install vermin==%s: %s did not finish: %s" % (VERMIN_PIN, what, err))
    if proc.returncode != 0:
        lines = proc.stderr.strip().splitlines() or proc.stdout.strip().splitlines() or ["no output"]
        raise Unreadable("cannot install vermin==%s: %s failed (exit %d): %s"
                         % (VERMIN_PIN, what, proc.returncode, lines[-1]))


def move_aside(path):
    """Delete the folder `path` by renaming it into a fresh sibling folder first, so a parallel run never reads half
    of it. Acts only on a real folder: a file or a symlink is left alone."""
    if os.path.islink(path) or not os.path.isdir(path):
        return
    aside = tempfile.mkdtemp(prefix=os.path.basename(path) + ".old-", dir=os.path.dirname(path))
    try:
        os.rename(path, os.path.join(aside, "old"))
    except OSError:
        pass
    shutil.rmtree(aside, ignore_errors=True)


def refuse_foreign_folder(cache):
    """Raises Unreadable, naming `cache`, unless it is missing, an empty folder, a finished cache or an old venv.
    Decided by file type first: a symlink (even to a folder) or a file is never ours to rename or delete."""
    if os.path.islink(cache) or (os.path.lexists(cache) and not os.path.isdir(cache)):
        raise Unreadable("cannot install vermin==%s: the cache path %s is a file or a symlink, not a folder; name "
                         "another path in FLOOR_VENV_DIR" % (VERMIN_PIN, cache))
    if not os.path.lexists(cache):
        return
    try:
        names = os.listdir(cache)
    except OSError as err:
        raise Unreadable("cannot install vermin==%s: cannot read the cache folder %s: %s" % (VERMIN_PIN, cache, err))
    if names and OK_MARKER not in names and "pyvenv.cfg" not in names:
        raise Unreadable("cannot install vermin==%s: the cache folder %s holds other files and is neither a vermin "
                         "cache nor a venv; name another folder in FLOOR_VENV_DIR or empty it" % (VERMIN_PIN, cache))


def imports_vermin(cache):
    try:
        proc = _nowindow.run([venv_python(cache), "-c", "import vermin"], capture_output=True, timeout=TIMEOUT)
    except Exception:  # OSError, ValueError, subprocess.TimeoutExpired: the cache cannot run
        return False
    return proc.returncode == 0


def build_cache(cache):
    """Make the venv in a sibling temp folder, then rename it to `cache`. A rename lost to a parallel run keeps the
    winner's cache. Raises Unreadable when the venv cannot be made or the pin cannot be installed."""
    parent = os.path.dirname(cache)
    marker = os.path.join(cache, OK_MARKER)
    try:
        os.makedirs(parent, exist_ok=True)
        stage = tempfile.mkdtemp(prefix=os.path.basename(cache) + ".tmp-", dir=parent)
    except OSError as err:
        raise Unreadable("cannot install vermin==%s: no folder for the cache %s: %s" % (VERMIN_PIN, cache, err))
    try:
        run_step("python -m venv", [sys.executable, "-m", "venv", stage])
        run_step("pip install", [venv_python(stage), "-m", "pip", "install", "--disable-pip-version-check",
                                 "vermin==" + VERMIN_PIN])
        # pip can succeed and put vermin elsewhere (PIP_TARGET, PIP_USER): the marker needs a vermin the venv imports.
        run_step("import vermin", [venv_python(stage), "-c", "import vermin"])
        try:
            with open(os.path.join(stage, OK_MARKER), "w", encoding="utf-8") as handle:
                handle.write(VERMIN_PIN + "\n")
        except OSError as err:
            raise Unreadable("cannot install vermin==%s: cannot write the marker: %s" % (VERMIN_PIN, err))
        for _ in range(2):
            try:
                os.rename(stage, cache)
                return
            except OSError as err:
                if os.path.isfile(marker):
                    return  # a parallel run won the rename; its cache is whole
                if not os.path.exists(cache):
                    raise Unreadable("cannot install vermin==%s: cannot move the cache into place: %s"
                                     % (VERMIN_PIN, err))
                # `cache` holds no marker, so it is an incomplete leftover: move it aside, then rename again.
                refuse_foreign_folder(cache)
                move_aside(cache)
        if not os.path.isfile(marker):
            raise Unreadable("cannot install vermin==%s: cannot move the cache into place at %s" % (VERMIN_PIN, cache))
    finally:
        shutil.rmtree(stage, ignore_errors=True)


_COMMAND = []


def vermin_command():
    """The vermin command as an argv list: FLOOR_VERMIN_CMD, else the cached venv, built on first use."""
    if not _COMMAND:
        custom = os.environ.get("FLOOR_VERMIN_CMD")
        if custom:
            _COMMAND.append(shlex.split(custom))
        else:
            cache = cache_dir()
            marker = os.path.join(cache, OK_MARKER)
            refuse_foreign_folder(cache)
            if os.path.isfile(marker) and not imports_vermin(cache):
                move_aside(cache)  # a marker over a venv that cannot import vermin: rebuild
            if not os.path.isfile(marker):
                build_cache(cache)
            _COMMAND.append([venv_python(cache), "-c", VERMIN_CODE])
    return list(_COMMAND[0])


def run_vermin(root, files):
    """Run vermin on files (relative to root). -> {rel: [feature, ...]} for each file over the floor."""
    base = vermin_command()
    cmd = base + FLAGS + files
    try:
        proc = _nowindow.run(cmd, cwd=root, capture_output=True, encoding="utf-8", errors="replace",
                             timeout=TIMEOUT)
    except (OSError, ValueError) as err:
        raise Unreadable("vermin cannot start (%s): %s" % (" ".join(base), err))
    except Exception as err:  # subprocess.TimeoutExpired
        raise Unreadable("vermin did not finish: %s" % err)
    findings = {}
    current = None
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        if line[0] not in " \t":
            current = next((rel for rel in files if line.endswith(" " + rel)), None)
            if current is not None:
                findings.setdefault(current, [])
            continue
        text = line.strip()
        if current is None:
            continue
        if text.startswith("error:"):
            raise Unreadable("vermin cannot parse %s: %s" % (current, text))
        findings[current].append(text)
    if proc.returncode == 0 and not findings:
        return {}
    if proc.returncode == 1 and findings:
        return findings
    detail = (proc.stderr.strip().splitlines() or proc.stdout.strip().splitlines() or ["no output"])[-1]
    raise Unreadable("vermin failed (exit %d): %s" % (proc.returncode, detail))


def is_type_operand(node):
    """True for None, a builtin type name, or a subscript of one: an operand that makes `|` a union type."""
    if isinstance(node, ast.Subscript):
        node = node.value
        return isinstance(node, ast.Name) and node.id in BUILTIN_TYPES
    if isinstance(node, ast.Constant):
        return node.value is None
    return isinstance(node, ast.Name) and node.id in BUILTIN_TYPES


def union_lines(expr, annotation=False):
    """The line numbers of each union-type `|` inside the expression. In an annotation every `|` is a union type,
    since a flag OR is never a valid annotation; elsewhere an operand must be a type (`is_type_operand`)."""
    return {node.lineno for node in ast.walk(expr)
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr)
            and (annotation or is_type_operand(node.left) or is_type_operand(node.right))}


def marker_lines(source):
    """Line numbers that carry a real `# novermin` comment. A marker inside a string is no comment."""
    lines = set()
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.COMMENT and MARKER.match(tok.string):
            lines.add(tok.start[0])
    return lines


class Unions(ast.NodeVisitor):
    """Collects the lines where a union type runs at import or call time. `scope` is module, class or function."""

    def __init__(self, future):
        self.future = future  # `from __future__ import annotations`: annotations never run
        self.scope = "module"
        self.lines = set()

    def take(self, expr, annotation=False):
        if expr is not None:
            self.lines |= union_lines(expr, annotation)

    def function(self, node):
        if not self.future:
            args = node.args
            every = args.posonlyargs + args.args + args.kwonlyargs + [args.vararg, args.kwarg]
            for arg in every:
                if arg is not None:
                    self.take(arg.annotation, annotation=True)
            self.take(node.returns, annotation=True)
        outer, self.scope = self.scope, "function"
        for child in node.body:
            self.visit(child)
        self.scope = outer

    visit_FunctionDef = visit_AsyncFunctionDef = function

    def visit_ClassDef(self, node):
        outer, self.scope = self.scope, "class"
        for child in node.body:
            self.visit(child)
        self.scope = outer

    def visit_Assign(self, node):
        if self.scope != "function":
            self.take(node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        if self.scope != "function":
            if not self.future:
                self.take(node.annotation, annotation=True)
            self.take(node.value)
        self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id in ("isinstance", "issubclass") and len(node.args) > 1:
            self.take(node.args[1])
        self.generic_visit(node)


def union_findings(root, rel):
    """-> sorted [line, ...] of the unexcused union types in root/rel. Raises Unreadable when the file does not parse."""
    path = os.path.join(root, *rel.split("/"))
    try:
        with open(path, "rb") as handle:
            data = handle.read()
        tree = ast.parse(data, filename=rel)
        source = data.decode(tokenize.detect_encoding(io.BytesIO(data).readline)[0])
        excused = marker_lines(source)
    except (OSError, SyntaxError, ValueError, UnicodeDecodeError, tokenize.TokenError) as err:
        raise Unreadable("cannot parse %s: %s" % (rel, err))
    future = any(isinstance(n, ast.ImportFrom) and n.module == "__future__"
                 and any(a.name == "annotations" for a in n.names) for n in tree.body)
    found = Unions(future)
    found.visit(tree)
    return sorted(found.lines - excused)


def main(argv):
    root = ROOT
    args = list(argv)
    if args:
        if args[0] != "--root" or len(args) != 2:
            print("check_python_floor: usage: check_python_floor.py [--root DIR]")
            return 2
        root = os.path.abspath(args[1])
    try:
        files = product_files(root)
        problems = {}
        for start in range(0, len(files), CHUNK):
            problems.update(run_vermin(root, files[start:start + CHUNK]))
        unions = {rel: union_findings(root, rel) for rel in files}
    except Unreadable as err:
        print("check_python_floor: cannot check: %s" % err)
        return 2
    for rel in sorted(problems):
        features = problems[rel] or ["needs more than 3.9"]
        print("%s: needs more than Python 3.9: %s" % (rel, "; ".join(features)))
    for rel in sorted(unions):
        for lineno in unions[rel]:
            print("%s:%d: %s" % (rel, lineno, UNION_NEEDS))
    return 1 if problems or any(unions.values()) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
