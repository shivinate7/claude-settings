#!/usr/bin/env python3
"""Cases for hooks/guard.py. Standard library only, and no test runner.

Run it from the repository root:

    python hooks/test_guard.py

Each case drives the guard as Claude Code drives it: one JSON object on stdin, and the decision read
back off stdout. An empty stdout is an allow. Anything else is parsed for permissionDecision.

BOTH DIRECTIONS ARE PINNED. A guard is exactly the wrong thing to change untested. Too loose and a
protected file is lost. Too tight and every session routes around it, which is the failure that
actually happened in both of the repositories this guard is ported from. So each GREEN case here is
as load-bearing as each RED one.

The cases come from two working guards and their own test suites:

  job-cost-reporting  harness/test_guard.py        the shared-tree cases
  q_max               harness/tests/guard.test.mjs the environment and frozen-path cases

Two literals are assembled from parts, so that this file cannot trip the guard it tests.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
# GUARD_UNDER_TEST points the suite at another copy of the guard, such as a `.bak` copy carrying
# one mutation. A mutation test then needs no copy of this file, so the cases cannot drift from the
# cases that pass.
GUARD = os.environ.get("GUARD_UNDER_TEST") or os.path.join(HERE, "guard.py")

# Assembled, so this file never holds the token whole.
ENV = "." + "env"
VCS = "g" + "it"

CASES = []


def add(name, expected, rule=None, raw=None, tool="Bash", cwd=None, env_path=None,
        **tool_input):
    CASES.append({
        "name": name,
        "expected": expected,
        "rule": rule,
        "raw": raw,
        "tool": tool,
        "cwd": cwd,
        "env_path": env_path,
        "tool_input": tool_input,
    })


def sh(name, command, expected, rule=None, tool="Bash", cwd=None, env_path=None):
    add(name, expected, rule=rule, tool=tool, cwd=cwd, env_path=env_path, command=command)


# --------------------------------------------------------------------------- the fixtures
#
# Every path a case names lives under one temporary root, so no case can reach the real
# configuration, the real log or a real repository.

ROOT = tempfile.mkdtemp(prefix="guard_cases_")
CFG = os.path.join(ROOT, "cfg")            # stands in for the config directory
LOGDIR = os.path.join(ROOT, "logcfg")      # a second config directory, for the log case
PROJ = os.path.join(ROOT, "proj")          # an ordinary project with its own .claude folder
CLONE = os.path.join(ROOT, "clone")        # the clone of claude-settings, which is NOT frozen
NOGIT = os.path.join(ROOT, "nogit")        # a directory that is not a git tree
GITMAIN = os.path.join(ROOT, "repo")       # an ordinary checkout, shared with other sessions
GITWT = os.path.join(ROOT, "lane")         # a linked worktree of that checkout
CONFLICT = os.path.join(ROOT, "conflict")  # a real checkout with an unresolved merge conflict
GHMAIN = os.path.join(ROOT, "ghmain")      # a fake command line tool answering "main"
GHDEV = os.path.join(ROOT, "ghdev")        # the same, answering "dev"
GHNONE = os.path.join(ROOT, "ghnone")      # an empty directory, so the tool is missing


def slash(path):
    return path.replace("\\", "/")


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def run_vcs(cwd, *args):
    return subprocess.run([VCS, *args], cwd=cwd, capture_output=True, text=True)


def _require_conflict(where, path):
    """Stop the suite unless `where` really holds an unresolved conflict on `path`.

    A fixture whose setup silently fails proves nothing: it can pass for the wrong reason on
    one machine and fail on another. This reads the tree with git itself, the same two checks
    the guard's own `conflict_in_progress` makes, so a broken build step is caught here rather
    than showing up later as a wrong PASS or a confusing FAIL far from its cause.
    """
    verify = run_vcs(where, "rev-parse", "--verify", "-q", "MERGE_HEAD")
    if verify.returncode != 0:
        sys.exit(
            "fixture setup failed in build_fixtures: MERGE_HEAD does not resolve in %r. "
            "The conflict-repo merge did not run, or it did not conflict. "
            "stderr: %s" % (where, verify.stderr.strip())
        )
    status = run_vcs(where, "status", "--porcelain")
    lines = [line for line in status.stdout.splitlines() if path in line]
    if not any(line[:2] in ("UU", "AA") for line in lines):
        sys.exit(
            "fixture setup failed in build_fixtures: %r is not left in an unresolved "
            "conflict state in %r. git status --porcelain shows: %r" % (path, where, lines)
        )


def make_fake_gh(folder, base):
    """Put a stand-in for the pull request tool in its own folder on PATH.

    MEASURED on Windows 2026-09-16: a call of "gh" through CreateProcess appends `.exe` and never
    reads PATHEXT, so a `gh.cmd` earlier on PATH was skipped and the real `gh.exe` further along
    answered instead. The guard resolves the program with shutil.which for that reason, and this
    stand-in is a `.cmd` file to keep the case honest on this machine.
    """
    os.makedirs(folder, exist_ok=True)
    body = '{"baseRefName":"%s"}' % base
    if os.name == "nt":
        write(os.path.join(folder, "gh.cmd"), "@echo off\r\necho " + body + "\r\n")
    else:
        script = os.path.join(folder, "gh")
        write(script, "#!/bin/sh\necho '" + body + "'\n")
        os.chmod(script, 0o755)


def build_fixtures():
    for folder in (CFG, LOGDIR, PROJ, CLONE, NOGIT, GITMAIN):
        os.makedirs(folder, exist_ok=True)
    write(os.path.join(CFG, "settings.json"), "{}\n")
    write(os.path.join(CFG, "CLAUDE.md"), "rules\n")
    write(os.path.join(CFG, "hooks", "guard.py"), "# hook\n")
    write(os.path.join(CFG, "lint", "prose.py"), "# lint\n")
    write(os.path.join(CFG, "agents", "builder.md"), "builder\n")
    write(os.path.join(PROJ, ".claude", "settings.json"), "{}\n")
    write(os.path.join(PROJ, ".claude", "settings.local.json"), "{}\n")
    write(os.path.join(PROJ, ".claude", "hooks", "g.py"), "# hook\n")
    write(os.path.join(PROJ, "src", "app.py"), "print(1)\n")
    # The clone of claude-settings. Its own settings.json is the SOURCE the install script copies,
    # so it must stay editable. The two marker files are what tell the clone from a config folder.
    write(os.path.join(CLONE, "settings.json"), "{}\n")
    write(os.path.join(CLONE, "install.ps1"), "# install\n")
    make_fake_gh(GHMAIN, "main")
    make_fake_gh(GHDEV, "dev")
    os.makedirs(GHNONE, exist_ok=True)
    # A real checkout and a real linked worktree of it. The shared-tree rule asks git which is
    # which, so no fake will do.
    run_vcs(GITMAIN, "init", "-q", "-b", "main", ".")
    run_vcs(GITMAIN, "-c", "user.email=cases@example.invalid", "-c", "user.name=cases",
            "commit", "-q", "--allow-empty", "-m", "first")
    run_vcs(GITMAIN, "worktree", "add", "-q", GITWT, "-b", "lane")

    # A real checkout with a real, unresolved merge conflict, built with git itself rather than
    # mocked. Two branches each change the same file, and merging one into the other leaves
    # MERGE_HEAD set and the file in the conflicted "AA" state, which git will not let a commit
    # leave silently.
    os.makedirs(CONFLICT, exist_ok=True)
    run_vcs(CONFLICT, "init", "-q", "-b", "main", ".")
    ident = ["-c", "user.email=cases@example.invalid", "-c", "user.name=cases"]
    write(os.path.join(CONFLICT, "docs", "DEBTS.md"), "base\n")
    run_vcs(CONFLICT, "add", "docs/DEBTS.md")
    run_vcs(CONFLICT, *ident, "commit", "-q", "-m", "base")
    run_vcs(CONFLICT, "checkout", "-q", "-b", "feature")
    write(os.path.join(CONFLICT, "docs", "DEBTS.md"), "feature change\n")
    run_vcs(CONFLICT, "add", "docs/DEBTS.md")
    run_vcs(CONFLICT, *ident, "commit", "-q", "-m", "feature change")
    run_vcs(CONFLICT, "checkout", "-q", "main")
    write(os.path.join(CONFLICT, "docs", "DEBTS.md"), "main change\n")
    run_vcs(CONFLICT, "add", "docs/DEBTS.md")
    run_vcs(CONFLICT, *ident, "commit", "-q", "-m", "main change")
    # MEASURED on CI (run 35182973995): this call ran with no `ident`, so on a runner with no
    # global git identity the merge refused before it ever touched the tree ("Committer identity
    # unknown", exit 128), MERGE_HEAD was never set, and the conflict-resolve fixtures below were
    # silently testing a CLEAN tree. It passed here only because this machine's own ~/.gitconfig
    # supplied an identity the fixture never asked for.
    run_vcs(CONFLICT, *ident, "merge", "feature")  # conflicts and leaves MERGE_HEAD set
    _require_conflict(CONFLICT, "docs/DEBTS.md")


build_fixtures()

CFG_SETTINGS = slash(os.path.join(CFG, "settings.json"))
CFG_CLAUDEMD = slash(os.path.join(CFG, "CLAUDE.md"))
CFG_HOOK = slash(os.path.join(CFG, "hooks", "guard.py"))
CFG_LINT = slash(os.path.join(CFG, "lint", "prose.py"))
CFG_AGENT = slash(os.path.join(CFG, "agents", "builder.md"))
PROJ_SETTINGS = slash(os.path.join(PROJ, ".claude", "settings.json"))
PROJ_LOCAL = slash(os.path.join(PROJ, ".claude", "settings.local.json"))
PROJ_HOOK = slash(os.path.join(PROJ, ".claude", "hooks", "g.py"))
PROJ_HOOKDIR = slash(os.path.join(PROJ, ".claude", "hooks"))
CLONE_SETTINGS = slash(os.path.join(CLONE, "settings.json"))
PY_PATH = os.path.dirname(sys.executable)


# =========================================================================== 1. shared trees
#
# Ported from job-cost-reporting harness/test_guard.py. The cases about that repository's read-only
# folder and its workbook binaries are left behind, because they are its own rules.
#
# In a directory that is not a git tree the rule denies, which is the fail-closed half: an unknown
# tree is not a safe tree.

sh("stash: set work aside in a shared tree", VCS + " stash push -u -m lane", "deny", "shared-tree",
   cwd=NOGIT)
sh("stash: a bare stash pushes, same as `stash push`", VCS + " stash", "deny", "shared-tree",
   cwd=NOGIT)
sh("stash: save is the old name for push", VCS + " stash save lane", "deny", "shared-tree",
   cwd=NOGIT)
sh("stash: drop destroys stashed work with no way back", VCS + " stash drop", "deny",
   "shared-tree", cwd=NOGIT)
sh("stash: clear destroys every stash with no way back", VCS + " stash clear", "deny",
   "shared-tree", cwd=NOGIT)
# `list` and `show` only read. `apply` and `pop` put work back, and git itself refuses to
# overwrite a modified file rather than clobber it (MEASURED against a real conflicting change,
# 2026-09-17). None of the four can discard a working tree, so the guard reads the ACTION word,
# not the subcommand name, and allows all four.
sh("stash: list only reads, no subcommand match", VCS + " stash list", "allow", cwd=NOGIT)
sh("stash: show only reads", VCS + " stash show", "allow", cwd=NOGIT)
sh("stash: apply puts work back, git refuses an overwrite", VCS + " stash apply", "allow",
   cwd=NOGIT)
sh("stash: pop puts work back, git refuses an overwrite", VCS + " stash pop stash@{0}", "allow",
   cwd=NOGIT)
sh("reset: throws the tree away", VCS + " reset --hard origin/main", "deny", "shared-tree",
   cwd=NOGIT)
sh("reset: --hard with no argument", VCS + " reset --hard", "deny", "shared-tree", cwd=NOGIT)
# A bare reset, and every flag except `--hard`, leaves the working tree alone, or aborts rather
# than overwrite a local change (MEASURED against a real uncommitted change, 2026-09-17: `--keep`
# and `--merge` both stopped with "Entry not up to date. Cannot merge." and the change survived).
# Only `--hard` rewrites the tree unconditionally, so it alone stays denied.
sh("reset: a plain reset only unstages, the working tree is untouched", VCS + " reset HEAD~1",
   "allow", cwd=NOGIT)
sh("reset: a bare reset with no argument", VCS + " reset", "allow", cwd=NOGIT)
sh("reset: an explicit mixed reset", VCS + " reset --mixed HEAD~1", "allow", cwd=NOGIT)
sh("reset: a soft reset moves the branch and touches nothing else", VCS + " reset --soft HEAD~1",
   "allow", cwd=NOGIT)
sh("reset: --keep aborts rather than overwrite a local change", VCS + " reset --keep HEAD~1",
   "allow", cwd=NOGIT)
sh("reset: --merge aborts rather than overwrite a local change", VCS + " reset --merge HEAD~1",
   "allow", cwd=NOGIT)
sh("reset: a reset naming a path only touches the index",
   VCS + " reset -- app/src/50_engine.js", "allow", cwd=NOGIT)
sh("reset: a reset at a commit naming a path only touches the index",
   VCS + " reset HEAD~1 -- app/src/50_engine.js", "allow", cwd=NOGIT)
sh("restore: overwrites a file", VCS + " restore app/src/50_engine.js", "deny", "shared-tree",
   cwd=NOGIT)
sh("restore: the whole tree", VCS + " restore .", "deny", "shared-tree", cwd=NOGIT)
sh("restore: staged and worktree together", VCS + " restore --staged --worktree src/jobStore.ts",
   "deny", "shared-tree", cwd=NOGIT)
sh("restore: the worktree flag alone still overwrites the file",
   VCS + " restore --worktree src/jobStore.ts", "deny", "shared-tree", cwd=NOGIT)
# `--staged` alone writes only the index. The working tree file is left as it was (MEASURED
# against a real uncommitted change, 2026-09-17).
sh("restore: staged alone only touches the index", VCS + " restore --staged src/jobStore.ts",
   "allow", cwd=NOGIT)
sh("restore: the short staged flag alone only touches the index",
   VCS + " restore -S src/jobStore.ts", "allow", cwd=NOGIT)
sh("checkout: a path after the double dash", VCS + " checkout -- app/src/50_engine.js", "deny",
   "shared-tree", cwd=NOGIT)
sh("checkout: a start point and a path", VCS + " checkout HEAD app/src/50_engine.js", "deny",
   "shared-tree", cwd=NOGIT)
sh("checkout: a folder", VCS + " checkout docs/", "deny", "shared-tree", cwd=NOGIT)
sh("checkout: the working directory", VCS + " checkout .", "deny", "shared-tree", cwd=NOGIT)
sh("checkout: a relative path", VCS + " checkout ./x", "deny", "shared-tree", cwd=NOGIT)
sh("checkout: HEAD and the double dash", VCS + " checkout HEAD -- CLAUDE.md", "deny",
   "shared-tree", cwd=NOGIT)
sh("checkout: an older commit and a path", VCS + " checkout HEAD~1 -- src/utils/benchmark.ts",
   "deny", "shared-tree", cwd=NOGIT)
sh("checkout: a branch and a path", VCS + " checkout main -- harness/check-invariants.mjs", "deny",
   "shared-tree", cwd=NOGIT)
sh("checkout: a named file", VCS + " checkout -- README.md", "deny", "shared-tree", cwd=NOGIT)

# PICKING A CONFLICT SIDE is not a discard. `--theirs` (or `--ours`, or `--merge`) resolves one
# side of an existing conflict; the tree is already left open by git itself, which will not let a
# commit go through silently. Built with a REAL merge conflict, never mocked, the same way the
# worktree cases above use a real checkout.
sh("checkout: --theirs resolves a real, unresolved merge conflict",
   VCS + " checkout --theirs docs/DEBTS.md", "allow", cwd=CONFLICT)
sh("checkout: the same call with no conflict in progress keeps today's decision",
   VCS + " checkout --theirs docs/DEBTS.md", "deny", "shared-tree", cwd=GITMAIN)
sh("checkout: a path with no conflict-side flag still denies, even in the conflicted tree",
   VCS + " checkout -- docs/DEBTS.md", "deny", "shared-tree", cwd=CONFLICT)
sh("checkout: a branch and a path still denies, even in the conflicted tree",
   VCS + " checkout main -- docs/", "deny", "shared-tree", cwd=CONFLICT)

sh("clean: -fd deletes untracked files", VCS + " clean -fd", "deny", "shared-tree", cwd=NOGIT)
sh("clean: the long force flag", VCS + " clean --force -d", "deny", "shared-tree", cwd=NOGIT)
sh("clean: the doubled force flag", VCS + " clean -ff", "deny", "shared-tree", cwd=NOGIT)
sh("clean: the flags bundled the other way", VCS + " clean -df", "deny", "shared-tree", cwd=NOGIT)
sh("shared tree: inside a compound command", "node harness/gate.js && " + VCS + " reset --hard",
   "deny", "shared-tree", cwd=NOGIT)
sh("shared tree: on a second line", VCS + " status\n" + VCS + " reset --hard\n", "deny",
   "shared-tree", cwd=NOGIT)
sh("shared tree: against another checkout", VCS + " -C ../other-worktree reset --hard", "deny",
   "shared-tree", cwd=NOGIT)
sh("shared tree: from the PowerShell tool as well", VCS + " reset --hard", "deny", "shared-tree",
   tool="PowerShell", cwd=NOGIT)
sh("shared tree: a stash from the PowerShell tool", VCS + " stash", "deny", "shared-tree",
   tool="PowerShell", cwd=NOGIT)

sh("clean: -n only lists", VCS + " clean -n", "allow", cwd=NOGIT)
sh("checkout: a new branch keeps every file", VCS + " checkout -b claude/lane main", "allow",
   cwd=NOGIT)
sh("checkout: a branch move keeps every file", VCS + " checkout main", "allow", cwd=NOGIT)
sh("checkout: a branch name holding a slash", VCS + " checkout claude/shared-tree-guard", "allow",
   cwd=NOGIT)
sh("checkout: the previous branch", VCS + " checkout -", "allow", cwd=NOGIT)
sh("checkout: a forced new branch at a commit", VCS + " checkout -B tmp 380d5fc", "allow",
   cwd=NOGIT)
sh("checkout: tracking a remote branch", VCS + " checkout --track origin/main", "allow", cwd=NOGIT)

# THE REDIRECT FALSE POSITIVE. MEASURED in guard.log: `git checkout origin/claude/pass3-seam 2>&1`
# was refused while the same call with no redirect passed, because `2>&1` reached
# `checkout_names_a_path` as a second plain word. A redirect must never change what a `git checkout`
# call is judged to name.
sh("checkout: a start point survives a merged-output redirect",
   VCS + " checkout origin/claude/pass3-seam 2>&1", "allow", cwd=NOGIT)
sh("checkout: a start point survives a discarded-error redirect",
   VCS + " checkout main 2>/dev/null", "allow", cwd=NOGIT)
sh("checkout: a new branch survives a log redirect and merged output",
   VCS + " checkout -b feat/x origin/feat/x >log.txt 2>&1", "allow", cwd=NOGIT)
sh("checkout: a status piped onward is not a checkout at all",
   VCS + " status 2>&1 | head -5", "allow", cwd=NOGIT)
sh("checkout: a path after the double dash survives a merged-output redirect",
   VCS + " checkout -- README.md 2>&1", "deny", "shared-tree", cwd=NOGIT)
sh("checkout: an older commit and a path survive a discarded-output redirect",
   VCS + " checkout HEAD~1 src/app.py >/dev/null", "deny", "shared-tree", cwd=NOGIT)
sh("stash: a discarded-error redirect is not a way past the rule",
   VCS + " stash 2>/dev/null", "deny", "shared-tree", cwd=NOGIT)
sh("shared tree: reading the tree", VCS + " status --porcelain", "allow", cwd=NOGIT)
sh("shared tree: a log is not a discard", VCS + " log main..HEAD --oneline", "allow", cwd=NOGIT)
sh("shared tree: a diff naming a path is not a discard", VCS + " diff --stat main..HEAD -- src/",
   "allow", cwd=NOGIT)
sh("shared tree: a cherry-pick is not a discard", VCS + " cherry-pick -n 380d5fc", "allow",
   cwd=NOGIT)
sh("shared tree: a fast-forward merge is not a discard", VCS + " merge --ff-only a6ab78d", "allow",
   cwd=NOGIT)
sh("shared tree: a compound of allowed commands", VCS + " checkout -b lane; " + VCS + " status",
   "allow", tool="PowerShell", cwd=NOGIT)

# THE WORKTREE HALF. A discard in a linked worktree loses only that lane's own work, so it asks. In
# the shared checkout it denies. The guard asks git which tree it stands in, so these four cases
# drive a real checkout and a real worktree built beside it.
sh("worktree: a hard reset in the shared checkout denies", VCS + " reset --hard", "deny",
   "shared-tree", cwd=GITMAIN)
sh("worktree: the same reset inside a worktree asks", VCS + " reset --hard", "ask",
   "shared-tree", cwd=GITWT)
sh("worktree: -C naming the worktree asks, from the shared checkout",
   VCS + " -C " + slash(GITWT) + " reset --hard", "ask", "shared-tree", cwd=GITMAIN)
sh("worktree: a cd into the worktree asks, from the shared checkout",
   "cd " + slash(GITWT) + " && " + VCS + " reset --hard", "ask", "shared-tree", cwd=GITMAIN)

# THE TABLE'S ALLOW ROWS, checked in both a shared checkout and a worktree, so an allow is proven
# to hold regardless of which tree the call runs in — a read or a restore never needed the
# worktree/shared split, which the rows below confirm rather than assume.
for _tree_name, _tree_path in (("shared checkout", GITMAIN), ("worktree", GITWT)):
    sh("stash: list allows in the " + _tree_name, VCS + " stash list", "allow", cwd=_tree_path)
    sh("stash: show allows in the " + _tree_name, VCS + " stash show", "allow", cwd=_tree_path)
    sh("stash: apply allows in the " + _tree_name, VCS + " stash apply", "allow", cwd=_tree_path)
    sh("stash: pop allows in the " + _tree_name, VCS + " stash pop", "allow", cwd=_tree_path)
    sh("reset: a plain reset allows in the " + _tree_name, VCS + " reset HEAD~1", "allow",
       cwd=_tree_path)
    sh("reset: --soft allows in the " + _tree_name, VCS + " reset --soft HEAD~1", "allow",
       cwd=_tree_path)
    sh("reset: --keep allows in the " + _tree_name, VCS + " reset --keep HEAD~1", "allow",
       cwd=_tree_path)
    sh("reset: --merge allows in the " + _tree_name, VCS + " reset --merge HEAD~1", "allow",
       cwd=_tree_path)
    sh("reset: naming a path allows in the " + _tree_name, VCS + " reset -- f.txt", "allow",
       cwd=_tree_path)
    sh("restore: --staged alone allows in the " + _tree_name, VCS + " restore --staged f.txt",
       "allow", cwd=_tree_path)

# THE OWNER'S EXACT COMMAND, carrying a redirect and a pipe into `tail`. `tail -10` is not a
# follow, so it must not trip the live-stream rule either.
sh("stash: the owner's exact apply command allows in the shared checkout",
   VCS + " stash apply stash@{0} 2>&1 | tail -10", "allow", cwd=GITMAIN)
sh("stash: the owner's exact apply command allows in a worktree",
   VCS + " stash apply stash@{0} 2>&1 | tail -10", "allow", cwd=GITWT)

# A COMMIT MESSAGE DISCUSSES THESE COMMANDS. MEASURED in job-cost-reporting on 2026-08-20: a
# heredoc body was read as a command, and a commit message naming the protected folder was refused.
sh("heredoc: a commit message that discusses the refused commands",
   VCS + " commit -F - <<'EOF'\n"
   "guard: refuse the reset, the restore and the stash in a shared tree\n"
   "also refuse pkill -f and lsof -t, which reach the whole machine\n"
   "EOF",
   "allow", cwd=NOGIT)
sh("heredoc: prose naming the stash with no interpreter",
   "cat > notes.md <<'DOC'\nNever run " + VCS + " stash in a shared checkout.\nDOC",
   "allow", cwd=NOGIT)
sh("heredoc: a body fed to a shell stays under inspection",
   "bash <<EOF\n" + VCS + " stash\nEOF", "deny", "shared-tree", cwd=NOGIT)
# THE DOCUMENTED HOLE. The body of an interpreter heredoc IS kept under inspection, but the
# shared-tree rule reads whitespace-separated words, and `os.system("git stash")` puts the call
# inside a quoted string. The guard allows it, and this case says so rather than hiding it.
sh("heredoc: a quoted call inside python source is not parsed as a shell call",
   "python - <<EOF\nimport os\nos.system(\"" + VCS + " stash\")\nEOF", "allow", cwd=NOGIT)


# =========================================================================== 2. machine-wide kills

sh("kill: pkill by pattern", "pkill -f node", "deny", "machine-wide-kill", cwd=NOGIT)
sh("kill: pkill by name reaches every match", "pkill node", "deny", "machine-wide-kill", cwd=NOGIT)
sh("kill: pkill with the long flag", 'pkill --full "node server.ts"', "deny", "machine-wide-kill",
   cwd=NOGIT)
sh("kill: killall by name", "killall node", "deny", "machine-wide-kill", cwd=NOGIT)
sh("kill: lsof -t feeds a kill list", "lsof -t -i :3000", "deny", "machine-wide-kill", cwd=NOGIT)
sh("kill: the same flag bundled", "lsof -ti :3000", "deny", "machine-wide-kill", cwd=NOGIT)
sh("kill: taskkill by image name", "taskkill /IM node.exe /F", "deny", "machine-wide-kill",
   cwd=NOGIT)
sh("kill: taskkill by image name, dash spelling", "taskkill -im node.exe", "deny",
   "machine-wide-kill", cwd=NOGIT)
sh("kill: Stop-Process by name", "Stop-Process -Name node", "deny", "machine-wide-kill",
   tool="PowerShell", cwd=NOGIT)
sh("kill: Stop-Process by name, abbreviated", "Stop-Process -n node", "deny", "machine-wide-kill",
   tool="PowerShell", cwd=NOGIT)

sh("kill: asking which port is busy kills nothing", "lsof -i :3000", "allow", cwd=NOGIT)
sh("kill: one process id in Bash", "kill 123", "allow", cwd=NOGIT)
sh("kill: one process id with taskkill", "taskkill /PID 4711 /F", "allow", cwd=NOGIT)
sh("kill: one process id with Stop-Process", "Stop-Process -Id 123", "allow", tool="PowerShell",
   cwd=NOGIT)
sh("kill: taskkill by image name, no other flag", "taskkill /IM node.exe", "deny",
   "machine-wide-kill", cwd=NOGIT)
sh("kill: xargs unwraps to the real command it runs", "xargs pkill", "deny",
   "machine-wide-kill", cwd=NOGIT)

# THE PREDICATE IS THE ACT, NOT THE TOOL OR THE SPELLING. MEASURED: the owner ran
# `grep -n -i "...|make reap|pkill..." CLAUDE.md` to search CLAUDE.md for the word, and it was
# denied as a machine-wide kill, although the command calls grep. Each case below names the word
# without ever calling the program that shares it.
sh("kill: a grep for the word is not a call to it, the owner's report",
   'grep -n -i "graceful shutdown|make reap|pkill" CLAUDE.md', "allow", cwd=NOGIT)
sh("kill: the word inside a single-quoted argument",
   "grep -n -i 'graceful shutdown|make reap|pkill' CLAUDE.md", "allow", cwd=NOGIT)
sh("kill: an echoed word and flag, quoted, prints text and calls nothing",
   'echo "pkill -f node"', "allow", cwd=NOGIT)
sh("kill: the word on the far side of a pipe filter", "cat notes.md | grep pkill", "allow",
   cwd=NOGIT)
sh("kill: a quoted phrase ahead of a real chained kill still denies",
   'echo "safe text" && pkill node', "deny", "machine-wide-kill", cwd=NOGIT)


# =========================================================================== 2b. live streams
#
# CLAUDE.md: "Never pipe a live stream through `tail`." A follow flag never ends on its own, so
# it outlives the turn and the agent that started it.

sh("stream: tail -f never ends", "tail -f app.log", "deny", "live-stream", cwd=NOGIT)
sh("stream: tail -F retries across rotation", "tail -F app.log", "deny", "live-stream", cwd=NOGIT)
sh("stream: the long follow flag", "tail --follow=name app.log", "deny", "live-stream", cwd=NOGIT)
sh("stream: a combined short flag", "tail -fn 20 app.log", "deny", "live-stream", cwd=NOGIT)
sh("stream: Get-Content -Wait never ends", "Get-Content app.log -Wait", "deny", "live-stream",
   tool="PowerShell", cwd=NOGIT)

sh("stream: an ordinary line count", "tail -n 50 app.log", "allow", cwd=NOGIT)
sh("stream: a short line count", "tail -5 app.log", "allow", cwd=NOGIT)
sh("stream: a pipe into a bounded tail", "python x.py | tail -5", "allow", cwd=NOGIT)
sh("stream: Get-Content -Tail reads and stops", "Get-Content app.log -Tail 20", "allow",
   tool="PowerShell", cwd=NOGIT)


# =========================================================================== 2c. waiter loops
#
# Rule 9, approved by the owner. A pause between polls turns waiting into a loop of turns that
# each print a word.

sh("waiter: a bare sleep", "sleep 30", "deny", "waiter", cwd=NOGIT)
sh("waiter: sleep ahead of a poll", "sleep 5 && gh pr list", "deny", "waiter", cwd=NOGIT)
sh("waiter: Start-Sleep on PowerShell", "Start-Sleep -Seconds 10", "deny", "waiter",
   tool="PowerShell", cwd=NOGIT)
sh("waiter: timeout /t on Windows cmd", "timeout /t 5", "deny", "waiter", cwd=NOGIT)

sh("waiter: a tool that waits once is allowed", "gh pr checks 12 --watch", "allow", cwd=NOGIT)
sh("waiter: a readiness check is allowed", "curl --retry 5 http://localhost:3000", "allow",
   cwd=NOGIT)
sh("waiter: an unrelated log query is allowed", VCS + " log --since=yesterday", "allow", cwd=NOGIT)


# =========================================================================== 3. push and delete

sh("push: the long force flag", VCS + " push --force", "ask", "force-push", cwd=NOGIT)
sh("push: the short force flag", VCS + " push -f origin x", "ask", "force-push", cwd=NOGIT)
sh("push: force with lease", VCS + " push --force-with-lease", "ask", "force-push", cwd=NOGIT)
sh("push: force with lease naming a ref", VCS + " push --force-with-lease=main origin main", "ask",
   "force-push", cwd=NOGIT)
sh("push: force from the PowerShell tool as well", VCS + " push --force-with-lease", "ask",
   "force-push", tool="PowerShell", cwd=NOGIT)
sh("push: an ordinary push", VCS + " push", "allow", cwd=NOGIT)
sh("push: setting the upstream", VCS + " push -u origin claude/lane", "allow", cwd=NOGIT)

sh("delete: the root", "rm -rf /", "deny", "destructive-delete", cwd=NOGIT)
sh("delete: the home directory", "rm -fr ~", "deny", "destructive-delete", cwd=NOGIT)
sh("delete: the home variable", "rm -rf $HOME", "deny", "destructive-delete", cwd=NOGIT)
sh("delete: the working directory", "rm -rf .", "deny", "destructive-delete", cwd=NOGIT)
sh("delete: a glob", "rm -rf *", "deny", "destructive-delete", cwd=NOGIT)
sh("delete: a drive root", "rm -rf C:/", "deny", "destructive-delete", cwd=NOGIT)
sh("delete: Remove-Item at a drive root", "Remove-Item -Recurse -Force C:\\", "deny",
   "destructive-delete", tool="PowerShell", cwd=NOGIT)
sh("delete: Remove-Item at the working directory", "Remove-Item -Recurse -Force .", "deny",
   "destructive-delete", tool="PowerShell", cwd=NOGIT)
sh("delete: Remove-Item with abbreviated flags at a glob", "Remove-Item -r -fo *", "deny",
   "destructive-delete", tool="PowerShell", cwd=NOGIT)
sh("delete: the alias, a drive root, and the flags after the target", "ri C:\\ -Recurse -Force",
   "deny", "destructive-delete", tool="PowerShell", cwd=NOGIT)
sh("delete: PowerShell folds case", "REMOVE-ITEM -RECURSE -FORCE ~", "deny", "destructive-delete",
   tool="PowerShell", cwd=NOGIT)

# PARITY is the point, not breadth. `rm -rf build/` is allowed, so its PowerShell twin must be too.
# A guard that answers differently for the same act teaches which tool to reach for.
sh("delete: a named build folder", "rm -rf build/", "allow", cwd=NOGIT)
sh("delete: a named dependency folder", "rm -rf node_modules", "allow", cwd=NOGIT)
sh("delete: the PowerShell twin of a named folder", "Remove-Item -Recurse -Force node_modules",
   "allow", tool="PowerShell", cwd=NOGIT)
sh("delete: one scratch file", "rm -f /tmp/scratch.txt", "allow", cwd=NOGIT)


# =========================================================================== 4. environment files
#
# Ported whole from q_max. The rule is about the CONTENTS of the file, so a read is refused as
# firmly as a write, and a runner that loads the file into its own environment is allowed by name.

add("env: Read of the file", "deny", "env-file", tool="Read", cwd=NOGIT,
    file_path=slash(os.path.join(PROJ, ENV)))
add("env: Write of the file", "deny", "env-file", tool="Write", cwd=NOGIT,
    file_path=slash(os.path.join(PROJ, ENV)))
add("env: Edit of the file", "deny", "env-file", tool="Edit", cwd=NOGIT,
    file_path=slash(os.path.join(PROJ, ENV)))
add("env: Edit of a variant", "deny", "env-file", tool="Edit", cwd=NOGIT,
    file_path=slash(os.path.join(PROJ, ENV + ".local")))
add("env: MultiEdit of the file", "deny", "env-file", tool="MultiEdit", cwd=NOGIT,
    file_path=slash(os.path.join(PROJ, ENV)))
add("env: NotebookEdit of a variant", "deny", "env-file", tool="NotebookEdit", cwd=NOGIT,
    notebook_path=slash(os.path.join(PROJ, ENV + ".ipynb")))
add("env: Grep naming the file by path", "deny", "env-file", tool="Grep", cwd=NOGIT,
    path=slash(os.path.join(PROJ, ENV + ".local")))
# The reviewer's own payload, pinned by name. Every refused case is checked for a leaked file
# name, and this one holds the exact shape the review asked for.
add("env: a Read outside the fixtures, and the reason names no file", "deny", "env-file",
    tool="Read", cwd="C:/repo", file_path="C:/repo/" + ENV)
add("env: Read of the example file", "allow", tool="Read", cwd=NOGIT,
    file_path=slash(os.path.join(PROJ, ENV + ".example")))
add("env: Edit of the example file", "allow", tool="Edit", cwd=NOGIT,
    file_path=slash(os.path.join(PROJ, ENV + ".example")))

sh("env: the two measured false positives, the accessor search",
   'grep -n "dotenv|VERIFY_DATABASE_URL|process\\' + ENV + '" harness/browser/verify.mjs',
   "allow", cwd=NOGIT)
sh("env: the two measured false positives, a listing", "ls -la " + ENV, "allow", cwd=NOGIT)
for accessor in (
    'grep -rn "process' + ENV + '.DATABASE_URL" src/',
    'grep -rn "import.meta' + ENV + '" src/',
    'rg "process\\' + ENV + '" server.ts',
    'grep -c "process\\' + ENV + '" src/utils/inflight.ts',
    "grep -rn dotenv harness/",
    'grep -rn "import\\.meta\\' + ENV + '" src/',
    'grep -rn "a\\.b\\.c' + ENV + '" src/',
):
    sh("env: the accessor never matches, " + accessor[:44], accessor, "allow", cwd=NOGIT)

sh("env: an absolute Windows path is still a path", "cat C:\\Users\\me\\" + ENV, "deny",
   "env-file", cwd=NOGIT)
sh("env: a dot-slash Windows path is still a path", "cat .\\" + ENV, "deny", "env-file", cwd=NOGIT)
sh("env: an absolute path through a dot segment", "cat C:\\Users\\me\\.config\\" + ENV, "deny",
   "env-file", cwd=NOGIT)

sh("env: ls reads no contents", "ls " + ENV, "allow", cwd=NOGIT)
sh("env: test -f reads no contents", "test -f " + ENV, "allow", cwd=NOGIT)
sh("env: a bracket existence test", "[ -f " + ENV + " ] && echo present", "allow", cwd=NOGIT)

for runner in (
    "node --env-file=" + ENV + " harness/browser/verify.mjs",
    "node --env-file-if-exists=" + ENV + " harness/browser/verify.mjs",
    "node --env-file " + ENV + " harness/browser/verify.mjs",
    "node --env-file=" + ENV + " /c/Users/x/node_modules/npm/bin/npm-cli.js run verify:browser",
    "npm --env-file=" + ENV + " run verify:browser",
    "npx --env-file=" + ENV + " tsx server.ts",
    "node --env-file=" + ENV + " app.js",
    "pnpm --env-file=" + ENV + " run dev",
    "docker --env-file=" + ENV + " run image",
    "podman --env-file " + ENV + " run image",
    "bun --env-file=" + ENV + " run index.ts",
    "deno --env-file=" + ENV + " run main.ts",
    "uv --env-file=" + ENV + " run main.py",
):
    sh("env: a runner may be handed the file, " + runner[:40], runner, "allow", cwd=NOGIT)

sh("env: the loader flag is not a way to print the file", "cat --env-file=" + ENV, "deny",
   "env-file", cwd=NOGIT)

for printer in (
    "cat " + ENV, "type " + ENV, "head -5 " + ENV, "tail -1 " + ENV, "less " + ENV,
    "more " + ENV, "strings " + ENV, "xxd " + ENV, "od -c " + ENV, "sed -n 1p " + ENV,
    "grep DATABASE_URL " + ENV, 'cat "' + ENV + '"',
):
    sh("env: printing stays blocked, " + printer[:34], printer, "deny", "env-file", cwd=NOGIT)

for writer in (
    "echo X=1 > " + ENV, "echo X=1 >> " + ENV, "echo X=1 | tee " + ENV,
    "cp other.txt " + ENV, "cp " + ENV + " /tmp/leak", "mv " + ENV + " " + ENV + ".bak",
    "rm " + ENV, "truncate -s 0 " + ENV, "sed -i s/a/b/ " + ENV,
):
    sh("env: writing stays blocked, " + writer[:34], writer, "deny", "env-file", cwd=NOGIT)

sh("env: a commit of the file", VCS + " add " + ENV, "deny", "env-file", cwd=NOGIT)
sh("env: a commit of the file with -A", VCS + " add -A " + ENV, "deny", "env-file", cwd=NOGIT)
sh("env: a commit naming the file", VCS + " commit -m x " + ENV, "deny", "env-file", cwd=NOGIT)
# The shared-tree rule stands ahead of the environment rule, so a stash naming the file is refused
# as a stash. Both rules deny, and the precedence is the only thing that differs.
sh("env: a stash naming the file is refused by the earlier rule",
   VCS + " stash push -- " + ENV, "deny", "shared-tree", cwd=NOGIT)

for token in (
    "cat ./" + ENV, "cat harness/" + ENV, "cat /c/Users/me/" + ENV,
    'cat "C:\\Users\\me\\' + ENV + '"', "cat " + ENV + ".local",
):
    sh("env: a path token wherever the path puts it, " + token[:34], token, "deny", "env-file",
       cwd=NOGIT)

sh("env: the allowance does not leak, a listing then a read",
   "ls " + ENV + " && cat " + ENV, "deny", "env-file", cwd=NOGIT)
sh("env: the allowance does not leak, a test then a read",
   "test -f " + ENV + "; cat " + ENV, "deny", "env-file", cwd=NOGIT)
sh("env: the allowance does not leak, a read piped onward",
   "cat " + ENV + " | grep KEY", "deny", "env-file", cwd=NOGIT)
sh("env: the allowance does not leak, a loader then a read",
   "node --env-file=" + ENV + " script.mjs && cat " + ENV, "deny", "env-file", cwd=NOGIT)

sh("env: a redirect beats the existence allowance", "ls > " + ENV, "deny", "env-file", cwd=NOGIT)
sh("env: a shell variable holding the path", "ENVF=/repo/" + ENV, "deny", "env-file", cwd=NOGIT)
sh("env: an assignment ahead of a read", 'ENVF=' + ENV + ' cat "$ENVF"', "deny", "env-file",
   cwd=NOGIT)
sh("env: a loader given a variable names no path token",
   'node --env-file="$ENVF" harness/browser/verify.mjs', "allow", cwd=NOGIT)

for example in (
    "cat " + ENV + ".example", VCS + " add " + ENV + ".example",
    "cp " + ENV + ".example /tmp/x", "grep DATABASE_URL " + ENV + ".example",
):
    sh("env: the example file is documentation, " + example[:34], example, "allow", cwd=NOGIT)

sh("env: PowerShell Get-Content", "Get-Content " + ENV, "deny", "env-file", tool="PowerShell",
   cwd=NOGIT)
sh("env: PowerShell alias and a dot-slash path", "gc .\\" + ENV, "deny", "env-file",
   tool="PowerShell", cwd=NOGIT)
sh("env: PowerShell Get-Content of the example file", "Get-Content " + ENV + ".example", "allow",
   tool="PowerShell", cwd=NOGIT)
sh("env: the accessor search in the other shell",
   "Select-String -Pattern 'import\\.meta\\" + ENV + "' -Path src/main.tsx", "allow",
   tool="PowerShell", cwd=NOGIT)


# =========================================================================== 5. merge into main
#
# Decision 8 ("Merge into main: allow and report") supersedes Decision 2 ("ask always"). Every
# merge call is now an ALLOW; the guard log is what carries the base and the tool, checked in
# merge_log_case() below.

sh("merge: a base of main is allowed", "gh pr merge 12 --squash", "allow", cwd=NOGIT,
   env_path=GHMAIN + os.pathsep + PY_PATH)
sh("merge: a base of dev is allowed", "gh pr merge 12 --squash", "allow", cwd=NOGIT,
   env_path=GHDEV + os.pathsep + PY_PATH)
sh("merge: an unreadable base is allowed", "gh pr merge 12 --squash", "allow",
   cwd=NOGIT, env_path=GHNONE + os.pathsep + PY_PATH)
sh("merge: no number is allowed", "gh pr merge", "allow",
   cwd=NOGIT, env_path=GHMAIN + os.pathsep + PY_PATH)
sh("merge: reading a pull request is untouched", "gh pr view 75 --json baseRefName", "allow",
   cwd=NOGIT, env_path=GHMAIN + os.pathsep + PY_PATH)
sh("merge: opening a pull request is untouched", "gh pr create --base main --title x --body y",
   "allow", cwd=NOGIT, env_path=GHMAIN + os.pathsep + PY_PATH)
add("merge: every call of the merge tool is allowed", "allow",
    tool="mcp__github__merge_pull_request", cwd=NOGIT, pullNumber=12, repo="x", owner="y")


# =========================================================================== 6. frozen paths
#
# Ported from q_max, with that repository's own two frozen paths replaced by the global set. The
# file-tool check is the WALL: an exact resolved path, and no heuristics. The shell check is a
# backstop over it, and a backstop that reads a command as one blob cannot tell a write from a
# mention, so both directions are pinned below.

for tool in ("Write", "Edit", "MultiEdit"):
    add("frozen: " + tool + " of the config settings", "deny", "frozen-path", tool=tool, cwd=NOGIT,
        file_path=CFG_SETTINGS)
    add("config-edit: " + tool + " of a project settings file is allowed", "allow", tool=tool,
        cwd=NOGIT, file_path=PROJ_SETTINGS)
add("frozen: Write of the global CLAUDE.md", "deny", "frozen-path", tool="Write", cwd=NOGIT,
    file_path=CFG_CLAUDEMD)
add("frozen: Write of a config hook", "deny", "frozen-path", tool="Write", cwd=NOGIT,
    file_path=CFG_HOOK)
add("frozen: Write of a config lint script", "deny", "frozen-path", tool="Write", cwd=NOGIT,
    file_path=CFG_LINT)
add("frozen: Write of a config agent file", "deny", "frozen-path", tool="Write", cwd=NOGIT,
    file_path=CFG_AGENT)
add("config-edit: Edit of a project local settings file is allowed", "allow", tool="Edit",
    cwd=NOGIT, file_path=PROJ_LOCAL)
add("config-edit: Edit of a project hook is allowed", "allow", tool="Edit", cwd=NOGIT,
    file_path=PROJ_HOOK)
add("config-edit: NotebookEdit of a project hook is allowed", "allow", tool="NotebookEdit",
    cwd=NOGIT, notebook_path=PROJ_HOOK)
# MEASURED on Linux CI 2026-09-16: guard.py's own docstring scopes this equivalence to
# Windows ("a forward slash, a backslash ... all read the same on Windows"). On POSIX a
# backslash is an ordinary filename character, not a separator, so the same text swap
# builds an unrelated relative path instead of an alternate spelling of the frozen file.
add("frozen: a backslash spelling of the same path",
    "deny" if os.name == "nt" else "allow", "frozen-path" if os.name == "nt" else None,
    tool="Write", cwd=NOGIT, file_path=CFG_SETTINGS.replace("/", "\\"))
add("config-edit: a relative spelling resolved against the cwd is allowed", "allow", tool="Write",
    cwd=PROJ, file_path=".claude/settings.json")

add("frozen: a frozen path stays readable", "allow", tool="Read", cwd=NOGIT,
    file_path=CFG_SETTINGS)
add("frozen: a frozen hook stays readable", "allow", tool="Read", cwd=NOGIT, file_path=CFG_HOOK)
add("frozen: Grep may look at a frozen path", "allow", tool="Grep", cwd=NOGIT, path=CFG_SETTINGS)
# THE CLONE IS NOT FROZEN. Its settings.json is the SOURCE the install script copies into the
# config directory, so a guard that froze it would freeze the only way to change the rules.
add("frozen: the clone of claude-settings is editable", "allow", tool="Edit", cwd=CLONE,
    file_path=CLONE_SETTINGS)
add("frozen: the clone's settings by a relative name", "allow", tool="Write", cwd=CLONE,
    file_path="settings.json")
add("frozen: an ordinary source file", "allow", tool="Edit", cwd=NOGIT, file_path="src/app.py")
add("frozen: an ordinary project file by absolute path", "allow", tool="Write", cwd=NOGIT,
    file_path=slash(os.path.join(PROJ, "src", "app.py")))

sh("config-edit: a redirect onto a project settings file is allowed",
   "echo '{}' > " + PROJ_SETTINGS, "allow", cwd=NOGIT)
sh("config-edit: an append onto a project settings file is allowed",
   "echo '{}' >> " + PROJ_SETTINGS, "allow", cwd=NOGIT)
sh("frozen: a redirect onto the global CLAUDE.md", "echo x > " + CFG_CLAUDEMD, "deny",
   "frozen-path", cwd=NOGIT)
sh("frozen: a redirect onto a config hook", "cat template.py > " + CFG_HOOK, "deny", "frozen-path",
   cwd=NOGIT)
sh("config-edit: rm of a project settings file is allowed", "rm " + PROJ_SETTINGS, "allow",
   cwd=NOGIT)
sh("config-edit: mv of a project settings file is allowed",
   "mv " + PROJ_SETTINGS + " elsewhere.json", "allow", cwd=NOGIT)
sh("config-edit: chmod of a project hook is allowed", "chmod 000 " + PROJ_HOOK, "allow", cwd=NOGIT)
sh("config-edit: sed -i on a project settings file is allowed",
   "sed -i s/a/b/ " + PROJ_SETTINGS, "allow", cwd=NOGIT)
sh("config-edit: tee onto a project settings file is allowed",
   "echo x | tee " + PROJ_SETTINGS, "allow", cwd=NOGIT)
sh("config-edit: truncate of a project hook is allowed", "truncate -s 0 " + PROJ_HOOK, "allow",
   cwd=NOGIT)
sh("config-edit: a heredoc redirected onto a settings file is allowed",
   "cat <<'DOC' > " + PROJ_SETTINGS + "\n{ \"hooks\": {} }\nDOC", "allow",
   cwd=NOGIT)
sh("frozen: a heredoc redirected onto the environment file",
   "cat <<'DOC' > " + ENV + "\nKEY=value\nDOC", "deny", "env-file", cwd=NOGIT)

sh("config-edit: PowerShell Set-Content is allowed",
   "Set-Content -Path " + PROJ_SETTINGS + " -Value 'x'", "allow", tool="PowerShell", cwd=NOGIT)
sh("config-edit: PowerShell Out-File with backslashes is allowed",
   "'x' | Out-File " + PROJ_SETTINGS.replace("/", "\\"), "allow", tool="PowerShell",
   cwd=NOGIT)
sh("config-edit: PowerShell Add-Content is allowed", "Add-Content " + PROJ_HOOK + " 'x'", "allow",
   tool="PowerShell", cwd=NOGIT)
sh("config-edit: PowerShell Remove-Item is allowed", "Remove-Item " + PROJ_SETTINGS, "allow",
   tool="PowerShell", cwd=NOGIT)
sh("config-edit: PowerShell Copy-Item is allowed", "Copy-Item other.json " + PROJ_SETTINGS,
   "allow", tool="PowerShell", cwd=NOGIT)

# THE THREE MEASURED FALSE POSITIVES of the q_max backstop. Each was a case of judging the TEXT of a
# command instead of its behaviour.
sh("frozen: a file-descriptor redirect is not a write to the file being read",
   "cat " + PROJ_SETTINGS + " 2>/dev/null", "allow", cwd=NOGIT)
sh("frozen: running a hook with merged output", "python " + PROJ_HOOK + " 2>&1", "allow",
   cwd=NOGIT)
sh("frozen: a read-only inspection of both",
   "wc -l " + PROJ_SETTINGS + " 2>/dev/null; ls " + PROJ_HOOKDIR, "allow", cwd=NOGIT)
sh("frozen: a frozen path named only in a comment",
   'echo "hello" > notes.txt   # ' + PROJ_SETTINGS + " is protected, do not edit", "allow",
   cwd=NOGIT)
sh("frozen: searching for the path name and writing the results elsewhere",
   'grep -rn "' + PROJ_SETTINGS + '" docs/ > /tmp/hits.txt', "allow", cwd=NOGIT)
sh("frozen: a heredoc writing prose that names the environment file",
   "cat > notes.md <<'DOC'\nThe guard refuses any command naming " + ENV + ".\nDOC", "allow",
   cwd=NOGIT)

# NO OVERRIDE TOKEN IS A SKELETON KEY, because no override token exists any more. A leftover token
# from either earlier guard changes nothing.
sh("frozen: a leftover token is not a key to the environment rule",
   "DESTRUCTIVE_OK=1 cat " + ENV, "deny", "env-file", cwd=NOGIT)
sh("frozen: a leftover token is not a key to the frozen rule",
   "DESTRUCTIVE_OK=1 tee " + CFG_SETTINGS, "deny", "frozen-path", cwd=NOGIT)
sh("frozen: a leftover token is not a key to the shared-tree rule",
   "GIT_DISCARD_OK=1 " + VCS + " restore src", "deny", "shared-tree", cwd=NOGIT)
sh("frozen: a leftover token is not a key to the push rule",
   "GIT_DISCARD_OK=1 " + VCS + " push --force", "ask", "force-push", cwd=NOGIT)


# =========================================================================== ordinary work

for ordinary in (
    "npm test",
    "node harness/check-invariants.mjs",
    VCS + " status --short",
    VCS + " add -A",
    VCS + " add -A && " + VCS + " commit -m WIP",
    'grep -rn "tieOutState" src/',
    'sed -i "s/a/b/" src/components/Dashboard.tsx',
    "python hooks/test_guard.py",
):
    sh("ordinary: " + ordinary[:44], ordinary, "allow", cwd=NOGIT)
sh("ordinary: npm ci is not the PowerShell ci alias", "npm ci", "allow", tool="PowerShell",
   cwd=NOGIT)


# =========================================================================== failing open

add("open: a payload with no command", "allow", tool="Bash", cwd=NOGIT)
add("open: a tool the guard does not handle", "allow", tool="Glob", cwd=NOGIT, pattern="**/*.ts")
add("open: a tool with a path the guard does not handle", "allow", tool="WebFetch", cwd=NOGIT,
    file_path=CFG_SETTINGS)
add("open: unreadable input", "allow", raw="not json at all")
add("open: a payload that is not an object", "allow", raw="[1, 2, 3]")
add("open: a bare number on stdin", "allow", raw="42")
add("open: an empty stdin", "allow", raw="")
add("open: an object with no keys at all", "allow", raw="{}")
add("open: a tool_input that is not an object", "allow", raw='{"tool_name":"Bash","tool_input":3}')


# --------------------------------------------------------------------------- the runner


def decide(case):
    """Return (decision, reason) for one case."""
    if case["raw"] is not None:
        payload = case["raw"]
    else:
        body = {"tool_name": case["tool"], "tool_input": dict(case["tool_input"])}
        if case["cwd"]:
            body["cwd"] = case["cwd"]
        payload = json.dumps(body)
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = CFG
    if case["env_path"]:
        env["PATH"] = case["env_path"]
    result = subprocess.run(
        [sys.executable, GUARD], input=payload, capture_output=True, text=True, env=env,
        timeout=120,
    )
    if result.returncode != 0:
        return "error", "exit %d: %s" % (result.returncode, result.stderr.strip()[:200])
    out = result.stdout.strip()
    if not out:
        return "allow", ""
    try:
        parsed = json.loads(out)
        block = parsed["hookSpecificOutput"]
        return block["permissionDecision"], block["permissionDecisionReason"]
    except Exception:
        return "unparsable", out[:200]


def log_case():
    """One deny writes one log line, and one allow writes none.

    It uses a config directory of its own, so the count is not the whole run's count.
    """
    path = os.path.join(LOGDIR, "guard.log")
    if os.path.exists(path):
        os.remove(path)
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = LOGDIR
    for command in ("pkill -f node", VCS + " status"):
        subprocess.run(
            [sys.executable, GUARD],
            input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command},
                              "cwd": NOGIT}),
            capture_output=True, text=True, env=env, timeout=60,
        )
    if not os.path.exists(path):
        return False, "no log file was written for the refusal"
    with open(path, encoding="utf-8") as handle:
        lines = [line for line in handle.read().splitlines() if line.strip()]
    if len(lines) != 1:
        return False, "expected one line, found %d" % len(lines)
    fields = lines[0].split("\t")
    if len(fields) != 5:
        return False, "expected five tab-separated fields, found %d" % len(fields)
    if fields[2] != "deny" or fields[3] != "machine-wide-kill":
        return False, "the line names %r and %r" % (fields[2], fields[3])
    return True, "one line, and nothing for the allow"


def config_edit_log_case():
    """Decision 7: a project config edit is allowed, and logged as `noted`/`config-edit`.

    Three calls that each touch a project's own `.claude` config: an Edit of its settings.json,
    an Edit of a hook under `.claude/hooks/`, and a Bash append onto its settings.json. Each must
    print nothing (a silent allow) and each must add one `noted`/`config-edit` line to the log.
    """
    folder = os.path.join(ROOT, "cfglog")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "guard.log")
    if os.path.exists(path):
        os.remove(path)
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = folder
    calls = [
        {"tool_name": "Edit", "tool_input": {"file_path": PROJ_SETTINGS}, "cwd": NOGIT},
        {"tool_name": "Edit", "tool_input": {"file_path": PROJ_HOOK}, "cwd": NOGIT},
        {"tool_name": "Bash", "tool_input": {"command": "echo x >> " + PROJ_SETTINGS},
         "cwd": NOGIT},
    ]
    for payload in calls:
        result = subprocess.run(
            [sys.executable, GUARD], input=json.dumps(payload), capture_output=True, text=True,
            env=env, timeout=60,
        )
        if result.returncode != 0:
            return False, "guard exited %d" % result.returncode
        if result.stdout.strip():
            return False, "expected a silent allow, got %r" % result.stdout.strip()[:120]
    if not os.path.exists(path):
        return False, "no log file was written for the noted edits"
    with open(path, encoding="utf-8") as handle:
        lines = [line for line in handle.read().splitlines() if line.strip()]
    if len(lines) != 3:
        return False, "expected three lines, found %d" % len(lines)
    for line in lines:
        fields = line.split("\t")
        if len(fields) != 5 or fields[2] != "noted" or fields[3] != "config-edit":
            return False, "line does not read noted/config-edit: %r" % line
    return True, "three noted lines, one per config edit"


def conflict_resolve_log_case():
    """`git checkout --theirs` during a real conflict is allowed, and logged as
    `noted`/`conflict-resolve`, the same shape as the other allow-and-log rules.
    """
    folder = os.path.join(ROOT, "conflictlog")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "guard.log")
    if os.path.exists(path):
        os.remove(path)
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = folder
    result = subprocess.run(
        [sys.executable, GUARD],
        input=json.dumps({"tool_name": "Bash",
                          "tool_input": {"command": VCS + " checkout --theirs docs/DEBTS.md"},
                          "cwd": CONFLICT}),
        capture_output=True, text=True, env=env, timeout=60,
    )
    if result.stdout.strip():
        return False, "expected a silent allow, got %r" % result.stdout.strip()[:120]
    if not os.path.exists(path):
        return False, "no log file was written for the noted resolve"
    with open(path, encoding="utf-8") as handle:
        lines = [line for line in handle.read().splitlines() if line.strip()]
    if len(lines) != 1:
        return False, "expected one line, found %d" % len(lines)
    fields = lines[0].split("\t")
    if len(fields) != 5 or fields[2] != "noted" or fields[3] != "conflict-resolve":
        return False, "line does not read noted/conflict-resolve: %r" % lines[0]
    return True, "one noted/conflict-resolve line"


# --------------------------------------------------------------------------- the reason hygiene
#
# CLAUDE.md: "A refusal's printed remedy never names the forbidden target." The WHOLE printed
# reason is covered, not its last sentence, so no refusal may carry the file it refused. This is
# checked on every refused case rather than on a few, because one interpolated name is the whole
# defect and it can enter through any rule.
FORBIDDEN_IN_A_REASON = (ENV, ROOT, slash(ROOT), "settings.json", "CLAUDE.md", "guard.py",
                         ".claude", "app.log", "sleep")


def merge_log_case():
    """Decision 8: a merge into main is allowed, and noted in the log when the base is main or
    unreadable, or when the call goes through the MCP tool that carries no base at all. A base of
    dev is allowed and logs nothing.
    """
    scenarios = [
        ("gh pr merge 12", GHMAIN, True, "base main"),
        ("gh pr merge 12", GHDEV, False, "base dev"),
        ("gh pr merge 12", GHNONE, True, "base unreadable"),
    ]
    problems = []
    for index, (command, ghdir, expect_logged, label) in enumerate(scenarios):
        folder = os.path.join(ROOT, "mlog%d" % index)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "guard.log")
        env = dict(os.environ)
        env["CLAUDE_CONFIG_DIR"] = folder
        env["PATH"] = ghdir + os.pathsep + PY_PATH
        result = subprocess.run(
            [sys.executable, GUARD],
            input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command},
                              "cwd": NOGIT}),
            capture_output=True, text=True, env=env, timeout=60,
        )
        if result.stdout.strip():
            problems.append("%s: expected a silent allow, got %r" % (
                label, result.stdout.strip()[:80]))
            continue
        logged = False
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                logged = any(
                    line.split("\t")[2:4] == ["noted", "merge-main"]
                    for line in handle.read().splitlines() if line.strip()
                )
        if logged != expect_logged:
            problems.append("%s: expected logged=%s, got %s" % (label, expect_logged, logged))

    folder = os.path.join(ROOT, "mlogtool")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "guard.log")
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = folder
    result = subprocess.run(
        [sys.executable, GUARD],
        input=json.dumps({"tool_name": "mcp__github__merge_pull_request",
                          "tool_input": {"pullNumber": 12, "repo": "x", "owner": "y"},
                          "cwd": NOGIT}),
        capture_output=True, text=True, env=env, timeout=60,
    )
    if result.stdout.strip():
        problems.append("merge tool: expected a silent allow, got %r" % (
            result.stdout.strip()[:80]))
    elif not os.path.exists(path):
        problems.append("merge tool: no log file was written")
    else:
        with open(path, encoding="utf-8") as handle:
            logged = any(
                line.split("\t")[2:4] == ["noted", "merge-main"]
                for line in handle.read().splitlines() if line.strip()
            )
        if not logged:
            problems.append("merge tool: log line does not read noted/merge-main")

    if problems:
        return False, "; ".join(problems)
    return True, "allow in all four cases, noted where the base is unsafe or unread"


def names_the_target(reason):
    """Return the first forbidden fragment the printed reason carries, else ''."""
    for fragment in FORBIDDEN_IN_A_REASON:
        if fragment and fragment in reason:
            return fragment
    return ""


def log_env_case():
    """A refused environment file reaches the log, although it never reaches the reason.

    The reason is generic on purpose, so the log is the only place a person can still read WHICH
    file fired. A guard that hid both would refuse and explain nothing.
    """
    folder = os.path.join(ROOT, "envlog")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "guard.log")
    if os.path.exists(path):
        os.remove(path)
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = folder
    result = subprocess.run(
        [sys.executable, GUARD],
        input=json.dumps({"tool_name": "Read",
                          "tool_input": {"file_path": "C:/repo/" + ENV},
                          "cwd": "C:/repo"}),
        capture_output=True, text=True, env=env, timeout=60,
    )
    if ENV in result.stdout:
        return False, "the printed output names the file"
    if not os.path.exists(path):
        return False, "no log file was written"
    with open(path, encoding="utf-8") as handle:
        lines = [line for line in handle.read().splitlines() if line.strip()]
    if len(lines) != 1 or ENV not in lines[0].split("\t")[-1]:
        return False, "the log line does not carry the path"
    return True, "generic on stdout, named in the log"


def main():
    total = len(CASES) + 5
    print("guard cases, %d in all" % total)
    print("fixtures under " + ROOT)
    print()
    failed = 0
    for case in CASES:
        got, reason = decide(case)
        ok = got == case["expected"]
        note = ""
        if ok and case["rule"] and case["rule"] not in reason:
            ok = False
            note = "  (the reason does not name rule %r: %s)" % (case["rule"], reason[:90])
        elif ok and got != "allow" and names_the_target(reason):
            ok = False
            note = "  (the reason names the forbidden target %r)" % names_the_target(reason)
        elif not ok:
            note = "  (%s)" % reason[:110] if reason else ""
        failed += 0 if ok else 1
        print("%s  %-6s(want %-6s)  [%-11s] %s%s" % (
            "PASS" if ok else "FAIL", got, case["expected"], case["tool"], case["name"], note))
    for label, checker in (
        ("log: one line per refusal and none for an allow", log_case),
        ("log: the refused file is named in the log and nowhere else", log_env_case),
        ("log: a project config edit is allowed and noted", config_edit_log_case),
        ("log: a merge into main is allowed and noted where the base is unsafe", merge_log_case),
        ("log: a conflict-side checkout is allowed and noted", conflict_resolve_log_case),
    ):
        ok, note = checker()
        failed += 0 if ok else 1
        print("%s  %-6s(want %-6s)  [%-11s] %s  (%s)" % (
            "PASS" if ok else "FAIL", "logged" if ok else "wrong", "logged", "Bash", label, note))
    print()
    shutil.rmtree(ROOT, ignore_errors=True)
    if failed:
        print("test_guard FAIL: %d of %d cases wrong" % (failed, total))
        return 1
    print("test_guard PASS: %d of %d cases right" % (total, total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
