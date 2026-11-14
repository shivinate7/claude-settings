# section 13410
# Local tier file (lane local-tier-file, step local-autonomy-equals-cloud). A local session has no cloud remote id, so the
# roadmap-one-writer proof cannot read its tags from the cloud. The launcher's session start writes the session's role to
# <CLAUDE_CONFIG_DIR>/state/session-roles/<session id>.json, {"session", "role", "repo"}, and the guard reads that file for the
# same proof. A file for another session, a role that is not triage, another repo, bad JSON or a session id that fails the id
# shape proves nothing, so the push stays refused. The cases also pin the rule that keeps Claude out of that folder: a write,
# edit, delete or shell redirect into it is refused, while a read of it, or a write beside it, passes.
# The controls are green on the old code too: the old guard refuses every local push to roadmap and reads no role file.
_LT_PREV_FAMILY = FAMILY
FAMILY = "merge"

LT_SID = "session_LTTRIAGE01"     # the session the files below are written for
LT_OTHER = "session_LTOTHER01"    # another session's id
LT_NEW = "session_LTCLEAR02"      # a /clear gives a new id; no file is written for it
LT_REPO = "o/r"                   # PUSHSSH's origin is git@github.com:o/r.git


def lt_role(session, role, repo=LT_REPO):
    return json.dumps({"session": session, "role": role, "repo": repo})


def lt_config(name, files):
    """A config directory for one case: its state/session-roles folder holds `files` ({file name: text}). Built on first use."""
    path = os.path.join(ROOT, "lt-cfg-" + name)

    def build():
        folder = os.path.join(path, "state", "session-roles")
        os.makedirs(folder, exist_ok=True)
        for fname, text in files.items():
            with open(os.path.join(folder, fname), "w", encoding="utf-8") as handle:
                handle.write(text)
    lazy_fixture([path], build)
    return path


LT_TRIAGE = lt_config("triage", {LT_SID + ".json": lt_role(LT_SID, "triage")})
LT_EMPTY = lt_config("empty", {})
LT_LANE = lt_config("lane", {LT_SID + ".json": lt_role(LT_SID, "lane")})
LT_COORD = lt_config("coord", {LT_SID + ".json": lt_role(LT_SID, "coordinator")})
LT_BATCH = lt_config("batch", {LT_SID + ".json": lt_role(LT_SID, "batch-runner")})
LT_OTHERID = lt_config("otherid", {LT_SID + ".json": lt_role(LT_OTHER, "triage")})
LT_BADJSON = lt_config("badjson", {LT_SID + ".json": '{"session": '})
LT_WRONGREPO = lt_config("wrongrepo", {LT_SID + ".json": lt_role(LT_SID, "triage", repo="x/y")})
LT_BADSID = lt_config("badsid", {"ltbad.json": lt_role("ltbad", "triage")})
LT_CLEAR = lt_config("clear", {LT_SID + ".json": lt_role(LT_SID, "triage")})
LT_OTHERENV = lt_config("otherenv", {LT_OTHER + ".json": lt_role(LT_OTHER, "triage")})
LT_ROLEFILE = os.path.join(LT_TRIAGE, "state", "session-roles", LT_SID + ".json")
LT_FOLDER = os.path.join(LT_TRIAGE, "state", "session-roles")
LT_PUSH = VCS + " push origin roadmap"
LT_LACKS = ("origin roadmap", "HEAD:roadmap")


# RED. Cause: the old guard reads no role file for a local session, so a local triage push to roadmap is refused.
# The hook's session_id names the file. The Bash env CLAUDE_CODE_SESSION_ID is set to the same id, as in a usual local session.
add("local-tier: a triage file for this session and repo lets a local push to roadmap through", "allow",
    tool="Bash", command=LT_PUSH, cwd=PUSHSSH, session=LT_SID, env={"CLAUDE_CODE_SESSION_ID": LT_SID},
    config=LT_TRIAGE, silent=True, windows=True)

# CONTROL, green on the old code: with no hook session_id, no file is read, so a guess about who is asking reads nothing.
add("local-tier: a triage file is not read when neither the hook id nor the env id is set", "deny", rule=RECORD_RULE,
    tool="Bash", command=LT_PUSH, cwd=PUSHSSH, config=LT_TRIAGE, env={"CLAUDE_CODE_SESSION_ID": None}, lacks=LT_LACKS,
    windows=True)
# RED on 34345f092. Cause: the guard reads the role file only when the hook's session_id equals the env id, so this push is refused.
add("local-tier: a triage file for the hook's session id lets a roadmap push through when the env id differs", "allow",
    tool="Bash", command=LT_PUSH, cwd=PUSHSSH, session=LT_SID, env={"CLAUDE_CODE_SESSION_ID": LT_OTHER},
    config=LT_TRIAGE, silent=True, windows=True)
# CONTROL, green on 34345f092: a file named for the env id alone is not this session's, so the push stays refused.
add("local-tier: a triage file for the env id alone does not prove a roadmap push for the hook's session", "deny", rule=RECORD_RULE,
    tool="Bash", command=LT_PUSH, cwd=PUSHSSH, session=LT_SID, env={"CLAUDE_CODE_SESSION_ID": LT_OTHER},
    config=LT_OTHERENV, lacks=LT_LACKS, windows=True)

# CONTROLS, green on the old code. Each is a refusal the old guard already gives, which the build must keep.
add("local-tier: a local push to roadmap with no role file is refused", "deny", rule=RECORD_RULE,
    tool="Bash", command=LT_PUSH, cwd=PUSHSSH, session=LT_SID, config=LT_EMPTY, lacks=LT_LACKS, windows=True)
add("local-tier: a lane's role file does not prove triage, the push is refused", "deny", rule=RECORD_RULE,
    tool="Bash", command=LT_PUSH, cwd=PUSHSSH, session=LT_SID, config=LT_LANE, lacks=LT_LACKS)
add("local-tier: a coordinator's role file does not prove triage, the push is refused", "deny", rule=RECORD_RULE,
    tool="Bash", command=LT_PUSH, cwd=PUSHSSH, session=LT_SID, config=LT_COORD, lacks=LT_LACKS)
add("local-tier: a batch runner's role file does not prove triage, the push is refused", "deny", rule=RECORD_RULE,
    tool="Bash", command=LT_PUSH, cwd=PUSHSSH, session=LT_SID, config=LT_BATCH, lacks=LT_LACKS)
add("local-tier: a role file that names another session is refused, the push stays refused", "deny", rule=RECORD_RULE,
    tool="Bash", command=LT_PUSH, cwd=PUSHSSH, session=LT_SID, config=LT_OTHERID, lacks=LT_LACKS)
add("local-tier: a role file that is bad JSON is refused, the push stays refused", "deny", rule=RECORD_RULE,
    tool="Bash", command=LT_PUSH, cwd=PUSHSSH, session=LT_SID, config=LT_BADJSON, lacks=LT_LACKS)
add("local-tier: a triage file for another repo is refused, the push stays refused", "deny", rule=RECORD_RULE,
    tool="Bash", command=LT_PUSH, cwd=PUSHSSH, session=LT_SID, config=LT_WRONGREPO, lacks=LT_LACKS)
add("local-tier: a session id that fails the id shape is refused, even with a file of that id", "deny", rule=RECORD_RULE,
    tool="Bash", command=LT_PUSH, cwd=PUSHSSH, session="ltbad", config=LT_BADSID, lacks=LT_LACKS)
add("local-tier: a /clear's new session id gets no stale role from the old id's file", "deny", rule=RECORD_RULE,
    tool="Bash", command=LT_PUSH, cwd=PUSHSSH, session=LT_NEW, config=LT_CLEAR, lacks=LT_LACKS)

# RED. Cause: no guard rule covers the role folder, so Claude's own write into it is allowed.
add("local-tier: a Write of a role file by Claude is refused", "deny", tool="Write", cwd=PUSHSSH,
    session=LT_SID, config=LT_TRIAGE, file_path=LT_ROLEFILE, content=lt_role(LT_SID, "triage"))
add("local-tier: an Edit of a role file by Claude is refused", "deny", tool="Edit", cwd=PUSHSSH,
    session=LT_SID, config=LT_TRIAGE, file_path=LT_ROLEFILE, old_string="triage", new_string="coordinator")
add("local-tier: a MultiEdit of a role file by Claude is refused", "deny", tool="MultiEdit", cwd=PUSHSSH,
    session=LT_SID, config=LT_TRIAGE, file_path=LT_ROLEFILE,
    edits=[{"old_string": "triage", "new_string": "batch-runner"}])
sh("local-tier: a shell redirect into a role file is refused",
   "echo '" + lt_role(LT_SID, "triage") + "' > " + LT_ROLEFILE, "deny", cwd=PUSHSSH,
   session=LT_SID, config=LT_TRIAGE)
sh("local-tier: a tee into a role file is refused",
   "printf '{}' | tee " + LT_ROLEFILE, "deny", cwd=PUSHSSH, session=LT_SID, config=LT_TRIAGE)
sh("local-tier: a delete of a role file is refused", "rm -f " + LT_ROLEFILE, "deny", cwd=PUSHSSH,
   session=LT_SID, config=LT_TRIAGE)
add("local-tier: a PowerShell write of a role file is refused", "deny", tool="PowerShell", cwd=PUSHSSH,
    session=LT_SID, config=LT_TRIAGE, windows=True,
    command="Set-Content -Path '" + LT_ROLEFILE + "' -Value '{}'")

# CONTROLS, green on the old code: reads of the folder pass. A path inside a string, after a comment, or in text with a
# lone quote is not a write into the folder. The old configuration rule already refuses every write under the config
# directory, so a write beside the folder there is refused on the old code too; no control is kept for it.
add("local-tier: a Read of a role file passes", "allow", tool="Read", cwd=PUSHSSH, session=LT_SID,
    config=LT_TRIAGE, file_path=LT_ROLEFILE, silent=True)
sh("local-tier: a cat of a role file passes", "cat " + LT_ROLEFILE, "allow", cwd=PUSHSSH,
   session=LT_SID, config=LT_TRIAGE, silent=True)
sh("local-tier: an ls of the role folder passes", "ls " + LT_FOLDER, "allow", cwd=PUSHSSH,
   session=LT_SID, config=LT_TRIAGE, silent=True)
sh("local-tier: the folder's path inside an echo string passes",
   'echo "state/session-roles is the folder"', "allow", cwd=PUSHSSH, session=LT_SID, config=LT_TRIAGE, silent=True)
sh("local-tier: the folder's path after a comment passes",
   "echo ok # state/session-roles/x.json is written later", "allow", cwd=PUSHSSH, session=LT_SID,
   config=LT_TRIAGE, silent=True)
sh("local-tier: the folder's path in text with a lone quote passes",
   "echo \"it's state/session-roles\"", "allow", cwd=PUSHSSH, session=LT_SID, config=LT_TRIAGE, silent=True)
# A local `merge <pr> --confirm` is judged by the session's OWN role file, and by CS_SESSION_ROLE when the launcher started it.
# An own file must name batch-runner and the merge's repo (a null repo refuses). No own file is today's behaviour, even with other
# sessions' files in the folder, and the same when the session has no id. Rule (c): CS_SESSION_ROLE set with no own file, or an own
# file whose role differs, refuses: the hook failed to bind the session. The rule (c) cases below pin it.
LT_HEAD = "1234567890abcdef1234567890abcdef12345678"  # a lowercase full sha, as the merge tool's parser takes it
LT_CONFIRM = "~/.claude/bin/merge 7 --confirm --head " + LT_HEAD
LT_LINGER = lt_config("linger", {LT_OTHER + ".json": lt_role(LT_OTHER, "triage")})
LT_BATCH_WRONG = lt_config("batchwrong", {LT_SID + ".json": lt_role(LT_SID, "batch-runner", repo="x/y")})
LT_BATCH_NULL = lt_config("batchnull", {LT_SID + ".json": json.dumps({"session": LT_SID, "role": "batch-runner", "repo": None})})
LT_IDS = {"CLAUDE_CODE_SESSION_ID": LT_SID}

# CONTROLS, green on the builder's head: an own triage or coordinator file refuses, an own batch-runner file for this repo passes.
add("local-tier: a local confirm with an own triage file is refused", "deny", rule="merge-confirm-repo",
    tool="Bash", command=LT_CONFIRM, cwd=PUSHSSH, session=LT_SID, env=LT_IDS, config=LT_TRIAGE)
add("local-tier: a local confirm with an own coordinator file is refused", "deny", rule="merge-confirm-repo",
    tool="Bash", command=LT_CONFIRM, cwd=PUSHSSH, session=LT_SID, env=LT_IDS, config=LT_COORD)
add("local-tier: a local confirm with an own batch-runner file for this repo is allowed", "allow",
    tool="Bash", command=LT_CONFIRM, cwd=PUSHSSH, session=LT_SID, env=LT_IDS, config=LT_BATCH, silent=True)
add("local-tier: an own batch-runner file that names another repo refuses the confirm", "deny", rule="merge-confirm-repo",
    tool="Bash", command=LT_CONFIRM, cwd=PUSHSSH, session=LT_SID, env=LT_IDS, config=LT_BATCH_WRONG)
add("local-tier: an own batch-runner file with a null repo refuses the confirm", "deny", rule="merge-confirm-repo",
    tool="Bash", command=LT_CONFIRM, cwd=PUSHSSH, session=LT_SID, env=LT_IDS, config=LT_BATCH_NULL)

# RED on the builder's head: no own file, so the confirm is today's behaviour and is allowed, though another session's file lingers.
add("local-tier: another session's lingering file does not refuse a session with no own file", "allow",
    tool="Bash", command=LT_CONFIRM, cwd=PUSHSSH, session=LT_SID, env=LT_IDS, config=LT_LINGER, silent=True)
# RED: the session has no id (hook id and env id both absent), so it has no own file, and the confirm is allowed.
add("local-tier: a session with no id and a triage file in the folder is allowed to confirm as today", "allow",
    tool="Bash", command=LT_CONFIRM, cwd=PUSHSSH, session=None, env={"CLAUDE_CODE_SESSION_ID": None},
    config=LT_TRIAGE, silent=True)
# RED: the hook id and the env id are unequal, so the session has no id and no own file; the file is named for the env id.
add("local-tier: unequal ids leave the session with no own file, so its confirm is allowed", "allow",
    tool="Bash", command=LT_CONFIRM, cwd=PUSHSSH, session=LT_SID, env={"CLAUDE_CODE_SESSION_ID": LT_OTHER},
    config=LT_OTHERENV, silent=True)

# CONTROL, green on 34345f092: the hook's session_id names the own file, so an env id that differs does not lift the refusal.
add("local-tier: a triage file for the hook's session id refuses a confirm when the env id differs", "deny", rule="merge-confirm-repo",
    tool="Bash", command=LT_CONFIRM, cwd=PUSHSSH, session=LT_SID, env={"CLAUDE_CODE_SESSION_ID": LT_OTHER}, config=LT_TRIAGE)
# CONTROL, green on 34345f092, rule (c): CS_SESSION_ROLE is set and the session has no id at all, so the hook could not bind it: refuse.
add("local-tier: a launcher session with CS_SESSION_ROLE and no id at all refuses the confirm", "deny", rule="merge-confirm-repo",
    tool="Bash", command=LT_CONFIRM, cwd=PUSHSSH, session=None,
    env={"CLAUDE_CODE_SESSION_ID": None, "CS_SESSION_ROLE": "batch-runner"}, config=LT_EMPTY)
# RED, rule (c): the launcher set CS_SESSION_ROLE, and no own file exists, so the hook failed to bind and the confirm refuses.
add("local-tier: a launcher session with CS_SESSION_ROLE and no own file refuses the confirm", "deny",
    rule="merge-confirm-repo", tool="Bash", command=LT_CONFIRM, cwd=PUSHSSH, session=LT_SID,
    env={"CLAUDE_CODE_SESSION_ID": LT_SID, "CS_SESSION_ROLE": "batch-runner"}, config=LT_EMPTY)
# RED, rule (c): the launcher set CS_SESSION_ROLE to coordinator, and the own file says batch-runner, so the two differ and it refuses.
add("local-tier: a launcher session whose own file differs from CS_SESSION_ROLE refuses the confirm", "deny",
    rule="merge-confirm-repo", tool="Bash", command=LT_CONFIRM, cwd=PUSHSSH, session=LT_SID,
    env={"CLAUDE_CODE_SESSION_ID": LT_SID, "CS_SESSION_ROLE": "coordinator"}, config=LT_BATCH)
# CONTROL, green on the builder's head: CS_SESSION_ROLE agrees with the own batch-runner file, so the confirm is allowed.
add("local-tier: a launcher session whose own batch-runner file agrees with CS_SESSION_ROLE is allowed", "allow",
    tool="Bash", command=LT_CONFIRM, cwd=PUSHSSH, session=LT_SID,
    env={"CLAUDE_CODE_SESSION_ID": LT_SID, "CS_SESSION_ROLE": "batch-runner"}, config=LT_BATCH, silent=True)

# A session may not claim a role for itself: the owner starts the launcher from his own terminal, never through Claude's tools.
# RED on 47171b260: the guard allows each of these forms, so each stops at the deny the owner's ruling asks for.
for _cmd in (
    "CS_SESSION_ROLE=batch-runner claude -p x",
    "env CS_SESSION_ROLE=triage claude",
    "bash -c \"CS_SESSION_ROLE=triage claude\"",
    "bin/claude-role batch-runner",
    "~/.claude/bin/claude-role triage",
    "bin/claude-role.cmd triage",
):
    add("local-role: a Bash call that starts a child session with a role is denied: " + _cmd, "deny",
        tool="Bash", command=_cmd, cwd=PUSHSSH, session=LT_SID)
add("local-role: a PowerShell call that sets CS_SESSION_ROLE and starts claude is denied", "deny",
    tool="PowerShell", command="$env:CS_SESSION_ROLE='x'; claude", cwd=PUSHSSH, session=LT_SID, windows=True)
# CONTROLS, green on 47171b260: reading the variable, grepping for the launcher's name and reading its file stay allowed.
add("local-role: echo of CS_SESSION_ROLE is allowed", "allow", tool="Bash", command="echo $CS_SESSION_ROLE",
    cwd=PUSHSSH, session=LT_SID, silent=True)
add("local-role: a grep for the launcher's name is allowed", "allow", tool="Bash",
    command="grep -rn claude-role hooks/", cwd=PUSHSSH, session=LT_SID, silent=True)
add("local-role: reading bin/claude-role with cat is allowed", "allow", tool="Bash",
    command="cat bin/claude-role", cwd=PUSHSSH, session=LT_SID, silent=True)

# More forms that claim a role for a child session: a subshell, a command substitution, a brace group, and a PowerShell
# SetEnvironmentVariable. RED on fbb931781, where the guard allows each one.
for _cmd in (
    "(CS_SESSION_ROLE=batch-runner claude -p hi)",
    "echo $(CS_SESSION_ROLE=batch-runner claude -p hi)",
    "{ CS_SESSION_ROLE=triage claude; }",
):
    add("local-role: a Bash call that starts a child session with a role in a group or substitution is denied: " + _cmd, "deny",
        tool="Bash", command=_cmd, cwd=PUSHSSH, session=LT_SID)
add("local-role: a PowerShell call that sets CS_SESSION_ROLE with SetEnvironmentVariable and starts claude is denied", "deny",
    tool="PowerShell", command="[Environment]::SetEnvironmentVariable('CS_SESSION_ROLE', 'batch-runner', 'Process'); claude -p hi",
    cwd=PUSHSSH, session=LT_SID, windows=True)
# CONTROLS, green on fbb931781: text that names the variable or the launcher is not a claim, and neither is a shell that reads or unsets it.
add("local-role: a commit message that quotes CS_SESSION_ROLE and claude-role is allowed", "allow", tool="Bash",
    command="git commit -m \"CS_SESSION_ROLE comes from bin/claude-role\"", cwd=PUSHSSH, session=LT_SID, silent=True)
add("local-role: a heredoc that names CS_SESSION_ROLE is allowed", "allow", tool="Bash",
    command="cat <<'EOF'\nCS_SESSION_ROLE=batch-runner claude -p hi\nEOF", cwd=PUSHSSH, session=LT_SID, silent=True)
add("local-role: a comment that names CS_SESSION_ROLE is allowed", "allow", tool="Bash",
    command="echo ok # it's CS_SESSION_ROLE", cwd=PUSHSSH, session=LT_SID, silent=True)
add("local-role: env | grep CS_SESSION_ROLE is allowed", "allow", tool="Bash",
    command="env | grep CS_SESSION_ROLE", cwd=PUSHSSH, session=LT_SID, silent=True)
add("local-role: env -u CS_SESSION_ROLE is allowed", "allow", tool="Bash",
    command="env -u CS_SESSION_ROLE true", cwd=PUSHSSH, session=LT_SID, silent=True)
add("local-role: unset CS_SESSION_ROLE is allowed", "allow", tool="Bash",
    command="unset CS_SESSION_ROLE", cwd=PUSHSSH, session=LT_SID, silent=True)
add("local-role: python3 -m pytest -k CS_SESSION_ROLE is allowed", "allow", tool="Bash",
    command="python3 -m pytest -k CS_SESSION_ROLE", cwd=PUSHSSH, session=LT_SID, silent=True)
add("local-role: python3 lint/test_claude_role.py is allowed", "allow", tool="Bash",
    command="python3 lint/test_claude_role.py", cwd=PUSHSSH, session=LT_SID, silent=True)
# PowerShell reads of the variable are not judged (guard.py: a read is not judged). RED on fbb931781 for the two that deny today.
for _cmd in (
    "Test-Path Env:CS_SESSION_ROLE",
    "Get-Item Env:CS_SESSION_ROLE",
    "Remove-Item Env:CS_SESSION_ROLE",
):
    add("local-role: a PowerShell read of the launcher's variable is allowed: " + _cmd, "allow",
        tool="PowerShell", command=_cmd, cwd=PUSHSSH, session=LT_SID, silent=True, windows=True)

FAMILY = _LT_PREV_FAMILY
