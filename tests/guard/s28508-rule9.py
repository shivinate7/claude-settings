# section 28508
FAMILY = "rule9"
# ---- Rule 9, the agent model floor. Both directions: Haiku in any spelling is denied, and
# every other model, or none, is allowed.
# SPAWN_TOOLS lists Task as well as Agent, so Task keeps one floor row. The rest name Agent.
# A full model id is the same branch as its short name, so the rows use the short names.
add("floor: Agent with model haiku is denied", "deny", "agent-model-floor",
    tool="Agent", prompt="do it", model="haiku")
add("floor: Task with model haiku is denied", "deny", "agent-model-floor",
    tool="Task", prompt="do it", model="haiku")
add("floor: Agent with a mixed-case haiku spelling is denied", "deny", "agent-model-floor",
    tool="Agent", prompt="do it", model="Claude-HAIKU-4-5")
add("floor: Agent with a list model naming haiku is denied", "deny", "agent-model-floor",
    tool="Agent", prompt="do it", model=["haiku"])
add("floor: Agent with model sonnet is allowed", "allow", tool="Agent", prompt="x", model="sonnet")
add("floor: Agent with no model is allowed", "allow", tool="Agent", prompt="x")

# ---- Rule 9, Haiku roles (owner ruling 2026-10-07). Haiku is allowed only for Explore,
# claude-code-guide, test-author and reviewer. Failure classes: false deny (a listed role blocked),
# false allow (a non-listed role, a near-miss name, or a missing role slips through).
HAIKU_ROLES = ("Explore", "claude-code-guide", "test-author", "reviewer", "record-writer")
HAIKU_MODELS = ("haiku",)
for _tool in ("Agent",):
    for _role in HAIKU_ROLES:
        for _model in HAIKU_MODELS:
            add("floor: %s %s with model %s is allowed" % (_tool, _role, _model), "allow",
                tool=_tool, prompt="do it", model=_model, subagent_type=_role)
    for _role in ("builder", "Plan", "general-purpose", "claude", "reviewer-lite", "not-explore"):
        add("floor: %s %s with model haiku is denied" % (_tool, _role), "deny",
            "agent-model-floor", tool=_tool, prompt="do it", model="haiku", subagent_type=_role)
add("floor: Agent with an empty subagent_type and haiku is denied", "deny", "agent-model-floor",
    tool="Agent", prompt="do it", model="haiku", subagent_type="")
add("floor: Agent with a list role and haiku is denied", "deny", "agent-model-floor",
    tool="Agent", prompt="do it", model="haiku", subagent_type=["reviewer"])
add("floor: Agent builder with model sonnet is still allowed", "allow",
    tool="Agent", prompt="x", model="sonnet", subagent_type="builder")
# The floor's remedy names Sonnet only. Opus is refused above a builder's row, so a remedy that names it
# would send the owner into the Opus refusal (decision agent-model-cap).
add("floor: Agent builder with model haiku names sonnet, and not opus", "deny", "agent-model-floor",
    carries=("model sonnet",), lacks=("opus", "Opus"),
    tool="Agent", prompt="do it", model="haiku", subagent_type="builder")
# An Explore on Opus runs only when its brief's first non-blank line carries the Audit: marker. Without it the
# Opus ceiling refuses it, and an owner override lifts it (decision agent-model-cap).
add("floor: Agent Explore with model opus and no Audit: marker is denied (item 137)", "deny",
    "agent-model-cap", tool="Agent", prompt="do it", model="opus", subagent_type="Explore")
add("floor: Agent Explore with model opus and Audit: on line one is allowed (item 137)", "allow",
    tool="Agent", prompt="Audit: check the glossary for meaning drift.", model="opus", subagent_type="Explore")
# record-writer (owner ruling 2026-10-10): Haiku is allowed only for the exact role name. A
# near-miss name is another role, so it is denied, the same as `reviewer-lite` above.
for _tool in ("Agent",):
    for _near in ("record-writers", "Record-Writer", "record_writer", "record-writer "):
        add("floor: %s %r with model haiku is denied" % (_tool, _near), "deny",
            "agent-model-floor", tool=_tool, prompt="do it", model="haiku",
            subagent_type=_near)
# record-writer on sonnet was allowed here until the role table denied it (the agent-role-model cases,
# near the end of this file, hold the new expectation).

# ---- Step-up (rule roles-third-round-steps-up, decision agent-model-cap). The brief's fixed form
# "Round N of 3" steps a reviewer up: the second needs sonnet, the third sonnet, and Opus is never an option for it.
# A builder's marker steps nothing up: its third try runs on its own row, Sonnet, so a builder on Opus is refused by the
# Opus ceiling and no marker lifts that refusal.
# A reviewer's third review on Opus is refused under agent-role-model with the remedy `use sonnet` and no override line. The
# middle step-up stays sonnet only.
# A reviewer's round 1 runs on the role's table model. Prose that quotes a round without the
# fixed form is never a signal. A missing model is not read from the env default by the floor,
# so the floor allows it. Step-up still denies a reviewer round 2 that does not name sonnet, and
# a round 2 or round 3 that names haiku or inherit (pinned below).
STEP_UP ="roles-third-round-steps-up"
add("floor step-up: reviewer Round 2 of 3 on haiku is denied", "deny", STEP_UP,
    tool="Agent", prompt="Round 2 of 3. Re-check the diff.", model="haiku", subagent_type="reviewer")
add("floor step-up: reviewer Round 3 of 3 on haiku is denied", "deny", STEP_UP,
    tool="Agent", prompt="Round 3 of 3. Re-check the diff.", model="haiku", subagent_type="reviewer")
# The remedy names Sonnet only: Opus is refused above the reviewer's row, so it is no remedy (item 127 pick a).
add("floor step-up: reviewer Round 3 of 3 on haiku names sonnet, and not Sonnet or Opus", "deny", STEP_UP,
    carries=("Reviewer round 3 runs on Sonnet.",), lacks=("Sonnet or Opus",),
    tool="Agent", prompt="Round 3 of 3. Re-check the diff.", model="haiku", subagent_type="reviewer")
add("floor step-up: reviewer Round 2 of 3 on opus is denied (ceiling)", "deny", STEP_UP,
    tool="Agent", prompt="Round 2 of 3. Re-check the diff.", model="opus", subagent_type="reviewer")
add("floor step-up: reviewer Round 2 of 3 on sonnet is allowed", "allow",
    tool="Agent", prompt="Round 2 of 3. Re-check the diff.", model="sonnet", subagent_type="reviewer")
add("floor step-up: reviewer Round 2 of 3 with no model is denied (no sonnet named)", "deny",
    STEP_UP, tool="Agent", prompt="Round 2 of 3. Re-check the diff.", subagent_type="reviewer")
add("floor step-up: reviewer Round 3 of 3 with model inherit is denied", "deny", STEP_UP,
    tool="Agent", prompt="Round 3 of 3. Re-check the diff.", model="inherit",
    subagent_type="reviewer")
add("floor step-up: reviewer Round 2 of 3 on claude-sonnet-5-5 is allowed", "allow",
    tool="Agent", prompt="Round 2 of 3. Re-check the diff.", model="claude-sonnet-5-5",
    subagent_type="reviewer")
add("floor step-up: builder Try 3 of 3 on sonnet is allowed (its own row, no step-up)", "allow",
    tool="Agent", prompt="Try 3 of 3. Finish the fix.", model="sonnet", subagent_type="builder")
add("floor step-up: builder Try 3 of 3 on opus is denied (no standing grant)", "deny", "agent-model-cap",
    tool="Agent", prompt="Try 3 of 3. Finish the fix.", model="opus", subagent_type="builder")
add("floor step-up: builder Try 1 of 3 on opus is denied (no standing grant)", "deny",
    "agent-model-cap", tool="Agent", prompt="Try 1 of 3. Start the fix.", model="opus",
    subagent_type="builder")
add("floor step-up: reviewer Round 1 of 3 on haiku with prose round 2 and round 3 is allowed",
    "allow", tool="Agent", subagent_type="reviewer", model="haiku",
    prompt="Round 1 of 3. The earlier review round 2 and round 3 notes are in the record.")
add("floor step-up: reviewer with no round line on haiku is allowed", "allow",
    tool="Agent", prompt="Check the diff for typos.", model="haiku", subagent_type="reviewer")
add("floor step-up: round line after a lone quote on line two is denied", "deny", STEP_UP,
    tool="Agent", prompt="Don't skip the check.\nRound 2 of 3. Re-check the diff.",
    model="haiku", subagent_type="reviewer")
# A round line on line three steps up too: the step-up reads every line that starts with the marker.
add("floor step-up: reviewer Round 2 of 3 on line three on haiku is denied", "deny", STEP_UP,
    tool="Agent", prompt="Check the diff.\nThe lane is c204.\nRound 2 of 3. Re-check the diff.",
    model="haiku", subagent_type="reviewer")
add("floor step-up: reviewer Round 3 of 3 on sonnet is allowed", "allow",
    tool="Agent", prompt="Round 3 of 3. Re-check the diff.", model="sonnet", subagent_type="reviewer")
# A reviewer's third review on Opus, with no record to read its row, meets the Opus ceiling: no marker grants it. Its refusal
# under the role row, with no override line, is pinned where the record is read (s40805, s36421).
add("floor step-up: reviewer's last round on opus is denied by the Opus ceiling, with no record to read", "deny",
    "agent-model-cap", tool="Agent", prompt="Round 3 of 3. Re-check the diff.",
    model="claude-opus-5-5", subagent_type="reviewer")
add("floor step-up: builder Try 2 of 3 on sonnet is allowed", "allow",
    tool="Agent", prompt="Try 2 of 3. Continue the fix.", model="sonnet", subagent_type="builder")
# The builder marker is the `Round N of 3` line (plan o13 group 9: a review and its fix is a round).
# The old `Try N of 3` line still counts until the try-marker-sunset note removes it.
add("floor step-up: builder Round 3 of 3 on sonnet is allowed (its own row, no step-up)", "allow",
    tool="Agent", prompt="Round 3 of 3. Finish the fix.", model="sonnet", subagent_type="builder")
add("floor step-up: builder Round 3 of 3 with no model is allowed (the default runs sonnet, its row)", "allow",
    tool="Agent", prompt="Round 3 of 3. Finish the fix.", subagent_type="builder")
add("floor step-up: builder Round 3 of 3 on opus is denied (no standing grant)", "deny", "agent-model-cap",
    tool="Agent", prompt="Round 3 of 3. Finish the fix.", model="opus", subagent_type="builder")
add("floor step-up: builder Round 2 of 3 on sonnet is allowed", "allow",
    tool="Agent", prompt="Round 2 of 3. Continue the fix.", model="sonnet", subagent_type="builder")
add("floor step-up: builder Round 1 of 3 on opus is denied (no standing grant)", "deny",
    "agent-model-cap", tool="Agent", prompt="Round 1 of 3. Start the fix.", model="opus",
    subagent_type="builder")
# ---- Step-up, a fix verifier (decision agent-model-cap, the reviewer row). A reviewer whose brief's first non-blank
# line is `Fix check` runs Sonnet, set per spawn, so the step-up refuses it on Haiku or with no model, as it refuses a
# later-round brief. Sonnet passes; Opus stays under the ceiling. The spelling is typed here, so a rename of the marker
# constant cannot quietly change what these cases pin. This section loads before the names are read (s30130 and s40805
# read them), and s40805's fix verifier checks fail if FIX_CHECK_MARKER is renamed. Failure classes: a false allow (a fix
# verifier on Haiku or with no model runs Haiku); a false refusal (a builder, or a marker not on line one, is refused).
FIX_VERIFIER = "Fix check"
FIX_BRIEF = FIX_VERIFIER + ". Re-check the diff."
FIX_VERIFIER_REASON = "Reviewer fix verifier runs on Sonnet. Spawn it with model sonnet."
add("floor step-up: reviewer fix verifier with no model is denied, and names Sonnet", "deny", STEP_UP,
    tool="Agent", prompt=FIX_BRIEF, subagent_type="reviewer", carries=(FIX_VERIFIER_REASON,), lacks=("Opus",))
add("floor step-up: reviewer fix verifier on haiku is denied, and names Sonnet", "deny", STEP_UP,
    tool="Agent", prompt=FIX_BRIEF, model="haiku", subagent_type="reviewer", carries=(FIX_VERIFIER_REASON,), lacks=("Opus",))
add("floor step-up: reviewer fix verifier on sonnet is allowed", "allow",
    tool="Agent", prompt=FIX_BRIEF, model="sonnet", subagent_type="reviewer")
# Opus is not a step-up grant for a fix verifier: the Opus ceiling refuses it under its own rule, as it does today.
add("floor step-up: reviewer fix verifier on opus is denied under agent-model-cap, the ceiling as before", "deny",
    "agent-model-cap", tool="Agent", prompt=FIX_BRIEF, model="opus", subagent_type="reviewer")
# The marker is a reviewer's: a builder's fix verifier is judged as the same brief without it.
add("floor step-up: builder fix verifier on sonnet is allowed", "allow",
    tool="Agent", prompt=FIX_BRIEF, model="sonnet", subagent_type="builder")
add("floor step-up: builder fix verifier with no model is allowed", "allow",
    tool="Agent", prompt=FIX_BRIEF, subagent_type="builder")
# The marker counts on the first non-blank line, opening it. On line two, or after prose on line one, it is prose.
add("floor step-up: reviewer with the fix verifier on line two, on haiku, is allowed", "allow",
    tool="Agent", prompt="Check the diff.\n" + FIX_BRIEF, model="haiku", subagent_type="reviewer")
add("floor step-up: reviewer with prose ahead of the fix verifier on line one, on haiku, is allowed", "allow",
    tool="Agent", prompt="Re: " + FIX_VERIFIER + " of PR 7. Re-check the diff.", model="haiku", subagent_type="reviewer")
# The round form of the marker, a round line with the fix words after it, is read by the round row, so that row keeps its reason.
ROUND_TWO_FIX = "Round 2 of 3 (fix check). Re-check the diff."
add("floor step-up: reviewer Round 2 of 3 fix verifier with no model is denied, with the round-2 reason", "deny",
    STEP_UP, tool="Agent", prompt=ROUND_TWO_FIX, subagent_type="reviewer",
    carries=("Reviewer round 2 runs on Sonnet.",))
add("floor step-up: reviewer Round 2 of 3 fix verifier on haiku is denied", "deny", STEP_UP,
    tool="Agent", prompt=ROUND_TWO_FIX, model="haiku", subagent_type="reviewer")
add("floor step-up: reviewer Round 2 of 3 fix verifier on sonnet is allowed", "allow",
    tool="Agent", prompt=ROUND_TWO_FIX, model="sonnet", subagent_type="reviewer")
# The role is matched without case or surrounding space, as role_key reads it (decision agent-model-cap), and a blank
# model is no model. Failure classes: a false allow (a reviewer spelled `Reviewer` or ` reviewer `, or with a blank
# model, on a fix verifier or a later-round brief runs Haiku); a false refusal (a padded Sonnet model, or a builder
# spelled `Builder`, is refused).
add("floor step-up: reviewer spelled Reviewer, fix verifier with no model is denied, and names Sonnet", "deny", STEP_UP,
    tool="Agent", prompt=FIX_BRIEF, subagent_type="Reviewer", carries=(FIX_VERIFIER_REASON,), lacks=("Opus",))
add("floor step-up: reviewer spelled with surrounding spaces, fix verifier with no model is denied, and names Sonnet",
    "deny", STEP_UP, tool="Agent", prompt=FIX_BRIEF, subagent_type=" reviewer ", carries=(FIX_VERIFIER_REASON,),
    lacks=("Opus",))
add("floor step-up: reviewer spelled Reviewer, Round 2 of 3 with no model is denied, with the round-2 reason", "deny",
    STEP_UP, tool="Agent", prompt="Round 2 of 3. Re-check the diff.", subagent_type="Reviewer",
    carries=("Reviewer round 2 runs on Sonnet.",))
add("floor step-up: reviewer fix verifier with a blank model is denied, and names Sonnet", "deny", STEP_UP,
    tool="Agent", prompt=FIX_BRIEF, model="  ", subagent_type="reviewer", carries=(FIX_VERIFIER_REASON,), lacks=("Opus",))
add("floor step-up: reviewer spelled Reviewer, fix verifier on sonnet is allowed", "allow",
    tool="Agent", prompt=FIX_BRIEF, model="sonnet", subagent_type="Reviewer")
add("floor step-up: reviewer spelled with surrounding spaces, fix verifier on sonnet is allowed", "allow",
    tool="Agent", prompt=FIX_BRIEF, model="sonnet", subagent_type=" reviewer ")
add("floor step-up: reviewer spelled Reviewer, Round 2 of 3 on sonnet is allowed", "allow",
    tool="Agent", prompt="Round 2 of 3. Re-check the diff.", model="sonnet", subagent_type="Reviewer")
add("floor step-up: reviewer fix verifier with a padded sonnet model is allowed", "allow",
    tool="Agent", prompt=FIX_BRIEF, model=" sonnet ", subagent_type="reviewer")
add("floor step-up: builder spelled Builder, fix verifier with no model is allowed", "allow",
    tool="Agent", prompt=FIX_BRIEF, subagent_type="Builder")
# A Workflow agent() call steps up the same way, read statically. The prompt is the first argument
# or a `prompt` key. A prompt, model or options object the scan cannot read as plain literals is
# unseen and passes.
# Failure classes: a false allow (a stepped-up reviewer with no model runs the Haiku pin), a false deny
# (a model or prompt set through code the scan cannot read).


def _step_flow(prompt, opts):
    return "const r = await agent(%s, {%s}); return r" % (prompt, opts)


for _name, _verdict, _script in (
        ("reviewer Round 2 with no model", "deny",
         _step_flow("'Round 2 of 3. Re-check the diff.'", "agentType: 'reviewer'")),
        ("reviewer Round 2 on sonnet", "allow",
         _step_flow("'Round 2 of 3. Re-check the diff.'", "agentType: 'reviewer', model: 'sonnet'")),
        ("reviewer Round 3 on haiku", "deny",
         _step_flow("'Round 3 of 3. Re-check.'", "agentType: 'reviewer', model: 'haiku'")),
        # A builder's marker steps nothing up: its third try runs on its own row, Sonnet. Its Opus
        # spawns are refused below, by the Opus ceiling.
        ("builder Try 3 on sonnet, its own row", "allow",
         _step_flow('"Try 3 of 3. Finish the fix."', 'agentType: "builder", model: "sonnet"')),
        ("builder Round 3 on sonnet, its own row", "allow",
         _step_flow('"Round 3 of 3. Finish the fix."', 'agentType: "builder", model: "sonnet"')),
        ("builder Round 3 with no model, the default runs sonnet", "allow",
         _step_flow("'Round 3 of 3. Finish the fix.'", "agentType: 'builder'")),
        ("builder Round 3 after a role word on line one, on sonnet", "allow",
         _step_flow("'Builder, Round 3 of 3. Finish the fix.'", "agentType: 'builder', model: 'sonnet'")),
        ("builder Round 3 as a prompt key on sonnet", "allow",
         "await agent({prompt: 'Round 3 of 3. Finish.', agentType: 'builder', model: 'sonnet'})"),
        # The first-line marker is read on a reviewer, where the step-up still acts on it.
        ("reviewer Round 2 after a role word on line one with no model", "deny",
         _step_flow("'Builder, Round 2 of 3. Re-check.'", "agentType: 'reviewer'")),
        ("reviewer Round 1 after a role word on line one with no model", "allow",
         _step_flow("'Builder, Round 1 of 3. Re-check.'", "agentType: 'reviewer'")),
        ("builder Round 2 on sonnet", "allow",
         _step_flow("'Round 2 of 3. Continue the fix.'", "agentType: 'builder', model: 'sonnet'")),
        ("reviewer Round 1 with no model", "allow",
         _step_flow("'Round 1 of 3. Check the diff.'", "agentType: 'reviewer'")),
        ("reviewer Round 2 with the model in a variable", "allow",
         _step_flow("'Round 2 of 3. Re-check.'", "agentType: 'reviewer', model: m")),
        ("reviewer Round 2 with a shorthand model", "allow",
         _step_flow("'Round 2 of 3. Re-check.'", "agentType: 'reviewer', model")),
        ("reviewer Round 2 with a spread", "allow",
         _step_flow("'Round 2 of 3. Re-check.'", "agentType: 'reviewer', ...opts")),
        ("reviewer Round 2 with a templated model", "allow",
         _step_flow("'Round 2 of 3. Re-check.'", "agentType: 'reviewer', model: `${fam}`")),
        ("reviewer with the prompt in a variable", "allow",
         _step_flow("brief", "agentType: 'reviewer'")),
        ("reviewer with a concatenated prompt", "allow",
         _step_flow("'Round 2 of 3. ' + rest", "agentType: 'reviewer'")),
        ("reviewer Round 2 in an interpolated template prompt", "deny",
         _step_flow("`Round 2 of 3. ${rest}`", "agentType: 'reviewer'")),
        ("reviewer Round 2 on line two of an interpolated template on haiku", "deny",
         _step_flow("`Role: reviewer.\\nRound 2 of 3.\\nBranch ${b}`",
                    "agentType: 'reviewer', model: 'haiku'")),
        ("reviewer Round 2 as an interpolated prompt key with no model", "deny",
         "await agent({prompt: `Round 2 of 3. Branch ${b}`, agentType: 'reviewer'})"),
        ("reviewer whose marker is only interpolated", "allow",
         _step_flow("`${'Round 2 of 3.'} Re-check.`", "agentType: 'reviewer'")),
        ("reviewer whose round number is interpolated", "allow",
         _step_flow("`Round ${n} of 3. Re-check.`", "agentType: 'reviewer'")),
        ("reviewer whose marker is split by an interpolation", "allow",
         _step_flow("`Round 2${x} of 3. Re-check.`", "agentType: 'reviewer'")),
        ("reviewer Round 1 in an interpolated template", "allow",
         _step_flow("`Round 1 of 3. Branch ${b}`", "agentType: 'reviewer'")),
        ("reviewer Round 2 after an escaped newline and tab", "deny",
         _step_flow("'ctx\\n\\tRound 2 of 3.'", "agentType: 'reviewer'")),
        ("reviewer Round 2 in a template prompt with no model", "deny",
         _step_flow("`Round 2 of 3. Re-check the diff.`", "agentType: 'reviewer'")),
        ("reviewer Round 2 on line two of an escaped prompt", "deny",
         _step_flow("'Context first.\\nRound 2 of 3. Re-check.'", "agentType: 'reviewer'")),
        ("reviewer Round 2 as a prompt key with no model", "deny",
         "await agent({prompt: 'Round 2 of 3. Re-check.', agentType: 'reviewer'})"),
        ("reviewer Round 2 as a prompt key on sonnet", "allow",
         "await agent({prompt: 'Round 2 of 3. Re-check.', agentType: 'reviewer', model: 'sonnet'})"),
        ("reviewer with a ternary agentType", "allow",
         _step_flow("'Round 2 of 3. Re-check.'", "agentType: x ? 'reviewer' : 'builder'")),
        ("prose round 2 only", "allow",
         _step_flow("'The round 2 of 3 notes are in the record.'", "agentType: 'reviewer'")),
        ("a commented-out Round 2 call", "allow",
         "// agent('Round 2 of 3.', {agentType: 'reviewer'})\nawait agent('x', {model: 'sonnet'})")):
    add("floor step-up: Workflow %s is %s" % (_name, "denied" if _verdict == "deny" else "allowed"),
        _verdict, *((STEP_UP,) if _verdict == "deny" else ()), tool="Workflow", script=_script)
# A builder on Opus has no standing grant on a Workflow agent() call either, so the Opus ceiling refuses it.
for _name, _script in (
        ("builder Try 3 on opus", _step_flow('"Try 3 of 3. Finish the fix."', 'agentType: "builder", model: "opus"')),
        ("builder Round 3 on opus", _step_flow('"Round 3 of 3. Finish the fix."', 'agentType: "builder", model: "opus"')),
        ("builder Round 3 after a role word on line one, on opus",
         _step_flow("'Builder, Round 3 of 3. Finish the fix.'", "agentType: 'builder', model: 'opus'"))):
    add("floor step-up: Workflow %s is denied under agent-model-cap" % _name, "deny", "agent-model-cap",
        tool="Workflow", script=_script)
# A reviewer's last step-up is a per-spawn word, so the Opus ceiling refuses it on a Workflow agent() call as on an
# Agent spawn (decision agent-model-cap). Its refusal is the never-lifted third-review refusal.
add("floor step-up: Workflow reviewer's last round on opus is denied by the Opus ceiling, with no record to read", "deny",
    "agent-model-cap", tool="Workflow",
    script=_step_flow("'Round 3 of 3. Re-check.'", "agentType: 'reviewer', model: 'opus'"))
# A literal fix verifier on a Workflow reviewer. The step-up judges a call that names no model (decision agent-model-cap),
# so the literal form with no model is refused, as the round-2 form is. A brief, a model or an options object the scan
# cannot read is skipped, so those forms pass.
FIX_SCRIPT = _step_flow("'%s. Re-check the diff.'" % FIX_VERIFIER, "agentType: 'reviewer'")
add("floor step-up: Workflow reviewer with a literal fix verifier and no model is denied, as round 2 is", "deny",
    STEP_UP, tool="Workflow", script=FIX_SCRIPT)
add("floor step-up: Workflow reviewer with a literal fix verifier on haiku is denied", "deny", STEP_UP,
    tool="Workflow", script=_step_flow("'%s. Re-check the diff.'" % FIX_VERIFIER, "agentType: 'reviewer', model: 'haiku'"))
add("floor step-up: Workflow reviewer with a literal fix verifier on sonnet is allowed", "allow",
    tool="Workflow", script=_step_flow("'%s. Re-check the diff.'" % FIX_VERIFIER, "agentType: 'reviewer', model: 'sonnet'"))
add("floor step-up: Workflow reviewer with a fix verifier in a variable brief and no model is allowed, the static read skips it",
    "allow", tool="Workflow",
    script="const brief = '%s. Re-check the diff.';\n" % FIX_VERIFIER + _step_flow("brief", "agentType: 'reviewer'"))
add("floor step-up: Workflow reviewer with a fix verifier and a model in a variable is allowed, the static read skips it",
    "allow", tool="Workflow", script=_step_flow("'%s. Re-check the diff.'" % FIX_VERIFIER, "agentType: 'reviewer', model: m"))
add("floor step-up: Workflow reviewer with a fix verifier and a spread is allowed, the static read skips it", "allow",
    tool="Workflow", script=_step_flow("'%s. Re-check the diff.'" % FIX_VERIFIER, "agentType: 'reviewer', ...opts"))

# ---- Rule 9, the Opus ceiling (decision agent-model-cap). An Agent or Task spawn that sets model opus is
# refused under `agent-model-cap`, unless a standing grant covers it: Plan, the designer, and an Explore whose brief
# carries the Audit: marker. The design reviewer runs Sonnet high, and a builder's marker grants nothing.
# An owner override
# lifts the refusal. A reviewer's last step-up is a per-spawn word, so it is refused too. The floor and the step-up
# deny first, so the middle step-up on opus above stays a deny. The deny cases stay in the floor and step-up blocks,
# and the sonnet and haiku controls sit there too: floor_hit and step_up_hit judge them as before.
# Failure classes: a false allow (an Opus spawn of any spelling or role passes unasked, or a marker
# the role does not own earns the grant), a false refusal (a standing grant, a Sonnet spawn, or text that
# only names opus is refused).
CEILING = "agent-model-cap"
add("ceiling: Agent with model opus and no role is denied", "deny", CEILING, tool="Agent", prompt="x",
    model="opus", carries=(("opus", "Opus"),))
add("ceiling: Task with model opus is denied", "deny", CEILING, tool="Task", prompt="x", model="opus")
for _spelling in ("claude-opus-5-5", "Claude-OPUS-5-5", ["opus"]):
    add("ceiling: Agent with the model spelled %r is denied" % (_spelling,), "deny", CEILING,
        tool="Agent", prompt="x", model=_spelling)
for _role in ("claude", "general-purpose", "builder", "reviewer", "test-author", "record-writer",
              "Planner"):
    add("ceiling: Agent %s with model opus and no standing grant is denied" % _role, "deny", CEILING,
        tool="Agent", prompt="do it", model="opus", subagent_type=_role)
add("ceiling: Agent Plan with model opus is allowed (standing grant)", "allow",
    tool="Agent", prompt="Design the plan.", model="opus", subagent_type="Plan")
add("ceiling: Task Plan with model claude-opus-5-5 is allowed (standing grant)", "allow",
    tool="Task", prompt="Design the plan.", model="claude-opus-5-5", subagent_type="Plan")
# The designer runs Opus by the owner's standing grant (decision design-agents). The design reviewer does not: its row
# is Sonnet high. A near-miss role name earns no grant.
for _tool, _model in (("Agent", "opus"), ("Task", "claude-opus-5-5")):
    add("ceiling: %s designer on %s is allowed (standing grant)" % (_tool, _model), "allow",
        tool=_tool, prompt="Draw the mockup.", model=_model, subagent_type="designer")
for _tool, _model in (("Agent", "opus"), ("Task", "claude-opus-5-5")):
    add("ceiling: %s design-reviewer on %s is denied (its row is sonnet, no standing grant)" % (_tool, _model), "deny",
        CEILING, tool=_tool, prompt="Review the screen.", model=_model, subagent_type="design-reviewer")
for _role in ("design", "designers", "design-review", "Designer"):
    add("ceiling: Agent %s on opus is denied (no standing grant)" % _role, "deny", CEILING,
        tool="Agent", prompt="Draw the mockup.", model="opus", subagent_type=_role)
add("ceiling: Agent builder Try 3 of 3 on the full opus id is denied (no standing grant)", "deny", CEILING,
    tool="Agent", prompt="Try 3 of 3. Finish the fix.", model="claude-opus-5-5",
    subagent_type="builder")
add("ceiling: Agent builder Round 3 of 3 on the full opus id is denied (no standing grant)", "deny", CEILING,
    tool="Agent", prompt="Round 3 of 3. Finish the fix.", model="claude-opus-5-5",
    subagent_type="builder")
# The marker is a line of its own, as step_up_hit reads it. A lone quote and comment openers in the
# lines above it hide nothing: the reviewer's second-review marker on line two is still read and stepped up.
add("ceiling: Agent reviewer Round 2 of 3 on line two after a lone quote and comment openers, with no model, is denied",
    "deny", STEP_UP, tool="Agent", prompt="Don't skip /* the // check # now.\nRound 2 of 3. Re-check the diff.",
    subagent_type="reviewer")
add("ceiling: Agent builder Try 3 of 3 on line two after a lone quote and comment openers is denied (no standing grant)",
    "deny", CEILING, tool="Agent", prompt="Don't skip /* the // check # now.\nTry 3 of 3. Finish the fix.",
    model="opus", subagent_type="builder")
# A marker the role does not own, or one that is only prose, earns no grant.
for _role, _brief in (
        ("reviewer", "Try 3 of 3. Finish the fix."),
        ("general-purpose", "Try 3 of 3. Finish the fix."),
        ("test-author", "Try 3 of 3. Finish the fix."),
        ("builder", "Round 2 of 3. Finish the fix."),
        ("builder", "Try 2 of 3. Finish the fix."),
        ("builder", "This is not try 3 of 3, only the first pass."),
        ("builder", "Plan: Try 3 of 3 later, after the review.")):
    add("ceiling: Agent %s on opus with the brief %r is denied" % (_role, _brief[:24]), "deny", CEILING,
        tool="Agent", prompt=_brief, model="opus", subagent_type=_role)
# A brief may open with a role word before the marker, or wrap the marker in markup. The first
# non-blank line counts when it holds the marker anywhere, word-bounded. A later line counts only
# when it starts with the marker. Failure classes: a false refusal (a third-try builder on opus is refused
# because a word or markup sits before the marker), a false allow (a middle-step marker, a near-miss
# like "of 30", or the marker in later prose earns the grant; a reviewer behind a role word dodges
# its step-up).
# The first-line marker is read on a reviewer's second review, where the step-up acts on it: a role word, blank lines,
# markup, or a marker on line two each leave the marker read. A first-review control, with the same shapes, is allowed. A
# builder's marker steps nothing up, so a builder on Sonnet is allowed whatever its first line says.
FIRST_LINE_BRIEF = "Reviewer, Round 2 of 3. Lane c204 re-check the diff.\nFiles: hooks/guard.py."
add("first-line marker: reviewer with no model and a role word before Round 2 of 3 on line one is denied",
    "deny", STEP_UP, tool="Agent", prompt=FIRST_LINE_BRIEF, subagent_type="reviewer")
add("first-line marker: reviewer with no model and blank lines ahead of Round 2 of 3 is denied",
    "deny", STEP_UP, tool="Agent", prompt="\n \t\n" + FIRST_LINE_BRIEF, subagent_type="reviewer")
add("first-line marker: the same reviewer brief at Round 1 of 3 with no model is allowed", "allow",
    tool="Agent", prompt=FIRST_LINE_BRIEF.replace("Round 2", "Round 1"), subagent_type="reviewer")
add("first-line marker: a builder brief with a role word before Round 3 of 3 on sonnet is allowed (its own row)",
    "allow", tool="Agent", prompt="Builder, Round 3 of 3. Lane c204 fix the marker scan.\nFiles: hooks/guard.py.",
    model="sonnet", subagent_type="builder")
for _label, _first in (("a role word and a dash", "Reviewer — Round 2 of 3"),
                       ("bold markup", "**Round 2 of 3**"),
                       ("a heading mark", "## Round 2 of 3")):
    add("first-line marker: reviewer with no model whose first line is %s around the marker is denied" % _label,
        "deny", STEP_UP, tool="Agent", prompt=_first + "\nLane c204 re-check the diff.", subagent_type="reviewer")
add("first-line marker: reviewer with no model and the marker on its own line two is denied", "deny", STEP_UP,
    tool="Agent", prompt="Reviewer, lane c204: don't skip the scan.\nRound 2 of 3\nFiles: hooks/guard.py.",
    subagent_type="reviewer")
add("first-line marker: builder on opus with Round 2 of 3 on line one is denied", "deny", CEILING,
    tool="Agent", prompt="Builder, Round 2 of 3. Lane c204 continue the fix.", model="opus",
    subagent_type="builder")
add("first-line marker: builder on opus with Round 3 of 3 only in later prose is denied", "deny", CEILING,
    tool="Agent", model="opus", subagent_type="builder",
    prompt="Builder, lane c204: fix the marker scan.\nFiles: hooks/guard.py.\n"
           "Notes: the review said Round 3 of 3 is next, after this pass.")
for _label, _first in (("a longer total", "Builder, Round 3 of 30. Lane c204 fix the marker scan."),
                       ("a longer word before it", "Builder, Subround 3 of 3. Lane c204 fix the marker scan.")):
    add("first-line marker: builder on opus with %s on line one is denied" % _label, "deny", CEILING,
        tool="Agent", prompt=_first, model="opus", subagent_type="builder")
add("first-line marker: builder on opus with no marker in the brief is denied, and names the role's model",
    "deny", CEILING, tool="Agent", prompt="Builder. Lane c204 fix the marker scan.\nFiles: hooks/guard.py.",
    model="opus", subagent_type="builder", carries=("name the role's model",))
add("first-line marker: reviewer with no model and Round 2 of 3 after a role word on line one is denied",
    "deny", STEP_UP, tool="Agent", prompt="Reviewer, Round 2 of 3. Lane c204 re-check the diff.",
    subagent_type="reviewer")
# On the first line only the leftmost marker counts. A second marker later on that line is prose
# about another step, so it never earns the grant, never adds a step-up deny, and never hides the
# leftmost one.
TWO_MARKERS = "Builder, Round 2 of 3. Do not jump to Round 3 of 3 yet."
add("first-line marker: builder on opus with a later marker on line one after Round 2 of 3 is denied", "deny",
    CEILING, tool="Agent", prompt=TWO_MARKERS, model="opus", subagent_type="builder")
add("first-line marker: the same brief on sonnet is allowed", "allow", tool="Agent",
    prompt=TWO_MARKERS, model="sonnet", subagent_type="builder")
add("first-line marker: reviewer on opus with Round 3 of 3 first and Round 2 of 3 later is denied by the Opus ceiling, no step-up deny",
    "deny", CEILING, tool="Agent", model="opus", subagent_type="reviewer",
    prompt="Round 3 of 3. The Round 2 of 3 report found one defect.")
add("first-line marker: reviewer with no model, Round 1 of 3 first and Round 3 of 3 later, is allowed",
    "allow", tool="Agent", subagent_type="reviewer",
    prompt="Round 1 of 3: check that Round 3 of 3 logic works")
# A first line that already starts with a marker, in any case or spelling, is read by that start alone.
# A first line whose leftmost marker-shaped text is the old spelling adds nothing either. A later
# marker on the line is prose in both.
for _label, _first in (("the old spelling at the start", "Try 2 of 3. Do not jump to Round 3 of 3 yet."),
                       ("lowercase at the start", "round 2 of 3. Do not jump to Round 3 of 3 yet."),
                       ("the old spelling after a role word", "Builder, Try 2 of 3. Round 3 of 3 later.")):
    add("first-line marker: builder on opus with %s and a later Round 3 of 3 is denied" % _label, "deny", CEILING,
        tool="Agent", prompt=_first, model="opus", subagent_type="builder")
add("first-line marker: reviewer with no model, lowercase round 1 first and Round 2 of 3 later, is allowed",
    "allow", tool="Agent", subagent_type="reviewer",
    prompt="round 1 of 3: check Round 2 of 3 logic")
add("first-line marker: builder on sonnet with ROUND 2 OF 3 first and a later Round 3 of 3 gets no step-up refusal",
    "allow", tool="Agent", model="sonnet", subagent_type="builder",
    prompt="ROUND 2 OF 3 and Round 3 of 3")
# Text that only names opus is no model.
add("ceiling: Agent on sonnet whose brief names opus is allowed", "allow",
    tool="Agent", prompt="Use opus for the review.\nmodel: opus", model="sonnet",
    description="opus lane", subagent_type="general-purpose")
add("ceiling: Agent with no model whose brief names opus is allowed", "allow",
    tool="Agent", prompt="Run on model opus, as the owner said.", subagent_type="builder")
add("ceiling: Task on sonnet is allowed", "allow", tool="Task", prompt="x", model="sonnet",
    subagent_type="general-purpose")
sh("ceiling: a shell command that only names a spawn on opus is not a spawn",
   "echo spawn the agent with model opus", "allow", cwd=NOGIT)

# ---- Brief claims need a probe (rule brief-claim-has-probe). A brief to a builder or a test-author that claims what
# main, origin/main or "today" passes, allows, accepts or refuses for an input is refused, unless the brief carries
# the probe that showed it: a command line and its result line. A claim written from memory of main is the mistake
# this stops. Selector: MUTATE_ONLY=brief-claim: runs these cases alone. Each deny is red on a guard that lets the
# claim through. Each allow is a control the rule must leave alone.
BRIEF_PROBE = "brief-claim-has-probe"
REPRO_TEST_AUTHOR = ("Round 1 passed but found that the fix adds false alarms that main does not have.\n"
                     "Move `adHocKey: ...` and `globalHotkey: Ctrl+Alt+2` to the passing list: main passes both.\n"
                     "Also main passes `password: none for guests and visitors`.")
add("brief-claim: test-author brief that says main passes two inputs, with no probe, is denied",
    "deny", BRIEF_PROBE, tool="Agent", prompt=REPRO_TEST_AUTHOR, subagent_type="test-author")
add("brief-claim: builder brief that says main passes a password input, with no probe, is denied",
    "deny", BRIEF_PROBE, tool="Agent", prompt="Make these green; main passes `password: none for the guest`.",
    subagent_type="builder", model="sonnet")
add("brief-claim: builder brief that says origin/main accepts an input, with no command, is denied",
    "deny", BRIEF_PROBE, tool="Agent",
    prompt="Make the failing case green. origin/main accepts `user: root` as a valid name.",
    subagent_type="builder", model="sonnet", carries=(("probe", "command"),))
add("brief-claim: test-author brief that says today main refuses an input, with no command, is denied",
    "deny", BRIEF_PROBE, tool="Agent",
    prompt="Write the case. Today main refuses `port: 0`, so the new case expects a refusal.",
    subagent_type="test-author")
add("brief-claim: test-author brief that says today the guard refuses an input, with no main named, is denied",
    "deny", BRIEF_PROBE, tool="Agent", prompt="Write the case. Today it refuses `password: none for the guest`.",
    subagent_type="test-author")
add("brief-claim: builder brief that says main allows an input, with no probe, is denied",
    "deny", BRIEF_PROBE, tool="Agent", prompt="Keep the scan as it is. main allows `port: 0`.",
    subagent_type="builder", model="sonnet")
add("brief-claim: builder brief with a main claim and a result line but no command is denied",
    "deny", BRIEF_PROBE, tool="Agent", prompt="Keep the scan as it is.\nmain allows `port: 0`.\nPASS",
    subagent_type="builder", model="sonnet")
add("brief-claim: builder brief with a main claim and a command but no result line is denied",
    "deny", BRIEF_PROBE, tool="Agent",
    prompt="Keep the scan as it is.\nmain allows `port: 0`.\n`python3 hooks/probe_main.py 'port: 0'`",
    subagent_type="builder", model="sonnet")
add("brief-claim: test-author brief whose probe is for another input does not show the claim, and is denied",
    "deny", BRIEF_PROBE, tool="Agent",
    prompt="main refuses `password: none for the guest`.\n```\n$ python3 hooks/probe_main.py 'port: 0'\nrefused\n```",
    subagent_type="test-author")
LONG_BRIEF = "\n".join("Keep the export scan narrow. Line %d of the brief." % n for n in range(1, 30))
add("brief-claim: builder brief with the claim on line 30 of a long brief, with no probe, is denied",
    "deny", BRIEF_PROBE, tool="Agent", prompt=LONG_BRIEF + "\nNote: main refuses `password: none for the guest`.",
    subagent_type="builder", model="sonnet")
add("brief-claim: builder brief with a lone quote and an unmatched backtick around a main claim is denied",
    "deny", BRIEF_PROBE, tool="Agent",
    prompt="Don't skip the scan. Main refuses `password: none for the guest, and the guest passes.\nMake these green.",
    subagent_type="builder", model="sonnet")
add("brief-claim: builder brief with a main refusal and a fenced git show probe with its result is allowed",
    "allow", tool="Agent",
    prompt="Make these green. Main refuses `password: none for the guest`.\n```\n"
           "$ git show origin/main:hooks/guard.py | python3 -I - 'password: none for the guest'\n"
           "origin_main RRRR\n```",
    subagent_type="builder", model="sonnet")
add("brief-claim: test-author brief with a main refusal and an inline python3 probe with its refused line is allowed",
    "allow", tool="Agent",
    prompt="Main refuses `globalHotkey: Ctrl+Alt+2`.\n"
           "`python3 hooks/probe_main.py 'globalHotkey: Ctrl+Alt+2'`\nrefused",
    subagent_type="test-author")
add("brief-claim: builder brief with origin/main passes an input and a PASS result line is allowed",
    "allow", tool="Agent",
    prompt="origin/main passes `user: root`.\n$ python3 hooks/probe_main.py 'user: root'\nPASS",
    subagent_type="builder", model="sonnet")
add("brief-claim: builder brief with no claim about main is allowed",
    "allow", tool="Agent",
    prompt="Make these green. The guard must refuse `password: none for the guest` for every role.",
    subagent_type="builder", model="sonnet")
add("brief-claim: reviewer brief with the main claim is allowed (out of scope)",
    "allow", tool="Agent", prompt="Check the diff. Main passes `password: none for the guest`, so the fix is wrong.",
    subagent_type="reviewer")
add("brief-claim: Explore brief with the main claim is allowed (out of scope)",
    "allow", tool="Agent",
    prompt="Find where the guest password rule lives. Main passes `password: none for the guest`.",
    subagent_type="Explore")
add("brief-claim: designer brief with the main claim is allowed (out of scope)",
    "allow", tool="Agent", prompt="Draw the mockup. Main passes `password: none for the guest`.",
    subagent_type="designer")
add("brief-claim: main and today as plain words are allowed",
    "allow", tool="Agent",
    prompt="The main point of this lane is the probe rule. The main branch is the base. Today the lane starts on it.",
    subagent_type="builder", model="sonnet")
add("brief-claim: an empty brief is allowed", "allow", tool="Agent", prompt="", subagent_type="builder",
    model="sonnet")


# ---- A spawn's brief that orders a discard of the working tree (rule brief-destructive-git, rule
# shared-trees-no-destructive-git). An Agent, Task or Workflow brief is denied when a command span in it is one that
# shared_tree_match reads as a discard: a backtick span, a fenced line, or a line led by "$ ". A negation before the
# span on its line (never, do not, don't, no), a "Must deny:" or "Add a case:" line, prose with no span, a git span that
# discards nothing, and a repo under a session scratchpad are false alarms the rule must leave alone. Each deny is red
# on main, where no rule reads a brief. Selector: MUTATE_ONLY=brief-destructive-git: runs these cases and log checks.
BRIEF_DESTRUCTIVE = "brief-destructive-git"
# A session id is 8 or more characters, so a short folder name would not read as a scratchpad (in_any_session_scratchpad).
# The spans below single-quote this path: the brief reader tokenizes a span like bash, which drops the backslashes of an
# unquoted Windows path, so the path would stop reading as a scratchpad. The forward-slash form needs no quotes.
SCRATCH_REPO = os.path.join(ROOT, FAKE_SESSION, "scratchpad", "repo")
from agent_brief import COMMON  # noqa: E402  the standing-rules text the SubagentStart hook gives every agent
STANDING_LINE_ONE = "\n".join(text for _, text in COMMON[:2])   # the heading, then the first rule line
STANDING_ALL = "\n".join(text for _, text in COMMON)
# Paragraphs 7 to 12 of the brief that set these cases, as a brief would carry them. Paragraph 12's scratch path is the
# session-shaped one above, so the text reads the same way the rule reads it.
BRIEF_ALLOW_PARAGRAPHS = (
    'A prohibition: "Never run `git reset --hard`." and "Do not run `git stash`." '
    "(a negation word before the span on its line: never, do not, don't, no).\n"
    "Case data: a line that starts with `Must deny:` or `Add a case:` holding `git reset --hard`.\n"
    "The standing-rules text from hooks/agent_brief.py COMMON line 1 pasted in a brief.\n"
    'Prose with no command span: "the reset with the hard flag lost work".\n'
    "A non-discarding git span: `git reset HEAD file.py`, `git stash list`, `git status`.\n"
    "A scratch repo: `git -C '" + SCRATCH_REPO + "' reset --hard` (a path under a session scratchpad, as "
    "`in_any_session_scratchpad` reads it) passes, mirroring the shell guard, which allows the session's own scratchpad."
)
add("brief-destructive-git: builder brief that orders `git reset --hard origin/main` is denied", "deny",
    BRIEF_DESTRUCTIVE, tool="Agent", prompt="Then run `git reset --hard origin/main` and re-apply your change.",
    subagent_type="builder", model="sonnet")
add("brief-destructive-git: builder brief that orders the reset in a fenced block is denied", "deny",
    BRIEF_DESTRUCTIVE, tool="Agent",
    prompt="Undo the bad commit first.\n```\ngit reset --hard HEAD~1\n```\nThen re-apply your change.",
    subagent_type="builder", model="sonnet")
add("brief-destructive-git: builder brief with a `$ ` line that runs a bare git stash is denied", "deny",
    BRIEF_DESTRUCTIVE, tool="Agent", prompt="Set the work aside first.\n$ git stash\nThen redo the edit.",
    subagent_type="builder", model="sonnet")
add("brief-destructive-git: builder brief with a `$ ` line that runs git clean -fd is denied", "deny",
    BRIEF_DESTRUCTIVE, tool="Agent", prompt="Clear the untracked files.\n$ git clean -fd\nThen redo the edit.",
    subagent_type="builder", model="sonnet")
add("brief-destructive-git: builder brief that orders `git checkout -- .` in a backtick span is denied", "deny",
    BRIEF_DESTRUCTIVE, tool="Agent", prompt="Drop your edits: `git checkout -- .`, then redo the change.",
    subagent_type="builder", model="sonnet")
add("brief-destructive-git: Workflow agent prompt that holds `git reset --hard` is denied", "deny",
    BRIEF_DESTRUCTIVE, tool="Workflow",
    script=_step_flow("'Run `git reset --hard` and redo the edit.'", "agentType: 'builder', model: 'sonnet'"))
add("brief-destructive-git: Task spawn whose brief orders `git reset --hard origin/main` is denied", "deny",
    BRIEF_DESTRUCTIVE, tool="Task", prompt="Then run `git reset --hard origin/main` and re-apply your change.",
    subagent_type="builder", model="sonnet")
# The scanner reads a brief and a Workflow script as text, so each case below holds a comment opener in a string, a
# lone quote, or a multi-line template literal in front of the ordered reset.
add("brief-destructive-git: builder brief with a lone apostrophe before the ordered reset is denied", "deny",
    BRIEF_DESTRUCTIVE, tool="Agent",
    prompt="It's late. Then run `git reset --hard origin/main` and re-apply your change.",
    subagent_type="builder", model="sonnet")
add("brief-destructive-git: builder brief with a hash opener inside the reset span is denied", "deny",
    BRIEF_DESTRUCTIVE, tool="Agent",
    prompt="Then run `git reset --hard HEAD~1 # undo the change` and re-apply it.",
    subagent_type="builder", model="sonnet")
add("brief-destructive-git: Workflow reset after a // inside a string on the same line is denied", "deny",
    BRIEF_DESTRUCTIVE, tool="Workflow",
    script="const home = 'https://compass.example'; "
           + _step_flow("'Run `git reset --hard origin/main`.'", "agentType: 'builder', model: 'sonnet'"))
add("brief-destructive-git: Workflow reset after a /* inside a string on the same line is denied", "deny",
    BRIEF_DESTRUCTIVE, tool="Workflow",
    script="const tag = '/* keep */'; "
           + _step_flow("'Run `git reset --hard origin/main`.'", "agentType: 'builder', model: 'sonnet'"))
add("brief-destructive-git: Workflow reset in a multi-line template literal prompt is denied", "deny",
    BRIEF_DESTRUCTIVE, tool="Workflow",
    script="const r = await agent(`Keep the scan.\nRun \\`git reset --hard origin/main\\` and redo the edit.`, "
           "{agentType: 'builder', model: 'sonnet'}); return r")
add("brief-destructive-git: builder brief with the reset on line 30 of a long brief is denied", "deny",
    BRIEF_DESTRUCTIVE, tool="Agent",
    prompt=LONG_BRIEF + "\nThen run `git reset --hard origin/main` and re-apply your change.",
    subagent_type="builder", model="sonnet")
add("brief-destructive-git: builder brief that prohibits `git reset --hard` is allowed", "allow",
    tool="Agent", prompt="Never run `git reset --hard`.", subagent_type="builder", model="sonnet")
add("brief-destructive-git: builder brief that prohibits `git stash` is allowed", "allow",
    tool="Agent", prompt="Do not run `git stash`.", subagent_type="builder", model="sonnet")
add("brief-destructive-git: builder brief that prohibits `git clean -fd` with don't is allowed", "allow",
    tool="Agent", prompt="Don't run `git clean -fd`.", subagent_type="builder", model="sonnet")
add("brief-destructive-git: builder brief that prohibits `git checkout -- .` with no is allowed", "allow",
    tool="Agent", prompt="No `git checkout -- .` in this lane.", subagent_type="builder", model="sonnet")
add("brief-destructive-git: a Must deny line holding `git reset --hard` is allowed", "allow",
    tool="Agent", prompt="Must deny: `git reset --hard origin/main` is refused.",
    subagent_type="test-author")
add("brief-destructive-git: an Add a case line holding `git stash` is allowed", "allow",
    tool="Agent", prompt="Add a case: `git stash` on a dirty tree is denied.", subagent_type="test-author")
add("brief-destructive-git: the standing-rules heading and first rule from agent_brief COMMON are allowed", "allow",
    tool="Agent", prompt=STANDING_LINE_ONE, subagent_type="builder", model="sonnet")
add("brief-destructive-git: the whole standing-rules text from agent_brief COMMON is allowed", "allow",
    tool="Agent", prompt=STANDING_ALL, subagent_type="builder", model="sonnet")
add("brief-destructive-git: prose with the reset and the hard flag and no span is allowed", "allow",
    tool="Agent", prompt="Earlier, the reset with the hard flag lost work.", subagent_type="builder", model="sonnet")
add("brief-destructive-git: a reset that only unstages a path is allowed", "allow",
    tool="Agent", prompt="Run `git reset HEAD file.py` to unstage it.", subagent_type="builder", model="sonnet")
add("brief-destructive-git: git stash list is a read and is allowed", "allow",
    tool="Agent", prompt="Run `git stash list` to see the stack.", subagent_type="builder", model="sonnet")
add("brief-destructive-git: git status is allowed", "allow",
    tool="Agent", prompt="Run `git status`.", subagent_type="builder", model="sonnet")
add("brief-destructive-git: a reset --hard in a scratch repo under a session scratchpad is allowed", "allow",
    tool="Agent", prompt="Try it first: `git -C '" + SCRATCH_REPO + "' reset --hard`.",
    subagent_type="builder", model="sonnet")
add("brief-destructive-git: a reset --hard in a scratch repo named with forward slashes is allowed", "allow",
    tool="Agent", prompt="Try it first: `git -C " + SCRATCH_REPO.replace(os.sep, "/") + " reset --hard`.",
    subagent_type="builder", model="sonnet")
add("brief-destructive-git: the brief's own allow paragraphs, as a test-author brief, are allowed", "allow",
    tool="Agent", prompt=BRIEF_ALLOW_PARAGRAPHS, subagent_type="test-author")
add("brief-destructive-git: an empty brief is allowed", "allow",
    tool="Agent", prompt="", subagent_type="builder", model="sonnet")
# Brief-scan cases for these causes: a negation word the scan does not read, a Never heading over bullets, a read-only
# role, a branch or worktree act, a scratch segment joined to a reset, and an inline triple-backtick span.
add("brief-destructive-git: builder brief that says `git reset --hard` must not run is allowed", "allow",
    tool="Agent", prompt="You must not run `git reset --hard`.", subagent_type="builder", model="sonnet")
add("brief-destructive-git: builder brief that says `git reset --hard` should not run is allowed", "allow",
    tool="Agent", prompt="You should not run `git reset --hard`.", subagent_type="builder", model="sonnet")
add("brief-destructive-git: builder brief that says to avoid `git reset --hard` is allowed", "allow",
    tool="Agent", prompt="Avoid `git reset --hard`.", subagent_type="builder", model="sonnet")
add("brief-destructive-git: builder brief that says you cannot run `git reset --hard` is allowed", "allow",
    tool="Agent", prompt="You cannot run `git reset --hard`.", subagent_type="builder", model="sonnet")
add("brief-destructive-git: builder brief that says to work without `git reset --hard` is allowed", "allow",
    tool="Agent", prompt="Work without `git reset --hard`.", subagent_type="builder", model="sonnet")
add("brief-destructive-git: bullets under a `Never run:` heading that name `git reset --hard` and `git stash` are allowed",
    "allow", tool="Agent", prompt="Never run:\n- `git reset --hard`\n- `git stash`",
    subagent_type="builder", model="sonnet")
add("brief-destructive-git: reviewer brief that says `git reset --hard origin/main` is refused is allowed", "allow",
    tool="Agent", prompt="Confirm `git reset --hard origin/main` is refused.", subagent_type="reviewer", model="sonnet")
add("brief-destructive-git: Explore brief that says `git reset --hard origin/main` is refused is allowed", "allow",
    tool="Agent", prompt="Confirm `git reset --hard origin/main` is refused.", subagent_type="Explore")
add("brief-destructive-git: Plan brief that says `git reset --hard origin/main` is refused is allowed", "allow",
    tool="Agent", prompt="Confirm `git reset --hard origin/main` is refused.", subagent_type="Plan")
add("brief-destructive-git: builder brief that orders `git branch -D old-lane` is allowed", "allow",
    tool="Agent", prompt="Delete it locally: `git branch -D old-lane`.", subagent_type="builder", model="sonnet")
add("brief-destructive-git: builder brief that orders `git worktree prune` is allowed", "allow",
    tool="Agent", prompt="Then run `git worktree prune`.", subagent_type="builder", model="sonnet")
add("brief-destructive-git: builder brief that orders `git worktree remove x` is allowed", "allow",
    tool="Agent", prompt="Then run `git worktree remove x`.", subagent_type="builder", model="sonnet")
add("brief-destructive-git: a brief whose scratch `git -C` segment is joined to a reset outside it is denied", "deny",
    BRIEF_DESTRUCTIVE, tool="Agent",
    prompt="Compare: `git -C '" + SCRATCH_REPO + "' status && git reset --hard origin/main`.",
    subagent_type="builder", model="sonnet")
add("brief-destructive-git: a reset under an inline ``` span line that is not a fence is denied", "deny",
    BRIEF_DESTRUCTIVE, tool="Agent", prompt="```git status```\nRun `git reset --hard origin/main`.",
    subagent_type="builder", model="sonnet")
# Brief-scan cases for these causes: a heading negator read across the whole heading, a negator that is not the word
# before its span ("without", "avoid"), emphasis marks inside a negator, a bold heading, a blank line before the list, a
# fence or a nested bullet under a negating heading, an inline triple-backtick span with text after it, and a read-only
# role with a plugin prefix. Each deny is red on a brief that the scan lets through; each allow is red on a refusal the
# scan makes, and its reason names this rule.
add("brief-destructive-git: heading Do not skip any step: does not cover a numbered list that orders a reset is denied",
    "deny", BRIEF_DESTRUCTIVE, tool="Agent",
    prompt="Do not skip any step:\n1. `git fetch`\n2. `git reset --hard origin/main`",
    subagent_type="builder", model="sonnet")
add("brief-destructive-git: heading Without losing the log, run: does not cover a bullet that orders a discard is denied",
    "deny", BRIEF_DESTRUCTIVE, tool="Agent", prompt="Without losing the log, run:\n- `git checkout -- .`",
    subagent_type="builder", model="sonnet")
add("brief-destructive-git: without that is not the word before the span does not cancel a reset is denied", "deny",
    BRIEF_DESTRUCTIVE, tool="Agent", prompt="Reset without asking: `git reset --hard origin/main`",
    subagent_type="builder", model="sonnet")
add("brief-destructive-git: avoid that is not the word before the span does not cancel a clean is denied", "deny",
    BRIEF_DESTRUCTIVE, tool="Agent", prompt="To avoid conflicts run `git clean -fd`",
    subagent_type="builder", model="sonnet")
add("brief-destructive-git: an inline triple-backtick span with text after it opens no fence, so the reset after it "
    "is denied", "deny", BRIEF_DESTRUCTIVE, tool="Agent",
    prompt="```git status``` first\nThen:\n```\ngit reset --hard origin/main\n```",
    subagent_type="builder", model="sonnet")
add("brief-destructive-git: emphasis marks inside the negator, Do **not** run, are allowed", "allow",
    tool="Agent", prompt="Do **not** run `git reset --hard`.", subagent_type="builder", model="sonnet")
add("brief-destructive-git: a bold Never run: heading over discard bullets is allowed", "allow",
    tool="Agent", prompt="**Never run:**\n- `git reset --hard`\n- `git stash`", subagent_type="builder", model="sonnet")
add("brief-destructive-git: a blank line between Never run: and its discard bullets is allowed", "allow",
    tool="Agent", prompt="Never run:\n\n- `git reset --hard`\n- `git stash`", subagent_type="builder", model="sonnet")
add("brief-destructive-git: a fenced discard under a Never run: heading is allowed", "allow",
    tool="Agent", prompt="Never run:\n```\ngit reset --hard\n```", subagent_type="builder", model="sonnet")
add("brief-destructive-git: a nested discard bullet under a - Never run: bullet heading is allowed", "allow",
    tool="Agent", prompt="- Never run:\n  - `git stash`", subagent_type="builder", model="sonnet")
add("brief-destructive-git: a plugin-prefixed reviewer role my-plugin:reviewer that says a reset is refused is allowed",
    "allow", tool="Agent", prompt="Confirm `git reset --hard origin/main` is refused.",
    subagent_type="my-plugin:reviewer", model="sonnet")
# Failure classes: a false allow on a Workflow spawn that names no model, or names one through a variable (spawn_inputs
# skips both, so no brief is read), and a false deny on prohibitions joined by commas (the comma ends the clause the
# negator sits in, so the second span reads as an order).
add("brief-destructive-git: Workflow builder agent with no model key that orders `git reset --hard origin/main` "
    "is denied", "deny", BRIEF_DESTRUCTIVE, tool="Workflow",
    script=_step_flow("'Run `git reset --hard origin/main`'", "agentType: 'builder'"))
add("brief-destructive-git: Workflow builder agent whose model is held in a variable and that orders "
    "`git reset --hard origin/main` is denied", "deny", BRIEF_DESTRUCTIVE, tool="Workflow",
    script="const m = 'sonnet'; "
           + _step_flow("'Run `git reset --hard origin/main`'", "agentType: 'builder', model: m"))
add("brief-destructive-git: builder brief whose comma list of prohibitions names `git stash`, `git reset --hard` and "
    "`git clean -fd` is allowed", "allow", tool="Agent",
    prompt="Never run `git stash`, `git reset --hard`, or `git clean -fd`.", subagent_type="builder", model="sonnet")
# A prose word that ends in x, then a comma, then a reset order. The comma-list join reads that x as a span placeholder
# and drops the clause, so the negator before the comma covers the order. Each is an order, so each is denied.
add("brief-destructive-git: builder brief, tests fail and you can't fix, then a reset order is denied", "deny",
    BRIEF_DESTRUCTIVE, tool="Agent",
    prompt="If the tests fail and you can't fix, `git reset --hard` and restart.",
    subagent_type="builder", model="sonnet")
add("brief-destructive-git: builder brief, no need to fix, then a reset order is denied", "deny",
    BRIEF_DESTRUCTIVE, tool="Agent",
    prompt="No need to fix, `git reset --hard` instead.", subagent_type="builder", model="sonnet")
add("brief-destructive-git: builder brief, never leave the box, then a reset order is denied", "deny",
    BRIEF_DESTRUCTIVE, tool="Agent",
    prompt="Never leave the box, `git reset --hard` first.", subagent_type="builder", model="sonnet")
# The x cases above fail on the no-case half only: the join reads a lower-case x. An upper-case X at the end of a
# word is read the same way, so this case pins the word-start half that a case-only fix would leave open.
add("brief-destructive-git: builder brief, a word ending in capital X (INBOX,) then a reset order is denied", "deny",
    BRIEF_DESTRUCTIVE, tool="Agent",
    prompt="Never edit the INBOX, `git reset --hard` first.", subagent_type="builder", model="sonnet")
# Control, green on the old code: a comma before an order is a clause break too, so the order is still denied. A
# builder that drops the comma from the clause split would let this through.
add("brief-destructive-git: control, a comma before the order keeps it an order and is denied", "deny",
    BRIEF_DESTRUCTIVE, tool="Agent", prompt="Don't skip tests, run `git reset --hard`.",
    subagent_type="builder", model="sonnet")
# Controls: a clause break before an order keeps it an order, a negation covers a span after an earlier span, and a
# builder's refusal text still orders a reset.
add("brief-destructive-git: control, a semicolon before the order keeps it an order and is denied", "deny",
    BRIEF_DESTRUCTIVE, tool="Agent", prompt="Don't skip tests; run `git reset --hard`.",
    subagent_type="builder", model="sonnet")
add("brief-destructive-git: control, a never over an earlier span still covers the reset after it is allowed", "allow",
    tool="Agent", prompt="Never run `a` or `git reset --hard`", subagent_type="builder", model="sonnet")
add("brief-destructive-git: control, builder brief that says `git reset --hard origin/main` is refused is denied", "deny",
    BRIEF_DESTRUCTIVE, tool="Agent", prompt="Confirm `git reset --hard origin/main` is refused.",
    subagent_type="builder", model="sonnet")


# The owner's override lifts this refusal the way it lifts an Opus spawn's (decision owner-override): a one-act override
# lets the first brief through, a timed one lets every brief through until it ends. Each story is refused with no override.
BRIEF_DESTRUCTIVE_SPAWN = {"prompt": "Then run `git reset --hard origin/main` and re-apply your change.",
                           "model": "sonnet", "subagent_type": "builder"}


def brief_destructive_override_check(timed):
    kind = "timed" if timed else "once"

    def check():
        config, session = ov_config("brief-destructive-" + kind), "ov-brief-destructive-" + kind

        def call(seconds):
            return lambda: ov_call("Agent", dict(BRIEF_DESTRUCTIVE_SPAWN), NOGIT, config, session, seconds)

        ok, why = ov_story([("with no override", call(0), "deny", BRIEF_DESTRUCTIVE)])
        if not ok:
            return False, why
        note = ov_type(config, session, "override 15m" if timed else "override")
        if timed:
            steps = [("first brief", call(60), "allow", BRIEF_DESTRUCTIVE),
                     ("brief just before the end", call(OV_TIMED_SECONDS - 1), "allow", BRIEF_DESTRUCTIVE),
                     ("brief at the end instant", call(OV_TIMED_SECONDS), "deny", BRIEF_DESTRUCTIVE)]
        else:
            steps = [("first brief", call(60), "allow", BRIEF_DESTRUCTIVE),
                     ("second brief, override spent", call(120), "deny", BRIEF_DESTRUCTIVE)]
        ok, why = ov_story(steps, note)
        if not ok:
            return False, why
        return True, "a brief's discard order was refused with no override, then went through %s" % (
            "until the end" if timed else "once")
    return check


for _is_timed in (False, True):
    _override_check = brief_destructive_override_check(_is_timed)
    LOG_CHECKS_EXTRA.append((
        "brief-destructive-git: an owner override lifts a brief's discard order %s"
        % ("until it ends" if _is_timed else "for one brief"), _override_check))
    FIXTURELESS_CHECKS.add(_override_check)  # it builds its own config folders and reads no lazy fixture


# ---- Brief-claim edges (rule brief-claim-has-probe). A claim can hide behind a backticked subject, a fence, a passive
# form, another verb, a probe for a longer input, a plain-quoted input, a path locator, or a quoted red-case text. It
# can also sit apart from its inputs (both, them, or a list above it), be negated, use "lets ... through", or sit
# unquoted in a Must deny: line. Each deny is red on a guard that lets the claim through. Each allow is a false alarm
# the rule must not raise: a double-quoted claim with backticks, a claim whose clause ends at "so", or a real probe
# shape (a cd, a pipe, an env prefix or time before python3). Each text is data: the prompt a brief carries, verbatim.
# Selector: MUTATE_ONLY=brief-claim: runs these with the cases above.
BRIEF_CLAIM_EDGES = (
    ("brief-claim: test-author brief with a backticked main subject and a refusal is denied",
     "deny", "test-author", "`main` refuses `git push --force`, so keep that."),
    ("brief-claim: builder brief with a backticked origin/main subject and a pass is denied",
     "deny", "builder", "`origin/main` passes `user: root`."),
    ("brief-claim: test-author brief with a claim inside a fence after Cases: is denied",
     "deny", "test-author", "Cases:\n```\nmain refuses `git push --force`\n```"),
    ("brief-claim: builder brief whose claim line is its own probe is denied",
     "deny", "builder", "`git push --force` refused on main"),
    ("brief-claim: test-author brief whose probe is for a longer input than the claim is denied",
     "deny", "test-author",
     "main refuses `git push`.\n$ python3 hooks/probe_main.py 'git push --force'\nrefused"),
    ("brief-claim: builder brief with main rejects an input is denied",
     "deny", "builder", "main rejects `git push --force`."),
    ("brief-claim: test-author brief with main blocks an input is denied",
     "deny", "test-author", "main blocks `git push --force`."),
    ("brief-claim: builder brief with an input refused on main in passive form is denied",
     "deny", "builder", "- `git push --force` is refused on main"),
    ("brief-claim: test-author brief where main passes a plain-quoted input is denied",
     "deny", "test-author", 'main passes "password: none for guests and visitors"'),
    ("brief-claim: builder brief with main as an adjective before a refusal is allowed",
     "allow", "builder", "The main session refuses `git push --force` on this checkout."),
    ("brief-claim: builder brief with main as an adjective before a pass is allowed",
     "allow", "builder", "The main checkout passes `verdict` for every lane."),
    ("brief-claim: builder brief with today as a time word and the builder as subject is allowed",
     "allow", "builder", "Today the builder passes `verdict` results to the lane."),
    ("brief-claim: test-author brief with a path locator after a probed refusal is allowed",
     "allow", "test-author",
     "main refuses `git push --force` in `hooks/guard.py`.\n$ python3 hooks/probe_main.py 'git push --force'\nrefused"),
    ("brief-claim: test-author brief quoting a claim after Add a case: is allowed",
     "allow", "test-author", 'Add a case: "main refuses `git push --force`, so keep that."'),
    ("brief-claim: test-author brief quoting a claim after Must deny: is allowed",
     "allow", "test-author", 'Must deny: "main passes `user: root`."'),
    ("brief-claim: test-author brief where main passes both, with its inputs in the sentence before, is denied",
     "deny", "test-author", "Move `user: root` and `port: 0` to the passing list. Main passes both."),
    ("brief-claim: builder brief where as main refuses it, with its inputs in a list below, is denied",
     "deny", "builder", "Each must be refused, as main refuses it:\n- `git push --force`\n- `port: 0`"),
    ("brief-claim: test-author brief where main passes all of them, after a list of inputs, is denied",
     "deny", "test-author", "- `user: root`\n- `port: 0`\nmain passes all of them."),
    ("brief-claim: builder brief where main doesn't refuse an input is denied",
     "deny", "builder", "main doesn't refuse `git push --force`."),
    ("brief-claim: test-author brief where main never refuses an input is denied",
     "deny", "test-author", "main never refuses `git push --force`."),
    ("brief-claim: builder brief where main lets an input through is denied",
     "deny", "builder", "main lets `port: 0` through."),
    ("brief-claim: test-author brief with an unquoted claim inside a Must deny: line is denied",
     "deny", "test-author", "Must deny: `x: y` (main allows `x: y` today)."),
    ("brief-claim: test-author brief with a backticked main claim in double quotes, no prefix, is allowed",
     "allow", "test-author", '- "`main` refuses `git push --force`"'),
    ("brief-claim: builder brief whose main claim is followed by so and a backticked command is allowed",
     "allow", "builder", "origin/main passes CI, so run `verdict pytest` first."),
    ("brief-claim: test-author brief whose main claim is followed by so and a backticked edit is allowed",
     "allow", "test-author", "main passes CI, so only edit `hooks/guard.py`."),
    ("brief-claim: builder brief with a cd-and-python3 probe and its result line is allowed",
     "allow", "builder", "Main refuses `x: y`.\n$ cd /w && python3 probe.py 'x: y'\nrefused"),
    ("brief-claim: test-author brief with a piped echo probe and its result line is allowed",
     "allow", "test-author", "Main refuses `x: y`.\n$ echo 'x: y' | python3 probe.py\nrefused"),
    ("brief-claim: builder brief with an env-prefixed python3 probe and its result line is allowed",
     "allow", "builder", "Main refuses `x: y`.\n$ PYTHONPATH=. python3 probe.py 'x: y'\nrefused"),
    ("brief-claim: test-author brief with a time-prefixed python3 probe and its result line is allowed",
     "allow", "test-author", "Main refuses `x: y`.\n$ time python3 probe.py 'x: y'\nrefused"),
    # Each deny here is a claim the rule must catch, and each allow a claim it must leave alone. The NUL case is a
    # deny, not an allow: a guard that crashes fails open, so an allow would pass on the crash.
    ("brief-claim: test-author brief where origin/main passes all tests, after a backticked path, is allowed",
     "allow", "test-author", "Edit `hooks/guard.py`. origin/main passes all tests."),
    ("brief-claim: builder brief where origin/main refuses each push, after a backticked path, is allowed",
     "allow", "builder", "Fix `x.py`. origin/main refuses each push."),
    ("brief-claim: test-author brief where origin/main passes CI after because, with an input before it, is allowed",
     "allow", "test-author", "Edit `hooks/guard.py`, because origin/main passes CI."),
    ("brief-claim: builder brief where main blocks raw pytest after because, with an input before it, is allowed",
     "allow", "builder", "Use `verdict` because main blocks raw pytest."),
    ("brief-claim: builder brief with a bulleted Controls heading after a probed refusal list is allowed",
     "allow", "builder",
     "$ python3 hooks/probe_main.py 'git push --force'\nrefused\n\nEach must be refused, as main refuses it:\n"
     "- `git push --force`\n\n- Controls that must still pass:\n  - `user: root`"),
    ("brief-claim: test-author brief with a numbered Controls heading after a probed refusal list is allowed",
     "allow", "test-author",
     "$ python3 hooks/probe_main.py 'git push --force'\nrefused\n\nEach must be refused, as main refuses it:\n"
     "- `git push --force`\n\n1. Controls that must still pass:\n   - `user: root`"),
    ("brief-claim: builder brief with a plain Controls heading after a probed refusal list is allowed",
     "allow", "builder",
     "$ python3 hooks/probe_main.py 'git push --force'\nrefused\n\nEach must be refused, as main refuses it:\n"
     "- `git push --force`\n\nControls that must still pass:\n- `user: root`"),
    ("brief-claim: test-author brief where main refuses each, after a list of inputs, is denied",
     "deny", "test-author", "- `user: root`\n- `port: 0`\nmain refuses each."),
    ("brief-claim: builder brief where main refuses an input named before the verb, with no probe, is denied",
     "deny", "builder", "For `user: root` main refuses."),
    ("brief-claim: test-author brief where two inputs pass on main, joined by and, is denied",
     "deny", "test-author", "`user: root` and `port: 0` pass on main."),
    ("brief-claim: builder brief where an input is listed as passing on main is denied",
     "deny", "builder", "The lane listed `git push --force` as passing on main."),
    ("brief-claim: test-author brief where On main, an input passes is denied",
     "deny", "test-author", "On main, `port: 0` passes."),
    ("brief-claim: builder brief where Today an input passes is denied",
     "deny", "builder", "Today `port: 0` passes."),
    ("brief-claim: test-author brief where the guard refuses an input today is denied",
     "deny", "test-author", "The guard refuses `port: 0` today."),
    ("brief-claim: builder brief with a NUL marker on a line with no quoted input, then a claim, is denied without a crash",
     "deny", "builder", "Keep the scan. \x000\x00 is a marker.\nMain refuses `port: 0`."),
    ("brief-claim: test-author brief with a comment opener inside a backticked input is denied",
     "deny", "test-author", "main refuses `/* x */` today."),
    ("brief-claim: builder brief with a hash opener inside a double-quoted input is denied",
     "deny", "builder", 'main refuses "# not a comment" today.'),
    ("brief-claim: test-author brief with a backtick span cut by a line break reads to the line's end, and is denied",
     "deny", "test-author", "main refuses `git push\n--force`."),
)
for _name, _expected, _role, _prompt in BRIEF_CLAIM_EDGES:
    add(_name, _expected, BRIEF_PROBE if _expected == "deny" else None, tool="Agent", prompt=_prompt,
        subagent_type=_role, **({"model": "sonnet"} if _role == "builder" else {}))
# A brief with two unprobed claims names every input in its refusal, not only the first.
add("brief-claim: builder brief with two unprobed claims names both inputs in its refusal, and is denied",
    "deny", BRIEF_PROBE, tool="Agent",
    prompt="Make these green.\nMain refuses `git push --force`.\nMain allows `port: 0`.",
    subagent_type="builder", model="sonnet", carries=("git push --force", "port: 0"))
# A referent that is a pronoun, or a count word such as all three or both today, takes the inputs of its own sentence,
# or of the sentence before it, and the refusal names them. Each deny here is a miss: the referent sat in the same
# sentence as its inputs, or the count word named no referent at all.
add("brief-claim: test-author brief where main refuses it, after an input in the same sentence, is denied",
    "deny", BRIEF_PROBE, tool="Agent", prompt="Edit `x`, because main refuses it.",
    subagent_type="test-author", carries=("`x`",))
add("brief-claim: builder brief where main refuses them, after two inputs in the same sentence, is denied",
    "deny", BRIEF_PROBE, tool="Agent", prompt="Edit `x` and `y`, because main refuses them.",
    subagent_type="builder", model="sonnet", carries=("`x`", "`y`"))
add("brief-claim: builder brief where main passes it, after an input in the same sentence, is denied",
    "deny", BRIEF_PROBE, tool="Agent", prompt="Edit `x`, because main passes it.",
    subagent_type="builder", model="sonnet", carries=("`x`",))
add("brief-claim: test-author brief where main passes them, after two inputs in the same sentence, is denied",
    "deny", BRIEF_PROBE, tool="Agent", prompt="Edit `x` and `y`, because main passes them.",
    subagent_type="test-author", carries=("`x`", "`y`"))
add("brief-claim: test-author brief where main refuses all three, after two inputs, is denied",
    "deny", BRIEF_PROBE, tool="Agent", prompt="Keep `a` and `b`. Main refuses all three.",
    subagent_type="test-author", carries=("`a`", "`b`"))
add("brief-claim: builder brief where main refuses both cases, after two inputs, is denied",
    "deny", BRIEF_PROBE, tool="Agent", prompt="Keep `a` and `b`. Main refuses both cases.",
    subagent_type="builder", model="sonnet", carries=("`a`", "`b`"))
add("brief-claim: test-author brief where main refuses these two, after two inputs, is denied",
    "deny", BRIEF_PROBE, tool="Agent", prompt="Keep `a` and `b`. Main refuses these two.",
    subagent_type="test-author", carries=("`a`", "`b`"))
add("brief-claim: builder brief where main refuses each one, after two inputs, is denied",
    "deny", BRIEF_PROBE, tool="Agent", prompt="Keep `a` and `b`. Main refuses each one.",
    subagent_type="builder", model="sonnet", carries=("`a`", "`b`"))
add("brief-claim: test-author brief where main refuses both today, after two inputs, is denied",
    "deny", BRIEF_PROBE, tool="Agent", prompt="Keep `a` and `b`. Main refuses both today.",
    subagent_type="test-author", carries=("`a`", "`b`"))
add("brief-claim: builder brief where main passes all three, after two inputs, is denied",
    "deny", BRIEF_PROBE, tool="Agent", prompt="Keep `a` and `b`. Main passes all three.",
    subagent_type="builder", model="sonnet", carries=("`a`", "`b`"))
add("brief-claim: builder brief where both cases must still pass, after two inputs, is allowed",
    "allow", tool="Agent", prompt="Keep `a` and `b`. Both cases must still pass.",
    subagent_type="builder", model="sonnet")
# Each case below kills one mutant of the claim scan that no case read before: the base verb block after not, the -ing
# verb refusing, the subjects check and rule before today, and now as the last word after a verb. Each is green on the
# guard as it stands and red on the mutant.
add("brief-claim: builder brief where main does not block an input is denied",
    "deny", BRIEF_PROBE, tool="Agent", prompt="Keep the scan as it is. Main does not block `git push --force`.",
    subagent_type="builder", model="sonnet")
add("brief-claim: builder brief where an input is refusing on main is denied",
    "deny", BRIEF_PROBE, tool="Agent", prompt="Keep the scan as it is. `port: 0` is refusing on main.",
    subagent_type="builder", model="sonnet")
add("brief-claim: test-author brief where the check refuses an input today is denied",
    "deny", BRIEF_PROBE, tool="Agent", prompt="Write the case. The check refuses `port: 0` today.",
    subagent_type="test-author")
add("brief-claim: test-author brief where the rule refuses an input today is denied",
    "deny", BRIEF_PROBE, tool="Agent", prompt="Write the case. The rule refuses `port: 0` today.",
    subagent_type="test-author")
add("brief-claim: test-author brief where an input before main refuses now is denied",
    "deny", BRIEF_PROBE, tool="Agent", prompt="Write the case. For `port: 0` main refuses now.",
    subagent_type="test-author")


# Pins for the count word, the pronoun tail and today (rule brief-claim-has-probe). A count word (all three, both now,
# all 3, these ones) after a claim refers to the inputs before it, as a pronoun does. The allows are claims the scan
# reads with no input of their own.
add("brief-claim: test-author brief where main refuses all three today, after two inputs, is denied",
    "deny", BRIEF_PROBE, tool="Agent", prompt="Keep `a` and `b`. Main refuses all three today.",
    subagent_type="test-author", carries=("`a`", "`b`"))
add("brief-claim: test-author brief where main refuses all three now, after two inputs, is denied",
    "deny", BRIEF_PROBE, tool="Agent", prompt="Keep `a` and `b`. Main refuses all three now.",
    subagent_type="test-author", carries=("`a`", "`b`"))
add("brief-claim: test-author brief where main refuses both now, after two inputs, is denied",
    "deny", BRIEF_PROBE, tool="Agent", prompt="Keep `a` and `b`. Main refuses both now.",
    subagent_type="test-author", carries=("`a`", "`b`"))
add("brief-claim: test-author brief where main refuses all 3, after two inputs, is denied",
    "deny", BRIEF_PROBE, tool="Agent", prompt="Keep `a` and `b`. Main refuses all 3.",
    subagent_type="test-author", carries=("`a`", "`b`"))
add("brief-claim: test-author brief where main refuses both inputs, after two inputs, is denied",
    "deny", BRIEF_PROBE, tool="Agent", prompt="Keep `a` and `b`. Main refuses both inputs.",
    subagent_type="test-author", carries=("`a`", "`b`"))
add("brief-claim: test-author brief where main refuses these ones, after two inputs, is denied",
    "deny", BRIEF_PROBE, tool="Agent", prompt="Keep `a` and `b`. Main refuses these ones.",
    subagent_type="test-author", carries=("`a`", "`b`"))
add("brief-claim: test-author brief where main refuses all five, after two inputs, is denied",
    "deny", BRIEF_PROBE, tool="Agent", prompt="Keep `a` and `b`. Main refuses all five.",
    subagent_type="test-author", carries=("`a`", "`b`"))
add("brief-claim: test-author brief where main passes all three tests is allowed",
    "allow", tool="Agent", prompt="Main passes all three tests.", subagent_type="test-author")
add("brief-claim: test-author brief where main refuses it after a fixed input is allowed",
    "allow", tool="Agent", prompt="Fix `X`, and main refuses it.", subagent_type="test-author")
add("brief-claim: test-author brief where main refuses it, then a verdict command, is allowed",
    "allow", tool="Agent", prompt="Main refuses it, so run `verdict pytest`.", subagent_type="test-author")
add("brief-claim: test-author brief where main passes CI for a kept input is allowed",
    "allow", tool="Agent", prompt="Keep it in `x` because main passes CI.", subagent_type="test-author")
add("brief-claim: test-author brief where main passes CI, and an edit keeps it green, is allowed",
    "allow", tool="Agent", prompt="Edit `x` because main passes CI, and keep it green.", subagent_type="test-author")
# A count word that is not the clause's end is no referent: "all three tests" names no inputs, so the two before it are not claimed.
add("brief-claim: test-author brief where main passes all three tests, after two inputs, is allowed",
    "allow", tool="Agent", prompt="Keep `a` and `b`. Main passes all three tests.", subagent_type="test-author")
add("brief-claim: test-author brief where today we know the guard refuses an input today is denied",
    "deny", BRIEF_PROBE, tool="Agent", prompt="Today we know the guard refuses `x` today.",
    subagent_type="test-author", carries=("`x`",))
add("brief-claim: test-author brief where the guard refuses an input in capitals TODAY is denied",
    "deny", BRIEF_PROBE, tool="Agent", prompt="The guard refuses `x` TODAY.",
    subagent_type="test-author", carries=("`x`",))
# Names only the first input: the scan reads one claim per sentence. The verdict is pinned.
add("brief-claim: test-author brief where the guard refuses an input today, and main refuses a second, is denied",
    "deny", BRIEF_PROBE, tool="Agent", prompt="The guard refuses `a` today, and main refuses `b`.",
    subagent_type="test-author", carries=("`a`",))


def _flow(model, role=None):
    spec = "model: '%s'" % model + (", agentType: '%s'" % role if role else "")
    return "const r = await agent({prompt: 'x', %s}); return r" % spec


for _model in HAIKU_MODELS:
    for _role in HAIKU_ROLES:
        add("floor: Workflow agent %s on %s is allowed" % (_role, _model), "allow",
            tool="Workflow", script=_flow(_model, _role))
    for _role in ("builder", "Plan", "general-purpose", None):
        add("floor: Workflow agent %s on %s is denied" % (_role or "without agentType", _model),
            "deny", "agent-model-floor", tool="Workflow", script=_flow(_model, _role))
add("floor: Workflow agent with a mixed-case haiku and no agentType is denied", "deny",
    "agent-model-floor", tool="Workflow", script=_flow("Claude-HAIKU-5-5"))
add("floor: Workflow with one listed and one unlisted haiku agent is denied", "deny",
    "agent-model-floor", tool="Workflow",
    script=_flow("haiku", "reviewer") + "\n" + _flow("haiku", "builder"))
for _near in ("record-writers", "Record-Writer"):
    add("floor: Workflow agent %r on haiku is denied" % _near, "deny", "agent-model-floor",
        tool="Workflow", script=_flow("haiku", _near))
add("floor: Workflow record-writer on haiku with a sonnet builder beside it is denied", "deny",
    "agent-model-floor", tool="Workflow",
    script=_flow("haiku", "record-writer") + "\n" + _flow("haiku", "builder"))
add("floor: Workflow agent on sonnet with no agentType is allowed", "allow",
    tool="Workflow", script=_flow("sonnet"))
add("floor: start_session naming haiku is denied", "deny", "agent-model-floor",
    tool="mcp__ccd_session__start_session", initiation="user_asked", prompt="x", model="haiku")
add("floor: start_session naming the full haiku id is denied", "deny", "agent-model-floor",
    tool="mcp__ccd_session__start_session", initiation="user_asked", prompt="x",
    model="claude-haiku-5-5")
add("floor: start_session naming sonnet is allowed", "allow",
    tool="mcp__ccd_session__start_session", initiation="user_asked", prompt="x", model="sonnet")
# create_session starts a session on a named model, so the floor judges it as start_session does
# (decision agent-model-cap, the floor). Failure classes: a false allow (a haiku session slips
# through because only start_session was judged), a false deny (sonnet, opus or no model refused).
CREATE_SESSION_CALL = "mcp__claude-code-remote__create_session"
for _model in ("haiku", "claude-haiku-5-5", "Claude-HAIKU-5-5", ["haiku"]):
    add("floor: create_session naming %r is denied" % (_model,), "deny", "agent-model-floor",
        tool=CREATE_SESSION_CALL, prompt="x", model=_model)
for _model in ("sonnet", "claude-sonnet-5-5", "opus", "claude-opus-5-5"):
    add("floor: create_session naming %s is allowed" % (_model,), "allow",
        tool=CREATE_SESSION_CALL, prompt="x", model=_model)
add("floor: create_session with no model is allowed", "allow", tool=CREATE_SESSION_CALL, prompt="x")

# ---- A Workflow call whose args hold a placeholder. A placeholder is an all-caps word with an underscore, or a
# __X__ word, and the whole value must be one (a sentence that holds one passes). The guard reads args and each
# array item or object value one level down. Each refusal names the placeholder and the fix. The args are
# structured values, not source text, so no comment-opener or quote case applies.
