#!/usr/bin/env python3
"""The global PreToolUse guard.

Modes:
- PreToolUse: Before each matched tool call, runs the owner's global rules in a fixed
  order and refuses or asks on the first match. Bad input allows the call.
- SubagentStop: When a builder, test-author or record-writer stops, judges its whole diff
  against its role, for example a builder that changed a test path. A builder's offence
  is refused at its first stop; any other role's offence is logged for the reviewer.

Claude Code runs this script before each matched tool call. The script reads one
JSON object on stdin and answers on stdout.

  stdin  : {"tool_name": str, "tool_input": {...}, "cwd": str}
  allow  : print nothing, exit 0
  refuse : print one hookSpecificOutput object with "deny" or "ask", exit 0; when the owner
           override lifts the refusal, print nothing, exit 0 (the allow output)

Fail open. Unreadable input, a payload that is not an object, or a missing key
all allow the call. A guard defect must never brick a session.

The rules below are the owner's global CLAUDE.md made mechanical. Each refusal and each note
logs its rule name. This index lists every rule name that `refuse()` or `record()` writes,
in the order `judge_shell` and `judge` check them. The first match wins, unless an override
lifts it: then the call is allowed and no later rule runs, so `never_lifted` checks the acts no
override lifts first. The reason text of a
rule is the constant it emits. Its limits are in its decision, or in the comment above its code.

Every tool the guard judges, first of the refusals (`judge`, after the Read and Grep exit,
set_override_veto and session_home_keep):
  handoff-unread       deny. After compaction, a call from the main session while its handoff is
                       unread. The reason names the handoff and says to Read it. A payload with
                       `agent_id` passes. An override lifts it. A failed import allows.
                       (precompact-handoff, item 9)

Shell tools (Bash, PowerShell), in judge_shell order:
  builder-diff         deny. A builder commit or push whose diff holds a test path, judged
                       against the commits the builder made and its working tree. The reason gives
                       the undo route and names no path. No override lifts it. SubagentStop
                       (`judge_stop`) refuses the builder's first stop the same way; a second stop
                       passes.
                       (builders-cannot-edit-tests)
  author-diff, writer-diff, designer-diff, role-diff-*
                       noted. A test-author or record-writer commit or push.
                       The diff it would send is logged for the reviewer. Never refuses.
                       SubagentStop (`judge_stop`) logs the same names for the whole diff, and
                       also role-diff-main-checkout, role-diff-unresolved and
                       role-diff-unread. An unread diff of any role, builder included, is logged
                       and allowed.
                       (builders-cannot-edit-tests)
  git-env-set          deny. A command that sets GIT_DIR, GIT_WORK_TREE or GIT_INDEX_FILE.
                       Reading, unsetting, or a mention in quoted text passes. (git-env-set-refused)
  shared-tree          deny or ask. A command that throws away work, judged against the state of
                       its subject. An empty subject passes. An unreadable subject is allowed and
                       noted as `subject-unread`. (stash-stack-is-a-shared-subject,
                       agent-worktree-discard-is-noted)
  pointer-head         deny. A command that moves HEAD off `main` in the pointer checkout.
                       A move to `main` passes.
  silent-write         deny. A git write whose own trace is silenced, by a null redirect or by
                       git's `-q`. The measured carve-outs are the comments above
                       SILENT_WRITE_SUBCOMMANDS and QUIET_FLAG_SUBCOMMANDS.
  hand-made-worktree   deny. A real worktree add whose new tree lands outside
                       `<primary>/.claude/worktrees/`. A repo under the temp folder passes.
                       (lanes-start-in-tool-worktrees)
  impeccable-review-only  deny. A build or settings-writer command of the impeccable skill.
                       (design-skills)
  cite-by-id          deny. A commit message or PR body that cites a record by its path.
  lane-by-slug         deny. A commit message or PR text that names a lane by a session number.
                       (lane-by-slug)
  machine-wide-kill    deny. A kill by name or pattern, or of a pid that is not a descendant of
                       this session. (a-kill-by-pid-needs-an-owned-pid)
  detached-launch      deny. A command that starts a process and detaches it from the session.
  wsl-allow-list       deny. A `wsl` call outside the fixed list of test commands. (wsl-allow-list)
  live-stream, waiter  deny. A command that follows a stream with no end, or polls with sleep.
  background-end       deny. A background command with no end note. (background-needs-end-note)
  playwright-browsers-path, playwright-install
                       deny. (playwright-browsers-path, playwright-install-once)
  rm-var-unguarded     deny. A recursive delete under an unguarded variable.
                       (rm-on-a-variable-needs-a-guard)
  rm-after-cd          deny. A recursive delete of a relative target after a cd.
                       (rm-after-cd-names-absolute-path)
  git-after-cd         deny. A git write after a cd that `;`, a newline or `||` joins. A `&&` chain
                       and `-C` with a full path pass. (git-after-cd-joins-with-and)
  ln-over-directory    deny. See the comment at rule 3b in judge_shell.
  destructive-delete   deny. A recursive delete, forced or not, at a root, a home, a glob, `.`,
                       the working folder (`$(pwd)` too) or a folder above it, in either shell.
                       (rm-path-wrapper)
  force-push           deny or ask. A lease with --force-if-includes passes. --force or a `+`
                       refspec refuses. A push that reaches the default branch asks.
                       (stale-safe-force-push)
  push-main            ask. A non-forced push whose destination is literally main or master,
                       `--all` included. The remote's HEAD is not read. A dry run passes.
  push-stray-branch    ask. A push with an implied destination (bare, `HEAD`, `@`, or a colon-less
                       refspec naming the current branch) that writes a name other than the branch's
                       upstream. Only with an upstream on the pushed remote that is not main or master.
  env-file             deny. Any read or write of an environment file.
  merge-checks         deny. A merge while the head has a check pending or red, while another
                       ready PR on the base runs CI, or when the read could not run. `--auto` too.
  merge-role-proof     deny. A merge-tool call with a role flag whose tier the session's own get_session
                       record (read from the transcript) does not show in its cs-build tags.
  roadmap-one-writer   deny. A `git push`, also one inside `bash -c`, `sh -c` or `eval`, whose destination is
                       the checkout's record branch (lint/layout.py record_branch) or `roadmap`, except a
                       dry run, unless the session's own get_session record (read
                       from the transcript) shows the tag cs-build:triage with no set_session_tags after
                       it. No record, no transcript or no env id is a refusal. An override lifts it.
  trust-card-in-build  deny. A call to either tool that opens the owner's trust card, unless the session's own
                       get_session record (read from the transcript) proves no cs-build tag. No record,
                       no transcript or no env id is a refusal.
  lane-closes-after-records
                       deny. An archive_session of a lane (newest get_session record of the target, read from the
                       transcript, tagged cs-build:lane) while an open pull request of its cs-repo has a head ref
                       equal to its cs-step slug. No record of the target, a lane with no cs-step or cs-repo tag,
                       and a read of the open list that fails (gh missing too) are refusals. A target with no lane
                       tag passes. An override lifts it.
  lane-one-topic      deny. A send_message whose first non-blank line starts with the marker
                       `Lane brief: <step>. Topic: <topic>.` (guard_merge.LANE_BRIEF_MARKER), when the target's newest
                       record (get_session, or the create_session that made it, read from the transcript) is tagged
                       cs-build:lane and its cs-topic tag differs from the brief's Topic, or the brief names none. A lane
                       with no cs-topic is judged by its cs-step tags: the brief's step must be one. The marker matches
                       without case, after optional markdown lead characters. A set_session_tags call on the target after
                       its record, and a marker brief with no record of the target, are refusals. A message without the marker reads no transcript. An
                       override lifts it.
  draft-pr             deny. A `gh pr create` without `--draft`. (draft-until-reviewed)
  records-page         deny. A `git commit` whose docs/records.md differs from the base's page.
                       (records-index-at-merge)
  conflict-markers     deny. A `git commit` that would hold a start, a lone mid and an end conflict marker
                       line in one file's added lines, read with `git diff --check`: the index, or the working
                       tree (untracked files too) when `-a`, a pathspec or an earlier add reaches the file; a
                       `merge`, `rebase` or `cherry-pick --continue` counts as a commit. It judges a commit only
                       when each earlier segment is a git add, commit or read, `true`, `false` or `cd`. Also a
                       `git push` whose net range (remote-tracking tip, else upstream, else default base, up
                       to the pushed ref, else HEAD) adds such a file; and a push after a commit the guard
                       could not judge, when that commit covers a triplet already in the tree or the chain
                       runs merge, pull, rebase, cherry-pick, stash pop or apply, or am.
                       (commit-refuses-conflict-markers)
  frozen-path          deny. A write to the settings, hooks or global CLAUDE.md under
                       `${CLAUDE_CONFIG_DIR:-$HOME/.claude}`. (frozen-path-resolves-shell-vars)
  config-edit          noted. A write to a project's own settings or hooks. See below.
  agent-model-cap   ask. A write to a settings file that sets or changes
                       `CLAUDE_CODE_SUBAGENT_MODEL`, `CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL` or the `_FORCE` form.
                       (agent-model-cap)
                       deny. An Agent or Task spawn that sets model opus, unless Plan, designer,
                       design-reviewer, a builder's third-round marker or an Explore's `Audit:` marker
                       covers it. The general override, `opus [role] <time>` or a step grant lifts the
                       spawn refusal; none lifts the settings-write ask.
  ask-alone            deny. An ask command chained with other commands. (ask-commands-run-alone)
  guard-crash          crash. The guard itself raised. The call is allowed and the log shows it.

Other tools, in `judge` order:
  worktree-home        deny. A call from an agent whose shell cwd or write target is outside its
                       own recorded worktree. Read and Grep pass, so a stranded agent can report.
                       A Write or Edit strictly inside the caller's own `agent-<id>-<suffix>`
                       red-run folder passes.
                       No record (a non-isolated agent, or the orchestrator) allows everything.
                       No override lifts it. (an-agent-outside-its-home-tree-must-stop)
  other-checkout       deny. Any session's write whose target sits in a checkout of this clone
                       other than the one holding its cwd. A nested worktree owns its own files.
                       A target in no checkout, or in the clone's `.git`, passes; so does a
                       linked checkout in this session's own scratchpad, for a call with no
                       `agent_id` and a valid session id. Unreadable git passes. The shell form
                       reads the targets frozen-path reads, after a leading `cd`. An override
                       lifts it.
                       A Bash or PowerShell `cd`, `pushd` or `Set-Location` into another
                       checkout is refused too, bare or chained; the cd target in the caller's
                       recorded home, a session's recorded home, or the caller's own
                       `agent-<id>-<suffix>` red-run folder passes that act. A write strictly
                       inside that red-run folder passes too, here and in worktree-home; the
                       folder root does not (no `rm -rf <red>`).
                       A write or `cd` into a separate clone of the same repo (same origin, read
                       from the config files) is refused too, as is a write from a cwd stranded
                       in one while `CLAUDE_PROJECT_DIR` names the home clone; a git verb that
                       changes files (SESSION_HOME_GIT_VERBS) is refused from that stranded cwd
                       and as `git -C <separate clone>`, while `git log` and `git show` pass; the
                       temp folder, other repos, an unreadable origin and the home clone pass.
                       (an-agent-outside-its-home-tree-must-stop)
  session-home         deny. A session whose recorded worktree folder is gone, with its cwd in the primary
                       checkout, and a write (Write family or shell) that lands in the primary's own
                       files. Its record is `<primary>/.git/session-homes/<session_id>`, written by a
                       call with no `agent_id` from a `.claude/worktrees/<name>` folder, cleared by that
                       session's ExitWorktree. The reason names the EnterWorktree tool. The clone's
                       `.git`, a target outside the clone, reads and non-writing shell pass. A git
                       `clean` counts only with a force flag. An
                       override lifts it. It adds no git spawn beyond what the call already spends.
  agent-role-model     deny. A spawn whose model ranks above its role's row in the decision record
                       (haiku < sonnet < opus), or that names no model where the role has no `model:`
                       pin and no default model is set. An Explore whose brief's first line
                       carries the `Audit:` marker, a reviewer on a later-round brief and every Opus
                       spawn pass it. An unread record
                       passes and is noted as `agent-role-model-unread`. The general override lifts an
                       above-row refusal; no override lifts the no-model refusal. A Workflow
                       `agent()` call is judged as a spawn; one whose model or agentType the scan
                       cannot read is skipped, and an unread brief is judged as an empty brief.
                       (agent-model-cap)
  agent-model-floor, roles-third-round-steps-up
                       deny. A spawn below the model floor, or a third round on the wrong model.
                       The Workflow scan is static. It reads string-literal `model` and
                       `agentType` keys, and a literal prompt, in each `agent()` call. A template
                       prompt reads its static text only. A step-up call whose prompt or model is
                       not a literal passes. A model set through a variable,
                       a spread, an alias, a concatenation, a template `${}`, a ternary, a computed key or a
                       shorthand key is not seen. A regex literal after `)`, `return` or
                       `typeof` that holds a quote can hide an `agent()` call.
                       (agent-model-cap)
  lane-effort-pin      deny. A `create_session` call tagged `cs-build:lane` whose prompt is
                       not exactly `/effort medium` (LANE_EFFORT), with no trimming. A lane tag is
                       any tag that, stripped and casefolded, is `cs-build:lane`; `tags` may be a
                       string. A call with no lane tag passes. An override lifts it.
                       `session_home_keep` skips this tool. (agent-model-cap)
  lane-repo-tag        deny. A `create_session` call with a lane tag (as for lane-effort-pin) and no tag
                       that names the calling checkout's GitHub `owner/name` as the roadmap reads a repo tag
                       (`repo_tag_names`): exact `cs-repo:` prefix, no strip, owner/name without case.
                       The repo is `git_reads.github_repo`, shared with the roadmap build: the "github"
                       key of the layout extras file's "roadmap" object first, else the last two
                       segments of the origin's path (a scheme-less local path too), `.git` stripped;
                       the host is never read. With no readable repo, any tag `cs-repo:<owner>/<name>`
                       passes. The deny reason names the tag to add.
                       Runs after lane-effort-pin. An override lifts it. (agent-model-cap, session-tiers)
  load-brake           deny. On a local session, a lane-start call, an agent's shell or file write, or a lane
                       session's own shell or file write, when the machine is busy (lane starts only) or full. A
                       lane session is one whose own newest get_session record carries `cs-build:lane` and no other
                       `cs-build:` tag; the coordinator, triage and the batch runner are never braked on their own
                       calls. The transcript is read only at full. A cloud session skips it. An override lifts it.
                       (machine-load-brake)
  merge-checks, draft-pr, impeccable-review-only
                       deny. The MCP merge, pull request and Skill forms of the rules above.
  simulator-boot-bypass
                       deny. A raw `simctl boot` (through `xcrun` or bare), or an open of
                       Simulator.app (`open -a Simulator`, `open -a Simulator.app`, an `open` of a
                       path that ends in Simulator.app, `open -b com.apple.iphonesimulator`).
                       Judged by the command word on the text alone, before any `simctl list`,
                       and before the two rules below. The remedy is `sim-test`. An override
                       lifts it. (sim-test-is-the-one-boot-path)
  simulator-boot-cap, simulator-boot-twin
                       deny. A simulator boot past the cap, or one that duplicates an idle device.
                       They judge only `xcodebuild -destination` and the simulator MCP `launch`.
                       (sweep-shuts-down-idle-simulators)
  simulator-boot-route
                       deny. An `xcodebuild -destination` that names a shut-down simulator. Judged
                       after the cap and twin rules. The remedy is `sim-test` for the `test` action,
                       else the generic destination. An override lifts it. (sim-test-is-the-one-boot-path)
  simulator-boot-lease
                       deny. A simulator MCP `launch` of a shut-down device, lock or no lock: no session
                       holds a lease for it. The remedy is `sim-test`. Judged after the cap and twin
                       rules. A launch of a booted device passes. An override lifts it.
                       (sim-test-is-the-one-boot-path)
  builder-test-edit, test-author-scope, record-writer-scope, designer-scope
                       deny. A role's write outside its scope. (builders-cannot-edit-tests)
  env-file, frozen-path, config-edit, agent-model-cap
                       the write-tool forms of the rules above. Every deny runs over all path
                       fields of a call before any ask.

A project's own `.claude/settings.json`, `.claude/settings.local.json` and `.claude/hooks/*`
are not frozen. They are allowed, and the guard logs one `config-edit` line, so the config-report
Stop hook can show the edit at turn end. `subject-unread` is logged the same way: an allow that a
person still gets to see.

`agent-model-cap` asks on a settings write and never refuses it, because that same write is how an Opus agent is
enabled on purpose. It stands after `frozen-path`, so only a project-scoped write reaches it. Its
ask names the requested value and the file, which is not an exception to the remedy rule below:
the ask tells the approver what is turned on and where. That text comes from a tool call, so the
value and the path are cleaned of control characters and cut at a bound.

A merge into main is allowed and never logged by the guard.
`hooks/decision_watch.py` names each merge from the transcript at turn end. A `git checkout`
with `--ours`, `--theirs` or `--merge` during an unresolved merge, rebase, cherry-pick or revert
picks a conflict side. It discards no work, so `shared-tree` passes it.

A read named by argv (`--help`, `-h`, `--dry-run`, `push -n`, `tag -l`) is not a write, and a
value of `-m` or `-F` is never a flag. A write whose `-C`, `--git-dir`, `cd` or cwd sits under
the temp folder is a throwaway and passes. `fetch` writes only a `src:dst` whose dst is a
branch. A redirect named inside quotes is text. The refusal names its command ("command N of M, the
push").

Every refusal names its rule and says what to do instead. The remedy never names the refused
command or path, because Claude would copy it as the way round (`git-remedy-never-names-target`).
The matched text goes to the log, so a person can still see what fired.

An "ask" decision puts the answer in the owner's hands. The one lift is the owner override
(decision owner-override): the owner types `override` as a whole prompt, and refuse() lets the
next refused act through, or every refused act for a time. The narrower Opus override (`opus 2h`) lifts
only the Opus spawn refusal, and so does a step grant on the lane's roadmap step (decision agent-model-cap).
No override lifts `frozen-path`, `git-env-set`, a kill of pid 0, 1 or -1, the
role and model guards (the settings-write ask of `agent-model-cap`,
`agent-model-floor`, the no-model refusal of `agent-role-model`, `roles-third-round-steps-up`, `builder-test-edit` and the other role guards),
or `worktree-home`. No override check reaches the missing-module deny, the `settings.json` deny list
or the `bin/rm` and `bin/merge` shims; each of those refusals says that no override lifts it. Every
refusal that goes through refuse() ends with the line the owner types, or with that same sentence.
The model judges (hooks/call_judge.py, hooks/prose_judge.py, hooks/sendmessage_state.py) refuse through
refuse() too, so an override lifts them.
"""

import difflib
import importlib
import importlib.machinery
import importlib.util
import json
import os
import re
import shlex
import sys
import time

# The shared code lives in guard_core.py, and the rule families in guard_<family>.py, beside this
# file. This file's own folder goes first on the path, so a copied guard.py loads its copied siblings.
_HERE = os.path.dirname(os.path.realpath(__file__))
if sys.path[:1] != [_HERE]:
    sys.path.insert(0, _HERE)

# The rule families in import order: each one imports only guard_core and the families before it.
_FAMILY_MODULES = ("guard_branch_worktree", "guard_shared_tree", "guard_pointer",
                   "guard_push_delete", "guard_merge", "guard_frozen", "guard_env",
                   "guard_kill", "guard_stream", "guard_rm_var", "guard_mask_script", "guard_wsl")
# guard.py and each guard_*.py the installer copies carry `INSTALL_ID = "<id>"`, one value per install
# run, stamped at copy time in place of the whole commented placeholder line below. A file with no such line is a placeholder
# (the repo copy, or an old file from before the stamp). A set of all placeholders matches, which is the
# repo run. A placeholder beside a real id is mixed, so it differs. A load that fails, or loads modules
# with different ids, means an install landed between two of our reads: wait, clear the modules, and load again. The wait is bounded; after it the
# fallback below fails closed, never open. This is the one home of the stamp check.
# INSTALL_ID = "uninstalled"
# An installed copy (a stamped INSTALL_ID) loads its guard_*.py modules from guard.d/<its id>/ beside
# it, when that folder is there. The installer writes that whole folder first and replaces this file
# last, so the replace of this one file switches the whole set: a load sees the old set or the new
# set, never a mix, however long the install stalls between two files. No folder, or a repo copy
# with no stamp, loads the modules beside this file.
_SET_DIR = os.path.join(_HERE, "guard.d", str(globals().get("INSTALL_ID", "")))
if "INSTALL_ID" in globals() and os.path.isdir(_SET_DIR):
    sys.path.insert(0, _SET_DIR)
_PLACEHOLDER = None
_LOAD_WAIT_SECONDS = 5.0
_LOAD_STEP_SECONDS = 0.25


def _install_ids_differ():
    ids = {getattr(sys.modules.get(name), "INSTALL_ID", _PLACEHOLDER)
           for name in ("guard_core",) + _FAMILY_MODULES}
    ids.add(globals().get("INSTALL_ID", _PLACEHOLDER))
    return len(ids) > 1


_load_deadline = time.monotonic() + _LOAD_WAIT_SECONDS
_loading = "guard_core"   # the module being loaded, for the fallback line below
while True:
    try:
        _loading = "git_reads"
        import git_reads
        _loading = "guard_core"
        import guard_core
        from guard_core import (
            AUTHOR_ROLE, BUILDER_ROLE, DESIGNER_ROLE, GIT_WORK_TREE_RE, heredoc_heads, POWERSHELL_CALL, READ_ONLY_TOOLS, REDIRECTION, SHELL_TOOLS,
            SILENT_WRITE_REDIRECT, WRITER_ROLE, WRITE_TOOLS, _absolute, _expanded, _force_utf8_streams,
            _resolved, _run_dir, _segment_git_c_target, _split_heredocs, agent_role, basename, cap_safe,
            clone_checkouts, command_indexes, command_root, git_calls, git_common_dir, inline_script, is_cloud, is_move_into, is_powershell, is_worktree, log_path_and_text,
            inner_commands, nested_script, norm,
            _segment_cd_target, _strip_heredoc_bodies_unconditionally,
            path_is_inside, primary_checkout, record, refuse, resolve_command,
            resolve_default_base,  # noqa: F401  re-exported: janitor/test_sweep.py calls guard.resolve_default_base
            segment_tokens, split_segments, strip_heredoc_bodies,
            CD_WORDS, _git_subcommand_index, cd_walk, dir_before_segment, shell_abs, walk_quotes,
            _compound_delta, _exits_on_failure, subshell_depth,
        )
        _loading = "guard_branch_worktree"
        from guard_branch_worktree import (
            BRANCH_DELETE_DENY_REASON, BRANCH_DELETE_FLAGS, WORKTREE_PRUNE_ASK_REASON, WORKTREE_REMOVE_DENY_REASON,
            worktree_remove_forced,
        )
        _loading = "guard_shared_tree"
        from guard_shared_tree import (
            PUSH_DENY_REASON, STACK_DENY_REASON, TREE_ASK_REASON, TREE_DENY_REASON,
            checkout_conflict_resolve, clean_deletes_files, names_only_files, one_place, session_id_of, shared_tree_match,
            SESSION_ID_RE, in_any_session_scratchpad, stash_takes_the_stack, subject_state, under_session_scratchpad,
        )
        _loading = "guard_pointer"
        from guard_pointer import (
            POINTER_HEAD_REASON, head_root, pointer_checkout, pointer_head_hit,
        )
        _loading = "guard_push_delete"
        from guard_push_delete import (
            DELETE_REASON, DESTRUCTIVE_DELETE, LINKED_NM_REASON, PUSH_ASK_REASON, PUSH_MAIN_REASON,
            PUSH_REASON, PUSH_STRAY_REASON, cmd_exe_delete_hit, delete_text, linked_nm_hit,
            parent_delete_hit, push_ask_hit, push_target, push_text, push_verdict, rm_delete_hit,
        )
        _loading = "guard_merge"
        from guard_merge import (
            BARE_MERGE_REASON, CONFLICT_MARKERS_CHAIN_REASON, CONFLICT_MARKERS_PUSH_REASON, CONFLICT_MARKERS_REASON,
            DRAFT_PR_REASON, MERGE_TOOLS, RECORDS_PAGE_REASON, ROLE_REASON,
            conflict_markers_hit, gh_call_of, git_call_of, merge_call_of, merge_check, merge_check_reason, record_writer_hit, records_page_hit, role_proof_hit,
            DEFAULT_RECORD_BRANCH, RECORD_REASON, settings_roots, TRUST_REASON, archive_hit, brief_hit, trust_card_hit,
            undrafted_pr_create, uses_merge_tool,
        )
        _loading = "guard_frozen"
        from guard_frozen import (
            FROZEN_REASON, GIT_FILE_VERBS, MUTATING_COMMAND, _shell_write_hit, frozen_shell_hit, interpreter_write_hit, is_frozen,
            is_project_config, project_config_shell_hit,
            PROJECT_FROZEN_FILES,  # noqa: F401  re-export: test_shared_names and test_wrappers read guard.PROJECT_FROZEN_FILES
        )
        _loading = "guard_env"
        from guard_env import (
            ENV_ADVICE, ENV_TOOL_REASON, _substitutions, env_heredoc_refusal, env_refusal, is_env,
        )
        _loading = "guard_kill"
        from guard_kill import (
            DETACHED_LAUNCH_REASON, GIT_ENV_REASON, KILL_PID_REASON, KILL_REASON,
            PLAYWRIGHT_INSTALL_REASON, PLAYWRIGHT_PATH_REASON, detached_launch_hit, foreign_pid_kill,
            git_env_command_hit, kill_fed_by_name, kill_fed_by_pipe, kill_hit, kills_group_pid,
            lsof_pids_reach_kill, playwright_command_hit, playwright_install_hit,
        )
        _loading = "guard_stream"
        from guard_stream import (
            BACKGROUND_END_REASON, LIVE_STREAM_REASON, LN_DESCENDS_REASON,
            NARRATED_TAIL_REASON, PATTERN_POLLER_REASON, WAITER_REASON, background_end_hit,
            live_stream_hit, ln_descends_hit, loop_condition_polls_a_pattern,
            narrated_tail_hit, waiter_verdict,
        )
        _loading = "guard_rm_var"
        from guard_rm_var import (
            rm_after_cd_hits, rm_after_cd_reason, rm_var_hits, rm_var_reason,
        )
        _loading = "guard_mask_script"
        from guard_mask_script import (
            mask_script,
        )
        _loading = "guard_wsl"
        from guard_wsl import WSL_REASON, wsl_hit

        _loading = "install-id"
        if _install_ids_differ():
            raise ImportError("the loaded modules carry different INSTALL_ID values")
        break
    except Exception as exc:
        if time.monotonic() < _load_deadline:
            time.sleep(_LOAD_STEP_SECONDS)
            for _name in ("git_reads", "guard_core") + _FAMILY_MODULES:
                sys.modules.pop(_name, None)
            importlib.invalidate_caches()
            _loading = "guard_core"
            continue
        # A recovery path must not depend on the module it recovers (CLAUDE.md
        # verification-recovery-independent-of-state). guard_core holds `record` and imports
        # `config_dir` from shared_names, so this writer repeats their few lines: one guard.log line
        # that names the module.
        try:
            folder = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
            os.makedirs(folder, exist_ok=True)
            text = " ".join(("%s: %s: %s" % (_loading, type(exc).__name__, exc)).split())[:120]
            with open(os.path.join(folder, "guard.log"), "a", encoding="utf-8") as handle:
                # Same form as record(): ISO 8601 with a colon UTC offset. datetime is imported here, not
                # taken from guard_core, so the writer survives the failure it reports.
                from datetime import datetime
                stamp = datetime.now().astimezone().isoformat(timespec="seconds")
                handle.write("\t".join([stamp, "", "crash", "guard-crash",
                                        text, "-"]) + "\n")  # the one literal "-": guard_core failed to load
        except Exception:
            pass
        if __name__ != "__main__":
            raise  # a hook that imports guard fails on its own terms, never by a silent allow
        # Fail closed (decision guard-hooks-fail-closed): a guard with a missing part judges nothing, so
        # it refuses the call. The reason tells the reader to reinstall and names no file. `refuse`
        # lives in the module that failed, so the deny is printed here. A SubagentStop has no tool
        # call to refuse, and a block there could trap the agent: it passes, as the log line records.
        try:
            stopping = json.load(sys.stdin).get("hook_event_name") == "SubagentStop"
        except Exception:
            stopping = False
        if not stopping:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse", "permissionDecision": "deny",
                "permissionDecisionReason": (
                    "guard-crash: the guard is missing a part and cannot judge this call, so it refuses "
                    "every call, Bash and PowerShell too. Remedy: in your own terminal, not a Claude "
                    "session, run install.sh from the claude-settings checkout (Windows: install.ps1), "
                    "then retry. No override lifts this refusal, because the failed guard cannot check "
                    "the acts that no override lifts. "
                    "(decision guard-hooks-fail-closed, a guard with a missing part refuses the call)")}}))
        sys.exit(0)


# `_git`, `config_dir` and the session reads are never bound here: a test or the janitor patches
# them on git_reads, and `guard.<name>` must read that one object, so git_reads is searched first.
# Code below calls them through the module. Other files reach every shared name through this hook.
def __getattr__(name):
    for module in [git_reads, guard_core] + [sys.modules[family] for family in _FAMILY_MODULES]:
        if hasattr(module, name):
            return getattr(module, name)
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


# ------------------------------------------------------------------ the silent write
#
# Rule 1c. CLAUDE.md (Git): "Never discard a command's output." A discarding REDIRECT is refused on
# every one of these six subcommands, whatever the subcommand does with its own output: the shell
# throws the stream away before git ever gets a say, so a hook's refusal and git's own proof of
# landing are both gone, together, always.
SILENT_WRITE_SUBCOMMANDS = ("commit", "push", "merge", "tag", "rebase", "cherry-pick", "pull")

# Gap roster. Each one moves a ref or lands a merge, so each is a write when its
# output is silenced: `pull` (a fetch plus a merge; its `-q` joins the quiet arm), a `fetch` that
# names a `src:dst` refspec (it moves a local ref; a bare `fetch` stays a read), `make merge`,
# `gh pr merge`, and a closed descriptor (`2>&-`, `>&-`), which silences like /dev/null.
# `--dry-run` moves nothing and stays allowed. Output sent to a FILE stays allowed: the owner held
# that until measured.

# git's OWN `-q`/`--quiet` flag is a narrower statement, and it does not read the same for every
# subcommand. MEASURED 2026-09-19 and 2026-09-20, in throwaway repos under this session's
# scratchpad, never in a shared checkout, `-q`/`--quiet` alone, no redirect, three states each: a
# write that succeeds, one a hook refuses (a `pre-commit`/`pre-receive` hook, or the conflict
# `merge`, `rebase`, and `cherry-pick` raise on their own), and a no-op (nothing staged or to
# push, an already-merged branch, nothing left to replay, a change already present).
#
#   git commit -q       success        exit 0, stdout '',                stderr ''
#                        hook refusal   exit 1, stdout '',                stderr the hook's own line
#                        no-op          exit 1, stdout "nothing to        stderr ''
#                                                commit ...",
#
#   git push --quiet    success        exit 0, stdout '',                stderr ''
#                        hook refusal   exit 1, stdout '',                stderr the full rejection
#                        no-op          exit 0, stdout '',                stderr ''
#
#   git merge -q         success        exit 0, stdout '',                stderr ''
#                        conflict       exit 1, stdout the full           stderr ''
#                                                CONFLICT message,
#                        no-op          exit 0, stdout '',                stderr ''
#
#   git rebase -q       success        exit 0, stdout '',                stderr ''
#                        conflict       exit 1, stdout the CONFLICT       stderr the apply error
#                                                message,                 and its hints,
#                        no-op          exit 0, stdout '',                stderr ''
#
#   git tag -q          every state    exit 129, stdout '',              stderr "error: unknown
#                                                                                switch `q'" plus
#                                                                                the full usage
#
#   git cherry-pick -q  every state    exit 129, stdout '',              stderr the full usage
#                                                                                ("-q" is not a
#                                                                                cherry-pick option)
#   git cherry-pick
#     --quiet            success        exit 0, stdout the full commit    stderr ''
#                                                summary line,
#                        conflict       exit 1, stdout the CONFLICT       stderr the apply error
#                                                message,                 and its hints,
#                        no-op          exit 1, stdout "nothing to        stderr "previous
#                                                commit ...",              cherry-pick is now
#                                                                          empty" and its hint
#
# `commit -q` hides nothing a session could not already read: a refusal keeps its own message on
# stderr, a no-op keeps its own message on stdout, and both keep a nonzero exit code, so silence
# at exit 0 is unambiguous proof of a landed commit. `commit` drops out of the quiet-flag arm.
#
# `push -q` and `merge -q` and `rebase -q` measure the same way as each other, and differently
# from `commit`. Each one's own refusal (a hook, or a real conflict) stays fully readable. But
# each one's success and its own no-op are BOTH silent and BOTH exit 0 (without `-q` they already
# differ: `push` prints "Everything up-to-date" against the `sha..sha  branch -> branch` summary,
# `merge` and `rebase` print their own "up to date"/"nothing to replay" line against a diffstat or
# a "Successfully rebased" line). `-q` erases the one line that told a real write from a no-op, so
# a session cannot read whether the write it just ran moved anything. All three keep the
# quiet-flag arm on this measurement, not on the flag's name.
#
# `tag` has NO `-q` and NO `--quiet` at all (git 2.39.3): both spellings exit 129 with "error:
# unknown switch" before git reads the tag name, the message, or the repository state. Every
# state measures identically, because the flag never gets past option parsing. `tag` therefore
# cannot use `-q`/`--quiet` to hide a success from a no-op or a refusal: the attempt is always a
# loud, immediate failure. `tag` drops out of the quiet-flag arm.
#
# `cherry-pick`'s short form, `-q`, is ALSO not a valid option (exit 129, the same shape as
# `tag`). Its long form, `--quiet`, IS valid, and measures as the least silent of the six: a
# success still prints the full one-line commit summary to stdout, a conflict prints its own
# CONFLICT message and hints in full, and a no-op (an already-applied change) prints "nothing to
# commit" and "previous cherry-pick is now empty" in full, at its own distinct nonzero exit. No
# state is silent, so nothing is lost by allowing either spelling. `cherry-pick` drops out of the
# quiet-flag arm.
QUIET_FLAG_SUBCOMMANDS = ("push", "merge", "rebase", "pull", "fetch")


def unquoted_at(text: str, index: int) -> bool:
    """True when `index` in `text` sits outside every quote, read off guard_core's quote walk (the
    one `split_segments` cuts with: an escaped quote, a `$'...'` string and a PowerShell backtick
    included). An unterminated quote runs to the end."""
    for at, _, quote in walk_quotes(text):
        if at >= index:
            return not quote
    return True


def discards_output(segment: str) -> bool:
    """True when the segment redirects stdout or stderr, on any descriptor, to a null device. A
    redirect named inside a quoted string (a commit message, an echo) is text, never a redirect.

    The walk reads a quote inside `$( )` or backticks as the outer string's own, so
    `-m "$(printf '"')" >/dev/null` hides the redirect. Each substitution is cut out first
    (`_substitutions`, the env layer's cut) and the text around it is read again. Too deep to cut
    is a redirect: this fails closed. ponytail: a bandaid; the cause, the quote walk's reading of
    a quote inside `$( )`, stays."""
    if any(unquoted_at(segment, m.start()) for m in SILENT_WRITE_REDIRECT.finditer(segment)):
        return True
    if "$(" not in segment and "`" not in segment or not SILENT_WRITE_REDIRECT.search(segment):
        return False
    texts, too_deep = _substitutions(segment, powershell=is_powershell(segment))
    if too_deep:
        return True
    outer = type(segment)(texts[-1][0])
    return any(unquoted_at(outer, m.start()) for m in SILENT_WRITE_REDIRECT.finditer(outer))


# A write whose output feeds a pipe is judged by that pipe's tail: silenced by a redirect, or a
# `grep -q`, which prints nothing by itself. A printing tail (`| tail -5`, `| tee f`) is not.
# `bash -c '...'` stays unparsed, a known gap the owner left.
def tail_discards(tail: str) -> bool:
    """True when a pipe's last segment prints nothing the session can read."""
    tail = tail.strip().lstrip("&").strip()   # `|&` leaves a leading `&`
    if discards_output(tail):
        return True
    tokens = segment_tokens(tail) or []
    index = resolve_command(tokens) if tokens else None
    return (index is not None and basename(tokens[index]) == "grep"
            and any(t in ("-q", "--quiet", "--silent") for t in tokens[index + 1:]))


def quiet_write(args) -> bool:
    """True when a git call carries `-q` or `--quiet`."""
    return "-q" in args or "--quiet" in args


# A flag that takes the NEXT token as its value. Such a value is text, never a flag: `commit -m -h`
# and `commit -m "--dry-run"` are real commits. A miss here only keeps a deny, never lifts one.
VALUE_FLAGS = {"-m", "--message", "-F", "--file", "-c", "-C", "--reuse-message", "--reedit-message",
               "--author", "--date", "--fixup", "--squash", "-t", "--template", "--cleanup",
               "--trailer", "-o", "--push-option", "-X", "--onto", "--repo", "--strategy",
               "--strategy-option", "--exec", "--pathspec-from-file", "--receive-pack"}
# A letter whose value depends on the subcommand: `-s` is a merge's strategy but a commit's
# sign-off, `-x` a rebase's command but a cherry-pick's note, `-u` a tag's key but a push's upstream.
SUBCOMMAND_VALUE_FLAGS = {"merge": {"-s"}, "pull": {"-s"}, "rebase": {"-s", "-x"}, "tag": {"-u"}}


def takes_next(subcommand: str, token: str) -> bool:
    """True when `token` takes the next token as its value. In a short cluster the first value
    letter takes the rest of the cluster (`-mfoo`), or the next token when it is last (`-am`)."""
    flags = VALUE_FLAGS | SUBCOMMAND_VALUE_FLAGS.get(subcommand, set())
    if token in flags:
        return True
    if token[:1] != "-" or token[1:2] in ("-", ""):
        return False
    letters = {flag[1] for flag in flags if len(flag) == 2}
    for at, letter in enumerate(token[1:], 1):
        if letter in letters:
            return at == len(token) - 1
    return False
LISTING = re.compile(r"-[ln]+\d*")   # `tag -l`, `-n5`, `-ln1`
FETCH_VALUE_FLAGS = {"--depth", "-j", "--jobs", "--upload-pack", "--refmap", "-o", "--server-option",
                     "--deepen", "--shallow-since", "--shallow-exclude"}


def read_verb(subcommand: str, args) -> bool:
    """True when the call's own argv names a read: help, a dry run, a tag listing, a dry-run
    push. Argv tokens only, never the value of `-m` or `-F`, and nothing after `--`."""
    skip = False
    for token in args:
        if skip:
            skip = False
        elif token == "--":
            return False
        elif token in ("--help", "-h", "--dry-run") or (subcommand == "push" and token == "-n") or (
                subcommand == "tag" and (token == "--list" or LISTING.fullmatch(token))):
            return True
        elif takes_next(subcommand, token):
            skip = True
    return False


def fetch_moves_branch(args) -> bool:
    """True when a fetch's refspec writes a local branch: a `src:dst` whose dst is under
    refs/heads/ or refs/remotes/, or a short name (git resolves that to a branch). The first
    plain word is the repository, never a refspec."""
    plain, skip = [], False
    for token in args:
        if skip:
            skip = False
        elif token in FETCH_VALUE_FLAGS:
            skip = True
        elif not token.startswith("-"):
            plain.append(token)
    for spec in plain[1:]:
        dst = spec.lstrip("+").partition(":")[2]
        if dst and (not dst.startswith("refs/") or dst.startswith(("refs/heads/", "refs/remotes/"))):
            return True
    return False


def silent_write_hit(segment: str, tail: str = ""):
    """Return (matched text, mechanism, kind) for a write whose own trace is silenced, else
    ("", "", "").

    `mechanism` is `"redirect"` or `"quiet"`, so the caller can print the reason that matches
    what actually fired; `kind` is the act's name (`push`, `commit`, `merge`). A redirect can hide
    a refusal AND a proof of landing on any of the subcommands, while the quiet flag is judged per
    subcommand against `QUIET_FLAG_SUBCOMMANDS`, the measured set. Only `SILENT_WRITE_SUBCOMMANDS`
    are judged at all. `fetch`, `rev-parse`, and every other read subcommand fall outside it,
    which is what keeps the test-by-exit-code shape `git rev-parse -q --verify <ref> >/dev/null
    2>&1` allowed. `merge --abort` is carved out inside the loop: it lands nothing, so it has no
    landing to prove. A call whose argv names a read (`read_verb`) is carved out the same way.
    `tail` is the last segment of the pipe this segment feeds, if any (see `tail_discards`).
    """
    silenced = discards_output(segment) or (bool(tail) and tail_discards(tail))
    for subcommand, args in git_calls(segment):
        if subcommand == "fetch":
            # Only a fetch that moves a local branch (`src:dst`) is a write; a bare one is a read.
            if not fetch_moves_branch(args):
                continue
        elif subcommand not in SILENT_WRITE_SUBCOMMANDS:
            continue
        if subcommand == "merge" and "--abort" in args:
            continue
        if read_verb(subcommand, args):
            continue
        matched = ("git " + subcommand + " " + " ".join(args)).strip()
        if silenced:
            return matched, "redirect", subcommand
        if subcommand in QUIET_FLAG_SUBCOMMANDS and quiet_write(args):
            return matched, "quiet", subcommand
    if silenced:
        tokens = segment_tokens(segment)
        index = resolve_command(tokens) if tokens else None
        if index is not None:
            word, rest = basename(tokens[index]), tokens[index + 1:]
            if (word == "make" and "merge" in rest) or (
                    word in ("gh", "gh.exe") and rest[:2] == ["pr", "merge"]):
                return word + " " + " ".join(rest), "redirect", ("make merge" if word == "make" else "gh pr merge")
    return "", "", ""


def _git_option_tokens(tokens):
    """The words of a segment's git call that sit before its subcommand: git's own options."""
    index = resolve_command(tokens)
    if index is None or basename(tokens[index]) not in ("git", "git.exe"):
        return []
    return tokens[index + 1:_git_subcommand_index(tokens, index)]


def _git_dir_target(tokens):
    """The `--git-dir` the git call names before its subcommand, either spelling, or None."""
    options = _git_option_tokens(tokens)
    for at, token in enumerate(options):
        if token.startswith("--git-dir="):
            return token[len("--git-dir="):]
        if token == "--git-dir":
            return options[at + 1] if at + 1 < len(options) else None
    return None


def _unexpanded(path) -> bool:
    """True when a path holds a variable or a substitution: the shell's value is not this hook's."""
    return any(mark in path for mark in "$%`")


# The writes that change the work tree as well as the repository. `commit`, `tag` and a `fetch`
# write only the repository.
WORK_TREE_WRITES = ("merge", "rebase", "cherry-pick", "pull")


def in_throwaway(segments, number: int, cwd: str, ends=()) -> bool:
    """True when the write in `segments[number]` runs under the temp folder, where a lost trace
    costs nothing real. Only a local git write counts: a `push`, `gh pr merge` or `make merge`
    reaches past the folder, wherever it runs. The folder is read the way
    the shell reads it (`dir_before_segment`: cd, pushd, Set-Location, cd -, a subshell's cd),
    then its own `-C`, then its own `--git-dir`, which names the repository and outranks `-C`.
    A `--git-dir` leaves the work tree in the folder, so a write that changes the work tree
    (WORK_TREE_WRITES) needs that folder under the temp folder too. A
    path that holds a variable, an unknown cwd, a `GIT_DIR` or `--work-tree` all read as not
    throwaway: this fails closed."""
    if any(subcommand == "push" for subcommand, _ in git_calls(segments[number])):
        return False
    tokens = segment_tokens(segments[number])
    index = resolve_command(tokens) if tokens else None
    if index is None or basename(tokens[index]) not in ("git", "git.exe"):
        return False
    where = dir_before_segment(segments, number, cwd, ends)
    options = _git_option_tokens(tokens)
    if any(t.startswith(("GIT_DIR=", "GIT_WORK_TREE=")) for t in tokens[:index]) or any(
            t.startswith("--work-tree") for t in options):
        return False
    judged = []
    for named in (_segment_git_c_target(tokens), _git_dir_target(tokens)):
        if named is not None:
            where = None if _unexpanded(named) else shell_abs(named, where)
        judged.append(where)
    # judged[0] is the work tree, judged[1] the repository
    if not any(subcommand in WORK_TREE_WRITES for subcommand, _ in git_calls(segments[number])):
        judged = judged[1:]
    import tempfile   # lazy: only a silenced write reaches here
    return all(folder and path_is_inside(folder, tempfile.gettempdir()) for folder in judged)


# decision lanes-start-in-tool-worktrees: a worktree comes only from the tool's own isolation.
HAND_MADE_VALUE_OPTIONS = ("-b", "-B", "--reason")


def worktree_add_target(args):
    """The new-tree path of a `worktree add` call's arguments, else None (no path, or a help
    flag). `-b`, `-B` and `--reason` take a value. `--orphan` is a flag in git 2.42 and later and
    took a value before, so its next word is a value only when another path word follows. `--`
    ends the options."""
    words, ended, cursor = [], False, 0
    while cursor < len(args):
        arg = args[cursor]
        cursor += 1
        if ended or not arg.startswith("-") or arg == "-":
            words.append(arg)
        elif arg == "--":
            ended = True
        elif arg in ("-h", "--help"):
            return None
        elif arg in HAND_MADE_VALUE_OPTIONS:
            cursor += 1
        elif arg == "--orphan" and cursor < len(args) and not args[cursor].startswith("-"):
            if len([a for a in args[cursor:] if not a.startswith("-")]) > 1:
                cursor += 1
    return words[0] if words else None


def hand_made_worktree_hit(segments, number: int, cwd: str, ends=()) -> str:
    """The new-tree path when `segments[number]` is a real worktree add whose tree lands
    outside `<primary>/.claude/worktrees/`, else "". The primary is the one of the repo the call
    runs in (`dir_before_segment`, then its own `-C`). A repo under the temp folder is a throwaway
    and passes, so the repo is judged, never the target. Anything unreadable allows."""
    tokens = segment_tokens(segments[number])
    index = resolve_command(tokens) if tokens else None
    if index is None or basename(tokens[index]) not in ("git", "git.exe"):
        return ""
    target = None
    for subcommand, args in git_calls(segments[number]):
        if subcommand == "worktree" and args and args[0] == "add":
            target = worktree_add_target(args[1:])
            break
    if target is None:
        return ""
    where = dir_before_segment(segments, number, cwd, ends)
    named = _segment_git_c_target(tokens)
    if named is not None:
        where = None if _unexpanded(named) else shell_abs(named, where)
    if not where or _unexpanded(target):
        return ""
    primary = primary_checkout(where)
    if not primary:
        return ""
    import tempfile   # lazy: only a real worktree add reaches here
    if path_is_inside(primary, tempfile.gettempdir()):
        return ""
    tree = shell_abs(target, where)
    if tree is None:
        return ""
    if path_is_inside(tree, os.path.join(primary, ".claude", "worktrees")) is True:
        return ""
    return target


WORKTREE_HAND_MADE_REASON = (
    "Rule (hand-made worktree): a worktree comes only from the Agent tool's isolation "
    "'worktree' option or from the EnterWorktree tool, never from a tree made by hand. "
    "A hand-made tree sends an agent or a session to work in the main clone and loses the isolation. "
    "Remedy: start the work with one of those two tools. Call EnterWorktree with a `name` and no "
    "`path`. If the tool's isolation was refused, "
    "make no tree by hand: stop and report to the owner which layer refused and its exact "
    "message. A guard refusal starts \"Rule (\" and names its rule. Any other refusal is the "
    "harness's."
)


SILENT_WRITE_REDIRECT_REASON = (
    "Rule (Git): command {command} of {total}, the {kind}: a redirect silences this write's own "
    "output (>/dev/null), so neither a refusal nor the line that proves it landed would reach "
    "the session. "
    "Remedy: run {program} again with its output kept, ending the line with `2>&1 | tail -1`, "
    "and read what it prints before you say it landed."
)
SILENT_WRITE_QUIET_REASON = (
    "Rule (Git): command {command} of {total}, the {kind}: its quiet flag (-q) drops the one line "
    "that told a real update apart from one that moved nothing, so the session cannot read "
    "which one just ran. "
    "Remedy: run {program} again without the quiet flag, ending the line with `2>&1 | tail -1`, "
    "and read what it prints before you say it landed."
)


# ------------------------------------------------------------------ each agent's own worktree
#
# MEASURED 2026-09-27, macOS, one Explore agent with `isolation: 'worktree'`: a PreToolUse payload
# from an agent carries `agent_id` (17 hex characters) and `agent_type`. The
# orchestrator's own payloads carry no `agent_id`. `session_id` is the SAME for the orchestrator
# and its agents, so it never tells them apart. The agent's `cwd` was
# `<primary>/.claude/worktrees/agent-<agent_id>`, on branch `worktree-agent-<agent_id>`.
#
# An agent resumed after the harness auto-removed its worktree loses BOTH the folder and the
# branch, so git alone cannot tell "never had a worktree" from "worktree was removed". A RECORD
# is needed: docs/decisions/an-agent-outside-its-home-tree-must-stop.md.
#
# The record lives under the CLONE's git common directory, not inside any one worktree, so it
# survives that worktree's removal (`git_common_dir` above). Unmeasured: Windows, and the
# Write/Edit payload shape; covered by fixture in `test_guard.py`, not by a live probe.
AGENT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def agent_home_record_path(where: str, agent_id: str):
    """Return the file that holds `agent_id`'s recorded worktree home, or None when the clone's
    common directory could not be read. Stored under
    `<git-common-dir>/agent-homes/<agent_id>`, so it survives the worktree's own removal."""
    common = git_common_dir(where)
    return os.path.join(common, "agent-homes", agent_id) if common else None


def read_agent_home(where: str, agent_id: str):
    """Return the recorded home for `agent_id`, `''` when no record exists yet, or None when the
    record could not be read at all (no git, no common dir, an unreadable file). `None` is
    UNKNOWN, never a hit."""
    path = agent_home_record_path(where, agent_id)
    if not path:
        return None
    if not os.path.exists(path):
        return ""
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read().strip()
    except Exception:
        return None


def write_agent_home(where: str, agent_id: str, home: str) -> None:
    path = agent_home_record_path(where, agent_id)
    if not path:
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(home)
    except Exception:
        pass


def agent_worktree_home(payload, cwd: str):
    """Return (status, home, primary) for this call's agent.

    status:
      "none"      no valid `agent_id` on the payload: the orchestrator, or a call this rule does
                  not judge at all.
      "unknown"   an `agent_id` is present, but the home record could not be read (no git, no
                  common directory, an unreadable file). Allowed, never a hit.
      "no-record" the record reads clean and holds nothing, and this call's own `cwd` is not the
                  agent's worktree shape either: a non-isolated agent. Allow everything.
      "home"      `home` names the agent's recorded worktree, whether just written on this call
                  or read back from an earlier one.
    """
    agent_id = payload.get("agent_id") if isinstance(payload, dict) else None
    if not isinstance(agent_id, str) or not AGENT_ID.match(agent_id):
        return "none", "", None
    if not isinstance(cwd, str) or not cwd:
        return "unknown", "", None
    primary = primary_checkout(cwd)
    if not primary:
        return "unknown", "", None
    candidate = os.path.join(primary, ".claude", "worktrees", "agent-" + agent_id)
    recorded = read_agent_home(cwd, agent_id)
    if recorded is None:
        return "unknown", "", primary
    if recorded:
        return "home", recorded, primary
    if path_is_inside(cwd, candidate) is True:
        write_agent_home(cwd, agent_id, candidate)
        return "home", candidate, primary
    return "no-record", "", primary


WORKTREE_HOME_REASON = (
    "Rule (worktree home): this agent's own working tree is gone, or this call reaches outside "
    "it. "
    "Remedy: make no further change. Stop, and report this to your orchestrator."
)

HANDOFF_UNREAD_REASON = (
    "Rule (handoff unread): context was compacted and this session has not read its handoff. "
    "Remedy: Read %s now. The Read clears this check. Then repeat the call."
)

OTHER_CHECKOUT_REASON = (
    "Rule (other checkout): this write lands in another checkout of this clone, not the one this "
    "session stands in. "
    "Remedy: write only inside your own checkout, or report the change to the session that owns "
    "the other one. To remove a whole worktree, use `git worktree remove`, or leave it to the "
    "janitor sweep."
)

OTHER_CHECKOUT_CD_DETAIL = "cd into another checkout: "
OTHER_CHECKOUT_CD_REASON = (
    "Rule (other checkout): this command changes directory into another checkout of this clone, "
    "not the one this session stands in. "
    "Remedy: stay in your own checkout. To read another one, use `git -C <dir>` or a path, never "
    "`cd`."
)

OTHER_CLONE_DETAIL = "write into another clone: "
OTHER_CLONE_CD_DETAIL = "cd into another clone: "
OTHER_CLONE_GIT_DETAIL = "git write into another clone: "
OTHER_CLONE_REMEDY = (
    "Remedy: change files only in your home checkout. To read another clone, use "
    "`git -C <dir> log` or `git -C <dir> show`, or a path."
)
OTHER_CLONE_REASON = (
    "Rule (other checkout): this command writes into a separate clone of this repo, or runs from one "
    "while this session's home is another clone. " + OTHER_CLONE_REMEDY
)
OTHER_CLONE_CD_REASON = (
    "Rule (other checkout): this command changes directory into, or writes into, a separate clone of "
    "this repo. " + OTHER_CLONE_REMEDY
)


# agent-worktree-discard-is-noted: inside a worktree the harness made FOR an agent
# (`<primary>/.claude/worktrees/<name>`, the same shape `agent_worktree_home` above reads), a
# discard is ALLOWED and logged as a note, not asked. MEASURED: 18 shared-tree asks in
# ~/.claude/guard.log since 2026-09-16, and the owner reports the prompt is frequent in
# agent-heavy repos and carries nothing to judge there, because the lane is the agent's own and
# its commits already sit on its own branch and in its own reflog. A worktree anywhere else keeps
# "ask": the loss there may still be a person's own work in a lane they made by hand.
def agent_owned_worktree(root: str):
    """True when `root` resolves under some primary checkout's own `.claude/worktrees/`, the
    folder the harness makes agent worktrees in. False when it plainly does not, None when
    either path could not be resolved. Real paths only (CLAUDE.md "building-allow-list-is-the-
    constant"): a `..` or a symlink that climbs back out must not pass."""
    primary = primary_checkout(root)
    if not primary:
        return None
    return path_is_inside(root, os.path.join(primary, ".claude", "worktrees"))


# ------------------------------------------------------------------ the agent model cap
#
# The owner's user settings cap an agent's model with `CLAUDE_CODE_SUBAGENT_MODEL` and
# `CLAUDE_CODE_SUBAGENT_MODEL_FORCE`. User settings are one layer of the settings stack, and a
# project's own `.claude/settings.json` and `.claude/settings.local.json` override them. Decision 7
# allows a write to both, so the write that Decision 7 allows is also the write that lifts the cap.
#
# The answer is `ask`, never `deny`. The same write is how an Opus agent gets enabled on purpose,
# so the owner answers one call at a time. A wall here would only push the work off the guard's
# path.
#
# THE SETTINGS TEST IS A BASENAME, and it is taken from the RESOLVED path as well as from the
# spelling the tool passed. Rule 7 resolves its own paths with `realpath`, so a basename test on the
# spelling alone would leave rule 8 blind to a shape rule 7 already sees: a symlink named
# `alias.json` that points at a project's `.claude/settings.json`. The resolve sits inside a `try`,
# so the cannot-raise property of this rule holds. The managed settings file joins the list at the
# same price.
SETTINGS_BASENAMES = ("settings.json", "settings.local.json", "managed-settings.json")

# The cap's two variables, and a value beside one of them. The key side carries the optional
# `_FORCE` GREEDILY, so `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` reads as its own key and never as the
# shorter key followed by stray text. One value pattern covers a JSON pair (`"KEY": "value"`) and a
# shell assignment (`KEY=value`), because a heredoc body carries either.
AGENT_CAP_KEY = re.compile(r"CLAUDE_CODE_(?:WORKFLOW_)?SUBAGENT_MODEL(?:_FORCE)?")
AGENT_CAP_ASSIGN = re.compile(
    r"(CLAUDE_CODE_(?:WORKFLOW_)?SUBAGENT_MODEL(?:_FORCE)?)['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9][A-Za-z0-9._\-]*)"
)

# The fields a write tool carries its content in. `old_string` stands before `new_string`, so that
# `cap_change` reads the value the edit ARRIVES at, not the value it leaves.
#
# EVERY EDIT IS READ. An earlier version of this rule read the first 200 edits of a `MultiEdit`,
# and a review MEASURED the boundary that cap bought an attacker: 199 no-op edits ahead of the cap
# change asked, 200 allowed. A bound that hides a lift is worse than no bound, and the scan is
# cheap: MEASURED 2026-09-19 on this machine, the reading takes 2.8 ms over a 2 MB blob and 11.9 ms
# over an 8 MB blob, linear, and 29 ms over an edit list of 5000. Nothing is capped here, and the
# boundary is gone: 199, 200, 201, 400 and 5000 no-op edits ahead of the lift all ask.
CAP_CONTENT_FIELDS = ("content", "old_string", "new_string", "new_source")
CAP_MAX_VALUE = 60
CAP_MAX_CHANGE = 300
CAP_MAX_PATH = 200

CAP_ASK_REASON = (
    "Rule (configuration): this write sets the agent model cap, which the owner's user settings "
    "hold. A project settings file overrides user settings, so the write lifts the cap for every "
    "agent started there. Requested: {change}. File: {where}. "
    "Approve it only when a model above Sonnet is wanted for this project. "
    "(decision agent-model-cap, the owner's cap on the agent model lifts only with his word)"
)


def is_settings_file(path: str, cwd: str = "") -> bool:
    """True when the path, or the path it resolves to, names a settings file.

    The spelling is tested first, so a path that names no existing file still reads. The resolved
    spelling is tested next, which is what catches a symlink pointing at a settings file. The
    resolve is wrapped, so this predicate cannot raise.
    """
    if not path or not isinstance(path, str):
        return False
    if basename(path) in SETTINGS_BASENAMES:
        return True
    try:
        return basename(_resolved(path, cwd)) in SETTINGS_BASENAMES
    except Exception:
        return False


def _json_value_text(value) -> str:
    """Return a JSON value as text, or '' for a value that is not a scalar."""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return ""  # an object, a list or null: the key is named, the value is unread


def json_cap_values(text: str):
    """Return {key: value text} for each cap variable a JSON payload sets, else {}.

    The walk reads KEYS, so a key spelled with a JSON escape (`\\u0043LAUDE_CODE_...`) reads the
    same as a key spelled plainly, and a value the text pattern cannot read, an object or a number,
    still names its key. Content that does not parse as JSON returns {} and leaves the text passes
    to answer. The walk carries its own stack, so a deep payload cannot exhaust the interpreter's.
    """
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    found = {}
    stack = [parsed]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(key, str) and AGENT_CAP_KEY.fullmatch(key.strip()):
                    found[key.strip()] = _json_value_text(value)
                if isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(node, list):
            for value in node:
                if isinstance(value, (dict, list)):
                    stack.append(value)
    return found


def _cap_reading(text: str):
    """Return an ordered {key: value text} for ONE text, empty when it names no cap variable.

    Three passes. THE TEXT PATTERN reads a `"KEY": "value"` pair and a `KEY=value` assignment, for
    text that is no whole JSON document: an `Edit` fragment, a heredoc body, a `sed` expression. The
    LAST assignment of a key wins there, which is what a `sed -i` expression carries: the
    replacement stands after the text it replaces. THE BARE KEY catches a key whose value the
    pattern cannot read, `"$OPUS_ID"` or an opening brace, and leaves it empty, which prints as
    `(value unread)`: the guard never guesses a value the text does not carry. THE JSON WALK reads
    the keys of text that parses as JSON, and its value wins, because it is the value the file will
    hold.

    Inside one text a READABLE value wins over a bare mention, because a key named twice in one blob
    is a settings pair plus a mention of it, not a change.

    THE LIMIT: a key spelled with a JSON escape inside text that does NOT parse as JSON, a heredoc
    body on one shell line for instance, is out of reach of all three passes. The shell route reads
    the whole command, and a command is no JSON document.
    """
    reading = {}
    if not isinstance(text, str) or not text:
        return reading
    for found in AGENT_CAP_ASSIGN.finditer(text):
        reading[found.group(1)] = found.group(2)
    for found in AGENT_CAP_KEY.finditer(text):
        reading.setdefault(found.group(0), "")
    for key, value in json_cap_values(text).items():
        if value or key not in reading:
            reading[key] = value
    return reading


def cap_change_parts(parts) -> str:
    """Return a short reading of each cap variable the write sets or changes, else ''.

    A LATER PART IS AUTHORITATIVE, an unreadable value included. The parts arrive in the order the
    write applies them, `old_string` before `new_string`, edit after edit, so the last part that
    names a key is the part that decides what the file ends up holding. An `Edit` from `"sonnet"` to
    `"$OPUS_ID"` therefore reads `(value unread)`, never `sonnet`: naming the value being LEFT would
    tell the approver the opposite of what is being turned on.
    """
    order = []
    values = {}
    for part in parts:
        for key, value in _cap_reading(part).items():
            if key not in values:
                order.append(key)
            values[key] = value
    if not order:
        return ""
    printed = [key + " = " + (cap_safe(values[key], CAP_MAX_VALUE) or "(value unread)")
               for key in order]
    return cap_safe(", ".join(printed), CAP_MAX_CHANGE)


def cap_change(text: str) -> str:
    """The one-text reading, for the shell route, which judges a whole command."""
    return cap_change_parts([text])


def write_content_parts(tool_input):
    """Return the texts a write tool would put in the file, IN THE ORDER IT APPLIES THEM.

    A list, never one joined blob, so `cap_change_parts` can tell the value an edit leaves from the
    value it arrives at. Every edit of a `MultiEdit` is read: see the measurement beside
    CAP_CONTENT_FIELDS.
    """
    if not isinstance(tool_input, dict):
        return []
    parts = []
    for field in CAP_CONTENT_FIELDS:
        value = tool_input.get(field, "")
        if isinstance(value, str):
            parts.append(value)
    edits = tool_input.get("edits", [])
    if isinstance(edits, list):
        for edit in edits:
            if not isinstance(edit, dict):
                continue
            for field in CAP_CONTENT_FIELDS:
                value = edit.get(field, "")
                if isinstance(value, str):
                    parts.append(value)
    return parts


def cap_ask_reason(change: str, where: str) -> str:
    """Build the printed ask, BOUNDED BY CONSTRUCTION.

    The template is fixed, the change holds at most the cap's two keys with a value of at most
    CAP_MAX_VALUE characters each, and the path is cut at CAP_MAX_PATH. So the reason cannot run
    past roughly 800 characters however long the value or the path a tool passed. `cap_safe` does
    the cleaning and marks each cut.
    """
    return CAP_ASK_REASON.format(change=cap_safe(change, CAP_MAX_CHANGE),
                                 where=cap_safe(where, CAP_MAX_PATH))


# ---- a message that cites a record by path
RECORD_LAYOUT_FILE = os.path.join("lint", "layout.json")   # lint/check_layout.py: equals lint/layout.py LAYOUT_FILE
_RECORD_PATTERN = []


def record_folders(text):
    """The record folders a cite may not name, from the text of lint/layout.json: each kind marked
    `"record": true`, at its layout path and, when the layout keeps one, its legacy path too (a repo
    may sit on either). Raises when the text is not a layout, and the caller reads that as unread."""
    data = json.loads(text)
    legacy = data.get("legacy") or {}
    found = []
    for kind in data["kinds"].values():
        if isinstance(kind, dict) and kind.get("record") is True and isinstance(kind.get("path"), str):
            for folder in (kind["path"], legacy.get(kind["path"], kind["path"])):
                folder = folder.strip("/")
                if (folder and folder not in found
                        and re.fullmatch(r"[\w.-]+(?:/[\w.-]+)*", folder)):
                    found.append(folder)
    return found


def record_path_pattern():
    """The pattern for a repo-root record path, or None when the record folders cannot be read.

    The folders are the record kinds of lint/layout.json, read from the file. A path counts only at
    the START of a word: after a space, quote, bracket, `=` or `*` (markdown bold), with an
    optional `./`. A URL and
    `lint/decisions/x.md` have a `/` or a word before the folder, so they are not repo-root record
    paths and stay allowed. A layout path such as `docs/decisions/0001.md` is a record path.
    """
    if _RECORD_PATTERN:
        return _RECORD_PATTERN[0]
    for root in settings_roots():
        try:
            with open(os.path.join(root, RECORD_LAYOUT_FILE), encoding="utf-8") as handle:
                names = record_folders(handle.read(MESSAGE_FILE_MAX))
        except Exception:
            continue
        if names:
            pattern = re.compile(
                r"(?:^|(?<=[\s\"'`(\[<,;=@*]))(?:\./)?(?:" + "|".join(map(re.escape, names))
                + r")/[\w.-]+\.md\b")
            _RECORD_PATTERN.append(pattern)
            return pattern
    return None
DROPS_LINES_PATH = re.compile(r"(?im)^(drops-lines[ \t]*:[ \t]*)(\S+)(?=[ \t]+--[ \t]+\S)")
MESSAGE_VALUE_FLAGS = {"--message", "--body"}
MESSAGE_FILE_FLAGS = {"--file", "--body-file"}
TITLE_FLAGS = {"--title", "--subject"}
MESSAGE_FILE_MAX = 64 * 1024

CITE_REASON = (
    "Rule (Git): this message cites a record by its path. A record is cited by its id, with a "
    "short gloss, like \"D12, short titles for records\". "
    "Remedy: write the id the record carries, or its slug while the number is unclaimed, "
    "and leave the folder and the file extension out. Only a commit's last-paragraph trailer "
    "`Drops-lines: <path> -- <reason>` may name a path. "
    "(rule git-cite-by-id, cite a record by its id, never by its path)"
)


# The short flags of each act, from `git commit -h` and `gh pr <act> --help`. "text" and "file"
# carry the message, "title" a gh title or squash subject. "value" takes a value that is no message,
# glued or the next argument (`-Bmain`, `-B main`), and "glued" takes only a glued one (`-uno`). A
# letter not named takes no value, so the walk over a cluster goes on past it (`-am x`, `-db x`).
# In gh, `-m` is a milestone, or a merge with no value: never a message.
SHORT_FLAGS = {
    "commit": dict(m="text", F="file", C="value", c="value", t="value", u="glued", S="glued"),
    "create": dict(b="text", F="file", t="title", a="value", B="value", H="value", l="value",
                   m="value", p="value", r="value", R="value", T="value"),
    "edit": dict(b="text", F="file", t="title", B="value", m="value", R="value"),
    "merge": dict(b="text", F="file", t="title", A="value", R="value"),
}


def message_sources(args, act, titles=False):
    """Return (texts, files, stdin) the message flags of a commit or PR call carry.

    `texts` are the inline values, `files` the named files, `stdin` True for `-F -`. Reads a long
    flag (`--message x`, `--message=x`) or any unique prefix of one of at least four characters
    (git takes `--mess=x`), and a short cluster such as `-am x`, `-amx`, `-mx`, `-m=x`, `-bx`,
    `-Fx`: the walk reads each letter of `act`'s SHORT_FLAGS until one takes a value, and what
    follows it is the value. A letter whose value is no message ends the walk, so `-BmN20` (base
    `mN20`) holds no message. `titles` also reads `--title`, `--subject` and `-t`, which are a gh call's title or squash
    subject (a commit's `-t` is a template file, so a commit never passes it).
    """
    texts, files, stdin = [], [], False
    names = MESSAGE_VALUE_FLAGS | MESSAGE_FILE_FLAGS | (TITLE_FLAGS if titles else set())
    index = 0
    while index < len(args):
        arg = args[index]
        index += 1
        name = value = None
        if arg.startswith("--"):
            flag, equals, glued = arg.partition("=")
            hits = [n for n in names if n == flag] or \
                [n for n in names if len(flag) >= 4 and n.startswith(flag)]
            if len(hits) != 1:
                continue
            name = hits[0]
            value = glued if equals else None
        elif re.match(r"^-[A-Za-z]", arg):
            for pos, letter in enumerate(arg[1:], 1):
                role = SHORT_FLAGS[act].get(letter)
                if role == "title":
                    role = "text" if titles else "value"
                if role is None:
                    continue
                rest = arg[pos + 1:]
                if role in ("text", "file"):
                    name = "--file" if role == "file" else letter
                    value = (rest[1:] if rest.startswith("=") else rest) if rest else None
                elif role == "value" and not rest:
                    index += 1   # its value is the next argument, never a flag
                break
        if name is None:
            continue
        if value is None:
            value = args[index] if index < len(args) else ""
            index += 1
        if name not in MESSAGE_FILE_FLAGS:
            texts.append(value)
        elif value == "-":
            stdin = True
        else:
            files.append(value)
    return texts, files, stdin


UNREAD_MARK = "\0unread:"
UNREAD_REASON = (
    "Rule (Git): the message file could not be read, so the guard cannot tell whether it cites a "
    "record by its path. "
    "Remedy: pass the message inline, or name a file this directory can read. "
    "(decision cite-by-id-refuses-unread-file, an unread message file is refused, not passed)"
)


def heredoc_offsets(segments, ends, bodies_kept=True):
    """Return, for each segment, the count of heredoc headers ahead of it (own_heredoc_bodies's
    `before`). A line inside a body is no header: `x = 1 << y` in `python3 - <<'EOF'` would shift the
    count and make the commit after it read the wrong body. A body runs from the line after its
    header, to a segment that is its delimiter.
    `bodies_kept` is false when the segments come from a command whose bodies were stripped: no body is in them to skip."""
    offsets, heads, queue, reading = [], 0, [], False
    for segment, end in zip(segments, ends):
        offsets.append(heads)
        if reading:
            if segment.strip() == queue[0]:
                queue.pop(0)
                reading = bool(queue)
        else:
            found = [delimiter for _, delimiter in heredoc_heads(segment)[0]]
            heads += len(found)
            # a body that opens and closes inside one quoted segment (`-m "$(cat <<EOF ... EOF`) is whole
            queue += [d for d in found if not any(line.strip() == d for line in segment.split("\n")[1:])]
            reading = bodies_kept and bool(queue) and end == "\n"
    return offsets


def own_heredoc_bodies(segment: str, raw: str, before: int):
    """Return the bodies of the heredocs whose headers sit inside this segment, in order. A heredoc
    of another command (`cat <<A && git commit -F - <<B`) is not the message.

    `before` is the count of headers in the segments ahead of this one. Raw is walked as the
    shell reads it (_split_heredocs): each header outside quotes and comments takes the next body
    in turn, and a body line is never read for headers. This segment takes the bodies `before`
    onward, one per header it holds, so two commits with the same text each take their own body.
    Raw is walked twice, bash's reading and the contraction reading, as split_segments does, and
    the bodies of both are judged: a lone `'` can hide a header from one reading, never both.
    """
    count = len(heredoc_heads(segment)[0])
    if not count:
        return []
    texts = []
    for contractions_are_text in (False, True):   # bash's reading, then the contraction reading
        found = [body for _, body, _ in _split_heredocs(raw, contractions_are_text)[1]]
        texts.extend(found[before:before + count])
    return list(dict.fromkeys(texts))   # the readings often agree: judge each body once


def message_texts(segment: str, raw: str, where: str, before: int, titles: bool = False):
    """Return (is_commit, texts, unread) for a `git commit` or `gh pr create|edit` segment, or None
    when the segment is neither. `titles` also takes `gh pr merge`, whose squash subject and body
    become a commit on main. `unread` is the name of a message file that could not be read, else
    ''. An unread message is not a clean one.

    A heredoc body belongs to the act only when the segment itself carries the `<<` header, so a
    heredoc that writes a record file never counts. `before` is the count of heredoc headers in the
    segments ahead of this one (own_heredoc_bodies).
    """
    call = git_call_of(segment)
    if call is not None:
        if call[0] != "commit":
            return None
        args = call[1]
    else:
        rest = gh_call_of(segment)
        acts = (["create"], ["edit"]) + ((["merge"],) if titles else ())
        if rest is None or rest[:1] != ["pr"] or rest[1:2] not in acts:
            return None
        args = rest[2:]
    act = "commit" if call is not None else rest[1]
    texts, files, stdin = message_sources(args, act, titles=titles and call is None)
    for name in files:
        if is_env(name):
            continue   # never opened here: the environment-file rule judges it, and refuses
        try:
            with open(os.path.normpath(_absolute(name, where)), encoding="utf-8",
                      errors="replace") as handle:
                texts.append(handle.read(MESSAGE_FILE_MAX))
        except Exception:
            return call is not None, texts, name   # unknown, never a pass
    if "<<" in segment:
        texts.extend(own_heredoc_bodies(segment, raw, before))
    return call is not None, texts, ""


def cited_record_path(segment: str, raw: str, where: str, before: int) -> str:
    """Return the first record path a commit message or PR body cites, else ''. A message file
    that cannot be read returns UNREAD_MARK + its name.

    Acts: `git commit` and `gh pr create|edit`.
    """
    read = message_texts(segment, raw, where, before)
    if read is None:
        return ""
    is_commit, texts, unread = read
    if unread:
        return UNREAD_MARK + unread
    pattern = record_path_pattern()
    if pattern is None:
        # An unread folder list is logged, as every unread subject is, and the rule stands down.
        record("Bash", "noted", "subject-unread", "cite-by-id: record folders unread")
        return ""
    if is_commit:
        # Owner ruling 2026-10-12: a commit's trailer `Drops-lines: <path> -- <reason>`, the shape
        # lint/check_silent_undo.py reads, may name its path. Git joins -m values as paragraphs and
        # reads trailers from the last one only, never from a lone subject. Only a token that is one
        # whole record path is blanked: `a.md,b.md` stays judged, as the lint keys on the token.
        paras = re.split(r"\n\s*\n", "\n\n".join(texts).strip())
        if len(paras) > 1:
            paras[-1] = DROPS_LINES_PATH.sub(
                lambda m: m.group(1) if pattern.fullmatch(m.group(2)) else m.group(0), paras[-1])
        texts = ["\n\n".join(paras)]
    for text in texts:
        found = pattern.search(norm(text))
        if found:
            return found.group(0)
    return ""


# ---- a message that names a lane by its session number
LANE_NUMBER = re.compile(r"\bN\d{1,3}b?\b")
LANE_QUOTED = re.compile(
    r"^[ \t]*(```|~~~).*?^[ \t]*\1|(?<!`)(`+)(?!`)[^\n]*?(?<!`)\2(?!`)", re.MULTILINE | re.DOTALL)
LANE_REASON = (
    "Rule (Git): this message names a lane by a session number. That number is handed out in one "
    "chat and means nothing outside it. "
    "Remedy: name the lane by its branch slug, like \"lane-number-cite\". A number inside a "
    "backtick code span or a fenced block is quoted text and stays allowed. "
    "(decision lane-by-slug, a lane is named by its branch slug, never by a session number)"
)


def lane_number_named(segment: str, raw: str, where: str, before: int) -> str:
    """Return the first session-number lane name (`N20`) in a commit message, PR body or title, or
    `gh pr merge` subject or body, else ''. Fenced blocks and backtick spans are quoted text and
    skipped. Same text extraction as cite-by-id. An unread message file returns UNREAD_MARK + its
    name: cite-by-id refuses an unread create or edit file first, so this covers merge.
    """
    read = message_texts(segment, raw, where, before, titles=True)
    if read is None:
        return ""
    if read[2]:
        return UNREAD_MARK + read[2]
    for text in read[1]:
        found = LANE_NUMBER.search(LANE_QUOTED.sub(" ", text))
        if found:
            return found.group(0)
    return ""


TEST_BASENAME = re.compile(
    r"^(?:test_.*\.py|.*_test\.(?:py|go)|.*\.test\.[cm]?[jt]sx?|.*\.spec\..+|conftest\.py"
    r"|jest\.setup\..+|(?:.*[-_]selftest|selftest_.*)\.(?!md$).+"
    # Shell/PowerShell test suites (incident 2026-10-03): `test_*.sh`, `*_test.sh`, `*.test.ps1`,
    # `*.Tests.ps1` (match runs on the lowercased basename, so `.Tests.ps1` arrives as `.tests.ps1`).
    r"|test_.*\.sh|.*_test\.sh|.*\.tests?\.ps1"
    r"|test_.*\.(?:[cm]js|[jt]sx?))$")
# SELF-TEST files (`*-selftest.*`, `*_selftest.*`, `selftest_*.*`) are test paths, except .md notes.
# `selftestify.py`, `myselftest.py` and a bare `scripts/selftest` match no shape.
# Case matters: `FooTest.java` is a test, `Contest.java` is not.
JAVA_TEST = re.compile(r"^\w*Tests?\.java$")
SWIFT_TEST = re.compile(r"^\w+Tests\.swift$")
XCODE_TEST_DIR = re.compile(r"^[A-Z]\w*Tests$")
TEST_DIRS = {"tests", "test", "__tests__", "spec", "testdata", "__snapshots__", "test_support"}
# Dependency lists only a test-author owns. A builder may add a dev dependency.
AUTHOR_BASENAMES = {"requirements-dev.txt"}
# The three mutation tests are test code for a test-author, named one by one so a later product
# mutate_*.py stays a builder's. A builder keeps editing them: they are not test paths. Case folds as in `is_test_rel`.
AUTHOR_MUTATION_TESTS = {"hooks/mutate_guard.py", "hooks/mutate_shared.py", "janitor/mutate_sweep.py"}
TEST_CONFIG = re.compile(
    r"^(?:pytest\.ini|tox\.ini|setup\.cfg|pyproject\.toml|package\.json"
    r"|(?:jest|vitest|playwright|karma)\.conf(?:ig)?\.\w+|vitest\.workspace\.\w+|\.mocharc(?:\.\w+)?|[^/]+\.xctestplan)$")
# What disables tests. NAMES are test-runner settings that no lint tool shares, so they count in any
# test config. FLAGS (`--ignore` is also ruff's and flake8's) count only in a test-runner context:
# pytest `addopts`, a `[tool.pytest*]` section, or a line that calls a test runner.
TEST_DISABLE_NAMES = re.compile(
    r"collect_ignore|norecursedirs|testpaths|skippedTests|testPathIgnorePatterns|testIgnore|testMatch"
    r"|testRegex|xfail|passWithNoTests"
    r"|pytest\.(?:mark\.)?skip|unittest\.(?:skip|expectedFailure)|\.skip\(|\bx(?:it|describe)\("
    r"|\bt\.Skip(?:Now)?\(")
TEST_DISABLE_FLAGS = re.compile(
    r"--(?:deselect|ignore|ignore-glob|collect-only)(?![\w-])|-p\s+no:|-[km]\s*['\"]?not\b")
TEST_RUNNER_CONTEXT = re.compile(
    r"addopts|\b(?:pytest|py\.test|jest|vitest|mocha|playwright|karma)\b|go\s+test")


def disables_tests(new_lines, old_lines) -> bool:
    """True when the ADDED lines (those of `new_lines` not in `old_lines`) disable tests."""
    section = ""
    for index, line in enumerate(new_lines):
        header = re.match(r"^\s*\[([^\]]+)\]", line)
        if header:
            section = header.group(1)
        if line in old_lines:
            continue
        if TEST_DISABLE_NAMES.search(line):
            return True
        if TEST_DISABLE_FLAGS.search(line) and (
                "pytest" in section
                or any(TEST_RUNNER_CONTEXT.search(near) for near in new_lines[max(0, index - 3):index + 1])):
            return True
    return False
BUILDER_TEST_REASON = (
    "A builder does not change tests or test config. Report the needed test change in your "
    "report. The orchestrator assigns it to a test-author."
    " A merge conflict in a test file takes the same route."
    " (decision builders-cannot-edit-tests, a builder never changes a test or test config)"
)
AUTHOR_SCOPE_REASON = (
    "A test-author changes only tests and test config. Report the needed product change in your "
    "report. The orchestrator assigns it to a builder."
)
WRITER_SCOPE_REASON = (
    "A record-writer changes only Markdown (*.md) files. Report the needed change to any other "
    "file in your report. The orchestrator assigns it to a builder."
)
DESIGNER_SCOPE_REASON = (
    "A designer changes only files in the repo's design folder. Report the needed change to any "
    "other file in your report. The orchestrator assigns it to a builder."
)


def is_test_rel(rel: str) -> bool:
    """True when a repository-relative path is a test path (see the block comment above)."""
    parts = [part for part in norm(rel).split("/") if part]
    return bool(parts) and (
        bool(TEST_BASENAME.match(parts[-1].lower())) or bool(JAVA_TEST.match(parts[-1]))
        or bool(SWIFT_TEST.match(parts[-1])) or any(XCODE_TEST_DIR.match(p) for p in parts)
        or _in_test_dir(parts)
    )


# `spec` is a test folder for code (`spec/foo_spec.rb`) and for its fixtures, but a Markdown or text
# file there is a document (`docs/spec/api.md`), not a test.
SPEC_DOC_EXTENSIONS = {".md", ".mdx", ".markdown", ".txt", ".rst", ".adoc"}


def _in_test_dir(parts) -> bool:
    for index, part in enumerate(parts):
        name = part.lower()
        if name not in TEST_DIRS:
            continue
        if (name == "spec" and index < len(parts) - 1
                and os.path.splitext(parts[-1])[1].lower() in SPEC_DOC_EXTENSIONS):
            continue
        return True
    return False


def is_test_config_rel(rel: str) -> bool:
    return bool(TEST_CONFIG.match(basename(rel)))


def author_path_ok(rel: str) -> bool:
    """A test-author may change a test path, test config, or a dev dependency list. `package.json`
    and `pyproject.toml` pass here and are read by content in `role_offences`. A workflow does not pass
    here: its whole test-run steps pass in `role_write_hit` and `role_offences` (`workflow_test_steps_only`)."""
    return (is_test_rel(rel) or is_test_config_rel(rel) or basename(rel) in AUTHOR_BASENAMES
            or norm(rel).lstrip("/").lower() in AUTHOR_MUTATION_TESTS)


# ---- workflow files (decision builders-cannot-edit-tests). The test-author check and the builder check are two
# verdicts that share the step and run readers below. A test-author changes a workflow only by adding, removing or
# moving whole test-run steps, so a new suite gets its CI step. A builder changes any workflow line, except one
# that disables tests or drops a test run.
WORKFLOW_REL = re.compile(r"^\.github/workflows/[^/]+\.ya?ml$")
# The only keys a test-run step holds. `continue-on-error`, `env`, `uses`, `with` are no test-run key.
WORKFLOW_STEP_KEYS = {"name", "if", "run", "shell", "working-directory", "timeout-minutes"}
WORKFLOW_STEP_START = re.compile(r"^(\s*)-\s+(name|run):")
WORKFLOW_KEY_LINE = re.compile(r"^(\s*)(?:-\s+)?([A-Za-z][\w-]*):\s*(.*)$")
WORKFLOW_INTERPRETERS = {"python", "python3", "node", "bash", "sh", "pwsh"}
# Interpreter flags whose next token is their value, not the script (`python -X utf8`, `node -r ts-node/register`).
WORKFLOW_VALUE_FLAGS = {"-X", "-W", "-r", "--require", "--import", "-o"}
# Interpreter flags after which a command or module follows, so no script path does (`python -m`, `bash -c`).
WORKFLOW_NO_PATH_FLAGS = {"-c", "-m"}
WORKFLOW_DISABLE_STEP = re.compile(
    r"^\s*(?:-\s+)?(?:continue-on-error:\s*(?:true|\$\{\{\s*true\s*\}\})|if:\s*(?:false|\$\{\{\s*false\s*\}\}))\s*$")


def is_workflow_rel(rel: str) -> bool:
    """True when a repository-relative path is a GitHub workflow file (`.github/workflows/*.yml|*.yaml`)."""
    return bool(WORKFLOW_REL.match(norm(rel).lstrip("/").lower()))


def workflow_path(token: str) -> str:
    """One spelling of a path a run line names: `\\` as `/`, no leading `./`."""
    token = token.replace("\\", "/")
    while token.startswith("./"):
        token = token[2:]
    return token


def workflow_script_index(args):
    """The index in `args` (the tokens after an interpreter) of the script it runs: the first token past the
    interpreter's flags and their values, or None when a `-c` or `-m` runs a command or module instead."""
    index = 0
    while index < len(args) and args[index].startswith("-"):
        if args[index] == "--":
            index += 1
            break
        if args[index] in WORKFLOW_NO_PATH_FLAGS:
            return None
        index += 2 if args[index] in WORKFLOW_VALUE_FLAGS else 1
    return index if index < len(args) else None


def workflow_step_disables(line: str) -> bool:
    """True when one step line is `continue-on-error: true` or `if: false`, so the step runs no test that counts."""
    return bool(WORKFLOW_DISABLE_STEP.match(line))


def workflow_run_is_test(value: str) -> bool:
    """True when one single-line `run:` value is `[interpreter] <test path> [args]` and nothing else.
    A tokenizer that keeps quotes whole judges it, so a `#` or `//` in quotes is an argument and an
    unquoted `&&`, `;`, `|`, redirect or `$(` is a token of its own that no test run holds."""
    value = value.strip()
    if not value or value[0] in "|>\"'&*!%@`" or "$(" in value or "`" in value:
        return False
    lexer = shlex.shlex(value, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        tokens = list(lexer)
    except ValueError:
        return False
    if any(set(tok) <= set(lexer.punctuation_chars) for tok in tokens):
        return False
    script = 0
    if tokens and tokens[0] in WORKFLOW_INTERPRETERS:
        tokens = tokens[1:]
        script = workflow_script_index(tokens)
    if script is None or not tokens or ".." in norm(tokens[script]).split("/") or not is_test_rel(tokens[script]):
        return False
    rest = tokens[:script] + tokens[script + 1:]
    return not TEST_DISABLE_FLAGS.search(" ".join(rest)) and not disables_tests([value], [])


def workflow_test_step(lines) -> bool:
    """True when `lines` (non-blank) are exactly one whole test-run step."""
    start = WORKFLOW_STEP_START.match(lines[0]) if lines else None
    if not start:
        return False
    keys = []
    for line in lines:
        found = WORKFLOW_KEY_LINE.match(line)
        if not found or found.group(2) not in WORKFLOW_STEP_KEYS or (
                line is not lines[0] and (len(found.group(1)) <= len(start.group(1)) or line.lstrip().startswith("- "))):
            return False
        keys.append((found.group(2), found.group(3)))
        if disables_tests([line], []) or workflow_step_disables(line):
            return False
    runs = [value for key, value in keys if key == "run"]
    return len(runs) == 1 and len(set(key for key, _ in keys)) == len(keys) and workflow_run_is_test(runs[0])


def workflow_step_chunk(lines) -> bool:
    """True when the non-blank `lines` split into whole test-run steps, each starting at a step line."""
    lines = [line for line in lines if line.strip()]
    if not lines:
        return True
    indent = len(WORKFLOW_STEP_START.match(lines[0]).group(1)) if WORKFLOW_STEP_START.match(lines[0]) else None
    if indent is None:
        return False
    steps = []
    for line in lines:
        starts = WORKFLOW_STEP_START.match(line)
        if starts and len(starts.group(1)) == indent:
            steps.append([line])
        else:
            steps[-1].append(line)
    return all(workflow_test_step(step) for step in steps)


def workflow_changed_lines(old_text: str, new_text: str):
    """The (removed, added) line groups of a diff from `old_text` to `new_text`, one pair per change."""
    old, new = old_text.splitlines(), new_text.splitlines()
    ops = difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes()
    return [(old[i1:i2], new[j1:j2]) for tag, i1, i2, j1, j2 in ops if tag != "equal"]


def workflow_test_steps_only(old_text: str, new_text: str) -> bool:
    """True when every added and removed non-blank line of the change forms whole test-run steps."""
    return all(workflow_step_chunk(removed) and workflow_step_chunk(added)
               for removed, added in workflow_changed_lines(old_text, new_text))


WORKFLOW_COMMAND_SPLIT = re.compile(r"&&|\|\||[;|]")
WORKFLOW_RUN_PREFIX = re.compile(r"^\s*(?:-\s+)?run:\s*")
WORKFLOW_RUN_BLOCK = re.compile(r"^(\s*)(?:-\s+)?run:\s*[|>][+-]?\s*$")


def workflow_command_tests(command: str) -> set:
    """The test paths one shell command line runs, each in its `workflow_path` spelling: the script an
    interpreter runs past its flags, every test path after a test runner, or the command itself when it is a
    test path. A lint tool that is given a test folder (`ruff check tests/`) runs none."""
    found = set()
    for segment in WORKFLOW_COMMAND_SPLIT.split(command):
        tokens = [tok.strip("\"'") for tok in segment.split()]
        while tokens and (re.match(r"^\w+=", tokens[0]) or tokens[0] in ("npx", "sudo", "time")):
            tokens.pop(0)
        if not tokens:
            continue
        runner = bool(TEST_RUNNER_CONTEXT.search(segment))
        if tokens[0] in WORKFLOW_INTERPRETERS:
            script = workflow_script_index(tokens[1:])
            args = tokens[1:] if runner else ([] if script is None else [tokens[1 + script]])
        else:
            args = tokens if runner else tokens[:1]
        found.update(workflow_path(tok) for tok in args if is_test_rel(workflow_path(tok)))
    return found


def workflow_run_commands(text: str):
    """The command lines of every `run:` in `text`: an inline value, or each line of a block scalar."""
    commands, block = [], None
    for line in text.splitlines():
        if block is not None:
            if not line.strip() or len(line) - len(line.lstrip()) > block:
                commands.append(line.strip())
                continue
            block = None
        opened = WORKFLOW_RUN_BLOCK.match(line)
        if opened:
            block = len(opened.group(1)) + (2 if line.lstrip().startswith("- ") else 0)
        elif WORKFLOW_RUN_PREFIX.match(line):
            commands.append(WORKFLOW_RUN_PREFIX.sub("", line, count=1))
    return commands


def workflow_invoked_tests(text: str) -> set:
    """Every test path a `run:` line of the workflow text runs."""
    return set().union(set(), *(workflow_command_tests(cmd) for cmd in workflow_run_commands(text)))


def workflow_command_is_test(command: str) -> bool:
    return bool(workflow_command_tests(command) or TEST_RUNNER_CONTEXT.search(command))


def workflow_added_indexes(old_text: str, new_text: str):
    """The line numbers of `new_text` that the change from `old_text` adds."""
    ops = difflib.SequenceMatcher(None, old_text.splitlines(), new_text.splitlines(), autojunk=False).get_opcodes()
    return [index for tag, _i1, _i2, j1, j2 in ops if tag != "equal" for index in range(j1, j2)]


def workflow_step_lines(lines, index: int):
    """The lines of the step (or job) that holds `lines[index]`: those at the key's indent or deeper, up to
    and with the `- ` line that opens the step. A fragment ends at its own first and last line."""
    def indent(line):
        return len(line) - len(line.lstrip())
    key = indent(lines[index]) + (2 if lines[index].lstrip().startswith("- ") else 0)
    start = index
    while start > 0 and not lines[start].lstrip().startswith("- "):
        above = lines[start - 1]
        if above.strip() and indent(above) < key:
            start = start - 1 if above.lstrip().startswith("- ") and indent(above) == key - 2 else start
            break
        start -= 1
    end = index + 1
    while end < len(lines) and (not lines[end].strip() or indent(lines[end]) >= key):
        end += 1
    return lines[start:end]


def workflow_disables_tests(old_text: str, new_text: str) -> bool:
    """True when an added line of the change disables tests: a disable name or flag on a line that calls
    a test runner or runs a test path through an interpreter."""
    for _removed, added in workflow_changed_lines(old_text, new_text):
        for line in added:
            if (TEST_DISABLE_NAMES.search(line) or TEST_DISABLE_FLAGS.search(line)) and (
                    TEST_RUNNER_CONTEXT.search(line)
                    or workflow_command_tests(WORKFLOW_RUN_PREFIX.sub("", line, count=1))):
                return True
    return False


def workflow_disables_step(old_text: str, new_text: str) -> bool:
    """True when the change adds `continue-on-error: true` or `if: false` to a step that runs tests."""
    lines = new_text.splitlines()
    return any(
        workflow_step_disables(lines[index])
        and any(workflow_command_is_test(cmd) for cmd in workflow_run_commands("\n".join(workflow_step_lines(lines, index))))
        for index in workflow_added_indexes(old_text, new_text))


def workflow_drops_tests(old_text: str, new_text: str) -> bool:
    """True when a test path that a run line runs in `old_text` is run nowhere in `new_text`."""
    return bool(workflow_invoked_tests(old_text) - workflow_invoked_tests(new_text))


def workflow_builder_refused(old_text: str, new_text: str) -> bool:
    """The one verdict on a builder's workflow change, for the write tools and the commit diff."""
    return (workflow_disables_tests(old_text, new_text) or workflow_disables_step(old_text, new_text)
            or workflow_drops_tests(old_text, new_text))


def workflow_pairs(tool_input, full: str):
    """The (old, new) texts a write tool call makes of a workflow: an Edit's old and new string, each edit
    of a MultiEdit, a Write's file on disk (empty if none) and its content; None when the call has none."""
    if not isinstance(tool_input, dict):
        return None
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        pairs = [(e.get("old_string"), e.get("new_string")) for e in edits if isinstance(e, dict)]
    elif "old_string" in tool_input or "new_string" in tool_input:
        pairs = [(tool_input.get("old_string"), tool_input.get("new_string"))]
    elif "content" in tool_input:
        try:
            with open(full, encoding="utf-8", errors="replace") as handle:
                disk = handle.read()
        except Exception:
            disk = ""
        pairs = [(disk, tool_input.get("content"))]
    else:
        return None
    if not pairs or any(not isinstance(o, str) or not isinstance(n, str) for o, n in pairs):
        return None
    return pairs


def design_folder():
    """The repo-relative design folder, lower case, from the `design` kind of lint/layout.json (the
    file RECORD_LAYOUT_FILE names), or None when no settings clone holds a readable layout. The
    layout keeps no legacy path for it, so every repo keeps it at the layout path."""
    if _DESIGN_FOLDER:
        return _DESIGN_FOLDER[0]
    for root in settings_roots():
        try:
            with open(os.path.join(root, RECORD_LAYOUT_FILE), encoding="utf-8") as handle:
                found = json.load(handle)["kinds"]["design"]["path"]
        except Exception:
            continue
        if isinstance(found, str) and found.strip("/"):
            _DESIGN_FOLDER.append(found.strip("/").lower())
            return _DESIGN_FOLDER[0]
    return None


_DESIGN_FOLDER = []


def designer_path_ok(rel: str) -> bool:
    """True when a repository-relative path sits inside the design folder. The case is folded,
    because the folder is one folder on a case-insensitive disk. An unread layout allows nothing."""
    folder = design_folder()
    parts = [part for part in norm(rel).lower().split("/") if part]
    if folder is None or ".." in parts:
        return False
    return "/".join(parts).startswith(folder + "/")


def drive_form_cwd(cwd: str) -> str:
    """A Git Bash `/c/Users/...` cwd in drive form (`C:/Users/...`) on Windows, else `cwd` as given.
    Off Windows `/c/` is a real folder. `_expanded` is the one reader of the drive spelling."""
    return _expanded(cwd, "") if cwd and os.name == "nt" else cwd


def repo_rel(path: str, cwd: str, outside: bool = True):
    """The path relative to its repository root (the nearest parent holding `.git`), posix, or the
    full path when it sits in no repository (`outside` False: None there). None when it cannot be
    read."""
    if not path or not isinstance(path, str):
        return None
    try:
        # Case kept: normcase would lowercase on Windows and break the case-sensitive Xcode/Java tests.
        full = norm(os.path.normpath(_expanded(path, cwd)))
    except Exception:
        return None
    parent = os.path.dirname(full)
    while parent and parent != os.path.dirname(parent):
        if os.path.exists(os.path.join(parent, ".git")):
            return full[len(parent):]
        parent = os.path.dirname(parent)
    return full if outside else None


def builder_test_path(path: str, cwd: str) -> bool:
    """True when `path` is a test path a builder may not change. The one predicate the Edit and Write
    tools (`role_write_hit`) and a shell write (`builder_shell_test_hit`) both ask. Test config that
    disables tests is judged on content, so only the Edit tools read it."""
    rel = repo_rel(path, cwd)
    if rel is None:
        return False
    # From a call that runs in a repository, a path in no repository is no test of it, as for the test-author
    # in role_write_hit. From a call in no repository nothing says which paths are outside, so the shape decides.
    # Both reads take cwd in drive form: a `/c/` cwd read raw hides its own repo from the target
    # read but not from the probe, and the target would then count as outside.
    where = drive_form_cwd(cwd)
    if (repo_rel(os.path.join(where or "", "x"), where, outside=False) is not None
            and repo_rel(path, where, outside=False) is None):
        return False
    return is_test_rel(rel)


def builder_shell_test_hit(raw: str, stripped: str, cwd: str) -> str:
    """The test path a builder's shell command writes, else ''. Two readings: the plain forms (a
    redirect, `tee`, `sed -i`, `cp`, a heredoc header) on the heredoc-stripped command, and the
    python or node script a heredoc body or `-c` / `-e` holds, on the raw command."""
    return (_shell_write_hit(stripped, cwd, builder_test_path, follow_cd=True, command_position=True)
            or interpreter_write_hit(raw, cwd, builder_test_path))


def role_write_hit(role: str, tool_input, target: str, cwd: str, session_id: str = "") -> str:
    """The early warning for a write tool call: the target path a role may not change, else ''.

    A test-author may also write its own session scratchpad and any path in no repository
    (owner ruling 2026-10-13): only product code IN a repository is out of its scope."""
    rel = repo_rel(target, cwd)
    if rel is None:
        return ""
    if role in (AUTHOR_ROLE, DESIGNER_ROLE):
        full = _expanded(target, cwd)
        ok = author_path_ok if role == AUTHOR_ROLE else designer_path_ok
        if ok(rel) or under_session_scratchpad(full, session_id):
            return ""
        if role == AUTHOR_ROLE and is_workflow_rel(rel):
            pairs = workflow_pairs(tool_input, full)
            if pairs and all(workflow_test_steps_only(o, n) for o, n in pairs):
                return ""
        # `session_id` is the parent's, the same for an agent (decision
        # an-agent-outside-its-home-tree-must-stop), and so is the id in the scratchpad path.
        # Another session's scratchpad is neither this one's nor "outside a repository".
        if in_any_session_scratchpad(full):
            return target
        return "" if repo_rel(target, cwd, outside=False) is None else target
    if role == WRITER_ROLE:
        return "" if rel.lower().endswith(".md") else target
    if builder_test_path(target, cwd):
        return target
    if is_test_config_rel(rel) and any(
            disables_tests(part.splitlines(), []) for part in write_content_parts(tool_input)):
        return target
    if is_workflow_rel(rel) and any(
            workflow_builder_refused(o, n) for o, n in workflow_pairs(tool_input, _expanded(target, cwd)) or ()):
        return target
    return ""


# HEAD reflog subjects (`%gs`). The agent's own commit: `commit`, `commit (initial)`, `commit (amend)` and
# `commit (merge)`. A replay the agent resolved or chose: a hand-resolved cherry-pick, a revert, and a
# rebase step that is no plain pick. A plain cherry-pick, rebase pick or `am` copies a commit someone
# else made, and a reset, checkout, pull or clean merge hands the agent other people's commits: none is read.
ENTRY_OWN = re.compile(r"^commit(?: \((?:initial|amend|merge)\))?:")
ENTRY_REBASE = re.compile(r"^(?:pull --)?rebase\b[^:(]*\(([^)]*)\)")
ENTRY_RESOLVED = re.compile(r"^(?:commit \(cherry-pick\)|revert)\b")
REBASE_PLAIN_STEPS = ("start", "finish", "abort", "pick", "reword", "edit")
# A git-dir entry that shows a replay in progress: its staged change is git's copy plus what the agent
# resolved. A MERGE_MSG without MERGE_HEAD is a `cherry-pick -n` or `revert -n`.
REPLAY_MARKS = ("CHERRY_PICK_HEAD", "REVERT_HEAD", "SQUASH_MSG", "MERGE_MSG", "rebase-merge", "rebase-apply")
# How a builder's test path in one change counts: refused, logged, or logged as the upstream side a
# rebase kept.
OWN, NOTED, KEPT = "own", "noted", "kept"


def entry_kind(subject: str) -> str:
    """OWN, NOTED (a replay the agent resolved or chose), 'start' (a rebase start) or '' for one HEAD
    reflog subject."""
    rebase = ENTRY_REBASE.match(subject)
    if rebase:
        step = rebase.group(1).strip()
        if step.startswith("start"):
            return "start"
        return "" if step.startswith(REBASE_PLAIN_STEPS) else NOTED
    if ENTRY_OWN.match(subject):
        return OWN
    return NOTED if ENTRY_RESOLVED.match(subject) else ""


def git_names(root: str, *args):
    """The NUL-separated names one git call prints, or None when git failed."""
    answer = guard_core._git(root, *args)
    if answer is None or answer.returncode != 0:
        return None
    return [p for p in answer.stdout.split("\0") if p]


def changed_paths(root: str, old: str, new=None):
    """The paths that differ from `old` (a commit or tree) to `new` (a commit), or to the working tree
    and its untracked files when `new` is None; None when git failed."""
    if new is not None:
        return git_names(root, "diff", "--name-only", "-z", "--no-renames", old, new)
    tracked = git_names(root, "diff", "--name-only", "-z", "--no-renames", old)
    fresh = git_names(root, "ls-files", "--others", "--exclude-standard", "-z")
    if tracked is None or fresh is None:
        return None
    return tracked + sorted(fresh)


def merge_tree(root: str, ours: str, theirs: str):
    """The tree git's own merge of two commits makes, each conflict left as markers; None when git
    failed. A path that differs from it is one the agent resolved or added. Needs git 2.38 or newer
    (`merge-tree --write-tree`), and writes the merged objects to the object store."""
    answer = guard_core._git(root, "merge-tree", "--write-tree", "--no-messages", "-z", ours, theirs)
    if answer is None or answer.returncode not in (0, 1):
        return None
    return answer.stdout.split("\0", 1)[0].strip() or None


def upstream_kept(root: str, orig: str, onto: str):
    """The paths a rebase of `orig` onto `onto` replayed that hold `onto`'s bytes again in the working
    tree: the agent kept the upstream side. Empty when HEAD no longer holds `onto`; None when git
    failed."""
    held = guard_core._git(root, "merge-base", "--is-ancestor", onto, "HEAD")
    if held is None or held.returncode not in (0, 1):
        return None
    if held.returncode:
        return []
    replayed = git_names(root, "diff", "--name-only", "-z", "--no-renames", onto + "..." + orig)
    moved = git_names(root, "diff", "--name-only", "-z", "--no-renames", onto)
    if replayed is None or moved is None:
        return None
    return [p for p in replayed if p not in set(moved)]


def own_changes(root: str):
    """The agent's own change, as a list of `(old, new, paths, kind)`; None when git could not answer:
    unknown, never clear. `new` None is the working tree, and `old` '' is no commit.

    OWN (a builder's test path in it is refused):
      - each commit the agent made (HEAD reflog `commit`, `commit (amend)`, `commit (merge)`) that HEAD
        still holds, against its first parent. A merge commit is measured against git's own merge of
        its parents, so only what the agent resolved or added counts;
      - the working tree against HEAD, or, while a merge is in progress, against git's own merge of
        HEAD and MERGE_HEAD.
    NOTED (logged, never refused): a replay the agent resolved or chose (a hand-resolved cherry-pick, a
    revert, a rebase squash, fixup or continue), and the working tree while a replay is in progress.
    KEPT (logged only): a path a held rebase replayed that holds the rebase start's bytes again, as the
    builder left it during the rebase. A write of those bytes after the rebase finished is its own change:
    the working tree or a commit of its own carries it, and that is refused.
    A plain cherry-pick or rebase pick, a clean merge, a reset, a checkout and a pull are other
    people's commits, and are not read."""
    log = guard_core._git(root, "reflog", "show", "--format=%H %gs", "HEAD")
    gitdir = guard_core._git(root, "rev-parse", "--absolute-git-dir")
    merging = guard_core._git(root, "rev-parse", "-q", "--verify", "MERGE_HEAD")
    if log is None or gitdir is None or merging is None or log.returncode or gitdir.returncode:
        return None
    entries = [line.partition(" ")[::2] for line in log.stdout.splitlines() if line.strip()][::-1]
    kinds = {}
    for sha, subject in entries:
        kind = entry_kind(subject)
        if kind in (OWN, NOTED):
            kinds.setdefault(sha, kind)
    lost = set()
    if kinds:
        # `kinds --not HEAD` lists what HEAD does not reach: a commit in it was reset or amended away.
        answer = guard_core._git(root, "rev-list", *kinds, "--not", "HEAD")
        if answer is None or answer.returncode != 0:
            return None
        lost = set(answer.stdout.split())
    changes = []
    for sha, kind in kinds.items():
        if sha in lost:
            continue
        parents = guard_core._git(root, "show", "-s", "--format=%P", sha)
        if parents is None or parents.returncode != 0:
            return None
        parents = parents.stdout.split()
        if len(parents) > 2:
            return None
        old = merge_tree(root, *parents) if len(parents) == 2 else (parents[0] if parents else "")
        if old is None:
            return None
        paths = (changed_paths(root, old, sha) if old else
                 git_names(root, "diff-tree", "--root", "-r", "--name-only", "--no-commit-id", "-z",
                           "--no-renames", sha))
        if paths is None:
            return None
        changes.append((old, sha, paths, kind))
    old = "HEAD"
    if merging.returncode == 0:
        old = merge_tree(root, "HEAD", merging.stdout.strip())
        if old is None:
            return None
    paths = changed_paths(root, old)
    if paths is None:
        return None
    replaying = merging.returncode != 0 and any(
        os.path.exists(os.path.join(gitdir.stdout.strip(), mark)) for mark in REPLAY_MARKS)
    changes.append((old, None, paths, NOTED if replaying else OWN))
    for index, (sha, subject) in enumerate(entries):
        if index and entry_kind(subject) == "start":
            kept = upstream_kept(root, entries[index - 1][0], sha)
            if kept is None:
                return None
            if kept:
                changes.append((sha, None, kept, KEPT))
    return changes


def package_json_author_ok(old: str, new: str) -> bool:
    """A test-author may change `devDependencies`, `jest`, and the test scripts of a manifest, and
    nothing else in it."""
    try:
        before, after = json.loads(old), json.loads(new)
    except Exception:
        return False
    if not isinstance(before, dict) or not isinstance(after, dict):
        return False

    def scripts(manifest):
        found = manifest.get("scripts")
        found = found if isinstance(found, dict) else {}
        return {k: v for k, v in found.items() if not re.match(r"^(?:pre|post)?test", k)}

    for key in set(before) | set(after):
        if key in ("devDependencies", "jest"):
            continue
        if key == "scripts":
            if scripts(before) != scripts(after):
                return False
        elif before.get(key) != after.get(key):
            return False
    return True


def toml_sections(text: str):
    """Split TOML text into {header: body}, the lines before any header under ''."""
    sections, name = {"": []}, ""
    for line in text.splitlines():
        found = re.match(r"^\s*\[\[?([^\]]+)\]\]?\s*$", line)
        if found:
            name = found.group(1).strip()
            sections.setdefault(name, [])
        else:
            sections[name].append(line.strip())
    return {key: "\n".join(body).strip() for key, body in sections.items()}


def pyproject_author_ok(old: str, new: str) -> bool:
    """A test-author may change the `[tool.pytest*]` sections of a project file, and nothing else."""
    before, after = toml_sections(old), toml_sections(new)
    return all(before.get(key) == after.get(key)
               for key in set(before) | set(after) if not key.startswith("tool.pytest"))


def text_at(root: str, rev, rel: str) -> str:
    """The file's text at `rev` (a commit or tree), in the working tree when `rev` is None, and ''
    when it does not exist there or `rev` is '' (no commit)."""
    if rev is None:
        try:
            with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as handle:
                return handle.read()
        except Exception:
            return ""
    if not rev:
        return ""
    answer = guard_core._git(root, "show", rev + ":" + norm(rel))
    return answer.stdout if answer is not None and answer.returncode == 0 else ""


def role_offences(root: str, top: str, role: str, paths, old: str, new=None):
    """The paths among `paths`, changed from `old` to `new` (see `own_changes`), whose change the role
    may not make. Each path is checked as spelled and as resolved through symlinks."""
    found = []
    for rel in paths:
        # `is_test_rel` is the one place a backslash becomes `/`. A path outside the repository
        # reads `../...`, which no role owns.
        real = os.path.realpath(os.path.join(top, rel))
        names = [rel, os.path.relpath(real, top)]
        if role == AUTHOR_ROLE and is_workflow_rel(rel) and all(
                is_workflow_rel(n) or author_path_ok(n) for n in names):
            bad = not workflow_test_steps_only(text_at(root, old, rel), text_at(root, new, rel))
        elif role == AUTHOR_ROLE:
            bad = not all(author_path_ok(n) for n in names)
            if not bad and basename(rel) == "package.json":
                bad = not package_json_author_ok(text_at(root, old, rel), text_at(root, new, rel))
            if not bad and basename(rel) == "pyproject.toml":
                bad = not pyproject_author_ok(text_at(root, old, rel), text_at(root, new, rel))
        elif role == WRITER_ROLE:
            bad = not all(n.lower().endswith(".md") for n in names)
        elif role == DESIGNER_ROLE:
            bad = not all(designer_path_ok(n) for n in names)
        else:
            bad = any(is_test_rel(n) for n in names) or (is_test_config_rel(rel) and disables_tests(
                text_at(root, new, rel).splitlines(), text_at(root, old, rel).splitlines())) or (
                is_workflow_rel(rel) and workflow_builder_refused(text_at(root, old, rel), text_at(root, new, rel)))
        if bad:
            found.append(rel)
    return found


def diff_violation(root: str, role: str):
    """Judge the agent's own change (`own_changes`). Returns `(offence, noted)`: the first path the role
    may not change ('' when none, None when git could not answer: UNKNOWN, never clear), and the paths
    a builder changed that are logged and never refused. Every offence of another role is logged only."""
    changes = own_changes(root)
    top = guard_core._git(root, "rev-parse", "--show-toplevel")
    if changes is None or top is None or top.returncode != 0:
        return None, []
    top = os.path.realpath(top.stdout.strip())
    builder = role == BUILDER_ROLE
    noted = []
    for old, new, paths, kind in changes:
        if kind == KEPT and not builder:
            continue
        found = role_offences(root, top, role, paths, old, new)
        if found is None:
            return None, []
        for rel in found:
            if not builder or kind == OWN:
                return rel, noted
            noted.append(rel)
    return "", noted


def diff_rule(role: str) -> str:
    return {AUTHOR_ROLE: "author-diff", WRITER_ROLE: "writer-diff",
            DESIGNER_ROLE: "designer-diff"}.get(role, "builder-diff")


def builder_diff_reason() -> str:
    """The refusal text for a builder's test change. It names no path: it gives the undo route."""
    return (
        BUILDER_TEST_REASON + " The guard refuses a test change you made, at commit, push and stop. "
        "Undo it: restore each test file you changed to its text at HEAD, and delete each test file "
        "you added. If a commit of yours holds the change, stop and report it. "
        "If a merge is in progress and the refusal is about a test conflict, run `git merge --abort` "
        "and report the conflict to the orchestrator; a test-author resolves it. "
        "This refusal is final: never write the files another way. (decision builders-cannot-edit-tests)"
    )


def diff_refusal(tool: str, role: str, root: str) -> None:
    """Judge a role's own change at commit or push. A builder's test change is refused (rule `builder-diff`,
    with the undo route). A builder's logged change, any other role's offence, and a change that could
    not be read are logged for the reviewer: a refusal on an unread change would be a false alarm."""
    found, noted = diff_violation(root, role)
    if found is None:
        record(tool, "noted", "role-diff-unread", root)
    elif found and role == BUILDER_ROLE:
        # A role guard stays outside every override (decision owner-override): a refusal is final.
        guard_core.set_override_veto(lambda: True)
        refuse(tool, "deny", "builder-diff", builder_diff_reason(), found)
    elif found or noted:
        record(tool, "noted", diff_rule(role), found or noted[0])


def judge_stop(payload) -> None:
    """A builder, test-author, record-writer or designer that stops has its own change judged. A
    builder's test change is refused at the first stop (rule `builder-diff`, with the undo route). A second
    stop (`stop_hook_active`) is allowed and logs `role-diff-unresolved`, so an agent that cannot fix
    its tree never loops. A builder's logged change and the other roles' offences log under the role's
    rule and never refuse. A cwd that is the main checkout and a change that could not be read log too,
    and allow. A missing cwd logs nothing."""
    role = agent_role(payload)
    if not role:
        return
    where = str(payload.get("cwd") or "")
    if not where:
        return
    if is_worktree(where) is False:
        record("SubagentStop", "noted", "role-diff-main-checkout", where)
        return
    found, noted = diff_violation(where, role)
    if found != "" and payload.get("stop_hook_active"):
        record("SubagentStop", "noted", "role-diff-unresolved", found or "unread")
    elif found is None:
        record("SubagentStop", "noted", "role-diff-unread", where)
    elif found and role == BUILDER_ROLE:
        record("SubagentStop", "deny", diff_rule(role), found)
        print(json.dumps({"decision": "block", "reason": diff_rule(role) + ": " + builder_diff_reason()}))
        sys.exit(0)
    elif found or noted:
        record("SubagentStop", "noted", diff_rule(role), found or noted[0])


SPAWN_TOOLS = ("Agent", "Task")
SESSION_TOOL = "mcp__ccd_session__start_session"
CREATE_SESSION_TOOL = "mcp__claude-code-remote__create_session"
# The one lane effort. lint/check_agent_models.py reads it from here and checks the lane row of the model table.
LANE_EFFORT = "medium"
LANE_TAG = "cs-build:lane"
LANE_EFFORT_REASON = (
    "A lane session's start prompt is `/effort %s` alone. A slash command runs only when it is the whole "
    "prompt. Start the lane with that prompt, then send the brief by send_message (decision agent-model-cap)."
    % LANE_EFFORT
)
# A template: %s is the tag the call must carry, `cs-repo:` plus the checkout's repo, or `cs-repo:<owner>/<name>`
# when no repo reads.
LANE_REPO_TAG_REASON = (
    "A lane session carries the full `cs-repo` tag of the checkout that starts it. Add `%s` to the lane's "
    "tags. A roll-out lane carries this repo's tag beside its target's (decision session-tiers, Tier tags)."
)
# A repo tag with no origin to compare to: the full form, one owner and one name.
FULL_REPO_TAG = re.compile(r"[^/\s]+/[^/\s]+")
# The one list of roles that may run Haiku. lint/check_agent_models.py reads it from here.
HAIKU_ROLES = ("Explore", "claude-code-guide", "test-author", "reviewer", "record-writer")
MODEL_FLOOR_REASON = (
    "Sonnet is the floor for this role. Start the agent or session with model sonnet, "
    "or name no model and let the default apply."
)
AGENT_CALL = re.compile(r"\bagent\s*\(")
SCRIPT_PAIR = re.compile(r"(?:(\w+)|\x00(\d+)\x00)\s*:\s*\x00(\d+)\x00")


def script_opts(text: str, start: int):
    """Yield the string-valued keys of each object literal that is a direct argument of the call
    whose arguments open at `start`."""
    depth, top, i = 1, [], start
    while i < len(text) and depth:
        ch = text[i]
        if ch in "([{":
            if ch == "{" and depth == 1:
                top.append([i + 1, ""])
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if ch == "}" and depth == 1 and top and top[-1][1] == "":
                top[-1][1] = text[top[-1][0]:i]
        i += 1
    for _, body in top:
        flat, level = [], 0
        for ch in body:
            level += ch in "([{"
            flat.append(ch if level == 0 else " ")
            level -= ch in ")]}"
        yield "".join(flat)


SCRIPT_KEY = re.compile(r"(?:(\w+)|\x00(\d+)\x00)\s*:(.*)\Z", re.DOTALL)
SCRIPT_TOKEN = re.compile(r"\s*\x00(\d+)\x00\s*\Z")
SCRIPT_FIRST_ARG = re.compile(r"\s*\x00(\d+)\x00")
SCRIPT_ARG_END = re.compile(r"\s*[,)]")
SCRIPT_ESCAPE = re.compile(r"\\(.)", re.DOTALL)
SCRIPT_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "v": "\v", "f": "\f", "b": "\b", "0": "\0", "\n": ""}


def script_group_end(text: str, i: int) -> int:
    """The index after the balanced "(...)" group that opens at i, or -1."""
    if i < 0 or not text.startswith("(", i):
        return -1
    depth = 0
    for j in range(i, len(text)):
        depth += {"(": 1, ")": -1}.get(text[j], 0)
        if depth == 0:
            return j + 1
    return -1


def script_agent_calls(script: str):
    """Yield (prompt, bodies) for each agent() call in a Workflow script. `prompt` is the first argument when
    it is one string literal, or the `prompt` key of a first-argument options object; else None. A template's
    `${...}` reads as a \\x00, so only its static text can hold a marker. Escapes are decoded, so a `\\n`
    starts a line. `bodies` holds (keys, unseen, literals) per options object: `keys` maps each key to its
    string-literal value; `unseen` names each key whose value is not one plain string literal, plus "..." for
    a spread, shorthand, computed key or method; `literals` maps each key whose value is one string or
    template literal to its masked entry."""
    text, strings = mask_script(script)

    def read(k):
        v = strings[int(k)]
        return v if isinstance(v, str) else script[v[0]:v[1]]

    def plain(v):
        v = v if isinstance(v, str) else v[2]
        return SCRIPT_ESCAPE.sub(lambda m: SCRIPT_ESCAPES.get(m.group(1), m.group(1)), v)

    for call in AGENT_CALL.finditer(text):
        bodies = []
        for body in script_opts(text, call.end()):
            keys, unseen, literals = {}, set(), {}
            for name, quoted, value in SCRIPT_PAIR.findall(body):
                keys[name or read(quoted)] = read(value)
            for part in filter(None, (p.strip() for p in body.split(","))):
                pair = SCRIPT_KEY.match(part)
                token = pair and SCRIPT_TOKEN.match(pair.group(3))
                if not pair:
                    unseen.add("...")
                    continue
                key = pair.group(1) or read(pair.group(2))
                if token:
                    literals[key] = strings[int(token.group(1))]
                if not token or not isinstance(strings[int(token.group(1))], str):
                    unseen.add(key)
            bodies.append((keys, unseen, literals))
        first, prompt = SCRIPT_FIRST_ARG.match(text, call.end()), None
        if first:
            entry, end = strings[int(first.group(1))], first.end()
            # mask_script leaves each `${...}` of a template as one "(code)" group after its token
            for _ in range(0 if isinstance(entry, str) else entry[2].count("\x00")):
                end = script_group_end(text, end)
            if end >= 0 and SCRIPT_ARG_END.match(text, end):
                prompt = plain(entry)
        elif text[call.end():].lstrip().startswith("{") and bodies:
            _, unseen, literals = bodies[0]
            if "prompt" in literals and "..." not in unseen:
                prompt = plain(literals["prompt"])
        yield prompt, bodies


def below_the_floor(model) -> bool:
    return "haiku" in str(model).lower()


def floor_hit(tool: str, tool_input) -> str:
    """The model a call names below the floor, or "". Listed roles may run Haiku."""
    if tool in SPAWN_TOOLS:
        model = tool_input.get("model")
        if below_the_floor(model) and tool_input.get("subagent_type") not in HAIKU_ROLES:
            return str(model)
    elif tool in (SESSION_TOOL, CREATE_SESSION_TOOL):
        if below_the_floor(tool_input.get("model")):
            return str(tool_input.get("model"))
    elif tool == "Workflow" and isinstance(tool_input.get("script"), str):
        for _, bodies in script_agent_calls(tool_input["script"]):
            for keys, _, _ in bodies:
                if below_the_floor(keys.get("model")) and keys.get("agentType") not in HAIKU_ROLES:
                    return keys["model"]
    return ""


def lane_effort_hit(tool: str, tool_input) -> str:
    """The prompt of a create_session call that tags a lane and is not the effort command exactly, or "".
    A slash command runs only as the whole prompt, so the compare is exact: no strip. A lane tag is any
    tag that, stripped and casefolded, is LANE_TAG; `tags` may be one string. A call with no lane tag
    is not judged. A missing prompt is not the command."""
    tags = tool_input.get("tags")
    if tool != CREATE_SESSION_TOOL:
        return ""
    if isinstance(tags, str):
        tags = [tags]
    if not isinstance(tags, list) or not any(isinstance(t, str) and t.strip().casefold() == LANE_TAG for t in tags):
        return ""
    prompt = tool_input.get("prompt")
    return "" if prompt == "/effort " + LANE_EFFORT else str(prompt or "(no prompt)")


def lane_repo_tag_hit(tool: str, tool_input, cwd: str):
    """(tags, repo) of a lane `create_session` call that carries no repo tag for the calling checkout's GitHub repo, or
    ("", None). The repo is git_reads.github_repo of cwd, the one reading the roadmap build shares: the extras' "github"
    key first, then the origin's path. A lane tag is judged as in lane_effort_hit. With no readable repo, any full
    `cs-repo:<owner>/<name>` tag passes. One read of the repo feeds both the verdict and the deny reason."""
    tags = tool_input.get("tags")
    if tool != CREATE_SESSION_TOOL:
        return "", None
    if isinstance(tags, str):
        tags = [tags]
    if not isinstance(tags, list) or not any(isinstance(t, str) and t.strip().casefold() == LANE_TAG for t in tags):
        return "", None
    repo = git_reads.github_repo(cwd) if isinstance(cwd, str) and cwd and os.path.isdir(cwd) else None
    # A tag is read as the roadmap reads it (repo_tag_names): exact prefix, no strip, owner/name without case.
    for tag in tags:
        if repo and repo_tag_names(tag, repo):
            return "", None
        if not repo and isinstance(tag, str) and tag.startswith(REPO_TAG) and FULL_REPO_TAG.fullmatch(tag[len(REPO_TAG):]):
            return "", None
    return ", ".join(str(t) for t in tags), repo


# A builder's third-round marker is the `Round N of 3` line. The old `Try N of 3` line still counts until
# note try-marker-sunset.
BUILDER_MARKERS = ("round", "try")
# The one marker scanner reads shared_names.BRIEF_MARKERS; each row is compiled once, at import.
from shared_names import BRIEF_MARKERS  # noqa: E402  the one home of the marker rows
_MARKER_ROWS = tuple((kind, re.compile(text), position) for kind, text, position in BRIEF_MARKERS)


def brief_first_line(brief) -> str:
    """A brief's first non-blank line, or "" for a brief that is not text. The one home of the first-line pick."""
    if not isinstance(brief, str):
        return ""
    return next((line for line in brief.split("\n") if line.strip()), "")


def marker_scan(brief) -> list:
    """The [(kind, n)] markers of a brief, read from BRIEF_MARKERS, in the order a reader meets them: each "line-start"
    match in line order, then each "first-line" row's hit in table order. A "line-start" row reads every line of the
    brief; a "first-line" row reads the first non-blank line alone. n is the row's group 1, or None for a row with none
    (the audit marker). A brief that is not text has none. Pure: no I/O, no process, no file. The two positions read
    different spans of the brief (decision agent-model-cap); BRIEF_MARKERS says which row uses which."""
    if not isinstance(brief, str):
        return []
    first = brief_first_line(brief)
    starts, leads = [], []
    for kind, rx, position in _MARKER_ROWS:
        if position == "line-start":
            found = list(rx.finditer(brief))
            starts.extend((hit.start(), kind, hit.group(1) if rx.groups else None) for hit in found)
        else:
            hit = rx.search(first)
            found = [hit] if hit else []
            leads.extend((kind, hit.group(1) if rx.groups else None) for hit in found)
    return [(kind, n) for _, kind, n in sorted(starts)] + leads


def marker_hits(brief) -> set:
    """The {(kind, n)} markers of a brief: the one marker scanner (marker_scan) as a set."""
    return set(marker_scan(brief))


def brief_markers(brief) -> list:
    """The [(kind, n)] round and try markers of a brief in line order, with the first-line one last: marker_scan
    without the audit marker, which has no n. Line order picks which refusal text a reviewer brief gets."""
    return [(kind, n) for kind, n in marker_scan(brief) if n is not None]


def builder_third_round(brief) -> bool:
    """True when a brief holds a builder's third-round marker, in either spelling."""
    return any(kind.lower() in BUILDER_MARKERS and n == "3" for kind, n in brief_markers(brief))


# A Workflow agent() call is read statically; one whose prompt or model the scan cannot read passes.
def step_up_hit(tool: str, tool_input) -> str:
    """The step-up reason for a spawn whose marker and model disagree, or "". Only a line
    that starts with the marker, or the brief's first line, counts. A missing model runs the env default, which is Sonnet for a builder; a reviewer's
    frontmatter model is haiku, so a reviewer on a later-round brief must name sonnet. A later-round reviewer that names Opus
    passes here and is refused by the Opus ceiling (opus_spawn_hit), so the remedy names Sonnet only (decision agent-model-cap)."""
    if tool in SPAWN_TOOLS and isinstance(tool_input.get("prompt"), str):
        return step_up_reason(tool_input["prompt"], tool_input.get("subagent_type"), tool_input.get("model"))
    if tool == "Workflow" and isinstance(tool_input.get("script"), str):
        for prompt, bodies in script_agent_calls(tool_input["script"]):
            keys, unseen = {}, set()
            for k, u, _ in bodies:
                keys.update(k)
                unseen |= u
            if prompt is None or "model" in unseen or "..." in unseen:
                continue
            role = None if "agentType" in unseen else keys.get("agentType")
            reason = step_up_reason(prompt, role, keys.get("model"))
            if reason:
                return reason
    return ""


def step_up_reason(prompt: str, role, model) -> str:
    model = str(model or "").lower()
    for kind, n in brief_markers(prompt):
        kind = kind.lower()
        if role == "reviewer" and kind == "round" and n == "2" and "sonnet" not in model:
            return "Reviewer round 2 runs on Sonnet. Spawn it with model sonnet."
        if role == "reviewer" and kind == "round" and n == "3" and "sonnet" not in model and "opus" not in model:
            return "Reviewer round 3 runs on Sonnet. Spawn it with model sonnet."
    if role == "builder" and builder_third_round(prompt) and "opus" not in model:
        return "Builder round 3 runs on Opus. Spawn it with model opus."
    return ""


# THE ROLE MODEL ROW (rule agent-role-model, decision agent-model-cap). The model per role is read at each spawn from the
# pointer checkout's decision record, so the guard holds no copy of the table. A row names a role in its first cell and a
# model in its second; a first cell that holds anything but role words (a qualifier such as `reviewer, rounds 2 and 3`, a
# skill, a hook) names no role, and the first row for a role wins. Cost per Agent or Task spawn: one read of the record and,
# for a spawn with no model, one read of the agent files. No process starts and no file is written, except the one
# `agent-role-model-unread` log line when a read fails.
ROLE_MODEL_RANK = ("haiku", "sonnet", "opus")
ROLE_TABLE_FILE = "agent-model-cap.md"   # inside the record folder that lint/layout.py names
ROLE_TABLE_MAX = 256 * 1024
ROLE_WORD = re.compile(r"[A-Za-z][A-Za-z-]*$")
ROLE_FIRST_WORD = re.compile(r"\W*([A-Za-z]+)")
ROLE_PARENTHETICAL = re.compile(r"\([^)]*\)")
ROLE_DEFAULT = "general-purpose"
# One point the owner has not ruled yet, one line to flip. A reviewer brief with a `Round N of 3` marker, N in
# ROLE_REVIEWER_FREE_ROUNDS, may run above its row; add "1" there to let a reviewer on its first marker run above its row.
# An Explore may run Sonnet, above its Haiku row, or Opus (opus_spawn_hit), only when its brief's first non-blank line carries
# EXPLORE_AUDIT_MARKER (decision agent-model-cap). Case-sensitive, so lowercase prose does not count. It counts on the first line, with anything ahead of it, as BRIEF_MARKERS says; marker_hits reads it.
from shared_names import EXPLORE_AUDIT_MARKER  # noqa: E402  the one home, shared with the spawn judge (hooks/call_judge.py)
from shared_names import REPO_TAG, repo_tag_names  # noqa: E402  the one home of the repo tag, shared with skills/roadmap/build.py
EXPLORE_ROLE = "Explore"
ROLE_REVIEWER_FREE_ROUNDS = ("2", "3")
ROLE_MODEL_ENV = "CLAUDE_CODE_SUBAGENT_MODEL"
ROLE_MODEL_REASON = (
    "Rule (configuration): this spawn names a model above the one its role runs on. Remedy: drop the model "
    "field, or name the role's model%s. (decision agent-model-cap)"
)
# A reviewer has a second way past its row, so only its refusal names it. Rounds come from the constant at call time.
ROLE_REVIEWER_ROUND_REMEDY = ", or, when this brief is for review round %s, open its first line with a `Round N of 3` marker (%s)"
# An Explore has a second way past its row, so only its refusal names it, and only for a ranked model: the marker
# does not lift a model the table does not rank.
ROLE_EXPLORE_AUDIT_REMEDY = ", or, when this brief is an audit, open its first line with the `%s` marker"
ROLE_NO_MODEL_MATCH = "no model, role "   # the matched text of the no-model refusal, which never_lifted reads
ROLE_NO_MODEL_REASON = (
    "Rule (configuration): this spawn names no model, its role has no model of its own, and no default "
    "model is set, so it would run on its parent's model. Remedy: name the role's model%s. "
    "(decision agent-model-cap)"
)


def _layout_module():
    """lint/layout.py, imported from the lint folder beside this file's folder. The one home of the import."""
    lint = os.path.join(_HERE, "..", "lint")
    if lint not in sys.path:
        sys.path.append(lint)
    import layout
    return layout


def record_branch_of(root):
    """The record branch of the checkout at `root`: lint/layout.py record_branch, else "roadmap" when the
    layout cannot be read."""
    try:
        layout = _layout_module()
        return layout.record_branch(root)
    except Exception:
        return DEFAULT_RECORD_BRANCH


def role_model_table(pointer_root):
    """{role: first word of its Model cell} read from the pointer checkout's decision record, or None when the
    record is missing, not text, or holds no row. The one reader of the table."""
    if not pointer_root:
        return None
    layout = _layout_module()
    try:
        folder = layout.layout()["kinds"]["decisions"]["path"].strip("/")
        with open(os.path.join(pointer_root, *folder.split("/"), ROLE_TABLE_FILE), encoding="utf-8") as handle:
            text = handle.read(ROLE_TABLE_MAX)
    except (OSError, ValueError, layout.LayoutError):
        return None
    table = {}
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        names = [part.strip() for part in ROLE_PARENTHETICAL.sub("", cells[0]).replace("`", "").split(",")]
        word = ROLE_FIRST_WORD.match(cells[1].replace("`", ""))
        if not all(ROLE_WORD.match(name) for name in names) or not word or word.group(1).lower() not in ROLE_MODEL_RANK:
            continue
        for name in names:
            table.setdefault(name, word.group(1).lower())
    return table or None


def role_model_rank(model):
    """The index in ROLE_MODEL_RANK of the family a model name holds (`claude-opus-5-5`, `Haiku`), the highest family
    when a name holds more than one, or None when it holds none. The one normaliser of a model name to its family."""
    return next((rank for rank, word in reversed(list(enumerate(ROLE_MODEL_RANK))) if word in str(model).lower()), None)


def frontmatter_keys(lines):
    """The top-level keys of frontmatter lines (the text between the two `---` lines): {key: raw value}, the first of
    a key wins. An indented line is a continuation of the key above it (a block scalar), never a key. Values stay raw:
    the caller strips comments and quotes. The one parser of agent frontmatter keys."""
    keys = {}
    for line in lines:
        if line[:1].isspace():
            continue
        key, _, value = line.partition(":")
        keys.setdefault(key.strip(), value.strip())
    return keys


def role_agent_keys(pointer_root):
    """Yield the frontmatter keys of each agents/*.md file in the pointer checkout, one dict per file with
    frontmatter, in file order, one file read at a time. Raises OSError when the folder or a file cannot be read, so
    a caller that stops early never reads the files after its match. The reader of agent frontmatter for the role
    rules. In lint/check_agent_models.py, main() reads the same files and passes their frontmatter to frontmatter_keys
    for its pin check."""
    folder = os.path.join(pointer_root, "agents")
    for name in sorted(name for name in os.listdir(folder) if name.endswith(".md")):
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as handle:
                lines = handle.read(ROLE_TABLE_MAX).splitlines()
        except ValueError as exc:
            raise OSError("agent file is not text: %s" % name) from exc
        if not lines or lines[0].strip() != "---":
            continue
        end = next((n for n, line in enumerate(lines[1:], 1) if line.strip() == "---"), len(lines))
        yield frontmatter_keys(lines[1:end])


def role_has_model_pin(pointer_root, role):
    """True when an agent file in the pointer checkout's agents folder names this role and pins a `model:` in its
    frontmatter, False when none does, None when the folder cannot be read."""
    try:
        for keys in role_agent_keys(pointer_root):
            if keys.get("name", "").lower() == role.lower() and keys.get("model"):
                return True
    except OSError:
        return None
    return False


# General-purpose and claude have no agents/ file, so they are listed here to count as real roles. Plan and Explore
# have agents/ files and are listed too, so the check does not depend on those files.
ROLE_BUILTINS = (ROLE_DEFAULT, "claude", "Plan", EXPLORE_ROLE)


def role_list_drift(pointer_root):
    """One line per disagreement between the role table and the three role lists, [] when all agree or when the
    table or the agents folder cannot be read (the lint check reports that as unknown). Lint-time only. Cost per
    lint run: each agent file is read 3 times and the table twice. main() in lint/check_agent_models.py reads each
    file once (frontmatter() parses that text), role_list_problems reads the table and the files once to test
    readability, and this function reads both again. floor_hit, opus_spawn_hit and hooks/override.py keep their constants.
    A real role has an agents/ file `name` or is built in, which drops the table's non-role keys."""
    table = role_model_table(pointer_root)
    if table is None:
        return []
    try:
        agents = list(role_agent_keys(pointer_root))
    except OSError:
        return []
    import override
    real = {keys["name"] for keys in agents if keys.get("name")} | set(ROLE_BUILTINS)
    on = {word: {role for role, model in table.items() if model == word and role in real} for word in ROLE_MODEL_RANK}
    standing_want = on["opus"]
    # No scoped `opus explore` override form: an Explore on Opus without the marker is lifted by `opus 2h` or `override` (item 137 pick a, option b not picked).
    override_want = {role for role in table if role in real} - on["opus"] - {EXPLORE_ROLE}
    lists = (("HAIKU_ROLES", "hooks/guard.py", set(HAIKU_ROLES), on["haiku"], "a haiku row"),
             ("OPUS_STANDING_ROLES", "hooks/guard.py", set(OPUS_STANDING_ROLES), standing_want, "an opus row"),
             ("OPUS_ROLES", "hooks/override.py", set(override.OPUS_ROLES), override_want, "a row below opus"))
    lines = []
    for name, home, have, want, row in lists:
        for role in sorted(have - want):
            lines.append("%s lists %s, but the role table does not put it on %s (%s)" % (name, role, row, home))
        for role in sorted(want - have):
            lines.append("%s lacks %s, which the role table puts on %s (%s)" % (name, role, row, home))
    return lines


def role_key(subagent_type) -> str:
    """The role a spawn names, without case and without surrounding space; an empty role is the default role. The one
    normaliser in this file: role_name and opus_spawn_hit's Explore grant both read the role through it.
    hooks/call_judge.py explore_off_model folds the Explore role on its own."""
    return (str(subagent_type or "").strip() or ROLE_DEFAULT).lower()


def role_name(table, subagent_type) -> str:
    """The role a spawn names, as the table spells it: matched without case and without surrounding space.
    A role the table lacks keeps its own spelling, stripped. An empty role is the default role."""
    role = str(subagent_type or "").strip() or ROLE_DEFAULT
    return next((name for name in table if role_key(name) == role_key(role)), role)


# A Workflow spawn whose brief the scan could not read carries BRIEF_UNREAD; its refusal adds BRIEF_LITERAL_REMEDY.
# The remedy stays lowercase mid-sentence, so both refusals carry the same words.
BRIEF_UNREAD = "brief_unread"
BRIEF_LITERAL_REMEDY = "write the brief as a literal string so the marker is readable"


def spawn_inputs(tool: str, tool_input):
    """Yield each spawn a call makes, shaped as an Agent input (`subagent_type`, `model`, `prompt`). An Agent or Task
    call is one spawn. A Workflow script yields one per agent() call that names a model, with agentType as the role
    and the model read from the script, so the role and Opus checks judge it as they judge an Agent spawn
    (decision agent-model-cap). A brief the scan cannot read (a variable, or a prompt key beside a spread) carries no
    marker and grants nothing, so the spawn is judged with an empty brief and BRIEF_UNREAD set, and its refusal names
    BRIEF_LITERAL_REMEDY, so the author can make the marker readable. A
    call whose model or agentType the scan cannot read, or that names no model, is skipped: a static read never
    guesses a role or a model. A shorthand or a spread with no literal agentType may set the role, so it is unread;
    a literal agentType beside a spread is read. step_up_hit still skips an unread brief, as a marker it cannot read
    has no round to check. Other tools yield nothing."""
    if tool in SPAWN_TOOLS:
        yield tool_input
    elif tool == "Workflow" and isinstance(tool_input.get("script"), str):
        for prompt, bodies in script_agent_calls(tool_input["script"]):
            keys, unseen = {}, set()
            for k, u, _ in bodies:
                keys.update(k)
                unseen |= u
            if unseen & {"model", "agentType"} or not keys.get("model"):
                continue
            if "..." in unseen and "agentType" not in keys:
                continue
            yield {"subagent_type": keys.get("agentType"), "model": keys["model"], "prompt": prompt or "",
                   BRIEF_UNREAD: prompt is None}


def role_model_check(tool: str, tool_input):
    """(reason, matched, unread) for the spawns of an Agent, Task or Workflow call against their roles' rows: the
    first refusal, else the first unread. Cost: one table read per spawn."""
    unread = ("", "", False)
    for spawn in spawn_inputs(tool, tool_input):
        verdict = role_model_one(spawn)
        if verdict[0]:
            return verdict
        if verdict[2] and not unread[2]:
            unread = verdict
    return unread


def role_model_one(tool_input):
    """(reason, matched, unread) for one spawn against its role's row. `reason` is the deny, or "".
    `unread` is true when the table or the agent files could not be read: the spawn then passes. With no pointer checkout the rule stands down, silent. A spawn on Opus is left to
    opus_spawn_hit. An Explore on an audit brief
    (EXPLORE_AUDIT_MARKER) and a reviewer on a later-round brief run above the row. Pure, so never_lifted may call it too.
    An above-row refusal is liftable by the general override (decision agent-model-cap); the
    no-model refusal (matched ROLE_NO_MODEL_MATCH...) is not, and never_lifted reads only that one."""
    pointer = pointer_checkout()
    if not pointer:
        return "", "", False  # no pointer checkout: nothing to read, as the pointer rules stand down
    table = role_model_table(pointer)
    if table is None:
        return "", pointer, True
    role = role_name(table, tool_input.get("subagent_type"))
    model = str(tool_input.get("model") or "").strip()
    if model:
        top = len(ROLE_MODEL_RANK) - 1
        named = role_model_rank(model)
        row = table.get(role)
        if named is None:
            # A model the table does not rank is above every row below the top rank. Its own rank is unruled, so none is guessed.
            named = top if row == ROLE_MODEL_RANK[top] else top + 1
        if named == top or row is None:
            return "", "", False
        if role == EXPLORE_ROLE and named < top and ("audit", None) in marker_hits(tool_input.get("prompt")):
            return "", "", False
        if role == "reviewer" and named < top and any(kind.lower() == "round" and n in ROLE_REVIEWER_FREE_ROUNDS
                                                      for kind, n in brief_markers(tool_input.get("prompt"))):
            return "", "", False
        if named > ROLE_MODEL_RANK.index(row):
            extra = ""
            if role == EXPLORE_ROLE and named < top:
                extra = ROLE_EXPLORE_AUDIT_REMEDY % EXPLORE_AUDIT_MARKER
            if role == "reviewer":
                extra = ROLE_REVIEWER_ROUND_REMEDY % (" or ".join(ROLE_REVIEWER_FREE_ROUNDS),
                                                    ", ".join("`Round %s of 3`" % n for n in ROLE_REVIEWER_FREE_ROUNDS))
            if tool_input.get(BRIEF_UNREAD):
                extra += ", or " + BRIEF_LITERAL_REMEDY
            return ROLE_MODEL_REASON % extra, model, False
        return "", "", False
    if os.environ.get(ROLE_MODEL_ENV, "").strip():
        return "", "", False
    pinned = role_has_model_pin(pointer, role)
    if pinned is None:
        return "", pointer, True
    if pinned:
        return "", "", False
    row = table.get(role, "sonnet")
    # A remedy never names Haiku: a role on a Haiku row has an agent file that pins it, so it rarely gets here.
    return ROLE_NO_MODEL_REASON % ("" if row == ROLE_MODEL_RANK[0] else " (%s)" % row), ROLE_NO_MODEL_MATCH + role, False


# THE MACHINE-LOAD BRAKE (decision machine-load-brake). A start call (a call that starts a lane or an agent) reads the machine's load once. Memory in
# use is a share of this machine's memory; disk free on the home drive is in GB (2**30 bytes) against the drive's
# size. Busy (memory over 85%, or disk free under the smaller of 10% of the disk and 15 GB) refuses a Workflow and an
# explicit background Agent or Task call. An Agent or Task call passes at busy only when it leaves
# run_in_background out or sets it false. (In the desktop harness a left-out call still runs in the background
# and the field is not offered, so busy does not slow an Agent call there.) Full (memory over 95%, disk free
# under the smaller of 5% of the disk and 5 GB) refuses every start call. A reading that cannot be read counts as normal. Only an
# agent's shell or file write also reads load (RUNNING_AGENT_TOOLS, below). A cloud session (CLAUDE_CODE_REMOTE
# "true") skips the brake and reads nothing, because the brake guards the owner's own machine.
START_TOOLS = SPAWN_TOOLS + ("Workflow", SESSION_TOOL)
LOAD_BUSY_MEMORY = 85.0
LOAD_FULL_MEMORY = 95.0
LOAD_BUSY_DISK_SHARE, LOAD_BUSY_DISK_GB = 10.0, 15.0   # busy: free under the smaller of the two
LOAD_FULL_DISK_SHARE, LOAD_FULL_DISK_GB = 5.0, 5.0
GIB = 2 ** 30
LOAD_CITE = "(decision machine-load-brake, a busy or full machine starts no new lane or agent)"
LOAD_LANE_CITE = "(decision machine-load-brake, a full machine stops a running agent at its next shell or file write)"
LOAD_BUSY_REASON = "the machine is busy (%s). %s " + LOAD_CITE
LOAD_BUSY_AGENT_FORM = ", or make this an Agent call that leaves run_in_background out or sets it false"
LOAD_BUSY_NO_FOREGROUND = "A Workflow has no foreground form. "
LOAD_FULL_REASON = "the machine is full (%s). No new lane or agent starts until the load drops. Wait, then retry. " + LOAD_CITE


def _read_memory():
    """Percent of physical memory in use, from the OS's own counter, or None on another platform."""
    import ctypes
    if sys.platform == "win32":
        from ctypes import wintypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
        return 100.0 * (status.ullTotalPhys - status.ullAvailPhys) / status.ullTotalPhys
    if sys.platform == "darwin":
        # kern.memorystatus_level is the free share that `memory_pressure` prints.
        level, size = ctypes.c_int(0), ctypes.c_size_t(ctypes.sizeof(ctypes.c_int))
        if ctypes.CDLL(None).sysctlbyname(b"kern.memorystatus_level", ctypes.byref(level),
                                          ctypes.byref(size), None, 0) != 0:
            return None
        return 100.0 - level.value
    return None


def _read_disk():
    """(GB free, GB total) of the drive that holds the home folder, 2**30 bytes to the GB."""
    import shutil
    usage = shutil.disk_usage(os.path.expanduser("~"))
    return usage.free / GIB, usage.total / GIB


def read_load() -> dict:
    """The readings: memory_pct (percent in use, clamped to 0-100) and disk_free_gb
    and disk_total_gb (GB, not clamped). No child process and no file. A reading that fails or cannot be read
    is None, and one failure hides no other."""
    out = {}
    for key, read in (("memory_pct", _read_memory),):
        try:
            value = read()
            out[key] = None if value is None else min(100.0, max(0.0, float(value)))
        except Exception:
            out[key] = None
    try:
        out["disk_free_gb"], out["disk_total_gb"] = _read_disk()
    except Exception:
        out["disk_free_gb"] = out["disk_total_gb"] = None
    return out


def _load_value(reading: dict, key: str):
    """A reading as a float, or None when it is unread or not a number."""
    v = reading.get(key)
    return None if isinstance(v, bool) or not isinstance(v, (int, float)) else float(v)


def load_hit(tool: str, tool_input) -> tuple:
    """(rule reason, matched) when the machine's load refuses this start call, else ("", ""). The one
    read of the call: a failed read or an unread value counts as normal. A cloud session is never braked."""
    if tool not in START_TOOLS or is_cloud():
        return "", ""
    try:
        reading = read_load()
    except Exception:
        return "", ""
    if not isinstance(reading, dict):
        return "", ""
    memory = _load_value(reading, "memory_pct")
    disk, disk_total = _load_value(reading, "disk_free_gb"), _load_value(reading, "disk_total_gb")
    disk_text = None if disk is None or disk_total is None else "disk %.1f GB free of %.0f GB" % (disk, disk_total)

    def disk_under(share, gb):
        return disk_text is not None and disk < min(disk_total * share / 100.0, gb)

    full = load_full(reading)
    if full:
        return LOAD_FULL_REASON % ", ".join(full), ", ".join(full)
    # An Agent or Task call that leaves run_in_background out or sets it false passes busy. Any other present value
    # is a background request. A session start has no such field, and no ruling covers it at busy.
    if tool == SESSION_TOOL or (tool in SPAWN_TOOLS and (
            "run_in_background" not in tool_input or tool_input["run_in_background"] is False)):
        return "", ""
    busy = [t for t in (memory is not None and memory > LOAD_BUSY_MEMORY and "memory %.1f%% in use" % memory,
                        disk_under(LOAD_BUSY_DISK_SHARE, LOAD_BUSY_DISK_GB) and disk_text) if t]
    if busy:
        # The remedy matches the reading: load drops by waiting, disk space comes back only when it is freed.
        waits = [t for t in busy if not t.startswith("disk")]
        remedy = " and ".join((["wait until the load drops"] if waits else [])
                              + (["free disk space"] if len(waits) < len(busy) else []))
        text = (LOAD_BUSY_NO_FOREGROUND + remedy.capitalize() if tool == "Workflow"
                else remedy.capitalize() + LOAD_BUSY_AGENT_FORM)
        return LOAD_BUSY_REASON % (", ".join(busy), text + "."), ", ".join(busy)
    return "", ""


# A RUNNING AGENT (decision machine-load-brake, "Running agents"). An agent's own call that can fill a disk (a shell or
# a file write) reads the load once, inside this hook that already runs for the call. Full refuses it, so an agent
# stops even while its orchestrator waits on the owner. Busy lets it run. The orchestrator's own calls read nothing,
# so the session that frees the disk is never braked by the full disk. A lane session (a session whose own record
# carries the lane tag, lane_session_hit) is braked the same way on its own calls, since it is a lane too.
RUNNING_AGENT_TOOLS = ("Bash", "PowerShell") + WRITE_TOOLS
LOAD_LANE_FULL_REASON = ("the machine is full (%s). Stop this agent now: end your turn and report the reading to "
                         "your orchestrator, which frees space or waits for the load to drop. " + LOAD_LANE_CITE)


def running_agent_hit(payload, tool: str) -> tuple:
    """(rule reason, matched) when an agent's disk-filling call meets a full machine, else ("", ""). One read
    per such call; none for the orchestrator or a lane session (lane_session_hit judges that), and none for a
    start call, which load_hit reads."""
    agent_id = payload.get("agent_id") if isinstance(payload, dict) else None
    if is_cloud() or tool not in RUNNING_AGENT_TOOLS or not isinstance(agent_id, str) or not AGENT_ID.match(agent_id):
        return "", ""
    try:
        reading = read_load()
    except Exception:
        return "", ""
    full = load_full(reading)
    return (LOAD_LANE_FULL_REASON % ", ".join(full), ", ".join(full)) if full else ("", "")


LOAD_SESSION_FULL_REASON = ("the machine is full (%s). You are a lane session: end your turn now and send this "
                            "reading to your parent with send_message to @parent, which frees space or waits for the "
                            "load to drop. " + LOAD_LANE_CITE)


def lane_session_hit(payload, tool: str) -> tuple:
    """(rule reason, matched) when a lane session's own disk-filling call meets a full machine, else ("", "").
    A call with an agent_id is an agent's (running_agent_hit). The load is read once; the transcript is read only
    at full, and an unread record or any error counts as no lane."""
    if not isinstance(payload, dict) or is_cloud() or tool not in RUNNING_AGENT_TOOLS or payload.get("agent_id"):
        return "", ""
    try:  # fails closed: an unimportable override or an unread id is no lane, so the later checks still run
        import override
        own_id = override.remote_session_id()
        if own_id is None:
            return "", ""
        full = load_full(read_load())
        transcript = payload.get("transcript_path")
        if not full or not isinstance(transcript, str) or not transcript:
            return "", ""
        import own_session
        tags, tagged_after, _parent = own_session.own_session_read(transcript, own_id)
        names = [t.strip().casefold() for t in tags if isinstance(t, str)] if isinstance(tags, list) else []
        if tagged_after or LANE_TAG not in names or any(n.startswith("cs-build:") and n != LANE_TAG for n in names):
            return "", ""
    except Exception:
        return "", ""
    return LOAD_SESSION_FULL_REASON % ", ".join(full), ", ".join(full)


def load_full(reading) -> list:
    """The readings over the full line, as text, or []. An unread or malformed reading counts as normal."""
    if not isinstance(reading, dict):
        return []
    memory = _load_value(reading, "memory_pct")
    disk, disk_total = _load_value(reading, "disk_free_gb"), _load_value(reading, "disk_total_gb")
    disk_full = (disk is not None and disk_total is not None
                 and disk < min(disk_total * LOAD_FULL_DISK_SHARE / 100.0, LOAD_FULL_DISK_GB))
    return [t for t in (memory is not None and memory > LOAD_FULL_MEMORY and "memory %.1f%% in use" % memory,
                        disk_full and "disk %.1f GB free of %.0f GB" % (disk, disk_total)) if t]


OPUS_SPAWN_REASON = (
    "Rule (configuration): this spawn sets model Opus, above its role's model. Opus runs "
    "only on the owner's typed override or grant for this spawn, except Plan, the designer, the design "
    "reviewer, a builder's Round 3 of 3 and an Explore whose brief's first line carries the `%s` marker "
    "(decision agent-model-cap). Remedy: drop the model field, or name the role's model. A reviewer's Round 2 or "
    "Round 3 brief names sonnet."
) % EXPLORE_AUDIT_MARKER
OPUS_BUILDER_REASON = (
    OPUS_SPAWN_REASON + " No `Round 3 of 3` marker was found in the brief's first line or at the start of "
    "any line. The marker applies only to a builder's third try, after review round 2 failed."
)
OPUS_STANDING_ROLES = ("Plan", "designer", "design-reviewer")


def opus_spawn_hit(tool: str, tool_input) -> tuple:
    """(model, role, brief_unread) of the first spawn in an Agent, Task or Workflow call that sets Opus with no standing grant,
    else ("", "", False). `role` is the role the spawn names, "" for none. `brief_unread` is the spawn's BRIEF_UNREAD.
    A standing grant
    is the role Plan, designer or design-reviewer, a builder whose brief holds the third-round marker (the same marker
    step_up_hit reads), or an Explore whose brief's first non-blank line carries EXPLORE_AUDIT_MARKER (decision agent-model-cap).
    Any other spawn above its role's model is refused (decision agent-model-cap), a reviewer on Opus too. The refusal is liftable by an override, so never_lifted does not read it."""
    for spawn in spawn_inputs(tool, tool_input):
        if opus_without_grant(spawn):
            return str(spawn.get("model")), str(spawn.get("subagent_type") or ""), bool(spawn.get(BRIEF_UNREAD))
    return "", "", False


def opus_without_grant(tool_input) -> bool:
    if "opus" not in str(tool_input.get("model") or "").lower():
        return False
    role, brief = tool_input.get("subagent_type"), tool_input.get("prompt")
    if role in OPUS_STANDING_ROLES:
        return False
    if role == "builder" and builder_third_round(brief):
        return False
    # Only the Explore grant reads the role through role_key, as role_model_check does; the other standing roles and the
    # builder stay exact-case, as they were.
    if role_key(role) == role_key(EXPLORE_ROLE) and ("audit", None) in marker_hits(brief):
        return False
    return True


# ASK ALONE (ruling ask-commands-run-alone). A command that would ASK is held, not printed, while the other rules run, so a
# deny anywhere still wins. At the end, an ask command with any other command in the shell call (`&&`, `||`,
# `;`, `|`, a newline) is refused, and the same command alone asks as before, as does one with a named
# harmless lead or tail (harmless_commands, below). The deny
# names the command by its kind, never its text. Only the first ask command is held: it is the one that
# printed before.
PENDING_ASK = []   # [(rule, reason, matched, command)], at most one
ASK_ALONE_REASON = ("this shell call chains a command that needs the owner's answer (%s) with "
                    "other commands. Run that command alone, in its own call, or drop it. "
                    "(decision ask-commands-run-alone, a command that asks the owner runs alone)")


def ask_command(rule: str, reason: str, matched: str, command: str) -> None:
    if not PENDING_ASK:
        PENDING_ASK.append((rule, reason, matched, rule + ", " + command))


def background_commands(segment: str) -> int:
    """The commands in one segment once an unquoted single `&` also separates them. `&&` is already
    split, and a `&` that joins a redirect (`&>`, `>&`, `<&`) is no separator. A `&` with nothing
    before it (PowerShell's call operator, the tail of `|&`) or nothing after it (a trailing job)
    adds no command. Local to ask-alone: split_segments stays as the other rules read it."""
    parts, quote, current, escaped = [], "", [], False
    for index, char in enumerate(segment):
        if escaped:
            escaped = False   # `\"` inside double quotes is text, never the closing mark
        elif quote:
            escaped = quote == '"' and char == "\\" and not POWERSHELL_CALL[0]
            quote = "" if char == quote else quote
        elif char in "'\"":
            quote = char
        elif char == "&" and segment[index - 1:index] not in (">", "<") \
                and segment[index + 1:index + 2] != ">":
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return max(1, sum(1 for part in parts if part.strip()))


def count_commands(text: str) -> int:
    """The commands in a shell call: its segments, a single `&` as a separator, and the commands inside a
    script handed to another interpreter (nested_script: `sh -c`, `cmd /c`, `pwsh -c`, `iex`,
    `env -S`, `eval`), which stand in place of the call that holds them."""
    commands = 0
    for segment in split_segments(text):
        if not segment.strip():
            continue
        commands += background_commands(segment)
        tokens = segment_tokens(segment)
        script = nested_script(tokens) if tokens else ""
        if script:
            commands += count_commands(script) - 1
    return commands


# THE HARMLESS ADDITIONS (decision ask-commands-run-alone). Two forms are no
# extra command beside an ask command. Before it: `cd X &&`, `export NAME=value &&`, `Set-Location X;`.
# After it: `| tail -N`, `| head -N`, `| Out-Null`, `&& echo <text>`, `; Write-Host <text>`. Each is
# read by its separator and its tokens, so `; echo`, `| cat`, `; Write-Output`, `| tee`, `| sh`, `||`
# and the aliases sl, chdir and Push-Location stay counted. A redirect, a substitution, a `&` or an
# escaped quote (`\"`, `\'`) in the segment makes it a command. Only a run of them at the head and a run at the tail count.
UNSAFE_TEXT = re.compile(r"""[<>`&]|\\["']|\$\(|\$\{""")  # an escaped quote may hide a command; a backslash in a path is fine
ASSIGN_WORD = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
COUNT_ARG = re.compile(r"^-(?:n)?\d+$|^-n\d+$")


def harmless_lead(tokens: list, end: str) -> bool:
    word, args = tokens[0].lower(), tokens[1:]
    if word == "cd" and end == "&&":
        # `cd -` is the previous folder, which no path in the command names
        return args != ["-"] and (len(args) == 1 or (len(args) == 2 and args[0] in ("-P", "-L") and args[1] != "-"))
    if word == "export" and end == "&&":
        return bool(args) and all(ASSIGN_WORD.match(arg) for arg in args)
    if word == "set-location" and end == ";":
        return len(args) == 1 or (len(args) == 2 and args[0].lower() in ("-path", "-literalpath"))
    return False


def harmless_tail(tokens: list, before: str) -> bool:
    word, args = tokens[0].lower(), tokens[1:]
    if word in ("tail", "head") and before == "|":
        return (len(args) == 1 and bool(COUNT_ARG.match(args[0]))) or (
            len(args) == 2 and args[0] == "-n" and args[1].isdigit())
    if word == "out-null" and before == "|":
        return not args
    return (word, before) in (("echo", "&&"), ("write-host", ";"))


def harmless_commands(text: str) -> int:
    """How many segments of `text` are a harmless lead or tail around the ask command. A segment
    that does not read as one form counts as a command, and the first and last are never both read
    as the ask command, so at least one segment stays."""
    ends = []
    segments = split_segments(text, ends)
    count = len(segments)

    def plain(index: int):
        segment = segments[index]
        if UNSAFE_TEXT.search(segment):
            return None
        tokens = segment_tokens(segment)
        return tokens or None

    head = 0
    while head < count - 1 and (tokens := plain(head)) and harmless_lead(tokens, ends[head]):
        head += 1
    tail = count
    while tail > head + 1 and (tokens := plain(tail - 1)) and harmless_tail(tokens, ends[tail - 2]):
        tail -= 1
    return head + count - tail


def settle_ask(tool: str, raw: str) -> None:
    if not PENDING_ASK:
        return
    rule, reason, matched, command = PENDING_ASK[0]
    # An interpreter heredoc (python, node, perl, ruby) is one command: its body is not counted line by line.
    # Strip the RAW command once. A second strip of stripped text reads a stray delimiter line as a new body.
    text = strip_heredoc_bodies(raw, shells_only=True)
    if count_commands(text) > 1:
        if count_commands(text) - harmless_commands(text) > 1:
            refuse(tool, "deny", "ask-alone", ASK_ALONE_REASON % command, matched)
    refuse(tool, "ask", rule, reason, matched)


def judge_shell(tool: str, raw: str, cwd: str, session_id: str = "", role: str = "",
                transcript: str = "", agent: bool = False,
                background: bool = False, description: str = "") -> None:
    POWERSHELL_CALL[0] = tool == "PowerShell"
    PENDING_ASK.clear()
    stripped = strip_heredoc_bodies(raw)
    cmd = norm(stripped)

    # 0b. A builder, test-author or record-writer's `git commit` or `git push` is judged on the diff it would send.
    if role:
        for segment in split_segments(stripped):
            for subcommand, _ in git_calls(segment):
                if subcommand in ("commit", "push"):
                    diff_refusal(tool, role, command_root(stripped, cwd))

    # 0c. A command that sets a git location variable (q_max incident, 2026-10-14). Placed before
    # rule 1 on purpose: the deny wins where the shared-tree guard would only ask (arbiter ruling).
    matched = git_env_command_hit(raw, stripped)
    if matched:
        refuse(tool, "deny", "git-env-set", GIT_ENV_REASON, matched)

    # 1. Shared trees.
    whole_root = []   # command_root reads the whole command: once per command, never per segment
    for segment in split_segments(stripped):
        if not segment.strip():
            continue
        words = segment_tokens(segment)
        own_c = _segment_git_c_target(words) if words else None
        if own_c is not None:
            # a `--work-tree` beside the `-C` moves the files the call discards to that tree
            root = command_root(segment, cwd) if GIT_WORK_TREE_RE.search(segment) else _absolute(own_c, cwd)
        else:
            whole_root = whole_root or [command_root(stripped, cwd)]
            root = whole_root[0]
        match = shared_tree_match(segment, root)
        if match is None:
            continue
        matched, subcommand, args = match
        resolved = checkout_conflict_resolve(segment, root)
        if resolved:
            continue
        # This session's own scratchpad: private by path, so nothing shared can be lost.
        if under_session_scratchpad(root, session_id):
            continue
        # The subject read. An empty subject is a silent pass. An unreadable subject is allowed
        # and logged under its OWN rule, so a reader can tell "I could not confirm this" from
        # "this destroys something", and the Stop hook names it at the end of the turn.
        state = subject_state(subcommand, args, root)
        if subcommand in ("checkout", "restore") and segment_tokens(REDIRECTION.sub(" ", segment)) is None:
            state = False  # an unparsable segment: the paths read above are a guess, keep the ask
        if state is None:
            # An unforced remove is refused by the VCS itself when the tree is dirty or locked,
            # so a note protects nothing (owner ruling, agent-worktree-discard-is-noted).
            if subcommand != "worktree-remove" or worktree_remove_forced(args):
                record(tool, "noted", "subject-unread", matched)
            continue
        if state is True:
            continue
        # A branch's ref and a worktree's own tree are never the running checkout's own lane, so
        # neither earns the worktree-scoped "ask" below: each is judged on its own terms, before
        # that generic split runs.
        if subcommand == "branch-delete":
            refuse(tool, "deny", "shared-tree", BRANCH_DELETE_DENY_REASON, matched)
        if subcommand == "worktree-remove":
            refuse(tool, "deny", "shared-tree", WORKTREE_REMOVE_DENY_REASON, matched)
        if subcommand == "worktree-prune":
            ask_command("shared-tree", WORKTREE_PRUNE_ASK_REASON, matched, "worktree prune")
            continue
        if subcommand == "stash" and stash_takes_the_stack(args):
            refuse(tool, "deny", "shared-tree", STACK_DENY_REASON, matched)
        # A stash PUT reaches here only when it would discard (state is not True above), and its
        # subject is `refs/stash`, the one ref every worktree of this clone already shares. The
        # worktree "ask" below is earned only for a subject that lives in THIS tree alone, so a
        # push refuses here instead of falling into that ask.
        if subcommand == "stash":
            refuse(tool, "deny", "shared-tree", PUSH_DENY_REASON, matched)
        worktree = is_worktree(root)
        if worktree is True:
            # agent-worktree-discard-is-noted: this lane is the harness's own
            # `.claude/worktrees/<name>` shape, so the loss is the agent's own commits, already
            # on its own branch and in its own reflog. Allow it, logged, not asked.
            if agent_owned_worktree(root) is True:
                record(tool, "noted", "shared-tree", matched)
                continue
            # agent-worktree-discard-is-noted ("Named files in a linked worktree"): named files
            # only write this lane's own change to those files, so no ask.
            if names_only_files(subcommand, args, root, segment) and one_place(stripped):
                continue
            ask_command("shared-tree", TREE_ASK_REASON, matched, "worktree discard")
            continue
        refuse(tool, "deny", "shared-tree", TREE_DENY_REASON, matched)

    # 1b. The pointer checkout's HEAD. Placed AFTER rule 1 on purpose: a `git checkout` that
    # names a path is a path operation, rule 1 already judges it, and this rule never sees it, so
    # the shared-tree clause keeps governing those calls unchanged.
    head_where = head_root(stripped, cwd)
    for segment in split_segments(stripped):
        if not segment.strip():
            continue
        matched = pointer_head_hit(segment, head_where)
        if matched:
            refuse(tool, "deny", "pointer-head", POINTER_HEAD_REASON, matched)

    # 1c. A git write whose own trace is silenced, by a redirect of either stream to a null
    # device, or, on the measured subcommands, by git's own quiet flag alone. Placed after the
    # pointer-head rule and before every rule below, so a silenced write is caught on its own
    # defect before anything else judges the same segment.
    ends = []
    segments = split_segments(stripped, ends)
    live = [number for number, segment in enumerate(segments) if segment.strip()]
    for number, segment in enumerate(segments):
        if not segment.strip():
            continue
        last = number
        while last < len(segments) - 1 and ends[last] == "|":
            last += 1
        matched, mechanism, kind = silent_write_hit(segment, segments[last] if last > number else "")
        if matched and not in_throwaway(segments, number, cwd, ends):
            reason = (SILENT_WRITE_REDIRECT_REASON if mechanism == "redirect"
                      else SILENT_WRITE_QUIET_REASON)
            refuse(tool, "deny", "silent-write",
                   reason.format(command=live.index(number) + 1, total=len(live), kind=kind,
                                 program=kind if " " in kind else "git " + kind), matched)

    # 1c2. A worktree made by hand, outside the tool's own folder.
    for number, segment in enumerate(segments):
        if segment.strip():
            matched = hand_made_worktree_hit(segments, number, cwd, ends)
            if matched:
                refuse(tool, "deny", "hand-made-worktree", WORKTREE_HAND_MADE_REASON, matched)

    # 1e. The impeccable skill's build and settings-writer commands (design-skills record).
    matched = impeccable_command_hit(raw)
    if matched:
        refuse(tool, "deny", "impeccable-review-only", IMPECCABLE_REASON, matched)

    # 1d. A commit message or PR body that cites a record by its path.
    cite_where = command_root(stripped, cwd)
    # each segment takes its own bodies: heredoc_offsets counts the headers ahead of it (1c's split)
    for segment, before in zip(segments, heredoc_offsets(segments, ends, stripped == raw)):
        if not segment.strip():
            continue
        matched = cited_record_path(segment, raw, cite_where, before)
        if matched.startswith(UNREAD_MARK):
            refuse(tool, "deny", "cite-by-id", UNREAD_REASON, matched[len(UNREAD_MARK):])
        if matched:
            refuse(tool, "deny", "cite-by-id", CITE_REASON, matched)
        matched = lane_number_named(segment, raw, cite_where, before)
        if matched.startswith(UNREAD_MARK):   # a gh pr merge file: cite-by-id never reads merge
            refuse(tool, "deny", "cite-by-id", UNREAD_REASON, matched[len(UNREAD_MARK):])
        if matched:
            refuse(tool, "deny", "lane-by-slug", LANE_REASON, matched)

    # 2. A machine-wide kill. Judged in COMMAND POSITION, from the segment's own tokens, never
    # by the word appearing anywhere in the text. A segment shlex cannot parse fails open:
    # judge nothing rather than guess what it would run.
    previous = None
    call_tokens = []
    for segment in split_segments(stripped):
        if not segment.strip():
            continue
        tokens = segment_tokens(segment)
        if tokens is None:
            previous = None
            continue
        call_tokens.append(tokens)
        matched = kill_hit(tokens) or kill_fed_by_name(tokens) or kill_fed_by_pipe(tokens, previous)
        previous = tokens
        if matched:
            refuse(tool, "deny", "machine-wide-kill", KILL_REASON, matched)
        # Every agent shares the main session's id, so only the main session may own by tag.
        matched = foreign_pid_kill(tokens, transcript, "" if agent else session_id)
        if matched:
            refuse(tool, "deny", "machine-wide-kill", KILL_PID_REASON, matched)
    # The whole call, not one segment: an `lsof -t` pid list reaches a kill across a filter, a loop or a file.
    matched = lsof_pids_reach_kill(call_tokens)
    if matched:
        refuse(tool, "deny", "machine-wide-kill", KILL_REASON, matched)

    # 2b. A detached launch: a subshell background job, a nohup/setsid wrapper, disown right
    # after a background job, or a bare trailing background job with no pid captured anywhere
    # in the command. Same decision as rule 2, deny, for the same reason: no pid survives to
    # stop it later.
    matched = detached_launch_hit(stripped)
    if matched:
        refuse(tool, "deny", "detached-launch", DETACHED_LAUNCH_REASON, matched)

    # 2c. WSL: only the fixed list of test commands (owner ruling 2026-10-13).
    matched = wsl_hit(stripped)
    if matched:
        refuse(tool, "deny", "wsl-allow-list", WSL_REASON, matched)

    # 3. A live stream that never ends, or a waiter loop (Rule 9). A waiter loop whose own
    # condition polls a pattern gets the more specific reason: the pattern can match the loop's
    # own command line and never go false.
    poller = ""
    for segment in split_segments(stripped):
        matched = live_stream_hit(segment)
        if matched:
            refuse(tool, "deny", "live-stream", LIVE_STREAM_REASON, matched)
        poller = loop_condition_polls_a_pattern(segment) or poller
    matched = waiter_verdict(split_segments(stripped), background)
    if matched:
        if poller:
            refuse(tool, "deny", "waiter", PATTERN_POLLER_REASON, poller + " " + matched)
        refuse(tool, "deny", "waiter", WAITER_REASON, matched)
    matched = narrated_tail_hit(stripped)
    if matched:
        refuse(tool, "deny", "live-stream", NARRATED_TAIL_REASON, matched)
    matched = background_end_hit(split_segments(stripped), background, description)
    if matched:
        refuse(tool, "deny", "background-end", BACKGROUND_END_REASON, matched)

    # 3c. A command that sets the Playwright browser cache location (incident 2026-10-10).
    matched = playwright_command_hit(raw, stripped)
    if matched:
        refuse(tool, "deny", "playwright-browsers-path", PLAYWRIGHT_PATH_REASON, matched)

    matched = playwright_install_hit(stripped, agent)
    if matched:
        refuse(tool, "deny", "playwright-install", PLAYWRIGHT_INSTALL_REASON, matched)
    # 3d. A recursive delete under an unguarded variable (decision rm-on-a-variable-needs-a-guard).
    # The guard syntax `${NAME:?}` is POSIX, so a PowerShell tool call is not judged.
    hits = [] if POWERSHELL_CALL[0] else rm_var_hits(stripped, cwd)
    if hits:
        refuse(tool, "deny", "rm-var-unguarded", rm_var_reason(hits), "; ".join(hits))

    # 3b. A trap ported from banchi's `scripts/guard-shell.py`: `ln -s` onto a directory that is
    # already there. It reads the segment's own command word, never a substring, and reads the
    # filesystem rather than the text.
    run_in = _run_dir(stripped, cwd)
    ends = []
    nm_segments = split_segments(stripped, ends)
    for number, segment in enumerate(nm_segments):
        matched = ln_descends_hit(segment, run_in)
        if matched:
            refuse(tool, "deny", "ln-over-directory", LN_DESCENDS_REASON, matched)
        folder = dir_before_segment(nm_segments, number, cwd, ends)
        matched = folder and linked_nm_hit(segment, folder)
        if matched:
            refuse(tool, "deny", "linked-node-modules", LINKED_NM_REASON, matched)

    # 4. A wide delete refuses, and a force push asks.
    # Split before backslashes turn to slashes, so `it\'s` opens no quote that hides a delete.
    delete_segments = [delete_text(segment) for segment in split_segments(stripped)]
    for number in range(len(delete_segments)):
        matched, reason = parent_delete_hit(delete_segments, number, cwd)
        if matched:
            refuse(tool, "deny", "destructive-delete", reason, matched)
    for pattern in DESTRUCTIVE_DELETE:
        found = pattern.search(cmd)
        if found:
            refuse(tool, "deny", "destructive-delete", DELETE_REASON, found.group(0))
    for segment in delete_segments:
        matched = rm_delete_hit(segment) or cmd_exe_delete_hit(segment)
        if matched:
            refuse(tool, "deny", "destructive-delete", DELETE_REASON, matched)
    # 4b. After the wide-delete rules, so a delete of `.` or `..` keeps its own refusal.
    # A recursive delete of a relative target after a cd (decision rm-after-cd-names-absolute-path).
    hits = [] if POWERSHELL_CALL[0] else rm_after_cd_hits(stripped)
    if hits:
        refuse(tool, "deny", "rm-after-cd", rm_after_cd_reason(hits), "; ".join(hits))
    for segment in split_segments(stripped):
        for subcommand, args in git_calls(push_text(segment)):
            where, overrides = push_target(segment, stripped, cwd) if subcommand == "push" else ("", {})
            verdict = push_verdict(args, where, overrides) if subcommand == "push" else ""
            if verdict == "ask":
                ask_command("force-push", PUSH_ASK_REASON, "git push " + " ".join(args), "forced push")
            elif verdict:
                refuse(tool, verdict, "force-push", PUSH_REASON, "git push " + " ".join(args))
            elif subcommand == "push" and not read_verb("push", args):
                # Owner rulings 206 a and 207 a: a non-forced push that writes main or master, or an
                # implied destination off the branch's upstream. A dry run writes nothing.
                kind = push_ask_hit(args, where, overrides)
                if kind == "main":
                    ask_command("push-main", PUSH_MAIN_REASON, "git push " + " ".join(args),
                                "push to the default branch")
                elif kind == "stray":
                    ask_command("push-stray-branch", PUSH_STRAY_REASON, "git push " + " ".join(args),
                                "push to a stray branch")

    # 5. The environment file. This layer reads the command BEFORE normalization.
    refusal, logged = env_refusal(stripped)
    if not refusal:
        refusal, logged = env_heredoc_refusal(raw)
    if refusal:
        refuse(tool, "deny", "env-file", refusal + ". " + ENV_ADVICE, logged)

    # 6. A merge outside the merge tool, while the head has a check pending or red, or the read
    # could not run. Judged per segment from the command word, so quoted text never fires it.
    for segment in split_segments(stripped):
        merging = merge_call_of(segment) if segment.strip() else None
        if merging is None:
            continue
        verdict, detail = merge_check(merging[0], merging[1], cite_where)
        if verdict != "green":
            refuse(tool, "deny", "merge-checks", merge_check_reason(verdict, detail),
                   "gh pr merge " + merging[0] + " " + verdict)
        # A green bare merge in a repo that uses the merge tool asks; a deny above still wins.
        if cite_where and uses_merge_tool(cite_where):
            ask_command("bare-merge", BARE_MERGE_REASON, "gh pr merge " + merging[0], "bare merge")

    # 6a. A merge-tool call with a role flag its own get_session record does not prove (rule merge-role-proof).
    matched = role_proof_hit(stripped, transcript)
    if matched:
        refuse(tool, "deny", "merge-role-proof", ROLE_REASON, matched)

    # 6a2. A push to the record branch from a session its own record does not prove triage (rule
    # roadmap-one-writer). Cost: one `git rev-parse` and one small file read per push, and one
    # transcript read only when the push reaches the record branch.
    matched = record_writer_hit(stripped, cwd, transcript, record_branch_of, read_verb)
    if matched:
        refuse(tool, "deny", "roadmap-one-writer", RECORD_REASON, matched)

    # 6b. A pull request opened without --draft.
    for text, _in_message in _substitutions(stripped)[0]:
        if any(undrafted_pr_create(seg) for seg in split_segments(text) if seg.strip()):
            refuse(tool, "deny", "draft-pr", DRAFT_PR_REASON, "gh pr create")

    # 6c. A lane commit of the generated records page (decision records-index-at-merge).
    matched = records_page_hit(stripped, cwd)
    if matched:
        refuse(tool, "deny", "records-page", RECORDS_PAGE_REASON, matched)

    # 6c2. A commit or push that would carry all three conflict markers in one file (rule conflict-markers).
    # Cost: a few short `git` reads per commit or push segment, and none for a command with neither.
    kind, matched = conflict_markers_hit(stripped, cwd)
    if matched:
        markers_reason = (CONFLICT_MARKERS_CHAIN_REASON if kind == "chain" else
                          CONFLICT_MARKERS_PUSH_REASON if kind == "push" else CONFLICT_MARKERS_REASON)
        refuse(tool, "deny", "conflict-markers", markers_reason.format(file=matched), matched)

    # 6c3. A git write after a cd that `;`, a newline or `||` joins (decision git-after-cd-joins-with-and):
    # when the cd fails the write runs in the folder the shell stayed in. Placed
    # after conflict-markers, so a refusal that names the defect in the commit itself comes first.
    matched = "" if POWERSHELL_CALL[0] else git_after_cd_hit(stripped, cwd)
    if matched:
        refuse(tool, "deny", "git-after-cd", GIT_AFTER_CD_REASON, matched)
    matched = "" if POWERSHELL_CALL[0] else git_push_after_check_hit(stripped)
    if matched:
        refuse(tool, "deny", "git-after-cd", GIT_PUSH_AFTER_CHECK_REASON, matched)

    # 7. A frozen path.
    matched = frozen_shell_hit(stripped, cwd)
    if matched:
        refuse(tool, "deny", "frozen-path", FROZEN_REASON, matched)

    # 7b. A project config edit: allowed (Decision 7), and noted in the log only.
    matched = project_config_shell_hit(stripped, cwd)
    if matched:
        record(tool, "noted", "config-edit", matched)

    # 7c. A builder's shell write to a test file. The path comes from the stripped command, a script's
    # own writes (a python or node heredoc body, -c, -e) from the raw one. Only an agent with a builder
    # role is judged, the same guard as the Edit tools.
    if role == BUILDER_ROLE:
        matched = builder_shell_test_hit(raw, stripped, cwd)
        if matched:
            refuse(tool, "deny", "builder-test-edit", BUILDER_TEST_REASON, matched)

    # 8. The agent model cap. The PATH comes from the stripped command, the same machinery the
    # frozen path uses, so a redirect, a `tee`, a `sed -i` and a heredoc header all read as writes.
    # The CONTENT comes from the RAW command, because a heredoc body is the content being written
    # and rule 1 strips it. A command that writes a settings file and names the cap variable
    # somewhere else on the line is asked too: an over-trigger of one prompt, inside a scope this
    # narrow, beats a bypass by a second segment.
    matched = _shell_write_hit(stripped, cwd, is_settings_file)
    if matched:
        change = cap_change(raw)
        if change:
            ask_command("agent-model-cap", cap_ask_reason(change, matched),
                     log_path_and_text(matched, change), "settings write")
    settle_ask(tool, raw)

# ------------------------------------------------------------------ a waiting-page item states the question form
#
# hooks/question_form.py is the one home of the rules (`port-question`, `uniform-pick`, `press-link`,
# `command-in-item`, `gh-login-switch`, `task-names-check`, `owner-judge`, `question-form`, `question-departs`). This check runs them only for a
# write to this repo's waiting page.
from shared_names import DATA_TOOL  # noqa: E402  the one home of the tool name, shared with hooks/call_judge.py


def data_tool_judge(tool_input, cwd=""):
    """((rule, matched), writes): data_tool_hit's verdict and the item writes it judged, for the rule that
    reads the writes again (page-item-design)."""
    import question_form
    return question_form.page_item_hit(tool_input, cwd)


def data_tool_hit(tool_input, cwd=""):
    """(rule, matched) for the first write of a waiting item that a rule refuses, else ("", ""). The write
    filter and the page check live in hooks/question_form.py, which hooks/call_judge.py also reads."""
    return data_tool_judge(tool_input, cwd)[0]


# ------------------------------------------------------------------ a waiting page behind main is not published
#
# Rule `page-stale` (decision page-stale-publish). A publish of this repo's waiting page from a file whose
# code is not main's skills/waiting-page/page.html is refused. The compare is skills/waiting-page/stale_pages.py
# `matches`, the one home of "current" (the designData, roadmap block and title text are ignored, so a
# page the writer's --write built passes). Main is origin/main of the checkout that holds stale_pages.py.
# Known limit: a live page that is itself untouched (placeholder title, empty blocks) is refused too; the guard cannot read the live page.
# A read, a list, an asset upload, a publish of another page, an unreadable file or an unreadable main
# is not judged: unknown allows and logs one line. A republish of main's untouched template, with its title
# and its designData and roadmap blocks all equal to main's own (stale_pages.carries_data), is refused too:
# it would drop the live page's data. A first publish, with no url, is not judged. A current page with data writes the stamp
# (stale_pages.STAMP, main's blob sha) that hooks/session_start.sh reads back.
PAGE_TOOL = "Artifact"
PAGE_STALE_REASON = ("this file is behind main's skills/waiting-page/page.html, so a publish would put old page code on the "
                     "waiting page. Read the live page (Artifact action read), run the waiting-page skill's "
                     "stale_pages.py with `--page <saved live page> --write <out>`, and publish <out> to the same url. "
                     "(decision page-stale-publish, a waiting page behind main is not published)")
PAGE_EMPTY_REASON = ("this file's designData and roadmap blocks are the empty ones, so a republish would drop the live page's "
                     "data. Read the live page (Artifact action read), run the waiting-page skill's stale_pages.py "
                     "with `--page <saved live page> --write <out>`, and publish <out> to the same url. If <out> is "
                     "refused again, the live page is itself untouched: set the `<title>` of <out> to \"<repo> Cockpit\" "
                     "and publish it to the same url. "
                     "(decision page-stale-publish, a waiting page behind main is not published)")


def _waiting_page_folder(name):
    """The waiting-page skill folder that holds `name`: the one beside this hooks folder, else the config
    folder's copy. None when neither does."""
    for folder in (os.path.join(_HERE, "..", "skills", "waiting-page"),
                   os.path.join(guard_core.config_dir(), "skills", "waiting-page")):
        if os.path.isfile(os.path.join(folder, name)):
            return folder
    return None


def _stale_pages_module():
    """stale_pages.py from the skill folder beside this hooks folder, else the config folder's copy; None
    when neither exists. Loaded here and not at the top, so a call that is no waiting-page publish
    never pays for it."""
    folder = _waiting_page_folder("stale_pages.py")
    if folder is None:
        return None
    if folder not in sys.path:
        sys.path.insert(0, folder)  # stale_pages imports splice from its own folder
    return importlib.import_module("stale_pages")


def page_stale_hit(tool_input, cwd):
    """(reason, matched) when the call publishes this repo's waiting page from a file behind main, else
    None. A call that is no such publish leaves before any import. Fails open: any unread state allows."""
    path, url = tool_input.get("file_path"), tool_input.get("url")
    if (tool_input.get("action") not in (None, "", "publish") or tool_input.get("asset") is True
            or not isinstance(path, str) or not path or not isinstance(url, str) or not url):
        return None
    try:
        import contextlib
        import io
        import question_form
        root = question_form.waiting_page_root(tool_input, cwd)
        if not root:
            return None
        stale_pages = _stale_pages_module()
        if stale_pages is None:
            record(PAGE_TOOL, "noted", "page-stale", "unknown: stale_pages.py not found")
            return None
        with contextlib.redirect_stderr(io.StringIO()):  # stale_pages says why main is unreadable; the log line does here
            template = stale_pages.find_template(None)
        if not template:
            record(PAGE_TOOL, "noted", "page-stale", "unknown: main's page.html cannot be read")
            return None
        with open(os.path.join(cwd, path) if cwd else path, encoding="utf-8", errors="replace", newline="") as handle:
            live = handle.read()
    except OSError as err:
        record(PAGE_TOOL, "noted", "page-stale", "unknown: " + cap_safe(str(err.strerror or err), 100))
        return None
    except Exception as err:  # a layout that cannot be read: not judged
        record(PAGE_TOOL, "noted", "page-stale", "unknown: " + cap_safe(type(err).__name__ + ": " + str(err), 100))
        return None
    text, _source, blob = template
    if not stale_pages.normal(live):  # an empty file is unread, as stale_pages --page reads it
        record(PAGE_TOOL, "noted", "page-stale", "unknown: the file is empty")
        return None
    if not stale_pages.matches(text, live):
        return PAGE_STALE_REASON, path
    if not stale_pages.carries_data(text, live):
        return PAGE_EMPTY_REASON, path
    if blob and not stale_pages.write_stamp(root, blob):
        record(PAGE_TOOL, "noted", "page-stale", "unknown: the stamp cannot be written")
    # The file an item write's picture check loads (rule page-item-design): the absolute path of this publish.
    stale_pages.write_published(root, os.path.abspath(os.path.join(cwd, path) if cwd else path))
    return None


# ------------------------------------------------------------------ a design picture is checked at write
#
# Rule `page-item-design` (decision page-item-design). An ArtifactData set or update of a waiting item
# whose data carries `designs` or an option `design` runs skills/waiting-page/check_designs.mjs against the page
# file the last allowed publish stamped (stale_pages.PUBLISHED). The checker runs the page's own code, so the
# sentence a miss quotes is the page's. A miss denies. Unknown (no node, no stamp, the file gone, the checker
# unable to render, a run past its cap) allows and logs one `noted` line. A write with no picture starts no node.
CHECK_DESIGNS = "check_designs.mjs"
CHECK_DESIGNS_CAP = 25  # seconds for one run; the checker caps itself at 20
# One deadline for every pictured item of one call, under the 60 s hook timeout. A run never outlasts what is left of it.
PAGE_ITEM_DESIGN_BATCH_SECONDS = 45
_design_deadline = [None]  # time.monotonic() of the deadline of the call being judged; read by _run_check_designs
PAGE_ITEM_DESIGN_FIX = " (decision page-item-design, a waiting item's design picture is checked when the item is written). Republish the design (the waiting-page skill, \"Add a design\"), then write the item again."


def _run_check_designs(page_file, item):
    """(code, text) from the checker on `item` (a dict) against `page_file`: code 0 pass, 1 miss with the page's
    sentence as text, 3 unknown with the reason as text. The one seam that starts node."""
    import shutil
    import subprocess  # TimeoutExpired only; the child starts through _nowindow
    import _nowindow  # the one home of a no-window child start (hooks/_nowindow.py)
    import tempfile
    node = shutil.which("node")
    folder = _waiting_page_folder(CHECK_DESIGNS)
    if node is None or folder is None:
        return 3, "node is not installed" if node is None else CHECK_DESIGNS + " not found"
    cap = CHECK_DESIGNS_CAP
    if _design_deadline[0] is not None:
        cap = max(1.0, min(cap, _design_deadline[0] - time.monotonic()))
    with tempfile.TemporaryDirectory() as scratch:
        item_file = os.path.join(scratch, "item.json")
        with open(item_file, "w", encoding="utf-8") as handle:
            json.dump(item, handle)
        try:
            run = _nowindow.run([node, os.path.join(folder, CHECK_DESIGNS), "--page", page_file, "--item", item_file],
                                capture_output=True, text=True, timeout=cap)
        except subprocess.TimeoutExpired:
            return 3, "no answer in %d s" % cap
        except OSError as err:
            return 3, str(err.strerror or err)
    lines = run.stdout.strip().splitlines()
    try:
        problem = json.loads(lines[-1]).get("problem") if lines else None
    except ValueError:
        return 3, "no answer line; exit %d" % run.returncode
    if run.returncode == 1 and isinstance(problem, str) and problem:
        return 1, problem
    if run.returncode == 0:
        return 0, ""
    return 3, (run.stderr.strip().splitlines() or ["exit %d" % run.returncode])[-1]


# ------------------------------------------------------------------ a design names its file, in a mockup home
#
# Rule `mockup-home` (decision mockup-home). An ArtifactData set or update of a waiting item whose data carries `designs`
# is denied when a design has no `file`, or a `file` outside the repo's design folder (lint/layout.py mockup_home_problem;
# a machine-home path is outside it). It judges the path's shape only, so it reads no file, asks no origin and starts no
# node; the roadmap build checks that origin holds the file. It runs before `page-item-design`. An item that is closed or
# has no `designs` is not judged. An unreadable layout allows and logs one `noted` line.
MOCKUP_HOME_FIX = " (decision mockup-home, a mockup kept off the repo is gone with the machine or the account that holds it)"


def mockup_home_hit(writes, tool_input, cwd):
    """(reason, matched) for the first `designs` entry of `writes` with no `file` or a refused one, else None.
    Fails open on any unread state."""
    import question_form
    try:
        root = question_form.waiting_page_root(tool_input, cwd)
        found = question_form.design_file_problems(writes, root) if root else []
    except Exception as err:
        record(DATA_TOOL, "noted", "mockup-home", "unknown: " + cap_safe(type(err).__name__ + ": " + str(err), 100))
        return None
    if not found:
        return None
    doc_id, slug, problem = found[0]
    return "design " + cap_safe(slug, 40) + ": " + problem + MOCKUP_HOME_FIX, "item " + cap_safe(str(doc_id or "?"), 40)


def page_design_hit(writes, tool_input, cwd):
    """(reason, matched) for the first write in `writes` whose picture the page would refuse, else None. A write
    with no picture leaves before the record is read. A set is judged whole. An update is judged only when it
    carries both `options` and `designs`: the checker needs the other half, which the write does not hold, so a
    partial update is allowed with one noted line. The pictured items of one call share one deadline. Fails open
    on any unread state."""
    import question_form
    pictured = []
    for op, doc_id, data in question_form.design_writes(writes):
        if op == "update" and not (data.get("options") and data.get("designs")):
            record(DATA_TOOL, "noted", "page-item-design",
                   "partial: an update of item %s carries only %s, so its picture is not checked"
                   % (cap_safe(str(doc_id or data.get("id") or "?"), 40), "options" if data.get("options") else "designs"))
            continue
        pictured.append((doc_id, data))
    if not pictured:
        return None
    try:
        root = question_form.waiting_page_root(tool_input, cwd)
        stale_pages = _stale_pages_module()
        if stale_pages is None:
            record(DATA_TOOL, "noted", "page-item-design", "unknown: stale_pages.py not found")
            return None
        page_file = stale_pages.read_published(root) if root else None
    except Exception as err:
        record(DATA_TOOL, "noted", "page-item-design", "unknown: " + cap_safe(type(err).__name__ + ": " + str(err), 100))
        return None
    if not page_file or not os.path.isfile(page_file):
        record(DATA_TOOL, "noted", "page-item-design",
               "unknown: " + ("no published page stamped" if not page_file else "the stamped page file is gone"))
        return None
    deadline = time.monotonic() + PAGE_ITEM_DESIGN_BATCH_SECONDS
    _design_deadline[0] = deadline
    try:
        for done, (doc_id, data) in enumerate(pictured):
            if time.monotonic() >= deadline:
                record(DATA_TOOL, "noted", "page-item-design",
                       "unknown: the %d s budget of this call is spent, %d item(s) not checked"
                       % (PAGE_ITEM_DESIGN_BATCH_SECONDS, len(pictured) - done))
                return None
            try:
                code, text = _run_check_designs(page_file, dict(data, id=data.get("id") or doc_id or "item"))
            except Exception as err:
                code, text = 3, type(err).__name__ + ": " + str(err)
            if code == 1:
                return text + PAGE_ITEM_DESIGN_FIX, "item " + str(doc_id or data.get("id") or "?")
            if code != 0:
                record(DATA_TOOL, "noted", "page-item-design", "unknown: " + cap_safe(text, 100))
    finally:
        _design_deadline[0] = None
    return None


# ------------------------------------------------------------------ impeccable is review-only
#
# docs/decisions/design-skills.md, rule `impeccable-review-only`: the skill loads only for a review
# (`audit`, `critique`). Its build commands and its settings writers are refused. The reason names
# no command; the log holds what the call asked for.
IMPECCABLE_REASON = ("impeccable is for a design review only. Ask for a review of the rendered "
                     "screens; make any change to the design by hand.")
IMPECCABLE_SKILLS = ("impeccable", "impeccable:impeccable")
IMPECCABLE_REVIEWS = ("audit", "critique")
# The skill reads the FIRST word of its args as the command and the rest as target text (skills/impeccable
# SKILL.md, Routing); it asks once when two commands fit. So a `;` starts no second command, and a part
# after it is refused only when it opens with a command verb other than a review: the Commands table
# of that SKILL.md is the list, read when a review carries a `;`. `|`, `&&` and a newline always chain.
IMPECCABLE_CHAIN = re.compile(r"[|\n]|&&")
IMPECCABLE_JOINERS = ("then", "and")
IMPECCABLE_SKILL_FILE = os.path.join(_HERE, "..", "skills", "impeccable", "SKILL.md")
IMPECCABLE_VERB_ROW = re.compile(r"^\| `([a-z]+)[^`]*` \| [A-Z][a-z]+ \|", re.M)
RUNNER_WORDS = ("npx", "bunx", "node", "pnpm", "yarn", "npm", "dlx", "exec", "run", "x")
PACKAGE_FLAGS = ("-p", "--package")


def impeccable_name(token: str) -> str:
    """The package or script name of a token, without a path, a `@version` or an extension."""
    name = basename(token).split("@", 1)[0]
    return name.rsplit(".", 1)[0]


def impeccable_command_verbs():
    """The command verbs in the Commands table of the impeccable SKILL.md, or None when the file or
    the table cannot be read. Unread, every part after a `;` is refused, as it was before the table."""
    try:
        with open(IMPECCABLE_SKILL_FILE, encoding="utf-8") as handle:
            table = re.split(r"(?m)^## ", handle.read().split("\n## Commands", 1)[1], 1)[0]
    except (OSError, IndexError, UnicodeDecodeError):
        return None
    return set(IMPECCABLE_VERB_ROW.findall(table)) or None


def impeccable_skill_hit(tool_input) -> str:
    skill, args = tool_input.get("skill"), tool_input.get("args") or ""
    if not isinstance(skill, str) or skill.lstrip("/") not in IMPECCABLE_SKILLS:
        return ""
    words = args.split(";")[0].split() if isinstance(args, str) else []
    text = args.strip() if isinstance(args, str) else ""
    if words and words[0] in IMPECCABLE_REVIEWS and not IMPECCABLE_CHAIN.search(text):
        parts = [part.split() for part in text.split(";")[1:]]
        for part in parts:   # "then polish" opens with polish: read past a joining word
            while part and part[0] in IMPECCABLE_JOINERS:
                part.pop(0)
        verbs = impeccable_command_verbs() if any(parts) else set()
        if verbs is not None and not any(part[0] in verbs - set(IMPECCABLE_REVIEWS)
                                         for part in parts if part):
            return ""
    return ("skill %s %s" % (skill, args))[:100]


def impeccable_shell_hit(segment: str) -> str:
    """A segment that runs impeccable with anything but `detect ...` or `hooks status`. Shell
    wrappers (`bash -c`, `npx -c`) are unwrapped; a runner or script suffix (`.cmd`, `.exe`,
    `.mjs`) and PowerShell's call operator `&` are read through."""
    tokens = segment_tokens(segment)
    if not tokens:
        return ""
    script = inline_script(tokens)
    if script:
        return next((hit for part in split_segments(script)
                     if (hit := impeccable_shell_hit(part))), "")
    index = resolve_command(tokens)
    if index is None or index >= len(tokens):
        return ""
    while index < len(tokens) and (impeccable_name(tokens[index]) in RUNNER_WORDS
                                   or tokens[index].startswith("-")):
        if tokens[index] in ("-c", "--call") and index + 1 < len(tokens):
            return next((hit for part in split_segments(tokens[index + 1])
                         if (hit := impeccable_shell_hit(part))), "")
        index += 2 if tokens[index] in PACKAGE_FLAGS else 1
    if index >= len(tokens) or impeccable_name(tokens[index]) != "impeccable":
        return ""
    rest = tokens[index + 1:]
    if rest[:1] == ["detect"] or rest[:2] == ["hooks", "status"]:
        return ""
    return segment.strip()[:100]


# A PowerShell here-string: `@'` ... `'@` is text, `@"` ... `"@` runs its `$(...)`.
_HERE_STRING = re.compile(r"@(['\"])[ \t]*\r?\n(.*?)\r?\n\1@", re.S)


def impeccable_command_hit(raw: str) -> str:
    """Judge a whole command for impeccable. Only a body a shell reads is judged as shell lines,
    and an unquoted heredoc body or an expandable here-string is judged by the `$(...)` and
    backticks it runs. The limits: a Python, Node, Perl or Ruby
    body is not read, and a here-string body is allowed."""
    texts = []
    if POWERSHELL_CALL[0] and "@" in raw:
        def cut(found):
            if found.group(1) == '"':
                texts.extend(t for t, _ in _substitutions(found.group(2), powershell=True,
                                                          heredoc=True)[0][:-1])
            return "x"
        raw = _HERE_STRING.sub(cut, raw)
    texts.append(strip_heredoc_bodies(raw, shells_only=True))
    if "<<" in raw:
        for quote, body, _ in _split_heredocs(raw)[1]:
            if not quote:
                texts.extend(t for t, _ in _substitutions(body, heredoc=True)[0][:-1])
    for text in texts:
        for segment in split_segments(text):
            matched = impeccable_shell_hit(segment)
            if matched:
                return matched
    return ""


# ------------------------------------------------------------------ simulator boots
#
# Decision sweep-shuts-down-idle-simulators, rulings 3 and 4. A boot is an
# `xcodebuild -destination` that names a shut-down simulator, or the simulator MCP tool's `launch`
# naming one. `simctl list` runs only after a call matched as a boot. The idle test is the sweep
# tier's own (`sweep.sim_keep_code`), imported lazily: janitor/sweep.py imports this file.
# A raw `simctl boot` and a Simulator.app open are refused first, on the text alone, by
# `simulator-boot-bypass` (decision sim-test-is-the-one-boot-path, ruling 4).
SIM_MCP = "mcp__Claude_Code_iOS_Simulator__control"
SIM_BOOT_CAP = 2


def _simctl_boot_args(word: str, rest: list):
    """The arguments after `simctl boot`, by the command word WORD (`xcrun` or `simctl`), or None when the
    command is no `simctl boot`. The list is empty when xargs feeds the device."""
    if word in ("xcrun", "simctl") and "simctl" in ([word] + rest):
        after = ([word] + rest)[([word] + rest).index("simctl") + 1:]
        if after[:1] == ["boot"]:
            return after[1:]
    return None


def _sim_commands(segment: str):
    """(command word as written, its arguments) at each command of SEGMENT and, through `inner_commands`, of each
    command a wrapper hands on (`bash -c`, `sh -lc`, `sudo`, `$(...)`). The one walk of the simulator rules.
    A quoted or echoed text is not a command and is not read."""
    tokens = segment_tokens(segment)
    if not tokens:
        return
    for start in command_indexes(tokens):
        yield tokens[start], tokens[start + 1:]
    for text in inner_commands(tokens):
        for part in split_segments(text):
            yield from _sim_commands(part)


def _xcodebuild_boot_names(rest: list) -> list:
    """The device names or UDIDs the arguments of an `xcodebuild` boot by `-destination`. Empty when it boots none."""
    found = []
    for i, token in enumerate(rest):
        value = rest[i + 1] if token == "-destination" and i + 1 < len(rest) else (
            token[len("-destination="):] if token.startswith("-destination=") else "")
        # The tokens keep no quote marks, so a shell operator glued after the closing quote
        # (`'id=X'&`, `"id=X">/dev/null`, `(cd ios && xcodebuild ... 'OS=17.0')`) is read into the value.
        # Cut it at the first `&`, `<`, `>`, `|` or `;`, then drop each trailing `)` that no `(` opens,
        # so "iPhone SE (3rd generation)" keeps its own paren.
        value = re.split(r"[&<>|;]", value, maxsplit=1)[0]
        while value.endswith(")") and value.count(")") > value.count("("):
            value = value[:-1]
        fields = dict(p.split("=", 1) for p in value.split(",") if "=" in p)
        if "iOS Simulator" in fields.get("platform", "") and (fields.get("id") or fields.get("name")):
            os_ = fields.get("OS", "")  # a numeric OS= filters a name; an id, or OS=latest, filters nothing
            os_ = "" if fields.get("id") or not re.fullmatch(r"[0-9.]+", os_) else os_
            found.append((fields.get("id") or fields["name"], os_))
    return found


def _sim_boots(segment: str) -> list:
    """[(name or (name, OS), remedy)] for each simulator the xcodebuild commands of SEGMENT boot by `-destination`."""
    return [(n, _sim_route_remedy(rest)) for command, rest in _sim_commands(segment)
            if basename(command) == "xcodebuild" for n in _xcodebuild_boot_names(rest)]


def _simulator_app_open(rest: list) -> bool:
    """True when the arguments of an `open` name Simulator.app: `-a Simulator[.app]`, a path that ends in
    Simulator.app, or `-b com.apple.iphonesimulator`. macOS reads these names without case."""
    for i, arg in enumerate(rest):
        low = arg.lower().rstrip("/")
        if re.fullmatch(r"-[A-Za-z]*[ab][A-Za-z]*", arg) and i + 1 < len(rest):  # a cluster (`-ga`, `-an`) with a or b takes the next word
            value = basename(rest[i + 1].rstrip("/"))
            if ("a" in arg and re.sub(r"\.app$", "", value) == "simulator") or (
                    "b" in arg and value == "com.apple.iphonesimulator"):
                return True
        elif low.endswith("/simulator.app") or low == "simulator.app":
            return True
    return False


def sim_bypass_hit(segment: str) -> str:
    """The matched text when one segment boots a simulator outside sim-test, else ''. Judged by the
    command word, at each command of the segment and in each command a wrapper hands on
    (`_sim_commands`), so `bash -c`, `sudo` and `$(...)` are read and a quoted or echoed text is not."""
    for command, rest in _sim_commands(segment):
        word = basename(command)
        if word == "open" and _simulator_app_open(rest):
            return ("open " + " ".join(rest))[:100]
        if _simctl_boot_args(word, rest) is not None:
            return " ".join([command] + rest)[:100]
    return ""


SIM_BYPASS_REASON = (
    "a simulator is booted through `sim-test` alone: it takes the one lock per Mac, boots, runs the "
    "tests and shuts down. Run `sim-test -scheme <scheme>` instead. "
    "(decision sim-test-is-the-one-boot-path)"
)


# The xcodebuild options that take the next word as their value, written from memory of `man xcodebuild` and
# not checked against it. Any other dash word is a flag with no value, so the word after it can be the action.
# A wrong entry changes only the remedy text, never the verdict. A colon or `=` form
# (`-only-testing:X`, `-scheme=X`) holds its value in the same word and is in no list.
SIM_ROUTE_VALUE_FLAGS = frozenset({
    "-project", "-workspace", "-target", "-scheme", "-configuration", "-xcconfig", "-arch", "-sdk", "-toolchain",
    "-destination", "-destination-timeout", "-jobs", "-derivedDataPath", "-resultBundlePath", "-resultBundleVersion",
    "-resultStreamPath", "-archivePath", "-exportPath", "-exportOptionsPlist", "-testPlan", "-xctestrun",
    "-testProductsPath", "-only-testing", "-skip-testing", "-only-test-configuration", "-skip-test-configuration",
    "-testLanguage", "-testRegion", "-test-iterations", "-parallel-testing-enabled", "-parallel-testing-worker-count",
    "-maximum-parallel-testing-workers", "-maximum-concurrent-test-device-destinations",
    "-maximum-concurrent-test-simulator-destinations", "-test-timeouts-enabled",
    "-default-test-execution-time-allowance", "-maximum-test-execution-time-allowance",
    "-test-repetition-relaunch-enabled", "-collect-test-diagnostics", "-enableCodeCoverage",
    "-enableAddressSanitizer", "-enableThreadSanitizer", "-enableUndefinedBehaviorSanitizer",
    "-enablePerformanceTestsDiagnostics", "-localizationPath", "-exportLanguage", "-clonedSourcePackagesDirPath",
    "-packageCachePath", "-scmProvider", "-defaultPackageRegistryURL", "-packageAuthorizationProvider",
    "-authenticationKeyPath", "-authenticationKeyID", "-authenticationKeyIssuerID", "-framework", "-library",
    "-headers", "-debug-symbols", "-output", "-find-executable", "-find-library", "-importPlatform",
    "-downloadPlatform", "-buildVersion", "-architectureVariant", "-exportPlatform", "-platform",
})


def _sim_route_remedy(rest: list) -> str:
    """The remedy for an `xcodebuild -destination` command with arguments REST: `sim-test` with its arguments (no
    -destination, no `test` action: sim-test adds it) when the action is `test`, else the generic
    destination. The action is the word `test` that no option takes as its value. The shell's redirects
    (`2>&1`, `> out.log`) and a lone `&` are no xcodebuild arguments, so the remedy drops them."""
    args, action, skip = [], False, False
    for i, token in enumerate(rest):
        if skip:
            skip = False
        elif token in ("-destination", "&") or token.startswith("-destination="):
            skip = token == "-destination"
        elif re.fullmatch(r"\d*[<>&|]+", token):
            skip = True  # a bare redirect operator (`>`, `2>`, `>&`, `&>`): its target is the next word
        elif REDIRECTION.fullmatch(token):
            pass
        elif token == "test" and not (i and rest[i - 1] in SIM_ROUTE_VALUE_FLAGS):
            action = True
        else:
            args.append(token)
    if action:
        return "Run `sim-test %s` instead." % " ".join(shlex.quote(a) for a in args)
    return "Use `-destination 'generic/platform=iOS Simulator'` instead, and boot nothing."


def sim_lease_holds(session: str, udids: list) -> bool:
    """True when SESSION holds a live sim-lease whose slot maps to every UDID in UDIDS (decision
    sim-test-is-the-one-boot-path, ruling 5). The slot map, the liveness test and the read live in bin/sim-lease,
    loaded by path as it has no .py name. An empty session or UDIDS, or any failure to load or read, is False:
    the refusal stands. The read takes no lock and writes nothing, and no bytecode file is written for the load."""
    if not session or not udids:
        return False
    keep = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "bin", "sim-lease")
        loader = importlib.machinery.SourceFileLoader("sim_lease", path)
        spec = importlib.util.spec_from_loader("sim_lease", loader)
        lease = importlib.util.module_from_spec(spec)
        loader.exec_module(lease)
        held = {lease.SLOT_UDID[e["slot"]].casefold() for e in lease.live_leases()
                if session == e.get("session") and e.get("slot") in lease.SLOT_UDID}
    except Exception:
        return False
    finally:
        sys.dont_write_bytecode = keep
    return all(u.casefold() in held for u in udids)


def sim_boot_refusal(tool: str, names: list, remedies: dict = None, session: str = "") -> None:
    """Refuse a boot of any of NAMES when two devices are booted, or an idle twin is booted. After those two
    rules, an `xcodebuild -destination` boot (REMEDIES maps a name to its remedy) is refused as
    simulator-boot-route, and an MCP launch as simulator-boot-lease, unless SESSION holds a live sim-lease whose
    slot is the launched device (sim_lease_holds)."""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "janitor"))
        import sweep
    except Exception:
        return  # fail open: no janitor beside this file (a cloud copy)
    if not sweep.sim_available():
        return
    devices = sweep.sim_read_devices()
    if devices is None:
        return
    shut_down = []
    for name in names:
        name, os_ = name if isinstance(name, tuple) else (name, "")  # a destination's OS= picks a runtime
        key = name.strip().casefold()  # a name compares without case or outer spaces; a UDID has no case
        hits = [d for d in devices if key == d["udid"].casefold() or key == d["name"].strip().casefold()]
        if os_:  # not importable from sim_boot_record: its version() is nested in by_name_ok
            hits = [d for d in hits if (v := d["runtime"].split("SimRuntime.")[-1].split("-", 1)[-1].replace("-", ".")) == os_
                    or v.startswith(os_ + ".")] or hits  # no runtime matches: judge them all
        hits = [d for d in hits if d["state"] != "Booted"]
        if not hits:
            continue  # unknown device, or every match already up: not a boot
        booted = [d for d in devices if d["state"] == "Booted"]
        if len(booted) >= SIM_BOOT_CAP:
            refuse(tool, "deny", "simulator-boot-cap",
                   "%d simulators are already booted: %s. Use one, or ask the owner to stop one, "
                   "then boot." % (len(booted), "; ".join("%s (%s)" % (d["name"], d["udid"]) for d in booted)),
                   name)
        boots, table, now = (sweep.sim_read_boots(os.path.join(guard_core.config_dir(), "state", "sim-boots.jsonl")),
                             sweep._read_ps_table(), time.time())
        for twin, want in ((t, w) for t in booted for w in hits):
            if (twin["udid"] in boots  # an unrecorded device is never idle
                    and (twin["deviceTypeIdentifier"], twin["runtime"]) == (want["deviceTypeIdentifier"], want["runtime"])
                    and sweep.sim_keep_code(twin, boots, table, now) is None):
                refuse(tool, "deny", "simulator-boot-twin",
                       "An idle booted simulator of the same type and runtime exists: %s (%s). Use it "
                       "instead of booting another." % (twin["name"], twin["udid"]), name)
        shut_down.append((name, [h["udid"] for h in hits]))
    for name, udids in shut_down:
        if tool == SIM_MCP:
            if sim_lease_holds(session, udids):
                continue  # this session's live lease is for this very device: the boot is under the lease
            refuse(tool, "deny", "simulator-boot-lease",
                   "A launch of the shut-down simulator %s boots it outside the one lock: the Mac "
                   "shares one simulator across repos, and `sim-test` holds that lock. Run `sim-test`, "
                   "which boots it under the lock, or launch a simulator that is already booted. "
                   "(decision sim-test-is-the-one-boot-path)" % name, name)
        elif (remedies or {}).get(name):
            refuse(tool, "deny", "simulator-boot-route",
                   "`xcodebuild -destination` boots %s outside the `sim-test` lock. %s "
                   "(decision sim-test-is-the-one-boot-path)" % (name, remedies[name]), name)


def worktree_home_hit(payload, tool: str, tool_input: dict, cwd: str) -> str:
    """Rule 0, worktree-home: return the log detail when an agent's call reaches outside its own
    worktree, else ''. `status` is "none" for the orchestrator (no `agent_id`) and for tools this
    rule does not judge; "unknown" when the record could not be read at all, which allows (an
    unreadable state is never a hit); "no-record" for a non-isolated agent, which allows everything;
    "home" once the agent's worktree is known, from this call or an earlier one. Read/Grep are never
    checked here: the agent must still be able to read and report
    (decision an-agent-outside-its-home-tree-must-stop)."""
    # Rule 0 alone reads a Git Bash `/c/Users/...` cwd in the form the home record is written in. Off
    # Windows `/c/` is a real folder. One reader of the drive spelling: `_expanded`. Every other
    # rule sees `cwd` as main does.
    home_cwd = drive_form_cwd(cwd)
    home_status, home, home_primary = agent_worktree_home(payload, home_cwd)
    if home_status != "home":
        return ""
    if tool in SHELL_TOOLS:
        # The one allowed call is a lone `cd` back into the home (a recovery step).
        if (path_is_inside(home_cwd, home) is False
                and not is_move_into(tool, str(tool_input.get("command", "")), home_cwd, home)):
            return "shell cwd outside recorded agent home"
    elif tool in WRITE_TOOLS:
        for write_target in (write_targets(tool_input) if home_primary else ()):
            # A relative `file_path` resolves against the CALLER's cwd, the payload's own
            # `cwd`, never the guard process's. `_resolved` (already used by `is_frozen` and
            # `is_project_config` for the same reason) joins it before either check.
            try:
                resolved_target = _resolved(write_target, home_cwd)
            except Exception:
                resolved_target = write_target
            if (path_is_inside(resolved_target, home_primary) is True
                    and path_is_inside(resolved_target, home) is False
                    and not _own_red_run(payload, home_primary, resolved_target, False)):
                return "write target outside recorded agent home"
    return ""


# A shell command with none of these can write no named file, so it spends no git read here. A
# redirect onto a stream (`2>&1`) or the null device writes no checkout, so it is dropped first.
SHELL_QUIET_REDIRECT = re.compile(r"\d*>>?[ \t]*(?:&[0-9-]|/dev/null\b)")
SHELL_WRITE_HINT = re.compile(r">|" + MUTATING_COMMAND + r"|\bsed\b")


def _owning_checkout(path: str, roots) -> str:
    """The deepest checkout root that holds `path`, else ''. A nested worktree under the
    primary's `.claude/worktrees/` is deeper than the primary, so it owns its own files."""
    owners = [root for root in roots if path_is_inside(path, root) is True]
    return max(owners, key=len) if owners else ""


def _checkout_root_by_stat(folder: str) -> str:
    """The nearest folder at or above `folder` that holds a `.git` entry (a folder, or a linked
    worktree's file), found by stat alone, else ''. No git is spawned."""
    while folder:
        if os.path.exists(os.path.join(folder, ".git")):
            return folder
        parent = os.path.dirname(folder)
        if parent == folder:
            return ""
        folder = parent
    return ""


def _git_common_dir(root: str) -> str:
    """The git common directory of the checkout at ROOT, read from files alone, else ''. A `.git`
    folder is its own; a `.git` file names `gitdir: <dir>`, and `<dir>/commondir` names the common
    one, relative to `<dir>`. No git is spawned."""
    dot = os.path.join(root, ".git")
    try:
        if os.path.isdir(dot):
            return os.path.realpath(dot)
        with open(dot, encoding="utf-8") as handle:
            first = handle.readline(4096).strip()
        if not first.startswith("gitdir:"):
            return ""
        git_dir = os.path.join(root, first[len("gitdir:"):].strip())
        try:
            with open(os.path.join(git_dir, "commondir"), encoding="utf-8") as handle:
                git_dir = os.path.join(git_dir, handle.readline(4096).strip())
        except OSError:
            pass  # no commondir: a submodule's or a bare-style git dir is its own common dir
        return os.path.realpath(git_dir)
    except (OSError, UnicodeDecodeError):
        return ""


def _clone_origin(common: str) -> str:
    """The `[remote "origin"]` url in COMMON's config file, else '' (no file, no origin, no url)."""
    try:
        with open(os.path.join(common, "config"), encoding="utf-8") as handle:
            lines = handle.read(1 << 20).splitlines()
    except (OSError, UnicodeDecodeError):
        return ""
    in_origin = False
    for line in lines:
        line = line.strip()
        if line.startswith("["):
            in_origin = re.fullmatch(r'\[remote\s+"origin"\]', line, re.IGNORECASE) is not None
        elif in_origin:
            found = re.match(r"url\s*=\s*(.+)$", line, re.IGNORECASE)
            if found:
                return found.group(1).strip().strip('"')
    return ""


def _origin_local(url: str) -> str:
    """The realpath a local-path origin names, else '' for a network url."""
    if url.startswith("file://"):
        url = url[len("file://"):]
    if os.path.isabs(url):
        return os.path.realpath(url)
    return ""


def _origin_key(url: str) -> str:
    """The `owner/repo` of a network origin url, lower case, with a `.git` suffix and a trailing `/`
    dropped, in any form (https, ssh `git@host:owner/repo`, a proxy url); '' when it names none."""
    url = url.rstrip("/\\")
    if url.endswith(".git"):
        url = url[:-len(".git")].rstrip("/")
    parts = [part for part in re.split(r"[/:\\]", url) if part]
    return "/".join(parts[-2:]).lower() if len(parts) >= 2 else ""


def _same_repo(common: str, other: str) -> bool:
    """True when the clones with git common dirs COMMON and OTHER are the same repo: a local-path
    origin that names the other clone, or two network origins naming one `owner/repo`. An origin
    that is missing or unreadable on either side is unknown, never a match."""
    urls = (_clone_origin(common), _clone_origin(other))
    for url, theirs in ((urls[0], other), (urls[1], common)):
        local = _origin_local(url) if url else ""
        if local and local in (theirs, os.path.dirname(theirs)):
            return True
    if urls[0] and _origin_local(urls[0]) and _origin_local(urls[0]) == _origin_local(urls[1] or ""):
        return True  # two clones of one local bare repository
    return (all(urls) and not any(_origin_local(url) for url in urls)
            and _origin_key(urls[0]) != "" and _origin_key(urls[0]) == _origin_key(urls[1]))


def _git_verb_called(command: str) -> bool:
    """True when COMMAND runs a git verb of SESSION_HOME_GIT_VERBS. A text with no `git` in it is
    never scanned, so a call with no git word spends nothing."""
    return "git" in command and any(
        verb in SESSION_HOME_GIT_VERBS
        for segment in split_segments(command, []) for verb, _args in git_calls(segment))


def _git_verb_may_hit(command: str, where: str) -> bool:
    """True when a git verb of SESSION_HOME_GIT_VERBS in COMMAND can change another clone's files, so
    it is worth the one `git worktree list`: the cwd is stranded in a separate clone of the
    `CLAUDE_PROJECT_DIR` clone, or a `-C` or `cd` folder's nearest `.git` is not the cwd's. The folder
    of each verb is read by session_home_git_hit, the one reader. Stat and small file reads; no git."""
    own_root = _checkout_root_by_stat(os.path.realpath(where)) if where else ""
    if not own_root:
        return False
    stranded = _clone_scope(None, own_root)[2]
    return bool(session_home_git_hit(
        command, where,
        lambda folder, _at: stranded or _checkout_root_by_stat(os.path.realpath(folder)) != own_root))


def _separate_clone(path: str, tops, common: str) -> bool:
    """True when PATH sits in a separate clone of the same repo as the checkouts TOPS, whose git
    common dir is COMMON: the nearest `.git` above it is not inside a top (a submodule), not above
    one (a dotfiles repo), names another common dir, and that clone has the same origin. Stat and
    small file reads only."""
    root = _checkout_root_by_stat(os.path.realpath(path))
    if not root or not common:
        return False
    if any(path_is_inside(root, top) is True or path_is_inside(top, root) is True for top in tops):
        return False
    other = _git_common_dir(root)
    return bool(other) and other != common and _same_repo(common, other)


def _clone_scope(roots, own: str):
    """(tops, common, stranded): the checkouts and common dir a path must sit in, to be no separate
    clone. Normally this clone's own. When `CLAUDE_PROJECT_DIR` names a folder in a clone that is a
    separate clone of the cwd's, the session is stranded: its home clone is the reference, and
    `stranded` is True. An unset, unreadable or unrelated value is unknown, and changes nothing."""
    home = os.environ.get("CLAUDE_PROJECT_DIR", "")
    try:
        top = _checkout_root_by_stat(os.path.realpath(home)) if home else ""
        common = _git_common_dir(top) if top else ""
        if common and _separate_clone(own, [top], common):
            return [top], common, True
    except Exception:
        pass
    return roots, _git_common_dir(own), False


def _cd_targets(tool: str, command: str, where: str):
    """The folder each real `cd`, `pushd` or `Set-Location` segment of COMMAND moves into, as a
    realpath. Read the way `_run_dir` reads the shell: heredoc bodies dropped first, one segment at a
    time, so a `cd` in a quote, a comment or a heredoc body is text. A target that holds a variable,
    a bare `cd`, `cd -`, a bare `pushd` or `pushd +N`, and a folder that does not exist are not read."""
    POWERSHELL_CALL[0] = tool == "PowerShell"
    command = _strip_heredoc_bodies_unconditionally(command)
    if not re.search(r"\bcd\b|set-location|\bpushd\b", command, re.IGNORECASE):
        return []
    found, ends = [], []
    segments = split_segments(command, ends)
    for number, segment in enumerate(segments):
        tokens = segment_tokens(segment)
        named = _segment_cd_target(tokens, ("cd", "set-location", "pushd")) if tokens else None
        if named is None or _unexpanded(named):
            continue
        # An absolute target needs no known folder.
        at = dir_before_segment(segments, number, where, ends)
        folder = shell_abs(named, at)
        if folder and os.path.isdir(folder):
            found.append(os.path.realpath(folder))
    return found


def _cd_home_exempt(payload, cwd: str, target: str) -> bool:
    """True when a `cd` into TARGET goes into the caller's recorded agent home (the recovery step
    worktree-home allows) or, for a call with no `agent_id`, the session's recorded home. It skips
    the `cd` act only; the write scan still judges every write in the same command. File reads,
    no git."""
    status, home, _ = agent_worktree_home(payload, cwd)
    if status == "home" and path_is_inside(target, home) is True:
        return True
    if isinstance(payload, dict) and payload.get("agent_id"):
        return False
    primary, _lane = session_home_place(cwd)
    record = session_home_record(payload, primary) if primary else ""
    try:
        with open(record, encoding="utf-8") as handle:
            held = handle.read().strip()
    except OSError:
        return False
    return bool(held) and path_is_inside(target, held) is True


# The shell verbs that may name the red-run folder's own root: `cp x <red>/` writes inside it. No
# other verb may, so `rm -rf <red>` stays refused (an-agent-outside-its-home-tree-must-stop).
RED_RUN_ROOT_VERBS = ("cp",)


def _own_red_run(payload, primary: str, path: str, root_ok: bool = True) -> bool:
    """True when PATH is inside the caller's own test-author red-run folder
    `<primary>/.claude/worktrees/agent-<its agent id>-<suffix>`. The one home for that test: the
    `cd` act and the write act of other-checkout, and worktree-home's Write target, all ask it.
    PRIMARY is the primary checkout alone, so a folder under a linked worktree never counts. The id and
    its dash match whole, so a sibling whose id only starts with this one does not pass. ROOT_OK False
    leaves the folder itself out: a write passes only strictly inside it, so a delete of the folder
    is still refused. Both sides compare case-folded and realpath'd (`path_is_inside`)."""
    agent_id = payload.get("agent_id") if isinstance(payload, dict) else None
    if not isinstance(agent_id, str) or not agent_id or not primary or not path:
        return False
    holder = os.path.join(primary, ".claude", "worktrees")
    folder = path
    while True:
        parent = os.path.dirname(folder)
        if parent == folder:
            return False
        if (path_is_inside(parent, holder) is True and path_is_inside(holder, parent) is True
                and os.path.normcase(os.path.basename(folder)).startswith(
                    os.path.normcase("agent-" + agent_id + "-"))):
            return root_ok or folder != path
        folder = parent


def other_checkout_hit(tool: str, tool_input: dict, cwd: str, session_id: str = "",
                       payload=None,
                       has_agent: bool = True) -> str:
    """Rule 0, other-checkout, for every session: the log detail when a write lands in a checkout
    of this clone other than the one holding `cwd`, else ''. A target in no checkout passes. A
    linked checkout in this session's own scratchpad passes for a call with no `agent_id` and a
    valid `session_id`; a caller that omits `has_agent` gets no exemption. An unreadable git
    state, or a cwd in no checkout, is unknown and passes. One git read per call that can write.
    A shell `cd`, `pushd` or `Set-Location` that moves into another checkout is refused too, unless
    `payload` marks the target as the caller's own home or red-run folder (a write strictly inside that red-run
    folder passes too, a shell `cp` may also name its root); a `cd` toward a folder
    under another `.git` entry spends the git read. A target in a separate clone of the same repo
    (the nearest `.git` above it names another common dir with the same origin, read by file) is
    refused the same way; the clone check spawns no git. Liftable by an owner override, unlike `worktree_home_hit`
    (decision an-agent-outside-its-home-tree-must-stop)."""
    where = _expanded(cwd, "") if cwd and os.name == "nt" else cwd
    moves = []
    if tool in WRITE_TOOLS:
        targets = write_targets(tool_input)
        writes = bool(targets)
    elif tool in SHELL_TOOLS:
        targets = None
        raw = str(tool_input.get("command", "") or "")
        command = strip_heredoc_bodies(raw)
        writes = bool(SHELL_WRITE_HINT.search(SHELL_QUIET_REDIRECT.sub(" ", command)))
        moves = _cd_targets(tool, raw, where) if where else []
        # A git verb spends the list only when stat and file reads show it can reach another clone.
        writes = writes or (_git_verb_called(command) and _git_verb_may_hit(command, where))
    else:
        return ""
    if moves:
        # A `cd` stays in its own checkout when the nearest `.git` above its target is the one above
        # the cwd. Stat alone tells, so only a move toward another `.git` entry spends the git read.
        own_root = _checkout_root_by_stat(os.path.realpath(where))
        moves = [m for m in moves
                 if own_root and _checkout_root_by_stat(m) not in ("", own_root) and not _cd_home_exempt(payload, where, m)]
    if not moves and not writes:
        return ""
    roots = clone_checkouts(where) if where else None
    own = _owning_checkout(where, roots) if roots else ""
    if not own:
        return ""

    tops, common, stranded = _clone_scope(roots, own)
    import tempfile   # lazy: only a call that can write or move reaches here
    temp = os.path.realpath(tempfile.gettempdir())
    clone_hit = {}   # target -> True when the hit was a separate clone, not a checkout of this one

    def elsewhere(target, at, verb=""):
        try:
            resolved = _resolved(target, at)
            owner = _owning_checkout(resolved, roots)
        except Exception:
            return False
        # An agent shares its session's id, and worktree-home judges no shell target, so only a
        # top-level call may write into the session's own scratchpad worktree.
        if not has_agent and under_session_scratchpad(resolved, session_id):
            return False
        # A separate clone of the same repo, or a write from a cwd stranded in one. The temp folder
        # holds scratchpads and throwaway clones, so it passes.
        clone_hit[target] = (
            path_is_inside(resolved, temp) is not True
            and ((stranded and bool(owner) and path_is_inside(resolved, os.path.join(owner, ".git")) is not True)
                 or (not owner and _separate_clone(resolved, tops, common))))
        if clone_hit[target]:
            return True
        # The primary's `.git` is the clone's common directory, shared by every checkout.
        return (bool(owner) and owner != own
                and path_is_inside(resolved, os.path.join(owner, ".git")) is not True
                and not _own_red_run(payload, roots[0], resolved, verb in RED_RUN_ROOT_VERBS))

    for move in moves:
        if elsewhere(move, where) and not _own_red_run(payload, roots[0], move):
            return (OTHER_CLONE_CD_DETAIL if clone_hit.get(move) else OTHER_CHECKOUT_CD_DETAIL) + move
    if targets is None:
        hit = _shell_write_hit(command, where, elsewhere, follow_cd=True, predicate_command=True) if writes else ""
        if not hit:
            # A git verb that changes files, run in a separate clone or from a stranded cwd. The one
            # reader of such verbs is session_home_git_hit; only the folder test differs.
            def in_clone(folder, _at):
                elsewhere(folder, folder)
                return clone_hit.get(folder, False)
            verb = session_home_git_hit(command, where, in_clone) if "git" in command else ""
            return OTHER_CLONE_GIT_DETAIL + verb if verb else ""
        return ("shell write into another clone: " if clone_hit.get(hit) else
                "shell write into another checkout: ") + hit
    for target in targets:
        if elsewhere(target, where):
            return (OTHER_CLONE_DETAIL if clone_hit.get(target) else "write target in another checkout: ") + target
    return ""


# ------------------------------------------------------------------ the session's own worktree
#
# Rule session-home. The harness removes a session's linked worktree and branch while the session
# runs on, and its shell falls back to the primary checkout. A write there lands on the clone's
# default branch, behind everything. The record `<primary>/.git/session-homes/<session_id>` holds the
# worktree path, so a later call can tell "never had a worktree" from "its worktree is gone". Only a
# call with no `agent_id` writes or clears it: an agent shares its session's id. The primary is found
# by path shape and a stat walk, never by git, so the rule adds no git spawn beyond what the call
# already spends. A git verb in the primary is read off the command text with `git_calls`.
SESSION_HOME_DIR = "session-homes"
# The git verbs that change the primary's files or branch. A `stash` that only reads (`list`, `show`)
# and a `clean` that deletes nothing (no force flag, as `clean -n`) are left out in session_home_write.
SESSION_HOME_GIT_VERBS = ("checkout", "switch", "pull", "merge", "commit", "rebase", "restore", "reset",
                          "stash", "cherry-pick", "revert", "am", "apply", "clean")
SESSION_HOME_REASON = (
    "Rule (session-home): this session's worktree is gone, so a write here would land in the primary "
    "checkout. "
    "Remedy: call the EnterWorktree tool first. Call it with a `name` and no `path`. It branches "
    "from origin's default branch. Then write inside that worktree."
)


def session_home_place(cwd: str):
    """Return (primary, lane) for a call's cwd, by path shape and a stat walk. `lane` is the
    `<primary>/.claude/worktrees/<name>` folder holding cwd, or '' when cwd sits in the primary's own
    files. (None, '') when neither shape fits: no checkout, a linked worktree elsewhere, or no
    `.git` directory at the primary."""
    if not cwd:
        return None, ""
    try:
        folder = os.path.realpath(cwd)
    except Exception:
        return None, ""
    while True:
        parent = os.path.dirname(folder)
        grand = os.path.dirname(parent)
        if (os.path.basename(parent) == "worktrees" and os.path.basename(grand) == ".claude"
                and os.path.isdir(os.path.join(os.path.dirname(grand), ".git"))):
            return os.path.dirname(grand), folder
        if os.path.isdir(os.path.join(folder, ".git")):
            return folder, ""
        if os.path.exists(os.path.join(folder, ".git")) or parent == folder:
            return None, ""
        folder = parent


def session_home_agent_tree(lane: str) -> bool:
    """True when LANE has an agent worktree's shape, `.claude/worktrees/agent-<agent_id>` (rule
    worktree-home). A top-level call there is the session inspecting an agent's tree, not its home."""
    name = os.path.basename(lane)
    return name.startswith("agent-") and bool(AGENT_ID.match(name[len("agent-"):]))


def session_home_record(payload, primary: str):
    """The record's path for this session, or '' when the call carries no valid session id."""
    sid = payload.get("session_id") if isinstance(payload, dict) else None
    if not isinstance(sid, str) or not SESSION_ID_RE.match(sid):
        return ""
    return os.path.join(primary, ".git", SESSION_HOME_DIR, sid)


def session_home_keep(payload, tool: str, cwd: str) -> None:
    """Write the session's record from a lane call, only when it is missing or different. The
    session's own ExitWorktree deletes it. An agent call does neither."""
    if not isinstance(payload, dict) or payload.get("agent_id") or tool == CREATE_SESSION_TOOL:
        # create_session reaches the guard for rules lane-effort-pin and agent-model-floor; it keeps no record
        return
    where = _expanded(cwd, "") if cwd and os.name == "nt" else cwd
    primary, lane = session_home_place(where)
    record = session_home_record(payload, primary) if primary else ""
    if not record:
        return
    try:
        try:
            with open(record, encoding="utf-8") as handle:
                held = handle.read().strip()
        except OSError:
            held = ""
        if tool == "ExitWorktree":
            # An exit ends a record whose worktree still stands, from any cwd. A record whose
            # worktree is gone stays, and the guard keeps judging.
            if held and os.path.isdir(held):
                os.remove(record)
            return
        if not lane or held == lane or session_home_agent_tree(lane):
            return
        import tempfile   # lazy: only a first or changed record reaches here
        folder = os.path.dirname(record)
        os.makedirs(folder, exist_ok=True)
        handle, temp = tempfile.mkstemp(dir=folder, prefix=".tmp-")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as out:
                out.write(lane)
            os.replace(temp, record)  # one step: a reader never sees a half-written path
        except BaseException:
            try:
                os.remove(temp)
            except OSError:
                pass
            raise
    except Exception:
        pass  # an unwritable record means no refusal later, never a failed call


GIT_AFTER_CD_REASON = (
    "Rule (git-after-cd, decision git-after-cd-joins-with-and): a git write that follows a cd, "
    "joined to it by `;`, a newline or `||`, runs in the working folder when the cd fails, "
    "because the shell stays where it was. "
    "Remedy: join the cd to the write with `&&`, so a failed cd stops the chain, or leave out the cd "
    "and name the folder with `-C` and its full path."
)


GIT_PUSH_AFTER_CHECK_REASON = (
    "Rule (git-after-cd, decision git-after-cd-joins-with-and): a git push that follows another command "
    "joined to it by `;` runs even when that command fails, so a failed check does not stop it. "
    "Remedy: join the commands with `&&`, so the push runs only when the command before it succeeds."
)


# The `branch` flags that move, rename or delete a ref (a force, a move, a delete).
GIT_BRANCH_WRITE_FLAGS = BRANCH_DELETE_FLAGS | {"-f", "--force", "-m", "-M", "--move"}


# The writes rule git-after-cd reads beyond SESSION_HOME_GIT_VERBS. They stay out of that list because rule
# session-home pins `worktree add` as allowed (the way a session makes its new home), and it does not
# judge the other three. After a failed cd each of these four runs in the folder the shell stayed in.
GIT_AFTER_CD_EXTRA_VERBS = ("add", "tag", "config", "worktree")
# `tag` flags that list or verify tags, `config` flags that only read or only write, and the `config` flags
# that take a value word of their own (the file, the type), which is not a key.
GIT_TAG_READ_FLAGS = {"-l", "--list", "-v", "--verify", "--contains", "--no-contains", "--points-at",
                      "--merged", "--no-merged", "--sort", "--format", "--column", "--no-column"}
GIT_CONFIG_READ_FLAGS = {"--get", "--get-all", "--get-regexp", "--get-urlmatch", "--get-color",
                         "--get-colorbool", "-l", "--list"}
GIT_CONFIG_WRITE_FLAGS = {"--add", "--replace-all", "--unset", "--unset-all", "-e", "--edit",
                          "--rename-section", "--remove-section"}
GIT_CONFIG_VALUE_FLAGS = {"-f", "--file", "--blob", "--type", "--default", "--comment"}


def git_config_writes(args) -> bool:
    """True when `git config` sets, adds, unsets or edits a value. A `--get`, `--list` or a key with no
    value (`git config user.name`) reads. The `get` and `list` subcommands read; `set`, `unset` and
    `edit` write."""
    words, flags, skip = [], set(), False
    for arg in args:
        if skip:
            skip = False
        elif arg.startswith("-"):
            flags.add(arg.split("=", 1)[0])
            skip = arg in GIT_CONFIG_VALUE_FLAGS
        else:
            words.append(arg)
    if flags & GIT_CONFIG_WRITE_FLAGS:
        return True
    if flags & GIT_CONFIG_READ_FLAGS or words[:1] in (["get"], ["list"]):
        return False
    return len(words) >= 2 or words[:1] in (["set"], ["unset"], ["edit"], ["rename-section"], ["remove-section"])


def session_home_write(verb: str, args) -> bool:
    """True when a call of a verb of SESSION_HOME_GIT_VERBS changes the files or the branch: a
    `stash list`, a `stash show` and a `clean` that deletes nothing only read."""
    if verb == "stash":
        return args[:1] not in (["list"], ["show"])
    if verb == "clean":
        return clean_deletes_files(args)
    return True


def git_after_cd_extra_write(verb: str, args) -> bool:
    """True when a call of a verb of GIT_AFTER_CD_EXTRA_VERBS changes the index, a ref, the config or the
    worktree list: an `add` that is no dry run, a `tag` that names or deletes a tag, a `config` that
    writes a value (`git_config_writes`) and `worktree add`."""
    if verb == "add":
        return not {"-n", "--dry-run"} & set(args)
    if verb == "tag":
        flags = {arg.split("=", 1)[0] for arg in args if arg.startswith("-")}
        listing = bool(flags & GIT_TAG_READ_FLAGS) or any(LISTING.fullmatch(flag) for flag in flags)
        return bool(args) and not listing
    if verb == "config":
        return git_config_writes(args)
    return args[:1] == ["add"]


def git_write_verb(verb: str, args) -> bool:
    """True when a git call changes a ref, the index, the config or the files: the verbs of SESSION_HOME_GIT_VERBS
    and of GIT_AFTER_CD_EXTRA_VERBS, `push`, `update-ref`, the file verbs of GIT_FILE_VERBS, a `fetch` that writes a branch
    (`fetch_moves_branch`), and `branch` with a force, move or delete flag. A call whose argv names a
    read (`read_verb`: a dry run, help), a `stash list`, a `stash show` and a `clean` that deletes
    nothing only read."""
    if read_verb(verb, args):
        return False
    if verb == "branch":
        return any(arg in GIT_BRANCH_WRITE_FLAGS for arg in args)
    if verb == "fetch":
        return fetch_moves_branch(args)
    if verb in SESSION_HOME_GIT_VERBS:
        return session_home_write(verb, args)
    if verb in GIT_AFTER_CD_EXTRA_VERBS:
        return git_after_cd_extra_write(verb, args)
    return verb in ("push", "update-ref") or verb in GIT_FILE_VERBS


def git_after_cd_hit(command: str, cwd: str) -> str:
    """The verb of a git write in COMMAND that runs in the folder the shell stayed in after a cd
    into a folder that is not there (decision git-after-cd-joins-with-and), else ''. One `cd_walk`
    that trusts a failed cd to leave the shell in place says whether the segment runs in a folder
    the shell stayed in (`stranded`). A `&&` chain skips the write when the cd fails, a `)` ends a
    subshell's cd, and a cd to a full path that lands moves the shell out of the stranded folder.
    `git -C <full path>` names its own folder and passes; a `-C` that holds a variable is unknown and
    passes; a relative `-C` is joined to the stranded folder and is refused."""
    ends = []
    segments = split_segments(command, ends)
    for number, segment in enumerate(segments):
        # a `)` or `}` that closes a group sits on the last word, so `push)` is the verb `push`
        calls = [(verb.rstrip(")}"), args) for verb, args in git_calls(segment)]
        verbs = [verb for verb, args in calls if git_write_verb(verb, args)]
        if not verbs:
            continue
        if not cd_walk(segments, number, cwd, ends, failed_cd_stays=True).stranded:
            continue
        tokens = segment_tokens(segment)
        if tokens is None:
            continue   # a segment cut inside a quote, as an interpreter's heredoc body is: its `-C` is unread
        named = _segment_git_c_target(tokens)
        if named is not None and (_unexpanded(named) or shell_abs(named, None)):
            continue
        return verbs[0]
    return ""


# The words that start a compound body (`if X; then git push`): the body's own test guards the push, so
# the `;` before it is no join to a check.
GIT_PUSH_BODY_WORDS = ("then", "do", "else", "elif")
# The words before a segment's command: a body opener, a test opener and `!`.
GIT_PUSH_LEADING_WORDS = GIT_PUSH_BODY_WORDS + ("if", "while", "until", "!", "time")
# Words that only open or close a compound, and commands whose failure no check can hide: `exit`, `set`,
# `true` and `:`. A cd is inert too: `git_after_cd_hit` has already refused each cd that strands the shell.
GIT_PUSH_INERT_WORDS = ("for", "select", "case", "in", "esac", "fi", "done", "{", "}", "(", ")",
                        "exit", "set", "true", ":")
# Commands that only print or set a variable: inert when no word of theirs runs a substitution.
GIT_PUSH_PLAIN_WORDS = ("export", "echo")


def _push_segment_inert(segment: str):
    """True when SEGMENT holds no command that can fail a check: empty, a compound word, a cd, `exit`,
    `set`, `true`, `:`, or an `export` or `echo` whose words run no substitution. None when a quote is cut
    in it (unknown). A group opener at the head is walked into, so `{ pytest -q`, `( pytest -q` and
    `(pytest -q)` are commands and `(cd X; true)` is not."""
    tokens = segment_tokens(segment)
    if tokens is None:
        return None
    words = list(tokens)
    while words and (words[0] in GIT_PUSH_LEADING_WORDS or not words[0].strip("({")):
        words.pop(0)
    if not words or words[0].startswith("}"):
        return True
    head = re.split(r"[<>&]", words[0].lstrip("({"))[0].rstrip(")}")   # `done>>/dev/null` closes a loop
    if head in GIT_PUSH_PLAIN_WORDS:
        return not any("`" in word or "$(" in word or "<(" in word or ">(" in word for word in words)
    return not head or head in CD_WORDS or head in GIT_PUSH_INERT_WORDS


def git_push_after_check_hit(command: str) -> str:
    """'push' when COMMAND holds a `git push` that runs after a `;`- or newline-joined command whose failure
    it cannot see, else '' (decision git-after-cd-joins-with-and). It reads the segments and ends that
    `git_after_cd_hit` reads, less the empty line after a trailing `&&`, `||` or `|`, which joins the two
    lines by that operator. From the push it walks back over its `&&` chain to the chain's start. Before
    that start, a `;` or newline joins the command before it. A cd, `exit`, `set` or `true` (or a group
    of them) is skipped and the walk goes on over that command's own `&&` chain, which must be inert too.
    So is a lone command whose failure ends the shell under `set -e` (`_push_stops_under_errexit`). A group
    opener is walked into, so a check inside `{ }` or `( )` refuses. A `|| exit`, the tail of
    `|| { ...; exit N; }` or `if ! X; then exit N; fi` (`_push_exit_tails`), and the test of the compound that
    holds the push (`_push_body_head`) each clear only the commands they cover: the walk goes on back past
    them, so a `;`-joined check further back still refuses. An `exit` inside a `( )` group leaves only that
    group, so neither it nor an exit tail inside one clears anything. Any other command refuses, a subshell
    included. The walk ends and passes at the start of the command line.
    A `||` or `|` before the start of the push's chain is no `;` join and passes. A dry run
    (`git_write_verb`) and an unreadable segment pass."""
    ends = []
    segments = split_segments(command, ends)
    if len(ends) < len(segments):
        return ""
    kept = [at for at, segment in enumerate(segments) if segment_tokens(segment) != []]
    segments, ends = [segments[at] for at in kept], [ends[at] for at in kept]
    tails = _push_exit_tails(segments, ends)
    for number, segment in enumerate(segments):
        calls = [(verb.rstrip(")}"), args) for verb, args in git_calls(segment)]
        if not any(verb == "push" and git_write_verb(verb, args) for verb, args in calls):
            continue
        if not segment_tokens(segment):
            continue
        position, first = number, True
        while True:
            start = position
            while start > 0 and ends[start - 1] == "&&":
                start -= 1
            if not first and not all(_push_segment_inert(part) for part in segments[start:position + 1]):
                if start < position or not _push_stops_under_errexit(segments, ends, start):
                    return "push"
            if _opens_push_body(segments, start, number):
                head = _push_body_head(segments, start)
                if head is None:
                    break
                position, first = head, True
                continue
            if start == 0:
                break
            if ends[start - 1] not in (";", "\n"):
                if first:
                    break
                return "push"
            before = segment_tokens(segments[start - 1])
            if before is None:
                break
            covered = None
            if (before[:1] == ["exit"] and start > 1 and ends[start - 2] == "||"
                    and not subshell_depth(segments, start - 1)):
                covered = start - 2
            elif start - 1 in tails and not subshell_depth(segments, start - 1):
                covered = tails[start - 1]
            if covered is not None:
                while covered > 0 and ends[covered - 1] in ("&&", "||", "|"):
                    covered -= 1   # the exit guards the whole `A || B` or `A | B` list, and no check before it
                position, first = covered, True
                continue
            position, first = start - 1, False
    return ""


def _push_exit_tails(segments, ends):
    """The segments that close an exit on a check's failure, past a bare `|| exit`: the `}` of
    `X || { ...; exit N; }` and the `fi` of `if ! X; then exit N; fi` (`_exits_on_failure`). The shell
    stops when X fails, so a push after the tail runs only when X passed. Gives each tail's index with the
    index of the command X it covers: the tail clears X alone, not what stands before it."""
    tails = {}
    for at, segment in enumerate(segments[:-1]):
        tokens = segment_tokens(segment) or []
        grouped = ends[at] == "||" and (segment_tokens(segments[at + 1]) or [])[:1] == ["{"]
        negated_if = (ends[at] in (";", "\n") and tokens[:2] == ["if", "!"]
                      and (at == 0 or ends[at - 1] in (";", "\n")))
        if not (grouped or negated_if) or not _exits_on_failure(segments, ends, at):
            continue
        depth = 0
        for close in range(at + grouped, len(segments)):
            depth += _compound_delta(segments[close], wide=True)
            if depth <= 0:
                tails[close] = at
                break
    return tails


def _opens_push_body(segments, start: int, number: int) -> bool:
    """True when `segments[start]` opens the compound body (`then`, `do`, `else`, `elif`) that holds the push
    at `segments[number]`: no closer between them ends that body. The body's own test guards the push."""
    tokens = segment_tokens(segments[start])
    if not tokens or tokens[0] not in GIT_PUSH_BODY_WORDS:
        return False
    return sum(_compound_delta(part, wide=True) for part in segments[start:number]) >= 0


def _push_body_head(segments, start: int):
    """For the body opener at `segments[start]` (`then`, `do`, `else`, `elif`): the index of the head of its
    compound (`if`, `for`, `while`, `until`), found by counting the compounds still open before it, else None
    when the head cannot be read. A `{` or `(` that opens the group the compound stands in is read past, so
    `{ for ...; do push; done; }` and `( if ...; then push; fi )` reach the check before the group. The compound's test guards only the body, not what stands before the
    compound, so the walk goes on back past the head to any earlier `;`-joined check."""
    opener = segment_tokens(segments[start])
    if start == 0 or not opener or opener[0] not in GIT_PUSH_BODY_WORDS:
        return None
    open_depth = 0
    for head in range(start - 1, -1, -1):
        open_depth += _compound_delta(re.sub(r"^[\s(]+", "", segments[head]), wide=True)   # `( if x` opens the `if`
        if open_depth >= 1:
            words = list(segment_tokens(segments[head]) or [])
            while words and (words[0] in GIT_PUSH_BODY_WORDS or not words[0].strip("({")):
                words.pop(0)   # a body word, or a `{` or `(` group opener, stands before the compound's head
            if words:
                words[0] = words[0].lstrip("({")   # `(if`
            return head if words[:1] in (["if"], ["for"], ["while"], ["until"]) else None
    return None


def _push_stops_under_errexit(segments, ends, at: int) -> bool:
    """True when a failure of the lone command `segments[at]` ends the shell under `set -e`: no `!`, compound
    word or `&` on it, and the cd walk reads `errexit_stops` there (a `set -e` sure to run, at the top level)."""
    segment = segments[at]
    tokens = segment_tokens(segment)
    if not tokens or tokens[0] == "!" or _compound_delta(segment, wide=True) or segment.rstrip().endswith("&"):
        return False
    return cd_walk(segments, at, "", ends).errexit_stops


def session_home_git_hit(command: str, where: str, in_primary) -> str:
    """The verb of a git call in COMMAND that changes the primary's files or branch and runs in the
    primary checkout, else ''. A leading `cd` and `git -C <path>` name the folder it runs in; a folder
    that holds a variable is unknown and passes."""
    ends = []
    segments = split_segments(command, ends)
    for number, segment in enumerate(segments):
        verbs = [(verb, args) for verb, args in git_calls(segment) if verb in SESSION_HOME_GIT_VERBS]
        if not verbs:
            continue
        folder = dir_before_segment(segments, number, where, ends)
        tokens = segment_tokens(segment)
        named = _segment_git_c_target(tokens) if tokens else None
        if named is not None:
            folder = None if _unexpanded(named) else shell_abs(named, folder)
        if not folder:
            continue
        for verb, args in verbs:
            if session_home_write(verb, args) and in_primary(folder, folder):
                return verb
    return ""


def session_home_hit(payload, tool: str, tool_input: dict, cwd: str) -> str:
    """Rule session-home: the log detail when a session whose recorded worktree is gone writes into
    the primary checkout, else ''. Only a call with no `agent_id` and a cwd in the primary's own files
    is judged. A missing, empty or unreadable record is unknown and passes. The clone's `.git`,
    `.claude/worktrees/`, and a target outside the clone pass. Liftable by an owner override."""
    if not isinstance(payload, dict) or payload.get("agent_id"):
        return ""
    if tool in WRITE_TOOLS:
        targets = write_targets(tool_input)
    elif tool in SHELL_TOOLS:
        targets = None
        command = strip_heredoc_bodies(str(tool_input.get("command", "") or ""))
        writes = bool(SHELL_WRITE_HINT.search(SHELL_QUIET_REDIRECT.sub(" ", command)))
        if not writes and "git" not in command:
            return ""
    else:
        return ""
    where = _expanded(cwd, "") if cwd and os.name == "nt" else cwd
    primary, lane = session_home_place(where)
    record = session_home_record(payload, primary) if primary and not lane else ""
    if not record:
        return ""
    try:
        with open(record, encoding="utf-8") as handle:
            home = handle.read().strip()
    except OSError:
        return ""
    if not home or os.path.isdir(home):
        return ""
    lanes = os.path.join(primary, ".claude", "worktrees")
    clone_git = os.path.join(primary, ".git")

    def in_primary(target, at):
        try:
            resolved = _resolved(target, at)
        except Exception:
            return False
        return (path_is_inside(resolved, primary) is True
                and path_is_inside(resolved, clone_git) is not True
                and (path_is_inside(resolved, lanes) is not True
                     or path_is_inside(resolved, home) is True))  # the gone home path is the primary's too

    if targets is None:
        verb = session_home_git_hit(command, where, in_primary)
        if verb:
            return "git " + verb + " in the primary checkout"
        hit = _shell_write_hit(command, where, in_primary, follow_cd=True) if writes else ""
        return "shell write into the primary checkout: " + hit if hit else ""
    for target in targets:
        if in_primary(target, where):
            return "write target in the primary checkout: " + target
    return ""


def never_lifted(payload, tool: str, tool_input: dict, cwd: str) -> bool:
    """True when the call holds an act no owner override lifts (decision owner-override): a
    git location variable, a frozen path, a kill of pid 0, 1 or -1, a role or model guard, or a
    worktree-home refusal. refuse() asks this before it spends an override, because a lifted act ends the
    check."""
    # role_model_check's above-row refusal is liftable (item 127 pick a); only its no-model refusal is never lifted.
    if (floor_hit(tool, tool_input) or step_up_hit(tool, tool_input)
            or role_model_check(tool, tool_input)[1].startswith(ROLE_NO_MODEL_MATCH)
            or worktree_home_hit(payload, tool, tool_input, cwd)):
        return True
    if tool in SHELL_TOOLS:
        raw = tool_input.get("command", "") or ""
        stripped = strip_heredoc_bodies(raw)
        return bool(git_env_command_hit(raw, stripped) or frozen_shell_hit(stripped, cwd)
                    or any(t and kills_group_pid(t) for t in map(segment_tokens, split_segments(stripped)))
                    or (_shell_write_hit(stripped, cwd, is_settings_file) and cap_change(raw))
                    or (agent_role(payload) == BUILDER_ROLE and builder_shell_test_hit(raw, stripped, cwd)))
    role = agent_role(payload)
    for target in write_targets(tool_input) if tool in WRITE_TOOLS else ():
        if (is_frozen(target, cwd) or (role and role_write_hit(role, tool_input, target, cwd, session_id_of(payload)))
                or (is_settings_file(target, cwd) and cap_change_parts(write_content_parts(tool_input)))):
            return True
    return False


def judge(payload) -> None:
    if payload.get("hook_event_name") == "SubagentStop":
        judge_stop(payload)
        return
    tool = payload.get("tool_name", "") or ""
    tool_input = payload.get("tool_input", {}) or {}
    if not isinstance(tool_input, dict):
        return
    # Read and Grep: no rule judges them, so the guard leaves at once and spends no git call.
    # worktree-home never judged them, the settings deny list owns the env files (Read and Edit of
    # `.env*` at any depth, `.env.example` carved out), and a frozen path stays readable.
    if tool in READ_ONLY_TOOLS:
        return
    cwd = payload.get("cwd", "") or os.getcwd() or ""
    if not isinstance(cwd, str):
        cwd = ""
    guard_core.set_override_veto(lambda: never_lifted(payload, tool, tool_input, cwd))
    session_home_keep(payload, tool, cwd)  # rule session-home's record, kept before any refusal can end the call
    # 0, handoff-unread. After compaction, no call the guard judges runs from the main session until it reads its handoff.
    # Not in never_lifted: the owner may mean the call. A failed import allows.
    try:
        from reread_check import unread_handoff
    except Exception:
        unread_handoff = None
    unread = unread_handoff(payload) if unread_handoff else ""
    if unread:
        refuse(tool, "deny", "handoff-unread", HANDOFF_UNREAD_REASON % unread, unread)
    # 0. Each agent stays inside its own worktree.
    home_hit = worktree_home_hit(payload, tool, tool_input, cwd)
    if home_hit:
        refuse(tool, "deny", "worktree-home", WORKTREE_HOME_REASON, home_hit)
    # 0, other-checkout. Every session writes only inside its own checkout of the clone. An override lifts it:
    # a rule id of its own, because the owner ruled that no override lifts worktree-home.
    other_hit = other_checkout_hit(tool, tool_input, cwd, session_id_of(payload),
                                   payload,
                                   bool(payload.get("agent_id")))
    if other_hit:
        refuse(tool, "deny", "other-checkout",
               OTHER_CLONE_CD_REASON if other_hit.startswith(OTHER_CLONE_CD_DETAIL)
               else OTHER_CLONE_REASON if "into another clone: " in other_hit[:40]
               else OTHER_CHECKOUT_CD_REASON if other_hit.startswith(OTHER_CHECKOUT_CD_DETAIL)
               else OTHER_CHECKOUT_REASON, other_hit)
    # 0, session-home. A session whose own worktree is gone writes nowhere in the primary checkout. An
    # override lifts it, and it is not in never_lifted: the owner may mean the write.
    session_hit = session_home_hit(payload, tool, tool_input, cwd)
    if session_hit:
        refuse(tool, "deny", "session-home", SESSION_HOME_REASON, session_hit)

    # 9. The agent model floor. A spawn that names a Haiku model is refused. The reason names no
    # model; the log holds what the call asked for.
    floor_model = floor_hit(tool, tool_input)
    if floor_model:
        refuse(tool, "deny", "agent-model-floor", MODEL_FLOOR_REASON, floor_model)

    # 9b. Step-up: a reviewer's second round on Sonnet, a builder's third on Opus. A reviewer's third round passes here on
    # Sonnet or Opus; the Opus ceiling (9d, opus_spawn_hit) then refuses Opus unless an override lifts it.
    step_up = step_up_hit(tool, tool_input)
    if step_up:
        refuse(tool, "deny", "roles-third-round-steps-up", step_up, str(tool_input.get("model")))

    # 9b2. The lane effort pin: a lane session starts with the effort command as its whole prompt. An
    # override lifts it: it is not in never_lifted, because the owner may mean another start prompt.
    lane_prompt = lane_effort_hit(tool, tool_input)
    if lane_prompt:
        refuse(tool, "deny", "lane-effort-pin", LANE_EFFORT_REASON, lane_prompt)

    # 9b2b. The lane repo tag: a lane session carries the full `cs-repo` tag of the checkout that starts it.
    # After the effort pin, so a call that breaks both reads the pin first. An override lifts it.
    lane_tags, lane_repo = lane_repo_tag_hit(tool, tool_input, cwd)
    if lane_tags:
        refuse(tool, "deny", "lane-repo-tag", LANE_REPO_TAG_REASON % (REPO_TAG + (lane_repo or "<owner>/<name>")), lane_tags)

    # 9b3. The role model row: a spawn above its role's row, or with no model where nothing else sets one, is refused.
    # The override lifts the above-row refusal and never the no-model one (never_lifted).
    # An unread table or agent folder passes and logs one line. Opus is judged at 9d.
    role_reason, role_matched, role_unread = role_model_check(tool, tool_input)
    if role_unread:
        record(tool, "noted", "agent-role-model-unread", role_matched)
    if role_reason:
        refuse(tool, "deny", "agent-role-model", role_reason, role_matched)

    # 9c. The machine-load brake: one read on a start call, and one on an agent's or a lane session's shell or file write.
    # It runs before the Opus refusal, because a lifted refusal exits refuse() at once and would skip this deny.
    load_reason, load_matched = load_hit(tool, tool_input)
    if not load_reason:
        load_reason, load_matched = running_agent_hit(payload, tool)
    if not load_reason:
        load_reason, load_matched = lane_session_hit(payload, tool)
    if load_reason:
        refuse(tool, "deny", "load-brake", load_reason, load_matched)

    # 9d. The Opus ceiling: a spawn on Opus with no standing grant is refused (decision agent-model-cap).
    # An override, an Opus pass for the spawn's role or a step grant lifts it. A spawn with no role runs general-purpose.
    opus_model, opus_role, opus_unread = opus_spawn_hit(tool, tool_input)
    if opus_model:
        refuse(tool, "deny", "agent-model-cap",
               (OPUS_BUILDER_REASON if opus_role == "builder" else OPUS_SPAWN_REASON)
               + (" The scan could not read this brief, so it read no marker: " + BRIEF_LITERAL_REMEDY + "."
                  if opus_unread else ""),
               opus_model,
               spawn_role=opus_role or "general-purpose")

    # A merge through the MCP tool is judged by the same merge guard as `gh pr merge`.
    if tool in MERGE_TOOLS:
        owner, name, number = (tool_input.get(k) for k in ("owner", "repo", "pullNumber"))
        repo = owner + "/" + name if isinstance(owner, str) and isinstance(name, str) else ""
        verdict, detail = merge_check("" if number is None else str(number), repo, cwd)
        if verdict != "green":
            refuse(tool, "deny", "merge-checks", merge_check_reason(verdict, detail),
                   "merge tool " + verdict)

    # The MCP create tool carries its own `draft` field.
    if tool == "mcp__github__create_pull_request" and tool_input.get("draft") is not True:
        refuse(tool, "deny", "draft-pr", DRAFT_PR_REASON, "create_pull_request without draft")

    # A trust-card call from a session whose own record is not proved untagged (rule trust-card-in-build).
    trust_transcript = payload.get("transcript_path")
    matched = trust_card_hit(tool, trust_transcript if isinstance(trust_transcript, str) else "")
    if matched:
        refuse(tool, "deny", "trust-card-in-build", TRUST_REASON, matched)

    # An archive of a lane whose records pull request is still open, or whose record is unread (rule lane-closes-after-records).
    archived = archive_hit(tool, tool_input, trust_transcript if isinstance(trust_transcript, str) else "")
    if archived:
        refuse(tool, "deny", "lane-closes-after-records", archived[1], archived[0])

    # A lane brief for a topic the target lane does not hold (rule lane-one-topic).
    briefed = brief_hit(tool, tool_input, trust_transcript if isinstance(trust_transcript, str) else "")
    if briefed:
        refuse(tool, "deny", "lane-one-topic", briefed[1], briefed[0])

    if tool == "Skill":
        matched = impeccable_skill_hit(tool_input)
        if matched:
            refuse(tool, "deny", "impeccable-review-only", IMPECCABLE_REASON, matched)
        return

    if tool == DATA_TOOL:
        (rule, matched), item_writes = data_tool_judge(tool_input, cwd)
        if rule:
            import question_form
        # One literal refuse() per rule: lint/rule_audit.py reads only string-literal rule ids.
        if rule == "port-question":
            refuse(tool, "deny", "port-question", question_form.PAGE_REASONS["port-question"], matched)
        if rule == "uniform-pick":
            refuse(tool, "deny", "uniform-pick", question_form.PAGE_REASONS["uniform-pick"], matched)
        if rule == "press-link":
            refuse(tool, "deny", "press-link", question_form.PAGE_REASONS["press-link"], matched)
        if rule == "command-in-item":
            refuse(tool, "deny", "command-in-item", question_form.PAGE_REASONS["command-in-item"], matched)
        if rule == "gh-login-switch":
            refuse(tool, "deny", "gh-login-switch", question_form.PAGE_REASONS["gh-login-switch"], matched)
        if rule == "task-names-check":
            refuse(tool, "deny", "task-names-check", question_form.PAGE_REASONS["task-names-check"], matched)
        if rule == "owner-judge":
            refuse(tool, "deny", "owner-judge", question_form.PAGE_REASONS["owner-judge"], matched)
        if rule == "option-letter-keys":
            refuse(tool, "deny", "option-letter-keys", question_form.PAGE_REASONS["option-letter-keys"], matched)
        if rule == "rework-off-page":
            refuse(tool, "deny", "rework-off-page", question_form.PAGE_REASONS["rework-off-page"], matched)
        if rule == "question-form":
            refuse(tool, "deny", "question-form", question_form.PAGE_REASONS["question-form"], matched)
        if rule == "question-departs":
            refuse(tool, "deny", "question-departs", question_form.PAGE_REASONS["question-departs"], matched)
        if rule == "item-field-rendered":
            refuse(tool, "deny", "item-field-rendered", question_form.PAGE_REASONS["item-field-rendered"], matched)
        if item_writes:
            unhomed = mockup_home_hit(item_writes, tool_input, cwd)
            if unhomed:
                refuse(tool, "deny", "mockup-home", unhomed[0], unhomed[1])
            unseen = page_design_hit(item_writes, tool_input, cwd)
            if unseen:
                refuse(tool, "deny", "page-item-design", unseen[0], unseen[1])
        return

    if tool == PAGE_TOOL:
        behind = page_stale_hit(tool_input, cwd)
        if behind:
            refuse(tool, "deny", "page-stale", behind[0], behind[1])
        return

    if tool in SHELL_TOOLS:
        command = tool_input.get("command", "") or ""
        if isinstance(command, str) and command.strip():
            transcript = payload.get("transcript_path") if isinstance(payload, dict) else ""
            judge_shell(tool, command, cwd, session_id_of(payload), agent_role(payload),
                        transcript if isinstance(transcript, str) else "",
                        bool(payload.get("agent_id") or payload.get("agent_type")),
                        tool_input.get("run_in_background") is True,
                        tool_input.get("description") or "")
            segments = split_segments(strip_heredoc_bodies(command))
            matched = next((hit for seg in segments if (hit := sim_bypass_hit(seg))), "")
            if matched:
                refuse(tool, "deny", "simulator-boot-bypass", SIM_BYPASS_REASON, matched)
            names, remedies = [], {}
            for seg in segments:
                for n, remedy in _sim_boots(seg):
                    names.append(n)
                    remedies.setdefault(n[0], remedy)
            if names:
                sim_boot_refusal(tool, names, remedies)
        return
    if tool == SIM_MCP:
        # `udid` is an alias of `device`: judge each non-empty name, so one field hides no other.
        names = list(dict.fromkeys(v for v in map(tool_input.get, ("device", "udid"))
                                   if isinstance(v, str) and v))
        if tool_input.get("action") == "launch" and names:
            sid = payload.get("session_id") if isinstance(payload, dict) else ""
            sim_boot_refusal(tool, names, None, sid if isinstance(sid, str) else "")
        return

    if tool not in WRITE_TOOLS:
        return

    # Every non-empty string path field the call carries is judged, so a decoy in one field hides
    # no refused path, and an ask on one field masks no refusal on another: every refusal (0b, 5, 7)
    # runs over all fields, then the 7b notes, then the 8 asks (docs/decisions/builders-cannot-edit-tests.md,
    # "Judge the result").
    targets = write_targets(tool_input)
    for target in targets:
        # 0b. The early warning for a builder, test-author, record-writer or designer write (see BUILDER_ROLE). A read is allowed.
        role = agent_role(payload)
        if role and tool in WRITE_TOOLS:
            matched = role_write_hit(role, tool_input, target, cwd, session_id_of(payload))
            if matched:
                code, why = {AUTHOR_ROLE: ("test-author-scope", AUTHOR_SCOPE_REASON),
                             WRITER_ROLE: ("record-writer-scope", WRITER_SCOPE_REASON),
                             DESIGNER_ROLE: ("designer-scope", DESIGNER_SCOPE_REASON)}.get(
                    role, ("builder-test-edit", BUILDER_TEST_REASON))
                refuse(tool, "deny", code, why, matched)

        # 5. The environment file. Every writing tool is refused. A read is not judged here: no hook
        # runs for Read, so settings.json denies Read and Edit of `.env*` at any depth, with `!`
        # carve-outs for `.env.example`. That deny list is the one layer that holds when the guard
        # cannot run. The reason names no file, and the log holds the path the tool asked for.
        if is_env(target):
            refuse(tool, "deny", "env-file", ENV_TOOL_REASON + ". " + ENV_ADVICE, target)

        # 7. A frozen path. Only a writing tool reaches here, so a frozen path stays readable.
        if is_frozen(target, cwd):
            refuse(tool, "deny", "frozen-path", FROZEN_REASON, target)
    for target in targets:
        # 7b. A project config edit: allowed (Decision 7), and noted in the log only.
        if is_project_config(target, cwd):
            record(tool, "noted", "config-edit", target)
    for target in targets:
        # 8. The agent model cap. Rule 7 already refused the config directory's own settings, so
        # only a project-scoped or clone-scoped settings file reaches here. The content read is what
        # the tool would WRITE, so a file that carries the variable name anywhere in that content
        # asks, a permission string or a comment line included. That is an over-ask and it stays:
        # the alternative is a value test that a crafted spelling walks past. A write that does not
        # carry the name never fires, and no other file than a settings file reaches this rule.
        if is_settings_file(target, cwd):
            change = cap_change_parts(write_content_parts(tool_input))
            if change:
                refuse(tool, "ask", "agent-model-cap", cap_ask_reason(change, target),
                       log_path_and_text(target, change))


def write_targets(tool_input: dict) -> list:
    """Every non-empty string path field of a write call, in a fixed order."""
    return [v for k in ("file_path", "path", "notebook_path")
            if isinstance((v := tool_input.get(k)), str) and v]


def main() -> None:
    _force_utf8_streams()
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # fail open on unreadable input
    if not isinstance(payload, dict):
        sys.exit(0)  # fail open on a payload that is not an object
    try:
        guard_core.set_log_session(payload.get("session_id"))  # the last column of every log line
    except Exception:
        pass  # a guard_core without the setter still judges: its line has no session cell (unknown session)
    try:
        guard_core.set_override_context(payload.get("session_id"), payload.get("agent_id"), payload.get("cwd"))
    except Exception:
        pass  # a guard_core without the setter has no override: every refusal stands
    try:
        judge(payload)
    except SystemExit:
        raise
    except Exception as exc:
        # Fail open, but never silently: a crash that hides a rule must show in the log.
        record(str(payload.get("tool_name", "")), "crash", "guard-crash",
               cap_safe(type(exc).__name__ + ": " + str(exc), 200))
        sys.exit(0)  # fail open on a guard defect
    sys.exit(0)


if __name__ == "__main__":
    main()
