#!/usr/bin/env bash
# Cases for actions/zizmor: action.yml, the checks job's step that runs it, and run.sh, the one home of
# the pinned zizmor run. Each run.sh case puts a stub pipx first on PATH. The stub writes its argv, one
# entry per line, to an argv file and exits with the code the case chose. A case checks that the stub was
# called before it reads run.sh's exit code, so a run.sh that never reached pipx cannot read as a pass.
#  - control-stub-records-argv: the stub itself records argv and exits with its code (passes on old code).
#  - default-paths-argv: with ZIZMOR_PATHS unset, run.sh passes .github/ as one entry.
#  - two-paths-argv, many-paths-argv: each path is one entry, in order; the full-size list is 25 paths.
#  - newline-paths-argv: paths separated by newlines, as a `paths: |` block gives them, are one entry each.
#  - empty-paths-never-pass: an empty ZIZMOR_PATHS never reads PASS with no path to audit.
#  - findings-exit-13-fails, clean-exit-0-passes: zizmor's own exit code decides run.sh's exit code.
#  - action-input-default-is-github: the action's paths input defaults to .github/.
#  - action-runs-run-sh: a run: block of action.yml runs run.sh.
#  - paths-reach-run-sh-through-env: action.yml maps ZIZMOR_PATHS from inputs.paths in an env: block.
#  - no-expr-in-run: no ${{ expression sits in any run: block of action.yml.
#  - scanner-*: run_blocks, the reader behind no-expr-in-run, sees a run: line, a block body with a lone
#    quote and a comment opener in a string, and does not read env: before run: or a key after a block.
#  - checks-zizmor-step-is-the-action, checks-zizmor-step-passes-paths: checks.yml's zizmor step.
#  - one-home-for-the-pin: the pin appears only in actions/zizmor/run.sh.
# A missing file FAILs its cases by name. The suite prints every case and never stops early.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
# One run folder per test run (test-temp-standard): lint/_test_temp.py makes it under the repo's one temp root.
work=$(python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import _test_temp; print(_test_temp.run_folder())' "$root/lint") || work=""
[ -n "$work" ] || { echo "FAIL - run folder: lint/_test_temp.py made no run folder"; exit 1; }
trap 'rm -rf "$work"' EXIT

RUN_SH="$here/run.sh"
ACTION_YML="$here/action.yml"
CHECKS="$root/.github/workflows/checks.yml"
PIN="zizmor==1.32.0"
bad=0
rc=0

pass() { echo "ok   $1"; }
fail() { echo "FAIL $1: $2"; bad=1; } # one case, one cause

# have <case> <file>: true when the file exists; else the case FAILs by name.
have() {
  [ -f "$2" ] && return 0
  fail "$1" "${2#"$root"/} is missing"
  return 1
}

# make_stub <dir> <exit>: a pipx that writes its argv, one entry per line, to <dir>/argv and exits <exit>.
make_stub() {
  mkdir -p "$1/bin"
  cat > "$1/bin/pipx" <<STUB
#!/bin/sh
printf '%s\n' "\$@" > "$1/argv"
exit $2
STUB
  chmod +x "$1/bin/pipx"
}

# run_sh <dir> <exit> [NAME=value ...]: run.sh in a fresh <dir> with the stub first on PATH. ZIZMOR_PATHS is
# unset unless the case sets it. Sets rc to run.sh's exit code.
run_sh() {
  dir=$1; code=$2; shift 2
  rm -rf "$dir"; mkdir -p "$dir"; make_stub "$dir" "$code"
  (cd "$dir" && env -u ZIZMOR_PATHS PATH="$dir/bin:$PATH" "$@" bash "$RUN_SH" > "$dir/out" 2>&1)
  rc=$?
}

# called <case> <dir>: true when the stub recorded a call. Else the case FAILs with run.sh's own output.
called() {
  [ -f "$2/argv" ] && return 0
  fail "$1" "pipx was never called (run.sh rc $rc): $(head -c 300 "$2/out" 2>/dev/null | tr '\n' ' ')"
  return 1
}

# argv_is <case> <dir> <entry>...: the recorded argv is exactly these entries, one per line.
argv_is() {
  case_name=$1; dir=$2; shift 2
  want=$(printf '%s\n' "$@")
  got=$(cat "$dir/argv")
  if [ "$got" = "$want" ]; then
    pass "$case_name"
  else
    fail "$case_name" "pipx argv was [$(printf '%s' "$got" | tr '\n' ' ')], wanted [$(printf '%s' "$want" | tr '\n' ' ')]"
  fi
}

# run_blocks <file>: the key line and body of each run: value in a YAML file, read by indent. A blank line
# keeps a block open; a line at or left of the key's column closes it.
run_blocks() {
  awk '
    /^[ \t-]*run:/ { ind = index($0, "run:") - 1; inrun = 1; print; next }
    inrun && /^[ \t]*$/ { next }
    inrun && (match($0, /[^ \t]/) - 1 > ind) { print; next }
    { inrun = 0 }
  ' "$1"
}

# expr_lines <file>: how many run: lines of the file hold a ${{ expression.
expr_lines() { run_blocks "$1" | grep -c -F "\${{"; }

# scan_case <case> <file> <yes|no>: run_blocks finds an expression line in the file, or none.
scan_case() {
  n=$(expr_lines "$2")
  if [ "$3" = yes ] && [ "$n" -ge 1 ]; then
    pass "$1"
  elif [ "$3" = no ] && [ "$n" -eq 0 ]; then
    pass "$1"
  else
    fail "$1" "run_blocks read $n expression line(s), wanted $3"
  fi
}

# paths_default <action.yml>: the default of the paths input, quotes removed; empty when absent.
paths_default() {
  awk '
    /^  paths:[ \t]*$/ { inp = 1; next }
    inp && /^  [^ ]/ { inp = 0 }
    inp && /^    default:/ { sub(/^    default:[ \t]*/, ""); gsub(/[\042\047]/, ""); print; exit }
  ' "$1"
}

# zizmor_step <uses|paths>: the checks job's zizmor step's uses: value or its with: paths value, read with
# lint/workflow_steps.py (the one step parser). Prints "absent" when the job has no step of that name.
zizmor_step() {
  python3 -I -c '
import re, sys
sys.path.insert(0, sys.argv[1])
from workflow_steps import job_block, step_blocks, step_key
with open(sys.argv[2], encoding="utf-8") as f:
    text = f.read()
for st in step_blocks(job_block(text, "checks") or ""):
    if step_key(st, "name") != "Workflow supply-chain audit (zizmor)":
        continue
    if sys.argv[3] == "uses":
        print(step_key(st, "uses") or "no uses: key")
    else:
        m = re.search(r"^          paths:[ \t]*(.*?)[ \t]*$", st, re.M)
        print(m.group(1) if m else "no with: paths key")
    break
else:
    print("absent")
' "$root/lint" "$CHECKS" "$1"
}

# control: the stub records its argv and exits with its code. It needs no run.sh, so it passes on old code.
ctl="$work/control"
make_stub "$ctl" 13
(cd "$ctl" && PATH="$ctl/bin:$PATH" pipx run "$PIN" .github/ actions/ > "$ctl/out" 2>&1)
crc=$?
if [ ! -f "$ctl/argv" ]; then
  fail control-stub-records-argv "the stub recorded no argv"
elif [ "$crc" -ne 13 ]; then
  fail control-stub-records-argv "the stub exited $crc, wanted its code 13"
else
  argv_is control-stub-records-argv "$ctl" run "$PIN" .github/ actions/
fi

d="$work/default"
if have default-paths-argv "$RUN_SH"; then
  run_sh "$d" 0
  if called default-paths-argv "$d"; then
    argv_is default-paths-argv "$d" run "$PIN" .github/
  fi
fi

d="$work/two"
if have two-paths-argv "$RUN_SH"; then
  run_sh "$d" 0 "ZIZMOR_PATHS=.github/ actions/"
  if called two-paths-argv "$d"; then
    argv_is two-paths-argv "$d" run "$PIN" .github/ actions/
  fi
fi

many=()
for i in $(seq 1 25); do many+=("dir$i/"); done
d="$work/many"
if have many-paths-argv "$RUN_SH"; then
  run_sh "$d" 0 "ZIZMOR_PATHS=${many[*]}"
  if called many-paths-argv "$d"; then
    argv_is many-paths-argv "$d" run "$PIN" "${many[@]}"
  fi
fi

d="$work/newline"
if have newline-paths-argv "$RUN_SH"; then
  # A `paths: |` block hands run.sh one value with a newline between paths and a trailing one.
  run_sh "$d" 0 "ZIZMOR_PATHS=.github/
actions/
"
  if called newline-paths-argv "$d"; then
    argv_is newline-paths-argv "$d" run "$PIN" .github/ actions/
  fi
fi

d="$work/empty"
if have empty-paths-never-pass "$RUN_SH"; then
  run_sh "$d" 0 ZIZMOR_PATHS=
  if [ "$rc" -ne 0 ]; then
    pass empty-paths-never-pass
  elif [ ! -f "$d/argv" ]; then
    fail empty-paths-never-pass "run.sh exited 0 without calling pipx"
  elif [ "$(grep -c '' "$d/argv")" -lt 3 ]; then
    fail empty-paths-never-pass "run.sh exited 0 with no path for zizmor to audit"
  else
    pass empty-paths-never-pass
  fi
fi

d="$work/findings"
if have findings-exit-13-fails "$RUN_SH"; then
  run_sh "$d" 13
  if called findings-exit-13-fails "$d"; then
    if [ "$rc" -ne 0 ]; then
      pass findings-exit-13-fails
    else
      fail findings-exit-13-fails "run.sh exited 0 when zizmor exited 13, its findings code"
    fi
  fi
fi

d="$work/clean"
if have clean-exit-0-passes "$RUN_SH"; then
  run_sh "$d" 0
  if called clean-exit-0-passes "$d"; then
    if [ "$rc" -eq 0 ]; then
      pass clean-exit-0-passes
    else
      fail clean-exit-0-passes "run.sh exited $rc when zizmor exited 0"
    fi
  fi
fi

if have action-input-default-is-github "$ACTION_YML"; then
  default=$(paths_default "$ACTION_YML")
  if [ "$default" = ".github/" ]; then
    pass action-input-default-is-github
  else
    fail action-input-default-is-github "the paths input default is '$default', wanted .github/"
  fi
fi

if have action-runs-run-sh "$ACTION_YML"; then
  if run_blocks "$ACTION_YML" | grep -q -F 'run.sh'; then
    pass action-runs-run-sh
  else
    fail action-runs-run-sh "no run: block of action.yml runs run.sh"
  fi
fi

if have paths-reach-run-sh-through-env "$ACTION_YML"; then
  if grep -q -E "^[[:space:]]+ZIZMOR_PATHS:[[:space:]]+[$]\{\{[[:space:]]*inputs\.paths[[:space:]]*\}\}[[:space:]]*$" "$ACTION_YML"; then
    pass paths-reach-run-sh-through-env
  else
    fail paths-reach-run-sh-through-env "action.yml does not map ZIZMOR_PATHS from inputs.paths in an env: block"
  fi
fi

if have no-expr-in-run "$ACTION_YML"; then
  n=$(expr_lines "$ACTION_YML")
  if [ "$n" -eq 0 ]; then
    pass no-expr-in-run
  else
    fail no-expr-in-run "$n run: line(s) of action.yml hold a \${{ expression; pass inputs through env"
  fi
fi

# The scanner's own cases: a run line whose comment opener sits in a string and whose quote is lone, a block
# body with the same, and the two shapes that must not count (env: before run:, and a key after a block).
scan="$work/scan"
mkdir -p "$scan"
cat > "$scan/line.yml" <<'YML'
    - name: a
      run: echo "# ${{ inputs.paths }}" && echo Don't
YML
cat > "$scan/block.yml" <<'YML'
      run: |
        echo "#" 'lone quote
        bash run.sh "${{ inputs.paths }}"
YML
cat > "$scan/env.yml" <<'YML'
      env:
        ZIZMOR_PATHS: ${{ inputs.paths }}
      run: bash "$ACTION_PATH/run.sh"
YML
cat > "$scan/after.yml" <<'YML'
      run: |
        echo ok
      env:
        ZIZMOR_PATHS: ${{ inputs.paths }}
YML
scan_case scanner-sees-expr-on-run-line "$scan/line.yml" yes
scan_case scanner-sees-expr-in-run-block "$scan/block.yml" yes
scan_case scanner-ignores-env-before-run "$scan/env.yml" no
scan_case scanner-ends-block-before-env "$scan/after.yml" no

u=$(zizmor_step uses)
if [ "$u" = absent ]; then
  fail checks-zizmor-step-is-the-action "checks.yml has no step named Workflow supply-chain audit (zizmor)"
elif [ "$u" = "\$/actions/zizmor" ]; then
  pass checks-zizmor-step-is-the-action
else
  fail checks-zizmor-step-is-the-action "the zizmor step's uses is '$u', wanted \$/actions/zizmor"
fi

p=$(zizmor_step paths)
if [ "$p" = absent ]; then
  fail checks-zizmor-step-passes-paths "checks.yml has no step named Workflow supply-chain audit (zizmor)"
elif [ "$p" = ".github/ actions/" ]; then
  pass checks-zizmor-step-passes-paths
else
  fail checks-zizmor-step-passes-paths "the zizmor step's with: paths is '$p', wanted '.github/ actions/'"
fi

# The pin's one home. git grep reads tracked files only; this file is excluded, since it names the pin.
hits=$(git -C "$root" grep -n 'zizmor==' -- .github/ actions/ ':!actions/zizmor/test_action.sh' 2>&1)
grc=$?
if [ "$grc" -eq 1 ]; then
  fail one-home-for-the-pin "no zizmor== pin under .github/ or actions/; wanted one line in actions/zizmor/run.sh"
elif [ "$grc" -ge 2 ]; then
  fail one-home-for-the-pin "git grep failed: $hits"
elif [ "$(printf '%s\n' "$hits" | grep -c '')" -eq 1 ] && [ "${hits%%:*}" = actions/zizmor/run.sh ]; then
  pass one-home-for-the-pin
else
  fail one-home-for-the-pin "the pin appears in $(printf '%s' "$hits" | cut -d: -f1 | sort -u | tr '\n' ' ')($(printf '%s\n' "$hits" | grep -c '') lines); wanted one line in actions/zizmor/run.sh"
fi

exit "$bad"
