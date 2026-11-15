# section 6591
FAMILY = "stream"  # the check-timeout rule belongs with check-tail in the stream family
#
# A background lane lint must set a time limit above its own bound (rule check-timeout). The limit is the `timeout`
# of the Bash or PowerShell tool input, in milliseconds. CHECK_TIMEOUT_MS, the bound, and the trigger constants come
# from the merge tool, read in section 6590. A foreground call can never reach the bound: its limit is at most
# FOREGROUND_MAX_MS, so every foreground lane lint is refused. A call that sets no limit gets the tool's default,
# which is under the bound too: 120000 ms in the foreground, 1800000 ms in the background.
FOREGROUND_MAX_MS = 600000  # the Bash tool's foreground limit
# The refusal names the limit to use and the background form. It never names the refused call's flag, bin/merge, or
# its own limit: a refusal never names the forbidden target.
CHECK_TIMEOUT_REFUSED_NAMES = ("--lane-lint", "bin/merge", str(CHECK_TIMEOUT_LOW_MS))
CHECK_TIMEOUT_REFUSED_CARRIES = (str(CHECK_TIMEOUT_MS), "background")

# THE REFUSAL. A background lane lint with a limit under the bound is refused, and so is one with no limit. A
# foreground lane lint is refused at any limit.
add("check-timeout: a lane lint under run_in_background with a limit under the bound is refused", "deny",
    CHECK_TIMEOUT_RULE, cwd=NOGIT, run_in_background=True, timeout=CHECK_TIMEOUT_LOW_MS,
    description=TAIL_BG_UNTIL, carries=CHECK_TIMEOUT_REFUSED_CARRIES, lacks=CHECK_TIMEOUT_REFUSED_NAMES,
    command=CHECK_TIMEOUT_LINT)
add("check-timeout: a lane lint under run_in_background with no limit is refused", "deny",
    CHECK_TIMEOUT_RULE, cwd=NOGIT, run_in_background=True, description=TAIL_BG_UNTIL,
    carries=CHECK_TIMEOUT_REFUSED_CARRIES, lacks=CHECK_TIMEOUT_REFUSED_NAMES, command=CHECK_TIMEOUT_LINT)
add("check-timeout: a lane lint in the foreground with no limit is refused", "deny",
    CHECK_TIMEOUT_RULE, cwd=NOGIT, carries=CHECK_TIMEOUT_REFUSED_CARRIES,
    lacks=CHECK_TIMEOUT_REFUSED_NAMES, command=CHECK_TIMEOUT_LINT)
add("check-timeout: a lane lint in the foreground at the tool maximum is refused", "deny",
    CHECK_TIMEOUT_RULE, cwd=NOGIT, timeout=FOREGROUND_MAX_MS, carries=CHECK_TIMEOUT_REFUSED_CARRIES,
    lacks=CHECK_TIMEOUT_REFUSED_NAMES, command=CHECK_TIMEOUT_LINT)
add("check-timeout: a lane lint in the foreground at the bound is refused", "deny",
    CHECK_TIMEOUT_RULE, cwd=NOGIT, timeout=CHECK_TIMEOUT_MS, carries=CHECK_TIMEOUT_REFUSED_CARRIES,
    lacks=CHECK_TIMEOUT_REFUSED_NAMES, command=CHECK_TIMEOUT_LINT)
add("check-timeout: a PowerShell lane lint under run_in_background with a limit under the bound is refused", "deny",
    CHECK_TIMEOUT_RULE, tool="PowerShell", cwd=NOGIT, run_in_background=True, timeout=CHECK_TIMEOUT_LOW_MS,
    description=TAIL_BG_UNTIL, carries=CHECK_TIMEOUT_REFUSED_CARRIES, lacks=CHECK_TIMEOUT_REFUSED_NAMES,
    command=CHECK_TIMEOUT_LINT)

# THE BOUND. The limit is read against CHECK_TIMEOUT_MS: one ms under is refused; at it, and one ms above, the run is
# allowed; a verdict wrapper keeps the same limit.
add("check-timeout: a limit one ms under the bound under run_in_background is refused", "deny",
    CHECK_TIMEOUT_RULE, cwd=NOGIT, run_in_background=True, timeout=CHECK_TIMEOUT_MS - 1,
    description=TAIL_BG_UNTIL, carries=CHECK_TIMEOUT_REFUSED_CARRIES, lacks=CHECK_TIMEOUT_REFUSED_NAMES,
    command=CHECK_TIMEOUT_LINT)
for _name, _limit in (("at the bound", CHECK_TIMEOUT_MS), ("one ms above the bound", CHECK_TIMEOUT_MS + 1)):
    add("check-timeout: a lane lint with a limit %s under run_in_background is allowed" % _name, "allow",
        cwd=NOGIT, run_in_background=True, timeout=_limit, description=TAIL_BG_UNTIL, command=CHECK_TIMEOUT_LINT)
add("check-timeout: the lane lint at the bound, wrapped in verdict under run_in_background, is allowed", "allow",
    cwd=NOGIT, run_in_background=True, timeout=CHECK_TIMEOUT_MS, description=TAIL_BG_UNTIL,
    command="verdict " + CHECK_TIMEOUT_LINT)
add("check-timeout: a PowerShell lane lint at the bound under run_in_background is allowed", "allow",
    tool="PowerShell", cwd=NOGIT, run_in_background=True, timeout=CHECK_TIMEOUT_MS, description=TAIL_BG_UNTIL,
    command=CHECK_TIMEOUT_LINT)

# THE SPELLINGS THAT COUNT. Each is refused in the background under a limit under the bound. The roster is the one
# check_stage reads: merge, merge.cmd, the merge script run by python, and each of them behind a wrapper.
for _name, _command in (
    ("the bin path", "~/.claude/bin/merge --lane-lint 3270"),
    ("merge.cmd", "merge.cmd --lane-lint 3270"),
    ("the merge script run by python", "python merge/merge.py --lane-lint 3270"),
    ("the launcher run by python", "python merge/launch.py --lane-lint 3270"),
    ("the merge script run by uv", "uv run python merge/merge.py --lane-lint 3270"),
    ("merge behind an env assignment", "env FOO=1 merge --lane-lint 3270"),
    ("merge behind verdict with no pipe", "verdict merge --lane-lint 3270"),
    ("the incident line behind the bin path verdict", "~/.claude/bin/verdict ~/.claude/bin/merge --lane-lint 1476 2>&1"),
):
    add("check-timeout: %s under run_in_background with a limit under the bound is refused" % _name, "deny",
        CHECK_TIMEOUT_RULE, cwd=NOGIT, run_in_background=True, timeout=CHECK_TIMEOUT_LOW_MS,
        description=TAIL_BG_UNTIL, carries=CHECK_TIMEOUT_REFUSED_CARRIES, lacks=CHECK_TIMEOUT_REFUSED_NAMES,
        command=_command)

# THE RUNS NOT JUDGED. The rule reads only a lane lint. The other merge verbs, a check that is not the merge tool, and
# an ordinary command pass at a limit under the bound.
for _name, _command in (
    ("merge --review-record", "merge --review-record 3270"),
    ("merge --release-check", "merge --release-check 3270"),
    ("merge --confirm", "merge 3270 --confirm"),
    ("ci-job checks --lint, which is not the merge tool", "~/.claude/bin/ci-job checks --lint --base origin/main"),
    ("an ordinary command", "make check"),
):
    add("check-timeout: %s under run_in_background with a limit under the bound is allowed" % _name, "allow",
        cwd=NOGIT, run_in_background=True, timeout=CHECK_TIMEOUT_LOW_MS, description=TAIL_BG_UNTIL, command=_command)

# SCANNER PINS (rule building-scanner-respects-strings). A mention of the run in a comment, a quote, a heredoc, a commit
# message or a template literal is no run. A real run after such text is one. Each construct is pinned on its own, as
# the live-stream pins are.
for _name, _command in (
    ("a # inside quotes", 'echo "# merge --lane-lint 3270"'),
    ("a // inside quotes", 'echo "x // merge --lane-lint"'),
    ("a /* inside quotes", 'echo "/* merge --lane-lint 3270"'),
    ("a multi-line quote", 'echo "first line\nmerge --lane-lint 3270\nlast line"'),
    ("a lone apostrophe in quotes", 'echo "don\'t merge --lane-lint"'),
    ("a heredoc body", "cat <<'EOF'\nmerge --lane-lint 3270\nEOF"),
    ("a commit message", VCS + ' commit -m "merge --lane-lint 3270 under a low limit"'),
    ("a multi-line template literal in single quotes", "node -e 'const s = `\nmerge --lane-lint 3270\n`'"),
):
    add("check-timeout: scanner: " + _name + " is no run", "allow", cwd=NOGIT, run_in_background=True,
        timeout=CHECK_TIMEOUT_LOW_MS, description=TAIL_BG_UNTIL, command=_command)
for _name, _command in (
    ("a lone apostrophe in quotes", 'echo "it\'s"; merge --lane-lint 1'),
    ("a # inside quotes", 'echo "# x"; merge --lane-lint 1'),
    ("a // inside quotes", 'echo "a // b"; merge --lane-lint 1'),
    ("a /* inside quotes", 'echo "/* x"; merge --lane-lint 1'),
    ("a multi-line quote", 'echo "a\nb"\nmerge --lane-lint 1'),
    ("a lone apostrophe in plain text", "echo don't; merge --lane-lint 1"),
    ("a heredoc body", "cat <<'EOF'\nnote\nEOF\nmerge --lane-lint 1"),
    ("a commit message with an apostrophe", VCS + ' commit -m "it\'s done"; merge --lane-lint 1'),
):
    add("check-timeout: scanner: a run after " + _name + " is refused", "deny", CHECK_TIMEOUT_RULE, cwd=NOGIT,
        run_in_background=True, timeout=CHECK_TIMEOUT_LOW_MS, description=TAIL_BG_UNTIL,
        carries=CHECK_TIMEOUT_REFUSED_CARRIES, lacks=CHECK_TIMEOUT_REFUSED_NAMES, command=_command)


# THE REMEDY NAMES NO TARGET (the stack refusal's style: stack_reason_hygiene_case). The guard's printed reason is read
# for each refusal form, not the constant alone: the reason names the limit to use and the background form, and it
# names none of the three parts of the refused call (its flag, bin/merge, its limit). Each problem names one cause.
CHECK_TIMEOUT_HYGIENE_REFUSALS = (
    ("a foreground lane lint with no limit", "Bash", CHECK_TIMEOUT_LINT, False, None),
    ("a background lane lint with no limit", "Bash", CHECK_TIMEOUT_LINT, True, None),
    ("a background lane lint with a limit under the bound", "Bash", CHECK_TIMEOUT_LINT, True, CHECK_TIMEOUT_LOW_MS),
    ("a PowerShell lane lint in the background", "PowerShell", CHECK_TIMEOUT_LINT, True, CHECK_TIMEOUT_LOW_MS),
    ("a verdict-wrapped lane lint in the background", "Bash", "verdict " + CHECK_TIMEOUT_LINT, True,
     CHECK_TIMEOUT_LOW_MS),
)


def check_timeout_hygiene_case():
    """CLAUDE.md: "A refusal's printed remedy never names the forbidden target."

    The refused call is the forbidden target here: its flag, bin/merge and its own limit. The remedy must point at
    the limit to use and at the background run instead, so an agent that reads it runs the lint correctly.
    """
    problems = []
    for label, tool, command, background, timeout in CHECK_TIMEOUT_HYGIENE_REFUSALS:
        tool_input = {"command": command, "description": TAIL_BG_UNTIL}
        if background:
            tool_input["run_in_background"] = True
        if timeout is not None:
            tool_input["timeout"] = timeout
        got, reason = decide({"raw": None, "tool": tool, "cwd": NOGIT, "session": None,
                              "env_path": None, "tool_input": tool_input})
        if got != "deny":
            problems.append("%s: expected deny, got %s" % (label, got))
            continue
        if CHECK_TIMEOUT_RULE not in reason:
            problems.append("%s: the refusal does not name rule %s" % (label, CHECK_TIMEOUT_RULE))
        if str(CHECK_TIMEOUT_MS) not in reason:
            problems.append("%s: the refusal does not name the limit to use" % label)
        if "background" not in reason:
            problems.append("%s: the refusal does not say to run in the background" % label)
        for fragment in CHECK_TIMEOUT_REFUSED_NAMES:
            if fragment in reason:
                problems.append("%s: the refusal names %r, part of the refused call" % (label, fragment))
    if problems:
        return False, "; ".join(problems)
    return True, "%d refusals name the limit to use and the background run, and none names the refused call" % len(
        CHECK_TIMEOUT_HYGIENE_REFUSALS)
