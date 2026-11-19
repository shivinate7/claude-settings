# section 43700
# The owner's word lifts the model floor for an Agent, Task, Workflow or lane-start spawn (rule agent-model-floor,
# guard step 9). Owner, 2026-11-18 19:03 CST: "if i say haiku it should work, there shouldnt be any guards on a FLOOR".
# When the owner's latest typed turn names the spawn's model as a whole word, and no negation precedes the name, a
# spawn on that model passes the floor. The word never lifts the Opus ceiling (agent-model-cap). With no owner word the
# refusal stands. A spawn that names no model stays on the default, Sonnet, and the owner's word never changes it.
#
# A red allow case has a Sonnet twin on the same transcript, so the floor is the only thing that separates them. A red
# deny case has a word that must not count: a negated name, a name inside a pasted block, or an Opus name. Each control
# keeps its verdict today. A word that is not the owner's latest typed turn (Claude's own text, a tool result, a peer
# relay, a machine notice, an earlier turn) does not lift the floor. An owner turn older than one megabyte is still the
# latest one. Labels carry `owner-model-word:`, so MUTATE_ONLY=owner-model-word runs these cases alone.
FAMILY = "rule9"

OMW_DIR = os.path.join(ROOT, "owner-model-word")  # the run folder's home for these transcripts
OMW_HAIKU = "Run the model audit on haiku."       # the owner's words that name the model
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

# ---- The default holds. A spawn that names no model is judged as today, and the owner's word does not give it haiku.
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

# ---- A haiku word inside a pasted block is not the owner's word: the owner typed only the sentence before the block.
OMW_PASTED = omw_file("owner-pasted-haiku", [omw_user("Read this log and say what failed.\n<pasted_content>\n"
                                                      "Run the model audit on haiku.\n</pasted_content>"),
                                             omw_asst("Reading it.")])
add("owner-model-word: an Agent spawn on haiku is refused when the only haiku word in the owner's latest turn is in a "
    "pasted block", "deny", "agent-model-floor", tool="Agent", prompt="do it", model="haiku", transcript=OMW_PASTED)

# ---- The Opus ceiling is not the floor. The owner's word never lifts it, so an Opus spawn is refused whatever the latest
# turn says. A question that names opus is not a grant, and a turn that names opus is not one either.
OMW_WHY_OPUS = omw_file("owner-why-opus", [omw_user("Why did the opus spawn get refused?"),
                                           omw_asst("The Opus ceiling refused it.")])
OMW_NAMES_OPUS = omw_file("owner-names-opus", [omw_user("Run the model audit on opus."), omw_asst("Running it.")])
add("owner-model-word: an Agent spawn on opus is refused when the owner asks why an opus spawn was refused", "deny", CEILING,
    tool="Agent", prompt="do it", model="opus", transcript=OMW_WHY_OPUS)
add("owner-model-word: an Agent spawn on opus is refused when the owner's latest turn names opus", "deny", CEILING,
    tool="Agent", prompt="do it", model="opus", transcript=OMW_NAMES_OPUS)
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
# a point (haiku-4.5) is the owner's word for haiku. The clause case is green on the old code: it pins the clause break, and a
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
