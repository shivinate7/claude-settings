# section 15173
FAMILY = "lane-one-topic"
FAMILIES["lane-one-topic"] = "one lane, one topic: a send_message brief whose Topic differs from the lane's cs-topic, or names none, is refused; an older lane with no cs-topic is judged by its cs-step tags; a message without the marker passes unread"
#
# Rule lane-one-topic. A lane is one topic: its cs-topic tag, set at create_session beside its cs-step tags. A
# send_message whose first non-blank line is `Lane brief: <step>. Topic: <topic>.` is refused when the target's newest
# record is a lane whose cs-topic differs from the brief's Topic, or a lane with a cs-topic when the brief names no
# Topic. A lane with no cs-topic (an older lane) is judged by its cs-step tags: the brief's step must be one of them.
# Any other message passes, and so does a brief to a target that is no lane. A marker brief with no record of its
# target is refused. Only a marker brief reads the transcript: a message without the marker passes unread.
LANE_ONE_TOPIC = "lane-one-topic"
SEND_MESSAGE = "mcp__claude-code-remote__send_message"
TOPIC_STEER = (("topic", "Topic"),)  # the refusal steers the sender to name the topic


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
            role_path("step-topic-lane"), "Lane brief: icon-a. Topic: colors.")
# Refused, and the steer says to start one with create_session: the sender already holds a lane, so a new lane is the
# right next step here. The create_session start's reason is split from this one, so the steer must stay on this side.
step_refuse("a brief for topic colors to a lane on topic icons keeps the steer to start one with create_session",
            role_path("step-topic-lane"), "Lane brief: icon-b. Topic: colors.",
            carries=("start one with create_session",))
# Refused: a lane with a topic gets a brief that names none. The steer names the topic, so the sender can fix it.
step_refuse("a brief that names no topic, to a lane with a topic, is refused, and the steer names the topic",
            role_path("step-topic-lane"), "Lane brief: icon-a.", carries=TOPIC_STEER)
# Refused: the match is exact. Topic icons-v2 is not topic icons, though it holds it as a substring.
step_refuse("a brief for topic icons-v2 to a lane on topic icons is refused: a substring is not the topic",
            role_path("step-topic-lane"), "Lane brief: icon-b. Topic: icons-v2.")
# Refused: the marker is the first non-blank line, so leading blank lines do not hide it from the judge.
step_refuse("a brief after two blank lines is judged: the marker is the first non-blank line",
            role_path("step-topic-lane"), "\n\nLane brief: icon-a. Topic: colors.")
# Refused: an older lane with no cs-topic is judged by its cs-step tags, and icon-c is not one of them.
step_refuse("a brief naming a step the older lane does not carry is refused",
            role_path("step-old-lane"), "Lane brief: icon-c. Topic: icons.")
# Refused: a lane that create_session started on topic icons, with its result as JSON, then as plain text. Each
# result shape has its own fixture, so a reader that takes only one shape fails one case.
step_refuse("a brief for topic colors to a lane that create_session started on topic icons (JSON result) is refused",
            role_path("step-create-json"), "Lane brief: icon-b. Topic: colors.", target=ROLE_NEW)
step_refuse("a brief for topic colors to a lane that create_session started on topic icons (plain result) is refused",
            role_path("step-create-text"), "Lane brief: icon-b. Topic: colors.", target=ROLE_NEW)
# Refused: the lane's record comes back wrapped as another session's untrusted text. The topic is still read from it.
step_refuse("a brief for topic colors to a lane on topic icons, its record wrapped, is refused",
            role_path("step-topic-lane-wrapped"), "Lane brief: icon-a. Topic: colors.",
            carries=("names a topic the lane does not hold",))
# Refused: no record of the target in the transcript, so the guard cannot tell the lane's topic.
step_refuse("a marker brief to a target with no record in the transcript is refused",
            role_path("no-record"), "Lane brief: icon-b. Topic: icons.")
# Refused, and paired with the cost case below: the transcript cannot be read, so a marker brief is refused.
step_refuse("a marker brief whose transcript cannot be read is refused",
            role_path("unreadable"), "Lane brief: icon-b. Topic: icons.")
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
           role_path("step-topic-lane"), "Lane brief: icon-b. Topic: icons.")
step_allow("a brief for the lane's own step on its own topic is allowed",
           role_path("step-topic-lane"), "Lane brief: icon-a. Topic: icons.")
# Passes: an older lane with two cs-step tags and no topic is judged by its steps: the second step is one of them.
step_allow("an older lane with two cs-step tags: a brief naming its second step is allowed",
           role_path("step-old-lane"), "Lane brief: icon-b. Topic: icons.")
# Passes: a lane that create_session started on topic icons, with a new step on that topic, in both result shapes.
step_allow("a brief for a new step on topic icons to a lane that create_session started (JSON result) is allowed",
           role_path("step-create-json"), "Lane brief: icon-b. Topic: icons.", target=ROLE_NEW)
step_allow("a brief for a new step on topic icons to a lane that create_session started (plain result) is allowed",
           role_path("step-create-text"), "Lane brief: icon-b. Topic: icons.", target=ROLE_NEW)
# Passes: a brief to a target that is no lane is not judged, whatever its topic line says.
step_allow("a brief with topic colors to a target that is no lane (cs-build:triage) is allowed",
           role_path("step-triage"), "Lane brief: icon-b. Topic: colors.")
# Passes: the newest record decides. A lane read, then a newer triage read, makes the target no lane.
step_allow("the newest record decides: a lane read, then a newer triage read, lets a brief through",
           role_path("step-lane-then-triage"), "Lane brief: icon-b. Topic: colors.")
# Refused: the target's tags were set after its newest record, so the record is stale. The steer re-reads the record
# with get_session. It never tells the sender to start a new lane, for a topic lane or a lane with no topic.
step_refuse("a brief for topic icons, after set_session_tags on a topic lane, is refused: re-read the record with get_session",
            role_path("step-topic-lane-retagged"), "Lane brief: icon-b. Topic: icons.",
            carries=("get_session",), lacks=("new lane",))
step_refuse("a brief for topic icons, after set_session_tags on a lane with no topic, is refused: re-read with get_session",
            role_path("step-old-lane-retagged"), "Lane brief: icon-b. Topic: icons.",
            carries=("get_session",), lacks=("new lane",))
# A create_session result shaped {"session_id": ...} is a record too: the brief is judged against the lane's topic.
step_allow("a create_session result shaped session_id counts as the record: a brief for its own topic icons passes",
           role_path("step-create-session-id"), "Lane brief: icon-b. Topic: icons.", target=ROLE_NEW)
# The refusal must be the topic's, not the no-record one: a reader that misses the record refuses every brief here.
step_refuse("a create_session result shaped session_id counts as the record: a brief for topic colors is refused",
            role_path("step-create-session-id"), "Lane brief: icon-b. Topic: colors.", target=ROLE_NEW,
            lacks=("holds no get_session",))
# Marker variants: bold, heading and lowercase all open a marker brief. Each names topic icons to a lane on colors.
step_refuse("a bold marker, **Lane brief:** x. Topic: icons., to a lane on topic colors is refused",
            role_path("step-colors-lane"), "**Lane brief:** x. Topic: icons.")
step_refuse("a heading marker, # Lane brief: x. Topic: icons., to a lane on topic colors is refused",
            role_path("step-colors-lane"), "# Lane brief: x. Topic: icons.")
step_refuse("a lowercase marker, lane brief: x. topic: icons., to a lane on topic colors is refused",
            role_path("step-colors-lane"), "lane brief: x. topic: icons.")
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
            role_path("step-topic-lane"), "Grant: <owner words>, <time>\nLane brief: icon-a. Topic: icons.")


# =========================================================================== a header stamp matches the clock
