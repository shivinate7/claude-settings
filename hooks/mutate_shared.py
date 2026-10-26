#!/usr/bin/env python3
"""Plumbing shared by hooks/mutate_guard.py and janitor/mutate_sweep.py.

Both files run the same shape of mutation test: apply one literal string replacement to a
source file, run a fixture suite against the mutated copy, and classify the result as KILLED,
SURVIVED, or WRONG CAUSE (a red suite whose FAIL lines never name the case the mutation's label
claims to break). Before this module, `safe_name`, `job_count`, `skip_reason`, and the
SURVIVED / WRONG CAUSE verdict-and-tally printing were each written out twice, and the two
copies had already started to drift: janitor/mutate_sweep.py's own `safe_name` lacked the
digest suffix hooks/mutate_guard.py's carries (see `safe_name` below), so the exact filename
collision that suffix was written to fix could still happen on the janitor side. Importing this
module instead of a second copy is what closes that gap for good, not just for today.

STDLIB ONLY, AND NOTHING RUNS AT IMPORT TIME beyond defining these names. Both callers are
gates: an import error or a syntax error here takes both mutation tests down at once instead of one,
so this file stays small, has no side effects on import, and takes on no new dependency.

What stays OUT of this module, and why: `mutation_parts` and `run_mutant` are NOT shared, even
though both files name a function by that name. Each file's own `MUTATIONS` list packs its
entry tuples in a different field order (hooks/mutate_guard.py: label, old, new, target?,
required?, only_on?, target defaulting to "guard"; janitor/mutate_sweep.py: label, target, old,
new, required, only_on?, target always required) and `run_mutant` mutates one bare file in one
case and lays out a whole multi-file scaffold directory in the other. Forcing those into one
shared shape means either reordering hundreds of literal mutation tuples that are themselves the
tested gate content (the reordering itself becoming a real chance to misfile a field and quietly
weaken a mutation), or writing a shared function that takes the field order as a parameter,
which recreates the duplication as a configuration option instead of removing it. Neither closes
real duplication; both add the fragility this module exists to avoid. They stay two local
functions, each shaped by its own file's `MUTATIONS`.
"""
import glob
import hashlib
import os
import shutil
import sys
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
    """Run one mutant's suite in two stages. `run(only) -> (code, red)`: `only` is the required
    case fragment to run alone, or None for the full suite.

    Stage 1 runs only the cases named by `required`. A nonzero exit with `required` among the red
    lines is a kill, the same kill the full suite would report, so stop there. Anything else
    (cases pass, none selected, red without the name) falls to the full suite, whose result is
    the verdict, exactly as before. MUTATE_FULL=1 skips stage 1, for debugging the old mode.
    """
    if os.environ.get("MUTATE_FULL"):
        return run(None)
    code, red = run(required)
    if code != 0 and any(required in line for line in red):
        return code, red
    return run(None)


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
