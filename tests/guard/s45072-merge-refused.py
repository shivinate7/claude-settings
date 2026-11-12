# section 45072
FAMILY = "merge"
#
# Three refusals that main does not make yet. Each deny case is red on main, where the call is allowed. Each allow case
# is a control that main already allows, and it sits beside the refusal it pins. The session fixtures are the role
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


# =========================================================================== draft-pr through gh api
# `draft-pr` covers a pull request created through `gh api`: a POST to the pulls route with no number after it. A create
# with no `draft=true` opens a ready pull request, so it is refused. A create with `draft=true`, a read, and a comment on
# a pull request are not creates, so each stays allowed.
API_CREATE_CARRY = ("draft", "integration PR")
for _form, _command in (
    ("an implicit POST", "gh api repos/o/r/pulls -f title=t -f head=h -f base=main"),
    ("a -X POST", "gh api -X POST repos/o/r/pulls -f title=t -f head=h -f base=main"),
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
READY_MARKS = (
    ("update_pull_request with draft false", "mcp__github__update_pull_request",
     dict(owner="y", repo="x", pullNumber=5, draft=False), None),
    ("gh pr ready 5", "Bash", {}, "gh pr ready 5"),
    ("gh api PATCH with draft=false", "Bash", {}, "gh api -X PATCH repos/o/r/pulls/5 -F draft=false"),
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
for _label, _command, _expected in call_shapes("gh pr ready 5"):
    ready_case("ready-lane: gh pr ready 5 %s is %s" % (_label, "refused in a lane" if _expected == "deny" else "no call"),
               _expected, "lane", "Bash", {}, _command)
