# section 43700
FAMILY = "goal-text-cites-role-ruling"
#
# Rule goal-text-cites-role-ruling. A send_message, or a SendMessage, whose text
# states a limit on a session's role is refused unless the same sentence or the same line names a ruling or a decision id.
#
#   A limit   a role, then cannot, can't, can not, may not or must not, then merge, push or mark ready.
#   A role    triage, the batch runner, runner <n>, the coordinator, a lane, the consultant or the arbiter (GLOSSARY.md).
#   A cite    an id in backticks, or the word ruling or decision with an id after it. An id is a hyphenated slug.
#
# The case it stops: a goal text told triage that triage cannot merge, with no ruling cited. Ruling own-everyone-merges
# (each session merges its own pull requests) makes that limit wrong.
#
# Quoted text is not a statement. A limit in double quotes, in a blockquote, in a code span or in a fenced block passes, so a
# report can carry a relayed owner word or a refusal text. A quote that never closes is text: a lone apostrophe, backtick or
# double quote before a limit does not hide it from the scanner.
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


def _gtr_fields(tool, message):
    """The tool_input of a send: SendMessage names its receiver in `to`, and the MCP tool in `session_id`."""
    if tool == SENDMESSAGE_TOOL:
        return {"to": "triage", "message": message}
    return {"session_id": GTR_TARGET, "message": message}


def gtr_deny(name, message, tool=SEND_MESSAGE):
    """A send the guard refuses under this rule. The reason names the rule and the one remedy."""
    add(GTR_LABEL + name, "deny", rule=GTR_RULE, tool=tool, cwd=NOGIT, carries=GTR_CITE, **_gtr_fields(tool, message))


def gtr_allow(name, message, tool=SEND_MESSAGE):
    """A send the guard lets through silently. This rule prints nothing for it."""
    add(GTR_LABEL + name, "allow", tool=tool, cwd=NOGIT, silent=True, **_gtr_fields(tool, message))


# ---- Refused: a limit on a role with no cite. The incident text first.
gtr_deny("the incident text, with no ruling, is refused", "Triage cannot merge; hand to runner 10.")
gtr_deny("the contraction can't is refused", "Triage can't merge the PR.")
gtr_deny("the contraction with a curly apostrophe is refused", "Triage can’t merge the PR.")
gtr_deny("can not, in two words, is refused", "The lane can not merge its own PR.")
gtr_deny("may not merge is refused for the batch runner", "The batch runner may not merge its lane PRs.")
gtr_deny("must not merge is refused for runner 10", "Runner 10 must not merge.")
gtr_deny("must not push is refused for the coordinator", "The coordinator must not push to main.")
gtr_deny("cannot push is refused for the consultant", "The consultant cannot push its own branch.")
gtr_deny("may not mark ready is refused for the arbiter", "The arbiter may not mark ready the pull request.")
gtr_deny("cannot mark ready is refused for the coordinator", "The coordinator cannot mark ready the integration PR.")
gtr_deny("an upper-case limit is refused", "TRIAGE CANNOT MERGE.")
gtr_deny("a role in the middle of a sentence is refused", "We agreed that triage cannot merge the PR.")
gtr_deny("a limit on the third line of a 200-line message is refused", GTR_LONG_LIMIT)
gtr_deny("SendMessage: a lane may not push, with no cite, is refused", "The lane may not push.", tool=SENDMESSAGE_TOOL)

# ---- Refused: a cite that does not count. A ruling word with no id, a decision word with no id, and a cite on another line.
gtr_deny("the word ruling with no id is no cite, so the limit is refused", "Per the owner's ruling, triage cannot merge.")
gtr_deny("the word decision with no id is no cite, so the limit is refused", "Triage cannot merge; the decision is open.")
gtr_deny("a cite on the line above does not exempt the limit below it",
         "Ruling own-everyone-merges covers the merge.\nTriage cannot merge; hand to runner 10.")
gtr_deny("a cite on the line below does not exempt the limit above it",
         "Triage cannot merge; hand to runner 10.\nSee decision session-tiers.")

# ---- Refused: the scanner. A quote, a code span or a fence that never closes, or closes before the limit, hides nothing.
gtr_deny("a lone apostrophe before an unquoted limit does not open a quote, so the limit is refused",
         "Don't wait: triage can't merge the PR.")
gtr_deny("a lone backtick before an unquoted limit does not open a code span, so the limit is refused",
         "Note the `pins: triage cannot merge; hand to runner 10.")
gtr_deny("a lone double quote before an unquoted limit does not open a quote, so the limit is refused",
         'Owner said "go on. Triage cannot merge; hand to runner 10.')
gtr_deny("a limit after a closed fenced block is refused, since the scanner returns to prose after the fence",
         "```\nrefused: example text\n```\nTriage cannot merge; hand to runner 10.")
gtr_deny("a limit after a code span that holds comment openers is refused",
         "Paths `a//b` and `/*` are examples. Triage cannot merge; hand to runner 10.")

# ---- Allowed: a limit quoted as text, which is not a statement. Owner words, a blockquote, a refusal text in a report, a
# code span and a fenced block, and an inner line of a fenced block.
gtr_allow("owner words in double quotes, with the owner named, are allowed",
          'Owner, typed: "triage cannot merge; hand to runner 10."')
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
gtr_allow("a limit with a bare ruling id after the word ruling is allowed",
          "Triage cannot merge, per ruling own-everyone-merges.")
gtr_allow("a limit with a bare decision id after the word decision is allowed",
          "Triage cannot merge; decision standing-merge-grant says so.")
gtr_allow("a limit with a backticked ruling id in the next sentence on its line is allowed",
          "Triage cannot merge. See `own-everyone-merges`.")
gtr_allow("a limit whose sentence wraps onto a line that holds the cite is allowed",
          "Triage cannot merge the lane PR, which\nruling own-everyone-merges covers.")
gtr_allow("SendMessage: a limit with a ruling id in its sentence is allowed",
          "Triage cannot merge (ruling own-everyone-merges).", tool=SENDMESSAGE_TOOL)

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
