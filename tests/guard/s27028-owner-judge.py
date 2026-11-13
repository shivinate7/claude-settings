# section 27028
FAMILY = "owner-judge"
#
# Rules question-form and owner-judge: one form for a waiting-page decision, judged by hooks/question_form.py.
# These cases run the real guard; the module's own cases, with item 92's shape, are in
# hooks/test_question_form.py. Built against a named incident: waiting item 34, Oct 28 13:40 CDT. A decision
# about CI internals, which CI job runs a check, reached the owner with options, a pick and a why. He saved b
# with "i really can't figure out how to decide". A decision carries these lines in `context`, each at a line
# start, in any case: `Goal: <goal>`, `Problem (<stake>): <text>`, and one to three
# `Based on (<kind>): <premise>`. <stake> is one of goal, money, risk, rule, cannot undo; <kind> is one of
# PREMISE_KINDS. Each option has a non-empty gain and lose. Only those lines count: the same words in the
# title, an option, why or elsewhere in context never do. A stood pick (`stands: true`) may write
# `Problem: <text>` with no stake. A task, a status-only or rank-only update, another artifact's page and a
# decision with status closed (the chat-answer flow writes one already answered) pass.
# A missing line is refused by `question-form`. The contract does not say whether `question-form` or
# `owner-judge` names a bare Problem line or a stake outside the set, so those cases accept either id.

OJ_KINDS = ("goal", "money", "risk", "rule", "cannot undo")
OJ_DOC = "ci-check-job"
OJ_CTX = "The stamp check runs in the lint job today. The test job could run it too."
OJ_RULE = "question-form"
OJ_PROBLEM_RULES = ("question-form", "owner-judge")
OJ_OPTIONS = [
    {"key": "a", "label": "Keep the check in the lint job", "how": "Leave the workflow as it is.",
     "gain": "No change to review.", "lose": "The lint job stays the slow one."},
    {"key": "b", "label": "Move the check to the test job", "how": "Move the step to the test job.",
     "gain": "The lint job gets faster.", "lose": "The test job runs longer."}]


def oj_ctx(goal=OJ_GOAL, problem=OJ_STAKE, based=(OJ_BASED,), tail=OJ_CTX, departs=QD_LINE, against=OJ_AGAINST):
    """The context of a decision: the form lines, the Departs from line, the Against the pick line, then the prose.
    A line passed as None or empty is left out."""
    return "\n".join(line for line in (goal, problem, *based, departs, against, tail) if line)


OJ_GOOD = oj_ctx()


def oj_item(**over):
    """Item 34's shape: a decision about which CI job runs a check, with options, a pick and a why, and no form lines."""
    item = {"id": OJ_DOC, "kind": "decision", "status": "open", "title": "Which CI job runs the stamp check?",
            "context": OJ_CTX, "options": OJ_OPTIONS, "pick": "a",
            "why": "The lint job already holds the other format checks."}
    item.update(over)
    return with_shown({k: v for k, v in item.items() if v is not None})


def oj(name, expected, item, rule=OJ_RULE, **extra):
    """One write of the item. `rule` names the refusal on a deny. A tuple of ids is any-of, and the
    refusal must name the Problem line either way."""
    if isinstance(rule, tuple):
        extra["carries"] = (*extra.get("carries", ()), "Problem", rule)
        rule = None
    wp_write("owner judge: " + name, expected, rule, item, doc_id=OJ_DOC, **extra)


def oj_replace(name, expected, field, old, new, rule=OJ_RULE):
    """One str_replace on a field of the decision. The rule judges a context edit that takes a form line out."""
    oj("a str_replace " + name, expected, None, rule=rule, action="str_replace", field=field, old_str=old,
       new_str=new)


def oj_write(data, op="set", collection="items"):
    return {"op": op, "collection": collection, "doc_id": OJ_DOC, "data": with_shown(data)}


def oj_batch(name, expected, writes, **extra):
    add("owner judge: a batch " + name, expected, OJ_RULE if expected == "deny" else None,
        tool="ArtifactData", cwd=PQ_REPO, url=PQ_URL, action="batch", writes=writes, **extra)


oj("item 34's shape (a CI job choice with options, a pick, a why and no form lines) is denied", "deny",
   oj_item())
oj("the refusal names the three lines, the five stakes and stands: true", "deny", oj_item(),
   carries=("Goal", "Problem", "Based on", "stands: true", *OJ_KINDS))
# Wrong-field class: the words are there, the lines are not.
oj("risk and rule words in the title, the options and why, with no form lines, are denied", "deny",
   oj_item(title="Which CI job runs the stamp check? A risk, a rule",
           options=[dict(OJ_OPTIONS[0], label="Keep it in the lint job (a rule, no risk)",
                         how="Goal: leave the workflow. Money: none. Cannot undo: nothing."), OJ_OPTIONS[1]],
           why="Small stake: a risk and a rule, no goal, no money, nothing that cannot undo."))
oj("risk and rule words in context, away from the form lines, are denied", "deny",
   oj_item(context=OJ_CTX + "\nThis is a rule change and a risk to the goal."))
oj("a Problem line in the title, not in context, is denied", "deny",
   oj_item(context=oj_ctx(problem=None), title=OJ_STAKE))
oj("a Problem line in why, not in context, is denied", "deny",
   oj_item(context=oj_ctx(problem=None), why="The lint job already holds the other format checks.\n" + OJ_STAKE))
oj("a Problem line in an option, not in context, is denied", "deny",
   oj_item(context=oj_ctx(problem=None), options=[dict(OJ_OPTIONS[0], how=OJ_STAKE), OJ_OPTIONS[1]]))

# Missing and malformed lines.
oj("no Goal line is denied", "deny", oj_item(context=oj_ctx(goal=None)))
oj("a Goal phrase mid-line does not count", "deny", oj_item(context=oj_ctx(goal="Aim. " + OJ_GOAL)))
oj("no Problem line is denied", "deny", oj_item(context=oj_ctx(problem=None)))
oj("a Problem phrase mid-line does not count", "deny", oj_item(context=oj_ctx(problem="Reason. " + OJ_STAKE)))
oj("a stake outside the set (internals) is denied", "deny",
   oj_item(context=oj_ctx(problem="Problem (internals): which job runs the check")), rule=OJ_PROBLEM_RULES)
oj("a bare Problem line with nothing after the colon is denied", "deny",
   oj_item(context=oj_ctx(problem="Problem (risk):   ")), rule=OJ_PROBLEM_RULES)
oj("a stake with no colon and no text is denied", "deny",
   oj_item(context=oj_ctx(problem="Problem (risk)")), rule=OJ_PROBLEM_RULES)
oj("a Problem line with no stake, on a decision that is not a stood pick, is denied", "deny",
   oj_item(context=oj_ctx(problem="Problem: which job runs the check, and why it needs your word")),
   rule=OJ_PROBLEM_RULES)
oj("no Based on line is denied", "deny", oj_item(context=oj_ctx(based=())))
oj("four Based on lines are denied", "deny",
   oj_item(context=oj_ctx(based=(OJ_BASED, "Based on (notes): two", "Based on (notes): three",
                                 "Based on (notes): four"))))
oj("a Based on kind outside the set is denied", "deny",
   oj_item(context=oj_ctx(based=("Based on (guess): the lint job is slow.",))))
oj("a Based on line with no kind is denied", "deny",
   oj_item(context=oj_ctx(based=("Based on: the lint job is slow.",))))
oj("an option with no lose is denied", "deny",
   oj_item(context=OJ_GOOD, options=[OJ_OPTIONS[0], {k: v for k, v in OJ_OPTIONS[1].items() if k != "lose"}]))
oj("an option with no gain is denied", "deny",
   oj_item(context=OJ_GOOD, options=[{k: v for k, v in OJ_OPTIONS[0].items() if k != "gain"}, OJ_OPTIONS[1]]))
oj("an option with an empty lose is denied", "deny",
   oj_item(context=OJ_GOOD, options=[OJ_OPTIONS[0], dict(OJ_OPTIONS[1], lose="")]))
oj("a decision with no context is denied", "deny", oj_item(context=None))
oj("an item with no kind is judged as a decision and denied", "deny", oj_item(kind=None))
oj("stands false with no form lines is denied", "deny", oj_item(stands=False))
oj("port false with no form lines is denied", "deny", oj_item(port=False))

# False-alarm class: a stake of any kind, a premise of any kind, in any case, at a line start, is the form.
for _kind in OJ_KINDS:
    oj("a Problem line of stake %s is allowed" % _kind, "allow",
       oj_item(context=oj_ctx(problem="Problem (%s): the pick changes what ships" % _kind)))
for _premise in PREMISE_KINDS:
    oj("a Based on line of kind %s is allowed" % _premise, "allow",
       oj_item(context=oj_ctx(based=("Based on (%s): the lint job is slow." % _premise,))))
oj("three Based on lines are allowed", "allow",
   oj_item(context=oj_ctx(based=(OJ_BASED, "Based on (notes): two", "Based on (assumed): three"))))
oj("a Problem line with no dash is allowed", "allow",
   oj_item(context=oj_ctx(problem="Problem (money): about $40 a month of runner time")))
oj("the Problem label is read in lower case", "allow",
   oj_item(context=oj_ctx(problem="problem (risk): the pick changes what ships")))
oj("the Problem line is read in upper case", "allow",
   oj_item(context=oj_ctx(problem="PROBLEM (RISK): the pick changes what ships")))
oj("comment openers and an apostrophe in the form lines are plain text", "allow",
   oj_item(context=oj_ctx(goal="Goal: keep the stamp check's job, with //path, /* glob and # tags, working.",
                          problem="Problem (risk): don't parse # or // here, so it needs your word")))
oj("a context that holds only the form lines is allowed", "allow", oj_item(context=oj_ctx(tail=None)))
oj("form lines with more lines after them are allowed", "allow",
   oj_item(context=oj_ctx(tail=OJ_CTX + "\nThe test job runs longer.")))
oj("a decision with the form is allowed", "allow", oj_item(context=OJ_GOOD))

# Stood-pick class: the session's own pick stands, so the stake needs no kind.
oj("a stood pick with `Problem:` and no stake is allowed", "allow",
   oj_item(stands=True, context=oj_ctx(problem="Problem: which job runs the check, and why it needs your word")))
oj("a stood pick with a stake is allowed", "allow", oj_item(stands=True, context=OJ_GOOD))
oj("a port with a Departs from line and the form is allowed", "allow",
   oj_item(port=True, context=oj_ctx(tail=OJ_CTX + "\n" + PQ_DEPARTS)))
oj("a task with a Why yours line and no form lines is not judged", "allow",
   tn_task(context=TN_CTX + "\n" + TN_WHY))
oj("a record that is neither a decision nor a task is not judged", "allow", oj_item(kind="note"))
oj("an items set to another artifact is allowed", "allow", oj_item(), url="https://claude.ai/artifact/other")
oj("a set to another collection is allowed", "allow", oj_item(), collection="answers")
add("owner judge: a repo with no waiting page allows item 34's shape", "allow", tool="ArtifactData",
    cwd=NOGIT, url=PQ_URL, action="set", collection="items", doc_id=OJ_DOC, data=oj_item())

# Updates: judged only for the fields they carry (context, options), and only with kind decision.
oj("an update that carries kind decision and context with no form lines is denied", "deny",
   {"kind": "decision", "context": OJ_CTX}, action="update")
oj("an update that carries kind decision and a context with the form is allowed", "allow",
   {"kind": "decision", "context": OJ_GOOD}, action="update")
oj("an update that carries kind decision, a stood pick and `Problem:` with no stake is allowed", "allow",
   {"kind": "decision", "context": oj_ctx(problem="Problem: which job runs the check"), "stands": True},
   action="update")
oj("an update that carries kind decision and no context is allowed", "allow",
   {"kind": "decision", "title": "Which CI job runs the check?"}, action="update")
oj("an update that carries kind decision and options with an option that has no lose is denied", "deny",
   {"kind": "decision", "options": [OJ_OPTIONS[0], {k: v for k, v in OJ_OPTIONS[1].items() if k != "lose"}]},
   action="update")
oj("an update that carries kind decision and options with a gain and a lose each is allowed", "allow",
   {"kind": "decision", "options": OJ_OPTIONS}, action="update")
oj("an update of the status only is allowed", "allow", {"status": "closed"}, action="update")
oj("an update of the rank only is allowed", "allow", {"rank": 3}, action="update")

# A closed decision asks the owner nothing. The writer's chat-answer flow (skills/waiting-page) writes a
# decision already answered: status closed, the answer and its time in context, no form lines. An open
# decision with the same context is still judged.
OJ_ANSWERED = OJ_CTX + "\nAnswer from chat, 10:42: keep the check in the lint job."
oj("a closed decision with the chat answer in context and no form lines is allowed", "allow",
   oj_item(status="closed", context=OJ_ANSWERED))
oj("a closed decision with no options and no form lines is allowed", "allow",
   {"id": OJ_DOC, "kind": "decision", "status": "closed", "title": "Which CI job runs the stamp check?",
    "context": OJ_ANSWERED})
oj("an update that carries kind decision, status closed and context, no form lines, is allowed", "allow",
   {"kind": "decision", "status": "closed", "context": OJ_ANSWERED}, action="update")
oj("an open decision with the chat answer in context and no form lines is denied", "deny",
   oj_item(status="open", context=OJ_ANSWERED))
oj("an update that carries kind decision, status open and context, no form lines, is denied", "deny",
   {"kind": "decision", "status": "open", "context": OJ_ANSWERED}, action="update")

# A str_replace on context is judged when old_str holds a form line and new_str does not.
oj_replace("that drops the Problem line from context is denied", "deny", "context", OJ_GOOD,
           oj_ctx(problem=None))
oj_replace("that drops the Goal line from context is denied", "deny", "context", OJ_GOOD, oj_ctx(goal=None))
oj_replace("that drops the only Based on line from context is denied", "deny", "context", OJ_GOOD,
           oj_ctx(based=()))
oj_replace("that swaps the Problem line for a stake outside the set is denied", "deny", "context", OJ_STAKE,
           "Problem (internals): which job runs the check", rule=OJ_PROBLEM_RULES)
oj_replace("that keeps every form line in context is allowed", "allow", "context", OJ_GOOD,
           oj_ctx(tail="The stamp check runs in the test job today."))
oj_replace("that swaps the Problem line for another stake is allowed", "allow", "context", OJ_STAKE,
           "Problem (money): the test job costs more runner time, so it needs your word")
oj_replace("whose old_str holds no form line is allowed", "allow", "context", OJ_CTX,
           "The stamp check runs in the test job today.")
oj_replace("on the title is allowed", "allow", "title", "Which CI job runs the stamp check?",
           "Which CI job runs the format check?")
oj_replace("on why is not judged", "allow", "why", OJ_STAKE, "The lint job is shorter.")

# A batch judges each write.
oj_batch("with an item that has no form lines among the sets is denied", "deny",
         [oj_write({"note": "x"}, collection="answers"), oj_write(oj_item())])
oj_batch("whose second write has no form lines is denied", "deny",
         [oj_write(oj_item(context=OJ_GOOD)), oj_write(oj_item(id="second"))])
oj_batch("with an update that carries kind decision and context, no form lines, is denied", "deny",
         [oj_write({"kind": "decision", "context": OJ_CTX}, op="update")])
oj_batch("with a str_replace that drops the Problem line is denied", "deny",
         [{"op": "str_replace", "collection": "items", "doc_id": OJ_DOC, "field": "context",
           "old_str": OJ_GOOD, "new_str": oj_ctx(problem=None)}])
oj_batch("of decisions that each carry the form is allowed", "allow",
         [oj_write(oj_item(context=OJ_GOOD)), oj_write(oj_item(id="second", context=OJ_GOOD))])
oj_batch("with a stood pick that writes `Problem:` with no stake is allowed", "allow",
         [oj_write(oj_item(stands=True, context=oj_ctx(problem="Problem: which job runs the check")))])
oj_batch("with a closed decision and no form lines is allowed", "allow",
         [oj_write(oj_item(status="closed", context=OJ_ANSWERED))])
oj_batch("with a closed decision, then an open one with no form lines, is denied", "deny",
         [oj_write(oj_item(status="closed", context=OJ_ANSWERED)), oj_write(oj_item(id="second"))])

# file_path data is read as `data` is.
os.makedirs(os.path.join(ROOT, "oj"), exist_ok=True)
OJ_FILE_BAD = os.path.join(ROOT, "oj", "bad.json")
OJ_FILE_GOOD = os.path.join(ROOT, "oj", "good.json")
with open(OJ_FILE_BAD, "w", encoding="utf-8") as _f:
    json.dump(with_shown(oj_item()), _f)
with open(OJ_FILE_GOOD, "w", encoding="utf-8") as _f:
    json.dump(with_shown(oj_item(context=OJ_GOOD)), _f)
oj("file_path data with no form lines is denied", "deny", None, file_path=OJ_FILE_BAD)
oj("file_path data with the form is allowed", "allow", None, file_path=OJ_FILE_GOOD)

# An older rule keeps its own id when the form is there (which rule names an item that breaks both is not fixed).
wp_write("owner judge: a widening pick with the form lines is refused by uniform-pick", "deny",
         "uniform-pick", oj_item(context=OJ_GOOD, options=[UP_WIDE, UP_MATCH]), doc_id=OJ_DOC)
wp_write("owner judge: a port with no Departs from line and the form lines is refused by port-question",
         "deny", "port-question", oj_item(context=oj_ctx(departs=None, tail=PQ_CTX)), doc_id=OJ_DOC)
wp_write("owner judge: a press with no link and the form lines is refused by press-link", "deny",
         "press-link", oj_item(context=OJ_GOOD, options=[PL_BAD_OPT, PL_KEEP_OPT]), doc_id=OJ_DOC)


# --------------------------------------------------------------------------- a question says how it departs from main
