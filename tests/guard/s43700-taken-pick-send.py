# section 43700
FAMILY = "pick-reaches-page"
#
# Rule pick-reaches-page, the send check (step page-taken-picks-area, row 2 of the goal). A coordinator's send_message or
# create_session whose text has a line that opens `Coordinator pick` is refused unless the same turn also sent the page
# writer (triage) the pick. The writer files a pick as a taken-pick card, which the owner can overrule; a pick sent only to
# a lane reaches the owner nowhere. The refusal's remedy names that card. It names no stands item: the owner's 15 Nov
# ruling (step page-no-preselected-pick) removed the stands fields. A send to the page writer passes. Only a coordinator's
# send is judged, and a turn is the records after the last human message. The page writer is the writer of the newest
# meta/page read in the transcript (lint/_transcript.py page_writer_id). A transcript with no page read, one that cannot be
# read, or a code error in the rule, allows and prints one stderr line that names the rule.
TK_RULE = "pick-reaches-page"
TK_SEND = "mcp__claude-code-remote__send_message"
TK_CREATE = "mcp__claude-code-remote__create_session"
TK_OWN = "session_TKCOORD01"  # the coordinator that sends the pick; TK_ENV below names it through the remote env id
TK_ENV = {"CLAUDE_CODE_REMOTE_SESSION_ID": "cse_TKCOORD01"}
TK_WRITER = "session_TKWRITER01"  # the page writer: the writer the meta/page read in each transcript names
TK_LANE = "session_TKLANE01"  # a lane the coordinator sends a pick to
TK_PICK = "Coordinator pick: icons-a"
TK_PICK_B = "Coordinator pick: colours-b"  # a second pick; the fixtures hold a writer card for TK_PICK only
TK_REMEDY = "send the pick to triage as a taken-pick card"  # the phrase the refusal's remedy must carry
TK_TURN_ONE = "Owner: pick the icons for the page."
TK_TURN_TWO = "Owner: and the colours too."
TK_DIR = os.path.join(ROOT, "takenpick")
TK_LINES = ("lane-no-writer", "writer-earlier-turn", "writer-same-turn", "writer-undelivered", "writer-no-marker",
            "writer-sidechain", "to-writer", "no-marker", "unread-writer", "code-error")


def tk_path(name):
    """The transcript fixture for one case: a JSONL file under this run's folder."""
    return os.path.join(TK_DIR, name + ".jsonl")


def tk_page_read(tool_id, writer):
    """One paired ArtifactData get of meta/page whose result names `writer`, as the page's own read returns it."""
    return [role_use(tool_id, "ArtifactData", {"action": "get", "collection": "meta", "doc_id": "page"}),
            role_result(tool_id, json.dumps({"id": "page", "writer": writer}))]


def tk_send(tool_id, target, text, result='{"status":"delivered"}', sidechain=False):
    """One paired send_message to `target`, with its result text (delivered unless `result` says otherwise): a send the
    turn already made. `sidechain` marks the send as an agent's record, which the rule does not count."""
    use = role_use(tool_id, TK_SEND, {"session_id": target, "message": text})
    if sidechain:
        line = json.loads(use)
        line["isSidechain"] = True
        use = json.dumps(line)
    return [use, role_result(tool_id, result)]


# The coordinator's own record, the writer's read, and the records of the lane and the writer, which the transcript must hold
# for the target-id-in-roster rule to know each target: the head every fixture shares.
TK_HEAD = ([role_said(TK_TURN_ONE)] + role_call("o1", COORD_TAGS, session=TK_OWN) + tk_page_read("p1", TK_WRITER)
           + role_target_call("l1", LANE_TAGS, target=TK_LANE) + role_target_call("w1", TRIAGE_TAGS, target=TK_WRITER))
# The same head with no meta/page read: the page's writer is unknown to this transcript.
TK_HEAD_NO_READ = ([role_said(TK_TURN_ONE)] + role_call("o1", COORD_TAGS, session=TK_OWN)
                   + role_target_call("l1", LANE_TAGS, target=TK_LANE) + role_target_call("w1", TRIAGE_TAGS, target=TK_WRITER))
# A record the rule's reader cannot take: its message is a string, not an object, so reading its tool uses raises.
TK_BAD_RECORD = json.dumps({"type": "assistant", "message": "a message that is text, not an object"})
TK_LINES_BY_NAME = {
    "lane-no-writer": TK_HEAD,
    # The writer got the pick in an earlier turn only: the owner's last words open a new turn, which sends nothing yet.
    "writer-earlier-turn": TK_HEAD + tk_send("s1", TK_WRITER, TK_PICK) + [role_said(TK_TURN_TWO)],
    # The writer got the same pick in this turn, so the lane send passes.
    "writer-same-turn": TK_HEAD + tk_send("s1", TK_WRITER, TK_PICK),
    # The writer's send this turn was not delivered: the writer got no card, so the lane send has nothing behind it.
    "writer-undelivered": TK_HEAD + tk_send("s1", TK_WRITER, TK_PICK, result='{"status":"error"}'),
    # The writer's send this turn carries no Coordinator pick line, so it is no card for the pick.
    "writer-no-marker": TK_HEAD + tk_send("s1", TK_WRITER, "Status: the icons are done."),
    # The writer's send is an agent's record, which does not count as the coordinator's card.
    "writer-sidechain": TK_HEAD + tk_send("s1", TK_WRITER, TK_PICK, sidechain=True),
    "to-writer": TK_HEAD,
    "no-marker": TK_HEAD,
    # The coordinator read no page at all, so no writer is named for the pick to reach.
    "unread-writer": TK_HEAD_NO_READ,
    # The turn holds a record the rule cannot read, after the owner's words.
    "code-error": TK_HEAD + [TK_BAD_RECORD],
}


def write_tk_transcripts():
    """Each fixture transcript, one JSON record per line, under this run's folder."""
    os.makedirs(TK_DIR, exist_ok=True)
    for name in TK_LINES:
        with open(tk_path(name), "w", encoding="utf-8") as handle:
            handle.write("\n".join(TK_LINES_BY_NAME[name]) + "\n")


lazy_fixture([tk_path(name) for name in TK_LINES], write_tk_transcripts)


def tk_input(tool, target, text):
    """The tool_input of a pick send: a send_message names its target; a create_session carries the pick in its prompt."""
    return dict(prompt=text) if tool == TK_CREATE else dict(session_id=target, message=text)


def tk_refuse(name, transcript, text, target=TK_LANE, tool=TK_SEND):
    """A coordinator's send the guard refuses. The reason names its rule and the taken-pick remedy, and no stands item."""
    add("pick-reaches-page: " + name, "deny", rule=TK_RULE, tool=tool, cwd=NOGIT, transcript=tk_path(transcript),
        env=TK_ENV, carries=(TK_REMEDY,), lacks=("stands",), **tk_input(tool, target, text))


def tk_allow(name, transcript, text, target=TK_LANE, tool=TK_SEND, err=()):
    """A send the guard lets through with nothing on stdout. `err` names what its stderr must carry."""
    add("pick-reaches-page: " + name, "allow", tool=tool, cwd=NOGIT, silent=True, transcript=tk_path(transcript),
        env=TK_ENV, err=err, **tk_input(tool, target, text))


# A pick sent to a lane with no writer send this turn is refused.
tk_refuse("a coordinator pick sent to a lane with no writer send this turn is refused, and the remedy names the taken-pick card",
          "lane-no-writer", TK_PICK)
# The writer got the pick in an earlier turn, so this turn's lane send has no writer send behind it: refused.
tk_refuse("a coordinator pick sent to a lane whose writer send is from an earlier turn is refused",
          "writer-earlier-turn", TK_PICK)

# MARKER FORMS. The line opens with `Coordinator picks` or with `(coordinator pick`, and the match is case-insensitive.
# The marker is `Coordinator pick` followed by a word boundary, after markdown lead characters only, so the rule judges the
# first two forms and refuses each sent to a lane with no writer send.
tk_refuse("a Coordinator picks line sent to a lane with no writer send this turn is refused",
          "lane-no-writer", "Coordinator picks: icons-a")
tk_refuse("a parenthesised coordinator pick line sent to a lane with no writer send this turn is refused",
          "lane-no-writer", "(coordinator pick, icons-a)")
# The lower-case form is matched already. Kept so a change to the marker cannot lose it.
tk_refuse("a lower-case coordinator pick line sent to a lane with no writer send this turn is refused",
          "lane-no-writer", "coordinator pick: icons-a")

# LIST MARKS. A markdown list mark before the marker is part of the lead, as the record's "after optional markdown marks" says.
# A bullet or a numbered pick line is refused with no writer send, as the plain line is.
tk_refuse("a bullet coordinator pick line sent to a lane with no writer send this turn is refused",
          "lane-no-writer", "- Coordinator pick: icons-a")
tk_refuse("a numbered coordinator pick line sent to a lane with no writer send this turn is refused",
          "lane-no-writer", "1. Coordinator pick: icons-a")
# CONTROL: the bullet line passes once the writer got the same pick this turn.
tk_allow("a bullet coordinator pick line passes when the writer got the same pick this turn",
         "writer-same-turn", "- Coordinator pick: icons-a")

# CREATE_SESSION. A coordinator's create_session whose prompt opens with a Coordinator pick line is judged the same way.
# The rule judges a create_session prompt as it judges a send_message, so a start with the pick in its prompt is refused with
# no writer send.
tk_refuse("a create_session whose prompt has a Coordinator pick line is refused when the writer got no pick this turn",
          "lane-no-writer", TK_PICK, tool=TK_CREATE)
# CONTROL: with the writer's send this turn, the same start passes.
tk_allow("a create_session whose prompt has a Coordinator pick line passes when the writer got the pick this turn",
         "writer-same-turn", TK_PICK, tool=TK_CREATE)

# UNREAD WRITER. A transcript with no page read names no writer, so the rule cannot judge the route. It allows the send and
# prints one stderr line that names the rule, as it does for a transcript it cannot read. A send straight to the writer allows too.
tk_allow("a coordinator pick sent to a lane from a transcript with no page read is allowed, with a stderr line that names the rule",
         "unread-writer", TK_PICK, err=(TK_RULE,))
tk_allow("a coordinator pick sent to the page writer from a transcript with no page read is allowed, with a stderr line that names the rule",
         "unread-writer", TK_PICK, target=TK_WRITER, err=(TK_RULE,))

# THE CARD MUST COUNT. The lane send passes only on a writer send this turn that the cloud delivered, that carries the
# Coordinator pick line for this pick, and that is not an agent's record. Each refusal below drops one of those tests.
tk_refuse("a coordinator pick sent to a lane is refused when the writer's send this turn was not delivered",
          "writer-undelivered", TK_PICK)
tk_refuse("a coordinator pick sent to a lane is refused when the writer's send this turn carries no Coordinator pick line",
          "writer-no-marker", TK_PICK)
tk_refuse("a coordinator pick sent to a lane is refused when the writer's send this turn is an agent's record",
          "writer-sidechain", TK_PICK)
# ONE CARD PER PICK. The writer's card for icons-a does not clear a send of colours-b: the card must carry the pick's own line.
tk_refuse("a coordinator pick sent to a lane is refused when the writer's card this turn is for another pick",
          "writer-same-turn", TK_PICK_B)

# FAIL OPEN, SAID ON STDERR. A transcript that cannot be read, or a code error inside the rule, allows, and says so on
# stderr, so the owner can see the rule did not judge.
tk_allow("a coordinator pick whose transcript cannot be read is allowed, with a stderr line that names the rule",
         "never-written", TK_PICK, err=(TK_RULE,))
tk_allow("a code error inside the rule is allowed, with a stderr line that names the rule",
         "code-error", TK_PICK, err=(TK_RULE,))

# CONTROLS, green on main: the lane send passes once the writer got the same pick this turn; a send to the writer passes; a
# message with no Coordinator pick line is not judged; a line that says Pick with no Coordinator is no marker.
tk_allow("a coordinator pick sent to a lane passes when the writer got the same pick this turn",
         "writer-same-turn", TK_PICK)
tk_allow("a coordinator pick sent to the page writer itself passes", "to-writer", TK_PICK, target=TK_WRITER)
tk_allow("a coordinator message with no Coordinator pick line passes", "no-marker", "Status: the icons are done.")
tk_allow("a line that opens Pick, with no Coordinator, is no marker", "lane-no-writer", "Pick: icons-a")
