# section 13407
FAMILY = "coordinator-scope"
#
# Rule coordinator-scope (decision session-tiers; rule roles-orchestrator-never-builds). A cloud coordinator
# briefs lanes and writes records. Its own calls write no repository path outside the record homes, spawn no
# agent outside its list (Plan, Explore, claude-code-guide and the refuter), and merge nothing. Its role is the
# role file's, else the cs-build tag its own get_session record holds after the tags its own later
# set_session_tags calls add or remove in the same transcript.
#
# A deny case passes only when its reason names the rule (test_guard scores that), so a deny from another rule
# is a fail. On main this rule does not exist: every refusal case below is red because the guard allows the call.
import guard_core as _guard_core  # noqa: E402  the one home of the refuter role's name (hooks/guard_core.py)

REFUTER_ROLE = _guard_core.REFUTER_ROLE
COORD_RULE = "coordinator-scope"
COORD_ROLE_TAG = "cs-build:coordinator"
COORD_RECORD = "session_COORDOWN01"          # the id a get_session record names
COORD_OWN_ENV = "cse_COORDOWN01"             # the environment's form of that id (hooks/override.py)
COORD_ENV = {"CLAUDE_CODE_REMOTE": "true", "CLAUDE_CODE_REMOTE_SESSION_ID": COORD_OWN_ENV}
COORD_CFG = os.path.join(ROOT, "coordcfg")          # a config folder whose role file names the coordinator
COORD_NOROLE = os.path.join(ROOT, "coordnorole")    # a config folder with no role file, so the transcript decides
COORD_DIR = os.path.join(ROOT, "coordrec")
COORD_ROLE_FILE = os.path.join(COORD_CFG, "state", "merge-role.json")
COORD_REPO_FILE = os.path.join(REPO, "src", "app.py")                          # a repository path, no record home
COORD_RECORD_FILE = os.path.join(REPO, "docs", "decisions", "coordinator-probe.md")  # a record home


def build_role_file():
    """The role file the guard reads for this session: a coordinator's own role, under the config folder's state."""
    os.makedirs(os.path.dirname(COORD_ROLE_FILE), exist_ok=True)
    with open(COORD_ROLE_FILE, "w", encoding="utf-8") as handle:
        json.dump({"session": COORD_OWN_ENV, "role": "coordinator"}, handle)


# Registered on the config folder: materialize_for builds a fixture when a case's config field names its key.
lazy_fixture([COORD_CFG], build_role_file)


def coord_tags_call(tool_id, add=(), remove=()):
    """One paired set_session_tags call on the coordinator's own record, adding and removing the given tags."""
    tool_input = {"session_ids": [COORD_RECORD]}
    if add:
        tool_input["add"] = list(add)
    if remove:
        tool_input["remove"] = list(remove)
    return [role_use(tool_id, SET_SESSION_TAGS, tool_input), role_result(tool_id, "ok")]


# The transcripts a session's own get_session record and later tag calls make. Each name is one role shape.
COORD_TRANSCRIPTS = {
    "record": role_call("g1", COORD_TAGS, session=COORD_RECORD),
    "added": role_call("g1", LANE_TAGS, session=COORD_RECORD) + coord_tags_call("t1", add=[COORD_ROLE_TAG]),
    "removed": role_call("g1", COORD_TAGS, session=COORD_RECORD) + coord_tags_call("t1", remove=[COORD_ROLE_TAG]),
    "added-then-removed": (role_call("g1", LANE_TAGS, session=COORD_RECORD)
                           + coord_tags_call("t1", add=[COORD_ROLE_TAG]) + coord_tags_call("t2", remove=[COORD_ROLE_TAG])),
    "no-record": [role_said("Check the open pull requests.")],  # no own get_session, no own tag call: the /clear gap
}


def coord_transcript(name):
    return os.path.join(COORD_DIR, name + ".jsonl")


def build_coord_transcripts():
    os.makedirs(COORD_DIR, exist_ok=True)
    for name, lines in COORD_TRANSCRIPTS.items():
        with open(coord_transcript(name), "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")


lazy_fixture([coord_transcript(name) for name in COORD_TRANSCRIPTS], build_coord_transcripts)

# --- the role file says coordinator: the role file decides, the transcript does not ---
add("coordinator-scope: a cloud coordinator's Edit of a repository path that is no record home is refused", "deny",
    COORD_RULE, tool="Edit", cwd=REPO, env=COORD_ENV, config=COORD_CFG, file_path=COORD_REPO_FILE)
add("coordinator-scope: a cloud coordinator's Write of a record home is allowed", "allow",
    tool="Write", cwd=REPO, env=COORD_ENV, config=COORD_CFG, file_path=COORD_RECORD_FILE)
sh("coordinator-scope: a cloud coordinator's shell redirect onto a repository path that is no record home is refused",
   "echo x > " + COORD_REPO_FILE, "deny", COORD_RULE, cwd=REPO, env=COORD_ENV, config=COORD_CFG)
# Control: main already refuses the merge tool for a coordinator (rule merge-confirm-repo), so no rule is named here.
sh("coordinator-scope: a cloud coordinator's merge tool run stays refused (control: merge-confirm-repo on main)",
   MERGE_SHIM + " 1 --confirm", "deny", None, cwd=NOGIT, env=COORD_ENV, config=COORD_CFG)
sh("coordinator-scope: a cloud coordinator's gh pr merge in the shell is refused",
   "gh pr merge 5 --squash", "deny", COORD_RULE, cwd=NOGIT, env=COORD_ENV, config=COORD_CFG)
sh("coordinator-scope: a cloud coordinator's gh pr merge with the repo flag before the verb is refused",
   "gh -R o/r pr merge 5", "deny", COORD_RULE, cwd=NOGIT, env=COORD_ENV, config=COORD_CFG)
# gh-write-cloud refuses every gh pr merge in a cloud session, --disable-auto included, and runs after this rule. So the
# verdict is that rule's deny; this rule's pin is that its reason never names coordinator-scope (the exemption holds).
sh("coordinator-scope: a cloud coordinator's gh pr merge --disable-auto is not its refusal (gh-write-cloud refuses it)",
   "gh pr merge --disable-auto 5", "deny", "gh-write-cloud", lacks=COORD_RULE, cwd=NOGIT, env=COORD_ENV,
   config=COORD_CFG)
add("coordinator-scope: a cloud coordinator's Agent spawn of a builder is refused", "deny", COORD_RULE,
    tool="Agent", cwd=NOGIT, env=COORD_ENV, config=COORD_CFG, subagent_type="builder", prompt="Build the change.")
add("coordinator-scope: a cloud coordinator's Agent spawn of a general-purpose agent is refused", "deny", COORD_RULE,
    tool="Agent", cwd=NOGIT, env=COORD_ENV, config=COORD_CFG, subagent_type="general-purpose", prompt="Do the work.")
add("coordinator-scope: a cloud coordinator's Agent spawn of an Explore agent is allowed", "allow",
    tool="Agent", cwd=NOGIT, env=COORD_ENV, config=COORD_CFG, subagent_type="Explore", prompt="Find the file.")
add("coordinator-scope: a cloud coordinator's Agent spawn of a Plan agent is allowed", "allow",
    tool="Agent", cwd=NOGIT, env=COORD_ENV, config=COORD_CFG, subagent_type="Plan", prompt="Plan the change.")
add("coordinator-scope: a cloud coordinator's Agent spawn of a claude-code-guide agent is allowed", "allow",
    tool="Agent", cwd=NOGIT, env=COORD_ENV, config=COORD_CFG, subagent_type="claude-code-guide",
    prompt="Explain the setting.")
# The rule reads the Task tool name as well as Agent (SPAWN_TOOLS in hooks/guard.py): a Task spawn of a builder is
# refused, and a Task spawn of a listed type is allowed. The refused one is the pin: an allow alone passes whether or not the rule reads Task.
add("coordinator-scope: a cloud coordinator's Task spawn of a Plan agent is allowed", "allow",
    tool="Task", cwd=NOGIT, env=COORD_ENV, config=COORD_CFG, subagent_type="Plan", prompt="Plan the change.")
add("coordinator-scope: a cloud coordinator's Task spawn of a builder is refused", "deny", COORD_RULE,
    tool="Task", cwd=NOGIT, env=COORD_ENV, config=COORD_CFG, subagent_type="builder", prompt="Build the change.")
# The refuter is on the coordinator's list (decision coordinator-spawns-refuter). On main no coordinator rule
# exists, so this allow is a green control: main allows every spawn. Its red is the mixed Workflow below.
add("coordinator-scope: a cloud coordinator's Agent spawn of a refuter is allowed", "allow",
    tool="Agent", cwd=NOGIT, env=COORD_ENV, config=COORD_CFG, subagent_type=REFUTER_ROLE,
    prompt="Argue against the plan.")
add("coordinator-scope: a cloud coordinator's Workflow that spawns only a refuter is allowed", "allow",
    tool="Workflow", cwd=NOGIT, env=COORD_ENV, config=COORD_CFG,
    script="await agent({prompt: 'Round 1. Argue against the plan.', agentType: '" + REFUTER_ROLE + "'})")
add("coordinator-scope: a cloud coordinator's Workflow that spawns a refuter and a builder is refused", "deny",
    COORD_RULE, tool="Workflow", cwd=NOGIT, env=COORD_ENV, config=COORD_CFG,
    script="await agent({prompt: 'Round 1. Argue against the plan.', agentType: '" + REFUTER_ROLE + "'})\n"
           "await agent({prompt: 'Build the change.', agentType: 'builder'})")
# A settled green head (GREEN_ON, as the merge rows use) so merge-checks allows the call and only this rule can refuse it.
# The role comes from the own record, since the role file lives in COORD_CFG and this case's config is MERGECFG.
add("coordinator-scope: a cloud coordinator's merge_pull_request is refused", "deny", COORD_RULE,
    tool="mcp__github__merge_pull_request", cwd=NOGIT, env=dict(COORD_ENV), env_path=GREEN_ON, config=MERGECFG,
    transcript=coord_transcript("record"), owner="o", repo="r", pullNumber=1)
add("coordinator-scope: a cloud coordinator's enable_pr_auto_merge is refused", "deny", COORD_RULE,
    tool="mcp__github__enable_pr_auto_merge", cwd=NOGIT, env=dict(COORD_ENV), env_path=GREEN_ON, config=MERGECFG,
    transcript=coord_transcript("record"), owner="o", repo="r", pullNumber=1)
add("coordinator-scope: a cloud coordinator's create_or_update_file of a repository path that is no record home is refused",
    "deny", COORD_RULE, tool="mcp__github__create_or_update_file", cwd=NOGIT, env=COORD_ENV, config=COORD_CFG,
    owner="o", repo="r", path="src/app.py", content="x", message="m", branch="b")

# --- the false-alarm list: a coordinator's record writes, its scratchpad and an agent's call stay allowed ---
# Each one is a write the rule must not refuse. A refusal of any of them stops the coordinator writing its own records.
sh("coordinator-scope: a cloud coordinator's sed -i on a decision record is allowed",
   "sed -i s/a/b/ docs/decisions/x.md", "allow", cwd=REPO, env=COORD_ENV, config=COORD_CFG)
sh("coordinator-scope: a cloud coordinator's echo appended to the records index is allowed",
   "echo x >> docs/records.md", "allow", cwd=REPO, env=COORD_ENV, config=COORD_CFG)
sh("coordinator-scope: a cloud coordinator's cp onto a decision record is allowed",
   "cp /tmp/a docs/decisions/b.md", "allow", cwd=REPO, env=COORD_ENV, config=COORD_CFG)
sh("coordinator-scope: a cloud coordinator's tee into the todo file is allowed",
   "tee docs/todo.md", "allow", cwd=REPO, env=COORD_ENV, config=COORD_CFG)
add("coordinator-scope: a cloud coordinator's create_or_update_file of a decision record is allowed", "allow",
    tool="mcp__github__create_or_update_file", cwd=NOGIT, env=COORD_ENV, config=COORD_CFG,
    owner="o", repo="r", path="docs/decisions/x.md", content="x", message="m", branch="b")
# A repository path inside this session's own scratchpad: PRIVREPO is a repository under the session's scratchpad.
# Without the scratchpad clause the same path is no record home and is refused, so the allow pins the clause.
add("coordinator-scope: a cloud coordinator's Write into a repository in its own scratchpad is allowed", "allow",
    tool="Write", cwd=PRIVREPO, env=COORD_ENV, config=COORD_CFG, session=FAKE_SESSION,
    file_path=os.path.join(PRIVREPO, "src", "app.py"))
# An agent's call is not the coordinator's own call (it carries agent_id), so the rule does not judge it. The same
# Edit without agent_id is refused (the Edit case above), so the allow pins the agent_id clause.
add("coordinator-scope: a call carrying agent_id is not the coordinator's own call: its Edit of a repo path is allowed",
    "allow", tool="Edit", cwd=REPO, env=COORD_ENV, config=COORD_CFG, agent_id="coord-sub1",
    file_path=COORD_REPO_FILE)

# --- no role file: the role is the cs-build tag the session's own get_session record holds, after its own tag calls ---
add("coordinator-scope: with no role file, a coordinator record's role refuses an Edit of a repository path", "deny",
    COORD_RULE, tool="Edit", cwd=REPO, env=COORD_ENV, config=COORD_NOROLE,
    transcript=coord_transcript("record"), file_path=COORD_REPO_FILE)
add("coordinator-scope: role apply: a coordinator's own later add of the tag holds the role for the same session", "deny",
    COORD_RULE, tool="Edit", cwd=REPO, env=COORD_ENV, config=COORD_NOROLE,
    transcript=coord_transcript("added"), file_path=COORD_REPO_FILE)
add("coordinator-scope: role apply: a coordinator's own later remove of the tag never loosens its record's role", "deny",
    COORD_RULE, tool="Edit", cwd=REPO, env=COORD_ENV, config=COORD_NOROLE,
    transcript=coord_transcript("removed"), file_path=COORD_REPO_FILE)
add("coordinator-scope: role apply: an own add then an own remove in one pass leaves the lane role, so the write is allowed",
    "allow", tool="Edit", cwd=REPO, env=COORD_ENV, config=COORD_NOROLE,
    transcript=coord_transcript("added-then-removed"), file_path=COORD_REPO_FILE)
add("coordinator-scope: with no own record and no own tag call, the role is not held, so the write is allowed (/clear gap)",
    "allow", tool="Edit", cwd=REPO, env=COORD_ENV, config=COORD_NOROLE,
    transcript=coord_transcript("no-record"), file_path=COORD_REPO_FILE)
