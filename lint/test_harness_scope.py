#!/usr/bin/env python3
"""CLI tests for the scope detector (.github/scripts/harness-scope.sh).

Each case builds a scratch git repo, commits a base, commits the changed paths, runs the script
with EVENT, BASE_SHA and BEFORE_SHA set, and reads the name=value lines it wrote to $GITHUB_OUTPUT.
HARNESS_SCOPE overrides the script path (for a successor). Needs bash on PATH.

The claim cases (ClaimLintOnly, run_pr) model CI: HEAD is the merge of the claim into the base,
HEAD_SHA is the PR head, EVENT_ACTION is github.event.action, PR_NUMBER is github.event.pull_request.number
(this PR's number, which the script must read), and the script reads the gates.yml pull_request runs on
BEFORE_SHA from `gh`. A stub `gh` on PATH logs its argv and answers only for BEFORE_SHA (STUB_SHA); a
non-zero exit is unreadable. It serves one runs list, newest first, in two views:
  - `gh run list ... --jq ...` (the query the script sends today) prints STUB_RUNLIST: one conclusion per line.
  - `gh api ...` with no --jq prints STUB_JSON, raw: {"workflow_runs": [{"conclusion", "created_at",
    "head_sha", "event", "pull_requests": [{"number", "base": {"sha"}}]}]}. The stub applies no jq, so the
    script reads this JSON with python3, not with --jq.
Any other query exits 1. Every run puts this stub first on PATH, so no test reaches the real gh.

Output names pinned (the `scope` job re-exports them as job outputs):
  JOB_FLAGS  one per gate job except the lint job `gates`: gates_windows, gates_windows_merge,
             gates_windows_rest, gates_macos, shell_macos, pointer_windows
  STEP_FLAGS code, guard, sweep (the suite flags the steps inside a job read)

Run with:  python3 lint/test_harness_scope.py -v
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.environ.get("HARNESS_SCOPE") or os.path.join(HERE, "..", ".github", "scripts", "harness-scope.sh")
JOB_FLAGS = ["gates_windows", "gates_windows_merge", "gates_windows_rest", "gates_macos", "shell_macos", "pointer_windows"]
STEP_FLAGS = ["code", "guard", "sweep"]
ALL = JOB_FLAGS + STEP_FLAGS
BASH = shutil.which("bash")


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


# The gh stub: logs its argv and, for a query that holds STUB_SHA, answers in one of two views of one runs list.
# `run list ... --jq ...` (the query the script sends today) prints STUB_RUNLIST. `api` with no --jq prints
# STUB_JSON, raw. The stub applies no jq, so an api call with --jq, and any other query, exits 1.
GH_STUB = r'''#!/usr/bin/env bash
printf '%s\n' "$*" >> "$STUB_LOG"
case "$*" in
  *"$STUB_SHA"*)
    case "$*" in
      "run list "*"--jq"*) printf '%s' "$STUB_RUNLIST"; exit "$STUB_EXIT" ;;
      "api "*"--jq"*) ;;
      "api "*) printf '%s' "$STUB_JSON"; exit "$STUB_EXIT" ;;
    esac ;;
esac
exit 1
'''


def stub_gh(sd, sha="", runs=(), code=1):
    """Write a `gh` into sd and return the env that puts it first on PATH. `runs`: gh_run() dicts, newest first.
    The default answers nothing, so no run reaches the real gh (which is authenticated on the author's machine)."""
    path = os.path.join(sd, "gh")
    with open(path, "w", newline="\n") as f:  # LF, so bash reads the shebang
        f.write(GH_STUB)
    os.chmod(path, 0o755)
    rest = [{"conclusion": r["conclusion"], "created_at": r["created_at"], "head_sha": sha, "event": "pull_request",
             "pull_requests": [{"number": int(r["pr"]), "base": {"sha": r["base"]}}]} for r in runs]
    return {"PATH": sd + os.pathsep + os.environ["PATH"], "STUB_LOG": os.path.join(sd, "gh.log"),
            "STUB_SHA": sha, "STUB_EXIT": str(code), "STUB_JSON": json.dumps({"workflow_runs": rest}),
            "STUB_RUNLIST": "".join(("null" if r["conclusion"] is None else r["conclusion"]) + "\n" for r in runs)}


def make_base(d, existing=(), landed=None):
    """A scratch repo holding one base commit. -> its sha."""
    git(d, "init", "-q")
    git(d, "config", "user.email", "t@t")
    git(d, "config", "user.name", "t")
    git(d, "config", "commit.gpgsign", "false")
    open(os.path.join(d, "seed.txt"), "w").write("seed\n")
    # The base holds landed-dirs.txt: the repo's own, or `landed` (a list of dir names) in its place.
    with open(os.path.join(HERE, "..", "landed-dirs.txt")) as f:
        real = f.read()
    open(os.path.join(d, "landed-dirs.txt"), "w").write(real if landed is None else chr(10).join(landed) + chr(10))
    for p in existing:  # in the base commit, so the head commit modifies them
        os.makedirs(os.path.dirname(os.path.join(d, p)), exist_ok=True)
        open(os.path.join(d, p), "w").write("old\n")
    git(d, "add", "-A")
    git(d, "commit", "-qm", "base")
    return git(d, "rev-parse", "HEAD")


def commit_files(d, paths, msg=("pre",)):
    """One commit that writes `paths`; `msg` gives its -m paragraphs. -> its sha."""
    for p in paths:
        full = os.path.join(d, p)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        open(full, "w").write("changed\n")
    git(d, "add", "-A")
    git(d, "commit", "-q", "--allow-empty", *[x for m in msg for x in ("-m", m)])
    return git(d, "rev-parse", "HEAD")


def run(paths, event="pull_request", base="auto", before="auto", existing=(), landed=None):
    """-> {name: 'true'|'false'} the script wrote. `paths` are committed on top of one base commit."""
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as sd:
        sha = make_base(d, existing, landed)
        for p in paths:
            full = os.path.join(d, p)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            open(full, "w").write("changed\n")
        git(d, "add", "-A")
        git(d, "commit", "-qm", "head", "--allow-empty")
        out = os.path.join(sd, "out.txt")
        env = dict(os.environ, EVENT=event, GITHUB_OUTPUT=out,
                   BASE_SHA=sha if base == "auto" else base, BEFORE_SHA=sha if before == "auto" else before,
                   **stub_gh(sd))
        r = subprocess.run([BASH, os.path.abspath(SCRIPT)], cwd=d, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        lines = open(out).read().split()
        return dict(l.split("=", 1) for l in lines)


ZZ = ("zz-unmapped/x.bin",)  # the PR's own earlier commit: today's scope maps it to every flag
CLAIM = ("Claim record numbers", "Record-claim: D-002")  # the merge tool's claim commit, as commit_claim writes it
CLAIM_FILES = ("decisions/zz-claim.md",)
PR = "7"  # this pull request's number: run_pr exports it as PR_NUMBER
T_OLD, T_NEW = "2026-10-13T08:00:00Z", "2026-10-13T09:00:00Z"  # ISO 8601 created_at: string order is time order
STALE_BASE = "d" * 40  # a base sha that is not this PR's BASE_SHA


def gh_run(conclusion, created, pr=PR, base=None):
    """One gates.yml pull_request run on BEFORE_SHA, for stub_gh. conclusion None: not concluded.
    base None: this fixture's BASE_SHA, which run_pr fills in."""
    return {"conclusion": conclusion, "created_at": created, "pr": pr, "base": base}


def run_pr(paths, *, chain=(ZZ,), back=1, msg=CLAIM, action="synchronize", runs=(gh_run("success", T_NEW),), code=0):
    """A synchronize on a pull request. -> (flags, gh argv lines, {base, before, claim} shas).

    Commits: a base, one commit per tuple in `chain` (the PR's own work), then the claim commit `paths`
    with `msg`. CI checks out the merge of the claim into the base, so HEAD is that merge and HEAD_SHA
    names the PR head. BEFORE_SHA is `back` commits behind the claim (the head before the push).
    `runs` = the gh_run() dicts the stub serves for BEFORE_SHA, newest first (default: one green run of
    this PR on this base). `code` = the stub's exit code; non-zero is unreadable."""
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as sd:
        base = make_base(d)
        for files in chain:
            commit_files(d, files)
        claim = commit_files(d, paths, msg)
        git(d, "checkout", "-q", "--detach", base)
        git(d, "merge", "-q", "--no-ff", "-m", "Merge pull request", claim)
        before = git(d, "rev-parse", f"{claim}~{back}")
        runs = [dict(r, base=base if r["base"] is None else r["base"]) for r in runs]
        out = os.path.join(sd, "out.txt")
        env = dict(os.environ, EVENT="pull_request", EVENT_ACTION=action, BASE_SHA=base, BEFORE_SHA=before,
                   HEAD_SHA=claim, PR_NUMBER=PR, GITHUB_OUTPUT=out, GITHUB_REPOSITORY="owner/repo",
                   **stub_gh(sd, before, runs, code))
        r = subprocess.run([BASH, os.path.abspath(SCRIPT)], cwd=d, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        flags = dict(l.split("=", 1) for l in open(out).read().split())
        log = os.path.join(sd, "gh.log")
        calls = open(log).read().splitlines() if os.path.exists(log) else []
        return flags, calls, {"base": base, "before": before, "claim": claim}


@unittest.skipUnless(BASH, "bash not on PATH")
class Scope(unittest.TestCase):
    def assertFlags(self, got, want_true=(), want_false=()):
        for n in ALL:
            self.assertIn(n, got, f"output {n} missing: {got}")
        for n in want_true:
            self.assertEqual(got[n], "true", f"{n}: {got}")
        for n in want_false:
            self.assertEqual(got[n], "false", f"{n}: {got}")

    def test_docs_only_pr_turns_every_job_off(self):
        got = run(["README.md", "decisions/some-record.md"])
        self.assertFlags(got, want_false=ALL)

    def test_merge_change_turns_the_merge_job_on(self):
        got = run(["merge/merge.py"])
        self.assertFlags(got, want_true=["gates_windows_merge", "code"])

    def test_guard_change_turns_the_guard_suites_on(self):
        got = run(["hooks/guard.py"])
        self.assertFlags(got, want_true=["gates_windows", "gates_macos", "guard", "sweep", "code"])

    def test_a_merge_change_leaves_a_job_that_never_runs_merge_suites_off(self):
        got = run(["merge/merge.py"])
        self.assertFlags(got, want_false=["pointer_windows", "shell_macos"])

    def test_workflow_or_scope_script_change_runs_everything(self):
        for p in (".github/workflows/gates.yml", ".github/scripts/harness-scope.sh"):
            self.assertFlags(run([p]), want_true=ALL)

    def test_unmapped_path_runs_everything(self):
        self.assertFlags(run(["zz-unmapped/blob.bin"]), want_true=ALL)

    def test_unreadable_diff_runs_everything(self):
        bogus = "f" * 40
        self.assertFlags(run(["README.md"], base=bogus), want_true=ALL)
        self.assertFlags(run(["README.md"], base=""), want_true=ALL)

    def test_push_schedule_and_dispatch_run_everything_even_for_docs(self):
        for ev in ("push", "schedule", "workflow_dispatch"):
            self.assertFlags(run(["README.md"], event=ev), want_true=ALL)

    def test_push_with_an_unreadable_range_runs_everything(self):
        self.assertFlags(run(["README.md"], event="push", before="e" * 40), want_true=ALL)

    # Map gaps found in review: each path is read by a suite in another job.
    def test_merge_tool_change_turns_on_the_suites_that_load_it(self):
        self.assertFlags(run(["merge/merge.py"]), want_true=["gates_windows", "gates_macos", "guard", "gates_windows_merge"])

    def test_record_slug_checker_change_turns_on_the_guard_suites(self):
        self.assertFlags(run(["lint/check_record_slugs.py"]), want_true=["gates_windows", "gates_macos", "guard", "code"])

    def test_janitor_launcher_change_turns_on_the_install_suite(self):
        self.assertFlags(run(["bin/claude-janitor"]), want_true=["gates_windows", "shell_macos"])

    def test_silent_undo_checker_change_turns_on_the_merge_job(self):
        self.assertFlags(run(["lint/check_silent_undo.py"]), want_true=["gates_windows_merge"])

    def test_session_start_change_turns_on_the_unknown_read_contract_job(self):
        self.assertFlags(run(["hooks/session_start.sh"]), want_true=["gates_windows_rest"])

    def test_a_new_file_in_a_landed_dir_turns_on_the_install_suite(self):
        for p in ("agents/new.md", "skills/new/SKILL.md", "output-styles/new.md", "lint/new.py"):
            self.assertFlags(run([p]), want_true=["gates_windows", "shell_macos"])

    def test_a_modified_md_under_skills_turns_on_nothing(self):
        self.assertFlags(run(["skills/old/SKILL.md"], existing=["skills/old/SKILL.md"]), want_false=ALL)

    def test_a_new_file_in_hooks_or_janitor_turns_on_the_install_suite(self):
        for p in ("hooks/new.py", "janitor/new.py"):
            self.assertFlags(run([p]), want_true=["gates_windows", "shell_macos"])

    def test_the_landed_dirs_come_from_landed_dirs_txt(self):
        # A made-up dir in the scratch repo's landed-dirs.txt: the script reads the file, it does not copy the list.
        self.assertFlags(run(["zz-made-up/new.md"], landed=["zz-made-up"]), want_true=["gates_windows", "shell_macos"])

    def test_an_empty_or_comment_only_landed_list_turns_everything_on(self):
        for landed in ([], ["# only a comment", ""]):
            self.assertFlags(run(["docs/new.md"], landed=landed), want_true=ALL)

    def test_a_trailing_slash_in_landed_dirs_is_read_as_the_dir(self):
        self.assertFlags(run(["zz-made-up/new.md"], landed=["zz-made-up/"]), want_true=["gates_windows", "shell_macos"])

    # Cut F: gates-windows-guard and gates-mutate-guard skip on the `guard` flag. The slice selector
    # (GUARD_TESTS) is read from hooks/test_guard.py, so an edit to that file must turn `guard` on,
    # or a pull request that changes the slice would run no guard job at all.
    def test_the_guard_selector_and_its_harness_turn_the_guard_flag_on(self):
        for p in ("hooks/test_guard.py", "hooks/mutate_guard.py", "hooks/guard.py"):
            self.assertFlags(run([p]), want_true=["guard"])

    # Review finding on #305: the guard suite reads these two paths, but the rules did not set `guard`,
    # so after cut F a pull request touching them ran the guard suite in no job (false green).
    def test_a_new_file_under_a_landed_dir_turns_on_the_guard_suite(self):
        self.assertFlags(run(["lint/zz_new.py"]), want_true=["guard"])

    def test_the_janitor_launcher_turns_on_the_guard_suite(self):
        self.assertFlags(run(["bin/claude-janitor"]), want_true=["guard"])

    # Control: a docs-only path must keep `guard` off, or the new rules over-trigger (false red).
    def test_a_docs_only_path_keeps_the_guard_flag_off(self):
        for p in ("README.md", "decisions/some-record.md"):
            self.assertFlags(run([p]), want_false=["guard"])

    # Round 2 hole: lint/guard_log_report.py imports hooks/guard_core.py at load, and decision_watch
    # reads guard.log through it at run time. So a change to it must select the same jobs as
    # lint/_transcript.py, the other module the decision watch loads (the rules at its line 36, 51).
    def test_guard_log_reader_change_selects_the_jobs_of_the_transcript_reader(self):
        reader = self.true_set(run(["lint/guard_log_report.py"]))
        self.assertEqual(reader, self.true_set(run(["lint/_transcript.py"])))
        self.assertTrue({"gates_windows_rest", "gates_macos", "code", "guard"} <= reader, reader)

    # Guard family: hooks/guard_<anything>.py is split out of hooks/guard.py. Each sibling must set
    # exactly the flags guard.py sets, as a new file and as an edit. Today the generic hooks/* rule
    # gives a new sibling no sweep flag, and an edited one no Windows or shell job.
    GUARD_SIBLINGS = ["hooks/guard_core.py", "hooks/guard_merge.py", "hooks/guard_rules.py"]

    def true_set(self, got):
        return {n for n in ALL if got[n] == "true"}

    def test_guard_sibling_new_file_sets_the_same_flags_as_guard_py(self):
        want = run(["hooks/guard.py"])
        self.assertFlags(want, want_true=["gates_windows", "gates_windows_rest", "gates_macos", "code", "guard", "sweep"],
                         want_false=["gates_windows_merge", "pointer_windows"])
        for p in self.GUARD_SIBLINGS:
            with self.subTest(path=p):
                self.assertEqual(run([p]), want)

    def test_guard_sibling_edit_sets_the_same_flags_as_guard_py(self):
        want = run(["hooks/guard.py"], existing=["hooks/guard.py"])
        self.assertFlags(want, want_true=["gates_windows", "gates_windows_rest", "gates_macos", "code", "guard", "sweep"],
                         want_false=["gates_windows_merge", "shell_macos", "pointer_windows"])
        for p in self.GUARD_SIBLINGS:
            with self.subTest(path=p):
                self.assertEqual(run([p], existing=[p]), want)

    # Control: the guard test file keeps today's flags. A family rule must not catch it.
    def test_guard_test_file_keeps_its_current_flags(self):
        p = "hooks/guard_test_x.py"
        self.assertEqual(self.true_set(run([p])),
                         {"gates_windows", "gates_windows_rest", "gates_macos", "shell_macos", "code", "guard"})
        self.assertEqual(self.true_set(run([p], existing=[p])), {"gates_windows_rest", "gates_macos", "code", "guard"})

    # Control: the guard selector test keeps today's flags.
    def test_test_guard_keeps_its_current_flags(self):
        p = "hooks/test_guard.py"
        self.assertEqual(self.true_set(run([p])), {"gates_windows", "gates_macos", "shell_macos", "code", "guard"})
        self.assertEqual(self.true_set(run([p], existing=[p])), {"gates_windows", "gates_macos", "code", "guard"})


@unittest.skipUnless(BASH, "bash not on PATH")
class ClaimLintOnly(unittest.TestCase):
    """A synchronize whose new commit is only the merge tool's claim (a Record-claim trailer, *.md only) runs
    lint only, when the newest gates run on BEFORE_SHA for this PR and this base concluded success. Every other
    case keeps the full scope, which for these fixtures is every flag: the PR's own ZZ commit maps to all of them."""

    def assertAll(self, got, want):  # every flag is `want`: "true" (the full scope) or "false" (lint only)
        for n in ALL:
            self.assertEqual(got.get(n), want, f"{n}: {got}")

    def assertFull(self, got):
        self.assertAll(got, "true")

    def test_the_gh_stub_answers_only_for_its_sha(self):  # fixture check, green on today's script: the seam runs here
        with tempfile.TemporaryDirectory() as sd:
            env = dict(os.environ, **stub_gh(sd, "abc123", [gh_run("success", T_NEW)], 0))
            hit = subprocess.run([BASH, "-c", "gh run list --commit abc123 --json conclusion --jq '.[].conclusion'"],
                                 env=env, capture_output=True, text=True)
            api = subprocess.run([BASH, "-c", "gh api 'repos/o/r/actions/workflows/gates.yml/runs?head_sha=abc123'"],
                                 env=env, capture_output=True, text=True)
            miss = subprocess.run([BASH, "-c", "gh api repos/o/r/commits/def456"], env=env, capture_output=True, text=True)
        self.assertEqual((hit.returncode, hit.stdout), (0, "success\n"), hit.stderr)
        self.assertEqual(api.returncode, 0, api.stderr)
        self.assertEqual(json.loads(api.stdout)["workflow_runs"][0]["pull_requests"][0]["number"], int(PR))
        self.assertNotEqual(miss.returncode, 0, miss.stdout)

    def test_a_claim_after_a_green_gates_run_is_lint_only(self):  # green on today's script and on the fix
        got, calls, shas = run_pr(CLAIM_FILES, runs=[gh_run("success", T_NEW)])
        self.assertAll(got, "false")
        self.assertTrue(any(shas["before"] in c for c in calls), calls)  # the verdict is read for BEFORE_SHA

    # Each case below flips one condition only. The rest hold: the newest run on BEFORE_SHA is a success for
    # this PR and this base, so each case would narrow if its own condition were ignored. Green on today's script, by design.
    def test_a_claim_two_commits_behind_the_green_run_keeps_the_full_scope(self):  # parent is not BEFORE_SHA
        got, _, _ = run_pr(CLAIM_FILES, chain=(ZZ, ("decisions/zz-pre.md",)), back=2)
        self.assertFull(got)

    def test_a_claim_without_the_trailer_keeps_the_full_scope(self):
        got, _, _ = run_pr(CLAIM_FILES, msg=("Claim record numbers",))
        self.assertFull(got)

    def test_a_claim_that_also_touches_a_py_file_keeps_the_full_scope(self):
        got, _, _ = run_pr(CLAIM_FILES + ("lint/zz_claim.py",))
        self.assertFull(got)

    def test_a_claim_on_opened_keeps_the_full_scope(self):
        got, _, _ = run_pr(CLAIM_FILES, action="opened")
        self.assertFull(got)

    def test_a_claim_on_ready_for_review_keeps_the_full_scope(self):
        got, _, _ = run_pr(CLAIM_FILES, action="ready_for_review")
        self.assertFull(got)

    def test_a_prior_run_that_did_not_conclude_success_keeps_the_full_scope(self):
        for verdict in ("failure", "cancelled", "skipped", None):  # a draft's run skips (incident 2026-10-12); None: not concluded
            with self.subTest(verdict=verdict):
                got, _, _ = run_pr(CLAIM_FILES, runs=[gh_run(verdict, T_NEW)])
                self.assertFull(got)
        with self.subTest(verdict="no run"):
            got, _, _ = run_pr(CLAIM_FILES, runs=[])
            self.assertFull(got)

    def test_an_unreadable_prior_run_keeps_the_full_scope(self):
        for runs, code in (([gh_run("success", T_NEW)], 1), ([], 1)):  # a non-zero exit is unreadable, whatever it printed
            with self.subTest(runs=len(runs), code=code):
                got, _, _ = run_pr(CLAIM_FILES, runs=runs, code=code)
                self.assertFull(got)

    # Review round 1, mixed runs: the script reads the NEWEST run on BEFORE_SHA. An older success does not count.
    # Both list orders: GitHub lists newest first, but the script must pick by created_at, not by position.
    def test_an_older_success_does_not_outrank_a_newer_failure(self):  # red on c4d6809: it greps any success
        newer_fail, older_ok = gh_run("failure", T_NEW), gh_run("success", T_OLD)
        for label, runs in (("newest first", [newer_fail, older_ok]), ("oldest first", [older_ok, newer_fail])):
            with self.subTest(order=label):
                got, _, _ = run_pr(CLAIM_FILES, runs=runs)
                self.assertFull(got)

    # Review round 1, stale base: a green run against another base does not vouch for this PR's base.
    def test_a_newest_success_against_another_base_keeps_the_full_scope(self):  # red on c4d6809
        got, _, _ = run_pr(CLAIM_FILES, runs=[gh_run("success", T_NEW, base=STALE_BASE)])
        self.assertFull(got)

    # Review round 1, foreign PR: a green run of another pull request on the same sha does not vouch for this one.
    def test_a_newest_success_of_another_pr_keeps_the_full_scope(self):  # red on c4d6809
        got, _, _ = run_pr(CLAIM_FILES, runs=[gh_run("success", T_NEW, pr="99")])
        self.assertFull(got)

    # Green control: the newest run is a success for this PR and this base, so an older failure beneath it
    # does not block lint only.
    def test_a_newest_success_for_this_pr_and_base_is_lint_only(self):  # green on c4d6809 and on the fix
        got, calls, shas = run_pr(CLAIM_FILES, runs=[gh_run("success", T_NEW), gh_run("failure", T_OLD)])
        self.assertAll(got, "false")
        self.assertTrue(any(shas["before"] in c for c in calls), calls)  # the verdict is read for BEFORE_SHA


if __name__ == "__main__":
    unittest.main()
