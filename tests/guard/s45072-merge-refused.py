# section 45072
FAMILY = "merge"
#
# Three refusals that main does not make yet. Each deny case is red on main: the call is allowed, or its reason lacks the
# remedy the case pins. The one exception is a form main already refuses, which pins that refusal for a fix to keep. Each
# allow case is a control that main already allows, and it sits beside the refusal it pins. The session fixtures are the role
# transcripts of section 13406 (role_path, ROLE_ENV), so no record is copied here.


# =========================================================================== auto-merge
# `auto-merge`. GitHub's auto-merge button is the owner's, so no session enables it, whatever its tier. The refusal
# names the merge tool that merges a pull request when the owner says so, and says the button stays the owner's. It
# never names the enable tool. Disabling auto-merge stops a merge, so it stays allowed.
AUTO_ENABLE = "mcp__github__enable_pr_auto_merge"
AUTO_CARRY = ("merge", "--confirm", "owner")
AUTO_LACKS = ("enable_pr_auto_merge",)
AUTO_ARGS = dict(owner="y", repo="x", pullNumber=5)
add("auto-merge: enable_pr_auto_merge is refused in a session with no record", "deny", rule="auto-merge",
    tool=AUTO_ENABLE, cwd=NOGIT, carries=AUTO_CARRY, lacks=AUTO_LACKS, **AUTO_ARGS)
for _who, _record in (("a lane", "lane"), ("a batch runner", "runner"), ("a coordinator", "coordinator"),
                      ("an untagged session", "untagged")):
    add("auto-merge: enable_pr_auto_merge in %s is refused" % _who, "deny", rule="auto-merge",
        tool=AUTO_ENABLE, cwd=NOGIT, transcript=role_path(_record), env=ROLE_ENV,
        carries=AUTO_CARRY, lacks=AUTO_LACKS, **AUTO_ARGS)
add("auto-merge: disable_pr_auto_merge stays allowed", "allow", tool="mcp__github__disable_pr_auto_merge",
    cwd=NOGIT, **AUTO_ARGS)
# The GraphQL API and the gh CLI reach the same button, so each is refused in the same sessions. The refusal names
# neither the enable mutation nor `--auto`. Disabling auto-merge stays allowed in both forms.
AUTO_CLI_LACKS = AUTO_LACKS + ("--auto", "enablePullRequestAutoMerge")
GQL_ENABLE = "gh api graphql -f query='mutation{enablePullRequestAutoMerge(input:{pullRequestId:\"x\"}){clientMutationId}}'"
GQL_DISABLE = "gh api graphql -f query='mutation{disablePullRequestAutoMerge(input:{pullRequestId:\"x\"}){clientMutationId}}'"
GH_AUTO_MERGE = "gh pr merge 5 --auto --squash"
GREEN_HEAD = dict(env_path=GHMAIN + os.pathsep + PY_PATH, config=MERGECFG)
for _who, _record in (("no session record", None), ("a lane", "lane"), ("a batch runner", "runner"),
                      ("a coordinator", "coordinator"), ("an untagged session", "untagged")):
    _role = {} if _record is None else dict(transcript=role_path(_record), env=ROLE_ENV)
    sh("auto-merge: the GraphQL enable mutation in %s is refused" % _who, GQL_ENABLE, "deny", "auto-merge",
       cwd=NOGIT, carries=AUTO_CARRY, lacks=AUTO_CLI_LACKS, **_role)
    sh("auto-merge: gh pr merge --auto on a green head in %s is refused" % _who, GH_AUTO_MERGE, "deny",
       "auto-merge", cwd=NOGIT, carries=AUTO_CARRY, lacks=AUTO_CLI_LACKS, **GREEN_HEAD, **_role)
sh("auto-merge: the GraphQL disable mutation stays allowed", GQL_DISABLE, "allow", cwd=NOGIT)
sh("auto-merge: gh pr merge --disable-auto on a green head stays allowed", "gh pr merge 5 --disable-auto", "allow",
   silent=True, cwd=NOGIT, **GREEN_HEAD)
# A flag before the `graphql` endpoint must not hide the mutation. Each shape sends the same mutation, so each is refused
# in the same sessions as the bare endpoint above.
GQL_FLAGGED = (
    "gh api -X POST graphql",
    "gh api -H 'X-Github-Next-Global-ID: 1' graphql",
    "gh api --hostname github.com graphql",
)
for _shape in GQL_FLAGGED:
    for _who, _record in (("no session record", None), ("a lane", "lane"), ("a batch runner", "runner"),
                          ("a coordinator", "coordinator"), ("an untagged session", "untagged")):
        _role = {} if _record is None else dict(transcript=role_path(_record), env=ROLE_ENV)
        sh("auto-merge: the GraphQL enable mutation as `%s` in %s is refused" % (_shape, _who),
           GQL_ENABLE.replace("gh api graphql", _shape), "deny", "auto-merge", cwd=NOGIT, carries=AUTO_CARRY,
           lacks=AUTO_CLI_LACKS, **_role)
# The `--auto=true` form reaches the same button, so it is refused on a green head like `--auto`.
sh("auto-merge: gh pr merge --auto=true on a green head is refused", "gh pr merge 5 --auto=true", "deny", "auto-merge",
   cwd=NOGIT, carries=AUTO_CARRY, lacks=AUTO_CLI_LACKS, **GREEN_HEAD)


# =========================================================================== draft-pr through gh api
# `draft-pr` covers a pull request created through `gh api`: a POST to the pulls route with no number after it. A create
# with no `draft=true` opens a ready pull request, so it is refused. A create with `draft=true`, a read, and a comment on
# a pull request are not creates, so each stays allowed.
API_CREATE_CARRY = ("draft", "integration PR")
for _form, _command in (
    ("an implicit POST", "gh api repos/o/r/pulls -f title=t -f head=h -f base=main"),
    ("a -X POST", "gh api -X POST repos/o/r/pulls -f title=t -f head=h -f base=main"),
    ("an absolute URL", "gh api https://api.github.com/repos/o/r/pulls -f title=t -f head=h -f base=main"),
    ("a draft=false field", "gh api repos/o/r/pulls -f title=t -f draft=false"),
):
    sh("draft-pr: gh api create with no draft=true is refused, %s" % _form, _command, "deny", "draft-pr",
       cwd=NOGIT, carries=API_CREATE_CARRY, lacks=DRAFT_LACKS)
sh("draft-pr: gh api create with -F draft=true is allowed",
   "gh api repos/o/r/pulls -f title=t -f head=h -f base=main -F draft=true", "allow", cwd=NOGIT)
sh("draft-pr: gh api -X POST create with -F draft=true is allowed",
   "gh api -X POST repos/o/r/pulls -f title=t -f head=h -f base=main -F draft=true", "allow", cwd=NOGIT)
sh("draft-pr: gh api GET of the pulls route is allowed", "gh api repos/o/r/pulls", "allow", cwd=NOGIT)
sh("draft-pr: gh api comment on a pull request is not a create", "gh api repos/o/r/pulls/5/comments -f body=x",
   "allow", cwd=NOGIT)
sh("draft-pr: gh api create on an absolute URL with -F draft=true is allowed",
   "gh api https://api.github.com/repos/o/r/pulls -f title=t -f head=h -f base=main -F draft=true", "allow", cwd=NOGIT)
# gh api makes a call with fields a POST, so a read with fields reaches the guard as a create. The refusal names -X GET
# for that read. Its create remedy keeps -F draft=true. A read that names -X GET is no create, so it stays allowed.
sh("draft-pr: gh api read with fields is refused as a create, and the reason names -X GET",
   "gh api repos/o/r/pulls -f state=open", "deny", "draft-pr", cwd=NOGIT, carries=API_CREATE_CARRY + ("-X GET",),
   lacks=DRAFT_LACKS)
sh("draft-pr: gh api -X GET with fields on the pulls route is allowed", "gh api -X GET repos/o/r/pulls -f state=open",
   "allow", cwd=NOGIT)


# The scanner reads a call as the shell does. A quoted `#` or an apostrophe before a call does not hide it, and text in a
# quoted string, a heredoc body or a comment is no call. Each shape is one case, for each call that is scanned.
def call_shapes(call):
    """(label, command, expected) for one shell call: the call in each shape a scanner must read as the parser does."""
    return (
        ("after a quoted #", 'echo "#" && ' + call, "deny"),
        ("after an apostrophe in a word", "echo Don't && " + call, "deny"),
        ("on a line of a multi-line quoted string", 'echo "start\n' + call + '\nend"', "allow"),
        ("in a heredoc body", "cat <<'EOF'\n" + call + "\nEOF", "allow"),
        ("in a comment", "echo ok # " + call, "allow"),
    )


for _label, _command, _expected in call_shapes("gh api repos/o/r/pulls -f title=t -f head=h -f base=main"):
    _deny = _expected == "deny"
    sh("draft-pr: gh api create %s is %s" % (_label, "refused" if _deny else "no call"), _command, _expected,
       rule="draft-pr" if _deny else None, cwd=NOGIT, carries=API_CREATE_CARRY if _deny else (),
       lacks=DRAFT_LACKS if _deny else ())


# =========================================================================== ready-lane
# `ready-lane`. A lane's pull request stays a draft, and only the batch's integration pull request goes ready (`draft-pr`).
# A session proved cs-build:lane, by its own newest get_session record, is refused each call that marks a pull request
# ready: an MCP update with draft false, `gh pr ready`, and a gh api PATCH with draft false. A batch runner and an untagged
# session keep main's verdict, which allows these calls. An update with no draft key, or with draft true, marks nothing
# ready, so it stays allowed in a lane.
READY_RULE = "ready-lane"
READY_CARRY = ("integration PR",)
# The GraphQL mutation that marks a pull request ready. Its query holds single and double quotes, so the shape controls
# at the end of this file escape it by hand.
GQL_READY = "gh api graphql -f query='mutation{markPullRequestReadyForReview(input:{pullRequestId:\"x\"}){clientMutationId}}'"
READY_MARKS = (
    ("update_pull_request with draft false", "mcp__github__update_pull_request",
     dict(owner="y", repo="x", pullNumber=5, draft=False), None),
    ("gh pr ready 5", "Bash", {}, "gh pr ready 5"),
    ("gh api PATCH with draft=false", "Bash", {}, "gh api -X PATCH repos/o/r/pulls/5 -F draft=false"),
    ("gh api PATCH on an absolute URL with draft=false", "Bash", {},
     "gh api -X PATCH https://api.github.com/repos/o/r/pulls/5 -F draft=false"),
    ("gh api PATCH with an --input body", "Bash", {}, "gh api -X PATCH repos/o/r/pulls/5 --input body.json"),
    ("gh api graphql markPullRequestReadyForReview", "Bash", {}, GQL_READY),
)


def ready_case(name, expected, record, tool, tool_input, command):
    """One call that marks a pull request ready, judged in the session of `record` (a role transcript of 13406, or None)."""
    kw = {"cwd": NOGIT}
    if record:
        kw.update(transcript=role_path(record), env=ROLE_ENV)
    if expected == "deny":
        kw.update(rule=READY_RULE, carries=READY_CARRY, lacks=DRAFT_LACKS)
    if command:
        sh(name, command, expected, **kw)
    else:
        add(name, expected, tool=tool, **kw, **tool_input)


for _label, _tool, _tool_input, _command in READY_MARKS:
    ready_case("ready-lane: %s is refused in a lane session" % _label, "deny", "lane",
               _tool, _tool_input, _command)
    ready_case("ready-lane: %s in a batch runner session stays as main judges it" % _label, "allow", "runner",
               _tool, _tool_input, _command)
    ready_case("ready-lane: %s in an untagged session stays as main judges it" % _label, "allow", "untagged",
               _tool, _tool_input, _command)
ready_case("ready-lane: update_pull_request with no draft key stays allowed in a lane session", "allow", "lane",
           "mcp__github__update_pull_request", dict(owner="y", repo="x", pullNumber=5, title="x"), None)
ready_case("ready-lane: update_pull_request with draft true stays allowed in a lane session", "allow", "lane",
           "mcp__github__update_pull_request", dict(owner="y", repo="x", pullNumber=5, draft=True), None)
# Pins that kill a mutant: a PATCH that sets no draft field, or sets draft true, marks nothing ready, so a lane keeps it.
ready_case("ready-lane: gh api PATCH with a title and no draft field stays allowed in a lane session", "allow", "lane",
           "Bash", {}, "gh api -X PATCH repos/o/r/pulls/5 -f title=x")
ready_case("ready-lane: gh api PATCH with -F draft=true stays allowed in a lane session", "allow", "lane", "Bash", {},
           "gh api -X PATCH repos/o/r/pulls/5 -F draft=true")
# A record that cannot be read proves no lane, so the mark is judged as main judges it. `unreadable` is a folder (13406).
ready_case("ready-lane: a ready mark with an unreadable own record is allowed (fails open)", "allow", "unreadable",
           "mcp__github__update_pull_request", dict(owner="y", repo="x", pullNumber=5, draft=False), None)
# `--undo` takes a pull request back to draft. It marks nothing ready, so a lane may run it.
ready_case("ready-lane: gh pr ready 5 --undo stays allowed in a lane session", "allow", "lane", "Bash", {},
           "gh pr ready 5 --undo")
for _label, _command, _expected in call_shapes("gh pr ready 5"):
    ready_case("ready-lane: gh pr ready 5 %s is %s" % (_label, "refused in a lane" if _expected == "deny" else "no call"),
               _expected, "lane", "Bash", {}, _command)
# The GraphQL mark in a shape that holds text, not a call. Its apostrophe shape is left out: the query's quotes break it.
ready_case("ready-lane: the GraphQL ready mark in a multi-line quoted string is no call", "allow", "lane", "Bash", {},
           'echo "start\n' + GQL_READY.replace('"', '\\"') + '\nend"')
ready_case("ready-lane: the GraphQL ready mark in a heredoc body is no call", "allow", "lane", "Bash", {},
           "cat <<'EOF'\n" + GQL_READY + "\nEOF")
ready_case("ready-lane: the GraphQL ready mark in a comment is no call", "allow", "lane", "Bash", {},
           "echo ok # " + GQL_READY)
# A flag before the `graphql` endpoint must not hide the ready mark. A lane is refused; a batch runner is allowed.
for _shape in GQL_FLAGGED:
    _command = GQL_READY.replace("gh api graphql", _shape)
    ready_case("ready-lane: the GraphQL ready mark as `%s` is refused in a lane session" % _shape, "deny", "lane",
               "Bash", {}, _command)
    ready_case("ready-lane: the GraphQL ready mark as `%s` is allowed in a batch runner session" % _shape, "allow",
               "runner", "Bash", {}, _command)
# gh pr merge --auto through each call shape, on a green head: a call is refused, and text that holds it is no call.
for _label, _command, _expected in call_shapes(GH_AUTO_MERGE):
    _deny = _expected == "deny"
    sh("auto-merge: gh pr merge --auto %s is %s" % (_label, "refused" if _deny else "no call"), _command, _expected,
       rule="auto-merge" if _deny else None, cwd=NOGIT, carries=AUTO_CARRY if _deny else (),
       lacks=AUTO_CLI_LACKS if _deny else (), silent=not _deny, **GREEN_HEAD)
