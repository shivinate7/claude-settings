# section 15173
FAMILY = "lane-one-topic"
#
# Rule lane-one-topic. A lane is one topic: its cs-topic tag, set at create_session beside its cs-step tags. A
# send_message whose first non-blank line is `Lane brief: <step>. Topic: <topic>.` is refused when the target's newest
# record is a lane whose cs-topic differs from the brief's Topic, or a lane with a cs-topic when the brief names no
# Topic. A lane with no cs-topic (an older lane) is judged by its cs-step tags: the brief's step must be one of them.
# A brief that clears those checks is refused too when it does not name each of Coordinator, Triage and Batch runner by
# its label. A label is a whole word, in any case: `_Triage_` and `**Triage:**` name Triage, while `Triaged`, `Triagey`
# and `Coordinators` do not. Nothing has to follow a label. A session id may follow it, and is optional. The refusal names
# the missing labels and asks for no session id. Why: a lane reaches its coordinator, its triage session and its batch
# runner by role, so a brief that names no role leaves the lane unable to tell who is who. Presence only: no id is matched
# to a roster. A target that is no lane, and a message without the marker, pass. Only a marker brief reads the transcript,
# and a marker brief to a target with no record is refused.
LANE_ONE_TOPIC = "lane-one-topic"
SEND_MESSAGE = "mcp__claude-code-remote__send_message"
# Each reason fragment below is unique to its reason, so a case pins its own refusal. The rule id is in every reason,
# so a fragment of it pins nothing.
TOPIC_REASON = ("names a topic the lane does not hold",)
STEP_REASON = ("names a step the lane does not carry",)
STALE_REASON = ("a set_session_tags call on the target followed",)
NO_RECORD_REASON = ("holds no get_session",)
# A marker brief to a lane names each role by its label. IDS_LINES names each role with an id, LABEL_LINES with its label
# only. Both are appended to the marker briefs that must clear the role check: the allow cases, and the topic, step, stale
# and no-record refusals, so each of those refuses on its own check alone. A role refusal keeps the other two labels
# present, so a failure names the one role it tests.
COORD_ID = "session_COORD01"
COORD_LINE = "\nCoordinator: " + COORD_ID
TRIAGE_ID = "session_TRIAGE01"
TRIAGE_LINE = "\nTriage: " + TRIAGE_ID
RUNNER_ID = "session_RUNNER01"
RUNNER_LINE = "\nBatch runner: " + RUNNER_ID
IDS_LINES = COORD_LINE + TRIAGE_LINE + RUNNER_LINE
LABEL_LINES = "\nCoordinator\nTriage\nBatch runner"
# The form the old id refusal named. The refusal now carries none of it (ROLE_LACKS), so a role refusal has no form to
# strip. outside_form in hooks/test_guard.py still reads this list.
BRIEF_ROLE_FORM = ("Coordinator: session_", "Triage: session_", "Batch runner: session_")
# A role refusal asks for no session id and names no gap limit: a label is all the brief needs.
ROLE_LACKS = ("session_<id>", "80 char")


def roles_refuse(name, transcript, message, missing, target=ROLE_OTHER):
    """A marker brief to a lane that clears the topic and step checks, and lacks a role label: refused. The reason names
    each missing role, asks for no session id, and names none of the test's ids."""
    step_refuse(name, transcript, message, target=target,
                lacks=(target, COORD_ID, TRIAGE_ID, RUNNER_ID) + ROLE_LACKS, names=missing)


def step_refuse(name, transcript, message, target=ROLE_OTHER, carries=(), lacks=(), names=()):
    """A send_message the guard refuses. The reason names its rule, and the rule's own id. `lacks` names fragments
    the reason must not hold, and `names` fragments it must name outside BRIEF_ROLE_FORM."""
    add("lane-one-topic: " + name, "deny", rule=LANE_ONE_TOPIC, tool=SEND_MESSAGE, cwd=NOGIT, transcript=transcript,
        env=ROLE_ENV, session_id=target, message=message, carries=carries, lacks=lacks, names=names)


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

# A marker brief to a lane names each role by its label. Each refusal below misses one label, and the other two stay
# present, so a failure names the one cause it tests.
ROLE_TOP = "Lane brief: icon-b. Topic: icons."  # the first line a step-topic-lane fixture clears
BRIEF_TEMPLATE_PATH = os.path.join(REPO, "skills", "project-ops", "templates", "brief.md")
with open(BRIEF_TEMPLATE_PATH, encoding="utf-8") as handle:
    BRIEF_TEMPLATE = handle.read()
BRIEF_TEMPLATE_IDS = {"Coordinator": "session_TPLCOORD01", "Triage": "session_TPLTRIAGE01",
                      "Batch runner": "session_TPLRUNNER01"}


def fill_template(text, ids=None):
    """The brief template with its grant line, step and topic slugs filled, and each `<label>: session_<id>` placeholder
    filled from `ids` when it is given. Every other placeholder stays as shipped. The grant line gets a grant the guard
    takes: a placeholder grant is refused before the role check, so it would hide the role cause."""
    text = text.replace("Grant: <owner words>, <time>", "Grant: B is good, 13:19 CST Nov 10")
    text = text.replace("<step-slug>", "icon-b").replace("<topic-slug>", "icons")
    for label, session in (ids or {}).items():
        text = text.replace(label + ": session_<id>", label + ": " + session)
    return text


# Allowed: a role label may take no colon, and a number may sit beside it.
step_allow("the three roles on line one with no colons are allowed",
           role_path("step-topic-lane"),
           ROLE_TOP + " Coordinator session_C1; Triage session_T2; Batch runner 8 session_B3.")
step_allow("a Roles line with no colon after Coordinator or Triage is allowed",
           role_path("step-topic-lane"),
           ROLE_TOP + "\nRoles: Coordinator session_C1; Triage session_T1; Batch runner 8 session_B1.")
step_allow("pasted roster lines, one per role, in the Standing sessions form, are allowed",
           role_path("step-topic-lane"),
           ROLE_TOP + "\n- Coordinator: \"Claude settings coordinator handoff\", session_C1, since 2026-11-03 15:32 CST."
           "\n- Triage: \"cs triage: claude-settings (6)\", session_T1, since 2026-11-03 15:38 CST."
           "\n- Batch runner: \"claude-settings batch runner 8\", session_B1, since 2026-11-03 15:38 CST.")
step_allow("a Triage roster line with a note in parentheses before its quoted label is allowed",
           role_path("step-topic-lane"),
           ROLE_TOP + "\n- Coordinator session_C1\n- Triage (the repo's one page): \"cs triage (6)\", session_T1, "
           "since 2026-11-03 15:38 CST.\n- Batch runner: session_B1")
step_allow("a Coordinator id in parentheses after its label is allowed",
           role_path("step-topic-lane"),
           ROLE_TOP + "\nCoordinator (session_C1)\nTriage: session_T1\nBatch runner 8: session_B1")
step_allow("a Coordinator id after the word is is allowed",
           role_path("step-topic-lane"),
           ROLE_TOP + "\nCoordinator is session_C1\nTriage: session_T1\nBatch runner 8: session_B1")
step_allow("a Batch runner number in parentheses before the colon is allowed",
           role_path("step-topic-lane"),
           ROLE_TOP + "\nCoordinator: session_C1\nTriage: session_T1\nBatch runner (7): session_B1")
step_allow("a Coordinator id in backticks is allowed",
           role_path("step-topic-lane"),
           ROLE_TOP + "\nCoordinator `session_C1`\nTriage: session_T1\nBatch runner 8: session_B1")
step_allow("role labels in bold, the colon inside the bold, are allowed",
           role_path("step-topic-lane"),
           ROLE_TOP + "\n**Coordinator:** session_C1\n**Triage:** session_T1\n**Batch runner 8:** session_B1")
step_allow("a Triage label in bold, the colon after the bold, is allowed",
           role_path("step-topic-lane"),
           ROLE_TOP + "\nCoordinator: session_C1\n**Triage**: session_T1\nBatch runner 8: session_B1")
step_allow("role labels in lower case with no colons are allowed: a label is read in any case",
           role_path("step-topic-lane"),
           ROLE_TOP + " coordinator session_C1; triage session_T2; batch runner 8 session_B3.")
step_allow("the coordinator's own brief form, verbatim, is allowed: a topic t lane, with no colons",
           role_path("step-topic-t-lane"),
           "Lane brief: x. Topic: t. Coordinator session_013NEJL2hB1pLZPDpzas7VgB; "
           "Triage session_013NEJL42Sv3tJkjpzY7bExj; Batch runner 8 session_013NEJL2vsmyKzJm8jUDt6za.")
step_allow("a brief with no roles to a target that is no lane is allowed",
           role_path("step-triage"), ROLE_TOP)
step_allow("the brief template, its slugs and id placeholders filled, is allowed",
           role_path("step-topic-lane"), fill_template(BRIEF_TEMPLATE, BRIEF_TEMPLATE_IDS))

# Refused: a role label is missing. Each refusal keeps the other two labels present, so a failure names the one cause it
# tests. A refusal asks for no session id (ROLE_LACKS).
roles_refuse("a brief with no Coordinator label is refused, though its Triage and Batch runner ids are named",
             role_path("step-topic-lane"), ROLE_TOP + TRIAGE_LINE + RUNNER_LINE, ["Coordinator"])
roles_refuse("a brief with no Triage label is refused, though its Coordinator and Batch runner ids are named",
             role_path("step-topic-lane"), ROLE_TOP + COORD_LINE + RUNNER_LINE, ["Triage"])
roles_refuse("a brief with no Batch runner label is refused, though its Coordinator and Triage ids are named",
             role_path("step-topic-lane"), ROLE_TOP + COORD_LINE + TRIAGE_LINE, ["Batch runner"])
roles_refuse("a brief with no role labels is refused",
             role_path("step-topic-lane"), ROLE_TOP, ["Coordinator", "Triage", "Batch runner"])
roles_refuse("a brief with the Triage and Batch runner labels and no Coordinator label is refused",
             role_path("step-topic-lane"), ROLE_TOP + "\nTriage\nBatch runner", ["Coordinator"])
roles_refuse("a brief with the Coordinator and Batch runner labels and no Triage label is refused",
             role_path("step-topic-lane"), ROLE_TOP + "\nCoordinator\nBatch runner", ["Triage"])
roles_refuse("a brief with the Coordinator and Triage labels and no Batch runner label is refused",
             role_path("step-topic-lane"), ROLE_TOP + "\nCoordinator\nTriage", ["Batch runner"])
roles_refuse("subtriage is not the Triage label: a brief naming subtriage for Triage is refused",
             role_path("step-topic-lane"), ROLE_TOP + COORD_LINE + "\nsubtriage: session_TRIAGE01" + RUNNER_LINE, ["Triage"])
roles_refuse("Coordinators is not the Coordinator label: a brief naming Coordinators is refused",
             role_path("step-topic-lane"), ROLE_TOP + "\nCoordinators: session_COORD01" + TRIAGE_LINE + RUNNER_LINE,
             ["Coordinator"])
roles_refuse("Coordinators-only is not the Coordinator label: a whole word is needed, and a plural is another word",
             role_path("step-topic-lane"), ROLE_TOP + "\nCoordinators-only\nTriage\nBatch runner", ["Coordinator"])
roles_refuse("Triagey is not the Triage label: a brief naming Triagey is refused",
             role_path("step-topic-lane"), ROLE_TOP + COORD_LINE + "\nTriagey: session_TRIAGE01" + RUNNER_LINE, ["Triage"])
roles_refuse("Triaged is not the Triage label: a label must stand as a whole word",
             role_path("step-topic-lane"), ROLE_TOP + "\nCoordinator\nTriaged\nBatch runner", ["Triage"])
roles_refuse("Batch runners is not the Batch runner label: the plural is another word",
             role_path("step-topic-lane"), ROLE_TOP + "\nCoordinator\nTriage\nBatch runners", ["Batch runner"])
roles_refuse("the batch-runner tag form is not the Batch runner label: it has no space",
             role_path("step-topic-lane"), ROLE_TOP + "\nCoordinator\nTriage\nbatch-runner", ["Batch runner"])
roles_refuse("three session ids with no role labels are refused: an id names no role by itself",
             role_path("step-topic-lane"), ROLE_TOP + " session_COORD01 session_TRIAGE01 session_RUNNER01.",
             ["Coordinator", "Triage", "Batch runner"])
roles_refuse("a Page writer label is no role: a brief naming a Page writer id for Triage is refused",
             role_path("step-topic-lane"), ROLE_TOP + COORD_LINE + "\nPage writer: session_x1" + RUNNER_LINE, ["Triage"])
roles_refuse("a Pretriage label is no Triage label: a brief naming Pretriage is refused",
             role_path("step-topic-lane"), ROLE_TOP + COORD_LINE + "\nPretriage: session_x1" + RUNNER_LINE, ["Triage"])

# Allowed: a role label may have words before its id, and its colon is optional. Briefs write the label loosely, so
# the check must still read the id as that role.
step_allow("a triage label with no colon, triage session_abc123, is allowed: the colon is optional",
           role_path("step-topic-lane"), ROLE_TOP + COORD_LINE + "\ntriage session_abc123" + RUNNER_LINE)
step_allow("a Triage label with words before its id, Triage session: session_x1, is allowed",
           role_path("step-topic-lane"), ROLE_TOP + COORD_LINE + "\nTriage session: session_x1" + RUNNER_LINE)
step_allow("a Triage label with words before its id, Triage id: session_x1, is allowed",
           role_path("step-topic-lane"), ROLE_TOP + COORD_LINE + "\nTriage id: session_x1" + RUNNER_LINE)

# Allowed: a label alone names its role, with no session id. The labels may stand on lines of their own, in any case, with
# words after them or none, and in markdown.
step_allow("the three role labels on their own lines, with no session ids, are allowed",
           role_path("step-topic-lane"), ROLE_TOP + LABEL_LINES)
step_allow("the three role labels in lower case, with no session ids, are allowed",
           role_path("step-topic-lane"), ROLE_TOP + "\ncoordinator\ntriage\nbatch runner")
step_allow("role labels in prose, with words around them and no session ids, are allowed",
           role_path("step-topic-lane"), ROLE_TOP + "\nAsk the Coordinator, the Triage and the Batch runner by role.")
step_allow("role labels followed by words, with no session ids, are allowed",
           role_path("step-topic-lane"),
           ROLE_TOP + "\nCoordinator (ask by role)\nTriage (page writer)\nBatch runner: the runner")
step_allow("markdown-wrapped role labels with no session ids are allowed: _Triage_ and **Batch runner:**",
           role_path("step-topic-lane"), ROLE_TOP + "\n**Coordinator**\n_Triage_\n**Batch runner:**")
# Allowed: a brief that names each role with an id beside its label, in the forms a label and id take.
step_allow("a triage id on the line after the brief passes", role_path("step-topic-lane"),
           ROLE_TOP + COORD_LINE + "\nTriage: session_abc123" + RUNNER_LINE)
step_allow("a triage id with a number, Triage 5:, passes", role_path("step-topic-lane"),
           ROLE_TOP + COORD_LINE + "\nTriage 5: session_abc123" + RUNNER_LINE)
step_allow("a triage id with a gloss, Triage (page and roadmap writer):, passes", role_path("step-topic-lane"),
           ROLE_TOP + COORD_LINE + "\nTriage (page and roadmap writer): session_abc123" + RUNNER_LINE)
step_allow("a triage id after a coordinator id on the same line passes", role_path("step-topic-lane"),
           ROLE_TOP + "\nCoordinator: session_x1. Triage: session_abc123" + RUNNER_LINE)
step_allow("a lowercase triage label passes", role_path("step-topic-lane"),
           ROLE_TOP + COORD_LINE + "\ntriage: session_abc123" + RUNNER_LINE)
step_allow("a triage id on the brief's first line passes", role_path("step-topic-lane"),
           ROLE_TOP + " Triage: session_abc123" + COORD_LINE + RUNNER_LINE)
step_allow("a batch runner id with a number, Batch runner 8: session_x8, passes", role_path("step-topic-lane"),
           ROLE_TOP + COORD_LINE + TRIAGE_LINE + "\nBatch runner 8: session_x8")
step_allow("a brief with the coordinator, triage and batch runner ids passes", role_path("step-topic-lane"),
           ROLE_TOP + IDS_LINES)
step_allow("an older lane's own step, with the three ids, passes", role_path("step-old-lane"),
           "Lane brief: icon-a. Topic: icons." + IDS_LINES)
step_allow("a bold triage label, **Triage:** session_abc123, passes", role_path("step-topic-lane"),
           ROLE_TOP + COORD_LINE + "\n**Triage:** session_abc123" + RUNNER_LINE)
step_allow("an italic triage label, _Triage_: session_abc123, passes", role_path("step-topic-lane"),
           ROLE_TOP + COORD_LINE + "\n_Triage_: session_abc123" + RUNNER_LINE)
step_allow("a backticked triage id, Triage: `session_abc123`, passes", role_path("step-topic-lane"),
           ROLE_TOP + COORD_LINE + "\nTriage: `session_abc123`" + RUNNER_LINE)
step_allow("a bold batch runner label, **Batch runner:** session_abc123, passes", role_path("step-topic-lane"),
           ROLE_TOP + COORD_LINE + TRIAGE_LINE + "\n**Batch runner:** session_abc123")
step_allow("an italic batch runner label, _Batch runner_: session_abc123, passes", role_path("step-topic-lane"),
           ROLE_TOP + COORD_LINE + TRIAGE_LINE + "\n_Batch runner_: session_abc123")
step_allow("a backticked batch runner id, Batch runner: `session_abc123`, passes", role_path("step-topic-lane"),
           ROLE_TOP + COORD_LINE + TRIAGE_LINE + "\nBatch runner: `session_abc123`")
step_allow("a lowercase batch runner label, batch runner: session_x8, passes", role_path("step-topic-lane"),
           ROLE_TOP + COORD_LINE + TRIAGE_LINE + "\nbatch runner: session_x8")

# The fresh lane and the older lane, each missing one role label, refuse on the role check.
roles_refuse("a brief for the lane's own topic, to a fresh lane with no triage label, is refused",
             role_path("step-create-json"), ROLE_TOP + COORD_LINE + RUNNER_LINE, ["Triage"], target=ROLE_NEW)
roles_refuse("a brief for an older lane's own step, with no triage label, is refused",
             role_path("step-old-lane"), "Lane brief: icon-a. Topic: icons." + COORD_LINE + RUNNER_LINE, ["Triage"])
roles_refuse("a brief with a triage label and no batch runner label is refused",
             role_path("step-topic-lane"), ROLE_TOP + COORD_LINE + TRIAGE_LINE, ["Batch runner"])

# Refused with the topic, step and record reasons: the role check runs after those, so a brief that fails them keeps its
# own reason. The lacks fragments check that the role form is not named in it.
step_refuse("a brief for topic colors to a lane on topic icons, with no role ids, keeps the topic reason",
            role_path("step-topic-lane"), "Lane brief: icon-b. Topic: colors.",
            carries=TOPIC_REASON, lacks=("Coordinator:", "Triage:", "Batch runner:"))
step_refuse("a brief naming a step the older lane does not carry, with no role ids, keeps the step reason",
            role_path("step-old-lane"), "Lane brief: icon-c. Topic: icons.",
            carries=STEP_REASON, lacks=("Coordinator:", "Triage:", "Batch runner:"))
step_refuse("a brief with no role ids to a target with no record keeps the no-record reason",
            role_path("no-record"), "Lane brief: icon-b. Topic: icons.",
            carries=("holds no get_session",), lacks=("Coordinator:", "Triage:", "Batch runner:"))
step_refuse("a brief with no role ids and an unreadable transcript keeps the no-record reason",
            role_path("unreadable"), "Lane brief: icon-b. Topic: icons.",
            carries=("holds no get_session",), lacks=("Coordinator:", "Triage:", "Batch runner:"))

# The brief template: its three labels are there with their id placeholders unfilled, so it is allowed, and so is the same
# template with the ids filled.
step_allow("the brief template with its session id placeholders unfilled is allowed: its three labels are present",
           role_path("step-topic-lane"), fill_template(BRIEF_TEMPLATE))


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
# A role refusal of a start asks for no session id, names no gap limit, names no step-steer, and names none of the test's
# ids. The topic refusal of a start names no session id, so `session id` tells the two reasons apart.
ROLE_START_LACKS = ("start one with create_session", COORD_ID, TRIAGE_ID, RUNNER_ID) + ROLE_LACKS


def start_refuse(name, prompt, tags=START_TOPIC_TAGS, carries=(), lacks=(), names=()):
    """A create_session start the guard refuses under lane-one-topic. It carries the effort, model and source that the
    other start rules judge, so the refusal is this rule's alone."""
    add("lane-one-topic: " + name, "deny", rule=LANE_ONE_TOPIC, tool=CREATE_SESSION, cwd=NOGIT, prompt=prompt,
        tags=tags, effort=LANE_EFFORT_FIELD, model="sonnet", source_url=LANE_SOURCE_URL,
        carries=carries, lacks=lacks, names=names)


def start_allow(name, prompt, tags=START_TOPIC_TAGS):
    """A create_session start the guard lets through."""
    add("lane-one-topic: " + name, "allow", tool=CREATE_SESSION, cwd=NOGIT, prompt=prompt, tags=tags,
        effort=LANE_EFFORT_FIELD, model="sonnet", source_url=LANE_SOURCE_URL)


def start_roles_refuse(name, prompt, missing, tags=START_TOPIC_TAGS):
    """A start that clears the topic or step check and lacks a role label: refused. The reason names each missing role,
    asks for no session id, and names none of the test's ids."""
    start_refuse(name, prompt, tags=tags, lacks=ROLE_START_LACKS, names=missing)


# Refused: a start that clears the topic check and names no label for any role. The reason names all three roles.
start_roles_refuse("a start for topic alpha, with its brief and no role labels, is refused",
                   START_BRIEF, ["Coordinator", "Triage", "Batch runner"])
# Refused: a start that lacks one role label. Each keeps the other two labels present, so a failure names one cause.
start_roles_refuse("a start for topic alpha with no Coordinator label is refused, though its Triage and Batch runner ids are named",
                   START_BRIEF + TRIAGE_LINE + RUNNER_LINE, ["Coordinator"])
start_roles_refuse("a start for topic alpha with no Triage label is refused",
                   START_BRIEF + COORD_LINE + RUNNER_LINE, ["Triage"])
start_roles_refuse("a start for topic alpha with no Batch runner label is refused",
                   START_BRIEF + COORD_LINE + TRIAGE_LINE, ["Batch runner"])
start_roles_refuse("a start for topic alpha with the Triage and Batch runner labels and no Coordinator label is refused",
                   START_BRIEF + "\nTriage\nBatch runner", ["Coordinator"])
start_roles_refuse("a start for topic alpha with the Coordinator and Batch runner labels and no Triage label is refused",
                   START_BRIEF + "\nCoordinator\nBatch runner", ["Triage"])
start_roles_refuse("a start for topic alpha with the Coordinator and Triage labels and no Batch runner label is refused",
                   START_BRIEF + "\nCoordinator\nTriage", ["Batch runner"])
# Refused: an older lane, with a cs-step tag and no cs-topic, is judged by its step, and its start names no role label.
start_roles_refuse("an older-lane start for step icon-a with no role labels is refused",
                   LANE_GRANT + "\nLane brief: icon-a. Topic: icons.", ["Coordinator", "Triage", "Batch runner"],
                   tags=OLD_START_TAGS)
# Allowed: the controls for the refusals above. The same start for topic alpha, and the same older-lane start, each with
# all three ids, or with all three labels and no ids.
start_allow("a start for topic alpha with the coordinator, triage and batch runner ids is allowed",
            START_BRIEF + IDS_LINES)
start_allow("a start for topic alpha with the three role labels and no ids is allowed",
            START_BRIEF + LABEL_LINES)
start_allow("an older-lane start for step icon-a with the three role ids is allowed",
            LANE_GRANT + "\nLane brief: icon-a. Topic: icons." + IDS_LINES, tags=OLD_START_TAGS)
start_allow("an older-lane start for step icon-a with the three role labels and no ids is allowed",
            LANE_GRANT + "\nLane brief: icon-a. Topic: icons." + LABEL_LINES, tags=OLD_START_TAGS)
# Refused on the topic, as before: a start whose brief names topic colors on a lane of topic alpha. The ids do not rescue
# a wrong topic, and with no ids the topic reason still wins over the role reason.
start_refuse("a start for topic colors on a lane of topic alpha, with all three role ids, is refused on the topic",
             LANE_GRANT + "\nLane brief: icon-a. Topic: colors." + IDS_LINES,
             carries=START_TOPIC_REASON, lacks=("session id",))
start_refuse("a start for topic colors on a lane of topic alpha, with no role ids, is refused on the topic",
             LANE_GRANT + "\nLane brief: icon-a. Topic: colors.",
             carries=START_TOPIC_REASON, lacks=("session id",))


# =========================================================================== a header stamp matches the clock
