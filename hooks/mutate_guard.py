#!/usr/bin/env python3
"""Mutation test for hooks/guard.py.

Stdlib only. For each mutation below, it copies guard.py to a temp file, applies one
literal string replacement, and runs hooks/test_guard.py against the copy with
GUARD_UNDER_TEST=<copy> and CLAUDE_CONFIG_DIR=<temp dir>. The suite must go red
(a nonzero exit backed by at least one FAIL line). A mutation the suite does not
catch is "survived", and any survivor fails this run.

A mutation whose replacement string is not found in the current guard.py is STALE:
the source moved on and the mutation no longer proves anything. That must fail
loudly, not be skipped, so it exits 1 with an error line instead of counting the
mutation either way.

The mutants run IN PARALLEL, one suite process per mutant, up to the CPU count at once
(MUTATE_JOBS overrides). Each mutant gets its own guard copy and its own config directory, so
the runs share nothing but the read-only fixture tree the suite builds under its own temp
root. MEASURED 2026-09-19 on a 4-core machine: 38 mutants serial, 14 min 8 s (22 s each);
47 mutants parallel, 4 min 29 s. The suite itself spawns guard.py once per case, which is
where the time goes.

Run:
    python hooks/mutate_guard.py

Ported from a prior run at
.../scratchpad/mutate3.py (fourteen mutations), plus five added for rules
guard.py grew since that run: the live-stream rule, the waiter rule (Rule 9),
the REDIRECTION strip in git_calls, and the Decision 7 config-edit log line.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "guard.py")
SUITE = os.path.join(HERE, "test_guard.py")
WATCH = os.path.join(HERE, "config_watch.py")
WATCH_SUITE = os.path.join(HERE, "test_config_watch.py")

# A mutation names the file it breaks and the suite that must catch it. "guard" is the default, so
# every mutation written before the watch existed reads unchanged.
TARGETS = {
    "guard": (GUARD, SUITE, "GUARD_UNDER_TEST", "guard"),
    "watch": (WATCH, WATCH_SUITE, "WATCH_UNDER_TEST", "config_watch"),
}

# (name, anchor text found once in the source, its mutated replacement).
# Each one breaks exactly one rule. One mutation per rule at least:
# shared-tree, machine-wide kill, live-stream, waiter, force push, destructive
# delete, env-file, merge-main, frozen-path, the redirect strip, and the log.
MUTATIONS = [
    # THE TWO ROOTS. `--work-tree` names whose FILES a call discards, and `--git-dir` names whose
    # HEAD it moves. Each mutant makes one of them unread, or makes one root answer the other's
    # question.
    ("work-tree: the tree option goes unread, so rule 1 judges the wrong tree",
     'GIT_WORK_TREE_RE = re.compile(r"--work-tree(?:=|\\s+)([\'\\"]?)([^\'\\";&|\\s]+)\\1")',
     'GIT_WORK_TREE_RE = re.compile(r"--never-a-real-option(\\A\\Z)(\\A\\Z)")'),
    ("pointer-head: the git directory option goes unread",
     'GIT_DIR_RE = re.compile(r"--git-dir(?:=|\\s+)([\'\\"]?)([^\'\\";&|\\s]+)\\1")',
     'GIT_DIR_RE = re.compile(r"--never-a-real-option(\\A\\Z)(\\A\\Z)")'),
    ("pointer-head: the HEAD root falls back through the work tree, naming the wrong HEAD",
     '        return run_dir\n    return _absolute(match.group(2), run_dir)',
     '        return command_root(cmd, shell_cwd)\n    return _absolute(match.group(2), run_dir)'),
    ("pointer-head: read the shared common git directory, so a worktree reads as its primary",
     '        answer = _git(where, "rev-parse", "--absolute-git-dir")',
     '        answer = _git(where, "rev-parse", "--git-common-dir")'),
    # RULE 1b, the pointer checkout's HEAD. Each mutant breaks one arm: the act test, the tree
    # test, the main exemption, the two path-operation arms, the `switch` subcommand, the top-level
    # read, and the pointer parse.
    ("pointer-head: no command ever moves HEAD",
     'def head_move_target(subcommand: str, args) -> str:',
     'def head_move_target(subcommand: str, args) -> str:\n    return ""'),
    ("pointer-head: call every tree the pointer checkout",
     '    return mine == theirs',
     '    return True'),
    ("pointer-head: lose the exemption for a move to main",
     '    if target == PROTECTED_BASE:\n        return ""',
     '    if target == "no-such-branch":\n        return ""'),
    ("pointer-head: read a double dash as a branch",
     '    if "--" in args:\n        return ""\n    switching = subcommand == "switch"',
     '    if False:\n        return ""\n    switching = subcommand == "switch"'),
    ("pointer-head: forget the path-operation flags",
     'CHECKOUT_PATH_FLAGS = {"--ours", "--theirs", "--patch", "-p", "--overlay", "--no-overlay"}',
     'CHECKOUT_PATH_FLAGS = set()'),
    ("pointer-head: watch checkout and not switch",
     'HEAD_MOVE_SUBCOMMANDS = ("checkout", "switch")',
     'HEAD_MOVE_SUBCOMMANDS = ("checkout",)'),
    ("pointer-head: compare the directory as written, not the git directory git reports",
     '    mine = git_dir_of(root)',
     '    mine = os.path.normcase(os.path.realpath(root)) if root else ""'),
    ("pointer-head: a pointer line that never parses",
     'POINTER_LINE = re.compile(r"^@(.+)/CLAUDE\\.md[ \\t]*$", re.MULTILINE)',
     'POINTER_LINE = re.compile(r"^@@(.+)/CLAUDE\\.md[ \\t]*$", re.MULTILINE)'),
    ("shared-tree: drop the git clean arm",
     '        if subcommand == "clean" and clean_deletes_files(args):',
     '        if False and clean_deletes_files(args):'),
    ("shared-tree: call every tree a worktree",
     '    return own != common',
     '    return True'),
    ("env-file: read only the bare environment basename",
     'ENV_BASENAME = re.compile(r"^\\.env(\\.[A-Za-z0-9_.\\-]+)?$")',
     'ENV_BASENAME = re.compile(r"^\\.env$")'),
    ("shared-tree: drop the interpreter heredoc exception",
     '    if INTERPRETER_HEREDOC.search(cmd):\n        return cmd',
     '    if False:\n        return cmd'),
    ("frozen-path: freeze nothing",
     '    if not path:\n        return False\n    try:\n        target = _resolved(path, cwd)\n'
     '        root = os.path.normcase(os.path.realpath(config_dir()))',
     '    if path:\n        return False\n    try:\n        target = _resolved(path, cwd)\n'
     '        root = os.path.normcase(os.path.realpath(config_dir()))'),
    ("force-push: forget the force push",
     'def push_is_forced(args) -> bool:',
     'def push_is_forced(args) -> bool:\n    return False'),
    ("merge-main: trust an unreadable merge base",
     '        elif base == "":',
     '        elif base == "never":'),
    ("machine-wide-kill: pkill and killall no longer deny in command position",
     '    if tool in KILL_COMMAND_WORDS:\n        return word',
     '    if False:\n        return word'),
    ("machine-wide-kill: taskkill's image flag no longer denies",
     '    if tool == "taskkill" and any(flag.lower() in TASKKILL_IMAGE_FLAGS for flag in rest):\n'
     '        return word',
     '    if False:\n        return word'),
    ("machine-wide-kill: Stop-Process's name flag no longer denies",
     '    if tool == "stop-process" and any('
     'flag.lower() in STOP_PROCESS_NAME_FLAGS for flag in rest):\n        return word',
     '    if False:\n        return word'),
    ("machine-wide-kill: lsof -t no longer feeds a kill list",
     '            if arg.startswith("-") and not arg.startswith("--") and "t" in arg:\n'
     '                return word + " " + arg',
     '            if False:\n                return word + " " + arg'),
    ("command word: a wrapper such as xargs no longer unwraps to what it runs",
     '    while index < end and basename(tokens[index]) in COMMAND_WRAPPERS:',
     '    while False:'),
    ("shell segments: a quote never closes, so a real call after it is swallowed whole",
     '            if char == quote:\n                quote = ""',
     '            if False:\n                quote = ""'),
    ("conflict-resolve: a conflict-side flag no longer exempts the checkout",
     'CHECKOUT_CONFLICT_FLAGS = {"--ours", "--theirs", "--merge"}',
     'CHECKOUT_CONFLICT_FLAGS = set()'),
    ("conflict-resolve: every tree reads as mid-conflict",
     '    return any(os.path.isdir(os.path.join(path, name)) for name in REBASE_STATE_DIRS)',
     '    return True'),
    ("log: stop logging refusals",
     '        with open(os.path.join(folder, "guard.log"), "a", encoding="utf-8") as handle:\n'
     '            handle.write(line + "\\n")',
     '        pass'),
    ("shared-tree: keep heredoc bodies in every rule",
     '    lines = cmd.split("\\n")',
     '    return cmd\n    lines = cmd.split("\\n")'),
    ("env-file: name the file in the environment reason, the reviewed defect",
     '        refuse(tool, "deny", "env-file", ENV_TOOL_REASON + ". " + ENV_ADVICE, target)',
     '        refuse(tool, "deny", "env-file", ENV_TOOL_REASON + " " + target + ". "'
     ' + ENV_ADVICE, target)'),
    ("env-file: name the file in the shell environment reason, the reviewed defect",
     '        refuse(tool, "deny", "env-file", refusal + ". " + ENV_ADVICE, logged)',
     '        refuse(tool, "deny", "env-file", logged + ". " + ENV_ADVICE, logged)'),
    ("frozen-path: name the path in the frozen reason",
     '        refuse(tool, "deny", "frozen-path", FROZEN_REASON, target)',
     '        refuse(tool, "deny", "frozen-path", FROZEN_REASON + " " + target, target)'),
    # Added: rules guard.py grew after the prior mutation run.
    ("live-stream: never refuse a live stream",
     '    for segment in split_segments(stripped):\n'
     '        matched = live_stream_hit(segment)\n'
     '        if matched:\n'
     '            refuse(tool, "deny", "live-stream", LIVE_STREAM_REASON, matched)',
     '    for segment in split_segments(stripped):\n'
     '        matched = live_stream_hit(segment)\n'
     '        if False:\n'
     '            refuse(tool, "deny", "live-stream", LIVE_STREAM_REASON, matched)'),
    ("waiter: never refuse a waiter loop (Rule 9)",
     '        matched = waiter_hit(segment)\n'
     '        if matched:\n'
     '            refuse(tool, "deny", "waiter", WAITER_REASON, matched)',
     '        matched = waiter_hit(segment)\n'
     '        if False:\n'
     '            refuse(tool, "deny", "waiter", WAITER_REASON, matched)'),
    ("destructive-delete: blind the wide-delete patterns",
     "    for pattern in DESTRUCTIVE_DELETE:\n        found = pattern.search(cmd)",
     "    for pattern in ():\n        found = pattern.search(cmd)"),
    ("git-call parsing: drop the redirect strip before tokenizing",
     '    tokens = REDIRECTION.sub(" ", segment).split()',
     '    tokens = segment.split()'),
    ("config-edit: stop noting project config edits, shell tool",
     '    matched = project_config_shell_hit(stripped, cwd)\n'
     '    if matched:\n'
     '        record(tool, "noted", "config-edit", matched)',
     '    matched = project_config_shell_hit(stripped, cwd)\n'
     '    if False:\n'
     '        record(tool, "noted", "config-edit", matched)'),
    # Added: the stash/reset/restore split (Decision 12). Each mutation collapses one predicate
    # back to a bare name match, the exact defect this split fixes, so a later edit that redoes
    # that collapse goes red here.
    ("shared-tree: stash collapses back to a name match on every action",
     '    return stash_action(args) not in STASH_READ_ACTIONS',
     '    return True'),
    # Added 2026-09-19 with the stack clause. The first mutant blinds the DIRECTION predicate, so
    # every stash call is read against the working tree. The second puts back the exact defect
    # this change fixes: only `drop` and `clear` read the stack, so `pop`, `apply` and `branch`
    # pass over a clean tree that carries another session's entry.
    ("shared-tree: no stash action is read as taking an entry off the stack",
     'def stash_takes_the_stack(args) -> bool:',
     'def stash_takes_the_stack(args) -> bool:\n    return False'),
    ("subject: only drop and clear read the stack, the narrow clause put back",
     '    if stash_takes_the_stack(args):\n        stack = stash_stack(where)',
     '    if stash_action(args) in ("drop", "clear"):\n        stack = stash_stack(where)'),
    ("shared-tree: reset collapses back to a name match, --hard or not",
     '    return "--hard" in args',
     '    return True'),
    # Added: the subject read. One per arm. Each mutation blinds ONE subject read, which must
    # turn that arm's empty-subject case red: a guard that refuses without reading its subject is
    # the defect these arms fix.
    ("subject: the reset arm never reads the working tree",
     'def reset_subject(args, where: str):',
     'def reset_subject(args, where: str):\n    return False'),
    ("subject: a hard reset at any commit passes on a clean tree, the owner's narrowing undone",
     '    if reset_target(args) not in RESET_HEAD_TARGETS:\n        return False',
     '    if False:\n        return False'),
    ("subject: the stash arm never reads the tree or the stack",
     'def stash_subject(args, where: str):',
     'def stash_subject(args, where: str):\n    return False'),
    ("subject: the restore arm never reads its paths",
     'def restore_subject(args, where: str):',
     'def restore_subject(args, where: str):\n    return False'),
    ("subject: the checkout arm never reads its paths",
     'def checkout_subject(args, where: str):',
     'def checkout_subject(args, where: str):\n    return False'),
    ("subject: the clean arm never reads the untracked entries",
     'def clean_subject(args, where: str):',
     'def clean_subject(args, where: str):\n    return False'),
    ("subject: a clean exclude pattern is read as a pathspec, so the read narrows wrongly",
     'CLEAN_OPT_WITH_VALUE = {"-e", "--exclude"}',
     'CLEAN_OPT_WITH_VALUE = set()'),
    ("subject: an unreadable subject is refused instead of allowed and logged",
     '        if state is None:\n'
     '            record(tool, "noted", "subject-unread", matched)\n'
     '            continue',
     '        if False:\n'
     '            record(tool, "noted", "subject-unread", matched)\n'
     '            continue'),
    ("scratchpad: this session's own scratchpad stops being private",
     'def under_session_scratchpad(where: str, session_id: str) -> bool:',
     'def under_session_scratchpad(where: str, session_id: str) -> bool:\n    return False'),
    ("scratchpad: every path reads as this session's scratchpad",
     '    parts = real.split(os.sep)',
     '    return True\n    parts = real.split(os.sep)'),
    ("shared-tree: restore collapses back to a name match, --staged or not",
     '    staged = "--staged" in args or "-S" in args\n'
     '    worktree = "--worktree" in args or "-W" in args\n'
     '    return worktree or not staged',
     '    return True'),
    # Added: the subagent model cap (rule 8, PR #42). These are the mutations its builder ran by hand
    # on `.bak` copies, now in CI. Each one undoes one thing the review made the rule do, so a later
    # edit that redoes it goes red here.
    ("cap: the edit-count cap comes back, so 200 no-op edits hide a lift",
     '    if isinstance(edits, list):\n        for edit in edits:',
     '    if isinstance(edits, list):\n        for edit in edits[:200]:'),
    ("cap: the resolved-basename branch is gone, so a symlink to a settings file walks past",
     '        return basename(_resolved(path, cwd)) in SETTINGS_BASENAMES\n'
     '    except Exception:\n        return False',
     '        return False\n'
     '    except Exception:\n        return False'),
    ("cap: the JSON key walk is gone, so a JSON-escaped key walks past",
     '    for key, value in json_cap_values(text).items():',
     '    for key, value in ():'),
    ("cap: cap_safe passes text through, so a long value is neither cut nor marked",
     '    clean = CAP_CONTROL.sub(" ", text or "")',
     '    return text or ""\n    clean = CAP_CONTROL.sub(" ", text or "")'),
    ("cap: the bare-key pass is gone, so an unreadable value walks past",
     '    for found in SUBAGENT_CAP_KEY.finditer(text):\n'
     '        reading.setdefault(found.group(0), "")',
     '    for found in ():\n'
     '        reading.setdefault(found.group(0), "")'),
    ("cap: the rule runs ahead of the frozen-path deny, so the config settings ask instead",
     '        if is_frozen(target, cwd):\n'
     '            refuse(tool, "deny", "frozen-path", FROZEN_REASON, target)',
     '        if is_settings_file(target, cwd):\n'
     '            change = cap_change_parts(write_content_parts(tool_input))\n'
     '            if change:\n'
     '                refuse(tool, "ask", "subagent-model-cap", cap_ask_reason(change, target),\n'
     '                       target + " " + change)\n'
     '        if is_frozen(target, cwd):\n'
     '            refuse(tool, "deny", "frozen-path", FROZEN_REASON, target)'),
    ("cap: the shell route runs ahead of the frozen-path deny, so a heredoc onto the config "
     "settings asks instead",
     '    matched = frozen_shell_hit(stripped, cwd)\n'
     '    if matched:\n'
     '        refuse(tool, "deny", "frozen-path", FROZEN_REASON, matched)',
     '    matched = _shell_write_hit(stripped, cwd, is_settings_file)\n'
     '    if matched:\n'
     '        change = cap_change(raw)\n'
     '        if change:\n'
     '            refuse(tool, "ask", "subagent-model-cap", cap_ask_reason(change, matched),\n'
     '                   matched + " " + change)\n'
     '    matched = frozen_shell_hit(stripped, cwd)\n'
     '    if matched:\n'
     '        refuse(tool, "deny", "frozen-path", FROZEN_REASON, matched)'),
    ("cap: the shell route reads the stripped command, so a heredoc body's cap change walks past",
     '        change = cap_change(raw)',
     '        change = cap_change(stripped)'),
    ("cap: an earlier part wins, so an Edit names the value it leaves, not the one it arrives at",
     '            values[key] = value',
     '            values.setdefault(key, value)'),
    ("frozen-path: the config-watch baseline store is not frozen",
     '    os.path.normcase("state"),',
     '    os.path.normcase("state_unfrozen"),'),

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
    #     -> "silent-write: a discarded proof of landing, stdout alone"
    #   "silent-write: the merge --abort carve-out is gone"
    #     -> "silent-write: an abort lands nothing, so it is carved out"
    #   "silent-write: fetch joins the denied subcommands"
    #     -> "silent-write: fetch's own quiet flag is a carve-out"
    #   "silent-write: commit, tag, and cherry-pick rejoin the quiet-flag arm, the measured
    #   carve-outs undone"
    #     -> "silent-write: commit's own quiet flag is a carve-out, MEASURED 2026-09-19"
    ("silent-write: the rule never denies at all",
     '        matched, mechanism = silent_write_hit(segment)\n'
     '        if matched:\n'
     '            reason = (SILENT_WRITE_REDIRECT_REASON if mechanism == "redirect"\n'
     '                      else SILENT_WRITE_QUIET_REASON)\n'
     '            refuse(tool, "deny", "silent-write", reason, matched)',
     '        matched, mechanism = silent_write_hit(segment)\n'
     '        if False:\n'
     '            reason = (SILENT_WRITE_REDIRECT_REASON if mechanism == "redirect"\n'
     '                      else SILENT_WRITE_QUIET_REASON)\n'
     '            refuse(tool, "deny", "silent-write", reason, matched)'),
    ("silent-write: the quiet-flag arm no longer fires for any subcommand",
     '        if subcommand in QUIET_FLAG_SUBCOMMANDS and quiet_write(args):',
     '        if False and quiet_write(args):'),
    ("silent-write: a discarding redirect no longer silences anything",
     '        if discards_output(segment):\n            return matched, "redirect"',
     '        if False:\n            return matched, "redirect"'),
    ("silent-write: the merge --abort carve-out is gone",
     '        if subcommand == "merge" and "--abort" in args:\n            continue',
     '        if False:\n            continue'),
    ("silent-write: fetch joins the denied subcommands",
     'SILENT_WRITE_SUBCOMMANDS = ("commit", "push", "merge", "tag", "rebase", "cherry-pick")',
     'SILENT_WRITE_SUBCOMMANDS = ("commit", "push", "merge", "tag", "rebase", "cherry-pick", '
     '"fetch")'),
    ("silent-write: commit, tag, and cherry-pick rejoin the quiet-flag arm, the measured "
     "carve-outs undone",
     'QUIET_FLAG_SUBCOMMANDS = ("push", "merge", "rebase")',
     'QUIET_FLAG_SUBCOMMANDS = ("commit", "push", "merge", "tag", "rebase", "cherry-pick")'),

    # ---- the PostToolUse watch. These break `hooks/config_watch.py` and must be killed by
    # `hooks/test_config_watch.py`, which writes the cap for real and reads the file back.
    ("watch: never restore, only report",
     '    if not restore(path, baseline["content"]):',
     '    if False and not restore(path, baseline["content"]):', "watch"),
    ("watch: restore in silence, so a revert is never reported",
     '    if messages:\n        print(json.dumps({"systemMessage": " ".join(messages)}))',
     '    if False:\n        print(json.dumps({"systemMessage": " ".join(messages)}))', "watch"),
    ("watch: treat every write as explained, so nothing is ever undone",
     '    if explained and explained == resolve(path, cwd):',
     '    if True:', "watch"),
    ("watch: compare the bytes, not the cap reading, so an ordinary edit is reverted too",
     '    if reading == was:',
     '    if False:', "watch"),
    ("watch: watch settings.json alone, so the local file is unwatched",
     'WATCHED_NAMES = tuple(name.lstrip("/") for name in guard.PROJECT_FROZEN_FILES)',
     'WATCHED_NAMES = ("\x2eclaude/settings.json",)', "watch"),
    ("watch: an absent file reads the same as an empty one, so a created file is not a change",
     '    if content is None:\n        return ""\n    return hashlib.sha256(content).hexdigest()',
     '    return hashlib.sha256(content or b"").hexdigest()', "watch"),
    ("watch: a missing baseline is read as clear rather than recorded",
     '    if baseline is None:\n        save_baseline(path, current)',
     '    if baseline is None:\n        save_baseline(path, None)', "watch"),
]


def run_suite(suite: str, variable: str, copy_path: str, config_dir: str):
    """Run one fixture suite against one mutated copy. Return (exit code, FAIL lines)."""
    env = dict(os.environ)
    env.pop("GUARD_UNDER_TEST", None)
    env.pop("WATCH_UNDER_TEST", None)
    env[variable] = copy_path
    env["CLAUDE_CONFIG_DIR"] = config_dir
    result = subprocess.run(
        [sys.executable, suite], capture_output=True, text=True, env=env, timeout=1200,
    )
    red = [line for line in result.stdout.splitlines() if line.startswith("FAIL")]
    return result.returncode, red


def safe_name(label: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in label)[:60]


def mutation_parts(entry):
    """Return (label, old, new, target) for one mutation. The target defaults to the guard."""
    label, old, new = entry[0], entry[1], entry[2]
    target = entry[3] if len(entry) > 3 else "guard"
    return label, old, new, target


def run_mutant(sources, work: str, entry):
    """Apply one mutation, run its suite against it, and return (label, code, FAIL lines)."""
    label, old, new, target = mutation_parts(entry)
    _path, suite, variable, stem = TARGETS[target]
    mutated = sources[target].replace(old, new, 1)
    copy_path = os.path.join(work, "%s_%s.py" % (stem, safe_name(label)))
    with open(copy_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(mutated)
    config_dir = os.path.join(work, "cfg_%s" % safe_name(label))
    os.makedirs(config_dir, exist_ok=True)
    code, red = run_suite(suite, variable, copy_path, config_dir)
    return label, code, red


def job_count() -> int:
    """How many suites to run at once: MUTATE_JOBS, else the CPU count, at least one."""
    try:
        wanted = int(os.environ.get("MUTATE_JOBS", "") or 0)
    except ValueError:
        wanted = 0
    return max(1, wanted or os.cpu_count() or 1)


def main() -> int:
    sources = {}
    for name, (path, _suite, _variable, _stem) in TARGETS.items():
        with open(path, encoding="utf-8") as handle:
            sources[name] = handle.read()

    # Every anchor is checked BEFORE any suite runs, so a stale mutation fails in the first
    # second, not after the mutants ahead of it in the list have spent their minutes. A mutation
    # whose anchor sits in the WRONG file is stale too, which is what the target lookup catches.
    for entry in MUTATIONS:
        label, old, _new, target = mutation_parts(entry)
        if target not in TARGETS:
            print("ERROR unknown mutation target %r: %s" % (target, label))
            return 1
        if old not in sources[target]:
            print("ERROR stale mutation, anchor text not found: %s" % label)
            return 1

    work = tempfile.mkdtemp(prefix="mutate_guard_")
    survivors = 0
    jobs = job_count()
    print("%d mutations, %d at a time" % (len(MUTATIONS), jobs))
    try:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            results = pool.map(lambda entry: run_mutant(sources, work, entry), MUTATIONS)
            for label, code, red in results:
                if code == 0 or not red:
                    survivors += 1
                    print("SURVIVED  %-64s %2d red" % (label, len(red)), flush=True)
                else:
                    print("KILLED    %-64s %2d red" % (label, len(red)), flush=True)
        print()
        print("%d of %d mutations killed" % (len(MUTATIONS) - survivors, len(MUTATIONS)))
        return 1 if survivors else 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
