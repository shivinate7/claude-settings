# section 42910
FAMILY = "lane-step-dup-pr"
#
# Rule lane-step-dup, part two: an open lane pull request holds the step. A create_session whose tags hold cs-step:<slug>,
# or a send_message whose brief names <slug>, is refused when an open pull request in the cs-repo has the slug as its head
# (the `lane/<slug>` head form counts too). The refusal names that pull request's number. A brief that says `continues #N`
# or `replaces #N` passes when #N is an open pull request of the step. A number that is no open pull request of the step
# does not pass, even where the phrase stands in a line of its own. A closed or merged pull request holds nothing, and
# neither does a pull request on another slug.
# A pull request read that cannot run is refused. Part one (live sessions) is in the lane-step-dup section, so the two can
# be held apart.
STEPPR_RULE = "lane-step-dup"
STEPPR_SLUG = ARCHIVE_SLUG  # the step slug the shared open-pull-request fixtures name: their open pull request has this head
STEPPR_PR = "#13"           # the number of the open pull request those fixtures hold
STEPPR_CONTINUES = LANE_PROMPT + " It continues #13."
STEPPR_REPLACES = LANE_PROMPT + " It replaces #13."
STEPPR_BRIEF = "Lane brief: lane-closes-after-records. Topic: dup-topic.\n\nDo the step."
STEPPR_BRIEF_CONTINUES = STEPPR_BRIEF + "\n\nThis continues #13."
STEPPR_TAGS = ["cs-build:lane", "cs-step:" + STEPPR_SLUG, "cs-repo:o/r"]
# A fixture whose open pull request #5 holds the step, and whose open pull request #9 is on another step. The
# continues and replaces cases name #5, or a number that is no open pull request of the step (#1, #2, #9).
ARCHOPEN_FIVE = os.path.join(ROOT, "archopen-five")


def build_archopen_five():
    """The step's open pull request #5, and #9 open on another slug: each a row of the open list."""
    make_fake_gh(ARCHOPEN_FIVE, "main", need=["o/r"], others=[
        {"number": 5, "head": "5" * 40, "ref": STEPPR_SLUG},
        {"number": 9, "head": "9" * 40, "ref": "dup-step-c"}])


lazy_fixture([ARCHOPEN_FIVE], build_archopen_five)


def steppr_create(name, expected, env_path, prompt=LANE_PROMPT, tags=STEPPR_TAGS, carries=()):
    """A create_session the pull request rule judges, over a whole read with no live session on the step. The call is a
    lane start that passes the lane rules, so only this rule decides it. An allow must print nothing."""
    add("lane-step-dup: " + name, expected, rule=None if expected == "allow" else STEPPR_RULE, tool=CREATE_SESSION,
        cwd=NOGIT, transcript=role_path("stepdup-create-empty"), env=ROLE_ENV, silent=expected == "allow",
        carries=carries, env_path=env_path, title="a lane session", tags=list(tags), prompt=prompt,
        effort=LANE_EFFORT_FIELD, model="sonnet", source_url=LANE_SOURCE_URL)


def steppr_send(name, expected, env_path, message, carries=()):
    """A send_message the pull request rule judges. The target is a lane on the brief's topic, and the transcript holds
    its record, so lane-one-topic passes the brief and only this rule decides it. An allow must print nothing."""
    add("lane-step-dup: " + name, expected, rule=None if expected == "allow" else STEPPR_RULE, tool=SEND_MESSAGE,
        cwd=NOGIT, transcript=role_path("stepdup-send-empty"), env=ROLE_ENV, silent=expected == "allow",
        carries=carries, env_path=env_path, session_id=STEPDUP_NEW, message=message)


# Refused: an open lane pull request on the step's slug. The refusal names the pull request.
steppr_create("a create_session tagged cs-step:lane-closes-after-records is refused while an open lane pull request holds the step, and names it",
              "deny", fake_gh_path(ARCHOPEN), carries=STEPPR_PR)
steppr_send("a brief for lane-closes-after-records is refused while an open lane pull request holds the step, and names it",
            "deny", fake_gh_path(ARCHOPEN), STEPPR_BRIEF, carries=STEPPR_PR)
# Refused: the open pull request's head is the lane/<slug> form, which holds the step too.
steppr_create("a create_session tagged cs-step:lane-closes-after-records is refused for an open pull request whose head is lane/lane-closes-after-records, and names it",
              "deny", fake_gh_path(ARCHOPEN_LANE), carries=STEPPR_PR)
# Refused: a brief that says continues the work, with no pull request number, does not pass the exemption.
steppr_create("a create_session whose brief says continues with no number is still refused while an open pull request holds the step",
              "deny", fake_gh_path(ARCHOPEN), prompt=LANE_PROMPT + " It continues the work.", carries=STEPPR_PR)
# Allowed: a brief that says it continues the open pull request passes it.
steppr_create("a create_session whose brief says continues #13 is allowed while the open pull request #13 holds the slug",
              "allow", fake_gh_path(ARCHOPEN), prompt=STEPPR_CONTINUES)
# Allowed: a brief that says it replaces the open pull request passes it.
steppr_create("a create_session whose brief says replaces #13 is allowed while the open pull request #13 holds the slug",
              "allow", fake_gh_path(ARCHOPEN), prompt=STEPPR_REPLACES)
# Allowed: the continues line in a brief sent to a lane passes the same exemption.
steppr_send("a brief whose body says continues #13 is allowed while the open pull request #13 holds the slug",
            "allow", fake_gh_path(ARCHOPEN), STEPPR_BRIEF_CONTINUES)

# Allowed: a closed pull request on the slug holds nothing.
steppr_create("a create_session tagged cs-step:lane-closes-after-records is allowed when the slug's pull request is closed",
              "allow", fake_gh_path(ARCHCLOSED))
# Allowed: a merged pull request on the slug holds nothing.
steppr_create("a create_session tagged cs-step:lane-closes-after-records is allowed when the slug's pull request is merged",
              "allow", fake_gh_path(ARCHMERGED))
# Allowed: an open pull request on another slug does not hold this step.
steppr_create("a create_session tagged cs-step:dup-step-c is allowed while an open pull request holds another slug",
              "allow", fake_gh_path(ARCHOPEN), tags=["cs-build:lane", "cs-step:dup-step-c", "cs-repo:o/r"])

# Refused: a pull request read that cannot run is refused, not allowed through.
steppr_create("a create_session tagged cs-step:lane-closes-after-records is refused when the pull request read cannot run",
              "deny", fake_gh_path(GHBROKEN))
steppr_send("a brief for lane-closes-after-records is refused when the pull request read cannot run",
            "deny", fake_gh_path(GHBROKEN), STEPPR_BRIEF)

# Refused: "a CI job continues #1 of 3" holds the phrase, but #1 is no open pull request of the step. The refusal names #5.
steppr_create("a create_session whose brief says a CI job continues #1 of 3 is refused while open pull request #5 holds the step, and names #5",
              "deny", ARCHOPEN_FIVE, prompt=LANE_PROMPT + " A CI job continues #1 of 3.", carries="#5")
# Refused: an unrelated line says the old doc replaces #2. #2 is no open pull request of the step, so #5 still holds it.
steppr_send("a brief for lane-closes-after-records with an unrelated line that replaces #2 is refused while open pull request #5 holds the step, and names #5",
            "deny", ARCHOPEN_FIVE, STEPPR_BRIEF + "\nThe old doc replaces #2 in the index.", carries="#5")
# Refused: continues #9 names an open pull request, but #9 is open on another step, not on this one.
steppr_create("a create_session whose brief says continues #9 is refused while open pull request #5 holds the step, though #9 is open on another step",
              "deny", ARCHOPEN_FIVE, prompt=LANE_PROMPT + " It continues #9.", carries="#5")
# Allowed: continues #5 and replaces #5 name the open pull request of the step.
steppr_create("a create_session whose brief says continues #5 is allowed while open pull request #5 holds the step",
              "allow", ARCHOPEN_FIVE, prompt=LANE_PROMPT + " It continues #5.")
steppr_create("a create_session whose brief says replaces #5 is allowed while open pull request #5 holds the step",
              "allow", ARCHOPEN_FIVE, prompt=LANE_PROMPT + " It replaces #5.")
