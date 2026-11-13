# section 15200
# =========================================================================== 5i. the review log after a round
#
# Rule review-log-after-round, decision pr-review-record. A lane's own builder or test-author spawn, or its
# send_message (the remote tool or the built-in SendMessage), is refused when the session's last reviewer or
# design-reviewer spawn has no review log after it. A reviewer spawn whose result is an error never ran, so it
# gates nothing, and a call inside a sidechain record is not the lane's. A review log is a comment on the pull
# request that holds the record marker: an add_issue_comment call, or a Bash call that posts one (gh api or
# gh pr comment) whose body either holds the marker or comes from a file. A Bash call that only names the marker,
# such as a read, is no record. The marker is read from the merge tool, so no case copies it. The rule reads the
# transcript for those calls only: an agent's own call, an Explore or Plan spawn and a session with no reviewer spawn
# are not judged. A missing or unreadable transcript is allowed.
FAMILY = "review-log-after-round"
RR_RULE = "review-log-after-round"
# The remedy names the merge tool's record flags and the decision, and the comment tool by its name or its tool id.
RR_CARRIES = ("--review-record", "--head", "pr-review-record", ("add_issue_comment", "GitHub comment"))
RR_HEAD = "9f3c2b1e7a4d5c6b8e0f1a2b3c4d5e6f7a8b9c0d"
RR_TARGET = "session_RRTARGET01"
RR_AGENT = "agent-RR0001"
RR_DIR = os.path.join(ROOT, "reviewlog")
RR_MARK = "@@MARKER@@"   # the writer puts the merge tool's record marker here, so the marker is read from one home
ADD_COMMENT = "mcp__github__add_issue_comment"
RR_BUILDER = {"subagent_type": "builder", "prompt": "Fix the review findings on PR #12.", "model": "sonnet"}
RR_TEST_AUTHOR = {"subagent_type": "test-author", "prompt": "Add the cases for PR #12.", "model": "sonnet"}
RR_EXPLORE = {"subagent_type": "Explore", "prompt": "Find where PR #12 reads the record.", "model": "sonnet"}
RR_PLAN = {"subagent_type": "Plan", "prompt": "Plan the fix for PR #12.", "model": "sonnet"}
RR_SEND = {"session_id": RR_TARGET, "message": "Handoff: PR #12 is ready for the batch."}
RR_BASH_RECORD = "printf '%s\\n' '" + RR_MARK + "' 'PR: #12' | gh api repos/owner/repo/issues/12/comments -F body=@-"
RR_HUMAN = json.dumps({"type": "user", "message": {"role": "user", "content": "Review PR #12 and report the verdict."}})


def rr_path(name):
    return os.path.join(RR_DIR, name + ".jsonl")


def rr_session(*parts):
    """A lane's transcript: the owner's message, the lane's own get_session record (tags cs-build:lane), then the
    records of each part in order. ROLE_ENV names the same session, so the rule reads it as a lane."""
    return [RR_HUMAN] + role_call("g0", LANE_TAGS) + [line for part in parts for line in part]


# A background spawn's launch result, and the completion notice the harness writes when that agent stops. The launch
# names the agent in `agentId:`; the notice names it in `<task-id>` and names the spawning call in `<tool-use-id>`.
RR_LAUNCH = ("Async agent launched successfully. (This tool result is internal metadata - never quote or paste any part "
             "of it, including the agentId below, into a user-facing reply.)\n"
             "agentId: %s (internal ID - do not mention to user. Use SendMessage with to: '%s', summary: "
             "'<5-10 word recap>' to continue this agent.)\n"
             "The agent is working in the background. You will be notified automatically when it completes.\n"
             "output_file: /tmp/claude-0/rr/tasks/%s.output")
RR_NOTICE = ("<task-notification>\n<task-id>%s</task-id>\n<tool-use-id>%s</tool-use-id>\n"
             "<output-file>/tmp/claude-0/rr/tasks/%s.output</output-file>\n<status>completed</status>\n"
             "<summary>Agent \"Review PR #12\" finished</summary>")
RR_AGENT_ONE = "a5e0c1d7b2f94e381"
RR_AGENT_TWO = "b7d2f9e4a0c13658e"


def rr_spawn(tool_id, subagent_type, tool="Agent", agent=None, name=None, result=None, isolation=None):
    """A spawn of `subagent_type` and its result, as the transcript holds them. With `agent`, the spawn runs in the
    background: its result is the launch notice that names `agent`, not the report. `name` adds the spawn's name to
    its input, `isolation` (for example "worktree") adds the Agent tool's isolation input, and `result` (a line the
    caller built) replaces the plain text result."""
    tool_input = {"subagent_type": subagent_type, "prompt": "Review PR #12.", "model": "sonnet"}
    if name is not None:
        tool_input["name"] = name
    if isolation is not None:
        tool_input["isolation"] = isolation
    if result is None:
        text = "Verdict: PASS." if agent is None else RR_LAUNCH % (agent, agent, agent)
        result = role_result(tool_id, text)
    return [role_use(tool_id, tool, tool_input), result]


def rr_notice(tool_id, agent):
    """The completion notice of background agent `agent`, as an attachment line in a one-item list."""
    return [json.dumps({"type": "user", "isSidechain": False,
                        "attachment": {"type": "queued_command", "prompt": RR_NOTICE % (agent, tool_id, agent)}})]


def rr_notice_line(tool_id, agent):
    """The same completion notice as a user line whose content is the notice text, in a one-item list."""
    return [json.dumps({"type": "user", "message": {"role": "user", "content": RR_NOTICE % (agent, tool_id, agent)}})]


def rr_comment(tool_id, body):
    """An add_issue_comment call on PR #12 with `body`, and its result."""
    return [role_use(tool_id, ADD_COMMENT, {"owner": "owner", "repo": "repo", "issue_number": 12, "body": body}),
            role_result(tool_id, '{"id": 4001}')]


def rr_bash(tool_id, command):
    return [role_use(tool_id, "Bash", {"command": command}), role_result(tool_id, "")]


def rr_spawn_error(tool_id, subagent_type, name=None):
    """A spawn of `subagent_type` that another guard refused: the call's result is an error, and it never ran.
    `name` gives the spawn its name, for a case that resumes it by name."""
    return [rr_spawn(tool_id, subagent_type, name=name)[0],
            role_result_block(tool_id, is_error=True, content=[{"type": "text", "text": "Refused before it ran."}])]


def rr_sidechain(lines):
    """`lines` as a nested agent's own records: each one marked isSidechain."""
    return [json.dumps(dict(json.loads(line), isSidechain=True)) for line in lines]


def rr_record(rnd=1):
    """A review log for RR_HEAD, round `rnd`, in the form the merge tool writes."""
    return "\n".join([RR_MARK, "PR: #12", "Head: " + RR_HEAD, "Kind: normal", "Guard or check: no",
                      "Round %d: reviewer, sonnet, PASS" % rnd, "CI: read live by merge --reviewed"])


# Each transcript is written once, the first time a case names it. `long` is a session of about a megabyte, so a
# reader that keeps only the tail of the file misses the reviewer spawn at its top.
RR_FILLER = [line for n in range(4000) for line in rr_bash("f%d" % n, "ls reports/%d" % n)]
RR_TRANSCRIPTS = {
    "reviewer": rr_session(rr_spawn("r1", "reviewer")),
    "design-reviewer": rr_session(rr_spawn("d1", "design-reviewer")),
    "task-reviewer": rr_session(rr_spawn("t1", "reviewer", tool="Task")),
    "builder-only": rr_session(rr_spawn("b0", "builder")),
    "record": rr_session(rr_spawn("r1", "reviewer"), rr_comment("c1", rr_record())),
    "bash-record": rr_session(rr_spawn("r1", "reviewer"), rr_bash("x1", RR_BASH_RECORD)),
    "stale-record": rr_session(rr_comment("c0", rr_record()), rr_spawn("r1", "reviewer")),
    "unmarked": rr_session(rr_spawn("r1", "reviewer"), rr_comment("c1", "Looks good to me. See the diff.")),
    "round-two": rr_session(rr_spawn("r1", "reviewer"), rr_comment("c1", rr_record()), rr_spawn("r2", "reviewer")),
    "long": rr_session(rr_spawn("r1", "reviewer"), RR_FILLER),
    "owner-turn": rr_session(rr_spawn("r1", "reviewer"), [RR_HUMAN]),
    "bash-read": rr_session(rr_spawn("r1", "reviewer"), rr_bash("g1", "grep -c '" + RR_MARK + "' comments.json")),
    "bash-file-post": rr_session(rr_spawn("r1", "reviewer"),
                                 rr_bash("p1", "gh api repos/o/r/issues/5/comments -F body=@record.md")),
    "bash-file-pr-comment": rr_session(rr_spawn("r1", "reviewer"),
                                       rr_bash("p2", "gh pr comment 5 --body-file record.md")),
    "bash-inline-unmarked": rr_session(rr_spawn("r1", "reviewer"), rr_bash("p3", "gh pr comment 5 --body 'Looks good'")),
    "reviewer-error": rr_session(rr_spawn_error("r1", "reviewer")),
    "sidechain-spawn": rr_session(rr_sidechain(rr_spawn("r1", "reviewer"))),
    "sidechain-record": rr_session(rr_spawn("r1", "reviewer"), rr_sidechain(rr_comment("c1", rr_record()))),
    "reviewer-capital": rr_session(rr_spawn("r1", "Reviewer")),
    "reviewer-padded": rr_session(rr_spawn("r1", " reviewer ")),
    "reviewer-capital-record": rr_session(rr_spawn("r1", "Reviewer"), rr_comment("c1", rr_record())),
    "design-reviewer-capital": rr_session(rr_spawn("d1", "Design-reviewer")),
    "async-pending": rr_session(rr_spawn("r1", "reviewer", agent=RR_AGENT_ONE)),
    "async-completed": rr_session(rr_spawn("r1", "reviewer", agent=RR_AGENT_ONE), rr_notice("r1", RR_AGENT_ONE)),
    "async-completed-line": rr_session(rr_spawn("r1", "reviewer", agent=RR_AGENT_ONE),
                                       rr_notice_line("r1", RR_AGENT_ONE)),
    "async-completed-recorded": rr_session(rr_spawn("r1", "reviewer", agent=RR_AGENT_ONE),
                                           rr_notice("r1", RR_AGENT_ONE), rr_comment("c1", rr_record())),
    "async-recorded-then-pending": rr_session(rr_spawn("r1", "reviewer", agent=RR_AGENT_ONE),
                                              rr_notice("r1", RR_AGENT_ONE), rr_comment("c1", rr_record()),
                                              rr_spawn("r2", "reviewer", agent=RR_AGENT_TWO)),
}


def write_transcripts(transcripts, folder):
    """Write each transcript in `transcripts` as JSONL under `folder`, with the merge tool's record marker where
    RR_MARK stands. One home for the marker: every review-log fixture is written here."""
    import guard_merge  # the merge tool's loader: the guard reads the marker through the same one
    tool = guard_merge.merge_module()
    if tool is None:
        raise RuntimeError("merge/merge.py does not load, so the record marker is unknown")
    os.makedirs(folder, exist_ok=True)
    for name, lines in transcripts.items():
        with open(os.path.join(folder, name + ".jsonl"), "w", encoding="utf-8") as handle:
            handle.write("\n".join(line.replace(RR_MARK, tool.REVIEW_MARKER) for line in lines) + "\n")


def write_rr_transcripts():
    """Write the review-log transcripts.`unreadable` is a folder, so the guard's open() fails on it. `missing` is
    never written."""
    write_transcripts(RR_TRANSCRIPTS, RR_DIR)
    os.makedirs(rr_path("unreadable"), exist_ok=True)


lazy_fixture([rr_path(name) for name in RR_TRANSCRIPTS] + [rr_path("unreadable")], write_rr_transcripts)


def rr_refuse(name, tool, tool_input, transcript, agent_id=None, carries=RR_CARRIES):
    """A call the guard refuses for the rule: the reason names the rule, the remedy and the decision, and `carries`."""
    add("review-log-after-round: " + name, "deny", rule=RR_RULE, tool=tool, cwd=NOGIT, transcript=transcript,
        carries=carries, agent_id=agent_id, env=ROLE_ENV, **tool_input)


def rr_allow(name, tool, tool_input, transcript, agent_id=None):
    """A call the guard lets through silently."""
    add("review-log-after-round: " + name, "allow", tool=tool, cwd=NOGIT, transcript=transcript, silent=True,
        agent_id=agent_id, env=ROLE_ENV, **tool_input)


# Refused: a builder, test-author or handoff after a reviewer spawn that has no record after it.
rr_refuse("a builder spawn after a reviewer spawn with no review log is refused",
          "Agent", RR_BUILDER, rr_path("reviewer"))
rr_refuse("a test-author spawn after a reviewer spawn with no review log is refused",
          "Agent", RR_TEST_AUTHOR, rr_path("reviewer"))
rr_refuse("a send_message handoff after a reviewer spawn with no review log is refused",
          SEND_MESSAGE, RR_SEND, rr_path("reviewer"))
rr_refuse("a design-reviewer spawn counts like a reviewer: a builder spawn after it with no record is refused",
          "Agent", RR_BUILDER, rr_path("design-reviewer"))
rr_refuse("a reviewer spawned by Task, then a builder spawned by Task with no record, is refused",
          "Task", RR_BUILDER, rr_path("task-reviewer"))
rr_refuse("a comment without the record marker after a reviewer spawn is no record: a builder spawn is refused",
          "Agent", RR_BUILDER, rr_path("unmarked"))
rr_refuse("a record posted before the last reviewer spawn is stale: a builder spawn after it is refused",
          "Agent", RR_BUILDER, rr_path("stale-record"))
rr_refuse("round two: the round-one record does not cover a second reviewer spawn, so a builder spawn is refused",
          "Agent", RR_BUILDER, rr_path("round-two"))
rr_refuse("a reviewer spawn far up a long transcript still counts: a builder spawn with no record after it is refused",
          "Agent", RR_BUILDER, rr_path("long"))
rr_refuse("a reviewer spawn in an earlier turn still counts: an owner message after it does not reset the check",
          "Agent", RR_BUILDER, rr_path("owner-turn"))
# Allowed: no reviewer spawn, a record after the last one, an agent's own call, a spawn the rule does not judge,
# and a transcript that is missing or unreadable.
rr_allow("a builder spawn before any reviewer spawn is allowed",
         "Agent", RR_BUILDER, rr_path("builder-only"))
rr_allow("a builder spawn after a reviewer spawn and a comment with the record marker is allowed",
         "Agent", RR_BUILDER, rr_path("record"))
rr_allow("a Bash call holding the record marker after a reviewer spawn lets a builder spawn through",
         "Agent", RR_BUILDER, rr_path("bash-record"))
rr_allow("an agent's builder spawn (payload with agent_id) is not judged by this rule",
         "Agent", RR_BUILDER, rr_path("reviewer"), agent_id=RR_AGENT)
rr_allow("a send_message with no reviewer spawn in the transcript is allowed: the merge tool catches it downstream",
         SEND_MESSAGE, RR_SEND, rr_path("builder-only"))
rr_allow("an Explore spawn after a reviewer spawn is not judged", "Agent", RR_EXPLORE, rr_path("reviewer"))
rr_allow("a Plan spawn after a reviewer spawn is not judged", "Agent", RR_PLAN, rr_path("reviewer"))
rr_allow("a missing transcript file is allowed, never refused", "Agent", RR_BUILDER, rr_path("missing"))
rr_allow("an unreadable transcript (a folder) is allowed, never refused", "Agent", RR_BUILDER, rr_path("unreadable"))
# The built-in SendMessage is judged like the remote send_message: the same handoff, the same record.
# Bound under its own name: main's OUTWARD_CALLS loops below rebind a module-level `_transcript`.
import _transcript as _transcript_home  # noqa: E402  the one home of the send-tool names (lint/_transcript.py SEND_TOOLS)
RR_BUILTIN_SEND = next(name for name in _transcript_home.SEND_TOOLS if name != SEND_MESSAGE)
RR_BUILTIN_HANDOFF = {"to": "builder-pr12", "message": "Handoff: PR #12 is ready for the batch."}
rr_refuse("a built-in SendMessage handoff after a reviewer spawn with no review log is refused",
          RR_BUILTIN_SEND, RR_BUILTIN_HANDOFF, rr_path("reviewer"))
rr_allow("a built-in SendMessage handoff after a reviewer spawn and a comment with the record marker is allowed",
         RR_BUILTIN_SEND, RR_BUILTIN_HANDOFF, rr_path("record"))
# A Bash call is a post only when it posts. A read that names the marker is no record. A post whose body comes from a
# file counts on its command, since the guard cannot read the file. An inline post without the marker is no record.
rr_refuse("a Bash read that names the record marker after a reviewer spawn is no record: a builder spawn is refused",
          "Agent", RR_BUILDER, rr_path("bash-read"))
rr_allow("a gh api post whose body comes from a file after a reviewer spawn lets a builder spawn through",
         "Agent", RR_BUILDER, rr_path("bash-file-post"))
rr_allow("a gh pr comment whose body comes from a file after a reviewer spawn lets a builder spawn through",
         "Agent", RR_BUILDER, rr_path("bash-file-pr-comment"))
rr_refuse("a gh pr comment with an inline body that lacks the record marker is no record: a builder spawn is refused",
          "Agent", RR_BUILDER, rr_path("bash-inline-unmarked"))
# A reviewer spawn that another guard refused never ran, and a call inside a sidechain record is not the lane's.
rr_allow("a reviewer spawn whose result is an error does not gate: a builder spawn after it is allowed",
         "Agent", RR_BUILDER, rr_path("reviewer-error"))
rr_allow("a reviewer spawn inside a sidechain record does not gate: a builder spawn after it is allowed",
         "Agent", RR_BUILDER, rr_path("sidechain-spawn"))
rr_refuse("a record marker comment inside a sidechain record is not the lane's post: a builder spawn is refused",
          "Agent", RR_BUILDER, rr_path("sidechain-record"))
# The refusal names the design-reviewer line of the round's record, which takes the form `Round <n>: design-reviewer, ...`.
rr_refuse("a builder spawn after a design-reviewer spawn with no record: the refusal names the design-reviewer line",
          "Agent", RR_BUILDER, rr_path("design-reviewer"), carries=RR_CARRIES + ("design-reviewer",))
# A role with a capital letter or a surrounding space is the same role, as role_key reads it (guard.py). The
# lowercase cases above are the controls: they take the same path with the role spelled as the table has it.
rr_refuse("a reviewer spawned as Reviewer, then a builder spawn with no record, is refused",
          "Agent", RR_BUILDER, rr_path("reviewer-capital"))
rr_refuse("a reviewer spawned with a surrounding space, then a builder spawn with no record, is refused",
          "Agent", RR_BUILDER, rr_path("reviewer-padded"))
rr_refuse("a design-reviewer spawned as Design-reviewer, then a builder spawn with no record, is refused",
          "Agent", RR_BUILDER, rr_path("design-reviewer-capital"), carries=RR_CARRIES + ("design-reviewer",))
rr_refuse("an unrecorded reviewer, then a Builder spawn, is refused",
          "Agent", dict(RR_BUILDER, subagent_type="Builder"), rr_path("reviewer"))
rr_refuse("an unrecorded reviewer, then a Test-author spawn, is refused",
          "Agent", dict(RR_TEST_AUTHOR, subagent_type="Test-author"), rr_path("reviewer"))
rr_refuse("an unrecorded reviewer, then a ' builder ' spawn with a surrounding space, is refused",
          "Agent", dict(RR_BUILDER, subagent_type=" builder "), rr_path("reviewer"))
rr_allow("a reviewer spawned as Reviewer, then a record, lets a builder spawn through",
         "Agent", RR_BUILDER, rr_path("reviewer-capital-record"))
# The remedy names every flag merge takes with --review-record. RR_CARRIES already holds --review-record and --head.
RR_REMEDY_FLAGS = ("--kind", "--guard", "--round")
rr_refuse("the reviewer remedy names --kind, --guard and --round, the flags merge takes with --review-record",
          "Agent", RR_BUILDER, rr_path("reviewer"), carries=RR_CARRIES + RR_REMEDY_FLAGS)
rr_refuse("the design-reviewer remedy names --kind, --guard and --round, the flags merge takes with --review-record",
          "Agent", RR_BUILDER, rr_path("design-reviewer"), carries=RR_CARRIES + ("design-reviewer",) + RR_REMEDY_FLAGS)
# A background reviewer opens the gate only once its completion notice is in the transcript: its launch result is not
# the report, and no record can be posted before the agent stops. A foreground reviewer, whose result is the report,
# counts at once. A completion comes as an attachment line or as a user line; each names the spawn by its agentId.
rr_allow("an async reviewer with no completion yet: a builder spawn is allowed, since no record can be posted",
         "Agent", RR_BUILDER, rr_path("async-pending"))
rr_allow("an async reviewer with no completion yet: a send_message handoff is allowed",
         SEND_MESSAGE, RR_SEND, rr_path("async-pending"))
rr_refuse("an async reviewer completed with no record: a builder spawn after its completion is refused",
          "Agent", RR_BUILDER, rr_path("async-completed"))
rr_refuse("an async reviewer completed as a user line, with no record: a builder spawn after it is refused",
          "Agent", RR_BUILDER, rr_path("async-completed-line"))
rr_allow("an async reviewer completed and recorded: a builder spawn after the record is allowed",
         "Agent", RR_BUILDER, rr_path("async-completed-recorded"))
rr_refuse("a foreground reviewer, its result the report, counts at once: a builder spawn with no record is refused",
          "Agent", RR_BUILDER, rr_path("reviewer"))
rr_allow("a first reviewer completed and recorded, a second still pending: a builder spawn is allowed",
         "Agent", RR_BUILDER, rr_path("async-recorded-then-pending"))


def rr_cost_case():
    """The refusal starts no child process and makes no network call. The probe counts both on this run. The deny
    is asserted first, so the check passes only when the rule reached its record read."""
    got, reason, side = lb_run("Agent", {"mode": "judge", "reading": LB_NORMAL, "network": True}, RR_BUILDER,
                               own_env=ROLE_ENV, transcript=rr_session(rr_spawn("c1", "reviewer")))
    if got == "error":
        return False, reason
    if got != "deny" or RR_RULE not in reason:
        return False, "%s, want a deny that names %s: %s" % (got, RR_RULE, reason[:80])
    if side["children"]:
        return False, "%d child process(es) started: %s" % (len(side["children"]), side["children"][:3])
    if side["network"]:
        return False, "%d network call(s) made: %s" % (len(side["network"]), side["network"][:3])
    return True, "the deny names the rule, and the run starts no child process and makes no network call"


RR_COST_LABEL = "review-log-after-round: a refused builder spawn starts no child process and makes no network call"


def review_send_matcher_case():
    """A guard matcher in settings.json covers every send tool, so the guard sees each handoff the rule judges."""
    with open(os.path.join(REPO, "settings.json"), encoding="utf-8") as handle:
        entries = json.load(handle)["hooks"]["PreToolUse"]
    matchers = [entry.get("matcher", "") for entry in entries
                if any("guard.py" in hook.get("command", "") for hook in entry.get("hooks", []))]
    if not matchers:
        return False, "no PreToolUse entry runs guard.py in settings.json"
    # Every name in SEND_TOOLS is checked, so the built-in SendMessage is not left out of the matcher.
    for name in _transcript_home.SEND_TOOLS:
        if not any(re.fullmatch(matcher, name) for matcher in matchers):
            return False, "no guard matcher covers %s: %r" % (name, matchers)
    return True, "a guard matcher covers every send tool"


RR_SEND_MATCHER_LABEL = "review-log-after-round: a settings.json matcher routes every send tool to the guard"
RR_SPAN_FLAGS = ("--review-record", "--head") + RR_REMEDY_FLAGS
RR_MERGE_COMMAND = re.compile(r"`(merge [^`]*)`")


def rr_remedy_case():
    """The design-reviewer refusal prints merge commands, and each one must run. Every backticked merge command in
    the reason holds each flag of RR_SPAN_FLAGS. The whole-reason check above passes when one command has a flag
    that another lacks, so this check reads each command on its own. The deny is asserted first, so the check
    passes only when the rule reached its remedy."""
    got, reason, side = lb_run("Agent", {"mode": "judge", "reading": LB_NORMAL, "network": True}, RR_BUILDER,
                               own_env=ROLE_ENV, transcript=rr_session(rr_spawn("d1", "design-reviewer")))
    if got == "error":
        return False, reason
    if got != "deny" or RR_RULE not in reason:
        return False, "%s, want a deny that names %s: %s" % (got, RR_RULE, reason[:80])
    commands = RR_MERGE_COMMAND.findall(reason)
    if not commands:
        return False, "the reason prints no backticked merge command: %s" % reason[:80]
    for command in commands:
        for flag in RR_SPAN_FLAGS:
            if not re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(flag), command):
                return False, "the merge command %r lacks %s" % (command[:70], flag)
    return True, "every merge command the reason prints names %s" % ", ".join(RR_SPAN_FLAGS)


RR_REMEDY_LABEL = ("review-log-after-round: every merge command the design-reviewer refusal prints names "
                   "--review-record, --head, --kind, --guard and --round")


