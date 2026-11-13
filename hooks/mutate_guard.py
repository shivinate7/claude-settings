#!/usr/bin/env python3
"""Mutation test for hooks/guard.py.

Stdlib only. For each mutation below, it copies guard.py to a temp file, applies one
literal string replacement, and runs hooks/test_guard.py against the copy with
GUARD_UNDER_TEST=<copy> and CLAUDE_CONFIG_DIR=<temp dir>. The suite must go red
(a nonzero exit backed by at least one FAIL line). A mutation the suite does not
catch is "survived", and any survivor fails this run.

A RED SUITE IS NOT ENOUGH. A mutant could die on a case unrelated to the rule its label
names, which proves nothing about that rule. Every mutation below therefore
carries a fifth field: the case name (or a distinctive fragment of it) that MUST appear among
the suite's own FAIL lines. A mutant whose red lines miss that name is "WRONG CAUSE", kept
distinct from "survived", and fails this run exactly as a survivor does. The field is mandatory:
`mutation_parts` and `run_mutant` refuse a mutation that carries none.

A mutation whose replacement string is not found in the current guard.py is STALE:
the source moved on and the mutation no longer proves anything. That must fail
loudly, not be skipped, so it exits 1 with an error line instead of counting the
mutation either way.

The mutants run IN PARALLEL, one suite process per mutant, up to the CPU count at once
(MUTATE_JOBS overrides). Each mutant gets its own guard copy and its own config directory, so
the runs share nothing but the read-only fixture tree the suite builds under its own temp
root. The suite itself spawns guard.py once per case, which is where the time goes.

Run:
    python hooks/mutate_guard.py

REPORT MODE (step c95): `python hooks/mutate_guard.py --report [--limit N] [--jobs N] [--only SUBSTR]`
scores other verdict-deciding files with mechanical mutants (hooks/mutate_shared.py `score_target`)
and prints, per file, mutants made, killed, kill rate and the suites that killed none. It reads on
demand and refuses nothing: no timer, no CI job.

REPLAY MODE (step tci-6): `python hooks/mutate_guard.py --replay <repo> --profile <name> [--prs N] [--limit N]
[--suite-timeout S] [--jobs N] [--pr-budget S]` scores the suites each recent merged pull request changed against mutants of the
product lines it added (`REPLAY_PROFILES` below, `replay_pr` in hooks/mutate_shared.py). Exit 0 whatever the scores.

CI MODES (decision mutation-report-scores-suites, owner item mutation-ci-job): three modes of the same home, run by the shared
action actions/mutation-report.
`--changed <repo> (--profile NAME | --profile-file JSON) --base REF [--head REF] [--limit N] [--budget S] [--suite-timeout S]
[--jobs N] [--log PATH]` mutates the product lines a change adds past merge-base(base, head), runs the suites the profile's `select`
lists for each file, and prints `catch share: K/R` and each `untested: path:line`. Exit 1 when mutants were made and none ran,
or when none ran because the run stopped first (the diff could not be read, a file did not parse, the checkout or the
install was refused, or the replay raised). A `no mutant ran: ...` line says so, with the cause. Exit 0 otherwise, whatever the share.
`--known-defects FILE --repo REPO (--profile NAME | --profile-file JSON) [--base REF] [--suite-timeout S] [--log PATH]`
plants each listed defect in a checkout of HEAD, installs the profile's packages into it as `--changed` does, and runs its
catcher suite: `CAUGHT`, `MISS` or `UNKNOWN` per defect. With `--base`, each id on REF's list also needs a row, or a
`Known-defect-removed: <id>` trailer in REF..HEAD, else `MISSING <id>`; an entry that differs from REF's needs a
`Known-defect-changed: <id>` trailer, else `CHANGED <id>`. Exit 1 when any defect is MISS, UNKNOWN, MISSING or CHANGED.
`--tests-for PATH` prints the suites that test one file: the select command of the `claude_settings` profile. A guard module
with a family row also prints its `hooks/test_guard.py::<family>` lines beside the suites that import it.
"""

import contextlib
import functools
import os
import shutil
import signal
import subprocess
import sys
import tempfile

import mutate_shared
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  git's tracked files under a folder, suites left out (testing/tracked_tree.py)
GUARD = os.path.join(HERE, "guard.py")
SUITE = os.path.join(HERE, "test_guard.py")
WATCH = os.path.join(HERE, "config_watch.py")
WATCH_SUITE = os.path.join(HERE, "test_config_watch.py")
DECISION = os.path.join(HERE, "decision_watch.py")
DECISION_SUITE = os.path.join(HERE, "test_decision_watch.py")
RULING = os.path.join(HERE, "ruling_home.py")
RULING_SUITE = os.path.join(HERE, "test_ruling_home.py")
OVERRIDE = os.path.join(HERE, "override.py")
CALL_JUDGE = os.path.join(HERE, "call_judge.py")
CALL_JUDGE_SUITE = os.path.join(HERE, "test_call_judge.py")
SIM_LEASE = os.path.join(HERE, "..", "bin", "sim-lease")
MERGE_TOOL = os.path.join(HERE, "..", "merge", "merge.py")

# A mutation names the file it breaks and the suite that must catch it. "guard" is the default, so
# every mutation written before the watch existed reads unchanged.
TARGETS = {
    "guard": (GUARD, SUITE, "GUARD_UNDER_TEST", "guard"),
    "watch": (WATCH, WATCH_SUITE, "WATCH_UNDER_TEST", "config_watch"),
    "decision": (DECISION, DECISION_SUITE, "DECISION_WATCH_UNDER_TEST", "decision_watch"),
    "ruling": (RULING, RULING_SUITE, "RULING_HOME_UNDER_TEST", "ruling_home"),
    "override": (OVERRIDE, SUITE, "GUARD_UNDER_TEST", "override"),
    "calljudge": (CALL_JUDGE, CALL_JUDGE_SUITE, "CALL_JUDGE_UNDER_TEST", "call_judge"),
    # bin/sim-lease, which the guard loads by path (hooks/guard.py sim_lease_holds). The suite is the guard's.
    "simlease": (SIM_LEASE, SUITE, "GUARD_UNDER_TEST", "sim_lease"),
    # merge/merge.py, the clean-merge walk the fix-branch refusal reads (guard_merge loads it beside hooks/). The suite is the guard's.
    "merge": (MERGE_TOOL, SUITE, "GUARD_UNDER_TEST", "merge"),
}

# (label, anchor text found once in the source, its mutated replacement, target, required case
# name). Each one breaks exactly one rule. One mutation per rule at least:
# shared-tree, machine-wide kill, live-stream, waiter, force push, destructive
# delete, env-file, frozen-path, the redirect strip, and the log.
#
# THE FIFTH FIELD is the case name, or a distinctive fragment of it, that must show up among the
# suite's own FAIL lines: `hooks/test_guard.py`'s FAIL line already prints `case["name"]` verbatim,
# and `hooks/test_config_watch.py`'s does the same with `entry["name"]`, so no second file needed
# a change to carry this. Each name was MEASURED against this file's own mutants, not guessed: a
# label's prose is a statement about which rule breaks, and the required name is the proof that some
# case actually reads that break, not a different one nearby.
MUTATIONS = [
    # THE TWO ROOTS. `--work-tree` names whose FILES a call discards, and `--git-dir` names whose
    # HEAD it moves. Each mutant makes one of them unread, or makes one root answer the other's
    # question.
    ("work-tree: the tree option goes unread, so rule 1 judges the wrong tree",
     'GIT_WORK_TREE_RE = re.compile(r"--work-tree(?:=|\\s+)([\'\\"]?)([^\'\\";&|\\s]+)\\1")',
     'GIT_WORK_TREE_RE = re.compile(r"--never-a-real-option(\\A\\Z)(\\A\\Z)")', "guard", 'work-tree: a clean cwd pointed at a dirty tree is judged on the dirty tree'),
    ("pointer-head: the git directory option goes unread",
     'GIT_DIR_RE = re.compile(r"--git-dir(?:=|\\s+)([\'\\"]?)([^\'\\";&|\\s]+)\\1")',
     'GIT_DIR_RE = re.compile(r"--never-a-real-option(\\A\\Z)(\\A\\Z)")', "guard", 'pointer: --git-dir reaches the pointer HEAD from an unrelated directory'),
    ("pointer-head: the HEAD root falls back through the work tree, naming the wrong HEAD",
     '        return run_dir\n    return _absolute(match.group(2), run_dir)',
     '        return guard_core.command_root(cmd, shell_cwd)\n    return _absolute(match.group(2), run_dir)', "guard", 'pointer: --work-tree alone moves no HEAD in the pointer checkout'),
    ("pointer-head: read the shared common git directory, so a worktree reads as its primary",
     '        answer = guard_core._git(where, "rev-parse", "--absolute-git-dir")',
     '        answer = guard_core._git(where, "rev-parse", "--git-common-dir")', "guard", 'pointer: switch of a branch in another checkout is allowed'),
    # RULE 1b, the pointer checkout's HEAD. Each mutant breaks one arm: the act test, the tree
    # test, the main exemption, the two path-operation arms, the `switch` subcommand, the top-level
    # read, and the pointer parse.
    ("pointer-head: no command ever moves HEAD",
     'def head_move_target(subcommand: str, args) -> str:',
     'def head_move_target(subcommand: str, args) -> str:\n    return ""', "guard", 'pointer: checkout of a branch in the pointer checkout is refused'),
    ("pointer-head: call every tree the pointer checkout",
     '    return mine == theirs',
     '    return True', "guard", 'pointer: checkout of a branch in another checkout is allowed'),
    # RULE pointer-edit, a write into the pointer checkout's own files. Each mutant breaks one arm.
    ("pointer-edit: the pointer's own .git is judged like a file of the checkout",
     '                and path_is_inside(resolved, git_dir) is not True\n',
     '', "guard", 'pointer-edit: Write into the pointer\'s own .git is not judged'),
    ("pointer-edit: a linked worktree nested under the pointer is judged like a file of the checkout",
     '                and path_is_inside(resolved, worktree_dir) is not True)',
     '                and True)', "guard", 'pointer-edit: Write into a linked worktree nested under the pointer is allowed'),
    ("pointer-edit: no write is ever judged",
     '    pointer = pointer_checkout()\n    if not pointer:\n        return ""\n    git_dir',
     '    return ""\n    pointer = pointer_checkout()\n    if not pointer:\n        return ""\n    git_dir', "guard", 'pointer-edit: Write of a tracked file in the pointer checkout is refused'),
    # The gate is WRITE_TOOLS. Artifact and ArtifactData carry a file_path too, and both allow cases go red when it drops.
    ("pointer-edit: the write-tool gate is dropped, so Artifact and ArtifactData are judged like writes",
     '    pointer_hit = pointer_edit_hit(write_targets(tool_input), cwd) if tool in WRITE_TOOLS else ""',
     '    pointer_hit = pointer_edit_hit(write_targets(tool_input), cwd)', "guard", 'with a pointer file as file_path is not a write and is allowed'),
    ("pointer-head: lose the exemption for a move to main",
     '    if target == PROTECTED_BASE:\n        return ""',
     '    if target == "no-such-branch":\n        return ""', "guard", 'pointer: a move back to main restores the invariant and passes'),
    ("pointer-head: read a double dash as a branch",
     '    if "--" in args:\n        return ""\n    switching = subcommand == "switch"',
     '    if False:\n        return ""\n    switching = subcommand == "switch"', "guard", 'pointer: a double dash names a path, and no HEAD moves'),
    ("pointer-head: forget the path-operation flags",
     'CHECKOUT_PATH_FLAGS = {"--ours", "--theirs", "--patch", "-p", "--overlay", "--no-overlay"}',
     'CHECKOUT_PATH_FLAGS = set()', "guard", 'pointer: --theirs with an extensionless path is no branch switch'),
    ("pointer-head: watch checkout and not switch",
     'HEAD_MOVE_SUBCOMMANDS = ("checkout", "switch")',
     'HEAD_MOVE_SUBCOMMANDS = ("checkout",)', "guard", 'pointer: switch of a branch in the pointer checkout is refused'),
    ("pointer-head: compare the directory as written, not the git directory git reports",
     '    mine = git_dir_of(root)',
     '    mine = os.path.normcase(os.path.realpath(root)) if root else ""', "guard", 'pointer: a subdirectory of the pointer checkout is still the pointer checkout'),
    ("pointer-head: a pointer line that never parses",
     'POINTER_LINE = re.compile(r"^@(.+)/CLAUDE\\.md[ \\t]*$", re.MULTILINE)',
     'POINTER_LINE = re.compile(r"^@@(.+)/CLAUDE\\.md[ \\t]*$", re.MULTILINE)', "guard", 'pointer: a new branch with -b is refused'),
    ("shared-tree: drop the git clean arm",
     '        if subcommand == "clean" and clean_deletes_files(args):',
     '        if False and clean_deletes_files(args):', "guard", 'clean: -fd deletes untracked files'),
    ("shared-tree: call every tree a worktree",
     '    return own != common',
     '    return True', "guard", 'worktree: a hard reset in the shared checkout denies'),
    ("shared-tree: an agent's own worktree never counts as agent-owned",
     '            if agent_owned_worktree(root) is True:',
     '            if False:', "guard",
     'agent-owned worktree is allowed and noted, not asked'),
    ("shared-tree: a lone operand that is also a revision still reads as a dirty file",
     '    if rev.returncode == 0:\n        return False\n',
     '    if False:\n        return False\n', "guard",
     'per-file bare: checkout of a dirty file that is also a branch in the shared checkout allows'),
    ("shared-tree: a lone operand with no tracked change still reads as a dirty file",
     '    return any(line[:2] != "??" for line in lines)\n',
     '    return True\n', "guard",
     'per-file bare: checkout of an untracked extensionless file in the shared checkout allows'),
    ("shared-tree: a revision read that gets no answer is no longer logged as subject-unread",
     '    if rev is None:\n        guard_core.record("Bash", "noted", "subject-unread", "git checkout " + name)\n',
     '    if rev is None:\n        pass\n', "guard",
     'a bare checkout of a dirty file with no git on PATH is allowed and logged once as subject-unread'),
    ("shared-tree: a status read that gets no answer is no longer logged as subject-unread",
     '    if lines is None:\n        guard_core.record("Bash", "noted", "subject-unread", "git checkout " + name)\n',
     '    if lines is None:\n        pass\n', "guard",
     'a bare checkout of a dirty file whose status git cannot read is allowed and logged once as subject-unread'),

    # ---- rule 1's three new git forms: branch delete, worktree remove, worktree prune. Each
    # mutation breaks one arm of the state read the plan named as the safety hole in this rule.
    ("branch-delete: -D no longer marks a delete call",
     'BRANCH_DELETE_FLAGS = {"-d", "-D", "--delete"}',
     'BRANCH_DELETE_FLAGS = {"-d", "--delete"}', "guard",
     'branch: a commit found nowhere else is the only copy, and the rule denies'),
    ("branch-delete: -d no longer marks a delete call",
     'BRANCH_DELETE_FLAGS = {"-d", "-D", "--delete"}',
     'BRANCH_DELETE_FLAGS = {"-D", "--delete"}', "guard",
     'branch: -d over the same only-copy branch still denies'),
    ("branch-delete: the ancestor test asks the question backwards",
     '    answer = _git(where, "merge-base", "--is-ancestor", branch, base)',
     '    answer = _git(where, "merge-base", "--is-ancestor", base, branch)', "guard",
     'branch: a commit found nowhere else is the only copy, and the rule denies'),
    ("branch-delete: a shallow clone's unknown ancestry stops the proof, so -D over the only copy is allowed",
     '        ancestor = False\n    if ancestor:\n        return "ancestor"',
     '        return None\n    if ancestor:\n        return "ancestor"', "guard",
     'branch delete, shallow clone: the only copy is denied'),
    ("branch-delete: cherry never reads as empty, so a rebased patch looks unique",
     '    return not any(line.startswith("+") for line in answer.stdout.splitlines())',
     '    return False', "guard",
     "branch: a rebased commit's patch already sits on origin/main, cherry proves it"),
    ("branch-delete: no remote ever contains a branch",
     '    return bool(answer.stdout.strip())',
     '    return False', "guard", 'branch: a commit pushed to the remote is not the only copy'),
    ("branch-delete: the only-copy branch never denies",
     '        if empty is False:\n            return False\n    return True',
     '        if False:\n            return False\n    return True', "guard",
     'branch: a commit found nowhere else is the only copy, and the rule denies'),
    ("branch-delete: the base never falls back past origin/HEAD",
     '    candidates = [remote + "/main", remote + "/master", "main", "master"]',
     '    candidates = []', "guard",
     'branch: local main\'s fallback still denies an only-copy branch'),

    ("worktree-remove: --force is read as the path, missing the real target",
     '    for arg in args:\n        if arg.startswith("-"):\n            continue\n        '
     'return _absolute(arg, where)\n    return ""',
     '    for arg in args:\n        if False:\n            continue\n        '
     'return _absolute(arg, where)\n    return ""', "guard",
     'worktree remove: the force flag does not skip the subject read'),
    ("worktree-remove: uncommitted and untracked work no longer denies",
     '    if lines and not dirty_paths_are_pushed_copies(target, lines):',
     '    if False and not dirty_paths_are_pushed_copies(target, lines):',
     "guard", 'worktree remove: uncommitted and untracked work denies'),
    ("worktree-remove: a locked tree no longer denies",
     '    locked = worktree_locked(where, target)\n    if locked is None:\n        return None\n'
     '    if locked:\n        return False',
     '    locked = worktree_locked(where, target)\n    if locked is None:\n        return None\n'
     '    if False:\n        return False', "guard",
     'worktree remove: a locked tree denies even though it is clean'),
    ("worktree-remove: a live session no longer denies",
     '    live = worktree_live_session(target)\n    if live is None:\n        return None\n'
     '    if live:\n        return False',
     '    live = worktree_live_session(target)\n    if live is None:\n        return None\n'
     '    if False:\n        return False', "guard",
     'worktree remove: a live session standing in a clean tree still denies'),
    ("worktree-remove: any session record counts as live, recycled pid included",
     '    diff = actual - started\n    if diff > SESSION_LIVE_TOLERANCE_MS:\n'
     '        return None\n    return diff >= -SESSION_LIVE_TOLERANCE_MS',
     '    return True', "guard", 'does not deny'),

    ("worktree-prune: reads only stdout, missing git's own stderr message",
     '    return not (answer.stdout.strip() or answer.stderr.strip())',
     '    return not answer.stdout.strip()', "guard",
     'worktree prune: a stale record asks, never denies'),
    ("worktree-prune: never asks, so a dropped record is silent",
     '        if subcommand == "worktree-prune":\n'
     '            ask_command("shared-tree", WORKTREE_PRUNE_ASK_REASON, matched, "worktree prune")',
     '        if False:\n'
     '            ask_command("shared-tree", WORKTREE_PRUNE_ASK_REASON, matched, "worktree prune")', "guard",
     'worktree prune: a stale record asks, never denies'),
    ("ask-alone: a chained ask command asks instead of denying",
     '    if count_commands(text) > 1:',
     '    if False:', "guard",
     'ask-alone: the incident, prune then worktree add then grep, denies and names the prune'),
    ("ask-alone: background_commands reads no quotes, so a & inside a quoted value splits",
     '            quote = char\n        elif char == "&"',
     '            quote = ""\n        elif char == "&"', "guard",
     'ask-alone: a single & inside a quoted cap value is one command, so it asks'),
    ("ask-alone: count_commands ignores the commands inside an inline bash -c script",
     '        if script:\n            commands += count_commands(script) - 1',
     '        if False:\n            commands += count_commands(script) - 1', "guard",
     'ask-alone: W after echo inside bash -c with double quotes denies'),
    ("worktree-prune: the call's own -n no longer reads as a pure read",
     '                if any(a in ("-n", "--dry-run") for a in args[1:]):\n'
     '                    continue  # the call\'s own dry run is a read, never a discard',
     '                if False:\n'
     '                    continue  # the call\'s own dry run is a read, never a discard', "guard",
     'worktree prune: -n itself is a read, not a discard, so it passes unconditionally'),
    ("env-file: read only the bare environment basename",
     '    return name.startswith(ENV_PREFIX) and name != ENV_ALLOWED',
     '    return name == ENV_PREFIX', "guard", 'env: a path token wherever the path puts it, cat .env.local'),
    ("shared-tree: drop the interpreter heredoc exception",
     '    if (SHELL_HEREDOC if shells_only and not per_body else INTERPRETER_HEREDOC)(text) or _runs_written_file(\n'
     '            text, headers):',
     '    if False:', "guard", 'heredoc: a body fed to a shell stays under inspection'),
    ("shared-tree: keep no heredoc body in the per-body reading",
     '        keep = [number for number, header in enumerate(headers)\n'
     '                if first(header) or _PIPED_SHELL(header) or _runs_written_file(text, [header], runner)\n'
     '                or not _feeds_data(header, shells_only)]',
     '        keep = []', "guard", 'frozen shell: a heredoc body fed to bash, naming a cat-write onto the config settings'),
    ("frozen-path: freeze nothing",
     '    if not path:\n        return False\n    try:\n        literal = _literal_resolved(path, cwd)\n'
     '        resolved = _resolved(path, cwd)',
     '    if path:\n        return False\n    try:\n        literal = _literal_resolved(path, cwd)\n'
     '        resolved = _resolved(path, cwd)', "guard", 'frozen: Write of the global CLAUDE.md'),
    ("frozen-path: never check the literal, un-resolved path (misses the installed symlink)",
     '    for target, root in ((literal, literal_root), (resolved, resolved_root)):',
     '    for target, root in ((resolved, resolved_root),):', "guard",
     'frozen: the live path stays frozen even though it is a real symlink into the clone '
     '[resolve-branch proof]'),
    ("frozen-path: drop docs/design from the frozen config dirs",
     '    os.path.normcase("docs/design"),\n', '', "guard",
     'frozen: Write of the config docs/design house rules'),
    ("frozen-path: match a frozen dir by its first part only (misses docs/design)",
     '        if any(rel.startswith(d + os.sep) for d in CONFIG_FROZEN_DIRS):',
     '        if len(parts) > 1 and parts[0] in CONFIG_FROZEN_DIRS:', "guard",
     'frozen: Write of the config docs/design house rules'),
    ("force-push: forget every forced push",
     '    if not (force or leased or plus or mirror or delete):\n        return ""',
     '    if True:\n        return ""', "guard", 'push: the long force flag'),
    ("force-push: the short force flag no longer forces",
     '                force = force or letter == "f"',
     '                force = False', "guard", 'push: the short force flag'),
    ("force-push: a --fo prefix no longer forces",
     '            elif len(name) >= 4 and "--force".startswith(name):\n                force = True',
     '            elif False:\n                force = True', "guard", 'push: a force prefix'),
    ("force-push: a plus refspec no longer forces",
     '    plus = any(spec.startswith("+") for spec in plain)',
     '    plus = False', "guard", 'push: a plus refspec'),
    ("force-push: a bare lease passes without includes",
     '    return "" if includes or not unpinned else "deny"',
     '    return ""', "guard", 'push: a bare lease without includes'),
    ("force-push: a lease never passes",
     '    return "" if includes or not unpinned else "deny"',
     '    return "deny"', "guard", 'push: lease with includes, bare'),
    ("force-push: a pinned lease needs includes",
     '    return "" if includes or not unpinned else "deny"',
     '    return "" if includes else "deny"', "guard", 'push: lease naming ref and sha is stale-safe alone'),
    ("force-push: a lease naming a ref counts as pinned",
     'unpinned = unpinned or not value.partition(":")[2]',
     'unpinned = unpinned or not value', "guard", 'push: a lease naming a ref, without includes'),
    ("force-push: the default branch no longer asks",
     '    if reaches:\n        return "ask"',
     '    if False:\n        return "ask"', "guard", 'forced to the default branch asks: HEAD:main'),
    ("force-push: unreadable git no longer asks",
     '    reaches = mirror or every or defaults is None',
     '    reaches = mirror or every', "guard", 'push: forced where git cannot be read asks'),
    ("force-push: mirror and all no longer ask",
     '    reaches = mirror or every or defaults is None',
     '    reaches = defaults is None', "guard", 'forced to the default branch asks: --mirror'),
    ("force-push: a non-repository reads as a repository",
     '    if repo is None or repo.returncode != 0:\n        return None',
     '    if False:\n        return None', "guard", 'push: forced with a plus where git cannot be read asks'),
    ("force-push: origin/HEAD is ignored for the fallback names",
     '        return named',
     '        return DEFAULT_BRANCH_FALLBACK', "guard", 'named by origin/HEAD, not by name'),
    ("force-push: the fallback forgets master",
     '    return DEFAULT_BRANCH_FALLBACK + named\n\n\n# A quoted',
     '    return ("main",) + named\n\n\n# A quoted', "guard", 'forced to master when no origin/HEAD'),
    ("force-push: HEAD as a destination is not resolved",
     '    if target in ("HEAD", "@"):',
     '    if target in ("@",):', "guard", 'lease with includes, HEAD, on main'),
    ("force-push: refs/heads/ is not stripped",
     'target.removeprefix("refs/heads/") in (defaults or ())',
     'target in (defaults or ())', "guard", 'forced to the default branch asks: a full ref'),
    ("force-push: a glob destination no longer asks",
     'if target is None or "*" in target:',
     'if target is None:', "guard", 'forced to the default branch asks: a glob refspec'),
    ("force-push: a push option value is read as the remote",
     '        elif arg in PUSH_VALUE_OPTS:\n            skip = True',
     '        elif False:\n            skip = True', "guard", 'push option value'),
    ("force-push: a quoted refspec is read with its quotes",
     """        arg = arg.replace('"', "").replace("'", "")""", "        arg = arg", "guard",
     'a quoted refspec'),
    ("force-push: --repo is not read as the remote",
     '                remote, repo_next = value, not value',
     '                remote, repo_next = "", False', "guard", 'with --repo'),
    ("force-push: a colon-first refspec is not a delete",
     '    return delete or any(spec.startswith(":") for spec in plain)',
     '    return delete', "guard", 'a delete refspec'),
    ("force-push: --delete is not a delete",
     '            elif name == "--delete":\n                delete = True',
     '            elif name == "--delete":\n                delete = False', "guard", 'with --delete'),
    ("force-push: -d is not a delete",
     '                delete = delete or letter == "d"', '                delete = delete', "guard",
     'with -d'),
    ("force-push: --no-force-if-includes does not cancel",
     '            elif name == "--no-force-if-includes":\n                includes = False',
     '            elif name == "--no-force-if-includes":\n                includes = True', "guard",
     'no-force-if-includes cancels'),
    ("force-push: a glued push option swallows the next argument",
     '                    skip = index == len(arg) - 2', '                    skip = arg.endswith("o")', "guard",
     'a glued push option then force'),
    ("force-push: git -C is not the target",
     '    where = _absolute(git_c, run_dir) if git_c is not None else run_dir',
     '    where = run_dir', "guard", 'with git -C'),
    ("force-push: a leading cd is not the target",
     '            run_dir = _absolute(cd, run_dir)', '            run_dir = run_dir', "guard", 'after cd'),
    ("force-push: a -c override is not read",
     '            overrides[key.lower()] = value', '            pass', "guard", 'with -c push.default'),
    ("force-push: -ofoo is read as -f",
     '                if letter == "o":', '                if False:', "guard", 'glued push option'),
    ("force-push: push.default upstream is read as current",
     '    if mode in ("upstream", "tracking"):', '    if False:', "guard", 'push.default upstream'),
    ("force-push: an exotic push.default is read as current",
     '        return merge.removeprefix("refs/heads/") if merge else None\n    return None',
     '        return merge.removeprefix("refs/heads/") if merge else None\n    return current', "guard",
     'push.default matching'),
    # The review-record rule: each mutant removes one link of the chain, and one named case must go red.
    ("push-needs-review-record: the guard.py call is dropped",
     'review_log_hit(transcript, lambda: push_destinations(args, where, overrides), where,\n'
     '                                                         lambda: push_sources(args, where, overrides))',
     '(False, "")', "guard", 'the incident: a reviewer FAIL in the foreground result'),
    ("push-needs-review-record: a posted record never clears its report",
     'pending = [report for report in pending if report not in held]',
     'pending = list(pending)', "guard", 'a FAIL round 1, then a FAIL record posted'),
    ("push-needs-review-record: a round report is cleared by any posted fix check line",
     '            if head is None:\n                return False',
     '            if head is None:\n                return bool(self.fix)', "guard",
     'a FAIL round 1 unrecorded beside a Fix check record line'),
    ("push-needs-review-record: a fix check PASS no longer denies its head branch",
     'if heads[number] in destinations() and',
     'if False and', "guard", 'a fix check PASS for PR 1464 posted, then a push to its head branch'),
    # The clean-merge allow (`_only_clean_merges`, then the walk in merge/merge.py), one link per row.
    ("push-needs-review-record: the clean-merge verdict is always true, so an evil merge is allowed",
     '        return branch in sources and bool(bases) and merge.clean_merges_pushed(where, sources[branch], head, bases)',
     '        return True', "guard", 'an evil merge of main with an edit beyond git'),
    ("push-needs-review-record: a clean-merge read that raises is allowed, not refused",
     '        return branch in sources and bool(bases) and merge.clean_merges_pushed(where, sources[branch], head, bases)\n'
     '    except Exception:\n        return False',
     '        return branch in sources and bool(bases) and merge.clean_merges_pushed(where, sources[branch], head, bases)\n'
     '    except Exception:\n        return True', "guard", 'a refspec source with a NUL byte'),
    # The default base is origin/HEAD's target when it is set (`_push_main_refs`): a base of origin/main alone refuses a trunk merge.
    ("push-needs-review-record: the default base is origin/main even when origin/HEAD names trunk",
     '    return ["refs/remotes/" + (head or remote + "/main")]',
     '    return ["refs/remotes/" + remote + "/main"]', "guard", 'a clean merge of trunk is allowed'),
    ("push-needs-review-record: a merge whose second parent is off main is read as clean",
     'if len(parents) != 2 or not tree or not any(ancestor(root, parents[1], base) is True for base in bases):',
     'if len(parents) != 2 or not tree:', "merge",
     'a clean merge whose second parent is a side branch off the root'),
    ("push-needs-review-record: a merge that differs from git's clean merge is read as clean",
     'if state != "clean" or merged != tree:', 'if state != "clean":', "merge",
     'an evil merge of main with an edit beyond git'),
    ("push-needs-review-record: the walk does not stop at the record's Head",
     '        if sha == head:\n            return True\n        c, text = git(root, "cat-file", "commit", sha)',
     '        c, text = git(root, "cat-file", "commit", sha)', "merge",
     'one clean merge of main onto the record'),
    ("push-needs-review-record: a verdict on the Done label line is not read",
     '                if loose and marker:\n                    return loose.group(), "round" if marker.group(1) else "fix", int(marker.group(1)) if marker.group(1) else None',
     '                if loose and marker:\n                    return None', "guard",
     'a reviewer FAIL round 1 on the Done label line, no record, then the push'),
    ("push-needs-review-record: a held report is never counted",
     '    return counted',
     '    return []', "guard",
     'a FAIL naming diff base A then head B'),
    ("push-needs-review-record: a commit on main counts for a held report",
     '    if on_main is not False:',
     '    if False:', "guard",
     'a FAIL naming only diff base A'),
    ("push-needs-review-record: a report no PR counts is dropped, not kept for the next PR",
     'early = [report for report in early if report[:-1] not in counted]   # held for a later PR',
     'early = []', "guard",
     'a FAIL naming head B, then a PR for another branch'),
    ("push-needs-review-record: the Done label round marker ignores case",
     '", re.I)\n_LABEL_WORD',
     '")\n_LABEL_WORD', "guard",
     'a Done label line reading Round 1 with a capital R'),
    ("push-needs-review-record: the Done label verdict is the first all-caps word",
     ' if word.group() in verdicts',
     '', "guard",
     'a Done label line whose first all-capitals word is HEAD'),
    ("push-needs-review-record: a Base head line names the reviewed head",
     'if not _BASE_BEFORE.search(', 'if True or not _BASE_BEFORE.search(', "guard",
     'reads Base main head B, reviewed A, with its record at B only'),
    # A transcript line that is valid JSON but not an object: the reader steps over it before any record read.
    ("push-needs-review-record: a transcript line that is valid JSON but not an object is read as a record",
     '            if not isinstance(record, dict):\n                continue\n            content = record["message"]',
     '            if False:\n                continue\n            content = record["message"]', "guard",
     'a transcript line that is a JSON list, then the push'),
    ("force-push: quoted text is read as a push",
     'return PUSH_QUOTED.sub(" ", segment)', 'return segment', "guard",
     'false alarm: --force quoted in a commit message'),
    ("force-push: a deny names the wrong reason",
     'refuse(tool, verdict, "force-push", PUSH_REASON, "git push " + " ".join(args))',
     'refuse(tool, verdict, "force-push", PUSH_ASK_REASON, "git push " + " ".join(args))',
     "guard", 'the long force flag'),
    # push-main and push-stray-branch (owner rulings 207 a and 206 a).
    ("push-main: a colon-less main is not a destination",
     '            elif source.removeprefix("refs/heads/") in DEFAULT_BRANCH_FALLBACK:\n                # A local origin makes main() empty; the other refspecs are still read for agent and stray.\n                if main():\n                    to_main = True',
     '            elif False:\n                if main():\n                    to_main = True', "guard", 'a push of main from a feature branch asks'),
    ("push-main: a refspec target of main is not a destination",
     '                if target.removeprefix("refs/heads/") in DEFAULT_BRANCH_FALLBACK and main():\n                    to_main = True',
     '                if False:\n                    to_main = True', "guard", 'HEAD:main from a feature branch asks'),
    ("push-main: a main refspec ends the read on a local origin",
     '                if main():\n                    to_main = True\n            elif source in ("HEAD", "@")',
     '                return main()\n            elif source in ("HEAD", "@")', "guard", 'local origin, main then HEAD on a branch tracking another name asks stray'),
    ("push-main: a main refspec before an agent name asks push-main",
     'if not agent and (to_main or',
     'if (to_main or', "guard", 'network origin, main then the agent name asks the agent rule'),
    ("push-all-main: --all no longer refuses",
     '    if every:\n',
     '    if False:\n', "guard", '--all from a lane checkout, local main ahead of origin/main, refuses'),
    ("push-agent-branch: --all from an agent checkout is not the agent rule's",
     '        if current() and AGENT_BRANCH.fullmatch(current()):\n            return "agent"',
     '        if False:\n            return "agent"', "guard", 'agent checkout, --all with main asks the agent rule'),
    ("push-all-main: an --all that may update main is silent",
     '        if updates_default([("refs/heads/" + name, name) for name in DEFAULT_BRANCH_FALLBACK]):\n            return "all"',
     '        if updates_default([("refs/heads/" + name, name) for name in DEFAULT_BRANCH_FALLBACK]):\n            return ""', "guard", '--all from a main checkout, local main ahead of origin/main, refuses'),
    ("push-all-main: a glob to a local-path origin is refused",
     '(unreadable or reach or globs) and main()',
     '(unreadable or reach or globs) and True', "guard",
     'glob refspec refs/heads/*:refs/heads/* to a local-path origin with local main ahead'),
    # Against the fixed text: git's `*` matches an empty name, so the reach test takes `>=`. The anchor is the whole
    # comparison, since a bare `>=` occurs on other lines. Its killer is the lane row that names main with `main*`.
    ("push-all-main: a glob whose star matches an empty name is not read as reaching main",
     'len(full) >= len(target_pre) + len(target_suf)',
     'len(full) > len(target_pre) + len(target_suf)', "guard",
     'glob refspec refs/heads/main*:refs/heads/main* from a lane checkout'),
    # Against the fixed text: a colon-less glob keeps its empty target and reads as unreadable. The tag row kills it.
    # The anchor starts at the partition line: the bare `target = target if colon else source` also sits in _push_dest.
    ("push-all-main: a colon-less glob refspec is read as unreadable",
     'spec.partition(":")\n    target = target if colon else source',
     'spec.partition(":")\n    target = target', "guard",
     'glob refspec refs/tags/v* (colon-less) from a lane checkout, local main ahead, is silent'),
    ("push-all-main: a matching tracking ref is refused",
     'shas.get("refs/remotes/" + remote + "/" + name) != shas[source]',
     'shas.get("refs/remotes/" + remote + "/" + name) == shas[source]', "guard",
     '--all from a main checkout, local main equal to origin/main, is silent'),
    ("push-all-main: an absent local main or master is an update",
     'if source in shas and shas.get("refs/remotes/" + remote + "/" + name) != shas[source]:',
     'if shas.get("refs/remotes/" + remote + "/" + name) != shas.get(source, ""):', "guard",
     '--all with no local main or master, from a lane checkout, is silent'),
    ("push-all-main: a failed ref read is silent",
     '    if answer is None or answer.returncode != 0:\n        return True',
     '    if answer is None or answer.returncode != 0:\n        return False', "guard",
     '--all with a failed read of the tracking refs, and a local agent-named branch, refuses for the update'),
    ("push-all-main: a second remote's tracking refs are read under origin",
     '_push_updates_default(cwd, state["remote"].get("name", ""), reach)',
     '_push_updates_default(cwd, "origin", reach)', "guard",
     '--all to a second remote whose main ref equals local main, is silent'),
    ("push-all-main: the remote's name is not kept for its tracking refs",
     'resolved["name"] = remote',
     'resolved["name"] = "origin"', "guard",
     '--all with no remote named, a branch tracking a second remote, is silent'),
    ("push-all-main: a push-all-main verdict is not refused",
     'elif kind == "all":',
     'elif kind == "all" and False:', "guard",
     '--all from a main checkout, local main ahead of origin/main, refuses'),
    ("push-all-main: the all-branches refusal prints the agent reason",
     'refuse(tool, "deny", "push-all-main", PUSH_ALL_REASON,',
     'refuse(tool, "deny", "push-all-main", PUSH_AGENT_REASON,', "guard",
     '--all from a main checkout, local main ahead of origin/main, refuses'),
    ("push-main: a bare push that writes main no longer asks",
     '        if dest in DEFAULT_BRANCH_FALLBACK:\n            return main()',
     '        if False:\n            return main()', "guard", 'main tracking origin/main, a bare push asks'),
    ("push-main: HEAD on main no longer asks",
     '(to_main or (implied and current() in DEFAULT_BRANCH_FALLBACK and main())):',
     '(to_main or False):', "guard", 'main tracking origin/main, HEAD asks'),
    ("push-main: push.default upstream is not read for a bare push",
     '            dest = merge or None',
     '            dest = None', "guard", 'a branch tracking main asks'),
    ("push-main: a bare push under simple ignores git's own refusal",
     '            dest = cur if merge == cur or (not merge and auto.lower() in ("true", "yes", "on", "1")) else None',
     '            dest = cur', "guard", 'a bare push on main with no upstream is git'),
    ("push-main: a remote with no URL no longer stays silent",
     '    if not url:\n        return False\n    if _is_local_path(url):',
     '    if not url:\n        return True\n    if _is_local_path(url):', "guard",
     'main, no remote in the repo is silent'),
    ("push-main: a local path or file URL no longer stays silent",
     '    if _is_local_path(url):\n        return False',
     '    if False:\n        return False', "guard", 'main, a file URL named as the remote is silent'),
    ("push-main: a remote the shell has not expanded reads as no remote, so it no longer asks",
     '    if _PUSH_SHELL_EXPANSION.search(remote):\n        return True',
     '    if False:\n        return True', "guard",
     'main, a double-quoted shell variable as the remote asks push-main'),
    ("push-main: an scp-like remote no longer asks",
     'return bool(_PUSH_URL_SCHEME.match(url) or _PUSH_URL_SCP.match(url))',
     'return bool(_PUSH_URL_SCHEME.match(url))', "guard", 'main, an scp-form origin asks'),
    ("push-stray-branch: a stray destination no longer asks",
     '    return "" if seen is not None and seen.returncode == 0 else "stray"',
     '    return ""', "guard", 'stray branch, HEAD asks'),
    ("push-stray-branch: an existing destination ref no longer stays silent",
     '    return "" if seen is not None and seen.returncode == 0 else "stray"',
     '    return "stray"', "guard", 'own ref on origin, HEAD is silent'),
    ("push-stray-branch: @ is not an implied destination",
     '            elif source in ("HEAD", "@") or',
     '            elif source in ("HEAD",) or', "guard", 'stray branch, @ asks'),
    ("push-stray-branch: a colon-less current branch is not implied",
     ' or (current() is not None and source == current()):',
     ' or False:', "guard", 'colon-less refspec asks'),
    ("push-stray-branch: a bare push under current is not implied",
     '            dest = cur\n            implied = True',
     '            dest = cur', "guard", 'a bare push under push.default current asks'),
    ("push-stray-branch: an upstream of main no longer stays silent",
     'or pushed != remote_cfg or merge in DEFAULT_BRANCH_FALLBACK:',
     'or pushed != remote_cfg:', "guard", 'lane from main, HEAD is silent'),
    ("push-stray-branch: another remote than the upstream's is judged",
     'or not remote_cfg or pushed != remote_cfg or merge in DEFAULT_BRANCH_FALLBACK:',
     'or not remote_cfg or merge in DEFAULT_BRANCH_FALLBACK:', "guard", "another remote than the upstream's"),
    ("push-all-main: --branches is not read as --all",
     '            elif name in ("--all", "--branches"):',
     '            elif name == "--all":', "guard",
     '--branches from a lane checkout, no origin/main tracking ref, refuses'),
    ("push-stray-branch: a -u push of the local name still asks",
     'if merge == current() or upstream:',
     'if merge == current():', "guard", 'stacked lane, -u HEAD is silent'),
    ("push-agent-branch: the agent name shape no longer matches",
     'AGENT_BRANCH = re.compile(r"(?:claude/|worktree-)?agent-[0-9a-f]{8,}")',
     'AGENT_BRANCH = re.compile(r"(?!)")', "guard", 'agent branch, HEAD asks'),
    ("push-agent-branch: the worktree- prefix is not a name",
     'AGENT_BRANCH = re.compile(r"(?:claude/|worktree-)?agent-[0-9a-f]{8,}")',
     'AGENT_BRANCH = re.compile(r"(?:claude/)?agent-[0-9a-f]{8,}")', "guard",
     'agent worktree, worktree-agent-<hex>, -u HEAD asks'),
    ("push-agent-branch: a short hex tail is a name",
     'AGENT_BRANCH = re.compile(r"(?:claude/|worktree-)?agent-[0-9a-f]{8,}")',
     'AGENT_BRANCH = re.compile(r"(?:claude/|worktree-)?agent-[0-9a-f]*")', "guard",
     'agent-1234567, -u HEAD is silent'),
    ("push-agent-branch: a config autoSetupRemote is not read",
     '(default|autosetupremote)$)"',
     '(default)$)"', "guard",
     'agent branch, a bare push under a config autoSetupRemote asks'),
    ("push-agent-branch: an exact 8-hex name no longer matches",
     'AGENT_BRANCH = re.compile(r"(?:claude/|worktree-)?agent-[0-9a-f]{8,}")',
     'AGENT_BRANCH = re.compile(r"(?:claude/|worktree-)?agent-[0-9a-f]{9,}")', "guard",
     'agent-12345678, -u HEAD asks'),
    ("push-agent-branch: an explicit destination is not read",
     '                agent = agent or bool(AGENT_BRANCH.fullmatch(target.removeprefix("refs/heads/")))',
     '                pass', "guard", 'explicit agent destination from a branch with no upstream asks'),
    ("push-agent-branch: an implied destination is not the current branch",
     '                agent = agent or bool(current() and AGENT_BRANCH.fullmatch(current()))',
     '                pass', "guard", 'agent branch, HEAD asks'),
    ("push-agent-branch: a bare push under current is not judged",
     '        agent = bool(dest and AGENT_BRANCH.fullmatch(dest))',
     '        agent = False', "guard", 'a bare push under push.default current asks'),
    ("push-agent-branch: autoSetupRemote is not read as the current name",
     '            dest = cur if merge == cur or (not merge and auto.lower() in ("true", "yes", "on", "1")) else None',
     '            dest = cur if merge == cur else None', "guard",
     'agent branch, a bare push under autoSetupRemote asks'),
    ("push-agent-branch: the refusal is not wired",
     '                elif kind == "agent":',
     '                elif kind == "agent-off":', "guard", 'agent branch, HEAD asks'),
    # The all-agent kind (rule push-all-main, decision plain-push-asks): a --all, --branches or glob push that sends a
    # local branch named like an agent worktree while the tracking refs show no update. Its code is split across
    # guard_push_delete.py (_local_agent_branches, _glob_sends, push_ask_hit, PUSH_ALL_AGENT_REASON) and guard.py (the
    # deny). Each anchor is found once across the guard family, so an entry names its file by its text alone.
    ("push-all-main: a local branch read as agent-named whatever its name",
     'if AGENT_BRANCH.fullmatch(ref.removeprefix("refs/heads/"))]', 'if True]', "guard",
     "with no local main or master, from a lane checkout"),
    ("push-all-main: a local branch is matched without its refs/heads/ prefix, so no agent name matches",
     'if AGENT_BRANCH.fullmatch(ref.removeprefix("refs/heads/"))]', 'if AGENT_BRANCH.fullmatch(ref)]', "guard",
     "--all with a local agent-named branch, main matching its tracking ref, refuses"),
    ("push-all-main: a failed listing of the local branches reads as no agent-named branch",
     '        return None\n    return [ref for ref in answer.stdout.split()',
     '        return []\n    return [ref for ref in answer.stdout.split()', "guard",
     "--all with a failed read of the local branches"),
    ("push-all-main: a glob's short source name is not read under refs/heads/",
     'pre, _, suf = _qualified(spec.partition(":")[0]).partition("*")',
     'pre, _, suf = spec.partition(":")[0].partition("*")', "guard",
     "glob refspec agent-*:agent-* with a local agent-named branch refuses"),
    ("push-all-main: a glob's source prefix is not checked, so any branch with its suffix matches",
     'ref.startswith(pre) and ref.endswith(suf) and len(ref)', 'ref.endswith(suf) and len(ref)', "guard",
     "glob refspec refs/heads/main* with a local agent-named branch"),
    ("push-all-main: a glob's source suffix is not checked, so any branch with its prefix matches",
     'ref.startswith(pre) and ref.endswith(suf) and len(ref)', 'ref.startswith(pre) and len(ref)', "guard",
     "glob refspec refs/heads/agent-*x with a local agent-named branch"),
    ("push-all-main: a glob whose prefix and suffix overlap matches a name shorter than both",
     'ref.endswith(suf) and len(ref) >= len(pre) + len(suf)]', 'ref.endswith(suf)]', "guard",
     "glob refspec whose prefix and suffix overlap"),
    ("push-all-main: --all never reads the local branches, so an agent-named branch is silent",
     '        sent = _local_agent_branches(cwd)\n        return "all" if sent is None else "all-agent" if sent else ""',
     '        sent = []\n        return "all" if sent is None else "all-agent" if sent else ""', "guard",
     "--all with a local agent-named branch, main matching its tracking ref, refuses"),
    ("push-all-main: --all with an agent-named branch names the update's reason",
     'return "all" if sent is None else "all-agent" if sent else ""',
     'return "all" if sent is None else "all" if sent else ""', "guard",
     "--all with a local agent-named branch, main matching its tracking ref, refuses"),
    ("push-all-main: --all with a failed read of the local branches is silent",
     '"all" if sent is None else "all-agent"', '"" if sent is None else "all-agent"', "guard",
     "--all with a failed read of the local branches"),
    ("push-all-main: --all with main ahead names an agent-named branch before the update",
     '        if updates_default([("refs/heads/" + name, name) for name in DEFAULT_BRANCH_FALLBACK]):\n            return "all"',
     '        if updates_default([("refs/heads/" + name, name) for name in DEFAULT_BRANCH_FALLBACK]) '
     'and not _local_agent_branches(cwd):\n            return "all"', "guard",
     "--all with main ahead of its tracking ref and a local agent-named branch refuses for the update"),
    ("push-all-main: a glob with a failed read of the local branches is silent",
     '                if local is None:\n                    return "all"',
     '                if local is None:\n                    return ""', "guard",
     "glob refspec refs/heads/*:refs/heads/* with a failed read of the local branches refuses"),
    ("push-all-main: a glob is refused for any agent-named branch, whatever its source side matches",
     'if any(_glob_sends(spec, local) for spec in globs):', 'if local:', "guard",
     "glob refspec refs/heads/main* with a local agent-named branch"),
    ("push-all-main: a glob is not judged by the agent-named branches it sends",
     '            if globs:\n                local = _local_agent_branches(cwd)',
     '            if False:\n                local = _local_agent_branches(cwd)', "guard",
     "glob refspec refs/heads/*:refs/heads/* with a local agent-named branch"),
    ("push-all-main: a glob that reaches no main is not read for an agent-named branch",
     'if not agent and (unreadable or reach or globs) and main():',
     'if not agent and (unreadable or reach) and main():', "guard",
     "glob refspec refs/heads/agent-*:refs/heads/agent-* with a local"),
    ("push-all-main: a glob with main ahead names an agent-named branch before the update",
     '            if unreadable or updates_default(reach):',
     '            if unreadable or (updates_default(reach) and not _local_agent_branches(cwd)):', "guard",
     "glob refspec refs/heads/*:refs/heads/* with main ahead of its tracking ref"),
    ("push-all-main: the all-agent reason does not name an agent worktree",
     'a local branch named like an agent worktree "', 'a local branch named like a worktree "', "guard",
     "--all with a local agent-named branch, main matching its tracking ref, refuses"),
    ("push-all-main: the all-agent reason does not say that every branch is sent",
     'this push sends every branch it matches, and a local', 'this push sends a branch it matches, and a local', "guard",
     "--all with a local agent-named branch, main matching its tracking ref, refuses"),
    ("push-all-main: the all-agent reason's remedy is not a push of the lane's own branch",
     "plain-push-asks). Remedy: push the lane's own branch by name: `git push origin HEAD:<lane-branch>`.",
     "plain-push-asks). Remedy: push the lane's own branch by name: `git push origin <lane-branch>`.", "guard",
     "--all with a local agent-named branch, main matching its tracking ref, refuses"),
    ("push-all-main: the all-agent reason claims that the default branch may update",
     'is among them (rule push-all-main, decision ',
     'is among them, and it may update the default branch (rule push-all-main, decision ', "guard",
     "--all with a local agent-named branch, main matching its tracking ref, refuses"),
    ("push-all-main: an all-agent verdict is not refused",
     '                elif kind == "all-agent":', '                elif kind == "all-agent" and False:', "guard",
     "--all with a local agent-named branch, main matching its tracking ref, refuses"),
    ("push-all-main: an all-agent refusal prints the update's reason",
     'refuse(tool, "deny", "push-all-main", PUSH_ALL_AGENT_REASON, "git push " + " ".join(args))',
     'refuse(tool, "deny", "push-all-main", PUSH_ALL_REASON, "git push " + " ".join(args))', "guard",
     "--all with a local agent-named branch, main matching its tracking ref, refuses"),
    ("push-all-main: an all-agent refusal is filed under the agent rule",
     'refuse(tool, "deny", "push-all-main", PUSH_ALL_AGENT_REASON, "git push " + " ".join(args))',
     'refuse(tool, "deny", "push-agent-branch", PUSH_ALL_AGENT_REASON, "git push " + " ".join(args))', "guard",
     "--all with a local agent-named branch, main matching its tracking ref, refuses"),
    ("push-all-main: an all-agent refusal asks instead of denying",
     'refuse(tool, "deny", "push-all-main", PUSH_ALL_AGENT_REASON, "git push " + " ".join(args))',
     'refuse(tool, "ask", "push-all-main", PUSH_ALL_AGENT_REASON, "git push " + " ".join(args))', "guard",
     "--all with a local agent-named branch, main matching its tracking ref, refuses"),
    ("env-file: a search command's pattern is read as a path",
     '                if index in patterns:\n                    continue\n',
     '                if False:\n                    continue\n', "guard",
     'trim: env: grep with a dot-star pattern'),
    ("machine-wide-kill: pkill and killall no longer deny in command position",
     '    if tool in KILL_COMMAND_WORDS:\n        return word',
     '    if False:\n        return word', "guard", 'kill: pkill by pattern denies'),
    ("machine-wide-kill: taskkill's image flag no longer denies",
     '    if tool == "taskkill" and any(flag.lower() in TASKKILL_IMAGE_FLAGS for flag in rest):\n'
     '        return word',
     '    if False:\n        return word', "guard", 'kill: taskkill by image name'),
    ("machine-wide-kill: Stop-Process's name flag no longer denies",
     '    if tool == "stop-process" and any('
     'flag.lower() in STOP_PROCESS_NAME_FLAGS for flag in rest):\n        return word',
     '    if False:\n        return word', "guard", 'kill: Stop-Process by name'),
    ("machine-wide-kill: lsof -t no longer feeds a kill list",
     '    return any(arg.startswith("-") and not arg.startswith("--") and "t" in arg\n'
     '               for arg in tokens[index + 1:])',
     '    return False', "guard",
     'kill: lsof -ti piped into xargs kill is the pid list of a kill'),
    ("machine-wide-kill: pkill -P no longer passes, so a kill of the shell's own children denies",
     '    if tool == "pkill" and parent_filter_pids(rest) is not None:\n        return ""',
     '    if False:\n        return ""', "guard", "kill: pkill -P of the shell's own pid passes"),
    ("machine-wide-kill: pkill -P of a foreign parent is no longer judged",
     '        for value in parent_filter_pids(tokens[index + 1:]) or ():',
     '        for value in ():', "guard",
     "kill: pkill -P of a parent this session did not start is refused", "posix"),
    ("machine-wide-kill: a kill of a pid this session did not start no longer denies",
     '        if pid_is_owned(abs(number) if number < -1 else number, root) is False:',
     '        if False:', "guard", 'kill: a pid this session did not start',
     "posix"),
    ("machine-wide-kill: the session tag matches as a substring, so a longer id owns the pid",
     '        return entries is not None and any(entry == want for entry in entries)',
     '        return entries is not None and any(want in entry for entry in entries)',
     "guard", 'kill: a PPID-1 pid whose session id entry has a suffix', "posix"),
    ("machine-wide-kill: a tagged job under an orphan stub shell reads foreign (only PPID 1 owns)",
     '    return parent == 1 or (bool(parent) and _ps_ppid(parent) == 1)',
     '    return parent == 1',
     "guard", 'kill: a job under an untagged PPID-1 stub, holding this session\'s id, from the main session',
     "posix"),
    ("machine-wide-kill: any pid under init owns the job, with no tag read",
     '            if _under_init(abs(number)) and holds_session_tag(abs(number), session_id):',
     '            if _under_init(abs(number)):',
     "guard", 'kill: a job under an untagged PPID-1 stub, holding another session\'s id, stays refused',
     "posix"),
    ("machine-wide-kill: an agent call owns a pid by the shared session tag",
     'foreign_pid_kill(tokens, transcript, "" if agent else session_id)',
     'foreign_pid_kill(tokens, transcript, session_id)',
     "guard", 'called by an agent (agent_id only)', "posix"),
    ("machine-wide-kill: pids 0, 1, -1 wait for the session root, so they pass when it is unknown",
     '        if number in (0, 1, -1):', '        if False:', "guard",
     'kill: init with the root unknown'),
    ("machine-wide-kill: a kill fed by pgrep or pidof in a substitution no longer denies",
     '    return "kill " + found.group(1) if found else ""', '    return ""', "guard",
     'kill: a pid list made by pgrep'),
    ("machine-wide-kill: pgrep piped into xargs kill no longer denies",
     '    if before is not None and basename(previous[before]) in PID_LISTERS:',
     '    if False:', "guard", 'kill: pgrep piped into xargs kill'),
    ("command word: a wrapper such as xargs no longer unwraps to what it runs",
     '    while index < end and basename(tokens[index]) in COMMAND_WRAPPERS:',
     '    while False:', "guard", 'kill: xargs unwraps to the real command it runs'),
    ("verdict-pipe: the clause is never called, so the whole rule is gone",
     '    matched = verdict_pipe_hit(stripped)\n    if matched:\n'
     '        refuse(tool, "deny", "verdict-pipe", VERDICT_PIPE_REASON, matched)',
     '    matched = ""\n    if matched:\n'
     '        refuse(tool, "deny", "verdict-pipe", VERDICT_PIPE_REASON, matched)',
     "guard", "verdict-pipe: a bare verdict piped to tail"),
    ("verdict-pipe: any segment end counts, not only a pipe",
     '        if ends[index] != "|":\n            continue\n        tokens = segment_tokens(segment)\n        if not tokens:\n            continue\n        at = resolve_command(tokens)\n        if at is None and _is_lookup',
     '        if not ends[index]:\n            continue\n        tokens = segment_tokens(segment)\n        if not tokens:\n            continue\n        at = resolve_command(tokens)\n        if at is None and _is_lookup',
     "guard", "verdict-pipe: verdict then a second command, &&"),
    ("verdict-pipe: a pipe at a line end is not a pipe when nothing follows on its line",
     '        if ends[index] != "|":\n            continue\n        tokens = segment_tokens(segment)\n        if not tokens:\n            continue\n        at = resolve_command(tokens)\n        if at is None and _is_lookup',
     '        if ends[index] != "|" or not segments[index + 1].strip():\n            continue\n        tokens = segment_tokens(segment)\n        if not tokens:\n            continue\n        at = resolve_command(tokens)\n        if at is None and _is_lookup',
     "guard", "verdict-pipe: a pipe at a line end, then tail"),
    ("verdict-pipe: a command substitution is no longer read as its own text",
     '    return next((hit for text, _in_message in texts if (hit := _verdict_pipe_in(text))), "")',
     '    return _verdict_pipe_in(stripped)',
     "guard", "verdict-pipe: a pipe in a double-quoted substitution, to tail"),
    ("verdict-pipe: a shell script handed to bash -c or sh -c is no longer read",
     '        hit = tokens and next((h for inner in inner_commands(tokens)',
     '        hit = tokens and next((h for inner in ()',
     "guard", "verdict-pipe: a pipe in bash -c, to tail"),
    ("verdict-pipe: command -v names a lookup, but it is read as a run of verdict",
     '        if at is None and _is_lookup(tokens):\n            continue\n',
     '',
     "guard", "verdict-pipe: command -v names verdict, piped to head"),
    ("verdict-pipe: a verdict word anywhere in the segment counts, not only ahead of the command",
     '        reach = tokens if at is None else tokens[:_skip_uv_run(tokens, at) + 1]',
     '        reach = tokens',
     "guard", "verdict-pipe: grep names verdict, pipe out of grep"),
    ("verdict-pipe: a verdict run through a wrapper such as timeout or python is no longer read",
     '        reach = tokens if at is None else tokens[:_skip_uv_run(tokens, at) + 1]',
     '        reach = tokens[at:] if at is not None else tokens',
     "guard", "verdict-pipe: a timeout ahead of verdict, piped to tail"),
    ("detached-launch: the clause is never called, so the whole rule is gone",
     '    matched = detached_launch_hit(stripped)\n    if matched:\n'
     '        refuse(tool, "deny", "detached-launch", DETACHED_LAUNCH_REASON, matched)',
     '    matched = ""\n    if matched:\n'
     '        refuse(tool, "deny", "detached-launch", DETACHED_LAUNCH_REASON, matched)',
     "guard", "detached: the incident's exact command orphans to pid 1"),
    ("detached-launch: a subshell background job no longer denies",
     '    if last == ")":\n        return tokens[-2] == "&"\n'
     '    return last.endswith(")") and last[:-1].endswith("&")',
     '    return False', "guard", "detached: the incident's exact command orphans to pid 1"),
    ("detached-launch: setsid no longer denies as a bare wrapper",
     '    if basename(word) != "setsid":\n        return ""',
     '    return ""', "guard", "detached: setsid with no -w starts its own session"),
    ("detached-launch: setsid -w no longer passes as a foreground wait",
     '        if arg == "--wait" or (not arg.startswith("--") and "w" in arg):\n            return ""',
     '        if False:\n            return ""', "guard",
     "detached: setsid -w waits for its child, so it runs in the foreground"),
    ("detached-launch: disown right after a background job no longer denies",
     '        if j < len(rest) and basename(rest[j]) == "disown":\n            return "& disown"',
     '        if False:\n            return "& disown"', "guard",
     "detached: disown right after a job whose pid is captured"),
    ("detached-launch: a bare trailing background job no longer denies",
     '            if tokens[i] == "&":\n                return tokens[i - 1] + " &"',
     '            if False:\n                return tokens[i - 1] + " &"', "guard",
     "detached: a bare trailing background job with no pid captured, "
     "MEASURED zero harmless matches in 16571 local Bash commands"),
    ("detached-launch: a background job before another line no longer denies (last segment only)",
     '    for segment in split_segments(cmd):\n        tokens = segment_tokens(segment) if',
     '    for segment in [s for s in split_segments(cmd) if s.strip()][-1:]:\n'
     '        tokens = segment_tokens(segment) if', "guard",
     "detached: a background job followed by another line, MEASURED to outlive the agent"),
    ("detached-launch: disown on its own line no longer denies",
     '    if j < len(tokens) and basename(tokens[j]) == "disown":\n        return "disown"',
     '    if False:\n        return "disown"', "guard",
     "detached: disown on its own line, even with a pid printed first"),
    ("detached-launch: a background job inside sh -c no longer denies",
     '        script = inline_script(tokens)\n        if script and',
     '        script = ""\n        if script and', "guard",
     "detached: a background job inside sh -c"),
    ("detached-launch: an ampersand in a python heredoc body denies again",
     '    cmd = _strip_heredoc_bodies_unconditionally(cmd)\n    if "$!" in cmd:',
     '    if "$!" in cmd:', "guard",
     "detached: an ampersand in a python heredoc body is Python, MEASURED 6 such local commands"),
    ("detached-launch: Start-Job no longer denies",
     '    if tool == "start-job":\n        return word',
     '    if False:\n        return word', "guard",
     "detached: Start-Job hands the work to a job object with no pid here at all"),
    ("detached-launch: Start-Process no longer denies, whatever flags it carries",
     '    if tool == "start-process":\n        rest = {t.lower() for t in tokens[index + 1:]}',
     '    if False:\n        rest = {t.lower() for t in tokens[index + 1:]}', "guard",
     "detached: Start-Process with neither -Wait nor -PassThru"),
    ("detached-launch: -Wait/-PassThru no longer exempt Start-Process, every call denies",
     '        if "-wait" in rest or "-passthru" in rest:\n            return ""',
     '        if False:\n            return ""', "guard",
     "detached: Start-Process -Wait blocks until the child exits"),
    ("detached-launch: cmd /c start no longer denies",
     '        if rest[i].lower() in ("/c", "/k") and rest[i + 1].lower() == "start":',
     '        if False:', "guard",
     "detached: cmd /c start opens an untracked window, from PowerShell"),
    ("command word: a PowerShell $name = assignment no longer skips ahead of the real command",
     '        if (POWERSHELL_ASSIGNMENT.match(tokens[index]) and index + 1 < end\n'
     '                and tokens[index + 1] == "="):\n            index += 2\n            continue',
     '        if False:\n            index += 2\n            continue', "guard",
     "detached: a PowerShell assignment ahead of Start-Process is still read, MEASURED "
     "wrongly missed before _skip_assignments_and_keywords learned $name ="),
    ("shell segments: a quote never closes, so a real call after it is swallowed whole",
     '        return 1, ("" if char == quote[-1] else quote)',
     '        return 1, quote', "guard", 'kill: a quoted phrase ahead of a real chained kill still denies'),
    ("shared-tree: a conflict-side flag no longer exempts the checkout",
     'CHECKOUT_CONFLICT_FLAGS = {"--ours", "--theirs", "--merge"}',
     'CHECKOUT_CONFLICT_FLAGS = set()', "guard", 'checkout: --theirs resolves a real, unresolved merge conflict'),
    ("shared-tree: every tree reads as mid-conflict",
     '    return any(os.path.isdir(os.path.join(path, name)) for name in REBASE_STATE_DIRS)',
     '    return True', "guard", "checkout: the same call with no conflict in progress keeps today's decision"),
    ("log: stop logging refusals",
     '                handle.write(line + "\\n")',
     '                pass', "guard", 'log: one line per refusal and none for an allow'),
    ("shared-tree: keep heredoc bodies in every rule",
     '    return "\\n".join(line for at, line in enumerate(cmd.split("\\n")) if at in show)',
     '    return cmd', "guard", 'heredoc: prose naming the stash with no interpreter'),
    ("env-file: name the file in the environment reason, the reviewed defect",
     '        refuse(tool, "deny", "env-file", ENV_TOOL_REASON + ". " + ENV_ADVICE, target)',
     '        refuse(tool, "deny", "env-file", ENV_TOOL_REASON + " " + target + ". "'
     ' + ENV_ADVICE, target)', "guard",
     'env: a Write outside the fixtures, and the reason names no file'),
    ("env-file: name the file in the shell environment reason, the reviewed defect",
     '        refuse(tool, "deny", "env-file", refusal + ". " + ENV_ADVICE, logged)',
     '        refuse(tool, "deny", "env-file", logged + ". " + ENV_ADVICE, logged)', "guard", 'env: an absolute Windows path is still a path'),
    ("env-file: never judge a substitution body",
     '        refusal = _env_flat(text, in_message or index == len(texts) - 1)',
     '        refusal = ("", "")', "guard", 'env: a substitution is judged, echo $(cat'),
    ("env-file: a substitution in a message may print any text",
     'in_message or index == len(texts) - 1', 'in_message or index >= 0', "guard",
     'env: a substitution is judged, cat $(printf'),
    ("env-file: a fixed string that names the file is refused",
     'text_to_file = command in ENV_TEXT_COMMANDS and text_ok',
     'text_to_file = command in ENV_TEXT_COMMANDS and False', "guard",
     'env: an existence test or fixed text, echo'),
    ("env-file: a double-bracket existence test is refused",
     'ENV_EXISTENCE_COMMANDS = ("ls", "test", "[", "[[")', 'ENV_EXISTENCE_COMMANDS = ("ls", "test", "[")',
     "guard", 'env: an existence test or fixed text, [[ -f'),
    ("env-file: a redirect from the file is not a read",
     r'READ_REDIRECT = re.compile(r"(?<![<])<(?![<(])")',
     r'READ_REDIRECT = re.compile(r"(?<![<])<x(?![<(])")', "guard", 'env: a substitution is judged, echo $(<'),
    ("env-file: a trailing paren hides the name",
     'word).strip("()")', 'word)', "guard",
     'env: a substitution is judged, (cat'),
    ("env-file: the backtick branch of the scan finds no substitution",
     '            done.extend(inner)', '            done.extend([])', "guard",
     'env: normalized, glob, heredoc or depth, ls `cat'),
    ("env-file: the process-substitution branch of the scan finds none",
     'cmd[i:i + 2] in ("<(", ">(")', 'cmd[i:i + 2] in ("<x", ">x")', "guard",
     'env: normalized, glob, heredoc or depth, ls <(cat'),
    ("env-file: an unquoted heredoc body is not judged",
     '        if not quote:\n            refusal = env_refusal(body, subs_only=True, heredoc=True)',
     '        if quote:\n            refusal = env_refusal(body, subs_only=True, heredoc=True)', "guard",
     'env: normalized, glob, heredoc or depth, cat <<EOF'),
    ("env-file: no cap on the depth of a nest",
     '            if len(stack) + depth > ENV_MAX_DEPTH:', '            if len(stack) + depth > 10 ** 9:', "guard",
     'env: normalized, glob, heredoc or depth, echo $($($'),
    ("env-file: a glob is not a name",
     'ENV_GLOB = re.compile(r"[?*\\[]")', 'ENV_GLOB = re.compile(r"[?*\\[]x")', "guard",
     'env: normalized, glob, heredoc or depth, cat .en?'),
    ("env-file: inner quotes stay in the word",
     'word = re.sub(r"[\\"\'`]", "", word).strip("()")', 'word = word.strip("()")', "guard",
     'env: normalized, glob, heredoc or depth, cat .e""nv'),
    ("env-file: a backslash stays in the word",
     'word = re.sub(r"\\\\(?!\\.)", "", word)', 'word = word', "guard",
     'env: normalized, glob, heredoc or depth, cat .e\\nv'),
    ("env-file: a glob names an env file only by a fixed suffix",
     '        if names_env_file(sample):', '        if sample.startswith(".env.local"):', "guard",
     'env: normalized, glob, heredoc or depth, cat .env.bak*'),
    ("env-file: the example exemption is a prefix, not the whole name",
     '    return name.startswith(ENV_PREFIX) and name != ENV_ALLOWED',
     '    return name.startswith(ENV_PREFIX) and not name.startswith(ENV_ALLOWED)', "guard",
     'env: a glob that could name a covered backup, cat .env.example*'),
    ("env-file: a piped echo keeps the text allowance",
     'text_ok and not piped', 'text_ok', "guard", 'env: a relay of the text, echo .env | xargs'),
    ("env-file: a pipe with a double bar counts as a pipe",
     'piped = end == "|" and', 'piped = end in ("|", "||") and', "guard",
     'env: text with no relay, echo .env || echo no'),
    ("env-file: the relay through a file is not checked",
     '    return _env_relay(texts)', '    return "", ""', "guard",
     'env: a relay of the text, echo .env > f; cat'),
    ("env-file: every command may read the relay file",
     '        return command not in ENV_RELAY_SAFE and any(', '        return False and any(',
     "guard", 'env: a relay of the text, echo .env > x && xargs'),
    ("env-file: no command may read the relay file, even a listing",
     '        return command not in ENV_RELAY_SAFE and any(', '        return True and any(', "guard",
     'env: text with no relay, echo .env > .worktreeinclude'),
    ("env-file: a printf newline escape stays in the word",
     'words = re.sub(r"\\\\[ntr]", " ", " ".join(words)).split()', 'pass', "guard",
     "env: a relay of the text, printf '.env"),
    ("env-file: an fd duplication hides the pipe after the text command",
     '    piece = re.sub(r"\\d*>&(\\d+|-)", " ", piece)', '    pass', "guard",
     'env: fd duplication or a read after the write, printf .env 2>&1'),
    ("env-file: a read before the write counts as a relay",
     '    written = set()\n    for words, _, command in segments[-1]:',
     '    for words, _, command in segments[-1]:', "guard",
     'env: check then write, grep x'),
    ("env-file: a read after the write is no relay",
     '        if reads(words, command, written):\n            return (ENV_CONTENTS_REASON,',
     '        if False:\n            return (ENV_CONTENTS_REASON,', "guard",
     'env: fd duplication or a read after the write, echo .env > f; cat f'),
    ("env-file: a runner given the file never reads as running inline code",
     '    if command.lower() not in ENV_INLINE_RUNNERS:\n        return False\n    hit, stdin = _runner_scan',
     '    return False\n    hit, stdin = _runner_scan', "guard",
     'inline code under a runner given the file denies, node --env-file=.env -e'),
    ("env-file: a runner given the file never reads as starting a printing child",
     '                    if _runner_child_prints(words, position, command, stdin_piped):\n',
     '                    if False:\n', "guard",
     'env-child: deny, a runner given the file must not print it through a child'),
    ("frozen-path: name the path in the frozen reason",
     '    refuse(tool, "deny", "frozen-path", FROZEN_REASON, target)',
     '    refuse(tool, "deny", "frozen-path", FROZEN_REASON + " " + target, target)', "guard", 'frozen: Write of a config hook'),
    # Added: rules guard.py grew after the prior mutation run.
    ("live-stream: never refuse a live stream",
     '    for segment in split_segments(stripped):\n'
     '        matched = live_stream_hit(segment)\n'
     '        if matched:\n'
     '            refuse(tool, "deny", "live-stream", LIVE_STREAM_REASON, matched)',
     '    for segment in split_segments(stripped):\n'
     '        matched = live_stream_hit(segment)\n'
     '        if False:\n'
     '            refuse(tool, "deny", "live-stream", LIVE_STREAM_REASON, matched)', "guard", 'stream: tail -f never ends'),
    ("waiter: never refuse a waiter loop (Rule 9)",
     '    matched = waiter_verdict(split_segments(stripped), background)\n'
     '    if matched:\n'
     '        if poller:',
     '    matched = waiter_verdict(split_segments(stripped), background)\n'
     '    if False:\n'
     '        if poller:', "guard",
     'waiter: a bare sleep'),
    ("waiter: a loop around a short sleep is let through",
     '    if sleeps and loop:\n        return sleeps[0][0]\n',
     '    if False:\n        return sleeps[0][0]\n', "guard",
     'waiter: an until-loop waiting on a file is refused'),
    ("waiter: a clock loop is let through in the foreground",
     '    if background and clock_loop(token_rows):\n',
     '    if clock_loop(token_rows):\n', "guard",
     'wait-until: the clock loop in the foreground stays refused'),
    ("waiter: every loop counts as a clock loop under run_in_background",
     '    if background and clock_loop(token_rows):\n',
     '    if background:\n', "guard",
     'wait-until: a loop with no clock bound stays refused under run_in_background'),
    ("waiter: a long pause is let through in the foreground",
     '    long_ok = background and followed\n',
     '    long_ok = followed\n', "guard",
     'waiter: a 30 s sleep ahead of a later call is refused'),
    ("waiter: a long pause followed by a command is refused under run_in_background",
     '    long_ok = background and followed\n',
     '    long_ok = False\n', "guard",
     'wait-until: a pause of 600 s, then one command, is allowed under run_in_background'),
    # The clock loop's checks in hooks/guard_stream.py (clock_test and clock_loop): one revert per check, and the
    # forms a loop could take that a check refuses. Each names the case that must go red.
    ("waiter: a clock loop with no date read is let through under run_in_background",
     '    if not cut:\n        return False\n',
     '    if not cut:\n        cut = 1\n', "guard",
     'a loop on a read of another command with a +%s format'),
    ("waiter: a clock loop with no literal time is let through under run_in_background",
     'bool(CLOCK_LITERAL.match(rest[1]))',
     'True', "guard",
     'a loop on date with no literal time'),
    ("waiter: a clock loop with a && clause after its test is let through under run_in_background",
     '    return words[heads[0] + 1:heads[0] + 2] == ["do"] and clock_test(token_rows[heads[0]])\n',
     '    return clock_test(token_rows[heads[0]])\n', "guard",
     'a && clause after it'),
    ("waiter: a second loop with no pause is let through",
     '    if len(heads) != 1 or any(',
     '    if any(', "guard",
     'a second loop with no pause'),
    ("waiter: a bare sleep of 600 s is let through under run_in_background",
     '    long_ok = background and followed\n',
     '    long_ok = background\n', "guard",
     'a bare sleep of 600 s with nothing after it'),
    # The polarity, the operators, the operand count, the literal forms and the command form of the test.
    ("waiter: a clock loop's direction is swapped, so a while loop on a later time is let through",
     '    ends_loop = LATER_THAN if head[0].lower() == "until" else EARLIER_THAN\n',
     '    ends_loop = EARLIER_THAN if head[0].lower() == "until" else LATER_THAN\n', "guard",
     'a while loop that waits while the clock is later than a literal'),
    ("waiter: a clock loop's direction is not checked, so a while loop on a later time is let through",
     '    ends_loop = LATER_THAN if head[0].lower() == "until" else EARLIER_THAN\n',
     '    ends_loop = LATER_THAN | EARLIER_THAN\n', "guard",
     'a while loop that waits while the clock is later than a literal'),
    ("waiter: an equality test is taken as a deadline, so a loop on an equal ISO time is let through",
     'LATER_THAN = {">", "-gt", "-ge"}',
     'LATER_THAN = {">", "-gt", "-ge", "="}', "guard",
     'a loop that tests the clock for equality with a full ISO time'),
    ("waiter: a clock test with an extra operand is let through under run_in_background",
     'len(rest) == 2 and',
     'len(rest) >= 2 and', "guard",
     'a clock loop with an extra file test'),
    ("waiter: an epoch literal is refused, so an epoch deadline is held as a wait",
     r'|\d{9,}$")',
     r'")', "guard",
     'a clock loop on an epoch that is reached is allowed'),
    ("waiter: an ISO date-time literal is refused, so an ISO deadline is held as a wait",
     r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?$|\d{9,}$',
     r'\d{9,}$', "guard",
     'a clock loop, then one command, is allowed under run_in_background'),
    ("waiter: an arithmetic test is taken as a clock test, so it is let through under run_in_background",
     'TEST_CLOSER = {"[": "]", "[[": "]]", "test": None}',
     'TEST_CLOSER = {"[": "]", "[[": "]]", "test": None, "((": "))"}', "guard",
     'a loop written as an arithmetic test'),
    ("waiter: a numeric order on a +%s read takes an ISO literal, so it is let through under run_in_background",
     '        return form == "+%s" and ":" not in rest[1]\n',
     '        return form == "+%s"\n', "guard",
     'a numeric order on a +%s read against an ISO date-time'),
    ("waiter: a text order on an ISO read takes an epoch literal, so it is let through under run_in_background",
     '    return form is not None and "%s" not in form and not rest[1].isdigit()\n',
     '    return form is not None and "%s" not in form\n', "guard",
     'a text order on an ISO read against an epoch'),
    # A `for` loop beside the clock loop makes it two loops, so the clock rule does not judge the command. Without
    # the word check, the clock loop would count as the command's one loop and the pause loop would go unjudged.
    ("waiter: a loop word other than while or until is ignored, so a clock loop beside a pause loop is let through",
     '    if len(heads) != 1 or any(w in LOOP_WORDS and w not in ("while", "until", "do") for w in words):\n',
     '    if len(heads) != 1:\n', "guard",
     'a clock loop with a command body, then a for loop with pauses'),
    ("waiter: a foreground watcher is let through",
     '    return run_watch or ("" if background else watcher)',
     '    return ""', "guard",
     'waiter: a foreground gh run watch is refused'),
    ("command word: a loop keyword no longer yields to the command inside it (Rule 9's own gap)",
     '        if ASSIGNMENT.match(tokens[index]) or tokens[index] in LOOP_KEYWORDS:',
     '        if ASSIGNMENT.match(tokens[index]):', "guard",
     'waiter: an until-loop over a plain readiness check, MEASURED wrongly allowed'),
    ("waiter: a pattern-polling loop condition no longer gets its own reason",
     '        if poller:\n'
     '            refuse(tool, "deny", "waiter", PATTERN_POLLER_REASON, poller + " " + matched)',
     '        if False:\n'
     '            refuse(tool, "deny", "waiter", PATTERN_POLLER_REASON, poller + " " + matched)',
     "guard",
     'waiter: a while-loop with a pattern-polling condition, MEASURED wrongly allowed'),
    ("destructive-delete: blind the wide-delete patterns",
     "    for pattern in DESTRUCTIVE_DELETE:\n        found = pattern.search(cmd)",
     "    for pattern in ():\n        found = pattern.search(cmd)", "guard",
     'delete: Remove-Item at a drive root'),
    # Added 2026-09-24 with the cmd.exe verbs (`rd`/`rmdir`/`del`/`erase` and their `/s` flag),
    # the Windows twin of the mutant just above. Drops the new forms back to the gap they fixed:
    # `rd /s /q C:\` denied nothing before this rule existed.
    ("destructive-delete: drop the cmd.exe verbs, the Windows forms this rule adds",
     'CMD_EXE_DELETE_WORDS = {"rd", "rmdir", "del", "erase"}',
     "CMD_EXE_DELETE_WORDS = set()", "guard",
     'delete: rd /s /q at a drive root, Bash'),
    # Added 2026-10-17 (guard-audit-fixes-234), the token reader of POSIX `rm -rf`. The patterns
    # above never match a `-rf` cluster, so `rm_delete_hit` is the only reader of `rm -rf ~/`.
    # Dropping it leaves the cmd.exe reader alone and every POSIX wide delete allowed.
    ("destructive-delete: drop the token reader of rm -rf, the POSIX form",
     "        matched = rm_delete_hit(segment) or cmd_exe_delete_hit(segment)",
     "        matched = cmd_exe_delete_hit(segment)", "guard",
     'delete: the home directory with a trailing slash'),
    ("git-call parsing: drop the redirect strip before tokenizing",
     '    text = REDIRECTION.sub(" ", segment)',
     '    text = segment', "guard", 'checkout: a start point survives a merged-output redirect'),
    ("git-call parsing: tokenize on whitespace, keep the quote marks",
     '    tokens = segment_tokens(text)\n',
     '    tokens = None\n', "guard", 'per-file deny: a double-quoted path in the shared checkout'),
    ("per-file carve-out: allow a worktree discard of any pathspec",
     '        if spec in (".", "") or spec[0] == ":" or any(c in spec for c in "*?["):\n            return False',
     '        if False:\n            return False', "guard", 'per-file ask: restore of a glob in a worktree still asks'),
    ("per-file carve-out: allow a restore flag outside the allow-list",
     '        if any(f not in RESTORE_PER_FILE_FLAGS for f in flags):\n            return False',
     '        if False:\n            return False', "guard", 'per-file ask: restore -p of one file in a worktree still asks'),
    ("per-file: a second -C replaces the first, never joins onto it",
     '    return os.path.join(base, value) if base and value else (value or base)',
     '    return value or base', "guard",
     'per-file deny: -C shared checkout then -C . reset --hard, from a clean worktree'),
    ("per-file: a restore operand before -- is no path",
     '        return before + after, True',
     '        return after, True', "guard",
     'per-file deny: restore f.txt -- keep.txt in the shared checkout, operand before --'),
    ("per-file carve-out: a restore operand before -- is not read in a worktree",
     '        specs = [a for a in head if not a.startswith("-")] + [a for a in specs if dashed or not a.startswith("-")]',
     '        specs = [a for a in specs if dashed or not a.startswith("-")]', "guard",
     'per-file ask: restore . -- keep.txt in a worktree: a dot before -- is a whole tree'),
    ("per-file carve-out: an unreadable pathspec is a path",
     '        if any(c in spec for c in "$`{}"):  # unreadable: a discard of unknown size\n            return False',
     '        if False:\n            return False', "guard",
     'per-file ask: restore "$F" -- keep.txt in a worktree still asks, unreadable before --'),
    ("per-file: the allow ignores a cd, pushd or popd in the command",
     '    if _MOVES_SHELL.search(cmd):\n        return False',
     '    if False:\n        return False', "guard",
     'per-file ask: cd lane && restore f.txt with no heredoc asks'),
    ("per-file: the allow ignores a second distinct -C target in the command",
     '    return len(targets) <= 1',
     '    return True', "guard",
     'per-file ask: two -C targets in one checkout'),
    ("config-edit: stop noting project config edits, shell tool",
     '    matched = project_config_shell_hit(stripped, cwd)\n'
     '    if matched:\n'
     '        record(tool, "noted", "config-edit", matched)',
     '    matched = project_config_shell_hit(stripped, cwd)\n'
     '    if False:\n'
     '        record(tool, "noted", "config-edit", matched)', "guard", 'log: a project config edit is allowed and noted'),
    # Added: the stash/reset/restore split (Decision 12). Each mutation collapses one predicate
    # back to a bare name match, the exact defect this split fixes, so a later edit that redoes
    # that collapse goes red here.
    ("shared-tree: stash collapses back to a name match on every action",
     '    return stash_action(args) not in STASH_READ_ACTIONS',
     '    return True', "guard", 'stash: list only reads, no subcommand match'),
    # Added 2026-09-19 with the stack clause. The first mutant blinds the DIRECTION predicate, so
    # every stash call is read against the working tree. The second puts back the exact defect
    # this change fixes: only `drop` and `clear` read the stack, so `pop`, `apply` and `branch`
    # pass over a clean tree that carries another session's entry.
    ("shared-tree: no stash action is read as taking an entry off the stack",
     'def stash_takes_the_stack(args) -> bool:',
     'def stash_takes_the_stack(args) -> bool:\n    return False', "guard", 'subject: dropping a real stash entry still denies'),
    ("subject: only drop and clear read the stack, the narrow clause put back",
     '    if stash_takes_the_stack(args):\n        stack = stash_stack(where)',
     '    if stash_action(args) in ("drop", "clear"):\n        stack = stash_stack(where)', "guard", 'subject: popping a real entry from a CLEAN checkout still denies'),
    ("shared-tree: reset collapses back to a name match, --hard or not",
     '    return any(flag in args for flag in RESET_DISCARD_FLAGS)',
     '    return True', "guard", 'reset: a plain reset only unstages, the working tree is untouched'),
    # Each mutant drops ONE flag from the one constant, so each form's own case must go red.
    ("shared-tree: reset --merge no longer takes --hard's verdict",
     'RESET_DISCARD_FLAGS = ("--hard", "--merge", "--keep")',
     'RESET_DISCARD_FLAGS = ("--hard", "--keep")', "guard", 'reset: --merge at HEAD over a staged edit and a staged new file refuses'),
    ("shared-tree: reset --keep no longer takes --hard's verdict",
     'RESET_DISCARD_FLAGS = ("--hard", "--merge", "--keep")',
     'RESET_DISCARD_FLAGS = ("--hard", "--merge")', "guard", 'reset: --keep at another commit moves the branch, so a shared checkout refuses'),
    # Added: the subject read. One per arm. Each mutation blinds ONE subject read, which must
    # turn that arm's empty-subject case red: a guard that refuses without reading its subject is
    # the defect these arms fix.
    ("subject: the reset arm never reads the working tree",
     'def reset_subject(args, where: str):',
     'def reset_subject(args, where: str):\n    return False', "guard", 'subject: a hard reset in a clean tree takes nothing'),
    ("subject: a hard reset at any commit passes on a clean tree, the owner's narrowing undone",
     '    if reset_target(args) not in RESET_HEAD_TARGETS:\n        return False',
     '    if False:\n        return False', "guard", 'subject: a hard reset one commit back moves the branch, clean tree or not'),
    ("subject: the stash arm never reads the tree or the stack",
     'def stash_subject(args, where: str):',
     'def stash_subject(args, where: str):\n    return False', "guard", 'subject: setting aside a clean tree takes nothing'),
    ("subject: the restore arm never reads its paths",
     'def restore_subject(args, where: str):',
     'def restore_subject(args, where: str):\n    return False', "guard", 'subject: restoring a clean path inside a dirty tree changes nothing'),
    ("subject: the checkout arm never reads its paths",
     'def checkout_subject(args, where: str):',
     'def checkout_subject(args, where: str):\n    return False', "guard", 'subject: checking out a clean path inside a dirty tree changes nothing'),
    ("subject: the clean arm never reads the untracked entries",
     'def clean_subject(args, where: str):',
     'def clean_subject(args, where: str):\n    return False', "guard", 'subject: a clean with no untracked file deletes nothing'),
    ("subject: a clean exclude pattern is read as a pathspec, so the read narrows wrongly",
     'CLEAN_OPT_WITH_VALUE = {"-e", "--exclude"}',
     'CLEAN_OPT_WITH_VALUE = set()', "guard", 'subject: an exclude pattern is not a pathspec'),
    # POSIX-only mutant: its required case ("subject: a git that cannot answer the status read
    # allows, rather than guess") is itself wrapped in `if os.name != "nt":` in test_guard.py, because
    # `make_blind_git`'s own docstring records a Windows measurement (2026-09-16): CreateProcess
    # appends `.exe` and never reads PATHEXT, so a `git.cmd` stand-in is skipped and the real
    # `git.exe` further on PATH answers instead, which would make the case pass for the wrong
    # reason. The case is therefore SKIPPED on Windows entirely, so the required name can never
    # appear among that platform's FAIL lines, whatever else the run turns up.
    ("subject: an unreadable subject is refused instead of allowed and logged",
     '        if state is None:\n',
     '        if False:\n', "guard", 'subject: a git that cannot answer the status read allows, rather than guess', "posix"),
    ("subject: an unforced worktree remove is noted as unread again",
     '            if subcommand != "worktree-remove" or worktree_remove_forced(args):',
     '            if True:', "guard", "log: an unforced worktree remove with an unreadable subject records no note", "posix"),
    ("subject: a forced worktree remove loses its unread note",
     '            if subcommand != "worktree-remove" or worktree_remove_forced(args):',
     '            if subcommand != "worktree-remove":', "guard", "log: a forced worktree remove with an unreadable subject is still noted", "posix"),
    ("subject: a quoted force flag reads as unforced", '            tokens = shlex.split(arg)', '            tokens = [arg]', "guard", "log: a quoted or abbreviated force on a worktree remove is still noted", "posix"),
    ("subject: an abbreviated force flag reads as unforced", '"--force".startswith(tok)', 'tok == "--force"', "guard", "log: a quoted or abbreviated force on a worktree remove is still noted", "posix"),
    ("scratchpad: this session's own scratchpad stops being private",
     'def under_session_scratchpad(where: str, session_id: str) -> bool:',
     'def under_session_scratchpad(where: str, session_id: str) -> bool:\n    return False', "guard", "scratchpad: a discard in this session's own scratchpad is private"),
    ("scratchpad: every path reads as this session's scratchpad",
     '    parts = real.split(os.sep)\n    for index in range(len(parts) - 1):',
     '    return True\n    parts = real.split(os.sep)\n    for index in range(len(parts) - 1):', "guard", "scratchpad: another session's scratchpad is not this session's"),
    ("scratchpad: no path reads as any session's scratchpad",
     '    return any(os.path.normcase(parts[i + 1]) == "scratchpad"',
     '    return False and any(os.path.normcase(parts[i + 1]) == "scratchpad"', "guard",
     "audit-high paths: test-author Edit of another session's scratchpad outside a repo is refused"),
    ("scratchpad-commit-msg-owner: the rule never fires",
     "matched = agent and scratchpad_message_file(segment, cite_where)",
     "matched = False and scratchpad_message_file(segment, cite_where)", "guard",
     "scratchpad-message: an agent's commit -F of a scratchpad file is refused"),
    ("scratchpad-commit-msg-owner: an orchestrator's call is refused too",
     "matched = agent and scratchpad_message_file(segment, cite_where)",
     "matched = scratchpad_message_file(segment, cite_where)", "guard",
     "scratchpad-message: an orchestrator's commit -F of the same scratchpad file is allowed"),
    ("shared-tree: restore collapses back to a name match, --staged or not",
     '    staged = "--staged" in args or "-S" in args\n'
     '    worktree = "--worktree" in args or "-W" in args\n'
     '    return worktree or not staged',
     '    return True', "guard", 'restore: staged alone only touches the index'),
    # Added: the agent model cap (rule 8, PR #42). These are the mutations its builder ran by hand
    # on `.bak` copies, now in CI. Each one undoes one thing the review made the rule do, so a later
    # edit that redoes it goes red here.
    ("cap: the edit-count cap comes back, so 200 no-op edits hide a lift",
     '    if isinstance(edits, list):\n        for edit in edits:',
     '    if isinstance(edits, list):\n        for edit in edits[:200]:', "guard", 'cap: the lift in the last of 400 edits still asks'),
    # MEASURED 2026-09-22: on an account with no SeCreateSymbolicLinkPrivilege (this box, and any
    # ordinary non-developer-mode Windows account), `os.symlink` raises and the symlink case below
    # degrades to allow, so it never turns red and this mutant SURVIVED, 0 red lines. On a runner
    # that can make a real symlink (Linux, and a privileged Windows runner), the symlink case is
    # what turns red instead, and the trailing-dot case is the one that does not (POSIX has no
    # trailing-dot quirk). The required field names the TAG both cases carry for exactly this
    # reason, not either case's own name: see the comment beside the trailing-dot case in
    # hooks/test_guard.py.
    ("cap: the resolved-basename branch is gone, so a symlink to a settings file walks past",
     '        return basename(_resolved(path, cwd)) in SETTINGS_BASENAMES\n'
     '    except Exception:\n        return False',
     '        return False\n'
     '    except Exception:\n        return False', "guard", '[resolve-branch proof]'),
    ("cap: the JSON key walk is gone, so a JSON-escaped key walks past",
     '    for key, value in json_cap_values(text).items():',
     '    for key, value in ():', "guard", 'cap: a JSON-escaped key in the content asks'),
    ("cap: cap_safe passes text through, so a long value is neither cut nor marked",
     '    clean = CAP_CONTROL.sub(" ", text or "")',
     '    return text or ""\n    clean = CAP_CONTROL.sub(" ", text or "")', "guard", 'cap: a very long model value is cut and the cut is marked'),
    ("cap: the bare-key pass is gone, so an unreadable value walks past",
     '    for found in AGENT_CAP_KEY.finditer(text):\n'
     '        reading.setdefault(found.group(0), "")',
     '    for found in ():\n'
     '        reading.setdefault(found.group(0), "")', "guard", 'cap: a value the pattern cannot read still asks'),
    ("cap: the rule runs ahead of the frozen-path deny, so the config settings ask instead",
     '        if is_frozen(target, cwd):\n'
     '            refuse(tool, "deny", "frozen-path", FROZEN_REASON, target)',
     '        if is_settings_file(target, cwd):\n'
     '            change = cap_change_parts(write_content_parts(tool_input))\n'
     '            if change:\n'
     '                refuse(tool, "ask", "agent-model-cap", cap_ask_reason(change, target),\n'
     '                       target + " " + change)\n'
     '        if is_frozen(target, cwd):\n'
     '            refuse(tool, "deny", "frozen-path", FROZEN_REASON, target)', "guard", 'cap: the config settings stay denied, never asked'),
    ("cap: the shell route runs ahead of the frozen-path deny, so a heredoc onto the config "
     "settings asks instead",
     '    matched = shell_write_hit(raw, cwd, is_frozen, _holds_frozen)\n'
     '    if matched:\n'
     '        refuse(tool, "deny", "frozen-path", FROZEN_REASON, matched)',
     '    matched = shell_write_hit(raw, cwd, is_settings_file)\n'
     '    if matched:\n'
     '        change = cap_change(raw)\n'
     '        if change:\n'
     '            refuse(tool, "ask", "agent-model-cap", cap_ask_reason(change, matched),\n'
     '                   matched + " " + change)\n'
     '    matched = shell_write_hit(raw, cwd, is_frozen, _holds_frozen)\n'
     '    if matched:\n'
     '        refuse(tool, "deny", "frozen-path", FROZEN_REASON, matched)', "guard", 'cap: a heredoc onto the config settings stays denied'),
    ("cap: the shell route reads the stripped command, so a heredoc body's cap change walks past",
     '        change = cap_change(raw)',
     '        change = cap_change(stripped)', "guard", 'cap: a heredoc writing a project settings file asks'),
    ("cap: an earlier part wins, so an Edit names the value it leaves, not the one it arrives at",
     '            values[key] = value',
     '            values.setdefault(key, value)', "guard", 'cap: Edit turning the force flag off asks'),
    ("cap: a Write of a settings file never asks, so an opus lift lands unasked",
     '        if is_settings_file(target, cwd):\n            change = cap_change_parts(write_content_parts(tool_input))',
     '        if False:\n            change = cap_change_parts(write_content_parts(tool_input))', "guard",
     'cap: Write of a project local settings file setting an opus model asks'),
    ("floor: the model test is case-sensitive, so a mixed-case haiku id walks past",
     '    return "haiku" in str(model).lower()',
     '    return "haiku" in str(model)', "guard", 'floor: Agent with a mixed-case haiku spelling is denied'),
    ("floor: a non-string model is skipped, so a list naming haiku walks past",
     '    return "haiku" in str(model).lower()',
     '    return isinstance(model, str) and "haiku" in model.lower()', "guard", 'floor: Agent with a list model naming haiku is denied'),
    ("role-model: the rank test is dropped, so a spawn above its role's row passes",
     '        if named > ROLE_MODEL_RANK.index(row):',
     '        if False:', "guard", 'role-model: test-author on sonnet is denied'),
    ("role-model: Explore loses its audit exemption, so an audit Explore on sonnet is denied",
     'if role == EXPLORE_ROLE and named < top and ("audit"',
     'if False and ("audit"', "guard", 'role-model: Explore on sonnet with Audit: on line 1 is allowed'),
    ("role-model: the audit marker is read off any line, so an Explore with it on line 2 walks past on sonnet",
     '            hit = rx.search(first)',
     '            hit = rx.search(brief)', "guard",
     'role-model: Explore on sonnet with Audit: on line 2 is denied (line 1 only counts)'),
    ("role-model: a reviewer round 2 or 3 loses its exemption, so it is denied on sonnet",
     'for kind, n in brief_markers(tool_input.get("prompt"))):',
     'for kind, n in brief_markers("")):', "guard", 'role-model: reviewer on sonnet with a Round 2 of 3 line is allowed'),
    ("role-model: a reviewer round 1 is exempt too, so it walks past on sonnet",
     'kind.lower() == "round" and n in ROLE_REVIEWER_FREE_ROUNDS',
     'kind.lower() == "round" and n in ("1", "2", "3")', "guard",
     'role-model: reviewer on sonnet with a Round 1 of 3 line is denied'),
    ("role-model: the reviewer fix check lift reads an empty brief, so a fix check reviewer on sonnet is denied",
     '("fixcheck", None) in marker_hits(tool_input.get("prompt")):',
     '("fixcheck", None) in marker_hits(""):', "guard",
     'role-model: fix check: reviewer on sonnet with the marker on line one is allowed'),
    ("role-model: the fix check lift drops its role test, so a test-author on sonnet with the marker walks past",
     'if role == "reviewer" and named < top and ("fixcheck", None) in marker_hits(tool_input.get("prompt")):',
     'if named < top and ("fixcheck", None) in marker_hits(tool_input.get("prompt")):', "guard",
     'role-model: fix check: test-author on sonnet with the marker is denied and names no fix check marker'),
    ("role-model: the fix check lift drops its rank test, so a reviewer on a model the table does not rank walks past with the marker",
     'if role == "reviewer" and named < top and ("fixcheck", None) in marker_hits(tool_input.get("prompt")):',
     'if role == "reviewer" and ("fixcheck", None) in marker_hits(tool_input.get("prompt")):', "guard",
     'role-model: fix check: reviewer on claude-fable-5-1 with the marker on line one is denied, the lift does not reach an unranked model'),
    ("role-model: the fix check row loses its line-start anchor, so a reviewer on sonnet with Round 1 of 3 first on line one walks past",
     r'("fixcheck", r"^[ \t]*" + re.escape(FIX_CHECK_MARKER)',
     r'("fixcheck", r"\b" + re.escape(FIX_CHECK_MARKER)', "guard",
     'role-model: fix check: reviewer on sonnet with Round 1 of 3 first on line one and the marker after it is denied'),
    ("role-model: the fix check row drops the tab from its line-start class, so a reviewer on sonnet with a leading tab walks past",
     r'("fixcheck", r"^[ \t]*" + re.escape(FIX_CHECK_MARKER)',
     r'("fixcheck", r"^[ ]*" + re.escape(FIX_CHECK_MARKER)', "guard",
     'role-model: fix check: reviewer on sonnet with the marker after a leading tab on line one is allowed'),
    ("role-model: the fix check row loses its trailing word boundary, so a reviewer on sonnet with Fix checkpoint on line one walks past",
     r're.escape(FIX_CHECK_MARKER) + r"\b", "first-line"),',
     r're.escape(FIX_CHECK_MARKER), "first-line"),', "guard",
     'role-model: fix check: reviewer on sonnet with Fix checkpoint on line one is denied'),
    ("role-model: Opus is no longer left to the ceiling, so a builder on opus is denied here",
     'named == top or row is None:',
     'row is None:', "guard",
     'role-model: builder on opus with no round line is denied under agent-model-cap, not this rule'),
    ("role-model: the default model is ignored, so a builder with no model is denied under a sonnet default",
     '    if os.environ.get(ROLE_MODEL_ENV, "").strip():',
     '    if False:', "guard", 'role-model: builder with no model is allowed when the default is sonnet'),
    ("role-model: the agent file pin is ignored, so a reviewer with no model is denied",
     '    if pinned:\n        return "", "", False',
     '    if False:\n        return "", "", False', "guard",
     'role-model: reviewer with no model is allowed when the default is unset'),
    ("role-model: the no-model deny is dropped, so a builder with no model and no default passes",
     '    return ROLE_NO_MODEL_REASON %',
     '    return "", "", False; ROLE_NO_MODEL_REASON %', "guard",
     'role-model: builder with no model is denied when the default is unset'),
    ("role-model: an unread table is not logged, so the pass leaves no trace",
     '    if role_unread:\n        record(',
     '    if False:\n        record(', "guard",
     'role-model: a missing decision file logs one unread line'),
    ("step-up: the line-start rows read the first line only, so a round line after the first line walks past",
     '            found = list(rx.finditer(brief))',
     '            found = list(rx.finditer(first))', "guard", 'floor step-up: round line after a lone quote on line two is denied'),
    ("step-up: the first-line round row is dropped, so a Round 3 of 3 behind a role word on line one asks",
     '            hit = rx.search(first)\n            found = [hit] if hit else []',
     '            hit = rx.search(first) if kind != "round" else None\n            found = [hit] if hit else []', "guard",
     'first-line marker: builder on opus with a role word before Round 3 of 3 on line one is allowed'),
    ("step-up: round 3 accepts only sonnet, so an opus reviewer is refused",
     'n == "3" and "sonnet" not in model and "opus" not in model',
     'n == "3" and "sonnet" not in model', "guard", 'floor step-up: reviewer Round 3 of 3 on opus is denied (the grant is per spawn, not standing)'),
    ("step-up: a builder round 3 on a non-opus model is no longer refused",
     'if role == "builder" and builder_third_round(prompt) and "opus" not in model:',
     'if False and role == "builder" and builder_third_round(prompt) and "opus" not in model:',
     "guard", 'floor step-up: builder Round 3 of 3 on sonnet is denied'),
    ("step-up: the builder marker drops Round, so a Round 3 of 3 builder on sonnet walks past",
     'BUILDER_MARKERS = ("round", "try")',
     'BUILDER_MARKERS = ("try",)', "guard", 'floor step-up: builder Round 3 of 3 on sonnet is denied'),
    ("step-up: the builder marker drops Try before its sunset, so a Try 3 of 3 builder on sonnet walks past",
     'BUILDER_MARKERS = ("round", "try")',
     'BUILDER_MARKERS = ("round",)', "guard", 'floor step-up: builder Try 3 of 3 on sonnet is denied'),
    ("step-up: any builder round steps up, so a Round 2 of 3 builder on sonnet is refused",
     'kind.lower() in BUILDER_MARKERS and n == "3"',
     'kind.lower() in BUILDER_MARKERS and n in "23"', "guard",
     'floor step-up: builder Round 2 of 3 on sonnet is allowed'),
    ("ceiling: the Opus spawn denial never fires, so an Opus spawn passes unrefused",
     'if "opus" not in str(tool_input.get("model") or "").lower():\n        return False',
     'if True:\n        return False', "guard", 'ceiling: Agent with model opus and no role is denied'),
    ("ceiling: a third-round line earns the standing grant for any role, so a reviewer passes unrefused",
     'if role == "builder" and builder_third_round(brief):',
     'if builder_third_round(brief):', "guard",
     "ceiling: Agent reviewer on opus with the brief 'Try 3 of 3. Finish the f' is denied"),
    ("ceiling: the Workflow scan yields no spawn, so a workflow builder on opus passes unrefused",
     'if unseen & {"model", "agentType"} or not keys.get("model"):',
     'if True:', "guard", 'role-model: Workflow builder on opus with no round line is denied under agent-model-cap'),
    ("ceiling: the Workflow scan skips a call whose brief it cannot read, so a variable-brief builder on opus passes",
     'if unseen & {"model", "agentType"} or not keys.get("model"):',
     'if prompt is None or unseen & {"model", "agentType"} or not keys.get("model"):', "guard",
     'role-model: Workflow builder on opus with a variable brief holding a Round 3 marker is denied'),
    ("ceiling: the Workflow scan skips a call with a spread in its options, so a spread-first builder on opus passes",
     'if unseen & {"model", "agentType"} or not keys.get("model"):',
     'if unseen & {"model", "agentType", "..."} or not keys.get("model"):', "guard",
     'role-model: Workflow builder on opus with a spread before its literal keys is denied'),
    ("ceiling: the Workflow scan judges a shorthand agentType as general-purpose, so a designer loop on opus is refused",
     'if "..." in unseen and "agentType" not in keys:',
     'if False:', "guard",
     'role-model: Workflow designer and design-reviewer on opus, a shorthand agentType in a loop, are allowed'),
    ("role row: a Workflow agent() call loses its agentType, so an Explore on sonnet runs as general-purpose",
     'yield {"subagent_type": keys.get("agentType"), "model": keys["model"], "prompt": prompt or "",',
     'yield {"subagent_type": None, "model": keys["model"], "prompt": prompt or "",', "guard",
     'role-model: Workflow Explore on sonnet with no marker is denied under agent-role-model'),
    ("frozen-path: the config-watch baseline store is not frozen",
     '    os.path.normcase("state"),',
     '    os.path.normcase("state_unfrozen"),', "guard", 'frozen: Write of the config-watch baseline store'),

    # ---- Rule 1c, the silent write (Decision, silent-write-leaves-a-trace). One mutant per arm:
    # the rule disabled outright, each of the two silencing detectors on its own, the two
    # in-loop carve-outs, and each subcommand set a carve-out depends on staying the shape it was
    # measured to be.
    # REQUIRED CASE NAMES, for the fifth `mutation_parts` field once it lands: each label below
    # names the silent-write test case its own red line must carry.
    #   "silent-write: the rule never denies at all"
    #     -> "silent-write: push's own quiet flag needs no redirect at all"
    #   "silent-write: the quiet-flag arm no longer fires for any subcommand"
    #     -> "silent-write: push's own quiet flag needs no redirect at all"
    #   "silent-write: a discarding redirect no longer silences anything"
    #     -> "silent-write: discarding a write command output denies, stdout alone"
    #   "silent-write: the merge --abort carve-out is gone"
    #     -> "silent-write: an abort lands nothing, so it is carved out"
    #   "silent-write: fetch joins the denied subcommands"
    #     -> "silent-write: fetch's own quiet flag is a carve-out"
    #   "silent-write: commit, tag, and cherry-pick rejoin the quiet-flag arm, the measured
    #   carve-outs undone"
    #     -> "silent-write: commit's own quiet flag is a carve-out, MEASURED 2026-09-19"
    ("silent-write: the rule never denies at all",
     '        matched, mechanism, kind = silent_write_hit(segment, segments[last] if last > number else "")\n'
     '        if matched and not in_throwaway(segments, number, cwd, ends):\n'
     '            reason = (SILENT_WRITE_REDIRECT_REASON if mechanism == "redirect"\n'
     '                      else SILENT_WRITE_QUIET_REASON)\n'
     '            refuse(tool, "deny", "silent-write",',
     '        matched, mechanism, kind = silent_write_hit(segment, segments[last] if last > number else "")\n'
     '        if False:\n'
     '            reason = (SILENT_WRITE_REDIRECT_REASON if mechanism == "redirect"\n'
     '                      else SILENT_WRITE_QUIET_REASON)\n'
     '            refuse(tool, "deny", "silent-write",', "guard",
     "silent-write: discarding a write command output denies, stdout alone"),
    ("silent-write: the quiet-flag arm no longer fires for any subcommand",
     '        if subcommand in QUIET_FLAG_SUBCOMMANDS and quiet_write(args):',
     '        if False and quiet_write(args):', "guard",
     "silent-write: push's own quiet flag needs no redirect at all"),
    ("silent-write: a discarding redirect no longer silences anything",
     '        if silenced:\n            return matched, "redirect"',
     '        if False:\n            return matched, "redirect"', "guard",
     'silent-write: discarding a write command output denies, stdout alone'),
    ("silent-write: the merge --abort carve-out is gone",
     '        if subcommand == "merge" and "--abort" in args:\n            continue',
     '        if False:\n            continue', "guard",
     'silent-write: an abort lands nothing, so it is carved out'),
    ("silent-write: every fetch is a write, not only a refspec fetch",
     '            if not fetch_moves_branch(args):\n                continue',
     '            if False:\n                continue', "guard",
     "silent-write: fetch discarding both streams is a carve-out"),
    ("silent-write: a pipe's tail is no longer followed",
     '        matched, mechanism, kind = silent_write_hit(segment, segments[last] if last > number else "")',
     '        matched, mechanism, kind = silent_write_hit(segment)', "guard",
     "silent-write pipe: cat discards the piped output"),
    ("silent-write: >&/dev/null no longer silences",
     '\\d?>>?&?)', '\\d?>>?)', "guard",
     "silent-write pipe: >&/dev/null shorthand"),
    ("silent-write: pull is no longer a write",
     'SILENT_WRITE_SUBCOMMANDS = ("commit", "push", "merge", "tag", "rebase", "cherry-pick", "pull")',
     'SILENT_WRITE_SUBCOMMANDS = ("commit", "push", "merge", "tag", "rebase", "cherry-pick")',
     "guard", "silent-write gap: pull silenced, both streams, with -C"),
    ("silent-write: a refspec fetch is no longer a write",
     '        if subcommand == "fetch":\n',
     '        if subcommand == "fetch":\n            continue\n', "guard",
     "silent-write gap: a fetch that moves a ref (refspec) silenced"),
    ("silent-write: pull and fetch leave the quiet-flag arm",
     'QUIET_FLAG_SUBCOMMANDS = ("push", "merge", "rebase", "pull", "fetch")',
     'QUIET_FLAG_SUBCOMMANDS = ("push", "merge", "rebase")', "guard",
     "silent-write gap: pull's own quiet flag"),
    ("silent-write: --dry-run no longer carves out",
     '        if read_verb(subcommand, args):\n            continue',
     '        if False:\n            continue', "guard",
     "silent-write gap, allow: a dry-run fetch into a local ref moves nothing"),
    ("silent-write: make merge is no longer a write",
     'word == "make" and "merge" in rest', 'False', "guard",
     "silent-write gap: make merge silenced by a discarded stderr"),
    ("silent-write: any make target is a write",
     'word == "make" and "merge" in rest', 'word == "make"', "guard",
     "silent-write gap, allow: make test is not a merge"),
    ("silent-write: gh pr merge is no longer a write",
     'rest[:2] == ["pr", "merge"]', 'False', "guard",
     "silent-write gap: gh pr merge silenced by a discarded stdout"),
    ("silent-write: any gh pr call is a write",
     'rest[:2] == ["pr", "merge"]', 'rest[:1] == ["pr"]', "guard",
     "silent-write gap, allow: gh pr view is a read"),
    ("silent-write: a closed descriptor no longer silences",
     '    r"|\\d?>&-(?=$|[\\s;&|])",   # a closed descriptor', '    r"|(?!)",', "guard",
     "silent-write gap: commit with stderr closed"),
    ("silent-write: commit, tag, and cherry-pick rejoin the quiet-flag arm, the measured "
     "carve-outs undone",
     'QUIET_FLAG_SUBCOMMANDS = ("push", "merge", "rebase", "pull", "fetch")',
     'QUIET_FLAG_SUBCOMMANDS = ("commit", "push", "merge", "tag", "rebase", "cherry-pick", '
     '"pull", "fetch")', "guard",
     "silent-write: commit's own quiet flag is a carve-out, MEASURED 2026-09-19"),
    # Review round 1 (lane silent-write-narrow). The two allow paths the narrowed rule added, each
    # made to allow everything. Each required case is a DENY that the mutant must lose.
    #   "silent-write: the throwaway test always passes, so a real checkout is never judged"
    #     -> "silent-write real: a discarded commit in a real checkout"
    #   "silent-write: the quote walk is quote-blind, so a redirect named in a message counts"
    #     -> "silent-write scanner: a discard named before a space inside a message is text"
    #        (SILENT_WRITE_REDIRECT needs a boundary after the null device, so the older case's
    #        `>/dev/null"` never matched and passed on a quote-blind walk; a space after the target
    #        makes only the quote walk keep this one an allow)
    ("silent-write: the throwaway test always passes, so a real checkout is never judged",
     'def in_throwaway(segments, number: int, cwd: str, ends=()) -> bool:',
     'def in_throwaway(segments, number: int, cwd: str, ends=()) -> bool:\n    return True', "guard",
     "silent-write real: a discarded commit in a real checkout"),
    ("silent-write: the quote walk is quote-blind, so a redirect named in a message counts",
     'def unquoted_at(text: str, index: int) -> bool:',
     'def unquoted_at(text: str, index: int) -> bool:\n    return True', "guard",
     "silent-write scanner: a discard named before a space inside a message is text"),

    # ---- the PostToolUse watch. These break `hooks/config_watch.py` and must be killed by
    # `hooks/test_config_watch.py`, which writes the cap for real and reads the file back.
    ("watch: never restore, only report",
     '    if not restore(path, baseline["content"]):',
     '    if False and not restore(path, baseline["content"]):', "watch", 'cp from another file'),
    ("watch: restore in silence, so a revert is never reported",
     '    if messages:\n        print(json.dumps({"systemMessage": " ".join(messages)}))',
     '    if False:\n        print(json.dumps({"systemMessage": " ".join(messages)}))', "watch", 'sed -i in place'),
    ("watch: treat every write as explained, so nothing is ever undone",
     'not (explained and explained == resolve(path, cwd))',
     'not (True)', "watch", 'mv from another file'),
    ("watch: compare the bytes, not the cap reading, so an ordinary edit is reverted too",
     'if reading != was and not (',
     'if True and not (', "watch", 'an ordinary project config edit is allowed and not reverted'),
    ("watch: watch settings.json alone, so the local file is unwatched",
     'WATCHED_NAMES = tuple(name.lstrip("/") for name in PROJECT_FROZEN_FILES)',
     'WATCHED_NAMES = ("\x2eclaude/settings.json",)', "watch", 'python3 -c writes the path'),
    ("watch: an absent file reads the same as an empty one, so a created file is not a change",
     '    if content is None:\n        return ""\n    return hashlib.sha256(content).hexdigest()',
     '    return hashlib.sha256(content or b"").hexdigest()', "watch",
     'a file goes from empty to absent before a lift, so the revert removes it, not empties it'),
    ("watch: a missing baseline is read as clear rather than recorded",
     '    if baseline is None:\n        save_baseline(path, current)',
     '    if baseline is None:\n        save_baseline(path, None)', "watch", 'a write to an unrelated file triggers nothing'),

    # ---- the expiry rule, added 2026-09-20. Nothing killed a mutant here before this block:
    # every case below is new, exercising `cap_lift_value`, `next_prior`, `expiry_problem`, and
    # the expiry tail of `judge_path` that `hooks/test_config_watch.py`'s "expiry" cases guard.
    ("watch: the 24-hour ceiling runs backwards, so only a SAFE deadline reads as too far ahead",
     '    if ahead > EXPIRY_MAX_AHEAD_HOURS * 3600:',
     '    if ahead < EXPIRY_MAX_AHEAD_HOURS * 3600:', "watch",
     'more than 24h ahead is revoked'),
    ("watch: the 24-hour bound is negated, so even a one-hour deadline reads as too far ahead",
     '    if ahead > EXPIRY_MAX_AHEAD_HOURS * 3600:',
     '    if ahead > -(EXPIRY_MAX_AHEAD_HOURS * 3600):', "watch",
     'a valid, current _agentCapUntil is NOT reverted'),
    ("watch: the passed-deadline test is inverted, so an expired deadline reads as current",
     '    if ahead < 0:\n        return "already passed"',
     '    if ahead > 0:\n        return "already passed"', "watch",
     'already passed is revoked'),
    ("watch: the missing-expiry branch is turned off, so a lift with no deadline survives",
     '    if where is None:\n        return "missing"',
     '    if False:\n        return "missing"', "watch",
     'a missing _agentCapUntil is revoked'),
    ("watch: next_prior carries the first lift's own content forward, so a later revert "
     "installs an override instead of the true baseline",
     '    if cap_lift_value(was):\n        return baseline.get("prior")',
     '    if cap_lift_value(was):\n        return baseline["content"]', "watch",
     "keeps the ORIGINAL pre-lift content as prior"),

    # ---- the 24-hour boundary itself, added 2026-09-20 (round 3). `expiry_problem` now takes
    # an injectable `clock`, so `hooks/test_config_watch.py`'s boundary cases can pin a
    # fixture's `_agentCapUntil` and the watch's own "now" to the SAME instant, and an
    # off-by-one at the exact edge is no longer invisible to this mutation test.
    ("watch: the too-far-ahead check admits its own edge, so a deadline exactly 24h out is "
     "wrongly revoked",
     '    if ahead > EXPIRY_MAX_AHEAD_HOURS * 3600:',
     '    if ahead >= EXPIRY_MAX_AHEAD_HOURS * 3600:', "watch",
     "exactly 24 hours ahead is accepted"),
    ("watch: the passed-deadline check admits its own edge, so the deadline instant itself "
     "reads as already passed",
     '    if ahead < 0:',
     '    if ahead <= 0:', "watch",
     "exactly at the deadline instant is accepted"),
    ("watch: the 24-hour ceiling is one second too loose, so a deadline one second over is "
     "wrongly accepted",
     '    if ahead > EXPIRY_MAX_AHEAD_HOURS * 3600:',
     '    if ahead > EXPIRY_MAX_AHEAD_HOURS * 3600 + 1:', "watch",
     "one second outside the 24h bound is revoked"),
    ("watch: the 24-hour ceiling is one second too tight, so a deadline exactly on it is "
     "wrongly revoked",
     '    if ahead > EXPIRY_MAX_AHEAD_HOURS * 3600:',
     '    if ahead > EXPIRY_MAX_AHEAD_HOURS * 3600 - 1:', "watch",
     "exactly 24 hours ahead is accepted"),

    # ---- the liveness oracle's alive/dead/unreadable split, added for Windows parity. Each
    # mutant here folds the new third state back into one of the other two, the exact shape of
    # the defect this whole change fixes.
    # POSIX-only mutant: it breaks `_process_start_ms`'s `ps`-exit-code arm, which
    # `_process_start_ms` never reaches on Windows (it routes straight to the ctypes Windows arm
    # instead, see guard.py's `_process_start_ms`). `process_start_ms_case` in test_guard.py
    # already skips its dead/unreadable POSIX-only sub-cases on Windows (`os.name == "nt"`), so
    # nothing on that platform can ever observe this mutation. The sixth field marks it
    # posix-only so the run loop skips it there instead of reporting a false survivor.
    ("liveness: a bad ps exit code reads as CONFIRMED dead instead of unreadable",
     '        if answer.returncode == 1 and not answer.stdout.strip():\n            return None\n'
     '        return PROCESS_START_UNREADABLE',
     '        return None',
     "guard", "liveness: process_start_ms splits alive/dead/unreadable apart", "posix"),
    ("liveness: session_is_live folds the unreadable third state back into False",
     '    if actual is PROCESS_START_UNREADABLE:\n        return None\n    if actual is None:',
     '    if actual is None:',
     "guard", "liveness: session_is_live carries True/False/None, never coercing unreadable to False"),
    ("liveness: worktree_live_session drops an unreadable record instead of answering None",
     '        live = session_is_live(record)\n        if live is True:\n            return True\n'
     '        if live is None:\n            saw_unreadable = True',
     '        if not session_is_live(record):\n            continue',
     "guard", "liveness: worktree_live_session answers None on an unreadable record under target"),
    ("liveness: the windows arm reads access-denied (error 5) as CONFIRMED dead",
     '        if error == 87:  # ERROR_INVALID_PARAMETER: no such process\n            return None',
     '        if error in (87, 5):\n            return None',
     "guard", "liveness: windows arm splits dead (error 87) from unreadable (error 5)"),
    ("liveness: the windows arm reads no-such-process (error 87) as unreadable, not dead",
     '        if error == 87:  # ERROR_INVALID_PARAMETER: no such process\n            return None\n'
     '        return PROCESS_START_UNREADABLE  # 5 (ERROR_ACCESS_DENIED) or any other code',
     '        return PROCESS_START_UNREADABLE',
     "guard", "liveness: windows arm splits dead (error 87) from unreadable (error 5)"),

    # ---- command-line argv coverage (found 2026-09-22: zero of the mutations above ever change
    # the argv of a subprocess.run call this file's guard.py itself builds). Each mutant here
    # makes one such call read the WRONG tree or the wrong pointer HEAD, never a stubbed call.
    #
    # `_git` drops `-C where`. Every internal git read this file makes (`git_dir_of`, ancestor and
    # remote-contains checks, the main/master existence probe, ...) then runs against whatever
    # directory the guard.py PROCESS happens to stand in, never `where`. `git_dir_of` is called on
    # both sides of `in_pointer_checkout` (`mine = git_dir_of(root)`, `theirs =
    # git_dir_of(pointer)`), so once the process's own ambient directory answers
    # `--absolute-git-dir` at all, `mine == theirs` holds for EVERY root, and a checkout that is
    # not the pointer checkout is judged as if it were. MEASURED against this mutant: the case
    # named below is the one where that flips the answer, from `mine != theirs` (allow) to `mine
    # == theirs` (wrongly denied).
    ("root-scope: _git drops -C, so it reads whichever tree the guard process happens to stand "
     "in, not the tree it was asked about",
     '        return _nowindow.run(\n'
     '            ["git", "-C", where, *args], capture_output=True, encoding="utf-8", errors="replace", timeout=10\n'
     '        )',
     '        return _nowindow.run(\n'
     '            ["git", *args], capture_output=True, encoding="utf-8", errors="replace", timeout=10\n'
     '        )',
     "guard", 'pointer: checkout of a branch in another checkout is allowed'),

    # `_process_start_ms`'s POSIX `ps -o lstart=` read gets the same treatment: a timeout so small
    # the read can never finish, so a live session's own liveness probe comes back
    # PROCESS_START_UNREADABLE instead of a real start time. POSIX-only: `_process_start_ms`
    # routes straight past this line on Windows (`if sys.platform.startswith("win"): return
    # _process_start_ms_windows(pid)`), and `process_start_ms_case` already skips its POSIX-only
    # sub-cases there (`os.name == "nt"`), so nothing on that platform can ever observe this
    # mutant. Marked posix-only for the same reason the bad-exit-code mutant above is.
    ("timeout: the POSIX ps liveness read cannot finish, so a live pid reads unreadable",
     '            ["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, '
     'timeout=5,',
     '            ["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, '
     'timeout=0.0001,',
     "guard", "liveness: process_start_ms splits alive/dead/unreadable apart", "posix"),

    # Added: four fail-open reads an audit found, each an `except Exception:` that answers a
    # confident value with no log line. Each mutant FORCES its try to raise, unconditionally,
    # so it exercises the fallback itself rather than merely deleting the branch the fallback
    # guards (that weaker shape is what the resolved-basename cap mutant above already does, and
    # it is why that one survived: 0 red lines). A forced raise turns the predicate off for every
    # input, so any existing case that depends on the predicate's normal answer is the proof.
    ("fail-open: is_frozen's resolve is forced to raise, so every frozen write is missed",
     '    try:\n        literal = _literal_resolved(path, cwd)\n'
     '        resolved = _resolved(path, cwd)\n'
     '        literal_root = os.path.normcase(os.path.normpath(guard_core.config_dir()))\n'
     '        resolved_root = os.path.normcase(os.path.realpath(guard_core.config_dir()))\n'
     '    except Exception:\n        return False',
     '    try:\n        raise Exception("mutant")\n        literal = _literal_resolved(path, cwd)\n'
     '        resolved = _resolved(path, cwd)\n'
     '        literal_root = os.path.normcase(os.path.normpath(guard_core.config_dir()))\n'
     '        resolved_root = os.path.normcase(os.path.realpath(guard_core.config_dir()))\n'
     '    except Exception:\n        return False',
     "guard", "frozen: Write of the global CLAUDE.md"),
    ("fail-open: is_project_config's resolve is forced to raise, so no edit is ever noted",
     '    try:\n        target = _resolved(path, cwd)\n    except Exception:\n        return False\n'
     '    posix = norm(target)',
     '    try:\n        raise Exception("mutant")\n        target = _resolved(path, cwd)\n'
     '    except Exception:\n        return False\n    posix = norm(target)',
     "guard", "log: a project config edit is allowed and noted"),
    # required is the shared "[resolve-branch proof]" tag, not a direct-basename cap case: a
    # direct-basename hit (e.g. PROJ_LOCAL's "settings.local.json") returns True on the FIRST
    # check in is_settings_file and never reaches this try at all, so no such case could ever be
    # the one that turns red here. Only a case whose literal spelling fails the direct test needs
    # the resolve this raise disables, which is exactly what the tag names (see the comment beside
    # the trailing-dot case in hooks/test_guard.py).
    ("fail-open: is_settings_file's resolve is forced to raise, degrading to a basename-only match",
     '    try:\n        return basename(_resolved(path, cwd)) in SETTINGS_BASENAMES\n'
     '    except Exception:\n        return False',
     '    try:\n        raise Exception("mutant")\n'
     '        return basename(_resolved(path, cwd)) in SETTINGS_BASENAMES\n'
     '    except Exception:\n        return False',
     "guard", "[resolve-branch proof]"),
    ("fail-open: pointer_checkout's read is forced to raise, silencing the whole pointer-head rule",
     '    try:\n        with open(os.path.join(guard_core.config_dir(), "CLAUDE.md"), encoding="utf-8-sig") '
     'as handle:\n            text = handle.read(POINTER_READ_MAX)\n    except Exception:\n'
     '        return ""',
     '    try:\n        raise Exception("mutant")\n'
     '        with open(os.path.join(guard_core.config_dir(), "CLAUDE.md"), encoding="utf-8-sig") as handle:\n'
     '            text = handle.read(POINTER_READ_MAX)\n    except Exception:\n        return ""',
     "guard", "pointer: checkout of a branch in the pointer checkout is refused"),

    # RULE 0, worktree-home. Each mutant breaks one clause of
    # docs/decisions/an-agent-outside-its-home-tree-must-stop.md. Each names the one case that kills it,
    # mostly `worktree_home_case`, the whole sequence: the bare family prefix ran every worktree-home case, 40 s a mutant.
    ("worktree-home: the first call from inside the worktree never writes the home record",
     '    if path_is_inside(cwd, candidate) is True:\n        write_agent_home(cwd, agent_id, candidate)',
     '    if path_is_inside(cwd, candidate) is False:\n        write_agent_home(cwd, agent_id, candidate)',
     "guard", "worktree-home: orchestrator, no-record"),
    ("worktree-home: the candidate worktree path drops the agent- prefix, so it never matches",
     'candidate = os.path.join(primary, ".claude", "worktrees", "agent-" + agent_id)',
     'candidate = os.path.join(primary, ".claude", "worktrees", agent_id)',
     "guard", "worktree-home: orchestrator, no-record"),
    ("worktree-home: AGENT_ID rejects a letter, so every real agent id reads as an orchestrator",
     'AGENT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")',
     'AGENT_ID = re.compile(r"^[0-9_-]{1,64}$")',
     "guard", "worktree-home: orchestrator, no-record"),
    ("worktree-home: a shell call outside its recorded home is judged as inside it",
     '        if (path_is_inside(home_cwd, home) is False\n',
     '        if (path_is_inside(home_cwd, home) is None\n',
     "guard", "worktree-home: orchestrator, no-record"),
    ("worktree-home: a write outside the recorded home, inside the clone, is allowed through",
     '            if (path_is_inside(resolved_target, home_primary) is True\n'
     '                    and path_is_inside(resolved_target, home) is False\n'
     '                    and not _own_red_run(payload, home_primary, resolved_target, False)):',
     '            if (path_is_inside(resolved_target, home_primary) is True\n'
     '                    and path_is_inside(resolved_target, home) is None\n'
     '                    and not _own_red_run(payload, home_primary, resolved_target, False)):',
     "guard", "worktree-home: a /c/ cwd inside the home is inside"),
    # The next two anchors sit in worktree_home_hit, which returns a log detail and lets judge()
    # refuse; a mutant that returns a detail for a status that allows is a deny.
    ("worktree-home: an unreadable home record denies instead of allowing",
     '    home_status, home, home_primary = agent_worktree_home(payload, home_cwd)\n'
     '    if home_status != "home":',
     '    home_status, home, home_primary = agent_worktree_home(payload, home_cwd)\n'
     '    if home_status == "unknown":\n'
     '        return "unreadable state"\n'
     '    if home_status != "home":',
     "guard", "worktree-home: orchestrator, no-record"),
    ("worktree-home: a non-isolated agent with no record is denied instead of allowed",
     '    home_status, home, home_primary = agent_worktree_home(payload, home_cwd)\n'
     '    if home_status != "home":',
     '    home_status, home, home_primary = agent_worktree_home(payload, home_cwd)\n'
     '    if home_status == "no-record":\n'
     '        return "no record"\n'
     '    if home_status != "home":',
     "guard", "worktree-home: orchestrator, no-record"),
    ("worktree-home: a relative write target drops the join onto the payload's own cwd",
     '            try:\n                resolved_target = _resolved(write_target, home_cwd)\n'
     '            except Exception:\n                resolved_target = write_target\n'
     '            if (path_is_inside(resolved_target, home_primary) is True\n'
     '                    and path_is_inside(resolved_target, home) is False\n'
     '                    and not _own_red_run(payload, home_primary, resolved_target, False)):',
     '            resolved_target = write_target\n'
     '            if (path_is_inside(resolved_target, home_primary) is True\n'
     '                    and path_is_inside(resolved_target, home) is False\n'
     '                    and not _own_red_run(payload, home_primary, resolved_target, False)):',
     "guard", "worktree-home: orchestrator, no-record"),
    ("worktree-home: the write-target loop judges only the first path field",
     '        for write_target in (write_targets(tool_input) if home_primary else ()):',
     '        for write_target in (write_targets(tool_input)[:1] if home_primary else ()):',
     "guard", "worktree-home: a later path field outside"),
    # RULE 0, other-checkout: `worktree_home_cross_checkout_case`.
    ("other-checkout: the shallowest checkout owns a path, so a nested worktree reads as the primary",
     "    return max(owners, key=len) if owners else \"\"",
     "    return min(owners, key=len) if owners else \"\"",
     "guard", "worktree-home: any session's write into another checkout"),
    ("other-checkout: a target in another checkout reads as in its own",
     "        return (bool(owner) and owner != own",
     "        return (bool(owner) and owner == own",
     "guard", "worktree-home: any session's write into another checkout"),
    ("other-checkout: the clone's common git directory is judged as the primary's own files",
     '                and path_is_inside(resolved, os.path.join(owner, ".git")) is not True\n'
     '                and not _own_red_run(',
     '                and True\n'
     '                and not _own_red_run(',
     "guard", "worktree-home: any session's write into another checkout"),
    ("other-checkout: a shell target ignores a leading cd",
     "        hit = _shell_write_hit(command, where, elsewhere, follow_cd=True, predicate_command=True)",
     "        hit = _shell_write_hit(command, where, elsewhere, follow_cd=False, predicate_command=True)",
     "guard", "worktree-home: any session's write into another checkout"),
    ("other-checkout: a quiet redirect pays the git read",
     '        writes = bool(SHELL_WRITE_HINT.search(SHELL_QUIET_REDIRECT.sub(" ", command))) or interpreter_may_write(raw)\n        moves =',
     '        writes = bool(SHELL_WRITE_HINT.search(command)) or interpreter_may_write(raw)\n        moves =',
     "guard", "worktree-home: the cross-checkout read costs"),
    ("other-checkout: an interpreter body's own write is not read",
     "        if not hit and interpreter_may_write(raw):\n            hit = interpreter_write_hit(raw, where, elsewhere)",
     "        if not hit and False:\n            hit = interpreter_write_hit(raw, where, elsewhere)",
     "guard", "worktree-home: a copy whose source is in another checkout"),
    # The `cd` act: `worktree_home_cd_*_case`.
    ("other-checkout: a cd into another checkout is not judged",
     "        if elsewhere(move, where) and not _own_red_run(",
     "        if False and not _own_red_run(",
     "guard", "worktree-home: a cd into another checkout of the clone is refused"),
    ("other-checkout: a bare cd with no write word is skipped like a read",
     "    if not moves and not writes:\n        return \"\"\n    roots =",
     "    if not writes:\n        return \"\"\n    roots =",
     "guard", "worktree-home: a cd into another checkout of the clone is refused"),
    ("other-checkout: a cd in a heredoc body reads as a move",
     "    command = _strip_heredoc_bodies_unconditionally(command)\n    if not re.search(",
     "    command = command\n    if not re.search(",
     "guard", "worktree-home: a cd in a comment, in quotes"),
    ("other-checkout: a PowerShell Set-Location is not read",
     '    if not re.search(r"\\bcd\\b|set-location|\\bpushd\\b", command, re.IGNORECASE):',
     '    if not re.search(r"\\bcd\\b|\\bpushd\\b", command, re.IGNORECASE):',
     "guard", "worktree-home: a cd into another checkout is refused when it is a relative climb"),
    ("other-checkout: the agent's recorded home is not exempt from the cd act",
     '    if status == "home" and path_is_inside(target, home) is True:\n        return True\n    if isinstance(payload, dict)',
     '    if False and path_is_inside(target, home) is True:\n        return True\n    if isinstance(payload, dict)',
     "guard", "worktree-home: the cd exemptions pass"),
    ("other-checkout: the session's recorded home is not exempt from the cd act",
     "    return bool(held) and path_is_inside(target, held) is True\n\n\n# The shell verbs",
     "    return False\n\n\n# The shell verbs",
     "guard", "worktree-home: the cd exemptions pass"),
    ("other-checkout: the agent's own red-run folder is not exempt from the cd act",
     '                and os.path.normcase(os.path.basename(folder)).startswith(',
     '                and False and os.path.normcase(os.path.basename(folder)).startswith(',
     "guard", "worktree-home: the cd exemptions pass"),
    ("other-checkout: the red-run exemption matches a prefix of the agent id",
     '                    os.path.normcase("agent-" + agent_id + "-"))):',
     '                    os.path.normcase("agent-" + agent_id))):',
     "guard", "worktree-home: an agent's cd into a sibling agent tree"),
    # The write act's exemption: `worktree_home_red_write_case`.
    ("other-checkout: a write into the agent's own red-run folder is refused",
     '                and not _own_red_run(payload, roots[0], resolved, verb in RED_RUN_ROOT_VERBS))',
     '                and True)',
     "guard", "worktree-home: an agent's write into its own red-run folder"),
    ("worktree-home: a Write into the agent's own red-run folder is refused",
     '                    and not _own_red_run(payload, home_primary, resolved_target, False)):',
     '                    and True):',
     "guard", "worktree-home: an agent's write into its own red-run folder"),
    ("other-checkout: the red-run folder's own root is exempt, so rm and mv may name it",
     "            return root_ok or folder != path",
     "            return True",
     "guard", "worktree-home: the own red-run folder's root is refused"),
    ("other-checkout: the red-run folder is anchored on the owning checkout, not the primary",
     '                and not _own_red_run(payload, roots[0], resolved, verb in RED_RUN_ROOT_VERBS))',
     '                and not _own_red_run(payload, owner, resolved, verb in RED_RUN_ROOT_VERBS))',
     "guard", "worktree-home: a red-run folder nested under another linked worktree"),
    ("other-checkout: a cd within its own checkout pays the git read",
     '                 if own_root and _checkout_root_by_stat(m) not in ("", own_root) and not _cd_home_exempt(payload, where, m)]',
     "                 if own_root and not _cd_home_exempt(payload, where, m)]",
     "guard", "worktree-home: the cross-checkout read costs"),
    ("other-checkout: a cd is judged only when the cwd has no checkout above it",
     '                 if own_root and _checkout_root_by_stat(m) not in ("", own_root) and not _cd_home_exempt(payload, where, m)]',
     "                 if not own_root and not _cd_home_exempt(payload, where, m)]",
     "guard", "worktree-home: a cd into another checkout of the clone is refused"),
    ("other-checkout: a cd into a folder in no checkout pays the read",
     '_checkout_root_by_stat(m) not in ("", own_root) and not _cd_home_exempt',
     '_checkout_root_by_stat(m) != own_root and not _cd_home_exempt',
     "guard", "worktree-home: the cross-checkout read costs"),
    ("other-checkout: an absolute cd after an untracked move is skipped",
     "        folder = shell_abs(named, at)\n",
     "        folder = shell_abs(named, at) if at else None\n",
     "guard", "worktree-home: an absolute cd into another checkout is refused after an untracked move"),
    ("other-checkout: a pushd is not read as a move",
     '_segment_cd_target(tokens, ("cd", "set-location", "pushd"))',
     '_segment_cd_target(tokens, ("cd", "set-location"))',
     "guard", "worktree-home: pushd into another checkout"),
    ("other-checkout: a command with only a pushd is skipped before it is read",
     '    if not re.search(r"\\bcd\\b|set-location|\\bpushd\\b", command, re.IGNORECASE):',
     '    if not re.search(r"\\bcd\\b|set-location", command, re.IGNORECASE):',
     "guard", "worktree-home: pushd into another checkout"),
    # RULE 0, other-checkout, the session's own scratchpad: `worktree_home_scratchpad_case`.
    ("other-checkout: a worktree in the session's own scratchpad is refused",
     "        if not has_agent and under_session_scratchpad(resolved, session_id):\n            return False\n",
     "        if not has_agent and False:\n            return False\n",
     "guard", "a write into a worktree in the session's own scratchpad"),
    ("other-checkout: a worktree in any session's scratchpad passes",
     "        if not has_agent and under_session_scratchpad(resolved, session_id):",
     "        if not has_agent and in_any_session_scratchpad(resolved):",
     "guard", "a write into a worktree in the session's own scratchpad"),
    ("other-checkout: an agent call passes into the session's own scratchpad worktree",
     "        if not has_agent and under_session_scratchpad(resolved, session_id):",
     "        if under_session_scratchpad(resolved, session_id):",
     "guard", "a write into a worktree in the session's own scratchpad"),
    # RULE 0, other-checkout, the separate-clone act: `_same_repo` and the stranded arm of `_clone_scope`.
    ("other-checkout: no two clones read as the same repo, so a separate clone of this repo passes",
     "    urls = (_clone_origin(common), _clone_origin(other))",
     "    return False\n    urls = (_clone_origin(common), _clone_origin(other))",
     "guard", "a Write into a separate clone of the same repo is refused"),
    ("other-checkout: every two clones read as the same repo, so a clone of a different repo is refused",
     "    urls = (_clone_origin(common), _clone_origin(other))",
     "    return True\n    urls = (_clone_origin(common), _clone_origin(other))",
     "guard", "a Write into a clone of a different repo is allowed"),
    ("other-checkout: a cwd is never stranded, so its relative write into a separate clone passes",
     "        if common and _separate_clone(own, [top], common):",
     "        if False and _separate_clone(own, [top], common):",
     "guard", "a cwd stranded in a separate clone refuses a relative Write"),
    ("other-checkout: a git verb in a shell call is not read, so a git -C commit into a separate clone passes",
     '    return "git" in command and any(',
     '    return False and "git" in command and any(',
     "guard", "a git -C commit into a separate clone of the same repo is refused"),
    # RULE 0, session-home: the `session_home_*_case` log checks.
    ("session-home: an agent call writes the session's record",
     '        return\n    where = _expanded(cwd, "") if cwd and os.name == "nt" else cwd\n    primary, lane = session_home_place(where)\n    record = session_home_record(payload, primary) if primary else ""',
     # An agent call from an agent-named tree is also shielded by session_home_agent_tree further
     # down, so dropping the agent_id return alone changes nothing the suite's case can see: the
     # mutant survives. The replacement switches both layers off, which is the rule broken: an
     # agent call writes the session's record.
     '        globals()["session_home_agent_tree"] = lambda _lane: False\n    where = _expanded(cwd, "") if cwd and os.name == "nt" else cwd\n    primary, lane = session_home_place(where)\n    record = session_home_record(payload, primary) if primary else ""',
     "guard", "session-home: an agent call writes and rewrites no session record"),
    ("session-home: ExitWorktree leaves the session's record",
     '        if tool == "ExitWorktree":',
     '        if tool == "ExitWorktree" and False:',
     "guard", "session-home: the session's ExitWorktree clears its record"),
    ("session-home: a standing recorded folder is read as gone",
     '    if not home or os.path.isdir(home):',
     '    if not home:',
     "guard", "session-home: a session whose worktree folder stands"),
    ("session-home: a missing record refuses the write",
     '    if not home or os.path.isdir(home):',
     '    if os.path.isdir(home):',
     "guard", "session-home: records are per session"),
    ("session-home: the clone's .git is judged as the primary's own files",
     '                and path_is_inside(resolved, clone_git) is not True\n',
     '\n',
     "guard", "session-home: while lost, the clone's .git"),
    ("session-home: the refusal does not name the EnterWorktree tool",
     'Remedy: call the EnterWorktree tool first.',
     'Remedy: open a new worktree first.',
     "guard", "session-home: a session whose worktree is gone is refused"),
    ("session-home: no override lifts the refusal",
     '            or worktree_home_hit(payload, tool, tool_input, cwd)):\n        return True',
     '            or worktree_home_hit(payload, tool, tool_input, cwd)\n            or session_home_hit(payload, tool, tool_input, cwd)):\n        return True',
     "guard", "session-home: an owner override lifts the refusal"),
    ("session-home: the primary is found with a clone read",
     '    return os.path.join(primary, ".git", SESSION_HOME_DIR, sid)',
     '    git_common_dir(primary)\n    return os.path.join(primary, ".git", SESSION_HOME_DIR, sid)',
     "guard", "session-home: the record and the refusal add no git spawn"),
    ("session-home: an agent's write from primary refused",
     '    if not isinstance(payload, dict) or payload.get("agent_id"):\n        return ""\n    if tool in WRITE_TOOLS:\n',
     '    if not isinstance(payload, dict):\n        return ""\n    if tool in WRITE_TOOLS:\n',
     "guard", "session-home: a non-isolated agent, with no record of its own"),
    ("session-home: an ExitWorktree from the primary clears the record",
     '            if held and os.path.isdir(held):\n                os.remove(record)',
     '            if held:\n                os.remove(record)',
     "guard", "session-home: an ExitWorktree from the primary checkout leaves"),
    ("session-home: an ExitWorktree from the primary keeps a live record",
     '            if held and os.path.isdir(held):\n                os.remove(record)',
     '            if lane and held and os.path.isdir(held):\n                os.remove(record)',
     "guard", "session-home: an ExitWorktree from the primary clears a record that names a live"),
    ("session-home: a call inside an agent's worktree writes the session's record",
     '        if not lane or held == lane or session_home_agent_tree(lane):',
     '        if not lane or held == lane:',
     "guard", "session-home: a top-level call inside an agent's worktree writes no session"),
    ("session-home: a git verb whose folder is a variable is judged as the primary",
     '        folder = dir_before_segment(segments, number, where, ends)\n        tokens = segment_tokens(segment)',
     '        folder = dir_before_segment(segments, number, where, ends) or where\n        tokens = segment_tokens(segment)',
     "guard", "session-home: while lost, a commit whose folder is a shell variable"),
    ("session-home: the gone home path reads as another worktree's folder",
     '                     or path_is_inside(resolved, home) is True))',
     '                     or False))',
     "guard", "session-home: a write to the lost home path is refused"),
    ("session-home: a git verb in the primary is not read",
     '        verb = session_home_git_hit(command, where, in_primary)',
     '        verb = ""',
     "guard", "session-home: while lost, git verbs"),
    ("session-home: a git -C into a live worktree is judged as the primary",
     '            folder = None if _unexpanded(named) else shell_abs(named, folder)\n        if not folder:\n            continue\n        for verb, args in verbs:',
     '            folder = where\n        if not folder:\n            continue\n        for verb, args in verbs:',
     "guard", "session-home: while lost, git verbs"),
    # RULE scratchpad-owner: the `spo_case_*` log checks.
    ("scratchpad-owner: a run of another agent's file is never refused",
     '        if writer and writer != agent:\n            return "agent %s runs',
     '        if False and writer != agent:\n            return "agent %s runs',
     "guard", "scratchpad-owner: 1 agent B runs agent A's script with python3"),
    ("scratchpad-owner: an agent's run of its own file is refused too",
     '        if writer and writer != agent:\n            return "agent %s runs',
     '        if writer:\n            return "agent %s runs',
     "guard", "scratchpad-owner: 5 agent A runs its own script"),
    ("scratchpad-owner: a call with no agent_id is judged",
     '    if not agent or not session or (SCRATCHPAD_WORD not in command and SCRATCHPAD_WORD not in cwd):',
     '    if not session or (SCRATCHPAD_WORD not in command and SCRATCHPAD_WORD not in cwd):',
     "guard", "scratchpad-owner: 7 a top-level call with no agent_id"),
    ("scratchpad-owner: a read of the file reads as a run",
     '        if _RUNNER(basename(word)):',
     '        if True:',
     "guard", "scratchpad-owner: 8 agent B reads agent A's script with cat"),
    ("scratchpad-owner: the heredoc body is read as run text",
     '    segments = split_segments(_resolve_vars(strip_heredoc_bodies(command)), ends)\n    for number, segment in enumerate(segments):\n        tokens = segment_tokens(segment)\n        index = resolve_command(tokens) if tokens else None',
     '    segments = split_segments(_resolve_vars(command), ends)\n    for number, segment in enumerate(segments):\n        tokens = segment_tokens(segment)\n        index = resolve_command(tokens) if tokens else None',
     "guard", "scratchpad-owner: extra, a run in a heredoc body is text"),
    ("scratchpad-owner: a relative path ignores the cd ahead of it",
     '        full = shell_abs(script, dir_before_segment(segments, number, cwd, ends))',
     '        full = shell_abs(script, cwd)',
     "guard", "scratchpad-owner: 2 agent B runs agent A's script after cd"),
    ("scratchpad-owner: a Write family target is not listed as a write",
     '                if SCRATCHPAD_WORD in full and under_session_scratchpad(full, session):\n                    files.append(full)',
     '                if SCRATCHPAD_WORD in full and under_session_scratchpad(full, session) and False:\n                    files.append(full)',
     "guard", "scratchpad-owner: 1 agent B runs agent A's script with python3"),
    ("scratchpad-owner: a passing write records no writer",
     '    record_writers()\n',
     '    pass\n',
     "guard", "scratchpad-owner: 3 agent B runs agent A's script through bash"),
    ("scratchpad-owner: a write over another agent's file is never refused",
     '        if writer and writer != agent and not taken:',
     '        if False and writer != agent and not taken:',
     "guard", "scratchpad-owner: overwrite 1 agent B's Write over agent A's file"),
    ("scratchpad-owner: an agent's rewrite of its own file is refused too",
     '        if writer and writer != agent and not taken:',
     '        if writer and not taken:',
     "guard", "scratchpad-owner: overwrite 4 agent A rewrites its own file"),
    ("scratchpad-owner: a shell write target is not listed as a write",
     '                if full and SCRATCHPAD_WORD in full and full not in files and under_session_scratchpad(full, session):',
     '                if full and SCRATCHPAD_WORD in full and full not in files and under_session_scratchpad(full, session) and "x" == "y":',
     "guard", "scratchpad-owner: overwrite 2 agent B's shell redirect over agent A's file"),
    ("scratchpad-owner: an interpreter's value flag is read as the script",
     '            at = workflow_script_index(args)   # past the interpreter\'s flags and their values',
     '            at = 0 if args else None   # past the interpreter\'s flags and their values',
     "guard", "scratchpad-owner: flag 1 agent B runs agent A's script past python3 -W ignore"),
    ("scratchpad-owner: a lone - before the script position is read as a script",
     '            script = args[at] if at is not None and "-" not in args[:at] else ""',
     '            script = args[at] if at is not None else ""',
     "guard", "scratchpad-owner: stdin 1 agent B's python3 - with a heredoc"),
    ("scratchpad-owner: a shell variable in a run path is not read",
     '    segments = split_segments(_resolve_vars(strip_heredoc_bodies(command)), ends)',
     '    segments = split_segments(strip_heredoc_bodies(command), ends)',
     "guard", "scratchpad-owner: variable 1 agent B runs agent A's script by a shell variable path"),
    ("scratchpad-owner: a refused overwrite moves the record",
     '    if taken:\n        # A refused write',
     '    record_writers()\n    if taken:\n        # A refused write',
     "guard", "scratchpad-owner: record 1 a refused overwrite leaves the record with agent A"),
    ("scratchpad-owner: a top-level write keeps the record",
     '            scratchpad_clear_writer(full, session)\n        return',
     '            pass\n        return',
     "guard", "scratchpad-owner: top-level 1 a call with no agent_id overwrites agent A's file with Write"),
    ("scratchpad-owner: an rm or mv records its writer",
     '            if full not in removed:\n                scratchpad_record_writer(full, session, agent)',
     '            if True:\n                scratchpad_record_writer(full, session, agent)',
     "guard", "scratchpad-owner: approved 2 agent B's rm the owner approves keeps the record with agent A"),
    ("scratchpad-owner: an overwrite the owner lifts leaves the old record",
     ', on_lift=record_writers)',
     ')',
     "guard", "scratchpad-owner: approved 1 agent B's overwrite the owner approves moves the record"),
    ("write-target deny loop judges only the first path field, so a later field's deny is skipped",
     '    for target in targets:\n        # 0b.',
     '    for target in targets[:1]:\n        # 0b.',
     "guard", "gap-control: NotebookEdit main session, an ordinary file_path beside notebook_path"),
    ("settings-cap ask loop judges only the first path field",
     '    for target in targets:\n        # 8. The agent model cap.',
     '    for target in targets[:1]:\n        # 8. The agent model cap.',
     "guard", "gap: NotebookEdit, settings cap in notebook_path beside file_path=docs/x.ipynb still asks"),

    # ---- the three git acts: context for a write, the merge guard, and cite by id. Each mutant breaks
    # one arm of one clause, and the required case is the one that must read that break.
    ("merge-checks: a pending head merges",
     '        if verdict != "green":\n            refuse(tool, "deny", "merge-checks", merge_check_reason(verdict, detail),\n                   "gh pr merge "',
     '        if verdict == "red":\n            refuse(tool, "deny", "merge-checks", merge_check_reason(verdict, detail),\n                   "gh pr merge "',
     "guard", 'merge-checks: a pending check denies'),
    ("merge-checks: an unread head merges",
     '        if verdict != "green":\n            refuse(tool, "deny", "merge-checks", merge_check_reason(verdict, detail),\n                   "gh pr merge "',
     '        if verdict not in ("green", "unknown"):\n            refuse(tool, "deny", "merge-checks", merge_check_reason(verdict, detail),\n                   "gh pr merge "',
     "guard", 'merge-checks: a gh that answers nothing readable is unknown'),
    ("merge-checks: the host merge tool is never guarded",
     '        if verdict != "green":\n            refuse(tool, "deny", "merge-checks", merge_check_reason(verdict, detail),\n                   "merge tool "',
     '        if False:\n            refuse(tool, "deny", "merge-checks", merge_check_reason(verdict, detail),\n                   "merge tool "',
     "guard", 'merge-checks: the merge tool of the host denies on a pending head'),
    ("merge-checks: --auto skips the guard",
     '        if merging is None:\n            continue\n        verdict, detail = merge_check(',
     '        if merging is None or "--auto" in segment:\n            continue\n        verdict, detail = merge_check(',
     "guard", 'merge-checks: --auto is guarded like any merge'),
    ("merge-checks: a head that reports nothing is green in a repo with workflows",
     'nothing_is_green=not has_workflows(where), batch_ignore=ignore)', 'nothing_is_green=True, batch_ignore=ignore)', "guard",
     'merge-checks: a head that reports nothing yet is not settled'),
    ("merge-checks: a repo with no workflow folder reads as having workflows",
     '    except FileNotFoundError:\n        return False', '    except FileNotFoundError:\n        return True',
     "guard", 'merge-checks: a head that reports nothing may merge when the repo has no workflows'),
    ("merge-checks: the read runs in the guard's own folder, not the command's",
     'merge_check(merging[0], merging[1], cite_where)', 'merge_check(merging[0], merging[1], cwd)',
     "guard", 'merge-checks: a cd names the repo the read runs in'),
    ("merge-checks: the host tool's read runs in the guard's own folder",
     'repo, cwd)\n        if verdict != "green":\n            refuse(tool, "deny", "merge-checks", merge_check_reason(verdict, detail),\n                   "merge tool "',
     'repo, "")\n        if verdict != "green":\n            refuse(tool, "deny", "merge-checks", merge_check_reason(verdict, detail),\n                   "merge tool "',
     "guard", 'merge-checks: the host merge tool reads the repo of the call'),
    ("merge-checks: the read gets no folder",
     'host = module.Host(required=pinned_required(where) or "protection", repo=repo or None, cwd=where or None)',
     'host = module.Host(required=pinned_required(where) or "protection", repo=repo or None)', "guard",
     'merge-checks: a cd names the repo the read runs in'),
    ("merge-checks: help is guarded like a merge",
     '    if "-h" in args or "--help" in args:\n        return None   # help merges nothing',
     '    if False:\n        return None', "guard", 'merge-checks: help merges nothing'),
    ("merge-checks: an unloadable merge tool passes",
     'return "unknown", "the merge tool\'s check reader could not be loaded"',
     'return "green", ""', "guard", 'merge-checks: a merge tool that cannot load'),
    ("merge-checks: the repo is never passed to the read",
     'host = module.Host(required=pinned_required(where) or "protection", repo=repo or None, cwd=where or None)',
     'host = module.Host(required=pinned_required(where) or "protection", cwd=where or None)', "guard",
     'merge-checks: the pull request and repo of the call are the ones read'),
    ("merge-checks: the pull request is never passed to the read",
     'return host.head_read(selector, nothing_is_green',
     'return host.head_read("", nothing_is_green', "guard",
     'merge-checks: the pull request and repo of the call are the ones read'),
    ("merge-checks: the long repo flag goes unread",
     '        elif taken:',
     '        elif taken and not arg.startswith("--repo="):', "guard", 'merge-checks: the long repo flag names the repo too'),
    ("merge-checks: a body flag's value is read as the pull request",
     'MERGE_VALUE_FLAGS = {"-R", "--repo", "-b", "--body",',
     'MERGE_VALUE_FLAGS = {"-R", "--repo", "--body",', "guard",
     'merge-checks: a flag value is no pull request'),
    ("merge-checks: any word that spells gh is the command word",
     '    index = resolve_command(tokens)\n    if index is None or basename(tokens[index]) not in ("gh", "gh.exe"):\n        return None\n    rest, root, group = tokens[index + 1:], [], []',
     '    index = next((i for i, t in enumerate(tokens) if basename(t) in ("gh", "gh.exe")), None)\n    if index is None:\n        return None\n    rest, root, group = tokens[index + 1:], [], []',
     "guard", 'merge-checks: the words of a merge in an echo are no merge'),
    ("merge-checks: the read has no time limit",
     '            module.SH_TIMEOUT = MERGE_READ_TIMEOUT',
     '            module.SH_TIMEOUT = None', "guard",
     'merge-checks: a gh slower than the guard waits is unknown'),
    ("bare-merge: a stamp with a merge block reads as not using the merge tool",
     '"merge" in config', 'False', "guard",
     'bare-merge: gh pr merge in a repo with a merge block asks'),
    ("cite-by-id: the debts folder is no record folder",
     '"|".join(map(re.escape, names))', 're.escape(names[0])', "guard",
     'cite-by-id: a -am cluster denies'),
    ("cite-by-id: the record folders are read from nowhere",
     "                found.append(folder)\n", "                pass\n",
     "guard", 'cite-by-id: a commit -m denies'),
    ("cite-by-id: a path deep in a URL or a subfolder is a record path",
     'r"(?:^|(?<=[\\s\\"\'`(\\[<,;=@*]))(?:\\./)?(?:"', 'r"(?:[\\w.:/-]*/)?(?:"', "guard",
     'cite-by-id: a URL that holds a record path is allowed'),
    ("cite-by-id: a dot-slash path is no record path",
     'r"(?:^|(?<=[\\s\\"\'`(\\[<,;=@*]))(?:\\./)?(?:"', 'r"(?:^|(?<=[\\s\\"\'`(\\[<,;=@*]))(?:"',
     "guard", 'cite-by-id: a dot-slash record path denies'),
    ("cite-by-id: an unread folder list denies nothing but says nothing",
     '        record("Bash", "noted", "subject-unread", "cite-by-id: record folders unread")\n',
     '', "guard", 'merge-checks: a merge tool that cannot load'),
    ("cite-by-id: any file of a record folder is a record",
     '+ r")/[\\w.-]+\\.md\\b")', '+ r")/[\\w.-]+")', "guard",
     'cite-by-id: a non-record file of a record folder is allowed'),
    ("cite-by-id: a backslash path is not read as a path",
     'found = pattern.search(norm(text))', 'found = pattern.search(text)', "guard",
     'cite-by-id: a backslash path denies'),
    ("cite-by-id: a heredoc body is never read",
     '    if "<<" in segment:\n        texts.extend(', '    if False:\n        texts.extend(',
     "guard", 'cite-by-id: a heredoc inside -m denies'),
    ("cite-by-id: every heredoc of the command is the message",
     '        texts.extend(found[before:before + count])',
     '        texts.extend(found)',
     "guard", 'lane-by-slug: a cat heredoc naming N16, then a clean commit heredoc is allowed'),
    ("cite-by-id: a Drops-lines trailer is excused in every paragraph",
     '        paras = re.split(r"\\n\\s*\\n", "\\n\\n".join(texts).strip())',
     '        paras = ["", "\\n\\n".join(texts)]',
     "guard", 'cite-by-id: a Drops-lines line in a middle paragraph is denied'),
    ("powershell: a backslash is eaten as under Bash",
     '    if is_powershell(segment):\n        segment = segment.replace("\\\\", "\\\\\\\\")',
     '    if False:\n        segment = segment.replace("\\\\", "\\\\\\\\")', "guard",
     'powershell: a backslash path survives tokenizing'),
    ("cite-by-id: an environment file is opened as a message file",
     '        if is_env(name):\n            continue', '        if False:\n            continue', "guard",
     'env: a message allowance does not leak, git commit -F .env'),
    ("cite-by-id: an unreadable message file passes",
     '            return call is not None, texts, name   # unknown, never a pass', '            pass',
     "guard", 'cite-by-id: a message file that cannot be read'),
    ("cite-by-id: a message file is never read",
     '    for name in files:\n        if is_env(name):', '    for name in []:\n        if is_env(name):', "guard",
     'cite-by-id: a file named by -F denies'),
    ("cite-by-id: a PR body file flag goes unread",
     'MESSAGE_FILE_FLAGS = {"--file", "--body-file"}',
     'MESSAGE_FILE_FLAGS = {"--file"}', "guard", 'cite-by-id: a PR body file denies'),
    ("cite-by-id: a short cluster ending in m goes unread",
     '"commit": dict(m="text", ', '"commit": dict(', "guard",
     'cite-by-id: a -am cluster denies'),
    ("cite-by-id: an attached -m value goes unread",
     '                    value = (rest[1:] if rest.startswith("=") else rest) if rest else None',
     '                    value = None', "guard", 'cite-by-id: an attached -m value denies'),
    ("cite-by-id: the long message flag goes unread",
     'MESSAGE_VALUE_FLAGS = {"--message", "--body"}',
     'MESSAGE_VALUE_FLAGS = {"--body"}', "guard", 'cite-by-id: the long --message= denies'),
    ("cite-by-id: a PR edit is no message",
     'acts = (["create"], ["edit"]) +', 'acts = (["create"],) +', "guard",
     'cite-by-id: a PR body file denies'),
    ("cite-by-id: every git call with a message flag is a commit",
     '        if call[0] != "commit":\n            return None', '        if False:\n            return None',
     "guard", 'cite-by-id: a note message, which this rule does not read'),
    # Builders do not edit tests, test-authors edit only tests. Each mutant breaks one clause; the
    # named case must go red.
    ("role-diff: every caller reads as no role",
     '    role = role.strip().lower()\n    return role if role in (BUILDER_ROLE, AUTHOR_ROLE, WRITER_ROLE, DESIGNER_ROLE) else ""',
     '    return ""', "guard", "builder-diff: the diff check refuses a builder's test change and logs a test-author's diff"),
    ("designer-scope: an unread layout allows every path",
     '    if folder is None or ".." in parts:\n        return False',
     '    if folder is None:\n        return True\n    if ".." in parts:\n        return False',
     "guard", "designer-scope: an unread layout allows no path"),
    ("role-diff: SubagentStop is never judged",
     '    if payload.get("hook_event_name") == "SubagentStop":\n        judge_stop(payload)',
     '    if False:\n        judge_stop(payload)', "guard", "builder-diff: the diff check refuses a builder's test change and logs a test-author's diff"),
    ("role-diff: commit and push are never judged",
     '                if subcommand in ("commit", "push"):', '                if False:', "guard", "builder-diff: the diff check refuses a builder's test change and logs a test-author's diff"),
    ("role-diff: push is not judged, only commit",
     '                if subcommand in ("commit", "push"):', '                if subcommand in ("commit",):',
     "guard", "builder-diff: the diff check refuses a builder's test change and logs a test-author's diff"),
    ("role-diff: the builder's own commits are never read",
     'ENTRY_OWN = re.compile(r"^commit(?: \\((?:initial|amend|merge)\\))?:")',
     'ENTRY_OWN = re.compile(r"^never-seen:")', "guard",
     "builder-refuse: a reset to a commit that holds the builder's own test edit is denied at push"),
    ("role-diff: a merge commit is judged against its first parent, not git's own merge",
     '            merged = merge_tree(root, *parents)',
     '            merged = (parents[0], ())', "guard",
     "builder-refuse: a merge of main with a product-file conflict, while main changed a test file, is allowed at push and stop"),
    ("role-diff: a merge in progress is judged against HEAD, not git's own merge",
     '        merged = merge_tree(root, "HEAD", merging.stdout.strip())', '        merged = ("HEAD", ())', "guard",
     "builder-refuse: a merge of main with a product-file conflict, while main changed a test file, is allowed at commit"),
    ("role-diff: a rebase pick is read as the builder's resolved replay",
     'REBASE_PLAIN_STEPS = ("start", "finish", "abort", "pick", "reword", "edit")',
     'REBASE_PLAIN_STEPS = ("start", "finish", "abort", "reword", "edit")', "guard",
     "builder-refuse: a rebase onto main where a test-author's commit and main change the same test file in different hunks"),
    ("role-diff: a replay in progress is refused as the builder's own work",
     '    changes.append((old, None, paths, NOTED if replaying else OWN, conflicts))',
     '    changes.append((old, None, paths, OWN, conflicts))', "guard",
     "builder-refuse: a builder's cherry-pick of a test-author's commit with --no-commit is allowed at commit"),
    ("role-diff: a write of the upstream side after a rebase is logged only",
     '            if not builder or kind == OWN:',
     '            if not builder or (kind == OWN and rel not in {r for _o, _n, p, k in changes if k == KEPT for r in p}):',
     "guard",
     "builder-refuse: after a rebase, main's bytes written back over a test file are denied at commit"),
    ("role-diff: untracked files are never read",
     '    return tracked + sorted(fresh)', '    return tracked', "guard",
     "builder-diff: the diff check refuses a builder's test change and logs a test-author's diff"),
    ("role-diff: an own commit HEAD no longer holds is still judged",
     '        if sha in lost:\n            continue', '        if False:\n            continue', "guard",
     "builder-refuse: a builder's conflicted merge of a test file, which it then resets away, is allowed and logs no builder-diff line"),
    ("role-diff: every path a builder changes offends",
     '            bad = any(is_builder_test_rel(n) for n in names) or (', '            bad = True or (', "guard",
     "builder-refuse: a builder's conflicted merge of a product file, both sides changed it, is allowed and logs no builder-diff line"),
    ("role-diff: a test-author's change is judged as a builder's",
     '        elif role == AUTHOR_ROLE:\n            bad = not all(author_path_ok(n) for n in names)',
     '        elif False:\n            bad = not all(author_path_ok(n) for n in names)', "guard",
     "builder-refuse: a test-author's ordinary commit of a test file is never refused and logs no author-diff line"),
    ("role-diff: a test-author's conflicted path is judged like any other",
     '        if role == AUTHOR_ROLE and all(norm(n) in merge_route_paths(conflicts) for n in names):', '        if False:', "guard",
     "builder-refuse: a test-author's merge commit that resolves a conflicted test file and a conflicted product file"),
    ("test-author: the write tool refuses a product path its merge left conflicted",
     '            if where and norm(rel).lstrip("/") in merge_route_paths(merge_conflicts(where) or ()):', '            if False:', "guard",
     "test-author: Edit of a product file its merge conflicts is allowed"),
    ("test-author: the merge route is given to a merge with no test path conflicted",
     '    if not any(is_test_rel(path) or is_mutation_test_rel(path) for path in conflicts):', '    if False:', "guard",
     "test-author: Edit of a product file its merge conflicts, with no test path conflicted, is refused"),
    ("test-author: a merge whose only test path is a mutation test is given no merge route",
     '    if not any(is_test_rel(path) or is_mutation_test_rel(path) for path in conflicts):',
     '    if not any(is_test_rel(path) for path in conflicts):', "guard",
     "test-author: Edit of a product file its merge conflicts, beside a conflicted hooks/mutate_guard.py, is allowed"),
    ("role-diff: a test-author's commit gives the merge route to a merge with no test path conflicted",
     '        if role == AUTHOR_ROLE and all(norm(n) in merge_route_paths(conflicts) for n in names):',
     '        if role == AUTHOR_ROLE and all(norm(n) in conflicts for n in names):', "guard",
     "builder-refuse: a test-author's merge commit that resolves a product-only conflict logs author-diff"),
    ("test-author: the merge route covers a conflicted workflow, test config or manifest",
     '    return [path for path in conflicts if not (is_workflow_rel(path) or author_path_ok(path))]',
     '    return list(conflicts)', "guard",
     "test-author: Edit of a workflow that changes a non-test step in a mixed merge is refused"),
    ("role-diff: a flag on a line that calls a runner is not read",
     'any(TEST_RUNNER_CONTEXT.search(near) for near', 'any(False for near', "guard", "builder-test: addopts --deselect added to pytest.ini is refused"),
    ("role-diff: --deselect no longer disables tests",
     'r"--(?:deselect|ignore|', 'r"--(?:never-seen|ignore|', "guard", "builder-test: addopts --deselect added to pytest.ini is refused"),
    ("role-diff: self-test files are no test paths",
     '|(?:.*[-_]selftest|selftest_.*)\\.(?!md$).+"', '"', "guard",
     "builder-test: Edit of self-test file scripts/foo-selftest.py is refused"),
    ("role-diff: conftest.py is no test path",
     '|conftest\\.py"', '|never-seen\\.py"', "guard", "builder-test: Edit of src/conftest.py is refused"),
    ("role-diff: no directory part makes a test path",
     'TEST_DIRS = {"tests", "test", "__tests__", "spec", "testdata", "__snapshots__", "test_support"}',
     'TEST_DIRS = set()', "guard", "builder-test: Edit of tests/helper.py is refused"),
    ("role-diff: Swift test basenames are plural only (cries wolf)",
     'SWIFT_TEST = re.compile(r"^\\w+Tests\\.swift$")', 'SWIFT_TEST = re.compile(r"^\\w+Tests?\\.swift$")',
     "guard", "swift-test: Edit of non-test App/LoginTest.swift is allowed"),
    ("role-diff: Xcode test dirs are PascalCase (cries wolf)",
     'XCODE_TEST_DIR = re.compile(r"^[A-Z]\\w*Tests$")', 'XCODE_TEST_DIR = re.compile(r"^.+Tests$")',
     "guard", "swift-test: Edit of non-test native/abTests/x.swift is allowed"),
    ("role-diff: Java test names match without case (cries wolf)",
     'JAVA_TEST = re.compile(r"^\\w*Tests?\\.java$")', 'JAVA_TEST = re.compile(r"^\\w*Tests?\\.java$", re.I)',
     "guard", "builder-test: Edit of src/Contest.java is allowed"),
    ("role-diff: the spec basename shape is dropped",
     '|.*\\.spec\\..+|conftest', '|conftest', "guard", "builder-test: Edit of web/a.spec.js is refused"),
    ("role-diff: any basename containing test is a test (cries wolf)",
     'bool(TEST_BASENAME.match(parts[-1].lower()))', '("test" in parts[-1].lower())', "guard",
     "builder-test: Edit of src/contest.py is allowed"),
    ("role-diff: the repo root is ignored, so a clone under tests is all tests (cries wolf)",
     '        if os.path.exists(os.path.join(parent, ".git")):\n            return full[len(parent):]',
     '        if False:\n            return full[len(parent):]', "guard",
     "builder-test: a repo that lives under a tests folder is not all test files"),
    ("role-diff: the write tools are never judged",
     '    if role and tool in WRITE_TOOLS:', '    if False:', "guard",
     "builder-test: Write of a test file is refused"),
    ("role-diff: a disabling line added to a config file is not read by the write tool",
     '    if is_test_config_rel(rel) and any(', '    if False and any(', "guard",
     "builder-test: addopts --deselect added to pytest.ini is refused"),
    ("role-diff: a stop from a main checkout is not logged",
     'record("SubagentStop", "noted", "role-diff-main-checkout", where)', 'pass', "guard",
     "role-diff: every unjudged stop is logged"),
    ("role-diff: a main checkout is judged as an agent's tree",
     '    if is_worktree(where) is False:', '    if False:', "guard", "role-diff: every unjudged stop is logged"),
    ("role-diff: the given-up stop is not logged",
     'record("SubagentStop", "noted", "role-diff-unresolved", found or "unread")', 'pass', "guard",
     "role-diff: every unjudged stop is logged"),
    ("test-author: the scope is never enforced in the diff",
     '            bad = not all(author_path_ok(n) for n in names)', '            bad = False', "guard", "builder-diff: the diff check refuses a builder's test change and logs a test-author's diff"),
    ("test-author: the write tool lets any path through",
     '                return ""\n        return target\n    if role == WRITER_ROLE:', '                return ""\n        return ""\n    if role == WRITER_ROLE:', "guard",
     "test-author: Edit of product code is refused"),
    ("test-author: test config is not its own",
     '    return (is_test_rel(rel) or is_test_config_rel(rel) or basename(rel) in AUTHOR_BASENAMES',
     '    return (is_test_rel(rel) or basename(rel) in AUTHOR_BASENAMES', "guard", "test-author: Edit of pytest.ini is allowed"),
    ("test-author: a workflow test step is not allowed",
     '            if pairs and all(workflow_test_steps_only(o, n) for o, n in pairs):\n                return ""',
     '            if False:\n                return ""', "guard",
     "test-author: a Linux test step inserted after a lint step is allowed"),
    ("test-author: a quoted command substitution in a test run is allowed",
     'or "$(" in value or "`" in value:', ':', "guard",
     "test-author: a quoted $( substitution in a test run in checks.yml is refused"),
    ("builder: a continue-on-error or if: false under a test step is allowed",
     "return (workflow_disables_tests(old_text, new_text) or workflow_disables_step(old_text, new_text)",
     "return (workflow_disables_tests(old_text, new_text) or False", "guard",
     "builder-test: continue-on-error added under a test step is refused"),
    ("builder: dropping a test run from a workflow is allowed",
     "            or workflow_drops_tests(old_text, new_text))", "            or False)", "guard",
     "builder-test: a whole test step deleted from checks.yml is refused"),
    ("builder: a disable flag on a test-runner line is not read",
     "                    TEST_RUNNER_CONTEXT.search(line)\n                    or workflow_command_tests(",
     "                    False\n                    or workflow_command_tests(", "guard",
     "builder-test: a pytest --deselect step added to checks.yml is refused"),
    ("builder: a lint tool given a test folder reads as a test run",
     "            args = tokens if runner else tokens[:1]", "            args = tokens", "guard",
     "builder-test: a ruff --ignore line on tests/ added to checks.yml is allowed"),
    ("builder: an interpreter flag hides the test path a run line runs",
     '    while index < len(args) and args[index].startswith("-"):', "    while False:", "guard",
     "builder-test: python3 -u in place of python3 on a test run is allowed"),
    ("test-author: a mutation test is not its own",
     '            or is_mutation_test_rel(rel))', '            or False)', "guard",
     "test-author: Edit of mutation test hooks/mutate_guard.py is allowed"),
    ("builder-test: is_builder_test_rel drops the mutation tests",
     '    return is_test_rel(rel) or is_mutation_test_rel(rel)', '    return is_test_rel(rel)', "guard",
     "builder-test: Edit of mutation test hooks/mutate_guard.py is refused"),
    ("builder-test: is_mutation_test_rel stops folding case",
     '    return norm(rel).lstrip("/").lower() in AUTHOR_MUTATION_TESTS', '    return norm(rel).lstrip("/") in AUTHOR_MUTATION_TESTS', "guard",
     "builder-test: Edit of HOOKS/mutate_guard.py is refused (case folds)"),
    ("role-diff: the builder reason drops the remedy",
     '"report. The orchestrator assigns it to a test-author."', '"report."', "guard",
     "builder-test: Write of a test file is refused"),
    ("role-diff: the author reason drops the remedy",
     '"report. The orchestrator assigns it to a builder."', '"report."', "guard",
     "test-author: Edit of product code is refused"),
    # Added with the three ported shell traps (narrated tail, ln over a directory,
    # push HEAD to a stray name). Each mutant undoes one predicate the trap's cases pin.
    ('narrate: never refuse a narrating command piped to tail',
     '        refuse(tool, "deny", "live-stream", NARRATED_TAIL_REASON, matched)',
     '        pass',
     "guard", 'narrate: merge --confirm piped to tail'),
    ('narrate: a merge preview is refused as if it were a wait',
     '    if not tokens or "--confirm" not in tokens:',
     '    if not tokens:',
     "guard", 'narrate: a merge preview is not a wait'),
    ('narrate: tee is counted as a truncating filter',
     'TRUNCATING_FILTERS = ("tail", "head")',
     'TRUNCATING_FILTERS = ("tail", "head", "tee")',
     "guard", 'narrate: tee keeps every byte'),
    ('narrate: every command is on the roster',
     '    if word in NARRATING_COMMANDS:\n        return word\n',
     '    if word:\n        return word\n',
     "guard", 'narrate: --confirm on a command off the roster'),
    ('narrate: a script run by path is no longer read',
     'NARRATING_SCRIPT_TAILS = ("merge/merge.py", "merge/launch.py")',
     'NARRATING_SCRIPT_TAILS = ("nothing/at-all",)',
     "guard", 'narrate: the launcher script run through python'),
    ('ln-over-directory: never refuse',
     '        refuse(tool, "deny", "ln-over-directory", LN_DESCENDS_REASON, matched)',
     '        pass',
     "guard", 'ln: -s over a real directory'),
    ('ln-over-directory: -n no longer clears a link to a directory',
     '    if os.path.islink(full) and no_deref:\n        return ""\n',
     '    if False:\n        return ""\n',
     "guard", 'ln: -sfn replaces a link to a directory'),
    ('ln-over-directory: -f is read as clearing a link to a directory',
     '            no_deref = no_deref or "n" in token[1:] or "h" in token[1:]',
     '            no_deref = no_deref or "n" in token[1:] or "h" in token[1:] or "f" in token[1:]',
     "guard", 'ln: -sf over a link to a directory'),
    ('ln-over-directory: any existing path is refused, not only a directory',
     '    if not os.path.isdir(full):\n        return ""\n    if os.path.islink',
     '    if not os.path.lexists(full):\n        return ""\n    if os.path.islink',
     "guard", 'ln: -sf over a link to a file'),
    ('ln-over-directory: a trailing slash no longer says the destination is a directory',
     '    if dest.endswith(("/", "\\\\")) or "$" in dest or "*" in dest:',
     '    if "$" in dest or "*" in dest:',
     "guard", 'ln: a trailing slash'),
    ('ln-over-directory: a hard link is read as symbolic',
     '    if not symbolic or len(operands) != 2:',
     '    if len(operands) != 2:',
     "guard", 'ln: a hard link over a directory name'),
    ('linked-node-modules: never refuse',
     '            refuse(tool, "deny", "linked-node-modules", LINKED_NM_REASON, matched)',
     '            pass',
     "guard", 'linked-nm: refuse npm ci (Bash) in a linked folder'),
    ('linked-node-modules: an install is refused in a real folder, not a link',
     '        if subcommand and not NPM_NO_CHANGE.intersection(words) and is_link(',
     '        if subcommand and not NPM_NO_CHANGE.intersection(words) and not is_link(',
     "guard", 'linked-nm: npm ci (Bash) in a real folder is allowed'),
    ('linked-node-modules: the working folder is never read as linked',
     '                os.path.join(npm_prefix_flag(words, where) or npm_prefix(where), "node_modules")):',
     '                os.path.join(npm_prefix_flag(words, where) or "never-a-folder", "node_modules")):',
     "guard", 'linked-nm: refuse npm install (Bash) in a linked folder'),
    ('npm_prefix_flag: the --prefix value is never read, so the working folder decides',
     '    return os.path.join(where, value) if value else ""',
     '    return ""',
     "guard", 'linked-nm: npm ci --prefix a real folder, run from a linked folder, is allowed'),
    ('linked-node-modules: a dry run is refused like an install',
     'NPM_NO_CHANGE = {"-g", "--global", "--location=global", "--help", "-h", "--dry-run"}',
     'NPM_NO_CHANGE = {"-g", "--global", "--location=global", "--help", "-h"}',
     "guard", 'linked-nm: npm ci --dry-run (Bash) in a linked folder is allowed'),
    ('linked-node-modules: a global install is refused like a local one',
     'NPM_NO_CHANGE = {"-g", "--global", "--location=global", "--help", "-h", "--dry-run"}',
     'NPM_NO_CHANGE = {"--help", "-h", "--dry-run"}',
     "guard", 'linked-nm: npm i -g x (Bash) in a linked folder is allowed'),
    ('linked-node-modules: a value flag before the subcommand is read as the subcommand',
     '"--logs-dir", "-C", "-L",',
     '"--logs-dir", "--never-a-flag", "-L",',
     "guard", 'linked-nm: npm -C . ls (Bash) in a linked folder is allowed'),
    ('linked-node-modules: a subcommand off the read-only list is allowed',
     '                if word not in NPM_READ_ONLY or (word == "audit"',
     '                if False or (word == "audit"',
     "guard", 'linked-nm: refuse npm prune (Bash) in a linked folder'),
    ('linked-node-modules: audit fix is read as a plain audit',
     '(word == "audit" and "fix" in words[at + 1:])',
     'False',
     "guard", 'linked-nm: refuse npm audit fix (Bash) in a linked folder'),
    ('linked-node-modules: run is missing from the read-only list',
     '    "run", "rum", "urn", "sbom",',
     '    "rum", "urn", "sbom",',
     "guard", 'linked-nm: npm run build (Bash) in a linked folder is allowed'),
    ('linked-node-modules: a recursive delete inside a linked node_modules goes unread',
     '        if _nm_recursive_delete(args) and any(',
     '        if False and any(',
     "guard", 'linked-nm: refuse rm -rf node_modules/ (Bash) in a linked folder'),
    ('linked-node-modules: a delete inside a real node_modules is refused',
     '(folder := _nm_inside(arg, where)) and is_link(os.path.join(folder, "node_modules"))',
     '(folder := _nm_inside(arg, where)) and not is_link(os.path.join(folder, "node_modules"))',
     "guard", 'linked-nm: rm -rf node_modules/ (Bash) in a real folder is allowed'),
    ('linked-node-modules: the walk never starts, so a sub folder is read as its own prefix',
     '    folder = where\n    while True:',
     '    folder = where\n    return where\n    while True:',
     "guard", 'linked-nm: walk: refuse npm ci two levels below a linked root'),
    ('linked-node-modules: the walk passes a folder with its own package.json',
     '("package.json", "node_modules")',
     '("node_modules",)',
     "guard", 'linked-nm: walk: npm install in a sub folder with its own package.json and no node_modules is allowed'),
    ('linked-node-modules: the walk passes a folder with a real node_modules',
     '("package.json", "node_modules")',
     '("package.json",)',
     "guard", 'linked-nm: walk: npm ci in a sub folder with a real node_modules and no package.json is allowed'),
    ('linked-node-modules: a workspace flag on npm version is read as a plain version',
     'version_in_workspace):',
     'False):',
     "guard", 'linked-nm: refuse npm version patch -w a (Bash) in a linked folder'),
    ('linked-node-modules: a dry run is exempt again for rebuild, rb and edit',
     'NPM_DRY_RUN_WRITERS = {"rebuild", "rb", "edit"}',
     'NPM_DRY_RUN_WRITERS = set()',
     "guard", 'linked-nm: refuse npm rebuild --dry-run (Bash) in a linked folder'),
    # ---- the always-silent stub. A hook whose main() exits 0 with no output passes every
    # "nothing printed" case on its own. Each suite pairs that silence with a known-bad input in
    # the same case (`known-bad pair`), and these mutants are the stub itself.
    ("decision watch: main() is an always-silent stub",
     'def main():\n    guard._force_utf8_streams()',
     'def main():\n    sys.exit(0)\n    guard._force_utf8_streams()', "decision",
     "main_ordinary_turn: known-bad pair"),
    ("decision watch: stop_hook_active is true for every input",
     '    if hook.get("stop_hook_active"):\n        sys.exit(0)  # this Stop firing', '    if True:\n        sys.exit(0)  # this Stop firing', "decision",
     "main_stop_hook_active: known-bad pair"),
    ("ruling home: main() is an always-silent stub",
     'def main():\n    try:\n        hook = json.load(sys.stdin)',
     'def main():\n    sys.exit(0)\n    try:\n        hook = json.load(sys.stdin)', "ruling",
     "main_silent: known-bad pair"),
    ("ruling home: every failure stands the hook down, git present or not",
     '    try:\n        reason = run(hook)\n    except Exception:',
     '    try:\n        reason = run(hook)\n        raise RuntimeError("mutant")\n    except Exception:', "ruling",
     "main_missing_git: known-bad pair"),
    ('rm-var-unguarded: never refuse',
     '        refuse(tool, "deny", "rm-var-unguarded", rm_var_reason(hits), "; ".join(hits))',
     '        pass',
     "guard", 'rm-var: a loop deletes under an unguarded variable'),
    # ---- substitution reads (debt guard-substitution-in-token): a command inside `$( )` is judged.
    ("substitution: judge_shell reads only the outer text, so a reset inside a dollar paren passes",
     '    texts = [stripped, *substitution_commands(raw, stripped)]\n',
     '    texts = [stripped]\n',
     "guard", "substitution: shared tree, an assignment from a dollar paren denies"),
    # ---- ask-step-hidden (debt ask-step-hidden-in-script): the push loop reads wrapped scripts through _push_calls.
    ("ask-step-hidden: the push loop skips _push_calls, so a force push inside bash -c passes",
     '        for args, where, overrides in _push_calls(segment, stripped, cwd):\n            verdict = push_verdict(',
     '        for args, where, overrides in ([] if tool else _push_calls(segment, stripped, cwd)):\n            verdict = push_verdict(',
     "guard", "ask-step-hidden: a force push inside bash -c denies"),
    ("push-calls-substitution: _push_calls reads only the wrapped script, so a force push inside a bash -c substitution passes",
     '            for each in (stripped, *substitution_commands(text, stripped)):\n                for part in split_segments(each):\n                    yield from _push_calls(',
     '            for each in (stripped,):\n                for part in split_segments(each):\n                    yield from _push_calls(',
     "guard", "ask-step-hidden: a force push in a bash -c substitution denies"),
    ("ask-step-hidden: the trailing paren or backtick stays on the path word, so a subshell write hides its path",
     '                word = _typed(word.rstrip(")`") or word, word)   # keeps the PowerShell type of the word\n',
     '                word = _typed(word, word)   # keeps the PowerShell type of the word\n',
     "guard", "ask-step-hidden: a cap write in a subshell with a leading space asks"),
    # ---- hand-made-worktree (decision lanes-start-in-tool-worktrees): one mutant per branch.
    ("hand-made-worktree: the judge_shell loop never asks, so no hand-made tree is refused",
     '            matched = hand_made_worktree_hit(segments, number, cwd, ends, payload)\n',
     '            matched = ""\n',
     "guard", 'hand-made worktree: a relative sibling path from the primary is refused'),
    ("hand-made-worktree: the inside-the-home-folder test is inverted",
     'if path_is_inside(tree, os.path.join(primary, ".claude", "worktrees")) is not True:',
     'if path_is_inside(tree, os.path.join(primary, ".claude", "worktrees")) is True:',
     "guard", 'hand-made worktree: a relative sibling path from the primary is refused'),
    ("hand-made-worktree: the inside-the-home-folder pass is dropped, so a home tree is refused",
     'if path_is_inside(tree, os.path.join(primary, ".claude", "worktrees")) is not True:',
     'if True:',
     "guard", "hand-made worktree: an absolute path under the primary's home folder passes"),
    ("hand-made-worktree: a call with no agent_id is judged as an agent, so lane9 is refused",
     'if status in ("none", "unknown") or _own_red_run(payload, primary, flat):',
     'if status == "unknown" or _own_red_run(payload, primary, tree):',
     "guard", "hand-made worktree: with no agent_id, the lane9 add from the primary passes"),
    ("hand-made-worktree: an agent's own red-run folder is no longer passed",
     'if status in ("none", "unknown") or _own_red_run(payload, primary, flat):',
     'if status in ("none", "unknown"):',
     "guard", "hand-made worktree: an agent adds its own red-run folder, as the red run does, passes"),
    ("hand-made-worktree: an agent's own recorded home is no longer passed",
     '    return "" if own else target\n',
     '    return target\n',
     "guard", "hand-made worktree: an agent adds its own recorded home tree passes"),
    ("hand-made-worktree: an agent may add any tree inside the folder",
     '    return "" if own else target\n',
     '    return ""\n',
     "guard", "hand-made worktree: an agent adds a non-agent folder, lane9, under the primary's folder is refused"),
    ("hand-made-worktree: a tree nested inside the agent's own home is passed",
     '    own = path_is_inside(flat, home) is True and path_is_inside(home, flat) is True\n',
     '    own = path_is_inside(flat, home) is True\n',
     "guard", "hand-made worktree: an agent adds a tree nested inside its own recorded home is refused"),
    ("hand-made-worktree: an agent with no home record is read as unknown, so it passes",
     'if status in ("none", "unknown") or _own_red_run(payload, primary, flat):',
     'if status in ("none", "unknown", "no-record") or _own_red_run(payload, primary, flat):',
     "guard", "hand-made worktree: an agent with no home record adds lane9 under the primary's folder is refused"),
    ("hand-made-worktree: an unreadable home record no longer allows",
     'if status in ("none", "unknown") or _own_red_run(payload, primary, flat):',
     'if status == "none" or _own_red_run(payload, primary, flat):',
     "guard", "hand-made worktree: an agent whose home record cannot be read adds lane9"),
    ("hand-made-worktree: a gone cwd is not asked again from the readable repo",
     '        status, home, _ = agent_worktree_home(payload, where)\n',
     '        status, home, _ = agent_worktree_home(payload, drive_form_cwd(cwd))\n',
     "guard", "hand-made worktree: an agent whose home folder is gone adds lane9 after a cd"),
    ("hand-made-worktree: the tree is not flattened, so a dot-dot walk out of the red-run folder passes",
     '    flat = os.path.normpath(tree)',
     '    flat = tree',
     "guard", "hand-made worktree: an agent walks out of its own red-run folder with .. to add lane9"),
    ("hand-made-worktree: an agent_type with no agent_id reads as no agent",
     'if status == "none" and isinstance(payload, dict) and payload.get("agent_type"):',
     'if False:',
     "guard", "hand-made worktree: a call that names an agent_type and no agent_id adds lane9"),
    ("hand-made-worktree: an option's value is taken as the new tree path",
     '        elif arg in HAND_MADE_VALUE_OPTIONS:\n            cursor += 1\n',
     '        elif arg in HAND_MADE_VALUE_OPTIONS:\n            pass\n',
     "guard", 'hand-made worktree: -b and a path under the home folder passes'),
    ("hand-made-worktree: a double dash no longer ends the options",
     '        if ended or not arg.startswith("-") or arg == "-":',
     '        if False or not arg.startswith("-") or arg == "-":',
     "guard", 'hand-made worktree: a dash-led name after a double dash is still a path'),
    ("hand-made-worktree: the run folder ignores cd and reads the payload cwd only",
     '    where = dir_before_segment(segments, number, cwd, ends)\n    named = _segment_git_c_target(tokens)\n    if named is not None:\n        where = None if _unexpanded(named) else shell_abs(named, where)\n    if not where:',
     '    where = cwd\n    named = _segment_git_c_target(tokens)\n    if named is not None:\n        where = None if _unexpanded(named) else shell_abs(named, where)\n    if not where:',
     "guard", 'hand-made worktree: cd into a non-temp primary'),
    ("hand-made-worktree: the run folder ignores -C",
     '    named = _segment_git_c_target(tokens)\n    if named is not None:\n        where = None if _unexpanded(named) else shell_abs(named, where)\n    if not where:',
     '    if not where:',
     "guard", 'hand-made worktree: -C reaches the primary from elsewhere'),
    ("hand-made-worktree: the temp exemption judges the target, not the repo",
     '    if path_is_inside(primary, tempfile.gettempdir()):\n        return ""\n    if _unexpanded(target):',
     '    if path_is_inside(shell_abs(target, where) or "", tempfile.gettempdir()):\n        return ""\n    if _unexpanded(target):',
     "guard", 'hand-made worktree: cd into a non-temp primary'),
    ("hand-made-worktree: the temp exemption is dropped, so a throwaway repo is refused",
     '    if path_is_inside(primary, tempfile.gettempdir()):\n        return ""\n    if _unexpanded(target):',
     '    if _unexpanded(target):',
     "guard", "hand-made worktree: a repo under the guard's temp folder is a throwaway"),
    ("hand-made-worktree: a variable is no longer read from the command's earlier assignment",
     '    for subcommand, args in git_calls(read):',
     '    for subcommand, args in git_calls(segments[number]):',
     "guard", 'hand-made worktree: a variable set in the same command to a path under the home folder'),
    ("hand-made-worktree: the variable read keeps the first segment, not the one judged",
     'mark.join(segments[:number + 1])).split(mark)[-1]',
     'mark.join(segments[:number + 1])).split(mark)[0]',
     "guard", 'hand-made worktree: a scratch path set in the same command, added from the non-temp primary as $S, is refused'),
    # The read in guard_core.py's _variable_text (the walk's cd and assignment reads). Its anchor is unique to that site.
    ("hand-made-worktree: a cd variable read in guard_core keeps the first assignment, not the value judged",
     'given + text).split(mark)[-1]',
     'given + text).split(mark)[0]',
     "guard", 'hand-made worktree: a variable folder, cd "$R", then a tree outside home is refused'),
    ("hand-made-worktree: a variable the command does not set is allowed",
     '        return target   # a variable the command does not set: the shell\'s value is unknown\n',
     '        return ""\n',
     "guard", 'hand-made worktree: a variable this command does not set'),
    ("hand-made-worktree: a -C variable is no longer read from the command's earlier assignment",
     '    tokens = segment_tokens(read)\n',
     '    tokens = segment_tokens(segments[number])\n',
     "guard", 'hand-made worktree: a -C variable set in the same command'),
    ("hand-made-worktree: an unset variable target is refused before the throwaway check",
     '    if path_is_inside(primary, tempfile.gettempdir()):\n        return ""\n    if _unexpanded(target):\n        return target',
     '    if _unexpanded(target):\n        return target\n    if path_is_inside(primary, tempfile.gettempdir()):\n        return ""\n    if False:\n        return target',
     "guard", "hand-made worktree: a repo under the guard's temp folder runs a variable target no command sets"),
    ("hand-made-worktree: every -C that held a variable is refused, though the command set it",
     '    named = _segment_git_c_target(tokens)\n    if named is not None:\n        where = None if _unexpanded(named) else shell_abs(named, where)\n    if not where:\n        return ""\n    primary = primary_checkout(where)',
     '    named = _segment_git_c_target(tokens)\n    if _unexpanded(_segment_git_c_target(segment_tokens(segments[number])) or ""):\n        return target\n    if named is not None:\n        where = None if _unexpanded(named) else shell_abs(named, where)\n    if not where:\n        return ""\n    primary = primary_checkout(where)',
     "guard", 'hand-made worktree: a -C variable set in the same command to the primary, with a home-folder target'),
    ("hand-made-worktree: the early exit is dropped, so every segment re-resolves its variables",
     '    if "worktree" not in segments[number]:\n        return ""',
     '    if False:\n        return ""',
     "guard", "rm-var: 4000 bindings and 4000 flagged deletes scale linearly in CPU"),
    ("hand-made-worktree: the help flag no longer ends the read",
     '        elif arg in ("-h", "--help"):\n            return None\n',
     '        elif arg in ("-hh",):\n            return None\n',
     "guard", 'hand-made worktree: a help flag after the path still only reads'),
    ("hand-made-worktree: the pointer remedy names worktree add again",
     'Call the EnterWorktree tool to make one ',
     'Run git worktree add -b x to make one ',
     "guard", 'hand-made worktree: the pointer remedy names EnterWorktree'),
    ("pointer-head: the remedy drops the git -C hint for an agent already in its own worktree",
     '"If you already have a worktree, run `git -C <that worktree> ...`, because your shell\'s "',
     '"Because your shell\'s "',
     "guard", 'hand-made worktree: the pointer remedy names EnterWorktree'),
    ("hand-made-worktree: the refusal text no longer says to report which layer refused",
     'stop and report to the owner which layer refused and its exact ',
     'stop and report to the owner the exact ',
     "guard", 'hand-made worktree: the refusal text'),
    # THE ONE-ACT OVERRIDE (hooks/override.py). A spend that skips the claim lifts a second act.
    ("override: a one-act override is spent with no claim, so a late reader is let through",
     '    if not _claim(path, raw):\n        return None\n',
     '',
     "override", 'override: a call that read a one-act override before it was spent is refused'),
    ("override: the claim marker names the session, not the override, so a new override is refused",
     'marker = "%s.%s.claim" % (path, hashlib.sha256(raw).hexdigest()[:32])',
     'marker = "%s.claim" % path',
     "override", 'override: a call that read a one-act override before it was spent is refused'),
    # THE OPUS OVERRIDE (hooks/override.py). It lifts only the Opus spawn ask, of its own role, until it ends.
    ("opus override: the scope check is dropped, so the Opus override lifts any refusal",
     'if rule == OPUS_RULE and spawn_role is not None else None',
     'if True else None',
     "override", 'opus override: every other refusal and ask stands under it'),
    ("opus override: the role check is dropped, so a role override lifts every role",
     '    if at >= until or (role is not None and role != str(spawn_role).lower()):',
     '    if at >= until:',
     "override", 'opus override: `opus builders 2h` lifts only builder spawns'),
    ("opus override: the end instant still lifts",
     '    if at >= until or (role is not None',
     '    if at > until or (role is not None',
     "override", 'opus override: `opus 2h` lets an Opus spawn through'),
    # THE VETO AND THE TAKE (decision owner-override). never_lifted names the acts an override may not lift, and
    # override.take reads the one-act override. A mutant that lifts a never-lifted act, or reads no override, must go red.
    ("never-lifted: a shell kill of pid 1 is liftable, so an override reaches it",
     'or any(t and kills_group_pid(t) for t in map(segment_tokens, split_segments(stripped)))',
     'or False',
     "guard", 'override: a kill of pid 1 ends with the no-override line'),
    ("never-lifted: a write of the frozen config settings is liftable, so an override reaches it",
     'if (is_frozen(target, cwd) or (role and role_write_hit',
     'if (False or (role and role_write_hit',
     "guard", 'override: a write of the config settings ends with the no-override line'),
    ("never-lifted: the no-model refusal is liftable, so an owner override lifts it",
     'or role_model_check(tool, tool_input)[1].startswith(ROLE_NO_MODEL_MATCH)',
     'or False',
     "guard", 'role-model: the no-model refusal stays under an owner override, and spends none'),
    ("take: a one-act override is never read, so no refusal is lifted",
     'return _take_override(session_id, agent_id, at) or opus or step',
     'return opus or step',
     "override", 'override: a one-act override lets through'),
    ("veto: refuse() takes an override even when the veto holds, so a never-lifted act is lifted",
     '    vetoed = _vetoed()\n',
     '    vetoed = False\n',
     "guard", 'override: a kill of pid 0, 1 or -1 stays refused under a one-act override'),
    # THE OVERRIDE LINE (step c80, hooks/override.py and refuse() in hooks/guard_core.py). A refusal ends with
    # the line the owner types, or with the sentence that no override lifts it.
    ("override line: a vetoed refusal offers an override that cannot lift it",
     'line = override.NO_OVERRIDE if vetoed else override.offer(rule, spawn_role, _override_who[1])',
     'line = override.offer(rule, spawn_role, _override_who[1])',
     "guard", 'override: a kill of pid 1 ends with the no-override line'),
    ("override line: an agent's refusal offers the one-act word that does not reach an agent",
     'else override.offer(rule, spawn_role, _override_who[1])',
     'else override.offer(rule, spawn_role)',
     "guard", 'override: a refusal an override lifts ends with the agent override line'),
    ("override line: the line leads the reason, so the fix is not first",
     'reason = reason.rstrip() + " " + line',
     'reason = line + " " + reason',
     "guard", 'override: a refusal an override lifts ends with the main override line'),
    ("override line: the missing-module deny stops saying that no override lifts it",
     '"then retry. No override lifts this refusal, because the failed guard cannot check "\n'
     '                    "the acts that no override lifts. "\n'
     '                    "(decision guard-hooks-fail-closed, a guard with a missing part refuses the call)")}}))',
     '"then retry.")}}))',
     "guard", 'override: a missing-module deny says that no override lifts it'),
    ("override line: the Opus spawn ask no longer names the Opus word",
     'if rule == OPUS_RULE and spawn_role is not None:\n        role = opus_role(str(spawn_role))',
     'if False:\n        role = opus_role(str(spawn_role))',
     "override", 'override: a refusal an override lifts ends with the opus override line'),
    ("override line: an agent's refusal offers the main session's line",
     '    if agent_id:\n        return ("To allow this act',
     '    if False:\n        return ("To allow this act',
     "override", 'override: a refusal an override lifts ends with the agent override line'),
    # THE CALL JUDGE (step c85, hooks/call_judge.py). Its refusal goes through refuse(); an Explore spawn
    # on a model that is neither Sonnet nor Opus is a model guard that no override lifts.
    ("call judge: the veto is dropped, so an override lifts the Explore model guard",
     'guard_core.set_override_veto(lambda: vetoed)',
     'guard_core.set_override_veto(lambda: False)',
     "calljudge", 'explore: a flagged spawn on haiku stays denied under a timed override'),
    ("call judge: an Opus Explore spawn is vetoed too",
     'return "sonnet" not in model and "opus" not in model',
     'return "sonnet" not in model',
     "calljudge", 'explore: an Explore spawn on opus is not vetoed'),
    ("call judge: the agent id is not passed, so a one-act override lifts an agent's call",
     'guard_core.set_override_context(payload.get("session_id"), payload.get("agent_id"))',
     'guard_core.set_override_context(payload.get("session_id"), None)',
     "calljudge", "agent: one-act override, an agent's call leaves the deny"),
    ("call judge: the question judge runs on Sonnet",
     'QUESTION_MODEL, QUESTION_TIMEOUT = "claude-opus-5-5", 60',
     'QUESTION_MODEL, QUESTION_TIMEOUT = "claude-sonnet-5-5", 60',
     "calljudge", 'question: one model call, claude-opus-5-5'),

    # ---- lane-repo-tag. Each mutant breaks one clause of the lane repo tag check, or of git_reads.github_repo and
    # origin_slug, the reading of a checkout's GitHub repo that the rule shares with the roadmap build.
    ("lane-repo-tag: the rule never fires",
     '    if repo_tag_hit_tags:\n        refuse(tool, "deny", "lane-repo-tag"',
     '    if False and repo_tag_hit_tags:\n        refuse(tool, "deny", "lane-repo-tag"',
     "guard", "lane-repo-tag: lane tag with no repo tag is denied"),
    ("lane-repo-tag: a tag in other case no longer matches",
     '        if repo and repo_tag_names(tag, repo):',
     '        if repo and tag == REPO_TAG + repo:',
     "guard", "lane-repo-tag: origin repo tag in other case is allowed"),
    ("lane-repo-tag: the owner is the first path segment, so a proxy origin names the wrong repo",
     '    owner, name = segments[-2], segments[-1]\n    if name.endswith(".git"):',
     '    owner, name = segments[0], segments[-1]\n    if name.endswith(".git"):',
     "guard", "lane-repo-tag: proxy-host origin, origin repo tag is allowed"),
    ("lane-repo-tag: a .git suffix stays on the repo name",
     '    if name.endswith(".git"):\n        name = name[:-4]\n    return "%s/%s"',
     '    if False:\n        name = name[:-4]\n    return "%s/%s"',
     "guard", "lane-repo-tag: origin with a .git suffix, origin repo tag is allowed"),
    ("lane-repo-tag: the no-origin fallback also applies when the origin is read",
     '        if not repo and isinstance(tag, str) and tag.startswith(REPO_TAG) and FULL_REPO_TAG.fullmatch(',
     '        if isinstance(tag, str) and tag.startswith(REPO_TAG) and FULL_REPO_TAG.fullmatch(',
     "guard", "lane-repo-tag: origin with a .git suffix, another repo's tag is denied"),
    ("lane-repo-tag: with no readable origin, every lane is allowed (the no-origin fallback is dropped)",
     '    # A tag is read as the roadmap reads it (repo_tag_names): exact prefix, no strip, owner/name without case.\n    for tag in tags:',
     '    if not repo:\n        return "", None\n    for tag in tags:',
     "guard", "lane-repo-tag: a checkout with no origin, short repo form is denied"),
    ("lane-repo-tag: the tag is stripped before the exact read, so a trailing space passes",
     '        if repo and repo_tag_names(tag, repo):',
     '        if repo and repo_tag_names(tag.strip(), repo):',
     "guard", "lane-repo-tag: origin repo tag with a trailing space is denied"),
    ("lane-repo-tag: a local path origin is not parsed, so it reads as no origin",
     '    else:\n        path = url\n',
     '    else:\n        path = url.partition(":")[2]\n',
     "guard", "lane-repo-tag: a local-path origin, another repo's tag is denied"),
    ("lane-repo-tag: the scp arm is dropped, so an scp origin reads its host into the path",
     '    elif ":" in url.partition("/")[0]:\n        path = url.partition(":")[2]\n',
     '    elif False:\n        path = url.partition(":")[2]\n',
     "guard", "lane-repo-tag: an scp origin, origin repo tag is allowed"),
    ("lane-repo-tag: a URL with a scheme reads its host and port, not its path, so it reads as no origin",
     '    if "://" in url:\n        path = url.split("://", 1)[1].partition("/")[2]\n',
     '    if "://" in url:\n        path = url.split("://", 1)[1].partition("/")[0]\n',
     "guard", "lane-repo-tag: an ssh origin with a port, another repo's tag is denied"),
    ("lane-repo-tag: the extras file is never read, so the origin decides",
     '    if extras is _READ_EXTRAS:\n        try:',
     '    if False:\n        try:',
     "guard", "lane-repo-tag: an extras file names the GitHub repo, its tag is allowed"),
    ("lane-repo-tag: the origin is read before the extras, so it wins over them",
     '    if isinstance(extras, dict) and isinstance(extras.get("github"), str):\n        return extras["github"]\n    done = _git(',
     '    if False:\n        return extras["github"]\n    done = _git(',
     "guard", "lane-repo-tag: an extras file names the GitHub repo, the origin's path is no repo tag"),
    ("lane-repo-tag: the deny reason names no repo",
     'LANE_REPO_TAG_REASON % (REPO_TAG + (lane_repo or "<owner>/<name>"))',
     'LANE_REPO_TAG_REASON % (REPO_TAG + "<owner>/<name>")',
     "guard", "lane-repo-tag: a denied lane names the expected repo tag in its reason"),
    # ---- lane-start-settings. Each mutant breaks one clause of the rule in guard.py: the model and source_url
    # reads, the empty and whitespace-only reads, the lane tag condition, or the refusal itself.
    ("lane-start-settings: the model is not checked, so a lane with no model is allowed",
     'missing = [k for k in ("model", "source_url")',
     'missing = [k for k in ("source_url",)',
     "guard", "lane-start-settings: lane tag with no model is denied"),
    ("lane-start-settings: the source_url is not checked, so a lane with no source_url is allowed",
     'missing = [k for k in ("model", "source_url")',
     'missing = [k for k in ("model",)',
     "guard", "lane-start-settings: lane tag with no source_url is denied"),
    ("lane-start-settings: an empty string counts as present",
     'if not (isinstance(tool_input.get(k), str) and tool_input[k].strip())]',
     'if not (isinstance(tool_input.get(k), str) and (tool_input[k].strip() or tool_input[k] == ""))]',
     "guard", "lane-start-settings: lane tag with an empty model is denied"),
    ("lane-start-settings: a whitespace-only value counts as present, so the strip is dropped",
     'if not (isinstance(tool_input.get(k), str) and tool_input[k].strip())]',
     'if not (isinstance(tool_input.get(k), str) and tool_input[k])]',
     "guard", "lane-start-settings: lane tag with a whitespace-only model is denied"),
    ("lane-start-settings: the lane tag condition is dropped, so every create_session with no model or source_url is refused",
     '    if not is_lane_create_session(tool, tool_input):\n'
     '        return ""\n'
     '    missing = [k for k in ("model", "source_url")',
     '    missing = [k for k in ("model", "source_url")',
     "guard", "lane-start-settings: coordinator call with no model and no source_url is allowed"),
    ("lane-start-settings: the rule never refuses, so a lane with no model or source_url is allowed",
     '    if lane_missing:\n        refuse(tool, "deny", "lane-start-settings"',
     '    if False and lane_missing:\n        refuse(tool, "deny", "lane-start-settings"',
     "guard", "lane-start-settings: lane tag with no model is denied"),
    ("lane-start-settings: a value that is not text counts as present when its str() is not blank, so null, a number and a list are allowed",
     'if not (isinstance(tool_input.get(k), str) and tool_input[k].strip())]',
     'if not (k in tool_input and str(tool_input[k]).strip())]',
     "guard", "lane-start-settings: lane tag with a non-text"),
    # ---- lane-floor. The floor's refusal names the lane remedy for a lane create_session and the no-model remedy for
    # every other spawn. Each mutant breaks that choice, or the one lane-tag reading the floor and the three lane checks
    # share (is_lane_create_session). lane_tags holds no case handling; the casefold lives in is_lane_create_session.
    ("lane-floor: a lane create_session below the floor gets the no-model remedy again",
     'LANE_MODEL_FLOOR_REASON if is_lane_create_session(tool, tool_input) else MODEL_FLOOR_REASON,',
     'MODEL_FLOOR_REASON,',
     "guard", "floor lane: a lane create_session on haiku is denied with the lane remedy"),
    ("lane-floor: every floor refusal gets the lane remedy, so an Agent spawn names the lane inputs",
     'LANE_MODEL_FLOOR_REASON if is_lane_create_session(tool, tool_input) else MODEL_FLOOR_REASON,',
     'LANE_MODEL_FLOOR_REASON,',
     "guard", "floor remedy: Agent on haiku keeps the no-model remedy"),
    ("lane-floor: is_lane_create_session is always False, so no lane check fires",
     '    return tool == CREATE_SESSION_TOOL and any(',
     '    return False and any(',
     "guard", "lane-start-settings: lane tag with no model is denied"),
    ("lane-floor: is_lane_create_session is always True, so every call is judged as a lane",
     '    return tool == CREATE_SESSION_TOOL and any(',
     '    return True or any(',
     "guard", "lane-start-settings: coordinator call with no model and no source_url is allowed"),
    ("lane-floor: the lane tag is matched without casefold, so an upper-case lane tag is no lane",
     'isinstance(t, str) and t.strip().casefold() == LANE_TAG for t in lane_tags(tool_input))',
     'isinstance(t, str) and t.strip() == LANE_TAG for t in lane_tags(tool_input))',
     "guard", "floor lane: an upper-case lane tag on haiku gets the lane remedy"),
    # RULE roadmap-one-writer. A push to the record branch needs the triage tag in the own record, with no
    # set_session_tags call after it.
    ("roadmap-one-writer: the triage tag is not checked, so any own record is a proof",
     '            return tags is not None and not tagged_after and ROLE_TAG_PREFIX + tier in tags',
     '            return tags is not None and not tagged_after', "guard",
     "a lane's push that names roadmap is refused"),
    ("roadmap-one-writer: a set_session_tags call after the record is ignored",
     '            return tags is not None and not tagged_after and ROLE_TAG_PREFIX + tier in tags',
     '            return tags is not None and ROLE_TAG_PREFIX + tier in tags', "guard",
     "a triage record with a set_session_tags call after it is refused a push to roadmap"),
    ("roadmap-one-writer: a push never counts as reaching the record branch",
     '            if {record, DEFAULT_RECORD_BRANCH} & set(push_destinations(args, where, overrides)) and (',
     '            if set() & set(push_destinations(args, where, overrides)) and (', "guard",
     "a lane's push that names roadmap is refused"),
    ("roadmap-one-writer: the default name roadmap is no record branch in a fork",
     '            if {record, DEFAULT_RECORD_BRANCH} & set(push_destinations(args, where, overrides)) and (',
     '            if {record} & set(push_destinations(args, where, overrides)) and (', "guard",
     "a lane's push to roadmap in the fork is refused"),
    ("roadmap-one-writer: a dry run is judged like a push",
     '            if read_verb("push", args):\n                continue',
     '            if False:\n                continue', "guard",
     "a lane's dry run of a push to roadmap with --dry-run is allowed"),
    ("roadmap-one-writer: a push handed to a shell, eval or ssh is not read",
     '    inner = inner_commands(tokens) if tokens else []',
     '    inner = []', "guard", "a push to roadmap inside bash -c is refused"),
    ("roadmap-one-writer: a wrapped push runs in the call's folder, not its segment's cd",
     '        inner_cwd = push_target(segment, script, cwd)[0] or cwd',
     '        inner_cwd = cwd', "guard", "a push inside bash -c after a cd is judged by the folder it moved to"),
    ("roadmap-one-writer: a set_session_tags call on another session voids the own proof",
     '                    if not isinstance(ids, list) or own_id in ids:',
     '                    if True:', "guard",
     "a triage record then a tag call on another session is allowed"),
    ("roadmap-one-writer: a set_session_tags call with no id list is ignored, so the proof stands",
     '                    if not isinstance(ids, list) or own_id in ids:',
     '                    if isinstance(ids, list) and own_id in ids:', "guard",
     "a triage record then a tag call that names no sessions is refused"),
    ("roadmap-one-writer: HEAD as a destination is not resolved to the current branch",
     '    if target in ("HEAD", "@"):\n        return _push_current_branch(cwd)',
     '    if False:\n        return _push_current_branch(cwd)', "guard",
     "a lane's HEAD push from the roadmap checkout is refused"),
    ("roadmap-one-writer: a bare push is not resolved to the current branch",
     '    if bare:\n        return _push_bare_destination(cwd, overrides)',
     '    if False:\n        return _push_bare_destination(cwd, overrides)', "guard",
     "a lane's bare push from the roadmap checkout is refused"),
    ("roadmap-one-writer: refs/heads/ is not cut off the destination",
     '        _DESTINATIONS[key] = [t.removeprefix("refs/heads/") if t else t for t in found]',
     '        _DESTINATIONS[key] = found', "guard", "a lane's push of a ref into refs/heads/roadmap is refused"),
    ("roadmap-one-writer: git -C does not move the push to its checkout",
     '            where, overrides = push_target(segment, script, cwd)\n            yield _command_words(args), where, overrides',
     '            where, overrides = cwd, {}\n            yield _command_words(args), where, overrides', "guard",
     "a lane's push of roadmap-fork with git -C into the fork is refused"),
    # A `)` or `&` glued to the last word ends the command (_command_words).
    ("roadmap-one-writer: a glued ) is kept, so a subshell's push reads roadmap)",
     '        word = arg.rstrip(")&")',
     '        word = arg.rstrip("&")', "guard",
     "a lane's push to roadmap in a subshell after a cd into the roadmap checkout is refused"),
    ("roadmap-one-writer: a glued & is kept, so a background push reads roadmap&",
     '        word = arg.rstrip(")&")',
     '        word = arg.rstrip(")")', "guard",
     "a lane's push to roadmap with a trailing background & is refused"),
    ("roadmap-one-writer: the push's words are not cut at the end of the command",
     '            yield _command_words(args), where, overrides',
     '            yield args, where, overrides', "guard",
     "a lane's HEAD:roadmap push in a subshell after a cd, piped to tail, is refused"),
    ("roadmap-one-writer: the word a glued ) or & ends keeps its mark",
     '            if word:\n                words.append(word)\n            break',
     '            if word:\n                words.append(arg)\n            break', "guard",
     "a lane's push to roadmap in a subshell under bash -c after a cd is refused"),
    ("roadmap-one-writer: the record branch is never read, so every checkout's record is roadmap",
     '        return layout.record_branch(root)',
     '        return DEFAULT_RECORD_BRANCH', "guard",
     "a lane's push of roadmap-fork is refused in the fork that names it its record branch"),
    # RULE simulator-boot-bypass (decision sim-test-is-the-one-boot-path, ruling 4). Each mutant breaks one arm.
    ("simulator-boot-bypass: a raw simctl boot is never read",
     '        if _simctl_boot_args(word, rest) is not None:\n            return',
     '        if False:\n            return', "guard", 'simulator-boot-bypass: xcrun simctl boot'),
    ("simulator-boot-bypass: a boot with no device argument (xargs feeds it) is not a boot",
     '            return after[1:]\n    return None',
     '            return after[1:] or None\n    return None', "guard", 'simulator-boot-bypass: xargs of an echo into a boot'),
    ("simulator-boot-bypass: an open flag cluster is not read, only a lone -a or -b",
     'if re.fullmatch(r"-[A-Za-z]*[ab][A-Za-z]*", arg)',
     'if re.fullmatch(r"-[ab]", arg)', "guard", 'simulator-boot-bypass: open -ga Simulator'),
    ("simulator-boot-bypass: a bare simctl word is not a boot command",
     'if word in ("xcrun", "simctl") and "simctl" in ([word] + rest):',
     'if word in ("xcrun",) and "simctl" in ([word] + rest):', "guard", 'simulator-boot-bypass: bare simctl boot'),
    ("simulator-boot-bypass: open -a Simulator is not read",
     'if ("a" in arg and re.sub(r"\\.app$", "", value) == "simulator") or (',
     'if (False) or (', "guard", 'simulator-boot-bypass: open -a Simulator'),
    ("simulator-boot-bypass: open -b the simulator bundle id is not read",
     '"b" in arg and value == "com.apple.iphonesimulator"):',
     'False):', "guard", 'simulator-boot-bypass: open -b the simulator bundle id'),
    ("simulator-boot-bypass: an open of the Simulator.app path is not read",
     'elif low.endswith("/simulator.app") or low == "simulator.app":',
     'elif False:', "guard", 'simulator-boot-bypass: open of the Simulator.app path'),
    ("simulator-boot-bypass: a command a wrapper hands on is not read",
     '    for text in inner_commands(tokens):\n        for part in split_segments(text):\n            yield from _sim_commands(part)',
     '    return', "guard", 'simulator-boot-bypass: bash -c wraps the boot'),
    ("simulator-boot-bypass: the refusal is never raised",
     '                refuse(tool, "deny", "simulator-boot-bypass", SIM_BYPASS_REASON, matched)',
     '                pass', "guard", 'simulator-boot-bypass: xcrun simctl boot'),
    # RULE simulator-boot-route (decision sim-test-is-the-one-boot-path, ruling 5).
    # Each mutant breaks one arm of its rule. The named case is the one that must die.
    ("simulator-boot-route: an xcodebuild boot of a shut-down device is never refused",
     '        elif (remedies or {}).get(name):',
     '        elif False:', "guard",
     "route: a test of a shut-down simulator by id names sim-test"),
    ("simulator-boot-route: the test action is never read, so every test gets the generic remedy",
     'elif token == "test" and not (',
     'elif False and not (', "guard",
     "route: a test with the action after its options, a shut-down simulator by name, names sim-test"),
    ("simulator-boot-route: a test gets the generic remedy, not sim-test",
     '    if action:\n        return "Run `sim-test',
     '    if not action:\n        return "Run `sim-test', "guard",
     "route: a test of a shut-down simulator by id names sim-test"),
    ("simulator-boot-route: a build names a destination that is not the generic one",
     "`-destination 'generic/platform=iOS Simulator'` instead, and boot nothing.",
     "`-destination 'generic/platform=iOS'` instead, and boot nothing.", "guard",
     "route: a build of a shut-down simulator names the generic destination"),
    # RULE simulator-boot-lease (decision sim-test-is-the-one-boot-path, ruling 5). Each mutant breaks one arm.
    ("simulator-boot-lease: the refusal is an ask, not a deny",
     'refuse(tool, "deny", "simulator-boot-lease",',
     'refuse(tool, "ask", "simulator-boot-lease",', "guard",
     "lease: one booted, an MCP launch of a shut-down device with no lock is refused by the lease"),
    ("simulator-boot-lease: a booted device is judged by the lease too",
     '        hits = [d for d in hits if d["state"] != "Booted"]',
     '        hits = list(hits)', "guard",
     "lease: an MCP launch of a booted device with no lock is allowed"),
    # The name arm compares exactly: a name without the case or outer-space fold matches no device. The UDID arm stays.
    ("simulator-boot-lease: a device name compares exactly, without the case and outer-space fold",
     '        hits = [d for d in devices if key == d["udid"].casefold() or key == d["name"].strip().casefold()]',
     '        hits = [d for d in devices if key == d["udid"].casefold() or name == d["name"]]', "guard",
     "lease: an MCP launch naming the shut-down device in lowercase is refused by the lease"),
    # The lease allow (ruling 5): one mutant per arm of guard.sim_lease_holds and of bin/sim-lease's read.
    ("simulator-boot-lease: the lease's session is not compared",
     '                if session == e.get("session") and e.get("slot") in lease.SLOT_UDID}',
     '                if e.get("slot") in lease.SLOT_UDID}', "guard",
     "lease: another session's live slot 1 lease on Duo 1 does not allow this session", "posix"),
    ("simulator-boot-lease: an empty session may match an empty lease session",
     '    if not session or not udids:\n        return False',
     '    if not udids:\n        return False', "guard",
     "lease: a lease with an empty session does not match a payload with no session", "posix"),
    ("simulator-boot-lease: every slot maps to Duo 1",
     'held = {lease.SLOT_UDID[e["slot"]].casefold()',
     'held = {lease.SLOT_UDID["1"].casefold()', "guard",
     "lease allow: this session's live slot 2 lease", "posix"),
    ("simulator-boot-lease: any held device allows a launch of any device",
     '    return all(u.casefold() in held for u in udids)',
     '    return bool(held)', "guard",
     "lease: this session's slot 1 lease does not allow a launch of Duo 2", "posix"),
    ("simulator-boot-lease: a shared name is allowed when any one of its devices is held",
     '    return all(u.casefold() in held for u in udids)',
     '    return any(u.casefold() in held for u in udids)', "guard",
     "lease: a shared name, this session's slot 1 lease alone is refused", "posix"),
    ("simulator-boot-lease: a lease that cannot be read allows",
     '    except Exception:\n        return False\n    finally:\n        sys.dont_write_bytecode = keep',
     '    except Exception:\n        return True\n    finally:\n        sys.dont_write_bytecode = keep', "guard",
     "lease: a lease file that is not JSON keeps the refusal", "posix"),
    ("sim-lease: a pid that is alive counts as live whatever its start time",
     '    return bool(entry.get("start")) and isinstance(pid, int) and start_time(pid) == entry["start"]',
     '    return bool(entry.get("start")) and isinstance(pid, int) and bool(start_time(pid))', "simlease",
     "lease: a reused pid (its start differs from the lease's) is refused", "posix"),
    ("sim-lease: a pid that is dead counts as live",
     '    return bool(entry.get("start")) and isinstance(pid, int) and start_time(pid) == entry["start"]',
     '    return bool(entry.get("start")) and isinstance(pid, int)', "simlease",
     "lease: a dead lease (its pid is not alive) is refused", "posix"),
    ("sim-lease: the live read takes the queue for the leases",
     '    return [e for e in data["leases"] if isinstance(e, dict) and is_live(e)]',
     '    return [e for e in data["queue"] if isinstance(e, dict) and is_live(e)]', "simlease",
     "lease: this session only queued, not granted, is refused", "posix"),
    ("sim-lease: the live read creates the lock file",
     '    return [e for e in data["leases"] if isinstance(e, dict) and is_live(e)]',
     '    open(os.path.join(state_dir(), "lock"), "a").close()\n'
     '    return [e for e in data["leases"] if isinstance(e, dict) and is_live(e)]', "simlease",
     "the lease read writes nothing", "posix"),
    ("sim-lease: the pro slot maps to another device",
     '"pro": "86F9268A-A905-4B82-9BC0-D7EBB682D341",',
     '"pro": "86F9268A-A905-4B82-9BC0-D7EBB682D342",', "simlease",
     "lease allow: this session's live pro lease", "posix"),
    # ---- handoff-unread (decision precompact-handoff, item 9): one mutant per arm. The anchors sit in
    # guard.py and in reread_check.py; a "guard" mutant lands in whichever module holds the anchor.
    ("handoff-unread: the refusal is never printed",
     '        refuse(tool, "deny", "handoff-unread", HANDOFF_UNREAD_REASON % unread, unread)',
     '        pass',
     "guard", "handoff-unread: after compaction, Bash is refused while the handoff is unread"),
    ("handoff-unread: a failed import of reread_check no longer fails open",
     '    except Exception:\n        unread_handoff = None\n',
     '    except Exception:\n        raise\n',
     "guard", "handoff-unread: a guard copy without reread_check.py fails open"),
    ("handoff-unread: an agent's call is judged like the main session's",
     '        if ph is None or not isinstance(payload, dict) or payload.get("agent_id"):',
     '        if ph is None or not isinstance(payload, dict):',
     "guard", "handoff-unread: a payload that carries agent_id is allowed"),
    ("handoff-unread: the flag is not read, so a set handoff alone refuses",
     '        if not sid or not isinstance(sid, str) or not os.path.isfile(ph.reread_flag_path(sid)):',
     '        if not sid or not isinstance(sid, str):',
     "guard", "handoff-unread: a call is allowed when the flag is absent"),
    ("handoff-unread: a missing handoff still refuses",
     '        return handoff if os.path.isfile(handoff) else ""',
     '        return handoff',
     "guard", "handoff-unread: a call is allowed when the flag is set and the handoff is missing"),
    ("mockup-home: the refuse arm is dropped, so a design whose file sits under the machine home is allowed",
     "            if unhomed:",
     "            if False:",
     "guard", "mockup-home: a design with a file under the machine home is denied"),
    # gh_call_of (hooks/guard_merge.py) is the one home every gh reader shares. Unread, a repo flag before
    # the verb hides `pr merge` and `pr create` from the merge guard, the draft read, ci_wake and the report guard.
    ("gh-root-flag: a repo flag before the pr verb goes unread",
     '    while rest and _gh_root_repo_flag(rest, 0):',
     '    while False and _gh_root_repo_flag(rest, 0):',
     "guard", "merge: gh_call_of reads the pr verb past a -R root flag"),
    # The second pass of gh_call_of's loop reads a repo flag right after the group word (`gh pr -R o/r comment`).
    # Only that pass goes: the first pass, before the group word, still reads its flags.
    ("gh-group-flag: a repo flag after the group word goes unread",
     '    for _ in (0, 1):',
     '    for _ in (0,):',
     "guard", "after the group word"),
    # records-page: a commit of MERGE_HEAD's page is allowed on origin/<base>'s first-parent line, or for a stacked
    # lane (some best merge base of HEAD and MERGE_HEAD is off origin/<base>).
    ("records-page: MERGE_HEAD is not read against origin/<base>, so another branch's page is allowed",
     '    return ids[1] if line is not None and line.returncode == 0 and ids[0] in line.stdout.split() else ""',
     '    return ids[1]',
     "guard", "a test-author commit of a non-base merge's page, the feature branch's, origin/main moved on"),
    ("records-page: the line is not first-parent only, so a branch merged into the base is allowed",
     '"rev-list", "--first-parent", origin)',
     '"rev-list", origin)',
     "guard", "off its first-parent line"),
    ("records-page: the page is not compared with MERGE_HEAD's, so a rebuilt page is allowed",
     '            if not page_id or page_id != _merge_head_page(top, base):',
     '            if not page_id or not _merge_head_page(top, base):',
     "guard", "a test-author commit of a page rebuilt after the merge, origin/main moved on"),
    ("records-page: MERGE_HEAD's page is never read, so the merge's own page is refused",
     '            if not page_id or page_id != _merge_head_page(top, base):',
     '            if True:',
     "guard", "a test-author commit of the merge's own page, after origin/main moved on"),
    # An absent page (a deletion staged in the index) is refused unless no merge brings one. Without the check, a
    # deleted page with no merge in progress compares '' with '' and is allowed.
    ("records-page: the absent-page check is dropped, so a commit that deletes the page is allowed with no merge",
     '            if not page_id or page_id != _merge_head_page(top, base):',
     '            if page_id != _merge_head_page(top, base):',
     "guard", "a commit that deletes the page, with no merge in progress"),
    # The stacked clause of `_merge_head_page` (guard_merge.py): a lane stacked on an unmerged base passes for
    # MERGE_HEAD's page. Each label starts "records-page: stacked clause", so that prefix selects these three.
    ("records-page: stacked clause, an is-ancestor exit of 0 or an error passes, so a failed read is a pass",
     "if seen is not None and seen.returncode == 1:",
     "if seen is not None and seen.returncode != 0:",
     "guard", "so the is-ancestor read fails"),
    ("records-page: stacked clause, merge-base without --all reads one best base, so a criss-cross base is missed",
     '    meet = _git(top, "merge-base", "--all", "HEAD", "MERGE_HEAD")',
     '    meet = _git(top, "merge-base", "HEAD", "MERGE_HEAD")',
     "guard", "a lane's merge of a criss-cross stacked base, with the base's page staged"),
    ("records-page: stacked clause, the page passes with no is-ancestor read, so a branch cut from main passes",
     '        seen = _git(top, "merge-base", "--is-ancestor", best, origin)\n'
     '        if seen is not None and seen.returncode == 1:   # 1 is "not an ancestor"; 0 is one, other is a failure\n'
     '            return ids[1]',
     '        return ids[1]',
     "guard", "an unrelated unmerged branch, whose merge bases are both on origin/main"),
    # Rule brief-destructive-git: the check reads no brief, so an ordered discard passes.
    ("brief-destructive-git: the check finds no ordered discard, so a brief that orders a reset passes",
     "                if match and match[1] not in BRIEF_DESTRUCTIVE_SKIP",
     "                if False and match and match[1] not in BRIEF_DESTRUCTIVE_SKIP",
     "guard", "brief-destructive-git: builder brief that orders `git reset --hard origin/main` is denied"),
    # Rule brief-claim-has-probe: one mutant per edge the cases pin.
    ("brief-claim: the check never fires, so an unprobed claim about main passes",
     '    return brief_claim_gaps(tool_input.get("prompt"))',
     '    return []',
     "guard", "brief-claim: builder brief that says main allows an input, with no probe, is denied"),
    ("brief-claim: the dispatch reads no claim, so the refusal never prints",
     "    claimed = brief_claim_hit(tool, tool_input)\n    if claimed:",
     '    claimed = ""\n    if claimed:',
     "guard", "brief-claim: test-author brief that says main passes two inputs, with no probe, is denied"),
    ("brief-claim: a test-author is out of scope",
     'BRIEF_CLAIM_ROLES = ("builder", "test-author")',
     'BRIEF_CLAIM_ROLES = ("builder",)',
     "guard", "brief-claim: test-author brief that says today main refuses an input, with no command, is denied"),
    ("brief-claim: a reviewer is in scope, so its main claim is refused",
     'BRIEF_CLAIM_ROLES = ("builder", "test-author")',
     'BRIEF_CLAIM_ROLES = ("builder", "test-author", "reviewer")',
     "guard", "brief-claim: reviewer brief with the main claim is allowed (out of scope)"),
    ("brief-claim: today is no subject, so a claim with no main named passes",
     "|(?<![\\w/.-])today,?",
     "|(?<![\\w/.-])zzzzz,?",
     "guard", "brief-claim: test-author brief that says today the guard refuses an input, with no main named, is denied"),
    ("brief-claim: a command with no result line counts as a probe",
     '        if result is not None:\n            probes.append([" ".join(row[1].split()), " ".join(result.split())])',
     '        probes.append([" ".join(row[1].split()), " ".join((result or "").split())])',
     "guard", "brief-claim: builder brief with a main claim and a command but no result line is denied"),
    ("brief-claim: a probe for any input shows every claim",
     "not any(_claim_probed(key, texts) for texts in probes)",
     "not any(probes)",
     "guard", "brief-claim: test-author brief whose probe is for another input does not show the claim, and is denied"),
    ("brief-claim: a lone backtick opens no input, so the claim after it hides",
     "|`+(.*)$|",
     "|(?!x)x|",
     "guard", "brief-claim: builder brief with a lone quote and an unmatched backtick around a main claim is denied"),
    ("brief-claim: only the first 29 lines are read, so a claim on line 30 hides",
     '    lines = brief.split("\\n")\n    marks = [i for i, line in enumerate(lines) if line.strip().startswith("```")]',
     '    lines = brief.split("\\n")[:29]\n    marks = [i for i, line in enumerate(lines) if line.strip().startswith("```")]',
     "guard", "brief-claim: builder brief with the claim on line 30 of a long brief, with no probe, is denied"),
    ("brief-claim: a backticked main is no subject",
     'if hit.group(1) and body.lower() in ("main", "origin/main"):',
     'if False and body.lower() in ("main", "origin/main"):',
     "guard", "brief-claim: test-author brief with a backticked main subject and a refusal is denied"),
    ("brief-claim: fenced text is not read for claims",
     "        listed = bool(BRIEF_CLAIM_LIST.match(text))\n",
     '        if fenced:\n            rows.append(("out", text))\n            continue\n        listed = bool(BRIEF_CLAIM_LIST.match(text))\n',
     "guard", "brief-claim: test-author brief with a claim inside a fence after Cases: is denied"),
    ("brief-claim: a line that starts with a backtick is read as a command first, so a claim line is its own probe",
     "        sentences = _claim_line(text)\n",
     '        sentences = [] if text.startswith("`") else _claim_line(text)\n',
     "guard", "brief-claim: builder brief whose claim line is its own probe is denied"),
    ("brief-claim: a probe that holds the input as part of a longer one shows it",
     '''shown = re.compile(r"(?:^|['\\"`])" + re.escape(key) + r"(?:$|['\\"`])")''',
     "shown = re.compile(re.escape(key))",
     "guard", "brief-claim: test-author brief whose probe is for a longer input than the claim is denied"),
    ("brief-claim: the verbs rejects and blocks are no claim",
     "accepts|accepted|refuses|refused|rejects|rejected|blocks|blocked)",
     "accepts|accepted|refuses|refused)",
     "guard", "brief-claim: builder brief with main rejects an input is denied"),
    ("brief-claim: the passive form is no claim",
     "clause = BRIEF_CLAIM_PASSIVE.search(sentence)",
     "clause = None",
     "guard", "brief-claim: builder brief with an input refused on main in passive form is denied"),
    ("brief-claim: a plain-quoted input is no input",
     '''|\\"([^\\"\\n]+)\\"|(?<!\\w)'([^'`\\n]+)'(?!\\w)")''',
     '")',
     "guard", "brief-claim: test-author brief where main passes a plain-quoted input is denied"),
    ("brief-claim: any word between main and the verb is read, so main as an adjective is a subject",
     '''_CLAIM_ADVERB = r"(?:(?:still|also|now|today|currently|already|even|always|never)\\s+)?"''',
     '''_CLAIM_ADVERB = r"(?:\\S+\\s+)?"''',
     "guard", "brief-claim: builder brief with main as an adjective before a refusal is allowed"),
    ("brief-claim: any word after today is a subject, so today as a time word is read",
     '_CLAIM_SUBJECT = r"(?:it|they|guard|hook|rule|check)"',
     '_CLAIM_SUBJECT = r"(?:it|they|guard|hook|rule|check|\\w+)"',
     "guard", "brief-claim: builder brief with today as a time word and the builder as subject is allowed"),
    ("brief-claim: a path after in is an input, not a locator",
     '            locator = (bool(BRIEF_CLAIM_LOCATOR.search(sentence[:m.start()])) and len(item.split()) == 1\n'
     '                       and ("/" in item or "." in item))',
     "            locator = False",
     "guard", "brief-claim: test-author brief with a path locator after a probed refusal is allowed"),
    ("brief-claim: a double-quoted span stops at a backtick, so a quoted case text is read as a claim",
     '''|\\"([^\\"\\n]+)\\"|''',
     '''|\\"([^\\"`\\n]+)\\"|''',
     "guard", "brief-claim: test-author brief quoting a claim after Must deny: is allowed"),
    ("brief-claim: a Must deny: line is skipped whole, so an unquoted claim in it hides",
     "        sentences = _claim_line(text)\n",
     '        sentences = [] if text.lower().startswith("must deny:") else _claim_line(text)\n',
     "guard", "brief-claim: test-author brief with an unquoted claim inside a Must deny: line is denied"),
    ("brief-claim: a referent takes nothing from the sentence before",
     'claimed.extend(before if refer == "before" else items)',
     "claimed.extend(items)",
     "guard", "brief-claim: test-author brief where main passes both, with its inputs in the sentence before, is denied"),
    ("brief-claim: a claim that ends with a colon takes no list lines after it",
     "        elif listed and waiting is not None:\n            waiting.extend(own)",
     "        elif False:\n            waiting.extend(own)",
     "guard", "brief-claim: builder brief where as main refuses it, with its inputs in a list below, is denied"),
    ("brief-claim: a referent after a list takes no list line",
     "        if listed:\n            before = block\n",
     "        if listed:\n            before = []\n",
     "guard", "brief-claim: test-author brief where main passes all of them, after a list of inputs, is denied"),
    ("brief-claim: a negated verb is no claim",
     '''_CLAIM_NOT = r"(?:(?:does|did|do)\\s+not|(?:does|did|do)n['\\u2019]t)\\s+"''',
     '''_CLAIM_NOT = r"(?!x)x"''',
     "guard", "brief-claim: builder brief where main doesn't refuse an input is denied"),
    ("brief-claim: never between main and the verb is no adverb",
     "already|even|always|never)",
     "already|even|always)",
     "guard", "brief-claim: test-author brief where main never refuses an input is denied"),
    ("brief-claim: lets ... through is no claim",
     '''r"\\b|lets" + _CLAIM_THROUGH''',
     '''r"\\b"''',
     "guard", "brief-claim: builder brief where main lets an input through is denied"),
    ("brief-claim: a claim clause runs past , so to the sentence's end",
     "    stop = BRIEF_CLAIM_BREAK.search(sentence, clause.end())\n    hi = stop.start() if stop else len(sentence)",
     "    hi = len(sentence)",
     "guard", "brief-claim: builder brief whose main claim is followed by so and a backticked command is allowed"),
    ("brief-claim: a probe that starts with cd ... && is no command",
     '''(?:(?:cd\\s[^&|;\\n]*&&|echo''',
     '''(?:(?:echo''',
     "guard", "brief-claim: builder brief with a cd-and-python3 probe and its result line is allowed"),
    ("brief-claim: a probe that starts with echo ... | is no command",
     '''&&|echo\\s[^|\\n]*\\||[A-Za-z_]''',
     '''&&|[A-Za-z_]''',
     "guard", "brief-claim: test-author brief with a piped echo probe and its result line is allowed"),
    ("brief-claim: a probe that starts with NAME=value is no command",
     '''\\||[A-Za-z_]\\w*=\\S*|time)''',
     '''\\||time)''',
     "guard", "brief-claim: builder brief with an env-prefixed python3 probe and its result line is allowed"),
    ("brief-claim: a probe that starts with time is no command",
     '''\\w*=\\S*|time)\\s+)*''',
     '''\\w*=\\S*)\\s+)*''',
     "guard", "brief-claim: test-author brief with a time-prefixed python3 probe and its result line is allowed"),
    ("brief-claim: the refusal names only the first gap",
     'for item in claimed)',
     'for item in claimed[:1])',
     "guard", "brief-claim: builder brief with two unprobed claims names both inputs in its refusal, and is denied"),
    ('brief-claim: all, each and both are referents anywhere in a clause, so main passes all tests takes the inputs before it',
     'r"\\b(?:it|them)\\b|\\b(?:both|all|each|these)\\b(?=[\\s.!?:;,)]*$|\\s+of\\s+(?:them|these|those)\\b)"',
     'r"\\b(?:it|them|both|all|each|these)\\b"',
     "guard", 'brief-claim: test-author brief where origin/main passes all tests, after a backticked path, is allowed'),
    ('brief-claim: a referent at the clause end is no referent, so main passes both takes nothing',
     '(?=[\\s.!?:;,)]*$|\\s+of\\s+(?:them|these|those)\\b)"',
     '(?=\\s+of\\s+(?:them|these|those)\\b)"',
     "guard", 'brief-claim: test-author brief where main passes both, with its inputs in the sentence before, is denied'),
    ('brief-claim: the active form takes every input of its clause whatever follows the verb',
     'if not claimed and (passive or BRIEF_CLAIM_BARE.fullmatch(sentence, clause.end(), hi)):',
     'if not claimed:',
     "guard", 'brief-claim: test-author brief where origin/main passes CI after because, with an input before it, is allowed'),
    ('brief-claim: a Controls heading does not close the claimed list',
     'if waiting is not None and not own and BRIEF_CLAIM_HEADING.match(text):',
     'if False:',
     "guard", 'brief-claim: builder brief with a bulleted Controls heading after a probed refusal list is allowed'),
    ('brief-claim: a numbered Controls heading does not close the claimed list',
     'r"(?:(?:[-*+]|\\d+[.)])\\s+)?controls?\\b[^:]*:\\s*$"',
     'r"(?:[-*+]\\s+)?controls?\\b[^:]*:\\s*$"',
     "guard", 'brief-claim: test-author brief with a numbered Controls heading after a probed refusal list is allowed'),
    ('brief-claim: the base verb form is no claim, so two inputs that pass on main hide',
     '_CLAIM_ANY = r"(?:" + _CLAIM_VERB + r"|" + _CLAIM_BASE + r"|" + _CLAIM_ING + r")"',
     '_CLAIM_ANY = r"(?:" + _CLAIM_VERB + r"|" + _CLAIM_ING + r")"',
     "guard", 'brief-claim: test-author brief where two inputs pass on main, joined by and, is denied'),
    ('brief-claim: the -ing verb form is no claim, so an input listed as passing on main hides',
     '_CLAIM_ANY = r"(?:" + _CLAIM_VERB + r"|" + _CLAIM_BASE + r"|" + _CLAIM_ING + r")"',
     '_CLAIM_ANY = r"(?:" + _CLAIM_VERB + r"|" + _CLAIM_BASE + r")"',
     "guard", 'brief-claim: builder brief where an input is listed as passing on main is denied'),
    ('brief-claim: a leading On main frame is no claim',
     'r"(?<![\\w/.-])(?:on\\s+(?:origin/main|main)(?![\\w/-])|today\\b),?\\s+"',
     'r"(?<![\\w/.-])(?:today\\b),?\\s+"',
     "guard", 'brief-claim: test-author brief where On main, an input passes is denied'),
    ('brief-claim: a leading Today frame is no claim',
     'r"(?<![\\w/.-])(?:on\\s+(?:origin/main|main)(?![\\w/-])|today\\b),?\\s+"',
     'r"(?<![\\w/.-])(?:on\\s+(?:origin/main|main)(?![\\w/-])),?\\s+"',
     "guard", 'brief-claim: builder brief where Today an input passes is denied'),
    ('brief-claim: a subject with today later in the sentence is no claim',
     '_CLAIM_ACTS + r"(?=[^.!?;]*\\btoday\\b)",',
     '_CLAIM_ACTS + r"(?!x)x",',
     "guard", 'brief-claim: test-author brief where the guard refuses an input today is denied'),
    ('brief-claim: a NUL in a brief is read as an input marker',
     '    text = text.replace("\\x00", " ")   # a NUL in a brief would read as a marker of its own\n',
     '',
     "guard", 'brief-claim: builder brief with a NUL marker on a line with no quoted input, then a claim, is denied without a crash'),
    ('brief-claim: the base verb block is no claim, so main does not block an input hides',
     '_CLAIM_BASE = r"(?:pass|allow|accept|refuse|reject|block)"',
     '_CLAIM_BASE = r"(?:pass|allow|accept|refuse|reject)"',
     "guard", 'brief-claim: builder brief where main does not block an input is denied'),
    ('brief-claim: the -ing verb refusing is no claim, so an input refusing on main hides',
     '_CLAIM_ING = r"(?:passing|allowing|accepting|refusing|rejecting|blocking)"',
     '_CLAIM_ING = r"(?:passing|allowing|accepting|rejecting|blocking)"',
     "guard", 'brief-claim: builder brief where an input is refusing on main is denied'),
    ('brief-claim: check is no claim subject, so the check refuses an input today hides',
     '_CLAIM_SUBJECT = r"(?:it|they|guard|hook|rule|check)"',
     '_CLAIM_SUBJECT = r"(?:it|they|guard|hook|rule)"',
     "guard", 'brief-claim: test-author brief where the check refuses an input today is denied'),
    ('brief-claim: rule is no claim subject, so the rule refuses an input today hides',
     '_CLAIM_SUBJECT = r"(?:it|they|guard|hook|rule|check)"',
     '_CLAIM_SUBJECT = r"(?:it|they|guard|hook|check)"',
     "guard", 'brief-claim: test-author brief where the rule refuses an input today is denied'),
    ('brief-claim: now is no bare word after a verb, so an input before main refuses now hides',
     '\\b(?:today|now)\\b)*"',
     '\\b(?:today)\\b)*"',
     "guard", 'brief-claim: test-author brief where an input before main refuses now is denied'),
    # The count word, the pronoun tail and today in _claim_active. The two whole-sentence searches in _claim_active
    # (the leading-claim search and the today-bounded subject search) have no mutant here: they are time-only, per the
    # brief. Equivalent mutants change no verdict, so none is listed: "<=" for "<", taking a subject whenever one is
    # found, and a today pattern without the word boundary.
    ('brief-claim: a count word does not refer, so refuses all three today hides from the refers test',
     'return bool(BRIEF_CLAIM_REFERENT.search(text) or BRIEF_CLAIM_COUNT.search(text))',
     'return bool(BRIEF_CLAIM_REFERENT.search(text))',
     "guard", 'brief-claim: test-author brief where main refuses all three today'),
    ('brief-claim: a pronoun does not refer, so refuses it after a same-sentence input is read as no claim',
     'return bool(BRIEF_CLAIM_REFERENT.search(text) or BRIEF_CLAIM_COUNT.search(text))',
     'return bool(BRIEF_CLAIM_COUNT.search(text))',
     "guard", 'brief-claim: test-author brief where main refuses it, after an input in the same sentence'),
    ('brief-claim: a bare now after both is no count, so refuses both now hides',
     r'|(?:today|now)\b)[\s.!?:;,)]*$",',
     r')[\s.!?:;,)]*$",',
     "guard", 'brief-claim: test-author brief where main refuses both now'),
    ('brief-claim: a today or now after a count word is no count, so refuses all three today hides',
     r'\b(?:\s+(?:today|now)\b)?|(?:today|now)\b)[\s.!?:;,)]*$"',
     r'\b|(?:today|now)\b)[\s.!?:;,)]*$"',
     "guard", 'brief-claim: test-author brief where main refuses all three today'),
    ('brief-claim: now after a count word is no count, so refuses all three now hides',
     r'(?:\s+(?:today|now)\b)?|',
     r'(?:\s+(?:today)\b)?|',
     "guard", 'brief-claim: test-author brief where main refuses all three now'),
    ('brief-claim: a bare now is no count, so refuses both now hides',
     r'|(?:today|now)\b)[\s.!?:;,)]*$"',
     r'|(?:today)\b)[\s.!?:;,)]*$"',
     "guard", 'brief-claim: test-author brief where main refuses both now'),
    ('brief-claim: ones is no count word, so refuses these ones hides',
     r'_CLAIM_COUNT_WORD = r"(?:one|ones|two',
     r'_CLAIM_COUNT_WORD = r"(?:one|two',
     "guard", 'brief-claim: test-author brief where main refuses these ones'),
    ('brief-claim: digits are no count word, so refuses all 3 hides',
     r'|ten|\d+|cases?|inputs?)"',
     r'|ten|cases?|inputs?)"',
     "guard", 'brief-claim: test-author brief where main refuses all 3'),
    ('brief-claim: inputs is no count word, so refuses both inputs hides',
     r'|ten|\d+|cases?|inputs?)"',
     r'|ten|\d+|cases?)"',
     "guard", 'brief-claim: test-author brief where main refuses both inputs'),
    ('brief-claim: five to nine are no count words, so refuses all five hides',
     r'_CLAIM_COUNT_WORD = r"(?:one|ones|two|three|four|five|six|seven|eight|nine|ten|',
     r'_CLAIM_COUNT_WORD = r"(?:one|ones|two|three|ten|',
     "guard", 'brief-claim: test-author brief where main refuses all five'),
    ('brief-claim: these is no referent lead, so refuses these ones hides',
     r'r"\b(?:both|all|each|these)\s+(?:" + _CLAIM_COUNT_WORD',
     r'r"\b(?:both|all|each)\s+(?:" + _CLAIM_COUNT_WORD',
     "guard", 'brief-claim: test-author brief where main refuses these ones'),
    ('brief-claim: both is no referent lead, so refuses both now hides',
     r'r"\b(?:both|all|each|these)\s+(?:" + _CLAIM_COUNT_WORD',
     r'r"\b(?:all|each|these)\s+(?:" + _CLAIM_COUNT_WORD',
     "guard", 'brief-claim: test-author brief where main refuses both now'),
    ('brief-claim: a count word that is not at the clause end still refers, so main passes all three tests takes two inputs',
     r'\b(?:\s+(?:today|now)\b)?|(?:today|now)\b)[\s.!?:;,)]*$"',
     r'\b(?:\s+(?:today|now)\b)?|(?:today|now)\b)"',
     "guard", 'brief-claim: test-author brief where main passes all three tests, after two inputs'),
    ('brief-claim: a pronoun tail reads the inputs before the verb, so refuses it after an input takes none',
     '''    if not claimed and not passive and refers:   # "Edit `x`, because main refuses it."
        claimed = [item for at, item in marks if lo <= at < hi]''',
     '''    if not claimed and not passive and refers:   # "Edit `x`, because main refuses it."
        claimed = [item for at, item in marks if clause.end() <= at < hi]''',
     "guard", 'brief-claim: test-author brief where main refuses it, after an input in the same sentence'),
    ('brief-claim: a pronoun tail reads the inputs from the start of the sentence, so a fixed input is claimed',
     '''    if not claimed and not passive and refers:   # "Edit `x`, because main refuses it."
        claimed = [item for at, item in marks if lo <= at < hi]''',
     '''    if not claimed and not passive and refers:   # "Edit `x`, because main refuses it."
        claimed = [item for at, item in marks if 0 <= at < hi]''',
     "guard", 'brief-claim: test-author brief where main refuses it after a fixed input is allowed'),
    ('brief-claim: a pronoun tail reads the inputs past the next break, so a verdict command is claimed',
     '''    if not claimed and not passive and refers:   # "Edit `x`, because main refuses it."
        claimed = [item for at, item in marks if lo <= at < hi]''',
     '''    if not claimed and not passive and refers:   # "Edit `x`, because main refuses it."
        claimed = [item for at, item in marks if lo <= at < len(sentence)]''',
     "guard", 'brief-claim: test-author brief where main refuses it, then a verdict command, is allowed'),
    ('brief-claim: the refers test reads the inputs before the clause, so a kept input is claimed',
     '    refers = _claim_refers(sentence[first:last])',
     '    refers = _claim_refers(sentence[lo:hi])',
     "guard", 'brief-claim: test-author brief where main passes CI for a kept input is allowed'),
    ('brief-claim: the refers test reads the rest of the sentence, so an edit that keeps it is claimed',
     '    refers = _claim_refers(sentence[first:last])',
     '    refers = _claim_refers(sentence[first:])',
     "guard", 'brief-claim: test-author brief where main passes CI, and an edit keeps it green, is allowed'),
    ('brief-claim: the same-sentence pronoun tail is off, so refuses it after an input hides',
     '    if not claimed and not passive and refers:',
     '    if not claimed and refers and False:',
     "guard", 'brief-claim: test-author brief where main refuses it, after an input in the same sentence'),
    ('brief-claim: the before path reads the pronoun only, so refuses all three today with inputs before hides',
     '    return [], "before" if refers else None',
     '    return [], "before" if BRIEF_CLAIM_REFERENT.search(sentence[first:last]) else None',
     "guard", 'brief-claim: test-author brief where main refuses all three today'),
    ('brief-claim: a claim with no referent takes the inputs before it, so main passes all tests is claimed',
     '    return [], "before" if refers else None',
     '    return [], "before"',
     "guard", 'brief-claim: test-author brief where main passes all three tests, after two inputs'),
    ('brief-claim: the today form wins only when it starts after the leading claim, so a later subject with today is missed',
     '        if subject is not None and (clause is None or subject.start() < clause.start()):',
     '        if subject is not None and (clause is None or subject.start() > clause.start()):',
     "guard", 'brief-claim: test-author brief where the guard refuses an input today, and main refuses a second'),
    ('brief-claim: the today form wins only when no leading claim exists, so a leading main claim hides the today subject',
     '        if subject is not None and (clause is None or subject.start() < clause.start()):',
     '        if subject is not None and clause is None:',
     "guard", 'brief-claim: test-author brief where the guard refuses an input today, and main refuses a second'),
    ('brief-claim: only the first today is read, so a leading Today frame hides the later today subject',
     '    for late in BRIEF_CLAIM_TODAY.finditer(sentence):\n        pass\n',
     '    for late in BRIEF_CLAIM_TODAY.finditer(sentence):\n        break\n',
     "guard", 'brief-claim: test-author brief where today we know the guard refuses an input today is denied'),
    ('brief-claim: today is case-sensitive, so a subject with TODAY in capitals is missed',
     'BRIEF_CLAIM_TODAY = re.compile(r"\\btoday\\b", re.IGNORECASE)',
     'BRIEF_CLAIM_TODAY = re.compile(r"\\btoday\\b")',
     "guard", 'brief-claim: test-author brief where the guard refuses an input in capitals TODAY is denied'),
    ('brief-claim: the today subject is dropped, so the subject-first form never claims',
     '    return clause\n\n\ndef _claim_clause',
     '    return None\n\n\ndef _claim_clause',
     "guard", 'brief-claim: test-author brief where main refuses all three today'),
]


# REPORT MODE. File -> the suites that exercise it or name it. A suite not listed here (merge/test_merge.py,
# lint/test_ci_scope.py) is not run against that file: test_merge.py takes minutes per mutant, and
# test_ci_scope.py only passes the file's path to the scope detector. hooks/test_guard.py runs only as the
# families of GUARD_MODULE_FAMILIES, or whole against REPORT_GOLD's file: a whole run takes minutes per mutant.
# Add a verdict-deciding file here, with the suites that name it, to put it in the report.
REPORT_TARGETS = [
    ("lint/report_guard.py", ["lint/test_report_guard.py", "lint/test_report_guard_route.py",
                             "lint/test_report_guard_stamped.py",
                             "lint/test_report_guard_landing.py",
                             "lint/test_report_guard_refusal.py", "lint/test_report_guard_handoff.py",
                             "lint/test_report_guard_cannot.py",
                             "lint/test_report_guard_remedy.py",
                             "hooks/test_reply_judge.py", "hooks/test_wrappers.py",
                             "lint/test_rule_audit.py", "lint/test_settings_matcher.py"]),
    ("lint/_clause.py", ["lint/test_clause.py", "lint/test_report_guard_cannot.py", "lint/test_report_guard.py"]),
    ("hooks/feedback_guard.py", ["hooks/test_feedback_inbox.py", "lint/test_settings_matcher.py"]),
    ("hooks/stall_watch.py", ["hooks/test_stall_watch.py", "hooks/test_stall_watch_stop.py",
                              "hooks/test_wrappers.py", "lint/test_hook_platform_exit.py",
                              "janitor/test_session_end_sweep.py", "lint/test_settings_matcher.py"]),
    ("lint/check_silent_undo.py", ["lint/test_check_silent_undo.py"]),
]
# hooks/guard_<x>.py -> the families of hooks/test_guard.py (FAMILIES there) that exercise it. `--tests-for` prints a row as
# `hooks/test_guard.py::<family>` lines beside the other suites that load the module, which the engine runs with
# GUARD_FAMILY=<family> for a family line. A mutant meets only the families that reach its module, since the whole file takes
# minutes. A guard module is a row, REPORT_GOLD's file, or in
# GUARD_MODULE_EXEMPT (a test checks this).
GUARD_MODULE_FAMILIES = {
    "hooks/guard_kill.py": ["kill", "git-env"],
    "hooks/guard_env.py": ["env", "git-env"],
    "hooks/guard_frozen.py": ["frozen"],
    "hooks/guard_pointer.py": ["pointer"],
    "hooks/guard_rm_var.py": ["rm-var"],
    "hooks/guard_shared_tree.py": ["shared-tree"],
    "hooks/guard_stream.py": ["stream"],
    "hooks/guard_push_delete.py": ["push-delete"],
    "hooks/guard_branch_worktree.py": ["branch-worktree"],
    "hooks/guard_merge.py": ["merge"],
    "hooks/guard_mask_script.py": ["mask-script"],
    "hooks/guard_argv.py": ["argv"],
}
GUARD_MODULE_EXEMPT = {
    "hooks/guard_core.py": "shared by every family, so a mutant of it needs the whole test_guard.py, which takes minutes",
}
# The gold standard: the guard's own suite against the same mechanical mutants, so the comparison is
# one engine to one engine. The hand-written MUTATIONS above kill 100% by construction (any survivor
# fails the CI job), which an ast sample of other files cannot be held against.
REPORT_GOLD = ("hooks/guard_wsl.py", ["hooks/test_guard.py"])
REPORT_LIMIT = 10  # mutants per file: the slowest suite (hooks/test_stall_watch.py) takes 150 s a run


def report_main(argv) -> int:
    """Print the per-file score table. Exit 0 whatever the scores: a report is not a check."""
    import argparse
    parser = argparse.ArgumentParser(prog="mutate_guard.py --report")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--limit", type=int, default=REPORT_LIMIT)
    parser.add_argument("--jobs", type=int, default=None)
    parser.add_argument("--only", default="", help="run only the targets whose path holds this text")
    args = parser.parse_args(argv)
    root = os.path.dirname(HERE)
    rows = []
    for target, tests in REPORT_TARGETS + [REPORT_GOLD]:
        if args.only not in target:
            continue
        print("scoring %s against %d suites ..." % (target, len(tests)), flush=True)
        rows.append(mutate_shared.score_target(root, target, tests, limit=args.limit, jobs=args.jobs))
        print(mutate_shared.format_report(rows[-1:]), flush=True)  # a killed run keeps the files already scored
    gold = [row for row in rows if row["file"] == REPORT_GOLD[0]]
    note = "unmeasured (not run)" if not gold else (
        "UNKNOWN (%s)" % gold[0]["reason"] if gold[0]["status"] != "OK"
        else "%s kills %d%% of its mutants (%s)" % (gold[0]["file"], round(gold[0]["rate"] * 100),
                                                     ", ".join(REPORT_GOLD[1])))
    print()
    print(mutate_shared.format_report(rows, gold=note))
    return 0


# REPLAY MODE. Repository -> how to read it (the profile keys are in hooks/mutate_shared.py). Each profile
# was measured on its repository: the suite times, and which suites are green on a clean checkout.
# q_max: one `node --test` file runs 0 to 15 s; harness/tests/checks-known-bad.test.mjs runs past 300 s,
# so it reads unusable under the suite timeout.
# banchi: the TypeScript tier runs through the Playwright unit config (the `unit` script of app/package.json),
# one file as a path argument. Its Python harness (harness/run.py) has no per-module runner of its own, so
# the runner below imports one harness/tests/tN_*.py and calls its `run()` under `isolated_home()`, as
# run.py does. A module is a suite only when it is green on a clean checkout: T6 needs demo-assets/ (its
# photos are left out of the checkout), so it reads unusable. T7 is minutes long whole, so a changed T7 group
# module, harness/tests/t7/<group>.py, is a suite of its own when it defines CHECKS (`suite_filter` below; a
# helper without CHECKS is none). Its runner loads harness/tests/t7_store_and_seams.py and calls its `run()` with
# an `order` that keeps only that group's checks, so they run in T7's order, each inside T7's hermetic().
# A failed or missing select runs every changed suite.
# mailaudit: suites are plain node scripts. check-docs, check-records, ci-wiring, milestone-due and send-key print
# FAIL on red; rules, golden, view-rules, worker/core, photoget and app print only a cross mark, so they cannot kill
# until mailaudit prints FAIL. app.test runs past the suite timeout, so it reads unusable.
# home: parts js and py. The addon is left out: it has no requirements or lock file, its pins sit inline in its
# workflow.
# ios_adblock: parts node and shell. Left out: test_chrome_slice.sh (TAP, covered by the node part),
# test_build_rules.sh and test_export_lists.sh (zsh), test_merge_chunks.sh (needs macOS Swift). The shell suites
# print FAIL on red.
# joyous: no-public-price, redirects, phone-first and tour-pages need dist/ or a browser, so they read unusable.
# degen: py only. The app/ Playwright specs need a browser, so they are left out. test_ig_spike*.py is red on a
# clean checkout. The install reads requirements-all.txt (runtime and dev pins, one flat file), so a module that
# imports dev-only pins (PyYAML, openapi_core, jsonschema) installs. A commit before that file landed reads "no lockfile".
BANCHI_MODULE_RUNNER = """\
import importlib, os, sys
sys.path.insert(0, os.getcwd())
from harness.tests.home import isolated_home
name = sys.argv[1][:-3].replace('/', '.')
group = name.startswith('harness.tests.t7.')
with isolated_home():
    if group:
        t7 = importlib.import_module('harness.tests.t7_store_and_seams')
        wanted = tuple(importlib.import_module(name).CHECKS)
        result = t7.run(order=lambda todo: [check for check in todo if check in wanted])
    else:
        result = importlib.import_module(name).run()
passed = getattr(result, 'passed', None)
if passed is not True and passed is not False:
    raise TypeError('run() returned no Result with a bool passed: %r' % (result,))
if not passed:
    print('FAIL: ' + name)
    print(result.detail)
    sys.exit(1)
"""
# banchi's per-file selector (scripts/tests-for.py), named by both parts. A commit that lacks the script has no
# copy in its checkout, so a replay reads the clone's HEAD copy (`_select_suites`, hooks/mutate_shared.py).
BANCHI_SELECT = ["python3", "scripts/tests-for.py", "{path}"]
HOME_SELECT = ["node", "scripts/tests-for.mjs", "{path}"]
IOS_ADBLOCK_SELECT = ["node", "scripts/tests-for.mjs", "{path}"]
REPLAY_PROFILES = {
    # claude_settings: the CI report (`--changed`) reads this repository by it. A suite is a `test_*.py` file anywhere;
    # `--tests-for` (below) names the suites of a file. No install: the suites use the standard library.
    # Product code is a `.py` file under hooks, lint, merge, janitor, actions or skills. `code_not` excludes a file named
    # `test_*.py` or `_test_*.py`, and any file under a folder named exactly `test`, `tests`, `fixture` or `fixtures`.
    # A `*_test.py` file or a folder such as `fixtures_cli` stays product.
    "claude_settings": {
        "code": r"^(hooks|lint|merge|janitor|actions|skills)/.*\.py$",
        "code_not": r"(^|/)(test_|_test_)[^/]*\.py$|(^|/)tests?/|(^|/)fixtures?/",
        "tests": r"(^|/)test_[^/]*\.py$",
        "argv": ["python3", "{suite}"], "classify": "fail_line", "install": None, "sparse_skip": [],
        "select": ["python3", "hooks/mutate_guard.py", "--tests-for", "{path}"],
    },
    "q_max": {
        "code": r"^(src|harness|app)/.*\.(ts|tsx|mts|mjs|js)$", "code_not": r"^harness/tests/|\.(test|spec)\.(mjs|js|ts|tsx|mts)$",
        "tests": r"^harness/tests/[^/]+\.test\.mjs$",
        "argv": ["node", "--test", "--test-reporter=tap", "{suite}"], "classify": "node_tap",
        "install": ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"],
        "lockfile": "package-lock.json", "sparse_skip": [],
        "select": ["node", "harness/tests-for.mjs", "{path}"],
    },
    "banchi": {"parts": {
        "ts": {
            "code": r"^app/src/.*\.(ts|tsx)$", "tests": r"^app/tests/unit/[^/]+\.unit\.ts$",
            "argv": ["node", "node_modules/@playwright/test/cli.js", "test", "-c", "playwright.unit.config.ts",
                     "{suite}"],
            "classify": "playwright", "cwd": "app",
            "install": ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"], "lockfile": "app/package-lock.json",
            "sparse_skip": ["demo-assets", "vendor"], "select": BANCHI_SELECT,
        },
        "py": {
            "code": r"^(?!harness/tests/).*\.py$", "code_not": r"^scripts/(.*/)?[^/]*selftest\.py$",
            "tests": r"^harness/tests/(t\d+_[^/]*|t7/[^/]+)\.py$",
            "suite_filter": {"paths": r"^harness/tests/t7/", "keep": "defines_checks"},
            "argv": ["{deps}/venv/bin/python", "-c", BANCHI_MODULE_RUNNER, "{suite}"], "classify": "fail_line",
            "install": [[sys.executable, "-m", "venv", "{deps}/venv"],
                        ["{deps}/venv/bin/pip", "install", "--quiet", "--disable-pip-version-check", "-r",
                         "requirements.txt"]],
            "lockfile": "requirements.txt", "link": None, "sparse_skip": ["demo-assets", "vendor"],
            "select": BANCHI_SELECT,
        },
    }},
    "mailaudit": {
        "code": r"^(src/[^/]+\.(mjs|jsx)|worker/[^/]+\.mjs|scripts/[^/]+\.mjs|build\.mjs|check-[^/]+\.mjs)$",
        "code_not": r"\.test\.mjs$", "tests": r"^(test/[^/]+|worker/core)\.test\.mjs$",
        "argv": ["node", "{suite}"], "classify": "fail_line",
        "install": ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"], "lockfile": "package-lock.json",
        "sparse_skip": [], "select": ["node", "scripts/tests-for.mjs", "{path}"],
    },
    "home": {"parts": {
        "js": {
            "code": r"^(web|tools)/[^/]+\.(js|mjs)$", "code_not": r"\.test\.(js|mjs)$",
            "tests": r"^(web/[^/]+\.test\.js|tools/[^/]+\.test\.mjs)$",
            "argv": ["node", "--test", "--test-reporter=tap", "{suite}"], "classify": "node_tap", "install": None,
            "sparse_skip": [], "select": HOME_SELECT,
        },
        "py": {
            "code": r"^tools/[^/]+\.py$", "code_not": r"(^|/)test_[^/]*\.py$", "tests": r"^tools/test_[^/]*\.py$",
            "argv": ["python3", "{suite}"], "classify": "fail_line", "install": None, "sparse_skip": [],
            "select": HOME_SELECT,
        },
    }},
    "ios_adblock": {"parts": {
        "node": {
            "code": r"^chrome/(build\.mjs|slice\.mjs|src/[^/]+\.js)$", "tests": r"^chrome/test/[^/]+\.test\.mjs$",
            "argv": ["node", "--test", "--test-reporter=tap", "{suite}"], "classify": "node_tap",
            "install": ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"],
            "lockfile": "chrome/package-lock.json", "sparse_skip": [], "select": IOS_ADBLOCK_SELECT,
        },
        "shell": {
            "code": r"^(chrome/check\.mjs|ios/WebExtension/src/(background|content|strictmode)\.js)$",
            "tests": r"^tests/test_(chrome_check|content_early|strictmode)\.sh$",
            "argv": ["bash", "{suite}"], "classify": "fail_line", "install": None, "sparse_skip": [],
            "select": IOS_ADBLOCK_SELECT,
        },
    }},
    "joyous": {
        "code": r"^src/.*\.(ts|tsx|mts|mjs|js)$", "code_not": r"^tests/|\.(test|spec)\.(mjs|js|ts|tsx|mts)$",
        "tests": r"^tests/(?:[^/]+\.test\.mjs|[^/]+/[^/]+\.test\.ts)$",
        "argv": ["node", "--experimental-strip-types", "--test", "--test-reporter=tap", "{suite}"],
        "classify": "node_tap",
        "install": ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"], "lockfile": "package-lock.json",
        "sparse_skip": [], "select": ["node", "scripts/tests-for.mjs", "{path}"],
    },
    "degen": {
        "code": r"^server/(?:[^/]+/)*[^/]+\.py$", "tests": r"^tests/(?!(?:web|tokens)/).*test_[^/]*\.py$",
        "argv": ["env", "FEED_FREE_FLOOR_GB=0", "{deps}/venv/bin/python", "-m", "unittest", "{suite}"],
        "classify": "fail_line",
        "install": [[sys.executable, "-m", "venv", "{deps}/venv"],
                    ["{deps}/venv/bin/pip", "install", "--quiet", "--disable-pip-version-check", "-r",
                     "requirements-all.txt"]],
        "lockfile": "requirements-all.txt", "link": None, "sparse_skip": [],
        "select": ["python3", "scripts/tests-for.py", "{path}"],
    },
}


@contextlib.contextmanager
def stop_on_signals():
    """SIGTERM and SIGINT become an exit, so the `finally` blocks of the caller run: the suite groups are killed first, then
    the caller removes its checkouts. The handlers and the stop flag are put back on the way out."""
    def stop(signum, _frame):
        mutate_shared.request_stop()
        raise SystemExit(128 + signum)

    saved = {}
    try:
        for number in (signal.SIGTERM, signal.SIGINT):
            saved[number] = signal.signal(number, stop)
    except ValueError:  # not the main thread: no handler, the default stays
        pass
    try:
        yield
    finally:
        for number, handler in saved.items():
            signal.signal(number, handler)
        mutate_shared.clear_stop()


def replay_main(argv) -> int:
    """Replay the last merged pull requests of a repository, print each row as it ends, then the table.
    Exit 0 whatever the scores: a replay is not a check. A bad argument is the only nonzero exit."""
    import argparse
    parser = argparse.ArgumentParser(prog="mutate_guard.py --replay")
    parser.add_argument("--replay", required=True, metavar="REPO", help="a clone of the repository to replay")
    parser.add_argument("--profile", required=True, choices=sorted(REPLAY_PROFILES))
    parser.add_argument("--prs", type=int, default=20, help="how many of the newest merged pull requests")
    parser.add_argument("--limit", type=int, default=20, help="mutants per pull request")
    parser.add_argument("--suite-timeout", type=float, default=120, help="seconds before a suite run is killed")
    parser.add_argument("--jobs", type=int, default=None)
    parser.add_argument("--pr-budget", type=float, default=None, metavar="SECONDS",
                        help="mutants not started this long after a pull request began count as not_run")
    args = parser.parse_args(argv)
    repo = os.path.abspath(args.replay)
    try:
        prs = mutate_shared.merged_prs(repo, "HEAD", args.prs)
    except ValueError as error:
        print("ERROR %s" % error)
        return 2
    profile = REPLAY_PROFILES[args.profile]
    print("replaying %d merged pull requests of %s with profile %s" % (len(prs), repo, args.profile), flush=True)
    deps = tempfile.mkdtemp(prefix="mutate_deps_")
    rows = []
    with stop_on_signals():
        try:
            for sha, _number, _title in prs:
                for row in mutate_shared.replay_profile(repo, sha, profile, limit=args.limit,
                                                        suite_timeout=args.suite_timeout, jobs=args.jobs, deps=deps,
                                                        pr_budget=args.pr_budget,
                                                        progress=lambda line: print(line, flush=True)):
                    rows.append(row)
                    print(mutate_shared.format_replay_row(row), flush=True)  # a killed run keeps the rows already scored
        finally:
            shutil.rmtree(deps, ignore_errors=True)
    print()
    print(mutate_shared.format_replay(rows))
    return 0


def add_profile_group(parser) -> None:
    """The required choice of `--profile NAME` or `--profile-file JSON` that `--changed` and `--known-defects` share. Read it with `load_profile`."""
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--profile", choices=sorted(REPLAY_PROFILES))
    which.add_argument("--profile-file", metavar="JSON", help="a profile as a JSON file, in place of a named one")


def load_profile(args) -> dict:
    """The profile `add_profile_group` chose. A file that cannot be read raises OSError, or ValueError when it is no JSON or no object."""
    import json
    if not args.profile_file:
        return REPLAY_PROFILES[args.profile]
    with open(args.profile_file, encoding="utf-8") as handle:
        profile = json.load(handle)
    if not isinstance(profile, dict):
        raise ValueError("the profile file %s does not hold a JSON object" % args.profile_file)
    return profile


def changed_main(argv) -> int:
    """The CI report of a change: mutate the product lines it adds past the merge base, run the suites the profile's `select`
    lists for each file, print the replay row, `catch share: K/R` and each `untested: path:line`. Exit 1 when mutants were made
    and none ran, or when none ran because the run stopped first (`no_run_cause` in `replay_pr`'s row), after a
    `no mutant ran: ...` line that names the cause. Exit 0 otherwise, whatever the share: a low share is a report, never a
    failure. `--budget` is a wall deadline (see `replay_pr`, `wall_deadline`). A bad argument, or a ref the repository cannot read, exits 2."""
    import argparse
    import json
    parser = argparse.ArgumentParser(prog="mutate_guard.py --changed")
    parser.add_argument("--changed", required=True, metavar="REPO", help="a clone of the repository holding the change")
    add_profile_group(parser)
    parser.add_argument("--base", required=True, help="the ref the change is cut from: the lines past its merge base with --head")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--limit", type=int, default=20, help="mutants in all")
    parser.add_argument("--budget", type=float, default=None, metavar="SECONDS",
                        help="a wall deadline: after this long from the start of the run, suites still running are killed and "
                             "mutants not finished count as not_run")
    parser.add_argument("--suite-timeout", type=float, default=120, help="seconds before a suite run is killed")
    parser.add_argument("--jobs", type=int, default=None)
    parser.add_argument("--log", default=None, metavar="PATH", help="write the totals as one JSON file")
    args = parser.parse_args(argv)
    repo = os.path.abspath(args.changed)
    try:
        profile = load_profile(args)
        head = mutate_shared._git(repo, "rev-parse", "--verify", "--quiet", "%s^{commit}" % args.head).strip()
        base = mutate_shared._git(repo, "merge-base", args.base, head).strip()
    except (OSError, ValueError) as error:  # a JSONDecodeError is a ValueError
        print("ERROR %s" % error)
        return 2
    print("scoring the lines %s adds past %s in %s" % (head[:8], base[:8], repo), flush=True)
    deps = tempfile.mkdtemp(prefix="mutate_deps_")
    with stop_on_signals():
        try:
            rows = mutate_shared.replay_profile(repo, head, profile, limit=args.limit, suite_timeout=args.suite_timeout,
                                                jobs=args.jobs, deps=deps, pr_budget=args.budget, base=base,
                                                select_all=True, wall_deadline=True,
                                                progress=lambda line: print(line, flush=True))
        finally:
            shutil.rmtree(deps, ignore_errors=True)
    print()
    print(mutate_shared.format_changed(rows))
    if args.log:
        total = mutate_shared.changed_summary(rows)
        total.update({"base": base, "head": head, "profile": args.profile or args.profile_file})
        with open(args.log, "w", encoding="utf-8") as handle:
            json.dump(total, handle, indent=1)
    made = sum(row.get("made", 0) for row in rows)
    not_run = sum(row.get("not_run", 0) for row in rows)
    # A run that stopped before any mutant ran is a run where no mutant ran, whatever its count. A part that ran mutants
    # keeps the exit 0 of a run in which some mutant ran: the rule is that no mutant ran at all.
    stopped = [row["no_run_cause"] for row in rows if row.get("no_run_cause")]
    if made - not_run == 0 and stopped:
        print("no mutant ran: %s" % "; ".join(stopped))
        return 1
    if made > 0 and made - not_run == 0:
        why = ("the budget ran out, or no selected suite reaches the changed files" if args.budget is not None
               else "no selected suite reaches the changed files")
        print("no mutant ran: %d of %d mutants not run (%s)" % (not_run, made, why))
        return 1
    return 0


def _known_defects_base_entries(repo: str, list_path: str, base: str):
    """(entries, problem) of the list that REF holds at the path of `list_path` in `repo`, read with git so a head that edits
    the file cannot hide an entry. entries is None when the base cannot be read; problem is then `(verdict, text)`, the
    verdict UNKNOWN or ERROR. A ref that resolves but holds no list file has no entries (the first adoption of the list)."""
    import json
    rel = os.path.relpath(os.path.realpath(list_path), os.path.realpath(repo))
    if rel == os.pardir or rel.startswith(os.pardir + os.sep) or os.path.isabs(rel):
        return None, ("UNKNOWN", "%s: the list is outside the repository, so its base list cannot be read" % list_path)
    spec = "%s:./%s" % (base, rel.replace(os.sep, "/"))
    try:
        mutate_shared._git(repo, "rev-parse", "--verify", "-q", base + "^{commit}")
    except ValueError:
        return None, ("UNKNOWN", "%s: the base ref does not resolve, so no base list was compared" % base)
    try:
        mutate_shared._git(repo, "cat-file", "-e", spec)
    except ValueError:
        return [], None
    try:
        entries = json.loads(mutate_shared._git(repo, "show", spec))
        if not isinstance(entries, list):
            raise ValueError("the top level is not a list")
    except ValueError as error:
        return None, ("ERROR", "cannot read %s: %s" % (spec, error))
    for position, entry in enumerate(entries, 1):
        if not isinstance(entry, dict) or "id" not in entry:
            return None, ("UNKNOWN", "%s: entry %d of the base list has no id, so a drop of it could not be told" % (spec, position))
    return entries, None


def known_defects_main(argv) -> int:
    """Replay the planted defects of a list (`.github/known-defects.json`) against a repository's HEAD. One line per defect:
    `CAUGHT`, `MISS` or `UNKNOWN`. Exit 1 when any defect is MISS or UNKNOWN (decision ci-unknown-is-red). A missing list file
    prints one UNKNOWN line that names its path and exits 1; an empty list exits 0 (with `--base`, only when REF's list names
    no entry); a list or a profile that cannot be read exits 2.
    `--profile` or `--profile-file` is required: the checkout gets the profile's install, as `--changed` does.
    With `--base REF` the head list is also compared with the list at REF (decision mutation-ci-report-and-replay): each id
    there needs a result row, unless a commit in REF..HEAD carries the exact trailer `Known-defect-removed: <id>`, else
    `MISSING <id>` prints and the exit is 1. An id on both lists whose entries differ as parsed objects (key order and
    spacing do not count; two head entries with one id differ unless both equal the base entry) prints `CHANGED <id>` and
    exits 1, unless a commit in REF..HEAD carries `Known-defect-changed: <id>`; the two keys are not interchangeable. A ref that does not resolve, or a list outside the repository, is UNKNOWN (exit
    1); a ref with no list file has nothing to compare; a base list that cannot be read exits 2. A base entry that is not an
    object or has no `id` is UNKNOWN (exit 1), never skipped. One trailer line names one id."""
    import argparse
    import json
    parser = argparse.ArgumentParser(prog="mutate_guard.py --known-defects")
    parser.add_argument("--known-defects", dest="list_path", required=True, metavar="FILE",
                        help="a JSON list of planted defects")
    parser.add_argument("--repo", required=True, help="a clone of the repository the defects are planted in")
    add_profile_group(parser)
    parser.add_argument("--base", default=None, metavar="REF",
                        help="a git ref whose list the head list must not drop an id from, unless a commit names it in a trailer")
    parser.add_argument("--suite-timeout", type=float, default=120, help="seconds before a suite run is killed")
    parser.add_argument("--log", default=None, metavar="PATH", help="write the results as one JSON file")
    args = parser.parse_args(argv)
    if not os.path.exists(args.list_path):
        print("UNKNOWN %s: the known-defects list is missing, so no planted defect was replayed" % args.list_path)
        return 1
    try:
        with open(args.list_path, encoding="utf-8") as handle:
            defects = json.load(handle)
        if not isinstance(defects, list):
            raise ValueError("the top level is not a list")
    except (OSError, ValueError) as error:
        print("ERROR cannot read %s: %s" % (args.list_path, error))
        return 2
    try:
        profile = load_profile(args)
    except (OSError, ValueError) as error:  # a JSONDecodeError is a ValueError
        print("ERROR %s" % error)
        return 2
    base_entries = []
    if args.base:
        base_entries, problem = _known_defects_base_entries(args.repo, args.list_path, args.base)
        if problem:
            print("%s %s" % problem)
            return 2 if problem[0] == "ERROR" else 1
    deps = tempfile.mkdtemp(prefix="mutate_deps_")
    with stop_on_signals():
        try:
            results = mutate_shared.run_known_defects(os.path.abspath(args.repo), defects, profile, deps,
                                                      suite_timeout=args.suite_timeout)
        finally:
            shutil.rmtree(deps, ignore_errors=True)
    print(mutate_shared.format_known_defects(results))
    missing, changed = [], []
    if base_entries:
        try:
            # One read serves both keys; `unfold` keeps each trailer on one `Key: value` line.
            trailers = mutate_shared._git(
                args.repo, "log", "--format=%(trailers:key=Known-defect-removed,key=Known-defect-changed,unfold)",
                "%s..HEAD" % args.base)
        except ValueError as error:
            print("UNKNOWN %s..HEAD: the commits could not be read for Known-defect trailers (%s)" % (args.base, error))
            return 1
        named = {"known-defect-removed": set(), "known-defect-changed": set()}
        for line in trailers.splitlines():
            key, _, value = line.partition(":")
            if key.strip().lower() in named:
                named[key.strip().lower()].add(value.strip())
        removed, excused = named["known-defect-removed"], named["known-defect-changed"]
        listed = {result["id"] for result in results}
        base_by_id = {}
        for entry in base_entries:
            base_by_id.setdefault(str(entry["id"]), []).append(entry)
        head_by_id = {}
        for entry in defects:
            head_by_id.setdefault(str(entry.get("id", "?")) if isinstance(entry, dict) else "?", []).append(entry)
        missing = sorted(set(base_by_id) - listed - removed)
        changed = sorted(known_id for known_id, base_rows in base_by_id.items()
                         if known_id in listed and known_id not in excused
                         and (any(row not in base_rows for row in head_by_id.get(known_id, []))
                              or any(row not in head_by_id.get(known_id, []) for row in base_rows)))
        for known_id in missing:
            print("MISSING %s: %s lists it, the head list has no row for it, and no commit in %s..HEAD has the trailer "
                  "`Known-defect-removed: %s` (one id per line, in the message's last block, beside Co-Authored-By)"
                  % (known_id, args.base, args.base, known_id))
        for known_id in changed:
            print("CHANGED %s: the head entry differs from the one %s lists, and no commit in %s..HEAD has the trailer "
                  "`Known-defect-changed: %s` (one id per line, in the message's last block, beside Co-Authored-By)"
                  % (known_id, args.base, args.base, known_id))
    if args.log:
        with open(args.log, "w", encoding="utf-8") as handle:
            json.dump({"repo": os.path.abspath(args.repo), "defects": results, "missing": missing, "changed": changed},
                      handle, indent=1)
    return 1 if missing or changed or any(result["verdict"] != "CAUGHT" for result in results) else 0


def _loads_module(source: str, stem: str) -> bool:
    """True when the Python text imports or loads the module `stem`, read from its `ast` tree (never its text, so a comment,
    a string or a docstring that names the module is not a load). The forms: `import`, `from ... import`,
    `importlib.import_module` and `__import__` with a literal name, and `spec_from_file_location`, `SourceFileLoader` and
    `runpy.run_path` with a string literal of the basename `<stem>.py` in the path argument (never the module-name argument),
    directly or through a name bound to such an expression by an assignment in any scope of the file (module, function or
    class level; one name bound in two scopes pools both values). A path that arrives as a function parameter is followed
    to the calls of that function in the same file: a call by a bare name, with the argument by position or by keyword
    for that parameter, counts as a binding of the parameter, read only inside the def that owns the parameter. Two functions
    with different names that share a parameter name keep their calls apart.
    Only the forms above are followed. Any other form reads False, and this list is not complete. Examples: a loader
    imported from another file, a wrapper that is called through another wrapper's parameter, an attribute call such as
    `obj.load(..., "widget.py")` or `self.load(...)`, a path parameter whose default holds the file when no call passes
    it (`def load(name, path=WIDGET)` called as `load("x")`), a lambda loader, a bare alias of the loader
    (`helper = load`), a loader that takes the path as `*args` or `**kwargs` (a `**kwargs` loader that copies the
    keyword into a local of the same name, `path = kwargs["path"]`, is followed; `p = kwargs["path"]` is not), a call
    that spreads the path in (a starred
    argument before it, as `load(*names, "widget.py")`, or `**{"path": ...}`), a name bound only as a `for` or
    comprehension target (`for path in ["widget.py"]`), and a name bound by tuple unpacking, augmented assignment,
    `with ... as` or an attribute store (`self.path = "widget.py"`). Also a class constructor that takes the path
    (`Loader("widget.py")`), `functools.partial(load, "widget.py")`, `map(load, [...])`, a walrus binding, and a split
    literal (`"widget" + ".py"`).
    Known false selections, so each reads True: a bare call `load(path=X)` also feeds a method `Loader.load` of the same
    name in the file, as every def of that name takes the call, and a loader that reassigns its path before the load reads
    the argument its calls pass, not the new value.

    It assumes module stems are unique across the repository, so a name match is a load of this file (only
    `test_action.py` repeats a stem today). A text that does not parse reads False."""
    import ast
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return False
    base = stem + ".py"
    bound = {}  # a name -> the expressions it is bound to, in any scope
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    bound.setdefault(target.id, []).append(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            bound.setdefault(node.target.id, []).append(node.value)

    parent = {}  # a node -> its parent, built with `fed` on the first file loader, so a file with none pays nothing
    fed = {}  # (a def, a parameter name) -> the argument expressions its calls pass for it

    def read_params() -> None:
        defs = {}  # a function name -> its defs, in any scope
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parent[child] = node
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defs.setdefault(node.name, []).append(node)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in defs:
                for function in defs[node.func.id]:
                    params = [arg.arg for arg in function.args.posonlyargs + function.args.args]
                    for index, value in enumerate(node.args):
                        if isinstance(value, ast.Starred):
                            break
                        if index < len(params):
                            fed.setdefault((function, params[index]), []).append(value)
                    for keyword in node.keywords:
                        if keyword.arg:
                            fed.setdefault((function, keyword.arg), []).append(keyword.value)

    def names_base(expr, seen, scope=()) -> bool:
        for part in ast.walk(expr):
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                if part.value.replace("\\", "/").rsplit("/", 1)[-1] == base:
                    return True
            elif isinstance(part, ast.Name):
                if part.id in bound and part.id not in seen:
                    seen.add(part.id)
                    if any(names_base(value, seen, scope) for value in bound[part.id]):
                        return True
                for function in scope:
                    key = (function, part.id)
                    if key in fed and key not in seen:
                        seen.add(key)
                        if any(names_base(value, seen) for value in fed[key]):
                            return True
        return False

    def last_part(dotted: str) -> bool:
        return dotted.rsplit(".", 1)[-1] == stem

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(last_part(alias.name) for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if (node.module and last_part(node.module)) or any(alias.name == stem for alias in node.names):
                return True
        elif isinstance(node, ast.Call):
            func = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            if func in ("import_module", "__import__"):
                first = node.args[0] if node.args else next((kw.value for kw in node.keywords if kw.arg == "name"), None)
                if isinstance(first, ast.Constant) and isinstance(first.value, str) and last_part(first.value):
                    return True
            elif func in ("spec_from_file_location", "SourceFileLoader", "run_path"):
                skip = 0 if func == "run_path" else 1  # the first argument of the other two is the module name
                parts = list(node.args[skip:]) + [kw.value for kw in node.keywords if kw.arg not in ("name", "fullname")]
                if not parent:
                    read_params()
                scope = []  # the defs around this call, innermost first: the parameters it can read
                up = parent.get(node)
                while up is not None:
                    if isinstance(up, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        scope.append(up)
                    up = parent.get(up)
                if any(names_base(part, set(), scope) for part in parts):
                    return True
    return False


def _guard_section_sources(tracked) -> list:
    """The text of each tracked `.py` file directly in the folder that the runner SUITE reads its guard sections from. The
    folder is the runner's SECTION_DIR, found by `rule_audit._section_dir`, the one home of that path. Empty when the runner
    names no folder. A file that cannot be read is skipped."""
    import ast
    lint = os.path.join(HERE, "..", "lint")
    if lint not in sys.path:
        sys.path.insert(0, lint)
    import rule_audit
    try:
        with open(SUITE, encoding="utf-8") as handle:
            folder = rule_audit._section_dir(ast.parse(handle.read()), SUITE)
    except (OSError, ValueError, SyntaxError):
        return []
    if not folder:
        return []
    rel = os.path.relpath(os.path.normpath(folder), os.path.dirname(HERE)).replace(os.sep, "/")
    sources = []
    for item in tracked:
        if os.path.dirname(item) != rel or not item.endswith(".py"):
            continue
        try:
            with open(item, encoding="utf-8") as handle:
                sources.append(handle.read())
        except (OSError, ValueError):
            continue
    return sources


def tests_for_main(argv) -> int:
    """Print the suites that test one file, a line each, sorted, once each. A file listed in REPORT_TARGETS prints exactly its
    suites. Any other `.py` file prints each tracked `test_<stem>.py` and `test_<stem>_*.py` beside it, plus each tracked
    `test_*.py` in the repository of the working folder that imports or loads its module (`_loads_module`). A guard section
    file (`_guard_section_sources`) that loads the module prints `hooks/test_guard.py`, its runner, in place of itself. A file
    with a row in GUARD_MODULE_FAMILIES prints that union with its `hooks/test_guard.py::<family>` lines, minus the plain whole
    `hooks/test_guard.py`. A non-`.py` file prints the suites beside it only. A suite that cannot be read or parsed is skipped.
    It is the `select` command of the `claude_settings` profile. A file with no suite prints nothing."""
    import argparse
    import re
    parser = argparse.ArgumentParser(prog="mutate_guard.py --tests-for")
    parser.add_argument("--tests-for", required=True, metavar="PATH", help="a repository-relative path")
    args = parser.parse_args(argv)
    path = os.path.normpath(args.tests_for).replace(os.sep, "/")
    listed = dict(REPORT_TARGETS)
    if path in listed:
        names = set(listed[path])
    else:
        folder, name = os.path.split(path)
        stem, extension = os.path.splitext(name)
        wanted = re.compile(r"test_%s(_[^/]*)?\.py" % re.escape(stem))
        done = _nowindow.run(["git", "ls-files", "-z"], capture_output=True, text=True,
                             encoding="utf-8", stdin=subprocess.DEVNULL)
        if done.returncode != 0:
            print("ERROR git ls-files failed: %s" % done.stderr.strip())
            return 2
        tracked = [item for item in done.stdout.split("\0") if item]
        names = {item for item in tracked
                 if os.path.dirname(item) == folder and wanted.fullmatch(os.path.basename(item))}
        if extension == ".py":
            for item in tracked:
                base = os.path.basename(item)
                if item in names or not (base.startswith("test_") and base.endswith(".py")):
                    continue
                try:
                    with open(item, encoding="utf-8") as handle:
                        source = handle.read()
                except (OSError, ValueError):
                    continue
                if _loads_module(source, stem):
                    names.add(item)
            # The runner reads each guard section file, so it stands for a section file that loads the module.
            if any(_loads_module(source, stem) for source in _guard_section_sources(tracked)):
                names.add("hooks/test_guard.py")
        if path in GUARD_MODULE_FAMILIES:
            # The whole `hooks/test_guard.py` loads every guard module and takes minutes per mutant, so only its families run.
            names.discard("hooks/test_guard.py")
            names.update("hooks/test_guard.py::%s" % family for family in GUARD_MODULE_FAMILIES[path])
    for name in sorted(names):
        print(name)
    return 0


def run_suite(suite: str, variable: str, copy_path: str, config_dir: str, only=None):
    """Run one fixture suite against one mutated copy. Return (exit code, FAIL lines, case lines,
    ERROR lines from `mutate_shared.diagnostic_lines`).

    The case lines are one per case run, passed or failed: `mutate_shared.staged_suite` reads them
    to know whether stage 1 ran the required case."""
    env = dict(os.environ)
    env.pop("GUARD_UNDER_TEST", None)
    env.pop("WATCH_UNDER_TEST", None)
    env.pop("DECISION_WATCH_UNDER_TEST", None)
    env.pop("RULING_HOME_UNDER_TEST", None)
    env.pop("CALL_JUDGE_UNDER_TEST", None)
    env[variable] = copy_path
    env["CLAUDE_CONFIG_DIR"] = config_dir
    env.pop("MUTATE_ONLY", None)
    if only:
        env["MUTATE_ONLY"] = only  # the suites run just the cases whose name holds this
    # stderr goes to a temp file, not a pipe: test_guard.py leaves a `sleep 300` that holds the suite's
    # stderr (spawn_live_parent), and run() waits for a pipe's EOF. Measured: every mutant took 306 s.
    # A file has no EOF to wait for. It is read after the run, only for unittest's ERROR blocks.
    with tempfile.TemporaryFile() as errors:
        result = _nowindow.run(
            # text=True keeps the default decoding: the child inherits env, so both sides share one encoding.
            [sys.executable, suite], stdout=subprocess.PIPE, stderr=errors, text=True,
            env=env, timeout=3600,  # interim stopgap, owner 12:11 CST Nov 10, decision ci-job-caps, ends with step time-pinned-tests-go
        )
        errors.seek(0)
        error_text = errors.read().decode("utf-8", "replace")
    lines = result.stdout.splitlines()
    red = [line for line in lines if line.startswith("FAIL")]
    # "PASS" and "FAIL" start each case line in every suite here; "ok " is test_call_judge.py's pass.
    ran = [line for line in lines if line.startswith(("PASS", "FAIL", "ok "))]
    return result.returncode, red, ran, mutate_shared.diagnostic_lines(result.stdout + "\n" + error_text)


def mutation_parts(entry):
    """Return (label, old, new, target, required, only_on) for one mutation.

    `target` defaults to "guard" for a 3-element entry, which is the shape every mutation
    written before the watch target existed still carries on disk until it is ported. `required`
    reads the same way for the port: absent on a 3- or 4-element entry.

    ONCE EVERY ENTRY CARRIES FIVE FIELDS, as they all do now, `required` is MANDATORY. A mutation
    with no required case name is as unproven as one that dies wrong: it says which rule breaks,
    but nothing checks that the suite's own red line is about THAT rule. The tolerant read above
    stays only so a future port has somewhere to land mid-edit; a caller that wants the field
    enforced asserts `len(entry) == 5` itself, which `run_mutant` below does.

    `only_on` is a SIXTH, optional field: "posix" or "windows", for a mutation whose broken code
    path only exists on one platform (e.g. `_process_start_ms`'s POSIX `ps` arm, never reached
    on Windows). Absent on every other entry, which runs on every platform as before.
    """
    label, old, new = entry[0], entry[1], entry[2]
    target = entry[3] if len(entry) > 3 else "guard"
    required = entry[4] if len(entry) > 4 else None
    only_on = entry[5] if len(entry) > 5 else None
    return label, old, new, target, required, only_on


def lay_out_guard_reads(root: str) -> None:
    """Copy into `root` the three files outside hooks/, lint/, janitor/ and skills/ that a copied guard family
    reads from beside its hooks folder: bin/sim-lease, the merge tool and the CI alarm's events. The folders
    lint/, janitor/ and skills/ come from the callers, through `tracked_tree.copy_tracked` (git's own list, so no
    file is hand-picked). The simulator refusal imports janitor/sweep.py and fails open without it.
    A guard copy gets its own `root`. The override copies sit one folder below `work`, so `main` calls this
    once on `work`. Cost (rule outcomes-mechanize-rules): per guard-family copy, three files (about 275 KB), and
    `main` makes one more under `work`. The folders copy_tracked lays out add git's list (225 files, about 4.8 MB,
    at this commit) to each copy. They stay until the run ends, when `work` is removed. Without these, arms that
    read them fail on every mutant alike, and the clean-layout control (`run_controls`) reads red."""
    os.makedirs(os.path.join(root, "bin"), exist_ok=True)
    shutil.copy(SIM_LEASE, os.path.join(root, "bin"))
    # guard_merge.py loads ../merge/merge.py (MERGE_TOOL_REL), which reads ../actions/ci-alarm/events.json (ALARM_EVENTS).
    os.makedirs(os.path.join(root, "merge"), exist_ok=True)
    shutil.copy(os.path.join(HERE, "..", "merge", "merge.py"), os.path.join(root, "merge"))
    os.makedirs(os.path.join(root, "actions", "ci-alarm"), exist_ok=True)
    shutil.copy(os.path.join(HERE, "..", "actions", "ci-alarm", "events.json"),
                os.path.join(root, "actions", "ci-alarm"))


def lay_out(sources, work: str, target: str, name: str, old: str, new: str) -> str:
    """Lay out one copy of `target` under `work` with `old` replaced by `new`, and return the path
    of the file its suite loads. `name` keys the copy's folder or file (through `mutate_shared.safe_name`).

    A mutant and its clean-layout control both go through here, so they differ only in the text:
    `old == new` is the control, the same layout with nothing mutated (see `run_controls`)."""
    stem = TARGETS[target][3]
    if target in ("guard", "simlease", "merge"):
        # The whole guard family goes in the mutant's own hooks folder, and the anchor lands in the one
        # module that holds it. The suite loads the copied guard.py, which finds its siblings.
        root = os.path.join(work, "%s_%s" % (stem, mutate_shared.safe_name(name)))
        tree = os.path.join(root, "hooks")
        mutate_shared.guard_tree(tree)
        lay_out_guard_reads(root)  # takes the original bin/sim-lease and merge/merge.py; a mutant of either overwrites it below
        if target == "simlease":
            with open(os.path.join(root, "bin", "sim-lease"), "w", encoding="utf-8", newline="\n") as handle:
                handle.write(sources[target].replace(old, new, 1))
        elif target == "merge":
            with open(os.path.join(root, "merge", "merge.py"), "w", encoding="utf-8", newline="\n") as handle:
                handle.write(sources[target].replace(old, new, 1))
        elif old != new:  # old == new is the clean-layout control: no anchor to find
            mutate_shared.apply_mutant(tree, old, new)
        copy_path = os.path.join(tree, "guard.py")
        # The guard family reads the folders beside its hooks folder as a checkout has them: ../lint (layout.py,
        # the role-model table: without it every role-model arm passes unjudged), ../janitor (the simulator
        # refusal fails open without sweep.py) and ../skills (waiting-page, impeccable). Git's own list of each
        # folder fills them, so a file the guard starts to read cannot be left out. git is read from the source
        # checkout, never from this scaffold.
        tracked_tree.copy_tracked(root, "lint", "janitor", "skills", root=os.path.dirname(HERE))
    else:
        copy_path = os.path.join(work, "%s_%s.py" % (stem, mutate_shared.safe_name(name)))
        mutated = sources[target].replace(old, new, 1)
    if target in ("ruling", "decision"):
        # ruling_home.py and decision_watch.py read `../lint/_transcript.py` beside itself. A bare copy in `work`
        # would crash on that import and read as red on every case, whatever was mutated
        # (a mutant's own cause of death must be checked). Lay out hooks/ and lint/ for the copy.
        tree = os.path.join(work, "tree_%s" % mutate_shared.safe_name(name))
        os.makedirs(os.path.join(tree, "hooks"), exist_ok=True)
        os.makedirs(os.path.join(tree, "lint"), exist_ok=True)
        shutil.copy(os.path.join(HERE, "..", "lint", "_transcript.py"), os.path.join(tree, "lint"))
        if target == "decision":
            mutate_shared.guard_tree(os.path.join(tree, "hooks"))
        copy_path = os.path.join(tree, "hooks", os.path.basename(TARGETS[target][0]))
    if target == "override":
        # The guard family, local_time.py and the mutated override.py share one folder: the
        # copied guard and the suite's grant child both import the override module beside guard.py.
        tree = os.path.join(work, "%s_%s" % (stem, mutate_shared.safe_name(name)))
        mutate_shared.guard_tree(tree)
        for helper in ("local_time.py", "_nowindow.py"):
            shutil.copy(os.path.join(HERE, helper), tree)
        with open(os.path.join(tree, "override.py"), "w", encoding="utf-8", newline="\n") as handle:
            handle.write(mutated)
        copy_path = os.path.join(tree, "guard.py")
    elif target == "calljudge":
        # call_judge.py imports guard_core and decision_watch beside itself: lay out the whole family.
        tree = os.path.join(work, "%s_%s" % (stem, mutate_shared.safe_name(name)))
        mutate_shared.guard_tree(tree)
        copy_path = os.path.join(tree, "call_judge.py")
        with open(copy_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(mutated)
    elif target not in ("guard", "simlease", "merge"):
        with open(copy_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(mutated)
    return copy_path


def run_controls(sources, work: str, entries):
    """Return {target: function} with one filtered control per target that has a mutation to run here.

    A control is `run_suite` on the unmutated layout, built by `lay_out` with an identity mutation and
    filtered to one required case of that target's own mutations (`run_control`). It answers one question:
    does this layout run its suite at all? A layout that crashes (a missing sibling module, a wrong path)
    fails every case whatever a mutant changed, and each FAIL line reads as a kill; one that exits 0 having
    run no case is the same crash seen from the other side.
    `mutate_shared.run_mutants` takes these functions as its `controls`: it runs them in the same pool as the
    mutants, ahead of them, under MUTATE_JOBS, and makes every mutant of a red, empty or raising target UNKNOWN
    (`mutate_shared.control_verdict`). `work` is `main`'s folder, after `main` has laid the shared guard family,
    lint and guard reads in it.

    Cost (rule outcomes-mechanize-rules): one filtered suite run and one temp tree per target per run, inside
    the job cap. A filtered run takes seconds, as a mutant's first stage does. It writes no log and starts no
    timer, thread or other long-lived process beyond the run's own pool."""
    targets = []
    for entry in entries:
        _label, _old, _new, target, _required, only_on = mutation_parts(entry)
        if target not in targets and not mutate_shared.skip_reason(only_on):
            targets.append(target)
    return {target: functools.partial(run_control, sources, work, target, entries) for target in targets}


def control_name(target: str) -> str:
    """The name keying a target's control copy, which `main` also checks for path collisions."""
    return "clean layout of %s" % target


def control_case(target: str, entries) -> str:
    """The required case fragment a target's control runs: the first one among its mutations that run here."""
    for entry in entries:
        _label, _old, _new, entry_target, required, only_on = mutation_parts(entry)
        if entry_target == target and required and not mutate_shared.skip_reason(only_on):
            return required
    raise ValueError("no mutation of target %s has a required case to run here" % target)


def run_control(sources, work: str, target: str, entries=None):
    """Run one filtered case of `target`'s suite on the unmutated layout. Return run_suite's result tuple.
    `entries` defaults to MUTATIONS."""
    _path, suite, variable, _stem = TARGETS[target]
    name = control_name(target)
    only = control_case(target, MUTATIONS if entries is None else entries)
    copy_path = lay_out(sources, work, target, name, "", "")
    config_dir = os.path.join(work, "cfg_%s" % mutate_shared.safe_name(name))
    os.makedirs(config_dir, exist_ok=True)
    return run_suite(suite, variable, copy_path, config_dir, only)


def run_mutant(sources, work: str, entry):
    """Apply one mutation, run its suite against it, and return (label, code, FAIL lines,
    required, skip, ERROR lines).

    `required` is the case name (or a distinctive fragment of it) the caller must find among the
    FAIL lines before trusting this mutant's death: see `mutate_shared.report_verdict`. `skip`,
    when not None, is why this mutant did not run on this platform at all: the caller reports it
    and counts it as neither killed, survived, nor wrong cause. This verdict is not yet trusted: `run_mutants`
    judges it against its target's clean-layout control (`run_controls`).
    """
    label, old, new, target, required, only_on = mutation_parts(entry)
    if required is None:
        raise ValueError("mutation carries no required case name: %s" % label)
    skip = mutate_shared.skip_reason(only_on)
    if skip:
        return label, None, [], required, skip
    _path, suite, variable, _stem = TARGETS[target]
    copy_path = lay_out(sources, work, target, label, old, new)
    config_dir = os.path.join(work, "cfg_%s" % mutate_shared.safe_name(label))
    os.makedirs(config_dir, exist_ok=True)
    code, red, seen = mutate_shared.staged_suite_seen(
        lambda only: run_suite(suite, variable, copy_path, config_dir, only), required)
    return label, code, red, required, None, seen


def main() -> int:
    if "--report" in sys.argv[1:]:
        return report_main(sys.argv[1:])
    if "--replay" in sys.argv[1:]:
        return replay_main(sys.argv[1:])
    if "--changed" in sys.argv[1:]:
        return changed_main(sys.argv[1:])
    if "--known-defects" in sys.argv[1:]:
        return known_defects_main(sys.argv[1:])
    if "--tests-for" in sys.argv[1:]:
        return tests_for_main(sys.argv[1:])
    sources = {}
    for name, (path, _suite, _variable, _stem) in TARGETS.items():
        with open(path, encoding="utf-8") as handle:
            sources[name] = handle.read()

    # Every anchor is checked BEFORE any suite runs, so a stale mutation fails in the first
    # second, not after the mutants ahead of it in the list have spent their minutes. A mutation
    # whose anchor sits in the WRONG file is stale too, which is what the target lookup catches.
    # The required-name field is checked here too: every entry must carry one, not just the ones
    # a reviewer remembered to fill in.

    # Two mutants must never write to the same path. safe_name already appends a digest of
    # the exact label, so this must not happen (see its docstring). Trust a guard only after
    # it goes red on the defect it guards. So this check recomputes the real file name for
    # each mutant, case-folded the way Windows reads names, instead of trusting the fix alone.

    seen_paths = {}
    for index, entry in enumerate(MUTATIONS):
        label, old, _new, target, required, _only_on = mutation_parts(entry)
        if target not in TARGETS:
            print("ERROR unknown mutation target %r: %s" % (target, label))
            return 1
        if target == "guard":
            # Across every guard module: exactly one match, or the mutant breaks the wrong spot.
            try:
                mutate_shared.find_anchor(HERE, old)
            except mutate_shared.StaleMutant:
                print("ERROR stale mutation, anchor text not found: %s" % label)
                return 1
            except mutate_shared.AmbiguousMutant as error:
                print("ERROR ambiguous mutation, %s: %s" % (error, label))
                return 1
        elif old not in sources[target]:
            print("ERROR stale mutation, anchor text not found: %s" % label)
            return 1
        if not required:
            print("ERROR mutation carries no required case name: %s" % label)
            return 1

        _tpath, _tsuite, _tvariable, stem = TARGETS[target]
        safed = mutate_shared.safe_name(label)
        # Two different entries land here. The same entry never returns twice. `index` marks
        # identity, not `label`. A literal duplicate label is still caught. That case is worse
        # than a case-only match, and the check treats it as a real collision, not a repeat
        # visit.
        for candidate in ("%s_%s.py" % (stem, safed), "cfg_%s" % safed):
            key = candidate.lower()
            other = seen_paths.get(key)
            if other is not None and other[0] != index:
                print("ERROR two mutations share one path on a case-insensitive filesystem: "
                      "%r and %r both produce %s" % (other[1], label, candidate))
                return 1
            seen_paths[key] = (index, label)

    # Each target's clean-layout control (run_controls) writes its own copy and config folder, and
    # must not collide with a mutant's either. The control's index is past every mutation's.
    for control_index, target in enumerate(sorted({mutation_parts(e)[3] for e in MUTATIONS}),
                                           start=len(MUTATIONS)):
        label = control_name(target)
        safed = mutate_shared.safe_name(label)
        for candidate in ("%s_%s.py" % (TARGETS[target][3], safed), "cfg_%s" % safed):
            other = seen_paths.get(candidate.lower())
            if other is not None:
                print("ERROR two mutations share one path on a case-insensitive filesystem: "
                      "%r and %r both produce %s" % (other[1], label, candidate))
                return 1
            seen_paths[candidate.lower()] = (control_index, label)

    work = tempfile.mkdtemp(prefix="mutate_guard_")
    # A "watch" mutant is a copy of config_watch.py that runs OUTSIDE hooks/, as its own
    # subprocess, and it does a plain `import guard` (never GUARD_UNDER_TEST: a mutation of the
    # watch must never be killed by a guard that moved with it, which is why
    # `test_config_watch.py`'s own `Project.env()` strips that variable before it spawns the
    # copy). Without the REAL guard.py sitting next to it, that import fails on every watch
    # mutant alike, and the crash reads as "the watch missed it" for EVERY case regardless of
    # which line was mutated: a kill with no bearing on the defect the mutation names, the exact
    # failure this file exists to catch. MEASURED: before this line, all seven `watch` mutants
    # printed the identical nine-case failure list, whatever the mutation.
    mutate_shared.guard_tree(work)
    # The override and calljudge copies sit one folder below `work`, so their `../lint` is work/lint:
    # override.py reads it, and so does the decision_watch.py beside a calljudge copy. The ruling and
    # decision copies read their own tree/lint instead (above). A guard copy carries its own lint folder (run_mutant).
    # The override copies also read ../janitor (the simulator refusal, which fails open without it) and ../skills.
    tracked_tree.copy_tracked(work, "lint", "janitor", "skills", root=os.path.dirname(HERE))
    lay_out_guard_reads(work)  # the override copies' ../merge, ../actions and ../bin

    try:
        return mutate_shared.run_mutants(
            MUTATIONS, lambda entry: run_mutant(sources, work, entry),
            controls=run_controls(sources, work, MUTATIONS), control_of=lambda entry: mutation_parts(entry)[3])
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
