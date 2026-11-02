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
"""

import os
import shutil
import subprocess
import sys
import tempfile

import mutate_shared
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)

HERE = os.path.dirname(os.path.abspath(__file__))
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

# A mutation names the file it breaks and the suite that must catch it. "guard" is the default, so
# every mutation written before the watch existed reads unchanged.
TARGETS = {
    "guard": (GUARD, SUITE, "GUARD_UNDER_TEST", "guard"),
    "watch": (WATCH, WATCH_SUITE, "WATCH_UNDER_TEST", "config_watch"),
    "decision": (DECISION, DECISION_SUITE, "DECISION_WATCH_UNDER_TEST", "decision_watch"),
    "ruling": (RULING, RULING_SUITE, "RULING_HOME_UNDER_TEST", "ruling_home"),
    "override": (OVERRIDE, SUITE, "GUARD_UNDER_TEST", "override"),
    "calljudge": (CALL_JUDGE, CALL_JUDGE_SUITE, "CALL_JUDGE_UNDER_TEST", "call_judge"),
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
     '.rstrip("/"))))]\n    if lines:\n        return False',
     '.rstrip("/"))))]\n    if False:\n        return False',
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
     'ENV_BASENAME = re.compile(r"^\\.env(\\.[A-Za-z0-9_.\\-]+)?$")',
     'ENV_BASENAME = re.compile(r"^\\.env$")', "guard", 'env: a path token wherever the path puts it, cat .env.local'),
    ("shared-tree: drop the interpreter heredoc exception",
     '    if (SHELL_HEREDOC if shells_only else INTERPRETER_HEREDOC)(_without_message_values(cmd)):\n'
     '        return cmd',
     '    if False:\n        return cmd', "guard", 'heredoc: a body fed to a shell stays under inspection'),
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
     '        elif target in ("HEAD", "@"):',
     '        elif target in ("@",):', "guard", 'lease with includes, HEAD, on main'),
    ("force-push: refs/heads/ is not stripped",
     'target.removeprefix("refs/heads/")',
     'target', "guard", 'forced to the default branch asks: a full ref'),
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
     '    delete = delete or any(spec.startswith(":") for spec in plain)',
     '    delete = delete', "guard", 'a delete refspec'),
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
    ("force-push: quoted text is read as a push",
     'return PUSH_QUOTED.sub(" ", segment)', 'return segment', "guard",
     'false alarm: --force quoted in a commit message'),
    ("force-push: a deny names the wrong reason",
     'refuse(tool, verdict, "force-push", PUSH_REASON, "git push " + " ".join(args))',
     'refuse(tool, verdict, "force-push", PUSH_ASK_REASON, "git push " + " ".join(args))',
     "guard", 'the long force flag'),
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
     '            if arg.startswith("-") and not arg.startswith("--") and "t" in arg:\n'
     '                return word + " " + arg',
     '            if False:\n                return word + " " + arg', "guard", 'kill: lsof -t feeds a kill list'),
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
    ("detached-launch: nohup/setsid no longer denies as a bare wrapper",
     '    return word if basename(word) in DETACH_WRAPPERS else ""',
     '    return ""', "guard", "detached: nohup alone, no background job, still detaches from "
     "the session"),
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
     '    return "\\n".join(_split_heredocs(cmd)[0])',
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
     'sample.startswith(".env.")', 'sample.startswith(".env.local")', "guard",
     'env: normalized, glob, heredoc or depth, cat .env.bak*'),
    ("env-file: the example glob is held",
     '    if word.startswith(ENV_ALLOWED):\n        return False', '    if False:\n        return False', "guard",
     'env: a normalized allowance, cat .env.example*'),
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
     '            found = os.path.join(found, value) if found and value else (value or found)',
     '            found = found or value', "guard",
     'per-file allow: -C parent then a relative -C lane, checkout -- of one file'),
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
     'per-file ask: two -C targets, lane then a second linked worktree, both per-file restores'),
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
     '    return "--hard" in args',
     '    return True', "guard", 'reset: a plain reset only unstages, the working tree is untouched'),
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
     '    matched = frozen_shell_hit(stripped, cwd)\n'
     '    if matched:\n'
     '        refuse(tool, "deny", "frozen-path", FROZEN_REASON, matched)',
     '    matched = _shell_write_hit(stripped, cwd, is_settings_file)\n'
     '    if matched:\n'
     '        change = cap_change(raw)\n'
     '        if change:\n'
     '            refuse(tool, "ask", "agent-model-cap", cap_ask_reason(change, matched),\n'
     '                   matched + " " + change)\n'
     '    matched = frozen_shell_hit(stripped, cwd)\n'
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
     'if tool not in SPAWN_TOOLS or "opus" not in str(tool_input.get("model") or "").lower():',
     'if True:', "guard", 'ceiling: Agent with model opus and no role is denied'),
    ("ceiling: a third-round line earns the standing grant for any role, so a reviewer passes unrefused",
     'if role == "builder" and builder_third_round(brief):',
     'if builder_third_round(brief):', "guard",
     "ceiling: Agent reviewer on opus with the brief 'Try 3 of 3. Finish the f' is denied"),
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
    # docs/decisions/an-agent-outside-its-home-tree-must-stop.md; all are caught by the single case
    # that exercises the whole sequence, `worktree_home_case`.
    ("worktree-home: the first call from inside the worktree never writes the home record",
     '    if path_is_inside(cwd, candidate) is True:\n        write_agent_home(cwd, agent_id, candidate)',
     '    if path_is_inside(cwd, candidate) is False:\n        write_agent_home(cwd, agent_id, candidate)',
     "guard", "worktree-home:"),
    ("worktree-home: the candidate worktree path drops the agent- prefix, so it never matches",
     'candidate = os.path.join(primary, ".claude", "worktrees", "agent-" + agent_id)',
     'candidate = os.path.join(primary, ".claude", "worktrees", agent_id)',
     "guard", "worktree-home:"),
    ("worktree-home: AGENT_ID rejects a letter, so every real agent id reads as an orchestrator",
     'AGENT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")',
     'AGENT_ID = re.compile(r"^[0-9_-]{1,64}$")',
     "guard", "worktree-home:"),
    ("worktree-home: a shell call outside its recorded home is judged as inside it",
     '        if (path_is_inside(home_cwd, home) is False\n',
     '        if (path_is_inside(home_cwd, home) is None\n',
     "guard", "worktree-home:"),
    ("worktree-home: a write outside the recorded home, inside the clone, is allowed through",
     '            if (path_is_inside(resolved_target, home_primary) is True\n'
     '                    and path_is_inside(resolved_target, home) is False):',
     '            if (path_is_inside(resolved_target, home_primary) is True\n'
     '                    and path_is_inside(resolved_target, home) is None):',
     "guard", "worktree-home:"),
    # The next two anchors sit in worktree_home_hit, which returns a log detail and lets judge()
    # refuse; a mutant that returns a detail for a status that allows is a deny.
    ("worktree-home: an unreadable home record denies instead of allowing",
     '    home_status, home, home_primary = agent_worktree_home(payload, home_cwd)\n'
     '    if home_status != "home":',
     '    home_status, home, home_primary = agent_worktree_home(payload, home_cwd)\n'
     '    if home_status == "unknown":\n'
     '        return "unreadable state"\n'
     '    if home_status != "home":',
     "guard", "worktree-home:"),
    ("worktree-home: a non-isolated agent with no record is denied instead of allowed",
     '    home_status, home, home_primary = agent_worktree_home(payload, home_cwd)\n'
     '    if home_status != "home":',
     '    home_status, home, home_primary = agent_worktree_home(payload, home_cwd)\n'
     '    if home_status == "no-record":\n'
     '        return "no record"\n'
     '    if home_status != "home":',
     "guard", "worktree-home:"),
    ("worktree-home: a relative write target drops the join onto the payload's own cwd",
     '            try:\n                resolved_target = _resolved(write_target, home_cwd)\n'
     '            except Exception:\n                resolved_target = write_target\n'
     '            if (path_is_inside(resolved_target, home_primary) is True\n'
     '                    and path_is_inside(resolved_target, home) is False):',
     '            resolved_target = write_target\n'
     '            if (path_is_inside(resolved_target, home_primary) is True\n'
     '                    and path_is_inside(resolved_target, home) is False):',
     "guard", "worktree-home:"),
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
     '                and path_is_inside(resolved, os.path.join(owner, ".git")) is not True)',
     '                and True)',
     "guard", "worktree-home: any session's write into another checkout"),
    ("other-checkout: a shell target ignores a leading cd",
     "        hit = _shell_write_hit(command, where, elsewhere, follow_cd=True)",
     "        hit = _shell_write_hit(command, where, elsewhere, follow_cd=False)",
     "guard", "worktree-home: any session's write into another checkout"),
    ("other-checkout: a quiet redirect pays the git read",
     '        if not SHELL_WRITE_HINT.search(SHELL_QUIET_REDIRECT.sub(" ", command)):',
     '        if not SHELL_WRITE_HINT.search(command):',
     "guard", "worktree-home: the cross-checkout read costs"),
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
     '        elif arg.startswith("--repo="):',
     '        elif False:', "guard", 'merge-checks: the long repo flag names the repo too'),
    ("merge-checks: a body flag's value is read as the pull request",
     'MERGE_VALUE_FLAGS = {"-R", "--repo", "-b", "--body",',
     'MERGE_VALUE_FLAGS = {"-R", "--repo", "--body",', "guard",
     'merge-checks: a flag value is no pull request'),
    ("merge-checks: any word that spells gh is the command word",
     '    index = resolve_command(tokens)\n    if index is None or basename(tokens[index]) not in ("gh", "gh.exe"):\n        return None\n    return tokens[index + 1:]',
     '    index = next((i for i, t in enumerate(tokens) if basename(t) in ("gh", "gh.exe")), None)\n    if index is None:\n        return None\n    return tokens[index + 1:]',
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
     '    return ""', "guard", "builder-diff: the diff check logs for the reviewer and never blocks"),
    ("designer-scope: an unread layout allows every path",
     '    if folder is None or ".." in parts:\n        return False',
     '    if folder is None:\n        return True\n    if ".." in parts:\n        return False',
     "guard", "designer-scope: an unread layout allows no path"),
    ("role-diff: SubagentStop is never judged",
     '    if payload.get("hook_event_name") == "SubagentStop":\n        judge_stop(payload)',
     '    if False:\n        judge_stop(payload)', "guard", "builder-diff: the diff check logs for the reviewer and never blocks"),
    ("role-diff: commit and push are never judged",
     '                if subcommand in ("commit", "push"):', '                if False:', "guard", "builder-diff: the diff check logs for the reviewer and never blocks"),
    ("role-diff: push is not judged, only commit",
     '                if subcommand in ("commit", "push"):', '                if subcommand in ("commit",):',
     "guard", "builder-diff: the diff check logs for the reviewer and never blocks"),
    ("role-diff: the merge base with the default branch is no base",
     '    default = resolve_default_base(root)\n    if default:\n        merged',
     '    default = None\n    if default:\n        merged', "guard",
     "builder-diff: main's later tests merged into a long-lived worktree log nothing"),
    ("role-diff: a path offends against ANY base, not every base",
     '    both = [rel for rel in sets[0] if all(rel in s for s in sets[1:])]',
     '    both = [rel for s in sets for rel in s]', "guard",
     "builder-diff: main's later tests merged into a long-lived worktree log nothing"),
    ("role-diff: untracked files are never read",
     '    for rel in [p for p in tracked.stdout.split("\\0") if p] + sorted(\n'
     '            p for p in fresh.stdout.split("\\0") if p):',
     '    for rel in [p for p in tracked.stdout.split("\\0") if p]:', "guard", "builder-diff: the diff check logs for the reviewer and never blocks"),
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
     '            bad = not all(author_path_ok(n) for n in names)', '            bad = False', "guard", "builder-diff: the diff check logs for the reviewer and never blocks"),
    ("test-author: the write tool lets any path through",
     '        return "" if repo_rel(target, cwd, outside=False) is None else target', '        return ""', "guard",
     "test-author: Edit of product code is refused"),
    ("test-author: test config is not its own",
     '    return (is_test_rel(rel) or is_test_config_rel(rel) or basename(rel) in AUTHOR_BASENAMES',
     '    return (is_test_rel(rel) or basename(rel) in AUTHOR_BASENAMES', "guard", "test-author: Edit of pytest.ini is allowed"),
    ("test-author: a mutation test is not its own",
     '            or norm(rel).lstrip("/").lower() in AUTHOR_MUTATION_TESTS)', '            or False)', "guard",
     "test-author: Edit of mutation test hooks/mutate_guard.py is allowed"),
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
     '                os.path.join(npm_prefix(where), "node_modules")):',
     '                os.path.join(npm_prefix(where), "never-a-folder")):',
     "guard", 'linked-nm: refuse npm install (Bash) in a linked folder'),
    ('linked-node-modules: a dry run is refused like an install',
     'NPM_NO_CHANGE = {"-g", "--global", "--location=global", "--help", "-h", "--dry-run"}',
     'NPM_NO_CHANGE = {"-g", "--global", "--location=global", "--help", "-h"}',
     "guard", 'linked-nm: npm ci --dry-run (Bash) in a linked folder is allowed'),
    ('linked-node-modules: a global install is refused like a local one',
     'NPM_NO_CHANGE = {"-g", "--global", "--location=global", "--help", "-h", "--dry-run"}',
     'NPM_NO_CHANGE = {"--help", "-h", "--dry-run"}',
     "guard", 'linked-nm: npm i -g x (Bash) in a linked folder is allowed'),
    ('linked-node-modules: a value flag before the subcommand is read as the subcommand',
     '    "--loglevel", "--prefix", "--cache",',
     '    "--never-a-flag", "--prefix", "--cache",',
     "guard", 'linked-nm: refuse npm --loglevel error ci (Bash) in a linked folder'),
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
    # ---- hand-made-worktree (decision lanes-start-in-tool-worktrees): one mutant per branch.
    ("hand-made-worktree: the judge_shell loop never asks, so no hand-made tree is refused",
     '            matched = hand_made_worktree_hit(segments, number, cwd, ends)\n',
     '            matched = ""\n',
     "guard", 'hand-made worktree: a relative sibling path from the primary is refused'),
    ("hand-made-worktree: the inside-the-home-folder test is inverted",
     'if path_is_inside(tree, os.path.join(primary, ".claude", "worktrees")) is True:',
     'if path_is_inside(tree, os.path.join(primary, ".claude", "worktrees")) is not True:',
     "guard", 'hand-made worktree: a relative sibling path from the primary is refused'),
    ("hand-made-worktree: the inside-the-home-folder pass is dropped, so a home tree is refused",
     'if path_is_inside(tree, os.path.join(primary, ".claude", "worktrees")) is True:',
     'if False:',
     "guard", "hand-made worktree: an absolute path under the primary's home folder passes"),
    ("hand-made-worktree: an option's value is taken as the new tree path",
     '        elif arg in HAND_MADE_VALUE_OPTIONS:\n            cursor += 1\n',
     '        elif arg in HAND_MADE_VALUE_OPTIONS:\n            pass\n',
     "guard", 'hand-made worktree: -b and a path under the home folder passes'),
    ("hand-made-worktree: a double dash no longer ends the options",
     '        if ended or not arg.startswith("-") or arg == "-":',
     '        if False or not arg.startswith("-") or arg == "-":',
     "guard", 'hand-made worktree: a dash-led name after a double dash is still a path'),
    ("hand-made-worktree: the run folder ignores cd and reads the payload cwd only",
     '    where = dir_before_segment(segments, number, cwd, ends)\n    named = _segment_git_c_target(tokens)\n    if named is not None:\n        where = None if _unexpanded(named) else shell_abs(named, where)\n    if not where or _unexpanded(target):',
     '    where = cwd\n    named = _segment_git_c_target(tokens)\n    if named is not None:\n        where = None if _unexpanded(named) else shell_abs(named, where)\n    if not where or _unexpanded(target):',
     "guard", 'hand-made worktree: cd into a non-temp primary'),
    ("hand-made-worktree: the run folder ignores -C",
     '    named = _segment_git_c_target(tokens)\n    if named is not None:\n        where = None if _unexpanded(named) else shell_abs(named, where)\n    if not where or _unexpanded(target):',
     '    if not where or _unexpanded(target):',
     "guard", 'hand-made worktree: -C reaches the primary from elsewhere'),
    ("hand-made-worktree: the temp exemption judges the target, not the repo",
     '    if path_is_inside(primary, tempfile.gettempdir()):\n        return ""\n    tree = shell_abs(target, where)',
     '    if path_is_inside(shell_abs(target, where) or "", tempfile.gettempdir()):\n        return ""\n    tree = shell_abs(target, where)',
     "guard", 'hand-made worktree: cd into a non-temp primary'),
    ("hand-made-worktree: the temp exemption is dropped, so a throwaway repo is refused",
     '    if path_is_inside(primary, tempfile.gettempdir()):\n        return ""\n    tree = shell_abs(target, where)',
     '    tree = shell_abs(target, where)',
     "guard", "hand-made worktree: a repo under the guard's temp folder is a throwaway"),
    ("hand-made-worktree: the help flag no longer ends the read",
     '        elif arg in ("-h", "--help"):\n            return None\n',
     '        elif arg in ("-hh",):\n            return None\n',
     "guard", 'hand-made worktree: a help flag after the path still only reads'),
    ("hand-made-worktree: the pointer remedy names worktree add again",
     'Call the EnterWorktree tool to make one ',
     'Run git worktree add -b x to make one ',
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
     '                    "the acts that no override lifts.")}}))',
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
]


# REPORT MODE. File -> the suites that exercise it or name it. A suite not listed here (hooks/test_guard.py,
# merge/test_merge.py, lint/test_ci_scope.py) is not run against that file: test_guard.py and test_merge.py
# take minutes each per mutant, and test_ci_scope.py only passes the file's path to the scope detector.
# Add a verdict-deciding file here, with the suites that name it, to put it in the report.
REPORT_TARGETS = [
    ("lint/report_guard.py", ["lint/test_report_guard.py", "hooks/test_reply_judge.py", "hooks/test_wrappers.py",
                             "lint/test_rule_audit.py", "lint/test_settings_matcher.py"]),
    ("hooks/feedback_guard.py", ["hooks/test_feedback_inbox.py", "lint/test_settings_matcher.py"]),
    ("hooks/stall_watch.py", ["hooks/test_stall_watch.py", "hooks/test_stall_watch_stop.py",
                              "hooks/test_wrappers.py", "lint/test_hook_platform_exit.py",
                              "janitor/test_session_end_sweep.py", "lint/test_settings_matcher.py"]),
    ("lint/check_silent_undo.py", ["lint/test_check_silent_undo.py"]),
]
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


def run_suite(suite: str, variable: str, copy_path: str, config_dir: str, only=None):
    """Run one fixture suite against one mutated copy. Return (exit code, FAIL lines, case lines).

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
    # stderr goes to DEVNULL, not a pipe: test_guard.py leaves a `sleep 300` that holds the suite's
    # stderr (spawn_live_parent), and run() waits for a pipe's EOF. Measured: every mutant took 306 s.
    result = _nowindow.run(
        # text=True keeps the default decoding: the child inherits env, so both sides share one encoding.
        [sys.executable, suite], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        env=env, timeout=1200,
    )
    lines = result.stdout.splitlines()
    red = [line for line in lines if line.startswith("FAIL")]
    # "PASS" and "FAIL" start each case line in every suite here; "ok " is test_call_judge.py's pass.
    ran = [line for line in lines if line.startswith(("PASS", "FAIL", "ok "))]
    return result.returncode, red, ran


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


def run_mutant(sources, work: str, entry):
    """Apply one mutation, run its suite against it, and return (label, code, FAIL lines,
    required, skip).

    `required` is the case name (or a distinctive fragment of it) the caller must find among the
    FAIL lines before trusting this mutant's death: see `mutate_shared.report_verdict`. `skip`,
    when not None, is why this mutant did not run on this platform at all: the caller reports it
    and counts it as neither killed, survived, nor wrong cause.
    """
    label, old, new, target, required, only_on = mutation_parts(entry)
    if required is None:
        raise ValueError("mutation carries no required case name: %s" % label)
    skip = mutate_shared.skip_reason(only_on)
    if skip:
        return label, None, [], required, skip
    _path, suite, variable, stem = TARGETS[target]
    if target == "guard":
        # The whole guard family goes in the mutant's own folder, and the anchor lands in the one
        # module that holds it. The suite loads the copied guard.py, which finds its siblings.
        tree = os.path.join(work, "%s_%s" % (stem, mutate_shared.safe_name(label)))
        mutate_shared.guard_tree(tree)
        mutate_shared.apply_mutant(tree, old, new)
        copy_path = os.path.join(tree, "guard.py")
    else:
        copy_path = os.path.join(work, "%s_%s.py" % (stem, mutate_shared.safe_name(label)))
        mutated = sources[target].replace(old, new, 1)
    if target in ("ruling", "decision"):
        # ruling_home.py and decision_watch.py read `../lint/_transcript.py` beside itself. A bare copy in `work`
        # would crash on that import and read as red on every case, whatever was mutated
        # (a mutant's own cause of death must be checked). Lay out hooks/ and lint/ for the copy.
        tree = os.path.join(work, "tree_%s" % mutate_shared.safe_name(label))
        os.makedirs(os.path.join(tree, "hooks"), exist_ok=True)
        os.makedirs(os.path.join(tree, "lint"), exist_ok=True)
        shutil.copy(os.path.join(HERE, "..", "lint", "_transcript.py"), os.path.join(tree, "lint"))
        if target == "decision":
            mutate_shared.guard_tree(os.path.join(tree, "hooks"))
        copy_path = os.path.join(tree, "hooks", os.path.basename(TARGETS[target][0]))
    if target == "override":
        # The guard family, local_time.py and the mutated override.py share one folder: the
        # copied guard and the suite's grant child both import the override module beside guard.py.
        tree = os.path.join(work, "%s_%s" % (stem, mutate_shared.safe_name(label)))
        mutate_shared.guard_tree(tree)
        for helper in ("local_time.py", "_nowindow.py"):
            shutil.copy(os.path.join(HERE, helper), tree)
        with open(os.path.join(tree, "override.py"), "w", encoding="utf-8", newline="\n") as handle:
            handle.write(mutated)
        copy_path = os.path.join(tree, "guard.py")
    elif target == "calljudge":
        # call_judge.py imports guard_core and decision_watch beside itself: lay out the whole family.
        tree = os.path.join(work, "%s_%s" % (stem, mutate_shared.safe_name(label)))
        mutate_shared.guard_tree(tree)
        copy_path = os.path.join(tree, "call_judge.py")
        with open(copy_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(mutated)
    elif target != "guard":
        with open(copy_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(mutated)
    config_dir = os.path.join(work, "cfg_%s" % mutate_shared.safe_name(label))
    os.makedirs(config_dir, exist_ok=True)
    code, red = mutate_shared.staged_suite(
        lambda only: run_suite(suite, variable, copy_path, config_dir, only), required)
    return label, code, red, required, None


def main() -> int:
    if "--report" in sys.argv[1:]:
        return report_main(sys.argv[1:])
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
    # Every guard copy sits one folder below `work`, so its `../lint` is work/lint. guard.py imports
    # lint/layout.py from there (role_model_table, the waiting-page check). Without this folder the import
    # fails, the guard exits silently and allows, and the role-model deny cases go red whatever the mutation.
    shutil.copytree(os.path.join(HERE, "..", "lint"), os.path.join(work, "lint"),
                    ignore=shutil.ignore_patterns("__pycache__"))

    try:
        return mutate_shared.run_mutants(
            MUTATIONS, lambda entry: run_mutant(sources, work, entry))
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
