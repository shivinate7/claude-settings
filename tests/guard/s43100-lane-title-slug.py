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
# The printed form and the opening are two constants in shared_names.py: LANE_TITLE_FORM, which the refusal prints, and
# LANE_TITLE_OPENING, which the guard reads. Both are read from the copy under test (GUARD's folder), so a mutant of either
# is judged here. A tree with no LANE_TITLE_FORM falls back to the form the rule names, so the section still loads there.
import importlib.util as _title_ilu
_title_spec = _title_ilu.spec_from_file_location(
    "shared_names_under_test", os.path.join(os.path.dirname(GUARD), "shared_names.py"))
_title_names = _title_ilu.module_from_spec(_title_spec)
_title_spec.loader.exec_module(_title_names)
LANE_TITLE_PRINTED = getattr(_title_names, "LANE_TITLE_FORM", "Lane <branch slug>:")
LANE_TITLE_SAMPLE = LANE_TITLE_PRINTED.replace("<branch slug>", "fan-settings") + " do the task"

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
add("lane-title-slug: a title with Lane, a space and no slug is denied", "deny", TITLE_RULE,
    title="Lane : do the task", carries=(TITLE_FORM,), **TITLE_START)
add("lane-title-slug: a title with no colon after the slug is denied", "deny", TITLE_RULE,
    title="Lane lane-title-slug do the task", carries=(TITLE_FORM,), **TITLE_START)
add("lane-title-slug: a title that names the slug after its words is denied", "deny", TITLE_RULE,
    title="Do the task, Lane lane-title-slug: fix it", carries=(TITLE_FORM,), **TITLE_START)
add("lane-title-slug: a title with a session number as its slug is denied", "deny", TITLE_RULE,
    title="Lane N20: do the task", carries=(TITLE_FORM,), **TITLE_START)
add("lane-title-slug: a title with a title-cased name, not a branch slug, is denied", "deny", TITLE_RULE,
    title="Lane Fan Settings: do the task", carries=(TITLE_FORM,), **TITLE_START)

# The refusal prints the form the guard reads, verbatim: the constant it is built from, not a copy of it.
add("lane-title-slug: the refusal carries the printed form verbatim", "deny", TITLE_RULE,
    title="Thermostat fan settings (Resideo)", carries=(LANE_TITLE_PRINTED,), **TITLE_START)

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
# A title may open after leading blanks: the guard strips it before the opening is read. A control, green on the old code.
add("lane-title-slug: a lane start whose title opens after leading blanks is allowed", "allow",
    title="  Lane fanfix: do the task", **TITLE_START)
# The printed form, with a sample slug for <branch slug>, is a title the guard allows: what the refusal tells the owner to write opens right.
add("lane-title-slug: the printed form, with a sample slug, opens a title the guard allows", "allow",
    title=LANE_TITLE_SAMPLE, **TITLE_START)

# ---- Scope. A call that tags no lane is not judged, whatever its title.
add("lane-title-slug: a create_session tagged as a triage start with a free title is allowed", "allow",
    tool=LANE_TOOL, tags=["cs-build:triage"], title="Thermostat fan settings (Resideo)", prompt="do the task")
add("lane-title-slug: a create_session with no tags and a free title is allowed", "allow",
    tool=LANE_TOOL, title="Thermostat fan settings (Resideo)", prompt="do the task")
