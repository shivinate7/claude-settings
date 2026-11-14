# section 40805
FAMILY = "role-model"
ROLE_RULE = "agent-role-model"
ROLE_REMEDY = "drop the model field, or name the role's model"
ROLE_DEFAULT_REMEDY = "name the role's model (sonnet)"
# A refusal for this rule names its remedy and no other target: not the table, not the agents folder.
ROLE_LACKS = ("docs/decisions", "agent-model-cap.md", "agents/")
# A reviewer's refusal also names the `Round N of 3` marker and the rounds that allow it. Those rounds are read from
# the guard under test (ROLE_REVIEWER_FREE_ROUNDS), never copied here. A refusal for any other role names neither.
ROUND_MARKER = "Round N of 3"
FREE_ROUND_MARKERS = tuple("Round %s of 3" % n for n in _load_guard_module().ROLE_REVIEWER_FREE_ROUNDS)
# The sentence a reviewer's refusal says about the first round and the test-author, as a literal (never the guard's text).
ROUND_ONE_SENTENCE = "round 1 and the test-author run on their role's model"
# The first-line form a fix check on a later round names: the round marker, then the fix check words.
ROUND_FIX_FORM = "Round N of 3 (fix check)"
# The Explore audit marker (shiv, Nov 1 11:43 CST, page item 107, pick a). A literal, not the guard's EXPLORE_AUDIT_MARKER:
# that constant is new, and a read at import time would fail every case on the old code.
EXPLORE_MARKER = "Audit:"
UNSET_DEFAULT = {"CLAUDE_CODE_SUBAGENT_MODEL": None}
EMPTY_DEFAULT = {"CLAUDE_CODE_SUBAGENT_MODEL": ""}
SONNET_DEFAULT = {"CLAUDE_CODE_SUBAGENT_MODEL": "sonnet"}

ROLE_TABLE_HEAD = "# Agent model cap\n\n| Point | Model | Effort |\n|---|---|---|\n"
ROLE_TABLE_TEST_AUTHOR_HAIKU = ROLE_TABLE_HEAD + "| test-author | haiku | xhigh |\n"
ROLE_TABLE_TEST_AUTHOR_SONNET = ROLE_TABLE_HEAD + "| test-author | sonnet | high |\n"
# The qualifier rows (`reviewer, rounds 2 and 3`, `builder, try 3 after`, `... that audits`) name no role.
ROLE_TABLE_RULES = ROLE_TABLE_HEAD + (
    "| Explore, claude-code-guide | haiku | xhigh |\n"
    "| Explore that audits or judges meaning, not a plain search | sonnet, when its brief's first non-blank line "
    "carries the `Audit:` marker; or opus on the owner's grant (2026-10-21 ruling, class level); set per spawn, "
    "which overrides the frontmatter `haiku` | high |\n"
    "| test-author | haiku | xhigh |\n"
    "| reviewer | haiku | xhigh |\n"
    "| reviewer, rounds 2 and 3 | sonnet, the ceiling | high |\n"
    "| builder | sonnet | high |\n"
    "| builder, try 3 after a FAIL at review round 2 | opus | high |\n"
    "| `planner` (`agents/planner.md`) | sonnet | high |\n"
    "| general-purpose, `claude` | sonnet, by the default | model default |\n")
ROLE_RULES_WANT = {"Explore": "haiku", "claude-code-guide": "haiku", "test-author": "haiku",
                   "reviewer": "haiku", "builder": "sonnet", "planner": "sonnet",
                   "general-purpose": "sonnet", "claude": "sonnet"}
# The refuter role is read-only and runs Opus by its own standing grant (decision plan-refuter). Its name is
# guard_core's REFUTER_ROLE, the one home of the name, read here and never typed. A guard_core with no such name
# reads as REFUTER_MISSING: a spawn of that name is then refused as a role with no grant, and refuter_name_check
# fails on the missing name itself (the same reading as the PowerShellScript cases).
REFUTER_MISSING = "<no REFUTER_ROLE in guard_core>"
_load_guard_module()  # sets sys.modules["guard_core"] for the read below
REFUTER = getattr(sys.modules["guard_core"], "REFUTER_ROLE", REFUTER_MISSING)


def refuter_name_check():
    """guard_core names the refuter role in REFUTER_ROLE, a non-empty string. Every refuter case reads that name
    from guard_core, so a guard_core without it fails this check and says so."""
    if REFUTER == REFUTER_MISSING:
        return False, "guard_core has no REFUTER_ROLE, the one home of the refuter role's name"
    if not isinstance(REFUTER, str) or not REFUTER.strip():
        return False, "guard_core.REFUTER_ROLE is %r, want a non-empty name" % (REFUTER,)
    return True, "guard_core.REFUTER_ROLE names the refuter role"


# The owner's real decision file: each role, with the first word of its Model cell.
ROLE_REAL_WANT = {"Explore": "haiku", "claude-code-guide": "haiku", "test-author": "haiku",
                  "reviewer": "haiku", "record-writer": "haiku", "builder": "sonnet", "Plan": "opus",
                  "designer": "opus", "design-reviewer": "opus", REFUTER: "opus", "general-purpose": "sonnet",
                  "claude": "sonnet"}
# Bytes that are not text, so no reader can take the decision file as a table.
ROLE_TABLE_UNREADABLE = b"# Agent model cap\n\xff\xfe\x80 not text\n"


def role_table(name, table=None, agents=(), files=None):
    """A pointer checkout under this run's folder, and its decision file when `table` is given: text,
    or bytes that are not text. Each name in `agents` gets an agents/ file whose frontmatter `name` is
    that name, so the guard reads it as a real role. `files` maps each agents/ file name to its body:
    text, or bytes that are not text, for a case that needs an exact file. Returns the checkout's folder."""
    pointer = os.path.join(ROOT, "rolepointer", name)
    os.makedirs(pointer, exist_ok=True)
    if table is not None:
        path = os.path.join(pointer, "docs", "decisions", "agent-model-cap.md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(table if isinstance(table, bytes) else table.encode("utf-8"))
    for role in agents:
        write(os.path.join(pointer, "agents", role.lower() + ".md"), "---\nname: %s\n---\n# %s\n" % (role, role))
    for file_name, body in (files or {}).items():
        path = os.path.join(pointer, "agents", file_name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(body if isinstance(body, bytes) else body.encode("utf-8"))
    return pointer


def role_config(name, pointer):
    """A config folder whose global rules name the pointer checkout `pointer`, by its `@<path>/CLAUDE.md` line."""
    config = os.path.join(ROOT, "rolecfg", name)
    write(os.path.join(config, "CLAUDE.md"), "@%s/CLAUDE.md\n" % slash(pointer))
    return config


ROLE_REAL_CFG = role_config("real", REPO)
ROLE_MISSING_CFG = role_config("missing", role_table("missing"))
ROLE_UNREADABLE_CFG = role_config("unreadable", role_table("unreadable", ROLE_TABLE_UNREADABLE))
ROLE_LIVE_POINTER = role_table("live", ROLE_TABLE_TEST_AUTHOR_HAIKU)
ROLE_LIVE_CFG = role_config("live", ROLE_LIVE_POINTER)
ROLE_RULES_POINTER = role_table("rules", ROLE_TABLE_RULES)
# The repository's builder pins sonnet, so a case that needs a builder with no model pin reads this fixture folder.
ROLE_UNPINNED_POINTER = role_table("unpinned", ROLE_TABLE_RULES, agents=("builder",))
ROLE_UNPINNED_CFG = role_config("unpinned", ROLE_UNPINNED_POINTER)


def role_input(role, model, prompt):
    """A spawn's tool input. `role` and `model` are left out when they are None."""
    spawn = {"prompt": prompt}
    if role is not None:
        spawn["subagent_type"] = role
    if model is not None:
        spawn["model"] = model
    return spawn


def role_spawn(config, spawn, tool="Agent", env=None):
    """Judge one spawn under `config`, as decide() judges a case, and return (decision, reason)."""
    return decide({"raw": None, "tool": tool, "tool_input": spawn, "cwd": None, "session": None,
                   "env_path": None, "config": config, "env": env, "transcript": None, "agent_id": None,
                   "agent_type": None, "event": None, "stop_active": False, "no_root": False,
                   "max_seconds": None, "temp": None, "process_cwd": None})


def role_model_refuse(name, role, model, prompt, tool="Agent", config=ROLE_REAL_CFG, carries=(ROLE_REMEDY,),
                      lacks=ROLE_LACKS, env=None):
    add(name, "deny", ROLE_RULE, tool=tool, config=config, env=env, carries=carries, lacks=lacks,
        **role_input(role, model, prompt))


def role_model_allow(name, role, model, prompt, tool="Agent", config=ROLE_REAL_CFG, env=None):
    add(name, "allow", tool=tool, config=config, env=env, **role_input(role, model, prompt))


def role_opus_refuse(name, role, model, prompt, tool="Agent", config=ROLE_REAL_CFG):
    """An Opus spawn above its row is refused under agent-model-cap, not this rule. An owner override lifts it,
    so the case is not never-lifted."""
    add(name, "deny", "agent-model-cap", tool=tool, config=config, lacks=(ROLE_RULE,),
        **role_input(role, model, prompt))


# ---- B: a model above its role's row is denied. The reason holds the remedy and no other target.
role_model_refuse("role-model: test-author on sonnet is denied", "test-author", "sonnet",
          "Write the failing cases.")
role_model_refuse("role-model: the same spawn as a Task is denied", "test-author", "sonnet",
          "Write the failing cases.", tool="Task")
role_model_refuse("role-model: reviewer on sonnet with no round line is denied, and names the Round N of 3 marker",
          "reviewer", "sonnet", "Check the diff for typos.",
          carries=(ROLE_REMEDY, ROUND_MARKER) + FREE_ROUND_MARKERS)
# The marker is a reviewer's remedy only: a test-author whose brief opens with a round line is still denied, and its
# refusal names no round marker, so no agent reads one as a way past its row.
role_model_refuse("role-model: test-author on sonnet with a Round 2 of 3 line is denied and names no round marker",
          "test-author", "sonnet", "Round 2 of 3. Write the failing cases.",
          lacks=ROLE_LACKS + (ROUND_MARKER,) + FREE_ROUND_MARKERS)
role_model_refuse("role-model: reviewer on sonnet with a Round 1 of 3 line is denied (round 1 runs on the row)",
          "reviewer", "sonnet", "Round 1 of 3. Check the diff for typos.",
          carries=(ROLE_REMEDY, ROUND_MARKER) + FREE_ROUND_MARKERS)
role_model_refuse("role-model: record-writer on sonnet is denied", "record-writer", "sonnet", "Record the decision.")
role_model_refuse("role-model: claude-code-guide on sonnet is denied", "claude-code-guide", "sonnet",
          "How do the hooks load?")
role_model_refuse("role-model: test-author on the full sonnet id is denied", "test-author", "claude-sonnet-5-5",
          "Write the failing cases.")
# A model the table does not rank is above any row below opus: fail closed. Its rank is unruled, so none is guessed.
role_model_refuse("role-model: fable on builder is denied, a model the table does not rank fails closed",
          "builder", "fable", "Fix the failing case.")
role_model_refuse("role-model: fable on test-author is denied, a model the table does not rank fails closed",
          "test-author", "fable", "Write the failing cases.")
role_model_refuse("role-model: claude-fable-5-1 on reviewer with no round line is denied, fails closed",
          "reviewer", "claude-fable-5-1", "Check the diff for typos.")
# A role written with a capital letter or a trailing space is the same role, so it takes its row.
role_model_refuse("role-model: role Test-author on sonnet is denied, matched to its row",
          "Test-author", "sonnet", "Write the failing cases.")
role_model_refuse("role-model: role with a trailing space on sonnet is denied, matched to its row",
          "test-author ", "sonnet", "Write the failing cases.")
role_model_refuse("role-model: role Reviewer on sonnet with no round line is denied, matched to its row",
          "Reviewer", "sonnet", "Check the diff for typos.")

# ---- B2: an Explore on Sonnet is denied unless the first `Audit:` on the brief's first non-blank line counts,
# with any text ahead of it (case-sensitive). Shiv's ruling: Nov 1 11:43 CST, page item 107, pick a.
role_model_refuse("role-model: Explore on sonnet with no marker is denied, and names the Audit: marker",
          "Explore", "sonnet", "Find where X is defined.", carries=(EXPLORE_MARKER,))
role_model_refuse("role-model: Explore on sonnet with Audit: on line 2 is denied (line 1 only counts)",
          "Explore", "sonnet", "Find where X is defined.\nAudit: check the glossary for meaning drift.",
          carries=(EXPLORE_MARKER,))
# Re-pointed from an allow case (shiv, Nov 1 11:43 CST, page item 107, pick a): plain prose on line 1 is not the marker.
role_model_refuse("role-model: Explore on sonnet whose first line is plain prose is denied",
          "Explore", "sonnet", "Audit the glossary for meaning drift.", carries=(EXPLORE_MARKER,))
role_model_refuse("role-model: Explore on sonnet with lowercase audit: on line 1 is denied (case-sensitive)",
          "Explore", "sonnet", "audit: check the glossary for meaning drift.", carries=(EXPLORE_MARKER,))
# The marker lifts only a Sonnet Explore. A model the table does not rank is still refused, and its reason names no
# marker.
role_model_refuse("role-model: Explore on fable with Audit: on line 1 is denied, reason names no marker",
          "Explore", "fable", "Audit: check the glossary for meaning drift.", lacks=ROLE_LACKS + (EXPLORE_MARKER,))

# ---- C: at or below the row passes. An Opus spawn above its row is refused under agent-model-cap (rule 9d).
# An Explore on Sonnet passes when the first `Audit:` on the brief's first non-blank line counts, with any text ahead
# of it. An Explore on Haiku or Opus passes with no marker. (shiv, Nov 1 11:43 CST, page item 107, pick a)
role_model_allow("role-model: Explore on sonnet with Audit: on line 1 is allowed", "Explore", "sonnet",
           "Audit: check the glossary for meaning drift.")
role_model_allow("role-model: Explore on sonnet with **Audit:** on line 1 is allowed (markup ahead of the marker)",
           "Explore", "sonnet", "**Audit:** check the glossary for meaning drift.")
role_model_allow("role-model: Explore on sonnet with prose ahead of Audit: on line 1 is allowed", "Explore", "sonnet",
           "Please read the Audit: docs section.")
role_model_allow("role-model: Explore on haiku is allowed, with no marker", "Explore", "haiku",
           "Find where X is defined.")
# An Explore on Opus is refused with no Audit: marker; the marker is its standing grant (item 137 pick a).
role_opus_refuse("role-model: Explore on opus with no marker is denied under agent-model-cap (item 137)", "Explore", "opus",
               "Find where X is defined.")
role_model_allow("role-model: Explore on opus with Audit: on line one is allowed (item 137)", "Explore", "opus",
           "Audit: check the glossary for meaning drift.")
# The Explore role matches with no regard to case or padding (role_model_check), so the Audit: grant on Opus must too.
role_model_allow("role-model: explore in lowercase on opus with Audit: on line one is allowed", "explore", "opus",
           "Audit: check X")
role_model_allow("role-model: Explore padded with spaces on opus with Audit: on line one is allowed", " Explore ", "opus",
           "Audit: check X")
role_model_allow("role-model: reviewer on sonnet with a Round 2 of 3 line is allowed", "reviewer", "sonnet",
           "Round 2 of 3. Re-check the diff.")
role_model_allow("role-model: reviewer on sonnet with a Round 3 of 3 line is allowed", "reviewer", "sonnet",
           "Round 3 of 3. Re-check the diff.")
# The row reads a round line on line three too: the same scan the step-up reads.
role_model_allow("role-model: reviewer on sonnet with a Round 2 of 3 line three is allowed", "reviewer", "sonnet",
           "Check the diff.\nThe lane is c204.\nRound 2 of 3. Re-check the diff.")
role_model_allow("role-model: builder on sonnet with no round line is allowed", "builder", "sonnet",
           "Fix the failing case.")
role_model_allow("role-model: designer on opus is allowed (standing grant)", "designer", "opus",
           "Draw the mockup.")
role_model_allow("role-model: a role not in the table on sonnet is allowed", "scout", "sonnet", "Look around.")
role_model_allow("role-model: test-author on haiku is allowed (its own row)", "test-author", "haiku",
           "Write the failing cases.")
role_model_allow("role-model: test-author on the full haiku id is allowed", "test-author", "claude-haiku-5-5",
           "Write the failing cases.")
role_model_allow("role-model: Plan on sonnet is allowed (below its row)", "Plan", "sonnet", "Plan the change.")
role_model_allow("role-model: general-purpose on sonnet is allowed", "general-purpose", "sonnet", "Find the file.")
role_model_allow("role-model: claude on sonnet is allowed", "claude", "sonnet", "Find the file.")
role_model_allow("role-model: claude-code-guide on haiku is allowed", "claude-code-guide", "haiku",
           "How do the hooks load?")
role_opus_refuse("role-model: builder on opus with no round line is denied under agent-model-cap, not this rule",
               "builder", "opus", "Fix the failing case.")
role_opus_refuse("role-model: general-purpose on opus is denied under agent-model-cap, not this rule",
               "general-purpose", "opus", "Find the file.")
role_opus_refuse("role-model: test-author on opus is denied under agent-model-cap, not this rule",
               "test-author", "opus", "Write the failing cases.")
# A role with no row has no grant, so the Opus ceiling refuses it, and says so rather than asking (item 127 pick a).
role_opus_refuse("role-model: a role with no row on opus is denied under agent-model-cap, not asked (item 127)",
               "scout", "opus", "Look around.")
role_opus_refuse("role-model: reviewer on opus with Round 3 of 3 is denied under agent-model-cap (item 127)",
               "reviewer", "opus", "Round 3 of 3. Re-check the diff.")
# Standing grants stay allowed on Opus (rule 9d): Plan, the design reviewer, the refuter, and a builder's third round.
role_model_allow("role-model: Plan on opus is allowed (standing grant)", "Plan", "opus", "Plan the change.")
role_model_allow("role-model: design-reviewer on opus is allowed (standing grant)", "design-reviewer", "opus",
                 "Review the mockup.")
role_model_allow("role-model: builder on opus with Round 3 of 3 is allowed (standing grant)", "builder", "opus",
                 "Round 3 of 3. Finish the fix.")
# The refuter's grant (page item 279, pick d): an Agent or Task spawn on Opus is allowed. Failure class: a false deny,
# the spawn refused above its row, and a false allow, a reviewer or a near-miss name given the grant (the controls below).
for _tool, _model in (("Agent", "opus"), ("Task", "claude-opus-5-5")):
    role_model_allow("role-model: %s refuter on %s is allowed (standing grant)" % (_tool, _model), REFUTER, _model,
                     "Refute the plan.", tool=_tool)
# Controls, green on the old code too: a reviewer on Opus stays refused, and a near-miss of the role name earns no grant.
role_opus_refuse("role-model: reviewer on opus with no round line is still denied (the refuter grant is not a reviewer's)",
                 "reviewer", "opus", "Check the diff for typos.")
for _near in (REFUTER + "s", REFUTER.title()):
    role_opus_refuse("role-model: a near-miss of the refuter role, %s, on opus is denied (no standing grant)" % _near,
                     _near, "opus", "Refute the plan.")

# ---- H: a Workflow agent() call faces the role row and the Opus ceiling, as an Agent spawn does (decision agent-model-cap).
# The guard reads each agent() call in the script and judges its agentType and model as an Agent spawn is judged: the
# Opus ceiling (agent-model-cap) and the role row (agent-role-model). The Audit: marker counts on the brief's first line
# only. Failure classes: a false allow (an above-row agent() call in a script passes); a false deny (a comment, a string
# or a template literal hides the brief or the model, or the marker is read past line 1).
def workflow_refuse(name, script, rule="agent-model-cap", carries=(), lacks=()):
    """A Workflow script whose agent() call is above its role's row: denied under `rule`."""
    add(name, "deny", rule, tool="Workflow", config=ROLE_REAL_CFG, carries=carries, lacks=lacks, script=script)


def workflow_allow(name, script):
    add(name, "allow", tool="Workflow", config=ROLE_REAL_CFG, script=script)


workflow_refuse("role-model: Workflow builder on opus with no round line is denied under agent-model-cap",
                _step_flow("'Fix the failing case.'", "agentType: 'builder', model: 'opus'"))
workflow_refuse("role-model: Workflow Explore on opus with no marker is denied under agent-model-cap",
                _step_flow("'Find where X is defined.'", "agentType: 'Explore', model: 'opus'"))
workflow_refuse("role-model: Workflow Explore on sonnet with no marker is denied under agent-role-model",
                _step_flow("'Find where X is defined.'", "agentType: 'Explore', model: 'sonnet'"),
                rule=ROLE_RULE, carries=(ROLE_REMEDY, EXPLORE_MARKER), lacks=ROLE_LACKS)
workflow_refuse("role-model: Workflow builder on opus as a prompt key is denied under agent-model-cap",
                "await agent({prompt: 'Fix the failing case.', agentType: 'builder', model: 'opus'});")
workflow_refuse("role-model: Workflow builder on opus with a lone quote in its brief is denied",
                _step_flow("\"Don't touch the tests. Fix the case.\"", "agentType: 'builder', model: 'opus'"))
workflow_refuse("role-model: Workflow builder on opus with a comment opener inside its brief is denied",
                _step_flow("'See https://example.test/a and /* keep going. Fix the case.'",
                           "agentType: 'builder', model: 'opus'"))
workflow_refuse("role-model: Workflow builder on opus in a multi-line template brief is denied",
                _step_flow("`Fix the failing case.\n// keep the old API\nDon't stop.`",
                           "agentType: 'builder', model: 'opus'"))
workflow_refuse("role-model: Workflow Explore on opus with Audit: on line two of a template is denied (line one only counts)",
                _step_flow("`Find where X is defined.\nAudit: check the glossary.`", "agentType: 'Explore', model: 'opus'"))
# At its row: a builder on sonnet is allowed.
workflow_allow("role-model: Workflow builder on sonnet is allowed (at its row)",
               _step_flow("'Fix the failing case.'", "agentType: 'builder', model: 'sonnet'"))
# Controls: the Audit: marker on line one is the Explore grant (item 137 pick a), and a commented-out call is not a spawn.
workflow_allow("role-model: Workflow Explore on opus with Audit: on line one is allowed (item 137)",
               _step_flow("'Audit: check the glossary for meaning drift.'", "agentType: 'Explore', model: 'opus'"))
workflow_allow("role-model: a commented-out Workflow builder on opus is not a spawn and is allowed",
               "// agent('Fix the failing case.', {agentType: 'builder', model: 'opus'})\n"
               "await agent('Fix the failing case.', {agentType: 'builder', model: 'sonnet'});")

# ---- H2: a brief the scan cannot read grants nothing. A variable brief has no literal for the scan, and a spread
# before the options' literal keys hides them, so the Opus ceiling judges the call with no marker and refuses it
# (decision agent-model-cap). The markers below sit in the variable on purpose: the
# scan does not read them, so they are no grant. Failure class: a false allow (an above-row Opus spawn in a script
# passes because its brief or its options are not literal).
workflow_refuse("role-model: Workflow builder on opus with a variable brief holding a Round 3 marker is denied",
                "const brief = 'Round 3 of 3. Finish the fix.';\n"
                + _step_flow("brief", "agentType: 'builder', model: 'opus'"))
workflow_refuse("role-model: Workflow builder on opus with a template brief built from a variable is denied",
                "const who = 'the failing case';\n"
                + _step_flow("`Fix ${who}.`", "agentType: 'builder', model: 'opus'"))
workflow_refuse("role-model: Workflow builder on opus with a spread before its literal keys is denied",
                "const opts = {};\n"
                + _step_flow("`Fix the failing case.`", "...opts, agentType: 'builder', model: 'opus'"))
workflow_refuse("role-model: Workflow Explore on opus with a variable brief holding an Audit: marker is denied",
                "const brief = 'Audit: check the glossary for meaning drift.';\n"
                + _step_flow("brief", "agentType: 'Explore', model: 'opus'"))
# The control: the same variable brief on the builder's own row is allowed.
workflow_allow("role-model: Workflow builder on sonnet with a variable brief is allowed (at its row)",
               "const brief = 'Fix the failing case.';\n"
               + _step_flow("brief", "agentType: 'builder', model: 'sonnet'"))

# H3: a refusal for a brief the scan cannot read names the remedy that makes it readable, a literal string. One
# constant holds the words, so each refusal of a variable brief carries the same remedy.
BRIEF_LITERAL_REMEDY = "write the brief as a literal string so the marker is readable"
workflow_refuse("role-model: Workflow builder on opus with a variable brief is denied and names the literal-brief remedy",
                "const brief = 'Fix the failing case.';\n"
                + _step_flow("brief", "agentType: 'builder', model: 'opus'"),
                carries=BRIEF_LITERAL_REMEDY)
workflow_refuse("role-model: Workflow Explore on sonnet with a variable brief is denied under agent-role-model and names the literal-brief remedy",
                "const brief = 'Audit: check the glossary for meaning drift.';\n"
                + _step_flow("brief", "agentType: 'Explore', model: 'sonnet'"),
                rule=ROLE_RULE, carries=BRIEF_LITERAL_REMEDY, lacks=ROLE_LACKS)

# H4: a call whose agentType the scan cannot read is skipped, not judged as general-purpose (guard.py spawn_inputs).
# A shorthand agentType is unread, so the designer and design-reviewer rows pass on opus.
workflow_allow("role-model: Workflow designer and design-reviewer on opus, a shorthand agentType in a loop, are allowed",
               "for (const agentType of ['designer', 'design-reviewer']) agent(`Review the screen.`, {agentType, model: 'opus'});")
# A spread of an object the scan cannot read hides the agentType, so the call is skipped and not judged as general-purpose.
workflow_allow("role-model: Workflow opus agent() with a spread and no literal agentType is skipped, and allowed",
               "const base = {};\n"
               "await agent(`Fix the failing case.`, {...base, model: 'opus'});")
# The boundary pair: a literal agentType after the same spread is read, and the Opus ceiling refuses it.
workflow_refuse("role-model: Workflow builder on opus after a spread of base with a literal agentType is denied",
                "const base = {};\n"
                "await agent(`Fix the failing case.`, {...base, agentType: 'builder', model: 'opus'});")


def workflow_opus_override_check():
    """The owner's typed override lifts the Opus refusal of a Workflow builder whose brief is a variable: refused with
    no override, allowed under it, and refused again once the one-act override is spent."""
    config, session = role_config("ov-workflow-opus", REPO), "role-ov-workflow-opus"
    script = "const brief = 'Fix the failing case.';\n" + _step_flow("brief", "agentType: 'builder', model: 'opus'")

    def call(seconds):
        return ov_call("Workflow", {"script": script}, NOGIT, config, session, seconds)

    ok, why = ov_story([("no override", lambda: call(0), "deny", "agent-model-cap")])
    if not ok:
        return False, why
    note = ov_type(config, session, "override")
    ok, why = ov_story([
        ("under the typed override", lambda: call(60), "allow", "agent-model-cap"),
        ("the override spent", lambda: call(120), "deny", "agent-model-cap"),
    ], note)
    if not ok:
        return False, why
    return True, "refused with no override, allowed under the typed override, refused again once spent"

# ---- D: no model, and no `model:` pin in the role's agent file. The guard's default env decides it.
role_model_refuse("role-model: builder with no model is denied when the default is unset",
          "builder", None, "Fix the failing case.", config=ROLE_UNPINNED_CFG, carries=(ROLE_DEFAULT_REMEDY,),
          env=UNSET_DEFAULT)
role_model_refuse("role-model: general-purpose with no model is denied when the default is unset",
          "general-purpose", None, "Find the file.", carries=(ROLE_DEFAULT_REMEDY,), env=UNSET_DEFAULT)
role_model_refuse("role-model: claude with no model is denied when the default is unset",
          "claude", None, "Find the file.", carries=(ROLE_DEFAULT_REMEDY,), env=UNSET_DEFAULT)
role_model_refuse("role-model: a spawn with no role and no model is denied when the default is unset",
          None, None, "Find the file.", carries=(ROLE_DEFAULT_REMEDY,), env=UNSET_DEFAULT)
role_model_refuse("role-model: a Task builder with no model is denied when the default is unset",
          "builder", None, "Fix the failing case.", tool="Task", config=ROLE_UNPINNED_CFG,
          carries=(ROLE_DEFAULT_REMEDY,), env=UNSET_DEFAULT)
role_model_refuse("role-model: builder with no model is denied when the default is empty",
          "builder", None, "Fix the failing case.", config=ROLE_UNPINNED_CFG, carries=(ROLE_DEFAULT_REMEDY,),
          env=EMPTY_DEFAULT)
role_model_allow("role-model: builder with no model is allowed when the default is sonnet",
           "builder", None, "Fix the failing case.", env=SONNET_DEFAULT)
role_model_allow("role-model: reviewer with no model is allowed when the default is unset (its file pins haiku)",
           "reviewer", None, "Check the diff for typos.", env=UNSET_DEFAULT)
role_model_allow("role-model: test-author with no model is allowed when the default is unset (its file pins haiku)",
           "test-author", None, "Write the failing cases.", env=UNSET_DEFAULT)
role_model_allow("role-model: Explore with no model is allowed when the default is unset (its file pins haiku)",
           "Explore", None, "Audit the glossary for meaning drift.", env=UNSET_DEFAULT)

# ---- E: a decision file that cannot be read fails open. The spawn passes, and the rule never denies.
role_model_allow("role-model: a missing decision file fails open for test-author on sonnet",
           "test-author", "sonnet", "Write the failing cases.", config=ROLE_MISSING_CFG)
role_model_allow("role-model: an unreadable decision file fails open for reviewer on sonnet",
           "reviewer", "sonnet", "Check the diff for typos.", config=ROLE_UNREADABLE_CFG)
role_model_allow("role-model: no pointer line fails open for test-author on sonnet",
           "test-author", "sonnet", "Write the failing cases.", config=CFG)
role_model_allow("role-model: a missing decision file never denies a builder with no model",
           "builder", None, "Fix the failing case.", config=ROLE_MISSING_CFG, env=UNSET_DEFAULT)


# ---- F: the owner's override and the role row (item 127 pick a, Nov 1 17:25 CST; item 137 pick a, Nov 1 18:38 CST).
# A refusal of a spawn above its row is liftable by the general override. The no-model refusal stays never-lifted, so
# it spends no override. An Explore on Opus and a test-author on Opus are lifted by their own opus grants.
ROLE_OV_TEST_AUTHOR = role_input("test-author", "sonnet", "Write the failing cases.")
ROLE_OV_NO_MODEL = role_input("builder", None, "Fix the failing case.")
ROLE_OV_UNSET = {"CLAUDE_CODE_SUBAGENT_MODEL": None}


def role_override_lift_check():
    """A test-author on sonnet is refused by its row. One override lifts that refusal once, then it refuses again."""
    config, session = role_config("ov-lift", REPO), "role-ov-lift"

    def call(seconds):
        return ov_call("Agent", dict(ROLE_OV_TEST_AUTHOR), NOGIT, config, session, seconds)

    ok, why = ov_story([("no override", lambda: call(0), "deny", ROLE_RULE)])
    if not ok:
        return False, why
    note = ov_type(config, session, "override")
    ok, why = ov_story([
        ("the first spawn, under the override", lambda: call(60), "allow", ROLE_RULE),
        ("the next spawn, override spent", lambda: call(120), "deny", ROLE_RULE),
    ], note)
    if not ok:
        return False, why
    return True, "refused by its row, lifted by one override, refused again once it was spent"


def role_override_no_model_check():
    """The no-model refusal stays never-lifted: under an override it is still refused and spends none, so the
    override that follows still lifts a test-author on sonnet."""
    config, session = role_config("ov-no-model", ROLE_UNPINNED_POINTER), "role-ov-no-model"

    def call(seconds, spawn, env=None):
        return ov_call("Agent", dict(spawn), NOGIT, config, session, seconds, env=env)

    ok, why = ov_story([("no model, no override", lambda: call(0, ROLE_OV_NO_MODEL, ROLE_OV_UNSET), "deny", ROLE_RULE)])
    if not ok:
        return False, why
    note = ov_type(config, session, "override")
    ok, why = ov_story([
        ("no model, under the override", lambda: call(60, ROLE_OV_NO_MODEL, ROLE_OV_UNSET), "deny", ROLE_RULE),
        ("test-author on sonnet, the override not spent by the no-model refusal",
         lambda: call(120, ROLE_OV_TEST_AUTHOR), "allow", ROLE_RULE),
    ], note)
    if not ok:
        return False, why
    return True, "the no-model refusal stayed under the override, which then lifted a test-author on sonnet"


def role_opus_explore_lift_check():
    """`opus 2h` lifts an Explore on Opus with no Audit: marker. The refusal is the Opus ceiling's (item 137 pick a)."""
    config, session = ov_config("role-opus-explore"), "role-opus-explore"
    spawn = {"prompt": "Find where X is defined.", "model": "opus", "subagent_type": "Explore"}

    def call(seconds):
        return ov_call("Agent", dict(spawn), NOGIT, config, session, seconds)

    ok, why = ov_story([("no override", lambda: call(0), "deny", "agent-model-cap")])
    if not ok:
        return False, why
    note = ov_type(config, session, "opus 2h")
    ok, why = ov_story([("under opus 2h", lambda: call(60), "allow", "agent-model-cap")], note)
    if not ok:
        return False, why
    return True, "refused with no marker, lifted by opus 2h"


def role_opus_role_lift_check():
    """`opus test-authors 2h` lifts a test-author on Opus and no other role: a builder on Opus is still refused."""
    config, session = ov_config("role-opus-role"), "role-opus-role"
    author = {"prompt": "Write the failing cases.", "model": "opus", "subagent_type": "test-author"}
    builder = {"prompt": "Round 1 of 3. Start the fix.", "model": "opus", "subagent_type": "builder"}

    def call(seconds, spawn):
        return ov_call("Agent", dict(spawn), NOGIT, config, session, seconds)

    ok, why = ov_story([("test-author on opus, no override", lambda: call(0, author), "deny", "agent-model-cap")])
    if not ok:
        return False, why
    note = ov_type(config, session, "opus test-authors 2h")
    ok, why = ov_story([
        ("test-author on opus, under the grant", lambda: call(60, author), "allow", "agent-model-cap"),
        ("builder on opus, not covered by a test-author grant", lambda: call(120, builder), "deny", "agent-model-cap"),
    ], note)
    if not ok:
        return False, why
    return True, "the test-author grant lifted a test-author on opus, and not a builder on opus"


ROLE_OVERRIDE_CHECKS = (
    ("role-model: an owner override lifts a test-author on sonnet once, then refuses again",
     role_override_lift_check),
    ("role-model: the no-model refusal stays under an owner override, and spends none",
     role_override_no_model_check),
    ("role-model: opus 2h lifts an Explore on opus with no Audit: marker (item 137)", role_opus_explore_lift_check),
    ("role-model: opus test-authors 2h lifts a test-author on opus, and no builder", role_opus_role_lift_check),
    ("role-model: the typed override lifts a Workflow builder on opus with a variable brief, once",
     workflow_opus_override_check),
)
for _label, _check in ROLE_OVERRIDE_CHECKS:
    LOG_CHECKS_EXTRA.append((_label, _check))


def role_model_reader():
    """The guard's table reader, or None when the guard has none (the checks then fail and say so)."""
    return getattr(_load_guard_module(), "role_model_table", None)


def role_real_table_check():
    """The owner's decision file reads to the rows the guard enforces: each role, with the first word of its Model cell."""
    reader = role_model_reader()
    if reader is None:
        return False, "the guard has no role_model_table(root) to read the decision file"
    try:
        table = reader(REPO) or {}
    except Exception as exc:
        return False, "reading the real decision file raised %r" % (exc,)
    wrong = sorted("%s reads %r, want %r" % (role, table.get(role), want)
                   for role, want in ROLE_REAL_WANT.items() if table.get(role) != want)
    if wrong:
        return False, "; ".join(wrong[:3])
    return True, "%d roles read from the real decision file, each to its row's first Model word" % len(
        ROLE_REAL_WANT)


def role_rules_check():
    """Qualifier rows name no role, and a plain row reads its first Model word."""
    reader = role_model_reader()
    if reader is None:
        return False, "the guard has no role_model_table(root) to read the decision file"
    try:
        table = reader(ROLE_RULES_POINTER)
    except Exception as exc:
        return False, "reading the decision file raised %r" % (exc,)
    if table != ROLE_RULES_WANT:
        return False, "the table reads as %r, want %r" % (table, ROLE_RULES_WANT)
    return True, "the qualifier rows add no role, and each plain row reads its first Model word"


def role_live_check():
    """The table is read at each spawn: a row edited between two spawns changes the second verdict."""
    spawn = role_input("test-author", "sonnet", "Write the failing cases.")
    first = role_spawn(ROLE_LIVE_CFG, spawn)
    if first[0] != "deny" or ROLE_RULE not in first[1]:
        return False, "with the row at haiku the spawn is %s (%s), want a %s deny" % (
            first[0], first[1][:70], ROLE_RULE)
    write(os.path.join(ROLE_LIVE_POINTER, "docs", "decisions", "agent-model-cap.md"),
          ROLE_TABLE_TEST_AUTHOR_SONNET)
    second = role_spawn(ROLE_LIVE_CFG, spawn)
    if second[0] != "allow":
        return False, "with the row edited to sonnet the spawn is %s (%s), want allow" % (
            second[0], second[1][:70])
    return True, "the same spawn is denied at haiku and allowed once its row is edited"


def role_unread_log_check(config, spawn, name):
    """An unread decision file allows the spawn, and writes exactly one noted line for this rule."""
    path = os.path.join(config, "guard.log")
    if os.path.exists(path):
        os.remove(path)
    got, reason = role_spawn(config, spawn)
    if got != "allow":
        return False, "the spawn with the %s file is %s (%s), want allow" % (name, got, reason[:70])
    if not os.path.exists(path):
        return False, "no guard.log was written for the %s file" % name
    with open(path, encoding="utf-8") as handle:
        lines = [line for line in handle.read().splitlines() if ROLE_RULE in line]
    if len(lines) != 1:
        return False, "expected one %s line for the %s file, found %d" % (ROLE_RULE, name, len(lines))
    fields = lines[0].split("\t")
    if len(fields) < 5 or fields[2] != "noted" or "unread" not in fields[3] or ROLE_RULE not in fields[3]:
        return False, "the line does not read noted, with an unread %s rule: %r" % (ROLE_RULE, lines[0])
    return True, "the %s file allows the spawn, and logs one noted unread line" % name


def role_unread_missing_check():
    return role_unread_log_check(ROLE_MISSING_CFG, role_input("test-author", "sonnet", "Write the failing cases."),
                                 "missing")


def role_unread_bad_check():
    return role_unread_log_check(ROLE_UNREADABLE_CFG, role_input("reviewer", "sonnet", "Check the diff for typos."),
                                 "unreadable")


# ---- G: role_has_model_pin(pointer_root, role) reads the missing-model default (rule part 2). It reads the agents/
# files in name order and stops at the first pin. An unreadable file ahead of the pin makes the answer None, which the
# guard reads as fail open. A file after the pin is never read. The unreadable file holds bytes that are not UTF-8: the
# suite runs as root, which reads any file whatever its mode.
ROLE_PIN_HAIKU = "---\nname: reviewer\nmodel: haiku\n---\n# reviewer\n"
ROLE_PIN_UNREADABLE = b"---\nname: scout\n\xff\xfe\x80 not text\n---\n"


def role_pin_check(pointer, want, what):
    """role_has_model_pin(pointer, "reviewer") gives `want` (True, False or None) for the agents/ folder there."""
    reader = getattr(_load_guard_module(), "role_has_model_pin", None)
    if reader is None:
        return False, "the guard has no role_has_model_pin(root, role) to read the agents folder"
    try:
        got = reader(pointer, "reviewer")
    except Exception as exc:
        return False, "reading the agents folder raised %r" % (exc,)
    if got is not want:
        return False, "%s: role_has_model_pin reads %r, want %r" % (what, got, want)
    return True, "%s: role_has_model_pin reads %r" % (what, want)


def role_pin_first_check():
    """A pinned file sorts first, so the reader stops there and never reads the unreadable file after it."""
    pointer = role_table("pin-first", files={"a.md": ROLE_PIN_HAIKU, "b.md": ROLE_PIN_UNREADABLE})
    return role_pin_check(pointer, True, "a pinned a.md sorts before an unreadable b.md")


def role_pin_unreadable_first_check():
    """An unreadable file sorts first, so the read fails there, before the pin after it is reached."""
    pointer = role_table("pin-unreadable-first", files={"a.md": ROLE_PIN_UNREADABLE, "b.md": ROLE_PIN_HAIKU})
    return role_pin_check(pointer, None, "an unreadable a.md sorts before a pinned b.md")


# ---- G2: role_has_model_pin reads a pin's value through frontmatter_scalar (decision agent-model-cap). A value that is
# only a comment, an unquoted `~` or `null`, or empty holds no model, so its line is no pin. A bare name, or a quoted
# name with a trailing comment, is a pin. Each case is one frontmatter line in one agents/ file.
def role_pin_line_check(name, line, want):
    """role_has_model_pin gives `want` for an agents/ file whose frontmatter holds the one line `line`."""
    pointer = role_table(name, files={"reviewer.md": "---\nname: reviewer\n%s\n---\n# reviewer\n" % line})
    return role_pin_check(pointer, want, "a reviewer file with the frontmatter line %r" % line)


def role_pin_line_case(name, line, want):
    """The check for one frontmatter line: role_has_model_pin gives `want` for it."""
    def check():
        return role_pin_line_check(name, line, want)
    return check


# ---- H: role_model_rank(model) reads the family a model value holds (decision agent-model-cap, the pin reader's family
# step). A family word is read from the value, never from a trailing comment, so `haiku  # sonnet` holds haiku. The
# control reads bare names only, so a red comment case is the trailing comment alone.
def role_model_rank_check(value, want, what):
    """role_model_rank(value) gives `want`, an index into ROLE_MODEL_RANK."""
    reader = getattr(_load_guard_module(), "role_model_rank", None)
    if reader is None:
        return False, "the guard has no role_model_rank(model) to read a model name's family"
    try:
        got = reader(value)
    except Exception as exc:
        return False, "%s: role_model_rank(%r) raised %r" % (what, value, exc)
    if got != want:
        return False, "%s: role_model_rank(%r) gives %r, want %r" % (what, value, got, want)
    return True, "%s: role_model_rank(%r) gives %r" % (what, value, want)


def role_model_rank_bare_check():
    """Control: a bare model name reads its family. claude-sonnet-5-5 is sonnet (1) and Haiku is haiku (0)."""
    for value, want in (("claude-sonnet-5-5", 1), ("Haiku", 0)):
        ok, detail = role_model_rank_check(value, want, "a bare model name")
        if not ok:
            return ok, detail
    return True, "a bare model name reads its family: claude-sonnet-5-5 is 1, Haiku is 0"


def role_model_rank_comment_check():
    """`haiku  # sonnet is above the row` holds haiku (0). The trailing comment names sonnet, and the reader must not read it."""
    return role_model_rank_check("haiku  # sonnet is above the row", 0, "a trailing comment that names sonnet")


# ---- F: the three role lists agree with the role table (decision agent-model-cap). role_list_drift(pointer_root)
# in hooks/guard.py returns one line per disagreement, and [] when all agree. The lists are constants, and the table
# is read from the pointer at run time. A real role is an agents/ file's `name`, or a built-in name. The junk rows
# below are the ones the reader yields on the real record (fallbackModel, advisorModel, and haiku and opus from the
# measured-cost rows). None of them is a real role, so none may cause drift.
ROLE_LIST_BUILTINS = ("general-purpose", "claude")
ROLE_LIST_JUNK = ("| `fallbackModel` | sonnet | n/a |\n"
                  "| `advisorModel` | opus | n/a |\n"
                  "| `haiku`, `opus` | sonnet | not a role |\n")
DRIFT_ABSENT = "the guard has no role_list_drift(pointer_root) to check the three role lists"


def role_list_table(models=None, rows=""):
    """A decision file with one row per real role at its ROLE_REAL_WANT model. `models` overrides a role's
    model, and `rows` adds rows. The junk rows follow, as on the real record."""
    models = models or {}
    body = "".join("| %s | %s | high |\n" % (role, models.get(role, want)) for role, want in ROLE_REAL_WANT.items())
    return ROLE_TABLE_HEAD + body + rows + ROLE_LIST_JUNK


def role_list_pointer(name, table, extra=()):
    """A pointer checkout for the drift cases: `table`, and an agents/ file for each real role that has no
    built-in name. `extra` names more real roles, each with an agents/ file."""
    agents = [role for role in ROLE_REAL_WANT if role not in ROLE_LIST_BUILTINS] + list(extra)
    return role_table(name, table, agents=agents)


def role_drift_lines(pointer):
    """(lines, why). `lines` is what role_list_drift gives for `pointer`. It is None, with `why` saying
    why, when the guard has no such function, the call raises, or it does not return a list of text."""
    checker = getattr(_load_guard_module(), "role_list_drift", None)
    if checker is None:
        return None, DRIFT_ABSENT
    try:
        lines = checker(pointer)
    except Exception as exc:
        return None, "role_list_drift(pointer_root) raised %r" % (exc,)
    if not isinstance(lines, list) or not all(isinstance(line, str) for line in lines):
        return None, "role_list_drift(pointer_root) did not return a list of text lines: %r" % (lines,)
    return lines, ""


def role_drift_clean_check(pointer, what):
    """The three lists agree with the table at `pointer`, so there is no drift line."""
    lines, why = role_drift_lines(pointer)
    if lines is None:
        return False, why
    if lines:
        return False, "%d drift lines for %s, want none: %r" % (len(lines), what, lines[:2])
    return True, "%s: the three role lists agree with the table, no drift" % what


def role_drift_names_check(pointer, names, what):
    """The table at `pointer` drifts from the lists, and one drift line names every word in `names`."""
    lines, why = role_drift_lines(pointer)
    if lines is None:
        return False, why
    if not any(all(name in line for name in names) for line in lines):
        return False, "no drift line names %s for %s; got %r" % (" and ".join(names), what, lines[:2])
    return True, "%s: a drift line names %s" % (what, " and ".join(names))


def role_list_real_check():
    return role_drift_clean_check(REPO, "the real decision record")


def role_list_junk_check():
    """The clean table carries the junk rows, and the reader yields them, so the drift check meets them."""
    reader = role_model_reader()
    if reader is None:
        return False, "the guard has no role_model_table(root) to read the decision file"
    pointer = role_list_pointer("listdrift-clean", role_list_table())
    table = reader(pointer) or {}
    absent = [key for key in ("fallbackModel", "advisorModel") if key not in table]
    if absent:
        return False, "the reader does not yield %s, so this case proves nothing" % ", ".join(absent)
    return role_drift_clean_check(pointer, "the junk keys fallbackModel and advisorModel")


def role_list_haiku_check():
    pointer = role_list_pointer("listdrift-test-author", role_list_table({"test-author": "sonnet"}))
    return role_drift_names_check(pointer, ("test-author", "HAIKU_ROLES"), "test-author moved to a sonnet row")


def role_list_opus_check():
    pointer = role_list_pointer("listdrift-scout", role_list_table(rows="| scout | opus | high |\n"), extra=("scout",))
    return role_drift_names_check(pointer, ("scout", "OPUS_STANDING_ROLES"), "a new opus row role")


def role_list_builder_check():
    pointer = role_list_pointer("listdrift-builder", role_list_table({"builder": "opus"}))
    return role_drift_names_check(pointer, ("builder", "OPUS_ROLES"), "builder moved to an opus row")


for _label, _check in (
    ("role-model: the owner's real decision file reads to the rows the guard enforces", role_real_table_check),
    ("role-model: qualifier rows name no role, and a plain row reads its first Model word", role_rules_check),
    ("role-model: the table is read at each spawn, so an edited row changes the next verdict", role_live_check),
    ("role-model: a missing decision file logs one unread line and allows the spawn", role_unread_missing_check),
    ("role-model: an unreadable decision file logs one unread line and allows the spawn", role_unread_bad_check),
    ("role-model: a pinned agent file sorts before an unreadable one, so the pin reads True", role_pin_first_check),
    ("role-model: an unreadable agent file sorts before a pinned one, so the read gives None", role_pin_unreadable_first_check),
    ("role-model: a pin of only a comment (`model: # sonnet`) is no pin, so role_has_model_pin is False",
     role_pin_line_case("pinline-comment-only", "model: # sonnet", False)),
    ("role-model: a pin of `model: ~` is no pin, so role_has_model_pin is False",
     role_pin_line_case("pinline-tilde", "model: ~", False)),
    ("role-model: a pin of `model: null` is no pin, so role_has_model_pin is False",
     role_pin_line_case("pinline-null", "model: null", False)),
    ("role-model: a pin of empty quotes (`model: \"\"`) is no pin, so role_has_model_pin is False",
     role_pin_line_case("pinline-empty-quotes", 'model: ""', False)),
    ("role-model: a pin with no value (`model:`) is no pin, so role_has_model_pin is False",
     role_pin_line_case("pinline-empty", "model:", False)),
    ("role-model: a bare pin (`model: sonnet`) is a pin, so role_has_model_pin is True",
     role_pin_line_case("pinline-bare", "model: sonnet", True)),
    ("role-model: a quoted pin with a trailing comment (`model: \"sonnet\" # note`) is a pin, so role_has_model_pin is True",
     role_pin_line_case("pinline-quoted-note", 'model: "sonnet" # note', True)),
    ("role-model: role_model_rank reads a bare model name's family, sonnet 1 and haiku 0", role_model_rank_bare_check),
    ("role-model: role_model_rank does not read sonnet from a trailing comment, so haiku # sonnet is 0",
     role_model_rank_comment_check),
    ("role-list: the three role lists agree with the real decision record", role_list_real_check),
    ("role-list: the junk keys the reader yields on the record cause no drift", role_list_junk_check),
    ("role-list: test-author moved from a haiku row to sonnet drifts HAIKU_ROLES", role_list_haiku_check),
    ("role-list: a new opus row role drifts OPUS_STANDING_ROLES", role_list_opus_check),
    ("role-list: builder moved to an opus row drifts the override's OPUS_ROLES", role_list_builder_check),
    ("refuter: guard_core names the refuter role in REFUTER_ROLE, the one home the cases read",
     refuter_name_check),
):
    LOG_CHECKS_EXTRA.append((_label, _check))
    FIXTURELESS_CHECKS.add(_check)


# ---- B3: one brief-marker table and one scanner. The table is shared_names.BRIEF_MARKERS, rows of (kind, regex text,
# position). The scanner is guard.marker_hits(brief), a set of (kind, n). Both names are new, so every read happens
# inside its check: a guard without them fails that check with its reason, and the run goes on.
def _marker_hits_fn():
    """guard.marker_hits from the guard under test, or None while the name is absent."""
    return getattr(_load_guard_module(), "marker_hits", None)


def _shared_names_under_test():
    """shared_names.py beside the guard under test, loaded under its own name so no cached copy answers."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "shared_names_under_test", os.path.join(os.path.dirname(GUARD), "shared_names.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def brief_marker_table_check():
    """Each row is (kind, regex text, position). The kinds round, try and audit each have a row, and an audit row holds
    EXPLORE_AUDIT_MARKER, read from the constant."""
    try:
        names = _shared_names_under_test()
    except Exception as exc:
        return False, "shared_names.py does not load: %r" % (exc,)
    rows = getattr(names, "BRIEF_MARKERS", None)
    if rows is None:
        return False, "shared_names has no BRIEF_MARKERS yet"
    if not isinstance(rows, tuple):
        return False, "BRIEF_MARKERS is a %s, want a tuple of rows" % type(rows).__name__
    problems, kinds, audit_texts = [], set(), []
    for row in rows:
        if not (isinstance(row, tuple) and len(row) == 3 and all(isinstance(f, str) for f in row)):
            problems.append("row %r is not (kind, regex text, position) of strings" % (row,))
            continue
        kind, text, position = row
        kinds.add(kind)
        if position not in ("line-start", "first-line"):
            problems.append("%s row has position %r" % (kind, position))
        try:
            re.compile(text)
        except re.error as exc:
            problems.append("%s row does not compile: %s" % (kind, exc))
        if kind == "audit":
            audit_texts.append(text)
    problems += ["no %s row" % kind for kind in ("round", "try", "audit") if kind not in kinds]
    marker = getattr(names, "EXPLORE_AUDIT_MARKER", "")
    if not marker or not any(marker in text for text in audit_texts):
        problems.append("no audit row holds EXPLORE_AUDIT_MARKER")
    if problems:
        return False, "; ".join(problems)
    return True, "BRIEF_MARKERS has round, try and audit rows, each positioned; the audit row holds the constant"


def marker_rows_check(*rows):
    """Each row is (brief, kind, n, holds): marker_hits(brief) holds (kind, n) when holds is True, and lacks it when
    False. The note names each row that is wrong."""
    def check():
        marker_hits = _marker_hits_fn()
        if marker_hits is None:
            return False, "guard.py has no marker_hits(brief) yet"
        wrong = []
        for brief, kind, n, holds in rows:
            try:
                got = marker_hits(brief)
            except Exception as exc:
                return False, "marker_hits(%r) raised %r" % (brief, exc)
            if not isinstance(got, set):
                return False, "marker_hits(%r) returned a %s, want a set" % (brief, type(got).__name__)
            if ((kind, n) in got) != holds:
                wrong.append("marker_hits(%r) %s (%s, %r)" % (brief, "lacks" if holds else "holds", kind, n))
        if wrong:
            return False, "; ".join(wrong)
        return True, "%d marker_hits rows as ruled" % len(rows)
    return check


def marker_none_check():
    marker_hits = _marker_hits_fn()
    if marker_hits is None:
        return False, "guard.py has no marker_hits(brief) yet"
    try:
        got = marker_hits(None)
    except Exception as exc:
        return False, "marker_hits(None) raised %r" % (exc,)
    if not isinstance(got, set) or got:
        return False, "marker_hits(None) is %r, want an empty set" % (got,)
    return True, "marker_hits(None) is an empty set"


def brief_markers_order_check():
    """brief_markers(brief) keeps the markers in the order the brief lists them. step_up_reason acts on the first
    one it meets, so that order picks the refusal text a reviewer on haiku gets. The brief lists the later-numbered
    marker first; a reversed scan would give the reviewer the other refusal."""
    guard = _load_guard_module()
    brief_markers = getattr(guard, "brief_markers", None)
    step_up_reason = getattr(guard, "step_up_reason", None)
    if brief_markers is None or step_up_reason is None:
        return False, "guard.py has no brief_markers(brief) or step_up_reason(prompt, role, model) yet"
    brief = "Round 3 of 3\nRound 2 of 3"
    try:
        got = [(kind.lower(), n) for kind, n in brief_markers(brief)]
        reason = step_up_reason(brief, "reviewer", "haiku")
    except Exception as exc:
        return False, "brief_markers or step_up_reason raised %r" % (exc,)
    wrong = []
    if got != [("round", "3"), ("round", "2")]:
        wrong.append("brief_markers gives %r, want the Round 3 marker then the Round 2 one" % (got,))
    if not reason.startswith("Reviewer round 3 runs on Sonnet."):
        wrong.append("a reviewer on haiku gets %r, want the Round 3 refusal" % (reason,))
    if "Sonnet or Opus" in reason:
        wrong.append("a reviewer's round 3 remedy names Opus, want Sonnet only: %r" % (reason,))
    if wrong:
        return False, "; ".join(wrong)
    return True, "brief_markers keeps line order; a reviewer on haiku gets the Round 3 refusal"


_BRIEF_MARKER_CHECKS = (
    ("brief markers: BRIEF_MARKERS has round, try and audit rows, each positioned, and the audit row holds "
     "EXPLORE_AUDIT_MARKER", brief_marker_table_check),
    ("brief markers: a Round line on line two counts as round 2",
     marker_rows_check(("Find X.\nRound 2 of 3", "round", "2", True))),
    ("brief markers: Audit: on the first line counts as audit, with no n",
     marker_rows_check(("Audit: check", "audit", None, True))),
    ("brief markers: Audit: on line two does not count as audit",
     marker_rows_check(("Find X.\nAudit: y", "audit", None, False))),
    ("brief markers: Audit: after prose on the first line counts as audit",
     marker_rows_check(("Please read the Audit: docs", "audit", None, True))),
    ("brief markers: a lowercase audit: does not count as audit (case-sensitive)",
     marker_rows_check(("audit: x", "audit", None, False))),
    ("brief markers: marker_hits(None) is an empty set", marker_none_check),
    ("brief markers: a lone quote in the prose ahead does not hide a Round line on line two",
     marker_rows_check(("Don't skip the check.\nRound 2 of 3.", "round", "2", True))),
    ("brief markers: a markdown heading or a // line ahead does not hide a Round line on line two",
     marker_rows_check(("## Lane c204\nRound 2 of 3.", "round", "2", True),
                       ("// lane c204\nRound 2 of 3.", "round", "2", True))),
    ("brief markers: a backtick span open across lines does not hide a Round line that starts a line",
     marker_rows_check(("Check `a\nRound 2 of 3` now.", "round", "2", True))),
    ("brief markers: first-line Round counts with a role word ahead, first-line Try does not, "
     "a Try line at line start counts",
     marker_rows_check(("Builder, Round 3 of 3. Fix.", "round", "3", True),
                       ("Builder, Try 3 of 3. Fix.", "try", "3", False),
                       ("Find X.\nTry 3 of 3.", "try", "3", True))),
    ("brief markers: a first line that starts with a marker in any case keeps the first-line rule off",
     marker_rows_check(("ROUND 1 OF 3 then Round 2 of 3", "round", "2", False),
                       ("Round 2 Of 3 and Round 3 of 3", "round", "3", False))),
    ("brief markers: brief_markers keeps line order, and a reviewer on haiku gets the Round 3 refusal from it",
     brief_markers_order_check),
)
for _label, _check in _BRIEF_MARKER_CHECKS:
    LOG_CHECKS_EXTRA.append((_label, _check))
    FIXTURELESS_CHECKS.add(_check)


# ---- B4: the fix check marker (owner item 444 a). A reviewer's fix check carries no round, so it
# lifts to Sonnet on FIX_CHECK_MARKER. The marker counts only when the brief's first non-blank line starts with it, leading
# spaces and tabs aside, and it is case-sensitive: text ahead of it on that line does not count. It lifts a reviewer on
# Sonnet only: Haiku passes on its own row, Opus stays under the ceiling, and a builder, a test-author or an Explore gets no
# lift. The constant is read from shared_names at module load, never copied. A missing constant reads as FIX_UNBUILT, so
# each case fails on its assert, not on an import error.
FIX_UNBUILT = "FIX_CHECK_NOT_BUILT"
try:
    FIX_MARKER = getattr(_shared_names_under_test(), "FIX_CHECK_MARKER", FIX_UNBUILT)
except Exception:
    FIX_MARKER = FIX_UNBUILT
FIX_MARKER_LOWER = FIX_MARKER.lower()


def fix_check_row_check():
    """BRIEF_MARKERS has a fixcheck row on the first line, and that row reads FIX_CHECK_MARKER."""
    try:
        names = _shared_names_under_test()
    except Exception as exc:
        return False, "shared_names.py does not load: %r" % (exc,)
    marker = getattr(names, "FIX_CHECK_MARKER", None)
    if not isinstance(marker, str) or not marker:
        return False, "shared_names has no FIX_CHECK_MARKER yet"
    rows = [row for row in getattr(names, "BRIEF_MARKERS", ())
            if isinstance(row, tuple) and len(row) == 3 and row[0] == "fixcheck"]
    if not rows:
        return False, "BRIEF_MARKERS has no fixcheck row yet"
    problems = []
    if not any(row[2] == "first-line" for row in rows):
        problems.append("the fixcheck row is not first-line")
    try:
        reads_marker = any(re.search(row[1], marker) for row in rows)
    except re.error as exc:
        return False, "the fixcheck row does not compile: %s" % (exc,)
    if not reads_marker:
        problems.append("no fixcheck row reads FIX_CHECK_MARKER")
    if problems:
        return False, "; ".join(problems)
    return True, "BRIEF_MARKERS has a first-line fixcheck row that reads FIX_CHECK_MARKER"


_FIX_CHECK_CHECKS = (
    ("brief markers: BRIEF_MARKERS has a first-line fixcheck row that reads FIX_CHECK_MARKER", fix_check_row_check),
    ("brief markers: the fix check marker on the first line counts as fixcheck, with no n",
     marker_rows_check((FIX_MARKER + ". Re-run the cases.", "fixcheck", None, True))),
    ("brief markers: the fix check marker after prose on the first line does not count as fixcheck",
     marker_rows_check(("Reviewer, " + FIX_MARKER + ". Re-run the cases.", "fixcheck", None, False))),
    ("brief markers: the fix check marker after markup on the first line does not count as fixcheck",
     marker_rows_check(("**" + FIX_MARKER + ":** re-run the cases.", "fixcheck", None, False))),
    ("brief markers: the fix check marker on the first non-blank line after blank lines counts as fixcheck",
     marker_rows_check(("\n\n" + FIX_MARKER + ". Re-run the cases.", "fixcheck", None, True))),
    ("brief markers: the fix check marker on line two does not count as fixcheck",
     marker_rows_check(("Find X.\n" + FIX_MARKER + ". Re-run the cases.", "fixcheck", None, False))),
    ("brief markers: a lowercase fix check on the first line does not count as fixcheck (case-sensitive)",
     marker_rows_check((FIX_MARKER_LOWER + ". Re-run the cases.", "fixcheck", None, False))),
)
for _label, _check in _FIX_CHECK_CHECKS:
    LOG_CHECKS_EXTRA.append((_label, _check))
    FIXTURELESS_CHECKS.add(_check)

# A reviewer on Sonnet with the marker on its first line passes. A reviewer's refusal names the marker in its remedy; a
# test-author's and an Explore's refusals never name it.
role_model_allow("role-model: fix check: reviewer on sonnet with the marker on line one is allowed", "reviewer", "sonnet",
                 FIX_MARKER + ". Re-run the cases.")
role_model_refuse("role-model: fix check: reviewer on sonnet with a role word ahead of the marker on line one is denied",
                  "reviewer", "sonnet", "Reviewer, " + FIX_MARKER + ". Re-run the cases.", carries=(ROLE_REMEDY, FIX_MARKER))
role_model_refuse("role-model: fix check: reviewer on sonnet with markup ahead of the marker on line one is denied",
                  "reviewer", "sonnet", "**" + FIX_MARKER + ":** re-run the cases.", carries=(ROLE_REMEDY, FIX_MARKER))
role_model_allow("role-model: fix check: reviewer on sonnet with the marker first on line one and a Round 1 of 3 after it is "
                 "allowed", "reviewer", "sonnet", FIX_MARKER + ". Round 1 of 3 finding F1, head abc1234.")
role_model_allow("role-model: fix check: reviewer on sonnet with the marker after leading spaces on line one is allowed",
                 "reviewer", "sonnet", "   " + FIX_MARKER + ", PR 7")
role_model_allow("role-model: fix check: reviewer on sonnet with the marker after a leading tab on line one is allowed",
                 "reviewer", "sonnet", "\t" + FIX_MARKER + ", PR 7")
role_model_refuse("role-model: fix check: reviewer on sonnet with Round 1 of 3 first on line one and the marker after it is denied",
                  "reviewer", "sonnet", "Round 1 of 3. New lane after " + FIX_MARKER + " FAIL on PR 12. Review it.",
                  carries=(ROLE_REMEDY, FIX_MARKER))
role_model_refuse("role-model: fix check: reviewer on sonnet with Re: ahead of the marker on line one is denied",
                  "reviewer", "sonnet", "Re: " + FIX_MARKER + " of PR 7", carries=(ROLE_REMEDY, FIX_MARKER))
# The row ends on \b, so a longer word that starts with the marker does not lift a reviewer on Sonnet.
role_model_refuse("role-model: fix check: reviewer on sonnet with Fix checkpoint on line one is denied",
                  "reviewer", "sonnet", FIX_MARKER + "point for PR 2296",
                  carries=(ROLE_REMEDY, ROUND_MARKER, FIX_MARKER) + FREE_ROUND_MARKERS)
role_model_allow("role-model: fix check: reviewer on sonnet with the marker after blank lines, as its first non-blank "
                 "line, is allowed", "reviewer", "sonnet", "\n\n" + FIX_MARKER + ". Re-run the cases.")
role_model_allow("role-model: fix check: the same reviewer spawn as a Task on sonnet is allowed", "reviewer", "sonnet",
                 FIX_MARKER + ". Re-run the cases.", tool="Task")
workflow_allow("role-model: fix check: Workflow reviewer on sonnet with the marker on line one is allowed",
               _step_flow("'%s. Re-run the cases.'" % FIX_MARKER, "agentType: 'reviewer', model: 'sonnet'"))
# A fix verifier runs Sonnet, set per spawn, so Haiku is refused. The step-up judges it before the role row, and its
# refusal names Sonnet and not Opus.
add("role-model: fix verifier: reviewer on haiku with the marker is denied under roles-third-round-steps-up, names Sonnet",
    "deny", "roles-third-round-steps-up", tool="Agent", config=ROLE_REAL_CFG, carries=(FIX_VERIFIER_REASON,), lacks=("Opus",),
    **role_input("reviewer", "haiku", FIX_MARKER + ". Re-run the cases."))
role_model_refuse("role-model: fix check: reviewer on sonnet with no marker is denied, and its remedy names the marker",
                  "reviewer", "sonnet", "Check the diff for typos.",
                  carries=(ROLE_REMEDY, ROUND_MARKER, FIX_MARKER) + FREE_ROUND_MARKERS)
role_model_refuse("role-model: fix check: the marker on line two does not lift a reviewer on sonnet, and the remedy names it",
                  "reviewer", "sonnet", "Check the diff.\n" + FIX_MARKER + ". Re-run the cases.",
                  carries=(ROLE_REMEDY, FIX_MARKER))
role_model_refuse("role-model: fix check: a lowercase marker on line one does not lift a reviewer on sonnet, and the "
                  "remedy names the marker", "reviewer", "sonnet", FIX_MARKER_LOWER + ". Re-run the cases.",
                  carries=(ROLE_REMEDY, FIX_MARKER))
# The lift reaches only a model below the top rank. A model the table does not rank counts above it, so the marker does not
# lift a reviewer on it. Its refusal still names the marker, as every reviewer refusal does.
role_model_refuse("role-model: fix check: reviewer on claude-fable-5-1 with the marker on line one is denied, the lift "
                  "does not reach an unranked model", "reviewer", "claude-fable-5-1", FIX_MARKER + ". Re-run the cases.",
                  carries=(ROLE_REMEDY, FIX_MARKER))
role_opus_refuse("role-model: fix check: reviewer on opus with the marker is denied under agent-model-cap, the ceiling holds",
                 "reviewer", "opus", FIX_MARKER + ". Re-run the cases.")
role_opus_refuse("role-model: fix check: builder on opus with the marker is denied under agent-model-cap, no lift",
                 "builder", "opus", FIX_MARKER + ". Fix the failing case.")
role_model_refuse("role-model: fix check: test-author on sonnet with the marker is denied and names no fix check marker",
                  "test-author", "sonnet", FIX_MARKER + ". Write the failing cases.",
                  lacks=ROLE_LACKS + (ROUND_MARKER, FIX_MARKER) + FREE_ROUND_MARKERS)
role_model_refuse("role-model: fix check: Explore on sonnet with the marker is denied, only the audit marker lifts an Explore",
                  "Explore", "sonnet", FIX_MARKER + ". Find where X is defined.", carries=(EXPLORE_MARKER,),
                  lacks=ROLE_LACKS + (FIX_MARKER,))

# A reviewer's refusal names each brief form that lifts it above its row: rounds 2 and 3, and the fix check on line one.
# It also says the first round and the test-author run on their role's model. A builder's refusal names none of these.
role_model_refuse("role-model: reviewer on sonnet with no round line names each brief form and the round 1 sentence",
                  "reviewer", "sonnet", "Check the diff for typos.",
                  carries=(ROLE_REMEDY, ROUND_MARKER, ROUND_ONE_SENTENCE, FIX_MARKER, ROUND_FIX_FORM) + FREE_ROUND_MARKERS)
role_model_refuse("role-model: builder on fable names no reviewer form and no round 1 sentence",
                  "builder", "fable", "Fix the failing case.",
                  lacks=ROLE_LACKS + (ROUND_MARKER, FIX_MARKER, ROUND_FIX_FORM, ROUND_ONE_SENTENCE) + FREE_ROUND_MARKERS)
# A fix check on a later round lifts a reviewer on Sonnet when its first line is the round marker and the fix check words.
# The round row reads that line, so the lift comes from the row, not from the fix check marker.
role_model_allow("role-model: round row: reviewer on sonnet with Round 2 of 3 (fix check) on line one is allowed, as a round 2 brief",
                 "reviewer", "sonnet", "Round 2 of 3 (fix check). Re-run the cases.")
# The first-round sentence and the fix check round form stay out of an Explore's and a test-author's refusal.
role_model_refuse("role-model: Explore on sonnet names neither the round 1 sentence nor the fix check round form",
                  "Explore", "sonnet", "Find where X is defined.", carries=(EXPLORE_MARKER,),
                  lacks=ROLE_LACKS + (ROUND_ONE_SENTENCE, ROUND_FIX_FORM))
role_model_refuse("role-model: test-author on sonnet names neither the round 1 sentence nor the fix check round form",
                  "test-author", "sonnet", "Write the failing cases.",
                  lacks=ROLE_LACKS + (ROUND_ONE_SENTENCE, ROUND_FIX_FORM))


# ---- I: the reviewer's guard marker. A reviewer on Sonnet may run a guard or check diff when its brief carries the line
# the review record writes, `Guard or check: yes` (rule agent-role-model). The marker must start a line and match case.
# It lifts Sonnet on any round. It lifts no other role and no Opus spawn, and a `no` value, a mid-line marker,
# a lowercase form or a line inside a fenced block lifts nothing. The marker text is a literal here: REVIEW_GUARD_MARKER in
# shared_names is a new name, and a read at import would fail every case on the old code (as EXPLORE_MARKER is). The check
# review_guard_marker_check holds shared_names to this text.
def review_log_guard_line():
    """The `Guard or check: yes` line merge/merge.py review_body writes for a guard or check change, read from the writer
    so this file holds no copy of the text."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("merge_tool_guard_line", os.path.join(REPO, "merge", "merge.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    body = module.review_body(1, "0" * 40, "normal", "yes", [], "zero")
    return next(line for line in body.splitlines() if line.startswith("Guard or check:"))


def review_guard_marker_check():
    """shared_names.REVIEW_GUARD_MARKER is the one name for the review record's Guard or check line. A missing name, or a
    shared_names that does not load, fails the check and says so."""
    try:
        names = _shared_names_under_test()
    except Exception as exc:
        return False, "shared_names.py does not load: %r" % (exc,)
    marker = getattr(names, "REVIEW_GUARD_MARKER", None)
    if marker is None:
        return False, "shared_names has no REVIEW_GUARD_MARKER, the one name for the review record's Guard or check line"
    if marker != review_log_guard_line():
        return False, "REVIEW_GUARD_MARKER is not the Guard or check line the review record writes"
    return True, "REVIEW_GUARD_MARKER is the review record's Guard or check line"


LOG_CHECKS_EXTRA.append(("role-model: shared_names' REVIEW_GUARD_MARKER is the review record's Guard or check line",
                         review_guard_marker_check))
FIXTURELESS_CHECKS.add(review_guard_marker_check)
REVIEW_GUARD_MARKER = "Guard or check: yes"  # the review record's line; see the header above
GUARD_NO_LINE = "Guard or check: no"

# A reviewer on Sonnet passes with the marker at a line start: on line 1 or later, on any round, with text after it on
# its line, and as a whole brief. The row still reads its Haiku pin, so a Haiku reviewer with the marker passes too.
role_model_allow("role-model: reviewer on sonnet with the guard marker on line 1 is allowed", "reviewer", "sonnet",
                 REVIEW_GUARD_MARKER + "\nCheck the guard diff.")
role_model_allow("role-model: reviewer on sonnet with the guard marker on line 3 is allowed", "reviewer", "sonnet",
                 "Check the diff.\nThe lane is c204.\n" + REVIEW_GUARD_MARKER)
role_model_allow("role-model: reviewer on sonnet on Round 1 with the guard marker is allowed (round 1 runs on Sonnet "
                 "for a guard diff)", "reviewer", "sonnet", "Round 1 of 3. Check the guard diff.\n" + REVIEW_GUARD_MARKER)
role_model_allow("role-model: reviewer on sonnet with text after the guard marker on its line is allowed (it starts "
                 "with the marker)", "reviewer", "sonnet", REVIEW_GUARD_MARKER + ". The diff edits the guard.")
role_model_allow("role-model: reviewer on sonnet whose whole brief is the guard marker is allowed", "reviewer", "sonnet",
                 REVIEW_GUARD_MARKER)
role_model_allow("role-model: reviewer on sonnet with the guard marker at the end of a 400-line brief is allowed",
                 "reviewer", "sonnet", "Check the diff.\n" * 399 + REVIEW_GUARD_MARKER)
role_model_allow("role-model: reviewer on sonnet as a Task with the guard marker is allowed", "reviewer", "sonnet",
                 REVIEW_GUARD_MARKER + "\nCheck the guard diff.", tool="Task")
role_model_allow("role-model: reviewer on haiku with the guard marker is allowed (its own row)", "reviewer", "haiku",
                 REVIEW_GUARD_MARKER + "\nCheck the guard diff.")
# A marker line may start with leading blanks: the brief table's line-start rows allow them, and a brief indents its
# template line. The first-pass brief is the case, since only the marker lifts Sonnet there.
role_model_allow("role-model: reviewer on sonnet on Round 1 with the guard marker after two spaces is allowed", "reviewer",
                 "sonnet", "Round 1 of 3. Check the guard diff.\n  " + REVIEW_GUARD_MARKER)
role_model_allow("role-model: reviewer on sonnet on Round 1 with the guard marker after four spaces is allowed", "reviewer",
                 "sonnet", "Round 1 of 3. Check the guard diff.\n    " + REVIEW_GUARD_MARKER)
role_model_allow("role-model: reviewer on sonnet on Round 1 with the guard marker after a tab is allowed", "reviewer",
                 "sonnet", "Round 1 of 3. Check the guard diff.\n\t" + REVIEW_GUARD_MARKER)

# A reviewer on Sonnet is refused with no marker, with `no` as the value, with the marker mid-line, or in lowercase.
role_model_refuse("role-model: reviewer on sonnet with Guard or check: no is denied", "reviewer", "sonnet",
                  "Check the docs diff.\n" + GUARD_NO_LINE)
role_model_refuse("role-model: reviewer on sonnet on Round 1 with Guard or check: no is denied (round 1 stays on the row)",
                  "reviewer", "sonnet", "Round 1 of 3. Check the docs diff.\n" + GUARD_NO_LINE)
role_model_refuse("role-model: reviewer on sonnet with the guard marker mid-line is denied", "reviewer", "sonnet",
                  "Check the diff. " + REVIEW_GUARD_MARKER)
# The boundary read takes the character at the marker's length from the line start, so a mid-line marker can put a space
# there. It must still lift nothing. The case above reads `r` there and would pass a startswith swapped for `in`.
role_model_refuse("role-model: reviewer on sonnet with the guard marker mid-line, a space at the boundary offset, is denied",
                  "reviewer", "sonnet", "Review the " + REVIEW_GUARD_MARKER)
# A model the table does not rank sits above every row, so the marker lifts it no more than a Round N line does.
role_model_refuse("role-model: reviewer on an unranked model with the guard marker is denied (claude-mystery-9 is above "
                  "the row)", "reviewer", "claude-mystery-9", REVIEW_GUARD_MARKER + "\nCheck the guard diff.")
# A fenced block is quoted text, as cite-by-id reads it, so a marker line inside one is no marker. A fence that closes
# before the marker line leaves the marker a line of the brief, so it counts.
role_model_refuse("role-model: reviewer on sonnet whose only guard marker line sits inside a ``` fence is denied",
                  "reviewer", "sonnet", "Check the docs diff.\n" + MD_FENCE + "\n" + REVIEW_GUARD_MARKER + "\n" + MD_FENCE)
role_model_allow("role-model: reviewer on sonnet whose guard marker follows a closed ``` fence is allowed", "reviewer",
                 "sonnet", "Check the guard diff.\n" + MD_FENCE + "\nsome code\n" + MD_FENCE + "\n" + REVIEW_GUARD_MARKER)
role_model_refuse("role-model: reviewer on sonnet with the guard marker in lowercase is denied (case-sensitive)",
                  "reviewer", "sonnet", REVIEW_GUARD_MARKER.lower())
# The marker is `yes` with the end of the line, a space, a tab, a CR or a full stop after it. A `|`, a `-` or a letter after yes (the
# template line `Guard or check: yes|no`, `yesterday`, `yes-ish`) is not that value, so those lift nothing.
role_model_refuse("role-model: reviewer on sonnet with the template line Guard or check: yes|no is denied",
                  "reviewer", "sonnet", "Check the docs diff.\nGuard or check: yes|no")
role_model_refuse("role-model: reviewer on sonnet with Guard or check: yesterday is denied",
                  "reviewer", "sonnet", "Check the docs diff.\nGuard or check: yesterday")
role_model_refuse("role-model: reviewer on sonnet with Guard or check: yes-ish is denied",
                  "reviewer", "sonnet", "Check the docs diff.\nGuard or check: yes-ish")
role_model_allow("role-model: reviewer on sonnet with Guard or check: yes alone on its line is allowed",
                 "reviewer", "sonnet", "Check the guard diff.\n" + REVIEW_GUARD_MARKER)
role_model_allow("role-model: reviewer on sonnet with Guard or check: yes and a trailing space is allowed",
                 "reviewer", "sonnet", "Check the guard diff.\n" + REVIEW_GUARD_MARKER + " \nThe lane is c204.")
role_model_allow("role-model: reviewer on sonnet with Guard or check: yes then a parenthesis is allowed",
                 "reviewer", "sonnet", "Check the guard diff.\n" + REVIEW_GUARD_MARKER + " (`hooks/`)")
role_model_allow("role-model: reviewer on sonnet with Guard or check: yes then a full stop is allowed",
                 "reviewer", "sonnet", "Check the guard diff.\n" + REVIEW_GUARD_MARKER + ".")
role_model_allow("role-model: reviewer on sonnet with Guard or check: yes then a tab and text is allowed",
                 "reviewer", "sonnet", "Check the guard diff.\n" + REVIEW_GUARD_MARKER + "\tThe diff edits the guard.")
# A CRLF brief ends every line `\r\n`, so its marker line ends `yes\r`. The CR after yes is a line end, not text after it.
role_model_allow("role-model: reviewer on sonnet with a CRLF brief whose Guard or check: yes line ends CR is allowed",
                 "reviewer", "sonnet", "Check the guard diff.\r\n" + REVIEW_GUARD_MARKER + "\r\nThe lane is c204.\r\n")
# The blanks allowance does not make an indented template line a value: `yes|no` after the blanks is not yes.
role_model_refuse("role-model: reviewer on sonnet with the indented template line Guard or check: yes|no is denied",
                  "reviewer", "sonnet", "Check the docs diff.\n    Guard or check: yes|no")
# The blanks allowance does not reach into a fence: an indented marker line inside one is quoted text, as before.
role_model_refuse("role-model: reviewer on sonnet whose only indented guard marker line sits inside a ``` fence is denied",
                  "reviewer", "sonnet", "Check the docs diff.\n" + MD_FENCE + "\n  " + REVIEW_GUARD_MARKER + "\n" + MD_FENCE)
# A bulleted marker does not start its line: the allowance is for blanks only, so the `-` ahead of the marker still refuses.
role_model_refuse("role-model: reviewer on sonnet with a bulleted Guard or check: yes is denied", "reviewer", "sonnet",
                  "Check the docs diff.\n- " + REVIEW_GUARD_MARKER)
# The refusal names the marker beside the Round N of 3 remedy, as a reviewer's second way past its row.
role_model_refuse("role-model: reviewer on sonnet with no marker is denied, and names the guard marker beside the "
                  "Round N of 3 remedy", "reviewer", "sonnet", "Check the guard diff.",
                  carries=(ROLE_REMEDY, ROUND_MARKER, REVIEW_GUARD_MARKER) + FREE_ROUND_MARKERS)
# Opus stays refused under agent-model-cap, marker or not.
role_opus_refuse("role-model: reviewer on opus with the guard marker is denied under agent-model-cap", "reviewer", "opus",
                 REVIEW_GUARD_MARKER + "\nCheck the guard diff.")
# The marker lifts a reviewer only. Other roles stay refused, and their refusals name no guard marker.
role_model_refuse("role-model: test-author on sonnet with the guard marker is denied, and names no guard marker",
                  "test-author", "sonnet", "Write the failing cases.\n" + REVIEW_GUARD_MARKER,
                  lacks=ROLE_LACKS + (REVIEW_GUARD_MARKER,))
role_model_refuse("role-model: Explore on sonnet with the guard marker and no Audit: is denied, and names no guard marker",
                  "Explore", "sonnet", "Find where X is defined.\n" + REVIEW_GUARD_MARKER,
                  carries=(EXPLORE_MARKER,), lacks=ROLE_LACKS + (REVIEW_GUARD_MARKER,))

# A Workflow agent() call faces the same reading: a reviewer on Sonnet with the marker at a line start passes, and the
# marker mid-line, a `no` value, or Opus does not.
workflow_allow("role-model: Workflow reviewer on sonnet with the guard marker on line 1 is allowed",
               _step_flow("'%s. Check the guard diff.'" % REVIEW_GUARD_MARKER, "agentType: 'reviewer', model: 'sonnet'"))
workflow_refuse("role-model: Workflow reviewer on sonnet with the guard marker mid-line is denied under agent-role-model",
                _step_flow("'Check the guard diff. %s'" % REVIEW_GUARD_MARKER, "agentType: 'reviewer', model: 'sonnet'"),
                rule=ROLE_RULE, carries=(ROLE_REMEDY,), lacks=ROLE_LACKS)
workflow_refuse("role-model: Workflow reviewer on sonnet with Guard or check: no is denied under agent-role-model",
                _step_flow("'%s. Check the docs.'" % GUARD_NO_LINE, "agentType: 'reviewer', model: 'sonnet'"),
                rule=ROLE_RULE, carries=(ROLE_REMEDY,), lacks=ROLE_LACKS)
workflow_refuse("role-model: Workflow reviewer on opus with the guard marker is denied under agent-model-cap",
                _step_flow("'%s. Check the guard diff.'" % REVIEW_GUARD_MARKER, "agentType: 'reviewer', model: 'opus'"))


# ---- J: the round rows, one home (decision agent-model-cap). The record's round table names the model each round runs on, and
# the guard reads it, so a changed row changes the verdict with no code edit. A record with no round row, or no record at all,
# keeps the verdicts the role row and the step-up give.
ROUND_TABLE_HEAD = "| Role | Round | Model | Effort |\n|---|---|---|---|\n"
ROUND_HAIKU_TWO_POINTER = role_table("roundhaiku", ROLE_TABLE_RULES + "\n" + ROUND_TABLE_HEAD + "| reviewer | 2 | haiku | high |\n")
ROUND_HAIKU_TWO_CFG = role_config("roundhaiku", ROUND_HAIKU_TWO_POINTER)
# Case 3: the record's second-round row names haiku, so a second-round reviewer on haiku is allowed. Without that row, the
# constant step-up refuses it, so this case passes only because the row lifts that refusal.
role_model_allow("role-model: round row: a record whose reviewer round 2 row names haiku lets a round 2 reviewer run haiku",
                 "reviewer", "haiku", "Round 2 of 3. Re-check the diff.", config=ROUND_HAIKU_TWO_CFG)
# The same record does not open the first round without the guard marker: the first-round row does not lift an unmarked brief.
role_model_refuse("role-model: round row: a record whose reviewer round 2 row names haiku still denies an unmarked round 1 "
                  "reviewer on sonnet", "reviewer", "sonnet", "Round 1 of 3. Check the diff.", config=ROUND_HAIKU_TWO_CFG,
                  carries=(ROLE_REMEDY,))
# The record's first-round row names sonnet, so the first round is among the rows that lift a reviewer on sonnet. The refusal names
# the first round among those rounds and says the test-author runs on its role's model. The fallback's free-rounds literal is not read.
ROUND_SONNET_ONE_POINTER = role_table("roundsonnetone", ROLE_TABLE_RULES + "\n" + ROUND_TABLE_HEAD + "| reviewer | 1 other | sonnet | xhigh |\n")
ROUND_SONNET_ONE_CFG = role_config("roundsonnetone", ROUND_SONNET_ONE_POINTER)
add("role-model: round 1 free: reviewer on sonnet names round 1 among the free rounds, and says the test-author runs on its role's model",
    "deny", ROLE_RULE, tool="Agent", config=ROUND_SONNET_ONE_CFG,
    carries=("the test-author runs on its role's model", "review round 1 or 2 or 3", ROLE_REMEDY),
    lacks=ROLE_LACKS + (ROUND_ONE_SENTENCE,), **role_input("reviewer", "sonnet", "Check the diff for typos."))
# The record's third-round row names haiku, the reviewer's own row, so a third-round reviewer on sonnet is not lifted. The step-up
# does not decide first: the third round is not the exact round, and sonnet is not below haiku. The table read in role_model_one
# decides it.
ROUND_HAIKU_THREE_POINTER = role_table("roundhaikuthree", ROLE_TABLE_RULES + "\n" + ROUND_TABLE_HEAD + "| reviewer | 3 | haiku | xhigh |\n")
ROUND_HAIKU_THREE_CFG = role_config("roundhaikuthree", ROUND_HAIKU_THREE_POINTER)
role_model_refuse("role-model: round row: a record whose reviewer round 3 row names haiku denies a round 3 reviewer on sonnet",
                  "reviewer", "sonnet", "Round 3 of 3. Re-check the diff.", config=ROUND_HAIKU_THREE_CFG,
                  carries=(ROLE_REMEDY, "`Round 2 of 3`"), lacks=ROLE_LACKS + ("`Round 3 of 3`",))

# Case 4: with no decision record the round rows read as absent, and the spawn passes on the fallback rows.
role_model_allow("role-model: no decision record, a reviewer round 1 on sonnet with the guard marker passes silently",
                 "reviewer", "sonnet", "Round 1 of 3. Check the guard diff.\n" + REVIEW_GUARD_MARKER, config=ROLE_MISSING_CFG)
# A missing record must not turn the step-up's refusal of a second-round reviewer on haiku into an allow. The constant
# refuses it, and the record's absence changes nothing. The round-row reader must keep this refusal.
add("role-model: no decision record still refuses a round 2 reviewer on haiku at the step-up", "deny", STEP_UP,
    tool="Agent", config=ROLE_MISSING_CFG, carries=("Reviewer round 2 runs on Sonnet.",),
    **role_input("reviewer", "haiku", "Round 2 of 3. Re-check the diff."))


LOG_CHECKS = LOG_CHECKS + tuple(LOG_CHECKS_EXTRA)

# The log checkers tagged "windows". Each one reads a live process's start time (guard.py
# L1837-1905, the ctypes arm on Windows) or a PowerShell tokenizing rule (L307-320).
WINDOWS_CHECKERS = {
    powershell_backslash_case,
    wsl_script_tag_keeps_backslash_case,
    wsl_split_tag_keeps_backslash_case,
    process_start_ms_case,
    process_start_ms_windows_case,
    session_is_live_case,
    session_is_live_backwards_clock_step_case,
    worktree_live_session_unreadable_case,
    worktree_live_session_two_spellings_case,
    worktree_live_session_path_unresolvable_case,
    # Each reads a `/c/` cwd through the Windows drive conversion, so it runs in the Windows slice.
    worktree_home_cwd_merge_case,
    worktree_home_cwd_shared_tree_case,
    worktree_home_cwd_builder_case,
    worktree_home_cwd_frozen_case,
    worktree_home_cwd_config_case,
    worktree_home_cwd_cap_case,
}
# audit-high: the fail-closed checks read no Windows-only code, but the Windows slice runs on
# every pull request, and a missing sibling is the Windows incident. They run in that slice too.
WINDOWS_CHECKERS.update(FAILCLOSED_CHECKS)
# load-brake: the checks that reach the real reader, whose Windows arm is ctypes (GlobalMemoryStatusEx
# and a process snapshot) that no Linux run exercises.
WINDOWS_CHECKERS.update(LB_CHECKS)
# override: a one-act override claimed by a rename let two Windows racers win (run 40296652083), and no
# Linux run shows it, so the claim cases run in the Windows slice.
WINDOWS_CHECKERS.update({ov_parallel_check, ov_take_race_check, ov_late_reader_check})


# --------------------------------------------------------------------------- the simulator boot rules
