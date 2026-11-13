# section 13407
FAMILY = "coordinator-scope"
#
# Rule coordinator-scope (decision session-tiers; rule roles-orchestrator-never-builds). A cloud coordinator
# briefs lanes and writes records. Its own calls write no repository path outside the record homes, spawn no
# agent outside its list (Plan, Explore, claude-code-guide and the refuter), and merge nothing. Its tier is the
# role file's, else the cs-build tag its own get_session record holds after the tags its own later
# set_session_tags calls add or remove in the same transcript.
#
# A deny case passes only when its reason names the rule (test_guard scores that), so a deny from another rule
# is a fail. On main this rule does not exist: every refusal case below is red because the guard allows the call.
import guard_core as _guard_core  # noqa: E402  the one home of the refuter role's name (hooks/guard_core.py)

REFUTER_ROLE = _guard_core.REFUTER_ROLE
COORD_RULE = "coordinator-scope"
COORD_TIER = "cs-build:coordinator"
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


# The transcripts a session's own get_session record and later tag calls make. Each name is one tier shape.
COORD_TRANSCRIPTS = {
    "record": role_call("g1", COORD_TAGS, session=COORD_RECORD),
    "added": role_call("g1", LANE_TAGS, session=COORD_RECORD) + coord_tags_call("t1", add=[COORD_TIER]),
    "removed": role_call("g1", COORD_TAGS, session=COORD_RECORD) + coord_tags_call("t1", remove=[COORD_TIER]),
    "added-then-removed": (role_call("g1", LANE_TAGS, session=COORD_RECORD)
                           + coord_tags_call("t1", add=[COORD_TIER]) + coord_tags_call("t2", remove=[COORD_TIER])),
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
add("coordinator-scope: a cloud coordinator's Agent spawn of a builder is refused", "deny", COORD_RULE,
    tool="Agent", cwd=NOGIT, env=COORD_ENV, config=COORD_CFG, subagent_type="builder", prompt="Build the change.")
add("coordinator-scope: a cloud coordinator's Agent spawn of a general-purpose agent is refused", "deny", COORD_RULE,
    tool="Agent", cwd=NOGIT, env=COORD_ENV, config=COORD_CFG, subagent_type="general-purpose", prompt="Do the work.")
add("coordinator-scope: a cloud coordinator's Agent spawn of an Explore agent is allowed", "allow",
    tool="Agent", cwd=NOGIT, env=COORD_ENV, config=COORD_CFG, subagent_type="Explore", prompt="Find the file.")
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
# The tier comes from the own record, since the role file lives in COORD_CFG and this case's config is MERGECFG.
add("coordinator-scope: a cloud coordinator's merge_pull_request is refused", "deny", COORD_RULE,
    tool="mcp__github__merge_pull_request", cwd=NOGIT, env=dict(COORD_ENV), env_path=GREEN_ON, config=MERGECFG,
    transcript=coord_transcript("record"), owner="o", repo="r", pullNumber=1)
add("coordinator-scope: a cloud coordinator's enable_pr_auto_merge is refused", "deny", COORD_RULE,
    tool="mcp__github__enable_pr_auto_merge", cwd=NOGIT, env=dict(COORD_ENV), env_path=GREEN_ON, config=MERGECFG,
    transcript=coord_transcript("record"), owner="o", repo="r", pullNumber=1)
add("coordinator-scope: a cloud coordinator's create_or_update_file of a repository path that is no record home is refused",
    "deny", COORD_RULE, tool="mcp__github__create_or_update_file", cwd=NOGIT, env=COORD_ENV, config=COORD_CFG,
    owner="o", repo="r", path="src/app.py", content="x", message="m", branch="b")

# --- no role file: the tier is the cs-build tag the session's own get_session record holds, after its own tag calls ---
add("coordinator-scope: with no role file, a coordinator record's tier refuses an Edit of a repository path", "deny",
    COORD_RULE, tool="Edit", cwd=REPO, env=COORD_ENV, config=COORD_NOROLE,
    transcript=coord_transcript("record"), file_path=COORD_REPO_FILE)
add("coordinator-scope: tier apply: a coordinator's own later add of the tag holds the tier for the same session", "deny",
    COORD_RULE, tool="Edit", cwd=REPO, env=COORD_ENV, config=COORD_NOROLE,
    transcript=coord_transcript("added"), file_path=COORD_REPO_FILE)
add("coordinator-scope: tier apply: a coordinator's own later remove of the tag never loosens its record's tier", "deny",
    COORD_RULE, tool="Edit", cwd=REPO, env=COORD_ENV, config=COORD_NOROLE,
    transcript=coord_transcript("removed"), file_path=COORD_REPO_FILE)
add("coordinator-scope: tier apply: an own add then an own remove in one pass leaves the lane tier, so the write is allowed",
    "allow", tool="Edit", cwd=REPO, env=COORD_ENV, config=COORD_NOROLE,
    transcript=coord_transcript("added-then-removed"), file_path=COORD_REPO_FILE)
add("coordinator-scope: with no own record and no own tag call, the tier is not held, so the write is allowed (/clear gap)",
    "allow", tool="Edit", cwd=REPO, env=COORD_ENV, config=COORD_NOROLE,
    transcript=coord_transcript("no-record"), file_path=COORD_REPO_FILE)
