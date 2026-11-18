#!/usr/bin/env bash
# The shared push-skip action's fixture suite. Static: action.yml is a composite with one decide step, which runs push-skip.py
# from the action path, is not continue-on-error, and reads WORKFLOW from inputs.workflow. Pinned: the script runs from a copy
# that holds only actions/push-skip, lint/, hooks/required_check.py (lint/ imports the required check's name from it),
# .github/scripts/nightly-skip.py and this repo's checks.yml. That checks.yml is a decoy: a pinned child must never read it.
# The calling workspace holds the child's checks.yml, CHILD_GOOD from lint/test_all_jobs_passed.py. api_get answers canned
# reads, so nothing reaches the network. Each case prints ok or FAIL, and the exit is 0 only when every case is ok.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
# One run folder per test run (test-temp-standard): lint/_test_temp.py makes it under the repo's one temp root.
work=$(python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import _test_temp; print(_test_temp.run_folder())' "$root/lint") || work=""
[ -n "$work" ] || { echo "FAIL - run folder: lint/_test_temp.py made no run folder"; exit 1; }
trap 'rm -rf "$work"' EXIT
bad=0
ok() { echo "ok   $1"; }
no() { echo "FAIL $1"; bad=1; }

# Static: the action's own wiring, read from action.yml.
action="$here/action.yml"
grep -qxE '  using: composite' "$action" && ok "static: action.yml is a composite" || no "static: action.yml is not a composite"
[ "$(grep -c '^    - name:' "$action")" -eq 1 ] && ok "static: the composite has one step" || no "static: the composite does not have exactly one step"
[ "$(grep -c '^      id: decide$' "$action")" -eq 1 ] && ok "static: the one step has id decide" || no "static: the step with id decide is missing"
grep -qxF '      run: python3 "${{ github.action_path }}/push-skip.py"' "$action" && ok "static: the step runs push-skip.py from the action path" \
  || no "static: the step does not run push-skip.py from the action path"
grep -q 'continue-on-error' "$action" && no "static: the step is continue-on-error, so a failed decision would not fail the job" \
  || ok "static: the step is not continue-on-error"
grep -qF 'WORKFLOW: ${{ inputs.workflow }}' "$action" && ok "static: WORKFLOW is set from inputs.workflow" \
  || no "static: WORKFLOW is not set from inputs.workflow"

# Pinned: a copy of the action and its readers only, then a workspace that holds the child's workflow.
pin="$work/pin"; caller="$work/caller"
mkdir -p "$pin/actions" "$pin/.github/scripts" "$pin/.github/workflows" "$caller/.github/workflows"
cp -r "$here" "$pin/actions/push-skip" && cp -r "$root/lint" "$pin/lint" \
  && mkdir -p "$pin/hooks" && cp "$root/hooks/required_check.py" "$pin/hooks/" \
  && cp "$root/.github/scripts/nightly-skip.py" "$pin/.github/scripts/" && cp "$root/.github/workflows/checks.yml" "$pin/.github/workflows/checks.yml" \
  || { echo "FAIL - pin: the copy of the action and its readers failed"; exit 1; }
python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import test_all_jobs_passed as t; sys.stdout.write(t.CHILD_GOOD)' "$root/lint" \
  > "$caller/.github/workflows/checks.yml" || { echo "FAIL - fixture: lint/test_all_jobs_passed.py did not give CHILD_GOOD"; exit 1; }

# The macOS caller: this repo's checks.yml. Its macOS jobs run on a schedule and a dispatch only (owner, 01:33 CST Nov 16), and its
# scope-skips map names each fast Windows job with the flags its job-level if reads (R62 and R63). checks-rest is a suite job the map
# does not name, and checks-windows-rest is one it names. The readback is the rules reader's, so the cases below rest on it.
readback=$(python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import all_jobs_passed_rules as r; import test_windows_split as t
text = open(sys.argv[2], encoding="utf-8").read()
named = r.scope_skips_map(text)
fast = all(sorted(named.get(n, [])) == sorted(f) for n, f in t.FAST_WINDOWS_JOBS.items()) and sorted(named) == sorted(t.FAST_WINDOWS_JOBS)
jobs = t.all_jobs(text)
print("same" if fast and "checks-rest" in jobs and "checks-rest" not in named and "checks-windows-rest" in named else sorted(named))' "$root/lint" "$root/.github/workflows/checks.yml") || readback=""
[ "$readback" = "same" ] && ok "static: checks.yml's scope-skips map names each fast Windows job, and checks-rest is no name in it" \
  || no "static: checks.yml's scope-skips map is not the fast-job map, or checks-rest is named: $readback"
macos_caller="$work/macos_caller"
mkdir -p "$macos_caller/.github/workflows"
cp "$root/.github/workflows/checks.yml" "$macos_caller/.github/workflows/checks.yml" \
  || { echo "FAIL - fixture: the macOS caller could not be written"; exit 1; }

# The scope-skips proof, on a literal map: the mapped caller is CHILD_GOOD with a scope-skips input that names lint, one of its own suite
# jobs. No macOS job is named, so these cases do not depend on the macOS jobs. The step is spelled $/actions/all-jobs-passed, the spelling
# the rules reader matches (ALL_JOBS_PASSED_USES in lint/all_jobs_passed_rules.py); a child's pinned spelling reads as no map.
mapped="$work/mapped_caller"
mkdir -p "$mapped/.github/workflows"
cat > "$work/mapped.py" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
import test_all_jobs_passed as t
anchor = "          needs: ${{ toJSON(needs) }} # every job above\n"
pinned_uses = "shivinate7/claude-settings/actions/all-jobs-passed@" + t.CHILD_PIN
assert t.CHILD_GOOD.count(anchor) == 1 and t.CHILD_GOOD.count(pinned_uses) == 1, "the all-jobs-passed step changed: the map must follow it"
text = t.CHILD_GOOD.replace(pinned_uses, "$/actions/all-jobs-passed").replace(anchor, anchor + "          scope-skips: '{\"lint\": [\"code\"]}'\n", 1)
sys.stdout.write(text)
PY
python3 -I "$work/mapped.py" "$root/lint" > "$mapped/.github/workflows/checks.yml" \
  || { echo "FAIL - fixture: the mapped caller could not be written"; exit 1; }
# P7: the map reads back from the mapped caller before any verdict is read from it.
readback=$(python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import all_jobs_passed_rules as r; print(sorted(r.scope_skips_map(open(sys.argv[2], encoding="utf-8").read())))' "$root/lint" "$mapped/.github/workflows/checks.yml") || readback=""
[ "$readback" = "['lint']" ] && ok "fixture: the mapped caller's scope-skips map reads back as lint" \
  || no "fixture: the mapped caller's scope-skips map reads back as $readback, wanted ['lint']"

# The driver: loads the pinned script, answers its reads from the case's canned routes, and prints the skip value it wrote.
cat > "$work/drive.py" <<'PY'
import contextlib, importlib.util, io, os, sys, urllib.parse
pin, caller, case, outdir = sys.argv[1:5]
REPO, TREE, PUSH, BATCH, LANE = "owner/repo", "a" * 40, "c" * 40, "d" * 40, "e" * 40
ROLLUP, WHEN = "all-jobs-passed", "2026-11-12T10:00:00Z"


def run(name, conclusion="success"):
    return {"name": name, "status": "completed", "conclusion": conclusion, "started_at": WHEN}


def step(name, conclusion="success"):
    return {"name": name, "status": "completed", "conclusion": conclusion}


def job(name, conclusion="success", steps=None):
    return {"name": name, "status": "completed", "conclusion": conclusion,
            "steps": [step("Run")] if steps is None else steps}


def batch_reads(runs=None):
    runs = [run(ROLLUP), run("lint"), run("test-mac")] if runs is None else runs
    return {"commits/%s/pulls" % PUSH: [{"head": {"ref": "batch-x", "sha": BATCH}}],
            "git/commits/%s" % BATCH: {"tree": {"sha": TREE}},
            "commits/%s/check-runs" % BATCH: {"check_runs": runs}}


def lane_reads(jobs=None):
    if jobs is None:
        jobs = [job(ROLLUP), job("lint"), job("test-mac"), job("publish", "skipped", steps=[])]
    return {"commits/%s/pulls" % PUSH: [{"head": {"ref": "lane-x", "sha": LANE}, "merged_at": WHEN}],
            "git/commits/%s" % LANE: {"tree": {"sha": TREE}},
            "actions/runs": {"workflow_runs": [{"id": 7, "name": "checks", "path": ".github/workflows/checks.yml", "event": "pull_request",
                                                "head_sha": LANE, "status": "completed", "conclusion": "success", "created_at": WHEN}]},
            "actions/runs/7/jobs": {"jobs": jobs}}


def caller_jobs():
    """Every job of the calling workflow, and which of them are macOS jobs, read by the pinned copy's own reader (lint/test_windows_split.py)."""
    sys.path.insert(0, os.path.join(pin, "lint"))
    import test_windows_split
    with open(os.path.join(caller, ".github", "workflows", "checks.yml"), encoding="utf-8") as handle:
        return sorted(test_windows_split.all_jobs(handle.read())), set(test_windows_split.MACOS_JOBS)


def skipped_runs(jobs, skipped):
    """The check runs of a ready batch head: each job in `skipped` skipped, every other job passed."""
    return [run(name, "skipped" if name in skipped else "success") for name in jobs]


def skipped_jobs(jobs, skipped):
    """The jobs of a ready lone-lane run: each job in `skipped` skipped with no steps, every other job passed."""
    return [job(name, "skipped", steps=[]) if name in skipped else job(name) for name in jobs]


ALL_JOBS, MACOS = caller_jobs()
SUITE = "checks-rest"  # a suite job of checks.yml that no macOS rule names, and the scope-skips map does not name: its skip is a gap
NAMED = "checks-windows-rest"  # a suite job the scope-skips map names: its skip is intended
CASES = {
    "green_batch": (batch_reads(), {}),
    "green_lane": (lane_reads(), {}),
    "skipped_suite": (lane_reads([job(ROLLUP), job("lint"), job("test-mac", "skipped", steps=[])]), {}),
    "skipped_step": (lane_reads([job(ROLLUP), job("lint", steps=[step("Run"), step("Lint tests", "skipped")]), job("test-mac")]), {}),
    "schedule": (lane_reads(), {"EVENT": "schedule"}),
    "dispatch": (lane_reads(), {"EVENT": "workflow_dispatch"}),
}
if case.startswith("macos"):  # the macOS cases read the caller's own jobs, so the suite job they refuse must be one of them
    assert SUITE in ALL_JOBS and NAMED in ALL_JOBS, "checks-rest or checks-windows-rest is not a job of checks.yml, so a macOS case would probe the wrong job"
CASES["macos_skipped_batch"] = (batch_reads(skipped_runs(ALL_JOBS, MACOS)), {})
CASES["macos_skipped_lane"] = (lane_reads(skipped_jobs(ALL_JOBS, MACOS)), {})
CASES["macos_and_suite_skipped_batch"] = (batch_reads(skipped_runs(ALL_JOBS, MACOS | {SUITE})), {})
CASES["macos_and_named_skipped_batch"] = (batch_reads(skipped_runs(ALL_JOBS, MACOS | {NAMED})), {})
# The scope-skips proof: the mapped caller names lint, so a skipped lint is proven only by the same run's scope job. Each case without a
# passing scope job, and each skipped job the map does not name, must stay a gap.
CASES["map_batch_proven"] = (batch_reads([run(ROLLUP), run("scope"), run("lint", "skipped"), run("test-mac")]), {})
CASES["map_batch_scope_failed"] = (batch_reads([run(ROLLUP), run("scope", "failure"), run("lint", "skipped"), run("test-mac")]), {})
CASES["map_batch_scope_absent"] = (batch_reads([run(ROLLUP), run("lint", "skipped"), run("test-mac")]), {})
CASES["map_batch_unnamed"] = (batch_reads([run(ROLLUP), run("scope"), run("lint"), run("test-mac", "skipped")]), {})
CASES["map_lane_proven"] = (lane_reads([job(ROLLUP), job("scope"), job("lint", "skipped", steps=[]), job("test-mac")]), {})
CASES["map_lane_scope_failed"] = (lane_reads([job(ROLLUP), job("scope", "failure"), job("lint", "skipped", steps=[]), job("test-mac")]), {})
CASES["map_lane_scope_absent"] = (lane_reads([job(ROLLUP), job("lint", "skipped", steps=[]), job("test-mac")]), {})
# No map at all (the empty state): the same run as map_batch_proven gives skip=false on the caller with no scope-skips input.
CASES["unmapped_batch_proven"] = (batch_reads([run(ROLLUP), run("scope"), run("lint", "skipped"), run("test-mac")]), {})
routes, extra = CASES[case]


def api_get(url, token):
    path = urllib.parse.urlsplit(url).path.split("/repos/%s/" % REPO, 1)[1]
    if path not in routes:
        raise RuntimeError("no canned read for %s" % path)
    return routes[path]


spec = importlib.util.spec_from_file_location("push_skip_pinned", os.path.join(pin, "actions", "push-skip", "push-skip.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module._nightly_skip().api_get = api_get
out = os.path.join(outdir, "out-" + case)
env = {"REPO": REPO, "GH_TOKEN": "t", "HEAD_SHA": PUSH, "PUSH_TREE": TREE, "GITHUB_WORKSPACE": caller, "GITHUB_OUTPUT": out}
env.update(extra)
printed = io.StringIO()
with contextlib.redirect_stdout(printed):
    module.main(env)
sys.stderr.write(printed.getvalue())
lines = [l.strip()[len("skip="):] for l in open(out, encoding="utf-8") if l.startswith("skip=")] if os.path.isfile(out) else []
print(lines[0] if len(lines) == 1 else "none")
PY

# Pinned cases: the script the copy carries decides from the caller's workspace, with its own readers.
pinned() { # pinned <case> <want> [the calling checkout, the child's by default]
  local got dir="${3:-$caller}"
  got=$(python3 -I "$work/drive.py" "$pin" "$dir" "$1" "$work" 2>"$work/$1.err") || got="error"
  if [ "$got" = "$2" ]; then ok "pinned: $1 gives skip=$2"
  else no "pinned: $1 gives skip=$got, wanted $2 ($(head -c 300 "$work/$1.err" | tr '\n' ' '))"; fi
}
pinned green_batch true
pinned green_lane true
pinned skipped_suite false
pinned skipped_step true
pinned schedule false
pinned dispatch false
pinned macos_skipped_batch true "$macos_caller"
pinned macos_skipped_lane true "$macos_caller"
pinned macos_and_suite_skipped_batch false "$macos_caller"
pinned macos_and_named_skipped_batch true "$macos_caller"
pinned map_batch_proven true "$mapped"
pinned map_batch_scope_failed false "$mapped"
pinned map_batch_scope_absent false "$mapped"
pinned map_batch_unnamed false "$mapped"
pinned map_lane_proven true "$mapped"
pinned map_lane_scope_failed false "$mapped"
pinned map_lane_scope_absent false "$mapped"
pinned unmapped_batch_proven false "$caller"

exit "$bad"
