# section 43725
FAMILY = "agent-browser-file-open"
#
# Rule agent-browser-file-open. A call by an agent (a payload with a non-empty agent_id) that opens a file: URL through the
# desktop app's built-in browser is refused. The calls are mcp__Claude_Browser__navigate and mcp__Claude_Browser__preview_start,
# which take the URL in `url`, and mcp__Claude_Browser__browser_batch, whose items named navigate or preview_start are judged by
# their input `url`. The app shows an "Allow Claude to open" card for such a call. Bypass mode does not skip that card, and it has
# no timeout. No one watches a subagent, so one such call stalled for 12 hours. Headless Chrome (Playwright) opens the same file
# with no card, so the refusal names headless Chrome or a localhost URL as the remedy. The scheme is read case-insensitively.
# An owner override lifts the refusal.
# The allows are as load-bearing as the refusals: a false alarm here stops an agent's check of a localhost page.
BROWSER_NAVIGATE = "mcp__Claude_Browser__navigate"
BROWSER_PREVIEW = "mcp__Claude_Browser__preview_start"
BROWSER_BATCH = "mcp__Claude_Browser__browser_batch"
AGENT_BROWSER_RULE = "agent-browser-file-open"
# The refusal's remedy. One of these fragments is enough: a tuple inside `carries` is any-of (see add in hooks/test_guard.py).
REMEDY = (("headless Chrome", "Playwright", "localhost"),)
# The incident's shape, with a placeholder for the owner's home folder: a file: URL inside an agent's .claude worktree.
FILE_URL = ("file:///Users/example/project/.claude/worktrees/agent-af44ec7ffb6db277d/docs/design/scene-state/"
            "scene-state-blind-1.html#c=house&s=sure")


def browser_payload(tool, tool_input, agent_id=AGENT_ID_VALUE):
    """The PreToolUse payload of one desktop-app browser call, as the hook receives it. An agent's payload carries agent_id
    beside tool_name and tool_input. The main session's payload carries none: pass agent_id=None to build that one."""
    body = {"tool_name": tool, "tool_input": tool_input, "cwd": NOGIT}
    if agent_id is not None:
        body["agent_id"] = agent_id
    return json.dumps(body)


def browser_refuse(name, tool, tool_input):
    """A browser call by an agent that the guard refuses. The reason names its rule and the remedy."""
    add("agent-browser-file-open: " + name, "deny", rule=AGENT_BROWSER_RULE, tool=tool,
        raw=browser_payload(tool, tool_input), carries=REMEDY)


def browser_allow(name, tool, tool_input, agent_id=AGENT_ID_VALUE):
    """A browser call the guard lets through silently. This rule refuses none of them."""
    add("agent-browser-file-open: " + name, "allow", tool=tool,
        raw=browser_payload(tool, tool_input, agent_id), silent=True)


# Refused: an agent's file: URL through each tool, with the scheme read in any case. The first is the incident's call.
browser_refuse("navigate to the file: URL of the incident is refused", BROWSER_NAVIGATE, {"url": FILE_URL})
browser_refuse("navigate to FILE:///tmp/x.html, an upper-case scheme, is refused", BROWSER_NAVIGATE,
               {"url": "FILE:///tmp/x.html"})
browser_refuse("preview_start of a file: URL is refused", BROWSER_PREVIEW, {"url": "file:///tmp/x.html"})
# Refused: a batch is judged item by item. A file: navigate in the second item refuses the whole call, and so does a
# preview_start item that names a file: URL.
browser_refuse("browser_batch whose second item navigates to a file: URL is refused", BROWSER_BATCH, {"actions": [
    {"name": "navigate", "input": {"url": "http://localhost:4173/x.html"}},
    {"name": "navigate", "input": {"url": "file:///tmp/x.html"}}]})
browser_refuse("browser_batch whose item is a preview_start of a file: URL is refused", BROWSER_BATCH, {"actions": [
    {"name": "preview_start", "input": {"url": "file:///tmp/x.html"}}]})
# Allowed: the main session carries no agent_id, so the same file: URL opens as before.
browser_allow("the same file: navigate with no agent_id is allowed (the main session)", BROWSER_NAVIGATE,
              {"url": FILE_URL}, agent_id=None)
# Allowed: an empty agent_id is no agent. The rule keys on a non-empty value.
browser_allow("the file: navigate with an empty agent_id is allowed", BROWSER_NAVIGATE, {"url": FILE_URL}, agent_id="")
# Allowed: a localhost page, an https page and the back action. None of them is a file: URL.
browser_allow("an agent's navigate to http://localhost:4173/x.html is allowed", BROWSER_NAVIGATE,
              {"url": "http://localhost:4173/x.html"})
browser_allow("an agent's navigate to https://example.com is allowed", BROWSER_NAVIGATE, {"url": "https://example.com"})
browser_allow("an agent's navigate with url back is allowed", BROWSER_NAVIGATE, {"url": "back"})
# Allowed: a batch of https items, an empty batch, and a preview_start that names a server and gives no url.
browser_allow("an agent's browser_batch of https items only is allowed", BROWSER_BATCH, {"actions": [
    {"name": "navigate", "input": {"url": "https://example.com"}},
    {"name": "navigate", "input": {"url": "https://example.org"}}]})
browser_allow("an agent's browser_batch with no actions is allowed", BROWSER_BATCH, {"actions": []})
browser_allow("an agent's preview_start with name and no url is allowed", BROWSER_PREVIEW, {"name": "web"})
