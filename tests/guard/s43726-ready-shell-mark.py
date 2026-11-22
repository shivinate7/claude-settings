# section 43726
FAMILY = "ready-mcp-mark-guard"
#
# `ready-mcp-mark-guard`, the shell form. The rule that section 43724 pins for the MCP update tool also reads the shell
# `gh pr ready` (Bash or PowerShell, without --undo): a ready mark is allowed only when this session's transcript shows a
# `merge <pr> --ready` run that passed its ready checks on the pull request's current head. Both forms pass
# ready_page_calls, the one parser of a ready mark, so a shell form counts as a mark exactly where records-page-ready counts it.
#
# THE FIXTURE. Section 43724's, unchanged: the records-page-ready repo, GHREADY_CURRENT (feat-current, whose records page
# is current, so records-page-ready allows the mark and the verdict comes from this rule alone) and its RPM_* transcripts.
# This section builds no transcript. RPM_NO_PASS holds no pass, RPM_OLD_PASS a pass on feat-current^, RPM_PASS a pass on feat-current.
#
# SELECTOR. A shell selector may be a number, a branch or a URL. The rule resolves a non-numeric one through Host.pr_number
# only when the transcript holds a pass to compare (with no stood sha it refuses with no head read, and the remedy then reads
# `merge <pr> --ready`). So each non-numeric case pairs a transcript with a pass on an older head (a deny that names
# `merge 12 --ready`, so the selector resolved to 12) with one on the current head (an allow). A deny and an allow on the same
# selector show that the allow comes from the head tie and not from a selector the rule could not read.

RSM_PREFIX = "ready-shell-mark: "
RSM_URL = "https://github.com/y/x/pull/12"      # the same pull request, named by URL
RSM_BRANCH = "feat-current"                     # the same pull request, named by its head branch


def rsm_shell(name, command, expected, transcript, tool="Bash", carries=(), lacks=()):
    """One shell call judged in the records-page repo, with the transcript the case names. A deny must name RPM_RULE."""
    sh(RSM_PREFIX + name, command, expected, rule=RPM_RULE if expected == "deny" else None, tool=tool, cwd=RPR_REPO,
       env_path=_rpr_env(GHREADY_CURRENT), config=MERGECFG, transcript=transcript, carries=carries, lacks=lacks)


# Refused: the mark with no ready pass, and with a pass on an older head. The refusal names the ready run and never the mark.
rsm_shell("gh pr ready 12 with no ready pass in the transcript is refused", "gh pr ready 12", "deny", RPM_NO_PASS,
          carries=RPM_REMEDY, lacks=RPM_TARGET_LACKS)
rsm_shell("gh pr ready 12 after a ready pass on an older head is refused", "gh pr ready 12", "deny", RPM_OLD_PASS,
          carries=RPM_REMEDY, lacks=RPM_TARGET_LACKS)
rsm_shell("a PowerShell gh pr ready 12 with no ready pass is refused", "gh pr ready 12", "deny", RPM_NO_PASS,
          tool="PowerShell", carries=RPM_REMEDY, lacks=RPM_TARGET_LACKS)
# Allowed: the pass on the current head (the control of the refusals above), --undo, the ready run itself.
rsm_shell("gh pr ready 12 after a ready pass on the current head is allowed", "gh pr ready 12", "allow", RPM_PASS)
rsm_shell("gh pr ready 12 --undo with no ready pass is allowed", "gh pr ready 12 --undo", "allow", RPM_NO_PASS)
rsm_shell("merge 12 --ready itself with no ready pass is allowed", MERGE_SHIM + " 12 --ready", "allow", RPM_NO_PASS)
# A selector that is not a number: a branch and a URL resolve to #12, so each pair splits on the head alone.
rsm_shell("gh pr ready by branch after a ready pass on an older head is refused", "gh pr ready " + RSM_BRANCH, "deny", RPM_OLD_PASS,
          carries=RPM_REMEDY, lacks=RPM_TARGET_LACKS)
rsm_shell("gh pr ready by branch after a ready pass on the current head is allowed", "gh pr ready " + RSM_BRANCH, "allow", RPM_PASS)
rsm_shell("gh pr ready by URL after a ready pass on an older head is refused", "gh pr ready " + RSM_URL, "deny", RPM_OLD_PASS,
          carries=RPM_REMEDY, lacks=RPM_TARGET_LACKS)
rsm_shell("gh pr ready by URL after a ready pass on the current head is allowed", "gh pr ready " + RSM_URL, "allow", RPM_PASS)
# The ready run and the mark in one call: the transcript holds no result of that run yet, so the mark has no pass to stand on.
rsm_shell("merge 12 --ready chained with gh pr ready 12 in one call is refused", MERGE_SHIM + " 12 --ready && gh pr ready 12", "deny",
          RPM_NO_PASS, carries=RPM_REMEDY, lacks=RPM_TARGET_LACKS)
# False-alarm controls: text that holds the words and marks nothing ready. The one parser reads quotes, heredocs and comments.
rsm_shell("gh pr ready 12 in a comment is no mark", "echo ok # gh pr ready 12", "allow", RPM_NO_PASS)
rsm_shell("gh pr ready 12 on a line of a multi-line quoted string is no mark", 'echo "start\ngh pr ready 12\nend"', "allow", RPM_NO_PASS)
rsm_shell("gh pr ready 12 in a heredoc body is no mark", "cat <<'EOF'\ngh pr ready 12\nEOF", "allow", RPM_NO_PASS)
