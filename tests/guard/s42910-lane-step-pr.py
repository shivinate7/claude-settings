# section 42910
FAMILY = "lane-step-dup-pr"
#
# Rule lane-step-dup, part two: an open lane pull request holds the step. A create_session whose tags hold cs-step:<slug>,
# or a send_message whose brief names <slug>, is refused when an open pull request in the cs-repo has the slug as its head
# (the `lane/<slug>` head form counts too). The refusal names that pull request's number. A brief that says `continues #N`
# or `replaces #N` passes. A closed or merged pull request holds nothing, and neither does a pull request on another slug.
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
