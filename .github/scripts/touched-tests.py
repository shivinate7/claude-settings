#!/usr/bin/env python3
"""Selects the test files a draft lane PR touches, for .github/workflows/lane-touched-tests.yml.

Input (env): BASE_SHA, the PR's base commit. The checkout is at HEAD.
Output: lines written to $GITHUB_OUTPUT (stdout when unset):
  files, any                    every test either OS runs (the union), and whether it is non-empty
  files_windows, any_windows    the tests the Windows job runs
  files_macos, any_macos        the tests the macOS job runs
  matrix                        {"include": [{"os", "files"}]}, one entry per OS that has tests; files is a JSON list as text
Stdout also names every touched path and what became of it, so the run log shows each decision.

A touched path selects:
  a test file (patterns TEST_PATTERNS)                                       -> itself
  dir/x.py                                                                   -> dir/test_x.py
  dir/x.sh                                                                   -> dir/test_x.sh
  dir/x.mjs, dir/x.js                                                        -> dir/x.test.{mjs,js}, dir/tests/x.test.{mjs,js}; x.mjs also dir/test_x.mjs
  any non-.md path under skills/plain-english-map/                           -> every test in its tests folder
  any non-.md, non-test path under a folder named tests                      -> every test under that folder
Each selected test then lands in one of these places, each printed with its reason, none dropped silently:
  HEAVY           the batch shards it in its own jobs; running it per lane push is a cost blow-up
  NEEDS_SETUP     needs a browser or a tool this workflow does not install, or runs on one OS only
  NOT_ON_WINDOWS  checks.yml runs it on no Windows job, so the batch would show no Windows red for it
  NOT_ON_MACOS    a Windows-only suite that would false-red on macOS
  run             listed for each OS that does not exclude it; a *.test.ps1 is Windows only
An unreadable diff (no BASE_SHA, git fails) exits 1 and writes no output (decision ci-unknown-is-red).
"""
import fnmatch
import json
import os
import subprocess
import sys

# Test-file name patterns, matched on the file's own name.
TEST_PATTERNS = ("*.test.mjs", "*.test.js", "test_*.mjs", "test_*.py", "test_*.sh", "*.test.sh", "*.test.ps1")
# The patterns that run on Windows only (checks.yml: pointer-windows runs them under Windows PowerShell 5.1).
WINDOWS_ONLY_PATTERNS = ("*.test.ps1",)

# The suites checks.yml runs in shard jobs or under a step cap of its own (glob -> reason).
HEAVY = {
    "hooks/test_guard.py": "heavy: runs in the batch's shard jobs (GUARD_SHARD)",
    "merge/test_merge.py": "heavy: runs in the batch's shard jobs (MERGE_SHARD)",
    "janitor/test_sweep.py": "heavy: runs in the batch's checks-windows-sweep job",
    "hooks/test_install_src.sh": "heavy: runs in the batch's shell-macos job under its own step cap",
}

# Suites that need a browser or a tool this workflow does not install (glob -> reason).
NEEDS_SETUP = {
    "*/tests/page.test.mjs": "needs Playwright and Chromium; runs in checks-shoot on Linux only",
    "skills/waiting-page/tests/test_check_designs.mjs": "needs Playwright and Chromium; runs in checks-shoot on Linux only",
    "lint/test_shoot.mjs": "needs Playwright and Chromium; runs in checks-shoot on Linux only",
    "lint/test_ios_ship.sh": "needs macOS tooling (bin/ios-ship); runs in shell-macos only",
    "lint/test_sim_test.sh": "needs macOS tooling (bin/sim-test); runs in shell-macos only",
}

# Tests checks.yml runs on no Windows job: they run in `checks`, `checks-merge-install`, `checks-guard`, `checks-shoot`
# or a macOS job. Read from the jobs of checks.yml; a test missing here runs on Windows and may false-red.
# The batch shows no Windows red for these, so a draft run does not either.
NOT_ON_WINDOWS = (
    "actions/all-jobs-passed/test_action.sh",
    "actions/ci-alarm/test_action.sh",
    "actions/ci-alarm/test_clear_rule.py",
    "actions/ci-done-comment/test_comment.py",
    "actions/code-check/test_action.py",
    "actions/playwright-setup/test_action.py",
    "actions/readme-links/test_readme_links.py",
    "actions/ruling-kind/test_action.sh",
    "actions/silent-undo/test_action.sh",
    "actions/ste-lint/test_action.py",
    "actions/test_action_metadata.py",
    "actions/test_ruling_kind_records_dir.py",
    "actions/zizmor/test_action.sh",
    "githooks/main-ref/test_hook.sh",
    "githooks/test_pre_commit.sh",
    "hooks/test_auto_mode_allow.py",
    "hooks/test_cloud_setup.sh",
    "hooks/test_mutate_ci.py",
    "hooks/test_mutate_js.py",
    "hooks/test_mutate_replay.py",
    "hooks/test_mutate_report.py",
    "hooks/test_mutate_shared.py",
    "hooks/test_nowindow.py",
    "hooks/test_sim_boot_record.py",
    "hooks/test_stall_watch.py",
    "janitor/test_prove_agent_end_reap.py",
    "lint/test_all_jobs_passed.py",
    "lint/test_check_agent_models.py",
    "lint/test_check_artifact_cites.py",
    "lint/test_check_claude_md_size.py",
    "lint/test_check_comment_narration.py",
    "lint/test_check_debt_retire.py",
    "lint/test_check_glossary.py",
    "lint/test_check_hook_stubs.py",
    "lint/test_check_ios_mockup.py",
    "lint/test_check_landed_dirs.py",
    "lint/test_check_mod_versions.py",
    "lint/test_check_record_slugs.py",
    "lint/test_check_red_run.py",
    "lint/test_check_ruling_kind.py",
    "lint/test_check_shared_resources.py",
    "lint/test_check_silent_undo.py",
    "lint/test_check_skill_model_rows.py",
    "lint/test_check_unknown_reads_contract.py",
    "lint/test_ci_job.py",
    "lint/test_ci_scope.py",
    "lint/test_compliance_probes.py",
    "lint/test_find_copies.py",
    "lint/test_find_time_pinned.py",
    "lint/test_guard_log_report.py",
    "lint/test_hook_catalog.py",
    "lint/test_label_once.py",
    "lint/test_layout.py",
    "lint/test_no_window_spawn.py",
    "lint/test_notes_union_merge.py",
    "lint/test_prove_route_judge.py",
    "lint/test_repo_colour.py",
    "lint/test_report_guard_review.py",
    "lint/test_report_guard_stalled.py",
    "lint/test_retired_names.py",
    "lint/test_retired_repos.py",
    "lint/test_rm_shim.py",
    "lint/test_rule_audit.py",
    "lint/test_scanner_traps.mjs",
    "lint/test_settings_matcher.py",
    "lint/test_sim_lease.py",
    "lint/test_stale_cites.py",
    "lint/test_ste_autofix.py",
    "lint/test_test_git.py",
    "lint/test_touched_tests.py",
    "lint/test_tracked_tree.py",
    "lint/test_wait_pid.py",
    "merge/test_idle_lanes.py",
    "merge/test_install_from_main.sh",
    "merge/test_lane_lint.py",
    "merge/test_repaired_merges.py",
    "skills/ios-apps/tests/test_new_app.py",
    "skills/project-ops/tests/test_scaffold.py",
    "skills/roadmap/test_build.py",
    "skills/waiting-page/test_export_page.py",
    "skills/waiting-page/test_page_grant.py",
    "skills/waiting-page/test_skill_park_relay.py",
    "skills/waiting-page/test_splice.py",
    "skills/waiting-page/test_stale_pages.py",
    "testing/skip-locally-fail-in-ci.test.mjs",
)

# Windows-only suites that would false-red on macOS: hooks/test_install_windows.sh asserts the real Git Bash uname.
# The other tests only Windows and Linux jobs run (merge/test_cmd.py, merge/test_launch.py, hooks/test_stall_watch_stop.py)
# are portable by design (test_cmd.py runs bin/merge off Windows), so macOS runs them.
NOT_ON_MACOS = (
    "hooks/test_install_windows.sh",
)

MAP_DIR = "skills/plain-english-map/"
MAP_TESTS = MAP_DIR + "tests/"


def fail(message):
    print(f"touched-tests: {message}", file=sys.stderr)
    sys.exit(1)


def git(*args):
    r = subprocess.run(["git", *args], capture_output=True)
    if r.returncode:
        fail(f"git {args[0]} failed: {r.stderr.decode(errors='replace').strip()}")
    return r.stdout.decode(errors="replace")


def is_test(path):
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in TEST_PATTERNS)


def reason(path, table):
    for glob, why in table.items():
        if fnmatch.fnmatchcase(path, glob):
            return why
    return None


def candidates(path, tracked):
    """The test files `path` selects, from the tracked paths at HEAD."""
    if is_test(path):
        return {path}
    found = set()
    directory, _, name = path.rpartition("/")
    prefix = directory + "/" if directory else ""
    stem, dot, ext = name.rpartition(".")
    if dot and ext == "py":
        found.add(f"{prefix}test_{stem}.py")
    elif dot and ext == "sh":
        found.add(f"{prefix}test_{stem}.sh")
    elif dot and ext in ("mjs", "js"):
        for test_ext in ("mjs", "js"):
            found.add(f"{prefix}{stem}.test.{test_ext}")
            found.add(f"{prefix}tests/{stem}.test.{test_ext}")
        if ext == "mjs":
            found.add(f"{prefix}test_{stem}.mjs")
    if not path.endswith(".md"):
        if path.startswith(MAP_DIR):
            found |= {t for t in tracked if t.startswith(MAP_TESTS) and is_test(t)}
        parts = path.split("/")
        if "tests" in parts[:-1]:
            folder = "/".join(parts[: parts.index("tests") + 1]) + "/"
            found |= {t for t in tracked if t.startswith(folder) and is_test(t)}
    return {c for c in found if c in tracked}


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def flag(listed):
    return "true" if listed else "false"


def write_outputs(windows, macos):
    files = sorted(set(windows) | set(macos))
    matrix = [{"os": name, "files": json.dumps(listed)}
              for name, listed in (("windows-latest", windows), ("macos-latest", macos)) if listed]
    lines = (f"files={json.dumps(files)}\nany={flag(files)}\n"
             f"files_windows={json.dumps(windows)}\nany_windows={flag(windows)}\n"
             f"files_macos={json.dumps(macos)}\nany_macos={flag(macos)}\n"
             f"matrix={json.dumps({'include': matrix})}\n")
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with open(target, "a", encoding="utf-8", newline="\n") as f:
            f.write(lines)
    else:
        sys.stdout.write(lines)


def main():
    base = os.environ.get("BASE_SHA", "").strip()
    if not base:
        fail("BASE_SHA is not set: the diff is unknown, so no test list can be trusted")
    touched = git("diff", "--name-only", "--no-renames", "-z", f"{base}...HEAD").split("\0")
    tracked = set(git("ls-tree", "-r", "--name-only", "-z", "HEAD").split("\0")) - {""}
    touched = sorted(p for p in touched if p and p in tracked)
    selected = set()
    for path in touched:
        found = sorted(candidates(path, tracked))
        print(f"touched {path} -> {', '.join(found) if found else 'no test file maps to it'}")
        selected |= set(found)
    windows, macos = [], []
    for test in sorted(selected):
        why = reason(test, HEAVY) or reason(test, NEEDS_SETUP)
        if why:
            print(f"skip {test}: {why}")
            continue
        on = []
        if matches(test, NOT_ON_WINDOWS):
            print(f"skip {test} on windows: checks.yml runs it on no Windows job")
        else:
            on.append("windows")
            windows.append(test)
        if matches(test, WINDOWS_ONLY_PATTERNS):
            print(f"skip {test} on macos: a Windows-only test")
        elif matches(test, NOT_ON_MACOS):
            print(f"skip {test} on macos: a Windows-only suite that false-reds there")
        else:
            on.append("macos")
            macos.append(test)
        if on:
            print(f"run {test} on {' and '.join(on)}")
    write_outputs(windows, macos)


if __name__ == "__main__":
    main()
