# section 15173
FAMILY = "lane-one-topic"
#
# Rule lane-one-topic. A lane is one topic: its cs-topic tag, set at create_session beside its cs-step tags. A
# send_message whose first non-blank line is `Lane brief: <step>. Topic: <topic>.` is refused when the target's newest
# record is a lane whose cs-topic differs from the brief's Topic, or a lane with a cs-topic when the brief names no
# Topic. A lane with no cs-topic (an older lane) is judged by its cs-step tags: the brief's step must be one of them.
# A brief that clears those checks is refused too when it does not name each of Coordinator, Triage and Batch runner by
# its label. A label is a whole word, in any case: `_Triage_` and `**Batch runner:**` name their roles, while `Triaged`,
# `Triagey`, `Batch runners` and `batch-runner` do not. Nothing has to follow a label. A session id may follow it, and is
# optional. The refusal names each missing role, asks for no session id, and says none is required. Why: a lane reaches
# its coordinator, its triage session and its batch runner by role, and a brief names a role, never a session id (restart
# plan, R22 points 2 and 3). Presence only: no id is matched to a roster. A target that is no lane, and a message without
# the marker, pass. Only a marker brief reads the transcript, and a marker brief to a target with no record is refused.
LANE_ONE_TOPIC = "lane-one-topic"
SEND_MESSAGE = "mcp__claude-code-remote__send_message"
# Each reason fragment below is unique to its reason, so a case pins its own refusal. The rule id is in every reason,
# so a fragment of it pins nothing.
TOPIC_REASON = ("names a topic the lane does not hold",)
STEP_REASON = ("names a step the lane does not carry",)
STALE_REASON = ("a set_session_tags call on the target followed",)
NO_RECORD_REASON = ("holds no get_session",)
# A marker brief names each role by its label. IDS_LINES names each role with an id, LABEL_LINES with its label only. Both
# clear the role check. The constants below serve the send_message cases, the role cases and the lane-start cases of this
# section; s15303 and s29666 read LABEL_LINES and IDS_LINES from here.
ROLES = ("Coordinator", "Triage", "Batch runner")  # hard-coded: a test that read the product's list would pass whatever it held
ROLE_TOP = "Lane brief: icon-b. Topic: icons."  # the first line a step-topic-lane fixture clears
COORD_ID = "session_COORD01"
COORD_LINE = "\nCoordinator: " + COORD_ID
COORD_LABEL = "\nCoordinator"
TRIAGE_ID = "session_TRIAGE01"
TRIAGE_LINE = "\nTriage: " + TRIAGE_ID
RUNNER_ID = "session_RUNNER01"
RUNNER_LINE = "\nBatch runner: " + RUNNER_ID
IDS_LINES = COORD_LINE + TRIAGE_LINE + RUNNER_LINE  # all three roles with ids: a full brief, which clears the role check
LABEL_LINES = "\nCoordinator\nTriage\nBatch runner"  # all three roles by label only, which clears the role check too
# A role refusal names each missing role by role, in ROLES order, and names no present role as missing. It says no session
# id is required: NO_ID_LACKS is the wording a reason would hold if it asked for one.
NO_ID_LACKS = "session id is required"
# The topic, step and record refusals name no role, so the role reason's phrase is absent from them.
ROLE_PHRASE = "by role"


def step_refuse(name, transcript, message, target=ROLE_OTHER, carries=(), lacks=()):
    """A send_message the guard refuses. The reason names its rule, and the rule's own id. `lacks` names fragments
    the reason must not hold."""
    add("lane-one-topic: " + name, "deny", rule=LANE_ONE_TOPIC, tool=SEND_MESSAGE, cwd=NOGIT, transcript=transcript,
        env=ROLE_ENV, session_id=target, message=message, carries=carries, lacks=lacks)


def step_allow(name, transcript, message, target=ROLE_OTHER):
    """A send_message the guard lets through silently."""
    add("lane-one-topic: " + name, "allow", tool=SEND_MESSAGE, cwd=NOGIT, silent=True, transcript=transcript,
        env=ROLE_ENV, session_id=target, message=message)


# Refused: the brief's topic differs from the lane's. Each brief names the lane's own step, so a match on the step
# alone cannot pass it.
step_refuse("a brief for topic colors to a lane on topic icons is refused, though it names the lane's own step",
            role_path("step-topic-lane"), "Lane brief: icon-a. Topic: colors." + IDS_LINES, carries=TOPIC_REASON)
# Refused, and the steer says to start one with create_session: the sender already holds a lane, so a new lane is the
# right next step here. The create_session start's reason is split from this one, so the steer must stay on this side.
step_refuse("a brief for topic colors to a lane on topic icons keeps the steer to start one with create_session",
            role_path("step-topic-lane"), "Lane brief: icon-b. Topic: colors.",
            carries=("start one with create_session",))
# Refused: a lane with a topic gets a brief that names none. The steer names the topic, so the sender can fix it.
step_refuse("a brief that names no topic, to a lane with a topic, is refused, and the steer names the topic",
            role_path("step-topic-lane"), "Lane brief: icon-a." + IDS_LINES, carries=TOPIC_REASON)
# Refused: the match is exact. Topic icons-v2 is not topic icons, though it holds it as a substring.
step_refuse("a brief for topic icons-v2 to a lane on topic icons is refused: a substring is not the topic",
            role_path("step-topic-lane"), "Lane brief: icon-b. Topic: icons-v2." + IDS_LINES, carries=TOPIC_REASON)
# Refused: the marker is the first non-blank line, so leading blank lines do not hide it from the judge.
step_refuse("a brief after two blank lines is judged: the marker is the first non-blank line",
            role_path("step-topic-lane"), "\n\nLane brief: icon-a. Topic: colors." + IDS_LINES, carries=TOPIC_REASON)
# Refused: an older lane with no cs-topic is judged by its cs-step tags, and icon-c is not one of them.
step_refuse("a brief naming a step the older lane does not carry is refused",
            role_path("step-old-lane"), "Lane brief: icon-c. Topic: icons." + IDS_LINES, carries=STEP_REASON)
# Refused: a lane that create_session started on topic icons, with its result as JSON, then as plain text. Each
# result shape has its own fixture, so a reader that takes only one shape fails one case.
step_refuse("a brief for topic colors to a lane that create_session started on topic icons (JSON result) is refused",
            role_path("step-create-json"), "Lane brief: icon-b. Topic: colors." + IDS_LINES, target=ROLE_NEW,
            carries=TOPIC_REASON)
step_refuse("a brief for topic colors to a lane that create_session started on topic icons (plain result) is refused",
            role_path("step-create-text"), "Lane brief: icon-b. Topic: colors." + IDS_LINES, target=ROLE_NEW,
            carries=TOPIC_REASON)
# Refused: the lane's record comes back wrapped as another session's untrusted text. The topic is still read from it.
step_refuse("a brief for topic colors to a lane on topic icons, its record wrapped, is refused",
            role_path("step-topic-lane-wrapped"), "Lane brief: icon-a. Topic: colors." + IDS_LINES,
            carries=TOPIC_REASON)
# Refused: no record of the target in the transcript, so the guard cannot tell the lane's topic.
step_refuse("a marker brief to a target with no record in the transcript is refused",
            role_path("no-record"), "Lane brief: icon-b. Topic: icons." + IDS_LINES, carries=NO_RECORD_REASON)
# Refused, and paired with the cost case below: the transcript cannot be read, so a marker brief is refused.
step_refuse("a marker brief whose transcript cannot be read is refused",
            role_path("unreadable"), "Lane brief: icon-b. Topic: icons." + IDS_LINES, carries=NO_RECORD_REASON)
# Passes, the cost pair of the refusal above: a message without the marker passes with the same unreadable
# transcript, so it reads none. A guard that read the transcript for every message would refuse it here.
step_allow("a message without the marker passes with an unreadable transcript, so it reads no transcript",
           role_path("unreadable"), "Status: PR #12 merged for icon-a.")
# Passes: a status message about the lane's step, with no marker.
step_allow("a status message about the lane's step, with no marker, is allowed",
           role_path("step-topic-lane"), "Status: PR #12 merged for icon-a.")
# Passes: the marker is not the first line, so the brief is not judged, though its topic differs.
step_allow("a marker on line two is not the first line, so the brief is not judged",
           role_path("step-topic-lane"), "Status: PR #12 merged.\nLane brief: icon-a. Topic: colors.")
# Passes: one lane, one topic, many steps. A new step on the lane's own topic is allowed.
step_allow("a brief for a new step on the lane's own topic is allowed: one lane, one topic",
           role_path("step-topic-lane"), "Lane brief: icon-b. Topic: icons." + IDS_LINES)
step_allow("a brief for the lane's own step on its own topic is allowed",
           role_path("step-topic-lane"), "Lane brief: icon-a. Topic: icons." + IDS_LINES)
# Passes: an older lane with two cs-step tags and no topic is judged by its steps: the second step is one of them.
step_allow("an older lane with two cs-step tags: a brief naming its second step is allowed",
           role_path("step-old-lane"), "Lane brief: icon-b. Topic: icons." + IDS_LINES)
# Passes: a lane that create_session started on topic icons, with a new step on that topic, in both result shapes.
step_allow("a brief for a new step on topic icons to a lane that create_session started (JSON result) is allowed",
           role_path("step-create-json"), "Lane brief: icon-b. Topic: icons." + IDS_LINES, target=ROLE_NEW)
step_allow("a brief for a new step on topic icons to a lane that create_session started (plain result) is allowed",
           role_path("step-create-text"), "Lane brief: icon-b. Topic: icons." + IDS_LINES, target=ROLE_NEW)
# Passes: a brief to a target that is no lane is not judged, whatever its topic line says.
step_allow("a brief with topic colors to a target that is no lane (cs-build:triage) is allowed",
           role_path("step-triage"), "Lane brief: icon-b. Topic: colors.")
# Passes: the newest record decides. A lane read, then a newer triage read, makes the target no lane.
step_allow("the newest record decides: a lane read, then a newer triage read, lets a brief through",
           role_path("step-lane-then-triage"), "Lane brief: icon-b. Topic: colors.")
# Refused: the target's tags were set after its newest record, so the record is stale. The steer re-reads the record
# with get_session. It never tells the sender to start a new lane, for a topic lane or a lane with no topic.
step_refuse("a brief for topic icons, after set_session_tags on a topic lane, is refused: re-read the record with get_session",
            role_path("step-topic-lane-retagged"), "Lane brief: icon-b. Topic: icons." + IDS_LINES,
            carries=STALE_REASON + ("get_session",), lacks=("new lane",))
step_refuse("a brief for topic icons, after set_session_tags on a lane with no topic, is refused: re-read with get_session",
            role_path("step-old-lane-retagged"), "Lane brief: icon-b. Topic: icons." + IDS_LINES,
            carries=STALE_REASON + ("get_session",), lacks=("new lane",))
# A create_session result shaped {"session_id": ...} is a record too: the brief is judged against the lane's topic.
step_allow("a create_session result shaped session_id counts as the record: a brief for its own topic icons passes",
           role_path("step-create-session-id"), "Lane brief: icon-b. Topic: icons." + IDS_LINES, target=ROLE_NEW)
# The refusal must be the topic's, not the no-record one: a reader that misses the record refuses every brief here.
step_refuse("a create_session result shaped session_id counts as the record: a brief for topic colors is refused",
            role_path("step-create-session-id"), "Lane brief: icon-b. Topic: colors." + IDS_LINES, target=ROLE_NEW,
            carries=TOPIC_REASON, lacks=("holds no get_session",))
# Marker variants: bold, heading and lowercase all open a marker brief. Each names topic icons to a lane on colors.
step_refuse("a bold marker, **Lane brief:** x. Topic: icons., to a lane on topic colors is refused",
            role_path("step-colors-lane"), "**Lane brief:** x. Topic: icons." + IDS_LINES, carries=TOPIC_REASON)
step_refuse("a heading marker, # Lane brief: x. Topic: icons., to a lane on topic colors is refused",
            role_path("step-colors-lane"), "# Lane brief: x. Topic: icons." + IDS_LINES, carries=TOPIC_REASON)
step_refuse("a lowercase marker, lane brief: x. topic: icons., to a lane on topic colors is refused",
            role_path("step-colors-lane"), "lane brief: x. topic: icons." + IDS_LINES, carries=TOPIC_REASON)

# A brief opens with the owner's Grant line, then the marker line. The guard skips the Grant line, so the marker line is
# judged as the marker case above is: topic colors to a lane on topic icons is refused, on the topic's reason.
step_refuse("a Grant line, then a brief for topic colors to a lane on topic icons, is refused: the Grant line is skipped",
            role_path("step-topic-lane"), "Grant: B is good, 13:19 CST Nov 10\nLane brief: icon-a. Topic: colors.",
            carries=("names a topic the lane does not hold",))
# Passes, the green control beside the refusal above: a Grant line, then plain text with no marker, passes as plain
# text does with no Grant line. The Grant line alone is not a refusal.
step_allow("a Grant line, then plain status text with no marker, is allowed",
           role_path("step-topic-lane"), "Grant: B is good, 13:19 CST Nov 10\nStatus: PR #12 merged for icon-a.")
# Refused: a placeholder Grant line is no grant, as on create_session. The brief's topic matches the lane, so only the
# placeholder can refuse it.
step_refuse("a Grant line that holds a placeholder is refused, though the brief's topic matches the lane",
            role_path("step-topic-lane"), "Grant: <owner words>, <time>\nLane brief: icon-a. Topic: icons." + IDS_LINES)


BRIEF_TEMPLATE_PATH = os.path.join(REPO, "skills", "project-ops", "templates", "brief.md")
with open(BRIEF_TEMPLATE_PATH, encoding="utf-8") as handle:
    BRIEF_TEMPLATE = handle.read()


def fill_template(text):
    """The shipped brief template with its grant line and its step and topic slugs filled. Every other placeholder stays
    as shipped. The grant line gets a grant the guard takes: a placeholder grant is refused before the role check, so it
    would hide the role cause."""
    text = text.replace("Grant: <owner words>, <time>", "Grant: B is good, 13:19 CST Nov 10")
    return text.replace("<step-slug>", "icon-b").replace("<topic-slug>", "icons")


def role_carry(missing):
    """The phrases a role refusal carries: the missing roles, named by role in ROLES order, and the line that says no
    session id is required."""
    return ("does not name " + ", ".join(missing) + " by role", "none is required")


def role_lacks(missing):
    """The phrases a role refusal must not hold for the roles it does not miss. A refusal names only its missing roles."""
    return tuple("does not name " + role + " by role" for role in ROLES if role not in missing)


def roles_refuse(name, transcript, message, missing, target=ROLE_OTHER):
    """A marker brief to a lane that clears the topic and step checks, and lacks a role label: refused. The reason names
    each missing role by role, says no session id is required, names none of the test's ids, and names no present role
    as missing."""
    step_refuse(name, transcript, message, target=target, carries=role_carry(missing),
                lacks=(target, COORD_ID, TRIAGE_ID, RUNNER_ID, NO_ID_LACKS) + role_lacks(missing))


# Allowed: the three roles clear the role check, in each form a label and its id take. Each form names all three roles,
# so a failure names the one form it tests.
step_allow("a brief naming the three roles with their ids is allowed: the controls for the refusals below",
           role_path("step-topic-lane"), ROLE_TOP + IDS_LINES)
step_allow("the three roles on line one with no colons are allowed",
           role_path("step-topic-lane"), ROLE_TOP + " Coordinator session_C1; Triage session_T1; Batch runner 8 session_B1.")
step_allow("the three roles on line one in lower case with no colons are allowed: a label is read in any case",
           role_path("step-topic-lane"), ROLE_TOP + " coordinator session_C1; triage session_T1; batch runner 8 session_B1.")
step_allow("a Roles line with no colon after the labels is allowed",
           role_path("step-topic-lane"),
           ROLE_TOP + "\nRoles: Coordinator session_C1; Triage session_T1; Batch runner 8 session_B1.")
step_allow("pasted roster lines, one per role, in the Standing sessions form, are allowed",
           role_path("step-topic-lane"),
           ROLE_TOP + "\n- Coordinator: \"Claude settings coordinator handoff\", session_C1, since 2026-11-03 15:32 CST."
           "\n- Triage: \"cs triage: claude-settings (6)\", session_T1, since 2026-11-03 15:38 CST."
           "\n- Batch runner: \"claude-settings batch runner 8\", session_B1, since 2026-11-03 15:38 CST.")
step_allow("a Coordinator roster line with a note in parentheses before its quoted label is allowed",
           role_path("step-topic-lane"),
           ROLE_TOP + "\n- Coordinator (the repo's one page): \"cs coordinator (6)\", session_C1, since 2026-11-03 15:38 CST."
           + TRIAGE_LINE + RUNNER_LINE)
step_allow("a Triage roster line with a note in parentheses before its quoted label is allowed",
           role_path("step-topic-lane"),
           ROLE_TOP + "\n- Coordinator session_C1\n- Triage (the repo's one page): \"cs triage (6)\", session_T1, "
           "since 2026-11-03 15:38 CST.\n- Batch runner: session_B1")
step_allow("a Coordinator id in parentheses after its label is allowed",
           role_path("step-topic-lane"), ROLE_TOP + "\nCoordinator (session_C1)" + TRIAGE_LINE + RUNNER_LINE)
step_allow("a Coordinator id after the word is is allowed",
           role_path("step-topic-lane"), ROLE_TOP + "\nCoordinator is session_C1" + TRIAGE_LINE + RUNNER_LINE)
step_allow("a Coordinator number in parentheses before the colon is allowed",
           role_path("step-topic-lane"), ROLE_TOP + "\nCoordinator (7): session_C1" + TRIAGE_LINE + RUNNER_LINE)
step_allow("a Coordinator id in backticks is allowed",
           role_path("step-topic-lane"), ROLE_TOP + "\nCoordinator `session_C1`" + TRIAGE_LINE + RUNNER_LINE)
step_allow("the Coordinator label in bold, the colon inside the bold, is allowed",
           role_path("step-topic-lane"), ROLE_TOP + "\n**Coordinator:** session_C1" + TRIAGE_LINE + RUNNER_LINE)
step_allow("the Coordinator label in bold, the colon after the bold, is allowed",
           role_path("step-topic-lane"), ROLE_TOP + "\n**Coordinator**: session_C1" + TRIAGE_LINE + RUNNER_LINE)
step_allow("the three role labels in prose, with words around them and no session ids, are allowed",
           role_path("step-topic-lane"), ROLE_TOP + "\nAsk the Coordinator, the Triage and the Batch runner by role.")
step_allow("role labels followed by words, with no session ids, are allowed",
           role_path("step-topic-lane"),
           ROLE_TOP + "\nCoordinator (ask by role)\nTriage (page writer)\nBatch runner: the runner")
step_allow("markdown-wrapped role labels with no session ids are allowed: _Coordinator_, **Triage:** and **Batch runner**",
           role_path("step-topic-lane"), ROLE_TOP + "\n_Coordinator_\n**Triage:**\n**Batch runner**")
step_allow("the three role labels on their own lines, with no session ids, are allowed",
           role_path("step-topic-lane"), ROLE_TOP + LABEL_LINES)
step_allow("the three role labels in lower case, with no session ids, are allowed",
           role_path("step-topic-lane"), ROLE_TOP + "\ncoordinator\ntriage\nbatch runner")
step_allow("the coordinator's own brief form, verbatim, is allowed: a topic t lane, with no colons",
           role_path("step-topic-t-lane"),
           "Lane brief: x. Topic: t. Coordinator session_013NEJL2hB1pLZPDpzas7VgB; "
           "Triage session_013NEJL42Sv3tJkjpzY7bExj; Batch runner 8 session_013NEJL2vsmyKzJm8jUDt6za.")
step_allow("a brief with no roles to a target that is no lane is allowed", role_path("step-triage"), ROLE_TOP)
step_allow("the shipped brief template, grant and slugs filled, is allowed: its Ask line names the three roles",
           role_path("step-topic-lane"), fill_template(BRIEF_TEMPLATE))


# The shipped template's own role lines are checked as text in section 21305, after LOG_CHECKS_EXTRA exists.

# Allowed: a role label may have words before its id, and its colon is optional. Briefs write a label loosely, so the
# check must still read the id as that role. Each form names the other two roles with ids, so it tests one label alone.
step_allow("a Coordinator label with no colon, Coordinator session_abc123, is allowed: the colon is optional",
           role_path("step-topic-lane"), ROLE_TOP + "\nCoordinator session_abc123" + TRIAGE_LINE + RUNNER_LINE)
step_allow("a Coordinator label with words before its id, Coordinator session: session_x1, is allowed",
           role_path("step-topic-lane"), ROLE_TOP + "\nCoordinator session: session_x1" + TRIAGE_LINE + RUNNER_LINE)
step_allow("a Coordinator label with words before its id, Coordinator id: session_x1, is allowed",
           role_path("step-topic-lane"), ROLE_TOP + "\nCoordinator id: session_x1" + TRIAGE_LINE + RUNNER_LINE)
step_allow("a Coordinator id with a number, Coordinator 5:, passes",
           role_path("step-topic-lane"), ROLE_TOP + "\nCoordinator 5: session_abc123" + TRIAGE_LINE + RUNNER_LINE)
step_allow("a Coordinator id with a gloss, Coordinator (page and roadmap writer):, passes",
           role_path("step-topic-lane"),
           ROLE_TOP + "\nCoordinator (page and roadmap writer): session_abc123" + TRIAGE_LINE + RUNNER_LINE)
step_allow("a Coordinator id after other text on its line passes",
           role_path("step-topic-lane"), ROLE_TOP + "\nSee the roster. Coordinator: session_abc123." + TRIAGE_LINE + RUNNER_LINE)
step_allow("a lowercase coordinator label passes",
           role_path("step-topic-lane"), ROLE_TOP + "\ncoordinator: session_abc123" + TRIAGE_LINE + RUNNER_LINE)
step_allow("a Coordinator id on the brief's first line passes",
           role_path("step-topic-lane"), ROLE_TOP + " Coordinator: session_abc123" + TRIAGE_LINE + RUNNER_LINE)
step_allow("an italic Coordinator label, _Coordinator_: session_abc123, passes",
           role_path("step-topic-lane"), ROLE_TOP + "\n_Coordinator_: session_abc123" + TRIAGE_LINE + RUNNER_LINE)
step_allow("a backticked Coordinator id, Coordinator: `session_abc123`, passes",
           role_path("step-topic-lane"), ROLE_TOP + "\nCoordinator: `session_abc123`" + TRIAGE_LINE + RUNNER_LINE)
step_allow("a Triage label with no colon, triage session_abc123, is allowed: the colon is optional",
           role_path("step-topic-lane"), ROLE_TOP + COORD_LINE + "\ntriage session_abc123" + RUNNER_LINE)
step_allow("a Triage label with words before its id, Triage session: session_x1, is allowed",
           role_path("step-topic-lane"), ROLE_TOP + COORD_LINE + "\nTriage session: session_x1" + RUNNER_LINE)
step_allow("a Triage label with words before its id, Triage id: session_x1, is allowed",
           role_path("step-topic-lane"), ROLE_TOP + COORD_LINE + "\nTriage id: session_x1" + RUNNER_LINE)
step_allow("a Triage id with a number, Triage 5:, passes",
           role_path("step-topic-lane"), ROLE_TOP + COORD_LINE + "\nTriage 5: session_abc123" + RUNNER_LINE)
step_allow("a Triage id with a gloss, Triage (page and roadmap writer):, passes",
           role_path("step-topic-lane"),
           ROLE_TOP + COORD_LINE + "\nTriage (page and roadmap writer): session_abc123" + RUNNER_LINE)
step_allow("a Triage id after the word is is allowed",
           role_path("step-topic-lane"), ROLE_TOP + COORD_LINE + "\nTriage is session_T1" + RUNNER_LINE)
step_allow("a lowercase Triage label passes",
           role_path("step-topic-lane"), ROLE_TOP + COORD_LINE + "\ntriage: session_abc123" + RUNNER_LINE)
step_allow("a Triage id on the brief's first line passes",
           role_path("step-topic-lane"), ROLE_TOP + " Triage: session_abc123" + COORD_LINE + RUNNER_LINE)
step_allow("a bold Triage label, **Triage:** session_abc123, passes",
           role_path("step-topic-lane"), ROLE_TOP + COORD_LINE + "\n**Triage:** session_abc123" + RUNNER_LINE)
step_allow("an italic Triage label, _Triage_: session_abc123, passes",
           role_path("step-topic-lane"), ROLE_TOP + COORD_LINE + "\n_Triage_: session_abc123" + RUNNER_LINE)
step_allow("a backticked Triage id, Triage: `session_abc123`, passes",
           role_path("step-topic-lane"), ROLE_TOP + COORD_LINE + "\nTriage: `session_abc123`" + RUNNER_LINE)
step_allow("a Batch runner number, Batch runner 8: session_x8, passes",
           role_path("step-topic-lane"), ROLE_TOP + COORD_LINE + TRIAGE_LINE + "\nBatch runner 8: session_x8")
step_allow("a Batch runner number in parentheses before the colon is allowed",
           role_path("step-topic-lane"), ROLE_TOP + COORD_LINE + TRIAGE_LINE + "\nBatch runner (7): session_B1")
step_allow("a bold Batch runner label, **Batch runner:** session_abc123, passes",
           role_path("step-topic-lane"), ROLE_TOP + COORD_LINE + TRIAGE_LINE + "\n**Batch runner:** session_abc123")
step_allow("an italic Batch runner label, _Batch runner_: session_abc123, passes",
           role_path("step-topic-lane"), ROLE_TOP + COORD_LINE + TRIAGE_LINE + "\n_Batch runner_: session_abc123")
step_allow("a backticked Batch runner id, Batch runner: `session_abc123`, passes",
           role_path("step-topic-lane"), ROLE_TOP + COORD_LINE + TRIAGE_LINE + "\nBatch runner: `session_abc123`")
step_allow("a lowercase Batch runner label, batch runner: session_x8, passes",
           role_path("step-topic-lane"), ROLE_TOP + COORD_LINE + TRIAGE_LINE + "\nbatch runner: session_x8")
step_allow("an older lane's own step, with the three ids, passes", role_path("step-old-lane"),
           "Lane brief: icon-a. Topic: icons." + IDS_LINES)

# Refused: a role label is missing. Each refusal names each missing role by role, and no role that is present.
roles_refuse("a brief with no Coordinator label is refused, though its Triage and Batch runner ids are named",
             role_path("step-topic-lane"), ROLE_TOP + TRIAGE_LINE + RUNNER_LINE, ["Coordinator"])
roles_refuse("a brief with the Triage and Batch runner labels and no Coordinator label is refused",
             role_path("step-topic-lane"), ROLE_TOP + "\nTriage\nBatch runner", ["Coordinator"])
roles_refuse("a brief with no Triage label is refused, though its Coordinator and Batch runner ids are named",
             role_path("step-topic-lane"), ROLE_TOP + COORD_LINE + RUNNER_LINE, ["Triage"])
roles_refuse("a brief with the Coordinator and Batch runner labels and no Triage label is refused",
             role_path("step-topic-lane"), ROLE_TOP + "\nCoordinator\nBatch runner", ["Triage"])
roles_refuse("a brief with no Batch runner label is refused, though its Coordinator and Triage ids are named",
             role_path("step-topic-lane"), ROLE_TOP + COORD_LINE + TRIAGE_LINE, ["Batch runner"])
roles_refuse("a brief with the Coordinator and Triage labels and no Batch runner label is refused",
             role_path("step-topic-lane"), ROLE_TOP + "\nCoordinator\nTriage", ["Batch runner"])
# Refused: two or three role labels are missing, and each missing role is named.
roles_refuse("a brief naming the Coordinator only, with its id, is refused: Triage and Batch runner are missing",
             role_path("step-topic-lane"), ROLE_TOP + COORD_LINE, ["Triage", "Batch runner"])
roles_refuse("a brief naming the Coordinator only, with no id, is refused: Triage and Batch runner are missing",
             role_path("step-topic-lane"), ROLE_TOP + COORD_LABEL, ["Triage", "Batch runner"])
roles_refuse("a brief naming Triage only, with its id, is refused: Coordinator and Batch runner are missing",
             role_path("step-topic-lane"), ROLE_TOP + TRIAGE_LINE, ["Coordinator", "Batch runner"])
roles_refuse("a brief naming Batch runner only, with its id, is refused: Coordinator and Triage are missing",
             role_path("step-topic-lane"), ROLE_TOP + RUNNER_LINE, ["Coordinator", "Triage"])
roles_refuse("a brief with no role labels is refused: all three roles are missing",
             role_path("step-topic-lane"), ROLE_TOP, ROLES)
roles_refuse("three session ids with no role labels are refused: an id names no role by itself",
             role_path("step-topic-lane"), ROLE_TOP + " session_COORD01 session_TRIAGE01 session_RUNNER01.", ROLES)
# Refused: a near miss of a label is no label, as a whole word or in its form. Each keeps the other two labels present.
roles_refuse("subtriage is not the Triage label: a brief naming subtriage for Triage is refused",
             role_path("step-topic-lane"), ROLE_TOP + COORD_LINE + "\nsubtriage: session_TRIAGE01" + RUNNER_LINE, ["Triage"])
roles_refuse("Triagey is not the Triage label: a brief naming Triagey is refused",
             role_path("step-topic-lane"), ROLE_TOP + COORD_LINE + "\nTriagey: session_TRIAGE01" + RUNNER_LINE, ["Triage"])
roles_refuse("Triaged is not the Triage label: a label must stand as a whole word",
             role_path("step-topic-lane"), ROLE_TOP + "\nCoordinator\nTriaged\nBatch runner", ["Triage"])
roles_refuse("a Pretriage label is no Triage label: a brief naming Pretriage is refused",
             role_path("step-topic-lane"), ROLE_TOP + COORD_LINE + "\nPretriage: session_x1" + RUNNER_LINE, ["Triage"])
roles_refuse("a Page writer label is no role: a brief naming a Page writer id for Triage is refused",
             role_path("step-topic-lane"), ROLE_TOP + COORD_LINE + "\nPage writer: session_x1" + RUNNER_LINE, ["Triage"])
roles_refuse("Batch runners is not the Batch runner label: the plural is another word",
             role_path("step-topic-lane"), ROLE_TOP + "\nCoordinator\nTriage\nBatch runners", ["Batch runner"])
roles_refuse("the batch-runner tag form is not the Batch runner label: it has no space",
             role_path("step-topic-lane"), ROLE_TOP + "\nCoordinator\nTriage\nbatch-runner", ["Batch runner"])
roles_refuse("a double space in Batch  runner is not the Batch runner label: the label is one space wide",
             role_path("step-topic-lane"), ROLE_TOP + "\nCoordinator\nTriage\nBatch  runner", ["Batch runner"])
roles_refuse("Coordinators is not the Coordinator label: a brief naming Coordinators is refused",
             role_path("step-topic-lane"), ROLE_TOP + "\nCoordinators: session_COORD01" + TRIAGE_LINE + RUNNER_LINE, ["Coordinator"])
roles_refuse("Coordinators-only is not the Coordinator label: a whole word is needed, and a plural is another word",
             role_path("step-topic-lane"), ROLE_TOP + "\nCoordinators-only\nTriage\nBatch runner", ["Coordinator"])
roles_refuse("Coordinatored is not the Coordinator label: a label must stand as a whole word",
             role_path("step-topic-lane"), ROLE_TOP + "\nCoordinatored: session_COORD01" + TRIAGE_LINE + RUNNER_LINE, ["Coordinator"])
roles_refuse("subcoordinator is not the Coordinator label: a label is no part of a longer word",
             role_path("step-topic-lane"), ROLE_TOP + "\nsubcoordinator: session_COORD01" + TRIAGE_LINE + RUNNER_LINE, ["Coordinator"])
roles_refuse("a Precoordinator label is no Coordinator label: a brief naming Precoordinator is refused",
             role_path("step-topic-lane"), ROLE_TOP + "\nPrecoordinator: session_x1" + TRIAGE_LINE + RUNNER_LINE, ["Coordinator"])
# Refused: a fresh lane and an older lane, each missing one role label, refuse on the role check.
roles_refuse("a brief for the lane's own topic, to a fresh lane with no Triage label, is refused",
             role_path("step-create-json"), ROLE_TOP + COORD_LINE + RUNNER_LINE, ["Triage"], target=ROLE_NEW)
roles_refuse("a brief for the lane's own topic, to a fresh lane with no Coordinator label, is refused",
             role_path("step-create-json"), ROLE_TOP + TRIAGE_LINE + RUNNER_LINE, ["Coordinator"], target=ROLE_NEW)
roles_refuse("a brief for an older lane's own step, with no Triage label, is refused",
             role_path("step-old-lane"), "Lane brief: icon-a. Topic: icons." + COORD_LINE + RUNNER_LINE, ["Triage"])
roles_refuse("a brief for an older lane's own step, with no Coordinator label, is refused",
             role_path("step-old-lane"), "Lane brief: icon-a. Topic: icons." + TRIAGE_LINE + RUNNER_LINE, ["Coordinator"])

# Refused with the topic, step and record reasons: the role check runs after those, so a brief that fails them keeps its
# own reason. The lacks check holds the role reason's phrase out of each of them.
step_refuse("a brief for topic colors to a lane on topic icons, with no role ids, keeps the topic reason",
            role_path("step-topic-lane"), "Lane brief: icon-b. Topic: colors.",
            carries=TOPIC_REASON, lacks=(ROLE_PHRASE,))
step_refuse("a brief naming a step the older lane does not carry, with no role ids, keeps the step reason",
            role_path("step-old-lane"), "Lane brief: icon-c. Topic: icons.",
            carries=STEP_REASON, lacks=(ROLE_PHRASE,))
step_refuse("a brief with no role ids to a target with no record keeps the no-record reason",
            role_path("no-record"), "Lane brief: icon-b. Topic: icons.",
            carries=("holds no get_session",), lacks=(ROLE_PHRASE,))
step_refuse("a brief with no role ids and an unreadable transcript keeps the no-record reason",
            role_path("unreadable"), "Lane brief: icon-b. Topic: icons.",
            carries=("holds no get_session",), lacks=(ROLE_PHRASE,))


# ---- A lane start names each role by its label too (rule lane-one-topic). The start's prompt is the owner's grant,
# then the brief, and its ids may sit on any line. The constants below live here, not in the rule-9 section (s29666),
# because sections load in number order and this one loads first; s29666 and s30130 read them from here.
LANE_GRANT = "Grant: B is good, 13:19 CST Nov 10"
LANE_EFFORT_FIELD = "medium"
# A lane call names the model it starts on and the repo it starts from. Each allowed start below carries both.
LANE_SOURCE_URL = "https://github.com/shivinate7/claude-settings"
OWN_LANE_TAGS = ["cs-build:lane", "cs-repo:shivinate7/claude-settings"]
# A start is built as the rule-9 starts are. Its cwd is NOGIT, not a checkout: a full cs-repo tag passes the repo-tag rule
# with no origin read, so no fixture repo is needed here.
START_TOPIC_TAGS = OWN_LANE_TAGS + ["cs-topic:alpha"]
OLD_START_TAGS = OWN_LANE_TAGS + ["cs-step:icon-a"]
START_BRIEF = LANE_GRANT + "\nLane brief: icon-a. Topic: alpha."
START_TOPIC_REASON = ("names a topic that the start's cs-topic tag does not hold",)


def start_refuse(name, prompt, tags=START_TOPIC_TAGS, carries=(), lacks=()):
    """A create_session start the guard refuses under lane-one-topic. It carries the effort, model and source that the
    other start rules judge, so the refusal is this rule's alone."""
    add("lane-one-topic: " + name, "deny", rule=LANE_ONE_TOPIC, tool=CREATE_SESSION, cwd=NOGIT, prompt=prompt,
        tags=tags, effort=LANE_EFFORT_FIELD, model="sonnet", source_url=LANE_SOURCE_URL,
        carries=carries, lacks=lacks)


def start_allow(name, prompt, tags=START_TOPIC_TAGS):
    """A create_session start the guard lets through."""
    add("lane-one-topic: " + name, "allow", tool=CREATE_SESSION, cwd=NOGIT, prompt=prompt, tags=tags,
        effort=LANE_EFFORT_FIELD, model="sonnet", source_url=LANE_SOURCE_URL)


ROLE_START_LACKS = ("start one with create_session", COORD_ID, TRIAGE_ID, RUNNER_ID, NO_ID_LACKS)


def start_roles_refuse(name, prompt, missing, tags=START_TOPIC_TAGS):
    """A start that clears the topic or step check and lacks a role label: refused. The reason names each missing role by
    role, says no session id is required, names none of the test's ids, and names no present role as missing. It steers to
    no new start, since this call is the start."""
    start_refuse(name, prompt, tags=tags, carries=role_carry(missing), lacks=ROLE_START_LACKS + role_lacks(missing))


# Refused: a start that clears the topic check and lacks a role label. Each names the roles it misses, as a send does.
start_roles_refuse("a start for topic alpha, with its brief and no role labels, is refused", START_BRIEF, ROLES)
start_roles_refuse("a start for topic alpha with no Coordinator label is refused, though its Triage and Batch runner ids are named",
                   START_BRIEF + TRIAGE_LINE + RUNNER_LINE, ["Coordinator"])
start_roles_refuse("a start for topic alpha with no Triage label is refused, though its Coordinator and Batch runner ids are named",
                   START_BRIEF + COORD_LINE + RUNNER_LINE, ["Triage"])
start_roles_refuse("a start for topic alpha with no Batch runner label is refused, though its Coordinator and Triage ids are named",
                   START_BRIEF + COORD_LINE + TRIAGE_LINE, ["Batch runner"])
start_roles_refuse("a start for topic alpha with the Triage and Batch runner labels and no Coordinator label is refused",
                   START_BRIEF + "\nTriage\nBatch runner", ["Coordinator"])
start_roles_refuse("a start for topic alpha with the Coordinator and Batch runner labels and no Triage label is refused",
                   START_BRIEF + "\nCoordinator\nBatch runner", ["Triage"])
start_roles_refuse("a start for topic alpha with the Coordinator and Triage labels and no Batch runner label is refused",
                   START_BRIEF + "\nCoordinator\nTriage", ["Batch runner"])
start_roles_refuse("a start for topic alpha that names the Coordinator only, with its id, is refused",
                   START_BRIEF + COORD_LINE, ["Triage", "Batch runner"])
start_roles_refuse("a start for topic alpha that names the Coordinator only, with no id, is refused",
                   START_BRIEF + COORD_LABEL, ["Triage", "Batch runner"])
start_roles_refuse("a start for topic alpha that names Triage only, with its id, is refused",
                   START_BRIEF + TRIAGE_LINE, ["Coordinator", "Batch runner"])
start_roles_refuse("a start for topic alpha that names Batch runner only, with its id, is refused",
                   START_BRIEF + RUNNER_LINE, ["Coordinator", "Triage"])
start_roles_refuse("a start for topic alpha with Triaged for Triage is refused: a label must stand as a whole word",
                   START_BRIEF + "\nCoordinator\nTriaged\nBatch runner", ["Triage"])
start_roles_refuse("a start for topic alpha with Coordinators for Coordinator is refused: the plural is another word",
                   START_BRIEF + "\nCoordinators: session_COORD01" + TRIAGE_LINE + RUNNER_LINE, ["Coordinator"])
# Refused: an older lane, with a cs-step tag and no cs-topic, is judged by its step, and its start names no role label.
start_roles_refuse("an older-lane start for step icon-a with no role labels is refused",
                   LANE_GRANT + "\nLane brief: icon-a. Topic: icons.", ROLES, tags=OLD_START_TAGS)
start_roles_refuse("an older-lane start for step icon-a with no Coordinator label is refused, though its Triage and Batch runner ids are named",
                   LANE_GRANT + "\nLane brief: icon-a. Topic: icons." + TRIAGE_LINE + RUNNER_LINE, ["Coordinator"],
                   tags=OLD_START_TAGS)
start_roles_refuse("an older-lane start for step icon-a with the Coordinator id only is refused",
                   LANE_GRANT + "\nLane brief: icon-a. Topic: icons." + COORD_LINE, ["Triage", "Batch runner"],
                   tags=OLD_START_TAGS)
# Allowed: the controls for the refusals above. The same start for topic alpha with all three ids, or with all three labels.
start_allow("a start for topic alpha with the coordinator, triage and batch runner ids is allowed", START_BRIEF + IDS_LINES)
start_allow("a start for topic alpha with the three role labels and no ids is allowed", START_BRIEF + LABEL_LINES)
start_allow("an older-lane start for step icon-a with the three role ids is allowed",
            LANE_GRANT + "\nLane brief: icon-a. Topic: icons." + IDS_LINES, tags=OLD_START_TAGS)
start_allow("an older-lane start for step icon-a with the three role labels and no ids is allowed",
            LANE_GRANT + "\nLane brief: icon-a. Topic: icons." + LABEL_LINES, tags=OLD_START_TAGS)
# Refused on the topic, as before: a start whose brief names topic colors on a lane of topic alpha. The ids do not rescue
# a wrong topic, and with no ids the topic reason still wins over the role reason. The topic refusal of a start names no
# session id, so `session id` tells it apart from the role reason, which asks for none.
start_refuse("a start for topic colors on a lane of topic alpha, with all three role ids, is refused on the topic",
             LANE_GRANT + "\nLane brief: icon-a. Topic: colors." + IDS_LINES,
             carries=START_TOPIC_REASON, lacks=("session id",))
start_refuse("a start for topic colors on a lane of topic alpha, with no role ids, is refused on the topic",
             LANE_GRANT + "\nLane brief: icon-a. Topic: colors.",
             carries=START_TOPIC_REASON, lacks=("session id",))


# =========================================================================== a header stamp matches the clock
