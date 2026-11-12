# section 43100
FAMILY = "rule9"  # the family of the lane start rules, with lane-effort-pin and lane-repo-tag

# ---- Lane title. A lane start's title opens with `Lane <branch slug>:`, so the owner can tell which branch a lane runs
# (rule lane-title-slug). The rule judges a create_session that tags a lane, and no other call. Its refusal prints the
# required form. Every case builds its lane start from section 29666 (LANE_TOOL, LANE_REPO, OWN_LANE_TAGS, LANE_PROMPT,
# LANE_EFFORT_FIELD, LANE_SOURCE_URL) and changes only its title, so the other lane rules pass and only this one can refuse.
TITLE_RULE = "lane-title-slug"
TITLE_FORM = ("Lane <branch slug>:", "Lane <slug>:")  # the remedy prints the form, in either spelling
TITLE_START = dict(tool=LANE_TOOL, cwd=LANE_REPO, tags=OWN_LANE_TAGS, prompt=LANE_PROMPT,
                   effort=LANE_EFFORT_FIELD, model="sonnet", source_url=LANE_SOURCE_URL)
# Full size: 32 characters, the longest slug the Git rule (git-slug-then-claim-number) allows.
FULL_SLUG = "abcdefghijklmnopqrstuvwxyz012345"
if len(FULL_SLUG) != 32:
    sys.exit("fixture setup failed: FULL_SLUG is %d characters, want 32" % len(FULL_SLUG))

# ---- Refused. A lane start whose title is missing, empty, a template placeholder, or not that form is denied. The
# refusal prints the required form, and never the session number as its example.
add("lane-title-slug: a lane start with a free title is denied", "deny", TITLE_RULE,
    title="Thermostat fan settings (Resideo)", carries=(TITLE_FORM,), lacks="Lane N", **TITLE_START)
add("lane-title-slug: a lane start with no title is denied", "deny", TITLE_RULE,
    carries=(TITLE_FORM,), **TITLE_START)
add("lane-title-slug: a lane start with an empty title is denied", "deny", TITLE_RULE,
    title="", carries=(TITLE_FORM,), **TITLE_START)
add("lane-title-slug: a lane start with the template placeholder as its title is denied", "deny", TITLE_RULE,
    title="Lane <branch slug>: <task>", carries=(TITLE_FORM,), **TITLE_START)
add("lane-title-slug: a title with the slug and no Lane word is denied", "deny", TITLE_RULE,
    title="lane-title-slug: do the task", carries=(TITLE_FORM,), **TITLE_START)
add("lane-title-slug: a title with Lane and no slug is denied", "deny", TITLE_RULE,
    title="Lane: do the task", carries=(TITLE_FORM,), **TITLE_START)
add("lane-title-slug: a title with no colon after the slug is denied", "deny", TITLE_RULE,
    title="Lane lane-title-slug do the task", carries=(TITLE_FORM,), **TITLE_START)
add("lane-title-slug: a title that names the slug after its words is denied", "deny", TITLE_RULE,
    title="Do the task, Lane lane-title-slug: fix it", carries=(TITLE_FORM,), **TITLE_START)
add("lane-title-slug: a title with a session number as its slug is denied", "deny", TITLE_RULE,
    title="Lane N20: do the task", carries=(TITLE_FORM,), **TITLE_START)
add("lane-title-slug: a title with a title-cased name, not a branch slug, is denied", "deny", TITLE_RULE,
    title="Lane Fan Settings: do the task", carries=(TITLE_FORM,), **TITLE_START)

# ---- Allowed. A title that opens with the form passes, the record's own example included. These pass on the old code.
add("lane-title-slug: a lane start titled with its own branch slug is allowed", "allow",
    title="Lane lane-title-slug: make the guard refuse a free lane title", **TITLE_START)
add("lane-title-slug: a lane start titled with a slug and a list after the colon is allowed", "allow",
    title="Lane small-screen-fixes: 519, 520", **TITLE_START)
add("lane-title-slug: a lane start with a one-word slug is allowed", "allow",
    title="Lane fanfix: do the task", **TITLE_START)
add("lane-title-slug: a lane start with digits in its slug is allowed", "allow",
    title="Lane retro2-fixes: do the task", **TITLE_START)
add("lane-title-slug: a lane start with a 32-character slug at full size is allowed", "allow",
    title="Lane " + FULL_SLUG + ": do the task", **TITLE_START)

# ---- Scope. A call that tags no lane is not judged, whatever its title.
add("lane-title-slug: a create_session tagged as a triage start with a free title is allowed", "allow",
    tool=LANE_TOOL, tags=["cs-build:triage"], title="Thermostat fan settings (Resideo)", prompt="do the task")
add("lane-title-slug: a create_session with no tags and a free title is allowed", "allow",
    tool=LANE_TOOL, title="Thermostat fan settings (Resideo)", prompt="do the task")
