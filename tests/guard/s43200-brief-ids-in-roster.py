# section 43200
FAMILY = "brief-ids-in-roster"  # the family of the roster check on lane briefs and lane starts

# ---- Brief ids in roster. A lane brief or a lane start that names a session id outside the roster is refused, so a
# hand-typed wrong id cannot wake a dead session. The roster is the `## Standing sessions` list in CLAUDE.md, read from
# refs/remotes/origin/roadmap of the payload's repo. The check reads a create_session that tags a lane (its prompt,
# whatever its opener), and a send_message with a line that starts with `Grant:` or `Lane brief:` after an optional
# markdown lead, wherever that line sits. Every case runs the real guard as a child, so each deny fails on old code as
# an assert ("expected deny, got allow") and never as an import error, which P3 does not allow for a new feature. Each
# allow case is a green control on old code.
#
# The escape: an id with a backtick or a double quote right before it and right after it is data (an incident quote)
# and passes. A quote elsewhere on the line hides nothing: a lone quote, a lone backtick or an apostrophe leaves a bare
# id judged, and so does a closed span with the id outside it (building-scanner-respects-strings). An id is matched in
# any case, and it ends before a dot, a dash or a `.md` after it.
#
# Known holes, named here as fail-open cases below: a repo with no roadmap ref, a roster with no Standing sessions section,
# an empty roster (the header with only template placeholders), and an unreadable ref each let every id through. The
# send_message target (session_id) is not judged: lanes are not on the roster, so a roster check on it would refuse every
# lane brief.
ROSTER_RULE = "brief-ids-in-roster"
# The refusal's remedy names this fetch, and no id as a thing to use. The reason names the roster, not the file: CLAUDE.md
# is a forbidden fragment for every rule but its own.
ROSTER_REMEDY = "git fetch origin +refs/heads/roadmap:refs/remotes/origin/roadmap"
ROSTER_SEND = "mcp__claude-code-remote__send_message"
ROSTER_TITLE = "Lane brief-ids-from-roster: check the ids a brief names"
ROSTER_GRANT = "Grant: owner 20:41 CST Nov 13, the roster check"
ROSTER_TASK = "Task: step brief-ids-from-roster "
GRANT_TASK = ROSTER_GRANT + "\n" + ROSTER_TASK

# An id is `session_`, a digit, then letters and digits. The runner id and the wrong id are the incident's: runner 10's
# right id, and the id the coordinator's brief named for it.
ROSTER_COORD = "session_01RosCoordAa0001Zz"
ROSTER_TRIAGE = "session_01RosTriageBb0002Yy"
ROSTER_RUNNER = "session_013NEJL2f1YCYsvLdpFqtWP3"
ROSTER_WRONG = "session_013NEJL2gw6EdrSyvHkTUEx6"
ROSTER_NEAR = "session_013NEJL2f1YCYsvLdpFqtWP4"  # runner 10's id with its last character changed
ROSTER_LANE = "session_01LaneOutsideRoster9"  # a lane's id, in the lane notes section after the roster
ROSTER_BATCH = "session_01RosBatchRepoCc0003Xx"  # a batch runner per repo scope
ROSTER_ARBITER = "session_01RosArbiterDd0004Ww"
ROSTER_WRONG_UPPER = "SESSION_" + ROSTER_WRONG[len("session_"):]  # the wrong id with its prefix in capitals
ROSTER_RUNNER_UPPER = "SESSION_" + ROSTER_RUNNER[len("session_"):]  # the runner's roster id, typed in capitals

ROSTER_REPO = os.path.join(ROOT, "roster-repo")  # the roster the coordinator keeps: three rows
ROSTER_FULL = os.path.join(ROOT, "roster-full")  # full size: every row the template names
ROSTER_EMPTY = os.path.join(ROOT, "roster-empty")  # the section is there, with only the template's placeholders
ROSTER_NOSECTION = os.path.join(ROOT, "roster-nosection")  # CLAUDE.md with no Standing sessions section
ROSTER_UNREADABLE = os.path.join(ROOT, "roster-unreadable")  # a roadmap ref whose CLAUDE.md cannot be read
ROSTER_DATED = os.path.join(ROOT, "roster-dated")  # the heading carries a date after its name
ROSTER_SUBHEAD = os.path.join(ROOT, "roster-subhead")  # a ### line sits between the section's intro and its rows

ROSTER_ROW_COORD = ('- Coordinator (starts every other session, holds lane state, talks with the owner): '
                    '"coordinator", %s, since 2026-11-10 14:29 CST. It compacts in place and has no successor.' % ROSTER_COORD)
ROSTER_ROW_TRIAGE = '- Triage (the repo\'s one page): "triage", %s, since 2026-11-10 14:30 CST.' % ROSTER_TRIAGE
ROSTER_ROW_RUNNER = ('- Batch runner (integration batch, CI waits, merge tool runs under the coordinator\'s grant): '
                     '"batch runner 10", %s, since 2026-11-12 09:05 CST.' % ROSTER_RUNNER)
ROSTER_ROW_BATCH = ('- Batch runner per repo scope (claude-settings): "batch runner, claude-settings", %s, '
                    'since 2026-11-12 09:10 CST.' % ROSTER_BATCH)
ROSTER_ROW_ARBITER = '- Arbiter: "arbiter", %s, since 2026-11-12 09:15 CST.' % ROSTER_ARBITER
ROSTER_ROW_PLACEHOLDER = ('- Coordinator (starts every other session, holds lane state, talks with the owner): '
                          '"<session title>", <session id>, since <date and time>.')


def roster_claude_md(rows, heading="## Standing sessions", before_rows=""):
    """CLAUDE.md with a Standing sessions section holding `rows`, then a lane notes section after it. `heading` is the
    section's heading line, and `before_rows` is any text between the section's intro and its rows. The lane's id sits
    in the lane notes section, so a case that names it proves the roster reader stops at the section's end."""
    return ("# Claude settings fixture\n\nThe rules of this repo live beside this file.\n\n"
            + heading + "\n\nThis roster is the one record of who holds each standing session.\n\n" + before_rows
            + "\n".join(rows) + "\n\nLanes are not on the roster. The coordinator holds lane state.\n\n"
            "## Lane notes\n\nThe lane for step brief-ids-from-roster is " + ROSTER_LANE + ". It is not on the roster.\n")


ROSTER_NOSECTION_TEXT = ("# Notes\n\nNo roster is kept in this repo yet. The lane for step brief-ids-from-roster is "
                         + ROSTER_LANE + ".\n")


def roster_repo(where, text, ref=True):
    """A checkout holding CLAUDE.md as `text`, with the claude-settings origin the lane tag rule reads. With `ref`, the
    roadmap ref points at that commit, as a fetched record branch does."""
    make_repo(where, {"CLAUDE.md": text})
    origin = run_vcs(where, "remote", "add", "origin", LANE_ORIGINS[LANE_REPO])
    if origin.returncode != 0:
        sys.exit("fixture setup failed in build_rosters: remote add origin failed in %r. stderr: %s"
                 % (where, origin.stderr.strip()))
    if ref:
        update = run_vcs(where, "update-ref", "refs/remotes/origin/roadmap", "HEAD")
        if update.returncode != 0:
            sys.exit("fixture setup failed in build_rosters: update-ref failed in %r. stderr: %s"
                     % (where, update.stderr.strip()))


def roster_reads(where):
    """The CLAUDE.md the fixture's roadmap ref holds, or None when git cannot read it: what the guard reads."""
    shown = run_vcs(where, "show", "refs/remotes/origin/roadmap:CLAUDE.md")
    return shown.stdout if shown.returncode == 0 else None


def build_rosters():
    roster_repo(ROSTER_REPO, roster_claude_md([ROSTER_ROW_COORD, ROSTER_ROW_TRIAGE, ROSTER_ROW_RUNNER]))
    roster_repo(ROSTER_FULL, roster_claude_md([ROSTER_ROW_COORD, ROSTER_ROW_TRIAGE, ROSTER_ROW_RUNNER,
                                               ROSTER_ROW_BATCH, ROSTER_ROW_ARBITER]))
    roster_repo(ROSTER_EMPTY, roster_claude_md([ROSTER_ROW_PLACEHOLDER]))
    roster_repo(ROSTER_NOSECTION, ROSTER_NOSECTION_TEXT)
    roster_repo(ROSTER_UNREADABLE, roster_claude_md([ROSTER_ROW_COORD, ROSTER_ROW_TRIAGE, ROSTER_ROW_RUNNER]))
    roster_repo(ROSTER_DATED, roster_claude_md([ROSTER_ROW_COORD, ROSTER_ROW_TRIAGE, ROSTER_ROW_RUNNER],
                                               heading="## Standing sessions (2026-11-13)"))
    roster_repo(ROSTER_SUBHEAD, roster_claude_md([ROSTER_ROW_COORD, ROSTER_ROW_TRIAGE, ROSTER_ROW_RUNNER],
                                                 before_rows="### Batch 10\n\n"))
    # Break the one blob of the unreadable ref: a loose ref to an object git does not hold. The ref then resolves to
    # nothing readable, so the guard reads no roster, and the check below holds that it really is unreadable.
    write(os.path.join(ROSTER_UNREADABLE, ".git", "refs", "remotes", "origin", "roadmap"), "1" * 40 + "\n")
    # Each fixture must hold what its cases claim. A roster that failed to build would let every allow pass for nothing.
    for where, (needle, present) in (
            (ROSTER_REPO, (ROSTER_RUNNER, True)),
            (ROSTER_FULL, (ROSTER_ARBITER, True)),
            (ROSTER_EMPTY, ("<session title>", True)),
            (ROSTER_DATED, (ROSTER_RUNNER, True)),
            (ROSTER_DATED, ("## Standing sessions (2026-11-13)", True)),
            (ROSTER_SUBHEAD, (ROSTER_RUNNER, True)),
            (ROSTER_SUBHEAD, ("### Batch 10", True)),
            (ROSTER_NOSECTION, ("## Standing sessions", False))):
        text = roster_reads(where)
        if text is None or (needle in text) != present:
            sys.exit("fixture setup failed in build_rosters: %r does not hold its roster as its cases claim" % where)
    if roster_reads(ROSTER_UNREADABLE) is not None:
        sys.exit("fixture setup failed in build_rosters: %r is readable, so it is no unreadable-ref case" % ROSTER_UNREADABLE)


lazy_fixture([ROSTER_REPO, ROSTER_FULL, ROSTER_EMPTY, ROSTER_NOSECTION, ROSTER_UNREADABLE, ROSTER_DATED, ROSTER_SUBHEAD],
             build_rosters)


def roster_incident(quote=""):
    """The incident sentence. Each id sits inside `quote` (empty for bare, a backtick or a double quote for data)."""
    return ("(a hand-typed wrong id (%s%s%s; the right runner 10 id is %s%s%s) is refused)"
            % (quote, ROSTER_WRONG, quote, quote, ROSTER_RUNNER, quote))


def roster_send(name, expected, message, cwd=ROSTER_REPO, target=ROSTER_RUNNER, bad=None, **kw):
    """A send_message the guard judges. A deny names its rule, carries the fetch remedy and never the bad id."""
    if expected == "deny":
        add(name, "deny", rule=ROSTER_RULE, tool=ROSTER_SEND, cwd=cwd, session_id=target, message=message,
            carries=(ROSTER_REMEDY,), lacks=(bad,), **kw)
    else:
        add(name, "allow", tool=ROSTER_SEND, cwd=cwd, session_id=target, message=message, silent=True, **kw)


def roster_start(name, expected, prompt, cwd=ROSTER_REPO, bad=None):
    """A create_session that tags a lane. Built from the lane start template (section 43100's TITLE_START), so only the
    roster check can refuse it: the lane rules around it pass."""
    fields = dict(TITLE_START, cwd=cwd, prompt=prompt, title=ROSTER_TITLE)
    if expected == "deny":
        add(name, "deny", rule=ROSTER_RULE, carries=(ROSTER_REMEDY,), lacks=(bad,), **fields)
    else:
        add(name, "allow", **fields)


# ---- Refused. A bare id the roster does not hold is refused, behind a Grant opener.
roster_send("brief-ids-in-roster: a Grant and Task message that names runner 10 by a wrong id is refused", "deny",
            GRANT_TASK + "Runner 10 is " + ROSTER_WRONG + ".", bad=ROSTER_WRONG)
# A Lane brief opener reads the same ids. The target's transcript is a lane on its own topic, so lane-one-topic passes
# the brief and the roster check is what refuses it.
roster_send("brief-ids-in-roster: a Lane brief to a lane on its own topic that names a wrong runner id is refused", "deny",
            "Lane brief: icon-a. Topic: icons.\nRunner 10 is " + ROSTER_WRONG + ".", bad=ROSTER_WRONG,
            target=ROLE_OTHER, transcript=role_path("step-topic-lane"), env=ROLE_ENV)
roster_send("brief-ids-in-roster: an id one character off a roster id is refused", "deny",
            GRANT_TASK + "Runner 10 is " + ROSTER_NEAR + ".", bad=ROSTER_NEAR)
roster_send("brief-ids-in-roster: a roster id with one character added is refused", "deny",
            GRANT_TASK + "Runner 10 is " + ROSTER_RUNNER + "X.", bad=ROSTER_RUNNER + "X")
# A roster id beside a wrong one does not clear the wrong one: every bare id is judged.
roster_send("brief-ids-in-roster: a roster id beside a wrong id does not clear the wrong id", "deny",
            GRANT_TASK + "Runner 10 is " + ROSTER_RUNNER + "; the old runner 10 was " + ROSTER_WRONG + ".",
            bad=ROSTER_WRONG)
# Quote escapes do not hide a bare id: a lone double quote, a lone backtick and an apostrophe open no quoted span.
roster_send("brief-ids-in-roster: a lone double quote before a wrong id does not hide it", "deny",
            GRANT_TASK + 'A quote " opens here, then runner 10 is ' + ROSTER_WRONG + ".", bad=ROSTER_WRONG)
roster_send("brief-ids-in-roster: a lone backtick before a wrong id does not hide it", "deny",
            GRANT_TASK + "A tick ` opens here, then runner 10 is " + ROSTER_WRONG + ".", bad=ROSTER_WRONG)
roster_send("brief-ids-in-roster: an apostrophe in Don't does not hide a wrong id after it", "deny",
            GRANT_TASK + "Don't send runner 10 " + ROSTER_WRONG + ".", bad=ROSTER_WRONG)
# An id that appears only in another section of CLAUDE.md is not on the roster: the reader stops at the section's end.
roster_send("brief-ids-in-roster: an id that appears only after the roster section is refused", "deny",
            GRANT_TASK + "Lane " + ROSTER_LANE + " holds the step.", bad=ROSTER_LANE)
# Full size: every row the template names is on the roster, and a wrong id beside them is still refused.
roster_send("brief-ids-in-roster: a full roster, with a wrong id beside its five rows, is refused", "deny",
            GRANT_TASK + " ".join([ROSTER_COORD, ROSTER_TRIAGE, ROSTER_RUNNER, ROSTER_BATCH, ROSTER_ARBITER])
            + " and " + ROSTER_WRONG + ".", cwd=ROSTER_FULL, bad=ROSTER_WRONG)
# A lane start: the exact text of the incident's start prompt, with the wrong id bare, is refused.
roster_start("brief-ids-in-roster: a lane start with the incident's start text and a bare wrong id is refused", "deny",
             ROSTER_GRANT + "\n" + ROSTER_TASK + roster_incident(), bad=ROSTER_WRONG)
# A lane start is read whether or not its first line is a Grant line: the prompt is judged, and these are the wiring check.
roster_start("brief-ids-in-roster: a lane start, Grant then a wrong runner id, is refused", "deny",
             ROSTER_GRANT + "\nTask: runner 10 is " + ROSTER_WRONG + ".", bad=ROSTER_WRONG)
roster_start("brief-ids-in-roster: a lane start with no Grant line that names a wrong id is refused", "deny",
             "Task: runner 10 is " + ROSTER_WRONG + ".", bad=ROSTER_WRONG)

# ---- Allowed. A roster id passes, and so does an id in backticks or double quotes, which is data.
roster_send("brief-ids-in-roster: a Grant and Task message naming runner 10 by its roster id is allowed", "allow",
            GRANT_TASK + "Runner 10 is " + ROSTER_RUNNER + ".")
# A roster id followed by a closing bracket, a semicolon or a period is one id: the trailing punctuation is not part of it.
roster_send("brief-ids-in-roster: a roster id before a bracket, a semicolon or a period is allowed", "allow",
            GRANT_TASK + "Runner 10 (" + ROSTER_RUNNER + "); the roster lists " + ROSTER_RUNNER + ".")
roster_send("brief-ids-in-roster: the incident sentence with its ids in backticks is allowed", "allow",
            GRANT_TASK + roster_incident("`"))
roster_send("brief-ids-in-roster: the incident sentence with its ids in double quotes is allowed", "allow",
            GRANT_TASK + roster_incident('"'))
roster_send("brief-ids-in-roster: a Grant and Task message with no session id is allowed", "allow",
            GRANT_TASK + "Do the roster check. No ids here.")
# A message with no lane opener is not read, so a wrong id in it passes.
roster_send("brief-ids-in-roster: a message with no lane opener, naming a wrong id, is allowed: it is not read", "allow",
            "Status: PR 12 merged. Runner 10 is " + ROSTER_WRONG + ".")
roster_send("brief-ids-in-roster: a Lane brief to a lane on its own topic that names a roster id is allowed", "allow",
            "Lane brief: icon-a. Topic: icons.\nRunner 10 is " + ROSTER_RUNNER + ".",
            target=ROLE_OTHER, transcript=role_path("step-topic-lane"), env=ROLE_ENV)
roster_send("brief-ids-in-roster: the full roster's five ids are all allowed", "allow",
            GRANT_TASK + " ".join([ROSTER_COORD, ROSTER_TRIAGE, ROSTER_RUNNER, ROSTER_BATCH, ROSTER_ARBITER]) + ".",
            cwd=ROSTER_FULL)
roster_start("brief-ids-in-roster: a lane start naming runner 10 by its roster id is allowed", "allow",
             ROSTER_GRANT + "\n" + ROSTER_TASK + "Runner 10 is " + ROSTER_RUNNER + ".")
roster_start("brief-ids-in-roster: a lane start with the incident's start text in backticks is allowed", "allow",
             ROSTER_GRANT + "\n" + ROSTER_TASK + roster_incident("`"))

# ---- Read wider. A Grant or Lane brief line is read wherever it sits, after a markdown lead. A quote hides an id only when
# it sits right before and right after it. An id matches in any case and ends before a dot, a dash or `.md`. The roster
# section is the heading that starts `## Standing sessions`, with any suffix, up to the next `## ` heading.
roster_send("brief-ids-in-roster: a bold Grant line, with a wrong id on a later line, is refused", "deny",
            "**Grant:** owner said go, 2026-11-13 10:00 CST.\nWake " + ROSTER_WRONG, bad=ROSTER_WRONG)
roster_send("brief-ids-in-roster: a quoted Grant line, with a wrong id on a later line, is refused", "deny",
            "> Grant: owner said go, 2026-11-13 10:00 CST.\nWake " + ROSTER_WRONG, bad=ROSTER_WRONG)
roster_send("brief-ids-in-roster: a Grant line under a heading, then a Lane brief line, with a wrong id, is refused", "deny",
            "## Batch 11 brief\n" + ROSTER_GRANT + "\nLane brief: step-a. Topic: x.\nWake " + ROSTER_WRONG, bad=ROSTER_WRONG)
roster_send("brief-ids-in-roster: a wrong id after a stray double quote, beside a quoted word, is refused", "deny",
            GRANT_TASK + 'The 5" monitor; wake ' + ROSTER_WRONG + ' and tell "them" to go.', bad=ROSTER_WRONG)
roster_send("brief-ids-in-roster: a wrong id after a lone backtick, before a backticked word, is refused", "deny",
            GRANT_TASK + "Stray ` before wake " + ROSTER_WRONG + ", then `done`.", bad=ROSTER_WRONG)
roster_send("brief-ids-in-roster: an uppercase wrong id is refused", "deny",
            GRANT_TASK + "Runner 10 is " + ROSTER_WRONG_UPPER + ".", bad=ROSTER_WRONG_UPPER)
# The refusal's reason names no escape: backticks and double quotes are not named as passing. A bare wrong id is judged.
add("brief-ids-in-roster: the refusal does not name the quote escape, backticks or double quotes", "deny", rule=ROSTER_RULE,
    tool=ROSTER_SEND, cwd=ROSTER_REPO, session_id=ROSTER_RUNNER, message=GRANT_TASK + "Runner 10 is " + ROSTER_WRONG + ".",
    carries=(ROSTER_REMEDY,), lacks=(ROSTER_WRONG, "backticks", "double quotes"))
roster_start("brief-ids-in-roster: a lane start with a stray double quote before a wrong id is refused", "deny",
             ROSTER_GRANT + "\n" + ROSTER_TASK + 'The 5" monitor; wake ' + ROSTER_WRONG + ' and tell "them" to go.',
             bad=ROSTER_WRONG)
roster_start("brief-ids-in-roster: a lane start with an uppercase wrong id is refused", "deny",
             ROSTER_GRANT + "\n" + ROSTER_TASK + "Runner 10 is " + ROSTER_WRONG_UPPER + ".", bad=ROSTER_WRONG_UPPER)
# Each fixture's roster holds its id, so a wrong id refused on it is refused for not being on it. The control comes first.
roster_send("brief-ids-in-roster: a roster id under a date on the heading is allowed", "allow",
            GRANT_TASK + "Runner 10 is " + ROSTER_RUNNER + ".", cwd=ROSTER_DATED)
roster_send("brief-ids-in-roster: a wrong id with a date on the roster heading is refused", "deny",
            GRANT_TASK + "Runner 10 is " + ROSTER_WRONG + ".", cwd=ROSTER_DATED, bad=ROSTER_WRONG)
roster_send("brief-ids-in-roster: a roster id under a ### line in the roster section is allowed", "allow",
            GRANT_TASK + "Runner 10 is " + ROSTER_RUNNER + ".", cwd=ROSTER_SUBHEAD)
roster_send("brief-ids-in-roster: a wrong id under a ### line in the roster section is refused", "deny",
            GRANT_TASK + "Runner 10 is " + ROSTER_WRONG + ".", cwd=ROSTER_SUBHEAD, bad=ROSTER_WRONG)
# Allowed. An id followed by `.md`, a dash or a period is the id, and a quote on both sides of it is data.
roster_send("brief-ids-in-roster: a roster id in a handoff path, before .md, is allowed", "allow",
            GRANT_TASK + "Read the handoff at ~/.claude/handoffs/" + ROSTER_RUNNER + ".md")
roster_send("brief-ids-in-roster: a roster id before a dash is allowed", "allow",
            GRANT_TASK + ROSTER_RUNNER + "- wake now.")
roster_send("brief-ids-in-roster: a roster id at the end of a sentence is allowed", "allow",
            GRANT_TASK + "Runner 10 is " + ROSTER_RUNNER + ".")
roster_send("brief-ids-in-roster: a wrong id alone in backticks, and one alone in double quotes, is allowed", "allow",
            GRANT_TASK + "Wrong: `" + ROSTER_WRONG + "`, and \"" + ROSTER_WRONG + "\".")
roster_send("brief-ids-in-roster: an uppercase roster id is the same id and is allowed", "allow",
            GRANT_TASK + "Runner 10 is " + ROSTER_RUNNER_UPPER + ".")
roster_start("brief-ids-in-roster: a lane start naming runner 10 in a handoff path, before .md, is allowed", "allow",
             ROSTER_GRANT + "\n" + ROSTER_TASK + "Read the handoff at ~/.claude/handoffs/" + ROSTER_RUNNER + ".md")

# ---- Fail open, the known holes named above. Each allow below lets a wrong id through, on purpose: the check has no
# roster to read. A repo with a roster and the holes both must still refuse, which the cases above pin.
# Known hole: a repo with no roadmap ref. LANE_REPO is a checkout with no roadmap ref (section 29666).
roster_send("brief-ids-in-roster: a repo with no roadmap ref fails open: a wrong id passes (known hole)", "allow",
            GRANT_TASK + "Runner 10 is " + ROSTER_WRONG + ".", cwd=LANE_REPO)
# Known hole: a roster with no Standing sessions section.
roster_send("brief-ids-in-roster: a roster with no Standing sessions section fails open (known hole)", "allow",
            GRANT_TASK + "Runner 10 is " + ROSTER_WRONG + ".", cwd=ROSTER_NOSECTION)
# Known hole: an empty roster, the section there with only template placeholders. The fetch remedy cannot fill it.
roster_send("brief-ids-in-roster: an empty roster, placeholders only, fails open (known hole)", "allow",
            GRANT_TASK + "Runner 10 is " + ROSTER_WRONG + ".", cwd=ROSTER_EMPTY)
# Known hole: an unreadable ref. The ref resolves to nothing readable, so no roster is read.
roster_send("brief-ids-in-roster: an unreadable roadmap ref fails open (known hole)", "allow",
            GRANT_TASK + "Runner 10 is " + ROSTER_WRONG + ".", cwd=ROSTER_UNREADABLE)
