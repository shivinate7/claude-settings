# section 40900
# The model a lane session starts on, against the lane row of decision agent-model-cap (rule lane-start-settings).
# This section loads after s40805, because the pointer fixture it varies (role_table, role_config, ROLE_TABLE_HEAD,
# ROLE_REAL_CFG) lives there. The lane constants come from s29666 and s30130, and the override helpers from s36421.
# The presence and source_url cases stay in s30130, beside the rule's other cases.
FAMILY = "rule9"

# Model names match by family, as role_model_rank reads them, so `claude-sonnet-5-5` is the sonnet row and `opus`
# is not. The real-table cases pass ROLE_REAL_CFG, so the guard reads this repo's decision file, not a stand-in.
# The fixture cases vary the lane row, so the expectation follows the row the guard reads, never a copied constant.
LANE_OPUS_POINTER = role_table("lanerow-opus", ROLE_TABLE_HEAD + "| lane (decision `session-tiers`) | opus | medium |\n")
LANE_OPUS_CFG = role_config("lanerow-opus", LANE_OPUS_POINTER)


def lane_model_fixture_check():
    """The fixture's lane row reads opus, so the cases on LANE_OPUS_CFG test the row the guard reads."""
    reader = role_model_reader()
    if reader is None:
        return False, "the guard has no role_model_table(root) to read the fixture decision file"
    try:
        table = reader(LANE_OPUS_POINTER) or {}
    except Exception as exc:
        return False, "reading the fixture decision file raised %r" % (exc,)
    if table.get("lane") != "opus":
        return False, "the fixture's lane row reads %r, want 'opus'" % (table.get("lane"),)
    return True, "the fixture's lane row reads opus"


def lane_model_real_row_check():
    """The real decision file's lane row reads sonnet, the model the real-table cases expect. When the row changes,
    this fails first and names the cause: those cases are stale and need re-pointing."""
    reader = role_model_reader()
    if reader is None:
        return False, "the guard has no role_model_table(root) to read the real decision file"
    try:
        table = reader(REPO) or {}
    except Exception as exc:
        return False, "reading the real decision file raised %r" % (exc,)
    if table.get("lane") != "sonnet":
        return False, "the real lane row reads %r, want 'sonnet': the real-table lane cases are stale" % (table.get("lane"),)
    return True, "the real decision file's lane row reads sonnet"


def lane_model_override_case():
    """A lane start on a model its row does not name is refused, and an owner override typed under it lifts the refusal.
    The refusal is not never-lifted: rule agent-model-floor is, and never_lifted reads floor_hit, so a lane-model check
    folded into floor_hit would lose the override."""
    config = role_config("lane-model-override", REPO)
    session = "ov-lane-model"
    tool_input = {"prompt": LANE_PROMPT, "effort": LANE_EFFORT_FIELD, "tags": OWN_LANE_TAGS,
                  "model": "opus", "source_url": LANE_SOURCE_URL}
    call = lambda s: ov_call(LANE_TOOL, tool_input, LANE_REPO, config, session, s)
    problem = ov_want(*call(0), "deny", "lane-start-settings")
    if problem:
        return False, "before the override: " + problem
    note = ov_type(config, session, "override 15m", 30)
    ok, why = ov_story([("under a timed override", lambda: call(60), "allow", "lane-start-settings")], note)
    return ok, why or "refused before the override, lifted under it"


add("lane-start-settings: lane tag with an opus model is denied, under the real decision file", "deny",
    "lane-start-settings", tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD,
    tags=OWN_LANE_TAGS, model="opus", source_url=LANE_SOURCE_URL, config=ROLE_REAL_CFG, carries="model")
add("lane-start-settings: lane tag with a dated opus model name is denied, under the real decision file", "deny",
    "lane-start-settings", tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD,
    tags=OWN_LANE_TAGS, model="claude-opus-5-5", source_url=LANE_SOURCE_URL, config=ROLE_REAL_CFG, carries="model")
add("lane-start-settings: lane tag with an upper-case opus model name is denied, under the real decision file", "deny",
    "lane-start-settings", tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD,
    tags=OWN_LANE_TAGS, model="OPUS", source_url=LANE_SOURCE_URL, config=ROLE_REAL_CFG, carries="model")
add("lane-start-settings: lane tag with a model that names no family of the row is denied", "deny",
    "lane-start-settings", tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD,
    tags=OWN_LANE_TAGS, model="unknown-model-5", source_url=LANE_SOURCE_URL, config=ROLE_REAL_CFG, carries="model")
add("lane-start-settings: lane tag with a dated sonnet model name is allowed, under the real decision file", "allow",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=OWN_LANE_TAGS,
    model="claude-sonnet-5-5", source_url=LANE_SOURCE_URL, config=ROLE_REAL_CFG)
add("lane-start-settings: a create_session with no lane tag on an opus model is allowed, under the real decision file",
    "allow", tool=LANE_TOOL, cwd=LANE_REPO, tags=["cs-build:coordinator"], prompt="do the task", model="opus",
    config=ROLE_REAL_CFG)
add("lane-start-settings: lane tag with an opus model is allowed when the decision's lane row names opus", "allow",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=OWN_LANE_TAGS,
    model="opus", source_url=LANE_SOURCE_URL, config=LANE_OPUS_CFG)
add("lane-start-settings: lane tag with a sonnet model is denied when the decision's lane row names opus", "deny",
    "lane-start-settings", tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD,
    tags=OWN_LANE_TAGS, model="sonnet", source_url=LANE_SOURCE_URL, config=LANE_OPUS_CFG, carries="model")

# LOG_CHECKS_EXTRA joined LOG_CHECKS at the end of s40805, so this section joins its own checks, as s42840 does.
LANE_MODEL_LOG_CHECKS = (
    ("lane-start-settings: the fixture's lane row reads opus", lane_model_fixture_check),
    ("lane-start-settings: the real decision file's lane row reads sonnet", lane_model_real_row_check),
    ("lane-start-settings: an owner override lifts a lane start on a model its row does not name", lane_model_override_case),
)
for _label, _check in LANE_MODEL_LOG_CHECKS:
    LOG_FAMILY[_label] = FAMILY
LOG_CHECKS = LOG_CHECKS + LANE_MODEL_LOG_CHECKS
