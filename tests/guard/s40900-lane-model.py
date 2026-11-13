# section 40900
# The model a lane starts on, against the lane row of decision agent-model-cap (rule lane-start-settings).
# This section loads after s40805, because the pointer fixture it varies (role_table, role_config, ROLE_TABLE_HEAD,
# ROLE_REAL_CFG) lives there. The lane constants come from s29666 and s30130. The presence and source_url cases stay in
# s30130, beside the rule's other cases.
FAMILY = "rule9"

# Model names match by family, as role_model_rank reads them, so `claude-sonnet-5-5` is the sonnet row and `opus` is not.
# The real-table cases pass ROLE_REAL_CFG, so the guard reads this repo's decision file, and they assume its lane row
# reads sonnet: a change to the row shows as a decision mismatch on those cases, which then need re-pointing. The fixture
# cases vary the lane row, so their expectation follows the row the guard reads, never a copied constant.
LANE_OPUS_POINTER = role_table("lanerow-opus", ROLE_TABLE_HEAD + "| lane (decision `session-tiers`) | opus | medium |\n")
LANE_OPUS_CFG = role_config("lanerow-opus", LANE_OPUS_POINTER)

# The fixture must read opus before the cases on LANE_OPUS_CFG mean anything (scope before subject). A broken fixture
# stops the run at setup, as the loader does for a broken section set, and the message says which row read wrong.
_fixture_reader = role_model_reader()
if _fixture_reader is None:
    sys.exit("fixture setup failed: the guard has no role_model_table(root) to read the lane fixture")
_fixture_lane = (_fixture_reader(LANE_OPUS_POINTER) or {}).get("lane")
if _fixture_lane != "opus":
    sys.exit("fixture setup failed: the lane fixture's row reads %r, want 'opus'" % (_fixture_lane,))


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
