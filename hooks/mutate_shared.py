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
import os
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


def ast_mutants(source: str, limit=None, seed: int = 0):
    """Return up to `limit` [(label, mutated source)], one mutation each, repeatable for one seed.

    A mutant whose text equals the normalized source is equivalent and is left out. Raises SyntaxError
    when `source` does not parse: the caller reads that as UNKNOWN.
    """
    base = normalize(source)
    found = []
    for position in range(len(_sites(ast.parse(source)))):
        tree = ast.parse(source)  # a fresh tree per site, so each mutant holds exactly one change
        kind, node, index = _sites(tree)[position]
        what = _apply(tree, kind, node, index)
        line = getattr(node, "lineno", 0)
        text = ast.unparse(ast.fix_missing_locations(tree))
        if text != base:
            found.append(("L%d %s" % (line, what), text))
    if limit is not None and len(found) > limit:
        keep = sorted(random.Random(seed).sample(range(len(found)), limit))
        found = [found[i] for i in keep]
    return found


def classify_run(code, output: str, timed_out: bool) -> str:
    """One suite run: "pass", "assert" (a FAIL line, an assertion went red), "crash" (red with no FAIL
    line: a throw, an import error) or "timeout". Only "assert" is evidence a mutant was caught."""
    if timed_out:
        return "timeout"
    if code == 0:
        return "pass"
    return "assert" if FAIL_LINE.search(output) else "crash"


def run_suite_file(folder: str, rel: str, timeout: float):
    """Run one suite as `python3 <rel>` from `folder`. Return (class, seconds). The child gets its own
    process group, killed whole at the timeout. Output goes to a file: a grandchild that holds a pipe
    open would make a pipe read wait for it."""
    import _nowindow  # lazy: this module defines names only at import (see the docstring)
    env = {k: v for k, v in os.environ.items() if not k.endswith("_UNDER_TEST") and k != "MUTATE_ONLY"}
    started = time.time()
    timed_out = False
    with tempfile.TemporaryFile() as log:
        extra = {"start_new_session": True} if os.name == "posix" else {}
        proc = _nowindow.Popen([sys.executable, os.path.join(folder, rel)], cwd=folder, stdout=log,
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
    return classify_run(proc.returncode, output, timed_out), time.time() - started


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
