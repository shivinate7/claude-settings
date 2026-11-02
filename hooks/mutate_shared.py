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
    proc_env.py, the one home of the exec-environment session-tag read."""
    shared = [os.path.join(folder, name) for name in ("git_reads.py", "proc_env.py")]
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


def find_anchor(folder: str, old: str):
    """Return (path, text) of the one guard module or git_reads.py in `folder` that holds `old`
    exactly once. Raise StaleMutant on zero matches, AmbiguousMutant on two or more, across all."""
    hits = []
    for path in anchor_files(folder):
        # Universal newlines: a checkout may hold CRLF, and an anchor spells a line break "\n".
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        hits.extend([(path, text)] * text.count(old))
    if not hits:
        raise StaleMutant("STALE: anchor text is in no guard module in %s" % folder)
    if len(hits) > 1:
        raise AmbiguousMutant("anchor text matches %d times in %s" % (
            len(hits), ", ".join(sorted({os.path.basename(p) for p, _ in hits}))))
    return hits[0]


def apply_mutant(tree: str, old: str, new: str) -> str:
    """Replace `old` with `new` in the one guard module in `tree` that holds it. Return its path.
    Write nothing when the anchor is stale or ambiguous (see find_anchor)."""
    path, text = find_anchor(tree, old)
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


def report_verdict(label: str, code, red, required: str) -> str:
    """Classify and print one mutant's verdict. Returns "survived", "wrong_cause", or "killed".

    A nonzero exit plus any red line is not proof, because every red line may belong to some OTHER
    case than the one the mutation's label names. `required` is the case
    name (or a distinctive fragment of it) that must appear among the suite's own FAIL lines
    before a kill counts as proof; a red suite that misses it is WRONG CAUSE, not KILLED.
    A WRONG CAUSE also prints the red lines it actually saw, bounded by WRONG_CAUSE_LINES_SHOWN, because a bare count says
    nothing about which case broke.
    """
    if code == 0 or not red:
        print("SURVIVED    %-62s %2d red" % (label, len(red)), flush=True)
        return "survived"
    if not any(required in line for line in red):
        print("WRONG CAUSE %-62s %2d red, missing %r" % (
            label, len(red), required), flush=True)
        for line in red[:WRONG_CAUSE_LINES_SHOWN]:
            print("            saw: %s" % line.strip(), flush=True)
        if len(red) > WRONG_CAUSE_LINES_SHOWN:
            print("            saw: ... and %d more" % (
                len(red) - WRONG_CAUSE_LINES_SHOWN), flush=True)
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


def run_mutants(entries, run_one):
    """Run every entry through `run_one`, in parallel, printing each mutant's verdict as it
    lands, then the tally line. Returns 0 when every mutant was killed (a caller's own `main`
    should return that, or 1 otherwise), so a caller can end with
    `return mutate_shared.run_mutants(MUTATIONS, run_one)`.

    `run_one(entry) -> (label, code, red, required, skip)` is supplied by the caller: it applies
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
        for label, code, red, required, skip in pool.map(run_one, entries):
            if skip:
                skipped += 1
                print("SKIPPED     %-62s %s" % (label, skip), flush=True)
                continue
            status = report_verdict(label, code, red, required)
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
    for position in range(len(_sites(ast.parse(source)))):
        tree = ast.parse(source)  # a fresh tree per site, so each mutant holds exactly one change
        kind, node, index = _sites(tree)[position]
        line = getattr(node, "lineno", 0)
        if wanted is not None and line not in wanted:
            continue
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
    import _nowindow  # lazy: this module defines names only at import (see the docstring)
    env = {k: v for k, v in os.environ.items() if not k.endswith("_UNDER_TEST") and k != "MUTATE_ONLY"}
    # No bytecode: a mutant of the same size and second as the clean file would load the clean .pyc.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    command = argv or [sys.executable, os.path.join(folder, rel)]
    started = time.time()
    timed_out = False
    with tempfile.TemporaryFile() as log:
        extra = {"start_new_session": True} if os.name == "posix" else {}
        proc = _nowindow.Popen(command, cwd=cwd or folder, stdout=log,
                               stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env, **extra)
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                if os.name == "posix":
                    os.killpg(proc.pid, signal.SIGKILL)
                else:
                    proc.kill()
            except OSError:
                proc.kill()
            proc.wait()
        log.seek(0)
        output = log.read().decode("utf-8", "replace")
    return (classify or classify_run)(proc.returncode, output, timed_out), time.time() - started


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
    killed none], unusable {suite: why}. See the report-mode comment above for what counts as a kill.
    """
    row = {"file": target, "status": "UNKNOWN", "reason": "", "made": 0, "killed": 0, "crashed": 0,
           "survived": 0, "rate": None, "killers": {}, "silent": [], "unusable": {}}
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
# per job, one install per lockfile hash. Written: a temp folder of checkouts and one deps folder
# per lockfile hash, all removed at the end. The target repository is left as found.
#
# A PROFILE says how one repository is read: {"code": regex of product files, "code_not": regex of
# files to leave out (optional), "tests": regex of suite files, "argv": the command with {suite} (the
# suite path from `cwd`) and {deps} (the install folder), "classify": a CLASSIFIERS name, "cwd": the folder
# the command runs in (optional), "install": argv, or a list of argv, run once per lockfile hash with the
# lockfile beside it in the deps folder (None for no install), "lockfile": its path in the repository,
# "link": the folder the install makes, linked into each checkout beside the lockfile (None for none),
# "sparse_skip": top folders left out of each checkout}. A profile of {"parts": {name: profile}} runs
# each part and keeps the rows that hold something.

INSTALL_TIMEOUT = 900
_MERGE_SUBJECT = re.compile(r"^Merge pull request #(\d+) from ")
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_PW_FAILURE = re.compile(r"^\s*\d+\) .* ─{3,}\s*$", re.M)
_PW_ASSERT = re.compile(r"\bexpect\((?:received|locator|page|response)\)|AssertionError|ERR_ASSERTION")


def classify_playwright(code, output: str, timed_out: bool) -> str:
    """One `playwright test` run: "pass", "assert" (a failure block holds an `expect(received)` matcher
    line or an AssertionError), "crash" (any other red: a load error, a throw, no test found) or
    "timeout". Only "assert" is evidence a mutant was caught."""
    if timed_out:
        return "timeout"
    if code == 0:
        return "pass"
    text = _ANSI.sub("", output)
    starts = [m.start() for m in _PW_FAILURE.finditer(text)] + [len(text)]
    for begin, end in zip(starts, starts[1:]):
        if _PW_ASSERT.search(text[begin:end]):
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


def _ensure_deps(repo: str, sha: str, profile: dict, deps_root: str):
    """The install folder for `sha`'s lockfile: (folder or None, why it is unusable). The install runs once
    per lockfile hash under `deps_root`, with the lockfile (and its package.json) beside it."""
    install = profile.get("install")
    if not install:
        return None, ""
    import _nowindow
    lock = profile.get("lockfile", "package-lock.json")
    try:
        data = _file_at(repo, sha, lock)
    except ValueError:
        return None, "no lockfile %s at this commit" % lock
    folder = os.path.join(deps_root, hashlib.sha1(data).hexdigest()[:16])
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
            run = _nowindow.run(argv, cwd=folder, capture_output=True, text=True, encoding="utf-8",
                                stdin=subprocess.DEVNULL, timeout=INSTALL_TIMEOUT)
            why = "" if run.returncode == 0 else "install exited %d: %s" % (
                run.returncode, (run.stderr or run.stdout).strip()[-300:])
        except (OSError, subprocess.TimeoutExpired) as error:
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
    link_name = profile.get("link", "node_modules")
    if deps and link_name:
        link = os.path.join(dest, os.path.dirname(profile.get("lockfile", "package-lock.json")), link_name)
        os.makedirs(os.path.dirname(link), exist_ok=True)
        os.symlink(os.path.join(deps, link_name), link)


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
            "killed": 0, "crashed": 0, "survived": 0, "survivors": [], "unusable": {}, "skipped": {}}


def replay_pr(repo: str, sha: str, profile: dict, limit: int = 20, seed: int = 0, suite_timeout: float = 120,
              jobs=None, deps=None) -> dict:
    """Score the suites the pull request merged at `sha` changed against mechanical mutants of the product
    lines it added. Returns a row: pr, sha, title, status ("OK", "UNKNOWN", "NO_PRODUCT" for no product
    file changed, "NO_TESTS" for product code with no suite changed), reason, made, killed, crashed,
    survived, survivors [(path, line, label)], unusable {suite: why}, skipped {file: why}.
    `deps` is a folder shared by many calls, for the installs; None makes one and removes it.
    A run is read as in report mode: only an assertion kills, and an unusable suite is not a killer."""
    row = _replay_row(repo, sha)
    code_re, tests_re = re.compile(profile["code"]), re.compile(profile["tests"])
    not_re = re.compile(profile["code_not"]) if profile.get("code_not") else None
    base = "%s^1" % sha
    try:
        files = _changed_files(repo, base, sha)
    except ValueError as error:
        row["reason"] = "cannot read the diff: %s" % error
        return row
    code = sorted(p for p, s in files.items() if s != "D" and code_re.search(p) and not (not_re and not_re.search(p)))
    suites = sorted(p for p, s in files.items() if s != "D" and tests_re.search(p))
    if not code:
        row["status"] = "NO_PRODUCT"
        return row
    if not suites:
        row["status"] = "NO_TESTS"
        return row

    own = tempfile.mkdtemp(prefix="mutate_replay_")
    try:
        return _replay_in(repo, sha, profile, row, code, suites, base, own, limit, seed, suite_timeout,
                          jobs or job_count(), deps or os.path.join(own, "deps"))
    finally:
        shutil.rmtree(own, ignore_errors=True)


def _replay_in(repo, sha, profile, row, code, suites, base, own, limit, seed, suite_timeout, jobs, deps):
    """The body of `replay_pr`, inside the temp folder `own`."""
    clean = {}  # path -> the text a clean run holds: the source, or its normalized form for Python
    found, parse_errors = [], {}
    for path in code:
        text = _file_at(repo, sha, path).decode("utf-8")
        try:
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
        except (SyntaxError, ValueError) as error:
            parse_errors[path] = "parse error: %s" % str(error).strip().splitlines()[0]
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
        if not usable:
            row["reason"] = "no suite is green on the clean source"
            return row
        usable = [suite for _seconds, suite in sorted(usable)]  # the quickest first: the first assertion ends a mutant
        bound = min(suite_timeout, max(10.0, 5 * slowest))

        def score(dest, mutant):
            path, _label, text = mutant
            _write(os.path.join(dest, path), text)
            try:
                kinds = set()
                for suite in usable:
                    kind = run_one(dest, suite, bound)[0]
                    kinds.add(kind)
                    if kind == "assert":
                        break
                return kinds
            finally:
                _write(os.path.join(dest, path), clean[path])

        with ThreadPoolExecutor(max_workers=count) as pool:
            outcomes = list(pool.map(lambda mutant: borrow(lambda dest: score(dest, mutant)), mutants))
    finally:
        for dest in made_dirs:
            _drop_checkout(repo, dest)

    for (path, label, _text), kinds in zip(mutants, outcomes):
        if "assert" in kinds:
            row["killed"] += 1
        elif kinds & {"crash", "timeout"}:
            row["crashed"] += 1
        else:
            row["survived"] += 1
            row["survivors"].append((path, _line_of(label), label))
    row["made"] = len(mutants)
    row["status"] = "OK"
    return row


def replay_profile(repo: str, sha: str, profile: dict, **options) -> list:
    """The rows of one pull request under `profile`: one row, or for a profile of parts the rows of the parts
    that hold something (a part that sees no product file is left out, unless every part sees none)."""
    if "parts" not in profile:
        return [replay_pr(repo, sha, profile, **options)]
    rows = []
    for name, part in profile["parts"].items():
        row = replay_pr(repo, sha, part, **options)
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
        return "%s  made %d, killed %d, crashed %d, survived %d  %s" % (
            head, row["made"], row["killed"], row["crashed"], row["survived"], row["title"])
    if row["status"] == "UNKNOWN":
        return "%s  %s  %s" % (head, row["reason"], row["title"])
    return "%s  %s" % (head, row["title"])


def format_replay_row(row: dict) -> str:
    """One pull request: its line, then each survivor, unusable suite and skipped file on a line of its own.
    An UNKNOWN row shows its reason and no rate."""
    lines = [_row_line(row)]
    for path, line, label in row.get("survivors", []):
        lines.append("  #%d %s:%d %s" % (row["pr"], path, line, label))
    for suite, why in sorted(row.get("unusable", {}).items()):
        lines.append("  unusable #%d %s (%s)" % (row["pr"], suite, why))
    for path, why in sorted(row.get("skipped", {}).items()):
        lines.append("  skipped #%d %s (%s)" % (row["pr"], path, why))
    return "\n".join(lines)


def format_replay(rows) -> str:
    """The replay table: a header, then each row as `format_replay_row` writes it, then one totals line over
    the scored rows (counts, never a rate; none when no row is scored)."""
    lines = ["replay of %d merged pull requests" % len(rows)]
    lines.extend(format_replay_row(row) for row in rows)
    scored = [row for row in rows if row["status"] == "OK"]
    if scored:
        lines.append("scored %d: killed %d of %d mutants (%d crashed, %d survived)" % (
            len(scored), sum(r["killed"] for r in scored), sum(r["made"] for r in scored),
            sum(r["crashed"] for r in scored), sum(r["survived"] for r in scored)))
    return "\n".join(lines)
