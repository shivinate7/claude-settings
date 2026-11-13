# section 29483
FAMILY = "workflow-args"
FAMILIES["workflow-args"] = "a Workflow call whose args is, or holds as an array or object value, a placeholder (an all-caps word with an underscore, or __X__) is refused, naming it and the fix; an absent, empty or real args passes, and so does a short all-caps word or a sentence with an env var name"
WORKFLOW_ARGS_RULE = "workflow-args-shape-check"
WORKFLOW_ARGS_FIX = ("replace", "real value", "fill in")
WORKFLOW_ARGS_SCRIPT = _step_flow("'Check the named files.'", "agentType: 'reviewer', model: 'sonnet'")
add("workflow-args: a placeholder string in args is refused", "deny", WORKFLOW_ARGS_RULE,
    tool="Workflow", script=WORKFLOW_ARGS_SCRIPT, args="FACT_CLOSE_PLACEHOLDER",
    carries=("FACT_CLOSE_PLACEHOLDER", WORKFLOW_ARGS_FIX))
add("workflow-args: a __X__ placeholder string in args is refused", "deny", WORKFLOW_ARGS_RULE,
    tool="Workflow", script=WORKFLOW_ARGS_SCRIPT, args="__FILL__",
    carries=("__FILL__", WORKFLOW_ARGS_FIX))
add("workflow-args: a __X__ placeholder last in an args array is refused", "deny", WORKFLOW_ARGS_RULE,
    tool="Workflow", script=WORKFLOW_ARGS_SCRIPT, args=["a.ts", "__FILL__"],
    carries=("__FILL__", WORKFLOW_ARGS_FIX))
add("workflow-args: a __X__ placeholder first in an args array is refused", "deny", WORKFLOW_ARGS_RULE,
    tool="Workflow", script=WORKFLOW_ARGS_SCRIPT, args=["__FILL__", "a.ts"],
    carries=("__FILL__", WORKFLOW_ARGS_FIX))
add("workflow-args: a caps placeholder as an args object value is refused", "deny", WORKFLOW_ARGS_RULE,
    tool="Workflow", script=WORKFLOW_ARGS_SCRIPT, args={"pr": "PR_NUMBER"},
    carries=("PR_NUMBER", WORKFLOW_ARGS_FIX))
add("workflow-args: a Workflow call with no args is allowed", "allow",
    tool="Workflow", script=WORKFLOW_ARGS_SCRIPT)
add("workflow-args: a file-list args array is allowed", "allow",
    tool="Workflow", script=WORKFLOW_ARGS_SCRIPT, args=["hooks/guard.py"])
add("workflow-args: a sentence args string is allowed", "allow",
    tool="Workflow", script=WORKFLOW_ARGS_SCRIPT, args="Fix the CI red on PR 2560")
add("workflow-args: an args object with a short all-caps word is allowed", "allow",
    tool="Workflow", script=WORKFLOW_ARGS_SCRIPT, args={"mode": "OK"})
add("workflow-args: a sentence that names an env var is allowed", "allow",
    tool="Workflow", script=WORKFLOW_ARGS_SCRIPT, args="MAILBOX_REPO is off")
add("workflow-args: a dunder inside a longer path is allowed", "allow",
    tool="Workflow", script=WORKFLOW_ARGS_SCRIPT, args=["hooks/__init__.py"])
add("workflow-args: an empty args array is allowed", "allow",
    tool="Workflow", script=WORKFLOW_ARGS_SCRIPT, args=[])
add("workflow-args: an empty args object is allowed", "allow",
    tool="Workflow", script=WORKFLOW_ARGS_SCRIPT, args={})
add("workflow-args: an empty args string is allowed", "allow",
    tool="Workflow", script=WORKFLOW_ARGS_SCRIPT, args="")

# ---- An agent's outward remote tools. An agent's call to a claude-code-remote tool that acts on another
# session, a trigger or a repo is refused. No agent role needs the server, and a general-purpose agent without an
# agent file holds it (measured). The payload's agent_id marks the agent (AGENT_ID, hooks/guard.py).
# The session's own call (no agent_id), an agent_type with no agent_id, and the read tools keep today's verdict.
# The payload is built whole, not through add()'s keywords: create_trigger's input is `name`, which add() takes.
