# section 26700
FAMILY = "task-options"
#
# Rule task-options (decision question-form, rule task-options), built against items 626 and 661, which held the
# paste prompt in an option's `how` on a task. The page draws a decision's options and never a task's, so a page
# task with a non-empty `options` list is refused, and the refusal names the fix: kind decision, or the prompt in
# the item's `command` field. A decision with options passes. The write is judged through question_form.item_hit,
# and judge() refuses on the rule's name.

TO_DOC = "task-options-page"
TO_HOW = "Paste the prompt from the command field into PowerShell."
TO_OPTIONS = [
    {"key": "a", "label": "Paste the prompt", "how": TO_HOW, "gain": "g", "lose": "l"},
    {"key": "b", "label": "Hold it", "gain": "g", "lose": "l"},
]
TO_COMMAND = {"powershell": "Get-Date", "mac": "date"}


def to_task(**over):
    """A page task with one step and the Why yours line, so only the options rule judges it (task-names-check reads
    that line, and command-in-item finds no file in the step)."""
    task = {"id": TO_DOC, "kind": "task", "status": "open", "title": "Open the shell", "steps": ["Open PowerShell"],
            "context": TN_WHY}
    task.update(over)
    return {k: v for k, v in task.items() if v is not None}


def to(name, expected, item, action="set", doc_id=TO_DOC, **extra):
    wp_write("task options: " + name, expected, "task-options", item, action=action, doc_id=doc_id, **extra)


to("a task with options that carry how is denied", "deny", to_task(options=TO_OPTIONS))
to("a task with options and a command is denied, since the page never draws the options", "deny",
   to_task(options=TO_OPTIONS, command=TO_COMMAND))
to("the refusal names both fixes: kind decision, and the command field", "deny", to_task(options=TO_OPTIONS),
   carries=("kind `decision`", "`command`"))
to("an update that writes kind task and options is denied", "deny", {"kind": "task", "options": TO_OPTIONS},
   action="update")
to("a decision with options is allowed", "allow", up_item(pick="b"), doc_id="banchi-titles")
