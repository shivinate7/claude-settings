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
PASS_CMD = "verdict python3 lint/test_x.py"
PASS_LINE = "PASS python3 lint/test_x.py (1.2s)"
SKIP_LINE = "SKIP python3 lint/test_x.py, 3 skipped (1.2s)"
FAIL_LINE = "FAIL python3 lint/test_x.py rc=1 (1.2s) log=/tmp/verdict-x.log"
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
BARE_RUN = transcript_file("bare.jsonl", [HUMAN] + call_records("python3 lint/test_x.py", PASS_LINE, "tu_b"))
OTHER_CMD = transcript_file("other-cmd.jsonl", [HUMAN] + call_records(
    PASS_CMD, "PASS python3 lint/test_y.py (1.2s)", "tu_o"))
# The parent's transcript holds no cite.
PARENT = transcript_file(PARENT_ID + ".jsonl", [HUMAN])
# The real call forms, and a result that comes as a list of text blocks. Each cite has a SKIP-only sibling.
REAL_FORMS = (("the full verdict path", "~/.claude/bin/verdict python3 lint/test_x.py"),
              ("after a cd", "cd x && ~/.claude/bin/verdict python3 lint/test_x.py"),
              ("through the repo's bin/verdict", "python3 bin/verdict python3 lint/test_x.py"))
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
for _claim in ("Lint passed. Status: done.", "CI is green.", "The build is clean.", "The lane lint passes."):
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
    ("clean with no check noun", "The merge is clean.", "The build is clean."),
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

# An agent sender with a cite in its own transcript is not pinned here. A real subagent transcript marks every record
# sidechain, and the rule reads non-sidechain calls only, so that outcome is an open owner pick (Input Needed).
add("pass-claim: an agent's claim with no cite in any transcript is refused", "deny", rule=PASS_RULE,
    tool="SendMessage", cwd=NOGIT, transcript=PARENT, agent_id=NOCITE_AGENT_ID, to=SEND_TO,
    message="Lint passed.")
