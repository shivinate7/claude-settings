# section 42900
FAMILY = "sendmessage-session-id"
#
# Rule pass-claim-cites-verdict, on a send. A "passed", "green", "clean" or "passes" claim tied to a check noun (lint,
# CI, tests, checks, suite, ci-job, build), in a message to @parent or to any other session, must cite a verdict line
# from the sending session's transcript: the verbatim `PASS <cmd> (<secs>s)` line of a non-sidechain Bash call whose
# program is verdict. The cite is read from the hook's transcript_path. These cases run guard.py, the PreToolUse hook
# the settings matcher runs for SendMessage and for mcp__claude-code-remote__send_message. The claim detector is the one
# the Stop check uses (lint/test_report_guard.py, PassClaimCitesVerdictTests). A refusal is one deny. A pass is silent.
# Each false-alarm allow has a red sibling that differs only in the probed feature.
#
# The family is sendmessage-session-id: a new family name would fail the run on a checkout that predates it.
PASS_RULE = "pass-claim-cites-verdict"
PASS_DIR = os.path.join(ROOT, "passclaim")
# A lint or checks claim needs a roster command (rule 4), so the cite here is merge --lane-lint.
PASS_CMD = "verdict merge --lane-lint 7"
PASS_LINE = "PASS merge --lane-lint 7 (1.2s)"
SKIP_LINE = "SKIP merge --lane-lint 7, 3 skipped (1.2s)"
FAIL_LINE = "FAIL merge --lane-lint 7 rc=1 (1.2s) log=/tmp/verdict-x.log"
PARENT_ID = "sess-passclaim-parent"
NOCITE_AGENT_ID = "pc9z8y7x6w5v4u3t2"  # an agent with no transcript at all
SEND_TO = "@parent"
SEND_SESSION = "session_01AbCdEfGhIjKlMnOpQrStUv"
MCP_TOOL = "mcp__claude-code-remote__send_message"
HUMAN = {"type": "user", "isSidechain": False, "message": {"role": "user", "content": "run the check"}}


def call_records(command, result, tool_id, tool="Bash", sidechain=False):
    """One tool call and its result, as a transcript stores them."""
    return [
        {"type": "assistant", "isSidechain": sidechain, "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": tool_id, "name": tool, "input": {"command": command}}]}},
        {"type": "user", "isSidechain": sidechain, "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": tool_id, "content": result}]}},
    ]


def transcript_file(name, records):
    """A transcript under this section's folder, one JSON record a line. Returns its path."""
    path = os.path.join(PASS_DIR, name)
    write(path, "".join(json.dumps(rec) + "\n" for rec in records))
    return path


UNCITED = transcript_file("uncited.jsonl", [HUMAN])
CITED = transcript_file("cited.jsonl", [HUMAN] + call_records(PASS_CMD, PASS_LINE, "tu_v"))
SKIP_ONLY = transcript_file("skip.jsonl", [HUMAN] + call_records(PASS_CMD, SKIP_LINE, "tu_k"))
PASS_THEN_FAIL = transcript_file("failed.jsonl", [HUMAN] + call_records(PASS_CMD, PASS_LINE, "tu_1")
                                 + call_records(PASS_CMD, FAIL_LINE, "tu_2"))
AGENT_RESULT = transcript_file("agent-result.jsonl", [HUMAN] + call_records(
    "run the lint", PASS_LINE, "tu_a", tool="Agent"))
SIDECHAIN = transcript_file("sidechain.jsonl", [HUMAN] + call_records(PASS_CMD, PASS_LINE, "tu_s", sidechain=True))
BARE_RUN = transcript_file("bare.jsonl", [HUMAN] + call_records("merge --lane-lint 7", PASS_LINE, "tu_b"))
OTHER_CMD = transcript_file("other-cmd.jsonl", [HUMAN] + call_records(
    PASS_CMD, "PASS python3 lint/test_y.py (1.2s)", "tu_o"))
# The parent's transcript holds no cite.
PARENT = transcript_file(PARENT_ID + ".jsonl", [HUMAN])
# The real call forms, and a result that comes as a list of text blocks. Each cite has a SKIP-only sibling.
REAL_FORMS = (("the full verdict path", "~/.claude/bin/verdict merge --lane-lint 7"),
              ("after a cd", "cd x && ~/.claude/bin/verdict merge --lane-lint 7"),
              ("through the repo's bin/verdict", "python3 bin/verdict merge --lane-lint 7"))
LIST_CITED = transcript_file("list-cited.jsonl", [HUMAN] + call_records(
    PASS_CMD, [{"type": "text", "text": PASS_LINE}], "tu_l"))
LIST_SKIP = transcript_file("list-skip.jsonl", [HUMAN] + call_records(
    PASS_CMD, [{"type": "text", "text": SKIP_LINE}], "tu_m"))


def pass_refuse(name, tool, message, transcript, **target):
    """A send the guard refuses: an unbacked pass claim. The reason names the rule."""
    add("pass-claim: " + name, "deny", rule=PASS_RULE, tool=tool, cwd=NOGIT, transcript=transcript,
        message=message, **target)


def pass_allow(name, tool, message, transcript, **target):
    """A send the guard lets through silently."""
    add("pass-claim: " + name, "allow", tool=tool, cwd=NOGIT, transcript=transcript, silent=True,
        message=message, **target)


# Each claim form, sent to @parent over SendMessage and to a session over the MCP send tool, with no cite.
for _claim in ("Lint passed. Status: done.", "Checks are green.", "The suite is clean.", "The lane lint passes."):
    pass_refuse("no cite, to @parent: " + _claim, "SendMessage", _claim, UNCITED, to=SEND_TO)
    pass_refuse("no cite, to a session: " + _claim, MCP_TOOL, _claim, UNCITED, session_id=SEND_SESSION)

# A cite that does not hold: each form the Stop check also refuses.
for _name, _transcript in (
    ("the PASS line only in the message", UNCITED),
    ("the PASS line in an Agent result", AGENT_RESULT),
    ("the PASS line in a sidechain", SIDECHAIN),
    ("a SKIP line alone", SKIP_ONLY),
    ("a FAIL of the same command after the pass", PASS_THEN_FAIL),
    ("text from a bare run", BARE_RUN),
    ("a PASS line naming another command", OTHER_CMD),
):
    pass_refuse("cite refused, " + _name, "SendMessage", "Lint passed (" + PASS_LINE + ").", _transcript, to=SEND_TO)

# A cite in this session's transcript passes, to @parent and to a session.
pass_allow("a cited claim to @parent is allowed", "SendMessage", "Lint passed.", CITED, to=SEND_TO)
pass_allow("a cited claim to a session is allowed", MCP_TOOL, "Lint passed.", CITED, session_id=SEND_SESSION)

# False-alarm controls, each with its red sibling. The sibling differs only in the probed feature.
for _name, _allowed, _refused in (
    ("quoted in backticks", "`lint passed`.", "lint passed."),
    ("negated", "Lint is not green.", "Lint is green."),
    ("attributed to a reviewer", "Reviewer: lint passed.", "Lint passed."),
    ("a statistic", "Tests: 12 passed, 2 failed.", "Tests passed, 2 failed."),
    ("clean with no check noun", "The merge is clean.", "The lint is clean."),
    ("passed the brief to a peer", "I passed the brief to the builder.", "I passed the brief, and lint passed."),
):
    pass_allow("control, " + _name + ", to @parent", "SendMessage", _allowed, UNCITED, to=SEND_TO)
    pass_refuse("sibling, " + _name + ", to @parent", "SendMessage", _refused, UNCITED, to=SEND_TO)
pass_allow("control, attributed to a reviewer, to a session", MCP_TOOL, "Reviewer: lint passed.", UNCITED,
           session_id=SEND_SESSION)
pass_refuse("sibling, unattributed, to a session", MCP_TOOL, "Lint passed.", UNCITED, session_id=SEND_SESSION)

# The real call forms and the list-shape result: a cite passes, and the SKIP-only sibling is refused.
for _n, (_form, _command) in enumerate(REAL_FORMS):
    _cited = transcript_file("form-%d-cited.jsonl" % _n, [HUMAN] + call_records(_command, PASS_LINE, "tu_c%d" % _n))
    _skipped = transcript_file("form-%d-skip.jsonl" % _n, [HUMAN] + call_records(_command, SKIP_LINE, "tu_s%d" % _n))
    pass_allow("cited " + _form + ", to @parent", "SendMessage", "Lint passed.", _cited, to=SEND_TO)
    pass_refuse("SKIP only " + _form + ", to @parent", "SendMessage", "Lint passed.", _skipped, to=SEND_TO)
pass_allow("cited as a list of text blocks, to @parent", "SendMessage", "Lint passed.", LIST_CITED, to=SEND_TO)
pass_refuse("SKIP as a list of text blocks, to @parent", "SendMessage", "Lint passed.", LIST_SKIP, to=SEND_TO)

# Attributed claims pass: a builder's report of a pass is no claim of this session. Each has a red sibling.
pass_allow("control, attributed to a builder, to @parent", "SendMessage", "The builder reports lint green.", UNCITED,
           to=SEND_TO)
pass_refuse("sibling, unattributed green, to @parent", "SendMessage", "Lint green.", UNCITED, to=SEND_TO)
pass_allow("control, the builder reports green, to @parent", "SendMessage", "The builder reports green.", UNCITED,
           to=SEND_TO)

# A send that carries an agent_id is an agent's own report, not the session's claim, so the check does not judge it
# (coordinator addendum, 11:23 CST). An agent's uncited "Lint passed." passes, over SendMessage and over the MCP send tool.
# The session's own claims stay judged: the sidechain and Agent-result rows above refuse a session send whose only
# verdict is an agent's.
add("pass-claim: an agent's uncited claim to @parent is allowed, it is the agent's own report", "allow",
    tool="SendMessage", cwd=NOGIT, transcript=PARENT, agent_id=NOCITE_AGENT_ID, silent=True, to=SEND_TO,
    message="Lint passed.")
# The MCP send tool is no row here: an agent's call to it is refused by agent-no-remote-tools, another rule, so the
# row would fail for that cause and never pass for this one.

# Rules 1-3: negation reaches only its own clause, a number erases a claim only as a count, and the claim forms count.
for _claim in ("Lint: PASS.", "All checks pass.", "Lint `passed`.", "No failures, lint passed.", "PR 7 lint passed.",
               "CI run 4321 lint passed."):
    pass_refuse("claim form, uncited, to @parent: " + _claim, "SendMessage", _claim, UNCITED, to=SEND_TO)
pass_allow("control, negation reaches only its clause, to @parent", "SendMessage", "Lint did not pass.", UNCITED,
           to=SEND_TO)
pass_allow("control, a count is no claim, to @parent", "SendMessage", "3/5 tests passed.", UNCITED, to=SEND_TO)
pass_allow("control, a claim wholly in backticks, to @parent", "SendMessage", "`Lint passed.`", UNCITED, to=SEND_TO)

# A colon, slash or pipe ends a negation clause, so the negation does not reach the claim after it. `to` is no
# condition cue. An instruction, a path token and a double-quoted mention are no claim. Each has a refused sibling.
for _claim in ("No issues found: lint passed.", "No failures: lint passed.", "Nothing to fix: lint passed.",
               "No failures / lint passed.", "No failures | lint passed.", "Merged to main and lint passed."):
    pass_refuse("claim form, uncited, to @parent: " + _claim, "SendMessage", _claim, UNCITED, to=SEND_TO)
pass_allow("control, lint did not pass, to @parent", "SendMessage", "Lint did not pass.", UNCITED, to=SEND_TO)
for _msg in ("Ensure lint passes before you hand off.", "Confirm the tests pass.", "Verify the checks are green.",
             "Clean up the lint warnings in hooks/x.py.", "Run a second lint pass.",
             "Files: tests/guard/s42900-pass-claim-send.py", 'the guard flags a "lint passed" claim.'):
    pass_allow("no claim, to @parent: " + _msg, "SendMessage", _msg, UNCITED, to=SEND_TO)
for _msg in ("Lint passes before you hand off.", "The tests pass.", "The checks are green.", "Files: lint passed.",
             "the guard flags a lint passed claim.", 'Size 12" and lint passed.'):
    pass_refuse("sibling, claim, to @parent: " + _msg, "SendMessage", _msg, UNCITED, to=SEND_TO)

# The refusal names the remedy's key phrase: the verdict command must match the claim. Both send tools read one reason.
pass_refuse("the refusal says the command must match the claim, to @parent", "SendMessage", "Lint passed.", UNCITED,
            to=SEND_TO, carries="must match the claim")
pass_refuse("the refusal says the command must match the claim, to a session", MCP_TOOL, "Lint passed.", UNCITED,
            session_id=SEND_SESSION, carries="must match the claim")

# Rule 4: a cite backs a claim only when its check matches. verdict true backs no claim, and a test-file cite backs
# no lint claim. Each refusal has an allowed sibling that differs only in the check.
TRUE_CITE = transcript_file("true-cite.jsonl", [HUMAN] + call_records("verdict true", "PASS true (1.2s)", "tu_t"))
TEST_CITE = transcript_file("test-cite.jsonl", [HUMAN] + call_records(
    "verdict python3 lint/test_x.py", "PASS python3 lint/test_x.py (1.2s)", "tu_tc"))
pass_refuse("cite matches the check, verdict true backs no lint claim, to @parent", "SendMessage", "Lint passed.",
            TRUE_CITE, to=SEND_TO)
pass_refuse("cite matches the check, a lint cite backs no tests claim, to @parent", "SendMessage", "Tests passed.",
            CITED, to=SEND_TO)
pass_refuse("cite matches the check, a test-file cite backs no lint claim, to @parent", "SendMessage", "Lint passed.",
            TEST_CITE, to=SEND_TO)
pass_allow("control, a test-file cite backs a tests claim, to @parent", "SendMessage", "Tests passed.", TEST_CITE,
           to=SEND_TO)
pass_allow("control, a roster cite backs a checks claim, to @parent", "SendMessage", "Checks passed.", CITED,
           to=SEND_TO)

# Rule 5: a cite in its shell-expanded form backs its claim. The PASS line names the command as the shell passed it on.
EXPANDED_CITE = transcript_file("expanded-cite.jsonl", [HUMAN] + call_records(
    "~/.claude/bin/verdict ~/.claude/bin/merge --lane-lint 7",
    "PASS %s --lane-lint 7 (1.2s)" % os.path.expanduser("~/.claude/bin/merge"), "tu_e"))
pass_allow("cite form, the shell-expanded path backs its claim, to @parent", "SendMessage", "Lint passed.",
           EXPANDED_CITE, to=SEND_TO)

# Rule 6: CI and build are no check noun, so these pass uncited, to @parent and to a session.
for _msg in ("Done: PR 12 merged, CI green.", "Clean merge, CI still running.", "The build is clean."):
    pass_allow("CI or build is no check noun, to @parent: " + _msg, "SendMessage", _msg, UNCITED, to=SEND_TO)
pass_allow("CI is no check noun, to a session", MCP_TOOL, "Done: PR 12 merged, CI green.", UNCITED,
           session_id=SEND_SESSION)
