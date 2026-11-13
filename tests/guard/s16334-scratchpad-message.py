# section 16334
FAMILY = "scratchpad-message"
FAMILIES["scratchpad-message"] = "a git commit whose -F message file sits in a session scratchpad: an agent's call is refused in every flag form, through a link into the scratchpad, and an orchestrator's call, a heredoc, -m and a gh body file pass"
#
# `scratchpad-commit-msg-owner`. An agent's `git commit -F <file>` is refused when the file sits in ANY
# session's scratchpad. The agents of a session share that folder, so the file may hold another agent's
# message, and the commit would carry it. The rule reads the path only. The session id does not decide
# it, and a link is judged by the file it resolves to. An orchestrator's call (no agent_id) and the other
# ways to pass a message stay allowed.

SCRATCH_RULE = "scratchpad-commit-msg-owner"  # the rule id the refusal prints: the lane slug
SCRATCH_REMEDY = ("-F -",)                    # the refusal names the heredoc form as a way to pass a message
SCRATCH_AGENT = "9f3c1a7e5b2d4c8f6"           # an agent's id on its payload
NO_LINK_HERE = "this host gives no symlink, so the link case does not run here"


def scratch_refuse(name, command, cwd=NOGIT, session=FAKE_SESSION, agent_id=SCRATCH_AGENT,
                   rule=SCRATCH_RULE, carries=SCRATCH_REMEDY):
    """One case: an agent's commit is refused. By default the refusal is the scratchpad rule, and its remedy
    names `-F -`. `rule=None` and `carries=()` pin only the refusal, whichever rule gives it."""
    sh(name, command, "deny", rule, carries=carries, cwd=cwd, session=session, agent_id=agent_id)


def scratch_allow(name, command, cwd=NOGIT, session=FAKE_SESSION, agent_id=SCRATCH_AGENT):
    """One case: the call is allowed. Its only difference from a deny case is the one variable named."""
    sh(name, command, "allow", cwd=cwd, session=session, agent_id=agent_id)


SCRATCH_CMD = VCS + " commit -F " + slash(SCRATCH_MSG)
# Each flag form reaches its own branch of message_sources: the long form, the value after the flag,
# the glued value, a cluster of short flags, and the amend act.
scratch_refuse("scratchpad-message: an agent's commit -F of a scratchpad file is refused", SCRATCH_CMD)
scratch_refuse("scratchpad-message: an agent's commit --file= of a scratchpad file is refused",
             VCS + " commit --file=" + slash(SCRATCH_MSG))
scratch_refuse("scratchpad-message: an agent's commit --file of a scratchpad file is refused",
             VCS + " commit --file " + slash(SCRATCH_MSG))
scratch_refuse("scratchpad-message: an agent's commit -F<file> glued of a scratchpad file is refused",
             VCS + " commit -F" + slash(SCRATCH_MSG))
scratch_refuse("scratchpad-message: an agent's commit -aF <file> cluster of a scratchpad file is refused",
             VCS + " commit -aF " + slash(SCRATCH_MSG))
scratch_refuse("scratchpad-message: an agent's commit --amend -F of a scratchpad file is refused",
             VCS + " commit --amend -F " + slash(SCRATCH_MSG))
# A relative path resolves against the call's cwd, which here is the scratchpad folder itself.
scratch_refuse("scratchpad-message: an agent's relative -F from inside its scratchpad is refused",
             VCS + " commit -F commit_msg.txt", cwd=os.path.dirname(SCRATCH_MSG))
# The file is judged by its path, so an empty file, another session's file and a call with no
# session id are all refused alike.
scratch_refuse("scratchpad-message: an agent's commit -F of an empty scratchpad file is refused",
             VCS + " commit -F " + slash(SCRATCH_EMPTY))
scratch_refuse("scratchpad-message: an agent's commit -F of another session's scratchpad file is refused",
             VCS + " commit -F " + slash(SCRATCH_OTHER_MSG))
scratch_refuse("scratchpad-message: an agent's commit -F of a scratchpad file with no session id is refused",
             SCRATCH_CMD, session=None)
# A scanner reads the commit after a comment opener in a string, a multi-line string, or a lone quote.
scratch_refuse("scratchpad-message: a comment opener in a string does not hide the -F scratchpad commit",
             'echo "# not a comment" && ' + SCRATCH_CMD)
scratch_refuse("scratchpad-message: a comment opener in a multi-line string does not hide the -F scratchpad commit",
             'echo "first\n# second"\n' + SCRATCH_CMD)
scratch_refuse("scratchpad-message: a lone quote in text does not hide the -F scratchpad commit",
             LONE_PAIR + SCRATCH_CMD)
if LINKS_MADE:
    scratch_refuse("scratchpad-message: an agent's commit -F of a link outside its scratchpad, into it, is refused",
                 VCS + " commit -F " + slash(SCRATCH_LINK_IN))
else:
    skip_case("scratchpad-message: an agent's commit -F of a link into its scratchpad is refused", NO_LINK_HERE)

# The controls. Each differs from a deny above by the one variable its name gives.
scratch_allow("scratchpad-message: an orchestrator's commit -F of the same scratchpad file is allowed",
              SCRATCH_CMD, agent_id=None)
scratch_allow("scratchpad-message: an agent's commit -F - with a heredoc is allowed",
              VCS + " commit -F - <<'EOF'\ntitle\n\nclean body\nEOF")
scratch_allow("scratchpad-message: an agent's heredoc body that names a scratchpad path is allowed",
              VCS + " commit -F - <<'EOF'\ntitle\n\nsee " + slash(SCRATCH_MSG) + "\nEOF")
scratch_allow("scratchpad-message: an agent's commit -m is allowed", VCS + ' commit -m "title"')
scratch_allow("scratchpad-message: an agent's commit -F of a file outside every scratchpad is allowed",
              VCS + " commit -F " + slash(MSG_NOGIT))
scratch_allow("scratchpad-message: a commit named in a shell comment runs no commit and is allowed",
              "echo x # " + SCRATCH_CMD)
scratch_allow("scratchpad-message: an agent's gh pr create --body-file of a scratchpad file is not this rule",
              "gh pr create --draft --title t --body-file " + slash(SCRATCH_MSG))
if LINKS_MADE:
    scratch_allow("scratchpad-message: an agent's commit -F of a link in its scratchpad, out to a file, is allowed",
                  VCS + " commit -F " + slash(SCRATCH_LINK_OUT))
else:
    skip_case("scratchpad-message: an agent's commit -F of a link out of its scratchpad is allowed", NO_LINK_HERE)

# The directory the commit runs in is set in the same command: by a variable, by pushd, or by git's own
# -C. Each form must still deny, judged from the directory the command really runs in.
# The variable binds the long-name form of the folder. A value holding `~` is no literal to the guard's
# _rm_literal, so `$S` would stay unexpanded, cite-by-id would refuse the file as unread, and this case
# would test a different rule on a Windows temp folder named with its 8.3 short name.
SCRATCH_DIR = slash(long_name(os.path.dirname(SCRATCH_MSG)))
if "~" in SCRATCH_DIR:   # no long name on this host: the case would test cite-by-id, so it does not run here
    skip_case("scratchpad-message: an agent's commit -F through a variable set in the same command is refused",
              "the temp folder holds ~ and has no long name here, so the variable case would test cite-by-id")
else:
    scratch_refuse("scratchpad-message: an agent's commit -F through a variable set in the same command is refused",
                 "S=" + SCRATCH_DIR + "; " + VCS + " commit -F $S/commit_msg.txt")
# A variable whose value holds `~` is no literal to the guard, so the file it names is unread and the call is
# refused. The file is clean and sits outside every scratchpad. No rule id is pinned: the case fails only when
# such a call is let through.
scratch_refuse("scratchpad-message: an agent's commit -F through a variable holding ~ is refused, by any rule",
             "S=" + slash(TILDE_DIR) + "; " + VCS + " commit -F $S/commit_msg.txt", rule=None, carries=())
scratch_refuse("scratchpad-message: an agent's commit -F after pushd into its scratchpad is refused",
             "pushd " + SCRATCH_DIR + " && " + VCS + " commit -F commit_msg.txt")
scratch_refuse("scratchpad-message: an agent's commit -C . -F after cd into its scratchpad is refused",
             "cd " + SCRATCH_DIR + " && " + VCS + " -C . commit -F commit_msg.txt")
# The control for the pushd form: the same directory move, to a folder outside every scratchpad, allows.
scratch_allow("scratchpad-message: an agent's commit -F of a relative file after pushd outside every scratchpad is allowed",
              "pushd " + slash(NOGIT) + " && " + VCS + " commit -F msg_nogit.txt")
# A main session's payload as measured (docs/decisions/a-kill-by-pid-needs-an-owned-pid.md): agent_id and
# agent_type both null. It is no agent call, so the same scratchpad file passes.
add("scratchpad-message: an orchestrator payload with agent_id and agent_type null is allowed", "allow",
    raw=json.dumps({"tool_name": "Bash", "tool_input": {"command": SCRATCH_CMD}, "cwd": NOGIT,
                    "session_id": FAKE_SESSION, "agent_id": None, "agent_type": None}))

# =========================================================================== 5b2. the records page on a ready pull request
