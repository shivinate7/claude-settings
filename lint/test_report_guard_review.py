#!/usr/bin/env python3
"""Cases for the review-record check of the Stop hook, lint/report_guard.py (part 2 of the coordinator design).

A lane's reply that claims a reviewer PASS for a pull request is refused unless that pull request has a
review record for its live head. Choices pinned here:
- The claim: a line of the reply, outside fenced blocks, with `round <N>` or `reviewer` (either case) and the
  word PASS or PASSED in capitals, in either order. A PASS in an inline code span counts. A test's "verdict PASS"
  is no claim. A PASS that a negation governs ("not PASS", "did not PASS") is no claim.
- A history line is no claim: a PASS its clause places in the past, as stale or before a change ("was before the
  fix", "went stale after the push"). Clauses split on `,`, `;` and `--`, and the clause that holds the PASS decides,
  so a history word in another clause does not hide a claim (a current PASS followed by ", superseding the stale FAIL").
- The pull requests: each PR number on a claim line, as `#<n>`, `PR <n>`, a backticked `#<n>`, or a github pull URL,
  on the line. Each one is checked. A claim line with no PR is refused, and the reason asks for one.
- The record: the newest comment whose first line is the review marker, read by merge/merge.py parse_review, that
  names the pull request (PR: #N) and the live head, and that merge/merge.py review_state calls done for that head.
  The newest record decides. The check takes merge's verdict, never a PASS word of its own. A newest record that does
  not parse is refused with wording that says so, never with the no-record wording. It names the CI line as the cause
  only when text follows the CI line; the parser stays strict. The remedy re-posts through `merge <n> --review-record`.
- The reads: the live head (pulls/<n>) and the comments (issues/<n>/comments), two REST reads per PR, made only for
  such a claim in a lane. A failed read (an exit, or an answer that is not JSON), or an exception in the check, never
  blocks: the reply gets a systemMessage with UNKNOWN, never "clear". The budget is the exception, see below. The cutover
  read is one such read, but it never hides the record check: when the pull and its comments were read and hold no record
  for the live head, the claim is still refused.
- The budget (decision `pr-review-record`): every gh read and the cutover read of one Stop share REVIEW_HOOK_BUDGET. A gh
  read gets what is left, never more than REVIEW_READ_TIMEOUT. A read that starts with nothing left is not started. When the
  budget runs out before a claim's record is read, or before the cutover read its record check needs, the claim is refused
  with the run-again cause. It is never let through on an UNKNOWN note alone.
- The remedy names `merge <n> --review-record` and never the live head sha: a record must name the head the
  reviewer read, and the refusal cannot know which head that was.
- The installed layout: the script is a symlink in the config folder, with no merge/ beside lint/. The check still
  finds merge/merge.py, and a claim with no record still blocks. The copied layout (cloud) is the same, with regular
  files: the check finds merge/merge.py through the checkout the global rules file names.

A lane is a session whose own get_session record is tagged cs-build:lane or names a parent. A session with no
such record is owner-facing, and is never read for this check.

Each case runs the Stop hook as a subprocess. A stand-in `gh` comes first on PATH: it answers the REST reads from
a state file, and logs each call's argv. No live GitHub is reached. The Stop runner, the transcript records and the
run folder are lint/test_report_guard.py's, imported and not copied.

    python3 lint/test_report_guard_review.py -v
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "merge"))
import test_report_guard as trg  # noqa: E402  the Stop runner, transcript records and run folder (one home)
import merge as merge_mod  # noqa: E402  the review record's form and parser (one home, merge/merge.py)
import report_guard as rg  # noqa: E402  the Stop's budget constants (one home, lint/report_guard.py)

LINT_DIR = HERE
HOOKS_DIR = os.path.join(HERE, "..", "hooks")
CALLS = trg.SameTurnWriter()  # builds tool-call records; holds no state
LANE_ENV, LANE_ID, PARENT = "cse_lane1", "session_lane1", "session_parent1"  # remote_session_id maps cse_ to session_
PR = 12
LIVE = "a1b2c3d4" * 5  # the head the stand-in serves for a pull request
OLD = "0f0e0d0c" * 5  # an earlier head, for the stale records
ROUNDS = [(1, "reviewer", "sonnet", "PASS")]
CHATTER = "Looks fine to me."
CLAIM = "OTHER: round 2 PASS on PR #12."
FAILED_READS = (("the pull request read exits 1", {"fail_pulls": "exit"}),
                ("the pull request read answers garbage", {"fail_pulls": "garbage"}),
                ("the comment read exits 1", {"fail_comments": "exit"}),
                ("the comment read answers garbage", {"fail_comments": "garbage"}))
CLAIM_FORMS = ("PASS, round 2 of 3, sonnet on PR 12",
               "PR 12 PASS (round 2)",
               "round 2 PASSED on #12",
               "round 2 PASS at https://github.com/example-owner/example-repo/pull/12")

# The stand-in gh. It serves `pulls/<n>` and `issues/<n>/comments`, optionally under repos/<o>/<r>/, for each PR
# the state names; any other number is a 404. `repos/<o>/<r>` answers the repo's default branch, as gh does.
# A list read pages as gh does: 30 items a page unless per_page says more (at most 100), one page unless --paginate.
# --paginate joins the pages into one array, and --paginate --slurp prints an array of the pages. This follows
# listing() in hooks/test_guard.py, the repo's model of gh. Real gh's bare --paginate output is not measured here.
FAKE_GH = r'''import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "state.json"), encoding="utf-8") as handle:
    state = json.load(handle)
args = sys.argv[1:]
with open(state["count_file"], "a", encoding="utf-8") as handle:
    handle.write(json.dumps(args) + "\n")
if not args or args[0] != "api" or any("graphql" in a.lower() for a in args):
    print("GraphQL is refused in this session: use the REST API with gh api <path>", file=sys.stderr)
    sys.exit(1)
path, fields, flags, i = "", {}, set(), 1
while i < len(args):
    a = args[i]
    if a in ("-X", "--method", "-H", "--header", "-q", "--jq", "--input"):
        i += 2
    elif a in ("-f", "-F", "--field", "--raw-field"):
        key, _, value = args[i + 1].partition("=")
        fields[key] = value
        i += 2
    elif a.startswith("-"):
        flags.add(a)
        i += 1
    else:
        path = a
        i += 1
path, _, query = path.partition("?")
for pair in filter(None, query.split("&")):
    key, _, value = pair.partition("=")
    fields.setdefault(key, value)


def fail(mode):
    if mode == "garbage":
        print("<html>502 Bad Gateway</html>")
        sys.exit(0)
    print("HTTP 500: Server Error", file=sys.stderr)
    sys.exit(1)


def not_found():
    print('{"message": "Not Found"}', file=sys.stderr)
    sys.exit(1)


pull = re.fullmatch(r"(?:repos/[^/]+/[^/]+/)?pulls/(\d+)", path)
issue = re.fullmatch(r"(?:repos/[^/]+/[^/]+/)?issues/(\d+)/comments", path)
if pull:
    if state["fail_pulls"]:
        fail(state["fail_pulls"])
    number = pull.group(1)
    if number not in state["prs"]:
        not_found()
    print(json.dumps({"number": int(number), "state": "open", "draft": False,
                      "head": {"sha": state["prs"][number]["head"], "ref": "feat-" + number},
                      "base": {"ref": state["base"], "repo": {"default_branch": state["default_branch"]}}}))
elif re.fullmatch(r"repos/[^/]+/[^/]+", path):
    print(json.dumps({"default_branch": state["default_branch"]}))
elif issue:
    if state["fail_comments"]:
        fail(state["fail_comments"])
    number = issue.group(1)
    if number not in state["prs"]:
        not_found()
    comments = [{"id": k + 1, "issue_url": "https://api.github.com/repos/example-owner/example-repo/issues/" + number,
                 **(item if isinstance(item, dict) else {"body": item})}
                for k, item in enumerate(state["prs"][number]["comments"])]
    size = min(int(fields.get("per_page", 30)), 100)
    pages = [comments[k:k + size] for k in range(0, len(comments), size)] or [[]]
    if "--slurp" in flags and "--paginate" not in flags:
        print("--slurp requires --paginate", file=sys.stderr)
        sys.exit(1)
    if "--paginate" in flags:
        chosen = pages
    else:
        page = int(fields.get("page", 1))
        chosen = [pages[page - 1] if page <= len(pages) else []]
    if "--slurp" in flags:
        print(json.dumps(chosen))
    elif "--paginate" in flags:
        print(json.dumps([c for p in chosen for c in p]))
    else:
        print(json.dumps(chosen[0]))
else:
    not_found()
'''


def write_fake_gh(folder):
    """The stand-in in `folder`: the script, and the launcher a POSIX shell and a Windows cmd both run."""
    script = os.path.join(folder, "ghfake.py")
    with open(script, "w", encoding="utf-8") as handle:
        handle.write(FAKE_GH)
    posix = os.path.join(folder, "gh")
    with open(posix, "w", encoding="utf-8", newline="\n") as handle:
        handle.write('#!/bin/sh\nexec "%s" "%s" "$@"\n' % (sys.executable, script))
    os.chmod(posix, 0o755)
    with open(os.path.join(folder, "gh.cmd"), "w", encoding="utf-8", newline="") as handle:
        handle.write('@echo off\r\n"%s" "%s" %%*\r\n' % (sys.executable, script))


def report(done, deviations="none"):
    """A report with `done` as its Done item and `deviations` as its Deviations item. The other two items hold nothing a check reads."""
    return "\n".join(["> **Done** " + done, "> **Deviations** " + deviations, "> **Input Needed** none", "> **Next** wait"])


def record(head=LIVE, n=PR, rounds=ROUNDS, fix=None, guard="no", net="not owed"):
    """A review record comment, in merge/merge.py's own form: Kind normal, Guard or check and Net value as given."""
    return merge_mod.review_body(n, head, "normal", guard, rounds, net, fix)


# The incident (pull request 2189, comment 6726184510): a valid record at its live head, with a note line after its CI line.
INCIDENT_PR, INCIDENT_HEAD = 2189, "d35865d42dae16eef06d9cc516c56f904c287fe1"
INCIDENT_ROUNDS = [(1, "reviewer", "haiku", "FAIL"), (2, "reviewer", "sonnet", "PASS"), (3, "reviewer", "sonnet", "PASS")]
INCIDENT_FIX = ("5acce9e26c7520dc8808304f87dfeb6805192300", "reviewer", "sonnet", "PASS")
INCIDENT_NOTE = 'Note, Fix: none, Until: 2026-11-21: the remedy says "copy your edited files aside"; on real git a copy leaves the file in place.'
FOOTER = "\n\n---\n_Generated by [Claude Code](https://claude.ai/code)_\n"  # the footer a GitHub post carries
SPACED_FOOTER = FOOTER.replace("\n---\n", "\n---  \n")  # the same footer, its rule line with two trailing spaces


def incident(note):
    """The incident's comment: the record, then the note line after a blank line when `note`, then the footer."""
    body = record(head=INCIDENT_HEAD, n=INCIDENT_PR, rounds=INCIDENT_ROUNDS, fix=INCIDENT_FIX, guard="yes", net="positive")
    return body.rstrip("\n") + ("\n\n" + INCIDENT_NOTE if note else "") + FOOTER


def unstamped(text):
    """The record with its Stamp line taken out: the shape of a body typed by hand, or of one made before the stamp's merge."""
    return "\n".join(line for line in text.splitlines() if not line.startswith("Stamp: ")) + "\n"


# The cutover history: origin/fixture holds merge/merge.py without the salt line, then with it, at CUTOVER. A record created before
# CUTOVER may carry no Stamp line; one created after it must carry one. Times are fixed, so no case reads the clock.
BEFORE = "2026-10-02T00:00:00Z"   # a comment created before the cutover
AFTER = "2026-11-01T00:00:00Z"    # a comment created after the cutover
CUTOVER = "2026-10-21T15:04:05Z"  # the committer time of the commit that adds the salt line
CUTOVER_GIT_DATE = "2026-10-21 15:04:05 +0000"
PRE_SALT_SOURCE = "def f():\n    return 1\n"
SALT_SOURCE = 'REVIEW_STAMP_SALT = "claude-settings review record stamp v1"\n' + "def f():\n    return 2\n"
POST_SALT_SOURCE = SALT_SOURCE.replace("return 2", "return 3")  # a later commit, which keeps the salt line
MERGE_DIR = os.path.join(HERE, "..", "merge")

# The Stop hook, run as __main__ with a fake clock for its fetches (lint/test_fake_fetch.py). The hook's merge is the one this
# driver imports: the hook's merge_module returns it. Each shared deadline the hook opens is recorded, and when the hook ends the
# clock's total fake time, its fetches and those deadlines go to LOG.
CUTOVER_DRIVER = """import contextlib, json, runpy, sys
sys.path[:0] = [%(hooks)r, %(merge)r, %(lint)r]
import guard_merge
import merge
import test_fake_fetch
clock = test_fake_fetch.FakeFetchClock(step=%(step)r)
spans, real_deadline = [], merge.shared_deadline
@contextlib.contextmanager
def recorded(seconds):
    spans.append(seconds)
    with real_deadline(seconds):
        yield
merge.shared_deadline = recorded
guard_merge.merge_module = lambda: merge
merge.SH_TIMEOUT = guard_merge.MERGE_READ_TIMEOUT
try:
    with clock.patched(merge):
        runpy.run_path(%(guard)r, run_name="__main__")
finally:
    with open(%(log)r, "w", encoding="utf-8") as handle:
        json.dump({"elapsed": clock.now, "fetches": clock.fetches, "spans": spans}, handle)
"""

# The Stop hook, run as __main__ in a process of its own on the fake clock (lint/test_fake_fetch.py). The hook's time.monotonic and its
# child starts read that clock, so each gh call's start and timeout are fake values. The driver's log: the fake seconds elapsed, and each
# gh call's [start, timeout, argv].
BUDGET_DRIVER = """import json, runpy, sys
sys.path[:0] = [%(hooks)r, %(lint)r]
import test_fake_fetch
clock = test_fake_fetch.FakeFetchClock(step=0.0, read_steps=%(read_steps)r)
try:
    with clock.patched_process():
        runpy.run_path(%(guard)r, run_name="__main__")
finally:
    with open(%(log)r, "w", encoding="utf-8") as handle:
        json.dump({"elapsed": clock.now, "reads": clock.reads}, handle)
"""


def setUpModule():
    trg.setUpModule()


def tearDownModule():
    trg.tearDownModule()


class ReviewRecordTests(unittest.TestCase):
    def setUp(self):
        self.run_dir = tempfile.mkdtemp(dir=trg.RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.run_dir, ignore_errors=True)
        self.cfg = os.path.join(self.run_dir, "cfg")
        self.home = os.path.join(self.run_dir, "home")
        self.repo = os.path.join(self.run_dir, "repo")
        self.gh_dir = os.path.join(self.run_dir, "bin")
        self.count = os.path.join(self.run_dir, "gh-calls.jsonl")
        for folder in (self.cfg, self.home, self.gh_dir):
            os.makedirs(folder)
        subprocess.run(["git", "init", "-q", self.repo], check=True, capture_output=True)
        subprocess.run(["git", "-C", self.repo, "remote", "add", "origin",
                        "https://github.com/example-owner/example-repo.git"], check=True, capture_output=True)
        # The default branch the stand-in names: origin/main at an empty commit, with no merge/merge.py, so its cutover is None.
        subprocess.run(["git", "-C", self.repo, "-c", "user.name=fixture", "-c", "user.email=fixture@example.com",
                        "commit", "-q", "--allow-empty", "-m", "fixture"], check=True, capture_output=True)
        subprocess.run(["git", "-C", self.repo, "update-ref", "refs/remotes/origin/main", "HEAD"], check=True, capture_output=True)
        write_fake_gh(self.gh_dir)
        self.assertIsNotNone(shutil.which("gh", path=self.gh_dir), "the stand-in gh is not on its own PATH")
        self.serve()

    def serve(self, comments=(), fail_pulls=None, fail_comments=None, prs=None, base="main", default_branch="main"):
        """The stand-in's answers: each PR's live head and its comments, oldest first, and any read to break. `base` is the branch
        the pull requests name as their base. `default_branch` is the repo's default branch: each pull carries it as
        base.repo.default_branch, and the repo read answers it. `prs` maps a PR number to {"head": sha, "comments": [bodies]}; without
        it, PR 12 has `comments`. A comment is its body, or a dict with body, created_at and updated_at, as the comment list gives them."""
        if prs is None:
            prs = {PR: {"head": LIVE, "comments": list(comments)}}
        state = {"prs": {str(n): {"head": p["head"], "comments": list(p["comments"])} for n, p in prs.items()},
                 "count_file": self.count, "fail_pulls": fail_pulls, "fail_comments": fail_comments,
                 "base": base, "default_branch": default_branch}
        with open(os.path.join(self.gh_dir, "state.json"), "w", encoding="utf-8") as handle:
            json.dump(state, handle)

    def cutover_history(self, base):
        """origin/<base> holds merge/merge.py without the salt line, then the commit that adds it, at CUTOVER. update-ref sets the
        remote-tracking ref, so nothing is pushed. Then merge's review_stamp_since reads this repo's own history."""
        path = os.path.join(self.repo, "merge", "merge.py")
        os.makedirs(os.path.dirname(path))
        for text, date in ((PRE_SALT_SOURCE, "2026-10-20 10:00:00 +0000"), (SALT_SOURCE, CUTOVER_GIT_DATE)):
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
            env = dict(os.environ, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
            subprocess.run(["git", "-C", self.repo, "add", "merge/merge.py"], check=True, capture_output=True)
            subprocess.run(["git", "-C", self.repo, "-c", "user.name=fixture", "-c", "user.email=fixture@example.com",
                            "commit", "-q", "-m", "fixture"], check=True, capture_output=True, env=env)
        subprocess.run(["git", "-C", self.repo, "update-ref", "refs/remotes/origin/" + base, "HEAD"], check=True, capture_output=True)

    def in_process_cutover(self, default):
        """merge's review_stamp_since, run in this process for the default branch `default`. gh is not on this process's PATH, so the
        default branch is the one the stand-in's pulls carry, given by a patch of host_default_branch."""
        with mock.patch.object(merge_mod, "host_default_branch", return_value=default):
            return merge_mod.review_stamp_since(self.repo, default)

    def report_hook_timeout(self):
        """The Stop hook timeout of the report guard, read from settings.json: the one Stop hook whose command runs report_guard.py."""
        with open(os.path.join(HERE, "..", "settings.json"), encoding="utf-8") as handle:
            settings = json.load(handle)
        hooks = [hook for group in settings["hooks"]["Stop"] for hook in group.get("hooks", []) if "report_guard.py" in hook.get("command", "")]
        self.assertEqual(len(hooks), 1, "settings.json names %d Stop hooks for report_guard.py, not one" % len(hooks))
        self.assertIn("timeout", hooks[0], "the report guard's Stop hook sets no timeout")
        return hooks[0]["timeout"]

    def shallow_cutover_clone(self):
        """A depth-2 clone of a source with three commits: the one before the salt, the salt commit (at CUTOVER) and a later one that keeps
        the salt. The salt commit is the clone's shallow boundary, so the cutover read must deepen. The clone's origin/main is the ref the
        report guard reads."""
        src = os.path.join(self.run_dir, "src")
        os.makedirs(os.path.join(src, "merge"))
        subprocess.run(["git", "init", "-q", src], check=True, capture_output=True)
        subprocess.run(["git", "-C", src, "symbolic-ref", "HEAD", "refs/heads/main"], check=True, capture_output=True)
        commits = ((PRE_SALT_SOURCE, "2026-10-20 10:00:00 +0000"), (SALT_SOURCE, CUTOVER_GIT_DATE), (POST_SALT_SOURCE, "2026-10-22 09:00:00 +0000"))
        for text, date in commits:
            with open(os.path.join(src, "merge", "merge.py"), "w", encoding="utf-8") as handle:
                handle.write(text)
            env = dict(os.environ, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
            subprocess.run(["git", "-C", src, "add", "merge/merge.py"], check=True, capture_output=True)
            subprocess.run(["git", "-C", src, "-c", "user.name=fixture", "-c", "user.email=fixture@example.com",
                            "commit", "-q", "-m", "fixture"], check=True, capture_output=True, env=env)
        clone = os.path.join(self.run_dir, "clone")
        subprocess.run(["git", "clone", "-q", "--depth", "2", "file://" + src, clone], check=True, capture_output=True)
        return clone

    def slow_cutover_run(self, step):
        """The Stop hook on a lane's PASS claim, with its cutover read on the shallow clone and each fetch taking `step` s of fake time.
        -> (the hook's printed reply, the driver's log: the fake seconds elapsed, the fetches, and each shared deadline's seconds)."""
        clone = self.shallow_cutover_clone()
        self.serve(comments=[record()])
        log = os.path.join(self.run_dir, "cutover-log.json")
        driver = os.path.join(self.run_dir, "cutover-driver.py")
        with open(driver, "w", encoding="utf-8") as handle:
            handle.write(CUTOVER_DRIVER % {"hooks": os.path.abspath(HOOKS_DIR), "merge": os.path.abspath(MERGE_DIR), "lint": LINT_DIR,
                                           "step": step, "guard": trg.REPORT_GUARD, "log": log})
        out = self.stop(self.lane_turn(report(CLAIM)), script=driver, cwd=clone)
        with open(log, encoding="utf-8") as handle:
            return out, json.load(handle)

    def budget_run(self, prs, read_steps, reply):
        """The Stop hook on a lane's `reply`, for the pull requests `prs` (serve's shape), in a process of its own on the fake clock: each
        gh call takes the fake seconds `read_steps` gives its arguments. -> (the hook's printed reply, the driver's log: the fake seconds
        elapsed, and each gh call's [start, timeout, argv])."""
        self.serve(prs=prs)
        log = os.path.join(self.run_dir, "budget-log.json")
        driver = os.path.join(self.run_dir, "budget-driver.py")
        with open(driver, "w", encoding="utf-8") as handle:
            handle.write(BUDGET_DRIVER % {"hooks": os.path.abspath(HOOKS_DIR), "lint": LINT_DIR, "read_steps": read_steps,
                                          "guard": trg.REPORT_GUARD, "log": log})
        out = self.stop(self.lane_turn(reply), script=driver)
        with open(log, encoding="utf-8") as handle:
            return out, json.load(handle)

    def gh_calls(self):
        """The argv of each stand-in call of the last Stop run."""
        if not os.path.exists(self.count):
            return []
        with open(self.count, encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def install_layout(self, copy=False):
        """The installer's landing: each file of lint/ and hooks/ is a symlink in the config folder, or with copy a
        regular file (the cloud landing, install.sh's copy mode). There is no merge/ beside lint/ either way.
        Returns the script's path in the config folder."""
        for src_dir, dst_dir in ((LINT_DIR, os.path.join(self.cfg, "lint")),
                                 (HOOKS_DIR, os.path.join(self.cfg, "hooks"))):
            os.makedirs(dst_dir)
            for name in os.listdir(src_dir):
                src = os.path.join(src_dir, name)
                if os.path.isfile(src):
                    if copy:
                        shutil.copyfile(src, os.path.join(dst_dir, name))
                    else:
                        os.symlink(src, os.path.join(dst_dir, name))
        return os.path.join(self.cfg, "lint", "report_guard.py")

    def point_rules_at_checkout(self):
        """The global rules file: one `@<path>/CLAUDE.md` line naming this real checkout, with merge/merge.py."""
        clone = os.path.dirname(os.path.realpath(HERE))
        with open(os.path.join(self.cfg, "CLAUDE.md"), "w", encoding="utf-8") as handle:
            handle.write("@%s/CLAUDE.md\n" % clone)

    def assert_record_blocks_claim(self, body):
        """The record is open to merge/merge.py, so a PASS claim on its PR is refused. The fixture is checked first."""
        self.assertEqual(merge_mod.review_state(merge_mod.parse_review(body), LIVE)[0], "open",
                         "fixture: merge/merge.py does not call this record open")
        self.serve(comments=[body])
        out = self.stop(self.lane_turn(report(CLAIM)))
        self.assert_reads_of(PR)
        self.assertIsNotNone(out, "merge calls this record open, but the check let the PASS claim through")
        self.assert_blocked(out)
        self.assertIn("PR #12", out["reason"], out)

    def assert_record_satisfies_claim(self, body):
        """The record is done to merge/merge.py, so a PASS claim on its PR passes on two reads. Fixture checked first."""
        self.assertEqual(merge_mod.review_state(merge_mod.parse_review(body), LIVE)[0], "done",
                         "fixture: merge/merge.py does not call this record done")
        self.serve(comments=[body])
        out = self.stop(self.lane_turn(report(CLAIM)))
        self.assert_two_rest_reads()
        self.assertIsNone(out, out)

    def stop(self, records, env_id=True, script=None, block=(), cwd=None):
        """Run the Stop hook on `records`. env_id is this session's remote id (a lane sets it). The stand-in
        comes first on PATH, and the call log is emptied first, so each run's calls are its own. `script` runs
        another copy of the hook, and `block` names modules the run cannot import. `cwd` is the hook's folder, the repo root when None."""
        open(self.count, "w", encoding="utf-8").close()
        path = trg.write_transcript(records, self.run_dir)
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": False, "cwd": cwd or self.repo}
        env = dict(os.environ, CLAUDE_CONFIG_DIR=self.cfg, HOME=self.home,
                   PATH=self.gh_dir + os.pathsep + os.environ.get("PATH", ""))
        env.pop("CLAUDE_CODE_REMOTE_SESSION_ID", None)
        if env_id:
            env["CLAUDE_CODE_REMOTE_SESSION_ID"] = LANE_ENV
        run = trg.run_guard(script or trg.REPORT_GUARD, hook, env=env, block=block)
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads(run.stdout) if run.stdout.strip() else None

    def lane_record(self, tags=("cs-build:lane",), parent=None):
        """This session's own get_session record. A lane tag or a parent id marks a lane."""
        ccr = {"id": LANE_ID, "tags": list(tags), "parent_session_id": parent}
        return CALLS.call("mcp__claude-code-remote__get_session", {"session_id": LANE_ID},
                          result=json.dumps({"ccr": ccr}))

    def lane_turn(self, reply, tags=("cs-build:lane",), parent=None, landed=False):
        """One lane turn: its own record, the peer message that starts it, and the reply. A landed turn has a
        human message and a git commit before the reply."""
        own = self.lane_record(tags, parent)
        if landed:
            return [*own, trg.human("do the task"), trg.tool_use_msg("Bash", {"command": "git commit -m x"}),
                    trg.tool_result_msg(), trg.assistant_text(reply)]
        return [*own, trg.peer_msg("do the task", from_session=PARENT), trg.assistant_text(reply)]

    def assert_blocked(self, out, msg=""):
        prefix = msg + " " if msg else ""
        self.assertIsNotNone(out, prefix + "the reply passed; expected a block")
        self.assertEqual(out.get("decision"), "block", prefix + str(out))
        self.assertTrue(out.get("reason"), prefix + str(out))

    def assert_reads_of(self, *numbers):
        """Exactly two REST reads for each PR in `numbers`, its live head and its comments, and no other read."""
        calls = self.gh_calls()
        self.assertEqual(len(calls), 2 * len(numbers), "reads of PRs %r expected, got %r" % (numbers, calls))
        for argv in calls:
            self.assertEqual(argv[0], "api", argv)
            self.assertFalse(any("graphql" in a.lower() for a in argv), argv)
        for n in numbers:
            self.assertTrue(any(a.endswith("pulls/%d" % n) for argv in calls for a in argv), (n, calls))
            self.assertTrue(any(a.endswith("issues/%d/comments" % n) for argv in calls for a in argv), (n, calls))

    def assert_reads_include(self, n):
        """Both REST reads of PR `n` appear among the calls. Other PRs' reads may appear too."""
        calls = self.gh_calls()
        self.assertTrue(any(a.endswith("pulls/%d" % n) for argv in calls for a in argv), "PR %d head not read: %r" % (n, calls))
        self.assertTrue(any(a.endswith("issues/%d/comments" % n) for argv in calls for a in argv),
                        "PR %d comments not read: %r" % (n, calls))

    def assert_two_rest_reads(self):
        self.assert_reads_of(PR)

    def assert_unparsed_remedy(self, reason, n):
        """The remedy of an unparsed record names the merge act for PR `n` and a post through it, and never a record written by hand."""
        self.assertIn("merge %d --review-record" % n, reason, "the remedy does not name `merge %d --review-record`: %r" % (n, reason))
        self.assertRegex(reason, r"(?i)\bpost", "the remedy does not say to post the record through that act: %r" % reason)
        self.assertNotRegex(reason, r"(?i)by hand|hand-writ|write the record",
                            "the remedy tells the lane to write the record by hand: %r" % reason)

    # Refused: a lane's claim with no record for its live head.

    def test_lane_round_pass_without_a_record_blocks(self):
        # Catches: a lane's round PASS sent by message, with no review record on its PR.
        self.assert_blocked(self.stop(self.lane_turn(report(CLAIM))))

    def test_lane_reviewer_pass_without_a_record_blocks(self):
        # Catches: the second claim shape, "reviewer ... PASS" on a Done line, not read as a review claim.
        self.assert_blocked(self.stop(self.lane_turn(report("OTHER: reviewer PASS on PR #12."))))

    def test_lane_round_pass_with_a_stale_record_blocks(self):
        # Catches: a record for an earlier head read as this head's record.
        self.serve(comments=[record(head=OLD)])
        self.assert_blocked(self.stop(self.lane_turn(report(CLAIM))))

    def test_lane_round_pass_with_a_record_naming_another_pr_blocks(self):
        # Catches: a record whose PR line names another pull request read as this pull request's record.
        self.serve(comments=[record(n=PR + 1)])
        self.assert_blocked(self.stop(self.lane_turn(report(CLAIM))))

    def test_newest_record_decides_so_a_stale_record_after_the_live_one_blocks(self):
        # Catches: an older record for the live head passing while the newest record, the one merge --reviewed
        # reads, is for an earlier head.
        self.serve(comments=[record(), record(head=OLD)])
        self.assert_blocked(self.stop(self.lane_turn(report(CLAIM))))

    def test_marker_line_with_trailing_spaces_is_a_record_as_merge_reads_it(self):
        # Catches: _newest_record's raw first-line test, which reads a record whose marker line has trailing spaces as no
        # record, so a lane's PASS claim on a PR that merge --reviewed reads as done is refused. merge's review_marked and
        # parse_review both strip a line's trailing whitespace.
        body = record().replace(merge_mod.REVIEW_MARKER + "\n", merge_mod.REVIEW_MARKER + "  \n", 1)
        self.assertTrue(merge_mod.review_marked(body), "fixture: merge does not read the marker line with trailing spaces as the marker")
        self.assert_record_satisfies_claim(body)

    def test_a_subfolder_cwd_reads_the_same_cutover_as_the_repo_root(self):
        # Catches: the cutover read run from a subfolder of the checkout, `git -C <subfolder>` reading merge/merge.py as a path under the
        # subfolder. The cutover is then none, and an unstamped record from before the cutover refuses. The control is the case below,
        # run from the root: the same record passes there, so the subfolder run is the one that differs.
        self.cutover_history("fixture")
        self.assertEqual(self.in_process_cutover("fixture"), CUTOVER,
                         "fixture: the cutover from the root is not the time of the commit that adds the salt line")
        body = unstamped(record())
        self.serve(comments=[{"body": body, "created_at": BEFORE}], base="fixture", default_branch="fixture")
        out = self.stop(self.lane_turn(report(CLAIM)), cwd=os.path.join(self.repo, "merge"))
        self.assert_reads_of(PR)
        self.assertIsNone(out, "a run from a subfolder refused an unstamped record from before the cutover:\n" + str(out))

    def test_an_unstamped_done_record_created_before_the_cutover_satisfies_a_pass_claim(self):
        # Catches: a record made before the stamp's merge, with no Stamp line, read as no record, so a lane's PASS claim on its
        # pull request is refused. merge --reviewed reads the same record as done.
        self.cutover_history("fixture")
        self.assertEqual(self.in_process_cutover("fixture"), CUTOVER,
                         "fixture: the cutover is not the time of the commit that adds the salt line")
        body = unstamped(record())
        self.assertEqual(merge_mod.review_state(merge_mod.parse_review(body, BEFORE, CUTOVER), LIVE)[0], "done",
                         "fixture: merge/merge.py does not call this record done")
        self.serve(comments=[{"body": body, "created_at": BEFORE}], base="fixture", default_branch="fixture")
        out = self.stop(self.lane_turn(report(CLAIM)))
        self.assert_reads_of(PR)
        self.assertIsNone(out, out)

    def test_an_unstamped_record_created_after_the_cutover_refuses_a_pass_claim(self):
        # Catches: the cutover letting a record made after the stamp's merge through with no Stamp line.
        self.cutover_history("fixture")
        self.serve(comments=[{"body": unstamped(record()), "created_at": AFTER}], base="fixture", default_branch="fixture")
        self.assert_blocked(self.stop(self.lane_turn(report(CLAIM))))

    def test_an_unstamped_record_created_before_and_edited_after_the_cutover_refuses_a_pass_claim(self):
        # Catches: a record created before the cutover and edited after it, with no Stamp line, read as made before the cutover.
        self.cutover_history("fixture")
        self.serve(comments=[{"body": unstamped(record()), "created_at": BEFORE, "updated_at": AFTER}], base="fixture",
                   default_branch="fixture")
        self.assert_blocked(self.stop(self.lane_turn(report(CLAIM))))

    def test_record_whose_rounds_hold_no_pass_does_not_satisfy_a_pass_claim(self):
        # Catches: a record for the live head read as satisfying a PASS claim when none of its rounds passed.
        for verdict in ("FAIL", "PARTIAL"):
            with self.subTest(verdict):
                body = merge_mod.review_body(PR, LIVE, "normal", "no", [(1, "reviewer", "sonnet", verdict)], "not owed")
                self.serve(comments=[body])
                out = self.stop(self.lane_turn(report(CLAIM)))
                self.assert_reads_of(PR)
                self.assert_blocked(out)
                self.assertIn("PR #12", out["reason"], out)

    def test_reviewer_fail_beside_a_design_pass_in_one_round_blocks(self):
        # Catches: a record read as passed because one line of the first round says PASS. merge reads the whole round, so
        # the reviewer's FAIL keeps that round open, whatever the design reviewer wrote in the same round.
        self.assert_record_blocks_claim(record(rounds=[(1, "reviewer", "sonnet", "FAIL"),
                                                       (1, "design-reviewer", "sonnet", "PASS")]))

    def test_round_passed_then_failed_in_a_later_round_blocks(self):
        # Catches: a PASS in an earlier round passing the record, though the last round failed.
        self.assert_record_blocks_claim(record(rounds=[(1, "reviewer", "sonnet", "PASS"),
                                                       (2, "reviewer", "sonnet", "FAIL")]))

    def test_fix_pass_with_no_round_blocks(self):
        # Catches: a fix check PASS passing a record with no round recorded. The fix re-reviews a round, so it needs
        # one. The fix names an earlier head, so its diff is not empty.
        self.assert_record_blocks_claim(record(rounds=[], fix=(OLD, "reviewer", "sonnet", "PASS")))

    def test_lane_pass_naming_no_pr_blocks_and_asks_for_the_pr(self):
        # Catches: a claim with no pull request on its line passing, or refused without asking for one. The live
        # record is on the comments, so only the missing PR can block here.
        self.serve(comments=[record()])
        out = self.stop(self.lane_turn(report("OTHER: round 2 PASS on commit 1234abc.")))
        self.assert_blocked(out)
        self.assertRegex(out["reason"], r"(?i)\bPR\b|pull request", out)
        self.assertNotRegex(out["reason"], r"merge \d+ --review-record", out)  # no number nobody gave

    def test_lane_pass_with_a_lone_apostrophe_still_blocks(self):
        # Catches: a quote scanner that reads the text between two apostrophes as quoted, and so hides the claim.
        self.assert_blocked(self.stop(self.lane_turn(
            report("OTHER: don't merge yet; round 2 PASS on PR #12. Won't re-run it."))))

    def test_lane_pass_blocks_under_either_lane_mark(self):
        # Catches: a lane recognised by its tag only, or by its parent only.
        for label, marks in (("tag only", {"tags": ("cs-build:lane",), "parent": None}),
                             ("parent only", {"tags": (), "parent": PARENT})):
            with self.subTest(label):
                self.assert_blocked(self.stop(self.lane_turn(report(CLAIM), **marks)))

    def test_landed_lane_pass_without_a_record_blocks(self):
        # Catches: the check run on unlanded turns only, so a commit in the turn lets the claim through.
        self.assert_blocked(self.stop(self.lane_turn(report(CLAIM), landed=True)))

    def test_remedy_names_the_record_act_and_never_the_live_head(self):
        # Catches: a remedy that names no act, or that prints the live head sha for a record the reviewer never made.
        out = self.stop(self.lane_turn(report(CLAIM)))
        self.assert_blocked(out)
        self.assertIn("merge 12 --review-record", out["reason"], out)
        self.assertNotIn(LIVE, out["reason"], out)
        self.assertNotIn(LIVE[:7], out["reason"], out)

    def test_unstamped_record_with_no_cutover_is_refused_and_the_remedy_names_the_stamp_line(self):
        # Catches: the refusal of an unstamped record in a repo with no cutover, whose text names no Stamp line, so the
        # reviewer is not told what the record lacks. The render command stays in the remedy.
        self.assertIsNone(self.in_process_cutover("main"), "fixture: a cutover is set for main")
        body = unstamped(record())
        self.assertIsNone(merge_mod.parse_review(body, None, None), "fixture: merge reads the unstamped record with no cutover")
        self.serve(comments=[body])
        out = self.stop(self.lane_turn(report(CLAIM)))
        self.assert_blocked(out)
        self.assertIn("merge 12 --review-record", out["reason"], out)
        self.assertIn("Stamp", out["reason"], "the refusal names no Stamp line for a record that has none:\n" + out["reason"])

    def test_full_size_comment_list_without_a_record_blocks(self):
        # Full size: 101 comments, none a record. The check reads them all, then blocks.
        self.serve(comments=[CHATTER] * 101)
        self.assert_blocked(self.stop(self.lane_turn(report(CLAIM))))

    def test_claim_forms_that_count_block_without_a_record(self):
        # Catches: a claim form read as no claim, or its PR missed: PR before PASS, PR without #, PASSED, and a PR
        # named by URL. Each form reads PR 12 and blocks.
        for form in CLAIM_FORMS:
            with self.subTest(form):
                self.serve()
                out = self.stop(self.lane_turn(report("OTHER: " + form + ".")))
                self.assert_reads_of(PR)
                self.assert_blocked(out)

    def test_pass_in_a_code_span_is_a_claim(self):
        # Catches: a PASS inside an inline code span read as no claim, which hides the claim from the check.
        self.serve()
        out = self.stop(self.lane_turn(report("OTHER: round 2 `PASS` on #12.")))
        self.assert_reads_of(PR)
        self.assert_blocked(out)

    def test_pr_number_in_a_code_span_counts(self):
        # Catches: a #N inside an inline code span not taken as the claim's PR, so the claim names no pull request.
        self.serve()
        out = self.stop(self.lane_turn(report("OTHER: round 2 PASS on `#12`.")))
        self.assert_reads_of(PR)
        self.assert_blocked(out)

    def test_every_pr_on_a_claim_line_is_checked(self):
        # Catches: only the first PR of a claim line checked, so a second PR's record is never read.
        with self.subTest("two claims on one line"):
            self.serve(prs={12: {"head": LIVE, "comments": [record(n=12)]}, 13: {"head": LIVE, "comments": []}})
            out = self.stop(self.lane_turn(report("OTHER: round 1 PASS on #12, round 1 PASS on #13.")))
            self.assert_reads_of(12, 13)
            self.assert_blocked(out)
            self.assertIn("PR #13", out["reason"], out)
            self.assertNotIn("PR #12", out["reason"], out)
        with self.subTest("a number before the claim's PR"):
            self.serve(prs={12: {"head": LIVE, "comments": []}})
            out = self.stop(self.lane_turn(report("OTHER: #7 is the issue; round 2 PASS on #12.")))
            self.assert_reads_include(12)
            self.assert_blocked(out)
            self.assertIn("PR #12", out["reason"], out)

    def test_installed_layout_pass_claim_without_a_record_blocks(self):
        # Catches: the review check finding merge/ only beside the script's own folder. Installed, lint/ is symlinked
        # into the config folder with no merge/ beside it, so the import fails and the claim reads UNKNOWN.
        script = self.install_layout()
        out = self.stop(self.lane_turn(report(CLAIM)), script=script)
        self.assert_blocked(out)
        self.assert_reads_of(PR)
        self.assertIn("PR #12", out["reason"], out)

    def test_copied_layout_pass_claim_without_a_record_blocks(self):
        # Catches: the review check finding merge/ only beside the script's own folder. Copied in (cloud), lint/ and
        # hooks/ are regular files with no merge/ beside lint/, so `import merge` fails and the claim reads UNKNOWN.
        # The global rules file names this checkout, whose merge/merge.py the check can load.
        script = self.install_layout(copy=True)
        self.point_rules_at_checkout()
        self.assertFalse(os.path.islink(script), "the copied script is a symlink, so this is not the copy layout")
        self.assertFalse(os.path.exists(os.path.join(self.cfg, "merge")), "a merge/ beside lint/ hides the copy layout")
        self.assertTrue(os.path.isfile(os.path.join(os.path.dirname(os.path.realpath(HERE)), "merge", "merge.py")),
                        "fixture: the rules file names a checkout with no merge/merge.py")
        self.serve()
        out = self.stop(self.lane_turn(report(CLAIM)), script=script)
        self.assertNotIn("UNKNOWN", (out or {}).get("systemMessage", ""),
                         "copied layout: the check read UNKNOWN, because merge/merge.py was not found beside lint/")
        self.assert_reads_of(PR)
        self.assert_blocked(out)
        self.assertIn("PR #12", out["reason"], out)

    def test_copied_layout_with_no_rules_pointer_reads_unknown_not_a_block(self):
        # Control: copied in with no merge/ and no rules pointer, the check cannot load the merge tool, so the claim
        # reads UNKNOWN, never a block. A fix must not turn that unread into a block.
        script = self.install_layout(copy=True)
        self.assertFalse(os.path.exists(os.path.join(self.cfg, "CLAUDE.md")), "fixture: a rules pointer is present")
        self.serve()
        out = self.stop(self.lane_turn(report(CLAIM)), script=script)
        self.assertNotEqual((out or {}).get("decision"), "block", out)
        self.assertIn("UNKNOWN", (out or {}).get("systemMessage", ""), out)

    def test_exception_in_the_lane_check_emits_unknown_not_silence(self):
        # Catches: an exception in the lane check, from the override import or the own-lane read, ending the check
        # with no word. The claim is not blocked, and the reply says the check read unknown.
        for label, module in (("override import", "override"), ("own-lane read", "own_session")):
            with self.subTest(label):
                self.serve()
                out = self.stop(self.lane_turn(report(CLAIM)), block=(module,))
                self.assertNotEqual((out or {}).get("decision"), "block", out)
                self.assertIn("Review-record guard: UNKNOWN", (out or {}).get("systemMessage", ""), out)

    def test_newest_record_that_does_not_parse_is_named_unparsed_not_missing(self):
        # Catches: a newest record that does not parse (a note line after its CI line) refused with the no-record wording,
        # which says no record exists for the live head when one does. The refusal stays; its words name the parse failure.
        with_note = incident(note=True)
        self.assertIsNone(merge_mod.parse_review(with_note), "fixture: the note text parses, so it is not the incident's record")
        self.serve(prs={INCIDENT_PR: {"head": INCIDENT_HEAD, "comments": [with_note]}})
        out = self.stop(self.lane_turn(report("OTHER: round 3 PASS on PR #2189.")))
        self.assert_reads_of(INCIDENT_PR)
        self.assert_blocked(out)
        reason = out["reason"]
        self.assertIn("PR #2189", reason, "the refusal does not name PR #2189: %r" % reason)
        self.assertRegex(reason, r"(?i)does not parse", "the refusal does not say the newest record does not parse: %r" % reason)
        self.assertRegex(reason, r"(?i)CI line", "the refusal does not name the CI line as the cause: %r" % reason)
        self.assertNotIn("has no review record for its live head", reason,
                         "the refusal says no record exists, though the newest record exists: %r" % reason)
        self.assert_unparsed_remedy(reason, INCIDENT_PR)

    def test_newest_record_with_a_bad_kind_is_unparsed_with_no_ci_line_cause(self):
        # Catches: a record that fails on a bad Kind line named as a CI-line failure, which sends the lane to fix a line that
        # is not the cause; or named as no record, which hides that the newest record exists. The refusal says it does not parse.
        bad_kind = merge_mod.review_body(PR, LIVE, "weird", "no", ROUNDS, "not owed")
        self.assertIsNone(merge_mod.parse_review(bad_kind), "fixture: the bad-Kind record parses, so it is not unparsed")
        self.serve(comments=[bad_kind])
        out = self.stop(self.lane_turn(report(CLAIM)))
        self.assert_reads_of(PR)
        self.assert_blocked(out)
        reason = out["reason"]
        self.assertIn("PR #12", reason, "the refusal does not name PR #12: %r" % reason)
        self.assertRegex(reason, r"(?i)does not parse", "the refusal does not say the newest record does not parse: %r" % reason)
        self.assertNotRegex(reason, r"(?i)CI line", "the refusal names the CI line as the cause of a bad Kind line: %r" % reason)
        self.assertNotIn("has no review record for its live head", reason,
                         "the refusal says no record exists, though the newest record exists: %r" % reason)
        self.assert_unparsed_remedy(reason, PR)

    # Unparsed records: the cause named for a record that does not parse (decision pr-review-record). The CI-line cause is
    # named for text after the CI line. A record with no Stamp line and no cutover names the Stamp cause, and that cause wins.

    def test_footer_with_trailing_spaces_is_not_text_after_the_ci_line(self):
        # Catches: a footer rule line `---` with trailing spaces read as text after the CI line, so a bad Kind line is named
        # with the CI-line cause. merge reads that line as the record's end, as it reads a plain `---`.
        body = merge_mod.review_body(PR, LIVE, "weird", "no", ROUNDS, "not owed") + SPACED_FOOTER
        self.assertIn("\n---  \n", body, "fixture: the footer's rule line has no trailing spaces")
        self.assertIsNone(merge_mod.parse_review(body), "fixture: the bad-Kind record parses, so it is not unparsed")
        self.serve(comments=[body])
        out = self.stop(self.lane_turn(report(CLAIM)))
        self.assert_reads_of(PR)
        self.assert_blocked(out)
        self.assertNotIn("the CI line must be the last line", out["reason"],
                         "the refusal names the CI line as the cause, though only the footer follows it: %r" % out["reason"])

    def test_valid_record_with_a_footer_of_trailing_spaces_still_passes(self):
        # Control: the same footer on a record that parses. merge reads the footer as the record's end, so the claim passes.
        self.assert_record_satisfies_claim(record() + SPACED_FOOTER)

    def test_ci_line_with_trailing_spaces_before_a_note_is_found_as_the_ci_line(self):
        # Catches: a CI line with trailing spaces not matched as the CI line, so the note after it is not named as the cause.
        # merge reads that CI line as the record's CI line, since parse_review strips each line; the note is the one fault.
        body = record().replace(merge_mod.REVIEW_CI_LINE + "\n", merge_mod.REVIEW_CI_LINE + "   \n", 1) + "\n" + INCIDENT_NOTE + "\n"
        self.assertIsNone(merge_mod.parse_review(body), "fixture: merge reads the note after the CI line as part of the record")
        self.serve(comments=[body])
        out = self.stop(self.lane_turn(report(CLAIM)))
        self.assert_reads_of(PR)
        self.assert_blocked(out)
        self.assertIn("the CI line must be the last line", out["reason"],
                      "the refusal does not name the CI line as the cause of text after it: %r" % out["reason"])

    def test_ci_line_with_trailing_spaces_and_nothing_after_it_passes(self):
        # Control: the same CI line with nothing after it. merge reads the record as the CI line, so the claim passes.
        self.assert_record_satisfies_claim(record().replace(merge_mod.REVIEW_CI_LINE + "\n", merge_mod.REVIEW_CI_LINE + "   \n", 1))

    def test_stamp_cause_wins_over_the_ci_line_cause_for_an_unstamped_record_with_a_note(self):
        # Catches: an unstamped record with a note after its CI line, and no cutover, named with the CI-line cause. The record
        # has no Stamp line, so the Stamp cause is the one to name.
        body = unstamped(record()) + "\n" + INCIDENT_NOTE + "\n"
        self.assertIsNone(self.in_process_cutover("main"), "fixture: a cutover is set for main")
        self.assertIsNone(merge_mod.parse_review(body, None, None), "fixture: merge reads the record with a note after the CI line")
        self.serve(comments=[body])
        out = self.stop(self.lane_turn(report(CLAIM)))
        self.assert_reads_of(PR)
        self.assert_blocked(out)
        self.assertIn("has no Stamp line", out["reason"], "the refusal does not name the missing Stamp line: %r" % out["reason"])
        self.assertNotIn("the CI line must be the last line", out["reason"],
                         "the refusal names the CI line, not the missing Stamp line: %r" % out["reason"])

    def test_ci_line_cause_is_named_for_a_stamped_record_with_a_note(self):
        # Control: a record with its Stamp line and a note after its CI line names the CI line, and no missing Stamp line.
        body = record() + "\n" + INCIDENT_NOTE + "\n"
        self.assertIsNone(merge_mod.parse_review(body), "fixture: merge reads the record with a note after the CI line")
        self.serve(comments=[body])
        out = self.stop(self.lane_turn(report(CLAIM)))
        self.assert_reads_of(PR)
        self.assert_blocked(out)
        self.assertIn("the CI line must be the last line", out["reason"],
                      "the refusal does not name the CI line as the cause: %r" % out["reason"])
        self.assertNotIn("has no Stamp line", out["reason"], "the refusal names a missing Stamp line the record has: %r" % out["reason"])

    def test_no_marked_comment_keeps_the_no_record_wording(self):
        # Catches: the parse wording replacing the no-record wording when no comment carries the marker at all.
        self.serve(comments=[CHATTER])
        out = self.stop(self.lane_turn(report(CLAIM)))
        self.assert_reads_of(PR)
        self.assert_blocked(out)
        self.assertIn("has no review record for its live head", out["reason"], out)
        self.assertNotIn("does not parse", out["reason"], out)

    # Passed: a record for the live head, and the reads that find it.

    def test_live_head_record_passes_on_two_rest_reads(self):
        # Catches: the live head's record not found, or the check reading through GraphQL or more than two calls.
        # The reads come first, so a miss shows as a read count and not as a bare block.
        self.serve(comments=[CHATTER, record()])
        out = self.stop(self.lane_turn(report(CLAIM)))
        self.assert_two_rest_reads()
        self.assertIsNone(out, out)

    def test_stop_reads_no_repo_record_for_the_default_branch(self):
        # Catches: the cutover read asking gh for the default branch through repos/{owner}/{repo}, a third read on each Stop.
        # The pull carries base.repo.default_branch, so the Stop reads the pull and its comments, and never the repo.
        self.serve(comments=[record()])
        out = self.stop(self.lane_turn(report(CLAIM)))
        repo_reads = [argv for argv in self.gh_calls() if "repos/{owner}/{repo}" in argv]
        self.assertEqual(repo_reads, [], "a Stop read the repo for its default branch: %r" % (self.gh_calls(),))
        self.assertIsNone(out, out)

    def test_record_past_the_first_page_of_comments_passes(self):
        # Full size: the record is the 101st comment. A read of one page of 30 or of 100 misses it.
        self.serve(comments=[CHATTER] * 100 + [record()])
        out = self.stop(self.lane_turn(report(CLAIM)))
        self.assert_two_rest_reads()
        self.assertIsNone(out, out)

    def test_round_fail_then_a_fix_pass_satisfies_the_claim(self):
        # Control: merge calls this record done, because the fix check passed the round. The check takes merge's
        # verdict, so the claim passes on the two reads.
        self.assert_record_satisfies_claim(record(rounds=[(1, "reviewer", "sonnet", "FAIL")],
                                                  fix=(OLD, "reviewer", "sonnet", "PASS")))

    def test_incident_record_without_the_note_passes(self):
        # Control: the incident's record with no note line passes at its live head, with its fix check. Merge reads it as
        # done, so the claim passes on the two reads. It is the green control beside the refusal above.
        no_note = incident(note=False)
        self.assertEqual(merge_mod.review_state(merge_mod.parse_review(no_note), INCIDENT_HEAD)[0], "done",
                         "fixture: merge/merge.py does not call the no-note record done")
        self.serve(prs={INCIDENT_PR: {"head": INCIDENT_HEAD, "comments": [no_note]}})
        out = self.stop(self.lane_turn(report("OTHER: round 3 PASS on PR #2189.")))
        self.assert_reads_of(INCIDENT_PR)
        self.assertIsNone(out, out)

    def test_ordinary_comment_newer_than_a_good_record_is_ignored(self):
        # Catches: the newest comment read as the record, so an ordinary comment posted after a good record refuses the claim.
        self.serve(comments=[record(), CHATTER])
        out = self.stop(self.lane_turn(report(CLAIM)))
        self.assert_two_rest_reads()
        self.assertIsNone(out, out)

    # Controls: no block, and no read, where the check does not apply.

    def test_non_lane_pass_claim_is_not_read_or_blocked(self):
        # Catches: an owner-facing session read for the review check, or refused for a claim it does not own.
        with self.subTest("owner-facing, no session id"):
            out = self.stop([trg.human("do the task"), trg.assistant_text(report(CLAIM))], env_id=False)
            self.assertIsNone(out, out)
            self.assertEqual(self.gh_calls(), [])
        with self.subTest("own record tagged coordinator, no parent"):
            records = [*self.lane_record(tags=("coordinator",), parent=None), trg.human("do the task"),
                       trg.assistant_text(report(CLAIM))]
            out = self.stop(records)
            self.assertIsNone(out, out)
            self.assertEqual(self.gh_calls(), [])

    def test_lane_without_a_review_pass_claim_makes_no_read(self):
        # Catches: a reply with no review claim read for the check, or a test's verdict read as a review claim.
        for line in ("OTHER: round 2 FAIL on PR #12, fix pending.",
                     "OTHER: verdict PASS for python3 lint/test_x.py on PR #12."):
            with self.subTest(line=line):
                out = self.stop(self.lane_turn(report(line)))
                self.assertIsNone(out, out)
                self.assertEqual(self.gh_calls(), [])

    def test_negated_pass_is_not_a_claim(self):
        # Catches: a PASS that a negation governs read as a claim made now.
        for line in ("OTHER: The reviewer returned FAIL, not PASS.", "OTHER: round 2 did not PASS on #12."):
            with self.subTest(line=line):
                self.serve()
                out = self.stop(self.lane_turn(report(line)))
                self.assertIsNone(out, out)
                self.assertEqual(self.gh_calls(), [])

    def test_history_line_is_not_a_claim(self):
        # Catches: a PASS that the line places in the past, as stale or before a change, blocking the reply.
        for line in ("OTHER: round 1 PASS on PR 12 was before the fix; round 2 is owed.",
                     "OTHER: Round 1 PASS on #12 was before the fix.",
                     "OTHER: round 1 PASS on #12 went stale after the push."):
            with self.subTest(line=line):
                self.serve()
                out = self.stop(self.lane_turn(report(line)))
                self.assertNotEqual((out or {}).get("decision"), "block", "history line blocked: %s" % line)

    def test_history_word_in_another_clause_does_not_hide_a_pass_claim(self):
        # Catches: a history word anywhere on the line hiding a PASS that sits in another clause. The clause that holds
        # the PASS decides, and clauses split on `,`, `;` and `--`.
        for line in ("OTHER: round 2 PASS on #12, superseding the stale round 1 FAIL.",
                     "OTHER: round 2 PASS on #12 -- previously FAIL, now PASS.",
                     "OTHER: reviewer PASS on #12; no longer blocked by CI."):
            with self.subTest(line=line):
                self.serve()
                out = self.stop(self.lane_turn(report(line)))
                self.assertNotEqual(self.gh_calls(), [], "the PASS claim was read as history: no PR was read")
                self.assert_reads_of(PR)
                self.assert_blocked(out)

    def test_fence_claim_is_not_a_claim(self):
        # Catches: a claim quoted in a fenced block, which is example text, read as a claim made now.
        fenced = "```\nOTHER: round 2 PASS on PR #12.\n```\n" + report("OTHER: round 2 FAIL on PR #12, fix pending.")
        out = self.stop(self.lane_turn(fenced))
        self.assertIsNone(out, out)
        self.assertEqual(self.gh_calls(), [])

    def test_landed_lane_reply_without_a_claim_is_clean(self):
        # Control: the landed fixture passes every other check, so the landed red case fails on this check alone.
        out = self.stop(self.lane_turn(report("OTHER: round 2 FAIL on PR #12, fix pending."), landed=True))
        self.assertIsNone(out, out)

    # A read that could not run: never a block, and never a clear.

    def test_failed_read_does_not_block(self):
        # Catches: a read that could not run refusing the reply, which would guess at a verdict.
        for label, failure in FAILED_READS:
            with self.subTest(label):
                self.serve(**failure)
                out = self.stop(self.lane_turn(report(CLAIM)))
                self.assertLessEqual(len(self.gh_calls()), 2)
                if out is not None:
                    self.assertNotEqual(out.get("decision"), "block", out)

    def test_failed_read_says_unknown_never_clear(self):
        # Catches: a failed read reported with no UNKNOWN word, or worded as clear.
        for label, failure in FAILED_READS:
            with self.subTest(label):
                self.serve(**failure)
                out = self.stop(self.lane_turn(report(CLAIM)))
                message = (out or {}).get("systemMessage", "")
                self.assertIn("UNKNOWN", message, out)
                self.assertNotRegex(message, r"(?i)\bclear\b", out)

    def delete_cutover_ref(self, base="main"):
        """Remove origin/<base>, the ref the cutover read asks for. The stand-in's default branch is main, so the read asks for origin/main."""
        subprocess.run(["git", "-C", self.repo, "update-ref", "-d", "refs/remotes/origin/" + base], check=True, capture_output=True)

    def test_a_failed_cutover_read_still_refuses_a_claim_with_no_record(self):
        # Catches: the cutover read's Stop (origin/main is gone here) skipping the whole record check, so a PASS claim with no record is given
        # an UNKNOWN note and let through. The pull and its comments were both read, and they hold no record, so the claim is refused.
        self.serve(comments=[CHATTER])
        self.delete_cutover_ref()
        out = self.stop(self.lane_turn(report(CLAIM)))
        self.assert_reads_of(PR)
        self.assert_blocked(out, msg="a failed cutover read let a PASS claim with no record through, as an UNKNOWN note:")
        self.assertIn("PR #12", out["reason"], out)

    def test_a_failed_cutover_read_does_not_refuse_a_stamped_record_for_the_live_head(self):
        # Control: the same missing origin/main, and a record stamped for the live head. The record stands, so the claim is not refused.
        self.serve(comments=[record()])
        self.delete_cutover_ref()
        out = self.stop(self.lane_turn(report(CLAIM)))
        self.assert_reads_of(PR)
        self.assertNotEqual((out or {}).get("decision"), "block", out)

    def test_a_failed_cutover_read_gives_an_unstamped_record_the_unknown_note_and_no_refusal(self):
        # Catches: a failed cutover read refusing a record that has no Stamp line and is otherwise well formed. Without the cutover
        # the record is unknown, so the claim gets the UNKNOWN note and no refusal.
        body = unstamped(record())
        self.assertEqual(merge_mod.review_state(merge_mod.parse_review(body, BEFORE, CUTOVER), LIVE)[0], "done",
                         "fixture: merge/merge.py does not read the unstamped record as well formed and done")
        self.serve(comments=[body])
        self.delete_cutover_ref()
        out = self.stop(self.lane_turn(report(CLAIM)))
        self.assert_reads_of(PR)
        self.assertNotEqual((out or {}).get("decision"), "block", "a failed cutover read refused an unstamped record: %r" % (out,))
        self.assertIn("UNKNOWN", (out or {}).get("systemMessage", ""), out)

    def test_a_failed_cutover_read_still_refuses_a_record_whose_stamp_does_not_match(self):
        # Catches: a newest record whose Stamp line does not match its lines (here FAIL edited to PASS) read as an unstamped record
        # the cutover could place, so a failed cutover read lets the PASS claim through. A Stamp line that is there must match.
        body = record(rounds=[(1, "reviewer", "sonnet", "FAIL")]).replace("Round 1: reviewer, sonnet, FAIL",
                                                                          "Round 1: reviewer, sonnet, PASS", 1)
        self.assertIn("Round 1: reviewer, sonnet, PASS", body, "fixture: the edit did not reach the round line")
        self.assertIsNone(merge_mod.parse_review(body), "fixture: merge/merge.py reads the edited record as well formed")
        self.serve(comments=[body])
        self.delete_cutover_ref()
        out = self.stop(self.lane_turn(report(CLAIM)))
        self.assert_reads_of(PR)
        self.assert_blocked(out, "a failed cutover read let a PASS claim through on a record whose Stamp line does not match:")
        self.assertIn("PR #12", out["reason"], out)

    def test_a_failed_cutover_read_still_refuses_a_record_with_a_malformed_field(self):
        # Catches: a newest record with a malformed field (Kind: weird, under a Stamp line that matches its text) read as no record
        # when the cutover read fails, so a failed cutover read lets the PASS claim through. A malformed record is refused.
        body = merge_mod.review_body(PR, LIVE, "weird", "no", ROUNDS, "not owed")
        self.assertIn("Kind: weird", body, "fixture: the record does not carry the malformed field")
        self.assertIsNone(merge_mod.parse_review(body), "fixture: merge/merge.py reads the record with Kind: weird as well formed")
        self.serve(comments=[body])
        self.delete_cutover_ref()
        out = self.stop(self.lane_turn(report(CLAIM)))
        self.assert_reads_of(PR)
        self.assert_blocked(out, "a failed cutover read let a PASS claim through on a record with a malformed field:")
        self.assertIn("PR #12", out["reason"], out)

    def test_a_failed_cutover_read_still_refuses_an_unstamped_record_naming_another_pr(self):
        # Catches: a failed cutover read passing an unstamped record for another pull request. The record is well formed and done for
        # the live head, so only its PR line decides: the cutover could place it, but no record names PR #12, so the claim is refused.
        body = unstamped(record(n=PR + 1))
        self.assertIsNone(merge_mod.parse_review(body, None, None), "fixture: merge/merge.py reads the unstamped record as well formed")
        placed = merge_mod.parse_review(body, "unknown", None)
        self.assertIsNotNone(placed, "fixture: merge/merge.py does not parse the unstamped record the way a failed read does")
        self.assertEqual(placed["n"], PR + 1, "fixture: the record does not name the other pull request")
        self.assertEqual(merge_mod.review_state(placed, LIVE)[0], "done", "fixture: the record is not done for the live head")
        self.serve(comments=[body])
        self.delete_cutover_ref()
        out = self.stop(self.lane_turn(report(CLAIM)))
        self.assert_reads_of(PR)
        self.assert_blocked(out, "a failed cutover read let a PASS claim through on an unstamped record for another PR:")
        self.assertIn("PR #12", out["reason"], out)

    def test_a_failed_cutover_read_still_refuses_an_unstamped_record_for_a_stale_head(self):
        # Catches: a failed cutover read passing an unstamped record for an earlier head. The record names this pull request and is
        # well formed, so only its head decides: merge's review_state calls it stale for the live head, and the claim is refused.
        body = unstamped(record(head=OLD))
        self.assertIsNone(merge_mod.parse_review(body, None, None), "fixture: merge/merge.py reads the unstamped record as well formed")
        placed = merge_mod.parse_review(body, "unknown", None)
        self.assertIsNotNone(placed, "fixture: merge/merge.py does not parse the unstamped record the way a failed read does")
        self.assertEqual(placed["n"], PR, "fixture: the record does not name this pull request")
        self.assertEqual(merge_mod.review_state(placed, LIVE)[0], "stale", "fixture: the record is not stale for the live head")
        self.serve(comments=[body])
        self.delete_cutover_ref()
        out = self.stop(self.lane_turn(report(CLAIM)))
        self.assert_reads_of(PR)
        self.assert_blocked(out, "a failed cutover read let a PASS claim through on an unstamped record for a stale head:")
        self.assertIn("PR #12", out["reason"], out)

    def test_a_slow_cutover_read_ends_within_the_hook_timeout_and_prints_the_unknown_note(self):
        # Catches: a cutover read whose fetches outlast the Stop hook's timeout. Each fetch takes 21 s of fake time, under merge's 25 s
        # per-call cap, so each one completes, and three of them outlast the hook's timeout. A hook killed there prints nothing, a silent
        # allow. The read must end inside the timeout, and the hook must print the UNKNOWN cutover note.
        out, log = self.slow_cutover_run(step=21)
        timeout = self.report_hook_timeout()
        self.assertIsNotNone(out, "the hook printed nothing: it was killed, or it never reached the cutover read")
        message = out.get("systemMessage", "")
        self.assertIn("UNKNOWN", message, "the hook printed no UNKNOWN note: %r" % (out,))
        self.assertIn("review cutover could not be read for PR #%d" % PR, message, "the note is not the cutover note: %r" % (out,))
        self.assertNotEqual(out.get("decision"), "block", "a failed cutover read blocked a record that is stamped and done: %r" % (out,))
        self.assertLessEqual(log["elapsed"], timeout, "the cutover read ran %g s of fake time, past the hook's %d s timeout, over %d fetches"
                             % (log["elapsed"], timeout, len(log["fetches"])))

    def test_the_report_guard_reads_the_cutover_under_a_shared_deadline_below_the_hook_timeout(self):
        # Catches: a cutover read with no budget. The budget is the seconds of the shared deadline the report guard opens around the read
        # (merge's shared_deadline, the one home of a read's budget). Each one must be above zero and below the hook's timeout, which is
        # read from settings.json here, never copied.
        out, log = self.slow_cutover_run(step=21)
        timeout = self.report_hook_timeout()
        self.assertTrue(log["spans"], "the report guard opened no shared deadline around the cutover read, so the read has no budget")
        for seconds in log["spans"]:
            self.assertGreater(seconds, 0, "the cutover budget is %r s, not above zero" % (seconds,))
            self.assertLess(seconds, timeout, "the cutover budget of %r s is not below the hook's %d s timeout" % (seconds, timeout))

    # The Stop's budget: every gh read of one Stop shares REVIEW_HOOK_BUDGET, on the fake clock of budget_run.

    def test_a_gh_read_that_starts_past_the_budget_is_not_started_and_the_hook_ends_inside_it(self):
        # Catches: a gh read given no budget. Each read takes more than the whole budget, so the first pull request's head read is cut at
        # the budget's end and spends it. The second pull request's head read must not start: its UNKNOWN read note must print, and the hook
        # must end inside the budget. The second pull request holds a stamped record, so a read that ran would pass it silently.
        budget = rg.REVIEW_HOOK_BUDGET
        prs = {PR: {"head": LIVE, "comments": [CHATTER]}, PR + 1: {"head": LIVE, "comments": [record(n=PR + 1)]}}
        out, log = self.budget_run(prs, {"pulls/": budget + 1, "/comments": budget + 1},
                                   report(CLAIM, "OTHER: round 2 PASS on PR #%d." % (PR + 1)))
        reads = [argv for _start, _timeout, argv in log["reads"]]
        self.assertTrue(any(a.endswith("pulls/%d" % PR) for argv in reads for a in argv),
                        "fixture: the first pull request's head read did not run, so the budget was not spent: %r" % (reads,))
        self.assertFalse(any(a.endswith("pulls/%d" % (PR + 1)) for argv in reads for a in argv),
                         "the second pull request's head was read after the budget was spent: %r" % (reads,))
        self.assertFalse(any(a.endswith("pulls/%d" % (PR + 1)) for argv in self.gh_calls() for a in argv),
                         "the stand-in answered the second pull request's head read: %r" % (self.gh_calls(),))
        self.assertIsNotNone(out, "the hook printed nothing")
        self.assertIn("Review-record guard: UNKNOWN, the check read nothing for PR #%d" % (PR + 1), out.get("systemMessage", ""),
                      "the second pull request has no UNKNOWN read note: %r" % (out,))
        self.assertLessEqual(log["elapsed"], budget, "the hook ended at %r s of fake time, past its %d s budget" % (log["elapsed"], budget))

    def test_a_slow_gh_read_is_given_the_time_left_not_the_full_read_timeout(self):
        # Catches: a gh read given REVIEW_READ_TIMEOUT when the Stop has less left. The head read is quick, so the comment read starts with
        # the budget less 5 s. That read is slower than the read timeout, so it must be given what is left, and it is cut at the budget's end.
        budget, cap, quick = rg.REVIEW_HOOK_BUDGET, rg.REVIEW_READ_TIMEOUT, 5
        self.assertLess(budget - quick, cap, "fixture: the time left is not under the read timeout, so the two cannot be told apart")
        out, log = self.budget_run({PR: {"head": LIVE, "comments": [record()]}}, {"pulls/": quick, "/comments": cap + 10}, report(CLAIM))
        reads = log["reads"]
        self.assertGreaterEqual(len(reads), 2, "fixture: PR %d made %d gh reads, not its head and its comments: %r" % (PR, len(reads), reads))
        self.assertEqual([start for start, _timeout, _argv in reads[:2]], [0.0, quick],
                         "fixture: the gh reads did not start at fake times on the hook's clock: %r" % (reads,))
        for start, timeout, argv in reads:
            self.assertLessEqual(timeout, budget - start, "a gh read that started at %r s was given %r s, more than the %r s the Stop has left: %r"
                                 % (start, timeout, budget - start, argv))
        self.assertLessEqual(log["elapsed"], budget, "the hook ended at %r s of fake time, past its %d s budget" % (log["elapsed"], budget))

    def test_a_spent_budget_never_lets_a_claim_pass_without_a_note(self):
        # Catches: a gh read that runs on past the Stop's budget and reads a record, so each claim passes with no note. Both pull requests
        # hold a stamped record for the live head, which passes if read, and every read takes more than the whole budget. The hook must end
        # inside its timeout, since a killed hook prints nothing, and each claimed pull request must carry its UNKNOWN read note.
        timeout = self.report_hook_timeout()
        budget = rg.REVIEW_HOOK_BUDGET
        prs = {PR: {"head": LIVE, "comments": [record()]}, PR + 1: {"head": LIVE, "comments": [record(n=PR + 1)]}}
        out, log = self.budget_run(prs, {"pulls/": budget + 1, "/comments": budget + 1},
                                   report(CLAIM, "OTHER: round 2 PASS on PR #%d." % (PR + 1)))
        self.assertLessEqual(log["elapsed"], timeout, "the hook ran %r s of fake time, past its %d s timeout: a killed hook prints nothing, a silent pass"
                             % (log["elapsed"], timeout))
        self.assertIsNotNone(out, "the hook printed nothing, so its claims passed with no note")
        for n in (PR, PR + 1):
            self.assertIn("the check read nothing for PR #%d" % n, out.get("systemMessage", ""), "PR #%d passed with no read note: %r" % (n, out))

    # The run-again cause (decision `pr-review-record`): a claim whose record the Stop's budget cut before the read is refused with that cause.
    # The two controls below run the same reads with time to spare, so each red case differs from its control by the budget alone.

    def test_control_comment_read_inside_the_budget_with_no_record_is_refused_as_no_record(self):
        # Control for the run-again case: the same slow pulls read, with the comment read inside what is left. The record is read and holds
        # none, so the refusal is the no-record cause, and it never carries the run-again wording.
        budget = rg.REVIEW_HOOK_BUDGET
        pulls_s, comments_s = 20, budget - 20 - 1
        self.assertLess(comments_s, budget - pulls_s, "fixture: the comment read does not fit in what is left of the budget")
        out, log = self.budget_run({PR: {"head": LIVE, "comments": [CHATTER]}}, {"pulls/": pulls_s, "/comments": comments_s}, report(CLAIM))
        self.assertTrue(any(a.endswith("issues/%d/comments" % PR) for argv in self.gh_calls() for a in argv),
                        "fixture: the comment read did not reach the stand-in, so no record was read: %r" % (self.gh_calls(),))
        self.assert_blocked(out, msg="a claim with no record was not refused:")
        self.assertIn("PR #12", out["reason"], out)
        self.assertIn("no review record", out["reason"], out)
        self.assertNotRegex(out["reason"], r"(?i)\brun again\b", "the no-record refusal carries the budget's run-again cause: %r" % (out,))

    def test_control_record_read_with_budget_left_for_the_cutover_is_not_refused(self):
        # Control for the spent-budget case: the same stamped record for the live head, with time left after the reads. The record stands.
        budget = rg.REVIEW_HOOK_BUDGET
        out, log = self.budget_run({PR: {"head": LIVE, "comments": [record()]}}, {"pulls/": 20, "/comments": 5}, report(CLAIM))
        self.assertTrue(any(a.endswith("issues/%d/comments" % PR) for argv in self.gh_calls() for a in argv),
                        "fixture: the comment read did not reach the stand-in, so no record was read: %r" % (self.gh_calls(),))
        self.assertLess(log["elapsed"], budget, "fixture: the reads spent the whole budget, so the cutover read had none")
        self.assertNotEqual((out or {}).get("decision"), "block", "a stamped record for the live head was refused with time left: %r" % (out,))

    def test_a_budget_that_cuts_the_comment_read_refuses_the_claim_to_run_again(self):
        # Catches: a claim with no record passing on an UNKNOWN note alone when the Stop's budget cuts its comment read. The pulls read takes
        # 20 s, so the comment read gets the 8 s left and takes 10 s: it is cut, the record is never read, and the claim is refused with the
        # run-again cause.
        budget = rg.REVIEW_HOOK_BUDGET
        pulls_s, comments_s = 20, 10
        self.assertLess(pulls_s, budget, "fixture: the pulls read alone spends the budget")
        self.assertGreater(comments_s, budget - pulls_s, "fixture: the comment read fits in what is left, so the budget does not cut it")
        out, log = self.budget_run({PR: {"head": LIVE, "comments": [CHATTER]}}, {"pulls/": pulls_s, "/comments": comments_s}, report(CLAIM))
        comment_reads = [(start, timeout) for start, timeout, argv in log["reads"] if any(a.endswith("issues/%d/comments" % PR) for a in argv)]
        self.assertEqual(comment_reads, [(float(pulls_s), budget - pulls_s)],
                         "fixture: the comment read did not start at %d s with %d s left: %r" % (pulls_s, budget - pulls_s, log["reads"]))
        self.assertFalse(any(a.endswith("issues/%d/comments" % PR) for argv in self.gh_calls() for a in argv),
                         "fixture: the stand-in answered the comment read, so the budget did not cut it: %r" % (self.gh_calls(),))
        self.assert_blocked(out, msg="the budget cut the comment read before the record was read, and the claim passed on an UNKNOWN note alone, not a refusal:")
        self.assertRegex(out["reason"], r"(?i)\brun again\b", "the refusal does not tell the reader to run again: %r" % (out,))
        self.assertIn("PR #12", out["reason"], out)

    def test_a_budget_spent_before_the_cutover_read_refuses_a_record_that_would_pass(self):
        # Catches: a claim passing on the cutover's UNKNOWN note alone when the Stop's budget is spent before the cutover read. The pulls read
        # takes 20 s and the comment read takes the 8 s left. It reads the record, which passes, and leaves the cutover read no time. The
        # claim is refused with the run-again cause, not let through on the note.
        budget = rg.REVIEW_HOOK_BUDGET
        pulls_s, comments_s = 20, budget - 20
        body = record()
        self.assertEqual(merge_mod.review_state(merge_mod.parse_review(body), LIVE)[0], "done",
                         "fixture: merge/merge.py does not call this record done")
        out, log = self.budget_run({PR: {"head": LIVE, "comments": [body]}}, {"pulls/": pulls_s, "/comments": comments_s}, report(CLAIM))
        self.assertTrue(any(a.endswith("issues/%d/comments" % PR) for argv in self.gh_calls() for a in argv),
                        "fixture: the comment read did not reach the stand-in, so the record was not read: %r" % (self.gh_calls(),))
        self.assertEqual(log["elapsed"], budget, "fixture: the reads did not spend the whole budget before the cutover read: %r" % (log["elapsed"],))
        self.assert_blocked(out, msg="the budget ran out before the cutover read, and the claim passed on the cutover's UNKNOWN note alone, not a refusal:")
        self.assertRegex(out["reason"], r"(?i)\brun again\b", "the refusal does not tell the reader to run again: %r" % (out,))
        self.assertIn("PR #12", out["reason"], out)


if __name__ == "__main__":
    unittest.main()
