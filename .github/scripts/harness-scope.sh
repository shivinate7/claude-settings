#!/usr/bin/env bash
# Decides which gates jobs and suites a run needs. Writes name=<bool> lines to $GITHUB_OUTPUT:
#   per job: gates_windows gates_windows_merge gates_windows_rest gates_macos shell_macos pointer_windows
#   per suite: code (any non-docs file changed), guard (guard mutation harness), sweep (janitor
#   mutation harness). The `gates` lint job always runs, so it has no flag.
# Everything is true on push, schedule and dispatch, on an unreadable diff, on a change to this
# script or the workflow, and on any path the table below does not name. Inputs (env): EVENT,
# BASE_SHA, BEFORE_SHA. decisions/docs-only-prs-skip-code-suites.md.
set -u
JOBS="gates_windows gates_windows_merge gates_windows_rest gates_macos shell_macos pointer_windows"
ALL="$JOBS code guard sweep"
range=""
case "${EVENT:-}" in
  pull_request) [ -n "${BASE_SHA:-}" ] && range="$BASE_SHA...HEAD" ;;
  push) [ -n "${BEFORE_SHA//0/}" ] && range="$BEFORE_SHA...HEAD" ;;
esac
on=" "
# --no-renames lists the old path of a rename too, so a move out of a mapped path counts.
if [ "${EVENT:-}" = pull_request ] && [ -n "$range" ] && files=$(git diff --name-only --no-renames "$range" 2>/dev/null) && [ -n "$files" ]; then
  W=gates_windows M=gates_windows_merge R=gates_windows_rest X=gates_macos S=shell_macos P=pointer_windows
  while IFS= read -r f; do
    case "$f" in
      # Fail safe: this script, the workflow, and git settings that change every checkout.
      .github/scripts/harness-scope.sh|.github/workflows/gates.yml|.gitattributes) on="$on $ALL " ;;
      # Guard and its installers' inputs: test_guard, the janitor suites and config_watch run guard.py.
      hooks/guard.py|hooks/mutate_shared.py|settings.json) on="$on $W $R $X code guard sweep " ;;
      landed-dirs.txt) on="$on $W $R $X $S code guard " ;;
      hooks/test_guard.py|hooks/mutate_guard.py) on="$on $W $X code guard " ;;
      # install.sh and session_start.sh: the checkout-detection suite and test_guard read them.
      install.sh|hooks/test_install_src.sh) on="$on $W $X $S code guard " ;;
      hooks/session_start.sh) on="$on $W $R $X $S code guard " ;;
      hooks/test_mutate_shared.py) on="$on code guard " ;;
      # Hook modules and suites that run on the rest and macOS jobs.
      hooks/*|lint/_transcript.py|lint/ste_lint.py|lint/ste_gate.py|lint/report_gate.py|lint/md_sweep.py|lint/ruling_census.py|lint/test_gates.py|lint/test_ruling_census.py|lint/check_unknown_reads_contract.py)
        on="$on $R $X code guard "; [ "$f" = lint/_transcript.py ] && on="$on $M " ;;
      # bin/claude-janitor: test_install_src reads it.
      bin/claude-janitor) on="$on $W $S $R $X code sweep " ;;
      janitor/*) on="$on $R $X code sweep " ;;
      bin/verdict|bin/verdict.cmd|lint/test_verdict.py) on="$on $R $X code " ;;
      # merge.py: guard.py loads it. check_record_slugs.py: guard.py reads it. check_silent_undo.py: merge.py imports it.
      merge/merge.py) on="$on $M $W $X code guard " ;;
      lint/check_record_slugs.py) on="$on $W $X code guard " ;;
      lint/check_silent_undo.py) on="$on $M code " ;;
      merge/*|bin/merge|bin/merge.cmd|.github/stamp.json) on="$on $M code " ;;
      actions/stamp/*.md) ;;
      actions/stamp/*) on="$on $R $X $M code " ;;
      install.ps1|install.test.ps1) on="$on $P code " ;;
      # Linux `gates` job only: the lints and opt-in templates.
      actions/*|githooks/*|testing/*|lint/*|.github/dependabot.yml|.gitignore) on="$on code " ;;
      # Docs: nothing runs on them but the lints in `gates`. (hooks/*.md, the precompact prompt, matches hooks/* above.)
      *.md) ;;
      *) on="$on $ALL " ;;
    esac
  done <<< "$files"
  # A new file under these folders changes what test_install_src and the guard suite see.
  added=$(git diff --name-only --diff-filter=A --no-renames "$range" 2>/dev/null) || added="agents/"
  grep -Eq '^(agents|skills|output-styles|lint)/' <<< "$added" && on="$on $W $S code "
else
  on=" $ALL "
fi
echo "harness scope: event=${EVENT:-} range=${range:-none} on=$on"
for n in $ALL; do
  case "$on" in *" $n "*) v=true ;; *) v=false ;; esac
  echo "$n=$v" >> "$GITHUB_OUTPUT"
done
