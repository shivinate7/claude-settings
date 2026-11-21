# section 13411
# Rule self-role-claim, the resume form (decision session-tiers). A role-less session that resumes or continues a session whose
# kept role file says a role starts a child that inherits that role: the child's SessionStart hook keeps the file on a resume
# (session_role.KEEP_SOURCES), so the child reads the role back. The guard refuses the start as it refuses the env claim in
# section 13410: a `claude` call that resumes a named session, or continues the newest one, is denied when the session it
# targets holds a role file. A value that names no session, a title or a bare `-c`, is judged by the role transcripts in the
# own folder. A title of the id shape (SESSION_ID_RE, 8 to 200 characters) must not pass as an id with no file: the title cases
# are there to catch a guard that reads such a title as an id, finds no file of that name, and allows.
# The controls are green on the old code too: a resume of a session with no kept file, a resume of a named session that holds
# none, a title or `-c` in a folder with no role transcript, text that names the command.
_RS_PREV_FAMILY = FAMILY
FAMILY = "merge"

RS_PROJECTS = os.path.join(ROOT, "rs-projects")  # the transcript folder that `claude -c` reads its target from
RS_NEWEST = os.path.join(RS_PROJECTS, LT_SID + ".jsonl")  # the target of `claude -c`: the most recent transcript here
RS_OWN = os.path.join(RS_PROJECTS, LT_OTHER + ".jsonl")  # the role-less session's own transcript, older than the target's
RS_BARE_PROJECTS = os.path.join(ROOT, "rs-bare-projects")  # a transcript folder with no role transcript in it
RS_BARE_OWN = os.path.join(RS_BARE_PROJECTS, LT_OTHER + ".jsonl")  # the role-less session's own transcript there
RS_TITLES = ("--resume batch-runner", "-r triage-session", "--resume roadmap-triage")  # titles of the id shape, no role file of that name


def build_rs_projects():
    os.makedirs(RS_PROJECTS, exist_ok=True)
    for path, mtime in ((RS_OWN, 1800000000), (RS_NEWEST, 1800003600)):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{}\n")
        os.utime(path, (mtime, mtime))
    os.makedirs(RS_BARE_PROJECTS, exist_ok=True)
    with open(RS_BARE_OWN, "w", encoding="utf-8") as handle:
        handle.write("{}\n")


lazy_fixture([RS_NEWEST, RS_OWN, RS_BARE_OWN], build_rs_projects)

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

# A title of the id shape must not be read as a session id. That read finds no file, so the guard allows and the folder
# scan never runs. No role file has the title's name, and the own folder holds a role transcript, so each must be denied.
for _title in RS_TITLES:
    for _config, _role in RS_CONFIGS:
        add("local-role: a role-less session that runs `claude %s` is denied when the own folder holds a %s role transcript" % (_title, _role),
            "deny", rule="self-role-claim", tool="Bash", command="claude " + _title, cwd=PUSHSSH, session=LT_OTHER, config=_config,
            transcript=RS_OWN, env=RS_NOENV)

# The same title through the two other shapes the guard reads: a nested `bash -c`, and PowerShell's Start-Process. Each must deny it, for the reason above.
add("local-role: a role-less session that runs `bash -c 'claude --resume roadmap-triage'` is denied when the own folder holds a triage role transcript",
    "deny", rule="self-role-claim", tool="Bash", command="bash -c 'claude --resume roadmap-triage'", cwd=PUSHSSH, session=LT_OTHER,
    config=LT_TRIAGE, transcript=RS_OWN, env=RS_NOENV)
add("local-role: a role-less session that runs `Start-Process claude '--resume roadmap-triage'` is denied by the resume clause when the own folder holds a triage role transcript",
    "deny", rule="self-role-claim", tool="PowerShell", command="Start-Process claude '--resume roadmap-triage'", cwd=PUSHSSH,
    session=LT_OTHER, config=LT_TRIAGE, transcript=RS_OWN, env=RS_NOENV)

# CONTROLS, green on the old code: no kept file for the session the call targets, so nothing is inherited.
add("local-role: a role-less session that resumes a session with no kept role file is allowed", "allow", tool="Bash",
    command="claude --resume " + LT_SID, cwd=PUSHSSH, session=LT_OTHER, config=LT_EMPTY, env=RS_NOENV, silent=True)
add("local-role: a role-less session that continues the newest session with no kept role file is allowed", "allow", tool="Bash",
    command="claude -c", cwd=PUSHSSH, session=LT_OTHER, config=LT_EMPTY, transcript=RS_OWN, env=RS_NOENV, silent=True)
add("local-role: a role-less session that resumes a named session with no kept file of its own is allowed", "allow", tool="Bash",
    command="claude --resume " + LT_OTHER, cwd=PUSHSSH, session=LT_OTHER, config=LT_TRIAGE, env=RS_NOENV, silent=True)

# CONTROLS, green on the old code: the same titles, with no role transcript in the own folder, are allowed.
for _title in RS_TITLES:
    add("local-role: a role-less session that runs `claude %s` is allowed when the own folder holds no role transcript" % _title, "allow",
        tool="Bash", command="claude " + _title, cwd=PUSHSSH, session=LT_OTHER, config=LT_TRIAGE, transcript=RS_BARE_OWN,
        env=RS_NOENV, silent=True)
add("local-role: a role-less session that runs `claude --resume roadmap-triage` is allowed when no role file exists", "allow",
    tool="Bash", command="claude --resume roadmap-triage", cwd=PUSHSSH, session=LT_OTHER, config=LT_EMPTY, transcript=RS_OWN,
    env=RS_NOENV, silent=True)

# CONTROLS, green on the old code: the folder scan allows when no role transcript sits in the own folder, for a bare `-c`,
# a nested `bash -c 'claude -c'` and a named id that keeps no role file, even with a role transcript beside it.
add("local-role: a role-less session that continues the newest session is allowed when the own folder holds no role transcript", "allow",
    tool="Bash", command="claude -c", cwd=PUSHSSH, session=LT_OTHER, config=LT_TRIAGE, transcript=RS_BARE_OWN, env=RS_NOENV, silent=True)
add("local-role: a role-less session that runs `bash -c 'claude -c'` is allowed when the own folder holds no role transcript", "allow",
    tool="Bash", command="bash -c 'claude -c'", cwd=PUSHSSH, session=LT_OTHER, config=LT_TRIAGE, transcript=RS_BARE_OWN, env=RS_NOENV,
    silent=True)
add("local-role: a role-less session that runs `bash -c 'claude -c'` is denied when the own folder holds a triage role transcript", "deny",
    rule="self-role-claim", tool="Bash", command="bash -c 'claude -c'", cwd=PUSHSSH, session=LT_OTHER, config=LT_TRIAGE, transcript=RS_OWN,
    env=RS_NOENV)
add("local-role: a role-less session that runs `claude --resume=%s` is allowed when that session keeps no role file" % LT_OTHER, "allow",
    tool="Bash", command="claude --resume=" + LT_OTHER, cwd=PUSHSSH, session=LT_OTHER, config=LT_TRIAGE, transcript=RS_OWN, env=RS_NOENV,
    silent=True)
add("local-role: a role-less session that runs `claude --resume=%s` is denied when that session keeps a triage role file" % LT_SID, "deny",
    rule="self-role-claim", tool="Bash", command="claude --resume=" + LT_SID, cwd=PUSHSSH, session=LT_OTHER, config=LT_TRIAGE, env=RS_NOENV)

# CONTROL, green on the old code: a Start-Process claude is refused by detached-launch (rule 2b), which runs after the resume clause.
# The case pins that the resume clause does not refuse it when no role transcript sits in the own folder.
add("local-role: a role-less session that runs `Start-Process claude '--resume roadmap-triage'` is refused by detached-launch, not the resume clause, when the own folder holds no role transcript",
    "deny", rule="detached-launch", lacks="self-role-claim", tool="PowerShell", command="Start-Process claude '--resume roadmap-triage'",
    cwd=PUSHSSH, session=LT_OTHER, config=LT_TRIAGE, transcript=RS_BARE_OWN, env=RS_NOENV)

# CONTROLS, green on the old code: text that names the resume form starts no session. The last one is the lone quote in text.
for _cmd in (
    'echo "claude --resume ' + LT_SID + '"',
    "echo ok # claude -c",
    "echo \"it's claude --resume " + LT_SID + "\"",
):
    add("local-role: a role-less session that only names a resume is allowed: " + _cmd, "allow", tool="Bash", command=_cmd,
        cwd=PUSHSSH, session=LT_OTHER, config=LT_TRIAGE, env=RS_NOENV, silent=True)

FAMILY = _RS_PREV_FAMILY
