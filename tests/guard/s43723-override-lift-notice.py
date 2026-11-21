# section 43723
FAMILY = "override"
#
# When an owner override lifts a refusal, the guard prints one line on stdout: a PreToolUse JSON object whose
# hookSpecificOutput.additionalContext names the lifted rule and says override, with no permissionDecision, so the
# normal permission flow runs. Claude does not see stderr from a hook that
# exits 0, and it does see additionalContext, so the line goes on stdout. ov_names_lift in section 36421 reads it.
#
# Cases 1 and 2 need that line, so they fail until the guard prints it. Case 3 needs no output at all. Case 4 is a
# control: a never-lifted act stays refused, and no lift line names its rule. Each case makes its calls through
# ovl_call, which runs the same guard call as ov_call (section 36421) and keeps the guard run's stdout and stderr.
OVL_KILL_RULE = "machine-wide-kill"  # the rule that refuses `kill $(pgrep ...)` (section 36421, ov_log_check)
OVL_NEVER_RULE = "frozen-path"  # the rule that refuses a Write of the override file, which no override lifts


def ovl_call(tool, tool_input, cwd, config, session, seconds):
    """One guard call through ov_call. Returns (decision, reason, stdout, stderr lines), where stdout is the guard run's
    stdout, stripped, and the stderr lines are its non-empty lines. A spy on subprocess.run keeps the run whose command
    ends in the guard, so the one decide() call is read once."""
    runs = []
    real_run = subprocess.run

    def spy(command, *args, **kwargs):
        result = real_run(command, *args, **kwargs)
        if isinstance(command, (list, tuple)) and command and command[-1] == GUARD:
            runs.append(result)
        return result

    with mock.patch.object(subprocess, "run", spy):
        got, reason = ov_call(tool, tool_input, cwd, config, session, seconds)
    if len(runs) != 1:
        return "no-run", "the guard ran %d times for one call" % len(runs), "", []
    stderr = [line for line in runs[0].stderr.splitlines() if line.strip()]
    return got, reason, runs[0].stdout.strip(), stderr


def ovl_lift_check(prompt, name):
    """Type `prompt`, then make one call that a kill refusal would stop. The act is allowed, and stdout holds the one
    JSON line that names the rule and says override."""
    config, session = ov_config(name), "ovl-" + name
    note = ov_type(config, session, prompt)
    if note:
        return False, note
    got, reason, stdout, _stderr = ovl_call("Bash", {"command": OV_KILL}, NOGIT, config, session, 60)
    problem = ov_want(got, reason, "allow", OVL_KILL_RULE)
    if problem:
        return False, "the lifted act: %s" % problem
    if not stdout:
        return False, "the lifted act printed nothing on stdout, want one JSON line that names %r and says override" % (
            OVL_KILL_RULE)
    if not ov_names_lift(stdout, OVL_KILL_RULE):
        return False, "the stdout line does not name %r and say override, or it has a permissionDecision: %r" % (
            OVL_KILL_RULE, stdout[:160])
    return True, "stdout holds one context line that names %r: %s" % (OVL_KILL_RULE, stdout[:100])


def ovl_timed_check():
    """A timed override (`override 15m`) lifts a kill refusal and prints one stdout line that names the rule."""
    return ovl_lift_check("override 15m", "notice-timed")


def ovl_once_check():
    """A one-act override (`override`) lifts a kill refusal and prints one stdout line that names the rule."""
    return ovl_lift_check("override", "notice-once")


def ovl_quiet_check():
    """A call that no rule refuses prints no output, on stdout or stderr, while an override is live, a timed one or a
    one-act one. A line on every call would turn this red."""
    for prompt, name in (("override 15m", "quiet-timed"), ("override", "quiet-once")):
        config, session = ov_config(name), "ovl-" + name
        note = ov_type(config, session, prompt)
        if note:
            return False, note
        got, reason, stdout, stderr = ovl_call("Bash", {"command": "echo ovl-quiet"}, NOGIT, config, session, 60)
        problem = ov_want(got, reason, "allow", "")
        if problem:
            return False, "under `%s`, a call no rule refuses: %s" % (prompt, problem)
        if stdout or stderr:
            return False, "under `%s`, a call no rule refuses printed output: stdout %r, stderr %r" % (
                prompt, stdout[:120], stderr[:2])
    return True, "an allowed call under a timed and a one-act override prints no output"


def ovl_never_lifted_check():
    """A Write of the override file stays refused under a live timed override, and no lift line names its rule."""
    config, session = ov_config("never-lifted"), "ovl-never-lifted"
    note = ov_type(config, session, "override 15m")
    if note:
        return False, note
    tool_input = {"file_path": slash(ov_pass_path(config, session)), "content": "{}"}
    got, reason, stdout, stderr = ovl_call("Write", tool_input, NOGIT, config, session, 60)
    problem = ov_want(got, reason, "deny", OVL_NEVER_RULE)
    if problem:
        return False, "the never-lifted act: %s" % problem
    if ov_names_lift(stdout, OVL_NEVER_RULE) or any(OVL_NEVER_RULE in line for line in stderr):
        return False, "the refused act printed a lift line that names %r: stdout %r, stderr %r" % (
            OVL_NEVER_RULE, stdout[:120], stderr[:2])
    return True, "the write of the override file stays refused under %s, and no lift line names it" % OVL_NEVER_RULE


OVL_CHECKS = (
    ("override notice: a timed override lifts a kill, and stdout names the rule in a context line", ovl_timed_check),
    ("override notice: a one-act override lifts a kill, and stdout names the rule in a context line", ovl_once_check),
    ("override notice: an allowed call under a live override prints no output", ovl_quiet_check),
    ("override notice: a never-lifted act stays refused, and no lift line names its rule", ovl_never_lifted_check),
)
# Late sections join LOG_CHECKS directly: LOG_CHECKS_EXTRA joined in section 40805, and a later append is in no run.
for _label, _check in OVL_CHECKS:
    LOG_FAMILY[_label] = _family(_label)
    FIXTURELESS_CHECKS.add(_check)
LOG_CHECKS = LOG_CHECKS + OVL_CHECKS
