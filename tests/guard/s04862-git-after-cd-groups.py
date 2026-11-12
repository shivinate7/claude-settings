# section 4862
FAMILY = "git-after-cd"

# Coverage: with spaces, the exit is the second word of its ( ) group, so only the subshell reading stops it
# from counting as the shell's exit. The unspaced form tokenizes as `(exit`, which is no exit at all.
sh("git-after-cd: a cd into a missing folder, then || ( exit 1 ) with spaces, then ; a git push is refused",
   "cd /tmp/w || ( exit 1 ); %s push" % VCS, "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

# A failed cd under && skips the group, loop or if body it heads: bash runs no git write in them, with the
# folder missing and git stubbed. A `;` after the group ends reopens the stranded folder, so the push refuses.
sh("git-after-cd: a failed cd, then && a brace group of git writes, passes",
   "cd /tmp/w && { %s add -A; %s commit -m m; }" % (VCS, VCS), "allow", cwd=NOGIT)

sh("git-after-cd: a failed cd, then && a brace group of git writes across newlines, passes",
   "cd /tmp/w && {\n%s add -A\n%s commit -m m\n}" % (VCS, VCS), "allow", cwd=NOGIT)

sh("git-after-cd: a failed cd, then && an if whose then branch pushes, passes",
   "cd /tmp/w && if true; then %s push; fi" % VCS, "allow", cwd=NOGIT)

sh("git-after-cd: a failed cd, then && a for loop that pushes, passes",
   "cd /tmp/w && for b in a; do %s push; done" % VCS, "allow", cwd=NOGIT)

# `while false` never runs its body, so no push runs in any folder, and `; true` ends the call.
sh("git-after-cd: a failed cd, then && a while loop whose body never runs, then ; true, passes",
   "cd /tmp/w && while false; do %s push; done; true" % VCS, "allow", cwd=NOGIT)

sh("git-after-cd: a failed cd, then && a brace group of git writes, then ; a git push is refused",
   "cd /tmp/w && { %s add -A; %s commit -m m; }; %s push" % (VCS, VCS, VCS), "deny", "git-after-cd",
   cwd=NOGIT, carries=("&&", "-C"))

# `if !` turns the failed cd into a passing test, so exit 1 runs and the shell stops before the push.
sh("git-after-cd: an if test that is a negated failed cd, then exit 1, then a git push, passes",
   "if ! cd /tmp/w; then exit 1; fi; %s push" % VCS, "allow", cwd=NOGIT)

# set -e stops the shell at the failed cd, so the push after ; never runs.
sh("git-after-cd: set -e, then a failed cd, then ; a git push, passes, the shell exits first",
   "set -e; cd /tmp/w; %s push" % VCS, "allow", cwd=NOGIT)

sh("git-after-cd: set -e on its own line, then a failed cd, then ; a git push, passes, the shell exits first",
   "set -e\ncd /tmp/w; %s push" % VCS, "allow", cwd=NOGIT)

# set +e turns the exit off again, so the failed cd leaves the shell running and the push after ; runs.
sh("git-after-cd: set -e then set +e, then a failed cd, then ; a git push is refused",
   "set -e; set +e; cd /tmp/w; %s push" % VCS, "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

# A failed cd skips the whole group, loop or nested group it heads, and the push after ; runs stranded.
# Each command below is checked under bash with a stub git and a missing folder: the push runs.
sh("git-after-cd: a failed cd, then && a brace group holding a for loop of git adds, then ; a git push is refused",
   'cd /tmp/w && { for f in a; do %s add "$f"; done }; %s push' % (VCS, VCS), "deny", "git-after-cd",
   cwd=NOGIT, carries=("&&", "-C"))

sh("git-after-cd: a failed cd, then && a brace group of a git add with a redirect, then ; a git push is refused",
   "cd /tmp/w && { %s add -A; }>/dev/null; %s push" % (VCS, VCS), "deny", "git-after-cd",
   cwd=NOGIT, carries=("&&", "-C"))

sh("git-after-cd: a failed cd, then && a for loop with a redirect, then ; a git push is refused",
   "cd /tmp/w && for f in a; do :; done>/dev/null; %s push" % VCS, "deny", "git-after-cd",
   cwd=NOGIT, carries=("&&", "-C"))

sh("git-after-cd: a failed cd, then && nested brace groups of a git add, then ; a git push is refused",
   "cd /tmp/w && { { %s add -A; } }; %s push" % (VCS, VCS), "deny", "git-after-cd",
   cwd=NOGIT, carries=("&&", "-C"))

# A set +e inside a group or an if still turns the exit off, so the failed cd leaves the shell running.
sh("git-after-cd: set -e, then a set +e inside an if, then a failed cd, then ; a git push is refused",
   "set -e; if true; then set +e; fi; cd /tmp/w; %s push" % VCS, "deny", "git-after-cd",
   cwd=NOGIT, carries=("&&", "-C"))

sh("git-after-cd: set -e, then a set +e inside a brace group, then a failed cd, then ; a git push is refused",
   "set -e; { set +e; }; cd /tmp/w; %s push" % VCS, "deny", "git-after-cd",
   cwd=NOGIT, carries=("&&", "-C"))

# A set -e in a function that is never called does not turn the exit on.
sh("git-after-cd: a set -e in a function never called, then a failed cd, then ; a git push is refused",
   "f() { set -e; }; cd /tmp/w; %s push" % VCS, "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

# A set -e behind a test that fails never runs, so the failed cd leaves the shell running.
sh("git-after-cd: a set -e behind a failing test, then a failed cd, then ; a git push is refused",
   '[ -n "$CI" ] && set -e; cd /tmp/w; %s push' % VCS, "deny", "git-after-cd", cwd=NOGIT,
   carries=("&&", "-C"))

# A set with an empty argument once raised IndexError in the errexit read, and the guard failed open.
sh("git-after-cd: set with an empty argument, then a failed cd, then ; a git push is refused",
   'set -- ""; cd /tmp/w; %s push' % VCS, "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

# THE GROUP GATE. Under set -e a failed cd ends the shell, except in a brace group or an if body that is the
# left side of ||: bash ignores errexit there, so the push after the cd runs in the stranded folder.
sh("git-after-cd: set -e, then a failed cd in a brace group on the left of ||, then ; a git push is refused",
   "set -e; { true; cd /tmp/w; %s push; } || true" % VCS, "deny", "git-after-cd", cwd=NOGIT,
   carries=("&&", "-C"))

sh("git-after-cd: set -e, then a failed cd in an if body on the left of ||, then ; a git push is refused",
   "set -e; if true; then :; cd /tmp/w; %s push; fi || true" % VCS, "deny", "git-after-cd", cwd=NOGIT,
   carries=("&&", "-C"))

# THE CLOSER READ. A closer with an attached redirect still closes its group, so the cd after it is bare under
# set -e and the shell exits there. Each form below is valid bash, and each shell exits before the push.
sh("git-after-cd: set -e, then a brace group closed by an attached > redirect, then a failed cd, then ; a git push, passes, the shell exits first",
   "set -e; { true; }>/dev/null\ncd /tmp/w; %s push" % VCS, "allow", cwd=NOGIT)

sh("git-after-cd: set -e, then a for loop closed by an attached >> redirect, then a failed cd, then ; a git push, passes, the shell exits first",
   "set -e; for f in a; do :; done>>/dev/null\ncd /tmp/w; %s push" % VCS, "allow", cwd=NOGIT)

sh("git-after-cd: set -e, then a brace group closed by an attached &> redirect, then a failed cd, then ; a git push, passes, the shell exits first",
   "set -e; { true; }&>/dev/null\ncd /tmp/w; %s push" % VCS, "allow", cwd=NOGIT)

sh("git-after-cd: set -e, then an if closed by fi, then a failed cd, then ; a git push, passes, the shell exits first",
   "set -e; if true; then :; fi\ncd /tmp/w; %s push" % VCS, "allow", cwd=NOGIT)

sh("git-after-cd: set -e, then a case closed by esac, then a failed cd, then ; a git push, passes, the shell exits first",
   "set -e; case x in x) :;; esac\ncd /tmp/w; %s push" % VCS, "allow", cwd=NOGIT)

# A quoted } and a word done_x are words, not closers. Each is the command word of its segment, which is the
# only place a closer is read, so the group stays open and the push after the failed cd runs before || true.
sh("git-after-cd: set -e, a quoted } as a command in a brace group on the left of ||, then a failed cd, then ; a git push is refused",
   'set -e; { true; "}"; cd /tmp/w; %s push; } || true' % VCS, "deny", "git-after-cd", cwd=NOGIT,
   carries=("&&", "-C"))

sh("git-after-cd: set -e, a word done_x as a command in a brace group on the left of ||, then a failed cd, then ; a git push is refused",
   "set -e; { true; done_x; cd /tmp/w; %s push; } || true" % VCS, "deny", "git-after-cd", cwd=NOGIT,
   carries=("&&", "-C"))

# THE WIDE READ. case, select and a function definition open a compound that errexit must see, so the cd in
# their body is not bare. Each body is on the left of ||, so errexit is ignored there and the push runs. A select
# body runs once its menu gets an answer, so it is judged as a body that may run.
sh("git-after-cd: set -e, a failed cd in a case body on the left of ||, then ; a git push is refused",
   "set -e; case x in x)\n cd /tmp/w\n %s push\n;; esac || true" % VCS, "deny", "git-after-cd",
   cwd=NOGIT, carries=("&&", "-C"))

sh("git-after-cd: set -e, a failed cd in a select body on the left of ||, then a git push is refused",
   "set -e; select x in a\ndo\n cd /tmp/w\n %s push\ndone || true" % VCS, "deny", "git-after-cd",
   cwd=NOGIT, carries=("&&", "-C"))

sh("git-after-cd: set -e, a failed cd in a function keyword body called on the left of ||, then a git push is refused",
   "set -e; function f {\n cd /tmp/w\n %s push\n}\nf || true" % VCS, "deny", "git-after-cd",
   cwd=NOGIT, carries=("&&", "-C"))

sh("git-after-cd: set -e, a failed cd in a f() body called on the left of ||, then a git push is refused",
   "set -e; f() {\n cd /tmp/w\n %s push\n}\nf || true" % VCS, "deny", "git-after-cd",
   cwd=NOGIT, carries=("&&", "-C"))

sh("git-after-cd: set -e, a failed cd in a f(){ body called on the left of ||, then a git push is refused",
   "set -e; f(){\n cd /tmp/w\n %s push\n}\nf || true" % VCS, "deny", "git-after-cd",
   cwd=NOGIT, carries=("&&", "-C"))

sh("git-after-cd: set -e, a failed cd in a f () body called on the left of ||, then a git push is refused",
   "set -e; f () {\n cd /tmp/w\n %s push\n}\nf || true" % VCS, "deny", "git-after-cd",
   cwd=NOGIT, carries=("&&", "-C"))

# THE ERREXIT READ. `--` ends the options, so the -e after it is a word and set turns nothing on.
sh("git-after-cd: set -- -e, then a failed cd, then ; a git push is refused",
   "set -- -e; cd /tmp/w; %s push" % VCS, "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

# An empty word ends the options too, so the +e after it is a word: errexit stays on and the cd ends the shell.
sh("git-after-cd: set with an empty word, then +e, then a failed cd, then ; a git push, passes, the shell exits first",
   'set -e; set "" +e; cd /tmp/w; %s push' % VCS, "allow", cwd=NOGIT)

# A plain word ends the options, so the -e after it is a positional word and errexit is not turned on.
sh("git-after-cd: set with a plain word, then -e, then a failed cd, then ; a git push is refused",
   "set bar -e; cd /tmp/w; %s push" % VCS, "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

# -o takes the next word as an option name: errexit is named by the long form, and -e after the name still counts.
sh("git-after-cd: set -o errexit, then a failed cd, then ; a git push, passes, the shell exits first",
   "set -o errexit; cd /tmp/w; %s push" % VCS, "allow", cwd=NOGIT)

sh("git-after-cd: set -o pipefail -e, then a failed cd, then ; a git push, passes, the shell exits first",
   "set -o pipefail -e; cd /tmp/w; %s push" % VCS, "allow", cwd=NOGIT)

# A set is read only as the first word of its segment, so echo's argument turns nothing on.
sh("git-after-cd: echo set -e, then a failed cd, then ; a git push is refused",
   "echo set -e; cd /tmp/w; %s push" % VCS, "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

# A set -e inside a subshell ends with the subshell, so the shell's own errexit stays off.
sh("git-after-cd: a set -e in a subshell, then a failed cd, then ; a git push is refused",
   "(set -e); cd /tmp/w; %s push" % VCS, "deny", "git-after-cd", cwd=NOGIT, carries=("&&", "-C"))

# A CRASH IN THE CD WALK. The walk runs inside cd_walk's try, and a raise there must read as stranded: the
# git-after-cd rule refuses the push after the cd, and the crash is logged as a guard crash. The planted copy
# raises at that try. The intact copy, on the same landing cd, is the control, so the refusal can only come
# from the crash path. Each failure names one cause.
GIT_AFTER_CD_CRASH_LABEL = ("git-after-cd: a crash in the cd walk reads as stranded, so the push after a cd that "
                            "lands is refused, and the crash is logged")

CD_WALK_TRY = "    try:\n        return _walk_segments(segments, number, shell_cwd, ends, failed_cd_stays)\n"

CD_WALK_PLANTED = ("    try:\n        if failed_cd_stays:\n            raise RuntimeError(\"planted walk fault\")\n"
                   "        return _walk_segments(segments, number, shell_cwd, ends, failed_cd_stays)\n")

def git_after_cd_crash_check():
    folder = os.path.join(ROOT, "after-cd-crash")
    shutil.rmtree(folder, ignore_errors=True)
    landing = os.path.join(folder, "landing")
    os.makedirs(landing)
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
        return False, "the cd_walk try block occurs %d times in guard_core.py, want once: no plant" % text.count(CD_WALK_TRY)
    write(core, text.replace(CD_WALK_TRY, CD_WALK_PLANTED, 1))
    command = "cd %s; %s push" % (slash(landing), VCS)

    def verdict(name):
        cfg = os.path.join(folder, name, "cfg")
        env = dict(os.environ)
        for var in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_REMOTE_SESSION_ID", "CLAUDE_PROJECT_DIR",
                    "CLAUDE_CODE_REMOTE"):
            env.pop(var, None)
        env["CLAUDE_CONFIG_DIR"] = cfg
        payload = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": landing}
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

    control, _reason, _log = verdict("intact")
    if control != "allow":
        return False, "control: the intact copy's verdict on the landing cd is %r, want allow" % control
    decision, reason, logged = verdict("planted")
    if decision != "deny":
        return False, "the planted copy's verdict on the landing cd is %r, want deny" % decision
    if "git-after-cd" not in reason:
        return False, "the planted deny is not the git-after-cd rule: %r" % reason[:90]
    if "guard-crash" not in logged or "planted walk fault" not in logged:
        return False, "the crash is not logged as a guard-crash line: the log ends %r" % logged[-120:]
    return True, "a crash in the cd walk refuses the push after a landing cd as git-after-cd, and is logged"

# The git-after-cd crash check builds its own copies and reads no lazy fixture, so it is fixtureless.
FIXTURELESS_CHECKS.add(git_after_cd_crash_check)
