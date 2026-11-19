# section 13411
# Rule self-role-claim, the resume form (decision session-tiers). A role-less session that resumes or continues a session whose
# kept role file says a role starts a child that inherits that role: the child's SessionStart hook keeps the file on a resume
# (session_role.KEEP_SOURCES), so the child reads the role back. The guard refuses the start as it refuses the env claim in
# section 13410: a `claude` call that resumes a named session, or continues the newest one, is denied when the session it
# targets holds a role file. The guard reads only the launcher variable today, so each deny below is allowed, and each fails.
# The controls are green on the old code too: a resume of a session with no kept file, a resume of a named session that holds
# none, and text that names the command.
_RS_PREV_FAMILY = FAMILY
FAMILY = "merge"

RS_PROJECTS = os.path.join(ROOT, "rs-projects")  # the transcript folder that `claude -c` reads its target from
RS_NEWEST = os.path.join(RS_PROJECTS, LT_SID + ".jsonl")  # the target of `claude -c`: the most recent transcript here
RS_OWN = os.path.join(RS_PROJECTS, LT_OTHER + ".jsonl")  # the role-less session's own transcript, older than the target's


def build_rs_projects():
    os.makedirs(RS_PROJECTS, exist_ok=True)
    for path, mtime in ((RS_OWN, 1800000000), (RS_NEWEST, 1800003600)):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{}\n")
        os.utime(path, (mtime, mtime))


lazy_fixture([RS_NEWEST, RS_OWN], build_rs_projects)

RS_NOENV = {"CS_SESSION_ROLE": None, "CLAUDE_CODE_SESSION_ID": LT_OTHER}  # a role-less session: the launcher variable is unset
RS_FORMS = (
    ("claude --resume " + LT_SID, None),
    ("claude -r " + LT_SID, None),
    ("claude --continue", RS_OWN),
    ("claude -c", RS_OWN),
)
RS_CONFIGS = ((LT_TRIAGE, "triage"), (LT_COORD, "coordinator"), (LT_BATCH, "batch-runner"))

# RED on the old code: the target's kept role file says a role, and the child would inherit it. Each form meets each role.
for _cmd, _transcript in RS_FORMS:
    for _config, _role in RS_CONFIGS:
        add("local-role: a role-less session that runs `%s` is denied when the session it targets keeps a %s role file" % (_cmd, _role),
            "deny", rule="self-role-claim", tool="Bash", command=_cmd, cwd=PUSHSSH, session=LT_OTHER, config=_config,
            transcript=_transcript, env=RS_NOENV)

# CONTROLS, green on the old code: no kept file for the session the call targets, so nothing is inherited.
add("local-role: a role-less session that resumes a session with no kept role file is allowed", "allow", tool="Bash",
    command="claude --resume " + LT_SID, cwd=PUSHSSH, session=LT_OTHER, config=LT_EMPTY, env=RS_NOENV, silent=True)
add("local-role: a role-less session that continues the newest session with no kept role file is allowed", "allow", tool="Bash",
    command="claude -c", cwd=PUSHSSH, session=LT_OTHER, config=LT_EMPTY, transcript=RS_OWN, env=RS_NOENV, silent=True)
add("local-role: a role-less session that resumes a named session with no kept file of its own is allowed", "allow", tool="Bash",
    command="claude --resume " + LT_OTHER, cwd=PUSHSSH, session=LT_OTHER, config=LT_TRIAGE, env=RS_NOENV, silent=True)

# CONTROLS, green on the old code: text that names the resume form starts no session. The last one is the lone quote in text.
for _cmd in (
    'echo "claude --resume ' + LT_SID + '"',
    "echo ok # claude -c",
    "echo \"it's claude --resume " + LT_SID + "\"",
):
    add("local-role: a role-less session that only names a resume is allowed: " + _cmd, "allow", tool="Bash", command=_cmd,
        cwd=PUSHSSH, session=LT_OTHER, config=LT_TRIAGE, env=RS_NOENV, silent=True)

FAMILY = _RS_PREV_FAMILY
