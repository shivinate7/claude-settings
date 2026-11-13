# section 28433
FAMILY = "rework-off-page"
FAMILIES["rework-off-page"] = "the page writer: an item whose text says being reworked is not written unless its status is closed, and a str_replace that adds the phrase is refused"
#
# Rule rework-off-page (decision rework-leaves-page), built against a named incident: waiting item 97, Oct 30
# 15:40 CDT. Item 97 was being reworked while still open and answerable, so the owner could answer options that
# were about to change. An item whose text (title, context, why, an option or a step) says "being reworked", in
# any case, is refused unless the same write has status closed. A str_replace carries no status and its stored
# item is unseen, so it is refused when its new_str adds the phrase.

RW_DOC = "rework-stamp-check"
RW_TEXT = "Options being reworked."


def rw_item(**over):
    merged = {"id": RW_DOC, "context": RW_TEXT}
    merged.update(over)
    return ol_item(**merged)


def rw(name, expected, item, action="set", **extra):
    wp_write("rework off page: " + name, expected, "rework-off-page", item, action=action, doc_id=RW_DOC, **extra)


rw("an open decision with Options being reworked in its context is denied", "deny", rw_item())
rw("the same decision with status closed is allowed", "allow", rw_item(status="closed"))
rw("the phrase in capitals, BEING REWORKED, is denied", "deny", rw_item(context="Options BEING REWORKED."))
rw("a context that says the options were reworked last week is allowed", "allow",
   rw_item(context="The options were reworked last week."))
rw("an update that carries only context with the phrase is denied", "deny", {"context": RW_TEXT}, action="update")
rw("an update that carries status open and that context is denied", "deny", {"status": "open", "context": RW_TEXT},
   action="update")
rw("an update that carries status closed and that context is allowed", "allow",
   {"status": "closed", "context": RW_TEXT}, action="update")
rw("an update of the status only is allowed", "allow", {"status": "closed"}, action="update")
rw("an item set to another artifact is allowed", "allow", rw_item(), url="https://claude.ai/artifact/other")
add("rework off page: a str_replace that adds the phrase to context is denied", "deny", "rework-off-page",
    tool="ArtifactData", cwd=PQ_REPO, url=PQ_URL, action="str_replace", collection="items", doc_id=RW_DOC,
    field="context", old_str="Options are open.", new_str=RW_TEXT)
rw("a str_replace that adds the phrase in capitals is denied", "deny", None, action="str_replace",
   field="context", old_str="Options are open.", new_str="Options BEING REWORKED.")
rw("a str_replace that takes the phrase out of context is allowed", "allow", None, action="str_replace",
   field="context", old_str=RW_TEXT, new_str="Options are ready.")

# Item text other than context: title, why and an option's own text. The same write with status closed is allowed.
RW_QUIET = "The options are open."
rw("a title that says Options being reworked is denied", "deny", rw_item(context=RW_QUIET, title=RW_TEXT))
rw("a why that says Options being reworked is denied", "deny", rw_item(context=RW_QUIET, why=RW_TEXT))
rw("an option's how that says being reworked is denied", "deny",
   rw_item(context=RW_QUIET, options=ol_opt(0, how="This option is being reworked.")))
rw("an update that carries only a title with the phrase is denied", "deny", {"title": RW_TEXT}, action="update")
rw("a str_replace that adds the phrase to a title is denied", "deny", None, action="str_replace",
   field="title", old_str="Which CI job runs the stamp check?", new_str=RW_TEXT)
rw("a closed item whose title says Options being reworked is allowed", "allow",
   rw_item(status="closed", context=RW_QUIET, title=RW_TEXT))

# Other spellings of the same state. A bare past-tense re-worked or the noun rework is not the state.
rw("the phrase with a hyphen, being re-worked, is denied", "deny", rw_item(context="Options being re-worked."))
rw("the phrase under rework is denied", "deny", rw_item(context="Options under rework."))
rw("a context that says the options were re-worked last week is allowed", "allow",
   rw_item(context="The options were re-worked last week."))
rw("a context that says the rework landed last week is allowed", "allow",
   rw_item(context="The rework landed last week."))
add("rework off page: a batch with an open reworked item is denied", "deny", "rework-off-page",
    tool="ArtifactData", cwd=PQ_REPO, url=PQ_URL, action="batch",
    writes=[{"op": "set", "collection": "items", "doc_id": RW_DOC, "data": rw_item()}])


# --------------------------------------------------------------------------- the reason hygiene
#
# CLAUDE.md: "A refusal's printed remedy never names the forbidden target." The WHOLE printed
# reason is covered, not its last sentence, so no refusal may carry the file it refused. This is
# checked on every refused case rather than on a few, because one interpolated name is the whole
# defect and it can enter through any rule.
# `git checkout` and `git switch` are on this list for the pointer rule, and the list is global,
# so no rule may print either one in a remedy. The pointer rule's remedy is a worktree, and it
# names `git worktree add` instead, which is a different command and not the refused target.
