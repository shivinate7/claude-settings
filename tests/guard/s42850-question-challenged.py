# section 42850
FAMILY = "question-challenged"
#
# Rule question-challenged (owner pick of the refuter-page-against row in the debate model tiers plan: each page
# decision gets a blind refuter's best case against the pick). A page decision with a pick carries a line at a
# line start in `context`: `Against the pick (<model>): <text>`, with <model> sonnet or opus. The line is the case
# a refuter wrote, given only Goal, Problem, Based on, the options and the pick. The guard checks that the line
# is present and well formed. It cannot prove the refuter was blind. The check runs after question-departs, at
# the same ArtifactData call. A closed item, a task, a note, an item with no pick, one with stands: true, a port
# item, an update with no context or no pick, another artifact's page and another collection are not judged. A
# str_replace on context that removes the line, or writes one that is not well formed, is refused. The line sits
# in `context` only. The pick is the `recommended` key, or its old name `pick`; either one makes a decision judged.
#
# The form lines, the Departs from line and OJ_AGAINST come from the sections before this one: the Against the
# pick line has one home beside QD_LINE, and oj_ctx and with_stake both take it from there.

QC_DOC = "challenged-item"
QC_EMPTY = "Against the pick (sonnet):"
QC_PLACE = "Against the pick (sonnet): <the refuter's case>"
QC_GPT = "Against the pick (gpt): the lint job already holds the other format checks."
QC_NO_MODEL = "Against the pick: the lint job already holds the other format checks."
QC_MID = "Why: Against the pick (sonnet): the lint job already holds the other format checks."
QC_OPUS = "Against the pick (opus): the stamp check is one step, and a second job adds a wait."
QC_BULLET = "- **Against the pick (sonnet):** the lint job already holds the other format checks."
QC_PUNCT = "Against the pick (sonnet): don't parse // or /* or # here, the lint job holds the other format checks"
QC_LONG = "Against the pick (sonnet): " + ("the lint job holds the other format checks and a move splits them. " * 20)
QC_WHY = "Why yours: a session on your computer was asked first and none could reach the remote"


def qc_item(**over):
    item = {"id": QC_DOC, "kind": "decision", "status": "open", "title": "Which CI job runs the stamp check?",
            "context": oj_ctx(), "options": OJ_OPTIONS, "pick": "a",
            "why": "The lint job already holds the other format checks."}
    item.update(over)
    return {k: v for k, v in item.items() if v is not None}


def qc(name, expected, item, action="set", **extra):
    # The options carry `shown`, as a session's write does (with_shown), or option-letters-frozen refuses each allow.
    kw = dict(action=action, collection="items", doc_id=QC_DOC, data=with_shown(item))
    kw.update(extra)
    add("question challenged: " + name, expected, "question-challenged" if expected == "deny" else None,
        tool="ArtifactData", cwd=PQ_REPO, **{"url": PQ_URL, **kw})


qc("a decision with the form and a pick, and no Against the pick line, is denied", "deny",
   qc_item(context=oj_ctx(against=None)))
qc("the refusal says to spawn a refuter given the pick, and to write its case in the line", "deny",
   qc_item(context=oj_ctx(against=None)), carries=("Against the pick", "refuter"))
qc("an Against the pick line with no text is denied", "deny", qc_item(context=oj_ctx(against=QC_EMPTY)))
qc("an Against the pick line that is only a placeholder is denied", "deny", qc_item(context=oj_ctx(against=QC_PLACE)))
qc("an Against the pick line with a model word outside sonnet and opus is denied", "deny",
   qc_item(context=oj_ctx(against=QC_GPT)))
qc("an Against the pick line with no model word is denied", "deny", qc_item(context=oj_ctx(against=QC_NO_MODEL)))
qc("an Against the pick phrase mid-line does not count", "deny", qc_item(context=oj_ctx(against=QC_MID)))
qc("an Against the pick line in why, not in context, is denied", "deny",
   qc_item(context=oj_ctx(against=None), why=OJ_AGAINST))
qc("an Against the pick line in an option, not in context, is denied", "deny",
   qc_item(context=oj_ctx(against=None), options=[dict(OJ_OPTIONS[0], how=OJ_AGAINST), OJ_OPTIONS[1]]))
qc("a decision with no kind and a pick, and no Against the pick line, is denied", "deny",
   qc_item(kind=None, context=oj_ctx(against=None)))
qc("a sonnet line is allowed", "allow", qc_item())
qc("an opus line is allowed", "allow", qc_item(context=oj_ctx(against=QC_OPUS)))
qc("a bullet and bold label on the line is allowed", "allow", qc_item(context=oj_ctx(against=QC_BULLET)))
qc("comment openers and an apostrophe in the text are plain text", "allow",
   qc_item(context=oj_ctx(against=QC_PUNCT)))
qc("a line of full size, about 1400 characters, is allowed", "allow", qc_item(context=oj_ctx(against=QC_LONG)))

qc("a closed decision with no Against the pick line is allowed", "allow",
   qc_item(status="closed", context=oj_ctx(against=None)))
qc("a task with a Why yours line and no Against the pick line is allowed", "allow",
   {"id": QC_DOC, "kind": "task", "status": "open", "title": "Merge the batch", "steps": ["Open Terminal"],
    "context": QC_WHY})
qc("a note with no Against the pick line is allowed", "allow", qc_item(kind="note", context=oj_ctx(against=None)))
qc("a decision with no pick is allowed", "allow", qc_item(pick=None, context=oj_ctx(against=None)))
qc("a stood pick with no Against the pick line is allowed", "allow",
   qc_item(stands=True, context=oj_ctx(against=None)))
qc("a port item with no Against the pick line is allowed", "allow",
   qc_item(port=True, context=oj_ctx(against=None)))
qc("an update that carries kind decision, a pick and a context with no line is denied", "deny",
   {"kind": "decision", "pick": "a", "context": oj_ctx(against=None)}, action="update")
qc("an update that carries kind decision, a pick and a context with the line is allowed", "allow",
   {"kind": "decision", "pick": "a", "context": oj_ctx()}, action="update")
qc("an update that carries kind decision and a pick, with no context, is allowed", "allow",
   {"kind": "decision", "pick": "a"}, action="update")
qc("an update that carries kind decision and a context, with no pick, is allowed", "allow",
   {"kind": "decision", "context": oj_ctx(against=None)}, action="update")
qc("an update that carries a pick and a context, with no kind, is allowed", "allow",
   {"pick": "a", "context": oj_ctx(against=None)}, action="update")
# A decision names its pick in `recommended` now, and `pick` is its old name. Each case below holds for `recommended`.
qc("a decision with a recommended key and no Against the pick line is denied", "deny",
   qc_item(pick=None, recommended="a", context=oj_ctx(against=None)))
qc("a decision with a recommended key and a sonnet line is allowed", "allow", qc_item(pick=None, recommended="a"))
qc("an update that carries kind decision, a recommended key and a context with no line is denied", "deny",
   {"kind": "decision", "recommended": "a", "context": oj_ctx(against=None)}, action="update")
qc("an update that carries kind decision, a recommended key and a context with the line is allowed", "allow",
   {"kind": "decision", "recommended": "a", "context": oj_ctx()}, action="update")
qc("an update that carries kind decision and a recommended key, with no context, is allowed", "allow",
   {"kind": "decision", "recommended": "a"}, action="update")
qc("a recommended key with stands true and no Against the pick line is allowed", "allow",
   qc_item(pick=None, recommended="a", stands=True, context=oj_ctx(against=None)))
qc("a recommended key on a port item with no Against the pick line is allowed", "allow",
   qc_item(pick=None, recommended="a", port=True, context=oj_ctx(against=None)))
qc("a decision with a recommended list of two keys and no Against the pick line is denied", "deny",
   qc_item(pick=None, recommended=["a", "b"], context=oj_ctx(against=None)))
qc("a decision with a recommended list of two keys and a sonnet line is allowed", "allow",
   qc_item(pick=None, recommended=["a", "b"]))
qc("an item set to another artifact is allowed", "allow", qc_item(context=oj_ctx(against=None)),
   url="https://claude.ai/artifact/other")
qc("a set to another collection is allowed", "allow", qc_item(context=oj_ctx(against=None)), collection="answers")
add("question challenged: a repo with no waiting page allows a decision with no line", "allow", tool="ArtifactData",
    cwd=NOGIT, url=PQ_URL, action="set", collection="items", doc_id=QC_DOC,
    data=qc_item(context=oj_ctx(against=None)))

# The older rules keep their ids: this check runs after them.
wp_write("question challenged: a decision with no Departs from line and no Against line is refused as question-departs",
         "deny", "question-departs", qc_item(context=oj_ctx(departs=None, against=None)), doc_id=QC_DOC)
wp_write("question challenged: a decision with no Goal and no Against line is refused as question-form", "deny",
         "question-form", qc_item(context=oj_ctx(goal=None, against=None)), doc_id=QC_DOC)


def qc_replace(name, expected, old, new, field="context"):
    add("question challenged: " + name, expected, "question-challenged" if expected == "deny" else None,
        tool="ArtifactData", cwd=PQ_REPO, url=PQ_URL, action="str_replace", collection="items", doc_id=QC_DOC,
        field=field, old_str=old, new_str=new)


qc_replace("a str_replace that drops the Against the pick line from context is denied", "deny", OJ_AGAINST, "")
qc_replace("a str_replace that leaves an empty Against the pick line is denied", "deny", OJ_AGAINST, QC_EMPTY)
qc_replace("a str_replace that swaps the line for one with a model word outside the set is denied", "deny",
           OJ_AGAINST, QC_GPT)
qc_replace("a str_replace that swaps the line for another well formed line is allowed", "allow", OJ_AGAINST, QC_OPUS)
qc_replace("a str_replace whose old_str holds no Against the pick line is allowed", "allow",
           "The stamp check runs in the lint job today.", "The stamp check runs in the test job today.")
qc_replace("a str_replace on the title is not judged", "allow", OJ_AGAINST, "", field="title")

add("question challenged: a batch with a decision that has no Against the pick line is denied", "deny",
    "question-challenged", tool="ArtifactData", cwd=PQ_REPO, url=PQ_URL, action="batch",
    writes=[{"op": "set", "collection": "items", "doc_id": QC_DOC,
             "data": with_shown(qc_item(context=oj_ctx(against=None)))}])
add("question challenged: a batch of decisions that each carry the line is allowed", "allow", tool="ArtifactData",
    cwd=PQ_REPO, url=PQ_URL, action="batch",
    writes=[{"op": "set", "collection": "items", "doc_id": QC_DOC, "data": with_shown(qc_item())},
            {"op": "set", "collection": "items", "doc_id": "challenged-second",
             "data": with_shown(qc_item(id="challenged-second"))}])

# A str_replace that empties the text of the line, and placeholder text that reads as a word: none, TBD,
# todo, n/a, an ellipsis and a lone em dash. Real text that holds one of those words is not a placeholder.
QC_PLACEHOLDER_TEXTS = ("none", "TBD", "todo", "n/a", "...", "—")

qc_replace("a str_replace that leaves the Against the pick text empty, after a space, is denied", "deny",
           OJ_AGAINST, "Against the pick (sonnet): ")
qc_replace("a str_replace that swaps the line for a lone placeholder word is denied", "deny",
           OJ_AGAINST, "Against the pick (sonnet): TBD")
for _text in QC_PLACEHOLDER_TEXTS:
    qc("an Against the pick text that is only %s is denied" % _text, "deny",
       qc_item(context=oj_ctx(against="Against the pick (sonnet): " + _text)))
qc("an Against the pick text that starts with none, and says more, is allowed", "allow",
   qc_item(context=oj_ctx(against="Against the pick (sonnet): none of the options keep the lint gate")))
