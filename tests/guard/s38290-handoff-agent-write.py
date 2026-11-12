# section 38290
FAMILY = "handoff-agent-write"
AW_RULE = "handoff-agent-write"
# The incident (the handoff lock report, Part 1: a builder agent overwrote its coordinator's handoff): an agent shares its
# parent's session id, so the agent's Write to the parent's handoff passed every handoff rule. These cases use the parent's session id (HS_SID),
# the parent's handoff on disk (HS_CFG, built by section 38287), and the agent's id on the payload.
AW_AGENT = "a1634141822b8dc54"              # the builder agent of the incident: 17 hex characters, a valid AGENT_ID
AW_EMPTY_CFG = os.path.join(ROOT, "aw-empty")   # a config folder with no handoff in it yet
AW_PREMISES = ("- P1 [assumed] The builder's own premise. Source: none. Checked never.",)   # the incident's second write
AW_WRITE = hs_text(premises=AW_PREMISES)    # every section, as the incident's Write held it
AW_FULL_SIZE = HS_FULL.replace(HS_BODIES["Where things stand"],
                               "Branch aw-tests at 2ac382cc6.\n" + "A line of state, kept.\n" * 6000)
AW_EDIT_OLD = "Nothing in flight.\n"
AW_EDIT_NEW = "Nothing in flight; the red run is recorded.\n"
AW_MULTI = [{"old_string": "Branch hsk-tests at", "new_string": "Branch hsk-tests2 at"},
            {"old_string": "The builder adds the check.", "new_string": "The builder adds the check, then the red run."}]
# The refusal tells the agent that it is an agent, that the handoff is its parent's, and that it must not retry.
# Each fragment is any-of, and the wording is not pinned.
AW_CARRIES = (("agent", "Agent"), ("parent", "Parent", "orchestrator", "coordinator"),
              ("retry", "Retry", "repeat", "Repeat", "again"))


def aw_scope():
    """The Edit and MultiEdit cases edit the parent's handoff as it stands on disk. An Edit whose old text is absent is
    allowed by the handoff rules, so those cases prove nothing unless the file holds the text they replace."""
    materialize(HS_CFG)
    try:
        with open(hs_handoff(HS_CFG), "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError as e:
        return False, "the parent's handoff is unreadable: %s" % e
    if text != HS_FULL:
        return False, "the parent's handoff on disk is not the full handoff the Edit cases name"
    for old in (AW_EDIT_OLD, AW_MULTI[0]["old_string"], AW_MULTI[1]["old_string"]):
        if old not in text:
            return False, "the parent's handoff on disk lacks the text %r the Edit cases replace" % old
    return True, "the parent's handoff on disk is the full handoff, and holds the text the Edit cases replace"


LOG_CHECKS_EXTRA.append(("handoff-agent-write: scope: the parent's handoff on disk holds the text the Edit cases replace",
                         aw_scope))

# A Write, Edit or MultiEdit of the parent's handoff from an agent is refused, whatever it holds. The rule runs before
# handoff-sections, so a refusal that would tell the agent how to pass the section check is never the one it reads.
add("handoff-agent-write: an agent's Write of the parent's handoff is refused, naming the rule and the parent",
    "deny", AW_RULE, tool="Write", cwd=NOGIT, session=HS_SID, config=HS_CFG, agent_id=AW_AGENT,
    carries=AW_CARRIES, file_path=hs_handoff(HS_CFG), content=AW_WRITE)
add("handoff-agent-write: an agent's Edit of the parent's handoff is refused, naming the rule and the parent",
    "deny", AW_RULE, tool="Edit", cwd=NOGIT, session=HS_SID, config=HS_CFG, agent_id=AW_AGENT,
    carries=AW_CARRIES, file_path=hs_handoff(HS_CFG), old_string=AW_EDIT_OLD, new_string=AW_EDIT_NEW)
add("handoff-agent-write: an agent's MultiEdit of the parent's handoff is refused, naming the rule and the parent",
    "deny", AW_RULE, tool="MultiEdit", cwd=NOGIT, session=HS_SID, config=HS_CFG, agent_id=AW_AGENT,
    carries=AW_CARRIES, file_path=hs_handoff(HS_CFG), edits=AW_MULTI)
# P8: the states the handoff reaches. Full-size, empty, and no handoff on disk yet.
add("handoff-agent-write: an agent's full-size Write of the parent's handoff is refused, naming the rule",
    "deny", AW_RULE, tool="Write", cwd=NOGIT, session=HS_SID, config=HS_CFG, agent_id=AW_AGENT,
    carries=AW_CARRIES, file_path=hs_handoff(HS_CFG), content=AW_FULL_SIZE)
add("handoff-agent-write: an agent's empty Write of the parent's handoff is refused, naming the rule",
    "deny", AW_RULE, tool="Write", cwd=NOGIT, session=HS_SID, config=HS_CFG, agent_id=AW_AGENT,
    carries=AW_CARRIES, file_path=hs_handoff(HS_CFG), content="")
add("handoff-agent-write: an agent's first Write of the parent's handoff, with no handoff on disk, is refused",
    "deny", AW_RULE, tool="Write", cwd=NOGIT, session=HS_SID, config=AW_EMPTY_CFG, agent_id=AW_AGENT,
    carries=AW_CARRIES, file_path=hs_handoff(AW_EMPTY_CFG), content=AW_WRITE)

# The controls. The same Write with no agent_id passes, so the refusals above are the agent's and not the content's.
add("handoff-agent-write: control: the same Write with no agent_id passes, silently",
    "allow", tool="Write", cwd=NOGIT, session=HS_SID, config=HS_CFG, silent=True,
    file_path=hs_handoff(HS_CFG), content=AW_WRITE)
add("handoff-agent-write: control: an agent writes its own notes file, not a handoff, and passes, silently",
    "allow", tool="Write", cwd=NOGIT, session=HS_SID, config=HS_CFG, agent_id=AW_AGENT, silent=True,
    file_path=os.path.join(NOGIT, "notes.md"), content=AW_WRITE)
add("handoff-agent-write: control: an agent writes the owner-feedback inbox beside the handoff, and passes, silently",
    "allow", tool="Write", cwd=NOGIT, session=HS_SID, config=HS_CFG, agent_id=AW_AGENT, silent=True,
    file_path=hs_inbox(HS_CFG), content=HS_INBOX_TEXT)
# A malformed agent_id is no agent's id to AGENT_ID, so the call is the session's own and the rule does not judge it.
add("handoff-agent-write: control: a malformed agent_id (a space and a slash) does not trigger the rule, silently",
    "allow", tool="Write", cwd=NOGIT, session=HS_SID, config=HS_CFG, agent_id="not an id/x", silent=True,
    file_path=hs_handoff(HS_CFG), content=AW_WRITE)
add("handoff-agent-write: control: a non-string agent_id does not trigger the rule, silently",
    "allow", tool="Write", cwd=NOGIT, session=HS_SID, config=HS_CFG, agent_id=42, silent=True,
    file_path=hs_handoff(HS_CFG), content=AW_WRITE)
