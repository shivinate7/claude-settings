# section 43725
FAMILY = "pr-create-session-link"
#
# `pr-create-session-link`. An MCP create call for a pull request, in a repo that uses the merge tool and from a cloud
# session with a known id, is refused unless its body holds this session's `Session: https://claude.ai/code/<id>` line.
# The merge tool reads that line at `--confirm` (merge/merge.py own_session_link), so a body without it fails only after
# review and CI. The refusal names the line to add, so the fix costs one retry at creation.
#
# THE FIXTURES. STAMPREPO and STAMPNOBLOCK, from section 13406, are reused and not rebuilt (one home). STAMPREPO's stamp holds a
# `merge` block, so it is a merge-tool repo. STAMPNOBLOCK's stamp holds none. Each case names its session through `env`:
# CLAUDE_CODE_REMOTE_SESSION_ID=cse_x reads as session_x. decide() drops the runner's own id, so no case sees a stray one.
# Each case passes config=MERGECFG, whose rules file points at this repo, so the merge tool loads for any copy of the guard.

PCSL_RULE = "pr-create-session-link"
PCSL_CREATE = "mcp__github__create_pull_request"
PCSL_UPDATE = "mcp__github__update_pull_request"
PCSL_LINK = "https://claude.ai/code/"
PCSL_LINE = "Session: " + PCSL_LINK              # where the refusal's line starts; the draft-pr refusal must not print it
PCSL_OWN = PCSL_LINE + "session_x"              # this session's line (env cse_x)
PCSL_OTHER = PCSL_LINE + "session_y"            # another session's line
PCSL_ENV = {"CLAUDE_CODE_REMOTE_SESSION_ID": "cse_x"}
PCSL_LOCAL = {"CLAUDE_CODE_REMOTE_SESSION_ID": None}   # a local session: the id is unset
PCSL_TARGET_LACKS = ("create_pull_request", "gh pr create")  # the refusal names neither the tool nor the command it refuses
PCSL_FIELDS = {"owner": "y", "repo": "x", "title": "x", "head": "h", "base": "main"}
PCSL_REFUSED = dict(expected="deny", rule=PCSL_RULE, carries=PCSL_OWN, lacks=PCSL_TARGET_LACKS)


def pcsl_create(name, expected, rule=None, cwd=STAMPREPO, env=PCSL_ENV, carries=(), lacks=(), **fields):
    """One MCP create call on the case's own fields. Draft is true and the body is absent unless the case sets them."""
    values = dict(PCSL_FIELDS, draft=True)
    values.update(fields)
    add(name, expected, rule=rule, tool=PCSL_CREATE, cwd=cwd, env=env, config=MERGECFG,
        carries=carries, lacks=lacks, **values)


def _pcsl_scope():
    """The two fixtures hold what the case names: a merge block in one stamp and none in the other, each a git tree.
    The cases branch on this, so a fixture that drifted would pass or refuse for the wrong reason."""
    materialize(STAMPREPO)
    materialize(STAMPNOBLOCK)
    problems = []
    for where, has_block in ((STAMPREPO, True), (STAMPNOBLOCK, False)):
        if not os.path.isdir(os.path.join(where, ".git")):
            problems.append("%s is not a git tree" % where)
        try:
            with open(os.path.join(where, ".github", "stamp.json"), encoding="utf-8") as handle:
                stamp = json.load(handle)
        except (OSError, ValueError) as error:
            problems.append("%s has no readable stamp (%s)" % (where, error))
            continue
        if ("merge" in stamp) != has_block:
            problems.append("%s has %s merge block" % (where, "no" if has_block else "a"))
    if problems:
        return False, "; ".join(problems)
    return True, "the merge repo holds a merge block, the plain repo holds none, and both are git trees"


# Refused: the body names no link of this session. The reason gives the line to add, and it names no tool or command.
pcsl_create("pr-create-session-link: a create with no body is refused", **PCSL_REFUSED)
pcsl_create("pr-create-session-link: a create with an empty body is refused", body="", **PCSL_REFUSED)
pcsl_create("pr-create-session-link: a create whose body is x is refused", body="x", **PCSL_REFUSED)
pcsl_create("pr-create-session-link: a create whose body holds another session's link only is refused", body=PCSL_OTHER,
            **PCSL_REFUSED)
# A non-string body reads as a body with no link. The carried line is what separates a refusal from a crash that allows.
pcsl_create("pr-create-session-link: a create whose body is not a string is refused, not crashed", body=5, **PCSL_REFUSED)

# The draft-pr refusal comes first: a draft false create gets it whatever its body holds. The link line must not be printed by it.
pcsl_create("pr-create-session-link: a draft false create with no body gets the draft-pr refusal first", expected="deny",
            rule="draft-pr", carries=("draft", "integration PR"), lacks=DRAFT_LACKS + (PCSL_LINE,), draft=False)
pcsl_create("pr-create-session-link: a draft false create with this session's link gets the draft-pr refusal first",
            expected="deny", rule="draft-pr", carries=("draft", "integration PR"), lacks=DRAFT_LACKS + (PCSL_LINE,),
            draft=False, body=PCSL_OWN)

# Allowed: the link is this session's, on its own line or in prose. Each control below changes one factor from the refused rows.
pcsl_create("pr-create-session-link: a body with this session's link on its own line is allowed", expected="allow",
            body="Summary of the change.\n\n" + PCSL_OWN + "\n")
pcsl_create("pr-create-session-link: a body that names this session's link inside prose is allowed", expected="allow",
            body="Opened from " + PCSL_LINK + "session_x, the session that wrote it.")
pcsl_create("pr-create-session-link: a create from a local session with no session id is allowed", expected="allow",
            env=PCSL_LOCAL)
pcsl_create("pr-create-session-link: a create in a repo with no merge tool is allowed", expected="allow", cwd=STAMPNOBLOCK)
add("pr-create-session-link: an MCP update of a pull request is allowed, the rule judges only a create", "allow",
    tool=PCSL_UPDATE, cwd=STAMPREPO, env=PCSL_ENV, config=MERGECFG, owner="y", repo="x", pullNumber=12,
    body="Updated the description only.")


def pcsl_override_check():
    """The owner types `override` after a refused create: the next create passes once, then the create after it is refused again.
    The steps run through ov_story, the one home of the one-act story (section 36421)."""
    materialize(STAMPREPO)
    session = "pcsl-override"
    notes = []

    def create(seconds):
        return ov_call(PCSL_CREATE, dict(PCSL_FIELDS, draft=True), STAMPREPO, MERGECFG, session, seconds, env=PCSL_ENV)

    def typed_then_create(seconds):
        notes.append(ov_type(MERGECFG, session, "override", seconds - 1))
        return create(seconds)

    ok, why = ov_story([
        ("with no override", lambda: create(0), "deny", PCSL_RULE),
        ("the first create after the owner's override", lambda: typed_then_create(60), "allow", PCSL_RULE),
        ("the create after the one act", lambda: create(120), "deny", PCSL_RULE),
    ])
    note = "; ".join(text for text in notes if text)
    if not ok:
        return False, why + (("; " + note) if note else "")
    return True, "refused with no override, allowed once after the owner's override, then refused again"


# This section loads after the join of LOG_CHECKS_EXTRA (section 40805), so its log checks join LOG_CHECKS directly, as section 40806 does.
PCSL_SCOPE_LABEL = "pr-create-session-link: the merge repo and the plain repo hold the stamps their cases name"
PCSL_OVERRIDE_LABEL = "pr-create-session-link: a one-act override lifts a refused create once, then the next create is refused again"
LOG_FAMILY[PCSL_SCOPE_LABEL] = FAMILY
LOG_FAMILY[PCSL_OVERRIDE_LABEL] = FAMILY
LOG_CHECKS = LOG_CHECKS + ((PCSL_SCOPE_LABEL, _pcsl_scope), (PCSL_OVERRIDE_LABEL, pcsl_override_check))
