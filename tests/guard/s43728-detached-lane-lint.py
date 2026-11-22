# section 43728
FAMILY = "kill"
#
# A LANE LINT STARTS AS A TRACKED TASK (decision detached-launch-refused, "A lane lint starts as a tracked task").
# `merge --lane-lint` and `bin/ci-job --lint` started detached from the harness have no task, so a FAIL wakes no one.
# Rule detached-launch refuses that start, and its reason says to use the tool's run_in_background. The pid advice of
# the plain detached-launch reason (`cmd & echo $!`) does not fix a lint, so this reason never offers it.
#
# Each refusal below carries the remedy (run_in_background) and lacks the pid advice. A kept pid is the shape that the
# plain rule let through, so those cases are red on the decision. The shapes the plain rule already refused (nohup ... &,
# setsid, disown, a subshell, bash -c) are red on the reason, which names the pid advice there.
DL_REMEDY = "run_in_background"
DL_PID_ADVICE = "capture a pid yourself"  # the second remedy of the plain detached-launch reason
DL_RULE = "detached-launch"


def dl_deny(name, command, **tool_input):
    add("detached lint: %s is refused with the run_in_background remedy" % name, "deny", DL_RULE, cwd=NOGIT,
        carries=DL_REMEDY, lacks=DL_PID_ADVICE, command=command, **tool_input)


def dl_allow(name, command, **tool_input):
    add("detached lint: %s is allowed" % name, "allow", cwd=NOGIT, command=command, **tool_input)


# --- Refused: a lint a `&` ends, or that nohup, setsid or disown detaches.
dl_deny("merge --lane-lint 7 & echo $!, a kept pid", "merge --lane-lint 7 & echo $!")
dl_deny("bin/ci-job checks --lint & echo $!, a kept pid", "bin/ci-job checks --lint & echo $!")
dl_deny("python3 bin/merge --lane-lint 12 & echo $!, a kept pid behind a launcher",
        "python3 bin/merge --lane-lint 12 & echo $!")
dl_deny("nohup merge --lane-lint 7 with a redirect and a trailing &", "nohup merge --lane-lint 7 > l 2>&1 &")
dl_deny("setsid merge --lane-lint 7", "setsid merge --lane-lint 7")
dl_deny("merge --lane-lint 7 & disown", "merge --lane-lint 7 & disown")
dl_deny("(merge --lane-lint 7 &), a subshell job", "(merge --lane-lint 7 &)")
dl_deny("bash -c 'merge --lane-lint 7 &', a script that backgrounds it", "bash -c 'merge --lane-lint 7 &'")
dl_deny("merge --lane-lint 7 & wait, a job a later wait joins", "merge --lane-lint 7 & wait")
# The call itself runs in the background, and the list inside it is still ended by `&`: the harness tracks the shell,
# not the lint the shell backgrounds, so the lint's end still reaches no one.
dl_deny("merge --lane-lint 7 & echo $! with run_in_background", "merge --lane-lint 7 & echo $!",
        run_in_background=True)

# --- The scanner reads the call as the shell does. A comment opener or a lone quote inside a string hides no lint that
# follows it, and a lint named inside a string or a comment starts nothing (see the allowed cases below).
for _opener in ("#", "//", "/*"):
    dl_deny("a quoted %s before merge --lane-lint 7 & echo $!" % _opener,
            'echo "%s"; merge --lane-lint 7 & echo $!' % _opener)
dl_deny("a lone apostrophe in text before merge --lane-lint 7 & echo $!",
        "echo \"it's\"; merge --lane-lint 7 & echo $!")

# --- Allowed: the lint in the foreground, or started so the harness tracks it.
dl_allow("merge --lane-lint 7 in the foreground", "merge --lane-lint 7")
dl_allow("bin/ci-job checks --lint in the foreground", "bin/ci-job checks --lint")
dl_allow("merge --lane-lint 7 with run_in_background and no &", "merge --lane-lint 7", run_in_background=True)
dl_allow("bin/ci-job checks --lint with run_in_background and no &", "bin/ci-job checks --lint",
         run_in_background=True)
dl_allow("nohup merge --lane-lint 7 with no &", "nohup merge --lane-lint 7")
dl_allow("setsid -w merge --lane-lint 7, which waits for its child", "setsid -w merge --lane-lint 7")
dl_allow("an echo that quotes merge --lane-lint 7 &", "echo 'merge --lane-lint 7 &'")
dl_allow("a heredoc body that holds merge --lane-lint 7 &", "cat <<'EOF'\nmerge --lane-lint 7 &\nEOF")
dl_allow("a comment line that holds merge --lane-lint 7 &", "# merge --lane-lint 7 &")
dl_allow("a trailing comment that holds merge --lane-lint 7 &", "ls # merge --lane-lint 7 &")
dl_allow("a multi-line quoted string that holds merge --lane-lint 7 &",
         'echo "first line\nmerge --lane-lint 7 &\nlast line"')

# --- Scope: only a lane lint gets this reason. A background job that is no lint keeps the plain rule's verdict, and a
# kept pid still lets it through.
dl_allow("sleep 3 & echo $!, no lint and a kept pid", "sleep 3 & echo $!")
add("detached lint: a background job that is no lint keeps the plain pid advice", "deny", DL_RULE, cwd=NOGIT,
    carries=DL_PID_ADVICE, command="python3 server.py &")

# --- The owner's typed override lifts this refusal as it lifts the plain rule (decision owner-override). The story is
# section 36421's: refused with no override, then allowed once (or until a timed override ends).
DL_OVERRIDE_ACT = ("detached-lint", "a lane lint started detached with a kept pid",
                   "merge --lane-lint 7 & echo $!", NOGIT, "deny", DL_RULE, None)
DL_CHECKS = tuple(
    (("detached lint: a timed override lets through %s until it ends" if _timed
      else "detached lint: a one-act override lets through %s once, then it is refused again") % DL_OVERRIDE_ACT[1],
     ov_act_check(DL_OVERRIDE_ACT, _timed))
    for _timed in (False, True))
# Late sections join LOG_CHECKS directly: LOG_CHECKS_EXTRA joined in section 40805, and a later append is in no run.
for _label, _check in DL_CHECKS:
    LOG_FAMILY[_label] = _family(_label)
    FIXTURELESS_CHECKS.add(_check)  # it reads NOGIT and its own config folder, and builds no other fixture
LOG_CHECKS = LOG_CHECKS + DL_CHECKS
