#!/usr/bin/env python3
"""The global PreToolUse guard.

Modes:
- PreToolUse: Before each matched tool call, runs the owner's global rules in a fixed
  order and refuses or asks on the first match. Bad input allows the call.
- SubagentStop: When a builder, test-author or record-writer stops, judges its whole diff
  against its role, for example a builder that changed a test path. Logs an offence for
  the reviewer and never refuses the stop.

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

Shell tools (Bash, PowerShell), in judge_shell order:
  builder-diff, author-diff, writer-diff, designer-diff, role-diff-*
                       noted. A builder, test-author or record-writer `git commit` or `git push`.
                       The diff it would send is logged for the reviewer. Never refuses.
                       SubagentStop (`judge_stop`) logs the same names for the whole diff, and
                       also role-diff-main-checkout, role-diff-unresolved and
                       role-diff-unread.
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
  cite-by-id           deny. A commit message or PR body that cites a record by its path.
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
  ln-over-directory    deny. See the comment at rule 3b in judge_shell.
  destructive-delete   deny. A recursive delete, forced or not, at a root, a home, a glob, `.`,
                       the working folder or a folder above it, in either shell.
                       (rm-path-wrapper)
  force-push           deny or ask. A lease with --force-if-includes passes. --force or a `+`
                       refspec refuses. A push that reaches the default branch asks.
                       (stale-safe-force-push)
  env-file             deny. Any read or write of an environment file.
  merge-checks         deny. A merge while the head has a check pending or red, while another
                       ready PR on the base runs CI, or when the read could not run. `--auto` too.
  draft-pr             deny. A `gh pr create` without `--draft`. (draft-until-reviewed)
  records-page         deny. A `git commit` whose docs/records.md differs from the base's page.
                       (records-index-at-merge)
  frozen-path          deny. A write to the settings, hooks or global CLAUDE.md under
                       `${CLAUDE_CONFIG_DIR:-$HOME/.claude}`. (frozen-path-resolves-shell-vars)
  config-edit          noted. A write to a project's own settings or hooks. See below.
  agent-model-cap   ask. A write to a settings file that sets or changes
                       `CLAUDE_CODE_SUBAGENT_MODEL`, `CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL` or the `_FORCE` form.
                       (agent-model-cap)
                       Also an Agent or Task spawn that sets model opus, unless Plan, Explore,
                       designer, design-reviewer or a builder's third-round marker covers it. An override lifts the spawn ask only.
  ask-alone            deny. An ask command chained with other commands. (ask-commands-run-alone)
  guard-crash          crash. The guard itself raised. The call is allowed and the log shows it.

Other tools, in `judge` order:
  worktree-home        deny. A call from an agent whose shell cwd or write target is outside its
                       own recorded worktree. Read and Grep pass, so a stranded agent can report.
                       No record (a non-isolated agent, or the orchestrator) allows everything.
                       No override lifts it. (an-agent-outside-its-home-tree-must-stop)
  other-checkout       deny. Any session's write whose target sits in a checkout of this clone
                       other than the one holding its cwd. A nested worktree owns its own files.
                       A target in no checkout, or in the clone's `.git`, passes; unreadable git
                       passes. The shell form reads the targets frozen-path reads, after a
                       leading `cd`. An override lifts it.
                       (an-agent-outside-its-home-tree-must-stop)
  session-home         deny. A session whose recorded worktree folder is gone, with its cwd in the primary
                       checkout, and a write (Write family or shell) that lands in the primary's own
                       files. Its record is `<primary>/.git/session-homes/<session_id>`, written by a
                       call with no `agent_id` from a `.claude/worktrees/<name>` folder, cleared by that
                       session's ExitWorktree. The reason names the EnterWorktree tool. The clone's
                       `.git`, a target outside the clone, reads and non-writing shell pass. An
                       override lifts it. It adds no git spawn beyond what the call already spends.
  coordinator-scope    deny. A cloud coordinator's own write (no `agent_id`, CLAUDE_CODE_REMOTE true,
                       merge role `coordinator` for the environment's session id) to a repository path
                       outside the layout kinds of COORDINATOR_KINDS and its scratchpad. A path in no
                       repository passes. The shell form reads the targets frozen-path reads, after a
                       leading `cd`. A `git commit` is judged on its pathspecs, else its staged files
                       (`-a`: the modified tracked files too). A git read that fails judges nothing.
                       The reason says to brief a lane session. An override lifts it.
                       COORDINATOR_SCOPE_MODE "ask" turns the deny into an ask.
                       (session-tiers, roles-orchestrator-never-builds)
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
  merge-checks, draft-pr, impeccable-review-only
                       deny. The MCP merge, pull request and Skill forms of the rules above.
  simulator-boot-cap, simulator-boot-twin
                       deny. A simulator boot past the cap, or one that duplicates an idle device.
                       (sweep-shuts-down-idle-simulators)
  builder-test-edit, test-author-scope, record-writer-scope, designer-scope
                       deny. A role's write outside its scope. (builders-cannot-edit-tests)
  env-file, frozen-path, config-edit, agent-model-cap
                       the write-tool forms of the rules above. Every deny runs over all path
                       fields of a call before any ask.

A project's own `.claude/settings.json`, `.claude/settings.local.json` and `.claude/hooks/*`
are not frozen. They are allowed, and the guard logs one `config-edit` line, so the config-report
Stop hook can show the edit at turn end. `subject-unread` is logged the same way: an allow that a
person still gets to see.

`agent-model-cap` asks and never refuses, because that same write is how an Opus agent is
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
only the Opus spawn ask, and so does a step grant on the lane's roadmap step (decision agent-model-cap).
No override lifts `frozen-path`, `git-env-set`, a kill of pid 0, 1 or -1, the
role and model guards (the settings-write ask of `agent-model-cap`,
`agent-model-floor`, `roles-third-round-steps-up`, `builder-test-edit` and the other role guards),
or `worktree-home`. No override check reaches the missing-module deny, the `settings.json` deny list
or the `bin/rm` and `bin/merge` shims; each of those refusals says that no override lifts it. Every
refusal that goes through refuse() ends with the line the owner types, or with that same sentence.
The model judges (hooks/call_judge.py, hooks/prose_judge.py, hooks/sendmessage_state.py) refuse through
refuse() too, so an override lifts them.
"""

import importlib
import json
import os
import re
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
            AUTHOR_ROLE, DESIGNER_ROLE, GIT_WORK_TREE_RE, heredoc_heads, POWERSHELL_CALL, READ_ONLY_TOOLS, REDIRECTION, SHELL_TOOLS,
            SILENT_WRITE_REDIRECT, WRITER_ROLE, WRITE_TOOLS, _absolute, _expanded, _force_utf8_streams,
            _resolved, _run_dir, _segment_git_c_target, _split_heredocs, agent_role, basename, cap_safe,
            clone_checkouts, command_root, git_calls, git_common_dir, inline_script, is_move_into, is_powershell, is_worktree, log_path_and_text,
            nested_script, norm,
            path_is_inside, primary_checkout, record, refuse, resolve_command, resolve_default_base,
            segment_tokens, split_segments, strip_heredoc_bodies,
            _git_subcommand_index, dir_before_segment, shell_abs, walk_quotes,
        )
        from shared_names import read_merge_role  # the one reader of the role file, for rule coordinator-scope
        _loading = "guard_branch_worktree"
        from guard_branch_worktree import (
            BRANCH_DELETE_DENY_REASON, WORKTREE_PRUNE_ASK_REASON, WORKTREE_REMOVE_DENY_REASON,
            worktree_remove_forced,
        )
        _loading = "guard_shared_tree"
        from guard_shared_tree import (
            PUSH_DENY_REASON, STACK_DENY_REASON, TREE_ASK_REASON, TREE_DENY_REASON,
            checkout_conflict_resolve, names_only_files, one_place, session_id_of, shared_tree_match,
            SESSION_ID_RE, in_any_session_scratchpad, stash_takes_the_stack, subject_state, under_session_scratchpad,
        )
        _loading = "guard_pointer"
        from guard_pointer import (
            POINTER_HEAD_REASON, head_root, pointer_head_hit,
        )
        _loading = "guard_push_delete"
        from guard_push_delete import (
            DELETE_REASON, DESTRUCTIVE_DELETE, LINKED_NM_REASON, PUSH_ASK_REASON, PUSH_REASON,
            cmd_exe_delete_hit, delete_text, linked_nm_hit, parent_delete_hit, push_target,
            push_text, push_verdict, rm_delete_hit,
        )
        _loading = "guard_merge"
        from guard_merge import (
            BARE_MERGE_REASON, DRAFT_PR_REASON, MERGE_TOOLS, RECORDS_PAGE_REASON, _commit_shape, gh_call_of, git_call_of,
            merge_call_of, merge_check, merge_check_reason, records_page_hit, settings_roots,
            undrafted_pr_create, uses_merge_tool,
        )
        _loading = "guard_frozen"
        from guard_frozen import (
            FROZEN_REASON, MUTATING_COMMAND, _shell_write_hit, frozen_shell_hit, is_frozen, is_project_config,
            project_config_shell_hit,
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
            playwright_command_hit, playwright_install_hit,
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
                handle.write("\t".join([time.strftime("%Y-%m-%dT%H:%M:%S"), "", "crash", "guard-crash",
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
                    "the acts that no override lifts.")}}))
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


# decision lanes-start-in-tool-worktrees: a lane tree comes only from the tool's own isolation.
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
    "Rule (hand-made worktree): a lane tree comes only from the Agent tool's isolation "
    "'worktree' option or from the EnterWorktree tool, never from a tree made by hand. "
    "A hand-made tree sends a lane to work in the main clone and loses the isolation. "
    "Remedy: start the lane with one of those two tools. Call EnterWorktree with a `name` and no "
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

OTHER_CHECKOUT_REASON = (
    "Rule (other checkout): this write lands in another checkout of this clone, not the one this "
    "session stands in. "
    "Remedy: write only inside your own checkout, or report the change to the session that owns "
    "the other one. To remove a whole worktree, use `git worktree remove`, or leave it to the "
    "janitor sweep."
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
    "Approve it only when a model above Sonnet is wanted for this project."
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
    "`Drops-lines: <path> -- <reason>` may name a path."
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
    "Remedy: pass the message inline, or name a file this directory can read."
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
    "backtick code span or a fenced block is quoted text and stays allowed."
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
        or any(p.lower() in TEST_DIRS for p in parts)
    )


def is_test_config_rel(rel: str) -> bool:
    return bool(TEST_CONFIG.match(basename(rel)))


def author_path_ok(rel: str) -> bool:
    """A test-author may change a test path, test config, or a dev dependency list. `package.json`
    and `pyproject.toml` pass here and are read by content in `role_offences`."""
    return (is_test_rel(rel) or is_test_config_rel(rel) or basename(rel) in AUTHOR_BASENAMES
            or norm(rel).lstrip("/").lower() in AUTHOR_MUTATION_TESTS)


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
        # `session_id` is the parent's, the same for an agent (decision
        # an-agent-outside-its-home-tree-must-stop), and so is the id in the scratchpad path.
        # Another session's scratchpad is neither this one's nor "outside a repository".
        if in_any_session_scratchpad(full):
            return target
        return "" if repo_rel(target, cwd, outside=False) is None else target
    if role == WRITER_ROLE:
        return "" if rel.lower().endswith(".md") else target
    if is_test_rel(rel):
        return target
    if is_test_config_rel(rel) and any(
            disables_tests(part.splitlines(), []) for part in write_content_parts(tool_input)):
        return target
    return ""


def diff_bases(root: str):
    """The commits this agent's own work is measured against. Empty when git could not answer.

    TWO candidates, and a path counts only if it differs from BOTH:
      - the oldest `HEAD` reflog entry: the commit the worktree was cut from. It survives a new
        branch name (`switch -c b2`), which a branch reflog would not.
      - the merge base of HEAD with the default branch. It moves forward each time main is merged
        or rebased in.
    The work the parent branch handed over differs from the first and not the second only if the
    parent is the default branch; the work main later gained differs from the second and not the
    first. Only the agent's own change differs from both."""
    bases = []
    log = guard_core._git(root, "reflog", "show", "--format=%H", "HEAD")
    lines = log.stdout.split() if log is not None and log.returncode == 0 else []
    if lines:
        bases.append(lines[-1])
    default = resolve_default_base(root)
    if default:
        merged = guard_core._git(root, "merge-base", "HEAD", default)
        if merged is not None and merged.returncode == 0 and merged.stdout.strip():
            if merged.stdout.strip() not in bases:
                bases.append(merged.stdout.strip())
    return bases


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


def base_text(root: str, base: str, rel: str) -> str:
    """The file's text at the base commit, or '' when it did not exist there."""
    answer = guard_core._git(root, "show", base + ":" + norm(rel))
    return answer.stdout if answer is not None and answer.returncode == 0 else ""


def work_text(root: str, rel: str) -> str:
    try:
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except Exception:
        return ""


def disabling_added(root: str, base: str, rel: str) -> bool:
    """True when the lines a change ADDS to one file, against the base, disable tests."""
    return disables_tests(work_text(root, rel).splitlines(), base_text(root, base, rel).splitlines())


def role_offences(root: str, top: str, base: str, role: str):
    """The paths whose change, against ONE base, the role may not make; None when git failed.

    The files are the working tree against the base (committed, staged and unstaged work in one
    read; a change put back to the base's own bytes is no change) plus untracked files. Each path
    is checked as spelled and as resolved through symlinks."""
    tracked = guard_core._git(root, "diff", "--name-only", "-z", "--no-renames", base)
    fresh = guard_core._git(root, "ls-files", "--others", "--exclude-standard", "-z")
    if tracked is None or fresh is None or tracked.returncode or fresh.returncode:
        return None
    found = []
    for rel in [p for p in tracked.stdout.split("\0") if p] + sorted(
            p for p in fresh.stdout.split("\0") if p):
        # `is_test_rel` is the one place a backslash becomes `/`. A path outside the repository
        # reads `../...`, which no role owns.
        real = os.path.realpath(os.path.join(top, rel))
        names = [rel, os.path.relpath(real, top)]
        if role == AUTHOR_ROLE:
            bad = not all(author_path_ok(n) for n in names)
            if not bad and basename(rel) == "package.json":
                bad = not package_json_author_ok(base_text(root, base, rel), work_text(root, rel))
            if not bad and basename(rel) == "pyproject.toml":
                bad = not pyproject_author_ok(base_text(root, base, rel), work_text(root, rel))
        elif role == WRITER_ROLE:
            bad = not all(n.lower().endswith(".md") for n in names)
        elif role == DESIGNER_ROLE:
            bad = not all(designer_path_ok(n) for n in names)
        else:
            bad = any(is_test_rel(n) for n in names) or (
                is_test_config_rel(rel) and disabling_added(root, base, rel))
        if bad:
            found.append(rel)
    return found


def diff_violation(root: str, role: str):
    """Judge the agent's whole result. Returns ('', base) when clean, (the first offending path,
    base) when not, and (None, base) when git could not answer: UNKNOWN, never clear.

    A path offends only if it offends against EVERY base (see `diff_bases`)."""
    bases = diff_bases(root)
    top = guard_core._git(root, "rev-parse", "--show-toplevel")
    if not bases or top is None or top.returncode != 0:
        return None, ""
    top = os.path.realpath(top.stdout.strip())
    sets = [role_offences(root, top, base, role) for base in bases]
    if any(s is None for s in sets):
        return None, bases[0]
    both = [rel for rel in sets[0] if all(rel in s for s in sets[1:])]
    return (both[0] if both else ""), bases[0]


def diff_rule(role: str) -> str:
    return {AUTHOR_ROLE: "author-diff", WRITER_ROLE: "writer-diff",
            DESIGNER_ROLE: "designer-diff"}.get(role, "builder-diff")


def diff_refusal(tool: str, role: str, root: str) -> None:
    """Log a role's diff at commit or push for the reviewer. Never refuses: the base can count the
    parent branch's files as the agent's own (docs/decisions/builders-cannot-edit-tests.md)."""
    found, _ = diff_violation(root, role)
    if found is None:
        record(tool, "noted", "role-diff-unread", root)
    elif found:
        record(tool, "noted", diff_rule(role), found)


def judge_stop(payload) -> None:
    """A builder, test-author or record-writer that stops has its whole diff judged. The stop is never blocked:
    an offence logs as `builder-diff`, `author-diff` or `writer-diff`. A cwd that is the main checkout and a
    diff that could not be read log too. A missing cwd logs nothing."""
    role = agent_role(payload)
    if not role:
        return
    where = str(payload.get("cwd") or "")
    if not where:
        return
    if is_worktree(where) is False:
        record("SubagentStop", "noted", "role-diff-main-checkout", where)
        return
    found, _ = diff_violation(where, role)
    if found != "" and payload.get("stop_hook_active"):
        # kept: role_log_case still expects this line on a second stop
        record("SubagentStop", "noted", "role-diff-unresolved", found or "unread")
    elif found is None:
        record("SubagentStop", "noted", "role-diff-unread", where)
    elif found:
        record("SubagentStop", "noted", diff_rule(role), found)


SPAWN_TOOLS = ("Agent", "Task")
SESSION_TOOL = "mcp__ccd_session__start_session"
# The one list of roles that may run Haiku. lint/check_agent_models.py reads it from here.
HAIKU_ROLES = ("Explore", "claude-code-guide", "test-author", "reviewer", "record-writer")
MODEL_FLOOR_REASON = (
    "Sonnet is the floor for this role. Start the agent or session with model sonnet or opus, "
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
    elif tool == SESSION_TOOL:
        if below_the_floor(tool_input.get("model")):
            return str(tool_input.get("model"))
    elif tool == "Workflow" and isinstance(tool_input.get("script"), str):
        for _, bodies in script_agent_calls(tool_input["script"]):
            for keys, _, _ in bodies:
                if below_the_floor(keys.get("model")) and keys.get("agentType") not in HAIKU_ROLES:
                    return keys["model"]
    return ""


STEP_UP_MARKER = re.compile(r"(?im)^[ \t]*(round|try)[ \t]+(\d)[ \t]+of[ \t]+3\b")
# A first non-blank line that does not start with a marker also counts its leftmost marker-shaped text, wherever
# it sits (a role word or markup ahead of it), but only when that text is `Round N of 3`. A later one on the line is
# prose, so a leftmost `Try N of 3` adds nothing. Case-sensitive, so lowercase prose does not count (decision agent-model-cap).
FIRST_LINE_MARKER = re.compile(r"\b(Round|Try)[ \t]+(\d)[ \t]+of[ \t]+3\b")
# A builder's third-round marker is the `Round N of 3` line. The old `Try N of 3` line still counts until
# note try-marker-sunset.
BUILDER_MARKERS = ("round", "try")


def brief_markers(brief) -> list:
    """The [(kind, n)] markers of a brief: each line that starts with the marker, plus the leftmost
    marker in a first non-blank line that does not start with one, when it is `Round N of 3`. The one
    home of the marker scan."""
    if not isinstance(brief, str):
        return []
    found = STEP_UP_MARKER.findall(brief)
    first = next((line for line in brief.split("\n") if line.strip()), "")
    lead = None if STEP_UP_MARKER.match(first) else FIRST_LINE_MARKER.search(first)
    return found + ([lead.groups()] if lead and lead.group(1) == "Round" else [])


def builder_third_round(brief) -> bool:
    """True when a brief holds a builder's third-round marker, in either spelling."""
    return any(kind.lower() in BUILDER_MARKERS and n == "3" for kind, n in brief_markers(brief))


# A Workflow agent() call is read statically; one whose prompt or model the scan cannot read passes.
def step_up_hit(tool: str, tool_input) -> str:
    """The step-up reason for a spawn whose marker and model disagree, or "". Only a line
    that starts with the marker, or the brief's first line, counts. A missing model runs the env default, which is Sonnet for a builder; a reviewer's
    frontmatter model is haiku, so a reviewer round 2 must name sonnet and round 3 must name sonnet or opus."""
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
            return "Reviewer round 3 runs on Sonnet or Opus. Spawn it with model sonnet or opus."
    if role == "builder" and builder_third_round(prompt) and "opus" not in model:
        return "Builder round 3 runs on Opus. Spawn it with model opus."
    return ""


# THE MACHINE-LOAD BRAKE (decision machine-load-brake). A lane-start call reads the machine's load once. Memory in
# use is a share of this machine's memory; disk free on the home drive is in GB (2**30 bytes) against the drive's
# size. Busy (memory over 85%, or disk free under the smaller of 10% of the disk and 15 GB) refuses a Workflow and an
# explicit background Agent or Task call. An Agent or Task call passes at busy only when it leaves
# run_in_background out or sets it false. (In the desktop harness a left-out call still runs in the background
# and the field is not offered, so busy does not slow an Agent lane there.) Full (memory over 95%, disk free
# under the smaller of 5% of the disk and 5 GB) refuses every lane. A reading that cannot be read counts as normal. Only an
# agent's shell or file write also reads load (RUNNING_LANE_TOOLS, below).
LANE_TOOLS = SPAWN_TOOLS + ("Workflow", SESSION_TOOL)
LOAD_BUSY_MEMORY = 85.0
LOAD_FULL_MEMORY = 95.0
LOAD_BUSY_DISK_SHARE, LOAD_BUSY_DISK_GB = 10.0, 15.0   # busy: free under the smaller of the two
LOAD_FULL_DISK_SHARE, LOAD_FULL_DISK_GB = 5.0, 5.0
GIB = 2 ** 30
LOAD_BUSY_REASON = "the machine is busy (%s). %s"
LOAD_BUSY_AGENT_FORM = ", or start this lane as an Agent call that leaves run_in_background out or sets it false"
LOAD_BUSY_NO_FOREGROUND = "A Workflow has no foreground form. "
LOAD_FULL_REASON = "the machine is full (%s). No new lane starts until the load drops. Wait, then retry."


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
    """(rule reason, matched) when the machine's load refuses this lane-start call, else ("", ""). The one
    read of the call: a failed read or an unread value counts as normal."""
    if tool not in LANE_TOOLS:
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


# A RUNNING LANE (decision machine-load-brake, "Running lanes"). An agent's own call that can fill a disk (a shell or
# a file write) reads the load once, inside this hook that already runs for the call. Full refuses it, so a lane
# stops even while its orchestrator waits on the owner. Busy lets it run. The orchestrator's own calls read nothing,
# so the session that frees the disk is never braked by the full disk.
RUNNING_LANE_TOOLS = ("Bash", "PowerShell") + WRITE_TOOLS
LOAD_LANE_FULL_REASON = ("the machine is full (%s). Stop this lane now: end your turn and report the reading to "
                         "your orchestrator, which frees space or waits for the load to drop.")


def running_lane_hit(payload, tool: str) -> tuple:
    """(rule reason, matched) when an agent's disk-filling call meets a full machine, else ("", ""). One read
    per such call; none for the orchestrator, and none for a lane-start call, which load_hit reads."""
    agent_id = payload.get("agent_id") if isinstance(payload, dict) else None
    if tool not in RUNNING_LANE_TOOLS or not isinstance(agent_id, str) or not AGENT_ID.match(agent_id):
        return "", ""
    try:
        reading = read_load()
    except Exception:
        return "", ""
    full = load_full(reading)
    return (LOAD_LANE_FULL_REASON % ", ".join(full), ", ".join(full)) if full else ("", "")


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
    "Rule (configuration): this spawn sets model Opus. Sonnet is the ceiling for an agent; Opus runs "
    "only on the owner's grant for this spawn, except Plan, Explore, the designer, the design "
    "reviewer and a builder's Round 3 of 3 "
    "(decision agent-model-cap). Approve it only when the owner asked for Opus here."
)
OPUS_BUILDER_REASON = (
    OPUS_SPAWN_REASON + " No `Round 3 of 3` marker was found in the brief's first line or at the start of "
    "any line. The marker applies only to a builder's third try, after review round 2 failed."
)
OPUS_STANDING_ROLES = ("Plan", "Explore", "designer", "design-reviewer")


def opus_spawn_hit(tool: str, tool_input) -> str:
    """The model of an Agent or Task spawn that sets Opus with no standing grant, or "". A standing grant
    is the role Plan, Explore, designer or design-reviewer, or a builder whose brief holds the third-round marker (the same marker
    step_up_hit reads). A reviewer's spawn is no standing grant, so a reviewer on Opus asks. The spawn ask is liftable by an
    override, so never_lifted does not read it."""
    if tool not in SPAWN_TOOLS or "opus" not in str(tool_input.get("model") or "").lower():
        return ""
    role, brief = tool_input.get("subagent_type"), tool_input.get("prompt")
    if role in OPUS_STANDING_ROLES:
        return ""
    if role == "builder" and builder_third_round(brief):
        return ""
    return str(tool_input.get("model"))


# ASK ALONE (ruling ask-commands-run-alone). A command that would ASK is held, not printed, while the other rules run, so a
# deny anywhere still wins. At the end, an ask command with any other command in the shell call (`&&`, `||`,
# `;`, `|`, a newline) is refused, and the same command alone asks as before, as does one with a named
# harmless lead or tail (harmless_commands, below). The deny
# names the command by its kind, never its text. Only the first ask command is held: it is the one that
# printed before.
PENDING_ASK = []   # [(rule, reason, matched, command)], at most one
ASK_ALONE_REASON = ("this shell call chains a command that needs the owner's answer (%s) with "
                    "other commands. Run that command alone, in its own call, or drop it.")


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

    # 1c2. A lane worktree made by hand, outside the tool's own folder.
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
    for segment in split_segments(stripped):
        if not segment.strip():
            continue
        tokens = segment_tokens(segment)
        if tokens is None:
            previous = None
            continue
        matched = kill_hit(tokens) or kill_fed_by_name(tokens) or kill_fed_by_pipe(tokens, previous)
        previous = tokens
        if matched:
            refuse(tool, "deny", "machine-wide-kill", KILL_REASON, matched)
        # Every agent shares the main session's id, so only the main session may own by tag.
        matched = foreign_pid_kill(tokens, transcript, "" if agent else session_id)
        if matched:
            refuse(tool, "deny", "machine-wide-kill", KILL_PID_REASON, matched)

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

    # 6b. A pull request opened without --draft.
    for text, _in_message in _substitutions(stripped)[0]:
        if any(undrafted_pr_create(seg) for seg in split_segments(text) if seg.strip()):
            refuse(tool, "deny", "draft-pr", DRAFT_PR_REASON, "gh pr create")

    # 6c. A lane commit of the generated records page (decision records-index-at-merge).
    matched = records_page_hit(stripped, cwd)
    if matched:
        refuse(tool, "deny", "records-page", RECORDS_PAGE_REASON, matched)

    # 7. A frozen path.
    matched = frozen_shell_hit(stripped, cwd)
    if matched:
        refuse(tool, "deny", "frozen-path", FROZEN_REASON, matched)

    # 7b. A project config edit: allowed (Decision 7), and noted in the log only.
    matched = project_config_shell_hit(stripped, cwd)
    if matched:
        record(tool, "noted", "config-edit", matched)


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
# `command-in-item`, `task-names-check`, `owner-judge`, `question-form`). This check runs them only for a
# write to this repo's waiting page.
DATA_TOOL = "ArtifactData"
WAITING_ITEMS = "items"


def _is_waiting_page(tool_input, cwd) -> bool:
    """True when the call's url is this repo's waiting page (lint/layout.py, the one home). A repo
    with no page reads as unknown, and its calls are not judged."""
    lint = os.path.join(_HERE, "..", "lint")
    if lint not in sys.path:
        sys.path.append(lint)
    import layout
    root = _git_root_of(cwd)
    page = layout.waiting_page(root) if root else "unknown"
    url = str(tool_input.get("url") or "").rstrip("/")
    return page != "unknown" and url == page.rstrip("/")


def _git_root_of(cwd):
    here = os.path.realpath(cwd or os.getcwd())
    while True:
        if os.path.exists(os.path.join(here, ".git")):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            return None
        here = parent


def data_tool_hit(tool_input, cwd=""):
    """(rule, matched) for the first write of a waiting item that a rule refuses, else ("", "")."""
    if not isinstance(tool_input, dict):
        return "", ""
    if tool_input.get("action") == "batch":
        entries = [(w.get("op"), w) for w in tool_input.get("writes") or [] if isinstance(w, dict)]
    else:
        entries = [(tool_input.get("action"), tool_input)]
    writes = [(op, e) for op, e in entries
              if op in ("set", "update", "str_replace") and e.get("collection") == WAITING_ITEMS]
    if not writes or not _is_waiting_page(tool_input, cwd):  # a read or another collection loads nothing more
        return "", ""
    import question_form
    for op, entry in writes:
        hit = question_form.item_hit(op, entry)
        if hit[0]:
            return hit
    return "", ""


# ------------------------------------------------------------------ impeccable is review-only
#
# docs/decisions/design-skills.md, rule `impeccable-review-only`: the skill loads only for a review
# (`audit`, `critique`). Its build commands and its settings writers are refused. The reason names
# no command; the log holds what the call asked for.
IMPECCABLE_REASON = ("impeccable is for a design review only. Ask for a review of the rendered "
                     "screens; make any change to the design by hand.")
IMPECCABLE_SKILLS = ("impeccable", "impeccable:impeccable")
IMPECCABLE_REVIEWS = ("audit", "critique")
IMPECCABLE_CHAIN = re.compile(r"[;|\n]|&&")
RUNNER_WORDS = ("npx", "bunx", "node", "pnpm", "yarn", "npm", "dlx", "exec", "run", "x")
PACKAGE_FLAGS = ("-p", "--package")


def impeccable_name(token: str) -> str:
    """The package or script name of a token, without a path, a `@version` or an extension."""
    name = basename(token).split("@", 1)[0]
    return name.rsplit(".", 1)[0]


def impeccable_skill_hit(tool_input) -> str:
    skill, args = tool_input.get("skill"), tool_input.get("args") or ""
    if not isinstance(skill, str) or skill.lstrip("/") not in IMPECCABLE_SKILLS:
        return ""
    words = args.split() if isinstance(args, str) else []
    if words and words[0] in IMPECCABLE_REVIEWS and not IMPECCABLE_CHAIN.search(args.strip()):
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
# docs/decisions/sweep-shuts-down-idle-simulators.md, rulings 3 and 4. A boot is `simctl boot`, an
# `xcodebuild -destination` that names a shut-down simulator, or the simulator MCP tool's `launch`
# naming one. `simctl list` runs only after a call matched as a boot. The idle test is the sweep
# tier's own (`sweep.sim_keep_code`), imported lazily: janitor/sweep.py imports this file.
SIM_MCP = "mcp__Claude_Code_iOS_Simulator__control"
SIM_BOOT_CAP = 2


def _sim_boot_names(segment: str) -> list:
    """The device names or UDIDs a segment boots, by the command word. Empty when it boots none."""
    tokens = segment_tokens(segment)
    index = resolve_command(tokens) if tokens else None
    if index is None:
        return []
    word, rest = basename(tokens[index]), tokens[index + 1:]
    if word == "xcodebuild":
        found = []
        for i, token in enumerate(rest):
            value = rest[i + 1] if token == "-destination" and i + 1 < len(rest) else (
                token[len("-destination="):] if token.startswith("-destination=") else "")
            fields = dict(p.split("=", 1) for p in value.split(",") if "=" in p)
            if "iOS Simulator" in fields.get("platform", "") and (fields.get("id") or fields.get("name")):
                os_ = fields.get("OS", "")  # a numeric OS= filters a name; an id, or OS=latest, filters nothing
                found.append((fields.get("id") or fields["name"], "" if fields.get("id") or not re.fullmatch(r"[0-9.]+", os_) else os_))
        return found
    if word in ("xcrun", "simctl") and "simctl" in ([word] + rest):
        after = ([word] + rest)[([word] + rest).index("simctl") + 1:]
        if after[:1] == ["boot"] and len(after) > 1:
            return [after[1]]
    return []


def sim_boot_refusal(tool: str, names: list) -> None:
    """Refuse a boot of any of NAMES when two devices are booted, or an idle twin is booted."""
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
    for name in names:
        name, os_ = name if isinstance(name, tuple) else (name, "")  # a destination's OS= picks a runtime
        hits = [d for d in devices if name.upper() == d["udid"].upper() or name == d["name"]]  # a UDID has no case
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


def worktree_home_hit(payload, tool: str, tool_input: dict, cwd: str) -> str:
    """Rule 0, worktree-home: return the log detail when an agent's call reaches outside its own
    worktree, else ''. `status` is "none" for the orchestrator (no `agent_id`) and for tools this
    rule does not judge; "unknown" when the record could not be read at all, which allows (an
    unreadable state is never a hit); "no-record" for a non-isolated agent, which allows everything;
    "home" once the agent's worktree is known, from this call or an earlier one. Read/Grep are never
    checked here: the agent must still be able to read and report
    (docs/decisions/an-agent-outside-its-home-tree-must-stop.md)."""
    # Rule 0 alone reads a Git Bash `/c/Users/...` cwd in the form the home record is written in. Off
    # Windows `/c/` is a real folder. One reader of the drive spelling: `_expanded`. Every other
    # rule sees `cwd` as main does.
    home_cwd = _expanded(cwd, "") if cwd and os.name == "nt" else cwd
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
                    and path_is_inside(resolved_target, home) is False):
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


def other_checkout_hit(tool: str, tool_input: dict, cwd: str) -> str:
    """Rule 0, other-checkout, for every session: the log detail when a write lands in a checkout
    of this clone other than the one holding `cwd`, else ''. A target in no checkout passes. An
    unreadable git state, or a cwd in no checkout, is unknown and passes. One git read per call
    that can write. Liftable by an owner override, unlike `worktree_home_hit`
    (docs/decisions/an-agent-outside-its-home-tree-must-stop.md)."""
    if tool in WRITE_TOOLS:
        targets = write_targets(tool_input)
    elif tool in SHELL_TOOLS:
        targets = None
        command = strip_heredoc_bodies(str(tool_input.get("command", "") or ""))
        if not SHELL_WRITE_HINT.search(SHELL_QUIET_REDIRECT.sub(" ", command)):
            return ""
    else:
        return ""
    if targets == []:
        return ""
    where = _expanded(cwd, "") if cwd and os.name == "nt" else cwd
    roots = clone_checkouts(where) if where else None
    own = _owning_checkout(where, roots) if roots else ""
    if not own:
        return ""

    def elsewhere(target, at):
        try:
            resolved = _resolved(target, at)
            owner = _owning_checkout(resolved, roots)
        except Exception:
            return False
        # The primary's `.git` is the clone's common directory, shared by every checkout.
        return (bool(owner) and owner != own
                and path_is_inside(resolved, os.path.join(owner, ".git")) is not True)

    if targets is None:
        hit = _shell_write_hit(command, where, elsewhere, follow_cd=True)
        return "shell write into another checkout: " + hit if hit else ""
    for target in targets:
        if elsewhere(target, where):
            return "write target in another checkout: " + target
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
# is left out in session_home_git_hit.
SESSION_HOME_GIT_VERBS = ("checkout", "switch", "pull", "merge", "commit", "rebase", "restore", "reset",
                          "stash", "cherry-pick", "revert", "am", "apply")
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
    if not isinstance(payload, dict) or payload.get("agent_id"):
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
            if verb == "stash" and args[:1] in (["list"], ["show"]):
                continue
            if in_primary(folder, folder):
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


# Rule coordinator-scope (records session-tiers and roles-orchestrator-never-builds; incident: a cloud
# coordinator edited another repo's instructions file itself, 2026-10-31). A cloud coordinator briefs lane
# sessions and writes records. Its own write goes only to a layout kind of COORDINATOR_KINDS, its own
# scratchpad, or a path in no repository. The rule acts only on a call with no agent, in a cloud session
# (CLAUDE_CODE_REMOTE true), whose merge role is `coordinator`: read_merge_role matches the role file to
# the environment's session id, never to the payload's. The kinds' paths are read from lint/layout.json
# (RECORD_LAYOUT_FILE), the layout's legacy map included, so no path is copied here. An owner override
# lifts the rule: it is not in never_lifted. Cost: one small file read per write or shell call of a cloud
# session, one `git diff --cached` per coordinator `git commit` (plus `git diff` for `-a`). A git read that
# fails judges nothing.
COORDINATOR_KINDS = ("decisions", "debts", "debt-notes", "plans", "specs", "todo", "records-index",
                     "design", "scorecard")
COORDINATOR_SCOPE_MODE = "deny"
COORDINATOR_SCOPE_REASON = (
    "Rule (Roles): a coordinator briefs lanes and writes records. It does not change a repository's code, "
    "settings or instructions itself. "
    "Remedy: brief a lane session to make this change, with the files and the check that proves it. "
    "Write records and your scratchpad yourself."
)
_COORDINATOR_PATHS = []


def coordinator_paths():
    """[(path, is_file)] for each kind of COORDINATOR_KINDS, at its layout path and its legacy path, lower
    case with no edge slash. [] when no settings clone holds a readable layout: then no repository path passes."""
    if _COORDINATOR_PATHS:
        return _COORDINATOR_PATHS[0]
    for root in settings_roots():
        try:
            with open(os.path.join(root, RECORD_LAYOUT_FILE), encoding="utf-8") as handle:
                data = json.load(handle)
            legacy = data.get("legacy") or {}
            found = []
            for kind in COORDINATOR_KINDS:
                path = data["kinds"][kind]["path"]
                for spelled in (path, legacy.get(path, path)):
                    spelled = norm(spelled).strip("/").lower()
                    entry = (spelled, bool(os.path.splitext(spelled)[1]))
                    if spelled and entry not in found:
                        found.append(entry)
        except Exception:
            continue
        _COORDINATOR_PATHS.append(found)
        return found
    return []


def coordinator_rel_ok(rel: str) -> bool:
    """True when a repository-relative path is a kind's file, or a file inside a kind's folder. The case is
    folded, because the folder is one folder on a case-insensitive disk."""
    parts = [part for part in norm(rel).lower().split("/") if part]
    if ".." in parts:
        return False
    joined = "/".join(parts)
    return any(joined == path or (not is_file and joined.startswith(path + "/"))
               for path, is_file in coordinator_paths())


def coordinator_path_outside(target: str, where: str, session_id: str) -> bool:
    """True when `target` sits in a repository, is no coordinator kind and is not this session's scratchpad."""
    try:
        rel = repo_rel(target, where, outside=False)
        return (rel is not None and not coordinator_rel_ok(rel)
                and not under_session_scratchpad(_expanded(target, where), session_id))
    except Exception:
        return False


def coordinator_commit_hit(stripped: str, cwd: str) -> str:
    """The first path a `git commit` of this command would hold that is no coordinator kind, else ''. The
    paths are the pathspecs on the commit line when it has any (a commit with paths ignores the index), else
    the staged files, and with `-a` the modified tracked files too."""
    for segment in split_segments(stripped):
        call = git_call_of(segment) if segment.strip() else None
        if call is None or call[0] != "commit":
            continue
        c_target = _segment_git_c_target(segment_tokens(segment) or [])
        root = command_root(stripped, cwd)
        where = _absolute(c_target, root) if c_target is not None else root
        if not where or not os.path.isdir(where):
            continue
        all_flag, specs = _commit_shape(call[1])
        names = []
        if specs:
            done = guard_core._git(where, "rev-parse", "--show-toplevel")
            if done is None or done.returncode != 0 or not done.stdout.strip():
                continue
            top = os.path.realpath(done.stdout.strip())
            for spec in specs:
                rel = norm(os.path.relpath(os.path.realpath(os.path.join(where, spec)), top))
                if not rel.startswith("../") and rel != "..":
                    names.append(rel)
        else:
            for extra in ([("diff", "--cached")] + ([("diff",)] if all_flag else [])):
                done = guard_core._git(where, *extra, "--name-only", "-z", "--no-renames")
                if done is not None and done.returncode == 0:
                    names.extend(name for name in done.stdout.split("\0") if name)
        for rel in names:
            if not coordinator_rel_ok(rel):
                return "git commit " + rel
    return ""


def coordinator_scope_hit(payload, tool: str, tool_input: dict, cwd: str) -> str:
    """Rule coordinator-scope: the log detail when a cloud coordinator's own call writes a repository path
    outside COORDINATOR_KINDS and its scratchpad, or commits one, else ''."""
    if tool not in WRITE_TOOLS and tool not in SHELL_TOOLS:
        return ""
    if os.environ.get("CLAUDE_CODE_REMOTE") != "true":
        return ""
    if not isinstance(payload, dict) or payload.get("agent_id") or payload.get("agent_type"):
        return ""
    if read_merge_role() != "coordinator":
        return ""
    session_id = session_id_of(payload)
    if tool in WRITE_TOOLS:
        for target in write_targets(tool_input):
            if coordinator_path_outside(target, cwd, session_id):
                return target
        return ""
    stripped = strip_heredoc_bodies(str(tool_input.get("command", "") or ""))
    hit = _shell_write_hit(stripped, cwd, lambda word, where: coordinator_path_outside(word, where, session_id),
                           follow_cd=True)
    return "shell write: " + hit if hit else coordinator_commit_hit(stripped, cwd)


def never_lifted(payload, tool: str, tool_input: dict, cwd: str) -> bool:
    """True when the call holds an act no owner override lifts (decision owner-override): a
    git location variable, a frozen path, a kill of pid 0, 1 or -1, a role or model guard, or a
    worktree-home refusal. refuse() asks this before it spends an override, because a lifted act ends the
    check."""
    if (floor_hit(tool, tool_input) or step_up_hit(tool, tool_input)
            or worktree_home_hit(payload, tool, tool_input, cwd)):
        return True
    if tool in SHELL_TOOLS:
        raw = tool_input.get("command", "") or ""
        stripped = strip_heredoc_bodies(raw)
        return bool(git_env_command_hit(raw, stripped) or frozen_shell_hit(stripped, cwd)
                    or any(t and kills_group_pid(t) for t in map(segment_tokens, split_segments(stripped)))
                    or (_shell_write_hit(stripped, cwd, is_settings_file) and cap_change(raw)))
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
    # worktree-home never judged them, the settings deny list owns Read(.env) and Read(.env.*),
    # and a frozen path stays readable.
    if tool in READ_ONLY_TOOLS:
        return
    cwd = payload.get("cwd", "") or os.getcwd() or ""
    if not isinstance(cwd, str):
        cwd = ""
    guard_core.set_override_veto(lambda: never_lifted(payload, tool, tool_input, cwd))
    session_home_keep(payload, tool, cwd)  # rule session-home's record, kept before any refusal can end the call
    # 0. Each agent stays inside its own worktree.
    home_hit = worktree_home_hit(payload, tool, tool_input, cwd)
    if home_hit:
        refuse(tool, "deny", "worktree-home", WORKTREE_HOME_REASON, home_hit)
    # 0, other-checkout. Every session writes only inside its own checkout of the clone. An override lifts it:
    # a rule id of its own, because the owner ruled that no override lifts worktree-home.
    other_hit = other_checkout_hit(tool, tool_input, cwd)
    if other_hit:
        refuse(tool, "deny", "other-checkout", OTHER_CHECKOUT_REASON, other_hit)
    # 0, session-home. A session whose own worktree is gone writes nowhere in the primary checkout. An
    # override lifts it, and it is not in never_lifted: the owner may mean the write.
    session_hit = session_home_hit(payload, tool, tool_input, cwd)
    if session_hit:
        refuse(tool, "deny", "session-home", SESSION_HOME_REASON, session_hit)
    # 0, coordinator-scope. A cloud coordinator's own write goes only to records, its scratchpad or a path in
    # no repository. An override lifts it, and it is not in never_lifted: the owner may mean the write.
    scope_hit = coordinator_scope_hit(payload, tool, tool_input, cwd)
    if scope_hit:
        refuse(tool, COORDINATOR_SCOPE_MODE, "coordinator-scope", COORDINATOR_SCOPE_REASON, scope_hit)

    # 9. The agent model floor. A spawn that names a Haiku model is refused. The reason names no
    # model; the log holds what the call asked for.
    floor_model = floor_hit(tool, tool_input)
    if floor_model:
        refuse(tool, "deny", "agent-model-floor", MODEL_FLOOR_REASON, floor_model)

    # 9b. Step-up: a reviewer's second round on Sonnet, its third on Sonnet or Opus, a builder's third on Opus.
    step_up = step_up_hit(tool, tool_input)
    if step_up:
        refuse(tool, "deny", "roles-third-round-steps-up", step_up, str(tool_input.get("model")))

    # 9c. The machine-load brake: one read on a lane-start call, and one on an agent's shell or file write.
    # It runs before the Opus ask, because a lifted ask exits refuse() at once and would skip this deny.
    load_reason, load_matched = load_hit(tool, tool_input)
    if not load_reason:
        load_reason, load_matched = running_lane_hit(payload, tool)
    if load_reason:
        refuse(tool, "deny", "load-brake", load_reason, load_matched)

    # 9d. The Opus ceiling: a spawn on Opus with no standing grant asks. An override, an Opus
    # pass for the spawn's role or a step grant lifts it. A spawn with no role runs general-purpose.
    opus_model = opus_spawn_hit(tool, tool_input)
    if opus_model:
        refuse(tool, "ask", "agent-model-cap",
               OPUS_BUILDER_REASON if tool_input.get("subagent_type") == "builder" else OPUS_SPAWN_REASON,
               opus_model,
               spawn_role=str(tool_input.get("subagent_type") or "general-purpose"))

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

    if tool == "Skill":
        matched = impeccable_skill_hit(tool_input)
        if matched:
            refuse(tool, "deny", "impeccable-review-only", IMPECCABLE_REASON, matched)
        return

    if tool == DATA_TOOL:
        rule, matched = data_tool_hit(tool_input, cwd)
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
        if rule == "task-names-check":
            refuse(tool, "deny", "task-names-check", question_form.PAGE_REASONS["task-names-check"], matched)
        if rule == "owner-judge":
            refuse(tool, "deny", "owner-judge", question_form.PAGE_REASONS["owner-judge"], matched)
        if rule == "question-form":
            refuse(tool, "deny", "question-form", question_form.PAGE_REASONS["question-form"], matched)
        if rule == "item-field-rendered":
            refuse(tool, "deny", "item-field-rendered", question_form.PAGE_REASONS["item-field-rendered"], matched)
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
            names = [n for seg in split_segments(strip_heredoc_bodies(command))
                     for n in _sim_boot_names(seg)]
            if names:
                sim_boot_refusal(tool, names)
        return
    if tool == SIM_MCP:
        # `udid` is an alias of `device`: judge each non-empty name, so one field hides no other.
        names = list(dict.fromkeys(v for v in map(tool_input.get, ("device", "udid"))
                                   if isinstance(v, str) and v))
        if tool_input.get("action") == "launch" and names:
            sim_boot_refusal(tool, names)
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

        # 5. The environment file. Every writing tool is refused. A read is not judged here: the
        # settings deny list blocks Read(.env) and Read(.env.*). The reason names no file, and the log
        # holds the path the tool asked for.
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
