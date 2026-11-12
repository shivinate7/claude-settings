# section 43580
FAMILY = "lane-one-topic"
#
# Rule lane-one-topic, the owner-unread sentence (decision session-tiers). A lane brief, sent by send_message or
# started by a lane create_session, is refused unless its text holds both OWNER_UNREAD_PHRASES, whitespace-flattened
# and case-blind. The phrases and the sentence come from test_guard.py (OWNER_FIRST, OWNER_LAST, OWNER_SENTENCE). Each
# brief here names the lane's own topic, so the topic check passes and only the owner-unread check can refuse it.
TOPIC_LACK = "names a topic the lane does not hold"  # the send_message topic refusal, which must not be the cause
START_TOPIC_LACK = "start's cs-topic tag does not hold"  # the create_session topic refusal, likewise
OWNER_GRANT = "Grant: B is good, 13:19 CST Nov 10"
SEND_BRIEF = "Lane brief: icon-a. Topic: icons."  # role_path("step-topic-lane") holds cs-topic icons
START_BRIEF = "Lane brief: icon-a. Topic: alpha."  # a start on cs-topic alpha, as s29666 uses
START = dict(tool=LANE_TOOL, cwd=LANE_REPO, tags=OWN_LANE_TAGS + ["cs-topic:alpha"], effort=LANE_EFFORT_FIELD,
             model="sonnet", source_url=LANE_SOURCE_URL)
ONLY_FIRST = "The %s this brief." % OWNER_FIRST
ONLY_LAST = "Send each override line, owner act and question to the Coordinator in the %s." % OWNER_LAST


def brief_refuse(name, message, carries=()):
    """A send_message brief the owner-unread check refuses. Its topic matches the lane, so the sentence is the cause."""
    step_refuse("owner-unread: " + name, role_path("step-topic-lane"), message, carries=carries, lacks=(TOPIC_LACK,))


def brief_allow(name, message):
    """A send_message the guard lets through silently. Built here, not by step_allow, so the message is exactly this."""
    add("owner-unread: " + name, "allow", tool=SEND_MESSAGE, cwd=NOGIT, silent=True,
        transcript=role_path("step-topic-lane"), env=ROLE_ENV, session_id=ROLE_OTHER, message=message)


# Refused: a brief with no owner-unread sentence. The Grant line does not supply one, and neither does the topic.
brief_refuse("a brief with a Grant line and no owner-unread sentence is refused", OWNER_GRANT + "\n" + SEND_BRIEF)
brief_refuse("a brief with no Grant line and no owner-unread sentence is refused", SEND_BRIEF)
# Refused: one phrase alone is no sentence. Each half is refused on its own.
brief_refuse("a brief with only the first phrase is refused", SEND_BRIEF + "\n" + ONLY_FIRST)
brief_refuse("a brief with only the second phrase is refused", SEND_BRIEF + "\n" + ONLY_LAST)
# Refused, with the remedy: the refusal names both phrases, so the sender can add the sentence.
brief_refuse("a refused brief's reason names both phrases", SEND_BRIEF, carries=(OWNER_FIRST, OWNER_LAST))
# Passes, the green controls beside the refusals above: the same brief with the sentence, in each form the match allows.
brief_allow("a brief with both phrases in one sentence after the marker is allowed", SEND_BRIEF + "\n" + OWNER_SENTENCE)
brief_allow("a brief whose sentence is upper case is allowed: the match is case-blind",
            SEND_BRIEF + "\n" + OWNER_SENTENCE.upper())
brief_allow("a brief whose sentence is bold markdown is allowed", SEND_BRIEF + "\n**" + OWNER_SENTENCE + "**")
brief_allow("a brief whose first phrase breaks its line is allowed: the match is whitespace-blind",
            SEND_BRIEF + "\n" + OWNER_SENTENCE.replace(OWNER_FIRST, OWNER_FIRST.replace(" ", "\n", 1), 1))
brief_allow("a brief with a Grant line and both phrases is allowed",
            OWNER_GRANT + "\n" + SEND_BRIEF + "\n" + OWNER_SENTENCE)
# Passes: the marker is on line two, so the message is not a lane brief and needs no sentence.
brief_allow("a marker on line two, with no owner-unread sentence, is not a lane brief and is allowed",
            "Status: PR #12 merged for icon-a.\n" + SEND_BRIEF)

# The same rule at a lane create_session start: the Grant line first, then the brief. The start's topic matches its
# cs-topic tag, so only the owner-unread check can refuse it.
add("owner-unread: a lane start with a Grant line and no owner-unread sentence is refused", "deny", "lane-one-topic",
    prompt=OWNER_GRANT + "\n" + START_BRIEF, lacks=(START_TOPIC_LACK,), **START)
add("owner-unread: a lane start with only the first phrase is refused", "deny", "lane-one-topic",
    prompt=OWNER_GRANT + "\n" + START_BRIEF + "\n" + ONLY_FIRST, lacks=(START_TOPIC_LACK,), **START)
add("owner-unread: a refused lane start's reason names both phrases", "deny", "lane-one-topic",
    prompt=OWNER_GRANT + "\n" + START_BRIEF, carries=(OWNER_FIRST, OWNER_LAST), lacks=(START_TOPIC_LACK,), **START)
add("owner-unread: a lane start with a Grant line and both phrases is allowed", "allow",
    prompt=OWNER_GRANT + "\n" + START_BRIEF + "\n" + OWNER_SENTENCE, **START)
# Passes: a create_session with no lane tag starts no lane, so its brief is not judged.
add("owner-unread: a create_session with no lane tag is not a lane start, so its brief is not judged", "allow",
    tool=LANE_TOOL, tags=["cs-build:triage"], prompt=START_BRIEF)
