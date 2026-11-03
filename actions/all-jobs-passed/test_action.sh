#!/usr/bin/env bash
# Red run: the check must fail on failure, cancelled, skipped and empty needs; pass on all success.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
bad=0
expect() { # want label json
  NEEDS="$3" bash "$here/check.sh" >/dev/null 2>&1; got=$?
  if { [ "$1" = pass ] && [ $got -eq 0 ]; } || { [ "$1" = fail ] && [ $got -ne 0 ]; }; then echo "ok   $2"
  else echo "FAIL $2 (exit $got, wanted $1)"; bad=1; fi
}
expect pass all-success '{"a":{"result":"success"},"b":{"result":"success"}}'
expect fail one-failed  '{"a":{"result":"success"},"b":{"result":"failure"}}'
expect fail one-cancelled '{"a":{"result":"cancelled"}}'
expect fail one-skipped '{"a":{"result":"success"},"b":{"result":"skipped"}}'
expect fail empty-needs '{}'

# Wiring: wiring.sh runs lint/all_jobs_passed_rules.py on the calling repo's WORKFLOW under GITHUB_WORKSPACE.
# Exit codes are exact (0 clean, 1 a problem, 2 unknown): a bash 127 from a missing script is never a pass.
root="$(cd "$here/../.." && pwd)"
# One run folder per test run (test-temp-standard): lint/_test_temp.py makes it under the repo's one temp root.
work=$(python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import _test_temp; print(_test_temp.run_folder())' "$root/lint") || work=""
[ -n "$work" ] || { echo "FAIL - run folder: lint/_test_temp.py made no run folder"; exit 1; }
trap 'rm -rf "$work"' EXIT
ws="$work/workspace"; mkdir -p "$ws/.github/workflows"
# The child workflows come from lint/test_all_jobs_passed.py, the one home of CHILD_GOOD and its mutants. Nothing is copied.
fixture() { # fixture <clean|dropped|full|empty> <path>
  python3 -I -c '
import sys
sys.path.insert(0, sys.argv[1])
import test_all_jobs_passed as t
text = {"clean": t.CHILD_GOOD, "dropped": t.CHILD_GOOD.replace(t.NEEDED_JOB, "", 1), "full": t.full_size_child(), "empty": ""}[sys.argv[2]]
sys.stdout.write(text)' "$root/lint" "$1" > "$2" || { echo "FAIL - fixture $1: lint/test_all_jobs_passed.py did not load"; exit 1; }
}
fixture clean "$ws/.github/workflows/checks.yml"
fixture dropped "$ws/.github/workflows/dropped.yml"
fixture full "$ws/.github/workflows/full.yml"
fixture empty "$ws/.github/workflows/empty.yml"
# Controls, green on this head: the rules script gives each fixture its verdict, so a later red belongs to wiring.sh.
ctl() { # ctl <want exit> <label> <path>
  python3 "$root/lint/all_jobs_passed_rules.py" --workflow "$3" >/dev/null 2>&1; got=$?
  if [ "$got" -eq "$1" ]; then echo "ok   control: $2"; else echo "FAIL control: $2 (exit $got, wanted $1)"; bad=1; fi
}
ctl 0 "rules script passes the clean child" "$ws/.github/workflows/checks.yml"
ctl 1 "rules script fails a dropped needed job" "$ws/.github/workflows/dropped.yml"
ctl 0 "rules script passes the full-size child" "$ws/.github/workflows/full.yml"
ctl 1 "rules script fails an empty file" "$ws/.github/workflows/empty.yml"
ctl 2 "rules script exits 2 on a missing file" "$ws/.github/workflows/missing.yml"
# wire <want exit> <label> <WORKFLOW>: runs wiring.sh over the fixture workspace and sets $out. A missing wiring.sh is named, not run.
wire() {
  if [ ! -f "$here/wiring.sh" ]; then echo "FAIL $2: wiring.sh is missing, so the action has no wiring step"; bad=1; return 1; fi
  out="$(GITHUB_WORKSPACE="$ws" WORKFLOW="$3" bash "$here/wiring.sh" 2>&1)"; got=$?
  if [ "$got" -eq "$1" ]; then echo "ok   $2"; else echo "FAIL $2 (exit $got, wanted $1)"; bad=1; fi
}
wire 0 "wiring: an empty WORKFLOW skips and exits 0" ""
wire 0 "wiring: the clean child passes" ".github/workflows/checks.yml"
wire 1 "wiring: a needed job dropped from needs fails" ".github/workflows/dropped.yml"
wire 0 "wiring: the full-size child passes" ".github/workflows/full.yml"
wire 1 "wiring: an empty workflow file fails" ".github/workflows/empty.yml"
wire 2 "wiring: a missing file exits 2" ".github/workflows/missing.yml"
if [ -f "$here/wiring.sh" ]; then
  case "$out" in *unknown*) echo "ok   wiring: a missing file's output says unknown";; *) echo "FAIL wiring: a missing file's output does not say unknown"; bad=1;; esac
fi
# Static: action.yml declares input workflow, and the one step that runs wiring.sh is under always() and sets WORKFLOW from
# inputs.workflow. The reader drops full-line comments, so a commented-out if: does not count. Each line it prints is one cause.
static_run() { # static_run <action.yml>: sets $problems to the reader's lines and $rc to its exit
  problems="$(python3 -I -c '
import re, sys
text = open(sys.argv[1], encoding="utf-8").read()
text = "\n".join(line for line in text.split("\n") if not line.lstrip().startswith("#"))
inputs = re.search(r"^inputs:\n((?:[ \t]+[^\n]*\n|\n)*)", text, re.M)
if not inputs or not re.search(r"^  workflow:[ \t]*(?:#[^\n]*)?$", inputs.group(1), re.M):
    print("input workflow is not declared under inputs")
steps = [s for s in re.split(r"^(?=    - )", text.partition("\n  steps:\n")[2], flags=re.M) if s.startswith("    - ")]
wiring = [s for s in steps if "wiring.sh" in s]
if len(wiring) != 1:
    print("want one step that runs wiring.sh, found %d" % len(wiring))
    sys.exit(0)
step = wiring[0]
if not re.search(r"^      if:[ \t]*(?:\$\{\{[ \t]*)?always\(\)", step, re.M):
    print("the wiring step is not under always(): after a failed needs step it is skipped, and a skip reads green")
if not re.search(r"^        WORKFLOW:[ \t]*\$\{\{[ \t]*inputs\.workflow[ \t]*\}\}[ \t]*(?:#[^\n]*)?$", step, re.M):
    print("the wiring step does not set WORKFLOW from inputs.workflow")' "$1" 2>&1)"; rc=$?
}
static_check() { # static_check <action.yml> <label>: one FAIL line per problem, or ok
  static_run "$1"
  if [ "$rc" -ne 0 ]; then echo "FAIL $2: the static reader crashed (exit $rc)"; bad=1; return; fi
  if [ -z "$problems" ]; then echo "ok   $2"; return; fi
  while IFS= read -r line; do echo "FAIL $2: $line"; done <<< "$problems"; bad=1
}
static_check "$here/action.yml" "static: action.yml declares workflow and wires wiring.sh under always()"
# A commented-out if: does not count as the wiring step's if. This mutant is a checker control: it is green on this head.
mut="$work/action-commented.yml"
cat > "$mut" <<'YML'
name: mutant
inputs:
  workflow:
    description: "child workflow"
    default: ''
runs:
  using: composite
  steps:
    - name: Wiring
      shell: bash
      # if: always()
      env:
        WORKFLOW: ${{ inputs.workflow }}
      run: bash "${{ github.action_path }}/wiring.sh"
YML
static_run "$mut"
case "$problems" in *"not under always()"*) echo "ok   static: a commented-out if: always() is reported as missing";; *) echo "FAIL static: a commented-out if: always() was not reported as missing";; esac
# Inline comments after a value and a # inside a string are not problems. This is a checker control: green on this head.
inl="$work/action-inline.yml"
cat > "$inl" <<'YML'
name: inline
inputs:
  workflow: # the child workflow, relative to the workspace
    description: "child #1 workflow path"
    default: ''
runs:
  using: composite
  steps:
    - name: Wiring
      shell: bash
      if: always() # after a failed needs step
      env:
        WORKFLOW: ${{ inputs.workflow }} # the child
      run: bash "${{ github.action_path }}/wiring.sh"
YML
static_run "$inl"
if [ "$rc" -eq 0 ] && [ -z "$problems" ]; then echo "ok   static: inline and in-string # are not problems"; else echo "FAIL static: an inline or in-string # was read as a problem: $problems"; bad=1; fi
exit $bad
