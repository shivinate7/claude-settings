#!/usr/bin/env python3
"""Plumbing shared by hooks/mutate_guard.py and janitor/mutate_sweep.py.

Both files run the same shape of mutation test: apply one literal string replacement to a
source file, run a fixture suite against the mutated copy, and classify the result as KILLED,
SURVIVED, or WRONG CAUSE (a red suite whose FAIL lines never name the case the mutation's label
says it breaks). Before this module, `safe_name`, `job_count`, `skip_reason`, and the
SURVIVED / WRONG CAUSE verdict-and-tally printing were each written out twice, and the two
copies had already started to drift: janitor/mutate_sweep.py's own `safe_name` lacked the
digest suffix hooks/mutate_guard.py's carries (see `safe_name` below), so the exact filename
collision that suffix was written to fix could still happen on the janitor side. Importing this
module instead of a second copy is what closes that gap for good, not just for today.

STDLIB ONLY, AND NOTHING RUNS AT IMPORT TIME beyond defining these names. Both callers are
checks: an import error or a syntax error here takes both mutation tests down at once instead of one,
so this file stays small, has no side effects on import, and takes on no new dependency.

What stays OUT of this module, and why: `mutation_parts` and `run_mutant` are NOT shared, even
though both files name a function by that name. Each file's own `MUTATIONS` list packs its
entry tuples in a different field order (hooks/mutate_guard.py: label, old, new, target?,
required?, only_on?, target defaulting to "guard"; janitor/mutate_sweep.py: label, target, old,
new, required, only_on?, target always required) and `run_mutant` mutates one bare file in one
case and lays out a whole multi-file scaffold directory in the other. Forcing those into one
shared shape means either reordering hundreds of literal mutation tuples that are themselves the
tested check content (the reordering itself becoming a real chance to misfile a field and quietly
weaken a mutation), or writing a shared function that takes the field order as a parameter,
which recreates the duplication as a configuration option instead of removing it. Neither closes
real duplication; both add the fragility this module exists to avoid. They stay two local
functions, each shaped by its own file's `MUTATIONS`.
"""
import ast
import glob
import hashlib
import json
import os
import queue
import random
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

# The folder guard_tree copies from. Read at call time, so a test can point it elsewhere.
HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))

# How many red lines a wrong cause prints before it stops. A wrong cause usually carries one or
# two, and the bound keeps a mutation that breaks half the suite from burying the rest of the run.
WRONG_CAUSE_LINES_SHOWN = 10


class StaleMutant(Exception):
    """A mutant's anchor text is in no guard module."""


class AmbiguousMutant(Exception):
    """A mutant's anchor text is in the guard modules more than once."""


def guard_files(folder: str):
    """Every guard module in `folder`: guard.py and its guard_*.py siblings, sorted."""
    return sorted(glob.glob(os.path.join(folder, "guard*.py")))


def anchor_files(folder: str):
    """Every file a guard mutant may be anchored in: the guard modules, then git_reads.py, which
    holds the reads of the repository and of sessions that the guard and the janitor share, then
    proc_env.py, the one home of the exec-environment session-tag read, then reread_check.py,
    the one home of the handoff-unread check the guard calls, then own_session.py, the one home of
    the own get_session read that guard_merge.py and lint/report_guard.py both import, then stall_watch.py,
    the one reader of the session's background work, which rule worktree-strands-agents calls."""
    shared = [os.path.join(folder, name)
              for name in ("git_reads.py", "proc_env.py", "reread_check.py", "own_session.py", "stall_watch.py")]
    return guard_files(folder) + [path for path in shared if os.path.exists(path)]


def module_files(folder: str):
    """Every module in `folder` that a copied guard may import: each *.py but the suites (test_*) and
    the harnesses (mutate_*, prove_*), sorted. A copy of this set cannot miss a new shared module.
    It lists the folder, not git: a mutation scaffold is not a git tree, and testing/tracked_tree.py
    does not land beside the hooks."""
    return sorted(os.path.join(folder, name) for name in os.listdir(folder)
                  if name.endswith(".py") and not name.startswith(("test_", "mutate_", "prove_")))


def guard_tree(dest: str) -> None:
    """Copy every module in HOOKS_DIR (module_files) into `dest`, so a copied guard.py finds its
    siblings beside it, never the real ones, and a module they import cannot be left out."""
    os.makedirs(dest, exist_ok=True)
    for path in module_files(HOOKS_DIR):
        shutil.copy(path, dest)


def find_anchor(folder: str, old: str, files=None):
    """Return (path, text) of the one guard module or git_reads.py in `folder` that holds `old`
    exactly once. Raise StaleMutant on zero matches, AmbiguousMutant on two or more, across all.
    `files` (folder-relative names) replaces that list: a known defect names the file it plants in."""
    hits = []
    paths = anchor_files(folder) if files is None else [os.path.join(folder, name) for name in files]
    for path in paths:
        # Universal newlines: a checkout may hold CRLF, and an anchor spells a line break "\n".
        try:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
        except FileNotFoundError:
            if files is None:
                raise
            raise StaleMutant("STALE: %s is not in %s" % (os.path.relpath(path, folder), folder))
        hits.extend([(path, text)] * text.count(old))
    if not hits:
        raise StaleMutant("STALE: anchor text is in no guard module in %s" % folder)
    if len(hits) > 1:
        raise AmbiguousMutant("anchor text matches %d times in %s" % (
            len(hits), ", ".join(sorted({os.path.basename(p) for p, _ in hits}))))
    return hits[0]


def apply_mutant(tree: str, old: str, new: str, files=None) -> str:
    """Replace `old` with `new` in the one guard module in `tree` that holds it (or in `files`, see
    find_anchor). Return its path. Write nothing when the anchor is stale or ambiguous."""
    path, text = find_anchor(tree, old, files)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.replace(old, new, 1))
    return path


def safe_name(label: str) -> str:
    """Turn a mutation label into a filesystem stem that stays unique, even case-insensitively.

    Two real labels in hooks/mutate_guard.py's own MUTATIONS differ only in the case
    of one letter. One reads "-D", the other reads "-d", inside the branch-delete flags. An
    alnum-to-underscore mapping alone keeps letter case, so both produced the identical name on
    a case-insensitive filesystem (Windows): one file, one config directory, two mutant runs
    racing to write it. The digest covers the exact label text. It does not depend on letter
    case, and it does not depend on where the mutation sits in a MUTATIONS list. Two different
    labels collide here only if their digests also collide.
    """
    base = "".join(ch if ch.isalnum() else "_" for ch in label)[:60]
    digest = hashlib.sha1(label.encode("utf-8")).hexdigest()[:8]
    return "%s_%s" % (base, digest)


def job_count() -> int:
    """How many suites to run at once: MUTATE_JOBS, else the CPU count, at least one."""
    try:
        wanted = int(os.environ.get("MUTATE_JOBS", "") or 0)
    except ValueError:
        wanted = 0
    return max(1, wanted or os.cpu_count() or 1)


def skip_reason(only_on):
    """Return why a mutation marked `only_on` does not run on this platform, or None to run it.

    `only_on` is "posix" or "windows", for a mutation whose broken code path only exists on one
    platform (e.g. a POSIX-only `ps` arm never reached on Windows). A mutation that carries no
    `only_on` at all runs on every platform, and this returns None for it too.
    """
    if only_on is None:
        return None
    here = "windows" if sys.platform.startswith("win") else "posix"
    if only_on == here:
        return None
    return "%s-only, this platform is %s" % (only_on, here)


_ERROR_HEADER = re.compile(r"^ERROR: ")
_RULE_LINE = re.compile(r"^(=|-){10,}\s*$")


def diagnostic_lines(output: str) -> list:
    """Each unittest `ERROR: ...` header in `output`, then that block's final exception line.

    A case that throws prints no FAIL line, so a WRONG CAUSE report built from FAIL lines alone
    shows only `FAILED (errors=1)` and loses the exception (a TimeoutExpired on Windows run
    42063704930). A block runs from its header to the next rule line of `=` or `-`; the dashed
    rule right under the header is skipped. Blocks with no traceback give the header alone."""
    lines = output.splitlines()
    found = []
    index = 0
    while index < len(lines):
        if not _ERROR_HEADER.match(lines[index]):
            index += 1
            continue
        found.append(lines[index].rstrip())
        index += 1
        if index < len(lines) and _RULE_LINE.match(lines[index]):
            index += 1
        last = None
        while index < len(lines) and not _RULE_LINE.match(lines[index]):
            if lines[index].strip():
                last = lines[index].rstrip()
            index += 1
        if last is not None:
            found.append(last)
    return found


def report_verdict(label: str, code, red, required: str, seen=()) -> str:
    """Classify and print one mutant's verdict. Returns "survived", "wrong_cause", or "killed".

    A nonzero exit plus any red line is not proof, because every red line may belong to some OTHER
    case than the one the mutation's label names. `required` is the case
    name (or a distinctive fragment of it) that must appear among the suite's own FAIL lines
    before a kill counts as proof; a red suite that misses it is WRONG CAUSE, not KILLED.
    A WRONG CAUSE also prints the red lines it actually saw, then `seen` (the suite's ERROR
    lines, see `diagnostic_lines`), as one report bounded by WRONG_CAUSE_LINES_SHOWN, because a
    bare count says nothing about which case broke. `seen` never changes the verdict: only `red` does.
    """
    if code == 0 or not red:
        print("SURVIVED    %-62s %2d red" % (label, len(red)), flush=True)
        return "survived"
    if not any(required in line for line in red):
        print("WRONG CAUSE %-62s %2d red, missing %r" % (
            label, len(red), required), flush=True)
        shown = list(red) + list(seen)
        for line in shown[:WRONG_CAUSE_LINES_SHOWN]:
            print("            saw: %s" % line.strip(), flush=True)
        if len(shown) > WRONG_CAUSE_LINES_SHOWN:
            print("            saw: ... and %d more" % (
                len(shown) - WRONG_CAUSE_LINES_SHOWN), flush=True)
        return "wrong_cause"
    print("KILLED      %-62s %2d red" % (label, len(red)), flush=True)
    return "killed"


def staged_suite(run, required: str):
    """Run one mutant's suite in two stages. Return (code, red).

    `run(only) -> (code, red, ran)`: `only` is the required case fragment to run alone, or None
    for the full suite. `ran` is the suite's per-case result lines, passed and failed.

    Stage 1 runs only the cases named by `required`. When any `ran` line names the case, stage 1's
    (code, red) is the verdict: once the required case ran, a non-kill fails the run either way, and
    stage 1 takes about 3 s against about 450 s for the full suite. A required case that passes
    reads SURVIVED (0 red), where the full suite would read WRONG CAUSE with its saw: lines; run
    with MUTATE_FULL=1 to get those lines for diagnosis. A suite that ignores the filter runs every
    case in stage 1. A stage 1 that ran no named case falls back to the full suite: none selected,
    a crash before the case, or a required case whose only row is a SKIP, which is not collected.
    MUTATE_FULL=1 runs the full suite alone.
    """
    if os.environ.get("MUTATE_FULL"):
        code, red, _ran = run(None)
        return code, red
    code, red, ran = run(required)
    if any(required in line for line in ran):
        return code, red
    code, red, _ran = run(None)
    return code, red


def staged_suite_seen(run, required: str):
    """`staged_suite` plus the diagnostics of the run that gave the verdict. Return (code, red, seen).

    `run(only)` returns (code, red, ran) or (code, red, ran, seen); a runner that has no `seen`
    reads as an empty one. `seen` is the last run's, which is the run `staged_suite` returned."""
    last = []

    def stage(only):
        code, red, ran, *extra = run(only)
        last[:] = extra[0] if extra else []
        return code, red, ran

    code, red = staged_suite(stage, required)
    return code, red, list(last)


def run_mutants(entries, run_one):
    """Run every entry through `run_one`, in parallel, printing each mutant's verdict as it
    lands, then the tally line. Returns 0 when every mutant was killed (a caller's own `main`
    should return that, or 1 otherwise), so a caller can end with
    `return mutate_shared.run_mutants(MUTATIONS, run_one)`.

    `run_one(entry) -> (label, code, red, required, skip[, seen])` is supplied by the caller: it applies
    one mutation and runs its suite however that caller lays a mutant out on disk (one file next
    to a shared work directory, or a whole per-mutant scaffold -- see this module's own
    docstring for why that part is not shared). This function owns only the parallel dispatch,
    the printed verdict, and the tally, which both callers ran through two copies of the same
    ThreadPoolExecutor loop before this extraction.
    """
    jobs = job_count()
    print("%d mutations, %d at a time" % (len(entries), jobs))
    survivors = 0
    wrong_cause = 0
    skipped = 0
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        for label, code, red, required, skip, *more in pool.map(run_one, entries):
            if skip:
                skipped += 1
                print("SKIPPED     %-62s %s" % (label, skip), flush=True)
                continue
            status = report_verdict(label, code, red, required, more[0] if more else ())
            if status == "survived":
                survivors += 1
            elif status == "wrong_cause":
                wrong_cause += 1
    print()
    ran = len(entries) - skipped
    killed = ran - survivors - wrong_cause
    print("%d of %d mutations killed (%d survived, %d wrong cause, %d skipped)" % (
        killed, ran, survivors, wrong_cause, skipped))
    return 1 if (survivors or wrong_cause) else 0


# ---------------------------------------------------------------------------------------------------
# REPORT MODE (step c95, lane c95-test-value). The question: do a file's tests pin anything that
# matters, or do some pin a static result? The hand-written MUTATIONS in hooks/mutate_guard.py prove
# the guard; they do not scale to the other verdict-deciding files, so this half makes mutants
# mechanically with `ast` and scores each file. It is read on demand (`python3 hooks/mutate_guard.py
# --report`): no timer, no long-lived process, not a required CI job. Cost per file: one scaffold copy
# per mutant, plus (suites x (mutants + 1)) test-process starts. Nothing is written outside a temp folder.
#
# TWO WAYS TO COUNT A KILL WRONG, BOTH CLOSED HERE.
# 1. A crash is not a kill. A mutant counts killed only when a suite prints a FAIL line (an assertion
#    went red). A throw, an import error or a timeout leaves no FAIL line, or ends at the timeout, and
#    reads "crashed".
# 2. A suite red on the clean source is not a killer. Every suite first runs on the NORMALIZED clean
#    source (the same `ast.unparse` text every mutant carries, so a suite that reads source text fails
#    here and not as a fake kill). A suite that is not green there is UNUSABLE for that file. A file
#    with no usable suite, a parse error, or a missing target reads UNKNOWN, never green or killed.

FAIL_LINE = re.compile(r"^FAIL(?::|\s|$)", re.M)
SCAFFOLD_SKIP = (".git", ".claude", "node_modules", "__pycache__")
_SWAPS = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.GtE, ast.GtE: ast.Lt, ast.Gt: ast.LtE,
          ast.LtE: ast.Gt, ast.In: ast.NotIn, ast.NotIn: ast.In, ast.Is: ast.IsNot, ast.IsNot: ast.Is}


def _sites(tree):
    """Every place one mechanical mutant can go, in a fixed order: (kind, node, comparison index)."""
    sites = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            sites.extend(("compare", node, i) for i, op in enumerate(node.ops) if type(op) in _SWAPS)
        elif isinstance(node, ast.BoolOp):
            sites.append(("boolop", node, None))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            sites.append(("not", node, None))
        elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
            sites.append(("const", node, None))
        elif isinstance(node, (ast.If, ast.While)):
            sites.append(("negate", node, None))
        elif isinstance(node, ast.Return):
            if node.value is not None and not (isinstance(node.value, ast.Constant) and node.value.value is None):
                sites.append(("retval", node, None))
            sites.append(("dropret", node, None))
    return sites


def _replace(tree, old, new):
    """Swap `old` for `new` in its parent. A tree has one parent per node, so the first hit is it."""
    for parent in ast.walk(tree):
        for field, value in ast.iter_fields(parent):
            if value is old:
                setattr(parent, field, new)
                return
            if isinstance(value, list):
                for index, item in enumerate(value):
                    if item is old:
                        value[index] = new
                        return


def _apply(tree, kind, node, index):
    """Apply one mutation in place. Return a short label of what changed."""
    if kind == "compare":
        before = type(node.ops[index]).__name__
        node.ops[index] = _SWAPS[type(node.ops[index])]()
        return "compare %s -> %s" % (before, type(node.ops[index]).__name__)
    if kind == "boolop":
        was = type(node.op).__name__
        node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
        return "bool %s -> %s" % (was, type(node.op).__name__)
    if kind == "not":
        _replace(tree, node, node.operand)
        return "not dropped"
    if kind == "const":
        node.value = not node.value
        return "%s -> %s" % (not node.value, node.value)
    if kind == "negate":
        node.test = ast.UnaryOp(op=ast.Not(), operand=node.test)
        return "%s test negated" % type(node).__name__.lower()
    if kind == "retval":
        node.value = ast.Constant(value=None)
        return "return value -> None"
    _replace(tree, node, ast.Pass())
    return "return dropped"


def normalize(source: str) -> str:
    """The text every mutant of `source` is built from: parsed and unparsed, so the clean control run
    and a mutant differ by the mutation alone. Raises SyntaxError on source that does not parse."""
    return ast.unparse(ast.parse(source))


def _sample(found, limit, seed):
    """Up to `limit` of `found`, in order, drawn the same way for every engine, so one seed keeps the
    same mutants on a .py file and on a .ts file."""
    if limit is not None and len(found) > limit:
        keep = sorted(random.Random(seed).sample(range(len(found)), limit))
        found = [found[i] for i in keep]
    return found


def ast_mutants(source: str, limit=None, seed: int = 0, lines=None):
    """Return up to `limit` [(label, mutated source)], one mutation each, repeatable for one seed.

    `lines`, when given, keeps only the sites whose node starts on one of those 1-based lines; the
    sample is drawn from what is kept. A mutant whose text equals the normalized source is
    equivalent and is left out. Raises SyntaxError when `source` does not parse: the caller reads
    that as UNKNOWN.
    """
    base = normalize(source)
    wanted = None if lines is None else set(lines)
    found = []
    for position, (_kind, probe, _index) in enumerate(_sites(ast.parse(source))):
        if wanted is not None and getattr(probe, "lineno", 0) not in wanted:
            continue  # skipped before the re-parse below: a large file with a few wanted lines costs few parses
        tree = ast.parse(source)  # a fresh tree per site, so each mutant holds exactly one change
        kind, node, index = _sites(tree)[position]
        line = getattr(node, "lineno", 0)
        what = _apply(tree, kind, node, index)
        text = ast.unparse(ast.fix_missing_locations(tree))
        if text != base:
            found.append(("L%d %s" % (line, what), text))
    return _sample(found, limit, seed)


# The JavaScript and TypeScript engine runs in its own process, because its parser is the typescript
# package (hooks/mutate_js.mjs). Cost: one `node` start per file mutated.
JS_ENGINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mutate_js.mjs")
JS_ENGINE_TIMEOUT = 120


def js_mutants(path: str, limit=None, seed: int = 0, lines=None):
    """Return up to `limit` [(label, mutated source)] for one .js/.mjs/.cjs/.jsx/.ts/.mts/.cts/.tsx
    file, sampled as `ast_mutants` samples. `lines` keeps only the sites that start on those lines.
    Raises ValueError when the engine cannot run or the file does not parse: the caller reads that
    as UNKNOWN, as it reads a SyntaxError from `ast_mutants`.
    """
    import _nowindow  # lazy: this module defines names only at import (see the docstring)
    if lines is not None and not set(lines):
        return []  # no line wanted: the engine would reject an empty list, and nothing could match
    node = shutil.which("node")
    if not node:
        raise ValueError("node is not on PATH")
    command = [node, JS_ENGINE, path]
    if lines is not None:
        command += ["--lines", ",".join(str(number) for number in sorted(set(lines)))]
    try:
        done = _nowindow.run(command, capture_output=True, text=True, encoding="utf-8",
                             stdin=subprocess.DEVNULL, timeout=JS_ENGINE_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("the JS engine did not run: %s" % error)
    if done.returncode != 0:
        raise ValueError(done.stderr.strip() or "the JS engine exited %d" % done.returncode)
    try:
        found = [(item["label"], item["text"]) for item in json.loads(done.stdout)]
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError("the JS engine printed no mutant list: %s" % error)
    return _sample(found, limit, seed)


def changed_lines(repo: str, base: str, head: str, path: str) -> set:
    """The 1-based lines of `path` (repository-relative) that `head` adds or rewrites against `base`.
    A deleted line adds none. Raises ValueError when the diff cannot be read."""
    import _nowindow
    done = _nowindow.run(["git", "-C", repo, "diff", "-U0", "--no-color", "--no-ext-diff", "--no-renames",
                          base, head, "--", path], capture_output=True, text=True, encoding="utf-8",
                         stdin=subprocess.DEVNULL)
    if done.returncode != 0:
        raise ValueError("git diff failed: %s" % done.stderr.strip())
    lines = set()
    for hunk in re.finditer(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@", done.stdout, re.M):
        first = int(hunk.group(1))
        count = 1 if hunk.group(2) is None else int(hunk.group(2))
        lines.update(range(first, first + count))
    return lines


def classify_run(code, output: str, timed_out: bool) -> str:
    """One suite run: "pass", "assert" (a FAIL line, an assertion went red), "crash" (red with no FAIL
    line: a throw, an import error) or "timeout". Only "assert" is evidence a mutant was caught."""
    if timed_out:
        return "timeout"
    if code == 0:
        return "pass"
    return "assert" if FAIL_LINE.search(output) else "crash"


_TAP_ENTRY = re.compile(r"^\s*(?:not ok|ok)\b|^\s*1\.\.\d|^\s*# Subtest:", re.M)
_ASSERT_MARK = re.compile(r"^\s*(?:code: 'ERR_ASSERTION'|name: 'AssertionError')", re.M)


def classify_node_tap(code, output: str, timed_out: bool) -> str:
    """One `node --test --test-reporter=tap` run: "pass", "assert" (an assertion went red: a `not ok`
    block has the keyed line `code: 'ERR_ASSERTION'` or `name: 'AssertionError'`), "crash" (any other
    red: an import error, a throw, an error text that only names AssertionError) or "timeout". Only "assert" is evidence a mutant was caught. A block runs from a test line to the
    next one, so an `ok` block that names an assertion (a test that expects one) does not count."""
    if timed_out:
        return "timeout"
    if code == 0:
        return "pass"
    starts = [m.start() for m in _TAP_ENTRY.finditer(output)] + [len(output)]
    for begin, end in zip(starts, starts[1:]):
        block = output[begin:end]
        if re.match(r"\s*not ok\b", block) and _ASSERT_MARK.search(block):
            return "assert"
    return "crash"


def run_suite_file(folder: str, rel: str, timeout: float, argv=None, classify=None, cwd=None):
    """Run one suite from `folder`. Return (class, seconds). By default the suite is `python3 <rel>`
    read by `classify_run`. A replay passes `argv` (the whole command), `classify` (a function of
    (code, output, timed_out)) and `cwd` (a folder inside `folder`). The child gets its own process
    group, killed whole at the timeout. Output goes to a file: a grandchild that holds a pipe open
    would make a pipe read wait for it."""
    env = {k: v for k, v in os.environ.items() if not k.endswith("_UNDER_TEST") and k != "MUTATE_ONLY"}
    # No bytecode: a mutant of the same size and second as the clean file would load the clean .pyc.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    command = argv or [sys.executable, os.path.join(folder, rel)]
    started = time.time()
    code, output, timed_out = run_in_group(command, cwd or folder, timeout, env)
    return (classify or classify_run)(code, output, timed_out), time.time() - started


_LIVE_GROUPS = set()  # process group ids of the children running now, so a signal can kill them
_LIVE_LOCK = threading.RLock()  # re-entrant: a signal handler runs on the main thread, which may hold it
_STOP = threading.Event()  # set by `request_stop`: no child starts after it
CUT = object()  # a mutant the budget cut: `_replay_in` scores it not_run and counts it in a note


def run_in_group(command, cwd: str, timeout: float, env=None):
    """Run `command` in its own process group, killed whole at the timeout. Return (exit code, output,
    timed_out). Output goes to a file: a grandchild that holds a pipe open would make a pipe read wait
    for it. Raises RuntimeError once `request_stop` has been called."""
    import _nowindow  # lazy: this module defines names only at import (see the docstring)
    timed_out = False
    with tempfile.TemporaryFile() as log:
        extra = {"start_new_session": True} if os.name == "posix" else {}
        with _LIVE_LOCK:
            if _STOP.is_set():
                raise RuntimeError("the replay was stopped")
            proc = _nowindow.Popen(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, env=env, **extra)
            _LIVE_GROUPS.add(proc.pid)
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_group(proc.pid, proc)
            proc.wait()
        finally:
            with _LIVE_LOCK:
                _LIVE_GROUPS.discard(proc.pid)
        log.seek(0)
        output = log.read().decode("utf-8", "replace")
    return proc.returncode, output, timed_out


def _kill_group(pid: int, proc=None) -> None:
    try:
        if os.name == "posix":
            os.killpg(pid, signal.SIGKILL)
        elif proc is not None:
            proc.kill()
    except OSError:
        if proc is not None:
            proc.kill()


def request_stop() -> None:
    """Stop every child now and start no other: the handler of SIGTERM and SIGINT calls this, so the
    `finally` blocks of a replay can remove its checkouts."""
    with _LIVE_LOCK:
        _STOP.set()
        for pid in list(_LIVE_GROUPS):
            _kill_group(pid)


def clear_stop() -> None:
    _STOP.clear()


def _copy_scaffold(root: str, dest: str, repo_init: bool) -> None:
    """A copy of `root` a suite can run in. A suite that lists files through the repository needs one,
    so `repo_init` starts an empty repository: its `ls-files --others` then lists the copy."""
    import _nowindow
    shutil.copytree(root, dest, symlinks=True, ignore=shutil.ignore_patterns(*SCAFFOLD_SKIP))
    if repo_init:
        _nowindow.run(["git", "init", "-q", dest], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def score_target(root: str, target: str, tests, limit: int = 10, timeout=None, jobs=None,
                 repo_init: bool = True, seed: int = 0) -> dict:
    """Score the suites `tests` against mechanical mutants of `target`, both paths relative to `root`.

    Returns a row: file, status ("OK" or "UNKNOWN"), reason, made, killed, crashed, survived, rate
    (killed / made, None when UNKNOWN), killers {suite: mutants it killed}, silent [usable suites that
    killed none], unusable {suite: why}, unloaded [usable suites that stay green on a wholly broken copy
    of the target: they never loaded it]. See the report-mode comment above for what counts as a kill.
    """
    row = {"file": target, "status": "UNKNOWN", "reason": "", "made": 0, "killed": 0, "crashed": 0,
           "survived": 0, "rate": None, "killers": {}, "silent": [], "unusable": {},
           "unloaded": []}
    path = os.path.join(root, target)
    if not os.path.isfile(path):
        row["reason"] = "target file is missing"
        return row
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    try:
        mutants = ast_mutants(source, limit=limit, seed=seed)
    except (SyntaxError, ValueError) as error:
        row["reason"] = "parse error: %s" % error
        return row
    for rel in tests:
        if not os.path.isfile(os.path.join(root, rel)):
            row["unusable"][rel] = "missing"
    present = [rel for rel in tests if rel not in row["unusable"]]
    if not mutants:
        row["reason"] = "no mutant could be made"
        return row
    if not present:
        row["reason"] = "no suite file exists"
        return row

    jobs = jobs or job_count()
    work = tempfile.mkdtemp(prefix="mutate_report_")
    try:
        clean = os.path.join(work, "clean")
        _copy_scaffold(root, clean, repo_init)
        _write(os.path.join(clean, target), normalize(source))
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            control = list(pool.map(lambda rel: run_suite_file(clean, rel, timeout or 1800), present))
        usable = []
        slowest = 0.0
        for rel, (kind, seconds) in zip(present, control):
            if kind == "pass":
                usable.append(rel)
                slowest = max(slowest, seconds)
            else:
                row["unusable"][rel] = "not green on the clean source (%s)" % kind
        if not usable:
            row["reason"] = "no suite is green on the clean source"
            return row
        bound = timeout or max(60.0, 4 * slowest)
        # A copy that raises on import: a suite that loads the target cannot stay green on it.
        broken = os.path.join(work, "broken")
        shutil.copytree(clean, broken, symlinks=True)
        _write(os.path.join(broken, target), 'raise RuntimeError("wholly broken copy of the target")\n')
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            broken_kinds = list(pool.map(lambda rel: run_suite_file(broken, rel, bound)[0], usable))
        unloaded = [rel for rel, kind in zip(usable, broken_kinds) if kind == "pass"]
        row["unloaded"] = unloaded
        if len(unloaded) == len(usable):  # no suite is shown to load the file, so a rate would score suites that never ran it
            row["reason"] = "every usable suite stays green on a wholly broken copy of the file"
            return row

        def one(item):
            number, (_label, text) = item
            folder = os.path.join(work, "m%d" % number)
            shutil.copytree(clean, folder, symlinks=True)
            _write(os.path.join(folder, target), text)
            try:
                return {rel: run_suite_file(folder, rel, bound)[0] for rel in usable}
            finally:
                shutil.rmtree(folder, ignore_errors=True)

        with ThreadPoolExecutor(max_workers=jobs) as pool:
            outcomes = list(pool.map(one, enumerate(mutants)))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    row["killers"] = {rel: 0 for rel in usable}
    for outcome in outcomes:
        kinds = set(outcome.values())
        for rel, kind in outcome.items():
            if kind == "assert":
                row["killers"][rel] += 1
        if "assert" in kinds:
            row["killed"] += 1
        elif kinds & {"crash", "timeout"}:
            row["crashed"] += 1
        else:
            row["survived"] += 1
    row["made"] = len(mutants)
    row["rate"] = row["killed"] / row["made"]
    row["silent"] = [rel for rel in usable if row["killers"][rel] == 0]
    row["unloaded"] = unloaded
    row["status"] = "OK"
    return row


def format_report(rows, gold=None) -> str:
    """The per-file table, the suites that were unusable, then the gold-standard line."""
    lines = ["%-28s %7s %6s %7s %9s %5s  %s" % (
        "file", "mutants", "killed", "crashed", "survived", "rate", "silent suites")]
    for row in rows:
        if row["status"] != "OK":
            lines.append("%-28s UNKNOWN (%s)" % (row["file"], row["reason"]))
            continue
        lines.append("%-28s %7d %6d %7d %9d %4d%%  %s" % (
            row["file"], row["made"], row["killed"], row["crashed"], row["survived"],
            round(row["rate"] * 100), ", ".join(row["silent"]) or "none"))
    for row in rows:
        for rel, why in sorted(row["unusable"].items()):
            lines.append("  unusable for %s: %s (%s)" % (row["file"], rel, why))
        for rel in row.get("unloaded", []):
            lines.append("  unloaded for %s: %s (green on a wholly broken copy of the file)" % (row["file"], rel))
    if gold is not None:
        lines.append("gold standard: %s" % gold)
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------------
# REPLAY MODE (step tci-6). The question: would the suites a past pull request changed have caught a
# wrong line in the product code that same pull request added? `python3 hooks/mutate_guard.py --replay
# <repo> --profile <name>` walks the last merged pull requests of a repository, makes mechanical
# mutants of the lines each one added (the engines above), and runs the suites it changed against each.
# Read on demand; no timer, no long-lived process, not a required CI job. The two counts of report
# mode hold here: a crash is not a kill, and a suite red on the clean source is not a killer.
# Cost per pull request: one control run per suite, one run per suite per mutant, one `git worktree`
# per job, one install per lockfile hash, install and link. Written: a temp folder of checkouts and one deps folder
# per lockfile hash, install and link, all removed at the end. The target repository is left as found. `--known-defects` runs the same
# installs in its own deps folder, each up to INSTALL_TIMEOUT. In the action
# that is a second install, because the `--changed` step removes its deps. A profile with a `select`
# adds, per pull request, one git read for each script path in its argv that the commit lacks, and one folder
# extract for a script that HEAD holds.
#
# A PROFILE says how one repository is read: {"code": regex of product files, "code_not": regex of
# files to leave out (optional), "tests": regex of suite files, "argv": the command with {suite} (the
# suite path from `cwd`) and {deps} (the install folder), "classify": a CLASSIFIERS name, "cwd": the folder
# the command runs in (optional), "install": argv, or a list of argv, run once per lockfile hash, install and link, with the
# lockfile beside it in the deps folder (None for no install), "lockfile": its path in the repository,
# "link": the folder the install makes, linked into each checkout beside the lockfile (None for none),
# "select": argv with {path}, run in a checkout at the pull request's commit, that prints the suites which
# test one product file (a changed suite is run on the mutants of that file only when its line is listed; a select
# that fails, or is missing, runs every changed suite and adds a row note). A script the argv names that the commit
# lacks is read from the clone's HEAD instead, with its whole folder, so the siblings it loads come along; the row
# names it. The commit's own copy wins. Only a part with a "/" is a script path: a bare command name resolves on
# PATH, so a bare root name such as `select.sh` is never served from HEAD; `./select.sh` is, with the whole tree,
# "suite_filter": {"paths": regex, "keep": a SUITE_FILTERS name} (optional); a changed file that "tests" matches
# and "paths" matches is a suite only when the filter reads its text as one,
# "sparse_skip": top folders left out of each checkout}. A profile of {"parts": {name: profile}} runs
# each part and keeps the rows that hold something.

INSTALL_TIMEOUT = 900
_MERGE_SUBJECT = re.compile(r"^Merge pull request #(\d+) from ")
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_PW_FAILURE = re.compile(r"^\s*\d+\) .* ─{3,}\s*$", re.M)
_PW_NOT_ASSERT = re.compile(r"Test timeout of|has been closed")
_PW_FRAME = re.compile(r"^\s*(?:>\s*)?\d+ \|", re.M)
_PW_ASSERT = re.compile(r"\bexpect\((?:received|locator|page|response)\)|AssertionError|ERR_ASSERTION")


def classify_playwright(code, output: str, timed_out: bool) -> str:
    """One `playwright test` run: "pass", "assert" (the error text of a failure block, before its source
    frame, holds an `expect(received)` matcher line or an AssertionError), "crash" (any other red: a load error, a throw, no test found) or
    "timeout". Only "assert" is evidence a mutant was caught."""
    if timed_out:
        return "timeout"
    if code == 0:
        return "pass"
    text = _ANSI.sub("", output)
    starts = [m.start() for m in _PW_FAILURE.finditer(text)] + [len(text)]
    for begin, end in zip(starts, starts[1:]):
        block = text[begin:end]
        frame = _PW_FRAME.search(block)
        # The error text ends where the source frame starts. The frame quotes the line that stood when
        # the error was thrown, so an `expect(page)` in it is no evidence of an assertion.
        error = block[:frame.start()] if frame else block
        # A timeout or a closed target reads red first: a web-first matcher that timed out prints its own
        # `expect(...)` error after the timeout line, and that is no assertion about the mutant.
        if not _PW_NOT_ASSERT.search(error) and _PW_ASSERT.search(error):
            return "assert"
    return "crash"


CLASSIFIERS = {"fail_line": classify_run, "node_tap": classify_node_tap, "playwright": classify_playwright}


def _git(repo: str, *args, binary: bool = False, stdin=None):
    """One git read or write on `repo`. Returns stdout. Raises ValueError on a nonzero exit."""
    import _nowindow
    done = _nowindow.run(["git", "-C", repo] + list(args), capture_output=True, input=stdin,
                         stdin=None if stdin is not None else subprocess.DEVNULL)
    if done.returncode != 0:
        raise ValueError("git %s failed: %s" % (args[0], done.stderr.decode("utf-8", "replace").strip()))
    return done.stdout if binary else done.stdout.decode("utf-8", "replace")


def _parse_merge(subject: str, body: str):
    """(number, title) of a GitHub pull request merge commit, or None for any other commit. The title is
    the first line of the body, as GitHub writes it."""
    found = _MERGE_SUBJECT.match(subject)
    if not found:
        return None
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    return int(found.group(1)), (lines[0] if lines else "")


def merged_prs(repo: str, branch: str, count: int):
    """The newest `count` pull requests merged on `branch`'s first-parent line, newest first, as
    [(merge sha, number, title)]. A merge that is not a pull request merge, and a pull request merge
    inside a branch (a second parent), is left out."""
    text = _git(repo, "log", "--first-parent", "--merges", "--format=%H%x1f%s%x1f%b%x1e", branch)
    found = []
    for record in text.split("\x1e"):
        fields = record.strip("\n").split("\x1f")
        if len(fields) != 3:
            continue
        parsed = _parse_merge(fields[1], fields[2])
        if parsed:
            found.append((fields[0], parsed[0], parsed[1]))
    return found[:count]


def _pr_of(repo: str, sha: str):
    """(number, title) of the pull request that `sha` merged. 0 and the subject for any other commit."""
    text = _git(repo, "log", "-1", "--format=%s%x1f%b", sha)
    subject, _, body = text.partition("\x1f")
    return _parse_merge(subject, body) or (0, subject.strip())


def _changed_files(repo: str, base: str, head: str):
    """{path: status letter} for each file `head` changes against `base`. A rename reads as a delete and an add."""
    text = _git(repo, "diff", "--name-status", "-z", "--no-renames", "--no-ext-diff", base, head)
    tokens = text.split("\0")
    return {tokens[i + 1]: tokens[i][:1] for i in range(0, len(tokens) - 1, 2)}


def _line_of(label: str) -> int:
    found = re.match(r"L(\d+)\b", label)
    return int(found.group(1)) if found else 0


def _file_at(repo: str, sha: str, path: str) -> bytes:
    return _git(repo, "show", "%s:%s" % (sha, path), binary=True)


def defines_checks(text: str) -> bool:
    """True when the module assigns CHECKS at its top level. Read from the parse tree, so a CHECKS line in a
    docstring, a comment or a string is not one. A module that does not parse is a suite: its run crashes, and
    a crash is a row, where a dropped file is silence."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return True
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        else:
            targets = [node.target] if isinstance(node, ast.AnnAssign) else []
        if any(isinstance(target, ast.Name) and target.id == "CHECKS" for target in targets):
            return True
    return False


SUITE_FILTERS = {"defines_checks": defines_checks}


def _is_suite(repo: str, sha: str, profile: dict, path: str) -> bool:
    rule = profile.get("suite_filter")
    if not rule or not re.search(rule["paths"], path):
        return True
    try:
        text = _file_at(repo, sha, path).decode("utf-8")
    except UnicodeDecodeError:
        return True
    return SUITE_FILTERS[rule["keep"]](text)


def _ensure_deps(repo: str, sha: str, profile: dict, deps_root: str):
    """The install folder for `sha`'s lockfile: (folder or None, why it is unusable). The install runs once
    per lockfile hash, install argv and link under `deps_root`, with the lockfile (and its package.json) beside it.
    Two parts with one lockfile and one install share a folder; a different install gets its own."""
    install = profile.get("install")
    if not install:
        return None, ""
    lock = profile.get("lockfile", "package-lock.json")
    try:
        data = _file_at(repo, sha, lock)
    except ValueError:
        return None, "no lockfile %s at this commit" % lock
    key = hashlib.sha1(data + json.dumps([install, profile.get("link", "node_modules")]).encode("utf-8"))
    folder = os.path.join(deps_root, key.hexdigest()[:16])
    failed, done_mark = os.path.join(folder, "FAILED"), os.path.join(folder, "DONE")
    if os.path.exists(done_mark):
        return folder, ""
    if os.path.exists(failed):
        with open(failed, encoding="utf-8") as handle:
            return None, handle.read()
    os.makedirs(folder, exist_ok=True)
    _write(os.path.join(folder, os.path.basename(lock)), data.decode("utf-8", "replace"))
    sibling = os.path.join(os.path.dirname(lock), "package.json")
    try:
        _write(os.path.join(folder, "package.json"), _file_at(repo, sha, sibling).decode("utf-8", "replace"))
    except ValueError:
        pass
    steps = install if isinstance(install[0], (list, tuple)) else [install]
    for step in steps:
        argv = [part.replace("{deps}", folder) for part in step]
        try:
            code, output, timed_out = run_in_group(argv, folder, INSTALL_TIMEOUT)
            if timed_out:
                why = "install passed %d s and was killed" % INSTALL_TIMEOUT
            else:
                why = "" if code == 0 else "install exited %d: %s" % (code, " ".join(output.split())[-300:])
        except OSError as error:
            why = "install did not run: %s" % error
        if why:
            _write(failed, why)
            return None, why
    _write(done_mark, "ok")
    return folder, ""


def _make_checkout(repo: str, sha: str, dest: str, skip, overrides: dict, deps, profile: dict) -> None:
    """A detached worktree of `repo` at `sha` in `dest`, without the top folders in `skip`, holding
    `overrides` ({path: text}) and the install folder linked in beside the lockfile. The checkout is
    written from the index, so a sparse skip changes no setting of the repository."""
    _git(repo, "-c", "core.hooksPath=%s" % os.devnull, "worktree", "add", "-q", "--detach", "--no-checkout",
         dest, sha)
    _git(dest, "read-tree", sha)
    names = _git(dest, "ls-files", "-z").split("\0")
    keep = [name for name in names if name and name.split("/")[0] not in skip]
    _git(dest, "checkout-index", "-z", "--stdin", stdin="\0".join(keep).encode("utf-8") + b"\0")
    for path, text in overrides.items():
        _write(os.path.join(dest, path), text)
    _link_deps(dest, deps, profile)


def _link_deps(dest: str, deps, profile: dict) -> None:
    """Link the install folder `deps` into checkout `dest` beside the profile's lockfile, as `link`. Nothing to link for no
    folder or no `link`. A link already there to the same target stays: two parts with one lockfile and one install share one
    folder. Any other path at the link name (a tracked file or folder, another target) raises OSError naming it."""
    link_name = profile.get("link", "node_modules")
    if deps and link_name:
        link = os.path.join(dest, os.path.dirname(profile.get("lockfile", "package-lock.json")), link_name)
        target = os.path.join(deps, link_name)
        if os.path.lexists(link):
            if os.path.islink(link) and os.readlink(link) == target:
                return
            raise OSError("%s exists and is not a link to %s" % (link, target))
        os.makedirs(os.path.dirname(link), exist_ok=True)
        os.symlink(target, link)


def _drop_checkout(repo: str, dest: str) -> None:
    try:
        _git(repo, "worktree", "remove", "--force", dest)
    except ValueError:
        shutil.rmtree(dest, ignore_errors=True)
        try:
            _git(repo, "worktree", "prune")
        except ValueError:
            pass


def _replay_row(repo: str, sha: str) -> dict:
    number, title = _pr_of(repo, sha)
    return {"pr": number, "sha": sha, "title": title, "status": "UNKNOWN", "reason": "", "made": 0,
            "killed": 0, "crashed": 0, "survived": 0, "not_run": 0, "survivors": [], "not_run_at": [],
            "unusable": {}, "skipped": {}, "notes": []}


def replay_pr(repo: str, sha: str, profile: dict, limit: int = 20, seed: int = 0, suite_timeout: float = 120,
              jobs=None, deps=None, pr_budget=None, progress=None, base=None, select_all: bool = False,
              wall_deadline: bool = False) -> dict:
    """Score the suites the pull request merged at `sha` changed against mechanical mutants of the product
    lines it added. Returns a row: pr, sha, title, status ("OK", "UNKNOWN", "NO_PRODUCT" for no product
    file changed, "NO_TESTS" for product code with no suite changed), reason, made, killed, crashed,
    survived, not_run, survivors [(path, line, label)], unusable {suite: why}, skipped {file: why},
    notes [text]. `made` counts every mutant, so killed + crashed + survived + not_run == made.
    A mutant is not_run when no changed suite reaches its file (the profile's `select`), or when the
    `pr_budget` seconds, counted from the start of this call, had passed before it started. It is never
    a survivor. `progress(line)`, when given, gets one line as each mutant finishes.
    `deps` is a folder shared by many calls, for the installs; None makes one and removes it.
    A run is read as in report mode: only an assertion kills, and an unusable suite is not a killer.
    `base` is the commit the added lines are read against (default: the first parent of `sha`), so a
    change that is no merge commit can be scored from its merge base. `select_all` (the `--changed` mode)
    runs, on the mutants of each file, every suite the profile's `select` lists for it, changed or not;
    a change with no suite is then no NO_TESTS row, and a mutant no suite reaches is not_run, with its
    line in `not_run_at`. Without `select_all`, only changed suites run.
    `wall_deadline` makes `pr_budget` a wall deadline: when it passes, the suites still running are killed
    (`request_stop`), and each mutant they ran is not_run, never crashed or survived. A note counts the
    mutants the budget cut. The stop is cleared on the way out. Without it, a running mutant is let finish."""
    started = time.time()
    row = _replay_row(repo, sha)
    code_re, tests_re = re.compile(profile["code"]), re.compile(profile["tests"])
    not_re = re.compile(profile["code_not"]) if profile.get("code_not") else None
    base = base or "%s^1" % sha
    try:
        files = _changed_files(repo, base, sha)
    except ValueError as error:
        row["reason"] = "cannot read the diff: %s" % error
        return row
    code = sorted(p for p, s in files.items() if s != "D" and code_re.search(p) and not (not_re and not_re.search(p)))
    suites = sorted(p for p, s in files.items() if s != "D" and tests_re.search(p))
    suites = [p for p in suites if _is_suite(repo, sha, profile, p)]
    if not code:
        row["status"] = "NO_PRODUCT"
        return row
    if not suites and not select_all:
        row["status"] = "NO_TESTS"
        return row

    own = tempfile.mkdtemp(prefix="mutate_replay_")
    try:
        return _replay_in(repo, sha, profile, row, code, suites, base, own, limit, seed, suite_timeout,
                          jobs or job_count(), deps or os.path.join(own, "deps"),
                          None if pr_budget is None else started + pr_budget, progress, select_all, wall_deadline)
    finally:
        shutil.rmtree(own, ignore_errors=True)


def _head_copy(repo: str, rel: str, own: str):
    """The absolute path of repo-relative file `rel` as the clone's HEAD holds it, extracted into `own` with its whole
    folder so a sibling it loads from beside itself is there too; None when HEAD has no such file. `git archive`
    leaves out an export-ignore sibling, and a symlinked sibling is not copied."""
    import io
    import tarfile
    try:
        archive = _git(repo, "archive", "HEAD", "--", os.path.dirname(rel) or rel, binary=True)
    except ValueError:
        return None
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            if member.isfile():
                target = os.path.join(own, member.name)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "wb") as handle:
                    handle.write(tar.extractfile(member).read())
    found = os.path.join(own, rel)
    return found if os.path.isfile(found) else None


def _select_suites(profile: dict, dest: str, path: str, suites, timeout: float, head=None):
    """The changed `suites` that the profile's `select` lists for product file `path`, run in checkout `dest`:
    (suites or None, note). None means no list: select is missing from the profile, or failed, and the note says why
    for a failure. A suite name is a line of the output; any other line is ignored. With `suites` None, every
    listed line that the profile's `tests` regex matches and `dest` holds is a suite, changed or not.
    `head(part)` serves a select argv part that has a "/" and no `{` and that `dest` lacks (a script the commit
    lacks): the absolute path of the copy at the clone's HEAD, or None. A bare command name is left to PATH.
    The run stays in `dest`."""
    select = profile.get("select")
    if not select:
        return None, ""
    argv = [head(part) or part if head and "/" in part and "{" not in part
            and not os.path.exists(os.path.join(dest, part)) else part for part in select]
    argv = [part.replace("{path}", path) for part in argv]
    try:
        code, output, timed_out = run_in_group(argv, dest, timeout)
    except OSError as error:
        return None, "%s: select did not run (%s), every changed suite runs" % (path, error)
    if timed_out or code != 0:
        return None, "%s: select %s, every changed suite runs" % (path, "timed out" if timed_out else "exited %d" % code)
    listed = {line.strip() for line in output.splitlines()}
    if suites is None:
        return sorted(name for name in listed if name and re.search(profile["tests"], name)
                      and os.path.isfile(os.path.join(dest, name))), ""
    return [suite for suite in suites if suite in listed], ""


def _replay_in(repo, sha, profile, row, code, suites, base, own, limit, seed, suite_timeout, jobs, deps,
               deadline=None, progress=None, select_all=False, wall_deadline=False):
    """The body of `replay_pr`, inside the temp folder `own`."""
    clean = {}  # path -> the text a clean run holds: the source, or its normalized form for Python
    found, parse_errors = [], {}
    for path in code:
        try:
            text = _file_at(repo, sha, path).decode("utf-8")
            lines = changed_lines(repo, base, sha, path)
            if path.endswith(".py"):
                clean[path] = normalize(text)
                made = ast_mutants(text, lines=lines)
            else:
                scratch = os.path.join(own, "src", path)
                os.makedirs(os.path.dirname(scratch), exist_ok=True)
                with open(scratch, "w", encoding="utf-8", newline="") as handle:
                    handle.write(text)
                clean[path] = text
                made = js_mutants(scratch, lines=lines)
        except UnicodeDecodeError as error:
            parse_errors[path] = "not UTF-8: %s" % error
            continue
        except (SyntaxError, ValueError) as error:
            parse_errors[path] = "parse error: %s" % ((str(error).strip().splitlines() or [type(error).__name__])[0])
            continue
        found.extend((path, label, mutated) for label, mutated in made)
    row["skipped"] = parse_errors
    if not found:
        reasons = sorted(set(parse_errors.values()))
        row["reason"] = ("%s; no mutant could be made" % "; ".join(reasons) if reasons
                         else "no mutant on the lines the pull request added")
        return row
    mutants = _sample(found, limit, seed)

    folder, why = _ensure_deps(repo, sha, profile, deps)
    if why:
        row["reason"] = why
        return row
    cwd_rel = profile.get("cwd", "")
    classify = CLASSIFIERS[profile["classify"]]

    def command(suite):
        rel = os.path.relpath(suite, cwd_rel) if cwd_rel else suite
        return [part.replace("{suite}", rel).replace("{deps}", folder or "") for part in profile["argv"]]

    count = max(1, min(jobs, max(len(suites), len(mutants))))
    spare = queue.Queue()
    made_dirs = []
    try:
        for number in range(count):
            dest = os.path.join(own, "w%d" % number)
            made_dirs.append(dest)
            try:
                _make_checkout(repo, sha, dest, set(profile.get("sparse_skip", [])), clean, folder, profile)
            except (ValueError, OSError) as error:
                row["reason"] = "checkout failed: %s" % error
                return row
            spare.put(dest)

        def borrow(work):
            dest = spare.get()
            try:
                return work(dest)
            finally:
                spare.put(dest)

        def run_one(dest, suite, bound):
            return run_suite_file(dest, suite, bound, argv=command(suite), classify=classify,
                                  cwd=os.path.join(dest, cwd_rel))

        # The suites that `select` lists for each file. None for a file means no list (no select, or it failed): the
        # changed suites run. With `select_all` the listed suites are the ones to run, so they take the control run.
        changed = list(suites)
        paths = sorted({mutant[0] for mutant in mutants})
        head_copies = {}  # select argv part -> its copy at HEAD (None when HEAD has none), read once per replay

        def head(part):
            if part not in head_copies:
                head_copies[part] = _head_copy(repo, part, os.path.join(own, "head"))
                if head_copies[part]:
                    row["notes"].append("%s: missing at the commit, read from HEAD" % part)
            return head_copies[part]

        listed_by = {}
        for path in paths:
            listed, note = borrow(lambda dest: _select_suites(profile, dest, path, None if select_all else changed,
                                                              suite_timeout, head))
            if note:
                row["notes"].append(note)
            listed_by[path] = listed
        if select_all:
            suites = sorted({name for path in paths for name in (changed if listed_by[path] is None
                                                                  else listed_by[path])})

        with ThreadPoolExecutor(max_workers=count) as pool:
            control = list(pool.map(lambda suite: borrow(lambda dest: run_one(dest, suite, suite_timeout)), suites))
        usable = []
        slowest = 0.0
        for suite, (kind, seconds) in zip(suites, control):
            if kind == "pass":
                usable.append((seconds, suite))
                slowest = max(slowest, seconds)
            else:
                row["unusable"][suite] = "not green on the clean source (%s)" % kind
        if not usable and not select_all:
            row["reason"] = "no suite is green on the clean source"
            return row
        usable = [suite for _seconds, suite in sorted(usable)]  # the quickest first: the first assertion ends a mutant
        bound = min(suite_timeout, max(10.0, 5 * slowest))

        # The suites to run on the mutants of each file: the usable suites that `select` lists for it, or the usable
        # changed ones when there is no list. A file no usable suite reaches gets none: its mutants are not_run.
        allowed = {}
        for path in paths:
            listed = listed_by[path]
            if listed is None:
                allowed[path] = [suite for suite in usable if suite in changed]
                continue
            allowed[path] = [suite for suite in usable if suite in listed]
            if not allowed[path]:
                who = "suite" if select_all else "changed suite"
                row["notes"].append("%s: %s" % (path, "no %s reaches it" % who if not listed else
                                                "the %ss that reach it are unusable" % who))

        expired = threading.Event()  # set by the deadline timer, after it has stopped the live suites
        progress_lock = threading.Lock()  # print writes text and newline apart, so workers' lines would interleave

        def score(dest, mutant):
            path, label, text = mutant
            if not allowed[path]:
                return None
            if deadline is not None and (time.time() > deadline or expired.is_set()):
                return CUT
            _write(os.path.join(dest, path), text)
            try:
                kinds = set()
                for suite in allowed[path]:
                    kind = run_one(dest, suite, bound)[0]
                    kinds.add(kind)
                    if kind == "assert":
                        break
            except RuntimeError:  # `run_in_group` refuses a start after `request_stop`
                if expired.is_set():
                    return CUT
                raise
            finally:
                _write(os.path.join(dest, path), clean[path])
            if "assert" not in kinds and expired.is_set():
                return CUT  # the deadline killed a suite part way: its exit says nothing about the mutant
            if progress:
                verdict = ("killed" if "assert" in kinds else "crashed" if kinds & {"crash", "timeout"}
                           else "survived")
                with progress_lock:
                    progress("  #%d mutant %s  %s:%d %s" % (row["pr"], verdict, path, _line_of(label), label))
            return kinds

        timer = None
        if wall_deadline and deadline is not None:
            def expire():
                expired.set()
                request_stop()

            timer = threading.Timer(max(0.0, deadline - time.time()), expire)
            timer.daemon = True
            timer.start()
        try:
            with ThreadPoolExecutor(max_workers=count) as pool:
                outcomes = list(pool.map(lambda mutant: borrow(lambda dest: score(dest, mutant)), mutants))
        finally:
            if timer is not None:
                timer.cancel()
                timer.join()  # the callback is short: after this, `expired` is final
                if expired.is_set():
                    clear_stop()
    finally:
        for dest in made_dirs:
            _drop_checkout(repo, dest)

    cut = 0
    for (path, label, _text), kinds in zip(mutants, outcomes):
        if kinds is None or kinds is CUT:
            row["not_run"] += 1
            row["not_run_at"].append((path, _line_of(label), label))
            cut += kinds is CUT
        elif "assert" in kinds:
            row["killed"] += 1
        elif kinds & {"crash", "timeout"}:
            row["crashed"] += 1
        else:
            row["survived"] += 1
            row["survivors"].append((path, _line_of(label), label))
    row["made"] = len(mutants)
    if cut:
        row["notes"].append("the budget cut %d of %d mutants: not_run" % (cut, len(mutants)))
    if row["not_run"] == row["made"]:
        row["reason"] = "no mutant ran (%d not run)" % row["not_run"]
        return row
    if parse_errors:
        # a rate over the files that parsed would read as the whole pull request's
        row["reason"] = "%d file(s) did not parse and were skipped (%s): no rate" % (
            len(parse_errors), ", ".join(sorted(parse_errors)))
        return row
    row["status"] = "OK"
    return row


def replay_profile(repo: str, sha: str, profile: dict, **options) -> list:
    """The rows of one pull request under `profile`: one row, or for a profile of parts the rows of the parts
    that hold something (a part that sees no product file is left out, unless every part sees none)."""
    def safely(part):
        """The row of `replay_pr`, or an UNKNOWN row when it raises, so the pull requests after this one
        still get rows. A stop (`request_stop`) is not caught."""
        try:
            return replay_pr(repo, sha, part, **options)
        except Exception as error:
            if _STOP.is_set():
                raise
            row = {"pr": 0, "sha": sha, "title": "", "status": "UNKNOWN", "made": 0, "killed": 0, "crashed": 0,
                   "survived": 0, "not_run": 0, "survivors": [], "unusable": {}, "skipped": {}, "notes": [],
                   "reason": "the replay raised %s: %s" % (type(error).__name__, error)}
            try:
                row["pr"], row["title"] = _pr_of(repo, sha)
            except ValueError:
                pass
            return row

    if "parts" not in profile:
        return [safely(profile)]
    rows = []
    for name, part in profile["parts"].items():
        row = safely(part)
        row["part"] = name
        rows.append(row)
    live = [row for row in rows if row["status"] != "NO_PRODUCT"]
    if live:
        return live
    rows[0].pop("part")
    return rows[:1]


def _row_line(row: dict) -> str:
    tag = " [%s]" % row["part"] if row.get("part") else ""
    head = "#%d%s %s" % (row["pr"], tag, row["status"])
    if row["status"] == "OK":
        not_run = ", not_run %d" % row["not_run"] if row.get("not_run") else ""
        return "%s  made %d, killed %d, crashed %d, survived %d%s  %s" % (
            head, row["made"], row["killed"], row["crashed"], row["survived"], not_run, row["title"])
    if row["status"] == "UNKNOWN":
        return "%s  %s  %s" % (head, row["reason"], row["title"])
    return "%s  %s" % (head, row["title"])


def format_replay_row(row: dict) -> str:
    """One pull request: its line, then each survivor, unusable suite, skipped file and note on a line of its own.
    An UNKNOWN row shows its reason and no rate."""
    lines = [_row_line(row)]
    for path, line, label in row.get("survivors", []):
        lines.append("  #%d %s:%d %s" % (row["pr"], path, line, label))
    for suite, why in sorted(row.get("unusable", {}).items()):
        lines.append("  unusable #%d %s (%s)" % (row["pr"], suite, why))
    for path, why in sorted(row.get("skipped", {}).items()):
        lines.append("  skipped #%d %s (%s)" % (row["pr"], path, why))
    for note in row.get("notes", []):
        lines.append("  note #%d %s" % (row["pr"], note))
    return "\n".join(lines)


def format_replay(rows) -> str:
    """The replay table: a header, then each row as `format_replay_row` writes it, then one totals line over
    the scored rows (counts, never a rate; none when no row is scored)."""
    lines = ["replay of %d merged pull requests" % len(rows)]
    lines.extend(format_replay_row(row) for row in rows)
    scored = [row for row in rows if row["status"] == "OK"]
    if scored:
        not_run = sum(r.get("not_run", 0) for r in scored)
        lines.append("scored %d: killed %d of %d mutants run (%d crashed, %d survived%s)" % (
            len(scored), sum(r["killed"] for r in scored), sum(r["made"] - r.get("not_run", 0) for r in scored),
            sum(r["crashed"] for r in scored), sum(r["survived"] for r in scored),
            ", %d not_run" % not_run if not_run else ""))
    return "\n".join(lines)


def changed_summary(rows) -> dict:
    """The totals of the rows that `--changed` scored: made, killed, crashed, survived, not_run, and `untested`, the
    sorted unique `path:line` of each line with a mutant that survived or was not run. A line with one killed and one
    surviving mutant is untested: the share counts mutants, and the list names the lines where a wrong edit got through."""
    total = {key: sum(row.get(key, 0) for row in rows) for key in ("made", "killed", "crashed", "survived", "not_run")}
    lines = {(path, line) for row in rows for path, line, _label in row.get("survivors", []) + row.get("not_run_at", [])}
    total["untested"] = ["%s:%d" % pair for pair in sorted(lines)]
    return total


def format_changed(rows) -> str:
    """The `--changed` report: each row as `format_replay_row` writes it, then one `catch share: K/R` line (K killed over R
    mutants that ran, a crash is no kill; a percentage only when R is above 0, so UNKNOWN never reads as a rate), then one
    `untested: path:line` line for each untested line."""
    total = changed_summary(rows)
    ran = total["made"] - total["not_run"]
    lines = [format_replay_row(row) for row in rows]
    share = "%.1f%%" % (100.0 * total["killed"] / ran) if ran else ""
    lines.append("catch share: %d/%d%s" % (total["killed"], ran, " (%s)" % share if share else ""))
    lines.extend("untested: %s" % where for where in total["untested"])
    return "\n".join(lines)


def run_known_defects(repo: str, defects, profile: dict, deps: str, suite_timeout: float = 120) -> list:
    """Replay planted defects against a clone's HEAD. Each defect is {id, name, file, old, new, argv, classify}: `old` is the one
    text in `file` that the plant replaces with `new`, and `argv` is the catcher suite, read by the classifier `classify`.
    Returns [{id, name, verdict, reason}] with the verdict CAUGHT (the suite prints an assertion on the planted copy), MISS
    (the suite passed, crashed or timed out on it) or UNKNOWN (the anchor is stale or ambiguous, the entry is malformed, the
    suite is not green on the clean copy, or the install or its link failed). Only an assertion catches, as in a replay. The run
    is in a checkout of HEAD made like a replay's, so the working tree and the repository are left as found.
    The checkout is prepared as `--changed` prepares its own. For each part of `profile` (the values of a `parts` profile, else
    the profile itself) the install runs under `deps`, a folder the caller removes, and its folder is linked beside the
    lockfile. Parts with one lockfile and one install share one install and one link; any other install runs once more. When an
    install or a link fails, every defect reads UNKNOWN and its reason names the install and the cause."""
    if not defects:
        return []
    sha = _git(repo, "rev-parse", "HEAD").strip()
    own = tempfile.mkdtemp(prefix="mutate_defects_")
    dest = os.path.join(own, "w")
    results = []

    def all_unknown(reason: str) -> list:
        return [{"id": str(d.get("id", "?")) if isinstance(d, dict) else "?",
                 "name": str(d.get("name", "")) if isinstance(d, dict) else "", "verdict": "UNKNOWN", "reason": reason}
                for d in defects]

    try:
        _make_checkout(repo, sha, dest, set(), {}, None, {})
        for part in (list(profile["parts"].values()) if "parts" in profile else [profile]):
            folder, why = _ensure_deps(repo, sha, part, deps)
            if why:
                return all_unknown("the install of the profile failed: %s" % why)
            try:
                _link_deps(dest, folder, part)
            except OSError as error:
                return all_unknown("the install could not be linked into the checkout: %s" % error)
        for defect in defects:
            results.append(_known_defect(dest, defect, suite_timeout))
    finally:
        _drop_checkout(repo, dest)
        shutil.rmtree(own, ignore_errors=True)
    return results


def _known_defect(dest: str, defect: dict, suite_timeout: float) -> dict:
    """One planted defect in checkout `dest`, which is left as it was found."""
    result = {"id": str(defect.get("id", "?")), "name": str(defect.get("name", "")), "verdict": "UNKNOWN", "reason": ""}
    try:
        file, old, new, argv = defect["file"], defect["old"], defect["new"], list(defect["argv"])
        classify = CLASSIFIERS[defect["classify"]]
    except (KeyError, TypeError) as error:
        result["reason"] = "the entry is malformed: %s %s" % (type(error).__name__, error)
        return result
    try:
        path, text = find_anchor(dest, old, [file])
    except (StaleMutant, AmbiguousMutant) as error:
        result["reason"] = str(error)
        return result
    try:
        control = run_suite_file(dest, "", suite_timeout, argv=argv, classify=classify, cwd=dest)[0]
        if control != "pass":
            result["reason"] = "the suite is not green on the clean copy (%s)" % control
            return result
        apply_mutant(dest, old, new, [file])
        try:
            kind = run_suite_file(dest, "", suite_timeout, argv=argv, classify=classify, cwd=dest)[0]
        finally:
            _write(path, text)
    except OSError as error:
        result["reason"] = "the suite did not run: %s" % error
        return result
    result["verdict"] = "CAUGHT" if kind == "assert" else "MISS"
    if kind != "assert":
        result["reason"] = {"pass": "the suite passed on the planted defect", "crash": "the suite crashed with no assertion",
                            "timeout": "the suite passed the timeout"}.get(kind, kind)
    return result


def format_known_defects(results) -> str:
    """One `CAUGHT|MISS|UNKNOWN id: name [reason]` line for each defect, then a totals line. No defect reads one line."""
    if not results:
        return "no known defects listed"
    lines = ["%s %s: %s%s" % (r["verdict"], r["id"], r["name"], " [%s]" % r["reason"] if r["reason"] else "")
             for r in results]
    counts = {verdict: sum(1 for r in results if r["verdict"] == verdict) for verdict in ("CAUGHT", "MISS", "UNKNOWN")}
    lines.append("known defects: %d caught, %d miss, %d unknown" % (counts["CAUGHT"], counts["MISS"], counts["UNKNOWN"]))
    return "\n".join(lines)
