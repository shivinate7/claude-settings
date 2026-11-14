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
LT_ROLEFILE = os.path.join(LT_TRIAGE, "state", "session-roles", LT_SID + ".json")
LT_FOLDER = os.path.join(LT_TRIAGE, "state", "session-roles")
LT_PUSH = VCS + " push origin roadmap"
LT_LACKS = ("origin roadmap", "HEAD:roadmap")


# RED. Cause: the old guard reads no role file for a local session, so a local triage push to roadmap is refused.
# Both ids are present and equal here (the hook's session_id and the Bash env CLAUDE_CODE_SESSION_ID), the one shape that passes.
add("local-tier: a triage file for this session and repo lets a local push to roadmap through", "allow",
    tool="Bash", command=LT_PUSH, cwd=PUSHSSH, session=LT_SID, env={"CLAUDE_CODE_SESSION_ID": LT_SID},
    config=LT_TRIAGE, silent=True, windows=True)

# CONTROLS, green on the old code: the file is not read unless both ids are present and equal. Absent ids and unequal ids are
# both refused, so the file of this session is never used on a guess about who is asking.
add("local-tier: a triage file is not read when neither the hook id nor the env id is set", "deny", rule=RECORD_RULE,
    tool="Bash", command=LT_PUSH, cwd=PUSHSSH, config=LT_TRIAGE, env={"CLAUDE_CODE_SESSION_ID": None}, lacks=LT_LACKS)
add("local-tier: a triage file is refused when the hook id and the env id differ", "deny", rule=RECORD_RULE,
    tool="Bash", command=LT_PUSH, cwd=PUSHSSH, session=LT_SID, env={"CLAUDE_CODE_SESSION_ID": LT_OTHER},
    config=LT_TRIAGE, lacks=LT_LACKS)

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
# A local `merge <pr> --confirm` is judged by the role the launcher wrote. A triage or coordinator file never confirms; a
# batch-runner file with both ids equal may. RED: the old guard allows every local confirm silently, whatever file is present.
LT_CONFIRM = "~/.claude/bin/merge 7 --confirm --head 1234567"
add("local-tier: a local confirm with a triage file is refused by the guard", "deny", rule=None,
    tool="Bash", command=LT_CONFIRM, cwd=PUSHSSH, session=LT_SID, env={"CLAUDE_CODE_SESSION_ID": LT_SID}, config=LT_TRIAGE)
add("local-tier: a local confirm with a coordinator file is refused by the guard", "deny", rule=None,
    tool="Bash", command=LT_CONFIRM, cwd=PUSHSSH, session=LT_SID, env={"CLAUDE_CODE_SESSION_ID": LT_SID}, config=LT_COORD)
# CONTROL, green on the old code: the batch-runner file with equal ids is allowed, as the old guard allows every confirm.
add("local-tier: a local confirm with a batch-runner file and equal ids is allowed", "allow",
    tool="Bash", command=LT_CONFIRM, cwd=PUSHSSH, session=LT_SID, env={"CLAUDE_CODE_SESSION_ID": LT_SID},
    config=LT_BATCH, silent=True)

FAMILY = _LT_PREV_FAMILY
