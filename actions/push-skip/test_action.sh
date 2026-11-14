#!/usr/bin/env bash
# The shared push-skip action's fixture suite. Static: action.yml is a composite with one decide step, which runs push-skip.py
# from the action path, is not continue-on-error, and reads WORKFLOW from inputs.workflow. Pinned: the script runs from a copy
# that holds only actions/push-skip, lint/, .github/scripts/nightly-skip.py and this repo's checks.yml. That checks.yml is a
# decoy: a pinned child must never read it. The calling workspace holds the child's checks.yml, CHILD_GOOD from
# lint/test_all_jobs_passed.py. api_get answers canned reads, so nothing reaches the network. Each case prints ok or FAIL,
# and the exit is 0 only when every case is ok.
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
  && cp "$root/.github/scripts/nightly-skip.py" "$pin/.github/scripts/" && cp "$root/.github/workflows/checks.yml" "$pin/.github/workflows/checks.yml" \
  || { echo "FAIL - pin: the copy of the action and its readers failed"; exit 1; }
python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import test_all_jobs_passed as t; sys.stdout.write(t.CHILD_GOOD)' "$root/lint" \
  > "$caller/.github/workflows/checks.yml" || { echo "FAIL - fixture: lint/test_all_jobs_passed.py did not give CHILD_GOOD"; exit 1; }

# The scope-skip callers: this repo's checks.yml, which sets the macOS scope-skips map, and the same file with that input removed. The scope-skip
# jobs come from testing/scope_skips.py here, since the pinned copy holds no testing/ folder.
scope_skipped_caller="$work/scope_skipped_caller"; nomap_caller="$work/nomap_caller"
mkdir -p "$scope_skipped_caller/.github/workflows" "$nomap_caller/.github/workflows"
[ "$(grep -c '^          scope-skips: ' "$root/.github/workflows/checks.yml")" -eq 1 ] \
  || { echo "FAIL - fixture: checks.yml does not set its scope-skips input exactly once"; exit 1; }
cp "$root/.github/workflows/checks.yml" "$scope_skipped_caller/.github/workflows/checks.yml" \
  && sed '/^          scope-skips: /d' "$root/.github/workflows/checks.yml" > "$nomap_caller/.github/workflows/checks.yml" \
  || { echo "FAIL - fixture: the scope-skip callers could not be written"; exit 1; }
SCOPE_SKIPPED=$(python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import scope_skips; print(" ".join(sorted(scope_skips.MACOS_SCOPE_SKIPS)))' "$root/testing") \
  || { echo "FAIL - fixture: testing/scope_skips.py did not give MACOS_SCOPE_SKIPS"; exit 1; }
export SCOPE_SKIPPED

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


SCOPE_SKIPPED = os.environ.get("SCOPE_SKIPPED", "").split()  # the macOS scope skip's jobs, from testing/scope_skips.py (test_action.sh reads it: the pinned copy holds no testing/)


def caller_needed():
    """The jobs the caller's workflow needs, read by the pinned copy's own reader (lint/all_jobs_passed_rules.py), rollup included."""
    sys.path.insert(0, os.path.join(pin, "lint"))
    import all_jobs_passed_rules
    with open(os.path.join(caller, ".github", "workflows", "checks.yml"), encoding="utf-8") as handle:
        return all_jobs_passed_rules.split_jobs(handle.read())[0] + [ROLLUP]


def scope_skipped_runs(needed):
    """The check runs of a ready batch head: each scope-skipped job skipped by its flags, every other job passed."""
    return [run(name, "skipped" if name in SCOPE_SKIPPED else "success") for name in needed]


def scope_skipped_jobs(needed):
    """The jobs of a ready lone-lane run: each scope-skipped job skipped with no steps, every other job passed."""
    return [job(name, "skipped", steps=[]) if name in SCOPE_SKIPPED else job(name) for name in needed]


NEEDED = caller_needed()
CASES = {
    "green_batch": (batch_reads(), {}),
    "green_lane": (lane_reads(), {}),
    "skipped_suite": (lane_reads([job(ROLLUP), job("lint"), job("test-mac", "skipped", steps=[])]), {}),
    "skipped_step": (lane_reads([job(ROLLUP), job("lint", steps=[step("Run"), step("Lint tests", "skipped")]), job("test-mac")]), {}),
    "schedule": (lane_reads(), {"EVENT": "schedule"}),
    "dispatch": (lane_reads(), {"EVENT": "workflow_dispatch"}),
}
CASES["scope_skipped_batch"] = (batch_reads(scope_skipped_runs(NEEDED)), {})
CASES["scope_skipped_lane"] = (lane_reads(scope_skipped_jobs(NEEDED)), {})
CASES["scope_skipped_nomap"] = CASES["scope_skipped_batch"]  # the same ready run, judged against a caller whose scope-skips input is removed
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
pinned scope_skipped_batch true "$scope_skipped_caller"
pinned scope_skipped_lane true "$scope_skipped_caller"
pinned scope_skipped_nomap false "$nomap_caller"

exit "$bad"
