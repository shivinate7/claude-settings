# section 43723
FAMILY = "override"
#
# When an owner override lifts a refusal, the guard prints one line on stderr that names the rule it lifted, such as
# `override lifted: <rule>`. The lifted act is allowed, so the owner sees that a refusal was lifted. The line goes to
# stderr, because an allow prints nothing on stdout: ov_want in section 36421 pins that, so the answer the guard gives
# stays the same. A call that no rule refuses prints no such line, and a never-lifted act stays refused with no line.
#
# Cases 1 and 2 need the new line, so they fail until the guard prints it. Cases 3 and 4 are controls that hold today.
# Each case makes its calls through ovl_call, which runs the same guard call as ov_call (section 36421) and keeps the
# guard run's stderr. The override is typed with ov_type, and the act is the one section 36421 uses.
OVL_KILL_RULE = "machine-wide-kill"  # the rule that refuses `kill $(pgrep ...)` (section 36421, ov_log_check)
OVL_NEVER_RULE = "frozen-path"  # the rule that refuses a Write of the override file, which no override lifts


def ovl_call(tool, tool_input, cwd, config, session, seconds):
    """One guard call through ov_call, with the stderr of its guard run. Returns (decision, reason, stderr lines).
    A spy on subprocess.run keeps the run whose command ends in the guard, so the one decide() call is read once."""
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
        return "no-run", "the guard ran %d times for one call" % len(runs), []
    return got, reason, [line for line in runs[0].stderr.splitlines() if line.strip()]


def ovl_lift_check(prompt, name):
    """Type `prompt`, then make one call that a kill refusal would stop. The act is allowed, and exactly one stderr
    line names the rule and says override."""
    config, session = ov_config(name), "ovl-" + name
    note = ov_type(config, session, prompt)
    if note:
        return False, note
    got, reason, lines = ovl_call("Bash", {"command": OV_KILL}, NOGIT, config, session, 60)
    problem = ov_want(got, reason, "allow", OVL_KILL_RULE)
    if problem:
        return False, "the lifted act: %s" % problem
    named = [line for line in lines if OVL_KILL_RULE in line]
    if len(named) != 1:
        return False, "the lifted act printed %d stderr line(s) that name %r, want one: %r" % (
            len(named), OVL_KILL_RULE, lines[:3])
    if "override" not in named[0]:
        return False, "the one stderr line that names %r does not say override: %r" % (OVL_KILL_RULE, named[0][:120])
    return True, "the lifted act printed one stderr line that names %r: %s" % (OVL_KILL_RULE, named[0][:80])


def ovl_timed_check():
    """A timed override (`override 15m`) lifts a kill refusal and prints one stderr line that names the rule."""
    return ovl_lift_check("override 15m", "notice-timed")


def ovl_once_check():
    """A one-act override (`override`) lifts a kill refusal and prints one stderr line that names the rule."""
    return ovl_lift_check("override", "notice-once")


def ovl_quiet_check():
    """A call that no rule refuses prints no stderr line while an override is live, a timed one or a one-act one. A
    notice on every call would turn this red."""
    for prompt, name in (("override 15m", "quiet-timed"), ("override", "quiet-once")):
        config, session = ov_config(name), "ovl-" + name
        note = ov_type(config, session, prompt)
        if note:
            return False, note
        got, reason, lines = ovl_call("Bash", {"command": "echo ovl-quiet"}, NOGIT, config, session, 60)
        problem = ov_want(got, reason, "allow", "")
        if problem:
            return False, "under `%s`, a call no rule refuses: %s" % (prompt, problem)
        if lines:
            return False, "under `%s`, a call no rule refuses printed stderr: %r" % (prompt, lines[:2])
    return True, "an allowed call under a timed and a one-act override prints no stderr"


def ovl_never_lifted_check():
    """A Write of the override file stays refused under a live timed override, and no stderr line names its rule.
    The lift line is for a lifted act only."""
    config, session = ov_config("never-lifted"), "ovl-never-lifted"
    note = ov_type(config, session, "override 15m")
    if note:
        return False, note
    tool_input = {"file_path": slash(ov_pass_path(config, session)), "content": "{}"}
    got, reason, lines = ovl_call("Write", tool_input, NOGIT, config, session, 60)
    problem = ov_want(got, reason, "deny", OVL_NEVER_RULE)
    if problem:
        return False, "the never-lifted act: %s" % problem
    named = [line for line in lines if OVL_NEVER_RULE in line]
    if named:
        return False, "the refused act printed a stderr line that names %r: %r" % (OVL_NEVER_RULE, named[0][:120])
    return True, "the write of the override file stays refused under %s, and no stderr line names it" % OVL_NEVER_RULE


OVL_CHECKS = (
    ("override notice: a timed override lifts a kill, and one stderr line names the rule", ovl_timed_check),
    ("override notice: a one-act override lifts a kill, and one stderr line names the rule", ovl_once_check),
    ("override notice: an allowed call under a live override prints no stderr line", ovl_quiet_check),
    ("override notice: a never-lifted act stays refused, and no stderr line names its rule", ovl_never_lifted_check),
)
# Late sections join LOG_CHECKS directly: LOG_CHECKS_EXTRA joined in section 40805, and a later append is in no run.
for _label, _check in OVL_CHECKS:
    LOG_FAMILY[_label] = _family(_label)
    FIXTURELESS_CHECKS.add(_check)
LOG_CHECKS = LOG_CHECKS + OVL_CHECKS
