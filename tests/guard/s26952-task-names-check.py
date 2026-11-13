# section 26952
FAMILY = "task-names-check"
#
# Decision task-names-its-check: a waiting-page task carries a "Why yours:" line naming the check that
# showed no session could do the act. The fixture is a task with a cloud refusal in context and no Why
# yours line. Its steps are plain and it carries a
# `command`, so command-in-item passes it and only this rule judges it. The rule judges only this
# repo's waiting page.

TN_CTX = "The cloud proxy refused the branch deletes (403)."
TN_STEPS = ["Open Terminal", "Paste the command below and run it"]
TN_COMMAND = CMD_BOTH_SHELLS  # the {powershell, mac} command of the 14:47 ruling


def tn_task(**over):
    task = {"id": "stale-branch-deletes", "kind": "task", "status": "open", "title": "Delete the stale branches",
            "context": TN_CTX, "steps": TN_STEPS, "command": TN_COMMAND}
    task.update(over)
    return {k: v for k, v in task.items() if v is not None}


def tn(name, expected, data, action="set", **extra):
    kw = dict(action=action, collection="items", doc_id="stale-branch-deletes", data=data)
    kw.update(extra)
    add("task names its check: " + name, expected, "task-names-check" if expected == "deny" else None,
        tool="ArtifactData", cwd=PQ_REPO, **{"url": PQ_URL, **kw})


tn("a task with steps and no Why yours line is denied", "deny", tn_task())
tn("a Why yours line in context allows the task", "allow", tn_task(context=TN_CTX + "\n" + TN_WHY))
tn("the Why yours line is read in any case, at a line start", "allow",
   tn_task(context=TN_CTX + "\nwhy yours: none could reach the remote"))
tn("a Why yours phrase mid-line does not count", "deny", tn_task(context="Reason. " + TN_WHY))
tn("a task with no context is denied", "deny", tn_task(context=None))
tn("an update that carries kind task and context with no Why yours line is denied", "deny",
   {"kind": "task", "context": TN_CTX}, action="update")
tn("an update that carries kind task, context and a Why yours line is allowed", "allow",
   {"kind": "task", "context": TN_CTX + "\n" + TN_WHY}, action="update")
tn("an update of the status only is allowed", "allow", {"status": "closed"}, action="update")
tn("an update of the rank only is allowed", "allow", {"rank": 3}, action="update")
# The form lines keep this case on the task rule; the question form reads them (OJ_FORM).
tn("a decision is not judged", "allow", tn_task(kind="decision", context=OJ_FORM + "\n" + QD_LINE + "\n" + TN_CTX))
tn("an items set to another artifact is allowed", "allow", tn_task(), url="https://claude.ai/artifact/other")
add("task names its check: a batch with a task that has no Why yours line is denied", "deny", "task-names-check",
    tool="ArtifactData", cwd=PQ_REPO, url=PQ_URL, action="batch",
    writes=[{"op": "set", "collection": "items", "doc_id": "stale-branch-deletes", "data": tn_task()}])
add("task names its check: the refusal says to ask the owner, or hand the task on, and add the line", "deny",
    "task-names-check", carries=("Why yours", "ask the owner"), tool="ArtifactData", cwd=PQ_REPO, url=PQ_URL,
    action="set", collection="items", doc_id="stale-branch-deletes", data=tn_task())
tn("a bare Why yours line with nothing after the colon is denied", "deny",
   tn_task(context=TN_CTX + "\nWhy yours:   "))


def tn_replace(name, expected, field, old, new):
    """One str_replace on a field of the task. The rule judges the text that replaces old_str."""
    add("task names its check: " + name, expected, "task-names-check" if expected == "deny" else None,
        tool="ArtifactData", cwd=PQ_REPO, url=PQ_URL, action="str_replace", collection="items",
        doc_id="stale-branch-deletes", field=field, old_str=old, new_str=new)


tn_replace("a str_replace that drops the Why yours line from context is denied", "deny", "context",
           TN_CTX + "\n" + TN_WHY, TN_CTX)
tn_replace("a str_replace that keeps the Why yours line in context is allowed", "allow", "context",
           TN_CTX + "\n" + TN_WHY, "The cloud proxy refused the branch deletes (403) again.\n" + TN_WHY)
tn_replace("a str_replace on the title is allowed", "allow", "title",
           "Delete the stale branches", "Delete the old branches")
tn_replace("a str_replace whose old_str holds no Why yours line is allowed", "allow", "context",
           TN_CTX, "The cloud proxy refused the branch deletes (403), twice.")
# Rule task-why-cited (decision claims-carry-backing, part (v)). hooks/test_question_form.py judges the rule in-process;
# this case runs the real guard, so a rule the guard does not dispatch would show here as an allow.
add("task why cited: a Why yours line with a capability reason and no cite is denied by the guard", "deny",
    "task-why-cited", tool="ArtifactData", cwd=PQ_REPO, url=PQ_URL, action="set", collection="items",
    doc_id="stale-branch-deletes",
    data=tn_task(context=TN_CTX + "\nWhy yours: the cloud proxy refused the branch deletes (403)."))


# --------------------------------------------------------------------------- a decision states the question form
