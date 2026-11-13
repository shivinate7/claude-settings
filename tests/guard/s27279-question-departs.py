# section 27279
FAMILY = "question-departs"
FAMILIES["question-departs"] = "the page writer: a decision says how it departs from main in a Departs from line, not a restatement of main"
#
# Rule question-departs (decision owner-judge's ruling, Oct 30: a question to the owner that restates main is
# not a question). A decision carries a line at a line start in `context`: `Departs from: <what on main> — <what
# changes>`. Both sides are non-empty, and the change side is not a restatement of main. The check runs after
# the form and the older rules, at the same ArtifactData call. A closed decision, a task, a note, an update that
# carries no context, and another artifact's page are not judged. The line sits in `context` only.

QD_DOC = "departs-item"
QD_RESTATE = "Departs from: agent-model-cap — Opus above the row stays the existing ask"
QD_WHY = "Why yours: a session on your computer was asked first and none could reach the remote"


def qd_item(**over):
    item = {"id": QD_DOC, "kind": "decision", "status": "open", "title": "Which CI job runs the stamp check?",
            "context": oj_ctx(), "options": OJ_OPTIONS, "pick": "a",
            "why": "The lint job already holds the other format checks."}
    item.update(over)
    return with_shown({k: v for k, v in item.items() if v is not None})


def qd(name, expected, item, action="set", **extra):
    kw = dict(action=action, collection="items", doc_id=QD_DOC, data=with_shown(item))
    kw.update(extra)
    add("question departs: " + name, expected, "question-departs" if expected == "deny" else None,
        tool="ArtifactData", cwd=PQ_REPO, **{"url": PQ_URL, **kw})


qd("a decision with the form and no Departs from line is denied", "deny", qd_item(context=oj_ctx(departs=None)))
qd("the refusal says to add the line", "deny", qd_item(context=oj_ctx(departs=None)), carries=("Departs from",))
qd("an empty Departs from line is denied", "deny", qd_item(context=oj_ctx(departs="Departs from:")))
qd("a line with no change side is denied", "deny",
   qd_item(context=oj_ctx(departs="Departs from: lint/stamp.py:run_stamp —")))
qd("a line with no separator is denied", "deny",
   qd_item(context=oj_ctx(departs="Departs from: lint/stamp.py:run_stamp")))
qd("a line with no left side is denied", "deny",
   qd_item(context=oj_ctx(departs="Departs from: — the stamp check moves to the lint job")))
qd("a line that restates main is denied", "deny", qd_item(context=oj_ctx(departs=QD_RESTATE)))
qd("a line whose change side is none is denied", "deny",
   qd_item(context=oj_ctx(departs="Departs from: lint/stamp.py:run_stamp — none")))
qd("a line whose change side is STAYS, in any case, is denied", "deny",
   qd_item(context=oj_ctx(departs="Departs from: lint/stamp.py:run_stamp — STAYS in the lint job")))
qd("a Departs from phrase mid-line does not count", "deny",
   qd_item(context=oj_ctx(departs="Why: Departs from: lint/stamp.py:run_stamp — the stamp moves")))
qd("a line in why, not in context, is denied", "deny", qd_item(context=oj_ctx(departs=None), why=QD_LINE))
qd("a line in an option, not in context, is denied", "deny",
   qd_item(context=oj_ctx(departs=None), options=[dict(OJ_OPTIONS[0], how=QD_LINE), OJ_OPTIONS[1]]))
qd("a valid line is allowed", "allow", qd_item())
qd("a valid line with a hyphen separator is allowed", "allow",
   qd_item(context=oj_ctx(departs="Departs from: lint/stamp.py:run_stamp - the stamp moves to the lint job")))
qd("a change side that holds the word nonetheless is allowed", "allow",
   qd_item(context=oj_ctx(departs="Departs from: lint/stamp.py:run_stamp — nonetheless the stamp moves")))
qd("comment openers and an apostrophe in the change side are plain text", "allow",
   qd_item(context=oj_ctx(departs="Departs from: lint/stamp.py:run_stamp — don't parse // or /* or # here")))

qd("a closed decision with the chat answer and no Departs from line is allowed", "allow",
   qd_item(status="closed", context=OJ_ANSWERED))
qd("a closed decision with the form and no Departs from line is allowed", "allow",
   qd_item(status="closed", context=oj_ctx(departs=None)))
qd("a task with a Why yours line and no Departs from line is allowed", "allow",
   {"id": QD_DOC, "kind": "task", "status": "open", "title": "Merge the batch", "steps": ["Open Terminal"],
    "context": QD_WHY})
qd("a note with the form and no Departs from line is allowed", "allow",
   qd_item(kind="note", context=oj_ctx(departs=None)))
qd("an update of the status only is allowed", "allow", {"status": "closed"}, action="update")
qd("an update that carries kind decision and no context is allowed", "allow",
   {"kind": "decision", "title": "Which CI job runs the check?"}, action="update")
qd("an update that carries kind decision and a context with no Departs from line is denied", "deny",
   {"kind": "decision", "context": oj_ctx(departs=None)}, action="update")
qd("an update that carries kind decision and a context with a restating line is denied", "deny",
   {"kind": "decision", "context": oj_ctx(departs=QD_RESTATE)}, action="update")
qd("an update that carries kind decision and a context with the line is allowed", "allow",
   {"kind": "decision", "context": oj_ctx()}, action="update")
qd("an items set to another artifact is allowed", "allow", qd_item(context=oj_ctx(departs=None)),
   url="https://claude.ai/artifact/other")
qd("a set to another collection is allowed", "allow", qd_item(context=oj_ctx(departs=None)), collection="answers")
add("question departs: a repo with no waiting page allows a decision with no line", "allow", tool="ArtifactData",
    cwd=NOGIT, url=PQ_URL, action="set", collection="items", doc_id=QD_DOC,
    data=qd_item(context=oj_ctx(departs=None)))

# The older rules and the form keep their ids: this check runs after them.
wp_write("question departs: a decision with no Goal and no line is refused as question-form", "deny",
         "question-form", qd_item(context=oj_ctx(goal=None, departs=None)), doc_id=QD_DOC)
wp_write("question departs: a port with no line is refused as port-question", "deny", "port-question",
         qd_item(context=oj_ctx(departs=None, tail=PQ_CTX)), doc_id=QD_DOC)
wp_write("question departs: a widening pick with no line is refused as uniform-pick", "deny", "uniform-pick",
         qd_item(context=oj_ctx(departs=None), options=[UP_WIDE, UP_MATCH], pick="a"), doc_id=QD_DOC)


def qd_replace(name, expected, old, new, field="context"):
    add("question departs: " + name, expected, "question-departs" if expected == "deny" else None,
        tool="ArtifactData", cwd=PQ_REPO, url=PQ_URL, action="str_replace", collection="items", doc_id=QD_DOC,
        field=field, old_str=old, new_str=new)


qd_replace("a str_replace that drops the Departs from line from context is denied", "deny", QD_LINE, "")
qd_replace("a str_replace that drops the line and keeps the form is denied", "deny", oj_ctx(), oj_ctx(departs=None))
qd_replace("a str_replace that swaps the line for another valid line is allowed", "allow", QD_LINE,
           "Departs from: lint/stamp.py:run_stamp — the stamp check moves to the test job")
qd_replace("a str_replace that keeps the line and changes the prose is allowed", "allow", oj_ctx(),
           oj_ctx(tail="The stamp check runs in the test job today."))
qd_replace("a str_replace whose old_str holds no Departs from line is allowed", "allow", OJ_CTX,
           "The stamp check runs in the test job today.")
qd_replace("a str_replace on the title is not judged", "allow", QD_LINE, "", field="title")

add("question departs: a batch with a decision that has no line is denied", "deny", "question-departs",
    tool="ArtifactData", cwd=PQ_REPO, url=PQ_URL, action="batch",
    writes=[{"op": "set", "collection": "items", "doc_id": QD_DOC, "data": qd_item(context=oj_ctx(departs=None))}])
add("question departs: a batch of decisions that each carry a line is allowed", "allow", tool="ArtifactData",
    cwd=PQ_REPO, url=PQ_URL, action="batch",
    writes=[{"op": "set", "collection": "items", "doc_id": QD_DOC, "data": qd_item()},
            {"op": "set", "collection": "items", "doc_id": "departs-second", "data": qd_item(id="departs-second")}])


# --------------------------------------------------------------------------- an item field the page renders
