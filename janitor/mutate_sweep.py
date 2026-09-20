#!/usr/bin/env python3
"""Mutation test for janitor/sweep.py and hooks/guard.py's sweep-facing primitives.

Stdlib only. Ported from hooks/mutate_guard.py (555 lines, read first): same shape, same
vocabulary (KILLED / SURVIVED / WRONG CAUSE), same fifth field (the required case name a
mutant's own FAIL lines must carry, so a kill on an unrelated case never counts as proof).

WHY THIS FILE EXISTS. janitor/test_sweep.py merged with 31 arms. The builder mutated 22
assertions BY HAND, reported 22 kills, and committed nothing: no later reader can reproduce
that evidence (plan, "the refusals"; CLAUDE.md, "trust a guard only once it goes red on the
defect it guards"). This harness makes the claim reproducible: `python3 janitor/mutate_sweep.py`
either kills every mutant below or names the ones it does not.

WHY TWO TARGETS, NOT ONE. janitor/sweep.py holds no code of its own for the ancestor test, the
`git cherry` patch test, the remote-contains test, or the pid-vs-start-time liveness read: it
calls hooks/guard.py's own tested primitives for every one of those (sweep.py's own docstring,
"the one outcome to avoid"). A mutation harness that only ever edited sweep.py could not touch
any of those four protections at all, and the build brief names all four by name. So a mutant
here carries a TARGET ("sweep" or "guard") and this file mutates a copy of whichever file
actually holds the line, the same file guard.py's own line 8 explains sweep.py leans on.

WHY A SCAFFOLD DIRECTORY, NOT AN ENV VAR. hooks/test_guard.py and hooks/test_config_watch.py
each read a `*_UNDER_TEST` environment variable naming the copy to import instead of the real
file (see hooks/mutate_guard.py's own TARGETS table). janitor/test_sweep.py has no such
variable, and the fence around this build forbids adding one: `janitor/mutate_sweep.py` and
`.github/workflows/gates.yml` are the only files this build may touch. So this harness rebuilds
the two-directory shape (`hooks/`, `janitor/`) that `janitor/test_sweep.py` already computes
its own import path from (`HERE = dirname(test_sweep.py)`, `REPO_ROOT = dirname(HERE)`,
`sys.path.insert(0, REPO_ROOT/hooks)`) inside a fresh temporary directory per mutant, and copies
the REAL `janitor/test_sweep.py` into it byte for byte, unmodified. Running that copy from that
scaffold makes `import sweep` and `import guard` resolve to whichever copies -- mutated or real
-- this harness placed next to it. The real `janitor/test_sweep.py` on disk is never touched,
and nothing is ever left behind: see `run_mutant` and `main`'s `finally`.

A MUTATION WHOSE ANCHOR TEXT IS NOT FOUND is STALE and fails loudly, the same rule
hooks/mutate_guard.py enforces, checked for every mutation before any suite runs.

A RED SUITE IS NOT ENOUGH. `janitor/test_sweep.py` runs as plain `unittest.main(verbosity=2)`,
which prints its per-case progress and its failure headings to STDERR, not STDOUT (unlike
hooks/test_guard.py's own hand-rolled PASS/FAIL runner). Both streams are scanned here for
lines containing "FAIL", and a mutant's death only counts when the required case name shows up
in one of them: a mutant that crashes the suite, or that some UNRELATED case happens to catch,
is WRONG CAUSE, not KILLED, kept distinct exactly as hooks/mutate_guard.py keeps it distinct.

ONE KNOWN SURVIVOR, NAMED ON PURPOSE: "sweep_repo: reap branches without --confirm". No case in
janitor/test_sweep.py calls `sweep.sweep_repo` with `confirm=False` against a repository that
actually holds a reapable branch or worktree (its three `confirm=False` calls all hit a
REFUSED repository -- no-default-base, opted-out, unreadable-optout -- before either loop
runs; its two `confirm=True` calls never have a `confirm=False` twin). This mutant --
`if confirm and decision["action"] == "reap":` with the `confirm and` dropped -- is MEASURED
against the current suite (see the build report) to run every branch decision for real, with
no `--confirm` on the command line, and 31 of 31 cases still pass. That is not a bug in this
harness: rule 1 below says a mutant no arm kills is a survivor and the run must say so, not
quietly drop the mutant or swap in an easier one. It stays in MUTATIONS, it is named as a
SURVIVOR, and the run exits 1 for it. Fixing the gap means adding a case to
janitor/test_sweep.py, which sits outside this build's fence; the build report raises it as
Input Needed instead of silently filing past it.

Run:
    python3 janitor/mutate_sweep.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
SWEEP = os.path.join(HERE, "sweep.py")
SUITE = os.path.join(HERE, "test_sweep.py")
GUARD = os.path.join(REPO_ROOT, "hooks", "guard.py")

SOURCES = {"sweep": SWEEP, "guard": GUARD}

# (label, target, anchor text found once in the source, its mutated replacement, the case name
# (or a distinctive fragment of it) that MUST appear among the suite's own FAIL lines). One
# mutant per PROTECTION, not per line: the seven refusals, the keep rule in both directions, the
# only-copy remote-contains test, the pid-vs-start-time liveness read, the tombstone's write
# order, the purge's age source, and the --confirm gate. `target` says which file's copy carries
# the anchor: "sweep" for janitor/sweep.py's own code, "guard" for the hooks/guard.py primitive
# sweep.py calls and never re-implements (see the module docstring above).
MUTATIONS = [
    # ---- the seven refusals (plan, "the refusals") ----
    ("refusal: the protected prefix never keeps a branch",
     "sweep",
     '    for prefix in protected_prefixes:\n'
     '        if branch.startswith(prefix):\n'
     '            return {"name": branch, "action": "keep", "reason": "protected-prefix:" + prefix}',
     '    for prefix in protected_prefixes:\n'
     '        if False:\n'
     '            return {"name": branch, "action": "keep", "reason": "protected-prefix:" + prefix}',
     "test_refusal_protected_prefix"),
    ("refusal: a checked-out branch is reaped anyway",
     "sweep",
     '    if branch in checked_out_branches:\n'
     '        return {"name": branch, "action": "keep", "reason": "checked-out"}',
     '    if branch in checked_out_branches and False:\n'
     '        return {"name": branch, "action": "keep", "reason": "checked-out"}',
     "test_refusal_checked_out_branch"),
    ("refusal: a dirty worktree no longer keeps",
     "sweep",
     '    if dirty:\n'
     '        return {"path": path, "action": "keep", "reason": "dirty"}',
     '    if False:\n'
     '        return {"path": path, "action": "keep", "reason": "dirty"}',
     "test_refusal_dirty_worktree"),
    ("refusal: a live session no longer keeps its worktree",
     "sweep",
     '    if live:\n'
     '        return {"path": path, "action": "keep", "reason": "live-session"}',
     '    if False:\n'
     '        return {"path": path, "action": "keep", "reason": "live-session"}',
     "test_refusal_live_session_worktree"),
    ("refusal: a locked worktree no longer keeps",
     "sweep",
     '    if locked:\n'
     '        holder = entry.get("locked_reason") or "locked"',
     '    if False:\n'
     '        holder = entry.get("locked_reason") or "locked"',
     "test_refusal_locked_worktree_names_its_holder"),
    ("refusal: main/master is no longer exempt",
     "sweep",
     '    if branch in ("main", "master"):\n'
     '        return {"name": branch, "action": "keep", "reason": "default-branch"}',
     '    if branch in ("no-such-default-branch",):\n'
     '        return {"name": branch, "action": "keep", "reason": "default-branch"}',
     "test_refusal_default_branch_itself"),
    ("refusal: an unreadable branch subject reaps instead of keeping",
     "sweep",
     '    empty = guard.branch_is_empty(where, base, branch)\n'
     '    if empty is None:\n'
     '        return {"name": branch, "action": "keep", "reason": "unreadable-subject"}',
     '    empty = guard.branch_is_empty(where, base, branch)\n'
     '    if False:\n'
     '        return {"name": branch, "action": "keep", "reason": "unreadable-subject"}',
     "test_refusal_unreadable_subject_is_kept"),
    # decide_worktree reads "unreadable" three times over (dirty, locked, live), each one its
    # own `is None` guard: hooks/test_guard.py's own blind-git fixture makes EVERY git call fail
    # at once, so knocking out only the FIRST guard is masked by the second (still None, for the
    # same blind reason) -- MEASURED, not assumed: an earlier version of this mutant that dropped
    # only the `dirty is None` guard survived with 0 red lines, because `worktree_locked` read
    # against the same blind git also came back None and returned "unreadable-subject" anyway.
    # This mutant instead drops all three guards at once, the only way to make this protection
    # (an unreadable subject KEEPS, never reaps) actually absent under that fixture.
    ("refusal: no unreadable worktree subject keeps any more (all three reads)",
     "sweep",
     'def decide_worktree(where: str, entry: dict):\n'
     '    """Return one decision dict: {"path", "action": "reap"|"keep", "reason"}."""\n'
     '    path = entry["path"]\n'
     '    dirty = guard.porcelain(path)\n'
     '    if dirty is None:\n'
     '        return {"path": path, "action": "keep", "reason": "unreadable-subject"}\n'
     '    if dirty:\n'
     '        return {"path": path, "action": "keep", "reason": "dirty"}\n'
     '    locked = guard.worktree_locked(where, path)\n'
     '    if locked is None:\n'
     '        return {"path": path, "action": "keep", "reason": "unreadable-subject"}\n'
     '    if locked:\n'
     '        holder = entry.get("locked_reason") or "locked"\n'
     '        return {"path": path, "action": "keep", "reason": "locked: %s" % holder}\n'
     '    live = guard.worktree_live_session(path)\n'
     '    if live is None:\n'
     '        return {"path": path, "action": "keep", "reason": "unreadable-subject"}\n'
     '    if live:\n'
     '        return {"path": path, "action": "keep", "reason": "live-session"}\n'
     '    return {"path": path, "action": "reap", "reason": "removable"}',
     'def decide_worktree(where: str, entry: dict):\n'
     '    """Return one decision dict: {"path", "action": "reap"|"keep", "reason"}."""\n'
     '    path = entry["path"]\n'
     '    dirty = guard.porcelain(path)\n'
     '    if False:\n'
     '        return {"path": path, "action": "keep", "reason": "unreadable-subject"}\n'
     '    if dirty:\n'
     '        return {"path": path, "action": "keep", "reason": "dirty"}\n'
     '    locked = guard.worktree_locked(where, path)\n'
     '    if False:\n'
     '        return {"path": path, "action": "keep", "reason": "unreadable-subject"}\n'
     '    if locked:\n'
     '        holder = entry.get("locked_reason") or "locked"\n'
     '        return {"path": path, "action": "keep", "reason": "locked: %s" % holder}\n'
     '    live = guard.worktree_live_session(path)\n'
     '    if False:\n'
     '        return {"path": path, "action": "keep", "reason": "unreadable-subject"}\n'
     '    if live:\n'
     '        return {"path": path, "action": "keep", "reason": "live-session"}\n'
     '    return {"path": path, "action": "reap", "reason": "removable"}',
     "test_refusal_unreadable_subject_worktree"),

    # ---- the keep rule, both directions (plan, "Phase 2") ----
    ("keep rule: the ancestry test never proves a branch empty",
     "guard",
     '    answer = _git(where, "merge-base", "--is-ancestor", branch, base)\n'
     '    if answer is None:\n'
     '        return None\n'
     '    if answer.returncode == 0:\n'
     '        return True\n'
     '    if answer.returncode == 1:\n'
     '        return False\n'
     '    return None',
     '    answer = _git(where, "merge-base", "--is-ancestor", branch, base)\n'
     '    if answer is None:\n'
     '        return None\n'
     '    return False',
     "test_ancestor_reaps"),
    ("keep rule: the git-cherry patch test never proves a branch empty",
     "guard",
     '    answer = _git(where, "cherry", base, branch)\n'
     '    if answer is None or answer.returncode != 0:\n'
     '        return None\n'
     '    return not any(line.startswith("+") for line in answer.stdout.splitlines())',
     '    answer = _git(where, "cherry", base, branch)\n'
     '    if answer is None or answer.returncode != 0:\n'
     '        return None\n'
     '    return False',
     "test_the_patch_test_sees_through_the_rebase_and_reaps"),

    # ---- the only-copy rule (plan, "Phase 2") ----
    ("only-copy: stop asking whether a remote carries the branch",
     "guard",
     '    answer = _git(\n'
     '        where, "for-each-ref", "--contains", branch, "--format=%(refname)", "refs/remotes"\n'
     '    )\n'
     '    if answer is None or answer.returncode != 0:\n'
     '        return None\n'
     '    return bool(answer.stdout.strip())',
     '    answer = _git(\n'
     '        where, "for-each-ref", "--contains", branch, "--format=%(refname)", "refs/remotes"\n'
     '    )\n'
     '    if answer is None or answer.returncode != 0:\n'
     '        return None\n'
     '    return False',
     "test_on_remote_reaps"),

    # ---- the liveness test (plan, "Phase 2") ----
    ("liveness: match the process id alone, ignore the recorded start time",
     "guard",
     '    if not isinstance(record, dict):\n'
     '        return False\n'
     '    pid = record.get("pid")\n'
     '    started = record.get("startedAt")\n'
     '    if not isinstance(started, (int, float)) or isinstance(started, bool):\n'
     '        return False\n'
     '    actual = _process_start_ms(pid)\n'
     '    if actual is None:\n'
     '        return False\n'
     '    return abs(actual - started) <= SESSION_LIVE_TOLERANCE_MS',
     '    if not isinstance(record, dict):\n'
     '        return False\n'
     '    pid = record.get("pid")\n'
     '    actual = _process_start_ms(pid)\n'
     '    return actual is not None',
     "test_mismatched_start_time_reads_as_dead_and_is_reapable"),

    # ---- the tombstone (plan, "Phase 2") ----
    ("tombstone: write the ref AFTER the delete instead of before",
     "sweep",
     'def reap_branch(root: str, branch: str, decision: dict, restore_log_path: str):\n'
     '    """Write the tombstone, log it, THEN delete. In that order: a delete that ran before its\n'
     '    tombstone landed could lose the branch\'s only pointer to work the log has not recorded yet."""\n'
     '    tip = guard._git(root, "rev-parse", "refs/heads/" + branch)\n'
     '    if tip is None or tip.returncode != 0:\n'
     '        decision["error"] = "could not resolve the branch tip; branch left alone"\n'
     '        return\n'
     '    commit = tip.stdout.strip()\n'
     '    tomb = guard._git(root, "update-ref", TOMBSTONE_REF_PREFIX + branch, commit)\n'
     '    if tomb is None or tomb.returncode != 0:\n'
     '        decision["error"] = "tombstone write failed; branch NOT deleted"\n'
     '        return\n'
     '    append_restore_log(restore_log_path, root, branch, commit)\n'
     '    delete = guard._git(root, "branch", "-D", branch)\n'
     '    if delete is None or delete.returncode != 0:\n'
     '        decision["error"] = "delete failed after the tombstone landed: %s" % (\n'
     '            delete.stderr.strip() if delete is not None else "git gave no answer"\n'
     '        )',
     'def reap_branch(root: str, branch: str, decision: dict, restore_log_path: str):\n'
     '    """MUTATED: delete first, tombstone after -- the ordering this mutant breaks."""\n'
     '    tip = guard._git(root, "rev-parse", "refs/heads/" + branch)\n'
     '    if tip is None or tip.returncode != 0:\n'
     '        decision["error"] = "could not resolve the branch tip; branch left alone"\n'
     '        return\n'
     '    commit = tip.stdout.strip()\n'
     '    delete = guard._git(root, "branch", "-D", branch)\n'
     '    if delete is None or delete.returncode != 0:\n'
     '        decision["error"] = "delete failed after the tombstone landed: %s" % (\n'
     '            delete.stderr.strip() if delete is not None else "git gave no answer"\n'
     '        )\n'
     '        return\n'
     '    tomb = guard._git(root, "update-ref", TOMBSTONE_REF_PREFIX + branch, commit)\n'
     '    if tomb is None or tomb.returncode != 0:\n'
     '        decision["error"] = "tombstone write failed; branch NOT deleted"\n'
     '        return\n'
     '    append_restore_log(restore_log_path, root, branch, commit)',
     "test_a_failed_delete_still_leaves_the_tombstone_and_the_branch"),
    ("tombstone: read the purge age from the ref's own mtime, not the restore log",
     "sweep",
     '        age_ms = now_ms - when',
     '        ref_path = os.path.join(repo, ".git", "refs", "janitor", "reaped", branch)\n'
     '        try:\n'
     '            mtime_ms = int(os.path.getmtime(ref_path) * 1000)\n'
     '        except OSError:\n'
     '            mtime_ms = now_ms\n'
     '        age_ms = now_ms - mtime_ms',
     "test_confirm_drops_a_tombstone_past_90_days"),

    # ---- --confirm (plan, "the refusals"). See the module docstring: MEASURED to survive. ----
    ("--confirm: reap branches for real with no --confirm on the line",
     "sweep",
     '    for branch in branches:\n'
     '        decision = decide_branch(root, base, branch, protected_prefixes, checked_out_branches)\n'
     '        result["branches"].append(decision)\n'
     '        if confirm and decision["action"] == "reap":\n'
     '            reap_branch(root, branch, decision, restore_log_path)',
     '    for branch in branches:\n'
     '        decision = decide_branch(root, base, branch, protected_prefixes, checked_out_branches)\n'
     '        result["branches"].append(decision)\n'
     '        if decision["action"] == "reap":\n'
     '            reap_branch(root, branch, decision, restore_log_path)',
     "test_reap_writes_a_tombstone_and_a_restore_log_line_before_deleting"),
]


def safe_name(label: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in label)[:60]


def mutation_parts(entry):
    """Return (label, target, old, new, required) for one mutation, enforcing the fifth field
    the same way hooks/mutate_guard.py's mutation_parts does: a mutation with no required case
    name is as unproven as one that dies wrong, so it is refused outright."""
    if len(entry) != 5:
        raise ValueError("mutation carries the wrong number of fields: %r" % (entry,))
    label, target, old, new, required = entry
    if target not in SOURCES:
        raise ValueError("mutation names an unknown target %r: %s" % (target, label))
    if not required:
        raise ValueError("mutation carries no required case name: %s" % label)
    return label, target, old, new, required


def build_scaffold(scaffold: str, sources: dict, mutated_target: str, mutated_text: str):
    """Lay out <scaffold>/hooks/guard.py and <scaffold>/janitor/{sweep.py,test_sweep.py} so that
    running <scaffold>/janitor/test_sweep.py resolves `import guard` and `import sweep` to the
    copies placed here (see the module docstring, "WHY A SCAFFOLD DIRECTORY"). Exactly one of
    guard.py / sweep.py carries `mutated_text`; the other is the real source, unchanged.
    test_sweep.py is always the real source, unchanged: this harness never edits the suite."""
    hooks_dir = os.path.join(scaffold, "hooks")
    janitor_dir = os.path.join(scaffold, "janitor")
    os.makedirs(hooks_dir, exist_ok=True)
    os.makedirs(janitor_dir, exist_ok=True)

    guard_text = mutated_text if mutated_target == "guard" else sources["guard"]
    sweep_text = mutated_text if mutated_target == "sweep" else sources["sweep"]

    with open(os.path.join(hooks_dir, "guard.py"), "w", encoding="utf-8", newline="\n") as h:
        h.write(guard_text)
    with open(os.path.join(janitor_dir, "sweep.py"), "w", encoding="utf-8", newline="\n") as h:
        h.write(sweep_text)
    with open(os.path.join(janitor_dir, "test_sweep.py"), "w", encoding="utf-8", newline="\n") as h:
        h.write(sources["test_sweep"])


def run_suite(suite_path: str, config_dir: str):
    """Run one scaffold's test_sweep.py. Return (exit code, FAIL lines from stdout+stderr).

    janitor/test_sweep.py is a plain `unittest.main(verbosity=2)`, which writes its per-case
    progress and its failure headings to STDERR by default -- unlike hooks/test_guard.py's own
    hand-rolled PASS/FAIL runner, which prints to stdout. Both streams are scanned here so a red
    line is never missed because of which stream unittest chose. `CLAUDE_CONFIG_DIR` is set only
    as a floor: setUpModule immediately overwrites it with its own fresh tempfile.mkdtemp()
    directory, so this value is never actually read once the suite is under way, and is set here
    only so nothing accidentally falls back to a real `~/.claude` before that line runs."""
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = config_dir
    result = subprocess.run(
        [sys.executable, suite_path], capture_output=True, text=True, env=env, timeout=1200,
    )
    red = [line for line in (result.stdout + result.stderr).splitlines() if "FAIL" in line]
    return result.returncode, red


def run_mutant(sources, work: str, index: int, entry):
    """Apply one mutation in its own scaffold, run the suite there, and return
    (label, code, FAIL lines, required)."""
    label, target, old, new, required = mutation_parts(entry)
    mutated_text = sources[target].replace(old, new, 1)
    scaffold = os.path.join(work, "m_%03d_%s" % (index, safe_name(label)))
    config_dir = os.path.join(scaffold, "cfg")
    os.makedirs(config_dir, exist_ok=True)
    try:
        build_scaffold(scaffold, sources, target, mutated_text)
        code, red = run_suite(os.path.join(scaffold, "janitor", "test_sweep.py"), config_dir)
        return label, code, red, required
    finally:
        shutil.rmtree(scaffold, ignore_errors=True)


def job_count() -> int:
    """How many suites to run at once: MUTATE_JOBS, else the CPU count, at least one. Same
    knob hooks/mutate_guard.py exposes, kept under the same name for one reader to know both."""
    try:
        wanted = int(os.environ.get("MUTATE_JOBS", "") or 0)
    except ValueError:
        wanted = 0
    return max(1, wanted or os.cpu_count() or 1)


def main() -> int:
    sources = {}
    for name, path in SOURCES.items():
        with open(path, encoding="utf-8") as handle:
            sources[name] = handle.read()
    with open(SUITE, encoding="utf-8") as handle:
        sources["test_sweep"] = handle.read()

    # Every anchor is checked before any suite runs, so a stale mutation fails in the first
    # second, not after the mutants ahead of it in the list have spent their minutes.
    for entry in MUTATIONS:
        label, target, old, _new, required = mutation_parts(entry)
        if old not in sources[target]:
            print("ERROR stale mutation, anchor text not found in %s: %s" % (target, label))
            return 1
        if not required:
            print("ERROR mutation carries no required case name: %s" % label)
            return 1

    work = tempfile.mkdtemp(prefix="mutate_sweep_")
    survivors = 0
    wrong_cause = 0
    jobs = job_count()
    print("%d mutations, %d at a time" % (len(MUTATIONS), jobs))
    try:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = [
                pool.submit(run_mutant, sources, work, i, entry)
                for i, entry in enumerate(MUTATIONS)
            ]
            for future in futures:
                label, code, red, required = future.result()
                if code == 0 or not red:
                    survivors += 1
                    print("SURVIVED    %-62s %2d red" % (label, len(red)), flush=True)
                elif not any(required in line for line in red):
                    wrong_cause += 1
                    print("WRONG CAUSE %-62s %2d red, missing %r" % (
                        label, len(red), required), flush=True)
                else:
                    print("KILLED      %-62s %2d red" % (label, len(red)), flush=True)
        print()
        killed = len(MUTATIONS) - survivors - wrong_cause
        print("%d of %d mutations killed (%d survived, %d wrong cause)" % (
            killed, len(MUTATIONS), survivors, wrong_cause))
        return 1 if (survivors or wrong_cause) else 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
