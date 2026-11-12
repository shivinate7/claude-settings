# section 14800
FAMILY = "push-target-named"

# RULE push-target-named (brief-names-push-target). An agent's `git push` is judged against the `Push to:` line of its
# own brief: the first user record of the agent's own transcript, which s14736's agent_transcript names beside the main
# transcript. A line that starts, after markdown lead characters and spaces, with `Push to:` names the one branch the
# agent may push to, or `none`. The first line with a real value decides: a placeholder line (`<branch>`) is skipped. A
# line inside a fence or in backticks does not count. Only
# a payload with a valid agent_id is judged: a top-level push and a dry run are not. The fixtures reuse the agent-file
# writer of s14736 (write_agent_transcripts), the one home of that layout.
PUSH_TARGET_RULE = "push-target-named"
PUSH_TARGET_AGENT = "b2f4c6d8e0a1b3c5d"  # an agent id as the harness sends it: 17 hex characters
PUSH_TARGET_NO_TARGET = "names no push target"  # the remedy a refusal prints for a brief that holds no real target
PUSH_NONE_REMEDY = "pushes nothing"  # the fragment a refusal for a none brief prints, and no other refusal prints
LONG_BRIEF = "".join("Context line %d, not a push line.\n" % i for i in range(400))  # full size: 400 lines before the target
PUSH_TARGET_FIXTURES = []


def pt_fixture(name, agents):
    """Register an AGENT_FIXTURES entry for the shared writer. `agents` is a list of (agent_id, texts): each text is one
    user record of that agent's file, in order. Texts None makes the file a folder (unreadable); texts [] makes it empty;
    an empty list of agents leaves no agent file at all."""
    AGENT_FIXTURES[name] = (AGENT_QUIET, [(agent, None if texts is None else [role_said(t) for t in texts])
                                          for agent, texts in agents])
    PUSH_TARGET_FIXTURES.append(name)


def pt_one(text):
    """The agent file of PUSH_TARGET_AGENT: its brief is one user record holding `text`. A list of blocks is the
    record's content as given: role_said writes a list as it is, and agent_brief_text joins its text blocks, one per line."""
    return [(PUSH_TARGET_AGENT, [text])]


def pt_blocks(*parts):
    """The content of a user record that is a list of text blocks, the shape a message of several parts takes."""
    return [{"type": "text", "text": part} for part in parts]


pt_fixture("pt-none", pt_one("Push to: none\n\nTask: report only."))
pt_fixture("pt-lane-x", pt_one("# Brief\n\nPush to: lane-x\n\nTask: push the lane."))
pt_fixture("pt-origin-prefix", pt_one("Push to: origin/lane-x\n\nTask: push."))
pt_fixture("pt-quote-lead", pt_one("> Push to: lane-x\n\nTask: push."))
pt_fixture("pt-heading-lead", pt_one("## Push to: lane-x\n\nTask: push."))
pt_fixture("pt-full-size", pt_one(LONG_BRIEF + "Push to: lane-x\n"))
pt_fixture("pt-fence-decoy", pt_one("```\nPush to: lane-y\n```\n\nPush to: lane-x\n"))
pt_fixture("pt-lone-backtick", pt_one("Use the ` character in the path.\nPush to: lane-x\n"))
pt_fixture("pt-fence-only", pt_one("Task.\n\n```\nPush to: lane-x\n```\n"))
pt_fixture("pt-inline-only", pt_one("Task.\n\n`Push to: lane-x`\n"))
pt_fixture("pt-mid-line", pt_one("Task. Push to: lane-x here.\n"))
pt_fixture("pt-two-lines", pt_one("Push to: lane-x\nPush to: lane-y\n"))
pt_fixture("pt-none-then-x", pt_one("Push to: none\nPush to: lane-x\n"))
pt_fixture("pt-placeholder", pt_one("Push to: <branch>\n"))
pt_fixture("pt-no-line", pt_one("# Brief\n\nTask: report only, push nothing.\n"))
pt_fixture("pt-second-record", [(PUSH_TARGET_AGENT, ["Task: report only.", "Push to: lane-x"])])
pt_fixture("pt-empty-file", [(PUSH_TARGET_AGENT, [])])
pt_fixture("pt-no-agent-file", [])
pt_fixture("pt-agent-folder", [(PUSH_TARGET_AGENT, None)])
# A value read without its code ticks, a trailing full stop or a refs/heads/ prefix. pt-origin-prefix is the origin/
# spelling.
pt_fixture("pt-tick-value", pt_one("Push to: `lane-x`\n\nTask: push."))
pt_fixture("pt-dot-value", pt_one("Push to: lane-x.\n\nTask: push."))
pt_fixture("pt-refs-value", pt_one("Push to: refs/heads/lane-x\n\nTask: push."))
# The value is the first whitespace-delimited word after Push to:, with backticks, asterisks, underscores, full stops,
# commas, semicolons and parentheses stripped from both ends. The words after it are a note, not the value.
pt_fixture("pt-paren-note", pt_one("Push to: lane-x (the lane branch)\n\nTask: push."))
pt_fixture("pt-none-note", pt_one("Push to: none (report only)\n\nTask: report only."))
pt_fixture("pt-wrapped-value", pt_one("Push to: (lane-x);\n\nTask: push."))
pt_fixture("pt-bold-value", pt_one("**Push to: lane-x**\n\nTask: push."))
pt_fixture("pt-underscore-value", pt_one("_Push to: lane-x_\n\nTask: push."))
pt_fixture("pt-tick-dot-value", pt_one("Push to: `lane-x`.\n\nTask: push."))
pt_fixture("pt-comma-value", pt_one("Push to: lane-x, then none\n\nTask: push."))
pt_fixture("pt-placeholder-note", pt_one("Push to: <branch> (name it)\n\nTask: push."))
# The stars after the colon are markup, so the value is the word after them.
pt_fixture("pt-bold-colon", pt_one("**Push to:** lane-x\n\nTask: push."))
# A placeholder line is skipped, indented or not, and the real line below it decides.
pt_fixture("pt-placeholder-then-x", pt_one("Push to: <branch>\nPush to: lane-x\n"))
pt_fixture("pt-indented-placeholder-then-x", pt_one("    Push to: <branch>\nPush to: lane-x\n"))
pt_fixture("pt-indented-placeholder", pt_one("    Push to: <branch>\n"))
# A brief that names the branch PUSHFEAT sits on, for a plain --tags push.
pt_fixture("pt-feat", pt_one("Push to: feat\n\nTask: push."))
# A brief held as a list of text blocks, and one whose only block is not text.
pt_fixture("pt-blocks-lane-x", pt_one(pt_blocks("# Brief", "Push to: lane-x", "Task: push.")))
pt_fixture("pt-blocks-no-text", pt_one([{"type": "tool_result", "tool_use_id": "t1", "content": "Push to: lane-x"}]))
# The brief-names-push-target re-point: the existing agent pushes of s21304, s22868 and s23264 send `git push origin work`,
# and each agent's brief names `work`, so they stay allowed once the rule is built. One file for the four agent ids.
pt_fixture("pt-repoint", [("auth1", ["Push to: work"]), ("rw1", ["Push to: work"]), ("bld1", ["Push to: work"]),
                          ("dz1", ["Push to: work"])])
PUSH_TARGET_REPOINT = role_path("pt-repoint")
lazy_fixture([role_path(name) for name in PUSH_TARGET_FIXTURES], write_agent_transcripts)


def pt_case(name, command, expected, fixture=None, rule=None, cwd=PUSHFEAT, carries=(), lacks=(), silent=False):
    """One `git push` (or other call) by PUSH_TARGET_AGENT, whose transcript is the fixture `fixture`. None names no
    transcript at all, so the payload carries no transcript_path."""
    sh(name, command, expected, rule, cwd=cwd, agent_id=PUSH_TARGET_AGENT,
       transcript=role_path(fixture) if fixture else None, carries=carries, lacks=lacks, silent=silent)


# ALLOW, the controls. A matching brief, its spellings and lead characters, a brief whose line sits far down, a fence or a
# lone backtick before the real line, the first of two lines, a dry run, a call that is not a push, a top-level push and
# an agent_type with no agent_id. Each is silent: the rule adds no line to a push it lets through.
pt_case("push-target-named: a matching Push to: line allows the agent's push",
        VCS + " push origin HEAD:lane-x", "allow", "pt-lane-x", silent=True)
pt_case("push-target-named: a refs/heads spelling of the matching branch allows the push",
        VCS + " push origin HEAD:refs/heads/lane-x", "allow", "pt-lane-x", silent=True)
pt_case("push-target-named: an origin/ prefix in the Push to: line names the same branch",
        VCS + " push origin HEAD:lane-x", "allow", "pt-origin-prefix", silent=True)
pt_case("push-target-named: a quote lead before Push to: is a Push to: line",
        VCS + " push origin HEAD:lane-x", "allow", "pt-quote-lead", silent=True)
pt_case("push-target-named: a heading lead before Push to: is a Push to: line",
        VCS + " push origin HEAD:lane-x", "allow", "pt-heading-lead", silent=True)
pt_case("push-target-named: a Push to: line 400 lines down a brief still decides",
        VCS + " push origin HEAD:lane-x", "allow", "pt-full-size", silent=True)
pt_case("push-target-named: a fenced Push to: line does not count, the real line after it decides",
        VCS + " push origin HEAD:lane-x", "allow", "pt-fence-decoy", silent=True)
pt_case("push-target-named: a lone backtick earlier in the brief does not hide the Push to: line",
        VCS + " push origin HEAD:lane-x", "allow", "pt-lone-backtick", silent=True)
pt_case("push-target-named: the first of two Push to: lines allows a push to its branch",
        VCS + " push origin HEAD:lane-x", "allow", "pt-two-lines", silent=True)
pt_case("push-target-named: a dry run is not judged under a none brief",
        VCS + " push -n origin HEAD:lane-y", "allow", "pt-none", silent=True)
pt_case("push-target-named: a --dry-run is not judged under a none brief",
        VCS + " push --dry-run origin HEAD:lane-y", "allow", "pt-none", silent=True)
pt_case("push-target-named: a git status call by the agent is not a push",
        VCS + " status", "allow", "pt-none", silent=True)
sh("push-target-named: a top-level push with no agent_id is not judged, though its transcript names none",
   VCS + " push origin HEAD:lane-y", "allow", cwd=PUSHFEAT, transcript=role_path("pt-none"), silent=True)
sh("push-target-named: an agent_type with no agent_id is not judged, though its transcript names none",
   VCS + " push origin HEAD:lane-y", "allow", cwd=PUSHFEAT, agent_type="builder",
   transcript=role_path("pt-none"), silent=True)
# The force verdict stands where it already refuses: the new rule does not replace force-push's refusal.
pt_case("push-target-named: a forced push under a none brief keeps its force-push refusal",
        VCS + " push --force origin HEAD:lane-y", "deny", "pt-none", rule="force-push", lacks=(PUSH_TARGET_RULE,))
pt_case("push-target-named: a forced push to another branch keeps force-push, not the brief's refusal",
        VCS + " push --force origin HEAD:lane-y", "deny", "pt-lane-x", rule="force-push", lacks=(PUSH_TARGET_RULE,))

# DENY, rule push-target-named. Each names the destination it refuses, and the refusal never names that destination.
# A refusal for a brief that names a target must not claim the brief names none: that fragment is `lacks`, so a fixture that
# was never read cannot pass as a refusal for a mismatch. A refusal for a brief with no real target carries the remedy.
pt_case("push-target-named: a none brief refuses the agent's push", VCS + " push origin HEAD:lane-y", "deny",
        "pt-none", rule=PUSH_TARGET_RULE, lacks=("lane-y", PUSH_TARGET_NO_TARGET))
pt_case("push-target-named: a push to a branch the brief does not name is refused",
        VCS + " push origin HEAD:lane-y", "deny", "pt-lane-x", rule=PUSH_TARGET_RULE,
        lacks=("lane-y", PUSH_TARGET_NO_TARGET))
pt_case("push-target-named: two refspecs, one to a branch the brief does not name, are refused",
        VCS + " push origin HEAD:lane-x HEAD:lane-y", "deny", "pt-lane-x", rule=PUSH_TARGET_RULE,
        lacks=("lane-y", PUSH_TARGET_NO_TARGET))
pt_case("push-target-named: a second push in a chain to another branch is refused",
        VCS + " push origin HEAD:lane-x && " + VCS + " push origin HEAD:lane-y", "deny", "pt-lane-x",
        rule=PUSH_TARGET_RULE, lacks=("lane-y", PUSH_TARGET_NO_TARGET))
pt_case("push-target-named: a push to another branch inside bash -c is refused",
        "bash -c '" + VCS + " push origin HEAD:lane-y'", "deny", "pt-lane-x", rule=PUSH_TARGET_RULE,
        lacks=("lane-y", PUSH_TARGET_NO_TARGET))
pt_case("push-target-named: a fenced decoy does not allow a push to its branch, the real line names another",
        VCS + " push origin HEAD:lane-y", "deny", "pt-fence-decoy", rule=PUSH_TARGET_RULE,
        lacks=("lane-y", PUSH_TARGET_NO_TARGET))
pt_case("push-target-named: a glob destination is refused under a matching brief",
        VCS + " push origin 'refs/heads/*:refs/heads/*'", "deny", "pt-lane-x", rule=PUSH_TARGET_RULE,
        lacks=(PUSH_TARGET_NO_TARGET,))
pt_case("push-target-named: a destination that cannot be resolved (a detached HEAD) is refused under a matching brief",
        VCS + " push origin HEAD", "deny", "pt-lane-x", rule=PUSH_TARGET_RULE, cwd=PUSHDETACHED,
        lacks=(PUSH_TARGET_NO_TARGET,))
pt_case("push-target-named: the first Push to: line decides, so a push to the second line's branch is refused",
        VCS + " push origin HEAD:lane-y", "deny", "pt-two-lines", rule=PUSH_TARGET_RULE,
        lacks=("lane-y", PUSH_TARGET_NO_TARGET))
pt_case("push-target-named: a none line first decides, so a push to the later branch is refused",
        VCS + " push origin HEAD:lane-x", "deny", "pt-none-then-x", rule=PUSH_TARGET_RULE,
        lacks=("lane-x", PUSH_TARGET_NO_TARGET))
pt_case("push-target-named: a placeholder Push to: line names no target and is refused, with the remedy",
        VCS + " push origin HEAD:lane-y", "deny", "pt-placeholder", rule=PUSH_TARGET_RULE,
        carries=(PUSH_TARGET_NO_TARGET,), lacks=("lane-y",))
pt_case("push-target-named: a brief with no Push to: line is refused, with the remedy",
        VCS + " push origin HEAD:lane-x", "deny", "pt-no-line", rule=PUSH_TARGET_RULE,
        carries=(PUSH_TARGET_NO_TARGET,), lacks=("lane-x",))
pt_case("push-target-named: a Push to: line only inside a fence does not count, so the push is refused",
        VCS + " push origin HEAD:lane-x", "deny", "pt-fence-only", rule=PUSH_TARGET_RULE,
        carries=(PUSH_TARGET_NO_TARGET,), lacks=("lane-x",))
pt_case("push-target-named: a Push to: line only in inline backticks does not count, so the push is refused",
        VCS + " push origin HEAD:lane-x", "deny", "pt-inline-only", rule=PUSH_TARGET_RULE,
        carries=(PUSH_TARGET_NO_TARGET,), lacks=("lane-x",))
pt_case("push-target-named: Push to: after other words on a line does not count, so the push is refused",
        VCS + " push origin HEAD:lane-x", "deny", "pt-mid-line", rule=PUSH_TARGET_RULE,
        carries=(PUSH_TARGET_NO_TARGET,), lacks=("lane-x",))
pt_case("push-target-named: only the first user record of the agent's transcript is the brief",
        VCS + " push origin HEAD:lane-x", "deny", "pt-second-record", rule=PUSH_TARGET_RULE,
        carries=(PUSH_TARGET_NO_TARGET,), lacks=("lane-x",))
pt_case("push-target-named: an empty agent transcript holds no brief and the push is refused",
        VCS + " push origin HEAD:lane-x", "deny", "pt-empty-file", rule=PUSH_TARGET_RULE,
        carries=(PUSH_TARGET_NO_TARGET,), lacks=("lane-x",))
pt_case("push-target-named: a missing agent transcript leaves the push with no brief, so it is refused",
        VCS + " push origin HEAD:lane-x", "deny", "pt-no-agent-file", rule=PUSH_TARGET_RULE,
        carries=(PUSH_TARGET_NO_TARGET,), lacks=("lane-x",))
pt_case("push-target-named: an unreadable agent transcript, a folder, leaves the push with no brief, so it is refused",
        VCS + " push origin HEAD:lane-x", "deny", "pt-agent-folder", rule=PUSH_TARGET_RULE,
        carries=(PUSH_TARGET_NO_TARGET,), lacks=("lane-x",))
pt_case("push-target-named: a payload with no transcript_path leaves the push with no brief, so it is refused",
        VCS + " push origin HEAD:lane-x", "deny", None, rule=PUSH_TARGET_RULE,
        carries=(PUSH_TARGET_NO_TARGET,), lacks=("lane-x",))

# A value is read without its code ticks, a trailing full stop or a refs/heads/ prefix, as an origin/ prefix already is. Each
# spelling allows a push to its branch, and each refuses a push to another. The allow is the red; the refusal is its control.
pt_case("push-target-named: a backticked Push to: value allows a push to its branch",
        VCS + " push origin HEAD:lane-x", "allow", "pt-tick-value", silent=True)
pt_case("push-target-named: a backticked Push to: value refuses a push to another branch",
        VCS + " push origin HEAD:lane-y", "deny", "pt-tick-value", rule=PUSH_TARGET_RULE,
        lacks=("lane-y", PUSH_TARGET_NO_TARGET))
pt_case("push-target-named: a Push to: value with a trailing full stop allows a push to its branch",
        VCS + " push origin HEAD:lane-x", "allow", "pt-dot-value", silent=True)
pt_case("push-target-named: a Push to: value with a trailing full stop refuses a push to another branch",
        VCS + " push origin HEAD:lane-y", "deny", "pt-dot-value", rule=PUSH_TARGET_RULE,
        lacks=("lane-y", PUSH_TARGET_NO_TARGET))
pt_case("push-target-named: a refs/heads/ Push to: value allows a push to its branch",
        VCS + " push origin HEAD:lane-x", "allow", "pt-refs-value", silent=True)
pt_case("push-target-named: a refs/heads/ Push to: value refuses a push to another branch",
        VCS + " push origin HEAD:lane-y", "deny", "pt-refs-value", rule=PUSH_TARGET_RULE,
        lacks=("lane-y", PUSH_TARGET_NO_TARGET))
pt_case("push-target-named: an origin/ Push to: value refuses a push to another branch",
        VCS + " push origin HEAD:lane-y", "deny", "pt-origin-prefix", rule=PUSH_TARGET_RULE,
        lacks=("lane-y", PUSH_TARGET_NO_TARGET))

# The first word after Push to: is the value, with its edges stripped. Each allow reads a value the rule must strip; each
# refusal beside one is its control.
pt_case("push-target-named: a Push to: value with a note in parentheses allows a push to the branch before the note",
        VCS + " push origin HEAD:lane-x", "allow", "pt-paren-note", silent=True)
pt_case("push-target-named: a Push to: value with a note in parentheses refuses a push to another branch",
        VCS + " push origin HEAD:lane-y", "deny", "pt-paren-note", rule=PUSH_TARGET_RULE,
        lacks=("lane-y", PUSH_TARGET_NO_TARGET, PUSH_NONE_REMEDY))
pt_case("push-target-named: a none value with a note in parentheses refuses the push with the none remedy",
        VCS + " push origin HEAD:lane-y", "deny", "pt-none-note", rule=PUSH_TARGET_RULE,
        carries=(PUSH_NONE_REMEDY,), lacks=("lane-y", PUSH_TARGET_NO_TARGET))
pt_case("push-target-named: a Push to: value in parentheses before a semicolon allows a push to its branch",
        VCS + " push origin HEAD:lane-x", "allow", "pt-wrapped-value", silent=True)
pt_case("push-target-named: a Push to: value in parentheses before a semicolon refuses a push to another branch",
        VCS + " push origin HEAD:lane-y", "deny", "pt-wrapped-value", rule=PUSH_TARGET_RULE,
        lacks=("lane-y", PUSH_TARGET_NO_TARGET, PUSH_NONE_REMEDY))
pt_case("push-target-named: a Push to: value wrapped in bold stars allows a push to its branch",
        VCS + " push origin HEAD:lane-x", "allow", "pt-bold-value", silent=True)
pt_case("push-target-named: a Push to: value wrapped in bold stars refuses a push to another branch",
        VCS + " push origin HEAD:lane-y", "deny", "pt-bold-value", rule=PUSH_TARGET_RULE,
        lacks=("lane-y", PUSH_TARGET_NO_TARGET, PUSH_NONE_REMEDY))
pt_case("push-target-named: a Push to: value wrapped in underscores allows a push to its branch",
        VCS + " push origin HEAD:lane-x", "allow", "pt-underscore-value", silent=True)
pt_case("push-target-named: a Push to: value wrapped in underscores refuses a push to another branch",
        VCS + " push origin HEAD:lane-y", "deny", "pt-underscore-value", rule=PUSH_TARGET_RULE,
        lacks=("lane-y", PUSH_TARGET_NO_TARGET, PUSH_NONE_REMEDY))
pt_case("push-target-named: a backticked Push to: value with a trailing full stop allows a push to its branch",
        VCS + " push origin HEAD:lane-x", "allow", "pt-tick-dot-value", silent=True)
pt_case("push-target-named: a backticked Push to: value with a trailing full stop refuses a push to another branch",
        VCS + " push origin HEAD:lane-y", "deny", "pt-tick-dot-value", rule=PUSH_TARGET_RULE,
        lacks=("lane-y", PUSH_TARGET_NO_TARGET, PUSH_NONE_REMEDY))
pt_case("push-target-named: a comma list's first word decides, so a push to it is allowed",
        VCS + " push origin HEAD:lane-x", "allow", "pt-comma-value", silent=True)
pt_case("push-target-named: a comma list's later word is no value, so a push to another branch is no none refusal",
        VCS + " push origin HEAD:lane-y", "deny", "pt-comma-value", rule=PUSH_TARGET_RULE,
        lacks=("lane-y", PUSH_TARGET_NO_TARGET, PUSH_NONE_REMEDY))
pt_case("push-target-named: a placeholder first word with a note after it is skipped, so the push gets the remedy",
        VCS + " push origin HEAD:lane-x", "deny", "pt-placeholder-note", rule=PUSH_TARGET_RULE,
        carries=(PUSH_TARGET_NO_TARGET,), lacks=("lane-x",))

# The stars after the colon are markup, so a bold colon names its branch.
pt_case("push-target-named: a bold **Push to:** line names its branch, so a push to it is allowed",
        VCS + " push origin HEAD:lane-x", "allow", "pt-bold-colon", silent=True)
pt_case("push-target-named: a bold **Push to:** line refuses a push to another branch, without the no-target remedy",
        VCS + " push origin HEAD:lane-y", "deny", "pt-bold-colon", rule=PUSH_TARGET_RULE,
        lacks=("lane-y", PUSH_TARGET_NO_TARGET))

# The push-main ask is pending when this step runs, so the deny is the verdict: a brief that names another branch refuses
# a push to main, and does not ask.
pt_case("push-target-named: a non-forced push to main under a brief naming another branch is refused, not asked",
        VCS + " push origin HEAD:main", "deny", "pt-lane-x", rule=PUSH_TARGET_RULE,
        lacks=("main", PUSH_TARGET_NO_TARGET, PUSH_NONE_REMEDY))

# A placeholder line is skipped, indented or not. The real line below it decides, so a refusal for another branch names a
# mismatch, never a brief with no target.
pt_case("push-target-named: a placeholder Push to: line is skipped, so the real line below it allows its branch",
        VCS + " push origin HEAD:lane-x", "allow", "pt-placeholder-then-x", silent=True)
pt_case("push-target-named: an indented placeholder line is skipped, so the real line below it allows its branch",
        VCS + " push origin HEAD:lane-x", "allow", "pt-indented-placeholder-then-x", silent=True)
pt_case("push-target-named: a placeholder line is skipped, so the real line below it refuses another branch",
        VCS + " push origin HEAD:lane-y", "deny", "pt-placeholder-then-x", rule=PUSH_TARGET_RULE,
        lacks=("lane-y", PUSH_TARGET_NO_TARGET))
pt_case("push-target-named: an indented placeholder line is skipped, so the real line below it refuses another branch",
        VCS + " push origin HEAD:lane-y", "deny", "pt-indented-placeholder-then-x", rule=PUSH_TARGET_RULE,
        lacks=("lane-y", PUSH_TARGET_NO_TARGET))
pt_case("push-target-named: an indented placeholder with no real line below it is refused, with the remedy",
        VCS + " push origin HEAD:lane-x", "deny", "pt-indented-placeholder", rule=PUSH_TARGET_RULE,
        carries=(PUSH_TARGET_NO_TARGET,), lacks=("lane-x",))

# A --tags push sends every tag to origin, so no branch a brief names covers it. A plain --tags push is refused under
# any brief.
pt_case("push-target-named: a --tags push to the brief's own branch is refused, since every tag reaches origin",
        VCS + " push --tags origin HEAD:lane-x", "deny", "pt-lane-x", rule=PUSH_TARGET_RULE,
        lacks=("lane-x", PUSH_TARGET_NO_TARGET))
pt_case("push-target-named: a plain --tags push under a brief naming the current branch is refused",
        VCS + " push --tags origin", "deny", "pt-feat", rule=PUSH_TARGET_RULE, lacks=(PUSH_TARGET_NO_TARGET,))
pt_case("push-target-named: a plain --tags push with no remote is refused under a brief naming another branch",
        VCS + " push --tags", "deny", "pt-lane-x", rule=PUSH_TARGET_RULE, lacks=(PUSH_TARGET_NO_TARGET,))
pt_case("push-target-named: a plain --tags push under a none brief is refused, as every push is",
        VCS + " push --tags origin", "deny", "pt-none", rule=PUSH_TARGET_RULE, lacks=(PUSH_TARGET_NO_TARGET,))
pt_case("push-target-named: a plain --tags push under a brief with no line is refused, with the remedy",
        VCS + " push --tags origin", "deny", "pt-no-line", rule=PUSH_TARGET_RULE, carries=(PUSH_TARGET_NO_TARGET,))

# A brief held as a list of text blocks is read as the text of its blocks, one per line. A block that is not text is
# no brief.
pt_case("push-target-named: a brief held as a list of text blocks allows a push to the branch its Push to: line names",
        VCS + " push origin HEAD:lane-x", "allow", "pt-blocks-lane-x", silent=True)
pt_case("push-target-named: a brief held as a list of text blocks refuses a push to another branch",
        VCS + " push origin HEAD:lane-y", "deny", "pt-blocks-lane-x", rule=PUSH_TARGET_RULE,
        lacks=("lane-y", PUSH_TARGET_NO_TARGET))
pt_case("push-target-named: a list with no text block is no brief, so the push is refused with the remedy",
        VCS + " push origin HEAD:lane-x", "deny", "pt-blocks-no-text", rule=PUSH_TARGET_RULE,
        carries=(PUSH_TARGET_NO_TARGET,), lacks=("lane-x",))
