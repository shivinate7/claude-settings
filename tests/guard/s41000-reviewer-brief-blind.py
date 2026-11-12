# section 41000
# --------------------------------------------------------------------------- a reviewer's brief holds no report
#
# Decision reviewer-brief-blind. A reviewer that
# reads the builder's report, or a prior round's verdict, anchors on it and confirms it. So a reviewer spawn (Agent
# or Task) is refused when its brief holds a report-shaped block or a verdict line, and so is each Workflow agent()
# call whose agentType is a reviewer. The check reads shapes at line start, never words. The owner's override lifts
# the refusal, as it lifts any refusal that goes through refuse().
# Failure classes: a fix check that cannot see the finding it names (a false refusal); a quote of the task's words
# that refuses (a false refusal); a report or verdict shape that passes (a false allow).
FAMILY = "reviewer-brief-blind"
RBB = "reviewer-brief-blind"


def rbb_refuse(name, prompt, role="reviewer", model="haiku", tool="Agent"):
    add(name, "deny", RBB, tool=tool, prompt=prompt, subagent_type=role, model=model)


def rbb_allow(name, prompt, role="reviewer", model="haiku", tool="Agent"):
    add(name, "allow", tool=tool, prompt=prompt, subagent_type=role, model=model)


# Refused. Each brief names the reviewer's task on its first line, so the refusal comes from the shape alone. A
# reviewer on haiku is within its own row, so no other rule refuses these spawns.
rbb_refuse("reviewer-brief-blind: refused: a reviewer brief that pastes a builder report, Done: and Deviations: lines",
           "Check the floor fix in hooks/guard.py.\nDone: the floor fix is in.\nDeviations: none.")
rbb_refuse("reviewer-brief-blind: refused: a reviewer brief with a Verdict: CHANGES line",
           "Re-check the floor fix.\nVerdict: CHANGES\nFiles: hooks/guard.py.")
rbb_refuse("reviewer-brief-blind: refused: a reviewer brief with a Round 1: PASS line",
           "Re-check the floor fix.\nRound 1: PASS\nFiles: hooks/guard.py.")
rbb_refuse("reviewer-brief-blind: refused: a reviewer brief with a BUILT item at line start",
           "Check the floor fix.\nBUILT c204a1f the floor fix, tests green.\nFiles: hooks/guard.py.")
# A Workflow agent() call whose agentType is a reviewer is judged the same way, with or without a model. The
# multi-line form holds real newlines in a template literal, the other holds the escaped newline of a quoted string.
add("reviewer-brief-blind: refused: a Workflow agent() reviewer, its multi-line template prompt carrying a report",
    "deny", RBB, tool="Workflow",
    script="const r = await agent(`Check the floor fix.\nDone: BUILT c204a1f.\nDeviations: none.`, "
           "{agentType: 'reviewer', model: 'haiku'}); return r")
add("reviewer-brief-blind: refused: a Workflow agent() reviewer with no model, its escaped prompt carrying a report",
    "deny", RBB, tool="Workflow",
    script="const r = await agent('Check the floor fix.\\nDone: BUILT c204a1f.\\nDeviations: none.', "
           "{agentType: 'reviewer'}); return r")
# A comment opener inside the prompt's string is text, not a comment: the report after it is still read.
add("reviewer-brief-blind: refused: a Workflow agent() reviewer whose prompt holds // and /* inside its string, then a report",
    "deny", RBB, tool="Workflow",
    script='const r = await agent("Do not skip /* the // check.\\nDone: BUILT c204a1f.\\nDeviations: none.", '
           "{agentType: 'reviewer', model: 'haiku'}); return r")
# The role set is the reviewer and the term for an agent that argues back, plus any plugin prefix on the reviewer.
rbb_refuse("reviewer-brief-blind: refused: a refuter spawn whose brief pastes a builder report",
           "Argue the floor fix.\nDone: BUILT c204a1f.\nDeviations: none.", role=REFUTER, model="sonnet")
rbb_refuse("reviewer-brief-blind: refused: a my-plugin:reviewer spawn whose brief pastes a builder report",
           "Check the floor fix.\nDone: BUILT c204a1f.\nDeviations: none.", role="my-plugin:reviewer", model="sonnet")
# Markdown forms of a report label and of an item. The decoration around a label word is no reason to pass a pasted report.
rbb_refuse("reviewer-brief-blind: refused: a reviewer brief with bold labels, **Done**: and **Deviations**:",
           "Check the floor fix.\n**Done**: the floor fix is in.\n**Deviations**: none.")
rbb_refuse("reviewer-brief-blind: refused: a reviewer brief with bullet labels, - Done: and - Deviations:",
           "Check the floor fix.\n- Done: the floor fix is in.\n- Deviations: none.")
rbb_refuse("reviewer-brief-blind: refused: a reviewer brief with heading labels, ## Done and ## Deviations",
           "Check the floor fix.\n## Done\nThe floor fix is in.\n## Deviations\nnone.")
rbb_refuse("reviewer-brief-blind: refused: a reviewer brief with a bullet item, - BUILT c1",
           "Check the floor fix.\n- BUILT c1 the floor fix.\nFiles: hooks/guard.py.")
# A verdict line needs no `Verdict:` or round label. A leading verdict word, or a `Prior round verdict:` line, is one too.
rbb_refuse("reviewer-brief-blind: refused: a reviewer brief whose leading verdict line is FAIL, round 1 of 3, haiku",
           "Re-check the floor fix.\nFAIL, round 1 of 3, haiku.\nFiles: hooks/guard.py.")
rbb_refuse("reviewer-brief-blind: refused: a reviewer brief with a Prior round verdict: FAIL line",
           "Re-check the floor fix.\nPrior round verdict: FAIL\nFiles: hooks/guard.py.")
# A single report label with an inline item is a report item, bold or plain. A round or prior verdict names its
# verdict word after the colon, whatever words stand before the colon.
rbb_refuse("reviewer-brief-blind: refused: a reviewer brief with one Done: label and an inline BUILT item",
           "Check the floor fix.\nDone: BUILT c204a1f the floor fix, tests green.\nFiles: hooks/guard.py.")
rbb_refuse("reviewer-brief-blind: refused: a reviewer brief with one bold Done: label and an inline BUILT item",
           "Check the floor fix.\n**Done**: BUILT c204a1f fix\nFiles: hooks/guard.py.")
rbb_refuse("reviewer-brief-blind: refused: a reviewer brief with a Previous round verdict: FAIL line",
           "Re-check the floor fix.\nPrevious round verdict: FAIL\nFiles: hooks/guard.py.")
rbb_refuse("reviewer-brief-blind: refused: a reviewer brief with a Last round verdict: FAIL line",
           "Re-check the floor fix.\nLast round verdict: FAIL\nFiles: hooks/guard.py.")
rbb_refuse("reviewer-brief-blind: refused: a reviewer brief with an Earlier verdict: PASS line",
           "Re-check the floor fix.\nEarlier verdict: PASS\nFiles: hooks/guard.py.")
rbb_refuse("reviewer-brief-blind: refused: a reviewer brief with a Round 1 result: FAIL line",
           "Re-check the floor fix.\nRound 1 result: FAIL\nFiles: hooks/guard.py.")
rbb_refuse("reviewer-brief-blind: refused: a reviewer brief with a Round 1 reviewer verdict: FAIL line",
           "Re-check the floor fix.\nRound 1 reviewer verdict: FAIL\nFiles: hooks/guard.py.")
rbb_refuse("reviewer-brief-blind: refused: a reviewer brief with a Verdict for round 1: FAIL line",
           "Re-check the floor fix.\nVerdict for round 1: FAIL\nFiles: hooks/guard.py.")
rbb_refuse("reviewer-brief-blind: refused: a reviewer brief with a lowercase round 1 result: FAIL line",
           "Re-check the floor fix.\nround 1 result: FAIL\nFiles: hooks/guard.py.")

# Prior verdicts a reviewer must not read, in shapes the guard misses: a leading verdict after a report label,
# a round label with no number, a round label with a dash for its colon, and a bold mark between the label and
# the verdict word. Each is a reviewer brief holding a prior verdict. It has one such shape and no second report
# label, so only the verdict shape can refuse it.
rbb_refuse("reviewer-brief-blind: refused: a reviewer brief whose Done: line leads with FAIL, round 1 of 3",
           "Re-check the floor fix.\nDone: FAIL, round 1 of 3, haiku\n- hooks/guard.py:2454, the floor reads the model before the role.")
rbb_refuse("reviewer-brief-blind: refused: a reviewer brief with a Round 1 line that takes a dash, then FAIL",
           "Re-check the floor fix.\nRound 1 — FAIL\n- hooks/guard.py:2454, the floor reads the model before the role.")
rbb_refuse("reviewer-brief-blind: refused: a reviewer brief with a Prior round: FAIL line, no verdict word before the colon",
           "Re-check the floor fix.\nPrior round: FAIL\n- hooks/guard.py:2454, the floor reads the model before the role.")
rbb_refuse("reviewer-brief-blind: refused: a reviewer brief with a bold **Round 1:** FAIL line",
           "Re-check the floor fix.\n**Round 1:** FAIL\n- hooks/guard.py:2454, the floor reads the model before the role.")
rbb_refuse("reviewer-brief-blind: refused: a reviewer brief with a bold **Verdict:** FAIL line",
           "Re-check the floor fix.\n**Verdict:** FAIL\n- hooks/guard.py:2454, the floor reads the model before the role.")

# Allowed. A later round gets the prior round's findings as a list, a fix check gets the one finding it checks, and
# the task's own words name the rule without a shape at line start. A builder's brief may hold its report.
rbb_allow("reviewer-brief-blind: allowed: a Round 2 of 3 reviewer brief with a findings list, file:line plus claim",
          "Round 2 of 3. Re-check the round 1 findings.\n"
          "Finding 1: hooks/guard.py:2454, the floor reads the model before the role.\n"
          "Finding 2: hooks/guard.py:2558, the step-up skips an unread brief.", model="sonnet")
rbb_allow("reviewer-brief-blind: allowed: a fix-check brief that names one finding",
          "Fix check for round 1, finding 2 only.\n"
          "Finding 2: hooks/guard.py:2558, the step-up skips an unread brief.\n"
          "Check that finding and no other.")
rbb_allow("reviewer-brief-blind: allowed: a brief quoting the task's words, never holds the builder's report, mid-line",
          "Check the diff. The rule says a reviewer brief \"never holds the builder's report, its reasoning, "
          "or a prior verdict\".")
rbb_allow("reviewer-brief-blind: allowed: a brief quoting the task's words, never holds the builder's report, at line start",
          "Check the diff.\nnever holds the builder's report, its reasoning, or a prior verdict.\nFiles: hooks/guard.py.")
rbb_allow("reviewer-brief-blind: allowed: a reviewer brief whose report-order instruction is one line",
          "Check the floor fix.\nReport in order: Done, Deviations, Input Needed, Next.\nFiles: hooks/guard.py.")
rbb_allow("reviewer-brief-blind: allowed: a builder spawn whose brief holds a report",
          "Fix the floor.\nDone: BUILT c204a1f the floor fix.\nDeviations: none.", role="builder", model="sonnet")
rbb_allow("reviewer-brief-blind: allowed: a findings line holding a lone quote and comment openers",
          "Round 2 of 3. Re-check the findings.\nFinding 1: hooks/guard.py:2454, don't skip /* the // check # now.",
          model="sonnet")
# One report label at line start is not a pasted report. A guard that refuses at one label, not two, fails this case.
rbb_allow("reviewer-brief-blind: allowed: a reviewer brief with exactly one report label at line start",
          "Check the floor fix.\nDone: when `verdict python3 hooks/test_guard.py` is green.\nFiles: hooks/guard.py.")
# A verdict word not right after the colon is a quote, not a verdict line. A line that opens with BUILT-IN is no item.
rbb_allow("reviewer-brief-blind: allowed: Round 2 of 3: check PASS or FAIL, the verdict word not right after the colon",
          "Re-check the floor fix.\nRound 2 of 3: check PASS or FAIL on the floor fix.\nFiles: hooks/guard.py.",
          model="sonnet")
rbb_allow("reviewer-brief-blind: allowed: a brief line that opens with BUILT-IN check, not a BUILT item",
          "Check the floor fix.\nBUILT-IN check: the floor reads the role before the model.\nFiles: hooks/guard.py.")
# A verdict word that opens a line is a quoted result, not a verdict line, unless the line is the report form
# `FAIL, round <n> of 3, ...`. A pasted test line that starts with FAIL is a quote too.
rbb_allow("reviewer-brief-blind: allowed: a reviewer brief with a line that opens PASS: and names the diff",
          "Re-check the floor fix.\nPASS: the diff fixes the finding.\nFiles: hooks/guard.py.")
rbb_allow("reviewer-brief-blind: allowed: a reviewer brief with a pasted test line, FAIL: test_x",
          "Re-check the floor fix.\nFAIL: test_x\nFiles: hooks/guard.py.")
# A brief that asks for a verdict, or for a report's shape, is not a report. Its twins that must still refuse are
# `Verdict: CHANGES` (above) for the verdict line, and the heading form `## Done` with a body under each label for the
# bare label list.
rbb_allow("reviewer-brief-blind: allowed: a reviewer brief whose Verdict: line names two words, PASS or FAIL, to choose from",
          "Check the floor fix.\nVerdict: PASS or FAIL, then findings.\nFiles: hooks/guard.py.")
rbb_allow("reviewer-brief-blind: allowed: a reviewer brief that asks for a Report with: list of the four labels, bare",
          "Check the floor fix.\nReport with:\n- Done\n- Deviations\n- Input Needed\n- Next\nFiles: hooks/guard.py.")
# Known limit (note brief-done-next-task-lines-refused, decision reviewer-brief-blind). A Done: and a Next: line that
# describe the task are read as a report's labels: telling them from a builder's lines takes a word rule, which the
# decision rules out. So this brief is refused until a word rule is ruled.
rbb_refuse("reviewer-brief-blind: refused: known limit until a word rule is ruled: a reviewer brief with "
           "Done: when and Next: lines that describe the task",
           "Check the floor fix in hooks/guard.py.\nDone: when the floor reads the role before the model, and the section's "
           "cases pass.\nNext: list each finding as file, line and claim.\nFiles: hooks/guard.py.")
# The green control for the line above: the same two labels with a builder's result. It stays refused, so a guard that
# drops Next from the label set would fail it.
rbb_refuse("reviewer-brief-blind: refused: a reviewer brief with a Done: result and a Next: line, a builder's report",
           "Check the floor fix.\nDone: the floor fix is in.\nNext: merge it.\nFiles: hooks/guard.py.")

# The empty state: a reviewer brief with no text holds no report, so it passes.
rbb_allow("reviewer-brief-blind: allowed: a reviewer brief with an empty prompt", "")
add("reviewer-brief-blind: allowed: a Workflow agent() reviewer on Round 2 of 3 with a findings list",
    "allow", tool="Workflow",
    script="const r = await agent('Round 2 of 3. Re-check.\\nFinding 1: hooks/guard.py:2454, the floor reads the "
           "model before the role.', {agentType: 'reviewer', model: 'sonnet'}); return r")
add("reviewer-brief-blind: allowed: a Workflow agent() builder whose prompt holds a report",
    "allow", tool="Workflow",
    script="const r = await agent('Fix the floor.\\nDone: BUILT c204a1f.\\nDeviations: none.', "
           "{agentType: 'builder', model: 'sonnet'}); return r")
# A commented-out call is not a call, so the report in it is not read as a reviewer's brief.
add("reviewer-brief-blind: allowed: a commented-out reviewer agent() call carrying a report",
    "allow", tool="Workflow",
    script="// await agent('Done: BUILT c204a1f.\\nDeviations: none.', {agentType: 'reviewer'})\n"
           "await agent('Fix the floor.', {agentType: 'builder', model: 'sonnet'})")

# A Workflow agent() reviewer whose prompt the scan cannot read is refused too (decision reviewer-brief-blind).
# The scan reads no variable, and a template's `${...}`
# hides its interpolated part, so a report can sit there unread. A plain template with no `${}` is read, as before.
# Each refusal names the literal-string remedy, read from guard.py, the one home of its words.
RBB_GUARD = _load_guard_module()
RBB_LITERAL_REMEDY = getattr(RBB_GUARD, "BRIEF_LITERAL_REMEDY", "<no BRIEF_LITERAL_REMEDY in guard>")
RBB_REPORT_VAR = "const builderReport = 'Done: BUILT c204a1f.\\nDeviations: none.';\n"
RBB_REPORT_PROMPT = "const prompt = 'Done: BUILT c204a1f.\\nDeviations: none.';\n"


def rbb_guard_text(name):
    """A string constant of guard.py, read by name. A missing name reads as "", which every reason holds, so a case that
    lacks it fails loudly rather than passing with nothing to check."""
    value = getattr(RBB_GUARD, name, "")
    return value if isinstance(value, str) else ""


# The unread refusal names the base remedy, never the marker form, and prints no report sentence. Both fragments come from
# guard.py: the marker suffix is what BRIEF_MARKER_REMEDY adds to BRIEF_LITERAL_REMEDY, and the report sentence is the
# first sentence of BRIEF_BLIND_REASON.
RBB_MARKER_SUFFIX = (rbb_guard_text("BRIEF_MARKER_REMEDY")[len(RBB_LITERAL_REMEDY):].strip()
                     if rbb_guard_text("BRIEF_MARKER_REMEDY").startswith(RBB_LITERAL_REMEDY) else "")
RBB_REPORT_SENTENCE = rbb_guard_text("BRIEF_BLIND_REASON").split(". ")[0]
RBB_UNREAD_LACKS = (RBB_MARKER_SUFFIX, RBB_REPORT_SENTENCE)


def rbb_unread_refuse(name, script):
    """A Workflow reviewer call whose prompt the scan cannot read is denied under reviewer-brief-blind, with the remedy."""
    add(name, "deny", RBB, tool="Workflow", script=script, carries=RBB_LITERAL_REMEDY, lacks=RBB_UNREAD_LACKS)


rbb_unread_refuse("reviewer-brief-blind: refused: a Workflow agent() reviewer whose template prompt reads ${builderReport}",
                  RBB_REPORT_VAR + _step_flow("`Review ${builderReport}`", "agentType: 'reviewer'"))
rbb_unread_refuse("reviewer-brief-blind: refused: a Workflow agent() reviewer whose prompt is a variable",
                  RBB_REPORT_PROMPT + _step_flow("prompt", "agentType: 'reviewer'"))
rbb_unread_refuse("reviewer-brief-blind: refused: a Workflow agent() refuter whose template prompt reads ${builderReport}",
                  RBB_REPORT_VAR + _step_flow("`Review ${builderReport}`", "agentType: '%s'" % REFUTER))
rbb_unread_refuse("reviewer-brief-blind: refused: a Workflow agent() refuter whose prompt is a variable",
                  RBB_REPORT_PROMPT + _step_flow("prompt", "agentType: '%s'" % REFUTER))
# A template with `${}` is unread even when its static text holds a lone quote and comment openers.
rbb_unread_refuse("reviewer-brief-blind: refused: a Workflow agent() reviewer, a multi-line template with ${}, a lone quote, // and /*",
                  _step_flow("`Check the floor fix.\nDon't skip /* the // check.\nBranch ${builderReport}`",
                             "agentType: 'reviewer'"))
# These were allowed as step-up cases. Each is a reviewer prompt the scan cannot read, so it is refused here.
rbb_unread_refuse("reviewer-brief-blind: refused: a Workflow agent() reviewer with the prompt in a variable",
                  _step_flow("brief", "agentType: 'reviewer'"))
rbb_unread_refuse("reviewer-brief-blind: refused: a Workflow agent() reviewer with a concatenated prompt",
                  _step_flow("'Round 2 of 3. ' + rest", "agentType: 'reviewer'"))
rbb_unread_refuse("reviewer-brief-blind: refused: a Workflow agent() reviewer whose marker is only interpolated",
                  _step_flow("`${'Round 2 of 3.'} Re-check.`", "agentType: 'reviewer'"))
rbb_unread_refuse("reviewer-brief-blind: refused: a Workflow agent() reviewer whose round number is interpolated",
                  _step_flow("`Round ${n} of 3. Re-check.`", "agentType: 'reviewer'"))
rbb_unread_refuse("reviewer-brief-blind: refused: a Workflow agent() reviewer whose marker is split by an interpolation",
                  _step_flow("`Round 2${x} of 3. Re-check.`", "agentType: 'reviewer'"))
rbb_unread_refuse("reviewer-brief-blind: refused: a Workflow agent() reviewer, Round 1 in an interpolated template",
                  _step_flow("`Round 1 of 3. Branch ${b}`", "agentType: 'reviewer'"))
# The controls. A plain template with a lone quote and comment openers is read through: its twin holds a report, so a
# scan that drops the call would fail the twin, not pass the plain template by accident.
add("reviewer-brief-blind: allowed: a Workflow agent() reviewer whose prompt is a plain template, no ${}, a lone quote and // inside",
    "allow", tool="Workflow",
    script="const r = await agent(`Check the floor fix.\nDon't skip /* the // check.\nFiles: hooks/guard.py.`, "
           "{agentType: 'reviewer', model: 'haiku'}); return r")
add("reviewer-brief-blind: refused: a Workflow agent() reviewer, the same plain template with a report under it",
    "deny", RBB, tool="Workflow",
    script="const r = await agent(`Check the floor fix.\nDon't skip /* the // check.\nDone: BUILT c204a1f.\nDeviations: none.`, "
           "{agentType: 'reviewer', model: 'haiku'}); return r")
add("reviewer-brief-blind: allowed: a Workflow agent() builder whose prompt is a variable holding a report",
    "allow", tool="Workflow", script=RBB_REPORT_PROMPT + _step_flow("prompt", "agentType: 'builder', model: 'sonnet'"))

# The owner override lifts the refusal, as it lifts the role-model refusal (role_override_lift_check copied here).
RBB_SPAWN = {"prompt": "Check the floor fix.\nDone: BUILT c204a1f.\nDeviations: none.", "subagent_type": "reviewer",
             "model": "haiku"}


def reviewer_brief_override_check():
    """One override lifts the reviewer-brief-blind refusal once, and the spent override refuses again. The first step
    makes the call with no override and wants the refusal, so a guard that refuses nothing cannot turn this green."""
    config, session = ov_config("reviewer-brief-blind"), "rbb-override"

    def call(seconds):
        return ov_call("Agent", dict(RBB_SPAWN), NOGIT, config, session, seconds)

    ok, why = ov_story([("no override", lambda: call(0), "deny", RBB)])
    if not ok:
        return False, why
    note = ov_type(config, session, "override")
    ok, why = ov_story([
        ("the first spawn, under the override", lambda: call(60), "allow", RBB),
        ("the next spawn, override spent", lambda: call(120), "deny", RBB),
    ], note)
    if not ok:
        return False, why
    return True, "refused, lifted once by an override, refused again once it was spent"


RBB_OVERRIDE_LABEL = "reviewer-brief-blind: an owner override lifts the refusal once, then the spent override refuses"
FIXTURELESS_CHECKS.add(reviewer_brief_override_check)  # its folders are its own, and it reads no lazy fixture
# LOG_CHECKS froze above this section, so LOG_CHECKS_EXTRA no longer reaches it. The check joins LOG_CHECKS here, as
# the simulator section's override checks do.
LOG_FAMILY[RBB_OVERRIDE_LABEL] = FAMILY
LOG_CHECKS = LOG_CHECKS + ((RBB_OVERRIDE_LABEL, reviewer_brief_override_check),)


