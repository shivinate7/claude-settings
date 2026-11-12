# section 4863
FAMILY = "git-after-cd"

# A FAILED TEST, THEN A SKIPPED CD. The && cd never runs when its test fails, so the push after ; runs in the folder
# the first failed cd left the shell in. Under set -e the cd reads as a bare failure that ends the shell, so the walk
# clears the stranding. bash does not exit there: the && list is not the last command, so errexit ignores it.
# Each form is checked under bash with a stub git and missing folders: the push runs in the stranded folder.
AFTER_CD_GONE = slash(os.path.join(ROOT, "after-cd-gone"))          # a folder no fixture makes

AFTER_CD_GONE_TWO = slash(os.path.join(ROOT, "after-cd-gone-two"))  # a second folder no fixture makes

sh("git-after-cd: set -e, a failed cd on the left of ||, then a failed && test and a && cd to a missing folder, then ; a git push is refused",
   "set -e; cd %s || true; [ -d %s ] && cd %s; %s push" % (AFTER_CD_GONE, AFTER_CD_GONE, AFTER_CD_GONE_TWO, VCS),
   "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

# The green control: without set -e the stranding carries through the skipped cd, so the push is refused too.
sh("git-after-cd: a failed cd on the left of ||, then a failed && test and a && cd to a missing folder, then ; a git push is refused",
   "cd %s || true; [ -d %s ] && cd %s; %s push" % (AFTER_CD_GONE, AFTER_CD_GONE, AFTER_CD_GONE_TWO, VCS),
   "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

# `}2` is no closer in bash: it is a command word, so the brace group stays open to the last }. The cd and the push
# then run inside a group on the left of ||, where errexit is ignored, and the push runs in the stranded folder.
sh("git-after-cd: set -e, a brace group closed by a }2>x word that is no closer, then a failed cd, then ; a git push inside the group on the left of || is refused",
   "set -e; { true; }2>x; cd %s; %s push; } || true" % (AFTER_CD_GONE, VCS), "deny", "git-after-cd", cwd=NOGIT,
   carries=("&&", "-C"))

# A CD THAT MAY NEVER RUN. After || or && a cd runs only when the left side lets it, so the walk must not read it as
# the shell's exit, even under set -e: the right side may be skipped, and the push after ; then runs in the stranded
# folder. Each form starts with a failed cd, so a stranding exists. Each is checked under bash with a stub git.
sh("git-after-cd: set -e, a failed cd on the left of ||, then a failed && test and a && cd to a second missing folder, then ; a git push is refused",
   "set -e; cd %s || true; [ -d %s ] && cd %s; %s push" % (AFTER_CD_GONE, AFTER_CD_GONE_TWO, AFTER_CD_GONE_TWO, VCS),
   "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

sh("git-after-cd: set -e, a failed cd on the left of ||, then a true || cd to a missing folder that is skipped, then ; a git push is refused",
   "set -e; cd %s || true; true || cd %s; %s push" % (AFTER_CD_GONE, AFTER_CD_GONE_TWO, VCS),
   "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

sh("git-after-cd: a failed cd, then a true || if ! cd to a missing folder then exit, whose body is skipped, then ; a git push is refused",
   "cd %s; true || if ! cd %s; then exit 1; fi; %s push" % (AFTER_CD_GONE, AFTER_CD_GONE_TWO, VCS),
   "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

# THE FALSE ALARM OF THE SKIPPED CD. A cd after && that its test never lets run is no stranding: the shell stays in
# the folder the landed cd named, so the push after ; runs there. Each form is checked under bash with a stub git.
sh("git-after-cd: a cd that lands, then a && test that fails, then a && cd to a missing folder, then ; a git push, passes, the skipped cd leaves the shell in the landed folder",
   "cd %s && [ -d %s ] && cd %s; %s push" % (slash(NOGIT), AFTER_CD_GONE_TWO, AFTER_CD_GONE_TWO, VCS), "allow", cwd=NOGIT)

sh("git-after-cd: set -e, a cd that lands, then a && test that fails, then a && cd to a missing folder, then ; a git push, passes, errexit ignores the && list",
   "set -e; cd %s && [ -d %s ] && cd %s; %s push" % (slash(NOGIT), AFTER_CD_GONE_TWO, AFTER_CD_GONE_TWO, VCS), "allow", cwd=NOGIT)

sh("git-after-cd: a cd that lands, then ; a && test that fails before a && cd to a missing folder, then ; a git push, passes, the skipped cd leaves the shell in the landed folder",
   "cd %s; [ -d %s ] && cd %s; %s push" % (slash(NOGIT), AFTER_CD_GONE_TWO, AFTER_CD_GONE_TWO, VCS), "allow", cwd=NOGIT)

sh("git-after-cd: set -e, a cd that lands, then ; a && test that fails before a && cd to a missing folder, then ; a git push, passes, errexit ignores the && list",
   "set -e; cd %s; [ -d %s ] && cd %s; %s push" % (slash(NOGIT), AFTER_CD_GONE_TWO, AFTER_CD_GONE_TWO, VCS), "allow", cwd=NOGIT)

# THE DIRECTORY TEST BY ITS SHAPE. `[ -d M ]`, `[[ -d M ]]` and `test -d M` each joined to a cd to M by && is a test
# that fails when M is missing, so the cd never runs and the push after ; runs where the shell is. The word matches
# after quote removal, so `test -d "M"` counts too. Each form is checked under bash with a stub git.
sh("git-after-cd: a [ -d M ] test that fails, then && cd to a missing folder, then ; a git push, passes, the cd never runs",
   "[ -d %s ] && cd %s; %s push" % (AFTER_CD_GONE_TWO, AFTER_CD_GONE_TWO, VCS), "allow", cwd=NOGIT)

sh("git-after-cd: a [[ -d M ]] test that fails, then && cd to a missing folder, then ; a git push, passes, the cd never runs",
   "[[ -d %s ]] && cd %s; %s push" % (AFTER_CD_GONE_TWO, AFTER_CD_GONE_TWO, VCS), "allow", cwd=NOGIT)

sh("git-after-cd: a test -d M that fails, then && cd to a missing folder, then ; a git push, passes, the cd never runs",
   "test -d %s && cd %s; %s push" % (AFTER_CD_GONE_TWO, AFTER_CD_GONE_TWO, VCS), "allow", cwd=NOGIT)

sh('git-after-cd: a quoted test word that fails, then && cd to the same word, then ; a git push, passes, the words match after quote removal',
   'test -d "%s" && cd %s; %s push' % (AFTER_CD_GONE_TWO, AFTER_CD_GONE_TWO, VCS), "allow", cwd=NOGIT)

# The test must head its && list. After && true || the test may be skipped, so the cd behind it is judged as before:
# here the cd runs, fails, and the push after ; runs in the folder the first cd landed in.
sh("git-after-cd: a cd that lands, then && true || a test that may be skipped, then && cd to a missing folder, then ; a git push is refused",
   "cd %s && true || [ -d %s ] && cd %s; %s push" % (slash(NOGIT), AFTER_CD_GONE_TWO, AFTER_CD_GONE_TWO, VCS),
   "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

# THE REFUSAL BRANCHES. _never_runs and _dir_test_word refuse three forms that a skipped cd could pass for. Each form
# is refused only because one branch holds: drop that branch and the form is allowed. Each is checked under bash with
# a stub git. A regular file for M makes -e pass and the cd fail. The push then runs in the start folder.
sh("git-after-cd: a [ -d M ] test joined by ; to a cd to a missing folder, then ; a git push is refused",
   "[ -d %s ]; cd %s; %s push" % (AFTER_CD_GONE_TWO, AFTER_CD_GONE_TWO, VCS),
   "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

sh("git-after-cd: a [ -e M ] test, then && cd to M, then ; a git push is refused",
   "[ -e %s ] && cd %s; %s push" % (AFTER_CD_GONE_TWO, AFTER_CD_GONE_TWO, VCS),
   "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

sh("git-after-cd: a [ -d N ] test on a folder that exists, then && cd to a missing folder, then ; a git push is refused",
   "[ -d %s ] && cd %s; %s push" % (slash(NOGIT), AFTER_CD_GONE_TWO, VCS),
   "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

def planted_cd_walk_guards(folder):
    """The shared step of the crash checks: an intact and a planted copy of the guard family under `folder`.
    The planted copy raises at cd_walk's try on a read with failed_cd_stays, the one read a crash reads as
    stranded. Returns (guards, "") or (None, the cause) when the try block does not occur once: no plant."""
    guards = {}
    for name in ("intact", "planted"):
        hooks = os.path.join(folder, name, "hooks")
        os.makedirs(hooks)
        copy_guard_family(hooks)
        guards[name] = os.path.join(hooks, "guard.py")
    core = os.path.join(folder, "planted", "hooks", "guard_core.py")
    with open(core, encoding="utf-8") as handle:
        text = handle.read()
    if text.count(CD_WALK_TRY) != 1:
        return None, "the cd_walk try block occurs %d times in guard_core.py, want once: no plant" % text.count(CD_WALK_TRY)
    write(core, text.replace(CD_WALK_TRY, CD_WALK_PLANTED, 1))
    return guards, ""

def planted_verdict(guards, folder, name, command, cwd):
    """(decision, reason, log text) that the `name` copy gives one Bash command run from `cwd`."""
    cfg = os.path.join(folder, name, "cfg")
    env = dict(os.environ)
    for var in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_REMOTE_SESSION_ID", "CLAUDE_PROJECT_DIR",
                "CLAUDE_CODE_REMOTE"):
        env.pop(var, None)
    env["CLAUDE_CONFIG_DIR"] = cfg
    payload = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd}
    run = subprocess.run([sys.executable, guards[name]], input=json.dumps(payload), capture_output=True,
                         text=True, env=env, timeout=120)
    out = run.stdout.strip()
    spec = json.loads(out).get("hookSpecificOutput", {}) if out else {}
    log = os.path.join(cfg, "guard.log")
    logged = ""
    if os.path.exists(log):
        with open(log, encoding="utf-8") as handle:
            logged = handle.read()
    return (spec.get("permissionDecision", "allow") if out else "allow",
            spec.get("permissionDecisionReason", ""), logged)
