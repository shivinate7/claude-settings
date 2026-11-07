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

# Combined step: action.yml has one step, and its command is run.sh. run.sh runs check.sh, then wiring.sh, and fails when
# either fails. The NEEDS values are the fake check's input: ONE_FAILED has a failed needed job, ALL_PASS has none.
ALL_PASS='{"lint":{"result":"success"},"test-mac":{"result":"success"}}'
ONE_FAILED='{"lint":{"result":"failure"},"test-mac":{"result":"success"}}'
combined() { # combined <0 or nz> <label> <NEEDS json> <WORKFLOW>: run.sh over the fixture workspace
  if [ ! -f "$here/run.sh" ]; then echo "FAIL $2: run.sh is missing, so the action has no combined step"; bad=1; return; fi
  out="$(NEEDS="$3" GITHUB_WORKSPACE="$ws" WORKFLOW="$4" bash "$here/run.sh" 2>&1)"; got=$?
  if { [ "$1" = nz ] && [ "$got" -ne 0 ]; } || { [ "$1" != nz ] && [ "$got" -eq "$1" ]; }; then echo "ok   $2"; else echo "FAIL $2 (exit $got, wanted $1)"; bad=1; fi
}
combined nz "combined: a failed needed job fails the step, with a clean wiring" "$ONE_FAILED" ".github/workflows/checks.yml"
combined nz "combined: a wiring defect fails the step, with every needed job green" "$ALL_PASS" ".github/workflows/dropped.yml"
combined 0 "combined: both clean pass the step" "$ALL_PASS" ".github/workflows/checks.yml"

# python3 off PATH: a PATH of the tools wiring.sh uses, and no python3. The case is void unless python3 is really absent.
nopy="$work/nopy"; mkdir -p "$nopy"
for t in dirname basename cat jq; do p="$(command -v "$t")" && ln -s "$p" "$nopy/$t"; done
bash_abs="$(command -v bash)"
nopy_case() { # nopy_case <label>: wiring.sh with python3 off PATH must exit non-zero, never 0
  if [ ! -f "$here/wiring.sh" ]; then echo "FAIL $1: wiring.sh is missing, so the action has no wiring step"; bad=1; return; fi
  if env PATH="$nopy" "$bash_abs" -c 'command -v python3' >/dev/null 2>&1; then echo "FAIL $1: python3 is still on the test PATH"; bad=1; return; fi
  out="$(env PATH="$nopy" GITHUB_WORKSPACE="$ws" WORKFLOW=.github/workflows/checks.yml "$bash_abs" "$here/wiring.sh" 2>&1)"; got=$?
  if [ "$got" -ne 0 ]; then echo "ok   $1 (exit $got)"; else echo "FAIL $1 (exit 0 with python3 off PATH)"; bad=1; fi
}
nopy_case "wiring: python3 off PATH exits non-zero, never 0"

# Static: action.yml has exactly one step under runs.steps. That step runs run.sh, sets no if: and no continue-on-error:,
# and sets WORKFLOW from inputs.workflow. The reader drops full-line comments and matches each key and the run line exactly.
static_run() { # static_run <action.yml>: sets $problems to the reader's lines and $rc to its exit
  problems="$(python3 -I -c '
import re, sys
text = open(sys.argv[1], encoding="utf-8").read()
text = "\n".join(line for line in text.split("\n") if not line.lstrip().startswith("#"))
inputs = re.search(r"^inputs:\n((?:[ \t]+[^\n]*\n|\n)*)", text, re.M)
if not inputs or not re.search(r"^  workflow:[ \t]*(?:#[^\n]*)?$", inputs.group(1), re.M):
    print("input workflow is not declared under inputs")
steps = [s for s in re.split(r"^(?=    - )", text.partition("\n  steps:\n")[2], flags=re.M) if s.startswith("    - ")]
if len(steps) != 1:
    print("want exactly one step under runs.steps, found %d" % len(steps))
    sys.exit(0)
step = steps[0]
if not re.search(r"^      run: bash \"\$\{\{ github\.action_path \}\}/run\.sh\"[ \t]*(?:#[^\n]*)?$", step, re.M):
    print("the one step does not run run.sh")
if re.search(r"^[ \t]*if[ \t]*:", step, re.M):
    print("the one step sets if:")
if re.search(r"^[ \t]*continue-on-error[ \t]*:", step, re.M):
    print("the one step sets continue-on-error:")
if not re.search(r"^        WORKFLOW:[ \t]*\$\{\{[ \t]*inputs\.workflow[ \t]*\}\}[ \t]*(?:#[^\n]*)?$", step, re.M):
    print("the one step does not set WORKFLOW from inputs.workflow")' "$1" 2>&1)"; rc=$?
}
static_expect() { # static_expect <label> <ok, or a substring the reader must print> <action.yml>: one FAIL line per problem
  static_run "$3"
  if [ "$rc" -ne 0 ]; then echo "FAIL $1: the static reader crashed (exit $rc)"; bad=1; return; fi
  if [ "$2" = ok ]; then
    if [ -z "$problems" ]; then echo "ok   $1"; return; fi
    while IFS= read -r line; do echo "FAIL $1: $line"; done <<< "$problems"; bad=1; return
  fi
  case "$problems" in *"$2"*) echo "ok   $1";; *) echo "FAIL $1: the reader did not print: $2"; bad=1;; esac
}
one_step() { # one_step <extra step key line, or empty> <run line>: a one-step action.yml as the step is written
  cat <<YML
name: All jobs passed
inputs:
  needs:
    description: "Pass toJSON(needs) from the calling job."
    required: true
  workflow:
    description: "The calling workflow's path."
    required: false
    default: ''
runs:
  using: composite
  steps:
    - name: Every needed job passed, and the wiring holds
      shell: bash
$1
      env:
        NEEDS: \${{ inputs.needs }}
        WORKFLOW: \${{ inputs.workflow }}
$2
YML
}
run_line='      run: bash "${{ github.action_path }}/run.sh" # both checks'
static_expect "static: action.yml has one step, which runs run.sh with WORKFLOW from inputs.workflow" ok "$here/action.yml"
# Checker controls, green on this head. A valid one-step action with an iffy key (not an if:) and inline comments is clean.
one_step "      iffy: a key that starts with if" "$run_line" > "$work/static-ok.yml"
static_expect "static control: a valid one-step action with an iffy key and inline comments is clean" ok "$work/static-ok.yml"
one_step "" '      # run: bash "${{ github.action_path }}/run.sh"' > "$work/static-commented.yml"
static_expect "static control: a commented-out run line does not count as run.sh" "does not run run.sh" "$work/static-commented.yml"
{ one_step "" "$run_line"; printf '    - name: extra\n      run: echo extra\n'; } > "$work/static-two.yml"
static_expect "static control: a second step is reported" "found 2" "$work/static-two.yml"
one_step "      if: always()" "$run_line" > "$work/static-if.yml"
static_expect "static control: an if: key on the step is reported" "sets if:" "$work/static-if.yml"
one_step "      continue-on-error: true" "$run_line" > "$work/static-coe.yml"
static_expect "static control: a continue-on-error: key on the step is reported" "continue-on-error" "$work/static-coe.yml"
exit $bad
