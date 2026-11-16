# section 43500
# The lane start in one pass (branch lane-start-one-pass). Change 1: a lane start that breaks several lane-start rules is
# refused once, under the first broken rule's name, with a count line and one line per broken rule in judge order. An
# override lifts only the rule it is spent on, and the call then goes on to the next broken rule. A call that breaks one
# rule keeps its own refusal, with no count line. Change 4: the archive read refusals name the fix (attach the repo
# read-only with add_repo) and never name "Retry once gh answers" as their only remedy.
#
# Every case starts from section 43100's passing lane start (TITLE_START) and section 29666's title (LANE_TITLE), and
# changes only the fields it breaks. The override cases use section 36421's helpers, and the archive cases section
# 14736's archive_refuse and its fixtures. Every section shares one namespace, so the new names carry LSP_ or _lsp_.
_lsp_prior_family = FAMILY
FAMILY = "rule9"  # Change 1: the lane start rules, judged in one refusal

LSP_TOKEN = "lane-start-pass"  # every label carries it, so MUTATE_ONLY=lane-start-pass runs these cases alone
# The judge order of the seven rules a create_session that tags a lane can break (guard.judge: brief_hit, brief_roster_hit,
# floor_hit, lane_effort_hit, lane_repo_tag_hit, lane_start_settings_hit, lane_title_hit).
LSP_ORDER = ("lane-one-topic", "brief-ids-in-roster", "agent-model-floor", "lane-effort-pin", "lane-repo-tag",
             "lane-start-settings", "lane-title-slug")
# One fragment per rule, taken from that rule's own remedy. Each fragment is in that remedy alone, so a one-rule case
# can check that no other rule's remedy is printed.
LSP_REMEDY = {
    "lane-one-topic": "names a topic that the start's cs-topic tag does not hold",
    "brief-ids-in-roster": "this brief names a session id",
    "agent-model-floor": "Sonnet is the floor for a lane",
    "lane-effort-pin": "A lane starts with the effort field set to",
    "lane-repo-tag": "carries the full `cs-repo` tag",
    "lane-start-settings": "A lane's start names `model` and `source_url`",
    "lane-title-slug": "A lane's title opens with",
}
LSP_COUNT = "%d lane-start rules broken:"  # the count line the refusal opens with, when two or more rules are broken
LSP_COUNT_WORDS = "lane-start rules broken"  # a one-rule refusal carries none of these words
LSP_BAD_TITLE = "Thermostat fan settings (Resideo)"  # breaks lane-title-slug
LSP_TOPIC_LINE = "Lane brief: lane-start-pass. Topic: other-topic."  # with a cs-topic:one-topic tag, breaks lane-one-topic
LSP_BARE_ID_LINE = "Do the task, then report to session_4711."  # a bare session id in the brief, breaks brief-ids-in-roster
LSP_ADD_REPO = "add_repo"
LSP_READ_ONLY = ("read-only", "read only")  # any-of: the fix names the access in one of these spellings
LSP_RETRY = "Retry once gh answers"
LSP_ONE_TOPIC = "cs-topic:one-topic"


def _lsp_log(label, check):
    """Join one log check to LOG_CHECKS with its family. Section 40805 joins LOG_CHECKS_EXTRA before this section runs, so an
    append to LOG_CHECKS_EXTRA here would be dropped; the family is set on LOG_FAMILY, as sections 43400 and 43421 do."""
    global LOG_CHECKS
    LOG_FAMILY[label] = FAMILY
    LOG_CHECKS = LOG_CHECKS + ((label, check),)


def _lsp_fields(**changes):
    """The tool_input of a lane start: section 43100's passing start with its title, each named field replaced.
    None drops the field."""
    fields = dict((key, value) for key, value in TITLE_START.items() if key not in ("tool", "cwd"))
    fields["title"] = LANE_TITLE
    for name, value in changes.items():
        if value is None:
            fields.pop(name, None)
        else:
            fields[name] = value
    return fields


def _lsp_others(rule):
    """What a one-rule refusal of `rule` must not carry: each other rule's remedy, and the count line's words."""
    return tuple(LSP_REMEDY[other] for other in LSP_ORDER if other != rule) + (LSP_COUNT_WORDS,)


def _lsp_one(rule, name, **changes):
    """A lane start that breaks only `rule`: today's refusal, under its own name, with no count line."""
    add(LSP_TOKEN + ": " + name, "deny", rule, tool=LANE_TOOL, cwd=LANE_REPO,
        carries=(LSP_REMEDY[rule],), lacks=_lsp_others(rule), **_lsp_fields(**changes))


def _lsp_pair(first, second, name, **changes):
    """A lane start that breaks `first` and `second`, in judge order: one refusal under `first`, with the count of 2."""
    add(LSP_TOKEN + ": " + name, "deny", first, tool=LANE_TOOL, cwd=LANE_REPO,
        carries=(LSP_COUNT % 2, first + ":", second + ":", LSP_REMEDY[first], LSP_REMEDY[second]),
        **_lsp_fields(**changes))
    _lsp_log(LSP_TOKEN + ": " + name + " (order)", _lsp_order_check(CASES[-1], (first, second)))


def _lsp_order_check(case, rules):
    """The refusal of `case` opens under rules[0], then a count line, then one line per rule, in the order of `rules`."""
    def check():
        got, reason = decide(case)
        if got != "deny":
            return False, "got %s, want deny" % got
        if not reason.startswith(rules[0] + ": "):
            return False, "the refusal is not under %s: %s" % (rules[0], reason[:90])
        # The refusal opens with the count line: right after the rule's own prefix, before any rule line.
        opening = LSP_COUNT % len(rules)
        if not reason[len(rules[0]) + 2:].startswith(opening):
            return False, "the refusal does not open with %r after its rule: %s" % (opening, reason[:90])
        count = reason.find(opening)
        at = count
        for rule in rules:
            pos = reason.find(rule + ": ", at)
            if pos < 0:
                return False, "no line for %s after the count line: %s" % (rule, reason[:90])
            at = pos + 1
        return True, "%d rules named in judge order after the count line" % len(rules)
    return check


def _lsp_once_check():
    """Two liftable rules broken: the owner's one-act override lifts the first only, and the call goes on to the second.
    The override is spent by that lift, so the next call is refused under the first again."""
    config = ov_config("lane-start-once")
    session = "session_LSPONCE01"
    fields = _lsp_fields(effort="high", title=LSP_BAD_TITLE)

    def call(seconds):
        return ov_call(LANE_TOOL, dict(fields), LANE_REPO, config, session, seconds)

    got, reason = call(0)
    if got != "deny" or not reason.startswith("lane-effort-pin: "):
        return False, "with no override: got %s (%s), want a refusal under lane-effort-pin" % (got, reason[:90])
    note = ov_type(config, session, "override", 1)
    got, reason = call(2)
    if got != "deny":
        return False, "the one-act override let the whole call through: got %s (%s), want lane-title-slug refused" % (
            got, reason[:90])
    if not reason.startswith("lane-title-slug: ") or LSP_REMEDY["lane-title-slug"] not in reason:
        return False, "after the lift, the refusal is not lane-title-slug's: %s" % reason[:90]
    if LSP_REMEDY["lane-effort-pin"] in reason:
        return False, "the lifted rule lane-effort-pin is still printed: %s" % reason[:90]
    got, reason = call(3)
    if got != "deny" or not reason.startswith("lane-effort-pin: ") or (LSP_COUNT % 2) not in reason:
        return False, "the override is spent, want both refused again under lane-effort-pin with the count of 2: %s (%s)" % (
            got, reason[:90])
    return True, "lane-effort-pin lifted by one act, lane-title-slug refused, then both again" + (
        "; " + note if note else "")


def _lsp_round_trip_check():
    """bin/lane-start's JSON, sent to the guard as a create_session, is allowed silently. The guard reads the same
    constants the helper prints, so a field the helper gets wrong is refused here."""
    helper = os.path.join(REPO, "bin", "lane-start")
    brief = os.path.join(ROOT, "lsp-round-trip-brief.md")
    write(brief, "Do the task in the brief file.\n")
    run = subprocess.run([sys.executable, helper, "lane-start-pass", "lane-start", LANE_GRANT, brief],
                         cwd=LANE_REPO, capture_output=True, text=True, timeout=60)
    if run.returncode != 0:
        return False, "bin/lane-start exits %d, want 0: %s" % (run.returncode, run.stderr.strip()[-120:])
    try:
        fields = json.loads(run.stdout)
    except ValueError as err:
        return False, "bin/lane-start printed no JSON object (%s): %s" % (err, run.stdout[:90])
    # The start tags its step, so lane-step-dup reads this session's transcript: section 30130's lane-start-listed, a whole
    # list read with no carrier, proves no other lane holds the step. Its stand-in pull request tool answers for this repo.
    got, reason = ov_call(LANE_TOOL, fields, LANE_REPO, ov_config("lane-start-round-trip"), "session_LSPRT01", 0,
                          env_path=fake_gh_path(LANE_START_GH), transcript=role_path("lane-start-listed"))
    if got != "allow" or reason:
        return False, "the helper's start is refused: %s (%s)" % (got, reason[:120])
    return True, "the helper's start is allowed silently"


# ---- One rule alone: today's refusal, under its own name, with no count line. Each rule has one, so a mutant that drops
# a rule from the collection leaves its case allowed, and goes red.
_lsp_one("lane-one-topic", "a lane brief for another topic alone is refused under lane-one-topic, with no count line",
         tags=OWN_LANE_TAGS + [LSP_ONE_TOPIC], prompt=LANE_GRANT + "\n" + LSP_TOPIC_LINE + "\nDo the task.")
_lsp_one("brief-ids-in-roster", "a lane start whose brief names a bare session id alone is refused under brief-ids-in-roster",
         prompt=LANE_GRANT + "\n" + LSP_BARE_ID_LINE)
_lsp_one("agent-model-floor", "a lane start on haiku alone is refused under agent-model-floor, with no count line",
         model="haiku")
_lsp_one("lane-effort-pin", "a lane start with effort high alone is refused under lane-effort-pin, with no count line",
         effort="high")
_lsp_one("lane-repo-tag", "a lane start with no cs-repo tag alone is refused under lane-repo-tag, with no count line",
         tags=["cs-build:lane"])
_lsp_one("lane-start-settings", "a lane start with no source_url alone is refused under lane-start-settings, with no count line",
         source_url=None)
_lsp_one("lane-title-slug", "a lane start with a free title alone is refused under lane-title-slug, with no count line",
         title=LSP_BAD_TITLE)

# ---- Two rules: one refusal under the first in judge order, with the count of 2 and a line for each.
_lsp_pair("lane-effort-pin", "lane-title-slug", "a lane start with effort high and a free title is one refusal of two rules",
          effort="high", title=LSP_BAD_TITLE)
_lsp_pair("agent-model-floor", "lane-start-settings", "a lane start on haiku with no source_url is one refusal of two rules",
          model="haiku", source_url=None)
_lsp_pair("brief-ids-in-roster", "lane-title-slug", "a lane start with a bare session id in its brief and a free title is one refusal of two rules",
          prompt=LANE_GRANT + "\n" + LSP_BARE_ID_LINE, title=LSP_BAD_TITLE)

# ---- All seven rules at once: the count is 7, every rule is named in judge order, and each remedy is printed. A mutant
# that drops one rule from the collection prints 6 and goes red here.
add(LSP_TOKEN + ": a lane start that breaks all seven lane-start rules is one refusal of seven, in judge order",
    "deny", LSP_ORDER[0], tool=LANE_TOOL, cwd=LANE_REPO,
    carries=((LSP_COUNT % 7,) + LSP_ORDER + tuple(LSP_REMEDY[rule] for rule in LSP_ORDER)
             + tuple(rule + ":" for rule in LSP_ORDER)),
    **_lsp_fields(tags=["cs-build:lane", LSP_ONE_TOPIC], prompt=LANE_GRANT + "\n" + LSP_TOPIC_LINE + "\n" + LSP_BARE_ID_LINE,
                  effort="high", model="haiku", source_url=None, title=LSP_BAD_TITLE))
_lsp_log(LSP_TOKEN + ": all seven lane-start rules are named in judge order after the count line",
         _lsp_order_check(CASES[-1], LSP_ORDER))

# ---- lane-step-dup in the one pass (part one: a live lane carries the start's step). A start that breaks one of the seven
# and holds such a step is one refusal naming both rules. The carrier is a whole list read of this repo with one live lane
# on the step. The start's own step is LSP_STEP_TAG, and its repo is the one the lane-repo-tag rule reads.
LSP_STEP_TAG = "cs-step:lsp-step-held"
LSP_STEP_TAGS = OWN_LANE_TAGS + [LSP_STEP_TAG]
LSP_CARRIER = "session_LSPCARRIER01"
LSP_STEP_REMEDY = "so this would start a second lane on one step"  # a fragment of lane-step-dup's reason


def write_lsp_transcripts():
    """The carrier's whole list read, written as JSONL under this run's role folder."""
    os.makedirs(ROLE_DIR, exist_ok=True)
    rows = [stepdup_row(LSP_CARRIER, STEPDUP_LIVE, ["cs-build:lane", LSP_STEP_TAG, "cs-repo:shivinate7/claude-settings"])]
    with open(role_path("lsp-step-carrier"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(stepdup_list("l1", rows)) + "\n")


lazy_fixture([role_path("lsp-step-carrier")], write_lsp_transcripts)
# The red case: the start breaks lane-title-slug, the last of the seven, and lane-step-dup follows it in judge order.
add(LSP_TOKEN + ": a lane start that breaks lane-title-slug and holds a step a live lane carries is one refusal of two rules",
    "deny", LSP_ORDER[-1], tool=LANE_TOOL, cwd=LANE_REPO, transcript=role_path("lsp-step-carrier"),
    env_path=fake_gh_path(LANE_START_GH),
    carries=("lane-step-dup:", LSP_COUNT % 2, LSP_ORDER[-1] + ":", LSP_REMEDY[LSP_ORDER[-1]], LSP_STEP_REMEDY, LSP_CARRIER),
    **_lsp_fields(tags=LSP_STEP_TAGS, title=LSP_BAD_TITLE))
_lsp_log(LSP_TOKEN + ": a lane start that breaks one rule and holds a step a live lane carries names both in judge order",
         _lsp_order_check(CASES[-1], (LSP_ORDER[-1], "lane-step-dup")))
# Controls, which the code already passes. The held step with every other rule met is lane-step-dup's alone, with no count line. The same
# broken rule with no live lane on its step is that rule's alone, so lane-step-dup adds no line when it passes.
add(LSP_TOKEN + ": a lane start that holds a step a live lane carries and breaks no other rule is refused under lane-step-dup alone",
    "deny", "lane-step-dup", tool=LANE_TOOL, cwd=LANE_REPO, transcript=role_path("lsp-step-carrier"),
    env_path=fake_gh_path(LANE_START_GH), carries=(LSP_CARRIER, LSP_STEP_REMEDY), lacks=_lsp_others("lane-step-dup"),
    **_lsp_fields(tags=LSP_STEP_TAGS))
add(LSP_TOKEN + ": a lane start that breaks lane-title-slug and holds no step a live lane carries is refused under that rule alone",
    "deny", LSP_ORDER[-1], tool=LANE_TOOL, cwd=LANE_REPO, transcript=role_path("lane-start-listed"),
    env_path=fake_gh_path(LANE_START_GH), carries=(LSP_REMEDY[LSP_ORDER[-1]],),
    lacks=("lane-step-dup:", LSP_COUNT_WORDS), **_lsp_fields(tags=LSP_STEP_TAGS, title=LSP_BAD_TITLE))

# ---- The override. One liftable rule per refusal: the first lifted, the second still refused, then the first again.
_lsp_log(LSP_TOKEN + ": a one-act override lifts the first broken rule only, and the next is refused", _lsp_once_check)

# ---- Allowed. A lane start that breaks no rule passes silently, and a call with no lane tag is not judged by these rules.
add(LSP_TOKEN + ": a lane start that breaks no lane-start rule is allowed silently", "allow", silent=True,
    tool=LANE_TOOL, cwd=LANE_REPO, **_lsp_fields())
add(LSP_TOKEN + ": a create_session with no lane tag is not judged by the lane-start rules", "allow", silent=True,
    tool=LANE_TOOL, cwd=LANE_REPO, **_lsp_fields(tags=None, effort="high", source_url=None, title=LSP_BAD_TITLE))
# send_message briefs keep one rule each: a brief with a bare session id and no lane start is refused under that rule alone.
add(LSP_TOKEN + ": a send_message brief that names a bare session id is refused under brief-ids-in-roster alone", "deny",
    "brief-ids-in-roster", tool="mcp__claude-code-remote__send_message",
    message=LANE_GRANT + "\n" + LSP_BARE_ID_LINE, carries=(LSP_REMEDY["brief-ids-in-roster"],),
    lacks=(LSP_COUNT_WORDS,))

# ---- The helper's output, through the guard. A missing or wrong helper fails here, by its exit and its output.
_lsp_log(LSP_TOKEN + ": the output of bin/lane-start is allowed as a create_session", _lsp_round_trip_check)

# ---- Change 4. The archive read refusals name the fix: attach the lane's repo read-only with add_repo, then retry.
FAMILY = "lane-closes-after-records"
# The open-list read fails (a broken gh). The lane's one repo is o/r (ARCH_LANE_TAGS), and the refusal names it.
archive_refuse(LSP_TOKEN + ": a lane whose open pull requests cannot be read names add_repo, read-only and its repo",
               role_path("archive-lane"), fake_gh_path(GHBROKEN),
               carries=(LSP_ADD_REPO, LSP_READ_ONLY, "o/r", ARCHIVE_READ_PIN), lacks=(LSP_RETRY,))
# The branch read fails (a source that is a string, not a list), so the branch reason is the one that refuses.
archive_refuse(LSP_TOKEN + ": a lane whose branch read cannot run names add_repo and read-only, not the retry alone",
               role_path("archive-inc-sources-str"), fake_gh_path(ARCHINC_BEHIND),
               carries=(LSP_ADD_REPO, LSP_READ_ONLY, ARCHIVE_READ_PIN), lacks=(LSP_RETRY,))
# No gh on the path: the open-list read cannot run at all.
archive_refuse(LSP_TOKEN + ": a lane with no gh on the path names add_repo and read-only",
               role_path("archive-lane"), GHNONE_PATH,
               carries=(LSP_ADD_REPO, LSP_READ_ONLY, ARCHIVE_READ_PIN), lacks=(LSP_RETRY,))
FAMILY = _lsp_prior_family
