# section 43700
FAMILY = "goal-text-cites-role-ruling"
#
# Rule goal-text-cites-role-ruling. A send_message, a SendMessage, an Agent spawn or a create_session whose text (its
# message, or its prompt) states a limit on a session's role is refused unless the same sentence or the same line names
# a ruling or a decision id.
#
#   A limit   a role, then cannot, can't, can not, won't, may not, must not or isn't allowed to, then merge, push or mark
#             ready. A send to another session may state it in the second person: You cannot merge.
#   A role    triage (also a triage session), the batch runner, runner <n> or runner #<n>, the coordinator, a lane or lanes
#             (lane <n> or lane <slug> too), the consultant or the arbiter (GLOSSARY.md).
#   A cite    an id in backticks, or the word ruling or decision with an id after it. An id is a hyphenated slug.
#
# The case it stops: a goal text told triage that triage cannot merge, with no ruling cited. Decision `draft-until-reviewed`
# (ruling Q2: each session merges its own pull requests) makes that limit wrong.
#
# Quoted text is not a statement. A limit in double or single quotes, in a blockquote, in a code span or in a fenced block
# passes, so a report can carry a relayed owner word or a refusal text. A quote that never closes is text: a lone apostrophe,
# backtick or double quote before a limit does not hide it from the scanner. An apostrophe inside a word (don't, runner 10's)
# opens no single quote.
#
# Out of scope: every other tool. A limit in a Bash command passes this rule. So does a limit whose subject is no role (a PR,
# a branch), a grant (can merge, may push) and a verb outside merge, push and mark ready.
#
# The fixtures use no clock, and no session that a roster or transcript could hold: GTR_TARGET is no record row, and NOGIT
# is no git tree. So no other send_message rule reads a roster, a transcript or a stamp for these cases.

GTR_RULE = "goal-text-cites-role-ruling"
GTR_LABEL = GTR_RULE + ": "  # every case name starts with the rule, so GUARD_FAMILY and MUTATE_ONLY reach these cases alone
GTR_TARGET = "session_GTRTARGET01"  # a target that no record row or listed session holds
GTR_CITE = (("ruling", "decision"),)  # the one remedy the refusal names: cite a ruling or decision, or drop the limit
GTR_PROSE = "\n".join("Status line %d: the page is current." % number for number in range(1, 201))  # full size, no limit
GTR_LONG_LIMIT = "PR 12 is green.\nRunner 10 is idle.\nTriage cannot merge; hand to runner 10.\n" + GTR_PROSE
# The spawn and session-start tools carry their goal text in `prompt`. Each takes the fields its call needs, so a case
# reaches this rule and no other: a sonnet model clears the model floor, and the Explore type is no builder.
GTR_PROMPT_FIELDS = {
    "Agent": {"subagent_type": "Explore", "description": "goal text", "model": "sonnet"},
    CREATE_SESSION_CALL: {"model": "sonnet"},
}


def _gtr_fields(tool, message):
    """The tool_input of a send or a spawn. SendMessage names its receiver in `to`, the MCP send in `session_id`, and an
    Agent spawn or a create_session carries its goal text in `prompt`."""
    if tool == SENDMESSAGE_TOOL:
        return {"to": "triage", "message": message}
    if tool in GTR_PROMPT_FIELDS:
        return dict(GTR_PROMPT_FIELDS[tool], prompt=message)
    return {"session_id": GTR_TARGET, "message": message}


def gtr_refuse(name, message, tool=SEND_MESSAGE):
    """A send or a spawn the guard refuses under this rule. The reason names the rule and the one remedy."""
    add(GTR_LABEL + name, "deny", rule=GTR_RULE, tool=tool, cwd=NOGIT, carries=GTR_CITE, **_gtr_fields(tool, message))


def gtr_allow(name, message, tool=SEND_MESSAGE):
    """A send or a spawn the guard lets through silently. This rule prints nothing for it."""
    add(GTR_LABEL + name, "allow", tool=tool, cwd=NOGIT, silent=True, **_gtr_fields(tool, message))


# ---- Refused: a limit on a role with no cite. The incident text first.
gtr_refuse("the incident text, with no ruling, is refused", "Triage cannot merge; hand to runner 10.")
gtr_refuse("the contraction can't is refused", "Triage can't merge the PR.")
gtr_refuse("the contraction with a curly apostrophe is refused", "Triage can’t merge the PR.")
gtr_refuse("can not, in two words, is refused", "The lane can not merge its own PR.")
gtr_refuse("may not merge is refused for the batch runner", "The batch runner may not merge its lane PRs.")
gtr_refuse("must not merge is refused for runner 10", "Runner 10 must not merge.")
gtr_refuse("must not push is refused for the coordinator", "The coordinator must not push to main.")
gtr_refuse("cannot push is refused for the consultant", "The consultant cannot push its own branch.")
gtr_refuse("may not mark ready is refused for the arbiter", "The arbiter may not mark ready the pull request.")
gtr_refuse("cannot mark ready is refused for the coordinator", "The coordinator cannot mark ready the integration PR.")
gtr_refuse("an upper-case limit is refused", "TRIAGE CANNOT MERGE.")
gtr_refuse("a role in the middle of a sentence is refused", "We agreed that triage cannot merge the PR.")
gtr_refuse("a limit on the third line of a 200-line message is refused", GTR_LONG_LIMIT)
gtr_refuse("SendMessage: a lane may not push, with no cite, is refused", "The lane may not push.", tool=SENDMESSAGE_TOOL)

# ---- Refused: a cite that does not count. A ruling word with no id, a decision word with no id, and a cite on another line.
gtr_refuse("the word ruling with no id is no cite, so the limit is refused", "Per the owner's ruling, triage cannot merge.")
gtr_refuse("the word decision with no id is no cite, so the limit is refused", "Triage cannot merge; the decision is open.")
gtr_refuse("a cite on the line above does not exempt the limit below it",
         "Decision draft-until-reviewed covers the merge.\nTriage cannot merge; hand to runner 10.")
gtr_refuse("a cite on the line below does not exempt the limit above it",
         "Triage cannot merge; hand to runner 10.\nSee decision session-tiers.")

# ---- Refused: the scanner. A quote, a code span or a fence that never closes, or closes before the limit, hides nothing.
gtr_refuse("a lone apostrophe before an unquoted limit does not open a quote, so the limit is refused",
         "Don't wait: triage can't merge the PR.")
gtr_refuse("a lone backtick before an unquoted limit does not open a code span, so the limit is refused",
         "Note the `pins: triage cannot merge; hand to runner 10.")
gtr_refuse("a lone double quote before an unquoted limit does not open a quote, so the limit is refused",
         'Owner said "go on. Triage cannot merge; hand to runner 10.')
gtr_refuse("a limit after a closed fenced block is refused, since the scanner returns to prose after the fence",
         "```\nrefused: example text\n```\nTriage cannot merge; hand to runner 10.")
gtr_refuse("a limit after a code span that holds comment openers is refused",
         "Paths `a//b` and `/*` are examples. Triage cannot merge; hand to runner 10.")
# Apostrophes inside words open no single quote. A naive pairing would hide the limit between them, so it must read.
gtr_refuse("a limit between two apostrophes in words is refused",
         "Owner's call: triage cannot merge; it's runner 10's job.")

# ---- Refused: the role and verb forms the first version missed. A plural role, a lane with a number or a branch slug, a
# runner with a hash number, a triage session, the contractions won't and isn't allowed to, and the second person sent to
# another session. Each reads allow on the old code.
gtr_refuse("plural lanes cannot merge is refused", "lanes cannot merge their own PRs.")
gtr_refuse("a lane with a number cannot merge is refused", "lane 3 cannot merge its PR.")
gtr_refuse("a lane with a branch slug cannot merge is refused", "lane my-branch-slug cannot merge its PR.")
gtr_refuse("a runner with a hash number cannot merge its lane PRs is refused", "Runner #10 cannot merge its lane PRs.")
gtr_refuse("a triage session cannot merge is refused", "The triage session cannot merge the PR.")
gtr_refuse("won't, in place of cannot, is refused for triage", "Triage won't merge the page.")
gtr_refuse("isn't allowed to, in place of may not, is refused for triage", "Triage isn't allowed to merge.")
gtr_refuse("a second-person limit sent to another session is refused", "You cannot merge this PR until CI is green.")

# ---- Refused: the same limit in a spawn prompt or a session start. The step covers any goal or brief a session writes for
# another session or agent, so an Agent prompt and a create_session prompt are judged as a send is.
gtr_refuse("the incident text in an Agent prompt is refused", "Triage cannot merge; hand to runner 10.", tool="Agent")
gtr_refuse("the incident text in a create_session prompt is refused", "Triage cannot merge; hand to runner 10.",
         tool=CREATE_SESSION_CALL)
# Controls: the same two calls with no limit pass, so a red above is the limit and not the call.
gtr_allow("an Agent prompt with no limit is allowed", "Explore the page and list its states.", tool="Agent")
gtr_allow("a create_session prompt with no limit is allowed", "Explore the page and list its states.",
          tool=CREATE_SESSION_CALL)

# ---- Allowed: a limit quoted as text, which is not a statement. Owner words, a blockquote, a refusal text in a report, a
# code span and a fenced block, and an inner line of a fenced block.
gtr_allow("owner words in double quotes, with the owner named, are allowed",
          'Owner, typed: "triage cannot merge; hand to runner 10."')
gtr_allow("owner words in single quotes, with the owner named, are allowed", "Owner said 'triage cannot merge'.")
gtr_allow("a limit in a blockquote is allowed", "> Triage cannot merge; hand to runner 10.")
gtr_allow("a limit in a fenced block, quoted as refusal text, is allowed",
          "Refusal text, verbatim:\n```\nTriage cannot merge; hand to runner 10.\n```\nResent without it.")
gtr_allow("a refusal quoted in double quotes inside a report is allowed",
          'Report: the guard refused "triage cannot merge", and I resent without it.')
gtr_allow("a limit in an inline code span is allowed",
          "Report: the guard refused `triage cannot merge`, and I resent without it.")
gtr_allow("the inner line of a multi-line fenced block is allowed",
          "Lines the guard read:\n```\nPR 12 is green.\nTriage cannot merge.\n```")

# ---- Allowed: a limit with a cite in its sentence or on its line.
gtr_allow("a limit with a backticked decision id in the same sentence is allowed",
          "Triage cannot merge (decision `session-tiers`).")
gtr_allow("a limit with a bare id after the word ruling is allowed",
          "Triage cannot merge, per ruling draft-until-reviewed.")
gtr_allow("a limit with a bare decision id after the word decision is allowed",
          "Triage cannot merge; decision standing-merge-grant says so.")
gtr_allow("a limit with a backticked id in the next sentence on its line is allowed",
          "Triage cannot merge. See `draft-until-reviewed`.")
gtr_allow("a limit whose sentence wraps onto a line that holds the cite is allowed",
          "Triage cannot merge the lane PR, which\ndecision draft-until-reviewed covers.")
gtr_allow("SendMessage: a limit with a decision id in its sentence is allowed",
          "Triage cannot merge (decision draft-until-reviewed).", tool=SENDMESSAGE_TOOL)

# ---- Allowed: a limit that is no role limit. A passive names no act by a role, and a first-person limit names no role.
gtr_allow("a passive limit, which names no act by a role, is allowed", "Triage cannot be merged by anyone.")
gtr_allow("a first-person limit with no role is allowed", "I cannot merge this PR until CI is green.")

# ---- Allowed: false alarms. A subject that is no role, a grant, a verb outside the three, and a message with no limit.
gtr_allow("a status line with a role and no limit is allowed", "Triage: PR 12 is ready for your review.")
gtr_allow("a limit whose subject is a PR, which is no role, is allowed", "PR #12 cannot merge until its run is green.")
gtr_allow("a limit whose subject is a branch, which is no role, is allowed", "The branch cannot push: the proxy returns 403.")
gtr_allow("a grant with can merge is allowed", "Triage can merge the page after the owner answers.")
gtr_allow("a lane's grant with can merge is allowed", "The lane can merge its own PR once CI is green.")
gtr_allow("a grant with may push is allowed", "Runner 10 may push the archive branch.")
gtr_allow("a limit with a verb outside merge, push and mark ready is allowed", "Triage cannot reach the page.")
gtr_allow("a role with no verb is allowed", "Triage holds the waiting-page item for the owner.")
gtr_allow("a past report of a merge is allowed", "Triage merged PR 12 and archived the lane.")
gtr_allow("an empty message is allowed", "")
gtr_allow("a full-size message with no limit is allowed", GTR_PROSE)
add(GTR_LABEL + "a Bash command that carries the limit is out of scope and allowed", "allow", tool="Bash", cwd=NOGIT,
    silent=True, command='echo "Triage cannot merge; hand to runner 10."')
