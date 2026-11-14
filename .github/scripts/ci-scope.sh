#!/usr/bin/env bash
# Decides which checks jobs and suites a run needs. Writes name=<bool> lines to $GITHUB_OUTPUT:
#   per job: checks_guard (set when code and guard are both set, or directly by a path the checks-guard job installs from: actions/playwright-setup, .github/shoot), checks_windows checks_windows_merge checks_windows_rest checks_windows_sweep (the janitor sweep suites, set with checks_windows_rest) checks_macos shell_macos pointer_windows, and shoot (below)
#   per suite: code (any non-docs file changed), mods (a path under mods/, or a .md path under skills/plain-english-map/: the mod tests and the
#   map skill tests, one CI step in each of the `checks`, `checks-windows` and `checks-macos` jobs), guard (guard mutation test), sweep (janitor mutation test), shoot (the checks-shoot and checks-waiting-page jobs: the bin/shoot suite and the page suites, which install a browser).
#   The `checks` lint job and the checks-merge-install, checks-install-checkout and checks-merge-git jobs always run, so they have no flag (their suites carry `code`).
#   checks_macos gates both checks-macos and checks-macos-b.
#   per lint step (the four pull-request steps of the `checks` job; each runs only when a file its lint reads changed):
#     lint_red_run (Red-run trailer: any non-.md path, and a .md path under a test folder, since lint/check_red_run.py asks hooks/guard.py is_test_rel),
#     lint_plan_refuter (Plan refuter line: a path under docs/plans/, and the files lint/check_plan_refuter.py imports),
#     lint_ruling_kind (Ruling kind check: a path under docs/decisions/, and the rule files CLAUDE.md and output-styles/shiv-stylisms.md),
#     lint_comment_narration (Comment narration check: any non-.md path; the checker reads no .md file).
#   lint/layout.py, lint/layout.json and .claude/layout-extras.json set all four: each lint finds its record folders through them.
#   checks_windows_rest_2 repeats checks_windows_rest's value (R62). No job reads it: checks-windows-rest-2 runs every step on a ready pull_request, so the output is kept only for the tests that derive it.
# mutation_report is set apart (the end of this file): true on a pull request whose HEAD_REF starts with `batch-`, and on any other event.
# Everything is true on push, schedule and dispatch, on an unreadable diff, on a change to this
# script or the workflow, and on any path the table below does not name. Inputs (env): EVENT,
# BASE_SHA, HEAD_REF.
set -u
JOBS="checks_windows checks_windows_merge checks_windows_rest checks_windows_sweep checks_macos shell_macos pointer_windows"
LINTS="lint_red_run lint_plan_refuter lint_ruling_kind lint_comment_narration"
ALL="$JOBS checks_guard code mods guard sweep shoot $LINTS"
range=""
[ "${EVENT:-}" = pull_request ] && [ -n "${BASE_SHA:-}" ] && range="$BASE_SHA...HEAD"
on=" "
# --no-renames lists the old path of a rename too, so a move out of a mapped path counts.
if [ "${EVENT:-}" = pull_request ] && [ -n "$range" ] && files=$(git diff --name-only --no-renames "$range" 2>/dev/null) && [ -n "$files" ]; then
  W=checks_windows M=checks_windows_merge R=checks_windows_rest Z=checks_windows_sweep X=checks_macos S=shell_macos P=pointer_windows
  while IFS= read -r f; do
    case "$f" in
      # Fail safe: this script, the workflow, and git settings that change every checkout.
      .github/scripts/ci-scope.sh|.github/workflows/checks.yml|.gitattributes) on="$on $ALL " ;;
      # Guard and its installers' inputs: test_guard, the janitor suites and config_watch run guard.py.
      # guard_<family>.py modules are guard.py; guard_test_* is not (it falls to hooks/* below).
      hooks/guard_test_*) on="$on $R $Z $X code guard " ;;
      hooks/guard.py|hooks/guard_*.py|hooks/shared_names.py|hooks/git_reads.py|hooks/question_form.py|hooks/own_session.py|hooks/precompact_handoff.py|hooks/mutate_shared.py) on="$on $W $R $Z $X code guard sweep " ;;
      # settings.json: the same jobs, plus merge/test_merge.py (CloudAllow reads it).
      settings.json) on="$on $M $W $R $Z $X code guard sweep " ;;
      landed-dirs.txt) on="$on $W $R $Z $X $S code guard " ;;
      # tests/guard/*: section files of hooks/test_guard.py, so the same flags (not under hooks/, so no shell_macos).
      hooks/test_guard.py|hooks/mutate_guard.py|tests/guard/*) on="$on $W $X code guard " ;;
      # install.sh and session_start.sh: the checkout-detection suite and test_guard read them.
      hooks/test_install_src.sh|hooks/test_install_windows.sh) on="$on $W $X $S code guard " ;;
      # install.sh: also read by merge/test_merge.py (CloudAllow reads its settings step).
      install.sh) on="$on $M $W $X $S code guard " ;;
      hooks/session_start.sh) on="$on $W $R $Z $X $S code guard " ;;
      hooks/test_mutate_shared.py|hooks/test_mutate_report.py|hooks/test_mutate_js.py|hooks/test_mutate_replay.py|hooks/test_mutate_ci.py|hooks/mutate_js.mjs) on="$on code guard " ;;
      # Hook modules and suites that run on the rest and macOS jobs.
      # guard_log_report.py: decision_watch imports it at run time, as it does _transcript.py.
      # _clause.py: report_guard.py imports it, and test_clause.py is its suite.
      hooks/*|lint/_transcript.py|lint/_clause.py|lint/test_clause.py|lint/guard_log_report.py|lint/ste_lint.py|lint/ui_suffixes.py|lint/report_guard.py|lint/ruling_census.py|lint/test_report_guard.py|lint/test_report_guard_route.py|lint/test_report_guard_stamped.py|lint/test_report_guard_landing.py|lint/test_report_guard_remedy.py|lint/test_report_guard_refusal.py|lint/test_report_guard_handoff.py|lint/test_report_guard_cannot.py|lint/test_report_guard_review.py|lint/test_ruling_census.py|lint/check_unknown_reads_contract.py)
        on="$on $R $Z $X code guard "; case "$f" in lint/_transcript.py|lint/guard_log_report.py) on="$on $M " ;; esac ;;
      # bin/claude-janitor: test_install_src reads it.
      bin/claude-janitor) on="$on $W $S $R $Z $X code guard sweep " ;;
      janitor/*) on="$on $R $Z $X code sweep " ;;
      bin/verdict|bin/verdict.cmd|lint/test_verdict.py) on="$on $R $Z $X code " ;;
      # The fixture copy helpers: suites in every job copy the repo's modules through them.
      testing/tracked_tree.py|testing/tracked_tree.sh|testing/TrackedTree.ps1|testing/SharedRead.ps1) on="$on $ALL " ;;
      # The test-run signing opt-out helper: suites in every job import it.
      lint/_test_git.py|lint/_test_git.sh|lint/_test_git.mjs) on="$on $ALL " ;;
      bin/ci-job) on="$on code " ;;
      # bin/ios-ship: macOS only. Its suite runs in the shell-macos job, under /bin/bash 3.2.
      bin/ios-ship|lint/test_ios_ship.sh) on="$on $S code " ;;
      # bin/sim-test: macOS only, like bin/ios-ship. Its suite runs in the shell-macos job, and runs the real bin/sim-lease
      # beside the script, so an edit to bin/sim-lease turns the same job on.
      bin/sim-test|lint/test_sim_test.sh|bin/sim-lease) on="$on $S code " ;;
      # bin/duo-fold: macOS only (bash 3.2 script for the iPhone Duo). Its suite runs in the shell-macos job.
      bin/duo-fold|lint/test_duo_fold.sh) on="$on $S code " ;;
      # bin/shoot: its suite installs Playwright and Chromium, so only these paths run it.
      bin/shoot|lint/test_shoot.mjs|testing/skip-locally-fail-in-ci.mjs) on="$on code shoot " ;;
      # actions/playwright-setup has four callers: checks-shoot and checks-waiting-page (shoot), checks-guard and checks-guard-2 (checks_guard). Both guard jobs also
      # install the Playwright that .github/shoot pins (package-dir), so that dir takes this arm too. Set checks_guard
      # directly: the guard flag would also start the guard suites, which this action does not touch. A .md edit runs none of the four jobs.
      actions/playwright-setup/*.md) ;;
      actions/playwright-setup/*|.github/shoot/*) on="$on code shoot checks_guard " ;;
      # merge.py: guard.py loads it. layout.json: guard.py reads it; layout.py: ste_lint.py and hook_catalog.py (merge.py) import it.
      # check_silent_undo.py: merge.py imports it.
      merge/merge.py) on="$on $M $W $X code guard " ;;
      lint/layout.json|lint/layout.py) on="$on $M $R $Z $W $X code guard " ;;
      lint/check_silent_undo.py) on="$on $M code " ;;
      merge/*|bin/merge|bin/merge.cmd|.github/stamp.json) on="$on $M $S code " ;;
      actions/stamp/*.md) ;;
      actions/stamp/*) on="$on $R $Z $X $M code " ;;
      # Mod tests: the mod-tests.sh step in checks, checks-windows and checks-macos reads mods/.
      mods/*) on="$on $W $X mods " ;;
      install.ps1|install.test.ps1|install-no-gap.test.ps1|install-bin-eol.test.ps1|install-set.test.ps1) on="$on $P code " ;;
      # decision-watch.test.mjs imports lint/test_scanner_traps.mjs, so the mod-tests.sh step runs it too.
      lint/test_scanner_traps.mjs) on="$on $W $X mods code " ;;
      # .gitignore: skills/plain-english-map/tests/typescript-home.test.mjs reads it, so it runs the mod step. `code` stays for the lints.
      .gitignore) on="$on $W $X mods code " ;;
      # bin/rm: the shim imports hooks/guard_rm_var.py (hooks/* above); it runs on posix jobs.
      bin/rm|lint/test_rm_shim.py) on="$on $X code " ;;
      # Linux `checks` job only: the lints and opt-in templates.
      actions/*|githooks/*|testing/*|lint/*|.github/dependabot.yml) on="$on code " ;;
      # Map skill .md files: its tests read them, so this arm turns on `mods` before the *.md arm.
      skills/plain-english-map/*.md) on="$on $W $X mods " ;;
      # Docs: nothing runs on them but the lints in `checks`. (hooks/*.md, the precompact prompt, matches hooks/* above.)
      *.md) ;;
      *) on="$on $ALL " ;;
    esac
    # shoot also covers the files the waiting page export suite (skills/waiting-page/test_export_page.py) imports, lazy
    # imports included: page_check.py reaches the guard family (guard_merge.py imports ci_wake.py), question_form.py, _nowindow.py, report_guard.py and its lint/_clause.py;
    # the suite's run folder is lint/_test_temp.py; layout.artifacts reads lint/layout.json at run time; SKILL.md and every file in reference/ hold the steps it and the page suite read. This is a second case, so the
    # flags each path sets above stay as they are, and guard_test_* (not imported) stays out. Chosen over one arm
    # (hooks/*.py, lint/*.py): that would start the browser job on every hook and lint edit, 88 + 94 files, most of
    # which the suite never reads, and the control cases pin hooks/mutate_shared.py and hooks/config_watch.py off.
    # The list cannot drift silently: lint/test_ci_scope.py walks the suite's imports and fails on a file missing here.
    # The cost per start: the suite ran 57 s, the browser install adds to it, the job cap is 10 min, and the job
    # runs beside the others on its own runner, so it adds billed minutes and no wall time.
    case "$f" in
      hooks/guard_test_*) ;;
      hooks/guard.py|hooks/guard_*.py|hooks/git_reads.py|hooks/own_session.py|hooks/precompact_handoff.py|hooks/shared_names.py|hooks/question_form.py|hooks/_nowindow.py|lint/report_guard.py|lint/_clause.py|lint/layout.py|lint/layout.json|lint/_test_temp.py|skills/waiting-page/SKILL.md|skills/waiting-page/reference/*|skills/waiting-page/export_page.py|hooks/call_judge.py|hooks/ci_wake.py|hooks/decision_watch.py|hooks/feedback_guard.py|hooks/local_time.py|hooks/override.py|hooks/proc_env.py|hooks/session_role.py|hooks/reply_judge.py|hooks/reread_check.py|hooks/route_match.py|hooks/ruling_home.py|janitor/sweep.py|janitor/temp_sweep.py|lint/_transcript.py|lint/guard_log_report.py|lint/rule_audit.py|lint/ruled_store.py|hooks/mail.py|hooks/agent_brief.py|hooks/stall_watch.py|hooks/ci_wait_cap.py|hooks/ci_wait_cap.json) on="$on shoot " ;;
    esac
    # The four pull-request lint steps of the `checks` job. This is a third case, so the flags each path sets above stay as
    # they are. A path the table above does not name has set every flag already (the `*)` arm).
    case "$f" in
      *.md)
        # check_red_run.py judges a .md under a test folder as a test path (hooks/guard.py is_test_rel: TEST_DIRS, an Xcode `*Tests`
        # folder, a `.spec.` name). nocasematch: is_test_rel lowercases a name before it compares.
        shopt -s nocasematch
        case "/$f" in */tests/*|*/test/*|*/__tests__/*|*/testdata/*|*/__snapshots__/*|*/test_support/*|*/testing/*|*.spec.*) on="$on lint_red_run " ;; esac
        shopt -u nocasematch
        case "/$f" in */[A-Z]*Tests/*) on="$on lint_red_run " ;; esac
        case "$f" in
          docs/decisions/*) on="$on lint_ruling_kind " ;;
          docs/plans/*) on="$on lint_plan_refuter " ;;
          CLAUDE.md|output-styles/shiv-stylisms.md) on="$on lint_ruling_kind " ;;
        esac ;;
      # The lints find the plans and decisions folders through layout.py, layout.json and the extras file.
      lint/layout.py|lint/layout.json|.claude/layout-extras.json) on="$on $LINTS " ;;
      # check_plan_refuter.py imports guard_core.py (REFUTER_ROLE), which imports git_reads.py and shared_names.py; _nowindow.py runs its git.
      # The guard family and its two shared modules take one flag set (the guard-sibling cases pin it), so hooks/guard.py and every guard_<family>.py carry it too.
      hooks/guard_test_*) on="$on lint_red_run lint_comment_narration " ;;
      hooks/guard.py|hooks/guard_*.py|hooks/git_reads.py|hooks/shared_names.py|hooks/_nowindow.py) on="$on lint_red_run lint_comment_narration lint_plan_refuter " ;;
      lint/check_plan_refuter.py) on="$on lint_red_run lint_comment_narration lint_plan_refuter " ;;
      lint/check_ruling_kind.py) on="$on lint_red_run lint_comment_narration lint_ruling_kind " ;;
      # Every other path that is not .md: the red-run check and the narration check read it.
      *) on="$on lint_red_run lint_comment_narration " ;;
    esac
  done <<< "$files"
  # A new file under a landed dir (landed-dirs.txt, the one list) changes what test_install_src and
  # the guard suite see. An unreadable or empty list turns everything on.
  dirs=$(sed 's/#.*//; s/[[:space:]]//g; s#/$##' landed-dirs.txt 2>/dev/null | grep -v '^$' | paste -sd'|' -)
  if [ -z "$dirs" ]; then
    on="$on $ALL "
  else
    added=$(git diff --name-only --diff-filter=A --no-renames "$range" 2>/dev/null) || on="$on $ALL "
    grep -Eq "^($dirs)/" <<< "$added" && on="$on $W $S code guard "
  fi
else
  on=" $ALL "
fi
# checks_guard: the checks-guard job runs the guard suite, which needs both flags (the old step if). The playwright-setup arm above also sets it directly.
case "$on" in *" code "*) case "$on" in *" guard "*) on="$on checks_guard " ;; esac ;; esac
echo "CI scope: event=${EVENT:-} range=${range:-none} on=$on"
for n in $ALL; do
  case "$on" in *" $n "*) v=true ;; *) v=false ;; esac
  echo "$n=$v" >> "$GITHUB_OUTPUT"
  # checks-windows-rest-2 is the second half of the rest suites (R62). Its output repeats the rest flag; no job reads it (the job runs every step on a ready pull_request).
  [ "$n" = checks_windows_rest ] && echo "checks_windows_rest_2=$v" >> "$GITHUB_OUTPUT"
done
# mutation_report: the mutation-report job runs on a pull request from a `batch-` branch (HEAD_REF), and on any other event, where the
# action skips a push or a schedule itself. It is outside ALL: a change to this script or the workflow must not start it on any other PR.
case "${EVENT:-}" in
  pull_request) case "${HEAD_REF:-}" in batch-*) v=true ;; *) v=false ;; esac ;;
  *) v=true ;;
esac
echo "mutation_report=$v" >> "$GITHUB_OUTPUT"
