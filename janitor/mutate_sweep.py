#!/usr/bin/env python3
"""Mutation test for janitor/sweep.py and hooks/guard.py's sweep-facing primitives.

Stdlib only. Same shape and vocabulary as hooks/mutate_guard.py (KILLED / SURVIVED / WRONG
CAUSE) and the same fifth field: the case name a mutant's own FAIL lines must carry, so a kill
on an unrelated case never counts as proof. `python3 janitor/mutate_sweep.py` either kills
every mutant below or names the ones it does not.

WHY TWO TARGETS, NOT ONE. janitor/sweep.py holds no code of its own for the ancestor test, the
`git cherry` patch test, the remote-contains test, or the pid-vs-start-time liveness read: it
calls hooks/guard.py's own tested primitives for each. A mutation test that only edited sweep.py
could touch none of those four protections. So a mutant carries a TARGET ("sweep" or "guard")
and this file mutates a copy of whichever file holds the line.

A THIRD TARGET, "session_end_sweep", covers the SessionEnd hook itself (janitor/session_end_
sweep.py), proven against its own suite (janitor/test_session_end_sweep.py) instead of
test_sweep.py -- see SUITE_FOR_TARGET below. Its scaffold also carries a copy of the real
REPO_ROOT/settings.json, never mutated, because that suite's HookBudgetFitsUnderItsHostCeiling
arm reads it.

WHY A SCAFFOLD DIRECTORY, NOT AN ENV VAR. hooks/test_guard.py and hooks/test_config_watch.py
each read a `*_UNDER_TEST` environment variable naming the copy to import (see
hooks/mutate_guard.py's own TARGETS table). janitor/test_sweep.py has no such variable. So this
mutation test rebuilds the two-directory shape (`hooks/`, `janitor/`) that `janitor/test_sweep.py`
computes its own import path from (`HERE = dirname(test_sweep.py)`, `REPO_ROOT = dirname(HERE)`,
`sys.path.insert(0, REPO_ROOT/hooks)`) inside a fresh temporary directory per mutant, and
copies the REAL `janitor/test_sweep.py` into it byte for byte. Running that copy from that
scaffold makes `import sweep` and `import guard` resolve to whichever copies -- mutated or
real -- this mutation test placed next to it. The real `janitor/test_sweep.py` on disk is never
touched, and nothing is left behind: see `run_mutant` and `main`'s `finally`.

A MUTATION WHOSE ANCHOR TEXT IS NOT FOUND is STALE and fails loudly, the same rule
hooks/mutate_guard.py enforces, checked for every mutation before any suite runs.

A RED SUITE IS NOT ENOUGH. `janitor/test_sweep.py` runs as plain `unittest.main(verbosity=2)`,
which prints its per-case progress and its failure headings to STDERR, not STDOUT. Both streams
are scanned for lines containing "FAIL", and a mutant's death only counts when the required
case name shows up in one of them: a mutant that crashes the suite, or that some UNRELATED case
happens to catch, is WRONG CAUSE, not KILLED.

A mutant no case kills is a survivor, and the run exits 1.

Run:
    python3 janitor/mutate_sweep.py
Only some mutants (label fragments, comma-separated; every anchor is still checked):
    MUTATE_ONLY="deadline,oldest first" python3 janitor/mutate_sweep.py
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO_ROOT, "hooks"))
import mutate_shared  # noqa: E402
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)

SWEEP = os.path.join(HERE, "sweep.py")
SUITE = os.path.join(HERE, "test_sweep.py")
GUARD = os.path.join(REPO_ROOT, "hooks", "guard.py")

# A third target, added for the SessionEnd hook's own budget protection (remaining-time
# spend): the hook has its own suite, test_session_end_sweep,
# which additionally reads the real REPO_ROOT/settings.json (HookBudgetFitsUnderItsHostCeiling)
# -- so its scaffold needs that file too, never mutated, copied alongside the rest.
SESSION_END_SWEEP = os.path.join(HERE, "session_end_sweep.py")
SESSION_END_SUITE = os.path.join(HERE, "test_session_end_sweep.py")
SETTINGS_JSON = os.path.join(REPO_ROOT, "settings.json")

# A fourth target: the agent-end reaper. Its cases live in test_sweep.py (AgentEndReapTests), and
# that suite imports it, so every scaffold carries a copy, mutated or not.
AGENT_END_REAP = os.path.join(HERE, "agent_end_reap.py")

SOURCES = {"sweep": SWEEP, "guard": GUARD, "session_end_sweep": SESSION_END_SWEEP,
           "agent_end_reap": AGENT_END_REAP}
# Each guard sibling module, hooks/guard_<name>.py, is a target keyed `guard_<name>`. Every
# scaffold carries the whole guard family, so `import guard` finds its siblings there.
SOURCES.update({
    os.path.splitext(os.path.basename(path))[0]: path
    for path in mutate_shared.guard_files(os.path.dirname(GUARD)) if path != GUARD
})
# hooks/git_reads.py holds the reads sweep.py and session_end_sweep.py call, so it is a target too.
GIT_READS = os.path.join(REPO_ROOT, "hooks", "git_reads.py")
SOURCES["git_reads"] = GIT_READS


def is_guard_key(name: str) -> bool:
    """True for "guard", each "guard_<name>" sibling key, and "git_reads"."""
    return name == "guard" or name.startswith("guard_") or name == "git_reads"


# Which suite proves a mutation of a given target. Every "sweep"/"guard" mutant is proven against
# test_sweep.py, exactly as before; "session_end_sweep" mutants are proven against the hook's own
# suite instead.
SUITE_FOR_TARGET = {
    **{name: "test_sweep.py" for name in SOURCES if is_guard_key(name)},
    "sweep": "test_sweep.py",
    "guard": "test_sweep.py",
    "session_end_sweep": "test_session_end_sweep.py",
    "agent_end_reap": "test_sweep.py",
}

# (label, target, anchor text found once in the source, its mutated replacement, the case name
# (or a distinctive fragment of it) that MUST appear among the suite's own FAIL lines). One
# mutant per PROTECTION, not per line: the seven refusals, the keep rule in both directions, the
# only-copy remote-contains test, the pid-vs-start-time liveness read, the tombstone's write
# order, the purge's age source, and the --confirm check. `target` says which file's copy carries
# the anchor: "sweep" for janitor/sweep.py's own code, "guard" or "guard_<name>" for the guard
# module that holds the primitive sweep.py calls and never re-implements (see the module docstring
# above).
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
    ("same-run cut: a removed worktree no longer releases its branch",
     "sweep",
     '                            if e.get("branch") and e["path"] not in removed}\n',
     '                            if e.get("branch")}\n',
     "test_confirm_removes_the_worktree_and_its_branch_in_one_run"),
    ("same-run cut: a removed worktree frees its branch name for a kept second holder",
     "sweep",
     '                            if e.get("branch") and e["path"] not in removed}\n',
     '                            if e.get("branch") and e["branch"] not in '
     '{x["branch"] for x in entries if x["path"] in removed}}\n',
     "test_a_second_kept_worktree_on_the_same_branch_keeps_it_held"),
    ("same-run cut: a failed removal still releases its branch",
     "sweep",
     '        gone = gone and not decision.get("error")\n',
     '        gone = gone\n',
     "test_a_failed_removal_keeps_the_branch_held"),
    ("same-run cut: a kept worktree releases its branch",
     "sweep",
     '        gone = decision["action"] == "reap"\n',
     '        gone = True\n',
     "test_a_kept_worktree_keeps_its_branch_held"),
    ("modes: --root accepts a primary whose common dir is not the original",
     "sweep",
     '                _is_toplevel(primary) and os.path.normcase(',
     '                _is_toplevel(primary) or os.path.normcase(',
     "test_root_whose_git_dir_sits_in_another_repos_root_exits_1"),
    ("modes: --root accepts a clone whose git dir is not under its own folder",
     "sweep",
     '        if primary is not None and not (\n',
     '        if False and not (\n',
     "test_root_in_a_separate_git_dir_clone_exits_1"),
    ("modes: --tier1 waits for --confirm again",
     "sweep",
     '    if mode == "tier1":\n        confirm = True\n',
     '    if mode == "tier1":\n        confirm = confirm\n',
     "test_tier1_prunes_stale_registrations_with_no_confirm_and_touches_nothing_else"),
    ("modes: --tier1 reaps branches too",
     "sweep",
     '    branches = [] if mode in ("tier1", "fast") else list_local_branches(root)\n',
     '    branches = list_local_branches(root)\n',
     "test_tier1_prunes_stale_registrations_with_no_confirm_and_touches_nothing_else"),
    ("modes: --branches removes worktrees",
     "sweep",
     '    judged = _oldest_idle_first(entries) if mode in ("full", "fast") else []\n',
     '    judged = _oldest_idle_first(entries)\n',
     "test_branches_reaps_a_merged_branch_but_removes_no_worktree_and_holds_theirs"),
    ("modes: --branches prunes registrations",
     "sweep",
     '    if mode not in ("branches", "fast"):\n        result["pruned"] =',
     '    if True:\n        result["pruned"] =',
     "test_branches_reaps_a_merged_branch_but_removes_no_worktree_and_holds_theirs"),
    ("modes: --branches reaps on an empty worktree list",
     "sweep",
     '    if mode == "branches" and not entries:\n',
     '    if False:\n',
     "test_branches_refuses_when_the_worktree_list_is_empty"),
    ("modes: --root keeps a worktree path instead of its primary checkout",
     "sweep",
     '        roots.append(primary)\n',
     '        roots.append(os.path.abspath(args.root))\n',
     "test_root_resolves_a_linked_worktree_to_its_primary_checkout"),
    ("modes: --root outside a repository exits 0",
     "sweep",
     '            print("janitor: %s is not inside a repository" % args.root, file=sys.stderr)\n            return 1\n',
     '            print("janitor: %s is not inside a repository" % args.root, file=sys.stderr)\n            return 0\n',
     "test_root_outside_any_repository_exits_1"),
    ("modes: a single-tier mode still runs the process tiers",
     "sweep",
     '    if mode != "full":\n        return 0\n',
     '    if False:\n        return 0\n',
     "test_single_tier_modes_do_no_process_work"),
    ("refusal: a dirty worktree no longer keeps",
     "sweep",
     '    if dirty:\n'
     '        return {"path": path, "action": "keep", "reason": "dirty"}',
     '    if False:\n'
     '        return {"path": path, "action": "keep", "reason": "dirty"}',
     "test_refusal_dirty_worktree"),
    ("refusal: a live session no longer keeps its worktree",
     "sweep",
     '        return {"path": path, "action": "keep", "reason": "unreadable-subject"}\n'
     '    if live:\n'
     '        return {"path": path, "action": "keep", "reason": "live-session"}',
     '        return {"path": path, "action": "keep", "reason": "unreadable-subject"}\n'
     '    if False:\n'
     '        return {"path": path, "action": "keep", "reason": "live-session"}',
     "test_refusal_live_session_worktree"),
    ("refusal: a locked worktree no longer keeps",
     "sweep",
     '    if entry.get("locked_reason") is not None:\n'
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
    # blind-git PATH stand-in. On Windows a list-form subprocess call never reaches a PATH shim
    # (decisions/list-form-subprocess-ignores-a-path-shim-on-windows.md), so `empty` never comes
    # back None and the case is skipped there: it cannot prove this mutant.
    ("refusal: an unreadable branch subject reaps instead of keeping",
     "sweep",
     '    if label is None:\n'
     '        return {"name": branch, "action": "keep", "reason": "unreadable-subject"}',
     '    if False:\n'
     '        return {"name": branch, "action": "keep", "reason": "unreadable-subject"}',
     "test_refusal_unreadable_subject_is_kept",
     "posix"),
    # decide_worktree reads "unreadable" three times over (dirty, live, pushed), each one its own
    # `is None` guard. hooks/test_guard.py's blind-git fixture makes EVERY git read None at once,
    # so dropping one guard alone is masked by the next. This mutant drops all three together, the
    # only way to make this protection (an unreadable subject KEEPS, never reaps) absent under that
    # fixture. The lock is not a git read any more (parse_worktree_list reads it once per pass), so
    # it is not one of the three.
    # only_on="posix": test_refusal_unreadable_subject_worktree's blind-git PATH stand-in is never
    # reached by a list-form subprocess call on Windows, so this suite's case is skipped there and
    # cannot prove this mutant.
    ("refusal: no unreadable worktree subject keeps any more (all three reads)",
     "sweep",
     '    if dirty is None:\n'
     '        return {"path": path, "action": "keep", "reason": "unreadable-subject"}\n'
     '    if dirty:\n'
     '        return {"path": path, "action": "keep", "reason": "dirty"}\n'
     '    # The lock comes from the entry `parse_worktree_list` read once for the pass, not a fresh\n'
     '    # `worktree list` per tree (measured: one of the reads that made a sweep outrun its 25 s).\n'
     '    # `remove_worktree` still has git refuse a locked tree.\n'
     '    stale_agent_lock = False\n'
     '    own_lock = False\n'
     '    if entry.get("locked_reason") is not None:\n'
     '        holder = entry.get("locked_reason") or "locked"\n'
     '        stale_agent_lock = stale_agent_lock_verdict(holder)\n'
     '        if stale_agent_lock is not True:\n'
     '            own_lock = (own_lock_rule and own_agent_lock_verdict(holder) is True\n'
     '                        and (not fast or batch is not None)\n'
     '                        and _own_lock_ready(where, path, batch, lock_idle))\n'
     '            if not own_lock:\n'
     '                return {"path": path, "action": "keep", "reason": "locked: %s" % holder}\n'
     '    live = git_reads.worktree_live_session(path)\n'
     '    if live is None:\n'
     '        return {"path": path, "action": "keep", "reason": "unreadable-subject"}\n'
     '    if live:\n'
     '        return {"path": path, "action": "keep", "reason": "live-session"}\n'
     '    pushed = True if fast else fully_pushed(path)\n'
     '    if pushed is None:\n'
     '        return {"path": path, "action": "keep", "reason": "unreadable-subject"}',
     '    if False:\n'
     '        return {"path": path, "action": "keep", "reason": "unreadable-subject"}\n'
     '    if dirty:\n'
     '        return {"path": path, "action": "keep", "reason": "dirty"}\n'
     '    # The lock comes from the entry `parse_worktree_list` read once for the pass, not a fresh\n'
     '    # `worktree list` per tree (measured: one of the reads that made a sweep outrun its 25 s).\n'
     '    # `remove_worktree` still has git refuse a locked tree.\n'
     '    stale_agent_lock = False\n'
     '    own_lock = False\n'
     '    if entry.get("locked_reason") is not None:\n'
     '        holder = entry.get("locked_reason") or "locked"\n'
     '        stale_agent_lock = stale_agent_lock_verdict(holder)\n'
     '        if stale_agent_lock is not True:\n'
     '            own_lock = (own_lock_rule and own_agent_lock_verdict(holder) is True\n'
     '                        and (not fast or batch is not None)\n'
     '                        and _own_lock_ready(where, path, batch, lock_idle))\n'
     '            if not own_lock:\n'
     '                return {"path": path, "action": "keep", "reason": "locked: %s" % holder}\n'
     '    live = git_reads.worktree_live_session(path)\n'
     '    if False:\n'
     '        return {"path": path, "action": "keep", "reason": "unreadable-subject"}\n'
     '    if live:\n'
     '        return {"path": path, "action": "keep", "reason": "live-session"}\n'
     '    pushed = True if fast else fully_pushed(path)\n'
     '    if False:\n'
     '        return {"path": path, "action": "keep", "reason": "unreadable-subject"}',
     "test_refusal_unreadable_subject_worktree",
     "posix"),

    # ---- the keep rule, both directions (plan, "Phase 2") ----
    ("keep rule: the ancestry test never proves a branch empty",
     "git_reads",
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
     "git_reads",
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
     "git_reads",
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
     "git_reads",
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
     '    tip = git_reads._git(root, "rev-parse", "refs/heads/" + branch)\n'
     '    if tip is None or tip.returncode != 0:\n'
     '        decision["error"] = "could not resolve the branch tip; branch left alone"\n'
     '        return\n'
     '    commit = tip.stdout.strip()\n'
     '    tomb = git_reads._git(root, "update-ref", TOMBSTONE_REF_PREFIX + branch, commit)\n'
     '    if tomb is None or tomb.returncode != 0:\n'
     '        decision["error"] = "tombstone write failed; branch NOT deleted"\n'
     '        return\n'
     '    append_restore_log(restore_log_path, root, branch, commit)\n'
     '    delete = git_reads._git(root, "branch", "-D", branch)\n'
     '    if delete is None or delete.returncode != 0:\n'
     '        decision["error"] = "delete failed after the tombstone landed: %s" % (\n'
     '            delete.stderr.strip() if delete is not None else "git gave no answer"\n'
     '        )',
     'def reap_branch(root: str, branch: str, decision: dict, restore_log_path: str):\n'
     '    """MUTATED: delete first, tombstone after -- the ordering this mutant breaks."""\n'
     '    tip = git_reads._git(root, "rev-parse", "refs/heads/" + branch)\n'
     '    if tip is None or tip.returncode != 0:\n'
     '        decision["error"] = "could not resolve the branch tip; branch left alone"\n'
     '        return\n'
     '    commit = tip.stdout.strip()\n'
     '    delete = git_reads._git(root, "branch", "-D", branch)\n'
     '    if delete is None or delete.returncode != 0:\n'
     '        decision["error"] = "delete failed after the tombstone landed: %s" % (\n'
     '            delete.stderr.strip() if delete is not None else "git gave no answer"\n'
     '        )\n'
     '        return\n'
     '    tomb = git_reads._git(root, "update-ref", TOMBSTONE_REF_PREFIX + branch, commit)\n'
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
    ("tombstone: a failed tombstone write no longer stops the branch delete",
     "sweep",
     '    if tomb is None or tomb.returncode != 0:\n'
     '        decision["error"] = "tombstone write failed',
     '    if False:\n'
     '        decision["error"] = "tombstone write failed',
     "test_a_failed_tombstone_write_stops_the_delete"),
    ("tombstone: an unresolved branch tip no longer leaves the branch alone",
     "sweep",
     '    if tip is None or tip.returncode != 0:\n'
     '        decision["error"] = "could not resolve the branch tip',
     '    if False:\n'
     '        decision["error"] = "could not resolve the branch tip',
     "test_an_unresolved_branch_tip_leaves_the_branch_alone"),
    ("purge: a non-numeric time_ms is no longer an unreadable entry",
     "sweep",
     '                or not isinstance(when, (int, float)) or isinstance(when, bool):',
     '                or False:',
     "test_a_non_numeric_time_ms_is_kept_not_purged"),
    ("purge: the ref is dropped by branch name, with no check that it holds the entry's commit",
     "sweep",
     '            if held.returncode == 1 or held.stdout.strip() != commit:\n'
     '                if held.returncode == 0:\n'
     '                    decision["reason"] += "; ref kept: it holds a younger restore point"\n'
     '                continue\n'
     '            dropped = git_reads._git(repo, "update-ref", "-d", ref, commit)',
     '            dropped = git_reads._git(repo, "update-ref", "-d", ref)',
     "test_an_expired_entry_keeps_the_ref_that_holds_the_younger_commit"),
    ("purge: an unexpired entry for the same commit no longer keeps the ref",
     "sweep",
     '            if row_key(entry) in unexpired:\n',
     '            if False:\n',
     "test_an_expired_entry_keeps_the_ref_while_an_unexpired_entry_names_its_commit"),
    ("purge: the repo key is the raw string, not the normalised real path",
     "sweep",
     '        return (os.path.normcase(os.path.realpath(repo)), branch.lower()',
     '        return (repo, branch.lower()',
     "test_an_unexpired_row_protects_the_ref_across_spellings_of_its_repo"),
    ("purge: the branch in the key keeps its case, so a case-folded ref is dropped",
     "sweep",
     'branch.lower() if isinstance(branch, str) else branch, e.get("commit"))\n',
     'branch, e.get("commit"))\n',
     "test_an_expired_entry_keeps_the_ref_when_an_unexpired_entry_differs_only_by_case"),
    ("purge: a git failure reading the ref is read as a gone ref",
     "sweep",
     '            if held is None or held.returncode not in (0, 1) or (\n',
     '            if held is None or (\n',
     "test_a_failed_ref_read_is_reported_and_keeps_the_ref"),
    ("purge: exit 1 with a stderr message (a broken ref) is read as a gone ref",
     "sweep",
     '                    held.returncode == 1 and held.stderr.strip()):\n',
     '                    False):\n',
     "test_a_broken_ref_file_is_an_error_not_a_gone_ref"),

    # ---- --confirm ----
    ("--confirm: reap branches for real with no --confirm on the line",
     "sweep",
     '        result["branches"].append(decision)\n'
     '        if confirm and decision["action"] == "reap":\n'
     '            reap_branch(root, branch, decision, restore_log_path)',
     '        result["branches"].append(decision)\n'
     '        if decision["action"] == "reap":\n'
     '            reap_branch(root, branch, decision, restore_log_path)',
     "test_preview_names_reapable_subjects_but_touches_neither"),

    # ---- the opt-out file: a present-but-malformed value must refuse, not default. A present
    # `sweep` that is not a boolean, or a present `protectedPrefixes` that is not a list of
    # strings, must refuse the whole repository -- the same direction an unreadable file already
    # takes -- rather than fall through to the permissive default and sweep a repository that
    # stated a wish the sweep could not read.
    ("opt-out: a malformed present sweep/protectedPrefixes value falls back to the permissive default",
     "sweep",
     '    if "sweep" in data and not isinstance(data["sweep"], bool):\n'
     '        return None\n'
     '    for key in ("protectedPrefixes", "huskNames", "buildDirs"):\n'
     '        if key in data and (not isinstance(data[key], list)\n'
     '                            or not all(isinstance(item, str) for item in data[key])):\n'
     '            return None\n'
     '    return data\n',
     '    return data\n',
     "test_sweep_string_false_refuses_the_whole_repository"),

    # ---- the primary-checkout exclusion ----
    #
    # sweep.py run against a LINKED WORKTREE's own path (a shape session_end_sweep.py exists to
    # prevent, but sweep.py must not depend on every caller getting that right) must still
    # exclude the clone's real primary checkout. Otherwise it is labeled `REAP removable`, and
    # `git worktree remove` fails only because git itself refuses to remove a main working
    # tree -- a refusal this program must not lean on. This mutant drops the exclusion
    # `_is_primary_checkout` decides on: the primary checkout falls through to
    # `decide_worktree` and gets a real decision recorded against it.
    ("primary-checkout: the clone's own main working tree is no longer excluded from decide_worktree",
     "sweep",
     '        is_primary = _is_primary_checkout(entry["path"])\n'
     '        if is_primary is True:\n'
     '            return None  # the clone\'s one primary checkout: no decision is ever recorded',
     '        is_primary = _is_primary_checkout(entry["path"])\n'
     '        if False:\n'
     '            return None  # MUTANT: the exclusion never fires',
     "test_no_decision_is_recorded_against_the_primary_checkout_when_swept_via_a_linked_worktree"),

    # ---- the SessionEnd hook's budget protections ----
    #
    # Spend what remains, not what was guessed: `remaining_sweep_timeout_seconds` must shrink
    # (or refuse to run the sweep at all) as the hook's own elapsed time eats into its budget,
    # rather than always handing the sweep the fixed SWEEP_TIMEOUT_SECONDS guess. Ignoring
    # `elapsed_seconds` entirely fails test_too_little_budget_left_returns_none, among others.
    ("budget: the sweep timeout ignores how much of the hook's budget is already spent",
     "session_end_sweep",
     '    remaining = SESSION_END_CEILING_SECONDS - elapsed_seconds - EXIT_MARGIN_SECONDS\n'
     '    sweep_timeout = min(SWEEP_TIMEOUT_SECONDS, remaining)\n'
     '    if sweep_timeout < MIN_USEFUL_SWEEP_SECONDS:\n'
     '        return None\n'
     '    return sweep_timeout',
     '    return SWEEP_TIMEOUT_SECONDS  # MUTANT: elapsed_seconds is never consulted',
     "test_too_little_budget_left_returns_none"),


    # An elapsed reading this function cannot trust (negative, or non-finite) must not be spent
    # as if it were free time. Dropping the validation block fails the negative row and the nan
    # row of test_too_little_budget_left_returns_none (one subTest per row). The inf row and the
    # over-ceiling row still return None without the block, so they stay green.
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
     "test_too_little_budget_left_returns_none"),

    # The hook's own reap call, `[sys.executable, SWEEP_PATH, root, "--confirm",
    # "--deadline-seconds", N]`, is the one subprocess.run in this program that deletes a branch
    # for real. Dropping `--confirm` turns the reap silently into a preview: sweep.py's own
    # `if confirm and decision["action"] == "reap":` then never fires, so `reap-me-a` survives.
    # `test_sweeps_repo_a_leaves_repo_b_untouched` runs the REAL sweep.py against a REAL git
    # repository, unmocked, and asserts the branch is gone.
    ("confirm: the sweep call drops --confirm, so a reap silently becomes a preview",
     "session_end_sweep",
     '            [sys.executable, SWEEP_PATH, root, "--confirm",',
     '            [sys.executable, SWEEP_PATH, root,',
     "test_sweeps_repo_a_leaves_repo_b_untouched"),
    ("strict: the SessionEnd sweep call passes --attended",
     "session_end_sweep",
     '            [sys.executable, SWEEP_PATH, root, "--confirm",',
     '            [sys.executable, SWEEP_PATH, root, "--confirm", "--attended",',
     "test_the_sweep_is_not_passed_the_attended_flag"),
    ("session-end argv: the deadline flag is dropped, so the sweep runs with no deadline",
     "session_end_sweep",
     '             "--deadline-seconds", str(sweep_timeout)],',
     '             ],',
     "test_the_sweep_is_passed_the_time_left_as_a_deadline_flag"),
    ("session-end argv: the time left is replaced by the constant 25",
     "session_end_sweep",
     '             "--deadline-seconds", str(sweep_timeout)],',
     '             "--deadline-seconds", "25"],',
     "test_the_sweep_is_passed_the_time_left_as_a_deadline_flag"),

    # only_on="posix": LooseProcessTests is skipped on Windows (its sh-loop fixture is POSIX only).
    ("loose processes: an unreadable owner is left out instead of listed",
     "sweep",
     '        if owner is False:\n            continue\n',
     '        if owner is not True:\n            continue\n',
     "test_unreadable_owner_is_listed_as_unknown",
     "posix"),
    ("loose processes: a live session's wrapper is listed",
     "sweep",
     '        if orphan is False:\n            continue\n',
     '        if False:\n            continue\n',
     "test_a_live_sessions_wrapper_is_not_listed",
     "posix"),
    ("loose processes: an unreadable orphan read is left out",
     "sweep",
     '        found.append({"pid": pid, "command": command,',
     '        if orphan is None:\n            continue\n'
     '        found.append({"pid": pid, "command": command,',
     "test_an_unreadable_orphan_read_is_listed_as_unknown",
     "posix"),

    # ---- orphaned TCP listeners ----
    #
    # ---- the agent-end reaper and the deepest-checkout match it depends on ----
    ("deepest checkout: the first containing checkout wins again, the primary over its worktree",
     "sweep",
     '    return max(matches, key=lambda path: len(os.path.normcase(os.path.realpath(path))))',
     '    return matches[0]',
     "test_the_deepest_checkout_wins_over_the_primary_that_contains_it"),
    ("agent worktrees: the sweep judges a listener in `.claude/worktrees/*` again",
     "sweep",
     '        if cwd is None or _under_agent_worktree(cwd):\n            continue',
     '        if cwd is None:\n            continue',
     "test_the_sweep_leaves_an_orphan_in_an_agent_worktree_to_the_reaper"),
    ("agent-end reap: the primary checkout is no longer refused as a target",
     "agent_end_reap",
     '    if primary:\n        return "primary-checkout", []',
     '    if False:\n        return "primary-checkout", []',
     "test_the_primary_checkout_is_never_a_target"),
    ("agent-end reap: a live session in the worktree no longer keeps everything",
     "agent_end_reap",
     '    if live:\n        return "live-session", []',
     '    if False:\n        return "live-session", []',
     "test_a_live_session_in_the_worktree_keeps_everything"),
    ("agent-end reap: a live parent outside the worktree no longer keeps the process",
     "agent_end_reap",
     '        if not sweep._cwd_under_checkout(cwd, target):\n            return False',
     '        if not sweep._cwd_under_checkout(cwd, target):\n            return True',
     "test_a_process_whose_live_parent_sits_outside_is_kept"),
    ("agent-end reap: a process outside the target worktree is considered too",
     "agent_end_reap",
     '        if cwd is None or not sweep._cwd_under_checkout(cwd, target):\n            continue',
     '        if cwd is None:\n            continue',
     "test_an_orphan_in_another_worktree_is_not_even_considered"),
    ("agent-end reap: a finished tree idle under 30 minutes is removed",
     "agent_end_reap",
     'decide_agent_end_worktree(root, entry, sweep.AGENT_END_IDLE_SECONDS)',
     'decide_agent_end_worktree(root, entry, None)',
     "test_an_other_agent_tree_idle_31_minutes_is_removed_and_29_minutes_is_kept"),
    ("agent-end reap: an agent id is no longer checked, so a path in it escapes the worktrees",
     "agent_end_reap",
     'AGENT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")',
     'AGENT_ID = re.compile(r"^.{1,64}$")',
     "test_an_unsafe_or_unknown_agent_id_names_nothing"),
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

    ("dead-rooted: a script missing from a live directory is judged dead, and reaps",
     "sweep",
     '    if os.path.isdir(probe):\n        return None\n    levels = 0',
     '    levels = 0',
     "test_missing_script_in_a_live_directory_is_kept",
     "posix"),

    ("loose: a process without the shell-snapshots mark is listed as loose",
     "sweep",
     '        if not command or SESSION_MARK not in command or pid == os.getpid():',
     '        if not command or pid == os.getpid():',
     "test_marked_orphan_is_listed_and_unmarked_is_not",
     "posix"),

    ("prune: a preview prunes the stale registration for real",
     "sweep",
     '    if confirm and names:\n        done = git_reads._git(root, "worktree", "prune")',
     '    if names:\n        done = git_reads._git(root, "worktree", "prune")',
     "test_preview_names_the_stale_registration_and_prunes_nothing"),

    ("prune: an unreadable preview is read as an empty list and prunes on",
     "sweep",
     '    if preview is None or preview.returncode != 0:\n        return {"names": None,',
     '    if preview is None:\n        return {"names": None,',
     "test_an_unreadable_preview_prunes_nothing"),

    ("prune: the preview keeps a stale registration's branch checked out",
     "sweep",
     '        entries = [e for e in entries if not e["prunable"]]',
     '        pass',
     "test_preview_and_confirm_agree_on_a_branch_held_by_a_stale_registration"),

    ("prune: a failed real prune still drops the stale registrations from the verdict",
     "sweep",
     '    if result["pruned"] and result["pruned"]["names"] and not result["pruned"]["error"]:',
     '    if result["pruned"] and result["pruned"]["names"]:',
     "test_a_failed_prune_leaves_the_registration_and_its_branch_kept"),

    # ---- husks ----
    ("husks: a folder holding a file outside huskNames is listed as a husk",
     "sweep",
     '    if not contents or not set(contents) <= set(names):',
     '    if not contents:',
     "test_a_folder_holding_anything_else_is_not_a_husk"),

    ("husks: a registered worktree is listed as a husk",
     "sweep",
     '    if os.path.normcase(os.path.realpath(path)) in registered:\n        return None',
     '    if False:\n        return None',
     "test_a_registered_worktree_is_not_a_husk"),

    ("husks: a preview deletes the husk",
     "sweep",
     '    if confirm:\n        for decision in result["husks"] or []:',
     '    if True:\n        for decision in result["husks"] or []:',
     "test_preview_lists_a_husk_as_would_and_deletes_nothing",
     "posix"),

    ("husks: the delete skips the re-proof and trusts the preview",
     "sweep",
     '    again = husk_verdict(root, path, entries, names)',
     '    again = decision',
     "test_confirm_keeps_a_folder_that_gained_a_foreign_file_after_the_find",
     "posix"),

    ("husks: a folder that became a link is no longer refused",
     "sweep",
     '    if is_link(path) or not os.path.isdir(path):\n        return None\n    registered',
     '    if not os.path.isdir(path):\n        return None\n    registered',
     "test_confirm_refuses_a_folder_that_became_a_link",
     "posix"),

    ('husks: a worktrees folder that is a link out of the repository is walked',
     "sweep",
     '    if os.path.normcase(os.path.realpath(os.path.dirname(path))) != os.path.normcase(own_base):\n        return None\n',
     '',
     'test_a_symlinked_worktrees_base_is_never_walked_or_deleted',
     "posix"),

    ('husks: an empty process table reads as nobody inside',
     "sweep",
     '    return table or None\n',
     '    return table\n',
     'test_an_empty_table_is_unreadable'),

    ('husks: a husk whose delete failed prints REAP',
     "sweep",
     '            tag = "KEEP" if h.get("error") else {"husk"',
     '            tag = None if False else {"husk"',
     'test_a_failed_delete_prints_keep_with_the_error',
     "posix"),

    ('husks: a Windows junction is not seen as a link',
     "sweep",
     '    return bool(hasattr(st, "st_file_attributes")\n                and st.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)\n',
     '    return False\n',
     'test_is_link_sees_a_junction_and_a_symlink_and_not_a_real_folder',
     "windows"),

    # ---- build folders reaped at agent end (decisions/build-dirs-reaped-at-agent-end.md) ----
    ('build dirs: a link named as a build folder is renamed',
     'sweep',
     '            if d == ".git" or is_link(full):',
     '            if d == ".git":',
     'test_a_link_named_as_a_build_folder_is_kept_and_its_target_untouched',
     "posix"),

    ('build dirs: a bare name matches only at the worktree root',
     'sweep',
     '            elif d in names or os.path.relpath',
     '            elif os.path.relpath',
     'test_native_build_bare_build_at_depth_and_derived_data_are_reaped',
     "posix"),

    ('build dirs: a folder with a live process cwd inside is renamed',
     'agent_end_reap',
     '        if busy(folder):\n            continue\n        new',
     '        if False:\n            continue\n        new',
     'test_reap_build_dirs_skips_the_folder_that_holds_a_cwd',
     "posix"),

    ('build dirs: a trash name with a live process cwd inside is deleted by the reap',
     'agent_end_reap',
     'doomed = [t for t in trash if not busy(t)]',
     'doomed = list(trash)',
     'test_reap_build_dirs_keeps_a_trash_name_that_holds_a_cwd',
     "posix"),

    ('build dirs: the reap deletes under a live session or a primary checkout',
     'agent_end_reap',
     '    if reason is None:\n        # A build runs from the worktree root',
     '    if True:\n        # A build runs from the worktree root',
     'test_a_live_session_inside_the_worktree_keeps_everything',
     "posix"),

    ('build dirs: a live build run from the worktree root loses its folder',
     'agent_end_reap',
     'if any(d["action"] != "reap" for d in decisions):',
     'if False:',
     'test_a_live_build_with_its_cwd_at_the_worktree_root_keeps_every_build_folder',
     "posix"),

    ('build dirs: a mis-shaped buildDirs value is not validated',
     'sweep',
     '("protectedPrefixes", "huskNames", "buildDirs")',
     '("protectedPrefixes", "huskNames")',
     'test_a_bad_build_dirs_value_deletes_nothing',
     "posix"),

    ('build dirs: any folder name is a trash name',
     'sweep',
     'TRASH_RE = re.compile(r"^.+\\.reap-trash-[0-9a-f]{12}$")',
     'TRASH_RE = re.compile(r"^.+$")',
     'test_a_later_reap_deletes_a_leftover_trash_name_and_keeps_a_name_outside_the_pattern',
     "posix"),

    ('build dirs: the janitor deletes a trash name with a process inside',
     'sweep',
     '    if inside:\n        return False, "process-inside: pid %s" % ", ".join(str(p) for p in sorted(inside))\n    return True, "leftover trash"',
     '    return True, "leftover trash"',
     'test_the_janitor_deletes_a_leftover_trash_name_and_keeps_one_with_a_live_process',
     "posix"),

    ('build dirs: the hook deletes in its own process before it returns',
     'agent_end_reap',
     '            os.rename(folder, new)\n',
     '            os.rename(folder, new)\n            __import__("shutil").rmtree(new)\n',
     'test_the_hook_renames_the_build_folder_first_and_returns_before_the_delete',
     "posix"),

    ('macos cwd table: the pid and path lines are mis-parsed',
     "sweep",
     '            table.append((pid, line[1:]))',
     '            table.append((pid, line))',
     'test_parses_pid_and_cwd_lines'),

    ('macos cwd table: lsof exit 1 is read as unreadable',
     "sweep",
     '    if answer.returncode not in (0, 1):\n        return None\n    table = []',
     '    if answer.returncode not in (0,):\n        return None\n    table = []',
     'test_exit_1_is_readable_and_other_exits_are_not'),

    ('macos cwd table: any lsof exit code is read as readable',
     "sweep",
     '    if answer.returncode not in (0, 1):\n        return None\n    table = []',
     '    if False:\n        return None\n    table = []',
     'test_exit_1_is_readable_and_other_exits_are_not'),

    ('macos cwd table: a lsof timeout escapes instead of reading as unknown',
     "sweep",
     '                                timeout=timeout)\n    except Exception:',
     '                                timeout=timeout)\n    except OSError:',
     'test_a_timeout_is_unreadable'),

    ('macos cwd table: processes_in ignores the table',
     "sweep",
     '        return [pid for pid, cwd in table if _cwd_under_checkout(cwd, path)], []',
     '        return [], []',
     'test_darwin_processes_in_reads_one_table'),

    # only_on="posix": the sleep fixture is POSIX only.
    ("husks: a process inside no longer keeps the husk",
     "sweep",
     '    if inside:\n        return {"path": path, "action": "keep", "reason": "process-inside',
     '    if False:\n        return {"path": path, "action": "keep", "reason": "process-inside',
     "test_a_process_inside_keeps_the_husk",
     "posix"),

    # ---- the worktree pre-removal process check ----
    ("pre-check: a process sitting inside the worktree no longer keeps it",
     "sweep",
     '    if inside:\n'
     '        return {"path": path, "action": "keep",\n'
     '                "reason": "process-inside: pid %s" % ", ".join(str(p) for p in sorted(inside))}',
     '    if False:\n'
     '        return {"path": path, "action": "keep",\n'
     '                "reason": "process-inside: pid %s" % ", ".join(str(p) for p in sorted(inside))}',
     "test_a_process_inside_the_worktree_keeps_it_and_names_the_pid"),

    # ---- the stale agent lock (a dead or reused pid frees a clean, fully pushed worktree) ----
    ("stale lock: a dead agent's lock still keeps the worktree",
     "sweep",
     '        if stale_agent_lock is not True:\n',
     '        if True:\n',
     "test_dead_pid_lock_is_stale_and_pushed_worktree_is_removable"),
    ("stale lock: a running agent's lock no longer keeps",
     "sweep",
     '    return abs(actual - locked_ms) > git_reads.SESSION_LIVE_TOLERANCE_MS',
     '    return True',
     "test_running_agent_lock_keeps"),
    ("stale lock: an unreadable lock start counts as stale",
     "sweep",
     '        except Exception:\n'
     '            return None\n'
     '    actual = git_reads._process_start_ms(pid)',
     '        except Exception:\n'
     '            return True\n'
     '    actual = git_reads._process_start_ms(pid)',
     "test_unreadable_lock_start_keeps"),
    ("stale lock: a lock with no start time counts as stale, even when its host runs",
     "sweep",
     '    if locked_ms is None:\n'
     '        return False\n',
     '    if locked_ms is None:\n'
     '        return True\n',
     "test_a_sibling_agent_tree_locked_by_the_same_host_pid_is_kept"),
    ("stale lock: --confirm removes without unlocking first",
     "sweep",
     '        unlocked = git_reads._git(root, "worktree", "unlock", path)',
     '        unlocked = git_reads._git(root, "worktree", "list", path)',
     "test_remove_unlocks_then_removes_without_force"),
    ("pushed check: an unpushed commit no longer keeps an unlocked worktree",
     "sweep",
     '    if not pushed:\n'
     '        # Unpushed is only a loss',
     '    if False:\n'
     '        # Unpushed is only a loss',
     "test_unlocked_clean_detached_worktree_with_an_unpushed_commit_keeps"),
    # ---- merged counts as safe, strays listed, run log ----
    ("merged exemption: a squash-merged, never-pushed lane is kept as unpushed",
     "sweep",
     '        merged = _merged_read(where, path, batch) if has_remote else False\n',
     '        merged = False\n',
     "test_a_squash_merged_lane_never_pushed_is_removable"),
    ("merged exemption: every unpushed commit counts as merged",
     "sweep",
     '        merged = _merged_read(where, path, batch) if has_remote else False\n',
     '        merged = True\n',
     "test_a_truly_unpushed_unique_commit_is_still_kept"),
    ("merged exemption: the has-remote guard is dropped",
     "sweep",
     '        merged = _merged_read(where, path, batch) if has_remote else False\n',
     '        merged = _merged_read(where, path, batch)\n',
     "test_a_repository_with_no_remote_keeps_every_worktree"),
    ("strays: the sweep lists none",
     "sweep",
     '    result["strays"] = find_strays(root, entries)',
     '    result["strays"] = []',
     "test_preview_lists_both_strays_in_the_result_and_the_report"),
    ("run log: a preview run writes it too",
     "sweep",
     '        if args.confirm:  # one line per repository',
     '        if True:  # one line per repository',
     "test_preview_appends_no_run_line_and_the_confirm_after_it_does"),
    # ---- strict default: merged and idle 1 hour (decisions/when-a-worktree-may-be-removed.md) ----
    ("strict: the merged-and-idle check is skipped",
     "sweep",
     '    elif not attended:\n        kept = _strict_keep(where, path, idle, batch)',
     '    elif False:\n        kept = _strict_keep(where, path, idle, batch)',
     "test_strict_keeps_a_pushed_but_unmerged_tree"),
    ("strict: decide_worktree defaults to the permissive person's rules",
     "sweep",
     'def decide_worktree(where: str, entry: dict, attended: bool = False, agent_rule: bool = True,',
     'def decide_worktree(where: str, entry: dict, attended: bool = True, agent_rule: bool = True,',
     "test_strict_removes_a_detached_merged_tree_and_keeps_a_detached_unmerged_one"),
    ("strict: sweep_repo defaults to the permissive person's rules",
     "sweep",
     '               attended: bool = False):',
     '               attended: bool = True):',
     "test_the_attended_flag_reaches_the_sweep"),
    ("strict: the check applies to a person's run too",
     "sweep",
     '    elif not attended:\n        kept = _strict_keep(where, path, idle, batch)',
     '    elif True:\n        kept = _strict_keep(where, path, idle, batch)',
     "test_a_persons_run_removes_an_unmerged_active_tree_as_before"),
    ("strict: an unmerged tree no longer keeps",
     "sweep",
     '    if not merged:\n        if fast:',
     '    if False:\n        if fast:',
     "test_strict_keeps_a_pushed_but_unmerged_tree"),
    ("strict: a pushed unmerged tree idle 24 hours no longer reaps",
     "sweep",
     '        if idle >= STRICT_UNMERGED_IDLE_SECONDS:\n            return None\n',
     '        if False:\n            return None\n',
     "test_strict_removes_a_pushed_unmerged_tree_idle_25_hours"),
    ("strict: merged is tested by ancestry alone, not by patch",
     "sweep",
     '        merged = git_reads.branch_cherry_empty(path, base, "HEAD")',
     '        merged = False',
     "test_strict_removes_a_tree_merged_by_patch_idle_2_hours"),
    ("strict: merged is read in the root checkout, not the worktree",
     "sweep",
     '    merged = git_reads.branch_is_ancestor(path, base, "HEAD")',
     '    merged = git_reads.branch_is_ancestor(where, base, "HEAD")',
     "test_strict_keeps_a_pushed_but_unmerged_tree"),
    ("strict: a recently active tree no longer keeps",
     "sweep",
     '    if idle < STRICT_IDLE_SECONDS:',
     '    if False:',
     "test_strict_keeps_a_merged_tree_active_10_minutes_ago"),
    ("strict: the idle window shrinks to one minute",
     "sweep",
     'STRICT_IDLE_SECONDS = 60 * 60',
     'STRICT_IDLE_SECONDS = 60',
     "test_strict_keeps_a_merged_tree_active_10_minutes_ago"),
    ("fast: the idle hour no longer keeps a merged tree",
     "sweep",
     'kept = _strict_keep(where, path, float("inf") if attended else idle, batch, fast=True)',
     'kept = _strict_keep(where, path, float("inf"), batch, fast=True)',
     "test_keeps_a_merged_tree_idle_less_than_an_hour"),
    ("fast: a person's run still waits out the idle hour",
     "sweep",
     'kept = _strict_keep(where, path, float("inf") if attended else idle, batch, fast=True)',
     'kept = _strict_keep(where, path, idle, batch, fast=True)',
     "test_a_persons_run_removes_that_same_tree"),
    ("fast: a repository whose default branch is local only is swept",
     "sweep",
     '    if mode == "fast" and not base.startswith("origin/"):',
     '    if False:',
     "test_refuses_a_repository_whose_default_branch_is_local_only"),
    ("strict: an unreadable idle time reads as idle",
     "sweep",
     '    if idle is None:\n        return {"path": path, "action": "keep", "reason": "unreadable-subject"}\n    if idle < STRICT',
     '    if idle is None:\n        idle = 10 ** 9\n    if idle < STRICT',
     "test_strict_keeps_a_tree_whose_idle_time_cannot_be_read"),
    ("strict: the index mtime is ignored",
     "sweep",
     '    for name in ("index", os.path.join("logs", "HEAD")):',
     '    for name in (os.path.join("logs", "HEAD"),):',
     "test_strict_activity_in_any_one_admin_file_keeps_the_tree"),
    ("strict: the reflog mtime is ignored",
     "sweep",
     '    for name in ("index", os.path.join("logs", "HEAD")):',
     '    for name in ("index",):',
     "test_strict_activity_in_any_one_admin_file_keeps_the_tree"),
    ("strict: idle is read after git status has touched the index",
     "sweep",
     '    idle = worktree_idle_seconds(entry["path"]) if not attended else None\n'
     '    path = entry["path"]\n    dirty = git_reads.porcelain(path)\n',
     '    path = entry["path"]\n    dirty = git_reads.porcelain(path)\n'
     '    idle = worktree_idle_seconds(path) if not attended else None\n',
     "test_strict_removes_a_merged_tree_idle_2_hours"),
    ("strict: sweep_repo drops the flag before it judges a worktree",
     "sweep",
     'return decide_worktree(root, entry, attended, agent_rule, batch, mode == "fast")',
     'return decide_worktree(root, entry, agent_rule=agent_rule, batch=batch, fast=mode == "fast")',
     "test_the_attended_flag_reaches_the_sweep"),
    ("strict: main drops the flag before it sweeps",
     "sweep",
     'mode, args.attended)',
     'mode, False)',
     "test_main_takes_the_attended_flag"),

    ("stale lock: a failed remove leaves the worktree unlocked",
     "sweep",
     '            relock = git_reads._git(root, "worktree", "lock", "--reason",',
     '            relock = git_reads._git(root, "worktree", "list", "--reason",',
     "test_failed_remove_restores_the_lock"),
    # only_on="posix": the case needs time.tzset, which Windows lacks.
    ("stale lock: the lock date is read as local time, not UTC",
     "sweep",
     '        locked_ms = calendar.timegm(time.strptime(',
     '        locked_ms = time.mktime(time.strptime(',
     "test_lock_date_is_read_as_utc_in_a_non_utc_zone",
     "posix"),
    ("pushed check: the live remote heads are ignored (local refs decide)",
     "sweep",
     '    live = _live_remote_heads(path)\n'
     '    if live is None:\n'
     '        return None\n',
     '    live = _live_remote_heads(path)\n'
     '    if live is None:\n'
     '        return None\n'
     '    answer = git_reads._git(path, "rev-list", "-n", "1", "HEAD", "--not", "--remotes")\n'
     '    return not answer.stdout.strip()\n',
     "test_a_branch_deleted_on_the_remote_is_not_pushed_so_its_tree_is_kept"),
    ("pushed check: an unreadable pushed read reaps instead of keeping",
     "sweep",
     '    pushed = True if fast else fully_pushed(path)\n'
     '    if pushed is None:',
     '    pushed = True if fast else fully_pushed(path)\n'
     '    if False:',
     "test_unreadable_pushed_check_keeps"),
    ("stale lock: an unreadable process start counts as stale",
     "sweep",
     '    if actual is git_reads.PROCESS_START_UNREADABLE:\n'
     '        return None',
     '    if actual is git_reads.PROCESS_START_UNREADABLE:\n'
     '        return True',
     "test_unreadable_process_start_is_unknown_not_stale"),
    ("stale lock: a lock reason of another form counts as stale",
     "sweep",
     '    if not found:\n'
     '        return False',
     '    if not found:\n'
     '        return True',
     "test_other_lock_reason_keeps"),
    ("stale lock: the decision no longer asks for an unlock",
     "sweep",
     '"unlock": True, "lock_reason": holder}',
     '"unlock": False, "lock_reason": holder}',
     "test_dead_pid_lock_is_stale_and_pushed_worktree_is_removable"),

    # The per-run read cache (PreviewCacheTests). Each mutant lets a stale or wrong read through.
    ("preview cache: a run with --confirm is cached too",
     "sweep",
     'if not args.confirm and mode != "tier1" else',
     'if mode != "tier1" else',
     "test_only_a_preview_caches_and_the_guard_reads_come_back_after"),
    ("preview cache: --tier1, which acts, is cached too",
     "sweep",
     'if not args.confirm and mode != "tier1" else',
     'if not args.confirm else',
     "test_only_a_preview_caches_and_the_guard_reads_come_back_after"),
    ("preview cache: the guard reads stay wrapped after the run",
     "sweep",
     '        git_reads._git, git_reads.session_records = real_git, real_records',
     '        pass',
     "test_only_a_preview_caches_and_the_guard_reads_come_back_after"),
    ("preview cache: a read is never stored",
     "sweep",
     '            _RUN[key] = compute()\n        return _RUN[key]',
     '            return compute()\n        return _RUN[key]',
     "test_cwd_table_is_read_once_per_preview_and_never_outside_one"),
    ("preview cache: the cache is not cleared after the run",
     "sweep",
     '        _RUN = None\n        git_reads._git, git_reads.session_records = real_git, real_records',
     '        pass\n        git_reads._git, git_reads.session_records = real_git, real_records',
     "test_cwd_table_is_read_once_per_preview_and_never_outside_one"),
    ("preview cache: every git read is cached, not only the worktree list",
     "sweep",
     '        if args == _WORKTREE_LIST_ARGS:',
     '        if True:',
     "test_worktree_list_is_read_once_per_repository_and_other_git_reads_are_not_cached"),
    ("preview cache: one repository answers for another",
     "sweep",
     '_memo(("git", where),',
     '_memo(("git",),',
     "test_worktree_list_is_read_once_per_repository_and_other_git_reads_are_not_cached"),
    ("preview cache: the session records are read every time",
     "sweep",
     '    git_reads.session_records = lambda: _memo("sessions", real_records)',
     '    git_reads.session_records = real_records',
     "test_session_records_are_read_once_per_preview"),
    ("preview cache: a failed ps table reads as an empty table",
     "sweep",
     '    return _NO_TABLE if table is None else table.get(pid)',
     '    return None if table is None else table.get(pid)',
     "test_a_failed_ps_table_falls_back_to_the_per_pid_read"),
    ("preview cache: an empty ps table reads as no process",
     "sweep",
     '    return table if table else None  # an empty',
     '    return table  # an empty',
     "test_an_empty_ps_table_falls_back_to_the_per_pid_read"),
    ("preview cache: Linux reads the ps table too",
     "sweep",
     '    if _RUN is None or sys.platform != "darwin":',
     '    if _RUN is None:',
     "test_without_a_preview_every_read_is_per_pid_and_linux_never_uses_the_table"),
    ("preview cache: the pid list comes from the table outside a preview",
     "sweep",
     '    if sys.platform == "darwin" and _RUN is not None:',
     '    if sys.platform == "darwin":',
     "test_without_a_preview_every_read_is_per_pid_and_linux_never_uses_the_table"),
    # only_on="posix": test_one_ps_table_... needs os.getuid and is skipped on Windows, so it
    # cannot kill the two table-read mutants below (the table path is macOS only).
    ("preview cache: the orphan read ignores the table",
     "sweep",
     '            return _ppid_is_init(row[0] if row else "")',
     '            return _ppid_is_init("1")',
     "test_one_ps_table_answers_command_orphan_owner_and_pid_list_on_macos",
     "posix"),
    ("preview cache: a pid with two cwd lines answers with the last",
     "sweep",
     '        found.setdefault(pid, cwd)',
     '        found[pid] = cwd',
     "test_one_cwd_table_answers_every_process_cwd_in_a_preview_on_macos"),
    ("preview cache: the cwd read ignores the table",
     "sweep",
     '    if _RUN is not None:\n        table = _all_cwds_macos()',
     '    if False:\n        table = _all_cwds_macos()',
     "test_one_cwd_table_answers_every_process_cwd_in_a_preview_on_macos"),
    ("preview cache: the owner read ignores the table",
     "sweep",
     '            return _uid_is_mine(row[1] if row else "")',
     '            return _uid_is_mine(str(os.getuid()))',
     "test_one_ps_table_answers_command_orphan_owner_and_pid_list_on_macos",
     "posix"),
    # The parallel preview (ParallelPreviewTests). only_on="posix" on all but "all at once": a
    # Windows preview stays serial (PREVIEW_THREADS), so no test can see these there.
    ("parallel preview: confirm no longer forces the one-at-a-time map",
     "sweep",
     '    if acts or pool is None or len(items) < 2:',
     '    if pool is None or len(items) < 2:',
     "test_a_run_that_acts_gets_one_decision_at_a_time_even_with_the_pool_open",
     "posix"),
    ("parallel preview: the branch loop does not say it acts",
     "sweep",
     '            branches, confirm)):',
     '            branches, False)):',
     "test_confirm_never_runs_decisions_side_by_side_even_with_the_pool_open",
     "posix"),
    ("parallel preview: a run that acts gets its decisions all at once",
     "sweep",
     '    if acts or pool is None or len(items) < 2:\n        return map(fn, items)',
     '    if acts or pool is None or len(items) < 2:\n        return iter(list(map(fn, items)))',
     "test_pmap_is_lazy_and_in_order_outside_a_preview"),
    ("parallel preview: results come back in finishing order",
     "sweep",
     '    return pool.map(fn, items)',
     '    return reversed(list(pool.map(fn, items)))',
     "test_pmap_returns_results_in_input_order_when_the_second_finishes_first",
     "posix"),
    ("parallel preview: two workers run the same cached read",
     "sweep",
     '    with _RUN_LOCK:\n        if key not in _RUN:',
     '    if True:\n        if key not in _RUN:',
     "test_a_cached_read_runs_once_when_workers_ask_together",
     "posix"),
    ("parallel preview: the pools stay open after the run",
     "sweep",
     '        _POOL = _ROOT_POOL = None',
     '        pass',
     "test_only_a_preview_caches_and_the_guard_reads_come_back_after",
     "posix"),
    # ---- the agent worktree rule (decisions/when-a-worktree-may-be-removed.md) ----
    ("agent rule: a finished agent tree is never removed past the older keeps",
     "sweep",
     '        if kept and agent_rule and _is_agent_worktree(where, path):',
     '        if False:',
     "test_a_removes_a_clean_pushed_tree_idle_5h_with_its_local_branch"),
    ("agent rule: the path check is dropped, so any tree can go",
     "sweep",
     '        if kept and agent_rule and _is_agent_worktree(where, path):',
     '        if kept and agent_rule:',
     "test_f_keeps_a_tree_outside_agent_folders_and_the_main_checkout"),
    ("agent rule: any name under the worktrees folder counts as an agent tree",
     "sweep",
     'name.startswith("agent-")',
     'name.startswith("")',
     "test_f_keeps_a_tree_outside_agent_folders_and_the_main_checkout"),
    ("agent rule: the 4 hour floor is gone",
     "sweep",
     '    if idle < AGENT_IDLE_SECONDS:',
     '    if False:',
     "test_b_keeps_a_pushed_unmerged_tree_idle_under_4h"),
    ("agent rule: the floor shrinks to zero",
     "sweep",
     'AGENT_IDLE_SECONDS = 4 * 60 * 60',
     'AGENT_IDLE_SECONDS = 0',
     "test_b_keeps_a_pushed_unmerged_tree_idle_under_4h"),
    ("agent rule: an unreadable idle time passes the 4 hour floor (idle_none_ok)",
     "sweep",
     '    if kept["reason"] == "unreadable-subject":\n        return kept\n    if idle < AGENT_IDLE_SECONDS:',
     '    if idle is not None and idle < AGENT_IDLE_SECONDS:',
     "test_j_keeps_a_tree_whose_idle_time_cannot_be_read"),
    ("agent rule: an empty remote-tracking read no longer keeps (contains_empty_ok)",
     "sweep",
     '    if not contains.stdout.strip():',
     '    if False:',
     "test_j_keeps_a_tree_the_remote_lists_when_no_tracking_ref_holds_its_head"),
    ("agent rule: a failed remote-tracking read no longer keeps",
     "sweep",
     '    if contains is None or contains.returncode != 0:',
     '    if False:',
     "test_h_keeps_a_tree_when_the_remote_reach_read_fails_and_logs_it"),
    ("agent rule: the repo's own remover no longer turns the rule off",
     "sweep",
     'return decide_worktree(root, entry, attended, agent_rule, batch, mode == "fast")',
     'return decide_worktree(root, entry, attended, True, batch, mode == "fast")',
     "test_g_runs_the_repos_remover_with_remove_and_removes_nothing_itself"),
    ("agent rule: the repo's own remover is never run",
     "sweep",
     '            elif confirm:\n                result["reaper"] = run_repo_reaper(root) or "ran"',
     '            elif False:\n                result["reaper"] = run_repo_reaper(root) or "ran"',
     "test_g_runs_the_repos_remover_with_remove_and_removes_nothing_itself"),
    ("agent rule: the repo's remover runs without --remove",
     "sweep",
     '[npm, "run", REAPER_SCRIPT, "--", "--remove"]',
     '[npm, "run", REAPER_SCRIPT]',
     "test_g_runs_the_repos_remover_with_remove_and_removes_nothing_itself"),
    ("agent rule: the repo's remover runs outside the repo",
     "sweep",
     'cwd=root, capture_output=True,',
     'cwd=os.path.dirname(root), capture_output=True,',
     "test_g_runs_the_repos_remover_with_remove_and_removes_nothing_itself"),
    # ---- the simulator tier (decisions/sweep-shuts-down-idle-simulators.md) ----
    ("simulator: a device booted under an hour ago is shut down",
     "sweep",
     '        return "booted-recently"',
     '        return None',
     "test_booted_under_an_hour_is_kept",
     "posix"),
    ("simulator: a process outside the device tree naming it no longer holds it",
     "sweep",
     '            return "held-by-process"',
     '            return None',
     "test_a_process_outside_the_device_tree_naming_its_udid_keeps_it",
     "posix"),
    ("simulator: Simulator.app running no longer keeps a device",
     "sweep",
     '        return "simulator-app-running"',
     '        return None',
     "test_simulator_app_running_keeps_every_device",
     "posix"),
    ("simulator: Xcode.app running no longer keeps a device",
     "sweep",
     '        return "xcode-running"',
     '        return None',
     "test_xcode_running_keeps_every_device",
     "posix"),
    ("simulator: an unreadable device list no longer keeps a device",
     "sweep",
     '"simctl-unreadable" if devices is None else',
     'None if devices is None else',
     "test_a_failed_simctl_read_keeps_every_device",
     "posix"),
    ("simulator: an unreadable process table reads as an empty one",
     "sweep",
     'if table is None:\n        return "process-table-unreadable"',
     'table = {}',
     "test_a_failed_process_table_keeps_every_device",
     "posix"),
    ("simulator: an unreadable boot time no longer keeps a device",
     "sweep",
     '        return "start-time-unreadable"',
     '        return None',
     "test_an_unreadable_start_time_keeps_that_device",
     "posix"),

    # ---- the sweep finishes: the judge deadline, oldest first ----
    ("deadline: a pass past its budget still judges every tree",
     "sweep",
     '        if _past_deadline():\n'
     '            return {"path": entry["path"], "action": "keep", "reason": "not judged: deadline"}\n',
     '        if False:\n'
     '            return {"path": entry["path"], "action": "keep", "reason": "not judged: deadline"}\n',
     "test_a_pass_past_its_deadline_stops_judging_and_reports_the_rest_not_judged"),
    ("oldest first: the sweep judges the youngest idle tree first",
     "sweep",
     '-(idle[e["path"]] or 0)',
     '(idle[e["path"]] or 0)',
     "test_the_oldest_idle_tree_is_judged_first"),
    ("deadline budget: NaN is no deadline, so every tree is judged",
     "sweep",
     '    _DEADLINE = None if n is None else _now() + (\n',
     '    _DEADLINE = None if n is None or n != n else _now() + (\n',
     "test_a_nan_deadline_has_no_time_left_and_judges_no_tree"),
    ("deadline budget: N <= 0 is no deadline, so every tree is judged",
     "sweep",
     '    _DEADLINE = None if n is None else _now() + (\n',
     '    _DEADLINE = None if n is None or n <= 0 else _now() + (\n',
     "test_a_negative_deadline_has_no_time_left_and_judges_no_tree"),
    ("deadline budget: the 7.5 s tail is ignored, so 7.5 s gets a 7.5 s budget",
     "sweep",
     'min(JUDGE_BUDGET_SECONDS, n - DEADLINE_TAIL_SECONDS))',
     'min(JUDGE_BUDGET_SECONDS, n))',
     "test_a_7_5_second_deadline_is_all_tail_so_its_budget_is_zero"),
    ("deadline budget: no 12 s cap, so 25 s gets a 17.5 s budget",
     "sweep",
     'min(JUDGE_BUDGET_SECONDS, n - DEADLINE_TAIL_SECONDS))',
     'n - DEADLINE_TAIL_SECONDS)',
     "test_a_25_second_deadline_gives_a_12_second_budget"),
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
    """Lay out <scaffold>/hooks/guard*.py, <scaffold>/janitor/{sweep.py,test_sweep.py,
    session_end_sweep.py,test_session_end_sweep.py} and <scaffold>/settings.json so that running
    either suite from <scaffold>/janitor resolves `import guard`, `import sweep` and
    `import session_end_sweep` to the copies placed here (see the module docstring, "WHY A
    SCAFFOLD DIRECTORY"). Exactly one of guard.py / sweep.py / session_end_sweep.py carries
    `mutated_text`; the rest are the real sources, unchanged. Both suites, and settings.json, are
    always the real sources: this mutation test never edits a suite or the real settings.json."""
    hooks_dir = os.path.join(scaffold, "hooks")
    janitor_dir = os.path.join(scaffold, "janitor")
    os.makedirs(hooks_dir, exist_ok=True)
    os.makedirs(janitor_dir, exist_ok=True)
    shutil.copy(os.path.join(REPO_ROOT, "hooks", "_nowindow.py"), hooks_dir)  # sweep.py imports it; never mutated
    shutil.copy(os.path.join(REPO_ROOT, "hooks", "shared_names.py"), hooks_dir)  # guard_core.py imports it; never mutated
    # sweep.py and guard_core.py import it. The loop below replaces this copy when `sources` holds
    # the target's own text for it (the mutated one, or the real one).
    shutil.copy(GIT_READS, hooks_dir)
    shutil.copy(os.path.join(HERE, "temp_sweep.py"), janitor_dir)  # sweep.py imports it; never mutated

    sweep_text = mutated_text if mutated_target == "sweep" else sources["sweep"]
    session_end_text = (
        mutated_text if mutated_target == "session_end_sweep" else sources["session_end_sweep"]
    )

    for name in sources:
        if is_guard_key(name):
            text = mutated_text if mutated_target == name else sources[name]
            with open(os.path.join(hooks_dir, name + ".py"), "w", encoding="utf-8",
                      newline="\n") as h:
                h.write(text)
    with open(os.path.join(janitor_dir, "sweep.py"), "w", encoding="utf-8", newline="\n") as h:
        h.write(sweep_text)
    with open(os.path.join(janitor_dir, "test_sweep.py"), "w", encoding="utf-8", newline="\n") as h:
        h.write(sources["test_sweep"])
    reap_text = mutated_text if mutated_target == "agent_end_reap" else sources["agent_end_reap"]
    with open(os.path.join(janitor_dir, "agent_end_reap.py"), "w", encoding="utf-8",
              newline="\n") as h:
        h.write(reap_text)
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


def run_suite(suite_path: str, config_dir: str, only=None):
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
    result = _nowindow.run(
        # text=True keeps the default decoding: the child inherits env, so both sides share one encoding.
        [sys.executable, suite_path] + (["-k", only] if only else []), capture_output=True, text=True, env=env, timeout=1200,
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
        code, red = mutate_shared.staged_suite(
            lambda only: run_suite(suite_path, config_dir, only), required)
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

    # MUTATE_ONLY=<fragment>[,<fragment>...] runs only the mutants whose label holds a fragment.
    # Every anchor is still checked above. Unset, every mutant runs.
    wanted = [f for f in os.environ.get("MUTATE_ONLY", "").split(",") if f]
    chosen = [(i, entry) for i, entry in enumerate(MUTATIONS)
              if not wanted or any(f in entry[0] for f in wanted)]
    if not chosen:
        print("ERROR MUTATE_ONLY matches no mutation: %s" % ",".join(wanted))
        return 1

    work = tempfile.mkdtemp(prefix="mutate_sweep_")
    try:
        return mutate_shared.run_mutants(
            chosen,
            lambda item: run_mutant(sources, work, item[0], item[1]))
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
