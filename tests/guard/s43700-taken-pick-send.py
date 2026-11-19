# section 43700
FAMILY = "pick-reaches-page"
#
# Rule pick-reaches-page, the send check (step page-taken-picks-area, row 2 of the goal). A coordinator's send_message whose
# text has a line that opens `Coordinator pick` is refused unless the same turn also sent the page writer (triage) the pick.
# The writer files a pick as a taken-pick card, which the owner can overrule; a pick sent only to a lane reaches the owner
# nowhere. The refusal's remedy names that card. It names no stands item: the owner's 15 Nov ruling (step
# page-no-preselected-pick) removed the stands fields. A send to the page writer passes. Only a coordinator's send is judged,
# and a turn is the records after the last human message. The page writer is the writer of the newest meta/page read in the
# transcript (lint/_transcript.py page_writer_id).
TK_RULE = "pick-reaches-page"
TK_SEND = "mcp__claude-code-remote__send_message"
TK_OWN = "session_TKCOORD01"  # the coordinator that sends the pick; TK_ENV below names it through the remote env id
TK_ENV = {"CLAUDE_CODE_REMOTE_SESSION_ID": "cse_TKCOORD01"}
TK_WRITER = "session_TKWRITER01"  # the page writer: the writer the meta/page read in each transcript names
TK_LANE = "session_TKLANE01"  # a lane the coordinator sends a pick to
TK_PICK = "Coordinator pick: icons-a"
TK_REMEDY = "send the pick to triage as a taken-pick card"  # the phrase the refusal's remedy must carry
TK_TURN_ONE = "Owner: pick the icons for the page."
TK_TURN_TWO = "Owner: and the colours too."
TK_DIR = os.path.join(ROOT, "takenpick")
TK_LINES = ("lane-no-writer", "writer-earlier-turn", "writer-same-turn", "to-writer", "no-marker")


def tk_path(name):
    """The transcript fixture for one case: a JSONL file under this run's folder."""
    return os.path.join(TK_DIR, name + ".jsonl")


def tk_page_read(tool_id, writer):
    """One paired ArtifactData get of meta/page whose result names `writer`, as the page's own read returns it."""
    return [role_use(tool_id, "ArtifactData", {"action": "get", "collection": "meta", "doc_id": "page"}),
            role_result(tool_id, json.dumps({"id": "page", "writer": writer}))]


def tk_send(tool_id, target, text):
    """One paired, delivered send_message to `target`: a send the turn already made."""
    return [role_use(tool_id, TK_SEND, {"session_id": target, "message": text}),
            role_result(tool_id, '{"status":"delivered"}')]


# The coordinator's own record, the writer's read, and the records of the lane and the writer, which the transcript must hold
# for the target-id-in-roster rule to know each target: the head every fixture shares.
TK_HEAD = ([role_said(TK_TURN_ONE)] + role_call("o1", COORD_TAGS, session=TK_OWN) + tk_page_read("p1", TK_WRITER)
           + role_target_call("l1", LANE_TAGS, target=TK_LANE) + role_target_call("w1", TRIAGE_TAGS, target=TK_WRITER))
TK_LINES_BY_NAME = {
    "lane-no-writer": TK_HEAD,
    # The writer got the pick in an earlier turn only: the owner's last words open a new turn, which sends nothing yet.
    "writer-earlier-turn": TK_HEAD + tk_send("s1", TK_WRITER, TK_PICK) + [role_said(TK_TURN_TWO)],
    # The writer got the same pick in this turn, so the lane send passes.
    "writer-same-turn": TK_HEAD + tk_send("s1", TK_WRITER, TK_PICK),
    "to-writer": TK_HEAD,
    "no-marker": TK_HEAD,
}


def write_tk_transcripts():
    """Each fixture transcript, one JSON record per line, under this run's folder."""
    os.makedirs(TK_DIR, exist_ok=True)
    for name in TK_LINES:
        with open(tk_path(name), "w", encoding="utf-8") as handle:
            handle.write("\n".join(TK_LINES_BY_NAME[name]) + "\n")


lazy_fixture([tk_path(name) for name in TK_LINES], write_tk_transcripts)


def tk_refuse(name, transcript, text, target=TK_LANE):
    """A coordinator's send_message the guard refuses. The reason names its rule and the taken-pick remedy, and no stands item."""
    add("pick-reaches-page: " + name, "deny", rule=TK_RULE, tool=TK_SEND, cwd=NOGIT, transcript=tk_path(transcript),
        env=TK_ENV, carries=(TK_REMEDY,), lacks=("stands",), session_id=target, message=text)


def tk_allow(name, transcript, text, target=TK_LANE):
    """A send_message the guard lets through silently."""
    add("pick-reaches-page: " + name, "allow", tool=TK_SEND, cwd=NOGIT, silent=True, transcript=tk_path(transcript),
        env=TK_ENV, session_id=target, message=text)


# RED on main: no rule holds a coordinator's pick back, so the pick sent to a lane with no writer send this turn is allowed.
tk_refuse("a coordinator pick sent to a lane with no writer send this turn is refused, and the remedy names the taken-pick card",
          "lane-no-writer", TK_PICK)
# RED on main: the writer got the pick in an earlier turn, so this turn's lane send has no writer send behind it.
tk_refuse("a coordinator pick sent to a lane whose writer send is from an earlier turn is refused",
          "writer-earlier-turn", TK_PICK)

# CONTROLS, green on main: the lane send passes once the writer got the same pick this turn; a send to the writer passes; a
# message with no Coordinator pick line is not judged.
tk_allow("a coordinator pick sent to a lane passes when the writer got the same pick this turn",
         "writer-same-turn", TK_PICK)
tk_allow("a coordinator pick sent to the page writer itself passes", "to-writer", TK_PICK, target=TK_WRITER)
tk_allow("a coordinator message with no Coordinator pick line passes", "no-marker", "Status: the icons are done.")
