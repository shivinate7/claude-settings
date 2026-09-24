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

A THIRD TARGET, "session_end_sweep", covers the SessionEnd hook itself (janitor/session_end_
sweep.py), proven against its own suite (janitor/test_session_end_sweep.py) instead of
test_sweep.py -- see SUITE_FOR_TARGET below. Its scaffold additionally carries a copy of the
real REPO_ROOT/settings.json, never mutated, because that suite's own HookBudgetFitsUnderIts
HostCeiling arm reads it.

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

A FORMER KNOWN SURVIVOR, NOW CLOSED. "--confirm: reap branches for real with no --confirm on
the line" (`if confirm and decision["action"] == "reap":` with the `confirm and` dropped) once
survived: no case called `sweep.sweep_repo` with `confirm=False` against a repository holding
a reapable subject. `janitor/test_sweep.py`'s `ConfirmGateTests.test_preview_names_reapable_
subjects_but_touches_neither` closes that gap. MEASURED here: this mutant is KILLED, required
case included. This paragraph stays as a record that the gap was real, found, and closed, not
as a live warning: rule 1 below still says a mutant no arm kills is a survivor, and the run
still exits 1 the day a future edit reopens this gap.

Run:
    python3 janitor/mutate_sweep.py
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO_ROOT, "hooks"))
import mutate_shared  # noqa: E402

SWEEP = os.path.join(HERE, "sweep.py")
SUITE = os.path.join(HERE, "test_sweep.py")
GUARD = os.path.join(REPO_ROOT, "hooks", "guard.py")

# A third target, added for the SessionEnd hook's own two budget protections (remaining-time
# spend, and the upper-edge headroom guard): the hook has its own suite, test_session_end_sweep,
# which additionally reads the real REPO_ROOT/settings.json (HookBudgetFitsUnderItsHostCeiling)
# -- so its scaffold needs that file too, never mutated, copied alongside the rest.
SESSION_END_SWEEP = os.path.join(HERE, "session_end_sweep.py")
SESSION_END_SUITE = os.path.join(HERE, "test_session_end_sweep.py")
SETTINGS_JSON = os.path.join(REPO_ROOT, "settings.json")

SOURCES = {"sweep": SWEEP, "guard": GUARD, "session_end_sweep": SESSION_END_SWEEP}

# Which suite proves a mutation of a given target. Every "sweep"/"guard" mutant is proven against
# test_sweep.py, exactly as before; "session_end_sweep" mutants are proven against the hook's own
# suite instead.
SUITE_FOR_TARGET = {
    "sweep": "test_sweep.py",
    "guard": "test_sweep.py",
    "session_end_sweep": "test_session_end_sweep.py",
}

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
    # only_on="posix": test_refusal_unreadable_subject_is_kept drives its subject through a
    # blind-git PATH stand-in. MEASURED on Windows (decisions/list-form-subprocess-ignores-a-
    # path-shim-on-windows.md): a list-form subprocess call never reaches a PATH-shadowing
    # .cmd shim there, so the real git answers instead of blind git, `empty` never comes back
    # None, and the case is skipped on that platform -- it cannot prove this mutant either way.
    ("refusal: an unreadable branch subject reaps instead of keeping",
     "sweep",
     '    empty = guard.branch_is_empty(where, base, branch)\n'
     '    if empty is None:\n'
     '        return {"name": branch, "action": "keep", "reason": "unreadable-subject"}',
     '    empty = guard.branch_is_empty(where, base, branch)\n'
     '    if False:\n'
     '        return {"name": branch, "action": "keep", "reason": "unreadable-subject"}',
     "test_refusal_unreadable_subject_is_kept",
     "posix"),
    # decide_worktree reads "unreadable" three times over (dirty, locked, live), each one its
    # own `is None` guard: hooks/test_guard.py's own blind-git fixture makes EVERY git call fail
    # at once, so knocking out only the FIRST guard is masked by the second (still None, for the
    # same blind reason) -- MEASURED, not assumed: an earlier version of this mutant that dropped
    # only the `dirty is None` guard survived with 0 red lines, because `worktree_locked` read
    # against the same blind git also came back None and returned "unreadable-subject" anyway.
    # This mutant instead drops all three guards at once, the only way to make this protection
    # (an unreadable subject KEEPS, never reaps) actually absent under that fixture.
    # only_on="posix": same measured platform fact as the branch mutant above --
    # test_refusal_unreadable_subject_worktree's blind-git PATH stand-in is never reached by a
    # list-form subprocess call on Windows, so this suite's case is skipped there and cannot
    # prove this mutant.
    ("refusal: no unreadable worktree subject keeps any more (all three reads)",
     "sweep",
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
     '        return {"path": path, "action": "keep", "reason": "live-session"}',
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
     '        return {"path": path, "action": "keep", "reason": "live-session"}',
     "test_refusal_unreadable_subject_worktree",
     "posix"),

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
     '    if actual is PROCESS_START_UNREADABLE:\n'
     '        return None\n'
     '    if actual is None:\n'
     '        return False\n'
     '    diff = actual - started\n'
     '    if diff > SESSION_LIVE_TOLERANCE_MS:\n'
     '        return None\n'
     '    return diff >= -SESSION_LIVE_TOLERANCE_MS',
     '    if not isinstance(record, dict):\n'
     '        return False\n'
     '    pid = record.get("pid")\n'
     '    actual = _process_start_ms(pid)\n'
     '    return actual is not None',
     "test_mismatched_start_time_reads_as_unreadable_not_dead"),

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
     "test_preview_names_reapable_subjects_but_touches_neither"),

    # ---- the opt-out file: a present-but-malformed value must refuse, not default (fail-open
    # fix). A present `sweep` that is not a boolean, or a present `protectedPrefixes` that is not
    # a list of strings, must refuse the whole repository -- the same direction an unreadable
    # file already takes -- rather than fall through to the permissive default and sweep a
    # repository that stated a wish the sweep could not read.
    ("opt-out: a malformed present sweep/protectedPrefixes value falls back to the permissive default",
     "sweep",
     '    if "sweep" in data and not isinstance(data["sweep"], bool):\n'
     '        return False, (), False\n'
     '    sweep_enabled = data.get("sweep", True)\n'
     '    if "protectedPrefixes" in data:\n'
     '        extra = data["protectedPrefixes"]\n'
     '        if not isinstance(extra, list) or not all(isinstance(item, str) for item in extra):\n'
     '            return False, (), False\n'
     '    else:\n'
     '        extra = []',
     '    sweep_enabled = data.get("sweep", True)\n'
     '    if not isinstance(sweep_enabled, bool):\n'
     '        sweep_enabled = True\n'
     '    extra = data.get("protectedPrefixes", [])\n'
     '    if not isinstance(extra, list):\n'
     '        extra = []',
     "test_sweep_string_false_refuses_the_whole_repository"),

    # ---- the primary-checkout exclusion (review fix, PR #83) ----
    #
    # A reviewer ran sweep.py against a LINKED WORKTREE's own path (a shape session_end_sweep.py
    # exists to prevent, but sweep.py itself must not depend on every caller getting that right)
    # and watched the clone's real primary checkout get labeled `REAP removable`. `git worktree
    # remove` on it then failed only because git itself refuses to remove a main working tree
    # that way -- a refusal this program must not lean on (CLAUDE.md, "a recovery control must
    # not depend on the state it recovers"). This mutant drops the exclusion `_is_primary_checkout`
    # decides on, the same shape the reviewer measured by hand: the primary checkout falls
    # through to `decide_worktree` again and gets a real decision recorded against it.
    ("primary-checkout: the clone's own main working tree is no longer excluded from decide_worktree",
     "sweep",
     '        is_primary = _is_primary_checkout(entry["path"])\n'
     '        if is_primary is True:\n'
     '            continue  # the clone\'s one primary checkout: no decision is ever recorded against it',
     '        is_primary = _is_primary_checkout(entry["path"])\n'
     '        if False:\n'
     '            continue  # MUTANT: the exclusion never fires',
     "test_no_decision_is_recorded_against_the_primary_checkout_when_swept_via_a_linked_worktree"),

    # ---- the SessionEnd hook's own two budget protections (this build) ----
    #
    # 1. Spend what remains, not what was guessed: `remaining_sweep_timeout_seconds` must shrink
    # (or refuse to run the sweep at all) as the hook's own elapsed time eats into its budget,
    # rather than always handing the sweep the fixed SWEEP_TIMEOUT_SECONDS guess. Verified by
    # hand against a `.bak` copy before this mutant was written: ignoring `elapsed_seconds`
    # entirely fails exactly test_too_little_budget_left_returns_none among the FAIL lines (and,
    # not required here, two siblings in the same protection).
    ("budget: the sweep timeout ignores how much of the hook's budget is already spent",
     "session_end_sweep",
     '    remaining = SESSION_END_CEILING_SECONDS - elapsed_seconds - EXIT_MARGIN_SECONDS\n'
     '    sweep_timeout = min(SWEEP_TIMEOUT_SECONDS, remaining)\n'
     '    if sweep_timeout < MIN_USEFUL_SWEEP_SECONDS:\n'
     '        return None\n'
     '    return sweep_timeout',
     '    return SWEEP_TIMEOUT_SECONDS  # MUTANT: elapsed_seconds is never consulted',
     "test_too_little_budget_left_returns_none"),

    # 2. The upper-edge headroom guard: a margin between settings.json's ceiling and the hook's
    # own worst case must not be allowed to run arbitrarily far ahead. Verified by hand against a
    # `.bak` copy: widening SESSION_END_TIMEOUT_MAX_HEADROOM_SECONDS to 2000 fails exactly
    # test_ceiling_far_ahead_of_the_worst_case_fails_the_band among the FAIL lines, and no other
    # case.
    ("budget: the upper-edge headroom guard accepts an unbounded margin",
     "session_end_sweep",
     'SESSION_END_TIMEOUT_MAX_HEADROOM_SECONDS = 20.0',
     'SESSION_END_TIMEOUT_MAX_HEADROOM_SECONDS = 2000.0',
     "test_ceiling_far_ahead_of_the_worst_case_fails_the_band"),

    # 3. PR #84 review: an elapsed reading this function cannot trust (negative, or non-finite)
    # must not be spent as if it were free time. Verified by hand against a `.bak` copy: dropping
    # the validation block fails exactly test_negative_elapsed_is_refused_not_treated_as_extra_
    # time and test_non_finite_elapsed_is_refused among the FAIL lines, and no other case (the
    # larger-than-the-ceiling case stays green on its own, unrelated arithmetic).
    ("budget: an untrustworthy elapsed reading (negative or non-finite) is spent as real time",
     "session_end_sweep",
     '    if (\n'
     '        not isinstance(elapsed_seconds, (int, float))\n'
     '        or isinstance(elapsed_seconds, bool)\n'
     '        or not math.isfinite(elapsed_seconds)\n'
     '        or elapsed_seconds < 0\n'
     '    ):\n'
     '        return None\n'
     '    remaining = SESSION_END_CEILING_SECONDS - elapsed_seconds - EXIT_MARGIN_SECONDS',
     '    remaining = SESSION_END_CEILING_SECONDS - elapsed_seconds - EXIT_MARGIN_SECONDS  '
     '# MUTANT: no validation',
     "test_negative_elapsed_is_refused_not_treated_as_extra_time"),

    # 4. Command-line argv coverage (found 2026-09-22): the hook's own reap call,
    # `[sys.executable, SWEEP_PATH, root, "--confirm"]`, is the one subprocess.run in this whole
    # program that actually deletes a branch for real, and no mutant here ever changed its argv
    # before this one. Dropping `--confirm` turns the reap silently into a preview: sweep.py's own
    # `if confirm and decision["action"] == "reap":` (janitor/sweep.py) then never fires, so
    # `reap-me-a` survives. `test_sweeps_repo_a_leaves_repo_b_untouched` runs the REAL sweep.py
    # against a REAL git repository, unmocked, and asserts the branch is gone -- proven against a
    # `.bak` copy before this mutant was written.
    ("confirm: the sweep call drops --confirm, so a reap silently becomes a preview",
     "session_end_sweep",
     '            [sys.executable, SWEEP_PATH, root, "--confirm"],',
     '            [sys.executable, SWEEP_PATH, root],',
     "test_sweeps_repo_a_leaves_repo_b_untouched"),

    # ---- orphaned TCP listeners (this build, 2026-09-24) ----
    #
    # `decide_listener`'s own three refusals, same shape as the branch/worktree refusals
    # above: each one is a keep this sweep must never lose, proven by mutating it out and
    # watching a REAL fixture listener (janitor/test_sweep.py's ListenerDecisionTests, a real
    # process this suite starts itself) reap where it must not.
    ("listener: a non-orphaned process is no longer refused, and reaps anyway",
     "sweep",
     '    if not orphan:\n'
     '        return {**base, "action": "keep", "reason": "not-orphaned"}',
     '    if False:\n'
     '        return {**base, "action": "keep", "reason": "not-orphaned"}',
     "test_non_orphaned_listener_is_kept"),
    ("listener: a live Claude session in the same checkout no longer keeps its listener",
     "sweep",
     '    if live:\n'
     '        return {**base, "action": "keep", "reason": "live-session"}',
     '    if False:\n'
     '        return {**base, "action": "keep", "reason": "live-session"}',
     "test_orphaned_listener_with_live_session_is_kept"),
    ("listener: a listener owned by someone else is no longer refused, and reaps anyway",
     "sweep",
     '    if not owner:\n'
     '        return {**base, "action": "keep", "reason": "not-current-user"}',
     '    if False:\n'
     '        return {**base, "action": "keep", "reason": "not-current-user"}',
     "test_owner_mismatch_is_kept"),

    # ---- the worktree pre-removal process check (this build, 2026-09-24) ----
    ("pre-check: a process sitting inside the worktree no longer keeps it",
     "sweep",
     '    if inside:\n'
     '        return {"path": path, "action": "keep",\n'
     '                "reason": "process-inside: pid %s" % ", ".join(str(p) for p in sorted(inside))}',
     '    if False:\n'
     '        return {"path": path, "action": "keep",\n'
     '                "reason": "process-inside: pid %s" % ", ".join(str(p) for p in sorted(inside))}',
     "test_a_process_inside_the_worktree_keeps_it_and_names_the_pid"),
]


def mutation_parts(entry):
    """Return (label, target, old, new, required, only_on) for one mutation, enforcing the
    fifth field the same way hooks/mutate_guard.py's mutation_parts does: a mutation with no
    required case name is as unproven as one that dies wrong, so it is refused outright.

    `only_on` is a SIXTH, optional field: "posix" or "windows", for a mutation whose one
    proving case cannot be driven on the other platform. Absent on every other entry, which
    runs everywhere as before. Same shape as hooks/mutate_guard.py's own `only_on`."""
    if len(entry) not in (5, 6):
        raise ValueError("mutation carries the wrong number of fields: %r" % (entry,))
    label, target, old, new, required = entry[:5]
    only_on = entry[5] if len(entry) > 5 else None
    if target not in SOURCES:
        raise ValueError("mutation names an unknown target %r: %s" % (target, label))
    if not required:
        raise ValueError("mutation carries no required case name: %s" % label)
    return label, target, old, new, required, only_on


def build_scaffold(scaffold: str, sources: dict, mutated_target: str, mutated_text: str):
    """Lay out <scaffold>/hooks/guard.py, <scaffold>/janitor/{sweep.py,test_sweep.py,
    session_end_sweep.py,test_session_end_sweep.py} and <scaffold>/settings.json so that running
    either suite from <scaffold>/janitor resolves `import guard`, `import sweep` and
    `import session_end_sweep` to the copies placed here (see the module docstring, "WHY A
    SCAFFOLD DIRECTORY"). Exactly one of guard.py / sweep.py / session_end_sweep.py carries
    `mutated_text`; the rest are the real sources, unchanged. Both suites, and settings.json, are
    always the real sources: this harness never edits a suite or the real settings.json."""
    hooks_dir = os.path.join(scaffold, "hooks")
    janitor_dir = os.path.join(scaffold, "janitor")
    os.makedirs(hooks_dir, exist_ok=True)
    os.makedirs(janitor_dir, exist_ok=True)

    guard_text = mutated_text if mutated_target == "guard" else sources["guard"]
    sweep_text = mutated_text if mutated_target == "sweep" else sources["sweep"]
    session_end_text = (
        mutated_text if mutated_target == "session_end_sweep" else sources["session_end_sweep"]
    )

    with open(os.path.join(hooks_dir, "guard.py"), "w", encoding="utf-8", newline="\n") as h:
        h.write(guard_text)
    with open(os.path.join(janitor_dir, "sweep.py"), "w", encoding="utf-8", newline="\n") as h:
        h.write(sweep_text)
    with open(os.path.join(janitor_dir, "test_sweep.py"), "w", encoding="utf-8", newline="\n") as h:
        h.write(sources["test_sweep"])
    with open(
        os.path.join(janitor_dir, "session_end_sweep.py"), "w", encoding="utf-8", newline="\n"
    ) as h:
        h.write(session_end_text)
    with open(
        os.path.join(janitor_dir, "test_session_end_sweep.py"),
        "w", encoding="utf-8", newline="\n",
    ) as h:
        h.write(sources["test_session_end_sweep"])
    with open(os.path.join(scaffold, "settings.json"), "w", encoding="utf-8", newline="\n") as h:
        h.write(sources["settings_json"])


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
    (label, code, FAIL lines, required, skip).

    `skip`, when not None, is why this mutant did not run on this platform at all: its one
    proving case cannot be driven here (see `skip_reason`). The caller reports it and counts it
    as neither killed, survived, nor wrong cause."""
    label, target, old, new, required, only_on = mutation_parts(entry)
    skip = mutate_shared.skip_reason(only_on)
    if skip:
        return label, None, [], required, skip
    mutated_text = sources[target].replace(old, new, 1)
    scaffold = os.path.join(work, "m_%03d_%s" % (index, mutate_shared.safe_name(label)))
    config_dir = os.path.join(scaffold, "cfg")
    os.makedirs(config_dir, exist_ok=True)
    try:
        build_scaffold(scaffold, sources, target, mutated_text)
        suite_path = os.path.join(scaffold, "janitor", SUITE_FOR_TARGET[target])
        code, red = run_suite(suite_path, config_dir)
        return label, code, red, required, None
    finally:
        shutil.rmtree(scaffold, ignore_errors=True)


def main() -> int:
    sources = {}
    for name, path in SOURCES.items():
        with open(path, encoding="utf-8") as handle:
            sources[name] = handle.read()
    with open(SUITE, encoding="utf-8") as handle:
        sources["test_sweep"] = handle.read()
    with open(SESSION_END_SUITE, encoding="utf-8") as handle:
        sources["test_session_end_sweep"] = handle.read()
    with open(SETTINGS_JSON, encoding="utf-8") as handle:
        sources["settings_json"] = handle.read()

    # Every anchor is checked before any suite runs, so a stale mutation fails in the first
    # second, not after the mutants ahead of it in the list have spent their minutes.
    for entry in MUTATIONS:
        label, target, old, _new, required, _only_on = mutation_parts(entry)
        if old not in sources[target]:
            print("ERROR stale mutation, anchor text not found in %s: %s" % (target, label))
            return 1
        if not required:
            print("ERROR mutation carries no required case name: %s" % label)
            return 1

    work = tempfile.mkdtemp(prefix="mutate_sweep_")
    try:
        return mutate_shared.run_mutants(
            list(enumerate(MUTATIONS)),
            lambda item: run_mutant(sources, work, item[0], item[1]))
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
