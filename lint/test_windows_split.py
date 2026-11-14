#!/usr/bin/env python3
"""Guard for the splits of .github/workflows/checks.yml: the Windows split, the Linux split and the macOS split.

WindowsSplit proves: (1) each suite command in REQUIRED runs in exactly one `windows-latest` job (none
dropped, none run twice); (2) at least MIN_JOBS `windows-latest` jobs carry those suites.
Cut F adds: the guard suite has its own Windows job (GUARD_JOB) and runs off it nowhere else; its
slice (GUARD_TESTS=windows-slice) runs only on pull_request; the guard mutation test has its own
Linux job (MUTATE_JOB) and runs nowhere else; both jobs skip on the `guard` scope flag. A scoped job's
job-level if, if any, holds only the draft guard; its scope condition sits in each step
(read_scope_condition, step_rest), so a step cannot run outside the scope condition.

Why not rule_audit.py: it reads step names only. This needs job boundaries and `run:` lines.
Line-based parse, stdlib only, like rule_audit. Only single-line `run: <cmd>` steps count.
CHECKS_YML overrides the path (used for red runs on a scratch copy).

CiCoverage also proves every tracked test file has a run step: test_*.py, test_*.sh, test_*.mjs, *.test.mjs,
*.test.js and *.test.ps1. A file the mod-test collector prints is covered by the step that runs that collector.

SplitJobs does the same for the Linux split (checks, checks-merge-install) and the macOS split (checks-macos, checks-macos-b):
each suite runs in exactly one job of its split, with its pinned `if:` and `shell:`. It also reads the Linux guard split
(checks-guard, checks-guard-2): the guard suite runs in one shard per job, each with its GUARD_SHARD value, and both shards
are named in the all-jobs-passed and ci-done needs.

Run with:  python3 lint/test_windows_split.py -v
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from workflow_steps import CHECKS_SUITE_JOBS, gating_text, job_block, run_body, step_blocks, step_env, step_key  # noqa: E402  the one home of the step parser
CHECKS = os.environ.get("CHECKS_YML") or os.path.join(HERE, "..", ".github", "workflows", "checks.yml")
MIN_JOBS = 3

# The run commands of the old single `checks-windows` job. Edit here only on purpose.
REQUIRED = [
    "python hooks/test_guard.py",
    "python janitor/test_sweep.py",
    "python janitor/mutate_sweep.py",
    "python hooks/test_config_watch.py",
    "python hooks/test_precompact_handoff.py",
    "python hooks/test_decision_watch.py",
    "python hooks/test_prose_judge.py",
    "python hooks/test_rm_prompt_answer.py",
    "python hooks/test_agent_brief.py",
    "python hooks/test_wrappers.py",
    "python lint/test_report_guard.py",
    "python hooks/test_ruling_home.py",
    "python lint/test_ruling_census.py",
    "python lint/test_verdict.py",
    "python lint/test_hook_platform_exit.py",
    "python lint/check_unknown_reads_contract.py",
    "python janitor/test_session_end_sweep.py",
    "python janitor/test_install_launchd.py",
    "python janitor/test_install_schtasks.py",
    "sh hooks/test_install_windows.sh",
    "node actions/stamp/test_stamp.mjs",
    "bash actions/stamp/test_action.sh",
    "python merge/test_launch.py",
    "python merge/test_merge.py",
    "python merge/test_cmd.py",
]


# The suites the single `checks` job ran (Linux) and the single `checks-macos` job ran (macOS) before the split, each with
# its step's `if:` and `shell:`. checks-merge-install and checks-macos-b took some of them, so each suite runs in exactly one
# job of its split. A suite is a run of a test file, a mutation test or the mod tests. The Linux pair is CHECKS_SUITE_JOBS,
# its one home in lint/workflow_steps.py; the macOS lists stay here.
LINUX_SPLIT = CHECKS_SUITE_JOBS
LINUX_CODE = "needs.scope.outputs.code == 'true'"
LINUX_CODE_SWEEP = f"{LINUX_CODE} && needs.scope.outputs.sweep == 'true'"
LINUX_SWEEP = "needs.scope.outputs.sweep == 'true'"
LINUX_MODS = "!cancelled() && needs.scope.outputs.mods == 'true'"
# The scope condition on a step that reads no .md file, unwrapped as unwrap() reads an `if:`. lint/test_checks_step_scope.py pins which steps take it.
NO_MD_SCOPE_CONDITION = "needs.scope.outputs.code == 'true' || github.event_name != 'pull_request'"
# The scope condition of a step that reads the doc groups in `groups` (lane ci-skip-untouched-steps, slice 3): code, the
# doc_<group> flags of ci-scope.sh, and a non-pull_request event. No group gives NO_MD_SCOPE_CONDITION. The flags come in
# DOC_GROUPS order, so a group tuple in any order builds one string. lint/test_checks_step_scope.py shares these constants.
DOC_GROUPS = ("decisions", "rules", "skills", "agents", "glossary", "map", "other", "any")


def doc_scope_condition(groups):
    """The inner expression of the scope condition for the doc groups `groups`. A name outside DOC_GROUPS is an error."""
    unknown = [g for g in groups if g not in DOC_GROUPS]
    if unknown:
        raise ValueError("not a doc group: %s" % unknown)
    flags = "".join("needs.scope.outputs.doc_%s == 'true' || " % g for g in DOC_GROUPS if g in groups)
    return "needs.scope.outputs.code == 'true' || %sgithub.event_name != 'pull_request'" % flags


# One constant per distinct group set that a doc step reads (the set of lint/test_checks_step_scope.py DOC_STEPS).
SCOPE_DOC_ANY = doc_scope_condition(("any",))
SCOPE_DOC_DECISIONS = doc_scope_condition(("decisions",))
SCOPE_DOC_RULES = doc_scope_condition(("rules",))
SCOPE_DOC_SKILLS = doc_scope_condition(("skills",))
SCOPE_DOC_AGENTS = doc_scope_condition(("agents",))
SCOPE_DOC_DECISIONS_RULES = doc_scope_condition(("decisions", "rules"))
SCOPE_DOC_DECISIONS_OTHER = doc_scope_condition(("decisions", "other"))
SCOPE_DOC_DECISIONS_MAP_OTHER = doc_scope_condition(("decisions", "map", "other"))
SCOPE_DOC_DECISIONS_RULES_OTHER = doc_scope_condition(("decisions", "rules", "other"))
SCOPE_DOC_SKILLS_OTHER = doc_scope_condition(("skills", "other"))
SCOPE_DOC_SKILLS_DECISIONS = doc_scope_condition(("skills", "decisions"))
SCOPE_DOC_SKILLS_AGENTS = doc_scope_condition(("skills", "agents"))
LINUX_SUITES = {
    "python3 actions/test_action_metadata.py": (LINUX_CODE, None),
    "python3 actions/code-check/test_action.py": (LINUX_CODE, None),
    "python3 actions/test_ruling_kind_records_dir.py": (LINUX_CODE, None),
    "python3 janitor/test_sweep.py": (LINUX_CODE_SWEEP, None),
    "python3 janitor/mutate_sweep.py": (LINUX_SWEEP, None),
    "python3 hooks/test_config_watch.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 hooks/test_config_watch_fast_exit.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 hooks/test_shared_names.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 hooks/test_precompact_handoff.py": (None, None),
    "python3 hooks/test_cc_version_check.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 hooks/test_handoff_wave2.py": (None, None),
    "python3 hooks/test_decision_watch.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 hooks/test_reply_judge.py": (None, None),
    "python3 hooks/test_prose_judge.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 hooks/test_sendmessage_state.py": (SCOPE_DOC_DECISIONS, None),
    "python3 hooks/test_refusal_note.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 hooks/test_call_judge.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 hooks/test_question_form.py": (SCOPE_DOC_ANY, None),
    "python3 hooks/test_rm_prompt_answer.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 hooks/test_agent_brief.py": (SCOPE_DOC_AGENTS, None),
    "python3 hooks/test_blind_brief.py": (SCOPE_DOC_SKILLS_AGENTS, None),
    "python3 hooks/test_local_time.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 hooks/test_probe.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 hooks/test_ci_wake.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 hooks/test_feedback_inbox.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 hooks/test_waiting_export.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 hooks/test_daily_note.py": (None, None),
    "python3 hooks/test_nowindow.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 hooks/test_auto_mode_allow.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 hooks/test_stall_watch.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 hooks/test_stall_watch_stop.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 hooks/test_sim_boot_record.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 hooks/test_wrappers.py": (None, None),
    "python3 hooks/test_scratchpad_owner.py": (None, None),
    "python3 hooks/test_checks_never_raise.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 hooks/test_session_start.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 lint/test_report_guard.py": (SCOPE_DOC_ANY, None),
    "python3 lint/test_ste_autofix.py": (LINUX_CODE, None),
    "python3 hooks/test_ruling_home.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 lint/test_ruling_census.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 lint/test_rule_audit.py": (SCOPE_DOC_DECISIONS_RULES, None),
    "python3 lint/test_stale_cites.py": (SCOPE_DOC_ANY, None),
    "python3 lint/test_guard_log_report.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 lint/test_verdict.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 lint/test_wait_pid.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 lint/test_tracked_tree.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 lint/test_test_git.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 lint/test_notes_union_merge.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 lint/test_ci_job.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 lint/test_windows_split.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 lint/test_all_jobs_passed.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 lint/test_ci_scope.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 lint/test_checks_step_scope.py": (None, None),
    "python3 lint/test_rm_shim.py": (LINUX_CODE, None),
    "python3 hooks/test_mutate_shared.py": (None, None),
    "python3 hooks/test_mutate_report.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 hooks/test_mutate_js.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 hooks/test_mutate_replay.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 lint/test_check_landed_dirs.py": (SCOPE_DOC_SKILLS, None),
    "python3 lint/test_settings_matcher.py": (SCOPE_DOC_DECISIONS, None),
    "python3 lint/test_hook_platform_exit.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 lint/test_check_hook_stubs.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 lint/test_check_hook_dup_names.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 lint/test_check_record_slugs.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 lint/test_check_red_run.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 lint/test_find_copies.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 lint/test_find_time_pinned.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 lint/test_check_mod_versions.py": (None, None),
    "python3 lint/test_hook_catalog.py": (SCOPE_DOC_ANY, None),
    "python3 lint/test_layout.py": (None, None),
    "python3 lint/test_label_once.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 lint/test_repo_colour.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 lint/test_retired_repos.py": (SCOPE_DOC_ANY, None),
    "python3 skills/waiting-page/test_stale_pages.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 skills/waiting-page/test_splice.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 lint/test_check_artifact_cites.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 skills/roadmap/test_build.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 lint/test_check_shared_resources.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 lint/test_check_ios_mockup.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 lint/test_compliance_probes.py": (SCOPE_DOC_ANY, None),
    "python3 lint/test_check_claude_md_size.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 lint/test_check_glossary.py": (SCOPE_DOC_ANY, None),
    "python3 lint/test_retired_names.py": (SCOPE_DOC_ANY, None),
    "python3 skills/project-ops/tests/test_scaffold.py": (SCOPE_DOC_SKILLS, None),
    "python3 skills/ios-apps/tests/test_new_app.py": (SCOPE_DOC_SKILLS, None),
    "python3 lint/test_check_ruling_kind.py": (None, None),
    "python3 lint/test_check_silent_undo.py": (SCOPE_DOC_ANY, None),
    "python3 lint/test_check_comment_narration.py": (None, None),
    "python3 lint/test_check_unknown_reads_contract.py": (NO_MD_SCOPE_CONDITION, None),
    "python3 lint/check_unknown_reads_contract.py": (LINUX_CODE, None),
    "python3 lint/test_check_agent_models.py": (SCOPE_DOC_ANY, None),
    "python3 lint/test_agent_push_form.py": (SCOPE_DOC_ANY, None),
    "python3 lint/test_check_skill_model_rows.py": (None, None),
    "python3 lint/test_no_window_spawn.py": (None, None),
    "pwsh -NoProfile -File install.test.ps1": (LINUX_CODE, None),
    "python3 janitor/test_session_end_sweep.py": (LINUX_CODE, None),
    "python3 janitor/test_install_launchd.py": (LINUX_CODE, None),
    "python3 janitor/test_install_schtasks.py": (LINUX_CODE, None),
    "python3 actions/ste-lint/test_action.py": (SCOPE_DOC_ANY, None),
    "python3 actions/playwright-setup/test_action.py": (NO_MD_SCOPE_CONDITION, None),
    "node actions/stamp/test_stamp.mjs": (NO_MD_SCOPE_CONDITION, None),
    "node lint/test_scanner_traps.mjs": (NO_MD_SCOPE_CONDITION, None),
    "bash actions/stamp/test_action.sh": (NO_MD_SCOPE_CONDITION, "bash"),
    "bash actions/all-jobs-passed/test_action.sh": (LINUX_CODE, "bash"),
    "bash actions/ci-alarm/test_action.sh": (LINUX_CODE, "bash"),
    "python3 actions/ci-alarm/test_clear_rule.py": (LINUX_CODE, "bash"),
    "python3 actions/ci-done-comment/test_comment.py": (LINUX_CODE, "bash"),
    "bash actions/ruling-kind/test_action.sh": (LINUX_CODE, "bash"),
    "python3 actions/readme-links/test_readme_links.py": (LINUX_CODE, "bash"),
    "bash githooks/main-ref/test_hook.sh": (LINUX_CODE, "bash"),
    "node --test testing/skip-locally-fail-in-ci.test.mjs": (LINUX_CODE, "bash"),
    "python3 merge/test_launch.py": (LINUX_CODE, None),
    "python3 merge/test_merge.py": (LINUX_CODE, None),
    "python3 merge/test_cmd.py": (LINUX_CODE, None),
    "python3 merge/test_repaired_merges.py": (LINUX_CODE, None),
    "python3 merge/test_lane_lint.py": (LINUX_CODE, None),
    "python3 merge/test_idle_lanes.py": (LINUX_CODE, None),
    "sh merge/test_install_from_main.sh": (LINUX_CODE, None),
    "sh hooks/test_install_src.sh": (LINUX_CODE, None),
    "sh hooks/test_cloud_setup.sh": (LINUX_CODE, None),
    "bash .github/scripts/mod-tests.sh": (LINUX_MODS, "bash"),
}

# The macOS split. R61 (owner pick b, 15:29 CST Nov 12): checks-macos runs one mac-tagged slice of the guard suite
# (GUARD_TESTS=macos-slice, no GUARD_SHARD), and no other macOS job runs the guard suite.
MACOS_SPLIT = ("checks-macos", "checks-macos-b")
MACOS_GUARD = "python3 hooks/test_guard.py"
MACOS_SLICE_JOB = "checks-macos"
MACOS_SLICE_ENV = {"GUARD_TESTS": "macos-slice"}
# A macOS job whose runs-on is an expression that reads the scope job's mac_runner output, a list of macOS labels from
# mac-runner.py. is_macos counts that job as macOS, so the macOS checks still see it.
# MAC_PICK_RUNS_ON is that runs-on text. The constant that holds it is not on this base, so the fixture keeps its own copy.
MAC_PICK = "needs.scope.outputs.mac_runner"
MAC_PICK_RUNS_ON = (f"${{{{ (github.event_name == 'pull_request' && github.event.pull_request.head.repo.full_name != github.repository) "
                    f"&& fromJSON('[\"macos-latest\"]') || fromJSON({MAC_PICK}) }}}}")
# R61 part 1: a push starts no macOS runner. Each job named here keeps `github.event_name != 'push'` as its job-level if.
MACOS_JOBS = ("shell-macos", "checks-macos", "checks-macos-b")
# R61 part 3: the 03:17 nightly's gate job, and the one scope output it reads (the gate's skip).
NIGHTLY_SKIP_JOB = "nightly-skip"
PUSH_SKIP_JOB = "push-skip"
SCOPE_NEEDS = {NIGHTLY_SKIP_JOB, PUSH_SKIP_JOB}  # scope's if reads each skip job's skip output, so it needs both
# The values the gate's skip output can hold: unset (''), skip (`true`) or run (`false`). A guard predicate must give one answer for all.
SKIP_VALUES = ("", "true", "false")
MAC_OWN = "(needs.scope.outputs.checks_macos == 'true' || github.event_name != 'pull_request') && !cancelled()"
MAC_CODE = f"{MAC_OWN} && needs.scope.outputs.code == 'true'"
MAC_SWEEP = "!cancelled() && needs.scope.outputs.sweep == 'true'"  # the mutation step carries only its sweep flag (R62)
MAC_MODS = f"{MAC_OWN} && needs.scope.outputs.mods == 'true'"
MACOS_SUITES = {
    "python3 hooks/test_guard_load_os.py": (MAC_CODE, None),
    "python3 lint/test_rm_shim.py": (MAC_CODE, None),
    "python3 lint/test_hook_platform_exit.py": (MAC_CODE, None),
    "python3 lint/check_unknown_reads_contract.py": (MAC_CODE, None),
    "python3 janitor/test_sweep.py": (MAC_CODE, None),
    "python3 janitor/mutate_sweep.py": (MAC_SWEEP, None),
    "python3 hooks/test_config_watch.py": (MAC_OWN, None),
    "python3 hooks/test_config_watch_fast_exit.py": (MAC_OWN, None),
    "python3 hooks/test_shared_names.py": (MAC_OWN, None),
    "python3 hooks/test_precompact_handoff.py": (MAC_OWN, None),
    "python3 hooks/test_cc_version_check.py": (MAC_OWN, None),
    "python3 hooks/test_handoff_wave2.py": (MAC_OWN, None),
    "python3 hooks/test_decision_watch.py": (MAC_OWN, None),
    "python3 hooks/test_reply_judge.py": (MAC_OWN, None),
    "python3 hooks/test_prose_judge.py": (MAC_OWN, None),
    "python3 hooks/test_sendmessage_state.py": (MAC_OWN, None),
    "python3 hooks/test_refusal_note.py": (MAC_OWN, None),
    "python3 hooks/test_call_judge.py": (MAC_OWN, None),
    "python3 hooks/test_question_form.py": (MAC_OWN, None),
    "python3 hooks/test_rm_prompt_answer.py": (MAC_OWN, None),
    "python3 hooks/test_agent_brief.py": (MAC_OWN, None),
    "python3 hooks/test_blind_brief.py": (MAC_OWN, None),
    "python3 hooks/test_local_time.py": (MAC_OWN, None),
    "python3 hooks/test_probe.py": (MAC_OWN, None),
    "python3 hooks/test_ci_wake.py": (MAC_OWN, None),
    "python3 hooks/test_feedback_inbox.py": (MAC_OWN, None),
    "python3 hooks/test_waiting_export.py": (MAC_OWN, None),
    "python3 hooks/test_daily_note.py": (MAC_OWN, None),
    "python3 hooks/test_stall_watch.py": (MAC_OWN, None),
    "python3 hooks/test_sim_boot_record.py": (MAC_OWN, None),
    "python3 hooks/test_wrappers.py": (MAC_OWN, None),
    "python3 hooks/test_session_start.py": (MAC_OWN, None),
    "python3 lint/test_report_guard.py": (MAC_OWN, None),
    "python3 hooks/test_ruling_home.py": (MAC_OWN, None),
    "python3 lint/test_ruling_census.py": (MAC_OWN, None),
    "python3 lint/test_verdict.py": (MAC_OWN, None),
    "python3 lint/test_wait_pid.py": (MAC_OWN, None),
    "python3 janitor/test_session_end_sweep.py": (MAC_CODE, None),
    "python3 janitor/test_install_launchd.py": (MAC_CODE, None),
    "python3 janitor/test_install_schtasks.py": (MAC_CODE, None),
    "node actions/stamp/test_stamp.mjs": (MAC_OWN, None),
    "bash actions/stamp/test_action.sh": (MAC_OWN, None),
    "bash .github/scripts/mod-tests.sh": (MAC_MODS, "bash"),
}


def all_jobs(text):
    """{job: {"os", "if": job-level if or None, "needs": raw needs text or None, "steps": [{key: value}]}}.

    Step keys sit at 8 spaces, or inline after `- ` at 6. Block scalars (`run: |`) read as "|".
    """
    jobs, job, in_jobs = {}, None, False
    for line in text.splitlines():
        if re.match(r"^jobs:\s*$", line):
            in_jobs = True
        elif in_jobs and (m := re.match(r"^  ([\w-]+):\s*$", line)):
            job = jobs[m.group(1)] = {"os": None, "if": None, "needs": None, "steps": []}
        elif not job:
            continue
        elif m := re.match(r"^    (runs-on|if|needs):\s*(\S.*?)\s*$", line):
            job[{"runs-on": "os", "if": "if", "needs": "needs"}[m.group(1)]] = m.group(2)
        elif m := re.match(r"^      - (\w+):\s*(.*?)\s*$", line):
            job["steps"].append({m.group(1): m.group(2)})
        elif (m := re.match(r"^        (\w+):\s*(.*?)\s*$", line)) and job["steps"]:
            job["steps"][-1][m.group(1)] = m.group(2)
        elif (m := re.match(r"^          (\w+):\s*(.*?)\s*$", line)) and job["steps"]:  # an `env:` block key
            if not isinstance(job["steps"][-1].get("env"), dict):
                job["steps"][-1]["env"] = {}
            job["steps"][-1]["env"][m.group(1)] = m.group(2)
    return jobs


def windows_jobs(text):
    return {n: j for n, j in all_jobs(text).items() if j["os"] == "windows-latest"}


# The Windows slices (MERGE_TESTS / GUARD_TESTS=windows-slice) are gone (R62): the ready-PR shards run every case. A step
# that still runs one is named by its key, so the pins can say it is gone. The slice step has the same `run:` as the full step.
SLICE = "python merge/test_merge.py [windows-slice]"
GUARD_CMD = "python hooks/test_guard.py"
GUARD_SLICE = "python hooks/test_guard.py [windows-slice]"
GUARD_JOB = "checks-windows-guard"
# A long suite splits across shard jobs: the base job, then `<base>-2` to `<base>-<n>`. The full step of each
# carries SHARD_VAR[base]=<i>/<n> in its step env, and the n values cover 1 to n once each, so every case runs
# once. A shard job past the first runs on a ready pull_request and never on a draft. Its if is the draft guard, and its
# steps carry the base job's scope condition, so a run with no flag for the base job runs no shard.
SHARD_VAR = {"checks-windows-guard": "GUARD_SHARD", "checks-windows-merge": "MERGE_SHARD"}
SHARD_CMD = {"checks-windows-guard": "python hooks/test_guard.py", "checks-windows-merge": "python merge/test_merge.py"}
SHARD_JOB_IF = "${{ github.event_name != 'pull_request' || !github.event.pull_request.draft }}"


def shard_base(name):
    """The base job a shard job belongs to (`checks-windows-guard-2` -> `checks-windows-guard`), or None."""
    m = re.fullmatch(r"(.+)-([2-9]|[1-9][0-9]+)", name)
    return m.group(1) if m and m.group(1) in SHARD_VAR else None


# The guard mutation test moves off `checks` (Linux) to its own Linux job (cut F).
MUTATE_CMD = "python3 hooks/mutate_guard.py"
MUTATE_JOB = "checks-mutate-guard"
MUTATE_JOBS = [MUTATE_JOB, MUTATE_JOB + "-b", MUTATE_JOB + "-c"]  # shard i of 3 runs MUTATE_SHARD=i/3
# The bin/shoot suite and its browser install have their own Linux job, off the `checks` lint job.
SHOOT_CMD = 'NODE_PATH="$PWD/.github/shoot/node_modules" node --test lint/test_shoot.mjs'
SHOOT_JOB = "checks-shoot"
# The export suite runs in SHOOT_JOB too: its picture cases run check_designs.mjs in Playwright, and loadPlaywright reads NODE_PATH.
EXPORT_CMD = 'NODE_PATH="$PWD/.github/shoot/node_modules" python3 skills/waiting-page/test_export_page.py'
EXPORT_IF = "needs.scope.outputs.shoot == 'true' || github.event_name != 'pull_request'"
# The waiting page suite has its own job, so SHOOT_JOB keeps its cap (decision ci-job-caps). ROADMAP_CMD stays in SHOOT_JOB.
WAITING_PAGE_CMD = 'NODE_PATH="$PWD/.github/shoot/node_modules" node --test skills/waiting-page/tests/page.test.mjs skills/waiting-page/tests/test_check_designs.mjs'
WAITING_PAGE_JOB = "checks-waiting-page"
ROADMAP_CMD = 'NODE_PATH="$PWD/.github/shoot/node_modules" node --test skills/roadmap/tests/page.test.mjs'
# The scope flag each job skips on when the flag is not its own name.
FLAG_OF = {GUARD_JOB: "guard", MUTATE_JOB: "guard", SHOOT_JOB: "shoot", "checks-macos-b": "checks_macos",
           "checks-guard-2": "checks_guard"}
FLAG_OF[WAITING_PAGE_JOB] = "shoot"
FLAG_OF.update({name: "guard" for name in MUTATE_JOBS})
# The lint jobs run on every PR with no scope condition: the Linux pair, read from its one home CHECKS_SUITE_JOBS.
LINT_JOBS = CHECKS_SUITE_JOBS
# all-jobs-passed is the one required check. Its needs are checked in lint/test_all_jobs_passed.py.
ALL_JOBS_PASSED_JOB = "all-jobs-passed"


def key(st):
    """A step's run command; a test_merge or test_guard step with its slice env reads as its SLICE."""
    run = st.get("run")
    env = st.get("env") if isinstance(st.get("env"), dict) else {}
    if run == "python merge/test_merge.py" and "MERGE_TESTS" in env:
        return SLICE
    if run == GUARD_CMD and "GUARD_TESTS" in env:
        return GUARD_SLICE
    return run


def shard_problems(cmd, homes):
    """A suite in several jobs is one shard family: its base job and `<base>-2`..`<base>-<n>`, each full step with
    SHARD_VAR=<i>/<n>, the values 1/n to n/n once each. [] when the homes are such a family."""
    names = [n for n, _ in homes]
    bases = {shard_base(n) or n for n in names}
    base = next(iter(bases))
    if len(bases) != 1 or base not in SHARD_VAR or SHARD_CMD[base] != cmd:
        return [f"{cmd!r} runs {len(homes)} times on windows-latest: {names}"]
    n = len(homes)
    want_names = {base} | {f"{base}-{i}" for i in range(2, n + 1)}
    got = sorted((st.get("env") or {}).get(SHARD_VAR[base], "") if isinstance(st.get("env"), dict) else ""
                 for _, st in homes)
    want = sorted(f"{i}/{n}" for i in range(1, n + 1))
    problems = []
    if set(names) != want_names or len(names) != n:
        problems.append(f"{cmd!r} shard jobs are {names}, want {sorted(want_names)}")
    if got != want:
        problems.append(f"{cmd!r} {SHARD_VAR[base]} values are {got}, want {want}: a case would run twice or never")
    return problems


def placement_problems(text):
    """Strings naming each suite not run exactly once, or too few carrying jobs."""
    wj = windows_jobs(text)
    jobs = {n: [key(st) for st in j["steps"]] for n, j in wj.items()}
    problems = []
    # R62: the ready-PR shards run every case, so the Windows merge slice has no step.
    homes = [n for n, runs in jobs.items() for r in runs if r == SLICE]
    if homes:
        problems.append(f"{SLICE!r} runs {len(homes)} times on windows-latest: {homes}, want 0")
    for cmd in REQUIRED:
        homes = [(n, st) for n, j in wj.items() for st in j["steps"] if key(st) == cmd]
        if len(homes) > 1:
            problems += shard_problems(cmd, homes)
        elif len(homes) != 1 or any(isinstance(st.get("env"), dict) and SHARD_VAR.get(n) in st["env"]
                                    for n, st in homes):
            problems.append(f"{cmd!r} runs {len(homes)} times on windows-latest: {[n for n, _ in homes]}"
                            + (" (a lone shard value)" if homes else ""))
    carrying = [n for n, runs in jobs.items() if any(r in REQUIRED for r in runs)]
    if len(carrying) < MIN_JOBS:
        problems.append(f"{len(carrying)} windows-latest jobs carry the suites, need {MIN_JOBS}: {carrying}")
    return problems


# Steps whose `shell:` is pinned. Any other REQUIRED step must set none.
SHELL = {"sh hooks/test_install_windows.sh": "bash", "bash actions/stamp/test_action.sh": "bash"}
# Steps whose own condition (the part after the scope condition) is pinned: the mutation test runs on every event, a ready
# pull_request included, and on its scope flag.
IF_PIN = {"python janitor/mutate_sweep.py":
          "${{ !cancelled() && needs.scope.outputs.sweep == 'true' }}",
          # The full merge suite runs on a ready pull_request whatever the flags say, and on push when code changed (R62).
          "python merge/test_merge.py": "${{ !cancelled() && (needs.scope.outputs.code == 'true' || github.event_name == 'pull_request') }}",
          # The full guard suite: the same rule as the merge suite (R62). Neither suite has a slice step.
          GUARD_CMD: "${{ !cancelled() && (needs.scope.outputs.code == 'true' || github.event_name == 'pull_request') }}"}


FLAGS = ["checks_windows", "checks_windows_merge", "checks_windows_rest", "checks_macos", "shell_macos", "pointer_windows",
         "code", "guard", "sweep", "shoot"]


def eval_if(expr, event, flag_value, draft=False, nightly_skip="", push_skip=""):
    """Evaluate an `if:` (a job's, a step's or a scope condition) for an event with every scope output set to flag_value and
    github.event.pull_request.draft set to draft. Reads only !cancelled(), success(), always(), &&, ||, !, parentheses,
    == and != on github.event_name, github.event.pull_request.draft, needs.scope.outputs.*, and the skip output of the two
    skip jobs (nightly_skip and push_skip: the value given, '' when unset, as GitHub reads an output no step set)."""
    e = expr.strip()
    if e.startswith("${{") and e.endswith("}}"):
        e = e[3:-2]
    e = e.replace("github.event.pull_request.draft", repr(draft))
    e = e.replace("!cancelled()", "True").replace("success()", "True").replace("always()", "True")
    e = e.replace("&&", " and ").replace("||", " or ")
    e = e.replace("github.event_name", repr(event))
    e = re.sub(r"needs\.scope\.outputs\.\w+", repr(flag_value), e)
    # Only the two skip jobs' skip outputs are read. Any other job's output stays unread, so the reader raises on it, as before.
    e = re.sub(rf"needs\.{re.escape(NIGHTLY_SKIP_JOB)}\.outputs\.skip\b", repr(nightly_skip), e)
    e = re.sub(rf"needs\.{re.escape(PUSH_SKIP_JOB)}\.outputs\.skip\b", repr(push_skip), e)
    e = re.sub(r"!(?!=)", " not ", e)
    return bool(eval(e, {"__builtins__": {}}))


def yaml_scalar(raw):
    """A YAML value without its trailing comment or outer quotes. `#` starts a comment only after a space and outside
    quotes, so `'a # b'` and `${{ x == '#' }}` keep their `#`, and a lone quote in plain text (`Don't`) is text."""
    s = (raw or "").strip()
    if s[:1] in ("'", '"'):
        end = s.find(s[0], 1)
        return s[1:end] if end != -1 else s
    m = re.search(r"(?:^|\s)#", s)
    return (s[:m.start()] if m else s).rstrip()


def unwrap(raw):
    """A value's expression with `${{ }}` removed, or None when the value is absent."""
    if raw is None:
        return None
    s = yaml_scalar(raw)
    return s[3:-2].strip() if s.startswith("${{") and s.endswith("}}") else s


def step_if(st):
    """A step's `if:` expression, or None when the step has none."""
    return unwrap(st.get("if"))


def paren_prefix(expr):
    """X when expr reads `(X) && ...` with X closed by its own parenthesis, else None. A paren inside single quotes is text."""
    if not expr or expr[0] != "(":
        return None
    depth, quoted = 0, False
    for i, ch in enumerate(expr):
        if ch == "'":
            quoted = not quoted
        elif quoted:
            continue
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return expr[1:i] if expr[i + 1:].startswith(" && ") else None
    return None


def top_level_or(expr):
    """True when expr has a `||` outside parentheses and outside single quotes. A quote that never closes makes the
    rest unreadable, so that counts as True too."""
    depth, quoted = 0, False
    for i, ch in enumerate(expr):
        if ch == "'":
            quoted = not quoted
        elif quoted:
            continue
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and expr.startswith("||", i):
            return True
    return quoted


def scope_condition_rest(expr, scope_condition):
    """What a step's `if` adds to the scope condition: "" for the bare scope condition, E for `(scope condition) && E`, None when the step lacks the scope condition
    or E has a `||` outside parentheses, since that lets the step run outside the scope condition."""
    if scope_condition is None or expr is None:
        return None
    if expr == scope_condition:
        return ""
    lead = f"({scope_condition}) && "
    rest = expr[len(lead):] if expr.startswith(lead) else ""
    if not rest or top_level_or(rest):
        return None
    return rest


def read_scope_condition(job):
    """G, the scope condition a scoped job's steps carry. Each step with an `if` gives a candidate: its `(X)` prefix, else the whole
    if. None when no step carries an `if`, or when the candidates differ."""
    cands = {paren_prefix(expr) or expr for expr in map(step_if, job["steps"]) if expr is not None}
    return cands.pop() if len(cands) == 1 else None


def step_rest(st, scope_condition):
    """A step's own condition E: what the scope condition leaves of the step's if. "" for the bare scope condition, None when
    the step lacks the scope condition. Every scoped step carries it, a shard's included (R62)."""
    return scope_condition_rest(step_if(st), scope_condition)


def scope_condition_property_problems(name, scope_condition, flag=None):
    """G keeps the scope condition's rules: it reads the job's own scope flag, it is one disjunction (a `&&` in it means a step's E
    was not parenthesised, so E runs inside the scope condition), it is true on push, schedule and dispatch with every flag false,
    true on pull_request with every flag true, and false on pull_request with every flag false."""
    own = flag or name.replace("-", "_")
    problems = []
    if f"needs.scope.outputs.{own}" not in scope_condition:
        problems.append(f"{name}: scope condition does not read needs.scope.outputs.{own}: {scope_condition}")
    if "&&" in scope_condition:
        problems.append(f"{name}: scope condition has &&, so a step's condition is not parenthesised: {scope_condition}")
    try:
        for ev in ("push", "schedule", "workflow_dispatch"):
            if not eval_if(scope_condition, ev, "false"):
                problems.append(f"{name}: scope condition skips on {ev}: {scope_condition}")
        if not eval_if(scope_condition, "pull_request", "true"):
            problems.append(f"{name}: scope condition skips on pull_request with every flag true: {scope_condition}")
        if eval_if(scope_condition, "pull_request", "false"):
            problems.append(f"{name}: scope condition runs on pull_request with every flag false: {scope_condition}")
    except Exception as ex:
        problems.append(f"{name}: scope condition is not in the allowed form ({ex!r}): {scope_condition}")
    return problems


def scope_condition_step_problems(name, job, scope_condition):
    """Every step of a scoped job carries the scope condition: bare, or as `(scope condition) && E`."""
    return [f"{name}: step {st.get('name') or st.get('uses') or st.get('run')} lacks the scope condition: {step_if(st)}"
            for st in job["steps"] if scope_condition_rest(step_if(st), scope_condition) is None]


def draft_guard_only(expr):
    """True when a job-level `if:` holds only the draft guard (ci-hygiene steps 11 and 19): it skips a draft PR, runs on a
    ready PR and on push, and reads no scope flag, so its answer does not change with the flags. Any other expression is False.
    It also reads no other job's output: the answer must match for every skip value (SKIP_VALUES)."""
    e = unwrap(expr)
    if not e:
        return False
    try:
        return all(eval_if(e, event, flag, draft=draft, nightly_skip=nightly_skip) == want for nightly_skip in SKIP_VALUES for event, flag, draft, want in (
            ("pull_request", "false", True, False),
            ("pull_request", "false", False, True),
            ("pull_request", "true", False, True),
            ("push", "false", False, True),
            ("push", "true", False, True)))
    except Exception:
        return False


# R62: the full Windows suite runs on a ready pull_request whatever the flags say. Its steps carry the draft guard, bare (checkout and
# setup) or as `(draft guard) && E`. A suite step's E reads code at most, the push gate, and never the job's own flag.
DRAFT_GUARD = "github.event_name != 'pull_request' || !github.event.pull_request.draft"
SWEEP_STEP_CMDS = ("python3 janitor/mutate_sweep.py", "python janitor/mutate_sweep.py")
SWEEP_JOBS = ("checks-macos", "checks-windows-sweep")


def sweep_union(own):
    """The condition a sweep job's checkout and setup carry: its own flag, the sweep flag, or an event other than pull_request (R62)."""
    return f"needs.scope.outputs.{own} == 'true' || needs.scope.outputs.sweep == 'true' || github.event_name != 'pull_request'"


def full_suite_problems(name, job):
    """R62 for a full-suite job (full_suite_job). Every step carries the draft guard, bare or as `(draft guard) && E`. A suite
    step keeps !cancelled(), and its E reads code at most (the push gate on the steps that have one). No step reads the job's
    own flag: a ready pull_request runs the suite whatever the flags say."""
    problems = []
    for st in job["steps"]:
        expr = step_if(st)
        label = st.get("name") or st.get("uses") or st.get("run")
        rest = scope_condition_rest(expr, DRAFT_GUARD)
        if rest is None:
            problems.append(f"{name}: step {label} lacks the draft guard: {expr}")
            continue
        if st.get("uses"):
            continue  # checkout and setup carry the draft guard alone
        if "!cancelled()" not in rest:
            problems.append(f"{name}: step {label} lacks !cancelled(): {expr}")
        flags = set(re.findall(r"needs\.scope\.outputs\.(\w+)", rest))
        if name in (GUARD_JOB, "checks-windows-merge") and "code" not in flags:
            problems.append(f"{name}: step {label} does not read code, so a push runs the suite with no code change: {expr}")
        if flags - {"code"}:
            problems.append(f"{name}: step {label} reads scope flags {sorted(flags - {'code'})}, want only code: {expr}")
    return problems


def sweep_job_problems(name, job, flag=None):
    """R62 for a job with the janitor sweep mutation step. Its suite steps carry one scope condition G, which reads the job's own
    flag and keeps the property rules. The mutation step carries only `!cancelled() && sweep` (pinned by IF_PIN and MACOS_SUITES).
    Checkout and setup carry the sweep union, so a PR that sets only the sweep flag still checks out."""
    own = flag or name.replace("-", "_")
    problems = []
    suite = [st for st in job["steps"] if not st.get("uses") and key(st) not in SWEEP_STEP_CMDS]
    setup = [st for st in job["steps"] if st.get("uses")]
    conds = {paren_prefix(e) or e for e in map(step_if, suite) if e is not None}
    if len(conds) != 1:
        return problems + [f"{name}: its suite steps carry no one scope condition (none carries one, or they disagree)"]
    scope_condition = conds.pop()
    problems += scope_condition_property_problems(name, scope_condition, flag)
    for st in suite:
        if scope_condition_rest(step_if(st), scope_condition) is None:
            problems.append(f"{name}: step {st.get('name') or st.get('run')} lacks the scope condition: {step_if(st)}")
    for st in setup:
        if step_if(st) != sweep_union(own):
            problems.append(f"{name}: {st.get('uses')} carries {step_if(st)!r}, want {sweep_union(own)!r}")
    for st in job["steps"]:
        if key(st) in SWEEP_STEP_CMDS and "needs.scope.outputs.sweep == 'true'" not in (step_if(st) or ""):
            problems.append(f"{name}: the sweep mutation step does not read the sweep flag: {step_if(st)}")
    return problems


def job_check_problems(name, job, flag=None):
    """`needs: scope`. A shard past the first keeps the event job-level if (SHARD_JOB_IF) and nothing else. The lint jobs
    (LINT_JOBS) have no scope condition. A lint or scoped job's job-level if, if any, is the draft guard (draft_guard_only).
    A scoped job's scope condition G is the one its steps carry (read_scope_condition), every step carries G
    (scope_condition_step_problems), and G keeps the scope condition rules (scope_condition_property_problems). `flag` names
    the scope output for a job whose flag is not its own name (FLAG_OF)."""
    problems = []
    if not re.fullmatch(r"\[?\s*scope\s*\]?", job["needs"] or ""):
        problems.append(f"{name}: needs is {job['needs']}, want scope")
    expr = job["if"]
    if shard_base(name):
        return problems + ([] if expr == SHARD_JOB_IF else [f"{name}: shard job if is {expr}, want {SHARD_JOB_IF}"])
    if name in LINT_JOBS:  # they run on every PR: no scope condition, and a job-level if only when it is the draft guard
        return problems + ([] if expr is None or draft_guard_only(expr) else [f"{name}: job-level if: {expr}"])
    # R61 part 1: a macOS job may keep the push guard as its job-level if (a step-level skip still starts its runner).
    if expr is not None and not draft_guard_only(expr) and not (name in MACOS_JOBS and push_guard_only(expr)):
        return problems + [f"{name}: scoped job keeps a job-level if, its scope condition belongs in its steps: {expr}"]
    if full_suite_job(name):
        return problems + full_suite_problems(name, job)
    if name in SWEEP_JOBS:
        return problems + sweep_job_problems(name, job, flag)
    scope_condition = read_scope_condition(job)
    if scope_condition is None:
        return problems + [f"{name}: its steps carry no one scope condition (none carries one, or they disagree)"]
    return problems + scope_condition_property_problems(name, scope_condition, flag) + scope_condition_step_problems(name, job, scope_condition)


def scope_needs_of(text):
    """The job names scope needs: its block list under `needs:`, else its inline value. Empty when it needs none or has no scope."""
    m_block = re.search(r"^  scope:\s*$(.*?)(?=^  [\w-]+:\s*$|\Z)", text, re.M | re.S)
    if not m_block:
        return set()
    m = re.search(r"^    needs:[ \t]*\n((?:      - [\w-]+[ \t]*\n)+)", m_block.group(1), re.M)
    if m:
        return set(re.findall(r"^\s+-\s+([\w-]+)\s*$", m.group(1), re.M))
    return set(re.findall(r"[\w-]+", (all_jobs(text).get("scope") or {}).get("needs") or ""))


def scope_problems(text):
    """A `scope` job on ubuntu with every flag as a job output; every other job passes job_check_problems
    (the lint jobs in LINT_JOBS need scope but run always)."""
    jobs = all_jobs(text)
    problems = []
    sc = jobs.get("scope")
    if not sc:
        return ["no scope job"]
    if not (sc["os"] or "").startswith("ubuntu"):
        problems.append(f"scope runs on {sc['os']}, want ubuntu")
    got_needs = scope_needs_of(text)
    if got_needs != SCOPE_NEEDS:
        problems.append(f"scope has needs {sorted(got_needs)}, want {sorted(SCOPE_NEEDS)}")
    block = re.search(r"^  scope:\s*$(.*?)(?=^  [\w-]+:\s*$|\Z)", text, re.M | re.S).group(1)
    for f in FLAGS:
        if not re.search(rf"^      {f}:\s*\S", block, re.M):
            problems.append(f"scope job has no output {f}")
    for name, job in jobs.items():
        # ci-done is the fan-in that comments when a run ends red: it needs every job, not scope
        # alone (actions/ci-done-comment/test_comment.py checks its needs and if). The two skip jobs have their own checks.
        if name not in ("scope", "ci-done", ALL_JOBS_PASSED_JOB, NIGHTLY_SKIP_JOB, PUSH_SKIP_JOB):
            problems += job_check_problems(name, job, FLAG_OF.get(name))
    return problems


def hardening_problems(text):
    """A carrying job has `needs: scope`, its scope condition in its steps (job_check_problems) and setup-python; a REQUIRED step
    keeps `!cancelled()`, its pinned shell and its pinned condition (the part after the scope condition)."""
    problems = []
    n = text.count("MERGE_TESTS")  # no merge slice step (R62), so no mention: a job, workflow or $GITHUB_ENV copy would slice a run.
    if n != 0:
        problems.append(f"MERGE_TESTS appears {n} times in checks.yml, want 0 (no merge slice step)")
    # A shard value outside a full step's own env (job, workflow or $GITHUB_ENV) would cut that suite's cases in every run.
    for var in SHARD_VAR.values():
        homes = sum(1 for j in all_jobs(text).values() for st in j["steps"]
                    if isinstance(st.get("env"), dict) and var in st["env"]
                    and (key(st) in REQUIRED or st.get("run") == MACOS_GUARD))
        mentions = sum(strip_comment(line).count(var) for line in text.splitlines())  # a comment that names the var is no home
        if mentions != homes:
            problems.append(f"{var} appears {mentions} times in checks.yml, want {homes} (once per shard step's env)")
    for name, job in windows_jobs(text).items():
        steps = job["steps"]
        if not any(key(st) in REQUIRED for st in steps):
            continue
        problems += job_check_problems(name, job, FLAG_OF.get(name))
        if not any(st.get("uses", "").startswith("actions/setup-python@") for st in steps):
            problems.append(f"{name}: no setup-python")
        for st in steps:
            cmd = key(st)
            if cmd not in REQUIRED:
                continue
            if "!cancelled()" not in (step_if(st) or ""):
                problems.append(f"{name}: {cmd!r} if lacks !cancelled(): {step_if(st)}")
            own_if = step_if(st) if cmd in SWEEP_STEP_CMDS else step_rest(st, read_scope_condition(job))  # the sweep step has no scope condition
            if cmd in IF_PIN and own_if != unwrap(IF_PIN[cmd]):
                problems.append(f"{name}: {cmd!r} condition is not the pinned text: {step_if(st)}")
            if st.get("shell") != SHELL.get(cmd):
                problems.append(f"{name}: {cmd!r} shell is {st.get('shell')}, want {SHELL.get(cmd)}")
    return problems


def guard_problems(text):
    """Cut F. The guard suite has its own windows-latest job, GUARD_JOB. It runs the full suite on a ready pull_request whatever
    the flags say, and on push when code changed, and has no slice step (R62). No other Windows job runs the guard suite."""
    jobs = windows_jobs(text)
    if GUARD_JOB not in jobs:
        return [f"no windows-latest job named {GUARD_JOB}"]
    problems = []
    for name, job in jobs.items():
        if name not in (GUARD_JOB, ) and shard_base(name) != GUARD_JOB and any(
                key(st) in (GUARD_CMD, GUARD_SLICE) for st in job["steps"]):
            problems.append(f"{name} runs the guard suite; it belongs to {GUARD_JOB} and its shard jobs alone")
        if shard_base(name) and any(key(st) in (SLICE, GUARD_SLICE) for st in job["steps"]):
            problems.append(f"{name} runs a slice; the slice belongs to the base job, the required check")
    job = jobs[GUARD_JOB]
    problems += job_check_problems(GUARD_JOB, job, FLAG_OF[GUARD_JOB])
    steps = {}
    for st in job["steps"]:
        steps.setdefault(key(st), st)
    if GUARD_CMD not in steps:
        problems.append(f"{GUARD_JOB} has no step {GUARD_CMD!r}")
    if GUARD_CMD in steps and step_rest(steps[GUARD_CMD], read_scope_condition(job)) != unwrap(IF_PIN[GUARD_CMD]):
        problems.append(f"{GUARD_JOB}: full guard condition is not the pinned text: {step_if(steps[GUARD_CMD])}")
    # R62: the ready-PR shards run every case, so the Windows guard slice has no step.
    if GUARD_SLICE in steps:
        problems.append(f"{GUARD_JOB} still runs {GUARD_SLICE!r}: the shards cover every case on pull_request")
    # One mention per slice step's env, and no other: the Windows slice (GUARD_JOB) and the macOS slice (R61, MACOS_SLICE_JOB).
    g = text.count("GUARD_TESTS")
    homes = sorted(n for n, j in all_jobs(text).items() for st in j["steps"] if "GUARD_TESTS" in (st.get("env") or {}))
    if g != len(homes) or any(h not in (GUARD_JOB, MACOS_SLICE_JOB) for h in homes):
        problems.append(f"GUARD_TESTS appears {g} times in checks.yml, in {homes}: want one slice step's env per slice, "
                        f"in {GUARD_JOB} or {MACOS_SLICE_JOB}")
    # CI runs the whole guard suite. A GUARD_FAMILY here would make CI run one family and call it green.
    f = text.count("GUARD_FAMILY")
    if f:
        problems.append(f"GUARD_FAMILY appears {f} times in checks.yml, want 0 (CI runs every case)")
    return problems


def mutate_problems(text):
    """Cut F. The guard mutation test runs in the MUTATE_JOBS shards on Linux, one shard each (MUTATE_SHARD=i/3), and in no other job."""
    jobs = all_jobs(text)
    homes = [n for n, j in jobs.items() for st in j["steps"] if st.get("run") == MUTATE_CMD]
    problems = []
    if sorted(homes) != sorted(MUTATE_JOBS):
        problems.append(f"{MUTATE_CMD!r} runs in {homes}, want exactly {MUTATE_JOBS!r}")
    for index, name in enumerate(MUTATE_JOBS, start=1):
        if name not in jobs:
            continue
        if not (jobs[name]["os"] or "").startswith("ubuntu"):
            problems.append(f"{name} runs on {jobs[name]['os']}, want ubuntu-latest")
        shards = [yaml_scalar(str((st.get("env") or {}).get("MUTATE_SHARD", ""))) for st in jobs[name]["steps"] if st.get("run") == MUTATE_CMD]
        if shards != [f"{index}/{len(MUTATE_JOBS)}"]:
            problems.append(f"{name}: the mutate step sets MUTATE_SHARD {shards}, want ['{index}/{len(MUTATE_JOBS)}']")
    return problems


def shoot_problems(text):
    """The shoot suite runs in SHOOT_JOB on Linux and in no other job. Every step of that job carries the scope condition,
    and the suite's own step carries the scope condition alone, so no step can skip the suite and read green. No other
    job installs a browser. A red SHOOT_JOB blocks a merge through all-jobs-passed's needs (test_all_jobs_passed.py)."""
    jobs = all_jobs(text)
    homes = [n for n, j in jobs.items() for st in j["steps"] if st.get("run") == SHOOT_CMD]
    problems = []
    if homes != [SHOOT_JOB]:
        problems.append(f"{SHOOT_CMD!r} runs in {homes}, want exactly [{SHOOT_JOB!r}]")
    job = jobs.get(SHOOT_JOB)
    if job:
        if not (job["os"] or "").startswith("ubuntu"):
            problems.append(f"{SHOOT_JOB} runs on {job['os']}, want ubuntu-latest")
        scope_condition = read_scope_condition(job)
        problems += scope_condition_step_problems(SHOOT_JOB, job, scope_condition)
        problems += [f"{SHOOT_JOB}: the suite step adds its own condition, it must carry the scope condition alone: {step_if(st)}"
                     for st in job["steps"] if st.get("run") == SHOOT_CMD and step_rest(st, scope_condition) != ""]
    # The raw job text, so an install inside a `run: |` block counts too.
    installs = [n for n in jobs if n != SHOOT_JOB and "playwright install" in (job_block(text, n) or "")]
    if installs:
        problems.append(f"a browser install runs outside {SHOOT_JOB}: {installs}")
    return problems


def export_suite_problems(text):
    """The export suite runs in SHOOT_JOB and in no other job, as EXPORT_CMD, with its `if:` and `shell:` pinned (EXPORT_IF, bash)
    and no env. Its picture cases need the Playwright that only SHOOT_JOB installs, so a copy elsewhere would fail there."""
    named = [n for n in all_jobs(text) for st in step_blocks(job_block(text, n))
             if any("test_export_page.py" in ln for ln in run_lines(st))]
    if named != [SHOOT_JOB]:
        return [f"the export suite runs in {named}, want exactly [{SHOOT_JOB!r}]"]
    homes = split_homes(text, [SHOOT_JOB], EXPORT_CMD)
    if len(homes) != 1:
        return [f"{SHOOT_JOB}: no step runs {EXPORT_CMD!r}, so the export suite's run line is not the pinned one"]
    return pin_problems(SHOOT_JOB, homes[0][1], EXPORT_CMD, EXPORT_IF, "bash")


def waiting_page_problems(text):
    """The waiting page suite runs in WAITING_PAGE_JOB on Linux and in no other job. The roadmap suite runs in SHOOT_JOB
    alone. Every step of WAITING_PAGE_JOB carries the scope condition alone (step_rest), so no step can add a condition that
    skips it and read green. The condition's form is scope_problems'. Named failure: a suite in the wrong job, in two, or in
    none; a step that adds to or lacks the scope condition."""
    jobs = all_jobs(text)
    problems = []
    for cmd, want in ((WAITING_PAGE_CMD, [WAITING_PAGE_JOB]), (ROADMAP_CMD, [SHOOT_JOB])):
        homes = [job for job, _ in split_homes(text, list(jobs), cmd)]
        if homes != want:
            problems.append(f"{cmd!r} runs in {homes}, want exactly {want}")
    job = jobs.get(WAITING_PAGE_JOB)
    if job:
        if not (job["os"] or "").startswith("ubuntu"):
            problems.append(f"{WAITING_PAGE_JOB} runs on {job['os']}, want ubuntu-latest")
        scope_condition = read_scope_condition(job)
        if scope_condition is None:
            problems.append(f"{WAITING_PAGE_JOB}: its steps carry no one scope condition (none carries one, or they disagree)")
        else:
            problems += [f"{WAITING_PAGE_JOB}: step {st.get('name') or st.get('uses') or st.get('run')} does not carry the scope "
                         f"condition alone: {step_if(st)}" for st in job["steps"] if step_rest(st, scope_condition) != ""]
    return problems


def run_lines(st):
    """A step's run commands: one per non-blank line of its run text, so a block scalar gives each of its lines."""
    return [ln.strip() for ln in (run_body(st) or "").split("\n") if ln.strip()]


def split_homes(text, jobs, cmd):
    """(job, step) for each step of the named jobs that runs `cmd` on one of its lines."""
    return [(job, st) for job in jobs for st in step_blocks(job_block(text, job)) if cmd in run_lines(st)]


def pin_problems(name, st, cmd, want_if, want_shell, want_env=None):
    """A suite's step keeps the `if:` and `shell:` pinned for it, and its env: none, or the shard value (want_env)."""
    got_if, got_env = unwrap(step_key(st, "if")), step_env(st)
    problems = []
    if got_if != want_if:
        problems.append(f"{name}: {cmd!r} if is {got_if!r}, want {want_if!r}")
    if step_key(st, "shell") != want_shell:
        problems.append(f"{name}: {cmd!r} shell is {step_key(st, 'shell')!r}, want {want_shell!r}")
    if got_env != (want_env or {}):
        problems.append(f"{name}: {cmd!r} env is {got_env}, want {want_env or {}}")
    return problems


def job_env_problems(text, jobs):
    """A job-level env reaches every step of its job, so it would override each suite's env."""
    return [f"{j}: job-level env, every step of the job takes it" for j in jobs
            if re.search(r"^    env:", job_block(text, j) or "", re.M)]


def linux_split_problems(text):
    """Each LINUX_SUITES command runs in exactly one LINUX_SPLIT job, with the `if:` and `shell:` pinned for it."""
    problems = job_env_problems(text, LINUX_SPLIT)
    for cmd, (want_if, want_shell) in LINUX_SUITES.items():
        homes = split_homes(text, LINUX_SPLIT, cmd)
        if len(homes) != 1:
            problems.append(f"{cmd!r} runs {len(homes)} times in {LINUX_SPLIT}: {[j for j, _ in homes]}")
        else:
            problems += pin_problems(homes[0][0], homes[0][1], cmd, want_if, want_shell)
    return problems


def macos_split_problems(text):
    """Each MACOS_SUITES command runs in exactly one MACOS_SPLIT job, pinned as above. The guard suite is not in the table:
    macos_slice_problems pins its one slice."""
    problems = job_env_problems(text, MACOS_SPLIT)
    for cmd, (want_if, want_shell) in MACOS_SUITES.items():
        homes = split_homes(text, MACOS_SPLIT, cmd)
        if len(homes) != 1:
            problems.append(f"{cmd!r} runs {len(homes)} times in {MACOS_SPLIT}: {[j for j, _ in homes]}")
        else:
            problems += pin_problems(homes[0][0], homes[0][1], cmd, want_if, want_shell)
    return problems + macos_slice_problems(text)


def is_macos(job):
    """A macOS job: a literal macos-* runs-on, or the runner pick that reads needs.scope.outputs.mac_runner (MAC_PICK)."""
    runs_on = job["os"] or ""
    return runs_on.startswith("macos") or MAC_PICK in runs_on


def macos_slice_problems(text):
    """R61 part 2: the guard suite runs once on macOS, as the mac-tagged slice (GUARD_TESTS=macos-slice) in MACOS_SLICE_JOB,
    with no GUARD_SHARD and on the MAC_CODE condition. No other macOS job runs a guard step, so checks-macos-b runs none."""
    macos = [n for n, j in all_jobs(text).items() if is_macos(j)]
    homes = split_homes(text, macos, MACOS_GUARD)
    problems = []
    if [j for j, _ in homes] != [MACOS_SLICE_JOB]:
        problems.append(f"{MACOS_GUARD!r} runs in {[j for j, _ in homes]}, want exactly one slice in {MACOS_SLICE_JOB} "
                        "and no guard step in any other macOS job")
    for job, st in homes:
        if job == MACOS_SLICE_JOB:
            problems += pin_problems(job, st, MACOS_GUARD, MAC_CODE, None, MACOS_SLICE_ENV)
    return problems


SHOOT_SCOPE = "needs.scope.outputs.shoot == 'true' || github.event_name != 'pull_request'"
SHOOT_IF = f"${{{{ {SHOOT_SCOPE} }}}}"


def shoot_doc(lint_run="ruff", install_if=SHOOT_IF, suite_if=SHOOT_IF, suite_run=SHOOT_CMD,
              runs_on="ubuntu-latest", extra="", shoot_extra="", roadmap_run=None, waiting_run=None, waiting_runs_on="ubuntu-latest",
              waiting_checkout_if=SHOOT_IF, waiting_install_if=SHOOT_IF, waiting_suite_if=SHOOT_IF):
    """A workflow for the shoot and waiting page checkers: the lint job `checks`; SHOOT_JOB with its install and suite, then
    roadmap_run and shoot_extra when set; WAITING_PAGE_JOB with its checkout, install and suite when waiting_run is set. `extra`
    adds steps to the lint job. An `if` of None leaves that step's `if:` out."""
    def if_line(expr):
        return f"        if: {expr}\n" if expr else ""
    install = if_line(install_if)
    suite = if_line(suite_if)
    roadmap = f"      - name: roadmap page suite\n        run: {roadmap_run}\n" if roadmap_run else ""
    waiting = ""
    if waiting_run:
        checkout = MOD_CHECKOUT.split("\n", 1)[0] + "\n"  # the pinned checkout line has one home, MOD_CHECKOUT
        waiting = (f"  {WAITING_PAGE_JOB}:\n    runs-on: {waiting_runs_on}\n    needs: scope\n    steps:\n" + checkout
                   + if_line(waiting_checkout_if)
                   + f"      - name: Install the pinned Playwright and Chromium\n{if_line(waiting_install_if)}"
                   + f"        uses: {PLAYWRIGHT_USES}\n"
                   + f"      - name: waiting page suite\n{if_line(waiting_suite_if)}        run: {waiting_run}\n")
    return ("jobs:\n  checks:\n    runs-on: ubuntu-latest\n    steps:\n"
            f"      - name: lint\n        run: {lint_run}\n" + extra
            + f"  {SHOOT_JOB}:\n    runs-on: {runs_on}\n    needs: scope\n    steps:\n"
            + f"      - name: Install Chromium\n{install}        run: playwright install chromium\n"
            + f"      - name: shoot fixture suite\n{suite}        run: {suite_run}\n" + roadmap + shoot_extra + waiting)


# The Linux guard split: the guard suite runs in two shards, one per job, each with its GUARD_SHARD value. Each shard step is
# pinned as the macOS guard shards are: the scope `if:`, no shell, and the suite's own env plus its shard value.
LINUX_GUARD_SHARD = {"checks-guard": "1/2", "checks-guard-2": "2/2"}
LINUX_GUARD = "python3 hooks/test_guard.py"
LINUX_GUARD_IF = "needs.scope.outputs.checks_guard == 'true' || github.event_name != 'pull_request'"
LINUX_GUARD_ENV = {"NODE_PATH": "${{ github.workspace }}/.github/shoot/node_modules", "GUARD_CHROMIUM": '"1"'}
PLAYWRIGHT_USES = "$/actions/playwright-setup"


def linux_guard_split_problems(text):
    """The Linux guard split: the guard suite runs in exactly the LINUX_GUARD_SHARD jobs, one shard each, and in no other Linux
    job. Each shard step is pinned by pin_problems. A job-level GUARD_SHARD reaches every step of its job, so job_env_problems
    flags it; a workflow-level one is hardening_problems' to flag."""
    problems = job_env_problems(text, tuple(LINUX_GUARD_SHARD))
    linux = [n for n, j in all_jobs(text).items() if (j["os"] or "").startswith("ubuntu")]
    homes = split_homes(text, linux, LINUX_GUARD)
    names = sorted(job for job, _ in homes)
    if names != sorted(LINUX_GUARD_SHARD):
        problems.append(f"{LINUX_GUARD!r} runs in {names}, want one shard in each of {sorted(LINUX_GUARD_SHARD)}")
    for job, st in homes:
        if job in LINUX_GUARD_SHARD:
            problems += pin_problems(job, st, LINUX_GUARD, LINUX_GUARD_IF, None,
                                     {**LINUX_GUARD_ENV, "GUARD_SHARD": LINUX_GUARD_SHARD[job]})
    return problems


def linux_guard_install_problems(text):
    """Each Linux guard shard job installs Playwright, the browser the guard's checker renders with, under the scope `if:`."""
    problems = []
    for job in LINUX_GUARD_SHARD:
        installs = [st for st in step_blocks(job_block(text, job)) if step_key(st, "uses") == PLAYWRIGHT_USES]
        if not installs:
            problems.append(f"{job} has no Playwright install step ({PLAYWRIGHT_USES})")
        for st in installs:
            problems += pin_problems(job, st, PLAYWRIGHT_USES, LINUX_GUARD_IF, None)
    return problems


class WindowsSplit(unittest.TestCase):
    def setUp(self):
        with open(CHECKS, encoding="utf-8") as f:
            self.text = f.read()
        self.assertTrue(windows_jobs(self.text), "parsed no windows-latest job: wrong path or parse")

    def test_each_suite_runs_exactly_once(self):
        bad = [p for p in placement_problems(self.text) if "times" in p]
        self.assertEqual(bad, [])
        # The mutation test is placed
        # once in its own job. Named failure: a mutation test dropped or doubled, so mutants go unrun.
        self.assertEqual(mutate_problems(self.text), [])

    def test_the_shoot_suite_has_its_own_job(self):
        # Named failure: the browser install shares the `checks` cap again. Whether a red shoot suite blocks a merge is
        # test_all_jobs_passed.py's: all-jobs-passed must need SHOOT_JOB, and that test derives its needs from checks.yml.
        self.assertEqual(shoot_problems(self.text), [])

    def test_the_shoot_checker_sees_its_defects(self):
        good = shoot_doc()
        self.assertEqual(shoot_problems(good), [])
        bad = {"back in checks": shoot_doc(extra=f"      - name: s\n        run: {SHOOT_CMD}\n"),
               "install in checks": shoot_doc(lint_run="playwright install --with-deps chromium"),
               "install in a checks block": shoot_doc(lint_run="|\n          ruff\n          playwright install chromium"),
               "suite step adds its own condition": shoot_doc(suite_if=f"${{{{ ({SHOOT_SCOPE}) && false }}}}"),
               "suite step lacks the scope condition": shoot_doc(suite_if=None),
               "install step lacks the scope condition": shoot_doc(install_if=None),
               "on windows": shoot_doc(runs_on="windows-latest"),
               "suite dropped": shoot_doc(suite_run="true")}
        for label, text in bad.items():
            with self.subTest(defect=label):
                self.assertTrue(shoot_problems(text), label)

    def test_the_export_suite_is_pinned_in_the_shoot_job(self):
        # Named failure: the export suite runs in `checks` again, which installs no browser, or in SHOOT_JOB without the
        # NODE_PATH prefix, so its picture cases find no Playwright and go red.
        self.assertEqual(export_suite_problems(self.text), [])

    def test_the_export_suite_checker_sees_its_defects(self):
        export = (f"      - name: export suite\n        if: ${{{{ {EXPORT_IF} }}}}\n"
                  f"        shell: bash\n        run: {EXPORT_CMD}\n")

        def doc(shoot=export, checks=""):
            return ("jobs:\n  checks:\n    runs-on: ubuntu-latest\n    needs: scope\n    steps:\n"
                    "      - name: lint\n        run: ruff\n" + checks
                    + f"  {SHOOT_JOB}:\n    runs-on: ubuntu-latest\n    needs: scope\n    steps:\n"
                    f"      - name: Install Chromium\n        if: ${{{{ {EXPORT_IF} }}}}\n        run: playwright install chromium\n"
                    + shoot)

        self.assertEqual(export_suite_problems(doc()), [])
        bad = {"in checks": doc(checks=export),
               "dropped": doc(shoot=""),
               "no NODE_PATH prefix": doc(shoot=export.replace(EXPORT_CMD, "python3 skills/waiting-page/test_export_page.py")),
               "shell not bash": doc(shoot=export.replace("        shell: bash\n", "")),
               "if adds its own condition": doc(shoot=export.replace(EXPORT_IF, f"({EXPORT_IF}) && false")),
               "if lacks the scope condition": doc(shoot=export.replace(f"        if: ${{{{ {EXPORT_IF} }}}}\n", "")),
               "env set": doc(shoot=export.replace("        run:", "        env:\n          BASE_REF: main\n        run:"))}
        for label, text in bad.items():
            with self.subTest(defect=label):
                self.assertTrue(export_suite_problems(text), label)

    def test_the_waiting_page_suite_has_its_own_job(self):
        # Named failure: the waiting page suite back in checks-shoot, where it hit that job's cap, or the roadmap suite moved out of it.
        self.assertEqual(waiting_page_problems(self.text), [])

    def test_the_waiting_page_checker_sees_its_defects(self):
        good = shoot_doc(roadmap_run=ROADMAP_CMD, waiting_run=WAITING_PAGE_CMD)
        self.assertEqual(waiting_page_problems(good), [])
        bad = {"waiting suite back in checks-shoot": shoot_doc(roadmap_run=ROADMAP_CMD, waiting_run=WAITING_PAGE_CMD,
                                                              shoot_extra=f"      - name: w\n        run: {WAITING_PAGE_CMD}\n"),
               "waiting suite in checks": shoot_doc(roadmap_run=ROADMAP_CMD, waiting_run=WAITING_PAGE_CMD,
                                                    extra=f"      - name: w\n        run: {WAITING_PAGE_CMD}\n"),
               "waiting suite dropped": shoot_doc(roadmap_run=ROADMAP_CMD, waiting_run="true"),
               "waiting job missing": shoot_doc(roadmap_run=ROADMAP_CMD),
               "waiting job on windows": shoot_doc(roadmap_run=ROADMAP_CMD, waiting_run=WAITING_PAGE_CMD,
                                                   waiting_runs_on="windows-latest"),
               "roadmap suite dropped": shoot_doc(waiting_run=WAITING_PAGE_CMD),
               # Named failure: a step's if adds to the scope condition, so the step can skip the waiting page suite and read green.
               "waiting suite step adds its own condition": shoot_doc(roadmap_run=ROADMAP_CMD, waiting_run=WAITING_PAGE_CMD,
                                                                     waiting_suite_if=f"${{{{ ({SHOOT_SCOPE}) && false }}}}"),
               "waiting suite step appends && false": shoot_doc(roadmap_run=ROADMAP_CMD, waiting_run=WAITING_PAGE_CMD,
                                                               waiting_suite_if=f"${{{{ {SHOOT_SCOPE} && false }}}}"),
               "waiting suite step lacks the scope condition": shoot_doc(roadmap_run=ROADMAP_CMD, waiting_run=WAITING_PAGE_CMD,
                                                                        waiting_suite_if=None),
               "waiting install step adds its own condition": shoot_doc(roadmap_run=ROADMAP_CMD, waiting_run=WAITING_PAGE_CMD,
                                                                       waiting_install_if=f"${{{{ ({SHOOT_SCOPE}) && false }}}}"),
               "waiting install step lacks the scope condition": shoot_doc(roadmap_run=ROADMAP_CMD, waiting_run=WAITING_PAGE_CMD,
                                                                          waiting_install_if=None),
               "waiting checkout step adds its own condition": shoot_doc(roadmap_run=ROADMAP_CMD, waiting_run=WAITING_PAGE_CMD,
                                                                        waiting_checkout_if=f"${{{{ ({SHOOT_SCOPE}) && false }}}}")}
        for label, text in bad.items():
            with self.subTest(defect=label):
                self.assertTrue(waiting_page_problems(text), label)

    def test_scope_job_checks_every_other_job(self):
        self.assertEqual(scope_problems(self.text), [])
        # The guard and mutate jobs skip on the
        # guard flag. Named failure: a cut job runs or never runs on push, schedule and dispatch.
        jobs = all_jobs(self.text)
        for name in (GUARD_JOB, MUTATE_JOB):
            self.assertIn(name, jobs, f"no job named {name}")
            self.assertEqual(job_check_problems(name, jobs[name], FLAG_OF[name]), [])
        # checks-guard-2 is the Linux guard shard, on checks_guard through FLAG_OF. Named failure: its steps name another flag,
        # so the shard starts on that flag's scope. The defect swaps the flag in every step: one scope condition, not steps that
        # disagree (which would be a different cause).
        job = job_block(self.text, "checks-guard-2")
        self.assertIsNotNone(job, "no job named checks-guard-2")
        self.assertEqual(self.text.count(job), 1, "the fixture: checks-guard-2's block appears once in checks.yml")
        self.assertEqual(job.count(LINUX_GUARD_IF), len(step_blocks(job)),
                         "the fixture: every step of checks-guard-2 carries LINUX_GUARD_IF")
        swapped = job.replace(LINUX_GUARD_IF, "needs.scope.outputs.checks_macos == 'true' || github.event_name != 'pull_request'")
        problems = [p for p in scope_problems(self.text.replace(job, swapped, 1)) if p.startswith("checks-guard-2:")]
        self.assertEqual(len(problems), 1, f"checks-guard-2 problems: {problems}")
        self.assertIn("does not read needs.scope.outputs.checks_guard", problems[0])

    def test_the_check_form_sees_its_defects(self):
        scope_condition = "needs.scope.outputs.checks_macos == 'true' || github.event_name != 'pull_request'"

        def job(steps=None, job_if=None, needs="scope"):
            if steps is None:
                steps = [{"name": "setup", "if": f"${{{{ {scope_condition} }}}}"},
                         {"name": "lint", "if": f"${{{{ ({scope_condition}) && !cancelled() }}}}"}]
            return {"needs": needs, "if": job_if, "steps": steps}

        self.assertEqual(job_check_problems("checks-macos", job()), [])
        self.assertEqual(job_check_problems("checks", {"needs": "scope", "if": None, "steps": []}), [])
        self.assertTrue(job_check_problems("checks", {"needs": None, "if": None, "steps": []}))
        # ci-hygiene steps 11 and 19: a job-level if that holds only the draft guard is allowed on a lint job and a scoped job.
        draft = "${{ !github.event.pull_request.draft }}"
        for name, flag in (("checks-merge-install", None), ("checks-macos-b", "checks_macos")):
            with self.subTest(job=name, defect="the draft guard as job-level if is refused"):
                self.assertEqual(job_check_problems(name, job(job_if=draft), flag), [])
        lint_bad = {
            "a job-level if reads a flag": job(job_if="${{ needs.scope.outputs.code == 'true' }}"),
            "a job-level if is a trigger guard": job(job_if="${{ github.event_name == 'pull_request' }}"),
            "draft guard and scope in one job-level if": job(job_if=f"${{{{ !github.event.pull_request.draft && ({scope_condition}) }}}}"),
        }
        for label, j in lint_bad.items():
            with self.subTest(defect=label):
                self.assertTrue(job_check_problems("checks-merge-install", j), label)
                self.assertTrue(job_check_problems("checks-macos-b", j, "checks_macos"), label)
        bad = {
            "job-level if kept": job(job_if=f"${{{{ {scope_condition} }}}}"),
            "pr_only": job([{"if": "${{ needs.scope.outputs.checks_macos == 'true' }}"}]),  # skips on push when the flag is false
            "not_pr_always": job([{"if": "${{ github.event_name != 'pull_request' }}"}]),  # never reads the flag
            "other_flag": job([{"if": f"${{{{ {scope_condition.replace('checks_macos', 'checks_windows')} }}}}"}]),
            "always_on_pr": job([{"if": "${{ !cancelled() || needs.scope.outputs.checks_macos == 'true' }}"}]),  # runs on PR with every flag false
            "parens dropped, one step": job([{"if": f"${{{{ {scope_condition} && !cancelled() }}}}"}]),
            "parens dropped, beside a bare scope condition": job([{"if": f"${{{{ {scope_condition} && !cancelled() }}}}"}, {"if": f"${{{{ {scope_condition} }}}}"}]),
            "one step missing the scope condition": job([{"if": f"${{{{ {scope_condition} }}}}"}, {"name": "bare"}]),
            "steps disagree": job([{"if": f"${{{{ {scope_condition} }}}}"},
                                   {"if": f"${{{{ ({scope_condition.replace('checks_macos', 'shell_macos')}) && !cancelled() }}}}"}]),
            "no step carries a scope condition": job([{"name": "a"}]),
            "top-level or past the scope condition": job([{"if": f"${{{{ ({scope_condition}) && !cancelled() || always() }}}}"}]),  # runs outside it
            "top-level or past the scope condition, event only": job([{"if": f"${{{{ ({scope_condition}) && !cancelled() || github.event_name == 'push' }}}}"}]),
            "wrong needs": job(needs="checks"),
        }
        for label, j in bad.items():
            with self.subTest(defect=label):
                self.assertTrue(job_check_problems("checks-macos", j), label)

    def test_suites_keep_their_conditions(self):
        self.assertEqual(hardening_problems(self.text), [])

    def test_a_comment_that_names_a_shard_value_is_no_home(self):
        # Rows: a full-line comment, a trailing comment on a shard key, and a comment after a lone apostrophe.
        # Named failure: a comment that names GUARD_SHARD counts as a shard home, so checks.yml goes red for a comment.
        self.assertIn("          GUARD_SHARD: 1/2\n", self.text)  # the fixture: a full step's shard key
        cases = {
            "a full-line comment": self.text + "# GUARD_SHARD=1/2 sets the shard on the full step only\n",
            "a trailing comment on a shard key": self.text.replace("          GUARD_SHARD: 1/2\n",
                                                                  "          GUARD_SHARD: 1/2  # GUARD_SHARD\n", 1),
            "a comment after a lone apostrophe": self.text + "      - run: echo Don't # GUARD_SHARD=1/2\n",
        }
        baseline = hardening_problems(self.text)  # a comment changes no verdict, whatever the file's own verdict is
        for label, text in cases.items():
            with self.subTest(case=label):
                self.assertEqual(hardening_problems(text), baseline, label)

    def test_a_shard_value_in_quotes_or_after_a_lone_quote_is_a_leak(self):
        # Rows: a comment opener inside quotes, a lone apostrophe before a leak, and a leak on the line after an open quote.
        # Named failure: a quote or an apostrophe hides a shard value that reaches $GITHUB_ENV, so it goes unflagged.
        cases = {
            "a comment opener inside quotes": self.text + '      - run: echo "# x" && echo GUARD_SHARD=1/2 >> "$GITHUB_ENV"\n',
            "a lone apostrophe before the leak": self.text + "      - run: echo Don't; echo GUARD_SHARD=1/2 >> \"$GITHUB_ENV\"\n",
            "a leak after an open quote on the line above": self.text + ('      - run: |\n          echo "start\n'
                                                                         '          echo GUARD_SHARD=1/2 >> "$GITHUB_ENV"\n'
                                                                         '          end"\n'),
        }
        for label, text in cases.items():
            with self.subTest(case=label):
                self.assertTrue([p for p in hardening_problems(text) if "GUARD_SHARD appears" in p], label)

    def test_checker_sees_drop_and_duplicate(self):
        # R62: no merge slice step, so a doc has none unless slice_ puts one in job 0 (a defect).
        def doc(*jobs, slice_=False):
            return "jobs:\n" + "".join(
                f"  j{i}:\n    runs-on: windows-latest\n    steps:\n"
                + "".join(f"      - run: {c}\n" for c in cmds)
                + ("      - run: python merge/test_merge.py\n        env:\n          MERGE_TESTS: windows-slice\n"
                   if slice_ and i == 0 else "")
                for i, cmds in enumerate(jobs)
            )
        self.assertEqual(placement_problems(doc(REQUIRED[:7], REQUIRED[7:14], REQUIRED[14:])), [])
        self.assertTrue(placement_problems(doc(REQUIRED[:7], REQUIRED[7:14], REQUIRED[14:], slice_=True)))
        self.assertTrue(placement_problems(doc(REQUIRED[1:7], REQUIRED[7:14], REQUIRED[14:])))
        self.assertTrue(placement_problems(doc(REQUIRED[:8], REQUIRED[7:14], REQUIRED[14:])))

    def test_checker_sees_the_merge_slice_defects(self):
        scope_condition = DRAFT_GUARD  # R62: the draft guard is the scope condition; the code gate rides in each step's own condition
        full_e = unwrap(IF_PIN["python merge/test_merge.py"])
        slice_e = "!cancelled() && github.event_name == 'pull_request' && needs.scope.outputs.code == 'true'"

        def doc(with_slice=False, env="windows-slice", full=full_e):
            full_step = f"      - name: Full\n        if: ${{{{ ({scope_condition}) && {full} }}}}\n        run: python merge/test_merge.py\n"
            slice_step = (f"      - name: Slice\n        if: ${{{{ ({scope_condition}) && {slice_e} }}}}\n        env:\n"
                          f"          MERGE_TESTS: {env}\n        run: python merge/test_merge.py\n") if with_slice else ""
            return ("jobs:\n  checks-windows-merge:\n    runs-on: windows-latest\n    needs: scope\n    steps:\n"
                    f"      - uses: actions/setup-python@abc # v6\n        if: ${{{{ {scope_condition} }}}}\n" + full_step + slice_step)

        good = doc()
        self.assertEqual(hardening_problems(good), [])
        self.assertFalse(any("MERGE_TESTS appears" in p for p in hardening_problems(good)))
        self.assertTrue(any("runs 1 times on windows-latest" in p for p in placement_problems(doc(with_slice=True))))
        self.assertTrue(any("MERGE_TESTS appears 1 times" in p for p in hardening_problems(doc(with_slice=True))))
        self.assertTrue(hardening_problems(doc(full=slice_e)))  # full run on pull_request only: the pin is every event
        for bad in (good.replace("    runs-on: windows-latest\n", "    runs-on: windows-latest\n    env:\n      MERGE_TESTS: windows-slice\n"),
                    "env:\n  MERGE_TESTS: windows-slice\n" + good,
                    good.replace("    steps:\n", "    steps:\n      - run: echo MERGE_TESTS=windows-slice >> $GITHUB_ENV\n")):
            self.assertTrue(any("MERGE_TESTS appears 1 times" in p for p in hardening_problems(bad)), bad)
        self.assertTrue(hardening_problems(doc(full=full_e.replace("needs.scope.outputs.code == 'true' || ", ""))))  # the push gate dropped
        self.assertTrue(any("reads scope flags" in p for p in hardening_problems(doc(full=full_e.replace("outputs.code", "outputs.checks_windows_merge")))))  # own flag read

    def test_checker_sees_the_shard_defects(self):
        scope_condition = DRAFT_GUARD  # R62: the base job's steps carry the draft guard, and the code gate rides in the full step
        full_e = unwrap(IF_PIN[GUARD_CMD])
        slice_e = "!cancelled() && github.event_name == 'pull_request' && needs.scope.outputs.code == 'true'"

        def job(name, shard, base=False, slice_=False):
            # The base job is scoped: the scope condition sits in each step. A shard keeps its job-level if and its steps' own ifs.
            def cond(e):
                return f"${{{{ ({scope_condition}) && {e} }}}}" if base else f"${{{{ {e} }}}}"

            head = f"  {name}:\n    runs-on: windows-latest\n    needs: scope\n" + ("" if base else f"    if: {SHARD_JOB_IF}\n")
            setup = "      - uses: actions/setup-python@abc # v6\n" + (f"        if: ${{{{ {scope_condition} }}}}\n" if base else "")
            full = (f"      - name: Full\n        if: {cond(full_e)}\n"
                    + (f"        env:\n          GUARD_SHARD: {shard}\n" if shard else "")
                    + "        run: python hooks/test_guard.py\n")
            sl = (f"      - name: Slice\n        if: {cond(slice_e)}\n        env:\n          GUARD_TESTS: windows-slice\n"
                  "        run: python hooks/test_guard.py\n") if slice_ else ""
            return head + "    steps:\n" + setup + full + sl

        def doc(*jobs):
            return "jobs:\n" + "".join(jobs)

        def place(text):
            return [p for p in placement_problems(text) if "test_guard" in p]

        base = job("checks-windows-guard", "1/3", base=True)
        good = doc(base, job("checks-windows-guard-2", "2/3"), job("checks-windows-guard-3", "3/3"))
        self.assertEqual(place(good), [])
        self.assertEqual(guard_problems(good), [])
        self.assertEqual(job_check_problems("checks-windows-guard-2", {"needs": "scope", "if": SHARD_JOB_IF, "steps": []}), [])
        bad = {
            "a shard dropped": doc(base, job("checks-windows-guard-2", "2/3")),
            "a shard doubled": doc(base, job("checks-windows-guard-2", "2/3"), job("checks-windows-guard-3", "2/3")),
            "a shard unset": doc(base, job("checks-windows-guard-2", "2/3"), job("checks-windows-guard-3", "")),
            "n disagrees": doc(base, job("checks-windows-guard-2", "2/2"), job("checks-windows-guard-3", "3/3")),
            "a slice step left in the base job": doc(job("checks-windows-guard", "1/3", base=True, slice_=True),
                                                     job("checks-windows-guard-2", "2/3"), job("checks-windows-guard-3", "3/3")),
            "a lone shard": doc(job("checks-windows-guard", "1/2", base=True, slice_=True)),
            "a stray job name": doc(base, job("checks-windows-guard-2", "2/3"), job("checks-windows-rest", "3/3")),
        }
        for label, text in bad.items():
            self.assertTrue(place(text) or guard_problems(text), label)
        # A shard job that runs on pull_request, or runs the slice, takes the PR verdict out of the required check.
        flag_if = "${{ needs.scope.outputs.guard == 'true' || github.event_name != 'pull_request' }}"  # a shard's job-level if on a flag
        self.assertTrue(job_check_problems("checks-windows-guard-2", {"needs": "scope", "if": flag_if, "steps": []}))
        self.assertTrue(guard_problems(doc(base, job("checks-windows-guard-2", "2/3", slice_=True),
                                           job("checks-windows-guard-3", "3/3"))))
        # A shard value set for the whole job or workflow would cut the PR slice too.
        self.assertFalse([p for p in hardening_problems(good) if "GUARD_SHARD appears" in p])
        for leak in (good.replace("    steps:\n", "    env:\n      GUARD_SHARD: 1/3\n    steps:\n", 1),
                     "env:\n  GUARD_SHARD: 1/3\n" + good):
            self.assertTrue([p for p in hardening_problems(leak) if "GUARD_SHARD appears" in p], leak)

    def test_the_guard_suite_has_its_own_windows_job(self):
        self.assertEqual(guard_problems(self.text), [])

    def test_checks_sets_no_guard_family(self):
        self.assertEqual([p for p in guard_problems(self.text) if "GUARD_FAMILY" in p], [])
        # The red run: the checker flags a
        # guard family set in checks. Named failure: a guard family runs in checks and CI goes green.
        bad = [p for p in guard_problems(self.text + "\n# GUARD_FAMILY=shared-tree\n") if "GUARD_FAMILY" in p]
        self.assertTrue(bad)

    def test_checker_sees_the_guard_slice_and_mutate_defects(self):
        scope_condition = DRAFT_GUARD  # R62: the draft guard is the scope condition; the code gate rides in the full step
        full_e = unwrap(IF_PIN[GUARD_CMD])
        slice_e = "!cancelled() && github.event_name == 'pull_request' && needs.scope.outputs.code == 'true'"

        def doc(full=full_e, slice_env=None, scope_condition_=scope_condition, job_if=None, extra="", more=""):
            # R62: no slice step. slice_env, when given, names a slice step left in the job.
            slice_step = (f"      - name: Slice\n        if: ${{{{ ({scope_condition_}) && {slice_e} }}}}\n        env:\n"
                          f"          GUARD_TESTS: {slice_env}\n        run: python hooks/test_guard.py\n") if slice_env else ""
            return ("jobs:\n  checks-windows-guard:\n    runs-on: windows-latest\n    needs: scope\n"
                    + (f"    if: {job_if}\n" if job_if else "") + extra + "    steps:\n"
                    f"      - uses: actions/setup-python@abc # v6\n        if: ${{{{ {scope_condition_} }}}}\n"
                    f"      - name: Full\n        if: ${{{{ ({scope_condition_}) && {full} }}}}\n        run: python hooks/test_guard.py\n"
                    + slice_step + more)
        self.assertEqual(guard_problems(doc()), [])
        self.assertTrue(guard_problems(doc(slice_env="windows-slice")))  # a slice step is left in the job
        self.assertTrue(guard_problems(doc(full=slice_e)))  # full suite runs on pull_request only
        self.assertTrue(guard_problems(doc(extra="    env:\n      GUARD_TESTS: windows-slice\n")))  # job-level env
        self.assertTrue(guard_problems(doc(job_if="needs.scope.outputs.code == 'true'")))  # a job-level if on the scoped job
        self.assertTrue(guard_problems(doc(full=full_e.replace("outputs.code", "outputs.checks_windows"))))  # reads its own flag
        self.assertTrue(guard_problems(doc(full=full_e.replace("needs.scope.outputs.code == 'true' || ", ""))))  # push gate dropped
        self.assertTrue(guard_problems(doc(scope_condition_="needs.scope.outputs.guard == 'true'")))  # a step without the draft guard
        self.assertTrue(guard_problems(doc(more="  checks-windows:\n    runs-on: windows-latest\n    needs: scope\n"
                                               "    if: ${{ needs.scope.outputs.checks_windows == 'true' }}\n"
                                               "    steps:\n      - run: python hooks/test_guard.py\n")))
        def shard_job(name, shard, os_="ubuntu-latest"):
            return (f"  {name}:\n    runs-on: {os_}\n    steps:\n      - run: python3 hooks/mutate_guard.py\n"
                    f"        env:\n          MUTATE_SHARD: {shard}\n")
        three = "jobs:\n" + shard_job("checks-mutate-guard", "1/3") + shard_job("checks-mutate-guard-b", "2/3") \
            + shard_job("checks-mutate-guard-c", "3/3")
        self.assertEqual(mutate_problems(three), [])
        self.assertTrue(mutate_problems(three.replace("checks-mutate-guard-c", "checks")))  # a shard in the lint job
        self.assertTrue(mutate_problems(three.replace("checks-mutate-guard-c:\n    runs-on: ubuntu-latest",
                                                      "checks-mutate-guard-c:\n    runs-on: windows-latest")))  # on Windows
        self.assertEqual(mutate_problems(three.replace("MUTATE_SHARD: 2/3", "MUTATE_SHARD: \"2/3\"  # shard two")), [])  # quotes and comment
        self.assertEqual(mutate_problems("jobs:\n" + shard_job("checks-mutate-guard-c", "3/3") + shard_job("checks-mutate-guard", "1/3")
                                         + shard_job("checks-mutate-guard-b", "2/3")), [])  # job order is free
        self.assertTrue(mutate_problems(three.replace("2/3", "1/3")))  # two shards run the same mutants
        self.assertTrue(mutate_problems(three.replace("        env:\n          MUTATE_SHARD: 3/3\n", "")))  # no shard set: runs all
        self.assertTrue(mutate_problems("jobs:\n" + shard_job("checks-mutate-guard", "1/3")))  # shards 2 and 3 missing
        self.assertTrue(mutate_problems(three + shard_job("checks", "1/3")))  # runs twice


def split_doc(jobs):
    """checks.yml text for `jobs`, {name: (runs-on, [(cmd, if, shell, env)])}, each step laid out as the real file lays it out."""
    out = ["jobs:"]
    for name, (runs_on, steps) in jobs.items():
        out.append(f"  {name}:\n    runs-on: {runs_on}\n    needs: scope\n    steps:")
        for cmd, if_, shell, env in steps:
            out.append("      - name: suite")
            if if_ is not None:
                out.append(f"        if: ${{{{ {if_} }}}}")
            if shell:
                out.append(f"        shell: {shell}")
            if env:
                out.append("        env:")
                out += [f"          {k}: {v}" for k, v in env.items()]
            out.append(f"        run: {cmd}")
    return "\n".join(out) + "\n"


def linux_guard_shard(value, if_=LINUX_GUARD_IF, shell=None, env=None):
    """One Linux guard shard step for split_doc: the suite with its env, its GUARD_SHARD value and any `env` override."""
    return (LINUX_GUARD, if_, shell, {**LINUX_GUARD_ENV, "GUARD_SHARD": value, **(env or {})})


def linux_guard_doc(a=None, b=None, extra=None):
    """checks.yml text for the planned Linux guard split: checks-guard runs shard 1/2 and checks-guard-2 shard 2/2. The step
    lists a and b replace those jobs' steps, and extra jobs are added as given."""
    jobs = {"checks-guard": ("ubuntu-latest", [linux_guard_shard("1/2")] if a is None else a),
            "checks-guard-2": ("ubuntu-latest", [linux_guard_shard("2/2")] if b is None else b)}
    return split_doc({**jobs, **(extra or {})})


def planned_linux_guard_split(text):
    """checks.yml text with the planned Linux guard split, built from the real file: checks-guard keeps its job with GUARD_SHARD
    1/2 in the guard step's env, a copy of that job named checks-guard-2 carries GUARD_SHARD 2/2, and checks-guard-2 follows
    checks-guard in each fan-in. A file that already has checks-guard-2 is returned as it is, so the cases stay true after the
    split lands."""
    if "\n  checks-guard-2:\n" in text:
        return text
    job = job_block(text, "checks-guard")
    env_end = '          GUARD_CHROMIUM: "1"\n'
    assert job.count(env_end) == 1, "the checks-guard guard step's env changed: this fixture must follow it"
    first = job.replace(env_end, env_end + "          GUARD_SHARD: 1/2\n")
    second = job.replace(env_end, env_end + "          GUARD_SHARD: 2/2\n")
    text = text.replace("  checks-guard:" + job, "  checks-guard:" + first + "  checks-guard-2:" + second, 1)
    return text.replace("      - checks-guard\n", "      - checks-guard\n      - checks-guard-2\n")


def fan_in_rules():
    """The two fan-in rules as (needs_of, needs_problems, ci_done_problems): all-jobs-passed's needs (all_jobs_passed_rules) and
    ci-done's needs (actions/ci-done-comment/test_comment.py). Imported here, not at the top: all_jobs_passed_rules imports this
    file, so a module-level import would be circular."""
    from all_jobs_passed_rules import needs_of, needs_problems  # noqa: E402  the one home of the all-jobs-passed needs rule
    sys.path.insert(0, os.path.join(HERE, "..", "actions", "ci-done-comment"))
    import test_comment  # noqa: E402  the one home of the ci-done needs rule
    return needs_of, needs_problems, test_comment.ci_done_problems


def without_need(text, job, name):
    """`text` with `name` taken out of the needs of `job` (the job's own block, from its key to the next job key)."""
    block = job_block(text, job)
    entry = f"      - {name}\n"
    assert block and entry in block, f"{name} is not in {job}'s needs"
    return text.replace(block, block.replace(entry, "", 1), 1)


class SplitJobs(unittest.TestCase):
    """The Linux split (checks, checks-merge-install) and the macOS split (checks-macos, checks-macos-b): each suite of the old
    single job runs in exactly one job of its split, with its pinned `if:` and `shell:` and no env (LINUX_SUITES, MACOS_SUITES)."""

    def setUp(self):
        with open(CHECKS, encoding="utf-8") as f:
            self.text = f.read()

    def test_each_linux_suite_runs_once_in_its_split(self):
        self.assertEqual(linux_split_problems(self.text), [])

    def test_each_macos_suite_runs_once_in_its_split_and_the_guard_slice_in_checks_macos(self):
        self.assertEqual(macos_split_problems(self.text), [])

    def test_a_macos_shard_value_outside_its_step_is_flagged(self):
        # The shard values are counted as homes in hardening_problems, so a stray one (here at job level) is a named problem.
        leak = self.text.replace("    steps:\n", "    env:\n      GUARD_SHARD: 1/2\n    steps:\n", 1)
        self.assertEqual(hardening_problems(self.text), [])
        self.assertTrue([p for p in hardening_problems(leak) if "GUARD_SHARD appears" in p])

    def test_checker_sees_the_linux_split_defects(self):
        rows = [(c, i, s, {}) for c, (i, s) in LINUX_SUITES.items()]
        half = len(rows) // 2

        def doc(rs):
            return split_doc({"checks": ("ubuntu-latest", rs[:half]), "checks-merge-install": ("ubuntu-latest", rs[half:])})

        self.assertEqual(linux_split_problems(doc(rows)), [])
        c0, i0, s0, _ = rows[0]
        bad = {
            "a suite dropped": doc(rows[1:]),
            "a suite run twice": doc(rows + [rows[-1]]),
            "a suite's if changed": doc([(c0, "needs.scope.outputs.code == 'false'", s0, {})] + rows[1:]),
            "a suite's shell added": doc([(c0, i0, "bash", {})] + rows[1:]),
            "a suite's env set": doc([(c0, i0, s0, {"BASE_REF": "main"})] + rows[1:]),
            "a job-level env": doc(rows).replace("    needs: scope\n    steps:", "    needs: scope\n    env:\n      BASE_REF: main\n    steps:", 1),
        }
        for label, text in bad.items():
            with self.subTest(defect=label):
                self.assertTrue(linux_split_problems(text), label)

    def test_checker_sees_the_macos_split_defects(self):
        rows = [(c, i, s, {}) for c, (i, s) in MACOS_SUITES.items()]
        half = len(rows) // 2
        slice_step = (MACOS_GUARD, MAC_CODE, None, MACOS_SLICE_ENV)

        def doc_on(runs_on):
            def doc(a=None, b=None, extra=None):
                a = rows[:half] + [slice_step] if a is None else a
                b = rows[half:] if b is None else b
                return split_doc({"checks-macos": (runs_on, a), "checks-macos-b": (runs_on, b), **(extra or {})})
            return doc

        # Each case runs on a literal macos-* runs-on and on the runner pick: the checker must see both as macOS.
        for runs_on in ("macos-latest", MAC_PICK_RUNS_ON):
            with self.subTest(runs_on=runs_on):
                doc = doc_on(runs_on)
                with self.subTest(case="the good split passes"):
                    self.assertEqual(macos_split_problems(doc()), [])
                # Named failure: on the pick, a slice in checks-macos-b is reported as in no job, so the problem names no job.
                with self.subTest(case="a slice in checks-macos-b names that job"):
                    self.assertIn("['checks-macos-b']", "\n".join(macos_slice_problems(doc(a=rows[:half], b=rows[half:] + [slice_step]))))
                c0, i0, s0, _ = rows[0]
                bad = {
                    "a suite dropped": doc(a=rows[1:half] + [slice_step]),
                    "a suite run in both jobs": doc(b=rows[half:] + [rows[0]]),
                    "a suite's if changed": doc(a=[(c0, "needs.scope.outputs.code == 'false'", s0, {})] + rows[1:half] + [slice_step]),
                    "a suite's env set": doc(a=[(c0, i0, s0, {"BASE_REF": "main"})] + rows[1:half] + [slice_step]),
                    "the slice dropped from checks-macos": doc(a=rows[:half]),
                    "the slice in checks-macos-b too": doc(b=rows[half:] + [slice_step]),
                    "a shard value on the slice": doc(a=rows[:half] + [(MACOS_GUARD, MAC_CODE, None, {**MACOS_SLICE_ENV, "GUARD_SHARD": "1/2"})]),
                    "the slice in a third macOS job": doc(extra={"checks-macos-c": (runs_on, [slice_step])}),
                }
                for label, text in bad.items():
                    with self.subTest(defect=label):
                        self.assertTrue(macos_split_problems(text), label)

    def test_the_unknown_reads_check_runs_once_in_each_split(self):
        # Named failure: check_unknown_reads_contract.py runs twice, or not at all, in a split, and no case notices.
        # Rows: a copy in checks-macos-b, a drop from checks-macos, and a drop from checks (Linux).
        mac_step = ("      - name: Unknown-read contract (guard + session_start)\n"
                    "        if: ${{ (needs.scope.outputs.checks_macos == 'true' || github.event_name != 'pull_request') && !cancelled() && needs.scope.outputs.code == 'true' }}\n"
                    "        run: python3 lint/check_unknown_reads_contract.py\n")
        linux_step = ("      - name: Unknown-read contract (guard + session_start)\n"
                      "        if: ${{ needs.scope.outputs.code == 'true' }}\n"
                      "        run: python3 lint/check_unknown_reads_contract.py\n")
        self.assertIn(mac_step, self.text)  # the fixture: checks-macos runs the check
        self.assertIn(linux_step, self.text)  # the fixture: checks runs the check
        self.assertIn("  checks-macos-b:\n", self.text)
        head, sep, tail = self.text.partition("  checks-macos-b:\n")
        copied = head + sep + tail.replace("    steps:\n", "    steps:\n" + mac_step, 1)
        cases = {
            "a copy in checks-macos-b": (copied, macos_split_problems),
            "the check dropped from checks-macos": (self.text.replace(mac_step, "", 1), macos_split_problems),
            "the check dropped from checks (Linux)": (self.text.replace(linux_step, "", 1), linux_split_problems),
        }
        for label, (text, check) in cases.items():
            with self.subTest(defect=label):
                self.assertTrue([p for p in check(text) if "check_unknown_reads_contract" in p], label)

    def test_the_linux_guard_runs_in_its_two_shard_jobs(self):
        # Named failure: the guard suite runs in one Linux job, or in a third, or in neither, so its cases do not each run once.
        self.assertEqual(linux_guard_split_problems(self.text), [])

    def test_the_linux_guard_shards_install_playwright(self):
        # Named failure: a guard shard job has no Playwright install, so the guard's checker has no browser to render with.
        self.assertEqual(linux_guard_install_problems(self.text), [])

    def test_checker_sees_the_linux_guard_split_defects(self):
        self.assertEqual(linux_guard_split_problems(linux_guard_doc()), [])  # the control: the planned split passes
        bad = {
            "the second shard missing": split_doc({"checks-guard": ("ubuntu-latest", [linux_guard_shard("1/2")])}),
            "the second shard's value dropped": linux_guard_doc(b=[(LINUX_GUARD, LINUX_GUARD_IF, None, dict(LINUX_GUARD_ENV))]),
            "both shards 1/2": linux_guard_doc(b=[linux_guard_shard("1/2")]),
            "a third Linux job runs the guard": linux_guard_doc(
                extra={"checks-guard-3": ("ubuntu-latest", [linux_guard_shard("1/2")])}),
            "the guard in neither shard job": linux_guard_doc(a=[], b=[]),
            "no job at all": "jobs:\n",
            "GUARD_SHARD in a job's env": linux_guard_doc().replace(
                "    needs: scope\n    steps:", "    needs: scope\n    env:\n      GUARD_SHARD: 1/2\n    steps:", 1),
            "the shard's if changed": linux_guard_doc(a=[linux_guard_shard(
                "1/2", if_="needs.scope.outputs.checks_macos == 'true' || github.event_name != 'pull_request'")]),
            "the shard's if dropped": linux_guard_doc(a=[linux_guard_shard("1/2", if_=None)]),
            "a shell added to a shard": linux_guard_doc(a=[linux_guard_shard("1/2", shell="bash")]),
            "the suite's env changed": linux_guard_doc(a=[linux_guard_shard("1/2", env={"GUARD_CHROMIUM": '"0"'})]),
        }
        for label, text in bad.items():
            with self.subTest(defect=label):
                self.assertTrue(linux_guard_split_problems(text), label)

    def test_the_planned_linux_guard_split_passes_the_split_and_install_checks(self):
        # The full-size control: the planned split of the real file passes both checks, so each defect below is the only flag.
        planned = planned_linux_guard_split(self.text)
        self.assertEqual(linux_guard_split_problems(planned), [])
        self.assertEqual(linux_guard_install_problems(planned), [])

    def test_checker_sees_the_planned_install_defects(self):
        planned = planned_linux_guard_split(self.text)
        job = job_block(planned, "checks-guard-2")
        install = f"        if: ${{{{ {LINUX_GUARD_IF} }}}}\n        uses: {PLAYWRIGHT_USES}\n"
        self.assertIn(install, job, "the fixture: checks-guard-2's install step carries the scope if")
        bad = {
            "the install step's if changed": planned.replace(job, job.replace(
                install, install.replace(LINUX_GUARD_IF, "needs.scope.outputs.code == 'true'"), 1), 1),
            "no install step in checks-guard-2": planned.replace(job, job.replace(
                f"        uses: {PLAYWRIGHT_USES}\n", "        uses: actions/checkout@v5\n", 1), 1),
        }
        for label, text in bad.items():
            with self.subTest(defect=label):
                self.assertTrue(linux_guard_install_problems(text), label)

    def test_hardening_does_not_flag_the_linux_shard_values(self):
        # The two Linux shard values are homes: each sits in a guard step's env, as the Windows and macOS shard values do.
        self.assertEqual([p for p in hardening_problems(planned_linux_guard_split(self.text)) if "GUARD_SHARD" in p], [])

    def test_hardening_flags_a_stray_guard_shard_value(self):
        # Named failure: a GUARD_SHARD value that no shard step owns reaches every step that inherits it (job or workflow env).
        ci_wake = ("python3 hooks/test_ci_wake.py", None, None, {"GUARD_SHARD": "1/2"})
        stray = {
            "in the workflow env": "env:\n  GUARD_SHARD: 1/2\n" + linux_guard_doc(),
            "on a step that runs no guard shard": linux_guard_doc(extra={"checks-ci-wake": ("ubuntu-latest", [ci_wake])}),
        }
        for label, text in stray.items():
            with self.subTest(defect=label):
                self.assertTrue([p for p in hardening_problems(text) if "GUARD_SHARD appears" in p], label)

    def test_both_guard_shards_are_in_each_fan_in(self):
        # Named failure: a guard shard runs on a pull request but is in neither all-jobs-passed's needs nor ci-done's, so its red
        # cannot block the merge or post the wake comment. The names come from LINUX_GUARD_SHARD, the one home of the split.
        needs_of, _, _ = fan_in_rules()
        for job in ("all-jobs-passed", "ci-done"):
            self.assertIsNotNone(job_block(self.text, job), job)
            for shard in LINUX_GUARD_SHARD:
                with self.subTest(job=job, shard=shard):
                    self.assertIn(shard, needs_of(job_block(self.text, job)) or [], f"{shard} is not in {job}'s needs")

    def test_a_shard_left_out_of_either_fan_in_is_flagged(self):
        _, needs_problems, ci_done_problems = fan_in_rules()
        planned = planned_linux_guard_split(self.text)
        # The control: the planned text passes both fan-in rules, so each defect below is the only flag.
        self.assertEqual(needs_problems(planned), [])
        self.assertEqual(ci_done_problems(planned), [])
        for job, check in (("all-jobs-passed", needs_problems), ("ci-done", ci_done_problems)):
            for shard in LINUX_GUARD_SHARD:
                with self.subTest(job=job, shard=shard):
                    self.assertTrue(check(without_need(planned, job, shard)), f"{shard} left out of {job}")


# ---- R61 (owner pick b, 15:29 CST Nov 12): macOS runs once per batch. The macOS jobs skip a push at job level, checks-macos
# runs one mac-tagged guard slice, and the 03:17 nightly is gated on main's head. Each helper reads checks.yml text; each
# case reads the real file, so it is red until the change lands.

# The scope condition's truth table on a run: (event, draft, the gate's skip output, scope runs?). An unset output is ''.
NIGHTLY_TRUTH = (("push", False, "", True), ("pull_request", False, "", True), ("pull_request", True, "", False),
                 ("workflow_dispatch", False, "", True), ("schedule", False, "false", True), ("schedule", False, "", True),
                 ("schedule", False, "true", False))


def push_guard_only(expr):
    """True when a job-level `if:` is the push guard and nothing else: true on a pull_request (draft or not), a schedule and a
    workflow_dispatch, false on a push. It reads no scope flag, so its answer holds for every flag value, and it reads no other
    job's output: the answer must match for every skip value (SKIP_VALUES)."""
    e = unwrap(expr)
    if not e:
        return False
    try:
        return all(eval_if(e, event, flag, draft=draft, nightly_skip=nightly_skip) == want for nightly_skip in SKIP_VALUES for event, flag, draft, want in (
            ("pull_request", "false", True, True), ("pull_request", "true", False, True),
            ("schedule", "false", False, True), ("workflow_dispatch", "false", False, True),
            ("push", "false", False, False), ("push", "true", False, False)))
    except Exception:
        return False


def schedule_only(expr):
    """True when a job-level `if:` runs on a schedule and nowhere else: false on a push, a pull_request and a workflow_dispatch.
    Like push_guard_only, its answer must match for every gate value."""
    e = unwrap(expr)
    if not e:
        return False
    try:
        return all(eval_if(e, event, "false", nightly_skip=nightly_skip) == want for nightly_skip in SKIP_VALUES for event, want in (
            ("schedule", True), ("pull_request", False), ("push", False), ("workflow_dispatch", False)))
    except Exception:
        return False


def push_guard_jobs(text):
    """The jobs whose job-level if is the push guard, sorted."""
    return sorted(n for n, j in all_jobs(text).items() if j["if"] is not None and push_guard_only(j["if"]))


def macos_push_guard_problems(text):
    """R61 part 1: each MACOS_JOBS job keeps the push guard as its job-level if, and no other job has one. A step-level skip still
    starts the macOS runner, so the guard sits on the job."""
    jobs = all_jobs(text)
    problems = []
    for name in MACOS_JOBS:
        job = jobs.get(name)
        if job is None:
            problems.append(f"no {name} job")
        elif job["if"] is None:
            problems.append(f"{name} has no job-level if: a push still starts its macOS runner")
        elif not push_guard_only(job["if"]):
            problems.append(f"{name} job-level if is not the push guard: {job['if']}")
    if push_guard_jobs(text) != sorted(MACOS_JOBS):
        problems.append(f"the push guard is a job-level if on {push_guard_jobs(text)}, want {sorted(MACOS_JOBS)}")
    return problems


def skip_job_problems(text):
    """R61 part 3: the nightly gate is an ubuntu job with no job-level if, so it runs on every event: a skipped gate would skip every
    job behind scope, since a skipped ancestor skips a job whose own if holds no status function. It reads no flag and needs no other job."""
    nightly_skip = all_jobs(text).get(NIGHTLY_SKIP_JOB)
    if nightly_skip is None:
        return [f"no {NIGHTLY_SKIP_JOB} job: a scheduled run has no gate to read"]
    problems = []
    if nightly_skip["if"] is not None:
        problems.append(f"{NIGHTLY_SKIP_JOB} if is {nightly_skip['if']}, want none: a skipped gate skips every job behind scope")
    if not (nightly_skip["os"] or "").startswith("ubuntu"):
        problems.append(f"{NIGHTLY_SKIP_JOB} runs on {nightly_skip['os']}, want ubuntu")
    return problems


def skip_block_problems(text):
    """R61 part 3: the gate's own block holds a timeout, exactly read-only actions and contents, and a skip output that a step sets."""
    if NIGHTLY_SKIP_JOB not in all_jobs(text):
        return [f"no {NIGHTLY_SKIP_JOB} job: a scheduled run has no gate to read"]
    block = job_block(text, NIGHTLY_SKIP_JOB) or ""
    problems = []
    if not re.search(r"^    timeout-minutes:[ \t]*\d+", block, re.M):
        problems.append(f"{NIGHTLY_SKIP_JOB} has no timeout-minutes number")
    perms = re.search(r"^    permissions:[ \t]*(?:#[^\n]*)?\n((?:      \S[^\n]*\n)+)", block, re.M)
    got = dict(re.findall(r"^      (\w+):[ \t]*(\S+)", perms.group(1), re.M)) if perms else {}
    if got != {"actions": "read", "contents": "read"}:
        problems.append(f"{NIGHTLY_SKIP_JOB} permissions are {got}, want exactly actions: read and contents: read")
    if not re.search(r"^    outputs:[ \t]*(?:#[^\n]*)?\n      skip:[ \t]*\$\{\{[ \t]*steps\.[\w-]+\.outputs\.skip[ \t]*\}\}", block, re.M):
        problems.append(f"{NIGHTLY_SKIP_JOB} has no skip output that a step sets")
    return problems


def scope_skip_problems(text):
    """R61 part 3: scope needs both skip jobs, and its if skips a scheduled run exactly when nightly-skip says skip. A skipped
    scope skips every job through needs; an unset or failed skip job reads '' and runs everything (unknown is not skip)."""
    sc = all_jobs(text).get("scope") or {}
    problems = []
    if scope_needs_of(text) != SCOPE_NEEDS:
        problems.append(f"scope needs {sorted(scope_needs_of(text))}, want {sorted(SCOPE_NEEDS)}: scope must wait on both skip jobs")
    expr = sc.get("if")
    if expr is None:
        return problems + ["scope has no if"]
    # A job whose needed job is skipped is skipped too, unless its if holds a status function at the top level. The truth table
    # below reads always() as true, so it cannot see this: a push, where the gate is skipped, would skip scope and every job.
    if not any(c in ("always()", "!cancelled()") for c in top_level_conjuncts(expr)):
        problems.append("scope if has no top-level always() or !cancelled() conjunct: a skipped gate skips scope and every job")
    for event, draft, skip, runs in NIGHTLY_TRUTH:
        try:
            got = eval_if(expr, event, "true", draft=draft, nightly_skip=skip)
        except Exception as ex:
            return problems + [f"scope if is unreadable ({ex!r}): {expr}"]
        if got != runs:
            problems.append(f"scope on {event} (draft {draft}, gate skip {skip!r}) runs {got}, want {runs}")
    return problems


def _pair_closes_at_end(e):
    """True when the `(` at index 0 of `e` closes at its last character, outside quotes: `(a) && (b)` does not."""
    depth, quoted = 0, False
    for i, ch in enumerate(e):
        if ch == "'":
            quoted = not quoted
        elif not quoted and ch == "(":
            depth += 1
        elif not quoted and ch == ")":
            depth -= 1
            if depth == 0:
                return i == len(e) - 1
    return False


def top_level_conjuncts(expr):
    """The `&&` parts of an `if:` at the top level: outside quotes and parentheses. A status function inside a quoted string or
    under an `||` is not one of them."""
    e = unwrap(expr) or ""
    while e.startswith("(") and e.endswith(")") and _pair_closes_at_end(e):  # one pair around all of the expression
        e = e[1:-1].strip()
    parts, depth, quoted, start, i = [], 0, False, 0, 0
    while i < len(e):
        ch = e[i]
        if ch == "'":
            quoted = not quoted
        elif not quoted:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif depth == 0 and e.startswith("&&", i):
                parts.append(e[start:i].strip())
                start = i + 2
                i += 2
                continue
        i += 1
    return parts + [e[start:].strip()]


class MacOnceByBatch(unittest.TestCase):
    """R61 on checks.yml. Each case reads the real file, so it is red until the change lands. The checker self-tests run on
    synthetic text and pass on any file: each defect below is the only flag."""

    def setUp(self):
        with open(CHECKS, encoding="utf-8") as f:
            self.text = f.read()

    def test_each_macos_job_skips_a_push_at_job_level(self):
        # Named failure: a macOS job has no job-level push guard, so a push starts its runner; a step-level skip still starts it.
        self.assertEqual(macos_push_guard_problems(self.text), [])

    def test_the_macos_jobs_still_run_on_a_pull_request_a_schedule_and_a_dispatch(self):
        # Named failure: the push guard also skips the batch PR's macOS proof, or the scheduled or manual macOS run.
        for name in MACOS_JOBS:
            with self.subTest(job=name):
                expr = all_jobs(self.text).get(name, {}).get("if")
                self.assertIsNotNone(expr, f"{name} has no job-level if")
                for event in ("pull_request", "schedule", "workflow_dispatch"):
                    self.assertTrue(eval_if(expr, event, "true"), f"{name} does not run on {event}")

    def test_checks_macos_runs_one_guard_slice_and_checks_macos_b_runs_none(self):
        # Named failure: checks-macos still runs a guard shard, or checks-macos-b still runs a guard step.
        self.assertEqual(macos_slice_problems(self.text), [])

    def test_the_nightly_skip_is_an_ubuntu_job_with_no_job_level_if(self):
        # Named failure: no gate job, or one with a job-level if, so it is skipped on a pull request and every job behind scope skips.
        self.assertEqual(skip_job_problems(self.text), [])

    def test_the_nightly_skip_holds_a_timeout_read_only_permissions_and_a_skip_output(self):
        # Named failure: the gate can write, has no cap, or has no skip output for scope to read.
        self.assertEqual(skip_block_problems(self.text), [])

    def test_scope_waits_on_the_skip_and_skips_a_scheduled_run_only_when_the_skip_says_skip(self):
        # Named failure: a scheduled run reruns a green main, or a skipped gate skips a push or a red run.
        self.assertEqual(scope_skip_problems(self.text), [])

    def test_checker_sees_the_push_guard_defects(self):
        # The control: the push guard on a macOS job, with its scope condition in the steps, passes. Each defect is flagged.
        def job_text(name, if_):
            text = split_doc({name: ("macos-latest", [(MACOS_GUARD, MAC_CODE, None, {})])})
            return text.replace("    needs: scope\n", f"    needs: scope\n    if: ${{{{ {if_} }}}}\n", 1)

        self.assertEqual(job_check_problems("checks-macos", all_jobs(job_text("checks-macos", "github.event_name != 'push'"))["checks-macos"]), [])
        bad = {
            "a push-only guard": ("checks-macos", "github.event_name == 'push'"),
            "a pull-request-only guard": ("checks-macos", "github.event_name == 'pull_request'"),
            "the push guard on a Windows job": ("checks-windows", "github.event_name != 'push'"),
            "the push guard with a flag": ("checks-macos", "github.event_name != 'push' && needs.scope.outputs.checks_macos == 'true'"),
            "the push guard reads the gate": ("checks-macos", "github.event_name != 'push' && needs.nightly-skip.outputs.skip != 'true'"),
        }
        for label, (name, if_) in bad.items():
            with self.subTest(defect=label):
                self.assertTrue(job_check_problems(name, all_jobs(job_text(name, if_))[name]), label)

    def test_checker_sees_the_nightly_skip_defects(self):
        # The control: an ubuntu gate with no job-level if, its timeout, read-only permissions and skip output passes, and so does
        # a scope that waits on it. Each defect below is flagged, and only the named defect.
        # Trailing comments on the if, the cap, the permissions and the outputs headers, and a # inside a quoted step, read as
        # text or as a comment as YAML does: none of them changes the answer.
        nightly_skip = ("  nightly-skip:\n    runs-on: ubuntu-latest\n"
                "    timeout-minutes: 5  # the cap\n    permissions:  # read-only\n      actions: read  # reads runs\n      contents: read\n"
                "    outputs:  # the gate's answer\n      skip: ${{ steps.decide.outputs.skip }}\n"
                "    steps:\n      - id: gate\n        run: echo \"skip=false # not a comment\" >> \"$GITHUB_OUTPUT\"\n")
        scope = ("  scope:\n    if: ${{ always() && (github.event_name != 'pull_request' || !github.event.pull_request.draft) "
                 "&& needs.nightly-skip.outputs.skip != 'true' && needs.push-skip.outputs.skip != 'true' }}\n"
                 "    needs:\n      - nightly-skip\n      - push-skip\n    runs-on: ubuntu-latest\n    steps:\n"
                 "      - run: echo scope\n")
        self.assertEqual(skip_job_problems("jobs:\n" + nightly_skip), [])
        self.assertEqual(skip_block_problems("jobs:\n" + nightly_skip), [])
        self.assertEqual(scope_skip_problems("jobs:\n" + scope + nightly_skip), [])
        # A scope that waits on nightly-skip alone is the defect this scope check names.
        self.assertTrue(scope_skip_problems("jobs:\n" + scope.replace("    needs:\n      - nightly-skip\n      - push-skip\n",
                                                                      "    needs:\n      - nightly-skip\n") + nightly_skip))
        # The control, with !cancelled() as the status function: it passes too.
        self.assertEqual(scope_skip_problems("jobs:\n" + scope.replace("always()", "!cancelled()") + nightly_skip), [])
        skip_bad = {
            "the gate skips on a pull request": nightly_skip.replace(
                "    runs-on:", "    if: ${{ github.event_name == 'schedule' }}  # the 03:17 run only\n    runs-on:", 1),
            "the gate on macOS": nightly_skip.replace("ubuntu-latest", "macos-latest"),
        }
        for label, text in skip_bad.items():
            with self.subTest(defect=label):
                self.assertTrue(skip_job_problems("jobs:\n" + text), label)
        block_bad = {
            "no timeout": nightly_skip.replace("    timeout-minutes: 5  # the cap\n", ""),
            "contents write": nightly_skip.replace("contents: read", "contents: write"),
            "no skip output": nightly_skip.replace("    outputs:  # the gate's answer\n      skip: ${{ steps.decide.outputs.skip }}\n", ""),
        }
        for label, text in block_bad.items():
            with self.subTest(defect=label):
                self.assertTrue(skip_block_problems("jobs:\n" + text), label)
        scope_bad = {
            "scope does not wait on nightly-skip": scope.replace("      - nightly-skip\n", ""),
            "scope does not wait on push-skip": scope.replace("      - push-skip\n", ""),
            "scope ignores nightly-skip": scope.replace(" && needs.nightly-skip.outputs.skip != 'true'", ""),
            "a draft PR runs": scope.replace("!github.event.pull_request.draft", "true"),
            # R61 part 3 status function: without a top-level always() or !cancelled(), a skipped gate skips scope on push.
            "scope without a status function": scope.replace("always() && ", ""),
            "always() only inside a quoted string": scope.replace("always() && (", "'always()' && ("),
            "always() only under an or": scope.replace("always() && (", "(always() || github.event_name == 'push') && ("),
        }
        for label, text in scope_bad.items():
            with self.subTest(defect=label):
                self.assertTrue(scope_skip_problems("jobs:\n" + text + nightly_skip), label)


FULL_SUITE_BASES = (GUARD_JOB, "checks-windows-merge", "checks-windows-rest")
PLATFORM_SWEEP_FLAG = {"macOS": "checks_macos", "Windows": "checks_windows_sweep"}


def full_suite_job(name):
    """True for a job of the full Windows suite: a guard or merge base or shard, or a rest job (R62)."""
    return (shard_base(name) or name) in FULL_SUITE_BASES or name.startswith("checks-windows-rest")


def step_label(st):
    """A step's name, else its action or run command, for a failure message."""
    return st.get("name") or st.get("uses") or key(st)


def runs_on(job, st, event, flag_value, draft):
    """True when a step of `job` runs on `event`, with every scope flag set to flag_value and the pull request's draft state.
    The job's own if counts, so a shard's draft guard is read with its steps."""
    if job["if"] is not None and not eval_if(job["if"], event, flag_value, draft=draft):
        return False
    expr = step_if(st)
    return expr is None or eval_if(expr, event, flag_value, draft=draft)


def eval_with(expr, event, values, default="false", draft=False):
    """eval_if with one value per scope flag: `values` maps a flag to its value, and every other flag reads `default`."""
    rewritten = re.sub(r"needs\.scope\.outputs\.(\w+)", lambda m: repr(values.get(m.group(1), default)), expr)
    return eval_if(rewritten, event, default, draft=draft)


class SweepOnReadyPull(unittest.TestCase):
    """R62, "each suite once per batch, on the batch PR", on checks.yml. The two janitor sweep mutation steps (macOS and Windows)
    run on a ready pull_request, as they do on push, schedule and dispatch. Each case reads the real file."""

    def setUp(self):
        with open(CHECKS, encoding="utf-8") as f:
            self.text = f.read()

    def sweep_home(self, jobs, cmd):
        # Scope first: the step must be in exactly one of the jobs before its condition is read.
        homes = split_homes(self.text, jobs, cmd)
        self.assertEqual(len(homes), 1, f"{cmd!r} runs {len(homes)} times in {jobs}, want once")
        return homes[0]

    def sweep_steps(self):
        return [("macOS", MACOS_SPLIT, "python3 janitor/mutate_sweep.py"),
                ("Windows", ["checks-windows-sweep"], "python janitor/mutate_sweep.py")]

    def test_the_macos_sweep_mutation_runs_on_a_ready_pull_request(self):
        # Named failure: the macOS sweep step's if still excludes pull_request, so a ready PR skips the mutation test.
        _, cmd_jobs, cmd = self.sweep_steps()[0]
        job, st = self.sweep_home(cmd_jobs, cmd)
        expr = unwrap(step_key(st, "if"))
        self.assertIsNotNone(expr, f"{job} sweep step has no if")
        self.assertTrue(eval_if(expr, "pull_request", "true"), f"{job} sweep step does not run on a ready pull_request: {expr}")

    def test_the_windows_sweep_mutation_runs_on_a_ready_pull_request(self):
        # Named failure: the Windows sweep step's if still excludes pull_request, so a ready PR skips the mutation test.
        _, cmd_jobs, cmd = self.sweep_steps()[1]
        job, st = self.sweep_home(cmd_jobs, cmd)
        expr = unwrap(step_key(st, "if"))
        self.assertIsNotNone(expr, f"{job} sweep step has no if")
        self.assertTrue(eval_if(expr, "pull_request", "true"), f"{job} sweep step does not run on a ready pull_request: {expr}")

    def test_both_sweep_mutations_run_on_a_ready_pull_request_whatever_their_platform_flag_says(self):
        # Named failure: a sweep step is gated on its platform's scope flag, so a ready PR whose flag is false skips the mutation.
        for label, cmd_jobs, cmd in self.sweep_steps():
            flag = PLATFORM_SWEEP_FLAG[label]
            job, st = self.sweep_home(cmd_jobs, cmd)
            expr = unwrap(step_key(st, "if"))
            with self.subTest(job=job):
                self.assertTrue(eval_with(expr, "pull_request", {flag: "false", "sweep": "true"}),
                                f"{job} sweep step does not run on a ready pull_request when {flag} is false: {expr}")

    def test_both_sweep_mutations_still_run_on_push_schedule_and_dispatch(self):
        # Control, green on the old code: the change must keep the events the step already ran on.
        for label, cmd_jobs, cmd in self.sweep_steps():
            job, st = self.sweep_home(cmd_jobs, cmd)
            expr = unwrap(step_key(st, "if"))
            for event in ("push", "schedule", "workflow_dispatch"):
                with self.subTest(job=job, event=event):
                    self.assertTrue(eval_if(expr, event, "true"), f"{label} sweep step does not run on {event}: {expr}")

    def test_both_sweep_mutations_run_the_full_suite_with_no_env(self):
        # Control, green on the old code: the ready-PR run takes the full mutation test, not a slice with its own env.
        for label, cmd_jobs, cmd in self.sweep_steps():
            job, st = self.sweep_home(cmd_jobs, cmd)
            with self.subTest(job=job):
                self.assertEqual(step_env(st), {}, f"{label} sweep step has an env: {step_env(st)}")
                self.assertEqual(run_lines(st), [cmd], f"{label} sweep step runs {run_lines(st)}, want {cmd}")


class ReadyPullShards(unittest.TestCase):
    """checks.yml under R62, "each suite once per batch, on the batch PR", and its lean (the full Windows shards run on the ready
    pull_request, and the slices go). The scope job runs on a ready pull_request and waits on both skip outputs. The
    ReadyPullFullSuite class holds the step rules. Each case reads the real file."""

    def setUp(self):
        with open(CHECKS, encoding="utf-8") as f:
            self.text = f.read()

    def test_the_scope_job_runs_on_a_ready_pull_request_and_waits_on_both_skip_outputs(self):
        # Named failure: scope skips a ready PR, or runs a push or a scheduled run that its skip output says to skip.
        jobs = all_jobs(self.text)
        self.assertIn("scope", jobs, "no scope job")
        expr = jobs["scope"]["if"]
        self.assertIsNotNone(expr, "scope has no if")
        self.assertTrue(eval_if(expr, "pull_request", "true"), f"scope does not run on a ready pull_request: {expr}")
        self.assertFalse(eval_if(expr, "push", "true", push_skip="true"), f"scope runs when push-skip says skip: {expr}")
        self.assertFalse(eval_if(expr, "schedule", "true", nightly_skip="true"), f"scope runs when nightly-skip says skip: {expr}")
        self.assertTrue(eval_if(expr, "push", "true", push_skip=""), f"scope skips a push that push-skip leaves unset: {expr}")

    def test_a_shard_job_steps_carry_their_base_jobs_condition_text(self):
        # Named failure: a shard's steps carry a different condition from its base job's, so the two run on different events.
        # A text pin that R62 does not state: it holds under R62 because shards and bases change together.
        jobs = windows_jobs(self.text)
        shards = [n for n in jobs if shard_base(n)]
        self.assertTrue(shards, "no Windows shard jobs")
        for name in shards:
            base = shard_base(name)
            with self.subTest(job=name):
                want = read_scope_condition(jobs[base])
                self.assertIsNotNone(want, f"{base} steps carry no one scope condition")
                self.assertEqual(read_scope_condition(jobs[name]), want, f"{name} scope condition is not {base}'s")

    def test_the_windows_guard_job_keeps_its_full_suite_and_has_no_slice_step(self):
        # Named failure: checks-windows-guard still runs the windows-slice guard step, so a ready PR runs its cases twice.
        jobs = windows_jobs(self.text)
        self.assertIn(GUARD_JOB, jobs, f"no {GUARD_JOB} job")
        keys = [key(st) for st in jobs[GUARD_JOB]["steps"]]
        self.assertIn(GUARD_CMD, keys, f"{GUARD_JOB} has no full guard step")
        self.assertNotIn(GUARD_SLICE, keys, f"{GUARD_JOB} still runs {GUARD_SLICE!r}")

    def test_the_windows_merge_job_has_no_slice_step(self):
        # Named failure: checks-windows-merge still runs the windows-slice merge step, so a ready PR runs its cases twice.
        jobs = windows_jobs(self.text)
        self.assertIn("checks-windows-merge", jobs, "no checks-windows-merge job")
        keys = [key(st) for st in jobs["checks-windows-merge"]["steps"]]
        self.assertNotIn(SLICE, keys, f"checks-windows-merge still runs {SLICE!r}")

    def test_no_windows_slice_env_is_set_anywhere_in_checks_yml(self):
        # Named failure: a GUARD_TESTS or MERGE_TESTS windows-slice value is still set in a step, a job or the workflow.
        self.assertEqual(re.findall(r"(?:GUARD|MERGE)_TESTS:\s*windows-slice", self.text), [],
                         "a windows-slice env is still set in checks.yml")


class ReadyPullFullSuite(unittest.TestCase):
    """R62, "each suite once per batch, on the batch PR", with its lean: the Windows guard and merge shards and the rest jobs run
    on a ready pull_request whatever the scope flags say, so a docs-only ready PR runs them too. A draft pull_request with no
    flag set runs none of their steps, and a shard's draft guard stays on its job. Push, schedule and dispatch keep their
    flag rules. Each case reads the real file, so it is red until the change lands."""

    def setUp(self):
        with open(CHECKS, encoding="utf-8") as f:
            self.text = f.read()
        self.jobs = windows_jobs(self.text)

    def suite_jobs(self):
        # Scope first: the bases R62 names must exist before any of their steps is read.
        names = [n for n in self.jobs if full_suite_job(n)]
        for base in FULL_SUITE_BASES:
            self.assertIn(base, names, f"no {base} job in the full Windows suite")
        return names

    def test_a_docs_only_ready_pull_request_runs_every_step_of_the_full_suite_jobs(self):
        # Named failure: a step of a full-suite job is gated on a scope flag or on code, which a docs-only PR leaves false.
        for name in self.suite_jobs():
            job = self.jobs[name]
            for st in job["steps"]:
                with self.subTest(job=name, step=step_label(st)):
                    self.assertTrue(runs_on(job, st, "pull_request", "false", draft=False),
                                    f"{name} step {step_label(st)!r} does not run on a ready pull_request with every scope flag false")

    def test_a_shard_job_skips_a_draft_pull_request_at_job_level_and_runs_a_ready_one(self):
        # Control, green on the old code: the draft skip is the shard job's own if, and it stays.
        for name in self.suite_jobs():
            if shard_base(name) is None:
                continue
            expr = self.jobs[name]["if"]
            with self.subTest(job=name):
                self.assertIsNotNone(expr, f"{name} has no job-level if, so a draft pull_request starts its shard")
                self.assertFalse(eval_if(expr, "pull_request", "true", draft=True), f"{name} runs on a draft pull_request: {expr}")
                self.assertTrue(eval_if(expr, "pull_request", "false", draft=False), f"{name} does not run on a ready pull_request: {expr}")

    def test_no_step_of_a_full_suite_job_runs_on_a_draft_pull_request_with_no_flag_set(self):
        # Control, green on the old code: a draft with every flag false runs no suite step, so the R62 change must keep that.
        for name in self.suite_jobs():
            job = self.jobs[name]
            for st in job["steps"]:
                with self.subTest(job=name, step=step_label(st)):
                    self.assertFalse(runs_on(job, st, "pull_request", "false", draft=True),
                                     f"{name} step {step_label(st)!r} runs on a draft pull_request with no scope flag set")

    def test_the_full_suite_steps_run_on_push_schedule_and_dispatch_with_every_flag_set(self):
        # Control, green on the old code: push, schedule and dispatch keep the flag rule, and with every flag set they run.
        for name in self.suite_jobs():
            job = self.jobs[name]
            for st in job["steps"]:
                for event in ("push", "schedule", "workflow_dispatch"):
                    with self.subTest(job=name, step=step_label(st), event=event):
                        self.assertTrue(runs_on(job, st, event, "true", draft=False),
                                        f"{name} step {step_label(st)!r} does not run on {event} with every flag set")


class TopLevelOr(unittest.TestCase):
    def test_an_or_in_parens_or_quotes_is_not_top_level(self):
        self.assertFalse(top_level_or("(a == 'x||y') && (b || c)"))
        self.assertFalse(top_level_or("a == 'x(' && (b || c)"))  # a paren inside quotes opens no group

    def test_an_or_after_a_quoted_paren_is_top_level(self):
        self.assertTrue(top_level_or("a == 'x(' || b"))  # the or sits after the quoted paren, outside it
        self.assertTrue(top_level_or("(a) && b || c"))

    def test_a_lone_quote_makes_the_rest_unreadable(self):
        self.assertTrue(top_level_or("a == 'Don't' && b"))  # the quote after Don never closes: unreadable, so True
        self.assertTrue(top_level_or("a == 'x' && b == 'y"))


class ScanCases(unittest.TestCase):
    """The line scanner's cases: a comment opener inside quotes is text, a lone quote in text is text, a paren inside
    quotes does not close the scope condition, and a line in a block body is not a key."""

    def test_a_comment_opener_inside_quotes_is_text(self):
        self.assertEqual(yaml_scalar("'a # b' # note"), "a # b")
        self.assertEqual(yaml_scalar('"x #y" # z'), "x #y")
        self.assertEqual(yaml_scalar("${{ x == '#' }}"), "${{ x == '#' }}")
        self.assertEqual(yaml_scalar("# only a comment"), "")

    def test_a_lone_quote_in_text_is_text(self):
        self.assertEqual(yaml_scalar("echo Don't # note"), "echo Don't")
        self.assertEqual(yaml_scalar("Don't"), "Don't")

    def test_a_paren_inside_quotes_does_not_close_the_scope_condition(self):
        self.assertEqual(paren_prefix("(a == ')') && !cancelled()"), "a == ')'")
        self.assertIsNone(paren_prefix("a == 'x' && !cancelled()"))

    def test_a_block_body_line_is_not_a_key(self):
        text = ("jobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - name: body\n        run: |\n"
                "          # if: not a key\n          needs: not a key\n          echo \"Don't # stop\"\n"
                "        if: ${{ needs.scope.outputs.code == 'true' }}\n")
        job = all_jobs(text)["a"]
        self.assertIsNone(job["if"])
        self.assertIsNone(job["needs"])
        self.assertEqual(step_if(job["steps"][0]), "needs.scope.outputs.code == 'true'")


# Mod and map-skill tests: one step in each of the jobs checks (Linux), checks-windows and checks-macos, on
# the `mods` scope flag. The step runs .github/scripts/mod-tests.sh with no argument, and that script is the
# one home of both suites. A copy of either suite in a run step would drift, so no step may hold one. The
# script finds every *.test.mjs and *.test.js file under mods/ except node_modules, so a new mods/<name>/
# joins with no edit here. It carries the exit code of every file: a failing first or last file fails it.
# The checker self-tests (ModTestStepChecker) run on synthetic text and pass now: they show each defect is
# seen. MOD_SCRIPT_NAME marks the step that runs the script.
MOD_FLAG = "mods"
MOD_JOBS = ["checks", "checks-windows", "checks-macos"]
MOD_SCRIPT_NAME = "mod-tests.sh"
MOD_CMD = "bash .github/scripts/mod-tests.sh"
MOD_SCRIPT = os.environ.get("MOD_TESTS_SH") or os.path.join(HERE, "..", ".github", "scripts", MOD_SCRIPT_NAME)
STAMP = os.path.join(HERE, "..", ".github", "stamp.json")
CHECKOUT = re.compile(r"^(?:      - |        )uses:[ \t]*actions/checkout@", re.M)
# A copy of either suite in a run command: the mod glob, a bare `node --test`, or the skill folder.
INLINE_COPY = re.compile(r"\*\.test\.m?js|\bnode\s+--test\s*$|plain-english-map")


def mod_steps(text, job):
    """The steps of one job whose run names the mod-test script."""
    return [st for st in step_blocks(job_block(text, job)) if MOD_SCRIPT_NAME in (run_body(st) or "")]


def mods_scope_problems(text):
    """The scope job must export the mods output. Without it needs.scope.outputs.mods is empty and the step never runs."""
    scope = job_block(text, "scope") or ""
    if not re.search(r"^      mods:[ \t]*\$\{\{[ \t]*steps\.scope\.outputs\.mods[ \t]*\}\}[ \t]*$", scope, re.M):
        return ["scope job does not export the mods output"]
    return []


def job_mod_step_problems(text, job):
    """Pins on the one mod-test step of one job. [] when the step is right."""
    homes = mod_steps(text, job)
    if len(homes) != 1:
        return [f"{job}: {len(homes)} steps run {MOD_SCRIPT_NAME}, want 1"]
    st = homes[0]
    steps = step_blocks(job_block(text, job))
    i = steps.index(st)
    problems = []
    cond = unwrap(step_key(st, "if")) or ""
    scope_condition = paren_prefix(cond)  # the job's scope condition is checked with the job; the event may read there, not in the step
    own = cond[len(f"({scope_condition}) && "):] if scope_condition is not None else cond
    if "!cancelled()" not in cond:
        problems.append(f"{job}: mod step if lacks !cancelled(): {cond}")
    if f"needs.scope.outputs.{MOD_FLAG} == 'true'" not in cond:
        problems.append(f"{job}: mod step if does not read needs.scope.outputs.{MOD_FLAG}: {cond}")
    if "github.event_name" in own:
        problems.append(f"{job}: mod step if reads the event; the {MOD_FLAG} flag alone decides: {cond}")
    if step_key(st, "shell") != "bash":
        problems.append(f"{job}: mod step shell is {step_key(st, 'shell')}, want bash")
    if step_key(st, "continue-on-error") is not None:
        problems.append(f"{job}: mod step sets continue-on-error, which swallows the exit code")
    body = (run_body(st) or "").strip()
    if body != MOD_CMD:
        problems.append(f"{job}: mod step runs {body!r}, want {MOD_CMD!r} with no argument")
    checkout = [j for j, s in enumerate(steps) if CHECKOUT.search(s)]
    if not checkout or checkout[0] > i:
        problems.append(f"{job}: no actions/checkout before the mod step")
    if i != len(steps) - 1:
        problems.append(f"{job}: mod step is not the last step")
    return problems


def mods_step_problems(text):
    """Pins on the mod-test step of each job in MOD_JOBS, and no inline copy of either suite anywhere."""
    problems = []
    for job in MOD_JOBS:
        problems += job_mod_step_problems(text, job)
    problems += [f"a run step holds a copy of a mod or map-skill suite: {c!r}"
                 for c in run_commands(text) if INLINE_COPY.search(c)]
    return problems


def mods_problems(text):
    return mods_scope_problems(text) + mods_step_problems(text)


def script_problems(script):
    """Pins on the script's text. A pipe or `|| true` hides a failing file's exit code. Comment lines and
    `case` patterns (`mods|skill)`) are not pipes."""
    code = [re.sub(r"^\s*[\w|\"'*-]+\)", "", ln) for ln in script.splitlines() if not ln.lstrip().startswith("#")]
    body = "\n".join(code)
    problems = []
    if re.search(r"(?<!\|)\|(?!\|)", body):
        problems.append("mod script pipes a command: the pipe takes the last command's exit code")
    if re.search(r"\|\|\s*(?:true|:)(?!\w)", body):
        problems.append("mod script ends a command with || true or || :")
    return problems


class ScriptRun:
    """What one run of the mod script left: exit code, merged output, and the npm calls its shim saw."""
    def __init__(self, rc, out, npm):
        self.rc, self.out, self.npm = rc, out, npm


def run_mod_script(arg, files, dirs=(), find_exit=None, cwd=".", script=None):
    """Run the script file in a scratch repo, with `arg` (None for no argument). files maps a path to True
    (passes), False (fails), or the source text to write as is. dirs are empty folders to make. find_exit, when set, puts a `find` first on
    PATH that runs the real find and then exits with that code, as a find does that meets an error after it
    listed files. An `npm` shim records its arguments, so no run reaches the network. cwd is a repo-relative
    folder to start in."""
    with tempfile.TemporaryDirectory() as root:
        work = os.path.join(root, "repo")
        shim = os.path.join(root, "shim")
        os.makedirs(shim)
        for d in (*dirs, cwd, ".github/scripts"):
            os.makedirs(os.path.join(work, d), exist_ok=True)
        calls = os.path.join(root, "npm.log")
        shims = {"npm": f'#!/bin/sh\necho "$@" >> "{calls}"\nexit 0\n'}
        if find_exit is not None:
            shims["find"] = f'#!/bin/sh\n"{shutil.which("find")}" "$@"\nexit {find_exit}\n'
        for name, body in shims.items():
            with open(os.path.join(shim, name), "w", encoding="utf-8", newline="\n") as f:
                f.write(body)
            os.chmod(os.path.join(shim, name), 0o755)
        env = dict(os.environ, PATH=shim + os.pathsep + os.environ["PATH"])
        for rel, ok in files.items():
            full = os.path.join(work, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            text = ok if isinstance(ok, str) else ("// fixture\n" if ok else 'throw new Error("planted failure");\n')
            with open(full, "w", encoding="utf-8") as f:
                f.write(text)
        target = os.path.join(work, ".github", "scripts", MOD_SCRIPT_NAME)
        shutil.copyfile(script or MOD_SCRIPT, target)
        r = subprocess.run([shutil.which("bash"), "--noprofile", "--norc", target.replace("\\", "/")] + ([arg] if arg is not None else []),
                           cwd=os.path.join(work, cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, timeout=300, env=env)
        npm = open(calls, encoding="utf-8").read().splitlines() if os.path.exists(calls) else []
        return ScriptRun(r.returncode, r.stdout, npm)


SKILL_OK = {"skills/plain-english-map/tests/ok.test.mjs": True}
NPM_CI = "ci --ignore-scripts --no-audit --no-fund"
# A mod test that reads its input, as a test that reads stdin does: it takes every line the loop has left.
STDIN_READER = 'import { readFileSync } from "node:fs";\nreadFileSync(0, "utf8");\n'


class ModTestStep(unittest.TestCase):
    def setUp(self):
        with open(CHECKS, encoding="utf-8") as f:
            self.text = f.read()

    def test_the_scope_job_exports_the_mods_flag(self):
        self.assertEqual(mods_scope_problems(self.text), [])

    def test_each_of_the_three_jobs_runs_the_script_in_one_pinned_step(self):
        for job in MOD_JOBS:
            with self.subTest(job=job):
                self.assertEqual(job_mod_step_problems(self.text, job), [])

    def test_no_run_step_holds_a_copy_of_either_suite(self):
        copies = [c for c in run_commands(self.text) if INLINE_COPY.search(c)]
        self.assertEqual(copies, [])

    def test_checks_stays_a_required_check_and_mods_adds_no_name(self):
        """Control, green now: the step rides jobs that are already required, so the list gains no name."""
        with open(STAMP, encoding="utf-8") as f:
            required = json.load(f)["merge"]["requiredChecks"]
        if required == "protection":  # the list lives in branch protection, which no offline test reads: check only that the workflow gains no mod job
            self.assertEqual([n for n in all_jobs(self.text) if "mod" in n.lower()], [])
            return
        for job in MOD_JOBS:
            self.assertIn(job, required)
        self.assertEqual([n for n in required if "mod" in n.lower()], [])


@unittest.skipUnless(shutil.which("bash") and shutil.which("node") and shutil.which("find"), "needs bash, node and find on PATH")
class ModTestScript(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.exists(MOD_SCRIPT), f"{MOD_SCRIPT} is missing, so no job runs a mod test")

    def test_the_script_text_has_no_pipe_and_no_or_true(self):
        with open(MOD_SCRIPT, encoding="utf-8") as f:
            self.assertEqual(script_problems(f.read()), [])

    def test_the_script_fails_when_any_mod_test_fails(self):
        cases = [
            ("all pass", {"mods/a/a.test.mjs": True, "mods/b/b.test.mjs": True}, True),
            ("first file fails", {"mods/a/first.test.mjs": False, "mods/b/b.test.mjs": True}, False),
            ("last file fails, in a new mod", {"mods/a/a.test.mjs": True, "mods/zz-new/last.test.mjs": False}, False),
            ("nested tests/ file fails", {"mods/a/a.test.mjs": True, "mods/a/tests/b.test.mjs": False}, False),
            ("*.test.js file fails", {"mods/a/a.test.mjs": True, "mods/a/c.test.js": False}, False),
            # Control: a dependency's own test under node_modules is not ours to run.
            ("node_modules test fails", {"mods/a/a.test.mjs": True, "mods/a/node_modules/dep/d.test.js": False}, True),
        ]
        for label, files, ok in cases:
            with self.subTest(case=label):
                r = run_mod_script("mods", files)
                self.assertEqual(r.rc == 0, ok, f"{label}: exit {r.rc}\n{r.out}")

    def test_a_mod_test_that_reads_stdin_does_not_hide_the_files_after_it(self):
        # Named cause: phase_mods feeds the file list on the loop's stdin, so a file that reads stdin takes the lines
        # after it, and the loop ends before the failing file runs. find does not sort, so the script's own list order
        # sets the roles: the reader first, the failing file second, a passing file third.
        names = ["mods/a/a.test.mjs", "mods/b/b.test.mjs", "mods/c/c.test.mjs"]
        probe = run_mod_script("list", {**SKILL_OK, **{name: True for name in names}})
        self.assertEqual(probe.rc, 0, probe.out)
        listed = [line for line in probe.out.splitlines() if line in names]
        self.assertEqual(len(listed), 3, "list does not name the three fixture files:\n" + probe.out)
        for label, first in (("file reads stdin", STDIN_READER), ("control: first file reads no stdin", True)):
            with self.subTest(case=label):
                r = run_mod_script("mods", {listed[0]: first, listed[1]: False, listed[2]: True})
                self.assertIn("planted failure", r.out, f"{label}: the failing second file did not run\n{r.out}")
                self.assertNotEqual(r.rc, 0, f"{label}: the phase exited 0 although the second file fails\n{r.out}")

    def test_the_script_fails_when_it_finds_no_test_or_find_errors(self):
        """`done < <(find ...)` drops find's exit code, and an empty loop exits 0 with nothing run."""
        ok = {"mods/a/a.test.mjs": True}
        cases = [
            ("mods/ is missing", {}, (), None),
            ("mods/ is empty", {}, ("mods",), None),
            ("mods/ holds no test file", {"mods/a/readme.md": True}, (), None),
            ("only a node_modules test file", {"mods/a/node_modules/dep/d.test.js": True}, (), None),
            ("find exits 2 after it listed a passing file", ok, (), 2),
        ]
        for label, files, dirs, find_exit in cases:
            with self.subTest(case=label):
                r = run_mod_script("mods", files, dirs, find_exit)
                self.assertNotEqual(r.rc, 0, f"{label}: the script exited 0\n{r.out}")
        self.assertEqual(run_mod_script("mods", ok).rc, 0)  # control: one passing file and a clean find pass

    def test_the_script_prints_the_file_count_before_it_runs_them(self):
        files = {"mods/a/a.test.mjs": True, "mods/a/tests/b.test.mjs": True, "mods/c/c.test.js": False,
                 "mods/a/node_modules/dep/d.test.js": True, "mods/a/readme.md": True}
        r = run_mod_script("mods", files)
        lines = r.out.splitlines()
        self.assertIn("mod tests: 3 files", lines, r.out)
        self.assertLess(r.out.index("mod tests: 3 files"), r.out.index("planted failure"), "the count came after a run")

    def test_the_script_runs_from_the_repo_root_whatever_the_cwd(self):
        r = run_mod_script("mods", {"mods/a/a.test.mjs": True}, cwd="mods/a")
        self.assertEqual(r.rc, 0, r.out)
        self.assertIn("mod tests: 1 files", r.out.splitlines())

    def test_an_unknown_argument_exits_2_and_runs_nothing(self):
        for arg in ("bogus", "all", "--help", "MODS"):
            with self.subTest(arg=arg):
                r = run_mod_script(arg, dict(SKILL_OK, **{"mods/a/a.test.mjs": True}))
                self.assertEqual(r.rc, 2, r.out)
                self.assertEqual(r.npm, [])
                self.assertNotIn("mod tests:", r.out)

    def test_the_mods_argument_runs_phase_one_only(self):
        r = run_mod_script("mods", dict(SKILL_OK, **{"mods/a/a.test.mjs": True}))
        self.assertEqual((r.rc, r.npm), (0, []), r.out)

    def test_the_skill_argument_runs_phase_two_only(self):
        # A failing mod file must not matter: phase one does not run.
        r = run_mod_script("skill", dict(SKILL_OK, **{"mods/a/a.test.mjs": False}))
        self.assertEqual(r.rc, 0, r.out)
        self.assertEqual(r.npm, [NPM_CI])
        self.assertNotIn("mod tests:", r.out)

    def test_the_skill_phase_fails_when_a_skill_test_fails(self):
        r = run_mod_script("skill", {"skills/plain-english-map/tests/bad.test.mjs": False})
        self.assertNotEqual(r.rc, 0, r.out)

    def test_no_argument_runs_both_phases_and_phase_two_runs_after_a_phase_one_failure(self):
        mods_ok, mods_bad = {"mods/a/a.test.mjs": True}, {"mods/a/a.test.mjs": False}
        skill_bad = {"skills/plain-english-map/tests/bad.test.mjs": False}
        cases = [
            ("both pass", dict(SKILL_OK, **mods_ok), True),
            ("phase one fails", dict(SKILL_OK, **mods_bad), False),
            ("phase two fails", dict(skill_bad, **mods_ok), False),
            ("both fail", dict(skill_bad, **mods_bad), False),
        ]
        for label, files, ok in cases:
            with self.subTest(case=label):
                r = run_mod_script(None, files)
                self.assertEqual(r.rc == 0, ok, f"{label}: exit {r.rc}\n{r.out}")
                self.assertEqual(r.npm, [NPM_CI], f"{label}: phase two did not run, or ran twice")
                self.assertIn("mod tests: 1 files", r.out.splitlines())


MOD_CHECKOUT = ("      - uses: actions/checkout@08c6903cd8c0fde910a37f88322edcfb5dd907a8 # v5.0.0\n"
                "        with:\n          fetch-depth: 0\n\n")
MOD_STEP = ("      - name: Mod and map-skill tests\n"
            "        if: ${{ !cancelled() && needs.scope.outputs.mods == 'true' }}\n"
            "        shell: bash\n"
            f"        run: {MOD_CMD}\n")
MOD_SCRIPT_TEXT = ("#!/usr/bin/env bash\n"
                   "# Phase one.\n"
                   "case \"${1:-}\" in\n"
                   "  mods|skill|\"\") ;;\n"
                   "  *) exit 2 ;;\n"
                   "esac\n"
                   "list=$(find mods -name node_modules -prune -o -name '*.test.mjs' -print) || exit 1\n"
                   "fail=0\n"
                   "while IFS= read -r f; do\n"
                   "  node \"$f\" || fail=1\n"
                   "done <<< \"$list\"\n"
                   "exit \"$fail\"\n")


def mod_doc(steps=None, extra=None, checkout=True, scope_out=True):
    """A synthetic checks fragment: the three jobs, each with a checkout, then its steps. `steps` maps a job to
    its step text (default MOD_STEP). `extra` maps a job to a step added after the mod step."""
    steps, extra = steps or {}, extra or {}
    scope = "      mods: ${{ steps.scope.outputs.mods }}\n" if scope_out else "      code: ${{ steps.scope.outputs.code }}\n"
    jobs = "".join(f"  {j}:\n    runs-on: ubuntu-latest\n    needs: scope\n    steps:\n"
                   + (MOD_CHECKOUT if checkout else "") + steps.get(j, MOD_STEP) + extra.get(j, "")
                   for j in MOD_JOBS)
    return "jobs:\n  scope:\n    outputs:\n" + scope + jobs + "  pointer-windows:\n    runs-on: windows-latest\n    steps:\n      - run: echo\n"


def only(job, body):
    """The steps argument of mod_doc that changes one job's mod step."""
    return {job: body}


class ModTestStepChecker(unittest.TestCase):
    def test_the_checker_passes_the_right_step(self):
        self.assertEqual(mods_problems(mod_doc()), [])

    def test_the_checker_sees_each_defect(self):
        inline_glob = ("      - name: Mod tests\n        run: |\n"
                       "          find mods -name '*.test.mjs' -print\n")
        inline_skill = "      - name: Skill\n        run: |\n          cd skills/plain-english-map/tests\n          node --test\n"
        defects = {
            "no step in checks": mod_doc(steps=only("checks", "")),
            "step missing from checks-windows": mod_doc(steps=only("checks-windows", "")),
            "step missing from checks-macos": mod_doc(steps=only("checks-macos", "")),
            "step passes an argument": mod_doc(steps=only("checks-macos", MOD_STEP.replace(".sh\n", ".sh mods\n"))),
            "step passes skill": mod_doc(steps=only("checks", MOD_STEP.replace(".sh\n", ".sh skill\n"))),
            "step calls another script": mod_doc(steps=only("checks", MOD_STEP.replace("mod-tests.sh", "mod-tests.sh; echo"))),
            "two steps in one job": mod_doc(steps=only("checks-windows", MOD_STEP + MOD_STEP)),
            "inline copy of the mod glob in checks": mod_doc(extra={"checks": inline_glob}),
            "inline copy of the mod glob in checks-windows": mod_doc(extra={"checks-windows": inline_glob}),
            "inline copy of the skill run": mod_doc(extra={"checks": inline_skill}),
            "old mod step kept beside the new one": mod_doc(steps=only("checks", inline_glob + MOD_STEP)),
            "wrong flag": mod_doc(steps=only("checks-windows", MOD_STEP.replace("outputs.mods", "outputs.code"))),
            "no !cancelled()": mod_doc(steps=only("checks-macos", MOD_STEP.replace("!cancelled() && ", ""))),
            "reads the event": mod_doc(steps=only("checks", MOD_STEP.replace("== 'true' }}", "== 'true' && github.event_name != 'pull_request' }}"))),
            "no shell": mod_doc(steps=only("checks-windows", MOD_STEP.replace("        shell: bash\n", ""))),
            "shell sh": mod_doc(steps=only("checks-macos", MOD_STEP.replace("shell: bash", "shell: sh"))),
            "shell pwsh": mod_doc(steps=only("checks-windows", MOD_STEP.replace("shell: bash", "shell: pwsh"))),
            "continue-on-error": mod_doc(steps=only("checks", MOD_STEP.replace("        shell: bash\n", "        shell: bash\n        continue-on-error: true\n"))),
            "no checkout": mod_doc(checkout=False),
            "a step after the mod step": mod_doc(extra={"checks-macos": "      - run: echo\n"}),
            "scope lacks the mods output": mod_doc(scope_out=False),
        }
        for label, doc in defects.items():
            with self.subTest(defect=label):
                self.assertTrue(mods_problems(doc), label)

    def test_each_defect_names_its_job(self):
        for job in MOD_JOBS:
            with self.subTest(job=job):
                problems = mods_step_problems(mod_doc(steps=only(job, "")))
                self.assertEqual([p.split(":")[0] for p in problems], [job], problems)

    def test_the_checker_misreads_no_comment_or_block_scalar(self):
        # Rows: a comment that names the script is no step, and a `run: |` block that holds only the script line is
        # the step. Named failure: a commented-out step reads as present, or a block step as absent.
        commented = "      # run: bash .github/scripts/mod-tests.sh\n"
        self.assertTrue(mods_step_problems(mod_doc(steps=only("checks", commented))))
        block = MOD_STEP.replace(f"run: {MOD_CMD}\n", f"run: |\n          {MOD_CMD}\n")
        self.assertEqual(mods_step_problems(mod_doc(steps=only("checks", block))), [])
        trailing = mod_doc(extra={"checks": "      # find mods -name '*.test.mjs'\n"})
        self.assertEqual(mods_step_problems(trailing), [])  # a comment line is not a run

    def test_the_script_checker_sees_each_defect(self):
        self.assertEqual(script_problems(MOD_SCRIPT_TEXT), [])  # control: case patterns and || are no pipe
        defects = {
            "pipe": MOD_SCRIPT_TEXT.replace('node "$f" || fail=1', 'node "$f" | tail -1'),
            "or true": MOD_SCRIPT_TEXT.replace("|| fail=1", "|| true"),
            "or colon": MOD_SCRIPT_TEXT.replace("|| fail=1", "|| :"),
            "pipe after a case pattern line": MOD_SCRIPT_TEXT.replace("exit 2 ;;", "echo x | cat ;;"),
        }
        for label, text in defects.items():
            with self.subTest(defect=label):
                self.assertTrue(script_problems(text), label)
        commented = MOD_SCRIPT_TEXT + "# node a | tail -1 || true\n"
        self.assertEqual(script_problems(commented), [])  # a comment line is not code


# ---- every test file runs in a CI step. A test file that no run step names never fails a pull
# request, so its red stays invisible. Failure classes: (a) product, a test file has no run line in
# checks.yml; (b) test, this parser misreads a run line (a comment, a quote, a block scalar); (c) stale,
# a test file was renamed or removed and its run line was not. Scope: the tracked files whose basename
# matches TEST_FILE. Tracked only, because a file git does not track, or a copy under node_modules, is
# not a suite CI runs. A `_test_` name is a helper (lint/_test_git.py) and never matches. mutate_*.py is
# not a suite (mutate_shared.py is plumbing). The mod and map-skill tests are not listed by name: COLLECTOR
# prints them, and a file it prints counts as covered only when a run step is exactly MOD_CMD, since that
# step is what runs them.
REPO = os.path.normpath(os.path.join(HERE, ".."))
COLLECTOR = MOD_CMD.split()[-1]  # the path MOD_CMD runs, so the collector's path has one home
TEST_FILE = re.compile(r"^(?:test_.*\.(?:py|sh|mjs)|.*\.test\.(?:mjs|js|ps1))$")


def strip_comment(text):
    """`text` up to a `#` that opens a shell comment: at the start, or after a space, outside quotes. A quote opens
    only at the start of a word, so the apostrophe in `don't` is text and a `#` after it still opens a comment."""
    quote = ""
    for i, ch in enumerate(text):
        if quote:
            quote = "" if ch == quote else quote
        elif ch in "\"'" and (i == 0 or text[i - 1] in " \t(=:"):
            quote = ch
        elif ch == "#" and (i == 0 or text[i - 1] in " \t"):
            return text[:i]
    return text


# A block scalar head: `|` or `>`, then an optional indent digit and chomping sign, then an optional comment.
BLOCK_HEAD = re.compile(r"^[|>][0-9+-]*(?:[ \t]+#.*)?$")
RUN_KEY = re.compile(r"^(\s*)(- )?run:[ \t]*(.*)$")


def run_commands(text):
    """Each shell command a workflow runs: a one-line `run:` value, and each line of a block scalar
    under `run:`. A block holds the lines indented deeper than its key, so a sibling key (`env:`) ends
    it. A comment line, or a trailing comment, is not a command."""
    commands, block = [], None  # block: the column of the open run key
    for line in text.splitlines():
        body = line.strip()
        column = len(line) - len(line.lstrip(" "))
        if block is not None and body and column <= block:
            block = None
        if block is not None:
            commands.append(strip_comment(body))
            continue
        found = RUN_KEY.match(line)
        if not found:
            continue
        key_column = len(found.group(1)) + (2 if found.group(2) else 0)  # `- run:` keys sit after the dash
        value = found.group(3).strip()
        if BLOCK_HEAD.match(value):
            block = key_column
        else:
            commands.append(strip_comment(value))
    return commands


# A run step may name a path with a `./` or `$VAR/` (or `${VAR}/`) prefix. The prefix is dropped first.
# A folder in front of the path (`hooks/lint/test_x.py`) still names another file.
PATH_PREFIX = re.compile(r"(?<![\w.$/-])(?:\./|\$\{?\w+\}?/)")


def names_path(commands, path):
    """True when a command names `path` as a whole word, after a path prefix is dropped.
    `test_x_stop.py` does not name `test_x.py`, and `hooks/lint/test_x.py` does not name `lint/test_x.py`."""
    pattern = re.compile(r"(?<![\w./-])" + re.escape(path) + r"(?![\w./-])")
    return any(pattern.search(PATH_PREFIX.sub("", command)) for command in commands)


def find_test_files(root):
    """Repo-relative posix paths of the tracked test files under `root`, sorted. git lists the paths, so an
    untracked file is not a test. A folder that is not a git repo fails the read and raises, so it never reads
    as holding no tests."""
    listed = subprocess.run(["git", "ls-files", "-z"], cwd=root, check=True, stdout=subprocess.PIPE).stdout
    paths = [p for p in listed.decode("utf-8").split("\0") if p]
    return sorted(p for p in paths if TEST_FILE.match(p.split("/")[-1]))


def runs_collector(commands):
    """True when a run step is exactly the collector's command. `list`, `mods` and an echo of the command run something else."""
    return any(command.strip() == MOD_CMD for command in commands)


def collected_files(root):
    """The files the collector prints for `list` in `root`, one repo-relative path per line. A nonzero exit raises,
    so a collector that fails cannot read as an empty list."""
    run = subprocess.run([shutil.which("bash") or "bash", COLLECTOR, "list"], cwd=root,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if run.returncode != 0:
        raise RuntimeError("%s list exits %d: %s" % (COLLECTOR, run.returncode, run.stderr.strip()))
    return [line for line in run.stdout.splitlines() if line]


class CiCoverage(unittest.TestCase):
    def test_every_test_file_runs_in_a_ci_step(self):
        with open(CHECKS, encoding="utf-8") as handle:
            commands = run_commands(gating_text(handle.read()))
        collected = set(collected_files(REPO)) if runs_collector(commands) else set()
        missing = [p for p in find_test_files(REPO) if p not in collected and not names_path(commands, p)]
        # No rename remedy: a `_test_` name is outside the scope, so a rename would hide a real test from this check.
        self.assertEqual(missing, [], "no run step in checks.yml covers: " + ", ".join(missing)
                         + ". Add a run step in .github/workflows/checks.yml.")

    def test_a_comment_line_is_not_a_run(self):
        # Rows: a comment line, a trailing comment, and a comment line inside a block. Named failure: a
        # commented-out suite counted as run, so CI looks covered when it is not.
        cases = [
            ("comment line", "      - run: echo\n      # run: python3 lint/test_x.py\n"),
            ("trailing comment", "      - run: echo  # python3 lint/test_x.py\n"),
            ("comment line in a block", "      - run: |\n          echo start\n          # python3 lint/test_x.py\n"),
            ("comment after a lone quote", "      - run: echo don't  # python3 lint/test_x.py\n"),
        ]
        for case, text in cases:
            with self.subTest(case):
                self.assertFalse(names_path(run_commands(text), "lint/test_x.py"))

    def test_a_hash_inside_quotes_is_not_a_comment(self):
        text = '      - run: echo "a # b" && python3 lint/test_x.py\n'
        self.assertTrue(names_path(run_commands(text), "lint/test_x.py"))

    def test_a_lone_quote_does_not_hide_a_run(self):
        # Rows: a lone quote in a run keeps the run, and a lone quote in a step name is not a run.
        # Named failure: a quote hides a suite or fakes one.
        cases = [
            ("quote in a run", "      - run: echo don't && python3 lint/test_x.py\n", True),
            ("quote in a name", "      - name: Don't skip lint/test_x.py\n", False),
        ]
        for case, text, runs in cases:
            with self.subTest(case):
                self.assertEqual(bool(names_path(run_commands(text), "lint/test_x.py")), runs)

    def test_a_block_scalar_line_is_a_run(self):
        text = "      - run: |\n          echo start\n          python3 lint/test_x.py\n"
        self.assertTrue(names_path(run_commands(text), "lint/test_x.py"))

    def test_a_block_ends_at_the_next_step(self):
        text = ("      - run: |\n          echo\n"
                "      - name: lint/test_x.py\n"
                "      - run: python3 lint/test_y.py\n")
        commands = run_commands(text)
        self.assertFalse(names_path(commands, "lint/test_x.py"))
        self.assertTrue(names_path(commands, "lint/test_y.py"))

    def test_a_longer_or_deeper_name_does_not_cover_a_shorter_one(self):
        text = "      - run: python3 lint/test_x_stop.py\n      - run: python3 mylint/test_x.py\n"
        self.assertFalse(names_path(run_commands(text), "lint/test_x.py"))

    def test_a_chomping_block_indicator_is_a_block(self):
        # Heads "| # c" and ">- # c": a trailing comment after the indicator still opens a block.
        # Named failure: a block run is missed.
        for head in ("|-", ">-", "|+", "| # c", ">- # c"):
            with self.subTest(head=head):
                text = "      - run: %s\n          echo start\n          python3 lint/test_x.py\n" % head
                self.assertTrue(names_path(run_commands(text), "lint/test_x.py"))

    def test_a_dot_slash_path_is_a_run(self):
        text = "      - run: python3 ./lint/test_x.py\n"
        self.assertTrue(names_path(run_commands(text), "lint/test_x.py"))

    def test_a_workspace_variable_path_is_a_run(self):
        for path in ("$GITHUB_WORKSPACE/lint/test_x.py", "${GITHUB_WORKSPACE}/lint/test_x.py"):
            with self.subTest(path=path):
                text = "      - run: python3 %s\n" % path
                self.assertTrue(names_path(run_commands(text), "lint/test_x.py"))

    def test_a_sibling_key_ends_a_run_block(self):
        text = ("      - run: |\n          echo start\n"
                "        env:\n          MERGE_TESTS: lint/test_x.py\n")
        self.assertFalse(names_path(run_commands(text), "lint/test_x.py"))

    def test_a_path_under_another_folder_is_not_a_run(self):
        for path in ("hooks/lint/test_x.py", "$GITHUB_WORKSPACE/hooks/lint/test_x.py"):
            with self.subTest(path=path):
                text = "      - run: python3 %s\n" % path
                self.assertFalse(names_path(run_commands(text), "lint/test_x.py"))

    def test_an_unreadable_folder_fails_the_scan(self):
        with self.assertRaises(OSError):
            find_test_files(os.path.join(HERE, "no-such-folder-for-the-scan"))


# ---- CI coverage cases on fixture repos. Each case runs the real CiCoverage case on a fixture: the module globals
# REPO and CHECKS are swapped for the fixture folder and its checks.yml, and the case reads what that run says.
# So a case tests the real scan, not a copy of it. The scan must read REPO and CHECKS at call time.

RUN_FOLDER = None  # set by setUpModule, so an import makes no folder
ENV_PATCH = None


def setUpModule():
    global RUN_FOLDER, ENV_PATCH
    import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
    RUN_FOLDER = _test_temp.run_folder()
    # A git hook sets these. A fixture git would then write the real index. The patch restores os.environ after the run.
    ENV_PATCH = mock.patch.dict(os.environ)
    ENV_PATCH.start()
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        os.environ.pop(name, None)


def tearDownModule():
    if ENV_PATCH:
        ENV_PATCH.stop()
    if RUN_FOLDER and os.path.isdir(RUN_FOLDER):
        sys.path.insert(0, os.path.join(HERE, "..", "testing"))
        import tracked_tree  # noqa: E402  test-temp-standard: teardown removes the run folder (testing/tracked_tree.py)
        tracked_tree.rm_tree(RUN_FOLDER)


def write_file(root, rel, text):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def checks_yml(*jobs):
    """checks.yml text, in the layout lint/workflow_steps.py reads. A job is (name, runs-on, steps), or (name, runs-on,
    steps, job keys): job keys are lines such as `if: false`, at 4 spaces. A step is a run command, or a list of its
    lines: the first line is the step's first key, on the `      - ` line, and the rest are keys at 8 spaces."""
    text = "jobs:\n"
    for name, runs_on, steps, *rest in jobs:
        text += "  %s:\n    runs-on: %s\n" % (name, runs_on)
        text += "".join("    %s\n" % key for key in (rest[0] if rest else ()))
        text += "    steps:\n"
        for step in steps:
            lines = step if isinstance(step, list) else ["run: %s" % step]
            text += "      - %s\n" % lines[0] + "".join("        %s\n" % line for line in lines[1:])
    return text


def collector_stub(paths, exit_code):
    """A stand-in for .github/scripts/mod-tests.sh: `list` prints `paths`, then exits `exit_code`."""
    lines = "".join("printf '%%s\\n' %s\n" % shlex.quote(path) for path in paths)
    return '#!/usr/bin/env bash\nif [ "${1:-}" = list ]; then\n%sexit %d\nfi\nexit 0\n' % (lines, exit_code)


def make_repo(tracked=(), untracked=(), checks="", collected=(), collector_exit=0, git=True):
    """A fixture repo in a new folder of this run. `tracked` paths are git-added, `untracked` paths are on disk
    only, and each file holds one line. `checks` is .github/workflows/checks.yml. With git False the folder is no
    repo. Returns the folder."""
    root = tempfile.mkdtemp(prefix="cov-", dir=RUN_FOLDER)
    for rel in (*tracked, *untracked):
        write_file(root, rel, "fixture\n")
    write_file(root, ".github/workflows/checks.yml", checks)
    write_file(root, ".github/scripts/mod-tests.sh", collector_stub(collected, collector_exit))
    if git:
        subprocess.run(["git", "init", "-q"], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if tracked:
            subprocess.run(["git", "add", "--"] + list(tracked), cwd=root, check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return root


def scan(root):
    """The real CiCoverage case run on fixture `root`: None when it passes, else the error it raised."""
    checks = os.path.join(root, ".github", "workflows", "checks.yml")
    with mock.patch.dict(globals(), {"REPO": root, "CHECKS": checks}):
        try:
            CiCoverage("test_every_test_file_runs_in_a_ci_step").test_every_test_file_runs_in_a_ci_step()
        except Exception as error:  # the gap report is an AssertionError; a failed collector raises its own error
            return error
    return None


def gap_text(root):
    """The gap report on fixture `root`, "" when the case passes. An error that is not a gap report is raised."""
    error = scan(root)
    if error is None:
        return ""
    if isinstance(error, AssertionError):
        return str(error)
    raise error


TEST_FILE_CHECKS = checks_yml(("checks", "ubuntu-latest", ["python3 lint/test_ok.py"]))  # names one test file
COLLECTED = ("mods/a/x.test.mjs", "skills/plain-english-map/tests/y.test.mjs")


class CiCoverageScope(unittest.TestCase):
    def test_tracked_js_and_mjs_test_files_are_reported(self):
        # Named cause: the scope reads only test_*.py, test_*.sh and *.test.ps1, so a JS test file is missed.
        text = gap_text(make_repo(tracked=["lint/test_ok.py", "lint/test_x.mjs", "lib/y.test.mjs", "lib/z.test.js"],
                                  checks=TEST_FILE_CHECKS))
        for path in ("lint/test_x.mjs", "lib/y.test.mjs", "lib/z.test.js"):
            with self.subTest(path=path):
                self.assertIn(path, text, "a tracked test file with no run line is not reported")
        self.assertNotIn("lint/test_ok.py", text, "a test file that a run step names is reported")

    def test_an_untracked_test_file_is_not_reported(self):
        # Named cause: the scan walks the disk, so a test file that git does not track counts.
        text = gap_text(make_repo(tracked=["lint/test_ok.py"], untracked=["lint/test_y.py"], checks=TEST_FILE_CHECKS))
        self.assertNotIn("lint/test_y.py", text, "an untracked test file is reported: the scan read the disk, not git")

    def test_a_js_file_under_untracked_node_modules_is_not_reported(self):
        text = gap_text(make_repo(tracked=["lint/test_ok.py", "lib/a.test.js"],
                                  untracked=["node_modules/pkg/b.test.js"], checks=TEST_FILE_CHECKS))
        with self.subTest("tracked"):
            self.assertIn("lib/a.test.js", text, "a tracked *.test.js with no run line is not reported")
        with self.subTest("untracked"):
            self.assertNotIn("node_modules/pkg/b.test.js", text,
                             "a *.test.js under an untracked node_modules is reported")

    def test_a_helper_named_with_an_underscore_is_not_reported(self):
        # A `_test_` name is a helper (lint/_test_git.py). The test-file row shows the scope is live, so the
        # helper rows cannot pass on a scan that reads nothing.
        helpers = ["lint/_test_helper.py", "lint/_test_helper.mjs", "lint/_test_git.mjs"]
        text = gap_text(make_repo(tracked=["lint/test_ok.py", "lint/test_x.mjs"] + helpers, checks=TEST_FILE_CHECKS))
        with self.subTest("test file"):
            self.assertIn("lint/test_x.mjs", text, "a tracked test_*.mjs with no run line is not reported")
        for helper in helpers:
            with self.subTest(helper=helper):
                self.assertNotIn(helper, text, "a helper named _test_* is reported as a test")

    def test_an_empty_git_repo_lists_no_test_files(self):
        # The empty state. Splitting git's empty output must not give one blank name.
        self.assertEqual(find_test_files(make_repo(checks=TEST_FILE_CHECKS)), [],
                         "an empty git repo lists a file it does not track")

    def test_a_name_with_a_space_or_non_ascii_comes_back_exact(self):
        # Without -z, git quotes such a name and the scan no longer matches the file.
        names = ["lint/test_my file.py", "lint/test_caf\u00e9.py"]
        self.assertEqual(find_test_files(make_repo(tracked=names, checks=TEST_FILE_CHECKS)), sorted(names),
                         "a tracked name with a space or a non-ASCII character came back altered")

    def test_a_non_git_folder_raises(self):
        # Named cause: the scan lists tracked files through git, so a folder that is no repo must fail the read.
        root = make_repo(untracked=["lint/test_x.py"], git=False)
        probe = subprocess.run(["git", "rev-parse"], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertNotEqual(probe.returncode, 0, "the fixture folder is inside a git repo, so the case proves nothing")
        try:
            found = find_test_files(root)
        except (OSError, subprocess.CalledProcessError):
            return
        self.fail("find_test_files listed %s for a folder that is not a git repo; it must raise" % found)

    def test_a_file_named_only_in_a_windows_job_is_covered(self):
        checks = checks_yml(("checks", "ubuntu-latest", ["python3 lint/test_ok.py"]),
                            ("checks-windows", "windows-latest", ["python lint/test_win.py"]))
        text = gap_text(make_repo(tracked=["lint/test_ok.py", "lint/test_win.py"], checks=checks))
        self.assertNotIn("lint/test_win.py", text, "a file that only a windows-latest job names is reported")

    def test_the_gap_report_names_the_run_step_and_no_rename(self):
        # Named failure: the report offers a rename to `_test_<name>`. A `_test_` name is outside the scope, so the
        # rename hides a real test from the check.
        text = gap_text(make_repo(tracked=["lint/test_x.py"], checks=TEST_FILE_CHECKS))
        with self.subTest("file"):
            self.assertIn("lint/test_x.py", text, "an unnamed test file is not reported")
        with self.subTest("add a run step"):
            self.assertIn("run step", text, "the gap report does not name the add-a-run-step remedy")
        with self.subTest("no rename"):
            self.assertNotIn("rename", text, "the gap report offers a rename, which hides a real test from the scope")
        with self.subTest("no _test_ name"):
            self.assertNotIn("_test_", text, "the gap report names a _test_ file, which the scope does not read")

    def test_a_test_dot_file_gets_a_run_step_remedy_only(self):
        # Named failure: the report offers a rename to _test_<name> for a `.test.*` file. That name still matches the
        # scope, so the rename would not clear the gap.
        text = gap_text(make_repo(tracked=["lint/test_ok.py", "lib/_test_x.test.mjs"], checks=TEST_FILE_CHECKS))
        with self.subTest("file"):
            self.assertIn("lib/_test_x.test.mjs", text, "a tracked .test.mjs with no run line is not reported")
        with self.subTest("run step"):
            self.assertIn("run step", text, "the gap report does not name the run-step remedy")
        with self.subTest("no rename"):
            self.assertNotIn("rename", text, "the gap report offers a rename for a .test.* file, which stays in scope")


# The sentinel is tracked and named by no run step, so every gating fixture reports it. Its report shows the scan read the
# fixture, and that is checked before any assert on GATING_FILE (P7: assert the scope before the subject).
GAP_SENTINEL = "lint/test_gap.py"
GATING_FILE = "lint/test_x.py"


class CiCoverageGating(unittest.TestCase):
    """A step or job that cannot fail a pull request does not count its file as covered. Each row runs the real scan."""

    def assert_gap(self, checks, reported, cause):
        text = gap_text(make_repo(tracked=[GAP_SENTINEL, GATING_FILE], checks=checks))
        self.assertIn(GAP_SENTINEL, text, "the scan did not report the unnamed sentinel, so it read no fixture")
        if reported:
            self.assertIn(GATING_FILE, text, cause)
        else:
            self.assertNotIn(GATING_FILE, text, cause)

    def test_a_gating_step_is_reported(self):
        # Rows: a step with continue-on-error: true, or a `${{ true }}` form (the spacing varies), or an always-false if:,
        # with the key below or on the dash line.
        rows = [
            ("continue-on-error: true", ["run: python3 lint/test_x.py", "continue-on-error: true"]),
            ("continue-on-error: ${{ true }}", ["run: python3 lint/test_x.py", "continue-on-error: ${{ true }}"]),
            ("continue-on-error: ${{true}}", ["run: python3 lint/test_x.py", "continue-on-error: ${{true}}"]),
            ("if: false", ["run: python3 lint/test_x.py", "if: false"]),
            ("if: ${{ false }}", ["run: python3 lint/test_x.py", "if: ${{ false }}"]),
            ("if: false on the dash line", ["if: false", "run: python3 lint/test_x.py"]),
        ]
        for label, step in rows:
            with self.subTest(label):
                checks = checks_yml(("checks", "ubuntu-latest", [step]))
                self.assert_gap(checks, True, "the only step naming lint/test_x.py has %s, which cannot fail a pull "
                                "request, yet the file counts as covered" % label)

    def test_a_gating_job_is_reported(self):
        # Rows: the job holding the only step that names the file has continue-on-error: true (or a `${{ true }}` form), or if: false.
        rows = [
            ("continue-on-error: true", ["continue-on-error: true"]),
            ("continue-on-error: ${{ true }}", ["continue-on-error: ${{ true }}"]),
            ("continue-on-error: ${{true}}", ["continue-on-error: ${{true}}"]),
            ("if: false", ["if: false"]),
        ]
        for label, job_keys in rows:
            with self.subTest(label):
                checks = checks_yml(("checks", "ubuntu-latest", ["python3 lint/test_x.py"], job_keys))
                self.assert_gap(checks, True, "the job holding the only step naming lint/test_x.py has %s, which cannot "
                                "fail a pull request, yet the file counts as covered" % label)

    def test_a_lone_quote_in_a_gating_step_name_is_reported(self):
        # Named failure: a lone quote in a step name is text, so it must not hide the gating key below it.
        step = ["name: Don't run it", "run: python3 lint/test_x.py", "continue-on-error: true"]
        self.assert_gap(checks_yml(("checks", "ubuntu-latest", [step])), True,
                        "the only step naming lint/test_x.py has continue-on-error: true after a lone quote in its name, "
                        "which cannot fail a pull request, yet the file counts as covered")

    def test_a_step_that_can_fail_a_pull_request_is_not_reported(self):
        # Rows: a normal step; a key that is false, or a value that can be false (a matrix expression, an if: that can be
        # true), on the step or the job; a file named by
        # a gating and a normal step; gating text that is not a key (a comment, a run block, a quoted run).
        block = '|\n          echo "continue-on-error: true"\n          python3 lint/test_x.py'
        scope = "needs.scope.outputs.code == 'true'"
        rows = [
            ("a normal step", ["python3 lint/test_x.py"], []),
            ("continue-on-error: false", [["run: python3 lint/test_x.py", "continue-on-error: false"]], []),
            ("continue-on-error: a matrix expression", [["run: python3 lint/test_x.py", "continue-on-error: ${{ matrix.experimental }}"]], []),
            ("an if: that can be true, on the step", [["run: python3 lint/test_x.py", "if: %s" % scope]], []),
            ("an if: that can be true, on the job", ["python3 lint/test_x.py"], ["needs: scope", "if: %s" % scope]),
            ("the file in a normal step and a gating step",
             ["python3 lint/test_x.py", ["run: python3 lint/test_x.py", "continue-on-error: true"]], []),
            ("a commented-out continue-on-error: true", [["run: python3 lint/test_x.py", "# continue-on-error: true"]], []),
            ("continue-on-error: true in a run block", [block], []),
            ("continue-on-error: true in a quoted run", ['echo "# continue-on-error: true" && python3 lint/test_x.py'], []),
        ]
        for label, steps, job_keys in rows:
            with self.subTest(label):
                checks = checks_yml(("checks", "ubuntu-latest", steps, job_keys))
                self.assert_gap(checks, False, "%s: the step can fail a pull request, yet the file is reported as a gap"
                                % label)


# Node's default `node --test` patterns (Node 22), matched against a file's name and against its path under the folder
# the run starts in. The collector must list the same files for the skill's tests.
NODE_TEST_NAME = re.compile(r"(?:.*\.test|.*-test|.*_test|test-.*|test)\.(?:cjs|mjs|js)$")
NODE_TEST_DIR = re.compile(r"(?:^|/)test/.+\.(?:cjs|mjs|js)$")
SKILL_TESTS = "skills/plain-english-map/tests"


def node_test_files(folder):
    """Repo-relative paths of the files a default Node test run finds under `folder`: recursive, node_modules skipped."""
    found = []
    for dirpath, dirs, names in os.walk(folder):
        dirs[:] = [d for d in dirs if d != "node_modules"]
        for name in names:
            path = os.path.join(dirpath, name)
            inside = os.path.relpath(path, folder).replace(os.sep, "/")
            if NODE_TEST_NAME.match(name) or NODE_TEST_DIR.search(inside):
                found.append(os.path.relpath(path, REPO).replace(os.sep, "/"))
    return found


def mod_check_files(folder):
    """Repo-relative paths of the check.mjs files under `folder`: recursive, node_modules skipped."""
    found = []
    for dirpath, dirs, names in os.walk(folder):
        dirs[:] = [d for d in dirs if d != "node_modules"]
        for name in names:
            if name == "check.mjs":
                found.append(os.path.relpath(os.path.join(dirpath, name), REPO).replace(os.sep, "/"))
    return found


class CiCoverageCollector(unittest.TestCase):
    def test_mod_tests_list_prints_what_both_phases_run(self):
        # The oracle: the mods find (node_modules pruned), the check.mjs files under mods, which mod_check_files
        # walks on its own, and Node's default test run under the skill's tests.
        bash = shutil.which("bash")
        mods = subprocess.run([bash, "-c", "find mods -name node_modules -prune -o \\( -name '*.test.mjs' -o -name '*.test.js' \\) -print"],
                              cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(mods.returncode, 0, "the mods find exits %d: %s" % (mods.returncode, mods.stderr))
        expected = sorted(mods.stdout.splitlines() + mod_check_files(os.path.join(REPO, "mods"))
                          + node_test_files(os.path.join(REPO, SKILL_TESTS)))
        self.assertTrue(expected, "the two oracles list no file, so the case proves nothing")
        # An npm shim that fails and logs. A list run must never reach the skill phase's install.
        shim = tempfile.mkdtemp(prefix="npm-", dir=RUN_FOLDER)
        npm_log = os.path.join(shim, "npm.log")
        write_file(shim, "npm", '#!/bin/sh\necho "$@" >> "%s"\nexit 1\n' % npm_log)
        os.chmod(os.path.join(shim, "npm"), 0o755)
        env = dict(os.environ, PATH=shim + os.pathsep + os.environ.get("PATH", ""))
        listed = subprocess.run([bash, ".github/scripts/mod-tests.sh", "list"], cwd=REPO, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        with self.subTest("exit code"):
            self.assertEqual(listed.returncode, 0,
                             "mod-tests.sh list exits %d: %s" % (listed.returncode, listed.stderr.strip()))
        with self.subTest("files"):
            self.assertEqual(sorted(listed.stdout.splitlines()), expected,
                             "mod-tests.sh list prints other files than the two phases' finds")
        with self.subTest("npm"):
            self.assertFalse(os.path.exists(npm_log), "mod-tests.sh list ran npm")

    def test_a_file_the_collector_does_not_print_is_reported(self):
        # The collector counts only the files it runs. Named failure: every mjs test counted as covered once a run
        # line names the collector.
        printed, unprinted = "mods/a/x.test.mjs", "mods/a/other.test.mjs"
        checks = checks_yml(("checks", "ubuntu-latest", ["python3 lint/test_ok.py", MOD_CMD]))
        root = make_repo(tracked=["lint/test_ok.py", printed, unprinted], collected=[printed], checks=checks)
        scoped = find_test_files(root)
        for path in (printed, unprinted):
            with self.subTest(path=path):
                self.assertIn(path, scoped, "%s is not a scoped test file, so its coverage proves nothing" % path)
        text = gap_text(root)
        with self.subTest("unprinted"):
            self.assertIn(unprinted, text, "a test file the collector does not print is covered by the collector")
        with self.subTest("printed"):
            self.assertNotIn(printed, text, "a file the collector prints is reported")

    def test_a_collected_file_is_covered_when_a_run_line_names_the_collector(self):
        checks = checks_yml(("checks", "ubuntu-latest", ["python3 lint/test_ok.py", MOD_CMD]))
        root = make_repo(tracked=["lint/test_ok.py"] + list(COLLECTED), collected=COLLECTED, checks=checks)
        text = gap_text(root)
        for path in COLLECTED:
            with self.subTest(path=path):
                self.assertIn(path, find_test_files(root),
                              "%s is not a scoped test file, so its coverage proves nothing" % path)
                self.assertNotIn(path, text, "a collected file is reported although a run line names the collector")

    def test_a_collected_file_is_reported_when_no_run_line_names_the_collector(self):
        root = make_repo(tracked=["lint/test_ok.py"] + list(COLLECTED), collected=COLLECTED, checks=TEST_FILE_CHECKS)
        text = gap_text(root)
        for path in COLLECTED:
            with self.subTest(path=path):
                self.assertIn(path, text,
                              "a collected file is not reported when no run line names the collector: %s" % path)

    def test_a_collected_file_is_covered_when_only_a_windows_job_names_the_collector(self):
        checks = checks_yml(("checks", "ubuntu-latest", ["python3 lint/test_ok.py"]),
                            ("checks-windows", "windows-latest", [MOD_CMD]))
        path = COLLECTED[0]
        root = make_repo(tracked=["lint/test_ok.py", path], collected=[path], checks=checks)
        self.assertIn(path, find_test_files(root), "%s is not a scoped test file, so its coverage proves nothing" % path)
        self.assertNotIn(path, gap_text(root),
                         "a collected file is reported when only a windows-latest job names the collector")

    def test_a_comment_or_name_line_does_not_name_the_collector(self):
        # Named failure: a commented run line, or a step name that spells the collector, counted as the run.
        base = checks_yml(("checks", "ubuntu-latest", ["python3 lint/test_ok.py"]))
        path = COLLECTED[0]
        rows = (("comment", "      # run: %s\n" % MOD_CMD), ("name", "      - name: %s\n" % MOD_CMD))
        for label, extra in rows:
            with self.subTest(label):
                root = make_repo(tracked=["lint/test_ok.py", path], collected=[path], checks=base + extra)
                self.assertIn(path, find_test_files(root),
                              "%s is not a scoped test file, so its coverage proves nothing" % path)
                self.assertIn(path, gap_text(root), "a %s line that spells the collector counts as its run" % label)

    def test_a_run_line_counts_for_the_collector_only_when_it_is_the_collector_command(self):
        # Named failure: a run line that adds an argument, or echoes the command, counted as the collector's run.
        path = COLLECTED[0]
        rows = (("list argument", "%s list" % MOD_CMD), ("mods argument", "%s mods" % MOD_CMD),
                ("echo", "echo %s" % MOD_CMD))
        for label, command in rows:
            with self.subTest(label):
                checks = checks_yml(("checks", "ubuntu-latest", ["python3 lint/test_ok.py", command]))
                root = make_repo(tracked=["lint/test_ok.py", path], collected=[path], checks=checks)
                self.assertIn(path, find_test_files(root),
                              "%s is not a scoped test file, so its coverage proves nothing" % path)
                self.assertIn(path, gap_text(root),
                              "a run line that is not exactly the collector command counts as its run: %s" % label)

    def test_the_collector_lists_the_files_a_default_node_run_finds(self):
        # Named failure: the collector lists only top-level *.test.mjs under the skill's tests, so a nested file, a
        # `_test.mjs` file or a file under test/ is missed. node_modules is never listed.
        planted = [SKILL_TESTS + "/nested/deep.test.mjs", SKILL_TESTS + "/b_test.mjs", SKILL_TESTS + "/test/c.js",
                   SKILL_TESTS + "/test-e.mjs", SKILL_TESTS + "/test.mjs"]
        root = make_repo(untracked=["mods/a/x.test.mjs"] + planted + [SKILL_TESTS + "/node_modules/pkg/d.test.mjs"])
        shutil.copyfile(MOD_SCRIPT, os.path.join(root, ".github", "scripts", "mod-tests.sh"))
        listed = subprocess.run([shutil.which("bash"), COLLECTOR, "list"], cwd=root,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        with self.subTest("exit code"):
            self.assertEqual(listed.returncode, 0,
                             "mod-tests.sh list exits %d: %s" % (listed.returncode, listed.stderr.strip()))
        with self.subTest("files"):
            self.assertEqual(sorted(listed.stdout.splitlines()), sorted(["mods/a/x.test.mjs"] + planted),
                             "mod-tests.sh list misses a file the default Node run finds under the skill's tests")

    def test_a_failing_collector_fails_the_scan(self):
        checks = checks_yml(("checks", "ubuntu-latest", ["python3 lint/test_ok.py", MOD_CMD]))
        error = scan(make_repo(tracked=["lint/test_ok.py"] + list(COLLECTED), collector_exit=3, checks=checks))
        self.assertIsNotNone(error, "the scan passed although the collector exits 3; a failed collector must fail it")
        self.assertNotIsInstance(error, AssertionError, "a failed collector reads as a gap report, not as an error")
        self.assertRegex(str(error), r"\b3\b", "the collector's error does not name its exit code 3: %s" % error)


if __name__ == "__main__":
    unittest.main()
