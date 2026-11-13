# section 43160
# The lane kinds of decision agent-model-cap (owner ruling own-747-role-layout, 2026-11-13 13:51 CST). A lane's kind comes from
# the marker line in the block of non-blank lines that follows its Grant line: `Guard or check: yes` makes a guard-or-check lane,
# `Docs only: yes` a docs lane, and no marker, or any other line, a product-code-or-design lane. The effort a lane starts at is the
# effort of its kind's row in the record, read from the record and never copied (rule lane-effort-pin). Its model is the model of
# that row (rule lane-start-settings). This section loads after s40805, which gives role_table, role_config and REVIEW_GUARD_MARKER,
# and after s29666, which gives the lane constants. The older single-row layout (one `lane` row) is read only by the fallback cases.
FAMILY = "rule9"  # the cases after this section keep rule 9's family

# The docs-lane marker. The guard-or-check marker is REVIEW_GUARD_MARKER (s40805), the one literal of the review record's line.
DOCS_MARKER = "Docs only: yes"
# A kind marker that is not one: `no` after the colon, so the lane is a product-code-or-design lane.
NOT_A_MARKER = "Guard or check: no"


def lane_kind_table(guard=("sonnet", "high"), product=("sonnet", "medium"), docs=("sonnet", "low")):
    """A decision record whose three lane rows name the given (model, effort) per kind. The rest of the record is the shared
    head (ROLE_TABLE_HEAD, s40805), so a case varies only the lane rows."""
    return ROLE_TABLE_HEAD + (
        "| lane, guard or check | %s | %s |\n"
        "| lane, product code or design | %s | %s |\n"
        "| lane, docs | %s | %s |\n") % (guard + product + docs)


# The owner's layout: guard or check high, product code or design medium, docs low, all on sonnet.
LANE_KIND_CFG = role_config("lanekind-default", role_table("lanekind-default", lane_kind_table()))
# The guard-or-check row names xhigh, so the effort the guard accepts for that kind can only come from this record.
LANE_KIND_XHIGH_CFG = role_config("lanekind-xhigh", role_table("lanekind-xhigh", lane_kind_table(guard=("sonnet", "xhigh"))))
# The product-code row names opus, so the model the lane start accepts for that kind can only come from this record. Only the
# product-code kind is cased here: its effort, medium, is one the pin accepts on main too, so a red case names the model rule and
# no other cause. A guard-or-check or docs lane on main is denied by the effort pin before the model is read.
LANE_KIND_MODEL_CFG = role_config("lanekind-models", role_table("lanekind-models", lane_kind_table(product=("opus", "medium"))))


def lane_brief(marker=None):
    """A lane start's prompt: the Grant line first, then the kind marker line when `marker` is given, then the brief."""
    return "\n".join([LANE_GRANT] + ([marker] if marker else []) + ["Do the task in the brief file."])


def lane_start(name, expected, rule, config, marker, effort, model="sonnet", carries=(), lines=None, tags=OWN_LANE_TAGS):
    """One lane start under `config`: the kind marker in the prompt, the effort field and the model. Allowed when `rule` is None.
    `lines`, when given, replaces the marker: the prompt's lines between the Grant line and the brief's own line, in order."""
    prompt = lane_brief(marker) if lines is None else "\n".join([LANE_GRANT] + lines + ["Do the task in the brief file."])
    add(name, expected, rule, tool=LANE_TOOL, title=LANE_TITLE, cwd=LANE_REPO, tags=tags, prompt=prompt,
        effort=effort, model=model, source_url=LANE_SOURCE_URL, config=config, carries=carries)


# A `Lane brief:` line is judged by lane-one-topic: a start that holds one carries the lane's cs-topic tag and names that topic
# (the form of the lane-one-topic controls in s29666). The brief template puts it on the line after the Grant line.
TOPIC_BRIEF = "Lane brief: icon-a. Topic: alpha."
TOPIC_TAGS = OWN_LANE_TAGS + ["cs-topic:alpha"]


# ---- Lane effort pin, by kind. The effort the pin accepts is the effort of the lane's kind's row.
lane_start("lane-effort-pin: a guard-or-check lane at effort high is allowed under the kind table", "allow", None,
           LANE_KIND_CFG, REVIEW_GUARD_MARKER, "high")
lane_start("lane-effort-pin: a guard-or-check lane at effort medium is denied under the kind table", "deny",
           "lane-effort-pin", LANE_KIND_CFG, REVIEW_GUARD_MARKER, "medium")
lane_start("lane-effort-pin: a guard-or-check lane at effort low is denied under the kind table", "deny",
           "lane-effort-pin", LANE_KIND_CFG, REVIEW_GUARD_MARKER, "low")
lane_start("lane-effort-pin: a docs lane at effort low is allowed under the kind table", "allow", None,
           LANE_KIND_CFG, DOCS_MARKER, "low")
lane_start("lane-effort-pin: a docs lane at effort medium is denied under the kind table", "deny",
           "lane-effort-pin", LANE_KIND_CFG, DOCS_MARKER, "medium")
lane_start("lane-effort-pin: a lane with no kind marker at effort medium is allowed under the kind table", "allow", None,
           LANE_KIND_CFG, None, "medium")
lane_start("lane-effort-pin: a lane with no kind marker at effort high is denied under the kind table", "deny",
           "lane-effort-pin", LANE_KIND_CFG, None, "high")
lane_start("lane-effort-pin: a lane with no kind marker at effort low is denied under the kind table", "deny",
           "lane-effort-pin", LANE_KIND_CFG, None, "low")
lane_start("lane-effort-pin: a `Guard or check: no` line is no kind marker, so the lane takes the product-code effort", "allow",
           None, LANE_KIND_CFG, NOT_A_MARKER, "medium")
lane_start("lane-effort-pin: a guard-or-check lane at effort xhigh is allowed when its kind's row names xhigh", "allow", None,
           LANE_KIND_XHIGH_CFG, REVIEW_GUARD_MARKER, "xhigh")
lane_start("lane-effort-pin: a guard-or-check lane at effort high is denied when its kind's row names xhigh", "deny",
           "lane-effort-pin", LANE_KIND_XHIGH_CFG, REVIEW_GUARD_MARKER, "high")

# ---- Lane start settings, by kind. The model the lane start accepts is the model of the lane's kind's row.
lane_start("lane-start-settings: a product-code lane on opus is allowed when its kind's row names opus", "allow", None,
           LANE_KIND_MODEL_CFG, None, "medium", model="opus")
lane_start("lane-start-settings: a product-code lane on sonnet is denied when its kind's row names opus", "deny",
           "lane-start-settings", LANE_KIND_MODEL_CFG, None, "medium", model="sonnet", carries="model")
lane_start("lane-start-settings: a product-code lane on opus is denied when its kind's row names sonnet", "deny",
           "lane-start-settings", LANE_KIND_CFG, None, "medium", model="opus", carries="model")


# ---- The kind marker is read from the block of non-blank lines after the Grant line, not from the second non-blank line alone.
# The brief template puts `Lane brief:` on the line after Grant, so the marker is then the third line. A blank line ends the block,
# so a marker past one is outside it and is read by no one.
SINGLE_ROW_POINTER = role_table("lanekind-single-row", ROLE_TABLE_HEAD + "| lane | sonnet | medium |\n")
SINGLE_ROW_CFG = role_config("lanekind-single-row", SINGLE_ROW_POINTER)
# The fallback efforts are the guard's LANE_KIND_FALLBACK, so the fallback cases expect the value the guard falls back to.
LANE_FALLBACK = _load_guard_module().LANE_KIND_FALLBACK


def single_row_fixture_check():
    """Scope before subject: the single-row record holds one `lane` row and no kind row, so the fallback cases below read
    the fallback and not a kind row."""
    path = os.path.join(SINGLE_ROW_POINTER, "docs", "decisions", "agent-model-cap.md")
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    kind_rows = [label for label in _load_guard_module().LANE_KIND_LABELS.values() if label in text]
    return ("| lane | sonnet | medium |" in text and not kind_rows), "the single-row record names a kind row: %r" % (kind_rows,)


_SINGLE_ROW_FIXTURE_LABEL = "lane-kind-fixture: the single-row record holds one lane row and no kind row"
LOG_FAMILY[_SINGLE_ROW_FIXTURE_LABEL] = "rule9"
LOG_CHECKS = LOG_CHECKS + ((_SINGLE_ROW_FIXTURE_LABEL, single_row_fixture_check),)

# A Lane brief line first in the block, then the marker: the marker is read at the third line.
lane_start("lane-effort-pin: a guard-or-check lane with a Lane brief line before its marker is allowed at effort high", "allow",
           None, LANE_KIND_CFG, None, "high", lines=[TOPIC_BRIEF, REVIEW_GUARD_MARKER], tags=TOPIC_TAGS)
lane_start("lane-effort-pin: a guard-or-check lane with a Lane brief line before its marker is denied at effort medium", "deny",
           "lane-effort-pin", LANE_KIND_CFG, None, "medium", lines=[TOPIC_BRIEF, REVIEW_GUARD_MARKER], tags=TOPIC_TAGS)
lane_start("lane-effort-pin: a docs lane with a Lane brief line before its marker is allowed at effort low", "allow",
           None, LANE_KIND_CFG, None, "low", lines=[TOPIC_BRIEF, DOCS_MARKER], tags=TOPIC_TAGS)
lane_start("lane-effort-pin: a docs lane with a Lane brief line before its marker is denied at effort medium", "deny",
           "lane-effort-pin", LANE_KIND_CFG, None, "medium", lines=[TOPIC_BRIEF, DOCS_MARKER], tags=TOPIC_TAGS)
# The marker is any non-blank line of the block, not only the second: a preamble line sits between the brief and the marker.
lane_start("lane-effort-pin: a guard-or-check marker past a preamble line in the block is read, so effort high is allowed", "allow",
           None, LANE_KIND_CFG, None, "high", lines=[TOPIC_BRIEF, "Read the brief file first.", REVIEW_GUARD_MARKER],
           tags=TOPIC_TAGS)
# A blank line after the Grant line ends the block: the marker past it is not read, so the lane is a product lane.
lane_start("lane-effort-pin: a guard-or-check marker past a blank line is not read, so effort high is denied", "deny",
           "lane-effort-pin", LANE_KIND_CFG, None, "high", lines=["", REVIEW_GUARD_MARKER])
lane_start("lane-effort-pin: a guard-or-check marker past a blank line is not read, so effort medium is allowed", "allow",
           None, LANE_KIND_CFG, None, "medium", lines=["", REVIEW_GUARD_MARKER])
# Control: a blank line after the Lane brief line ends the block, so the marker past it is not read and effort medium holds.
lane_start("lane-effort-pin: a guard-or-check marker past a blank line after a Lane brief line is not read, at effort medium",
           "allow", None, LANE_KIND_CFG, None, "medium", lines=[TOPIC_BRIEF, "", REVIEW_GUARD_MARKER], tags=TOPIC_TAGS)
# Under an unreadable record, and under the single-row record, a lane starts at the fallback effort of its kind.
lane_start("lane-effort-pin: an unreadable record gives a guard-or-check lane the fallback effort, so effort high is allowed", "allow",
           None, ROLE_UNREADABLE_CFG, None, LANE_FALLBACK["guard"][1], lines=[TOPIC_BRIEF, REVIEW_GUARD_MARKER], tags=TOPIC_TAGS)
lane_start("lane-effort-pin: an unreadable record gives a guard-or-check lane the fallback effort, so product effort is denied",
           "deny", "lane-effort-pin", ROLE_UNREADABLE_CFG, None, LANE_FALLBACK["product"][1], lines=[TOPIC_BRIEF, REVIEW_GUARD_MARKER],
           tags=TOPIC_TAGS)
lane_start("lane-effort-pin: the single-row record gives a guard-or-check lane the fallback effort, so effort high is allowed", "allow",
           None, SINGLE_ROW_CFG, None, LANE_FALLBACK["guard"][1], lines=[TOPIC_BRIEF, REVIEW_GUARD_MARKER], tags=TOPIC_TAGS)
lane_start("lane-effort-pin: the single-row record gives a docs lane the fallback effort, so effort low is allowed", "allow",
           None, SINGLE_ROW_CFG, None, LANE_FALLBACK["docs"][1], lines=[TOPIC_BRIEF, DOCS_MARKER], tags=TOPIC_TAGS)
lane_start("lane-effort-pin: the single-row record gives a product lane the fallback effort, so effort medium is allowed", "allow",
           None, SINGLE_ROW_CFG, None, LANE_FALLBACK["product"][1], lines=[TOPIC_BRIEF], tags=TOPIC_TAGS)


# ---- The design reviewer runs Sonnet high and the designer stays Opus high (owner ruling own-756-design-reviewer-sonnet,
# 2026-11-13 14:01 CST). The guard's Opus allowance for the design reviewer is the OPUS_STANDING_ROLES list, which must follow the
# table: the three role lists agree with the table (role_list_drift), and an Opus spawn of the design reviewer passes only when its
# row names opus. role_list_table and role_list_pointer (s40805) build the fixtures, so each case varies one row.
DR_SONNET_POINTER = role_list_pointer("dr-sonnet", role_list_table(models={"design-reviewer": "sonnet"}))
DR_SONNET_CFG = role_config("dr-sonnet", DR_SONNET_POINTER)
# The design reviewer moved to a sonnet row (own-756), so the opus-row pointer names it explicitly: the drift case below reads it.
DR_OPUS_POINTER = role_list_pointer("dr-opus", role_list_table(models={"design-reviewer": "opus"}))

# An Opus spawn of the design reviewer is refused under agent-model-cap, the rule it really hits: its row names sonnet
# and the Opus ceiling has no standing grant for it. No row can lift that, so this is an override refusal, not the row's.
role_opus_refuse("agent-model-cap: a design-reviewer spawn on opus is refused when its row names sonnet", "design-reviewer",
                 "opus", "Review the screen.", config=DR_SONNET_CFG)
role_model_allow("agent-role-model: a design-reviewer spawn on sonnet is allowed when its row names sonnet", "design-reviewer",
                 "sonnet", "Review the screen.", config=DR_SONNET_CFG)
role_model_allow("agent-role-model: a designer spawn on opus stays allowed when the design reviewer's row names sonnet", "designer",
                 "opus", "Design the screen.", config=DR_SONNET_CFG)


def design_reviewer_sonnet_drift_check():
    """The three role lists agree with the table when the design reviewer's row names sonnet: no drift line for it."""
    return role_drift_clean_check(DR_SONNET_POINTER, "the design reviewer on a sonnet row")


def design_reviewer_opus_drift_check():
    """The design reviewer on an opus row drifts OPUS_STANDING_ROLES, which lacks it: the lists follow the table."""
    return role_drift_names_check(DR_OPUS_POINTER, ("design-reviewer", "OPUS_STANDING_ROLES"),
                                  "the design reviewer on an opus row")


# ---- The builder row (owner ruling own-755-a-builder-by-kind, 2026-11-13 14:01 CST): model sonnet, effort follows the lane kind,
# high in guard or check lanes and medium in product, design and docs lanes. Nothing in the guard reads the builder row's effort
# today (the guard reads the model word of each row, and the round rows, and a spawn's effort is not judged), so the effort is
# checked as the record's text. The model is checked through the guard's table reader.
BUILDER_EFFORT_WORDS = ("high", "medium", "guard or check", "product", "design", "docs")


def builder_row_cells():
    """The cells of the record's `builder` row (backticks removed), or None when the record has none. Only the row whose first
    cell is exactly `builder` counts: `builder, try 3 ...` and the round row `builder | 3` are other rows."""
    with open(os.path.join(REPO, "docs", "decisions", "agent-model-cap.md"), encoding="utf-8") as handle:
        for line in handle.read().splitlines():
            if not line.strip().startswith("|"):
                continue
            cells = [cell.strip().replace("`", "") for cell in line.strip().strip("|").split("|")]
            if len(cells) >= 3 and cells[0].lower() == "builder":
                return cells
    return None


def builder_model_check():
    """The builder row names sonnet, read through the guard's own table reader (role_model_table, s40805's role_model_reader)."""
    reader = role_model_reader()
    if reader is None:
        return False, "the guard has no role_model_table(root) to read the builder row"
    word = (reader(REPO) or {}).get("builder")
    return word == "sonnet", "the builder row names model %r, want 'sonnet'" % (word,)


def builder_effort_check():
    """The builder row's effort cell names high for guard or check lanes and medium for product, design and docs lanes."""
    cells = builder_row_cells()
    if cells is None:
        return False, "the record has no `builder` row"
    cell = cells[2].lower()
    missing = [word for word in BUILDER_EFFORT_WORDS if word not in cell]
    return not missing, "the builder row's effort cell %r does not name %s" % (cells[2], ", ".join(missing) or "the kinds")


ROLE_ROW_LABEL_KEYS = ("lane, guard or check", "lane, product code or design", "lane, docs", "batch runner")


def role_table_rows_check():
    """The role table reads each lane row and the batch runner row whole, under its full label, and splits no lane label
    into a role of its own (`lane`): ROLE_ROW_LABELS is what keeps a comma inside a label from splitting it."""
    reader = role_model_reader()
    if reader is None:
        return False, "the guard has no role_model_table(root) to read the record"
    table = reader(REPO) or {}
    missing = [key for key in ROLE_ROW_LABEL_KEYS if table.get(key) != "sonnet"]
    if missing:
        return False, "the role table does not read %s whole as a sonnet row: %r" % (", ".join(missing), sorted(table))
    if "lane" in table:
        return False, "the role table splits a lane label into a role named 'lane': %r" % (sorted(table),)
    return True, "the role table reads the three lane rows and the batch runner row whole, as sonnet"


for _label, _check in (
        ("role-model: the role table reads the lane rows and the batch runner row whole, and splits no lane label",
         role_table_rows_check),
        ("role-model: the design reviewer on a sonnet row adds no drift line, so the Opus allowance follows the table",
         design_reviewer_sonnet_drift_check),
        ("role-model: the design reviewer on an opus row drifts OPUS_STANDING_ROLES, so the lists follow the table",
         design_reviewer_opus_drift_check),
        ("role-model: the builder row names sonnet, read through the guard's table reader", builder_model_check),
        ("role-model: the builder row's effort follows the lane kind in the record's text", builder_effort_check),
):
    LOG_FAMILY[_label] = "role-model"
    LOG_CHECKS = LOG_CHECKS + ((_label, _check),)


# ---- Reviewer round 3 runs Sonnet high, and Opus is never an option and never prompts (owner ruling own-r3-reviewer-sonnet-high,
# 2026-11-13 14:05 CST). The round row is the record's `reviewer | 3` row. A reviewer spawn on Opus in round 3 is refused by the
# agent-role-model rule with the remedy `use sonnet`, and that refusal names no override. The round marker is the brief's first line.
R3_POINTER = role_table("r3-sonnet-high", ROLE_TABLE_RULES + "\n" + ROUND_TABLE_HEAD + "| reviewer | 3 | sonnet | high |\n")
R3_CFG = role_config("r3-sonnet-high", R3_POINTER)
R3_BRIEF = "Round 3 of 3\nReview the diff for the guard change."


def r3_fixture_check():
    """Scope before subject: the round fixture reads reviewer round 3 as sonnet, through the guard's round-table reader."""
    rounds = _load_guard_module().role_round_table(R3_POINTER)
    word = (rounds or {}).get(("reviewer", "3", "other"))
    return word == "sonnet", "the round fixture reads reviewer round 3 as %r, want 'sonnet'" % (word,)


_R3_FIXTURE_LABEL = "role-model: the round fixture reads reviewer round 3 as sonnet, so the round cases below mean what they say"
LOG_FAMILY[_R3_FIXTURE_LABEL] = "role-model"
LOG_CHECKS = LOG_CHECKS + ((_R3_FIXTURE_LABEL, r3_fixture_check),)

add("agent-role-model: a reviewer spawn on opus in round 3 is refused with the remedy use sonnet, and names no override", "deny",
    "agent-role-model", tool="Agent", config=R3_CFG, subagent_type="reviewer", model="opus", prompt=R3_BRIEF,
    carries=("use sonnet",), lacks=("override",))
add("agent-role-model: a reviewer spawn on sonnet in round 3 is allowed when its round row names sonnet high", "allow",
    tool="Agent", config=R3_CFG, subagent_type="reviewer", model="sonnet", prompt=R3_BRIEF)
