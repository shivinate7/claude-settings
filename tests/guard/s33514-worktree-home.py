# section 33514
FAMILY = "worktree-home"
LOG_CHECKS_EXTRA.append(("worktree-home: a relative cd from a variable folder into another checkout is "
                         "refused, as from a literal folder", worktree_home_cd_variable_climb_case))


# =========================================================================== session-home
#
# Rule session-home: a session whose linked worktree is gone may not write into the primary
# checkout. The record is `<primary>/.git/session-homes/<session_id>`, one file per session. It
# holds the worktree path, and a top-level call (no agent_id) from inside
# `<primary>/.claude/worktrees/<name>` writes it when it is missing or differs. That session's
# ExitWorktree deletes it. An agent shares its session's id, so an agent call never writes or
# deletes the record. The rule reads the path shape and walks the folders up for `.git`: no git read.
