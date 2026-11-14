# section 33355
FAMILY = "misc"  # this literal mixes several rules, so its log checks are not one family
LOG_CHECKS = (
    ("log: one line per refusal and none for an allow", log_case),
    ("log: the refused file is named in the log and nowhere else", log_env_case),
    ("log: a project config edit is allowed and noted", config_edit_log_case),
    ("log: a cap lift is asked and logged with its file and value", cap_log_case),
    ("log: a cap lift under a deep path still logs the model", cap_deep_path_log_case),
    ("cap: the printed reason is bounded, single-line and marks a cut", cap_reason_bound_case),
    ("trim: a guard crash fails open and logs a crash line", crash_log_case),
    ("merge-checks: a merge tool that cannot load is unknown, and denies", merge_tool_missing_case),
    ("merge-checks: a merge tool that exits at import is unknown or pending, and denies",
     merge_import_exits_case),
    ("cite-by-id: a -F file that cannot be read is denied with the folders unread too",
     cite_unread_folders_case),
    ("merge-checks: a gh that never answers still denies, well inside the hook's 60s budget",
     merge_hang_timeout_case),
    ("powershell: a backslash path survives tokenizing, a Bash one does not", powershell_backslash_case),
    ("wsl: a PowerShell script tag keeps its backslashes in segment_tokens", wsl_script_tag_keeps_backslash_case),
    ("wsl: a split segment keeps the PowerShell tag its script had", wsl_split_tag_keeps_backslash_case),
    ("log: an unreadable subject is allowed and noted", subject_unread_log_case),
    ("log: a hard reset in an agent-owned worktree is allowed and noted, not asked",
     agent_worktree_reset_noted_case),
    ("log: checkout -- in an agent-owned worktree is allowed and noted, not asked",
     agent_worktree_checkout_noted_case),
    ("log: an unforced worktree remove with an unreadable subject records no note",
     worktree_remove_plain_quiet_case),
    ("log: a forced worktree remove with an unreadable subject is still noted",
     worktree_remove_force_noted_case),
    ("log: a quoted or abbreviated force on a worktree remove is still noted",
     worktree_remove_force_forms_noted_case),
    ("log: a branch delete with no resolvable base is allowed and noted",
     branch_base_unread_log_case),
    ("stack: the refusal never names the action it refused", stack_reason_hygiene_case),
    ("playwright: the refusal names the stale __dirlock and pgrep, and no other path",
     playwright_remedy_case),
    ("hand-made worktree: the refusal text points to isolation and EnterWorktree, names no target",
     hand_made_refusal_text_case),
    ("hand-made worktree: the pointer remedy names EnterWorktree, not worktree add",
     pointer_remedy_names_enter_worktree_case),
    (HM_NAMED_LABEL, hand_made_named_red_path_case),
    (HM_NO_AGENT_LABEL, hand_made_no_agent_reason_case),
    (HM_BAD_ID_LABEL, hand_made_bad_agent_id_reason_case),
    ("split_segments: a comment starting a word ends its line, "
     "letter-before-# and quoted-# stay literal", split_segments_comment_case),
    ("env: heredoc-allow-strip: strip_heredoc_bodies keeps no body line of the incident cat write",
     incident_write_strip_case),
    ("liveness: process_start_ms splits alive/dead/unreadable apart", process_start_ms_case),
    ("liveness: process_start_ms reads a repeated-hour start (01:30 CDT) as its instant, in Chicago",
     process_start_ms_repeated_hour_cdt_case),
    ("liveness: process_start_ms reads a repeated-hour start (01:30 CST) as its instant, in Chicago",
     process_start_ms_repeated_hour_cst_case),
    ("liveness: windows arm splits dead (error 87) from unreadable (error 5)",
     process_start_ms_windows_case),
    ("liveness: session_is_live carries True/False/None, never coercing unreadable to False",
     session_is_live_case),
    ("liveness: session_is_live says True for a repeated-hour start (01:30 CDT) in Chicago",
     session_is_live_repeated_hour_cdt_case),
    ("liveness: session_is_live says True for a repeated-hour start (01:30 CST) in Chicago",
     session_is_live_repeated_hour_cst_case),
    ("liveness: worktree_live_session answers None on an unreadable record under target",
     worktree_live_session_unreadable_case),
    ("liveness: worktree_live_session matches two spellings of one identity as under target",
     worktree_live_session_two_spellings_case),
    ("liveness: worktree_live_session answers None when the identity fallback can't tell",
     worktree_live_session_path_unresolvable_case),
    ("liveness: session_is_live reads an implied backwards clock step as unreadable, not dead",
     session_is_live_backwards_clock_step_case),
    ("worktree-home: orchestrator, no-record, home, outside-home, edit, read, removed-home, "
     "unreadable", worktree_home_case),
    ("worktree-home: any session's write into another checkout of its clone is refused; outside "
     "the clone and its own checkout pass", worktree_home_cross_checkout_case),
    ("worktree-home: a copy whose source is in another checkout is allowed; a write into another "
     "checkout, from a copy or an interpreter body, is refused",
     worktree_home_cross_checkout_copy_case),
    ("worktree-home: a write into a worktree in the session's own scratchpad is allowed; another "
     "session's, an agent's, a sessionless, a symlinked and a climbing write are refused",
     worktree_home_scratchpad_case),
    ("worktree-home: an owner override lifts the cross-checkout refusal",
     worktree_home_cross_checkout_override_case),
    ("worktree-home: the cross-checkout read costs one git spawn per write call and none otherwise",
     worktree_home_cross_checkout_cost_case),
    ("roadmap-one-writer: a push starts one rev-parse, one more for a stray push, symbolic-ref for a refspec, "
     "HEAD and bare, push.default for bare only, one config read of the remote for a literal main destination, "
     "no read for HEAD:<branch>, a --all or glob push reads the remote's URL and its tracking refs, "
     "one rev-list for each pushed ref not to main or master, "
     "and reads the transcript only at the record branch",
     record_push_cost_case),
    ("conflict-markers: the cost probe judges a clean commit as no hit, under a stand-in git (the control)",
     cmk_cost_control_case),
    ("conflict-markers: git add -A && git commit -m x spawns one rev-parse, one diff --check and one ls-files",
     cmk_cost_add_commit_case),
    ("conflict-markers: git add -A alone spawns no git", cmk_cost_add_case),
    ("conflict-markers: git commit -m x spawns one rev-parse and one diff --check", cmk_cost_commit_case),
    ("worktree-home: a cd into another checkout of the clone is refused, bare or chained to a build, "
     "a write or a mkdir, from a lane or the primary, and names no path",
     worktree_home_cd_into_other_checkout_case),
    ("worktree-home: the other-checkout refusal names the EnterWorktree call with `path` for a write "
     "and for a cd, and names neither `cd` nor env -C as a route",
     worktree_home_other_checkout_remedy_case),
    ("worktree-home: a cd into another checkout is refused when it is a relative climb, a subshell or "
     "a PowerShell Set-Location", worktree_home_cd_parse_forms_case),
    ("worktree-home: an agent's cd into a sibling agent tree, or into a folder that only starts with "
     "its id, is refused", worktree_home_cd_agent_sibling_case),
    ("worktree-home: a cd to a checkout's own root or subfolder, a folder outside the clone, or the "
     "clone's .git passes", worktree_home_cd_allowed_case),
    ("worktree-home: the cd exemptions pass: an agent's recorded home from outside it, its own red-run "
     "folder, a session's recorded home", worktree_home_cd_exempt_case),
    ("worktree-home: an agent's write into its own red-run folder, by a cd chained to it, a cp, a Write "
     "or an Edit, is allowed; the same writes into a sibling's red-run folder, a prefix-named folder, "
     "the primary, or with no agent_id are refused", worktree_home_red_write_case),
    ("worktree-home: the own red-run folder's root is refused to rm, mv and a Write, and a cp into it "
     "or a write inside it passes", worktree_home_red_root_case),
    ("worktree-home: a red-run folder nested under another linked worktree, not the primary's, is "
     "refused to a cd, a shell write and a Write", worktree_home_red_nested_case),
    ("worktree-home: a write into the own red-run folder spelled in other letters of case passes on "
     "Windows, and is a skip elsewhere", worktree_home_red_case_fold_case),
    ("worktree-home: a cd in a comment, in quotes or in a heredoc body is text, and a real cd after one "
     "is refused", worktree_home_cd_text_case),
    ("worktree-home: an owner override lifts a bare cd into another checkout",
     worktree_home_cd_override_case),
    ("worktree-home: any session's write into another checkout is refused after a cd the cd act "
     "passes, when the write resolves against that cd's folder", worktree_home_cd_then_write_case),
    ("worktree-home: an absolute cd into another checkout is refused after an untracked move, a cd - "
     "or a missing folder; a relative cd after a missing folder is a declared limit, and ordinary work "
     "from a worktree root allows", worktree_home_cd_after_untracked_case),
    ("worktree-home: pushd into another checkout is refused, bare or chained; a pushd within the "
     "cwd's own checkout, or outside the clone, passes", worktree_home_pushd_case),
    ("worktree-home: a later path field outside the recorded home is refused, not skipped",
     worktree_home_later_field_case),
    ("worktree-home: a lone cd or Set-Location into the recorded home is allowed from outside "
     "it, in Windows or POSIX form", worktree_home_lone_cd_case),
    ("worktree-home: a cd or Set-Location into the home chained with another step is still denied",
     worktree_home_chained_case),
    ("worktree-home: a /c/ cwd inside the home is inside, and the same form outside it is denied",
     worktree_home_posix_cwd_case),
    ("worktree-home: a cd or Set-Location outside the home, or to its suffixed sibling, is denied",
     worktree_home_cd_out_case),
    ("worktree-home: a lone move with a separator is refused, quoted or not",
     worktree_home_quoted_move_case),
    ("worktree-home: sl, chdir and set-location are not moves in Bash",
     worktree_home_bash_alias_case),
    ("worktree-home: the merge rule reads a /c/ cwd as main does", worktree_home_cwd_merge_case),
    ("worktree-home: the shared-tree rule reads a /c/ cwd as main does",
     worktree_home_cwd_shared_tree_case),
    ("worktree-home: the builder test-edit rule reads a /c/ cwd as main does",
     worktree_home_cwd_builder_case),
    ("worktree-home: the frozen-path rule reads a /c/ cwd as main does",
     worktree_home_cwd_frozen_case),
    ("worktree-home: the config-edit rule reads a /c/ cwd as main does",
     worktree_home_cwd_config_case),
    ("worktree-home: the agent cap rule reads a /c/ cwd as main does", worktree_home_cwd_cap_case),
    ("worktree-home: a builder write to a test file from a /c/ cwd in a repository is refused "
     "off Windows", worktree_home_cwd_builder_refuse_case),
    ("worktree-home: a builder write to product code from a /c/ cwd in a repository is allowed "
     "off Windows", worktree_home_cwd_builder_src_case),
    ("worktree-home: a builder write to a path in no repository from a /c/ cwd is allowed "
     "off Windows", worktree_home_cwd_builder_scratch_case),
)
for _label, _check in LOG_CHECKS:  # the literal above is not appended: tag it here
    LOG_FAMILY.setdefault(_label, _family(_label))


# The cd act with a variable folder joins the worktree-home family, as the cd cases above it do.
