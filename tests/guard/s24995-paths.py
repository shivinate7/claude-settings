# section 24995
FAMILY = "paths"

add("open: a payload with no command", "allow", tool="Bash", cwd=NOGIT)
add("open: a tool the guard does not handle", "allow", tool="Glob", cwd=NOGIT, pattern="**/*.ts")
add("open: a tool with a path the guard does not handle", "allow", tool="WebFetch", cwd=NOGIT,
    file_path=CFG_SETTINGS)
add("open: unreadable input", "allow", raw="not json at all")
add("open: a payload that is not an object", "allow", raw="[1, 2, 3]")
add("open: a bare number on stdin", "allow", raw="42")
add("open: an empty stdin", "allow", raw="")
add("open: an object with no keys at all", "allow", raw="{}")
add("open: a tool_input that is not an object", "allow", raw='{"tool_name":"Bash","tool_input":3}')


# --------------------------------------------------------------------------- impeccable is review-only
