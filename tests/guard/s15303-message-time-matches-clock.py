# section 15303
FAMILY = "message-time-matches-clock"
FAMILIES["message-time-matches-clock"] = "a send_message whose first non-blank line opens with a header stamp (a label of 1 to 4 words, then a comma, a colon or a spaced dash, then H:MM or HH:MM with optional seconds, then CST or CDT in any case) is refused when the stamp is wrong for the clock: a CST or CDT label that is not the clock's zone, a dated stamp more than 1 minute ahead, or an undated stamp 2 to 60 minutes ahead; an undated stamp more than 60 minutes ahead, or behind the clock, passes; a stamp later in the message, mid-line, on a status line, or on another tool passes. A dated ISO instant with an offset more than 1 minute ahead is refused too in `added` of an ArtifactData write to collection items (a whole instant, or a time fragment such as T20:24:00Z), `updatedAt` of a Write to a roadmap step file, each instant an Edit or MultiEdit writes to a roadmap step file (with or without a key), and the last literal `updatedAt` key in a Bash command (bare, quoted, or followed by `]`; then `:`, `=` or jq's `|=`; then a single- or double-quoted value); a time in prose, another field or collection, or a value with no offset passes"
#
# Rule message-time-matches-clock. A send_message whose first non-blank line, after its markdown lead chars, opens
# with a header stamp is refused when the stamp is wrong for the clock. A header stamp is `<label>` (1 to 4 words),
# then `,`, `:`, or a dash spaced on both sides (` - `, ` — `), then an optional date `YYYY-MM-DD `, then `H:MM` or
# `HH:MM`, an optional `:SS`, then the zone `CST` or `CDT` in any letter case. Anything may follow it. The zone must
# be the clock's own: a CDT stamp in CST season and a CST stamp in CDT season are refused, whatever the minutes.
# A dated stamp is an instant with its zone's offset, refused when it is more than 1 minute ahead, with no upper
# limit. An undated stamp is a signed minute-of-day offset mod 1440, refused only when it is 2 to 60 minutes ahead:
# more than 60 ahead reads as a quote from an earlier day, and passes. A stamp behind the clock passes. The wrap reads
# the short way: 00:01 at a clock of 23:59 is 2 minutes ahead. The clock is LOCAL_TIME_NOW. The rule reads no
# transcript and only the first line, so the cases here need no transcript, except the one lane brief, which needs a
# lane that lane-one-topic allows.
MTC_RULE = "message-time-matches-clock"
# The refusal names the now-central helper a session reads the time from, ~/.claude/bin/now-central. That path
# is the remedy, so the rule may name its folder, as handoff-unread does. The other fragments stay forbidden.
REASON_MAY_NAME["message-time-matches-clock"] = (".claude",)
MTC_TOOL = "mcp__claude-code-remote__send_later"  # a tool with a message field that is not send_message
MTC_CLOCK = "2026-11-07T13:22:00-06:00"           # 13:22 CST, the clock of most cases below
MTC_NEXT_DAY = "2026-11-08T00:01:00-06:00"        # 00:01 CST, the clock of the midnight pair
MTC_BODY = "detail " * 2500                       # a long body after the first line: about 17,500 characters
MTC_MORNING = "2026-11-08T07:08:00-06:00"        # 07:08 CST, the clock of the header-form, zone and window cases
MTC_CDT = "2026-10-30T13:22:00-05:00"            # 13:22 CDT, the clock of the CDT-season cases
# The helper a session reads the time from, later than the stamp. Every message-time refusal names it. The test
# side holds this one copy: no product constant holds the path alone (local_time's NOW_CENTRAL_POINTER is a sentence).
NOW_CENTRAL_PATH = "~/.claude/bin/now-central"


def mtc_env(clock):
    """The guard's environment with its clock fixed, so a verdict never depends on the real time."""
    return dict(ROLE_ENV, LOCAL_TIME_NOW=clock)


def mtc_refuse(name, message, clock=MTC_CLOCK, carries=(), lacks=()):
    """A send_message whose header stamp is off the clock. The guard refuses it, and the reason names the rule and
    the now-central helper."""
    add("message-time-matches-clock: " + name, "deny", rule=MTC_RULE, tool=SEND_MESSAGE, cwd=NOGIT,
        env=mtc_env(clock), session_id=ROLE_OTHER, message=message,
        carries=tuple(carries) + (NOW_CENTRAL_PATH,), lacks=lacks)


def mtc_allow(name, message, clock=MTC_CLOCK, transcript=None):
    """A send_message the guard lets through silently."""
    add("message-time-matches-clock: " + name, "allow", tool=SEND_MESSAGE, cwd=NOGIT, silent=True,
        env=mtc_env(clock), session_id=ROLE_OTHER, message=message, transcript=transcript)


# Refused: an incident stamp 18 minutes ahead. The reason prints the real time, so the sender can fix the stamp.
mtc_refuse("an incident stamp 18 minutes ahead is refused, and the reason prints the real time 13:22 CST",
           "Coordinator, 13:40 CST: pick 1 taken", carries=("13:22 CST",))
# Refused: 24 minutes ahead, on a clock that is not the default.
mtc_refuse("a stamp 24 minutes ahead, at a clock of 13:26, is refused",
           "Coordinator, 13:50 CST", clock="2026-11-07T13:26:00-06:00")
# Passes: 10 minutes behind. A stamp behind the clock passes.
mtc_allow("a stamp 10 minutes behind is allowed: a stamp behind the clock passes",
          "Coordinator, 13:12 CST: pick 1 taken")
# Refused: 4 minutes ahead. The limit is 1 minute, so this sits past it.
mtc_refuse("a stamp 4 minutes ahead is refused: the limit is 1 minute",
           "Coordinator, 13:26 CST")
# Passes: 4 minutes behind. A stamp behind the clock passes.
mtc_allow("a stamp 4 minutes behind is allowed: a stamp behind the clock passes",
          "Coordinator, 13:18 CST")
# Refused: `Now` is a label like any other, so `Now: 13:30 CST` is a header 8 minutes ahead.
mtc_refuse("a Now: header 8 minutes ahead, Now: 13:30 CST, is refused",
           "Now: 13:30 CST")
# Refused: markdown lead chars are read past, so the bold and quote forms carry the header too.
mtc_refuse("a bold header, **Coordinator, 13:40 CST**, is refused",
           "**Coordinator, 13:40 CST**")
mtc_refuse("a quoted header, > Coordinator, 13:40 CST, is refused",
           "> Coordinator, 13:40 CST: pick 1 taken")
# Refused: a date in the stamp is read, and the stamp is judged as the instant it names.
mtc_refuse("a dated header, 2026-11-07 13:40 CST, 18 minutes ahead is refused",
           "Coordinator, 2026-11-07 13:40 CST")
# Passes: dated the day before, the stamp is behind the clock. The date counts toward how far behind.
mtc_allow("a header dated the day before, at the clock's own minute, is allowed: a stamp behind the clock passes",
          "Coordinator, 2026-11-06 13:22 CST")
# Refused: dated the day after, the stamp is 1440 minutes ahead. A reader that ignores the date sees 0 and allows it.
mtc_refuse("a header dated the day after, at the clock's own minute, is refused: a date counts",
           "Coordinator, 2026-11-08 13:22 CST")
# Refused: 14:22 CDT is the instant 13:22 CST, but CDT is the wrong zone label in CST season, so it is refused.
mtc_refuse("a CDT header in CST season at the same instant, 14:22 CDT at 13:22 CST, is refused: the zone is wrong",
           "Coordinator, 14:22 CDT")
# Refused: 15:22 CDT is 14:22 CST, 60 minutes ahead. The reason prints the clock in CST, not CDT.
mtc_refuse("a CDT header in CST season, 60 minutes ahead, is refused, and the reason prints 13:22 CST, not CDT",
           "Coordinator, 15:22 CDT", carries=("13:22 CST",), lacks=("13:22 CDT",))
# Refused: only the header stamp is judged. A right stamp later on the line does not save an off header.
mtc_refuse("a header 18 minutes off is refused though a right stamp follows it on the line",
           "Coordinator, 13:40 CST: pick 1 taken (13:22 CST)")
# Refused: the marker is the first non-blank line, so blank lines above it do not hide the header.
mtc_refuse("a header after two blank lines is the first non-blank line, and is refused",
           "\n\nCoordinator, 13:40 CST: pick 1 taken")
# Passes: 23:50 is 11 minutes behind 00:01 across midnight. A stamp behind the clock passes.
mtc_allow("a header of 23:50 CST at 00:01 CST, 11 minutes behind across midnight, is allowed",
          "Coordinator, 23:50 CST", clock=MTC_NEXT_DAY)
# Refused: 00:01 at a clock of 23:59 is 2 minutes ahead across midnight. The mirror of the pair above.
mtc_refuse("a header of 00:01 CST at 23:59 CST, 2 minutes ahead across midnight, is refused",
           "Coordinator, 00:01 CST", clock="2026-11-07T23:59:00-06:00")
# Refused: a long body after an off header changes nothing. The first line is judged at full message size.
mtc_refuse("a header 18 minutes off with a long body after it is refused, however long the message",
           "Coordinator, 13:40 CST: pick 1 taken\n" + MTC_BODY)

# Refused: the incident. A header 2 minutes ahead is past the 1-minute limit.
mtc_refuse("a header 2 minutes ahead is refused: the incident, pick taken at 13:24 CST",
           "Coordinator, 13:24 CST: pick taken")
# Refused: 3 minutes ahead is past the limit.
mtc_refuse("a header 3 minutes ahead is refused: the limit is 1 minute",
           "Coordinator, 13:25 CST")
# Passes: exactly 1 minute ahead is inside the limit. The limit is inclusive.
mtc_allow("a header exactly 1 minute ahead is allowed: the limit is inclusive",
          "Coordinator, 13:23 CST")
# Passes: 3 minutes behind is behind the clock, so it passes.
mtc_allow("a header 3 minutes behind is allowed: a stamp behind the clock passes",
          "Coordinator, 13:19 CST")
# Passes: 23:59 at 00:01 is 2 minutes behind across midnight, so it passes.
mtc_allow("a header of 23:59 CST at 00:01 CST, 2 minutes behind across midnight, is allowed",
          "Coordinator, 23:59 CST", clock=MTC_NEXT_DAY)
# Passes: a dated header exactly 1 minute ahead is inside the limit.
mtc_allow("a dated header exactly 1 minute ahead is allowed",
          "Coordinator, 2026-11-07 13:23 CST")
# Passes: a ruling quoted mid-line carries its own stamp. Only the header stamp is read.
mtc_allow("a quoted ruling mid-line is allowed: the owner's stamp sits inside the line",
          'Coordinator, 13:22 CST: owner ruled (owner 2026-10-30 16:20 CDT) yes')
# Passes: a second stamp on the header line is not judged. The header stamp is the one that counts.
mtc_allow("a second stamp on the header line is allowed: only the header stamp is judged",
          "Coordinator, 13:22 CST: first offered 13:40 CST, pick 1 taken")
# Passes: a stamp only on line 2. The first line is a status line with no stamp.
mtc_allow("a stamp only on line 2 is not read: the first line is a status line",
          "Status: PR #12 merged.\nCoordinator, 13:40 CST: pick 1 taken")
# Passes: a stamp mid-line on a status line is not a header.
mtc_allow("a status line with a stamp mid-line is allowed",
          "Status: PR #12 merged (owner 16:36 CST).")
# Passes: a lane brief's first line holds no stamp, so the later stamp is not judged. The lane fixture lets the
# brief through lane-one-topic, so this case isolates this rule.
mtc_allow("a lane brief whose first line holds no stamp is allowed, though a stamp follows it",
          "Lane brief: icon-a. Topic: icons.\nCoordinator, 13:40 CST: go",
          transcript=role_path("step-topic-lane"))
# Refused: a label of four words is a header, so this stamp 18 minutes ahead is refused.
mtc_refuse("a label of four words, Owner of the lane, 13:40 CST, is a header and is refused",
           "Owner of the lane, 13:40 CST: pick 1 taken")
# Passes: a label with no comma, colon or dash is not a header, so the line passes.
mtc_allow("a label with no comma, colon or dash is not a header, so the line passes",
          "Coordinator 13:40 CST: pick 1 taken")
# Passes: the empty states. No first line means nothing to judge.
mtc_allow("an empty message passes: there is no first line to judge",
          "")
mtc_allow("a message of blank lines only passes: there is no first line to judge",
          "\n  \n\n")
# Passes: the full-size pair of the refusal above. A header 1 minute ahead with a long body is allowed.
mtc_allow("a header 1 minute ahead with a long body after it is allowed, however long the message",
          "Coordinator, 13:23 CST: pick 1 taken\n" + MTC_BODY)
# Passes: the rule judges send_message only. Another tool with a message field and the same stamp is not judged.
add("message-time-matches-clock: a send_later with a header 18 minutes off is not judged: the rule is send_message's",
    "allow", tool=MTC_TOOL, cwd=NOGIT, silent=True, env=mtc_env(MTC_CLOCK),
    message="Coordinator, 13:40 CST: pick 1 taken", delay_minutes=5)
# Passes: a dated header behind the clock passes, with seconds on the clock. 13:22 against 13:25:30 is 3 minutes behind.
mtc_allow("a dated header 3 minutes behind, at a clock of 13:25:30, is allowed: a stamp behind the clock passes",
          "Coordinator, 2026-11-07 13:22 CST", clock="2026-11-07T13:25:30-06:00")
# Passes: 16:36 is 9 hours 28 minutes ahead at 07:08. More than 60 minutes ahead reads as a quote from an earlier day.
mtc_allow("a header quoting another label's time, Owner, 16:36 CST, 9 hours 28 minutes ahead, is allowed: past 60 minutes it passes",
          "Owner, 16:36 CST: go", clock=MTC_MORNING)
# Refused: a header quoting another label's time, 18 minutes ahead. The reason tells the sender to open with its own label.
mtc_refuse("a header quoting another label's time, Owner, 13:40 CST, is refused, and the reason names your own label",
           "Owner, 13:40 CST: go", carries=("your own label",))

# The wider header form. Each form is refused at a stamp 32 minutes ahead of 07:08, and passes at the clock's own minute.
# Refused: a 1-digit hour.
mtc_refuse("a 1-digit hour header, Triage, 7:40 CST, 32 minutes ahead at 07:08, is refused",
           "Triage, 7:40 CST: x", clock=MTC_MORNING)
mtc_allow("a 1-digit hour header at the clock's own minute, Triage, 7:08 CST, is allowed",
          "Triage, 7:08 CST: x", clock=MTC_MORNING)
# Refused: a spaced em dash in place of the comma.
mtc_refuse("a spaced em-dash header, 07:40 CST after the label, 32 minutes ahead at 07:08, is refused",
           "Coordinator — 07:40 CST: x", clock=MTC_MORNING)
mtc_allow("a spaced em-dash header at the clock's own minute, 07:08 CST after the label, is allowed",
          "Coordinator — 07:08 CST: x", clock=MTC_MORNING)
# Refused: a spaced hyphen in place of the comma.
mtc_refuse("a spaced hyphen header, 07:40 CST after the label, 32 minutes ahead at 07:08, is refused",
           "Coordinator - 07:40 CST: x", clock=MTC_MORNING)
mtc_allow("a spaced hyphen header at the clock's own minute, 07:08 CST after the label, is allowed",
          "Coordinator - 07:08 CST: x", clock=MTC_MORNING)
# Refused: a label of four words.
mtc_refuse("a four-word label header, Coordinator for the lane, 07:40 CST, 32 minutes ahead at 07:08, is refused",
           "Coordinator for the lane, 07:40 CST: x", clock=MTC_MORNING)
mtc_allow("a four-word label header at the clock's own minute, Coordinator for the lane, 07:08 CST, is allowed",
          "Coordinator for the lane, 07:08 CST: x", clock=MTC_MORNING)
# Refused: seconds after the time.
mtc_refuse("a header with seconds, Coordinator, 07:40:00 CST, 32 minutes ahead at 07:08, is refused",
           "Coordinator, 07:40:00 CST: x", clock=MTC_MORNING)
mtc_allow("a header with seconds at the clock's own minute, Coordinator, 07:08:00 CST, is allowed",
          "Coordinator, 07:08:00 CST: x", clock=MTC_MORNING)
# Refused: a lowercase zone.
mtc_refuse("a lowercase zone header, Coordinator, 07:40 cst, 32 minutes ahead at 07:08, is refused",
           "Coordinator, 07:40 cst: x", clock=MTC_MORNING)
mtc_allow("a lowercase zone header at the clock's own minute, Coordinator, 07:08 cst, is allowed",
          "Coordinator, 07:08 cst: x", clock=MTC_MORNING)

# The zone must be the clock's own. A wrong zone label is refused whatever the minutes.
# Refused: a CDT stamp at the clock's own minute, in CST season. The instant is an hour behind, so only the label is wrong.
mtc_refuse("a CDT header at the clock's own minute in CST season, Coordinator, 07:08 CDT, is refused: the zone is wrong",
           "Coordinator, 07:08 CDT: x", clock=MTC_MORNING)
# Refused: a CST stamp in CDT season. 12:22 CST is the instant 13:22 CDT, so only the zone label is wrong.
mtc_refuse("a CST header in CDT season at the same instant, Coordinator, 12:22 CST at 13:22 CDT, is refused: the zone is wrong",
           "Coordinator, 12:22 CST: x", clock=MTC_CDT)
# Passes: the CDT-season pair. A CDT stamp at the clock's own minute in CDT season is allowed.
mtc_allow("a CDT header at the clock's own minute in CDT season, Coordinator, 13:22 CDT, is allowed",
          "Coordinator, 13:22 CDT: x", clock=MTC_CDT)

# The undated window: 2 to 60 minutes ahead is refused, and past 60 it reads as a quote from an earlier day.
# Refused: 60 minutes ahead at 07:08 is the window's upper edge, and the edge is inside it.
mtc_refuse("a header 60 minutes ahead at 07:08 is refused: the window's upper edge is inside it",
           "Coordinator, 08:08 CST: x", clock=MTC_MORNING)
# Passes: 61 minutes ahead at 07:08 is past the window, so it reads as a quote from an earlier day.
mtc_allow("a header 61 minutes ahead at 07:08 is allowed: past 60 minutes it reads as a quote from an earlier day",
          "Coordinator, 08:09 CST: x", clock=MTC_MORNING)
# Refused: a dated stamp has no window. 16:36 on the same day is 9 hours 28 minutes ahead at 07:08, and is refused.
mtc_refuse("a dated header 9 hours 28 minutes ahead at 07:08 is refused: a dated stamp has no window",
           "Coordinator, 2026-11-08 16:36 CST: x", clock=MTC_MORNING)


# ---- the written values: ArtifactData `added`, a roadmap step's `updatedAt`, a literal `updatedAt` in Bash
# The same rule on more tools. Only these written values are judged, as ISO-8601 instants with an offset (`Z` or
# +-HH:MM): `added` in an ArtifactData write (set, update, each write of a batch) to collection `items`; `updatedAt`
# in a Write (the content's JSON) or an Edit (the new_string) to a roadmap step file; and a literal `updatedAt` in a
# Bash command, read as text, inside shell quotes or not. A value more than 1 minute ahead of the clock is refused.
# A value behind the clock passes, because a kept old value is always behind. Quoted times in prose and other fields pass.
# The cases mirror the incident in decision local-time-central: `added` 20:16Z written to items at a clock of 20:14Z,
# and a roadmap step `updatedAt` ahead of the clock, in the shape 2026-11-07T14:15:00-06:00.
MTC_WRITE_CLOCK = "2026-11-07T14:14:00-06:00"  # 14:14 CST, which is 20:14Z: the clock of every case below
MTC_WRITE_CARRIES = ("14:14 CST", "2026-11-07T14:14-06:00", "2026-11-07T20:14Z")  # the real time, with its offset, both ways
MTC_CDT_CLOCK = "2026-07-08T09:26:00-05:00"  # 09:26 CDT, which is 14:26Z: a clock in the other daylight season
MTC_CDT_CARRIES = ("09:26 CDT", "2026-07-08T09:26-05:00", "2026-07-08T14:26Z")  # the real time, with its -05:00 offset
MTC_ITEM_URL = "https://claude.ai/artifact/mtcwrites"  # the page whose items the ArtifactData cases write
MTC_STEP = os.path.join(NOGIT, "roadmap", "data", "steps", "silent-undo-edit-pass.json")  # a roadmap step file
MTC_NOT_STEP = os.path.join(NOGIT, "docs", "silent-undo-edit-pass.json")  # a path that is not a step file
MTC_OFF_STEP = '{"id": "silent-undo-edit-pass", "updatedAt": "2026-11-07T14:30:00-06:00"}\n'  # 16 minutes ahead


def mtc_write(name, expected, tool, clock=MTC_WRITE_CLOCK, carries=MTC_WRITE_CARRIES, lacks=(), **tool_input):
    """One case of the written-value rule: `tool_input`, run as `tool`, against `clock` (default MTC_WRITE_CLOCK).
    A deny must print each of `carries`, the now-central helper's path among them, and none of `lacks`."""
    if expected == "deny":
        add("message-time-matches-clock: " + name, "deny", rule=MTC_RULE, tool=tool, cwd=NOGIT,
            env=mtc_env(clock), carries=tuple(carries) + (NOW_CENTRAL_PATH,), lacks=lacks, **tool_input)
    else:
        add("message-time-matches-clock: " + name, "allow", tool=tool, cwd=NOGIT, silent=True,
            env=mtc_env(clock), **tool_input)


def mtc_set(name, expected, data, action="set", collection="items", doc_id="silent-undo-edit-pass",
            clock=MTC_WRITE_CLOCK, carries=MTC_WRITE_CARRIES, lacks=()):
    """An ArtifactData write of one document: `data` to `collection`, on the page the cases name, at `clock`."""
    mtc_write(name, expected, "ArtifactData", clock=clock, carries=carries, lacks=lacks, url=MTC_ITEM_URL,
              action=action, collection=collection, doc_id=doc_id, data=data)


def mtc_batch(name, expected, writes):
    """An ArtifactData batch of `writes`, each one a dict of op, collection, doc_id and data."""
    mtc_write(name, expected, "ArtifactData", url=MTC_ITEM_URL, action="batch", writes=writes)


def mtc_bash(name, expected, command, clock=MTC_WRITE_CLOCK, carries=MTC_WRITE_CARRIES, transcript=None):
    """A Bash command whose text carries, or does not carry, a literal updatedAt value. A case whose command needs
    another clock, or a transcript for another rule to allow it, names both; the rest keep the 14:14 CST clock."""
    mtc_write(name, expected, "Bash", clock=clock, carries=carries, command=command, transcript=transcript)


# Refused: an `added` in items 4 minutes ahead. The limit is 1 minute, so this is past it.
mtc_set("an added 4 minutes ahead in items is refused", "deny",
        {"id": "silent-undo-edit-pass", "added": "2026-11-07T20:18:00Z"})
# Passes: an `added` 5 minutes behind is behind the clock, so it passes.
mtc_set("an added 5 minutes behind in items is allowed: a value behind the clock passes", "allow",
        {"id": "silent-undo-edit-pass", "added": "2026-11-07T20:09:00Z"})
# Refused: the offset form, 11 minutes ahead (14:25 CST is 20:25Z).
mtc_set("an added 14:25 at -06:00, 11 minutes ahead, in items is refused", "deny",
        {"id": "silent-undo-edit-pass", "added": "2026-11-07T14:25:00-06:00"})
# Passes: 14:14 at -05:00 is 19:14Z, 60 minutes behind the clock, so it passes.
mtc_set("an added of 14:14 at -05:00 in items is allowed: 60 minutes behind, a value behind passes", "allow",
        {"id": "silent-undo-edit-pass", "added": "2026-11-07T14:14:00-05:00"})
# Refused: 14:14 at -07:00 is 21:14Z, 60 minutes ahead. A reader that drops the offset sees 0 and allows it.
mtc_set("an added of 14:14 at -07:00 in items is refused: 60 minutes ahead, the offset counts", "deny",
        {"id": "silent-undo-edit-pass", "added": "2026-11-07T14:14:00-07:00"})
# Refused: an update is judged as a set is.
mtc_set("an update that sets an added 4 minutes ahead in items is refused", "deny",
        {"added": "2026-11-07T20:18:00Z"}, action="update")
# Passes: an update that sets a value 10 minutes behind passes.
mtc_set("an update that sets an added 10 minutes behind in items is allowed", "allow",
        {"added": "2026-11-07T20:04:00Z"}, action="update")
# Refused: each write of a batch is judged. The first is exact, the second 16 minutes ahead.
mtc_batch("a batch whose second write sets an added 16 minutes ahead is refused", "deny", [
    {"op": "set", "collection": "items", "doc_id": "silent-undo-edit-pass",
     "data": {"id": "silent-undo-edit-pass", "added": "2026-11-07T20:14:00Z"}},
    {"op": "set", "collection": "items", "doc_id": "silent-undo-edit-next",
     "data": {"id": "silent-undo-edit-next", "added": "2026-11-07T20:30:00Z"}}])
# Refused: a step Write, judged on the content's JSON, 16 minutes ahead.
mtc_write("a roadmap step Write with updatedAt 14:30 at -06:00 is refused", "deny", "Write",
          file_path=MTC_STEP, content=MTC_OFF_STEP)
# Refused: the stamp sits after a full-size note. The whole content is read, however long it is.
mtc_write("a roadmap step Write whose updatedAt follows a full-size note is refused, however long the content",
          "deny", "Write", file_path=MTC_STEP,
          content='{"id": "silent-undo-edit-pass", "note": "' + MTC_BODY + '", "updatedAt": "2026-11-07T14:30:00-06:00"}\n')
# Refused: a step Edit, judged on its new_string. The old_string holds an exact time and is not the one judged.
mtc_write("a roadmap step Edit whose new_string holds updatedAt 14:30 at -06:00 is refused", "deny", "Edit",
          file_path=MTC_STEP, old_string='"updatedAt": "2026-11-07T14:14:00-06:00"',
          new_string='"updatedAt": "2026-11-07T14:30:00-06:00"')
# Refused: the literal form in a Bash heredoc, the shape the incident's writes took.
mtc_bash("a Bash heredoc with updatedAt=\"2026-11-07T14:30:00-06:00\" is refused", "deny",
         'cat > "$D/silent-undo-edit-pass.txt" <<\'EOF\'\nupdatedAt="2026-11-07T14:30:00-06:00"\nEOF')
# Refused: the JSON form in a Bash heredoc.
mtc_bash("a Bash heredoc of JSON with \"updatedAt\": 14:30 at -06:00 is refused", "deny",
         'cat > "$D/silent-undo-edit-pass.json" <<\'EOF\'\n{"id": "silent-undo-edit-pass", "updatedAt": "2026-11-07T14:30:00-06:00"}\nEOF')
# Refused: a comment opener, `#`, inside a double-quoted string does not hide the literal after it on the line.
mtc_bash("a Bash literal after a # inside a double-quoted string is refused", "deny",
         r"""echo "step #2 of 4"; printf '%s\n' 'updatedAt="2026-11-07T14:30:00-06:00"'""")
# Refused: a lone apostrophe in unquoted text does not hide the literal, though a quote-aware reader would skip it.
mtc_bash("a Bash literal after a lone apostrophe in unquoted text is refused", "deny",
         r"""echo Owner's step; printf '%s\n' 'updatedAt="2026-11-07T14:30:00-06:00"'""")
# Refused: an escaped JSON form in a double-quoted string is the same literal once the shell reads it.
mtc_bash("an escaped JSON updatedAt 14:30 at -06:00 in a double-quoted string is refused", "deny",
         r'''printf "%s\n" "{\"id\": \"silent-undo-edit-pass\", \"updatedAt\": \"2026-11-07T14:30:00-06:00\"}" > "$D/silent-undo-edit-pass.json"''')
# Refused: a literal on the second line of a multi-line single-quoted string is still a literal in the command.
mtc_bash("a Bash literal on line 2 of a multi-line single-quoted string is refused", "deny",
         r"""printf '%s\n' 'step one
updatedAt="2026-11-07T14:30:00-06:00"'""")

# Refused: 20:16Z is 2 minutes ahead, past the 1-minute limit. This is the incident's own value.
mtc_set("an added 20:16Z, 2 minutes ahead, in items is refused: the incident value is past the limit", "deny",
        {"id": "silent-undo-edit-pass", "added": "2026-11-07T20:16:00Z"})
# Passes: 20:15Z is 1 minute ahead, inside the limit. The limit is inclusive.
mtc_set("an added 20:15Z, 1 minute ahead, in items is allowed: the limit is inclusive", "allow",
        {"id": "silent-undo-edit-pass", "added": "2026-11-07T20:15:00Z"})
# Refused: the clock is 20:14:59Z, whose minute is 20:14, so 20:16Z is 2 minutes ahead. Kept to the second, the gap
# is 61 seconds, one whole minute, so the value would pass. The clock's seconds are cut to the minute first.
mtc_set("an added 20:16Z in items is refused at a clock of 20:14:59: the clock's seconds are cut to the minute",
        "deny", {"id": "silent-undo-edit-pass", "added": "2026-11-07T20:16:00Z"},
        clock="2026-11-07T14:14:59-06:00")
# Passes: 14:14 CST exact, in each form. The Z form first.
mtc_set("an added exactly 20:14Z in items is allowed", "allow",
        {"id": "silent-undo-edit-pass", "added": "2026-11-07T20:14:00Z"})
mtc_set("an added exactly 14:14 at -06:00 in items is allowed", "allow",
        {"id": "silent-undo-edit-pass", "added": "2026-11-07T14:14:00-06:00"})
# Passes: `added` is judged in collection items only. Answers and receipts are not judged, though 36 minutes off.
mtc_set("an added 36 minutes ahead in answers is allowed: only collection items is judged", "allow",
        {"id": "silent-undo-edit-pass", "added": "2026-11-07T20:50:00Z"}, collection="answers")
mtc_set("an added 36 minutes ahead in receipts is allowed: only collection items is judged", "allow",
        {"id": "silent-undo-edit-pass", "added": "2026-11-07T20:50:00Z"}, collection="receipts")
# Passes: other fields are not judged. `replied` in answers and `ruled` in items are 3 hours off, and pass.
mtc_set("a replied 3 hours off in answers is allowed: replied is not judged", "allow",
        {"id": "silent-undo-edit-pass", "replied": "2026-11-07T23:14:00Z"}, collection="answers")
mtc_set("a ruled 3 hours off in items is allowed: ruled is not judged", "allow",
        {"id": "silent-undo-edit-pass", "ruled": "2026-11-07T17:14:00Z"})
# Passes: a time in prose, HH:MM CST inside note or why, is not a written value.
mtc_set("an HH:MM CST time inside note and why in items is allowed: quoted times in prose pass", "allow",
        {"id": "silent-undo-edit-pass", "note": "Owner ruled at 13:40 CST: pick b.", "why": "Asked at 13:40 CST."})
# Passes: a value with no offset is not judged.
mtc_set("an added with no offset in items is allowed: a value with no offset is not judged", "allow",
        {"id": "silent-undo-edit-pass", "added": "2026-11-07T14:30:00"})
# Passes: an update that carries no added is not judged, the empty case of the field.
mtc_set("an update that carries no added is allowed", "allow", {"status": "closed"}, action="update")
# Passes: a batch of right writes, one of them in answers, is allowed.
mtc_batch("a batch of right writes, one in answers 36 minutes off, is allowed", "allow", [
    {"op": "set", "collection": "items", "doc_id": "silent-undo-edit-pass",
     "data": {"id": "silent-undo-edit-pass", "added": "2026-11-07T20:14:00Z"}},
    {"op": "set", "collection": "answers", "doc_id": "silent-undo-edit-pass",
     "data": {"id": "silent-undo-edit-pass", "added": "2026-11-07T20:50:00Z"}}])
# Passes: a step Write at 14:14 exact, in each form, and a step with no updatedAt at all.
mtc_write("a roadmap step Write at 20:14Z exact is allowed", "allow", "Write", file_path=MTC_STEP,
          content='{"id": "silent-undo-edit-pass", "updatedAt": "2026-11-07T20:14:00Z"}\n')
mtc_write("a roadmap step Write at 14:14 at -06:00 exact is allowed", "allow", "Write", file_path=MTC_STEP,
          content='{"id": "silent-undo-edit-pass", "updatedAt": "2026-11-07T14:14:00-06:00"}\n')
mtc_write("a roadmap step Write with no updatedAt is allowed: the empty case", "allow", "Write",
          file_path=MTC_STEP, content='{"id": "silent-undo-edit-pass"}\n')
mtc_write("a roadmap step Write with an updatedAt that has no offset is allowed", "allow", "Write",
          file_path=MTC_STEP, content='{"id": "silent-undo-edit-pass", "updatedAt": "2026-11-07T14:30:00"}\n')
# Passes: a Write to a path that is not a step file is not judged, though its updatedAt is 16 minutes ahead.
mtc_write("a Write to a non-step path holding updatedAt 14:30 at -06:00 is allowed", "allow", "Write",
          file_path=MTC_NOT_STEP, content=MTC_OFF_STEP)
# Passes: a step Edit at exact time, in each form.
mtc_write("a roadmap step Edit whose new_string holds 20:14Z exact is allowed", "allow", "Edit", file_path=MTC_STEP,
          old_string='"updatedAt": "2026-11-07T14:14:00-06:00"', new_string='"updatedAt": "2026-11-07T20:14:00Z"')
mtc_write("a roadmap step Edit whose new_string holds 14:14 at -06:00 exact is allowed", "allow", "Edit",
          file_path=MTC_STEP, old_string='"updatedAt": "2026-11-07T20:14:00Z"',
          new_string='"updatedAt": "2026-11-07T14:14:00-06:00"')
# Passes: the literal forms at exact time, in each form.
mtc_bash("a Bash heredoc with updatedAt=\"2026-11-07T20:14:00Z\" exact is allowed", "allow",
         'cat > "$D/silent-undo-edit-pass.txt" <<\'EOF\'\nupdatedAt="2026-11-07T20:14:00Z"\nEOF')
mtc_bash("a Bash heredoc of JSON with updatedAt 14:14 at -06:00 exact is allowed", "allow",
         'cat > "$D/silent-undo-edit-pass.json" <<\'EOF\'\n{"id": "silent-undo-edit-pass", "updatedAt": "2026-11-07T14:14:00-06:00"}\nEOF')
# Passes: `updatedAt=$T` is a shell variable, not a literal, so the value the variable takes is not read.
mtc_bash("a Bash updatedAt=$T from a shell variable is allowed: a variable is not a literal", "allow",
         'T=$(date -u +%Y-%m-%dT%H:%M:%SZ); echo updatedAt=$T')


# Passes: an old updatedAt or added that a write keeps, resends or quotes is behind the clock, so it passes.
mtc_write("a roadmap step Write that changes note and keeps an old updatedAt 2026-11-06T18:00Z is allowed", "allow",
          "Write", file_path=MTC_STEP,
          content='{"id": "silent-undo-edit-pass", "note": "Changed the note.", "updatedAt": "2026-11-06T18:00:00Z"}\n')
mtc_write("a roadmap step Edit whose new_string carries the old updatedAt 2026-11-06T18:00Z is allowed", "allow",
          "Edit", file_path=MTC_STEP, old_string='"note": "Old note."',
          new_string='"note": "New note.",\n  "updatedAt": "2026-11-06T18:00:00Z"')
mtc_set("an ArtifactData set that resends an old added 2026-11-01T10:00Z in items is allowed", "allow",
        {"id": "silent-undo-edit-pass", "added": "2026-11-01T10:00:00Z", "note": "Resent."})
mtc_bash("a Bash git log -S for the old updatedAt literal is allowed", "allow",
         """git log -S '"updatedAt": "2026-11-06T18:00:00Z"' --oneline -- roadmap/data/steps""")
mtc_bash("a Bash grep for the old updatedAt literal is allowed", "allow",
         """grep -rn '"updatedAt": "2026-11-06T18:00:00Z"' roadmap/data/steps""")
mtc_bash("a Bash heredoc fixture holding the old updatedAt literal is allowed", "allow",
         'cat > "$D/fixture.json" <<\'EOF\'\n{"id": "silent-undo-edit-pass", "updatedAt": "2026-11-06T18:00:00Z"}\nEOF')


# Passes: a repair that rewrites an ahead value to the clock. The command holds the ahead value first and the right
# time last. Only the last literal is the value the command leaves, so only that one is judged.
mtc_bash("a Bash sed repair of updatedAt from 14:30 to 14:14 at -06:00 is allowed: the last literal is the clock", "allow",
         r"""sed -i 's/"updatedAt": "2026-11-07T14:30:00-06:00"/"updatedAt": "2026-11-07T14:14:00-06:00"/' roadmap/data/steps/x.json""")
mtc_bash("a Bash Python string replace of updatedAt from 14:30 to 14:14 at -06:00 is allowed: the last literal is the clock",
         "allow",
         r'''python3 -c "import json; p='roadmap/data/steps/x.json'; s=open(p).read(); open(p,'w').write(s.replace('\"updatedAt\": \"2026-11-07T14:30:00-06:00\"', '\"updatedAt\": \"2026-11-07T14:14:00-06:00\"'))"''')
# Passes: `==` is a comparison, not a write, so the regex skips it. Only the assignment's value, 14:10 CST, is judged.
mtc_bash("a Bash Python == check of updatedAt 14:30 at -06:00, then an = write of 14:10, is allowed: a comparison is not judged",
         "allow",
         r"""python3 -c 'import json; d=json.load(open("roadmap/data/steps/x.json")); assert d["updatedAt"] == "2026-11-07T14:30:00-06:00"; d["updatedAt"] = "2026-11-07T14:10:00-06:00"; json.dump(d, open("roadmap/data/steps/x.json","w"))'""")
# Refused: the last literal is 14:30 at -06:00, 16 minutes ahead. The earlier 14:00 is behind, and does not hide it.
mtc_bash("a Bash sed that sets updatedAt 14:00 to 14:30 at -06:00, the last literal ahead, is refused", "deny",
         r"""sed -i 's/"updatedAt": "2026-11-07T14:00:00-06:00"/"updatedAt": "2026-11-07T14:30:00-06:00"/' roadmap/data/steps/x.json""")


# ---- the document through file_path, and the str_replace action: `added` written two more ways
# A set, an update or a batch entry may pass the document through `file_path`, a local JSON file, instead of `data`.
# A str_replace edits one top-level string field in place. Both can carry `added` into collection items, so both
# are judged. The refuse cases hold a value 10 minutes ahead (20:24Z); each pair holds the exact value (20:14Z).
MTC_FILE_DIR = os.path.join(ROOT, "mtc")  # a folder of the run folder, for the document files below
os.makedirs(MTC_FILE_DIR, exist_ok=True)


def mtc_doc_file(name, added):
    """A local JSON file holding one item document with `added`, under the run folder."""
    path = os.path.join(MTC_FILE_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"id": "silent-undo-edit-pass", "added": added}, f)
    return path


MTC_FILE_AHEAD = mtc_doc_file("ahead.json", "2026-11-07T20:24:00Z")  # 10 minutes ahead of the clock
MTC_FILE_EXACT = mtc_doc_file("exact.json", "2026-11-07T20:14:00Z")  # the clock itself

# Refused: a set whose document comes through file_path, 10 minutes ahead. The guard reads the file, not only data.
mtc_write("a set that passes an item through file_path with added 10 minutes ahead is refused", "deny",
          "ArtifactData", url=MTC_ITEM_URL, action="set", collection="items",
          doc_id="silent-undo-edit-pass", file_path=MTC_FILE_AHEAD)
mtc_write("an update that passes an item through file_path with added 10 minutes ahead is refused", "deny",
          "ArtifactData", url=MTC_ITEM_URL, action="update", collection="items",
          doc_id="silent-undo-edit-pass", file_path=MTC_FILE_AHEAD)
mtc_batch("a batch entry that passes an item through file_path with added 10 minutes ahead is refused", "deny", [
    {"op": "set", "collection": "items", "doc_id": "silent-undo-edit-pass", "file_path": MTC_FILE_AHEAD}])
# Passes: the same three with added at the clock itself, 20:14Z.
mtc_write("a set that passes an item through file_path with added exactly 20:14Z is allowed", "allow",
          "ArtifactData", url=MTC_ITEM_URL, action="set", collection="items",
          doc_id="silent-undo-edit-pass", file_path=MTC_FILE_EXACT)
mtc_write("an update that passes an item through file_path with added exactly 20:14Z is allowed", "allow",
          "ArtifactData", url=MTC_ITEM_URL, action="update", collection="items",
          doc_id="silent-undo-edit-pass", file_path=MTC_FILE_EXACT)
mtc_batch("a batch entry that passes an item through file_path with added exactly 20:14Z is allowed", "allow", [
    {"op": "set", "collection": "items", "doc_id": "silent-undo-edit-pass", "file_path": MTC_FILE_EXACT}])

# Refused: a str_replace of the added field in items, which moves its value to 10 minutes ahead (20:24Z).
mtc_write("a str_replace that moves added in items to 10 minutes ahead is refused", "deny", "ArtifactData",
          url=MTC_ITEM_URL, action="str_replace", collection="items", doc_id="silent-undo-edit-pass",
          field="added", old_str="2026-11-07T20:04:00Z", new_str="2026-11-07T20:24:00Z")
# Passes: the same str_replace to the clock itself, 20:14Z.
mtc_write("a str_replace that moves added in items to exactly 20:14Z is allowed", "allow", "ArtifactData",
          url=MTC_ITEM_URL, action="str_replace", collection="items", doc_id="silent-undo-edit-pass",
          field="added", old_str="2026-11-07T20:04:00Z", new_str="2026-11-07T20:14:00Z")

# ---- written forms the check judges: a value with no updatedAt key in a roadmap step Edit, a date-less fragment in a
# str_replace, and a shell assignment with a single-quoted pair. The check judges the value a write lands, not the key
# beside it. A shell command is judged only through a literal updatedAt key with a quoted value. An unquoted value, or a
# value with no key, is still missed.
# Refused: an Edit of a step file that writes 14:30 at -06:00 over an older instant. Its new_string has no key.
mtc_write("a roadmap step Edit that writes 14:30 at -06:00 over an older instant, with no updatedAt key, is refused",
          "deny", "Edit", file_path=MTC_STEP, old_string="2026-11-07T13:00:00-06:00",
          new_string="2026-11-07T14:30:00-06:00")
# Refused: the same write as one entry of a MultiEdit. The entry's new_string has no updatedAt key.
mtc_write("a roadmap step MultiEdit entry that writes 14:30 at -06:00 over an older instant, with no key, is refused",
          "deny", "MultiEdit", file_path=MTC_STEP,
          edits=[{"old_string": "2026-11-07T13:00:00-06:00", "new_string": "2026-11-07T14:30:00-06:00"}])
# Refused: the same entry with its updatedAt key, the form the check already reads. A control for the case above.
mtc_write("a roadmap step MultiEdit entry whose new_string holds updatedAt 14:30 at -06:00 is refused", "deny",
          "MultiEdit", file_path=MTC_STEP,
          edits=[{"old_string": '"updatedAt": "2026-11-07T13:00:00-06:00"',
                  "new_string": '"updatedAt": "2026-11-07T14:30:00-06:00"'}])
# Passes: the keyless Edit at a value 10 minutes behind the clock, and at the clock itself.
mtc_write("a roadmap step Edit that writes 14:04 at -06:00 over an older instant, with no updatedAt key, is allowed",
          "allow", "Edit", file_path=MTC_STEP, old_string="2026-11-07T13:00:00-06:00",
          new_string="2026-11-07T14:04:00-06:00")
mtc_write("a roadmap step Edit that writes exactly 20:14Z over an older instant, with no updatedAt key, is allowed",
          "allow", "Edit", file_path=MTC_STEP, old_string="2026-11-07T13:00:00-06:00",
          new_string="2026-11-07T20:14:00Z")
# Refused: a str_replace that sets added to the fragment T20:24:00Z. A fragment has no full instant to read.
mtc_write("a str_replace that sets added in items to the fragment T20:24:00Z is refused", "deny", "ArtifactData",
          url=MTC_ITEM_URL, action="str_replace", collection="items", doc_id="silent-undo-edit-pass",
          field="added", old_str="T20:04:00Z", new_str="T20:24:00Z")
# Passes: a str_replace that sets added to a full instant 10 minutes behind the clock.
mtc_write("a str_replace that moves added in items to 10 minutes behind is allowed", "allow", "ArtifactData",
          url=MTC_ITEM_URL, action="str_replace", collection="items", doc_id="silent-undo-edit-pass",
          field="added", old_str="2026-11-07T20:02:00Z", new_str="2026-11-07T20:04:00Z")
# Refused: a python3 -c dict assignment with a double-quoted key. A `]` sits between the key and the `=`.
mtc_bash("a Bash python3 -c dict assignment of updatedAt 14:30 at -06:00 is refused", "deny",
         r"""python3 -c 'd["updatedAt"] = "2026-11-07T14:30:00-06:00"'""")
# Refused: the same with a single-quoted key, d['updatedAt']=, and the value double-quoted.
mtc_bash("a Bash python3 -c assignment with a single-quoted updatedAt key, 14:30 at -06:00, is refused", "deny",
         r'''python3 -c "d['updatedAt']=\"2026-11-07T14:30:00-06:00\""''')
# Refused: a jq |= assignment of updatedAt 14:30 at -06:00. The `|` sits between the key and the value.
mtc_bash("a Bash jq |= assignment of updatedAt 14:30 at -06:00 is refused", "deny",
         r"""jq '.updatedAt |= "2026-11-07T14:30:00-06:00"' roadmap/data/steps/silent-undo-edit-pass.json""")
# Refused: a single-quoted key and value, 16 minutes ahead. The scan reads the command as text, not as shell tokens,
# so the quote style does not hide the literal from the clock.
mtc_bash("a Bash python3 -c assignment with a single-quoted key and value, 14:30 at -06:00, is refused", "deny",
         r'''python3 -c "import json; d=json.load(open('roadmap/data/steps/x.json')); d['updatedAt']='2026-11-07T14:30:00-06:00'"''')
# Passes: the same assignment 4 minutes behind the clock. A value behind the clock passes.
mtc_bash("a Bash python3 -c assignment with a single-quoted key and value, 14:10 at -06:00, is allowed", "allow",
         r'''python3 -c "import json; d=json.load(open('roadmap/data/steps/x.json')); d['updatedAt']='2026-11-07T14:10:00-06:00'"''')
# Passes: the value opens on a single quote and closes on a double one, 16 minutes ahead. The `\1` backreference holds
# the close to the open quote, so this mismatched pair is not a literal the scan reads.
mtc_bash("a Bash value opened on a single quote and closed on a double, 14:30 at -06:00, is allowed: the pair must match",
         "allow", r'''d['updatedAt']='2026-11-07T14:30:00-06:00"''')
# Refused: a dict literal with a single-quoted key and value, 16 minutes ahead.
mtc_bash("a Bash python3 -c dict literal with a single-quoted updatedAt, 14:30 at -06:00, is refused", "deny",
         r'''python3 -c "d={'updatedAt': '2026-11-07T14:30:00-06:00'}"''')
# Passes: the same dict literal 4 minutes behind the clock.
mtc_bash("a Bash python3 -c dict literal with a single-quoted updatedAt, 14:10 at -06:00, is allowed", "allow",
         r'''python3 -c "d={'updatedAt': '2026-11-07T14:10:00-06:00'}"''')
# Refused: the incident's Python write as written. Its value, 05:40Z on Nov 2, is 23:40 CST, which is 10 minutes ahead
# of a 23:30 CST clock. At the 14:14 CST clock that value is days behind, so that clock cannot refuse this command.
mtc_bash("the incident Python write, a single-quoted updatedAt 10 minutes ahead at 23:30 CST, is refused", "deny",
         INCIDENT_PYTHON_WRITE, clock="2026-11-01T23:30:00-06:00",
         carries=("23:30 CST", "2026-11-01T23:30-06:00", "2026-11-02T05:30Z"), transcript=TRIAGE_TRANSCRIPT)
# Passes: the same write at 23:41 CST, a minute after its value. A value behind the clock passes.
mtc_bash("the incident Python write at 23:41 CST, a minute after its value, is allowed", "allow",
         INCIDENT_PYTHON_WRITE, clock="2026-11-01T23:41:00-06:00", transcript=TRIAGE_TRANSCRIPT)
# Passes: a single-quoted repair from 14:30 to 14:10 at -06:00, the behind value last. Only the last keyed literal is
# judged, and it is behind the clock.
mtc_bash("a Bash single-quoted repair from 14:30 to 14:10 at -06:00, the behind value last, is allowed", "allow",
         r'''python3 -c "import json; d=json.load(open('roadmap/data/steps/x.json')); d['updatedAt']='2026-11-07T14:30:00-06:00'.replace(\"'updatedAt': '2026-11-07T14:30:00-06:00'\", \"'updatedAt': '2026-11-07T14:10:00-06:00'\")"''')
# Passes: a grep for a single-quoted key holds no instant, so no written value is judged.
mtc_bash("a Bash grep for a single-quoted updatedAt key with no instant is allowed", "allow",
         r'''grep "'updatedAt'" roadmap/data/steps/x.json''')
# Passes: // and /* inside quoted strings, beside an updatedAt 20 minutes behind. The scan must not crash or refuse.
mtc_bash("a Bash command with // and /* inside quoted strings, beside a behind updatedAt, is allowed", "allow",
         r'''echo "see http://claude.ai/x /* note */" && python3 -c "import json; print(json.dumps({\"updatedAt\": \"2026-11-07T13:54:00-06:00\"}))"''')
# Passes: a JSX-like text, <p>Don't</p>, beside a behind updatedAt. A lone apostrophe must not stop the scan.
mtc_bash("a Bash command with <p>Don't</p> text, beside a behind updatedAt, is allowed", "allow",
         r'''echo "<p>Don't</p>" && python3 -c "import json; print(json.dumps({\"updatedAt\": \"2026-11-07T13:54:00-06:00\"}))"''')
# Passes: an instant 16 minutes ahead in prose, beside a behind updatedAt. Only a literal updatedAt value is judged.
mtc_bash("a Bash command with an instant 16 minutes ahead in prose, beside a behind updatedAt, is allowed", "allow",
         r'''echo "due 2026-11-07T14:30:00-06:00 for the step" && python3 -c "import json; print(json.dumps({\"updatedAt\": \"2026-11-07T13:54:00-06:00\"}))"''')
# Passes: `!=` is a compare, not a write, so the value after it is not judged, even 16 minutes ahead at 14:14 CST.
mtc_bash("a Bash != compare of updatedAt to 14:30 at -06:00 is allowed: a compare writes no value", "allow",
         r'''python3 -c "import json; d=json.load(open('roadmap/data/steps/x.json')); print(d['updatedAt'] != '2026-11-07T14:30:00-06:00')"''')
# Passes: `>` is a compare too, so the value after it is not judged, even 16 minutes ahead at 14:14 CST.
mtc_bash("a Bash > compare of updatedAt to 14:30 at -06:00 is allowed: a compare writes no value", "allow",
         r'''python3 -c "import json; d=json.load(open('roadmap/data/steps/x.json')); print(d['updatedAt'] > '2026-11-07T14:30:00-06:00')"''')
# Refused at a CDT clock: the reason prints the clock with its -05:00 offset, and no CST offset.
mtc_set("an added 14 minutes ahead in items, at a CDT clock of 09:26, is refused: the reason prints -05:00", "deny",
        {"id": "silent-undo-edit-pass", "added": "2026-07-08T14:40:00Z"},
        clock=MTC_CDT_CLOCK, carries=MTC_CDT_CARRIES, lacks=("-06:00",))

# =========================================================================== 5i. SendMessage to a cloud session
