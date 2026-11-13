# section 43100
FAMILY = "pick-reaches-page"
#
# Rule pick-reaches-page. A coordinator (its own record tags cs-build:coordinator) sends a send_message with a line
# that opens `Coordinator pick` or `Coordinator picks` (after markdown lead chars, a list lead such as `- `, `* `, `+ `,
# `1. ` or `1) `, and spaces; any case). The marker is followed, after optional spaces, by `:`, `.`, `,`, `;`, `-` and a
# space, or by the line's end: `Coordinator pick summary:` and `Coordinator pick-up:` are no marker. A pick sent to a lane
# is refused unless the page writer got a send in this turn (after the last human message; the whole transcript when it
# holds no human record) that names the same pick key. When this session is the page writer, a pick to a lane passes if
# this session wrote an item this turn that names the key. A pick sent to the page writer passes. The marker counts only
# at a line's start, outside a closed fenced block: an unclosed fence hides nothing. Only a coordinator's send_message is
# judged; no own record, no own session id or no transcript fails open. A message with no marker reads no transcript. The
# page writer is the `writer` in the newest ArtifactData get of meta/page (lint/_transcript.py). With no meta/page
# read, it is the `page-writer` key of the layout extras file of the checkout that holds the cwd (lint/layout.py); with
# neither, no writer is known, and a pick to a lane passes.
PK_RULE = "pick-reaches-page"
PK_SEND = "mcp__claude-code-remote__send_message"
PK_OWN = "session_PKOWN01"  # the coordinator; override.remote_session_id reads cse_PKOWN01 as this id
PK_ENV = {"CLAUDE_CODE_REMOTE_SESSION_ID": "cse_PKOWN01"}
PK_WRITER = "session_PKWRITER01"  # the page writer: the `writer` the meta/page read names
PK_LANE = "session_PKLANE01"  # a lane the coordinator sends a pick to
PK_OLD_WRITER = "session_PKOLDWRITER01"  # the writer an earlier meta/page read named: the newest read decides
PK_PICK = "Coordinator pick: icons-a"
PK_DIR = os.path.join(ROOT, "pickrec")
PK_PROBE = os.path.join(PK_DIR, "pk-probe.py")  # the load-brake probe, run as the guard, with its open spy
PK_TURN_ONE = "Owner: pick the icons for the page."
PK_TURN_TWO = "Owner: and the colors too."
PK_LAYOUT_WRITER = "session_PKLAYOUT01"  # the writer the layout extras key `page-writer` names, with no meta/page read
PK_LAYOUT_REPO = os.path.join(PK_DIR, "layout-repo")  # a checkout whose layout extras name PK_LAYOUT_WRITER
PK_NOKEY_REPO = os.path.join(PK_DIR, "nokey-repo")  # a checkout whose layout extras name no page writer


def pk_path(name):
    """The transcript fixture for one case: a JSONL file under this run's folder."""
    return os.path.join(PK_DIR, name + ".jsonl")


def pk_page_read(tool_id, writer):
    """One paired ArtifactData get of meta/page whose result names `writer`, as the page's own read returns it."""
    return [role_use(tool_id, "ArtifactData", {"action": "get", "collection": "meta", "doc_id": "page"}),
            role_result(tool_id, json.dumps({"id": "page", "writer": writer}))]


def pk_send(tool_id, target, text):
    """One paired send_message to `target` whose result is the cloud's delivered body."""
    return [role_use(tool_id, PK_SEND, {"session_id": target, "message": text}),
            role_result(tool_id, '{"status":"delivered"}')]


def pk_send_failed(tool_id, target, text):
    """One paired send_message to `target` whose result is an error: the send did not reach the session."""
    return [role_use(tool_id, PK_SEND, {"session_id": target, "message": text}),
            role_result_block(tool_id, is_error=True, content=[{"type": "text", "text": "not delivered"}])]


def pk_item_set(tool_id, key, collection="items", verb="set"):
    """One paired ArtifactData set or update that writes `key` into `collection`, its data naming the pick `key`."""
    return [role_use(tool_id, "ArtifactData", {"action": verb, "collection": collection, "doc_id": key,
                                               "data": {"title": "Coordinator pick: " + key, "status": "stands"}}),
            role_result(tool_id, '{"version":2}')]


def pk_item_batch(tool_id, key):
    """One paired ArtifactData batch whose one write sets the item `key`, its data naming the pick `key`."""
    return [role_use(tool_id, "ArtifactData", {"action": "batch", "writes": [
                {"op": "set", "collection": "items", "doc_id": key,
                 "data": {"title": "Coordinator pick: " + key, "status": "stands"}}]}),
            role_result(tool_id, '{"applied":1}')]


def pk_item_get(tool_id, key):
    """One paired ArtifactData get of the item `key`: a read, no write."""
    return [role_use(tool_id, "ArtifactData", {"action": "get", "collection": "items", "doc_id": key}),
            role_result(tool_id, json.dumps({"id": key, "version": 2}))]


# The coordinator's own record, the writer's read and the lane's record: the head every coordinator fixture shares.
PK_HEAD = (role_call("o1", COORD_TAGS, session=PK_OWN) + pk_page_read("p1", PK_WRITER)
           + role_target_call("l1", LANE_TAGS, target=PK_LANE))
# The same head when this session is the page writer: the coordinator's own id is the writer the meta/page read names.
PK_OWN_HEAD = ([role_said(PK_TURN_ONE)] + role_call("o1", COORD_TAGS, session=PK_OWN)
               + pk_page_read("p1", PK_OWN) + role_target_call("l1", LANE_TAGS, target=PK_LANE))
# The layout route: the coordinator's own record and the lane's record, and no meta/page read at all.
PK_LAYOUT_HEAD = ([role_said(PK_TURN_ONE)] + role_call("o1", COORD_TAGS, session=PK_OWN)
                  + role_target_call("l1", LANE_TAGS, target=PK_LANE))
PK_LINES = {
    "turn-empty": [role_said(PK_TURN_ONE)] + PK_HEAD,
    "turn-writer-sent": [role_said(PK_TURN_ONE)] + PK_HEAD + pk_send("s1", PK_WRITER, PK_PICK),
    "turn-writer-earlier": [role_said(PK_TURN_ONE)] + PK_HEAD + pk_send("s1", PK_WRITER, PK_PICK)
                           + [role_said(PK_TURN_TWO)],
    "turn-writer-other": [role_said(PK_TURN_ONE)] + PK_HEAD + pk_send("s1", PK_WRITER, "Coordinator pick: colors-b"),
    "turn-writer-casefold": [role_said(PK_TURN_ONE)] + PK_HEAD
                            + pk_send("s1", PK_WRITER, "Coordinator pick: ICONS-A."),
    "turn-writer-no-key": [role_said(PK_TURN_ONE)] + PK_HEAD
                          + pk_send("s1", PK_WRITER, "Status: the page is up to date."),
    "turn-lane-sent": [role_said(PK_TURN_ONE)] + PK_HEAD + pk_send("s1", PK_LANE, PK_PICK),
    "lane-own": [role_said(PK_TURN_ONE)] + role_call("o1", LANE_TAGS, session=PK_OWN)
                + pk_page_read("p1", PK_WRITER) + role_target_call("l1", LANE_TAGS, target=PK_LANE),
    "no-own-record": [role_said(PK_TURN_ONE)] + pk_page_read("p1", PK_WRITER)
                     + role_target_call("l1", LANE_TAGS, target=PK_LANE),
    # Two meta/page reads: the newest names PK_WRITER, so a send to PK_OLD_WRITER is not a send to the writer.
    "two-page-reads": [role_said(PK_TURN_ONE)] + role_call("o1", COORD_TAGS, session=PK_OWN)
                      + pk_page_read("p0", PK_OLD_WRITER) + pk_page_read("p1", PK_WRITER)
                      + role_target_call("l1", LANE_TAGS, target=PK_LANE) + pk_send("s1", PK_OLD_WRITER, PK_PICK),
    "two-page-reads-new": [role_said(PK_TURN_ONE)] + role_call("o1", COORD_TAGS, session=PK_OWN)
                          + pk_page_read("p0", PK_OLD_WRITER) + pk_page_read("p1", PK_WRITER)
                          + role_target_call("l1", LANE_TAGS, target=PK_LANE) + pk_send("s1", PK_WRITER, PK_PICK),
    # The pick key is the whole rest of the line: a writer send naming a longer key names a different pick.
    "turn-writer-longer": [role_said(PK_TURN_ONE)] + PK_HEAD
                          + pk_send("s1", PK_WRITER, "Coordinator pick: icons-a and colors-b"),
    # This session is the page writer: its own item writes this turn are the writer's send.
    "own-wrote-set": PK_OWN_HEAD + pk_item_set("w1", "icons-a"),
    "own-wrote-batch": PK_OWN_HEAD + pk_item_batch("w1", "icons-a"),
    "own-wrote-update": PK_OWN_HEAD + pk_item_set("w1", "icons-a", verb="update"),
    "own-read-only": PK_OWN_HEAD + pk_item_get("w1", "icons-a"),
    "own-wrote-other-key": PK_OWN_HEAD + pk_item_set("w1", "colors-b"),
    "own-wrote-earlier": PK_OWN_HEAD + pk_item_set("w1", "icons-a") + [role_said(PK_TURN_TWO)],
    "own-wrote-none": PK_OWN_HEAD,
    "own-wrote-meta": PK_OWN_HEAD + pk_item_set("w1", "page", collection="meta"),
    # No human record: the whole transcript is the turn, so a writer send anywhere in it counts.
    "no-human-writer-sent": PK_HEAD + pk_send("s1", PK_WRITER, PK_PICK),
    "no-human-writer-sent-first": pk_send("s0", PK_WRITER, PK_PICK) + PK_HEAD,
    "no-human-none": PK_HEAD,
    # The writer's send whose result is an error still counts: only the call is read (pinned current behaviour).
    "undelivered-writer-send": [role_said(PK_TURN_ONE)] + PK_HEAD + pk_send_failed("s1", PK_WRITER, PK_PICK),
    # The layout route: no meta/page read, so the writer is the layout key of the checkout at the cwd.
    "layout-no-send": PK_LAYOUT_HEAD,
    "layout-writer-sent": PK_LAYOUT_HEAD + pk_send("s1", PK_LAYOUT_WRITER, PK_PICK),
    # A transcript that is not JSON records: no own record can be read, so the send fails open.
    "unreadable": ["this is not a transcript", "42", "[1, 2]"],
}


def write_pk_transcripts():
    """Write each fixture as JSONL, one record per line."""
    for name, lines in PK_LINES.items():
        write(pk_path(name), "\n".join(lines) + "\n")


lazy_fixture([pk_path(name) for name in PK_LINES], write_pk_transcripts)


def pk_build_repos():
    """Two checkouts for the layout route, each a `.git` folder and a layout extras file. One names PK_LAYOUT_WRITER as
    its page writer; the other names none, so its extras file holds only the kinds."""
    for where, extras in ((PK_LAYOUT_REPO, {"kinds": {}, "page-writer": PK_LAYOUT_WRITER}),
                          (PK_NOKEY_REPO, {"kinds": {}})):
        os.makedirs(os.path.join(where, ".git"), exist_ok=True)
        write(os.path.join(where, ".claude", "layout-extras.json"), json.dumps(extras) + "\n")


lazy_fixture([PK_LAYOUT_REPO, PK_NOKEY_REPO], pk_build_repos)


def pk_log(label, check):
    """Register one log check. LOG_CHECKS_EXTRA joined LOG_CHECKS in s40805, before this section, so the check joins
    LOG_CHECKS itself, under this family, and needs no fixture materialized for it."""
    global LOG_CHECKS
    LOG_FAMILY[label] = PK_RULE
    LOG_CHECKS = LOG_CHECKS + ((label, check),)
    FIXTURELESS_CHECKS.add(check)


def pk_refuse(name, message, transcript="turn-empty", target=PK_LANE, carries=(), cwd=NOGIT):
    """A coordinator's send_message the guard refuses. The reason names its rule. `cwd` is the checkout the send runs in."""
    add("pick-reaches-page: " + name, "deny", rule=PK_RULE, tool=PK_SEND, cwd=cwd, transcript=pk_path(transcript),
        env=PK_ENV, carries=carries, session_id=target, message=message)


def pk_allow(name, message, transcript="turn-empty", target=PK_LANE, env=PK_ENV, cwd=NOGIT):
    """A send_message the guard lets through silently. `cwd` is the checkout the send runs in."""
    add("pick-reaches-page: " + name, "allow", tool=PK_SEND, cwd=cwd, silent=True, transcript=pk_path(transcript),
        env=env, session_id=target, message=message)


# Refused: a pick to a lane, with no writer send this turn. Each marker form opens a line after its lead chars.
pk_refuse("a plain pick to a lane, with no writer send this turn, is refused, and the steer names triage or the writer",
          PK_PICK, carries=(("triage", "writer"),))
pk_refuse("a bold pick marker, **Coordinator pick:** icons-a, to a lane is refused",
          "**Coordinator pick:** icons-a")
pk_refuse("a heading pick marker, # Coordinator pick: icons-a, to a lane is refused", "# Coordinator pick: icons-a")
pk_refuse("a quoted pick marker, > Coordinator pick: icons-a, to a lane is refused", "> Coordinator pick: icons-a")
pk_refuse("a lowercase pick marker, coordinator pick: icons-a, to a lane is refused", "coordinator pick: icons-a")
pk_refuse("an italic pick marker, _Coordinator pick: icons-a_, to a lane is refused", "_Coordinator pick: icons-a_")
# Refused: the marker counts on any line of the message, not only the first.
pk_refuse("a pick marker on line three, after a blank line, to a lane is refused",
          "Two picks follow.\n\nCoordinator pick: icons-a")
# Refused: a lone quote, backtick or comment opener in the text before the marker does not hide it.
pk_refuse("a pick marker after a lone apostrophe in the line before it is refused",
          "Owner's call on the picks.\nCoordinator pick: icons-a")
pk_refuse("a pick marker after a lone backtick in the line before it is refused",
          "Use `icons for the page.\nCoordinator pick: icons-a")
pk_refuse("a pick marker after a comment opener in prose, /* in the line before it, is refused",
          "See the note /* about the picks\nCoordinator pick: icons-a")
# Refused: a fence ends at its closing line, so a marker after it is a real line.
pk_refuse("a pick marker after a fence that closes is refused: the fence ends at its closing line",
          "```\nsample\n```\nCoordinator pick: icons-a")
# Refused: a list lead before the marker makes a pick line, as a bullet or a numbered item does.
pk_refuse("a pick marker after a dash bullet is a list lead, and to a lane is refused", "- Coordinator pick: icons-a")
pk_refuse("a pick marker after a star bullet is a list lead, and to a lane is refused", "* Coordinator pick: icons-a")
pk_refuse("a pick marker after a plus bullet is a list lead, and to a lane is refused", "+ Coordinator pick: icons-a")
pk_refuse("a pick marker after a numbered dot list lead, 1. , is refused to a lane",
          "1. Coordinator pick: icons-a")
pk_refuse("a pick marker after a numbered paren list lead, 1) , is refused to a lane",
          "1) Coordinator pick: icons-a")
# Refused: the plural marker, and the record forms (a full stop, a comma, a colon after spaces, a semicolon, a spaced
# dash, a line end) all open a pick line.
pk_refuse("a plural marker, Coordinator picks: icons-a, to a lane is refused", "Coordinator picks: icons-a")
pk_refuse("a record marker with a full stop, - Coordinator pick., to a lane is refused", "- Coordinator pick.")
pk_refuse("a record marker with a comma, Coordinator pick, icons-a, to a lane is refused", "Coordinator pick, icons-a")
pk_refuse("a marker with spaces before its colon, Coordinator pick   : icons-a, to a lane is refused",
          "Coordinator pick   : icons-a")
pk_refuse("a marker with a semicolon, Coordinator pick; icons-a, to a lane is refused", "Coordinator pick; icons-a")
pk_refuse("a marker with a spaced dash, Coordinator pick - icons-a, to a lane is refused", "Coordinator pick - icons-a")
pk_refuse("a marker alone on its line, Coordinator pick, to a lane is refused", "Coordinator pick")
# Passes: the marker must be followed by a terminator; a word that goes on after `pick` is no marker.
pk_allow("a pick word followed by summary, Coordinator pick summary:, is no marker and passes",
         "Coordinator pick summary: icons-a")
pk_allow("a pick word followed by -up, Coordinator pick-up:, is no marker and passes",
         "Coordinator pick-up: icons-a")

# Passes: a marker that is not at a line's start, sits in a fenced block, or is not a pick at all.
pk_allow("a pick marker mid-line, not at a line start, passes", "We logged a Coordinator pick: icons-a earlier.")
pk_allow("a pick marker inside a fenced block passes", "Example:\n```\nCoordinator pick: icons-a\n```")
pk_allow("a shell comment, # Coordinator pick, inside a fenced block passes",
         "```bash\n# Coordinator pick: icons-a\n```")
pk_allow("a status line about icons-a, with no marker, passes", "Status: icons-a is in review.")
# Refused: an unclosed fence hides nothing, so a pick after it is judged.
pk_refuse("a pick after an unclosed backtick fence is judged: an unclosed fence hides nothing",
          "```\nCoordinator pick: icons-a")
pk_refuse("a pick after an unclosed tilde fence is judged: an unclosed fence hides nothing",
          "~~~\nCoordinator pick: icons-a")
pk_refuse("a pick after a one-line fenced note, ```a``` note, is judged: the note opens no fence",
          "```a``` note\nCoordinator pick: icons-a")
pk_refuse("a closed block hides its pick, and a pick after a later unclosed fence is judged",
          "```\nCoordinator pick: icons-a\n```\n```\nCoordinator pick: colors-b")
# Passes: a pick sent to the page writer is the route the rule asks for.
pk_allow("a pick sent to the page writer passes, with no earlier send this turn", PK_PICK, target=PK_WRITER)

# The turn rule: a pick to a lane passes only after the writer's send this turn names the same pick key.
pk_allow("a pick to a lane passes after the writer's send this turn names the same pick",
         PK_PICK, transcript="turn-writer-sent")
pk_refuse("a writer send naming the same pick, in an earlier turn, does not count: the pick to a lane is refused",
          PK_PICK, transcript="turn-writer-earlier")
pk_refuse("a writer send this turn naming a different pick does not count: the pick to a lane is refused",
          PK_PICK, transcript="turn-writer-other")
pk_allow("the pick key is casefolded and stripped: ICONS-A. to the writer, then icons-a in lowercase, passes",
         "coordinator pick: icons-a", transcript="turn-writer-casefold")
pk_refuse("a writer send this turn that names no pick does not count: the pick to a lane is refused",
          PK_PICK, transcript="turn-writer-no-key")
pk_refuse("a send to a lane this turn naming the same pick does not count: only the writer does",
          PK_PICK, transcript="turn-lane-sent")
pk_refuse("a writer send naming a longer pick key does not name this pick: the key is the whole rest of the line",
          PK_PICK, transcript="turn-writer-longer")
pk_refuse("a send to an older page writer does not count when a newer meta/page read names another writer",
          PK_PICK, transcript="two-page-reads")
pk_allow("a send to the newest page writer counts, though an older meta/page read named another writer",
         PK_PICK, transcript="two-page-reads-new")

# This session is the page writer: a pick to a lane passes only after its own item write this turn names the key.
pk_allow("a pick to a lane passes when this session is the page writer and its set of an item this turn names the key",
         PK_PICK, transcript="own-wrote-set")
pk_allow("a pick to a lane passes when this session is the page writer and its batch of an item this turn names the key",
         PK_PICK, transcript="own-wrote-batch")
pk_allow("a pick to a lane passes when this session is the page writer and its update of an item this turn names the key",
         PK_PICK, transcript="own-wrote-update")
pk_refuse("a page writer's get of an item naming the key is a read, not a write: the pick to a lane is refused",
          PK_PICK, transcript="own-read-only")
pk_refuse("a page writer's item write naming a different key does not count: the pick to a lane is refused",
          PK_PICK, transcript="own-wrote-other-key")
pk_refuse("a page writer's item write from an earlier turn does not count: the pick to a lane is refused",
          PK_PICK, transcript="own-wrote-earlier")
pk_refuse("a page writer that wrote no item this turn: the pick to a lane is refused",
          PK_PICK, transcript="own-wrote-none")
pk_refuse("a page writer's write naming the key outside the items collection is no keyed item: the pick to a lane is refused",
          PK_PICK, transcript="own-wrote-meta")

# No human record: the whole transcript is the turn, so the send counts wherever it sits in the transcript.
pk_allow("with no human record, a writer send naming the pick passes: the whole transcript is the turn",
         PK_PICK, transcript="no-human-writer-sent")
pk_allow("with no human record, a writer send naming the pick before the coordinator's record also passes",
         PK_PICK, transcript="no-human-writer-sent-first")
pk_refuse("with no human record and no writer send, the pick to a lane is refused",
          PK_PICK, transcript="no-human-none")

# The layout route: no meta/page read, so the writer is the page-writer key of the checkout at the cwd. With no writer
# known (no key, or no checkout at the cwd), the pick to a lane passes.
pk_refuse("with no meta/page read, a pick to a lane is refused while the layout's page writer has no send this turn",
          PK_PICK, transcript="layout-no-send", cwd=PK_LAYOUT_REPO, carries=("writer",))
pk_allow("with no meta/page read, a pick to a lane passes after the layout's page writer is sent the pick this turn",
         PK_PICK, transcript="layout-writer-sent", cwd=PK_LAYOUT_REPO)
pk_allow("with no meta/page read, a pick sent to the layout's page writer itself passes",
         PK_PICK, transcript="layout-no-send", target=PK_LAYOUT_WRITER, cwd=PK_LAYOUT_REPO)
pk_allow("with no meta/page read and a checkout whose layout key names no writer, a pick to a lane passes: no writer known",
         PK_PICK, transcript="layout-no-send", cwd=PK_NOKEY_REPO)
pk_allow("with no meta/page read and no checkout at the cwd, a pick to a lane passes: no writer known",
         PK_PICK, transcript="layout-no-send", cwd=NOGIT)

# Passes: only a coordinator's send is judged. A lane, no own record, no transcript and no own id all fail open.
pk_allow("a lane's own pick passes: only a coordinator's send is judged", PK_PICK, transcript="lane-own")
pk_allow("a coordinator send with no own record in the transcript passes: fail open", PK_PICK,
         transcript="no-own-record")
pk_allow("a coordinator send with no own session id in the environment passes: fail open", PK_PICK, env=None)
add("pick-reaches-page: a coordinator send with no transcript path passes: fail open", "allow", tool=PK_SEND,
    cwd=NOGIT, silent=True, env=PK_ENV, session_id=PK_LANE, message=PK_PICK)
# Passes: a pick written into another tool is not a send_message.
sh("pick-reaches-page: a pick written into a Bash echo is not a send and passes", "echo 'Coordinator pick: icons-a'",
   "allow", silent=True, transcript=pk_path("turn-empty"), env=PK_ENV, cwd=NOGIT)

# Controls that pin the scanner and the readers as they stand (green on the current head). Each names what it pins.
pk_allow("a // prose line with no pick marker passes: a comment opener in prose is no marker", "// see the picks below")
pk_refuse("a // prose line before a pick marker does not hide the pick", "// see below\nCoordinator pick: icons-a")
pk_allow("a # prose line with no pick marker passes", "# see the picks below")
pk_allow("a lone apostrophe in plain text with no pick marker passes", "Owner's note: the page is up to date.")
pk_allow("a lone apostrophe before a pick sent to the page writer passes: the writer route passes",
         "Don't stop.\nCoordinator pick: icons-a", target=PK_WRITER)
pk_allow("a transcript that holds no JSON record passes: fail open", PK_PICK, transcript="unreadable")
pk_allow("a transcript path that does not exist passes: fail open", PK_PICK, transcript="missing")
pk_allow("a writer send that was not delivered still counts: pins current behaviour, only the call is read",
         PK_PICK, transcript="undelivered-writer-send")


# Scope before subject (P7): each fixture reads as the guard reads it, before any case asserts on the guard.
def pk_scope_check():
    """The page writer and the coordinator's own tags read from each fixture, through the real readers. A fixture
    named own-* is this session's own write: its page writer is the coordinator itself."""
    import _transcript as pk_transcript
    import own_session as pk_own
    problems = []
    for name in ("turn-empty", "turn-writer-sent", "turn-writer-earlier", "turn-writer-other", "turn-writer-casefold",
                 "turn-writer-no-key", "turn-lane-sent", "turn-writer-longer", "two-page-reads", "two-page-reads-new",
                 "own-wrote-set", "own-wrote-batch", "own-wrote-update", "own-read-only", "own-wrote-other-key",
                 "own-wrote-earlier", "own-wrote-none", "own-wrote-meta", "no-human-writer-sent",
                 "no-human-writer-sent-first", "no-human-none", "undelivered-writer-send"):
        records = pk_transcript.read_transcript(pk_path(name))
        want = PK_OWN if name.startswith("own-") else PK_WRITER
        if pk_transcript.page_writer_id(records) != want:
            problems.append(name + ": the page writer does not read as " + want)
        tags = pk_own.own_session_read(pk_path(name), PK_OWN)[0] or []
        if "cs-build:coordinator" not in tags:
            problems.append(name + ": the own record does not hold cs-build:coordinator")
    if pk_own.own_session_read(pk_path("lane-own"), PK_OWN)[0] is None:
        problems.append("lane-own: the own record is missing")
    if pk_own.own_session_read(pk_path("no-own-record"), PK_OWN)[0] is not None:
        problems.append("no-own-record: an own record reads for a session the transcript never names")
    return (not problems), "; ".join(problems) or "every fixture reads as its case assumes"


pk_log("pick-reaches-page: each fixture reads as its case assumes, before the guard is judged", pk_scope_check)


def pk_layout_transcripts_check():
    """Each layout transcript reads as its case assumes: its coordinator is the own record, and no meta/page read names a
    writer, so the layout key is the only route to a writer."""
    import _transcript as pk_transcript
    import own_session as pk_own
    for name in ("layout-no-send", "layout-writer-sent"):
        if pk_transcript.page_writer_id(pk_transcript.read_transcript(pk_path(name))) is not None:
            return False, name + ": a meta/page read names a writer, so the layout key is not the route"
        if "cs-build:coordinator" not in (pk_own.own_session_read(pk_path(name), PK_OWN)[0] or []):
            return False, name + ": the own record does not hold cs-build:coordinator"
    return True, "both layout transcripts hold no meta/page writer and the coordinator's own record"


def pk_layout_key_check():
    """Each checkout's layout page-writer key reads as its case assumes: one names PK_LAYOUT_WRITER, the other none."""
    import layout as pk_layout
    if pk_layout.page_writer_key(PK_LAYOUT_REPO) != PK_LAYOUT_WRITER:
        return False, "layout-repo: its page-writer key does not read as " + PK_LAYOUT_WRITER
    if pk_layout.page_writer_key(PK_NOKEY_REPO) is not None:
        return False, "nokey-repo: a page-writer key reads from an extras file that names none"
    return True, "layout-repo names its page writer, and nokey-repo names none"


pk_log("pick-reaches-page: the layout transcripts read as their cases assume, before the guard is judged",
       pk_layout_transcripts_check)
pk_log("pick-reaches-page: the layout checkouts read their page-writer key as their cases assume",
       pk_layout_key_check)


def pk_probe_script():
    """The load-brake probe as a script: it runs the guard under test and counts each open of the path it is told."""
    os.makedirs(PK_DIR, exist_ok=True)
    head = ("import os, sys\n"
            "sys.argv = [sys.argv[0], %r, os.environ['PK_PROBE_SIDE'], os.environ['PK_PROBE_SPEC']]\n" % GUARD)
    write(PK_PROBE, head + LB_PROBE)
    return PK_PROBE


def pk_spy_run(message, transcript, target=PK_LANE):
    """(decision, reason, opens): the guard's verdict on one coordinator send, and how many times it opened the
    transcript. The probe is the load-brake one (s39497): it counts opens through builtins.open and io.open."""
    path = pk_path(transcript)
    materialize(path)
    side = os.path.join(PK_DIR, "side-%s.json" % abs(hash(message + transcript)))
    if os.path.exists(side):
        os.remove(side)
    spec = json.dumps({"mode": "judge", "spy": path})
    case = {"raw": None, "tool": PK_SEND, "tool_input": {"session_id": target, "message": message}, "cwd": NOGIT,
            "session": None, "env_path": None, "config": None, "agent_id": None, "agent_type": None, "temp": None,
            "env": dict(PK_ENV, PK_PROBE_SIDE=side, PK_PROBE_SPEC=spec), "load": None, "transcript": path,
            "guard": pk_probe_script()}
    got, reason = decide(case)
    try:
        with open(side, encoding="utf-8") as handle:
            opens = json.load(handle).get("opened", 0)
    except (OSError, ValueError):
        opens = None  # the probe wrote no record: the guard crashed before it, which the verdict shows
    return got, reason, opens


def pk_read_check(name, message, want, reads):
    """A check that the guard's verdict is `want`, and that it opens the transcript when `reads` is True, else never."""
    def check():
        got, reason, opens = pk_spy_run(message, "turn-empty")
        if got != want:
            return False, "got %s (%s), want %s" % (got, reason[:70], want)
        if opens is None:
            return False, "the probe wrote no open count: the guard did not reach its judge"
        if (opens > 0) != reads:
            return False, "the transcript opened %d times, want %s" % (opens, "at least once" if reads else "never")
        return True, "%s, and the transcript opened %d times" % (want, opens)
    pk_log("pick-reaches-page: " + name, check)


# Cost (rule outcomes-mechanize-rules): a send with no marker reads no transcript. The control is the refused pick,
# which reads it, so the spy is shown to count a read here. The load-brake spy is the one home of the open count.
pk_read_check("a status send with no pick marker reads no transcript, so it costs no read",
              "Status: icons-a is in review.", "allow", reads=False)
pk_read_check("a pick to a lane reads the transcript before it is refused", PK_PICK, "deny", reads=True)


# The owner's override lifts a refused pick like any refusal (copy of the act checks above).
def pk_override_check(name, prompt, timed):
    """A one-act or timed override lets a refused pick through, as the override family's acts do."""
    config, session = ov_config("pick-" + name), "pk-ov-" + name
    transcript = pk_path("turn-empty")
    materialize(transcript)

    def call(seconds):
        return lambda: ov_call(PK_SEND, {"session_id": PK_LANE, "message": PK_PICK}, NOGIT, config, session, seconds,
                               env=PK_ENV, transcript=transcript)

    ok, why = ov_story([("with no override", call(0), "deny", PK_RULE)])
    if not ok:
        return False, why
    note = ov_type(config, session, prompt)
    if timed:
        steps = [("first call", call(60), "allow", PK_RULE),
                 ("call just before the end", call(OV_TIMED_SECONDS - 1), "allow", PK_RULE),
                 ("call at the end instant", call(OV_TIMED_SECONDS), "deny", PK_RULE)]
    else:
        steps = [("first call", call(60), "allow", PK_RULE),
                 ("second call, override spent", call(120), "deny", PK_RULE)]
    ok, why = ov_story(steps, note)
    if not ok:
        return False, why
    return True, "a refused pick, then allowed %s" % ("until the end" if timed else "once")


for _is_timed in (False, True):
    _pk_name = "a timed override lets a refused pick through until it ends" if _is_timed else \
        "a one-act override lets a refused pick through once, then refuses it again"
    _pk_check = (lambda t: lambda: pk_override_check("timed" if t else "once",
                                                     "override 15m" if t else "override", t))(_is_timed)
    pk_log("pick-reaches-page: " + _pk_name, _pk_check)
