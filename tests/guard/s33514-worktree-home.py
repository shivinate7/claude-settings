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
LOG_CHECKS_EXTRA.append(("worktree-home: orchestrator, no-record, home, outside-home, edit, read, removed-home, "
                         "unreadable", worktree_home_case))
LOG_CHECKS_EXTRA.append(("worktree-home: any session's write into another checkout of its clone is refused; outside "
                         "the clone and its own checkout pass", worktree_home_cross_checkout_case))
LOG_CHECKS_EXTRA.append(("worktree-home: a write into a worktree in the session's own scratchpad is allowed; another "
                         "session's, an agent's, a sessionless, a symlinked and a climbing write are refused",
                         worktree_home_scratchpad_case))
LOG_CHECKS_EXTRA.append(("worktree-home: an owner override lifts the cross-checkout refusal",
                         worktree_home_cross_checkout_override_case))
LOG_CHECKS_EXTRA.append(("worktree-home: the cross-checkout read costs one git spawn per write call and none otherwise",
                         worktree_home_cross_checkout_cost_case))
LOG_CHECKS_EXTRA.append(("worktree-home: a cd into another checkout of the clone is refused, bare or chained to a build, "
                         "a write or a mkdir, from a lane or the primary, and names no path",
                         worktree_home_cd_into_other_checkout_case))
LOG_CHECKS_EXTRA.append(("worktree-home: the other-checkout refusal names the EnterWorktree call with `path` for a write "
                         "and for a cd, and names neither `cd` nor env -C as a route",
                         worktree_home_other_checkout_remedy_case))
LOG_CHECKS_EXTRA.append(("worktree-home: a cd into another checkout is refused when it is a relative climb, a subshell or "
                         "a PowerShell Set-Location", worktree_home_cd_parse_forms_case))
LOG_CHECKS_EXTRA.append(("worktree-home: an agent's cd into a sibling agent tree, or into a folder that only starts with "
                         "its id, is refused", worktree_home_cd_agent_sibling_case))
LOG_CHECKS_EXTRA.append(("worktree-home: a cd to a checkout's own root or subfolder, a folder outside the clone, or the "
                         "clone's .git passes", worktree_home_cd_allowed_case))
LOG_CHECKS_EXTRA.append(("worktree-home: the cd exemptions pass: an agent's recorded home from outside it, its own red-run "
                         "folder, a session's recorded home", worktree_home_cd_exempt_case))
LOG_CHECKS_EXTRA.append(("worktree-home: an agent's write into its own red-run folder, by a cd chained to it, a cp, a Write "
                         "or an Edit, is allowed; the same writes into a sibling's red-run folder, a prefix-named folder, "
                         "the primary, or with no agent_id are refused", worktree_home_red_write_case))
LOG_CHECKS_EXTRA.append(("worktree-home: the own red-run folder's root is refused to rm, mv and a Write, and a cp into it "
                         "or a write inside it passes", worktree_home_red_root_case))
LOG_CHECKS_EXTRA.append(("worktree-home: a red-run folder nested under another linked worktree, not the primary's, is "
                         "refused to a cd, a shell write and a Write", worktree_home_red_nested_case))
LOG_CHECKS_EXTRA.append(("worktree-home: a write into the own red-run folder spelled in other letters of case passes on "
                         "Windows, and is a skip elsewhere", worktree_home_red_case_fold_case))
LOG_CHECKS_EXTRA.append(("worktree-home: a cd in a comment, in quotes or in a heredoc body is text, and a real cd after one "
                         "is refused", worktree_home_cd_text_case))
LOG_CHECKS_EXTRA.append(("worktree-home: an owner override lifts a bare cd into another checkout",
                         worktree_home_cd_override_case))
LOG_CHECKS_EXTRA.append(("worktree-home: any session's write into another checkout is refused after a cd the cd act "
                         "passes, when the write resolves against that cd's folder", worktree_home_cd_then_write_case))
LOG_CHECKS_EXTRA.append(("worktree-home: an absolute cd into another checkout is refused after an untracked move, a cd - "
                         "or a missing folder; a relative cd after a missing folder is a declared limit, and ordinary work "
                         "from a worktree root allows", worktree_home_cd_after_untracked_case))
LOG_CHECKS_EXTRA.append(("worktree-home: pushd into another checkout is refused, bare or chained; a pushd within the "
                         "cwd's own checkout, or outside the clone, passes", worktree_home_pushd_case))
LOG_CHECKS_EXTRA.append(("worktree-home: a later path field outside the recorded home is refused, not skipped",
                         worktree_home_later_field_case))
LOG_CHECKS_EXTRA.append(("worktree-home: a lone cd or Set-Location into the recorded home is allowed from outside "
                         "it, in Windows or POSIX form", worktree_home_lone_cd_case))
LOG_CHECKS_EXTRA.append(("worktree-home: a cd or Set-Location into the home chained with another step is still denied",
                         worktree_home_chained_case))
LOG_CHECKS_EXTRA.append(("worktree-home: a /c/ cwd inside the home is inside, and the same form outside it is denied",
                         worktree_home_posix_cwd_case))
LOG_CHECKS_EXTRA.append(("worktree-home: a cd or Set-Location outside the home, or to its suffixed sibling, is denied",
                         worktree_home_cd_out_case))
LOG_CHECKS_EXTRA.append(("worktree-home: a lone move with a separator is refused, quoted or not",
                         worktree_home_quoted_move_case))
LOG_CHECKS_EXTRA.append(("worktree-home: sl, chdir and set-location are not moves in Bash",
                         worktree_home_bash_alias_case))
LOG_CHECKS_EXTRA.append(("worktree-home: the merge rule reads a /c/ cwd as main does", worktree_home_cwd_merge_case))
LOG_CHECKS_EXTRA.append(("worktree-home: the shared-tree rule reads a /c/ cwd as main does",
                         worktree_home_cwd_shared_tree_case))
LOG_CHECKS_EXTRA.append(("worktree-home: the builder test-edit rule reads a /c/ cwd as main does",
                         worktree_home_cwd_builder_case))
LOG_CHECKS_EXTRA.append(("worktree-home: the frozen-path rule reads a /c/ cwd as main does",
                         worktree_home_cwd_frozen_case))
LOG_CHECKS_EXTRA.append(("worktree-home: the config-edit rule reads a /c/ cwd as main does",
                         worktree_home_cwd_config_case))
LOG_CHECKS_EXTRA.append(("worktree-home: the agent cap rule reads a /c/ cwd as main does", worktree_home_cwd_cap_case))
LOG_CHECKS_EXTRA.append(("worktree-home: a builder write to a test file from a /c/ cwd in a repository is refused "
                         "off Windows", worktree_home_cwd_builder_refuse_case))
LOG_CHECKS_EXTRA.append(("worktree-home: a builder write to product code from a /c/ cwd in a repository is allowed "
                         "off Windows", worktree_home_cwd_builder_src_case))
LOG_CHECKS_EXTRA.append(("worktree-home: a builder write to a path in no repository from a /c/ cwd is allowed "
                         "off Windows", worktree_home_cwd_builder_scratch_case))
