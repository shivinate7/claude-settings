# section 42907
FAMILY = "dead-pr-wait"
# ---------------------------------------------------------------------------
# The placement end of step dead-pr-waits (part b). The step write path refuses a new or edited roadmap step
# whose text waits on a bare PR number (#N) with no blockedBy step slug. Matcher, as the step states it:
# (after|waits? on|waiting for|blocked on|once|until|when) #N, in lower case. Each refusal names the rule
# dead-pr-wait and the remedy blockedBy.
# Pinned as passing: a wait inside a fenced code block, a double-quoted phrase, a blockquote line or an inline
# code span, since it is quoted text, not a wait. That reading is to confirm.
# Not pinned: case (a capital "After #N" passes or refuses, unmeasured), and an edit that leaves an old bare
# wait untouched (the step file's status or updatedAt change). Write, Edit and MultiEdit are pinned. A Bash
# heredoc, jq and an MCP write are not pinned here.
DPW_RULE = "dead-pr-wait"
DPW_REMEDY = "blockedBy"  # the remedy each refusal names
DPW_DIR = os.path.join(NOGIT, "roadmap", "data", "steps")  # the step folder, under a directory that is no git tree
DPW_NEW = os.path.join(DPW_DIR, "dead-pr-wait-new.json")  # a step file that does not exist yet
DPW_BARE = os.path.join(DPW_DIR, "dead-pr-wait-bare.json")  # on disk, with blockedBy empty
DPW_SLUG = os.path.join(DPW_DIR, "dead-pr-wait-slug.json")  # on disk, with blockedBy naming a slug
DPW_NOT_STEP = os.path.join(NOGIT, "docs", "dead-pr-wait-note.json")  # a path that is not a step file
DPW_KEEP = object()  # dpw_step(): leave the blockedBy key out of the step
DPW_UPDATED = "2026-10-26T00:00:00Z"  # behind the clock, so the written-time rule never judges it
DPW_WAIT = "The lint lane waits on #42."
DPW_SLUG_BLOCK = ["lint-config-guard-paths"]
DPW_FILL = "Brief is written. " * 400  # a full-size note, about 7 KB


def dpw_step(note, blocked=DPW_KEEP):
    """The JSON text of a step with `note`. blockedBy is written only when given, so the key can be absent."""
    step = {"id": "dead-pr-wait-case", "title": "t", "status": "todo", "phase": "cleanup", "order": 1,
            "note": note, "updatedAt": DPW_UPDATED}
    if blocked is not DPW_KEEP:
        step["blockedBy"] = blocked
    return json.dumps(step, indent=2) + "\n"


os.makedirs(DPW_DIR, exist_ok=True)
with open(DPW_BARE, "w", encoding="utf-8") as _f:
    _f.write(dpw_step("Brief is written.", []))
with open(DPW_SLUG, "w", encoding="utf-8") as _f:
    _f.write(dpw_step("Brief is written.", DPW_SLUG_BLOCK))


def dpw_write(name, expected, note, blocked=DPW_KEEP, path=DPW_NEW):
    """One Write of a step with `note`, and blockedBy when given, to `path`."""
    content = dpw_step(note, blocked)
    if expected == "deny":
        add("dead-pr-wait: " + name, "deny", rule=DPW_RULE, tool="Write", cwd=NOGIT, carries=(DPW_REMEDY,),
            file_path=path, content=content)
    else:
        add("dead-pr-wait: " + name, "allow", tool="Write", cwd=NOGIT, file_path=path, content=content)


# DENY: a new step whose text waits on a bare #N, with no blockedBy slug.
dpw_write("a new step waiting on #42 with blockedBy left out is refused", "deny", DPW_WAIT)
dpw_write("a new step waiting on #42 with blockedBy an empty list is refused", "deny", DPW_WAIT, blocked=[])
dpw_write("a new step that runs after #42 with no blockedBy is refused", "deny", "Runs after #42 lands.")
dpw_write("a new step blocked on #42 with no blockedBy is refused", "deny", "The lint lane is blocked on #42.")
dpw_write("a new step that starts once #42 is in, with no blockedBy, is refused", "deny", "Starts once #42 is in.")
dpw_write("a wait on the second line of a note is refused", "deny", "Brief is written.\nThe lint lane waits on #42.")
dpw_write("a comment opener in the note text does not hide a wait on #42", "deny",
          "Path /* is a glob; the lint lane waits on #42.")
dpw_write("a lone apostrophe in the note text does not hide a wait on #42", "deny",
          "Owner's call: the lint lane waits on #42.")
dpw_write("a full-size note with the wait at its end is refused", "deny", DPW_FILL + DPW_WAIT)

# DENY: an edit, or a MultiEdit, that adds a bare wait to a step on disk whose blockedBy is empty.
add("dead-pr-wait: an edit that adds a wait on #42 to a step on disk with blockedBy empty is refused", "deny",
    rule=DPW_RULE, tool="Edit", cwd=NOGIT, carries=(DPW_REMEDY,), file_path=DPW_BARE,
    old_string='"note": "Brief is written."', new_string='"note": "Brief is written. The lint lane waits on #42."')
add("dead-pr-wait: a MultiEdit that adds a wait on #42 to a step on disk with blockedBy empty is refused", "deny",
    rule=DPW_RULE, tool="MultiEdit", cwd=NOGIT, carries=(DPW_REMEDY,), file_path=DPW_BARE,
    edits=[{"old_string": '"note": "Brief is written."',
            "new_string": '"note": "Brief is written. The lint lane waits on #42."'}])

# ALLOW: a wait that names a step slug in blockedBy, and an edit to a step on disk that already names one.
dpw_write("a new step waiting on #42 with a blockedBy slug is allowed", "allow", DPW_WAIT, blocked=DPW_SLUG_BLOCK)
add("dead-pr-wait: an edit that adds a wait on #42 to a step on disk with a blockedBy slug is allowed", "allow",
    tool="Edit", cwd=NOGIT, file_path=DPW_SLUG,
    old_string='"note": "Brief is written."', new_string='"note": "Brief is written. The lint lane waits on #42."')

# ALLOW: text that is not a wait on a bare #N. An ordinary mention, quoted, fenced or coded text, a slug wait,
# a step with no wait, and a path that is not a step file (the control for the deny cases above).
dpw_write("an ordinary mention of #42 with no wait word is allowed", "allow",
          "Compare the result with #42 before merging.")
dpw_write("a wait on #42 inside a fenced code block is allowed", "allow",
          "Example:\n```\nThe lint lane waits on #42.\n```\nThe lint is held.")
dpw_write("a wait on #42 inside double quotes is allowed", "allow",
          'The old note said "waits on #42" and was dropped.')
dpw_write("a wait on #42 on a blockquote line is allowed", "allow", "> The lint lane waits on #42.\n\nThe lint is held.")
dpw_write("a wait on #42 inside an inline code span is allowed", "allow",
          "The note reads `waits on #42` as an example.")
dpw_write("a wait on a step slug, with no #N, is allowed", "allow", "The lint lane waits on lint-config-guard-paths.")
dpw_write("a step with no wait at all is allowed", "allow", "Brief is written.")
dpw_write("a wait on #42 in a path that is not a step file is allowed", "allow", DPW_WAIT, path=DPW_NOT_STEP)
