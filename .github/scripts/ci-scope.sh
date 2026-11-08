#!/usr/bin/env bash
# Decides which checks jobs and suites a run needs. Writes name=<bool> lines to $GITHUB_OUTPUT:
#   per job: checks_guard (set when code and guard are both set, or directly by a path the checks-guard job installs from: actions/playwright-setup, .github/shoot), checks_windows checks_windows_merge checks_windows_rest checks_windows_sweep (the janitor sweep suites, set with checks_windows_rest) checks_macos shell_macos pointer_windows, and shoot (below)
#   per suite: code (any non-docs file changed), mods (a path under mods/, or a .md path under skills/plain-english-map/: the mod tests and the
#   map skill tests, one CI step in each of the `checks`, `checks-windows` and `checks-macos` jobs), guard (guard mutation test), sweep (janitor mutation test), shoot (the checks-shoot job: the bin/shoot suite, which installs a browser).
#   The `checks` lint job and the checks-merge-install job always run, so they have no flag (their suites carry `code`).
#   checks_macos gates both checks-macos and checks-macos-b.
# mutation_report is set apart (the end of this file): true on a pull request whose HEAD_REF starts with `batch-`, and on any other event.
# Everything is true on push, schedule and dispatch, on an unreadable diff, on a change to this
# script or the workflow, and on any path the table below does not name. Inputs (env): EVENT,
# BASE_SHA, HEAD_REF.
set -u
JOBS="checks_windows checks_windows_merge checks_windows_rest checks_windows_sweep checks_macos shell_macos pointer_windows"
ALL="$JOBS checks_guard code mods guard sweep shoot"
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
      hooks/guard.py|hooks/guard_*.py|hooks/shared_names.py|hooks/git_reads.py|hooks/question_form.py|hooks/own_session.py|hooks/precompact_handoff.py|hooks/merge_options.py|hooks/override.py|hooks/_nowindow.py|hooks/proc_env.py|hooks/reread_check.py|hooks/call_judge.py|hooks/decision_watch.py|hooks/feedback_guard.py|hooks/local_time.py|hooks/ruling_home.py|hooks/route_match.py|hooks/reply_judge.py|hooks/mutate_shared.py) on="$on $W $R $Z $X code guard sweep " ;;
      # settings.json: the same jobs, plus merge/test_merge.py (CloudAllow reads it).
      settings.json) on="$on $M $W $R $Z $X code guard sweep " ;;
      landed-dirs.txt) on="$on $W $R $Z $X $S code guard " ;;
      hooks/test_guard.py|hooks/mutate_guard.py) on="$on $W $X code guard " ;;
      # install.sh and session_start.sh: the checkout-detection suite and test_guard read them.
      hooks/test_install_src.sh|hooks/test_install_windows.sh) on="$on $W $X $S code guard " ;;
      # install.sh: also read by merge/test_merge.py (CloudAllow reads its settings step).
      install.sh) on="$on $M $W $X $S code guard " ;;
      hooks/session_start.sh) on="$on $W $R $Z $X $S code guard " ;;
      hooks/test_mutate_shared.py|hooks/test_mutate_report.py|hooks/test_mutate_js.py|hooks/test_mutate_replay.py|hooks/test_mutate_ci.py|hooks/mutate_js.mjs) on="$on code guard " ;;
      # Hook modules and suites that run on the rest and macOS jobs.
      # guard_log_report.py: decision_watch imports it at run time, as it does _transcript.py.
      hooks/*|lint/_transcript.py|lint/guard_log_report.py|lint/ste_lint.py|lint/ui_suffixes.py|lint/report_guard.py|lint/ruling_census.py|lint/test_report_guard.py|lint/test_report_guard_route.py|lint/test_report_guard_landing.py|lint/test_report_guard_refusal.py|lint/test_report_guard_handoff.py|lint/test_report_guard_review.py|lint/test_ruling_census.py|lint/check_unknown_reads_contract.py)
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
      # bin/shoot: its suite installs Playwright and Chromium, so only these paths run it.
      bin/shoot|lint/test_shoot.mjs|testing/skip-locally-fail-in-ci.mjs) on="$on code shoot " ;;
      # actions/playwright-setup has two callers: checks-shoot (shoot) and checks-guard (checks_guard). checks-guard also
      # installs the Playwright that .github/shoot pins (package-dir), so that dir takes this arm too. Set checks_guard
      # directly: the guard flag would also start the guard suites, which this action does not touch. A .md edit runs neither job.
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
done
# mutation_report: the mutation-report job runs on a pull request from a `batch-` branch (HEAD_REF), and on any other event, where the
# action skips a push or a schedule itself. It is outside ALL: a change to this script or the workflow must not start it on any other PR.
case "${EVENT:-}" in
  pull_request) case "${HEAD_REF:-}" in batch-*) v=true ;; *) v=false ;; esac ;;
  *) v=true ;;
esac
echo "mutation_report=$v" >> "$GITHUB_OUTPUT"
