# section 43720
# The owner's model word lifts a model refusal for an Agent, Task, Workflow or lane-start spawn: the model floor
# (agent-model-floor, guard step 9), the role row (agent-role-model) and the Opus ceiling (agent-model-cap), and no other rule.
# Rulings: a named model holds until the task's next report (13:27 CST Nov 23); every model, Opus too (22:35 CST Nov 24); a
# judge, not a plain match, decides that the owner named a model (10:41 CST Nov 25); a turn-end line while a model is on
# (10:02 CST Nov 25). Haiku keeps main's plain text match on the owner's latest typed turn (owner, 2026-11-18 19:03 CST).
# A judged yes for any model writes the hold to the Opus pass file (state/override/opus/<session>.json: `model`, and `end`
# "report" for a plain ask), which ends at the session's next report or at `until`. Claude's own text, a tool result, a peer
# relay, a machine notice, a pasted block, a seed brief (turnOrigin other than human) and a compaction summary are never the
# owner's model name. With no word the refusal stands. A spawn that names no model stays on the default, Sonnet.
#
# A red allow case has a control on the same transcript, so the lift is the only thing that separates them. A red deny case
# has a word that must not count. Each control keeps its verdict on the old code too. An owner turn older than one megabyte is
# still the latest one. ov_clock and OV_T0 come from section 36421. Labels carry `owner-model-word:`, so
# MUTATE_ONLY=owner-model-word runs these alone.
FAMILY = "rule9"

OMW_DIR = os.path.join(ROOT, "owner-model-word")  # the run folder's home for these transcripts
OMW_HAIKU = "Run the model audit on haiku."       # the owner's typed text that names the model
OMW_FULL_LINES = 1500                             # about 1.6 MB of filler, more than one megabyte


def omw_user(text):
    """An owner turn: a user record with text and no origin, as the transcript holds it."""
    return {"type": "user", "message": {"role": "user", "content": text}}


def omw_asst(text):
    """An assistant reply: Claude's own words, never the owner's."""
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def omw_result(text):
    """A tool result: a user record whose content is a tool_result block, never a typed turn."""
    return {"type": "user", "message": {"role": "user",
                                        "content": [{"type": "tool_result", "tool_use_id": "toolu_omw", "content": text}]}}


def omw_peer(text):
    """A peer session's message relayed into this session: a user record whose origin is a peer."""
    return {"type": "user", "origin": {"kind": "peer", "from": "coordinator"},
            "message": {"role": "user", "content": text}}


def omw_file(name, records):
    """A transcript under the run folder, one JSON record per line. The file is built the first time a case names it,
    so a case that names no transcript builds none."""
    path = os.path.join(OMW_DIR, name + ".jsonl")

    def build():
        write(path, "".join(json.dumps(record) + "\n" for record in records))

    lazy_fixture([path], build)
    return path


OMW_OWNER_HAIKU = omw_file("owner-haiku", [omw_user(OMW_HAIKU), omw_asst("Running the audit.")])
OMW_FULL_HAIKU = omw_file("full-owner-haiku", [omw_user("Use sonnet for the audit.")]
                          + [omw_asst("x" * 1000) for _ in range(OMW_FULL_LINES)]
                          + [omw_user(OMW_HAIKU)])
OMW_PLAIN = omw_file("owner-plain", [omw_user("Run the model audit."), omw_asst("Running it.")])
OMW_LATEST_SONNET = omw_file("owner-latest-sonnet", [omw_user(OMW_HAIKU), omw_asst("Ok."), omw_user("Use sonnet instead.")])
OMW_LATEST_OPUS = omw_file("owner-latest-opus", [omw_user(OMW_HAIKU), omw_asst("Ok."), omw_user("Use opus for it.")])
OMW_ASSISTANT_HAIKU = omw_file("assistant-haiku", [omw_user("Run the model audit."), omw_asst("I will run this on haiku.")])
OMW_RESULT_HAIKU = omw_file("result-haiku", [omw_user("Run the model audit."), omw_result("model: haiku")])
OMW_PEER_HAIKU = omw_file("peer-haiku", [omw_user("Run the model audit."), omw_peer(OMW_HAIKU)])
OMW_NOTICE_HAIKU = omw_file("notice-haiku", [omw_user("Run the model audit."),
                                             omw_user("<system-reminder>\nUse haiku for the audit.\n</system-reminder>")])
OMW_EMPTY = omw_file("empty", [])
OMW_MISSING = os.path.join(OMW_DIR, "missing.jsonl")  # named, never built

WF_SCRIPT = "await agent(\"do it\", {model:\"%s\"})"

# ---- Red: the owner's latest turn names haiku, so an Agent or Workflow spawn on haiku passes. Each has a Sonnet twin.
add("owner-model-word: an Agent spawn on haiku is allowed when the owner's latest turn names haiku", "allow",
    tool="Agent", prompt="do it", model="haiku", transcript=OMW_OWNER_HAIKU)
add("owner-model-word: twin, an Agent spawn on sonnet is allowed with the same owner turn", "allow",
    tool="Agent", prompt="do it", model="sonnet", transcript=OMW_OWNER_HAIKU)
add("owner-model-word: a Workflow agent on haiku is allowed when the owner's latest turn names haiku", "allow",
    tool="Workflow", script=WF_SCRIPT % "haiku", transcript=OMW_OWNER_HAIKU)
add("owner-model-word: twin, a Workflow agent on sonnet is allowed with the same owner turn", "allow",
    tool="Workflow", script=WF_SCRIPT % "sonnet", transcript=OMW_OWNER_HAIKU)
add("owner-model-word: an Agent spawn on haiku is allowed when the owner's latest turn names haiku after a transcript "
    "over one megabyte", "allow",
    tool="Agent", prompt="do it", model="haiku", transcript=OMW_FULL_HAIKU)
add("owner-model-word: twin, an Agent spawn on sonnet is allowed after the same transcript over one megabyte", "allow",
    tool="Agent", prompt="do it", model="sonnet", transcript=OMW_FULL_HAIKU)

# ---- Controls: each word below is not the owner's latest typed turn, so the refusal stands as it does today.
add("owner-model-word: an Agent spawn on haiku is refused when the owner's turns name no model", "deny",
    "agent-model-floor", tool="Agent", prompt="do it", model="haiku", transcript=OMW_PLAIN)
add("owner-model-word: an Agent spawn on haiku is refused when the owner's latest turn names sonnet, though an earlier one "
    "named haiku", "deny", "agent-model-floor",
    tool="Agent", prompt="do it", model="haiku", transcript=OMW_LATEST_SONNET)
add("owner-model-word: an Agent spawn on haiku is refused when the owner's latest turn names opus, though an earlier one "
    "named haiku", "deny", "agent-model-floor",
    tool="Agent", prompt="do it", model="haiku", transcript=OMW_LATEST_OPUS)
add("owner-model-word: an Agent spawn on haiku is refused when only Claude's own reply names haiku", "deny",
    "agent-model-floor", tool="Agent", prompt="do it", model="haiku", transcript=OMW_ASSISTANT_HAIKU)
add("owner-model-word: an Agent spawn on haiku is refused when only a tool result names haiku", "deny",
    "agent-model-floor", tool="Agent", prompt="do it", model="haiku", transcript=OMW_RESULT_HAIKU)
add("owner-model-word: an Agent spawn on haiku is refused when only a peer relay names haiku", "deny",
    "agent-model-floor", tool="Agent", prompt="do it", model="haiku", transcript=OMW_PEER_HAIKU)
add("owner-model-word: an Agent spawn on haiku is refused when only a machine notice names haiku", "deny",
    "agent-model-floor", tool="Agent", prompt="do it", model="haiku", transcript=OMW_NOTICE_HAIKU)
add("owner-model-word: an Agent spawn on haiku with no transcript_path is refused", "deny",
    "agent-model-floor", tool="Agent", prompt="do it", model="haiku")
add("owner-model-word: an Agent spawn on haiku whose transcript is missing is refused", "deny",
    "agent-model-floor", tool="Agent", prompt="do it", model="haiku", transcript=OMW_MISSING)
add("owner-model-word: an Agent spawn on haiku whose transcript is empty is refused", "deny",
    "agent-model-floor", tool="Agent", prompt="do it", model="haiku", transcript=OMW_EMPTY)

# ---- The default holds. A spawn that names no model is judged as today, and the owner's model name does not give it haiku.
add("owner-model-word: an Agent spawn with no model is allowed as today, with no owner word", "allow",
    tool="Agent", prompt="do it", transcript=OMW_PLAIN, silent=True)
add("owner-model-word: an Agent spawn with no model stays on the default when the owner names haiku", "allow",
    tool="Agent", prompt="do it", transcript=OMW_OWNER_HAIKU, silent=True)

# ---- A negated name lifts nothing. The negation regex misses a spelling without an apostrophe, a curly apostrophe, a stop
# word, a word between the negation and the model, and a correction that comes after the model. The straight apostrophe
# is the control: the same negation the regex knows.
OMW_DONT = omw_file("owner-dont-use-haiku", [omw_user("dont use haiku."), omw_asst("Not using haiku.")])
OMW_CURLY_DONT = omw_file("owner-curly-dont-haiku", [omw_user("Don’t use haiku."), omw_asst("Not using haiku.")])
OMW_DO_NOT_AUDIT = omw_file("owner-do-not-audit-haiku", [omw_user("Do not run the audit on haiku."), omw_asst("Ok.")])
OMW_STOP_USING = omw_file("owner-stop-using-haiku", [omw_user("Stop using haiku."), omw_asst("Ok.")])
OMW_CORRECTED = omw_file("owner-haiku-corrected", [omw_user("Use haiku. No, not haiku, use sonnet."), omw_asst("Ok.")])
OMW_STRAIGHT_DONT = omw_file("owner-straight-dont-haiku", [omw_user("Don't use haiku."), omw_asst("Not using haiku.")])
add("owner-model-word: an Agent spawn on haiku is refused when the owner's latest turn says dont use haiku", "deny",
    "agent-model-floor", tool="Agent", prompt="do it", model="haiku", transcript=OMW_DONT)
add("owner-model-word: an Agent spawn on haiku is refused when the owner's latest turn says don't with a curly apostrophe",
    "deny", "agent-model-floor", tool="Agent", prompt="do it", model="haiku", transcript=OMW_CURLY_DONT)
add("owner-model-word: an Agent spawn on haiku is refused when the owner's latest turn says do not run the audit on haiku",
    "deny", "agent-model-floor", tool="Agent", prompt="do it", model="haiku", transcript=OMW_DO_NOT_AUDIT)
add("owner-model-word: an Agent spawn on haiku is refused when the owner's latest turn says stop using haiku", "deny",
    "agent-model-floor", tool="Agent", prompt="do it", model="haiku", transcript=OMW_STOP_USING)
add("owner-model-word: an Agent spawn on haiku is refused when the owner's latest turn says use haiku, then no, not haiku, "
    "use sonnet", "deny", "agent-model-floor", tool="Agent", prompt="do it", model="haiku", transcript=OMW_CORRECTED)
add("owner-model-word: control, an Agent spawn on haiku is refused when the owner's latest turn says don't use haiku with "
    "a straight apostrophe", "deny", "agent-model-floor", tool="Agent", prompt="do it", model="haiku",
    transcript=OMW_STRAIGHT_DONT)

# ---- A haiku word inside a pasted block is not the owner's model name: the owner typed only the sentence before the block.
OMW_PASTED = omw_file("owner-pasted-haiku", [omw_user("Read this log and say what failed.\n<pasted_content>\n"
                                                      "Run the model audit on haiku.\n</pasted_content>"),
                                             omw_asst("Reading it.")])
add("owner-model-word: an Agent spawn on haiku is refused when the only haiku word in the owner's latest turn is in a "
    "pasted block", "deny", "agent-model-floor", tool="Agent", prompt="do it", model="haiku", transcript=OMW_PASTED)

# ---- The Opus ceiling takes no typed word. Opus is lifted only by a judged hold (the hold section below) or by an override.
# A question that names opus, and a turn that names it, are refused as on main (controls, 22:35 and 10:02 CST rulings
# read with the judge's ruling of 10:41 CST Nov 25).
OMW_WHY_OPUS = omw_file("owner-why-opus", [omw_user("Why did the opus spawn get refused?"),
                                           omw_asst("The Opus ceiling refused it.")])
OMW_NAMES_OPUS = omw_file("owner-names-opus", [omw_user("Run the model audit on opus."), omw_asst("Running it.")])
add("owner-model-word: control, an Agent spawn on opus is refused when the owner asks why an opus spawn was refused", "deny",
    CEILING, tool="Agent", prompt="do it", model="opus", transcript=OMW_WHY_OPUS)
add("owner-model-word: control, an Agent spawn on opus is refused when the owner's latest typed turn names opus", "deny",
    CEILING, tool="Agent", prompt="do it", model="opus", transcript=OMW_NAMES_OPUS)
add("owner-model-word: control, an Agent spawn on opus is refused when the owner's latest turn names haiku", "deny", CEILING,
    tool="Agent", prompt="do it", model="opus", transcript=OMW_OWNER_HAIKU)

# ---- A lane start takes the same word. Its floor is judged with the lane-start rules; every other lane rule still holds.
# _lsp_fields (section 43500) is the one home of a passing lane start: the Grant line, the title and the effort are set.
add("owner-model-word: a lane start on haiku is allowed when the owner's latest turn names haiku", "allow",
    tool=LANE_TOOL, cwd=LANE_REPO, transcript=OMW_OWNER_HAIKU, **_lsp_fields(model="haiku"))
add("owner-model-word: twin, a lane start on sonnet is allowed with the same owner turn", "allow",
    tool=LANE_TOOL, cwd=LANE_REPO, transcript=OMW_OWNER_HAIKU, **_lsp_fields(model="sonnet"))
add("owner-model-word: control, a lane start on haiku is refused when the owner's turns name no model", "deny",
    "agent-model-floor", tool=LANE_TOOL, cwd=LANE_REPO, transcript=OMW_PLAIN, **_lsp_fields(model="haiku"))

# ---- The owner's latest typed turn counts however far back it sits. More than one megabyte of Claude's reply after it
# does not hide it.
OMW_OLD_HAIKU = omw_file("owner-haiku-then-over-mib", [omw_user(OMW_HAIKU)]
                         + [omw_asst("x" * 1000) for _ in range(OMW_FULL_LINES)])
add("owner-model-word: an Agent spawn on haiku is allowed when the owner's latest turn names haiku and over one megabyte "
    "of Claude's reply follows it", "allow", tool="Agent", prompt="do it", model="haiku", transcript=OMW_OLD_HAIKU)
add("owner-model-word: twin, an Agent spawn on sonnet is allowed after the same transcript", "allow",
    tool="Agent", prompt="do it", model="sonnet", transcript=OMW_OLD_HAIKU)

# ---- Clause and negation reach. A negation reaches only to the end of its own clause (MODEL_CLAUSE_BREAK, guard.py), and
# a negation that governs another word does not refuse the name: `Not sonnet but haiku`, `Skip the checks and run it on
# haiku`. `instead` negates nothing when it does not stand before the name. A name written in full (claude-haiku-4-5) or with
# a point (haiku-4.5) is the owner's model name for haiku. The clause case is green on the old code: it pins the clause break, and a
# mutant whose MODEL_CLAUSE_BREAK matches nothing turns it red. The other allows are red on the old code, each with a Sonnet
# twin. The two controls are negations that do govern the name, so they stay refused.
OMW_CLAUSE_DONT = omw_file("owner-dont-clause-then-haiku", [omw_user("Don't overthink it. Use haiku."), omw_asst("Ok.")])
OMW_INSTEAD = omw_file("owner-instead-use-haiku", [omw_user("Instead use haiku."), omw_asst("Ok.")])
OMW_NOT_SONNET_BUT = omw_file("owner-not-sonnet-but-haiku", [omw_user("Not sonnet but haiku."), omw_asst("Ok.")])
OMW_DONT_COLON = omw_file("owner-dont-colon-use-haiku", [omw_user("Don't overthink it: use haiku."), omw_asst("Ok.")])
OMW_SKIP_CHECKS = omw_file("owner-skip-checks-haiku", [omw_user("Skip the checks and run it on haiku"), omw_asst("Ok.")])
OMW_FULL_NAME = omw_file("owner-full-model-name", [omw_user("Use claude-haiku-4-5 for the audit."), omw_asst("Ok.")])
OMW_POINT_NAME = omw_file("owner-point-model-name", [omw_user("Use haiku-4.5 for the audit."), omw_asst("Ok.")])
OMW_SONNET_INSTEAD_OF = omw_file("owner-sonnet-instead-of-haiku",
                                 [omw_user("Use sonnet instead of haiku."), omw_asst("Ok.")])
OMW_NOT_HAIKU_BUT = omw_file("owner-not-haiku-but-sonnet", [omw_user("Not haiku but sonnet."), omw_asst("Ok.")])

add("owner-model-word: an Agent spawn on haiku is allowed when a negation sits in an earlier clause, after a full stop", "allow",
    tool="Agent", prompt="do it", model="haiku", transcript=OMW_CLAUSE_DONT)
add("owner-model-word: an Agent spawn on haiku is allowed when the owner's latest turn says instead use haiku", "allow",
    tool="Agent", prompt="do it", model="haiku", transcript=OMW_INSTEAD)
add("owner-model-word: twin, an Agent spawn on sonnet is allowed with the same owner turn (instead use haiku)", "allow",
    tool="Agent", prompt="do it", model="sonnet", transcript=OMW_INSTEAD)
add("owner-model-word: an Agent spawn on haiku is allowed when the owner's latest turn says not sonnet but haiku", "allow",
    tool="Agent", prompt="do it", model="haiku", transcript=OMW_NOT_SONNET_BUT)
add("owner-model-word: twin, an Agent spawn on sonnet is allowed with the same owner turn (not sonnet but haiku)", "allow",
    tool="Agent", prompt="do it", model="sonnet", transcript=OMW_NOT_SONNET_BUT)
add("owner-model-word: an Agent spawn on haiku is allowed when the owner's latest turn says don't overthink it: use haiku",
    "allow", tool="Agent", prompt="do it", model="haiku", transcript=OMW_DONT_COLON)
add("owner-model-word: twin, an Agent spawn on sonnet is allowed with the same owner turn (don't overthink it: use haiku)",
    "allow", tool="Agent", prompt="do it", model="sonnet", transcript=OMW_DONT_COLON)
add("owner-model-word: an Agent spawn on haiku is allowed when the owner's latest turn says skip the checks and run it on "
    "haiku", "allow", tool="Agent", prompt="do it", model="haiku", transcript=OMW_SKIP_CHECKS)
add("owner-model-word: twin, an Agent spawn on sonnet is allowed with the same owner turn (skip the checks, run it on haiku)",
    "allow", tool="Agent", prompt="do it", model="sonnet", transcript=OMW_SKIP_CHECKS)
add("owner-model-word: an Agent spawn on claude-haiku-4-5 is allowed when the owner's latest turn names claude-haiku-4-5",
    "allow", tool="Agent", prompt="do it", model="claude-haiku-4-5", transcript=OMW_FULL_NAME)
add("owner-model-word: twin, an Agent spawn on sonnet is allowed with the same owner turn (claude-haiku-4-5)", "allow",
    tool="Agent", prompt="do it", model="sonnet", transcript=OMW_FULL_NAME)
add("owner-model-word: an Agent spawn on haiku-4.5 is allowed when the owner's latest turn names haiku-4.5", "allow",
    tool="Agent", prompt="do it", model="haiku-4.5", transcript=OMW_POINT_NAME)
add("owner-model-word: twin, an Agent spawn on sonnet is allowed with the same owner turn (haiku-4.5)", "allow",
    tool="Agent", prompt="do it", model="sonnet", transcript=OMW_POINT_NAME)
add("owner-model-word: control, an Agent spawn on haiku is refused when the owner's latest turn says use sonnet instead of "
    "haiku", "deny", "agent-model-floor", tool="Agent", prompt="do it", model="haiku", transcript=OMW_SONNET_INSTEAD_OF)
add("owner-model-word: control, an Agent spawn on haiku is refused when the owner's latest turn says not haiku but sonnet",
    "deny", "agent-model-floor", tool="Agent", prompt="do it", model="haiku", transcript=OMW_NOT_HAIKU_BUT)

# ---- A haiku named two owner turns back no longer lifts the floor by itself: the text match reads the latest typed turn only.
# A judged haiku hold lifts it for the task until its report (the hold section below).
OMW_HAIKU_TWO_BACK = omw_file("owner-haiku-two-turns-back", [omw_user(OMW_HAIKU), omw_asst("Running the audit."),
                                                            omw_user("Check the logs too."), omw_asst("Checking the logs.")])
add("owner-model-word: control, an Agent spawn on haiku is refused when the owner named haiku two turns back and the latest "
    "turn names no model", "deny", "agent-model-floor", tool="Agent", prompt="do it", model="haiku",
    transcript=OMW_HAIKU_TWO_BACK)

# ---- A pasted block is not the owner's model name, however far back it sits: the haiku word below is in a block two turns back.
OMW_PASTED_HELD = omw_file("owner-pasted-haiku-held", [omw_user("Read this log and say what failed.\n<pasted_content>\n"
                                                                 "Run the model audit on haiku.\n</pasted_content>"),
                                                      omw_asst("Reading it."), omw_user("Check the logs too."),
                                                      omw_asst("Checking the logs.")])
OMW_PASTED_OPUS = omw_file("owner-pasted-opus", [omw_user("Read this log and say what failed.\n<pasted_content>\n"
                                                          "Run the model audit on opus.\n</pasted_content>"),
                                                 omw_asst("Reading it.")])
add("owner-model-word: control, an Agent spawn on haiku is refused when the only haiku word is in a pasted block two turns back",
    "deny", "agent-model-floor", tool="Agent", prompt="do it", model="haiku", transcript=OMW_PASTED_HELD)
add("owner-model-word: control, an Agent spawn on opus is refused when the only opus word in the owner's turn is in a pasted block",
    "deny", CEILING, tool="Agent", prompt="do it", model="opus", transcript=OMW_PASTED_OPUS)

# ---- Each model keeps the newest word only. A later model word ends the earlier ones: "use opus", then "use sonnet instead",
# leaves Opus off. Both are controls: the Opus ceiling refuses on the old code too, and a plain sonnet spawn is allowed.
OMW_OPUS_THEN_SONNET = omw_file("owner-opus-then-sonnet-instead", [omw_user("Use opus for it."), omw_asst("Ok."),
                                                                  omw_user("Use sonnet instead.")])
add("owner-model-word: control, an Agent spawn on opus is refused when the owner's later turn says use sonnet instead of the "
    "earlier use opus", "deny", CEILING, tool="Agent", prompt="do it", model="opus", transcript=OMW_OPUS_THEN_SONNET)
add("owner-model-word: twin, an Agent spawn on sonnet is allowed with the same owner turns (use opus, then use sonnet instead)",
    "allow", tool="Agent", prompt="do it", model="sonnet", transcript=OMW_OPUS_THEN_SONNET)

# ---- "no <model>" and "<model> off" end the word, so the Opus ceiling refuses again. Both are controls on the old code too.
OMW_OPUS_NO = omw_file("owner-opus-then-no-opus", [omw_user("Use opus for it."), omw_asst("Ok."), omw_user("no opus"),
                                                  omw_asst("Stopped.")])
OMW_OPUS_OFF = omw_file("owner-opus-then-opus-off", [omw_user("Use opus for it."), omw_asst("Ok."), omw_user("opus off"),
                                                    omw_asst("Stopped.")])
add("owner-model-word: control, an Agent spawn on opus is refused when the owner's later turn says no opus", "deny", CEILING,
    tool="Agent", prompt="do it", model="opus", transcript=OMW_OPUS_NO)
add("owner-model-word: control, an Agent spawn on opus is refused when the owner's later turn says opus off", "deny", CEILING,
    tool="Agent", prompt="do it", model="opus", transcript=OMW_OPUS_OFF)

# ---- THE HOLD FILE (the lane decision). A judged yes for a named model writes the hold to the Opus pass file,
# state/override/opus/<session>.json: `model`, and `end` "report" for a plain ask with no length. It ends at the session's next
# report (an assistant record after `at` that passes report_shape_ok) or at `until`, whichever comes first. A keyword hold
# keeps its `until` and has no `end`. These helpers write the file as the judge's yes does. Times are seconds after OV_T0.
OMW_NOW_ENV = {"LOCAL_TIME_NOW": ov_clock(60)}  # the guard's clock, a minute after the hold was set
OMW_REPORT = "> **Done** BUILT abc123\n> **Next** ship it"


def omw_at(record, stamp):
    """The record with the transcript timestamp `stamp`: the instant the reader compares with a hold's `at`."""
    record["timestamp"] = stamp
    return record


def omw_hold(name, session, model, end="report", at=0, until=2 * 3600, role=None):
    """A config folder with the role table pointer (role_config) and the session's hold file for `model`. Returns the
    folder, for a case's `config`. The file is built when a case names the folder."""
    config = role_config("omw-" + name, REPO)
    body = {"kind": "opus", "until": ov_clock(until), "role": role, "model": model, "at": ov_clock(at)}
    if end:
        body["end"] = end
    path = os.path.join(config, "state", "override", "opus", session + ".json")
    lazy_fixture([config], lambda: write(path, json.dumps(body)))
    return config


OMW_HOLD_PLAIN = omw_file("omw-hold-plain", [omw_at(omw_user("Use sonnet for the record."), ov_clock(-60)),
                                              omw_at(omw_asst("Ok."), ov_clock(30))])
OMW_REPORT_AFTER = omw_file("omw-report-after-hold", [omw_at(omw_user("Use sonnet for the record."), ov_clock(-60)),
                                                      omw_at(omw_asst("Ok."), ov_clock(30)),
                                                      omw_at(omw_asst(OMW_REPORT), ov_clock(120))])


def omw_lets_through(name, tool_input, config, session, seconds, rule, transcript=OMW_HOLD_PLAIN, tool="Agent"):
    """A log check: the one guard call, at `seconds` after OV_T0, must be an allow. A hold lifts a refusal in one of two ways,
    silent (the floor and the role row skip their refusal) or with the one lift line that names `rule` (the Opus ceiling
    goes through take()). ov_want reads both, as the Opus pass cases do. The check runs in every full run."""
    def call():
        return ov_call(tool, dict(tool_input), NOGIT, config, session, seconds, transcript=transcript)
    # This section loads after the LOG_CHECKS_EXTRA join (section 40805), so the check joins LOG_CHECKS directly.
    global LOG_CHECKS
    label = "owner-model-word: " + name
    LOG_CHECKS = LOG_CHECKS + ((label, lambda: ov_story([(name, call, "allow", rule)])),)
    LOG_FAMILY[label] = FAMILY


# ---- The role row takes the judged hold, not a typed word. A record-writer on sonnet (its row is haiku) and a builder on fable
# (fable is not ranked, so the row fails closed) pass only while the owner's hold for that model is on. Each allow has a
# control with no hold, refused as today.
omw_lets_through("a record-writer spawn on sonnet is allowed while the owner's sonnet hold is on",
                 role_input("record-writer", "sonnet", "Write the record."), omw_hold("sonnet-held", "omw-sonnet-held", "sonnet"),
                 "omw-sonnet-held", 60, ROLE_MODEL_RULE)
add("owner-model-word: control, a record-writer spawn on sonnet is refused under agent-role-model when no hold is on", "deny",
    ROLE_MODEL_RULE, tool="Agent", config=ROLE_REAL_CFG, transcript=OMW_PLAIN, carries=(ROLE_REMEDY,),
    lacks=ROLE_LACKS, **role_input("record-writer", "sonnet", "Write the record."))
omw_lets_through("a builder spawn on fable is allowed while the owner's fable hold is on",
                 role_input("builder", "fable", "Fix the failing case."), omw_hold("fable-held", "omw-fable-held", "fable"),
                 "omw-fable-held", 60, ROLE_MODEL_RULE)
add("owner-model-word: control, a builder spawn on fable is refused under agent-role-model when no hold is on", "deny",
    ROLE_MODEL_RULE, tool="Agent", config=ROLE_REAL_CFG, transcript=OMW_PLAIN, carries=(ROLE_REMEDY,),
    lacks=ROLE_LACKS, **role_input("builder", "fable", "Fix the failing case."))

# ---- The floor takes the judged haiku hold as well as the text match. A haiku hold lifts the floor on a transcript that names no
# model. Haiku keeps the plain text match: a judge error writes no hold, and the owner's typed haiku word still lifts the floor.
omw_lets_through("an Agent spawn on haiku is allowed while the owner's haiku hold is on, with no model word in the transcript",
                 {"prompt": "do it", "model": "haiku"}, omw_hold("haiku-held", "omw-haiku-held", "haiku"),
                 "omw-haiku-held", 60, "agent-model-floor")
add("owner-model-word: control, an Agent spawn on haiku is allowed by the plain match when the judge's error left no hold",
    "allow", tool="Agent", prompt="do it", model="haiku", transcript=OMW_OWNER_HAIKU)
add("owner-model-word: control, an Agent spawn on haiku is refused after a report ends the haiku hold", "deny",
    "agent-model-floor", tool="Agent", prompt="do it", model="haiku", config=omw_hold("haiku-report", "omw-haiku-report", "haiku"),
    session="omw-haiku-report", transcript=OMW_REPORT_AFTER, env={"LOCAL_TIME_NOW": ov_clock(180)})

# ---- A hold ends at the session's next report, and at `until` (2 h after it was set). A plain Opus hold is the same file.
add("owner-model-word: control, a record-writer spawn on sonnet is refused after the report ends the sonnet hold", "deny",
    ROLE_MODEL_RULE, tool="Agent", config=omw_hold("sonnet-report", "omw-sonnet-report", "sonnet"),
    session="omw-sonnet-report", transcript=OMW_REPORT_AFTER, env={"LOCAL_TIME_NOW": ov_clock(180)},
    carries=(ROLE_REMEDY,), lacks=ROLE_LACKS, **role_input("record-writer", "sonnet", "Write the record."))
omw_lets_through("control, an Agent spawn on opus is allowed while a plain Opus hold is on, before the report",
                 {"prompt": "do it", "model": "opus"}, omw_hold("opus-held", "omw-opus-held", "opus"), "omw-opus-held", 60,
                 CEILING)
add("owner-model-word: an Agent spawn on opus is refused after the report ends a plain Opus hold", "deny", CEILING,
    tool="Agent", prompt="do it", model="opus", config=omw_hold("opus-report", "omw-opus-report", "opus"),
    session="omw-opus-report", transcript=OMW_REPORT_AFTER, env={"LOCAL_TIME_NOW": ov_clock(180)})
omw_lets_through("a held sonnet still lifts a record-writer spawn at 1 h 59 min, before its 2 h end",
                 role_input("record-writer", "sonnet", "Write the record."), omw_hold("sonnet-2h", "omw-sonnet-2h", "sonnet"),
                 "omw-sonnet-2h", 7140, ROLE_MODEL_RULE)
add("owner-model-word: control, a record-writer spawn on sonnet is refused at 2 h 01 min, after the hold's 2 h end", "deny",
    ROLE_MODEL_RULE, tool="Agent", config=omw_hold("sonnet-2h-end", "omw-sonnet-2h-end", "sonnet"),
    session="omw-sonnet-2h-end", transcript=OMW_HOLD_PLAIN, env={"LOCAL_TIME_NOW": ov_clock(7260)},
    carries=(ROLE_REMEDY,), lacks=ROLE_LACKS, **role_input("record-writer", "sonnet", "Write the record."))

# ---- A held model lifts only its three rules. Neither the Opus ceiling nor a remote session call from an agent is lifted by a
# held sonnet. Both are controls: each is refused on the old code too.
add("owner-model-word: a held sonnet does not lift the Opus ceiling for a spawn with no role", "deny", CEILING,
    tool="Agent", prompt="do it", model="opus", config=omw_hold("sonnet-ceiling", "omw-sonnet-ceiling", "sonnet"),
    session="omw-sonnet-ceiling", transcript=OMW_HOLD_PLAIN, env=OMW_NOW_ENV)
add("owner-model-word: control, a held sonnet lifts no other rule: an agent's remote session call is still refused", "deny",
    "agent-no-remote-tools", tool=CREATE_SESSION, agent_id=OV_AGENT, config=omw_hold("sonnet-other", "omw-sonnet-other", "sonnet"),
    session="omw-sonnet-other", transcript=OMW_HOLD_PLAIN, env=OMW_NOW_ENV)

# ---- A local session's first typed turn is the owner's own word: no seed skip applies outside a cloud session. Control.
OMW_FIRST_HAIKU = omw_file("local-first-turn-haiku", [omw_user(OMW_HAIKU)])
add("owner-model-word: control, an Agent spawn on haiku is allowed when a local session's first typed turn names haiku", "allow",
    tool="Agent", prompt="do it", model="haiku", transcript=OMW_FIRST_HAIKU)
