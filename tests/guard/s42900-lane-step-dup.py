# section 42900
FAMILY = "lane-step-dup"
#
# Rule lane-step-dup, part one: a live session carries the step. A create_session whose tags hold cs-step:<slug>, or a
# send_message whose first non-blank line is `Lane brief: <slug>. Topic: <topic>.`, is refused when another live session
# in the same cs-repo carries <slug> as a cs-step tag. The refusal names that session's id. The guard reads this
# session's transcript: the list_sessions reads, their cursors, and the target's get_session record. A list that is not
# whole (one read with no cursor, or a chain of reads whose cursor is the last row of the page before, ending with
# has_more false), or that cannot be parsed, is refused. Archived sessions, other steps and other repos hold no step.
# Part two (open pull requests) is in the lane-step-dup-pr section, so the two can be held apart.
STEPDUP_RULE = "lane-step-dup"
STEPDUP_LIVE = "SESSION_STATUS_RUNNING"
STEPDUP_ARCHIVED = "SESSION_STATUS_ARCHIVED"
STEPDUP_CARRIER = "session_STEPDUPCARRIER01"  # a live lane on the topic that carries dup-step-a
STEPDUP_NEW = "session_STEPDUPNEW01"          # a live lane on the same topic that carries no step of the brief
STEPDUP_CARRIER_TAGS = ["cs-build:lane", "cs-topic:dup-topic", "cs-step:dup-step-a", "cs-repo:o/r"]
STEPDUP_NEW_TAGS = ["cs-build:lane", "cs-topic:dup-topic", "cs-repo:o/r"]
STEPDUP_NEAR_TAGS = ["cs-build:lane", "cs-topic:dup-topic", "cs-step:dup-step-ab", "cs-repo:o/r"]
STEPDUP_OTHER_REPO_TAGS = ["cs-build:lane", "cs-topic:dup-topic", "cs-step:dup-step-a", "cs-repo:other/repo"]
STEPDUP_UPPER_TAGS = ["cs-build:lane", "cs-topic:dup-topic", "cs-step:DUP-STEP-A", "cs-repo:o/r"]
STEPDUP_BRIEF = "Lane brief: dup-step-a. Topic: dup-topic.\n\nDo the step."
# A stand-in pull request tool whose only pull request on a slug is closed, so no slug in these cases is held by an open one.
STEPDUP_NO_OPEN_PR = fake_gh_path(ARCHCLOSED)


def stepdup_row(sid, status, tags):
    """One list_sessions row: the keys the tool returns for a session, with `tags` as a list."""
    return {"id": sid, "title": "a lane session", "session_status": status, "tags": list(tags)}


def stepdup_list(tool_id, rows, more=False, args=None, cut=False):
    """One list_sessions call and its result: `rows` in one wrapped record. `more` sets has_more, a read that is not the
    last page. `args` is the call's input: an after_id cursor makes the read a page of a chain. `cut` drops the end of
    the result, so the text is not a whole record."""
    body = role_wrapped(json.dumps({"ccr": {"data": list(rows), "has_more": more}}))
    return [role_use(tool_id, LIST_SESSIONS, dict(args or {})), role_result(tool_id, body[:-40] if cut else body)]


def stepdup_fill(count):
    """`count` live lanes on other steps: the rows a full page holds before its last row."""
    return [stepdup_row("session_STEPDUPFILL%03d" % n, STEPDUP_LIVE,
                        ["cs-build:lane", "cs-step:stepdup-filler-%03d" % n, "cs-repo:o/r"]) for n in range(count)]


def stepdup_noise():
    """One unrelated Bash call and its result: a transcript with no list_sessions read in it."""
    return [role_use("b1", "Bash", {"command": "git status"}), role_result("b1", "ok")]


STEPDUP_CARRIER_ROW = stepdup_row(STEPDUP_CARRIER, STEPDUP_LIVE, STEPDUP_CARRIER_TAGS)
STEPDUP_PAGE_A = stepdup_row("session_STEPDUPPAGEA", STEPDUP_LIVE, ["cs-build:lane", "cs-step:dup-step-b", "cs-repo:o/r"])
STEPDUP_PAGE_B = stepdup_row("session_STEPDUPPAGEB", STEPDUP_LIVE, ["cs-build:lane", "cs-step:dup-step-c", "cs-repo:o/r"])

# Each fixture is one session's transcript: the reads the rule judges, in the order they were made.
STEPDUP_LINES = {
    # One whole read of one page.
    "stepdup-create-carrier": stepdup_list("l1", [STEPDUP_CARRIER_ROW]),
    "stepdup-create-carrier-upper": stepdup_list("l1", [stepdup_row(STEPDUP_CARRIER, STEPDUP_LIVE, STEPDUP_UPPER_TAGS)]),
    "stepdup-create-archived": stepdup_list("l1", [stepdup_row(STEPDUP_CARRIER, STEPDUP_ARCHIVED, STEPDUP_CARRIER_TAGS)]),
    "stepdup-create-near": stepdup_list("l1", [stepdup_row(STEPDUP_CARRIER, STEPDUP_LIVE, STEPDUP_NEAR_TAGS)]),
    "stepdup-create-other-repo": stepdup_list("l1", [stepdup_row(STEPDUP_CARRIER, STEPDUP_LIVE, STEPDUP_OTHER_REPO_TAGS)]),
    "stepdup-create-empty": stepdup_list("l1", []),
    "stepdup-create-full": stepdup_list("l1", stepdup_fill(39) + [STEPDUP_CARRIER_ROW]),
    "stepdup-create-cut": stepdup_list("l1", [STEPDUP_CARRIER_ROW], cut=True),
    "stepdup-create-no-read": stepdup_noise(),
    # A chain of two reads: the second names the last row of the first by after_id.
    "stepdup-create-chain-empty": stepdup_list("l1", [STEPDUP_PAGE_A, STEPDUP_PAGE_B], more=True)
                                  + stepdup_list("l2", [], args={"after_id": STEPDUP_PAGE_B["id"]}),
    "stepdup-create-chain-carrier-first": stepdup_list("l1", [STEPDUP_CARRIER_ROW, STEPDUP_PAGE_B], more=True)
                                          + stepdup_list("l2", [], args={"after_id": STEPDUP_PAGE_B["id"]}),
    "stepdup-create-chain-carrier-second": stepdup_list("l1", [STEPDUP_PAGE_A, STEPDUP_PAGE_B], more=True)
                                           + stepdup_list("l2", [STEPDUP_CARRIER_ROW], args={"after_id": STEPDUP_PAGE_B["id"]}),
    "stepdup-create-chain-wrong-cursor": stepdup_list("l1", [STEPDUP_PAGE_A, STEPDUP_PAGE_B], more=True)
                                         + stepdup_list("l2", [], args={"after_id": STEPDUP_PAGE_A["id"]}),
    "stepdup-create-chain-incomplete": stepdup_list("l1", [STEPDUP_CARRIER_ROW], more=True),
    # A brief: the target is a lane on the brief's topic, read with get_session, then the list read.
    "stepdup-send-carrier": role_target_call("t0", STEPDUP_NEW_TAGS, target=STEPDUP_NEW, wrapped=True)
                            + stepdup_list("l1", [STEPDUP_CARRIER_ROW]),
    "stepdup-send-self": role_target_call("t0", STEPDUP_CARRIER_TAGS, target=STEPDUP_CARRIER, wrapped=True)
                         + stepdup_list("l1", [STEPDUP_CARRIER_ROW]),
    "stepdup-send-empty": role_target_call("t0", STEPDUP_NEW_TAGS, target=STEPDUP_NEW, wrapped=True)
                          + stepdup_list("l1", []),
    "stepdup-send-no-read": role_target_call("t0", STEPDUP_NEW_TAGS, target=STEPDUP_NEW, wrapped=True),
    "stepdup-send-target-only": role_target_call("t0", STEPDUP_CARRIER_TAGS, target=STEPDUP_CARRIER, wrapped=True),
}


def write_stepdup_transcripts():
    """Write each fixture as JSONL under this run's role folder."""
    os.makedirs(ROLE_DIR, exist_ok=True)
    for name, lines in STEPDUP_LINES.items():
        with open(role_path(name), "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")


lazy_fixture([role_path(name) for name in STEPDUP_LINES], write_stepdup_transcripts)


def stepdup_create(name, expected, transcript, tags, prompt=LANE_PROMPT, carries=(), lacks=(), env_path=STEPDUP_NO_OPEN_PR):
    """A create_session the rule judges. The call is a lane start that passes the lane rules (its Grant line, effort,
    model and source), so only lane-step-dup decides it. An allow must print nothing."""
    add("lane-step-dup: " + name, expected, rule=None if expected == "allow" else STEPDUP_RULE, tool=CREATE_SESSION,
        cwd=NOGIT, transcript=transcript, env=ROLE_ENV, silent=expected == "allow", carries=carries, lacks=lacks,
        env_path=env_path, title="a lane session", tags=list(tags), prompt=prompt, effort=LANE_EFFORT_FIELD,
        model="sonnet", source_url=LANE_SOURCE_URL)


def stepdup_send(name, expected, transcript, message, target=STEPDUP_NEW, carries=(), lacks=(), env_path=STEPDUP_NO_OPEN_PR):
    """A send_message the rule judges. The target's own record is in the transcript, so lane-one-topic passes the brief
    and only lane-step-dup decides it. An allow must print nothing."""
    add("lane-step-dup: " + name, expected, rule=None if expected == "allow" else STEPDUP_RULE, tool=SEND_MESSAGE,
        cwd=NOGIT, transcript=transcript, env=ROLE_ENV, silent=expected == "allow", carries=carries, lacks=lacks,
        env_path=env_path, session_id=target, message=message)


STEP_CREATE_TAGS = ["cs-build:lane", "cs-step:dup-step-a", "cs-repo:o/r"]

# Refused: a live session carries the step. The refusal names that session.
stepdup_create("a create_session tagged cs-step:dup-step-a is refused while a live session in the cs-repo carries it, and names that session",
               "deny", role_path("stepdup-create-carrier"), STEP_CREATE_TAGS, carries=STEPDUP_CARRIER)
stepdup_send("a brief for dup-step-a to a new lane is refused while a live session carries the step, and names that session",
             "deny", role_path("stepdup-send-carrier"), STEPDUP_BRIEF, carries=STEPDUP_CARRIER)
# Refused: the carrier is read from a chain's second page, so the chain is read to its end.
stepdup_create("a create_session tagged cs-step:dup-step-a is refused when the live carrier is on the second page of a whole chain",
               "deny", role_path("stepdup-create-chain-carrier-second"), STEP_CREATE_TAGS, carries=STEPDUP_CARRIER)
# Refused: the carrier is on the first page, and the second page holds no carrier. A reader that keeps only the last page
# of a chain misses it.
stepdup_create("a create_session tagged cs-step:dup-step-a is refused when the live carrier is on the first page of a whole chain",
               "deny", role_path("stepdup-create-chain-carrier-first"), STEP_CREATE_TAGS, carries=STEPDUP_CARRIER)
# Refused: the carrier is on a page that says more pages follow, and no later page was read.
stepdup_create("a create_session tagged cs-step:dup-step-a is refused when the live carrier is on an incomplete first page",
               "deny", role_path("stepdup-create-chain-incomplete"), STEP_CREATE_TAGS, carries=STEPDUP_CARRIER)
# Refused: a page of forty rows, the carrier as its last row. A reader that stops before a page's last row misses it.
stepdup_create("a create_session tagged cs-step:dup-step-a is refused when the carrier is the last row of a full page of forty",
               "deny", role_path("stepdup-create-full"), STEP_CREATE_TAGS, carries=STEPDUP_CARRIER)
# Refused: a step tag in capitals is the same step as the carrier's lower-case tag.
stepdup_create("a create_session tagged cs-step:DUP-STEP-A is refused by a live carrier of dup-step-a, and names it",
               "deny", role_path("stepdup-create-carrier"), ["cs-build:lane", "cs-step:DUP-STEP-A", "cs-repo:o/r"],
               carries=STEPDUP_CARRIER)
# Refused: the carrier's tag is in capitals, and the create's tag is lower case.
stepdup_create("a create_session tagged cs-step:dup-step-a is refused by a live carrier whose step tag is in capitals, and names it",
               "deny", role_path("stepdup-create-carrier-upper"), STEP_CREATE_TAGS, carries=STEPDUP_CARRIER)
# Refused: without a whole list read, the guard cannot tell whether a live session carries the step.
stepdup_create("a create_session tagged cs-step:dup-step-a is refused when this session has no list_sessions read",
               "deny", role_path("stepdup-create-no-read"), STEP_CREATE_TAGS)
stepdup_send("a brief for dup-step-a is refused when this session has no list_sessions read",
             "deny", role_path("stepdup-send-no-read"), STEPDUP_BRIEF)
# Refused: the list read's text is cut, so its rows are text and not a read.
stepdup_create("a create_session tagged cs-step:dup-step-a is refused when the list_sessions read is cut short",
               "deny", role_path("stepdup-create-cut"), STEP_CREATE_TAGS)
# Refused: the second read's cursor is not the last row of the first page, so the two reads are not one list. The second
# page is empty, so a reader that joined the pages without checking the cursor would allow the create.
stepdup_create("a create_session tagged cs-step:dup-step-a is refused when the second read's cursor is not the first page's last row",
               "deny", role_path("stepdup-create-chain-wrong-cursor"), STEP_CREATE_TAGS)

# Allowed: each shape changes one fact of a refused case. These keep the rule narrow.
stepdup_send("a brief to the live carrier itself is allowed: the target already carries the step",
             "allow", role_path("stepdup-send-self"), STEPDUP_BRIEF, target=STEPDUP_CARRIER)
# Allowed: the target's own record carries the step, and the transcript holds no list read. The brief goes to the carrier.
stepdup_send("a brief to a target that carries the step is allowed with no list_sessions read in the transcript",
             "allow", role_path("stepdup-send-target-only"), STEPDUP_BRIEF, target=STEPDUP_CARRIER)
stepdup_create("a create_session tagged cs-step:dup-step-a is allowed when the carrier is archived",
               "allow", role_path("stepdup-create-archived"), STEP_CREATE_TAGS)
stepdup_create("a create_session tagged cs-step:dup-step-a is allowed when a whole read finds no live session on it",
               "allow", role_path("stepdup-create-empty"), STEP_CREATE_TAGS)
stepdup_create("a create_session tagged cs-step:dup-step-c is allowed when the live carrier holds only dup-step-a",
               "allow", role_path("stepdup-create-carrier"), ["cs-build:lane", "cs-step:dup-step-c", "cs-repo:o/r"])
stepdup_create("a create_session tagged cs-step:dup-step-a is allowed when the live carrier holds only dup-step-ab: a step id is exact",
               "allow", role_path("stepdup-create-near"), STEP_CREATE_TAGS)
stepdup_create("a create_session tagged cs-step:dup-step-a is allowed when the live carrier is in another cs-repo",
               "allow", role_path("stepdup-create-other-repo"), STEP_CREATE_TAGS)
stepdup_create("a create_session tagged cs-step:dup-step-a is allowed when a two-page chain holds no live session on it",
               "allow", role_path("stepdup-create-chain-empty"), STEP_CREATE_TAGS)
