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
import time

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
        session=None, carries=(), config=None, **tool_input):
    """Register one case.

    `carries` names fragments the printed reason MUST hold, which is how a case pins what an
    approver reads, not only the decision.

    A case NEVER opts out of the generic-reason check. Which fragments a reason may name is read
    from the case's RULE, through `REASON_MAY_NAME` below, so the exemption belongs to one rule and
    no case can widen it by itself.
    """
    CASES.append({
        "name": name,
        "expected": expected,
        "rule": rule,
        "raw": raw,
        "tool": tool,
        "cwd": cwd,
        "env_path": env_path,
        "session": session,
        "carries": (carries,) if isinstance(carries, str) else tuple(carries),
        # The config directory the case runs against. It decides where the global rules file is
        # read from, so a pointer case names its own and every other case keeps the default.
        "config": config,
        "tool_input": tool_input,
    })


def sh(name, command, expected, rule=None, tool="Bash", cwd=None, env_path=None, session=None,
       carries=(), config=None):
    add(name, expected, rule=rule, tool=tool, cwd=cwd, env_path=env_path, session=session,
        carries=carries, config=config, command=command)


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
SUBJCLEAN = os.path.join(ROOT, "subjclean")  # a real checkout with a clean tree and no stash
SUBJCLEANWT = os.path.join(ROOT, "subjcleanlane")  # a real, clean linked worktree of that one
SUBJDIRTY = os.path.join(ROOT, "subjdirty")  # a real checkout with real uncommitted work
SUBJSTASH = os.path.join(ROOT, "subjstash")  # a clean tree carrying one real stash entry
SUBJSTASHWT = os.path.join(ROOT, "subjstashlane")  # a linked worktree of it: same stack
GITBLIND = os.path.join(ROOT, "gitblind")  # a git that answers the repo test and no status read
# A repository under a scratchpad named after one session. ROOT already sits under the system
# temporary directory, which is the other half of the path test.
FAKE_SESSION = "5b9f6a3d-0000-4000-8000-000000000000"
OTHER_SESSION = "0000ffff-0000-4000-8000-000000000000"
PRIVREPO = os.path.join(ROOT, FAKE_SESSION, "scratchpad", "priv")
GHMAIN = os.path.join(ROOT, "ghmain")      # a fake command line tool answering "main"
GHDEV = os.path.join(ROOT, "ghdev")        # the same, answering "dev"
GHNONE = os.path.join(ROOT, "ghnone")      # an empty directory, so the tool is missing
# THE POINTER CHECKOUT. `PTRCFG` is a config directory whose global rules file points at
# `PTRMAIN`, which stands in for the machine's primary checkout: the one every session runs its
# hooks and its lint from. `PTRWT` is a real linked worktree of it, which must stay allowed.
# `PTRBADCFG` and `PTRGONECFG` are the two fail-open shapes, and `PTRNOCFG` holds no rules file.
PTRCFG = os.path.join(ROOT, "ptrcfg")
PTRMAIN = os.path.join(ROOT, "ptrmain")
PTRWT = os.path.join(ROOT, "ptrlane")
PTRBADCFG = os.path.join(ROOT, "ptrbadcfg")
PTRGONECFG = os.path.join(ROOT, "ptrgonecfg")
PTRNOCFG = os.path.join(ROOT, "ptrnocfg")

# --------------------------------------------------------------- branch delete / worktree fixtures
#
# BRANCHREMOTE stands in for a remote: a bare clone BRANCHREPO pushes to, so `git for-each-ref
# --contains` has a real remote-tracking ref to answer against. BRANCHREPO carries a real
# `origin/HEAD`, so its cases prove the FIRST base in the resolve order. BRANCHFALLBACKMAIN and
# BRANCHFALLBACKMASTER carry no remote at all, so their one case each proves the second and third
# steps of that same order. BRANCHNOBASE answers none of the three, so its case proves the
# unreadable arm.
BRANCHREMOTE = os.path.join(ROOT, "branchremote.git")
BRANCHREPO = os.path.join(ROOT, "branchrepo")
BRANCHFALLBACKMAIN = os.path.join(ROOT, "branchfallbackmain")
BRANCHFALLBACKMASTER = os.path.join(ROOT, "branchfallbackmaster")
BRANCHNOBASE = os.path.join(ROOT, "branchnobase")

# WTMAIN is the primary checkout of its own small repository. Every linked worktree below is a
# real one, because the rule reads `git worktree list --porcelain` and `git status --porcelain`
# with git itself, never a guess from a path. WTPRUNE is a SEPARATE repository, so pruning it
# never touches WTMAIN's own registrations.
WTMAIN = os.path.join(ROOT, "wtmain")
WTCLEAN = os.path.join(ROOT, "wtclean")
WTDIRTY = os.path.join(ROOT, "wtdirtylane")
WTLOCKED = os.path.join(ROOT, "wtlocked")
WTLIVE = os.path.join(ROOT, "wtlive")
WTDEADSESSION = os.path.join(ROOT, "wtdeadsession")
WTSTALESTART = os.path.join(ROOT, "wtstalestart")
WTPRUNE = os.path.join(ROOT, "wtprune")
WTPRUNESTALE = os.path.join(ROOT, "wtprunestale")

# Each of these is a config directory whose `sessions/` folder holds one record, read through
# `CLAUDE_CONFIG_DIR` exactly as the live sessions folder would be. A record is built against a
# REAL process (this test runner's own pid), read back with `ps` the same way the guard itself
# reads it, so the fixture cannot drift from what the guard actually measures.
WTLIVECFG = os.path.join(ROOT, "wtlivecfg")
WTDEADCFG = os.path.join(ROOT, "wtdeadcfg")
WTSTALESTARTCFG = os.path.join(ROOT, "wtstalestartcfg")


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


IDENT = ["-c", "user.email=cases@example.invalid", "-c", "user.name=cases"]


def _porcelain(where):
    """Return the lines of `git status --porcelain`, the same read the guard makes."""
    status = run_vcs(where, "status", "--porcelain")
    if status.returncode != 0:
        sys.exit(
            "fixture setup failed in build_fixtures: git status --porcelain failed in %r. "
            "stderr: %s" % (where, status.stderr.strip())
        )
    return [line for line in status.stdout.splitlines() if line.strip()]


def _require_clean(where):
    """Stop the suite unless `where` really has an empty working-tree subject.

    The empty-subject cases below prove that an empty subject PASSES. A fixture that is quietly
    dirty would pass them for the wrong reason, the PR #30 defect: a fixture whose setup never
    ran and whose case therefore proved nothing.
    """
    lines = _porcelain(where)
    if lines:
        sys.exit(
            "fixture setup failed in build_fixtures: %r was built to be clean, and git status "
            "--porcelain shows: %r" % (where, lines)
        )


def _require_dirty(where, tracked, untracked, clean_path):
    """Stop the suite unless `where` really holds a modified tracked file, a real untracked file,
    and one tracked path that is NOT in the status output.

    The non-empty cases below prove that a non-empty subject is still refused, and the per-path
    cases prove that a clean path inside a dirty tree passes. Both need each of the three to be
    real, so each one is read back with git itself.
    """
    lines = _porcelain(where)
    if not any(line[1:].strip().endswith(tracked) and line[:2].strip() == "M" for line in lines):
        sys.exit(
            "fixture setup failed in build_fixtures: %r is not modified in %r. git status "
            "--porcelain shows: %r" % (tracked, where, lines)
        )
    if not any(line[:2] == "??" and line[3:].strip().endswith(untracked) for line in lines):
        sys.exit(
            "fixture setup failed in build_fixtures: %r is not untracked in %r. git status "
            "--porcelain shows: %r" % (untracked, where, lines)
        )
    if any(clean_path in line for line in lines):
        sys.exit(
            "fixture setup failed in build_fixtures: %r was built to be clean inside %r, and "
            "git status --porcelain shows it: %r" % (clean_path, where, lines)
        )
    scoped = run_vcs(where, "status", "--porcelain", "--", clean_path)
    if scoped.returncode != 0 or scoped.stdout.strip():
        sys.exit(
            "fixture setup failed in build_fixtures: the path-scoped read of %r in %r is not "
            "empty: exit %d, %r" % (clean_path, where, scoped.returncode, scoped.stdout)
        )


def _require_stash(where, count):
    """Stop the suite unless `where`'s stash stack really holds `count` entries.

    A fixture that claims a one-entry stack and holds none would make the `stash drop` case pass
    for the wrong reason. MEASURED lesson from CI: `git stash push` writes a commit, so it needs
    a git identity, and a runner has none unless the call carries one.
    """
    listing = run_vcs(where, "stash", "list")
    if listing.returncode != 0:
        sys.exit(
            "fixture setup failed in build_fixtures: git stash list failed in %r. stderr: %s"
            % (where, listing.stderr.strip())
        )
    lines = [line for line in listing.stdout.splitlines() if line.strip()]
    if len(lines) != count:
        sys.exit(
            "fixture setup failed in build_fixtures: %r was built with %d stash entries, and "
            "git stash list shows %d: %r" % (where, count, len(lines), lines)
        )


def _require_pointer_branch(where, branch):
    """Stop the suite unless `where` is really checked out on `branch`.

    The allowed case below is a move TO `main`, and the refused cases are moves away from it. A
    fixture sitting on some other branch would answer the same decisions for a reason the cases
    were not built to prove, so the branch is read back with git itself.
    """
    head = run_vcs(where, "rev-parse", "--abbrev-ref", "HEAD")
    if head.returncode != 0 or head.stdout.strip() != branch:
        sys.exit(
            "fixture setup failed in build_fixtures: %r was built on %r, and git answers %r. "
            "stderr: %s" % (where, branch, head.stdout.strip(), head.stderr.strip())
        )


def _real_process_start_ms(pid):
    """Return `pid`'s real start time in epoch milliseconds, read the same way the guard reads
    it: `ps -o lstart=` on POSIX, parsed with `time.mktime` as this machine's own local clock;
    `OpenProcess`/`GetProcessTimes` on Windows, called below when `sys.platform` says Windows.

    A session-liveness fixture built from ANY OTHER read (a rendered string compared by eye, a
    guessed offset) could drift from what `hooks/guard.py` itself computes and pass or fail the
    live-session cases for the wrong reason. This is a second, independent implementation of the
    same read, not a call into the guard's own function, so a fixture and the code it proves
    cannot share one bug. That holds on Windows too: the arm below copies guard.py's own
    `_process_start_ms_windows` logic rather than calling it.
    """
    if sys.platform.startswith("win"):
        import ctypes
        import ctypes.wintypes

        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            sys.exit(
                "fixture setup failed in build_fixtures: OpenProcess(%d) answered no handle. "
                "GetLastError: %d" % (pid, ctypes.GetLastError())
            )
        try:
            creation = ctypes.wintypes.FILETIME()
            exit_time = ctypes.wintypes.FILETIME()
            kernel_time = ctypes.wintypes.FILETIME()
            user_time = ctypes.wintypes.FILETIME()
            ok = kernel32.GetProcessTimes(
                handle, ctypes.byref(creation), ctypes.byref(exit_time),
                ctypes.byref(kernel_time), ctypes.byref(user_time),
            )
            if not ok:
                sys.exit(
                    "fixture setup failed in build_fixtures: GetProcessTimes(%d) failed." % pid
                )
            value = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
            return value // 10000 - 11644473600000
        finally:
            kernel32.CloseHandle(handle)
    result = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)],
                             capture_output=True, text=True, timeout=5)
    text = result.stdout.strip()
    if result.returncode != 0 or not text:
        sys.exit(
            "fixture setup failed in build_fixtures: `ps -o lstart= -p %d` answered nothing. "
            "stderr: %s" % (pid, result.stderr.strip())
        )
    parsed = time.strptime(text, "%a %b %d %H:%M:%S %Y")
    return int(time.mktime(parsed) * 1000)


def make_repo(where, files):
    """Build a real checkout holding `files`, committed, with an explicit identity."""
    os.makedirs(where, exist_ok=True)
    run_vcs(where, "init", "-q", "-b", "main", ".")
    for name, text in files.items():
        write(os.path.join(where, name), text)
    run_vcs(where, "add", "-A")
    commit = run_vcs(where, *IDENT, "commit", "-q", "-m", "first")
    if commit.returncode != 0:
        sys.exit(
            "fixture setup failed in build_fixtures: the first commit in %r failed. stderr: %s"
            % (where, commit.stderr.strip())
        )


def make_blind_git(folder):
    """Put a `git` on PATH that answers the repository test and NO status read.

    The unreadable-subject arm needs git to fail to ANSWER, which is not the same as a directory
    that is no git tree. A real repository is still the cwd; only the program answering is blind,
    so the case drives the guard's own "I could not read this" path rather than a mock of it.

    MEASURED on Windows 2026-09-16, recorded in `make_fake_gh` below: a call through
    CreateProcess appends `.exe` and never reads PATHEXT, so a `git.cmd` stand-in would be
    skipped there and the case would answer for the wrong reason. The unreadable-subject cases
    are therefore SKIPPED on Windows rather than run against a stand-in that never answers.
    """
    os.makedirs(folder, exist_ok=True)
    script = os.path.join(folder, "git")
    write(script, "#!/bin/sh\n"
                  "for arg in \"$@\"; do\n"
                  "  if [ \"$arg\" = \"--is-inside-work-tree\" ]; then echo true; exit 0; fi\n"
                  "done\n"
                  "echo 'blind git: no answer' >&2\n"
                  "exit 128\n")
    os.chmod(script, 0o755)


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
    #
    # BOTH TREES CARRY REAL UNCOMMITTED WORK. The four worktree cases below are about the
    # deny-or-ask SPLIT, and the rule now reads the subject first, so a clean tree there would
    # pass on the empty subject and prove nothing about the split. That is the PR #30 defect in
    # its general form: a fixture that passes for a reason it was not built to test.
    run_vcs(GITMAIN, "init", "-q", "-b", "main", ".")
    run_vcs(GITMAIN, *IDENT, "commit", "-q", "--allow-empty", "-m", "first")
    write(os.path.join(GITMAIN, "docs", "DEBTS.md"), "base\n")
    write(os.path.join(GITMAIN, "f.txt"), "base\n")
    write(os.path.join(GITMAIN, "keep.txt"), "base\n")
    run_vcs(GITMAIN, "add", "-A")
    run_vcs(GITMAIN, *IDENT, "commit", "-q", "-m", "files")
    run_vcs(GITMAIN, "worktree", "add", "-q", GITWT, "-b", "lane")
    for _tree in (GITMAIN, GITWT):
        write(os.path.join(_tree, "docs", "DEBTS.md"), "uncommitted\n")
        write(os.path.join(_tree, "f.txt"), "uncommitted\n")
        write(os.path.join(_tree, "new.txt"), "untracked\n")
        _require_dirty(_tree, "f.txt", "new.txt", "keep.txt")

    # THE SUBJECT READ. Each arm gets both sides, built with real state: a real clean tree, a
    # real uncommitted edit, a real untracked file, a real one-entry stash stack.
    make_repo(SUBJCLEAN, {"f.txt": "base\n", "keep.txt": "base\n"})
    _require_clean(SUBJCLEAN)
    _require_stash(SUBJCLEAN, 0)
    # A CLEAN worktree of that clean checkout. The narrowed `reset --hard` arm keeps the
    # deny-or-ask split for a named commit, and the ask half of that split can only be shown in a
    # real linked worktree whose tree is also clean.
    run_vcs(SUBJCLEAN, "worktree", "add", "-q", SUBJCLEANWT, "-b", "subjlane")
    _require_clean(SUBJCLEANWT)

    make_repo(SUBJDIRTY, {"f.txt": "base\n", "keep.txt": "base\n"})
    write(os.path.join(SUBJDIRTY, "f.txt"), "uncommitted\n")
    write(os.path.join(SUBJDIRTY, "new.txt"), "untracked\n")
    _require_dirty(SUBJDIRTY, "f.txt", "new.txt", "keep.txt")
    _require_stash(SUBJDIRTY, 0)

    # One real stash entry over a CLEAN tree, so the `stash drop` cases prove the guard reads the
    # STACK and not the tree. The push carries the identity, because a stash writes a commit.
    make_repo(SUBJSTASH, {"f.txt": "base\n"})
    write(os.path.join(SUBJSTASH, "f.txt"), "to be stashed\n")
    run_vcs(SUBJSTASH, *IDENT, "stash", "push", "-m", "cases")
    _require_stash(SUBJSTASH, 1)
    _require_clean(SUBJSTASH)
    # A linked worktree of that checkout. `refs/stash` lives in the common git directory, so the
    # worktree sees the same one-entry stack, and a drop there destroys the primary's entry.
    run_vcs(SUBJSTASH, "worktree", "add", "-q", SUBJSTASHWT, "-b", "stashlane")
    _require_stash(SUBJSTASHWT, 1)

    # A dirty repository under a scratchpad named after one session.
    make_repo(PRIVREPO, {"f.txt": "base\n", "keep.txt": "base\n"})
    write(os.path.join(PRIVREPO, "f.txt"), "uncommitted\n")
    write(os.path.join(PRIVREPO, "new.txt"), "untracked\n")
    _require_dirty(PRIVREPO, "f.txt", "new.txt", "keep.txt")

    # THE POINTER CHECKOUT, built with git itself. The rule compares TOP LEVELS read from git, so
    # no fake directory will do, and the worktree that must stay allowed has to be a real one.
    #
    # PTRMAIN CARRIES REAL UNCOMMITTED WORK on `f.txt`, and `keep.txt` is really clean inside it.
    # The path-operation cases are what prove rule 1 still governs `checkout -- <path>` in this
    # checkout, unchanged, and both of rule 1's answers need real state to come out of.
    # `docs/note.md` exists so that the subdirectory case below runs in a real directory. A `cd`
    # into a directory that is not there would answer "allow" for the wrong reason.
    make_repo(PTRMAIN, {"f.txt": "base\n", "keep.txt": "base\n", "docs/note.md": "base\n"})
    write(os.path.join(PTRMAIN, "f.txt"), "uncommitted\n")
    write(os.path.join(PTRMAIN, "new.txt"), "untracked\n")
    _require_dirty(PTRMAIN, "f.txt", "new.txt", "keep.txt")
    run_vcs(PTRMAIN, "worktree", "add", "-q", PTRWT, "-b", "ptrlane")
    _require_clean(PTRWT)
    _require_pointer_branch(PTRMAIN, "main")
    # The pointer line has the same shape the installer writes and the shell readers parse.
    write(os.path.join(PTRCFG, "CLAUDE.md"), "@" + slash(PTRMAIN) + "/CLAUDE.md\n")
    write(os.path.join(PTRBADCFG, "CLAUDE.md"), "rules with no pointer line\n")
    write(os.path.join(PTRGONECFG, "CLAUDE.md"),
          "@" + slash(os.path.join(ROOT, "nosuchcheckout")) + "/CLAUDE.md\n")
    os.makedirs(PTRNOCFG, exist_ok=True)

    make_blind_git(GITBLIND)

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

    # ----------------------------------------------------------------- branch delete fixtures
    #
    # BRANCHREPO pushes to a real bare remote, so `git cherry` and `git for-each-ref --contains`
    # both read REAL history, never a guess. The shape below builds four branches off one
    # history so each of the rule's three tests gets a branch only IT would pass:
    #
    #   ancestor-work   never moves past the first commit: trivially an ancestor of `origin/main`.
    #   rebased-work    carries a commit whose PATCH main also carries, under a different commit
    #                   id, so only `git cherry` (not ancestry) proves it is redundant.
    #   unmerged-work   carries a commit found nowhere else at all: the only-copy case.
    #   pushed-work     carries a commit AS unique as unmerged-work's, but pushed to the remote,
    #                   so only the remote-contains test proves it is safe to delete.
    os.makedirs(BRANCHREMOTE, exist_ok=True)
    run_vcs(BRANCHREMOTE, "init", "-q", "--bare")
    make_repo(BRANCHREPO, {"base.txt": "base\n"})
    run_vcs(BRANCHREPO, "remote", "add", "origin", slash(BRANCHREMOTE))
    push = run_vcs(BRANCHREPO, "push", "-q", "origin", "main")
    if push.returncode != 0:
        sys.exit("fixture setup failed in build_fixtures: pushing BRANCHREPO's main failed. "
                  "stderr: %s" % push.stderr.strip())
    run_vcs(BRANCHREPO, "remote", "set-head", "origin", "main")
    run_vcs(BRANCHREPO, "checkout", "-q", "-b", "ancestor-work")
    run_vcs(BRANCHREPO, "checkout", "-q", "main")
    run_vcs(BRANCHREPO, "checkout", "-q", "-b", "rebased-work")
    write(os.path.join(BRANCHREPO, "r.txt"), "same patch\n")
    run_vcs(BRANCHREPO, "add", "r.txt")
    run_vcs(BRANCHREPO, *IDENT, "commit", "-q", "-m", "add r.txt on rebased-work")
    run_vcs(BRANCHREPO, "checkout", "-q", "main")
    write(os.path.join(BRANCHREPO, "r.txt"), "same patch\n")  # identical content, own commit
    run_vcs(BRANCHREPO, "add", "r.txt")
    run_vcs(BRANCHREPO, *IDENT, "commit", "-q", "-m", "add r.txt directly on main")
    run_vcs(BRANCHREPO, "checkout", "-q", "-b", "unmerged-work")
    write(os.path.join(BRANCHREPO, "u.txt"), "found nowhere else\n")
    run_vcs(BRANCHREPO, "add", "u.txt")
    run_vcs(BRANCHREPO, *IDENT, "commit", "-q", "-m", "unmerged-work's only copy")
    run_vcs(BRANCHREPO, "checkout", "-q", "main")
    run_vcs(BRANCHREPO, "checkout", "-q", "-b", "pushed-work")
    write(os.path.join(BRANCHREPO, "p.txt"), "pushed to the remote\n")
    run_vcs(BRANCHREPO, "add", "p.txt")
    run_vcs(BRANCHREPO, *IDENT, "commit", "-q", "-m", "pushed-work's commit")
    pushb = run_vcs(BRANCHREPO, "push", "-q", "origin", "pushed-work")
    if pushb.returncode != 0:
        sys.exit("fixture setup failed in build_fixtures: pushing pushed-work failed. "
                  "stderr: %s" % pushb.stderr.strip())
    run_vcs(BRANCHREPO, "checkout", "-q", "main")
    pushm = run_vcs(BRANCHREPO, "push", "-q", "origin", "main")
    if pushm.returncode != 0:
        sys.exit("fixture setup failed in build_fixtures: re-pushing main failed. "
                  "stderr: %s" % pushm.stderr.strip())
    fetch = run_vcs(BRANCHREPO, "fetch", "-q", "origin")
    if fetch.returncode != 0:
        sys.exit("fixture setup failed in build_fixtures: fetching origin failed. "
                  "stderr: %s" % fetch.stderr.strip())
    base_check = run_vcs(BRANCHREPO, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
    if base_check.returncode != 0 or base_check.stdout.strip() != "origin/main":
        sys.exit(
            "fixture setup failed in build_fixtures: origin/HEAD in BRANCHREPO does not resolve "
            "to origin/main. git answers: %r, stderr: %s"
            % (base_check.stdout.strip(), base_check.stderr.strip())
        )
    cherry_check = run_vcs(BRANCHREPO, "cherry", "origin/main", "rebased-work")
    if any(line.startswith("+") for line in cherry_check.stdout.splitlines()):
        sys.exit(
            "fixture setup failed in build_fixtures: rebased-work still carries a `+` against "
            "origin/main, so it does not prove the patch-id test. git cherry says: %r"
            % cherry_check.stdout
        )

    # A fallback base with no remote at all: only local `main` answers, proving the SECOND step
    # of the resolve order (`origin/HEAD`, then local `main`, then local `master`).
    make_repo(BRANCHFALLBACKMAIN, {"base.txt": "base\n"})
    run_vcs(BRANCHFALLBACKMAIN, "checkout", "-q", "-b", "ancestor-fallback")
    run_vcs(BRANCHFALLBACKMAIN, "checkout", "-q", "main")
    # A branch that only a REAL fallback to local `main` can deny: if the fallback silently gave
    # up instead, the base would read as unreadable and this branch would wrongly pass.
    run_vcs(BRANCHFALLBACKMAIN, "checkout", "-q", "-b", "unmerged-fallback")
    write(os.path.join(BRANCHFALLBACKMAIN, "uf.txt"), "found nowhere else, no remote at all\n")
    run_vcs(BRANCHFALLBACKMAIN, "add", "uf.txt")
    run_vcs(BRANCHFALLBACKMAIN, *IDENT, "commit", "-q", "-m", "unmerged-fallback's only copy")
    run_vcs(BRANCHFALLBACKMAIN, "checkout", "-q", "main")

    # A fallback base with only local `master`, no `main` and no remote, proving the THIRD step.
    os.makedirs(BRANCHFALLBACKMASTER, exist_ok=True)
    run_vcs(BRANCHFALLBACKMASTER, "init", "-q", "-b", "master", ".")
    write(os.path.join(BRANCHFALLBACKMASTER, "base.txt"), "base\n")
    run_vcs(BRANCHFALLBACKMASTER, "add", "-A")
    run_vcs(BRANCHFALLBACKMASTER, *IDENT, "commit", "-q", "-m", "first")
    run_vcs(BRANCHFALLBACKMASTER, "checkout", "-q", "-b", "ancestor-fallback-master")
    run_vcs(BRANCHFALLBACKMASTER, "checkout", "-q", "master")
    run_vcs(BRANCHFALLBACKMASTER, "checkout", "-q", "-b", "unmerged-fallback-master")
    write(os.path.join(BRANCHFALLBACKMASTER, "uf.txt"), "found nowhere else, no remote at all\n")
    run_vcs(BRANCHFALLBACKMASTER, "add", "uf.txt")
    run_vcs(BRANCHFALLBACKMASTER, *IDENT, "commit", "-q", "-m",
            "unmerged-fallback-master's only copy")
    run_vcs(BRANCHFALLBACKMASTER, "checkout", "-q", "master")

    # No `origin/HEAD`, no local `main`, no local `master`: none of the three steps answers, so
    # the base is UNREADABLE and the delete must be allowed and logged, never denied and never
    # silently passed.
    os.makedirs(BRANCHNOBASE, exist_ok=True)
    run_vcs(BRANCHNOBASE, "init", "-q", "-b", "trunk", ".")
    write(os.path.join(BRANCHNOBASE, "base.txt"), "base\n")
    run_vcs(BRANCHNOBASE, "add", "-A")
    run_vcs(BRANCHNOBASE, *IDENT, "commit", "-q", "-m", "first")
    run_vcs(BRANCHNOBASE, "checkout", "-q", "-b", "orphan-work")
    write(os.path.join(BRANCHNOBASE, "o.txt"), "irrelevant to the unreadable case\n")
    run_vcs(BRANCHNOBASE, "add", "o.txt")
    run_vcs(BRANCHNOBASE, *IDENT, "commit", "-q", "-m", "orphan-work's commit")
    run_vcs(BRANCHNOBASE, "checkout", "-q", "trunk")
    base_check2 = run_vcs(BRANCHNOBASE, "rev-parse", "--verify", "-q", "refs/heads/main")
    if base_check2.returncode == 0:
        sys.exit("fixture setup failed in build_fixtures: BRANCHNOBASE unexpectedly has a "
                  "local main")

    # ----------------------------------------------------------------- worktree remove/prune
    #
    # WTMAIN carries real tracked files, the same `keep.txt`/`f.txt` shape SUBJDIRTY uses above,
    # so `_require_dirty` can prove WTDIRTY really is dirty and `keep.txt` really is clean.
    make_repo(WTMAIN, {"f.txt": "base\n", "keep.txt": "base\n"})
    run_vcs(WTMAIN, "worktree", "add", "-q", WTCLEAN, "-b", "wtclean-branch")
    _require_clean(WTCLEAN)
    run_vcs(WTMAIN, "worktree", "add", "-q", WTDIRTY, "-b", "wtdirty-branch")
    write(os.path.join(WTDIRTY, "f.txt"), "uncommitted\n")
    write(os.path.join(WTDIRTY, "new.txt"), "untracked\n")
    _require_dirty(WTDIRTY, "f.txt", "new.txt", "keep.txt")
    run_vcs(WTMAIN, "worktree", "add", "-q", WTLOCKED, "-b", "wtlocked-branch")
    _require_clean(WTLOCKED)
    lock = run_vcs(WTMAIN, "worktree", "lock", WTLOCKED, "--reason", "fixture")
    if lock.returncode != 0:
        sys.exit("fixture setup failed in build_fixtures: locking WTLOCKED failed. stderr: %s"
                  % lock.stderr.strip())
    lock_check = run_vcs(WTMAIN, "worktree", "list", "--porcelain")
    locked_ok = False
    for block in lock_check.stdout.split("\n\n"):
        lines = block.splitlines()
        if not lines or not lines[0].startswith("worktree "):
            continue
        path = lines[0][len("worktree "):].strip()
        if os.path.realpath(path) != os.path.realpath(WTLOCKED):
            continue
        locked_ok = any(line == "locked" or line.startswith("locked ") for line in lines[1:])
        break
    if not locked_ok:
        sys.exit(
            "fixture setup failed in build_fixtures: WTLOCKED is not registered as locked. "
            "git worktree list --porcelain says: %r" % lock_check.stdout
        )
    run_vcs(WTMAIN, "worktree", "add", "-q", WTLIVE, "-b", "wtlive-branch")
    _require_clean(WTLIVE)
    run_vcs(WTMAIN, "worktree", "add", "-q", WTDEADSESSION, "-b", "wtdead-branch")
    _require_clean(WTDEADSESSION)
    run_vcs(WTMAIN, "worktree", "add", "-q", WTSTALESTART, "-b", "wtstalestart-branch")
    _require_clean(WTSTALESTART)

    # A live session record, built against THIS TEST RUNNER'S OWN pid, which stays alive for the
    # whole run. `startedAt` is read with `_real_process_start_ms`, a second, independent
    # implementation of the same `ps`-plus-`mktime` read the guard makes, so the fixture cannot
    # share a bug with the code it proves.
    self_pid = os.getpid()
    self_start_ms = _real_process_start_ms(self_pid)
    os.makedirs(os.path.join(WTLIVECFG, "sessions"), exist_ok=True)
    write(
        os.path.join(WTLIVECFG, "sessions", "%d.json" % self_pid),
        json.dumps({"pid": self_pid, "cwd": slash(WTLIVE), "startedAt": self_start_ms}),
    )

    # A DEAD pid: a real short-lived process, started and waited on here, so its pid is not
    # running by the time any case reads it. The record still names the RIGHT start time for
    # that pid; only the process itself is gone, which is the exact case the plan names: "the
    # id is alive AND its recorded start time still matches".
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead_pid = dead.pid
    dead.wait(timeout=10)
    os.makedirs(os.path.join(WTDEADCFG, "sessions"), exist_ok=True)
    write(
        os.path.join(WTDEADCFG, "sessions", "%d.json" % dead_pid),
        json.dumps({"pid": dead_pid, "cwd": slash(WTDEADSESSION), "startedAt": 0}),
    )

    # A RECYCLED-PID shape: the pid IS alive (this runner, again) and the cwd sits inside the
    # target tree, but the recorded start time does not match the live process's real start
    # time. A pid can be reused by an unrelated process after the session that recorded it
    # exited, and this is exactly the claim that must not read as live.
    os.makedirs(os.path.join(WTSTALESTARTCFG, "sessions"), exist_ok=True)
    write(
        os.path.join(WTSTALESTARTCFG, "sessions", "%d.json" % self_pid),
        json.dumps({
            "pid": self_pid, "cwd": slash(WTSTALESTART), "startedAt": self_start_ms - 999999999,
        }),
    )

    # WTPRUNE is its own repository, so pruning it can never touch WTMAIN's own worktrees.
    # WTPRUNESTALE is added and then its directory is removed out from under git, the same shape
    # `is_worktree`'s own comment measures elsewhere in this file: a stale administrative record
    # with no directory behind it.
    make_repo(WTPRUNE, {"base.txt": "base\n"})
    run_vcs(WTPRUNE, "worktree", "add", "-q", WTPRUNESTALE, "-b", "wtprune-branch")
    shutil.rmtree(WTPRUNESTALE)
    prune_check = run_vcs(WTPRUNE, "worktree", "prune", "-n")
    if not (prune_check.stdout.strip() or prune_check.stderr.strip()):
        sys.exit(
            "fixture setup failed in build_fixtures: WTPRUNE has nothing to prune after "
            "WTPRUNESTALE's directory was removed. git answers stdout=%r stderr=%r"
            % (prune_check.stdout, prune_check.stderr)
        )
    prune_clean_check = run_vcs(WTMAIN, "worktree", "prune", "-n")
    if prune_clean_check.stdout.strip() or prune_clean_check.stderr.strip():
        sys.exit(
            "fixture setup failed in build_fixtures: WTMAIN unexpectedly has something to "
            "prune. git answers stdout=%r stderr=%r"
            % (prune_clean_check.stdout, prune_clean_check.stderr)
        )


build_fixtures()

CFG_SETTINGS = slash(os.path.join(CFG, "settings.json"))
CFG_CLAUDEMD = slash(os.path.join(CFG, "CLAUDE.md"))
CFG_HOOK = slash(os.path.join(CFG, "hooks", "guard.py"))
CFG_LINT = slash(os.path.join(CFG, "lint", "prose.py"))
CFG_AGENT = slash(os.path.join(CFG, "agents", "builder.md"))
# The baseline store `hooks/config_watch.py` restores from. A session that could rewrite the
# baseline could launder a cap lift into it, so it is frozen on the same terms as the hooks.
CFG_STATE = slash(os.path.join(CFG, "state", "config-watch", "entry.json"))
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
# `list` and `show` only read the stack, so they allow everywhere. Every other action takes an
# entry OFF the stack, and the stack belongs to the whole clone, so each one denies here. Owner's
# ruling, 2026-09-19: the old exemption for `apply` and `pop` read the wrong subject. Git does
# refuse to overwrite a modified file, which the old note MEASURED on 2026-09-17, but the thing
# at risk is the shared entry, not this tree.
sh("stash: list only reads, no subcommand match", VCS + " stash list", "allow", cwd=NOGIT)
sh("stash: show only reads", VCS + " stash show", "allow", cwd=NOGIT)
sh("stash: apply takes an entry off a stack the whole clone shares", VCS + " stash apply", "deny",
   "shared-tree", cwd=NOGIT)
sh("stash: pop consumes the entry it applies", VCS + " stash pop stash@{0}", "deny",
   "shared-tree", cwd=NOGIT)
sh("stash: branch consumes the entry it builds from", VCS + " stash branch lane", "deny",
   "shared-tree", cwd=NOGIT)
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
# GITMAIN carries a real uncommitted change to this same file, so the call has a subject to
# destroy and the case is still about the missing conflict, not about an empty tree.
sh("checkout: the same call with no conflict in progress keeps today's decision",
   VCS + " checkout --theirs docs/DEBTS.md", "deny", "shared-tree", cwd=GITMAIN)
sh("checkout: a path with no conflict-side flag still denies, even in the conflicted tree",
   VCS + " checkout -- docs/DEBTS.md", "deny", "shared-tree", cwd=CONFLICT)
sh("checkout: a branch and a path still denies, even in the conflicted tree",
   VCS + " checkout main -- docs/", "deny", "shared-tree", cwd=CONFLICT)

# THE SUBJECT READ, BOTH SIDES OF EVERY ARM. The rule reads what the call would TAKE, with the
# two reads git itself makes: `git status --porcelain` for a working-tree subject and `git stash
# list` for a stack subject. An empty subject passes, and a non-empty subject is refused exactly
# as before. Every fixture below is real state, asserted in build_fixtures: SUBJCLEAN is a clean
# tree with no stash, SUBJDIRTY holds a modified `f.txt`, an untracked `new.txt`, and a clean
# tracked `keep.txt`, and SUBJSTASH holds one stash entry over a clean tree.
sh("subject: a hard reset in a clean tree takes nothing", VCS + " reset --hard HEAD", "allow",
   cwd=SUBJCLEAN)
sh("subject: a hard reset over a real uncommitted change still denies", VCS + " reset --hard HEAD",
   "deny", "shared-tree", cwd=SUBJDIRTY)
sh("subject: a bare hard reset in a clean tree takes nothing", VCS + " reset --hard", "allow",
   cwd=SUBJCLEAN)
sh("subject: a bare hard reset in a clean worktree takes nothing", VCS + " reset --hard", "allow",
   cwd=SUBJCLEANWT)
sh("subject: a hard reset at HEAD in a clean worktree takes nothing",
   VCS + " reset --hard HEAD", "allow", cwd=SUBJCLEANWT)
# A `reset --hard` THAT NAMES ANOTHER COMMIT also moves the branch. Another session standing in
# that checkout is then on rewritten history, and the reflog that recovers the commit belongs to
# the tree that ran the reset, not to theirs. So a clean tree is NOT a pass for these forms, and
# the deny-or-ask split stays: deny in the shared checkout, ask in the worktree.
sh("subject: a hard reset one commit back moves the branch, clean tree or not",
   VCS + " reset --hard HEAD~1", "deny", "shared-tree", cwd=SUBJCLEAN)
sh("subject: the same reset in a clean worktree asks", VCS + " reset --hard HEAD~1", "ask",
   "shared-tree", cwd=SUBJCLEANWT)
sh("subject: a hard reset at a remote branch moves the branch", VCS + " reset --hard origin/main",
   "deny", "shared-tree", cwd=SUBJCLEAN)
sh("subject: a hard reset at a raw sha moves the branch",
   VCS + " reset --hard 380d5fca1b2c3d4e5f60718293a4b5c6d7e8f901", "deny", "shared-tree",
   cwd=SUBJCLEAN)
sh("subject: a hard reset at a raw sha in a clean worktree asks",
   VCS + " reset --hard 380d5fca1b2c3d4e5f60718293a4b5c6d7e8f901", "ask", "shared-tree",
   cwd=SUBJCLEANWT)
sh("subject: a quiet hard reset at HEAD is still a pass in a clean tree",
   VCS + " reset -q --hard HEAD", "allow", cwd=SUBJCLEAN)
sh("subject: setting aside a clean tree takes nothing", VCS + " stash push -u -m lane", "allow",
   cwd=SUBJCLEAN)
sh("subject: setting aside real uncommitted work still denies", VCS + " stash push -u -m lane",
   "deny", "shared-tree", cwd=SUBJDIRTY)
sh("subject: a bare stash over a clean tree takes nothing", VCS + " stash", "allow",
   cwd=SUBJCLEAN)
# THE STACK IS ITS OWN SUBJECT. Every action that takes an entry off the stack is read with `git
# stash list`, never with the tree. SUBJDIRTY is dirty and its stack is empty. SUBJSTASH is clean
# and its stack holds one entry. The two cases cross, which is what proves the right read is made.
#
# A CLEAN TREE IS NOT A PASS FOR THESE ARMS. MEASURED 2026-09-19 against the guard before this
# change: `git stash pop` allowed in a clean checkout holding a real entry, which is exactly the
# state in which taking another session's work leaves no trace. The SUBJSTASH rows below are that
# case, one per action.
sh("subject: dropping an empty stash stack destroys nothing", VCS + " stash drop", "allow",
   cwd=SUBJDIRTY)
sh("subject: dropping a real stash entry still denies", VCS + " stash drop", "deny",
   "shared-tree", cwd=SUBJSTASH)
sh("subject: dropping a real stash entry from a worktree still denies, the stack is clone-wide",
   VCS + " stash drop", "deny", "shared-tree", cwd=SUBJSTASHWT)
sh("subject: clearing an empty stash stack destroys nothing", VCS + " stash clear", "allow",
   cwd=SUBJDIRTY)
sh("subject: clearing a stack holding a real entry still denies", VCS + " stash clear", "deny",
   "shared-tree", cwd=SUBJSTASH)
sh("subject: popping an empty stash stack takes nothing", VCS + " stash pop", "allow",
   cwd=SUBJDIRTY)
sh("subject: popping a real entry from a CLEAN checkout still denies", VCS + " stash pop",
   "deny", "shared-tree", cwd=SUBJSTASH)
sh("subject: popping a real entry from a worktree still denies, the stack is clone-wide",
   VCS + " stash pop", "deny", "shared-tree", cwd=SUBJSTASHWT)
sh("subject: applying over an empty stash stack takes nothing", VCS + " stash apply", "allow",
   cwd=SUBJDIRTY)
sh("subject: applying a real entry from a CLEAN checkout still denies", VCS + " stash apply",
   "deny", "shared-tree", cwd=SUBJSTASH)
sh("subject: the named-entry apply is the same act", VCS + " stash apply stash@{0}", "deny",
   "shared-tree", cwd=SUBJSTASH)
sh("subject: branching off a real entry still denies", VCS + " stash branch lane", "deny",
   "shared-tree", cwd=SUBJSTASH)
sh("subject: branching off an empty stash stack takes nothing", VCS + " stash branch lane",
   "allow", cwd=SUBJDIRTY)
# THE TWO READS STAY ALLOWED where the stack really holds an entry, which is the only place the
# allow means anything.
sh("subject: list reads the stack that holds a real entry", VCS + " stash list", "allow",
   cwd=SUBJSTASH)
sh("subject: show reads the entry without taking it", VCS + " stash show stash@{0}", "allow",
   cwd=SUBJSTASH)
sh("subject: a hard reset in the tree that holds the stash takes nothing",
   VCS + " reset --hard HEAD", "allow", cwd=SUBJSTASH)
# `_run_dir` BYPASSES, found in review of the token-based rewrite. Both send the command's cwd
# to SUBJDIRTY (real, dirty) and name SUBJCLEAN (real, clean) as a directory the command text
# ATTACHES or MENTIONS, never one it actually runs in. The real subject stays SUBJDIRTY, so both
# still deny. MEASURED against the reviewed head: both wrongly read the subject as SUBJCLEAN and
# ALLOWED a real `reset --hard` over the dirty tree.
sh("run-dir bypass: an attached `-C<path>` is not a spelling git accepts, so it names no tree",
   VCS + " -C" + SUBJCLEAN + " status; " + VCS + " reset --hard HEAD",
   "deny", "shared-tree", cwd=SUBJDIRTY)
sh("run-dir bypass: a `cd` inside an interpreter heredoc body never moves the outer shell",
   "python3 <<'EOF'\ncd " + SUBJCLEAN + "\nprint('hi')\nEOF\n" + VCS + " reset --hard HEAD",
   "deny", "shared-tree", cwd=SUBJDIRTY)
# PER PATH for `restore` and `checkout <path>`: the pathspec goes to git, and an empty answer
# proves the write changes nothing. Both named paths sit in the SAME dirty tree.
sh("subject: restoring a clean path inside a dirty tree changes nothing",
   VCS + " restore keep.txt", "allow", cwd=SUBJDIRTY)
sh("subject: restoring the modified path still denies", VCS + " restore f.txt", "deny",
   "shared-tree", cwd=SUBJDIRTY)
sh("subject: restoring the whole clean tree changes nothing", VCS + " restore .", "allow",
   cwd=SUBJCLEAN)
sh("subject: checking out a clean path inside a dirty tree changes nothing",
   VCS + " checkout -- keep.txt", "allow", cwd=SUBJDIRTY)
sh("subject: checking out the modified path still denies", VCS + " checkout -- f.txt", "deny",
   "shared-tree", cwd=SUBJDIRTY)
sh("subject: a start point and a clean path change nothing",
   VCS + " checkout HEAD -- keep.txt", "allow", cwd=SUBJDIRTY)
sh("subject: a start point and the modified path still denies",
   VCS + " checkout HEAD -- f.txt", "deny", "shared-tree", cwd=SUBJDIRTY)
# `clean -f` deletes the UNTRACKED part of that same output, so that part is its subject.
sh("subject: a clean with no untracked file deletes nothing", VCS + " clean -fd", "allow",
   cwd=SUBJCLEAN)
sh("subject: a clean over a real untracked file still denies", VCS + " clean -fd", "deny",
   "shared-tree", cwd=SUBJDIRTY)
sh("subject: a clean scoped to a tracked path deletes nothing", VCS + " clean -fd keep.txt",
   "allow", cwd=SUBJDIRTY)
# `-e` carries a value. The value is NOT a pathspec, and reading it as one would narrow the read
# and let the delete of everything else pass on an empty answer.
sh("subject: an exclude pattern is not a pathspec", VCS + " clean -fd -e build", "deny",
   "shared-tree", cwd=SUBJDIRTY)
# THIS SESSION'S SCRATCHPAD, BY PATH. The same dirty repository answers three ways: private to
# the session the payload names, shared to any other session, and shared with no session at all.
add("scratchpad: a discard in this session's own scratchpad is private", "allow", cwd=PRIVREPO,
    session=FAKE_SESSION, command=VCS + " reset --hard HEAD")
add("scratchpad: another session's scratchpad is not this session's", "deny", "shared-tree",
    cwd=PRIVREPO, session=OTHER_SESSION, command=VCS + " reset --hard HEAD")
add("scratchpad: no session id names no scratchpad", "deny", "shared-tree", cwd=PRIVREPO,
    command=VCS + " reset --hard HEAD")
add("scratchpad: the same session id outside the scratchpad proves nothing", "deny",
    "shared-tree", cwd=SUBJDIRTY, session=FAKE_SESSION, command=VCS + " reset --hard HEAD")
# AN UNREADABLE SUBJECT IS ALLOWED, and logged under its own rule (checked in
# subject_unread_log_case). The cwd is the REAL dirty repository, so the only difference from the
# deny case above is that the git on PATH gives no answer.
if os.name != "nt":
    sh("subject: a git that cannot answer the status read allows, rather than guess",
       VCS + " reset --hard HEAD", "allow", cwd=SUBJDIRTY, env_path=GITBLIND)
    sh("subject: the same blind git on a stack subject allows", VCS + " stash drop", "allow",
       cwd=SUBJSTASH, env_path=GITBLIND)
# A DIRECTORY THAT IS NO GIT TREE IS NOT AN UNREADABLE SUBJECT. git answers there, and the answer
# is "no tree", so the rule keeps its fail-closed deny. Every NOGIT case above rests on this.
sh("subject: a directory that is no git tree still denies", VCS + " reset --hard HEAD", "deny",
   "shared-tree", cwd=NOGIT)

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
sh("worktree: restore of a dirty path still asks, unchanged", VCS + " restore f.txt", "ask",
   "shared-tree", cwd=GITWT)
sh("worktree: checkout -- of a dirty path still asks, unchanged", VCS + " checkout -- f.txt",
   "ask", "shared-tree", cwd=GITWT)

# THE PUSH ARM. `refs/stash` lives in the COMMON git directory (MEASURED above, next to
# SUBJSTASHWT), so a push from a worktree lands on the SAME one-entry-wide stack the primary
# checkout and every other lane share. The worktree "ask" that `reset --hard` and `restore` earn
# just above never applies to this arm: it is earned for a subject that lives in THIS tree
# alone, and a stash push's subject does not.
sh("worktree: a stash push in a dirty worktree denies, the stack is clone-wide",
   VCS + " stash push -u -m lane", "deny", "shared-tree", cwd=GITWT)
sh("worktree: a bare stash in a dirty worktree denies, the stack is clone-wide",
   VCS + " stash", "deny", "shared-tree", cwd=GITWT)
sh("worktree: stash save in a dirty worktree denies, the stack is clone-wide",
   VCS + " stash save lane", "deny", "shared-tree", cwd=GITWT)
sh("worktree: a stash push in the shared checkout still denies, unchanged",
   VCS + " stash push -u -m lane", "deny", "shared-tree", cwd=GITMAIN)

# THE TABLE'S ALLOW ROWS, checked in both a shared checkout and a worktree, so an allow is proven
# to hold regardless of which tree the call runs in — a read or a restore never needed the
# worktree/shared split, which the rows below confirm rather than assume.
for _tree_name, _tree_path in (("shared checkout", GITMAIN), ("worktree", GITWT)):
    sh("stash: list allows in the " + _tree_name, VCS + " stash list", "allow", cwd=_tree_path)
    sh("stash: show allows in the " + _tree_name, VCS + " stash show", "allow", cwd=_tree_path)
    sh("stash: apply over an empty stack allows in the " + _tree_name, VCS + " stash apply",
       "allow", cwd=_tree_path)
    sh("stash: pop over an empty stack allows in the " + _tree_name, VCS + " stash pop",
       "allow", cwd=_tree_path)
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
# follow, so it must not trip the live-stream rule either. Both stacks are empty, so the allow
# here proves the redirect and the pipe are read, not that the act is safe: the SUBJSTASH rows
# above hold the same command against a stack that really carries an entry.
sh("stash: the owner's exact apply command over an empty stack allows in the shared checkout",
   VCS + " stash apply stash@{0} 2>&1 | tail -10", "allow", cwd=GITMAIN)
sh("stash: the owner's exact apply command over an empty stack allows in a worktree",
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


# `--work-tree` NAMES THE TREE WHOSE FILES A CALL DISCARDS. MEASURED 2026-09-19 with real git:
# from a CLEAN checkout, `git --work-tree=<dirty> status --porcelain` reported the OTHER tree's
# modified and untracked files. So rule 1 judges the named tree, not the one the call runs in.
# BOTH DIRECTIONS: a clean cwd pointed at a dirty tree must deny, and a dirty cwd pointed at a
# clean tree must pass, or the option is only half read.
sh("work-tree: a clean cwd pointed at a dirty tree is judged on the dirty tree",
   VCS + " --work-tree=" + slash(SUBJDIRTY) + " reset --hard", "deny", "shared-tree",
   cwd=SUBJCLEAN)
sh("work-tree: a dirty cwd pointed at a clean tree passes on the empty subject",
   VCS + " --work-tree=" + slash(SUBJCLEAN) + " reset --hard", "allow", cwd=SUBJDIRTY)
sh("work-tree: the spaced form is read the same way",
   VCS + " --work-tree " + slash(SUBJDIRTY) + " reset --hard", "deny", "shared-tree",
   cwd=SUBJCLEAN)


# ============================================================ 1. branch delete / worktree remove/prune
#
# The three git forms the machine-wide janitor plan named as a hole in this rule: `git branch
# -d/-D`, `git worktree remove`, `git worktree prune`. Each is judged on the STATE OF ITS SUBJECT,
# the same shape every other arm of this rule already uses, never a name list.
#
# BOTH `-d` AND `-D` ARE READ THE SAME WAY. Neither creates, renames nor lists a branch, so a
# non-delete `git branch` call must keep allowing, unchanged.
sh("branch: a plain branch call only lists, no delete flag", VCS + " branch", "allow", cwd=NOGIT)
sh("branch: creating a branch is not a delete", VCS + " branch newname", "allow", cwd=NOGIT)
sh("branch: renaming a branch is not a delete", VCS + " branch -m old new", "allow", cwd=NOGIT)

# THE THREE TESTS THAT MAKE A BRANCH'S SUBJECT EMPTY, each proven with real history pushed to a
# real bare remote (BRANCHREPO), so `git cherry` and `git for-each-ref --contains` answer for
# real, never a mock.
sh("branch: an ancestor of origin/main deletes clean with -d",
   VCS + " branch -d ancestor-work", "allow", cwd=BRANCHREPO)
sh("branch: the same ancestor deletes clean with -D",
   VCS + " branch -D ancestor-work", "allow", cwd=BRANCHREPO)
sh("branch: a rebased commit's patch already sits on origin/main, cherry proves it",
   VCS + " branch -D rebased-work", "allow", cwd=BRANCHREPO)
sh("branch: a commit pushed to the remote is not the only copy",
   VCS + " branch -D pushed-work", "allow", cwd=BRANCHREPO)
# THE ONLY-COPY CASE. unmerged-work is not an ancestor, its patch is not on origin/main, and no
# remote ref contains it: this is the defect the plan measured against the live hook.
sh("branch: a commit found nowhere else is the only copy, and the rule denies",
   VCS + " branch -D unmerged-work", "deny", "shared-tree", cwd=BRANCHREPO)
sh("branch: -d over the same only-copy branch still denies",
   VCS + " branch -d unmerged-work", "deny", "shared-tree", cwd=BRANCHREPO)
# TWO NAMES IN ONE CALL. One safe and one unsafe name still denies: one held-only-copy makes the
# whole call's subject non-empty.
sh("branch: one safe name and one only-copy name in the same call still denies",
   VCS + " branch -D ancestor-work unmerged-work", "deny", "shared-tree", cwd=BRANCHREPO)

# THE RESOLVE ORDER'S OTHER TWO STEPS. BRANCHFALLBACKMAIN and BRANCHFALLBACKMASTER carry no
# remote at all, so each proves its own step answers when the step before it cannot.
sh("branch: local main answers when there is no origin/HEAD",
   VCS + " branch -D ancestor-fallback", "allow", cwd=BRANCHFALLBACKMAIN)
sh("branch: local master answers when there is no main and no origin/HEAD",
   VCS + " branch -D ancestor-fallback-master", "allow", cwd=BRANCHFALLBACKMASTER)
# THE FALLBACK MUST DENY TOO, not just pass. A base that silently gave up would read as
# unreadable and let an only-copy branch through; these prove the fallback is a real read.
sh("branch: local main's fallback still denies an only-copy branch",
   VCS + " branch -D unmerged-fallback", "deny", "shared-tree", cwd=BRANCHFALLBACKMAIN)
sh("branch: local master's fallback still denies an only-copy branch",
   VCS + " branch -D unmerged-fallback-master", "deny", "shared-tree", cwd=BRANCHFALLBACKMASTER)
# NONE OF THE THREE ANSWERS. The base is unreadable, so the call is allowed and logged, never
# denied and never silently passed over an unproven subject.
sh("branch: no origin/HEAD, no local main, no local master: unreadable, allowed",
   VCS + " branch -D orphan-work", "allow", cwd=BRANCHNOBASE)

# `git worktree remove <path>`. The subject lives at PATH, not at the checkout the command runs
# in, so every case below runs from WTMAIN and names one of its own linked worktrees.
sh("worktree remove: a clean, unlocked tree with no live session passes",
   VCS + " worktree remove " + slash(WTCLEAN), "allow", cwd=WTMAIN)
sh("worktree remove: uncommitted and untracked work denies",
   VCS + " worktree remove " + slash(WTDIRTY), "deny", "shared-tree", cwd=WTMAIN)
sh("worktree remove: the force flag does not skip the subject read",
   VCS + " worktree remove --force " + slash(WTDIRTY), "deny", "shared-tree", cwd=WTMAIN)
sh("worktree remove: a locked tree denies even though it is clean",
   VCS + " worktree remove " + slash(WTLOCKED), "deny", "shared-tree", cwd=WTMAIN)
# A LIVE SESSION. WTLIVECFG's one record names THIS TEST RUNNER'S OWN pid and its real start
# time, read back with `ps` exactly as the guard reads it, so the process really is alive and
# the start time really does match.
sh("worktree remove: a live session standing in a clean tree still denies",
   VCS + " worktree remove " + slash(WTLIVE), "deny", "shared-tree", cwd=WTMAIN,
   config=WTLIVECFG)
# A RECYCLED PID CANNOT INHERIT A DEAD SESSION'S CLAIM. Two ways a record goes stale: the pid no
# longer runs at all, or the pid runs but its start time no longer matches (another process now
# holds that number).
sh("worktree remove: a session record for a pid that is no longer running does not deny",
   VCS + " worktree remove " + slash(WTDEADSESSION), "allow", cwd=WTMAIN, config=WTDEADCFG)
sh("worktree remove: a live pid whose recorded start time does not match does not deny",
   VCS + " worktree remove " + slash(WTSTALESTART), "allow", cwd=WTMAIN, config=WTSTALESTARTCFG)

# `git worktree prune`. This deletes NO FILES, only an administrative record, so the worst case
# is an ASK, never a deny, whatever the run location.
sh("worktree prune: a stale record asks, never denies",
   VCS + " worktree prune", "ask", "shared-tree", cwd=WTPRUNE)
sh("worktree prune: nothing to prune passes", VCS + " worktree prune", "allow", cwd=WTMAIN)
sh("worktree prune: -n itself is a read, not a discard, so it passes unconditionally",
   VCS + " worktree prune -n", "allow", cwd=WTPRUNE)


# =========================================================================== 1b. the pointer HEAD
#
# The pointer checkout is the one checkout whose HEAD decides which copy of the rules and the gates
# every session on this machine runs. Its HEAD stays `main`.
#
# BOTH DIRECTIONS ARE PINNED, and the GREEN half carries the weight here: a rule this broad would
# stop every lane from switching a branch anywhere. So the same two commands are run in a
# non-pointer checkout and in a real linked worktree of the pointer checkout itself, and both must
# be allowed.

sh("pointer: checkout of a branch in the pointer checkout is refused",
   VCS + " checkout somebranch", "deny", "pointer-head", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: switch of a branch in the pointer checkout is refused",
   VCS + " switch somebranch", "deny", "pointer-head", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: a new branch with -b is refused",
   VCS + " checkout -b somebranch", "deny", "pointer-head", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: a new branch with -b and a start point is refused",
   VCS + " checkout -b somebranch origin/main", "deny", "pointer-head", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: -B resets and switches, so it is refused",
   VCS + " checkout -B somebranch", "deny", "pointer-head", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: an orphan branch is refused",
   VCS + " checkout --orphan somebranch", "deny", "pointer-head", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: switch -c is the new-branch form of switch",
   VCS + " switch -c somebranch", "deny", "pointer-head", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: detaching leaves no branch named at all",
   VCS + " checkout --detach", "deny", "pointer-head", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: switch -d detaches too",
   VCS + " switch -d somebranch", "deny", "pointer-head", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: the previous-branch shorthand is a switch",
   VCS + " checkout -", "deny", "pointer-head", cwd=PTRMAIN, config=PTRCFG)
# A remote-tracking ref detaches HEAD rather than putting it on `main`, so the exemption for the
# bare name `main` must not reach it.
sh("pointer: origin/main detaches, so it is not the main exemption",
   VCS + " checkout origin/main", "deny", "pointer-head", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: a subdirectory of the pointer checkout is still the pointer checkout",
   "cd " + slash(os.path.join(PTRMAIN, "docs")) + " && " + VCS + " switch somebranch", "deny",
   "pointer-head", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: -C reaches the pointer checkout from anywhere",
   VCS + " -C " + slash(PTRMAIN) + " switch somebranch", "deny", "pointer-head", cwd=NOGIT,
   config=PTRCFG)

# THE MOVE TO MAIN IS THE REPAIR. A deny there would wall off the one command that restores the
# invariant this rule exists to protect.
sh("pointer: a move back to main restores the invariant and passes",
   VCS + " checkout main", "allow", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: switch main passes for the same reason",
   VCS + " switch main", "allow", cwd=PTRMAIN, config=PTRCFG)

# READS NEVER FIRE.
sh("pointer: listing branches only reads", VCS + " branch --list", "allow", cwd=PTRMAIN,
   config=PTRCFG)
sh("pointer: status only reads", VCS + " status", "allow", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: a bare checkout names no branch and moves no HEAD", VCS + " checkout", "allow",
   cwd=PTRMAIN, config=PTRCFG)
sh("pointer: worktree add is the remedy, not the act",
   VCS + " worktree add -b somebranch " + slash(os.path.join(ROOT, "newlane")), "allow",
   cwd=PTRMAIN, config=PTRCFG)

# THE RULE IS NOT TOO BROAD. The same two commands in another checkout, and in a real linked
# worktree of the pointer checkout, are allowed.
sh("pointer: checkout of a branch in another checkout is allowed",
   VCS + " checkout somebranch", "allow", cwd=GITMAIN, config=PTRCFG)
sh("pointer: switch of a branch in another checkout is allowed",
   VCS + " switch somebranch", "allow", cwd=GITMAIN, config=PTRCFG)
sh("pointer: checkout of a branch in a worktree of the pointer checkout is allowed",
   VCS + " checkout somebranch", "allow", cwd=PTRWT, config=PTRCFG)
sh("pointer: switch of a branch in a worktree of the pointer checkout is allowed",
   VCS + " switch somebranch", "allow", cwd=PTRWT, config=PTRCFG)
sh("pointer: a branch switch in a directory that is no git tree is allowed",
   VCS + " switch somebranch", "allow", cwd=NOGIT, config=PTRCFG)

# RULE 1 KEEPS GOVERNING A PATH OPERATION IN THIS CHECKOUT, UNCHANGED. `f.txt` is really modified
# there, so rule 1 denies; `keep.txt` is really clean, so rule 1's empty-subject arm passes. Both
# answers are rule 1's own, and the pointer rule never sees either call.
sh("pointer: checkout of a dirty path keeps rule 1's deny", VCS + " checkout -- f.txt", "deny",
   "shared-tree", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: checkout of a clean path keeps rule 1's empty-subject pass",
   VCS + " checkout -- keep.txt", "allow", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: a bare path argument is still rule 1's subject", VCS + " checkout f.txt", "deny",
   "shared-tree", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: --theirs is a path operation, not a branch switch",
   VCS + " checkout --theirs f.txt", "deny", "shared-tree", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: a branch plus a path writes one file, and rule 1 judges it",
   VCS + " checkout somebranch -- f.txt", "deny", "shared-tree", cwd=PTRMAIN, config=PTRCFG)

# THE PATH-OPERATION ARMS OF THIS RULE, REACHED. Rule 1 answers first for a dirty or
# file-shaped pathspec, so these two are the cases where rule 1b's own `--` and `--theirs` arms
# are what decides. `docs` is a real, clean, extensionless directory in the fixture, which rule 1
# reads as neither a path nor a discard, so the call arrives at rule 1b untouched.
sh("pointer: a double dash names a path, and no HEAD moves", VCS + " checkout -- docs", "allow",
   cwd=PTRMAIN, config=PTRCFG)
sh("pointer: --theirs with an extensionless path is no branch switch",
   VCS + " checkout --theirs docs", "allow", cwd=PTRMAIN, config=PTRCFG)

# THE GIT DIRECTORY IS WHERE HEAD LIVES. MEASURED 2026-09-19 with real git: from an unrelated
# directory, `git --git-dir=<X>/.git switch other` moved HEAD inside X, with no `-C`, no `cd` and
# no `--work-tree` on the line. So the rule reads `--git-dir`, and the comparison is between git
# directories rather than between top levels.
PTR_GITDIR = slash(os.path.join(PTRMAIN, ".git"))
OTHER_GITDIR = slash(os.path.join(GITMAIN, ".git"))
PTRWT_GITDIR = slash(os.path.join(PTRMAIN, ".git", "worktrees", "ptrlane"))

sh("pointer: --git-dir reaches the pointer HEAD from an unrelated directory",
   VCS + " --git-dir=" + PTR_GITDIR + " switch somebranch", "deny", "pointer-head", cwd=NOGIT,
   config=PTRCFG)
sh("pointer: the spaced --git-dir form is the same act",
   VCS + " --git-dir " + PTR_GITDIR + " checkout somebranch", "deny", "pointer-head", cwd=NOGIT,
   config=PTRCFG)
sh("pointer: --git-dir with a move to main keeps the exemption",
   VCS + " --git-dir=" + PTR_GITDIR + " checkout main", "allow", cwd=NOGIT, config=PTRCFG)
sh("pointer: --git-dir naming another clone is allowed",
   VCS + " --git-dir=" + OTHER_GITDIR + " switch somebranch", "allow", cwd=NOGIT, config=PTRCFG)
# A linked worktree keeps its own HEAD in its own per-worktree git directory, so naming that
# directory is not naming the primary checkout's HEAD.
sh("pointer: --git-dir naming a worktree of the pointer clone is allowed",
   VCS + " --git-dir=" + PTRWT_GITDIR + " switch somebranch", "allow", cwd=NOGIT, config=PTRCFG)
sh("pointer: a --git-dir that is not there fires nothing",
   VCS + " --git-dir=" + slash(os.path.join(ROOT, "nosuchgitdir")) + " switch somebranch",
   "allow", cwd=NOGIT, config=PTRCFG)
# `--work-tree` retargets the FILES and leaves HEAD where the call runs, so it must NOT be read as
# a pointer HEAD move. Run from a directory that is no git tree, this names the pointer checkout's
# files and no checkout's HEAD.
sh("pointer: --work-tree alone moves no HEAD in the pointer checkout",
   VCS + " --work-tree=" + slash(PTRMAIN) + " switch somebranch", "allow", cwd=NOGIT,
   config=PTRCFG)

# FAIL OPEN. An unreadable pointer means no rule, never a broken session.
sh("pointer: a rules file with no pointer line fires nothing",
   VCS + " switch somebranch", "allow", cwd=PTRMAIN, config=PTRBADCFG)
sh("pointer: a pointer naming a directory that is gone fires nothing",
   VCS + " switch somebranch", "allow", cwd=PTRMAIN, config=PTRGONECFG)
sh("pointer: no global rules file at all fires nothing",
   VCS + " switch somebranch", "allow", cwd=PTRMAIN, config=PTRNOCFG)


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

# BLAST RADIUS of the loop-keyword fix in `resolve_command` (Rule 9's own defect): a kill inside
# a loop's `do` block, or inside an `if`'s `then` block, used to resolve to the keyword as its
# command word and pass. MEASURED wrongly allowed before this fix.
sh("kill: a pkill inside a loop's do-block, MEASURED wrongly allowed",
   "while true; do pkill -f server; done", "deny", "machine-wide-kill", cwd=NOGIT)
sh("kill: a pkill inside an if's then-block, MEASURED wrongly allowed",
   "if true; then pkill -f server; fi", "deny", "machine-wide-kill", cwd=NOGIT)


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

# BLAST RADIUS of the loop-keyword fix: `live_stream_hit` already reads every token of its
# segment, not only the first, so a follow flag inside a loop's do-block denied before this fix
# too. Pinned here so a later change cannot narrow that read back to command position only.
sh("stream: tail -f inside a loop's do-block denies unchanged",
   "while true; do tail -f app.log; done", "deny", "live-stream", cwd=NOGIT)


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

# Rule 9 missed every loop body. `split_segments` cuts a loop on its own `;`, so the segment
# after it is `do sleep 1`, and the command word read as `do`, not `sleep`. MEASURED against the
# live guard before this fix: the two loops below were both wrongly allowed.
sh("waiter: a while-loop with a pattern-polling condition, MEASURED wrongly allowed",
   "while ! pgrep -f server; do sleep 1; done", "deny", "waiter",
   carries=("condition polls",))
sh("waiter: an until-loop over a plain readiness check, MEASURED wrongly allowed",
   "until curl -sf localhost:3000; do sleep 2; done", "deny", "waiter")
sh("waiter: a for-loop's own do-block still denies",
   "for i in 1 2 3; do sleep 1; done", "deny", "waiter")
sh("waiter: a non-waiter loop body stays allowed",
   'while read l; do echo "$l"; done', "allow", cwd=NOGIT)

# `split_segments` read the `'` in a `#` comment as opening a quote that ran to the end of the
# text, so every loop under such a comment was invisible. MEASURED in Banchi on 2026-09-19 on
# its lifted copy: the runaway-driver fixture went from refused to allowed. A `#` that starts
# a word is a comment to the end of its line; one inside a word or a quote is not.
sh("waiter: a loop under a comment holding an apostrophe, MEASURED wrongly allowed",
   "# the merge driver's shape\nwhile true; do sleep 5; done", "deny", "waiter")
sh("waiter: a `#` inside a word is not a comment, so the loop after it still denies",
   "echo fix#3; while true; do sleep 5; done", "deny", "waiter")


# =========================================================================== 2d. the silent write
#
# Rule 1c, the owner's ruling. CLAUDE.md: "Never discard a command's output." A discarding
# redirect denies on any of the six subcommands, whatever git itself would have printed. git's
# own `-q`/`--quiet` flag is judged per subcommand, against `QUIET_FLAG_SUBCOMMANDS`, MEASURED
# 2026-09-19 and 2026-09-20 in throwaway repos, never a shared checkout, all six. `push`, `merge`,
# and `rebase` deny on the flag alone: each one's success and its own no-op are both silent at
# exit 0, so the flag erases the one line that told a real write from one that moved nothing.
# `commit`, `tag`, and `cherry-pick` carve out: `commit`'s refusal and no-op both keep their own
# stream and a nonzero exit; `tag` has no `-q`/`--quiet` at all, so the flag is always a loud,
# immediate option-parsing failure (exit 129); `cherry-pick`'s short form is invalid the same way,
# and its long form still prints a full summary, conflict, or "nothing to commit" in every state.

sh("silent-write: push's own quiet flag needs no redirect at all",
   VCS + " push --quiet", "deny", "silent-write", carries="moved nothing", cwd=NOGIT)
sh("silent-write: merge's own quiet flag needs no redirect at all, MEASURED 2026-09-20",
   VCS + " merge --quiet feature/x", "deny", "silent-write", carries="moved nothing", cwd=NOGIT)
sh("silent-write: rebase's own quiet flag needs no redirect at all, MEASURED 2026-09-20",
   VCS + " rebase -q main", "deny", "silent-write", carries="moved nothing", cwd=NOGIT)
sh("silent-write: a discarded refusal, stderr alone",
   VCS + " commit -m x 2>/dev/null", "deny", "silent-write", carries="a redirect silences",
   cwd=NOGIT)
sh("silent-write: a discarded proof of landing, stdout alone",
   VCS + " commit -m x >/dev/null", "deny", "silent-write", carries="a redirect silences",
   cwd=NOGIT)
sh("silent-write: both streams discarded together",
   VCS + " commit -q -m x >/dev/null 2>&1", "deny", "silent-write", cwd=NOGIT)
sh("silent-write: a tag silenced by a discarded stream, its own flag does not exist",
   VCS + " tag -a v1 -m x >/dev/null 2>&1", "deny", "silent-write", cwd=NOGIT)
sh("silent-write: a cherry-pick silenced by a discarded stream",
   VCS + " cherry-pick --quiet abc1234 >/dev/null 2>&1", "deny", "silent-write", cwd=NOGIT)
sh("silent-write: the Windows null device denies with no quiet flag at all",
   VCS + " commit -m x 2>NUL", "deny", "silent-write", cwd=NOGIT)
sh("silent-write: PowerShell's null variable denies with no quiet flag at all",
   VCS + " commit -m x 2>$null", "deny", "silent-write", tool="PowerShell", cwd=NOGIT)

sh("silent-write: an ordinary commit stays allowed", VCS + " commit -m x", "allow", cwd=NOGIT)
sh("silent-write: an ordinary push stays allowed", VCS + " push", "allow", cwd=NOGIT)
sh("silent-write: commit's own quiet flag is a carve-out, MEASURED 2026-09-19",
   VCS + " commit -q -m x", "allow", cwd=NOGIT)
sh("silent-write: commit's own quiet flag stays a carve-out with -a as well",
   VCS + " commit -q -a -m x", "allow", cwd=NOGIT)
sh("silent-write: tag's own quiet flag is a carve-out, MEASURED 2026-09-20 (tag has no -q at all)",
   VCS + " tag -a v1 -m x -q", "allow", cwd=NOGIT)
sh("silent-write: tag's own long quiet flag is a carve-out too, same measurement",
   VCS + " tag -a v1 -m x --quiet", "allow", cwd=NOGIT)
sh("silent-write: cherry-pick's short quiet flag is a carve-out, MEASURED 2026-09-20 "
   "(-q is not a cherry-pick option)",
   VCS + " cherry-pick -q abc1234", "allow", cwd=NOGIT)
sh("silent-write: cherry-pick's long quiet flag is a carve-out too, MEASURED 2026-09-20 "
   "(every state still prints in full)",
   VCS + " cherry-pick --quiet abc1234", "allow", cwd=NOGIT)
sh("silent-write: fetch's own quiet flag is a carve-out",
   VCS + " fetch -q", "allow", cwd=NOGIT)
sh("silent-write: fetch discarding both streams is a carve-out",
   VCS + " fetch --quiet origin main >/dev/null 2>&1", "allow", cwd=NOGIT)
sh("silent-write: an abort lands nothing, so it is carved out",
   VCS + " merge --abort 2>/dev/null", "allow", cwd=NOGIT)
sh("silent-write: the exit-code test shape rule 1b already relies on",
   VCS + " rev-parse -q --verify HEAD >/dev/null 2>&1", "allow", cwd=NOGIT)
sh("silent-write: an ordinary read discarding its output is a carve-out",
   VCS + " status --porcelain >/dev/null 2>&1", "allow", cwd=NOGIT)
sh("silent-write: 2>&1 alone duplicates a stream and discards nothing",
   VCS + " commit -m x 2>&1", "allow", cwd=NOGIT)


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

# BLAST RADIUS of the loop-keyword fix: `git_calls` already scans every token of its segment for
# `git`, not only the first, so a force push inside a loop's do-block asked before this fix too.
# Pinned here so a later change cannot narrow that scan back to command position only.
sh("push: git push --force inside a loop's do-block asks unchanged",
   "while true; do " + VCS + " push --force; done", "ask", "force-push", cwd=NOGIT)

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
add("frozen: Write of the config-watch baseline store", "deny", "frozen-path", tool="Write",
    cwd=NOGIT, file_path=CFG_STATE)
# `cp` onto the store carries no readable value, so rule 8 would stay silent. Rule 7 needs only the
# PATH, which is why the store is frozen rather than merely watched.
sh("frozen: cp onto the config-watch baseline store", "cp /tmp/x.json " + CFG_STATE, "deny",
   "frozen-path", cwd=NOGIT)
sh("frozen: sed -i on the config-watch baseline store", "sed -i '' s/a/b/ " + CFG_STATE, "deny",
   "frozen-path", cwd=NOGIT)
add("frozen: Read of the config-watch baseline store is allowed", "allow", tool="Read",
    cwd=NOGIT, file_path=CFG_STATE)
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


# =========================================================================== 6b. the model cap
#
# Rule 8. A project settings file overrides the owner's user settings, so a write there can lift
# the subagent model cap the user settings hold. The decision is `ask`, never `deny`: the same
# write is how an Opus worker gets enabled on purpose.
#
# THE ASK NAMES THE VALUE AND THE FILE. `REASON_MAY_NAME` holds that exemption, keyed by this
# rule's name and no case's say-so, and each ask case pins the fragment the approver must read
# through `carries`. The generic-reason rule the exemption steps around governs a REFUSAL'S REMEDY,
# where naming the target reads as permission to run it. This is an ask whose whole job is to say
# what is being turned on.
#
# BOTH DIRECTIONS ARE PINNED here too: the settings write that touches neither variable keeps the
# silent Decision 7 allow, and the config directory's own settings keep rule 7's deny.

CAP_KEY = "CLAUDE_CODE_SUBAGENT_MODEL"
CAP_FORCE = CAP_KEY + "_FORCE"
OPUS = "claude-opus-5"
MANAGED_SETTINGS = slash(os.path.join(ROOT, "managed", "managed-settings.json"))
PROJ_README = slash(os.path.join(PROJ, "README.md"))


def cap_settings(model=OPUS, force="1", compact=False):
    """The text of a settings file that sets the cap variables."""
    body = {"env": {CAP_KEY: model, CAP_FORCE: force}}
    if compact:
        return json.dumps(body, separators=(",", ":"))
    return json.dumps(body, indent=2)


add("cap: Write of a project local settings file setting an opus model asks", "ask",
    "subagent-model-cap", tool="Write", cwd=NOGIT, file_path=PROJ_LOCAL, content=cap_settings(),
    carries=(OPUS, "settings.local.json"))
add("cap: Write of a project settings file setting an opus model asks", "ask",
    "subagent-model-cap", tool="Write", cwd=NOGIT, file_path=PROJ_SETTINGS, content=cap_settings(),
    carries=(OPUS, "settings.json"))
add("cap: a relative project settings path setting an opus model asks", "ask",
    "subagent-model-cap", tool="Write", cwd=PROJ, file_path=".claude/settings.local.json",
    content=cap_settings(), carries=(OPUS,))
add("cap: Edit turning the force flag off asks", "ask", "subagent-model-cap", tool="Edit",
    cwd=NOGIT, file_path=PROJ_SETTINGS,
    old_string='"' + CAP_FORCE + '": "1"', new_string='"' + CAP_FORCE + '": "0"',
    carries=(CAP_FORCE + " = 0",))
add("cap: Edit naming the model variable with no value asks", "ask", "subagent-model-cap",
    tool="Edit", cwd=NOGIT, file_path=PROJ_LOCAL,
    old_string='"' + CAP_KEY + '": "sonnet",', new_string="",
    carries=(CAP_KEY + " = sonnet",))
add("cap: MultiEdit reaching an opus model asks", "ask", "subagent-model-cap", tool="MultiEdit",
    cwd=NOGIT, file_path=PROJ_LOCAL,
    edits=[{"old_string": '"' + CAP_KEY + '": "sonnet"',
            "new_string": '"' + CAP_KEY + '": "' + OPUS + '"'}],
    carries=(OPUS,))
add("cap: a managed settings file is a settings file", "ask", "subagent-model-cap", tool="Write",
    cwd=NOGIT, file_path=MANAGED_SETTINGS, content=cap_settings(), carries=(OPUS,))

# THE EDIT LIST IS READ WHOLE. An earlier version read the first 200 edits, and the review MEASURED
# the boundary that bought: 199 no-op edits ahead of the lift asked, 200 allowed. This case pins the
# boundary itself, so a count bound cannot come back unseen.
CAP_NOOP_EDITS = [{"old_string": "line %d" % index, "new_string": "row %d" % index}
                  for index in range(200)]
add("cap: 200 no-op edits ahead of the lift still asks", "ask", "subagent-model-cap",
    tool="MultiEdit", cwd=NOGIT, file_path=PROJ_SETTINGS,
    edits=CAP_NOOP_EDITS + [{"old_string": '"' + CAP_KEY + '": "sonnet"',
                             "new_string": '"' + CAP_KEY + '": "' + OPUS + '"'}],
    carries=(OPUS,))
add("cap: the lift in the last of 400 edits still asks", "ask", "subagent-model-cap",
    tool="MultiEdit", cwd=NOGIT, file_path=PROJ_LOCAL,
    edits=(CAP_NOOP_EDITS * 2) + [{"old_string": '"' + CAP_FORCE + '": "1"',
                                   "new_string": '"' + CAP_FORCE + '": "0"'}],
    carries=(CAP_FORCE + " = 0",))

# A SYMLINK IS A SPELLING OF THE FILE IT POINTS AT. Rule 7 resolves its paths, so rule 8 resolves
# too, else an alias walks past this rule and not past that one. A platform that refuses the link
# gets the honest answer for the path that is then only a name: allow.
CAP_ALIAS = slash(os.path.join(PROJ, "alias.json"))
try:
    os.symlink(os.path.join(PROJ, ".claude", "settings.json"), CAP_ALIAS.replace("/", os.sep))
    CAP_ALIAS_MADE = True
except Exception:
    CAP_ALIAS_MADE = False
add("cap: a symlink to a project settings file resolves and asks",
    "ask" if CAP_ALIAS_MADE else "allow", "subagent-model-cap" if CAP_ALIAS_MADE else None,
    tool="Write", cwd=NOGIT, file_path=CAP_ALIAS, content=cap_settings(),
    carries=(OPUS,) if CAP_ALIAS_MADE else ())

# A JSON ESCAPE IN THE KEY. The text pattern reads no key here, so the JSON walk is what answers.
CAP_ESCAPED_KEY = '\\u0043LAUDE_CODE_SUBAGENT_MODEL'
add("cap: a JSON-escaped key in the content asks", "ask", "subagent-model-cap", tool="Write",
    cwd=NOGIT, file_path=PROJ_LOCAL,
    content='{\n  "env": {\n    "' + CAP_ESCAPED_KEY + '": "' + OPUS + '"\n  }\n}\n',
    carries=(CAP_KEY + " = " + OPUS,))
add("cap: a JSON number value is read, not guessed", "ask", "subagent-model-cap", tool="Write",
    cwd=NOGIT, file_path=PROJ_SETTINGS,
    content=json.dumps({"env": {CAP_FORCE: 0}}), carries=(CAP_FORCE + " = 0",))

# THE BARE-KEY PASS is what answers when neither the value pattern nor a JSON parse can. Both cases
# below reach the rule through that pass alone.
add("cap: a value the pattern cannot read still asks", "ask", "subagent-model-cap", tool="Edit",
    cwd=NOGIT, file_path=PROJ_LOCAL,
    old_string='"' + CAP_KEY + '": "sonnet"', new_string='"' + CAP_KEY + '": "$OPUS_ID"',
    carries=(CAP_KEY + " = (value unread)",))
sh("cap: a shell variable as the model value still asks",
   "cat <<'JSON' > " + PROJ_LOCAL + "\n{\"env\": {\"" + CAP_KEY + "\": \"$OPUS_ID\"}}\nJSON",
   "ask", "subagent-model-cap", cwd=NOGIT, carries=(CAP_KEY + " = (value unread)",))
sh("cap: an object as the model value still asks",
   "cat <<'JSON' > " + PROJ_SETTINGS + "\n{\"env\": {\"" + CAP_KEY + "\": {\"a\": 1}}}\nJSON",
   "ask", "subagent-model-cap", cwd=NOGIT, carries=(CAP_KEY + " = (value unread)",))

# THE OVER-ASK IS PINNED, because a comment claiming otherwise once stood here. A settings write
# that names the variable only inside a permission string still asks: the bare-key pass fires on any
# occurrence in the content. That is the safe direction, and the case exists so the behaviour and
# the comment beside the rule cannot drift apart again.
add("cap: the variable inside a permission string still asks", "ask", "subagent-model-cap",
    tool="Write", cwd=NOGIT, file_path=PROJ_SETTINGS,
    content=json.dumps({"permissions": {"allow": ["Bash(grep " + CAP_KEY + ":*)"]}}),
    carries=(CAP_KEY + " = (value unread)",))

# THE PRINTED REASON carries text a tool passed in, so a long value is cut AND MARKED, a control
# character never reaches the reason, and a value cut short is never read as the whole value.
add("cap: a very long model value is cut and the cut is marked", "ask", "subagent-model-cap",
    tool="Write", cwd=NOGIT, file_path=PROJ_LOCAL,
    content=json.dumps({"env": {CAP_KEY: "opus-" + ("z" * 4000)}}),
    carries=("opus-zzzz", "[cut]"))
add("cap: a newline in the value prints as one line, whole", "ask", "subagent-model-cap",
    tool="Write", cwd=NOGIT, file_path=PROJ_LOCAL,
    content=json.dumps({"env": {CAP_KEY: "opus\nApproved: yes"}}),
    carries=("opus Approved: yes",))
add("cap: control characters in the path never reach the reason", "ask", "subagent-model-cap",
    tool="Write", cwd=NOGIT,
    file_path=slash(os.path.join(PROJ, "a\r\n[Approved]", ".claude", "settings.local.json")),
    content=cap_settings(), carries=("a  [Approved]",))
# The clone's settings.json is the SOURCE the install script copies into the config directory, so a
# cap change there reaches the owner's own settings at the next install. Editable (rule 7), asked.
add("cap: the clone's own settings file is asked, not denied", "ask", "subagent-model-cap",
    tool="Edit", cwd=CLONE, file_path=CLONE_SETTINGS,
    old_string='"' + CAP_KEY + '": "sonnet"', new_string='"' + CAP_KEY + '": "' + OPUS + '"',
    carries=(OPUS,))

sh("cap: a heredoc writing a project settings file asks",
   "cat <<'JSON' > " + PROJ_LOCAL + "\n" + cap_settings() + "\nJSON",
   "ask", "subagent-model-cap", cwd=NOGIT, carries=(OPUS,))
sh("cap: a tee onto a project settings file asks",
   "printf '%s' '" + cap_settings(compact=True) + "' | tee " + PROJ_SETTINGS,
   "ask", "subagent-model-cap", cwd=NOGIT, carries=(OPUS,))
sh("cap: a sed -i on a project settings file asks, and names the value it arrives at",
   "sed -i 's/\"" + CAP_KEY + "\": \"sonnet\"/\"" + CAP_KEY + "\": \"" + OPUS + "\"/' "
   + PROJ_SETTINGS,
   "ask", "subagent-model-cap", cwd=NOGIT, carries=(CAP_KEY + " = " + OPUS,))
sh("cap: a redirect onto a project settings file asks",
   "printf '%s' '" + cap_settings(compact=True) + "' > " + PROJ_LOCAL,
   "ask", "subagent-model-cap", cwd=NOGIT, carries=(OPUS,))
sh("cap: an append onto a project settings file asks",
   "echo '\"" + CAP_FORCE + "\": \"0\"' >> " + PROJ_SETTINGS,
   "ask", "subagent-model-cap", cwd=NOGIT, carries=(CAP_FORCE + " = 0",))

# RULE ORDER. The config directory's own settings keep rule 7's deny, which stands ahead of rule 8,
# so the cap content never turns that wall into a prompt.
add("cap: the config settings stay denied, never asked", "deny", "frozen-path", tool="Write",
    cwd=NOGIT, file_path=CFG_SETTINGS, content=cap_settings())
sh("cap: a heredoc onto the config settings stays denied",
   "cat <<'JSON' > " + CFG_SETTINGS + "\n" + cap_settings() + "\nJSON",
   "deny", "frozen-path", cwd=NOGIT)

# THE OTHER DIRECTION. A settings write that touches neither variable, and a file that only TALKS
# about them, both keep their old answer.
add("cap: a project settings write touching neither variable is allowed", "allow", tool="Write",
    cwd=NOGIT, file_path=PROJ_SETTINGS,
    content=json.dumps({"env": {"TZ": "UTC"}, "permissions": {"allow": ["Bash(ls:*)"]}}, indent=2))
add("cap: prose naming the variable in a README is allowed", "allow", tool="Write", cwd=NOGIT,
    file_path=PROJ_README,
    content="Set " + CAP_KEY + " to sonnet, with " + CAP_FORCE + " at 1, to cap every worker.\n")
add("cap: an ordinary source file naming the variable is allowed", "allow", tool="Edit", cwd=NOGIT,
    file_path=slash(os.path.join(PROJ, "src", "env.py")),
    old_string="x = 1", new_string='CAP = os.environ["' + CAP_KEY + '"]')
add("cap: a Read of a settings file is not a write", "allow", tool="Read", cwd=NOGIT,
    file_path=PROJ_LOCAL)
sh("cap: a grep for the variable in a settings file is not a write",
   "grep -n " + CAP_KEY + " " + PROJ_SETTINGS, "allow", cwd=NOGIT)
sh("cap: reading a settings file into another file is not a write to it",
   "cat " + PROJ_SETTINGS + " > /tmp/copy.json", "allow", cwd=NOGIT)

# FAILING OPEN, this rule's own shapes. A content field of the wrong type, an edit list of the
# wrong type, and a payload with no tool name at all: each allows the call.
add("cap: a content field that is not a string allows", "allow", tool="Write", cwd=NOGIT,
    file_path=PROJ_LOCAL, content=3)
add("cap: an edit list that is not a list allows", "allow", tool="MultiEdit", cwd=NOGIT,
    file_path=PROJ_LOCAL, edits="not a list")
add("cap: an edit list holding something other than an object allows", "allow", tool="MultiEdit",
    cwd=NOGIT, file_path=PROJ_LOCAL, edits=[7])
add("cap: a payload with no tool name allows", "allow",
    raw=json.dumps({"tool_input": {"file_path": PROJ_LOCAL, "content": cap_settings()}}))


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
        if case["session"]:
            body["session_id"] = case["session"]
        payload = json.dumps(body)
    env = dict(os.environ)
    # `.get`, not `[...]`: a checker below builds a case dict by hand and names only the keys it
    # needs, so a key added here must not turn into a KeyError in a checker that never asked for
    # it. MEASURED on CI run 35473213091: indexing this key crashed `stack_reason_hygiene_case`,
    # which reached this branch through the pull request's MERGE commit. It landed on main (#54)
    # after this branch started, so no run on the branch alone could have caught it. A hand-built
    # case is the shape to expect from the next such checker too, so the read tolerates it.
    env["CLAUDE_CONFIG_DIR"] = case.get("config") or CFG
    # The scratchpad pass reads the session id the PAYLOAD carries, and falls back to the
    # environment only when the payload carries none. A real session id in the runner's own
    # environment would leak into every case, so it is dropped here and each case names its own.
    env.pop("CLAUDE_CODE_SESSION_ID", None)
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


def cap_log_case():
    """Rule 8 logs its ask the way the other rules log, so the config report can surface it.

    One tool call and one shell call, each lifting the cap in a project settings file. Each must
    print an `ask`, and each must add one `ask`/`subagent-model-cap` line whose matched text holds
    the file and the requested value.
    """
    folder = os.path.join(ROOT, "caplog")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "guard.log")
    if os.path.exists(path):
        os.remove(path)
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = folder
    calls = [
        {"tool_name": "Write",
         "tool_input": {"file_path": PROJ_LOCAL, "content": cap_settings()}, "cwd": NOGIT},
        {"tool_name": "Bash",
         "tool_input": {"command": "printf '%s' '" + cap_settings(compact=True) + "' > "
                        + PROJ_SETTINGS},
         "cwd": NOGIT},
    ]
    for payload in calls:
        result = subprocess.run(
            [sys.executable, GUARD], input=json.dumps(payload), capture_output=True, text=True,
            env=env, timeout=60,
        )
        if result.returncode != 0:
            return False, "guard exited %d" % result.returncode
        if '"ask"' not in result.stdout:
            return False, "expected an ask, got %r" % result.stdout.strip()[:120]
    if not os.path.exists(path):
        return False, "no log file was written for the asks"
    with open(path, encoding="utf-8") as handle:
        lines = [line for line in handle.read().splitlines() if line.strip()]
    asks = [line.split("\t") for line in lines if line.split("\t")[2:4] == ["ask",
                                                                           "subagent-model-cap"]]
    if len(asks) != 2:
        return False, "expected two ask lines, found %d of %d" % (len(asks), len(lines))
    for fields in asks:
        if len(fields) != 5 or OPUS not in fields[4] or "settings" not in fields[4]:
            return False, "the log line does not carry the file and the value: %r" % fields[-1:]
    return True, "two ask lines, each naming the file and the model"


def cap_deep_path_log_case():
    """A cap lift under a DEEP path still logs the model, on every platform.

    THE DEFECT THIS PINS, MEASURED 2026-09-19: the guard joined the settings path and the cap
    reading into one log field and cut the join from the tail at the log's bound. A long root ate
    the field, and the line ended `CLAUDE_CODE_SUBAG` with the model gone. That is the one thing the
    line is written for. The suite caught it on macOS only, because a macOS temporary root is long
    and `/tmp` on ubuntu is short. THE FIXTURE BUILDS ITS OWN LONG PATH, so the case reads the same
    on every platform and ubuntu CI goes red on a regression too.

    The path is never created. Rule 8 judges the payload, so an absent file proves the same point
    and the case stays cheap.
    """
    deep = os.path.join(ROOT, "d" * 60, "e" * 60, "proj", ".claude", "settings.local.json")
    deep = slash(deep)
    if len(deep) <= 120:
        return False, "the fixture path is only %d characters, so it pins nothing" % len(deep)
    folder = os.path.join(ROOT, "capdeeplog")
    os.makedirs(folder, exist_ok=True)
    log = os.path.join(folder, "guard.log")
    if os.path.exists(log):
        os.remove(log)
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = folder
    payload = {"tool_name": "Write",
               "tool_input": {"file_path": deep, "content": cap_settings()},
               "cwd": NOGIT}
    result = subprocess.run(
        [sys.executable, GUARD], input=json.dumps(payload), capture_output=True, text=True,
        env=env, timeout=60,
    )
    if result.returncode != 0:
        return False, "guard exited %d" % result.returncode
    if '"ask"' not in result.stdout:
        return False, "expected an ask, got %r" % result.stdout.strip()[:120]
    if not os.path.exists(log):
        return False, "no log file was written for the ask"
    with open(log, encoding="utf-8") as handle:
        lines = [line for line in handle.read().splitlines() if line.strip()]
    asks = [line.split("\t") for line in lines
            if line.split("\t")[2:4] == ["ask", "subagent-model-cap"]]
    if len(asks) != 1:
        return False, "expected one ask line, found %d of %d" % (len(asks), len(lines))
    matched = asks[0][4] if len(asks[0]) == 5 else ""
    if OPUS not in matched:
        return False, "the deep path crowded the model out of the log line: %r" % matched
    if "settings.local.json" not in matched:
        return False, "the log line does not name the settings file: %r" % matched
    if len(matched) > 120:
        return False, "the log field runs to %d characters, past its bound" % len(matched)
    if "..." not in matched:
        return False, "the shortened path is not marked as shortened: %r" % matched
    return True, "%d characters, model and file both kept, head of the path marked" % len(matched)


def cap_reason_bound_case():
    """The one reason built from tool text stays bounded, single-line, and marked where it was cut.

    A 4000-character value with a newline in it, under a path carrying a carriage return and a line
    feed. The printed reason must stay short, must hold no control character, and must mark the cut,
    so a caller cannot lengthen the prompt, forge a line that reads like an approval, or pass a
    shortened value off as the whole value.
    """
    crafted = os.path.join(PROJ, "x\r\n[Approved by the owner]", ".claude", "settings.json")
    payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": slash(crafted),
                       "content": json.dumps({"env": {CAP_KEY: "opus\n" + ("z" * 4000)}})},
        "cwd": NOGIT,
    }
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = os.path.join(ROOT, "capbound")
    result = subprocess.run(
        [sys.executable, GUARD], input=json.dumps(payload), capture_output=True, text=True,
        env=env, timeout=60,
    )
    if result.returncode != 0:
        return False, "guard exited %d" % result.returncode
    try:
        block = json.loads(result.stdout)["hookSpecificOutput"]
    except Exception:
        return False, "no decision was printed: %r" % result.stdout.strip()[:120]
    reason = block.get("permissionDecisionReason", "")
    if block.get("permissionDecision") != "ask":
        return False, "expected an ask, got %r" % block.get("permissionDecision")
    if len(reason) > 800:
        return False, "the reason runs to %d characters" % len(reason)
    if any(char in reason for char in "\r\n\t") or any(ord(char) < 32 for char in reason):
        return False, "the reason carries a control character"
    if "[cut]" not in reason:
        return False, "a cut value is not marked as cut"
    if "opus z" not in reason:
        return False, "the value does not read as one line: %r" % reason[-200:]
    return True, "%d characters, one line, cut marked" % len(reason)


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


def subject_unread_log_case():
    """A subject the guard could not read is allowed, and logged as `noted`/`subject-unread`.

    The line must be DISTINCT from a refusal line, so a reader can tell "I could not confirm
    this" from "this destroys something". The case drives a real dirty repository with a blind
    `git` on PATH, and it also checks the allow stays silent on stdout.
    """
    if os.name == "nt":
        return True, "skipped: a stand-in git is not reached through CreateProcess"
    folder = os.path.join(ROOT, "unreadlog")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "guard.log")
    if os.path.exists(path):
        os.remove(path)
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = folder
    env["PATH"] = GITBLIND
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    result = subprocess.run(
        [sys.executable, GUARD],
        input=json.dumps({"tool_name": "Bash",
                          "tool_input": {"command": VCS + " reset --hard HEAD"},
                          "cwd": SUBJDIRTY}),
        capture_output=True, text=True, env=env, timeout=60,
    )
    if result.stdout.strip():
        return False, "expected a silent allow, got %r" % result.stdout.strip()[:120]
    if not os.path.exists(path):
        return False, "no log file was written for the unread subject"
    with open(path, encoding="utf-8") as handle:
        lines = [line for line in handle.read().splitlines() if line.strip()]
    if len(lines) != 1:
        return False, "expected one line, found %d" % len(lines)
    fields = lines[0].split("\t")
    if len(fields) != 5 or fields[2] != "noted" or fields[3] != "subject-unread":
        return False, "line does not read noted/subject-unread: %r" % lines[0]
    if "reset" not in fields[4]:
        return False, "the line does not carry the matched command: %r" % fields[4]
    return True, "one noted/subject-unread line, distinct from a refusal"


def branch_base_unread_log_case():
    """`git branch -D` over a repository with no `origin/HEAD`, no local `main` and no local
    `master` is allowed, and logged as `noted`/`subject-unread`, the same shape as an unreadable
    working-tree subject above.

    Unlike `subject_unread_log_case`, this needs no blind stand-in `git`: BRANCHNOBASE really
    answers none of the three resolve steps, so the read is genuinely unreadable, not simulated.
    """
    folder = os.path.join(ROOT, "branchnobaselog")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "guard.log")
    if os.path.exists(path):
        os.remove(path)
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = folder
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    result = subprocess.run(
        [sys.executable, GUARD],
        input=json.dumps({"tool_name": "Bash",
                          "tool_input": {"command": VCS + " branch -D orphan-work"},
                          "cwd": BRANCHNOBASE}),
        capture_output=True, text=True, env=env, timeout=60,
    )
    if result.stdout.strip():
        return False, "expected a silent allow, got %r" % result.stdout.strip()[:120]
    if not os.path.exists(path):
        return False, "no log file was written for the unresolved base"
    with open(path, encoding="utf-8") as handle:
        lines = [line for line in handle.read().splitlines() if line.strip()]
    if len(lines) != 1:
        return False, "expected one line, found %d" % len(lines)
    fields = lines[0].split("\t")
    if len(fields) != 5 or fields[2] != "noted" or fields[3] != "subject-unread":
        return False, "line does not read noted/subject-unread: %r" % lines[0]
    if "branch" not in fields[4]:
        return False, "the line does not carry the matched command: %r" % fields[4]
    return True, "one noted/subject-unread line for the unresolved base"


# --------------------------------------------------------------------------- the reason hygiene
#
# CLAUDE.md: "A refusal's printed remedy never names the forbidden target." The WHOLE printed
# reason is covered, not its last sentence, so no refusal may carry the file it refused. This is
# checked on every refused case rather than on a few, because one interpolated name is the whole
# defect and it can enter through any rule.
# `git checkout` and `git switch` are on this list for the pointer rule, and the list is global,
# so no rule may print either one in a remedy. The pointer rule's remedy is a worktree, and it
# names `git worktree add` instead, which is a different command and not the refused target.
FORBIDDEN_IN_A_REASON = (ENV, ROOT, slash(ROOT), "settings.json", "CLAUDE.md", "guard.py",
                         ".claude", "app.log", "sleep", VCS + " checkout", VCS + " switch")

# ONE RULE MAY NAME ITS SUBJECT, and only the fragments listed beside it. Rule 8 asks rather than
# refuses, and the ask exists to tell an approver what is being turned on and where, so the settings
# path is the point of the message. The exemption is keyed by RULE, never by case, so a new case
# cannot widen it, and a fragment left off this list, `CLAUDE.md` or `guard.py`, stays forbidden in
# rule 8's reason too.
REASON_MAY_NAME = {
    "subagent-model-cap": (ROOT, slash(ROOT), "settings.json", ".claude"),
}


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


def names_the_target(reason, rule=None):
    """Return the first forbidden fragment the printed reason carries, else ''.

    A fragment listed for the case's RULE in `REASON_MAY_NAME` is permitted. Every other fragment
    is forbidden, whatever the rule.
    """
    permitted = REASON_MAY_NAME.get(rule or "", ())
    for fragment in FORBIDDEN_IN_A_REASON:
        if fragment and fragment not in permitted and fragment in reason:
            return fragment
    return ""


def stack_reason_hygiene_case():
    """CLAUDE.md: "A refusal's printed remedy never names the forbidden target."

    The stack refusal is the one message a worker reads after the harness worktree reminder tells
    it to use the very commands this rule forbids. The message must therefore point somewhere
    else. It may name the two reads, `git stash list` and `git stash show`, because both stay
    allowed. It may not name the action it just refused.
    """
    forbidden = ("pop", "apply", "drop", "clear", "branch")
    problems = []
    for action in forbidden:
        command = VCS + " stash " + action
        if action == "branch":
            command += " lane"
        got, reason = decide({
            "raw": None, "tool": "Bash", "cwd": SUBJSTASH, "session": None,
            "env_path": None, "tool_input": {"command": command},
        })
        if got != "deny":
            problems.append("%s: expected deny, got %s" % (action, got))
            continue
        named = [word for word in forbidden if "stash " + word in reason]
        if named:
            problems.append("%s: the reason names the forbidden action %r" % (action, named[0]))
        for read in ("git stash list", "git stash show"):
            if read not in reason:
                problems.append("%s: the reason does not point at %r" % (action, read))
    if problems:
        return False, "; ".join(problems)
    return True, "five refusals, none naming its own action, all pointing at the two reads"


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


def _load_guard_module():
    """Import GUARD (respecting GUARD_UNDER_TEST) as a module, for a direct unit check.

    Every other case in this file drives the guard as a subprocess, one JSON object on
    stdin. `split_segments` has no JSON-shaped entry point of its own, so this loads the
    file under test directly, the same way `python3 -c "import guard; guard.split_segments(...)"`
    in the bug report does.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("guard_under_test", GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def split_segments_comment_case():
    """A `#` is a comment only where the shell would read it as one.

    MEASURED regression, 2026-09-19: without the comment rule, the `'` in
    `# the driver's shape` opens a quote that runs to end of text, and everything after it
    — including `while true; do sleep 5; done` — collapses into one segment. Rule 1 never
    sees the real command. `guard-shell-selftest.sh`'s runaway-driver fixture went from
    refused to ALLOWED the moment a per-line reader was swapped in ahead of this fix.

    `fix#3` and `'#300'` must stay non-comments: a `#` after a letter, or inside quotes, is
    an ordinary character.
    """
    guard = _load_guard_module()
    problems = []

    got = guard.split_segments("# the driver's shape\nwhile true; do sleep 5; done")
    want = ["", "while true", " do sleep 5", " done"]
    if got != want:
        problems.append("apostrophe-in-comment: got %r want %r" % (got, want))
    if len(got) < 2:
        problems.append(
            "apostrophe-in-comment collapsed to one segment: got %r" % (got,))

    got = guard.split_segments("echo fix#3; ls")
    want = ["echo fix#3", " ls"]
    if got != want:
        problems.append("fix#3 (no quotes): got %r want %r" % (got, want))

    got = guard.split_segments("echo '#300'; ls")
    want = ["echo '#300'", " ls"]
    if got != want:
        problems.append("quoted hash '#300': got %r want %r" % (got, want))

    # A comment at index 0, and one after each of `;`, `|`, `&`, `(`.
    for prefix, sep in (
        ("", ""),
        ("true;", ";"),
        ("true|", "|"),
        ("true&", "&"),
        ("(", "("),
    ):
        cmd = prefix + "# comment after %r" % sep
        got = guard.split_segments(cmd)
        joined = "".join(got)
        if "comment after" in joined:
            problems.append("comment after %r was not dropped: %r" % (sep, got))

    return (not problems), "; ".join(problems) if problems else "comment rule holds"


def process_start_ms_case():
    """`_process_start_ms` must tell apart three outcomes: alive, CONFIRMED dead, and
    unreadable. A regression that folds unreadable back into dead would let a live session's
    worktree look removable, the defect this whole PR fixes.

    The alive check runs on every platform: it only compares against `_real_process_start_ms`,
    which itself has a Windows arm. The dead and unreadable sub-cases below are POSIX-only
    TECHNIQUES, not POSIX-only outcomes: a just-exited pid is reused fast enough on Windows that
    it reads back alive, and faking a broken `ps` on PATH does nothing there, since the Windows
    arm never calls `ps`. Both are skipped on non-POSIX. The Windows arm's own correctness is
    proven separately and deterministically by `process_start_ms_windows_case`, which stubs
    `ctypes.windll` instead of depending on real OS timing.
    """
    guard = _load_guard_module()
    problems = []

    self_pid = os.getpid()
    want_alive = _real_process_start_ms(self_pid)
    got_alive = guard._process_start_ms(self_pid)
    if not isinstance(got_alive, int) or isinstance(got_alive, bool):
        problems.append("alive: did not return an int: %r" % (got_alive,))
    elif abs(got_alive - want_alive) > 2000:
        problems.append("alive: got %r want near %r" % (got_alive, want_alive))

    if os.name == "nt":
        if problems:
            return False, "; ".join(problems)
        return True, (
            "alive read matches; skipped: dead-pid and ps-faking techniques are POSIX-only; "
            "the Windows arm is proven separately by process_start_ms_windows_case"
        )

    # A process this test starts and waits on is CONFIRMED dead the moment `wait()` returns.
    finished = subprocess.Popen([sys.executable, "-c", "pass"])
    finished.wait()
    dead_pid = finished.pid
    got_dead = guard._process_start_ms(dead_pid)
    if got_dead is not None:
        problems.append("dead: got %r want None" % (got_dead,))

    # Unreadable, arm 1: `ps` answers with a nonzero exit code that is NOT 1. That is a read
    # failure, never a death, and must not collapse to the same `None` a confirmed-dead pid gets.
    fake_dir = tempfile.mkdtemp(prefix="fake-ps-bad-exit-")
    old_path = os.environ.get("PATH", "")
    try:
        fake_ps = os.path.join(fake_dir, "ps")
        write(fake_ps, "#!/bin/sh\nexit 2\n")
        os.chmod(fake_ps, 0o755)
        os.environ["PATH"] = fake_dir + os.pathsep + old_path
        got_bad_exit = guard._process_start_ms(self_pid)
    finally:
        os.environ["PATH"] = old_path
        shutil.rmtree(fake_dir, ignore_errors=True)
    if got_bad_exit is not guard.PROCESS_START_UNREADABLE:
        problems.append(
            "unreadable (bad exit code): got %r want PROCESS_START_UNREADABLE" % (got_bad_exit,))

    # Unreadable, arm 2: no `ps` on PATH at all, so the exec itself fails.
    empty_dir = tempfile.mkdtemp(prefix="fake-ps-missing-")
    try:
        os.environ["PATH"] = empty_dir
        got_missing = guard._process_start_ms(self_pid)
    finally:
        os.environ["PATH"] = old_path
        shutil.rmtree(empty_dir, ignore_errors=True)
    if got_missing is not guard.PROCESS_START_UNREADABLE:
        problems.append(
            "unreadable (ps missing): got %r want PROCESS_START_UNREADABLE" % (got_missing,))

    return (not problems), "; ".join(problems) if problems else "alive/dead/unreadable read apart"


def _fake_kernel32(open_process_result, get_last_error=0, get_process_times_ok=True,
                    creation_high=0, creation_low=0):
    """A stand-in for `ctypes.windll.kernel32`, built the same way `make_blind_git` stands in
    for a real `git`: the real target (Windows) is unavailable on this machine, so the CALL
    SURFACE is stubbed instead, which still drives the Windows arm's own branching logic."""
    closed = []

    class Kernel32:
        def OpenProcess(self, access, inherit, pid):
            return open_process_result

        def GetProcessTimes(self, handle, creation_ref, exit_ref, kernel_ref, user_ref):
            if not get_process_times_ok:
                return 0
            import ctypes
            import ctypes.wintypes
            ptr = ctypes.cast(creation_ref, ctypes.POINTER(ctypes.wintypes.FILETIME))
            ptr.contents.dwHighDateTime = creation_high
            ptr.contents.dwLowDateTime = creation_low
            return 1

        def CloseHandle(self, handle):
            closed.append(handle)
            return 1

    class Windll:
        kernel32 = Kernel32()

    return Windll(), closed, (lambda: get_last_error)


def process_start_ms_windows_case():
    """Drive `_process_start_ms_windows`'s own branches with a stubbed `ctypes.windll`, since
    this machine has no real kernel32. A NULL handle with error 87 (no such process) reads as
    CONFIRMED dead. A NULL handle with error 5 (access denied) reads as unreadable, never as
    dead. A valid handle's FILETIME converts to the same epoch millisecond the formula in the
    code names.
    """
    import ctypes

    guard = _load_guard_module()
    problems = []
    real_windll = getattr(ctypes, "windll", None)
    real_get_last_error = getattr(ctypes, "GetLastError", None)

    def run(open_result, error, times_ok=True, high=0, low=0):
        fake_windll, closed, get_last_error = _fake_kernel32(
            open_result, error, times_ok, high, low)
        ctypes.windll = fake_windll
        ctypes.GetLastError = get_last_error
        try:
            return guard._process_start_ms_windows(4321), closed
        finally:
            if real_windll is None:
                del ctypes.windll
            else:
                ctypes.windll = real_windll
            if real_get_last_error is None:
                del ctypes.GetLastError
            else:
                ctypes.GetLastError = real_get_last_error

    # error 87, ERROR_INVALID_PARAMETER: no such process at all -> CONFIRMED dead.
    got, closed = run(open_result=0, error=87)
    if got is not None:
        problems.append("windows dead (error 87): got %r want None" % (got,))
    if closed:
        problems.append("windows dead (error 87): CloseHandle called on a NULL handle")

    # error 5, ERROR_ACCESS_DENIED: the process exists, but this read cannot see into it.
    got, closed = run(open_result=0, error=5)
    if got is not guard.PROCESS_START_UNREADABLE:
        problems.append(
            "windows access-denied (error 5): got %r want PROCESS_START_UNREADABLE" % (got,))

    # A valid handle: 10,000 100ns ticks past the epoch-zero FILETIME (1601-01-01 UTC) is one
    # millisecond past that same instant, so this converts to epoch millisecond 1.
    ticks = 11644473600000 * 10000 + 10000
    high = (ticks >> 32) & 0xFFFFFFFF
    low = ticks & 0xFFFFFFFF
    got, closed = run(open_result=99, error=0, times_ok=True, high=high, low=low)
    if got != 1:
        problems.append("windows alive: FILETIME converted to %r want %r" % (got, 1))
    if not closed:
        problems.append("windows alive: CloseHandle was never called on the valid handle")

    return (not problems), "; ".join(problems) if problems else "windows arm splits dead/unreadable/alive"


def session_is_live_case():
    """`session_is_live` must carry `_process_start_ms`'s three states through as True, False,
    and None, never coercing the unreadable third state into False. The module's own
    `_process_start_ms` is stubbed here so this case proves `session_is_live`'s own wiring, not
    a real process's real state.
    """
    guard = _load_guard_module()
    problems = []
    record = {"pid": 4321, "startedAt": 1_000_000}

    guard._process_start_ms = lambda pid: 1_000_000
    live = guard.session_is_live(record)
    if live is not True:
        problems.append("live: got %r want True" % (live,))

    guard._process_start_ms = lambda pid: None
    dead = guard.session_is_live(record)
    if dead is not False:
        problems.append("dead: got %r want False" % (dead,))

    guard._process_start_ms = lambda pid: guard.PROCESS_START_UNREADABLE
    try:
        unreadable = guard.session_is_live(record)
    except Exception as e:
        problems.append(
            "unreadable: session_is_live raised %r instead of answering None (not False)" % (e,))
    else:
        if unreadable is not None:
            problems.append("unreadable: got %r want None (not False)" % (unreadable,))

    return (not problems), "; ".join(problems) if problems else "session_is_live carries all three states"


def worktree_live_session_unreadable_case():
    """`worktree_live_session` must answer None, not False, when a record's cwd sits under
    TARGET but that record's own liveness read is unreadable, and no OTHER record under TARGET
    is confirmed live. Returning False here would make an unreadable-but-maybe-live session's
    worktree look removable to `worktree_remove_subject` and `janitor/sweep.py`'s
    `decide_worktree`, both of which already keep on None.
    """
    guard = _load_guard_module()
    problems = []
    target = tempfile.mkdtemp(prefix="wt-live-unreadable-")
    try:
        guard.session_records = lambda: [{"pid": 1, "startedAt": 1, "cwd": target}]
        guard.session_is_live = lambda record: None
        got = guard.worktree_live_session(target)
        if got is not None:
            problems.append(
                "unreadable record under target: got %r want None, not False" % (got,))
    finally:
        shutil.rmtree(target, ignore_errors=True)

    return (not problems), "; ".join(problems) if problems else "unreadable record propagates as None"


def worktree_live_session_two_spellings_case():
    """A live session's cwd and TARGET can name one physical directory in two strings that
    `os.path.normcase(os.path.realpath(...))` never makes equal. MEASURED by hand on this
    machine: mapping drive `T:` to `\\\\localhost\\c$` left `os.path.realpath` naming the UNC
    path for one spelling and the local `C:\\...` path for the other -- they never compared
    equal as strings -- while `os.stat` gave both the identical `(st_dev, st_ino)`. That is the
    exact split a Windows `subst` drive or a mapped network drive can produce against the
    worktree path `janitor/sweep.py` hands the sweep.

    This case does not depend on that mapped drive existing on whatever machine runs the
    suite (loopback SMB sharing is not guaranteed on every CI image), so it simulates the same
    split at the `_path_identity` seam instead: two genuinely different temp directories stand
    in for the two spellings, and `_path_identity` is stubbed to answer as if they were one
    file. That proves `worktree_live_session` FOLDS a matching identity into "under target" and
    returns True for a live session there. It does NOT re-prove that `os.stat` truly agrees
    across every real subst/mapped-drive pair on every Windows build -- that half was checked
    against the real mapped drive above, not by this automated case.
    """
    guard = _load_guard_module()
    problems = []
    target = tempfile.mkdtemp(prefix="wt-live-target-")
    other_spelling = tempfile.mkdtemp(prefix="wt-live-other-spelling-")
    real_identity = guard._path_identity
    try:
        guard.session_records = lambda: [{"pid": 1, "startedAt": 1, "cwd": other_spelling}]
        guard.session_is_live = lambda record: True
        target_resolved = os.path.realpath(target)
        other_resolved = os.path.realpath(other_spelling)
        shared = ("same-underlying-file",)

        def fake_identity(path):
            if path in (target_resolved, other_resolved):
                return shared
            return real_identity(path)

        guard._path_identity = fake_identity
        got = guard.worktree_live_session(target)
        if got is not True:
            problems.append(
                "two spellings, one identity, live session: got %r want True" % (got,))
    finally:
        guard._path_identity = real_identity
        shutil.rmtree(target, ignore_errors=True)
        shutil.rmtree(other_spelling, ignore_errors=True)

    return (not problems), "; ".join(problems) if problems else "matching identity is under target"


def worktree_live_session_path_unresolvable_case():
    """When the string spellings differ AND the identity fallback itself cannot tell (target's
    own identity is unreadable), the record must count as unresolvable, never as "not under
    target." Folding it into "not under" would let a live session's worktree, reached through a
    spelling `realpath` never collapses, look removable. Keep is the safe direction, so the
    answer must be None, not False.
    """
    guard = _load_guard_module()
    problems = []
    target = tempfile.mkdtemp(prefix="wt-live-target-unresolvable-")
    other_spelling = tempfile.mkdtemp(prefix="wt-live-other-unresolvable-")
    real_identity = guard._path_identity
    try:
        guard.session_records = lambda: [{"pid": 1, "startedAt": 1, "cwd": other_spelling}]
        guard.session_is_live = lambda record: True  # must not even matter: identity is unresolvable
        guard._path_identity = lambda path: None
        got = guard.worktree_live_session(target)
        if got is not None:
            problems.append(
                "identity unresolvable, differing spellings: got %r want None, not False" % (got,))
    finally:
        guard._path_identity = real_identity
        shutil.rmtree(target, ignore_errors=True)
        shutil.rmtree(other_spelling, ignore_errors=True)

    return (not problems), "; ".join(problems) if problems else "unresolvable identity propagates as None"


def session_is_live_backwards_clock_step_case():
    """A backwards clock step landing between the two ORIGINAL measurements (the kernel's own
    process-creation FILETIME, fixed forever once recorded, and the record's `startedAt`,
    written 1.7-3.2s later by `Date.now()`) can leave `actual` (read now) more than the
    tolerance AHEAD of `started`. That is also the recycled-pid signature (a new process at
    this pid, created well after the old record's startedAt) -- the two are indistinguishable
    from this reading alone. `session_is_live` must answer None (cannot tell), never False
    (confirmed dead), for that direction, because a confident False here is exactly what let a
    genuinely live, clock-glitched session get reaped. The opposite direction (`started` far
    AHEAD of `actual`, which no legitimate same-process reading ever produces, since `started`
    is always written strictly after `actual`) stays a confident False, unchanged.
    """
    guard = _load_guard_module()
    problems = []
    record = {"pid": 4321, "startedAt": 1_000_000}

    # actual is 5 minutes AFTER started: the ambiguous, must-not-be-confident-False direction.
    guard._process_start_ms = lambda pid: 1_000_000 + 300_000
    implied_backwards = guard.session_is_live(record)
    if implied_backwards is not None:
        problems.append(
            "actual far ahead of started (implies a backwards step): got %r want None" % (
                implied_backwards,))

    # actual is 5 minutes BEFORE started: never produced by the same live process, stays False.
    guard._process_start_ms = lambda pid: 1_000_000 - 300_000
    still_dead = guard.session_is_live(record)
    if still_dead is not False:
        problems.append(
            "actual far behind started: got %r want False (unchanged)" % (still_dead,))

    # within tolerance, either side: unaffected by the fix.
    guard._process_start_ms = lambda pid: 1_000_000 + 2_000
    within = guard.session_is_live(record)
    if within is not True:
        problems.append("within tolerance: got %r want True (unaffected)" % (within,))

    return (not problems), "; ".join(problems) if problems else "backwards-step direction reads unreadable"


# The checkers that read the log. THE COUNT IS READ FROM THIS LIST, never written beside it: a
# literal count drifts the moment a case is added, and a suite that miscounts its own cases is a
# suite a reader stops trusting.
LOG_CHECKS = (
    ("log: one line per refusal and none for an allow", log_case),
    ("log: the refused file is named in the log and nowhere else", log_env_case),
    ("log: a project config edit is allowed and noted", config_edit_log_case),
    ("log: a cap lift is asked and logged with its file and value", cap_log_case),
    ("log: a cap lift under a deep path still logs the model", cap_deep_path_log_case),
    ("cap: the printed reason is bounded, single-line and marks a cut", cap_reason_bound_case),
    ("log: a merge into main is allowed and noted where the base is unsafe", merge_log_case),
    ("log: a conflict-side checkout is allowed and noted", conflict_resolve_log_case),
    ("log: an unreadable subject is allowed and noted", subject_unread_log_case),
    ("log: a branch delete with no resolvable base is allowed and noted",
     branch_base_unread_log_case),
    ("stack: the refusal never names the action it refused", stack_reason_hygiene_case),
    ("split_segments: a comment starting a word ends its line, "
     "letter-before-# and quoted-# stay literal", split_segments_comment_case),
    ("liveness: process_start_ms splits alive/dead/unreadable apart", process_start_ms_case),
    ("liveness: windows arm splits dead (error 87) from unreadable (error 5)",
     process_start_ms_windows_case),
    ("liveness: session_is_live carries True/False/None, never coercing unreadable to False",
     session_is_live_case),
    ("liveness: worktree_live_session answers None on an unreadable record under target",
     worktree_live_session_unreadable_case),
    ("liveness: worktree_live_session matches two spellings of one identity as under target",
     worktree_live_session_two_spellings_case),
    ("liveness: worktree_live_session answers None when the identity fallback can't tell",
     worktree_live_session_path_unresolvable_case),
    ("liveness: session_is_live reads an implied backwards clock step as unreadable, not dead",
     session_is_live_backwards_clock_step_case),
)


def main():
    total = len(CASES) + len(LOG_CHECKS)
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
        elif ok and case["carries"] and [f for f in case["carries"] if f not in reason]:
            ok = False
            note = "  (the reason does not carry %r: %s)" % (
                [f for f in case["carries"] if f not in reason][0], reason[:90])
        elif ok and got != "allow" and names_the_target(reason, case["rule"]):
            ok = False
            note = "  (the reason names the forbidden target %r)" % names_the_target(
                reason, case["rule"])
        elif not ok:
            note = "  (%s)" % reason[:110] if reason else ""
        failed += 0 if ok else 1
        print("%s  %-6s(want %-6s)  [%-11s] %s%s" % (
            "PASS" if ok else "FAIL", got, case["expected"], case["tool"], case["name"], note))
    for label, checker in LOG_CHECKS:
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
